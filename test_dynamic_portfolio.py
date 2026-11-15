from copy import deepcopy

import numpy as np
import pytest

from dynamic_portfolio import allocate, MIXES, refresh
from institutional_return_engines import context
from test_institutional_return_engines import market  # noqa: F401


@pytest.mark.parametrize("regime", list(MIXES))
def test_dynamic_blend_reconciles_without_order_authority(market, regime):  # noqa: F811
    ctx = context(market, len(market) - 1, {})
    ctx.update(
        regime=regime,
        macro_valid=regime != "MARKET_ONLY_DEGRADED",
        growth="growth" in regime,
        inflation=regime in {"stagflation", "inflationary_growth"},
    )
    result = allocate(ctx)
    assert np.isclose(sum(result["weights"].values()) + result["cash"], 1)
    assert np.isclose(sum(result["risk_shares"].values()), 1)
    assert max(result["risk_shares"].values()) <= 0.250001
    assert result["forecast_volatility"] <= 0.080001
    assert not result["execution_enabled"] and not result["promotion_enabled"]


def test_macro_and_market_changes_change_allocations(market):  # noqa: F811
    a = context(market, len(market) - 1, {})
    b = deepcopy(a)
    b.update(macro_valid=True, regime="stagflation", growth=False, inflation=True)
    assert allocate(a)["weights"] != allocate(b)["weights"]
    b["cov"] *= 9
    assert allocate(b)["forecast_volatility"] <= 0.080001


def test_component_failure_blocks_the_blend(market, monkeypatch):  # noqa: F811
    import dynamic_portfolio

    monkeypatch.setattr(
        dynamic_portfolio, "proposal", lambda *_: {"status": "BLOCKED_RISK_SOLVE"}
    )
    with pytest.raises(ValueError, match="component risk solve"):
        allocate(context(market, len(market) - 1, {}))


def test_stale_report_cannot_replace_published_snapshot(tmp_path, monkeypatch):
    import dynamic_portfolio

    bundle = tmp_path / "bundle.json"
    bundle.write_text('{"training_report":"unused"}')
    output = tmp_path / "latest.json"
    output.write_text("previous snapshot")
    monkeypatch.setattr(
        dynamic_portfolio,
        "load_training_report",
        lambda _: {
            "current_numerical_source_match": True,
            "market_session": "2000-01-03",
        },
    )
    with pytest.raises(ValueError, match="Fresh source-matched"):
        refresh(bundle, output)
    assert output.read_text() == "previous snapshot"
