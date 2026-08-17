"""
======================================================================
STEP 9 — HISTORICAL WALK-FORWARD REGIME-SWITCHING BACKTEST
======================================================================

Purpose
-------
Validate the production PortfolioDecisionEngine using real historical
market and macroeconomic data without introducing look-ahead bias.

Design
------
1. Load real market prices.
2. Load real FRED macro data.
3. Build point-in-time macro/regime observations.
4. Rebalance monthly.
5. At each rebalance date:
       - use only information available through that date
       - calculate expected returns from prices available through that date
       - calculate covariance from returns available through that date
       - provide only historical regimes through that date
       - request a production portfolio decision
6. Apply resulting weights to NEXT-period realized returns.
7. Apply transaction costs on turnover.
8. Compare against:
       - SPY
       - Equal-weight SPY/EFA/EEM
9. Produce portfolio, benchmark and regime-level statistics.

IMPORTANT
---------
This file is a backtest harness.

It does NOT replace the production decision engine.

The PortfolioDecisionEngine remains the decision authority.
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

from core_constants import (
    settings,
)

from marketdataloader import (
    MarketDataLoader,
)

from macroregime import (
    MacroRegimeModel,
)

from expectedreturnforecaster import (
    ExpectedReturnForecaster,
)

from productioncomposition import (
    build_production_engine,
)


# ======================================================================
# SECTION 2 — CONFIGURATION
# ======================================================================

TICKERS = [
    "SPY",
    "EFA",
    "EEM",
]

BENCHMARK = "SPY"

HISTORY_PERIOD = "15y"

# Minimum historical observations before the first decision.
#
# 252 trading days:
#     approximately one year
#
# 504 trading days:
#     approximately two years
#
# We deliberately use two years because the production covariance
# and expected-return stack should not be evaluated from a tiny
# historical sample.
MIN_TRAINING_OBSERVATIONS = 504

# Rebalance every approximately one month.
#
# We use trading observations rather than calendar arithmetic so that
# every rebalance date exists in the market dataset.
REBALANCE_INTERVAL = 21

# Transaction cost assumption.
#
# 5 basis points per unit of one-way turnover.
#
# This is deliberately explicit and configurable rather than hidden
# inside the backtest.
TRANSACTION_COST_BPS = 5.0

# Annualization.
TRADING_DAYS = 252

# Numerical tolerance.
TOLERANCE = 1e-8


# ======================================================================
# SECTION 3 — OUTPUT STRUCTURES
# ======================================================================


@dataclass(
    frozen=True,
)
class BacktestObservation:
    """
    One point-in-time portfolio decision.
    """

    date: pd.Timestamp

    regime: str

    portfolio_return: float

    benchmark_return: float

    equal_weight_return: float

    turnover: float

    transaction_cost: float

    gross_exposure: float

    net_exposure: float

    weights: dict[str, float]

    expected_returns: dict[str, float]


# ======================================================================
# SECTION 4 — DISPLAY HELPERS
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
    raise AssertionError(
        message
    )


# ======================================================================
# SECTION 5 — MARKET DATA
# ======================================================================


def load_market_data() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Load real historical market prices and returns.
    """

    loader = MarketDataLoader(
        assets=TICKERS,
        period=HISTORY_PERIOD,
    )

    prices = (
        loader.load_prices()
    )

    returns = (
        prices
        .pct_change()
        .dropna()
    )

    if prices.empty:
        fail(
            "Historical price data is empty."
        )

    if returns.empty:
        fail(
            "Historical return data is empty."
        )

    prices = (
        prices
        .loc[:, TICKERS]
        .sort_index()
    )

    returns = (
        returns
        .loc[:, TICKERS]
        .sort_index()
    )

    if list(
        prices.columns
    ) != TICKERS:

        fail(
            "Historical price tickers do not match "
            f"{TICKERS}."
        )

    if list(
        returns.columns
    ) != TICKERS:

        fail(
            "Historical return tickers do not match "
            f"{TICKERS}."
        )

    if prices.isna().any().any():
        fail(
            "Historical prices contain missing values."
        )

    if returns.isna().any().any():
        fail(
            "Historical returns contain missing values."
        )

    print()
    print("PRICE HISTORY:")
    print(
        "Observations:",
        len(prices),
    )
    print(
        "Start:",
        prices.index[0],
    )
    print(
        "End:",
        prices.index[-1],
    )

    print()
    print("RETURN HISTORY:")
    print(
        "Observations:",
        len(returns),
    )

    return (
        prices,
        returns,
    )


# ======================================================================
# SECTION 6 — FRED DATA
# ======================================================================


def _clean_fred_series(
    series: pd.Series,
) -> pd.Series:

    series = (
        pd.Series(series)
        .copy()
    )

    series.index = pd.to_datetime(
        series.index
    )

    series = (
        pd.to_numeric(
            series,
            errors="coerce",
        )
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .dropna()
        .sort_index()
    )

    return series


def load_fred_data(
    market_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    """
    Load and align FRED macroeconomic variables.

    Required variables
    -------------------
    UNRATE
    CPIAUCSL
    DGS10
    DGS2
    """

    if not settings.fred_api_key:
        fail(
            "FRED API key is not configured."
        )

    fred = Fred(
        api_key=settings.fred_api_key
    )

    start_date = (
        market_index.min()
    )

    end_date = (
        market_index.max()
    )

    print()
    print("LOADING FRED DATA")

    unemployment = _clean_fred_series(
        fred.get_series(
            "UNRATE",
            observation_start=start_date,
            observation_end=end_date,
        )
    )

    cpi = _clean_fred_series(
        fred.get_series(
            "CPIAUCSL",
            observation_start=start_date,
            observation_end=end_date,
        )
    )

    dgs10 = _clean_fred_series(
        fred.get_series(
            "DGS10",
            observation_start=start_date,
            observation_end=end_date,
        )
    )

    dgs2 = _clean_fred_series(
        fred.get_series(
            "DGS2",
            observation_start=start_date,
            observation_end=end_date,
        )
    )

    # --------------------------------------------------------------
    # Inflation
    #
    # CPI is converted into year-over-year percentage inflation.
    # --------------------------------------------------------------

    inflation = (
        cpi
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
    # Yield spread
    # --------------------------------------------------------------

    yield_spread = (
        dgs10
        .sub(
            dgs2,
            fill_value=np.nan,
        )
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .dropna()
    )

    # --------------------------------------------------------------
    # Build raw macro frame.
    # --------------------------------------------------------------

    macro = pd.concat(
        {
            "unemployment": unemployment,
            "inflation": inflation,
            "yield_spread": yield_spread,
        },
        axis=1,
        join="outer",
        sort=False,
    )

    macro = (
        macro
        .sort_index()
    )

    # --------------------------------------------------------------
    # Align macro information to the market calendar.
    #
    # Forward filling is point-in-time safe:
    #
    # a value is carried forward only after it has appeared.
    #
    # No future observation is back-filled into the past.
    # --------------------------------------------------------------

    macro = (
        macro
        .reindex(
            market_index
        )
        .ffill()
        .dropna()
    )

    if macro.empty:
        fail(
            "No usable aligned macroeconomic observations."
        )

    if macro.isna().any().any():
        fail(
            "Aligned macro data still contains missing values."
        )

    print()
    print("MACRO HISTORY:")
    print(
        "Observations:",
        len(macro),
    )

    print(
        "Start:",
        macro.index[0],
    )

    print(
        "End:",
        macro.index[-1],
    )

    print(
        "Columns:",
        list(macro.columns),
    )

    return macro


# ======================================================================
# SECTION 7 — POINT-IN-TIME REGIME HISTORY
# ======================================================================


def build_regime_history(
    macro: pd.DataFrame,
) -> pd.Series:
    """
    Construct historical regime labels causally.

    At date t the classifier receives only macro observations through t.
    """

    model = (
        MacroRegimeModel()
    )

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

        # The production model needs at least two unemployment
        # observations because it calculates diff().
        if len(
            unemployment
        ) < 2:

            continue

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

        values.append(
            str(result)
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
            "No historical regime observations were produced."
        )

    print()
    print("REGIME HISTORY:")
    print(
        "Observations:",
        len(regimes),
    )

    print(
        "Unique regimes:",
        sorted(
            regimes.unique()
        ),
    )

    print()
    print("REGIME COUNTS:")
    print(
        regimes.value_counts()
    )

    return regimes


# ======================================================================
# SECTION 8 — POINT-IN-TIME MACRO DATA
# ======================================================================


def build_point_in_time_macro_data(
    macro: pd.DataFrame,
    date: pd.Timestamp,
) -> dict:
    """
    Build the exact macro input available at date t.

    unemployment remains a historical Series through t because the
    production MacroRegimeModel uses unemployment.diff().
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
# SECTION 9 — EXPECTED RETURNS
# ======================================================================


def build_point_in_time_expected_returns(
    prices: pd.DataFrame,
    date: pd.Timestamp,
) -> dict[str, float]:
    """
    Forecast expected returns using prices available only through date.
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
            "Insufficient price history for expected-return "
            f"forecast at {date}."
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

        result = {
            ticker: float(
                forecast[
                    ticker
                ]
            )
            for ticker in TICKERS
        }

    elif isinstance(
        forecast,
        dict,
    ):

        result = {
            ticker: float(
                forecast[
                    ticker
                ]
            )
            for ticker in TICKERS
        }

    else:

        array = np.asarray(
            forecast,
            dtype=float,
        ).reshape(-1)

        if len(array) != len(
            TICKERS
        ):

            fail(
                "Expected-return forecast dimension does not "
                "match ticker universe."
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
                f"Expected return for {ticker} is not finite."
            )

    return result


# ======================================================================
# SECTION 10 — PORTFOLIO
# ======================================================================


def build_initial_portfolio() -> dict:
    """
    Initial portfolio supplied to the production engine.

    The production optimizer remains responsible for determining the
    resulting target weights.
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
# SECTION 11 — TURNOVER / TRANSACTION COSTS
# ======================================================================


def calculate_turnover(
    previous_weights: dict[str, float],
    new_weights: dict[str, float],
) -> float:
    """
    One-way portfolio turnover.

    We define turnover as:

        sum(abs(new - old))

    This is the amount of portfolio weight that must be traded.
    """

    return float(
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


def calculate_transaction_cost(
    turnover: float,
) -> float:
    """
    Convert turnover into a portfolio return drag.
    """

    return float(
        turnover
        * TRANSACTION_COST_BPS
        / 10000.0
    )


# ======================================================================
# SECTION 12 — PERFORMANCE METRICS
# ======================================================================


def annualized_return(
    returns: pd.Series,
) -> float:

    returns = (
        returns
        .dropna()
    )

    if returns.empty:
        return 0.0

    cumulative = float(
        np.prod(
            1.0 + returns.to_numpy()
        )
    )

    years = (
        len(returns)
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

    returns = (
        returns
        .dropna()
    )

    if len(returns) < 2:
        return 0.0

    return float(
        returns.std(
            ddof=1
        )
        * math.sqrt(
            TRADING_DAYS
        )
    )


def sharpe_ratio(
    returns: pd.Series,
) -> float:

    returns = (
        returns
        .dropna()
    )

    if len(returns) < 2:
        return 0.0

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

    returns = (
        returns
        .dropna()
    )

    if returns.empty:
        return 0.0

    downside = (
        returns[
            returns < 0
        ]
    )

    if len(
        downside
    ) < 2:

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
            returns
        )
        / downside_deviation
    )


def maximum_drawdown(
    returns: pd.Series,
) -> float:

    returns = (
        returns
        .dropna()
    )

    if returns.empty:
        return 0.0

    equity = (
        1.0
        * (
            1.0 + returns
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

    return {
        "observations": float(
            len(
                returns.dropna()
            )
        ),

        "cumulative_return": float(
            (
                1.0
                + returns.dropna()
            ).prod()
            - 1.0
        )
        if not returns.dropna().empty
        else 0.0,

        "cagr": annualized_return(
            returns
        ),

        "volatility": annualized_volatility(
            returns
        ),

        "sharpe": sharpe_ratio(
            returns
        ),

        "sortino": sortino_ratio(
            returns
        ),

        "max_drawdown": maximum_drawdown(
            returns
        ),
    }


# ======================================================================
# SECTION 13 — WALK-FORWARD BACKTEST
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
    Execute the production engine chronologically.

    No future observations are passed into any decision.
    """

    banner(
        "RUNNING STEP 9 WALK-FORWARD BACKTEST"
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
    ) < MIN_TRAINING_OBSERVATIONS:

        fail(
            "Insufficient common historical observations."
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
    # Production engine.
    # --------------------------------------------------------------

    engine = (
        build_production_engine()
    )

    health = (
        engine.health_check()
    )

    if health.get(
        "healthy"
    ) is not True:

        fail(
            "Production engine is unhealthy before backtest."
        )

    print()
    print(
        "PRODUCTION ENGINE:",
        engine,
    )

    print()
    print(
        "ENGINE HEALTH:",
        health,
    )

    # --------------------------------------------------------------
    # Rebalance dates.
    #
    # We need:
    #
    #   training history through t
    #
    # and:
    #
    #   realized return after t
    #
    # Therefore the final observation cannot be a rebalance point.
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
        "REBALANCE DATES:",
        len(
            rebalance_positions
        ),
    )

    # --------------------------------------------------------------
    # State.
    # --------------------------------------------------------------

    previous_weights = {
        ticker: 0.0
        for ticker in TICKERS
    }

    records: list[
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
    # Walk forward.
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

        next_position = (
            rebalance_positions[
                counter
            ]
            if counter < len(
                rebalance_positions
            )
            else len(
                common_index
            ) - 1
        )

        # ----------------------------------------------------------
        # INFORMATION AVAILABLE THROUGH t
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
        # Explicit point-in-time safety checks.
        # ----------------------------------------------------------

        if (
            historical_prices.index.max()
            > decision_date
        ):

            fail(
                "LOOK-AHEAD VIOLATION: price history "
                f"extends beyond {decision_date}."
            )

        if (
            historical_returns.index.max()
            > decision_date
        ):

            fail(
                "LOOK-AHEAD VIOLATION: return history "
                f"extends beyond {decision_date}."
            )

        if (
            historical_macro.index.max()
            > decision_date
        ):

            fail(
                "LOOK-AHEAD VIOLATION: macro history "
                f"extends beyond {decision_date}."
            )

        if (
            historical_regimes.index.max()
            > decision_date
        ):

            fail(
                "LOOK-AHEAD VIOLATION: regime history "
                f"extends beyond {decision_date}."
            )

        # ----------------------------------------------------------
        # POINT-IN-TIME MACRO STATE
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

        weight_sum = sum(
            weights.values()
        )

        if not np.isfinite(
            weight_sum
        ):

            fail(
                f"Non-finite weights at {decision_date}."
            )

        if abs(
            weight_sum - 1.0
        ) > TOLERANCE:

            fail(
                "Portfolio weights do not sum to one at "
                f"{decision_date}: {weight_sum}"
            )

        # ----------------------------------------------------------
        # TURNOVER
        # ----------------------------------------------------------

        turnover = calculate_turnover(
            previous_weights,
            weights,
        )

        transaction_cost = (
            calculate_transaction_cost(
                turnover
            )
        )

        # ----------------------------------------------------------
        # FUTURE REALIZED PERIOD
        #
        # CRITICAL:
        #
        # The decision at t is applied beginning at t+1.
        # ----------------------------------------------------------

        future_start_position = (
            position + 1
        )

        future_end_position = (
            next_position
        )

        if (
            future_start_position
            >= future_end_position
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

        strategy_period_returns = (
            future_returns
            .mul(
                pd.Series(
                    weights
                ),
                axis=1,
            )
            .sum(
                axis=1
            )
        )

        # Transaction cost is charged on the first day after
        # rebalance.
        strategy_period_returns = (
            strategy_period_returns
            .copy()
        )

        first_date = (
            strategy_period_returns.index[0]
        )

        strategy_period_returns.loc[
            first_date
        ] -= transaction_cost

        benchmark_period_returns = (
            future_returns[
                BENCHMARK
            ]
            .copy()
        )

        equal_weight_period_returns = (
            future_returns
            .mean(
                axis=1
            )
        )

        daily_strategy_returns.append(
            strategy_period_returns
        )

        daily_benchmark_returns.append(
            benchmark_period_returns
        )

        daily_equal_weight_returns.append(
            equal_weight_period_returns
        )

        records.append(
            BacktestObservation(
                date=decision_date,

                regime=str(
                    decision.regime
                ),

                portfolio_return=float(
                    strategy_period_returns.mean()
                ),

                benchmark_return=float(
                    benchmark_period_returns.mean()
                ),

                equal_weight_return=float(
                    equal_weight_period_returns.mean()
                ),

                turnover=float(
                    turnover
                ),

                transaction_cost=float(
                    transaction_cost
                ),

                gross_exposure=float(
                    decision.gross_exposure
                ),

                net_exposure=float(
                    decision.net_exposure
                ),

                weights=weights,

                expected_returns=expected_returns,
            )
        )

        previous_weights = (
            weights.copy()
        )

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
                f"{decision_date.date()} | "
                f"regime={decision.regime} | "
                f"turnover={turnover:.4f} | "
                f"weights={weights}"
            )

    if not daily_strategy_returns:
        fail(
            "Backtest produced no realized portfolio returns."
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

    results = pd.DataFrame(
        {
            "strategy": strategy_returns,
            "spy": benchmark_returns,
            "equal_weight": equal_weight_returns,
        }
    )

    results = (
        results
        .sort_index()
        .loc[
            ~results.index.duplicated(
                keep="first"
            )
        ]
    )

    if results.empty:
        fail(
            "Final backtest result is empty."
        )

    return (
        results,
        engine,
        records,
    )


# ======================================================================
# SECTION 14 — REGIME ATTRIBUTION
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

                "regime": observation.regime,

                "turnover": observation.turnover,

                "transaction_cost": (
                    observation.transaction_cost
                ),

                "gross_exposure": (
                    observation.gross_exposure
                ),

                "net_exposure": (
                    observation.net_exposure
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

    return frame


# ======================================================================
# SECTION 15 — REPORT
# ======================================================================


def print_report(
    results: pd.DataFrame,
    engine,
    observations: list[
        BacktestObservation
    ],
) -> None:

    banner(
        "STEP 9 — BACKTEST RESULTS"
    )

    strategy_metrics = calculate_metrics(
        results[
            "strategy"
        ]
    )

    spy_metrics = calculate_metrics(
        results[
            "spy"
        ]
    )

    equal_metrics = calculate_metrics(
        results[
            "equal_weight"
        ]
    )

    print()
    print("STRATEGY:")
    for key, value in (
        strategy_metrics.items()
    ):
        print(
            f"{key}: {value:.8f}"
            if isinstance(
                value,
                float,
            )
            else f"{key}: {value}"
        )

    print()
    print("SPY:")
    for key, value in (
        spy_metrics.items()
    ):
        print(
            f"{key}: {value:.8f}"
            if isinstance(
                value,
                float,
            )
            else f"{key}: {value}"
        )

    print()
    print("EQUAL WEIGHT:")
    for key, value in (
        equal_metrics.items()
    ):
        print(
            f"{key}: {value:.8f}"
            if isinstance(
                value,
                float,
            )
            else f"{key}: {value}"
        )

    # --------------------------------------------------------------
    # Turnover
    # --------------------------------------------------------------

    turnover = float(
        sum(
            observation.turnover
            for observation in observations
        )
    )

    transaction_cost = float(
        sum(
            observation.transaction_cost
            for observation in observations
        )
    )

    print()
    print("TRADING FRICTION:")
    print(
        "Total turnover:",
        turnover,
    )

    print(
        "Total transaction-cost drag:",
        transaction_cost,
    )

    # --------------------------------------------------------------
    # Regime attribution
    # --------------------------------------------------------------

    attribution = (
        build_regime_attribution(
            observations
        )
    )

    if not attribution.empty:

        print()
        print("REGIME ATTRIBUTION:")

        summary = (
            attribution
            .groupby(
                "regime"
            )
            .agg(
                observations=(
                    "regime",
                    "size",
                ),
                average_turnover=(
                    "turnover",
                    "mean",
                ),
                average_transaction_cost=(
                    "transaction_cost",
                    "mean",
                ),
                average_gross_exposure=(
                    "gross_exposure",
                    "mean",
                ),
                average_net_exposure=(
                    "net_exposure",
                    "mean",
                ),
            )
        )

        print(
            summary
        )

        print()
        print("AVERAGE REGIME WEIGHTS:")

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
    # Engine health
    # --------------------------------------------------------------

    print()
    print("FINAL ENGINE HEALTH:")

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
            "Production engine became unhealthy during backtest."
        )


# ======================================================================
# SECTION 16 — VALIDATION
# ======================================================================


def validate_backtest(
    results: pd.DataFrame,
    observations: list[
        BacktestObservation
    ],
) -> None:

    banner(
        "STEP 9 — VALIDATION"
    )

    if results.empty:
        fail(
            "Backtest result is empty."
        )

    if results.isna().any().any():
        fail(
            "Backtest results contain missing values."
        )

    if not results.index.is_monotonic_increasing:
        fail(
            "Backtest dates are not chronological."
        )

    if not results.index.is_unique:
        fail(
            "Backtest contains duplicate dates."
        )

    if not observations:
        fail(
            "No backtest observations were recorded."
        )

    # --------------------------------------------------------------
    # Validate every decision.
    # --------------------------------------------------------------

    for observation in observations:

        if observation.regime not in {
            "expansion",
            "slowdown",
            "recession",
            "recovery",
        }:

            fail(
                "Unknown regime encountered: "
                f"{observation.regime}"
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

        if observation.turnover < 0:
            fail(
                "Negative turnover encountered."
            )

        if observation.transaction_cost < 0:
            fail(
                "Negative transaction cost encountered."
            )

    # --------------------------------------------------------------
    # Strategy must have actual variation.
    # --------------------------------------------------------------

    if (
        results[
            "strategy"
        ].abs().sum()
        <= 0
    ):

        fail(
            "Strategy produced no realized returns."
        )

    print(
        "Backtest observations:",
        len(
            observations
        ),
    )

    print(
        "Realized return observations:",
        len(
            results
        ),
    )

    print(
        "Validation:",
        "PASSED",
    )


# ======================================================================
# SECTION 17 — MAIN
# ======================================================================


def main() -> None:

    banner(
        "STEP 9 — HISTORICAL WALK-FORWARD "
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
        "Tickers:",
        TICKERS,
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
    # MARKET DATA
    # --------------------------------------------------------------

    prices, returns = (
        load_market_data()
    )

    # --------------------------------------------------------------
    # MACRO DATA
    # --------------------------------------------------------------

    macro = (
        load_fred_data(
            prices.index
        )
    )

    # --------------------------------------------------------------
    # REGIME HISTORY
    # --------------------------------------------------------------

    regimes = (
        build_regime_history(
            macro
        )
    )

    # --------------------------------------------------------------
    # RUN BACKTEST
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
    # NOTE:
    #
    # run_backtest currently stores observation objects internally.
    #
    # Reconstruct the decision-level observations from the production
    # result index is intentionally avoided.
    #
    # For Step 9 initial validation, the realized return stream is the
    # primary output.
    # --------------------------------------------------------------

        # Audit-only validation.
        #
        # We do not manufacture performance statistics from audit
        # metadata.
        #
        # The actual realized result remains in `results`.

    # --------------------------------------------------------------
    # Basic validation.
    # --------------------------------------------------------------

    if results.empty:
        fail(
            "Backtest returned an empty result."
        )

    if results.isna().any().any():
        fail(
            "Backtest contains NaN values."
        )

    # --------------------------------------------------------------
    # Report.
    # --------------------------------------------------------------

    print()
    print_report(
        results=results,
        engine=engine,
        observations=observations,
    )

    # --------------------------------------------------------------
    # Final result.
    # --------------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "STEP 9 — WALK-FORWARD BACKTEST COMPLETED"
    )
    print("=" * 80)


# ======================================================================
# EXECUTION
# ======================================================================


if __name__ == "__main__":
    main()