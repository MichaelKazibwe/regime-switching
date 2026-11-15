"""Paper freeze/resume and heartbeat controls; no live authority or email sender."""

from datetime import datetime, timezone, timedelta
import json
from managed_execution import verify_permit
from strategy_integrity import fingerprint


class ManagedOperations:
    def __init__(self, engine):
        self.engine = engine

    def freeze(self, token, scope, *, now=None):
        p = self.engine.sessions.resolve(token, now=now or self.engine.clock())
        self.engine.store.freeze(p, scope)
        return dict(status="FROZEN", orders_cancelled=False, execution_enabled=False)

    def resume_paper(self, token, scope, permit, signature, *, now=None):
        now = now or self.engine.clock()
        e = self.engine
        p = e.sessions.resolve(token, now=now)
        verify_permit(
            permit, signature, e.key, scope, e.release_id, e.image_digest, now=now
        )
        with e.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not e.simulation_only:
                e._writer(db, scope, now)
            e.store.check_account(db, p, scope, "enable_paper")
            unresolved = db.execute(
                "SELECT COUNT(*) FROM outbox WHERE tenant=? AND account=? AND state IN ('UNKNOWN','DISPATCHING','CANCEL_PENDING')",
                (scope.tenant, scope.account),
            ).fetchone()[0]
            row = db.execute(
                "SELECT body,sha FROM account_reconciliation WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            ).fetchone()
            if unresolved or not row:
                raise PermissionError("Reconcile unresolved orders before resume")
            report = json.loads(row[0])
            stamp = datetime.fromisoformat(report["as_of"])
            if (
                fingerprint(report) != row[1]
                or report["status"] != "MATCHED"
                or not timedelta(0) <= now - stamp <= timedelta(seconds=60)
            ):
                raise PermissionError("Fresh matched reconciliation required")
            db.execute(
                "UPDATE accounts SET frozen=0 WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            )
        return dict(status="PAPER_RESUMED", execution_enabled=False)

    @staticmethod
    def heartbeat(record, *, now=None):
        now = now or datetime.now(timezone.utc)
        stamp = datetime.fromisoformat(record["as_of"])
        healthy = (
            stamp.tzinfo is not None
            and now.tzinfo is not None
            and timedelta(0) <= now - stamp <= timedelta(seconds=60)
            and record.get("reconciled") is True
            and record.get("transport_healthy") is True
        )
        return dict(
            status="HEALTHY_PAPER" if healthy else "ALERT_REQUIRED",
            external_delivery_verified=False,
            execution_enabled=False,
        )
