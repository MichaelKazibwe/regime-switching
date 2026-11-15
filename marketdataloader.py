"""
======================================================================
MARKET DATA LOADER
======================================================================

Production-grade historical market-data loading boundary.

Purpose
-------
This module provides the controlled market-data ingestion boundary for
the regime-switching portfolio system.

The loader is responsible for:

    1. Downloading historical market prices from Yahoo Finance.
    2. Attempting a batched download before individual recovery.
    3. Normalizing Yahoo Finance output.
    4. Preserving the requested production asset universe.
    5. Recovering genuinely missing assets individually.
    6. Never interpolating historical observations.
    7. Never forward-filling historical observations.
    8. Never backward-filling historical observations.
    9. Never fabricating historical observations.
   10. Preserving partial missing observations exactly as received.
   11. Validating final price and return matrices.
   12. Exposing deterministic loader health state.

Critical Data-Recovery Contract
--------------------------------
The distinction between a missing asset and a partially missing
historical series is intentional.

A missing asset means:

    * the asset column does not exist, or
    * the asset column exists but contains no valid observations.

Such an asset may be downloaded individually.

A partially missing asset means:

    * the asset column exists, and
    * at least one valid historical observation exists, and
    * at least one historical observation is NaN.

Such an asset MUST NOT be downloaded again merely to fill the gaps.

The loader therefore does NOT:

    * interpolate,
    * forward-fill,
    * backward-fill,
    * synthesize,
    * estimate,
    * overwrite valid observations,
    * or fill partial historical gaps from a second download.

This preserves the integrity of the observed historical dataset.

Author
------
Portfolio System Engineering

Version
-------
3.0.0

Phase
-----
Production Hardening
======================================================================
"""


from __future__ import annotations


# ======================================================================
# SECTION 1
# IMPORTS
# ======================================================================


import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable
from tradingcalendar import TradingCalendar


import pandas as pd
import yfinance as yf


from core_constants import DEFAULT_ASSETS, settings
from exceptions import DataValidationError
from validators import DataValidator


# ======================================================================
# SECTION 2
# MODULE LOGGER
# ======================================================================


logger = logging.getLogger(__name__)


# ======================================================================
# SECTION 3
# MARKET DATA LOADER
# ======================================================================


class MarketDataLoader:
    """
    Production-grade historical market-data loader.

    The loader provides a controlled boundary between external market
    data and the portfolio/risk system.

    Core guarantees
    ---------------

    1. Batched Yahoo Finance download is attempted first.

    2. Yahoo Finance MultiIndex output is normalized.

    3. Missing asset columns are detected explicitly.

    4. Completely empty asset columns may be recovered individually.

    5. Partially missing asset columns are preserved exactly.

    6. Historical prices are never interpolated.

    7. Historical prices are never forward-filled.

    8. Historical prices are never backward-filled.

    9. Historical prices are never fabricated.

   10. Requested asset ordering is preserved.

   11. Final price data can be passed through DataValidator.

   12. Loader health state remains deterministic.

    Recovery policy
    ---------------

    An asset is eligible for individual recovery only when:

        * the asset column is absent, or
        * the asset column contains no valid observations.

    An asset with some valid observations and some NaNs is NOT
    considered a missing asset and therefore is NOT recovered.
    """

    API_VERSION = "2.0.0"

    COMPONENT = "MarketDataLoader"

    PUBLIC_METHODS = (
        "load_prices",
        "load_returns",
        "health_check",
    )

    # ==================================================================
    # SECTION 3.1
    # CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        assets: Iterable[str] | None = None,
        period: str | None = None,
        *,
        auto_adjust: bool = True,
        max_retries: int = 2,
        max_data_age: timedelta | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """
        Initialize the market-data loader.

        Parameters
        ----------
        assets:
            Requested asset universe.

        period:
            Yahoo Finance historical period. If omitted, the configured
            settings.yahoo_period value is used.

        auto_adjust:
            Whether Yahoo Finance adjusted prices should be requested.

        max_retries:
            Number of retries after the initial download attempt.

        max_data_age:
            Optional maximum permitted age of the latest valid
            observation for each asset. If omitted, stale-data
            protection is disabled.

        clock:
            Optional timezone-aware clock used for deterministic
            freshness evaluation and testing.
        """

        requested_assets = (
            list(assets)
            if assets is not None
            else list(DEFAULT_ASSETS)
        )

        self.assets = self._normalize_assets(
            requested_assets
        )

        if not self.assets:
            raise ValueError(
                "MarketDataLoader requires at least one asset."
            )

        self.period = (
            period
            if period is not None
            else settings.yahoo_period
        )

        self.auto_adjust = bool(
            auto_adjust
        )

        self.max_retries = max(
            0,
            int(max_retries),
        )

        if max_data_age is not None:
            if not isinstance(max_data_age, timedelta):
                raise TypeError(
                    "max_data_age must be a datetime.timedelta or None"
                )

            if max_data_age <= timedelta(0):
                raise ValueError(
                    "max_data_age must be positive"
                )

        self.max_data_age = max_data_age

        self._clock = clock or (
            lambda: datetime.now(timezone.utc)
        )

        initial_clock = self._clock()

        if (
            initial_clock.tzinfo is None
            or initial_clock.utcoffset() is None
        ):
            raise ValueError(
                "clock must return a timezone-aware datetime"
            )

        self._calendar = TradingCalendar()

        # --------------------------------------------------------------
        # DOWNLOAD STATE
        # --------------------------------------------------------------

        self.last_downloaded_assets: tuple[str, ...] = ()

        self.last_failed_assets: tuple[str, ...] = ()

        self.last_recovered_assets: tuple[str, ...] = ()

        self.last_batch_error: str | None = None

        self.last_incomplete_assets: tuple[str, ...] = ()

        # --------------------------------------------------------------
        # STALE-DATA / FRESHNESS STATE
        # --------------------------------------------------------------

        self.last_stale_assets: tuple[str, ...] = ()

        self.last_observation_timestamps: dict[
            str,
            str | None,
        ] = {}

        self.last_freshness_age_seconds: dict[
            str,
            float | None,
        ] = {}

        self.last_freshness_status = (
            "DISABLED"
            if self.max_data_age is None
            else "NOT_EVALUATED"
        )

    # ==================================================================
    # SECTION 4
    # ASSET NORMALIZATION
    # ==================================================================

    @staticmethod
    def _normalize_assets(
        assets: Iterable[str],
    ) -> list[str]:
        """
        Normalize the requested asset universe.

        Rules
        -----
        Tickers are:

            * converted to strings;
            * stripped;
            * upper-cased;
            * deduplicated;
            * preserved in first-seen order.
        """

        normalized: list[str] = []

        for asset in assets:

            ticker = (
                str(asset)
                .strip()
                .upper()
            )

            if not ticker:
                continue

            if ticker not in normalized:

                normalized.append(
                    ticker
                )

        return normalized

    # ==================================================================
    # SECTION 5
    # YAHOO FINANCE DOWNLOAD BOUNDARY
    # ==================================================================

    def _download(
        self,
        ticker_or_tickers,
    ) -> pd.DataFrame:
        """
        Execute the Yahoo Finance download boundary.

        No transformation or recovery is performed here.
        """

        return yf.download(
            ticker_or_tickers,
            period=self.period,
            auto_adjust=self.auto_adjust,
            progress=False,
            threads=False,
        )

    # ==================================================================
    # SECTION 6
    # MULTIINDEX NORMALIZATION
    # ==================================================================

    @staticmethod
    def _extract_close(
        data: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Extract Close prices from Yahoo Finance output.

        Supported layouts
        -----------------
        Price / Ticker:

            ('Close', 'SPY')
            ('Close', 'EFA')

        Ticker / Price:

            ('SPY', 'Close')
            ('EFA', 'Close')

        Single-ticker responses containing a normal ``Close`` column are
        also supported.
        """

        if data is None:

            return pd.DataFrame()

        if data.empty:

            return pd.DataFrame()

        frame = data.copy()

        # ------------------------------------------------------------------
        # SECTION 6.1
        # SINGLE-TICKER RESPONSE
        # ------------------------------------------------------------------

        if not isinstance(
            frame.columns,
            pd.MultiIndex,
        ):

            if "Close" in frame.columns:

                close = frame[
                    ["Close"]
                ].copy()

                return close.rename(
                    columns={
                        "Close": "UNKNOWN"
                    }
                )

            return frame

        # ------------------------------------------------------------------
        # SECTION 6.2
        # MULTIINDEX LEVELS
        # ------------------------------------------------------------------

        level0 = list(
            frame.columns.get_level_values(0)
        )

        level1 = list(
            frame.columns.get_level_values(1)
        )

        # ------------------------------------------------------------------
        # SECTION 6.3
        # PRICE-FIRST LAYOUT
        # ------------------------------------------------------------------

        if "Close" in level0:

            close = frame[
                "Close"
            ].copy()

            if isinstance(
                close,
                pd.Series,
            ):

                close = close.to_frame()

            return close

        # ------------------------------------------------------------------
        # SECTION 6.4
        # TICKER-FIRST LAYOUT
        # ------------------------------------------------------------------

        if "Close" in level1:

            close_columns = [
                column
                for column in frame.columns
                if column[1] == "Close"
            ]

            if not close_columns:

                return pd.DataFrame()

            close = frame[
                close_columns
            ].copy()

            close.columns = [
                column[0]
                for column in close_columns
            ]

            return close

        return pd.DataFrame()

    # ==================================================================
    # SECTION 7
    # SINGLE-TICKER DOWNLOAD
    # ==================================================================

    def _download_single(
        self,
        ticker: str,
    ) -> pd.Series | None:
        """
        Download and extract one ticker.

        Retries are performed up to ``max_retries``.

        A successful result must contain at least one valid observation.

        Missing observations within an otherwise valid series are NOT
        fabricated or repaired here.
        """

        for attempt in range(
            self.max_retries + 1
        ):

            try:

                logger.info(
                    "Downloading %s individually "
                    "(attempt %d/%d).",
                    ticker,
                    attempt + 1,
                    self.max_retries + 1,
                )

                raw = self._download(
                    ticker
                )

                if raw is None or raw.empty:

                    logger.warning(
                        "No data returned for %s.",
                        ticker,
                    )

                    continue

                close = self._extract_close(
                    raw
                )

                if close.empty:

                    continue

                # ----------------------------------------------------------
                # IDENTIFY SINGLE-TICKER SERIES
                # ----------------------------------------------------------

                if ticker in close.columns:

                    series = close[
                        ticker
                    ].copy()

                elif "UNKNOWN" in close.columns:

                    series = close[
                        "UNKNOWN"
                    ].copy()

                elif len(
                    close.columns
                ) == 1:

                    series = close.iloc[
                        :,
                        0,
                    ].copy()

                else:

                    logger.warning(
                        "Could not identify Close "
                        "column for %s. Columns=%s",
                        ticker,
                        list(close.columns),
                    )

                    continue

                series.name = ticker

                series.index = pd.to_datetime(
                    series.index
                )

                series = series.sort_index()

                series = series[
                    ~series.index.duplicated(
                        keep="last"
                    )
                ]

                # ----------------------------------------------------------
                # NUMERIC NORMALIZATION
                # ----------------------------------------------------------

                series = pd.to_numeric(
                    series,
                    errors="coerce",
                )

                # ----------------------------------------------------------
                # NO FABRICATION
                # ----------------------------------------------------------

                if series.dropna().empty:

                    logger.warning(
                        "All observations are NaN for %s.",
                        ticker,
                    )

                    continue

                return series

            except Exception as exc:

                logger.warning(
                    "Individual download failed "
                    "for %s on attempt %d: %s",
                    ticker,
                    attempt + 1,
                    exc,
                )

        return None

    # ==================================================================
    # SECTION 8
    # BATCH DOWNLOAD
    # ==================================================================

    def _download_batch(
        self,
    ) -> pd.DataFrame:
        """
        Download the complete requested universe in one batch.

        A batch failure is recorded and converted to an empty frame so
        that individual recovery can subsequently be attempted.
        """

        self.last_batch_error = None

        try:

            logger.info(
                "Downloading prices for %s",
                self.assets,
            )

            raw = self._download(
                self.assets
            )

            if raw is None or raw.empty:

                raise DataValidationError(
                    "Yahoo Finance returned an "
                    "empty price frame."
                )

            prices = self._extract_close(
                raw
            )

            if prices.empty:

                raise DataValidationError(
                    "Yahoo Finance returned data "
                    "but no Close prices could be extracted."
                )

            prices = prices.copy()

            prices.index = pd.to_datetime(
                prices.index
            )

            prices = prices.sort_index()

            prices = prices[
                ~prices.index.duplicated(
                    keep="last"
                )
            ]

            prices.columns = [
                str(column)
                .strip()
                .upper()
                for column in prices.columns
            ]

            return prices

        except Exception as exc:

            self.last_batch_error = str(
                exc
            )

            logger.warning(
                "Batch market-data download failed: %s",
                exc,
            )

            return pd.DataFrame()

    # ==================================================================
    # SECTION 9
    # RECOVERY POLICY
    # ==================================================================

    @staticmethod
    def _asset_requires_recovery(
        frame: pd.DataFrame,
        ticker: str,
    ) -> bool:
        """
        Determine whether an asset genuinely requires recovery.

        Recovery is required only when:

            1. the asset column is absent; or
            2. the asset column contains zero valid observations.

        A partially missing asset does NOT require recovery.

        This distinction is critical.

        Example
        -------
        Given:

            SPY
            ---
            100
            NaN
            102
            NaN
            104

        SPY is a valid, partially observed historical series.

        It must remain:

            100
            NaN
            102
            NaN
            104

        It must NOT be downloaded again and merged over the missing
        observations.
        """

        if ticker not in frame.columns:

            return True

        series = frame[ticker]

        if series.dropna().empty:

            return True

        return False

    # ==================================================================
    # SECTION 10
    # RECOVER MISSING ASSETS
    # ==================================================================

    def _recover_missing_assets(
        self,
        prices: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Recover genuinely missing assets individually.

        Recovery contract
        -----------------
        The method recovers only:

            * completely absent asset columns;
            * completely empty / all-NaN asset columns.

        It does NOT recover:

            * individual missing observations;
            * partially missing series;
            * isolated historical gaps.

        No interpolation, forward-fill, backward-fill, or synthetic
        observation generation is permitted.
        """

        frame = (
            prices.copy()
            if prices is not None
            else pd.DataFrame()
        )

        # ------------------------------------------------------------------
        # SECTION 10.1
        # NORMALIZE INPUT FRAME
        # ------------------------------------------------------------------

        if not frame.empty:

            frame.columns = [
                str(column)
                .strip()
                .upper()
                for column in frame.columns
            ]

            frame.index = pd.to_datetime(
                frame.index
            )

            frame = frame.sort_index()

            frame = frame[
                ~frame.index.duplicated(
                    keep="last"
                )
            ]

        # ------------------------------------------------------------------
        # SECTION 10.2
        # IDENTIFY GENUINELY MISSING ASSETS
        # ------------------------------------------------------------------

        recovery_required: list[str] = []

        for ticker in self.assets:

            if self._asset_requires_recovery(
                frame,
                ticker,
            ):

                recovery_required.append(
                    ticker
                )

        # ------------------------------------------------------------------
        # SECTION 10.3
        # NOTHING TO RECOVER
        # ------------------------------------------------------------------

        if not recovery_required:

            self.last_recovered_assets = ()

            return frame

        logger.warning(
            "Assets requiring recovery: %s",
            recovery_required,
        )

        recovered: list[str] = []

        # ------------------------------------------------------------------
        # SECTION 10.4
        # INDIVIDUAL RECOVERY
        # ------------------------------------------------------------------

        for ticker in recovery_required:

            series = self._download_single(
                ticker
            )

            if series is None:

                logger.error(
                    "Unable to recover %s.",
                    ticker,
                )

                continue

            series = series.copy()

            series.index = pd.to_datetime(
                series.index
            )

            series = series.sort_index()

            series = series[
                ~series.index.duplicated(
                    keep="last"
                )
            ]

            series = pd.to_numeric(
                series,
                errors="coerce",
            )

            series.name = ticker

            # --------------------------------------------------------------
            # COMPLETELY MISSING ASSET
            # --------------------------------------------------------------

            if ticker not in frame.columns:

                frame = frame.join(
                    series,
                    how="outer",
                )

                if not frame[ticker].dropna().empty:

                    recovered.append(
                        ticker
                    )

                continue

            # --------------------------------------------------------------
            # ALL-NA ASSET
            # --------------------------------------------------------------

            original = frame[
                ticker
            ].copy()

            if original.dropna().empty:

                frame[ticker] = series

                if not frame[ticker].dropna().empty:

                    recovered.append(
                        ticker
                    )

                continue

            # --------------------------------------------------------------
            # DEFENSIVE BRANCH
            #
            # This branch should not normally be reached because
            # _asset_requires_recovery() excludes partially missing
            # assets.
            #
            # It is deliberately fail-preserving rather than filling
            # observations.
            # --------------------------------------------------------------

            logger.warning(
                "Skipping recovery merge for %s because "
                "valid observations already exist.",
                ticker,
            )

        self.last_recovered_assets = tuple(
            recovered
        )

        return frame

    # ==================================================================
    # SECTION 11
    # FINAL NORMALIZATION
    # ==================================================================

    def _finalize(
        self,
        prices: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Normalize the final price matrix and update loader state.

        No imputation occurs during finalization.
        """

        if prices is None or prices.empty:

            raise DataValidationError(
                "No historical price data returned."
            )

        frame = prices.copy()

        # ------------------------------------------------------------------
        # SECTION 11.1
        # REQUESTED UNIVERSE
        # ------------------------------------------------------------------

        frame = frame.reindex(
            columns=self.assets
        )

        # ------------------------------------------------------------------
        # SECTION 11.2
        # INDEX NORMALIZATION
        # ------------------------------------------------------------------

        frame.index = pd.to_datetime(
            frame.index
        )

        frame = frame.sort_index()

        frame = frame[
            ~frame.index.duplicated(
                keep="last"
            )
        ]

        # ------------------------------------------------------------------
        # SECTION 11.3
        # NUMERIC CONVERSION
        # ------------------------------------------------------------------

        for ticker in self.assets:

            frame[ticker] = pd.to_numeric(
                frame[ticker],
                errors="coerce",
            )

        # ------------------------------------------------------------------
        # SECTION 11.4
        # NO IMPUTATION
        #
        # Explicitly prohibited:
        #
        #   * forward-fill
        #   * backward-fill
        #   * interpolation
        #   * synthetic values
        # ------------------------------------------------------------------

        # ------------------------------------------------------------------
        # SECTION 11.5
        # COMPLETENESS STATE
        # ------------------------------------------------------------------

        incomplete: list[str] = []

        for ticker in self.assets:

            if ticker not in frame.columns:

                incomplete.append(
                    ticker
                )

                continue

            if frame[ticker].isna().any():

                incomplete.append(
                    ticker
                )

        self.last_incomplete_assets = tuple(
            incomplete
        )

        # ------------------------------------------------------------------
        # SECTION 11.6
        # DOWNLOADED ASSETS
        # ------------------------------------------------------------------

        self.last_downloaded_assets = tuple(
            ticker
            for ticker in self.assets
            if ticker in frame.columns
            and not frame[ticker].dropna().empty
        )

        # ------------------------------------------------------------------
        # SECTION 11.7
        # FAILED ASSETS
        # ------------------------------------------------------------------

        self.last_failed_assets = tuple(
            ticker
            for ticker in self.assets
            if (
                ticker
                not in self.last_downloaded_assets
                or ticker
                in self.last_incomplete_assets
            )
        )

        return frame

    # ==================================================================
    # SECTION 12
    # PUBLIC PRICE API
    # ==================================================================

    def _assess_freshness(
        self,
        prices: pd.DataFrame,
    ) -> None:
        """Assess latest valid observations against max_data_age."""

        self.last_stale_assets = ()
        self.last_observation_timestamps = {}
        self.last_freshness_age_seconds = {}

        if self.max_data_age is None:
            self.last_freshness_status = "DISABLED"
            return

        now = self._clock()

        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError(
                "clock must return a timezone-aware datetime"
            )

        now_utc = now.astimezone(timezone.utc)

        latest_session = self._calendar.latest_completed_session(
            now_utc
        )

        reference_time = min(
            latest_session,
            now_utc,
        )

        stale_assets: list[str] = []

        for asset in self.assets:

            if asset not in prices.columns:
                self.last_observation_timestamps[asset] = None
                self.last_freshness_age_seconds[asset] = None
                stale_assets.append(asset)
                continue

            series = prices[asset].dropna()

            if series.empty:
                self.last_observation_timestamps[asset] = None
                self.last_freshness_age_seconds[asset] = None
                stale_assets.append(asset)
                continue

            observation = series.index[-1]

            if not isinstance(observation, pd.Timestamp):
                observation = pd.Timestamp(observation)

            if (
                observation.tzinfo is None
                or observation.utcoffset() is None
            ):
                # Historical loader output may contain naive timestamps.
                # Treat them as UTC rather than silently mixing timezone
                # semantics during freshness evaluation.
                observation_utc = observation.tz_localize("UTC")
            else:
                observation_utc = observation.tz_convert("UTC")

            age_seconds = max(
                0.0,
                (
                    reference_time - observation_utc
                ).total_seconds(),
            )

            self.last_observation_timestamps[asset] = (
                observation_utc.isoformat()
            )

            self.last_freshness_age_seconds[asset] = (
                age_seconds
            )

            if age_seconds > self.max_data_age.total_seconds():
                stale_assets.append(asset)

        self.last_stale_assets = tuple(
            sorted(set(stale_assets))
        )

        self.last_freshness_status = (
            "STALE"
            if self.last_stale_assets
            else "FRESH"
        )

    def load_prices(
        self,
        validate: bool = True,
    ) -> pd.DataFrame:
        """
        Load historical prices.

        Parameters
        ----------
        validate:
            When True, the final matrix is passed through
            DataValidator.

            When False, incomplete observations remain visible for
            explicit research handling.

        Returns
        -------
        pandas.DataFrame
            Historical price matrix in requested asset order.
        """

        prices = self._download_batch()

        prices = self._recover_missing_assets(
            prices
        )

        prices = self._finalize(
            prices
        )

        self._assess_freshness(
            prices
        )

        if validate:

            DataValidator.validate_prices(
                prices
            )

        return prices

    # ==================================================================
    # SECTION 13
    # PUBLIC RETURNS API
    # ==================================================================

    def load_returns(
        self,
    ) -> pd.DataFrame:
        """
        Load validated historical percentage returns.

        No missing-price imputation is performed before calculating
        returns.
        """

        try:

            prices = self.load_prices()

            if prices is None or prices.empty:

                raise RuntimeError(
                    "No market data returned."
                )

            returns = (
                prices
                .pct_change(
                    fill_method=None
                )
                .dropna()
            )

            if returns.empty:

                raise RuntimeError(
                    "Return series is empty."
                )

            DataValidator.validate_returns(
                returns
            )

            return returns

        except RuntimeError:

            raise

        except Exception as exc:

            logger.exception(
                "Market data loading failed."
            )

            raise RuntimeError(
                str(exc)
            ) from exc

    # ==================================================================
    # SECTION 14
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> dict:
        """
        Return deterministic loader health information.

        ``healthy`` is false whenever any requested asset has failed
        recovery or remains incomplete.
        """

        return {
            "api_version": self.API_VERSION,
            "component": self.COMPONENT,
            "healthy": (
                not bool(self.last_failed_assets)
                and not bool(self.last_stale_assets)
            ),
            "asset_count": len(
                self.assets
            ),
            "assets": list(
                self.assets
            ),
            "downloaded_assets": list(
                self.last_downloaded_assets
            ),
            "failed_assets": list(
                self.last_failed_assets
            ),
            "recovered_assets": list(
                self.last_recovered_assets
            ),
            "incomplete_assets": list(
                self.last_incomplete_assets
            ),
            "batch_error": self.last_batch_error,
            "period": self.period,
            "max_data_age_seconds": (
                self.max_data_age.total_seconds()
                if self.max_data_age is not None
                else None
            ),
            "stale_assets": list(
                self.last_stale_assets
            ),
            "observation_timestamps": dict(
                self.last_observation_timestamps
            ),
            "freshness_age_seconds": dict(
                self.last_freshness_age_seconds
            ),
            "freshness_status": self.last_freshness_status,
        }


# ======================================================================
# SECTION 15
# MODULE-LEVEL REGRESSION TEST
# ======================================================================


def test_market_data_exception() -> None:
    """
    Minimal module-level regression test.

    Full production regression coverage belongs in
    ``test_marketdataloader.py``.
    """

    class BrokenLoader(
        MarketDataLoader
    ):

        def load_prices(
            self,
            validate: bool = True,
        ):

            raise RuntimeError(
                "Yahoo unavailable"
            )

    try:

        BrokenLoader(
            assets=["SPY"]
        ).load_returns()

    except RuntimeError:

        print(
            "RuntimeError correctly raised"
        )

        return

    raise AssertionError(
        "BrokenLoader did not raise RuntimeError."
    )


# ======================================================================
# SECTION 16
# MODULE EXECUTION
# ======================================================================


if __name__ == "__main__":

    test_market_data_exception()

    print(
        "MarketDataLoader tests passed."
    )