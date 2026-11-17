import json

import numpy as np
import pandas as pd
import pytest

from diversifiedregimepolicy import AllocationError
from fourregimestrategies import (
    FEATURES,
    FourMacroStrategies,
    macro_forecasts,
    strategy_proposal,
)
from fourstrategysimulation import simulate_strategy
from evaluate_four_macro_strategies import align_benchmark_labels
from report_four_macro_strategies import conditional_scenarios
from test_goal_portfolio import inputs
from smartregimeportfolio import REGIMES


def features(count=120):
    result = []
    for i, date in enumerate(pd.bdate_range("2000-01-01", periods=count)):
        row = {name: float(np.sin(i / (7 + j))) for j, name in enumerate(FEATURES)}
        row.update(
            date=str(date.date()),
            as_of=(date.tz_localize("UTC") + pd.Timedelta(hours=21)).isoformat(),
        )
        result.append(row)
    return result


def settings():
    return {
        "horizon_sessions": 5,
        "training_sessions": 50,
        "minimum_training": 20,
        "refit_sessions": 7,
        "regularization_C": 0.1,
        "model_weight": 0.5,
        "minimum_mature_predictions": 3,
    }


def test_macro_forecaster_purges_unknown_labels_and_ignores_future_changes():
    rows = features()
    original, scores = macro_forecasts(rows, settings())
    changed = [dict(r) for r in rows]
    for row in changed[80:]:
        row["ip_growth"] = -1000
        row["inflation_change"] = 1000
    later, _ = macro_forecasts(changed, settings())
    for date in list(original)[:80]:
        assert original[date] == later[date]
    for date, prediction in original.items():
        if prediction["training_last_label_date"]:
            assert pd.Timestamp(prediction["training_last_label_date"]) < date
        assert sum(prediction["used"]) == pytest.approx(1)
        assert min(prediction["used"]) >= 0
    assert scores


def test_forecast_gate_falls_back_to_frequency_until_enough_matured_predictions():
    forecasts, _ = macro_forecasts(features(40), settings())
    for p in forecasts.values():
        if p["mature_gate_observations"] < 3:
            assert not p["enabled"]
            assert p["used"] == p["baseline"]


@pytest.mark.parametrize("name", list(FourMacroStrategies().config["strategies"]))
@pytest.mark.parametrize("regime", list(REGIMES) + ["crisis"])
def test_all_four_strategies_preserve_risk_contract_and_crisis_limits(name, regime):
    _, _, daily, states = inputs()
    p = FourMacroStrategies()
    s = next(iter(states.values()))
    target = REGIMES[0] if regime == "crisis" else regime
    signal = {
        **s["signal"],
        "regime": regime,
        "stress": regime == "crisis",
        "probabilities": {r: float(r == target) for r in REGIMES},
        "macro_forecast": {
            "as_of": s["signal"]["as_of"],
            "used": [float(r == target) for r in REGIMES],
        },
    }
    h = daily.iloc[s["i"] - 251 : s["i"] + 1][s["symbols"]]
    a = strategy_proposal(
        p,
        h,
        s["covariance"],
        signal,
        {"strategy": name, "tail_multiplier": 1.25},
        s["trends"],
        reserve_symbol="SGOV",
        drawdown=0,
        factor=1.0,
    )
    w = np.array([a["weights"][symbol] for symbol in h])
    rc = w * (s["covariance"] @ w) / (w @ s["covariance"] @ w)
    assert a["risk_budget_error"] <= 1e-6
    assert max(w) <= 0.25 + 1e-10 and max(rc) <= 0.25 + 1e-6
    assert a["cash"] + sum(w) == pytest.approx(1)
    assert a["calibrated_estimated_volatility"] <= a["volatility_ceiling"] + 1e-10
    if regime == "crisis":
        assert a["cash"] >= 0.6 - 1e-10
        assert a["requested_sleeve_risk_budgets"][0] <= 0.15 + 1e-10


def test_future_forecast_and_invalid_score_fail_closed():
    p = FourMacroStrategies()
    signal = {
        "as_of": "2020-01-01T21:00:00Z",
        "probabilities": {r: 0.25 for r in REGIMES},
        "macro_forecast": {"as_of": "2020-01-02T21:00:00Z", "used": [0.25] * 4},
    }
    with pytest.raises(AllocationError, match="Future"):
        p.mixture(signal)
    signal["macro_forecast"] = {"as_of": signal["as_of"], "used": [1, 1, 1, 1]}
    with pytest.raises(AllocationError, match="weights"):
        p.mixture(signal)


def test_expansion_risk_targets_exceed_slowdown_and_config_cannot_omit_a_quadrant(
    tmp_path,
):
    p = FourMacroStrategies()
    for spec in p.config["strategies"].values():
        assert (
            spec["risk_budgets"]["disinflationary_growth"][0]
            > spec["risk_budgets"]["deflationary_slowdown"][0]
        )
        assert (
            spec["volatility_ceilings"]["disinflationary_growth"]
            > spec["volatility_ceilings"]["deflationary_slowdown"]
        )
    del p.config["strategies"]["economic_balance"]["risk_budgets"]["stagflation"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(p.config))
    with pytest.raises(AllocationError):
        FourMacroStrategies(path)


def test_simulator_keeps_next_close_timing_prefix_invariance_and_gap_risk():
    _, prices, daily, states = inputs(gap=True)
    p = FourMacroStrategies()
    for state in states.values():
        state["signal"]["macro_forecast"] = {
            "as_of": state["signal"]["as_of"],
            "used": [0.25] * 4,
        }
    params = {"strategy": "economic_balance", "volatility_ceiling": 0.06}
    full, trades, info = simulate_strategy(prices, daily, states, p, params)
    assert full.iloc[0].gross_return == 0
    assert full.iloc[0]["return"] < 0
    assert (
        pd.Timestamp(trades[0]["decision_time"]).date()
        < pd.Timestamp(trades[0]["date"]).date()
    )
    assert full.account_drawdown.min() < -0.05
    assert info["lock_date"] is None  # Current policy has no automatic drawdown lock.
    clipped = prices.iloc[:-2]
    prefix, _, _ = simulate_strategy(
        clipped,
        daily.loc[clipped.index],
        {d: s for d, s in states.items() if d < clipped.index[-1]},
        p,
        params,
    )
    pd.testing.assert_frame_equal(prefix, full.loc[prefix.index])


def test_benchmark_label_alignment_replaces_old_metadata_without_duplicate_columns():
    index = pd.bdate_range("2020-01-01", periods=3)
    frame = pd.DataFrame(
        {"return": 0.0, "regime": "old", "macro_quadrant": "old"}, index=index
    )
    labels = pd.DataFrame({"regime": "new", "macro_quadrant": "new"}, index=index)
    result = align_benchmark_labels(frame, labels)
    assert result.columns.is_unique
    assert (result.regime == "new").all()
    assert (frame.regime == "old").all()
    with pytest.raises(ValueError, match="lack"):
        align_benchmark_labels(frame, labels.iloc[:-1])


def test_conditional_scenarios_preserve_paired_streams_and_flag_small_samples():
    dates = pd.bdate_range("2000-01-01", periods=1008)
    labels = np.repeat(list(REGIMES), 252)
    frame = pd.DataFrame(
        {
            "return": np.random.default_rng(5).normal(0.0002, 0.005, len(dates)),
            "macro_quadrant": labels,
            "regime": "crisis",
        },
        index=dates,
    )
    result = conditional_scenarios(
        {"one": frame, "identical": frame.copy()}, paths=40, seed=91
    )
    one = result.loc[result.model == "one"].drop(columns="model").reset_index(drop=True)
    two = (
        result.loc[result.model == "identical"]
        .drop(columns="model")
        .reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(one, two)
    assert set(one.starting_condition) == set(REGIMES) | {"market_crisis"}
    tiny = conditional_scenarios({"one": frame.iloc[:63]}, paths=10)
    assert (tiny.status == "INSUFFICIENT_BLOCKS").all()


def test_extreme_equity_trend_is_projected_to_feasible_asset_risk_budgets():
    _, _, daily, states = inputs()
    p = FourMacroStrategies()
    s = next(iter(states.values()))
    h = daily.iloc[s["i"] - 251 : s["i"] + 1][s["symbols"]]
    probs = {r: float(r == REGIMES[0]) for r in REGIMES}
    signal = {
        **s["signal"],
        "probabilities": probs,
        "macro_forecast": {"as_of": s["signal"]["as_of"], "used": [1.0, 0.0, 0.0, 0.0]},
    }
    trends = {symbol: float(symbol in p.config["sleeves"]["equities"]) for symbol in h}
    a = strategy_proposal(
        p,
        h,
        s["covariance"],
        signal,
        {"strategy": "defensive_growth"},
        trends,
        reserve_symbol="SGOV",
        drawdown=0,
        factor=1,
    )
    assert a["requested_sleeve_risk_budgets"][0] > 0.75
    assert max(a["core_risk_targets"].values()) <= 0.24 + 1e-10
    assert max(a["full_account_risk_shares"].values()) <= 0.25 + 1e-6
    assert a["risk_budget_error"] <= 1e-6
