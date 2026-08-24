from __future__ import annotations

import logging
from typing import Iterable

import pandas as pd
import yfinance as yf

from core_constants import DEFAULT_ASSETS, settings
from exceptions import DataValidationError
from validators import DataValidator


logger = logging.getLogger(__name__)


# ============================================================
# MARKET DATA LOADER
# ============================================================


class MarketDataLoader:
    """
    Production-grade historical market-data loader.

    Design principles
    -----------------
    1. Attempt a batched Yahoo Finance download first.
    2. Normalize Yahoo Finance MultiIndex output.
    3. Detect missing/empty assets explicitly.
    4. Retry failed assets individually.
    5. Never silently fabricate prices.
    6. Preserve the requested asset universe.
    7. Validate the final price matrix before returning it.
    """

    API_VERSION = "2.0.0"

    def __init__(
        self,
        assets: Iterable[str] | None = None,
        period: str | None = None,
        *,
        auto_adjust: bool = True,
        max_retries: int = 2,
    ) -> None:

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

        self.last_downloaded_assets: tuple[str, ...] = ()
        self.last_failed_assets: tuple[str, ...] = ()
        self.last_recovered_assets: tuple[str, ...] = ()
        self.last_batch_error: str | None = None
        self.last_incomplete_assets: tuple[str, ...] = ()

    # ========================================================
    # NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_assets(
        assets: Iterable[str],
    ) -> list[str]:

        normalized: list[str] = []

        for asset in assets:

            ticker = str(asset).strip().upper()

            if not ticker:
                continue

            if ticker not in normalized:
                normalized.append(ticker)

        return normalized

    # ========================================================
    # DOWNLOAD HELPERS
    # ========================================================

    def _download(
        self,
        ticker_or_tickers,
    ) -> pd.DataFrame:

        return yf.download(
            ticker_or_tickers,
            period=self.period,
            auto_adjust=self.auto_adjust,
            progress=False,
            threads=False,
        )

    # ========================================================
    # MULTIINDEX NORMALIZATION
    # ========================================================

    @staticmethod
    def _extract_close(
        data: pd.DataFrame,
    ) -> pd.DataFrame:

        if data is None:
            return pd.DataFrame()

        if data.empty:
            return pd.DataFrame()

        frame = data.copy()

        # ----------------------------------------------------
        # Standard single-ticker response
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # MultiIndex response
        #
        # Depending on yfinance version, Yahoo can return:
        #
        # Price / Ticker
        # or
        # Ticker / Price
        # ----------------------------------------------------

        level0 = list(
            frame.columns.get_level_values(0)
        )

        level1 = list(
            frame.columns.get_level_values(1)
        )

        # Price-first:
        #
        # ('Close', 'SPY')
        # ('Close', 'EFA')
        #

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

        # Ticker-first:
        #
        # ('SPY', 'Close')
        # ('EFA', 'Close')
        #

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

    # ========================================================
    # SINGLE-TICKER EXTRACTION
    # ========================================================

    def _download_single(
        self,
        ticker: str,
    ) -> pd.Series | None:

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

                close = (
                    self._extract_close(
                        raw
                    )
                )

                if close.empty:
                    continue

                # Single ticker may still have
                # UNKNOWN as the column name.
                if ticker in close.columns:

                    series = close[
                        ticker
                    ].copy()

                elif "UNKNOWN" in close.columns:

                    series = close[
                        "UNKNOWN"
                    ].copy()

                elif len(close.columns) == 1:

                    series = close.iloc[
                        :, 0
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

                # Do NOT fill missing prices.
                #
                # Missing prices must remain visible
                # and be rejected later.

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

    # ========================================================
    # BATCH DOWNLOAD
    # ========================================================

    def _download_batch(
        self,
    ) -> pd.DataFrame:

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

            # Normalize column names.
            prices.columns = [
                str(column).strip().upper()
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


    # ========================================================
    # RECOVERY
    # ========================================================

    def _recover_missing_assets(
        self,
        prices: pd.DataFrame,
    ) -> pd.DataFrame:

        frame = (
            prices.copy()
            if prices is not None
            else pd.DataFrame()
        )

        # ----------------------------------------------------
        # NORMALIZE INPUT FRAME
        # ----------------------------------------------------

        if not frame.empty:

            frame.columns = [
                str(column).strip().upper()
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

        # ----------------------------------------------------
        # IDENTIFY ASSETS REQUIRING RECOVERY
        # ----------------------------------------------------

        recovery_required: list[str] = []

        for ticker in self.assets:

            # Completely missing column.
            if ticker not in frame.columns:

                recovery_required.append(
                    ticker
                )

                continue

            series = frame[ticker]

            # Completely unusable series.
            if series.dropna().empty:

                recovery_required.append(
                    ticker
                )

                continue

            # Partially missing series.
            #
            # We attempt a fresh Yahoo download.
            #
            # IMPORTANT:
            # We do NOT interpolate, forward-fill,
            # backward-fill, or manufacture prices.
            if series.isna().any():

                recovery_required.append(
                    ticker
                )

        # ----------------------------------------------------
        # NOTHING TO RECOVER
        # ----------------------------------------------------

        if not recovery_required:

            self.last_recovered_assets = ()

            return frame

        logger.warning(
            "Assets requiring recovery: %s",
            recovery_required,
        )

        recovered: list[str] = []

        # ----------------------------------------------------
        # INDIVIDUAL RECOVERY
        # ----------------------------------------------------

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

            # Normalize recovered series.
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

            # ------------------------------------------------
            # COMPLETELY MISSING ASSET
            # ------------------------------------------------

            if ticker not in frame.columns:

                frame = frame.join(
                    series,
                    how="outer",
                )

                recovered.append(
                    ticker
                )

                continue

            # ------------------------------------------------
            # PARTIALLY MISSING ASSET
            # ------------------------------------------------
            #
            # Preserve the original batch observations.
            #
            # Only genuinely missing observations are allowed
            # to be supplied by the individual download.
            #
            # No interpolation.
            # No forward-fill.
            # No backward-fill.
            # No synthetic observations.

            original = frame[ticker].copy()

            merged = original.combine_first(
                series
            )

            frame[ticker] = merged

            # ------------------------------------------------
            # DETERMINE WHETHER RECOVERY ACTUALLY WORKED
            # ------------------------------------------------

            remaining_missing = (
                frame[ticker].isna().any()
            )

            if remaining_missing:

                logger.warning(
                    "Recovery download for %s "
                    "did not eliminate all missing "
                    "observations.",
                    ticker,
                )

            else:

                recovered.append(
                    ticker
                )

        # ----------------------------------------------------
        # FINAL RECOVERY STATE
        # ----------------------------------------------------

        self.last_recovered_assets = tuple(
            recovered
        )

        return frame

    # ========================================================
    # FINAL NORMALIZATION
    # ========================================================

    def _finalize(
        self,
        prices: pd.DataFrame,
    ) -> pd.DataFrame:

        if prices is None or prices.empty:

            raise DataValidationError(
                "No historical price data returned."
            )

        frame = prices.copy()

        # ----------------------------------------------------
        # KEEP ONLY REQUESTED UNIVERSE
        # ----------------------------------------------------

        frame = frame.reindex(
            columns=self.assets
        )

        # ----------------------------------------------------
        # NORMALIZE INDEX
        # ----------------------------------------------------

        frame.index = pd.to_datetime(
            frame.index
        )

        frame = frame.sort_index()

        frame = frame[
            ~frame.index.duplicated(
                keep="last"
            )
        ]

        # ----------------------------------------------------
        # NUMERIC CONVERSION
        # ----------------------------------------------------

        for ticker in self.assets:

            frame[ticker] = pd.to_numeric(
                frame[ticker],
                errors="coerce",
            )

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # DO NOT:
        #   - forward-fill
        #   - backward-fill
        #   - interpolate
        #   - fabricate prices
        #
        # Genuine Yahoo Finance gaps must remain visible.
        # Strict validation will reject them when requested.
        # Historical research callers can explicitly request
        # validate=False and handle incomplete observations.
        # ----------------------------------------------------

        # ----------------------------------------------------
        # DATASET COMPLETENESS STATE
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # DOWNLOADED ASSETS
        # ----------------------------------------------------

        self.last_downloaded_assets = tuple(
            ticker
            for ticker in self.assets
            if ticker in frame.columns
            and not frame[ticker].dropna().empty
        )

        # ----------------------------------------------------
        # FAILED ASSETS
        #
        # An asset is considered failed if:
        #   1. it has no usable observations, OR
        #   2. it contains unresolved missing observations.
        # ----------------------------------------------------

        self.last_failed_assets = tuple(
            ticker
            for ticker in self.assets
            if ticker not in self.last_downloaded_assets
            or ticker in self.last_incomplete_assets
        )

        return frame

    # ========================================================
    # PUBLIC PRICE API
    # ========================================================

    def load_prices(
        self,
        validate: bool = True,
    ) -> pd.DataFrame:

        prices = self._download_batch()

        prices = self._recover_missing_assets(
            prices
        )

        prices = self._finalize(
            prices
        )

        if validate:

            DataValidator.validate_prices(
                prices
            )

        return prices

    # ========================================================
    # PUBLIC RETURNS API
    # ========================================================

    def load_returns(
        self,
    ) -> pd.DataFrame:

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

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self,
    ) -> dict:

        return {
            "api_version": self.API_VERSION,
            "component": "MarketDataLoader",
            "healthy": not bool(
                self.last_failed_assets
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
        }


# ============================================================
# REGRESSION TEST
# ============================================================


def test_market_data_exception() -> None:

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


# ============================================================
# MODULE EXECUTION
# ============================================================


if __name__ == "__main__":

    test_market_data_exception()

    print(
        "MarketDataLoader tests passed."
    )