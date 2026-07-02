
import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression

from marketdataloader import MarketDataLoader

from rewrite import Regime

import plotly.express as px

# ============================================================
# REGIME COVARIANCE
# ============================================================

class RegimeCovariance:

    def estimate(
        self,
        returns,
        regime
    ):

        covariance = returns.cov()

        if regime == Regime.RECESSION:

            return covariance * 1.5

        if regime == Regime.SLOWDOWN:

            return covariance * 1.2

        return covariance

# ============================================================
# BAYESIAN FORECAST
# ============================================================

class BayesianExpectedReturns:

    def combine(
        self,
        prior,
        signal,
        confidence=0.5
    ):

        posterior = (

            confidence
            * signal

            +

            (1 - confidence)
            * prior
        )

        return posterior
    
# ============================================================
# DYNAMIC FACTOR EXPOSURE
# ============================================================

class DynamicFactorExposure:

    def rolling_beta(
        self,
        asset_returns,
        factor_returns,
        window=252
    ):

        betas = []

        for i in range(
            window,
            len(asset_returns)
        ):

            y = asset_returns.iloc[
                i-window:i
            ]

            X = factor_returns.iloc[
                i-window:i
            ]

            model = LinearRegression()

            model.fit(
                X,
                y
            )

            betas.append(
                model.coef_
            )

        return pd.DataFrame(
            betas
        )
    
# ============================================================
# CONDITIONAL VAR
# ============================================================

class CVaREngine:

    def calculate(
        self,
        returns,
        confidence=0.95
    ):

        var = np.percentile(
            returns,
            (1-confidence)*100
        )

        tail = returns[
            returns <= var
        ]

        return tail.mean()
    
# ============================================================
# DRAWDOWN MODEL
# ============================================================

class DrawdownForecast:

    def forecast(
        self,
        volatility
    ):

        return (
            -2.0
            * volatility
        )
    
# ============================================================
# CORRELATION BREAKDOWN
# ============================================================

class CorrelationMonitor:

    def breakdown(
        self,
        returns,
        threshold=0.30
    ):

        corr = returns.corr()

        avg_corr = (

            corr.values.mean()
        )

        return {

            "average_correlation":
                avg_corr,

            "breakdown":
                avg_corr
                >
                threshold
        }
    
# ============================================================
# FACTOR ATTRIBUTION
# ============================================================

class FactorAttribution:

    def attribute(
        self,
        betas,
        factor_returns
    ):

        return (
            betas
            *
            factor_returns
        )
    
# ============================================================
# BRINSON
# ============================================================

class BrinsonAttribution:

    def allocation_effect(
        self,
        portfolio_weight,
        benchmark_weight,
        benchmark_return
    ):

        return (

            portfolio_weight
            -
            benchmark_weight

        ) * benchmark_return

    def selection_effect(
        self,
        benchmark_weight,
        portfolio_return,
        benchmark_return
    ):

        return (

            benchmark_weight

            *

            (
                portfolio_return
                -
                benchmark_return
            )
        )
    
class AdvancedVisualization:

    def rolling_sharpe(
        self,
        returns,
        window=126
    ):

        rolling = (

            returns.rolling(window)
            .mean()

            /

            returns.rolling(window)
            .std()

        ) * np.sqrt(252)

        return px.line(
            rolling,
            title="Rolling Sharpe"
        )

    def drawdown_chart(
        self,
        returns
    ):

        equity = (
            1 + returns
        ).cumprod()

        drawdown = (

            equity
            /
            equity.cummax()

        ) - 1

        return px.line(
            drawdown,
            title="Drawdown"
        )
    
def test_cvar():

    loader = MarketDataLoader(
        ["SPY"],
        "1y"
    )

    returns = (
        loader
        .load_returns()["SPY"]
    )

    cvar = (
        CVaREngine()
        .calculate(
            returns
        )
    )

    assert np.isfinite(cvar)

    assert cvar < 0

    print(
        "CVaR test passed"
    )