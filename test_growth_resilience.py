"""Current policy, funded benchmark accounting and untrusted-feed boundaries."""

from datetime import datetime, timezone
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest
from goalportfolio import AccountDrawdownGuard
from growth_resilience import WEIGHTS, backtest, metrics, simulate
from market_news import parse_feed, NewsCache
from portfolio_objectives import drawdown_factor


def test_current_guard_measures_large_drawdown_without_cash_lock():
    g = AccountDrawdownGuard()
    assert g.update(1.2) == (0.0, 1.0)
    dd, factor = g.update(0.6)
    assert dd == pytest.approx(-0.5) and factor == 1.0 and not g.locked
    assert drawdown_factor(-0.8) == 1.0
    legacy = AccountDrawdownGuard(0.02, 0.04)
    assert legacy.update(0.95)[1] == 0 and legacy.locked


def test_benchmark_fully_funded_and_costs_have_no_return_floor():
    assert sum(WEIGHTS.values()) == pytest.approx(1)
    assert max(WEIGHTS.values()) <= 0.25
    daily = pd.DataFrame({"SPY": [-0.1] * 42})
    curve, r, turn = backtest(daily, {"SPY": 1.0}, cost=0)
    assert (
        curve[0] == 1
    )  # cash until first closing trade, no first-day return lookahead
    assert curve[-1] == pytest.approx(0.9**41)
    costly, _, _ = backtest(daily, {"SPY": 1.0}, cost=0.0015)
    assert costly[-1] < curve[-1]
    assert metrics(curve, r, turn)["maximum_drawdown"] < -0.9


def test_joint_scenarios_keep_losses_and_reproduce_seed():
    daily = pd.DataFrame({"SPY": [-0.002] * 70, "IEF": [0.001] * 70})
    kwargs = dict(paths=20, years=1, seed=1)
    a = simulate(daily, {"SPY": 1.0}, **kwargs)
    assert a == simulate(daily, {"SPY": 1.0}, **kwargs)
    assert a["terminal_loss_frequency"] == 1
    assert a["p95_drawdown_magnitude"] > 0.3
    assert np.isfinite(a["terminal_return_quantiles"]["median"])


def test_feed_rejects_unsafe_and_future_items():
    now = datetime(2026, 10, 31, tzinfo=timezone.utc)
    xml = b"""<rss><channel><item><title>Rate update</title><link>https://www.federalreserve.gov/one</link><pubDate>Fri, 30 Oct 2026 12:00:00 GMT</pubDate></item><item><title>Future</title><link>https://example.com</link><pubDate>Sun, 01 Nov 2026 12:00:00 GMT</pubDate></item><item><title>Unsafe</title><link>javascript:alert(1)</link><pubDate>Fri, 30 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>"""
    rows = parse_feed(xml, "Federal Reserve", now=now)
    assert len(rows) == 1 and rows[0]["title"] == "Rate update"
    with pytest.raises(ValueError):
        parse_feed(b'<!DOCTYPE rss [<!ENTITY a "bad">]><rss/>', "x", now=now)


def test_news_refresh_failure_preserves_dated_snapshot_and_ttl():
    old = {
        "headlines": [{"title": "Original"}],
        "fetched_at": "2026-10-30T00:00:00+00:00",
        "sources": [],
    }
    cache = NewsCache(old)
    with patch(
        "market_news.fetch_news",
        return_value={
            "headlines": [],
            "sources": [],
            "status": "UNAVAILABLE",
            "fetched_at": "2026-10-31T00:00:00+00:00",
        },
    ) as fetch:
        result = cache.get()
        assert result["status"] == "CACHED_AFTER_REFRESH_FAILURE"
        assert result["original_fetched_at"] == old["fetched_at"]
        assert cache.get() == result and fetch.call_count == 1


def test_news_endpoint_requires_authentication_and_uses_cache():
    from io import BytesIO
    from types import SimpleNamespace
    from strategy_dashboard_server import handler

    app = SimpleNamespace(
        news=SimpleNamespace(get=lambda: {"status": "LIVE_HEADLINES", "headlines": []})
    )
    cls = handler(app, "a" * 64)
    h = object.__new__(cls)
    h.server = SimpleNamespace(server_port=8768)
    h.send_response = lambda code: setattr(h, "code", code)
    h.send_header = lambda *args: None
    h.end_headers = lambda: None
    h.wfile = BytesIO()
    h.headers = {"Host": "127.0.0.1:8768"}
    h.path = "/api/news"
    h.do_GET()
    assert h.code == 401
    h.headers["Authorization"] = "Bearer " + "a" * 64
    h.wfile = BytesIO()
    h.do_GET()
    assert h.code == 200 and b"LIVE_HEADLINES" in h.wfile.getvalue()
    h.headers["Origin"] = "https://untrusted.invalid"
    h.do_GET()
    assert h.code == 403


def test_training_selection_has_no_legacy_drawdown_ceiling():
    from institutionalportfolio import InstitutionalPortfolio
    from refine_institutional_portfolio import select

    policy = InstitutionalPortfolio()
    dates = pd.bdate_range("2010-01-01", periods=1010)
    frame = pd.DataFrame(
        {
            "return": -0.001,
            "cash": 0.1,
            "turnover": 0.0,
            "cost_as_initial_capital": 0.0,
        },
        index=dates,
    )
    frame["equity"] = (1 + frame["return"]).cumprod()
    selections, trials = select({0: frame}, [policy.config["proxy_parameters"]], policy)
    assert trials[0]["max_drawdown"] < -0.05 and trials[0]["eligible"]
    assert not selections[0].get("fallback", False)
