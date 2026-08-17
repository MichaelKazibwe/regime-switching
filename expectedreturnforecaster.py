from __future__ import annotations

from forecastmodels import (
    MomentumForecast,
    TrendForecast,
    MeanReversionForecast,
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

    The combined forecasting model requires sufficient price
    history for every underlying forecasting component.

    Current production requirements:
        Momentum       : 252 price observations
        Trend          : 200 price observations
        Mean reversion : 63 return observations

    Therefore the combined model requires at least 252 price
    observations.
    """

    MOMENTUM_LOOKBACK = 252
    TREND_LOOKBACK = 200
    MEAN_REVERSION_LOOKBACK = 63

    MOMENTUM_WEIGHT = 0.50
    TREND_WEIGHT = 0.30
    MEAN_REVERSION_WEIGHT = 0.20

    MINIMUM_HISTORY = max(
        MOMENTUM_LOOKBACK,
        TREND_LOOKBACK,
        MEAN_REVERSION_LOOKBACK + 1,
    )

    def __init__(self):

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

    # ========================================================
    # HISTORY VALIDATION
    # ========================================================

    @classmethod
    def minimum_history(
        cls,
    ) -> int:
        """
        Return the minimum number of price observations required
        by the complete expected-return forecasting stack.
        """

        return cls.MINIMUM_HISTORY

    @classmethod
    def validate_history(
        cls,
        prices,
    ) -> None:
        """
        Validate that sufficient price history exists for all
        production forecasting components.
        """

        try:
            observations = len(
                prices
            )

        except TypeError as exc:

            raise TypeError(
                "Prices must be a sized time-series object."
            ) from exc

        if observations < cls.MINIMUM_HISTORY:

            raise ValueError(
                "Insufficient history for expected-return "
                "forecasting: "
                f"required at least {cls.MINIMUM_HISTORY} "
                f"price observations, received "
                f"{observations}."
            )

    # ========================================================
    # FORECAST
    # ========================================================

    def forecast(
        self,
        prices,
    ):

        self.validate_history(
            prices
        )

        self.last_observations = len(
            prices
        )

        momentum = (
            self.momentum.forecast(
                prices,
                lookback=self.MOMENTUM_LOOKBACK,
            )
        )

        trend = (
            self.trend.forecast(
                prices,
                short_window=50,
                long_window=self.TREND_LOOKBACK,
            )
        )

        reversion = (
            self.mean_reversion.forecast(
                prices,
                lookback=self.MEAN_REVERSION_LOOKBACK,
            )
        )

        self.last_components = {
            "momentum": momentum,
            "trend": trend,
            "mean_reversion": reversion,
        }

        expected_returns = (
            self.MOMENTUM_WEIGHT
            * momentum
            +
            self.TREND_WEIGHT
            * trend
            +
            self.MEAN_REVERSION_WEIGHT
            * reversion
        )

        self.last_forecast = expected_returns

        return expected_returns
