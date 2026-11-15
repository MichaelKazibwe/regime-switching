from datetime import datetime, timedelta, timezone
import json

import pandas as pd
import pytest

from paper_qualification import CHECKS, evidence_checks, observation, record
from paperstore import SQLitePaperStore
from researchdatastore import ResearchDataStore
from tradingcalendar import TradingCalendar


def test_receipts_require_evidence_and_are_bound_to_release(tmp_path):
    root = tmp_path / "evidence"
    artifact = tmp_path / "host-review.txt"
    artifact.write_text("Actual host review fixture")
    release = {"release_id": "a" * 64, "source_commit": "b" * 40}
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    assert set(evidence_checks(root, release, now=now).values()) == {"BLOCKED"}
    with pytest.raises(ValueError, match="supporting artifacts"):
        record(root, release, "host", [], "Michael", "PASS")
    path = record(root, release, "host", [artifact], "Michael", "PASS")
    checks = evidence_checks(root, release, now=now)
    assert checks["host"] == "PASS"
    assert checks["ci"] == "BLOCKED"
    other = {**release, "release_id": "c" * 64}
    assert evidence_checks(root, other, now=now)["host"] == "BLOCKED"
    receipt = json.loads(path.read_text())
    (root / receipt["artifacts"][0]["path"]).write_text("tampered")
    with pytest.raises(ValueError, match="changed"):
        evidence_checks(root, release, now=now)


def test_latest_failure_revokes_a_previous_receipt(tmp_path):
    artifact = tmp_path / "review.json"
    artifact.write_text("{}")
    release = {"release_id": "a" * 64, "source_commit": "b" * 40}
    record(tmp_path / "ledger", release, "ci", [artifact], "Michael", "PASS")
    record(tmp_path / "ledger", release, "ci", [artifact], "Michael", "FAIL")
    checks = evidence_checks(tmp_path / "ledger", release, now=datetime.now(timezone.utc))
    assert set(checks) == set(CHECKS)
    assert checks["ci"] == "FAIL"


@pytest.fixture
def sessions(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    database = tmp_path / "state.sqlite3"
    store = SQLitePaperStore(database)
    snapshots = tmp_path / "snapshots"
    research = ResearchDataStore(snapshots)
    calendar = TradingCalendar()
    days = [day for day in pd.date_range("2026-01-02", "2026-05-01") if calendar.is_trading_day(day)][:60]
    now = None
    for index, day in enumerate(days):
        close = pd.Timestamp(calendar.session(day)["market_close"]).isoformat()
        result = {"paper_execution": {
            "status": "EXECUTED" if index in {0, 21, 42} else "NOT_DUE",
            "orders": [{"reconciliation": {"approved": True}}] if index in {0, 21, 42} else [],
        }}
        artifact = research.write_snapshot(
            {"session": index}, input_fingerprint=research.fingerprint({"session": index}),
            configuration={"frozen": True}, provenance={"code_revision": "b" * 40,
                "source_tree_sha256": "a" * 64, "dependency_mismatches": {}, "python_version": "3.12.16"},
        )
        payload = {"cycle_id": str(day.date()), "result": result, "data_source": "YAHOO_FINANCE+FRED", "data_as_of": close,
                   "research_snapshot": artifact, "configuration_fingerprint": artifact["configuration_fingerprint"]}
        now = pd.Timestamp(close).to_pydatetime() + timedelta(hours=1)
        event = store.append_event(f"paper-cycle:{day.date()}", "PAPER_DECISION_CYCLE", payload, occurred_at=now.isoformat())
        report = {"cycle_id": str(day.date()), "status": "APPROVED", "event_id": event.event_id,
                  "event_hash": event.event_hash, "decision": result, "data_source": payload["data_source"],
                  "data_as_of": close, "updated_at": now.isoformat()}
        (reports / f"{day.date()}.json").write_text(json.dumps(report))
    kwargs = {"now": now, "source_commit": "b" * 40, "source_tree_sha256": "a" * 64, "snapshots": snapshots}
    return reports, database, kwargs


def test_observation_requires_60_contiguous_current_sessions_and_three_rebalances(sessions):
    reports, database, kwargs = sessions
    result = observation(reports, database, **kwargs)
    assert result["status"] == "PASS"
    assert result["sessions"] == 60
    assert result["completed_rebalances"] == 3
    victim = sorted(reports.glob("*.json"))[10]
    victim.unlink()
    result = observation(reports, database, **kwargs)
    assert result["status"] == "BLOCKED"
    assert result["missing_sessions"]


def test_observation_rejects_edited_reports_and_wrong_release(sessions):
    reports, database, kwargs = sessions
    with pytest.raises(ValueError, match="runtime does not match"):
        observation(reports, database, **{**kwargs, "source_commit": "c" * 40})
    path = sorted(reports.glob("*.json"))[0]
    report = json.loads(path.read_text())
    report["decision"]["paper_execution"]["orders"][0]["reconciliation"]["approved"] = False
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="differs from stored event"):
        observation(reports, database, **kwargs)


def test_observation_rejects_synthetic_sources(sessions):
    reports, database, kwargs = sessions
    path = sorted(reports.glob("*.json"))[0]
    report = json.loads(path.read_text())
    report["data_source"] = "DETERMINISTIC_TEST_FIXTURE"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Synthetic"):
        observation(reports, database, **kwargs)
