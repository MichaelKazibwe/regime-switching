from datetime import datetime, timezone
import json
import numpy as np
import pytest
from return_engine_shadow import advance
from strategy_integrity import file_hash
from strategy_monthly_report import read_events
from test_integrated_portfolio import fixture_bundle  # noqa: F401


def test_new_challengers_register_only_future_fills_and_cannot_promote(
    fixture_bundle, tmp_path, monkeypatch  # noqa: F811
):  # noqa: F811
    root, capture = fixture_bundle
    b, _ = capture("2026-10-30")
    from pathlib import Path

    bundle = json.loads(b.read_text())
    report = Path(bundle["training_report"])
    r = json.loads(report.read_text())
    r["current_numerical_source_match"] = True
    report.write_text(json.dumps(r))
    import return_engine_shadow as shadow

    monkeypatch.setattr(
        shadow, "load_training_report", lambda p: json.loads(Path(p).read_text())
    )
    ctx = {
        "symbols": ["SPY", "VEA", "IEF", "GLD"],
        "cov": np.eye(4) * 0.01,
        "macro_valid": True,
        "regime": "TEST",
    }
    monkeypatch.setattr(shadow, "context", lambda *args: ctx)
    monkeypatch.setattr(
        shadow,
        "proposal",
        lambda name, c: {
            "weights": dict.fromkeys(c["symbols"], 0.2),
            "cash": 0.2,
            "status": "TEST_ONLY",
        },
    )
    a = tmp_path / "assessment.json"
    a.write_text(
        json.dumps({"source_hashes": {}, "inputs": {"bundle_sha256": file_hash(b)}})
    )
    check = tmp_path / "robustness.json"
    check.write_text(
        json.dumps({"assessment_sha256": file_hash(a), "source_artifacts": {}})
    )
    db = tmp_path / "new-candidates" / "prospective.sqlite3"
    now = datetime(2026, 10, 30, 22, tzinfo=timezone.utc)
    first = advance(b, a, check, db, now=now)
    assert (
        first["return_sessions"] == 0
        and first["next_fill_session"] == "2026-11-02"
        and not first["release_approved"]
    )
    e = read_events(db)[0][0]
    assert len(e["states"]) == 4 and all(
        n.startswith("institutional_v1_") for n in e["states"]
    )
    assert all(
        s["weights"] == {} and not s["drawdown_controls"] for s in e["states"].values()
    )
    assert advance(b, a, check, db, now=now)["status"] == "ALREADY_REGISTERED"
    before = file_hash(db)
    a.write_text("{}")
    with pytest.raises((ValueError, KeyError)):
        advance(b, a, check, db, now=now)
    assert file_hash(db) == before
