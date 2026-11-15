"""Weekly bounded candidate study after the week's final completed NYSE session."""

from datetime import datetime, timezone
from pathlib import Path
import fcntl
import json
import subprocess
import sys

import pandas as pd
import pandas_market_calendars as mcal

from strategy_training_data import usable_session
from strategy_receipts import atomic_json
from strategy_integrity import strict_json, file_hash, fingerprint
from observation_process import run_bounded, install_cancellation


def run(
    root=Path("var/p1-weekly"),
    operations=Path("var/strategy-operations-integrated-v1"),
    *,
    now=None,
):
    now = now or datetime.now(timezone.utc)
    root, operations = Path(root), Path(operations)
    session = usable_session(now)
    monday = session - pd.Timedelta(days=session.weekday())
    week = mcal.get_calendar("NYSE").schedule(monday, monday + pd.Timedelta(days=6))
    if session != week.index[-1]:
        return dict(status="WAITING_FOR_WEEKLY_CLOSE", promotion_enabled=False)
    job = strict_json(operations / "latest-job.json")
    if job.get("status") != "PASSED_SHADOW_ONLY" or job.get("market_session") != str(
        session.date()
    ):
        return dict(status="BLOCKED_DAILY_VALIDATION", promotion_enabled=False)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "research.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        files = [
            "run_p1_refinement.py",
            "resilient_candidate.py",
            "forecast_calibration.py",
            "portfolio_risk_envelope.py",
            "market_quality.py",
            "institutional_return_engines.py",
            "evaluate_institutional_engines.py",
            "portfolio_contract.py",
            "growth_resilience.py",
            "economic_design_assessment.py",
            "economic_evidence.py",
            "live_strategy_training.py",
            "research/four_macro_strategies.json",
            "compare_portfolio_models.py",
            "institutionalportfolio.py",
        ]
        sources = {p: file_hash(p) for p in files}
        key = fingerprint(dict(week=str(monday.date()), sources=sources))
        last = (
            strict_json(root / "latest.json") if (root / "latest.json").exists() else {}
        )
        if last.get("key") == key and (
            last.get("status") == "COMPLETED_REVIEW_ONLY" or last.get("attempt", 0) >= 2
        ):
            return dict(
                status="ALREADY_STUDIED_OR_RETRY_LIMIT", promotion_enabled=False
            )
        attempt = last.get("attempt", 0) + 1 if last.get("key") == key else 1
        output = root / (now.strftime("%Y%m%dT%H%M%S%fZ"))
        bundle = Path(job["job"]) / "dashboard/latest-strategy-run.json"
        status = dict(
            key=key,
            attempt=attempt,
            status="RUNNING",
            started_at=now.isoformat(),
            promotion_enabled=False,
            execution_enabled=False,
            source_hashes=sources,
            output=str(output),
        )
        atomic_json(root / "latest.json", status)
        log = root / (output.name + ".log")
        try:
            with log.open("w") as stream:
                completed = run_bounded(
                    [
                        sys.executable,
                        "run_p1_refinement.py",
                        "--bundle",
                        str(bundle),
                        "--output",
                        str(output),
                    ],
                    cwd=Path.cwd(),
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=7200,
                )
            if completed.returncode or any(
                file_hash(p) != h for p, h in sources.items()
            ):
                raise ValueError("Research worker failed or source changed")
            result = strict_json(output / "assessment.json")
            if (
                {str(Path(p).resolve()): h for p, h in result["source_hashes"].items()}
                != {str(Path(p).resolve()): h for p, h in sources.items()}
                or result["promotion_enabled"] is not False
                or result["execution_enabled"] is not False
            ):
                raise ValueError("Research source/authority mismatch")
            if result["status"] != "COMPLETED_REVIEW_ONLY" or result[
                "bundle_sha256"
            ] != file_hash(bundle):
                raise ValueError("Research input/status mismatch")
            for name, digest in result["artifacts"].items():
                if Path(name).name != name or file_hash(output / name) != digest:
                    raise ValueError("Research artifact mismatch")
            status["status"] = "COMPLETED_REVIEW_ONLY"
        except Exception as exc:
            status.update(status="FAILED", error_type=type(exc).__name__)
            raise
        finally:
            status["finished_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(root / "latest.json", status)
        return status


if __name__ == "__main__":
    install_cancellation()
    print(json.dumps(run(), indent=2))
