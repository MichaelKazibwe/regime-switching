"""
======================================================================
oms.py

Institutional Order Management System

Central orchestration layer between:

    Order
    OrderStatus
    OrderBook
    ExecutionEngine
    PortfolioAccount

Responsibilities:

    - order validation
    - order submission
    - submission integrity
    - order lifecycle management
    - execution routing
    - cancellation
    - rejection
    - audit trail
    - serialization
    - health checks

The OMS does NOT:

    - generate portfolio targets
    - calculate transaction costs
    - execute trades directly
    - modify portfolio accounting directly

Those responsibilities remain with the appropriate components.

Phase:
    III-B.1 — Submission Integrity

Author: Michael Kazibwe
======================================================================
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from executionengine import ExecutionEngine
from order import Order
from orderbook import OrderBook
from orderstatus import OrderStatus
from portfolioaccount import PortfolioAccount
from pretraderiskgate import (
    PreTradeRiskGate,
    RiskDecision,
)

# ============================================================
# OMS
# ============================================================


class OMS:
    """
    Institutional Order Management System.

    Phase III-B.1 introduces deterministic submission
    validation and rejection handling while preserving
    the Phase III-A public API.
    """

    API_VERSION = "1.0.0"

    # ========================================================
    # REJECTION REASONS
    # ========================================================

    INVALID_ORDER = "INVALID_ORDER"

    MISSING_ORDER_ID = "MISSING_ORDER_ID"

    DUPLICATE_ORDER = "DUPLICATE_ORDER"

    INVALID_TICKER = "INVALID_TICKER"

    INVALID_SIDE = "INVALID_SIDE"

    INVALID_QUANTITY = "INVALID_QUANTITY"

    INVALID_ORDER_TYPE = "INVALID_ORDER_TYPE"

    INVALID_LIMIT_PRICE = "INVALID_LIMIT_PRICE"

    INVALID_STOP_PRICE = "INVALID_STOP_PRICE"

    INVALID_STATUS = "INVALID_STATUS"

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(
        self,
        order_book: Optional[OrderBook] = None,
        execution_engine: Optional[ExecutionEngine] = None,
        risk_gate: Optional[PreTradeRiskGate] = None,
):

        self.order_book = (
        order_book
        if order_book is not None
        else OrderBook()
    )

        self.execution_engine = (
        execution_engine
        if execution_engine is not None
        else ExecutionEngine()
    )

        self.risk_gate = (
        risk_gate
        if risk_gate is not None
        else PreTradeRiskGate()
    )

        self.order_history: list[dict] = []

        self.last_order: Optional[Order] = None

        self.last_trade = None

        self.last_risk_decision: Optional[
        RiskDecision
    ] = None

    # ========================================================
    # TIMESTAMP
    # ========================================================

    @staticmethod
    def _timestamp() -> str:

        return datetime.now(
            UTC
        ).isoformat()

    # ========================================================
    # AUDIT EVENT
    # ========================================================

    def _record_event(
        self,
        order: Order,
        previous_status: str,
        new_status: str,
        event: str,
        reason: Optional[str] = None,
    ) -> None:

        self.order_history.append(

            {
                "timestamp":
                    self._timestamp(),

                "order_id":
                    getattr(
                        order,
                        "order_id",
                        None
                    ),

                "ticker":
                    getattr(
                        order,
                        "ticker",
                        None
                    ),

                "previous_status":
                    previous_status,

                "new_status":
                    new_status,

                "event":
                    event,

                "reason":
                    reason,
            }

        )

        self.last_order = order

    # ========================================================
    # REJECTION EVENT
    # ========================================================

    def _record_rejection(
        self,
        order: Order,
        reason: str,
        previous_status: Optional[str] = None,
    ) -> Order:

        previous = (

            previous_status

            if previous_status is not None

            else getattr(
                order,
                "status",
                "UNKNOWN"
            )

        )

        order.status = OrderStatus.REJECTED.name

        self.last_rejection_reason = reason

        self._record_event(

            order,

            previous,

            OrderStatus.REJECTED.name,

            "REJECT",

            reason,

        )

        return order

    # ========================================================
    # VALIDATE ORDER
    # ========================================================

    @staticmethod
    def _validate_order(
        order: Order
    ) -> bool:

        if not isinstance(
            order,
            Order
        ):

            raise TypeError(
                "order must be an Order object."
            )

        if not getattr(
            order,
            "order_id",
            None
        ):

            raise ValueError(
                OMS.MISSING_ORDER_ID
            )

        if not getattr(
            order,
            "ticker",
            None
        ):

            raise ValueError(
                OMS.INVALID_TICKER
            )

        if getattr(
            order,
            "quantity",
            0
        ) <= 0:

            raise ValueError(
                OMS.INVALID_QUANTITY
            )

        if getattr(
            order,
            "side",
            None
        ) not in (

            "BUY",

            "SELL",

        ):

            raise ValueError(
                OMS.INVALID_SIDE
            )

        if getattr(
            order,
            "order_type",
            None
        ) not in (

            "MARKET",

            "LIMIT",

            "STOP",

            "STOP_LIMIT",

        ):

            raise ValueError(
                OMS.INVALID_ORDER_TYPE
            )

        # ----------------------------------------------------
        # LIMIT PRICE
        # ----------------------------------------------------

        if order.order_type in (

            "LIMIT",

            "STOP_LIMIT",

        ):

            if (

                order.limit_price is None

                or order.limit_price <= 0

            ):

                raise ValueError(
                    OMS.INVALID_LIMIT_PRICE
                )

        # ----------------------------------------------------
        # STOP PRICE
        # ----------------------------------------------------

        if order.order_type in (

            "STOP",

            "STOP_LIMIT",

        ):

            if (

                order.stop_price is None

                or order.stop_price <= 0

            ):

                raise ValueError(
                    OMS.INVALID_STOP_PRICE
                )

        order.validate()

        return True

    # ========================================================
    # VALIDATION REASON
    # ========================================================

    @staticmethod
    def _validation_reason(
        order: object
    ) -> str:

        if not isinstance(
            order,
            Order
        ):

            return OMS.INVALID_ORDER

        if not getattr(
            order,
            "order_id",
            None
        ):

            return OMS.MISSING_ORDER_ID

        if not getattr(
            order,
            "ticker",
            None
        ):

            return OMS.INVALID_TICKER

        if getattr(
            order,
            "quantity",
            0
        ) <= 0:

            return OMS.INVALID_QUANTITY

        if getattr(
            order,
            "side",
            None
        ) not in (

            "BUY",

            "SELL",

        ):

            return OMS.INVALID_SIDE

        if getattr(
            order,
            "order_type",
            None
        ) not in (

            "MARKET",

            "LIMIT",

            "STOP",

            "STOP_LIMIT",

        ):

            return OMS.INVALID_ORDER_TYPE

        if order.order_type in (

            "LIMIT",

            "STOP_LIMIT",

        ):

            if (

                order.limit_price is None

                or order.limit_price <= 0

            ):

                return OMS.INVALID_LIMIT_PRICE

        if order.order_type in (

            "STOP",

            "STOP_LIMIT",

        ):

            if (

                order.stop_price is None

                or order.stop_price <= 0

            ):

                return OMS.INVALID_STOP_PRICE

        return OMS.INVALID_ORDER

    # ========================================================
    # SUBMISSION VALIDATION
    # ========================================================

    def validate_submission(
        self,
        order: Order,
    ) -> bool:

        try:

            self._validate_order(
                order
            )

        except TypeError:

            raise

        except ValueError as exc:

            reason = str(exc)

            if reason not in (

                self.MISSING_ORDER_ID,

                self.INVALID_TICKER,

                self.INVALID_QUANTITY,

                self.INVALID_SIDE,

                self.INVALID_ORDER_TYPE,

                self.INVALID_LIMIT_PRICE,

                self.INVALID_STOP_PRICE,

                self.INVALID_ORDER,

            ):

                reason = self._validation_reason(
                    order
                )

            raise ValueError(
                reason
            ) from exc

        return True

    # ========================================================
    # SUBMIT ORDER
    # ========================================================

    def submit_order(
        self,
        order: Order,
    ) -> Order:

        # ----------------------------------------------------
        # TYPE CHECK
        # ----------------------------------------------------

        if not isinstance(
            order,
            Order
        ):

            raise TypeError(
                "order must be an Order object."
            )

        # ----------------------------------------------------
        # DUPLICATE CHECK
        # ----------------------------------------------------

        if getattr(
            order,
            "order_id",
            None
        ) and self.order_book.has_order(
            order.order_id
        ):

            return self._record_rejection(

                order,

                self.DUPLICATE_ORDER,

                getattr(
                    order,
                    "status",
                    "UNKNOWN"
                ),

            )

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        try:

            self.validate_submission(
                order
            )

        except ValueError as exc:

            reason = str(exc)

            return self._record_rejection(

                order,

                reason,

                getattr(
                    order,
                    "status",
                    "UNKNOWN"
                ),

            )

        # ----------------------------------------------------
        # VALIDATED
        # ----------------------------------------------------

        previous_status = order.status

        order.status = (
            OrderStatus.VALIDATED.name
        )

        self._record_event(

            order,

            previous_status,

            order.status,

            "VALIDATE",

        )

        # ----------------------------------------------------
        # ORDER BOOK
        # ----------------------------------------------------

        self.order_book.add_order(
            order
        )

        # ----------------------------------------------------
        # PENDING
        # ----------------------------------------------------

        previous_status = order.status

        order.status = (
            OrderStatus.PENDING.name
        )

        self._record_event(

            order,

            previous_status,

            order.status,

            "SUBMIT",

        )

        self.last_rejection_reason = None

        return order

    # ========================================================
    # PRE-TRADE RISK CHECK
    # ========================================================

    def check_order_risk(
        self,
        order: Order,
        account: PortfolioAccount,
        execution_price: float,
    ) -> RiskDecision:

        self._validate_order(
            order
        )

        decision = self.risk_gate.check(
            order,
            account,
            execution_price,
        )

        self.last_risk_decision = decision

        self.order_history.append(

            {
                "timestamp":
                    self._timestamp(),

                "order_id":
                    order.order_id,

                "ticker":
                    order.ticker,

                "event":
                    "RISK_CHECK",

                "approved":
                    decision.approved,

                "reason":
                    decision.reason,
            }

        )

        return decision

    # ========================================================
    # EXECUTE ORDER
    # ========================================================

    def execute_order(
        self,
        order_id: str,
        account: PortfolioAccount,
        execution_price: float,
    ):

        order = self.order_book.get_order(
            order_id
        )

        if order.status not in (
            OrderStatus.PENDING.name,
            OrderStatus.PARTIALLY_FILLED.name,
        ):

            raise RuntimeError(
                f"Order '{order_id}' is not executable "
                f"from status '{order.status}'."
            )

        decision = self.check_order_risk(
            order,
            account,
            execution_price,
        )

        if not decision.approved:

            raise RuntimeError(
                f"Pre-trade risk check rejected "
                f"order '{order_id}': "
                f"{decision.reason}"
            )

        previous_status = order.status

        trade = self.execution_engine.execute(
            order,
            account,
            execution_price,
        )

        self.last_trade = trade

        # ----------------------------------------------------
        # FILLED
        # ----------------------------------------------------

        if order.status == OrderStatus.FILLED.name:

            self.order_book.complete_order(
                order_id
            )

            self._record_event(
                order,
                previous_status,
                OrderStatus.FILLED.name,
                "FILL",
            )

        # ----------------------------------------------------
        # PARTIAL FILL
        # ----------------------------------------------------

        elif order.status == (
            OrderStatus.PARTIALLY_FILLED.name
        ):

            self._record_event(
                order,
                previous_status,
                OrderStatus.PARTIALLY_FILLED.name,
                "PARTIAL_FILL",
            )

        # ----------------------------------------------------
        # UNEXPECTED EXECUTION STATE
        # ----------------------------------------------------

        else:

            raise RuntimeError(
                f"Execution produced unexpected "
                f"order status '{order.status}'."
            )

        return trade
    # ========================================================
    # CANCEL ORDER
    # ========================================================

    def cancel_order(
        self,
        order_id: str,
        reason: Optional[str] = None,
    ) -> Order:

        order = self.order_book.get_order(
            order_id
        )

        if order.status in (

            OrderStatus.FILLED.name,

            OrderStatus.CANCELLED.name,

            OrderStatus.REJECTED.name,

            OrderStatus.EXPIRED.name,

        ):

            raise RuntimeError(

                f"Order '{order_id}' cannot be cancelled "
                f"from status '{order.status}'."

            )

        previous_status = order.status

        cancelled = self.order_book.cancel_order(
            order_id
        )

        self._record_event(

            cancelled,

            previous_status,

            OrderStatus.CANCELLED.name,

            "CANCEL",

            reason,

        )

        return cancelled

    # ========================================================
    # REJECT EXISTING ORDER
    # ========================================================

    def reject_order(
        self,
        order_id: str,
        reason: Optional[str] = None,
    ) -> Order:

        order = self.order_book.get_order(
            order_id
        )

        if order.status in (

            OrderStatus.FILLED.name,

            OrderStatus.CANCELLED.name,

            OrderStatus.REJECTED.name,

            OrderStatus.EXPIRED.name,

        ):

            raise RuntimeError(

                f"Order '{order_id}' cannot be rejected "
                f"from status '{order.status}'."

            )

        previous_status = order.status

        rejected = self.order_book.reject_order(
            order_id
        )

        self._record_event(

            rejected,

            previous_status,

            OrderStatus.REJECTED.name,

            "REJECT",

            reason,

        )

        self.last_rejection_reason = reason

        return rejected

    # ========================================================
    # GET ORDER
    # ========================================================

    def get_order(
        self,
        order_id: str,
    ) -> Order:

        return self.order_book.get_order(
            order_id
        )

    # ========================================================
    # HAS ORDER
    # ========================================================

    def has_order(
        self,
        order_id: str,
    ) -> bool:

        return self.order_book.has_order(
            order_id
        )

    # ========================================================
    # ACTIVE ORDERS
    # ========================================================

    def active_orders(
        self
    ):

        return self.order_book.active()

    # ========================================================
    # COMPLETED ORDERS
    # ========================================================

    def completed_orders(
        self
    ):

        return self.order_book.completed()

    # ========================================================
    # CANCELLED ORDERS
    # ========================================================

    def cancelled_orders(
        self
    ):

        return self.order_book.cancelled()

    # ========================================================
    # REJECTED ORDERS
    # ========================================================

    def rejected_orders(
        self
    ):

        return self.order_book.rejected()

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ):

        return {

            "api_version":
                self.API_VERSION,

            "active_orders":
                self.order_book.active_count,

            "completed_orders":
                self.order_book.completed_count,

            "cancelled_orders":
                self.order_book.cancelled_count,

            "rejected_orders":
                self.order_book.rejected_count,

            "audit_events":
                len(
                    self.order_history
                ),

            "last_order":
                None
                if self.last_order is None
                else self.last_order.order_id,

            "last_risk_decision":
                None
                if self.last_risk_decision is None
                else self.last_risk_decision.to_dict(),

            "last_rejection_reason":
                self.last_rejection_reason,

        }

    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(
        self
    ):

        return {

            "component":
                "OMS",

            "api_version":
                self.API_VERSION,

            "summary":
                self.summary(),

        }

    # ========================================================
    # PUBLIC METHODS
    # ========================================================

    @property
    def public_methods(
        self
    ):

        return [

            "submit_order",

            "validate_submission",

            "execute_order",

            "cancel_order",

            "reject_order",

            "get_order",

            "has_order",

            "active_orders",

            "completed_orders",

            "cancelled_orders",

            "rejected_orders",

            "summary",

            "health_check",

            "to_dict",

            "from_dict",

        ]

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ):

        self.execution_engine.health_check()

        for order in self.order_book.active():

            order.validate()

            if order.status not in (
                OrderStatus.NEW.name,
                OrderStatus.VALIDATED.name,
                OrderStatus.PENDING.name,
                OrderStatus.PARTIALLY_FILLED.name,
                OrderStatus.SUSPENDED.name,
            ):

                raise RuntimeError(
                    f"Invalid active order state: "
                    f"{order.status}"
                )

        if not hasattr(
            self.risk_gate,
            "check"
        ):

            raise RuntimeError(
                "PreTradeRiskGate is unavailable."
            )

        return True

    # ========================================================
    # TO DICTIONARY
    # ========================================================

    def to_dict(
        self
    ):

        return {

            "api_version":
                self.API_VERSION,

            "order_history":
                list(
                    self.order_history
                ),

            "last_order":
                None
                if self.last_order is None
                else self.last_order.to_dict(),

            "last_rejection_reason":
                self.last_rejection_reason,

            "summary":
                self.summary(),

        }

    # ========================================================
    # FROM DICTIONARY
    # ========================================================

    @classmethod
    def from_dict(
        cls,
        data,
    ):

        oms = cls()

        oms.order_history = list(

            data.get(
                "order_history",
                []
            )

        )

        last_order = data.get(
            "last_order"
        )

        if last_order is not None:

            oms.last_order = (
                Order.from_dict(
                    last_order
                )
            )

        oms.last_rejection_reason = (
            data.get(
                "last_rejection_reason"
            )
        )

        return oms


# ============================================================
# REGRESSION TESTS
# ============================================================

def test_oms():

    # ========================================================
    # ISOLATED TEST FIXTURES
    # ========================================================

    oms = OMS()

    risk_oms = OMS()

    account = PortfolioAccount(
        initial_cash=100000.0
    )

    restricted_account = PortfolioAccount(
        initial_cash=1_000.0
    )

    # ========================================================
    # PRE-TRADE RISK APPROVAL
    # ========================================================

    approved_order = Order(

        order_id="OMS-RISK-000001",

        ticker="SPY",

        side="BUY",

        quantity=10,

    )

    submitted = risk_oms.submit_order(
    approved_order
    )

    decision = risk_oms.check_order_risk(

        approved_order,

        account,

        500.0,

    )

    assert decision.approved

    assert decision.reason is None

    assert decision.order_id == (
        "OMS-RISK-000001"
    )

    assert risk_oms.last_risk_decision is decision

    # ========================================================
    # PRE-TRADE RISK REJECTION
    # ========================================================

    restricted_account = PortfolioAccount(
        initial_cash=1_000.0
    )

    rejected_order = Order(

        order_id="OMS-RISK-000002",

        ticker="SPY",

        side="BUY",

        quantity=10,

    )

    risk_oms.submit_order(
        rejected_order
    )

    decision = risk_oms.check_order_risk(

        rejected_order,

        restricted_account,

        500.0,

    )

    assert not decision.approved

    assert decision.reason == (
        PreTradeRiskGate.INSUFFICIENT_CASH
    )

    try:

        risk_oms.execute_order(

            order_id="OMS-RISK-000002",

            account=restricted_account,

            execution_price=500.0,

        )

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError as exc:

        assert (
            "INSUFFICIENT_CASH"
            in str(exc)
        )

        assert rejected_order.filled_quantity == 0.0

        assert (
        restricted_account.cash
        == 1_000.0
        )

    # ========================================================
    # VALID SUBMISSION
    # ========================================================

    order = Order(

        order_id="OMS-000001",

        ticker="SPY",

        side="BUY",

        quantity=100,

    )

    submitted = oms.submit_order(
        order
    )

    assert submitted is order

    assert order.status == (
        OrderStatus.PENDING.name
    )

    assert oms.has_order(
        "OMS-000001"
    )

    assert oms.summary()[
        "active_orders"
    ] == 1

    assert oms.last_rejection_reason is None

    # ========================================================
    # EXECUTE ORDER
    # ========================================================

    trade = oms.execute_order(

        order_id="OMS-000001",

        account=account,

        execution_price=500.0,

    )

    assert trade is not None

    assert order.status == (
        OrderStatus.FILLED.name
    )

    assert order.filled

    assert oms.summary()[
        "completed_orders"
    ] == 1

    assert oms.summary()[
        "active_orders"
    ] == 0

    assert oms.last_trade is trade

    # ========================================================
    # CANCEL ORDER
    # ========================================================

    cancel_order = Order(

        order_id="OMS-000002",

        ticker="QQQ",

        side="BUY",

        quantity=50,

    )

    oms.submit_order(
        cancel_order
    )

    cancelled = oms.cancel_order(

        "OMS-000002",

        reason="Regression test cancellation",

    )

    assert cancelled is cancel_order

    assert cancel_order.status == (
        OrderStatus.CANCELLED.name
    )

    assert oms.summary()[
        "cancelled_orders"
    ] == 1

    # ========================================================
    # REJECT EXISTING ORDER
    # ========================================================

    reject_order = Order(

        order_id="OMS-000003",

        ticker="TLT",

        side="BUY",

        quantity=20,

    )

    oms.submit_order(
        reject_order
    )

    rejected = oms.reject_order(

        "OMS-000003",

        reason="Regression test rejection",

    )

    assert rejected is reject_order

    assert reject_order.status == (
        OrderStatus.REJECTED.name
    )

    assert oms.summary()[
        "rejected_orders"
    ] == 1

    # ========================================================
    # AUDIT TRAIL
    # ========================================================

    assert len(
        oms.order_history
    ) >= 6

    assert oms.order_history[0][
        "event"
    ] == "VALIDATE"

    assert oms.order_history[1][
        "event"
    ] == "SUBMIT"

    # ========================================================
    # INVALID TICKER
    # ========================================================

    invalid_ticker = Order(

        order_id="OMS-INVALID-001",

        ticker="",

        side="BUY",

        quantity=10,

    )

    rejected_invalid_ticker = oms.submit_order(
        invalid_ticker
    )

    assert rejected_invalid_ticker is invalid_ticker

    assert invalid_ticker.status == (
        OrderStatus.REJECTED.name
    )

    assert oms.last_rejection_reason == (
        OMS.INVALID_TICKER
    )

    assert not oms.order_book.active_orders.get(
        "OMS-INVALID-001"
    )

    assert oms.order_history[-1][
        "event"
    ] == "REJECT"

    assert oms.order_history[-1][
        "reason"
    ] == OMS.INVALID_TICKER

    # ========================================================
    # INVALID SIDE
    # ========================================================

    invalid_side = Order(

        order_id="OMS-INVALID-002",

        ticker="SPY",

        side="LONG",

        quantity=10,

    )

    oms.submit_order(
        invalid_side
    )

    assert invalid_side.status == (
        OrderStatus.REJECTED.name
    )

    assert oms.last_rejection_reason == (
        OMS.INVALID_SIDE
    )

    # ========================================================
    # INVALID QUANTITY
    # ========================================================

    invalid_quantity = Order(

        order_id="OMS-INVALID-003",

        ticker="SPY",

        side="BUY",

        quantity=0,

    )

    oms.submit_order(
        invalid_quantity
    )

    assert invalid_quantity.status == (
        OrderStatus.REJECTED.name
    )

    assert oms.last_rejection_reason == (
        OMS.INVALID_QUANTITY
    )

    # ========================================================
    # INVALID ORDER TYPE
    # ========================================================

    invalid_type = Order(

        order_id="OMS-INVALID-004",

        ticker="SPY",

        side="BUY",

        quantity=10,

        order_type="INVALID",

    )

    oms.submit_order(
        invalid_type
    )

    assert invalid_type.status == (
        OrderStatus.REJECTED.name
    )

    assert oms.last_rejection_reason == (
        OMS.INVALID_ORDER_TYPE
    )

    # ========================================================
    # INVALID LIMIT PRICE
    # ========================================================

    invalid_limit = Order(

        order_id="OMS-INVALID-005",

        ticker="SPY",

        side="BUY",

        quantity=10,

        order_type="LIMIT",

        limit_price=None,

    )

    oms.submit_order(
        invalid_limit
    )

    assert invalid_limit.status == (
        OrderStatus.REJECTED.name
    )

    assert oms.last_rejection_reason == (
        OMS.INVALID_LIMIT_PRICE
    )

    # ========================================================
    # DUPLICATE ORDER
    # ========================================================

    duplicate = Order(

        order_id="OMS-000001",

        ticker="SPY",

        side="BUY",

        quantity=10,

    )

    duplicate_result = oms.submit_order(
        duplicate
    )

    assert duplicate_result is duplicate

    assert duplicate.status == (
        OrderStatus.REJECTED.name
    )

    assert oms.last_rejection_reason == (
        OMS.DUPLICATE_ORDER
    )

    # Existing order remains unchanged.
    assert oms.get_order(
        "OMS-000001"
    ) is order

    assert order.status == (
        OrderStatus.FILLED.name
    )

    # ========================================================
    # REJECTED SUBMISSIONS DO NOT ENTER ORDER BOOK
    # ========================================================

    assert not oms.has_order(
        "OMS-INVALID-001"
    )

    assert not oms.has_order(
        "OMS-INVALID-002"
    )

    assert not oms.has_order(
        "OMS-INVALID-003"
    )

    assert not oms.has_order(
        "OMS-INVALID-004"
    )

    assert not oms.has_order(
        "OMS-INVALID-005"
    )

    # ========================================================
    # AUDIT REJECTION EVENTS
    # ========================================================

    rejection_events = [

        event

        for event in oms.order_history

        if event["event"] == "REJECT"

    ]

    assert len(
        rejection_events
    ) >= 6

    # ========================================================
    # SERIALIZATION
    # ========================================================

    exported = oms.to_dict()

    assert exported[
        "api_version"
    ] == OMS.API_VERSION

    assert exported[
        "last_rejection_reason"
    ] == OMS.DUPLICATE_ORDER

    restored = OMS.from_dict(
        exported
    )

    assert restored.order_history == (
        oms.order_history
    )

    assert restored.last_order is not None

    assert (
        restored.last_order.order_id
        == oms.last_order.order_id
    )

    assert (
        restored.last_rejection_reason
        == oms.last_rejection_reason
    )

    # ========================================================
    # HEALTH
    # ========================================================

    assert oms.health_check()

    # ========================================================
    # INVALID EXECUTION
    # ========================================================

    try:

        oms.execute_order(

            order_id="OMS-000002",

            account=account,

            execution_price=500.0,

        )

        raise AssertionError(
            "Expected RuntimeError"
        )

    except RuntimeError:

        pass

    # ========================================================
    # PUBLIC API
    # ========================================================

    assert (
        "submit_order"
        in oms.public_methods
    )

    assert (
        "validate_submission"
        in oms.public_methods
    )

    assert (
        "execute_order"
        in oms.public_methods
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    metadata = oms.metadata

    assert metadata["component"] == "OMS"

    assert metadata["api_version"] == (
        OMS.API_VERSION
    )

    summary = oms.summary()

    assert summary[
        "api_version"
    ] == OMS.API_VERSION

    assert summary[
        "completed_orders"
    ] == 1

    assert summary[
        "cancelled_orders"
    ] == 1

    assert summary[
        "rejected_orders"
    ] == 1

    print(
        "OMS Phase III-B.1 tests passed."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_oms()