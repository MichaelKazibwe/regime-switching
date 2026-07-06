"""
===============================================================
TRADE ANALYTICS

Institutional Trade Analytics

Provides analytics for executed trades.

===============================================================
"""

from __future__ import annotations

from trade import Trade

from basecomponent import BaseObject


# ============================================================
# TRADE ANALYTICS
# ============================================================

class TradeAnalytics(BaseObject):

    """
    Analytics for executed trades.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "turnover",

        "gross_buy_value",

        "gross_sell_value",

        "net_traded_value",

        "trade_count",

        "average_trade_size",

        "largest_trade",

        "summary",

        "metadata",

        "health_check"

    )

    # ========================================================
    # VALIDATION
    # ========================================================

    def _validate(
        self,
        trades: list[Trade]
    ):

        if not isinstance(
            trades,
            list
        ):

            raise TypeError(

                "Trades must be a list."

            )

        for trade in trades:

            if not isinstance(
                trade,
                Trade
            ):

                raise TypeError(

                    "All elements must be Trade objects."

                )

    # ========================================================
    # TURNOVER
    # ========================================================

    def turnover(
        self,
        trades: list[Trade]
    ) -> float:

        self._validate(

            trades

        )

        return sum(

            trade.trade_value

            for trade in trades

        )

    # ========================================================
    # GROSS BUY VALUE
    # ========================================================

    def gross_buy_value(
        self,
        trades: list[Trade]
    ) -> float:

        self._validate(

            trades

        )

        return sum(

            trade.trade_value

            for trade in trades

            if trade.side == "BUY"

        )

    # ========================================================
    # GROSS SELL VALUE
    # ========================================================

    def gross_sell_value(
        self,
        trades: list[Trade]
    ) -> float:

        self._validate(

            trades

        )

        return sum(

            trade.trade_value

            for trade in trades

            if trade.side == "SELL"

        )
    
        # ========================================================
    # NET TRADED VALUE
    # ========================================================

    def net_traded_value(
        self,
        trades: list[Trade]
    ) -> float:

        """
        Buy value minus sell value.
        """

        self._validate(

            trades

        )

        return (

            self.gross_buy_value(

                trades

            )

            -

            self.gross_sell_value(

                trades

            )

        )

    # ========================================================
    # TRADE COUNT
    # ========================================================

    def trade_count(
        self,
        trades: list[Trade]
    ) -> int:

        """
        Number of executed trades.
        """

        self._validate(

            trades

        )

        return len(

            trades

        )

    # ========================================================
    # AVERAGE TRADE SIZE
    # ========================================================

    def average_trade_size(
        self,
        trades: list[Trade]
    ) -> float:

        """
        Average traded value.
        """

        self._validate(

            trades

        )

        if not trades:

            return 0.0

        return (

            self.turnover(

                trades

            )

            /

            len(

                trades

            )

        )

    # ========================================================
    # LARGEST TRADE
    # ========================================================

    def largest_trade(
        self,
        trades: list[Trade]
    ) -> Trade | None:

        """
        Largest executed trade.
        """

        self._validate(

            trades

        )

        if not trades:

            return None

        return max(

            trades,

            key=lambda trade: trade.trade_value

        )

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self,
        trades: list[Trade]
    ) -> dict:

        """
        Analytics summary.
        """

        self._validate(

            trades

        )

        largest = self.largest_trade(

            trades

        )

        return {

            "trade_count":

                self.trade_count(

                    trades

                ),

            "turnover":

                self.turnover(

                    trades

                ),

            "gross_buy_value":

                self.gross_buy_value(

                    trades

                ),

            "gross_sell_value":

                self.gross_sell_value(

                    trades

                ),

            "net_traded_value":

                self.net_traded_value(

                    trades

                ),

            "average_trade_size":

                self.average_trade_size(

                    trades

                ),

            "largest_trade":

                None

                if largest is None

                else largest.summary()

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

            {

                "analytics":

                    "trade"

            }

        )

        return metadata

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ) -> bool:

        """
        Verify analytics engine.
        """

        return True
    
# ============================================================
# REGRESSION TESTS
# ============================================================

def test_trade_analytics():

    analytics = TradeAnalytics()

    trades = [

        Trade(

            ticker="SPY",

            shares=100,

            price=500.0,

            side="BUY"

        ),

        Trade(

            ticker="QQQ",

            shares=50,

            price=400.0,

            side="BUY"

        ),

        Trade(

            ticker="TLT",

            shares=20,

            price=100.0,

            side="SELL"

        )

    ]

    assert analytics.trade_count(

        trades

    ) == 3

    assert analytics.turnover(

        trades

    ) == 72000.0

    assert analytics.gross_buy_value(

        trades

    ) == 70000.0

    assert analytics.gross_sell_value(

        trades

    ) == 2000.0

    assert analytics.net_traded_value(

        trades

    ) == 68000.0

    assert analytics.average_trade_size(

        trades

    ) == 24000.0

    largest = analytics.largest_trade(

        trades

    )

    assert largest is not None

    assert largest.ticker == "SPY"

    summary = analytics.summary(

        trades

    )

    assert summary["trade_count"] == 3

    assert analytics.health_check()

    assert TradeAnalytics.API_VERSION == "1.0.0"

    assert tuple(

        TradeAnalytics.PUBLIC_METHODS

    ) == (

        "turnover",

        "gross_buy_value",

        "gross_sell_value",

        "net_traded_value",

        "trade_count",

        "average_trade_size",

        "largest_trade",

        "summary",

        "metadata",

        "health_check"

    )

    print(

        "TradeAnalytics tests passed."

    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_trade_analytics()