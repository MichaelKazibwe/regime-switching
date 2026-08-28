"""
======================================================================
PHASE IV-I-J.7 — LEGACY EXECUTION PRIMITIVE CONTAINMENT

Institutional execution-boundary regression tests.

Purpose
-------
Prove that legacy execution entry points cannot bypass the
authorization-aware execution pipeline.

Required execution chain:

    ExecutionAuthorization
        ↓
    AuthorizedOrderIntent
        ↓
    AuthorizedExecutionHandoff
        ↓
    AuthorizedRoutingHandoff
        ↓
    BrokerRouter
        ↓
    BrokerExecutionEngine
        ↓
    ExecutionEngine
        ↓
    PortfolioAccount

Legacy entry points must fail closed.

This module does not create authorization and does not enable
live trading.

Author: Michael Kazibwe
======================================================================
"""

from __future__ import annotations

import pytest

from oms import OMS, OMSAuthorizationError
from order import Order
from orderstatus import OrderStatus
from portfolioaccount import PortfolioAccount


# ======================================================================
# LEGACY OMS EXECUTION CONTAINMENT
# ======================================================================


def test_legacy_oms_execute_order_is_fail_closed() -> None:
    oms = OMS()

    order = Order(
        order_id="J7-OMS-000001",
        ticker="SPY",
        side="BUY",
        quantity=10,
    )

    submitted = oms.submit_order(order)

    assert submitted is order
    assert order.status == OrderStatus.PENDING.name

    account = PortfolioAccount(
        initial_cash=100_000.0
    )

    with pytest.raises(OMSAuthorizationError):
        oms.execute_order(
            order_id=order.order_id,
            account=account,
            execution_price=500.0,
        )

    assert order.status == OrderStatus.PENDING.name
    assert account.cash == 100_000.0
    assert order.filled_quantity == 0.0


# ======================================================================
# LEGACY OMS PATH MUST NOT ACCOUNT
# ======================================================================


def test_legacy_oms_execution_does_not_mutate_account() -> None:
    oms = OMS()

    order = Order(
        order_id="J7-OMS-000002",
        ticker="QQQ",
        side="BUY",
        quantity=10,
    )

    oms.submit_order(order)

    account = PortfolioAccount(
        initial_cash=100_000.0
    )

    initial_cash = account.cash
    initial_positions = dict(account.positions)

    with pytest.raises(OMSAuthorizationError):
        oms.execute_order(
            order_id=order.order_id,
            account=account,
            execution_price=400.0,
        )

    assert account.cash == initial_cash
    assert account.positions == initial_positions
    assert order.filled_quantity == 0.0


# ======================================================================
# LEGACY OMS PATH MUST NOT ENABLE EXECUTION
# ======================================================================


def test_legacy_oms_execution_does_not_enable_live_trading() -> None:
    oms = OMS()

    assert getattr(
        oms,
        "live_trading_enabled",
        False,
    ) is False


def test_legacy_oms_execution_does_not_create_authorization() -> None:
    oms = OMS()

    order = Order(
        order_id="J7-OMS-000003",
        ticker="SPY",
        side="BUY",
        quantity=5,
    )

    oms.submit_order(order)

    account = PortfolioAccount(
        initial_cash=100_000.0
    )

    with pytest.raises(OMSAuthorizationError):
        oms.execute_order(
            order_id=order.order_id,
            account=account,
            execution_price=500.0,
        )

    assert not hasattr(
        oms,
        "execution_authorization",
    )


# ======================================================================
# RAW ORDER CANNOT CROSS AUTHORIZED EXECUTION BOUNDARY
# ======================================================================


def test_raw_order_cannot_be_used_as_authorized_execution_handoff() -> None:
    oms = OMS()

    order = Order(
        order_id="J7-RAW-000001",
        ticker="SPY",
        side="BUY",
        quantity=10,
    )

    account = PortfolioAccount(
        initial_cash=100_000.0
    )

    with pytest.raises(OMSAuthorizationError):
        oms.execute_authorized_order(
            order,
            None,
            account,
        )


# ======================================================================
# AUTHORIZED EXECUTION API MUST EXIST
# ======================================================================


def test_authorized_execution_is_explicit_public_boundary() -> None:
    oms = OMS()

    assert (
        "execute_authorized_order"
        in oms.public_methods
    )


# ======================================================================
# LEGACY EXECUTION API REMAINS COMPATIBLE BUT DISABLED
# ======================================================================


def test_legacy_execute_order_remains_api_compatible() -> None:
    oms = OMS()

    assert hasattr(
        oms,
        "execute_order",
    )

    assert callable(
        oms.execute_order,
    )


# ======================================================================
# ORDER STATE REMAINS UNCHANGED AFTER LEGACY REJECTION
# ======================================================================


def test_legacy_execution_rejection_preserves_pending_state() -> None:
    oms = OMS()

    order = Order(
        order_id="J7-STATE-000001",
        ticker="TLT",
        side="BUY",
        quantity=20,
    )

    oms.submit_order(order)

    account = PortfolioAccount(
        initial_cash=100_000.0
    )

    with pytest.raises(OMSAuthorizationError):
        oms.execute_order(
            order_id=order.order_id,
            account=account,
            execution_price=100.0,
        )

    assert order.status == OrderStatus.PENDING.name
    assert order.filled_quantity == 0.0


# ======================================================================
# NO DIRECT EXECUTION AUTHORIZATION THROUGH LEGACY API
# ======================================================================


def test_legacy_execution_cannot_become_authorized() -> None:
    oms = OMS()

    order = Order(
        order_id="J7-AUTH-000001",
        ticker="SPY",
        side="BUY",
        quantity=10,
    )

    oms.submit_order(order)

    account = PortfolioAccount(
        initial_cash=100_000.0
    )

    with pytest.raises(OMSAuthorizationError) as exc_info:
        oms.execute_order(
            order_id=order.order_id,
            account=account,
            execution_price=500.0,
        )

    assert (
        "authorized execution boundary"
        in str(exc_info.value).lower()
    )


# ======================================================================
# HEALTH
# ======================================================================


def test_oms_health_remains_valid_after_legacy_execution_rejection() -> None:
    oms = OMS()

    order = Order(
        order_id="J7-HEALTH-000001",
        ticker="SPY",
        side="BUY",
        quantity=1,
    )

    oms.submit_order(order)

    account = PortfolioAccount(
        initial_cash=100_000.0
    )

    with pytest.raises(OMSAuthorizationError):
        oms.execute_order(
            order_id=order.order_id,
            account=account,
            execution_price=500.0,
        )

    assert oms.health_check()


# ======================================================================
# CONTRACT
# ======================================================================


def test_j7_legacy_execution_containment_contract() -> None:
    oms = OMS()

    assert "execute_order" in oms.public_methods
    assert "execute_authorized_order" in oms.public_methods

    assert callable(oms.execute_order)
    assert callable(oms.execute_authorized_order)