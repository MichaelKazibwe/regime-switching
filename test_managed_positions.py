from datetime import timedelta
import hashlib
import hmac
import pytest
from test_managed_execution import system, NOW, adapter, prepare  # noqa: F401
from strategy_integrity import canonical
from ibkr_paper_orders import IBKRPaperOrders, GatewayPaperWriter
from test_managed_execution import Reader


def sign(e, p):
    return hmac.new(e.key, canonical(p).encode(), hashlib.sha256).hexdigest()


def fill(e, t, a, broker_id, event_id, quantity, notional, fee="0", status="FILLED"):
    return e.event(
        t,
        a,
        dict(
            tenant=a.tenant,
            account=a.account,
            event_id=event_id,
            broker_id=broker_id,
            status=status,
            cumulative_filled=quantity,
            cumulative_notional=notional,
            cumulative_fee=fee,
            trade_date="2026-11-02",
            settlement_date="2026-11-03",
        ),
    )


def bought(s):
    e, t, a, *_ = s
    prepare(s)
    e.dispatch(t, a, "one", adapter(lambda *_: [dict(order_id="99")]))
    fill(e, t, a, "99", "buy", "2", "200")
    book = e.account_book(t, a)
    e.reconcile(t, a, book, book)
    return book


def test_partial_costs_fees_and_explicit_settlement_are_atomic(system):  # noqa: F811
    e, t, a, *_ = system
    prepare(system)
    e.dispatch(t, a, "one", adapter(lambda *_: [dict(order_id="99")]))
    fill(e, t, a, "99", "part", "1", "100", "1", status="PARTIAL")
    book = e.account_book(t, a)
    assert book["positions"] == {"123": "1"} and book["available_cash"]["USD"] == "199"
    fill(e, t, a, "99", "full", "2", "200", "1.5")
    book = e.account_book(t, a)
    assert book["cash"]["USD"] == "98.5" and book["settled_cash"]["USD"] == "300"
    with e.store.connect() as db:
        settlements = db.execute(
            "SELECT id,sha FROM managed_settlements ORDER BY id"
        ).fetchall()
    p = {
        **system[-2],
        "settlement_id": settlements[0][0],
        "settlement_hash": settlements[0][1],
    }
    with pytest.raises(PermissionError, match="not due"):
        e.confirm_settlement(t, a, p, sign(e, p))
    later = NOW + timedelta(days=1)
    principal = e.sessions.resolve(t, now=NOW)
    token = e.sessions.issue(principal, now=later)
    for sid, sha in settlements:
        p = {
            **system[-2],
            "issued_at": later.isoformat(),
            "expires_at": (later + timedelta(minutes=5)).isoformat(),
            "settlement_id": sid,
            "settlement_hash": sha,
        }
        assert e.confirm_settlement(token, a, p, sign(e, p), now=later) == "CONFIRMED"
        assert (
            e.confirm_settlement(token, a, p, sign(e, p), now=later)
            == "ALREADY_CONFIRMED"
        )
    assert e.account_book(token, a, now=later)["settled_cash"]["USD"] == "98.5"


def test_reduce_only_sell_cannot_short_or_reuse_unsettled_proceeds(system):  # noqa: F811
    e, t, a, c, q, p, sig = system
    bought(system)
    with pytest.raises(PermissionError):
        e.prepare(t, a, "short", c, q, "3", p, sig, side="SELL", reduce_only=True)
    with pytest.raises(PermissionError):
        e.prepare(t, a, "not-reduce", c, q, "1", p, sig, side="SELL")
    e.prepare(t, a, "sell", c, q, "2", p, sig, side="SELL", reduce_only=True)
    transport = adapter(lambda *_: [dict(order_id="100")])
    e.dispatch(t, a, "sell", transport)
    fill(e, t, a, "100", "sale", "2", "199.98", "1")
    book = e.account_book(t, a)
    assert book["positions"] == {} and book["available_cash"]["USD"] == "100"
    e.reconcile(t, a, book, book)
    with pytest.raises(PermissionError, match="Settled cash"):
        e.prepare(t, a, "rebuy", c, q, "2", p, sig)


def test_pending_sells_reserve_holdings(system):  # noqa: F811
    e, t, a, c, q, p, sig = system
    bought(system)
    e.prepare(t, a, "sale1", c, q, "1", p, sig, side="SELL", reduce_only=True)
    with pytest.raises(PermissionError):
        e.prepare(t, a, "sale2", c, q, "2", p, sig, side="SELL", reduce_only=True)


def test_invalid_fill_rolls_back_position_journal_and_event(system):  # noqa: F811
    e, t, a, *_ = system
    prepare(system)
    e.dispatch(t, a, "one", adapter(lambda *_: [dict(order_id="99")]))
    with pytest.raises(ValueError, match="limit"):
        fill(e, t, a, "99", "bad", "1", "101", status="PARTIAL")
    assert e.account_book(t, a)["positions"] == {}
    with e.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM broker_events").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM managed_settlements").fetchone()[0] == 0


def test_real_paper_writer_cannot_accept_simulation(system):  # noqa: F811
    e, t, a, *_ = system
    prepare(system)
    writer = GatewayPaperWriter("DU123")
    with pytest.raises(PermissionError, match="Synthetic"):
        e.dispatch(t, a, "one", IBKRPaperOrders("DU123", Reader(), writer))


def test_production_authorization_is_required_and_bound_to_exact_order(
    system,  # noqa: F811
    monkeypatch,  # noqa: F811
):  # noqa: F811
    from authorizedorderintent import AuthorizedOrderIntent
    from test_phase_iv_i_authorized_order_intent import _make_authorization
    from order import Order

    e, t, a, c, q, p, _ = system
    e.simulation_only = False
    with pytest.raises(PermissionError, match="provider"):
        e.prepare(t, a, "risk", c, q, "2", p, sign(e, p))
    order = Order("SPY", "BUY", 2, order_id="risk", order_type="LIMIT", limit_price=100)
    artifact = AuthorizedOrderIntent.from_authorization(_make_authorization(), order)
    e.authorization_reader = lambda _: artifact
    p = {**p, "instrument_symbol": "SPY", "instrument_id": "123"}
    with pytest.raises(PermissionError, match="portfolio risk provider"):
        e.prepare(t, a, "risk", c, q, "2", p, sign(e, p))
    # This test isolates immutable production authorization; measured portfolio
    # evidence has its own fail-closed provider tests and is never fabricated here.
    monkeypatch.setattr(e, "_portfolio_envelope", lambda *_: None)
    from writer_fencing import claim

    e.writer_lease = claim(e.store, a, "test-process", now=NOW)
    assert e.prepare(t, a, "risk", c, q, "2", p, sign(e, p)) == "PAPER_QUEUED"
    changed = AuthorizedOrderIntent.from_authorization(
        _make_authorization(),
        Order("SPY", "BUY", 3, order_id="risk", order_type="LIMIT", limit_price=100),
    )
    e.authorization_reader = lambda _: changed
    with pytest.raises(PermissionError, match="dimensions"):
        e.dispatch(t, a, "risk", adapter(lambda *_: None))


def test_fee_headroom_is_reserved_and_overrun_records_truth_then_freezes(system):  # noqa: F811
    e, t, a, *_ = system
    with pytest.raises(PermissionError, match="Settled cash"):
        prepare(system, "all-cash", quantity="3")
    prepare(system)
    e.dispatch(t, a, "one", adapter(lambda *_: [dict(order_id="99")]))
    fill(e, t, a, "99", "fee-overrun", "2", "200", "3")
    assert e.account_book(t, a)["cash"]["USD"] == "97"
    with e.store.connect() as db:
        assert db.execute("SELECT frozen FROM accounts").fetchone()[0] == 1
        assert (
            db.execute("SELECT reason FROM managed_incidents").fetchone()[0]
            == "FEE_BUFFER_BREACH_REVIEW_REQUIRED"
        )
