"""Authenticated local shadow-allocation service. No client state or orders.

The public shell has no financial payload. A random URL-fragment token is
exchanged only via Authorization headers; it is never sent in request URLs.
"""

from __future__ import annotations

import argparse
import base64
from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading

from investor_dashboard import ASSETS
from macro_allocation_lab import prepare_lab, recalculate
from macro_lab_pdf import render_allocation_pdf
from strategy_training_data import usable_session
from strategy_integrity import canonical, verify_seal, validate_scenario


def read_payload(document):
    from html.parser import HTMLParser

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.active = False
            self.parts = []

        def handle_starttag(self, tag, attrs):
            if tag == "script" and dict(attrs).get("id") == "investor-data":
                self.active = True

        def handle_endtag(self, tag):
            if tag == "script":
                self.active = False

        def handle_data(self, value):
            if self.active:
                self.parts.append(value)

    parser = Parser()
    parser.feed(Path(document).read_text())
    return json.loads("".join(parser.parts))


class Application:
    def __init__(self, document, capture, training, output):
        captured = json.loads(Path(capture).read_text())
        if captured.get('synthetic_fixture') and os.environ.get('PILOT_ALLOW_SYNTHETIC_QA') != '1':
            raise ValueError('Synthetic research snapshots cannot serve a normal pilot')
        self.dashboard_root = Path(document).resolve().parent
        self.payload = read_payload(document)
        self.lab = prepare_lab(capture, training)
        if (
            self.payload.get("training", {}).get("run_id")
            != self.lab["report"]["run_id"]
        ):
            raise ValueError(
                "Dashboard and calculation bundle must use the same training run"
            )
        self.document = Path(document)
        verify_seal(self.document, self.payload)
        if self.payload.get("portfolio_contracts"):
            from portfolio_contract import verify_contracts

            verify_contracts(self.payload)
        if canonical(self.payload["training"]) != canonical(self.lab["report"]):
            raise ValueError("Displayed training evidence mismatch")
        for rows in self.payload["allocation_lab"]["results"].values():
            for result in rows.values():
                validate_scenario(result, self.lab)
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        from market_news import NewsCache

        self.news = NewsCache(self.payload.get("news"))
        self.lock = threading.Lock()
        self.results = OrderedDict()
        self.live_pointer = Path("var/dashboard-live/latest.json")
        self.refresh_error = None
        for rows in self.payload.get("allocation_lab", {}).get("results", {}).values():
            for result in rows.values():
                if result.get("result_id"):
                    self.results[result["result_id"]] = result

    def refresh(self):
        """Replace all financial state together, only after full validation."""
        if not self.live_pointer.exists():
            return
        try:
            from strategy_integrity import strict_json, file_hash

            pointer = strict_json(self.live_pointer)
            document = Path(pointer["document"]).resolve()
            if document == self.document.resolve():
                return
            if file_hash(document) != pointer["document_sha256"]:
                raise ValueError("Published dashboard hash mismatch")
            if file_hash(pointer["bundle"]) != pointer["bundle_sha256"]:
                raise ValueError("Published bundle hash mismatch")
            bundle = strict_json(pointer["bundle"])
            candidate = Application(
                document, bundle["capture"], bundle["training_report"], self.output
            )
            for name in ("dashboard_root", "document", "payload", "lab", "results"):
                setattr(self, name, getattr(candidate, name))
            self.refresh_error = None
        except (OSError, ValueError, KeyError, TypeError):
            self.refresh_error = "New dashboard unavailable or invalid; retaining the dated verified snapshot."

    def calculate(self, request):
        if set(request) - {"strategy", "forecast_weights", "quarters", "mode"}:
            raise ValueError("Unsupported scenario fields")
        if self.lab["report"]["market_session"] != str(
            usable_session(datetime.now(timezone.utc)).date()
        ):
            raise ValueError(
                "Market snapshot is stale; capture and train a fresh completed session"
            )
        result = recalculate(
            self.lab,
            request["strategy"],
            request["forecast_weights"],
            quarters=request.get("quarters", 4),
            paths=500,
            mode=request.get("mode", "user_scenario"),
        )
        if result.get("result_id"):
            self.results[result["result_id"]] = result
            while len(self.results) > 32:
                self.results.popitem(last=False)
        return result

    def portfolio_pdf(self, profile_id):
        verify_seal(self.document, self.payload)
        name = self.payload.get("pdf_links", {}).get(profile_id)
        if not name or Path(name).name != name or not name.endswith(".pdf"):
            raise ValueError("Unknown saved portfolio report")
        path = self.dashboard_root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Saved portfolio PDF is unavailable")
        return path.read_bytes()

    def pdf(self, result_id):
        if not isinstance(result_id, str) or result_id not in self.results:
            raise ValueError("Recalculate this scenario before PDF export")
        path = self.output / f"{result_id}.pdf"
        # Regenerate from the validated calculation; never trust an unrelated cached PDF.
        from portfolio_contract import make_contract

        result = self.results[result_id]
        contract = make_contract(
            result["strategy"],
            {**result["weights"], "USD_CASH": result["cash"]},
            result["market_session"],
            self.lab["report"]["run_id"],
            basis="CUSTOM_OR_SAVED_MACRO_SCENARIO",
            performance="CONDITIONAL_SCENARIO_NOT_REALIZED_RETURNS",
        )
        render_allocation_pdf(result, path, self.lab["report"], contract=contract)
        return path.read_bytes()


def shell():
    bootstrap = """(async()=>{try{let token=/^[a-f0-9]{64}$/.test(location.hash.slice(1))?location.hash.slice(1):sessionStorage.getItem('strategy-token');if(!token)throw Error('Open the private launch URL printed by the local strategy service.');const response=await fetch('/api/dashboard',{headers:{Authorization:'Bearer '+token}});if(!response.ok)throw Error('Private session authentication failed.');sessionStorage.setItem('strategy-token',token);history.replaceState(null,'',location.pathname);const meta=document.createElement('meta');meta.name='strategy-api-token';meta.content=token;document.head.append(meta);document.getElementById('investor-data').textContent=JSON.stringify(await response.json());"""
    script = (
        bootstrap
        + (ASSETS / "investor.js").read_text()
        + "\n}catch(error){document.getElementById('source-description').textContent=error.message;}})();"
    )
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    return (
        (ASSETS / "investor.html")
        .read_text()
        .replace("default-src 'none';", "default-src 'none'; connect-src 'self';")
        .replace("__SCRIPT_HASH__", digest)
        .replace("__STYLE__", (ASSETS / "investor.css").read_text())
        .replace("__SCRIPT__", script)
        .replace("__DATA__", "{}")
        .encode()
    )


def handler(application, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, body, status=200, kind="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def json(self, data, status=200):
            self.send(json.dumps(data, allow_nan=False).encode(), status)

        def origin_ok(self):
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            return host in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            } and (not origin or origin == f"http://{host}")

        def authorized(self):
            return self.origin_ok() and hmac.compare_digest(
                self.headers.get("Authorization", "").encode(),
                ("Bearer " + token).encode(),
            )

        def do_GET(self):
            if not self.origin_ok():
                self.json({"error": "Loopback same-origin access required"}, 403)
                return
            if self.path == "/":
                self.send(shell(), kind="text/html; charset=utf-8")
                return
            if self.path == "/api/observations":
                if not self.authorized():
                    self.json({"error": "Authentication required"}, 401)
                    return
                from dashboard_runtime import runtime

                self.json(runtime())
                return
            if self.path == "/api/news":
                if not self.authorized():
                    self.json({"error": "Authentication required"}, 401)
                    return
                self.json(application.news.get())
                return
            if self.path == "/api/dashboard":
                if not self.authorized():
                    self.json({"error": "Authentication required"}, 401)
                    return
                if hasattr(application, "refresh"):
                    with application.lock:
                        application.refresh()
                        self.json(application.payload)
                else:
                    self.json(application.payload)
                return
            if self.path == "/api/dashboard-status":
                if not self.authorized():
                    self.json({"error": "Authentication required"}, 401)
                    return
                with application.lock:
                    application.refresh()
                    session = application.payload["training"]["market_session"]
                    self.json(
                        dict(
                            version=application.payload["training"]["run_id"],
                            market_session=session,
                            stale=session
                            != str(usable_session(datetime.now(timezone.utc)).date()),
                            error=application.refresh_error,
                        )
                    )
                return
            self.json({"error": "Not found"}, 404)

        def do_POST(self):
            if not self.authorized():
                self.json({"error": "Authentication required"}, 401)
                return
            if self.path not in {
                "/api/reallocate",
                "/api/scenario-pdf",
                "/api/portfolio-pdf",
            }:
                self.json({"error": "Not found"}, 404)
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.json({"error": "JSON required"}, 415)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("Scenario body exceeds bounds")
                request = json.loads(
                    self.rfile.read(length),
                    parse_constant=lambda _: (_ for _ in ()).throw(
                        ValueError("Nonfinite input")
                    ),
                )
                if not isinstance(request, dict):
                    raise ValueError("JSON object required")
            except (ValueError, TypeError):
                self.json({"error": "Invalid scenario request"}, 400)
                return
            if not application.lock.acquire(blocking=False):
                self.json({"error": "A calculation is active; retry shortly"}, 409)
                return
            try:
                application.refresh()
                if self.path == "/api/reallocate":
                    self.json(application.calculate(request))
                elif self.path == "/api/portfolio-pdf":
                    if set(request) != {"profile_id"}:
                        raise ValueError("Only profile_id is accepted")
                    self.send(
                        application.portfolio_pdf(request["profile_id"]),
                        kind="application/pdf",
                    )
                else:
                    if set(request) != {"result_id"}:
                        raise ValueError("Only result_id is accepted")
                    self.send(
                        application.pdf(request["result_id"]), kind="application/pdf"
                    )
            except (ValueError, KeyError, TypeError) as exc:
                self.json({"error": str(exc)}, 400)
            except Exception:
                self.json(
                    {"error": "Calculation failed; no client state was changed"}, 500
                )
            finally:
                application.lock.release()

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dashboard",
        type=Path,
        default=Path("var/investor-dashboard/investor-dashboard.html"),
    )
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--training-report", type=Path)
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path("var/investor-dashboard/latest-strategy-run.json"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("var/strategy-scenario-pdfs")
    )
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Invalid port")
    if not args.capture and not args.training_report:
        pointer = Path("var/dashboard-live/latest.json")
        if pointer.exists() and args.bundle == Path(
            "var/investor-dashboard/latest-strategy-run.json"
        ):
            from strategy_integrity import strict_json, file_hash

            published = strict_json(pointer)
            if (
                file_hash(published["document"]) != published["document_sha256"]
                or file_hash(published["bundle"]) != published["bundle_sha256"]
            ):
                raise ValueError("Published viewer integrity failure")
            args.dashboard = Path(published["document"])
            args.bundle = Path(published["bundle"])
        bundle = json.loads(args.bundle.read_text())
        args.capture = Path(bundle["capture"])
        args.training_report = Path(bundle["training_report"])
    elif not args.capture or not args.training_report:
        parser.error(
            "Supply both --capture and --training-report, or a completed --bundle"
        )
    app = Application(args.dashboard, args.capture, args.training_report, args.output)
    token = secrets.token_hex(32)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(app, token))
    server.daemon_threads = True
    print(
        f"Private local strategy service: http://127.0.0.1:{server.server_port}/#{token}",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
