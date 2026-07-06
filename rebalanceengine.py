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

                )

        }

        return report