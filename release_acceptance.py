"""One read-only release audit, with isolated report/recovery exercises.

Exit 0: ready for operator review; 1: failed checks; 2: unmet prerequisites;
3: another acceptance/daily job is active. Never approves or submits trades,
sends email, refreshes models, or adds prospective observations.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid
import xml.etree.ElementTree as ET

from strategy_integrity import file_hash, fingerprint, strict_json
from strategy_receipts import atomic_json
from forward_cohort import database as cohort_database

ROOT = Path(__file__).resolve().parent
VALID = {"PASS", "FAIL", "BLOCKED"}


@dataclass
class Config:
    bundle: Path = Path("var/investor-dashboard/latest-strategy-run.json")
    dashboard: Path = Path("var/investor-dashboard/investor-dashboard.html")
    operations: Path = Path("var/strategy-operations-integrated-v1")
    challenger_index: Path = Path("var/institutional-return-engines/latest.json")
    challenger_database: Path = field(default_factory=lambda: cohort_database(Path("var/return-engine-shadow-v1")))
    output: Path = Path("var/release-acceptance")
    portfolio: str = "Growth_Resilience_reference"
    financial_evidence: Path | None = None
    qualification_release: Path | None = None
    qualification_evidence: Path = Path("var/qualification")
    product_mandate: Path | None = None
    product_evidence: Path | None = None
    browser_evidence: Path | None = None
    recipients: Path = Path(".env.monthly-recipients.json")
    monthly_delivery_root: Path = Path("var/monthly-reports")
    run_tests: bool = True


def result(status="PASS", reason="", **details):
    if status not in VALID:
        raise ValueError("Unknown acceptance status")
    return {"status": status, "reason": reason, "details": details}


def source_snapshot(root=ROOT):
    paths = set(root.glob("*.py")) | set(root.glob("Dockerfile*"))
    for pattern in [
        "dashboard/*",
        "pilot/*",
        "deploy/pilot/*",
        "research/*.json",
        "requirements*.lock",
        ".github/workflows/*",
        "deploy/systemd/*",
        "compose*.yaml",
        "ruff.toml",
    ]:
        paths.update(root.glob(pattern))
    return {
        str(p.relative_to(root)): file_hash(p)
        for p in sorted(paths)
        if p.is_file() and not p.is_symlink()
    }


def tracked_inputs(c):
    paths = {
        c.bundle,
        c.dashboard,
        c.dashboard.parent / "artifact-manifest.json",
        c.challenger_index,
        cohort_database(c.operations),
        c.operations / "active-cohort.json",
        c.challenger_database,
        c.challenger_database.parent / "active-cohort.json",
        c.operations / "latest-job.json",
    }
    if c.bundle.is_file():
        b = strict_json(c.bundle)
        for key in ["capture", "training_report", "portfolio_contracts"]:
            p = Path(b[key])
            paths.add(p)
        capture = Path(b["capture"])
        paths.update(capture.parent / n for n in strict_json(capture)["files"])
        report = Path(b["training_report"])
        paths.update(report.parent / n for n in strict_json(report)["artifacts"])
        extension = Path(b["benchmark_extension"])
        paths.update(
            extension / n for n in ["capture.json", "XLV-adjusted.csv", "news.json"]
        )
    manifest = c.dashboard.parent / "artifact-manifest.json"
    if manifest.is_file():
        m = strict_json(manifest)
        paths.update(c.dashboard.parent / n for n in m.get("pdfs", {}))
        if m.get("main_investor_pdf"):
            paths.add(Path(m["main_investor_pdf"]["path"]))
    if c.challenger_index.is_file():
        i = strict_json(c.challenger_index)
        paths.update(Path(i[k]) for k in ["assessment", "robustness"])
        if Path(i["robustness"]).is_file():
            paths.update(
                Path(p) for p in strict_json(i["robustness"])["source_artifacts"]
            )
    paths.add(c.recipients)
    delivery = c.monthly_delivery_root / "deliveries.sqlite3"
    paths.add(delivery)
    for source in [c.product_mandate, c.browser_evidence]:
        if source is not None:
            paths.add(source)
    from paper_release import safe_file

    for source in [c.browser_evidence]:
        if source is not None and source.is_file():
            for item in strict_json(source).get("artifacts", []):
                paths.add(safe_file(source.parent, item["path"]))
    for evidence in [
        c.qualification_evidence if c.qualification_release else None,
        c.product_evidence,
    ]:
        if evidence is not None:
            for receipt in (evidence / "records").glob("*.json"):
                paths.add(receipt)
                for item in strict_json(receipt).get("artifacts", []):
                    paths.add(safe_file(evidence, item["path"]))
    if c.qualification_release is not None:
        manifest = c.qualification_release / "release-manifest.json"
        paths.add(manifest)
        if manifest.is_file():
            paths.update(
                safe_file(c.qualification_release, n)
                for n in strict_json(manifest)["files"]
            )
    if c.financial_evidence is not None:
        for filename in ["cash-history.json", "exposures.json", "execution-costs.json"]:
            manifest = c.financial_evidence / filename
            paths.add(manifest)
            if manifest.is_file():
                doc = strict_json(manifest)
                references = list(doc.get("evidence", []))
                if isinstance(doc.get("returns"), dict):
                    references.append(doc["returns"])
                for item in references:
                    paths.add(safe_file(c.financial_evidence, item["file"]))
    return {
        str(p.resolve()): file_hash(p) if p.is_file() and not p.is_symlink() else None
        for p in sorted(paths)
    }


ACTIONS = {
    "input_capture": "Refresh completed-session market/macro inputs and source-matched training; do not invent or backfill observations.",
    "dashboard_scenarios_pdf": "Rebuild the dashboard/PDF bundle from verified matching inputs and investigate failed checks.",
    "benchmark_recalculation": "Reconcile benchmark calculations with the captured inputs; preserve historical reports.",
    "challenger_replay": "Re-evaluate and reconcile challengers against the current verified bundle.",
    "core_ledger": "Reconcile the daily job and registered portfolio identities without rewriting a sealed session.",
    "challenger_ledger": "Run the locked challenger cycle on fresh verified inputs; preserve its frozen cohort.",
    "daily_job_monitoring": "Investigate the linked job/receipt chain and scheduling deadline on the qualified host.",
    "monthly_pdf_email_preview": "Repair report generation or attachment identity checks using isolated output.",
    "backup_restore": "Investigate backup/restore divergence before trusting recovery.",
    "financial_evidence": "Supply protected reviewed cash, cost, duration/FX/holdings and instrument-access evidence.",
    "completed_month_coverage": "Accumulate a complete post-registration month with verified boundaries; do not infer missing returns.",
    "monthly_delivery_evidence": "Configure protected sender/enrollment and collect authorized completed-period delivery evidence; this audit never sends.",
    "prospective_observation": "Accumulate real later sessions in both cohorts; repeated acceptance runs add no observations.",
    "host_image_alert_recovery_reviews": "Qualify an immutable current-source release, Linux host, alerts and recovery using existing qualification receipts.",
    "product_and_jurisdiction_reviews": "Complete existing product-scope, jurisdiction, suitability and independent review gates for the first pilot.",
    "browser_visual_qualification": "Supply matching dated browser interaction/rendering evidence and hashes, including mobile and failure states.",
    "pinned_runtime_environment": "Qualify the pinned Python/dependency environment in an immutable image; do not change the global interpreter to fake a match.",
    "python_style": "Resolve reported static-check failures.",
    "javascript_syntax": "Resolve parser errors or run in a supported development/CI environment with a syntax runtime.",
    "regression": "Run the full suite on this stable source snapshot and resolve all failures/skips.",
    "source_and_input_stability": "Retry after concurrent source/data writers finish; investigate any unexpected original-ledger change.",
}


class Audit:
    def __init__(self, c, run, now):
        self.c, self.run, self.now = c, run, now
        self.rows = []
        self.values = {}

    def stage(self, name, fn, *, category="engineering", requires=()):
        print(f"Checking {name}...", flush=True)
        start = time.monotonic()
        missing = [
            key for key in requires if self.values.get(key, {}).get("status") != "PASS"
        ]
        if missing:
            value = result(
                "BLOCKED", "Required upstream checks did not pass", upstream=missing
            )
        else:
            try:
                value = fn()
                if not isinstance(value, dict) or value.get("status") not in VALID:
                    raise ValueError("Invalid check result")
                json.dumps(value, allow_nan=False)
            except Exception as exc:
                from secretredaction import redact_sensitive_message

                value = result(
                    "FAIL", redact_sensitive_message(f"{type(exc).__name__}: {exc}")
                )
        row = {
            "id": name,
            "category": category,
            "duration_seconds": round(time.monotonic() - start, 3),
            **value,
        }
        if row["status"] != "PASS":
            row["priority"] = (
                "P0" if row["status"] == "FAIL" or category == "engineering" else "P1"
            )
            row["next_action"] = ACTIONS.get(
                name, "Investigate and supply valid evidence before release review."
            )
        self.rows.append(row)
        self.values[name] = row
        print(f"  {value['status']}: {value.get('reason', '')}", flush=True)
        return row

    def command(self, name, args, *, timeout=1200):
        log = self.run / (name + ".log")
        with log.open("w") as handle:
            log.chmod(0o600)
            p = subprocess.run(
                args,
                cwd=ROOT,
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        return p.returncode, {
            "log": str(log),
            "sha256": file_hash(log),
            "command": args,
        }


def check_inputs(a):
    from strategy_training_data import usable_session
    from strategy_report import load_training_report
    from portfolio_contract import extended_prices

    b = strict_json(a.c.bundle)
    r = load_training_report(b["training_report"])
    prices = extended_prices(b["capture"], b["benchmark_extension"])
    if not r["current_numerical_source_match"]:
        return result("FAIL", "Training numerical sources changed")
    expected = str(usable_session(a.now).date())
    if r["market_session"] != expected:
        return result(
            "BLOCKED",
            "Fresh completed-session capture and training required",
            expected=expected,
            actual=r["market_session"],
        )
    a.bundle, a.training, a.prices = b, r, prices
    return result(
        reason="Verified capture, healthcare extension and training sources",
        market_session=expected,
        instruments=len(prices.columns),
    )


def check_dashboard(a):
    from strategy_operations import audit
    from strategy_dashboard_server import read_payload

    evidence = audit(a.c.bundle, a.c.dashboard)
    a.payload = read_payload(a.c.dashboard)
    atomic_json(a.run / "dashboard-evidence.json", evidence)
    return result(
        "PASS" if evidence["status"] == "LOCAL_ACCEPTANCE_PASSED" else "BLOCKED",
        "Portfolio contracts, twenty scenarios, PDF bindings and dashboard evidence checked",
        checks=evidence["checks"],
    )


def check_benchmark(a):
    from growth_resilience import build_benchmark

    expected = build_benchmark(a.bundle["capture"], a.bundle["benchmark_extension"])
    if fingerprint(expected) != fingerprint(a.payload["growth_resilience"]):
        raise ValueError("Displayed benchmark differs from independent recalculation")
    return result(
        reason="Benchmark weights, history, risk and bootstrap independently reconciled",
        version=expected["version"],
    )


def normalized_replay_evidence(proof):
    # Equivalent relative and absolute artifact references identify the same files.
    # Numerical evidence remains exact; no return/risk tolerance is introduced.
    proof = json.loads(json.dumps(proof, allow_nan=False))
    proof["assessment"] = str(Path(proof["assessment"]).resolve())
    hashes = {str(Path(p).resolve()): h for p, h in proof["source_artifacts"].items()}
    if len(hashes) != len(proof["source_artifacts"]):
        raise ValueError("Duplicate aliases in replay evidence")
    proof["source_artifacts"] = hashes
    return proof


def check_challengers(a):
    from assess_return_engine_robustness import assess

    i = strict_json(a.c.challenger_index)
    if i["bundle_sha256"] != file_hash(a.c.bundle):
        return result("BLOCKED", "Refresh challenger evaluation for the current bundle")
    proof = assess(i["assessment"], a.c.bundle, a.run / "challenger-replay.json")
    if fingerprint(normalized_replay_evidence(proof)) != fingerprint(
        normalized_replay_evidence(strict_json(i["robustness"]))
    ):
        raise ValueError("Saved challenger diagnostics differ from independent replay")
    displayed = a.payload.get("return_engines", {})
    if normalized_replay_evidence(
        displayed.get("robustness", {})
    ) != normalized_replay_evidence(proof) or displayed.get(
        "assessment"
    ) != strict_json(i["assessment"]):
        raise ValueError("Challenger display does not match evaluated evidence")
    return result(
        reason="All four challenger trade paths, risk-matched references and displayed results reconciled",
        strategies=len(proof["strategies"]),
    )


def inspect_ledger(
    database,
    session,
    now,
    *,
    report_sha256=None,
    contract_map=None,
    assessment_sha256=None,
):
    from strategy_monthly_report import read_events

    events = read_events(database)
    if not events:
        return result("BLOCKED", "No prospective registration exists")
    last = events[-1][0]
    if any(datetime.fromisoformat(e["recorded_at"]) > now for e, _ in events):
        raise ValueError("Future observation in prospective ledger")
    if last["session"] != session:
        return result(
            "BLOCKED",
            "Prospective job is behind the market capture",
            last_session=last["session"],
            expected=session,
        )
    if report_sha256 is not None and last.get("report_sha256") != report_sha256:
        return result(
            "BLOCKED", "Registered decisions refer to a different training report"
        )
    if (
        assessment_sha256 is not None
        and last.get("assessment_sha256") != assessment_sha256
    ):
        return result(
            "BLOCKED",
            "Registered challengers refer to a different evaluated assessment",
        )
    if contract_map is not None:
        registered = last.get("portfolio_contracts", {})
        different = [
            key
            for key, c in contract_map.items()
            if registered.get(key, {}).get("contract_id") != c["contract_id"]
        ]
        if different:
            return result(
                "BLOCKED",
                "Displayed proposed contracts differ from registered decisions; reconcile explicitly without rewriting the ledger",
                portfolios=different,
            )
    known_contracts = {
        c["contract_id"]: c
        for e, _ in events
        for c in e.get("portfolio_contracts", {}).values()
    }
    if any(e.get("release_approved") is not False for e, _ in events):
        raise ValueError("Unexpected release flag in shadow ledger")
    for e, _ in events:
        for state in e["states"].values():
            pending = state.get("pending")
            if pending and pending["decision_session"] >= pending["fill_session"]:
                raise ValueError("Same-close prospective fill registered")
            if pending and pending.get("contract_id"):
                from portfolio_contract import normalized_weights

                contract = known_contracts.get(pending["contract_id"])
                if not contract:
                    raise ValueError("Pending decision has no registered contract")
                planned = normalized_weights(
                    {
                        **pending["weights"],
                        "USD_CASH": 1 - sum(pending["weights"].values()),
                    }
                )
                if set(planned) != set(contract["weights"]) or any(
                    abs(w - contract["weights"][s]) > 1e-10 for s, w in planned.items()
                ):
                    raise ValueError(
                        "Pending weights disagree with their portfolio contract"
                    )
        for marks in e["marks"].values():
            for mark in marks:
                fill = mark.get("fill")
                if fill and (
                    fill["decision_session"] >= mark["session"]
                    or fill["fill_session"] != mark["session"]
                ):
                    raise ValueError("Historical fill timing mismatch")
    return result(
        reason="Immutable chain and forward-only decision timing verified",
        observations=len(events),
        return_sessions=last["return_sessions"],
        chain_head=events[-1][1],
    )


def check_api(a):
    from io import BytesIO
    from strategy_dashboard_server import handler

    cls = handler(SimpleNamespace(payload=a.payload), "a" * 64)
    h = object.__new__(cls)
    h.server = SimpleNamespace(server_port=8768)
    h.send_response = lambda code: setattr(h, "code", code)
    h.send_header = lambda *args: None
    h.end_headers = lambda: None
    h.headers = {"Host": "127.0.0.1:8768"}
    h.path = "/api/dashboard"
    h.wfile = BytesIO()
    h.do_GET()
    if h.code != 401:
        raise ValueError("Unauthenticated financial API was not denied")
    h.headers["Authorization"] = "Bearer " + "a" * 64
    h.wfile = BytesIO()
    h.do_GET()
    if h.code != 200 or json.loads(h.wfile.getvalue()) != a.payload:
        raise ValueError(
            "Authenticated API does not serve the audited portfolio payload"
        )
    h.headers["Origin"] = "https://untrusted.invalid"
    h.wfile = BytesIO()
    h.do_GET()
    if h.code != 403:
        raise ValueError("Cross-origin access was not denied")
    return result(
        reason="Actual handler denies unauthenticated/cross-origin reads and serves the audited payload",
        scope="IN_PROCESS_NO_LISTENING_SERVER_OR_BROWSER",
    )


def check_runtime(a):
    import re
    from researchdatastore import ResearchDataStore

    provenance = ResearchDataStore.runtime_provenance()
    targets = set()
    for path in ROOT.glob("Dockerfile*"):
        targets.update(re.findall(r"FROM python:([0-9.]+)", path.read_text()))
    python_version = provenance["python_version"].split()[0]
    python_ok = len(targets) == 1 and python_version in targets
    mismatches = provenance["dependency_mismatches"]
    return result(
        "PASS" if python_ok and not mismatches else "BLOCKED",
        "Pinned Python/dependency environment must be qualified in the release image",
        current_python=python_version,
        image_python_versions=sorted(targets),
        dependency_mismatches=mismatches,
        scope="CURRENT_PROCESS_ONLY_NOT_A_DOCKER_BUILD",
    )


def check_regression(a):
    if not a.c.run_tests:
        return result(
            "BLOCKED",
            "Regression explicitly skipped; prior XML does not qualify this run",
        )
    code, proof = a.command(
        "regression",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            f"--junitxml={a.run / 'regression.xml'}",
        ],
    )
    xml = a.run / "regression.xml"
    if not xml.is_file():
        return result("FAIL", "Regression produced no result artifact", **proof)
    root = ET.parse(xml).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    counts = {
        key: sum(int(s.get(key, 0)) for s in suites)
        for key in ["tests", "failures", "errors", "skipped"]
    }
    ok = (
        code == 0
        and counts["tests"] > 0
        and counts["failures"] == 0
        and counts["errors"] == 0
        and counts["skipped"] == 0
    )
    return result(
        "PASS" if ok else "FAIL",
        "Fresh full regression; skips cannot silently qualify release",
        **counts,
        **proof,
        junit_sha256=file_hash(xml),
    )


def check_style(a):
    code, proof = a.command(
        "ruff",
        [sys.executable, "-m", "ruff", "check", "--output-format", "concise"],
        timeout=120,
    )
    return result("PASS" if code == 0 else "FAIL", "Static Python checks", **proof)


def check_js(a):
    node = shutil.which("node")
    swift = shutil.which("swift")
    source = ROOT / "dashboard/investor.js"
    if node:
        args = [node, "--check", str(source)]
    elif swift:
        script = a.run / "check-js.swift"
        script.write_text("""import Foundation
import JavaScriptCore
let c=JSContext()!
let s=try String(contentsOfFile:CommandLine.arguments[1],encoding:.utf8)
let d=try JSONSerialization.data(withJSONObject:s,options:[.fragmentsAllowed])
c.evaluateScript("new Function("+String(data:d,encoding:.utf8)!+")")
if let e=c.exception { print(e.toString() ?? "JavaScript error"); exit(1) }
print("JavaScript syntax verified; browser rendering not exercised")
""")
        args = [
            swift,
            "-module-cache-path",
            str(a.run / "swift-cache"),
            str(script),
            str(source),
        ]
    else:
        return result(
            "BLOCKED",
            "No JavaScript syntax runtime available; no installation attempted",
        )
    code, proof = a.command("javascript", args, timeout=180)
    return result(
        "PASS" if code == 0 else "FAIL",
        "Syntax check only; browser qualification remains separate",
        **proof,
    )


def check_monthly(a):
    from strategy_monthly_report import build_strategy_summary
    from monthlyreport import create_pdf, previous_month
    from monthlydelivery import Subscriber, make_message

    month = previous_month(a.now)
    summary = build_strategy_summary(
        cohort_database(a.c.operations), month, a.c.portfolio, now=a.now
    )
    artifact = create_pdf(
        summary,
        user_id="acceptance-preview",
        name="Release acceptance preview",
        output_directory=a.run / "monthly",
    )
    user = Subscriber(
        "acceptance-preview",
        "Release acceptance preview",
        "acceptance@example.invalid",
        "2000-01",
        False,
        a.c.portfolio,
    )
    message = make_message(
        SimpleNamespace(smtp_sender="preview@example.invalid"), user, summary, artifact
    )
    message["X-Release-Acceptance-Only"] = "true"
    attachments = list(message.iter_attachments())
    if (
        len(attachments) != 1
        or attachments[0].get_payload(decode=True) != Path(artifact["pdf"]).read_bytes()
    ):
        raise ValueError("Email attachment differs from generated portfolio PDF")
    path = a.run / "monthly-preview.eml"
    path.write_bytes(message.as_bytes())
    path.chmod(0o600)
    a.monthly_summary = summary
    return result(
        reason="Completed-month PDF and MIME attachment generated locally; no SMTP call",
        month=month,
        coverage=summary["coverage"],
        portfolio=a.c.portfolio,
        pdf=str(artifact["pdf"]),
        pdf_sha256=artifact["pdf_sha256"],
        email_sha256=file_hash(path),
        email_sent=False,
    )


def check_monthly_delivery(a):
    # Inspect existing evidence only. No delivery worker or SMTP connection runs.
    if a.monthly_summary["coverage"] != "COMPLETE":
        return result(
            "BLOCKED",
            "No complete monthly portfolio period exists to verify actual report delivery",
        )
    if not os.environ.get("PAPER_SMTP_HOST") or not os.environ.get("PAPER_SMTP_SENDER"):
        return result(
            "BLOCKED",
            "Monthly SMTP sender is not configured in this acceptance process; no credentials are printed",
        )
    from monthlydelivery import load_subscribers

    if not a.c.recipients.is_file():
        return result("BLOCKED", "No protected recipient enrollment supplied")
    month = a.monthly_summary["month"]
    users = [
        u
        for u in load_subscribers(a.c.recipients)
        if u.active and u.portfolio_id == a.c.portfolio and u.start_month <= month
    ]
    if not users:
        return result(
            "BLOCKED", "No active enrolled recipients for the selected portfolio/month"
        )
    database = a.c.monthly_delivery_root / "deliveries.sqlite3"
    if not database.is_file():
        return result("BLOCKED", "No existing monthly delivery evidence ledger")
    if database.is_symlink():
        raise ValueError("Delivery evidence cannot be a symlink")
    import sqlite3

    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Invalid delivery evidence database")
        for user in users:
            row = db.execute(
                "SELECT * FROM deliveries WHERE portfolio_id=? AND month=? AND user_id=?",
                (a.c.portfolio, month, user.user_id),
            ).fetchone()
            if row is None or row["status"] != "SENT":
                return result(
                    "BLOCKED",
                    "At least one enrolled recipient lacks unambiguous SMTP acceptance",
                )
            if row["recipient"].casefold() != user.email.casefold():
                raise ValueError("Delivery recipient differs from current enrollment")
            from paper_release import safe_file

            root = a.c.monthly_delivery_root
            relative = f"{a.c.portfolio}/{month}/{user.user_id}/{row['report_id']}"
            manifest = strict_json(safe_file(root, relative + "/manifest.json"))
            saved = strict_json(safe_file(root, relative + "/summary.json"))
            if (
                manifest["report_id"] != row["report_id"]
                or manifest["pdf_sha256"] != row["pdf_sha256"]
                or file_hash(safe_file(root, relative + "/report.pdf"))
                != row["pdf_sha256"]
                or file_hash(safe_file(root, relative + "/summary.json"))
                != manifest["summary_sha256"]
                or saved["source_fingerprint"]
                != a.monthly_summary["source_fingerprint"]
            ):
                raise ValueError(
                    "Delivered report differs from current verified period evidence"
                )
    return result(
        reason="Existing attachment/recipient evidence and SMTP acceptance verified; inbox receipt is not inferred",
        recipients=len(users),
        email_sent_by_acceptance=False,
    )


def check_recovery(a):
    from shadow_bundle_backup import create_backup, restore_backup
    from strategy_monthly_report import read_events

    original = cohort_database(a.c.operations)
    backup = create_backup(original, a.c.bundle, a.run / "backup")
    restored = restore_backup(a.run / "backup", a.run / "restored")
    if backup["chain_head"] != restored["chain_head"] or read_events(
        original
    ) != read_events(a.run / "restored/ledger.sqlite3"):
        raise ValueError("Restored ledger does not reconcile")
    return result(
        reason="Actual ledger/input backup and isolated restore verified",
        events=backup["events"],
        chain_head=backup["chain_head"],
        scope="LOCAL_ONLY_NOT_REMOTE_HOST_QUALIFICATION",
    )


def check_financial(a):
    from economic_evidence import verify
    import pandas as pd

    dates = pd.read_csv(
        Path(a.bundle["training_report"]).parent / "economic_balance.csv",
        index_col=0,
        parse_dates=True,
    ).index
    proof = verify(
        a.c.financial_evidence, [s for s in a.prices if s != "ALLW"], dates, now=a.now
    )
    atomic_json(a.run / "financial-evidence.json", proof)
    return result(
        "PASS" if all(proof["checks"].values()) else "BLOCKED",
        "Reviewed cash, costs, holdings/FX/duration and access evidence required",
        checks=proof["checks"],
        reasons=proof["reasons"],
    )


def check_host(a):
    if a.c.qualification_release is None:
        return result(
            "BLOCKED",
            "No qualified immutable release/host evidence supplied",
            docker_locally_available=bool(shutil.which("docker")),
        )
    from paper_release import verify
    from paper_qualification import evidence_checks

    root = a.c.qualification_release
    m = strict_json(root / "release-manifest.json")
    verify(root, m)
    if not m["clean_commit"]:
        return result(
            "BLOCKED", "A diagnostic dirty release is not a qualified release"
        )
    required = set(a.training["source_hashes"]) | {
        "release_acceptance.py",
        "portfolio_contract.py",
        "strategy_dashboard_server.py",
        "refresh_strategy_dashboard.py",
        "institutional_return_engines.py",
        "evaluate_institutional_engines.py",
        "return_engine_shadow.py",
        "run_return_engine_cycle.py",
        "dashboard/investor.js",
        "dashboard/investor.html",
        "dashboard/investor.css",
    }
    unmatched = [
        p for p in sorted(required) if m["files"].get(p) != file_hash(ROOT / p)
    ]
    if unmatched:
        return result(
            "BLOCKED",
            "Qualification release does not contain current required source versions",
            unmatched=unmatched,
        )
    proof = evidence_checks(a.c.qualification_evidence, m, now=a.now)
    required_checks = [
        "ci",
        "security",
        "host",
        "data_smoke",
        "alert_delivery",
        "restore_replay",
        "failure_drills",
        "ownership",
        "paper_signoff",
        "strategy_acceptance",
    ]
    return result(
        "PASS" if all(proof[k] == "PASS" for k in required_checks) else "BLOCKED",
        "Release-bound existing qualification receipts checked; human attestations are not automatic proof",
        release_id=m["release_id"],
        checks=proof,
    )


def check_product(a):
    if a.c.product_mandate is None:
        return result(
            "BLOCKED",
            "Jurisdiction/product-scope and pilot-mandate review have not been supplied",
        )
    from clientmandate import ClientMandate
    from productrelease import readiness, release_manifest

    mandate = ClientMandate(**strict_json(a.c.product_mandate))
    proof = readiness(
        release_manifest(),
        mandate,
        [s for s in a.prices if s != "ALLW"],
        now=a.now,
        root=a.c.product_evidence,
    )
    atomic_json(a.run / "product-readiness.json", proof)
    return result(
        "PASS" if proof.get("public_recommendations_enabled") is True else "BLOCKED",
        "Existing product review gates checked; this command never approves release",
        checks=proof.get("checks", {}),
    )


BROWSER_CHECKS = {
    "desktop_overview",
    "macro_scenario_interaction",
    "risk_charts",
    "allocation_search",
    "news_failure_state",
    "pdf_download",
    "mobile_layout",
}


def check_browser(a):
    if a.c.browser_evidence is None:
        return result(
            "BLOCKED",
            "No release-bound browser interaction/rendering qualification supplied; syntax is a separate check",
        )
    from paper_release import safe_file

    doc = strict_json(a.c.browser_evidence)
    stamp = datetime.fromisoformat(doc["reviewed_at"])
    expiry = datetime.fromisoformat(doc["expires_at"])
    if (
        doc.get("schema_version") != 1
        or doc.get("status") != "PASS"
        or not isinstance(doc.get("reviewer"), str)
        or not doc["reviewer"].strip()
        or stamp.tzinfo is None
        or expiry.tzinfo is None
        or not stamp <= a.now <= expiry
        or (expiry - stamp).total_seconds() > 31 * 86400
        or doc.get("source_snapshot_id") != fingerprint(source_snapshot())
        or doc.get("bundle_sha256") != file_hash(a.c.bundle)
        or doc.get("dashboard_sha256") != file_hash(a.c.dashboard)
        or set(doc.get("checks", {})) != BROWSER_CHECKS
        or any(v is not True for v in doc["checks"].values())
        or not doc.get("artifacts")
    ):
        raise ValueError(
            "Browser evidence is incomplete, stale or bound to another release"
        )
    for item in doc["artifacts"]:
        if (
            file_hash(safe_file(a.c.browser_evidence.parent, item["path"]))
            != item["sha256"]
        ):
            raise ValueError("Browser artifact changed")
    return result(
        reason="Named source/input-bound browser review and artifacts verified; this does not run a browser",
        reviewer=doc["reviewer"],
        checks=doc["checks"],
    )


def summarize(rows):
    if not rows or any(row.get("status") not in VALID for row in rows):
        raise ValueError("Complete typed acceptance results required")
    fail = [r["id"] for r in rows if r["status"] == "FAIL"]
    blocked = [r["id"] for r in rows if r["status"] == "BLOCKED"]
    local = [r for r in rows if r["category"] == "engineering"]
    engineering = (
        "PASS"
        if local and all(r["status"] == "PASS" for r in local)
        else "FAIL"
        if any(r["status"] == "FAIL" for r in local)
        else "BLOCKED"
    )
    return {
        "status": "FAILED_CHECKS"
        if fail
        else "BLOCKED_PREREQUISITES"
        if blocked
        else "READY_FOR_OPERATOR_REVIEW",
        "engineering_status": engineering,
        "failed_checks": fail,
        "blocked_checks": blocked,
        "exit_code": 1 if fail else 2 if blocked else 0,
        "release_approved": False,
        "execution_enabled": False,
        "email_sent": False,
    }


def write_reports(a, initial, protected):
    summary = summarize(a.rows)
    report = {
        "schema_version": 1,
        "run_id": a.run.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **summary,
        "snapshot_id": fingerprint({"sources": initial, "inputs": protected}),
        "source_hashes": initial,
        "input_hashes": protected,
        "checks": a.rows,
        "blocking_actions": [
            {
                "check": r["id"],
                "priority": r.get("priority"),
                "next_action": r.get("next_action"),
            }
            for r in a.rows
            if r["status"] != "PASS"
        ],
        "scope": "Private recommendation/simulation release audit. No deployment, model change, ledger observation, recipient enrollment or message delivery.",
    }
    atomic_json(a.run / "acceptance.json", report)
    lines = [
        "# Release acceptance",
        "",
        f"Status: **{report['status']}**. Local engineering: **{report['engineering_status']}**.",
        "",
        "This report does not approve release, place orders, or send email.",
        "",
        "| Check | Category | Status | Finding |",
        "|---|---|---|---|",
    ]
    for r in a.rows:
        lines.append(
            f"| {r['id']} | {r['category']} | {r['status']} | {r['reason'].replace('|', '/').replace(chr(10), ' ')} |"
        )
    lines += ["", "## Remaining work", ""]
    for r in a.rows:
        if r["status"] != "PASS":
            lines.append(
                f"- **{r.get('priority', 'P1')} / {r['status']} — {r['id']}**: {r['reason']} Next: {r.get('next_action', 'Investigate the check.')}"
            )
    lines += [
        "",
        "Full stage details, evidence hashes and artifact paths are in [acceptance.json](acceptance.json).",
        "The monthly preview may correctly report NO_DATA/PARTIAL. Generating a document is an engineering check; it does not establish financial coverage or delivery.",
    ]
    p = a.run / "acceptance.md"
    p.write_text("\n".join(lines) + "\n")
    p.chmod(0o600)
    atomic_json(
        a.c.output / "latest.json",
        {
            "run": str(a.run.resolve()),
            "report": str((a.run / "acceptance.json").resolve()),
            "report_sha256": file_hash(a.run / "acceptance.json"),
            "status": report["status"],
        },
    )
    return report


def run_acceptance(c, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Aware acceptance clock required")
    c.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    with ExitStack() as stack:
        lock = stack.enter_context((c.output / "acceptance.lock").open("a"))
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for path in [
            c.operations / "job.lock",
            c.challenger_index.parent / "cycle.lock",
        ]:
            if path.is_file():
                handle = stack.enter_context(path.open("r"))
                fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        run = (
            c.output
            / "runs"
            / (now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8])
        )
        run.mkdir(parents=True, mode=0o700)
        a = Audit(c, run.resolve(), now)
        initial = source_snapshot()
        protected = {}
        a.stage("input_capture", lambda: check_inputs(a))
        try:
            protected = tracked_inputs(c)
        except Exception as exc:
            failure_type = type(exc).__name__
            a.stage(
                "input_inventory",
                lambda: result(
                    "FAIL", f"Cannot bind full input inventory: {failure_type}"
                ),
            )
        a.stage(
            "dashboard_scenarios_pdf",
            lambda: check_dashboard(a),
            requires=["input_capture"],
        )
        a.stage(
            "authenticated_api_payload",
            lambda: check_api(a),
            requires=["dashboard_scenarios_pdf"],
        )
        a.stage(
            "benchmark_recalculation",
            lambda: check_benchmark(a),
            requires=["dashboard_scenarios_pdf"],
        )
        a.stage(
            "challenger_replay",
            lambda: check_challengers(a),
            requires=["dashboard_scenarios_pdf"],
        )
        a.stage(
            "core_ledger",
            lambda: inspect_ledger(
                cohort_database(c.operations),
                a.training["market_session"],
                now,
                report_sha256=file_hash(a.bundle["training_report"]),
                contract_map=strict_json(a.bundle["portfolio_contracts"]),
            ),
            requires=["input_capture"],
        )
        a.stage(
            "challenger_ledger",
            lambda: inspect_ledger(
                c.challenger_database,
                a.training["market_session"],
                now,
                assessment_sha256=file_hash(
                    strict_json(c.challenger_index)["assessment"]
                ),
            ),
            requires=["input_capture"],
        )
        from strategy_healthcheck import health

        a.stage(
            "daily_job_monitoring",
            lambda: result(
                "PASS"
                if health(c.operations, now)["status"] == "HEALTHY_SHADOW_JOB"
                else "BLOCKED",
                "Existing daily-job receipt and deadline chain",
                monitor=health(c.operations, now),
            ),
            category="operations",
        )
        a.stage(
            "monthly_pdf_email_preview",
            lambda: check_monthly(a),
            requires=["core_ledger"],
        )
        a.stage(
            "backup_restore",
            lambda: check_recovery(a),
            requires=["core_ledger", "input_capture"],
        )
        a.stage(
            "financial_evidence",
            lambda: check_financial(a),
            category="release",
            requires=["input_capture"],
        )
        a.stage(
            "completed_month_coverage",
            lambda: result(
                "PASS" if a.monthly_summary["coverage"] == "COMPLETE" else "BLOCKED",
                "A complete post-registration month is required for a financial monthly report",
                coverage=a.monthly_summary["coverage"],
            ),
            category="observation",
            requires=["monthly_pdf_email_preview"],
        )
        core = a.values.get("core_ledger", {}).get("details", {})
        challenger = a.values.get("challenger_ledger", {}).get("details", {})
        a.stage(
            "monthly_delivery_evidence",
            lambda: check_monthly_delivery(a),
            category="release",
            requires=["monthly_pdf_email_preview"],
        )
        a.stage(
            "prospective_observation",
            lambda: result(
                "PASS"
                if core.get("observations", 0) >= 20
                and challenger.get("observations", 0) >= 20
                and core.get("return_sessions", 0) >= 20
                and challenger.get("return_sessions", 0) >= 20
                else "BLOCKED",
                "At least 20 actual observations and 20 forward-return sessions per cohort; not proof of investment performance",
                core=core,
                challengers=challenger,
            ),
            category="observation",
            requires=["core_ledger", "challenger_ledger"],
        )
        a.stage(
            "host_image_alert_recovery_reviews",
            lambda: check_host(a),
            category="release",
            requires=["input_capture"],
        )
        a.stage(
            "product_and_jurisdiction_reviews",
            lambda: check_product(a),
            category="release",
            requires=["input_capture"],
        )
        a.stage(
            "browser_visual_qualification",
            lambda: check_browser(a),
            category="release",
        )
        a.stage(
            "pinned_runtime_environment", lambda: check_runtime(a), category="release"
        )
        a.stage("python_style", lambda: check_style(a))
        a.stage("javascript_syntax", lambda: check_js(a))
        a.stage("regression", lambda: check_regression(a))

        def unchanged():
            if source_snapshot() != initial or tracked_inputs(c) != protected:
                raise ValueError(
                    "Bound source/input changed during acceptance; retry after the writer finishes"
                )
            return result(
                reason="All bound source files, inputs, dashboards, PDFs and original ledgers stayed unchanged"
            )

        a.stage("source_and_input_stability", unchanged)
        return write_reports(a, initial, protected)


def main(argv=None):
    os.chdir(ROOT)
    p = argparse.ArgumentParser(description=__doc__)
    for name in [
        "bundle",
        "dashboard",
        "operations",
        "challenger-index",
        "challenger-database",
        "output",
        "portfolio",
        "financial-evidence",
        "qualification-release",
        "qualification-evidence",
        "product-mandate",
        "product-evidence",
        "browser-evidence",
        "recipients",
        "monthly-delivery-root",
    ]:
        key = name.replace("-", "_")
        default = getattr(Config(), key)
        p.add_argument(
            "--" + name, type=str if name == "portfolio" else Path, default=default
        )
    p.add_argument(
        "--skip-tests",
        action="store_true",
        help="Quick diagnostics only; regression remains BLOCKED",
    )
    args = p.parse_args(argv)
    values = vars(args)
    skip = values.pop("skip_tests")
    try:
        report = run_acceptance(Config(**values, run_tests=not skip))
    except BlockingIOError:
        print(
            json.dumps(
                {
                    "status": "BUSY",
                    "reason": "Acceptance or a daily job is active; no existing report/observation was replaced",
                    "release_approved": False,
                }
            )
        )
        return 3
    except Exception as exc:
        from secretredaction import redact_sensitive_message

        print(
            json.dumps(
                {
                    "status": "INITIALIZATION_FAILED",
                    "reason": redact_sensitive_message(f"{type(exc).__name__}: {exc}"),
                    "release_approved": False,
                }
            )
        )
        return 1
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "status",
                    "engineering_status",
                    "failed_checks",
                    "blocked_checks",
                    "exit_code",
                ]
            },
            indent=2,
        )
    )
    print("Report:", str((Config(**values).output / "latest.json").resolve()))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
