"""Internal authenticated paper boundary; no public login or live enablement."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import secrets

from managed_accounts import Principal, amount, exact_add


class PaperSessions:
    """Trusted issuer supplies grants; callers only present opaque tokens.

    Deliberately process-local: restart invalidates sessions. Not a substitute
    for production MFA/OIDC, durable revocation and security qualification.
    """

    def __init__(self):
        self._sessions = {}

    def issue(self, principal, *, now=None, lifetime=timedelta(minutes=15)):
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or not timedelta(0) < lifetime <= timedelta(minutes=15):
            raise ValueError("Aware clock and bounded session lifetime required")
        if not isinstance(principal, Principal):
            raise ValueError("Trusted principal required")
        token = secrets.token_urlsafe(32)
        self._sessions[hashlib.sha256(token.encode()).digest()] = (
            principal,
            now + lifetime,
            now,
        )
        return token

    def resolve(self, token, *, now=None):
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or not isinstance(token, str):
            raise PermissionError("Invalid session")
        record = self._sessions.get(hashlib.sha256(token.encode()).digest())
        if not record or not record[2] <= now < record[1]:
            raise PermissionError("Expired or invalid session")
        return record[0]

    def revoke(self, token):
        self._sessions.pop(hashlib.sha256(token.encode()).digest(), None)


def eligible_paper_order(
    session_registry,
    token,
    scope,
    contract,
    quote,
    quantity,
    *,
    client_country,
    allowed_countries=(),
    now=None,
):
    now = now or datetime.now(timezone.utc)
    principal = session_registry.resolve(token, now=now)
    principal.require(scope, "enqueue")
    if client_country not in allowed_countries:
        raise PermissionError("Client country not approved for this paper pilot")
    contract.validate()
    if (
        quote.get("instrument_id") != contract.contract_id
        or quote.get("currency") != contract.currency
        or quote.get("quote_unit", contract.currency) != contract.quote_unit
    ):
        raise ValueError("Quote/instrument mismatch")
    stamp = datetime.fromisoformat(quote["as_of"])
    if stamp.tzinfo is None or not timedelta(0) <= now - stamp <= timedelta(seconds=30):
        raise ValueError("Stale or future executable quote")
    return principal, contract.validate_order(quantity, quote["ask"])


def fair_lot_allocation(total_lots, budgets):
    """Pre-trade largest-remainder rule; lexical tie break, no founder override."""
    if (
        isinstance(total_lots, bool)
        or not isinstance(total_lots, int)
        or total_lots < 0
        or not budgets
    ):
        raise ValueError("Nonnegative lot count and account budgets required")
    values = {key: amount(value) for key, value in budgets.items()}
    if any(v < 0 for v in values.values()):
        raise ValueError("Negative budget")
    total = Decimal(0)
    for value in values.values():
        total = exact_add(total, value)
    if total <= 0:
        raise ValueError("Positive total budget required")
    from decimal import localcontext

    with localcontext() as ctx:
        ctx.prec = 60
        exact = {k: total_lots * v / total for k, v in values.items()}
        result = {k: int(v) for k, v in exact.items()}
        remaining = total_lots - sum(result.values())
        for key in sorted(values, key=lambda k: (-(exact[k] - result[k]), k))[
            :remaining
        ]:
            result[key] += 1
    return result


def cash_nav(balances, base_currency, fx, *, now=None):
    """Cash-only valuation, not portfolio NAV; direct rates need dated evidence."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Aware clock required")
    result = Decimal(0)
    from decimal import localcontext

    with localcontext() as ctx:
        ctx.prec = 60
        for currency, value in balances.items():
            balance = amount(value)
            if currency == base_currency:
                result = exact_add(result, balance)
                continue
            quote = fx.get((currency, base_currency))
            if not quote or not quote.get("source"):
                raise ValueError("Missing FX valuation evidence")
            stamp = datetime.fromisoformat(quote["as_of"])
            if stamp.tzinfo is None or not timedelta(0) <= now - stamp <= timedelta(
                minutes=5
            ):
                raise ValueError("Stale or future FX valuation")
            rate = amount(quote["rate"])
            if rate <= 0:
                raise ValueError("Positive FX rate required")
            result = exact_add(result, balance * rate)
    return result


def pilot_readiness(*, account_kind, evidence):
    """Read-only decision support. Never returns an executable authorization."""
    required = {
        "clean_release",
        "qualified_image_host",
        "broker_sandbox",
        "reconciliation_recovery",
        "model_review",
        "observation",
        "owner_review",
    }
    if account_kind == "CLIENT":
        required |= {
            "licence_scope",
            "client_mandate",
            "identity_isolation",
            "client_country",
        }
    elif account_kind != "FOUNDER":
        raise ValueError("Explicit account kind required")
    # Evidence documents require an independent reviewer; booleans are not receipts.
    # Full external evidence validation remains the existing qualification tools.
    missing = sorted(required - set(evidence))
    return dict(
        status="BLOCKED_PENDING_QUALIFICATION",
        account_kind=account_kind,
        required_reviews=sorted(required),
        missing_evidence=missing,
        execution_enabled=False,
        release_approved=False,
    )
