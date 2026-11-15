"""Independent local missed-job monitor; no external message delivery."""

from datetime import datetime, timezone
import json
from pathlib import Path
from strategy_healthcheck import health
from strategy_receipts import atomic_json


def check(root=Path("var"), *, now=None):
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    core = health(root / "strategy-operations-integrated-v1", now)
    okay = False
    pending = False
    try:
        tick = json.loads(
            (root / "local-observation-scheduler/heartbeat.json").read_text()
        )
        age = (now - datetime.fromisoformat(tick["checked_at"])).total_seconds()
        cycle = json.loads((root / "live-observation-cycle/latest.json").read_text())
        okay = (
            core["status"] == "HEALTHY_SHADOW_JOB"
            and 0 <= age <= 7200
            and tick["status"] in {"COMPLETED", "CURRENT_SESSION_ALREADY_VALIDATED"}
            and cycle["status"] == "PASSED_SHADOW_ONLY"
            and cycle["market_session"] == core["expected_session"]
        )
        pending = (
            core["status"] == "PENDING_SHADOW_JOB"
            and 0 <= age <= 7200
            and tick["status"] not in {"FAILED", "RETRY_BUDGET_EXHAUSTED"}
            and (
                cycle.get("status") == "RUNNING"
                or cycle.get("market_session") != core["expected_session"]
            )
        )
    except (OSError, ValueError, KeyError, TypeError):
        pass
    result = dict(
        checked_at=now.isoformat(),
        status="HEALTHY_LOCAL_OBSERVATIONS"
        if okay
        else "PENDING_SHADOW_JOB"
        if pending
        else "ALERT_REQUIRED",
        core=core,
        external_delivery=False,
        execution_enabled=False,
    )
    atomic_json(root / "observation-watchdog/latest.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
