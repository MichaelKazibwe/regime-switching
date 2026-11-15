import io
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from paper_dashboard import dashboard_state, load_reports, render_dashboard
from paper_dashboard_server import MarketCache, MarketProvider, make_handler


def test_quotes_use_last_bar_and_previous_session_close_without_inventing_missing_assets():
    index = pd.to_datetime(["2026-10-28T19:55:00Z", "2026-10-29T13:30:00Z", "2026-10-29T19:55:00Z"])
    columns = pd.MultiIndex.from_tuples([("Close", "SPY"), ("Close", "QQQ")])
    frame = pd.DataFrame([[100,200],[101,201],[103,202]], index=index, columns=columns)
    calls = []

    def download(*args, **kwargs):
        calls.append(kwargs)
        return frame

    result = MarketProvider(download=download).quotes()
    spy = next(item for item in result["quotes"] if item["symbol"] == "SPY")
    missing = next(item for item in result["quotes"] if item["symbol"] == "TLT")
    assert spy["price"] == 103
    assert spy["change_pct"] == pytest.approx(.03)
    assert spy["as_of"] == "2026-10-29T19:55:00+00:00"
    assert missing["price"] is None
    assert result["partial"] is True
    assert calls[0]["auto_adjust"] is False
    assert calls[0]["interval"] == "5m"


def test_price_cache_throttles_requests_labels_stale_success_and_recovers():
    clock = [0]

    class Provider:
        calls = 0
        fail = False

        def quotes(self):
            self.calls += 1
            if self.fail:
                raise RuntimeError("sensitive upstream error not for clients")
            return {"quotes": [{"symbol": "SPY", "price": 100}]}

    provider = Provider()
    cache = MarketCache(provider, clock=lambda: clock[0])
    assert cache.get()["stale"] is False
    assert cache.get()["cached"] is True
    assert provider.calls == 1
    clock[0] = 61
    provider.fail = True
    failed = cache.get()
    assert failed["available"] is True
    assert failed["stale"] is True
    assert failed["quotes"][0]["price"] == 100
    assert "sensitive" not in failed["error"]
    cache.get()
    assert provider.calls == 2
    clock[0] = 92
    provider.fail = False
    assert cache.get()["stale"] is False


def test_provider_failure_without_saved_prices_never_supplies_mock_quotes():
    class FailingProvider:
        def quotes(self):
            raise RuntimeError("offline")

    result = MarketCache(FailingProvider()).get()
    assert result["available"] is False
    assert result.get("quotes") is None


def test_dashboard_loader_skips_corrupt_and_invalid_reports_and_handles_null_execution(tmp_path):
    (tmp_path / "bad.json").write_text("{")
    (tmp_path / "invalid.json").write_text('{"decision": []}')
    (tmp_path / "valid.json").write_text('{"cycle_id":"null-execution","decision":{"paper_execution":null}}')
    reports = load_reports(tmp_path, 10)
    assert len(reports) == 1
    assert "null-execution" in render_dashboard(reports)


def test_dashboard_script_payload_is_safe_and_template_tokens_are_not_reinterpreted():
    value = '</script><img src=x onerror=alert(1)>__DASHBOARD_STYLE__'
    document = render_dashboard([{"cycle_id": value, "decision": {}}])
    assert '</script><img' not in document
    assert "\\u003c/script\\u003e" in document
    assert "__DASHBOARD_STYLE__" in document
    assert "&lt;/script&gt;&lt;img" in document


def test_dashboard_state_only_exposes_fields_used_by_the_interface():
    state = dashboard_state([{"cycle_id": "cycle", "configuration": {"private": "secret"},
                             "notification": {"error": "private-message"}, "decision": {}}])
    assert "secret" not in json.dumps(state)
    assert "private-message" not in json.dumps(state)


def dispatch(tmp_path, path, host="127.0.0.1:8766", origin=None):
    handler_class = make_handler(tmp_path, MarketCache())
    handler = object.__new__(handler_class)
    handler.path = path
    handler.headers = {"Host": host, **({"Origin": origin} if origin else {})}
    handler.server = SimpleNamespace(server_port=8766)
    handler.wfile = io.BytesIO()
    status = []
    headers = {}
    handler.send_response = status.append
    handler.send_header = headers.__setitem__
    handler.end_headers = lambda: None
    handler.do_GET()
    return status[0], headers, handler.wfile.getvalue()


def test_dashboard_api_rejects_foreign_origin_bad_symbols_and_file_paths(tmp_path):
    assert dispatch(tmp_path, "/api/state", host="evil.example:8766")[0] == 403
    assert dispatch(tmp_path, "/api/state", origin="https://evil.example")[0] == 403
    assert dispatch(tmp_path, "/api/history?symbol=NOT_A_PORTFOLIO_ASSET")[0] == 400
    assert dispatch(tmp_path, "/api/history?range=INVALID")[0] == 400
    assert dispatch(tmp_path, "/.env.paper")[0] == 404
    status, headers, body = dispatch(tmp_path, "/api/state")
    assert status == 200
    assert json.loads(body)["reports"] == []
    assert "sha256-" in headers["Content-Security-Policy"]
    assert headers["X-Frame-Options"] == "DENY"
