"""Local, read-only dashboard API with cached Yahoo Finance provider prices.

Run: python -m paper_dashboard_server --port 8766
Only loopback clients are supported. This process never runs portfolio decisions
or submits orders. Yahoo bars are indicative and may be delayed.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import yfinance as yf

from assetuniverse import PRODUCTION_ASSETS
from paper_dashboard import dashboard_state, load_reports, render_dashboard, script_source
from tradingcalendar import TradingCalendar


RANGES = {"1D": ("1d", "5m"), "5D": ("5d", "15m"), "1M": ("1mo", "1d"),
          "3M": ("3mo", "1d"), "1Y": ("1y", "1d")}


def _close_frame(frame: pd.DataFrame, symbols: tuple[str, ...]) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError("No market observations returned")
    close = frame["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(symbols[0])
    close = close.copy()
    index = pd.DatetimeIndex(close.index)
    close.index = index.tz_localize("America/New_York") if index.tz is None else index
    return close.sort_index()


class MarketProvider:
    def __init__(self, download=None):
        self.download = download or yf.download

    def _load(self, symbols, period, interval):
        return _close_frame(self.download(
            list(symbols), period=period, interval=interval, auto_adjust=False,
            progress=False, threads=4, timeout=12, prepost=False, ignore_tz=False,
        ), tuple(symbols))

    def quotes(self) -> dict:
        frame = self._load(PRODUCTION_ASSETS, "5d", "5m")
        quotes = []
        for symbol in PRODUCTION_ASSETS:
            values = frame[symbol].dropna() if symbol in frame else pd.Series(dtype=float)
            values = values[(values > 0) & values.map(math.isfinite)]
            if values.empty:
                quotes.append({"symbol": symbol, "price": None, "as_of": None, "change_pct": None})
                continue
            last = values.index[-1]
            session_date = last.tz_convert("America/New_York").date()
            previous = values[[stamp.tz_convert("America/New_York").date() < session_date for stamp in values.index]]
            reference = float(previous.iloc[-1]) if not previous.empty else None
            price = float(values.iloc[-1])
            quotes.append({"symbol": symbol, "price": price,
                           "as_of": last.tz_convert("UTC").isoformat(),
                           "change_pct": price / reference - 1 if reference else None})
        if not any(item["price"] is not None for item in quotes):
            raise ValueError("No usable quotes")
        return {"quotes": quotes, "source": "Yahoo Finance", "interval": "5-minute bars",
                "partial": any(item["price"] is None for item in quotes)}

    def history(self, symbol: str, window: str) -> dict:
        period, interval = RANGES[window]
        values = self._load((symbol,), period, interval)[symbol].dropna()
        values = values[(values > 0) & values.map(math.isfinite)]
        if values.empty:
            raise ValueError("No usable history")
        return {"symbol": symbol, "range": window, "interval": interval, "source": "Yahoo Finance",
                "points": [{"time": stamp.tz_convert("UTC").isoformat(), "value": float(value)}
                           for stamp, value in values.items()]}


class MarketCache:
    """Serialize downloads, cache successes and back off failures without fake quotes."""

    def __init__(self, provider=None, *, clock=time.monotonic):
        self.provider = provider or MarketProvider()
        self.clock = clock
        self.lock = threading.Lock()
        self.entries = {}

    def get(self, symbol=None, window=None) -> dict:
        key = (symbol, window)
        with self.lock:
            current = self.clock()
            existing = self.entries.get(key)
            if existing and current < existing["expires"]:
                return {**existing["payload"], "cached": True}
            try:
                payload = self.provider.quotes() if symbol is None else self.provider.history(symbol, window)
                payload = {**payload, "available": True, "stale": False,
                           "fetched_at": datetime.now(timezone.utc).isoformat()}
                ttl = 60 if symbol is None else 300
            except Exception:
                payload = {**(existing["payload"] if existing else {}), "available": bool(existing and existing["payload"].get("available")),
                           "stale": True, "error": "Market provider unavailable. Retrying automatically; saved portfolio records are unaffected."}
                ttl = 30
            self.entries[key] = {"expires": self.clock() + ttl, "payload": payload}
            return {**payload, "cached": False}


def make_handler(reports_directory: Path, market: MarketCache):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return  # Local operational reports and query values are not written to shared logs.

        def _send(self, payload, status=200, content_type="application/json; charset=utf-8"):
            body = json.dumps(payload, allow_nan=False).encode() if not isinstance(payload, bytes) else payload
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            script_hash = base64.b64encode(hashlib.sha256(script_source().encode()).digest()).decode()
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'sha256-" + script_hash + "'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            port = self.server.server_port
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if host not in {f"127.0.0.1:{port}", f"localhost:{port}"} or (origin and origin != f"http://{host}"):
                self._send({"error": "Loopback same-origin access required"}, 403)
                return
            url = urlsplit(self.path)
            try:
                if url.path == "/":
                    self._send(render_dashboard(load_reports(reports_directory, 365)).encode(), content_type="text/html; charset=utf-8")
                elif url.path == "/api/state":
                    state = dashboard_state(load_reports(reports_directory, 365))
                    calendar = TradingCalendar()
                    state["market_open"] = calendar.is_market_open()
                    self._send(state)
                elif url.path == "/api/quotes":
                    self._send(market.get())
                elif url.path == "/api/history":
                    query = parse_qs(url.query)
                    symbol = query.get("symbol", ["SPY"])[0]
                    window = query.get("range", ["3M"])[0]
                    if symbol not in PRODUCTION_ASSETS or window not in RANGES:
                        self._send({"error": "Unsupported asset or chart range"}, 400)
                    else:
                        self._send(market.get(symbol, window))
                elif url.path == "/favicon.ico":
                    self._send(b"", 204)
                else:
                    self._send({"error": "Not found"}, 404)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self._send({"error": "Dashboard data unavailable. Inspect the local reports and retry."}, 503)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--reports", type=Path, default=Path("var/paper-reports"))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.reports, MarketCache()))
    server.daemon_threads = True
    print(f"Paper dashboard: http://127.0.0.1:{args.port} (read-only, indicative provider prices)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
