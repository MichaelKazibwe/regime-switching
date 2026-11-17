"""Read-only, allowlisted runtime diagnostics for the authenticated local viewer."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from prospective_strategy_ledger import summary
from strategy_integrity import strict_json
from strategy_training_data import usable_session
from forward_cohort import database as cohort_database


def runtime(root=Path("var"), *, now=None):
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    result = dict(
        checked_at=now.isoformat(),
        expected_session=str(usable_session(now).date()),
        execution_enabled=False,
        promotion_enabled=False,
    )
    try:
        tick = strict_json(root / "local-observation-scheduler/heartbeat.json")
        age = (now - datetime.fromisoformat(tick["checked_at"])).total_seconds()
        result["scheduler"] = dict(
            status=tick["status"],
            checked_at=tick["checked_at"],
            heartbeat_recent=0 <= age <= 7200,
        )
    except (OSError, ValueError, KeyError, TypeError):
        result["scheduler"] = dict(status="UNAVAILABLE", heartbeat_recent=False)
    try:
        result["prospective"] = summary(
            cohort_database(root / "strategy-operations-integrated-v1")
        )
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        result["prospective"] = dict(status="UNAVAILABLE")
    from strategy_monthly_report import read_events

    result["cohorts"] = {}
    for name, directory in (
        ("institutional", "return-engine-shadow-v1"),
        ("dynamic", "dynamic-forward-v1"),
    ):
        try:
            events = read_events(cohort_database(root / directory))
            last = events[-1][0]
            metrics = {}
            for key, state in last["states"].items():
                marks = [m for event, _ in events for m in event["marks"][key]]
                metrics[key] = dict(
                    total_return=state["nav"] - 1,
                    maximum_drawdown=state["maximum_drawdown"],
                    return_sessions=len(marks),
                    cost_as_initial_capital=sum(
                        m["cost_as_initial_capital"] for m in marks
                    ),
                )
            result["cohorts"][name] = dict(
                last_session=last["session"], metrics=metrics
            )
        except (OSError, ValueError, KeyError, TypeError, IndexError, sqlite3.Error):
            result["cohorts"][name] = dict(status="UNAVAILABLE")
    return result


def age_runtime(evidence, *, now=None):
    """Recompute liveness at read time without modifying frozen research evidence."""
    from copy import deepcopy
    now = now or datetime.now(timezone.utc)
    result = deepcopy(evidence)
    result['served_at'] = now.isoformat()
    scheduler = result.setdefault('scheduler', {})
    try:
        stamp = datetime.fromisoformat(scheduler['checked_at'])
        if stamp.tzinfo is None:
            raise ValueError('Aware heartbeat required')
        age = (now-stamp).total_seconds()
        scheduler['heartbeat_age_seconds'] = max(0.,age)
        scheduler['heartbeat_recent'] = 0 <= age <= 7200
    except (KeyError, TypeError, ValueError):
        scheduler['heartbeat_recent'] = False
        scheduler['heartbeat_age_seconds'] = None
    scheduler['healthy'] = scheduler['heartbeat_recent'] and scheduler.get('status') not in {
        'FAILED','RETRY_BUDGET_EXHAUSTED','UNAVAILABLE'}
    return result
