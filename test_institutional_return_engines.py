"""Return-engine timing, observed eligibility and non-promotable risk checks."""

from copy import deepcopy
import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import pytest
from institutional_return_engines import (
    context,
    proposal,
    validate_weights,
    NAMES,
    GROUPS,
)
from evaluate_institutional_engines import Replay


@pytest.fixture
def market():
    dates = mcal.get_calendar("NYSE").schedule("2018-01-01", "2020-01-01").index[:320]
    rng = np.random.default_rng(9203)
    symbols = list(GROUPS)
    values = rng.normal(0.0002, 0.006, (len(dates), len(symbols)))
    prices = pd.DataFrame(
        100 * np.cumprod(1 + values, axis=0), index=dates, columns=symbols
    )
    return prices


def test_future_macro_cannot_enter_decision_and_missing_macro_is_explicit(market):
    day = str(market.index[-1].date())
    close = mcal.get_calendar("NYSE").schedule(day, day).market_close.iloc[0]
    bad = {
        day: {
            "as_of": (close + pd.Timedelta(minutes=1)).isoformat(),
            "macro_valid": True,
            "ip_growth": 1.0,
            "unemployment_change": 0.0,
            "inflation_change": 0.1,
        }
    }
    with pytest.raises(ValueError, match="Future macro"):
        context(market, len(market) - 1, bad, decision_time=close)
    c = context(market, len(market) - 1, {})
    assert c["regime"] == "MARKET_ONLY_DEGRADED" and not c["macro_valid"]


def test_no_preinception_price_fill_or_substituted_macro(market):
    market["SGOV"] = np.nan
    market["DBMF"] = np.nan
    c = context(market, len(market) - 1, {})
    assert (
        c["reserve"] == "SHY"
        and "SGOV" not in c["symbols"]
        and "DBMF" not in c["symbols"]
    )
    r = proposal("economic_balance", c)
    assert r["cash"] >= 0.35 - 1e-7


def test_all_fixed_candidates_obey_risk_caps_without_fixed_loss_target(market):
    c = context(market, len(market) - 1, {})
    for name in NAMES:
        r = proposal(name, c)
        assert r["status"] == "UNAPPROVED_INSTITUTIONAL_METHOD_CANDIDATE"
        assert validate_weights(
            np.array([r["weights"][s] for s in c["symbols"]]), name, c
        )
        assert r["cash"] >= 0.35 - 1e-7 and max(r["weights"].values()) <= 0.2500001
        assert r["forecast_volatility"] <= 0.070001 and not r["promotion_enabled"]


def test_future_prices_do_not_change_prior_close_target(market):
    a = context(market, 280, {})
    changed = market.copy()
    changed.iloc[281:] *= 5
    b = context(changed, 280, {})
    for name in NAMES:
        assert proposal(name, a)["weights"] == proposal(name, b)["weights"]


def test_gap_cannot_trigger_an_impossible_same_close_risk_exit(market):
    symbols = ["SPY", "VEA", "VWO", "IEF", "TIP", "SHY", "TLT", "GLD", "DBC", "DBMF"]
    p = market[symbols].copy()
    p.iloc[:] = 100.0
    p.loc[p.index[281] :, "SPY"] = 500.0
    runner = Replay(p, {})
    fake = {
        "symbols": symbols,
        "cov": np.eye(10) * 0.0001,
        "macro_valid": True,
        "regime": "TEST_ONLY",
        "decision_session": None,
    }
    runner.ctx = lambda i: {
        **deepcopy(fake),
        "decision_session": str(p.index[i].date()),
    }
    runner.target = lambda i, n: {
        "weights": dict.fromkeys(symbols, 0.09),
        "status": "SYNTHETIC_TEST_TARGET",
    }
    frames, audits = runner.run(280, 282)
    for name in NAMES:
        trades = audits[name]["trades"]
        assert [t["date"] for t in trades] == [
            str(p.index[280].date()),
            str(p.index[282].date()),
        ]
        assert all(t["decision_session"] < t["date"] for t in trades)
        assert frames[name].iloc[0]["gross_return"] == 0
        assert frames[name].iloc[1]["gross_return"] == pytest.approx(0.36)
