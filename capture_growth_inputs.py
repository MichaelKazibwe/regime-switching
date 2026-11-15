"""Capture additional benchmark health-care history and public RSS headlines."""

from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import yfinance as yf

from market_news import fetch_news
from strategy_integrity import file_hash
from strategy_receipts import atomic_json
from strategy_training_data import usable_session


def capture_growth_inputs():
    root = Path("var/growth-resilience-data") / datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    root.mkdir(parents=True, mode=0o700)
    session = usable_session(datetime.now(timezone.utc))
    yf.set_tz_cache_location(str(root / "provider-cache"))
    raw = yf.download(
        "XLV",
        start="2010-01-01",
        end=str((session + pd.Timedelta(days=1)).date()),
        auto_adjust=True,
        progress=False,
        threads=False,
        timeout=20,
    )
    if raw.empty:
        raise ValueError("No XLV market history received")
    close = raw["Close"]
    close.columns = ["XLV"] if isinstance(close, pd.DataFrame) else close.name
    close = close.loc[:session]
    if (
        close.index[-1].date() != session.date()
        or close.isna().any().any()
        or (close <= 0).any().any()
    ):
        raise ValueError("Incomplete healthcare price history")
    close.to_csv(root / "XLV-adjusted.csv")
    news = fetch_news()
    atomic_json(root / "news.json", news)
    atomic_json(
        root / "capture.json",
        {
            "market_session": str(session.date()),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "price_source": "Yahoo Finance adjusted daily close",
            "prices_sha256": file_hash(root / "XLV-adjusted.csv"),
            "news_sha256": file_hash(root / "news.json"),
        },
    )
    atomic_json("var/growth-resilience-data/latest.json", {"root": str(root)})
    print("Healthcare observations:", len(close), "through", session.date())
    print(
        "News:",
        news["status"],
        "headlines",
        len(news["headlines"]),
        "sources",
        [(s["source"], s["status"]) for s in news["sources"]],
    )

    return root


if __name__ == "__main__":
    capture_growth_inputs()
