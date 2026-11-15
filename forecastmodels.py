"""
================================================================
FORECAST MODELS

Institutional signal-generation layer.

Provides three deterministic forecast signals:

    1. Momentum
    2. Trend
    3. Mean reversion

A forecast signal is NOT an expected return.

This module therefore guarantees the integrity of the raw signal
outputs while leaving economic calibration to the next layer.

Production invariants
---------------------

Every successful forecast:

    * is a pandas Series
    * contains exactly one value per asset
    * preserves the input asset order
    * contains no NaN values
    * contains no infinite values
    * contains only numeric values
    * does not mutate the caller's price data

Signal definitions
------------------

Momentum:

    P_t / P_(t-L) - 1

Trend:

    SMA_short / SMA_long - 1

Mean reversion:

    -z_score(return)

================================================================
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


# ============================================================
# SIGNAL VALIDATION
# ============================================================


class ForecastSignalValidator:
    """
    Central validation boundary for forecast signals.

    All forecast components should pass their output through this
    validator before returning it to the orchestration layer.
    """

    @staticmethod
    def validate_prices(
        prices: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Validate and defensively copy price history.
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
                "Prices must contain at least one asset."
            )

        if prices.columns.duplicated().any():
            duplicated = (
                prices.columns[
                    prices.columns.duplicated()
                ]
                .tolist()
            )

            raise ValueError(
                "Prices contain duplicated asset "
                f"columns: {duplicated}."
            )

        if not prices.index.is_monotonic_increasing:
            raise ValueError(
                "Price index must be monotonically increasing."
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
                "Prices must contain strictly positive values."
            )

        return numeric.copy()

    @staticmethod
    def validate_signal(
        signal: Any,
        asset_index: pd.Index,
        signal_name: str,
    ) -> pd.Series:
        """
        Validate a completed forecast signal.

        The returned Series is guaranteed to have the canonical
        asset index and ordering.
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
                "Signal asset index cannot be empty."
            )

        if asset_index.has_duplicates:
            raise ValueError(
                "Signal asset index contains duplicate assets."
            )

        # ----------------------------------------------------
        # Convert to Series
        # ----------------------------------------------------

        if isinstance(
            signal,
            pd.Series,
        ):
            result = signal.copy()

        else:
            try:
                values = np.asarray(
                    signal,
                    dtype=float,
                ).reshape(-1)

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise ValueError(
                    f"{signal_name} signal could not be "
                    "converted to numeric values."
                ) from exc

            if values.size != len(asset_index):
                raise ValueError(
                    f"{signal_name} signal returned "
                    f"{values.size} values; expected "
                    f"{len(asset_index)}."
                )

            result = pd.Series(
                values,
                index=asset_index,
                dtype=float,
            )

        # ----------------------------------------------------
        # Dimension
        # ----------------------------------------------------

        if result.size != len(asset_index):
            raise ValueError(
                f"{signal_name} signal returned "
                f"{result.size} values; expected "
                f"{len(asset_index)}."
            )

        # ----------------------------------------------------
        # Duplicate labels
        # ----------------------------------------------------

        if result.index.has_duplicates:
            duplicated = (
                result.index[
                    result.index.duplicated()
                ]
                .tolist()
            )

            raise ValueError(
                f"{signal_name} signal contains "
                f"duplicate asset labels: {duplicated}."
            )

        # ----------------------------------------------------
        # Asset-set validation
        # ----------------------------------------------------

        if set(result.index) != set(asset_index):
            missing = [
                asset
                for asset in asset_index
                if asset not in result.index
            ]

            unexpected = [
                asset
                for asset in result.index
                if asset not in asset_index
            ]

            raise ValueError(
                f"{signal_name} signal asset mismatch. "
                f"Missing={missing}, "
                f"unexpected={unexpected}."
            )

        # ----------------------------------------------------
        # Canonical ordering
        # ----------------------------------------------------

        result = result.reindex(
            asset_index
        )

        # ----------------------------------------------------
        # Numeric conversion
        # ----------------------------------------------------

        try:
            result = result.astype(
                float
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise ValueError(
                f"{signal_name} signal contains "
                "non-numeric values."
            ) from exc

        # ----------------------------------------------------
        # Missing values
        # ----------------------------------------------------

        if result.isna().any():
            missing_assets = (
                result.index[
                    result.isna()
                ]
                .tolist()
            )

            raise ValueError(
                f"{signal_name} signal contains "
                f"missing values for assets: "
                f"{missing_assets}."
            )

        # ----------------------------------------------------
        # Finite values
        # ----------------------------------------------------

        values = result.to_numpy(
            dtype=float
        )

        if not np.isfinite(
            values
        ).all():

            invalid_assets = (
                result.index[
                    ~np.isfinite(values)
                ]
                .tolist()
            )

            raise ValueError(
                f"{signal_name} signal contains "
                f"non-finite values for assets: "
                f"{invalid_assets}."
            )

        # ----------------------------------------------------
        # Final canonical output
        # ----------------------------------------------------

        return pd.Series(
            values,
            index=asset_index,
            dtype=float,
            name=signal_name,
        )


# ============================================================
# BASE SIGNAL MODEL
# ============================================================


class _BaseForecast:
    """
    Internal base class for forecast signal components.
    """

    API_VERSION = "1.0.0"

    COMPONENT = "Forecast"

    @staticmethod
    def _validate_prices(
        prices: pd.DataFrame,
    ) -> pd.DataFrame:

        return ForecastSignalValidator.validate_prices(
            prices
        )

    @staticmethod
    def _validate_history(
        prices: pd.DataFrame,
        minimum_history: int,
        component: str,
    ) -> None:

        if len(prices) < minimum_history:
            raise ValueError(
                f"Insufficient history for {component}: "
                f"required at least {minimum_history} "
                f"observations, received {len(prices)}."
            )

    @staticmethod
    def _validate_parameter(
        value: int,
        name: str,
        minimum: int = 1,
    ) -> int:

        if isinstance(
            value,
            bool,
        ):
            raise TypeError(
                f"{name} must be an integer."
            )

        try:
            value = int(value)

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise TypeError(
                f"{name} must be an integer."
            ) from exc

        if value < minimum:
            raise ValueError(
                f"{name} must be at least {minimum}."
            )

        return value


# ============================================================
# MOMENTUM FORECAST
# ============================================================


class MomentumForecast(
    _BaseForecast
):
    """
    Cross-sectional momentum signal.

    Formula
    -------

        P_t / P_(t-L) - 1
    """

    COMPONENT = "Momentum"

    DEFAULT_LOOKBACK = 252

    def forecast(
        self,
        prices: pd.DataFrame,
        lookback: int = DEFAULT_LOOKBACK,
    ) -> pd.Series:

        prices = self._validate_prices(
            prices
        )

        lookback = self._validate_parameter(
            lookback,
            "lookback",
        )

        self._validate_history(
            prices,
            lookback,
            self.COMPONENT,
        )

        signal = (
            prices.iloc[-1]
            /
            prices.iloc[-lookback - 1]
            -
            1.0
        )

        return ForecastSignalValidator.validate_signal(
            signal,
            prices.columns,
            self.COMPONENT,
        )


# ============================================================
# TREND FORECAST
# ============================================================


class TrendForecast(
    _BaseForecast
):
    """
    Moving-average trend signal.

    Formula
    -------

        SMA_short / SMA_long - 1
    """

    COMPONENT = "Trend"

    DEFAULT_SHORT_WINDOW = 50

    DEFAULT_LONG_WINDOW = 200

    def forecast(
        self,
        prices: pd.DataFrame,
        short_window: int = DEFAULT_SHORT_WINDOW,
        long_window: int = DEFAULT_LONG_WINDOW,
    ) -> pd.Series:

        prices = self._validate_prices(
            prices
        )

        short_window = self._validate_parameter(
            short_window,
            "short_window",
        )

        long_window = self._validate_parameter(
            long_window,
            "long_window",
        )

        if short_window >= long_window:
            raise ValueError(
                "short_window must be smaller than "
                "long_window."
            )

        self._validate_history(
            prices,
            long_window,
            self.COMPONENT,
        )

        short_ma = (
            prices.iloc[
                -short_window:
            ]
            .mean()
        )

        long_ma = (
            prices.iloc[
                -long_window:
            ]
            .mean()
        )

        if (
            long_ma <= 0
        ).any():

            raise ValueError(
                "Trend calculation encountered "
                "non-positive long-window averages."
            )

        signal = (
            short_ma
            /
            long_ma
            -
            1.0
        )

        return ForecastSignalValidator.validate_signal(
            signal,
            prices.columns,
            self.COMPONENT,
        )


# ============================================================
# MEAN REVERSION FORECAST
# ============================================================


class MeanReversionForecast(
    _BaseForecast
):
    """
    Mean-reversion signal based on return z-score.

    Formula
    -------

        -z(return)
    """

    COMPONENT = "MeanReversion"

    DEFAULT_LOOKBACK = 63

    def forecast(
        self,
        prices: pd.DataFrame,
        lookback: int = DEFAULT_LOOKBACK,
    ) -> pd.Series:

        prices = self._validate_prices(
            prices
        )

        lookback = self._validate_parameter(
            lookback,
            "lookback",
        )

        minimum_history = (
            lookback + 1
        )

        self._validate_history(
            prices,
            minimum_history,
            self.COMPONENT,
        )

        returns = (
            prices
            .pct_change(
                fill_method=None
            )
            .dropna()
        )

        if len(returns) < lookback:
            raise ValueError(
                f"Insufficient return history for "
                f"{self.COMPONENT}: required at least "
                f"{lookback} observations."
            )

        window = (
            returns.iloc[
                -lookback:
            ]
        )

        mean = window.mean()

        std = window.std(
            ddof=1
        )

        if (
            std <= 0
        ).any():

            zero_variance_assets = (
                std.index[
                    std <= 0
                ]
                .tolist()
            )

            raise ValueError(
                "Mean-reversion calculation encountered "
                "zero-variance returns for assets: "
                f"{zero_variance_assets}."
            )

        latest_returns = (
            returns.iloc[-1]
        )

        signal = -(
            latest_returns - mean
        ) / std

        return ForecastSignalValidator.validate_signal(
            signal,
            prices.columns,
            self.COMPONENT,
        )


# ============================================================
# REGRESSION TESTS
# ============================================================


def test_forecast_signal_validator():

    assets = pd.Index(
        [
            "SPY",
            "QQQ",
            "TLT",
        ]
    )

    # --------------------------------------------------------
    # Valid signal
    # --------------------------------------------------------

    signal = pd.Series(
        [
            0.10,
            0.20,
            -0.05,
        ],
        index=assets,
    )

    result = (
        ForecastSignalValidator.validate_signal(
            signal,
            assets,
            "Test",
        )
    )

    assert isinstance(
        result,
        pd.Series,
    )

    assert result.index.equals(
        assets
    )

    assert np.isfinite(
        result.values
    ).all()

    # --------------------------------------------------------
    # Ordering must be canonicalized
    # --------------------------------------------------------

    reversed_signal = pd.Series(
        [
            -0.05,
            0.20,
            0.10,
        ],
        index=[
            "TLT",
            "QQQ",
            "SPY",
        ],
    )

    result = (
        ForecastSignalValidator.validate_signal(
            reversed_signal,
            assets,
            "Test",
        )
    )

    assert result.index.equals(
        assets
    )

    assert np.allclose(
        result.values,
        [
            0.10,
            0.20,
            -0.05,
        ],
    )

    # --------------------------------------------------------
    # Missing asset
    # --------------------------------------------------------

    try:

        ForecastSignalValidator.validate_signal(
            pd.Series(
                [0.10, 0.20],
                index=[
                    "SPY",
                    "QQQ",
                ],
            ),
            assets,
            "Test",
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    # --------------------------------------------------------
    # Duplicate asset
    # --------------------------------------------------------

    try:

        ForecastSignalValidator.validate_signal(
            pd.Series(
                [0.10, 0.20, 0.30],
                index=[
                    "SPY",
                    "SPY",
                    "TLT",
                ],
            ),
            assets,
            "Test",
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    # --------------------------------------------------------
    # NaN
    # --------------------------------------------------------

    try:

        ForecastSignalValidator.validate_signal(
            pd.Series(
                [0.10, np.nan, 0.30],
                index=assets,
            ),
            assets,
            "Test",
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    # --------------------------------------------------------
    # Infinity
    # --------------------------------------------------------

    try:

        ForecastSignalValidator.validate_signal(
            pd.Series(
                [0.10, np.inf, 0.30],
                index=assets,
            ),
            assets,
            "Test",
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass


def test_momentum_forecast():

    periods = 300

    prices = pd.DataFrame(
        {
            "SPY": np.linspace(
                100.0,
                150.0,
                periods,
            ),
            "QQQ": np.linspace(
                100.0,
                130.0,
                periods,
            ),
            "TLT": np.linspace(
                100.0,
                90.0,
                periods,
            ),
        }
    )

    model = MomentumForecast()

    signal = model.forecast(
        prices,
        lookback=252,
    )

    assert isinstance(
        signal,
        pd.Series,
    )

    assert signal.index.equals(
        prices.columns
    )

    assert np.isfinite(
        signal.values
    ).all()

    expected = (
        prices.iloc[-1]
        /
        prices.iloc[-253]
        -
        1.0
    )

    assert np.allclose(
        signal.values,
        expected.values,
    )


def test_trend_forecast():

    periods = 300

    prices = pd.DataFrame(
        {
            "SPY": np.linspace(
                100.0,
                150.0,
                periods,
            ),
            "QQQ": np.linspace(
                100.0,
                130.0,
                periods,
            ),
            "TLT": np.linspace(
                100.0,
                90.0,
                periods,
            ),
        }
    )

    model = TrendForecast()

    signal = model.forecast(
        prices,
        short_window=50,
        long_window=200,
    )

    assert isinstance(
        signal,
        pd.Series,
    )

    assert signal.index.equals(
        prices.columns
    )

    assert np.isfinite(
        signal.values
    ).all()

    short_ma = (
        prices.iloc[-50:]
        .mean()
    )

    long_ma = (
        prices.iloc[-200:]
        .mean()
    )

    expected = (
        short_ma
        /
        long_ma
        -
        1.0
    )

    assert np.allclose(
        signal.values,
        expected.values,
    )


def test_mean_reversion_forecast():

    np.random.seed(42)

    periods = 200

    returns = np.random.normal(
        0.001,
        0.02,
        size=(periods, 3),
    )

    prices = pd.DataFrame(
        100.0
        *
        np.exp(
            np.cumsum(
                returns,
                axis=0,
            )
        ),
        columns=[
            "SPY",
            "QQQ",
            "TLT",
        ],
    )

    model = MeanReversionForecast()

    signal = model.forecast(
        prices,
        lookback=63,
    )

    assert isinstance(
        signal,
        pd.Series,
    )

    assert signal.index.equals(
        prices.columns
    )

    assert np.isfinite(
        signal.values
    ).all()


def test_forecast_history_validation():

    prices = pd.DataFrame(
        np.ones(
            (50, 3)
        ),
        columns=[
            "SPY",
            "QQQ",
            "TLT",
        ],
    )

    try:

        MomentumForecast().forecast(
            prices,
            lookback=252,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    try:

        TrendForecast().forecast(
            prices,
            short_window=10,
            long_window=200,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    try:

        MeanReversionForecast().forecast(
            prices,
            lookback=63,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass


def test_forecast_parameter_validation():

    prices = pd.DataFrame(
        np.ones(
            (300, 3)
        ),
        columns=[
            "SPY",
            "QQQ",
            "TLT",
        ],
    )

    try:

        MomentumForecast().forecast(
            prices,
            lookback=0,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    try:

        TrendForecast().forecast(
            prices,
            short_window=200,
            long_window=50,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    try:

        MeanReversionForecast().forecast(
            prices,
            lookback=0,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass


def test_forecast_price_validation():

    prices = pd.DataFrame(
        {
            "SPY": [100.0, 101.0, np.nan],
            "QQQ": [100.0, 101.0, 102.0],
        }
    )

    try:

        MomentumForecast().forecast(
            prices,
            lookback=1,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    prices = pd.DataFrame(
        {
            "SPY": [100.0, 101.0, 102.0],
            "QQQ": [100.0, 101.0, 102.0],
        }
    )

    # Python dictionaries cannot preserve duplicate keys, so
    # duplicate-column validation is tested directly.

    duplicate_columns = pd.DataFrame(
        [
            [100.0, 100.0],
            [101.0, 101.0],
            [102.0, 102.0],
        ],
        columns=[
            "SPY",
            "SPY",
        ],
    )

    try:

        MomentumForecast().forecast(
            duplicate_columns,
            lookback=1,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass


def test_forecast_models_do_not_mutate_prices():

    np.random.seed(42)

    prices = pd.DataFrame(
        100.0
        *
        np.exp(
            np.cumsum(
                np.random.normal(
                    0.001,
                    0.02,
                    size=(300, 3),
                ),
                axis=0,
            )
        ),
        columns=[
            "SPY",
            "QQQ",
            "TLT",
        ],
    )

    original = prices.copy(
        deep=True
    )

    MomentumForecast().forecast(
        prices,
        lookback=252,
    )

    TrendForecast().forecast(
        prices,
        short_window=50,
        long_window=200,
    )

    MeanReversionForecast().forecast(
        prices,
        lookback=63,
    )

    assert prices.equals(
        original
    )


def test_forecast_signal_api():

    assert MomentumForecast.API_VERSION == "1.0.0"

    assert TrendForecast.API_VERSION == "1.0.0"

    assert MeanReversionForecast.API_VERSION == "1.0.0"

    assert (
        MomentumForecast.COMPONENT
        == "Momentum"
    )

    assert (
        TrendForecast.COMPONENT
        == "Trend"
    )

    assert (
        MeanReversionForecast.COMPONENT
        == "MeanReversion"
    )


# ============================================================
# REGRESSION ENTRY POINT
# ============================================================


def run_regression_tests():

    test_forecast_signal_validator()

    test_momentum_forecast()

    test_trend_forecast()

    test_mean_reversion_forecast()

    test_forecast_history_validation()

    test_forecast_parameter_validation()

    test_forecast_price_validation()

    test_forecast_models_do_not_mutate_prices()

    test_forecast_signal_api()

    print(
        "A15.1 forecast signal tests passed."
    )


if __name__ == "__main__":

    run_regression_tests()