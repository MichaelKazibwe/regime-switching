from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import pytest
from managed_accounts import (
    ManagedPaperStore,
    AccountScope,
    Principal,
    InstrumentContract,
)
from managed_boundary import PaperSessions
from managed_execution import ManagedExecution
from managed_operations import ManagedOperations
from managed_transport import ManagedPaperTransport
from ibkr_paper_orders import IBKRPaperOrders
from strategy_integrity import canonical, fingerprint
from order import Order

NOW = datetime(2026, 11, 2, 16, tzinfo=timezone.utc)


@pytest.fixture
def system(tmp_path):
    store = ManagedPaperStore(tmp_path / "state.sqlite3")
    scope = AccountScope("tenant", "DU123")
    store.create_account(scope)
    principal = Principal(
        "test-operator",
        frozenset(
            (scope.tenant, scope.account, a)
            for a in (
                "read",
                "enqueue",
                "dispatch",
                "cancel",
                "reconcile",
                "enable_paper",
                "freeze",
            )
        ),
    )
    sessions = PaperSessions()
    token = sessions.issue(principal, now=NOW)
    engine = ManagedExecution(
        store,
        sessions,
        verification_key=b"test-key-not-real-credentials-32bytes",
        release_id="test-release",
        image_digest="test-image",
        clock=lambda: NOW,
        simulation_only=True,
    )
    permit = dict(
        tenant=scope.tenant,
        account=scope.account,
        release_id="test-release",
        image_digest="test-image",
        mode="PAPER",
        issued_at=NOW.isoformat(),
        expires_at=(NOW + timedelta(minutes=5)).isoformat(),
        reviewer="TEST FIXTURE ONLY",
        evidence_id="synthetic-not-approval",
        max_order_notional="500",
        max_open_notional="1000",
        fee_buffer="2",
        currency="USD",
        client_country="MU",
        allowed_countries=["MU"],
        mandate_id="test-mandate",
    )
    signature = hmac.new(
        engine.key, canonical(permit).encode(), hashlib.sha256
    ).hexdigest()
    snapshot = dict(
        tenant=scope.tenant,
        account=scope.account,
        as_of=NOW.isoformat(),
        cash={"USD": "300"},
        settled_cash={"USD": "300"},
        positions={},
        open_orders=[],
        corporate_actions=[],
    )
    engine.reconcile(token, scope, snapshot, snapshot)
    permit.update(
        opening_snapshot_hash=fingerprint(snapshot),
        opening_positions={},
        allow_reduce_only_sell=True,
    )
    signature = hmac.new(
        engine.key, canonical(permit).encode(), hashlib.sha256
    ).hexdigest()
    engine.adopt_opening_book(token, scope, permit, signature)
    ManagedOperations(engine).resume_paper(token, scope, permit, signature)
    contract = InstrumentContract(
        "IBKR", "TEST", "123", "XNYS", "USD", "USD", "1", "1", "0.01"
    )
    quote = dict(
        instrument_id="123",
        currency="USD",
        bid="99.99",
        ask="100.00",
        as_of=NOW.isoformat(),
        basis="UNADJUSTED_EXECUTABLE",
        source="synthetic-test",
    )
    return engine, token, scope, contract, quote, permit, signature


def prepare(s, id="one", quantity="2"):
    e, t, a, c, q, p, sig = s
    return e.prepare(t, a, id, c, q, quantity, p, sig)


class Reader:
    def get(self, path):
        return [dict(accountId="DU123", type="DEMO")]


def adapter(request):
    return IBKRPaperOrders("DU123", Reader(), request)


def test_prepare_counts_pending_orders_against_settled_cash(system):
    assert prepare(system) == "PAPER_QUEUED"
    assert prepare(system) == "ALREADY_QUEUED"
    with pytest.raises(PermissionError, match="Settled cash"):
        prepare(system, "two")


def test_signature_and_release_scope_cannot_be_replaced(system):
    e, t, a, c, q, p, sig = system
    with pytest.raises(PermissionError):
        e.prepare(t, a, "x", c, q, "1", {**p, "max_order_notional": "9999"}, sig)
    with pytest.raises(PermissionError):
        e.prepare(t, AccountScope("other", "DU123"), "x", c, q, "1", p, sig)


def test_ambiguous_submit_freezes_and_never_resubmits(system):
    e, t, a, *_ = system
    prepare(system)
    calls = []

    def timeout(*args):
        calls.append(args)
        raise TimeoutError("TEST")

    transport = adapter(timeout)
    with pytest.raises(TimeoutError):
        e.dispatch(t, a, "one", transport)
    with pytest.raises(PermissionError):
        e.dispatch(t, a, "one", transport)
    assert len(calls) == 1
    with pytest.raises(PermissionError):
        ManagedOperations(e).resume_paper(t, a, system[-2], system[-1])


def test_restart_quarantines_inflight_intents(system):
    e, t, a, *_ = system
    prepare(system)
    with e.store.connect() as db:
        db.execute("UPDATE outbox SET state='DISPATCHING'")
    assert e.recover() == 1
    with e.store.connect() as db:
        assert db.execute("SELECT state FROM outbox").fetchone()[0] == "UNKNOWN"


def test_partial_duplicate_cancel_and_late_fill(system):
    e, t, a, *_ = system
    prepare(system)
    transport = adapter(lambda *args: [dict(order_id="99", order_status="Submitted")])
    e.dispatch(t, a, "one", transport)
    partial = dict(
        tenant=a.tenant,
        account=a.account,
        event_id="a",
        broker_id="99",
        status="PARTIAL",
        cumulative_filled="1",
        cumulative_notional="100",
        cumulative_fee="0",
        trade_date="2026-11-02",
        settlement_date="2026-11-03",
    )
    assert e.event(t, a, partial) == "RECORDED"
    assert e.event(t, a, partial) == "DUPLICATE"
    assert e.cancel(t, a, "99", transport) == "CANCEL_PENDING"
    e.event(
        t,
        a,
        dict(
            tenant=a.tenant,
            account=a.account,
            event_id="b",
            broker_id="99",
            status="CANCELLED",
            cumulative_filled="1",
            cumulative_notional="100",
            cumulative_fee="0",
            trade_date="2026-11-02",
            settlement_date="2026-11-03",
        ),
    )
    e.event(
        t,
        a,
        dict(
            tenant=a.tenant,
            account=a.account,
            event_id="c",
            broker_id="99",
            status="FILLED",
            cumulative_filled="2",
            cumulative_notional="200",
            cumulative_fee="0",
            trade_date="2026-11-02",
            settlement_date="2026-11-03",
        ),
    )
    with pytest.raises(ValueError):
        e.event(t, a, {**partial, "event_id": "d"})


def test_unknown_and_conflicting_execution_events_rejected(system):
    e, t, a, *_ = system
    prepare(system)
    transport = adapter(lambda *args: [dict(order_id="99")])
    e.dispatch(t, a, "one", transport)
    event = dict(
        tenant=a.tenant,
        account=a.account,
        event_id="a",
        broker_id="99",
        status="PARTIAL",
        cumulative_filled="1",
        cumulative_notional="100",
        cumulative_fee="0",
        trade_date="2026-11-02",
        settlement_date="2026-11-03",
    )
    e.event(t, a, event)
    with pytest.raises(ValueError):
        e.event(t, a, {**event, "cumulative_filled": "1.5"})
    with pytest.raises(PermissionError):
        e.event(t, a, {**event, "event_id": "b", "broker_id": "999"})


def test_corporate_actions_and_unexplained_cash_freeze(system):
    e, t, a, *_ = system
    x = dict(
        tenant=a.tenant,
        account=a.account,
        as_of=NOW.isoformat(),
        cash={"USD": "300"},
        settled_cash={"USD": "300"},
        positions={},
        open_orders=[],
        corporate_actions=[],
    )
    changed = deepcopy(x)
    changed["cash"]["USD"] = "301"
    changed["corporate_actions"] = ["TEST SPLIT REVIEW"]
    assert e.reconcile(t, a, changed, x)["status"] == "QUARANTINED"
    with pytest.raises(PermissionError):
        prepare(system)


def test_ibkr_warning_is_quarantined_not_auto_confirmed(system):
    e, t, a, *_ = system
    prepare(system)
    calls = []

    def warning(*args):
        calls.append(args)
        return [dict(id="reply", message=["TEST WARNING"])]

    with pytest.raises(ValueError):
        e.dispatch(t, a, "one", adapter(warning))
    assert len(calls) == 1 and calls[0][1].endswith("/orders")


def test_brokertransport_bridge_refuses_unprepared_or_modified_orders(system):
    e, t, a, *_ = system
    prepare(system)
    bridge = ManagedPaperTransport(
        e, t, a, adapter(lambda *args: [dict(order_id="99")]), {"SPY": "123"}
    )
    bridge.connect()
    with pytest.raises(PermissionError):
        bridge.submit_order(
            Order("SPY", "BUY", 3, order_id="one", order_type="LIMIT", limit_price=100)
        )
    receipt = bridge.submit_order(
        Order("SPY", "BUY", 2, order_id="one", order_type="LIMIT", limit_price=100)
    )
    assert receipt["broker_order_id"] == "99"
    assert bridge.get_order("99")["status"] == "ACCEPTED"


def test_quote_expiry_blocks_dispatch_before_transport(system):
    e, t, a, *_ = system
    prepare(system)
    with pytest.raises(PermissionError):
        e.dispatch(
            t, a, "one", adapter(lambda *_: None), now=NOW + timedelta(seconds=31)
        )


def test_future_issued_session_not_yet_valid(system):
    e, t, *_ = system
    with pytest.raises(PermissionError):
        e.sessions.resolve(t, now=NOW - timedelta(seconds=1))


def test_settled_cash_rechecked_before_dispatch(system):
    e, t, a, *_ = system
    prepare(system)
    snapshot = dict(
        tenant=a.tenant,
        account=a.account,
        as_of=NOW.isoformat(),
        cash={"USD": "300"},
        settled_cash={"USD": "100"},
        positions={},
        open_orders=[],
        corporate_actions=[],
    )
    assert e.reconcile(t, a, snapshot, snapshot)["status"] == "QUARANTINED"
    with pytest.raises(PermissionError, match="frozen"):
        e.dispatch(t, a, "one", adapter(lambda *_: None))


def test_unknown_binding_requires_signed_broker_identity_and_stays_frozen(system):
    e, t, a, *_ = system
    prepare(system)
    with e.store.connect() as db:
        db.execute("UPDATE outbox SET state='DISPATCHING'")
    e.recover()
    permit = {**system[-2], "resolution_client_id": "one", "resolution_broker_id": "99"}
    with pytest.raises(PermissionError):
        e.bind_unknown(t, a, "one", permit, system[-1])
    signature = hmac.new(e.key, canonical(permit).encode(), hashlib.sha256).hexdigest()
    assert e.bind_unknown(t, a, "one", permit, signature).startswith(
        "BOUND_STILL_FROZEN"
    )
    with pytest.raises(PermissionError):
        ManagedOperations(e).resume_paper(t, a, system[-2], system[-1])
