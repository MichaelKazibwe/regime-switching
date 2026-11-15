"""Bounded local scheduler tick for completed-session shadow observations."""

from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

from strategy_receipts import atomic_json
from strategy_training_data import usable_session
from strategy_integrity import fingerprint, file_hash
from observation_process import run_bounded

ROOT = Path(__file__).resolve().parent


def tick(root=ROOT):
    root = Path(root).resolve()
    state = root / "var/local-observation-scheduler"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "tick.lock").open("a") as lock:
        os.fchmod(lock.fileno(), 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        now = datetime.now(timezone.utc)
        session = str(usable_session(now).date())
        report = dict(
            checked_at=now.isoformat(),
            expected_session=session,
            execution_enabled=False,
            promotion_enabled=False,
        )
        latest = root / "var/live-observation-cycle/latest.json"
        try:
            previous = json.loads(latest.read_text()) if latest.is_file() else {}
            if (
                previous.get("status") == "PASSED_SHADOW_ONLY"
                and previous.get("market_session") == session
            ):
                from dashboard_publication import publish

                publish(
                    root / "var/strategy-operations-integrated-v1",
                    root / "var/dashboard-live",
                )
                report["status"] = "CURRENT_SESSION_ALREADY_VALIDATED"
                return 0
            identity = fingerprint(
                {
                    n: file_hash(root / n)
                    for n in (
                        "local_observation_scheduler.py",
                        "scheduled_strategy_validation.py",
                        "refresh_strategy_dashboard.py",
                        "live_observation_cycle.py",
                        "strategy_operations.py",
                        "investor_macro_feed.py",
                        "prospective_strategy_ledger.py",
                        "forward_cohort.py",
                    )
                    if (root / n).is_file()
                }
            )
            attempts_path = state / "attempts.json"
            attempts = (
                json.loads(attempts_path.read_text()) if attempts_path.exists() else {}
            )
            if attempts.get("session") != session or attempts.get("source") != identity:
                attempts = dict(session=session, source=identity, count=0)
            if attempts["count"] >= 3:
                report["status"] = "RETRY_BUDGET_EXHAUSTED"
                return 2
            attempts["count"] += 1
            atomic_json(attempts_path, attempts)
            report["attempt"] = attempts["count"]
            report["status"] = "RUNNING"
            atomic_json(state / "heartbeat.json", report)
            log_path = state / (now.strftime("%Y%m%dT%H%M%S%fZ") + ".log")
            fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as log:
                result = run_bounded(
                    [sys.executable, str(root / "live_observation_cycle.py")],
                    cwd=root,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=7500,
                )
            report.update(
                status="COMPLETED" if result.returncode == 0 else "FAILED",
                exit_code=result.returncode,
                log=str(log_path),
            )
            if result.returncode == 0:
                from dashboard_publication import publish

                publish(
                    root / "var/strategy-operations-integrated-v1",
                    root / "var/dashboard-live",
                )
            return result.returncode
        except Exception as exc:
            report.update(status="FAILED", error_type=type(exc).__name__)
            return 1
        finally:
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(state / "heartbeat.json", report)
            if report.get("status") in {"FAILED", "RETRY_BUDGET_EXHAUSTED"}:
                atomic_json(
                    state / "alerts/latest.json",
                    {
                        **report,
                        "external_delivery": False,
                        "action": "Inspect failed stage and immutable logs; do not reset observation ledgers.",
                    },
                )


if __name__ == "__main__":
    raise SystemExit(tick())
