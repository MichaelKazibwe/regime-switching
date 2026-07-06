"""
===============================================================
ORDER

Institutional Order Object

Represents an order submitted for execution.

===============================================================
"""

from __future__ import annotations

from dataclasses import dataclass


# ============================================================
# ORDER
# ============================================================

@dataclass
class Order:

    ticker: str

    side: str

    quantity: float

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

    # ========================================================
    # REMAINING QUANTITY
    # ========================================================

    @property
    def remaining_quantity(
        self
    ):

        return max(

            0.0,

            self.quantity

            -

            self.filled_quantity

        )

    # ========================================================
    # FILLED
    # ========================================================

    @property
    def filled(
        self
    ):

        return self.remaining_quantity == 0.0
    
    # ========================================================
    # VALIDATE
    # ========================================================

    def validate(
        self
    ):

        if not self.ticker:

            raise ValueError(
                "Ticker cannot be empty."
            )

        if self.quantity <= 0:

            raise ValueError(
                "Quantity must be positive."
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

        return True
    
    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ):

        return {

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
    
    # ========================================================
    # TO DICTIONARY
    # ========================================================

    def to_dict(
        self
    ):

        return {

            key: value

            for key, value

            in self.__dict__.items()

        }

    # ========================================================
    # FROM DICTIONARY
    # ========================================================

    @classmethod
    def from_dict(
        cls,
        data
    ):

        return cls(

            **data

        )
    
    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ):

        return self.validate()
    
        # ========================================================
    # ORDER STATES
    # ========================================================

    def is_pending(
        self
    ):

        return self.status == "PENDING"

    def is_submitted(
        self
    ):

        return self.status == "SUBMITTED"

    def is_partially_filled(
        self
    ):

        return self.status == "PARTIALLY_FILLED"

    def is_filled(
        self
    ):

        return self.status == "FILLED"

    def is_cancelled(
        self
    ):

        return self.status == "CANCELLED"

    def is_rejected(
        self
    ):

        return self.status == "REJECTED"

    def is_open(
        self
    ):

        return self.status in (

            "PENDING",

            "SUBMITTED",

            "PARTIALLY_FILLED"

        )
    
        # ========================================================
    # FILL
    # ========================================================

    def fill(
        self,
        quantity: float,
        price: float
    ):

        if quantity <= 0:

            raise ValueError(
                "Fill quantity must be positive."
            )

        if quantity > self.remaining_quantity:

            raise ValueError(
                "Fill exceeds remaining quantity."
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

        # ========================================================
    # CANCEL
    # ========================================================

    def cancel(
        self
    ):

        if self.is_filled():

            raise RuntimeError(

                "Filled order cannot be cancelled."

            )

        self.status = "CANCELLED"

# ============================================================
# REGRESSION TESTS
# ============================================================

def test_order():

    order = Order(

        ticker="SPY",

        side="BUY",

        quantity=100,

        order_type="MARKET"

    )

    # ========================================================
    # VALIDATION
    # ========================================================

    assert order.validate()

    assert order.health_check()

    # ========================================================
    # INITIAL STATE
    # ========================================================

    assert order.is_pending()

    assert order.is_open()

    assert not order.is_filled()

    assert order.remaining_quantity == 100

    # ========================================================
    # PARTIAL FILL
    # ========================================================

    order.fill(

        quantity=40,

        price=500.0

    )

    assert order.is_partially_filled()

    assert order.remaining_quantity == 60

    assert order.average_fill_price == 500.0

    # ========================================================
    # COMPLETE FILL
    # ========================================================

    order.fill(

        quantity=60,

        price=505.0

    )

    assert order.is_filled()

    assert order.remaining_quantity == 0

    assert order.filled_quantity == 100

    assert order.average_fill_price == 503.0

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = order.summary()

    assert summary["ticker"] == "SPY"

    assert summary["status"] == "FILLED"

    assert summary["trade_value"] == (

        503.0

        *

        100

    )

    # ========================================================
    # SERIALIZATION
    # ========================================================

    exported = order.to_dict()

    restored = Order.from_dict(

        exported

    )

    assert restored.ticker == order.ticker

    assert restored.status == order.status

    # ========================================================
    # CANCEL
    # ========================================================

    pending = Order(

        ticker="QQQ",

        side="SELL",

        quantity=50

    )

    pending.cancel()

    assert pending.is_cancelled()

    # ========================================================
    # INVALID CANCEL
    # ========================================================

    try:

        order.cancel()

        raise AssertionError(

            "Expected RuntimeError"

        )

    except RuntimeError:

        pass

    # ========================================================
    # INVALID FILL
    # ========================================================

    try:

        pending.fill(

            quantity=100,

            price=100.0

        )

        raise AssertionError(

            "Expected ValueError"

        )

    except ValueError:

        pass

    # ========================================================
    # INVALID SIDE
    # ========================================================

    try:

        Order(

            ticker="SPY",

            side="LONG",

            quantity=100

        ).validate()

        raise AssertionError(

            "Expected ValueError"

        )

    except ValueError:

        pass

    print(

        "Order tests passed."

    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_order()