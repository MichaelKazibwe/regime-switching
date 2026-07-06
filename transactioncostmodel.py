"""
===============================================================
TRANSACTION COST MODEL

Institutional Transaction Cost Engine

Estimates trading costs including commissions and slippage.

===============================================================
"""

from __future__ import annotations

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
        trades: pd.DataFrame
    ):

        if not isinstance(
            trades,
            pd.DataFrame
        ):

            raise TypeError(
                "Trades must be a pandas DataFrame."
            )

        if "Trade Value" not in trades.columns:

            raise ValueError(
                "Trades must contain 'Trade Value'."
            )

        if trades.empty:

            raise ValueError(
                "Trades are empty."
            )
        
    # ========================================================
    # COMMISSION
    # ========================================================

    def commission_cost(
        self,
        trades: pd.DataFrame
    ):

        self._validate_trades(
            trades
        )

        traded = np.abs(

            trades[
                "Trade Value"
            ]

        ).sum()

        return (

            traded

            *

            self.commission_rate

        )

    # ========================================================
    # SLIPPAGE
    # ========================================================

    def slippage_cost(
        self,
        trades: pd.DataFrame
    ):

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
        Estimate total transaction cost.
        """

        commission, slippage = self.estimate(

            shares,

            price

        )

        return (

            commission

            +

            slippage

        )
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

        trade_value = (

            shares

            *

            price

        )

        commission = (

            trade_value

            *

            self.commission_rate

        )

        slippage = (

            trade_value

            *

            self.slippage_rate

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
    ):

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
    ):

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
    ):

        return {

            "metadata":

                self.metadata,

            "commission_rate":

                self.commission_rate,

            "slippage_rate":

                self.slippage_rate

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

            commission_rate=data.get(

                "commission_rate",

                0.0005

            ),

            slippage_rate=data.get(

                "slippage_rate",

                0.0010

            )

        )
    
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

    trades = pd.DataFrame(

        {

            "Trade Value": [

                10000.0,

                -5000.0,

                20000.0

            ]

        }

    )

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

        trades

    )

    assert np.isclose(

        total,

        expected_commission

        +

        expected_slippage

    )

    # ========================================================
    # ESTIMATE
    # ========================================================

    estimate = model.estimate(

        trades

    )

    assert np.isclose(

        estimate,

        total

    )

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = model.summary()

    assert summary["commission_rate"] == 0.0005

    assert summary["slippage_rate"] == 0.0010

    assert summary["last_trade_value"] == 35000.0

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

            pd.DataFrame()

        )

        raise AssertionError(

            "Expected ValueError"

        )

    except ValueError:

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