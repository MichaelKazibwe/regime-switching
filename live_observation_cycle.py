"""One-shot genuine completed-session validation; no orders or model promotion."""

import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import uuid

from scheduled_strategy_validation import run as validate
from run_return_engine_cycle import cycle as engines
from dynamic_forward import advance as dynamic
from prospective_strategy_ledger import summary
from strategy_integrity import strict_json, file_hash
from strategy_receipts import atomic_json
from strategy_monthly_report import read_events
from forward_cohort import database as cohort_database


def advance_once(database, session, action):
    if Path(database).is_file():
        events = read_events(database)
        if events and events[-1][0]["session"] == session:
            return dict(
                status="ALREADY_SEALED_NO_RETRAINING",
                observed_sessions=len(events),
                return_sessions=events[-1][0]["return_sessions"],
            )
    return action()


def run(
    root="var/live-observation-cycle",
    operations="var/strategy-operations-integrated-v1",
):
    root, operations = Path(root).resolve(), Path(operations).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "cycle.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stamp = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            + "-"
            + uuid.uuid4().hex[:8]
        )
        receipt = root / "runs" / stamp / "receipt.json"
        receipt.parent.mkdir(parents=True, mode=0o700)
        report = dict(
            status="RUNNING",
            started_at=datetime.now(timezone.utc).isoformat(),
            execution_enabled=False,
            promotion_enabled=False,
        )
        atomic_json(receipt, report)
        try:
            report["stage"] = "CORE_VALIDATION"
            report["validation"] = validate(operations, refresh=True)
            job = strict_json(operations / "latest-job.json")
            if job["status"] != "PASSED_SHADOW_ONLY":
                raise ValueError("Successful linked shadow job required")
            candidate = Path(job["job"]) / "dashboard"
            bundle = candidate / "latest-strategy-run.json"
            report["stage"] = "DATA_LINEAGE"
            from market_quality import review

            b = strict_json(bundle)
            quality_path = root / "data-quality/latest.json"
            previous_capture = (
                strict_json(quality_path).get("capture")
                if quality_path.exists()
                else None
            )
            quality = review(b["capture"], previous_capture)
            atomic_json(quality_path, {"capture": b["capture"], **quality})
            report["data_quality"] = quality
            # Never mutate either the sealed observation artifacts or investor dashboard.
            report["stage"] = "INSTITUTIONAL_COHORT"
            report["engines"] = advance_once(
                cohort_database("var/return-engine-shadow-v1"),
                job["market_session"],
                lambda: engines(bundle, publish_preview=False,
                                database=cohort_database("var/return-engine-shadow-v1")),
            )
            report["stage"] = "DYNAMIC_COHORT"
            report["dynamic"] = advance_once(
                cohort_database("var/dynamic-forward-v1"),
                job["market_session"],
                lambda: dynamic(bundle, cohort_database("var/dynamic-forward-v1")),
            )
            report["diagnostics"] = summary(cohort_database(operations))
            report["bundle_sha256"] = file_hash(bundle)
            report["market_session"] = job["market_session"]
            report["parameter_review"] = dict(
                status="COLLECTING_FORWARD_EVIDENCE",
                matured_forecasts=report["diagnostics"]["forecast_outcomes"]["matured"],
                policy="Daily risk/allocation recalculation and classifier training use past data. Parameter trials require a separate version and chronological validation; forward results are not training labels until matured. No automatic promotion.",
            )
            report["status"] = "PASSED_SHADOW_ONLY"
            report["stage"] = "COMPLETE"
        except Exception as exc:
            report.update(status="FAILED", error_type=type(exc).__name__)
            raise
        finally:
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(receipt, report)
            atomic_json(root / "latest.json", {"receipt": str(receipt), **report})
        return report


if __name__ == "__main__":
    from observation_process import install_cancellation

    install_cancellation()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="var/live-observation-cycle")
    parser.add_argument("--operations", default="var/strategy-operations-integrated-v1")
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.operations), indent=2))
