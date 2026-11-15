from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from managed_accounts import Principal, AccountScope, InstrumentContract
from managed_boundary import (
    PaperSessions,
    eligible_paper_order,
    fair_lot_allocation,
    cash_nav,
    pilot_readiness,
)

NOW = datetime(2026, 11, 2, 16, tzinfo=timezone.utc)


def test_opaque_sessions_expire_revoke_and_cannot_change_account_grants():
    registry = PaperSessions()
    scope = AccountScope("t", "a")
    token = registry.issue(
        Principal("operator", frozenset({("t", "a", "enqueue")})), now=NOW
    )
    registry.resolve(token, now=NOW).require(scope, "enqueue")
    with pytest.raises(PermissionError):
        registry.resolve(token, now=NOW).require(AccountScope("t", "other"), "enqueue")
    with pytest.raises(PermissionError):
        registry.resolve(token, now=NOW + timedelta(minutes=15))
    registry.revoke(token)
    with pytest.raises(PermissionError):
        registry.resolve(token, now=NOW)


def test_eligibility_defaults_deny_and_quotes_cannot_be_stale_or_wrong():
    registry = PaperSessions()
    token = registry.issue(
        Principal("operator", frozenset({("t", "a", "enqueue")})), now=NOW
    )
    contract = InstrumentContract(
        "paper", "unverified", "id", "XNYS", "USD", "USD", "1", "1", "0.01"
    )
    quote = dict(
        instrument_id="id", currency="USD", ask="100.01", as_of=NOW.isoformat()
    )

    def check(**kwargs):
        return eligible_paper_order(
            registry,
            token,
            AccountScope("t", "a"),
            contract,
            kwargs.pop("quote", quote),
            "2",
            client_country="MU",
            now=NOW,
            **kwargs,
        )

    with pytest.raises(PermissionError):
        check()
    assert check(allowed_countries=("MU",))[1] == Decimal("200.02")
    with pytest.raises(ValueError):
        check(allowed_countries=("MU",), quote={**quote, "currency": "GBP"})
    with pytest.raises(ValueError):
        check(
            allowed_countries=("MU",),
            quote={**quote, "as_of": (NOW - timedelta(seconds=31)).isoformat()},
        )


def test_allocation_is_conservative_and_independent_of_dict_order():
    budgets = {"founder": "1", "client-a": "1", "client-b": "1"}
    a = fair_lot_allocation(5, budgets)
    assert a == fair_lot_allocation(5, dict(reversed(list(budgets.items()))))
    assert sum(a.values()) == 5 and a["founder"] == 1
    assert fair_lot_allocation(1, {"zero": "0", "funded": "1"})["zero"] == 0


def test_currency_cash_nav_requires_fresh_direct_rate():
    balances = {"USD": "100", "GBP": "50"}
    fx = {
        ("GBP", "USD"): dict(
            rate="1.25", as_of=NOW.isoformat(), source="synthetic-test"
        )
    }
    assert cash_nav(balances, "USD", fx, now=NOW) == Decimal("162.50")
    with pytest.raises(ValueError):
        cash_nav(balances, "USD", {}, now=NOW)
    with pytest.raises(ValueError):
        cash_nav(balances, "USD", fx, now=NOW + timedelta(minutes=6))


def test_client_and_founder_gates_cannot_authorize_trades():
    founder = pilot_readiness(account_kind="FOUNDER", evidence={})
    client = pilot_readiness(account_kind="CLIENT", evidence={})
    assert set(founder["required_reviews"]) < set(client["required_reviews"])
    assert not client["execution_enabled"] and not founder["execution_enabled"]
    assert (
        pilot_readiness(
            account_kind="CLIENT",
            evidence={k: True for k in client["required_reviews"]},
        )["release_approved"]
        is False
    )


def test_gbp_pence_quote_requires_explicit_unit():
    registry = PaperSessions()
    token = registry.issue(
        Principal("operator", frozenset({("t", "a", "enqueue")})), now=NOW
    )
    contract = InstrumentContract(
        "paper", "unverified", "id", "XLON", "GBP", "GBX", "0.01", "1", "0.5"
    )
    quote = dict(instrument_id="id", currency="GBP", ask="100", as_of=NOW.isoformat())
    with pytest.raises(ValueError):
        eligible_paper_order(
            registry,
            token,
            AccountScope("t", "a"),
            contract,
            quote,
            "1",
            client_country="MU",
            allowed_countries=("MU",),
            now=NOW,
        )
    assert eligible_paper_order(
        registry,
        token,
        AccountScope("t", "a"),
        contract,
        {**quote, "quote_unit": "GBX"},
        "1",
        client_country="MU",
        allowed_countries=("MU",),
        now=NOW,
    )[1] == Decimal("1")
