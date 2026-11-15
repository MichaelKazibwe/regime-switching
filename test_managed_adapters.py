from datetime import timedelta
import pytest
from managed_adapters import raw_quote, normalize_paper_account
from test_managed_execution import NOW
from managed_accounts import AccountScope, InstrumentContract


def test_adjusted_prices_cannot_be_promoted_to_execution_quotes():
    c = InstrumentContract(
        "IBKR", "TEST", "123", "XNYS", "USD", "USD", "1", "1", "0.01"
    )
    q = dict(
        kind="RAW_BID_ASK",
        instrument_id="123",
        currency="USD",
        source="TEST",
        as_of=NOW.isoformat(),
        bid="99",
        ask="100",
    )
    assert (
        raw_quote(lambda *_: q, AccountScope("t", "DU123"), c, now=NOW)["basis"]
        == "UNADJUSTED_EXECUTABLE"
    )
    with pytest.raises(ValueError):
        raw_quote(
            lambda *_: {**q, "kind": "ADJUSTED_CLOSE"},
            AccountScope("t", "DU123"),
            c,
            now=NOW,
        )


def test_snapshot_preserves_settled_cash_and_requires_actual_action_review():
    s = dict(
        status="READ_ONLY_PAPER_SNAPSHOT_UNQUALIFIED",
        account="DU123",
        captured_at=NOW.isoformat(),
        ledger={
            "USD": dict(acctcode="DU123", cashbalance=100, settledcash=80),
            "BASE": dict(acctcode="DU123", cashbalance=100, settledcash=80),
        },
        positions=[dict(acctId="DU123", conid=123, position=2)],
    )
    normalized = normalize_paper_account(
        s, AccountScope("t", "DU123"), [], NOW.isoformat(), now=NOW
    )
    assert normalized["settled_cash"] == {"USD": "80"} and normalized["cash"] == {
        "USD": "100"
    }
    assert normalized["corporate_actions"] is None
    with pytest.raises(ValueError):
        normalize_paper_account(
            s,
            AccountScope("t", "DU123"),
            [],
            NOW.isoformat(),
            now=NOW + timedelta(minutes=2),
        )
