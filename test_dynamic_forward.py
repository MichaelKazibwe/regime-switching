from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest
import dynamic_forward as forward
from portfolio_contract import make_contract
from strategy_monthly_report import read_events


def test_dynamic_registration_has_no_backfilled_returns_and_is_idempotent(
    tmp_path, monkeypatch
):
    frame = pd.DataFrame(
        100.0,
        index=pd.to_datetime(["2026-10-30"]),
        columns=["SPY", "GLD", "IEF", "TIP"],
    )
    snapshot = dict(
        decision_session="2026-10-30",
        snapshot_id="test-only",
        version="TEST",
        weights={s: 0.05 for s in frame},
    )
    snapshot["contract"] = make_contract(
        forward.KEY,
        snapshot["weights"],
        "2026-10-30",
        "TEST",
        basis="TEST",
        performance="TEST",
    )
    monkeypatch.setattr(forward, "refresh", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(
        forward,
        "strict_json",
        lambda p: (
            {
                "capture": "unused",
                "benchmark_extension": "unused",
                "training_report": "unused",
            }
            if str(p) == "bundle"
            else []
        ),
    )
    monkeypatch.setattr(forward, "extended_prices", lambda *_: frame.assign(XLV=100))
    monkeypatch.setattr(
        forward,
        "context",
        lambda *_: dict(symbols=list(frame), cov=np.eye(4) * 0.0001, macro_valid=True),
    )
    database = tmp_path / "cohort.sqlite3"
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    result = forward.advance("bundle", database, now=now)
    assert result["observed_sessions"] == 1 and result["return_sessions"] == 0
    assert result["next_fill_session"] == "2026-11-02"
    assert (
        forward.advance("bundle", database, now=now)["status"] == "ALREADY_REGISTERED"
    )
    event = read_events(database)[0][0]
    assert event["states"][forward.KEY]["weights"] == {}
    snapshot["snapshot_id"] = "changed"
    with pytest.raises(ValueError, match="already sealed"):
        forward.advance("bundle", database, now=now)
    assert len(read_events(database)) == 1
