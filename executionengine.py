"""
===============================================================
EXECUTION ENGINE

Institutional Execution Engine

Coordinates order execution using the execution domain.

===============================================================
"""

from __future__ import annotations

from typing import List

from basecomponent import BaseObject

from order import Order
from trade import Trade
from portfolioaccount import PortfolioAccount
from transactioncostmodel import TransactionCostModel
from tradeanalytics import TradeAnalytics


# ============================================================
# EXECUTION ENGINE
# ============================================================

class ExecutionEngine(BaseObject):

    """
    Institutional execution engine.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "execute",

        "execute_batch",

        "summary",

        "metadata"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(
        self,
        transaction_cost_model: TransactionCostModel | None = None,
        trade_analytics: TradeAnalytics | None = None
    ):

        super().__init__()

        self.transaction_cost_model = (

            transaction_cost_model

            if transaction_cost_model is not None

            else TransactionCostModel()

        )

        self.trade_analytics = (

            trade_analytics

            if trade_analytics is not None

            else TradeAnalytics()

        )

        self.execution_history: List[Trade] = []

        self.last_trade = None

        self.last_execution = None

    # ========================================================
    # APPLY TRADE
    # ========================================================

    def _apply_trade(
        self,
        account: PortfolioAccount,
        trade: Trade
    ):

        """
        Apply an executed trade to an account.
        """

        # ====================================================
        # POSITION UPDATE
        # ====================================================

        position = account.positions.get(

            trade.ticker

        )

        share_delta = (

            trade.shares

            if trade.side == "BUY"

            else -trade.shares

        )

        if position is None:

            account.update_position(

                ticker=trade.ticker,

                shares=share_delta,

                average_cost=trade.price

            )

        else:

            new_shares = (

                position.shares

                +

                share_delta

            )

            if new_shares < 0:

                raise ValueError(

                    f"Trade would create a negative position in "

                    f"{trade.ticker}."

                )

            account.update_position(

                ticker=trade.ticker,

                shares=new_shares,

                average_cost=trade.price

            )

        # ====================================================
        # CASH UPDATE
        # ====================================================

        account.cash += trade.net_cash_flow

        # ====================================================
        # HISTORY
        # ====================================================

        account.trade_history.append(

            trade

        )

        account.turnover_history.append(

            self.trade_analytics.turnover(

                trade.trade_value

            )

        )

        account.cost_history.append(

            trade.total_cost

        )

        self.execution_history.append(

            trade

        )

        self.last_trade = trade


    # ========================================================
    # EXECUTE
    # ========================================================

    def execute(
        self,
        order: Order,
        account: PortfolioAccount,
        execution_price: float
    ) -> Trade:
        
        commission, slippage = (

        self.transaction_cost_model.estimate(

        shares=order.quantity,

        price=execution_price

    )

)


        # ====================================================
        # VALIDATION
        # ====================================================

        order.validate()

        if execution_price <= 0:

            raise ValueError(

                "Execution price must be positive."

            )

        # ====================================================
        # TRANSACTION COSTS
        # ====================================================

        commission = (

            self.transaction_cost_model.commission_rate

            *

            order.quantity

            *

            execution_price

        )

        slippage = (

            self.transaction_cost_model.slippage_rate

            *

            order.quantity

            *

            execution_price

        )

        # ====================================================
        # CREATE TRADE
        # ====================================================

        trade = Trade(

            ticker=order.ticker,

            shares=order.quantity,

            price=execution_price,

            side=order.side,

            commission=commission,

            slippage=slippage

        )

        # ====================================================
        # APPLY TRADE
        # ====================================================

        self._apply_trade(

            account,

            trade

        )

        # ====================================================
        # UPDATE ORDER
        # ====================================================

        order.fill(

            quantity=order.quantity,

            price=execution_price

        )

        # ====================================================
        # CACHE LAST EXECUTION
        # ====================================================

        self.last_execution = {

            "ticker": trade.ticker,

            "side": trade.side,

            "shares": trade.shares,

            "execution_price": execution_price,

            "trade_value": trade.trade_value,

            "commission": trade.commission,

            "slippage": trade.slippage,

            "total_cost": trade.total_cost,

            "net_cash_flow": trade.net_cash_flow,

            "cash_after": account.cash

        }

        return trade
    
    # ========================================================
    # EXECUTE BATCH
    # ========================================================

    def execute_batch(
    self,
    orders: list[tuple[Order, float]],
    account: PortfolioAccount
) -> list[Trade]:

        """
        Execute multiple orders.
        """

        trades = []

        for order, execution_price in orders:

            trades.append(

            self.execute(

                order,

                account,

                execution_price

            )

            )

        return trades

    @property
    def execution_count(self) -> int:

         
        return len(

        self.execution_history

    )
    
    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ):

        return {

    "executions": len(self.execution_history),

    "last_execution": self.last_execution

}
    
    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(
        self
    ):

        metadata = super().metadata

        metadata.update(

            self.summary()

        )

        return metadata
    
    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ):

        if self.last_trade is not None:

         self.last_trade.health_check()

        for trade in self.execution_history:

         trade.health_check()

        return True
    
    # ========================================================
    # TO DICTIONARY
    # ========================================================

    def to_dict(
        self
    ):

        return {

    "execution_history": [

        trade.to_dict()

        for trade in self.execution_history

    ],

    "last_execution":

        self.last_execution

}

    # ========================================================
    # FROM DICTIONARY
    # ========================================================

    @classmethod
    def from_dict(
        cls,
        data
    ):

        engine = cls()

        engine.execution_history = [

    Trade.from_dict(trade_data)

    for trade_data in data.get(

        "execution_history",

        []

    )

]

        if engine.execution_history:

            engine.last_trade = (

                engine.execution_history[-1]

            )

        return engine

# ============================================================
# REGRESSION TESTS
# ============================================================

def test_execution_engine():

    engine = ExecutionEngine()

    account = PortfolioAccount(

        initial_cash=100000.0

    )

    # ========================================================
    # BUY ORDER
    # ========================================================

    buy = Order(

        ticker="SPY",

        side="BUY",

        quantity=100

    )

    trade = engine.execute(

        buy,

        account,

        execution_price=500.0

    )

    assert trade.trade_value == 50000.0

    assert len(engine.execution_history) == 1

    assert len(account.trade_history) == 1

    assert engine.last_trade == trade

    assert engine.execution_count == 1

    assert account.positions["SPY"].shares == 100

    # ========================================================
    # SELL ORDER
    # ========================================================

    sell = Order(

        ticker="SPY",

        side="SELL",

        quantity=40

    )

    engine.execute(

        sell,

        account,

        execution_price=510.0

    )

    assert len(engine.execution_history) == 2

    assert account.positions["SPY"].shares == 60

    assert engine.execution_count == 2

    # ========================================================
    # ORDER FILL
    # ========================================================

    assert buy.filled

    assert buy.filled_quantity == 100

    assert buy.average_fill_price == 500.0

    assert sell.filled

    assert sell.filled_quantity == 50

    assert sell.average_fill_price == 510.0
    
    # ========================================================
    # POSITION
    # ========================================================

    position = account.positions["SPY"]

    assert position.shares == 50

    assert position.average_cost == 510.0
    
    # ========================================================
    # CASH
    # ========================================================

    assert account.cash < 100000.0
    
    # ========================================================
    # BATCH EXECUTION
    # ========================================================

    batch = [

        (

            Order(

                ticker="QQQ",

                side="BUY",

                quantity=10

            ),

            400.0

        ),

        (

            Order(

                ticker="TLT",

                side="BUY",

                quantity=20

            ),

            90.0

        )

    ]

    trades = engine.execute_batch(

        batch,

        account

    )

    assert len(trades) == 2

    assert engine.execution_count == 4
    
    # ========================================================
    # METADATA
    # ========================================================

    metadata = engine.metadata

    assert metadata["executions"] == 4
    
    # ========================================================
    # LAST EXECUTION
    # ========================================================

    assert engine.last_execution is not None

    assert engine.last_execution["ticker"] == "TLT"
    
    # ========================================================
    # SUMMARY
    # ========================================================

    summary = engine.summary()

    assert summary["executions"] == 2

    assert summary["last_execution"]["ticker"] == "SPY"

    # ========================================================
    # SERIALIZATION
    # ========================================================

    exported = engine.to_dict()

    restored = ExecutionEngine.from_dict(

        exported

    )

    assert restored.last_trade is not None

    assert restored.last_execution is not None

    # ========================================================
    # HEALTH
    # ========================================================

    assert engine.health_check()

    assert restored.health_check()

    # ========================================================
    # INVALID PRICE
    # ========================================================

    try:

        engine.execute(

            buy,

            account,

            execution_price=0.0

        )

        raise AssertionError(

            "Expected ValueError"

        )

    except ValueError:

        pass

    # ========================================================
    # API FREEZE
    # ========================================================

    assert ExecutionEngine.API_VERSION == "1.0.0"

    assert tuple(

        ExecutionEngine.PUBLIC_METHODS

    ) == (

        "execute",

        "execute_batch",

        "summary",

        "metadata"

    )

    assert hasattr(engine, "execute")

    assert hasattr(engine, "execute_batch")

    assert hasattr(engine, "summary")
    
    print(

        "ExecutionEngine tests passed."

    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_execution_engine()