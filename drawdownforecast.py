import numpy as np
import pandas as pd

# ============================================================
# DRAWDOWN FORECAST ENGINE
# ============================================================

class DrawdownForecastEngine:

    @staticmethod
    def max_drawdown(
        returns
    ):

        equity = (

            1.0
            +
            pd.Series(
                returns
            )

        ).cumprod()

        peak = (
            equity.cummax()
        )

        drawdown = (

            equity
            /
            peak

            - 1.0

        )

        return float(
            drawdown.min()
        )
    
class RegimeDrawdownSimulator:

    @staticmethod
    def simulate_drawdowns(
        state_paths,
        state_return_map
    ):

        drawdowns = []

        for path in state_paths:

            path_returns = []

            for state in path:

                mu = (
                    state_return_map[
                        state
                    ]
                )

                path_returns.append(

                    np.random.normal(

                        mu,

                        abs(mu)
                        +
                        0.01

                    )

                )

            dd = (

                DrawdownForecastEngine
                .max_drawdown(
                    path_returns
                )

            )

            drawdowns.append(
                dd
            )

        return np.array(
            drawdowns
        )
    
class DrawdownProbabilityAnalytics:

    @staticmethod
    def summary(
        drawdowns
    ):

        return {

            "mean_drawdown":

                drawdowns.mean(),

            "worst_drawdown":

                drawdowns.min(),

            "prob_10pct":

                np.mean(
                    drawdowns <= -0.10
                ),

            "prob_20pct":

                np.mean(
                    drawdowns <= -0.20
                ),

            "prob_30pct":

                np.mean(
                    drawdowns <= -0.30
                )

        }
