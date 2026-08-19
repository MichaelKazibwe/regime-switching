from __future__ import annotations

import numpy as np
import pandas as pd


# ============================================================
# FORECAST MODEL VALIDATION
# ============================================================


def _validate_price_history(
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate and normalize the price-history input.

    Expected structure:

        index  -> time
        columns -> assets

    Returns
    -------
    pandas.DataFrame
        Validated copy of the input.
    """

    if not isinstance(
        prices,
        pd.DataFrame,
    ):
        raise TypeError(
            "Prices must be provided as a "
            "pandas DataFrame."
        )

    if prices.empty:
        raise ValueError(
            "Price history cannot be empty."
        )

    if prices.shape[1] == 0:
        raise ValueError(
            "Price history must contain at least "
            "one asset."
        )

    if not prices.index.is_monotonic_increasing:
        raise ValueError(
            "Price history index must be "
            "monotonically increasing."
        )

    if prices.columns.duplicated().any():
        duplicated = (
            prices.columns[
                prices.columns.duplicated()
            ]
            .tolist()
        )

        raise ValueError(
            "Price history contains duplicated "
            f"asset columns: {duplicated}."
        )

    numeric = prices.apply(
        pd.to_numeric,
        errors="coerce",
    )

    if not np.isfinite(
        numeric.to_numpy(
            dtype=float
        )
    ).all():

        raise ValueError(
            "Price history contains "
            "non-finite values."
        )

    if (
        numeric
        <= 0.0
    ).any().any():

        raise ValueError(
            "Price history must contain "
            "strictly positive prices."
        )

    return numeric.copy()


def _validate_forecast_output(
    forecast,
    asset_index,
    component_name: str,
) -> pd.Series:
    """
    Validate a forecast component and return it
    as an asset-indexed pandas Series.
    """

    if isinstance(
        forecast,
        pd.Series,
    ):

        result = forecast.copy()

    else:

        result = pd.Series(
            np.asarray(
                forecast,
                dtype=float,
            ).reshape(-1),
            index=asset_index,
            dtype=float,
        )

    if result.size != len(
        asset_index
    ):

        raise ValueError(
            f"{component_name} forecast returned "
            f"{result.size} values but "
            f"{len(asset_index)} assets were expected."
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


# ============================================================
# MOMENTUM FORECASTING
# ============================================================


class MomentumForecast:
    """
    Deterministic momentum forecast.

    Formula:

        P_t / P_{t-L} - 1

    where L is the configured lookback.
    """

    def forecast(
        self,
        prices,
        lookback: int = 252,
    ) -> pd.Series:

        prices = _validate_price_history(
            prices
        )

        if not isinstance(
            lookback,
            int,
        ) or lookback <= 0:

            raise ValueError(
                "Momentum lookback must be "
                "a positive integer."
            )

        if len(prices) < lookback:

            raise ValueError(
                "Insufficient history for momentum "
                f"forecast: required {lookback} "
                f"observations, received {len(prices)}."
            )

        forecast = (
            prices.iloc[-1]
            /
            prices.iloc[-lookback]
            -
            1.0
        )

        return _validate_forecast_output(
            forecast,
            prices.columns,
            "Momentum",
        )


# ============================================================
# TREND FORECASTING
# ============================================================


class TrendForecast:
    """
    Moving-average trend forecast.

    Formula:

        short_MA / long_MA - 1
    """

    def forecast(
        self,
        prices,
        short_window: int = 50,
        long_window: int = 200,
    ) -> pd.Series:

        prices = _validate_price_history(
            prices
        )

        if not isinstance(
            short_window,
            int,
        ) or short_window <= 0:

            raise ValueError(
                "Trend short_window must be "
                "a positive integer."
            )

        if not isinstance(
            long_window,
            int,
        ) or long_window <= 0:

            raise ValueError(
                "Trend long_window must be "
                "a positive integer."
            )

        if short_window > long_window:

            raise ValueError(
                "Trend short_window cannot exceed "
                "long_window."
            )

        if len(prices) < long_window:

            raise ValueError(
                "Insufficient history for trend "
                f"forecast: required {long_window} "
                f"observations, received {len(prices)}."
            )

        short_ma = (
            prices
            .rolling(
                short_window
            )
            .mean()
            .iloc[-1]
        )

        long_ma = (
            prices
            .rolling(
                long_window
            )
            .mean()
            .iloc[-1]
        )

        if (
            short_ma <= 0.0
        ).any() or (
            long_ma <= 0.0
        ).any():

            raise ValueError(
                "Trend moving averages must "
                "be strictly positive."
            )

        forecast = (
            short_ma
            /
            long_ma
            -
            1.0
        )

        return _validate_forecast_output(
            forecast,
            prices.columns,
            "Trend",
        )


# ============================================================
# MEAN REVERSION FORECAST
# ============================================================


class MeanReversionForecast:
    """
    Mean-reversion forecast based on the most recent
    return's standardized deviation from its trailing
    return distribution.

    Forecast:

        -z_t
    """

    def forecast(
        self,
        prices,
        lookback: int = 63,
    ) -> pd.Series:

        prices = _validate_price_history(
            prices
        )

        if not isinstance(
            lookback,
            int,
        ) or lookback <= 0:

            raise ValueError(
                "Mean-reversion lookback must "
                "be a positive integer."
            )

        returns = (
            prices
            .pct_change()
            .dropna(
                how="all"
            )
        )

        if len(returns) < lookback:

            raise ValueError(
                "Insufficient return history for "
                "mean-reversion forecast: "
                f"required {lookback} return "
                f"observations, received {len(returns)}."
            )

        recent_returns = (
            returns
            .tail(
                lookback
            )
        )

        mean = (
            recent_returns
            .mean()
        )

        std = (
            recent_returns
            .std()
        )

        latest = (
            returns
            .iloc[-1]
        )

        if (
            std <= 0.0
        ).any():

            zero_variance_assets = (
                std.index[
                    std <= 0.0
                ]
                .tolist()
            )

            raise ValueError(
                "Mean-reversion forecast cannot "
                "be calculated for zero-variance "
                f"assets: {zero_variance_assets}."
            )

        zscore = (
            (
                latest
                -
                mean
            )
            /
            std
        )

        forecast = -zscore

        return _validate_forecast_output(
            forecast,
            prices.columns,
            "Mean-reversion",
        )