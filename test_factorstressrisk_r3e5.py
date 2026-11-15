"""Dedicated R3E.5 regression tests for FactorStressRiskEngine."""

from __future__ import annotations

import numpy as np
import pandas as pd

from factorstressrisk import FactorStressRiskEngine, FactorStressRiskError


def _loadings() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Market": [1.0, 0.8, 0.2],
            "Value": [0.0, 0.5, -0.3],
            "Momentum": [0.2, 0.1, 0.7],
        },
        index=["SPY", "QQQ", "TLT"],
    )


def test_factor_stress_math() -> None:
    engine = FactorStressRiskEngine()
    weights = {"SPY": 0.5, "QQQ": 0.3, "TLT": 0.2}
    shocks = {"Market": -0.20, "Value": -0.10, "Momentum": -0.05}

    result = engine.factor_stress(
        weights,
        _loadings(),
        shocks,
        initial_equity=100_000.0,
    )

    exposure = np.array([0.5, 0.3, 0.2]) @ _loadings().to_numpy()
    expected_return = float(
        exposure @ np.array([-0.20, -0.10, -0.05])
    )

    assert np.isclose(result.portfolio_return, expected_return)
    assert np.isclose(result.portfolio_pnl, 100_000.0 * expected_return)
    assert np.isclose(result.portfolio_loss, max(0.0, -result.portfolio_pnl))
    assert np.isclose(result.stressed_equity, 100_000.0 + result.portfolio_pnl)


def test_factor_exposures_and_contributions() -> None:
    engine = FactorStressRiskEngine()
    result = engine.factor_stress(
        {"SPY": 0.5, "QQQ": 0.3, "TLT": 0.2},
        _loadings(),
        {"Market": -0.20, "Value": -0.10, "Momentum": -0.05},
        initial_equity=100_000.0,
    )

    assert set(result.factor_exposures) == {"Market", "Value", "Momentum"}
    assert set(result.factor_pnl_contributions) == set(result.factor_exposures)
    assert set(result.factor_loss_contributions) == set(result.factor_exposures)

    assert np.isclose(
        sum(result.factor_pnl_contributions.values()),
        result.portfolio_pnl,
    )


def test_asset_results_and_largest_contributor() -> None:
    engine = FactorStressRiskEngine()
    result = engine.factor_stress(
        {"SPY": 0.5, "QQQ": 0.3, "TLT": 0.2},
        _loadings(),
        {"Market": -0.20, "Value": -0.10, "Momentum": -0.05},
        initial_equity=100_000.0,
    )

    assert len(result.asset_results) == 3
    assert result.largest_loss_contributor in {"SPY", "QQQ", "TLT"}
    assert result.largest_factor_loss_contributor in {
        "Market",
        "Value",
        "Momentum",
    }


def test_negative_weights_are_supported() -> None:
    engine = FactorStressRiskEngine()
    result = engine.factor_stress(
        {"SPY": 1.0, "TLT": -0.5, "QQQ": 0.5},
        _loadings(),
        {"Market": -0.10, "Value": 0.00, "Momentum": 0.00},
        initial_equity=100_000.0,
    )

    assert np.isfinite(result.portfolio_pnl)
    assert np.isclose(result.gross_exposure, 2.0)
    assert np.isclose(result.net_exposure, 1.0)


def test_factor_model_object_is_supported() -> None:
    class Model:
        asset_loadings = _loadings()

    engine = FactorStressRiskEngine()
    result = engine.factor_stress(
        {"SPY": 0.5, "QQQ": 0.3, "TLT": 0.2},
        Model(),
        {"Market": -0.20, "Value": -0.10, "Momentum": -0.05},
    )

    assert np.isfinite(result.portfolio_return)


def test_invalid_factor_shocks_are_rejected() -> None:
    engine = FactorStressRiskEngine()
    try:
        engine.factor_stress(
            {"SPY": 0.5, "QQQ": 0.3, "TLT": 0.2},
            _loadings(),
            {"Market": -1.0, "Value": -0.10, "Momentum": -0.05},
        )
        raise AssertionError("Expected FactorStressRiskError")
    except FactorStressRiskError:
        pass


def test_contract_and_health() -> None:
    engine = FactorStressRiskEngine()
    assert engine.health_check()
    assert engine.API_VERSION == "1.0.0"
    assert engine.PHASE == "R3E.5"
    assert tuple(engine.PUBLIC_METHODS) == (
        "factor_stress",
        "stress_scenario",
        "summary",
        "metadata",
        "health_check",
        "validate",
        "to_dict",
        "save_json",
    )
    assert engine.metadata["analytics_only"] is True
    assert engine.metadata["governance"] is False
    assert engine.metadata["execution"] is False


def run_tests() -> None:
    tests = (
        test_factor_stress_math,
        test_factor_exposures_and_contributions,
        test_asset_results_and_largest_contributor,
        test_negative_weights_are_supported,
        test_factor_model_object_is_supported,
        test_invalid_factor_shocks_are_rejected,
        test_contract_and_health,
    )

    for test in tests:
        test()

    print(f"FactorStressRiskEngine R3E.5 tests: {len(tests)}/{len(tests)} passed.")
    print("R3E.5 STATUS: PASS")


if __name__ == "__main__":
    run_tests()
