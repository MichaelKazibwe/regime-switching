"""Account-isolated paper foundation for a future managed-account service.

No broker transport, live authorization or public identity provider is exposed.
Principals must eventually be derived from a verified authentication service.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
import json
import os
from pathlib import Path
import sqlite3

from strategy_integrity import canonical, fingerprint


def identifier(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError("Nonempty bounded identifier required")
    return value


def amount(value):
    if not isinstance(value, str):
        raise ValueError("Decimal amounts must be strings")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid amount") from None
    if (
        not result.is_finite()
        or result.copy_abs() > Decimal("1e15")
        or result.as_tuple().exponent < -8
    ):
        raise ValueError("Finite bounded amount with at most eight decimals required")
    return result


def exact_add(left, right):
    with localcontext() as ctx:
        ctx.prec = 60
        return left + right


@dataclass(frozen=True)
class AccountScope:
    tenant: str
    account: str

    def validate(self):
        identifier(self.tenant)
        identifier(self.account)
        return self


@dataclass(frozen=True)
class Principal:
    subject: str
    # Explicit account/action grants; no wildcard or implicit administrator access.
    grants: frozenset[tuple[str, str, str]]

    def require(self, scope, action):
        scope.validate()
        identifier(self.subject)
        if (scope.tenant, scope.account, action) not in self.grants:
            raise PermissionError("Account permission denied")


@dataclass(frozen=True)
class InstrumentContract:
    broker: str
    broker_entity: str
    contract_id: str
    venue: str
    currency: str
    quote_unit: str
    quote_to_currency: str
    lot: str
    tick: str
    asset_type: str = "STOCK"

    def validate(self):
        for value in (self.broker, self.broker_entity, self.contract_id, self.venue):
            identifier(value)
        if (
            len(self.currency) != 3
            or not self.currency.isalpha()
            or not self.currency.isupper()
        ):
            raise ValueError("Uppercase currency code required")
        if self.asset_type not in {"STOCK", "ETF"}:
            raise ValueError("FX and futures need separate qualified contracts")
        if self.quote_unit not in {self.currency, "GBX"}:
            raise ValueError("Unknown quote unit")
        expected = Decimal("0.01") if self.quote_unit == "GBX" else Decimal("1")
        if self.quote_unit == "GBX" and self.currency != "GBP":
            raise ValueError("GBX must settle in GBP")
        if amount(self.quote_to_currency) != expected:
            raise ValueError("Invalid quote conversion")
        if amount(self.lot) <= 0 or amount(self.tick) <= 0:
            raise ValueError("Positive lot and tick required")
        return self

    def validate_order(self, quantity, price):
        self.validate()
        q, p = amount(quantity), amount(price)
        with localcontext() as ctx:
            ctx.prec = 60
            if q <= 0 or p <= 0 or q % amount(self.lot) or p % amount(self.tick):
                raise ValueError("Order violates quantity/price increments")
            return q * p * amount(self.quote_to_currency)


class ManagedPaperStore:
    """SQLite single-writer transactions, exact cash journals and paper outbox.

    Direct filesystem access is trusted. This is not a replacement for API
    authentication, signed mandates, encrypted custody or broker reconciliation.
    """

    def __init__(self, path):
        self.path = Path(path)
        if self.path.is_symlink():
            raise ValueError("Regular database required")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    tenant TEXT, account TEXT, frozen INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(tenant, account));
                CREATE TABLE IF NOT EXISTS journals (
                    tenant TEXT, account TEXT, event TEXT, body TEXT NOT NULL, sha TEXT NOT NULL,
                    PRIMARY KEY(tenant, account, event));
                CREATE TABLE IF NOT EXISTS outbox (
                    client_id TEXT PRIMARY KEY, tenant TEXT, account TEXT,
                    body TEXT NOT NULL, sha TEXT NOT NULL, state TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS immutable_journals_update
                BEFORE UPDATE ON journals BEGIN SELECT RAISE(ABORT,'Immutable journal'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_journals_delete
                BEFORE DELETE ON journals BEGIN SELECT RAISE(ABORT,'Immutable journal'); END;
            """)
        os.chmod(self.path, 0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA synchronous=FULL")
        return db

    def create_account(self, scope):
        """Trusted provisioning only; new accounts start frozen."""
        scope.validate()
        with self.connect() as db:
            db.execute(
                "INSERT INTO accounts(tenant,account) VALUES (?,?)",
                (scope.tenant, scope.account),
            )

    @staticmethod
    def check_account(db, principal, scope, action):
        principal.require(scope, action)
        row = db.execute(
            "SELECT frozen FROM accounts WHERE tenant=? AND account=?",
            (scope.tenant, scope.account),
        ).fetchone()
        if row is None:
            raise PermissionError("Unknown account")
        return bool(row[0])

    def freeze(self, principal, scope):
        with self.connect() as db:
            self.check_account(db, principal, scope, "freeze")
            db.execute(
                "UPDATE accounts SET frozen=1 WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            )

    def enable_paper(self, principal, scope):
        with self.connect() as db:
            self.check_account(db, principal, scope, "enable_paper")
            db.execute(
                "UPDATE accounts SET frozen=0 WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            )

    def post(self, principal, scope, event, entries):
        """Balanced per currency; cross-currency sums are never netted."""
        identifier(event)
        totals = {}
        if not isinstance(entries, list) or not 1 <= len(entries) <= 1000:
            raise ValueError("Between one and 1000 journal entries required")
        for entry in entries:
            if set(entry) != {"ledger", "currency", "amount"}:
                raise ValueError("Exact journal schema required")
            identifier(entry["ledger"])
            currency = entry["currency"]
            if (
                not isinstance(currency, str)
                or len(currency) != 3
                or not currency.isalpha()
                or not currency.isupper()
            ):
                raise ValueError("Currency required")
            totals[currency] = exact_add(
                totals.get(currency, Decimal(0)), amount(entry["amount"])
            )
        if any(totals.values()):
            raise ValueError("Journal must balance separately in each currency")
        body, digest = canonical(entries), fingerprint(entries)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.check_account(db, principal, scope, "journal")
            old = db.execute(
                "SELECT sha FROM journals WHERE tenant=? AND account=? AND event=?",
                (scope.tenant, scope.account, event),
            ).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError("Conflicting journal replay")
                return "ALREADY_POSTED"
            db.execute(
                "INSERT INTO journals VALUES (?,?,?,?,?)",
                (scope.tenant, scope.account, event, body, digest),
            )
        return "POSTED"

    def balances(self, principal, scope):
        totals = {}
        with self.connect() as db:
            self.check_account(db, principal, scope, "read")
            rows = db.execute(
                "SELECT body,sha FROM journals WHERE tenant=? AND account=?",
                (scope.tenant, scope.account),
            ).fetchall()
        for body, digest in rows:
            entries = json.loads(body)
            if fingerprint(entries) != digest:
                raise ValueError("Journal integrity failure")
            for entry in entries:
                key = (entry["ledger"], entry["currency"])
                totals[key] = exact_add(
                    totals.get(key, Decimal(0)), amount(entry["amount"])
                )
        return totals

    def enqueue(self, principal, scope, client_id, intent):
        """Persist a paper intent; never submit it or treat it as authorization."""
        identifier(client_id)
        if (
            intent.get("mode") != "PAPER"
            or intent.get("execution_enabled") is not False
        ):
            raise ValueError("Only non-executable paper intents supported")
        if (
            intent.get("tenant") != scope.tenant
            or intent.get("account") != scope.account
        ):
            raise ValueError("Intent/account mismatch")
        for name in ("instrument_id", "mandate_id", "release_id", "authorization_id"):
            identifier(intent.get(name))
        body, digest = canonical(intent), fingerprint(intent)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.check_account(db, principal, scope, "enqueue"):
                raise PermissionError("Account frozen")
            old = db.execute(
                "SELECT tenant,account,sha FROM outbox WHERE client_id=?", (client_id,)
            ).fetchone()
            if old:
                if old != (scope.tenant, scope.account, digest):
                    raise ValueError("Conflicting client order identifier")
                return "ALREADY_QUEUED"
            db.execute(
                "INSERT INTO outbox VALUES (?,?,?,?,?,?)",
                (client_id, scope.tenant, scope.account, body, digest, "PAPER_PENDING"),
            )
        return "PAPER_QUEUED"
