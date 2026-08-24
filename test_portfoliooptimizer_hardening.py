"""
======================================================================
PORTFOLIO OPTIMIZER HARDENING TESTS
======================================================================

Formal production regression tests for PortfolioOptimizer.

These tests validate the PUBLIC production contract rather than
implementation-specific internals.

Coverage
--------
1. Configuration validation
2. Asset-order validation
3. Covariance validation
4. Risk-budget resolution
5. Black-Litterman dimensional safety
6. Constraint dimensional safety
7. Volatility-targeting integration
8. Leverage backstop
9. Cash accounting
10. Final numerical invariants
11. Regime differentiation
12. Deterministic repeated optimization
13. Public result contract
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
    Minimal production-compatible risk-budget dependency.

    PortfolioOptimizer may normalize public regime names before passing
    them to the risk-budget engine.

    Current production regime compatibility:

        expansion -> bull
        recession -> crisis

    The stub therefore exposes the canonical normalized production
    regime names and explicitly supports the public aliases above.

    The stub deliberately remains deterministic and contains no
    production risk-budget logic.
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

        Public aliases are normalized before configuration lookup.
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
        Compatibility helper for code paths that expose an optimizer
        method on the risk-budget dependency.
        """

        del covariance

        return np.asarray(
            target_budget,
            dtype=float,
        )


class StubConstraints:
    """
    Pass-through constraint engine.

    Returns the production-compatible constraint result structure.
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


class StubVolatilityTarget:
    """
    Deterministic pass-through volatility-targeting engine.

    PortfolioOptimizer expects scale_weights() to return the scaled
    portfolio weight vector directly.
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
    Deliberately failing dependency used to verify failure
    propagation.
    """

    def scale_weights(
        self,
        *args,
        **kwargs,
    ):
        del args
        del kwargs

        raise RuntimeError(
            "volatility targeting failure"
        )


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


class StubForecastEngine:
    """
    Optional deterministic forecast dependency.
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
        risk_budget_engine=StubRiskBudgetEngine(),
        constraints=StubConstraints(),
        vol_target_engine=StubVolatilityTarget(),
        forecast_engine=StubForecastEngine(),
        black_litterman=StubBlackLitterman(),
    )


@pytest.fixture
def assets():
    """
    Deterministic production-style two-asset test universe.
    """

    return (
        "SPY",
        "TLT",
    )


# ======================================================================
# CONFIGURATION HARDENING
# ======================================================================


def test_rejects_missing_risk_budget_engine():
    """
    Risk-budget dependency is mandatory.
    """

    with pytest.raises(
        PortfolioOptimizerConfigurationError
    ):
        PortfolioOptimizer(
            risk_budget_engine=None,
            constraints=StubConstraints(),
            vol_target_engine=StubVolatilityTarget(),
        )


def test_rejects_missing_constraints():
    """
    Constraint dependency is mandatory.
    """

    with pytest.raises(
        PortfolioOptimizerConfigurationError
    ):
        PortfolioOptimizer(
            risk_budget_engine=StubRiskBudgetEngine(),
            constraints=None,
            vol_target_engine=StubVolatilityTarget(),
        )


def test_rejects_missing_volatility_target_engine():
    """
    Volatility-targeting dependency is mandatory.
    """

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
    """
    Empty asset universes must fail before optimization.
    """

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
    """
    Duplicate asset identifiers must fail deterministically.
    """

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
    """
    Empty asset identifiers must fail explicitly.
    """

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


# ======================================================================
# COVARIANCE VALIDATION
# ======================================================================


def test_rejects_non_square_covariance(
    optimizer,
    assets,
):
    """
    Covariance matrix must be square.
    """

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
    """
    Covariance dimension must match asset universe dimension.
    """

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
    """
    Non-finite covariance values must fail.
    """

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


def test_rejects_materially_indefinite_covariance(
    optimizer,
    assets,
):
    """
    Materially indefinite covariance matrices must fail.
    """

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
    """
    Tiny floating-point covariance asymmetry should be accepted
    and handled by the production covariance validation layer.
    """

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
    """
    Unknown regimes must not silently fall back to another regime.
    """

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
    """
    Assets without a configured risk budget must fail explicitly.
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
                "GLD",
            ),
        )


# ======================================================================
# FINAL PORTFOLIO INVARIANTS
# ======================================================================


def test_final_weights_are_finite(
    optimizer,
    covariance,
    assets,
):
    """
    Final portfolio weights must be finite.
    """

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


def test_final_weights_are_nonnegative(
    optimizer,
    covariance,
    assets,
):
    """
    Final portfolio weights must respect the long-only constraint.
    """

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
    """
    Cash must be finite and non-negative.
    """

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    cash = float(
        result["cash"]
    )

    assert np.isfinite(cash)
    assert cash >= -1e-10


def test_exposure_plus_cash_equals_one(
    optimizer,
    covariance,
    assets,
):
    """
    Gross exposure plus cash must equal one.
    """

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
    """
    Final gross exposure must not exceed the regime leverage limit.
    """

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
    """
    Production optimization result must include a risk report.
    """

    result = optimizer.optimize(
        covariance=covariance,
        regime="expansion",
        asset_order=assets,
    )

    assert result["risk_report"] is not None


# ======================================================================
# CONSTRAINT HARDENING
# ======================================================================


def test_constraint_dimension_mismatch_is_rejected(
    covariance,
):
    """
    A constraint engine returning the wrong number of weights must
    fail at the constraint boundary.
    """

    optimizer = PortfolioOptimizer(
        risk_budget_engine=StubRiskBudgetEngine(),
        constraints=BadConstraintEngine(),
        vol_target_engine=StubVolatilityTarget(),
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
    """
    Negative weights returned by the constraint engine must be rejected.
    """

    optimizer = PortfolioOptimizer(
        risk_budget_engine=StubRiskBudgetEngine(),
        constraints=NegativeConstraintEngine(),
        vol_target_engine=StubVolatilityTarget(),
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
# VOLATILITY TARGET HARDENING
# ======================================================================


def test_volatility_target_failure_is_not_silently_ignored(
    covariance,
):
    """
    A volatility-targeting dependency failure must propagate through
    the PortfolioOptimizer calculation boundary.
    """

    optimizer = PortfolioOptimizer(
        risk_budget_engine=StubRiskBudgetEngine(),
        constraints=StubConstraints(),
        vol_target_engine=FailingVolatilityTarget(),
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


# ======================================================================
# REGIME DIFFERENTIATION
# ======================================================================


def test_expansion_and_recession_have_different_targets(
    optimizer,
    covariance,
    assets,
):
    """
    Expansion and recession must resolve to different risk budgets.

    This verifies that the optimizer does not collapse distinct
    production regimes into the same allocation policy.
    """

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


# ======================================================================
# DETERMINISM
# ======================================================================


def test_repeated_optimization_is_deterministic(
    optimizer,
    covariance,
    assets,
):
    """
    Repeated optimization with identical inputs must produce identical
    results within numerical tolerance.
    """

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
# PUBLIC CONTRACT
# ======================================================================


def test_public_contract_contains_required_fields(
    optimizer,
    covariance,
    assets,
):
    """
    Verify the required production result fields.
    """

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