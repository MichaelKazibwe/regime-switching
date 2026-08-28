"""
================================================================
order.py

Institutional Order Object
================================================================

Canonical OMS Order representation.

ARCHITECTURAL BOUNDARY
----------------------

This class represents the canonical Order inside the OMS.

The Order owns the lifecycle state of an order as observed by the
OMS. It does NOT own broker connectivity, broker authentication,
broker routing, or broker execution.

Therefore:

    - Order.submit() records the OMS submission transition.
    - Order.submit() does NOT communicate with a broker.
    - Broker routing belongs to BrokerRouter.
    - Broker execution belongs to BrokerExecutionEngine.
    - Broker-specific execution receipts remain broker-side.
    - OMS lifecycle accounting remains inside Order / OMS.
    - Execution fills may transition the canonical Order to
      PARTIALLY_FILLED or FILLED.

Canonical OMS lifecycle states:

    NEW
    VALIDATED
    PENDING
    SUBMITTED
    PARTIALLY_FILLED
    FILLED
    CANCELLED
    REJECTED
    EXPIRED
    SUSPENDED

IMPORTANT
---------

SUBMITTED is an OMS lifecycle state indicating that the order has
crossed the OMS submission boundary.

It does NOT mean that this object itself has contacted a broker.

The actual broker-side state remains the responsibility of the
broker integration layer.

This distinction preserves the separation between:

    OMS lifecycle
        ↓
    authorized routing
        ↓
    broker submission
        ↓
    broker execution
        ↓
    execution receipt
        ↓
    OMS fill accounting

================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


# ==============================================================
# CANONICAL OMS STATUS VALUES
# ==============================================================

CANONICAL_ORDER_STATUSES = frozenset(
    {
        "NEW",
        "VALIDATED",
        "PENDING",
        "SUBMITTED",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCELLED",
        "REJECTED",
        "EXPIRED",
        "SUSPENDED",
    }
)


TERMINAL_ORDER_STATUSES = frozenset(
    {
        "FILLED",
        "CANCELLED",
        "REJECTED",
        "EXPIRED",
    }
)


ACTIVE_ORDER_STATUSES = frozenset(
    {
        "NEW",
        "VALIDATED",
        "PENDING",
        "SUBMITTED",
        "PARTIALLY_FILLED",
        "SUSPENDED",
    }
)


# ==============================================================
# ORDER
# ==============================================================


@dataclass
class Order:
    """
    Canonical institutional OMS Order.

    The Order owns canonical OMS lifecycle state.

    It does not own broker connectivity or broker execution.

    ``SUBMITTED`` means that the OMS has accepted the order for
    submission/routing. It does not itself imply that an external
    broker has accepted or executed the order.
    """

    ticker: str

    side: str

    quantity: float

    order_id: str = field(
        default_factory=lambda:
            f"ORD-{uuid4().hex[:12].upper()}"
    )

    order_type: str = "MARKET"

    limit_price: float | None = None

    stop_price: float | None = None

    time_in_force: str = "DAY"

    status: str = "PENDING"

    filled_quantity: float = 0.0

    average_fill_price: float = 0.0

    broker: str | None = None

    exchange: str | None = None

    currency: str = "USD"

    timestamp: str | None = None

    # ==========================================================
    # REMAINING QUANTITY
    # ==========================================================

    @property
    def remaining_quantity(
        self,
    ) -> float:
        """
        Return the unfilled quantity.

        The value is never allowed to become negative.
        """

        return max(
            0.0,
            self.quantity - self.filled_quantity,
        )

    # ==========================================================
    # FILLED
    # ==========================================================

    @property
    def filled(
        self,
    ) -> bool:
        """
        Return True when the entire order quantity is filled.
        """

        return self.remaining_quantity == 0.0

    # ==========================================================
    # TERMINAL
    # ==========================================================

    @property
    def terminal(
        self,
    ) -> bool:
        """
        Return True when the order is in a terminal state.
        """

        return self.status in TERMINAL_ORDER_STATUSES

    # ==========================================================
    # ACTIVE
    # ==========================================================

    @property
    def active(
        self,
    ) -> bool:
        """
        Return True while the order remains active.
        """

        return self.status in ACTIVE_ORDER_STATUSES

    # ==========================================================
    # VALIDATE
    # ==========================================================

    def validate(
        self,
    ) -> bool:
        """
        Validate the structural and lifecycle integrity of the
        canonical OMS Order.

        Validation is deliberately deterministic and side-effect
        free.
        """

        # ------------------------------------------------------
        # ORDER ID
        # ------------------------------------------------------

        if not isinstance(
            self.order_id,
            str,
        ) or not self.order_id.strip():

            raise ValueError(
                "Order ID cannot be empty."
            )

        # ------------------------------------------------------
        # TICKER
        # ------------------------------------------------------

        if not isinstance(
            self.ticker,
            str,
        ) or not self.ticker.strip():

            raise ValueError(
                "Ticker cannot be empty."
            )

        # ------------------------------------------------------
        # SIDE
        # ------------------------------------------------------

        if self.side not in (
            "BUY",
            "SELL",
        ):

            raise ValueError(
                "Side must be BUY or SELL."
            )

        # ------------------------------------------------------
        # QUANTITY
        # ------------------------------------------------------

        if self.quantity <= 0:

            raise ValueError(
                "Quantity must be positive."
            )

        # ------------------------------------------------------
        # FILLED QUANTITY
        # ------------------------------------------------------

        if self.filled_quantity < 0:

            raise ValueError(
                "Filled quantity cannot be negative."
            )

        if self.filled_quantity > self.quantity:

            raise ValueError(
                "Filled quantity cannot exceed order quantity."
            )

        # ------------------------------------------------------
        # ORDER TYPE
        # ------------------------------------------------------

        if self.order_type not in (
            "MARKET",
            "LIMIT",
            "STOP",
            "STOP_LIMIT",
        ):

            raise ValueError(
                "Unsupported order type."
            )

        # ------------------------------------------------------
        # LIMIT PRICE
        # ------------------------------------------------------

        if self.order_type in (
            "LIMIT",
            "STOP_LIMIT",
        ):

            if (
                self.limit_price is None
                or self.limit_price <= 0
            ):

                raise ValueError(
                    (
                        "Limit price must be positive for "
                        f"{self.order_type} orders."
                    )
                )

        # ------------------------------------------------------
        # STOP PRICE
        # ------------------------------------------------------

        if self.order_type in (
            "STOP",
            "STOP_LIMIT",
        ):

            if (
                self.stop_price is None
                or self.stop_price <= 0
            ):

                raise ValueError(
                    (
                        "Stop price must be positive for "
                        f"{self.order_type} orders."
                    )
                )

        # ------------------------------------------------------
        # MARKET ORDER PRICE GUARD
        # ------------------------------------------------------

        if self.order_type == "MARKET":

            if self.limit_price is not None:
                raise ValueError(
                    "MARKET orders cannot define a limit price."
                )

            if self.stop_price is not None:
                raise ValueError(
                    "MARKET orders cannot define a stop price."
                )

        # ------------------------------------------------------
        # STOP ORDER PRICE GUARD
        # ------------------------------------------------------

        if self.order_type == "STOP":

            if self.limit_price is not None:
                raise ValueError(
                    "STOP orders cannot define a limit price."
                )

        # ------------------------------------------------------
        # LIMIT ORDER PRICE GUARD
        # ------------------------------------------------------

        if self.order_type == "LIMIT":

            if self.stop_price is not None:
                raise ValueError(
                    "LIMIT orders cannot define a stop price."
                )

        # ------------------------------------------------------
        # TIME IN FORCE
        # ------------------------------------------------------

        if self.time_in_force not in (
            "DAY",
            "GTC",
            "IOC",
            "FOK",
        ):

            raise ValueError(
                "Unsupported time-in-force."
            )

        # ------------------------------------------------------
        # AVERAGE FILL PRICE
        # ------------------------------------------------------

        if self.average_fill_price < 0:

            raise ValueError(
                "Average fill price cannot be negative."
            )

        # ------------------------------------------------------
        # FILL PRICE CONSISTENCY
        # ------------------------------------------------------

        if (
            self.filled_quantity == 0
            and self.average_fill_price != 0
        ):

            raise ValueError(
                (
                    "Average fill price must be zero when "
                    "filled quantity is zero."
                )
            )

        if (
            self.filled_quantity > 0
            and self.average_fill_price <= 0
        ):

            raise ValueError(
                (
                    "Average fill price must be positive when "
                    "filled quantity is greater than zero."
                )
            )

        # ------------------------------------------------------
        # CANONICAL STATUS
        # ------------------------------------------------------

        if self.status not in CANONICAL_ORDER_STATUSES:

            raise ValueError(
                (
                    "Unsupported canonical OMS order status: "
                    f"{self.status}."
                )
            )

        # ------------------------------------------------------
        # FILLED STATE CONSISTENCY
        # ------------------------------------------------------

        if self.status == "FILLED":

            if self.filled_quantity != self.quantity:

                raise ValueError(
                    (
                        "FILLED order must have filled_quantity "
                        "equal to quantity."
                    )
                )

            if self.average_fill_price <= 0:

                raise ValueError(
                    (
                        "FILLED order must have a positive "
                        "average_fill_price."
                    )
                )

        # ------------------------------------------------------
        # PARTIAL FILL STATE CONSISTENCY
        # ------------------------------------------------------

        if self.status == "PARTIALLY_FILLED":

            if not (
                0.0
                < self.filled_quantity
                < self.quantity
            ):

                raise ValueError(
                    (
                        "PARTIALLY_FILLED order must have a "
                        "filled quantity greater than zero and "
                        "less than total quantity."
                    )
                )

        # ------------------------------------------------------
        # UNFILLED LIFECYCLE STATE CONSISTENCY
        # ------------------------------------------------------

        if self.status in (
            "NEW",
            "VALIDATED",
            "PENDING",
            "SUBMITTED",
            "CANCELLED",
            "REJECTED",
            "EXPIRED",
            "SUSPENDED",
        ):

            if self.filled_quantity > 0:

                raise ValueError(
                    (
                        f"{self.status} order cannot contain "
                        "filled quantity."
                    )
                )

        return True

    # ==========================================================
    # SUMMARY
    # ==========================================================

    def summary(
        self,
    ) -> dict:
        """
        Return a concise order representation.
        """

        return {
            "order_id": self.order_id,
            "ticker": self.ticker,
            "side": self.side,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "order_type": self.order_type,
            "status": self.status,
            "trade_value":
                self.average_fill_price
                * self.filled_quantity,
        }

    # ==========================================================
    # TO DICTIONARY
    # ==========================================================

    def to_dict(
        self,
    ) -> dict:
        """
        Serialize the Order into a plain dictionary.
        """

        return {
            key: value
            for key, value
            in self.__dict__.items()
        }

    # ==========================================================
    # FROM DICTIONARY
    # ==========================================================

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> Order:
        """
        Reconstruct and validate an Order from a dictionary.
        """

        if not isinstance(
            data,
            dict,
        ):

            raise TypeError(
                "Order data must be a dictionary."
            )

        order = cls(
            **data
        )

        order.validate()

        return order

    # ==========================================================
    # HEALTH CHECK
    # ==========================================================

    def health_check(
        self,
    ) -> bool:
        """
        Run the complete order validation contract.
        """

        return self.validate()

    # ==========================================================
    # STATE PREDICATES
    # ==========================================================

    def is_new(
        self,
    ) -> bool:
        return self.status == "NEW"

    def is_validated(
        self,
    ) -> bool:
        return self.status == "VALIDATED"

    def is_pending(
        self,
    ) -> bool:
        return self.status == "PENDING"

    def is_submitted(
        self,
    ) -> bool:
        """
        Return True when the OMS has transitioned the order to
        SUBMITTED.

        This is a lifecycle predicate only.

        It does not indicate that a broker has accepted the order.
        """

        return self.status == "SUBMITTED"

    def is_partially_filled(
        self,
    ) -> bool:
        return self.status == "PARTIALLY_FILLED"

    def is_filled(
        self,
    ) -> bool:
        return self.status == "FILLED"

    def is_cancelled(
        self,
    ) -> bool:
        return self.status == "CANCELLED"

    def is_rejected(
        self,
    ) -> bool:
        return self.status == "REJECTED"

    def is_expired(
        self,
    ) -> bool:
        return self.status == "EXPIRED"

    def is_suspended(
        self,
    ) -> bool:
        return self.status == "SUSPENDED"

    def is_open(
        self,
    ) -> bool:
        """
        Return True when the order remains active.

        SUBMITTED is intentionally included because a submitted
        order may still be awaiting execution.
        """

        return self.status in ACTIVE_ORDER_STATUSES

    # ==========================================================
    # SUBMIT
    # ==========================================================

    def submit(
        self,
    ) -> None:
        """
        Transition a PENDING OMS Order to SUBMITTED.

        IMPORTANT:

        This method does not route the order to a broker.

        It records only the canonical OMS lifecycle transition.

        Actual broker submission remains the responsibility of the
        authorized execution/routing boundary.

        Valid transition:

            PENDING -> SUBMITTED

        Invalid transitions fail closed.
        """

        if not self.is_pending():

            raise RuntimeError(
                (
                    "Only pending orders can be submitted. "
                    f"Current status is {self.status}."
                )
            )

        self.status = "SUBMITTED"

    # ==========================================================
    # FILL
    # ==========================================================

    def fill(
        self,
        quantity: float,
        price: float,
    ) -> None:
        """
        Apply an execution fill to the canonical Order.

        Valid execution lifecycle:

            SUBMITTED
                ↓
            PARTIALLY_FILLED
                ↓
            FILLED

        A direct fill on a PENDING order is also permitted for
        backwards compatibility with existing paper-execution
        paths and legacy callers.

        This method does not communicate with a broker.
        """

        # ------------------------------------------------------
        # QUANTITY
        # ------------------------------------------------------

        if quantity <= 0:

            raise ValueError(
                "Fill quantity must be positive."
            )

        # ------------------------------------------------------
        # PRICE
        # ------------------------------------------------------

        if price <= 0:

            raise ValueError(
                "Fill price must be positive."
            )

        # ------------------------------------------------------
        # TERMINAL STATES
        # ------------------------------------------------------

        if self.is_cancelled():

            raise RuntimeError(
                "Cancelled order cannot be filled."
            )

        if self.is_rejected():

            raise RuntimeError(
                "Rejected order cannot be filled."
            )

        if self.is_expired():

            raise RuntimeError(
                "Expired order cannot be filled."
            )

        if self.is_filled():

            raise RuntimeError(
                "Filled order cannot receive another fill."
            )

        # ------------------------------------------------------
        # FILL BOUNDARY
        # ------------------------------------------------------

        if quantity > self.remaining_quantity:

            raise ValueError(
                "Fill exceeds remaining quantity."
            )

        # ------------------------------------------------------
        # WEIGHTED AVERAGE EXECUTION PRICE
        # ------------------------------------------------------

        previous_quantity = self.filled_quantity

        previous_value = (
            previous_quantity
            * self.average_fill_price
        )

        new_quantity = (
            previous_quantity
            + quantity
        )

        new_value = (
            previous_value
            + quantity * price
        )

        self.filled_quantity = new_quantity

        self.average_fill_price = (
            new_value / new_quantity
        )

        # ------------------------------------------------------
        # LIFECYCLE TRANSITION
        # ------------------------------------------------------

        if self.remaining_quantity == 0.0:

            self.status = "FILLED"

        else:

            self.status = "PARTIALLY_FILLED"

    # ==========================================================
    # CANCEL
    # ==========================================================

    def cancel(
        self,
    ) -> None:
        """
        Transition an active non-terminal order to CANCELLED.

        Valid examples:

            PENDING -> CANCELLED
            SUBMITTED -> CANCELLED
            PARTIALLY_FILLED -> CANCELLED

        Cancellation does not communicate with a broker.
        """

        if self.is_filled():

            raise RuntimeError(
                "Filled order cannot be cancelled."
            )

        if self.is_cancelled():

            raise RuntimeError(
                "Order is already cancelled."
            )

        if self.is_rejected():

            raise RuntimeError(
                "Rejected order cannot be cancelled."
            )

        if self.is_expired():

            raise RuntimeError(
                "Expired order cannot be cancelled."
            )

        self.status = "CANCELLED"

    # ==========================================================
    # REJECT
    # ==========================================================

    def reject(
        self,
    ) -> None:
        """
        Transition an active order to REJECTED.
        """

        if self.is_filled():

            raise RuntimeError(
                "Filled order cannot be rejected."
            )

        if self.is_cancelled():

            raise RuntimeError(
                "Cancelled order cannot be rejected."
            )

        if self.is_rejected():

            raise RuntimeError(
                "Order is already rejected."
            )

        if self.is_expired():

            raise RuntimeError(
                "Expired order cannot be rejected."
            )

        self.status = "REJECTED"

    # ==========================================================
    # EXPIRE
    # ==========================================================

    def expire(
        self,
    ) -> None:
        """
        Transition an active order to EXPIRED.
        """

        if self.is_filled():

            raise RuntimeError(
                "Filled order cannot be expired."
            )

        if self.is_cancelled():

            raise RuntimeError(
                "Cancelled order cannot be expired."
            )

        if self.is_rejected():

            raise RuntimeError(
                "Rejected order cannot be expired."
            )

        if self.is_expired():

            raise RuntimeError(
                "Order is already expired."
            )

        self.status = "EXPIRED"

    # ==========================================================
    # SUSPEND
    # ==========================================================

    def suspend(
        self,
    ) -> None:
        """
        Suspend an active non-terminal order.
        """

        if self.terminal:

            raise RuntimeError(
                "Terminal order cannot be suspended."
            )

        self.status = "SUSPENDED"


# ==============================================================
# REGRESSION TESTS
# ==============================================================


def test_order() -> None:
    """
    Local regression tests for the canonical Order contract.
    """

    # ==========================================================
    # CREATE
    # ==========================================================

    order = Order(
        order_id="ORD-000001",
        ticker="SPY",
        side="BUY",
        quantity=100,
        order_type="MARKET",
    )

    assert order.validate()
    assert order.health_check()

    # ==========================================================
    # INITIAL STATE
    # ==========================================================

    assert order.is_pending()
    assert order.is_open()
    assert order.active
    assert not order.terminal
    assert not order.is_filled()
    assert not order.is_submitted()

    assert order.remaining_quantity == 100
    assert order.filled_quantity == 0

    # ==========================================================
    # SUBMIT
    # ==========================================================

    order.submit()

    assert order.status == "SUBMITTED"
    assert order.is_submitted()
    assert order.is_open()
    assert order.active
    assert not order.terminal

    # ==========================================================
    # RESUBMISSION MUST FAIL
    # ==========================================================

    try:

        order.submit()

        raise AssertionError(
            "Submitted order was submitted twice."
        )

    except RuntimeError as exc:

        assert "pending" in str(exc).lower()

    # ==========================================================
    # PARTIAL FILL
    # ==========================================================

    order.fill(
        quantity=40,
        price=500.0,
    )

    assert order.is_partially_filled()
    assert order.is_open()
    assert order.active
    assert not order.terminal
    assert not order.is_submitted()

    assert order.remaining_quantity == 60
    assert order.filled_quantity == 40
    assert order.average_fill_price == 500.0

    # ==========================================================
    # COMPLETE FILL
    # ==========================================================

    order.fill(
        quantity=60,
        price=505.0,
    )

    assert order.is_filled()
    assert not order.is_open()
    assert not order.active
    assert order.terminal
    assert not order.is_submitted()

    assert order.remaining_quantity == 0
    assert order.filled_quantity == 100
    assert order.average_fill_price == 503.0

    # ==========================================================
    # SUMMARY
    # ==========================================================

    summary = order.summary()

    assert summary["order_id"] == "ORD-000001"
    assert summary["ticker"] == "SPY"
    assert summary["side"] == "BUY"
    assert summary["quantity"] == 100
    assert summary["filled_quantity"] == 100
    assert summary["remaining_quantity"] == 0
    assert summary["status"] == "FILLED"
    assert summary["trade_value"] == 50300.0

    # ==========================================================
    # SERIALIZATION
    # ==========================================================

    exported = order.to_dict()

    assert exported["order_id"] == "ORD-000001"

    restored = Order.from_dict(
        exported
    )

    assert restored.order_id == order.order_id
    assert restored.ticker == order.ticker
    assert restored.side == order.side
    assert restored.quantity == order.quantity
    assert restored.status == order.status
    assert restored.filled_quantity == order.filled_quantity
    assert restored.average_fill_price == (
        order.average_fill_price
    )
    assert restored.validate()

    # ==========================================================
    # CANCEL FROM PENDING
    # ==========================================================

    pending = Order(
        order_id="ORD-000002",
        ticker="QQQ",
        side="SELL",
        quantity=50,
    )

    assert pending.is_pending()

    pending.cancel()

    assert pending.is_cancelled()
    assert not pending.is_open()
    assert pending.terminal
    assert not pending.is_submitted()

    # ==========================================================
    # CANCEL FROM SUBMITTED
    # ==========================================================

    cancellable = Order(
        order_id="ORD-000003",
        ticker="GLD",
        side="BUY",
        quantity=25,
    )

    cancellable.submit()

    assert cancellable.is_submitted()

    cancellable.cancel()

    assert cancellable.is_cancelled()
    assert not cancellable.is_open()
    assert not cancellable.is_submitted()

    # ==========================================================
    # SUBMISSION AFTER CANCELLATION
    # ==========================================================

    try:

        cancellable.submit()

        raise AssertionError(
            "Cancelled order was resubmitted."
        )

    except RuntimeError as exc:

        assert "pending" in str(exc).lower()

    # ==========================================================
    # REJECT
    # ==========================================================

    rejected = Order(
        order_id="ORD-000004",
        ticker="TLT",
        side="BUY",
        quantity=20,
    )

    rejected.reject()

    assert rejected.is_rejected()
    assert not rejected.is_open()
    assert rejected.terminal
    assert not rejected.is_submitted()

    # ==========================================================
    # REJECTED ORDER CANNOT SUBMIT
    # ==========================================================

    try:

        rejected.submit()

        raise AssertionError(
            "Rejected order was resubmitted."
        )

    except RuntimeError as exc:

        assert "pending" in str(exc).lower()

    # ==========================================================
    # EXPIRE
    # ==========================================================

    expired = Order(
        order_id="ORD-000005",
        ticker="IWM",
        side="SELL",
        quantity=10,
    )

    expired.expire()

    assert expired.is_expired()
    assert not expired.is_open()
    assert expired.terminal

    # ==========================================================
    # SUSPEND
    # ==========================================================

    suspended = Order(
        order_id="ORD-000006",
        ticker="DIA",
        side="BUY",
        quantity=15,
    )

    suspended.suspend()

    assert suspended.is_suspended()
    assert suspended.is_open()
    assert suspended.active

    # ==========================================================
    # INVALID CANCEL — FILLED
    # ==========================================================

    try:

        order.cancel()

        raise AssertionError(
            "Expected RuntimeError."
        )

    except RuntimeError as exc:

        assert "filled" in str(exc).lower()

    # ==========================================================
    # INVALID FILL — CANCELLED
    # ==========================================================

    try:

        pending.fill(
            quantity=10,
            price=100.0,
        )

        raise AssertionError(
            "Expected RuntimeError."
        )

    except RuntimeError as exc:

        assert "cancelled" in str(exc).lower()

    # ==========================================================
    # INVALID FILL — REJECTED
    # ==========================================================

    try:

        rejected.fill(
            quantity=10,
            price=100.0,
        )

        raise AssertionError(
            "Expected RuntimeError."
        )

    except RuntimeError as exc:

        assert "rejected" in str(exc).lower()

    # ==========================================================
    # INVALID SIDE
    # ==========================================================

    try:

        Order(
            order_id="ORD-000007",
            ticker="SPY",
            side="LONG",
            quantity=100,
        ).validate()

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:

        pass

    # ==========================================================
    # INVALID ORDER ID
    # ==========================================================

    try:

        Order(
            order_id="",
            ticker="SPY",
            side="BUY",
            quantity=100,
        ).validate()

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:

        pass

    # ==========================================================
    # INVALID QUANTITY
    # ==========================================================

    try:

        Order(
            order_id="ORD-000008",
            ticker="SPY",
            side="BUY",
            quantity=0,
        ).validate()

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:

        pass

    # ==========================================================
    # INVALID FILLED QUANTITY
    # ==========================================================

    try:

        Order(
            order_id="ORD-000009",
            ticker="SPY",
            side="BUY",
            quantity=100,
            filled_quantity=150,
        ).validate()

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:

        pass

    # ==========================================================
    # INVALID ORDER TYPE
    # ==========================================================

    try:

        Order(
            order_id="ORD-000010",
            ticker="SPY",
            side="BUY",
            quantity=100,
            order_type="INVALID",
        ).validate()

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:

        pass

    # ==========================================================
    # INVALID TIME IN FORCE
    # ==========================================================

    try:

        Order(
            order_id="ORD-000011",
            ticker="SPY",
            side="BUY",
            quantity=100,
            time_in_force="INVALID",
        ).validate()

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:

        pass

    # ==========================================================
    # INVALID STATUS
    # ==========================================================

    try:

        Order(
            order_id="ORD-000012",
            ticker="SPY",
            side="BUY",
            quantity=100,
            status="UNKNOWN",
        ).validate()

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:

        pass

    # ==========================================================
    # INVALID FILL PRICE
    # ==========================================================

    try:

        fresh_order = Order(
            order_id="ORD-000013",
            ticker="SPY",
            side="BUY",
            quantity=100,
        )

        fresh_order.fill(
            quantity=10,
            price=0,
        )

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:

        pass

    # ==========================================================
    # OVERFILL
    # ==========================================================

    try:

        overfill_order = Order(
            order_id="ORD-000014",
            ticker="SPY",
            side="BUY",
            quantity=100,
        )

        overfill_order.submit()

        overfill_order.fill(
            quantity=101,
            price=500.0,
        )

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError as exc:

        assert (
            "Fill exceeds remaining quantity"
            in str(exc)
        )

    # ==========================================================
    # DOUBLE FILL AFTER COMPLETE FILL
    # ==========================================================

    try:

        order.fill(
            quantity=1,
            price=510.0,
        )

        raise AssertionError(
            "Expected RuntimeError."
        )

    except RuntimeError as exc:

        assert (
            "Filled order cannot receive another fill"
            in str(exc)
        )

    # ==========================================================
    # FINAL VALIDATION
    # ==========================================================

    assert order.validate()
    assert restored.validate()

    print(
        "Order tests passed."
    )


# ==============================================================
# MAIN
# ==============================================================


if __name__ == "__main__":
    test_order()