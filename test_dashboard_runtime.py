from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

from dashboard_runtime import runtime
from strategy_dashboard_server import handler


def test_absent_observations_are_unavailable_not_zero_performance(tmp_path):
    report = runtime(tmp_path, now=datetime(2026, 11, 2, 14, tzinfo=timezone.utc))
    assert report["scheduler"]["heartbeat_recent"] is False
    assert report["prospective"]["status"] == "UNAVAILABLE"
    assert "metrics" not in report["prospective"]
    assert not report["execution_enabled"]


def test_runtime_endpoint_auth_and_same_origin(monkeypatch):
    import dashboard_runtime

    calls = []
    monkeypatch.setattr(
        dashboard_runtime, "runtime", lambda: calls.append(True) or {"status": "safe"}
    )
    h = object.__new__(handler(SimpleNamespace(), "a" * 64))
    h.server = SimpleNamespace(server_port=8769)
    h.path = "/api/observations"
    h.headers = {"Host": "127.0.0.1:8769"}
    h.wfile = BytesIO()
    h.send_response = lambda code: setattr(h, "code", code)
    h.send_header = lambda *args: None
    h.end_headers = lambda: None
    h.do_GET()
    assert h.code == 401 and not calls
    h.headers["Authorization"] = "Bearer " + "a" * 64
    h.do_GET()
    assert h.code == 200 and calls == [True]
    h.headers["Origin"] = "https://untrusted.invalid"
    h.do_GET()
    assert h.code == 403 and calls == [True]
