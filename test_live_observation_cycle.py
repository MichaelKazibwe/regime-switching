import json

import pytest

import live_observation_cycle as jobs


def test_duplicate_sealed_session_does_not_retrain(tmp_path, monkeypatch):
    database = tmp_path / "ledger"
    database.touch()
    monkeypatch.setattr(
        jobs,
        "read_events",
        lambda _: [({"session": "2026-10-30", "return_sessions": 0}, "hash")],
    )
    result = jobs.advance_once(
        database, "2026-10-30", lambda: pytest.fail("duplicate training")
    )
    assert result["return_sessions"] == 0
    assert result["status"] == "ALREADY_SEALED_NO_RETRAINING"


def test_failure_retained_without_running_downstream(tmp_path, monkeypatch):
    def fail(*_, **__):
        raise RuntimeError("feed unavailable")

    monkeypatch.setattr(jobs, "validate", fail)
    monkeypatch.setattr(
        jobs, "engines", lambda *_, **__: pytest.fail("failed input used")
    )
    with pytest.raises(RuntimeError):
        jobs.run(tmp_path / "cycle", tmp_path / "operations")
    receipt = json.loads((tmp_path / "cycle/latest.json").read_text())
    assert receipt["status"] == "FAILED"
    assert not receipt["execution_enabled"]
    assert not receipt["promotion_enabled"]


def test_first_session_invokes_action(tmp_path):
    assert (
        jobs.advance_once(tmp_path / "absent", "2026-10-30", lambda: "advanced")
        == "advanced"
    )
