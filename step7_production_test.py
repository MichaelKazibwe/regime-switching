# ======================================================================
# STEP 7 — END-TO-END PRODUCTION PORTFOLIO DECISION
# ======================================================================

import numpy as np
import pandas as pd

from productioncomposition import (
    ProductionComposition,
)


# ======================================================================
# 7.1 BUILD PRODUCTION ENGINE
# ======================================================================

composition = (
    ProductionComposition()
)

engine = (
    composition.build_engine()
)


print()
print("=" * 80)
print("STEP 7 — END-TO-END PRODUCTION PORTFOLIO DECISION")
print("=" * 80)


# ======================================================================
# 7.2 VERIFY PRODUCTION DEPENDENCIES
# ======================================================================

print()
print("ENGINE:")
print(engine)

print()
print("OPTIMIZER:")
print(engine.optimizer)

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


assert engine is not None
assert engine.optimizer is not None
assert (
    engine.optimizer.risk_budget_engine
    is not None
)
assert (
    engine.optimizer.constraints
    is not None
)
assert (
    engine.black_litterman
    is not None
)


# ======================================================================
# 7.3 PRICE HISTORY
#
# ExpectedReturnForecaster requires price observations.
#
# 300 observations deliberately gives us enough history for:
#   Momentum       = 252
#   Trend          = 200
#   Mean reversion = 63
# ======================================================================

tickers = [
    "SPY",
    "EFA",
    "EEM",
]

observations = 300

rng = np.random.default_rng(
    42
)

returns = pd.DataFrame(
    rng.normal(
        loc=0.0005,
        scale=0.01,
        size=(
            observations,
            len(tickers),
        ),
    ),
    columns=tickers,
)

prices = (
    100.0
    * (
        1.0
        + returns
    ).cumprod()
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


assert len(prices) == 300
assert list(prices.columns) == tickers
assert prices.shape == (
    300,
    3,
)


# ======================================================================
# 7.4 MACRO HISTORY
#
# 300 observations are supplied.
#
# _identify_regime() converts these historical Series into the latest
# scalar observation before calling MacroRegimeModel.classify().
# ======================================================================

macro_data = {
    "unemployment": pd.Series(
        np.full(
            observations,
            5.0,
        )
    ),

    "yield_spread": pd.Series(
        np.full(
            observations,
            1.5,
        )
    ),

    "inflation": pd.Series(
        np.full(
            observations,
            2.5,
        )
    ),
}


print()
print("MACRO HISTORY:")
print(
    {
        key: len(value)
        for key, value
        in macro_data.items()
    }
)


assert len(
    macro_data["unemployment"]
) == 300

assert len(
    macro_data["yield_spread"]
) == 300

assert len(
    macro_data["inflation"]
) == 300


# ======================================================================
# 7.5 REGIME HISTORY
#
# RegimeCovariance requires historical regime labels aligned with the
# return observations.
# ======================================================================

regimes = pd.Series(
    ["EXPANSION"] * observations
)


print()
print("REGIME HISTORY:")
print(
    f"Observations: {len(regimes)}"
)
print(
    "Unique regimes:",
    regimes.unique().tolist(),
)


assert len(regimes) == 300

assert (
    regimes.unique().tolist()
    == ["EXPANSION"]
)


# ======================================================================
# 7.6 PORTFOLIO
# ======================================================================

portfolio = {
    "weights": {
        "SPY": 1.0 / 3.0,
        "EFA": 1.0 / 3.0,
        "EEM": 1.0 / 3.0,
    }
}


print()
print("PORTFOLIO:")
print(portfolio)


assert set(
    portfolio["weights"].keys()
) == set(tickers)

assert abs(
    sum(
        portfolio["weights"].values()
    )
    - 1.0
) < 1e-8


# ======================================================================
# 7.7 INPUT VALIDATION
# ======================================================================

print()
print("INPUT HISTORY VALIDATION: PASSED")


# ======================================================================
# 7.8 RUN PRODUCTION DECISION
#
# IMPORTANT:
#
# PortfolioDecisionEngine.decide() accepts:
#
#     portfolio
#     returns
#     macro_data
#     regimes
#
# It DOES NOT accept:
#
#     prices=
#
# ======================================================================

print()
print("RUNNING PRODUCTION DECISION...")


decision = (
    engine.decide(
        portfolio=portfolio,
        returns=prices,
        macro_data=macro_data,
        regimes=regimes,
    )
)


# ======================================================================
# 7.9 DISPLAY DECISION
# ======================================================================

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


# ======================================================================
# 7.10 ENGINE SUMMARY
# ======================================================================

print()
print("ENGINE SUMMARY:")

summary = (
    engine.summary()
)

print(summary)


# ======================================================================
# 7.11 ENGINE HEALTH
# ======================================================================

print()
print("ENGINE HEALTH:")

health = (
    engine.health_check()
)

print(health)


# ======================================================================
# 7.12 PRODUCTION ASSERTIONS
# ======================================================================

assert decision is not None

assert decision.status != "FAILED", (
    "Production decision failed: "
    f"{decision.errors}"
)

assert decision.approved is True

assert decision.regime is not None

assert (
    decision.regime.upper()
    == "EXPANSION"
)

assert len(
    decision.tickers
) == 3

assert len(
    decision.weights
) == 3

assert len(
    decision.expected_returns
) == 3

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
    health["healthy"]
    is True
)


# ======================================================================
# 7.13 FINAL STATUS
# ======================================================================

print()
print("=" * 80)
print(
    "STEP 7 PASSED — END-TO-END PRODUCTION DECISION SUCCESSFUL"
)
print("=" * 80)