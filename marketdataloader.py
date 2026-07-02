from core_constants import (
    DEFAULT_ASSETS,
    settings
)

import logging

import pandas as pd
import yfinance as yf

from validators import DataValidator

logger = logging.getLogger(__name__)

# ============================================================
# MARKET DATA
# ============================================================


class MarketDataLoader:

    def __init__(
        self,
        assets=None,
        period=None
    ):

        self.assets = (
            assets
            if assets
            else DEFAULT_ASSETS
        )

        self.period = (
            period
            if period
            else settings.yahoo_period
        )

    def load_prices(self):

        logger.info(
            "Downloading prices for %s",
            self.assets
        )

        prices = yf.download(
            self.assets,
            period=self.period,
            auto_adjust=True,
            progress=False
        )

        if isinstance(
            prices.columns,
            pd.MultiIndex
        ):

            prices = prices["Close"]

        DataValidator.validate_prices(
            prices
        )

        return prices

    def load_returns(self):

        logger.info(
            "Downloading prices for %s",
            self.assets
        )

        try:

            prices = self.load_prices()

            if prices is None or prices.empty:
                raise RuntimeError(
                    "No market data returned."
                )

            returns = (
                prices
                .pct_change()
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

        except Exception as e:

            logger.exception(
                "Market data loading failed."
            )

            raise RuntimeError(
                str(e)
            ) from e


# ============================================================
# TESTS
# ============================================================


def test_market_data_exception():

    class BrokenLoader(MarketDataLoader):

        def load_prices(self):
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

    assert False