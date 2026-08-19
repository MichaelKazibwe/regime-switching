from __future__ import annotations

import numpy as np
import pandas as pd

from forecastmodels import (
    MeanReversionForecast,
    MomentumForecast,
    TrendForecast,
)


# ============================================================
# EXPECTED RETURN FORECASTER
# ============================================================


class ExpectedReturnForecaster:
    """
    Production expected-return forecasting orchestrator.

    Combines:

        Momentum       : 50%
        Trend          : 30%
        Mean reversion : 20%

    The forecasting stack requires sufficient price history
    for every underlying forecasting component.

    Production requirements:

        Momentum       : 252 price observations
        Trend          : 200 price observations
        Mean reversion : 63 return observations

    Therefore the complete stack requires at least
    252 price observations.
    """

    API_VERSION = "1.0.0"

    COMPONENT = "ExpectedReturnForecaster"

    MOMENTUM_LOOKBACK = 252

    TREND_LOOKBACK = 200

    MEAN_REVERSION_LOOKBACK = 63

    TREND_SHORT_WINDOW = 50

    MOMENTUM_WEIGHT = 0.50

    TREND_WEIGHT = 0.30

    MEAN_REVERSION_WEIGHT = 0.20

    MINIMUM_HISTORY = max(
        MOMENTUM_LOOKBACK,
        TREND_LOOKBACK,
        MEAN_REVERSION_LOOKBACK + 1,
    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(
        self,
    ) -> None:

        self.momentum = (
            MomentumForecast()
        )

        self.trend = (
            TrendForecast()
        )

        self.mean_reversion = (
            MeanReversionForecast()
        )

        self.last_forecast = None

        self.last_components = None

        self.last_observations = None

        self.last_diagnostics = None

    # ========================================================
    # HISTORY
    # ========================================================

    @classmethod
    def minimum_history(
        cls,
    ) -> int:
        """
        Return the minimum number of price observations
        required by the complete forecasting stack.
        """

        return cls.MINIMUM_HISTORY

    @classmethod
    def validate_history(
        cls,
        prices,
    ) -> None:
        """
        Validate the minimum historical observation
        requirement.
        """

        try:
            observations = len(
                prices
            )

        except TypeError as exc:

            raise TypeError(
                "Prices must be a sized "
                "time-series object."
            ) from exc

        if observations < (
            cls.MINIMUM_HISTORY
        ):

            raise ValueError(
                "Insufficient history for expected-return "
                "forecasting: required at least "
                f"{cls.MINIMUM_HISTORY} price observations, "
                f"received {observations}."
            )

    # ========================================================
    # INPUT VALIDATION
    # ========================================================

    @staticmethod
    def _validate_prices(
        prices,
    ) -> pd.DataFrame:
        """
        Validate the complete forecast input.
        """

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

        numeric = prices.apply(
            pd.to_numeric,
            errors="coerce",
        )

        values = numeric.to_numpy(
            dtype=float
        )

        if not np.isfinite(
            values
        ).all():

            raise ValueError(
                "Prices contain non-finite values."
            )

        if (
            values <= 0.0
        ).any():

            raise ValueError(
                "Prices must contain strictly "
                "positive values."
            )

        if not numeric.index.is_monotonic_increasing:

            raise ValueError(
                "Price index must be monotonically "
                "increasing."
            )

        return numeric

    # ========================================================
    # FORECAST
    # ========================================================

    def forecast(
        self,
        prices,
    ) -> pd.Series:
        """
        Generate the production combined expected-return
        forecast.
        """

        prices = self._validate_prices(
            prices
        )

        self.validate_history(
            prices
        )

        self.last_observations = len(
            prices
        )

        asset_index = prices.columns

        # ----------------------------------------------------
        # MOMENTUM
        # ----------------------------------------------------

        momentum = (
            self.momentum.forecast(
                prices,
                lookback=(
                    self.MOMENTUM_LOOKBACK
                ),
            )
        )

        momentum = self._validate_component(
            momentum,
            asset_index,
            "Momentum",
        )

        # ----------------------------------------------------
        # TREND
        # ----------------------------------------------------

        trend = (
            self.trend.forecast(
                prices,
                short_window=(
                    self.TREND_SHORT_WINDOW
                ),
                long_window=(
                    self.TREND_LOOKBACK
                ),
            )
        )

        trend = self._validate_component(
            trend,
            asset_index,
            "Trend",
        )

        # ----------------------------------------------------
        # MEAN REVERSION
        # ----------------------------------------------------

        reversion = (
            self.mean_reversion.forecast(
                prices,
                lookback=(
                    self.MEAN_REVERSION_LOOKBACK
                ),
            )
        )

        reversion = self._validate_component(
            reversion,
            asset_index,
            "Mean reversion",
        )

        # ----------------------------------------------------
        # STORE COMPONENTS
        # ----------------------------------------------------

        self.last_components = {
            "momentum": momentum.copy(),
            "trend": trend.copy(),
            "mean_reversion": reversion.copy(),
        }

        # ----------------------------------------------------
        # WEIGHT VALIDATION
        # ----------------------------------------------------

        total_weight = (
            self.MOMENTUM_WEIGHT
            +
            self.TREND_WEIGHT
            +
            self.MEAN_REVERSION_WEIGHT
        )

        if not np.isclose(
            total_weight,
            1.0,
            atol=1e-12,
        ):

            raise ValueError(
                "Expected-return forecast weights "
                f"must sum to one; got {total_weight}."
            )

        # ----------------------------------------------------
        # COMBINATION
        # ----------------------------------------------------

        expected_returns = (
            self.MOMENTUM_WEIGHT
            *
            momentum
            +
            self.TREND_WEIGHT
            *
            trend
            +
            self.MEAN_REVERSION_WEIGHT
            *
            reversion
        )

        expected_returns = (
            pd.Series(
                expected_returns,
                index=asset_index,
                dtype=float,
            )
        )

        # ----------------------------------------------------
        # FINAL VALIDATION
        # ----------------------------------------------------

        if expected_returns.isna().any():

            raise ValueError(
                "Combined expected-return forecast "
                "contains missing values."
            )

        if not np.isfinite(
            expected_returns.to_numpy(
                dtype=float
            )
        ).all():

            raise ValueError(
                "Combined expected-return forecast "
                "contains non-finite values."
            )

        if not expected_returns.index.equals(
            asset_index
        ):

            raise ValueError(
                "Combined forecast asset ordering "
                "does not match input prices."
            )

        # ----------------------------------------------------
        # STATE
        # ----------------------------------------------------

        self.last_forecast = (
            expected_returns.copy()
        )

        self.last_diagnostics = {
            "api_version": self.API_VERSION,
            "component": self.COMPONENT,
            "observations": int(
                self.last_observations
            ),
            "asset_count": int(
                len(asset_index)
            ),
            "minimum_history": int(
                self.MINIMUM_HISTORY
            ),
            "weights": {
                "momentum": float(
                    self.MOMENTUM_WEIGHT
                ),
                "trend": float(
                    self.TREND_WEIGHT
                ),
                "mean_reversion": float(
                    self.MEAN_REVERSION_WEIGHT
                ),
            },
        }

        return expected_returns

    # ========================================================
    # COMPONENT VALIDATION
    # ========================================================

    @staticmethod
    def _validate_component(
        component,
        asset_index,
        component_name: str,
    ) -> pd.Series:
        """
        Validate an individual forecast component and
        normalize it to the production asset ordering.
        """

        if isinstance(
            component,
            pd.Series,
        ):

            result = component.copy()

        else:

            values = np.asarray(
                component,
                dtype=float,
            ).reshape(-1)

            result = pd.Series(
                values,
                index=asset_index,
                dtype=float,
            )

        if result.size != len(
            asset_index
        ):

            raise ValueError(
                f"{component_name} forecast returned "
                f"{result.size} values; expected "
                f"{len(asset_index)}."
            )

        if not result.index.equals(
            asset_index
        ):

            result = result.reindex(
                asset_index
            )

        if result.isna().any():

            raise ValueError(
                f"{component_name} forecast contains "
                "missing values."
            )

        values = result.to_numpy(
            dtype=float
        )

        if not np.isfinite(
            values
        ).all():

            raise ValueError(
                f"{component_name} forecast contains "
                "non-finite values."
            )

        return result.astype(
            float
        )

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self,
    ) -> dict:
        """
        Return deterministic component health information.
        """

        try:

            weights = np.array(
                [
                    self.MOMENTUM_WEIGHT,
                    self.TREND_WEIGHT,
                    self.MEAN_REVERSION_WEIGHT,
                ],
                dtype=float,
            )

            healthy = (
                np.isfinite(
                    weights
                ).all()
                and
                np.isclose(
                    weights.sum(),
                    1.0,
                    atol=1e-12,
                )
                and
                self.MINIMUM_HISTORY > 0
            )

            return {
                "status": (
                    "HEALTHY"
                    if healthy
                    else "UNHEALTHY"
                ),
                "api_version": (
                    self.API_VERSION
                ),
                "component": (
                    self.COMPONENT
                ),
                "minimum_history": (
                    self.MINIMUM_HISTORY
                ),
                "weights_sum": float(
                    weights.sum()
                ),
            }

        except Exception as exc:

            return {
                "status": "UNHEALTHY",
                "api_version": (
                    self.API_VERSION
                ),
                "component": (
                    self.COMPONENT
                ),
                "error": str(exc),
            }