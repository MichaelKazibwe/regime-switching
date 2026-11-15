"""
=======================================================================
R3D.4 — DRAWDOWN / RECOVERY / RUIN PRODUCTION CONTRACT TESTS
=======================================================================

Focused tests for the R3D.4 additions:
    1. simulated drawdown threshold probabilities
    2. 50% drawdown probability
    3. report-ready drawdown aliases
    4. recovery/time-under-water contract
    5. deterministic risk-of-ruin preservation
=======================================================================
"""

import numpy as np

from drawdownrisk import DrawdownRiskEngine, RiskOfRuinAnalytics


def test_drawdown_threshold_probabilities() -> None:
    returns = np.array([-0.10, -0.10], dtype=float)

    result = RiskOfRuinAnalytics.simulate(
        returns,
        horizon=2,
        simulations=100,
        initial_equity=1.0,
        ruin_threshold=0.50,
        rng=np.random.default_rng(42),
    )

    assert np.isclose(result["prob_dd_10pct"], 1.0)
    assert np.isclose(result["prob_dd_20pct"], 0.0)
    assert np.isclose(result["prob_dd_30pct"], 0.0)
    assert np.isclose(result["prob_dd_50pct"], 0.0)
    assert result["worst_maximum_drawdown"] < 0.20


def test_drawdown_report_contract() -> None:
    returns = np.array([0.10, -0.20, 0.25], dtype=float)

    engine = DrawdownRiskEngine()
    result = engine.analyze(
        returns,
        horizon=5,
        simulations=100,
        rng=np.random.default_rng(42),
    )

    report = result["drawdown_report"]

    assert np.isclose(
        report["current_drawdown"],
        result["drawdown_state"]["current_drawdown"],
    )
    assert report["maximum_drawdown"] <= 0.0
    assert (
        report["time_under_water"]
        == report["maximum_drawdown_duration"]
    )
    assert "recovery" in report
    assert result["risk_of_ruin"] is not None
    assert "prob_dd_50pct" in result["risk_of_ruin"]


def test_risk_of_ruin_remains_finite_horizon_bootstrap() -> None:
    result = RiskOfRuinAnalytics.simulate(
        np.array([-0.01], dtype=float),
        horizon=10,
        simulations=100,
        initial_equity=1.0,
        ruin_threshold=0.50,
        rng=np.random.default_rng(42),
    )

    assert result["method"] == "historical_bootstrap"
    assert result["ruin_probability"] == 0.0
    assert result["survival_probability"] == 1.0
    assert result["ruined_paths"] == 0
    assert result["surviving_paths"] == 100


def test_drawdown_probability_monotonicity() -> None:
    returns = np.array([-0.25], dtype=float)

    result = RiskOfRuinAnalytics.simulate(
        returns,
        horizon=1,
        simulations=100,
        initial_equity=1.0,
        ruin_threshold=0.50,
        rng=np.random.default_rng(42),
    )

    assert result["prob_dd_10pct"] == 1.0
    assert result["prob_dd_20pct"] == 1.0
    assert result["prob_dd_30pct"] == 0.0
    assert result["prob_dd_50pct"] == 0.0
    assert (
        result["prob_dd_10pct"]
        >= result["prob_dd_20pct"]
        >= result["prob_dd_30pct"]
        >= result["prob_dd_50pct"]
    )


def run_tests() -> None:
    tests = (
        test_drawdown_threshold_probabilities,
        test_drawdown_report_contract,
        test_risk_of_ruin_remains_finite_horizon_bootstrap,
        test_drawdown_probability_monotonicity,
    )

    for test in tests:
        test()

    print(f"R3D.4 standalone tests: {len(tests)}/{len(tests)} passed.")
    print("R3D.4 STATUS: PASS")


if __name__ == "__main__":
    run_tests()
