"""IBKR-specific paper payload adapter with injected I/O and manual warning veto.

No HTTP writer is installed or enabled here. A qualified connector supplies
request(method,path,payload), paper discovery and account binding. Tests use a
local fake; this does not establish broker entitlement or a live connection.
"""

import re
from managed_accounts import amount
import json
from urllib.request import Request
from ibkr_paper_probe import GatewayReader


class GatewayPaperWriter(GatewayReader):
    """TLS-verified loopback paper writer, explicitly disabled by default.

    Only configured operators may supply this to the account-bound coordinator
    after sandbox qualification. No authentication automation, reply approval,
    warning suppression, wildcard cancellation, remote URL or live account.
    """

    def __init__(self, account, *, submission_enabled=False, cafile=None):
        if not isinstance(account, str) or not re.fullmatch(r"DU[0-9]+", account):
            raise ValueError("Explicit paper account required")
        super().__init__(cafile=cafile)
        self.account, self.submission_enabled = account, submission_enabled

    def _exchange(self, method, path, payload=None):
        data = (
            json.dumps(payload, allow_nan=False).encode()
            if payload is not None
            else None
        )
        if data is not None and len(data) > 16384:
            raise ValueError("Order payload exceeds bound")
        request = Request(
            "https://localhost:5000/v1/api" + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with self.opener.open(request, timeout=10) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("Broker response exceeds bound")
        return json.loads(
            body,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("Nonfinite broker response")
            ),
        )

    def __call__(self, method, path, payload):
        if self.submission_enabled is not True:
            raise PermissionError("Paper HTTP submission disabled")
        post = method == "POST" and path == f"/iserver/account/{self.account}/orders"
        cancel = method == "DELETE" and re.fullmatch(
            rf"/iserver/account/{self.account}/order/[1-9][0-9]*", path
        )
        if not (post or cancel):
            raise PermissionError("Paper endpoint/account allowlist")
        if post and (
            not isinstance(payload, dict)
            or set(payload) != {"orders"}
            or len(payload["orders"]) != 1
            or payload["orders"][0].get("acctId") != self.account
        ):
            raise PermissionError("Single account-bound paper order required")
        rows = self.get("/portfolio/accounts")
        if not isinstance(rows, list) or not any(
            r.get("accountId", r.get("id")) == self.account and r.get("type") == "DEMO"
            for r in rows
        ):
            raise PermissionError("Broker demo account identity not verified")
        # IBKR requires account discovery for trading/cancellation endpoints.
        tradable = self._exchange("GET", "/iserver/accounts")
        if not isinstance(tradable, dict) or self.account not in tradable.get(
            "accounts", []
        ):
            raise PermissionError("Paper trading account not returned by broker")
        return self._exchange(method, path, payload)


class IBKRPaperOrders:
    mode = "PAPER"

    def __init__(self, account, reader, request=None):
        if not re.fullmatch(r"DU[0-9]+", account):
            raise ValueError("Paper account required")
        self.account, self.reader, self.request = account, reader, request

    def confirm_paper(self):
        rows = self.reader.get("/portfolio/accounts")
        if not isinstance(rows, list) or not any(
            r.get("accountId", r.get("id")) == self.account and r.get("type") == "DEMO"
            for r in rows
        ):
            raise PermissionError("Broker paper identity unavailable")

    def submit_intent(self, client_id, intent):
        if self.request is None:
            raise PermissionError("No qualified paper writer configured")
        if isinstance(self.request, GatewayPaperWriter) and (
            intent.get("simulation_only") is not False
            or not intent.get("production_authorization_sha256")
        ):
            raise PermissionError(
                "Synthetic simulation cannot reach the paper HTTP writer"
            )
        if (
            intent.get("mode") != "PAPER"
            or intent.get("execution_enabled") is not False
            or intent.get("account") != self.account
        ):
            raise PermissionError("Paper intent/account mismatch")
        self.confirm_paper()
        if (
            intent.get("side") not in {"BUY", "SELL"}
            or not str(intent["instrument_id"]).isdigit()
        ):
            raise ValueError("Paper adapter supports long-only limit stocks/funds only")
        if intent["side"] == "SELL" and intent.get("reduce_only") is not True:
            raise PermissionError("Only prepared reduce-only sells supported")
        quantity, price = amount(intent["quantity"]), amount(intent["price"])
        if quantity <= 0 or price <= 0:
            raise ValueError("Positive order dimensions required")
        if (
            amount(str(float(quantity))) != quantity
            or amount(str(float(price))) != price
        ):
            raise ValueError("Order cannot be represented exactly in broker JSON")
        result = self.request(
            "POST",
            f"/iserver/account/{self.account}/orders",
            {
                "orders": [
                    dict(
                        acctId=self.account,
                        conid=int(intent["instrument_id"]),
                        cOID=client_id,
                        orderType="LMT",
                        side=intent["side"],
                        tif="DAY",
                        quantity=float(quantity),
                        price=float(price),
                    )
                ]
            },
        )
        if (
            not isinstance(result, list)
            or len(result) != 1
            or not result[0].get("order_id")
            or result[0].get("id")
            or result[0].get("error")
        ):
            raise ValueError("Unresolved broker reply; do not auto-confirm or resend")
        return dict(
            client_id=client_id,
            broker_id=str(result[0]["order_id"]),
            status=result[0].get("order_status"),
        )

    def cancel(self, broker_id):
        if self.request is None:
            raise PermissionError("No qualified paper writer configured")
        if not re.fullmatch(r"[0-9]+", str(broker_id)):
            raise ValueError("Single positive broker order ID required")
        self.confirm_paper()
        return self.request(
            "DELETE", f"/iserver/account/{self.account}/order/{broker_id}", None
        )
