"""
======================================================================
orderstatus.py
======================================================================

Institutional Order Management System (OMS)

Defines the lifecycle states for every order.

Author: Michael Kazibwe
======================================================================
"""

from __future__ import annotations

from enum import Enum, auto


class OrderStatus(Enum):
    """
    Order lifecycle states.
    """

    NEW = auto()

    VALIDATED = auto()

    PENDING = auto()

    PARTIALLY_FILLED = auto()

    FILLED = auto()

    CANCELLED = auto()

    REJECTED = auto()

    EXPIRED = auto()

    SUSPENDED = auto()

    def __str__(self) -> str:
        return self.name

    @classmethod
    def terminal_states(cls) -> set["OrderStatus"]:
        """
        States from which an order cannot transition.
        """
        return {
            cls.FILLED,
            cls.CANCELLED,
            cls.REJECTED,
            cls.EXPIRED,
        }

    @classmethod
    def active_states(cls) -> set["OrderStatus"]:
        """
        Orders that are still alive.
        """
        return {
            cls.NEW,
            cls.VALIDATED,
            cls.PENDING,
            cls.PARTIALLY_FILLED,
            cls.SUSPENDED,
        }

    @property
    def is_terminal(self) -> bool:
        return self in self.terminal_states()

    @property
    def is_active(self) -> bool:
        return self in self.active_states()

# ========================================================
# TESTS
# ========================================================

def test_order_status():

    assert OrderStatus.NEW.is_active

    assert not OrderStatus.NEW.is_terminal

    assert OrderStatus.FILLED.is_terminal

    assert not OrderStatus.FILLED.is_active

    assert OrderStatus.REJECTED.is_terminal

    assert str(OrderStatus.CANCELLED) == "CANCELLED"

    print("OrderStatus tests passed.")


if __name__ == "__main__":

    test_order_status()