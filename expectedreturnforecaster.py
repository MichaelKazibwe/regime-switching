from forecastmodels import (
    MomentumForecast,
    TrendForecast,
    MeanReversionForecast,
)

# ============================================================
# EXPECTED RETURN FORECASTER
# ============================================================

class ExpectedReturnForecaster:

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

    def forecast(
        self,
        prices
    ):

        momentum = (
            self.momentum.forecast(
                prices
            )
        )

        trend = (
            self.trend.forecast(
                prices
            )
        )

        reversion = (
            self.mean_reversion.forecast(
                prices
            )
        )

        expected_returns = (

            0.50 * momentum

            +

            0.30 * trend

            +

            0.20 * reversion

        )

        return expected_returns
