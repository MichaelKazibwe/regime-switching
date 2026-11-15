"""
======================================================================
test_phase3d_step5_reconciliation_integrity.py

Phase 3D Step 5 — Reconciliation Integrity Regression Tests
======================================================================

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from dataclasses import dataclass

import pytest

from reconciliationengine import (
    DiscrepancyType,
    ReconciliationEngine,
    ReconciliationStatus,
)


@dataclass
class State:
    order_id: str = "ORD-001"
    broker_order_id: str = "BROKER-001"
    ticker: str = "SPY"
    side: str = "BUY"
    status: str = "PARTIALLY_FILLED"
    quantity: float = 100.0
    filled_quantity: float = 40.0
    remaining_quantity: float = 60.0
    average_fill_price: float = 500.0


def test_partial_fill_then_cancel_is_reconcilable() -> None:
    engine = ReconciliationEngine()
    oms = State(status="CANCELLED")
    broker = State(status="CANCELLED")

    decision = engine.reconcile_order(oms, broker)

    assert decision.status == ReconciliationStatus.MATCHED
    assert decision.approved is True
    assert decision.oms_filled_quantity == 40.0
    assert decision.oms_remaining_quantity == 60.0


def test_filled_state_requires_full_quantity_and_zero_remaining() -> None:
    engine = ReconciliationEngine()
    oms = State(
        status="FILLED",
        filled_quantity=90.0,
        remaining_quantity=10.0,
    )
    broker = State(
        status="FILLED",
        filled_quantity=90.0,
        remaining_quantity=10.0,
    )

    decision = engine.reconcile_order(oms, broker)

    assert decision.status == ReconciliationStatus.DISCREPANCY
    assert decision.approved is False
    assert decision.discrepancy_type == DiscrepancyType.INVALID_OMS_STATE


def test_partial_fill_state_cannot_have_zero_remaining() -> None:
    engine = ReconciliationEngine()
    oms = State(
        status="PARTIALLY_FILLED",
        filled_quantity=100.0,
        remaining_quantity=0.0,
    )
    broker = State(
        status="PARTIALLY_FILLED",
        filled_quantity=100.0,
        remaining_quantity=0.0,
    )

    decision = engine.reconcile_order(oms, broker)

    assert decision.status == ReconciliationStatus.DISCREPANCY
    assert decision.approved is False
    assert decision.discrepancy_type == DiscrepancyType.INVALID_OMS_STATE


def test_remaining_quantity_must_equal_quantity_minus_fill() -> None:
    engine = ReconciliationEngine()
    oms = State(remaining_quantity=50.0)
    broker = State(remaining_quantity=50.0)

    decision = engine.reconcile_order(oms, broker)

    assert decision.status == ReconciliationStatus.DISCREPANCY
    assert decision.approved is False
    assert decision.discrepancy_type == DiscrepancyType.INVALID_OMS_STATE


def test_rejected_order_cannot_contain_fills() -> None:
    engine = ReconciliationEngine()
    oms = State(
        status="REJECTED",
        filled_quantity=10.0,
        remaining_quantity=90.0,
    )
    broker = State(
        status="REJECTED",
        filled_quantity=10.0,
        remaining_quantity=90.0,
    )

    decision = engine.reconcile_order(oms, broker)

    assert decision.status == ReconciliationStatus.DISCREPANCY
    assert decision.approved is False
    assert decision.discrepancy_type == DiscrepancyType.INVALID_OMS_STATE


def test_broker_invalid_state_is_fail_closed_after_valid_oms() -> None:
    engine = ReconciliationEngine()
    oms = State(
        status="PARTIALLY_FILLED",
        filled_quantity=100.0,
        remaining_quantity=0.0,
    )
    broker = State(
        status="PARTIALLY_FILLED",
        filled_quantity=100.0,
        remaining_quantity=0.0,
    )

    decision = engine.reconcile_order(oms, broker)

    assert decision.status == ReconciliationStatus.DISCREPANCY
    assert decision.approved is False
    assert decision.discrepancy_type == DiscrepancyType.INVALID_OMS_STATE


def test_reconciliation_is_read_only() -> None:
    engine = ReconciliationEngine()
    oms = State()
    broker = State()

    before_oms = oms.__dict__.copy()
    before_broker = broker.__dict__.copy()

    engine.reconcile_order(oms, broker)

    assert oms.__dict__ == before_oms
    assert broker.__dict__ == before_broker


def test_nonfinite_quantities_remain_fail_closed() -> None:
    engine = ReconciliationEngine()
    oms = State(quantity=float("inf"))
    broker = State(quantity=float("inf"))

    with pytest.raises(ValueError):
        engine.reconcile_order(oms, broker)
