"""
================================================================
RISK GOVERNOR TEST SUITE

R3C.2 - Standalone deterministic regression tests.

Tests:
    1. PASS decision
    2. Volatility REDUCE
    3. Leverage REDUCE
    4. Position concentration REJECT
    5. Risk contribution REJECT
    6. Governor never increases exposure
    7. Invalid inputs fail closed
    8. API / metadata / health contract
    9. Reduction preserves portfolio direction
   10. Zero portfolio
================================================================
"""

import numpy as np

from riskgovernor import (
    PortfolioRiskGovernor,
    RiskGovernorAction,
    RiskGovernorResult,
)


# ================================================================
# TEST FIXTURE
# ================================================================


def build_governor() -> PortfolioRiskGovernor:
    """
    Build the standard deterministic R3C test governor.
    """

    return PortfolioRiskGovernor(
        max_annual_volatility=0.20,
        max_leverage=1.00,
        max_position_weight=0.50,
        max_risk_contribution_pct=0.50,
        tolerance=1e-10,
        periods_per_year=252,
    )


# ================================================================
# 1. PASS
# ================================================================


def test_pass() -> None:
    governor = build_governor()

    weights = np.array(
        [0.25, 0.25],
        dtype=float,
    )

    covariance = np.diag(
        [
            0.000025,
            0.000025,
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == (
        RiskGovernorAction.PASS.value
    )

    assert result.approved

    assert np.isclose(
        result.scale,
        1.0,
    )

    assert np.allclose(
        result.approved_weights,
        weights,
    )

    assert result.breaches == ()


# ================================================================
# 2. VOLATILITY REDUCTION
# ================================================================


def test_volatility_reduction() -> None:
    governor = build_governor()

    weights = np.array(
        [0.50, 0.50],
        dtype=float,
    )

    covariance = np.diag(
        [
            0.0004,
            0.0004,
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == (
        RiskGovernorAction.REDUCE.value
    )

    assert result.approved

    assert (
        "MAX_ANNUAL_VOLATILITY"
        in result.breaches
    )

    assert (
        result.scale < 1.0
    )

    assert (
        result.scale > 0.0
    )

    assert (
        result.governed_annualized_volatility
        <=
        governor.max_annual_volatility
        +
        governor.tolerance
    )

    assert (
        result.governed_gross_leverage
        <=
        governor.max_leverage
        +
        governor.tolerance
    )


# ================================================================
# 3. LEVERAGE REDUCTION
# ================================================================


def test_leverage_reduction() -> None:
    governor = PortfolioRiskGovernor(
        max_annual_volatility=10.0,
        max_leverage=1.00,
        max_position_weight=2.00,
        max_risk_contribution_pct=1.00,
    )

    weights = np.array(
        [0.80, 0.80],
        dtype=float,
    )

    covariance = np.diag(
        [
            0.000001,
            0.000001,
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == (
        RiskGovernorAction.REDUCE.value
    )

    assert result.approved

    assert (
        "MAX_LEVERAGE"
        in result.breaches
    )

    expected_scale = (
        1.00 / 1.60
    )

    assert np.isclose(
        result.scale,
        expected_scale,
    )

    assert np.isclose(
        result.governed_gross_leverage,
        1.00,
    )


# ================================================================
# 4. POSITION CONCENTRATION REJECT
# ================================================================


def test_position_concentration_reject() -> None:
    governor = PortfolioRiskGovernor(
        max_annual_volatility=10.0,
        max_leverage=2.00,
        max_position_weight=0.40,
        max_risk_contribution_pct=1.00,
    )

    weights = np.array(
        [0.80, 0.20],
        dtype=float,
    )

    covariance = np.diag(
        [
            0.000001,
            0.000001,
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == (
        RiskGovernorAction.REJECT.value
    )

    assert not result.approved

    assert (
        "MAX_POSITION_WEIGHT"
        in result.breaches
    )

    assert np.isclose(
        result.scale,
        0.0,
    )

    assert result.approved_weights == ()


# ================================================================
# 5. RISK CONTRIBUTION REJECT
# ================================================================


def test_risk_contribution_reject() -> None:
    governor = PortfolioRiskGovernor(
        max_annual_volatility=10.0,
        max_leverage=2.00,
        max_position_weight=1.00,
        max_risk_contribution_pct=0.60,
    )

    weights = np.array(
        [0.90, 0.10],
        dtype=float,
    )

    covariance = np.diag(
        [
            0.0004,
            0.0001,
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == (
        RiskGovernorAction.REJECT.value
    )

    assert not result.approved

    assert (
        "MAX_RISK_CONTRIBUTION"
        in result.breaches
    )


# ================================================================
# 6. NEVER INCREASE EXPOSURE
# ================================================================


def test_never_increases_exposure() -> None:
    governor = build_governor()

    test_cases = [
        (
            np.array(
                [0.25, 0.25],
                dtype=float,
            ),
            np.diag(
                [
                    0.000025,
                    0.000025,
                ]
            ),
        ),
        (
            np.array(
                [0.50, 0.50],
                dtype=float,
            ),
            np.diag(
                [
                    0.0004,
                    0.0004,
                ]
            ),
        ),
        (
            np.array(
                [0.80, 0.80],
                dtype=float,
            ),
            np.diag(
                [
                    0.000001,
                    0.000001,
                ]
            ),
        ),
    ]

    for weights, covariance in test_cases:

        result = governor.govern(
            weights,
            covariance,
        )

        if result.approved_weights:

            governed = np.asarray(
                result.approved_weights,
                dtype=float,
            )

            assert np.all(
                governed
                <=
                weights
                +
                1e-12
            )

        assert (
            result.scale
            <=
            1.0
            +
            1e-12
        )


# ================================================================
# 7. INVALID INPUTS FAIL CLOSED
# ================================================================


def test_invalid_nan_covariance_rejects() -> None:
    governor = build_governor()

    weights = np.array(
        [0.50, 0.50],
        dtype=float,
    )

    covariance = np.array(
        [
            [0.0001, np.nan],
            [np.nan, 0.0001],
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == (
        RiskGovernorAction.REJECT.value
    )

    assert not result.approved

    assert (
        "INVALID_RISK_INPUT"
        in result.breaches
    )

    assert np.isclose(
        result.scale,
        0.0,
    )


def test_invalid_dimension_rejects() -> None:
    governor = build_governor()

    weights = np.array(
        [0.50, 0.50],
        dtype=float,
    )

    covariance = np.array(
        [
            [0.0001],
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == (
        RiskGovernorAction.REJECT.value
    )

    assert not result.approved

    assert (
        "INVALID_RISK_INPUT"
        in result.breaches
    )


# ================================================================
# 8. EVALUATE RETURNS A COMPLETE RESULT
# ================================================================


def test_evaluate_returns_result() -> None:
    """
    The diagnostic evaluate() path must return a complete
    RiskGovernorResult rather than None.
    """

    governor = build_governor()

    weights = np.array(
        [0.25, 0.25],
        dtype=float,
    )

    covariance = np.diag(
        [
            0.000025,
            0.000025,
        ]
    )

    result = governor.evaluate(
        weights,
        covariance,
    )

    assert isinstance(
        result,
        RiskGovernorResult,
    )
    assert result.action == (
        RiskGovernorAction.PASS.value
    )
    assert result.approved
    assert result.approved_weights == (
        0.25,
        0.25,
    )


# ================================================================
# 9. API / METADATA / HEALTH
# ================================================================


def test_api_contract() -> None:
    governor = build_governor()

    assert (
        governor.API_VERSION
        ==
        "1.1.0"
    )

    assert (
        "evaluate"
        in governor.PUBLIC_METHODS
    )

    assert (
        "govern"
        in governor.PUBLIC_METHODS
    )

    assert (
        "health_check"
        in governor.PUBLIC_METHODS
    )

    assert governor.validate()

    assert governor.health_check()


def test_metadata_contract() -> None:
    governor = build_governor()

    metadata = governor.metadata

    assert (
        metadata["class"]
        ==
        "PortfolioRiskGovernor"
    )

    assert (
        metadata["version"]
        ==
        "1.1.0"
    )

    assert (
        metadata["risk_frequency"]
        ==
        "daily"
    )

    assert (
        metadata["annualization_method"]
        ==
        "sqrt_time"
    )

    assert (
        metadata["periods_per_year"]
        ==
        252
    )

    assert (
        metadata["scope"]
        ==
        "portfolio_risk_governance"
    )


# ================================================================
# 10. REDUCTION PRESERVES DIRECTION
# ================================================================


def test_reduction_preserves_weight_direction() -> None:
    governor = PortfolioRiskGovernor(
        max_annual_volatility=0.10,
        max_leverage=2.00,
        max_position_weight=1.00,
        max_risk_contribution_pct=1.00,
    )

    weights = np.array(
        [
            0.60,
            -0.40,
        ],
        dtype=float,
    )

    covariance = np.array(
        [
            [0.0004, 0.0000],
            [0.0000, 0.0004],
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == (
        RiskGovernorAction.REDUCE.value
    )

    assert result.approved

    governed = np.asarray(
        result.approved_weights,
        dtype=float,
    )

    assert (
        governed[0] > 0.0
    )

    assert (
        governed[1] < 0.0
    )

    assert (
        np.sign(
            governed[0]
        )
        ==
        np.sign(
            weights[0]
        )
    )

    assert (
        np.sign(
            governed[1]
        )
        ==
        np.sign(
            weights[1]
        )
    )

    assert np.all(
        np.abs(governed)
        <=
        np.abs(weights)
        +
        1e-12
    )


# ================================================================
# 11. ZERO PORTFOLIO
# ================================================================


def test_zero_portfolio_passes() -> None:
    governor = build_governor()

    weights = np.array(
        [0.0, 0.0],
        dtype=float,
    )

    covariance = np.diag(
        [
            0.0001,
            0.0001,
        ]
    )

    result = governor.govern(
        weights,
        covariance,
    )

    assert result.action == (
        RiskGovernorAction.PASS.value
    )

    assert result.approved

    assert np.isclose(
        result.scale,
        1.0,
    )

    assert np.isclose(
        result.annualized_volatility,
        0.0,
    )

    assert np.isclose(
        result.gross_leverage,
        0.0,
    )

    assert np.isclose(
        result.cash,
        1.0,
    )

    assert np.allclose(
        result.approved_weights,
        [0.0, 0.0],
    )


# ================================================================
# RUNNER
# ================================================================


def run_tests() -> None:

    tests = [
        test_pass,
        test_volatility_reduction,
        test_leverage_reduction,
        test_position_concentration_reject,
        test_risk_contribution_reject,
        test_never_increases_exposure,
        test_invalid_nan_covariance_rejects,
        test_invalid_dimension_rejects,
        test_evaluate_returns_result,
        test_api_contract,
        test_metadata_contract,
        test_reduction_preserves_weight_direction,
        test_zero_portfolio_passes,
    ]

    passed = 0

    for test in tests:
        test()
        passed += 1

    print(
        f"Risk Governor tests: "
        f"{passed}/{len(tests)} passed."
    )

    print(
        "R3C.2 STATUS: PASS"
    )


# ================================================================
# MAIN
# ================================================================


if __name__ == "__main__":
    run_tests()