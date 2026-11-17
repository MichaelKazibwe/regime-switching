"""
======================================================================
STEP 9 — REGISTRY-QUALIFIED HISTORICAL WALK-FORWARD REGIME-SWITCHING BACKTEST
======================================================================

Purpose
-------
Validate the production PortfolioDecisionEngine against real
historical market and macroeconomic data without introducing
look-ahead bias.

Production universe
-------------------
SPY
QQQ
IWM
VEA
VWO
TLT
IEF
SHY
LQD
HYG
GLD
SLV
DBC
VNQ

Design
------
1. Load real historical prices for all registered paper-qualified assets.
2. Calculate historical returns.
3. Load real FRED macroeconomic data.
4. Align macro observations to the market calendar.
5. Construct historical point-in-time regime labels.
6. Walk forward chronologically.
7. At every rebalance date:
       - use only information available through that date;
       - calculate expected returns using prices through that date;
       - calculate covariance/risk using returns through that date;
       - provide historical regimes only through that date;
       - request a production portfolio decision.
8. Apply the resulting portfolio to the NEXT holding period.
9. Apply transaction costs to turnover.
10. Compare against:
       - SPY
       - registry-qualified equal-weight portfolio
11. Produce portfolio and regime-level statistics.
12. Validate deterministic execution.
13. Validate that no future observations enter any decision.

IMPORTANT
---------
This file is a historical backtest harness.

It does NOT replace the production decision engine.

The PortfolioDecisionEngine remains the decision authority.

The backtest must never modify the production decision logic.
======================================================================
"""

# ======================================================================
# SECTION 1 — IMPORTS
# ======================================================================

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

from fredapi import Fred

from core_constants import settings

from marketdataloader import MarketDataLoader

from macroregime import MacroRegimeModel

from expectedreturnforecaster import (
    ExpectedReturnForecaster,
)

from productioncomposition import (
    build_production_engine,
)


# ======================================================================
# SECTION 2 — PRODUCTION CONFIGURATION
# ======================================================================

TICKERS = list(__import__("assetuniverse").PRODUCTION_ASSETS)

BENCHMARK = "SPY"

HISTORY_PERIOD = "15y"

MIN_TRAINING_OBSERVATIONS = 504

REBALANCE_INTERVAL = 21

TRANSACTION_COST_BPS = 5.0

TRADING_DAYS = 252

TOLERANCE = 1e-8

EXPECTED_ASSET_COUNT = len(__import__("assetuniverse").PRODUCTION_ASSETS)


# ======================================================================
# SECTION 3 — OUTPUT STRUCTURES
# ======================================================================


@dataclass(frozen=True)
class BacktestObservation:
    """
    Audit record for one point-in-time production decision.
    """

    date: pd.Timestamp

    next_date: pd.Timestamp

    regime: str

    training_observations: int

    holding_observations: int

    portfolio_return: float

    benchmark_return: float

    equal_weight_return: float

    turnover: float

    transaction_cost: float

    gross_exposure: float

    net_exposure: float

    active_positions: int

    weights: dict[str, float]

    expected_returns: dict[str, float]


# ======================================================================
# SECTION 4 — DISPLAY / FAILURE HELPERS
# ======================================================================


def banner(
    title: str,
) -> None:

    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def fail(
    message: str,
) -> None:

    print()
    print("=" * 80)
    print("STEP 9 FAILED")
    print("=" * 80)
    print()
    print(message)
    print()

    raise AssertionError(message)


# ======================================================================
# SECTION 5 — UNIVERSE VALIDATION
# ======================================================================


def validate_universe() -> None:
    """
    Validate that Step 9 is operating on the complete production
    registry-qualified universe.
    """

    if len(TICKERS) != EXPECTED_ASSET_COUNT:

        fail(
            "Production universe must contain exactly "
            f"{EXPECTED_ASSET_COUNT} assets. "
            f"Found {len(TICKERS)}."
        )

    if len(set(TICKERS)) != len(TICKERS):

        fail(
            "Production universe contains duplicate tickers."
        )

    required = {
        "SPY",
        "QQQ",
        "IWM",
        "VEA",
        "VWO",
        "TLT",
        "IEF",
        "SHY",
        "LQD",
        "HYG",
        "GLD",
        "SLV",
        "DBC",
        "VNQ",
    }

    if set(TICKERS) != required:

        fail(
            "Step 9 production universe does not match "
            "the required registry-qualified architecture."
        )

    if BENCHMARK not in TICKERS:

        fail(
            f"Benchmark {BENCHMARK} is not in the "
            "production asset universe."
        )

    print()
    print("PRODUCTION ASSET UNIVERSE:")
    print(TICKERS)
    print(
        "Asset count:",
        len(TICKERS),
    )


# ======================================================================
# SECTION 6 — MARKET DATA
# ======================================================================


def load_market_data() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Load real historical market prices and returns.

    No price observations are fabricated.

    Complete-case alignment is performed only after the source
    diagnostics have been displayed.
    """

    banner(
        "1. LOADING REGISTRY-QUALIFIED HISTORICAL MARKET DATA"
    )

    loader = MarketDataLoader(
        assets=TICKERS,
        period=HISTORY_PERIOD,
    )

    prices = loader.load_prices(
        validate=False
    )

    if prices is None or prices.empty:

        fail(
            "Historical market price data is empty."
        )

    prices = (
        prices
        .copy()
        .sort_index()
    )

    missing_columns = [
        ticker
        for ticker in TICKERS
        if ticker not in prices.columns
    ]

    if missing_columns:

        fail(
            "Historical market data is missing required "
            f"assets: {missing_columns}"
        )

    prices = prices.loc[
        :,
        TICKERS,
    ]

    if len(prices) < MIN_TRAINING_OBSERVATIONS:

        fail(
            "Insufficient raw historical observations: "
            f"{len(prices)}."
        )

    # --------------------------------------------------------------
    # SOURCE QUALITY
    # --------------------------------------------------------------

    print()
    print(
        "RAW HISTORICAL DATA QUALITY:"
    )

    print(
        "Observations:",
        len(prices),
    )

    missing = prices.isna().sum()

    print(
        "Missing observations by ticker:"
    )

    print(missing)

    # --------------------------------------------------------------
    # No missing observations are expected from the current
    # production market-data normalization.
    # --------------------------------------------------------------

    for ticker in TICKERS:

        if int(
            missing[ticker]
        ) != 0:

            fail(
                f"Unexpected missing observations for "
                f"{ticker}: {int(missing[ticker])}"
            )

    # --------------------------------------------------------------
    # PRICE VALIDATION
    # --------------------------------------------------------------

    if not np.isfinite(
        prices.to_numpy(
            dtype=float
        )
    ).all():

        fail(
            "Historical price matrix contains non-finite values."
        )

    if not (
        prices > 0
    ).all().all():

        fail(
            "Historical price matrix contains non-positive prices."
        )

    # --------------------------------------------------------------
    # COMPLETE CASE
    # --------------------------------------------------------------

    prices = (
        prices
        .dropna(
            how="any"
        )
    )

    if len(prices) < MIN_TRAINING_OBSERVATIONS:

        fail(
            "Insufficient complete historical observations "
            f"after alignment: {len(prices)}."
        )

    if not prices.index.is_monotonic_increasing:

        fail(
            "Historical price index is not chronological."
        )

    if not prices.index.is_unique:

        fail(
            "Historical price index contains duplicates."
        )

    # --------------------------------------------------------------
    # RETURNS
    # --------------------------------------------------------------

    returns = (
        prices
        .pct_change()
        .dropna()
    )

    if returns.empty:

        fail(
            "Historical return matrix is empty."
        )

    if returns.isna().any().any():

        fail(
            "Historical return matrix contains NaN values."
        )

    if not np.isfinite(
        returns.to_numpy(
            dtype=float
        )
    ).all():

        fail(
            "Historical return matrix contains non-finite values."
        )

    if list(
        prices.columns
    ) != TICKERS:

        fail(
            "Historical price columns do not match "
            "the registry-qualified universe."
        )

    if list(
        returns.columns
    ) != TICKERS:

        fail(
            "Historical return columns do not match "
            "the registry-qualified universe."
        )

    print()
    print(
        "PRICE HISTORY:"
    )

    print(
        f"Observations: {len(prices)}"
    )

    print(
        f"Tickers: {list(prices.columns)}"
    )

    print(
        f"Shape: {prices.shape}"
    )

    print(
        f"Start: {prices.index[0]}"
    )

    print(
        f"End: {prices.index[-1]}"
    )

    print()
    print(
        "RETURN HISTORY:"
    )

    print(
        f"Observations: {len(returns)}"
    )

    print(
        f"Shape: {returns.shape}"
    )

    print(
        f"Start: {returns.index[0]}"
    )

    print(
        f"End: {returns.index[-1]}"
    )

    print()
    print(
        "RETURN DATA QUALITY:"
    )

    print(
        returns.isna().sum()
    )

    return prices, returns


# ======================================================================
# SECTION 7 — FRED HELPERS
# ======================================================================


def _clean_fred_series(
    series: pd.Series,
) -> pd.Series:

    cleaned = (
        pd.Series(series)
        .copy()
    )

    cleaned.index = pd.to_datetime(
        cleaned.index
    )

    if cleaned.index.tz is not None:

        cleaned.index = (
            cleaned.index
            .tz_localize(None)
        )

    cleaned = (
        pd.to_numeric(
            cleaned,
            errors="coerce",
        )
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .dropna()
        .sort_index()
    )

    cleaned = (
        cleaned[
            ~cleaned.index.duplicated(
                keep="last"
            )
        ]
    )

    return cleaned


# ======================================================================
# SECTION 8 — FRED DATA
# ======================================================================


def load_fred_data(
    market_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    """
    Load historical FRED macroeconomic observations and align them
    to the market trading calendar.

    Variables:

        UNRATE
        CPIAUCSL
        DGS10
        DGS2

    Inflation is calculated on the original monthly CPI series before
    market-calendar alignment.

    Forward filling carries the latest available observation forward.

    IMPORTANT:
    This is an observation-date backtest. It is not a vintage/release-
    timestamp FRED backtest. Historical revisions to FRED observations
    are therefore not explicitly modeled here.
    """

    banner(
        "2. LOADING FRED MACROECONOMIC DATA"
    )

    if not settings.fred_api_key:

        fail(
            "FRED API key is not configured."
        )

    market_index = pd.DatetimeIndex(
        pd.to_datetime(
            market_index
        )
    )

    if market_index.empty:

        fail(
            "Market calendar is empty."
        )

    if market_index.tz is not None:

        market_index = (
            market_index
            .tz_localize(None)
        )

    market_index = (
        market_index
        .sort_values()
        .drop_duplicates()
    )

    fred = Fred(
        api_key=settings.fred_api_key
    )

    start_date = market_index.min()
    end_date = market_index.max()

    print()
    print(
        "MARKET CALENDAR:"
    )

    print(
        f"Observations: {len(market_index)}"
    )

    print(
        f"Start: {start_date}"
    )

    print(
        f"End: {end_date}"
    )

    series_map = {
        "unemployment": "UNRATE",
        "cpi": "CPIAUCSL",
        "dgs10": "DGS10",
        "dgs2": "DGS2",
    }

    raw: dict[str, pd.Series] = {}

    for name, series_id in series_map.items():

        print()
        print(
            f"Downloading FRED series: {series_id}"
        )

        try:

            series = fred.get_series(
                series_id,
                observation_start=start_date,
                observation_end=end_date,
            )

        except Exception as exc:

            fail(
                f"Unable to download FRED series "
                f"{series_id}: {exc}"
            )

        if series is None:

            fail(
                f"FRED returned no data for {series_id}."
            )

        series = _clean_fred_series(
            series
        )

        if series.empty:

            fail(
                f"FRED series {series_id} contains no "
                "usable observations."
            )

        print(
            f"Observations: {len(series)}"
        )

        print(
            f"Start: {series.index[0]}"
        )

        print(
            f"End: {series.index[-1]}"
        )

        raw[name] = series

    # --------------------------------------------------------------
    # INFLATION
    # --------------------------------------------------------------

    inflation = (
        raw["cpi"]
        .pct_change(
            periods=12
        )
        .mul(100.0)
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .dropna()
    )

    # --------------------------------------------------------------
    # YIELD SPREAD
    # --------------------------------------------------------------

    treasury = pd.concat(
        {
            "dgs10": raw["dgs10"],
            "dgs2": raw["dgs2"],
        },
        axis=1,
        join="outer",
        sort=True,
    )

    treasury = (
        treasury
        .ffill()
    )

    treasury["yield_spread"] = (
        treasury["dgs10"]
        -
        treasury["dgs2"]
    )

    yield_spread = (
        treasury["yield_spread"]
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .dropna()
    )

    # --------------------------------------------------------------
    # RAW MACRO FRAME
    # --------------------------------------------------------------

    macro = pd.concat(
        {
            "unemployment": raw["unemployment"],
            "inflation": inflation,
            "yield_spread": yield_spread,
        },
        axis=1,
        join="outer",
        sort=True,
    )

    macro = (
        macro
        .sort_index()
    )

    print()
    print(
        "MACRO VARIABLES BEFORE MARKET ALIGNMENT"
    )

    print()
    print(
        f"Observations: {len(macro)}"
    )

    print(
        "Missing observations:"
    )

    print(
        macro.isna().sum().to_dict()
    )

    # --------------------------------------------------------------
    # MARKET CALENDAR ALIGNMENT
    # --------------------------------------------------------------

    macro = (
        macro
        .reindex(
            market_index
        )
        .ffill()
    )

    macro = (
        macro
        .dropna(
            subset=[
                "unemployment",
                "inflation",
                "yield_spread",
            ]
        )
    )

    required_columns = [
        "unemployment",
        "inflation",
        "yield_spread",
    ]

    if macro.empty:

        fail(
            "No usable aligned macroeconomic observations."
        )

    if macro[
        required_columns
    ].isna().any().any():

        fail(
            "Aligned macroeconomic data contains missing values."
        )

    if not np.isfinite(
        macro[
            required_columns
        ]
        .to_numpy(
            dtype=float
        )
    ).all():

        fail(
            "Aligned macroeconomic data contains "
            "non-finite values."
        )

    if not macro.index.is_monotonic_increasing:

        fail(
            "Aligned macro index is not chronological."
        )

    print()
    print(
        "ALIGNED MACROECONOMIC DATA"
    )

    print()
    print(
        f"Observations: {len(macro)}"
    )

    print(
        f"Start: {macro.index[0]}"
    )

    print(
        f"End: {macro.index[-1]}"
    )

    print(
        f"Columns: {list(macro.columns)}"
    )

    print()
    print(
        "Missing values:"
    )

    print(
        macro[
            required_columns
        ]
        .isna()
        .sum()
        .to_dict()
    )

    print()
    print(
        "Latest macro observations:"
    )

    print(
        macro.tail()
    )

    return macro


# ======================================================================
# SECTION 9 — HISTORICAL REGIME ENGINE
# ======================================================================


def build_regime_history(
    macro: pd.DataFrame,
) -> pd.Series:
    """
    Construct historical regime labels chronologically.

    The classifier only receives information available at each
    observation date.
    """

    banner(
        "3. BUILDING HISTORICAL REGIME HISTORY"
    )

    model = MacroRegimeModel()

    values: list[str] = []
    dates: list[pd.Timestamp] = []

    for date in macro.index:

        history = (
            macro
            .loc[:date]
        )

        unemployment = (
            history[
                "unemployment"
            ]
        )

        if len(
            unemployment
        ) < 2:

            continue

        yield_spread = float(
            history[
                "yield_spread"
            ].iloc[-1]
        )

        inflation = float(
            history[
                "inflation"
            ].iloc[-1]
        )

        result = model.classify(
            unemployment,
            yield_spread,
            inflation,
        )

        if hasattr(
            result,
            "value",
        ):

            result = result.value

        result = str(
            result
        ).lower()

        values.append(
            result
        )

        dates.append(
            date
        )

    regimes = pd.Series(
        values,
        index=pd.DatetimeIndex(
            dates
        ),
        name="regime",
    )

    if regimes.empty:

        fail(
            "Historical regime series is empty."
        )

    if not regimes.index.is_monotonic_increasing:

        fail(
            "Historical regime series is not chronological."
        )

    print()
    print(
        "REGIME HISTORY:"
    )

    print(
        f"Observations: {len(regimes)}"
    )

    print(
        "Unique regimes:",
        sorted(
            regimes.unique().tolist()
        ),
    )

    print()
    print(
        "REGIME COUNTS:"
    )

    print(
        regimes.value_counts()
    )

    return regimes


# ======================================================================
# SECTION 10 — POINT-IN-TIME MACRO STATE
# ======================================================================


def build_point_in_time_macro_data(
    macro: pd.DataFrame,
    date: pd.Timestamp,
) -> dict:
    """
    Return exactly the macro information available through date.
    """

    history = (
        macro
        .loc[:date]
    )

    if history.empty:

        fail(
            f"No macro history available at {date}."
        )

    unemployment = (
        history[
            "unemployment"
        ]
        .copy()
    )

    if len(
        unemployment
    ) < 2:

        fail(
            f"Insufficient unemployment history at {date}."
        )

    return {
        "unemployment": unemployment,

        "yield_spread": float(
            history[
                "yield_spread"
            ].iloc[-1]
        ),

        "inflation": float(
            history[
                "inflation"
            ].iloc[-1]
        ),
    }


# ======================================================================
# SECTION 11 — POINT-IN-TIME EXPECTED RETURNS
# ======================================================================


def build_point_in_time_expected_returns(
    prices: pd.DataFrame,
    date: pd.Timestamp,
) -> dict[str, float]:
    """
    Generate expected returns using only prices through date.
    """

    historical_prices = (
        prices
        .loc[:date]
        .copy()
    )

    if len(
        historical_prices
    ) < MIN_TRAINING_OBSERVATIONS:

        fail(
            "Insufficient historical price observations for "
            f"expected-return forecast at {date}: "
            f"{len(historical_prices)}."
        )

    if (
        historical_prices.index.max()
        > date
    ):

        fail(
            "LOOK-AHEAD VIOLATION in expected-return "
            f"history at {date}."
        )

    forecaster = (
        ExpectedReturnForecaster()
    )

    forecast = (
        forecaster.forecast(
            historical_prices
        )
    )

    if isinstance(
        forecast,
        pd.Series,
    ):

        result = {}

        for ticker in TICKERS:

            if ticker not in forecast.index:

                fail(
                    f"Expected-return forecast is missing "
                    f"{ticker} at {date}."
                )

            result[ticker] = float(
                forecast[
                    ticker
                ]
            )

    elif isinstance(
        forecast,
        dict,
    ):

        result = {}

        for ticker in TICKERS:

            if ticker not in forecast:

                fail(
                    f"Expected-return forecast is missing "
                    f"{ticker} at {date}."
                )

            result[ticker] = float(
                forecast[
                    ticker
                ]
            )

    else:

        try:

            array = np.asarray(
                forecast,
                dtype=float,
            ).reshape(-1)

        except Exception as exc:

            fail(
                "Unable to convert expected-return forecast "
                f"to an array at {date}: {exc}"
            )

        if len(array) != len(
            TICKERS
        ):

            fail(
                "Expected-return forecast dimension "
                f"{len(array)} does not match "
                f"registry-qualified universe."
            )

        result = {
            ticker: float(
                array[index]
            )
            for index, ticker in enumerate(
                TICKERS
            )
        }

    for ticker, value in result.items():

        if not np.isfinite(
            value
        ):

            fail(
                f"Expected return for {ticker} is not finite "
                f"at {date}."
            )

    return result


# ======================================================================
# SECTION 12 — INITIAL PORTFOLIO
# ======================================================================


def build_initial_portfolio() -> dict:
    """
    Equal-weight input portfolio.

    This is only the portfolio supplied to the production engine.
    The production optimizer remains responsible for the final
    target weights.
    """

    equal_weight = (
        1.0 / len(TICKERS)
    )

    return {
        "weights": {
            ticker: equal_weight
            for ticker in TICKERS
        }
    }


# ======================================================================
# SECTION 13 — TURNOVER
# ======================================================================


def calculate_turnover(
    previous_weights: dict[str, float],
    new_weights: dict[str, float],
) -> float:
    """
    One-way portfolio turnover:

        sum(abs(new_weight - previous_weight))
    """

    turnover = float(
        sum(
            abs(
                float(
                    new_weights.get(
                        ticker,
                        0.0,
                    )
                )
                -
                float(
                    previous_weights.get(
                        ticker,
                        0.0,
                    )
                )
            )
            for ticker in TICKERS
        )
    )

    if not np.isfinite(
        turnover
    ):

        fail(
            "Turnover is non-finite."
        )

    if turnover < -TOLERANCE:

        fail(
            "Turnover cannot be negative."
        )

    return max(
        turnover,
        0.0,
    )


# ======================================================================
# SECTION 14 — TRANSACTION COST
# ======================================================================


def calculate_transaction_cost(
    turnover: float,
) -> float:

    cost = float(
        turnover
        * TRANSACTION_COST_BPS
        / 10000.0
    )

    if cost < -TOLERANCE:

        fail(
            "Transaction cost cannot be negative."
        )

    return max(
        cost,
        0.0,
    )


# ======================================================================
# SECTION 15 — PERFORMANCE METRICS
# ======================================================================


def annualized_return(
    returns: pd.Series,
) -> float:

    clean = (
        returns
        .dropna()
    )

    if clean.empty:
        return 0.0

    cumulative = float(
        np.prod(
            1.0
            + clean.to_numpy()
        )
    )

    years = (
        len(clean)
        / TRADING_DAYS
    )

    if years <= 0:
        return 0.0

    if cumulative <= 0:
        return -1.0

    return float(
        cumulative ** (
            1.0 / years
        )
        - 1.0
    )


def annualized_volatility(
    returns: pd.Series,
) -> float:

    clean = (
        returns
        .dropna()
    )

    if len(clean) < 2:
        return 0.0

    return float(
        clean.std(
            ddof=1
        )
        * math.sqrt(
            TRADING_DAYS
        )
    )


def sharpe_ratio(
    returns: pd.Series,
) -> float:

    volatility = annualized_volatility(
        returns
    )

    if volatility <= 0:
        return 0.0

    return float(
        annualized_return(
            returns
        )
        / volatility
    )


def sortino_ratio(
    returns: pd.Series,
) -> float:

    clean = (
        returns
        .dropna()
    )

    if len(clean) < 2:
        return 0.0

    downside = (
        clean[
            clean < 0
        ]
    )

    if len(downside) < 2:
        return 0.0

    downside_deviation = float(
        downside.std(
            ddof=1
        )
        * math.sqrt(
            TRADING_DAYS
        )
    )

    if downside_deviation <= 0:
        return 0.0

    return float(
        annualized_return(
            clean
        )
        / downside_deviation
    )


def maximum_drawdown(
    returns: pd.Series,
) -> float:

    clean = (
        returns
        .dropna()
    )

    if clean.empty:
        return 0.0

    equity = (
        1.0
        * (
            1.0
            + clean
        ).cumprod()
    )

    peak = (
        equity
        .cummax()
    )

    drawdown = (
        equity
        / peak
        - 1.0
    )

    return float(
        drawdown.min()
    )


def calculate_metrics(
    returns: pd.Series,
) -> dict[str, float]:

    clean = (
        returns
        .dropna()
    )

    cumulative = (
        float(
            (
                1.0
                + clean
            ).prod()
            - 1.0
        )
        if not clean.empty
        else 0.0
    )

    return {
        "observations": float(
            len(clean)
        ),
        "cumulative_return": cumulative,
        "cagr": annualized_return(
            clean
        ),
        "volatility": annualized_volatility(
            clean
        ),
        "sharpe": sharpe_ratio(
            clean
        ),
        "sortino": sortino_ratio(
            clean
        ),
        "max_drawdown": maximum_drawdown(
            clean
        ),
    }


# ======================================================================
# SECTION 16 — WALK-FORWARD BACKTEST
# ======================================================================


def run_backtest(
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    macro: pd.DataFrame,
    regimes: pd.Series,
) -> tuple[
    pd.DataFrame,
    object,
    list[BacktestObservation],
]:
    """
    Execute the production decision engine chronologically.

    Every decision at t uses only information <= t.

    The resulting weights are applied only to returns after t.
    """

    banner(
        "4. RUNNING REGISTRY-QUALIFIED WALK-FORWARD BACKTEST"
    )

    # --------------------------------------------------------------
    # Common decision calendar.
    # --------------------------------------------------------------

    common_index = (
        prices.index
        .intersection(
            returns.index
        )
        .intersection(
            macro.index
        )
        .intersection(
            regimes.index
        )
        .sort_values()
    )

    if len(
        common_index
    ) < MIN_TRAINING_OBSERVATIONS + 2:

        fail(
            "Insufficient common observations for "
            "walk-forward backtesting."
        )

    prices = prices.loc[
        common_index
    ]

    returns = returns.loc[
        common_index
    ]

    macro = macro.loc[
        common_index
    ]

    regimes = regimes.loc[
        common_index
    ]

    # --------------------------------------------------------------
    # Alignment validation.
    # --------------------------------------------------------------

    if not prices.index.equals(
        returns.index
    ):

        fail(
            "Prices and returns are not aligned."
        )

    if not prices.index.equals(
        macro.index
    ):

        fail(
            "Prices and macro history are not aligned."
        )

    if not prices.index.equals(
        regimes.index
    ):

        fail(
            "Prices and regime history are not aligned."
        )

    if list(
        prices.columns
    ) != TICKERS:

        fail(
            "Backtest price universe does not match "
            "the registered paper-qualified assets."
        )

    if list(
        returns.columns
    ) != TICKERS:

        fail(
            "Backtest return universe does not match "
            "the registered paper-qualified assets."
        )

    print()
    print(
        "ALIGNED BACKTEST SAMPLE:"
    )

    print(
        "Observations:",
        len(common_index),
    )

    print(
        "Start:",
        common_index[0],
    )

    print(
        "End:",
        common_index[-1],
    )

    print(
        "Assets:",
        len(TICKERS),
    )

    # --------------------------------------------------------------
    # Build production engine.
    # --------------------------------------------------------------

    engine = (
        build_production_engine()
    )

    health = (
        engine.health_check()
    )

    print()
    print(
        "PRODUCTION ENGINE:"
    )

    print(
        engine
    )

    print()
    print(
        "INITIAL ENGINE HEALTH:"
    )

    print(
        health
    )

    if health.get(
        "healthy"
    ) is not True:

        fail(
            "Production engine is unhealthy before "
            "the historical backtest."
        )

    # --------------------------------------------------------------
    # Rebalance positions.
    #
    # Position i is a decision date.
    #
    # Its realized holding period begins at i+1.
    #
    # The final position is excluded because it has no future
    # observation available for evaluation.
    # --------------------------------------------------------------

    start_position = (
        MIN_TRAINING_OBSERVATIONS
    )

    rebalance_positions = list(
        range(
            start_position,
            len(common_index) - 1,
            REBALANCE_INTERVAL,
        )
    )

    if not rebalance_positions:

        fail(
            "No valid rebalance dates were generated."
        )

    print()
    print(
        "REBALANCE CONFIGURATION:"
    )

    print(
        "Rebalance count:",
        len(
            rebalance_positions
        ),
    )

    print(
        "Training window:",
        MIN_TRAINING_OBSERVATIONS,
    )

    print(
        "Interval:",
        REBALANCE_INTERVAL,
        "trading days",
    )

    # --------------------------------------------------------------
    # Portfolio state.
    #
    # Starting with zero weights means the first allocation incurs
    # the full implementation turnover.
    # --------------------------------------------------------------

    previous_weights = {
        ticker: 0.0
        for ticker in TICKERS
    }

    observations: list[
        BacktestObservation
    ] = []

    daily_strategy_returns: list[
        pd.Series
    ] = []

    daily_benchmark_returns: list[
        pd.Series
    ] = []

    daily_equal_weight_returns: list[
        pd.Series
    ] = []

    # --------------------------------------------------------------
    # WALK FORWARD
    # --------------------------------------------------------------

    for counter, position in enumerate(
        rebalance_positions,
        start=1,
    ):

        decision_date = (
            common_index[
                position
            ]
        )

        # ----------------------------------------------------------
        # Determine the next rebalance date.
        # ----------------------------------------------------------

        if counter < len(
            rebalance_positions
        ):

            next_position = (
                rebalance_positions[
                    counter
                ]
            )

        else:

            next_position = (
                len(common_index)
                - 1
            )

        next_date = (
            common_index[
                next_position
            ]
        )

        # ----------------------------------------------------------
        # INFORMATION SET THROUGH t
        # ----------------------------------------------------------

        historical_prices = (
            prices
            .loc[:decision_date]
        )

        historical_returns = (
            returns
            .loc[:decision_date]
        )

        historical_macro = (
            macro
            .loc[:decision_date]
        )

        historical_regimes = (
            regimes
            .loc[:decision_date]
        )

        # ----------------------------------------------------------
        # LOOK-AHEAD SAFETY
        # ----------------------------------------------------------

        if (
            historical_prices.index.max()
            > decision_date
        ):

            fail(
                "LOOK-AHEAD VIOLATION: prices at "
                f"{decision_date}."
            )

        if (
            historical_returns.index.max()
            > decision_date
        ):

            fail(
                "LOOK-AHEAD VIOLATION: returns at "
                f"{decision_date}."
            )

        if (
            historical_macro.index.max()
            > decision_date
        ):

            fail(
                "LOOK-AHEAD VIOLATION: macro at "
                f"{decision_date}."
            )

        if (
            historical_regimes.index.max()
            > decision_date
        ):

            fail(
                "LOOK-AHEAD VIOLATION: regimes at "
                f"{decision_date}."
            )

        if (
            historical_prices.index.min()
            != prices.index.min()
        ):

            fail(
                "Historical price window was unexpectedly "
                "truncated at "
                f"{decision_date}."
            )

        # ----------------------------------------------------------
        # POINT-IN-TIME MACRO
        # ----------------------------------------------------------

        macro_data = (
            build_point_in_time_macro_data(
                macro,
                decision_date,
            )
        )

        # ----------------------------------------------------------
        # POINT-IN-TIME EXPECTED RETURNS
        # ----------------------------------------------------------

        expected_returns = (
            build_point_in_time_expected_returns(
                prices,
                decision_date,
            )
        )

        # ----------------------------------------------------------
        # PORTFOLIO INPUT
        # ----------------------------------------------------------

        portfolio = (
            build_initial_portfolio()
        )

        # ----------------------------------------------------------
        # PRODUCTION DECISION
        # ----------------------------------------------------------

        decision = engine.decide(
            portfolio=portfolio,

            returns=historical_returns,

            macro_data=macro_data,

            expected_returns=expected_returns,

            regimes=historical_regimes,

            scenarios=None,
        )

        if decision.status == "FAILED":

            fail(
                "Production decision failed at "
                f"{decision_date}: "
                f"{decision.errors}"
            )

        if decision.approved is not True:

            fail(
                "Production decision was not approved at "
                f"{decision_date}: "
                f"{decision.errors}"
            )

        # ----------------------------------------------------------
        # EXTRACT FINAL PRODUCTION WEIGHTS
        # ----------------------------------------------------------

        weights = {
            ticker: float(
                decision.weights.get(
                    ticker,
                    0.0,
                )
            )
            for ticker in TICKERS
        }

        # ----------------------------------------------------------
        # WEIGHT VALIDATION
        # ----------------------------------------------------------

        weight_array = np.asarray(
            list(
                weights.values()
            ),
            dtype=float,
        )

        if not np.isfinite(
            weight_array
        ).all():

            fail(
                f"Non-finite production weights at "
                f"{decision_date}."
            )

        weight_sum = float(
            weight_array.sum()
        )

        if abs(
            weight_sum - 1.0
        ) > TOLERANCE:

            fail(
                "Production weights do not sum to one at "
                f"{decision_date}: {weight_sum}"
            )

        if (
            np.abs(
                weight_array
            )
            > 1.0 + TOLERANCE
        ).any():

            fail(
                "Individual production weight exceeds "
                f"100% at {decision_date}."
            )

        # ----------------------------------------------------------
        # ACTIVE POSITIONS
        # ----------------------------------------------------------

        active_positions = sum(
            1
            for weight in weight_array
            if abs(weight) > TOLERANCE
        )

        if active_positions < 1:

            fail(
                f"Production engine produced no active "
                f"positions at {decision_date}."
            )

        # ----------------------------------------------------------
        # TURNOVER
        # ----------------------------------------------------------

        turnover = (
            calculate_turnover(
                previous_weights,
                weights,
            )
        )

        transaction_cost = (
            calculate_transaction_cost(
                turnover
            )
        )

        # ----------------------------------------------------------
        # FUTURE HOLDING PERIOD
        #
        # CRITICAL:
        #
        # Decision at t is applied beginning at t+1.
        # ----------------------------------------------------------

        future_start_position = (
            position + 1
        )

        future_end_position = (
            next_position
        )

        if (
            future_start_position
            > future_end_position
        ):

            continue

        future_dates = (
            common_index[
                future_start_position:
                future_end_position + 1
            ]
        )

        future_returns = (
            returns
            .loc[
                future_dates
            ]
        )

        if future_returns.empty:

            continue

        # ----------------------------------------------------------
        # FUTURE DATA SAFETY CHECK
        # ----------------------------------------------------------

        if (
            future_returns.index.min()
            <= decision_date
        ):

            fail(
                "LOOK-AHEAD / TIMING VIOLATION: realized "
                "holding period includes decision date."
            )

        if (
            future_returns.index.min()
            != common_index[
                position + 1
            ]
        ):

            fail(
                "Holding period does not begin on the first "
                "trading observation after the decision date."
            )

        # ----------------------------------------------------------
        # STRATEGY REALIZED RETURNS
        # ----------------------------------------------------------

        weight_series = pd.Series(
            weights,
            dtype=float,
        )

        strategy_period_returns = (
            future_returns
            .mul(
                weight_series,
                axis=1,
            )
            .sum(
                axis=1
            )
        )

        # ----------------------------------------------------------
        # TRANSACTION COST
        #
        # Charged on first realized day after the rebalance.
        # ----------------------------------------------------------

        first_realized_date = (
            strategy_period_returns.index[0]
        )

        strategy_period_returns = (
            strategy_period_returns
            .copy()
        )

        strategy_period_returns.loc[
            first_realized_date
        ] -= transaction_cost

        # ----------------------------------------------------------
        # BENCHMARK
        # ----------------------------------------------------------

        benchmark_period_returns = (
            future_returns[
                BENCHMARK
            ]
            .copy()
        )

        # ----------------------------------------------------------
        # REGISTRY-QUALIFIED EQUAL-WEIGHT BENCHMARK
        # ----------------------------------------------------------

        equal_weight_period_returns = (
            future_returns
            .mean(
                axis=1
            )
        )

        # ----------------------------------------------------------
        # SANITY
        # ----------------------------------------------------------

        for series_name, series in {
            "strategy": strategy_period_returns,
            "benchmark": benchmark_period_returns,
            "equal_weight": equal_weight_period_returns,
        }.items():

            if series.isna().any():

                fail(
                    f"{series_name} contains NaN values "
                    f"at {decision_date}."
                )

            if not np.isfinite(
                series.to_numpy(
                    dtype=float
                )
            ).all():

                fail(
                    f"{series_name} contains non-finite "
                    f"values at {decision_date}."
                )

        # ----------------------------------------------------------
        # STORE DAILY RETURNS
        # ----------------------------------------------------------

        daily_strategy_returns.append(
            strategy_period_returns
        )

        daily_benchmark_returns.append(
            benchmark_period_returns
        )

        daily_equal_weight_returns.append(
            equal_weight_period_returns
        )

        # ----------------------------------------------------------
        # PERIOD-LEVEL RETURNS
        # ----------------------------------------------------------

        period_strategy_return = float(
            (
                1.0
                + strategy_period_returns
            ).prod()
            - 1.0
        )

        period_benchmark_return = float(
            (
                1.0
                + benchmark_period_returns
            ).prod()
            - 1.0
        )

        period_equal_weight_return = float(
            (
                1.0
                + equal_weight_period_returns
            ).prod()
            - 1.0
        )

        # ----------------------------------------------------------
        # AUDIT RECORD
        # ----------------------------------------------------------

        observations.append(
            BacktestObservation(
                date=decision_date,

                next_date=next_date,

                regime=str(
                    decision.regime
                ).lower(),

                training_observations=len(
                    historical_returns
                ),

                holding_observations=len(
                    future_returns
                ),

                portfolio_return=(
                    period_strategy_return
                ),

                benchmark_return=(
                    period_benchmark_return
                ),

                equal_weight_return=(
                    period_equal_weight_return
                ),

                turnover=turnover,

                transaction_cost=transaction_cost,

                gross_exposure=float(
                    decision.gross_exposure
                ),

                net_exposure=float(
                    decision.net_exposure
                ),

                active_positions=active_positions,

                weights=weights,

                expected_returns=expected_returns,
            )
        )

        # ----------------------------------------------------------
        # STATE UPDATE
        # ----------------------------------------------------------

        previous_weights = (
            weights.copy()
        )

        # ----------------------------------------------------------
        # PROGRESS
        # ----------------------------------------------------------

        if (
            counter == 1
            or counter % 10 == 0
            or counter == len(
                rebalance_positions
            )
        ):

            print(
                f"[{counter:03d}/"
                f"{len(rebalance_positions):03d}] "
                f"{decision_date.date()} -> "
                f"{next_date.date()} | "
                f"regime={decision.regime} | "
                f"active={active_positions:02d} | "
                f"turnover={turnover:.6f} | "
                f"period_return="
                f"{period_strategy_return:.6f}"
            )

    # --------------------------------------------------------------
    # FINAL REALIZED RETURN STREAMS
    # --------------------------------------------------------------

    if not daily_strategy_returns:

        fail(
            "Backtest produced no realized strategy returns."
        )

    strategy_returns = (
        pd.concat(
            daily_strategy_returns
        )
        .sort_index()
    )

    benchmark_returns = (
        pd.concat(
            daily_benchmark_returns
        )
        .sort_index()
    )

    equal_weight_returns = (
        pd.concat(
            daily_equal_weight_returns
        )
        .sort_index()
    )

    # --------------------------------------------------------------
    # Duplicate-date validation.
    # --------------------------------------------------------------

    if strategy_returns.index.duplicated().any():

        fail(
            "Strategy realized return stream contains "
            "duplicate dates."
        )

    if benchmark_returns.index.duplicated().any():

        fail(
            "Benchmark return stream contains duplicate dates."
        )

    if equal_weight_returns.index.duplicated().any():

        fail(
            "Equal-weight return stream contains duplicate dates."
        )

    # --------------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------------

    results = pd.DataFrame(
        {
            "strategy": strategy_returns,
            "spy": benchmark_returns,
            "equal_weight_14": equal_weight_returns,
        }
    ).sort_index()

    if results.empty:

        fail(
            "Final backtest result is empty."
        )

    if results.isna().any().any():

        fail(
            "Final backtest result contains NaN values."
        )

    if not np.isfinite(
        results.to_numpy(
            dtype=float
        )
    ).all():

        fail(
            "Final backtest result contains "
            "non-finite values."
        )

    return (
        results,
        engine,
        observations,
    )


# ======================================================================
# SECTION 17 — REGIME ATTRIBUTION
# ======================================================================


def build_regime_attribution(
    observations: list[
        BacktestObservation
    ],
) -> pd.DataFrame:

    if not observations:

        return pd.DataFrame()

    rows = []

    for observation in observations:

        rows.append(
            {
                "date": observation.date,

                "next_date": observation.next_date,

                "regime": observation.regime,

                "training_observations": (
                    observation.training_observations
                ),

                "holding_observations": (
                    observation.holding_observations
                ),

                "portfolio_return": (
                    observation.portfolio_return
                ),

                "benchmark_return": (
                    observation.benchmark_return
                ),

                "equal_weight_return": (
                    observation.equal_weight_return
                ),

                "turnover": (
                    observation.turnover
                ),

                "transaction_cost": (
                    observation.transaction_cost
                ),

                "gross_exposure": (
                    observation.gross_exposure
                ),

                "net_exposure": (
                    observation.net_exposure
                ),

                "active_positions": (
                    observation.active_positions
                ),

                **{
                    f"weight_{ticker}": (
                        observation.weights[
                            ticker
                        ]
                    )
                    for ticker in TICKERS
                },
            }
        )

    frame = pd.DataFrame(
        rows
    )

    frame["date"] = pd.to_datetime(
        frame["date"]
    )

    frame["next_date"] = pd.to_datetime(
        frame["next_date"]
    )

    return frame


# ======================================================================
# SECTION 18 — PERFORMANCE REPORT
# ======================================================================


def print_performance_block(
    name: str,
    returns: pd.Series,
) -> None:

    metrics = calculate_metrics(
        returns
    )

    print()
    print(
        name
    )

    print(
        "-" * len(name)
    )

    for key, value in metrics.items():

        print(
            f"{key}: {value:.8f}"
        )


def print_report(
    results: pd.DataFrame,
    engine,
    observations: list[
        BacktestObservation
    ],
) -> None:

    banner(
        "5. STEP 9 BACKTEST RESULTS"
    )

    print_performance_block(
        "REGISTRY-QUALIFIED PRODUCTION STRATEGY",
        results[
            "strategy"
        ],
    )

    print_performance_block(
        "SPY BENCHMARK",
        results[
            "spy"
        ],
    )

    print_performance_block(
        "REGISTRY-QUALIFIED EQUAL-WEIGHT BENCHMARK",
        results[
            "equal_weight_14"
        ],
    )

    # --------------------------------------------------------------
    # Relative performance.
    # --------------------------------------------------------------

    strategy_cumulative = (
        (
            1.0
            + results[
                "strategy"
            ]
        ).prod()
        - 1.0
    )

    spy_cumulative = (
        (
            1.0
            + results[
                "spy"
            ]
        ).prod()
        - 1.0
    )

    equal_cumulative = (
        (
            1.0
            + results[
                "equal_weight_14"
            ]
        ).prod()
        - 1.0
    )

    print()
    print(
        "CUMULATIVE PERFORMANCE COMPARISON:"
    )

    print(
        f"Strategy: "
        f"{strategy_cumulative:.8f}"
    )

    print(
        f"SPY: "
        f"{spy_cumulative:.8f}"
    )

    print(
        f"registry-qualified equal weight: "
        f"{equal_cumulative:.8f}"
    )

    print()
    print(
        "STRATEGY - SPY:"
    )

    print(
        f"{strategy_cumulative - spy_cumulative:.8f}"
    )

    print()
    print(
        "STRATEGY - REGISTRY-QUALIFIED EQUAL WEIGHT:"
    )

    print(
        f"{strategy_cumulative - equal_cumulative:.8f}"
    )

    # --------------------------------------------------------------
    # Trading friction.
    # --------------------------------------------------------------

    total_turnover = float(
        sum(
            observation.turnover
            for observation in observations
        )
    )

    total_transaction_cost = float(
        sum(
            observation.transaction_cost
            for observation in observations
        )
    )

    average_turnover = (
        total_turnover
        / len(observations)
    )

    print()
    print(
        "TRADING FRICTION:"
    )

    print(
        f"Rebalances: "
        f"{len(observations)}"
    )

    print(
        f"Total turnover: "
        f"{total_turnover:.8f}"
    )

    print(
        f"Average turnover: "
        f"{average_turnover:.8f}"
    )

    print(
        f"Total transaction-cost drag: "
        f"{total_transaction_cost:.8f}"
    )

    # --------------------------------------------------------------
    # Exposure.
    # --------------------------------------------------------------

    gross_exposures = pd.Series(
        [
            observation.gross_exposure
            for observation in observations
        ]
    )

    net_exposures = pd.Series(
        [
            observation.net_exposure
            for observation in observations
        ]
    )

    active_positions = pd.Series(
        [
            observation.active_positions
            for observation in observations
        ]
    )

    print()
    print(
        "EXPOSURE:"
    )

    print(
        f"Average gross exposure: "
        f"{gross_exposures.mean():.8f}"
    )

    print(
        f"Maximum gross exposure: "
        f"{gross_exposures.max():.8f}"
    )

    print(
        f"Average net exposure: "
        f"{net_exposures.mean():.8f}"
    )

    print(
        f"Maximum active positions: "
        f"{int(active_positions.max())}"
    )

    print(
        f"Minimum active positions: "
        f"{int(active_positions.min())}"
    )

    # --------------------------------------------------------------
    # Regime attribution.
    # --------------------------------------------------------------

    attribution = (
        build_regime_attribution(
            observations
        )
    )

    if not attribution.empty:

        print()
        print(
            "REGIME ATTRIBUTION:"
        )

        regime_rows = []

        for regime, group in (
            attribution
            .groupby(
                "regime"
            )
        ):

            period_return = float(
                (
                    1.0
                    + group[
                        "portfolio_return"
                    ]
                ).prod()
                - 1.0
            )

            benchmark_return = float(
                (
                    1.0
                    + group[
                        "benchmark_return"
                    ]
                ).prod()
                - 1.0
            )

            equal_return = float(
                (
                    1.0
                    + group[
                        "equal_weight_return"
                    ]
                ).prod()
                - 1.0
            )

            regime_rows.append(
                {
                    "regime": regime,
                    "observations": len(group),
                    "strategy_return": period_return,
                    "spy_return": benchmark_return,
                    "equal_weight_return": equal_return,
                    "average_turnover": float(
                        group[
                            "turnover"
                        ].mean()
                    ),
                    "transaction_cost": float(
                        group[
                            "transaction_cost"
                        ].sum()
                    ),
                    "average_active_positions": float(
                        group[
                            "active_positions"
                        ].mean()
                    ),
                    "average_gross_exposure": float(
                        group[
                            "gross_exposure"
                        ].mean()
                    ),
                }
            )

        regime_summary = pd.DataFrame(
            regime_rows
        ).set_index(
            "regime"
        )

        print(
            regime_summary
        )

        print()
        print(
            "AVERAGE REGIME WEIGHTS:"
        )

        weight_columns = [
            f"weight_{ticker}"
            for ticker in TICKERS
        ]

        print(
            attribution
            .groupby(
                "regime"
            )[
                weight_columns
            ]
            .mean()
        )

    # --------------------------------------------------------------
    # FINAL ENGINE HEALTH.
    # --------------------------------------------------------------

    print()
    print(
        "FINAL ENGINE HEALTH:"
    )

    health = (
        engine.health_check()
    )

    print(
        health
    )

    if health.get(
        "healthy"
    ) is not True:

        fail(
            "Production engine became unhealthy during "
            "the historical backtest."
        )


# ======================================================================
# SECTION 19 — BACKTEST VALIDATION
# ======================================================================


def validate_backtest(
    results: pd.DataFrame,
    observations: list[
        BacktestObservation
    ],
) -> None:

    banner(
        "6. STEP 9 VALIDATION"
    )

    # --------------------------------------------------------------
    # Result-level validation.
    # --------------------------------------------------------------

    if results.empty:

        fail(
            "Backtest result is empty."
        )

    if results.isna().any().any():

        fail(
            "Backtest results contain NaN values."
        )

    if not np.isfinite(
        results.to_numpy(
            dtype=float
        )
    ).all():

        fail(
            "Backtest results contain non-finite values."
        )

    if not results.index.is_monotonic_increasing:

        fail(
            "Backtest dates are not chronological."
        )

    if not results.index.is_unique:

        fail(
            "Backtest contains duplicate dates."
        )

    # --------------------------------------------------------------
    # Required result columns.
    # --------------------------------------------------------------

    required_columns = {
        "strategy",
        "spy",
        "equal_weight_14",
    }

    if not required_columns.issubset(
        results.columns
    ):

        fail(
            "Backtest result is missing required "
            f"columns: "
            f"{required_columns - set(results.columns)}"
        )

    # --------------------------------------------------------------
    # Observation-level validation.
    # --------------------------------------------------------------

    if not observations:

        fail(
            "No backtest observations were recorded."
        )

    valid_regimes = {
        "expansion",
        "slowdown",
        "recession",
        "recovery",
        "bull",
        "neutral",
        "crisis",
    }

    for observation in observations:

        if observation.regime not in valid_regimes:

            fail(
                "Unknown regime encountered: "
                f"{observation.regime}"
            )

        if (
            observation.training_observations
            < MIN_TRAINING_OBSERVATIONS
        ):

            fail(
                "Training window below minimum at "
                f"{observation.date}."
            )

        if (
            observation.holding_observations
            < 1
        ):

            fail(
                "No holding observations at "
                f"{observation.date}."
            )

        if (
            observation.next_date
            <= observation.date
        ):

            fail(
                "Next rebalance date is not after "
                f"decision date {observation.date}."
            )

        weight_sum = sum(
            observation.weights.values()
        )

        if abs(
            weight_sum - 1.0
        ) > TOLERANCE:

            fail(
                "Weights failed validation at "
                f"{observation.date}: "
                f"{weight_sum}"
            )

        if observation.turnover < -TOLERANCE:

            fail(
                "Negative turnover encountered."
            )

        if observation.transaction_cost < -TOLERANCE:

            fail(
                "Negative transaction cost encountered."
            )

        if observation.active_positions < 1:

            fail(
                "No active positions at "
                f"{observation.date}."
            )

        if observation.active_positions > len(
            TICKERS
        ):

            fail(
                "Active position count exceeds "
                "registry-qualified universe."
            )

        if not np.isfinite(
            observation.portfolio_return
        ):

            fail(
                "Non-finite portfolio return."
            )

    # --------------------------------------------------------------
    # Verify all registered paper-qualified assets are represented in every decision.
    #
    # A weight may be zero, but the asset must exist in the decision
    # vector.
    # --------------------------------------------------------------

    for observation in observations:

        if set(
            observation.weights.keys()
        ) != set(TICKERS):

            fail(
                "Decision weight vector does not contain "
                "exactly the registered paper-qualified assets at "
                f"{observation.date}."
            )

        if set(
            observation.expected_returns.keys()
        ) != set(TICKERS):

            fail(
                "Expected-return vector does not contain "
                "exactly the registered paper-qualified assets at "
                f"{observation.date}."
            )

    # --------------------------------------------------------------
    # Verify first realized return occurs strictly after the first
    # decision date.
    # --------------------------------------------------------------

    first_decision = observations[0].date

    first_realized = results.index[0]

    if first_realized <= first_decision:

        fail(
            "Realized returns begin on or before the first "
            "decision date."
        )

    # --------------------------------------------------------------
    # Strategy must actually contain realized variation.
    # --------------------------------------------------------------

    if (
        results[
            "strategy"
        ].abs().sum()
        <= TOLERANCE
    ):

        fail(
            "Strategy produced no realized return variation."
        )

    # --------------------------------------------------------------
    # Transaction-cost validation.
    # --------------------------------------------------------------

    expected_cost = (
        sum(
            observation.turnover
            for observation in observations
        )
        * TRANSACTION_COST_BPS
        / 10000.0
    )

    actual_cost = (
        sum(
            observation.transaction_cost
            for observation in observations
        )
    )

    if abs(
        expected_cost
        - actual_cost
    ) > TOLERANCE:

        fail(
            "Transaction-cost calculation is inconsistent."
        )

    # --------------------------------------------------------------
    # Exposure validation.
    # --------------------------------------------------------------

    for observation in observations:

        if observation.gross_exposure < -TOLERANCE:

            fail(
                "Gross exposure cannot be negative."
            )

        if not np.isfinite(
            observation.gross_exposure
        ):

            fail(
                "Gross exposure is non-finite."
            )

        if not np.isfinite(
            observation.net_exposure
        ):

            fail(
                "Net exposure is non-finite."
            )

    print()
    print(
        "Validation checks:"
    )

    print(
        "registry-qualified universe: PASS"
    )

    print(
        "Chronological results: PASS"
    )

    print(
        "No NaN results: PASS"
    )

    print(
        "No non-finite results: PASS"
    )

    print(
        "registry-qualified decision vectors: PASS"
    )

    print(
        "Weight sums: PASS"
    )

    print(
        "Training-window validation: PASS"
    )

    print(
        "Holding-period validation: PASS"
    )

    print(
        "Transaction-cost validation: PASS"
    )

    print(
        "Look-ahead timing validation: PASS"
    )

    print(
        "Realized return validation: PASS"
    )

    print()
    print(
        "Backtest observations:",
        len(observations),
    )

    print(
        "Realized return observations:",
        len(results),
    )

    print()
    print(
        "STEP 9 VALIDATION: PASSED"
    )


# ======================================================================
# SECTION 20 — DETERMINISM TEST
# ======================================================================


def validate_deterministic_decisions(
    observations_a: list[
        BacktestObservation
    ],
    observations_b: list[
        BacktestObservation
    ],
) -> None:
    """
    Validate that repeated production decisions are deterministic.

    This compares the decision-level audit output rather than relying
    on object identity.
    """

    if len(
        observations_a
    ) != len(
        observations_b
    ):

        fail(
            "Determinism failure: different number "
            "of observations."
        )

    for first, second in zip(
        observations_a,
        observations_b,
    ):

        if first.date != second.date:

            fail(
                "Determinism failure: decision dates differ."
            )

        if first.regime != second.regime:

            fail(
                "Determinism failure: regimes differ."
            )

        if first.active_positions != (
            second.active_positions
        ):

            fail(
                "Determinism failure: active position "
                "counts differ."
            )

        for ticker in TICKERS:

            if not np.isclose(
                first.weights[ticker],
                second.weights[ticker],
                atol=TOLERANCE,
                rtol=TOLERANCE,
            ):

                fail(
                    "Determinism failure for "
                    f"{ticker} at {first.date}: "
                    f"{first.weights[ticker]} != "
                    f"{second.weights[ticker]}"
                )

    print()
    print(
        "DETERMINISM CHECK: PASSED"
    )


# ======================================================================
# SECTION 21 — MAIN
# ======================================================================


def main() -> None:

    banner(
        "STEP 9 — REGISTRY-QUALIFIED HISTORICAL WALK-FORWARD "
        "REGIME-SWITCHING BACKTEST"
    )

    print()
    print(
        "Python:",
        sys.version,
    )

    print()
    print(
        "Working directory:",
        os.getcwd(),
    )

    print()
    print(
        "History period:",
        HISTORY_PERIOD,
    )

    print()
    print(
        "Minimum training observations:",
        MIN_TRAINING_OBSERVATIONS,
    )

    print()
    print(
        "Rebalance interval:",
        REBALANCE_INTERVAL,
        "trading days",
    )

    print()
    print(
        "Transaction cost:",
        TRANSACTION_COST_BPS,
        "bps",
    )

    # --------------------------------------------------------------
    # UNIVERSE
    # --------------------------------------------------------------

    validate_universe()

    # --------------------------------------------------------------
    # MARKET DATA
    # --------------------------------------------------------------

    prices, returns = (
        load_market_data()
    )

    # --------------------------------------------------------------
    # FRED
    # --------------------------------------------------------------

    macro = (
        load_fred_data(
            prices.index
        )
    )

    # --------------------------------------------------------------
    # REGIMES
    # --------------------------------------------------------------

    regimes = (
        build_regime_history(
            macro
        )
    )

    # --------------------------------------------------------------
    # BACKTEST
    # --------------------------------------------------------------

    results, engine, observations = (
        run_backtest(
            prices=prices,
            returns=returns,
            macro=macro,
            regimes=regimes,
        )
    )

    # --------------------------------------------------------------
    # VALIDATE
    # --------------------------------------------------------------

    validate_backtest(
        results=results,
        observations=observations,
    )

    # --------------------------------------------------------------
    # REPORT
    # --------------------------------------------------------------

    print_report(
        results=results,
        engine=engine,
        observations=observations,
    )

    # --------------------------------------------------------------
    # FINAL STATUS
    # --------------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "STEP 9 PASSED — REGISTRY-QUALIFIED HISTORICAL "
        "WALK-FORWARD BACKTEST SUCCESSFUL"
    )
    print("=" * 80)


# ======================================================================
# EXECUTION
# ======================================================================


if __name__ == "__main__":

    main()