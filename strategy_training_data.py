"""Immutable fresh adjusted-market and ALFRED-vintage capture for shadow training."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from assetuniverse import DIVERSIFIED_ASSETS
from macrovintage import MacroVintageData
from productreport import private_write
from tradingcalendar import TradingCalendar


def usable_session(now, publication_minutes=15):
    if now.tzinfo is None:
        raise ValueError("Aware capture clock required")
    close = TradingCalendar().latest_completed_session(
        now - timedelta(minutes=publication_minutes)
    )
    if close is None:
        raise ValueError("No completed session")
    return close.tz_convert("America/New_York").tz_localize(None).normalize()


def validate_prices(prices, session):
    import pandas_market_calendars as mcal

    if (
        not isinstance(prices.index, pd.DatetimeIndex)
        or prices.index.tz is not None
        or not prices.index.is_unique
        or not prices.index.is_monotonic_increasing
    ):
        raise ValueError("Ordered unique naive market sessions required")
    prices = prices.loc[prices.index <= pd.Timestamp(session)].copy()
    missing = set(DIVERSIFIED_ASSETS) - set(prices)
    if missing:
        raise ValueError("Missing core instruments: " + ",".join(sorted(missing)))
    values = prices[list(DIVERSIFIED_ASSETS)].to_numpy(dtype=float)
    if np.isinf(values).any() or np.any(values[np.isfinite(values)] <= 0):
        raise ValueError("Invalid adjusted prices")
    if prices.empty or prices.index[-1] != pd.Timestamp(session):
        raise ValueError("Latest usable completed session missing")
    expected = mcal.get_calendar("NYSE").schedule(prices.index[0], session).index
    if not prices.index.equals(expected):
        raise ValueError("Missing or extra exchange sessions; no filling permitted")
    if prices[list(DIVERSIFIED_ASSETS)].iloc[-1].isna().any():
        raise ValueError("Stale or missing latest core-instrument observation")
    if len(prices) < 1260:
        raise ValueError("At least five years of observed market sessions required")
    return prices


def capture(output, base_macro_manifest, *, clock=None):
    import yfinance as yf
    from fetch_strategy_macro import SERIES, fetch_series

    now = clock() if clock else datetime.now(timezone.utc)
    session = usable_session(now)
    root = Path(output) / now.strftime("%Y%m%dT%H%M%S%fZ")
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    yf.set_tz_cache_location(str(root / "provider-cache"))
    symbols = [*DIVERSIFIED_ASSETS, "DBMF", "ALLW"]
    raw = yf.download(
        symbols,
        start="2010-01-01",
        end=str((session + pd.Timedelta(days=1)).date()),
        auto_adjust=True,
        threads=False,
        progress=False,
        timeout=20,
    )
    if raw.empty:
        raise RuntimeError("Market provider returned no data; capture is incomplete")
    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    prices.index = pd.DatetimeIndex(prices.index).tz_localize(None)
    prices = validate_prices(prices, session)
    private_write(root / "prices.csv", prices.to_csv())
    print(
        f"Market snapshot: {len(prices)} sessions through {session.date()}; {len(prices.columns)} instruments.",
        flush=True,
    )
    base = json.loads(Path(base_macro_manifest).read_text())
    manifest = {
        "status": "ACTUAL_FRED_RELEASES",
        "retrieved_at": now.isoformat(),
        "cutoff": str(session.date()),
        "series": {},
    }
    for key in SERIES:
        item = base["series"][key]
        old = MacroVintageData.from_csv(
            Path(item["path"]), expected_sha256=item["sha256"]
        ).releases[["date", "realtime_start", "value"]]
        if session > pd.Timestamp(base["cutoff"]):
            new = fetch_series(
                key, str(session.date()), realtime_start=base["cutoff"]
            ).releases[["date", "realtime_start", "value"]]
            merged = pd.concat([old, new], ignore_index=True)
            duplicate = merged[
                merged.duplicated(["date", "realtime_start"], keep=False)
            ]
            if (
                len(duplicate)
                and (
                    duplicate.groupby(["date", "realtime_start"]).value.nunique(
                        dropna=False
                    )
                    > 1
                ).any()
            ):
                raise ValueError(
                    "Conflicting archived vintage keys; source requires review"
                )
            merged = merged.drop_duplicates(["date", "realtime_start"])
        else:
            merged = old
        data = MacroVintageData(merged[merged.realtime_start <= session])
        target = root / f"{key}.csv"
        info = data.freeze(target)
        target.chmod(0o600)
        manifest["series"][key] = info
        print(f"{key}: {len(data.releases)} point-in-time vintage records.", flush=True)
    private_write(root / "macro-manifest.json", json.dumps(manifest, indent=2))
    files = [
        root / "prices.csv",
        root / "macro-manifest.json",
        *[root / f"{k}.csv" for k in SERIES],
    ]
    ready = {
        "status": "CAPTURED_FOR_SHADOW_TRAINING",
        "captured_at": now.isoformat(),
        "price_session": str(session.date()),
        "publication_buffer_minutes": 15,
        "prices": str(root / "prices.csv"),
        "macro_manifest": str(root / "macro-manifest.json"),
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "limitations": [
            "Adjusted vendor price histories may reflect subsequent corporate-action adjustments.",
            "Retrospectively selected universe; historical coverage is not pristine prospective evidence.",
            "No ongoing scheduler or order submission.",
        ],
    }
    private_write(root / "capture.json", json.dumps(ready, indent=2))
    print(
        json.dumps(
            {"capture": str(root / "capture.json"), "session": str(session.date())}
        ),
        flush=True,
    )
    return root / "capture.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("var/strategy-training-snapshots")
    )
    parser.add_argument(
        "--base-macro-manifest",
        type=Path,
        default=Path("var/research/smart-macro-vintages/manifest.json"),
    )
    args = parser.parse_args()
    capture(args.output, args.base_macro_manifest)


if __name__ == "__main__":
    main()
