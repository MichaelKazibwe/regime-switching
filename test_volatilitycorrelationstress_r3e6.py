"""
========================================================================
R3E.6 DEDICATED REGRESSION TEST
========================================================================
"""

import numpy as np

from volatilitycorrelationstress import (
    VolatilityCorrelationStressEngine,
    VolatilityCorrelationStressError,
)


def test_identity_stress() -> None:
    covariance = np.diag([0.04, 0.09])
    weights = np.array([0.5, 0.5])

    engine = VolatilityCorrelationStressEngine()

    result = engine.stress_portfolio(
        weights,
        covariance,
        volatility_shocks=[0.0, 0.0],
        correlation_shock=0.0,
    )

    expected = np.sqrt(
        weights @ covariance @ weights
    )
    assert np.isclose(
        result["baseline_volatility"],
        expected,
    )
    assert np.isclose(
        result["stressed_volatility"],
        expected,
    )


def test_volatility_shock() -> None:
    covariance = np.diag([0.04, 0.09])
    weights = np.array([0.5, 0.5])

    engine = VolatilityCorrelationStressEngine()

    result = engine.stress_portfolio(
        weights,
        covariance,
        volatility_shocks=[1.0, 0.0],
    )

    assert result["stressed_volatility"] > result["baseline_volatility"]


def test_correlation_shock() -> None:
    covariance = np.array(
        [
            [0.04, 0.0],
            [0.0, 0.09],
        ]
    )
    weights = np.array([0.5, 0.5])

    engine = VolatilityCorrelationStressEngine()

    result = engine.stress_portfolio(
        weights,
        covariance,
        correlation_shock=0.50,
    )

    assert result["stressed_volatility"] > result["baseline_volatility"]

    stressed = np.asarray(
        result["stressed_covariance"]
    )
    assert np.linalg.eigvalsh(stressed).min() >= -1e-10


def test_combined_stress() -> None:
    covariance = np.array(
        [
            [0.04, 0.01],
            [0.01, 0.09],
        ]
    )
    weights = np.array([0.6, 0.4])

    engine = VolatilityCorrelationStressEngine()

    result = engine.stress_portfolio(
        weights,
        covariance,
        volatility_shocks=[0.25, 0.50],
        correlation_shock=0.10,
    )

    assert result["volatility_change"] > 0.0
    assert result["variance_change"] > 0.0


def test_annualization() -> None:
    covariance = np.diag([0.04, 0.09])
    weights = np.array([0.5, 0.5])

    engine = VolatilityCorrelationStressEngine()

    native = engine.stress_portfolio(
        weights,
        covariance,
    )
    annual = engine.stress_portfolio(
        weights,
        covariance,
        annualize=True,
    )

    assert np.isclose(
        annual["baseline_volatility"],
        native["baseline_volatility"] * np.sqrt(252),
    )
    assert np.isclose(
        annual["stressed_volatility"],
        native["stressed_volatility"] * np.sqrt(252),
    )


def test_invalid_inputs() -> None:
    engine = VolatilityCorrelationStressEngine()
    covariance = np.diag([0.04, 0.09])

    try:
        engine.stress_portfolio(
            [0.5],
            covariance,
        )
        raise AssertionError("Expected stress error")
    except VolatilityCorrelationStressError:
        pass

    try:
        engine.stress_portfolio(
            [0.5, 0.5],
            covariance,
            volatility_shocks=[-1.0, 0.0],
        )
        raise AssertionError("Expected stress error")
    except VolatilityCorrelationStressError:
        pass


def test_metadata_health_and_serialization() -> None:
    engine = VolatilityCorrelationStressEngine()

    assert engine.validate()
    assert engine.health_check()["healthy"]

    metadata = engine.metadata
    assert metadata["phase"] == "R3E.6"
    assert metadata["analytics_only"]
    assert not metadata["governance"]
    assert not metadata["execution"]

    payload = engine.to_dict()
    assert payload["metadata"]["component"] == (
        "VolatilityCorrelationStressEngine"
    )


def run_regression_tests() -> None:
    tests = (
        test_identity_stress,
        test_volatility_shock,
        test_correlation_shock,
        test_combined_stress,
        test_annualization,
        test_invalid_inputs,
        test_metadata_health_and_serialization,
    )

    passed = 0
    for test in tests:
        test()
        passed += 1

    print(
        f"VolatilityCorrelationStressEngine R3E.6 tests: "
        f"{passed}/{len(tests)} passed."
    )
    print("R3E.6 STATUS: PASS")


if __name__ == "__main__":
    run_regression_tests()
