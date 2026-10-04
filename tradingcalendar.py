"""
======================================================================
TRADING CALENDAR
======================================================================

Production trading-session and clock boundary.

Purpose
-------
Provides the authoritative market-session calendar used by production
safety controls.

Design guarantees
-----------------
1. Uses the NYSE trading calendar.
2. Uses timezone-aware UTC reference timestamps.
3. Accepts an explicit ``as_of`` timestamp for deterministic testing.
4. Does not use ``pd.Timestamp.today()``.
5. Does not mutate market-data timestamps.
6. Distinguishes trading sessions from non-trading days.
7. Provides session information without making execution decisions.

This module is intentionally small. It is a shared infrastructure
boundary for clock/calendar-aware safety controls.

Version
-------
1.0.0
======================================================================
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pandas_market_calendars as mcal


class TradingCalendar:
    """
    Authoritative NYSE trading-calendar boundary.
    """

    API_VERSION = "1.0.0"
    COMPONENT = "TradingCalendar"
    EXCHANGE = "NYSE"

    def __init__(self, calendar_name: str = EXCHANGE) -> None:
        if not isinstance(calendar_name, str) or not calendar_name.strip():
            raise ValueError("calendar_name must be a non-empty string.")

        self.calendar_name = calendar_name.strip().upper()
        self._calendar = mcal.get_calendar(self.calendar_name)

    # ==================================================================
    # CLOCK
    # ==================================================================

    @staticmethod
    def utc_now() -> datetime:
        """
        Return the current timezone-aware UTC timestamp.
        """
        return datetime.now(UTC)

    @staticmethod
    def normalize_as_of(as_of: datetime | pd.Timestamp | str | None) -> pd.Timestamp:
        """
        Normalize an evaluation timestamp to timezone-aware UTC.

        Naive timestamps are interpreted as UTC deliberately so tests can
        provide simple deterministic timestamps without depending on the
        machine's local timezone.
        """
        if as_of is None:
            timestamp = pd.Timestamp(TradingCalendar.utc_now())
        else:
            timestamp = pd.Timestamp(as_of)

        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")

        return timestamp

    # ==================================================================
    # SESSION
    # ==================================================================

    def is_trading_day(
        self,
        date: str | pd.Timestamp | datetime,
    ) -> bool:
        """
        Return whether the supplied calendar date is an NYSE session.
        """
        timestamp = pd.Timestamp(date)

        schedule = self._calendar.schedule(
            start_date=timestamp.date(),
            end_date=timestamp.date(),
        )

        return not schedule.empty

    def session(
        self,
        date: str | pd.Timestamp | datetime,
    ) -> pd.Series | None:
        """
        Return the NYSE session row for a date, or None if the date is
        not a trading session.
        """
        timestamp = pd.Timestamp(date)

        schedule = self._calendar.schedule(
            start_date=timestamp.date(),
            end_date=timestamp.date(),
        )

        if schedule.empty:
            return None

        return schedule.iloc[0]

    def is_market_open(
        self,
        as_of: datetime | pd.Timestamp | str | None = None,
    ) -> bool:
        """
        Return whether the NYSE market is open at ``as_of``.

        The evaluation timestamp is normalized to UTC before comparison
        with the calendar's timezone-aware session boundaries.
        """
        timestamp = self.normalize_as_of(as_of)

        session = self.session(timestamp)

        if session is None:
            return False

        return bool(
            session["market_open"]
            <= timestamp
            <= session["market_close"]
        )

    def latest_completed_session(
        self,
        as_of: datetime | pd.Timestamp | str | None = None,
    ) -> pd.Timestamp | None:
        """
        Return the most recent NYSE session close at or before ``as_of``.

        This deliberately operates on completed sessions rather than
        elapsed calendar hours. Therefore weekends and exchange holidays
        do not create false stale-data conditions.
        """
        timestamp = self.normalize_as_of(as_of)

        start = (timestamp - pd.Timedelta(days=14)).date()
        end = timestamp.date()

        schedule = self._calendar.schedule(
            start_date=start,
            end_date=end,
        )

        if schedule.empty:
            return None

        completed = schedule.loc[
            schedule["market_close"] <= timestamp
        ]

        if completed.empty:
            return None

        return pd.Timestamp(completed["market_close"].iloc[-1]).tz_convert(
            "UTC"
        )

    def health_check(self) -> dict[str, object]:
        """
        Return deterministic component health metadata.
        """
        return {
            "api_version": self.API_VERSION,
            "component": self.COMPONENT,
            "healthy": True,
            "exchange": self.calendar_name,
        }


if __name__ == "__main__":
    calendar = TradingCalendar()

    now = calendar.utc_now()

    print("TradingCalendar 5J.2 self-test")
    print("API version:", calendar.API_VERSION)
    print("Exchange:", calendar.calendar_name)
    print("UTC now:", now.isoformat())
    print("Trading day:", calendar.is_trading_day(now))
    print("Market open:", calendar.is_market_open(now))
    print(
        "Latest completed session:",
        calendar.latest_completed_session(now),
    )
    print("Health:", calendar.health_check())
