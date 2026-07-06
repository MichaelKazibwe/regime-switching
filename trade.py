"""
===============================================================
TRADE

Institutional Trade Object

Represents one executed trade.

===============================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
import uuid


# ============================================================
# TRADE
# ============================================================

@dataclass(frozen=True)
class Trade:

    """
    Executed trade.
    """

    trade_id: str = field(

        default_factory=lambda: str(

            uuid.uuid4()

        )

    )

    ticker: str = ""

    shares: float = 0.0

    price: float = 0.0

    side: str = "BUY"

    commission: float = 0.0

    slippage: float = 0.0

    average_cost: float = 0.0

    broker: str | None = None

    exchange: str | None = None

    currency: str = "USD"

    timestamp: str | None = None

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "validate",

        "summary",

        "to_dict",

        "from_dict",

        "health_check"

    )

    # ========================================================
    # TRADE VALUE
    # ========================================================

    @property
    def trade_value(
        self
    ) -> float:

        return (

            self.shares

            *

            self.price

        )

    # ========================================================
    # TOTAL COST
    # ========================================================

    @property
    def total_cost(
        self
    ) -> float:

        return (

            self.commission

            +

            self.slippage

        )

    # ========================================================
    # NET CASH FLOW
    # ========================================================

    @property
    def net_cash_flow(
        self
    ) -> float:

        if self.side == "BUY":

            return -(

                self.trade_value

                +

                self.total_cost

            )

        if self.side == "SELL":

            return (

                self.trade_value

                -

                self.total_cost

            )

        raise ValueError(

            f"Unsupported trade side: {self.side}"

        )

    # ========================================================
    # VALIDATE
    # ========================================================

    def validate(
        self
    ) -> bool:

        """
        Validate trade integrity.
        """

        if not self.ticker:

            raise ValueError(
                "Ticker cannot be empty."
            )

        if self.shares <= 0:

            raise ValueError(
                "Shares must be positive."
            )

        if self.price <= 0:

            raise ValueError(
                "Price must be positive."
            )

        if self.side not in (

            "BUY",

            "SELL"

        ):

            raise ValueError(

                "Side must be BUY or SELL."

            )

        if self.commission < 0:

            raise ValueError(

                "Commission cannot be negative."

            )

        if self.slippage < 0:

            raise ValueError(

                "Slippage cannot be negative."

            )
        
        if self.trade_value < 0:

            raise ValueError(

                "Trade value cannot be negative."

            )

        if self.total_cost < 0:

            raise ValueError(

                "Total cost cannot be negative."

            )

        
        return True

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ) -> dict:

        """
        Return trade summary.
        """

        return {

            "trade_id":

                self.trade_id,

            "ticker":

                self.ticker,

            "side":

                self.side,

            "shares":

                self.shares,

            "price":

                self.price,

            "trade_value":

                self.trade_value,

            "commission":

                self.commission,

            "slippage":

                self.slippage,

            "total_cost":

                self.total_cost,

            "net_cash_flow":

                self.net_cash_flow,

            "currency":

                self.currency,

            "broker":

                self.broker,

            "exchange":

                self.exchange,

            "timestamp":

                self.timestamp

        }

    # ========================================================
    # TO DICTIONARY
    # ========================================================

    def to_dict(
        self
    ) -> dict:

        """
        Serialize trade.
        """

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
        data: dict
    ) -> "Trade":

        """
        Deserialize trade.
        """

        return cls(

            **data

        )

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ) -> bool:

        """
        Verify trade integrity.
        """

        return self.validate()

# ============================================================
# REGRESSION TESTS
# ============================================================

def test_trade():

    # ========================================================
    # BUY TRADE
    # ========================================================

    trade = Trade(

        ticker="SPY",

        shares=100,

        price=500.0,

        side="BUY",

        commission=5.0,

        slippage=10.0

    )

    assert trade.validate()

    assert trade.health_check()

    assert trade.trade_value == 50000.0

    assert trade.total_cost == 15.0

    assert trade.net_cash_flow == -50015.0

    # ========================================================
    # SELL TRADE
    # ========================================================

    sell = Trade(

        ticker="SPY",

        shares=50,

        price=600.0,

        side="SELL",

        commission=4.0,

        slippage=6.0

    )

    assert sell.trade_value == 30000.0

    assert sell.total_cost == 10.0

    assert sell.net_cash_flow == 29990.0

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = trade.summary()

    assert summary["ticker"] == "SPY"

    assert summary["shares"] == 100

    assert summary["side"] == "BUY"

    assert summary["trade_value"] == 50000.0

    # ========================================================
    # SERIALIZATION
    # ========================================================

    exported = trade.to_dict()

    restored = Trade.from_dict(

        exported

    )

    assert restored.trade_id == trade.trade_id

    assert restored.trade_value == trade.trade_value

    assert restored.side == trade.side

    # ========================================================
    # INVALID SIDE
    # ========================================================

    try:

        Trade(

            ticker="SPY",

            shares=100,

            price=500,

            side="LONG"

        ).validate()

        raise AssertionError(

            "Expected ValueError"

        )

    except ValueError:

        pass

    # ========================================================
    # INVALID SHARES
    # ========================================================

    try:

        Trade(

            ticker="SPY",

            shares=0,

            price=500,

            side="BUY"

        ).validate()

        raise AssertionError(

            "Expected ValueError"

        )

    except ValueError:

        pass

    # ========================================================
    # INVALID PRICE
    # ========================================================

    try:

        Trade(

            ticker="SPY",

            shares=10,

            price=0,

            side="BUY"

        ).validate()

        raise AssertionError(

            "Expected ValueError"

        )

    except ValueError:

        pass

    # ========================================================
    # API FREEZE
    # ========================================================

    assert Trade.API_VERSION == "1.0.0"

    assert tuple(

        Trade.PUBLIC_METHODS

    ) == (

        "validate",

        "summary",

        "to_dict",

        "from_dict",

        "health_check"

    )

    print(

        "Trade tests passed."

    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_trade()