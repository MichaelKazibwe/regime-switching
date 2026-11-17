"""Authenticated loopback operator API. Not a public multi-tenant deployment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading

import pandas as pd

from clientmandate import CashRate, ClientMandate
from investmentcatalog import catalogue_payload
from productallocation import PlanningCosts
from productaudit import archive, archival_arguments
from recommendationservice import recommend
from productstate import ProductState


class OperatorApplication:
    def __init__(
        self,
        prices,
        cash_rate,
        state_root,
        *,
        historical_preview=False,
        as_of=None,
        costs=PlanningCosts(),
        fx_to_base=None,
        annual_fund_expenses=None,
    ):
        self.prices = prices.copy()
        self.cash_rate = cash_rate
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.state_root.chmod(0o700)
        # This pilot uses one state owner; prevent lost high-water updates from
        # a second API process pointed at the same private directory.
        import fcntl

        self._state_lock = open(self.state_root / "operator.lock", "a+")
        os.chmod(self.state_root / "operator.lock", 0o600)
        try:
            fcntl.flock(self._state_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._state_lock.close()
            raise ValueError(
                "Operator state directory already has an active owner"
            ) from exc
        self.historical_preview = historical_preview
        self.as_of = as_of
        self.costs = costs
        self.fx_to_base = fx_to_base.copy() if fx_to_base is not None else None
        self.annual_fund_expenses = annual_fund_expenses
        if historical_preview and not as_of:
            raise ValueError(
                "Historical operator mode requires an explicit snapshot timestamp"
            )
        self.lock = threading.RLock()

    def close(self):
        self._state_lock.close()

    def plan(self, request):
        if set(request) - {
            "mandate",
            "current_weights",
            "annual_tax_drag",
            "sale_tax_rates",
            "equity_fraction",
            "trend_confirmed",
            "paths",
        }:
            raise ValueError("Unsupported request fields")
        mandate = ClientMandate(**request["mandate"]).validate()
        count = request.get("paths", 500)
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 100 <= count <= 2000
        ):
            raise ValueError("Operator API allows 100–2000 scenario paths")
        key = hashlib.sha256(mandate.client_id.encode()).hexdigest()
        client_root = self.state_root / key
        with self.lock, ProductState(client_root) as store:
            store.recover()
            state = None
            saved = store.state()
            if saved is not None:
                if saved["base_currency"] != mandate.base_currency:
                    raise ValueError("A base-currency change needs account review")
                state = saved["state"]
            now = (
                self.as_of
                if self.historical_preview
                else datetime.now(timezone.utc).isoformat()
            )
            arguments = dict(
                decision_time=now,
                current=request.get("current_weights"),
                costs=self.costs,
                annual_tax_drag=request.get("annual_tax_drag"),
                sell_tax_rates=request.get("sale_tax_rates"),
                risk_state=state,
                equity_fraction=request.get("equity_fraction", 1.0),
                trend_confirmed=request.get("trend_confirmed", False),
                historical_preview=self.historical_preview,
                paths=count,
                fx_to_base=self.fx_to_base,
                annual_fund_expenses=self.annual_fund_expenses,
            )
            # This endpoint is always an operator tool and never loads public approval receipts.
            result = recommend(mandate, self.prices, self.cash_rate, **arguments)
            existing = store.get(result["recommendation_id"])
            if existing is not None:
                return existing
            result["input_snapshot"] = archive(
                client_root / "snapshots",
                result,
                mandate,
                self.prices,
                self.cash_rate,
                archival_arguments(**arguments),
            )
            store.commit(result)
            return result


def make_handler(application, token):
    if not isinstance(token, str) or not 32 <= len(token) <= 256 or not token.isascii():
        raise ValueError(
            "A private operator token of at least 32 characters is required"
        )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def send_json(self, data, status=200):
            body = json.dumps(data, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            host = self.headers.get("Host", "")
            if host not in {
                f"localhost:{self.server.server_port}",
                f"127.0.0.1:{self.server.server_port}",
            }:
                self.send_json({"error": "Loopback host required"}, 403)
                return False
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{host}":
                self.send_json({"error": "Same-origin requests required"}, 403)
                return False
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
                self.send_json({"error": "Authentication required"}, 401)
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            if self.path == "/v1/catalogue":
                self.send_json(
                    {
                        "instruments": catalogue_payload(),
                        "broker_submission_enabled": False,
                    }
                )
            elif self.path == "/health":
                self.send_json(
                    {
                        "status": "OPERATOR_SERVICE",
                        "public_release": False,
                        "broker_submission_enabled": False,
                    }
                )
            else:
                self.send_json({"error": "Not found"}, 404)

        def do_POST(self):
            if not self.authorized():
                return
            if self.path != "/v1/plan":
                self.send_json({"error": "Not found"}, 404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if (
                    not 2 <= length <= 262144
                    or self.headers.get("Content-Type", "").split(";")[0]
                    != "application/json"
                ):
                    self.send_json({"error": "Bounded JSON request required"}, 400)
                    return
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Object required")
                self.send_json(application.plan(body))
            except (ValueError, TypeError, KeyError):
                self.send_json(
                    {
                        "error": "Invalid planning inputs; no recommendation was released"
                    },
                    400,
                )
            except Exception:
                self.send_json(
                    {"error": "Planning unavailable; operator review required"}, 503
                )

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument("--cash-rate", type=Path, required=True)
    parser.add_argument("--fx-to-base", type=Path)
    parser.add_argument("--fund-expenses", type=Path)
    parser.add_argument("--state-root", type=Path, default=Path("var/product-api"))
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--historical-preview", action="store_true")
    parser.add_argument("--as-of")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Invalid port")
    token = os.environ.get("PRODUCT_API_TOKEN", "")
    prices = pd.read_csv(args.prices, index_col=0, parse_dates=True)
    application = OperatorApplication(
        prices,
        CashRate(**json.loads(args.cash_rate.read_text())),
        args.state_root,
        historical_preview=args.historical_preview,
        as_of=args.as_of,
        annual_fund_expenses=json.loads(args.fund_expenses.read_text())
        if args.fund_expenses
        else None,
        fx_to_base=__import__("productallocation").read_fx_csv(args.fx_to_base)
        if args.fx_to_base
        else None,
    )
    handler = make_handler(application, token)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(
        f"Operator recommendation API: http://127.0.0.1:{args.port}; public release and order submission disabled."
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        application.close()


if __name__ == "__main__":
    main()
