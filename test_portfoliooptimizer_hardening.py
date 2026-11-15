"""
======================================================================
A16 — PORTFOLIO OPTIMIZER HARDENING REGRESSION TESTS
======================================================================

Formal production regression tests for PortfolioOptimizer.

This suite validates the hardened PUBLIC production contract.

Coverage
--------
1. Configuration validation
2. Asset-order validation
3. Covariance validation
4. Risk-budget resolution
5. Constraint boundary validation
6. Volatility-targeting integration
7. Leverage backstop
8. Cash accounting
9. Final numerical invariants
10. Regime differentiation
11. Deterministic repeated optimization
12. Public optimization result contract
13. Public summary contract
14. Health contract
15. Failure-state invalidation
16. Dependency failure propagation where part of the active
    optimization boundary

Important A16 contract decisions
--------------------------------
- Constraint-result structural failures are validated directly at
  the constraint boundary and therefore raise ValueError.
- Volatility-targeting dependency failures are wrapped by the
  PortfolioOptimizer calculation boundary.
- PortfolioOptimizer.summary() is an aggregate state summary and
  does not duplicate the complete optimization result.
- Forecast and Black-Litterman dependencies are not assumed to be
  executed by every optimization path merely because optional
  dependencies can be injected.
- Failed optimization invalidates the previous successful result
  state. Stale portfolio results must never remain exposed as a
  successful current result.
======================================================================
"""

from __future__ import annotations

import numpy as np
import pytest

from portfoliooptimizer import (
    PortfolioOptimizer,
    PortfolioOptimizerCalculationError,
    PortfolioOptimizerConfigurationError,
)


# ======================================================================
# TEST DOUBLES
# ======================================================================


class StubRiskBudgetEngine:
    """
    Deterministic production-compatible risk-budget dependency.
    """

    def __init__(self) -> None:

        self.risk_budgets = {
            "bull": {
                "SPY": 0.60,
                "TLT": 0.40,
            },
            "crisis": {
                "SPY": 0.30,
                "TLT": 0.70,
            },
        }

        self.last_budget_resolution: dict[str, object] = {}

    def get_target_budgets(
        self,
        regime,
        tickers,
    ):
        """
        Resolve deterministic test risk budgets.
        """

        normalized = (
            str(regime)
            .strip()
            .lower()
        )

        aliases = {
            "expansion": "bull",
            "recession": "crisis",
        }

        normalized = aliases.get(
            normalized,
            normalized,
        )

        if normalized not in self.risk_budgets:

            raise ValueError(
                f"Unknown test regime: {normalized}"
            )

        ordered_tickers = tuple(
            str(ticker).strip()
            for ticker in tickers
        )

        if not ordered_tickers:

            raise ValueError(
                "Test risk-budget ticker list cannot be empty."
            )

        if any(
            not ticker
            for ticker in ordered_tickers
        ):

            raise ValueError(
                "Test risk-budget ticker identifiers "
                "cannot be empty."
            )

        if len(
            set(ordered_tickers)
        ) != len(ordered_tickers):

            raise ValueError(
                "Test risk-budget tickers cannot contain duplicates."
            )

        try:

            budgets = {
                ticker: float(
                    self.risk_budgets[
                        normalized
                    ][ticker]
                )
                for ticker in ordered_tickers
            }

        except KeyError as exc:

            raise ValueError(
                "Test risk budget is missing "
                f"asset '{exc.args[0]}' for regime "
                f"'{normalized}'."
            ) from exc

        total = float(
            sum(
                budgets.values()
            )
        )

        if (
            not np.isfinite(total)
            or total <= 0.0
        ):

            raise ValueError(
                "Test risk budgets have invalid total."
            )

        budgets = {
            ticker: value / total
            for ticker, value in budgets.items()
        }

        self.last_budget_resolution = {
            "regime": normalized,
            "requested_assets": list(
                ordered_tickers
            ),
        }

        return budgets

    def optimize(
        self,
        covariance,
        target_budget,
    ):
        """
        Compatibility helper for implementations that expose an
        optimizer method on the risk-budget dependency.
        """

        del covariance

        return np.asarray(
            target_budget,
            dtype=float,
        )


class StubConstraints:
    """
    Deterministic pass-through constraint engine.
    """

    def enforce(
        self,
        weights,
    ):

        weights = np.asarray(
            weights,
            dtype=float,
        )

        return {
            "weights": weights,
            "cash": 0.0,
        }


class BadConstraintEngine:
    """
    Returns the wrong number of weights.
    """

    def enforce(
        self,
        weights,
    ):

        weights = np.asarray(
            weights,
            dtype=float,
        )

        return {
            "weights": weights[:-1],
            "cash": 0.0,
        }


class NegativeConstraintEngine:
    """
    Returns an invalid negative allocation.
    """

    def enforce(
        self,
        weights,
    ):

        weights = np.asarray(
            weights,
            dtype=float,
        ).copy()

        weights[0] = -0.10

        return {
            "weights": weights,
            "cash": 0.0,
        }


class NonFiniteConstraintEngine:
    """
    Returns a non-finite allocation.
    """

    def enforce(
        self,
        weights,
    ):

        weights = np.asarray(
            weights,
            dtype=float,
        ).copy()

        weights[0] = np.nan

        return {
            "weights": weights,
            "cash": 0.0,
        }


class StubVolatilityTarget:
    """
    Deterministic pass-through volatility-targeting dependency.

    Signature intentionally matches the production invocation:

        scale_weights(
            weights,
            covariance,
            target_volatility,
            max_leverage=...
        )
    """

    def scale_weights(
        self,
        weights,
        covariance=None,
        target_volatility=None,
        max_leverage=None,
        **kwargs,
    ):

        del covariance
        del target_volatility
        del max_leverage
        del kwargs

        return np.asarray(
            weights,
            dtype=float,
        ).copy()


class FailingVolatilityTarget:
    """
    Deliberately failing volatility-targeting dependency.
    """

    def scale_weights(
        self,
        weights,
        covariance=None,
        target_volatility=None,
        max_leverage=None,
        **kwargs,
    ):

        del weights
        del covariance
        del target_volatility
        del max_leverage
        del kwargs

        raise RuntimeError(
            "volatility targeting failure"
        )


class OversizedVolatilityTarget:
    """
    Deliberately returns oversized weights.

    The optimizer's authoritative leverage backstop must prevent
    final gross exposure from exceeding maximum leverage.
    """

    def scale_weights(
        self,
        weights,
        covariance=None,
        target_volatility=None,
        max_leverage=None,
        **kwargs,
    ):

        del covariance
        del target_volatility
        del max_leverage
        del kwargs

        weights = np.asarray(
            weights,
            dtype=float,
        )

        return (
            weights * 10.0
        )


class StubForecastEngine:
    """
    Optional deterministic forecast dependency.

    This dependency exists for constructor compatibility and
    integration tests where the production optimizer actually
    invokes forecast generation.
    """

    def forecast(
        self,
        *args,
        **kwargs,
    ):

        del args
        del kwargs

        return np.array(
            [0.01, 0.02],
            dtype=float,
        )


class WrongDimensionForecast:
    """
    Deliberately malformed forecast dependency.

    Used only where forecast execution is explicitly requested.
    """

    def forecast(
        self,
        *args,
        **kwargs,
    ):

        del args
        del kwargs

        return np.array(
            [0.01],
            dtype=float,
        )


class StubBlackLitterman:
    """
    Optional deterministic Black-Litterman dependency.
    """

    def posterior_returns(
        self,
        *args,
        **kwargs,
    ):

        del args
        del kwargs

        return np.array(
            [0.01, 0.02],
            dtype=float,
        )


class WrongDimensionBlackLitterman:
    """
    Deliberately malformed Black-Litterman dependency.

    Used only where Black-Litterman execution is explicitly requested.
    """

    def posterior_returns(
        self,
        *args,
        **kwargs,
    ):

        del args
        del kwargs

        return np.array(
            [0.01],
            dtype=float,
        )


# ======================================================================
# FIXTURES
# ======================================================================


@pytest.fixture
def covariance():
    """
    Well-conditioned positive-semidefinite covariance matrix.
    """

    return np.array(
        [
            [0.04, 0.006],
            [0.006, 0.09],
        ],
        dtype=float,
    )


@pytest.fixture
def optimizer():
    """
    Fully wired deterministic PortfolioOptimizer.
    """

    return PortfolioOptimizer(
        risk_budget_engine=(
            StubRiskBudgetEngine()
        ),
        constraints=(
            StubConstraints()
        ),
        vol_target_engine=(
            StubVolatilityTarget()
        ),
        forecast_engine=(
            StubForecastEngine()
        ),
        black_litterman=(
            StubBlackLitterman()
        ),
    )


@pytest.fixture
def assets():
    """
    Deterministic production-style two-asset universe.
    """

    return (
        "SPY",
        "TLT",
    )


# ======================================================================
# CONFIGURATION HARDENING
# ======================================================================


def test_rejects_missing_risk_budget_engine():

    with pytest.raises(
        PortfolioOptimizerConfigurationError
    ):

        PortfolioOptimizer(
            risk_budget_engine=None,
            constraints=StubConstraints(),
            vol_target_engine=StubVolatilityTarget(),
        )


def test_rejects_missing_constraints():

    with pytest.raises(
        PortfolioOptimizerConfigurationError
    ):

        PortfolioOptimizer(
            risk_budget_engine=StubRiskBudgetEngine(),
            constraints=None,
            vol_target_engine=StubVolatilityTarget(),
        )


def test_rejects_missing_volatility_target_engine():

    with pytest.raises(
        PortfolioOptimizerConfigurationError
    ):

        PortfolioOptimizer(
            risk_budget_engine=StubRiskBudgetEngine(),
            constraints=StubConstraints(),
            vol_target_engine=None,
        )


# ======================================================================
# ASSET VALIDATION
# ======================================================================


def test_rejects_empty_asset_order(
    optimizer,
    covariance,
):

    with pytest.raises(
        PortfolioOptimizerCalculationError,
        match="Asset validation failed",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=[],
        )


def test_rejects_duplicate_assets(
    optimizer,
    covariance,
):

    with pytest.raises(
        PortfolioOptimizerCalculationError,
        match="Asset validation failed",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=(
                "SPY",
                "SPY",
            ),
        )


def test_rejects_empty_asset_identifier(
    optimizer,
    covariance,
):

    with pytest.raises(
        PortfolioOptimizerCalculationError,
        match="Asset validation failed",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=(
                "SPY",
                "",
            ),
        )


def test_rejects_non_string_asset_identifier(
    optimizer,
    covariance,
):
    """
    Non-string asset identifiers must ultimately fail through the
    production asset/risk-budget validation boundary.

    PortfolioOptimizer currently canonicalizes asset identifiers
    before risk-budget resolution, so None becomes the string
    'None' and is rejected because no corresponding risk budget
    exists.
    """

    with pytest.raises(
        PortfolioOptimizerCalculationError,
        match="Risk-budget resolution failed",
    ):
        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=(
                "SPY",
                None,
            ),
        )


# ======================================================================
# COVARIANCE VALIDATION
# ======================================================================


def test_rejects_non_square_covariance(
    optimizer,
    assets,
):

    covariance = np.ones(
        (2, 3),
        dtype=float,
    )

    with pytest.raises(
        PortfolioOptimizerCalculationError,
        match="Covariance validation failed",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=assets,
        )


def test_rejects_covariance_dimension_mismatch(
    optimizer,
):

    covariance = np.eye(
        3,
        dtype=float,
    )

    with pytest.raises(
        PortfolioOptimizerCalculationError,
        match="Covariance validation failed",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=(
                "SPY",
                "TLT",
            ),
        )


def test_rejects_nonfinite_covariance(
    optimizer,
    assets,
):

    covariance = np.eye(
        2,
        dtype=float,
    )

    covariance[0, 0] = np.nan

    with pytest.raises(
        PortfolioOptimizerCalculationError,
        match="Covariance validation failed",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=assets,
        )


def test_rejects_infinite_covariance(
    optimizer,
    assets,
):

    covariance = np.eye(
        2,
        dtype=float,
    )

    covariance[0, 1] = np.inf
    covariance[1, 0] = np.inf

    with pytest.raises(
        PortfolioOptimizerCalculationError,
        match="Covariance validation failed",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=assets,
        )


def test_rejects_materially_indefinite_covariance(
    optimizer,
    assets,
):

    covariance = np.array(
        [
            [1.0, 2.0],
            [2.0, 1.0],
        ],
        dtype=float,
    )

    with pytest.raises(
        PortfolioOptimizerCalculationError,
        match="positive semidefinite",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=assets,
        )


def test_accepts_small_numerical_covariance_asymmetry(
    optimizer,
):

    covariance = np.array(
        [
            [
                0.04,
                0.00600000000001,
            ],
            [
                0.006,
                0.09,
            ],
        ],
        dtype=float,
    )

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=(
            "SPY",
            "TLT",
        ),
    )

    assert result is not None


# ======================================================================
# RISK-BUDGET VALIDATION
# ======================================================================


def test_unknown_regime_is_rejected(
    optimizer,
    covariance,
    assets,
):

    with pytest.raises(
        PortfolioOptimizerConfigurationError
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="unknown",
            asset_order=assets,
        )


def test_missing_asset_budget_is_rejected(
    optimizer,
    covariance,
):

    with pytest.raises(
        PortfolioOptimizerCalculationError,
        match="Risk-budget resolution failed",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=(
                "SPY",
                "GLD",
            ),
        )


def test_risk_budget_is_normalized(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    budget = result[
        "risk_budget"
    ]

    assert np.isclose(
        sum(
            budget.values()
        ),
        1.0,
        atol=1e-10,
    )


def test_risk_budget_preserves_asset_order(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    budget = result[
        "risk_budget"
    ]

    assert list(
        budget.keys()
    ) == list(
        assets
    )


# ======================================================================
# CONSTRAINT HARDENING
# ======================================================================


def test_constraint_dimension_mismatch_is_rejected(
    covariance,
):

    optimizer = PortfolioOptimizer(
        risk_budget_engine=(
            StubRiskBudgetEngine()
        ),
        constraints=(
            BadConstraintEngine()
        ),
        vol_target_engine=(
            StubVolatilityTarget()
        ),
    )

    with pytest.raises(
        ValueError,
        match="Constraint engine returned",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=(
                "SPY",
                "TLT",
            ),
        )


def test_negative_constraint_weights_are_rejected(
    covariance,
):

    optimizer = PortfolioOptimizer(
        risk_budget_engine=(
            StubRiskBudgetEngine()
        ),
        constraints=(
            NegativeConstraintEngine()
        ),
        vol_target_engine=(
            StubVolatilityTarget()
        ),
    )

    with pytest.raises(
        ValueError,
        match="Constraint engine returned",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=(
                "SPY",
                "TLT",
            ),
        )


def test_nonfinite_constraint_weights_are_rejected(
    covariance,
):

    optimizer = PortfolioOptimizer(
        risk_budget_engine=(
            StubRiskBudgetEngine()
        ),
        constraints=(
            NonFiniteConstraintEngine()
        ),
        vol_target_engine=(
            StubVolatilityTarget()
        ),
    )

    with pytest.raises(
        ValueError,
        match="Constraint engine returned",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=(
                "SPY",
                "TLT",
            ),
        )


# ======================================================================
# VOLATILITY TARGETING HARDENING
# ======================================================================


def test_volatility_target_failure_is_not_silently_ignored(
    covariance,
):

    optimizer = PortfolioOptimizer(
        risk_budget_engine=(
            StubRiskBudgetEngine()
        ),
        constraints=(
            StubConstraints()
        ),
        vol_target_engine=(
            FailingVolatilityTarget()
        ),
    )

    with pytest.raises(
        PortfolioOptimizerCalculationError,
        match="Volatility-targeting engine failed",
    ):

        optimizer.optimize(
            covariance=covariance,
            regime="expansion",
            asset_order=(
                "SPY",
                "TLT",
            ),
        )


def test_leverage_backstop_limits_oversized_volatility_target(
    covariance,
):

    optimizer = PortfolioOptimizer(
        risk_budget_engine=(
            StubRiskBudgetEngine()
        ),
        constraints=(
            StubConstraints()
        ),
        vol_target_engine=(
            OversizedVolatilityTarget()
        ),
    )

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=(
            "SPY",
            "TLT",
        ),
    )

    assert (
        result["gross_exposure"]
        <= result["maximum_leverage"]
        + 1e-8
    )

    assert np.isfinite(
        result["gross_exposure"]
    )

    assert np.isfinite(
        result["cash"]
    )


# ======================================================================
# FINAL PORTFOLIO INVARIANTS
# ======================================================================


def test_final_weights_are_finite(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    weights = np.asarray(
        result["weights"],
        dtype=float,
    )

    assert np.isfinite(
        weights
    ).all()


def test_final_weights_have_correct_dimension(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    weights = np.asarray(
        result["weights"],
        dtype=float,
    )

    assert weights.size == len(
        assets
    )


def test_final_weights_are_nonnegative(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    weights = np.asarray(
        result["weights"],
        dtype=float,
    )

    assert np.all(
        weights >= -1e-10
    )


def test_cash_is_finite_and_nonnegative(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    cash = float(
        result["cash"]
    )

    assert np.isfinite(
        cash
    )

    assert cash >= -1e-10


def test_gross_exposure_is_finite(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    gross_exposure = float(
        result["gross_exposure"]
    )

    assert np.isfinite(
        gross_exposure
    )

    assert gross_exposure >= -1e-10


def test_exposure_plus_cash_equals_one(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    assert np.isclose(
        result["gross_exposure"]
        + result["cash"],
        1.0,
        atol=1e-6,
    )


def test_final_exposure_respects_regime_leverage(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    assert (
        result["gross_exposure"]
        <= result["maximum_leverage"]
        + 1e-8
    )


def test_risk_report_is_present(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    assert result[
        "risk_report"
    ] is not None


# ======================================================================
# REGIME DIFFERENTIATION
# ======================================================================


def test_expansion_and_recession_have_different_targets(
    optimizer,
    covariance,
    assets,
):

    expansion = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    recession = optimizer.optimize(
        covariance=covariance,
        regime="recession",
        asset_order=assets,
    )

    assert (
        expansion["regime"]
        != recession["regime"]
    )

    assert not np.isclose(
        expansion["risk_budget"]["SPY"],
        recession["risk_budget"]["SPY"],
    )


def test_expansion_and_recession_produce_different_budget_vectors(
    optimizer,
    covariance,
    assets,
):

    expansion = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    recession = optimizer.optimize(
        covariance=covariance,
        regime="recession",
        asset_order=assets,
    )

    expansion_budget = np.asarray(
        [
            expansion["risk_budget"][asset]
            for asset in assets
        ],
        dtype=float,
    )

    recession_budget = np.asarray(
        [
            recession["risk_budget"][asset]
            for asset in assets
        ],
        dtype=float,
    )

    assert not np.allclose(
        expansion_budget,
        recession_budget,
    )


# ======================================================================
# DETERMINISM
# ======================================================================


def test_repeated_optimization_is_deterministic(
    optimizer,
    covariance,
    assets,
):

    first = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    second = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    np.testing.assert_allclose(
        first["weights"],
        second["weights"],
        atol=1e-10,
        rtol=1e-10,
    )

    assert first["cash"] == pytest.approx(
        second["cash"],
        abs=1e-10,
    )

    assert first["gross_exposure"] == pytest.approx(
        second["gross_exposure"],
        abs=1e-10,
    )


# ======================================================================
# PUBLIC RESULT CONTRACT
# ======================================================================


def test_public_contract_contains_required_fields(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    required = {
        "weights",
        "cash",
        "regime",
        "expected_returns",
        "risk_report",
        "volatility_diagnostics",
        "asset_order",
        "risk_budget",
        "baseline_weights",
        "bl_multipliers",
        "bl_tilted_weights",
        "constrained_weights",
        "constraint_cash",
        "gross_exposure",
        "target_volatility",
        "maximum_leverage",
        "weight_map",
    }

    assert required.issubset(
        result.keys()
    )


def test_result_asset_order_matches_input(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    assert tuple(
        result["asset_order"]
    ) == assets


def test_result_weights_match_asset_order(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    weight_map = result[
        "weight_map"
    ]

    assert list(
        weight_map.keys()
    ) == list(
        assets
    )


def test_result_weight_map_matches_weights(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    weights = np.asarray(
        result["weights"],
        dtype=float,
    )

    mapped = np.asarray(
        [
            result["weight_map"][asset]
            for asset in assets
        ],
        dtype=float,
    )

    np.testing.assert_allclose(
        weights,
        mapped,
        atol=1e-10,
        rtol=1e-10,
    )


def test_expected_returns_public_field_is_structurally_safe(
    optimizer,
    covariance,
    assets,
):
    """
    Validate the public expected_returns field without assuming that
    every optimization path produces a fully populated forecast vector.

    If expected_returns is populated, it must have one value per asset
    and all values must be finite.
    """

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    assert "expected_returns" in result

    expected_returns = result[
        "expected_returns"
    ]

    if expected_returns is None:
        return

    values = np.asarray(
        expected_returns,
        dtype=float,
    ).reshape(-1)

    # A scalar/NaN placeholder is not a valid populated forecast.
    if values.size == 1 and np.isnan(values[0]):
        return

    assert values.size == len(
        assets
    )

    assert np.isfinite(
        values
    ).all()


def test_baseline_weights_are_dimensionally_safe(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    baseline = np.asarray(
        result["baseline_weights"],
        dtype=float,
    )

    assert baseline.size == len(
        assets
    )

    assert np.isfinite(
        baseline
    ).all()


def test_constrained_weights_are_dimensionally_safe(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    constrained = np.asarray(
        result["constrained_weights"],
        dtype=float,
    )

    assert constrained.size == len(
        assets
    )

    assert np.isfinite(
        constrained
    ).all()


# ======================================================================
# SUMMARY CONTRACT
# ======================================================================


def test_summary_contains_core_state(
    optimizer,
    covariance,
    assets,
):

    optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    summary = optimizer.summary()

    required = {
        "component",
        "api_version",
        "phase",
        "last_result_available",
        "last_regime",
        "asset_count",
        "gross_exposure",
        "net_exposure",
        "cash",
        "financing",
    }

    assert required.issubset(
        summary.keys()
    )


def test_summary_reflects_successful_result(
    optimizer,
    covariance,
    assets,
):

    optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    summary = optimizer.summary()

    assert summary[
        "last_result_available"
    ] is True

    assert summary[
        "asset_count"
    ] == len(
        assets
    )

    assert summary[
        "last_regime"
    ] is not None

    assert np.isfinite(
        float(
            summary["gross_exposure"]
        )
    )

    assert np.isfinite(
        float(
            summary["cash"]
        )
    )


# ======================================================================
# HEALTH CONTRACT
# ======================================================================


def test_health_check_returns_dictionary(
    optimizer,
):

    health = optimizer.health_check()

    assert isinstance(
        health,
        dict,
    )


def test_health_check_exposes_component_identity(
    optimizer,
):

    health = optimizer.health_check()

    assert (
        health["component"]
        == "PortfolioOptimizer"
    )


def test_health_check_exposes_api_version(
    optimizer,
):

    health = optimizer.health_check()

    assert (
        health["api_version"]
        == optimizer.API_VERSION
    )


# ======================================================================
# FAILURE STATE MANAGEMENT
# ======================================================================


def test_failed_optimization_clears_result_state(
    optimizer,
    covariance,
    assets,
):

    successful = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    assert successful is not None

    previous_summary = (
        optimizer.summary()
    )

    assert previous_summary[
        "last_result_available"
    ] is True

    with pytest.raises(
        PortfolioOptimizerCalculationError
    ):

        optimizer.optimize(
            covariance=np.array(
                [
                    [1.0, 2.0],
                    [2.0, 1.0],
                ],
                dtype=float,
            ),
            regime="expansion",
            asset_order=assets,
        )

    current_summary = (
        optimizer.summary()
    )

    assert isinstance(
        current_summary,
        dict,
    )

    assert current_summary[
        "last_result_available"
    ] is False

    assert current_summary[
        "asset_count"
    ] is None

    assert current_summary[
        "cash"
    ] is None

    assert current_summary[
        "gross_exposure"
    ] is None


def test_failed_optimization_invalidates_last_result(
    optimizer,
    covariance,
    assets,
):

    optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    assert optimizer.summary()[
        "last_result_available"
    ] is True

    with pytest.raises(
        PortfolioOptimizerCalculationError
    ):

        optimizer.optimize(
            covariance=np.array(
                [
                    [1.0, 2.0],
                    [2.0, 1.0],
                ],
                dtype=float,
            ),
            regime="expansion",
            asset_order=assets,
        )

    assert optimizer.summary()[
        "last_result_available"
    ] is False


def test_failed_optimization_does_not_report_previous_asset_count(
    optimizer,
    covariance,
    assets,
):

    optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    assert optimizer.summary()[
        "asset_count"
    ] == 2

    with pytest.raises(
        PortfolioOptimizerCalculationError
    ):

        optimizer.optimize(
            covariance=np.array(
                [
                    [1.0, 2.0],
                    [2.0, 1.0],
                ],
                dtype=float,
            ),
            regime="expansion",
            asset_order=assets,
        )

    assert optimizer.summary()[
        "asset_count"
    ] is None


# ======================================================================
# API FREEZE
# ======================================================================


def test_api_version_is_present(
    optimizer,
):

    assert isinstance(
        optimizer.API_VERSION,
        str,
    )

    assert optimizer.API_VERSION


def test_public_methods_are_present(
    optimizer,
):

    public_methods = tuple(
        optimizer.PUBLIC_METHODS
    )

    assert "optimize" in (
        public_methods
    )

    assert "summary" in (
        public_methods
    )

    assert "health_check" in (
        public_methods
    )


# ======================================================================
# DIRECT CONSTRAINT BOUNDARY TESTS
# ======================================================================


def test_constraint_boundary_rejects_wrong_dimension_directly(
    covariance,
):

    optimizer = PortfolioOptimizer(
        risk_budget_engine=(
            StubRiskBudgetEngine()
        ),
        constraints=(
            BadConstraintEngine()
        ),
        vol_target_engine=(
            StubVolatilityTarget()
        ),
    )

    weights = np.array(
        [0.60, 0.40],
        dtype=float,
    )

    with pytest.raises(
        ValueError,
        match="Constraint engine returned",
    ):

        optimizer._apply_constraints(
            weights,
            (
                "SPY",
                "TLT",
            ),
        )


def test_constraint_boundary_rejects_negative_weights_directly(
    covariance,
):

    del covariance

    optimizer = PortfolioOptimizer(
        risk_budget_engine=(
            StubRiskBudgetEngine()
        ),
        constraints=(
            NegativeConstraintEngine()
        ),
        vol_target_engine=(
            StubVolatilityTarget()
        ),
    )

    weights = np.array(
        [0.60, 0.40],
        dtype=float,
    )

    with pytest.raises(
        ValueError,
        match="Constraint engine returned",
    ):

        optimizer._apply_constraints(
            weights,
            (
                "SPY",
                "TLT",
            ),
        )


def test_constraint_boundary_rejects_nonfinite_weights_directly(
    covariance,
):

    del covariance

    optimizer = PortfolioOptimizer(
        risk_budget_engine=(
            StubRiskBudgetEngine()
        ),
        constraints=(
            NonFiniteConstraintEngine()
        ),
        vol_target_engine=(
            StubVolatilityTarget()
        ),
    )

    weights = np.array(
        [0.60, 0.40],
        dtype=float,
    )

    with pytest.raises(
        ValueError,
        match="Constraint engine returned",
    ):

        optimizer._apply_constraints(
            weights,
            (
                "SPY",
                "TLT",
            ),
        )


# ======================================================================
# VOLATILITY TARGET DIRECT BOUNDARY
# ======================================================================


def test_volatility_target_boundary_propagates_dependency_failure(
    covariance,
):

    optimizer = PortfolioOptimizer(
        risk_budget_engine=(
            StubRiskBudgetEngine()
        ),
        constraints=(
            StubConstraints()
        ),
        vol_target_engine=(
            FailingVolatilityTarget()
        ),
    )

    weights = np.array(
        [0.60, 0.40],
        dtype=float,
    )

    with pytest.raises(
        PortfolioOptimizerCalculationError,
        match="Volatility-targeting engine failed",
    ):

        optimizer._apply_volatility_targeting(
            weights,
            covariance,
            0.15,
            1.0,
        )


# ======================================================================
# REGRESSION ENTRY POINT
# ======================================================================


def test_a16_portfolio_optimizer_hardening_smoke(
    optimizer,
    covariance,
    assets,
):

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    assert result is not None

    assert (
        optimizer.summary()[
            "last_result_available"
        ]
        is True
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":

    pytest.main(
        [
            __file__,
            "-q",
        ]
    )