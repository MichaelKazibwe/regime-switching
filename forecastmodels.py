from __future__ import annotations

import numpy as np
import pandas as pd


# ======================================================================
# FORECAST MODEL VALIDATION
# ======================================================================


def _validate_price_history(
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate and normalize price-history input.

    Expected structure
    ------------------
    index:
        Time observations.

    columns:
        Asset tickers.

    Returns
    -------
    pandas.DataFrame
        A validated, numeric, defensive copy of the input.

    Notes
    -----
    This function deliberately does not mutate the caller's DataFrame.
    """

    if not isinstance(
        prices,
        pd.DataFrame,
    ):
        raise TypeError(
            "Prices must be provided as a pandas DataFrame."
        )

    if prices.empty:
        raise ValueError(
            "Price history cannot be empty."
        )

    if prices.shape[1] == 0:
        raise ValueError(
            "Price history must contain at least one asset."
        )

    if prices.columns.has_duplicates:
        duplicated = (
            prices.columns[
                prices.columns.duplicated()
            ]
            .tolist()
        )

        raise ValueError(
            "Price history contains duplicated asset columns: "
            f"{duplicated}."
        )

    if not prices.index.is_monotonic_increasing:
        raise ValueError(
            "Price history index must be monotonically increasing."
        )

    if prices.index.has_duplicates:
        raise ValueError(
            "Price history index cannot contain duplicate observations."
        )

    numeric = prices.apply(
        pd.to_numeric,
        errors="coerce",
    )

    values = numeric.to_numpy(
        dtype=float
    )

    if values.size == 0:
        raise ValueError(
            "Price history contains no observations."
        )

    if not np.isfinite(
        values
    ).all():
        raise ValueError(
            "Price history contains non-finite values."
        )

    if (
        numeric <= 0.0
    ).any().any():
        raise ValueError(
            "Price history must contain strictly positive prices."
        )

    return numeric.copy()


def _validate_asset_index(
    asset_index: pd.Index,
) -> pd.Index:
    """
    Validate the asset index used by forecast outputs.
    """

    if not isinstance(
        asset_index,
        pd.Index,
    ):
        asset_index = pd.Index(
            asset_index
        )

    if len(asset_index) == 0:
        raise ValueError(
            "Asset index cannot be empty."
        )

    if asset_index.has_duplicates:
        raise ValueError(
            "Asset index cannot contain duplicate assets."
        )

    return asset_index


def _validate_forecast_output(
    forecast,
    asset_index: pd.Index,
    component_name: str,
) -> pd.Series:
    """
    Validate a forecast component and return it as an
    asset-indexed pandas Series.

    The returned Series always has exactly the supplied
    asset index and therefore cannot silently retain an
    incompatible index.
    """

    asset_index = _validate_asset_index(
        asset_index
    )

    # --------------------------------------------------------------
    # SERIES INPUT
    # --------------------------------------------------------------

    if isinstance(
        forecast,
        pd.Series,
    ):

        result = forecast.copy()

        if result.index.has_duplicates:
            raise ValueError(
                f"{component_name} forecast contains "
                "duplicate asset labels."
            )

        if len(result) != len(asset_index):

            raise ValueError(
                f"{component_name} forecast returned "
                f"{len(result)} values but "
                f"{len(asset_index)} assets were expected."
            )

        # Explicitly align by asset label.
        result = result.reindex(
            asset_index
        )

    # --------------------------------------------------------------
    # ARRAY-LIKE INPUT
    # --------------------------------------------------------------

    else:

        try:

            values = np.asarray(
                forecast,
                dtype=float,
            ).reshape(-1)

        except Exception as exc:

            raise ValueError(
                f"{component_name} forecast could not "
                "be converted to numeric values."
            ) from exc

        if values.size != len(asset_index):

            raise ValueError(
                f"{component_name} forecast returned "
                f"{values.size} values but "
                f"{len(asset_index)} assets were expected."
            )

        result = pd.Series(
            values,
            index=asset_index,
            dtype=float,
        )

    # --------------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------------

    if not result.index.equals(
        asset_index
    ):

        raise ValueError(
            f"{component_name} forecast index does not "
            "match the expected asset index."
        )

    if result.isna().any():

        missing_assets = (
            result.index[
                result.isna()
            ]
            .tolist()
        )

        raise ValueError(
            f"{component_name} forecast contains missing "
            f"values for assets: {missing_assets}."
        )

    values = result.to_numpy(
        dtype=float
    )

    if not np.isfinite(
        values
    ).all():

        raise ValueError(
            f"{component_name} forecast contains non-finite values."
        )

    return result.astype(
        float
    )


def _align_asset_series(
    series: pd.Series,
    asset_index: pd.Index,
    component_name: str,
) -> pd.Series:
    """
    Explicitly align a Series to the canonical asset index.

    This helper exists specifically to prevent accidental pandas
    label alignment from propagating incompatible indexes through
    forecast calculations.
    """

    if not isinstance(
        series,
        pd.Series,
    ):
        raise TypeError(
            f"{component_name} must be a pandas Series."
        )

    if series.index.has_duplicates:
        raise ValueError(
            f"{component_name} contains duplicate asset labels."
        )

    aligned = series.reindex(
        asset_index
    )

    if aligned.isna().any():

        missing_assets = (
            aligned.index[
                aligned.isna()
            ]
            .tolist()
        )

        raise ValueError(
            f"{component_name} cannot be aligned to the "
            f"asset universe. Missing assets: {missing_assets}."
        )

    values = aligned.to_numpy(
        dtype=float
    )

    if not np.isfinite(
        values
    ).all():

        raise ValueError(
            f"{component_name} contains non-finite values."
        )

    return aligned.astype(
        float
    )


def _validate_window(
    value: int,
    name: str,
) -> None:
    """
    Validate a positive integer forecasting window.
    """

    if not isinstance(
        value,
        (int, np.integer),
    ) or isinstance(
        value,
        bool,
    ) or value <= 0:

        raise ValueError(
            f"{name} must be a positive integer."
        )


# ======================================================================
# MOMENTUM FORECASTING
# ======================================================================


class MomentumForecast:
    """
    Deterministic momentum forecast.

    Formula
    -------

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

        _validate_window(
            lookback,
            "Momentum lookback",
        )

        if len(prices) < lookback:

            raise ValueError(
                "Insufficient history for momentum forecast: "
                f"required {lookback} observations, "
                f"received {len(prices)}."
            )

        asset_index = prices.columns

        latest_prices = (
            prices.iloc[-1]
            .copy()
        )

        historical_prices = (
            prices.iloc[-lookback]
            .copy()
        )

        latest_prices = _align_asset_series(
            latest_prices,
            asset_index,
            "Momentum latest prices",
        )

        historical_prices = _align_asset_series(
            historical_prices,
            asset_index,
            "Momentum historical prices",
        )

        # Convert to NumPy arrays before arithmetic so pandas
        # cannot introduce unintended label alignment.
        latest_values = latest_prices.to_numpy(
            dtype=float
        )

        historical_values = historical_prices.to_numpy(
            dtype=float
        )

        forecast_values = (
            latest_values
            /
            historical_values
            -
            1.0
        )

        forecast = pd.Series(
            forecast_values,
            index=asset_index,
            dtype=float,
        )

        return _validate_forecast_output(
            forecast,
            asset_index,
            "Momentum",
        )


# ======================================================================
# TREND FORECASTING
# ======================================================================


class TrendForecast:
    """
    Moving-average trend forecast.

    Formula
    -------

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

        _validate_window(
            short_window,
            "Trend short_window",
        )

        _validate_window(
            long_window,
            "Trend long_window",
        )

        if short_window > long_window:

            raise ValueError(
                "Trend short_window cannot exceed long_window."
            )

        if len(prices) < long_window:

            raise ValueError(
                "Insufficient history for trend forecast: "
                f"required {long_window} observations, "
                f"received {len(prices)}."
            )

        asset_index = prices.columns

        short_ma = (
            prices
            .rolling(
                window=short_window,
                min_periods=short_window,
            )
            .mean()
            .iloc[-1]
        )

        long_ma = (
            prices
            .rolling(
                window=long_window,
                min_periods=long_window,
            )
            .mean()
            .iloc[-1]
        )

        short_ma = _align_asset_series(
            short_ma,
            asset_index,
            "Trend short moving average",
        )

        long_ma = _align_asset_series(
            long_ma,
            asset_index,
            "Trend long moving average",
        )

        short_values = short_ma.to_numpy(
            dtype=float
        )

        long_values = long_ma.to_numpy(
            dtype=float
        )

        if not (
            short_values > 0.0
        ).all():

            raise ValueError(
                "Trend short moving averages must "
                "be strictly positive."
            )

        if not (
            long_values > 0.0
        ).all():

            raise ValueError(
                "Trend long moving averages must "
                "be strictly positive."
            )

        forecast_values = (
            short_values
            /
            long_values
            -
            1.0
        )

        forecast = pd.Series(
            forecast_values,
            index=asset_index,
            dtype=float,
        )

        return _validate_forecast_output(
            forecast,
            asset_index,
            "Trend",
        )


# ======================================================================
# MEAN REVERSION FORECAST
# ======================================================================


class MeanReversionForecast:
    """
    Mean-reversion forecast based on the most recent return's
    standardized deviation from its trailing return distribution.

    Formula
    -------

        z_t = (r_t - mean(r)) / std(r)

        forecast = -z_t

    The implementation explicitly aligns all intermediate
    Series to the canonical asset index before performing
    calculations.
    """

    def forecast(
        self,
        prices,
        lookback: int = 63,
    ) -> pd.Series:

        prices = _validate_price_history(
            prices
        )

        _validate_window(
            lookback,
            "Mean-reversion lookback",
        )

        asset_index = prices.columns

        # --------------------------------------------------------------
        # RETURNS
        # --------------------------------------------------------------

        returns = (
            prices
            .pct_change(
                fill_method=None
            )
            .iloc[1:]
            .copy()
        )

        if returns.empty:

            raise ValueError(
                "Unable to calculate returns from "
                "the supplied price history."
            )

        if len(returns) < lookback:

            raise ValueError(
                "Insufficient return history for "
                "mean-reversion forecast: "
                f"required {lookback} return observations, "
                f"received {len(returns)}."
            )

        # Explicitly enforce canonical asset ordering.
        returns = returns.reindex(
            columns=asset_index
        )

        if not returns.columns.equals(
            asset_index
        ):

            raise ValueError(
                "Mean-reversion return columns do not "
                "match the price-history asset universe."
            )

        # --------------------------------------------------------------
        # TRAILING RETURN DISTRIBUTION
        # --------------------------------------------------------------

        recent_returns = (
            returns
            .tail(
                lookback
            )
            .copy()
        )

        if len(recent_returns) != lookback:

            raise ValueError(
                "Mean-reversion trailing return window "
                "has an unexpected length."
            )

        mean = (
            recent_returns
            .mean(
                axis=0
            )
        )

        std = (
            recent_returns
            .std(
                axis=0,
                ddof=1,
            )
        )

        latest = (
            returns
            .iloc[-1]
            .copy()
        )

        # --------------------------------------------------------------
        # EXPLICIT ASSET ALIGNMENT
        # --------------------------------------------------------------

        mean = _align_asset_series(
            mean,
            asset_index,
            "Mean-reversion trailing mean",
        )

        std = _align_asset_series(
            std,
            asset_index,
            "Mean-reversion trailing standard deviation",
        )

        latest = _align_asset_series(
            latest,
            asset_index,
            "Mean-reversion latest return",
        )

        # --------------------------------------------------------------
        # ZERO-VARIANCE VALIDATION
        # --------------------------------------------------------------

        std_values = std.to_numpy(
            dtype=float
        )

        zero_variance_mask = (
            std_values <= 0.0
        )

        if zero_variance_mask.any():

            zero_variance_assets = (
                asset_index[
                    zero_variance_mask
                ]
                .tolist()
            )

            raise ValueError(
                "Mean-reversion forecast cannot be calculated "
                "for zero-variance assets: "
                f"{zero_variance_assets}."
            )

        # --------------------------------------------------------------
        # NUMPY CALCULATION
        # --------------------------------------------------------------
        #
        # Once the Series have been explicitly aligned, arithmetic
        # is performed on NumPy arrays. This prevents pandas from
        # silently performing label-based alignment during the
        # critical forecast calculation.
        # --------------------------------------------------------------

        latest_values = latest.to_numpy(
            dtype=float
        )

        mean_values = mean.to_numpy(
            dtype=float
        )

        std_values = std.to_numpy(
            dtype=float
        )

        zscore_values = (
            latest_values
            -
            mean_values
        ) / std_values

        forecast_values = (
            -zscore_values
        )

        forecast = pd.Series(
            forecast_values,
            index=asset_index,
            dtype=float,
        )

        return _validate_forecast_output(
            forecast,
            asset_index,
            "Mean-reversion",
        )


# ======================================================================
# MODULE CONTRACT
# ======================================================================


__all__ = [
    "MomentumForecast",
    "TrendForecast",
    "MeanReversionForecast",
]