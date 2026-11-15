"""
======================================================================
EXPECTED RETURN CALIBRATOR

A15.2 — Hardened Expected-Return Calibration Layer

Institutional expected-return calibration boundary.

Transforms validated forecast signals into bounded, finite,
asset-aligned expected-return estimates suitable for downstream
portfolio construction and Black-Litterman integration.

Calibration model
-----------------

    μ_i = clip(k * s_i * σ_i, lower, upper)

where

    μ_i : calibrated expected return
    s_i : forecast signal
    σ_i : annualized asset volatility
    k   : calibration strength

Design principles
-----------------

1. Explicit input contracts.
2. Exact asset-index preservation.
3. No implicit pandas alignment at the final numerical boundary.
4. No NaN or infinite outputs.
5. Explicit volatility annualization.
6. Explicit calibration strength.
7. Explicit expected-return bounds.
8. Deterministic clipping.
9. Clipping is observable through diagnostics.
10. No mutation of caller-owned inputs.
11. No silent handling of malformed inputs.
12. Production health-check boundary.
13. Frozen public API.
======================================================================
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


# ======================================================================
# EXPECTED RETURN CALIBRATOR
# ======================================================================


class ExpectedReturnCalibrator:
    """
    Production expected-return calibration engine.

    The calibrator converts dimensionless forecast signals into
    bounded expected returns using asset volatility.

    Default calibration:

        expected_return
            =
            calibration_strength
            × signal
            × annualized_volatility

    followed by explicit lower/upper clipping.

    Parameters
    ----------
    calibration_strength:
        Strength applied to the forecast signal.

    periods_per_year:
        Number of observations used to annualize volatility.

    lower_bound:
        Minimum permitted expected return.

    upper_bound:
        Maximum permitted expected return.

    Notes
    -----
    The calibrator deliberately does not generate forecasts itself.
    It is a numerical boundary between the forecasting layer and
    downstream portfolio construction.
    """

    # ==================================================================
    # API METADATA
    # ==================================================================

    API_VERSION = "1.0.0"

    COMPONENT = "ExpectedReturnCalibrator"

    PUBLIC_METHODS = (
        "calibrate",
        "validate",
        "summary",
        "health_check",
    )

    # ==================================================================
    # DEFAULT CONFIGURATION
    # ==================================================================

    DEFAULT_CALIBRATION_STRENGTH = 1.0

    DEFAULT_PERIODS_PER_YEAR = 252

    DEFAULT_LOWER_BOUND = -0.50

    DEFAULT_UPPER_BOUND = 0.50

    # ==================================================================
    # CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        calibration_strength: float = DEFAULT_CALIBRATION_STRENGTH,
        periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
        lower_bound: float = DEFAULT_LOWER_BOUND,
        upper_bound: float = DEFAULT_UPPER_BOUND,
    ) -> None:
        """
        Initialize the expected-return calibration engine.
        """

        self.calibration_strength = float(
            calibration_strength
        )

        self.periods_per_year = int(
            periods_per_year
        )

        self.lower_bound = float(
            lower_bound
        )

        self.upper_bound = float(
            upper_bound
        )

        # --------------------------------------------------------------
        # Last successful calibration
        # --------------------------------------------------------------

        self.last_forecast: pd.Series | None = None

        # --------------------------------------------------------------
        # Last volatility
        # --------------------------------------------------------------

        self.last_volatility: pd.Series | None = None

        # --------------------------------------------------------------
        # Last signal
        # --------------------------------------------------------------

        self.last_signal: pd.Series | None = None

        # --------------------------------------------------------------
        # Last diagnostics
        # --------------------------------------------------------------

        self.last_diagnostics: dict[str, Any] | None = None

        # --------------------------------------------------------------
        # Validate configuration immediately.
        # --------------------------------------------------------------

        self._validate_configuration()

    # ==================================================================
    # CONFIGURATION VALIDATION
    # ==================================================================

    def _validate_configuration(self) -> None:
        """
        Validate calibration configuration.
        """

        if not np.isfinite(
            self.calibration_strength
        ):
            raise ValueError(
                "calibration_strength must be finite."
            )

        if self.calibration_strength < 0.0:
            raise ValueError(
                "calibration_strength cannot be negative."
            )

        if self.periods_per_year <= 0:
            raise ValueError(
                "periods_per_year must be positive."
            )

        if not np.isfinite(
            self.lower_bound
        ):
            raise ValueError(
                "lower_bound must be finite."
            )

        if not np.isfinite(
            self.upper_bound
        ):
            raise ValueError(
                "upper_bound must be finite."
            )

        if self.lower_bound >= self.upper_bound:
            raise ValueError(
                "lower_bound must be strictly less "
                "than upper_bound."
            )

    # ==================================================================
    # INDEX VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_asset_index(
        asset_index: pd.Index,
    ) -> pd.Index:
        """
        Validate the canonical asset index.
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
            duplicated = (
                asset_index[
                    asset_index.duplicated()
                ]
                .tolist()
            )

            raise ValueError(
                "Asset index contains duplicate "
                f"assets: {duplicated}."
            )

        return asset_index

    # ==================================================================
    # SERIES VALIDATION
    # ==================================================================

    @classmethod
    def _validate_series(
        cls,
        values: Any,
        asset_index: pd.Index,
        name: str,
    ) -> pd.Series:
        """
        Validate a signal or volatility vector.

        The returned Series has exactly the canonical asset index
        and ordering.
        """

        asset_index = cls._validate_asset_index(
            asset_index
        )

        # --------------------------------------------------------------
        # Convert input to Series
        # --------------------------------------------------------------

        if isinstance(
            values,
            pd.Series,
        ):
            result = values.copy()

        else:
            try:
                array = np.asarray(
                    values,
                    dtype=float,
                ).reshape(-1)

            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    f"{name} could not be converted "
                    "to numeric values."
                ) from exc

            if array.size != len(
                asset_index
            ):
                raise ValueError(
                    f"{name} contains {array.size} "
                    f"values; expected {len(asset_index)}."
                )

            result = pd.Series(
                array,
                index=asset_index,
                dtype=float,
            )

        # --------------------------------------------------------------
        # Dimension validation
        # --------------------------------------------------------------

        if result.size != len(
            asset_index
        ):
            raise ValueError(
                f"{name} contains {result.size} "
                f"values; expected {len(asset_index)}."
            )

        # --------------------------------------------------------------
        # Duplicate index validation
        # --------------------------------------------------------------

        if result.index.has_duplicates:
            duplicated = (
                result.index[
                    result.index.duplicated()
                ]
                .tolist()
            )

            raise ValueError(
                f"{name} contains duplicate "
                f"asset labels: {duplicated}."
            )

        # --------------------------------------------------------------
        # Explicit alignment
        # --------------------------------------------------------------

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
                    f"{name} could not be aligned "
                    "to the asset index."
                ) from exc

        # --------------------------------------------------------------
        # Missing-value validation
        # --------------------------------------------------------------

        if result.isna().any():
            missing_assets = (
                result.index[
                    result.isna()
                ]
                .tolist()
            )

            raise ValueError(
                f"{name} contains missing values "
                f"for assets: {missing_assets}."
            )

        # --------------------------------------------------------------
        # Numeric conversion
        # --------------------------------------------------------------

        try:
            result = result.astype(
                float
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                f"{name} contains non-numeric values."
            ) from exc

        # --------------------------------------------------------------
        # Finite-value validation
        # --------------------------------------------------------------

        numeric_values = result.to_numpy(
            dtype=float
        )

        if not np.isfinite(
            numeric_values
        ).all():
            invalid_assets = (
                result.index[
                    ~np.isfinite(
                        numeric_values
                    )
                ]
                .tolist()
            )

            raise ValueError(
                f"{name} contains non-finite values "
                f"for assets: {invalid_assets}."
            )

        # --------------------------------------------------------------
        # Final invariant
        # --------------------------------------------------------------

        if not result.index.equals(
            asset_index
        ):
            raise ValueError(
                f"{name} asset ordering does not "
                "match the canonical asset index."
            )

        return pd.Series(
            numeric_values,
            index=asset_index,
            dtype=float,
            name=name,
        )

    # ==================================================================
    # PUBLIC VALIDATION
    # ==================================================================

    def validate(
        self,
        signals: pd.Series | np.ndarray | list,
        volatility: pd.Series | np.ndarray | list,
        asset_index: pd.Index | None = None,
    ) -> dict[str, Any]:
        """
        Validate calibration inputs without performing calibration.

        Parameters
        ----------
        signals:
            Forecast signal vector.

        volatility:
            Annualized volatility vector.

        asset_index:
            Optional canonical asset index.

        Returns
        -------
        dict
            Validation diagnostics.
        """

        if asset_index is None:

            if isinstance(
                signals,
                pd.Series,
            ):
                asset_index = signals.index

            else:
                try:
                    signal_array = np.asarray(
                        signals
                    ).reshape(-1)

                except Exception as exc:
                    raise ValueError(
                        "Signals could not be interpreted."
                    ) from exc

                asset_index = pd.RangeIndex(
                    len(signal_array)
                )

        asset_index = self._validate_asset_index(
            asset_index
        )

        signal_series = self._validate_series(
            signals,
            asset_index,
            "signal",
        )

        volatility_series = self._validate_series(
            volatility,
            asset_index,
            "volatility",
        )

        volatility_values = (
            volatility_series.to_numpy(
                dtype=float
            )
        )

        if (
            volatility_values < 0.0
        ).any():
            invalid_assets = (
                volatility_series.index[
                    volatility_values < 0.0
                ]
                .tolist()
            )

            raise ValueError(
                "Volatility cannot be negative. "
                f"Invalid assets: {invalid_assets}."
            )

        return {
            "valid": True,
            "asset_count": int(
                len(asset_index)
            ),
            "asset_order": [
                str(asset)
                for asset in asset_index
            ],
            "signal_minimum": float(
                signal_series.min()
            ),
            "signal_maximum": float(
                signal_series.max()
            ),
            "volatility_minimum": float(
                volatility_series.min()
            ),
            "volatility_maximum": float(
                volatility_series.max()
            ),
        }

    # ==================================================================
    # VOLATILITY FROM RETURNS
    # ==================================================================

    @classmethod
    def annualized_volatility(
        cls,
        returns: pd.DataFrame,
        periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    ) -> pd.Series:
        """
        Calculate annualized volatility from a return matrix.

        Standard deviation is estimated per asset and multiplied by
        sqrt(periods_per_year).

        Missing observations are not fabricated. Pandas' standard
        deviation operates on available observations, but the final
        result must be finite.
        """

        if not isinstance(
            returns,
            pd.DataFrame,
        ):
            raise TypeError(
                "Returns must be a pandas DataFrame."
            )

        if returns.empty:
            raise ValueError(
                "Returns cannot be empty."
            )

        if returns.shape[1] == 0:
            raise ValueError(
                "Returns must contain at least one asset."
            )

        periods_per_year = int(
            periods_per_year
        )

        if periods_per_year <= 0:
            raise ValueError(
                "periods_per_year must be positive."
            )

        numeric = returns.apply(
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
                "Returns contain non-finite values."
            )

        volatility = (
            numeric.std(
                axis=0,
                ddof=1,
            )
            * np.sqrt(
                periods_per_year
            )
        )

        volatility = volatility.astype(
            float
        )

        if not np.isfinite(
            volatility.to_numpy(
                dtype=float
            )
        ).all():
            raise ValueError(
                "Annualized volatility contains "
                "non-finite values."
            )

        if (
            volatility < 0.0
        ).any():
            raise ValueError(
                "Annualized volatility cannot be negative."
            )

        volatility.name = "annualized_volatility"

        return volatility

    # ==================================================================
    # CALIBRATION
    # ==================================================================

    def calibrate(
        self,
        signals: pd.Series | np.ndarray | list,
        volatility: pd.Series | np.ndarray | list,
        asset_index: pd.Index | None = None,
    ) -> pd.Series:
        """
        Convert forecast signals into bounded expected returns.

        Formula
        -------

            raw_return_i
                =
                calibration_strength
                × signal_i
                × volatility_i

            expected_return_i
                =
                clip(
                    raw_return_i,
                    lower_bound,
                    upper_bound,
                )

        Parameters
        ----------
        signals:
            Forecast signal vector.

        volatility:
            Annualized volatility vector.

        asset_index:
            Canonical asset order.

        Returns
        -------
        pandas.Series
            Bounded expected-return vector.
        """

        # --------------------------------------------------------------
        # Determine canonical asset index
        # --------------------------------------------------------------

        if asset_index is None:

            if isinstance(
                signals,
                pd.Series,
            ):
                asset_index = signals.index

            else:

                signal_array = np.asarray(
                    signals,
                    dtype=float,
                ).reshape(-1)

                asset_index = pd.RangeIndex(
                    len(signal_array)
                )

        asset_index = self._validate_asset_index(
            asset_index
        )

        # --------------------------------------------------------------
        # Validate inputs
        # --------------------------------------------------------------

        validation = self.validate(
            signals=signals,
            volatility=volatility,
            asset_index=asset_index,
        )

        signal_series = self._validate_series(
            signals,
            asset_index,
            "signal",
        )

        volatility_series = self._validate_series(
            volatility,
            asset_index,
            "volatility",
        )

        volatility_values = (
            volatility_series.to_numpy(
                dtype=float
            )
        )

        if (
            volatility_values < 0.0
        ).any():
            invalid_assets = (
                volatility_series.index[
                    volatility_values < 0.0
                ]
                .tolist()
            )

            raise ValueError(
                "Volatility cannot be negative. "
                f"Invalid assets: {invalid_assets}."
            )

        # --------------------------------------------------------------
        # Positional numerical boundary
        # --------------------------------------------------------------

        signal_values = (
            signal_series.to_numpy(
                dtype=float
            )
        )

        raw_expected_returns = (
            self.calibration_strength
            * signal_values
            * volatility_values
        )

        if not np.isfinite(
            raw_expected_returns
        ).all():
            raise ValueError(
                "Raw calibrated expected returns "
                "contain non-finite values."
            )

        # --------------------------------------------------------------
        # Explicit clipping
        # --------------------------------------------------------------

        expected_return_values = np.clip(
            raw_expected_returns,
            self.lower_bound,
            self.upper_bound,
        )

        if not np.isfinite(
            expected_return_values
        ).all():
            raise ValueError(
                "Calibrated expected returns contain "
                "non-finite values."
            )

        # --------------------------------------------------------------
        # Clipping diagnostics
        # --------------------------------------------------------------

        clipped_mask = (
            ~np.isclose(
                expected_return_values,
                raw_expected_returns,
                rtol=0.0,
                atol=1e-15,
            )
        )

        clipped_assets = (
            asset_index[
                clipped_mask
            ]
            .tolist()
        )

        # --------------------------------------------------------------
        # Final output
        # --------------------------------------------------------------

        expected_returns = pd.Series(
            expected_return_values,
            index=asset_index,
            dtype=float,
            name="expected_return",
        )

        if expected_returns.isna().any():
            raise ValueError(
                "Calibrated expected returns contain "
                "missing values."
            )

        if not expected_returns.index.equals(
            asset_index
        ):
            raise ValueError(
                "Calibrated expected-return asset "
                "ordering does not match input."
            )

        # --------------------------------------------------------------
        # State
        # --------------------------------------------------------------

        self.last_signal = (
            signal_series.copy()
        )

        self.last_volatility = (
            volatility_series.copy()
        )

        self.last_forecast = (
            expected_returns.copy()
        )

        self.last_diagnostics = {
            "api_version": self.API_VERSION,
            "component": self.COMPONENT,
            "asset_count": int(
                len(asset_index)
            ),
            "asset_order": [
                str(asset)
                for asset in asset_index
            ],
            "calibration_strength": float(
                self.calibration_strength
            ),
            "periods_per_year": int(
                self.periods_per_year
            ),
            "lower_bound": float(
                self.lower_bound
            ),
            "upper_bound": float(
                self.upper_bound
            ),
            "clipped_count": int(
                clipped_mask.sum()
            ),
            "clipped_assets": [
                str(asset)
                for asset in clipped_assets
            ],
            "raw_minimum": float(
                raw_expected_returns.min()
            ),
            "raw_maximum": float(
                raw_expected_returns.max()
            ),
            "calibrated_minimum": float(
                expected_return_values.min()
            ),
            "calibrated_maximum": float(
                expected_return_values.max()
            ),
            "validation": validation,
        }

        return expected_returns

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return deterministic component health information.

        The health check does not perform calibration.
        """

        try:

            self._validate_configuration()

            return {
                "status": "HEALTHY",
                "healthy": True,
                "api_version": self.API_VERSION,
                "component": self.COMPONENT,
                "calibration_strength": float(
                    self.calibration_strength
                ),
                "periods_per_year": int(
                    self.periods_per_year
                ),
                "lower_bound": float(
                    self.lower_bound
                ),
                "upper_bound": float(
                    self.upper_bound
                ),
                "last_forecast_available": (
                    self.last_forecast is not None
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

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict[str, Any]:
        """
        Return the current calibrator state.
        """

        return {
            "api_version": self.API_VERSION,
            "component": self.COMPONENT,
            "calibration_strength": float(
                self.calibration_strength
            ),
            "periods_per_year": int(
                self.periods_per_year
            ),
            "lower_bound": float(
                self.lower_bound
            ),
            "upper_bound": float(
                self.upper_bound
            ),
            "last_forecast_available": (
                self.last_forecast is not None
            ),
            "last_volatility_available": (
                self.last_volatility is not None
            ),
            "last_signal_available": (
                self.last_signal is not None
            ),
            "last_diagnostics_available": (
                self.last_diagnostics is not None
            ),
        }


# ======================================================================
# REGRESSION TESTS
# ======================================================================


def test_expected_return_calibrator() -> None:
    """
    Comprehensive A15.2 regression suite.
    """

    assets = pd.Index(
        [
            "SPY",
            "QQQ",
            "TLT",
            "GLD",
        ]
    )

    signals = pd.Series(
        [
            0.50,
            -0.25,
            0.10,
            2.00,
        ],
        index=assets,
    )

    volatility = pd.Series(
        [
            0.20,
            0.30,
            0.10,
            0.40,
        ],
        index=assets,
    )

    # ==============================================================
    # CONSTRUCTION
    # ==============================================================

    calibrator = (
        ExpectedReturnCalibrator()
    )

    assert (
        calibrator.API_VERSION
        ==
        "1.0.0"
    )

    assert (
        calibrator.COMPONENT
        ==
        "ExpectedReturnCalibrator"
    )

    assert tuple(
        calibrator.PUBLIC_METHODS
    ) == (
        "calibrate",
        "validate",
        "summary",
        "health_check",
    )

    # ==============================================================
    # HEALTH
    # ==============================================================

    health = (
        calibrator.health_check()
    )

    assert health["healthy"] is True

    assert health["status"] == "HEALTHY"

    # ==============================================================
    # VALIDATION
    # ==============================================================

    validation = calibrator.validate(
        signals,
        volatility,
        assets,
    )

    assert validation["valid"] is True

    assert validation["asset_count"] == 4

    # ==============================================================
    # CALIBRATION
    # ==============================================================

    expected = calibrator.calibrate(
        signals,
        volatility,
        assets,
    )

    manual = (
        signals.to_numpy()
        *
        volatility.to_numpy()
    )

    manual = np.clip(
        manual,
        calibrator.lower_bound,
        calibrator.upper_bound,
    )

    assert isinstance(
        expected,
        pd.Series,
    )

    assert expected.index.equals(
        assets
    )

    assert np.allclose(
        expected.to_numpy(),
        manual,
    )

    assert np.isfinite(
        expected.to_numpy()
    ).all()

    # ==============================================================
    # BOUNDS
    # ==============================================================

    assert (
        expected >= calibrator.lower_bound
    ).all()

    assert (
        expected <= calibrator.upper_bound
    ).all()

    # ==============================================================
    # CLIPPING
    # ==============================================================

    extreme_signals = pd.Series(
        [
            10.0,
            -10.0,
            0.0,
            1.0,
        ],
        index=assets,
    )

    extreme_expected = (
        calibrator.calibrate(
            extreme_signals,
            volatility,
            assets,
        )
    )

    assert (
        extreme_expected.loc["SPY"]
        ==
        calibrator.upper_bound
    )

    assert (
        extreme_expected.loc["QQQ"]
        ==
        calibrator.lower_bound
    )

    assert (
        extreme_expected.loc["TLT"]
        ==
        0.0
    )

    assert (
        calibrator.last_diagnostics[
            "clipped_count"
        ]
        == 2
    )

    # ==============================================================
    # INDEX ORDERING
    # ==============================================================

    reordered_assets = pd.Index(
        [
            "GLD",
            "SPY",
            "TLT",
            "QQQ",
        ]
    )

    reordered_signals = signals.reindex(
        reordered_assets
    )

    reordered_volatility = (
        volatility.reindex(
            reordered_assets
        )
    )

    reordered_expected = (
        calibrator.calibrate(
            reordered_signals,
            reordered_volatility,
            reordered_assets,
        )
    )

    assert reordered_expected.index.equals(
        reordered_assets
    )

    assert np.allclose(
        reordered_expected.loc[
            assets
        ].to_numpy(),
        expected.loc[
            assets
        ].to_numpy(),
        atol=1e-12,
    )

    # ==============================================================
    # ARRAY INPUT
    # ==============================================================

    array_expected = (
        calibrator.calibrate(
            signals.to_numpy(),
            volatility.to_numpy(),
            assets,
        )
    )

    assert array_expected.index.equals(
        assets
    )

    assert np.allclose(
        array_expected.to_numpy(),
        expected.to_numpy(),
    )

    # ==============================================================
    # INVALID SIGNAL
    # ==============================================================

    invalid_signals = signals.copy()

    invalid_signals.iloc[0] = np.nan

    try:

        calibrator.calibrate(
            invalid_signals,
            volatility,
            assets,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # INFINITE SIGNAL
    # ==============================================================

    invalid_signals = signals.copy()

    invalid_signals.iloc[0] = np.inf

    try:

        calibrator.calibrate(
            invalid_signals,
            volatility,
            assets,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # NEGATIVE VOLATILITY
    # ==============================================================

    invalid_volatility = volatility.copy()

    invalid_volatility.iloc[0] = -0.10

    try:

        calibrator.calibrate(
            signals,
            invalid_volatility,
            assets,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # DUPLICATE ASSET INDEX
    # ==============================================================

    duplicate_assets = pd.Index(
        [
            "SPY",
            "QQQ",
            "TLT",
            "SPY",
        ]
    )

    try:

        calibrator.calibrate(
            signals.to_numpy(),
            volatility.to_numpy(),
            duplicate_assets,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # DIMENSION MISMATCH
    # ==============================================================

    try:

        calibrator.calibrate(
            signals.iloc[:-1],
            volatility,
            assets,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # INVALID CONFIGURATION
    # ==============================================================

    try:

        ExpectedReturnCalibrator(
            lower_bound=0.50,
            upper_bound=0.50,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    try:

        ExpectedReturnCalibrator(
            calibration_strength=-1.0,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    try:

        ExpectedReturnCalibrator(
            periods_per_year=0,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:

        pass

    # ==============================================================
    # ANNUALIZED VOLATILITY
    # ==============================================================

    np.random.seed(42)

    returns = pd.DataFrame(
        np.random.normal(
            0.0,
            0.01,
            size=(500, 4),
        ),
        columns=assets,
    )

    annualized = (
        calibrator.annualized_volatility(
            returns
        )
    )

    assert isinstance(
        annualized,
        pd.Series,
    )

    assert annualized.index.equals(
        assets
    )

    assert len(
        annualized
    ) == 4

    assert np.isfinite(
        annualized.to_numpy()
    ).all()

    assert (
        annualized >= 0.0
    ).all()

    # ==============================================================
    # SERIALIZATION / STATE
    # ==============================================================

    assert (
        calibrator.last_forecast
        is not None
    )

    assert (
        calibrator.last_signal
        is not None
    )

    assert (
        calibrator.last_volatility
        is not None
    )

    assert (
        calibrator.last_diagnostics
        is not None
    )

    # ==============================================================
    # SUMMARY
    # ==============================================================

    summary = (
        calibrator.summary()
    )

    assert (
        summary["api_version"]
        ==
        "1.0.0"
    )

    assert (
        summary["component"]
        ==
        "ExpectedReturnCalibrator"
    )

    assert (
        summary["last_forecast_available"]
        is True
    )

    assert (
        summary["last_signal_available"]
        is True
    )

    assert (
        summary["last_volatility_available"]
        is True
    )

    # ==============================================================
    # INPUT IMMUTABILITY
    # ==============================================================

    original_signals = signals.copy()

    original_volatility = (
        volatility.copy()
    )

    calibrator.calibrate(
        signals,
        volatility,
        assets,
    )

    assert signals.equals(
        original_signals
    )

    assert volatility.equals(
        original_volatility
    )

    print(
        "ExpectedReturnCalibrator tests passed."
    )


# ======================================================================
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    test_expected_return_calibrator()