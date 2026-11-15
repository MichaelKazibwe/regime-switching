from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from assetuniverse import PRODUCTION_ASSETS
from paperconfig import PaperRuntimeConfig
from paperdata import PaperDataError, PaperDataProvider
from tradingcalendar import TradingCalendar


class _FakeFred:
    def __init__(self) -> None:
        self.series = {
            "UNRATE": pd.Series(
                np.linspace(5.0, 4.0, 48),
                index=pd.date_range("2022-01-01", periods=48, freq="MS"),
            ),
            "CPIAUCSL": pd.Series(
                np.linspace(250.0, 300.0, 48),
                index=pd.date_range("2022-01-01", periods=48, freq="MS"),
            ),
            "GDP": pd.Series(
                np.linspace(20_000.0, 25_000.0, 20),
                index=pd.date_range("2022-01-01", periods=20, freq="QS"),
            ),
            "DGS10": pd.Series(
                np.full(700, 4.0),
                index=pd.bdate_range("2024-01-01", periods=700),
            ),
            "DGS2": pd.Series(
                np.full(700, 3.0),
                index=pd.bdate_range("2024-01-01", periods=700),
            ),
        }

    def get_series(self, series_id, observation_start=None):
        return self.series[series_id]


class _FakeMarketDataLoader:
    def __init__(self, assets, **kwargs) -> None:
        self.assets = tuple(assets)
        self.clock = kwargs["clock"]

    def load_prices(self, validate=True):
        last_session = TradingCalendar().latest_completed_session(self.clock())
        index = pd.bdate_range(end=last_session.date(), periods=300)
        values = np.arange(300, dtype=float)[:, None] * 0.01 + 100.0
        return pd.DataFrame(
            np.repeat(values, len(self.assets), axis=1),
            index=index,
            columns=self.assets,
        )

    @staticmethod
    def health_check():
        return {"healthy": True}


def test_paper_data_provider_builds_aligned_market_macro_envelope(monkeypatch) -> None:
    monkeypatch.setattr("paperdata.MarketDataLoader", _FakeMarketDataLoader)
    now = datetime(2026, 10, 29, 23, tzinfo=timezone.utc)
    config = PaperRuntimeConfig(timezone="America/New_York")
    provider = PaperDataProvider(config, clock=lambda: now, fred_client=_FakeFred())

    result = provider()

    assert tuple(result["prices"].columns) == tuple(PRODUCTION_ASSETS)
    assert result["returns"].index.equals(result["prices"].index[1:])
    assert len(result["regimes"]) == len(result["returns"])
    assert result["macro_data"]["growth"] > 0
    assert result["macro_data"]["inflation"] > 0
    assert result["data_source"] == "YAHOO_FINANCE+FRED"
    assert result["data_as_of"].tzinfo is not None
    assert result["data_as_of"] == TradingCalendar().latest_completed_session(now).to_pydatetime()


def test_paper_data_provider_rejects_missing_latest_market_session(monkeypatch) -> None:
    class _StaleMarketDataLoader(_FakeMarketDataLoader):
        def load_prices(self, validate=True):
            prices = super().load_prices(validate=validate)
            prices.index = prices.index - pd.Timedelta(days=1)
            return prices

    monkeypatch.setattr("paperdata.MarketDataLoader", _StaleMarketDataLoader)
    now = datetime(2026, 10, 29, 23, tzinfo=timezone.utc)
    provider = PaperDataProvider(
        PaperRuntimeConfig(timezone="America/New_York"),
        clock=lambda: now,
        fred_client=_FakeFred(),
    )
    with pytest.raises(PaperDataError, match="latest completed NYSE session"):
        provider()
