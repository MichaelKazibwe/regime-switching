"""
======================================================================
test_phase3d_step5c_posttrade_lifecycle.py

Phase III-D Step 5C — Post-Trade Lifecycle Integrity
======================================================================

Deterministic regression tests for post-trade execution identity,
partial-fill lifecycle semantics, missing execution handling, and
serialization/recovery.

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from __future__ import annotations

from order import Order
from posttradeexecutionmonitor import (
    ExecutionDiscrepancy,
    PostTradeExecutionMonitor,
    PostTradeStatus,
)


def _execution(
    *,
    broker_order_id: str = "PAPER-001",
    execution_id: str = "PEXEC-0001",
    fill_id: str = "PFILL-0001",
    quantity: float = 40.0,
    price: float = 500.0,
    status: str = "PARTIALLY_FILLED",
) -> dict:
    return {
        "broker_order_id": broker_order_id,
        "client_order_id": "STEP5C-001",
        "ticker": "SPY",
        "side": "BUY",
        "quantity": quantity,
        "execution_price": price,
        "status": status,
        "execution_id": execution_id,
        "fill_id": fill_id,
        "timestamp": "2026-09-07T20:00:00+00:00",
    }


def test_multiple_partial_fills_same_broker_order_are_not_duplicates() -> None:
    monitor = PostTradeExecutionMonitor()
    order = Order(
        order_id="STEP5C-001",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
    )

    first = _execution(
        execution_id="PEXEC-0001",
        fill_id="PFILL-0001",
        quantity=40.0,
    )
    second = _execution(
        execution_id="PEXEC-0002",
        fill_id="PFILL-0002",
        quantity=60.0,
    )

    assert monitor.check_duplicate(order, first) is False
    first_result = monitor.monitor_execution(
        order,
        first,
        expected_price=500.0,
    )
    assert first_result.approved
    assert first_result.status == PostTradeStatus.PARTIALLY_CONFIRMED

    assert monitor.check_duplicate(order, second) is False
    second_result = monitor.monitor_execution(
        order,
        second,
        expected_price=500.0,
    )
    assert second_result.approved
    assert second_result.status == PostTradeStatus.PARTIALLY_CONFIRMED

    assert monitor.summary()["partial_count"] == 2


def test_duplicate_execution_or_fill_identity_is_rejected() -> None:
    monitor = PostTradeExecutionMonitor()
    order = Order(
        order_id="STEP5C-001",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
    )

    first = _execution(
        execution_id="PEXEC-0001",
        fill_id="PFILL-0001",
    )
    monitor.monitor_execution(order, first, expected_price=500.0)

    same_execution_new_fill = _execution(
        execution_id="PEXEC-0001",
        fill_id="PFILL-9999",
        quantity=10.0,
    )
    result = monitor.monitor_execution(
        order,
        same_execution_new_fill,
        expected_price=500.0,
    )
    assert not result.approved
    assert result.status == PostTradeStatus.DUPLICATE
    assert result.reason == ExecutionDiscrepancy.DUPLICATE_EXECUTION

    same_fill_new_execution = _execution(
        execution_id="PEXEC-9999",
        fill_id="PFILL-0001",
        quantity=10.0,
    )
    result = monitor.monitor_execution(
        order,
        same_fill_new_execution,
        expected_price=500.0,
    )
    assert not result.approved
    assert result.status == PostTradeStatus.DUPLICATE


def test_filled_status_cannot_be_approved_for_partial_quantity() -> None:
    monitor = PostTradeExecutionMonitor()
    order = Order(
        order_id="STEP5C-001",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
    )

    result = monitor.monitor_execution(
        order,
        _execution(
            quantity=40.0,
            status="FILLED",
            execution_id="PEXEC-0003",
            fill_id="PFILL-0003",
        ),
        expected_price=500.0,
    )

    assert not result.approved
    assert result.status == PostTradeStatus.DISCREPANCY
    assert result.reason == ExecutionDiscrepancy.STATUS_MISMATCH


def test_missing_execution_is_reachable_and_fail_closed() -> None:
    monitor = PostTradeExecutionMonitor()
    order = Order(
        order_id="STEP5C-001",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
    )

    result = monitor.monitor_execution(order, None)

    assert not result.approved
    assert result.status == PostTradeStatus.MISSING
    assert result.reason == ExecutionDiscrepancy.MISSING_EXECUTION
    assert monitor.summary()["missing_count"] == 1


def test_identity_registries_survive_serialization_and_recovery() -> None:
    monitor = PostTradeExecutionMonitor()
    order = Order(
        order_id="STEP5C-001",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
    )

    event = _execution(
        execution_id="PEXEC-0007",
        fill_id="PFILL-0007",
    )
    monitor.monitor_execution(order, event, expected_price=500.0)

    restored = PostTradeExecutionMonitor.from_dict(monitor.to_dict())

    assert restored.check_duplicate(order, event) is True
    assert restored.summary()["monitor_count"] == monitor.summary()["monitor_count"]
    assert restored.health_check()


def test_final_partial_fill_with_filled_broker_status_uses_cumulative_quantity() -> None:
    monitor = PostTradeExecutionMonitor()
    order = Order(
        order_id="STEP5C-002",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
    )

    final_fill = _execution(
        broker_order_id="PAPER-002",
        execution_id="PEXEC-0010",
        fill_id="PFILL-0010",
        quantity=60.0,
        status="FILLED",
    )
    final_fill["cumulative_filled_quantity"] = 100.0
    final_fill["remaining_quantity"] = 0.0
    final_fill["client_order_id"] = order.order_id

    result = monitor.monitor_execution(
        order,
        final_fill,
        expected_price=500.0,
    )

    assert result.approved
    assert result.status == PostTradeStatus.CONFIRMED
    assert result.executed_quantity == 100.0
    assert result.remaining_quantity == 0.0
