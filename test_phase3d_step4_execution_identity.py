"""
======================================================================
Phase 3D Step 4 — Execution Identity and Partial-Fill Integrity
======================================================================

Certifies separation of:
    decision_id
    order_id
    broker_order_id
    execution_id
    fill_id

and the cumulative quantity invariants at the paper-broker and broker-
execution boundaries.
"""

from __future__ import annotations

import pytest

from order import Order
from paperbroker import PaperBroker


def test_order_identity_fields_are_immutable() -> None:
    order = Order(
        ticker="SPY",
        side="BUY",
        quantity=100.0,
        order_id="ORD-ID-001",
        decision_id="PDEC-TEST-00000001",
    )

    for field, value in (
        ("order_id", "ORD-ID-002"),
        ("ticker", "QQQ"),
        ("side", "SELL"),
        ("quantity", 50.0),
        ("decision_id", "PDEC-TEST-00000002"),
    ):
        with pytest.raises(AttributeError):
            setattr(order, field, value)


def test_order_quantity_invariants() -> None:
    order = Order(
        ticker="SPY",
        side="BUY",
        quantity=100.0,
        decision_id="PDEC-TEST-00000001",
    )

    order.fill(40.0, 500.0)
    assert order.filled_quantity == 40.0
    assert order.remaining_quantity == 60.0

    order.fill(60.0, 501.0)
    assert order.filled_quantity == 100.0
    assert order.remaining_quantity == 0.0
    assert order.status == "FILLED"

    with pytest.raises(ValueError):
        order.fill(1.0, 502.0)


def test_paper_broker_distinguishes_broker_order_execution_and_fill_ids() -> None:
    broker = PaperBroker()
    order = Order(
        ticker="SPY",
        side="BUY",
        quantity=100.0,
        order_id="ORD-ID-003",
        decision_id="PDEC-TEST-00000003",
    )

    submission = broker.submit_order(order)
    assert submission["client_order_id"] == order.order_id
    broker_order_id = submission["broker_order_id"]
    assert broker_order_id != order.order_id

    first = broker.fill_order(order.order_id, 500.0, quantity=40.0)
    second = broker.fill_order(order.order_id, 501.0, quantity=60.0)

    assert first.execution_id != second.execution_id
    assert first.fill_id != second.fill_id
    assert first.execution_id
    assert first.fill_id
    assert first.decision_id == order.decision_id
    assert second.decision_id == order.decision_id
    assert first.broker_order_id == broker_order_id
    assert second.broker_order_id == broker_order_id

    record = broker.get_order(order.order_id)
    assert record.filled_quantity == 100.0
    assert record.remaining_quantity == 0.0
    assert tuple(record.execution_ids) == (
        first.execution_id,
        second.execution_id,
    )
    assert tuple(record.fill_ids) == (first.fill_id, second.fill_id)
    assert record.status == "FILLED"


def test_paper_broker_rejects_overfill() -> None:
    broker = PaperBroker()
    order = Order(
        ticker="SPY",
        side="BUY",
        quantity=100.0,
        order_id="ORD-ID-004",
        decision_id="PDEC-TEST-00000004",
    )
    broker.submit_order(order)
    broker.fill_order(order.order_id, 500.0, quantity=70.0)

    with pytest.raises(ValueError, match="remaining quantity"):
        broker.fill_order(order.order_id, 500.0, quantity=31.0)


def test_paper_broker_execution_and_fill_sequences_are_distinct() -> None:
    broker = PaperBroker()
    order = Order(
        ticker="SPY",
        side="BUY",
        quantity=10.0,
        decision_id="PDEC-TEST-00000005",
    )
    broker.submit_order(order)
    receipt = broker.fill_order(order.order_id, 500.0, quantity=5.0)

    assert receipt.execution_id.startswith("PEXEC-")
    assert receipt.fill_id.startswith("PFILL-")
    assert receipt.execution_id != receipt.fill_id
