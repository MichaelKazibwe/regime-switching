import itertools
import json

import numpy as np
import pandas as pd
import pytest

from diversifiedregimepolicy import AllocationError
from institutionalportfolio import (
    ForecastCalibration,
    InstitutionalPortfolio,
    calibrated_covariance,
    conditional_core_weights,
    coverage_report,
)
from refine_institutional_portfolio import run, select
from smartregimeportfolio import REGIMES


def fixture():
    policy = InstitutionalPortfolio()
    symbols = [s for group in policy.config["sleeves"].values() for s in group] + [
        "SHY",
        "SGOV",
    ]
    rng = np.random.default_rng(72)
    values = rng.normal(size=(260, len(symbols))) * np.array(
        [0.012, 0.013, 0.015, 0.012, 0.005, 0.007, 0.004, 0.012, 0.018, 0.001, 0.0002]
    )
    returns = pd.DataFrame(
        values, index=pd.bdate_range("2020-01-01", periods=260), columns=symbols
    )
    signal = {
        "as_of": (
            returns.index[251].tz_localize("UTC") + pd.Timedelta(hours=21)
        ).isoformat(),
        "probabilities": {r: 0.25 for r in REGIMES},
        "stress": False,
        "regime": REGIMES[0],
        "trend_weak": True,
    }
    return policy, returns, signal


def test_conditional_solver_includes_reserve_cross_risk():
    c = np.array([[0.04, 0.005], [0.005, 0.01]])
    cross = np.array([-0.001, 0.002])
    b = np.array([0.6, 0.4])
    w = conditional_core_weights(c, cross, 0.25, b, 0.5)
    contributions = w * (c @ w + 0.25 * cross)
    assert w.sum() == pytest.approx(0.5)
    assert np.allclose(contributions / contributions.sum(), b, atol=1e-8)
    pure = w * (c @ w)
    assert not np.allclose(pure / pure.sum(), b, atol=1e-4)


@pytest.mark.parametrize("stress", [True, False])
@pytest.mark.parametrize("anchor", ["balanced", "growth_balanced"])
@pytest.mark.parametrize("reserve", ["SHY", "SGOV", None])
def test_allocation_contract_is_exact_and_reserve_is_invested(stress, anchor, reserve):
    policy, history, signal = fixture()
    history = history.iloc[:252]
    signal = {**signal, "stress": stress}
    c, _ = calibrated_covariance(history)
    params = {"anchor": anchor, "volatility_ceiling": 0.06, "macro_view_weight": 0.25}
    a = policy.allocate(
        history,
        c,
        signal,
        params,
        reserve_symbol=reserve,
        account_drawdown=0,
        calibration_multiplier=1.2,
        decision_time=signal["as_of"],
    )
    w = np.array([a["weights"][s] for s in history])
    rc = w * (c @ w) / (w @ c @ w)
    assert a["risk_budget_error"] <= 1e-6
    assert max(rc) <= 0.25 + 1e-6
    assert w.max() <= 0.25 + 1e-10
    assert w.sum() + a["cash"] == pytest.approx(1)
    assert a["calibrated_estimated_volatility"] <= a["volatility_ceiling"] + 1e-10
    assert sum(a["full_account_risk_shares"].values()) == pytest.approx(1)
    if reserve:
        assert a["reserve_weight"] == pytest.approx(a["weights"][reserve])
        assert a["full_account_risk_shares"][reserve] == pytest.approx(
            rc[list(history).index(reserve)]
        )
    if stress:
        assert a["cash"] >= 0.6 - 1e-10


def test_covariance_retains_liquidity_volatility_and_uses_only_supplied_stress():
    _, history, _ = fixture()
    c, used = calibrated_covariance(history.iloc[:252])
    assert not used
    assert np.sqrt(c[-1, -1]) < 0.01
    stressed = history.iloc[:45] * 2
    stress_cov, used = calibrated_covariance(history.iloc[:252], stressed)
    assert used and np.linalg.eigvalsh(stress_cov).min() > 0
    with pytest.raises(AllocationError):
        calibrated_covariance(history.iloc[:251])


def test_calibration_is_reduce_only_and_requires_realized_outcomes():
    c = ForecastCalibration(warmup=3, half_life=1)
    assert c.multiplier == 1
    c.observe(0.03, 0.0001)
    c.observe(0.03, 0.0001)
    assert c.multiplier == 1
    c.observe(0.03, 0.0001)
    assert c.multiplier == 2
    for _ in range(30):
        c.observe(0, 0.0001)
    assert c.multiplier == 1
    with pytest.raises(AllocationError):
        c.observe(np.nan, 0.0001)


def test_future_signal_and_malformed_covariance_fail_closed():
    policy, history, signal = fixture()
    c, _ = calibrated_covariance(history.iloc[:252])
    params = policy.config["proxy_parameters"]
    kwargs = dict(
        reserve_symbol="SHY",
        account_drawdown=0,
        calibration_multiplier=1,
        decision_time=signal["as_of"],
    )
    with pytest.raises(AllocationError, match="Future"):
        policy.allocate(
            history.iloc[:252],
            c,
            {**signal, "as_of": "2030-01-01T21:00:00Z"},
            params,
            **kwargs,
        )
    c[0, 1] += 0.01
    with pytest.raises(AllocationError, match="covariance"):
        policy.allocate(history.iloc[:252], c, signal, params, **kwargs)


def test_simulator_scores_prior_holdings_before_next_close_fill_and_is_prefix_invariant():
    policy, history, signal = fixture()
    prices = (1 + history).cumprod()
    # Prepend a price observation so all 252 returns are available at first decision.
    prices = pd.concat(
        [
            pd.DataFrame(
                [np.ones(len(prices.columns))],
                columns=prices.columns,
                index=[prices.index[0] - pd.Timedelta(days=1)],
            ),
            prices,
        ]
    )
    daily = prices.pct_change(fill_method=None)
    states = {}
    for i in range(252, len(prices) - 1):
        h = daily.iloc[i - 251 : i + 1]
        c, _ = calibrated_covariance(h)
        stamp = (
            prices.index[i].tz_localize("UTC") + pd.Timedelta(hours=21)
        ).isoformat()
        states[prices.index[i]] = {
            "symbols": list(h.columns),
            "covariance": c,
            "signal": {**signal, "as_of": stamp},
            "reserve": "SHY",
        }

    def schedule(date):
        return policy.config["proxy_parameters"]

    full, trades = run(prices, daily, states, policy, schedule)
    assert full.iloc[0].gross_return == pytest.approx(0)
    assert full.iloc[0].raw_daily_sigma == pytest.approx(0)
    assert full.iloc[0]["return"] < 0  # initial purchase cost only
    assert (
        pd.Timestamp(trades[0]["decision_time"]).date()
        < pd.Timestamp(trades[0]["execution_date"]).date()
    )
    shortened = prices.iloc[:-2]
    prefix, _ = run(
        shortened,
        daily.loc[shortened.index],
        {d: v for d, v in states.items() if d < shortened.index[-1]},
        policy,
        schedule,
    )
    pd.testing.assert_frame_equal(prefix, full.loc[prefix.index])


def test_selection_does_not_use_future_returns_and_falls_back_if_no_risk_feasible_candidate():
    policy = InstitutionalPortfolio()
    dates = pd.bdate_range("2010-01-01", periods=1010)
    frame = pd.DataFrame(
        {
            "return": np.tile([0.02, -0.019], 505),
            "cash": 0.1,
            "turnover": 0.0,
            "cost_as_initial_capital": 0.0,
        },
        index=dates,
    )
    frame["equity"] = (1 + frame["return"]).cumprod()
    params = policy.config["proxy_parameters"]
    a, trials = select({0: frame}, [params], policy)
    assert a[0]["fallback"]
    assert pd.Timestamp(a[0]["training_end"]) < pd.Timestamp(a[0]["evaluation_start"])
    changed = frame.copy()
    changed.loc[dates[756] :, "return"] = 0.1
    changed["equity"] = (1 + changed["return"]).cumprod()
    b, _ = select({0: changed}, [params], policy)
    assert a[0] == b[0]
    assert len(trials) == 2


def test_risk_coverage_detects_a_misspecified_forecast():
    r = np.random.default_rng(77).normal(0, 0.02, 2000)
    report = coverage_report(r, np.full(2000, 0.005))
    assert report["kupiec_unconditional_coverage_pvalue"] < 0.001
    assert report["realized_to_forecast_volatility_ratio"] > 3


def test_plan_cannot_relax_strict_risk_contract(tmp_path):
    p = InstitutionalPortfolio()
    for key, value in [
        ("risk_budget_tolerance", 1e-3),
        ("maximum_full_account_risk_share", 0.5),
        ("production_activation", True),
    ]:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({**p.config, key: value}))
        with pytest.raises(AllocationError):
            InstitutionalPortfolio(path)


def test_search_is_bounded_to_eight_variants():
    p = InstitutionalPortfolio()
    assert len(list(itertools.product(*p.config["candidate_grid"].values()))) == 8
