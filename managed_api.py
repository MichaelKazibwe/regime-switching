"""Authenticated account-scoped paper API boundary, with server-owned inputs.

No listener is started. Production TLS/MFA/OIDC and external qualification are
mandatory before exposing this boundary. Client data never supplies grants,
quotes, signed permits, broker snapshots, or transport objects.
"""

from managed_accounts import AccountScope
from managed_operations import ManagedOperations


class ManagedPaperAPI:
    def __init__(
        self,
        engine,
        *,
        instruments,
        quote_reader,
        permit_reader,
        transport_reader,
        broker_reader,
        local_reader,
    ):
        self.engine = engine
        self.instruments = dict(instruments)
        self.quote_reader, self.permit_reader = quote_reader, permit_reader
        self.transport_reader = transport_reader
        self.broker_reader, self.local_reader = broker_reader, local_reader

    def handle(self, token, request):
        if (
            not isinstance(request, dict)
            or set(request) != {"action", "tenant", "account", "payload"}
            or not isinstance(request["payload"], dict)
        ):
            raise ValueError("Exact API request envelope required")
        scope = AccountScope(request["tenant"], request["account"]).validate()
        e = self.engine
        principal = e.sessions.resolve(token, now=e.clock())
        action, payload = request["action"], request["payload"]
        permission = {
            "orders": "read",
            "prepare": "enqueue",
            "dispatch": "dispatch",
            "cancel": "cancel",
            "freeze": "freeze",
            "resume": "enable_paper",
            "reconcile": "reconcile",
        }.get(action)
        if not permission:
            raise PermissionError("Unknown paper operation")
        principal.require(scope, permission)
        if action == "orders":
            if payload:
                raise ValueError("No order read overrides allowed")
            with e.store.connect() as db:
                e.store.check_account(db, principal, scope, "read")
                rows = db.execute(
                    "SELECT client_id,state FROM outbox WHERE tenant=? AND account=? ORDER BY client_id",
                    (scope.tenant, scope.account),
                ).fetchall()
            return dict(
                mode="PAPER",
                execution_enabled=False,
                orders=[dict(client_id=r[0], state=r[1]) for r in rows],
            )
        if action == "prepare":
            if not {"instrument_id", "quantity", "client_id"} <= set(payload) or set(
                payload
            ) - {"instrument_id", "quantity", "client_id", "side", "reduce_only"}:
                raise ValueError("Client cannot override quote, permit or grants")
            contract = self.instruments[payload["instrument_id"]]
            permit, signature = self.permit_reader(scope)
            return e.prepare(
                token,
                scope,
                payload["client_id"],
                contract,
                self.quote_reader(scope, contract),
                payload["quantity"],
                permit,
                signature,
                side=payload.get("side", "BUY"),
                reduce_only=payload.get("reduce_only", False),
            )
        if action == "dispatch":
            if set(payload) != {"client_id"}:
                raise ValueError("Single prepared client ID required")
            return e.dispatch(
                token, scope, payload["client_id"], self.transport_reader(scope)
            )
        if action == "cancel":
            if set(payload) != {"broker_id"}:
                raise ValueError("Single bound broker ID required")
            return e.cancel(
                token, scope, payload["broker_id"], self.transport_reader(scope)
            )
        if payload:
            raise ValueError("No operational input overrides allowed")
        if action == "freeze":
            return ManagedOperations(e).freeze(token, scope, now=e.clock())
        if action == "resume":
            permit, signature = self.permit_reader(scope)
            return ManagedOperations(e).resume_paper(token, scope, permit, signature)
        return e.reconcile(
            token, scope, self.broker_reader(scope), self.local_reader(scope)
        )
