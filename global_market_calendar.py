"""Venue-specific regular-session timing; unsupported venues fail closed."""

from datetime import timedelta
import pandas as pd
import pandas_market_calendars as mcal

VENUES = {"XNYS": "NYSE", "XLON": "LSE", "XHKG": "HKEX", "XJSE": "XJSE"}


def aware(value):
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError("Aware timestamp required")
    return stamp.tz_convert("UTC")


def schedule(venue, start, end):
    if venue not in VENUES:
        raise ValueError("Venue calendar unqualified or unsupported")
    if (pd.Timestamp(end) - pd.Timestamp(start)).days > 370:
        raise ValueError("Calendar request exceeds resource bound")
    return mcal.get_calendar(VENUES[venue]).schedule(start, end)


def is_regular_session(venue, now):
    stamp = aware(now)
    rows = schedule(
        venue, (stamp - timedelta(days=1)).date(), (stamp + timedelta(days=1)).date()
    )
    for _, row in rows.iterrows():
        if row.market_open <= stamp < row.market_close:
            if "break_start" in rows and row.break_start <= stamp < row.break_end:
                return False
            return True
    return False


def latest_completed_session(venue, now):
    stamp = aware(now)
    rows = schedule(venue, (stamp - timedelta(days=31)).date(), stamp.date())
    complete = rows.loc[rows.market_close <= stamp]
    if complete.empty:
        raise ValueError("No completed session in bounded calendar window")
    return str(complete.index[-1].date())


def next_close(venue, decision_time):
    stamp = aware(decision_time)
    rows = schedule(venue, stamp.date(), (stamp + timedelta(days=31)).date())
    later = rows.loc[rows.market_close > stamp]
    if later.empty:
        raise ValueError("No later close in bounded calendar window")
    return later.market_close.iloc[0].isoformat()
