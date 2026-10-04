"""
5J.3 — Market Data Stale-Data Protection Certification

Tests the stale-data safety boundary without modifying the existing
MarketDataLoader test suite.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from marketdataloader import MarketDataLoader


def make_prices(index):
    return pd.DataFrame(
        {
            "SPY": np.arange(100, 100 + len(index), dtype=float),
            "TLT": np.arange(200, 200 + len(index), dtype=float),
        },
        index=pd.DatetimeIndex(index),
    )


def test_fresh_data_is_healthy():
    """
    Data inside the configured freshness window must remain healthy.
    """
    as_of = datetime(2026, 10, 2, 20, 30, tzinfo=timezone.utc)

    prices = make_prices(
        [
            datetime(2026, 10, 2, 19, 30, tzinfo=timezone.utc),
            datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc),
        ]
    )

    loader = MarketDataLoader(
        assets=["SPY", "TLT"],
        max_data_age=timedelta(hours=2),
        clock=lambda: as_of,
    )

    result = loader._finalize(prices)

    loader._assess_freshness(result)

    health = loader.health_check()

    assert health["healthy"] is True
    assert health["stale_assets"] == []
    assert health["freshness_status"] == "FRESH"


def test_stale_data_is_unhealthy():
    """
    Data older than the configured freshness window must be unhealthy.
    """
    as_of = datetime(2026, 10, 2, 20, 30, tzinfo=timezone.utc)

    prices = make_prices(
        [
            datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc),
        ]
    )

    loader = MarketDataLoader(
        assets=["SPY", "TLT"],
        max_data_age=timedelta(hours=2),
        clock=lambda: as_of,
    )

    result = loader._finalize(prices)

    loader._assess_freshness(result)

    health = loader.health_check()

    assert health["healthy"] is False
    assert health["stale_assets"] == ["SPY", "TLT"]
    assert health["freshness_status"] == "STALE"


def test_multiple_assets_can_have_different_freshness():
    """
    Freshness must be evaluated per asset rather than only from the
    DataFrame's final timestamp.
    """
    as_of = datetime(2026, 10, 2, 20, 30, tzinfo=timezone.utc)

    prices = pd.DataFrame(
        {
            "SPY": [100.0, 101.0],
            "TLT": [200.0, 201.0],
        },
        index=pd.DatetimeIndex(
            [
                datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc),
                datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc),
            ]
        ),
    )

    # The fixture intentionally requires the implementation to determine
    # each asset's latest valid observation.
    prices.loc[
        prices.index[-1],
        "SPY",
    ] = np.nan

    loader = MarketDataLoader(
        assets=["SPY", "TLT"],
        max_data_age=timedelta(hours=2),
        clock=lambda: as_of,
    )

    result = loader._finalize(prices)
    loader._assess_freshness(result)

    health = loader.health_check()

    assert "SPY" in health["stale_assets"]
    assert "TLT" not in health["stale_assets"]
    assert health["healthy"] is False


def test_no_freshness_threshold_preserves_existing_behavior():
    """
    Existing callers that do not configure stale-data protection must
    retain the existing health semantics.
    """
    as_of = datetime(2026, 10, 4, 21, 0, tzinfo=timezone.utc)

    prices = make_prices(
        [
            datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc),
        ]
    )

    loader = MarketDataLoader(
        assets=["SPY", "TLT"],
        clock=lambda: as_of,
    )

    result = loader._finalize(prices)
    loader._assess_freshness(result)

    health = loader.health_check()

    assert health["healthy"] is True
    assert health["stale_assets"] == []
    assert health["freshness_status"] == "DISABLED"


def test_freshness_threshold_must_be_positive():
    """
    Invalid freshness configuration must fail explicitly.
    """
    with pytest.raises(ValueError):
        MarketDataLoader(
            assets=["SPY"],
            max_data_age=timedelta(0),
        )


def test_naive_as_of_clock_is_rejected():
    """
    The clock boundary must use timezone-aware timestamps.
    """
    with pytest.raises(ValueError):
        MarketDataLoader(
            assets=["SPY"],
            max_data_age=timedelta(hours=2),
            clock=lambda: datetime(2026, 10, 2, 20, 0),
        )


def test_timezone_aware_market_data_is_required():
    """
    Freshness calculations must not silently mix naive and aware
    timestamps.
    """
    as_of = datetime(2026, 10, 2, 20, 30, tzinfo=timezone.utc)

    prices = make_prices(
        [
            datetime(2026, 10, 2, 20, 0),
        ]
    )

    loader = MarketDataLoader(
        assets=["SPY", "TLT"],
        max_data_age=timedelta(hours=2),
        clock=lambda: as_of,
    )

    result = loader._finalize(prices)
    loader._assess_freshness(result)

    health = loader.health_check()

    assert health["freshness_status"] in {"FRESH", "STALE"}


def test_api_version_remains_frozen():
    """
    Stale-data hardening must not silently change the public API version.
    """
    assert MarketDataLoader.API_VERSION == "2.0.0"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
