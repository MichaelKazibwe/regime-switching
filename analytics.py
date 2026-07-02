import numpy as np

from core_constants import TRADING_DAYS

# ============================================================
# PERFORMANCE ANALYTICS
# ============================================================

class PerformanceAnalytics:

    def annual_return(
        self,
        returns
    ):

        compounded = (
            (1 + returns)
            .prod()
        )

        years = (
            len(returns)
            / TRADING_DAYS
        )

        return (
            compounded ** (1 / years)
            - 1
        )

    def annual_volatility(
        self,
        returns
    ):

        return (

            returns.std()

            *

            np.sqrt(
                TRADING_DAYS
            )

        )

    def sharpe_ratio(
        self,
        returns,
        rf=0.02
    ):

        ann_return = (
            self.annual_return(
                returns
            )
        )

        ann_vol = (
            self.annual_volatility(
                returns
            )
        )

        if ann_vol <= 0:

            return 0.0

        return (
            ann_return - rf
        ) / ann_vol

    def sortino_ratio(
        self,
        returns,
        rf=0.02
    ):

        downside = (

            returns[
                returns < 0
            ]

        )

        downside_vol = (

            downside.std()

            *

            np.sqrt(
                TRADING_DAYS
            )

        )

        if downside_vol <= 0:

            return 0.0

        return (
            self.annual_return(
                returns
            )
            -
            rf
        ) / downside_vol

    def max_drawdown(
        self,
        returns
    ):

        equity = (
            (1 + returns)
            .cumprod()
        )

        peak = (
            equity.cummax()
        )

        drawdown = (
            equity / peak
            - 1
        )

        return drawdown.min()

    def calmar_ratio(
        self,
        returns
    ):

        mdd = abs(
            self.max_drawdown(
                returns
            )
        )

        if mdd <= 0:

            return 0.0

        return (
            self.annual_return(
                returns
            )
            /
            mdd
        )

    def summary(
        self,
        returns
    ):

        return {

            "annual_return":
                self.annual_return(
                    returns
                ),

            "annual_vol":
                self.annual_volatility(
                    returns
                ),

            "sharpe":
                self.sharpe_ratio(
                    returns
                ),

            "sortino":
                self.sortino_ratio(
                    returns
                ),

            "max_drawdown":
                self.max_drawdown(
                    returns
                ),

            "calmar":
                self.calmar_ratio(
                    returns
                )

        }

