from copy import deepcopy
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from performance_forecasts import evaluate, losses, improvement_bound, persistence_probabilities
from performance_portfolios import Experiments, risk_diagnostics, reconciliation
from institutional_return_engines import validate_weights, GROUPS
from run_performance_improvements import cash_inputs
from strategy_receipts import atomic_json
from strategy_integrity import file_hash
from test_four_macro_strategies import features, settings


@pytest.fixture
def observed_prices():
    import pandas_market_calendars as mcal

    dates = mcal.get_calendar("NYSE").schedule("2020-01-01", "2022-01-01").index[:300]
    rng = np.random.default_rng(121126)
    r = rng.normal(0.00015, 0.005, (len(dates), len(GROUPS)))
    r[:, list(GROUPS).index("SGOV")] *= 0.03
    return pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=dates, columns=list(GROUPS))


def test_proper_scores_and_invalid_probabilities():
    good = losses([[0.7, 0.1, 0.1, 0.1]], [0])
    bad = losses([[0.1, 0.7, 0.1, 0.1]], [0])
    assert good["brier"][0] < bad["brier"][0]
    assert good["log_loss"][0] < bad["log_loss"][0]
    for p in [[[0.7, 0.1, 0.1, 0.2]], [[np.nan, 0, 0, 1]], [[-0.1, 0.1, 0, 1]]]:
        with pytest.raises(ValueError):
            losses(p, [0])


def test_forecasts_refit_only_before_origin_and_ignore_future_features():
    rows = features(240)
    for row in rows:
        row["macro_valid"] = True
    a = evaluate(rows, settings(), [160], 0.1, 0.25)
    changed = deepcopy(rows)
    for row in changed[161:]:
        row["ip_growth"] = 1000
        row["inflation_change"] = -1000
    b = evaluate(changed, settings(), [160], 0.1, 0.25)
    assert a["probabilities"] == b["probabilities"]
    assert a["bindings"][0]["last_training_label"] < rows[160]["date"]
    assert set(a["benchmarks"]) == {"frequency", "persistence", "transition"}


def test_persistence_transition_fit_ignores_future_outcomes():
    rows = features(120)
    for row in rows:
        row["macro_valid"] = True
    first = persistence_probabilities(rows, 80, 5, np.ones(4) / 4)
    for row in rows[81:]:
        row["inflation_change"] = 1000
    second = persistence_probabilities(rows, 80, 5, np.ones(4) / 4)
    assert np.allclose(first, second)
    assert np.allclose(np.sum(first, axis=1), 1)


def test_small_quarterly_samples_cannot_gain_a_confidence_bound():
    assert improvement_bound(np.ones(11), np.zeros(11)) is None
    assert improvement_bound(np.ones(20), np.zeros(20), alpha=0.05/6) == pytest.approx(1)
    assert improvement_bound(np.zeros(20), np.ones(20)) < 0


def test_missing_forecast_inputs_do_not_generate_predictions():
    rows = features(100)
    assert evaluate(rows, settings(), [80], 0.1, 0.5)["status"] == "BLOCKED_NO_OUTCOMES"


def test_incumbent_replay_matches_frozen_reference(observed_prices):
    from evaluate_institutional_engines import Replay

    reference, _ = Replay(observed_prices, {}).run(253, 270)
    engine = Experiments(observed_prices, {})
    actual, trades = engine.run("economic_balance", "incumbent", 253, 270)
    assert np.allclose(actual.equity, reference["economic_balance"].equity)
    assert all(t["decision_session"] < t["date"] for t in trades)
    assert reconciliation(observed_prices, actual, trades, 0.0015)["sessions"] == 18
    altered = actual.copy()
    altered.loc[altered.index[-1], "equity"] += 0.01
    with pytest.raises(ValueError, match="replay mismatch"):
        reconciliation(observed_prices, altered, trades, 0.0015)


@pytest.mark.parametrize("variant", ["observed_reserve", "normal_covariance", "stress_covariance", "group_risk", "combined"])
def test_candidate_never_relaxes_existing_or_research_risk_caps(observed_prices, variant):
    engine = Experiments(observed_prices, {})
    result = engine.target(270, "economic_balance", variant)
    ctx = engine.runner.ctx(270)
    w = np.array([result["weights"][s] for s in ctx["symbols"]])
    assert validate_weights(w, "economic_balance", ctx)
    assert engine.valid(w, "economic_balance", ctx, variant, engine.covariances_at(270))
    assert sum(w) + result["cash"] == pytest.approx(1)
    assert not result["promotion_enabled"] and not result["execution_enabled"]
    assert w.max() <= 0.25 + 1e-7


def test_group_risk_reports_negative_hedges_without_netting_positive_risk():
    covariance = np.array([[0.04, -0.03], [-0.03, 0.09]])
    d = risk_diagnostics([0.7, 0.1], covariance, ["SPY", "GLD"])
    assert d["signed_group_risk"]["real_assets"] < 0
    assert d["positive_group_risk"]["real_assets"] == 0
    assert d["positive_group_risk"]["equity"] > 1


def test_risk_targets_ignore_later_market_prices(observed_prices):
    first = Experiments(observed_prices, {}).target(270, "economic_balance", "group_risk")
    changed = observed_prices.copy()
    changed.iloc[271:] *= 10
    second = Experiments(changed, {}).target(270, "economic_balance", "group_risk")
    assert first["weights"] == second["weights"]


def test_account_cash_requires_complete_hash_bound_evidence(tmp_path):
    dates = pd.bdate_range("2026-01-01", periods=3)
    assert cash_inputs(None, None, dates)[1]["status"].startswith("BLOCKED")
    path, evidence = tmp_path / "cash.csv", tmp_path / "evidence.json"
    pd.DataFrame({"cash_return": [0.0001] * 3}, index=dates).to_csv(path)
    record = dict(currency="USD", reviewer="Test reviewer", source="Synthetic fixture",
                  reviewed_at=datetime.now(timezone.utc).isoformat(), returns_sha256=file_hash(path))
    atomic_json(evidence, record)
    series, _ = cash_inputs(path, evidence, dates)
    assert series.sum() == pytest.approx(0.0003)
    with pytest.raises(ValueError, match="Complete"):
        cash_inputs(path, evidence, dates.append(pd.DatetimeIndex(["2026-01-06"])))
    path.write_text(path.read_text() + "2026-01-06,0.1\n")
    with pytest.raises(ValueError, match="Bound"):
        cash_inputs(path, evidence, dates)


def test_regime_reliability_counts_include_probability_boundaries():
    from performance_evidence import reliability_by_regime

    p = [[1, 0, 0, 0], [0.6, 0.2, 0.2, 0], [0.25] * 4]
    result = reliability_by_regime(p, [0, 1, 2])
    for row in result.values():
        assert sum(b["count"] for b in row["bins"]) == 3
        assert all(0 <= b["observed_frequency"] <= 1 for b in row["bins"])


def test_fixed_decision_cost_stress_reduces_terminal_nav():
    from economic_design_assessment import replay

    dates = pd.bdate_range("2026-01-01", periods=50)
    returns = pd.DataFrame({"SPY": [0.001] * 50}, index=dates)
    targets = {d: {"SPY": 0.6 if i % 2 else 0.4} for i, d in enumerate(dates[::5])}
    nav = [replay(returns, targets, cost_rate=c).equity.iloc[-1] for c in [0, 0.0015, 0.003]]
    assert nav[0] > nav[1] > nav[2]


def test_missing_future_outcome_does_not_shift_forecast_calendar():
    from performance_forecast_calendar import calendar_evaluation

    rows = features(240)
    for row in rows:
        row["macro_valid"] = True
    rows[165]["macro_valid"] = False
    result = calendar_evaluation(rows, settings(), [160, 170], 0.1, 0.25)
    assert [r["origin"] for r in result["fixed_calendar"]] == [rows[160]["date"], rows[170]["date"]]
    assert result["fixed_calendar"][0]["status"] == "OUTCOME_UNAVAILABLE"
    assert result["bindings"][0]["origin"] == rows[170]["date"]
    assert result["outcomes"] == 1
