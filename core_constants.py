from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict
)

import numpy as np


# ============================================================
# SETTINGS
# ============================================================

class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False
    )

    fred_api_key: str | None = None

    database_url: str | None = None

    alpaca_key: str | None = None

    alpaca_secret: str | None = None

    redis_host: str = "localhost"

    redis_port: int = 6379

    yahoo_period: str = "15y"

    max_position_weight: float = 0.25

    max_leverage: float = 1.0

    max_turnover: float = 0.30


settings = Settings()


# ============================================================
# GLOBAL CONSTANTS
# ============================================================

TRADING_DAYS = 252

BENCHMARK = "SPY"


# ============================================================
# STRATEGIC ASSET UNIVERSE
# ============================================================

DEFAULT_ASSETS = [

    # US EQUITIES
    "SPY",
    "QQQ",
    "IWM",

    # INTERNATIONAL EQUITIES
    "VEA",
    "VWO",

    # GOVERNMENT BONDS
    "TLT",
    "IEF",
    "SHY",

    # CREDIT
    "LQD",
    "HYG",

    # REAL ASSETS
    "GLD",
    "SLV",
    "DBC",

    # REAL ESTATE
    "VNQ"
]


# ============================================================
# FRED MACRO SERIES
# ============================================================

FRED_SERIES = {

    "FEDFUNDS": "FEDFUNDS",
    "UNRATE": "UNRATE",
    "CPI": "CPIAUCSL",
    "GDP": "GDP",
    "DGS10": "DGS10",
    "DGS2": "DGS2"
}


# ============================================================
# STRATEGIC RISK BUDGETS
# MUST SUM TO 1.0
# ============================================================

RISK_BUDGETS = {

    # US EQUITIES
    "SPY": 0.15,
    "QQQ": 0.10,
    "IWM": 0.05,

    # INTERNATIONAL EQUITIES
    "VEA": 0.10,
    "VWO": 0.05,

    # GOVERNMENT BONDS
    "TLT": 0.15,
    "IEF": 0.10,
    "SHY": 0.05,

    # CREDIT
    "LQD": 0.07,
    "HYG": 0.03,

    # REAL ASSETS
    "GLD": 0.07,
    "SLV": 0.03,
    "DBC": 0.03,

    # REAL ESTATE
    "VNQ": 0.02
}


# ============================================================
# MARKET PORTFOLIO PROXY
# MUST SUM TO 1.0
# ============================================================

market_weights = np.array([

    # US EQUITIES
    0.30,   # SPY
    0.15,   # QQQ
    0.05,   # IWM

    # INTERNATIONAL EQUITIES
    0.10,   # VEA
    0.05,   # VWO

    # GOVERNMENT BONDS
    0.10,   # TLT
    0.05,   # IEF
    0.03,   # SHY

    # CREDIT
    0.05,   # LQD
    0.02,   # HYG

    # REAL ASSETS
    0.04,   # GLD
    0.02,   # SLV
    0.02,   # DBC

    # REAL ESTATE
    0.02    # VNQ
])

market_weights = (
    market_weights
    /
    market_weights.sum()
)

# ============================================================
# REGIME VOL TARGETS
# ============================================================

REGIME_VOL_TARGETS = {

    "bull": 0.15,

    "neutral": 0.10,

    "crisis": 0.05
}

# ============================================================
# REGIME RISK BUDGETS
# ============================================================

REGIME_RISK_BUDGETS = {

    "bull": {

        "SPY": 0.20,
        "QQQ": 0.20,

        "IWM": 0.10,
        "VEA": 0.10,
        "VWO": 0.05,

        "TLT": 0.05,
        "IEF": 0.05,
        "SHY": 0.02,

        "LQD": 0.05,
        "HYG": 0.03,

        "GLD": 0.05,
        "SLV": 0.03,
        "DBC": 0.02,

        "VNQ": 0.05
    },

    "neutral": {

        "SPY": 0.15,
        "QQQ": 0.10,

        "IWM": 0.08,
        "VEA": 0.08,
        "VWO": 0.04,

        "TLT": 0.10,
        "IEF": 0.10,
        "SHY": 0.05,

        "LQD": 0.07,
        "HYG": 0.03,

        "GLD": 0.10,
        "SLV": 0.03,
        "DBC": 0.02,

        "VNQ": 0.05
    },

    "crisis": {

        "SPY": 0.03,
        "QQQ": 0.02,

        "IWM": 0.01,
        "VEA": 0.02,
        "VWO": 0.01,

        "TLT": 0.20,
        "IEF": 0.15,
        "SHY": 0.10,

        "LQD": 0.08,
        "HYG": 0.01,

        "GLD": 0.20,
        "SLV": 0.05,
        "DBC": 0.01,

        "VNQ": 0.11
    }
}

# ============================================================
# REGIME LEVERAGE
# ============================================================

REGIME_MAX_LEVERAGE = {

    "bull": 1.00,

    "neutral": 0.75,

    "crisis": 0.40
}

# ============================================================
# REGIME CONFIG TEST
# ============================================================

def test_regime_configuration():

    for regime in [

        "bull",
        "neutral",
        "crisis"

    ]:

        budget_sum = sum(

            REGIME_RISK_BUDGETS[
                regime
            ].values()

        )

        assert np.isclose(
            budget_sum,
            1.0
        ), (
            f"{regime} budget sum = "
            f"{budget_sum}"
        )

        assert (
            REGIME_VOL_TARGETS[
                regime
            ] > 0
        )

        assert (
            REGIME_MAX_LEVERAGE[
                regime
            ] > 0
        )

    print(
        "Regime configuration test passed"
    )