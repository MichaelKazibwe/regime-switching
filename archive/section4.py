# from section1 import EnvironmentValidator
# from section1 import test_var
# from section2 import test_cvar
# from rewrite import SessionLocal
# from rewrite import test_market_data
# from rewrite import test_backtest
import numpy as np

from core_constants import settings

import logging

logger = logging.getLogger(__name__)

from core_constants import TRADING_DAYS

SessionLocal = None

# ============================================================
# PERFORMANCE ANALYTICS
# ============================================================

class PerformanceAnalytics:

    def metrics(
        self,
        returns
    ):

        years = (
            len(returns)
            /
            TRADING_DAYS
        )

        cagr = (

            (
                1 +
                returns
            ).prod()

            **

            (
                1 / years
            )

        ) - 1

        volatility = (

            returns.std()

            *

            np.sqrt(
                TRADING_DAYS
            )
        )

        sharpe = (

            cagr
            /
            volatility

            if volatility > 0

            else 0
        )

        max_drawdown = (

            (
                (
                    1 +
                    returns
                )
                .cumprod()
            )

            /

            (
                (
                    1 +
                    returns
                )
                .cumprod()
                .cummax()
            )

            - 1
        ).min()

        return {

            "cagr":
                cagr,

            "volatility":
                volatility,

            "sharpe":
                sharpe,

            "max_drawdown":
                max_drawdown
        }


# ============================================================
# RETRY ENGINE
# ============================================================

import time

class RetryEngine:

    def execute(
        self,
        func,
        retries=3,
        delay=2,
        *args,
        **kwargs
    ):

        last_error = None

        for attempt in range(retries):

            try:

                return func(
                    *args,
                    **kwargs
                )

            except Exception as e:

                last_error = e

                logger.warning(
                    f"Retry {attempt+1}/{retries}: {e}"
                )

                time.sleep(delay)

        raise last_error
    
# ============================================================
# CIRCUIT BREAKER
# ============================================================

class CircuitBreaker:

    def __init__(
        self,
        threshold=5
    ):

        self.threshold = threshold

        self.failures = 0

        self.open = False

    def call(
        self,
        func,
        *args,
        **kwargs
    ):

        if self.open:

            raise RuntimeError(
                "Circuit Open"
            )

        try:

            result = func(
                *args,
                **kwargs
            )

            self.failures = 0

            return result

        except Exception:

            self.failures += 1

            if self.failures >= self.threshold:

                self.open = True

            raise

# ============================================================
# HEALTH CHECK
# ============================================================

class HealthChecker:

    def status(self):

        report = {}

        report["database"] = (
            SessionLocal is not None
        )

        report["redis"] = True

        report["alpaca"] = (
            settings.alpaca_key
            is not None
        )

        report["fred"] = (
            settings.fred_api_key
            is not None
        )

        return report
    
# ============================================================
# POSITION VALIDATOR
# ============================================================

class PositionValidator:

    def validate(
        self,
        positions
    ):

        for symbol, qty in (
            positions.items()
        ):

            if np.isnan(qty):

                raise ValueError(
                    f"{symbol}: NaN quantity"
                )

        return True
    
# ============================================================
# CONSISTENCY CHECK
# ============================================================

class PortfolioConsistency:

    def check(
        self,
        positions,
        prices
    ):

        value = 0

        for symbol, qty in (
            positions.items()
        ):

            if symbol not in prices:

                raise ValueError(
                    f"Missing price {symbol}"
                )

            value += (
                qty
                * prices[symbol]
            )

        return value
    
# ============================================================
# SECRETS
# ============================================================

import os

class SecretsManager:

    def get(
        self,
        key
    ):

        return os.getenv(
            key
        )
    
# ============================================================
# LATENCY
# ============================================================

import time

class LatencyMonitor:

    def measure(
        self,
        func,
        *args,
        **kwargs
    ):

        start = time.time()

        result = func(
            *args,
            **kwargs
        )

        latency = (
            time.time()
            - start
        )

        return {

            "result":
                result,

            "latency":
                latency
        }
    
# ============================================================
# SHUTDOWN
# ============================================================

import signal

class ShutdownManager:

    def __init__(self):

        self.shutdown = False

    def handler(
        self,
        signum,
        frame
    ):

        logger.info(
            "Shutdown requested"
        )

        self.shutdown = True

    def register(self):

        signal.signal(
            signal.SIGINT,
            self.handler
        )

        signal.signal(
            signal.SIGTERM,
            self.handler
        )

# ============================================================
# RECOVERY
# ============================================================

class RecoveryManager:

    def recover_positions(
        self,
        repository
    ):

        logger.info(
            "Recovering positions"
        )

        return repository
    
# ============================================================
# UNIT TESTS
# ============================================================

class TestSuite:

    def run(self):

        from rewrite import (
            test_market_data,
            test_backtest
        )

        from section1 import test_var

        from section2 import test_cvar

        test_market_data()

        test_backtest()

        test_var()

        test_cvar()

        print(
            "All tests completed"
        )
# ============================================================
# DIAGNOSTICS
# ============================================================

class Diagnostics:

    def run(self):

        from section1 import (
            EnvironmentValidator
        )

        print(
            "Environment:"
        )

        print(
            EnvironmentValidator()
            .validate()
        )

# ============================================================
# PAPER TRADING LOCK
# ============================================================

class TradingMode:

    PAPER = "paper"

    LIVE = "live"


class TradingGuard:

    def __init__(
        self,
        mode=TradingMode.PAPER
    ):

        self.mode = mode

    def verify_live_trading(self):

        if self.mode != TradingMode.LIVE:

            raise RuntimeError(
                "Live trading disabled"
            )
        
def test_diagnostics():

    Diagnostics().run()
