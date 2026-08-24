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
3. Supports explicit production asset-budget aliases for supported
   portfolio subsets.
4. Validates budget normalization.
5. Calculates portfolio risk contributions.
6. Calculates percentage risk contributions.
7. Calculates risk-budget deviations.
8. Produces deterministic diagnostics.
9. Provides health and metadata interfaces.
10. Supports serialization.
11. Fails fast on invalid production configuration.

Canonical regime budgets remain authoritative.

Default supported subset aliases:

    EFA -> VEA
    EEM -> VWO

These aliases allow the production engine to operate on supported
three-asset test/subset portfolios without modifying the canonical
production risk-budget configuration.

This module does NOT contain test doubles.

======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from scipy.optimize import minimize

from core_constants import REGIME_RISK_BUDGETS
from riskcontributionanalyzer import RiskContributionAnalytics


# ======================================================================
# EXCEPTIONS
# ======================================================================


class RiskBudgetEngineError(Exception):
    """
    Base exception for production risk-budget errors.
    """


class RiskBudgetConfigurationError(RiskBudgetEngineError):
    """
    Raised when risk-budget configuration is invalid.
    """


class RiskBudgetCalculationError(RiskBudgetEngineError):
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
            "tickers": list(self.tickers),
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

    REGIME_RISK_BUDGETS remains the authoritative source of production
    regime budgets.

    The engine additionally supports explicit asset-budget aliases.
    An alias does not create a new independent risk budget; it maps a
    supported portfolio asset to the canonical budget of its configured
    economic proxy.

    Default aliases:

        EFA -> VEA
        EEM -> VWO

    This preserves the canonical production configuration while allowing
    supported subset portfolios to operate correctly.
    """

    API_VERSION = "1.0.0"
    COMPONENT = "RiskBudgetEngine"
    PHASE = "IV-B.1A"

    DEFAULT_TOLERANCE = 1e-6

    # ------------------------------------------------------------------
    # DEFAULT SUPPORTED ASSET ALIASES
    # ------------------------------------------------------------------

    DEFAULT_ASSET_BUDGET_ALIASES = {
        "EFA": "VEA",
        "EEM": "VWO",
    }

    # ------------------------------------------------------------------
    # CONSTRUCTOR
    # ------------------------------------------------------------------

    def __init__(
        self,
        risk_budgets: Optional[
            dict[str, dict[str, float]]
        ] = None,
        tolerance: float = DEFAULT_TOLERANCE,
        asset_budget_aliases: Optional[
            dict[str, str]
        ] = None,
    ) -> None:
        """
        Initialize the production risk-budget engine.

        Parameters
        ----------
        risk_budgets:
            Optional explicit regime risk-budget configuration.

        tolerance:
            Numerical validation tolerance.

        asset_budget_aliases:
            Optional mapping of supported requested assets to canonical
            budget assets.

        The supplied aliases extend, rather than replace, the defaults.
        """

        self.risk_budgets = (
            risk_budgets
            if risk_budgets is not None
            else REGIME_RISK_BUDGETS
        )

        self.tolerance = float(
            tolerance
        )

        self.asset_budget_aliases = dict(
            self.DEFAULT_ASSET_BUDGET_ALIASES
        )

        if asset_budget_aliases is not None:
            self.asset_budget_aliases.update(
                {
                    str(asset).strip(): str(source).strip()
                    for asset, source
                    in asset_budget_aliases.items()
                }
            )

        self.last_result: Optional[
            RiskBudgetResult
        ] = None

        self.last_budget_resolution: dict[
            str,
            Any,
        ] = {}

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

        if not np.isfinite(
            self.tolerance
        ):
            raise RiskBudgetConfigurationError(
                "Risk-budget tolerance must be finite."
            )

        if self.tolerance <= 0.0:
            raise RiskBudgetConfigurationError(
                "Risk-budget tolerance must be positive."
            )

        if not isinstance(
            self.asset_budget_aliases,
            dict,
        ):
            raise RiskBudgetConfigurationError(
                "asset_budget_aliases must be a dictionary."
            )

        for asset, source in (
            self.asset_budget_aliases.items()
        ):
            asset_name = str(
                asset
            ).strip()

            source_name = str(
                source
            ).strip()

            if not asset_name or not source_name:
                raise RiskBudgetConfigurationError(
                    "Asset-budget aliases cannot contain "
                    "empty identifiers."
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
                ticker_name = str(
                    ticker
                ).strip()

                if not ticker_name:
                    raise RiskBudgetConfigurationError(
                        f"Risk budget for regime "
                        f"'{regime}' contains an empty asset."
                    )

                try:
                    value = float(
                        budget
                    )
                except (
                    TypeError,
                    ValueError,
                ) as exc:
                    raise RiskBudgetConfigurationError(
                        f"Risk budget for '{ticker}' in regime "
                        f"'{regime}' must be numeric."
                    ) from exc

                if not np.isfinite(
                    value
                ):
                    raise RiskBudgetConfigurationError(
                        f"Risk budget for '{ticker}' in regime "
                        f"'{regime}' is not finite."
                    )

                if value < 0.0:
                    raise RiskBudgetConfigurationError(
                        f"Risk budget for '{ticker}' in regime "
                        f"'{regime}' cannot be negative."
                    )

                total += value

            if not np.isclose(
                total,
                1.0,
                atol=self.tolerance,
                rtol=0.0,
            ):
                raise RiskBudgetConfigurationError(
                    f"Risk budgets for regime '{regime}' "
                    f"must sum to 1. Got {total}."
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
        ).strip()

        if not value:
            raise RiskBudgetConfigurationError(
                "regime cannot be empty."
            )

        for configured_regime in (
            self.risk_budgets
        ):
            if (
                str(
                    configured_regime
                ).strip().lower()
                == value.lower()
            ):
                return configured_regime

        raise RiskBudgetConfigurationError(
            f"No risk budget configured for regime '{value}'."
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

        Directly configured assets use their canonical regime budget.

        A missing requested asset may use an explicit supported
        asset-budget alias.

        Example:

            EFA -> VEA
            EEM -> VWO

        The selected budgets are renormalized across the requested
        portfolio universe.

        Unknown assets still fail explicitly.
        """

        normalized_regime = (
            self._normalize_regime(
                regime
            )
        )

        if tickers is None:
            raise RiskBudgetConfigurationError(
                "tickers cannot be None."
            )

        ordered_tickers = tuple(
            str(ticker).strip()
            for ticker in tickers
        )

        if not ordered_tickers:
            raise RiskBudgetConfigurationError(
                "tickers cannot be empty."
            )

        if any(
            not ticker
            for ticker in ordered_tickers
        ):
            raise RiskBudgetConfigurationError(
                "tickers cannot contain empty identifiers."
            )

        if len(
            set(ordered_tickers)
        ) != len(
            ordered_tickers
        ):
            raise RiskBudgetConfigurationError(
                "tickers cannot contain duplicates."
            )

        configured = dict(
            self.risk_budgets[
                normalized_regime
            ]
        )

        budgets: dict[
            str,
            float,
        ] = {}

        resolution: dict[
            str,
            dict[str, Any],
        ] = {}

        unresolved: list[str] = []

        for ticker in ordered_tickers:
            if ticker in configured:
                source_asset = ticker

                resolution[ticker] = {
                    "source_asset": source_asset,
                    "method": "direct",
                }

            else:
                source_asset = (
                    self.asset_budget_aliases.get(
                        ticker
                    )
                )

                if (
                    source_asset is None
                    or source_asset not in configured
                ):
                    unresolved.append(
                        ticker
                    )
                    continue

                resolution[ticker] = {
                    "source_asset": source_asset,
                    "method": "alias",
                }

            value = float(
                configured[
                    source_asset
                ]
            )

            if not np.isfinite(
                value
            ):
                raise RiskBudgetConfigurationError(
                    f"Resolved risk budget for asset "
                    f"'{ticker}' in regime "
                    f"'{normalized_regime}' is not finite."
                )

            if value < 0.0:
                raise RiskBudgetConfigurationError(
                    f"Resolved risk budget for asset "
                    f"'{ticker}' in regime "
                    f"'{normalized_regime}' cannot be negative."
                )

            budgets[ticker] = value

        if unresolved:
            raise RiskBudgetConfigurationError(
                "Missing risk budgets for assets "
                f"{unresolved} in regime "
                f"'{normalized_regime}'. "
                "No supported asset-budget alias is configured."
            )

        total = float(
            sum(
                budgets.values()
            )
        )

        if (
            not np.isfinite(
                total
            )
            or total <= self.tolerance
        ):
            raise RiskBudgetConfigurationError(
                "Selected risk budgets have "
                "zero or invalid total allocation."
            )

        budgets = {
            ticker: float(
                value / total
            )
            for ticker, value
            in budgets.items()
        }

        budget_sum = float(
            sum(
                budgets.values()
            )
        )

        if not np.isclose(
            budget_sum,
            1.0,
            atol=self.tolerance,
            rtol=0.0,
        ):
            raise RiskBudgetConfigurationError(
                "Resolved selected risk budgets "
                "do not sum to one."
            )

        self.last_budget_resolution = {
            "regime": normalized_regime,
            "requested_assets": list(
                ordered_tickers
            ),
            "resolution": resolution,
            "budget_source": (
                "REGIME_RISK_BUDGETS"
            ),
            "selected_budget_sum_before_normalization": (
                total
            ),
            "normalized_budget_sum": (
                budget_sum
            ),
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

        The optimization seeks weights for which:

            RC_i / total_risk ~= target_budget_i

        where:

            RC_i = w_i * (Sigma @ w)_i
        """

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

        if (
            not np.isfinite(
                budget_sum
            )
            or budget_sum <= self.tolerance
        ):
            raise RiskBudgetCalculationError(
                "Target budgets must have a "
                "positive finite total."
            )

        target_budget = (
            target_budget
            / budget_sum
        )

        # --------------------------------------------------------------
        # POSITIVE SEMIDEFINITE SAFETY
        # --------------------------------------------------------------

        try:
            eigenvalues = np.linalg.eigvalsh(
                covariance
            )
        except np.linalg.LinAlgError as exc:
            raise RiskBudgetCalculationError(
                "Unable to determine covariance eigenvalues."
            ) from exc

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

        if minimum_eigenvalue < 1e-12:
            covariance = (
                covariance
                + np.eye(n)
                * 1e-12
            )

        # --------------------------------------------------------------
        # INITIAL WEIGHTS
        # --------------------------------------------------------------

        x0 = (
            np.ones(
                n,
                dtype=float,
            )
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

            if not np.isfinite(
                weights
            ).all():
                return 1e12

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
            (
                0.0,
                1.0,
            )
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

        if not np.isfinite(
            weights
        ).all():
            raise RiskBudgetCalculationError(
                "Risk-budget optimizer returned "
                "non-finite weights."
            )

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
            or weight_sum <= self.tolerance
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
            rtol=0.0,
        ):
            raise RiskBudgetCalculationError(
                "Risk-budget optimizer returned "
                f"weights summing to {weights.sum()}."
            )

        # --------------------------------------------------------------
        # FINAL RISK-BUDGET VALIDATION
        # --------------------------------------------------------------

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
            raise RiskBudgetCalculationError(
                "Risk-budget optimizer produced "
                "invalid total risk contribution."
            )

        realized_budget = (
            contributions
            / total_contribution
        )

        if not np.isfinite(
            realized_budget
        ).all():
            raise RiskBudgetCalculationError(
                "Risk-budget optimizer produced "
                "non-finite realized risk budgets."
            )

        budget_error = float(
            np.sum(
                np.abs(
                    realized_budget
                    - target_budget
                )
            )
            / 2.0
        )

        if not np.isfinite(
            budget_error
        ):
            raise RiskBudgetCalculationError(
                "Risk-budget optimization produced "
                "a non-finite budget error."
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
        Calculate absolute component variance contributions.

        Historical RiskBudgetEngine contract:

            RC_i = w_i * (Sigma @ w)_i

        Therefore:

            sum(RC_i) = portfolio variance.

        RiskContributionAnalytics is the canonical implementation of
        Euler volatility risk.

        Its volatility contributions are converted back into variance
        contributions:

            RC_variance_i
                = RC_volatility_i * sigma_p

        This preserves the existing RiskBudgetEngine contract while
        avoiding duplicated Euler-risk mathematics.
        """

        if not weights:
            return {}

        if tickers is None:
            tickers = list(
                weights.keys()
            )

        ordered_tickers = tuple(
            str(ticker).strip()
            for ticker in tickers
        )

        if not ordered_tickers:
            return {}

        if any(
            not ticker
            for ticker in ordered_tickers
        ):
            raise RiskBudgetCalculationError(
                "tickers cannot contain empty identifiers."
            )

        if len(
            set(ordered_tickers)
        ) != len(
            ordered_tickers
        ):
            raise RiskBudgetCalculationError(
                "tickers cannot contain duplicates."
            )

        matrix = np.asarray(
            covariance,
            dtype=float,
        )

        n = len(
            ordered_tickers
        )

        if matrix.ndim != 2:
            raise RiskBudgetCalculationError(
                "Covariance must be a 2-dimensional matrix."
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

        if not np.isfinite(
            matrix
        ).all():
            raise RiskBudgetCalculationError(
                "Covariance contains non-finite values."
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

        if not np.isfinite(
            vector
        ).all():
            raise RiskBudgetCalculationError(
                "Portfolio weights contain non-finite values."
            )

        # --------------------------------------------------------------
        # Portfolio variance
        # --------------------------------------------------------------

        portfolio_variance = float(
            vector
            @ matrix
            @ vector
        )

        if not np.isfinite(
            portfolio_variance
        ):
            raise RiskBudgetCalculationError(
                "Portfolio variance is non-finite."
            )

        if portfolio_variance < 0.0:
            if portfolio_variance < -1e-12:
                raise RiskBudgetCalculationError(
                    "Portfolio variance is materially negative: "
                    f"{portfolio_variance:.12e}."
                )

            portfolio_variance = 0.0

        # A zero-volatility portfolio has zero component risk.
        if (
            portfolio_variance
            <= self.tolerance
        ):
            return {
                ticker: 0.0
                for ticker in ordered_tickers
            }

        # --------------------------------------------------------------
        # Canonical Euler risk calculation
        # --------------------------------------------------------------

        try:
            volatility = (
                RiskContributionAnalytics
                .portfolio_volatility(
                    vector,
                    matrix,
                )
            )

            euler_contributions = (
                RiskContributionAnalytics
                .risk_contributions(
                    vector,
                    matrix,
                )
            )

        except (
            ValueError,
            np.linalg.LinAlgError,
        ) as exc:
            raise RiskBudgetCalculationError(
                "RiskContributionAnalytics failed to "
                f"calculate component risk: {exc}"
            ) from exc

        if (
            not np.isfinite(
                volatility
            )
            or volatility <= self.tolerance
        ):
            raise RiskBudgetCalculationError(
                "Portfolio volatility is invalid."
            )

        if not np.isfinite(
            euler_contributions
        ).all():
            raise RiskBudgetCalculationError(
                "Euler risk contributions contain "
                "non-finite values."
            )

        # --------------------------------------------------------------
        # Convert volatility RC -> variance RC
        # --------------------------------------------------------------

        variance_contributions = (
            euler_contributions
            * volatility
        )

        if not np.isfinite(
            variance_contributions
        ).all():
            raise RiskBudgetCalculationError(
                "Variance risk contributions contain "
                "non-finite values."
            )

        contribution_sum = float(
            variance_contributions.sum()
        )

        if not np.isclose(
            contribution_sum,
            portfolio_variance,
            atol=1e-8,
            rtol=1e-8,
        ):
            raise RiskBudgetCalculationError(
                "Variance risk decomposition failed. "
                f"Component-risk sum="
                f"{contribution_sum:.12e}, "
                f"portfolio variance="
                f"{portfolio_variance:.12e}."
            )

        return {
            ticker: float(
                variance_contributions[index]
            )
            for index, ticker
            in enumerate(
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

        values = np.asarray(
            list(
                risk_contributions.values()
            ),
            dtype=float,
        )

        if not np.isfinite(
            values
        ).all():
            raise RiskBudgetCalculationError(
                "Risk contributions contain non-finite values."
            )

        total_risk = float(
            values.sum()
        )

        if not np.isfinite(
            total_risk
        ):
            raise RiskBudgetCalculationError(
                "Total risk contribution is non-finite."
            )

        if abs(
            total_risk
        ) <= self.tolerance:
            return {
                ticker: 0.0
                for ticker in risk_contributions
            }

        percentages = (
            values
            / total_risk
        )

        if not np.isfinite(
            percentages
        ).all():
            raise RiskBudgetCalculationError(
                "Percentage risk contributions contain "
                "non-finite values."
            )

        if not np.isclose(
            percentages.sum(),
            1.0,
            atol=1e-8,
            rtol=1e-8,
        ):
            raise RiskBudgetCalculationError(
                "Percentage risk contributions do not "
                "sum to one."
            )

        return {
            ticker: float(
                percentages[index]
            )
            for index, ticker
            in enumerate(
                risk_contributions
            )
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

        if not isinstance(
            target_budgets,
            dict,
        ):
            raise RiskBudgetCalculationError(
                "target_budgets must be a dictionary."
            )

        if not isinstance(
            risk_contribution_pct,
            dict,
        ):
            raise RiskBudgetCalculationError(
                "risk_contribution_pct must be a dictionary."
            )

        tickers = set(
            target_budgets
        ).union(
            risk_contribution_pct
        )

        result: dict[
            str,
            float,
        ] = {}

        for ticker in sorted(
            tickers
        ):
            actual = float(
                risk_contribution_pct.get(
                    ticker,
                    0.0,
                )
            )

            target = float(
                target_budgets.get(
                    ticker,
                    0.0,
                )
            )

            if not np.isfinite(
                actual
            ):
                raise RiskBudgetCalculationError(
                    f"Risk contribution percentage for "
                    f"'{ticker}' is non-finite."
                )

            if not np.isfinite(
                target
            ):
                raise RiskBudgetCalculationError(
                    f"Target risk budget for "
                    f"'{ticker}' is non-finite."
                )

            result[ticker] = float(
                actual - target
            )

        return result

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

        if not isinstance(
            weights,
            dict,
        ):
            raise RiskBudgetCalculationError(
                "weights must be a dictionary."
            )

        if not weights:
            raise RiskBudgetCalculationError(
                "weights cannot be empty."
            )

        if tickers is None:
            tickers = list(
                weights.keys()
            )

        ordered_tickers = tuple(
            str(ticker).strip()
            for ticker in tickers
        )

        if not ordered_tickers:
            raise RiskBudgetCalculationError(
                "tickers cannot be empty."
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

        if not np.isfinite(
            total_risk
        ):
            raise RiskBudgetCalculationError(
                "Total risk is non-finite."
            )

        budget_error = float(
            sum(
                abs(value)
                for value in budget_errors.values()
            )
            / 2.0
        )

        if not np.isfinite(
            budget_error
        ):
            raise RiskBudgetCalculationError(
                "Budget error is non-finite."
            )

        within_tolerance = (
            budget_error
            <= self.tolerance
        )

        diagnostics = {
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
            "budget_resolution": dict(
                self.last_budget_resolution
            ),
        }

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
            diagnostics=diagnostics,
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

        vector = np.asarray(
            [
                budgets[ticker]
                for ticker in tickers
            ],
            dtype=float,
        )

        if not np.isfinite(
            vector
        ).all():
            raise RiskBudgetCalculationError(
                "Budget vector contains non-finite values."
            )

        return vector

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
                "alias_count": len(
                    self.asset_budget_aliases
                ),
                "tolerance": self.tolerance,
            }

        except Exception as exc:
            return {
                "api_version": self.API_VERSION,
                "component": self.COMPONENT,
                "phase": self.PHASE,
                "healthy": False,
                "error": str(exc),
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
            "alias_count": len(
                self.asset_budget_aliases
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
            "asset_budget_aliases": dict(
                self.asset_budget_aliases
            ),
            "tolerance": float(
                self.tolerance
            ),
            "last_budget_resolution": dict(
                self.last_budget_resolution
            ),
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
        self.last_budget_resolution = {}


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
    Validate production risk-budget engine configuration and
    core invariants.
    """

    engine = RiskBudgetEngine()

    # --------------------------------------------------------------
    # Health
    # --------------------------------------------------------------

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

    # --------------------------------------------------------------
    # Canonical budget normalization
    # --------------------------------------------------------------

    for regime in engine.risk_budgets:
        configured_tickers = list(
            engine.risk_budgets[
                regime
            ].keys()
        )

        budgets = (
            engine.get_target_budgets(
                regime,
                configured_tickers,
            )
        )

        assert np.isclose(
            sum(
                budgets.values()
            ),
            1.0,
            atol=1e-6,
        )

    # --------------------------------------------------------------
    # Alias resolution
    # --------------------------------------------------------------

    for regime in engine.risk_budgets:
        configured = engine.risk_budgets[
            regime
        ]

        if (
            "SPY" in configured
            and "VEA" in configured
            and "VWO" in configured
        ):
            subset = (
                engine.get_target_budgets(
                    regime,
                    [
                        "SPY",
                        "EFA",
                        "EEM",
                    ],
                )
            )

            assert set(
                subset
            ) == {
                "SPY",
                "EFA",
                "EEM",
            }

            assert np.isclose(
                sum(
                    subset.values()
                ),
                1.0,
                atol=1e-6,
            )

            assert (
                engine.last_budget_resolution[
                    "resolution"
                ]["EFA"]["source_asset"]
                == "VEA"
            )

            assert (
                engine.last_budget_resolution[
                    "resolution"
                ]["EEM"]["source_asset"]
                == "VWO"
            )

    # --------------------------------------------------------------
    # Risk-contribution mathematical invariant
    # --------------------------------------------------------------

    covariance = np.array(
        [
            [0.04, 0.01],
            [0.01, 0.09],
        ],
        dtype=float,
    )

    weights = {
        "A": 0.60,
        "B": 0.40,
    }

    contributions = (
        engine.calculate_risk_contributions(
            weights,
            covariance,
            [
                "A",
                "B",
            ],
        )
    )

    vector = np.array(
        [
            0.60,
            0.40,
        ],
        dtype=float,
    )

    portfolio_variance = float(
        vector
        @ covariance
        @ vector
    )

    assert np.isclose(
        sum(
            contributions.values()
        ),
        portfolio_variance,
        atol=1e-10,
    )

    contribution_pct = (
        engine.calculate_risk_contribution_pct(
            contributions
        )
    )

    assert np.isclose(
        sum(
            contribution_pct.values()
        ),
        1.0,
        atol=1e-10,
    )

    # --------------------------------------------------------------
    # Budget vector
    # --------------------------------------------------------------

    for regime in engine.risk_budgets:
        tickers = list(
            engine.risk_budgets[
                regime
            ].keys()
        )

        vector = engine.budget_vector(
            regime,
            tickers,
        )

        assert vector.shape == (
            len(tickers),
        )

        assert np.isfinite(
            vector
        ).all()

        assert np.isclose(
            vector.sum(),
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