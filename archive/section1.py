
from marketdataloader import MarketDataLoader

# ============================================================
# ENVIRONMENT VALIDATION
# ============================================================

from core_constants import settings

class EnvironmentValidator:

    def validate(self):

        required = {

            "fred_api_key":
                settings.fred_api_key,

            "redis_host":
                settings.redis_host
        }

        optional = {

            "database_url":
                settings.database_url,

            "alpaca_key":
                settings.alpaca_key
        }

        report = {}

        for key, value in required.items():

            report[key] = (
                value is not None
            )

        for key, value in optional.items():

            report[key] = (
                value is not None
            )

        return report    
# ============================================================
# VAR ENGINE
# ============================================================

import numpy as np

class VaREngine:

    def historical_var(
        self,
        returns,
        confidence=0.95
    ):

        percentile = (
            (1 - confidence)
            * 100
        )

        return np.percentile(
            returns,
            percentile
        )

    def expected_shortfall(
        self,
        returns,
        confidence=0.95
    ):

        var = self.historical_var(
            returns,
            confidence
        )

        tail = returns[
            returns <= var
        ]

        return tail.mean()
    
# ============================================================
# EXPOSURE MONITOR
# ============================================================

class ExposureMonitor:

    def gross_exposure(
        self,
        weights
    ):

        return np.sum(
            np.abs(weights)
        )

    def net_exposure(
        self,
        weights
    ):

        return np.sum(
            weights
        )

    def leverage(
        self,
        weights
    ):

        return self.gross_exposure(
            weights
        )
    
# ============================================================
# STRATEGY MANAGER
# ============================================================

class StrategyManager:

    def __init__(self):

        self.strategies = {}

    def register(
        self,
        name,
        strategy
    ):

        self.strategies[
            name
        ] = strategy

    def signals(
        self,
        data
    ):

        results = {}

        for name, strategy in (
            self.strategies.items()
        ):

            results[name] = (
                strategy.generate(
                    data
                )
            )

        return results
    
# ============================================================
# FUND
# ============================================================

class Fund:

    def __init__(
        self,
        name,
        capital
    ):

        self.name = name

        self.capital = capital

        self.positions = {}

    def nav(
        self,
        prices
    ):

        total = self.capital

        for symbol, qty in (
            self.positions.items()
        ):

            if symbol in prices:

                total += (
                    qty
                    * prices[symbol]
                )

        return total
    
# ============================================================
# FUND REGISTRY
# ============================================================

class FundRegistry:

    def __init__(self):

        self.funds = {}

    def add_fund(
        self,
        fund
    ):

        self.funds[
            fund.name
        ] = fund

    def get(
        self,
        name
    ):

        return self.funds[
            name
        ]
    
from apscheduler.schedulers.background import (
    BackgroundScheduler
)

# ============================================================
# SCHEDULER
# ============================================================

class PortfolioScheduler:

    def __init__(self):

        self.scheduler = (
            BackgroundScheduler()
        )

    def start(self):

        self.scheduler.start()

    def add_daily_job(
        self,
        func,
        hour=16
    ):

        self.scheduler.add_job(

            func,

            "cron",

            hour=hour
        )

# ============================================================
# HEALTH CHECK
# ============================================================

from section4 import PerformanceAnalytics

from prometheus_client import Gauge

class PortfolioHealth:

    def status(
        self,
        returns
    ):

        analytics = (
            PerformanceAnalytics()
        )

        metrics = (
            analytics.metrics(
                returns
            )
        )

        return {

            "sharpe":
                metrics["sharpe"],

            "drawdown":
                metrics["max_drawdown"],

            "healthy":
                metrics[
                    "max_drawdown"
                ] > -0.20
        }
    
portfolio_sharpe_metric = Gauge(
    "portfolio_sharpe",
    "Portfolio Sharpe"
)

portfolio_drawdown_metric = Gauge(
    "portfolio_drawdown",
    "Portfolio Drawdown"
)

# ============================================================
# DOCKERFILE GENERATOR
# ============================================================

class DockerGenerator:

    def dockerfile(self):

        return """
FROM python:3.12

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt

CMD ["streamlit","run","rewrite.py"]
"""

# ============================================================
# DOCKER COMPOSE
# ============================================================

class ComposeGenerator:

    def compose(self):

        return """
services:

  app:
    build: .

  redis:
    image: redis

  postgres:
    image: postgres
"""

# ============================================================
# GITHUB ACTIONS
# ============================================================

class GithubActionsGenerator:

    def workflow(self):

        return """
name: tests

on:
  push:

jobs:

  test:

    runs-on:
      ubuntu-latest

    steps:

      - uses: actions/checkout@v4

      - name: install

        run: |
          pip install -r requirements.txt

      - name: test

        run: |
          pytest
"""

def test_var():

    loader = MarketDataLoader(
        ["SPY"],
        "1y"
    )

    returns = (
    loader
    .load_returns()["SPY"]
)

    engine = VaREngine()

    var = (
        engine
        .historical_var(
            returns
        )
    )

    es = (
        engine
        .expected_shortfall(
            returns
        )
    )

    assert np.isfinite(var)

    assert np.isfinite(es)

    assert var < 0

    assert es < var

    print(
        "VaR test passed"
    )
    
