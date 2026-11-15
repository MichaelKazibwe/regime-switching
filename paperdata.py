"""Real-data input adapter for the daily paper worker.

Yahoo Finance supplies adjusted ETF prices. FRED macro observations are
delayed before they are aligned to market dates; revised FRED values are not
vintage data, so these inputs are for paper operation and not unbiased
historical backtests.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from fredapi import Fred

from core_constants import settings
from macroregime import MacroRegimeModel
from marketdataloader import MarketDataLoader
from paperconfig import PaperRuntimeConfig
from tradingcalendar import TradingCalendar


class PaperDataError(RuntimeError):
    """Raised when required market or macro observations are unavailable."""


class PaperDataProvider:
    """Fetch and validate the configured ETF and macro input envelope."""

    FRED_SERIES = {
        "unemployment": "UNRATE",
        "cpi": "CPIAUCSL",
        "gdp": "GDP",
        "ten_year": "DGS10",
        "two_year": "DGS2",
    }
    RELEASE_LAG_DAYS = {"UNRATE": 45, "CPIAUCSL": 45, "GDP": 90}

    def __init__(self, config: PaperRuntimeConfig, *, clock=None, fred_client=None) -> None:
        self.config = config
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.fred_client = fred_client

    def _fred(self):
        if self.fred_client is not None:
            return self.fred_client
        key = os.environ.get("FRED_API_KEY") or settings.fred_api_key
        if not key:
            raise PaperDataError("FRED_API_KEY is required for the paper data adapter.")
        return Fred(api_key=key)

    def _macro_observations(self, market_index: pd.DatetimeIndex) -> dict[str, pd.Series]:
        fred = self._fred()
        first_date = (market_index.min() - pd.Timedelta(days=500)).date().isoformat()
        series: dict[str, pd.Series] = {}
        for key, series_id in self.FRED_SERIES.items():
            try:
                observations = fred.get_series(series_id, observation_start=first_date)
            except Exception as exc:
                raise PaperDataError(f"Unable to load FRED series {series_id}: {exc}") from exc
            if observations is None or observations.empty:
                raise PaperDataError(f"FRED series {series_id} is empty.")
            observations = pd.to_numeric(observations, errors="coerce").dropna()
            observations.index = pd.DatetimeIndex(observations.index).tz_localize(None)
            lag = self.RELEASE_LAG_DAYS.get(series_id, 0)
            observations.index = observations.index + pd.to_timedelta(lag, unit="D")
            series[key] = observations.sort_index()
        return series

    def __call__(self) -> dict[str, Any]:
        max_age = timedelta(hours=self.config.maximum_price_age_hours)
        loader = MarketDataLoader(
            assets=self.config.assets,
            period=self.config.market_period,
            max_data_age=max_age,
            clock=self.clock,
        )
        prices = loader.load_prices(validate=True)
        health = loader.health_check()
        if not health.get("healthy"):
            raise PaperDataError(f"Market data health check failed: {health}")
        if tuple(prices.columns) != self.config.assets:
            raise PaperDataError("Market price columns do not match the configured universe.")
        returns = prices.pct_change(fill_method=None).dropna()
        if returns.empty or not returns.index.equals(prices.index[1:]):
            raise PaperDataError("Market return history is empty or misaligned.")

        macro = self._macro_observations(prices.index)
        aligned = {
            key: values.reindex(prices.index, method="ffill")
            for key, values in macro.items()
        }
        aligned = {key: value.dropna() for key, value in aligned.items()}
        if any(value.empty for value in aligned.values()):
            raise PaperDataError("Macro history does not overlap the price history.")

        inflation = macro["cpi"].pct_change(12, fill_method=None) * 100.0
        growth = macro["gdp"].pct_change(4, fill_method=None) * 100.0
        inflation = inflation.dropna().reindex(prices.index, method="ffill")
        growth = growth.dropna().reindex(prices.index, method="ffill")
        spread = aligned["ten_year"] - aligned["two_year"]
        unemployment = aligned["unemployment"]
        model = MacroRegimeModel()
        regimes: list[str] = []
        for date in returns.index:
            current_unemployment = unemployment.loc[:date]
            current_spread = spread.loc[:date].dropna()
            current_inflation = inflation.loc[:date].dropna()
            if current_spread.empty or current_inflation.empty:
                regimes.append("EXPANSION")
                continue
            regimes.append(
                model.classify(
                    current_unemployment,
                    current_spread.iloc[-1],
                    current_inflation.iloc[-1],
                ).name
            )
        if len(regimes) != len(returns):
            raise PaperDataError("Regime history is not aligned to returns.")

        latest_date = prices.index[-1]
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise PaperDataError("Data provider clock must be timezone-aware.")
        expected_close = TradingCalendar().latest_completed_session(now)
        if expected_close is None:
            raise PaperDataError("No completed NYSE session is available for this cycle.")
        if latest_date.date() != expected_close.date():
            raise PaperDataError(
                "Market prices do not include the latest completed NYSE session."
            )
        as_of = expected_close.to_pydatetime().astimezone(timezone.utc)
        if as_of > now.astimezone(timezone.utc) + timedelta(minutes=5):
            raise PaperDataError("Market data timestamp is in the future.")

        macro_data = {
            "growth": float(growth.dropna().iloc[-1]),
            "inflation": float(inflation.dropna().iloc[-1]),
            "yield_spread": float(spread.dropna().iloc[-1]),
            "unemployment": unemployment,
        }
        portfolio = {ticker: 1.0 / len(self.config.assets) for ticker in self.config.assets}
        return {
            "portfolio": portfolio,
            "returns": returns,
            "prices": prices,
            "regimes": regimes,
            "macro_data": macro_data,
            "data_as_of": as_of,
            "data_source": "YAHOO_FINANCE+FRED",
            "benchmark": self.config.benchmark,
        }
