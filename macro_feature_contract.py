"""Exact-calendar macro feature contract shared by current and vintage readers.

Callers own release availability. This module never fills missing observations.
"""

import numpy as np
import pandas as pd

SERIES = ("UNRATE", "CPIAUCSL", "INDPRO", "DGS10", "DGS3MO")
CONTRACT_VERSION = "EXACT_CALENDAR_V1"


class MacroFeatureUnavailable(ValueError):
    """A required observation is missing or exceeds its freshness limit."""


def calculate_macro_features(views, decision_date):
    date = pd.Timestamp(decision_date)
    if date.tzinfo is not None:
        date = date.tz_convert("America/New_York").tz_localize(None)
    date = date.normalize()
    if set(views) != set(SERIES):
        raise ValueError("All five macro series required")
    dates = {}
    monthly = {}
    for key, series in views.items():
        if (
            not isinstance(series.index, pd.DatetimeIndex)
            or series.index.tz is not None
            or not series.index.is_unique
            or not series.index.is_monotonic_increasing
            or not np.isfinite(series.to_numpy(dtype=float)).all()
        ):
            raise ValueError(f"Invalid macro observations: {key}")
        if not series.empty and series.index[-1].normalize() > date:
            raise ValueError(f"Future macro observation: {key}")
        limit = 14 if key in {"DGS10", "DGS3MO"} else 90
        if series.empty or (date.date() - series.index[-1].date()).days > limit:
            raise MacroFeatureUnavailable(f"Macro series missing or stale: {key}")
        dates[key] = str(series.index[-1].date())
        if key not in {"DGS10", "DGS3MO"}:
            periods = series.index.to_period("M")
            if not periods.is_unique:
                raise ValueError(f"Ambiguous monthly macro periods: {key}")
            monthly[key] = pd.Series(series.to_numpy(), index=periods)
    required_dates = {}

    def required(key, offsets):
        series = monthly[key]
        periods = [series.index[-1] - offset for offset in offsets]
        if any(period not in series for period in periods):
            raise MacroFeatureUnavailable(f"Missing required calendar period: {key}")
        required_dates[key] = [str(period) for period in periods]
        return [float(series.loc[period]) for period in periods]

    ip, ip6 = required("INDPRO", [0, 6])
    cpi, cpi12, cpi3, cpi15 = required("CPIAUCSL", [0, 12, 3, 15])
    u = required("UNRATE", [0, 1, 2, 3, 4, 5])
    if min(ip, ip6, cpi, cpi12, cpi3, cpi15) <= 0:
        raise ValueError("Nonpositive required macro index")
    yields = pd.concat([views["DGS10"], views["DGS3MO"]], axis=1, join="inner").dropna()
    if yields.empty or (date.date() - yields.index[-1].date()).days > 14:
        raise MacroFeatureUnavailable("Missing or stale aligned Treasury yields")
    required_dates["yield_curve"] = str(yields.index[-1].date())
    inflation = 100 * (cpi / cpi12 - 1)
    return {
        "ip_growth": 100 * ((ip / ip6) ** 2 - 1),
        "unemployment_change": float(np.mean(u[:3]) - np.mean(u[3:])),
        "inflation_yoy": inflation,
        "inflation_change": inflation - 100 * (cpi3 / cpi15 - 1),
        "yield_curve": float(yields.iloc[-1, 0] - yields.iloc[-1, 1]),
        "observation_dates": dates,
        "required_observation_periods": required_dates,
        "feature_contract": CONTRACT_VERSION,
    }
