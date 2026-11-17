import numpy as np
import pandas as pd
import pytest

from cycle_benchmark import allocate, account, simulate, BUDGETS, CAPS
from institutional_return_engines import GROUPS


def test_benchmark_caps_are_verified_against_observed_covariance():
    rng = np.random.default_rng(141126)
    symbols = [s for s in GROUPS if s != "ALLW"]
    history = pd.DataFrame(rng.normal(.0001, .005, (400, len(symbols))),
                           index=pd.bdate_range("2020-01-01", periods=400), columns=symbols)
    result = allocate(history, BUDGETS["balanced"], .06)
    w = np.array([result["weights"][s] for s in symbols])
    covariance = history.tail(252).cov().to_numpy() * 252
    assert np.sqrt(w @ covariance @ w) <= .06 + 1e-7
    assert w.max() <= .25 + 1e-7 and result["cash"] >= .05 - 1e-7
    assert w.sum() + result["cash"] == pytest.approx(1)
    for group, cap in CAPS.items():
        assert sum(result["weights"][s] for s in symbols if GROUPS[s] == group) <= cap + 1e-7


def test_drawdown_overlay_does_not_clip_market_losses_or_fill_early():
    dates = pd.bdate_range("2020-01-01", periods=5)
    returns = pd.DataFrame({"SPY": [0, -.10, .20, -.70, 0]}, index=dates)
    frame, values = account(returns, {"SPY": .6}, guard=[.05, .10])
    assert frame["return"].iloc[2] > .10
    assert values["maximum_drawdown"] < -.10
    _, unchanged = account(returns, {"SPY": .6}, cost=.0015)
    _, higher = account(returns, {"SPY": .6}, cost=.003)
    assert higher["total_return"] < unchanged["total_return"]


def test_conditional_simulation_never_fills_unavailable_cycle_pools():
    blocks = [np.zeros((3, 21, 1)), np.empty((0, 21, 1)), np.empty((0, 21, 1)), np.empty((0, 21, 1))]
    transition = np.ones((4, 4)) / 4
    allowed = simulate(blocks, transition, np.array([.6]), None, [0]*4, paths=20)
    assert allowed["status"] == "SIMULATED"
    assert len(allowed["fan"][0]) == 253
    assert allowed["median_return"] == pytest.approx(-.0009/1.0009, abs=1e-9)
    assert simulate(blocks, transition, np.array([.6]), None, None, paths=20)["status"] == "UNAVAILABLE"


@pytest.mark.parametrize('weights', [{'SPY':.6,'IEF':.4}, {'MSFT':.5,'IEF':.4}, {'MSFT':-1}, {'MSFT':float('nan')}, {'MSFT':1.1}])
def test_reference_never_silently_drops_holdings_or_accepts_invalid_weights(weights):
    returns = pd.DataFrame({'MSFT':[.01,-.01,.005,.002]}, index=pd.bdate_range('2026-11-09',periods=4))
    with pytest.raises(ValueError):
        account(returns,weights)


def test_explicit_cash_reference_is_valid():
    returns = pd.DataFrame({'MSFT':[.01,-.01,.005,.002]}, index=pd.bdate_range('2026-11-09',periods=4))
    _, result = account(returns,{'USD_CASH':1.})
    assert result['total_return'] == 0
