# ======================================================================
# STEP 8 — REGISTRY-QUALIFIED HISTORICAL DATA + PRODUCTION DECISION INTEGRATION
# ======================================================================

"""
Step 8 validates the production portfolio engine against real
historical market and macroeconomic data using the complete
registry-qualified production universe.

Pipeline
--------
1. Download historical prices from Yahoo Finance.
2. Validate the complete registry-qualified price matrix.
3. Calculate historical returns.
4. Download macroeconomic data from FRED.
5. Calculate inflation from monthly CPI data.
6. Calculate the 10Y-2Y Treasury yield spread.
7. Align macroeconomic data to the market trading calendar.
8. Construct a historical macro-regime series.
9. Build the current macro state.
10. Generate expected returns from historical prices.
11. Build the registry-qualified production portfolio.
12. Send the aligned production inputs into PortfolioDecisionEngine.
13. Validate the complete production decision.
14. Validate production engine health.
15. Run a deterministic second decision check.
"""

# ======================================================================
# SECTION 1 — IMPORTS
# ======================================================================

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from fredapi import Fred

from core_constants import settings
from expectedreturnforecaster import ExpectedReturnForecaster
from macroregime import MacroRegimeModel, Regime
from marketdataloader import MarketDataLoader
from productioncomposition import ProductionComposition


# ======================================================================
# SECTION 2 — PRODUCTION CONFIGURATION
# ======================================================================

TICKERS = list(__import__("assetuniverse").PRODUCTION_ASSETS)

HISTORY_PERIOD = "15y"

MIN_OBSERVATIONS = 252

EXPECTED_ASSET_COUNT = len(__import__("assetuniverse").PRODUCTION_ASSETS)

REGIME_LOOKBACK = 252

NUMERIC_TOLERANCE = 1e-8


# ======================================================================
# SECTION 3 — OUTPUT HELPERS
# ======================================================================

def banner(title: str) -> None:
    """Print a standard Step 8 section banner."""

    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def fail(message: str) -> None:
    """Fail the Step 8 integration test with a clear message."""

    print()
    print("=" * 80)
    print("STEP 8 FAILED")
    print("=" * 80)
    print()
    print(message)
    print()

    raise AssertionError(message)


# ======================================================================
# SECTION 4 — VALIDATE PRODUCTION UNIVERSE
# ======================================================================

def validate_production_universe() -> None:
    """Validate the configured registry-qualified production universe."""

    if len(TICKERS) != EXPECTED_ASSET_COUNT:
        fail(
            "Production asset universe contains "
            f"{len(TICKERS)} assets; expected "
            f"{EXPECTED_ASSET_COUNT}."
        )

    if len(set(TICKERS)) != len(TICKERS):
        fail(
            "Production asset universe contains duplicate tickers."
        )

    if not all(
        isinstance(ticker, str) and ticker.strip()
        for ticker in TICKERS
    ):
        fail(
            "Production asset universe contains invalid ticker values."
        )

    print()
    print("PRODUCTION ASSET UNIVERSE:")
    print(TICKERS)
    print(
        f"Asset count: {len(TICKERS)}"
    )


# ======================================================================
# SECTION 5 — NORMALIZE DATETIME INDEX
# ======================================================================

def normalize_datetime_index(
    index: pd.Index,
) -> pd.DatetimeIndex:
    """Normalize a pandas index to a unique sorted naive DatetimeIndex."""

    normalized = pd.DatetimeIndex(
        pd.to_datetime(index)
    )

    if normalized.tz is not None:
        normalized = normalized.tz_localize(None)

    normalized = (
        normalized
        .sort_values()
        .drop_duplicates()
    )

    return normalized


# ======================================================================
# SECTION 6 — LOAD HISTORICAL MARKET DATA
# ======================================================================

def load_market_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load historical prices and calculate historical returns.

    Prices are kept intact for the expected-return forecasting layer.

    Returns are calculated from the validated price matrix and therefore
    contain one fewer observation than prices under normal conditions.
    """

    banner("1. LOADING HISTORICAL MARKET DATA")

    validate_production_universe()

    loader = MarketDataLoader(
        assets=TICKERS,
        period=HISTORY_PERIOD,
    )

    prices = loader.load_prices(
        validate=False
    )

    if prices is None or prices.empty:
        fail(
            "Yahoo Finance returned no historical price data."
        )

    prices = prices.copy()

    # --------------------------------------------------------------
    # NORMALIZE INDEX
    # --------------------------------------------------------------

    prices.index = normalize_datetime_index(
        prices.index
    )

    # --------------------------------------------------------------
    # VERIFY REQUIRED COLUMNS
    # --------------------------------------------------------------

    missing_tickers = [
        ticker
        for ticker in TICKERS
        if ticker not in prices.columns
    ]

    if missing_tickers:
        fail(
            "Historical market data is missing required "
            f"production assets: {missing_tickers}"
        )

    # --------------------------------------------------------------
    # SELECT EXACT PRODUCTION ORDER
    # --------------------------------------------------------------

    prices = prices.loc[
        :,
        TICKERS,
    ].copy()

    # --------------------------------------------------------------
    # REMOVE ONLY ROWS WHERE ALL ASSETS ARE MISSING
    # --------------------------------------------------------------

    prices = prices.dropna(
        how="all"
    )

    if prices.empty:
        fail(
            "Historical price matrix became empty after "
            "removing completely missing observations."
        )

    # --------------------------------------------------------------
    # RAW SOURCE QUALITY REPORT
    # --------------------------------------------------------------

    print()
    print("RAW HISTORICAL DATA QUALITY:")
    print(
        f"Observations: {len(prices)}"
    )

    missing_by_ticker = (
        prices
        .isna()
        .sum()
    )

    print(
        "Missing observations by ticker:"
    )
    print(
        missing_by_ticker
    )

    # --------------------------------------------------------------
    # COMPLETE-CASE MARKET MATRIX
    #
    # We do not fabricate missing prices.
    #
    # A row containing a missing value for any required production
    # asset is removed before returns are calculated.
    # --------------------------------------------------------------

    prices = prices.dropna(
        how="any"
    )

    if prices.empty:
        fail(
            "Complete-case historical price matrix is empty."
        )

    if len(prices) < MIN_OBSERVATIONS:
        fail(
            "Insufficient historical price data after "
            "complete-case alignment: "
            f"required at least {MIN_OBSERVATIONS}, "
            f"received {len(prices)}."
        )

    # --------------------------------------------------------------
    # NUMERIC VALIDATION
    # --------------------------------------------------------------

    prices = prices.apply(
        pd.to_numeric,
        errors="coerce",
    )

    if prices.isna().any().any():
        fail(
            "Historical prices contain non-numeric or missing "
            "observations after numeric conversion."
        )

    if not np.isfinite(
        prices.to_numpy(dtype=float)
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
    # PRICE MONOTONICITY
    # --------------------------------------------------------------

    if not prices.index.is_monotonic_increasing:
        fail(
            "Historical price index is not monotonically increasing."
        )

    if prices.index.has_duplicates:
        fail(
            "Historical price index contains duplicate dates."
        )

    # --------------------------------------------------------------
    # CALCULATE RETURNS
    # --------------------------------------------------------------

    returns = (
        prices
        .pct_change()
        .dropna(
            how="any"
        )
    )

    if returns.empty:
        fail(
            "Historical return series is empty."
        )

    if list(returns.columns) != TICKERS:
        fail(
            "Historical return columns do not match the "
            "production asset universe."
        )

    if not np.isfinite(
        returns.to_numpy(dtype=float)
    ).all():
        fail(
            "Historical return matrix contains non-finite values."
        )

    if returns.index.has_duplicates:
        fail(
            "Historical return index contains duplicate dates."
        )

    if not returns.index.is_monotonic_increasing:
        fail(
            "Historical return index is not monotonically increasing."
        )

    # --------------------------------------------------------------
    # REPORT
    # --------------------------------------------------------------

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
    print(
        f"Start: {returns.index[0]}"
    )
    print(
        f"End: {returns.index[-1]}"
    )

    print()
    print("RETURN DATA QUALITY:")
    print(
        "Missing observations by ticker:"
    )
    print(
        returns.isna().sum()
    )

    return prices, returns


# ======================================================================
# SECTION 7 — LOAD FRED DATA
# ======================================================================

def load_fred_data(
    price_index: pd.Index,
) -> pd.DataFrame:
    """
    Load and align historical FRED macroeconomic data.

    Series
    ------
    UNRATE
        Monthly unemployment rate.

    CPIAUCSL
        Monthly CPI index used to calculate year-over-year inflation.

    DGS10
        Daily 10-year Treasury yield.

    DGS2
        Daily 2-year Treasury yield.

    Inflation is calculated from the original monthly CPI series
    before market-calendar alignment.

    Monthly macroeconomic observations are then forward-filled onto
    the market trading calendar. This uses the latest information
    available as of each market date.
    """

    banner("2. LOADING FRED MACROECONOMIC DATA")

    # ==============================================================
    # 1. FRED API VALIDATION
    # ==============================================================

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

    # ==============================================================
    # 2. MARKET CALENDAR
    # ==============================================================

    market_index = normalize_datetime_index(
        price_index
    )

    if market_index.empty:
        fail(
            "Market price index contains no observations."
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

    # ==============================================================
    # 3. FRED CLIENT
    # ==============================================================

    fred = Fred(
        api_key=settings.fred_api_key
    )

    series_map = {
        "unemployment": "UNRATE",
        "cpi": "CPIAUCSL",
        "dgs10": "DGS10",
        "dgs2": "DGS2",
    }

    raw: dict[str, pd.Series] = {}

    # ==============================================================
    # 4. DOWNLOAD FRED SERIES
    # ==============================================================

    for name, series_id in series_map.items():

        print()
        print(
            f"Downloading FRED series: {series_id}"
        )

        try:
            series = fred.get_series(
                series_id,
                observation_start=market_index[0],
                observation_end=market_index[-1],
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

        series = pd.Series(
            series
        )

        series.index = normalize_datetime_index(
            series.index
        )

        series = pd.to_numeric(
            series,
            errors="coerce",
        )

        series = (
            series
            .replace(
                [np.inf, -np.inf],
                np.nan,
            )
            .dropna()
            .sort_index()
        )

        if series.empty:
            fail(
                f"FRED series {series_id} contains "
                "no usable observations."
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

    # ==============================================================
    # 5. EXTRACT SERIES
    # ==============================================================

    unemployment = raw["unemployment"].copy()
    cpi = raw["cpi"].copy()
    dgs10 = raw["dgs10"].copy()
    dgs2 = raw["dgs2"].copy()

    # ==============================================================
    # 6. CALCULATE YEAR-OVER-YEAR INFLATION
    #
    # CPI is monthly.
    #
    # Inflation is calculated BEFORE daily market-calendar alignment.
    # ==============================================================

    inflation = (
        cpi
        .pct_change(periods=12)
        * 100.0
    )

    inflation = (
        inflation
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .dropna()
        .sort_index()
    )

    if inflation.empty:
        fail(
            "Unable to construct a usable CPI-based "
            "inflation series."
        )

    # ==============================================================
    # 7. CALCULATE 10Y-2Y YIELD SPREAD
    # ==============================================================

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
        .sort_index()
    )

    if yield_spread.empty:
        fail(
            "Unable to construct a usable Treasury "
            "yield-spread series."
        )

    # ==============================================================
    # 8. BUILD MACRO DATAFRAME BEFORE MARKET ALIGNMENT
    # ==============================================================

    macro = pd.concat(
        {
            "unemployment": unemployment,
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

    # ==============================================================
    # 9. ALIGN TO MARKET TRADING CALENDAR
    # ==============================================================

    macro = (
        macro
        .reindex(market_index)
        .ffill()
    )

    # ==============================================================
    # 10. REMOVE LEADING OBSERVATIONS WITHOUT A COMPLETE
    #     INFORMATION SET
    # ==============================================================

    required_columns = [
        "unemployment",
        "inflation",
        "yield_spread",
    ]

    macro = macro.dropna(
        subset=required_columns
    )

    if macro.empty:
        fail(
            "No usable aligned macroeconomic observations "
            "were produced."
        )

    # ==============================================================
    # 11. FINAL MACRO VALIDATION
    # ==============================================================

    if list(macro.columns) != required_columns:
        fail(
            "Aligned macroeconomic columns are incorrect: "
            f"{list(macro.columns)}"
        )

    if macro.index.has_duplicates:
        fail(
            "Aligned macroeconomic data contains duplicate dates."
        )

    if not macro.index.is_monotonic_increasing:
        fail(
            "Aligned macroeconomic data is not chronologically ordered."
        )

    if macro[required_columns].isna().any().any():
        fail(
            "Aligned macroeconomic data still contains missing values."
        )

    macro_values = macro[
        required_columns
    ].to_numpy(
        dtype=float
    )

    if not np.isfinite(
        macro_values
    ).all():
        fail(
            "Aligned macroeconomic data contains non-finite values."
        )

    # ==============================================================
    # 12. REPORT
    # ==============================================================

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
# SECTION 8 — BUILD HISTORICAL REGIME HISTORY
# ======================================================================

def build_regime_history(
    macro_df: pd.DataFrame,
) -> pd.Series:
    """
    Classify every aligned historical macro observation.

    The resulting regime Series uses exactly the same index as the
    aligned macro dataframe.
    """

    banner("3. BUILDING HISTORICAL REGIME HISTORY")

    model = MacroRegimeModel()

    regime_values: list[str] = []

    for timestamp, row in macro_df.iterrows():

        try:
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
        except Exception as exc:
            fail(
                "Macro regime classification failed at "
                f"{timestamp}: {exc}"
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

        regime_value = regime_value.strip()

        if not regime_value:
            fail(
                "Macro regime classifier returned an empty "
                f"regime at {timestamp}."
            )

        regime_values.append(
            regime_value
        )

    regimes = pd.Series(
        regime_values,
        index=macro_df.index,
        name="regime",
    )

    if regimes.empty:
        fail(
            "Historical regime series is empty."
        )

    if not regimes.index.equals(
        macro_df.index
    ):
        fail(
            "Historical regime index does not match "
            "aligned macro data."
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
# SECTION 9 — BUILD CURRENT MACRO STATE
# ======================================================================

def build_current_macro_data(
    macro_df: pd.DataFrame,
) -> dict[str, float]:
    """Build the latest scalar macro state used by the engine."""

    latest = macro_df.iloc[-1]

    macro_data = {
        "unemployment": float(
            latest["unemployment"]
        ),
        "yield_spread": float(
            latest["yield_spread"]
        ),
        "inflation": float(
            latest["inflation"]
        ),
    }

    if not all(
        np.isfinite(value)
        for value in macro_data.values()
    ):
        fail(
            "Current macro state contains non-finite values."
        )

    print()
    print("CURRENT MACRO STATE:")
    print(
        macro_data
    )

    return macro_data


# ======================================================================
# SECTION 10 — BUILD EXPECTED RETURNS
# ======================================================================

def build_expected_returns(
    prices: pd.DataFrame,
) -> dict[str, float]:
    """
    Generate expected returns from the complete historical price matrix.

    Every production asset must receive a finite forecast.
    """

    banner("4. BUILDING EXPECTED RETURNS")

    forecaster = ExpectedReturnForecaster()

    try:
        forecast = forecaster.forecast(
            prices
        )
    except Exception as exc:
        fail(
            "ExpectedReturnForecaster failed: "
            f"{exc}"
        )

    if forecast is None:
        fail(
            "ExpectedReturnForecaster returned None."
        )

    if isinstance(
        forecast,
        pd.Series,
    ):
        forecast_map = forecast.to_dict()

    elif isinstance(
        forecast,
        dict,
    ):
        forecast_map = dict(
            forecast
        )

    else:
        fail(
            "ExpectedReturnForecaster returned unsupported "
            f"type: {type(forecast).__name__}"
        )

    missing_forecasts = [
        ticker
        for ticker in TICKERS
        if ticker not in forecast_map
    ]

    if missing_forecasts:
        fail(
            "Expected-return forecast is missing production "
            f"assets: {missing_forecasts}"
        )

    expected_returns: dict[str, float] = {}

    for ticker in TICKERS:

        try:
            value = float(
                forecast_map[ticker]
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            fail(
                f"Expected return for {ticker} cannot be "
                f"converted to float: {exc}"
            )

        if not np.isfinite(value):
            fail(
                f"Expected return for {ticker} is non-finite: "
                f"{value}"
            )

        expected_returns[ticker] = value

    if len(
        expected_returns
    ) != EXPECTED_ASSET_COUNT:
        fail(
            "Expected-return forecast does not contain exactly "
            f"{EXPECTED_ASSET_COUNT} assets."
        )

    print()
    print("EXPECTED RETURNS:")

    print(
        expected_returns
    )

    return expected_returns


# ======================================================================
# SECTION 11 — BUILD REGISTRY-QUALIFIED INPUT PORTFOLIO
# ======================================================================

def build_portfolio() -> dict[str, dict[str, float]]:
    """Build the equal-weight registry-qualified production input portfolio."""

    weight = 1.0 / len(TICKERS)

    weights = {
        ticker: weight
        for ticker in TICKERS
    }

    portfolio = {
        "weights": weights
    }

    print()
    print("INPUT PORTFOLIO:")
    print(
        portfolio
    )

    weight_sum = sum(
        weights.values()
    )

    if not np.isclose(
        weight_sum,
        1.0,
        atol=NUMERIC_TOLERANCE,
    ):
        fail(
            "Input portfolio weights do not sum to one: "
            f"{weight_sum}"
        )

    if set(weights) != set(TICKERS):
        fail(
            "Input portfolio ticker set does not match "
            "the production universe."
        )

    return portfolio


# ======================================================================
# SECTION 12 — ALIGN PRODUCTION INPUT HISTORY
# ======================================================================

def align_production_history(
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    macro_df: pd.DataFrame,
    regimes: pd.Series,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.Series,
]:
    """
    Align returns, macro observations and regimes to the same
    historical decision dates.

    Prices are deliberately retained separately because they are
    used by the expected-return forecasting layer.
    """

    banner("INPUT HISTORY VALIDATION")

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

    print(
        f"Assets: {len(TICKERS)}"
    )

    # --------------------------------------------------------------
    # RETURNS / MACRO / REGIME ARE THE DECISION HISTORY.
    #
    # Prices have one extra observation because pct_change()
    # removes the first return observation.
    # --------------------------------------------------------------

    common_index = (
        returns.index
        .intersection(
            macro_df.index
        )
        .intersection(
            regimes.index
        )
    )

    if len(common_index) < MIN_OBSERVATIONS:
        fail(
            "Insufficient aligned production observations after "
            "joining returns, macro data and regimes: "
            f"{len(common_index)}."
        )

    common_index = (
        pd.DatetimeIndex(common_index)
        .sort_values()
        .drop_duplicates()
    )

    aligned_returns = returns.loc[
        common_index
    ].copy()

    aligned_macro = macro_df.loc[
        common_index
    ].copy()

    aligned_regimes = regimes.loc[
        common_index
    ].copy()

    # --------------------------------------------------------------
    # VALIDATE ASSET ORDER
    # --------------------------------------------------------------

    if list(
        aligned_returns.columns
    ) != TICKERS:
        fail(
            "Aligned returns do not use the exact registry-qualified "
            "production ordering."
        )

    # --------------------------------------------------------------
    # VALIDATE INDEX ALIGNMENT
    # --------------------------------------------------------------

    if not aligned_returns.index.equals(
        aligned_macro.index
    ):
        fail(
            "Aligned returns and macro indices differ."
        )

    if not aligned_returns.index.equals(
        aligned_regimes.index
    ):
        fail(
            "Aligned returns and regime indices differ."
        )

    # --------------------------------------------------------------
    # VALIDATE NUMERICS
    # --------------------------------------------------------------

    if aligned_returns.isna().any().any():
        fail(
            "Aligned returns contain missing values."
        )

    if aligned_macro.isna().any().any():
        fail(
            "Aligned macro data contains missing values."
        )

    if aligned_regimes.isna().any():
        fail(
            "Aligned regime history contains missing values."
        )

    if not np.isfinite(
        aligned_returns.to_numpy(
            dtype=float
        )
    ).all():
        fail(
            "Aligned returns contain non-finite values."
        )

    # --------------------------------------------------------------
    # PRICE HISTORY MUST COVER THE DECISION HISTORY
    # --------------------------------------------------------------

    if not set(
        aligned_returns.index
    ).issubset(
        set(prices.index)
    ):
        fail(
            "Price history does not cover all aligned "
            "return observations."
        )

    print(
        "Aligned observations:",
        len(aligned_returns),
    )

    print(
        "Aligned tickers:",
        list(aligned_returns.columns),
    )

    print(
        "Aligned start:",
        aligned_returns.index[0],
    )

    print(
        "Aligned end:",
        aligned_returns.index[-1],
    )

    print(
        "PASSED"
    )

    return (
        prices,
        aligned_returns,
        aligned_macro,
        aligned_regimes,
    )


# ======================================================================
# SECTION 13 — RUN PRODUCTION DECISION
# ======================================================================

def run_production_decision(
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    macro_df: pd.DataFrame,
    regimes: pd.Series,
    macro_data: dict[str, float],
    expected_returns: dict[str, float],
    portfolio: dict[str, dict[str, float]],
):
    """Run and validate the complete registry-qualified production decision."""

    banner(
        "5. END-TO-END REGISTRY-QUALIFIED PRODUCTION PORTFOLIO DECISION"
    )

    composition = ProductionComposition()

    engine = composition.build_engine()

    if engine is None:
        fail(
            "ProductionComposition.build_engine() returned None."
        )

    print()
    print("ENGINE:")
    print(
        engine
    )

    print()
    print("OPTIMIZER:")
    print(
        engine.optimizer
    )

    print()
    print("RISK BUDGET ENGINE:")
    print(
        engine.optimizer.risk_budget_engine
    )

    print()
    print("BLACK-LITTERMAN:")
    print(
        engine.black_litterman
    )

    # --------------------------------------------------------------
    # DEPENDENCY VALIDATION
    # --------------------------------------------------------------

    if engine.optimizer is None:
        fail(
            "Production engine has no PortfolioOptimizer."
        )

    if engine.optimizer.risk_budget_engine is None:
        fail(
            "PortfolioOptimizer has no RiskBudgetEngine."
        )

    if engine.optimizer.constraints is None:
        fail(
            "PortfolioOptimizer has no PortfolioConstraints."
        )

    if engine.black_litterman is None:
        fail(
            "Production engine has no Black-Litterman component."
        )

    # --------------------------------------------------------------
    # FINAL INPUT VALIDATION
    # --------------------------------------------------------------

    if len(TICKERS) != EXPECTED_ASSET_COUNT:
        fail(
            "Step 8 is not operating on the complete registry-qualified "
            "production universe."
        )

    if list(
        returns.columns
    ) != TICKERS:
        fail(
            "Production return history does not match the "
            "registry-qualified universe."
        )

    if set(
        expected_returns
    ) != set(TICKERS):
        fail(
            "Expected-return assets do not match the "
            "registry-qualified universe."
        )

    if set(
        portfolio["weights"]
    ) != set(TICKERS):
        fail(
            "Portfolio assets do not match the "
            "registry-qualified universe."
        )

    # --------------------------------------------------------------
    # PRODUCTION DECISION
    # --------------------------------------------------------------

    print()
    print(
        "RUNNING REGISTRY-QUALIFIED PRODUCTION DECISION..."
    )

    try:
        decision = engine.decide(
            portfolio=portfolio,
            returns=returns,
            macro_data=macro_data,
            expected_returns=expected_returns,
            regimes=regimes,
            scenarios=None,
        )
    except Exception as exc:
        fail(
            "PortfolioDecisionEngine.decide() raised an "
            f"unexpected exception: {type(exc).__name__}: {exc}"
        )

    if decision is None:
        fail(
            "PortfolioDecisionEngine returned None."
        )

    # --------------------------------------------------------------
    # DISPLAY DECISION
    # --------------------------------------------------------------

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
    print("SCENARIO RESULTS:")
    print(
        decision.scenario_results
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

    # --------------------------------------------------------------
    # DECISION VALIDATION
    # --------------------------------------------------------------

    if decision.status == "FAILED":
        fail(
            "Production decision failed: "
            f"{decision.errors}"
        )

    if decision.approved is not True:
        fail(
            "Production decision was not approved: "
            f"{decision.errors}"
        )

    if decision.regime is None:
        fail(
            "Production decision did not return a regime."
        )

    decision_tickers = list(
        decision.tickers
    )

    if decision_tickers != TICKERS:
        fail(
            "Decision ticker ordering does not match the "
            "registry-qualified production universe.\n"
            f"Expected: {TICKERS}\n"
            f"Received: {decision_tickers}"
        )

    if len(
        decision.weights
    ) != EXPECTED_ASSET_COUNT:
        fail(
            "Production decision returned "
            f"{len(decision.weights)} weights; expected "
            f"{EXPECTED_ASSET_COUNT}."
        )

    if set(
        decision.weights
    ) != set(TICKERS):
        fail(
            "Production decision weight assets do not match "
            "the production universe."
        )

    if len(
        decision.expected_returns
    ) != EXPECTED_ASSET_COUNT:
        fail(
            "Production decision returned "
            f"{len(decision.expected_returns)} expected returns; "
            f"expected {EXPECTED_ASSET_COUNT}."
        )

    if set(
        decision.expected_returns
    ) != set(TICKERS):
        fail(
            "Production decision expected-return assets do not "
            "match the production universe."
        )

    # --------------------------------------------------------------
    # WEIGHT VALIDATION
    # --------------------------------------------------------------

    weight_values = np.asarray(
        list(
            decision.weights.values()
        ),
        dtype=float,
    )

    if not np.isfinite(
        weight_values
    ).all():
        fail(
            "Production decision contains non-finite weights."
        )

    weight_sum = float(
        weight_values.sum()
    )

    if not np.isclose(
        weight_sum,
        1.0,
        atol=NUMERIC_TOLERANCE,
    ):
        fail(
            "Production decision weights do not sum to one: "
            f"{weight_sum}"
        )

    if (
        weight_values < -NUMERIC_TOLERANCE
    ).any():
        fail(
            "Production decision contains negative weights."
        )

    # --------------------------------------------------------------
    # EXPECTED RETURN VALIDATION
    # --------------------------------------------------------------

    expected_return_values = np.asarray(
        list(
            decision.expected_returns.values()
        ),
        dtype=float,
    )

    if not np.isfinite(
        expected_return_values
    ).all():
        fail(
            "Production decision contains non-finite expected returns."
        )

    # --------------------------------------------------------------
    # PORTFOLIO METRIC VALIDATION
    # --------------------------------------------------------------

    portfolio_return = float(
        decision.portfolio_return
    )

    portfolio_variance = float(
        decision.portfolio_variance
    )

    portfolio_volatility = float(
        decision.portfolio_volatility
    )

    gross_exposure = float(
        decision.gross_exposure
    )

    net_exposure = float(
        decision.net_exposure
    )

    if not np.isfinite(
        portfolio_return
    ):
        fail(
            "Portfolio return is non-finite."
        )

    if not np.isfinite(
        portfolio_variance
    ):
        fail(
            "Portfolio variance is non-finite."
        )

    if not np.isfinite(
        portfolio_volatility
    ):
        fail(
            "Portfolio volatility is non-finite."
        )

    if not np.isfinite(
        gross_exposure
    ):
        fail(
            "Gross exposure is non-finite."
        )

    if not np.isfinite(
        net_exposure
    ):
        fail(
            "Net exposure is non-finite."
        )

    if portfolio_variance < -NUMERIC_TOLERANCE:
        fail(
            "Portfolio variance is negative: "
            f"{portfolio_variance}"
        )

    if portfolio_volatility < -NUMERIC_TOLERANCE:
        fail(
            "Portfolio volatility is negative: "
            f"{portfolio_volatility}"
        )

    if gross_exposure < -NUMERIC_TOLERANCE:
        fail(
            "Gross exposure is negative: "
            f"{gross_exposure}"
        )

    # --------------------------------------------------------------
    # POSITION COUNT
    # --------------------------------------------------------------

    positive_positions = sum(
        abs(
            float(weight)
        ) > NUMERIC_TOLERANCE
        for weight in decision.weights.values()
    )

    if decision.number_of_positions != positive_positions:
        fail(
            "Decision number_of_positions does not match "
            "the number of non-zero portfolio weights.\n"
            f"Reported: {decision.number_of_positions}\n"
            f"Calculated: {positive_positions}"
        )

    if decision.number_of_positions <= 0:
        fail(
            "Production decision contains no active positions."
        )

    # --------------------------------------------------------------
    # RISK CONTRIBUTION VALIDATION
    # --------------------------------------------------------------

    if set(
        decision.risk_contributions
    ) != set(TICKERS):
        fail(
            "Risk-contribution assets do not match the "
            "production universe."
        )

    if set(
        decision.risk_contribution_pct
    ) != set(TICKERS):
        fail(
            "Risk-contribution percentage assets do not match "
            "the production universe."
        )

    risk_contributions = np.asarray(
        list(
            decision.risk_contributions.values()
        ),
        dtype=float,
    )

    risk_contribution_pct = np.asarray(
        list(
            decision.risk_contribution_pct.values()
        ),
        dtype=float,
    )

    if not np.isfinite(
        risk_contributions
    ).all():
        fail(
            "Risk contributions contain non-finite values."
        )

    if not np.isfinite(
        risk_contribution_pct
    ).all():
        fail(
            "Risk contribution percentages contain "
            "non-finite values."
        )

    # --------------------------------------------------------------
    # ENGINE HEALTH
    # --------------------------------------------------------------

    health = engine.health_check()

    print()
    print("ENGINE HEALTH:")
    print(
        health
    )

    if health.get(
        "healthy"
    ) is not True:
        fail(
            "Production engine health check failed: "
            f"{health}"
        )

    # --------------------------------------------------------------
    # DETERMINISM CHECK
    #
    # Re-run the exact same decision using the same inputs.
    # The resulting production weights and key metrics must be
    # numerically stable.
    # --------------------------------------------------------------

    print()
    print("DETERMINISM CHECK:")

    second_decision = engine.decide(
        portfolio=portfolio,
        returns=returns,
        macro_data=macro_data,
        expected_returns=expected_returns,
        regimes=regimes,
        scenarios=None,
    )

    if second_decision.status != decision.status:
        fail(
            "Production decision status is not deterministic."
        )

    if second_decision.approved != decision.approved:
        fail(
            "Production approval state is not deterministic."
        )

    if second_decision.regime != decision.regime:
        fail(
            "Production regime is not deterministic."
        )

    for ticker in TICKERS:

        first_weight = float(
            decision.weights[ticker]
        )

        second_weight = float(
            second_decision.weights[ticker]
        )

        if not np.isclose(
            first_weight,
            second_weight,
            atol=1e-10,
            rtol=1e-10,
        ):
            fail(
                "Production weight is not deterministic for "
                f"{ticker}: "
                f"{first_weight} vs {second_weight}"
            )

    if not np.isclose(
        float(
            decision.portfolio_variance
        ),
        float(
            second_decision.portfolio_variance
        ),
        atol=1e-10,
        rtol=1e-10,
    ):
        fail(
            "Portfolio variance is not deterministic."
        )

    if not np.isclose(
        float(
            decision.portfolio_volatility
        ),
        float(
            second_decision.portfolio_volatility
        ),
        atol=1e-10,
        rtol=1e-10,
    ):
        fail(
            "Portfolio volatility is not deterministic."
        )

    print(
        "PASSED"
    )

    # --------------------------------------------------------------
    # FINAL STATUS
    # --------------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "STEP 8 PASSED — REGISTRY-QUALIFIED HISTORICAL DATA "
        "PRODUCTION INTEGRATION SUCCESSFUL"
    )
    print("=" * 80)

    return decision


# ======================================================================
# SECTION 14 — MAIN
# ======================================================================

def main() -> None:
    """Execute the complete Step 8 integration test."""

    banner(
        "STEP 8 — REGISTRY-QUALIFIED HISTORICAL DATA PRODUCTION TEST"
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
        "Minimum observations:",
        MIN_OBSERVATIONS,
    )

    print()
    print(
        "Regime lookback:",
        REGIME_LOOKBACK,
    )

    # --------------------------------------------------------------
    # 1. HISTORICAL MARKET DATA
    # --------------------------------------------------------------

    prices, returns = load_market_data()

    # --------------------------------------------------------------
    # 2. FRED MACRO DATA
    # --------------------------------------------------------------

    macro_df = load_fred_data(
        prices.index
    )

    # --------------------------------------------------------------
    # 3. HISTORICAL REGIMES
    # --------------------------------------------------------------

    regimes = build_regime_history(
        macro_df
    )

    # --------------------------------------------------------------
    # 4. CURRENT MACRO STATE
    # --------------------------------------------------------------

    macro_data = build_current_macro_data(
        macro_df
    )

    # --------------------------------------------------------------
    # 5. EXPECTED RETURNS
    # --------------------------------------------------------------

    expected_returns = build_expected_returns(
        prices
    )

    # --------------------------------------------------------------
    # 6. INPUT PORTFOLIO
    # --------------------------------------------------------------

    portfolio = build_portfolio()

    # --------------------------------------------------------------
    # 7. ALIGN DECISION HISTORY
    # --------------------------------------------------------------

    (
        prices,
        aligned_returns,
        aligned_macro,
        aligned_regimes,
    ) = align_production_history(
        prices=prices,
        returns=returns,
        macro_df=macro_df,
        regimes=regimes,
    )

    # --------------------------------------------------------------
    # 8. RUN PRODUCTION DECISION
    # --------------------------------------------------------------

    run_production_decision(
        prices=prices,
        returns=aligned_returns,
        macro_df=aligned_macro,
        regimes=aligned_regimes,
        macro_data=macro_data,
        expected_returns=expected_returns,
        portfolio=portfolio,
    )


# ======================================================================
# EXECUTION
# ======================================================================

if __name__ == "__main__":
    main()