import numpy as np

# ============================================================
# FORWARD RISK METRICS
# ============================================================

class ForwardRiskMetrics:

    @staticmethod
    def summarize(

        terminal_returns

    ):

        expected_return = (

            terminal_returns.mean()

        )

        volatility = (

            terminal_returns.std()

        )

        var95 = np.percentile(

            terminal_returns,

            5

        )

        cvar95 = (

            terminal_returns[

                terminal_returns <= var95

            ].mean()

        )

        probability_of_loss = (

            terminal_returns < 0

        ).mean()

        downside = (

            terminal_returns[

                terminal_returns < 0

            ]

        )

        if len(downside) > 1:

            downside_volatility = (

                downside.std()

            )

        else:

            downside_volatility = np.nan

        if volatility > 0:

            sharpe = (

                expected_return

                /

                volatility

            )

        else:

            sharpe = np.nan

        if (

            np.isfinite(

                downside_volatility

            )

            and

            downside_volatility > 0

        ):

            sortino = (

                expected_return

                /

                downside_volatility

            )

        else:

            sortino = np.nan

        gains = (

            terminal_returns[

                terminal_returns > 0

            ].sum()

        )

        losses = abs(

            terminal_returns[

                terminal_returns < 0

            ].sum()

        )

        if losses > 0:

            omega = (

                gains

                /

                losses

            )

        else:

            omega = np.inf

        return {

            "expected_return":

                expected_return,

            "volatility":

                volatility,

            "best_case":

                terminal_returns.max(),

            "worst_case":

                terminal_returns.min(),

            "VaR95":

                var95,

            "CVaR95":

                cvar95,

            "probability_of_loss":

                probability_of_loss,

            "sharpe":

                sharpe,

            "sortino":

                sortino,

            "omega":

                omega

        }