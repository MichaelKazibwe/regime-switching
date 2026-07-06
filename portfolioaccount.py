"""
===============================================================
PORTFOLIO ACCOUNT

Institutional Portfolio Account

Represents a live brokerage account.

===============================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pandas as pd
import numpy as np

from basecomponent import BaseObject


# ============================================================
# POSITION
# ============================================================

@dataclass
class Position:

    ticker: str

    shares: float = 0.0

    average_cost: float = 0.0

    market_price: float = 0.0

    trade_id: str | None = None

    broker: str | None = None

    exchange: str | None = None

    currency: str = "USD"

# ============================================================
# PORTFOLIO ACCOUNT
# ============================================================

class PortfolioAccount(BaseObject):

    """
    Institutional brokerage account.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "deposit",

        "withdraw",

        "update_position",

        "portfolio_value",

        "weights",

        "summary",

        "metadata"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(
        self,
        initial_cash: float = 1_000_000.0
    ):

        super().__init__()

        self.cash = float(

            initial_cash

        )

        self.positions: Dict[
            str,
            Position
        ] = {}

        self.trade_history = []

        self.turnover_history = []

        self.cost_history = []

        self.last_prices = None

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ):

        return {

            "cash":

                self.cash,

            "positions":

                len(

                    self.positions

                ),

            "trades":

                len(

                    self.trade_history

                ),

            "turnover_events":

                len(

                    self.turnover_history

                ),

            "cost_events":

                len(

                    self.cost_history

                )

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
    # DEPOSIT
    # ========================================================

    def deposit(
        self,
        amount: float
    ):

        if amount <= 0:

            raise ValueError(
                "Deposit must be positive."
            )

        self.cash += float(
            amount
        )

    # ========================================================
    # WITHDRAW
    # ========================================================

    def withdraw(
        self,
        amount: float
    ):

        if amount <= 0:

            raise ValueError(
                "Withdrawal must be positive."
            )

        if amount > self.cash:

            raise ValueError(
                "Insufficient cash."
            )

        self.cash -= float(
            amount
        )

    # ========================================================
    # UPDATE POSITION
    # ========================================================

    def update_position(
        self,
        ticker: str,
        shares: float,
        average_cost: float = 0.0
    ):

        if ticker not in self.positions:

            self.positions[ticker] = Position(

                ticker=ticker,

                shares=shares,

                average_cost=average_cost

            )

        else:

            self.positions[ticker].shares = shares

            self.positions[ticker].average_cost = average_cost

    # ========================================================
    # POSITION VALUE
    # ========================================================

    def position_value(
        self,
        ticker: str,
        market_price: float
    ):

        if ticker not in self.positions:

            return 0.0

        return (

            self.positions[ticker].shares

            *

            market_price

        )
    
    # ========================================================
    # PORTFOLIO VALUE
    # ========================================================

    def portfolio_value(
        self,
        prices: pd.Series
    ):

        self.last_prices = prices.copy()

        total = self.cash

        for ticker, position in self.positions.items():

            if ticker in prices.index:

                total += (

                    position.shares

                    *

                    float(

                        prices[ticker]

                    )

                )

        return float(
            total
        )
    
    # ========================================================
    # WEIGHTS
    # ========================================================

    def weights(
        self,
        prices: pd.Series
    ):

        total = self.portfolio_value(
            prices
        )

        if total == 0:

            return pd.Series(
                dtype=float
            )

        weights = {}

        for ticker, position in self.positions.items():

            if ticker in prices.index:

                weights[ticker] = (

                    position.shares

                    *

                    float(

                        prices[ticker]

                    )

                ) / total

        return pd.Series(
            weights,
            dtype=float
        )
    
    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ):

        if self.cash < 0:

            raise RuntimeError(
                "Negative cash balance."
            )

        for ticker, position in self.positions.items():

            if position.shares < 0:

                raise RuntimeError(

                    f"{ticker}: negative shares."

                )

            if position.average_cost < 0:

                raise RuntimeError(

                    f"{ticker}: negative average cost."

                )

        return True
    
    # ========================================================
    # TO DICTIONARY
    # ========================================================

    def to_dict(
        self
    ):

        return {

            "cash":

                self.cash,

            "positions": {

                ticker: {

                    "ticker":

                        position.ticker,

                    "shares":

                        position.shares,

                    "average_cost":

                        position.average_cost,

                    "market_price":

                        position.market_price

                }

                for ticker, position

                in self.positions.items()

            },

            "trade_history":

                list(

                    self.trade_history

                ),

            "turnover_history":

                list(

                    self.turnover_history

                ),

            "cost_history":

                list(

                    self.cost_history

                )

        }

    # ========================================================
    # FROM DICTIONARY
    # ========================================================

    @classmethod
    def from_dict(
        cls,
        data
    ):

        account = cls(

            initial_cash=data.get(

                "cash",

                0.0

            )

        )

        for ticker, values in data.get(

            "positions",

            {}

        ).items():

            account.positions[ticker] = Position(

                ticker=values["ticker"],

                shares=values["shares"],

                average_cost=values["average_cost"],

                market_price=values.get(

                    "market_price",

                    0.0

                )

            )

        account.trade_history = list(

            data.get(

                "trade_history",

                []

            )

        )

        account.turnover_history = list(

            data.get(

                "turnover_history",

                []

            )

        )

        account.cost_history = list(

            data.get(

                "cost_history",

                []

            )

        )

        return account
    
# ============================================================
# REGRESSION TESTS
# ============================================================

def test_portfolio_account():

    account = PortfolioAccount(

        initial_cash=100000.0

    )

    # ========================================================
    # CASH
    # ========================================================

    assert account.cash == 100000.0

    account.deposit(

        5000.0

    )

    assert account.cash == 105000.0

    account.withdraw(

        5000.0

    )

    assert account.cash == 100000.0

    # ========================================================
    # POSITION
    # ========================================================

    account.update_position(

        "SPY",

        shares=100,

        average_cost=500

    )

    assert "SPY" in account.positions

    assert account.positions["SPY"].shares == 100

    assert account.positions["SPY"].average_cost == 500

    # ========================================================
    # PORTFOLIO VALUE
    # ========================================================

    prices = pd.Series(

        {

            "SPY": 550.0

        }

    )

    value = account.portfolio_value(

        prices

    )

    assert value == (

        100000.0

        +

        100

        *

        550.0

    )

    # ========================================================
    # WEIGHTS
    # ========================================================

    weights = account.weights(

        prices

    )

    assert "SPY" in weights.index

    assert np.isclose(

        weights.sum(),

        (

            55000.0

            /

            value

        )

    )

    # ========================================================
    # SUMMARY
    # ========================================================

    summary = account.summary()

    assert summary["positions"] == 1

    # ========================================================
    # METADATA
    # ========================================================

    metadata = account.metadata

    assert metadata["version"] == "1.0.0"

    # ========================================================
    # SERIALIZATION
    # ========================================================

    exported = account.to_dict()

    restored = PortfolioAccount.from_dict(

        exported

    )

    assert restored.cash == account.cash

    assert restored.positions["SPY"].shares == 100

    # ========================================================
    # HEALTH
    # ========================================================

    assert account.health_check()

    # ========================================================
    # INVALID WITHDRAWAL
    # ========================================================

    try:

        account.withdraw(

            1e9

        )

        raise AssertionError(

            "Expected ValueError"

        )

    except ValueError:

        pass

    # ========================================================
    # API FREEZE
    # ========================================================

    assert PortfolioAccount.API_VERSION == "1.0.0"

    assert tuple(

        PortfolioAccount.PUBLIC_METHODS

    ) == (

        "deposit",

        "withdraw",

        "update_position",

        "portfolio_value",

        "weights",

        "summary",

        "metadata"

    )

    print(

        "PortfolioAccount tests passed."

    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    test_portfolio_account()