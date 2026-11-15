"""Scheduled monthly PDF generation and individually addressed email delivery.

Generate-only is the default. Sending requires --send, active recipients, TLS,
and configured SMTP. Ambiguous SMTP outcomes require operator reconciliation.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, parseaddr
import fcntl
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import smtplib
import sqlite3
import ssl

from monthlyreport import MonthlyReportError, build_summary, create_pdf, money, pct, period_bounds, previous_month
from paperconfig import PaperRuntimeConfig
from secretredaction import redact_sensitive_message


@dataclass(frozen=True)
class Subscriber:
    user_id: str
    name: str
    email: str
    start_month: str
    active: bool
    portfolio_id: str = "paper-default"


def load_subscribers(path: Path) -> list[Subscriber]:
    if path.is_symlink():
        raise MonthlyReportError("Recipient configuration cannot be a symlink")
    document = json.loads(path.read_text())
    if document.get("schema_version") != 1 or not isinstance(document.get("users"), list):
        raise MonthlyReportError("Expected schema_version 1 and a users list")
    subscribers, ids, addresses = [], set(), set()
    for item in document["users"]:
        user = Subscriber(**item)
        for key in (user.user_id, user.portfolio_id):
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key):
                raise MonthlyReportError("Invalid user/portfolio identifier")
        if not isinstance(user.name, str) or not 1 <= len(user.name.strip()) <= 120 or any(ord(char)<32 for char in user.name):
            raise MonthlyReportError("Invalid subscriber display name")
        if not isinstance(user.email, str) or len(user.email)>254 or not re.fullmatch(r"[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+", user.email):
            raise MonthlyReportError("Each subscriber needs exactly one valid email address")
        if type(user.active) is not bool:
            raise MonthlyReportError("Subscriber active must be a JSON boolean")
        period_bounds(user.start_month)
        address = (user.portfolio_id, user.email.casefold())
        if user.user_id in ids or address in addresses:
            raise MonthlyReportError("Duplicate subscriber ID or portfolio email address")
        ids.add(user.user_id)
        addresses.add(address)
        subscribers.append(user)
    return subscribers


class DeliveryLedger:
    def __init__(self, path: Path):
        self.path = path
        if path.is_symlink():
            raise MonthlyReportError("Delivery database cannot be a symlink")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        except FileExistsError:
            pass
        with closing(self.connect()) as connection:
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS deliveries (
                    portfolio_id TEXT NOT NULL, month TEXT NOT NULL, user_id TEXT NOT NULL,
                    recipient TEXT NOT NULL, report_id TEXT NOT NULL, pdf_sha256 TEXT NOT NULL,
                    message_id TEXT NOT NULL, status TEXT NOT NULL,
                    updated_at TEXT NOT NULL, detail TEXT,
                    PRIMARY KEY (portfolio_id, month, user_id),
                    CHECK(status IN ('PREPARED','SENDING','SENT','FAILED','UNKNOWN'))
                );
                CREATE TABLE IF NOT EXISTS resolutions (
                    sequence INTEGER PRIMARY KEY, portfolio_id TEXT NOT NULL, month TEXT NOT NULL,
                    user_id TEXT NOT NULL, outcome TEXT NOT NULL, reviewer TEXT NOT NULL,
                    reason TEXT NOT NULL, occurred_at TEXT NOT NULL
                );
            """)

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def get(self, portfolio, month, user_id):
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT * FROM deliveries WHERE portfolio_id=? AND month=? AND user_id=?",
                                     (portfolio, month, user_id)).fetchone()
        return dict(row) if row else None

    def reserve(self, user, artifact, message_id, *, retry_failed=False):
        key = (artifact["portfolio_id"], artifact["month"], user.user_id)
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status FROM deliveries WHERE portfolio_id=? AND month=? AND user_id=?", key).fetchone()
            if row and row["status"] == "SENT":
                connection.rollback()
                return "ALREADY_SENT"
            if row and (row["status"] != "FAILED" or not retry_failed):
                connection.rollback()
                return "NEEDS_REVIEW" if row["status"] != "FAILED" else "FAILED_PREVIOUSLY"
            connection.execute("""INSERT INTO deliveries VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(portfolio_id,month,user_id) DO UPDATE SET recipient=excluded.recipient,
                report_id=excluded.report_id, pdf_sha256=excluded.pdf_sha256, message_id=excluded.message_id,
                status=excluded.status, updated_at=excluded.updated_at, detail=NULL""",
                (*key, user.email, artifact["report_id"], artifact["pdf_sha256"], message_id,
                 "PREPARED", datetime.now(timezone.utc).isoformat(), None))
            connection.commit()
        return "RESERVED"

    def update(self, portfolio, month, user_id, status, detail=None):
        with closing(self.connect()) as connection, connection:
            connection.execute("UPDATE deliveries SET status=?, updated_at=?, detail=? WHERE portfolio_id=? AND month=? AND user_id=?",
                               (status, datetime.now(timezone.utc).isoformat(), detail, portfolio, month, user_id))

    def resolve(self, portfolio, month, user_id, outcome, reviewer, reason):
        if outcome not in {"SENT", "FAILED"} or not reviewer.strip() or not reason.strip():
            raise MonthlyReportError("Resolution requires SENT/FAILED, a reviewer, and evidence-based reason")
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status FROM deliveries WHERE portfolio_id=? AND month=? AND user_id=?", (portfolio, month, user_id)).fetchone()
            if not row or row["status"] not in {"UNKNOWN", "SENDING", "PREPARED"}:
                raise MonthlyReportError("Only interrupted or ambiguous delivery attempts can be resolved")
            now = datetime.now(timezone.utc).isoformat()
            connection.execute("INSERT INTO resolutions (portfolio_id,month,user_id,outcome,reviewer,reason,occurred_at) VALUES (?,?,?,?,?,?,?)",
                               (portfolio, month, user_id, outcome, reviewer, reason, now))
            connection.execute("UPDATE deliveries SET status=?,updated_at=?,detail=? WHERE portfolio_id=? AND month=? AND user_id=?",
                               (outcome, now, reason, portfolio, month, user_id))
            connection.commit()


def make_message(config, user, summary, artifact):
    if (artifact["user_id"] != user.user_id or artifact["portfolio_id"] != user.portfolio_id
            or artifact["portfolio_id"] != summary["portfolio_id"] or artifact["month"] != summary["month"]):
        raise MonthlyReportError("Attachment does not belong to this subscriber, portfolio and month")
    if summary.get("kind") == "CONTRACT_BOUND_PROSPECTIVE_SHADOW":
        from portfolio_contract import validate_contract
        for c in summary.get("portfolio_contracts",[]):
            validate_contract(c)
            if c["portfolio_key"] != summary["portfolio_id"]:
                raise MonthlyReportError("Monthly portfolio identity mismatch")
    sender = parseaddr(config.smtp_sender or "")[1]
    if not sender or "@" not in sender:
        raise MonthlyReportError("A valid SMTP sender is required")
    month = datetime.strptime(summary["month"], "%Y-%m").strftime("%B %Y")
    key = f"{summary['portfolio_id']}:{summary['month']}:{user.user_id}"
    message = EmailMessage()
    message["From"], message["To"] = config.smtp_sender, user.email
    message["Subject"] = f"REGIME | {month} paper portfolio report"
    message["Date"] = format_datetime(datetime.now(timezone.utc))
    message["Message-ID"] = f"<{hashlib.sha256(key.encode()).hexdigest()}@{sender.split('@')[-1]}>"
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(
        f"Hello {user.name},\n\nYour {month} shared paper portfolio report is attached.\n\n"
        f"Portfolio: {summary['portfolio_id']} / basis: {summary.get('valuation_basis','SAVED_PAPER_ACCOUNT')}\n"
        f"Coverage: {summary['coverage']} ({summary['observed_sessions']} of {summary['expected_sessions']} NYSE sessions).\n"
        f"Monthly return: {pct(summary['monthly_return'])}\nLast recorded NAV: {money(summary['closing_nav'])}\n\n"
        "Missing period boundaries are shown as unavailable. These are saved paper-account results, not live brokerage assets.\n\n"
        "REGIME Portfolio Intelligence\nPlease contact your portfolio operator to change report preferences.\n"
    )
    message.add_alternative(
        '<html><body style="font:14px Arial,sans-serif;color:#183047;max-width:620px;margin:30px auto">'
        '<div style="background:#152c42;color:white;padding:24px;font-weight:bold;letter-spacing:3px">REGIME</div>'
        f'<div style="padding:24px"><h2>Your {escape(month)} report</h2><p>Hello {escape(user.name)},</p>'
        '<p>Your shared paper portfolio report is attached as a PDF.</p>'
        f'<p><strong>Coverage:</strong> {escape(summary["coverage"])} &middot; {summary["observed_sessions"]}/{summary["expected_sessions"]} sessions</p>'
        f'<p><strong>Monthly return:</strong> {escape(pct(summary["monthly_return"]))}<br>'
        f'<strong>Last recorded NAV:</strong> {escape(money(summary["closing_nav"]))}</p>'
        '<p style="color:#677e90;font-size:12px">Historical paper-account results. Missing boundaries are reported as unavailable. Contact your operator to change report preferences.</p>'
        '</div></body></html>', subtype="html")
    payload = Path(artifact["pdf"]).read_bytes()
    if hashlib.sha256(payload).hexdigest() != artifact["pdf_sha256"] or not payload.startswith(b"%PDF-"):
        raise MonthlyReportError("PDF attachment integrity check failed")
    message.add_attachment(payload, maintype="application", subtype="pdf", filename=f"regime-paper-{summary['month']}.pdf")
    return message


def deliver(config, user, summary, artifact, ledger, *, retry_failed=False, smtp_factory=smtplib.SMTP):
    if not user.active or user.portfolio_id != summary["portfolio_id"] or summary["month"] < user.start_month:
        return {"user_id": user.user_id, "status": "SKIPPED_NOT_ENROLLED"}
    if not config.smtp_host or not config.smtp_use_tls:
        raise MonthlyReportError("Monthly delivery requires configured SMTP with TLS enabled")
    if summary.get("kind") == "CONTRACT_BOUND_PROSPECTIVE_SHADOW" and summary["coverage"] != "COMPLETE":
        return {"user_id": user.user_id, "status": "BLOCKED_INCOMPLETE_STRATEGY_PERIOD"}
    if summary["sources"] and not summary["database_verified"]:
        raise MonthlyReportError("Email delivery requires database-verified source records")
    message = make_message(config, user, summary, artifact)
    status = ledger.reserve(user, artifact, str(message["Message-ID"]), retry_failed=retry_failed)
    if status != "RESERVED":
        return {"user_id": user.user_id, "status": status}
    key = (summary["portfolio_id"], summary["month"], user.user_id)
    smtp, attempted, accepted = None, False, False
    ledger.update(*key, "SENDING")
    try:
        smtp = smtp_factory(config.smtp_host, config.smtp_port, timeout=30)
        smtp.starttls(context=ssl.create_default_context())
        if config.smtp_username:
            smtp.login(config.smtp_username, config.smtp_password or "")
        attempted = True
        refused = smtp.send_message(message, from_addr=parseaddr(config.smtp_sender)[1], to_addrs=[user.email])
        if refused:
            ledger.update(*key, "FAILED", "Recipient was refused by SMTP")
            return {"user_id": user.user_id, "status": "FAILED"}
        accepted = True
        ledger.update(*key, "SENT", "SMTP accepted the message; human receipt is not confirmed")
        return {"user_id": user.user_id, "status": "SENT", "message_id": str(message["Message-ID"])}
    except Exception as exc:
        status = "UNKNOWN" if attempted or accepted else "FAILED"
        detail = redact_sensitive_message(f"{type(exc).__name__}: {exc}", (config.smtp_password or "",))
        ledger.update(*key, status, detail)
        return {"user_id": user.user_id, "status": status}
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                try:
                    smtp.close()
                except Exception:
                    pass


def write_status(output: Path, result: dict):
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = output / "last-run.json.tmp"
    temporary.write_text(json.dumps({**result, "updated_at": datetime.now(timezone.utc).isoformat()}, indent=2, sort_keys=True) + "\n")
    temporary.chmod(0o600)
    temporary.replace(output / "last-run.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipients", type=Path, default=Path(os.environ.get("PAPER_MONTHLY_RECIPIENTS_FILE", ".env.monthly-recipients.json")))
    parser.add_argument("--output", type=Path, default=Path("var/monthly-reports"))
    parser.add_argument("--portfolio-id", default="paper-default")
    parser.add_argument("--strategy-ledger", type=Path, help="Contract-bound shadow ledger; requires explicit --portfolio-id")
    parser.add_argument("--macro-features", type=Path)
    parser.add_argument("--latest-macro-features", type=Path)
    parser.add_argument("--macro-forecasts", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--month", default=None, help="Completed month YYYY-MM; defaults to prior New York month")
    run.add_argument("--send", action="store_true")
    run.add_argument("--retry-failed", action="store_true")
    resolve = commands.add_parser("resolve")
    resolve.add_argument("--month", required=True)
    resolve.add_argument("--user-id", required=True)
    resolve.add_argument("--outcome", choices=("SENT", "FAILED"), required=True)
    resolve.add_argument("--reviewer", required=True)
    resolve.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    try:
        config = PaperRuntimeConfig.from_env()
        config.state_database.parent.mkdir(parents=True, exist_ok=True)
        # Share the worker/backup lock for the whole monthly operation, including delivery DB writes.
        with config.state_database.with_suffix(config.state_database.suffix + ".lock").open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise MonthlyReportError("Paper worker, backup, or monthly delivery is active") from exc
            ledger = DeliveryLedger(args.output / "deliveries.sqlite3")
            if args.command == "resolve":
                period_bounds(args.month)
                ledger.resolve(args.portfolio_id, args.month, args.user_id, args.outcome, args.reviewer, args.reason)
                result = {"status": "RESOLVED", "user_id": args.user_id, "month": args.month}
            else:
                month = args.month or previous_month()
                if not args.strategy_ledger:
                    summary = build_summary(config.report_directory, month, database=config.state_database, portfolio_id=args.portfolio_id, macro_features=json.loads(args.macro_features.read_text()) if args.macro_features else None, macro_forecasts=json.loads(args.macro_forecasts.read_text()) if args.macro_forecasts else None, latest_macro_features=json.loads(args.latest_macro_features.read_text()) if args.latest_macro_features else None)
                if args.strategy_ledger:
                    if args.portfolio_id == "paper-default":
                        raise MonthlyReportError("An explicit strategy portfolio ID is required")
                    from strategy_monthly_report import build_strategy_summary
                    summary = build_strategy_summary(args.strategy_ledger, month, args.portfolio_id)
                users = [user for user in load_subscribers(args.recipients)
                         if user.active and user.portfolio_id == args.portfolio_id and user.start_month <= month]
                results = []
                for user in users:
                    existing = ledger.get(args.portfolio_id, month, user.user_id) if args.send else None
                    if existing and existing["status"] == "SENT":
                        results.append({"user_id": user.user_id, "status": "ALREADY_SENT"})
                        continue
                    artifact = create_pdf(summary, user_id=user.user_id, name=user.name, output_directory=args.output)
                    results.append(deliver(config, user, summary, artifact, ledger, retry_failed=args.retry_failed)
                                   if args.send else {"user_id": user.user_id, "status": "GENERATED", "pdf": str(artifact["pdf"])})
                ok = all(item["status"] in {"GENERATED", "SENT", "ALREADY_SENT"} for item in results)
                result = {"status": "PASS" if ok else "REVIEW_REQUIRED", "month": month,
                          "coverage": summary["coverage"], "recipients": results,
                          "note": "No eligible active subscribers" if not results else "SMTP acceptance is not proof of human receipt"}
                write_status(args.output, result)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] in {"PASS", "RESOLVED"} else 2
    except Exception as exc:
        detail = redact_sensitive_message(f"{type(exc).__name__}: {exc}", (os.environ.get("PAPER_SMTP_PASSWORD", ""),))
        result = {"status": "BLOCKED", "error": detail}
        try:
            write_status(args.output, result)
        except OSError:
            pass
        print(json.dumps(result))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
