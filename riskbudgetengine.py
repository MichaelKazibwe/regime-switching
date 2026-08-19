"""
======================================================================
RISK BUDGET ENGINE
======================================================================

Production risk-budget allocation engine.

Phase
-----
IV-B.1A

Purpose
-------
Provides the production risk-budgeting dependency required by
PortfolioOptimizer and ProductionComposition.

The engine:

1. Retrieves regime-specific risk budgets.
2. Validates asset coverage.
3. Validates budget normalization.
4. Calculates portfolio risk contributions.
5. Calculates percentage risk contributions.
6. Calculates risk-budget deviations.
7. Produces deterministic diagnostics.
8. Provides health and metadata interfaces.
9. Supports serialization.
10. Fails fast on invalid production configuration.

This module does NOT contain test doubles.

======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from scipy.optimize import minimize

from core_constants import (
    REGIME_RISK_BUDGETS,
)


# ======================================================================
# EXCEPTIONS
# ======================================================================


class RiskBudgetEngineError(Exception):
    """
    Base exception for production risk-budget errors.
    """


class RiskBudgetConfigurationError(
    RiskBudgetEngineError
):
    """
    Raised when risk-budget configuration is invalid.
    """


class RiskBudgetCalculationError(
    RiskBudgetEngineError
):
    """
    Raised when risk-budget calculations fail.
    """


# ======================================================================
# RESULT OBJECTS
# ======================================================================


@dataclass(frozen=True)
class RiskBudgetResult:
    """
    Immutable risk-budget calculation result.
    """

    regime: str

    tickers: tuple[str, ...]

    target_budgets: dict[str, float]

    risk_contributions: dict[str, float]

    risk_contribution_pct: dict[str, float]

    budget_errors: dict[str, float]

    total_risk: float

    budget_error: float

    within_tolerance: bool

    diagnostics: dict[str, Any]

    # ------------------------------------------------------------------
    # SERIALIZATION
    # ------------------------------------------------------------------

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        Serialize the result.
        """

        return {
            "regime": self.regime,
            "tickers": list(
                self.tickers
            ),
            "target_budgets": dict(
                self.target_budgets
            ),
            "risk_contributions": dict(
                self.risk_contributions
            ),
            "risk_contribution_pct": dict(
                self.risk_contribution_pct
            ),
            "budget_errors": dict(
                self.budget_errors
            ),
            "total_risk": float(
                self.total_risk
            ),
            "budget_error": float(
                self.budget_error
            ),
            "within_tolerance": bool(
                self.within_tolerance
            ),
            "diagnostics": dict(
                self.diagnostics
            ),
        }


# ======================================================================
# RISK BUDGET ENGINE
# ======================================================================


class RiskBudgetEngine:
    """
    Production risk-budget engine.

    The engine uses REGIME_RISK_BUDGETS from core_constants as the
    authoritative source of target risk budgets.

    No test doubles are used.
    """

    API_VERSION = "1.0.0"

    COMPONENT = "RiskBudgetEngine"

    PHASE = "IV-B.1A"

    DEFAULT_TOLERANCE = 1e-6

    # ------------------------------------------------------------------
    # CONSTRUCTOR
    # ------------------------------------------------------------------

    def __init__(
        self,
        risk_budgets: Optional[
            dict[str, dict[str, float]]
        ] = None,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        """
        Initialize the production risk-budget engine.
        """

        self.risk_budgets = (
            risk_budgets
            if risk_budgets is not None
            else REGIME_RISK_BUDGETS
        )

        self.tolerance = float(
            tolerance
        )

        self.last_result: Optional[
            RiskBudgetResult
        ] = None

        self._validate_configuration()

    # ==================================================================
    # CONFIGURATION VALIDATION
    # ==================================================================

    def _validate_configuration(
        self,
    ) -> None:
        """
        Validate the complete risk-budget configuration.
        """

        if not isinstance(
            self.risk_budgets,
            dict,
        ):
            raise RiskBudgetConfigurationError(
                "risk_budgets must be a dictionary."
            )

        if self.tolerance <= 0.0:
            raise RiskBudgetConfigurationError(
                "Risk-budget tolerance must be positive."
            )

        if not self.risk_budgets:
            raise RiskBudgetConfigurationError(
                "No risk-budget regimes have been configured."
            )

        for regime, budgets in (
            self.risk_budgets.items()
        ):
            if not isinstance(
                budgets,
                dict,
            ):
                raise RiskBudgetConfigurationError(
                    f"Risk budget for regime "
                    f"'{regime}' must be a dictionary."
                )

            if not budgets:
                raise RiskBudgetConfigurationError(
                    f"Risk budget for regime "
                    f"'{regime}' is empty."
                )

            total = 0.0

            for ticker, budget in (
                budgets.items()
            ):
                value = float(
                    budget
                )

                if not np.isfinite(
                    value
                ):
                    raise RiskBudgetConfigurationError(
                        f"Risk budget for "
                        f"'{ticker}' in regime "
                        f"'{regime}' is not finite."
                    )

                if value < 0.0:
                    raise RiskBudgetConfigurationError(
                        f"Risk budget for "
                        f"'{ticker}' in regime "
                        f"'{regime}' cannot be negative."
                    )

                total += value

            if not np.isclose(
                total,
                1.0,
                atol=self.tolerance,
            ):
                raise RiskBudgetConfigurationError(
                    f"Risk budgets for regime "
                    f"'{regime}' must sum to 1. "
                    f"Got {total}."
                )

    # ==================================================================
    # REGIME NORMALIZATION
    # ==================================================================

    def _normalize_regime(
        self,
        regime: Any,
    ) -> str:
        """
        Normalize regime representation.
        """

        if regime is None:
            raise RiskBudgetConfigurationError(
                "regime cannot be None."
            )

        value = getattr(
            regime,
            "value",
            regime,
        )

        value = str(
            value
        ).strip().upper()

        if value in self.risk_budgets:
            return value

        # Allow lowercase keys in configuration.
        for configured_regime in (
            self.risk_budgets
        ):
            if (
                str(
                    configured_regime
                ).upper()
                == value
            ):
                return configured_regime

        raise RiskBudgetConfigurationError(
            f"No risk budget configured for "
            f"regime '{value}'."
        )

    # ==================================================================
    # TARGET BUDGETS
    # ==================================================================

    def get_target_budgets(
        self,
        regime: Any,
        tickers: list[str] | tuple[str, ...],
    ) -> dict[str, float]:
        """
        Return target risk budgets for the supplied assets.
        """

        normalized_regime = (
            self._normalize_regime(
                regime
            )
        )

        ordered_tickers = tuple(
            str(ticker)
            for ticker in tickers
        )

        if not ordered_tickers:
            raise RiskBudgetConfigurationError(
                "tickers cannot be empty."
            )

        configured = dict(
            self.risk_budgets[
                normalized_regime
            ]
        )

        missing = [
            ticker
            for ticker in ordered_tickers
            if ticker not in configured
        ]

        if missing:
            raise RiskBudgetConfigurationError(
                "Missing risk budgets for "
                f"assets {missing} in regime "
                f"'{normalized_regime}'."
            )

        budgets = {
            ticker: float(
                configured[ticker]
            )
            for ticker in ordered_tickers
        }

        total = sum(
            budgets.values()
        )

        if total <= 0.0:
            raise RiskBudgetConfigurationError(
                "Selected risk budgets have "
                "zero total allocation."
            )

        # Normalize the selected universe.
        budgets = {
            ticker: value / total
            for ticker, value in budgets.items()
        }

        return budgets

    # ==================================================================
    # RISK-BUDGET OPTIMIZATION
    # ==================================================================

    def optimize(
        self,
        covariance: Any,
        target_budget: Any,
    ) -> np.ndarray:
        """
        Solve the long-only risk-budget optimization problem.

        Parameters
        ----------
        covariance:
            Square covariance matrix.

        target_budget:
            Target percentage contribution to portfolio risk
            for each asset.

        Returns
        -------
        numpy.ndarray
            Long-only portfolio weights summing to one.

        Notes
        -----
        The optimization seeks weights for which:

            RC_i / total_Risk ~= target_budget_i

        where:

            RC_i = w_i * (Sigma @ w)_i

        The RiskBudgetEngine remains responsible for the
        optimization contract consumed by PortfolioOptimizer.
        """

        # --------------------------------------------------------------
        # INPUT NORMALIZATION
        # --------------------------------------------------------------

        covariance = np.asarray(
            covariance,
            dtype=float,
        )

        target_budget = np.asarray(
            target_budget,
            dtype=float,
        ).reshape(-1)

        # --------------------------------------------------------------
        # COVARIANCE VALIDATION
        # --------------------------------------------------------------

        if covariance.ndim != 2:
            raise RiskBudgetCalculationError(
                "Covariance must be a 2-dimensional matrix."
            )

        if (
            covariance.shape[0]
            != covariance.shape[1]
        ):
            raise RiskBudgetCalculationError(
                "Covariance matrix must be square."
            )

        n = covariance.shape[0]

        if n == 0:
            raise RiskBudgetCalculationError(
                "Covariance matrix cannot be empty."
            )

        if target_budget.size != n:
            raise RiskBudgetCalculationError(
                "Target budget length "
                f"{target_budget.size} does not match "
                f"covariance dimension {n}."
            )

        if not np.isfinite(
            covariance
        ).all():
            raise RiskBudgetCalculationError(
                "Covariance contains non-finite values."
            )

        if not np.isfinite(
            target_budget
        ).all():
            raise RiskBudgetCalculationError(
                "Target budget contains non-finite values."
            )

        if np.any(
            target_budget < 0.0
        ):
            raise RiskBudgetCalculationError(
                "Target budgets cannot be negative."
            )

        # --------------------------------------------------------------
        # SYMMETRIZE COVARIANCE
        # --------------------------------------------------------------

        covariance = (
            covariance
            + covariance.T
        ) / 2.0

        # --------------------------------------------------------------
        # TARGET-BUDGET VALIDATION
        # --------------------------------------------------------------

        budget_sum = float(
            target_budget.sum()
        )

        if budget_sum <= self.tolerance:
            raise RiskBudgetCalculationError(
                "Target budgets must have a positive total."
            )

        target_budget = (
            target_budget
            / budget_sum
        )

        # --------------------------------------------------------------
        # POSITIVE SEMIDEFINITE SAFETY
        # --------------------------------------------------------------

        eigenvalues = np.linalg.eigvalsh(
            covariance
        )

        minimum_eigenvalue = float(
            eigenvalues.min()
        )

        if minimum_eigenvalue < -1e-10:
            raise RiskBudgetCalculationError(
                "Covariance matrix is not "
                "positive semidefinite. "
                f"Minimum eigenvalue: "
                f"{minimum_eigenvalue:.6e}."
            )

        # Small numerical regularization for near-singular matrices.
        if minimum_eigenvalue < 1e-12:
            covariance = (
                covariance
                + np.eye(n) * 1e-12
            )

        # --------------------------------------------------------------
        # INITIAL WEIGHTS
        # --------------------------------------------------------------

        x0 = (
            np.ones(n, dtype=float)
            / float(n)
        )

        # --------------------------------------------------------------
        # RISK-BUDGET OBJECTIVE
        # --------------------------------------------------------------

        def objective(
            weights: np.ndarray,
        ) -> float:

            weights = np.asarray(
                weights,
                dtype=float,
            )

            portfolio_variance = float(
                weights
                @ covariance
                @ weights
            )

            if (
                not np.isfinite(
                    portfolio_variance
                )
                or portfolio_variance
                <= self.tolerance
            ):
                return 1e12

            marginal_risk = (
                covariance
                @ weights
            )

            contributions = (
                weights
                * marginal_risk
            )

            total_contribution = float(
                contributions.sum()
            )

            if (
                not np.isfinite(
                    total_contribution
                )
                or total_contribution
                <= self.tolerance
            ):
                return 1e12

            contribution_pct = (
                contributions
                / total_contribution
            )

            error = (
                contribution_pct
                - target_budget
            )

            return float(
                np.sum(
                    error ** 2
                )
            )

        # --------------------------------------------------------------
        # CONSTRAINTS
        # --------------------------------------------------------------

        constraints = [
            {
                "type": "eq",
                "fun": (
                    lambda weights:
                    float(
                        np.sum(weights)
                        - 1.0
                    )
                ),
            }
        ]

        bounds = [
            (0.0, 1.0)
            for _ in range(n)
        ]

        # --------------------------------------------------------------
        # OPTIMIZATION
        # --------------------------------------------------------------

        try:

            result = minimize(
                objective,
                x0,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={
                    "maxiter": 500,
                    "ftol": 1e-12,
                    "disp": False,
                },
            )

        except Exception as exc:

            raise RiskBudgetCalculationError(
                "Risk-budget optimization failed: "
                f"{exc}"
            ) from exc

        # --------------------------------------------------------------
        # OPTIMIZER FAILURE
        # --------------------------------------------------------------

        if not result.success:
            raise RiskBudgetCalculationError(
                "Risk-budget optimization did not converge: "
                f"{result.message}"
            )

        weights = np.asarray(
            result.x,
            dtype=float,
        )

        # --------------------------------------------------------------
        # FINAL NORMALIZATION
        # --------------------------------------------------------------

        weights = np.clip(
            weights,
            0.0,
            1.0,
        )

        weight_sum = float(
            weights.sum()
        )

        if (
            not np.isfinite(
                weight_sum
            )
            or weight_sum
            <= self.tolerance
        ):
            raise RiskBudgetCalculationError(
                "Risk-budget optimizer returned "
                "invalid weights."
            )

        weights = (
            weights
            / weight_sum
        )

        # --------------------------------------------------------------
        # FINAL INVARIANTS
        # --------------------------------------------------------------

        if not np.isfinite(
            weights
        ).all():
            raise RiskBudgetCalculationError(
                "Risk-budget optimizer returned "
                "non-finite weights."
            )

        if np.any(
            weights < -1e-10
        ):
            raise RiskBudgetCalculationError(
                "Risk-budget optimizer returned "
                "negative weights."
            )

        if not np.isclose(
            weights.sum(),
            1.0,
            atol=1e-8,
        ):
            raise RiskBudgetCalculationError(
                "Risk-budget optimizer returned "
                f"weights summing to {weights.sum()}."
            )

        return weights

    # ==================================================================
    # RISK CONTRIBUTIONS
    # ==================================================================

    def calculate_risk_contributions(
        self,
        weights: dict[str, float],
        covariance: Any,
        tickers: Optional[
            list[str] | tuple[str, ...]
        ] = None,
    ) -> dict[str, float]:
        """
        Calculate absolute component risk contributions.
        """

        if not weights:
            return {}

        if tickers is None:
            tickers = list(
                weights.keys()
            )

        ordered_tickers = tuple(
            str(ticker)
            for ticker in tickers
        )

        matrix = np.asarray(
            covariance,
            dtype=float,
        )

        if matrix.ndim != 2:
            raise RiskBudgetCalculationError(
                "Covariance must be a 2-dimensional matrix."
            )

        n = len(
            ordered_tickers
        )

        if matrix.shape != (
            n,
            n,
        ):
            raise RiskBudgetCalculationError(
                "Covariance dimension "
                f"{matrix.shape} does not match "
                f"ticker count {n}."
            )

        vector = np.asarray(
            [
                float(
                    weights.get(
                        ticker,
                        0.0,
                    )
                )
                for ticker in ordered_tickers
            ],
            dtype=float,
        )

        if not np.all(
            np.isfinite(
                vector
            )
        ):
            raise RiskBudgetCalculationError(
                "Portfolio weights contain "
                "non-finite values."
            )

        if not np.all(
            np.isfinite(
                matrix
            )
        ):
            raise RiskBudgetCalculationError(
                "Covariance contains "
                "non-finite values."
            )

        marginal = (
            matrix @ vector
        )

        contributions = (
            vector * marginal
        )

        return {
            ticker: float(
                contributions[index]
            )
            for index, ticker in enumerate(
                ordered_tickers
            )
        }

    # ==================================================================
    # PERCENTAGE RISK CONTRIBUTIONS
    # ==================================================================

    def calculate_risk_contribution_pct(
        self,
        risk_contributions: dict[str, float],
    ) -> dict[str, float]:
        """
        Convert absolute risk contributions into percentages.
        """

        if not risk_contributions:
            return {}

        total_risk = float(
            sum(
                risk_contributions.values()
            )
        )

        if abs(
            total_risk
        ) <= self.tolerance:
            return {
                ticker: 0.0
                for ticker in risk_contributions
            }

        return {
            ticker: float(
                contribution
                / total_risk
            )
            for ticker, contribution
            in risk_contributions.items()
        }

    # ==================================================================
    # BUDGET ERRORS
    # ==================================================================

    def calculate_budget_errors(
        self,
        target_budgets: dict[str, float],
        risk_contribution_pct: dict[str, float],
    ) -> dict[str, float]:
        """
        Calculate deviation from target risk budgets.
        """

        tickers = set(
            target_budgets
        ).union(
            risk_contribution_pct
        )

        return {
            ticker: float(
                risk_contribution_pct.get(
                    ticker,
                    0.0,
                )
                - target_budgets.get(
                    ticker,
                    0.0,
                )
            )
            for ticker in sorted(
                tickers
            )
        }

    # ==================================================================
    # COMPLETE ANALYSIS
    # ==================================================================

    def analyze(
        self,
        weights: dict[str, float],
        covariance: Any,
        regime: Any,
        tickers: Optional[
            list[str] | tuple[str, ...]
        ] = None,
    ) -> RiskBudgetResult:
        """
        Perform complete risk-budget analysis.
        """

        if tickers is None:
            tickers = list(
                weights.keys()
            )

        ordered_tickers = tuple(
            str(ticker)
            for ticker in tickers
        )

        normalized_regime = (
            self._normalize_regime(
                regime
            )
        )

        target_budgets = (
            self.get_target_budgets(
                normalized_regime,
                ordered_tickers,
            )
        )

        risk_contributions = (
            self.calculate_risk_contributions(
                weights,
                covariance,
                ordered_tickers,
            )
        )

        risk_contribution_pct = (
            self.calculate_risk_contribution_pct(
                risk_contributions
            )
        )

        budget_errors = (
            self.calculate_budget_errors(
                target_budgets,
                risk_contribution_pct,
            )
        )

        total_risk = float(
            sum(
                risk_contributions.values()
            )
        )

        budget_error = float(
            sum(
                abs(
                    value
                )
                for value in budget_errors.values()
            )
            / 2.0
        )

        within_tolerance = (
            budget_error
            <= self.tolerance
        )

        result = RiskBudgetResult(
            regime=normalized_regime,
            tickers=ordered_tickers,
            target_budgets=dict(
                target_budgets
            ),
            risk_contributions=dict(
                risk_contributions
            ),
            risk_contribution_pct=dict(
                risk_contribution_pct
            ),
            budget_errors=dict(
                budget_errors
            ),
            total_risk=total_risk,
            budget_error=budget_error,
            within_tolerance=within_tolerance,
            diagnostics={
                "ticker_count": len(
                    ordered_tickers
                ),
                "budget_sum": float(
                    sum(
                        target_budgets.values()
                    )
                ),
                "risk_contribution_sum": float(
                    sum(
                        risk_contribution_pct.values()
                    )
                ),
                "tolerance": self.tolerance,
            },
        )

        self.last_result = result

        return result

    # ==================================================================
    # BUDGET VECTOR
    # ==================================================================

    def budget_vector(
        self,
        regime: Any,
        tickers: list[str] | tuple[str, ...],
    ) -> np.ndarray:
        """
        Return target budgets as an ordered numpy vector.
        """

        budgets = (
            self.get_target_budgets(
                regime,
                tickers,
            )
        )

        return np.asarray(
            [
                budgets[ticker]
                for ticker in tickers
            ],
            dtype=float,
        )

    # ==================================================================
    # OPTIMIZER COMPATIBILITY
    # ==================================================================

    def get_risk_budget(
        self,
        regime: Any,
        tickers: list[str] | tuple[str, ...],
    ) -> dict[str, float]:
        """
        Compatibility interface for PortfolioOptimizer.
        """

        return self.get_target_budgets(
            regime,
            tickers,
        )

    def risk_budget(
        self,
        regime: Any,
        tickers: list[str] | tuple[str, ...],
    ) -> dict[str, float]:
        """
        Alias for get_target_budgets().
        """

        return self.get_target_budgets(
            regime,
            tickers,
        )

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return component health.
        """

        try:
            self._validate_configuration()

            regimes = list(
                self.risk_budgets.keys()
            )

            return {
                "api_version": self.API_VERSION,
                "component": self.COMPONENT,
                "phase": self.PHASE,
                "healthy": True,
                "regime_count": len(
                    regimes
                ),
                "regimes": regimes,
                "tolerance": self.tolerance,
            }

        except Exception as exc:
            return {
                "api_version": self.API_VERSION,
                "component": self.COMPONENT,
                "phase": self.PHASE,
                "healthy": False,
                "error": str(
                    exc
                ),
            }

    # ==================================================================
    # METADATA
    # ==================================================================

    def metadata(
        self,
    ) -> dict[str, Any]:
        """
        Return engine metadata.
        """

        return {
            "module": "riskbudgetengine",
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "regime_count": len(
                self.risk_budgets
            ),
            "tolerance": self.tolerance,
        }

    # ==================================================================
    # SERIALIZATION
    # ==================================================================

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        Serialize engine configuration and state.
        """

        return {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "risk_budgets": {
                str(regime): {
                    str(ticker): float(
                        value
                    )
                    for ticker, value
                    in budgets.items()
                }
                for regime, budgets
                in self.risk_budgets.items()
            },
            "tolerance": self.tolerance,
            "last_result": (
                None
                if self.last_result is None
                else self.last_result.to_dict()
            ),
        }

    # ==================================================================
    # RESET
    # ==================================================================

    def reset(
        self,
    ) -> None:
        """
        Reset calculation state.
        """

        self.last_result = None


# ======================================================================
# PUBLIC FACTORY
# ======================================================================


def build_risk_budget_engine(
    **kwargs: Any,
) -> RiskBudgetEngine:
    """
    Production factory for RiskBudgetEngine.
    """

    return RiskBudgetEngine(
        **kwargs
    )


# ======================================================================
# MODULE SELF-TEST
# ======================================================================


def test_risk_budget_engine() -> None:
    """
    Validate production risk-budget engine configuration.
    """

    engine = RiskBudgetEngine()

    health = engine.health_check()

    assert health[
        "healthy"
    ]

    assert (
        health[
            "regime_count"
        ]
        > 0
    )

    for regime in (
        engine.risk_budgets
    ):
        budgets = engine.get_target_budgets(
            regime,
            list(
                engine.risk_budgets[
                    regime
                ].keys()
            ),
        )

        assert np.isclose(
            sum(
                budgets.values()
            ),
            1.0,
            atol=1e-6,
        )

    print(
        "RiskBudgetEngine Phase IV-B.1A tests passed."
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":
    test_risk_budget_engine()