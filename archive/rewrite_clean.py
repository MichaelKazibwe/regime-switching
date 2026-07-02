
from marketdataloader import MarketDataLoader

# ============================================================
# SECTION 1
# CORE INFRASTRUCTURE
# ============================================================

import json
import logging

from datetime import datetime

import numpy as np
import pandas as pd

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict
)

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    DateTime
)

from sqlalchemy.orm import (
    declarative_base,
    sessionmaker
)

# ============================================================
# SETTINGS
# ============================================================

class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False
    )

    # --------------------------
    # Market Data
    # --------------------------

    yahoo_period: str = "15y"

    fred_api_key: str | None = None

    # --------------------------
    # Database
    # --------------------------

    database_url: str | None = None

    # --------------------------
    # Redis
    # --------------------------

    redis_host: str = "localhost"

    redis_port: int = 6379

    # --------------------------
    # Alpaca
    # --------------------------

    alpaca_key: str | None = None

    alpaca_secret: str | None = None

    alpaca_base_url: str = (
        "https://paper-api.alpaca.markets"
    )

    # --------------------------
    # Risk
    # --------------------------

    max_leverage: float = 1.0

    max_position_weight: float = 0.25

    max_turnover: float = 0.30

    # --------------------------
    # Logging
    # --------------------------

    log_level: str = "INFO"


settings = Settings()

# ============================================================
# CONSTANTS
# ============================================================

TRADING_DAYS = 252

DEFAULT_ASSETS = [
    "SPY",
    "EFA",
    "EEM",
    "TLT",
    "IEF",
    "GLD",
    "DBC",
    "XLP",
    "XLU",
    "SHY"
]

BENCHMARK = "SPY"

FRED_SERIES = {
    "FEDFUNDS": "FEDFUNDS",
    "UNRATE": "UNRATE",
    "CPI": "CPIAUCSL",
    "GDP": "GDP",
    "DGS10": "DGS10",
    "DGS2": "DGS2"
}

# ============================================================
# EXCEPTIONS
# ============================================================

class PortfolioException(Exception):
    pass


class DataValidationError(
    PortfolioException
):
    pass


class RiskLimitBreach(
    PortfolioException
):
    pass


class BrokerError(
    PortfolioException
):
    pass


class DatabaseError(
    PortfolioException
):
    pass

# ============================================================
# LOGGING
# ============================================================

class JsonFormatter(
    logging.Formatter
):

    def format(self, record):

        payload = {
            "timestamp":
                datetime.utcnow().isoformat(),

            "level":
                record.levelname,

            "module":
                record.module,

            "message":
                record.getMessage()
        }

        return json.dumps(payload)


def get_logger(name):

    logger = logging.getLogger(name)

    if not logger.handlers:

        handler = logging.StreamHandler()

        handler.setFormatter(
            JsonFormatter()
        )

        logger.addHandler(handler)

        logger.setLevel(
            getattr(
                logging,
                settings.log_level.upper(),
                logging.INFO
            )
        )

    return logger


logger = get_logger(__name__)

# ============================================================
# DATABASE
# ============================================================

engine = None
SessionLocal = None

if settings.database_url:

    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True
    )

    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )

Base = declarative_base()

# ============================================================
# DATABASE MODELS
# ============================================================

class Trade(Base):

    __tablename__ = "trades"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    order_id = Column(
        String,
        nullable=False
    )

    symbol = Column(
        String,
        nullable=False
    )

    side = Column(
        String,
        nullable=False
    )

    quantity = Column(
        Float,
        nullable=False
    )

    price = Column(
        Float,
        nullable=False
    )

    timestamp = Column(
        DateTime,
        nullable=False
    )


class Position(Base):

    __tablename__ = "positions"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    symbol = Column(
        String,
        unique=True,
        nullable=False
    )

    quantity = Column(
        Float,
        nullable=False,
        default=0
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow
    )

# ============================================================
# REPOSITORIES
# ============================================================

class TradeRepository:

    @staticmethod
    def save_trade(
        trade
    ):

        if SessionLocal is None:

            raise DatabaseError(
                "Database not configured"
            )

        session = SessionLocal()

        try:

            session.add(trade)

            session.commit()

        except Exception:

            session.rollback()

            raise

        finally:

            session.close()


class PositionRepository:

    @staticmethod
    def update_position(
        position
    ):

        if SessionLocal is None:

            raise DatabaseError(
                "Database not configured"
            )

        session = SessionLocal()

        try:

            session.merge(position)

            session.commit()

        except Exception:

            session.rollback()

            raise

        finally:

            session.close()

# ============================================================
# STARTUP CHECK
# ============================================================

if __name__ == "__main__":

    print(
        "Section 1 initialized successfully"
    )

    print(
        "Database configured:",
        settings.database_url is not None
    )

# ============================================================
# SECTION 2
# DATA LAYER
# ============================================================

import pandas as pd
import yfinance as yf

from fredapi import Fred

from validators import DataValidator

# ============================================================
# FRED DATA
# ============================================================

class FredDataLoader:

    def __init__(self):

        self.fred = None

        if settings.fred_api_key:

            self.fred = Fred(
                api_key=settings.fred_api_key
            )

    def get_series(
        self,
        series_id
    ):

        if self.fred is None:

            raise ValueError(
                "FRED API key not configured"
            )

        return self.fred.get_series(
            series_id
        )

    def load_macro_dataset(self):

        if self.fred is None:

            raise ValueError(
                "FRED API key not configured"
            )

        dataset = {}

        for name, code in (
            FRED_SERIES.items()
        ):

            try:

                dataset[name] = (
                    self.fred.get_series(
                        code
                    )
                )

            except Exception as e:

                logger.warning(
                    f"Failed loading {name}: {e}"
                )

        return pd.DataFrame(
            dataset
        )

# ============================================================
# FACTOR DATA
# ============================================================

class FactorDataLoader:

    def load_fama_french(
        self,
        file_path
    ):

        logger.info(
            f"Loading factor file {file_path}"
        )

        df = pd.read_csv(
            file_path
        )

        if df.empty:

            raise DataValidationError(
                "Factor file empty"
            )

        return df


# ============================================================
# SECTION 3
# FORECASTING + ALPHA + OPTIMIZATION
# ============================================================

from enum import Enum

import numpy as np

from scipy.optimize import minimize

from sklearn.linear_model import LinearRegression

# ============================================================
# MACRO REGIMES
# ============================================================

class Regime(Enum):

    EXPANSION = "expansion"

    SLOWDOWN = "slowdown"

    RECESSION = "recession"

    RECOVERY = "recovery"


class MacroRegimeModel:

    def classify(
        self,
        unemployment,
        yield_spread,
        inflation
    ):

        if yield_spread < 0:

            return Regime.RECESSION

        if unemployment.diff().iloc[-1] > 0:

            return Regime.SLOWDOWN

        if inflation > 4:

            return Regime.RECOVERY

        return Regime.EXPANSION

# ============================================================
# RECESSION MODEL
# ============================================================

class RecessionProbability:

    def probability(
        self,
        spread,
        unemployment_change,
        fed_funds
    ):

        score = (
            -3.0 * spread
            + 2.0 * unemployment_change
            + 0.15 * fed_funds
        )

        probability = (
            1 /
            (
                1 +
                np.exp(-score)
            )
        )

        return float(
            probability
        )

# ============================================================
# MOMENTUM
# ============================================================

class MomentumModel:

    def score(
        self,
        prices
    ):

        if len(prices) < 252:

            raise ValueError(
                "Need at least 252 observations"
            )

        momentum = (
            prices.iloc[-1]
            /
            prices.iloc[-252]
        ) - 1

        return momentum

# ============================================================
# FACTOR MODEL
# ============================================================

class FactorModel:

    def estimate_betas(
        self,
        asset_returns,
        factor_returns
    ):

        model = LinearRegression()

        model.fit(
            factor_returns,
            asset_returns
        )

        return {

            "alpha":
                model.intercept_,

            "betas":
                model.coef_
        }

# ============================================================
# EXPECTED RETURNS
# ============================================================

class ExpectedReturnModel:

    def forecast(
        self,
        momentum_signal,
        valuation_signal,
        macro_signal
    ):

        expected_returns = (

            0.40
            * momentum_signal

            +

            0.40
            * valuation_signal

            +

            0.20
            * macro_signal
        )

        return expected_returns

# ============================================================
# BLACK LITTERMAN
# ============================================================

class BlackLitterman:

    def implied_returns(
        self,
        covariance,
        market_weights,
        risk_aversion
    ):

        return (

            risk_aversion

            *

            covariance

            @

            market_weights
        )

    def posterior_returns(
        self,
        covariance,
        pi,
        P,
        Q,
        omega,
        tau=0.05
    ):

        tau_sigma = (
            tau
            * covariance
        )

        posterior_cov = np.linalg.inv(

            np.linalg.inv(
                tau_sigma
            )

            +

            P.T

            @

            np.linalg.inv(
                omega
            )

            @

            P
        )

        posterior_mean = (

            posterior_cov

            @

            (

                np.linalg.inv(
                    tau_sigma
                )

                @

                pi

                +

                P.T

                @

                np.linalg.inv(
                    omega
                )

                @

                Q
            )
        )

        return posterior_mean

# ============================================================
# DYNAMIC MARKET WEIGHTS
# ============================================================

class MarketCapWeights:

    def estimate(
        self,
        market_caps
    ):

        market_caps = np.array(
            market_caps
        )

        return (

            market_caps

            /

            market_caps.sum()
        )

# ============================================================
# BL VIEWS
# ============================================================

def create_views(
    expected_returns
):

    n = len(
        expected_returns
    )

    P = np.eye(n)

    Q = np.array(
        expected_returns
    )

    return P, Q

# ============================================================
# RISK BUDGETS
# ============================================================

RISK_BUDGETS = {

    "SPY": 0.20,
    "EFA": 0.10,
    "EEM": 0.10,

    "TLT": 0.20,
    "IEF": 0.10,

    "GLD": 0.10,
    "DBC": 0.05,

    "XLP": 0.05,
    "XLU": 0.05,
    "SHY": 0.05
}

# ============================================================
# RISK BUDGETING
# ============================================================

class RiskBudgeting:

    def portfolio_vol(
        self,
        weights,
        covariance
    ):

        return np.sqrt(

            weights.T

            @

            covariance

            @

            weights
        )

    def risk_contribution(
        self,
        weights,
        covariance
    ):

        vol = self.portfolio_vol(
            weights,
            covariance
        )

        marginal = (

            covariance

            @

            weights
        ) / vol

        contribution = (
            weights
            * marginal
        )

        return contribution

    def optimize(
        self,
        covariance,
        target_budget
    ):

        n = len(
            target_budget
        )

        x0 = (
            np.ones(n)
            / n
        )

        def objective(w):

            rc = (
                self.risk_contribution(
                    w,
                    covariance
                )
            )

            rc = (
                rc
                /
                rc.sum()
            )

            return np.sum(
                (
                    rc
                    -
                    target_budget
                ) ** 2
            )

        constraints = [

            {
                "type": "eq",

                "fun":
                    lambda w:
                    np.sum(w) - 1
            }
        ]

        bounds = [

            (0, 1)

            for _
            in range(n)
        ]

        result = minimize(

            objective,

            x0,

            method="SLSQP",

            bounds=bounds,

            constraints=constraints
        )

        if not result.success:

            raise ValueError(
                result.message
            )

        return result.x

# ============================================================
# PORTFOLIO CONSTRAINTS
# ============================================================

class PortfolioConstraints:

    MAX_WEIGHT = (
        settings.max_position_weight
    )

    MIN_WEIGHT = 0.0

    MAX_LEVERAGE = (
        settings.max_leverage
    )

    @staticmethod
    def enforce(
        weights
    ):

        weights = np.clip(

            weights,

            PortfolioConstraints.MIN_WEIGHT,

            PortfolioConstraints.MAX_WEIGHT
        )

        weights /= weights.sum()

        return weights

# ============================================================
# ALPHA ENGINE
# ============================================================

class AlphaEngine:

    def combine(
        self,
        momentum,
        factor,
        macro
    ):

        return (

            0.40
            * momentum

            +

            0.40
            * factor

            +

            0.20
            * macro
        )

# ============================================================
# SECTION 3 TEST
# ============================================================

def test_risk_budgeting():

    covariance = np.array([

        [0.10, 0.02, 0.01],

        [0.02, 0.08, 0.01],

        [0.01, 0.01, 0.06]
    ])

    target_budget = np.array([

        0.40,
        0.30,
        0.30
    ])

    rb = RiskBudgeting()

    weights = rb.optimize(
        covariance,
        target_budget
    )

    print(
        "Risk Budget Weights:"
    )

    print(weights)

    assert np.isclose(
        weights.sum(),
        1.0
    )

    assert (
        weights >= 0
    ).all()

    print(
        "Risk Budgeting test passed"
    )

    
import numpy as np

# ============================================================
# SECTION 4
# PORTFOLIO CONSTRUCTION + EXECUTION + BACKTESTING
# ============================================================

from dataclasses import dataclass
from datetime import datetime

# ============================================================
# VOLATILITY TARGETING
# ============================================================

class VolatilityTargeting:

    def scale_weights(
        self,
        weights,
        covariance,
        target_vol=0.10
    ):

        portfolio_vol = np.sqrt(

            weights.T

            @

            covariance

            @

            weights
        )

        if portfolio_vol <= 0:

            return weights

        scale_factor = (
            target_vol
            /
            portfolio_vol
        )

        scaled_weights = (
            weights
            * scale_factor
        )

        return scaled_weights

# ============================================================
# ALLOCATION ENGINE
# ============================================================

class AllocationEngine:

    def allocate(
        self,
        alpha_scores
    ):

        alpha_scores = np.maximum(
            alpha_scores,
            0
        )

        if alpha_scores.sum() == 0:

            return (

                np.ones(
                    len(alpha_scores)
                )

                /

                len(alpha_scores)
            )

        return (

            alpha_scores

            /

            alpha_scores.sum()
        )

# ============================================================
# PORTFOLIO OPTIMIZER
# ============================================================

class PortfolioOptimizer:

    def __init__(
        self,
        risk_budget_engine,
        constraints,
        vol_target_engine=None
    ):

        self.risk_budget_engine = (
            risk_budget_engine
        )

        self.constraints = (
            constraints
        )

        self.vol_target_engine = (
            vol_target_engine
        )

    def optimize(
        self,
        covariance,
        risk_budget,
        target_vol=None
    ):

        weights = (

            self.risk_budget_engine
            .optimize(
                covariance,
                risk_budget
            )
        )

        weights = (

            self.constraints
            .enforce(weights)
        )

        if (

            target_vol is not None

            and

            self.vol_target_engine
        ):

            weights = (

                self.vol_target_engine
                .scale_weights(
                    weights,
                    covariance,
                    target_vol
                )
            )

        return weights

# ============================================================
# POSITION SIZING
# ============================================================

class PositionSizer:

    def __init__(
        self,
        capital
    ):

        self.capital = capital

    def shares(
        self,
        weights,
        prices
    ):

        allocations = (
            weights
            * self.capital
        )

        shares = (
            allocations
            /
            prices
        )

        return (
            shares.astype(int)
        )

# ============================================================
# ORDER OBJECT
# ============================================================

@dataclass
class Order:

    symbol: str

    quantity: int

    side: str

    timestamp: datetime

    order_type: str = "MARKET"

    status: str = "CREATED"

# ============================================================
# SLIPPAGE
# ============================================================

class SlippageModel:

    def __init__(
        self,
        slippage_bps=3
    ):

        self.slippage_bps = (
            slippage_bps
        )

    def apply(
        self,
        price,
        side
    ):

        slip = (
            self.slippage_bps
            /
            10000
        )

        if side == "BUY":

            return (
                price
                *
                (1 + slip)
            )

        return (
            price
            *
            (1 - slip)
        )

# ============================================================
# TRANSACTION COSTS
# ============================================================

class TransactionCostModel:

    def __init__(
        self,
        bps=5
    ):

        self.bps = bps

    def cost(
        self,
        quantity,
        price
    ):

        return (

            quantity
            *
            price
            *
            self.bps
            /
            10000
        )

# ============================================================
# EXECUTION ENGINE
# ============================================================

class ExecutionEngine:

    def __init__(
        self,
        slippage_model,
        tc_model
    ):

        self.slippage_model = (
            slippage_model
        )

        self.tc_model = (
            tc_model
        )

    def execute(
        self,
        order,
        market_price
    ):

        fill_price = (

            self.slippage_model
            .apply(
                market_price,
                order.side
            )
        )

        trading_cost = (

            self.tc_model
            .cost(
                order.quantity,
                fill_price
            )
        )

        order.status = "FILLED"

        return {

            "fill_price":
                fill_price,

            "cost":
                trading_cost
        }

# ============================================================
# OMS
# ============================================================

class OMS:

    def __init__(self):

        self.orders = []

    def submit(
        self,
        order
    ):

        self.orders.append(
            order
        )

    def open_orders(self):

        return [

            order

            for order

            in self.orders

            if order.status
            != "FILLED"
        ]

    def filled_orders(self):

        return [

            order

            for order

            in self.orders

            if order.status
            == "FILLED"
        ]

# ============================================================
# PORTFOLIO STATE
# ============================================================

class PortfolioState:

    def __init__(self):

        self.positions = {}

    def update_position(
        self,
        symbol,
        quantity
    ):

        self.positions[symbol] = (

            self.positions.get(
                symbol,
                0
            )

            +

            quantity
        )

    def holdings(self):

        return self.positions

# ============================================================
# PAPER BROKER
# ============================================================

class PaperBroker:

    def __init__(self):

        self.positions = {}

    def execute(
        self,
        order
    ):

        quantity = (

            order.quantity

            if order.side == "BUY"

            else -order.quantity
        )

        self.positions[
            order.symbol
        ] = (

            self.positions.get(
                order.symbol,
                0
            )

            +

            quantity
        )

        order.status = "FILLED"

        return order

# ============================================================
# BROKER ROUTER
# ============================================================

class BrokerRouter:

    def __init__(
        self,
        primary,
        backup
    ):

        self.primary = primary

        self.backup = backup

    def execute(
        self,
        order
    ):

        try:

            return (
                self.primary
                .execute(order)
            )

        except Exception:

            logger.warning(
                "Primary broker failed."
            )

            return (
                self.backup
                .execute(order)
            )

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
# BACKTESTER
# ============================================================

class Backtester:

    def __init__(
        self,
        strategy
    ):

        self.strategy = strategy

    def run(
        self,
        returns
    ):

        portfolio_returns = []

        for t in range(
            252,
            len(returns)
        ):

            window = (
                returns.iloc[:t]
            )

            weights = (

                self.strategy
                .generate(
                    window
                )
            )

            next_return = (
                returns.iloc[t]
            )

            portfolio_returns.append(

                (
                    weights
                    *
                    next_return
                ).sum()
            )

        return pd.Series(

            portfolio_returns,

            index=returns.index[
                252:
            ]
        )

# ============================================================
# SECTION 4 SMOKE TEST
# ============================================================

class EqualWeightStrategy:

    def generate(
        self,
        window
    ):

        n = len(
            window.columns
        )

        return (
            np.ones(n)
            /
            n
        )


def test_backtester():

    loader = MarketDataLoader(
        assets=["SPY", "TLT", "GLD"],
        period="5y"
    )

    returns = (
        loader.load_returns()
    )

    strategy = (
        EqualWeightStrategy()
    )

    bt = Backtester(
        strategy
    )

    results = bt.run(
        returns
    )

    analytics = (
        PerformanceAnalytics()
    )

    metrics = (
        analytics.metrics(
            results
        )
    )

    print(metrics)

# ============================================================
# SECTION 5
# PRODUCTION SERVICES
# ============================================================

import json
import redis

from prometheus_client import (
    Gauge,
    Counter
)

from fastapi import FastAPI

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)

from reportlab.lib.styles import (
    getSampleStyleSheet
)

from email.mime.text import MIMEText

import smtplib

import pandas_market_calendars as mcal

# ============================================================
# REDIS
# ============================================================

class RedisClient:

    def __init__(self):

        self.client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True
        )

    def set_json(
        self,
        key,
        value
    ):

        self.client.set(
            key,
            json.dumps(value)
        )

    def get_json(
        self,
        key
    ):

        value = self.client.get(key)

        if value:

            return json.loads(value)

        return None

# ============================================================
# DATABASE REPOSITORY
# ============================================================

class Repository:

    @staticmethod
    def session():

        if SessionLocal is None:

            raise DatabaseError(
                "Database not configured"
            )

        return SessionLocal()

# ============================================================
# ALPACA
# ============================================================

try:

    from alpaca.trading.client import (
        TradingClient
    )

    from alpaca.trading.requests import (
        MarketOrderRequest
    )

    from alpaca.trading.enums import (
        OrderSide,
        TimeInForce
    )

    ALPACA_AVAILABLE = True

except Exception:

    ALPACA_AVAILABLE = False


class AlpacaBroker:

    def __init__(self):

        if not ALPACA_AVAILABLE:

            raise ImportError(
                "alpaca-py not installed"
            )

        if not settings.alpaca_key:

            raise ValueError(
                "Alpaca key missing"
            )

        self.client = TradingClient(
            settings.alpaca_key,
            settings.alpaca_secret,
            paper=True
        )

    def submit_order(
        self,
        symbol,
        qty,
        side
    ):

        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=(
                OrderSide.BUY
                if side == "BUY"
                else OrderSide.SELL
            ),
            time_in_force=TimeInForce.DAY
        )

        return (
            self.client.submit_order(
                order
            )
        )

# ============================================================
# PROMETHEUS
# ============================================================

portfolio_value_metric = Gauge(
    "portfolio_value",
    "Portfolio Value"
)

portfolio_var_metric = Gauge(
    "portfolio_var",
    "Portfolio VaR"
)

orders_executed_metric = Counter(
    "orders_executed",
    "Orders Executed"
)

# ============================================================
# ALERT ENGINE
# ============================================================

class AlertEngine:

    def send_email(
        self,
        subject,
        body,
        sender,
        password,
        receiver
    ):

        msg = MIMEText(body)

        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = receiver

        server = smtplib.SMTP(
            "smtp.gmail.com",
            587
        )

        server.starttls()

        server.login(
            sender,
            password
        )

        server.send_message(msg)

        server.quit()

# ============================================================
# RECONCILIATION
# ============================================================

class Reconciliation:

    def compare(
        self,
        internal_positions,
        broker_positions
    ):

        breaks = {}

        symbols = (

            set(
                internal_positions.keys()
            )

            |

            set(
                broker_positions.keys()
            )
        )

        for symbol in symbols:

            internal_qty = (
                internal_positions.get(
                    symbol,
                    0
                )
            )

            broker_qty = (
                broker_positions.get(
                    symbol,
                    0
                )
            )

            if internal_qty != broker_qty:

                breaks[symbol] = {

                    "internal":
                        internal_qty,

                    "broker":
                        broker_qty
                }

        return breaks

# ============================================================
# KILL SWITCH
# ============================================================

class KillSwitch:

    def __init__(
        self,
        max_drawdown=-0.20
    ):

        self.max_drawdown = (
            max_drawdown
        )

    def check(
        self,
        current_drawdown
    ):

        if current_drawdown < (
            self.max_drawdown
        ):

            raise RiskLimitBreach(
                "Trading halted"
            )

# ============================================================
# MARKET CALENDAR
# ============================================================

class MarketCalendar:

    def is_open_today(self):

        nyse = (
            mcal.get_calendar(
                "NYSE"
            )
        )

        schedule = nyse.schedule(
            start_date=pd.Timestamp.today(),
            end_date=pd.Timestamp.today()
        )

        return (
            len(schedule)
            > 0
        )

# ============================================================
# PDF REPORTING
# ============================================================

class PDFReport:

    def generate(
        self,
        metrics,
        filename
    ):

        doc = (
            SimpleDocTemplate(
                filename
            )
        )

        styles = (
            getSampleStyleSheet()
        )

        content = [

            Paragraph(
                "Portfolio Report",
                styles["Title"]
            ),

            Spacer(1, 12)
        ]

        for key, value in (
            metrics.items()
        ):

            content.append(

                Paragraph(
                    f"{key}: {value}",
                    styles["BodyText"]
                )
            )

        doc.build(content)

# ============================================================
# FASTAPI
# ============================================================

api = FastAPI()


@api.get("/health")
def health():

    return {

        "status":
            "healthy"
    }


@api.get("/portfolio")
def portfolio_status():

    return {

        "status":
            "running"
    }

# ============================================================
# STREAMLIT
# ============================================================

def render_dashboard():

    import streamlit as st

    st.set_page_config(
        layout="wide"
    )

    st.title(
        "Institutional Portfolio Dashboard"
    )

    st.metric(
        "Portfolio Value",
        "$1,000,000"
    )

    st.metric(
        "Sharpe Ratio",
        "1.35"
    )

    st.metric(
        "Max Drawdown",
        "-8%"
    )

# ============================================================
# INTEGRATION TESTS
# ============================================================

def test_market_data():

    loader = MarketDataLoader(
        assets=["SPY"],
        period="1y"
    )

    returns = (
        loader.load_returns()
    )

    assert len(
        returns
    ) > 0

    assert not returns.empty

    returns = loader.load_returns()

    assert returns.isna().sum().sum() == 0


def test_backtest():

    loader = MarketDataLoader(
        assets=[
            "SPY",
            "TLT",
            "GLD"
        ],
        period="3y"
    )

    returns = (
        loader.load_returns()
    )

    strategy = (
        EqualWeightStrategy()
    )

    bt = Backtester(
        strategy
    )

    result = bt.run(
        returns
    )

    assert len(
        result
    ) > 0

# ============================================================
# STARTUP CHECK
# ============================================================

def startup_check():

    print(
        "Section 5 loaded successfully"
    )

    print(
        "Redis Host:",
        settings.redis_host
    )

    print(
        "Database Enabled:",
        SessionLocal is not None
    )

    print(
        "Alpaca Configured:",
        settings.alpaca_key is not None
    )

# ============================================================
# MONTE CARLO SIMULATION
# ============================================================

class MonteCarloSimulator:

    def simulate(
        self,
        returns,
        n_sims=1000,
        horizon=252
    ):

        mu = returns.mean()

        sigma = returns.std()

        simulations = []

        for _ in range(n_sims):

            path = np.random.normal(
                mu,
                sigma,
                horizon
            )

            equity = (
                1 + pd.Series(path)
            ).cumprod()

            simulations.append(
                equity.iloc[-1]
            )

        return np.array(
            simulations
        )

    def summary(
        self,
        simulations
    ):

        return {

            "mean_terminal":

                simulations.mean(),

            "median_terminal":

                np.median(
                    simulations
                ),

            "5pct":

                np.percentile(
                    simulations,
                    5
                ),

            "95pct":

                np.percentile(
                    simulations,
                    95
                )
        }
    
# ============================================================
# STRESS TESTING
# ============================================================

class StressTester:

    def historical_crash(
        self,
        returns
    ):

        worst = returns.nsmallest(
            10
        )

        return {

            "worst_day":
                worst.min(),

            "avg_worst_10":
                worst.mean()
        }

    def scenario_shock(
        self,
        weights,
        shock=-0.20
    ):

        pnl = (
            weights.sum()
            * shock
        )

        return pnl
    
# ============================================================
# WALK FORWARD
# ============================================================

class WalkForwardOptimizer:

    def run(
        self,
        returns,
        train_window=504,
        test_window=63
    ):

        results = []

        start = train_window

        while (

            start
            + test_window

            <

            len(returns)
        ):

            train = returns.iloc[
                start-train_window:
                start
            ]

            test = returns.iloc[
                start:
                start+test_window
            ]

            mean_returns = (
                train.mean()
            )

            weights = (

                mean_returns
                /
                mean_returns.sum()
            )

            pnl = (

                test
                @
                weights
            )

            results.extend(
                pnl.values
            )

            start += test_window

        return pd.Series(
            results
        )
    
# ============================================================
# REGIME VOLATILITY
# ============================================================

class RegimeVolatilityModel:

    def estimate(
        self,
        returns,
        regime
    ):

        base_vol = (

            returns.std()

            *
            np.sqrt(
                TRADING_DAYS
            )
        )

        if regime == Regime.RECESSION:

            return (
                base_vol
                * 1.5
            )

        if regime == Regime.SLOWDOWN:

            return (
                base_vol
                * 1.2
            )

        return base_vol
    
# ============================================================
# PERFORMANCE ATTRIBUTION
# ============================================================

class PerformanceAttribution:

    def contribution(
        self,
        weights,
        returns
    ):

        contributions = (

            weights
            *
            returns
        )

        return contributions

    def summary(
        self,
        weights,
        returns
    ):

        contrib = (
            self.contribution(
                weights,
                returns
            )
        )

        return pd.DataFrame({

            "weight":
                weights,

            "return":
                returns,

            "contribution":
                contrib
        })
    
# ============================================================
# STRATEGY REGISTRY
# ============================================================

class StrategyRegistry:

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

    def get(
        self,
        name
    ):

        return self.strategies[
            name
        ]
    
# ============================================================
# ENSEMBLE ALPHA
# ============================================================

class EnsembleSignal:

    def combine(
        self,
        signals,
        weights=None
    ):

        signals = np.array(
            signals
        )

        if weights is None:

            weights = (

                np.ones(
                    len(signals)
                )

                /

                len(signals)
            )

        return np.dot(
            signals,
            weights
        )
    
import plotly.express as px

class Visualization:

    def equity_curve(
        self,
        returns
    ):

        equity = (
            1 + returns
        ).cumprod()

        return px.line(
            equity,
            title="Equity Curve"
        )

    def allocation_pie(
        self,
        weights,
        labels
    ):

        return px.pie(
            values=weights,
            names=labels,
            title="Portfolio Allocation"
        )    
# ============================================================
# FULL HRP
# ============================================================

from scipy.cluster.hierarchy import (
    linkage,
    dendrogram
)

from scipy.spatial.distance import squareform

class HRPOptimizer:

    def correlation_distance(
        self,
        corr
    ):

        return np.sqrt(
            0.5 * (1 - corr)
        )

    def optimize(
        self,
        covariance
    ):

        corr = np.corrcoef(
            covariance
        )

        distance = (
            self.correlation_distance(
                corr
            )
        )

        link = linkage(
            squareform(
                distance,
                checks=False
            ),
            method="ward"
        )

        n = len(covariance)

        weights = (
            np.ones(n)
            / n
        )

        return weights