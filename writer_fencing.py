"""Account-scoped monotonic SQLite writer leases, never broker-side fencing."""

from dataclasses import dataclass
from datetime import timedelta, datetime


class FencedOut(PermissionError):
    pass


def initialize(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS writer_leases(tenant TEXT,account TEXT,owner TEXT,epoch INTEGER,expires TEXT,PRIMARY KEY(tenant,account))"
    )


@dataclass(frozen=True)
class WriterLease:
    tenant: str
    account: str
    owner: str
    epoch: int

    def check(self, db, scope, now):
        row = db.execute(
            "SELECT owner,epoch,expires FROM writer_leases WHERE tenant=? AND account=?",
            (scope.tenant, scope.account),
        ).fetchone()
        if (
            (scope.tenant, scope.account) != (self.tenant, self.account)
            or not row
            or tuple(row[:2]) != (self.owner, self.epoch)
            or now.tzinfo is None
            or now >= datetime.fromisoformat(row[2])
        ):
            raise FencedOut("Expired, superseded or wrong-account writer")


def claim(store, scope, owner, *, now, seconds=60):
    scope.validate()
    if (
        now.tzinfo is None
        or not isinstance(owner, str)
        or not owner.strip()
        or not 1 <= seconds <= 120
    ):
        raise ValueError("Aware clock, unique process owner and bounded lease required")
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        initialize(db)
        if not db.execute(
            "SELECT 1 FROM accounts WHERE tenant=? AND account=?",
            (scope.tenant, scope.account),
        ).fetchone():
            raise FencedOut("Unknown account")
        row = db.execute(
            "SELECT owner,epoch,expires FROM writer_leases WHERE tenant=? AND account=?",
            (scope.tenant, scope.account),
        ).fetchone()
        if row and now < datetime.fromisoformat(row[2]):
            raise FencedOut("Writer lease already active; renew the existing token")
        if db.execute(
            "SELECT COUNT(*) FROM outbox WHERE tenant=? AND account=? AND state='DISPATCHING'",
            (scope.tenant, scope.account),
        ).fetchone()[0]:
            raise FencedOut("Quarantine/recover ambiguous dispatch before takeover")
        epoch = row[1] + 1 if row else 1
        db.execute(
            "INSERT INTO writer_leases VALUES(?,?,?,?,?) ON CONFLICT(tenant,account) DO UPDATE SET owner=excluded.owner,epoch=excluded.epoch,expires=excluded.expires",
            (
                scope.tenant,
                scope.account,
                owner,
                epoch,
                (now + timedelta(seconds=seconds)).isoformat(),
            ),
        )
    return WriterLease(scope.tenant, scope.account, owner, epoch)


def renew(store, lease, scope, *, now, seconds=60):
    if not 1 <= seconds <= 120:
        raise ValueError("Bounded lease required")
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        lease.check(db, scope, now)
        db.execute(
            "UPDATE writer_leases SET expires=? WHERE tenant=? AND account=? AND owner=? AND epoch=?",
            (
                (now + timedelta(seconds=seconds)).isoformat(),
                scope.tenant,
                scope.account,
                lease.owner,
                lease.epoch,
            ),
        )
