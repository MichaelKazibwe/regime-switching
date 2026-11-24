"""Contract-level regressions for the institutional decision-support upgrade."""

from pathlib import Path
import shutil
from datetime import datetime, timezone

import numpy as np
import pytest

from strategy_eligibility import eligible_prices, dynamic_protocol_identity
from strategy_receipts import atomic_json
from test_institutional_return_engines import market  # noqa: F401


def test_excluded_asset_absent_does_not_break_current_or_forward_membership(market):  # noqa: F811
    import pandas as pd
    panel = market.drop(columns=["XLV"], errors="ignore")
    selected = eligible_prices(panel)
    assert "XLV" not in selected and len(selected.columns) >= 8
    with_excluded = panel.assign(XLV=panel.iloc[:, 0])
    pd.testing.assert_frame_equal(selected, eligible_prices(with_excluded))


def test_real_refresh_with_optional_ticker_absent(market, tmp_path, monkeypatch):  # noqa: F811
    import dynamic_portfolio as module
    from strategy_training_data import usable_session
    now = datetime(2026, 11, 18, 22, 30, tzinfo=timezone.utc)
    session = str(usable_session(now).date())
    panel = market.drop(columns=["XLV"], errors="ignore").copy()
    # Move the complete synthetic history to actual completed sessions.
    import pandas_market_calendars as mcal
    dates = mcal.get_calendar("NYSE").schedule("2025-01-01", session).index[-len(panel):]
    panel.index = dates
    atomic_json(tmp_path/"features.json", [])
    bundle = tmp_path/"bundle.json"
    atomic_json(bundle, dict(capture="synthetic", benchmark_extension="synthetic",
                            training_report=str(tmp_path/"training.json")))
    monkeypatch.setattr(module, "load_training_report", lambda _: dict(
        current_numerical_source_match=True, market_session=session))
    monkeypatch.setattr(module, "extended_prices", lambda *_: panel)
    result = module.refresh(bundle, tmp_path/"snapshot.json", now=now)
    assert "XLV" not in result["weights"]
    assert sum(result["weights"].values()) + result["cash"] == pytest.approx(1)
    assert np.isfinite(result["forecast_volatility"])
    assert not result["execution_enabled"]


def test_protocol_is_relocatable_and_changes_with_policy_bytes(tmp_path):
    from strategy_integrity import strict_json
    roots = [tmp_path/"host", tmp_path/"other-root"]
    names = [
        "dynamic_forward.py", "dynamic_portfolio.py", "institutional_return_engines.py",
        "prospective_strategy_ledger.py", "strategy_eligibility.py",
        "research/dynamic_eligibility.json", "global_asset_registry.py",
        "research/global_asset_registry.json", "global_market_calendar.py",
    ]
    for root in roots:
        for name in names:
            destination = root/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(name), destination)
    identity = dynamic_protocol_identity(roots[0])
    assert identity == dynamic_protocol_identity(roots[1])
    policy = roots[1]/"research/dynamic_eligibility.json"
    data = strict_json(policy)
    data["exclude"]["SPY"] = "Synthetic changed admission policy"
    atomic_json(policy, data)
    assert dynamic_protocol_identity(roots[1]) != identity
