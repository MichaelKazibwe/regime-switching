"""BrokerTransport bridge: only previously prepared account-bound PAPER intents."""

import json
from livebroker import BrokerTransport
from managed_accounts import amount


class ManagedPaperTransport(BrokerTransport):
    def __init__(self, engine, token, scope, adapter, symbols):
        self.engine, self.token, self.scope, self.adapter, self.symbols = (
            engine,
            token,
            scope,
            adapter,
            dict(symbols),
        )
        self.connected = False

    def connect(self):
        if self.adapter.account != self.scope.account or self.adapter.mode != "PAPER":
            raise PermissionError("Paper account mismatch")
        self.adapter.confirm_paper()
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False
        return True

    def authenticate(self):
        return self.connect()

    def health_check(self):
        return self.connected

    def submit_order(self, order):
        if not self.connected:
            raise PermissionError("Paper transport disconnected")
        order.validate()
        with self.engine.store.connect() as db:
            row = db.execute(
                "SELECT body FROM outbox WHERE tenant=? AND account=? AND client_id=?",
                (self.scope.tenant, self.scope.account, order.order_id),
            ).fetchone()
        if not row:
            raise PermissionError("Unprepared order")
        intent = json.loads(row[0])
        if (
            (order.order_type, order.side, order.time_in_force)
            != ("LIMIT", intent["side"], "DAY")
            or self.symbols.get(order.ticker) != intent["instrument_id"]
            or amount(str(order.quantity)) != amount(intent["quantity"])
            or amount(str(order.limit_price)) != amount(intent["price"])
        ):
            raise PermissionError("Order differs from prepared paper intent")
        receipt = self.engine.dispatch(
            self.token, self.scope, order.order_id, self.adapter
        )
        return dict(
            broker_order_id=receipt["broker_id"],
            client_order_id=order.order_id,
            status="ACCEPTED",
            filled_quantity=0.0,
            average_fill_price=0.0,
        )

    def cancel_order(self, broker_order_id):
        status = self.engine.cancel(
            self.token, self.scope, str(broker_order_id), self.adapter
        )
        return dict(broker_order_id=str(broker_order_id), status=status)

    def get_order(self, broker_order_id):
        p = self.engine.sessions.resolve(self.token, now=self.engine.clock())
        with self.engine.store.connect() as db:
            self.engine.store.check_account(db, p, self.scope, "read")
            row = db.execute(
                "SELECT b.client_id,b.filled,o.state FROM broker_ids b JOIN outbox o ON b.client_id=o.client_id WHERE b.tenant=? AND b.account=? AND b.broker_id=?",
                (self.scope.tenant, self.scope.account, str(broker_order_id)),
            ).fetchone()
        if not row:
            raise PermissionError("Unknown account-bound broker order")
        return dict(
            broker_order_id=str(broker_order_id),
            client_order_id=row[0],
            filled_quantity=float(amount(row[1])),
            status=row[2],
            view="LOCAL_EVENT_STATE_NOT_A_FRESH_BROKER_QUERY",
        )
