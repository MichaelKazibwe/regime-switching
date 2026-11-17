"""Fail-closed monitoring of v2 run-start, completion and linked observations."""

from forward_cohort import observations as cohort_observations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from strategy_integrity import strict_json, file_hash
from strategy_receipts import read_observation
from strategy_training_data import usable_session


def health(root, now=None):
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    session = str(usable_session(now).date())
    import pandas as pd

    # Daily timer: 22:30 UTC, bounded two-hour refresh plus 15-minute grace.
    deadline = datetime.fromisoformat(session + "T22:30:00+00:00") + pd.Timedelta(
        hours=2, minutes=15
    )
    reason = "missing_or_invalid_receipt"
    okay = False
    try:
        job = strict_json(root / "latest-job.json")
        if not isinstance(job, dict) or job.get("schema_version") != 2:
            reason = "invalid_job_schema"
            raise ValueError("Invalid job schema")
        started = datetime.fromisoformat(job["started_at"])
        if started.tzinfo is None or started > now:
            raise ValueError("Invalid job clock")
        if job["status"] == "RUNNING":
            reason = (
                "run_overdue"
                if (now - started).total_seconds() > 7500
                else "run_in_progress"
            )
        elif job["status"] == "PASSED_SHADOW_ONLY":
            finished = datetime.fromisoformat(job["finished_at"])
            receipt = read_observation(cohort_observations(root) / (session + ".json"), now)
            evidence = receipt["evidence"]
            job_path = Path(job["job"]).resolve()
            if job_path.parent != (root / "runs").resolve():
                raise ValueError("Invalid job path")
            okay = (
                finished.tzinfo is not None
                and started <= finished <= now
                and job["market_session"] == session
                and all(
                    job[k] == evidence[k]
                    for k in ["report_sha256", "artifact_manifest_sha256"]
                )
                and strict_json(job_path / "status.json")
                == {k: v for k, v in job.items() if k != "job"}
                and file_hash(evidence["bundle"]) == evidence["bundle_sha256"]
                and file_hash(evidence["training_report_path"])
                == evidence["report_sha256"]
                and file_hash(evidence["artifact_manifest_path"])
                == evidence["artifact_manifest_sha256"]
            )
            reason = "linked_current_session" if okay else "job_receipt_mismatch"
        else:
            reason = "job_failed"
    except FileNotFoundError:
        okay = False
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        reason = "invalid_receipt_or_job"
        okay = False
    pending = not okay and (
        (reason == "run_in_progress")
        or (reason == "missing_or_invalid_receipt" and now < deadline)
    )
    return {
        "status": "HEALTHY_SHADOW_JOB"
        if okay
        else "PENDING_SHADOW_JOB"
        if pending
        else "ALERT_REQUIRED",
        "reason": reason,
        "expected_session": session,
        "release_approved": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="var/strategy-operations-integrated-v1")
    args = parser.parse_args()
    result = health(args.root)
    print(json.dumps(result, indent=2))
    raise SystemExit(
        0 if result["status"] in {"HEALTHY_SHADOW_JOB", "PENDING_SHADOW_JOB"} else 1
    )


if __name__ == "__main__":
    main()
