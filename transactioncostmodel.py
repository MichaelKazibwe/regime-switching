"""
===============================================================
TRANSACTION COST MODEL

Institutional Transaction Cost Engine

Estimates trading costs including commissions and slippage.

===============================================================
"""

from __future__ import annotations

from trade import Trade

import numpy as np
import pandas as pd

from basecomponent import BaseObject
from tradeanalytics import TradeAnalytics

# ============================================================
# TRANSACTION COST MODEL
# ============================================================

class TransactionCostModel(BaseObject):

    """
    Institutional transaction cost model.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "estimate",

        "commission_cost",

        "slippage_cost",

        "total_cost",

        "summary",

        "metadata"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(
        self,
        commission_rate=0.0005,
        slippage_rate=0.0010
    ):

        super().__init__()

        self.commission_rate = float(
            commission_rate
        )

        self.slippage_rate = float(
            slippage_rate
        )

        self.last_cost = None

        self.last_trade_value = None

    # ========================================================
    # VALIDATION
    # ========================================================

    def _validate_trades(
        self,
        trades: list[Trade]
    ):

        if not isinstance(
            trades,
            list
        ):

            raise TypeError(

                "Trades must be a list of Trade objects."

            )

        if not trades:

            raise ValueError(

                "Trades cannot be empty."

            )

        for trade in trades:

            if not isinstance(
                trade,
                Trade
            ):

                raise TypeError(

                    "All items must be Trade objects."

                )

            trade.validate()    
    # ========================================================
    # COMMISSION
    # ========================================================

    def commission_cost(
        self,
        trades: list[Trade]
    ) -> float:

        """
        Estimate total commissions for a list of trades.
        """

        self._validate_trades(

            trades

        )

        traded = sum(

            trade.trade_value

            for trade in trades

        )

        self.last_trade_value = traded

        commission = (

            traded

            *

            self.commission_rate

        )

        self.last_cost = commission

        return commission

    # ========================================================
    # SLIPPAGE
    # ========================================================

    def slippage_cost(
    self,
    trades: list[Trade]
) -> float:

        self._validate_trades(
            trades
        )

        analytics = TradeAnalytics()

        traded = analytics.turnover(
                trades
        )

        return (

            traded

            *

            self.slippage_rate

        )

    # ========================================================
    # TOTAL COST
    # ========================================================

    def total_cost(
        self,
        shares: float,
        price: float
    ) -> float:
        """
        Estimate the total transaction cost.
        """

        trade_value = shares * price

        commission, slippage = self.estimate(
            shares,
            price
        )

        total = commission + slippage

        self.last_trade_value = trade_value
        self.last_cost = total

        return total

    # ========================================================
    # ESTIMATE
    # ========================================================

    def estimate(
        self,
        shares: float,
        price: float
    ) -> tuple[float, float]:
        """
        Estimate commission and slippage for a trade.

        Returns
        -------
        (commission, slippage)
        """

        # ========================================================
        # INPUT VALIDATION
        # ========================================================

        if not isinstance(shares, (int, float)):
            raise TypeError(
                "shares must be numeric."
            )

        if not isinstance(price, (int, float)):
            raise TypeError(
                "price must be numeric."
            )

        if shares < 0:
            raise ValueError(
                "shares cannot be negative."
            )

        if price < 0:
            raise ValueError(
                "price cannot be negative."
            )

        # ========================================================
        # CALCULATIONS
        # ========================================================

        trade_value = (
            shares
            * price
        )

        commission = (
            trade_value
            * self.commission_rate
        )

        slippage = (
            trade_value
            * self.slippage_rate
        )

        return (
            commission,
            slippage
        )
    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ) -> dict:

        return {

            "commission_rate":
                self.commission_rate,

            "slippage_rate":
                self.slippage_rate,

            "last_trade_value":
                self.last_trade_value,

            "last_cost":
                self.last_cost

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
    # TO DICTIONARY
    # ========================================================

    def to_dict(
        self
    ) -> dict:

        return {

            "metadata":
                self.metadata,

            "commission_rate":
                self.commission_rate,

            "slippage_rate":
                self.slippage_rate,

            "last_trade_value":
                self.last_trade_value,

            "last_cost":
                self.last_cost

        }

    # ========================================================
    # FROM DICTIONARY
    # ========================================================

    @classmethod
    def from_dict(
        cls,
        data: dict
    ) -> "TransactionCostModel":

        obj = cls(

            commission_rate=data.get(
                "commission_rate",
                0.0005
            ),

            slippage_rate=data.get(
                "slippage_rate",
                0.0010
            )

        )

        obj.last_trade_value = data.get(
            "last_trade_value"
        )

        obj.last_cost = data.get(
            "last_cost"
        )

        return obj
    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ):

        if self.commission_rate < 0:

            raise RuntimeError(

                "Negative commission."

            )

        if self.slippage_rate < 0:

            raise RuntimeError(

                "Negative slippage."

            )

        return True
    
# ============================================================
# REGRESSION TESTS
# ============================================================


def test_transaction_cost_model():

    trades = [

    Trade(
        ticker="SPY",
        shares=20,
        price=500.0,
        side="BUY"
    ),

    Trade(
        ticker="QQQ",
        shares=10,
        price=500.0,
        side="SELL"
    ),

    Trade(
        ticker="TLT",
        shares=40,
        price=500.0,
        side="BUY"
    )

]

    model = TransactionCostModel(

        commission_rate=0.0005,

        slippage_rate=0.0010

    )

    # ========================================================
    # COMMISSION
    # ========================================================

    commission = model.commission_cost(

        trades

    )

    expected_commission = (

        35000.0

        *

        0.0005

    )

    assert np.isclose(

        commission,

        expected_commission

    )

    # ========================================================
    # SLIPPAGE
    # ========================================================

    slippage = model.slippage_cost(

        trades

    )

    expected_slippage = (

        35000.0

        *

        0.0010

    )

    assert np.isclose(

        slippage,

        expected_slippage

    )

    # ========================================================
    # TOTAL COST
    # ========================================================

    total = model.total_cost(

    shares=100,

    price=500.0

)

    expected_total = (

    100

    * 500.0

    * (

        model.commission_rate

        +

        model.slippage_rate

    )

)

    assert np.isclose(

    total,

    expected_total

)

    # ========================================================
    # ESTIMATE
    # ========================================================

    shares = 100

    price = 350.0

    commission, slippage = model.estimate(

        shares,

        price

    )

    expected_commission = (

        shares

        *

        price

        *

        model.commission_rate

    )

    expected_slippage = (

        shares

        *

        price

        *

        model.slippage_rate

    )

    assert np.isclose(

        commission,

        expected_commission

    )

    assert np.isclose(

        slippage,

        expected_slippage

    )

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = model.summary()

    print("\nSummary:", summary)
    print("last_trade_value:", summary["last_trade_value"])
    print("last_cost:", summary["last_cost"])

    assert summary["commission_rate"] == 0.0005

    assert summary["slippage_rate"] == 0.0010

    assert summary["last_trade_value"] == 50000.0

    assert summary["last_cost"] == total

    # ========================================================
    # METADATA
    # ========================================================

    metadata = model.metadata

    assert metadata["version"] == "1.0.0"

    # ========================================================
    # SERIALIZATION
    # ========================================================

    exported = model.to_dict()

    restored = TransactionCostModel.from_dict(

        exported

    )

    assert restored.commission_rate == model.commission_rate

    assert restored.slippage_rate == model.slippage_rate

    # ========================================================
    # HEALTH
    # ========================================================

    assert model.health_check()

    # ========================================================
    # INVALID INPUT
    # ========================================================

    try:

        model.estimate(

            pd.DataFrame(),

            100.0

        )

        raise AssertionError(

            "Expected TypeError"

        )

    except TypeError:

        pass

    # ========================================================
    # API FREEZE
    # ========================================================

    assert TransactionCostModel.API_VERSION == "1.0.0"

    assert tuple(

        TransactionCostModel.PUBLIC_METHODS

    ) == (

        "estimate",

        "commission_cost",

        "slippage_cost",

        "total_cost",

        "summary",

        "metadata"

    )

    print(

        "TransactionCostModel tests passed."

    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_transaction_cost_model()