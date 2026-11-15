"""Read-only local IBKR Client Portal paper probe; no order endpoints.

API reference: https://ibkrcampus.com/docs/web-api/v1/endpoints/portfolio/
An already authenticated paper Gateway and trusted TLS certificate are needed.
"""

import json
import re
import ssl
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from datetime import datetime, timezone

from managed_accounts import amount


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("Gateway redirects are not allowed")


class GatewayReader:
    def __init__(self, *, cafile=None):
        self.opener = build_opener(
            NoRedirect(),
            HTTPSHandler(context=ssl.create_default_context(cafile=cafile)),
        )

    def get(self, path):
        if not re.fullmatch(
            r"/portfolio/(accounts|DU[0-9]+/(ledger|positions/[0-9]+))", path
        ):
            raise ValueError("Read-only portfolio endpoint allowlist")
        request = Request("https://localhost:5000/v1/api" + path, method="GET")
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


def snapshot(reader, account):
    if not isinstance(account, str) or not re.fullmatch(r"DU[0-9]+", account):
        raise ValueError("Explicit paper account required")
    accounts = reader.get("/portfolio/accounts")
    if not isinstance(accounts, list):
        raise ValueError("Invalid account discovery response")
    selected = [a for a in accounts if a.get("accountId", a.get("id")) == account]
    if len(selected) != 1 or selected[0].get("type") != "DEMO":
        raise ValueError("Paper account identity not confirmed by broker")
    positions = []
    seen = set()
    for page in range(20):
        rows = reader.get(f"/portfolio/{account}/positions/{page}")
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError("Invalid positions page")
        if not rows:
            break
        for row in rows:
            if row.get("acctId") != account or row.get("conid") in seen:
                raise ValueError("Wrong-account or duplicate position")
            if isinstance(row.get("position"), bool):
                raise ValueError("Invalid position quantity")
            amount(str(row["position"]))
            seen.add(row["conid"])
            positions.append(row)
    else:
        raise ValueError("Positions pagination incomplete")
    ledger = reader.get(f"/portfolio/{account}/ledger")
    if not isinstance(ledger, dict) or not ledger:
        raise ValueError("Missing account ledger")
    for currency, row in ledger.items():
        if row.get("acctcode") != account:
            raise ValueError("Wrong-account cash ledger")
        for key in ("cashbalance", "settledcash"):
            if isinstance(row.get(key), bool):
                raise ValueError("Invalid cash")
            amount(str(row[key]))
    return dict(
        status="READ_ONLY_PAPER_SNAPSHOT_UNQUALIFIED",
        account=account,
        captured_at=datetime.now(timezone.utc).isoformat(),
        positions=positions,
        ledger=ledger,
        execution_enabled=False,
        release_approved=False,
    )
