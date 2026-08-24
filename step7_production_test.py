# ======================================================================
# STEP 7 — END-TO-END 14-ASSET PRODUCTION PORTFOLIO DECISION
# ======================================================================

from __future__ import annotations

import numpy as np
import pandas as pd

from core_constants import REGIME_MAX_LEVERAGE
from productioncomposition import ProductionComposition


# ======================================================================
# 7.1 PRODUCTION ASSET UNIVERSE
# ======================================================================

PRODUCTION_ASSETS = [
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
]

OBSERVATIONS = 300
RANDOM_SEED = 42
REGIME = "EXPANSION"

EXPECTED_TICKER_COUNT = len(PRODUCTION_ASSETS)


# ======================================================================
# 7.2 BUILD PRODUCTION ENGINE
# ======================================================================

composition = ProductionComposition()
engine = composition.build_engine()

print()
print("=" * 80)
print("STEP 7 — END-TO-END 14-ASSET PRODUCTION PORTFOLIO DECISION")
print("=" * 80)


# ======================================================================
# 7.3 VERIFY PRODUCTION DEPENDENCIES
# ======================================================================

print()
print("ENGINE:")
print(engine)

print()
print("OPTIMIZER:")
print(engine.optimizer)

print()
print("RISK BUDGET ENGINE:")
print(engine.optimizer.risk_budget_engine)

print()
print("BLACK-LITTERMAN:")
print(engine.black_litterman)

assert engine is not None
assert engine.optimizer is not None
assert engine.optimizer.risk_budget_engine is not None
assert engine.optimizer.constraints is not None
assert engine.black_litterman is not None


# ======================================================================
# 7.4 VERIFY THE CANONICAL 14-ASSET UNIVERSE
# ======================================================================

print()
print("PRODUCTION ASSET UNIVERSE:")
print(PRODUCTION_ASSETS)

assert len(PRODUCTION_ASSETS) == 14
assert len(set(PRODUCTION_ASSETS)) == 14


# ======================================================================
# 7.5 PRICE / RETURN HISTORY
#
# 300 observations provide enough history for the production forecast
# components:
#
#   Momentum       = 252
#   Trend          = 200
#   Mean reversion = 63
#
# The synthetic return process contains common factors so the
# covariance matrix is non-degenerate and economically meaningful.
# ======================================================================

rng = np.random.default_rng(RANDOM_SEED)

n_assets = len(PRODUCTION_ASSETS)

market_factor = rng.normal(
    loc=0.0004,
    scale=0.0080,
    size=OBSERVATIONS,
)

style_factor = rng.normal(
    loc=0.0001,
    scale=0.0040,
    size=OBSERVATIONS,
)

idiosyncratic = rng.normal(
    loc=0.0,
    scale=0.0050,
    size=(OBSERVATIONS, n_assets),
)

market_loadings = np.array(
    [
        1.00,
        1.08,
        1.15,
        0.82,
        0.95,
        -0.35,
        -0.20,
        -0.05,
        0.20,
        0.45,
        0.10,
        0.15,
        0.30,
        0.75,
    ],
    dtype=float,
)

style_loadings = np.array(
    [
        0.10,
        0.20,
        0.35,
        0.15,
        0.25,
        -0.10,
        -0.05,
        -0.02,
        0.10,
        0.25,
        -0.15,
        -0.10,
        0.05,
        0.20,
    ],
    dtype=float,
)

asset_drifts = np.array(
    [
        0.00055,
        0.00060,
        0.00050,
        0.00040,
        0.00045,
        0.00020,
        0.00015,
        0.00008,
        0.00025,
        0.00030,
        0.00035,
        0.00040,
        0.00030,
        0.00045,
    ],
    dtype=float,
)

returns_array = (
    asset_drifts
    + np.outer(
        market_factor,
        market_loadings,
    )
    + np.outer(
        style_factor,
        style_loadings,
    )
    + idiosyncratic
)

# ----------------------------------------------------------------------
# IMPORTANT:
#
# Assign the index to RETURNS before constructing PRICES.
#
# This guarantees:
#
#     prices.index == returns.index
#
# and also allows the macro and regime histories to use exactly the
# same observation dates.
# ----------------------------------------------------------------------

observation_index = pd.date_range(
    start="2020-01-01",
    periods=OBSERVATIONS,
    freq="B",
)

returns = pd.DataFrame(
    returns_array,
    index=observation_index,
    columns=PRODUCTION_ASSETS,
)

prices = (
    100.0
    * (1.0 + returns).cumprod()
)


print()
print("PRICE HISTORY:")
print(f"Observations: {len(prices)}")
print(f"Tickers: {list(prices.columns)}")
print(f"Shape: {prices.shape}")
print(f"Start: {prices.index[0]}")
print(f"End: {prices.index[-1]}")

print()
print("RETURN HISTORY:")
print(f"Observations: {len(returns)}")
print(f"Shape: {returns.shape}")


assert len(prices) == OBSERVATIONS
assert len(returns) == OBSERVATIONS

assert list(prices.columns) == PRODUCTION_ASSETS
assert list(returns.columns) == PRODUCTION_ASSETS

assert prices.shape == (
    OBSERVATIONS,
    EXPECTED_TICKER_COUNT,
)

assert returns.shape == (
    OBSERVATIONS,
    EXPECTED_TICKER_COUNT,
)

assert prices.index.equals(
    returns.index
)

assert prices.notna().all().all()
assert returns.notna().all().all()

assert np.isfinite(
    prices.to_numpy()
).all()

assert np.isfinite(
    returns.to_numpy()
).all()

assert (
    prices > 0.0
).all().all()


# ======================================================================
# 7.6 MACRO HISTORY
# ======================================================================

macro_data = {
    "unemployment": pd.Series(
        np.full(
            OBSERVATIONS,
            5.0,
            dtype=float,
        ),
        index=observation_index,
        name="unemployment",
    ),
    "yield_spread": pd.Series(
        np.full(
            OBSERVATIONS,
            1.5,
            dtype=float,
        ),
        index=observation_index,
        name="yield_spread",
    ),
    "inflation": pd.Series(
        np.full(
            OBSERVATIONS,
            2.5,
            dtype=float,
        ),
        index=observation_index,
        name="inflation",
    ),
}


print()
print("MACRO HISTORY:")
print(
    {
        key: len(value)
        for key, value in macro_data.items()
    }
)


assert set(macro_data) == {
    "unemployment",
    "yield_spread",
    "inflation",
}

for series in macro_data.values():
    assert len(series) == OBSERVATIONS
    assert series.index.equals(
        observation_index
    )
    assert series.notna().all()
    assert np.isfinite(
        series.to_numpy()
    ).all()


# ======================================================================
# 7.7 REGIME HISTORY
# ======================================================================

regimes = pd.Series(
    [REGIME] * OBSERVATIONS,
    index=observation_index,
    name="regime",
)


print()
print("REGIME HISTORY:")
print(f"Observations: {len(regimes)}")
print(
    "Unique regimes:",
    regimes.unique().tolist(),
)

assert len(regimes) == OBSERVATIONS

assert regimes.index.equals(
    observation_index
)

assert regimes.notna().all()

assert regimes.unique().tolist() == [
    REGIME
]


# ======================================================================
# 7.8 INPUT PORTFOLIO
# ======================================================================

initial_weight = (
    1.0 / EXPECTED_TICKER_COUNT
)

portfolio_weights = {
    ticker: initial_weight
    for ticker in PRODUCTION_ASSETS
}

portfolio = {
    "weights": portfolio_weights,
}


print()
print("INPUT PORTFOLIO:")
print(portfolio)

assert set(
    portfolio["weights"].keys()
) == set(PRODUCTION_ASSETS)

assert len(
    portfolio["weights"]
) == EXPECTED_TICKER_COUNT

assert all(
    np.isfinite(float(weight))
    for weight in portfolio["weights"].values()
)

assert all(
    float(weight) >= 0.0
    for weight in portfolio["weights"].values()
)

assert abs(
    sum(
        portfolio["weights"].values()
    ) - 1.0
) < 1e-8


# ======================================================================
# 7.9 COMPLETE INPUT ALIGNMENT VALIDATION
# ======================================================================

print()
print("INPUT HISTORY VALIDATION:")

print(
    f"Prices: {prices.shape}"
)

print(
    f"Returns: {returns.shape}"
)

print(
    "Macro:",
    {
        key: len(value)
        for key, value in macro_data.items()
    },
)

print(
    f"Regimes: {len(regimes)}"
)

print(
    f"Assets: {len(PRODUCTION_ASSETS)}"
)

print(
    "Aligned tickers:",
    list(prices.columns),
)


assert prices.index.equals(
    returns.index
)

assert prices.index.equals(
    observation_index
)

assert returns.index.equals(
    observation_index
)

assert regimes.index.equals(
    observation_index
)

for series in macro_data.values():
    assert series.index.equals(
        observation_index
    )

assert list(prices.columns) == (
    PRODUCTION_ASSETS
)

assert list(returns.columns) == (
    PRODUCTION_ASSETS
)

print("PASSED")


# ======================================================================
# 7.10 RUN PRODUCTION DECISION
#
# IMPORTANT:
#
# The existing production contract is:
#
#     engine.decide(
#         portfolio=...,
#         returns=...,
#         macro_data=...,
#         regimes=...,
#     )
#
# Do not introduce a prices= argument here.
# ======================================================================

print()
print("RUNNING 14-ASSET PRODUCTION DECISION...")

decision = engine.decide(
    portfolio=portfolio,
    returns=prices,
    macro_data=macro_data,
    regimes=regimes,
)


# ======================================================================
# 7.11 DISPLAY DECISION
# ======================================================================

print()
print("STATUS:")
print(decision.status)

print()
print("APPROVED:")
print(decision.approved)

print()
print("REGIME:")
print(decision.regime)

print()
print("TICKERS:")
print(decision.tickers)

print()
print("WEIGHTS:")
print(decision.weights)

print()
print("EXPECTED RETURNS:")
print(decision.expected_returns)

print()
print("PORTFOLIO RETURN:")
print(decision.portfolio_return)

print()
print("PORTFOLIO VOLATILITY:")
print(decision.portfolio_volatility)

print()
print("PORTFOLIO VARIANCE:")
print(decision.portfolio_variance)

print()
print("GROSS EXPOSURE:")
print(decision.gross_exposure)

print()
print("NET EXPOSURE:")
print(decision.net_exposure)

print()
print("NUMBER OF POSITIONS:")
print(decision.number_of_positions)

print()
print("RISK CONTRIBUTIONS:")
print(decision.risk_contributions)

print()
print("RISK CONTRIBUTION %:")
print(decision.risk_contribution_pct)

print()
print("SCENARIO RESULTS:")
print(decision.scenario_results)

print()
print("WARNINGS:")
print(decision.warnings)

print()
print("ERRORS:")
print(decision.errors)

print()
print("DIAGNOSTICS:")
print(decision.diagnostics)


# ======================================================================
# 7.12 ENGINE SUMMARY
# ======================================================================

print()
print("ENGINE SUMMARY:")

summary = engine.summary()

print(summary)


# ======================================================================
# 7.13 ENGINE HEALTH
# ======================================================================

print()
print("ENGINE HEALTH:")

health = engine.health_check()

print(health)


# ======================================================================
# 7.14 PRODUCTION ASSERTIONS
# ======================================================================

assert decision is not None

assert decision.status != "FAILED", (
    "14-asset production decision failed: "
    f"{decision.errors}"
)

assert decision.approved is True

assert decision.regime is not None

assert decision.regime.lower() == (
    "expansion"
)


# ----------------------------------------------------------------------
# Ticker integrity
# ----------------------------------------------------------------------

assert len(decision.tickers) == (
    EXPECTED_TICKER_COUNT
)

assert set(decision.tickers) == set(
    PRODUCTION_ASSETS
)


# ----------------------------------------------------------------------
# Weight integrity
# ----------------------------------------------------------------------

assert len(decision.weights) == (
    EXPECTED_TICKER_COUNT
)

assert set(
    decision.weights.keys()
) == set(PRODUCTION_ASSETS)

assert all(
    np.isfinite(float(weight))
    for weight in decision.weights.values()
)

assert all(
    float(weight) >= -1e-10
    for weight in decision.weights.values()
)

weight_sum = sum(
    float(weight)
    for weight in decision.weights.values()
)

gross_exposure = sum(
    abs(float(weight))
    for weight in decision.weights.values()
)

assert abs(
    weight_sum
    - decision.net_exposure
) < 1e-8

assert abs(
    gross_exposure
    - decision.gross_exposure
) < 1e-8


# ----------------------------------------------------------------------
# Exposure integrity
# ----------------------------------------------------------------------

assert decision.gross_exposure >= (
    -1e-10
)

assert decision.net_exposure >= (
    -1e-10
)


# ----------------------------------------------------------------------
# Position count
# ----------------------------------------------------------------------

expected_position_count = sum(
    1
    for weight in decision.weights.values()
    if abs(float(weight)) > 1e-10
)

assert (
    decision.number_of_positions
    == expected_position_count
)

assert (
    0
    <= decision.number_of_positions
    <= EXPECTED_TICKER_COUNT
)


# ----------------------------------------------------------------------
# Expected-return integrity
# ----------------------------------------------------------------------

assert len(
    decision.expected_returns
) == EXPECTED_TICKER_COUNT

assert set(
    decision.expected_returns.keys()
) == set(PRODUCTION_ASSETS)

assert all(
    np.isfinite(float(value))
    for value in decision.expected_returns.values()
)


# ----------------------------------------------------------------------
# Portfolio statistics
# ----------------------------------------------------------------------

assert np.isfinite(
    float(decision.portfolio_return)
)

assert np.isfinite(
    float(decision.portfolio_variance)
)

assert np.isfinite(
    float(decision.portfolio_volatility)
)

assert decision.portfolio_variance >= (
    -1e-10
)

assert decision.portfolio_volatility >= (
    -1e-10
)


# ----------------------------------------------------------------------
# Risk contribution integrity
# ----------------------------------------------------------------------

assert len(
    decision.risk_contributions
) == EXPECTED_TICKER_COUNT

assert set(
    decision.risk_contributions.keys()
) == set(PRODUCTION_ASSETS)

assert len(
    decision.risk_contribution_pct
) == EXPECTED_TICKER_COUNT

assert set(
    decision.risk_contribution_pct.keys()
) == set(PRODUCTION_ASSETS)

assert all(
    np.isfinite(float(value))
    for value in decision.risk_contributions.values()
)

assert all(
    np.isfinite(float(value))
    for value in decision.risk_contribution_pct.values()
)

risk_contribution_sum = sum(
    float(value)
    for value
    in decision.risk_contributions.values()
)

assert abs(
    risk_contribution_sum
    - decision.portfolio_variance
) < 1e-6


# ----------------------------------------------------------------------
# Risk contribution percentage integrity
# ----------------------------------------------------------------------

risk_pct_sum = sum(
    float(value)
    for value
    in decision.risk_contribution_pct.values()
)

if decision.portfolio_variance > 1e-10:
    assert abs(
        risk_pct_sum - 1.0
    ) < 1e-6


# ----------------------------------------------------------------------
# Position-weight limit
# ----------------------------------------------------------------------

maximum_position_weight = max(
    abs(float(weight))
    for weight in decision.weights.values()
)

assert (
    maximum_position_weight
    <= 0.25 + 1e-8
)


# ----------------------------------------------------------------------
# Regime leverage limit
# ----------------------------------------------------------------------

regime_key = str(
    decision.regime
).lower()

if regime_key in REGIME_MAX_LEVERAGE:
    maximum_leverage = float(
        REGIME_MAX_LEVERAGE[regime_key]
    )

    assert (
        decision.gross_exposure
        <= maximum_leverage + 1e-8
    )


# ----------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------

assert health["healthy"] is True

assert health["components"]

assert health["components"][
    "optimizer"
]["healthy"] is True


# ======================================================================
# 7.15 DETERMINISM CHECK
# ======================================================================

print()
print("DETERMINISM CHECK:")

second_engine = (
    ProductionComposition()
    .build_engine()
)

second_decision = second_engine.decide(
    portfolio=portfolio,
    returns=prices,
    macro_data=macro_data,
    regimes=regimes,
)

assert second_decision.status == (
    decision.status
)

assert second_decision.approved == (
    decision.approved
)

assert second_decision.regime == (
    decision.regime
)

assert second_decision.tickers == (
    decision.tickers
)

for ticker in PRODUCTION_ASSETS:
    assert np.isclose(
        float(
            second_decision.weights[ticker]
        ),
        float(
            decision.weights[ticker]
        ),
        atol=1e-10,
        rtol=1e-10,
    )

print("PASSED")


# ======================================================================
# 7.16 FINAL STATUS
# ======================================================================

print()
print("=" * 80)
print(
    "STEP 7 PASSED — "
    "14-ASSET END-TO-END PRODUCTION "
    "DECISION SUCCESSFUL"
)
print("=" * 80)