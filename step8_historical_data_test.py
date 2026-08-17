# ======================================================================
# STEP 8 — HISTORICAL DATA + PRODUCTION DECISION INTEGRATION
# ======================================================================

"""
Step 8 validates the production portfolio engine against real
historical market and macroeconomic data.

Pipeline
--------
1. Download historical prices from Yahoo Finance.
2. Calculate historical returns.
3. Download macroeconomic data from FRED.
4. Align macro data to the market calendar.
5. Construct a historical macro-regime series.
6. Build current macro state.
7. Generate expected returns from historical prices.
8. Send returns, regimes and expected returns into the
   PortfolioDecisionEngine.
9. Validate the complete production decision.
"""

# ======================================================================
# SECTION 1 — IMPORTS
# ======================================================================

from __future__ import annotations

import os
import sys

from productioncomposition import (
    ProductionComposition,
)

import numpy as np
import pandas as pd

from fredapi import Fred

from core_constants import (
    settings,
)

from macroregime import (
    MacroRegimeModel,
    Regime,
)

from marketdataloader import (
    MarketDataLoader,
)

from expectedreturnforecaster import (
    ExpectedReturnForecaster,
)

# ======================================================================
# SECTION 2 — CONFIGURATION
# ======================================================================

TICKERS = [
    "SPY",
    "EFA",
    "EEM",
]

HISTORY_PERIOD = "15y"

MIN_OBSERVATIONS = 252

REGIME_LOOKBACK = 252


# ======================================================================
# SECTION 3 — OUTPUT HELPERS
# ======================================================================

def banner(title: str) -> None:

    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def fail(message: str) -> None:

    print()
    print("=" * 80)
    print("STEP 8 FAILED")
    print("=" * 80)
    print()
    print(message)
    print()

    raise AssertionError(message)


# ======================================================================
# SECTION 4 — LOAD MARKET DATA
# ======================================================================

def load_market_data() -> tuple[pd.DataFrame, pd.DataFrame]:

    banner("1. LOADING HISTORICAL MARKET DATA")

    loader = MarketDataLoader(
        assets=TICKERS,
        period=HISTORY_PERIOD,
    )

    prices = loader.load_prices()

    if prices is None or prices.empty:

        fail(
            "Yahoo Finance returned no price data."
        )

    prices = prices.copy()

    prices = prices[
        TICKERS
    ]

    prices = prices.dropna(
        how="all"
    )

    prices = prices.dropna(
        how="any"
    )

    if len(prices) < MIN_OBSERVATIONS:

        fail(
            "Insufficient historical price data: "
            f"required at least {MIN_OBSERVATIONS}, "
            f"received {len(prices)}."
        )

    returns = (
        prices
        .pct_change()
        .dropna()
    )

    if returns.empty:

        fail(
            "Historical return series is empty."
        )

    print()
    print("PRICE HISTORY:")
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
    print("RETURN HISTORY:")
    print(
        f"Observations: {len(returns)}"
    )
    print(
        f"Shape: {returns.shape}"
    )

    return prices, returns


# ======================================================================
# SECTION 5 — LOAD FRED DATA
# ======================================================================

def load_fred_data(
    price_index,
):
    """
    Load and align historical FRED macroeconomic data
    to the market trading calendar.

    Important frequency handling:

        UNRATE   -> monthly
        CPIAUCSL -> monthly
        DGS10    -> daily
        DGS2     -> daily

    Inflation is calculated on the original monthly CPI
    series BEFORE any daily-calendar alignment.

    The resulting macroeconomic observations are then
    forward-filled onto the market trading calendar.

    This preserves the latest information available at each
    market date and avoids look-ahead bias.
    """

    print()
    print("=" * 80)
    print("LOADING FRED MACROECONOMIC DATA")
    print("=" * 80)

    # ============================================================
    # 1. VALIDATE FRED CONFIGURATION
    # ============================================================

    if settings.fred_api_key is None:
        fail(
            "FRED API key is not configured.\n\n"
            "Add this to your .env file:\n\n"
            "FRED_API_KEY=YOUR_FRED_API_KEY"
        )

    if not settings.fred_api_key.strip():
        fail(
            "FRED API key is empty.\n\n"
            "Add a valid FRED API key to .env."
        )

    # ============================================================
    # 2. VALIDATE MARKET INDEX
    # ============================================================

    if price_index is None:
        fail(
            "Price index cannot be None."
        )

    market_index = pd.DatetimeIndex(
        pd.to_datetime(
            price_index
        )
    )

    if market_index.empty:
        fail(
            "Price index contains no observations."
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

    print()
    print("MARKET CALENDAR:")
    print(
        f"Observations: {len(market_index)}"
    )
    print(
        f"Start: {market_index[0]}"
    )
    print(
        f"End: {market_index[-1]}"
    )

    # ============================================================
    # 3. FRED CLIENT
    # ============================================================

    fred = Fred(
        api_key=settings.fred_api_key
    )

    # ============================================================
    # 4. SERIES DEFINITIONS
    # ============================================================

    series_map = {
        "unemployment": "UNRATE",
        "cpi": "CPIAUCSL",
        "dgs10": "DGS10",
        "dgs2": "DGS2",
    }

    raw = {}

    # ============================================================
    # 5. DOWNLOAD EACH SERIES
    # ============================================================

    for name, series_id in series_map.items():

        print()
        print(
            f"Downloading FRED series: "
            f"{series_id}"
        )

        try:

            series = fred.get_series(
                series_id,
                observation_start=(
                    market_index[0]
                ),
                observation_end=(
                    market_index[-1]
                ),
            )

        except Exception as exc:

            fail(
                f"Unable to download FRED series "
                f"{series_id}: {exc}"
            )

        if series is None:

            fail(
                f"FRED returned no data for "
                f"{series_id}."
            )

        series = pd.Series(
            series
        )

        # --------------------------------------------------------
        # NORMALIZE INDEX
        # --------------------------------------------------------

        series.index = pd.to_datetime(
            series.index
        )

        if series.index.tz is not None:

            series.index = (
                series.index
                .tz_localize(None)
            )

        # --------------------------------------------------------
        # NUMERIC CLEANING
        # --------------------------------------------------------

        series = pd.to_numeric(
            series,
            errors="coerce",
        )

        series = series.dropna()

        series = (
            series
            .sort_index()
        )

        series = series[
            ~series.index.duplicated(
                keep="last"
            )
        ]

        if series.empty:

            fail(
                f"FRED series {series_id} "
                f"contains no usable observations."
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

    # ============================================================
    # 6. CALCULATE MACRO VARIABLES
    #
    # CRITICAL:
    #
    # Calculate inflation BEFORE combining the monthly
    # CPI series with the daily Treasury series.
    # ============================================================

    unemployment = (
        raw["unemployment"]
        .copy()
    )

    cpi = (
        raw["cpi"]
        .copy()
    )

    dgs10 = (
        raw["dgs10"]
        .copy()
    )

    dgs2 = (
        raw["dgs2"]
        .copy()
    )

    # ------------------------------------------------------------
    # INFLATION
    #
    # CPI is monthly.
    #
    # 12 observations = 12 months.
    # ------------------------------------------------------------

    inflation = (
        cpi
        .pct_change(
            periods=12
        )
        * 100.0
    )

    inflation = (
        inflation
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .dropna()
    )

    # ------------------------------------------------------------
    # YIELD SPREAD
    #
    # 10-year Treasury minus 2-year Treasury.
    #
    # Align the two daily Treasury series before
    # calculating the spread.
    # ------------------------------------------------------------

    treasury = pd.concat(
        {
            "dgs10": dgs10,
            "dgs2": dgs2,
        },
        axis=1,
        join="outer",
    )

    treasury = (
        treasury
        .sort_index()
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

    # ============================================================
    # 7. BUILD MACRO DATAFRAME
    #
    # At this stage:
    #
    # unemployment -> monthly
    # inflation    -> monthly
    # yield spread -> daily
    #
    # They are intentionally NOT forced onto the same
    # calendar yet.
    # ============================================================

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

    print()
    print("=" * 80)
    print("MACRO VARIABLES BEFORE MARKET ALIGNMENT")
    print("=" * 80)

    print()
    print(
        f"Observations: {len(macro)}"
    )

    print(
        "Missing observations:"
    )

    print(
        macro[
            [
                "unemployment",
                "inflation",
                "yield_spread",
            ]
        ]
        .isna()
        .sum()
        .to_dict()
    )

    # ============================================================
    # 8. ALIGN TO MARKET TRADING CALENDAR
    #
    # This is where monthly macro variables are carried
    # forward onto trading days.
    #
    # Example:
    #
    # UNRATE:
    #
    # 2026-07-01 = 4.1
    #
    # becomes:
    #
    # 2026-07-01 -> 4.1
    # 2026-07-02 -> 4.1
    # 2026-07-03 -> 4.1
    # ...
    #
    # until the next unemployment observation.
    #
    # This is the correct information set.
    # ============================================================

    macro = (
        macro
        .reindex(
            market_index
        )
        .ffill()
    )

    # ============================================================
    # 9. DROP ONLY LEADING MISSING VALUES
    #
    # These can occur because:
    #
    # - inflation requires 12 months of CPI history
    # - some Treasury observations may begin later
    #
    # We do NOT use an exact-date intersection.
    # ============================================================

    macro = macro.dropna(
        subset=[
            "unemployment",
            "yield_spread",
            "inflation",
        ]
    )

    # ============================================================
    # 10. FINAL VALIDATION
    # ============================================================

    if macro.empty:

        fail(
            "No usable aligned macroeconomic "
            "observations were produced."
        )

    required_columns = [
        "unemployment",
        "yield_spread",
        "inflation",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in macro.columns
    ]

    if missing_columns:

        fail(
            "Aligned macroeconomic data is "
            f"missing columns: {missing_columns}"
        )

    if macro[
        required_columns
    ].isna().any().any():

        fail(
            "Aligned macroeconomic data still "
            "contains missing observations."
        )

    values = macro[
        required_columns
    ].to_numpy(
        dtype=float
    )

    if not np.isfinite(
        values
    ).all():

        fail(
            "Aligned macroeconomic data contains "
            "non-finite values."
        )

    # ============================================================
    # 11. FINAL REPORT
    # ============================================================

    print()
    print("=" * 80)
    print("ALIGNED MACROECONOMIC DATA")
    print("=" * 80)

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
    print("Missing values:")

    print(
        macro[
            required_columns
        ]
        .isna()
        .sum()
        .to_dict()
    )

    print()
    print("Latest macro observations:")

    print(
        macro.tail()
    )

    return macro


# ======================================================================
# SECTION 6 — BUILD HISTORICAL REGIMES
# ======================================================================

def build_regime_history(
    macro_df: pd.DataFrame,
) -> pd.Series:

    banner("3. BUILDING HISTORICAL REGIME HISTORY")

    model = MacroRegimeModel()

    regime_values = []

    for _, row in macro_df.iterrows():

        result = model.classify(
            float(
                row["unemployment"]
            ),
            float(
                row["yield_spread"]
            ),
            float(
                row["inflation"]
            ),
        )

        if isinstance(
            result,
            Regime,
        ):

            regime_value = result.value

        else:

            regime_value = str(
                result
            )

        regime_values.append(
            regime_value
        )

    regimes = pd.Series(
        regime_values,
        index=macro_df.index,
        name="regime",
    )

    regimes = regimes.dropna()

    if regimes.empty:

        fail(
            "Historical regime series is empty."
        )

    print()
    print("REGIME HISTORY:")
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
    print("REGIME COUNTS:")

    print(
        regimes.value_counts()
    )

    return regimes


# ======================================================================
# SECTION 7 — BUILD CURRENT MACRO STATE
# ======================================================================

def build_current_macro_data(
    macro_df: pd.DataFrame,
) -> dict:

    latest = (
        macro_df
        .iloc[-1]
    )

    macro_data = {

        "unemployment": float(
            latest[
                "unemployment"
            ]
        ),

        "yield_spread": float(
            latest[
                "yield_spread"
            ]
        ),

        "inflation": float(
            latest[
                "inflation"
            ]
        ),
    }

    print()
    print("CURRENT MACRO STATE:")

    print(
        macro_data
    )

    return macro_data


# ======================================================================
# SECTION 8 — BUILD EXPECTED RETURNS
# ======================================================================

def build_expected_returns(
    prices: pd.DataFrame,
) -> dict[str, float]:

    banner("4. BUILDING EXPECTED RETURNS")

    forecaster = (
        ExpectedReturnForecaster()
    )

    forecast = (
        forecaster.forecast(
            prices
        )
    )

    if forecast is None:

        fail(
            "Expected-return forecaster "
            "returned None."
        )

    if isinstance(
        forecast,
        pd.Series,
    ):

        expected_returns = {
            ticker: float(
                forecast[ticker]
            )
            for ticker in TICKERS
        }

    elif isinstance(
        forecast,
        dict,
    ):

        expected_returns = {
            ticker: float(
                forecast[ticker]
            )
            for ticker in TICKERS
        }

    else:

        fail(
            "Expected-return forecaster returned "
            f"unsupported type: "
            f"{type(forecast).__name__}"
        )

    print()
    print(
        "EXPECTED RETURNS:"
    )

    print(
        expected_returns
    )

    return expected_returns


# ======================================================================
# SECTION 9 — BUILD PORTFOLIO
# ======================================================================

def build_portfolio() -> dict:

    weights = {
        ticker: 1.0 / len(TICKERS)
        for ticker in TICKERS
    }

    portfolio = {
        "weights": weights
    }

    print()
    print("PORTFOLIO:")
    print(
        portfolio
    )

    return portfolio


# ======================================================================
# SECTION 10 — RUN PRODUCTION DECISION
# ======================================================================

def run_production_decision(
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    macro_df: pd.DataFrame,
    regimes: pd.Series,
    macro_data: dict,
    expected_returns: dict,
    portfolio: dict,
):

    banner(
        "5. END-TO-END PRODUCTION PORTFOLIO DECISION"
    )

    composition = (
    ProductionComposition()
    )

    engine = (
    composition.build_engine()
    )

    print()
    print("ENGINE:")
    print(
        engine
    )

    print()
    print("INPUT HISTORY VALIDATION:")

    print(
        f"Prices: {prices.shape}"
    )

    print(
        f"Returns: {returns.shape}"
    )

    print(
        f"Macro: {macro_df.shape}"
    )

    print(
        f"Regimes: {len(regimes)}"
    )

    # --------------------------------------------------------------
    # ALIGN EVERYTHING TO THE SAME HISTORICAL WINDOW
    # --------------------------------------------------------------

    common_index = (
        prices.index
        .intersection(
            returns.index
        )
        .intersection(
            macro_df.index
        )
        .intersection(
            regimes.index
        )
    )

    if len(common_index) < MIN_OBSERVATIONS:

        fail(
            "Insufficient aligned historical "
            "observations after joining market, "
            "macro and regime data: "
            f"{len(common_index)}."
        )

    prices = prices.loc[
        common_index
    ]

    returns = returns.loc[
        common_index
    ]

    macro_df = macro_df.loc[
        common_index
    ]

    regimes = regimes.loc[
        common_index
    ]

    # --------------------------------------------------------------
    # SAFETY CHECKS
    # --------------------------------------------------------------

    assert len(prices) == len(returns)

    assert len(prices) == len(macro_df)

    assert len(prices) == len(regimes)

    assert list(
        prices.columns
    ) == TICKERS

    assert list(
        returns.columns
    ) == TICKERS

    assert regimes.index.equals(
        returns.index
    )

    assert macro_df.index.equals(
        returns.index
    )

    print(
        "Aligned observations:",
        len(returns),
    )

    print(
        "Aligned tickers:",
        list(returns.columns),
    )

    # --------------------------------------------------------------
    # RUN ENGINE
    #
    # IMPORTANT:
    # `returns` is passed for covariance/risk estimation.
    #
    # `expected_returns` is supplied explicitly because the
    # ExpectedReturnForecaster operates on PRICE history.
    # --------------------------------------------------------------

    print()
    print(
        "RUNNING PRODUCTION DECISION..."
    )

    decision = engine.decide(

        portfolio=portfolio,

        returns=returns,

        macro_data=macro_data,

        expected_returns=expected_returns,

        regimes=regimes,

        scenarios=None,
    )

    # ==================================================================
    # RESULT
    # ==================================================================

    print()
    print("STATUS:")
    print(
        decision.status
    )

    print()
    print("APPROVED:")
    print(
        decision.approved
    )

    print()
    print("REGIME:")
    print(
        decision.regime
    )

    print()
    print("TICKERS:")
    print(
        decision.tickers
    )

    print()
    print("WEIGHTS:")
    print(
        decision.weights
    )

    print()
    print("EXPECTED RETURNS:")
    print(
        decision.expected_returns
    )

    print()
    print("PORTFOLIO RETURN:")
    print(
        decision.portfolio_return
    )

    print()
    print("PORTFOLIO VOLATILITY:")
    print(
        decision.portfolio_volatility
    )

    print()
    print("PORTFOLIO VARIANCE:")
    print(
        decision.portfolio_variance
    )

    print()
    print("GROSS EXPOSURE:")
    print(
        decision.gross_exposure
    )

    print()
    print("NET EXPOSURE:")
    print(
        decision.net_exposure
    )

    print()
    print("NUMBER OF POSITIONS:")
    print(
        decision.number_of_positions
    )

    print()
    print("RISK CONTRIBUTIONS:")
    print(
        decision.risk_contributions
    )

    print()
    print("RISK CONTRIBUTION %:")
    print(
        decision.risk_contribution_pct
    )

    print()
    print("WARNINGS:")
    print(
        decision.warnings
    )

    print()
    print("ERRORS:")
    print(
        decision.errors
    )

    print()
    print("DIAGNOSTICS:")
    print(
        decision.diagnostics
    )

    # ==================================================================
    # VALIDATION
    # ==================================================================

    assert decision.status != "FAILED", (
        "Production decision failed: "
        f"{decision.errors}"
    )

    assert decision.approved is True, (
        "Production decision was not approved: "
        f"{decision.errors}"
    )

    assert decision.regime is not None

    assert len(
        decision.tickers
    ) == len(TICKERS)

    assert len(
        decision.weights
    ) == len(TICKERS)

    assert len(
        decision.expected_returns
    ) == len(TICKERS)

    assert (
        decision.portfolio_variance
        >= 0.0
    )

    assert (
        decision.portfolio_volatility
        >= 0.0
    )

    assert abs(
        sum(
            decision.weights.values()
        )
        - 1.0
    ) < 1e-8

    assert (
        decision.gross_exposure
        >= 0.0
    )

    assert (
        decision.number_of_positions
        == len(TICKERS)
    )

    health = (
        engine.health_check()
    )

    print()
    print("ENGINE HEALTH:")
    print(
        health
    )

    assert health["healthy"] is True

    print()
    print("=" * 80)
    print(
        "STEP 8 PASSED — HISTORICAL DATA "
        "PRODUCTION INTEGRATION SUCCESSFUL"
    )
    print("=" * 80)

    return decision


# ======================================================================
# SECTION 11 — MAIN
# ======================================================================

def main() -> None:

    banner(
        "STEP 8 — HISTORICAL DATA PRODUCTION TEST"
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

    # --------------------------------------------------------------
    # MARKET
    # --------------------------------------------------------------

    prices, returns = (
        load_market_data()
    )

    # --------------------------------------------------------------
    # FRED
    # --------------------------------------------------------------

    macro_df = (
        load_fred_data(
            prices.index
        )
    )

    # --------------------------------------------------------------
    # REGIMES
    # --------------------------------------------------------------

    regimes = (
        build_regime_history(
            macro_df
        )
    )

    # --------------------------------------------------------------
    # CURRENT MACRO STATE
    # --------------------------------------------------------------

    macro_data = (
        build_current_macro_data(
            macro_df
        )
    )

    # --------------------------------------------------------------
    # EXPECTED RETURNS
    # --------------------------------------------------------------

    expected_returns = (
        build_expected_returns(
            prices
        )
    )

    # --------------------------------------------------------------
    # PORTFOLIO
    # --------------------------------------------------------------

    portfolio = (
        build_portfolio()
    )

    # --------------------------------------------------------------
    # PRODUCTION DECISION
    # --------------------------------------------------------------

    run_production_decision(

        prices=prices,

        returns=returns,

        macro_df=macro_df,

        regimes=regimes,

        macro_data=macro_data,

        expected_returns=expected_returns,

        portfolio=portfolio,
    )


# ======================================================================
# EXECUTION
# ======================================================================

if __name__ == "__main__":

    main()