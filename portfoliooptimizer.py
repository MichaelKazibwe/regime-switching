"""
======================================================================
PORTFOLIO OPTIMIZER
======================================================================

Production portfolio orchestration engine.

Phase
-----
IV-B.1B

Purpose
-------
Production portfolio construction pipeline.

Pipeline
--------
    Macro Regime
        ->
    Risk Budget
        ->
    Baseline Risk-Budget Portfolio
        ->
    Expected Returns
        ->
    Black-Litterman
        ->
    Controlled BL Tilt
        ->
    Portfolio Constraints
        ->
    Volatility Targeting
        ->
    Regime Leverage Backstop
        ->
    Cash / Financing Accounting
        ->
    Risk Diagnostics
        ->
    Production Portfolio

Design Principles
-----------------
1. RiskBudgetEngine is authoritative for asset-level regime risk budgets.
2. PortfolioOptimizer does not duplicate risk-budget configuration.
3. RiskBudgetEngine is authoritative for risk-budget optimization.
4. Black-Litterman is a controlled overlay and cannot arbitrarily replace
   the regime portfolio.
5. PortfolioConstraints remains authoritative for position constraints.
6. VolatilityTargeting remains authoritative for volatility scaling.
7. Regime maximum leverage is independently enforced as a final hard
   production invariant.
8. Leveraged portfolios explicitly distinguish:
       - gross exposure
       - net exposure
       - cash
       - financing
9. Production invariants use explicit exceptions rather than Python
   assertions.
10. Public return keys from the previous production contract are retained.
11. Numerical inputs are validated before entering downstream engines.
12. Diagnostics are deterministic and suitable for regression testing.

Backward Compatibility
----------------------
The following public result keys are intentionally preserved:

    weights
    cash
    regime
    expected_returns
    expected_return_map
    forecasts
    risk_report
    volatility_diagnostics
    asset_order
    risk_budget
    baseline_weights
    baseline_weight_map
    bl_multipliers
    bl_multiplier_map
    bl_tilted_weights
    bl_tilted_weight_map
    constrained_weights
    constrained_weight_map
    constraint_cash
    gross_exposure
    target_volatility
    maximum_leverage
    weight_map

Additional production diagnostics:

    financing
    financing_weight
    net_exposure

======================================================================
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from blacklitterman import BlackLittermanModel
from core_constants import (
    REGIME_MAX_LEVERAGE,
    REGIME_RISK_BUDGETS,
    REGIME_VOL_TARGETS,
)
from expectedreturnforecaster import ExpectedReturnForecaster
from macroregime import PortfolioRegimeMapper, Regime
from riskcontributionanalyzer import RiskBudgetReport


# ======================================================================
# EXCEPTIONS
# ======================================================================


class PortfolioOptimizerError(Exception):
    """
    Base exception for production portfolio optimization errors.
    """


class PortfolioOptimizerConfigurationError(
    PortfolioOptimizerError
):
    """
    Raised when optimizer configuration is invalid.
    """


class PortfolioOptimizerCalculationError(
    PortfolioOptimizerError
):
    """
    Raised when portfolio optimization or validation fails.
    """


# ======================================================================
# PORTFOLIO OPTIMIZER
# ======================================================================


class PortfolioOptimizer:
    """
    Production portfolio orchestration engine.

    The optimizer deliberately separates policy from mechanics.

    Risk-budget policy
    ------------------
    RiskBudgetEngine

    Position constraints
    --------------------
    PortfolioConstraints

    Volatility targeting
    --------------------
    VolatilityTargeting

    Expected returns
    ----------------
    ExpectedReturnForecaster

    Bayesian overlay
    -----------------
    BlackLittermanModel

    Final portfolio construction
    ----------------------------
    PortfolioOptimizer

    The optimizer does not independently own the canonical asset-level
    risk-budget configuration.
    """

    API_VERSION = "2.1.0"
    COMPONENT = "PortfolioOptimizer"
    PHASE = "IV-B.1B"

    DEFAULT_BL_TILT_STRENGTH = 0.25
    DEFAULT_BL_TILT_FLOOR = 0.50
    DEFAULT_BL_TILT_CAP = 1.50

    DEFAULT_TOLERANCE = 1e-8

    COVARIANCE_NEGATIVE_EIGENVALUE_TOLERANCE = 1e-10
    COVARIANCE_REGULARIZATION = 1e-12
    VARIANCE_NEGATIVE_TOLERANCE = 1e-12

    LEVERAGE_TOLERANCE = 1e-8
    EXPOSURE_TOLERANCE = 1e-10

    # ==================================================================
    # CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        risk_budget_engine,
        constraints,
        vol_target_engine,
        forecast_engine=None,
        black_litterman=None,
        bl_tilt_strength: float = DEFAULT_BL_TILT_STRENGTH,
        bl_tilt_floor: float = DEFAULT_BL_TILT_FLOOR,
        bl_tilt_cap: float = DEFAULT_BL_TILT_CAP,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        """
        Initialize the production optimizer.
        """

        if risk_budget_engine is None:
            raise PortfolioOptimizerConfigurationError(
                "risk_budget_engine cannot be None."
            )

        if constraints is None:
            raise PortfolioOptimizerConfigurationError(
                "constraints cannot be None."
            )

        if vol_target_engine is None:
            raise PortfolioOptimizerConfigurationError(
                "vol_target_engine cannot be None. "
                "Production PortfolioOptimizer requires an "
                "authoritative VolatilityTargeting engine."
            )

        required_dependencies = {
            "risk_budget_engine.get_target_budgets": (
                hasattr(
                    risk_budget_engine,
                    "get_target_budgets",
                )
            ),
            "risk_budget_engine.optimize": (
                hasattr(
                    risk_budget_engine,
                    "optimize",
                )
            ),
            "constraints.enforce": (
                hasattr(
                    constraints,
                    "enforce",
                )
            ),
            "vol_target_engine.scale_weights": (
                hasattr(
                    vol_target_engine,
                    "scale_weights",
                )
            ),
        }

        missing = [
            name
            for name, available
            in required_dependencies.items()
            if not available
        ]

        if missing:
            raise PortfolioOptimizerConfigurationError(
                "PortfolioOptimizer dependencies are missing "
                f"required interfaces: {missing}"
            )

        self.risk_budget_engine = risk_budget_engine
        self.constraints = constraints
        self.vol_target_engine = vol_target_engine

        self.forecast_engine = (
            forecast_engine
            if forecast_engine is not None
            else ExpectedReturnForecaster()
        )

        self.black_litterman = (
            black_litterman
            if black_litterman is not None
            else BlackLittermanModel()
        )

        self.bl_tilt_strength = float(
            bl_tilt_strength
        )

        self.bl_tilt_floor = float(
            bl_tilt_floor
        )

        self.bl_tilt_cap = float(
            bl_tilt_cap
        )

        self.tolerance = float(
            tolerance
        )

        self._validate_configuration()

        self._reset_state()

    # ==================================================================
    # STATE
    # ==================================================================

    def _reset_state(
        self,
    ) -> None:
        """
        Reset calculation state.
        """

        self.last_forecasts = None
        self.last_posterior_returns = None
        self.last_regime = None
        self.last_volatility_diagnostics = None
        self.last_weights = None
        self.last_cash = None
        self.last_financing = None
        self.last_net_exposure = None
        self.last_gross_exposure = None
        self.last_risk_budget = None
        self.last_baseline_weights = None
        self.last_bl_multipliers = None
        self.last_bl_tilted_weights = None
        self.last_constraint_result = None

    # ==================================================================
    # CONFIGURATION VALIDATION
    # ==================================================================

    def _validate_configuration(
        self,
    ) -> None:
        """
        Validate optimizer configuration.
        """

        if (
            not np.isfinite(
                self.bl_tilt_strength
            )
            or not 0.0
            <= self.bl_tilt_strength
            <= 1.0
        ):
            raise PortfolioOptimizerConfigurationError(
                "bl_tilt_strength must be finite and between 0 and 1."
            )

        if (
            not np.isfinite(
                self.bl_tilt_floor
            )
            or self.bl_tilt_floor <= 0.0
        ):
            raise PortfolioOptimizerConfigurationError(
                "bl_tilt_floor must be positive and finite."
            )

        if (
            not np.isfinite(
                self.bl_tilt_cap
            )
            or self.bl_tilt_cap <= 0.0
        ):
            raise PortfolioOptimizerConfigurationError(
                "bl_tilt_cap must be positive and finite."
            )

        if (
            self.bl_tilt_floor
            > self.bl_tilt_cap
        ):
            raise PortfolioOptimizerConfigurationError(
                "bl_tilt_floor cannot exceed bl_tilt_cap."
            )

        if (
            not np.isfinite(
                self.tolerance
            )
            or self.tolerance <= 0.0
        ):
            raise PortfolioOptimizerConfigurationError(
                "tolerance must be positive and finite."
            )

    # ==================================================================
    # REGIME NORMALIZATION
    # ==================================================================

    @staticmethod
    def _normalize_regime(
        regime,
    ) -> str:
        """
        Normalize a supported regime to the canonical configuration key.

        The optimizer accepts:

            - canonical string keys
            - macro Regime enum values
            - strings representing supported macro regimes

        The final value must correspond to a configured portfolio regime.
        """

        if regime is None:
            raise PortfolioOptimizerConfigurationError(
                "regime cannot be None."
            )

        if isinstance(
            regime,
            Regime,
        ):
            try:
                mapped = (
                    PortfolioRegimeMapper.map_regime(
                        regime
                    )
                )
            except Exception as exc:
                raise PortfolioOptimizerConfigurationError(
                    f"Unable to map macro regime '{regime}'."
                ) from exc

            normalized = str(
                mapped
            ).strip().lower()

        elif isinstance(
            regime,
            str,
        ):
            normalized = (
                regime.strip().lower()
            )

            if normalized in {
                "expansion",
                "recovery",
                "slowdown",
                "recession",
            }:
                try:
                    normalized = str(
                        PortfolioRegimeMapper.map_regime(
                            Regime(normalized)
                        )
                    ).strip().lower()
                except Exception:
                    # If the string itself is already a canonical
                    # portfolio regime, the configuration check below
                    # will determine whether it is valid.
                    pass

        else:
            value = getattr(
                regime,
                "value",
                None,
            )

            if value is None:
                raise PortfolioOptimizerConfigurationError(
                    "Unsupported regime type: "
                    f"{type(regime)}"
                )

            normalized = str(
                value
            ).strip().lower()

        configured_keys = {
            str(key).strip().lower(): str(key)
            for key in REGIME_RISK_BUDGETS
        }

        if normalized in configured_keys:
            return configured_keys[normalized]

        # Also permit the RiskBudgetEngine to own the canonical regime
        # namespace when it exposes a custom configuration.
        raise PortfolioOptimizerConfigurationError(
            f"Unknown regime '{normalized}'. Expected one of "
            f"{list(REGIME_RISK_BUDGETS.keys())} or a supported "
            "macro regime."
        )

    # ==================================================================
    # ASSET VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_asset_order(
        asset_order,
    ) -> tuple[str, ...]:
        """
        Validate and normalize asset order.
        """

        if asset_order is None:
            raise ValueError(
                "asset_order cannot be None."
            )

        try:
            if len(asset_order) == 0:
                raise ValueError(
                    "asset_order cannot be empty."
                )
        except TypeError as exc:
            raise ValueError(
                "asset_order must be a sized iterable of asset identifiers."
            ) from exc

        normalized = tuple(
            str(asset).strip()
            for asset in asset_order
        )

        if any(
            not asset
            for asset in normalized
        ):
            raise ValueError(
                "asset_order contains an empty asset identifier."
            )

        if len(
            set(normalized)
        ) != len(normalized):
            raise ValueError(
                "asset_order contains duplicate assets."
            )

        return normalized

    # ==================================================================
    # COVARIANCE VALIDATION
    # ==================================================================

    @classmethod
    def _validate_covariance(
        cls,
        covariance,
        asset_order,
    ) -> np.ndarray:
        """
        Validate, symmetrize and safely regularize covariance.
        """

        try:
            covariance = np.asarray(
                covariance,
                dtype=float,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Covariance could not be converted to a numeric array."
            ) from exc

        if covariance.ndim != 2:
            raise ValueError(
                "Covariance must be a 2-dimensional matrix."
            )

        if (
            covariance.shape[0]
            != covariance.shape[1]
        ):
            raise ValueError(
                "Covariance matrix must be square."
            )

        if (
            covariance.shape[0]
            != len(asset_order)
        ):
            raise ValueError(
                "Asset order length "
                f"{len(asset_order)} does not match covariance "
                f"dimension {covariance.shape[0]}."
            )

        if not np.isfinite(
            covariance
        ).all():
            raise ValueError(
                "Covariance contains non-finite values."
            )

        covariance = (
            covariance
            + covariance.T
        ) / 2.0

        try:
            eigenvalues = np.linalg.eigvalsh(
                covariance
            )
        except np.linalg.LinAlgError as exc:
            raise ValueError(
                "Unable to determine covariance eigenvalues."
            ) from exc

        if eigenvalues.size == 0:
            raise ValueError(
                "Covariance matrix cannot be empty."
            )

        minimum_eigenvalue = float(
            eigenvalues.min()
        )

        if (
            minimum_eigenvalue
            < -cls.COVARIANCE_NEGATIVE_EIGENVALUE_TOLERANCE
        ):
            raise ValueError(
                "Covariance matrix is not positive semidefinite. "
                f"Minimum eigenvalue={minimum_eigenvalue:.6e}."
            )

        if minimum_eigenvalue < 0.0:
            covariance = (
                covariance
                + np.eye(
                    covariance.shape[0]
                )
                * cls.COVARIANCE_REGULARIZATION
            )

        elif minimum_eigenvalue < 1e-12:
            covariance = (
                covariance
                + np.eye(
                    covariance.shape[0]
                )
                * cls.COVARIANCE_REGULARIZATION
            )

        return covariance

    # ==================================================================
    # VECTOR VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_risk_budgets(
        risk_budget,
        asset_order,
    ) -> np.ndarray:
        """
        Validate and normalize target risk budgets.
        """

        try:
            risk_budget = np.asarray(
                risk_budget,
                dtype=float,
            ).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Risk budgets could not be converted to a numeric vector."
            ) from exc

        if risk_budget.shape != (
            len(asset_order),
        ):
            raise ValueError(
                "Risk budget shape "
                f"{risk_budget.shape} does not match asset universe "
                f"size {len(asset_order)}."
            )

        if not np.isfinite(
            risk_budget
        ).all():
            raise ValueError(
                "Risk budgets contain non-finite values."
            )

        if np.any(
            risk_budget < -1e-12
        ):
            raise ValueError(
                "Risk budgets cannot be negative."
            )

        risk_budget = np.maximum(
            risk_budget,
            0.0,
        )

        total = float(
            risk_budget.sum()
        )

        if (
            not np.isfinite(total)
            or total <= 0.0
        ):
            raise ValueError(
                "Risk budgets must have a positive total."
            )

        risk_budget /= total

        if not np.isclose(
            risk_budget.sum(),
            1.0,
            atol=1e-8,
        ):
            raise ValueError(
                "Normalized risk budgets do not sum to one."
            )

        return risk_budget

    @staticmethod
    def _validate_return_vector(
        values,
        asset_order,
        name: str,
    ) -> np.ndarray:
        """
        Validate an asset-aligned return vector.
        """

        try:
            values = np.asarray(
                values,
                dtype=float,
            ).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{name} could not be converted to a numeric vector."
            ) from exc

        if values.size != len(
            asset_order
        ):
            raise ValueError(
                f"{name} vector length {values.size} "
                "does not match asset universe "
                f"size {len(asset_order)}."
            )

        if not np.isfinite(
            values
        ).all():
            raise ValueError(
                f"{name} contains non-finite values."
            )

        return values

    # ==================================================================
    # RISK-BUDGET RESOLUTION
    # ==================================================================

    def _resolve_target_budgets(
        self,
        regime: str,
        asset_order: tuple[str, ...],
    ) -> dict[str, float]:
        """
        Resolve target budgets through RiskBudgetEngine.

        RiskBudgetEngine owns asset-level risk-budget policy.

        PortfolioOptimizer deliberately does not inspect individual
        assets in the canonical production risk-budget configuration.
        """

        try:
            target_budgets = (
                self.risk_budget_engine.get_target_budgets(
                    regime,
                    list(asset_order),
                )
            )
        except Exception as exc:
            raise PortfolioOptimizerCalculationError(
                "Risk-budget resolution failed for "
                f"regime '{regime}' and assets "
                f"{list(asset_order)}: {exc}"
            ) from exc

        if not isinstance(
            target_budgets,
            dict,
        ):
            raise PortfolioOptimizerCalculationError(
                "RiskBudgetEngine.get_target_budgets() "
                "must return a dictionary."
            )

        missing_assets = [
            asset
            for asset in asset_order
            if asset not in target_budgets
        ]

        if missing_assets:
            raise PortfolioOptimizerCalculationError(
                "Risk budget engine did not provide budgets "
                f"for assets: {missing_assets}"
            )

        try:
            values = np.asarray(
                [
                    target_budgets[asset]
                    for asset in asset_order
                ],
                dtype=float,
            )
        except (TypeError, ValueError) as exc:
            raise PortfolioOptimizerCalculationError(
                "RiskBudgetEngine returned non-numeric "
                "target budgets."
            ) from exc

        if not np.isfinite(
            values
        ).all():
            raise PortfolioOptimizerCalculationError(
                "Risk-budget engine returned "
                "non-finite target budgets."
            )

        if np.any(
            values < -self.tolerance
        ):
            raise PortfolioOptimizerCalculationError(
                "Risk-budget engine returned "
                "negative target budgets."
            )

        total = float(
            values.sum()
        )

        if (
            not np.isfinite(total)
            or total <= self.tolerance
        ):
            raise PortfolioOptimizerCalculationError(
                "Risk-budget engine returned "
                "zero or invalid total target budget."
            )

        values /= total

        return {
            asset: float(
                values[index]
            )
            for index, asset
            in enumerate(asset_order)
        }

    # ==================================================================
    # BASELINE RISK-BUDGET PORTFOLIO
    # ==================================================================

    def _build_baseline_weights(
        self,
        covariance: np.ndarray,
        risk_budget: np.ndarray,
    ) -> np.ndarray:
        """
        Build the baseline portfolio from the authoritative
        RiskBudgetEngine.
        """

        try:
            weights = (
                self.risk_budget_engine.optimize(
                    covariance,
                    risk_budget,
                )
            )
        except Exception as exc:
            raise PortfolioOptimizerCalculationError(
                "Risk-budget optimization failed: "
                f"{exc}"
            ) from exc

        if weights is None:
            raise PortfolioOptimizerCalculationError(
                "Risk-budget optimizer returned None."
            )

        try:
            weights = np.asarray(
                weights,
                dtype=float,
            ).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise PortfolioOptimizerCalculationError(
                "Risk-budget optimizer returned "
                "non-numeric weights."
            ) from exc

        if weights.size != (
            risk_budget.size
        ):
            raise PortfolioOptimizerCalculationError(
                "Risk-budget optimizer returned "
                f"{weights.size} weights; expected "
                f"{risk_budget.size}."
            )

        if not np.isfinite(
            weights
        ).all():
            raise PortfolioOptimizerCalculationError(
                "Risk-budget optimizer returned "
                "non-finite weights."
            )

        if np.any(
            weights < -self.tolerance
        ):
            raise PortfolioOptimizerCalculationError(
                "Risk-budget optimizer returned "
                "negative weights."
            )

        weights = np.maximum(
            weights,
            0.0,
        )

        total = float(
            weights.sum()
        )

        if (
            not np.isfinite(total)
            or total <= self.tolerance
        ):
            raise PortfolioOptimizerCalculationError(
                "Risk-budget optimizer returned "
                "zero total allocation."
            )

        weights /= total

        if not np.isclose(
            weights.sum(),
            1.0,
            atol=1e-8,
        ):
            raise PortfolioOptimizerCalculationError(
                "Baseline risk-budget weights do not sum to one."
            )

        return weights

    # ==================================================================
    # BLACK-LITTERMAN
    # ==================================================================

    @staticmethod
    def _normalize_signal(
        posterior_returns: np.ndarray,
    ) -> np.ndarray:
        """
        Normalize posterior returns to [-1, 1].
        """

        posterior_returns = np.asarray(
            posterior_returns,
            dtype=float,
        ).reshape(-1)

        if posterior_returns.size == 0:
            return np.zeros_like(
                posterior_returns
            )

        if not np.isfinite(
            posterior_returns
        ).all():
            raise PortfolioOptimizerCalculationError(
                "Posterior returns contain non-finite values."
            )

        center = float(
            np.mean(
                posterior_returns
            )
        )

        centered = (
            posterior_returns
            - center
        )

        scale = float(
            np.max(
                np.abs(
                    centered
                )
            )
        )

        if (
            not np.isfinite(scale)
            or scale <= 1e-14
        ):
            return np.zeros_like(
                posterior_returns
            )

        return np.clip(
            centered / scale,
            -1.0,
            1.0,
        )

    def _apply_black_litterman_tilt(
        self,
        baseline_weights: np.ndarray,
        posterior_returns: Optional[
            np.ndarray
        ],
    ) -> tuple[
        np.ndarray,
        np.ndarray,
    ]:
        """
        Apply a controlled BL tilt around baseline weights.
        """

        baseline_weights = np.asarray(
            baseline_weights,
            dtype=float,
        ).reshape(-1)

        if not np.isfinite(
            baseline_weights
        ).all():
            raise PortfolioOptimizerCalculationError(
                "Baseline weights contain non-finite values."
            )

        if np.any(
            baseline_weights < -self.tolerance
        ):
            raise PortfolioOptimizerCalculationError(
                "Baseline weights contain negative values."
            )

        if posterior_returns is None:
            return (
                baseline_weights.copy(),
                np.ones_like(
                    baseline_weights
                ),
            )

        posterior_returns = np.asarray(
            posterior_returns,
            dtype=float,
        ).reshape(-1)

        if (
            posterior_returns.size
            != baseline_weights.size
        ):
            raise PortfolioOptimizerCalculationError(
                "Posterior-return vector and baseline portfolio "
                "have different dimensions."
            )

        if not np.isfinite(
            posterior_returns
        ).all():
            raise PortfolioOptimizerCalculationError(
                "Cannot apply BL tilt to "
                "non-finite posterior returns."
            )

        signal = self._normalize_signal(
            posterior_returns
        )

        multipliers = np.clip(
            1.0
            + self.bl_tilt_strength * signal,
            self.bl_tilt_floor,
            self.bl_tilt_cap,
        )

        tilted_weights = (
            baseline_weights
            * multipliers
        )

        total = float(
            tilted_weights.sum()
        )

        if (
            not np.isfinite(total)
            or total <= self.tolerance
        ):
            raise PortfolioOptimizerCalculationError(
                "Black-Litterman tilt produced "
                "an invalid total allocation."
            )

        tilted_weights /= total

        if not np.isfinite(
            tilted_weights
        ).all():
            raise PortfolioOptimizerCalculationError(
                "Black-Litterman tilted weights contain "
                "non-finite values."
            )

        if np.any(
            tilted_weights < -self.tolerance
        ):
            raise PortfolioOptimizerCalculationError(
                "Black-Litterman tilted weights contain "
                "negative values."
            )

        return (
            tilted_weights,
            multipliers,
        )

    # ==================================================================
    # FORECAST + BLACK-LITTERMAN
    # ==================================================================

    def _generate_return_overlay(
        self,
        covariance: np.ndarray,
        asset_order: tuple[str, ...],
        prices: Any,
    ) -> Optional[np.ndarray]:
        """
        Generate posterior returns when price data is available.
        """

        self.last_forecasts = None
        self.last_posterior_returns = None

        if prices is None:
            return None

        if self.forecast_engine is None:
            return None

        if self.black_litterman is None:
            return None

        try:
            forecasts = (
                self.forecast_engine.forecast(
                    prices
                )
            )
        except Exception as exc:
            raise PortfolioOptimizerCalculationError(
                "Expected-return forecasting failed: "
                f"{exc}"
            ) from exc

        if forecasts is None:
            raise PortfolioOptimizerCalculationError(
                "Expected-return forecaster returned None."
            )

        if not hasattr(
            forecasts,
            "values",
        ):
            raise TypeError(
                "Expected-return forecasts must expose "
                "a 'values' attribute."
            )

        forecast_values = (
            self._validate_return_vector(
                forecasts.values,
                asset_order,
                "Expected-return forecast",
            )
        )

        self.last_forecasts = (
            forecasts.copy()
            if hasattr(
                forecasts,
                "copy",
            )
            else forecasts
        )

        # Preserve the existing BL market-prior contract for backward
        # compatibility. The regime risk-budget portfolio remains the
        # portfolio-construction baseline; this vector is the BL prior.
        market_weights = (
            np.ones(
                len(asset_order),
                dtype=float,
            )
            / float(
                len(asset_order)
            )
        )

        try:
            posterior_returns = (
                self.black_litterman.posterior_returns(
                    covariance,
                    market_weights,
                    forecast_values,
                )
            )
        except Exception as exc:
            raise PortfolioOptimizerCalculationError(
                "Black-Litterman posterior-return calculation failed: "
                f"{exc}"
            ) from exc

        posterior_returns = (
            self._validate_return_vector(
                posterior_returns,
                asset_order,
                "Black-Litterman posterior return",
            )
        )

        self.last_posterior_returns = (
            posterior_returns.copy()
        )

        return posterior_returns

    # ==================================================================
    # CONSTRAINTS
    # ==================================================================

    def _apply_constraints(
        self,
        weights: np.ndarray,
        asset_order: tuple[str, ...],
    ) -> tuple[
        np.ndarray,
        float,
        dict[str, Any],
    ]:
        """
        Apply PortfolioConstraints.
        """

        try:
            result = (
                self.constraints.enforce(
                    weights
                )
            )
        except Exception as exc:
            raise PortfolioOptimizerCalculationError(
                "Portfolio constraint enforcement failed: "
                f"{exc}"
            ) from exc

        if not isinstance(
            result,
            dict,
        ):
            raise TypeError(
                "Portfolio constraints must return a dictionary."
            )

        if "weights" not in result:
            raise ValueError(
                "Portfolio constraints result does not contain "
                "'weights'."
            )

        if "cash" not in result:
            raise ValueError(
                "Portfolio constraints result does not contain "
                "'cash'."
            )

        constrained_weights = np.asarray(
            result["weights"],
            dtype=float,
        ).reshape(-1)

        try:
            constraint_cash = float(
                result["cash"]
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Portfolio constraints returned invalid cash."
            ) from exc

        if (
            constrained_weights.size
            != len(asset_order)
        ):
            raise ValueError(
                "Constraint engine returned "
                f"{constrained_weights.size} weights; expected "
                f"{len(asset_order)}."
            )

        if not np.isfinite(
            constrained_weights
        ).all():
            raise ValueError(
                "Constraint engine returned "
                "non-finite weights."
            )

        if np.any(
            constrained_weights
            < -self.tolerance
        ):
            raise ValueError(
                "Constraint engine returned "
                "negative weights."
            )

        if not np.isfinite(
            constraint_cash
        ):
            raise ValueError(
                "Constraint engine returned "
                "invalid cash."
            )

        if (
            constraint_cash
            < -self.tolerance
        ):
            raise ValueError(
                "Constraint engine returned "
                "negative cash."
            )

        constrained_weights = np.maximum(
            constrained_weights,
            0.0,
        )

        self.last_constraint_result = dict(
            result
        )

        return (
            constrained_weights,
            max(
                0.0,
                constraint_cash,
            ),
            dict(result),
        )

    # ==================================================================
    # VOLATILITY TARGETING
    # ==================================================================

    def _apply_volatility_targeting(
        self,
        weights: np.ndarray,
        covariance: np.ndarray,
        target_vol: float,
        max_leverage: float,
    ) -> tuple[
        np.ndarray,
        Any,
    ]:
        """
        Apply authoritative volatility targeting.
        """

        try:
            scaled_weights = (
                self.vol_target_engine.scale_weights(
                    weights,
                    covariance,
                    target_vol,
                    max_leverage=max_leverage,
                )
            )
        except Exception as exc:
            raise PortfolioOptimizerCalculationError(
                "Volatility-targeting engine failed: "
                f"{exc}"
            ) from exc

        if scaled_weights is None:
            raise PortfolioOptimizerCalculationError(
                "Volatility-targeting engine returned None."
            )

        scaled_weights = np.asarray(
            scaled_weights,
            dtype=float,
        ).reshape(-1)

        if (
            scaled_weights.size
            != weights.size
        ):
            raise PortfolioOptimizerCalculationError(
                "Volatility-targeting engine returned "
                f"{scaled_weights.size} weights; expected "
                f"{weights.size}."
            )

        if not np.isfinite(
            scaled_weights
        ).all():
            raise PortfolioOptimizerCalculationError(
                "Volatility-targeting engine returned "
                "non-finite weights."
            )

        if np.any(
            scaled_weights
            < -self.tolerance
        ):
            raise PortfolioOptimizerCalculationError(
                "Volatility-targeting engine returned "
                "negative weights."
            )

        scaled_weights = np.maximum(
            scaled_weights,
            0.0,
        )

        engine_result = None

        if hasattr(
            self.vol_target_engine,
            "get_last_result",
        ):
            try:
                engine_result = (
                    self.vol_target_engine.get_last_result()
                )
            except Exception:
                engine_result = None

        elif hasattr(
            self.vol_target_engine,
            "last_result",
        ):
            engine_result = (
                self.vol_target_engine.last_result
            )

        return (
            scaled_weights,
            engine_result,
        )

    # ==================================================================
    # LEVERAGE BACKSTOP
    # ==================================================================

    def _enforce_leverage_backstop(
        self,
        weights: np.ndarray,
        max_leverage: float,
    ) -> tuple[
        np.ndarray,
        bool,
    ]:
        """
        Enforce the final hard gross-exposure ceiling.

        This method never introduces short positions and therefore only
        scales an already-valid long-only portfolio downward when required.
        """

        weights = np.asarray(
            weights,
            dtype=float,
        ).reshape(-1)

        if not np.isfinite(
            weights
        ).all():
            raise PortfolioOptimizerCalculationError(
                "Weights contain non-finite values before "
                "leverage enforcement."
            )

        if np.any(
            weights < -self.tolerance
        ):
            raise PortfolioOptimizerCalculationError(
                "Weights contain negative values before "
                "leverage enforcement."
            )

        if (
            not np.isfinite(max_leverage)
            or max_leverage <= 0.0
        ):
            raise PortfolioOptimizerCalculationError(
                "Maximum leverage must be positive and finite."
            )

        weights = np.maximum(
            weights,
            0.0,
        )

        gross = float(
            np.sum(
                np.abs(weights)
            )
        )

        if not np.isfinite(
            gross
        ):
            raise PortfolioOptimizerCalculationError(
                "Gross exposure became non-finite."
            )

        binding = False

        if (
            gross
            > max_leverage
            + self.LEVERAGE_TOLERANCE
        ):
            if gross <= self.EXPOSURE_TOLERANCE:
                raise PortfolioOptimizerCalculationError(
                    "Invalid gross exposure during leverage enforcement."
                )

            weights = (
                weights
                * (
                    max_leverage
                    / gross
                )
            )

            binding = True

        final_gross = float(
            np.sum(
                np.abs(weights)
            )
        )

        if (
            not np.isfinite(final_gross)
        ):
            raise PortfolioOptimizerCalculationError(
                "Final gross exposure became non-finite."
            )

        if (
            final_gross
            > max_leverage
            + self.LEVERAGE_TOLERANCE
        ):
            raise PortfolioOptimizerCalculationError(
                "Portfolio remains above maximum regime leverage "
                "after enforcement. "
                f"Gross exposure={final_gross:.12f}; "
                f"maximum leverage={max_leverage:.12f}."
            )

        return (
            weights,
            binding,
        )

    # ==================================================================
    # EXPOSURE / CASH / FINANCING ACCOUNTING
    # ==================================================================

    @staticmethod
    def _calculate_exposure_metrics(
        weights: np.ndarray,
    ) -> dict[str, float]:
        """
        Calculate production exposure accounting.

        For a long-only portfolio:

            gross exposure = sum(abs(weights))
            net exposure   = sum(weights)

        Cash represents uninvested capital when gross exposure is below 1.

        Financing represents borrowed capital when gross exposure exceeds 1.

        Thus:

            gross + cash - financing = 1

        and:

            financing = max(gross - 1, 0)
            cash      = max(1 - gross, 0)
        """

        weights = np.asarray(
            weights,
            dtype=float,
        ).reshape(-1)

        if not np.isfinite(
            weights
        ).all():
            raise PortfolioOptimizerCalculationError(
                "Cannot calculate exposure metrics from "
                "non-finite weights."
            )

        gross_exposure = float(
            np.sum(
                np.abs(weights)
            )
        )

        net_exposure = float(
            np.sum(weights)
        )

        if (
            not np.isfinite(gross_exposure)
            or not np.isfinite(net_exposure)
        ):
            raise PortfolioOptimizerCalculationError(
                "Portfolio exposure became non-finite."
            )

        cash_weight = max(
            0.0,
            1.0 - gross_exposure,
        )

        financing_weight = max(
            0.0,
            gross_exposure - 1.0,
        )

        accounting_total = (
            gross_exposure
            + cash_weight
            - financing_weight
        )

        if not np.isclose(
            accounting_total,
            1.0,
            atol=1e-8,
        ):
            raise PortfolioOptimizerCalculationError(
                "Portfolio exposure accounting failed. "
                f"Gross={gross_exposure:.12f}, "
                f"Cash={cash_weight:.12f}, "
                f"Financing={financing_weight:.12f}, "
                f"Accounting total={accounting_total:.12f}."
            )

        return {
            "gross_exposure": gross_exposure,
            "net_exposure": net_exposure,
            "cash_weight": cash_weight,
            "financing_weight": financing_weight,
            "financing": financing_weight,
        }

    # ==================================================================
    # PORTFOLIO VOLATILITY
    # ==================================================================

    @staticmethod
    def _calculate_portfolio_volatility(
        weights: np.ndarray,
        covariance: np.ndarray,
    ) -> float:
        """
        Calculate portfolio volatility.
        """

        variance = float(
            weights
            @ covariance
            @ weights
        )

        if not np.isfinite(
            variance
        ):
            raise PortfolioOptimizerCalculationError(
                "Portfolio variance is non-finite."
            )

        if variance < 0.0:
            if (
                variance
                > -PortfolioOptimizer.VARIANCE_NEGATIVE_TOLERANCE
            ):
                variance = 0.0
            else:
                raise PortfolioOptimizerCalculationError(
                    "Portfolio variance is materially negative: "
                    f"{variance}."
                )

        volatility = float(
            np.sqrt(variance)
        )

        if not np.isfinite(
            volatility
        ):
            raise PortfolioOptimizerCalculationError(
                "Portfolio volatility is non-finite."
            )

        return volatility

    # ==================================================================
    # VOLATILITY DIAGNOSTICS
    # ==================================================================

    def _build_volatility_diagnostics(
        self,
        engine_result,
        target_vol: float,
        max_leverage: float,
        final_weights: np.ndarray,
        final_volatility: float,
        backstop_binding: bool,
    ) -> dict[str, Any]:
        """
        Build deterministic volatility and exposure diagnostics.
        """

        exposure = self._calculate_exposure_metrics(
            final_weights
        )

        final_gross = exposure[
            "gross_exposure"
        ]

        cash_weight = exposure[
            "cash_weight"
        ]

        financing_weight = exposure[
            "financing_weight"
        ]

        net_exposure = exposure[
            "net_exposure"
        ]

        volatility_error = (
            final_volatility
            - target_vol
        )

        volatility_shortfall = max(
            0.0,
            target_vol
            - final_volatility,
        )

        diagnostics: dict[str, Any] = {
            "status": (
                "ENGINE"
                if engine_result is not None
                else "CALCULATED"
            ),
            "engine_result": engine_result,
            "original_volatility": None,
            "target_volatility": float(
                target_vol
            ),
            "final_volatility": float(
                final_volatility
            ),
            "volatility_error": float(
                volatility_error
            ),
            "volatility_shortfall": float(
                volatility_shortfall
            ),
            "target_achieved": bool(
                np.isclose(
                    final_volatility,
                    target_vol,
                    rtol=1e-6,
                    atol=1e-8,
                )
            ),
            "maximum_leverage": float(
                max_leverage
            ),
            "gross_exposure": float(
                final_gross
            ),
            "net_exposure": float(
                net_exposure
            ),
            "cash_weight": float(
                cash_weight
            ),
            "financing_weight": float(
                financing_weight
            ),
            "financing": float(
                financing_weight
            ),
            "leverage_backstop_binding": bool(
                backstop_binding
            ),
            "leverage_binding": bool(
                backstop_binding
            ),
            "required_leverage": None,
            "exposure_accounting": {
                "gross_plus_cash_minus_financing": float(
                    final_gross
                    + cash_weight
                    - financing_weight
                ),
                "accounting_valid": True,
            },
        }

        if engine_result is not None:
            if hasattr(
                engine_result,
                "original_volatility",
            ):
                diagnostics[
                    "original_volatility"
                ] = float(
                    engine_result.original_volatility
                )

            if hasattr(
                engine_result,
                "scale_factor",
            ):
                diagnostics[
                    "scale_factor"
                ] = float(
                    engine_result.scale_factor
                )

            if hasattr(
                engine_result,
                "required_leverage",
            ):
                diagnostics[
                    "required_leverage"
                ] = float(
                    engine_result.required_leverage
                )

            if hasattr(
                engine_result,
                "target_achieved",
            ):
                diagnostics[
                    "target_achieved"
                ] = bool(
                    engine_result.target_achieved
                )

            if hasattr(
                engine_result,
                "leverage_binding",
            ):
                diagnostics[
                    "leverage_binding"
                ] = bool(
                    engine_result.leverage_binding
                )

            if hasattr(
                engine_result,
                "diagnostics",
            ):
                engine_diagnostics = (
                    engine_result.diagnostics
                )

                if isinstance(
                    engine_diagnostics,
                    dict,
                ):
                    diagnostics[
                        "engine_diagnostics"
                    ] = dict(
                        engine_diagnostics
                    )

        return diagnostics

    # ==================================================================
    # REGIME CONFIGURATION
    # ==================================================================

    def _resolve_regime_parameters(
        self,
        normalized_regime: str,
    ) -> tuple[float, float]:
        """
        Resolve volatility target and maximum leverage.

        Risk-budget policy is deliberately NOT resolved here.
        """

        configured_vol_keys = {
            str(key).strip().lower(): key
            for key in REGIME_VOL_TARGETS
        }

        configured_leverage_keys = {
            str(key).strip().lower(): key
            for key in REGIME_MAX_LEVERAGE
        }

        regime_key = normalized_regime.strip().lower()

        if regime_key not in configured_vol_keys:
            raise PortfolioOptimizerConfigurationError(
                "No volatility target configured for regime "
                f"'{normalized_regime}'."
            )

        if regime_key not in configured_leverage_keys:
            raise PortfolioOptimizerConfigurationError(
                "No maximum leverage configured for regime "
                f"'{normalized_regime}'."
            )

        target_vol = float(
            REGIME_VOL_TARGETS[
                configured_vol_keys[regime_key]
            ]
        )

        max_leverage = float(
            REGIME_MAX_LEVERAGE[
                configured_leverage_keys[regime_key]
            ]
        )

        if (
            not np.isfinite(target_vol)
            or target_vol <= 0.0
        ):
            raise PortfolioOptimizerConfigurationError(
                "Regime target volatility must be "
                "positive and finite."
            )

        if (
            not np.isfinite(max_leverage)
            or max_leverage <= 0.0
        ):
            raise PortfolioOptimizerConfigurationError(
                "Regime maximum leverage must be "
                "positive and finite."
            )

        return (
            target_vol,
            max_leverage,
        )

    # ==================================================================
    # FINAL INVARIANTS
    # ==================================================================

    def _validate_final_portfolio(
        self,
        weights: np.ndarray,
        max_leverage: float,
        cash_weight: float,
        financing_weight: float,
        final_gross_exposure: float,
        final_volatility: float,
    ) -> None:
        """
        Enforce final production invariants explicitly.

        No Python ``assert`` statements are used here so these checks
        remain active even under ``python3 -O``.
        """

        if not np.isfinite(
            weights
        ).all():
            raise PortfolioOptimizerCalculationError(
                "Final weights contain non-finite values."
            )

        if np.any(
            weights < -self.tolerance
        ):
            raise PortfolioOptimizerCalculationError(
                "Final weights contain negative values."
            )

        if not np.isfinite(
            cash_weight
        ):
            raise PortfolioOptimizerCalculationError(
                "Final cash weight is non-finite."
            )

        if (
            not np.isfinite(
                financing_weight
            )
            or financing_weight < -self.tolerance
        ):
            raise PortfolioOptimizerCalculationError(
                "Final financing weight is invalid."
            )

        if not np.isfinite(
            final_gross_exposure
        ):
            raise PortfolioOptimizerCalculationError(
                "Final gross exposure is non-finite."
            )

        if (
            final_gross_exposure
            > max_leverage
            + self.LEVERAGE_TOLERANCE
        ):
            raise PortfolioOptimizerCalculationError(
                "Final portfolio exceeds regime maximum leverage. "
                f"Gross exposure={final_gross_exposure:.12f}; "
                f"maximum={max_leverage:.12f}."
            )

        accounting_total = (
            final_gross_exposure
            + cash_weight
            - financing_weight
        )

        if not np.isclose(
            accounting_total,
            1.0,
            atol=1e-8,
        ):
            raise PortfolioOptimizerCalculationError(
                "Final exposure accounting failed. "
                f"Gross={final_gross_exposure:.12f}; "
                f"Cash={cash_weight:.12f}; "
                f"Financing={financing_weight:.12f}; "
                f"Total={accounting_total:.12f}."
            )

        if not np.isfinite(
            final_volatility
        ):
            raise PortfolioOptimizerCalculationError(
                "Final portfolio volatility is non-finite."
            )

    # ==================================================================
    # MAIN OPTIMIZATION
    # ==================================================================

    def optimize(
        self,
        covariance,
        regime,
        asset_order,
        prices=None,
    ) -> dict[str, Any]:
        """
        Execute the complete production portfolio optimization pipeline.
        """

        # --------------------------------------------------------------
        # RESET STATE
        # --------------------------------------------------------------

        self._reset_state()

        # --------------------------------------------------------------
        # REGIME
        # --------------------------------------------------------------

        normalized_regime = (
            self._normalize_regime(
                regime
            )
        )

        self.last_regime = (
            normalized_regime
        )

        # --------------------------------------------------------------
        # ASSETS
        # --------------------------------------------------------------

        try:
            asset_order = (
                self._validate_asset_order(
                    asset_order
                )
            )
        except Exception as exc:
            raise PortfolioOptimizerCalculationError(
                f"Asset validation failed: {exc}"
            ) from exc

        # --------------------------------------------------------------
        # COVARIANCE
        # --------------------------------------------------------------

        try:
            covariance = (
                self._validate_covariance(
                    covariance,
                    asset_order,
                )
            )
        except Exception as exc:
            raise PortfolioOptimizerCalculationError(
                f"Covariance validation failed: {exc}"
            ) from exc

        # --------------------------------------------------------------
        # REGIME PARAMETERS
        # --------------------------------------------------------------

        target_vol, max_leverage = (
            self._resolve_regime_parameters(
                normalized_regime
            )
        )

        # --------------------------------------------------------------
        # RISK BUDGETS
        # --------------------------------------------------------------

        target_budgets = (
            self._resolve_target_budgets(
                normalized_regime,
                asset_order,
            )
        )

        risk_budget = (
            self._validate_risk_budgets(
                [
                    target_budgets[asset]
                    for asset in asset_order
                ],
                asset_order,
            )
        )

        self.last_risk_budget = {
            asset: float(
                risk_budget[index]
            )
            for index, asset
            in enumerate(
                asset_order
            )
        }

        # --------------------------------------------------------------
        # BASELINE
        # --------------------------------------------------------------

        baseline_weights = (
            self._build_baseline_weights(
                covariance,
                risk_budget,
            )
        )

        self.last_baseline_weights = (
            baseline_weights.copy()
        )

        # --------------------------------------------------------------
        # FORECAST + BL
        # --------------------------------------------------------------

        posterior_returns = (
            self._generate_return_overlay(
                covariance,
                asset_order,
                prices,
            )
        )

        # --------------------------------------------------------------
        # CONTROLLED BL TILT
        # --------------------------------------------------------------

        (
            tilted_weights,
            bl_multipliers,
        ) = self._apply_black_litterman_tilt(
            baseline_weights,
            posterior_returns,
        )

        self.last_bl_multipliers = (
            bl_multipliers.copy()
        )

        self.last_bl_tilted_weights = (
            tilted_weights.copy()
        )

        # --------------------------------------------------------------
        # CONSTRAINTS
        # --------------------------------------------------------------

        (
            constrained_weights,
            constraint_cash,
            constraint_result,
        ) = self._apply_constraints(
            tilted_weights,
            asset_order,
        )

        # --------------------------------------------------------------
        # VOLATILITY TARGETING
        # --------------------------------------------------------------

        (
            scaled_weights,
            volatility_engine_result,
        ) = self._apply_volatility_targeting(
            constrained_weights,
            covariance,
            target_vol,
            max_leverage,
        )

        # --------------------------------------------------------------
        # LEVERAGE BACKSTOP
        # --------------------------------------------------------------

        (
            final_weights,
            leverage_backstop_binding,
        ) = self._enforce_leverage_backstop(
            scaled_weights,
            max_leverage,
        )

        # --------------------------------------------------------------
        # FINAL EXPOSURE ACCOUNTING
        # --------------------------------------------------------------

        exposure = (
            self._calculate_exposure_metrics(
                final_weights
            )
        )

        final_gross_exposure = exposure[
            "gross_exposure"
        ]

        net_exposure = exposure[
            "net_exposure"
        ]

        cash_weight = exposure[
            "cash_weight"
        ]

        financing_weight = exposure[
            "financing_weight"
        ]

        # --------------------------------------------------------------
        # FINAL VOLATILITY
        # --------------------------------------------------------------

        final_volatility = (
            self._calculate_portfolio_volatility(
                final_weights,
                covariance,
            )
        )

        # --------------------------------------------------------------
        # FINAL VALIDATION
        # --------------------------------------------------------------

        self._validate_final_portfolio(
            final_weights,
            max_leverage,
            cash_weight,
            financing_weight,
            final_gross_exposure,
            final_volatility,
        )

        # --------------------------------------------------------------
        # VOLATILITY DIAGNOSTICS
        # --------------------------------------------------------------

        volatility_diagnostics = (
            self._build_volatility_diagnostics(
                volatility_engine_result,
                target_vol,
                max_leverage,
                final_weights,
                final_volatility,
                leverage_backstop_binding,
            )
        )

        volatility_diagnostics[
            "constraint_cash"
        ] = float(
            constraint_cash
        )

        volatility_diagnostics[
            "final_gross_exposure"
        ] = float(
            final_gross_exposure
        )

        volatility_diagnostics[
            "final_net_exposure"
        ] = float(
            net_exposure
        )

        volatility_diagnostics[
            "final_cash_weight"
        ] = float(
            cash_weight
        )

        volatility_diagnostics[
            "final_financing_weight"
        ] = float(
            financing_weight
        )

        volatility_diagnostics[
            "final_financing"
        ] = float(
            financing_weight
        )

        # --------------------------------------------------------------
        # RISK-BUDGET RESOLUTION DIAGNOSTICS
        # --------------------------------------------------------------

        budget_resolution = getattr(
            self.risk_budget_engine,
            "last_budget_resolution",
            None,
        )

        if isinstance(
            budget_resolution,
            dict,
        ):
            volatility_diagnostics[
                "risk_budget_resolution"
            ] = dict(
                budget_resolution
            )

        # --------------------------------------------------------------
        # RISK REPORT
        # --------------------------------------------------------------

        try:
            risk_report = (
                RiskBudgetReport.create(
                    asset_order,
                    final_weights,
                    covariance,
                    risk_budget,
                )
            )
        except Exception as exc:
            raise PortfolioOptimizerCalculationError(
                "Risk-budget report creation failed: "
                f"{exc}"
            ) from exc

        # --------------------------------------------------------------
        # STORE STATE
        # --------------------------------------------------------------

        self.last_weights = (
            final_weights.copy()
        )

        self.last_cash = float(
            cash_weight
        )

        self.last_financing = float(
            financing_weight
        )

        self.last_net_exposure = float(
            net_exposure
        )

        self.last_gross_exposure = float(
            final_gross_exposure
        )

        self.last_volatility_diagnostics = (
            volatility_diagnostics
        )

        # --------------------------------------------------------------
        # PUBLIC PRODUCTION MAPPINGS
        # --------------------------------------------------------------

        weight_map = {
            asset: float(
                final_weights[index]
            )
            for index, asset
            in enumerate(
                asset_order
            )
        }

        expected_return_map = (
            None
            if posterior_returns is None
            else {
                asset: float(
                    posterior_returns[index]
                )
                for index, asset
                in enumerate(
                    asset_order
                )
            }
        )

        baseline_weight_map = {
            asset: float(
                baseline_weights[index]
            )
            for index, asset
            in enumerate(
                asset_order
            )
        }

        bl_tilted_weight_map = {
            asset: float(
                tilted_weights[index]
            )
            for index, asset
            in enumerate(
                asset_order
            )
        }

        constrained_weight_map = {
            asset: float(
                constrained_weights[index]
            )
            for index, asset
            in enumerate(
                asset_order
            )
        }

        multiplier_map = {
            asset: float(
                bl_multipliers[index]
            )
            for index, asset
            in enumerate(
                asset_order
            )
        }

        # --------------------------------------------------------------
        # FINAL PUBLIC CONTRACT
        # --------------------------------------------------------------

        return {
            "weights": final_weights.copy(),

            "cash": float(
                cash_weight
            ),

            "financing": float(
                financing_weight
            ),

            "financing_weight": float(
                financing_weight
            ),

            "net_exposure": float(
                net_exposure
            ),

            "gross_exposure": float(
                final_gross_exposure
            ),

            "regime": normalized_regime,

            "expected_returns": (
                None
                if posterior_returns is None
                else posterior_returns.copy()
            ),

            "expected_return_map": (
                expected_return_map
            ),

            "forecasts": self.last_forecasts,

            "risk_report": risk_report,

            "volatility_diagnostics": (
                volatility_diagnostics
            ),

            "asset_order": list(
                asset_order
            ),

            "risk_budget": dict(
                self.last_risk_budget
            ),

            "baseline_weights": (
                baseline_weights.copy()
            ),

            "baseline_weight_map": (
                baseline_weight_map
            ),

            "bl_multipliers": (
                bl_multipliers.copy()
            ),

            "bl_multiplier_map": (
                multiplier_map
            ),

            "bl_tilted_weights": (
                tilted_weights.copy()
            ),

            "bl_tilted_weight_map": (
                bl_tilted_weight_map
            ),

            "constrained_weights": (
                constrained_weights.copy()
            ),

            "constrained_weight_map": (
                constrained_weight_map
            ),

            "constraint_cash": float(
                constraint_cash
            ),

            "target_volatility": float(
                target_vol
            ),

            "maximum_leverage": float(
                max_leverage
            ),

            "weight_map": dict(
                weight_map
            ),
        }

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return production component health.
        """

        try:
            checks = {
                "risk_budget_engine": (
                    self.risk_budget_engine
                    is not None
                    and hasattr(
                        self.risk_budget_engine,
                        "get_target_budgets",
                    )
                    and hasattr(
                        self.risk_budget_engine,
                        "optimize",
                    )
                ),

                "constraints": (
                    self.constraints
                    is not None
                    and hasattr(
                        self.constraints,
                        "enforce",
                    )
                ),

                "volatility_targeting": (
                    self.vol_target_engine
                    is not None
                    and hasattr(
                        self.vol_target_engine,
                        "scale_weights",
                    )
                ),

                "forecast_engine": (
                    self.forecast_engine
                    is not None
                    and hasattr(
                        self.forecast_engine,
                        "forecast",
                    )
                ),

                "black_litterman": (
                    self.black_litterman
                    is not None
                    and hasattr(
                        self.black_litterman,
                        "posterior_returns",
                    )
                ),

                "configuration": True,
            }

            healthy = all(
                checks.values()
            )

            return {
                "status": (
                    "HEALTHY"
                    if healthy
                    else "UNHEALTHY"
                ),
                "healthy": healthy,
                "component": self.COMPONENT,
                "api_version": self.API_VERSION,
                "phase": self.PHASE,
                "checks": checks,
            }

        except Exception as exc:
            return {
                "status": "UNHEALTHY",
                "healthy": False,
                "component": self.COMPONENT,
                "api_version": self.API_VERSION,
                "phase": self.PHASE,
                "error": str(exc),
            }


# ======================================================================
# PRODUCTION FACTORY
# ======================================================================


def build_portfolio_optimizer(
    risk_budget_engine,
    constraints,
    vol_target_engine,
    forecast_engine=None,
    black_litterman=None,
    **kwargs,
) -> PortfolioOptimizer:
    """
    Production factory for PortfolioOptimizer.
    """

    return PortfolioOptimizer(
        risk_budget_engine=risk_budget_engine,
        constraints=constraints,
        vol_target_engine=vol_target_engine,
        forecast_engine=forecast_engine,
        black_litterman=black_litterman,
        **kwargs,
    )


# ======================================================================
# BASIC PRODUCTION TEST
# ======================================================================


def test_portfolio_optimizer_configuration() -> None:
    """
    Validate that production dependencies are mandatory.
    """

    try:
        PortfolioOptimizer(
            risk_budget_engine=None,
            constraints=None,
            vol_target_engine=None,
        )

    except PortfolioOptimizerConfigurationError:
        return

    raise AssertionError(
        "PortfolioOptimizer should reject missing "
        "production dependencies."
    )


# ======================================================================
# EXPOSURE ACCOUNTING SELF-TEST
# ======================================================================


def test_portfolio_optimizer_exposure_accounting() -> None:
    """
    Validate the hardened cash/financing accounting model.

    Cases:

        0.75 gross -> 0.25 cash
        1.00 gross -> 0.00 cash
        1.25 gross -> 0.25 financing
    """

    unleveraged = (
        PortfolioOptimizer._calculate_exposure_metrics(
            np.asarray(
                [0.25, 0.25, 0.25],
                dtype=float,
            )
        )
    )

    assert np.isclose(
        unleveraged["gross_exposure"],
        0.75,
    )

    assert np.isclose(
        unleveraged["cash_weight"],
        0.25,
    )

    assert np.isclose(
        unleveraged["financing_weight"],
        0.0,
    )

    fully_invested = (
        PortfolioOptimizer._calculate_exposure_metrics(
            np.asarray(
                [0.40, 0.30, 0.30],
                dtype=float,
            )
        )
    )

    assert np.isclose(
        fully_invested["gross_exposure"],
        1.0,
    )

    assert np.isclose(
        fully_invested["cash_weight"],
        0.0,
    )

    assert np.isclose(
        fully_invested["financing_weight"],
        0.0,
    )

    leveraged = (
        PortfolioOptimizer._calculate_exposure_metrics(
            np.asarray(
                [0.50, 0.40, 0.35],
                dtype=float,
            )
        )
    )

    assert np.isclose(
        leveraged["gross_exposure"],
        1.25,
    )

    assert np.isclose(
        leveraged["cash_weight"],
        0.0,
    )

    assert np.isclose(
        leveraged["financing_weight"],
        0.25,
    )

    assert np.isclose(
        leveraged["gross_exposure"]
        + leveraged["cash_weight"]
        - leveraged["financing_weight"],
        1.0,
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":
    test_portfolio_optimizer_configuration()
    test_portfolio_optimizer_exposure_accounting()

    print(
        "PortfolioOptimizer Phase IV-B.1B tests passed."
    )