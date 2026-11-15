from decimal import Decimal

import pytest

from managed_accounts import (
    AccountScope,
    Principal,
    ManagedPaperStore,
    InstrumentContract,
)


@pytest.fixture
def store(tmp_path):
    db = ManagedPaperStore(tmp_path / "accounts.sqlite3")
    a, b = AccountScope("firm-a", "account-1"), AccountScope("firm-b", "account-1")
    for scope in (a, b):
        db.create_account(scope)
    principal = Principal(
        "operator",
        frozenset(
            (a.tenant, a.account, action)
            for action in ("read", "journal", "enqueue", "freeze", "enable_paper")
        ),
    )
    return db, a, b, principal


def entries(currency="USD", value="100.01"):
    return [
        {"ledger": "cash", "currency": currency, "amount": value},
        {"ledger": "capital", "currency": currency, "amount": "-" + value},
    ]


def intent(scope):
    return dict(
        tenant=scope.tenant,
        account=scope.account,
        mode="PAPER",
        execution_enabled=False,
        instrument_id="contract-1",
        mandate_id="mandate-1",
        release_id="release-1",
        authorization_id="auth-1",
    )


def test_account_access_cannot_cross_tenant_even_with_same_account_id(store):
    db, a, b, p = store
    db.post(p, a, "deposit", entries())
    assert db.balances(p, a)[("cash", "USD")] == Decimal("100.01")
    for call in (
        lambda: db.balances(p, b),
        lambda: db.post(p, b, "x", entries()),
        lambda: db.enable_paper(p, b),
        lambda: db.freeze(p, b),
    ):
        with pytest.raises(PermissionError):
            call()


def test_currency_balance_and_replay_are_exact(store):
    db, a, _, p = store
    assert db.post(p, a, "x", entries()) == "POSTED"
    assert db.post(p, a, "x", entries()) == "ALREADY_POSTED"
    with pytest.raises(ValueError, match="Conflicting"):
        db.post(p, a, "x", entries(value="100.02"))
    with pytest.raises(ValueError, match="separately"):
        db.post(p, a, "bad", [entries()[0], entries("GBP")[1]])
    assert db.balances(p, a)[("cash", "USD")] == Decimal("100.01")


def test_frozen_and_nonpaper_intents_cannot_enqueue(store):
    db, a, b, p = store
    with pytest.raises(PermissionError, match="frozen"):
        db.enqueue(p, a, "id", intent(a))
    db.enable_paper(p, a)
    assert db.enqueue(p, a, "id", intent(a)) == "PAPER_QUEUED"
    assert db.enqueue(p, a, "id", intent(a)) == "ALREADY_QUEUED"
    with pytest.raises(ValueError):
        db.enqueue(p, a, "other", {**intent(a), "mode": "LIVE"})
    with pytest.raises(ValueError):
        db.enqueue(p, a, "other", intent(b))
    with pytest.raises(ValueError, match="Conflicting"):
        db.enqueue(p, a, "id", {**intent(a), "instrument_id": "another"})
    db.freeze(p, a)
    with pytest.raises(PermissionError):
        db.enqueue(p, a, "id2", intent(a))


def test_reopened_database_retains_journal_and_order_identity(store):
    db, a, _, p = store
    db.post(p, a, "x", entries())
    db.enable_paper(p, a)
    db.enqueue(p, a, "id", intent(a))
    reopened = ManagedPaperStore(db.path)
    assert reopened.balances(p, a)[("cash", "USD")] == Decimal("100.01")
    assert reopened.enqueue(p, a, "id", intent(a)) == "ALREADY_QUEUED"


def test_quote_units_board_lots_and_ticks():
    contract = InstrumentContract(
        "candidate", "unverified", "1", "XLON", "GBP", "GBX", "0.01", "100", "0.5"
    )
    assert contract.validate_order("100", "125.5") == Decimal("125.500")
    for q, price in [("1", "125.5"), ("100", "125.1"), ("NaN", "100"), ("-100", "100")]:
        with pytest.raises(ValueError):
            contract.validate_order(q, price)


@pytest.mark.parametrize(
    "value", ["NaN", "Infinity", "1e-100", "1000000000000001", 1.2]
)
def test_nonexact_or_unbounded_journals_rejected(store, value):
    db, a, _, p = store
    rows = entries()
    rows[0]["amount"] = value
    with pytest.raises(ValueError):
        db.post(p, a, "bad", rows)


def test_journal_sql_mutation_is_rejected(store):
    import sqlite3

    db, a, _, p = store
    db.post(p, a, "x", entries())
    with db.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="Immutable"):
            connection.execute("DELETE FROM journals")


def test_cash_precision_does_not_depend_on_callers_decimal_context(store):
    from decimal import localcontext

    db, a, _, p = store
    with localcontext() as ctx:
        ctx.prec = 3
        db.post(p, a, "x", entries(value="100.12345678"))
        assert db.balances(p, a)[("cash", "USD")] == Decimal("100.12345678")
