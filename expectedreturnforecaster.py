from __future__ import annotations

from typing import Any

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

    The forecast is constructed from three deterministic
    component forecasts:

        Momentum       : 50%
        Trend          : 30%
        Mean reversion : 20%

    Component requirements
    ----------------------

    Momentum:
        252 price observations.

    Trend:
        200 price observations.

    Mean reversion:
        63 return observations, which requires at least
        64 price observations.

    Therefore the complete forecasting stack requires:

        252 price observations.

    Important contract
    ------------------

    ``forecast()`` accepts PRICE HISTORY.

    It does not accept a return matrix.

    Expected input structure:

        index   -> chronological observations
        columns -> asset tickers
        values  -> strictly positive prices

    The returned Series always has:

        index   -> exactly the same ticker order
        values  -> finite expected-return forecasts
    """

    API_VERSION = "1.0.0"

    COMPONENT = "ExpectedReturnForecaster"

    # --------------------------------------------------------
    # COMPONENT PARAMETERS
    # --------------------------------------------------------

    MOMENTUM_LOOKBACK = 252

    TREND_LOOKBACK = 200

    TREND_SHORT_WINDOW = 50

    MEAN_REVERSION_LOOKBACK = 63

    # --------------------------------------------------------
    # COMPONENT WEIGHTS
    # --------------------------------------------------------

    MOMENTUM_WEIGHT = 0.50

    TREND_WEIGHT = 0.30

    MEAN_REVERSION_WEIGHT = 0.20

    # --------------------------------------------------------
    # COMPLETE STACK REQUIREMENT
    # --------------------------------------------------------

    MINIMUM_HISTORY = max(
        MOMENTUM_LOOKBACK,
        TREND_LOOKBACK,
        MEAN_REVERSION_LOOKBACK + 1,
    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(self) -> None:
        """
        Initialize the production forecasting stack.
        """

        self.momentum = MomentumForecast()

        self.trend = TrendForecast()

        self.mean_reversion = MeanReversionForecast()

        # ----------------------------------------------------
        # Last successful forecast
        # ----------------------------------------------------

        self.last_forecast: pd.Series | None = None

        # ----------------------------------------------------
        # Last component forecasts
        # ----------------------------------------------------

        self.last_components: dict[str, pd.Series] | None = None

        # ----------------------------------------------------
        # Last observation count
        # ----------------------------------------------------

        self.last_observations: int | None = None

        # ----------------------------------------------------
        # Last diagnostics
        # ----------------------------------------------------

        self.last_diagnostics: dict[str, Any] | None = None

    # ========================================================
    # HISTORY
    # ========================================================

    @classmethod
    def minimum_history(cls) -> int:
        """
        Return the minimum number of price observations required
        by the complete forecasting stack.
        """

        return int(cls.MINIMUM_HISTORY)

    @classmethod
    def validate_history(
        cls,
        prices: pd.DataFrame,
    ) -> None:
        """
        Validate the minimum historical observation requirement.

        Parameters
        ----------
        prices:
            Validated price-history DataFrame.

        Raises
        ------
        TypeError
            If the object does not have a usable length.

        ValueError
            If insufficient observations are supplied.
        """

        if not isinstance(
            prices,
            pd.DataFrame,
        ):
            raise TypeError(
                "Prices must be a pandas DataFrame."
            )

        observations = len(prices)

        if observations < cls.MINIMUM_HISTORY:
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
        prices: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Validate and normalize price history.

        Requirements
        ------------

        * pandas DataFrame
        * non-empty
        * at least one asset
        * unique asset columns
        * monotonically increasing index
        * numeric values
        * finite values
        * strictly positive prices

        Returns
        -------

        pandas.DataFrame
            Defensive numeric copy of the input.
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
                "Price index must be monotonically "
                "increasing."
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

        return numeric.copy()

    # ========================================================
    # ASSET INDEX VALIDATION
    # ========================================================

    @staticmethod
    def _validate_asset_index(
        asset_index: pd.Index,
    ) -> pd.Index:
        """
        Validate the canonical production asset index.
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
                "Forecast asset index cannot be empty."
            )

        if asset_index.has_duplicates:
            duplicated = (
                asset_index[
                    asset_index.duplicated()
                ]
                .tolist()
            )

            raise ValueError(
                "Forecast asset index contains "
                f"duplicate assets: {duplicated}."
            )

        return asset_index

    # ========================================================
    # COMPONENT VALIDATION
    # ========================================================

    @classmethod
    def _validate_component(
        cls,
        component: Any,
        asset_index: pd.Index,
        component_name: str,
    ) -> pd.Series:
        """
        Validate and normalize an individual forecast component.

        The returned Series is guaranteed to have:

            * exactly one value per asset
            * exactly the canonical asset index
            * exactly the canonical asset order
            * no missing values
            * only finite floating-point values

        This method deliberately avoids relying on implicit pandas
        alignment during the final forecast combination.
        """

        asset_index = cls._validate_asset_index(
            asset_index
        )

        # ----------------------------------------------------
        # Convert component into Series
        # ----------------------------------------------------

        if isinstance(
            component,
            pd.Series,
        ):
            result = component.copy()

        else:
            try:
                values = np.asarray(
                    component,
                    dtype=float,
                ).reshape(-1)

            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{component_name} forecast could not "
                    "be converted to numeric values."
                ) from exc

            if values.size != len(asset_index):
                raise ValueError(
                    f"{component_name} forecast returned "
                    f"{values.size} values; expected "
                    f"{len(asset_index)}."
                )

            result = pd.Series(
                values,
                index=asset_index,
                dtype=float,
            )

        # ----------------------------------------------------
        # Dimension validation
        # ----------------------------------------------------

        if result.size != len(asset_index):
            raise ValueError(
                f"{component_name} forecast returned "
                f"{result.size} values; expected "
                f"{len(asset_index)}."
            )

        # ----------------------------------------------------
        # Index validation
        # ----------------------------------------------------

        if result.index.has_duplicates:
            duplicated = (
                result.index[
                    result.index.duplicated()
                ]
                .tolist()
            )

            raise ValueError(
                f"{component_name} forecast contains "
                f"duplicate asset labels: {duplicated}."
            )

        # ----------------------------------------------------
        # Explicit canonical reordering
        # ----------------------------------------------------

        if not result.index.equals(
            asset_index
        ):
            try:
                result = result.reindex(
                    asset_index
                )

            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    f"{component_name} forecast could not "
                    "be aligned to the canonical asset index."
                ) from exc

        # ----------------------------------------------------
        # Missing-value validation
        # ----------------------------------------------------

        if result.isna().any():
            missing_assets = (
                result.index[
                    result.isna()
                ]
                .tolist()
            )

            raise ValueError(
                f"{component_name} forecast contains "
                f"missing values for assets: {missing_assets}."
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
                f"{component_name} forecast contains "
                "non-numeric values."
            ) from exc

        # ----------------------------------------------------
        # Finite-value validation
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
                f"{component_name} forecast contains "
                "non-finite values for assets: "
                f"{invalid_assets}."
            )

        # ----------------------------------------------------
        # Final index invariant
        # ----------------------------------------------------

        if not result.index.equals(
            asset_index
        ):
            raise ValueError(
                f"{component_name} forecast asset "
                "ordering does not match input prices."
            )

        return pd.Series(
            values,
            index=asset_index,
            dtype=float,
        )

    # ========================================================
    # WEIGHT VALIDATION
    # ========================================================

    @classmethod
    def _validate_weights(cls) -> None:
        """
        Validate the configured component weights.
        """

        weights = np.asarray(
            [
                cls.MOMENTUM_WEIGHT,
                cls.TREND_WEIGHT,
                cls.MEAN_REVERSION_WEIGHT,
            ],
            dtype=float,
        )

        if not np.isfinite(
            weights
        ).all():
            raise ValueError(
                "Expected-return forecast weights "
                "must be finite."
            )

        if (
            weights < 0.0
        ).any():
            raise ValueError(
                "Expected-return forecast weights "
                "cannot be negative."
            )

        total = float(
            weights.sum()
        )

        if not np.isclose(
            total,
            1.0,
            atol=1e-12,
        ):
            raise ValueError(
                "Expected-return forecast weights "
                f"must sum to one; got {total}."
            )

    # ========================================================
    # FORECAST
    # ========================================================

    def forecast(
        self,
        prices: pd.DataFrame,
    ) -> pd.Series:
        """
        Generate the production combined expected-return forecast.

        Parameters
        ----------
        prices:
            Historical price DataFrame.

        Returns
        -------
        pandas.Series
            Expected-return forecast indexed exactly by the
            input asset columns.

        Raises
        ------
        TypeError
            Invalid input type.

        ValueError
            Invalid prices, insufficient history, invalid component
            output, or invalid forecast weights.
        """

        # ----------------------------------------------------
        # Validate prices
        # ----------------------------------------------------

        prices = self._validate_prices(
            prices
        )

        # ----------------------------------------------------
        # Validate history
        # ----------------------------------------------------

        self.validate_history(
            prices
        )

        # ----------------------------------------------------
        # Canonical asset index
        # ----------------------------------------------------

        asset_index = (
            self._validate_asset_index(
                prices.columns
            )
        )

        # ----------------------------------------------------
        # Validate component weights BEFORE execution
        # ----------------------------------------------------

        self._validate_weights()

        # ----------------------------------------------------
        # State
        # ----------------------------------------------------

        self.last_observations = int(
            len(prices)
        )

        # ====================================================
        # MOMENTUM
        # ====================================================

        try:
            momentum_raw = (
                self.momentum.forecast(
                    prices,
                    lookback=self.MOMENTUM_LOOKBACK,
                )
            )

        except Exception as exc:
            raise RuntimeError(
                "Momentum forecast failed."
            ) from exc

        momentum = (
            self._validate_component(
                momentum_raw,
                asset_index,
                "Momentum",
            )
        )

        # ====================================================
        # TREND
        # ====================================================

        try:
            trend_raw = (
                self.trend.forecast(
                    prices,
                    short_window=self.TREND_SHORT_WINDOW,
                    long_window=self.TREND_LOOKBACK,
                )
            )

        except Exception as exc:
            raise RuntimeError(
                "Trend forecast failed."
            ) from exc

        trend = (
            self._validate_component(
                trend_raw,
                asset_index,
                "Trend",
            )
        )

        # ====================================================
        # MEAN REVERSION
        # ====================================================

        try:
            reversion_raw = (
                self.mean_reversion.forecast(
                    prices,
                    lookback=self.MEAN_REVERSION_LOOKBACK,
                )
            )

        except Exception as exc:
            raise RuntimeError(
                "Mean-reversion forecast failed."
            ) from exc

        reversion = (
            self._validate_component(
                reversion_raw,
                asset_index,
                "Mean reversion",
            )
        )

        # ====================================================
        # STORE COMPONENTS
        # ====================================================

        self.last_components = {
            "momentum": momentum.copy(),
            "trend": trend.copy(),
            "mean_reversion": reversion.copy(),
        }

        # ====================================================
        # EXPLICIT NUMPY COMBINATION
        # ====================================================

        # IMPORTANT:
        #
        # Do not rely on pandas Series arithmetic here.
        #
        # All three components have already been validated and
        # explicitly reordered to asset_index. We therefore
        # combine their underlying arrays positionally.
        #
        # This eliminates accidental pandas index alignment from
        # the production combination boundary.

        momentum_values = (
            momentum.to_numpy(
                dtype=float
            )
        )

        trend_values = (
            trend.to_numpy(
                dtype=float
            )
        )

        reversion_values = (
            reversion.to_numpy(
                dtype=float
            )
        )

        expected_return_values = (
            self.MOMENTUM_WEIGHT
            * momentum_values
            +
            self.TREND_WEIGHT
            * trend_values
            +
            self.MEAN_REVERSION_WEIGHT
            * reversion_values
        )

        # ====================================================
        # FINAL NUMERIC VALIDATION
        # ====================================================

        if not np.isfinite(
            expected_return_values
        ).all():
            raise ValueError(
                "Combined expected-return forecast "
                "contains non-finite values."
            )

        # ====================================================
        # FINAL SERIES
        # ====================================================

        expected_returns = pd.Series(
            expected_return_values,
            index=asset_index,
            dtype=float,
            name="expected_return",
        )

        # ----------------------------------------------------
        # Final missing-value check
        # ----------------------------------------------------

        if expected_returns.isna().any():
            missing_assets = (
                expected_returns.index[
                    expected_returns.isna()
                ]
                .tolist()
            )

            raise ValueError(
                "Combined expected-return forecast "
                f"contains missing values for assets: "
                f"{missing_assets}."
            )

        # ----------------------------------------------------
        # Final index invariant
        # ----------------------------------------------------

        if not expected_returns.index.equals(
            asset_index
        ):
            raise ValueError(
                "Combined forecast asset ordering "
                "does not match input prices."
            )

        # ====================================================
        # STATE
        # ====================================================

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
            "asset_order": [
                str(asset)
                for asset in asset_index
            ],
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
            "component_ranges": {
                "momentum": {
                    "minimum": float(
                        momentum_values.min()
                    ),
                    "maximum": float(
                        momentum_values.max()
                    ),
                },
                "trend": {
                    "minimum": float(
                        trend_values.min()
                    ),
                    "maximum": float(
                        trend_values.max()
                    ),
                },
                "mean_reversion": {
                    "minimum": float(
                        reversion_values.min()
                    ),
                    "maximum": float(
                        reversion_values.max()
                    ),
                },
                "combined": {
                    "minimum": float(
                        expected_return_values.min()
                    ),
                    "maximum": float(
                        expected_return_values.max()
                    ),
                },
            },
        }

        return expected_returns

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return deterministic component health information.

        Health checks do not execute a forecast.
        """

        try:
            weights = np.asarray(
                [
                    self.MOMENTUM_WEIGHT,
                    self.TREND_WEIGHT,
                    self.MEAN_REVERSION_WEIGHT,
                ],
                dtype=float,
            )

            weights_finite = bool(
                np.isfinite(
                    weights
                ).all()
            )

            weights_non_negative = bool(
                (
                    weights >= 0.0
                ).all()
            )

            weights_sum = float(
                weights.sum()
            )

            weights_valid = bool(
                np.isclose(
                    weights_sum,
                    1.0,
                    atol=1e-12,
                )
            )

            history_valid = bool(
                self.MINIMUM_HISTORY > 0
            )

            components_available = all(
                component is not None
                for component in (
                    self.momentum,
                    self.trend,
                    self.mean_reversion,
                )
            )

            healthy = bool(
                weights_finite
                and weights_non_negative
                and weights_valid
                and history_valid
                and components_available
            )

            return {
                "status": (
                    "HEALTHY"
                    if healthy
                    else "UNHEALTHY"
                ),
                "healthy": healthy,
                "api_version": self.API_VERSION,
                "component": self.COMPONENT,
                "minimum_history": int(
                    self.MINIMUM_HISTORY
                ),
                "weights_sum": weights_sum,
                "weights_valid": weights_valid,
                "components_available": (
                    components_available
                ),
            }

        except Exception as exc:
            return {
                "status": "UNHEALTHY",
                "healthy": False,
                "api_version": self.API_VERSION,
                "component": self.COMPONENT,
                "error": str(exc),
            }

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self,
    ) -> dict[str, Any]:
        """
        Return the current forecaster state summary.
        """

        return {
            "api_version": self.API_VERSION,
            "component": self.COMPONENT,
            "minimum_history": int(
                self.MINIMUM_HISTORY
            ),
            "last_observations": (
                None
                if self.last_observations is None
                else int(self.last_observations)
            ),
            "last_forecast_available": (
                self.last_forecast is not None
            ),
            "last_components_available": (
                self.last_components is not None
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