from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


# ======================================================================
# EXCEPTIONS
# ======================================================================


class VolatilityTargetingError(Exception):
    """
    Base exception for production volatility-targeting errors.
    """


class VolatilityTargetingConfigurationError(
    VolatilityTargetingError
):
    """
    Raised when volatility-targeting configuration is invalid.
    """


class VolatilityTargetingCalculationError(
    VolatilityTargetingError
):
    """
    Raised when volatility-targeting calculations fail.
    """


# ======================================================================
# RESULT OBJECT
# ======================================================================


@dataclass(frozen=True)
class VolatilityTargetResult:
    """
    Immutable volatility-targeting result.
    """

    original_volatility: float

    target_volatility: float

    scale_factor: float

    final_volatility: float

    maximum_leverage: float

    gross_exposure: float

    target_achieved: bool

    leverage_binding: bool

    volatility_shortfall: float

    required_leverage: float

    diagnostics: dict[str, Any]


# ======================================================================
# VOLATILITY TARGETING ENGINE
# ======================================================================


class VolatilityTargeting:
    """
    Production volatility-targeting engine.

    Responsibilities
    ----------------
    1. Calculate current portfolio volatility.
    2. Calculate the scaling required to reach a volatility target.
    3. Respect a maximum leverage constraint.
    4. Preserve the relative composition of the input portfolio.
    5. Report whether the target was actually achievable.

    The engine does NOT:
        - determine regime,
        - determine risk budgets,
        - perform asset selection,
        - enforce individual position caps.

    Those responsibilities belong to upstream/downstream components.
    """

    API_VERSION = "1.0.0"

    COMPONENT = "VolatilityTargeting"

    DEFAULT_TOLERANCE = 1e-10

    # ------------------------------------------------------------------
    # CONSTRUCTOR
    # ------------------------------------------------------------------

    def __init__(
        self,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:

        self.tolerance = float(
            tolerance
        )

        if (
            not np.isfinite(
                self.tolerance
            )
            or self.tolerance <= 0.0
        ):
            raise VolatilityTargetingConfigurationError(
                "Volatility-targeting tolerance "
                "must be positive and finite."
            )

        self.last_result = None

    # ==================================================================
    # VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_inputs(
        weights: Any,
        covariance: Any,
        target_vol: float,
        max_leverage: float,
    ) -> tuple[
        np.ndarray,
        np.ndarray,
        float,
        float,
    ]:

        weights = np.asarray(
            weights,
            dtype=float,
        ).reshape(-1)

        covariance = np.asarray(
            covariance,
            dtype=float,
        )

        target_vol = float(
            target_vol
        )

        max_leverage = float(
            max_leverage
        )

        if weights.size == 0:
            raise VolatilityTargetingCalculationError(
                "Weights cannot be empty."
            )

        if covariance.ndim != 2:
            raise VolatilityTargetingCalculationError(
                "Covariance must be a "
                "2-dimensional matrix."
            )

        if (
            covariance.shape[0]
            != covariance.shape[1]
        ):
            raise VolatilityTargetingCalculationError(
                "Covariance matrix must be square."
            )

        if (
            covariance.shape[0]
            != weights.size
        ):
            raise VolatilityTargetingCalculationError(
                "Weight vector length "
                f"{weights.size} does not match "
                "covariance dimension "
                f"{covariance.shape[0]}."
            )

        if not np.isfinite(
            weights
        ).all():
            raise VolatilityTargetingCalculationError(
                "Weights contain non-finite values."
            )

        if not np.isfinite(
            covariance
        ).all():
            raise VolatilityTargetingCalculationError(
                "Covariance contains non-finite values."
            )

        if (
            not np.isfinite(
                target_vol
            )
            or target_vol <= 0.0
        ):
            raise VolatilityTargetingCalculationError(
                "Target volatility must be "
                "positive and finite."
            )

        if (
            not np.isfinite(
                max_leverage
            )
            or max_leverage <= 0.0
        ):
            raise VolatilityTargetingCalculationError(
                "Maximum leverage must be "
                "positive and finite."
            )

        if np.any(
            weights < -1e-12
        ):
            raise VolatilityTargetingCalculationError(
                "Negative weights are not supported."
            )

        covariance = (
            covariance
            + covariance.T
        ) / 2.0

        return (
            weights,
            covariance,
            target_vol,
            max_leverage,
        )

    # ==================================================================
    # PORTFOLIO VOLATILITY
    # ==================================================================

    @staticmethod
    def portfolio_volatility(
        weights: np.ndarray,
        covariance: np.ndarray,
    ) -> float:

        variance = float(
            weights
            @ covariance
            @ weights
        )

        if (
            not np.isfinite(
                variance
            )
        ):
            raise VolatilityTargetingCalculationError(
                "Portfolio variance is non-finite."
            )

        # Protect against tiny negative
        # numerical round-off.
        if variance < 0.0:

            if variance > -1e-12:

                variance = 0.0

            else:

                raise VolatilityTargetingCalculationError(
                    "Portfolio variance is negative: "
                    f"{variance}."
                )

        return float(
            np.sqrt(
                variance
            )
        )

    # ==================================================================
    # SCALE WEIGHTS
    # ==================================================================

    def scale_weights(
        self,
        weights: Any,
        covariance: Any,
        target_vol: float = 0.10,
        max_leverage: float | None = None,
    ) -> np.ndarray:
        """
        Scale portfolio weights toward target volatility.

        If max_leverage is supplied, the resulting portfolio will
        never exceed that gross exposure.

        The relative proportions of the supplied weights are preserved.
        """

        (
            weights,
            covariance,
            target_vol,
            validated_max_leverage,
        ) = self._validate_inputs(
            weights,
            covariance,
            target_vol,
            (
                max_leverage
                if max_leverage is not None
                else 1.0
            ),
        )

        original_gross = float(
            np.sum(
                np.abs(
                    weights
                )
            )
        )

        if (
            original_gross
            <= self.tolerance
        ):

            self.last_result = (
                VolatilityTargetResult(
                    original_volatility=0.0,
                    target_volatility=target_vol,
                    scale_factor=0.0,
                    final_volatility=0.0,
                    maximum_leverage=validated_max_leverage,
                    gross_exposure=0.0,
                    target_achieved=False,
                    leverage_binding=False,
                    volatility_shortfall=target_vol,
                    required_leverage=0.0,
                    diagnostics={
                        "status": "ZERO_PORTFOLIO",
                    },
                )
            )

            return np.zeros_like(
                weights
            )

        original_volatility = (
            self.portfolio_volatility(
                weights,
                covariance,
            )
        )

        if (
            original_volatility
            <= self.tolerance
        ):

            # No meaningful volatility exists
            # from which to calculate a scale.
            self.last_result = (
                VolatilityTargetResult(
                    original_volatility=(
                        original_volatility
                    ),
                    target_volatility=target_vol,
                    scale_factor=1.0,
                    final_volatility=(
                        original_volatility
                    ),
                    maximum_leverage=(
                        validated_max_leverage
                    ),
                    gross_exposure=(
                        original_gross
                    ),
                    target_achieved=False,
                    leverage_binding=False,
                    volatility_shortfall=(
                        target_vol
                        - original_volatility
                    ),
                    required_leverage=(
                        original_gross
                    ),
                    diagnostics={
                        "status": "ZERO_VOLATILITY",
                    },
                )
            )

            return weights.copy()

        # --------------------------------------------------------------
        # VOLATILITY SCALING
        # --------------------------------------------------------------

        volatility_scale = (
            target_vol
            /
            original_volatility
        )

        # --------------------------------------------------------------
        # LEVERAGE SCALING
        # --------------------------------------------------------------

        if original_gross <= self.tolerance:

            leverage_scale = 0.0

        else:

            leverage_scale = (
                validated_max_leverage
                /
                original_gross
            )

        # Required gross exposure after
        # volatility targeting.
        required_gross = (
            original_gross
            * volatility_scale
        )

        required_leverage = (
            required_gross
        )

        # --------------------------------------------------------------
        # FINAL SCALE
        # --------------------------------------------------------------

        scale_factor = min(
            volatility_scale,
            leverage_scale,
        )

        if scale_factor < 0.0:
            scale_factor = 0.0

        scaled_weights = (
            weights
            * scale_factor
        )

        gross_exposure = float(
            np.sum(
                np.abs(
                    scaled_weights
                )
            )
        )

        # Final hard leverage protection.
        if (
            gross_exposure
            >
            validated_max_leverage
            +
            self.tolerance
        ):

            correction = (
                validated_max_leverage
                /
                gross_exposure
            )

            scaled_weights *= correction

            scale_factor *= correction

            gross_exposure = float(
                np.sum(
                    np.abs(
                        scaled_weights
                    )
                )
            )

        final_volatility = (
            self.portfolio_volatility(
                scaled_weights,
                covariance,
            )
        )

        leverage_binding = (
            required_gross
            >
            validated_max_leverage
            +
            self.tolerance
        )

        target_achieved = (
            abs(
                final_volatility
                -
                target_vol
            )
            <= max(
                self.tolerance,
                target_vol * 1e-6,
            )
        )

        volatility_shortfall = max(
            0.0,
            target_vol
            -
            final_volatility,
        )

        self.last_result = (
            VolatilityTargetResult(
                original_volatility=(
                    original_volatility
                ),
                target_volatility=target_vol,
                scale_factor=float(
                    scale_factor
                ),
                final_volatility=(
                    final_volatility
                ),
                maximum_leverage=(
                    validated_max_leverage
                ),
                gross_exposure=(
                    gross_exposure
                ),
                target_achieved=(
                    target_achieved
                ),
                leverage_binding=(
                    leverage_binding
                ),
                volatility_shortfall=(
                    volatility_shortfall
                ),
                required_leverage=(
                    required_leverage
                ),
                diagnostics={
                    "status": (
                        "TARGET_ACHIEVED"
                        if target_achieved
                        else
                        "LEVERAGE_CONSTRAINED"
                        if leverage_binding
                        else
                        "TARGET_NOT_REACHED"
                    ),
                    "original_gross_exposure": (
                        original_gross
                    ),
                    "required_gross_exposure": (
                        required_gross
                    ),
                    "final_gross_exposure": (
                        gross_exposure
                    ),
                    "volatility_scale": (
                        volatility_scale
                    ),
                    "leverage_scale": (
                        leverage_scale
                    ),
                },
            )
        )

        return scaled_weights

    # ==================================================================
    # RESULT / DIAGNOSTICS
    # ==================================================================

    def get_last_result(
        self,
    ) -> VolatilityTargetResult | None:

        return self.last_result

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:

        try:

            if (
                not np.isfinite(
                    self.tolerance
                )
                or self.tolerance <= 0.0
            ):
                return {
                    "status": "UNHEALTHY",
                    "component": self.COMPONENT,
                    "api_version": self.API_VERSION,
                }

            return {
                "status": "HEALTHY",
                "component": self.COMPONENT,
                "api_version": self.API_VERSION,
                "tolerance": self.tolerance,
            }

        except Exception as exc:

            return {
                "status": "UNHEALTHY",
                "component": self.COMPONENT,
                "api_version": self.API_VERSION,
                "error": str(exc),
            }


# ======================================================================
# FACTORY
# ======================================================================


def build_volatility_targeting() -> VolatilityTargeting:
    """
    Construct the production volatility-targeting engine.
    """

    return VolatilityTargeting()