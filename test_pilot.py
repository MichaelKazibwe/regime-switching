from collections import OrderedDict
from datetime import datetime, timezone
from http.client import HTTPConnection
import json
from types import SimpleNamespace
import threading

import pytest

from pilot_auth import AuthStore
from pilot_server import Pilot, BoundedServer, handler
from strategy_training_data import usable_session

PASSWORD = "Synthetic-test-password-123!"


def test_password_changes_rotate_sessions_and_revoke_old_password(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.add_user("tester@example.test", PASSWORD)
    token = store.login("tester@example.test", PASSWORD, "peer")
    session = store.session(token)
    assert session["must_change"]
    store.change_password(session, PASSWORD, PASSWORD + "-new")
    assert store.session(token) is None
    with pytest.raises(PermissionError):
        store.login("tester@example.test", PASSWORD, "peer")
    newer = store.login("tester@example.test", PASSWORD + "-new", "peer")
    assert not store.session(newer)["must_change"]
    store.revoke_user("tester@example.test")
    assert store.session(newer) is None


def test_session_idle_and_absolute_expiry(tmp_path):
    clock = [1000.0]
    store = AuthStore(tmp_path / "auth.sqlite3", clock=lambda: clock[0], idle_seconds=10, absolute_seconds=30)
    store.add_user("tester@example.test", PASSWORD, must_change=False)
    token = store.login("tester@example.test", PASSWORD, "peer")
    clock[0] += 11
    assert store.session(token) is None
    token = store.login("tester@example.test", PASSWORD, "peer")
    for _ in range(3):
        clock[0] += 9
        assert store.session(token)
    clock[0] += 4
    assert store.session(token) is None


def test_durable_login_limit_and_private_backup(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.add_user("tester@example.test", PASSWORD)
    for _ in range(10):
        with pytest.raises(PermissionError):
            store.login("tester@example.test", "incorrect-password-123", "peer")
    restarted = AuthStore(tmp_path / "auth.sqlite3")
    with pytest.raises(PermissionError):
        restarted.login("tester@example.test", PASSWORD, "peer")
    backup = tmp_path / "backup.sqlite3"
    restarted.backup(backup)
    assert AuthStore(backup).list_users()[0]["username"] == "tester@example.test"
    assert backup.stat().st_mode & 0o777 == 0o600
    assert PASSWORD.encode() not in backup.read_bytes()


def test_reset_requires_explicit_reactivation(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.add_user("tester@example.test", PASSWORD)
    store.revoke_user("tester@example.test")
    with pytest.raises(ValueError):
        store.reset_password("tester@example.test", PASSWORD + "-new")
    store.reset_password("tester@example.test", PASSWORD + "-new", reactivate=True)
    assert store.session(store.login("tester@example.test", PASSWORD + "-new", "peer"))["must_change"]


class FakeApplication:
    def __init__(self):
        self.payload = dict(training=dict(run_id="test-version", market_session=str(usable_session(datetime.now(timezone.utc)).date())),
                            plans=[{"id": "shared-research-example"}])
        self.lock = threading.Lock()
        self.results = OrderedDict(saved={"research": True})
        self.refresh_error = None
        self.news = SimpleNamespace(get=lambda: {"status": "UNAVAILABLE", "headlines": []})

    def refresh(self):
        pass

    def calculate(self, body):
        if set(body) != {"id"}:
            raise ValueError("Invalid synthetic fields")
        self.results[body["id"]] = body
        return {"result_id": body["id"], "execution_enabled": False}

    def pdf(self, result_id):
        if result_id not in self.results:
            raise ValueError("Not available in this user scope")
        return b"%PDF-synthetic-test"

    def portfolio_pdf(self, profile_id):
        if profile_id != "shared-research-example":
            raise ValueError("Invalid example")
        return b"%PDF-synthetic-example"


@pytest.fixture
def service(tmp_path):
    server = BoundedServer(("127.0.0.1", 0), handler(None))
    origin = f"http://127.0.0.1:{server.server_port}"
    pilot = Pilot(FakeApplication(), tmp_path, origin, insecure_local=True)
    server.RequestHandlerClass = handler(pilot)
    for name, role in [("alice@example.test", "tester"), ("bob@example.test", "tester"),
                       ("viewer@example.test", "viewer")]:
        pilot.auth.add_user(name, PASSWORD, role=role, must_change=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(path, body=None, *, cookie=None, csrf=None, origin_header=origin, host=None, raw=None):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        headers = {"Host": host or f"127.0.0.1:{server.server_port}"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        if body is not None or raw is not None:
            headers.update({"Content-Type": "application/json", "Origin": origin_header})
            data = raw if raw is not None else json.dumps(body)
            connection.request("POST", path, data, headers)
        else:
            connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result
    yield pilot, request
    server.shutdown()
    server.server_close()
    thread.join(5)


def sign_in(request, name="alice@example.test"):
    status, headers, _ = request("/api/login", {"username": name, "password": PASSWORD})
    assert status == 200
    cookie = headers["Set-Cookie"].split(";")[0]
    _, _, body = request("/api/session", cookie=cookie)
    return cookie, json.loads(body)["csrf"]


def test_weekly_routes_require_login_and_verified_artifacts(service, monkeypatch, tmp_path):
    _, request = service
    monkeypatch.setenv("PILOT_WEEKLY_ROOT", str(tmp_path / "weekly"))
    for path in ("/api/weekly", "/api/weekly/pdf"):
        assert request(path)[0] == 401
    cookie, _ = sign_in(request, "viewer@example.test")
    assert request("/api/weekly", cookie=cookie)[0] == 503
    root = tmp_path / "weekly"
    root.mkdir()
    (root / "latest.json").write_text('{"research_id":"../escape"}')
    assert request("/api/weekly/pdf", cookie=cookie)[0] == 503


def test_daily_status_retains_failed_update_then_reports_new_version(service, monkeypatch):
    import pilot_daily
    pilot, request = service
    pilot.daily_root = "synthetic"
    cookie, _ = sign_in(request)
    def fail(*_):
        raise ValueError("Invalid new snapshot")
    monkeypatch.setattr(pilot_daily, "refresh", fail)
    status, _, body = request("/api/dashboard-status", cookie=cookie)
    assert status == 200
    assert json.loads(body)["version"] == "test-version"
    assert json.loads(body)["error"]
    def update(app, *_):
        app.payload["training"]["run_id"] = "next-daily-version"
        app.refresh_error = None
        return "revision"
    monkeypatch.setattr(pilot_daily, "refresh", update)
    pilot.daily_checked = 0
    assert json.loads(request("/api/dashboard-status", cookie=cookie)[2])["version"] == "next-daily-version"


def test_macro_monitor_requires_auth_and_source_bound_inputs(service):
    _, request = service
    assert request("/api/macro-alpha")[0] == 401
    assert request("/api/macro-monitor")[0] == 401
    cookie, _ = sign_in(request, "viewer@example.test")
    assert request("/api/macro-monitor", cookie=cookie)[0] == 503


def test_http_origin_cookie_csrf_and_logout(service):
    _, request = service
    assert request("/api/dashboard")[0] == 401
    assert request("/healthz")[0] == 200
    assert request("/api/login", {"username": "alice@example.test", "password": PASSWORD}, origin_header="https://attacker.invalid")[0] == 403
    cookie, csrf = sign_in(request)
    assert request("/api/dashboard", cookie=cookie)[0] == 200
    assert request("/api/dashboard", cookie=cookie, host="attacker.invalid")[0] == 403
    assert request("/api/reallocate", {"id": "private-a"}, cookie=cookie)[0] == 403
    assert request("/api/reallocate", {"id": "private-a"}, cookie=cookie, csrf=csrf)[0] == 200
    assert request("/api/logout", {}, cookie=cookie, csrf=csrf)[0] == 200
    assert request("/api/dashboard", cookie=cookie)[0] == 401


def test_http_user_calculation_isolation_and_roles(service):
    pilot, request = service
    alice, a_csrf = sign_in(request)
    bob, b_csrf = sign_in(request, "bob@example.test")
    assert request("/api/reallocate", {"id": "alice-private"}, cookie=alice, csrf=a_csrf)[0] == 200
    assert request("/api/scenario-pdf", {"result_id": "alice-private"}, cookie=alice, csrf=a_csrf)[0] == 200
    assert request("/api/scenario-pdf", {"result_id": "alice-private"}, cookie=bob, csrf=b_csrf)[0] == 400
    assert "alice-private" not in pilot.application.results
    viewer, v_csrf = sign_in(request, "viewer@example.test")
    assert request("/api/reallocate", {"id": "no-access"}, cookie=viewer, csrf=v_csrf)[0] == 403
    assert request("/api/portfolio-pdf", {"profile_id": "shared-research-example"}, cookie=viewer, csrf=v_csrf)[0] == 200
    pilot.auth.revoke_user("bob@example.test")
    assert request("/api/dashboard", cookie=bob)[0] == 401


def test_http_malformed_json_and_no_order_routes(service):
    _, request = service
    cookie, csrf = sign_in(request)
    assert request("/api/reallocate", raw='{"id":"a","id":"b"}', cookie=cookie, csrf=csrf)[0] == 400
    assert request("/api/reallocate", raw='{"id":NaN}', cookie=cookie, csrf=csrf)[0] == 400
    assert request("/api/orders", {}, cookie=cookie, csrf=csrf)[0] == 404
    assert request("/api/reallocate", raw='x' * 9000, cookie=cookie, csrf=csrf)[0] == 400


def test_production_origin_requires_https_and_secure_host_cookie(tmp_path):
    with pytest.raises(ValueError):
        Pilot(FakeApplication(), tmp_path, "http://example.test")
    secure = Pilot(FakeApplication(), tmp_path, "https://pilot.example.test")
    assert secure.secure and secure.cookie_name.startswith("__Host-")


def test_forwarded_client_ip_is_trusted_only_from_configured_proxy(tmp_path, monkeypatch):
    import pilot_server

    pilot = Pilot(FakeApplication(), tmp_path, "https://pilot.example.test", trusted_proxy="proxy")
    monkeypatch.setattr(pilot_server.socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("172.20.0.2", 0))])
    assert pilot.peer_identity("172.20.0.2", "192.0.2.10, 198.51.100.8") == "198.51.100.8"
    assert pilot.peer_identity("203.0.113.5", "198.51.100.8") == "203.0.113.5"
    assert pilot.peer_identity("172.20.0.2", "invalid") == "172.20.0.2"


def test_pilot_scripts_have_content_bound_csp():
    import base64
    import hashlib
    import re
    from pilot_server import shell, auth_page

    for html in [shell().decode(), auth_page().decode(), auth_page(True).decode()]:
        scripts = re.findall(r"<script>([\s\S]*?)</script>", html)
        assert len(scripts) == 1
        digest = base64.b64encode(hashlib.sha256(scripts[0].encode()).digest()).decode()
        assert "sha256-" + digest in html
        assert "sessionStorage" not in html


def test_duplicate_invitation_preserves_existing_credentials(tmp_path):
    store=AuthStore(tmp_path/'auth.sqlite3')
    store.add_user('test-user',PASSWORD,must_change=False)
    with pytest.raises(ValueError,match='already exists'):
        store.add_user('test-user',PASSWORD+'different')
    assert store.login('test-user',PASSWORD,'synthetic-peer')
    assert len(store.list_users())==1


def test_viewer_cannot_record_research_approval(service):
    _,request=service
    cookie,csrf=sign_in(request,'viewer@example.test')
    assert request('/api/review',{},cookie=cookie,csrf=csrf)[0]==403


def test_workspace_requires_login_and_uses_authenticated_actor(service, monkeypatch):
    pilot, request = service
    assert request('/api/workspace')[0] == 401
    def payload(session):
        return dict(actor=session['user_id'], role=session['role'], execution_enabled=False)
    monkeypatch.setattr(pilot, 'workspace_payload', payload)
    alice, _ = sign_in(request)
    viewer, _ = sign_in(request, 'viewer@example.test')
    a = json.loads(request('/api/workspace', cookie=alice)[2])
    b = json.loads(request('/api/workspace', cookie=viewer)[2])
    assert a['actor'] != b['actor']
    assert a['role'] == 'tester' and b['role'] == 'viewer'
    assert not a['execution_enabled'] and not b['execution_enabled']


def test_overloaded_server_returns_bounded_service_unavailable():
    class Request:
        sent=b''
        closed=False
        def settimeout(self,_):pass
        def sendall(self,value):self.sent=value
        def close(self):self.closed=True
    server=BoundedServer.__new__(BoundedServer)
    server.slots=threading.BoundedSemaphore(0)
    request=Request()
    server.process_request(request,('127.0.0.1',0))
    assert request.sent.startswith(b'HTTP/1.1 503') and b'Retry-After: 1' in request.sent
    assert request.closed
