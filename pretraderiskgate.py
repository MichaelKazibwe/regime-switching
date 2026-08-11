"""
======================================================================
pretraderiskgate.py

Institutional Pre-Trade Risk Gate

Phase III-B.2-A

Provides deterministic pre-trade controls before an order is
submitted for execution.

Responsibilities:

    - order validation
    - quantity limits
    - notional limits
    - cash availability
    - sell-position availability
    - execution-price validation
    - deterministic risk decisions
    - risk decision audit information
    - serialization
    - health checks
    - regression tests

The PreTradeRiskGate does NOT:

    - execute orders
    - modify portfolio accounting
    - submit orders to the OrderBook
    - generate portfolio targets
    - calculate portfolio optimization

Author: Michael Kazibwe
======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


from order import Order
from portfolioaccount import PortfolioAccount


# ============================================================
# RISK DECISION
# ============================================================


@dataclass(frozen=True)
class RiskDecision:
    """
    Immutable result of a pre-trade risk check.
    """

    approved: bool

    reason: Optional[str]

    order_id: Optional[str]

    ticker: Optional[str]

    side: Optional[str]

    quantity: float

    execution_price: float

    notional: float

    available_cash: float

    available_position: float

    limit_quantity: Optional[float]

    limit_notional: Optional[float]

    # ========================================================
    # TO DICTIONARY
    # ========================================================

    def to_dict(
        self
    ) -> dict:

        return {

            "approved":
                self.approved,

            "reason":
                self.reason,

            "order_id":
                self.order_id,

            "ticker":
                self.ticker,

            "side":
                self.side,

            "quantity":
                self.quantity,

            "execution_price":
                self.execution_price,

            "notional":
                self.notional,

            "available_cash":
                self.available_cash,

            "available_position":
                self.available_position,

            "limit_quantity":
                self.limit_quantity,

            "limit_notional":
                self.limit_notional,

        }


# ============================================================
# PRE-TRADE RISK GATE
# ============================================================


class PreTradeRiskGate:
    """
    Institutional pre-trade risk control.

    The gate evaluates an order and returns a deterministic
    RiskDecision.

    It does not mutate the order or account.
    """

    API_VERSION = "1.0.0"

    # ========================================================
    # REJECTION REASONS
    # ========================================================

    INVALID_ORDER = "INVALID_ORDER"

    INVALID_EXECUTION_PRICE = (
        "INVALID_EXECUTION_PRICE"
    )

    QUANTITY_LIMIT_EXCEEDED = (
        "QUANTITY_LIMIT_EXCEEDED"
    )

    NOTIONAL_LIMIT_EXCEEDED = (
        "NOTIONAL_LIMIT_EXCEEDED"
    )

    INSUFFICIENT_CASH = (
        "INSUFFICIENT_CASH"
    )

    INSUFFICIENT_POSITION = (
        "INSUFFICIENT_POSITION"
    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(
        self,
        max_order_quantity: Optional[float] = None,
        max_order_notional: Optional[float] = None,
    ):

        if (
            max_order_quantity is not None
            and max_order_quantity <= 0
        ):

            raise ValueError(
                "max_order_quantity must be positive."
            )

        if (
            max_order_notional is not None
            and max_order_notional <= 0
        ):

            raise ValueError(
                "max_order_notional must be positive."
            )

        self.max_order_quantity = (
            max_order_quantity
        )

        self.max_order_notional = (
            max_order_notional
        )

        self.last_decision: Optional[
            RiskDecision
        ] = None

    # ========================================================
    # ORDER VALIDATION
    # ========================================================

    @staticmethod
    def validate_order(
        order: Order
    ) -> bool:

        if not isinstance(
            order,
            Order
        ):

            raise TypeError(
                "order must be an Order object."
            )

        order.validate()

        return True

    # ========================================================
    # EXECUTION PRICE
    # ========================================================

    @staticmethod
    def check_execution_price(
        execution_price: float
    ) -> bool:

        if execution_price <= 0:

            raise ValueError(
                PreTradeRiskGate.INVALID_EXECUTION_PRICE
            )

        return True

    # ========================================================
    # QUANTITY
    # ========================================================

    def check_quantity(
        self,
        quantity: float
    ) -> bool:

        if quantity <= 0:

            raise ValueError(
                PreTradeRiskGate.INVALID_ORDER
            )

        if (

            self.max_order_quantity is not None

            and quantity
            > self.max_order_quantity

        ):

            raise ValueError(
                PreTradeRiskGate
                .QUANTITY_LIMIT_EXCEEDED
            )

        return True

    # ========================================================
    # NOTIONAL
    # ========================================================

    def check_notional(
        self,
        notional: float
    ) -> bool:

        if notional <= 0:

            raise ValueError(
                PreTradeRiskGate.INVALID_ORDER
            )

        if (

            self.max_order_notional is not None

            and notional
            > self.max_order_notional

        ):

            raise ValueError(
                PreTradeRiskGate
                .NOTIONAL_LIMIT_EXCEEDED
            )

        return True

    # ========================================================
    # POSITION
    # ========================================================

    @staticmethod
    def available_position(
        order: Order,
        account: PortfolioAccount
    ) -> float:

        if order.side != "SELL":

            return float(
                getattr(
                    account.positions.get(
                        order.ticker
                    ),
                    "shares",
                    0.0
                )
            )

        position = account.positions.get(
            order.ticker
        )

        if position is None:

            return 0.0

        return float(
            getattr(
                position,
                "shares",
                0.0
            )
        )

    # ========================================================
    # CASH
    # ========================================================

    @staticmethod
    def available_cash(
        account: PortfolioAccount
    ) -> float:

        return float(
            account.cash
        )

    # ========================================================
    # CHECK CASH
    # ========================================================

    def check_cash(
        self,
        order: Order,
        notional: float,
        account: PortfolioAccount,
    ) -> bool:

        if order.side != "BUY":

            return True

        available_cash = (
            self.available_cash(
                account
            )
        )

        if notional > available_cash:

            raise ValueError(
                self.INSUFFICIENT_CASH
            )

        return True

    # ========================================================
    # CHECK POSITION
    # ========================================================

    def check_position(
        self,
        order: Order,
        account: PortfolioAccount,
    ) -> bool:

        if order.side != "SELL":

            return True

        available = (
            self.available_position(
                order,
                account
            )
        )

        if order.quantity > available:

            raise ValueError(
                self.INSUFFICIENT_POSITION
            )

        return True

    # ========================================================
    # BUILD DECISION
    # ========================================================

    def _decision(
        self,
        order: Order,
        account: PortfolioAccount,
        execution_price: float,
        approved: bool,
        reason: Optional[str],
    ) -> RiskDecision:

        notional = (
            abs(order.quantity)
            * execution_price
        )

        available_cash = (
            self.available_cash(
                account
            )
        )

        available_position = (
            self.available_position(
                order,
                account
            )
        )

        decision = RiskDecision(

            approved=approved,

            reason=reason,

            order_id=getattr(
                order,
                "order_id",
                None
            ),

            ticker=getattr(
                order,
                "ticker",
                None
            ),

            side=getattr(
                order,
                "side",
                None
            ),

            quantity=float(
                getattr(
                    order,
                    "quantity",
                    0.0
                )
            ),

            execution_price=float(
                execution_price
            ),

            notional=float(
                notional
            ),

            available_cash=float(
                available_cash
            ),

            available_position=float(
                available_position
            ),

            limit_quantity=(
                self.max_order_quantity
            ),

            limit_notional=(
                self.max_order_notional
            ),

        )

        self.last_decision = decision

        return decision

    # ========================================================
    # CENTRAL CHECK
    # ========================================================

    def check(
        self,
        order: Order,
        account: PortfolioAccount,
        execution_price: float,
    ) -> RiskDecision:
        """
        Evaluate an order without mutating state.
        """

        try:

            self.validate_order(
                order
            )

        except (
            TypeError,
            ValueError,
        ):

            return self._decision(

                order,

                account,

                execution_price,

                False,

                self.INVALID_ORDER,

            )

        # ----------------------------------------------------
        # EXECUTION PRICE
        # ----------------------------------------------------

        if execution_price <= 0:

            return self._decision(

                order,

                account,

                execution_price,

                False,

                self.INVALID_EXECUTION_PRICE,

            )

        # ----------------------------------------------------
        # QUANTITY
        # ----------------------------------------------------

        try:

            self.check_quantity(
                order.quantity
            )

        except ValueError as exc:

            return self._decision(

                order,

                account,

                execution_price,

                False,

                str(exc),

            )

        # ----------------------------------------------------
        # NOTIONAL
        # ----------------------------------------------------

        notional = (

            abs(order.quantity)
            * execution_price

        )

        try:

            self.check_notional(
                notional
            )

        except ValueError as exc:

            return self._decision(

                order,

                account,

                execution_price,

                False,

                str(exc),

            )

        # ----------------------------------------------------
        # CASH
        # ----------------------------------------------------

        try:

            self.check_cash(

                order,

                notional,

                account,

            )

        except ValueError as exc:

            return self._decision(

                order,

                account,

                execution_price,

                False,

                str(exc),

            )

        # ----------------------------------------------------
        # POSITION
        # ----------------------------------------------------

        try:

            self.check_position(

                order,

                account,

            )

        except ValueError as exc:

            return self._decision(

                order,

                account,

                execution_price,

                False,

                str(exc),

            )

        # ----------------------------------------------------
        # APPROVED
        # ----------------------------------------------------

        return self._decision(

            order,

            account,

            execution_price,

            True,

            None,

        )

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ) -> dict:

        return {

            "api_version":
                self.API_VERSION,

            "max_order_quantity":
                self.max_order_quantity,

            "max_order_notional":
                self.max_order_notional,

            "last_decision":
                None
                if self.last_decision is None
                else self.last_decision.to_dict(),

        }

    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(
        self
    ) -> dict:

        return {

            "component":
                "PreTradeRiskGate",

            "api_version":
                self.API_VERSION,

            "phase":
                "III-B.2-A",

            "summary":
                self.summary(),

        }

    # ========================================================
    # PUBLIC METHODS
    # ========================================================

    @property
    def public_methods(
        self
    ) -> list[str]:

        return [

            "validate_order",

            "check_execution_price",

            "check_quantity",

            "check_notional",

            "available_position",

            "available_cash",

            "check_cash",

            "check_position",

            "check",

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
    ) -> bool:

        if (

            self.max_order_quantity is not None

            and self.max_order_quantity <= 0

        ):

            raise RuntimeError(
                "Invalid quantity limit."
            )

        if (

            self.max_order_notional is not None

            and self.max_order_notional <= 0

        ):

            raise RuntimeError(
                "Invalid notional limit."
            )

        return True

    # ========================================================
    # TO DICTIONARY
    # ========================================================

    def to_dict(
        self
    ) -> dict:

        return {

            "api_version":
                self.API_VERSION,

            "max_order_quantity":
                self.max_order_quantity,

            "max_order_notional":
                self.max_order_notional,

            "last_decision":
                None
                if self.last_decision is None
                else self.last_decision.to_dict(),

        }

    # ========================================================
    # FROM DICTIONARY
    # ========================================================

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ):

        gate = cls(

            max_order_quantity=data.get(
                "max_order_quantity"
            ),

            max_order_notional=data.get(
                "max_order_notional"
            ),

        )

        decision = data.get(
            "last_decision"
        )

        if decision is not None:

            gate.last_decision = (
                RiskDecision(
                    **decision
                )
            )

        return gate


# ============================================================
# REGRESSION TESTS
# ============================================================


def test_pre_trade_risk_gate():

    account = PortfolioAccount(

        initial_cash=100000.0

    )

    gate = PreTradeRiskGate(

        max_order_quantity=1000.0,

        max_order_notional=50000.0,

    )

    # ========================================================
    # VALID BUY
    # ========================================================

    buy = Order(

        order_id="RISK-000001",

        ticker="SPY",

        side="BUY",

        quantity=50,

    )

    decision = gate.check(

        buy,

        account,

        500.0,

    )

    assert decision.approved

    assert decision.reason is None

    assert decision.notional == 25000.0

    assert decision.available_cash == 100000.0

    assert decision.order_id == (
        "RISK-000001"
    )

    # ========================================================
    # INVALID EXECUTION PRICE
    # ========================================================

    invalid_price = gate.check(

        buy,

        account,

        0.0,

    )

    assert not invalid_price.approved

    assert invalid_price.reason == (
        gate.INVALID_EXECUTION_PRICE
    )

    # ========================================================
    # QUANTITY LIMIT
    # ========================================================

    quantity_limit = Order(

        order_id="RISK-000002",

        ticker="SPY",

        side="BUY",

        quantity=1001,

    )

    decision = gate.check(

        quantity_limit,

        account,

        100.0,

    )

    assert not decision.approved

    assert decision.reason == (
        gate.QUANTITY_LIMIT_EXCEEDED
    )

    # ========================================================
    # NOTIONAL LIMIT
    # ========================================================

    notional_limit = Order(

        order_id="RISK-000003",

        ticker="SPY",

        side="BUY",

        quantity=100,

    )

    decision = gate.check(

        notional_limit,

        account,

        600.0,

    )

    assert not decision.approved

    assert decision.reason == (
        gate.NOTIONAL_LIMIT_EXCEEDED
    )

    # ========================================================
    # INSUFFICIENT CASH
    # ========================================================

    cash_limited_account = PortfolioAccount(

        initial_cash=40000.0

    )

    cash_limit = Order(

        order_id="RISK-000004",

        ticker="SPY",

        side="BUY",

        quantity=90,

    )

    decision = gate.check(

        cash_limit,

        cash_limited_account,

        500.0,

    )

    assert not decision.approved

    assert decision.reason == (
        gate.INSUFFICIENT_CASH
    )

    assert decision.notional == 45000.0

    assert decision.available_cash == 40000.0

    # ========================================================
    # SELL WITHOUT POSITION
    # ========================================================

    sell = Order(

        order_id="RISK-000005",

        ticker="QQQ",

        side="SELL",

        quantity=10,

    )

    decision = gate.check(

        sell,

        account,

        400.0,

    )

    assert not decision.approved

    assert decision.reason == (
        gate.INSUFFICIENT_POSITION
    )

    # ========================================================
    # SELL WITH POSITION
    # ========================================================

    account.update_position(
    ticker="SPY",
    shares=100,
    average_cost=500.0,
)

    # We only test the risk gate here.
    # The account remains unchanged because the
    # risk gate must never mutate portfolio state.
    account.update_position(
    ticker="SPY",
    shares=100,
    average_cost=500.0,
)

    sell_existing = Order(

        order_id="RISK-000007",

        ticker="SPY",

        side="SELL",

        quantity=50,

    )

    decision = gate.check(

        sell_existing,

        account,

        500.0,

    )

    assert decision.approved

    assert decision.available_position == 100.0

    # ========================================================
    # EXCESSIVE SELL
    # ========================================================

    excess_sell = Order(

        order_id="RISK-000008",

        ticker="SPY",

        side="SELL",

        quantity=101,

    )

    decision = gate.check(

        excess_sell,

        account,

        400.0,

    )

    assert not decision.approved

    assert decision.reason == (
        gate.INSUFFICIENT_POSITION
    )

    # ========================================================
    # NO STATE MUTATION
    # ========================================================

    assert account.cash == 100000.0

    assert account.positions[
        "SPY"
    ].shares == 100

    # ========================================================
    # LAST DECISION
    # ========================================================

    assert gate.last_decision is decision

    assert not gate.last_decision.approved

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = gate.summary()

    assert summary[
        "api_version"
    ] == gate.API_VERSION

    assert summary[
        "max_order_quantity"
    ] == 1000.0

    assert summary[
        "max_order_notional"
    ] == 50000.0

    # ========================================================
    # SERIALIZATION
    # ========================================================

    exported = gate.to_dict()

    restored = (
        PreTradeRiskGate.from_dict(
            exported
        )
    )

    assert restored.max_order_quantity == (
        gate.max_order_quantity
    )

    assert restored.max_order_notional == (
        gate.max_order_notional
    )

    assert (
        restored.last_decision.to_dict()
        == gate.last_decision.to_dict()
    )

    # ========================================================
    # HEALTH
    # ========================================================

    assert gate.health_check()

    # ========================================================
    # PUBLIC API
    # ========================================================

    assert (
        "check"
        in gate.public_methods
    )

    assert (
        "check_cash"
        in gate.public_methods
    )

    assert (
        "check_position"
        in gate.public_methods
    )

    print(
        "PreTradeRiskGate Phase III-B.2-A tests passed."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_pre_trade_risk_gate()