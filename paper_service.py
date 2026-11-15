"""One-shot scheduled worker for the paper-only portfolio service.

Schedule this command from cron/systemd or a managed scheduler. The process
uses a local nonblocking lock, stores state under the configured SQLite file,
and writes one JSON operator report per cycle.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo

from paper_runtime import PaperDecisionRunner
from paperconfig import PaperRuntimeConfig
from paperdata import PaperDataProvider
from paperexecution import PaperExecutionSession
from paperstore import SQLitePaperStore
from paperalerts import notify_operator
from secretredaction import redact_sensitive_message
from paper_dashboard import write_dashboard
from tradingcalendar import TradingCalendar


def _safe_error_message(error: Exception) -> str:
    """Remove configured secrets and common credential query parameters."""
    return redact_sensitive_message(
        f"{type(error).__name__}: {error}",
        tuple(os.environ.get(key, "") for key in ("FRED_API_KEY", "PAPER_SMTP_PASSWORD")),
    )


def _write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    temporary.replace(path)


def run_once(
    config: PaperRuntimeConfig,
    cycle_id: str | None = None,
    *,
    input_provider: Callable[[], dict[str, Any]] | None = None,
) -> dict:
    """Run one scheduled paper cycle and persist an operator report."""
    config.state_database.parent.mkdir(parents=True, exist_ok=True)
    lock_path = config.state_database.with_suffix(config.state_database.suffix + ".lock")
    with lock_path.open("a+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another paper service cycle is already running.") from exc

        now = datetime.now(timezone.utc)
        cycle_id = cycle_id or now.astimezone(ZoneInfo(config.timezone)).date().isoformat()
        session = PaperExecutionSession(
            SQLitePaperStore(config.state_database),
            config.initial_cash,
            commission_rate=config.commission_rate,
            slippage_rate=config.slippage_rate,
        )
        runner = PaperDecisionRunner(
            config,
            input_provider=input_provider or PaperDataProvider(config),
            execution_handler=lambda result, inputs, cycle: session.execute(
                result,
                inputs,
                cycle,
                cash_buffer_fraction=config.cash_buffer_fraction,
                rebalance_interval_days=config.rebalance_interval_days,
            ),
        )
        report_path = config.report_directory / f"{cycle_id}.json"
        alert_path = config.alert_file
        try:
            event = runner.run_once(cycle_id)
            decision = event.payload.get("result", {})
            status = str(decision.get("status", "UNKNOWN"))
            report = {
                "cycle_id": cycle_id,
                "status": status,
                "event_id": event.event_id,
                "event_hash": event.event_hash,
                "data_as_of": event.payload.get("data_as_of"),
                "data_source": event.payload.get("data_source"),
                "input_fingerprint": event.payload.get("input_fingerprint"),
                "configuration_fingerprint": event.payload.get("configuration_fingerprint"),
                "decision_fingerprint": event.payload.get("decision_fingerprint"),
                "research_snapshot": event.payload.get("research_snapshot"),
                "configuration": event.payload.get("configuration"),
                "decision": decision,
                "dashboard_file": str(config.dashboard_file),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if status in {"REJECTED", "BLOCKED"}:
                report["notification"] = notify_operator(
                    config,
                    cycle_id=cycle_id,
                    status=status,
                    message=f"Paper decision cycle {cycle_id} ended with {status}.",
                    decision_id=decision.get("decision_id"),
                )
                alert_path.parent.mkdir(parents=True, exist_ok=True)
                with alert_path.open("a") as alert_file:
                    alert_file.write(json.dumps(report, sort_keys=True, default=str) + "\n")
            _write_report(report_path, report)
            write_dashboard(config.report_directory, config.dashboard_file)
            return report
        except Exception as exc:
            report = {
                "cycle_id": cycle_id,
                "status": "FAILED",
                "error": _safe_error_message(exc),
                "dashboard_file": str(config.dashboard_file),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                report["notification"] = notify_operator(
                    config,
                    cycle_id=cycle_id,
                    status="FAILED",
                    message=report["error"],
                )
            except Exception as notification_error:
                report["notification_error"] = (
                    f"{type(notification_error).__name__}: {notification_error}"
                )
            _write_report(report_path, report)
            try:
                write_dashboard(config.report_directory, config.dashboard_file)
            except Exception as dashboard_error:
                report["dashboard_error"] = _safe_error_message(dashboard_error)
                _write_report(report_path, report)
            alert_path.parent.mkdir(parents=True, exist_ok=True)
            with alert_path.open("a") as alert_file:
                alert_file.write(json.dumps(report, sort_keys=True) + "\n")
            print(json.dumps(report, sort_keys=True), file=sys.stderr)
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-id", help="Stable idempotency key; defaults to local date.")
    args = parser.parse_args(argv)
    config = PaperRuntimeConfig.from_env()
    today = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    if not TradingCalendar().is_trading_day(today):
        print(json.dumps({"status": "SKIPPED", "reason": "NYSE_NON_TRADING_DAY"}))
        return 0
    try:
        report = run_once(config, args.cycle_id)
    except Exception:
        return 1
    print(json.dumps(report, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
