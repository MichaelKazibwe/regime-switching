"""Bounded invitation-only research pilot; no orders or public recommendations."""

import argparse
import base64
from collections import OrderedDict
from copy import copy, deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import hmac
import ipaddress
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import signal
import socket
import tempfile
import threading
import time
from urllib.parse import urlsplit

from pilot_auth import AuthStore
from strategy_dashboard_server import Application
from investor_dashboard import ASSETS
from strategy_integrity import strict_json, file_hash
from strategy_training_data import usable_session

LOG = logging.getLogger("regime.pilot")
PILOT_ASSETS = Path(__file__).resolve().parent / "pilot"


def encode(data):
    return json.dumps(data, allow_nan=False).encode()


def shell():
    script = (PILOT_ASSETS / "bootstrap.js").read_text() + "\n" + (ASSETS / "investor.js").read_text()
    script += ("\n" + (PILOT_ASSETS / "benchmark.js").read_text()
               + "\n" + (PILOT_ASSETS / "weekly.js").read_text()
               + "\n" + (PILOT_ASSETS / "macro-monitor.js").read_text()
               + "\n" + (PILOT_ASSETS / "workspace.js").read_text()
               + "\n}catch(error){document.getElementById('source-description').textContent='Workspace unavailable. Please sign in again or contact the operator.';}})();")
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    html = (ASSETS / "investor.html").read_text()
    html = html.replace('</nav>', '<button class="nav" data-view="benchmark">Cycle benchmark</button><button class="nav" data-view="weekly">Weekly portfolios</button></nav>', 1)
    html = html.replace('</aside>', '<div id="pilot-account" class="small"></div><button id="pilot-logout" class="button">Sign out</button></aside>', 1)
    html = html.replace('</main>', (PILOT_ASSETS / "benchmark.html").read_text() + '</main>', 1)
    html = html.replace('</main>', (PILOT_ASSETS / "weekly.html").read_text() + '</main>', 1)
    html = html.replace('</main>', (PILOT_ASSETS / "macro-monitor.html").read_text() + '</main>', 1)
    return (html.replace("default-src 'none';", "default-src 'none'; connect-src 'self';")
            .replace("__SCRIPT_HASH__", digest).replace("__STYLE__", (ASSETS / "investor.css").read_text()
                     + "\n" + (PILOT_ASSETS / "pilot.css").read_text())
            .replace("__SCRIPT__", script).replace("__DATA__", "{}").encode())


def auth_page(change=False):
    html = (PILOT_ASSETS / "login.html").read_text()
    script = (PILOT_ASSETS / "login.js").read_text()
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    return (html.replace("__SCRIPT_HASH__", digest).replace("__SCRIPT__", script)
            .replace("__MODE__", "password" if change else "login").encode())


class Pilot:
    def __init__(self, application, state, origin, *, insecure_local=False, benchmark=None, trusted_proxy=None):
        parsed = urlsplit(origin)
        if (parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username
                or parsed.password or not parsed.hostname
                or (parsed.scheme != "https" and not (
                    insecure_local and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}))):
            raise ValueError("Use an HTTPS public origin; HTTP is permitted only for explicit loopback tests")
        self.origin = origin.rstrip("/")
        self.host = parsed.netloc
        self.secure = parsed.scheme == "https"
        self.cookie_name = "__Host-regime_session" if self.secure else "regime_test_session"
        self.application, self.state = application, Path(state)
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.auth = AuthStore(self.state / "auth.sqlite3")
        self.users, self.rate = OrderedDict(), OrderedDict()
        self.rate_lock = threading.Lock()
        self.benchmark = Path(benchmark) if benchmark else None
        self.trusted_proxy = trusted_proxy
        self.daily_root = os.environ.get("PILOT_DAILY_ROOT")
        self.daily_revision = None
        self.daily_checked = 0.
        self.snapshot_root = None
        self.macro_monitor_cache = None

    def macro_monitor_payload(self):
        key = (self.application.payload["training"]["run_id"], self.daily_revision)
        if self.macro_monitor_cache is None or self.macro_monitor_cache[0] != key:
            from macro_monitor import build
            root = Path(self.daily_root) / self.daily_revision if self.daily_root and self.daily_revision else self.snapshot_root
            if root is None:
                raise ValueError("Portable daily macro evidence unavailable")
            launch = strict_json(root / "launch.json")
            self.macro_monitor_cache = (key, build(root / launch["capture"], root / launch["training_report"]))
        return {**self.macro_monitor_cache[1], "stale": self.application.payload["training"]["market_session"] != str(usable_session(datetime.now(timezone.utc)).date()),
                "update_error": self.application.refresh_error}

    def refresh(self):
        if not self.daily_root:
            self.application.refresh()
            return
        now = time.monotonic()
        if now - self.daily_checked < 60:
            return
        self.daily_checked = now
        try:
            from pilot_daily import refresh
            self.daily_revision = refresh(self.application, self.daily_root, self.state, self.daily_revision)
        except (OSError, ValueError, KeyError, TypeError):
            self.application.refresh_error = "Daily update unavailable or invalid; retaining the last verified snapshot."

    def peer_identity(self, peer, forwarded):
        if self.trusted_proxy and forwarded:
            try:
                trusted = {r[4][0] for r in socket.getaddrinfo(self.trusted_proxy, None, type=socket.SOCK_STREAM)}
                if peer in trusted:
                    return str(ipaddress.ip_address(forwarded.split(",")[-1].strip()))
            except (OSError, ValueError):
                pass
        return peer

    def throttle(self, key, *, limit=180, now=None):
        now = time.monotonic() if now is None else now
        with self.rate_lock:
            count, start = self.rate.get(key, (0, now))
            if now - start >= 60:
                count, start = 0, now
            self.rate[key] = (count + 1, start)
            self.rate.move_to_end(key)
            while len(self.rate) > 4096:
                self.rate.popitem(last=False)
            return count < limit

    def user_application(self, session):
        key = session["user_id"]
        app = self.application
        version = app.payload["training"]["run_id"]
        cached = self.users.get(key)
        if cached is None or cached[0] != version:
            personal = copy(app)
            personal.results = deepcopy(app.results)
            personal.output = self.state / "scenarios" / key
            personal.output.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.users[key] = (version, personal)
        self.users.move_to_end(key)
        while len(self.users) > 64:
            self.users.popitem(last=False)
        return self.users[key][1]

    def benchmark_payload(self):
        root = Path(self.daily_root) / self.daily_revision if self.daily_root and self.daily_revision else self.snapshot_root
        benchmark = root / "benchmark.json" if root and (root / "benchmark.json").is_file() else self.benchmark
        if benchmark is None or not benchmark.is_file():
            return dict(status="UNAVAILABLE", reason="No source-bound cycle benchmark is installed")
        result = strict_json(benchmark)
        if (result.get("status") != "RESEARCH_BENCHMARK"
                or result.get("execution_enabled") is not False
                or result.get("promotion_enabled") is not False
                or any(file_hash(p) != h for p, h in result["source_hashes"].items())):
            raise ValueError("Benchmark evidence mismatch")
        return result


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, *, workers=8):
        self.slots = threading.BoundedSemaphore(workers)
        super().__init__(address, handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


def handler(pilot):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RegimePilot"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *args):
            pass

        def send(self, body, status=200, kind="application/json", cookie=None):
            self.send_response(status)
            for name, value in {"Content-Type": kind, "Content-Length": str(len(body)),
                                "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                                "Permissions-Policy": "camera=(), microphone=(), geolocation=()"}.items():
                self.send_header(name, value)
            if pilot.secure:
                self.send_header("Strict-Transport-Security", "max-age=31536000")
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
                if "Max-Age=0" in cookie and pilot.secure:
                    self.send_header("Clear-Site-Data", '"cache", "cookies", "storage"')
            self.end_headers()
            try:
                if self.command != "HEAD":
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def json(self, data, status=200, cookie=None):
            self.send(encode(data), status, cookie=cookie)

        def allowed_origin(self):
            return (self.headers.get("Host") == pilot.host
                    and self.headers.get("Origin", pilot.origin) == pilot.origin
                    and self.headers.get("Sec-Fetch-Site", "same-origin") in {"same-origin", "none"})

        def session(self):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
            except Exception:
                return None, ""
            token = cookie[pilot.cookie_name].value if pilot.cookie_name in cookie else ""
            return pilot.auth.session(token), token

        def cookie(self, token, *, expire=False):
            return (f"{pilot.cookie_name}={token}; Path=/; HttpOnly; SameSite=Strict; "
                    f"Max-Age={0 if expire else pilot.auth.absolute}" + ("; Secure" if pilot.secure else ""))

        def request_json(self):
            if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("Bounded JSON is required")
            if len(self.headers.get_all("Content-Length", [])) != 1:
                raise ValueError("One content length required")
            length = int(self.headers["Content-Length"])
            if not 0 < length <= 8192:
                raise ValueError("Request size is invalid")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete request")
            def pairs(values):
                result = {}
                for k, v in values:
                    if k in result:
                        raise ValueError("Duplicate JSON fields")
                    result[k] = v
                return result
            value = json.loads(raw, object_pairs_hook=pairs,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite input")))
            if not isinstance(value, dict):
                raise ValueError("An object is required")
            return value

        def do_GET(self):
            if not self.allowed_origin():
                self.json({"error": "Unrecognized origin"}, 403)
                return
            if not pilot.throttle(pilot.peer_identity(self.client_address[0], self.headers.get("X-Forwarded-For"))):
                self.json({"error": "Request limit reached; retry shortly"}, 429)
                return
            if self.path == "/healthz":
                self.json({"status": "alive", "execution_enabled": False})
                return
            if self.path == "/favicon.ico":
                self.send(b"", status=204, kind="image/x-icon")
                return
            if self.path in {"/login", "/password"}:
                self.send(auth_page(self.path == "/password"), kind="text/html; charset=utf-8")
                return
            session, _ = self.session()
            if session is None:
                if self.path == "/":
                    self.send_response(303)
                    self.send_header("Location", "/login")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                else:
                    self.json({"error": "Sign in required"}, 401)
                return
            if self.path == "/api/session":
                self.json({k: session[k] for k in ["username", "role", "csrf", "must_change"]})
                return
            if session["must_change"]:
                self.json({"error": "Change your temporary password first"}, 403)
                return
            try:
                app = pilot.application
                if self.path == "/":
                    self.send(shell(), kind="text/html; charset=utf-8")
                elif self.path == "/api/news":
                    self.json(app.news.get())
                elif self.path == "/api/observations":
                    from dashboard_runtime import runtime
                    with app.lock:
                        pilot.refresh()
                        source = Path(pilot.daily_root) / pilot.daily_revision / "monitoring-runtime.json" if pilot.daily_root and pilot.daily_revision else None
                        self.json(strict_json(source) if source and source.is_file() else runtime())
                elif self.path == "/api/benchmark":
                    self.json(pilot.benchmark_payload())
                elif self.path == "/api/macro-monitor":
                    with app.lock:
                        pilot.refresh()
                        self.json(pilot.macro_monitor_payload())
                elif self.path in {"/api/weekly", "/api/weekly/pdf"}:
                    from weekly_portfolios import published, weekly_session
                    root = Path(os.environ.get("PILOT_WEEKLY_ROOT", "var/weekly-portfolios/published"))
                    if not (root / "latest.json").is_file():
                        self.json(dict(status="UNAVAILABLE", reason="No verified weekly research is installed"), 503)
                    else:
                        root, weekly = published(root)
                        weekly["stale"] = weekly["market_session"] != weekly_session(datetime.now(timezone.utc))
                        if self.path.endswith("/pdf"):
                            self.send((root / "dashboard-report.pdf").read_bytes(), kind="application/pdf")
                        else:
                            self.json(weekly)
                elif self.path in {"/api/dashboard", "/api/dashboard-status", "/readyz"}:
                    with app.lock:
                        pilot.refresh()
                        market_session = app.payload["training"]["market_session"]
                        stale = market_session != str(usable_session(datetime.now(timezone.utc)).date())
                        if self.path == "/api/dashboard":
                            self.json(app.payload)
                        else:
                            self.json(dict(version=app.payload["training"]["run_id"],
                                           market_session=market_session, stale=stale,
                                           error=app.refresh_error, execution_enabled=False),
                                      503 if self.path == "/readyz" and (stale or app.refresh_error) else 200)
                else:
                    self.json({"error": "Not found"}, 404)
            except Exception:
                LOG.exception("Pilot read failed: %s", self.path if self.path in {"/api/dashboard", "/api/benchmark", "/api/observations", "/api/news"} else "other")
                self.json({"error": "Verified data is temporarily unavailable"}, 503)

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            if not self.allowed_origin() or self.headers.get("Origin") != pilot.origin:
                self.json({"error": "Same-origin request required"}, 403)
                return
            peer = pilot.peer_identity(self.client_address[0], self.headers.get("X-Forwarded-For"))
            if not pilot.throttle(peer, limit=180):
                self.json({"error": "Request limit reached"}, 429)
                return
            try:
                body = self.request_json()
                if self.path == "/api/login":
                    if set(body) != {"username", "password"}:
                        raise ValueError("Invalid sign in")
                    token = pilot.auth.login(body["username"], body["password"], peer)
                    session = pilot.auth.session(token)
                    self.json({"next": "/password" if session["must_change"] else "/"}, cookie=self.cookie(token))
                    return
                session, token = self.session()
                if session is None:
                    self.json({"error": "Sign in required"}, 401)
                    return
                if not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf"]):
                    self.json({"error": "Refresh your session before retrying"}, 403)
                    return
                if self.path == "/api/logout":
                    if body:
                        raise ValueError("No logout fields expected")
                    pilot.auth.logout(token)
                    self.json({"status": "signed_out"}, cookie=self.cookie("", expire=True))
                    return
                if self.path == "/api/password":
                    if set(body) != {"old_password", "new_password"}:
                        raise ValueError("Invalid password change")
                    pilot.auth.change_password(session, **body)
                    self.json({"status": "changed_sign_in_again"}, cookie=self.cookie("", expire=True))
                    return
                if session["must_change"]:
                    self.json({"error": "Change your temporary password first"}, 403)
                    return
                if self.path not in {"/api/reallocate", "/api/scenario-pdf", "/api/portfolio-pdf"}:
                    self.json({"error": "Not found"}, 404)
                    return
                if self.path == "/api/reallocate" and session["role"] != "tester":
                    self.json({"error": "This account has read-only access"}, 403)
                    return
                app = pilot.application
                if not app.lock.acquire(blocking=False):
                    self.json({"error": "A calculation is active; retry shortly"}, 409)
                    return
                try:
                    pilot.refresh()
                    personal = pilot.user_application(session)
                    if self.path == "/api/reallocate":
                        self.json(personal.calculate(body))
                    elif self.path == "/api/scenario-pdf":
                        if set(body) != {"result_id"}:
                            raise ValueError("Only result_id is accepted")
                        with tempfile.TemporaryDirectory(prefix="pdf-", dir=personal.output) as temporary:
                            transient = copy(personal)
                            transient.output = Path(temporary)
                            pdf = transient.pdf(body["result_id"])
                        self.send(pdf, kind="application/pdf")
                    else:
                        if set(body) != {"profile_id"}:
                            raise ValueError("Only profile_id is accepted")
                        self.send(personal.portfolio_pdf(body["profile_id"]), kind="application/pdf")
                finally:
                    app.lock.release()
            except PermissionError:
                self.json({"error": "Invalid credentials or temporary login limit"}, 401)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                self.json({"error": "Request could not be accepted; check inputs and data freshness"}, 400)
            except Exception:
                LOG.exception("Pilot calculation failed")
                self.json({"error": "Service temporarily unavailable"}, 503)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=Path("var/pilot"))
    parser.add_argument("--origin", default=os.environ.get("PILOT_PUBLIC_ORIGIN"))
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--insecure-local", action="store_true")
    args = parser.parse_args()
    if (not args.origin or not 1 <= args.port <= 65535
            or (args.insecure_local and args.bind not in {"127.0.0.1", "localhost"})):
        parser.error("Origin/port required; insecure tests must bind only to loopback")
    os.umask(0o077)
    args.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    owner = open(args.state / "service.lock", "a+")
    try:
        fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        owner.close()
        raise ValueError("Another pilot process owns this state directory") from None
    logging.basicConfig(level=logging.INFO)
    daily_root = os.environ.get("PILOT_DAILY_ROOT")
    if daily_root and (Path(daily_root) / "latest.json").is_file():
        from pilot_daily import revision_directory
        _, directory = revision_directory(daily_root)
        args.snapshot = directory / "launch.json"
    snapshot = strict_json(args.snapshot)
    from pilot_release import verify_snapshot, verify_context, materialize_snapshot
    document = None
    if (args.snapshot.parent / "snapshot-manifest.json").exists():
        verify_snapshot(args.snapshot.parent)
        document = materialize_snapshot(args.snapshot.parent, args.state)
    elif not args.insecure_local:
        raise ValueError("A verified portable snapshot is required for the deployed pilot")
    if not args.insecure_local:
        verify_context(Path.cwd())
    def resolve(value):
        path = Path(value)
        return path if path.is_absolute() else args.snapshot.parent / path
    application = Application(document or resolve(snapshot["document"]), resolve(snapshot["capture"]), resolve(snapshot["training_report"]),
                              args.state / "shared-saved-pdfs")
    pilot = Pilot(application, args.state, args.origin, insecure_local=args.insecure_local,
                  benchmark=args.benchmark, trusted_proxy=os.environ.get("PILOT_TRUSTED_PROXY"))
    pilot.snapshot_root = args.snapshot.parent if (args.snapshot.parent / "snapshot-manifest.json").is_file() else None
    server = BoundedServer((args.bind, args.port), handler(pilot))
    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOG.info("Invited research pilot listening; no trading or public recommendation routes")
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        owner.close()


if __name__ == "__main__":
    main()
