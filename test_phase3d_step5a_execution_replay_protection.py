"""
======================================================================
test_phase3d_step5a_execution_replay_protection.py

Phase III-D Step 5A — Execution Event Replay Protection
======================================================================

Deterministic regression tests for the execution identity boundary.

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from __future__ import annotations

import importlib
import sys
import types

import pytest


class _ExecutionEngineStub:
    def execute(self, order, account, execution_price, quantity=None):
        raise AssertionError("Duplicate/replayed execution reached accounting.")

    def health_check(self):
        return True


class _PortfolioAccountStub:
    def health_check(self):
        return True


def _import_module():
    sys.modules["executionengine"] = types.SimpleNamespace(
        ExecutionEngine=_ExecutionEngineStub,
    )
    sys.modules["portfolioaccount"] = types.SimpleNamespace(
        PortfolioAccount=_PortfolioAccountStub,
    )
    sys.path.insert(0, "/mnt/data/phase3d_step4_work")
    sys.path.insert(0, "/mnt/data/phase3d_step5_work")
    sys.modules.pop("brokerexecutionengine", None)
    return importlib.import_module("brokerexecutionengine")


def _make_order_and_receipt(bee):
    Order = importlib.import_module("order").Order
    PaperBroker = importlib.import_module("paperbroker").PaperBroker

    order = Order(
        order_id="STEP5A-001",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
        decision_id="PDEC-TEST-00000001",
    )
    broker = PaperBroker()
    broker.submit_order(order)
    receipt = broker.fill_order(
        order.order_id,
        execution_price=500.0,
        quantity=40.0,
    )
    return order, broker, receipt


def _seed_processed_result(bee, receipt):
    result = bee.BrokerExecutionResult(
        approved=True,
        status=bee.BrokerExecutionStatus.PARTIALLY_EXECUTED,
        broker=receipt.broker,
        broker_order_id=receipt.broker_order_id,
        client_order_id=receipt.client_order_id,
        ticker=receipt.ticker,
        side=receipt.side,
        quantity=float(receipt.quantity),
        execution_price=float(receipt.execution_price),
        reason=None,
        execution_id=receipt.execution_id,
        timestamp=receipt.timestamp,
        trade=None,
        receipt=receipt.to_dict(),
        decision_id=receipt.decision_id,
        fill_id=receipt.fill_id,
    )
    key = bee.BrokerExecutionEngine._registry_key(receipt)
    bridge = bee.BrokerExecutionEngine(execution_engine=_ExecutionEngineStub())
    bridge._record_result(result, key)
    return bridge


def test_replayed_execution_id_is_rejected_even_with_new_fill_id():
    bee = _import_module()
    order, broker, receipt = _make_order_and_receipt(bee)
    bridge = _seed_processed_result(bee, receipt)

    PaperExecutionReceipt = importlib.import_module("paperbroker").PaperExecutionReceipt
    replay = PaperExecutionReceipt(
        broker_order_id=receipt.broker_order_id,
        client_order_id=receipt.client_order_id,
        ticker=receipt.ticker,
        side=receipt.side,
        quantity=10.0,
        execution_price=501.0,
        status="PARTIALLY_FILLED",
        timestamp=receipt.timestamp,
        broker=receipt.broker,
        execution_id=receipt.execution_id,
        fill_id="PFILL-REPLAY-00000001",
        decision_id=receipt.decision_id,
    )

    with pytest.raises(RuntimeError, match="Duplicate broker execution"):
        bridge.execute_receipt(
            order,
            replay,
            _PortfolioAccountStub(),
        )


def test_replayed_fill_id_is_rejected_even_with_new_execution_id():
    bee = _import_module()
    order, broker, receipt = _make_order_and_receipt(bee)
    bridge = _seed_processed_result(bee, receipt)

    PaperExecutionReceipt = importlib.import_module("paperbroker").PaperExecutionReceipt
    replay = PaperExecutionReceipt(
        broker_order_id=receipt.broker_order_id,
        client_order_id=receipt.client_order_id,
        ticker=receipt.ticker,
        side=receipt.side,
        quantity=10.0,
        execution_price=501.0,
        status="PARTIALLY_FILLED",
        timestamp=receipt.timestamp,
        broker=receipt.broker,
        execution_id="PEXEC-REPLAY-00000001",
        fill_id=receipt.fill_id,
        decision_id=receipt.decision_id,
    )

    with pytest.raises(RuntimeError, match="Duplicate broker execution"):
        bridge.execute_receipt(
            order,
            replay,
            _PortfolioAccountStub(),
        )


def test_serialization_preserves_replay_registries():
    bee = _import_module()
    _, _, receipt = _make_order_and_receipt(bee)
    bridge = _seed_processed_result(bee, receipt)

    exported = bridge.to_dict()
    restored = bee.BrokerExecutionEngine.from_dict(
        exported,
        execution_engine=_ExecutionEngineStub(),
    )

    assert receipt.execution_id in restored.execution_id_registry
    assert receipt.fill_id in restored.fill_id_registry
    assert restored.has_execution(
        bridge._registry_key(receipt)
    )
    assert restored.health_check()


def test_duplicate_result_is_counted_once():
    bee = _import_module()
    order, _, receipt = _make_order_and_receipt(bee)
    bridge = _seed_processed_result(bee, receipt)

    before = bridge.duplicate_count
    with pytest.raises(RuntimeError, match="Duplicate broker execution"):
        bridge.execute_receipt(
            order,
            receipt,
            _PortfolioAccountStub(),
        )

    assert bridge.duplicate_count == before + 1


def test_malformed_serialized_registry_entry_fails_closed():
    bee = _import_module()
    _, _, receipt = _make_order_and_receipt(bee)
    bridge = _seed_processed_result(bee, receipt)
    exported = bridge.to_dict()
    exported["execution_registry"]["BROKEN"] = "not-a-dict"

    with pytest.raises(ValueError, match="execution_registry entries"):
        bee.BrokerExecutionEngine.from_dict(
            exported,
            execution_engine=_ExecutionEngineStub(),
        )
