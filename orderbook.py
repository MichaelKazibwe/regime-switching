"""
======================================================================
orderbook.py
======================================================================

Institutional Order Book

Stores and manages Order objects for the
Order Management System (OMS).

Author: Michael Kazibwe
======================================================================
"""

from __future__ import annotations

from typing import Dict, Optional

from basecomponent import BaseObject
from order import Order
from orderstatus import OrderStatus
from datetime import UTC, datetime

class OrderBook(BaseObject):
    """
    Institutional Order Book.

    Responsible ONLY for storing and retrieving orders.

    It does NOT execute orders.
    """

    API_VERSION = "1.0.0"

    # ==========================================================
    # Constructor
    # ==========================================================

    def __init__(self):

        super().__init__()

        self.active_orders: Dict[str, Order] = {}

        self.completed_orders: Dict[str, Order] = {}

        self.cancelled_orders: Dict[str, Order] = {}

        self.rejected_orders: Dict[str, Order] = {}

        self.order_history: list[dict] = []

        self.last_order: Optional[Order] = None

    # ==========================================================
    # Validation
    # ==========================================================

    @staticmethod
    def _validate_order(order: Order):

        if not isinstance(order, Order):
            raise TypeError(
                "order must be an Order object."
            )

        if not hasattr(order, "order_id"):
            raise AttributeError(
                "Order must have an order_id."
            )

        if not order.order_id:
            raise ValueError(
                "Order ID cannot be empty."
            )

    # ==========================================================
    # Add Order
    # ==========================================================

    def add_order(self, order: Order):

        self._validate_order(order)

        if order.order_id in self.active_orders:
            raise ValueError(
                f"Order '{order.order_id}' already exists."
            )

        self.active_orders[
            order.order_id
        ] = order

        self.last_order = order

        self.order_history.append(
    {
        "timestamp": datetime.now(UTC).isoformat(),
        "order_id": order.order_id,
        "status": "NEW",
    }
)

    # ==========================================================
    # Lookup
    # ==========================================================

    def has_order(
        self,
        order_id: str
    ) -> bool:

        return (
            order_id in self.active_orders
            or order_id in self.completed_orders
            or order_id in self.cancelled_orders
            or order_id in self.rejected_orders
        )

    def get_order(
        self,
        order_id: str
    ) -> Order:

        for container in (
            self.active_orders,
            self.completed_orders,
            self.cancelled_orders,
            self.rejected_orders,
        ):

            if order_id in container:
                return container[order_id]

        raise KeyError(
            f"Order '{order_id}' not found."
        )

    # ==========================================================
    # Remove
    # ==========================================================

    def remove_order(
        self,
        order_id: str
    ):

        if order_id not in self.active_orders:
            raise KeyError(
                f"Order '{order_id}' not found."
            )

        del self.active_orders[order_id]

        self.order_history.append(
            f"Removed {order_id}"
        )

    # ==========================================================
    # Views
    # ==========================================================

    def active(self):

        return list(
            self.active_orders.values()
        )

    def completed(self):

        return list(
            self.completed_orders.values()
        )

    def cancelled(self):

        return list(
            self.cancelled_orders.values()
        )

    def rejected(self):

        return list(
            self.rejected_orders.values()
        )

    # ==========================================================
    # Summary
    # ==========================================================

    def summary(
        self
    ):

        return {

            "active_orders":
                self.active_count,

            "completed_orders":
                self.completed_count,

            "cancelled_orders":
                self.cancelled_count,

            "rejected_orders":
                self.rejected_count,

            "history_events":
                len(
                    self.order_history
                ),

            "last_order":
                None
                if self.last_order is None
                else self.last_order.order_id,
        }

    # ==========================================================
    # Clear
    # ==========================================================

    def clear(self):

        self.active_orders.clear()

        self.completed_orders.clear()

        self.cancelled_orders.clear()

        self.rejected_orders.clear()

        self.order_history.clear()

        self.last_order = None

    def to_dict(self) -> dict:
        """Serialize all order states for durable paper recovery."""
        return {
            "api_version": self.API_VERSION,
            "active_orders": {key: value.to_dict() for key, value in self.active_orders.items()},
            "completed_orders": {key: value.to_dict() for key, value in self.completed_orders.items()},
            "cancelled_orders": {key: value.to_dict() for key, value in self.cancelled_orders.items()},
            "rejected_orders": {key: value.to_dict() for key, value in self.rejected_orders.items()},
            "order_history": list(self.order_history),
            "last_order_id": None if self.last_order is None else self.last_order.order_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrderBook":
        """Restore every canonical order into exactly one lifecycle bucket."""
        if not isinstance(data, dict):
            raise TypeError("OrderBook data must be a dictionary.")
        book = cls()
        for bucket_name in ("active_orders", "completed_orders", "cancelled_orders", "rejected_orders"):
            bucket_data = data.get(bucket_name, {})
            if not isinstance(bucket_data, dict):
                raise TypeError(f"{bucket_name} must be a dictionary.")
            bucket = getattr(book, bucket_name)
            for order_id, order_data in bucket_data.items():
                order = Order.from_dict(order_data)
                if order.order_id != order_id or book.has_order(order_id):
                    raise ValueError("OrderBook contains a duplicate or mismatched order ID.")
                bucket[order_id] = order
        book.order_history = list(data.get("order_history", []))
        last_order_id = data.get("last_order_id")
        if last_order_id is not None:
            book.last_order = book.get_order(last_order_id)
        return book

    # ==========================================================
    # Internal State Transition
    # ==========================================================

    def _move_order(
        self,
        order_id: str,
        destination: dict[str, Order],
        new_status: OrderStatus,
    ) -> Order:

        if order_id not in self.active_orders:

            raise KeyError(
                f"Order '{order_id}' not found in active orders."
            )

        order = self.active_orders.pop(
            order_id
        )

        order.status = new_status.name

        destination[order_id] = order

        self.last_order = order

        self.order_history.append(
            {
                "timestamp":
                    datetime.now(UTC).isoformat(),

                "order_id":
                    order_id,

                "status":
                    new_status.name,
            }
        )

        return order

    # ==========================================================
    # Complete Order
    # ==========================================================

    def complete_order(
        self,
        order_id: str,
    ) -> Order:

        return self._move_order(
            order_id,
            self.completed_orders,
            OrderStatus.FILLED,
        )

    # ==========================================================
    # Cancel Order
    # ==========================================================

    def cancel_order(
        self,
        order_id: str,
    ) -> Order:

        return self._move_order(
            order_id,
            self.cancelled_orders,
            OrderStatus.CANCELLED,
        )

    # ==========================================================
    # Reject Order
    # ==========================================================

    def reject_order(
        self,
        order_id: str,
    ) -> Order:

        return self._move_order(
            order_id,
            self.rejected_orders,
            OrderStatus.REJECTED,
        )

    # ==========================================================
    # ORDER COUNTS
    # ==========================================================

    @property
    def active_count(
        self
    ):

        return len(
            self.active_orders
        )

    @property
    def completed_count(
        self
    ):

        return len(
            self.completed_orders
        )

    @property
    def cancelled_count(
        self
    ):

        return len(
            self.cancelled_orders
        )

    @property
    def rejected_count(
        self
    ):

        return len(
            self.rejected_orders
        )

# ==========================================================
# TESTS
# ==========================================================

def test_orderbook():

    # ======================================================
    # PHASE I — BASIC ORDER STORAGE
    # ======================================================

    book = OrderBook()

    order = Order(

        order_id="ORD-TEST-000001",

        ticker="SPY",

        side="BUY",

        quantity=100

    )

    book.add_order(

        order

    )

    # ------------------------------------------------------
    # ADD / LOOKUP
    # ------------------------------------------------------

    assert book.has_order(

        "ORD-TEST-000001"

    )

    retrieved = book.get_order(

        "ORD-TEST-000001"

    )

    assert retrieved is order

    # ------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------

    summary = book.summary()

    assert summary["active_orders"] == 1

    assert summary["completed_orders"] == 0

    assert summary["cancelled_orders"] == 0

    assert summary["rejected_orders"] == 0

    # ------------------------------------------------------
    # LAST ORDER
    # ------------------------------------------------------

    assert book.last_order is order

    # ------------------------------------------------------
    # REMOVE
    # ------------------------------------------------------

    book.remove_order(

        "ORD-TEST-000001"

    )

    assert not book.has_order(

        "ORD-TEST-000001"

    )

    assert book.active_count == 0

    print(

        "OrderBook Phase I tests passed."

    )

    # ======================================================
    # PHASE II — ORDER STATE TRANSITIONS
    # ======================================================

    # Use a fresh book so Phase I cannot contaminate
    # Phase II state or counters.

    book = OrderBook()

    order1 = Order(

        order_id="ORD-000001",

        ticker="SPY",

        side="BUY",

        quantity=100

    )

    order2 = Order(

        order_id="ORD-000002",

        ticker="QQQ",

        side="SELL",

        quantity=50

    )

    order3 = Order(

        order_id="ORD-000003",

        ticker="GLD",

        side="BUY",

        quantity=25

    )

    # ------------------------------------------------------
    # ADD ORDERS
    # ------------------------------------------------------

    book.add_order(

        order1

    )

    book.add_order(

        order2

    )

    book.add_order(

        order3

    )

    assert book.active_count == 3

    # ------------------------------------------------------
    # STATE TRANSITIONS
    # ------------------------------------------------------

    book.complete_order(

        "ORD-000001"

    )

    book.cancel_order(

        "ORD-000002"

    )

    book.reject_order(

        "ORD-000003"

    )

    # ------------------------------------------------------
    # COUNTS
    # ------------------------------------------------------

    assert book.active_count == 0

    assert book.completed_count == 1

    assert book.cancelled_count == 1

    assert book.rejected_count == 1

    # ------------------------------------------------------
    # STATUS
    # ------------------------------------------------------

    assert (

        book.get_order(

            "ORD-000001"

        ).status

        == OrderStatus.FILLED.name

    )

    assert (

        book.get_order(

            "ORD-000002"

        ).status

        == OrderStatus.CANCELLED.name

    )

    assert (

        book.get_order(

            "ORD-000003"

        ).status

        == OrderStatus.REJECTED.name

    )

    # ------------------------------------------------------
    # ORDER RETRIEVAL
    # ------------------------------------------------------

    assert (

        book.get_order(

            "ORD-000001"

        ) is order1

    )

    assert (

        book.get_order(

            "ORD-000002"

        ) is order2

    )

    assert (

        book.get_order(

            "ORD-000003"

        ) is order3

    )

    # ------------------------------------------------------
    # HISTORY
    # ------------------------------------------------------

    assert len(

        book.order_history

    ) == 6

    # Three NEW events

    assert book.order_history[0]["order_id"] == (

        "ORD-000001"

    )

    assert book.order_history[0]["status"] == "NEW"

    assert book.order_history[1]["order_id"] == (

        "ORD-000002"

    )

    assert book.order_history[1]["status"] == "NEW"

    assert book.order_history[2]["order_id"] == (

        "ORD-000003"

    )

    assert book.order_history[2]["status"] == "NEW"

    # Three transition events

    assert book.order_history[3]["order_id"] == (

        "ORD-000001"

    )

    assert book.order_history[3]["status"] == (

        OrderStatus.FILLED.name

    )

    assert book.order_history[4]["order_id"] == (

        "ORD-000002"

    )

    assert book.order_history[4]["status"] == (

        OrderStatus.CANCELLED.name

    )

    assert book.order_history[5]["order_id"] == (

        "ORD-000003"

    )

    assert book.order_history[5]["status"] == (

        OrderStatus.REJECTED.name

    )

    # ------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------

    summary = book.summary()

    assert summary["active_orders"] == 0

    assert summary["completed_orders"] == 1

    assert summary["cancelled_orders"] == 1

    assert summary["rejected_orders"] == 1

    print(

        "OrderBook Phase II tests passed."

    )

    # ======================================================
    # FINAL RESULT
    # ======================================================

    print(

        "\nAll OrderBook tests passed."

    )


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":

    test_orderbook()
