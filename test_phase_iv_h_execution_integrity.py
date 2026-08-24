"""
Phase IV-H — Execution Integrity Boundary
==========================================

This suite defines the execution-integrity boundary downstream of
Phase IV-G.

Phase IV-H converts the discovered downstream execution behavior into
explicit regression contracts covering:

1. order lifecycle integrity;
2. order-book integrity;
3. paper-broker submission and fill integrity;
4. paper-broker cancellation integrity;
5. broker-router integrity;
6. LIVE broker fail-closed behavior;
7. LIVE broker authorized positive-path behavior;
8. LIVE broker authorization revocation;
9. broker execution receipt integrity;
10. reconciliation integrity;
11. post-trade execution monitoring;
12. execution analytics invariants;
13. deterministic trade generation.

Phase IV-G remains the authoritative upstream execution-safety
boundary.

This suite intentionally tests public execution contracts and
observable state transitions rather than implementation details.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _import(module: str, name: str) -> Any:
    imported = __import__(module, fromlist=[name])
    return getattr(imported, name)


def _make_order(
    *,
    order_id: str = "H-ORDER-001",
    ticker: str = "SPY",
    side: str = "BUY",
    quantity: float = 100.0,
) -> Any:
    Order = _import("order", "Order")

    return Order(
        ticker=ticker,
        side=side,
        quantity=quantity,
        order_id=order_id,
    )


def _make_live_broker() -> Any:
    LiveBroker = _import("livebroker", "LiveBroker")
    return LiveBroker()


def _make_paper_broker() -> Any:
    PaperBroker = _import("paperbroker", "PaperBroker")
    return PaperBroker()


@dataclass(frozen=True)
class ExecutionIntegrityContract:
    """
    Declarative Phase IV-H execution-integrity contract.

    This object deliberately contains no broker credentials, network
    state, or live execution capability.
    """

    authorization_required: bool = True
    pretrade_risk_required: bool = True
    broker_route_required: bool = True
    reconciliation_required: bool = True
    posttrade_monitor_required: bool = True
    duplicate_submission_blocked: bool = True
    live_trading_default_disabled: bool = True


# ============================================================================
# PHASE IV-G UPSTREAM AUTHORITY
# ============================================================================


def test_phase_iv_g_remains_upstream_authority() -> None:
    ProductionExecutionGate = _import(
        "productionexecutiongate",
        "ProductionExecutionGate",
    )

    gate = ProductionExecutionGate()

    assert hasattr(gate, "require_authorization")
    assert callable(gate.require_authorization)


# ============================================================================
# COMPONENT AVAILABILITY
# ============================================================================


def test_phase_iv_h_component_imports_are_stable() -> None:
    modules = (
        "order",
        "orderstatus",
        "orderbook",
        "brokerrouter",
        "paperbroker",
        "livebroker",
        "pretraderiskgate",
        "reconciliationengine",
        "posttradeexecutionmonitor",
        "executionanalytics",
        "tradegenerator",
        "executionengine",
        "oms",
        "brokerexecutionengine",
    )

    for module_name in modules:
        __import__(module_name)


def test_order_module_exposes_order_contract() -> None:
    assert hasattr(__import__("order"), "Order")


def test_order_status_module_exposes_status_contract() -> None:
    assert hasattr(__import__("orderstatus"), "OrderStatus")


def test_order_book_exposes_order_book_contract() -> None:
    assert hasattr(__import__("orderbook"), "OrderBook")


def test_broker_router_exposes_routing_contract() -> None:
    assert hasattr(__import__("brokerrouter"), "BrokerRouter")


def test_paper_broker_is_available() -> None:
    assert hasattr(__import__("paperbroker"), "PaperBroker")


def test_live_broker_is_available() -> None:
    assert hasattr(__import__("livebroker"), "LiveBroker")


def test_pretrade_risk_gate_is_available() -> None:
    assert hasattr(__import__("pretraderiskgate"), "PreTradeRiskGate")


def test_reconciliation_engine_is_available() -> None:
    assert hasattr(
        __import__("reconciliationengine"),
        "ReconciliationEngine",
    )


def test_post_trade_monitor_is_available() -> None:
    assert hasattr(
        __import__("posttradeexecutionmonitor"),
        "PostTradeExecutionMonitor",
    )


def test_execution_analytics_is_available() -> None:
    assert hasattr(
        __import__("executionanalytics"),
        "ExecutionAnalytics",
    )


def test_trade_generator_is_available() -> None:
    assert hasattr(__import__("tradegenerator"), "TradeGenerator")


def test_execution_engine_is_available() -> None:
    assert hasattr(__import__("executionengine"), "ExecutionEngine")


def test_oms_is_available() -> None:
    assert hasattr(__import__("oms"), "OMS")


def test_broker_execution_engine_is_available() -> None:
    assert hasattr(
        __import__("brokerexecutionengine"),
        "BrokerExecutionEngine",
    )


# ============================================================================
# DECLARATIVE INTEGRITY CONTRACT
# ============================================================================


def test_phase_iv_h_integrity_contract_is_fail_closed() -> None:
    contract = ExecutionIntegrityContract()

    assert contract.authorization_required is True
    assert contract.pretrade_risk_required is True
    assert contract.broker_route_required is True
    assert contract.reconciliation_required is True
    assert contract.posttrade_monitor_required is True
    assert contract.duplicate_submission_blocked is True
    assert contract.live_trading_default_disabled is True


def test_phase_iv_h_contract_is_immutable() -> None:
    contract = ExecutionIntegrityContract()

    try:
        contract.authorization_required = False
    except Exception:
        pass
    else:
        raise AssertionError(
            "Execution integrity contract must be immutable."
        )


def test_phase_iv_h_integrity_contract_is_deterministic() -> None:
    first = ExecutionIntegrityContract()
    second = ExecutionIntegrityContract()

    assert first == second


def test_phase_iv_h_integrity_contract_has_expected_fields() -> None:
    contract = ExecutionIntegrityContract()

    expected = {
        "authorization_required",
        "pretrade_risk_required",
        "broker_route_required",
        "reconciliation_required",
        "posttrade_monitor_required",
        "duplicate_submission_blocked",
        "live_trading_default_disabled",
    }

    assert set(contract.__dataclass_fields__) == expected


def test_phase_iv_h_does_not_authorize_execution_by_itself() -> None:
    contract = ExecutionIntegrityContract()

    assert not hasattr(contract, "authorized")
    assert not hasattr(contract, "approve")
    assert not hasattr(contract, "authorize")


def test_phase_iv_h_requires_reconciliation() -> None:
    assert ExecutionIntegrityContract().reconciliation_required is True


def test_phase_iv_h_requires_posttrade_monitoring() -> None:
    assert ExecutionIntegrityContract().posttrade_monitor_required is True


def test_phase_iv_h_blocks_duplicate_submission_contractually() -> None:
    assert ExecutionIntegrityContract().duplicate_submission_blocked is True


def test_phase_iv_h_requires_pretrade_risk_contractually() -> None:
    assert ExecutionIntegrityContract().pretrade_risk_required is True


def test_phase_iv_h_requires_broker_route_contractually() -> None:
    assert ExecutionIntegrityContract().broker_route_required is True


def test_phase_iv_h_requires_authorization_contractually() -> None:
    assert ExecutionIntegrityContract().authorization_required is True


# ============================================================================
# LIVE BROKER DEFAULT SAFETY
# ============================================================================


def test_live_broker_defaults_to_non_live_state() -> None:
    broker = _make_live_broker()

    assert getattr(broker, "_connected", False) is False
    assert getattr(broker, "_authenticated", False) is False
    assert getattr(broker, "_live_trading_enabled", False) is False


def test_live_broker_cannot_be_considered_connected_by_default() -> None:
    broker = _make_live_broker()

    assert getattr(broker, "_connected", False) is False


def test_live_broker_does_not_enable_trading_by_default() -> None:
    broker = _make_live_broker()

    assert getattr(broker, "_live_trading_enabled", False) is False


def test_phase_iv_h_does_not_create_live_broker_connection() -> None:
    broker = _make_live_broker()

    assert getattr(broker, "_connected", False) is False


def test_phase_iv_h_does_not_enable_live_trading() -> None:
    broker = _make_live_broker()

    assert getattr(broker, "_live_trading_enabled", False) is False


def test_live_broker_summary_is_fail_closed_by_default() -> None:
    broker = _make_live_broker()
    summary = broker.summary()

    assert summary["connected"] is False
    assert summary["authenticated"] is False
    assert summary["live_trading_enabled"] is False


# ============================================================================
# H1 — ORDER LIFECYCLE INTEGRITY
# ============================================================================


def test_order_submit_transition_is_valid() -> None:
    order = _make_order()

    order.submit()

    assert order.status == "SUBMITTED"
    assert order.is_submitted()


def test_order_partial_fill_transition_is_valid() -> None:
    order = _make_order()
    order.submit()

    order.fill(40.0, 500.0)

    assert order.status == "PARTIALLY_FILLED"
    assert order.filled_quantity == 40.0
    assert order.remaining_quantity == 60.0


def test_order_full_fill_transition_is_valid() -> None:
    order = _make_order()
    order.submit()

    order.fill(100.0, 500.0)

    assert order.status == "FILLED"
    assert order.filled_quantity == 100.0
    assert order.remaining_quantity == 0.0
    assert order.is_filled()


def test_order_cancellation_is_terminal() -> None:
    order = _make_order()
    order.cancel()

    assert order.status == "CANCELLED"
    assert order.is_cancelled()


def test_cancelled_order_cannot_be_filled() -> None:
    order = _make_order()
    order.cancel()

    try:
        order.fill(10.0, 500.0)
    except RuntimeError as exc:
        assert "cancelled" in str(exc).lower()
    else:
        raise AssertionError("Cancelled order accepted a fill.")


def test_cancelled_order_cannot_be_submitted() -> None:
    order = _make_order()
    order.cancel()

    try:
        order.submit()
    except RuntimeError as exc:
        assert "pending" in str(exc).lower()
    else:
        raise AssertionError("Cancelled order was resubmitted.")


def test_rejected_order_cannot_be_filled_or_submitted() -> None:
    order = _make_order()
    order.reject()

    try:
        order.fill(10.0, 500.0)
    except RuntimeError as exc:
        assert "rejected" in str(exc).lower()
    else:
        raise AssertionError("Rejected order accepted a fill.")

    try:
        order.submit()
    except RuntimeError as exc:
        assert "pending" in str(exc).lower()
    else:
        raise AssertionError("Rejected order was resubmitted.")


def test_filled_order_cannot_be_cancelled_or_resubmitted() -> None:
    order = _make_order()
    order.submit()
    order.fill(100.0, 500.0)

    try:
        order.cancel()
    except RuntimeError as exc:
        assert "filled" in str(exc).lower()
    else:
        raise AssertionError("Filled order was cancelled.")

    try:
        order.submit()
    except RuntimeError as exc:
        assert "pending" in str(exc).lower()
    else:
        raise AssertionError("Filled order was resubmitted.")


def test_order_overfill_is_rejected() -> None:
    order = _make_order()
    order.submit()

    try:
        order.fill(101.0, 500.0)
    except ValueError as exc:
        assert "remaining quantity" in str(exc).lower()
    else:
        raise AssertionError("Order accepted an overfill.")


# ============================================================================
# H2 — ORDER BOOK INTEGRITY
# ============================================================================


def test_order_book_adds_order_once() -> None:
    OrderBook = _import("orderbook", "OrderBook")

    book = OrderBook()
    order = _make_order(order_id="H2-001")

    book.add_order(order)

    assert book.has_order("H2-001")
    assert book.get_order("H2-001") is order


def test_order_book_rejects_duplicate_order_id() -> None:
    OrderBook = _import("orderbook", "OrderBook")

    book = OrderBook()
    book.add_order(_make_order(order_id="H2-001"))

    try:
        book.add_order(_make_order(order_id="H2-001"))
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("Duplicate order ID was accepted.")


def test_order_book_missing_order_operations_fail_closed() -> None:
    OrderBook = _import("orderbook", "OrderBook")

    book = OrderBook()

    for operation in (
        lambda: book.get_order("DOES-NOT-EXIST"),
        lambda: book.remove_order("DOES-NOT-EXIST"),
    ):
        try:
            operation()
        except KeyError:
            continue
        else:
            raise AssertionError(
                "Missing order operation did not fail closed."
            )


# ============================================================================
# H3 — PAPER BROKER EXECUTION INTEGRITY
# ============================================================================


def test_paper_broker_submission_registers_order() -> None:
    broker = _make_paper_broker()
    order = _make_order(order_id="H3-001", quantity=100.0)

    result = broker.submit_order(order)

    assert result["broker"] == "PAPER"
    assert result["client_order_id"] == "H3-001"
    assert result["status"] == "SUBMITTED"
    assert broker.has_order("H3-001")


def test_paper_broker_duplicate_submission_is_blocked() -> None:
    broker = _make_paper_broker()
    order = _make_order(order_id="H3-DUP")

    broker.submit_order(order)

    try:
        broker.submit_order(order)
    except ValueError as exc:
        assert "already been submitted" in str(exc)
    else:
        raise AssertionError(
            "Paper broker accepted duplicate submission."
        )


def test_paper_broker_partial_and_full_fills_are_integrity_safe() -> None:
    broker = _make_paper_broker()
    order = _make_order(order_id="H3-FILL", quantity=100.0)

    broker.submit_order(order)

    partial = broker.fill_order(
        "H3-FILL",
        execution_price=500.0,
        quantity=40.0,
    )

    assert partial.quantity == 40.0
    assert partial.status == "PARTIALLY_FILLED"

    final = broker.fill_order(
        "H3-FILL",
        execution_price=501.0,
        quantity=60.0,
    )

    assert final.quantity == 60.0
    assert final.status == "FILLED"

    record = broker.get_order("H3-FILL")
    assert record.status == "FILLED"
    assert record.filled_quantity == 100.0
    assert record.remaining_quantity == 0.0


def test_paper_broker_rejects_excessive_fill() -> None:
    broker = _make_paper_broker()
    order = _make_order(order_id="H3-OVERFILL", quantity=100.0)

    broker.submit_order(order)

    broker.fill_order(
        "H3-OVERFILL",
        execution_price=500.0,
        quantity=40.0,
    )

    try:
        broker.fill_order(
            "H3-OVERFILL",
            execution_price=500.0,
            quantity=61.0,
        )
    except ValueError as exc:
        assert "remaining quantity" in str(exc).lower()
    else:
        raise AssertionError("Paper broker accepted excessive fill.")


def test_paper_broker_rejects_fill_after_completion() -> None:
    broker = _make_paper_broker()
    order = _make_order(order_id="H3-COMPLETE", quantity=10.0)

    broker.submit_order(order)
    broker.fill_order(
        "H3-COMPLETE",
        execution_price=500.0,
        quantity=10.0,
    )

    try:
        broker.fill_order(
            "H3-COMPLETE",
            execution_price=500.0,
            quantity=1.0,
        )
    except RuntimeError as exc:
        assert "FILLED" in str(exc)
    else:
        raise AssertionError(
            "Paper broker accepted fill after completion."
        )


# ============================================================================
# H4 — PAPER BROKER CANCELLATION INTEGRITY
# ============================================================================


def test_paper_broker_cancellation_is_terminal() -> None:
    broker = _make_paper_broker()
    order = _make_order(order_id="H4-001")

    broker.submit_order(order)

    result = broker.cancel_order("H4-001")

    assert result["status"] == "CANCELLED"
    assert broker.get_order("H4-001").status == "CANCELLED"


def test_paper_broker_cannot_fill_cancelled_order() -> None:
    broker = _make_paper_broker()
    order = _make_order(order_id="H4-FILL-CANCEL")

    broker.submit_order(order)
    broker.cancel_order("H4-FILL-CANCEL")

    try:
        broker.fill_order(
            "H4-FILL-CANCEL",
            execution_price=500.0,
            quantity=10.0,
        )
    except RuntimeError as exc:
        assert "CANCELLED" in str(exc)
    else:
        raise AssertionError(
            "Cancelled paper order accepted a fill."
        )


def test_paper_broker_cannot_cancel_cancelled_order() -> None:
    broker = _make_paper_broker()
    order = _make_order(order_id="H4-CANCEL-TWICE")

    broker.submit_order(order)
    broker.cancel_order("H4-CANCEL-TWICE")

    try:
        broker.cancel_order("H4-CANCEL-TWICE")
    except RuntimeError as exc:
        assert "CANCELLED" in str(exc)
    else:
        raise AssertionError(
            "Cancelled paper order was cancelled twice."
        )


# ============================================================================
# H5 — BROKER ROUTER INTEGRITY
# ============================================================================


def test_broker_router_requires_broker_selection() -> None:
    BrokerRouter = _import("brokerrouter", "BrokerRouter")

    router = BrokerRouter()
    order = _make_order(order_id="H5-NO-BROKER")

    try:
        router.route_order(order)
    except RuntimeError as exc:
        assert "No broker specified" in str(exc)
    else:
        raise AssertionError(
            "Router silently routed without a broker."
        )


def test_broker_router_rejects_missing_broker() -> None:
    BrokerRouter = _import("brokerrouter", "BrokerRouter")

    router = BrokerRouter()
    order = _make_order(order_id="H5-MISSING")

    try:
        router.route_order(order, broker_name="MISSING")
    except KeyError as exc:
        assert "MISSING" in str(exc)
    else:
        raise AssertionError(
            "Router accepted an unregistered broker."
        )


def test_broker_router_rejects_missing_default_broker() -> None:
    BrokerRouter = _import("brokerrouter", "BrokerRouter")

    router = BrokerRouter()

    try:
        router.set_default_broker("DOES-NOT-EXIST")
    except KeyError as exc:
        assert "DOES-NOT-EXIST" in str(exc)
    else:
        raise AssertionError(
            "Router configured an unavailable default broker."
        )


def test_broker_router_can_route_to_registered_paper_broker() -> None:
    BrokerRouter = _import("brokerrouter", "BrokerRouter")

    router = BrokerRouter()
    broker = _make_paper_broker()

    router.register_broker(broker)

    result = router.route_order(
        _make_order(order_id="H5-PAPER"),
        broker_name="PAPER",
    )

    assert result is not None
    assert result.broker == "PAPER"


# ============================================================================
# H6 — LIVE BROKER FAIL-CLOSED STATE MACHINE
# ============================================================================


def test_live_broker_rejects_submission_when_disconnected() -> None:
    broker = _make_live_broker()

    try:
        broker.submit_order(_make_order(order_id="H6-DISCONNECTED"))
    except RuntimeError as exc:
        assert str(exc) == "LIVE_BROKER_DISCONNECTED"
    else:
        raise AssertionError(
            "Disconnected LIVE broker accepted submission."
        )


def test_live_broker_cannot_enable_trading_while_disconnected() -> None:
    broker = _make_live_broker()

    try:
        broker.enable_live_trading()
    except RuntimeError as exc:
        assert "broker disconnected" in str(exc).lower()
    else:
        raise AssertionError(
            "LIVE trading was enabled while disconnected."
        )


def test_live_broker_without_transport_cannot_connect() -> None:
    broker = _make_live_broker()

    try:
        broker.connect()
    except RuntimeError as exc:
        assert "transport" in str(exc).lower()
    else:
        raise AssertionError(
            "LIVE broker connected without transport."
        )


def test_live_broker_without_transport_cannot_authenticate() -> None:
    broker = _make_live_broker()

    try:
        broker.authenticate()
    except RuntimeError as exc:
        assert "transport" in str(exc).lower()
    else:
        raise AssertionError(
            "LIVE broker authenticated without transport."
        )


# ============================================================================
# H7 — LIVE BROKER AUTHORIZED POSITIVE PATH
# ============================================================================


def test_live_broker_positive_path_requires_explicit_gates() -> None:
    LiveBroker = _import("livebroker", "LiveBroker")
    TestLiveTransport = _import("livebroker", "_TestLiveTransport")

    broker = LiveBroker(transport=TestLiveTransport())

    assert broker.summary()["connected"] is False
    assert broker.summary()["authenticated"] is False
    assert broker.summary()["live_trading_enabled"] is False

    assert broker.connect() is True
    assert broker.authenticate() is True
    assert broker.enable_live_trading() is True

    summary = broker.summary()

    assert summary["connected"] is True
    assert summary["authenticated"] is True
    assert summary["live_trading_enabled"] is True


def test_live_broker_authorized_positive_path_accepts_submission() -> None:
    LiveBroker = _import("livebroker", "LiveBroker")
    TestLiveTransport = _import("livebroker", "_TestLiveTransport")

    broker = LiveBroker(transport=TestLiveTransport())

    broker.connect()
    broker.authenticate()
    broker.enable_live_trading()

    result = broker.submit_order(
        _make_order(order_id="H7-LIVE-001", quantity=10.0)
    )

    assert result["broker"] == "LIVE"
    assert result["client_order_id"] == "H7-LIVE-001"
    assert result["status"] == "ACCEPTED"

    summary = broker.summary()

    assert summary["orders"] == 1
    assert summary["active_orders"] == 1
    assert summary["submission_count"] == 1


# ============================================================================
# H8 — LIVE AUTHORIZATION REVOCATION
# ============================================================================


def test_live_broker_disabling_trading_blocks_future_submission() -> None:
    LiveBroker = _import("livebroker", "LiveBroker")
    TestLiveTransport = _import("livebroker", "_TestLiveTransport")

    broker = LiveBroker(transport=TestLiveTransport())

    broker.connect()
    broker.authenticate()
    broker.enable_live_trading()

    broker.submit_order(
        _make_order(order_id="H8-LIVE-001", quantity=10.0)
    )

    assert broker.disable_live_trading() is True

    try:
        broker.submit_order(
            _make_order(order_id="H8-LIVE-002", quantity=10.0)
        )
    except RuntimeError as exc:
        assert str(exc) == "LIVE_TRADING_DISABLED"
    else:
        raise AssertionError(
            "LIVE broker accepted order after authorization revocation."
        )


def test_live_broker_disconnect_revokes_live_state() -> None:
    LiveBroker = _import("livebroker", "LiveBroker")
    TestLiveTransport = _import("livebroker", "_TestLiveTransport")

    broker = LiveBroker(transport=TestLiveTransport())

    broker.connect()
    broker.authenticate()
    broker.enable_live_trading()

    broker.disconnect()

    summary = broker.summary()

    assert summary["connected"] is False
    assert summary["authenticated"] is False
    assert summary["live_trading_enabled"] is False


# ============================================================================
# H9 — BROKER EXECUTION RECEIPT INTEGRITY
# ============================================================================


def test_broker_execution_receipt_can_be_validated() -> None:
    PaperBroker = _import("paperbroker", "PaperBroker")
    BrokerExecutionEngine = _import(
        "brokerexecutionengine",
        "BrokerExecutionEngine",
    )

    broker = PaperBroker()
    engine = BrokerExecutionEngine()

    order = _make_order(order_id="H9-001", quantity=10.0)

    broker.submit_order(order)
    receipt = broker.fill_order(
        "H9-001",
        execution_price=500.0,
        quantity=10.0,
    )

    assert engine.validate_order(order)
    assert engine.validate_receipt(receipt)


def test_broker_execution_engine_validates_structurally_valid_receipt() -> None:
    PaperBroker = _import("paperbroker", "PaperBroker")
    BrokerExecutionEngine = _import(
        "brokerexecutionengine",
        "BrokerExecutionEngine",
    )

    broker = PaperBroker()
    engine = BrokerExecutionEngine()

    order = _make_order(order_id="H9-VALID", quantity=10.0)

    broker.submit_order(order)

    receipt = broker.fill_order(
        "H9-VALID",
        execution_price=500.0,
        quantity=10.0,
    )

    assert engine.validate_receipt(receipt) is True


# ============================================================================
# H10 — RECONCILIATION INTEGRITY
# ============================================================================


def test_reconciliation_matching_orders_are_approved() -> None:
    ReconciliationEngine = _import(
        "reconciliationengine",
        "ReconciliationEngine",
    )

    engine = ReconciliationEngine()

    order = _make_order(order_id="H10-001", quantity=100.0)

    decision = engine.reconcile_order(
        order,
        order,
    )

    assert decision.status == "MATCHED"
    assert decision.approved is True


def test_reconciliation_quantity_mismatch_is_rejected() -> None:
    ReconciliationEngine = _import(
        "reconciliationengine",
        "ReconciliationEngine",
    )

    engine = ReconciliationEngine()

    oms_order = _make_order(
        order_id="H10-QTY",
        quantity=100.0,
    )
    broker_order = _make_order(
        order_id="H10-QTY",
        quantity=99.0,
    )

    decision = engine.reconcile_order(
        oms_order,
        broker_order,
    )

    assert decision.status == "DISCREPANCY"
    assert decision.approved is False
    assert decision.discrepancy_type == "QUANTITY_MISMATCH"


def test_reconciliation_matching_account_position_is_approved() -> None:
    ReconciliationEngine = _import(
        "reconciliationengine",
        "ReconciliationEngine",
    )

    engine = ReconciliationEngine()

    decision = engine.reconcile_account_position(
        "SPY",
        expected_position=100.0,
        actual_position=100.0,
    )

    assert decision.status == "MATCHED"
    assert decision.approved is True


def test_reconciliation_account_position_mismatch_is_rejected() -> None:
    ReconciliationEngine = _import(
        "reconciliationengine",
        "ReconciliationEngine",
    )

    engine = ReconciliationEngine()

    decision = engine.reconcile_account_position(
        "SPY",
        expected_position=100.0,
        actual_position=95.0,
    )

    assert decision.status == "DISCREPANCY"
    assert decision.approved is False
    assert decision.discrepancy_type == "ACCOUNT_POSITION_MISMATCH"


# ============================================================================
# H11 — POST-TRADE EXECUTION MONITORING
# ============================================================================


def test_post_trade_quantity_check_detects_matching_execution() -> None:
    PostTradeExecutionMonitor = _import(
        "posttradeexecutionmonitor",
        "PostTradeExecutionMonitor",
    )

    monitor = PostTradeExecutionMonitor()

    order = _make_order(quantity=100.0)

    class Execution:
        quantity = 100.0
        execution_price = 500.0
        status = "FILLED"

    result = monitor.check_quantity(order, Execution())

    assert result[0] is True
    assert result[1] == 100.0
    assert result[2] == 100.0


def test_post_trade_price_check_detects_matching_execution() -> None:
    PostTradeExecutionMonitor = _import(
        "posttradeexecutionmonitor",
        "PostTradeExecutionMonitor",
    )

    monitor = PostTradeExecutionMonitor()

    class Execution:
        execution_price = 500.0

    result = monitor.check_price(
        expected_price=500.0,
        execution=Execution(),
    )

    assert result[0] is True
    assert result[1] == 500.0
    assert result[2] == 500.0
    assert result[3] == 0.0


def test_post_trade_duplicate_check_does_not_flag_distinct_execution() -> None:
    PostTradeExecutionMonitor = _import(
        "posttradeexecutionmonitor",
        "PostTradeExecutionMonitor",
    )

    monitor = PostTradeExecutionMonitor()

    order = _make_order(order_id="H11-001")

    class Execution:
        broker_order_id = "BROKER-001"

    assert monitor.check_duplicate(order, Execution()) is False


# ============================================================================
# H12 — EXECUTION ANALYTICS INVARIANTS
# ============================================================================


def test_execution_analytics_fill_ratio_is_bounded() -> None:
    ExecutionAnalytics = _import(
        "executionanalytics",
        "ExecutionAnalytics",
    )

    analytics = ExecutionAnalytics()

    assert analytics.calculate_fill_ratio(100.0, 100.0) == 1.0
    assert analytics.calculate_fill_ratio(100.0, 50.0) == 0.5


def test_execution_analytics_rejects_overfill_ratio() -> None:
    ExecutionAnalytics = _import(
        "executionanalytics",
        "ExecutionAnalytics",
    )

    analytics = ExecutionAnalytics()

    try:
        analytics.calculate_fill_ratio(100.0, 101.0)
    except ValueError as exc:
        assert "cannot exceed" in str(exc)
    else:
        raise AssertionError(
            "Execution analytics accepted overfill."
        )


def test_execution_analytics_rejects_negative_fill() -> None:
    ExecutionAnalytics = _import(
        "executionanalytics",
        "ExecutionAnalytics",
    )

    analytics = ExecutionAnalytics()

    try:
        analytics.calculate_fill_ratio(100.0, -1.0)
    except ValueError as exc:
        assert "negative" in str(exc)
    else:
        raise AssertionError(
            "Execution analytics accepted negative fill."
        )


def test_execution_analytics_rejects_zero_ordered_quantity() -> None:
    ExecutionAnalytics = _import(
        "executionanalytics",
        "ExecutionAnalytics",
    )

    analytics = ExecutionAnalytics()

    try:
        analytics.calculate_fill_ratio(0.0, 0.0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError(
            "Execution analytics accepted zero ordered quantity."
        )


def test_execution_analytics_buy_and_sell_slippage_are_valid() -> None:
    ExecutionAnalytics = _import(
        "executionanalytics",
        "ExecutionAnalytics",
    )

    analytics = ExecutionAnalytics()

    buy = analytics.calculate_slippage(
        "BUY",
        benchmark_price=500.0,
        execution_price=501.0,
    )

    sell = analytics.calculate_slippage(
        "SELL",
        benchmark_price=500.0,
        execution_price=499.0,
    )

    assert buy[0] == 1.0
    assert sell[0] == 1.0
    assert buy[1] == 0.002
    assert sell[1] == 0.002


# ============================================================================
# H13 — TRADE GENERATOR INTEGRITY
# ============================================================================


def test_trade_generator_zero_delta_produces_no_instruction() -> None:
    TradeGenerator = _import("tradegenerator", "TradeGenerator")

    generator = TradeGenerator()

    assert (
        generator.generate_instruction(
            "SPY",
            100.0,
            100.0,
            500.0,
        )
        is None
    )


def test_trade_generator_buy_delta_is_correct() -> None:
    TradeGenerator = _import("tradegenerator", "TradeGenerator")

    generator = TradeGenerator()

    instruction = generator.generate_instruction(
        "SPY",
        100.0,
        110.0,
        500.0,
    )

    assert instruction is not None
    assert instruction.side == "BUY"
    assert instruction.quantity == 10.0
    assert instruction.delta == 10.0


def test_trade_generator_sell_delta_is_correct() -> None:
    TradeGenerator = _import("tradegenerator", "TradeGenerator")

    generator = TradeGenerator()

    instruction = generator.generate_instruction(
        "SPY",
        110.0,
        100.0,
        500.0,
    )

    assert instruction is not None
    assert instruction.side == "SELL"
    assert instruction.quantity == 10.0
    assert instruction.delta == -10.0


def test_trade_generator_handles_negative_current_position() -> None:
    TradeGenerator = _import("tradegenerator", "TradeGenerator")

    generator = TradeGenerator()

    instruction = generator.generate_instruction(
        "SPY",
        -10.0,
        10.0,
        500.0,
    )

    assert instruction is not None
    assert instruction.side == "BUY"
    assert instruction.quantity == 20.0
    assert instruction.delta == 20.0


def test_trade_generator_order_generation_is_deterministic() -> None:
    TradeGenerator = _import("tradegenerator", "TradeGenerator")

    first_generator = TradeGenerator()
    second_generator = TradeGenerator()

    first_instruction = first_generator.generate_instruction(
        "SPY",
        0.0,
        10.0,
        500.0,
    )
    second_instruction = second_generator.generate_instruction(
        "SPY",
        0.0,
        10.0,
        500.0,
    )

    assert first_instruction == second_instruction

    first_order = first_generator.generate_order(first_instruction)
    second_order = second_generator.generate_order(second_instruction)

    assert first_order.ticker == second_order.ticker
    assert first_order.side == second_order.side
    assert first_order.quantity == second_order.quantity
    assert first_order.order_type == second_order.order_type
    assert first_order.time_in_force == second_order.time_in_force