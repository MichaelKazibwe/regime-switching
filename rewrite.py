from macroregime import (
    Regime,
    PortfolioRegimeMapper,
)

from regimesimulation import (
    RegimeMonteCarlo,
    RegimePortfolioSimulator,
    RegimeSimulationAnalytics,
)

from expectedreturnforecaster import (
    ExpectedReturnForecaster,
)

from blacklitterman import (
    BlackLittermanModel,
)

from forwardriskmetrics import ForwardRiskMetrics

from marketdataloader import MarketDataLoader

from constraints import PortfolioConstraints

from analytics import PerformanceAnalytics

from portfoliooptimizer import PortfolioOptimizer

from riskcontributionanalyzer import (
    RiskContributionAnalytics,
    RiskBudgetReport,
)

from core_constants import (
    DEFAULT_ASSETS,
    REGIME_RISK_BUDGETS,
    TRADING_DAYS
)

# ============================================================
# SECTION 1
# CORE INFRASTRUCTURE
# ============================================================

import json
import logging
import plotly.express as px

from hmmlearn.hmm import GaussianHMM

from scipy.cluster.hierarchy import (
    linkage,
)

from scipy.spatial.distance import (
    squareform,
)

from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import minimize
from sklearn.linear_model import LinearRegression
from fredapi import Fred
from dataclasses import dataclass
from exceptions import (
    DataValidationError,
    DatabaseError,
    RiskLimitBreach,
)

import redis
import smtplib
import pandas_market_calendars as mcal

from email.mime.text import MIMEText

from fastapi import FastAPI

from prometheus_client import (
    Gauge,
    Counter,
)

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)

from reportlab.lib.styles import (
    getSampleStyleSheet,
)

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

from sklearn.covariance import (
    LedoitWolf
)

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("PortfolioSystem")

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

FRED_SERIES = {
    "FEDFUNDS": "FEDFUNDS",
    "UNRATE": "UNRATE",
    "CPI": "CPIAUCSL",
}


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

    logger.info(
        "Section 1 initialized successfully"
    )

    logger.info(
        "Database configured:",
        settings.database_url is not None
    )

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


def test_regime_mapper():

    assert (

        PortfolioRegimeMapper
        .map_regime(
            Regime.EXPANSION
        )

        ==

        "bull"
    )

    assert (

        PortfolioRegimeMapper
        .map_regime(
            Regime.RECOVERY
        )

        ==

        "bull"
    )

    assert (

        PortfolioRegimeMapper
        .map_regime(
            Regime.SLOWDOWN
        )

        ==

        "neutral"
    )

    assert (

        PortfolioRegimeMapper
        .map_regime(
            Regime.RECESSION
        )

        ==

        "crisis"
    )

    logger.info(
        "Regime mapper test passed"
    )

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
# RISK BUDGETING
# ============================================================

class RiskBudgeting:

    def portfolio_vol(
        self,
        weights,
        covariance
    ):

        covariance = np.nan_to_num(
            covariance
        )

        variance = (

            weights.T

            @

            covariance

            @

            weights
        )

        variance = max(
            variance,
            0.0
        )

        return np.sqrt(
            variance
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

        if vol <= 1e-12:

            return np.zeros_like(
                weights
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

        contribution = np.nan_to_num(
            contribution
        )

        return contribution

    def optimize(
        self,
        covariance,
        target_budget
    ):

        covariance = np.asarray(
            covariance,
            dtype=float
        )

        covariance = np.nan_to_num(
            covariance
        )

        target_budget = np.asarray(
            target_budget,
            dtype=float
        )

        target_budget = (
            target_budget
            /
            target_budget.sum()
        )

        n = len(
            target_budget
        )

        x0 = (
            np.ones(n)
            / n
        )

        def objective(w):

            w = np.maximum(
                w,
                1e-12
            )

            rc = (
                self.risk_contribution(
                    w,
                    covariance
                )
            )

            rc_sum = rc.sum()

            if rc_sum <= 1e-12:

                return 1e6

            rc = (
                rc
                /
                rc_sum
            )

            error = (
                rc
                -
                target_budget
            )

            return np.sum(
                error ** 2
            )

        constraints = [

            {
                "type": "eq",
                "fun": (
                    lambda w:
                    np.sum(w) - 1.0
                )
            }
        ]

        bounds = [

            (
                0.0,
                1.0
            )

            for _ in range(n)
        ]

        result = minimize(

            objective,

            x0,

            method="SLSQP",

            bounds=bounds,

            constraints=constraints,

            options={
                "maxiter": 500,
                "ftol": 1e-12
            }
        )

        if not result.success:

            logger.warning(result.message)
            
            return x0

        weights = np.maximum(
            result.x,
            0.0
        )

        weights /= (
            weights.sum()
        )

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

    logger.info(
        "Risk Budget Weights:"
    )

    logger.debug("Weights:\n%s", weights)
    

def test_risk_budgeting_edge_cases():

    rb = RiskBudgeting()

    cov = np.array([
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0]
    ])

    target = np.array([
        0.4,
        0.3,
        0.3
    ])

    weights = rb.optimize(
        cov,
        target
    )

    assert np.isfinite(
        weights
    ).all()

    assert np.isclose(
        weights.sum(),
        1.0
    )

    assert (
        weights >= 0
    ).all()

    logger.info(
        "Risk Budget Edge Case test passed"
    )   
    
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

        weights = np.asarray(
            weights,
            dtype=float
        )

        covariance = np.asarray(
            covariance,
            dtype=float
        )

        covariance = np.nan_to_num(
            covariance
        )

        portfolio_var = (

            weights.T

            @

            covariance

            @

            weights
        )

        if portfolio_var <= 0:

            return weights

        portfolio_vol = np.sqrt(
            portfolio_var
        )

        if not np.isfinite(
            portfolio_vol
        ):

            return weights

        scale_factor = (
            target_vol
            /
            portfolio_vol
        )

        max_leverage = (
            settings.max_leverage
        )

        scale_factor = min(
            scale_factor,
            max_leverage
        )

        scaled_weights = (
            weights
            * scale_factor
        )

        gross_exposure = (
            scaled_weights.sum()
        )

        if gross_exposure > max_leverage:

            scaled_weights *= (
                max_leverage
                /
                gross_exposure
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
# OPTIMIZER RISK REPORT TEST
# ============================================================

def test_optimizer_risk_report():

    covariance = np.eye(
        len(DEFAULT_ASSETS)
    )

    optimizer = PortfolioOptimizer(

        RiskBudgeting(),

        PortfolioConstraints(),

        VolatilityTargeting()

    )

    result = (

        optimizer.optimize(

            covariance,

            "neutral",

            DEFAULT_ASSETS

        )

    )

    report = result[
        "risk_report"
    ]

    assert len(
        report
    ) == len(
        DEFAULT_ASSETS
    )

    assert (
        "Target"
        in report.columns
    )

    assert (
        "Actual"
        in report.columns
    )

    assert (
        "Difference"
        in report.columns
    )

    logger.info(
        "Optimizer risk report test passed"
    )

# ============================================================
# REGIME PORTFOLIO TEST
# ============================================================

def test_regime_portfolio_optimizer():

    covariance = np.eye(14)

    optimizer = (

        PortfolioOptimizer(

            RiskBudgeting(),

            PortfolioConstraints(),

            VolatilityTargeting()

        )

    )

    test_regimes = [

        Regime.EXPANSION,
        Regime.SLOWDOWN,
        Regime.RECESSION,
        Regime.RECOVERY

    ]

    for macro_regime in test_regimes:

        result = (

    optimizer
    .optimize(
        covariance,
        macro_regime,
        DEFAULT_ASSETS
    )

)

        weights = (
            result["weights"]
        )

        cash = (
            result["cash"]
        )

        portfolio_regime = (
            result["regime"]
        )

        assert np.isfinite(
            weights
        ).all()

        assert (
            weights >= 0
        ).all()

        assert np.isfinite(
            cash
        )

        assert cash >= 0

        assert np.isclose(

            weights.sum()

            +

            cash,

            1.0,

            atol=1e-6

        )

        assert portfolio_regime in [

            "bull",
            "neutral",
            "crisis"

        ]

    logger.info(
        "Regime portfolio optimizer test passed"
    )

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
        assert (
    prices > 0
).all(), (
    "Invalid prices"
)

        assert (
    weights >= 0
).all(), (
    "Negative portfolio weights"
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
# SLIPPAGE MODEL
# ============================================================

class SlippageModel:

    def __init__(
        self,
        base_slippage_bps=5.0,
        impact_factor=0.10
    ):

        self.base_slippage_bps = (
            base_slippage_bps
        )

        self.impact_factor = (
            impact_factor
        )

    def estimate(

        self,

        turnover,

        portfolio_vol

    ):

        slippage_bps = (

            self.base_slippage_bps

            *

            (
                1.0
                +
                self.impact_factor
                *
                portfolio_vol
            )

        )

        return (

            turnover

            *
            slippage_bps

            /
            10000.0

        )

# ============================================================
# SLIPPAGE TEST
# ============================================================

def test_slippage_model():

    model = (
        SlippageModel()
    )

    cost = (
        model.estimate(
            turnover=0.50,
            portfolio_vol=0.20
        )
    )

    assert cost > 0

    assert np.isfinite(
        cost
    )

    logger.info(
        "Slippage test passed"
    )

# ============================================================
# TRANSACTION_COST_MODEL
# ============================================================

class LegacyTransactionCostModel:

    def __init__(
        self,
        commission_bps=1.0,
        slippage_bps=5.0
    ):

        self.commission_bps = (
            commission_bps
        )

        self.slippage_bps = (
            slippage_bps
        )

    def estimate_cost(

        self,

        turnover

    ):

        total_bps = (

            self.commission_bps

            +

            self.slippage_bps

        )

        return (

            turnover

            *

            total_bps

            / 10000.0

        )

# ============================================================
# TRANSACTION COST TEST
# ============================================================

def test_transaction_cost_model():

    model = (
        LegacyTransactionCostModel(
            commission_bps=1,
            slippage_bps=5
        )
    )

    cost = (
        model.estimate_cost(
            turnover=0.50
        )
    )

    expected = (
        0.50
        *
        6
        /
        10000
    )

    assert np.isclose(
        cost,
        expected
    )

    logger.info(
        "Transaction Cost test passed"
    )

# ============================================================
# EXECUTION ENGINE
# ============================================================

class LegacyExecutionEngine:

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
# BACKTESTER
# ============================================================

class Backtester:

    def __init__(
        self,
        strategy,
        transaction_cost_model=None
    ):

        self.strategy = strategy

        self.transaction_cost_model = (

            transaction_cost_model

            if transaction_cost_model is not None

            else LegacyTransactionCostModel()
        )

    def run(
        self,
        returns
    ):

        portfolio_returns = []

        turnover_series = []

        cost_series = []

        previous_weights = None

        for t in range(
            252,
            len(returns)
        ):

            window = (
                returns.iloc[:t]
            )

            weights = np.asarray(

                self.strategy
                .generate(
                    window
                ),

                dtype=float
            )

            next_return = (
                returns.iloc[t]
            )

            gross_return = (

                weights

                *

                next_return.values

            ).sum()

            if previous_weights is None:

                turnover = 0.0

            else:

                turnover = (

                    TurnoverControl
                    .turnover(
                        previous_weights,
                        weights
                    )

                )

            portfolio_vol = np.std(
                window.values
            )

            transaction_cost = (

                self.transaction_cost_model
                .estimate_cost(
                    turnover
                )

            )

            slippage_cost = (

                SlippageModel()
                .estimate(
                    turnover,
                    portfolio_vol
                )

            )

            total_cost = (

                transaction_cost

                +

                slippage_cost

            )

            net_return = (

                gross_return

                -

                total_cost

            )

            portfolio_returns.append(
                net_return
            )

            turnover_series.append(
                turnover
            )

            cost_series.append(
                total_cost
            )

            previous_weights = (
                weights.copy()
            )

        result = pd.DataFrame(

            {

                "return":
                    portfolio_returns,

                "turnover":
                    turnover_series,

                "cost":
                    cost_series

            },

            index=returns.index[
                252:
            ]

        )

        return result
    
def test_backtest_costs():

    class DummyStrategy:

        def generate(
            self,
            window
        ):

            n = len(
                window.columns
            )

            return (
                np.ones(n)
                / n
            )

    returns = pd.DataFrame(

        np.random.normal(
            0,
            0.01,
            (600, 5)
        )
    )

    results = (
        Backtester(
            DummyStrategy()
        )
        .run(
            returns
        )
    )

    assert "return" in results.columns

    assert "turnover" in results.columns

    assert "cost" in results.columns

    assert np.isfinite(
        results.values
    ).all()

    logger.info(
        "Backtest cost test passed"
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
    analytics = PerformanceAnalytics()

    logger.info(
    analytics.summary(
        results["return"]
    )
)
    
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

    logger.info(
        "Section 5 loaded successfully"
    )

    logger.info(
        "Redis Host: %s",
        settings.redis_host
    )

    logger.info(
        "Database Enabled: %s",
        SessionLocal is not None
    )

    logger.info(
        "Alpaca Configured: %s",
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

        # ============================================
        # PORTFOLIO ACCOUNT
        # ============================================

        account = PortfolioAccount(
            initial_capital=1_000_000
        )

        # ============================================
        # BACKTEST STORAGE
        # ============================================

        results = []

        daily_returns = []

        nav_history = []

        regime_history = []

        turnover_history = []

        transaction_cost_history = []

        trade_count = 0

        
        # ============================================
        # INITIAL PORTFOLIO VALUE
        # ============================================

        previous_nav = float(
            account.portfolio_value
        )

        # ============================================
        # WALK FORWARD START
        # ============================================

        start = train_window

        # ============================================
        # PORTFOLIO OPTIMIZER
        # ============================================

        optimizer = PortfolioOptimizer(

            RiskBudgeting(),

            PortfolioConstraints(),

            VolatilityTargeting()

        )

        # ============================================
        # WALK FORWARD LOOP
        # ============================================

        while (

            start + test_window

            < len(returns)

        ):

            # ===================================
            # TRAIN / TEST SPLIT
            # ===================================

            train = returns.iloc[
                start - train_window:
                start
            ]

            test = returns.iloc[
                start:
                start + test_window
            ]

            assert len(train) == train_window

            assert len(test) > 0

            assert account.portfolio_value > 0

            # ===================================
            # COVARIANCE ESTIMATION
            # ===================================

            covariance = (
                CovarianceEstimator
                .ledoit_wolf(
                    train
                )
            )

            # ===================================
            # VALIDATION
            # ===================================

            assert (
                covariance.shape[0]
                ==
                covariance.shape[1]
            )

            assert (
                covariance.shape[0]
                ==
                len(train.columns)
            )

            assert np.isfinite(
                covariance
            ).all()

            # ===================================
            # MARKET REGIME
            # ===================================

            market_returns = (
                train.mean(
                    axis=1
                )
            )

            hmm = HMMRegimeModel()

            hmm.fit(
                market_returns
            )

            current_state = (
                hmm.current_state(
                    market_returns
                )
            )

            state_ranks = (
                hmm.state_volatility_rank(
                    market_returns
                )
            )

            regime = (
                HMMRegimeMapper
                .map_state(
                    current_state,
                    state_ranks
                )
            )

            regime_history.append(
                regime
            )

            # ===================================
            # REGIME EXPECTED RETURNS
            # ===================================

            states = (
                hmm.predict_states(
                    market_returns
                )
            )

            regime_returns = (
                RegimeExpectedReturnModel
                .estimate(
                    train,
                    states,
                    hmm.n_states
                )
            )

            next_state_probs = (
                RegimeTransitionAnalytics
                .next_state_probabilities(
                    hmm,
                    current_state
                )
            )

            regime_forecast = (
                RegimeForecastCombiner
                .combine(
                    regime_returns,
                    next_state_probs
                )
            )

            # ===================================
            # BLACK-LITTERMAN
            # ===================================

            posterior_forecast = (
                RegimeBlackLitterman
                .posterior_forecast(
                    covariance,
                    regime_forecast
                )
            )

            if posterior_forecast is not None:

                forecast_scale = (
                    posterior_forecast
                    .rank(
                        pct=True
                    )
                )

            else:

                forecast_scale = pd.Series(
                    1.0,
                    index=train.columns
                )

            # ===================================
            # REGIME RISK
            # ===================================

            crisis_probability = (
                RegimeProbabilityEngine
                .crisis_probability(
                    hmm,
                    current_state,
                    state_ranks
                )
            )

            leverage_multiplier = (
                RegimeProbabilityEngine
                .leverage_multiplier(
                    crisis_probability
                )
            )

            # ===================================
            # PORTFOLIO OPTIMIZATION
            # ===================================

            optimization = (
                optimizer.optimize(
                    covariance,
                    regime,
                    train.columns,
                    prices=None
                )
            )

            weights = pd.Series(
                optimization["weights"],
                index=train.columns,
                dtype=float
            )

            # ===================================
            # FORECAST TILT
            # ===================================

            weights *= forecast_scale

            if weights.sum() > 0:

                weights /= (
                    weights.sum()
                )

            # ===================================
            # LEVERAGE ADJUSTMENT
            # ===================================

            weights *= (
                leverage_multiplier
            )

            # ===================================
            # SAFETY CHECKS
            # ===================================

            assert np.isfinite(
                weights
            ).all()

            assert (
                weights >= 0
            ).all()
            
            # ===================================
            # TARGET PORTFOLIO
            # ===================================

            target_weights = (
                weights.copy()
            )

            # ===================================
            # MARKET PRICES
            # ===================================

            current_prices = pd.Series(
                100.0,
                index=train.columns,
                dtype=float
            )

            # ===================================
            # REBALANCE
            # ===================================

            trades = (
                RebalanceEngine
                .threshold_rebalance(
                    account,
                    target_weights,
                    current_prices,
                    threshold=0.03
                )
            )

            # ===================================
            # EXECUTION ANALYTICS
            # ===================================

            if trades is not None:

                trade_count += 1

                transaction_cost = (
                    TransactionCostModel
                    .estimate(
                        trades
                    )
                )

                transaction_cost_history.append(
                    transaction_cost
                )

                if len(
                    account.turnover_history
                ) > 0:

                    turnover_history.append(

                        account.turnover_history[-1]

                    )

            # ===================================
            # DAILY PORTFOLIO ACCOUNTING
            # ===================================

            for _, row in test.iterrows():

                portfolio_return = float(

                    np.dot(

                        weights.values,

                        row.values

                    )

                )

                current_nav = (

                    previous_nav

                    *

                    (

                        1.0

                        +

                        portfolio_return

                    )

                )

                account.portfolio_value = (
                    current_nav
                )

                account.nav_history.append(
                    current_nav
                )

                nav_history.append(
                    current_nav
                )

                daily_return = (

                    current_nav

                    /

                    previous_nav

                    -

                    1.0

                )

                daily_returns.append(
                    daily_return
                )

                results.append(
                    daily_return
                )

                previous_nav = (
                    current_nav
                )

            # ===================================
            # NEXT WALK-FORWARD WINDOW
            # ===================================

            start += test_window

        # ============================================
        # FINALIZE RESULTS
        # ============================================

        returns_series = pd.Series(

            daily_returns,

            name="Portfolio Returns"

        )

        nav_series = pd.Series(

            nav_history,

            name="Portfolio NAV"

        )

        # ============================================
        # CONSISTENCY CHECKS
        # ============================================

        assert len(
            nav_series
        ) >= len(
            returns_series
        )

        assert account.portfolio_value > 0

        assert np.isfinite(
            returns_series
        ).all()

        assert np.isfinite(
            nav_series
        ).all()

        # ============================================
        # PERFORMANCE ANALYTICS
        # ============================================

        analytics = PerformanceAnalytics()

        annual_return = (
            analytics.annual_return(
                returns_series
            )
        )

        annual_volatility = (
            analytics.annual_volatility(
                returns_series
            )
        )

        sharpe = (
            analytics.sharpe_ratio(
                returns_series
            )
        )

        sortino = (
            analytics.sortino_ratio(
                returns_series
            )
        )

        max_drawdown = (
            analytics.max_drawdown(
                returns_series
            )
        )

        calmar = (
            analytics.calmar_ratio(
                returns_series
            )
        )

        total_return = (

            nav_series.iloc[-1]

            /

            nav_series.iloc[0]

            -

            1.0

        )

        positive_returns = (

            returns_series[
                returns_series > 0
            ]

        )

        negative_returns = (

            returns_series[
                returns_series < 0
            ]

        )

        win_rate = (

            len(
                positive_returns
            )

            /

            len(
                returns_series
            )

            if len(
                returns_series
            ) > 0

            else 0.0

        )

        average_gain = (

            positive_returns.mean()

            if len(
                positive_returns
            ) > 0

            else 0.0

        )

        average_loss = (

            negative_returns.mean()

            if len(
                negative_returns
            ) > 0

            else 0.0

        )

        gross_profit = (
            positive_returns.sum()
        )

        gross_loss = abs(
            negative_returns.sum()
        )

        profit_factor = (

            gross_profit

            /

            gross_loss

            if gross_loss > 0

            else np.inf

        )

        performance = {

            "annual_return":
                annual_return,

            "annual_volatility":
                annual_volatility,

            "sharpe":
                sharpe,

            "sortino":
                sortino,

            "calmar":
                calmar,

            "max_drawdown":
                max_drawdown,

            "total_return":
                total_return,

            "final_nav":
                float(
                    nav_series.iloc[-1]
                ),

            "win_rate":
                win_rate,

            "average_gain":
                average_gain,

            "average_loss":
                average_loss,

            "profit_factor":
                profit_factor

        }

        # ============================================
        # ROLLING PERFORMANCE ANALYTICS
        # ============================================

        rolling_window = min(
            63,
            len(returns_series)
        )

        rolling_volatility = (

            returns_series

            .rolling(
                rolling_window
            )

            .std()

            *

            np.sqrt(
                TRADING_DAYS
            )

        )

        rolling_mean = (

            returns_series

            .rolling(
                rolling_window
            )

            .mean()

            *

            TRADING_DAYS

        )

        rolling_sharpe = (

            rolling_mean

            /

            rolling_volatility.replace(
                0,
                np.nan
            )

        )

        rolling_nav = (

            1.0

            +

            returns_series

        ).cumprod()

        rolling_peak = (
            rolling_nav.cummax()
        )

        rolling_drawdown = (

            rolling_nav

            /

            rolling_peak

            -

            1.0

        )

        rolling_performance = {

            "rolling_volatility":
                rolling_volatility,

            "rolling_sharpe":
                rolling_sharpe,

            "rolling_drawdown":
                rolling_drawdown,

            "rolling_nav":
                rolling_nav

        }
        
        # ============================================
        # BACKTEST OBJECT
        # ============================================

        return {

            "returns": returns_series,

            "nav": nav_series,

            "account": account,

            "regimes": regime_history,

            "turnover": turnover_history,

            "transaction_costs": transaction_cost_history,

            "trade_count": trade_count,

            "daily_returns": returns_series,

            "performance": performance,

            "rolling_performance": rolling_performance

        }

# ============================================================
# WALK FORWARD TEST
# ============================================================

def test_walk_forward_regime():

    loader = MarketDataLoader(

        assets=DEFAULT_ASSETS,

        period="10y"

    )

    returns = loader.load_returns()

    backtest = (

        WalkForwardOptimizer()

        .run(

            returns

        )

    )

    # ============================================
    # STRUCTURE
    # ============================================

    expected_keys = {

        "returns",

        "nav",

        "account",

        "regimes",

        "turnover",

        "transaction_costs",

        "trade_count",

        "daily_returns"

    }

    assert expected_keys.issubset(

        backtest.keys()

    )

    # ============================================
    # RETURN SERIES
    # ============================================

    assert len(

        backtest["returns"]

    ) > 0

    assert np.isfinite(

        backtest["returns"]

    ).all()

    # ============================================
    # NAV SERIES
    # ============================================

    assert len(

        backtest["nav"]

    ) > 0

    assert np.isfinite(

        backtest["nav"]

    ).all()

    assert (

        backtest["nav"]

        > 0

    ).all()

    # ============================================
    # ACCOUNT
    # ============================================

    account = backtest["account"]

    assert account.portfolio_value > 0

    # ============================================
    # REGIMES
    # ============================================

    assert len(

        backtest["regimes"]

    ) > 0

    # ============================================
    # COUNTERS
    # ============================================

    assert (

        backtest["trade_count"]

        >= 0

    )

    performance = backtest[
        "performance"
    ]

    assert (
        "annual_return"
        in performance
    )

    assert (
        "annual_volatility"
        in performance
    )

    assert (
        "sharpe"
        in performance
    )

    assert (
        "sortino"
        in performance
    )

    assert (
        "max_drawdown"
        in performance
    )

    assert (
        "calmar"
        in performance
    )

    assert (
        "total_return"
        in performance
    )

    assert (
        "final_nav"
        in performance
    )

    assert (
        "win_rate"
        in performance
    )

    assert (
        "average_gain"
        in performance
    )

    assert (
        "average_loss"
        in performance
    )

    assert (
        "profit_factor"
        in performance
    )

    assert performance[
        "final_nav"
    ] > 0

    assert (
        0.0
        <=
        performance[
            "win_rate"
        ]
        <=
        1.0
    )

    assert np.isfinite(

        list(
            performance.values()
        )
    ).all()
    
    rolling = backtest[
        "rolling_performance"
    ]
    
    assert (
        "rolling_volatility"
        in rolling
    )

    assert (
        "rolling_sharpe"
        in rolling
    )

    assert (
        "rolling_drawdown"
        in rolling
    )

    assert (
        "rolling_nav"
        in rolling
    )

    assert len(
        rolling["rolling_nav"]
    ) == len(
        backtest["returns"]
    )

    assert np.isfinite(

        rolling[
            "rolling_nav"
        ]

    ).all()

    logger.info(

        "Regime Walk Forward test passed"

    )

# ============================================================
# WALK FORWARD BACKTESTER
# ============================================================

class WalkForwardBacktester:

    def __init__(
        self,
        strategy,
        train_window=252,
        rebalance_frequency=21
    ):

        self.strategy = strategy

        self.train_window = (
            train_window
        )

        self.rebalance_frequency = (
            rebalance_frequency
        )

    def run(
        self,
        returns
    ):

        portfolio_returns = []

        dates = []

        weights = None

        for t in range(

            self.train_window,

            len(returns)

        ):

            if (

                weights is None

                or

                (
                    t
                    -
                    self.train_window
                )
                %
                self.rebalance_frequency
                ==
                0

            ):

                train_data = (

                    returns.iloc[
                        t-self.train_window:t
                    ]
                )

                weights = (

                    self.strategy
                    .generate(
                        train_data
                    )
                )

            next_return = (
                returns.iloc[t]
            )

            pnl = (

                np.asarray(weights)

                *

                next_return.values

            ).sum()

            portfolio_returns.append(
                pnl
            )

            dates.append(
                returns.index[t]
            )

        return pd.Series(

            portfolio_returns,

            index=dates
        )
    
def test_walk_forward():

    class DummyStrategy:

        def generate(
            self,
            window
        ):

            n = len(
                window.columns
            )

            return (
                np.ones(n)
                / n
            )

    returns = pd.DataFrame(

        np.random.normal(
            0,
            0.01,
            (1000, 5)
        )

    )

    result = (

        WalkForwardBacktester(
            DummyStrategy()
        )
        .run(
            returns
        )

    )

    assert len(result) > 0

    assert np.isfinite(
        result
    ).all()

    logger.info(
        "Walk Forward test passed"
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
# COVARIANCE ESTIMATION
# ============================================================

class CovarianceEstimator:

    @staticmethod
    def sample_covariance(
        returns
    ):

        covariance = (
            returns
            .cov()
            .values
        )

        return covariance

    @staticmethod
    def ledoit_wolf(
        returns
    ):

        returns = (
            returns
            .dropna()
        )

        lw = LedoitWolf()

        lw.fit(
            returns
        )

        covariance = (
            lw.covariance_
        )

        assert (
            covariance.shape[0]
            ==
            covariance.shape[1]
        ), (
            "Covariance matrix "
            "must be square"
        )

        assert (
            covariance.shape[0]
            ==
            len(returns.columns)
        ), (
            f"Covariance dimension "
            f"{covariance.shape[0]} "
            f"!= asset count "
            f"{len(returns.columns)}"
        )

        assert np.isfinite(
            covariance
        ).all(), (
            "Non-finite values "
            "in covariance matrix"
        )

        return covariance
    

# ============================================================
# COVARIANCE ESTIMATOR TEST
# ============================================================

def test_covariance_estimator():

    returns = pd.DataFrame(

        np.random.normal(
            0,
            0.01,
            (500, 10)
        )
    )

    cov = (
        CovarianceEstimator
        .ledoit_wolf(
            returns
        )
    )

    assert cov.shape == (
        10,
        10
    )

    assert np.isfinite(
        cov
    ).all()

    logger.info(
        "Covariance estimator test passed"
    )

# ============================================================
# FULL HRP
# ============================================================

class HRPOptimizer:

    def correlation_distance(
        self,
        corr
    ):

        corr = np.asarray(
            corr,
            dtype=float
        )

        corr = np.nan_to_num(
            corr
        )

        corr = np.clip(
            corr,
            -1.0,
            1.0
        )

        distance = np.sqrt(
            np.maximum(
                0.0,
                0.5 * (
                    1.0 - corr
                )
            )
        )

        np.fill_diagonal(
            distance,
            0.0
        )

        return distance

    def get_quasi_diag(
        self,
        linkage_matrix
    ):

        link = linkage_matrix.astype(int)

        sort_ix = [
            int(link[-1, 0]),
            int(link[-1, 1])
        ]

        num_items = int(
            link[-1, 3]
        )

        while any(
            i >= num_items
            for i in sort_ix
        ):

            new_sort = []

            for i in sort_ix:

                if i < num_items:

                    new_sort.append(i)

                else:

                    cluster = (
                        link[
                            i - num_items
                        ]
                    )

                    new_sort.extend([
                        int(cluster[0]),
                        int(cluster[1])
                    ])

            sort_ix = new_sort

        return sort_ix

    def get_cluster_var(
        self,
        covariance,
        cluster_items
    ):

        cov_slice = covariance[
            np.ix_(
                cluster_items,
                cluster_items
            )
        ]

        inv_diag = (
            1.0
            /
            np.diag(cov_slice)
        )

        weights = (
            inv_diag
            /
            inv_diag.sum()
        )

        cluster_var = (
            weights.T
            @ cov_slice
            @ weights
        )

        return float(
            cluster_var
        )

    def recursive_bisection(
        self,
        covariance,
        sorted_ix
    ):

        weights = pd.Series(
            1.0,
            index=sorted_ix
        )

        clusters = [
            sorted_ix
        ]

        while len(clusters) > 0:

            clusters = [

                cluster[i:j]

                for cluster in clusters

                for i, j in (
                    (
                        0,
                        len(cluster) // 2
                    ),
                    (
                        len(cluster) // 2,
                        len(cluster)
                    )
                )

                if len(cluster) > 1
            ]

            for i in range(
                0,
                len(clusters),
                2
            ):

                if i + 1 >= len(clusters):
                    continue

                cluster_1 = (
                    clusters[i]
                )

                cluster_2 = (
                    clusters[i + 1]
                )

                var_1 = (
                    self.get_cluster_var(
                        covariance,
                        cluster_1
                    )
                )

                var_2 = (
                    self.get_cluster_var(
                        covariance,
                        cluster_2
                    )
                )

                alpha = (
                    1.0
                    -
                    (
                        var_1
                        /
                        (
                            var_1
                            + var_2
                        )
                    )
                )

                weights[
                    cluster_1
                ] *= alpha

                weights[
                    cluster_2
                ] *= (
                    1.0 - alpha
                )

        return weights

    def optimize(
        self,
        covariance,
        labels=None
    ):

        covariance = np.asarray(
            covariance,
            dtype=float
        )

        n_assets = len(
            covariance
        )

        if labels is None:

            labels = list(
                range(n_assets)
            )

        std = np.sqrt(
            np.diag(covariance)
        )

        corr = (
            covariance
            /
            np.outer(
                std,
                std
            )
        )

        corr = np.nan_to_num(
            corr
        )

        corr = np.clip(
            corr,
            -1.0,
            1.0
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
            method="single"
        )

        sorted_ix = (
            self.get_quasi_diag(
                link
            )
        )

        hrp_weights = (
            self.recursive_bisection(
                covariance,
                sorted_ix
            )
        )

        hrp_weights = (
            hrp_weights
            /
            hrp_weights.sum()
        )

        weights = (
            hrp_weights
            .sort_index()
            .values
        )

        return pd.Series(
            weights,
            index=labels
        )
    
# ============================================================
# HRP TEST
# ============================================================

def test_hrp():

    cov = np.array([

        [0.04, 0.01, 0.00],

        [0.01, 0.09, 0.02],

        [0.00, 0.02, 0.16]

    ])

    labels = [
        "SPY",
        "TLT",
        "GLD"
    ]

    weights = (
        HRPOptimizer()
        .optimize(
            cov,
            labels=labels
        )
    )

    constraint_result = (
        PortfolioConstraints
        .enforce(weights.values)
    )

    weights = pd.Series(
        constraint_result["weights"],
        index=weights.index
    )

    cash = (
        constraint_result["cash"]
    )

    assert (
        abs(
            weights.sum()
            + cash
            - 1.0
        )
        < 1e-6
    )

    assert (
        (weights >= 0).all()
    )
    assert (
        len(weights)
        == 3
    )

    logger.info("HRP test passed")
    logger.info("HRP weights:\n%s", weights)
    
# ============================================================
# UNIVERSE TEST
# ============================================================

def test_asset_universe():

    loader = MarketDataLoader(
        DEFAULT_ASSETS,
        "1y"
    )

    returns = (
        loader.load_returns()
    )

    assert not returns.empty

    assert (
        returns.shape[1]
        ==
        len(DEFAULT_ASSETS)
    )

    assert np.isfinite(
        returns.values
    ).all()

    logger.info(
        "Universe test passed"
    )

    logger.debug(
    "Assets: %s",
    returns.columns.tolist()
)
    
# ============================================================
# LIVE HRP TEST
# ============================================================

def test_hrp_live():

    loader = MarketDataLoader(
        DEFAULT_ASSETS,
        "2y"
    )

    returns = (
        loader.load_returns()
    )

    cov = (
    CovarianceEstimator
    .ledoit_wolf(
        returns
    )
)

    weights = (
    HRPOptimizer()
    .optimize(
        cov,
        labels=returns.columns
    )
)

    print(weights)

    print(
        "Weight Sum:",
        weights.sum()
    )

    assert np.isclose(
        weights.sum(),
        1.0
    )

    assert (
        weights >= 0
    ).all()

    logger.info(
        "Live HRP test passed"
    )

class TurnoverControl:

    @staticmethod
    def turnover(
        old_weights,
        new_weights
    ):

        return np.sum(
            np.abs(
                new_weights
                -
                old_weights
            )
        )
    
def test_turnover():

    old = np.array([
        0.50,
        0.50
    ])

    new = np.array([
        0.40,
        0.60
    ])

    turnover = (
        TurnoverControl
        .turnover(
            old,
            new
        )
    )

    assert np.isclose(
        turnover,
        0.20
    )

    logger.info(
        "Turnover test passed"
    )

# ============================================================
# ANALYTICS TEST
# ============================================================

def test_performance_analytics():

    returns = pd.Series(

        np.random.normal(
            0.0005,
            0.01,
            2000
        )

    )

    analytics = (
        PerformanceAnalytics()
    )

    metrics = (
        analytics.summary(
            returns
        )
    )

    assert np.isfinite(
        list(metrics.values())
    ).all()

    logger.info(
        "Performance analytics test passed"
    )

# ============================================================
# FULL SYSTEM TEST
# ============================================================

def test_full_system():

    loader = MarketDataLoader(

        assets=DEFAULT_ASSETS,

        period="10y"

    )

    returns = (
        loader.load_returns()
    )

    result = (

        WalkForwardOptimizer()
        .run(
            returns
        )

    )

    analytics = (
        PerformanceAnalytics()
    )

    metrics = (

    analytics.summary(

        result["returns"]

    )

)

    print("\n========== RESULTS ==========")

    for k, v in metrics.items():

        print(
            k,
            ":",
            round(float(v), 4)
        )

    print("=============================\n")

    assert np.isfinite(
        list(metrics.values())
    ).all()

    logger.info(
        "Full system test passed"
    )

# ============================================================
# ASSET ALIGNMENT TEST
# ============================================================

def test_asset_alignment():

    asset_order = [

        "DBC",
        "GLD",
        "HYG",
        "IEF",
        "IWM",
        "LQD",
        "QQQ",
        "SHY",
        "SLV",
        "SPY",
        "TLT",
        "VEA",
        "VNQ",
        "VWO"

    ]

    risk_budget = np.array(

        [

            REGIME_RISK_BUDGETS[
                "bull"
            ][asset]

            for asset
            in asset_order

        ],

        dtype=float

    )

    assert len(
        risk_budget
    ) == len(
        asset_order
    )

    assert np.isclose(
        risk_budget.sum(),
        1.0,
        atol=1e-6
    )

    logger.info(
        "Asset alignment test passed"
    )

# ============================================================
# HIDDEN MARKOV REGIME MODEL
# ============================================================

class HMMRegimeModel:

    def __init__(
        self,
        n_states=3
    ):

        self.n_states = n_states

        self.model = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=100,
            tol=1e-4,
            random_state=42
        )

    def fit(
        self,
        returns
    ):

        X = np.asarray(
            returns,
            dtype=float
        )

        X = X.reshape(
            -1,
            1
        )

        std = np.std(X)

        if std < 1e-8:

            raise ValueError(
                "Insufficient variance "
                "for HMM fit"
            )

        X = (
            X - np.mean(X)
        ) / std

        self.model.fit(X)

        return self

    def predict_states(
        self,
        returns
    ):

        X = np.asarray(
            returns,
            dtype=float
        )

        X = X.reshape(
            -1,
            1
        )

        std = np.std(X)

        if std < 1e-8:

            return np.zeros(
                len(X),
                dtype=int
            )

        X = (
            X - np.mean(X)
        ) / std

        return self.model.predict(X)

    def current_state(
        self,
        returns
    ):

        states = self.predict_states(
            returns
        )

        return int(
            states[-1]
        )

    def state_volatility_rank(
        self,
        returns
    ):

        returns = np.asarray(
            returns,
            dtype=float
        )

        states = self.predict_states(
            returns
        )

        vols = {}

        for state in range(
            self.n_states
        ):

            state_returns = (

                returns[
                    states == state
                ]

            )

            if len(state_returns) == 0:

                vols[state] = 0.0

            else:

                vols[state] = float(
                    np.std(
                        state_returns
                    )
                )

        ordered = sorted(

            vols.items(),

            key=lambda x: x[1]

        )

        return {

            state: rank

            for rank, (
                state,
                _
            ) in enumerate(
                ordered
            )

        }

    def detect_regime(
        self,
        returns
    ):

        try:

            self.fit(
                returns
            )

            current_state = (
                self.current_state(
                    returns
                )
            )

            state_ranks = (
                self.state_volatility_rank(
                    returns
                )
            )

            return (

                HMMRegimeMapper
                .map_state(
                    current_state,
                    state_ranks
                )

            )

        except Exception:

            return "neutral"


class HMMRegimeMapper:

    @staticmethod
    def map_state(
        state,
        state_vol_rank
    ):

        if state_vol_rank[state] == 0:

            return "bull"

        if state_vol_rank[state] == 1:

            return "neutral"

        return "crisis"


# ============================================================
# HMM TESTS
# ============================================================

def test_hmm_regime():

    returns = np.concatenate([

        np.random.normal(
            0.001,
            0.01,
            1000
        ),

        np.random.normal(
            -0.0005,
            0.03,
            1000
        ),

        np.random.normal(
            0.0002,
            0.015,
            1000
        )

    ])

    model = HMMRegimeModel()

    model.fit(
        returns
    )

    states = (
        model.predict_states(
            returns
        )
    )

    assert len(
        states
    ) == len(
        returns
    )

    assert np.isfinite(
        states
    ).all()

    logger.info(
        "HMM regime test passed"
    )


def test_hmm_state_ranking():

    returns = np.concatenate([

        np.random.normal(
            0.001,
            0.01,
            1000
        ),

        np.random.normal(
            -0.002,
            0.04,
            1000
        ),

        np.random.normal(
            0.0005,
            0.02,
            1000
        )

    ])

    model = HMMRegimeModel()

    model.fit(
        returns
    )

    ranks = (
        model.state_volatility_rank(
            returns
        )
    )

    assert len(
        ranks
    ) == 3

    assert set(
        ranks.values()
    ) == {0, 1, 2}

    logger.info(
        "HMM state ranking test passed"
    )


def test_hmm_regime_detection():

    returns = np.random.normal(
        0.0005,
        0.02,
        3000
    )

    model = HMMRegimeModel()

    regime = (
        model.detect_regime(
            returns
        )
    )

    assert regime in [
        "bull",
        "neutral",
        "crisis"
    ]

    logger.info(
        "HMM regime detection test passed"
    )
                
# ============================================================
# FORECAST TESTS
# ============================================================

def test_expected_return_forecaster():

    prices = pd.DataFrame(

        np.cumprod(

            1 +

            np.random.normal(
                0.0005,
                0.01,
                (1000, len(DEFAULT_ASSETS))
            ),

            axis=0

        ),

        columns=DEFAULT_ASSETS

    )

    forecasts = (

        ExpectedReturnForecaster()
        .forecast(
            prices
        )

    )

    assert len(
        forecasts
    ) == len(
        DEFAULT_ASSETS
    )

    assert np.isfinite(
        forecasts
    ).all()

    logger.info(
        "Expected return forecaster test passed"
    )

    
# ============================================================
# BLACK-LITTERMAN TEST
# ============================================================

def test_black_litterman():

    covariance = np.eye(
        len(DEFAULT_ASSETS)
    )

    market_weights = (

        np.ones(
            len(DEFAULT_ASSETS)
        )

        /

        len(DEFAULT_ASSETS)

    )

    views = np.random.normal(

        0.08,
        0.03,
        len(DEFAULT_ASSETS)

    )

    posterior = (

        BlackLittermanModel()
        .posterior_returns(

            covariance,

            market_weights,

            views

        )

    )

    assert len(
        posterior
    ) == len(
        DEFAULT_ASSETS
    )

    assert np.isfinite(
        posterior
    ).all()

    logger.info(
        "Black-Litterman test passed"
    )

#================================
# risk contribution test
# ==============================
    
def test_risk_contributions():

    covariance = np.eye(5)

    weights = np.array([

        0.20,
        0.20,
        0.20,
        0.20,
        0.20

    ])

    rc = (

        RiskContributionAnalytics
        .risk_contribution_pct(
            weights,
            covariance
        )

    )

    assert np.isclose(

        rc.sum(),

        1.0,

        atol=1e-6

    )

    assert np.isfinite(
        rc
    ).all()

    logger.info(
        "Risk contribution test passed"
    )

def test_risk_budget_report():

    covariance = np.eye(4)

    weights = np.array([

        0.25,
        0.25,
        0.25,
        0.25

    ])

    target_budget = np.array([

        0.25,
        0.25,
        0.25,
        0.25

    ])

    report = (

        RiskBudgetReport
        .create(

            ["A", "B", "C", "D"],

            weights,

            covariance,

            target_budget

        )

    )

    assert len(
        report
    ) == 4

    assert (
        "Actual"
        in report.columns
    )

    logger.info(
        "Risk budget report test passed"
    )

# ============================================================
# PERFORMANCE ATTRIBUTION
# ============================================================

class PortfolioAttribution:

    @staticmethod
    def contribution(
        weights,
        returns
    ):

        return (
            weights
            * returns
        )

    @staticmethod
    def contribution_pct(
        weights,
        returns
    ):

        contrib = (

            PortfolioAttribution
            .contribution(
                weights,
                returns
            )

        )

        total = contrib.sum()

        if np.isclose(
            total,
            0.0
        ):

            return np.zeros(
                len(contrib)
            )

        return (
            contrib
            / total
        )

    @staticmethod
    def report(
        asset_names,
        weights,
        returns
    ):

        contrib = (

            PortfolioAttribution
            .contribution(
                weights,
                returns
            )

        )

        pct = (

            PortfolioAttribution
            .contribution_pct(
                weights,
                returns
            )

        )

        return pd.DataFrame({

            "Asset":
                asset_names,

            "Weight":
                weights,

            "Return":
                returns,

            "Contribution":
                contrib,

            "ContributionPct":
                pct

        })
    
def test_performance_attribution():

    weights = np.array([
        0.25,
        0.25,
        0.25,
        0.25
    ])

    returns = np.array([
        0.10,
        0.05,
        -0.02,
        0.03
    ])

    report = (

        PortfolioAttribution
        .report(

            ["A", "B", "C", "D"],

            weights,

            returns

        )

    )

    assert len(report) == 4

    assert (
        "Contribution"
        in report.columns
    )

    assert (
        "ContributionPct"
        in report.columns
    )

    logger.info(
        "Performance attribution test passed"
    )

# ============================================================
# TRANSACTION COST ATTRIBUTION
# ============================================================

class TransactionCostAnalytics:

    @staticmethod
    def turnover(
        old_weights,
        new_weights
    ):

        return float(

            np.abs(
                new_weights
                - old_weights
            ).sum()

        )

    @staticmethod
    def transaction_cost(
        turnover,
        cost_bps=10
    ):

        return (

            turnover
            *
            cost_bps
            /
            10000.0

        )

    @staticmethod
    def net_return(
        gross_return,
        transaction_cost
    ):

        return (
            gross_return
            -
            transaction_cost
        )

    @staticmethod
    def report(
        old_weights,
        new_weights,
        gross_return,
        cost_bps=10
    ):

        turnover = (

            TransactionCostAnalytics
            .turnover(
                old_weights,
                new_weights
            )

        )

        cost = (

            TransactionCostAnalytics
            .transaction_cost(
                turnover,
                cost_bps
            )

        )

        net = (

            TransactionCostAnalytics
            .net_return(
                gross_return,
                cost
            )

        )

        return {

            "turnover":
                turnover,

            "cost":
                cost,

            "gross_return":
                gross_return,

            "net_return":
                net

        }
    
def test_transaction_cost_analytics():

    old_weights = np.array([
        0.25,
        0.25,
        0.25,
        0.25
    ])

    new_weights = np.array([
        0.40,
        0.20,
        0.20,
        0.20
    ])

    report = (

        TransactionCostAnalytics
        .report(

            old_weights,

            new_weights,

            gross_return=0.10,

            cost_bps=10

        )

    )

    assert report["turnover"] > 0

    assert report["cost"] > 0

    assert (

        report["net_return"]

        <

        report["gross_return"]

    )

    logger.info(
        "Transaction cost test passed"
    )

# ============================================================
# REGIME TRANSITION ANALYTICS
# ============================================================

class RegimeTransitionAnalytics:

    @staticmethod
    def transition_matrix(
        hmm_model
    ):

        return np.asarray(
            hmm_model.model.transmat_,
            dtype=float
        )

    @staticmethod
    def persistence(
        hmm_model
    ):

        matrix = (

            RegimeTransitionAnalytics
            .transition_matrix(
                hmm_model
            )

        )

        return np.diag(
            matrix
        )

    @staticmethod
    def next_state_probabilities(
        hmm_model,
        current_state
    ):

        matrix = (

            RegimeTransitionAnalytics
            .transition_matrix(
                hmm_model
            )

        )

        return matrix[
            current_state
        ]

    @staticmethod
    def expected_duration(
        hmm_model
    ):

        persistence = (

            RegimeTransitionAnalytics
            .persistence(
                hmm_model
            )

        )

        duration = {}

        for state, p in enumerate(
            persistence
        ):

            if p >= 0.999:

                duration[state] = np.inf

            else:

                duration[state] = (
                    1.0
                    /
                    (1.0 - p)
                )

        return duration
    
def test_transition_matrix():

    returns = np.concatenate([

        np.random.normal(
            0.001,
            0.01,
            1000
        ),

        np.random.normal(
            -0.002,
            0.04,
            1000
        ),

        np.random.normal(
            0.0005,
            0.02,
            1000
        )

    ])

    model = HMMRegimeModel()

    model.fit(
        returns
    )

    matrix = (

        RegimeTransitionAnalytics
        .transition_matrix(
            model
        )

    )

    assert matrix.shape == (
        model.n_states,
        model.n_states
    )

    assert np.allclose(
        matrix.sum(axis=1),
        1.0,
        atol=1e-6
    )

    logger.info(
        "Transition matrix test passed"
    )

def test_regime_persistence():

    returns = np.concatenate([

        np.random.normal(
            0.001,
            0.01,
            1000
        ),

        np.random.normal(
            -0.002,
            0.04,
            1000
        ),

        np.random.normal(
            0.0005,
            0.02,
            1000
        )

    ])

    model = HMMRegimeModel()

    model.fit(
        returns
    )

    persistence = (

        RegimeTransitionAnalytics
        .persistence(
            model
        )

    )

    assert len(
        persistence
    ) == model.n_states

    assert (
        persistence >= 0
    ).all()

    logger.info(
        "Persistence test passed"
    )

def test_expected_duration():

    returns = np.concatenate([

        np.random.normal(
            0.001,
            0.01,
            1000
        ),

        np.random.normal(
            -0.002,
            0.04,
            1000
        ),

        np.random.normal(
            0.0005,
            0.02,
            1000
        )

    ])

    model = HMMRegimeModel()

    model.fit(
        returns
    )

    duration = (

        RegimeTransitionAnalytics
        .expected_duration(
            model
        )

    )

    assert len(
        duration
    ) == model.n_states

    logger.info(
        "Expected duration test passed"
    )

# ============================================================
# REGIME PROBABILITY ENGINE
# ============================================================

class RegimeProbabilityEngine:

    @staticmethod
    def crisis_probability(
        hmm_model,
        current_state,
        state_rank
    ):

        probs = (

            RegimeTransitionAnalytics
            .next_state_probabilities(
                hmm_model,
                current_state
            )

        )

        crisis_state = None

        for state, rank in (
            state_rank.items()
        ):

            if rank == 2:

                crisis_state = state
                break

        return float(
            probs[crisis_state]
        )

    @staticmethod
    def leverage_multiplier(
        crisis_probability
    ):

        if crisis_probability > 0.60:

            return 0.50

        if crisis_probability > 0.40:

            return 0.75

        if crisis_probability > 0.20:

            return 0.90

        return 1.00
    
def test_regime_probability_engine():

    returns = np.concatenate([

        np.random.normal(
            0.001,
            0.01,
            1000
        ),

        np.random.normal(
            -0.002,
            0.04,
            1000
        ),

        np.random.normal(
            0.0005,
            0.02,
            1000
        )

    ])

    model = HMMRegimeModel()

    model.fit(
        returns
    )

    current_state = (
        model.current_state(
            returns
        )
    )

    ranks = (
        model.state_volatility_rank(
            returns
        )
    )

    p_crisis = (

        RegimeProbabilityEngine
        .crisis_probability(

            model,

            current_state,

            ranks

        )

    )

    assert (
        0.0
        <=
        p_crisis
        <=
        1.0
    )

    multiplier = (

        RegimeProbabilityEngine
        .leverage_multiplier(
            p_crisis
        )

    )

    assert (
        0.0
        <
        multiplier
        <=
        1.0
    )

    logger.info(
        "Regime probability test passed"
    )

# ============================================================
# REGIME_EXPECTED_RETURNS
# ============================================================
    
class RegimeForecastCombiner:

    @staticmethod
    def combine(
        regime_returns,
        next_state_probs
    ):

        assets = (
            list(
                regime_returns[
                    next(
                        iter(
                            regime_returns
                        )
                    )
                ].index
            )
        )

        forecast = pd.Series(

            0.0,

            index=assets

        )

        for state, mu in (
            regime_returns.items()
        ):

            forecast += (
                next_state_probs[
                    state
                ]
                *
                mu
            )

        return forecast
    
# ============================================================
# REGIME EXPECTED RETURNS
# ============================================================

class RegimeExpectedReturnModel:

    @staticmethod
    def estimate(
        returns,
        states,
        n_states
    ):

        regime_returns = {}

        for state in range(
            n_states
        ):

            mask = (
                states == state
            )

            if mask.sum() == 0:
                continue

            regime_returns[state] = (

                returns.loc[
                    mask
                ]
                .mean()

            )

        return regime_returns
        
def test_regime_expected_returns():

    returns = pd.DataFrame(

        np.random.normal(
            0,
            0.01,
            (3000, 5)
        ),

        columns=[
            "A",
            "B",
            "C",
            "D",
            "E"
        ]

    )

    states = np.repeat(
        [0, 1, 2],
        1000
    )

    result = (

        RegimeExpectedReturnModel
        .estimate(

            returns,

            states,

            3

        )

    )

    assert len(
        result
    ) == 3

    logger.info(
        "Regime expected returns test passed"
    )

def test_regime_forecast_combiner():

    regime_returns = {

        0: pd.Series(
            [0.10, 0.05]
        ),

        1: pd.Series(
            [0.04, 0.03]
        ),

        2: pd.Series(
            [-0.10, -0.05]
        )

    }

    probs = np.array([
        0.50,
        0.30,
        0.20
    ])

    forecast = (

        RegimeForecastCombiner
        .combine(

            regime_returns,

            probs

        )

    )

    assert len(
        forecast
    ) == 2

    assert np.isfinite(
        forecast
    ).all()

    logger.info(
        "Regime forecast combiner test passed"
    )

# ============================================================
# REGIME BLACK-LITTERMAN
# ============================================================

class RegimeBlackLitterman:

    @staticmethod
    def posterior_forecast(
        covariance,
        regime_forecast,
        tau=0.05
    ):

        n_assets = len(
            regime_forecast
        )

        market_weights = np.ones(
            n_assets
        ) / n_assets

        model = (
            BlackLittermanModel()
        )

        posterior = (

            model.posterior_returns(

                covariance,

                market_weights,

                regime_forecast.values

            )

        )

        return pd.Series(

            posterior,

            index=regime_forecast.index

        )
    
def test_regime_black_litterman():

    covariance = np.eye(5)

    forecast = pd.Series(

        [0.10, 0.05, 0.02, 0.01, -0.03],

        index=[
            "A",
            "B",
            "C",
            "D",
            "E"
        ]

    )

    posterior = (

        RegimeBlackLitterman
        .posterior_forecast(

            covariance,

            forecast

        )

    )

    assert len(
        posterior
    ) == 5

    assert np.isfinite(
        posterior
    ).all()

    logger.info(
        "Regime Black-Litterman test passed"
    )
    
# ============================================================
# FORWARD RISK ANALYZER
# ============================================================

class MonteCarloBacktestAnalyzer:

    def __init__(

        self,

        horizon=252,

        simulations=1000

    ):

        self.horizon = horizon

        self.simulations = simulations

    def run(

        self,

        transition_matrix,

        start_state,

        state_return_map

    ):

        # ============================================
        # SIMULATE REGIME PATHS
        # ============================================

        paths = (

            RegimeMonteCarlo

            .simulate_states(

                transition_matrix,

                start_state,

                horizon=self.horizon,

                n_sims=self.simulations

            )

        )

        # ============================================
        # SIMULATE PORTFOLIO RETURNS
        # ============================================

        terminal_returns = (

            RegimePortfolioSimulator

            .simulate_returns(

                paths,

                state_return_map

            )

        )

        # ============================================
        # SUMMARY STATISTICS
        # ============================================

        summary = (

            RegimeSimulationAnalytics

            .summary(

                terminal_returns

            )

        )

        # ============================================
        # FORWARD RISK METRICS
        # ============================================

        risk_metrics = (

            ForwardRiskMetrics

            .summarize(

                terminal_returns

            )

        )

        return {

            "paths": paths,

            "terminal_returns": terminal_returns,

            "summary": summary,

            "risk_metrics": risk_metrics

        }


# ============================================================
# FORWARD RISK ANALYZER TEST
# ============================================================

def test_forward_risk_analyzer():

    transition = np.array([

        [0.90, 0.08, 0.02],

        [0.10, 0.80, 0.10],

        [0.05, 0.15, 0.80]

    ])

    analyzer = (

        MonteCarloBacktestAnalyzer()

    )

    result = (

        analyzer.run(

            transition_matrix=transition,

            start_state=0,

            state_return_map={

                0: 0.0010,

                1: 0.0003,

                2: -0.0005

            }

        )

    )

    assert "paths" in result

    assert "terminal_returns" in result

    assert "summary" in result

    assert "risk_metrics" in result

    assert "expected_return" in (

        result["risk_metrics"]

    )

    assert "volatility" in (

        result["risk_metrics"]

    )

    assert "best_case" in (

        result["risk_metrics"]

    )

    assert "worst_case" in (

        result["risk_metrics"]

    )

    assert result["paths"].shape[0] == 1000

    assert len(

        result["terminal_returns"]

    ) == 1000

    assert "mean_terminal" in result["summary"]

    logger.info(

        "Forward risk analyzer test passed"

    )


# ============================================================
# REGIME MONTE CARLO TEST
# ============================================================

def test_regime_monte_carlo():

    transition = np.array([

        [0.90, 0.08, 0.02],

        [0.10, 0.80, 0.10],

        [0.05, 0.15, 0.80]

    ])

    paths = (

        RegimeMonteCarlo

        .simulate_states(

            transition,

            start_state=0,

            horizon=50,

            n_sims=100

        )

    )

    assert paths.shape[0] == 100

    logger.info(

        "Regime Monte Carlo test passed"

    )

# ============================================================
# FORWARD RISK METRICS TEST
# ============================================================

def test_forward_risk_metrics():

    simulations = np.random.normal(

        0.08,

        0.15,

        1000

    )

    metrics = (

        ForwardRiskMetrics

        .summarize(

            simulations

        )

    )

    assert "expected_return" in metrics

    assert "volatility" in metrics

    assert "best_case" in metrics

    assert "worst_case" in metrics

    assert "VaR95" in metrics

    assert "CVaR95" in metrics

    assert "probability_of_loss" in metrics

    assert "sharpe" in metrics

    assert "sortino" in metrics

    assert "omega" in metrics

    assert np.isfinite(

        metrics["sharpe"]

    )

    assert (

        np.isfinite(

            metrics["sortino"]

        )

        or

        np.isnan(

            metrics["sortino"]

        )

    )

    assert (

        np.isfinite(

            metrics["omega"]

        )

        or

        np.isinf(

            metrics["omega"]

        )

    )

    assert (

        0.0

        <=

        metrics["probability_of_loss"]

        <=

        1.0

    )

    assert np.isfinite(

        list(

            metrics.values()

        )

    ).all()

    logger.info(

        "Forward risk metrics test passed"

    )

# ============================================================
# SCENARIO SHOCK ENGINE
# ============================================================

class ScenarioShockEngine:

    @staticmethod
    def apply(

        portfolio_returns,

        shock

    ):

        portfolio_returns = np.asarray(

            portfolio_returns,

            dtype=float

        )

        shocked = (

            portfolio_returns

            + shock

        )

        return shocked
    
# ============================================================
# SCENARIO SHOCK TEST
# ============================================================

def test_scenario_shock_engine():

    returns = np.random.normal(

        0.0005,

        0.01,

        252

    )

    shocked = (

        ScenarioShockEngine

        .apply(

            returns,

            shock=-0.02

        )

    )

    assert len(

        shocked

    ) == len(

        returns

    )

    assert (

        shocked.mean()

        <

        returns.mean()

    )

    logger.info(

        "Scenario shock engine test passed"

    )

def test_regime_portfolio_simulator():

    paths = np.random.randint(

        0,
        3,
        (100, 50)

    )

    returns = (

        RegimePortfolioSimulator
        .simulate_returns(

            paths,

            {

                0: 0.001,
                1: 0.0003,
                2: -0.0005

            }

        )

    )

    assert len(
        returns
    ) == 100

    logger.info(
        "Regime portfolio simulator test passed"
    )

def test_regime_simulation_analytics():

    sims = np.random.normal(
        0.10,
        0.20,
        1000
    )

    stats = (

        RegimeSimulationAnalytics
        .summary(
            sims
        )

    )

    assert (
        "mean_terminal"
        in stats
    )

    logger.info(
        "Regime simulation analytics test passed"
    )

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
    
def test_drawdown_forecast():

    returns = np.random.normal(
        0.0005,
        0.01,
        500
    )

    dd = (

        DrawdownForecastEngine
        .max_drawdown(
            returns
        )

    )

    assert dd <= 0

    logger.info(
        "Drawdown forecast test passed"
    )

def test_drawdown_probability():

    drawdowns = np.random.uniform(
        -0.40,
        0.0,
        1000
    )

    stats = (

        DrawdownProbabilityAnalytics
        .summary(
            drawdowns
        )

    )

    assert (
        "prob_20pct"
        in stats
    )

    logger.info(
        "Drawdown probability test passed"
    )

# ============================================================
# PORTFOLIO REPORT GENERATOR
# ============================================================

class PortfolioReportGenerator:

    @staticmethod
    def create(
        optimizer_result,
        performance_stats,
        drawdown_stats,
        transition_stats,
        crisis_probability=None,
        leverage_multiplier=None
    ):

        report = {

            # --------------------------------
            # PORTFOLIO
            # --------------------------------

            "regime":

                optimizer_result.get(
                    "regime"
                ),

            "weights":

                optimizer_result.get(
                    "weights"
                ),

            "cash":

                optimizer_result.get(
                    "cash"
                ),

            # --------------------------------
            # FORECASTS
            # --------------------------------

            "forecasts":

                optimizer_result.get(
                    "forecasts"
                ),

            "expected_returns":

                optimizer_result.get(
                    "expected_returns"
                ),

            # --------------------------------
            # RISK
            # --------------------------------

            "risk_report":

                optimizer_result.get(
                    "risk_report"
                ),

            "crisis_probability":

                crisis_probability,

            "leverage_multiplier":

                leverage_multiplier,

            # --------------------------------
            # PERFORMANCE
            # --------------------------------

            "performance":

                performance_stats,

            # --------------------------------
            # DRAWDOWNS
            # --------------------------------

            "drawdown":

                drawdown_stats,

            # --------------------------------
            # REGIME
            # --------------------------------

            "transition":

                transition_stats

        }

        return report
    
class PortfolioReportFormatter:

    @staticmethod
    def print_report(
        report
    ):

        print()

        print("=" * 60)
        print("PORTFOLIO REPORT")
        print("=" * 60)

        print()

        print(
            "Regime:",
            report["regime"]
        )

        print(
            "Crisis Probability:",
            report[
                "crisis_probability"
            ]
        )

        print(
            "Leverage Multiplier:",
            report[
                "leverage_multiplier"
            ]
        )

        print()

        if report["performance"]:

            for key, value in (
                report[
                    "performance"
                ].items()
            ):

                print(
                    f"{key}: "
                    f"{value:.4f}"
                )

        print()

        if report["drawdown"]:

            print(
                "Drawdown Statistics"
            )

            for key, value in (
                report[
                    "drawdown"
                ].items()
            ):

                print(
                    f"{key}: "
                    f"{value:.4f}"
                )

        print()

        print("=" * 60)

def test_portfolio_report_generator():

    report = (

        PortfolioReportGenerator
        .create(

            optimizer_result={

                "regime":
                    "neutral",

                "weights":
                    np.array([
                        0.5,
                        0.5
                    ]),

                "cash":
                    0.0,

                "risk_report":
                    pd.DataFrame()

            },

            performance_stats={

                "sharpe":
                    1.2

            },

            drawdown_stats={

                "prob_20pct":
                    0.08

            },

            transition_stats={

                "duration":
                    15

            },

            crisis_probability=0.12,

            leverage_multiplier=0.88

        )

    )

    assert (
        report["regime"]
        ==
        "neutral"
    )

    logger.info(
        "Portfolio report generator test passed"
    )

# ============================================================
# PORTFOLIO VISUALIZATION
# ============================================================

class PortfolioVisualizer:

    @staticmethod
    def allocation_pie_chart(
        asset_order,
        weights
    ):

        weights = np.asarray(
            weights,
            dtype=float
        )

        mask = weights > 0

        plt.figure(
            figsize=(8, 8)
        )

        plt.pie(

            weights[mask],

            labels=np.array(
                asset_order
            )[mask],

            autopct="%1.1f%%"

        )

        plt.title(
            "Portfolio Allocation"
        )

        plt.tight_layout()

        plt.show()

    @staticmethod
    def risk_contribution_chart(
        risk_report
    ):

        plt.figure(
            figsize=(12, 6)
        )

        x = np.arange(
            len(risk_report)
        )

        width = 0.35

        plt.bar(

            x - width / 2,

            risk_report[
                "Target"
            ],

            width,

            label="Target"

        )

        plt.bar(

            x + width / 2,

            risk_report[
                "Actual"
            ],

            width,

            label="Actual"

        )

        plt.xticks(

            x,

            risk_report.index,

            rotation=45

        )

        plt.ylabel(
            "Risk Contribution"
        )

        plt.title(
            "Risk Budget Attribution"
        )

        plt.legend()

        plt.tight_layout()

        plt.show()

def test_risk_contribution_chart():

    report = pd.DataFrame({

        "Target": np.repeat(
            0.1,
            10
        ),

        "Actual": np.repeat(
            0.1,
            10
        )

    })

    PortfolioVisualizer \
        .risk_contribution_chart(
            report
        )

    logger.info(
        "Risk contribution chart test passed"
    )

# ============================================================
# ALLOCATION PIE CHART TEST
# ============================================================

def test_allocation_pie_chart():

    PortfolioVisualizer \
        .allocation_pie_chart(

            DEFAULT_ASSETS,

            np.repeat(

                1.0
                /
                len(DEFAULT_ASSETS),

                len(DEFAULT_ASSETS)

            )

        )

    logger.info(
        "Allocation pie chart test passed"
    )

#========================
# portfolio dashboard
#========================

class PortfolioDashboard:

    @staticmethod
    def display(result):
        """
        Displays the current optimizer state.
        """

        print("\n" + "=" * 70)
        print("                PORTFOLIO DASHBOARD")
        print("=" * 70)

        print(f"Current Regime : {result['regime']}")
        print(f"Cash Weight    : {result['cash']:.2%}")

        if result.get("expected_returns") is not None:
            print(
                f"Forecast Mean  : "
                f"{np.mean(result['expected_returns']):.4%}"
            )

        print("=" * 70)

        print("\nPortfolio Allocation")

        allocation = pd.Series(

            result["weights"],
            index=result["assets"]

        )

        print(
            allocation.round(4)
        )

        if "risk_report" in result:

            print("\nRisk Budget Report")

            print(

                result[
                    "risk_report"
                ].round(4)

            )

        if "performance" in result:

            print("\nPerformance")

            for key, value in (

                result[
                    "performance"
                ].items()

            ):

                print(
                    f"{key:20s}"
                    f"{value:10.4f}"
                )

        PortfolioVisualizer \
            .allocation_pie_chart(

                result["assets"],

                result["weights"]

            )

        PortfolioVisualizer \
            .risk_contribution_chart(

                result[
                    "risk_report"
                ]

            )
        
def test_portfolio_dashboard():

    covariance = np.eye(
        len(DEFAULT_ASSETS)
    )

    optimizer = PortfolioOptimizer(

        RiskBudgeting(),

        PortfolioConstraints(),

        VolatilityTargeting()

    )

    result = optimizer.optimize(

        covariance,

        "neutral",

        DEFAULT_ASSETS

    )

    result["assets"] = DEFAULT_ASSETS

    PortfolioDashboard.display(
        result
    )

    logger.info(
        "Portfolio dashboard test passed"
    )

# ============================================================
# REGIME DASHBOARD
# ============================================================

class RegimeDashboard:

    @staticmethod
    def display(
        regime,
        current_state,
        crisis_probability,
        leverage_multiplier,
        transition_matrix,
        expected_duration
    ):

        print("\n")
        print("=" * 80)
        print("                 REGIME DASHBOARD")
        print("=" * 80)

        print(
            f"Portfolio Regime      : {regime}"
        )

        print(
            f"HMM State             : {current_state}"
        )

        print(
            f"Crisis Probability    : "
            f"{crisis_probability:.2%}"
        )

        print(
            f"Leverage Multiplier   : "
            f"{leverage_multiplier:.2f}"
        )

        print(
            f"Expected Duration     : "
            f"{expected_duration:.1f} days"
        )

        print("=" * 80)

    @staticmethod
    def transition_heatmap(
        transition_matrix
    ):

        plt.figure(
            figsize=(8, 6)
        )

        plt.imshow(
            transition_matrix,
            interpolation="nearest",
            aspect="auto"
        )

        plt.colorbar()

        plt.xticks(
            range(
                transition_matrix.shape[0]
            )
        )

        plt.yticks(
            range(
                transition_matrix.shape[0]
            )
        )

        plt.xlabel(
            "Next State"
        )

        plt.ylabel(
            "Current State"
        )

        plt.title(
            "HMM Transition Matrix"
        )

        plt.tight_layout()

        plt.show()

    @staticmethod
    def probability_chart(
        crisis_probability
    ):

        plt.figure(
            figsize=(6, 4)
        )

        plt.bar(

            [
                "Bull",
                "Neutral",
                "Crisis"
            ],

            [
                1.0 - crisis_probability,
                0.0,
                crisis_probability
            ]

        )

        plt.ylabel(
            "Probability"
        )

        plt.title(
            "Regime Probability"
        )

        plt.tight_layout()

        plt.show()

def test_regime_dashboard():

    matrix = np.array([

        [0.93,0.05,0.02],

        [0.10,0.82,0.08],

        [0.04,0.12,0.84]

    ])

    RegimeDashboard.display(

        regime="neutral",

        current_state=1,

        crisis_probability=0.18,

        leverage_multiplier=0.82,

        transition_matrix=matrix,

        expected_duration=18

    )

    RegimeDashboard.transition_heatmap(
        matrix
    )

    RegimeDashboard.probability_chart(
        0.18
    )

    logger.info(
        "Regime dashboard test passed"
    )

# ============================================================
# PORTFOLIO ACCOUNTING
# ============================================================

class PortfolioAccount:

    def __init__(
        self,
        initial_capital=1_000_000
    ):

        self.initial_capital = float(
            initial_capital
        )

        self.cash = float(
            initial_capital
        )

        self.positions = {}

        self.portfolio_value = float(
            initial_capital
        )

        self.nav_history = []

        self.turnover_history = []

        self.trade_history = []

        self.weight_history = []

    def value(
        self,
        prices
    ):

        holdings = 0.0

        for asset, shares in self.positions.items():

            holdings += (

                shares
                *
                prices[asset]

            )

        self.portfolio_value = (

            self.cash
            +
            holdings

        )

        return self.portfolio_value
    
    def weights(
        self,
        prices
    ):

        total = self.value(
            prices
        )

        w = {}

        for asset, shares in self.positions.items():

            w[asset] = (

                shares
                *
                prices[asset]

            ) / total

        return pd.Series(w)
    
    def update_nav(
        self,
        prices
    ):

        nav = self.value(
            prices
        )

        self.nav_history.append(
            nav
        )

        return nav
    
    def returns(self):

        nav = pd.Series(
            self.nav_history
        )

        return nav.pct_change().dropna()
    
def test_portfolio_account():

    account = PortfolioAccount()

    account.positions = {

        "SPY":100,

        "QQQ":50

    }

    prices = pd.Series({

        "SPY":500,

        "QQQ":400

    })

    value = account.value(
        prices
    )

    assert value > 0

    account.update_nav(
        prices
    )

    assert len(
        account.nav_history
    ) == 1

    logger.info(
        "Portfolio account test passed"
    )

#====================
#Trade Generator
#====================

class TradeGenerator:

    @staticmethod
    def generate_trades(
        account,
        target_weights,
        prices
    ):

        portfolio_value = account.value(
            prices
        )

        current_weights = account.weights(
            prices
        )

        current_weights = current_weights.reindex(
            target_weights.index,
            fill_value=0.0
        )

        trades = pd.DataFrame(

            index=target_weights.index

        )

        trades["Current Weight"] = (
            current_weights
        )

        trades["Target Weight"] = (
            target_weights
        )

        trades["Weight Change"] = (

            trades["Target Weight"]

            -

            trades["Current Weight"]

        )

        trades["Trade Value"] = (

            trades["Weight Change"]

            *

            portfolio_value

        )

        trades["Price"] = (

            prices.loc[
                trades.index
            ]

        )

        trades["Shares"] = (

            trades["Trade Value"]

            /

            trades["Price"]

        )

        return trades
    
#=================
#Turnover
#=================

class TradeAnalytics:

    @staticmethod
    def turnover(
        trades
    ):

        return float(

            np.abs(

                trades[
                    "Trade Value"
                ]

            ).sum()

        )
    
#===================
#Transaction costs
#===================

class TransactionCostModel:

    @staticmethod
    def estimate(

        trades,

        commission=0.0005,

        slippage=0.001

    ):

        traded = np.abs(

            trades[
                "Trade Value"
            ]

        ).sum()

        return (

            traded

            *

            (

                commission

                +

                slippage

            )

        )
    
#==================
#Execution costs
#==================

class ExecutionEngine:

    @staticmethod
    def execute(

        account,

        trades

    ):

        cost = (

            TransactionCostModel
            .estimate(
                trades
            )

        )

        for asset in trades.index:

            shares = float(

                trades.loc[
                    asset,
                    "Shares"
                ]

            )

            price = float(

                trades.loc[
                    asset,
                    "Price"
                ]

            )

            account.positions[asset] = (

                account.positions.get(
                    asset,
                    0.0
                )

                +

                shares

            )

            account.cash -= (

                shares
                *
                price

            )

        account.cash -= cost

        account.trade_history.append(
            trades
        )

        account.turnover_history.append(

            TradeAnalytics.turnover(
                trades
            )

        )

        return cost
    
#==============
#Test
#==============

def test_execution_engine():

    account = PortfolioAccount()

    prices = pd.Series({

        asset:100.0

        for asset in DEFAULT_ASSETS

    })

    target = pd.Series(

        np.repeat(

            1.0 / len(DEFAULT_ASSETS),

            len(DEFAULT_ASSETS)

        ),

        index=DEFAULT_ASSETS

    )

    trades = (

        TradeGenerator
        .generate_trades(

            account,

            target,

            prices

        )

    )

    cost = (

        ExecutionEngine
        .execute(

            account,

            trades

        )

    )

    assert cost > 0

    assert len(

        account.trade_history

    ) == 1

    assert len(

        account.turnover_history

    ) == 1

    logger.info(
        "Execution engine test passed"
    )

# ============================================================
# REBALANCE ENGINE
# ============================================================

class RebalanceEngine:

    @staticmethod
    def should_rebalance(
        current_weights,
        target_weights,
        threshold=0.03
    ):

        current = current_weights.reindex(
            target_weights.index,
            fill_value=0.0
        )

        drift = np.abs(
            current
            -
            target_weights
        )

        return bool(
            drift.max() > threshold
        )

    @staticmethod
    def drift_report(
        current_weights,
        target_weights
    ):

        current = current_weights.reindex(
            target_weights.index,
            fill_value=0.0
        )

        report = pd.DataFrame({

            "Current": current,

            "Target": target_weights

        })

        report["Drift"] = (

            report["Current"]

            -

            report["Target"]

        )

        report["Absolute Drift"] = (

            report["Drift"].abs()

        )

        return report

    @staticmethod
    def threshold_rebalance(
        account,
        target_weights,
        prices,
        threshold=0.03
    ):

        current_weights = account.weights(
            prices
        )

        if not RebalanceEngine.should_rebalance(

            current_weights,

            target_weights,

            threshold

        ):

            return None

        trades = (

            TradeGenerator.generate_trades(

                account,

                target_weights,

                prices

            )

        )

        ExecutionEngine.execute(

            account,

            trades

        )

        return trades


# ============================================================
# REBALANCE TEST
# ============================================================

def test_rebalance_engine():

    account = PortfolioAccount()

    prices = pd.Series(

        {

            asset: 100.0

            for asset in DEFAULT_ASSETS

        }

    )

    target = pd.Series(

        np.repeat(

            1.0 / len(DEFAULT_ASSETS),

            len(DEFAULT_ASSETS)

        ),

        index=DEFAULT_ASSETS

    )

    account.positions = {

        DEFAULT_ASSETS[0]: 500.0

    }

    trades = (

        RebalanceEngine.threshold_rebalance(

            account,

            target,

            prices,

            threshold=0.02

        )

    )

    assert trades is not None

    assert isinstance(
        trades,
        pd.DataFrame
    )

    assert "Trade Value" in trades.columns

    assert len(
        account.trade_history
    ) == 1

    assert len(
        account.turnover_history
    ) == 1

    logger.info(
        "Rebalance engine test passed"
    )