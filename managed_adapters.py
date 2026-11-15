"""Explicit raw-quote and IBKR-paper snapshot normalization; no adjusted fills."""

from datetime import datetime, timezone, timedelta
from managed_accounts import amount


def raw_quote(reader, scope, contract, *, now=None):
    now = now or datetime.now(timezone.utc)
    contract.validate()
    row = reader(scope, contract)
    if (
        row.get("kind") != "RAW_BID_ASK"
        or row.get("instrument_id") != contract.contract_id
        or row.get("currency") != contract.currency
        or row.get("quote_unit", contract.currency) != contract.quote_unit
        or not row.get("source")
    ):
        raise ValueError(
            "Identified raw quote required; adjusted research prices denied"
        )
    stamp = datetime.fromisoformat(row["as_of"])
    if (
        stamp.tzinfo is None
        or now.tzinfo is None
        or not timedelta(0) <= now - stamp <= timedelta(seconds=30)
    ):
        raise ValueError("Stale/future quote")
    bid, ask = amount(row["bid"]), amount(row["ask"])
    if not 0 < bid <= ask:
        raise ValueError("Invalid bid/ask")
    return {**row, "basis": "UNADJUSTED_EXECUTABLE"}


def normalize_paper_account(snapshot, scope, open_orders, orders_as_of, *, now=None):
    now = now or datetime.now(timezone.utc)
    if (
        snapshot.get("account") != scope.account
        or snapshot.get("status") != "READ_ONLY_PAPER_SNAPSHOT_UNQUALIFIED"
    ):
        raise PermissionError("Account-bound paper snapshot required")
    for value in (snapshot["captured_at"], orders_as_of):
        stamp = datetime.fromisoformat(value)
        if (
            now.tzinfo is None
            or stamp.tzinfo is None
            or not timedelta(0) <= now - stamp <= timedelta(seconds=60)
        ):
            raise ValueError("Stale/future account or open-order snapshot")
    if (
        not isinstance(open_orders, list)
        or any(not isinstance(v, str) or not v for v in open_orders)
        or len(set(open_orders)) != len(open_orders)
    ):
        raise ValueError("Complete explicit broker order identifiers required")
    cash, settled, positions = {}, {}, {}
    for currency, row in snapshot["ledger"].items():
        if row.get("acctcode") != scope.account:
            raise PermissionError("Wrong cash account")
        if currency == "BASE":
            continue
        if len(currency) != 3 or not currency.isupper():
            raise ValueError("Explicit currency required")
        cash[currency] = str(amount(str(row["cashbalance"])))
        settled[currency] = str(amount(str(row["settledcash"])))
    if not cash:
        raise ValueError("Missing explicit currency balances")
    for row in snapshot["positions"]:
        if row.get("acctId") != scope.account:
            raise PermissionError("Wrong position account")
        key = str(row["conid"])
        if key in positions:
            raise ValueError("Duplicate contract position")
        positions[key] = str(amount(str(row["position"])))
    return dict(
        tenant=scope.tenant,
        account=scope.account,
        as_of=min(
            snapshot["captured_at"],
            orders_as_of,
            key=lambda v: datetime.fromisoformat(v),
        ),
        cash=cash,
        settled_cash=settled,
        positions=positions,
        open_orders=sorted(open_orders),
        # Caller must supply actual action state before reconciliation.
        corporate_actions=None,
    )
