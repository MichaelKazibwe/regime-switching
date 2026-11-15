"""
======================================================================
test_phase3d_step6_restart_integrity.py

Phase III-D Step 6 — Durable State and Restart Integrity
======================================================================
"""

from __future__ import annotations

import copy

import pytest

from brokerexecutionengine import BrokerExecutionEngine
from executionengine import ExecutionEngine
from order import Order
from paperbroker import PaperBroker
from portfolioaccount import PortfolioAccount, Position
from posttradeexecutionmonitor import PostTradeExecutionMonitor
from reconciliationengine import ReconciliationEngine


def _build_state():
    broker = PaperBroker()
    execution_engine = ExecutionEngine()
    broker_execution = BrokerExecutionEngine(execution_engine=execution_engine)
    account = PortfolioAccount(initial_cash=100_000.0)
    order = Order(
        order_id="STEP6-001",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
        decision_id="PDEC-STEP6-001",
    )

    submission = broker.submit_order(order)
    broker_order_id = submission["broker_order_id"]

    first_receipt = broker.fill_order(
        broker_order_id,
        execution_price=500.0,
        quantity=40.0,
    )
    first_result = broker_execution.execute_receipt(
        order,
        first_receipt,
        account,
    )
    assert first_result.approved

    return (
        broker,
        execution_engine,
        broker_execution,
        account,
        order,
        first_receipt,
        broker_order_id,
    )


def test_restart_preserves_all_identity_and_accounting_state():
    (
        broker,
        execution_engine,
        broker_execution,
        account,
        order,
        first_receipt,
        broker_order_id,
    ) = _build_state()

    broker_restored = PaperBroker.from_dict(copy.deepcopy(broker.to_dict()))
    execution_restored = ExecutionEngine.from_dict(copy.deepcopy(execution_engine.to_dict()))
    broker_execution_restored = BrokerExecutionEngine.from_dict(
        copy.deepcopy(broker_execution.to_dict()),
        execution_engine=execution_restored,
    )
    account_restored = PortfolioAccount.from_dict(copy.deepcopy(account.to_dict()))
    order_restored = Order.from_dict(copy.deepcopy(order.to_dict()))

    assert broker_restored.get_order(broker_order_id).filled_quantity == 40.0
    assert broker_restored.get_order(broker_order_id).remaining_quantity == 60.0
    assert broker_restored.get_order(broker_order_id).decision_id == order.decision_id
    assert broker_restored.get_order(broker_order_id).execution_ids == (first_receipt.execution_id,)
    assert broker_restored.get_order(broker_order_id).fill_ids == (first_receipt.fill_id,)

    assert order_restored.order_id == order.order_id
    assert order_restored.decision_id == order.decision_id
    assert order_restored.filled_quantity == 40.0
    assert order_restored.remaining_quantity == 60.0
    assert order_restored.average_fill_price == 500.0

    assert account_restored.cash == account.cash
    assert account_restored.positions["SPY"].shares == 40.0
    assert account_restored.positions["SPY"].average_cost == 500.0
    assert len(account_restored.trade_history) == 1

    assert broker_execution_restored.execution_id_registry == broker_execution.execution_id_registry
    assert broker_execution_restored.fill_id_registry == broker_execution.fill_id_registry
    assert broker_execution_restored.execution_count == broker_execution.execution_count
    assert broker_execution_restored.last_result is not None
    assert broker_execution_restored.last_result.execution_id == first_receipt.execution_id

    assert execution_restored.execution_count == execution_engine.execution_count
    assert len(execution_restored.execution_history) == len(execution_engine.execution_history)
    assert execution_restored.last_trade is not None


def test_replay_after_restart_is_rejected_without_accounting_change():
    (
        broker,
        execution_engine,
        broker_execution,
        account,
        order,
        first_receipt,
        _,
    ) = _build_state()

    broker_execution_restored = BrokerExecutionEngine.from_dict(
        copy.deepcopy(broker_execution.to_dict()),
        execution_engine=ExecutionEngine.from_dict(copy.deepcopy(execution_engine.to_dict())),
    )
    account_restored = PortfolioAccount.from_dict(copy.deepcopy(account.to_dict()))
    order_restored = Order.from_dict(copy.deepcopy(order.to_dict()))

    cash_before = account_restored.cash
    shares_before = account_restored.positions["SPY"].shares
    history_before = len(account_restored.trade_history)

    with pytest.raises(RuntimeError, match="Duplicate broker execution"):
        broker_execution_restored.execute_receipt(
            order_restored,
            first_receipt,
            account_restored,
        )

    assert account_restored.cash == cash_before
    assert account_restored.positions["SPY"].shares == shares_before
    assert len(account_restored.trade_history) == history_before


def test_restart_preserves_execution_and_fill_sequences():
    (
        broker,
        _,
        _,
        _,
        _,
        first_receipt,
        broker_order_id,
    ) = _build_state()

    restored = PaperBroker.from_dict(copy.deepcopy(broker.to_dict()))
    second_receipt = restored.fill_order(
        broker_order_id,
        execution_price=505.0,
        quantity=60.0,
    )

    assert second_receipt.execution_id != first_receipt.execution_id
    assert second_receipt.fill_id != first_receipt.fill_id
    assert second_receipt.execution_id == "PEXEC-000000000002"
    assert second_receipt.fill_id == "PFILL-000000000002"


def test_position_identity_and_average_cost_survive_restart():
    account = PortfolioAccount(initial_cash=100_000.0)
    account.positions["SPY"] = account.positions.get("SPY") or Position(
        ticker="SPY",
        shares=100.0,
        average_cost=503.0,
        market_price=510.0,
        trade_id="TRADE-STEP6",
        broker="PAPER",
        exchange="NYSE",
        currency="USD",
    )

    restored = PortfolioAccount.from_dict(copy.deepcopy(account.to_dict()))
    position = restored.positions["SPY"]

    assert position.shares == 100.0
    assert position.average_cost == 503.0
    assert position.market_price == 510.0
    assert position.trade_id == "TRADE-STEP6"
    assert position.broker == "PAPER"
    assert position.exchange == "NYSE"
    assert position.currency == "USD"


def test_restart_preserves_reconciliation_and_posttrade_identity_registries():
    monitor = PostTradeExecutionMonitor()
    reconciliation = ReconciliationEngine()
    order = Order(
        order_id="STEP6-002",
        ticker="QQQ",
        side="BUY",
        quantity=10.0,
    )

    event = {
        "broker_order_id": "PAPER-STEP6-002",
        "client_order_id": order.order_id,
        "ticker": "QQQ",
        "side": "BUY",
        "quantity": 10.0,
        "execution_price": 400.0,
        "status": "FILLED",
        "execution_id": "PEXEC-STEP6-002",
        "fill_id": "PFILL-STEP6-002",
        "cumulative_filled_quantity": 10.0,
        "remaining_quantity": 0.0,
    }

    monitor.monitor_execution(order, event, expected_price=400.0)
    monitor_restored = PostTradeExecutionMonitor.from_dict(copy.deepcopy(monitor.to_dict()))

    assert monitor_restored.check_duplicate(order, event) is True
    assert monitor_restored.summary()["monitor_count"] == monitor.summary()["monitor_count"]
    assert monitor_restored.health_check()

    reconciliation_restored = ReconciliationEngine.from_dict(copy.deepcopy(reconciliation.to_dict()))
    assert reconciliation_restored.reconciliation_count == reconciliation.reconciliation_count
    assert reconciliation_restored.last_decision == reconciliation.last_decision
    assert reconciliation_restored.health_check()


def test_restart_preserves_trade_objects_not_plain_dicts():
    (
        _broker,
        _execution_engine,
        _broker_execution,
        account,
        _order,
        _first_receipt,
        _broker_order_id,
    ) = _build_state()

    restored = PortfolioAccount.from_dict(copy.deepcopy(account.to_dict()))

    assert restored.trade_history
    assert all(hasattr(trade, "validate") for trade in restored.trade_history)
    assert restored.trade_history[0].ticker == "SPY"
    assert restored.trade_history[0].shares == 40.0
    assert restored.health_check()


def test_restart_rejects_corrupted_account_history():
    account = PortfolioAccount(initial_cash=100_000.0)
    payload = account.to_dict()
    payload["turnover_history"] = [1.0]

    with pytest.raises(ValueError, match="turnover_history length"):
        PortfolioAccount.from_dict(payload)


def test_restart_rejects_corrupted_execution_state():
    engine = ExecutionEngine()
    payload = engine.to_dict()
    payload["execution_history"] = {"invalid": True}

    with pytest.raises(ValueError, match="execution_history must be a list"):
        ExecutionEngine.from_dict(payload)


def test_restart_preserves_reconciliation_history_after_real_reconciliation():
    oms = Order(
        order_id="STEP6-003",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
    )
    oms.fill(100.0, 500.0)

    broker = PaperBroker()
    submission = broker.submit_order(
        Order(
            order_id="STEP6-003",
            ticker="SPY",
            side="BUY",
            quantity=100.0,
        )
    )
    broker_record = broker.get_order(submission["broker_order_id"])
    broker.fill_order(
        submission["broker_order_id"],
        execution_price=500.0,
        quantity=100.0,
    )
    broker_record = broker.get_order(submission["broker_order_id"])

    engine = ReconciliationEngine()
    decision = engine.reconcile_order(oms, broker_record)
    assert decision.approved
    assert engine.reconciliation_count == 1

    restored = ReconciliationEngine.from_dict(copy.deepcopy(engine.to_dict()))

    assert restored.reconciliation_count == 1
    assert restored.matched_count == 1
    assert restored.last_decision is not None
    assert restored.last_decision.status == decision.status
    assert restored.health_check()



def test_restart_continues_legitimate_partial_fill_end_to_end():
    (
        broker,
        execution_engine,
        broker_execution,
        account,
        order,
        first_receipt,
        broker_order_id,
    ) = _build_state()

    broker_restored = PaperBroker.from_dict(copy.deepcopy(broker.to_dict()))
    execution_restored = ExecutionEngine.from_dict(
        copy.deepcopy(execution_engine.to_dict())
    )
    broker_execution_restored = BrokerExecutionEngine.from_dict(
        copy.deepcopy(broker_execution.to_dict()),
        execution_engine=execution_restored,
    )
    account_restored = PortfolioAccount.from_dict(
        copy.deepcopy(account.to_dict())
    )
    order_restored = Order.from_dict(copy.deepcopy(order.to_dict()))

    second_receipt = broker_restored.fill_order(
        broker_order_id,
        execution_price=505.0,
        quantity=60.0,
    )

    result = broker_execution_restored.execute_receipt(
        order_restored,
        second_receipt,
        account_restored,
    )

    assert result.approved
    assert second_receipt.execution_id not in {
        first_receipt.execution_id
    }
    assert second_receipt.fill_id not in {first_receipt.fill_id}
    assert order_restored.filled_quantity == 100.0
    assert order_restored.remaining_quantity == 0.0
    assert order_restored.status == "FILLED"
    assert account_restored.positions["SPY"].shares == 100.0
    assert account_restored.cash < account.cash
    assert len(account_restored.trade_history) == 2
    assert broker_restored.get_order(broker_order_id).filled_quantity == 100.0
    assert broker_restored.get_order(broker_order_id).remaining_quantity == 0.0
    assert broker_restored.get_order(broker_order_id).status == "FILLED"
    assert broker_execution_restored.execution_count == 2
    assert broker_execution_restored.has_execution(second_receipt.execution_id)
    assert second_receipt.fill_id in broker_execution_restored.fill_id_registry
