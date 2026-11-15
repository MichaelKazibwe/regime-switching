"""Account-bound PAPER orchestration, durable ambiguity quarantine and reconciliation.

No live enablement. The supplied transport must be an explicitly selected paper
connector. Existing production authorization and broker routes are unchanged.
"""

from datetime import datetime, timezone, timedelta
from datetime import date
from decimal import Decimal
import hashlib
import hmac
import json

from managed_accounts import amount, exact_add, identifier
from managed_boundary import eligible_paper_order
from strategy_integrity import canonical, fingerprint
from global_market_calendar import is_regular_session
import managed_positions
from writer_fencing import FencedOut

OPEN_STATES = {
    "PAPER_PENDING",
    "DISPATCHING",
    "UNKNOWN",
    "ACCEPTED",
    "PARTIAL",
    "CANCEL_PENDING",
}


def verify_permit(permit, signature, key, scope, release_id, image_digest, *, now):
    if len(key) < 32:
        raise ValueError("Protected verification key required")
    expected = hmac.new(key, canonical(permit).encode(), hashlib.sha256).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise PermissionError("Invalid permit signature")
    issued, expires = (
        datetime.fromisoformat(permit[k]) for k in ("issued_at", "expires_at")
    )
    if (
        now.tzinfo is None
        or issued.tzinfo is None
        or expires.tzinfo is None
        or not issued <= now < expires
        or expires - issued > timedelta(hours=24)
    ):
        raise PermissionError("Expired or invalid permit window")
    if (
        permit.get("tenant"),
        permit.get("account"),
        permit.get("release_id"),
        permit.get("image_digest"),
        permit.get("mode"),
    ) != (scope.tenant, scope.account, release_id, image_digest, "PAPER"):
        raise PermissionError("Permit scope mismatch")
    if not permit.get("reviewer") or not permit.get("evidence_id"):
        raise PermissionError("Reviewed evidence required")
    for name in ("max_order_notional", "max_open_notional"):
        if amount(permit[name]) <= 0:
            raise ValueError("Positive paper limits required")
    return permit


class ManagedExecution:
    def __init__(
        self,
        store,
        sessions,
        *,
        verification_key,
        release_id,
        image_digest,
        clock=None,
        authorization_reader=None,
        portfolio_risk_reader=None,
        writer_lease=None,
        simulation_only=False,
    ):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.store, self.sessions = store, sessions
        if not isinstance(simulation_only, bool):
            raise ValueError("Explicit simulation mode required")
        self.authorization_reader, self.simulation_only = (
            authorization_reader,
            simulation_only,
        )
        self.portfolio_risk_reader = portfolio_risk_reader
        self.writer_lease = writer_lease
        self.key, self.release_id, self.image_digest = (
            verification_key,
            release_id,
            image_digest,
        )
        with store.connect() as db:
            from writer_fencing import initialize

            initialize(db)
            managed_positions.initialize(db)
            db.executescript("""
              CREATE TABLE IF NOT EXISTS broker_events(tenant TEXT,account TEXT,event_id TEXT,body TEXT,sha TEXT,PRIMARY KEY(tenant,account,event_id));
              CREATE TABLE IF NOT EXISTS broker_ids(tenant TEXT,account TEXT,broker_id TEXT,client_id TEXT UNIQUE,filled TEXT NOT NULL DEFAULT '0',PRIMARY KEY(tenant,account,broker_id));
              CREATE TABLE IF NOT EXISTS account_reconciliation(tenant TEXT,account TEXT,body TEXT,sha TEXT,PRIMARY KEY(tenant,account));
              CREATE TABLE IF NOT EXISTS managed_incidents(seq INTEGER PRIMARY KEY,tenant TEXT,account TEXT,as_of TEXT,reason TEXT);
              CREATE TABLE IF NOT EXISTS portfolio_risk_reviews(seq INTEGER PRIMARY KEY,tenant TEXT,account TEXT,client_id TEXT,body TEXT,sha TEXT);
              CREATE TRIGGER IF NOT EXISTS immutable_risk_review_update BEFORE UPDATE ON portfolio_risk_reviews BEGIN SELECT RAISE(ABORT,'Immutable risk review'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_risk_review_delete BEFORE DELETE ON portfolio_risk_reviews BEGIN SELECT RAISE(ABORT,'Immutable risk review'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_broker_events_update BEFORE UPDATE ON broker_events BEGIN SELECT RAISE(ABORT,'Immutable broker event'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_broker_events_delete BEFORE DELETE ON broker_events BEGIN SELECT RAISE(ABORT,'Immutable broker event'); END;
            """)

    def adopt_opening_book(self, token, scope, permit, signature, *, now=None):
        now = now or self.clock()
        p = self.sessions.resolve(token, now=now)
        verify_permit(
            permit,
            signature,
            self.key,
            scope,
            self.release_id,
            self.image_digest,
            now=now,
        )
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self.simulation_only:
                self._writer(db, scope, now)
            if not self.store.check_account(db, p, scope, "reconcile"):
                raise PermissionError("Freeze account before reviewed opening import")
            if db.execute(
                "SELECT 1 FROM position_baselines WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            ).fetchone():
                raise PermissionError("Opening book already registered")
            row = db.execute(
                "SELECT body,sha FROM account_reconciliation WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            ).fetchone()
            if not row:
                raise PermissionError("Matched opening snapshot required")
            report = json.loads(row[0])
            if (
                fingerprint(report) != row[1]
                or report["status"] != "MATCHED"
                or not timedelta(0)
                <= now - datetime.fromisoformat(report["as_of"])
                <= timedelta(seconds=60)
            ):
                raise PermissionError("Opening snapshot stale or blocked")
            broker = report["broker"]
            if broker["open_orders"]:
                raise PermissionError(
                    "Resolve existing broker orders before opening import"
                )
            if broker["cash"] != broker["settled_cash"]:
                raise PermissionError(
                    "Opening unsettled cash requires prior-trade review"
                )
            if permit.get("opening_snapshot_hash") != fingerprint(broker) or set(
                permit.get("opening_positions", {})
            ) != set(broker["positions"]):
                raise PermissionError("Signed opening account evidence required")
            for instrument, position in permit["opening_positions"].items():
                quantity = amount(position["quantity"])
                if quantity < 0 or quantity != amount(broker["positions"][instrument]):
                    raise ValueError("Opening quantity mismatch")
                currency = position["currency"]
                if len(currency) != 3 or not currency.isupper():
                    raise ValueError("Opening currency required")
                cost = position.get("cost")
                if cost is not None and amount(cost) < 0:
                    raise ValueError("Opening cost invalid")
                db.execute(
                    "INSERT INTO managed_positions VALUES (?,?,?,?,?,?)",
                    (
                        scope.tenant,
                        scope.account,
                        instrument,
                        currency,
                        str(quantity),
                        cost,
                    ),
                )
                if cost is not None:
                    managed_positions.post(
                        db,
                        scope,
                        "opening-position:" + instrument,
                        [
                            dict(
                                ledger="positions_cost", currency=currency, amount=cost
                            ),
                            dict(
                                ledger="opening_capital",
                                currency=currency,
                                amount=str(-amount(cost)),
                            ),
                        ],
                    )
            for currency, value in broker["cash"].items():
                cash = amount(value)
                managed_positions.post(
                    db,
                    scope,
                    "opening:" + currency,
                    [
                        dict(ledger="cash", currency=currency, amount=str(cash)),
                        dict(
                            ledger="opening_capital",
                            currency=currency,
                            amount=str(-cash),
                        ),
                    ],
                )
            db.execute(
                "INSERT INTO position_baselines VALUES (?,?,?)",
                (scope.tenant, scope.account, fingerprint(broker)),
            )
        return "REVIEWED_PAPER_OPENING_REGISTERED"

    def confirm_settlement(self, token, scope, permit, signature, *, now=None):
        now = now or self.clock()
        p = self.sessions.resolve(token, now=now)
        verify_permit(
            permit,
            signature,
            self.key,
            scope,
            self.release_id,
            self.image_digest,
            now=now,
        )
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self.simulation_only:
                self._writer(db, scope, now)
            self.store.check_account(db, p, scope, "reconcile")
            result = managed_positions.confirm_settlement(
                db, scope, permit["settlement_id"], permit["settlement_hash"], now
            )
            db.execute(
                "DELETE FROM account_reconciliation WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            )
        return result

    def reconcile(self, token, scope, broker, local, *, now=None):
        """Normalized snapshots; unexplained differences/actions/orders freeze account.

        Corporate actions are not guessed or automatically applied. Caller must
        normalize broker data and explicitly reconcile outstanding local orders.
        """
        now = now or self.clock()
        p = self.sessions.resolve(token, now=now)
        reasons = []
        for snapshot in (broker, local):
            if (snapshot.get("tenant"), snapshot.get("account")) != (
                scope.tenant,
                scope.account,
            ):
                raise PermissionError("Wrong-account reconciliation snapshot")
            stamp = datetime.fromisoformat(snapshot["as_of"])
            if stamp.tzinfo is None or not timedelta(0) <= now - stamp <= timedelta(
                seconds=60
            ):
                raise ValueError("Stale or future reconciliation snapshot")
        for snapshot in (broker, local):
            for field in ("cash", "settled_cash", "positions"):
                if not isinstance(snapshot.get(field), dict):
                    raise ValueError("Normalized account quantities required")
                for value in snapshot[field].values():
                    amount(value)
            if not isinstance(snapshot.get("open_orders"), list) or not isinstance(
                snapshot.get("corporate_actions"), list
            ):
                raise ValueError("Explicit order and corporate-action state required")
        for field in ("cash", "settled_cash", "positions", "open_orders"):
            if broker.get(field) != local.get(field):
                reasons.append(field + "_mismatch")
        if broker.get("corporate_actions") or local.get("corporate_actions"):
            reasons.append("corporate_action_review")
        record = dict(
            as_of=now.isoformat(),
            status="MATCHED" if not reasons else "QUARANTINED",
            reasons=reasons,
            broker=broker,
            local=local,
        )
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self.simulation_only:
                self._writer(db, scope, now)
            self.store.check_account(db, p, scope, "reconcile")
            if db.execute(
                "SELECT 1 FROM position_baselines WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            ).fetchone():
                cash, settled, _ = managed_positions.cash_state(db, scope)
                positions = {
                    k: amount(v)
                    for k, v in db.execute(
                        "SELECT instrument,quantity FROM managed_positions WHERE tenant=? AND account=?",
                        (scope.tenant, scope.account),
                    )
                    if amount(v) != 0
                }
                orders = sorted(
                    r[0]
                    for r in db.execute(
                        "SELECT b.broker_id FROM broker_ids b JOIN outbox o ON b.client_id=o.client_id WHERE b.tenant=? AND b.account=? AND o.state IN ('ACCEPTED','PARTIAL','CANCEL_PENDING')",
                        (scope.tenant, scope.account),
                    )
                )
                if positions != {
                    k: amount(v)
                    for k, v in local["positions"].items()
                    if amount(v) != 0
                }:
                    reasons.append("local_position_book_mismatch")
                if cash != {
                    k: amount(v) for k, v in local["cash"].items()
                } or settled != {
                    k: amount(v) for k, v in local["settled_cash"].items()
                }:
                    reasons.append("local_cash_book_mismatch")
                if orders != sorted(local["open_orders"]):
                    reasons.append("local_open_order_book_mismatch")
                if reasons:
                    record["status"] = "QUARANTINED"
                    record["reasons"] = reasons
            db.execute(
                "INSERT OR REPLACE INTO account_reconciliation VALUES (?,?,?,?)",
                (scope.tenant, scope.account, canonical(record), fingerprint(record)),
            )
            if reasons:
                db.execute(
                    "UPDATE accounts SET frozen=1 WHERE tenant=? AND account=?",
                    (scope.tenant, scope.account),
                )
        return record

    def prepare(
        self,
        token,
        scope,
        client_id,
        contract,
        quote,
        quantity,
        permit,
        signature,
        *,
        side="BUY",
        reduce_only=False,
        now=None,
    ):
        identifier(client_id)
        now = now or self.clock()
        limits = verify_permit(
            permit,
            signature,
            self.key,
            scope,
            self.release_id,
            self.image_digest,
            now=now,
        )
        if limits.get("currency") != contract.currency:
            raise PermissionError("Permit currency mismatch")
        if side not in {"BUY", "SELL"} or not isinstance(reduce_only, bool):
            raise ValueError("Explicit supported side/reduce-only required")
        if side == "SELL" and (
            not reduce_only or limits.get("allow_reduce_only_sell") is not True
        ):
            raise PermissionError("Signed reduce-only SELL permission required")
        p, notional = eligible_paper_order(
            self.sessions,
            token,
            scope,
            contract,
            quote,
            quantity,
            client_country=limits["client_country"],
            allowed_countries=limits["allowed_countries"],
            now=now,
        )
        if not is_regular_session(contract.venue, now):
            raise PermissionError("Venue regular session closed")
        if quote.get("basis") != "UNADJUSTED_EXECUTABLE" or not quote.get("source"):
            raise ValueError("Executable raw quote and source required")
        bid, ask = amount(quote["bid"]), amount(quote["ask"])
        if bid <= 0 or ask < bid or (ask - bid) / ask > Decimal("0.02"):
            raise ValueError("Invalid or excessive bid/ask spread")
        price = quote["ask"] if side == "BUY" else quote["bid"]
        notional = contract.validate_order(quantity, price)
        if notional > amount(limits["max_order_notional"]):
            raise PermissionError("Order notional cap")
        fee_buffer = amount(limits["fee_buffer"])
        if fee_buffer < 0:
            raise ValueError("Reviewed nonnegative fee buffer required")
        risk_hash = None
        if not self.simulation_only:
            risk_hash = self._production_risk(
                client_id, limits, contract, quantity, price, side
            )
        # Long-only stock/fund LIMIT orders; no shorts, margin, FX or futures.
        intent = dict(
            mode="PAPER",
            execution_enabled=False,
            tenant=scope.tenant,
            account=scope.account,
            instrument_id=contract.contract_id,
            mandate_id=limits["mandate_id"],
            release_id=self.release_id,
            authorization_id=fingerprint(permit),
            quantity=quantity,
            price=price,
            side=side,
            reduce_only=reduce_only,
            quote_to_currency=contract.quote_to_currency,
            accounting_required=True,
            simulation_only=self.simulation_only,
            production_authorization_sha256=risk_hash,
            currency=contract.currency,
            notional=str(notional),
            fee_buffer=str(fee_buffer),
            cash_reservation=str(exact_add(notional, fee_buffer)),
            created_at=now.isoformat(),
            quote_as_of=quote["as_of"],
            permit=permit,
            permit_signature=signature,
        )
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.store.check_account(db, p, scope, "enqueue"):
                raise PermissionError("Account frozen")
            if not db.execute(
                "SELECT 1 FROM position_baselines WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            ).fetchone():
                raise PermissionError("Reviewed opening position/cash book required")
            previous = db.execute(
                "SELECT body FROM outbox WHERE client_id=?", (client_id,)
            ).fetchone()
            if previous:
                if json.loads(previous[0]) != intent:
                    raise ValueError("Conflicting replay")
                return "ALREADY_QUEUED"
            row = db.execute(
                "SELECT body,sha FROM account_reconciliation WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            ).fetchone()
            if not row:
                raise PermissionError("Account reconciliation missing")
            r = json.loads(row[0])
            if (
                fingerprint(r) != row[1]
                or r["status"] != "MATCHED"
                or now - datetime.fromisoformat(r["as_of"]) > timedelta(seconds=60)
            ):
                raise PermissionError("Account reconciliation stale or blocked")
            _, _, available_cash = managed_positions.cash_state(db, scope)
            cash = min(
                amount(r["broker"]["settled_cash"].get(contract.currency, "0")),
                available_cash.get(contract.currency, Decimal(0)),
            )
            pending = Decimal(0)
            reserved_sell = Decimal(0)
            for body, state in db.execute(
                "SELECT body,state FROM outbox WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            ):
                order = json.loads(body)
                if (
                    state in OPEN_STATES
                    and order.get("side", "BUY") == "BUY"
                    and order.get("currency") == contract.currency
                ):
                    pending = exact_add(
                        pending,
                        amount(order.get("cash_reservation", order["notional"])),
                    )
                if (
                    state in OPEN_STATES
                    and order.get("side") == "SELL"
                    and order.get("instrument_id") == contract.contract_id
                ):
                    # Conservative reservation keeps the full sell quantity until
                    # terminal status; partial fills can therefore only reduce capacity.
                    reserved_sell = exact_add(reserved_sell, amount(order["quantity"]))
            if side == "SELL":
                position = db.execute(
                    "SELECT quantity FROM managed_positions WHERE tenant=? AND account=? AND instrument=?",
                    (scope.tenant, scope.account, contract.contract_id),
                ).fetchone()
                available = min(
                    amount(position[0]) if position else Decimal(0),
                    amount(r["broker"]["positions"].get(contract.contract_id, "0")),
                )
                if exact_add(reserved_sell, amount(quantity)) > available:
                    raise PermissionError(
                        "Reduce-only SELL exceeds unreserved holdings"
                    )
            if side == "BUY" and (
                exact_add(pending, exact_add(notional, fee_buffer)) > cash
                or exact_add(pending, notional) > amount(limits["max_open_notional"])
            ):
                raise PermissionError("Settled cash or pending exposure cap")
            if not self.simulation_only:
                self._portfolio_envelope(db, scope, client_id, intent, now, "PREPARE")
                self._writer(db, scope, now)
                intent["writer_epoch"] = self.writer_lease.epoch
            db.execute(
                "INSERT INTO outbox VALUES (?,?,?,?,?,?)",
                (
                    client_id,
                    scope.tenant,
                    scope.account,
                    canonical(intent),
                    fingerprint(intent),
                    "PAPER_PENDING",
                ),
            )
        return "PAPER_QUEUED"

    def dispatch(self, token, scope, client_id, transport, *, now=None):
        now = now or self.clock()
        p = self.sessions.resolve(token, now=now)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.store.check_account(db, p, scope, "dispatch"):
                raise PermissionError("Account frozen")
            row = db.execute(
                "SELECT body,sha,state FROM outbox WHERE client_id=? AND tenant=? AND account=?",
                (client_id, scope.tenant, scope.account),
            ).fetchone()
            if not row or row[2] != "PAPER_PENDING":
                raise PermissionError("Not a dispatchable paper intent")
            intent = json.loads(row[0])
            if fingerprint(intent) != row[1]:
                raise ValueError("Outbox integrity failure")
            verify_permit(
                intent["permit"],
                intent["permit_signature"],
                self.key,
                scope,
                self.release_id,
                self.image_digest,
                now=now,
            )
            if not self.simulation_only:
                current = self._production_risk(
                    client_id,
                    intent["permit"],
                    None,
                    intent["quantity"],
                    intent["price"],
                    intent["side"],
                )
                if current != intent["production_authorization_sha256"]:
                    raise PermissionError("Production authorization changed")
            if (
                not timedelta(0)
                <= now - datetime.fromisoformat(intent["quote_as_of"])
                <= timedelta(seconds=30)
            ):
                raise PermissionError("Intent quote window expired")
            if transport.account != scope.account or transport.mode != "PAPER":
                raise PermissionError("Paper transport/account mismatch")
            reconciliation = db.execute(
                "SELECT body,sha FROM account_reconciliation WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            ).fetchone()
            if not reconciliation:
                raise PermissionError("Fresh reconciliation required at dispatch")
            report = json.loads(reconciliation[0])
            if (
                fingerprint(report) != reconciliation[1]
                or report["status"] != "MATCHED"
                or not timedelta(0)
                <= now - datetime.fromisoformat(report["as_of"])
                <= timedelta(seconds=60)
            ):
                raise PermissionError("Fresh matched reconciliation required")
            pending = Decimal(0)
            sell_reserved = Decimal(0)
            for body, state in db.execute(
                "SELECT body,state FROM outbox WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            ):
                order = json.loads(body)
                if (
                    state in OPEN_STATES
                    and order.get("side", "BUY") == "BUY"
                    and order.get("currency") == intent["currency"]
                ):
                    pending = exact_add(
                        pending,
                        amount(order.get("cash_reservation", order["notional"])),
                    )
                if (
                    state in OPEN_STATES
                    and order.get("side") == "SELL"
                    and order.get("instrument_id") == intent["instrument_id"]
                ):
                    sell_reserved = exact_add(sell_reserved, amount(order["quantity"]))
            if intent["side"] == "SELL":
                position = db.execute(
                    "SELECT quantity FROM managed_positions WHERE tenant=? AND account=? AND instrument=?",
                    (scope.tenant, scope.account, intent["instrument_id"]),
                ).fetchone()
                available = min(
                    amount(position[0]) if position else Decimal(0),
                    amount(
                        report["broker"]["positions"].get(intent["instrument_id"], "0")
                    ),
                )
                if sell_reserved > available:
                    raise PermissionError(
                        "Holdings changed before reduce-only dispatch"
                    )
            _, _, available_cash = managed_positions.cash_state(db, scope)
            if intent["side"] == "BUY" and pending > min(
                amount(report["broker"]["settled_cash"].get(intent["currency"], "0")),
                available_cash.get(intent["currency"], Decimal(0)),
            ):
                raise PermissionError("Settled cash changed before dispatch")
            if not self.simulation_only:
                self._portfolio_envelope(db, scope, client_id, intent, now, "DISPATCH")
                self._writer(db, scope, now)
                if intent.get("writer_epoch") != self.writer_lease.epoch:
                    raise FencedOut("Prepared intent belongs to an older writer epoch")
            db.execute(
                "UPDATE outbox SET state='DISPATCHING' WHERE client_id=?", (client_id,)
            )
        try:
            receipt = transport.submit_intent(client_id, intent)
            if receipt.get("client_id") != client_id or not receipt.get("broker_id"):
                raise ValueError("Ambiguous broker acknowledgement")
            with self.store.connect() as db:
                if not self.simulation_only:
                    db.execute("BEGIN IMMEDIATE")
                    self._writer(db, scope, self.clock())
                db.execute(
                    "INSERT INTO broker_ids(tenant,account,broker_id,client_id) VALUES (?,?,?,?)",
                    (scope.tenant, scope.account, str(receipt["broker_id"]), client_id),
                )
                db.execute(
                    "UPDATE outbox SET state='ACCEPTED' WHERE client_id=?", (client_id,)
                )
            return receipt
        except Exception:
            with self.store.connect() as db:
                db.execute(
                    "UPDATE outbox SET state='UNKNOWN' WHERE client_id=?", (client_id,)
                )
                db.execute(
                    "UPDATE accounts SET frozen=1 WHERE tenant=? AND account=?",
                    (scope.tenant, scope.account),
                )
            raise

    def recover(self):
        """Crash in dispatch means unknown outcome, never automatic resubmission."""
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT tenant,account FROM outbox WHERE state='DISPATCHING'"
            ).fetchall()
            for tenant, account in rows:
                db.execute(
                    "UPDATE accounts SET frozen=1 WHERE tenant=? AND account=?",
                    (tenant, account),
                )
            db.execute("UPDATE outbox SET state='UNKNOWN' WHERE state='DISPATCHING'")
        return len(rows)

    def bind_unknown(self, token, scope, client_id, permit, signature, *, now=None):
        """Reviewed binding of a confirmed broker order; never retry an unknown send."""
        now = now or self.clock()
        p = self.sessions.resolve(token, now=now)
        verify_permit(
            permit,
            signature,
            self.key,
            scope,
            self.release_id,
            self.image_digest,
            now=now,
        )
        if (
            permit.get("resolution_client_id") != client_id
            or not isinstance(permit.get("resolution_broker_id"), str)
            or not permit["resolution_broker_id"].isdigit()
        ):
            raise PermissionError("Signed broker-ID resolution required")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self.simulation_only:
                self._writer(db, scope, now)
            self.store.check_account(db, p, scope, "reconcile")
            row = db.execute(
                "SELECT state FROM outbox WHERE tenant=? AND account=? AND client_id=?",
                (scope.tenant, scope.account, client_id),
            ).fetchone()
            if not row or row[0] != "UNKNOWN":
                raise PermissionError("Only quarantined submissions can be bound")
            db.execute(
                "INSERT INTO broker_ids(tenant,account,broker_id,client_id) VALUES (?,?,?,?)",
                (
                    scope.tenant,
                    scope.account,
                    permit["resolution_broker_id"],
                    client_id,
                ),
            )
            db.execute(
                "UPDATE outbox SET state='ACCEPTED' WHERE client_id=?", (client_id,)
            )
            db.execute(
                "DELETE FROM account_reconciliation WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            )
        return "BOUND_STILL_FROZEN_RECONCILIATION_REQUIRED"

    def cancel(self, token, scope, broker_id, transport, *, now=None):
        p = self.sessions.resolve(token, now=now or self.clock())
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self.simulation_only:
                self._writer(db, scope, now)
            self.store.check_account(db, p, scope, "cancel")
            row = db.execute(
                "SELECT client_id FROM broker_ids WHERE tenant=? AND account=? AND broker_id=?",
                (scope.tenant, scope.account, broker_id),
            ).fetchone()
            if not row:
                raise PermissionError("Unknown account-bound order")
            state = db.execute(
                "SELECT state FROM outbox WHERE client_id=?", (row[0],)
            ).fetchone()[0]
            if state not in {"ACCEPTED", "PARTIAL"}:
                raise PermissionError("Order not cancellable without reconciliation")
            if transport.account != scope.account or transport.mode != "PAPER":
                raise PermissionError("Wrong paper transport")
            db.execute(
                "UPDATE outbox SET state='CANCEL_PENDING' WHERE client_id=?", (row[0],)
            )
        try:
            transport.cancel(broker_id)
        except Exception:
            with self.store.connect() as db:
                db.execute(
                    "UPDATE outbox SET state='UNKNOWN' WHERE client_id=?", (row[0],)
                )
                db.execute(
                    "UPDATE accounts SET frozen=1 WHERE tenant=? AND account=?",
                    (scope.tenant, scope.account),
                )
            raise
        return "CANCEL_PENDING"

    def event(self, token, scope, event, *, now=None):
        now = now or self.clock()
        self.sessions.resolve(token, now=now).require(scope, "reconcile")
        try:
            return self._record_event(token, scope, event, now=now)
        except FencedOut:
            raise
        except (ValueError, KeyError, PermissionError):
            # The event transaction has rolled back. An unresolved broker event
            # must invalidate the prior apparently healthy account snapshot.
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "UPDATE accounts SET frozen=1 WHERE tenant=? AND account=?",
                    (scope.tenant, scope.account),
                )
                db.execute(
                    "DELETE FROM account_reconciliation WHERE tenant=? AND account=?",
                    (scope.tenant, scope.account),
                )
                db.execute(
                    "INSERT INTO managed_incidents(tenant,account,as_of,reason) VALUES (?,?,?,?)",
                    (
                        scope.tenant,
                        scope.account,
                        now.isoformat(),
                        "BROKER_EVENT_REVIEW_REQUIRED",
                    ),
                )
            raise

    def _record_event(self, token, scope, event, *, now=None):
        identifier(event.get("event_id"))
        identifier(event.get("broker_id"))
        p = self.sessions.resolve(token, now=now or self.clock())
        if (event.get("tenant"), event.get("account")) != (scope.tenant, scope.account):
            raise PermissionError("Broker event/account mismatch")
        status = event["status"]
        if status not in {
            "ACCEPTED",
            "PARTIAL",
            "FILLED",
            "CANCEL_PENDING",
            "CANCELLED",
            "REJECTED",
        }:
            raise ValueError("Unknown broker status")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self.simulation_only:
                self._writer(db, scope, now)
            self.store.check_account(db, p, scope, "reconcile")
            old = db.execute(
                "SELECT sha FROM broker_events WHERE tenant=? AND account=? AND event_id=?",
                (scope.tenant, scope.account, event["event_id"]),
            ).fetchone()
            digest = fingerprint(event)
            if old:
                if old[0] != digest:
                    raise ValueError("Conflicting execution event")
                return "DUPLICATE"
            row = db.execute(
                "SELECT client_id,filled FROM broker_ids WHERE tenant=? AND account=? AND broker_id=?",
                (scope.tenant, scope.account, event["broker_id"]),
            ).fetchone()
            if not row:
                raise PermissionError("Unknown broker order/account")
            order = db.execute(
                "SELECT body,state FROM outbox WHERE client_id=?", (row[0],)
            ).fetchone()
            cumulative = amount(event["cumulative_filled"])
            quantity = amount(json.loads(order[0])["quantity"])
            if not amount(row[1]) <= cumulative <= quantity:
                raise ValueError("Regressive or excess fill")
            if status == "FILLED" and cumulative != quantity:
                raise ValueError("Incomplete filled event")
            if order[1] == "FILLED" and status != "FILLED":
                raise ValueError("Terminal status regression")
            if order[1] in {"CANCELLED", "REJECTED"} and status != "FILLED":
                raise ValueError("Terminal status regression")
            if status == "PARTIAL" and not 0 < cumulative < quantity:
                raise ValueError("Invalid partial fill")
            if json.loads(order[0]).get("accounting_required"):
                if (
                    cumulative > amount(row[1])
                    and date.fromisoformat(event["trade_date"])
                    > (now or self.clock()).date()
                ):
                    raise ValueError("Future trade date")
                managed_positions.apply_fill(
                    db, scope, row[0], json.loads(order[0]), event, row[1]
                )
                if amount(event.get("cumulative_fee", "0")) > amount(
                    json.loads(order[0])["fee_buffer"]
                ):
                    db.execute(
                        "UPDATE accounts SET frozen=1 WHERE tenant=? AND account=?",
                        (scope.tenant, scope.account),
                    )
                    db.execute(
                        "INSERT INTO managed_incidents(tenant,account,as_of,reason) VALUES (?,?,?,?)",
                        (
                            scope.tenant,
                            scope.account,
                            (now or self.clock()).isoformat(),
                            "FEE_BUFFER_BREACH_REVIEW_REQUIRED",
                        ),
                    )
            db.execute(
                "INSERT INTO broker_events VALUES (?,?,?,?,?)",
                (
                    scope.tenant,
                    scope.account,
                    event["event_id"],
                    canonical(event),
                    digest,
                ),
            )
            db.execute(
                "UPDATE broker_ids SET filled=? WHERE client_id=?",
                (str(cumulative), row[0]),
            )
            db.execute("UPDATE outbox SET state=? WHERE client_id=?", (status, row[0]))
            # Any fill/reject/cancel changes exposure or cash; require a new snapshot.
            if status != "ACCEPTED":
                db.execute(
                    "DELETE FROM account_reconciliation WHERE tenant=? AND account=?",
                    (scope.tenant, scope.account),
                )
        return "RECORDED"

    def account_book(self, token, scope, *, now=None):
        now = now or self.clock()
        p = self.sessions.resolve(token, now=now)
        with self.store.connect() as db:
            self.store.check_account(db, p, scope, "read")
            cash, settled, available = managed_positions.cash_state(db, scope)
            positions = {
                symbol: qty
                for symbol, qty in db.execute(
                    "SELECT instrument,quantity FROM managed_positions WHERE tenant=? AND account=?",
                    (scope.tenant, scope.account),
                )
                if amount(qty) != 0
            }
            orders = [
                r[0]
                for r in db.execute(
                    "SELECT b.broker_id FROM broker_ids b JOIN outbox o ON b.client_id=o.client_id WHERE b.tenant=? AND b.account=? AND o.state IN ('ACCEPTED','PARTIAL','CANCEL_PENDING')",
                    (scope.tenant, scope.account),
                )
            ]
        return dict(
            tenant=scope.tenant,
            account=scope.account,
            as_of=now.isoformat(),
            cash={c: str(v) for c, v in cash.items()},
            settled_cash={c: str(v) for c, v in settled.items()},
            available_cash={c: str(v) for c, v in available.items()},
            positions=positions,
            open_orders=sorted(orders),
            corporate_actions=[],
        )

    def _writer(self, db, scope, now):
        if self.writer_lease is None:
            from writer_fencing import FencedOut

            raise FencedOut("Active writer lease required")
        self.writer_lease.check(db, scope, now)

    def _portfolio_envelope(self, db, scope, client_id, intent, now, phase):
        from managed_portfolio_risk import review

        cash, _, _ = managed_positions.cash_state(db, scope)
        positions = {
            i: dict(quantity=q, currency=c)
            for i, q, c in db.execute(
                "SELECT instrument,quantity,currency FROM managed_positions WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            )
            if amount(q) != 0
        }
        pending = []
        for cid, body, digest, state in db.execute(
            "SELECT client_id,body,sha,state FROM outbox WHERE tenant=? AND account=?",
            (scope.tenant, scope.account),
        ):
            if state in OPEN_STATES:
                if fingerprint(json.loads(body)) != digest:
                    raise ValueError("Pending exposure integrity failure")
                pending.append({**json.loads(body), "client_id": cid})
        today = {}
        for body, digest in db.execute(
            "SELECT body,sha FROM broker_events WHERE tenant=? AND account=?",
            (scope.tenant, scope.account),
        ):
            event = json.loads(body)
            if fingerprint(event) != digest:
                raise ValueError("Broker event history integrity failure")
            if event.get("trade_date") == now.date().isoformat():
                original = db.execute(
                    "SELECT o.body FROM broker_ids b JOIN outbox o ON o.client_id=b.client_id WHERE b.tenant=? AND b.account=? AND b.broker_id=?",
                    (scope.tenant, scope.account, event["broker_id"]),
                ).fetchone()
                if (
                    original is None
                    or json.loads(original[0])["currency"] != intent["currency"]
                ):
                    raise PermissionError("Unqualified daily cross-currency turnover")
                today[event["broker_id"]] = max(
                    today.get(event["broker_id"], Decimal(0)),
                    amount(event.get("cumulative_notional", "0")),
                )
        request = dict(
            tenant=scope.tenant,
            account=scope.account,
            client_id=client_id,
            positions=positions,
            cash={c: str(v) for c, v in cash.items()},
            pending=pending,
            traded_today=str(sum(today.values(), Decimal(0))),
            proposed=intent,
        )
        result = review(request, self.portfolio_risk_reader, intent["permit"], now)
        record = dict(phase=phase, request=request, result=result)
        db.execute(
            "INSERT INTO portfolio_risk_reviews(tenant,account,client_id,body,sha) VALUES (?,?,?,?,?)",
            (
                scope.tenant,
                scope.account,
                client_id,
                canonical(record),
                fingerprint(record),
            ),
        )
        return result

    def _production_risk(self, client_id, permit, contract, quantity, price, side):
        from authorizedorderintent import AuthorizedOrderIntent

        if self.authorization_reader is None:
            raise PermissionError("Production risk authorization provider required")
        artifact = self.authorization_reader(client_id)
        if (
            type(artifact) is not AuthorizedOrderIntent
            or artifact.validate() is not True
        ):
            raise PermissionError("Validated production AuthorizedOrderIntent required")
        order = artifact.order
        if (
            order.order_id != client_id
            or order.ticker != permit.get("instrument_symbol")
            or order.side != side
            or order.order_type != "LIMIT"
            or order.time_in_force != "DAY"
            or amount(str(order.quantity)) != amount(quantity)
            or amount(str(order.limit_price)) != amount(price)
        ):
            raise PermissionError("Production authorization/order dimensions mismatch")
        if contract is not None and contract.contract_id != permit.get("instrument_id"):
            raise PermissionError("Production authorization/instrument binding missing")
        # Status/fill fields legitimately change through OMS. Bind immutable
        # order dimensions and the original risk authorization, not lifecycle state.
        return fingerprint(
            dict(
                decision_id=artifact.decision_id,
                regime=artifact.regime,
                authorization=artifact.authorization.to_dict(),
                order={
                    k: getattr(order, k)
                    for k in (
                        "order_id",
                        "ticker",
                        "side",
                        "quantity",
                        "order_type",
                        "limit_price",
                        "stop_price",
                        "time_in_force",
                    )
                },
            )
        )
