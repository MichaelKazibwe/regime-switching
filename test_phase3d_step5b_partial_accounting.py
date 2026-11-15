"""
======================================================================
test_phase3d_step5b_partial_accounting.py

Phase III-D Step 5B — Authoritative Partial-Fill Accounting
======================================================================
"""

from __future__ import annotations

from executionengine import ExecutionEngine
from order import Order
from portfolioaccount import PortfolioAccount


def test_partial_fill_updates_order_and_account_consistently():
    engine = ExecutionEngine()
    account = PortfolioAccount(initial_cash=100_000.0)
    order = Order(
        order_id="STEP5B-001",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
        decision_id="PDEC-STEP5B-001",
    )

    first = engine.execute(
        order,
        account,
        execution_price=500.0,
        quantity=40.0,
    )

    assert first.shares == 40.0
    assert order.filled_quantity == 40.0
    assert order.remaining_quantity == 60.0
    assert order.status == "PARTIALLY_FILLED"
    assert account.positions["SPY"].shares == 40.0

    second = engine.execute(
        order,
        account,
        execution_price=505.0,
        quantity=60.0,
    )

    assert second.shares == 60.0
    assert order.filled_quantity == 100.0
    assert order.remaining_quantity == 0.0
    assert order.status == "FILLED"
    assert account.positions["SPY"].shares == 100.0
    assert len(account.trade_history) == 2
    assert engine.execution_count == 2


def test_partial_fill_cannot_exceed_remaining_quantity():
    engine = ExecutionEngine()
    account = PortfolioAccount(initial_cash=100_000.0)
    order = Order(
        order_id="STEP5B-002",
        ticker="SPY",
        side="BUY",
        quantity=100.0,
    )

    engine.execute(order, account, 500.0, quantity=75.0)

    try:
        engine.execute(order, account, 500.0, quantity=26.0)
    except ValueError as exc:
        assert "remaining quantity" in str(exc)
    else:
        raise AssertionError("ExecutionEngine accepted an overfill.")

    assert order.filled_quantity == 75.0
    assert order.remaining_quantity == 25.0
    assert account.positions["SPY"].shares == 75.0


def test_legacy_full_execution_path_remains_unchanged():
    engine = ExecutionEngine()
    account = PortfolioAccount(initial_cash=100_000.0)
    order = Order(
        order_id="STEP5B-003",
        ticker="QQQ",
        side="BUY",
        quantity=10.0,
    )

    trade = engine.execute(order, account, 400.0)

    assert trade.shares == 10.0
    assert order.filled_quantity == 10.0
    assert order.remaining_quantity == 0.0
    assert order.status == "FILLED"
    assert account.positions["QQQ"].shares == 10.0
    assert engine.health_check()
