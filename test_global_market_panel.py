import pandas as pd
import pytest

from global_asset_registry import load_registry
from global_market_panel import base_currency_panel


def bars(session, stamp, value, column="close"):
    return pd.DataFrame(dict(session=session, available_at=stamp, **{column: value}))


def test_observed_london_pence_prices_and_fx_are_causal():
    registry = load_registry()
    valuations = pd.DatetimeIndex(["2026-11-12T21:00:00Z", "2026-11-13T21:00:00Z"])
    observed = bars(["2026-11-12", "2026-11-13"], ["2026-11-12T16:30:00Z", "2026-11-13T16:30:00Z"], [3000., 3100.])
    fx = bars(["2026-11-12", "2026-11-13"], ["2026-11-12T20:00:00Z", "2026-11-13T22:00:00Z"], [1.25, 9.99], "rate")
    result = base_currency_panel(registry, {"SHEL.L": observed}, valuations, fx={"GBP": fx})
    assert list(result["SHEL.L"]) == [37.5, 38.75]  # future FX quote is excluded
    assert result.attrs["observations"]["SHEL.L"][-1]["fx_available_at"] == "2026-11-12T20:00:00+00:00"


def test_closed_local_holiday_can_reuse_a_real_mark_but_missing_open_session_cannot():
    registry = load_registry()
    observed = bars(["2026-11-02"], ["2026-11-02T06:30:00Z"], [2000.])
    fx = bars(["2026-11-02"], ["2026-11-02T20:00:00Z"], [.007], "rate")
    result = base_currency_panel(registry, {"7203.T": observed}, pd.DatetimeIndex(["2026-11-03T21:00:00Z"]), fx={"JPY": fx})
    assert result.iloc[0, 0] == 14.
    assert result.attrs["observations"]["7203.T"][0]["unchanged_closed_market_mark"]
    with pytest.raises(ValueError, match="Missing actual"):
        base_currency_panel(registry, {"7203.T": observed}, pd.DatetimeIndex(["2026-11-04T21:00:00Z"]), fx={"JPY": fx})


def test_missing_fx_and_false_early_availability_are_rejected():
    registry = load_registry()
    observed = bars(["2026-11-13"], ["2026-11-13T12:00:00Z"], [3000.])
    valuation = pd.DatetimeIndex(["2026-11-13T21:00:00Z"])
    with pytest.raises(ValueError, match="FX required"):
        base_currency_panel(registry, {"SHEL.L": observed}, valuation)
    fx = bars(["2026-11-13"], ["2026-11-13T20:00:00Z"], [1.25], "rate")
    with pytest.raises(ValueError, match="precedes"):
        base_currency_panel(registry, {"SHEL.L": observed}, valuation, fx={"GBP": fx})
