"""
======================================================================
tradegenerator.py

Institutional Trade Generator
======================================================================

Converts portfolio target positions into executable Order objects.

Responsibilities
----------------

    - reconcile current positions against target positions
    - calculate position deltas
    - determine BUY / SELL direction
    - apply minimum trade thresholds
    - generate deterministic order IDs
    - generate individual orders
    - generate batches of orders
    - provide metadata
    - provide health checks
    - provide serialization
    - provide regression tests

The TradeGenerator does NOT:

    - perform portfolio optimization
    - perform pre-trade risk checks
    - submit orders to the OMS
    - execute trades
    - route orders to brokers
    - modify portfolio accounting

Those responsibilities belong to:

    PortfolioOptimizer
    PreTradeRiskGate
    OMS
    BrokerRouter
    ExecutionEngine
    PortfolioAccount

Architecture
------------

    Portfolio / RebalanceEngine
                |
                v
         TradeGenerator
                |
                v
             Order
                |
                v
        PreTradeRiskGate
                |
                v
              OMS
                |
                v
          BrokerRouter

Author: Michael Kazibwe
Version: 1.0.0
======================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from order import Order
from portfolioaccount import PortfolioAccount


# ======================================================================
# TRADE INSTRUCTION
# ======================================================================


@dataclass(frozen=True)
class TradeInstruction:
    """
    Immutable description of a portfolio trade.

    This is an intermediate representation used before an Order
    object is created.
    """

    ticker: str
    side: str
    quantity: float
    current_position: float
    target_position: float
    delta: float
    execution_price: Optional[float] = None

    @property
    def notional(self) -> Optional[float]:
        """
        Return estimated trade notional when a price is available.
        """

        if self.execution_price is None:
            return None

        return abs(
            self.quantity
            * self.execution_price
        )

    def to_dict(self) -> dict:
        """
        Serialize the trade instruction.
        """

        return {
            "ticker": self.ticker,
            "side": self.side,
            "quantity": self.quantity,
            "current_position": self.current_position,
            "target_position": self.target_position,
            "delta": self.delta,
            "execution_price": self.execution_price,
            "notional": self.notional,
        }


# ======================================================================
# TRADE GENERATOR
# ======================================================================


class TradeGenerator:
    """
    Institutional trade-generation engine.

    Converts current portfolio positions and target positions into
    deterministic Order objects.

    No portfolio state is modified by this class.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (
        "generate_instruction",
        "generate_order",
        "generate_orders",
        "generate_from_account",
        "reconcile",
        "summary",
        "metadata",
        "health_check",
        "to_dict",
        "from_dict",
    )

    BUY = "BUY"
    SELL = "SELL"

    # ==================================================================
    # CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        minimum_trade_quantity: float = 0.0,
        minimum_trade_notional: Optional[float] = None,
        order_type: str = "MARKET",
        time_in_force: str = "DAY",
        order_id_prefix: str = "TRD",
    ):
        """
        Parameters
        ----------
        minimum_trade_quantity:
            Minimum absolute position delta required to generate
            an order.

        minimum_trade_notional:
            Optional minimum estimated trade notional.

        order_type:
            Order type passed to Order.

        time_in_force:
            Time-in-force passed to Order.

        order_id_prefix:
            Prefix used for deterministic generated order IDs.
        """

        if minimum_trade_quantity < 0:
            raise ValueError(
                "minimum_trade_quantity cannot be negative."
            )

        if (
            minimum_trade_notional is not None
            and minimum_trade_notional < 0
        ):
            raise ValueError(
                "minimum_trade_notional cannot be negative."
            )

        if not order_type:
            raise ValueError(
                "order_type cannot be empty."
            )

        if not time_in_force:
            raise ValueError(
                "time_in_force cannot be empty."
            )

        if not order_id_prefix:
            raise ValueError(
                "order_id_prefix cannot be empty."
            )

        self.minimum_trade_quantity = float(
            minimum_trade_quantity
        )

        self.minimum_trade_notional = (
            None
            if minimum_trade_notional is None
            else float(minimum_trade_notional)
        )

        self.order_type = str(
            order_type
        ).upper()

        self.time_in_force = str(
            time_in_force
        ).upper()

        self.order_id_prefix = str(
            order_id_prefix
        ).upper()

        self.last_instructions: list[
            TradeInstruction
        ] = []

        self.last_orders: list[Order] = []

        self._generation_count = 0

    # ==================================================================
    # NORMALIZATION
    # ==================================================================

    @staticmethod
    def _validate_ticker(
        ticker: str,
    ) -> str:
        """
        Validate and normalize a ticker.
        """

        if not isinstance(
            ticker,
            str,
        ):
            raise TypeError(
                "ticker must be a string."
            )

        ticker = ticker.strip().upper()

        if not ticker:
            raise ValueError(
                "ticker cannot be empty."
            )

        return ticker

    @staticmethod
    def _validate_position(
        value: float,
        name: str,
    ) -> float:
        """
        Validate a portfolio position.
        """

        try:
            value = float(value)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise TypeError(
                f"{name} must be numeric."
            ) from exc

        if not value == value:
            raise ValueError(
                f"{name} cannot be NaN."
            )

        return value

    # ==================================================================
    # CURRENT POSITION
    # ==================================================================

    @staticmethod
    def current_position(
        account: PortfolioAccount,
        ticker: str,
    ) -> float:
        """
        Return the current number of shares for a ticker.

        Missing positions are treated as zero.
        """

        if not isinstance(
            account,
            PortfolioAccount,
        ):
            raise TypeError(
                "account must be a PortfolioAccount."
            )

        ticker = TradeGenerator._validate_ticker(
            ticker
        )

        position = account.positions.get(
            ticker
        )

        if position is None:
            return 0.0

        return float(
            position.shares
        )

    # ==================================================================
    # DELTA
    # ==================================================================

    @staticmethod
    def position_delta(
        current_position: float,
        target_position: float,
    ) -> float:
        """
        Calculate target minus current position.

        Positive delta = BUY
        Negative delta = SELL
        Zero delta = no trade
        """

        current = TradeGenerator._validate_position(
            current_position,
            "current_position",
        )

        target = TradeGenerator._validate_position(
            target_position,
            "target_position",
        )

        return target - current

    # ==================================================================
    # SIDE
    # ==================================================================

    @staticmethod
    def determine_side(
        delta: float,
    ) -> Optional[str]:
        """
        Determine trade direction from a position delta.
        """

        delta = float(delta)

        if delta > 0:
            return TradeGenerator.BUY

        if delta < 0:
            return TradeGenerator.SELL

        return None

    # ==================================================================
    # QUANTITY
    # ==================================================================

    @staticmethod
    def trade_quantity(
        delta: float,
    ) -> float:
        """
        Return the absolute quantity to trade.
        """

        return abs(
            float(delta)
        )

    # ==================================================================
    # THRESHOLD
    # ==================================================================

    def passes_quantity_threshold(
        self,
        quantity: float,
    ) -> bool:
        """
        Determine whether a quantity is large enough to trade.
        """

        return (
            abs(float(quantity))
            >= self.minimum_trade_quantity
        )

    # ==================================================================
    # NOTIONAL THRESHOLD
    # ==================================================================

    def passes_notional_threshold(
        self,
        quantity: float,
        execution_price: Optional[float],
    ) -> bool:
        """
        Determine whether a trade passes the optional notional
        threshold.
        """

        if self.minimum_trade_notional is None:
            return True

        if execution_price is None:
            raise ValueError(
                "execution_price is required when "
                "minimum_trade_notional is configured."
            )

        execution_price = float(
            execution_price
        )

        if execution_price <= 0:
            raise ValueError(
                "execution_price must be positive."
            )

        notional = abs(
            float(quantity)
            * execution_price
        )

        return (
            notional
            >= self.minimum_trade_notional
        )

    # ==================================================================
    # GENERATE INSTRUCTION
    # ==================================================================

    def generate_instruction(
        self,
        ticker: str,
        current_position: float,
        target_position: float,
        execution_price: Optional[float] = None,
    ) -> Optional[TradeInstruction]:
        """
        Generate a TradeInstruction for one asset.

        Returns None when no trade is required or when the trade
        falls below configured thresholds.
        """

        ticker = self._validate_ticker(
            ticker
        )

        current = self._validate_position(
            current_position,
            "current_position",
        )

        target = self._validate_position(
            target_position,
            "target_position",
        )

        if execution_price is not None:

            execution_price = float(
                execution_price
            )

            if execution_price <= 0:
                raise ValueError(
                    "execution_price must be positive."
                )

        delta = self.position_delta(
            current,
            target,
        )

        side = self.determine_side(
            delta
        )

        if side is None:
            return None

        quantity = self.trade_quantity(
            delta
        )

        if not self.passes_quantity_threshold(
            quantity
        ):
            return None

        if not self.passes_notional_threshold(
            quantity,
            execution_price,
        ):
            return None

        return TradeInstruction(
            ticker=ticker,
            side=side,
            quantity=quantity,
            current_position=current,
            target_position=target,
            delta=delta,
            execution_price=execution_price,
        )

    # ==================================================================
    # ORDER ID
    # ==================================================================

    def _next_order_id(
        self,
        ticker: str,
        index: int,
    ) -> str:
        """
        Generate a deterministic order ID.

        The generation counter separates independent generation
        batches while the index preserves deterministic ordering
        inside a batch.
        """

        return (
            f"{self.order_id_prefix}-"
            f"{self._generation_count:08d}-"
            f"{index:04d}-"
            f"{ticker}"
        )

    # ==================================================================
    # GENERATE ORDER
    # ==================================================================

    def generate_order(
        self,
        instruction: TradeInstruction,
        index: int = 1,
    ) -> Order:
        """
        Convert a TradeInstruction into an Order.
        """

        if not isinstance(
            instruction,
            TradeInstruction,
        ):
            raise TypeError(
                "instruction must be a TradeInstruction."
            )

        if index <= 0:
            raise ValueError(
                "index must be positive."
            )

        order_id = self._next_order_id(
            instruction.ticker,
            index,
        )

        return Order(
            order_id=order_id,
            ticker=instruction.ticker,
            side=instruction.side,
            quantity=instruction.quantity,
            order_type=self.order_type,
            time_in_force=self.time_in_force,
        )

    # ==================================================================
    # GENERATE ORDERS
    # ==================================================================

    def generate_orders(
        self,
        current_positions: Mapping[str, float],
        target_positions: Mapping[str, float],
        execution_prices: Optional[
            Mapping[str, float]
        ] = None,
    ) -> list[Order]:
        """
        Generate orders for a complete portfolio reconciliation.

        Assets appearing only in target_positions are treated as
        current position zero.

        Assets appearing only in current_positions are treated as
        target position zero.

        The resulting ticker order is deterministic.
        """

        if not isinstance(
            current_positions,
            Mapping,
        ):
            raise TypeError(
                "current_positions must be a mapping."
            )

        if not isinstance(
            target_positions,
            Mapping,
        ):
            raise TypeError(
                "target_positions must be a mapping."
            )

        if execution_prices is not None and not isinstance(
            execution_prices,
            Mapping,
        ):
            raise TypeError(
                "execution_prices must be a mapping."
            )

        self._generation_count += 1

        self.last_instructions = []
        self.last_orders = []

        tickers = sorted(
            {
                self._validate_ticker(
                    ticker
                )
                for ticker in (
                    set(current_positions)
                    | set(target_positions)
                )
            }
        )

        for index, ticker in enumerate(
            tickers,
            start=1,
        ):

            current = current_positions.get(
                ticker,
                0.0,
            )

            target = target_positions.get(
                ticker,
                0.0,
            )

            execution_price = None

            if execution_prices is not None:
                execution_price = execution_prices.get(
                    ticker
                )

            instruction = self.generate_instruction(
                ticker=ticker,
                current_position=current,
                target_position=target,
                execution_price=execution_price,
            )

            if instruction is None:
                continue

            self.last_instructions.append(
                instruction
            )

            order = self.generate_order(
                instruction,
                index=len(
                    self.last_instructions
                ),
            )

            self.last_orders.append(
                order
            )

        return list(
            self.last_orders
        )

    # ==================================================================
    # GENERATE FROM ACCOUNT
    # ==================================================================

    def generate_from_account(
        self,
        account: PortfolioAccount,
        target_positions: Mapping[str, float],
        execution_prices: Optional[
            Mapping[str, float]
        ] = None,
    ) -> list[Order]:
        """
        Generate orders directly from a PortfolioAccount.
        """

        if not isinstance(
            account,
            PortfolioAccount,
        ):
            raise TypeError(
                "account must be a PortfolioAccount."
            )

        current_positions = {
            ticker: float(
                position.shares
            )
            for ticker, position
            in account.positions.items()
        }

        return self.generate_orders(
            current_positions=current_positions,
            target_positions=target_positions,
            execution_prices=execution_prices,
        )

    # ==================================================================
    # RECONCILE
    # ==================================================================

    def reconcile(
        self,
        current_positions: Mapping[str, float],
        target_positions: Mapping[str, float],
    ) -> dict[str, float]:
        """
        Return target minus current position for every asset.

        This method does not generate orders.
        """

        if not isinstance(
            current_positions,
            Mapping,
        ):
            raise TypeError(
                "current_positions must be a mapping."
            )

        if not isinstance(
            target_positions,
            Mapping,
        ):
            raise TypeError(
                "target_positions must be a mapping."
            )

        tickers = sorted(
            {
                self._validate_ticker(
                    ticker
                )
                for ticker in (
                    set(current_positions)
                    | set(target_positions)
                )
            }
        )

        return {
            ticker: self.position_delta(
                current_positions.get(
                    ticker,
                    0.0,
                ),
                target_positions.get(
                    ticker,
                    0.0,
                ),
            )
            for ticker in tickers
        }

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(self) -> dict:
        """
        Return generator state summary.
        """

        buy_quantity = sum(
            instruction.quantity
            for instruction in self.last_instructions
            if instruction.side == self.BUY
        )

        sell_quantity = sum(
            instruction.quantity
            for instruction in self.last_instructions
            if instruction.side == self.SELL
        )

        return {
            "api_version": self.API_VERSION,
            "generated_orders": len(
                self.last_orders
            ),
            "generated_instructions": len(
                self.last_instructions
            ),
            "buy_orders": sum(
                instruction.side == self.BUY
                for instruction in self.last_instructions
            ),
            "sell_orders": sum(
                instruction.side == self.SELL
                for instruction in self.last_instructions
            ),
            "buy_quantity": buy_quantity,
            "sell_quantity": sell_quantity,
            "generation_count": self._generation_count,
            "minimum_trade_quantity":
                self.minimum_trade_quantity,
            "minimum_trade_notional":
                self.minimum_trade_notional,
            "order_type":
                self.order_type,
            "time_in_force":
                self.time_in_force,
        }

    # ==================================================================
    # METADATA
    # ==================================================================

    @property
    def metadata(self) -> dict:
        """
        Return module metadata.
        """

        return {
            "component": "TradeGenerator",
            "api_version": self.API_VERSION,
            "public_methods": list(
                self.PUBLIC_METHODS
            ),
            "summary": self.summary(),
        }

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def health_check(self) -> bool:
        """
        Validate internal generator state.
        """

        if self.API_VERSION != "1.0.0":
            raise RuntimeError(
                "Invalid TradeGenerator API version."
            )

        if self.minimum_trade_quantity < 0:
            raise RuntimeError(
                "Invalid minimum trade quantity."
            )

        if (
            self.minimum_trade_notional is not None
            and self.minimum_trade_notional < 0
        ):
            raise RuntimeError(
                "Invalid minimum trade notional."
            )

        if not self.order_type:
            raise RuntimeError(
                "Order type cannot be empty."
            )

        if not self.time_in_force:
            raise RuntimeError(
                "Time-in-force cannot be empty."
            )

        if not self.order_id_prefix:
            raise RuntimeError(
                "Order ID prefix cannot be empty."
            )

        for instruction in self.last_instructions:

            if instruction.quantity <= 0:
                raise RuntimeError(
                    "Trade instruction quantity must be positive."
                )

            if instruction.side not in (
                self.BUY,
                self.SELL,
            ):
                raise RuntimeError(
                    "Invalid trade instruction side."
                )

        for order in self.last_orders:

            order.validate()

        return True

    # ==================================================================
    # TO DICTIONARY
    # ==================================================================

    def to_dict(self) -> dict:
        """
        Serialize generator state.
        """

        return {
            "api_version": self.API_VERSION,
            "minimum_trade_quantity":
                self.minimum_trade_quantity,
            "minimum_trade_notional":
                self.minimum_trade_notional,
            "order_type":
                self.order_type,
            "time_in_force":
                self.time_in_force,
            "order_id_prefix":
                self.order_id_prefix,
            "generation_count":
                self._generation_count,
            "last_instructions": [
                instruction.to_dict()
                for instruction
                in self.last_instructions
            ],
            "last_orders": [
                order.to_dict()
                for order
                in self.last_orders
            ],
        }

    # ==================================================================
    # FROM DICTIONARY
    # ==================================================================

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> TradeGenerator:
        """
        Restore a TradeGenerator from serialized data.
        """

        if not isinstance(
            data,
            dict,
        ):
            raise TypeError(
                "data must be a dictionary."
            )

        generator = cls(
            minimum_trade_quantity=data.get(
                "minimum_trade_quantity",
                0.0,
            ),
            minimum_trade_notional=data.get(
                "minimum_trade_notional"
            ),
            order_type=data.get(
                "order_type",
                "MARKET",
            ),
            time_in_force=data.get(
                "time_in_force",
                "DAY",
            ),
            order_id_prefix=data.get(
                "order_id_prefix",
                "TRD",
            ),
        )

        generator._generation_count = int(
            data.get(
                "generation_count",
                0,
            )
        )

        generator.last_instructions = [
            TradeInstruction(
                ticker=item["ticker"],
                side=item["side"],
                quantity=float(
                    item["quantity"]
                ),
                current_position=float(
                    item["current_position"]
                ),
                target_position=float(
                    item["target_position"]
                ),
                delta=float(
                    item["delta"]
                ),
                execution_price=item.get(
                    "execution_price"
                ),
            )
            for item
            in data.get(
                "last_instructions",
                [],
            )
        ]

        generator.last_orders = [
            Order.from_dict(
                item
            )
            for item
            in data.get(
                "last_orders",
                [],
            )
        ]

        return generator


# ======================================================================
# REGRESSION TESTS
# ======================================================================


def test_trade_generator():
    """
    Regression tests for TradeGenerator.
    """

    generator = TradeGenerator()

    # ==============================================================
    # BASIC HEALTH
    # ==============================================================

    assert generator.health_check()

    assert (
        generator.API_VERSION
        == "1.0.0"
    )

    # ==============================================================
    # RECONCILIATION
    # ==============================================================

    current = {
        "SPY": 100,
        "QQQ": 50,
        "TLT": 25,
    }

    target = {
        "SPY": 150,
        "QQQ": 20,
        "GLD": 10,
    }

    reconciliation = generator.reconcile(
        current,
        target,
    )

    assert reconciliation["SPY"] == 50
    assert reconciliation["QQQ"] == -30
    assert reconciliation["TLT"] == -25
    assert reconciliation["GLD"] == 10

    # ==============================================================
    # SIDE
    # ==============================================================

    assert (
        generator.determine_side(50)
        == TradeGenerator.BUY
    )

    assert (
        generator.determine_side(-50)
        == TradeGenerator.SELL
    )

    assert (
        generator.determine_side(0)
        is None
    )

    # ==============================================================
    # INSTRUCTION — BUY
    # ==============================================================

    buy_instruction = (
        generator.generate_instruction(
            ticker="SPY",
            current_position=100,
            target_position=150,
        )
    )

    assert buy_instruction is not None

    assert (
        buy_instruction.ticker
        == "SPY"
    )

    assert (
        buy_instruction.side
        == TradeGenerator.BUY
    )

    assert (
        buy_instruction.quantity
        == 50
    )

    assert (
        buy_instruction.delta
        == 50
    )

    # ==============================================================
    # INSTRUCTION — SELL
    # ==============================================================

    sell_instruction = (
        generator.generate_instruction(
            ticker="QQQ",
            current_position=100,
            target_position=40,
        )
    )

    assert sell_instruction is not None

    assert (
        sell_instruction.side
        == TradeGenerator.SELL
    )

    assert (
        sell_instruction.quantity
        == 60
    )

    assert (
        sell_instruction.delta
        == -60
    )

    # ==============================================================
    # NO TRADE
    # ==============================================================

    no_trade = (
        generator.generate_instruction(
            ticker="TLT",
            current_position=100,
            target_position=100,
        )
    )

    assert no_trade is None

    # ==============================================================
    # GENERATE ORDER
    # ==============================================================

    generator._generation_count = 1

    order = generator.generate_order(
        buy_instruction,
        index=1,
    )

    assert isinstance(
        order,
        Order,
    )

    assert (
        order.ticker
        == "SPY"
    )

    assert (
        order.side
        == "BUY"
    )

    assert (
        order.quantity
        == 50
    )

    assert (
        order.order_type
        == "MARKET"
    )

    assert (
        order.time_in_force
        == "DAY"
    )

    assert order.order_id.startswith(
        "TRD-"
    )

    # ==============================================================
    # BATCH GENERATION
    # ==============================================================

    orders = generator.generate_orders(
        current_positions={
            "SPY": 100,
            "QQQ": 100,
            "TLT": 50,
        },
        target_positions={
            "SPY": 150,
            "QQQ": 50,
            "TLT": 50,
            "GLD": 25,
        },
    )

    assert len(orders) == 3

    order_map = {
        order.ticker: order
        for order in orders
    }

    assert (
        order_map["SPY"].side
        == "BUY"
    )

    assert (
        order_map["SPY"].quantity
        == 50
    )

    assert (
        order_map["QQQ"].side
        == "SELL"
    )

    assert (
        order_map["QQQ"].quantity
        == 50
    )

    assert (
        order_map["GLD"].side
        == "BUY"
    )

    assert (
        order_map["GLD"].quantity
        == 25
    )

    # ==============================================================
    # THRESHOLD
    # ==============================================================

    threshold_generator = TradeGenerator(
        minimum_trade_quantity=10
    )

    assert (
        threshold_generator.generate_instruction(
            ticker="SPY",
            current_position=100,
            target_position=105,
        )
        is None
    )

    assert (
        threshold_generator.generate_instruction(
            ticker="SPY",
            current_position=100,
            target_position=110,
        )
        is not None
    )

    # ==============================================================
    # NOTIONAL THRESHOLD
    # ==============================================================

    notional_generator = TradeGenerator(
        minimum_trade_notional=10_000
    )

    assert (
        notional_generator.generate_instruction(
            ticker="SPY",
            current_position=100,
            target_position=105,
            execution_price=500,
        )
        is None
    )

    assert (
        notional_generator.generate_instruction(
            ticker="SPY",
            current_position=100,
            target_position=120,
            execution_price=500,
        )
        is not None
    )

    # ==============================================================
    # ACCOUNT INTEGRATION
    # ==============================================================

    account = PortfolioAccount(
        initial_cash=100_000
    )

    account.update_position(
        ticker="SPY",
        shares=100,
        average_cost=450,
    )

    account.update_position(
        ticker="QQQ",
        shares=50,
        average_cost=400,
    )

    account_orders = generator.generate_from_account(
        account,
        target_positions={
            "SPY": 125,
            "QQQ": 25,
            "TLT": 10,
        },
    )

    account_order_map = {
        order.ticker: order
        for order in account_orders
    }

    assert len(
        account_orders
    ) == 3

    assert (
        account_order_map["SPY"].side
        == "BUY"
    )

    assert (
        account_order_map["SPY"].quantity
        == 25
    )

    assert (
        account_order_map["QQQ"].side
        == "SELL"
    )

    assert (
        account_order_map["QQQ"].quantity
        == 25
    )

    assert (
        account_order_map["TLT"].side
        == "BUY"
    )

    assert (
        account_order_map["TLT"].quantity
        == 10
    )

    # ==============================================================
    # NO STATE MUTATION
    # ==============================================================

    assert (
        account.positions["SPY"].shares
        == 100
    )

    assert (
        account.positions["QQQ"].shares
        == 50
    )

    # ==============================================================
    # SERIALIZATION
    # ==============================================================

    exported = generator.to_dict()

    restored = (
        TradeGenerator.from_dict(
            exported
        )
    )

    assert (
        restored.API_VERSION
        == generator.API_VERSION
    )

    assert (
        restored.minimum_trade_quantity
        == generator.minimum_trade_quantity
    )

    assert (
        restored.order_type
        == generator.order_type
    )

    assert (
        restored.time_in_force
        == generator.time_in_force
    )

    assert (
        len(restored.last_orders)
        == len(generator.last_orders)
    )

    # ==============================================================
    # METADATA
    # ==============================================================

    metadata = generator.metadata

    assert (
        metadata["component"]
        == "TradeGenerator"
    )

    assert (
        metadata["api_version"]
        == generator.API_VERSION
    )

    assert (
        "generate_orders"
        in metadata["public_methods"]
    )

    # ==============================================================
    # INVALID INPUT
    # ==============================================================

    try:

        generator.generate_instruction(
            ticker="",
            current_position=0,
            target_position=10,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    try:

        generator.generate_instruction(
            ticker="SPY",
            current_position=0,
            target_position=10,
            execution_price=0,
        )

        raise AssertionError(
            "Expected ValueError"
        )

    except ValueError:
        pass

    # ==============================================================
    # FINAL HEALTH CHECK
    # ==============================================================

    assert generator.health_check()

    print(
        "TradeGenerator Phase III-B.3 tests passed."
    )


# ======================================================================
# MAIN
# ======================================================================


if __name__ == "__main__":
    test_trade_generator()
