"""
5J.2 TradingCalendar certification tests.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from tradingcalendar import TradingCalendar


def test_calendar_initializes_with_nyse():
    calendar = TradingCalendar()

    assert calendar.calendar_name == "NYSE"
    assert calendar.API_VERSION == "1.0.0"


def test_utc_clock_is_timezone_aware():
    calendar = TradingCalendar()

    timestamp = calendar.utc_now()

    assert timestamp.tzinfo is not None
    assert timestamp.utcoffset() is not None


def test_naive_as_of_is_deterministically_interpreted_as_utc():
    calendar = TradingCalendar()

    result = calendar.normalize_as_of(
        "2026-01-05 15:00:00"
    )

    assert result.tzinfo is not None
    assert str(result.tz) == "UTC"
    assert result == pd.Timestamp(
        "2026-01-05 15:00:00",
        tz="UTC",
    )


def test_timezone_aware_as_of_is_converted_to_utc():
    calendar = TradingCalendar()

    result = calendar.normalize_as_of(
        "2026-01-05 15:00:00+00:00"
    )

    assert result == pd.Timestamp(
        "2026-01-05 15:00:00",
        tz="UTC",
    )


def test_weekday_trading_day():
    calendar = TradingCalendar()

    assert calendar.is_trading_day(
        "2026-01-05"
    )


def test_weekend_is_not_trading_day():
    calendar = TradingCalendar()

    assert not calendar.is_trading_day(
        "2026-01-03"
    )


def test_known_nyse_holiday_is_not_trading_day():
    calendar = TradingCalendar()

    # 2026-01-01 is New Year's Day.
    assert not calendar.is_trading_day(
        "2026-01-01"
    )


def test_market_open_during_known_session():
    calendar = TradingCalendar()

    assert calendar.is_market_open(
        datetime(
            2026,
            1,
            5,
            15,
            0,
            tzinfo=UTC,
        )
    )


def test_market_closed_after_session():
    calendar = TradingCalendar()

    assert not calendar.is_market_open(
        datetime(
            2026,
            1,
            5,
            22,
            0,
            tzinfo=UTC,
        )
    )


def test_market_closed_on_weekend():
    calendar = TradingCalendar()

    assert not calendar.is_market_open(
        datetime(
            2026,
            1,
            3,
            15,
            0,
            tzinfo=UTC,
        )
    )


def test_latest_completed_session_ignores_weekend_gap():
    calendar = TradingCalendar()

    result = calendar.latest_completed_session(
        datetime(
            2026,
            1,
            3,
            15,
            0,
            tzinfo=UTC,
        )
    )

    assert result is not None

    # Friday 2026-01-02 NYSE close = 21:00 UTC.
    assert result == pd.Timestamp(
        "2026-01-02 21:00:00",
        tz="UTC",
    )


def test_latest_completed_session_before_market_open():
    calendar = TradingCalendar()

    result = calendar.latest_completed_session(
        datetime(
            2026,
            1,
            5,
            14,
            0,
            tzinfo=UTC,
        )
    )

    assert result is not None

    # Friday's completed session remains the latest completed session.
    assert result == pd.Timestamp(
        "2026-01-02 21:00:00",
        tz="UTC",
    )


def test_health_contract():
    calendar = TradingCalendar()

    health = calendar.health_check()

    assert health == {
        "api_version": "1.0.0",
        "component": "TradingCalendar",
        "healthy": True,
        "exchange": "NYSE",
    }


def test_invalid_calendar_name_fails_closed():
    with pytest.raises(Exception):
        TradingCalendar("NOT_A_REAL_EXCHANGE")
