from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from assetuniverse import DIVERSIFIED_ASSETS
from diversifiedregimepolicy import AllocationError
from evaluate_three_year_goal import (
    PLAN,
    cohorts,
    gap_scenarios,
    goal_success,
    reanalyze_cached,
    rolling_goal,
    simulate,
)
from goalportfolio import (
    AccountDrawdownGuard,
    FilteredHistoricalRisk,
    goal_proposal,
    research_parameters,
)
from institutionalportfolio import InstitutionalPortfolio, calibrated_covariance
from smartregimeportfolio import REGIMES


def inputs(gap=False):
    p = InstitutionalPortfolio(PLAN)
    active = [s for group in p.config["sleeves"].values() for s in group] + [
        "SHY",
        "SGOV",
    ]
    dates = pd.bdate_range("2018-01-01", periods=272)
    rng = np.random.default_rng(151)
    r = pd.DataFrame(
        rng.normal(0.0001, 0.004, (len(dates), len(active))),
        index=dates,
        columns=active,
    )
    r[["SHY", "SGOV"]] *= 0.05
    if gap:
        r.iloc[255, :] = -0.20
    prices = (1 + r).cumprod().reindex(columns=DIVERSIFIED_ASSETS)
    daily = prices.pct_change(fill_method=None)
    states = {}
    for i in range(252, len(prices) - 1):
        h = daily.iloc[i - 251 : i + 1][active]
        covariance, _ = calibrated_covariance(h)
        stamp = (dates[i].tz_localize("UTC") + pd.Timedelta(hours=22)).isoformat()
        states[dates[i]] = {
            "i": i,
            "symbols": active,
            "covariance": covariance,
            "reserve": "SGOV",
            "trends": {s: 1.0 for s in active},
            "signal": {
                "as_of": stamp,
                "stress": False,
                "regime": REGIMES[0],
                "probabilities": {r: 0.25 for r in REGIMES},
            },
        }
    return p, prices, daily, states


def test_high_water_mark_never_resets_and_lock_cannot_self_clear():
    guard = AccountDrawdownGuard(0.02, 0.04)
    assert guard.update(1.0) == (0.0, 1.0)
    assert guard.update(0.97)[1] == pytest.approx(0.5)
    assert guard.update(0.959)[1] == 0
    assert guard.locked
    assert guard.update(1.2)[1] == 0
    assert guard.peak == 1.2


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_equity_fails_closed(value):
    with pytest.raises(AllocationError):
        AccountDrawdownGuard().update(value)


def test_filtered_tail_forecasts_use_only_past_outcomes_and_do_not_resize_risk():
    a = FilteredHistoricalRisk(window=100, warmup=20)
    assert not a.forecast(0.01)["ready"]
    for r in np.linspace(-2, 2, 30):
        a.observe(r * 0.01, 0.01)
    before = a.forecast(0.01)
    assert before["ready"] and before["past_outcomes"] == 30
    assert before["es95"] >= before["var95"] >= 0
    a.observe(-0.50, 0.01)
    assert before != a.forecast(0.01)
    assert before["past_outcomes"] == 30
    assert a.forecast(0)["var95"] == 0
    with pytest.raises(AllocationError):
        a.observe(np.nan, 0.01)


@pytest.mark.parametrize("j", [0, 1, 2, 6, 7, 8])
def test_goal_proposal_preserves_strict_contract_after_scaling(j):
    p, _, daily, states = inputs()
    date = next(iter(states))
    s = states[date]
    h = daily.iloc[s["i"] - 251 : s["i"] + 1][s["symbols"]]
    original = deepcopy(p.config)
    params = research_parameters(p.config)[j]
    a = goal_proposal(
        p,
        h,
        s["covariance"],
        s["signal"],
        params,
        s["trends"],
        reserve_symbol="SGOV",
        drawdown=-0.03,
        factor=0.5,
    )
    assert p.config == original
    w = np.array([a["weights"][symbol] for symbol in h])
    rc = w * (s["covariance"] @ w) / (w @ s["covariance"] @ w)
    assert a["risk_budget_error"] <= 1e-6
    assert max(rc) <= 0.25 + 1e-6
    assert max(w) <= 0.125 + 1e-10
    assert sum(w) <= 0.475 + 1e-10
    assert a["cash"] + sum(w) == pytest.approx(1)


def test_future_decision_and_unknown_parameters_are_rejected():
    p, _, daily, states = inputs()
    s = next(iter(states.values()))
    h = daily.iloc[s["i"] - 251 : s["i"] + 1][s["symbols"]]
    params = {**research_parameters(p.config)[0], "volatility_ceiling": 1.0}
    with pytest.raises(AllocationError, match="Undeclared"):
        goal_proposal(
            p,
            h,
            s["covariance"],
            s["signal"],
            params,
            s["trends"],
            reserve_symbol="SGOV",
            drawdown=0,
            factor=1,
        )
    future = h.copy()
    future.index = future.index + pd.Timedelta(days=1000)
    with pytest.raises(AllocationError, match="historical"):
        goal_proposal(
            p,
            future,
            s["covariance"],
            s["signal"],
            research_parameters(p.config)[0],
            s["trends"],
            reserve_symbol="SGOV",
            drawdown=0,
            factor=1,
        )


def test_costs_and_forecasts_align_with_old_holdings_before_next_close_fill():
    p, prices, daily, states = inputs()
    frame, trades, _ = simulate(
        prices, daily, states, p, research_parameters(p.config)[0]
    )
    assert frame.iloc[0].gross_return == pytest.approx(0)
    assert frame.iloc[0].raw_daily_sigma == 0
    assert frame.iloc[0]["return"] < 0
    assert (
        pd.Timestamp(trades[0]["decision_time"]).date()
        < pd.Timestamp(trades[0]["date"]).date()
    )
    shortened = prices.iloc[:-2]
    partial, _, _ = simulate(
        shortened,
        daily.loc[shortened.index],
        {d: s for d, s in states.items() if d < shortened.index[-1]},
        p,
        research_parameters(p.config)[0],
    )
    pd.testing.assert_frame_equal(partial, frame.loc[partial.index])


def test_gap_can_exceed_five_percent_before_protective_cash_fill():
    p, prices, daily, states = inputs(gap=True)
    frame, _, audit = simulate(
        prices, daily, states, p, research_parameters(p.config)[0]
    )
    assert frame.account_drawdown.min() < -0.05
    assert audit["lock_date"] is not None
    assert frame.cash.iloc[-1] == pytest.approx(1)
    assert frame.cash_locked.iloc[-1]


def test_rolling_goal_uses_peak_not_initial_capital_and_exact_compounding():
    dates = pd.bdate_range("2010-01-01", periods=756)
    r = np.full(756, 1.5 ** (1 / 756) - 1)
    r[100] = 0.20
    r[101] = -0.10
    frame = pd.DataFrame({"return": r}, index=dates)
    result = rolling_goal(frame)
    assert result.iloc[0].max_drawdown == pytest.approx(-0.10)
    assert not result.iloc[0].joint_success
    assert result.iloc[0].return_3y == pytest.approx(np.prod(1 + r) - 1)


def test_calendar_cohorts_exclude_incomplete_three_year_accounts():
    index = pd.bdate_range("2010-07-01", "2015-10-01")
    prices = pd.DataFrame(index=index)
    accounts = cohorts(prices, {index[0]: {}})
    assert len(accounts) == 3
    assert all(start + pd.DateOffset(years=3) <= index[-1] for start, end in accounts)
    assert all(end <= start + pd.DateOffset(years=3) for start, end in accounts)


def test_gap_stress_does_not_claim_five_percent_loss_protection():
    rows = gap_scenarios(
        [{"weights": {"SPY": 0.25, "VEA": 0.25, "VWO": 0.20, "GLD": 0.10}}]
    )
    assert any(row["breaches_5pct"] for row in rows)
    assert max(
        row["worst_synthetic_loss"] for row in rows if row["delay_sessions"] == 3
    ) > max(row["worst_synthetic_loss"] for row in rows if row["delay_sessions"] == 1)


def test_search_is_predeclared_and_bounded():
    p = InstitutionalPortfolio(PLAN)
    variants = research_parameters(p.config)
    assert len(variants) == 12
    assert {v["macro_view_weight"] for v in variants} == {0.0, 0.1}
    assert p.config["production_activation"] is False


def test_goal_boundary_accepts_floating_roundoff_but_rejects_actual_shortfall():
    total = float(np.prod(1 + np.full(756, 1.5 ** (1 / 756) - 1)) - 1)
    assert goal_success(total, -0.05)
    assert not goal_success(0.49999, -0.05)
    assert not goal_success(0.60, -0.05001)
    assert not goal_success(float("nan"), -0.04)


def test_simulation_cache_rejects_changed_evidence(tmp_path, monkeypatch):
    import json
    import evaluate_three_year_goal as module

    artifact = tmp_path / "evidence.csv"
    artifact.write_text("changed")
    (tmp_path / "simulation-cache.json").write_text(
        json.dumps({"file_hashes": {str(artifact): "wrong-hash"}})
    )
    monkeypatch.setattr(module, "OUT", tmp_path)
    with pytest.raises(ValueError, match="changed"):
        reanalyze_cached()
