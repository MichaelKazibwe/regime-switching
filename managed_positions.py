"""Transactional paper positions, fill costs and explicit settlement confirmation.

Average carrying cost only, not tax-lot accounting. Opening positions without
verified cost retain unknown P&L. No inferred broker fills or settlement dates.
"""

from datetime import date
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import json

from managed_accounts import amount
from strategy_integrity import canonical, fingerprint


def initialize(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS managed_positions(tenant TEXT,account TEXT,instrument TEXT,currency TEXT,quantity TEXT,cost TEXT,PRIMARY KEY(tenant,account,instrument));
      CREATE TABLE IF NOT EXISTS fill_accounting(client_id TEXT PRIMARY KEY,notional TEXT,fee TEXT);
      CREATE TABLE IF NOT EXISTS managed_settlements(id TEXT PRIMARY KEY,tenant TEXT,account TEXT,body TEXT,sha TEXT,confirmed INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS position_baselines(tenant TEXT,account TEXT,sha TEXT,PRIMARY KEY(tenant,account));
    """)


def post(db, scope, event, entries):
    if sum((amount(r["amount"]) for r in entries), Decimal(0)) != 0:
        raise ValueError("Unbalanced fill journal")
    db.execute(
        "INSERT INTO journals VALUES (?,?,?,?,?)",
        (scope.tenant, scope.account, event, canonical(entries), fingerprint(entries)),
    )


def cash_state(db, scope):
    values = {}
    with localcontext() as ctx:
        ctx.prec = 60
        for body, digest in db.execute(
            "SELECT body,sha FROM journals WHERE tenant=? AND account=?",
            (scope.tenant, scope.account),
        ):
            entries = json.loads(body)
            if fingerprint(entries) != digest:
                raise ValueError("Accounting journal integrity failure")
            for r in entries:
                key = (r["ledger"], r["currency"])
                values[key] = values.get(key, Decimal(0)) + amount(r["amount"])
        currencies = {c for _, c in values}
        settled = {c: values.get(("cash", c), Decimal(0)) for c in currencies}
        cash = {
            c: settled[c]
            + values.get(("trade_payable", c), Decimal(0))
            + values.get(("settlement_receivable", c), Decimal(0))
            for c in currencies
        }
        available = {
            c: settled[c]
            + min(values.get(("trade_payable", c), Decimal(0)), Decimal(0))
            + min(values.get(("settlement_receivable", c), Decimal(0)), Decimal(0))
            for c in currencies
        }
    return cash, settled, available


def apply_fill(db, scope, client_id, intent, event, previous_filled):
    quantity = amount(event["cumulative_filled"])
    old = amount(previous_filled)
    prior = db.execute(
        "SELECT notional,fee FROM fill_accounting WHERE client_id=?", (client_id,)
    ).fetchone()
    old_notional, old_fee = (
        (amount(v) for v in prior) if prior else (Decimal(0), Decimal(0))
    )
    if quantity == old and "cumulative_fee" not in event:
        return
    notional = amount(event["cumulative_notional"])
    fee = amount(event["cumulative_fee"])
    if notional < old_notional or fee < old_fee or notional < 0 or fee < 0:
        raise ValueError("Trade corrections require separate broker review")
    dq, dn, df = quantity - old, notional - old_notional, fee - old_fee
    if dq == 0 and dn != 0 or dq > 0 and dn <= 0:
        raise ValueError("Notional/quantity delta mismatch")
    if dq == 0 and df == 0:
        return
    trade, settles = (
        date.fromisoformat(event[k]) for k in ("trade_date", "settlement_date")
    )
    if settles < trade:
        raise ValueError("Settlement precedes trade")
    currency = intent["currency"]
    row = db.execute(
        "SELECT quantity,cost,currency FROM managed_positions WHERE tenant=? AND account=? AND instrument=?",
        (scope.tenant, scope.account, intent["instrument_id"]),
    ).fetchone()
    held = amount(row[0]) if row else Decimal(0)
    cost = (
        amount(row[1])
        if row and row[1] is not None
        else Decimal(0)
        if not row
        else None
    )
    if row and row[2] != currency:
        raise ValueError("Position currency mismatch")
    with localcontext() as ctx:
        ctx.prec = 60
        limit = (
            amount(intent["price"]) * amount(intent.get("quote_to_currency", "1")) * dq
        )
        if dq > 0 and (
            (intent["side"] == "BUY" and dn > limit)
            or (intent["side"] == "SELL" and dn < limit)
        ):
            raise ValueError("Fill violates prepared limit price")
        rows = []

        def entry(ledger, value):
            rows.append(
                dict(ledger=ledger, currency=currency, amount=format(value, "f"))
            )

        if intent["side"] == "BUY":
            new_qty = held + dq
            new_cost = cost + dn if cost is not None else None
            entry("positions_cost", dn)
            entry("trade_payable", -dn - df)
            entry("fees", df)
            net = -dn - df
            clearing = "trade_payable"
        else:
            if dq > held:
                raise ValueError("Fill would create a short position")
            new_qty = held - dq
            removed = (
                (cost * dq / held).quantize(
                    Decimal("0.00000001"), rounding=ROUND_HALF_EVEN
                )
                if cost is not None and held
                else Decimal(0)
            )
            new_cost = cost - removed if cost is not None else None
            entry("settlement_receivable", dn - df)
            entry("fees", df)
            if cost is None:
                entry("unverified_cost_disposal", -dn)
            else:
                entry("positions_cost", -removed)
                entry("realized_pnl", removed - dn)
            net = dn - df
            clearing = "settlement_receivable"
        if new_qty == 0:
            new_cost = Decimal(0)
        amount(format(new_qty, "f"))
        for r in rows:
            amount(r["amount"])
        if sum((Decimal(r["amount"]) for r in rows), Decimal(0)) != 0:
            raise ValueError("Fill journal does not reconcile")
        db.execute(
            "INSERT INTO journals VALUES (?,?,?,?,?)",
            (
                scope.tenant,
                scope.account,
                "fill:" + event["event_id"],
                canonical(rows),
                fingerprint(rows),
            ),
        )
        db.execute(
            "INSERT OR REPLACE INTO managed_positions VALUES (?,?,?,?,?,?)",
            (
                scope.tenant,
                scope.account,
                intent["instrument_id"],
                currency,
                format(new_qty, "f"),
                format(new_cost, "f") if new_cost is not None else None,
            ),
        )
        db.execute(
            "INSERT OR REPLACE INTO fill_accounting VALUES (?,?,?)",
            (client_id, str(notional), str(fee)),
        )
        settlement = dict(
            currency=currency,
            net_cash=format(net, "f"),
            clearing=clearing,
            trade_date=trade.isoformat(),
            settlement_date=settles.isoformat(),
            event_id=event["event_id"],
        )
        key = fingerprint(
            dict(tenant=scope.tenant, account=scope.account, settlement=settlement)
        )
        db.execute(
            "INSERT INTO managed_settlements VALUES (?,?,?,?,?,0)",
            (
                key,
                scope.tenant,
                scope.account,
                canonical(settlement),
                fingerprint(settlement),
            ),
        )


def confirm_settlement(db, scope, settlement_id, record_hash, as_of):
    row = db.execute(
        "SELECT body,sha,confirmed FROM managed_settlements WHERE tenant=? AND account=? AND id=?",
        (scope.tenant, scope.account, settlement_id),
    ).fetchone()
    if not row:
        raise PermissionError("Unknown account settlement")
    record = json.loads(row[0])
    if fingerprint(record) != row[1] or row[1] != record_hash:
        raise PermissionError("Settlement evidence mismatch")
    if date.fromisoformat(record["settlement_date"]) > as_of.date():
        raise PermissionError("Settlement not due")
    if row[2]:
        return "ALREADY_CONFIRMED"
    net = amount(record["net_cash"])
    entries = [
        dict(ledger="cash", currency=record["currency"], amount=str(net)),
        dict(ledger=record["clearing"], currency=record["currency"], amount=str(-net)),
    ]
    post(db, scope, "settle:" + settlement_id, entries)
    db.execute(
        "UPDATE managed_settlements SET confirmed=1 WHERE id=?", (settlement_id,)
    )
    return "CONFIRMED"
