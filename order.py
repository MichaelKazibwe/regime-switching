"""
================================================================
ORDER

Institutional Order Object

Represents an order submitted for execution.

================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field

from uuid import uuid4

# ==============================================================
# ORDER
# ==============================================================

@dataclass
class Order:

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
        self
    ) -> float:

        return max(

            0.0,

            self.quantity

            -

            self.filled_quantity

        )

    # ==========================================================
    # FILLED
    # ==========================================================

    @property
    def filled(
        self
    ) -> bool:

        return self.remaining_quantity == 0.0

    # ==========================================================
    # VALIDATE
    # ==========================================================

    def validate(
        self
    ) -> bool:

        if not self.order_id:

            raise ValueError(
                "Order ID cannot be empty."
            )

        if not self.ticker:

            raise ValueError(
                "Ticker cannot be empty."
            )

        if self.quantity <= 0:

            raise ValueError(
                "Quantity must be positive."
            )

        if self.filled_quantity < 0:

            raise ValueError(
                "Filled quantity cannot be negative."
            )

        if self.filled_quantity > self.quantity:

            raise ValueError(
                "Filled quantity cannot exceed order quantity."
            )

        if self.side not in (

            "BUY",

            "SELL"

        ):

            raise ValueError(
                "Side must be BUY or SELL."
            )

        if self.order_type not in (

            "MARKET",

            "LIMIT",

            "STOP",

            "STOP_LIMIT"

        ):

            raise ValueError(
                "Unsupported order type."
            )

        if self.time_in_force not in (

            "DAY",

            "GTC",

            "IOC",

            "FOK"

        ):

            raise ValueError(
                "Unsupported time-in-force."
            )

        if self.average_fill_price < 0:

            raise ValueError(
                "Average fill price cannot be negative."
            )

        return True

    # ==========================================================
    # SUMMARY
    # ==========================================================

    def summary(
        self
    ) -> dict:

        return {

            "order_id":

                self.order_id,

            "ticker":

                self.ticker,

            "side":

                self.side,

            "quantity":

                self.quantity,

            "filled_quantity":

                self.filled_quantity,

            "remaining_quantity":

                self.remaining_quantity,

            "order_type":

                self.order_type,

            "status":

                self.status,

            "trade_value":

                self.average_fill_price

                *

                self.filled_quantity

        }

    # ==========================================================
    # TO DICTIONARY
    # ==========================================================

    def to_dict(
        self
    ) -> dict:

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
        data: dict
    ) -> Order:

        if not isinstance(
            data,
            dict
        ):

            raise TypeError(
                "Order data must be a dictionary."
            )

        return cls(

            **data

        )

    # ==========================================================
    # HEALTH CHECK
    # ==========================================================

    def health_check(
        self
    ) -> bool:

        return self.validate()

    # ==========================================================
    # ORDER STATES
    # ==========================================================

    def is_pending(
        self
    ) -> bool:

        return self.status == "PENDING"

    def is_submitted(
        self
    ) -> bool:

        return self.status == "SUBMITTED"

    def is_partially_filled(
        self
    ) -> bool:

        return self.status == "PARTIALLY_FILLED"

    def is_filled(
        self
    ) -> bool:

        return self.status == "FILLED"

    def is_cancelled(
        self
    ) -> bool:

        return self.status == "CANCELLED"

    def is_rejected(
        self
    ) -> bool:

        return self.status == "REJECTED"

    def is_open(
        self
    ) -> bool:

        return self.status in (

            "PENDING",

            "SUBMITTED",

            "PARTIALLY_FILLED"

        )

    # ==========================================================
    # FILL
    # ==========================================================

    def fill(
        self,
        quantity: float,
        price: float
    ) -> None:

        if quantity <= 0:

            raise ValueError(
                "Fill quantity must be positive."
            )

        if price <= 0:

            raise ValueError(
                "Fill price must be positive."
            )

        if quantity > self.remaining_quantity:

            raise ValueError(
                "Fill exceeds remaining quantity."
            )

        if self.is_cancelled():

            raise RuntimeError(
                "Cancelled order cannot be filled."
            )

        if self.is_rejected():

            raise RuntimeError(
                "Rejected order cannot be filled."
            )

        previous = self.filled_quantity

        self.filled_quantity += quantity

        if previous == 0:

            self.average_fill_price = price

        else:

            self.average_fill_price = (

                (

                    previous

                    *

                    self.average_fill_price

                )

                +

                (

                    quantity

                    *

                    price

                )

            ) / self.filled_quantity

        if self.remaining_quantity == 0:

            self.status = "FILLED"

        else:

            self.status = "PARTIALLY_FILLED"

    # ==========================================================
    # CANCEL
    # ==========================================================

    def cancel(
        self
    ) -> None:

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

        self.status = "CANCELLED"

    # ==========================================================
    # SUBMIT
    # ==========================================================

    def submit(
        self
    ) -> None:

        if not self.is_pending():

            raise RuntimeError(
                "Only pending orders can be submitted."
            )

        self.status = "SUBMITTED"

    # ==========================================================
    # REJECT
    # ==========================================================

    def reject(
        self
    ) -> None:

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

        self.status = "REJECTED"


# ==============================================================
# REGRESSION TESTS
# ==============================================================

def test_order():

    # ==========================================================
    # CREATE ORDER
    # ==========================================================

    order = Order(

        order_id="ORD-000001",

        ticker="SPY",

        side="BUY",

        quantity=100,

        order_type="MARKET"

    )

    # ==========================================================
    # VALIDATION
    # ==========================================================

    assert order.validate()

    assert order.health_check()

    # ==========================================================
    # INITIAL STATE
    # ==========================================================

    assert order.is_pending()

    assert order.is_open()

    assert not order.is_filled()

    assert order.remaining_quantity == 100

    assert order.filled_quantity == 0

    # ==========================================================
    # SUBMIT
    # ==========================================================

    order.submit()

    assert order.is_submitted()

    assert order.is_open()

    # ==========================================================
    # PARTIAL FILL
    # ==========================================================

    order.fill(

        quantity=40,

        price=500.0

    )

    assert order.is_partially_filled()

    assert order.is_open()

    assert order.remaining_quantity == 60

    assert order.filled_quantity == 40

    assert order.average_fill_price == 500.0

    # ==========================================================
    # COMPLETE FILL
    # ==========================================================

    order.fill(

        quantity=60,

        price=505.0

    )

    assert order.is_filled()

    assert not order.is_open()

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

    # ==========================================================
    # CANCEL
    # ==========================================================

    pending = Order(

        order_id="ORD-000002",

        ticker="QQQ",

        side="SELL",

        quantity=50

    )

    assert pending.is_pending()

    pending.cancel()

    assert pending.is_cancelled()

    assert not pending.is_open()

    # ==========================================================
    # SUBMIT THEN CANCEL
    # ==========================================================

    cancellable = Order(

        order_id="ORD-000003",

        ticker="GLD",

        side="BUY",

        quantity=25

    )

    cancellable.submit()

    assert cancellable.is_submitted()

    cancellable.cancel()

    assert cancellable.is_cancelled()

    # ==========================================================
    # REJECT
    # ==========================================================

    rejected = Order(

        order_id="ORD-000004",

        ticker="TLT",

        side="BUY",

        quantity=20

    )

    rejected.reject()

    assert rejected.is_rejected()

    assert not rejected.is_open()

    # ==========================================================
    # INVALID CANCEL
    # ==========================================================

    try:

        order.cancel()

        raise AssertionError(
            "Expected RuntimeError."
        )

    except RuntimeError:

        pass

    # ==========================================================
    # INVALID FILL
    # ==========================================================

    try:

        pending.fill(

            quantity=100,

            price=100.0

        )

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:

        pass

    # ==========================================================
    # INVALID SIDE
    # ==========================================================

    try:

        Order(

            order_id="ORD-000005",

            ticker="SPY",

            side="LONG",

            quantity=100

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

            quantity=100

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

            order_id="ORD-000006",

            ticker="SPY",

            side="BUY",

            quantity=0

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

            order_id="ORD-000007",

            ticker="SPY",

            side="BUY",

            quantity=100,

            filled_quantity=150

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

            order_id="ORD-000008",

            ticker="SPY",

            side="BUY",

            quantity=100,

            order_type="INVALID"

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

            order_id="ORD-000009",

            ticker="SPY",

            side="BUY",

            quantity=100

        )

        fresh_order.fill(

            quantity=10,

            price=0

        )

        raise AssertionError(
            "Expected ValueError."
        )

    except ValueError:

        pass

    print(
        "Order tests passed."
    )


# ==============================================================
# MAIN
# ==============================================================

if __name__ == "__main__":

    test_order()