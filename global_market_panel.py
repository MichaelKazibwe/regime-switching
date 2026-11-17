"""Calendar-aware base-currency valuation from timestamped actual observations.

Closed-market marks may remain unchanged; a missing expected local close or FX
quote never becomes a manufactured native observation. FX is units of base per
native currency. Values must be available by each portfolio valuation timestamp.
"""

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
from pathlib import Path
import hashlib
import json
import shutil


def _observations(frame, value):
    if not {"session", "available_at", value} <= set(frame):
        raise ValueError("Timestamped actual observations required")
    result = frame.copy()
    result["session"] = pd.to_datetime(result["session"]).dt.normalize()
    result["available_at"] = pd.to_datetime(result["available_at"], utc=True)
    if (result["session"].duplicated().any() or not result["session"].is_monotonic_increasing
            or not result["available_at"].is_monotonic_increasing
            or not np.isfinite(result[value]).all() or (result[value] <= 0).any()):
        raise ValueError("Unique ordered positive observed values required")
    return result


def base_currency_panel(registry, observations, valuations, *, base_currency="USD", fx=None, max_fx_age_hours=96):
    valuations = pd.DatetimeIndex(valuations)
    if valuations.tz is None or valuations.has_duplicates or not valuations.is_monotonic_increasing:
        raise ValueError("Unique ordered aware valuation timestamps required")
    if valuations.empty or not 0 < max_fx_age_hours <= 96:
        raise ValueError("Bounded FX freshness and valuation history required")
    fx = fx or {}
    prices, provenance = {}, {}
    for symbol, raw in observations.items():
        item = registry.instruments[symbol]
        if item.pricing_model not in {"adjusted_close", "total_return", "net_asset_value"}:
            raise ValueError("Instrument requires a qualified contract-return adapter")
        bars = _observations(raw, "close")
        schedule = mcal.get_calendar(item.calendar).schedule(
            (valuations[0] - pd.Timedelta(days=14)).date(), valuations[-1].date())
        rates = _observations(fx[item.listing_currency], "rate") if item.listing_currency != base_currency and item.listing_currency in fx else None
        if item.listing_currency != base_currency and rates is None:
            raise ValueError(f"Qualified timestamped {item.listing_currency}/{base_currency} FX required")
        values, evidence = [], []
        for stamp in valuations:
            completed = schedule.loc[schedule.market_close <= stamp]
            if completed.empty:
                raise ValueError("No completed local session before valuation")
            expected = completed.index[-1].normalize()
            known = bars.loc[(bars.session == expected) & (bars.available_at <= stamp)]
            if len(known) != 1:
                raise ValueError(f"Missing actual completed local observation: {symbol} {expected.date()}")
            bar = known.iloc[0]
            # Reject a provider timestamp that pretends a local close was known early.
            if bar.available_at < completed.market_close.iloc[-1]:
                raise ValueError("Observation availability precedes its local close")
            rate, fx_stamp = 1., None
            if rates is not None:
                known_fx = rates.loc[rates.available_at <= stamp]
                if known_fx.empty or stamp - known_fx.available_at.iloc[-1] > pd.Timedelta(hours=max_fx_age_hours):
                    raise ValueError("Missing or stale FX; no FX fill permitted")
                rate, fx_stamp = float(known_fx.rate.iloc[-1]), known_fx.available_at.iloc[-1].isoformat()
            values.append(float(bar.close) * item.price_multiplier * rate)
            evidence.append(dict(local_session=str(expected.date()), available_at=bar.available_at.isoformat(),
                fx_available_at=fx_stamp, unchanged_closed_market_mark=bool(stamp.date() != expected.date())))
        prices[symbol], provenance[symbol] = values, evidence
    panel = pd.DataFrame(prices, index=valuations)
    if panel.empty or not np.isfinite(panel.to_numpy()).all():
        raise ValueError("Complete qualified global valuation marks required")
    panel.attrs.update(base_currency=base_currency, registry_id=registry.identity,
                       valuation_kind="ACTUAL_AS_OF_MARKS_WITH_EXPLICIT_CLOSED_MARKET_CARRY",
                       observations=provenance)
    return panel


def capture_manifest(path, destination, registry):
    """Import qualified timestamped providers; archive raw quotes/FX with hashes."""
    path, destination = Path(path).resolve(), Path(destination)
    document = json.loads(path.read_text())
    if document.get("schema_version") != 1 or document.get("base_currency") != "USD" or document.get("registry_id") != registry.identity:
        raise ValueError("Source-bound USD global valuation manifest required")
    files = []
    def read(record, name):
        source = Path(record["path"])
        source = source if source.is_absolute() else path.parent / source
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Global provider artifact hash mismatch")
        target = destination / name
        shutil.copyfile(source, target)
        target.chmod(0o600)
        files.append(target)
        return pd.read_csv(target)
    timestamps = read(document["valuations"], "global-valuations.csv")["timestamp"]
    quotes = {s: read(record, "global-quote-" + hashlib.sha256(s.encode()).hexdigest()[:16] + ".csv")
              for s, record in document["quotes"].items()}
    rates = {c: read(record, "global-fx-" + hashlib.sha256(c.encode()).hexdigest()[:16] + ".csv")
             for c, record in document.get("fx", {}).items()}
    if not set(registry.symbols()) <= set(quotes):
        raise ValueError("All enabled research instruments require qualified global quotes")
    panel = base_currency_panel(registry, quotes, pd.DatetimeIndex(timestamps), fx=rates)
    provenance = destination / "global-valuation-provenance.json"
    provenance.write_text(json.dumps(panel.attrs, sort_keys=True, allow_nan=False))
    provenance.chmod(0o600)
    files.append(provenance)
    panel.index = panel.index.tz_convert("America/New_York").tz_localize(None).normalize()
    return panel, files
