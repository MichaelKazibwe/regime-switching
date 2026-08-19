from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from expectedreturnforecaster import (
    ExpectedReturnForecaster,
)


# ============================================================
# EXCEPTIONS
# ============================================================


class RegimeForecastError(
    Exception
):
    """
    Base exception for regime-conditioned
    forecasting errors.
    """


class RegimeForecastConfigurationError(
    RegimeForecastError
):
    """
    Raised when regime forecast configuration
    is invalid.
    """


class RegimeForecastCalculationError(
    RegimeForecastError
):
    """
    Raised when regime forecast calculation
    fails.
    """


# ============================================================
# REGIME FORECAST POLICY
# ============================================================


@dataclass(
    frozen=True
)
class RegimeForecastPolicy:
    """
    Immutable regime-specific forecast weights.
    """

    momentum: float

    trend: float

    mean_reversion: float

    def validate(
        self,
    ) -> None:

        values = np.asarray(
            [
                self.momentum,
                self.trend,
                self.mean_reversion,
            ],
            dtype=float,
        )

        if not np.isfinite(
            values
        ).all():

            raise RegimeForecastConfigurationError(
                "Regime forecast weights must "
                "all be finite."
            )

        if np.any(
            values < 0.0
        ):

            raise RegimeForecastConfigurationError(
                "Regime forecast weights cannot "
                "be negative."
            )

        if not np.isclose(
            values.sum(),
            1.0,
            atol=1e-12,
        ):

            raise RegimeForecastConfigurationError(
                "Regime forecast weights must "
                f"sum to one; got {values.sum()}."
            )


# ============================================================
# REGIME FORECAST ENGINE
# ============================================================


class RegimeForecastEngine:
    """
    Production regime-conditioned forecast engine.

    Responsibilities
    ----------------

    1. Generate the baseline forecast components.
    2. Select a deterministic regime-specific policy.
    3. Recombine the same forecast components using
       regime-specific weights.
    4. Preserve asset ordering.
    5. Expose complete diagnostics.

    The engine does NOT:

        - determine the macro regime,
        - modify the underlying forecast models,
        - perform Black-Litterman,
        - optimize portfolio weights,
        - enforce portfolio constraints.
    """

    API_VERSION = "1.0.0"

    COMPONENT = "RegimeForecastEngine"

    REGIMES = (
        "bull",
        "neutral",
        "crisis",
    )

    POLICIES = {
        "bull": RegimeForecastPolicy(
            momentum=0.60,
            trend=0.30,
            mean_reversion=0.10,
        ),
        "neutral": RegimeForecastPolicy(
            momentum=0.50,
            trend=0.30,
            mean_reversion=0.20,
        ),
        "crisis": RegimeForecastPolicy(
            momentum=0.20,
            trend=0.20,
            mean_reversion=0.60,
        ),
    }

    def __init__(
        self,
        forecaster: ExpectedReturnForecaster | None = None,
    ) -> None:

        self.forecaster = (
            forecaster
            if forecaster is not None
            else ExpectedReturnForecaster()
        )

        for policy in self.POLICIES.values():

            policy.validate()

        self.last_regime = None

        self.last_forecast = None

        self.last_components = None

        self.last_policy = None

        self.last_diagnostics = None

    # ========================================================
    # REGIME VALIDATION
    # ========================================================

    @classmethod
    def validate_regime(
        cls,
        regime: str,
    ) -> str:

        if not isinstance(
            regime,
            str,
        ):

            raise RegimeForecastConfigurationError(
                "Regime must be a string."
            )

        normalized = (
            regime
            .strip()
            .lower()
        )

        if normalized not in cls.REGIMES:

            raise RegimeForecastConfigurationError(
                "Unsupported forecast regime "
                f"'{regime}'. Expected one of "
                f"{cls.REGIMES}."
            )

        return normalized

    # ========================================================
    # PRICE VALIDATION
    # ========================================================

    @staticmethod
    def validate_prices(
        prices: pd.DataFrame,
    ) -> None:

        if not isinstance(
            prices,
            pd.DataFrame,
        ):

            raise TypeError(
                "Prices must be a pandas DataFrame."
            )

        if prices.empty:

            raise ValueError(
                "Prices cannot be empty."
            )

        if prices.shape[1] == 0:

            raise ValueError(
                "Prices must contain at least "
                "one asset."
            )

        if prices.columns.duplicated().any():

            duplicated = (
                prices.columns[
                    prices.columns.duplicated()
                ]
                .tolist()
            )

            raise ValueError(
                "Prices contain duplicated "
                f"asset columns: {duplicated}."
            )

    # ========================================================
    # FORECAST
    # ========================================================

    def forecast(
        self,
        prices: pd.DataFrame,
        regime: str,
    ) -> pd.Series:
        """
        Generate a regime-conditioned expected-return
        forecast.
        """

        regime = self.validate_regime(
            regime
        )

        self.validate_prices(
            prices
        )

        try:

            baseline = (
                self.forecaster.forecast(
                    prices
                )
            )

        except Exception as exc:

            raise RegimeForecastCalculationError(
                "Baseline expected-return "
                "forecast failed."
            ) from exc

        if not isinstance(
            baseline,
            pd.Series,
        ):

            baseline = pd.Series(
                np.asarray(
                    baseline,
                    dtype=float,
                ).reshape(-1),
                index=prices.columns,
                dtype=float,
            )

        components = (
            self.forecaster.last_components
        )

        if not isinstance(
            components,
            dict,
        ):

            raise RegimeForecastCalculationError(
                "Expected-return forecaster did not "
                "provide component forecasts."
            )

        required_components = {
            "momentum",
            "trend",
            "mean_reversion",
        }

        if not (
            required_components
            <=
            set(
                components.keys()
            )
        ):

            raise RegimeForecastCalculationError(
                "Expected-return forecaster is "
                "missing required forecast components."
            )

        asset_index = prices.columns

        validated_components = {}

        for name in required_components:

            component = components[
                name
            ]

            if not isinstance(
                component,
                pd.Series,
            ):

                component = pd.Series(
                    np.asarray(
                        component,
                        dtype=float,
                    ).reshape(-1),
                    index=asset_index,
                    dtype=float,
                )

            component = component.reindex(
                asset_index
            )

            if component.isna().any():

                raise RegimeForecastCalculationError(
                    f"{name} forecast contains "
                    "missing values."
                )

            values = component.to_numpy(
                dtype=float
            )

            if not np.isfinite(
                values
            ).all():

                raise RegimeForecastCalculationError(
                    f"{name} forecast contains "
                    "non-finite values."
                )

            validated_components[
                name
            ] = component.astype(
                float
            )

        policy = self.POLICIES[
            regime
        ]

        policy.validate()

        regime_forecast = (
            policy.momentum
            *
            validated_components[
                "momentum"
            ]
            +
            policy.trend
            *
            validated_components[
                "trend"
            ]
            +
            policy.mean_reversion
            *
            validated_components[
                "mean_reversion"
            ]
        )

        regime_forecast = pd.Series(
            regime_forecast,
            index=asset_index,
            dtype=float,
        )

        if regime_forecast.isna().any():

            raise RegimeForecastCalculationError(
                "Regime-conditioned forecast "
                "contains missing values."
            )

        if not np.isfinite(
            regime_forecast.to_numpy(
                dtype=float
            )
        ).all():

            raise RegimeForecastCalculationError(
                "Regime-conditioned forecast "
                "contains non-finite values."
            )

        if not regime_forecast.index.equals(
            asset_index
        ):

            raise RegimeForecastCalculationError(
                "Regime-conditioned forecast "
                "asset ordering does not match "
                "the price universe."
            )

        # ----------------------------------------------------
        # STATE
        # ----------------------------------------------------

        self.last_regime = regime

        self.last_policy = policy

        self.last_components = {
            key: value.copy()
            for key, value
            in validated_components.items()
        }

        self.last_forecast = (
            regime_forecast.copy()
        )

        self.last_diagnostics = {
            "api_version": self.API_VERSION,
            "component": self.COMPONENT,
            "regime": regime,
            "asset_count": int(
                len(asset_index)
            ),
            "observations": int(
                len(prices)
            ),
            "weights": {
                "momentum": float(
                    policy.momentum
                ),
                "trend": float(
                    policy.trend
                ),
                "mean_reversion": float(
                    policy.mean_reversion
                ),
            },
        }

        return regime_forecast

    # ========================================================
    # POLICY ACCESS
    # ========================================================

    @classmethod
    def policy_for_regime(
        cls,
        regime: str,
    ) -> RegimeForecastPolicy:

        normalized = cls.validate_regime(
            regime
        )

        return cls.POLICIES[
            normalized
        ]

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self,
    ) -> dict[str, Any]:

        try:

            for regime in self.REGIMES:

                self.POLICIES[
                    regime
                ].validate()

            return {
                "status": "HEALTHY",
                "api_version": self.API_VERSION,
                "component": self.COMPONENT,
                "regimes": list(
                    self.REGIMES
                ),
                "policy_count": len(
                    self.POLICIES
                ),
            }

        except Exception as exc:

            return {
                "status": "UNHEALTHY",
                "api_version": self.API_VERSION,
                "component": self.COMPONENT,
                "error": str(exc),
            }


# ============================================================
# FACTORY
# ============================================================


def build_regime_forecast_engine(
    forecaster: ExpectedReturnForecaster | None = None,
) -> RegimeForecastEngine:
    """
    Construct the production regime forecast engine.
    """

    return RegimeForecastEngine(
        forecaster=forecaster
    )

