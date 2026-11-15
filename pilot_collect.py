"""Preserve imported sealed sessions; resume normal collection on new sessions."""

from datetime import datetime, timezone
from pathlib import Path
import json

from forward_cohort import database
from local_observation_scheduler import tick
from strategy_monthly_report import read_events
from strategy_training_data import usable_session
from strategy_integrity import strict_json, file_hash
from strategy_receipts import atomic_json


def collect(root=Path.cwd(), *, now=None):
    root = Path(root).resolve()
    now = now or datetime.now(timezone.utc)
    expected = str(usable_session(now).date())
    migration = root / "var/pilot-input/cohort-import.json"
    if migration.is_file():
        imported = strict_json(migration)
        core = imported["cohorts"].get("strategy-operations-integrated-v1")
        if core and core["session"] == expected:
            operations = root / "var/strategy-operations-integrated-v1"
            if not (operations / "observations" / (expected + ".json")).is_file():
                path = database(operations)
                events = read_events(path)
                if (not events or events[-1][0]["session"] != expected
                        or events[-1][1] != core["chain_head"] or file_hash(path) != core["database_sha256"]):
                    raise ValueError("Imported cohort identity mismatch; do not reseal or overwrite history")
                report = dict(status="IMPORTED_SESSION_READ_ONLY", checked_at=now.isoformat(),
                              expected_session=expected, source_chain_head=core["chain_head"],
                              source_session_already_sealed=True, new_observations=0,
                              message="Verified imported session; new host observation starts at the next eligible market session",
                              execution_enabled=False, promotion_enabled=False)
                atomic_json(root / "var/local-observation-scheduler/heartbeat.json", report)
                return report
    code = tick(root)
    report = strict_json(root / "var/local-observation-scheduler/heartbeat.json")
    if code:
        raise RuntimeError("Completed-session validation did not pass; inspect its private receipt")
    return report


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))
