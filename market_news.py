"""Bounded public RSS headline reader; no article bodies or trading signals."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import re
import threading
import time
from urllib.parse import urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener
import xml.etree.ElementTree as ET

SOURCES = {
    "Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
    "European Central Bank": "https://www.ecb.europa.eu/rss/press.html",
    "Yahoo Finance": "https://finance.yahoo.com/rss/topstories",
}
HOSTS = {urlparse(u).hostname for u in SOURCES.values()}


def safe_link(url):
    p = urlparse(url)
    return (
        p.scheme == "https"
        and bool(p.hostname)
        and p.username is None
        and p.password is None
        and not p.hostname.lower().startswith(
            ("localhost", "127.", "10.", "192.168.", "169.254.")
        )
    )


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_link(newurl) or urlparse(newurl).hostname not in HOSTS:
            raise ValueError("Feed redirect outside provider allowlist")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def parse_feed(raw, source, *, now=None):
    now = now or datetime.now(timezone.utc)
    if (
        len(raw) > 1_000_000
        or b"<!DOCTYPE" in raw.upper()
        or b"<!ENTITY" in raw.upper()
    ):
        raise ValueError("Unsafe or oversized feed")
    root = ET.fromstring(raw)
    items = []
    for item in root.findall(".//item")[:80]:
        title = " ".join(re.sub("<[^>]+>", "", item.findtext("title", "")).split())[
            :300
        ]
        link = item.findtext("link", "").strip()
        try:
            published = parsedate_to_datetime(item.findtext("pubDate", ""))
            if published.tzinfo is None:
                continue
        except (ValueError, TypeError):
            continue
        if not title or not safe_link(link) or published > now + timedelta(minutes=5):
            continue
        items.append(
            {
                "title": title,
                "url": link,
                "source": source,
                "published_at": published.astimezone(timezone.utc).isoformat(),
                "aged": (now - published) > timedelta(days=14),
                "topic": topic(title),
            }
        )
    return items


def topic(title):
    text = title.lower()
    for name, words in [
        ("Policy & rates", ["rate", "inflation", "fed", "ecb", "monetary", "bank"]),
        (
            "Industry & technology",
            ["chip", "ai ", "technology", "manufactur", "energy", "health", "industry"],
        ),
        (
            "Global markets",
            ["china", "japan", "europe", "tariff", "trade", "emerging", "market"],
        ),
    ]:
        if any(w in text for w in words):
            return name
    return "Economy & business"


def fetch_source(item):
    source, url = item
    try:
        request = Request(
            url,
            headers={
                "User-Agent": "RegimeInvestorDashboard/1.0 (public RSS headline reader)",
                "Accept": "application/rss+xml, application/xml, text/xml",
            },
        )
        with build_opener(Redirects()).open(request, timeout=8) as response:
            if urlparse(response.url).hostname not in HOSTS:
                raise ValueError("Unexpected feed host")
            raw = response.read(1_000_001)
        rows = parse_feed(raw, source)
        return rows, {
            "source": source,
            "status": "FETCHED" if rows else "NO_VALID_DATED_HEADLINES",
            "url": url,
        }
    except Exception as exc:
        return [], {
            "source": source,
            "status": "UNAVAILABLE",
            "error_type": type(exc).__name__,
            "url": url,
        }


def fetch_news():
    now = datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(fetch_source, SOURCES.items()))
    unique = {row["url"]: row for rows, _ in results for row in rows}
    rows = sorted(unique.values(), key=lambda r: r["published_at"], reverse=True)[:45]
    return {
        "status": "LIVE_HEADLINES"
        if any(not r["aged"] for r in rows)
        else "AGED_HEADLINES"
        if rows
        else "UNAVAILABLE",
        "fetched_at": now,
        "headlines": rows,
        "sources": [meta for _, meta in results],
        "refresh_seconds": 300,
        "use": "Information only; no sentiment score, forecast alpha or automatic trades.",
    }


class NewsCache:
    def __init__(self, initial=None):
        self.lock = threading.Lock()
        self.value = initial
        self.updated = 0.0

    def get(self):
        with self.lock:
            if self.value is None or time.monotonic() - self.updated >= 300:
                fresh = fetch_news()
                if not fresh["headlines"] and self.value and self.value["headlines"]:
                    fresh["headlines"] = self.value["headlines"]
                    fresh["status"] = "CACHED_AFTER_REFRESH_FAILURE"
                    fresh["original_fetched_at"] = self.value["fetched_at"]
                self.value = fresh
                self.updated = time.monotonic()
            return self.value
