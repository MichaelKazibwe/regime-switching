from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from core_constants import TRADING_DAYS

# ======================================================================
# EXCEPTIONS
# ======================================================================

class VolatilityTargetingError(Exception):
    """Base exception for production volatility-targeting errors."""


class VolatilityTargetingConfigurationError(
    VolatilityTargetingError
):
    """Raised when volatility-targeting configuration is invalid."""


class VolatilityTargetingCalculationError(
    VolatilityTargetingError
):
    """Raised when volatility-targeting calculations fail."""


# ======================================================================
# RESULT OBJECT
# ======================================================================

@dataclass(frozen=True)
class VolatilityTargetResult:
    """
    Immutable volatility-targeting result.

    Volatility fields are expressed in the frequency requested by the
    calculation. The diagnostics dictionary records the frequency
    contract and, when annualized, the native-frequency equivalents.
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

    Covariance is assumed to be expressed in the frequency of the
    supplied return observations.

    annualize=False:
        volatility remains in covariance/native frequency.

    annualize=True:
        covariance is internally scaled by periods_per_year and all
        target-comparison quantities are therefore annualized.

    The caller's covariance is never mutated.
    """

    API_VERSION = "1.0.0"
    COMPONENT = "VolatilityTargeting"
    DEFAULT_TOLERANCE = 1e-10
    DEFAULT_PERIODS_PER_YEAR = TRADING_DAYS

    def __init__(
        self,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:

        self.tolerance = float(tolerance)

        if (
            not np.isfinite(self.tolerance)
            or self.tolerance <= 0.0
        ):
            raise VolatilityTargetingConfigurationError(
                "Volatility-targeting tolerance "
                "must be positive and finite."
            )

        self.last_result = None

    # ==================================================================
    # PERIOD VALIDATION
    # ==================================================================

    @classmethod
    def _validate_periods_per_year(
        cls,
        periods_per_year: int,
    ) -> int:

        if isinstance(periods_per_year, bool):
            raise VolatilityTargetingConfigurationError(
                "periods_per_year must be a positive integer."
            )

        try:
            value = int(periods_per_year)
        except (TypeError, ValueError) as exc:
            raise VolatilityTargetingConfigurationError(
                "periods_per_year must be a positive integer."
            ) from exc

        if value <= 0:
            raise VolatilityTargetingConfigurationError(
                "periods_per_year must be positive."
            )

        return value

    # ==================================================================
    # COVARIANCE PREPARATION
    # ==================================================================

    @classmethod
    def _prepare_covariance(
        cls,
        covariance: Any,
        annualize: bool = False,
        periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    ) -> np.ndarray:
        """Prepare covariance for the requested risk frequency."""

        covariance = np.asarray(covariance, dtype=float)

        if not isinstance(annualize, bool):
            raise TypeError("annualize must be boolean.")

        periods_per_year = cls._validate_periods_per_year(
            periods_per_year
        )

        if annualize:
            covariance = covariance * periods_per_year

        return covariance

    # ==================================================================
    # INPUT VALIDATION
    # ==================================================================

    @classmethod
    def _validate_inputs(
        cls,
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

        weights = np.asarray(weights, dtype=float).reshape(-1)
        covariance = np.asarray(covariance, dtype=float)
        target_vol = float(target_vol)
        max_leverage = float(max_leverage)

        if weights.size == 0:
            raise VolatilityTargetingCalculationError(
                "Weights cannot be empty."
            )

        if covariance.ndim != 2:
            raise VolatilityTargetingCalculationError(
                "Covariance must be a 2-dimensional matrix."
            )

        if covariance.shape[0] != covariance.shape[1]:
            raise VolatilityTargetingCalculationError(
                "Covariance matrix must be square."
            )

        if covariance.shape[0] != weights.size:
            raise VolatilityTargetingCalculationError(
                "Weight vector length "
                f"{weights.size} does not match covariance dimension "
                f"{covariance.shape[0]}."
            )

        if not np.isfinite(weights).all():
            raise VolatilityTargetingCalculationError(
                "Weights contain non-finite values."
            )

        if not np.isfinite(covariance).all():
            raise VolatilityTargetingCalculationError(
                "Covariance contains non-finite values."
            )

        if not np.isfinite(target_vol) or target_vol <= 0.0:
            raise VolatilityTargetingCalculationError(
                "Target volatility must be positive and finite."
            )

        if (
            not np.isfinite(max_leverage)
            or max_leverage <= 0.0
        ):
            raise VolatilityTargetingCalculationError(
                "Maximum leverage must be positive and finite."
            )

        if np.any(weights < -1e-12):
            raise VolatilityTargetingCalculationError(
                "Negative weights are not supported."
            )

        covariance = (covariance + covariance.T) / 2.0

        eigenvalues = np.linalg.eigvalsh(covariance)

        if eigenvalues.min() < -1e-10:
            raise VolatilityTargetingCalculationError(
                "Covariance matrix is not positive semi-definite."
            )

        return (
            weights,
            covariance,
            target_vol,
            max_leverage,
        )

    # ==================================================================
    # PORTFOLIO VARIANCE
    # ==================================================================

    @staticmethod
    def portfolio_variance(
        weights: np.ndarray,
        covariance: np.ndarray,
    ) -> float:

        variance = float(weights @ covariance @ weights)

        if not np.isfinite(variance):
            raise VolatilityTargetingCalculationError(
                "Portfolio variance is non-finite."
            )

        if variance < 0.0:
            if variance > -1e-12:
                variance = 0.0
            else:
                raise VolatilityTargetingCalculationError(
                    "Portfolio variance is materially negative: "
                    f"{variance}."
                )

        return variance

    # ==================================================================
    # PORTFOLIO VOLATILITY
    # ==================================================================

    @classmethod
    def portfolio_volatility(
        cls,
        weights: np.ndarray,
        covariance: np.ndarray,
    ) -> float:

        variance = cls.portfolio_variance(
            weights,
            covariance,
        )

        return float(np.sqrt(variance))

    # ==================================================================
    # SCALE WEIGHTS
    # ==================================================================

    def scale_weights(
        self,
        weights: Any,
        covariance: Any,
        target_vol: float = 0.10,
        max_leverage: float | None = None,
        annualize: bool = False,
        periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    ) -> np.ndarray:
        """
        Scale portfolio weights toward a volatility target.

        final_volatility remains expressed in the requested calculation
        frequency. Thus annualize=True means final_volatility is annual
        volatility, while annualize=False means it is native-frequency
        volatility.

        The same frequency is used consistently for:
            - original_volatility
            - target_volatility
            - final_volatility
            - volatility_shortfall
            - target_achieved
            - volatility scaling
        """

        periods_per_year = self._validate_periods_per_year(
            periods_per_year
        )

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

        calculation_covariance = self._prepare_covariance(
            covariance,
            annualize=annualize,
            periods_per_year=periods_per_year,
        )

        annualization_factor = (
            np.sqrt(periods_per_year)
            if annualize
            else 1.0
        )

        risk_frequency = (
            "annual"
            if annualize
            else "native"
        )

        original_gross = float(
            np.sum(np.abs(weights))
        )

        # --------------------------------------------------------------
        # ZERO PORTFOLIO
        # --------------------------------------------------------------

        if original_gross <= self.tolerance:

            self.last_result = VolatilityTargetResult(
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
                    "annualized": annualize,
                    "risk_frequency": risk_frequency,
                    "periods_per_year": periods_per_year,
                    "annualization_factor": annualization_factor,
                    "original_volatility_native": 0.0,
                    "final_volatility_native": 0.0,
                    "target_volatility_frequency": risk_frequency,
                },
            )

            return np.zeros_like(weights)

        # --------------------------------------------------------------
        # ORIGINAL VOLATILITY
        # --------------------------------------------------------------

        original_volatility = self.portfolio_volatility(
            weights,
            calculation_covariance,
        )

        # --------------------------------------------------------------
        # ZERO VOLATILITY
        # --------------------------------------------------------------

        if original_volatility <= self.tolerance:

            self.last_result = VolatilityTargetResult(
                original_volatility=original_volatility,
                target_volatility=target_vol,
                scale_factor=1.0,
                final_volatility=original_volatility,
                maximum_leverage=validated_max_leverage,
                gross_exposure=original_gross,
                target_achieved=False,
                leverage_binding=False,
                volatility_shortfall=target_vol - original_volatility,
                required_leverage=original_gross,
                diagnostics={
                    "status": "ZERO_VOLATILITY",
                    "annualized": annualize,
                    "risk_frequency": risk_frequency,
                    "periods_per_year": periods_per_year,
                    "annualization_factor": annualization_factor,
                    "original_volatility_native": (
                        original_volatility / annualization_factor
                    ),
                    "final_volatility_native": (
                        original_volatility / annualization_factor
                    ),
                    "target_volatility_frequency": risk_frequency,
                },
            )

            return weights.copy()

        # --------------------------------------------------------------
        # REQUIRED VOLATILITY SCALE
        # --------------------------------------------------------------

        volatility_scale = (
            target_vol / original_volatility
        )

        # --------------------------------------------------------------
        # REQUIRED GROSS EXPOSURE
        # --------------------------------------------------------------

        required_gross = (
            original_gross * volatility_scale
        )

        required_leverage = required_gross

        # --------------------------------------------------------------
        # MAXIMUM LEVERAGE SCALE
        # --------------------------------------------------------------

        leverage_scale = (
            validated_max_leverage / original_gross
        )

        # --------------------------------------------------------------
        # FINAL SCALE
        # --------------------------------------------------------------

        scale_factor = max(
            min(
                volatility_scale,
                leverage_scale,
            ),
            0.0,
        )

        scaled_weights = weights * scale_factor

        # --------------------------------------------------------------
        # FINAL LEVERAGE PROTECTION
        # --------------------------------------------------------------

        gross_exposure = float(
            np.sum(np.abs(scaled_weights))
        )

        if (
            gross_exposure
            > validated_max_leverage + self.tolerance
        ):

            correction = (
                validated_max_leverage / gross_exposure
            )

            scaled_weights *= correction
            scale_factor *= correction

            gross_exposure = float(
                np.sum(np.abs(scaled_weights))
            )

        # --------------------------------------------------------------
        # FINAL VOLATILITY
        # --------------------------------------------------------------

        final_volatility = self.portfolio_volatility(
            scaled_weights,
            calculation_covariance,
        )

        # --------------------------------------------------------------
        # TARGET / LEVERAGE DIAGNOSTICS
        # --------------------------------------------------------------

        target_tolerance = max(
            self.tolerance,
            target_vol * 1e-6,
        )

        target_achieved = (
            abs(final_volatility - target_vol)
            <= target_tolerance
        )

        leverage_binding = (
            required_gross
            > validated_max_leverage + self.tolerance
        )

        volatility_shortfall = max(
            0.0,
            target_vol - final_volatility,
        )

        if target_achieved:
            status = "TARGET_ACHIEVED"
        elif leverage_binding:
            status = "LEVERAGE_CONSTRAINED"
        else:
            status = "TARGET_NOT_REACHED"

        # Native-frequency equivalents are retained for provenance.
        original_volatility_native = (
            original_volatility / annualization_factor
        )

        final_volatility_native = (
            final_volatility / annualization_factor
        )

        self.last_result = VolatilityTargetResult(
            original_volatility=original_volatility,
            target_volatility=target_vol,
            scale_factor=float(scale_factor),
            final_volatility=final_volatility,
            maximum_leverage=validated_max_leverage,
            gross_exposure=gross_exposure,
            target_achieved=target_achieved,
            leverage_binding=leverage_binding,
            volatility_shortfall=volatility_shortfall,
            required_leverage=required_leverage,
            diagnostics={
                "status": status,
                "annualized": annualize,
                "risk_frequency": risk_frequency,
                "periods_per_year": periods_per_year,
                "annualization_factor": annualization_factor,
                "target_volatility_frequency": risk_frequency,
                "original_volatility_native": (
                    original_volatility_native
                ),
                "original_volatility_annualized": (
                    original_volatility_native
                    * np.sqrt(periods_per_year)
                ),
                "final_volatility_native": (
                    final_volatility_native
                ),
                "final_volatility_annualized": (
                    final_volatility_native
                    * np.sqrt(periods_per_year)
                ),
                "original_gross_exposure": original_gross,
                "required_gross_exposure": required_gross,
                "final_gross_exposure": gross_exposure,
                "volatility_scale": volatility_scale,
                "leverage_scale": leverage_scale,
            },
        )

        return scaled_weights

    # ==================================================================
    # EXPLICIT ANNUALIZED VOLATILITY
    # ==================================================================

    @classmethod
    def annualized_volatility(
        cls,
        weights: Any,
        covariance: Any,
        periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    ) -> float:
        """Calculate annualized portfolio volatility."""

        periods_per_year = cls._validate_periods_per_year(
            periods_per_year
        )

        weights = np.asarray(
            weights,
            dtype=float,
        ).reshape(-1)

        covariance = cls._prepare_covariance(
            covariance,
            annualize=True,
            periods_per_year=periods_per_year,
        )

        return cls.portfolio_volatility(
            weights,
            covariance,
        )

    # ==================================================================
    # RESULT
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
            healthy = (
                np.isfinite(self.tolerance)
                and self.tolerance > 0.0
            )

            return {
                "status": (
                    "HEALTHY"
                    if healthy
                    else "UNHEALTHY"
                ),
                "component": self.COMPONENT,
                "api_version": self.API_VERSION,
                "tolerance": self.tolerance,
                "default_periods_per_year": (
                    self.DEFAULT_PERIODS_PER_YEAR
                ),
                "risk_frequency_contract": (
                    "input covariance frequency "
                    "unless annualize=True"
                ),
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
    """Construct the production volatility-targeting engine."""

    return VolatilityTargeting()


# ======================================================================
# REGRESSION TESTS
# ======================================================================

def test_volatility_targeting():

    weights = np.array([
        0.50,
        0.50,
    ])

    daily_variance = (
        0.10 ** 2
        / TRADING_DAYS
    )

    covariance = np.array([
        [2.0 * daily_variance, 0.0],
        [0.0, 2.0 * daily_variance],
    ])

    engine = VolatilityTargeting()

    # --------------------------------------------------------
    # DAILY VOLATILITY
    # --------------------------------------------------------

    daily_vol = engine.portfolio_volatility(
        weights,
        covariance,
    )

    expected_daily = (
        0.10
        / np.sqrt(TRADING_DAYS)
    )

    assert np.isclose(
        daily_vol,
        expected_daily,
        rtol=1e-10,
        atol=1e-12,
    )

    # --------------------------------------------------------
    # ANNUALIZED VOLATILITY
    # --------------------------------------------------------

    annual_vol = engine.annualized_volatility(
        weights,
        covariance,
    )

    assert np.isclose(
        annual_vol,
        0.10,
        rtol=1e-10,
        atol=1e-12,
    )

    # --------------------------------------------------------
    # ANNUALIZED TARGETING
    # --------------------------------------------------------

    scaled = engine.scale_weights(
        weights,
        covariance,
        target_vol=0.15,
        max_leverage=2.0,
        annualize=True,
    )

    result = engine.get_last_result()

    assert result is not None

    assert np.isclose(
        result.final_volatility,
        0.15,
        rtol=1e-6,
        atol=1e-10,
    )

    assert result.target_achieved
    assert not result.leverage_binding

    assert np.isclose(
        np.sum(np.abs(scaled)),
        1.5,
        atol=1e-10,
    )

    # --------------------------------------------------------
    # LEVERAGE-CONSTRAINED TARGET
    # --------------------------------------------------------

    scaled = engine.scale_weights(
        weights,
        covariance,
        target_vol=0.50,
        max_leverage=1.25,
        annualize=True,
    )

    result = engine.get_last_result()

    assert result is not None

    assert result.leverage_binding
    assert not result.target_achieved

    assert np.sum(np.abs(scaled)) <= (
        1.25 + 1e-10
    )

    # --------------------------------------------------------
    # HEALTH
    # --------------------------------------------------------

    health = engine.health_check()

    assert health["status"] == "HEALTHY"

    print("VolatilityTargeting tests passed.")


if __name__ == "__main__":
    test_volatility_targeting()
