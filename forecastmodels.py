# ============================================================
# MOMENTUM FORECASTING
# ============================================================

class MomentumForecast:

    def forecast(
        self,
        prices,
        lookback=252
    ):

        if len(prices) < lookback:

            raise ValueError(
                "Insufficient history"
            )

        momentum = (

            prices.iloc[-1]

            /

            prices.iloc[-lookback]

            - 1.0

        )

        return momentum
    
# ============================================================
# TREND FORECASTING
# ============================================================

class TrendForecast:

    def forecast(
        self,
        prices,
        short_window=50,
        long_window=200
    ):

        short_ma = (

            prices
            .rolling(short_window)
            .mean()
            .iloc[-1]

        )

        long_ma = (

            prices
            .rolling(long_window)
            .mean()
            .iloc[-1]

        )

        signal = (

            short_ma
            /
            long_ma

            - 1.0

        )

        return signal
    
# ============================================================
# MEAN REVERSION
# ============================================================

class MeanReversionForecast:

    def forecast(
        self,
        prices,
        lookback=63
    ):

        returns = (

            prices
            .pct_change()
            .dropna()

        )

        zscore = (

            (
                returns.iloc[-1]
                -
                returns.tail(lookback).mean()
            )

            /

            returns.tail(lookback).std()

        )

        return -zscore
