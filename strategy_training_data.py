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


def validate_prices(prices, session, *, required_symbols=None):
    import pandas_market_calendars as mcal

    if (
        not isinstance(prices.index, pd.DatetimeIndex)
        or prices.index.tz is not None
        or not prices.index.is_unique
        or not prices.index.is_monotonic_increasing
    ):
        raise ValueError("Ordered unique naive market sessions required")
    prices = prices.loc[prices.index <= pd.Timestamp(session)].copy()
    symbols = list(DIVERSIFIED_ASSETS if required_symbols is None else required_symbols)
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("Explicit unique capture symbols required")
    missing = set(symbols) - set(prices)
    if missing:
        raise ValueError("Missing core instruments: " + ",".join(sorted(missing)))
    values = prices[symbols].to_numpy(dtype=float)
    if np.isinf(values).any() or np.any(values[np.isfinite(values)] <= 0):
        raise ValueError("Invalid adjusted prices")
    if prices.empty or prices.index[-1] != pd.Timestamp(session):
        raise ValueError("Latest usable completed session missing")
    expected = mcal.get_calendar("NYSE").schedule(prices.index[0], session).index
    if not prices.index.equals(expected):
        raise ValueError("Missing or extra exchange sessions; no filling permitted")
    if prices[symbols].iloc[-1].isna().any():
        raise ValueError("Stale or missing latest core-instrument observation")
    if len(prices) < 1260:
        raise ValueError("At least five years of observed market sessions required")
    return prices


def capture(output, base_macro_manifest, *, clock=None, global_panel_manifest=None):
    import yfinance as yf
    from fetch_strategy_macro import SERIES, fetch_series

    now = clock() if clock else datetime.now(timezone.utc)
    session = usable_session(now)
    root = Path(output) / now.strftime("%Y%m%dT%H%M%S%fZ")
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    yf.set_tz_cache_location(str(root / "provider-cache"))
    from investmentcatalog import catalogue
    cat = catalogue()
    if global_panel_manifest is None and any(cat[s].listing_currency != "USD" for s in DIVERSIFIED_ASSETS):
        raise ValueError("Native-currency capture requires qualified global_market_panel prices and FX provenance")
    symbols = list(dict.fromkeys([*DIVERSIFIED_ASSETS, *[s for s, i in cat.items() if i.listing_currency == "USD"]]))
    extra_files = []
    if global_panel_manifest is not None:
        from global_market_panel import capture_manifest
        from global_asset_registry import load_registry
        prices, extra_files = capture_manifest(global_panel_manifest, root, load_registry())
        raw = None
    else:
        raw = yf.download(
            symbols,
            start="2010-01-01",
            end=str((session + pd.Timedelta(days=1)).date()),
            auto_adjust=True,
            threads=False,
            progress=False,
            timeout=20,
        )
    if raw is not None and raw.empty:
        raise RuntimeError("Market provider returned no data; capture is incomplete")
    if raw is not None:
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
        *extra_files,
    ]
    ready = {
        "status": "CAPTURED_FOR_SHADOW_TRAINING",
        "captured_at": now.isoformat(),
        "price_session": str(session.date()),
        "publication_buffer_minutes": 15,
        "base_currency": "USD",
        "universe_contract": __import__("global_asset_registry").load_registry().payload(),
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
    parser.add_argument("--global-panel-manifest", type=Path,
                        help="Qualified timestamped global quotes/FX and valuation manifest")
    args = parser.parse_args()
    capture(args.output, args.base_macro_manifest, global_panel_manifest=args.global_panel_manifest)


if __name__ == "__main__":
    main()
