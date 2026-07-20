"""
===============================================================
REBALANCE ENGINE

Institutional Portfolio Rebalancing Engine

Converts target allocations into executable orders.

===============================================================
"""

from __future__ import annotations

from basecomponent import BaseObject

from order import Order
from portfolioaccount import PortfolioAccount
from executionengine import ExecutionEngine
from transactioncostmodel import TransactionCostModel


# ============================================================
# REBALANCE ENGINE
# ============================================================

class RebalanceEngine(BaseObject):

    """
    Portfolio rebalancing engine.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "generate_orders",

        "estimate_cost",

        "rebalance",

        "summary",

        "metadata",

        "health_check"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(
        self,
        execution_engine: ExecutionEngine | None = None,
        transaction_cost_model: TransactionCostModel | None = None
    ):

        super().__init__()

        self.execution_engine = (

            execution_engine

            if execution_engine is not None

            else ExecutionEngine()

        )

        self.transaction_cost_model = (

            transaction_cost_model

            if transaction_cost_model is not None

            else TransactionCostModel()

        )

        self.last_orders = []

        self.last_trades = []

        self.last_report = {}

    # ========================================================
    # GENERATE ORDERS
    # ========================================================

    def generate_orders(
        self,
        account: PortfolioAccount,
        target_weights: dict[str, float],
        prices: dict[str, float]
    ) -> list[Order]:

        """
        Generate orders required to rebalance the portfolio.
        """

        portfolio_value = account.cash

        for position in account.positions.values():

            portfolio_value += (

                position.shares

                *

                prices[position.ticker]

            )

        orders = []

        for ticker, target_weight in target_weights.items():

            price = prices[ticker]

            target_value = (

                portfolio_value

                *

                target_weight

            )

            target_shares = (

                target_value

                /

                price

            )

            current_position = account.positions.get(

                ticker

            )

            current_shares = (

                0.0

                if current_position is None

                else current_position.shares

            )

            difference = (

                target_shares

                -

                current_shares

            )

            if abs(

                difference

            ) < 1e-8:

                continue

            side = (

                "BUY"

                if difference > 0

                else "SELL"

            )

            orders.append(

                Order(

                    ticker=ticker,

                    side=side,

                    quantity=abs(

                        difference

                    )

                )

            )

        self.last_orders = orders

        return orders
    
    # ========================================================
    # ESTIMATE COST
    # ========================================================

    def estimate_cost(
        self,
        orders: list[Order],
        prices: dict[str, float]
    ) -> dict:

        """
        Estimate transaction costs for a list of orders.
        """

        total_commission = 0.0

        total_slippage = 0.0

        total_trade_value = 0.0

        for order in orders:

            execution_price = prices[

                order.ticker

            ]

            trade_value = (

                order.quantity

                *

                execution_price

            )

            commission, slippage = (

                self.transaction_cost_model.estimate(

                    shares=order.quantity,

                    price=execution_price

                )

            )

            total_trade_value += (

                trade_value

            )

            total_commission += (

                commission

            )

            total_slippage += (

                slippage

            )

            average_cost_per_order = (

                0.0

            if not orders

            else (

        total_commission

        +

        total_slippage

    )

    /

    len(

        orders

    )

)
        
        report = {

            "orders":

                len(

                    orders

                ),

            "trade_value":

                total_trade_value,

            "commission":

                total_commission,

            "slippage":

                total_slippage,

            "total_cost":

                (

                    total_commission

                    +

                    total_slippage

                ),
                
            "average_cost_per_order":
             average_cost_per_order

        }

        return report
    
    # ========================================================
    # REBALANCE
    # ========================================================

    def rebalance(
        self,
        account: PortfolioAccount,
        target_weights: dict[str, float],
        prices: dict[str, float],
        execute: bool= True
    ) -> dict:

        """
        Rebalance the portfolio to the target allocation.
        """

        # ====================================================
        # GENERATE ORDERS
        # ====================================================

        orders = self.generate_orders(

            account,

            target_weights,

            prices

        )

        # ====================================================
        # ESTIMATE COST
        # ====================================================

        estimated_cost = self.estimate_cost(

            orders,

            prices

        )

                # ====================================================
        # EXECUTE ORDERS
        # ====================================================

        trades = []

        if execute:

            for order in orders:

                trade = self.execution_engine.execute(

                    order=order,

                    account=account,

                    execution_price=prices[
                        order.ticker
                    ]

                )

                trades.append(

                    trade

                )

        # ====================================================
        # CACHE
        # ====================================================

        self.last_orders = orders

        self.last_trades = trades

        # ====================================================
        # REPORT
        # ====================================================

        report = {

            "orders":

    [

        order.to_dict()

        for order in orders

    ],

                

            "trades":

    [

        trade.to_dict()

        for trade in trades

    ],

                

            "estimated_cost":

                estimated_cost,

            "cash_after":

                account.cash,

            "positions":

                len(

                    account.positions

                ),

            "executions":

    len(

        trades

    ),

"preview_only":

    not execute

        }

        self.last_report = report

        return report
    
    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ) -> dict:

        """
        Return a summary of the most recent rebalance.
        """

        return {

            "orders":

                len(

                    self.last_orders

                ),

            "trades":

                len(

                    self.last_trades

                ),

            "cash":

                self.last_report.get(

                    "cash_after",

                    0.0

                ),

            "estimated_cost":

                self.last_report.get(

                    "estimated_cost",

                    {}

                ).get(

                    "total_cost",

                    0.0

                )

        }

    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(
        self
    ) -> dict:

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
    ) -> bool:

        """
        Verify that all required components are available.
        """

        return (

            self.execution_engine is not None

            and

            self.transaction_cost_model is not None

        )
    
# ============================================================
# REGRESSION TEST
# ============================================================

def test_rebalance_engine():

    from portfolioaccount import PortfolioAccount

    account = PortfolioAccount(

        initial_cash=100000.0

    )

    engine = RebalanceEngine()

    target_weights = {

        "SPY": 0.60,

        "QQQ": 0.40

    }

    prices = {

        "SPY": 500.0,

        "QQQ": 400.0

    }

    report = engine.rebalance(

        account,

        target_weights,

        prices

    )

    assert len(

        report["orders"]

    ) == 2

    assert len(

        report["trades"]

    ) == 2

    assert report["cash_after"] < 100000.0

    summary = engine.summary()

    assert summary["orders"] == 2

    assert summary["trades"] == 2

    assert engine.health_check()

    metadata = engine.metadata

    assert metadata["orders"] == 2

    assert metadata["trades"] == 2

    assert RebalanceEngine.API_VERSION == "1.0.0"

    assert tuple(

        RebalanceEngine.PUBLIC_METHODS

    ) == (

        "generate_orders",

        "estimate_cost",

        "rebalance",

        "summary",

        "metadata",

        "health_check"

    )

    print(

        "RebalanceEngine tests passed."

    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_rebalance_engine()