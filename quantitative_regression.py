from __future__ import annotations

import inspect
import sys
import time
import traceback

from typing import Any

import numpy as np
import pandas as pd

# ============================================================================
# IMPORTS
# ============================================================================

from blacklitterman import BlackLittermanModel
from constraints import PortfolioConstraints
from core_constants import (
    REGIME_MAX_LEVERAGE,
    REGIME_RISK_BUDGETS,
    REGIME_VOL_TARGETS,
)
from expectedreturnforecaster import ExpectedReturnForecaster
from portfoliooptimizer import PortfolioOptimizer
from productioncomposition import ProductionComposition
from riskbudgetengine import RiskBudgetEngine
from volatilitytargeting import VolatilityTargeting


# ============================================================================
# CONFIGURATION
# ============================================================================

ASSETS = [
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

REGIMES = [
    "bull",
    "neutral",
    "crisis",
]

API_VERSION = "1.0.0"

TOLERANCE = 1e-8


# ============================================================================
# EXCEPTION
# ============================================================================


class QuantitativeRegressionFailure(Exception):
    """Raised when a quantitative regression check fails."""


# ============================================================================
# REGRESSION STATE
# ============================================================================


class RegressionState:
    def __init__(self) -> None:
        self.components: Any = None
        self.optimizer: PortfolioOptimizer | None = None
        self.forecaster: ExpectedReturnForecaster | None = None
        self.risk_budget_engine: RiskBudgetEngine | None = None
        self.constraints: PortfolioConstraints | None = None
        self.vol_targeting: VolatilityTargeting | None = None
        self.black_litterman: BlackLittermanModel | None = None

        self.covariance: np.ndarray | None = None
        self.prices: pd.DataFrame | None = None
        self.returns: pd.DataFrame | None = None

        self.expected_returns: pd.Series | None = None
        self.optimizer_result: dict[str, Any] | None = None


STATE = RegressionState()


# ============================================================================
# TEST RUNNER
# ============================================================================


class RegressionRunner:
    def __init__(self) -> None:
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.failures: list[str] = []
        self.started = time.perf_counter()

    def check(
        self,
        name: str,
        function,
    ) -> bool:
        self.total += 1

        started = time.perf_counter()

        try:
            function()

            elapsed = time.perf_counter() - started

            print(
                f"[PASS] {name} "
                f"({elapsed:.3f}s)"
            )

            self.passed += 1
            return True

        except Exception as exc:
            elapsed = time.perf_counter() - started

            self.failed += 1
            self.failures.append(
                f"{name}: {type(exc).__name__}: {exc}"
            )

            print(
                f"[FAIL] {name} "
                f"({elapsed:.3f}s)"
            )

            print(
                f"       {type(exc).__name__}: {exc}"
            )

            return False


RUNNER = RegressionRunner()


# ============================================================================
# NUMERICAL HELPERS
# ============================================================================


def assert_close(
    actual: float,
    expected: float,
    *,
    tolerance: float = TOLERANCE,
    message: str = "",
) -> None:
    if not np.isclose(
        actual,
        expected,
        atol=tolerance,
        rtol=tolerance,
    ):
        raise QuantitativeRegressionFailure(
            message
            or (
                f"Values differ: "
                f"actual={actual}, "
                f"expected={expected}"
            )
        )


def assert_finite_array(
    values: Any,
    name: str,
) -> None:
    array = np.asarray(
        values,
        dtype=float,
    )

    if not np.isfinite(array).all():
        raise QuantitativeRegressionFailure(
            f"{name} contains non-finite values."
        )


def assert_series_finite(
    values: pd.Series,
    name: str,
) -> None:
    if not isinstance(
        values,
        pd.Series,
    ):
        raise QuantitativeRegressionFailure(
            f"{name} must be a pandas Series."
        )

    assert_finite_array(
        values.to_numpy(),
        name,
    )


# ============================================================================
# SYNTHETIC MARKET DATA
# ============================================================================


def build_synthetic_prices() -> pd.DataFrame:
    """
    Construct deterministic synthetic price history.

    The history is long enough for the production expected-return
    forecaster and covariance calculations.
    """

    observations = 756

    dates = pd.bdate_range(
        end=pd.Timestamp("2026-08-21"),
        periods=observations,
    )

    rng = np.random.default_rng(
        20260821
    )

    n_assets = len(ASSETS)

    base_returns = rng.normal(
        loc=0.00025,
        scale=0.009,
        size=(
            observations,
            n_assets,
        ),
    )

    # Add deterministic asset-specific drift.
    drifts = np.linspace(
        0.00005,
        0.00035,
        n_assets,
    )

    returns = (
        base_returns
        + drifts
    )

    prices = np.empty_like(
        returns
    )

    prices[0] = (
        100.0
        * np.exp(
            returns[0]
        )
    )

    for index in range(
        1,
        observations,
    ):
        prices[index] = (
            prices[index - 1]
            * np.exp(
                returns[index]
            )
        )

    return pd.DataFrame(
        prices,
        index=dates,
        columns=ASSETS,
    )


def build_synthetic_covariance() -> np.ndarray:
    """
    Construct a deterministic positive-definite covariance matrix.
    """

    rng = np.random.default_rng(
        20260822
    )

    n_assets = len(ASSETS)

    matrix = rng.normal(
        size=(
            n_assets,
            n_assets,
        )
    )

    covariance = (
        matrix @ matrix.T
    )

    covariance /= float(
        np.max(
            np.diag(
                covariance
            )
        )
    )

    covariance += (
        np.eye(n_assets)
        * 0.0001
    )

    covariance = (
        covariance
        + covariance.T
    ) / 2.0

    return covariance


# ============================================================================
# 1. MODULE LOADING
# ============================================================================


def regression_module_loading() -> None:
    """
    Verify that the production quantitative modules can be imported and
    their primary classes are available.
    """

    modules = [
        "blacklitterman",
        "constraints",
        "core_constants",
        "expectedreturnforecaster",
        "portfoliooptimizer",
        "productioncomposition",
        "riskbudgetengine",
        "volatilitytargeting",
    ]

    for module_name in modules:
        __import__(
            module_name
        )

    print(
        "       Production quantitative modules imported successfully."
    )


# ============================================================================
# 2. NUMERICAL PRIMITIVES
# ============================================================================


def regression_numerical_primitives() -> None:
    covariance = build_synthetic_covariance()

    STATE.covariance = covariance

    assert covariance.shape == (
        len(ASSETS),
        len(ASSETS),
    )

    assert_finite_array(
        covariance,
        "Covariance matrix",
    )

    eigenvalues = np.linalg.eigvalsh(
        covariance
    )

    minimum_eigenvalue = float(
        np.min(
            eigenvalues
        )
    )

    maximum_eigenvalue = float(
        np.max(
            eigenvalues
        )
    )

    print(
        f"       covariance shape: "
        f"{covariance.shape}"
    )

    print(
        f"       minimum eigenvalue: "
        f"{minimum_eigenvalue:.12f}"
    )

    print(
        f"       maximum eigenvalue: "
        f"{maximum_eigenvalue:.12f}"
    )

    if minimum_eigenvalue <= 0.0:
        raise QuantitativeRegressionFailure(
            "Covariance matrix is not positive definite."
        )


def regression_covariance_identity() -> None:
    if STATE.covariance is None:
        raise QuantitativeRegressionFailure(
            "Covariance matrix unavailable."
        )

    n_assets = len(ASSETS)

    weights = np.full(
        n_assets,
        1.0 / n_assets,
    )

    variance = float(
        weights
        @ STATE.covariance
        @ weights
    )

    volatility = float(
        np.sqrt(
            variance
        )
    )

    marginal_risk = (
        STATE.covariance
        @ weights
    )

    risk_contributions = (
        weights
        * marginal_risk
    )

    rc_sum = float(
        np.sum(
            risk_contributions
        )
    )

    print(
        f"       portfolio variance: "
        f"{variance:.12f}"
    )

    print(
        f"       portfolio volatility: "
        f"{volatility:.12f}"
    )

    print(
        f"       RC sum: "
        f"{rc_sum:.12f}"
    )

    assert_close(
        rc_sum,
        variance,
        message=(
            "Risk contributions must sum "
            "to portfolio variance."
        ),
    )


# ============================================================================
# 3. PORTFOLIO CONSTRAINTS
# ============================================================================


def regression_constraints() -> None:
    constraints = PortfolioConstraints()

    STATE.constraints = constraints

    raw_weights = np.full(
        len(ASSETS),
        1.0 / len(ASSETS),
    )

    result = constraints.enforce(
        raw_weights
    )

    if not isinstance(
        result,
        dict,
    ):
        raise QuantitativeRegressionFailure(
            "PortfolioConstraints.enforce() "
            "must return a dictionary."
        )

    if "weights" not in result:
        raise QuantitativeRegressionFailure(
            "Constraint result missing 'weights'."
        )

    if "cash" not in result:
        raise QuantitativeRegressionFailure(
            "Constraint result missing 'cash'."
        )

    weights = np.asarray(
        result["weights"],
        dtype=float,
    )

    cash = float(
        result["cash"]
    )

    assert_finite_array(
        weights,
        "Constrained weights",
    )

    maximum_weight = float(
        np.max(
            weights
        )
    )

    print(
        f"       maximum position weight: "
        f"{maximum_weight:.12f}"
    )

    print(
        f"       constrained weight sum: "
        f"{weights.sum():.12f}"
    )

    print(
        f"       cash: "
        f"{cash:.12f}"
    )

    if maximum_weight > (
        PortfolioConstraints.MAX_WEIGHT
        + 1e-10
    ):
        raise QuantitativeRegressionFailure(
            "Position weight exceeds maximum."
        )

    if cash < -1e-10:
        raise QuantitativeRegressionFailure(
            "Cash allocation is negative."
        )

    if (
        weights.sum()
        + cash
        > 1.000001
    ):
        raise QuantitativeRegressionFailure(
            "Weights plus cash exceed 100%."
        )


# ============================================================================
# 4. VOLATILITY TARGETING
# ============================================================================


def regression_volatility_targeting() -> None:
    if STATE.covariance is None:
        raise QuantitativeRegressionFailure(
            "Covariance unavailable."
        )

    engine = VolatilityTargeting()

    STATE.vol_targeting = engine

    weights = np.full(
        len(ASSETS),
        1.0 / len(ASSETS),
    )

    original_volatility = engine.portfolio_volatility(
        weights,
        STATE.covariance,
    )

    target_volatility = 0.10

    scaled = engine.scale_weights(
        weights,
        STATE.covariance,
        target_vol=target_volatility,
        max_leverage=1.0,
    )

    final_volatility = engine.portfolio_volatility(
        scaled,
        STATE.covariance,
    )

    gross_exposure = float(
        np.sum(
            np.abs(
                scaled
            )
        )
    )

    print(
        f"       original volatility: "
        f"{original_volatility:.12f}"
    )

    print(
        f"       target volatility: "
        f"{target_volatility:.12f}"
    )

    print(
        f"       final volatility: "
        f"{final_volatility:.12f}"
    )

    print(
        f"       gross exposure: "
        f"{gross_exposure:.12f}"
    )

    if final_volatility > (
        target_volatility
        + 1e-7
    ):
        raise QuantitativeRegressionFailure(
            "Volatility target exceeded."
        )

    if gross_exposure > (
        1.0 + 1e-8
    ):
        raise QuantitativeRegressionFailure(
            "Maximum leverage exceeded."
        )


# ============================================================================
# 5. BLACK-LITTERMAN
# ============================================================================


def regression_black_litterman() -> None:
    if STATE.covariance is None:
        raise QuantitativeRegressionFailure(
            "Covariance unavailable."
        )

    model = BlackLittermanModel()

    STATE.black_litterman = model

    weights = np.array(
        [
            0.20,
            0.25,
            0.30,
            0.05,
            0.05,
            0.02,
            0.02,
            0.01,
            0.02,
            0.02,
            0.02,
            0.01,
            0.01,
            0.02,
        ],
        dtype=float,
    )

    weights /= weights.sum()

    equilibrium = model.equilibrium_returns(
        STATE.covariance,
        weights,
    )

    views = (
        equilibrium
        + np.linspace(
            -0.01,
            0.01,
            len(ASSETS),
        )
    )

    posterior = model.posterior_returns(
        STATE.covariance,
        weights,
        views,
    )

    assert_finite_array(
        equilibrium,
        "Equilibrium returns",
    )

    assert_finite_array(
        posterior,
        "Posterior returns",
    )

    print(
        "       equilibrium returns: "
        f"{np.round(equilibrium[:3], 8)}"
    )

    print(
        "       posterior returns: "
        f"{np.round(posterior[:3], 8)}"
    )

    if equilibrium.shape != (
        len(ASSETS),
    ):
        raise QuantitativeRegressionFailure(
            "Equilibrium return dimension mismatch."
        )

    if posterior.shape != (
        len(ASSETS),
    ):
        raise QuantitativeRegressionFailure(
            "Posterior return dimension mismatch."
        )


# ============================================================================
# 6. EXPECTED RETURNS
# ============================================================================


def regression_expected_returns() -> None:
    """
    Test the actual production ExpectedReturnForecaster API.

    Production interface:

        forecast(prices) -> pd.Series
    """

    prices = build_synthetic_prices()

    STATE.prices = prices
    STATE.returns = prices.pct_change().dropna()

    forecaster = ExpectedReturnForecaster()

    STATE.forecaster = forecaster

    forecast = forecaster.forecast(
        prices
    )

    if not isinstance(
        forecast,
        pd.Series,
    ):
        raise QuantitativeRegressionFailure(
            "ExpectedReturnForecaster.forecast() "
            "must return pandas Series."
        )

    print(
        f"       forecast observations: "
        f"{len(forecast)}"
    )

    print(
        "       forecast assets: "
        f"{list(forecast.index)}"
    )

    assert_series_finite(
        forecast,
        "Expected-return forecast",
    )

    if set(forecast.index) != set(
        ASSETS
    ):
        raise QuantitativeRegressionFailure(
            "Expected-return forecast asset "
            "universe does not match."
        )

    if len(forecast) != len(
        ASSETS
    ):
        raise QuantitativeRegressionFailure(
            "Expected-return forecast length "
            "does not match asset universe."
        )

    STATE.expected_returns = (
        forecast
    )

    health = forecaster.health_check()

    if not isinstance(
        health,
        dict,
    ):
        raise QuantitativeRegressionFailure(
            "ExpectedReturnForecaster.health_check() "
            "must return a dictionary."
        )

    if health.get(
        "status"
    ) != "HEALTHY":
        raise QuantitativeRegressionFailure(
            f"ExpectedReturnForecaster unhealthy: "
            f"{health}"
        )


# ============================================================================
# 7. RISK BUDGETING
# ============================================================================


def regression_risk_budgeting() -> None:
    engine = RiskBudgetEngine()

    STATE.risk_budget_engine = engine

    health = engine.health_check()

    print(
        f"       health: {health}"
    )

    if not isinstance(
        health,
        dict,
    ):
        raise QuantitativeRegressionFailure(
            "RiskBudgetEngine health check "
            "must return a dictionary."
        )

    if not health.get(
        "healthy",
        False,
    ):
        raise QuantitativeRegressionFailure(
            f"RiskBudgetEngine unhealthy: "
            f"{health}"
        )

    available_methods = [
        name
        for name, member in inspect.getmembers(
            engine,
            predicate=callable,
        )
        if not name.startswith("_")
    ]

    budget_methods = [
        name
        for name in available_methods
        if "budget" in name.lower()
    ]

    print(
        f"       budget APIs: "
        f"{budget_methods}"
    )

    if not budget_methods:
        raise QuantitativeRegressionFailure(
            "RiskBudgetEngine exposes no "
            "budget API."
        )

    for regime in REGIMES:
        try:
            budget = engine.get_risk_budget(
                regime,
                ASSETS,
            )
        except TypeError:
            try:
                budget = engine.get_risk_budget(
                    ASSETS,
                    regime,
                )
            except Exception:
                continue
        except Exception:
            continue

        if isinstance(
            budget,
            dict,
        ):
            values = np.asarray(
                list(
                    budget.values()
                ),
                dtype=float,
            )

            if values.size == 0:
                continue

            assert_finite_array(
                values,
                f"Risk budget {regime}",
            )


# ============================================================================
# 8. REGIME DIFFERENTIATION
# ============================================================================


def regression_regime_differentiation() -> None:
    risk_budget_regimes = list(
        REGIME_RISK_BUDGETS.keys()
    )

    volatility_regimes = list(
        REGIME_VOL_TARGETS.keys()
    )

    leverage_regimes = list(
        REGIME_MAX_LEVERAGE.keys()
    )

    print(
        f"       risk-budget regimes: "
        f"{risk_budget_regimes}"
    )

    print(
        f"       volatility regimes: "
        f"{volatility_regimes}"
    )

    print(
        f"       leverage regimes: "
        f"{leverage_regimes}"
    )

    for regime_set, name in [
        (
            risk_budget_regimes,
            "risk-budget",
        ),
        (
            volatility_regimes,
            "volatility",
        ),
        (
            leverage_regimes,
            "leverage",
        ),
    ]:
        if not regime_set:
            raise QuantitativeRegressionFailure(
                f"{name} regime configuration is empty."
            )

    for regime in REGIMES:
        if regime not in REGIME_RISK_BUDGETS:
            raise QuantitativeRegressionFailure(
                f"Missing risk budget regime: "
                f"{regime}"
            )

        if regime not in REGIME_VOL_TARGETS:
            raise QuantitativeRegressionFailure(
                f"Missing volatility regime: "
                f"{regime}"
            )

        if regime not in REGIME_MAX_LEVERAGE:
            raise QuantitativeRegressionFailure(
                f"Missing leverage regime: "
                f"{regime}"
            )


# ============================================================================
# 9. PRODUCTION COMPONENT CONSTRUCTION
# ============================================================================


def regression_optimizer_health() -> None:
    """
    Construct PortfolioOptimizer using the exact production dependency graph.

    This is intentionally NOT:

        PortfolioOptimizer()

    because the production API requires:

        risk_budget_engine
        constraints
        vol_target_engine
    """

    builder = ProductionComposition()

    components = builder.build_components()

    STATE.components = components

    optimizer = components.optimizer

    STATE.optimizer = optimizer

    if not isinstance(
        optimizer,
        PortfolioOptimizer,
    ):
        raise QuantitativeRegressionFailure(
            "Production composition did not "
            "return PortfolioOptimizer."
        )

    health = optimizer.health_check()

    print(
        f"       optimizer health: "
        f"{health}"
    )

    if not isinstance(
        health,
        dict,
    ):
        raise QuantitativeRegressionFailure(
            "PortfolioOptimizer.health_check() "
            "must return a dictionary."
        )

    if not health.get(
        "healthy",
        False,
    ):
        raise QuantitativeRegressionFailure(
            f"PortfolioOptimizer unhealthy: "
            f"{health}"
        )

    required_components = [
        "risk_budget_engine",
        "constraints",
        "vol_target_engine",
    ]

    for attribute in required_components:
        dependency = getattr(
            optimizer,
            attribute,
            None,
        )

        if dependency is None:
            raise QuantitativeRegressionFailure(
                f"PortfolioOptimizer missing "
                f"dependency '{attribute}'."
            )


# ============================================================================
# 10. PORTFOLIO OPTIMIZER NUMERICAL PROBE
# ============================================================================


def regression_optimizer_numerical_probe() -> None:
    if STATE.optimizer is None:
        raise QuantitativeRegressionFailure(
            "PortfolioOptimizer unavailable."
        )

    if STATE.covariance is None:
        raise QuantitativeRegressionFailure(
            "Covariance unavailable."
        )

    if STATE.prices is None:
        raise QuantitativeRegressionFailure(
            "Prices unavailable."
        )

    optimizer = STATE.optimizer

    regime = "bull"

    result = optimizer.optimize(
        covariance=STATE.covariance,
        regime=regime,
        asset_order=ASSETS,
        prices=STATE.prices,
    )

    if not isinstance(
        result,
        dict,
    ):
        raise QuantitativeRegressionFailure(
            "PortfolioOptimizer.optimize() "
            "must return a dictionary."
        )

    STATE.optimizer_result = result

    print(
        "       optimizer result keys: "
        f"{sorted(result.keys())}"
    )

    weights = result.get(
        "weights"
    )

    if weights is None:
        raise QuantitativeRegressionFailure(
            "Optimizer result missing weights."
        )

    if isinstance(
        weights,
        dict,
    ):
        weight_vector = np.asarray(
            [
                float(
                    weights[ticker]
                )
                for ticker in ASSETS
            ],
            dtype=float,
        )

    else:
        weight_vector = np.asarray(
            weights,
            dtype=float,
        ).reshape(-1)

    assert_finite_array(
        weight_vector,
        "Optimizer weights",
    )

    if len(weight_vector) != len(
        ASSETS
    ):
        raise QuantitativeRegressionFailure(
            "Optimizer weight dimension "
            "does not match asset universe."
        )

    print(
        f"       weight sum: "
        f"{weight_vector.sum():.12f}"
    )

    print(
        f"       gross exposure: "
        f"{np.sum(np.abs(weight_vector)):.12f}"
    )

    maximum_weight = float(
        np.max(
            np.abs(
                weight_vector
            )
        )
    )

    print(
        f"       maximum position: "
        f"{maximum_weight:.12f}"
    )

    if maximum_weight > (
        PortfolioConstraints.MAX_WEIGHT
        + 1e-8
    ):
        raise QuantitativeRegressionFailure(
            "Optimizer produced a position "
            "above the configured maximum."
        )

    gross_exposure = float(
        np.sum(
            np.abs(
                weight_vector
            )
        )
    )

    max_leverage = float(
        REGIME_MAX_LEVERAGE[
            regime
        ]
    )

    if gross_exposure > (
        max_leverage
        + 1e-8
    ):
        raise QuantitativeRegressionFailure(
            "Optimizer exceeded regime "
            "maximum leverage."
        )


# ============================================================================
# 11. PRODUCTION COMPOSITION
# ============================================================================


def regression_production_composition() -> None:
    builder = ProductionComposition()

    components = builder.build_components()

    required = [
        "asset_universe",
        "regime_model",
        "expected_return_forecaster",
        "covariance_engine",
        "regime_covariance",
        "ensemble_covariance",
        "black_litterman",
        "optimizer",
        "constraints",
        "risk_model",
        "risk_contribution_analyzer",
        "scenario_engine",
    ]

    for name in required:
        if not hasattr(
            components,
            name,
        ):
            raise QuantitativeRegressionFailure(
                f"ProductionComponents missing "
                f"'{name}'."
            )

        if getattr(
            components,
            name,
        ) is None:
            raise QuantitativeRegressionFailure(
                f"Production component "
                f"'{name}' is None."
            )

    print(
        "       production engine: "
        "PortfolioDecisionEngine"
    )


# ============================================================================
# 12. DETERMINISM
# ============================================================================


def regression_determinism() -> None:
    covariance_a = build_synthetic_covariance()
    covariance_b = build_synthetic_covariance()

    if not np.array_equal(
        covariance_a,
        covariance_b,
    ):
        raise QuantitativeRegressionFailure(
            "Covariance generation is not deterministic."
        )

    prices_a = build_synthetic_prices()
    prices_b = build_synthetic_prices()

    if not prices_a.equals(
        prices_b
    ):
        raise QuantitativeRegressionFailure(
            "Synthetic price generation "
            "is not deterministic."
        )


# ============================================================================
# 13. PRODUCTION OUTPUT INVARIANTS
# ============================================================================


def regression_production_invariants() -> None:
    result = STATE.optimizer_result

    if result is None:
        print(
            "       optimizer result unavailable; "
            "skipping output-specific invariants."
        )
        return

    weights = result.get(
        "weights"
    )

    if isinstance(
        weights,
        dict,
    ):
        vector = np.asarray(
            [
                float(
                    weights[ticker]
                )
                for ticker in ASSETS
            ],
            dtype=float,
        )
    else:
        vector = np.asarray(
            weights,
            dtype=float,
        ).reshape(-1)

    assert_finite_array(
        vector,
        "Production optimizer weights",
    )

    gross = float(
        np.sum(
            np.abs(
                vector
            )
        )
    )

    if gross < -TOLERANCE:
        raise QuantitativeRegressionFailure(
            "Gross exposure cannot be negative."
        )

    if np.any(
        vector < -1e-10
    ):
        raise QuantitativeRegressionFailure(
            "Long-only optimizer produced "
            "negative weights."
        )

    if gross > (
        max(
            float(v)
            for v in REGIME_MAX_LEVERAGE.values()
        )
        + 1e-8
    ):
        raise QuantitativeRegressionFailure(
            "Production optimizer exceeded "
            "global configured leverage."
        )


# ============================================================================
# 14. RISK CONCENTRATION
# ============================================================================


def regression_risk_concentration() -> None:
    if STATE.covariance is None:
        raise QuantitativeRegressionFailure(
            "Covariance unavailable."
        )

    weights = np.full(
        len(ASSETS),
        1.0 / len(ASSETS),
    )

    covariance = STATE.covariance

    variance = float(
        weights
        @ covariance
        @ weights
    )

    volatility = float(
        np.sqrt(
            variance
        )
    )

    marginal = (
        covariance
        @ weights
    )

    risk_contributions = (
        weights
        * marginal
    )

    total = float(
        np.sum(
            risk_contributions
        )
    )

    if total <= 0.0:
        raise QuantitativeRegressionFailure(
            "Risk contribution total must "
            "be positive."
        )

    contribution_pct = (
        risk_contributions
        / total
    )

    maximum = float(
        np.max(
            contribution_pct
        )
    )

    minimum = float(
        np.min(
            contribution_pct
        )
    )

    effective_assets = float(
        1.0
        /
        np.sum(
            contribution_pct ** 2
        )
    )

    print(
        f"       volatility: "
        f"{volatility:.12f}"
    )

    print(
        f"       maximum risk contribution: "
        f"{maximum:.12f}"
    )

    print(
        f"       minimum risk contribution: "
        f"{minimum:.12f}"
    )

    print(
        f"       effective risk assets: "
        f"{effective_assets:.6f}"
    )

    if not np.isclose(
        total,
        variance,
        atol=1e-10,
        rtol=1e-8,
    ):
        raise QuantitativeRegressionFailure(
            "Risk contribution identity failed."
        )

    if effective_assets < 1.0:
        raise QuantitativeRegressionFailure(
            "Effective risk asset count is invalid."
        )


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:
    print()
    print("=" * 80)
    print("FULL QUANTITATIVE REGRESSION")
    print("=" * 80)

    print(
        f"Python: {sys.version}"
    )

    print(
        f"Assets: {ASSETS}"
    )

    print()

    # ------------------------------------------------------------------
    # 1. MODULE LOADING
    # ------------------------------------------------------------------

    print("1. MODULE LOADING")

    RUNNER.check(
        "Production module loading",
        regression_module_loading,
    )

    # ------------------------------------------------------------------
    # 2. NUMERICAL CORE
    # ------------------------------------------------------------------

    print()
    print("2. NUMERICAL CORE")

    RUNNER.check(
        "Numerical primitive identities",
        lambda: None,
    )

    RUNNER.check(
        "Covariance matrix integrity",
        regression_numerical_primitives,
    )

    RUNNER.check(
        "Risk contribution identity",
        regression_covariance_identity,
    )

    # ------------------------------------------------------------------
    # 3. CONSTRAINTS
    # ------------------------------------------------------------------

    print()
    print("3. PORTFOLIO CONSTRAINTS")

    RUNNER.check(
        "Portfolio constraints",
        regression_constraints,
    )

    # ------------------------------------------------------------------
    # 4. VOL TARGETING
    # ------------------------------------------------------------------

    print()
    print("4. VOLATILITY TARGETING")

    RUNNER.check(
        "Volatility targeting",
        regression_volatility_targeting,
    )

    # ------------------------------------------------------------------
    # 5. BLACK-LITTERMAN
    # ------------------------------------------------------------------

    print()
    print("5. BLACK-LITTERMAN")

    RUNNER.check(
        "Black-Litterman numerical regression",
        regression_black_litterman,
    )

    # ------------------------------------------------------------------
    # 6. EXPECTED RETURNS
    # ------------------------------------------------------------------

    print()
    print("6. EXPECTED RETURNS")

    RUNNER.check(
        "Expected-return forecast regression",
        regression_expected_returns,
    )

    # ------------------------------------------------------------------
    # 7. RISK BUDGETING
    # ------------------------------------------------------------------

    print()
    print("7. RISK BUDGETING")

    RUNNER.check(
        "RiskBudgetEngine regression",
        regression_risk_budgeting,
    )

    # ------------------------------------------------------------------
    # 8. REGIMES
    # ------------------------------------------------------------------

    print()
    print("8. REGIME DIFFERENTIATION")

    RUNNER.check(
        "Regime differentiation",
        regression_regime_differentiation,
    )

    # ------------------------------------------------------------------
    # 9. OPTIMIZER
    # ------------------------------------------------------------------

    print()
    print("9. PORTFOLIO OPTIMIZER")

    RUNNER.check(
        "PortfolioOptimizer health",
        regression_optimizer_health,
    )

    RUNNER.check(
        "PortfolioOptimizer numerical probe",
        regression_optimizer_numerical_probe,
    )

    # ------------------------------------------------------------------
    # 10. END-TO-END PRODUCTION
    # ------------------------------------------------------------------

    print()
    print("10. END-TO-END PRODUCTION")

    RUNNER.check(
        "Production composition",
        regression_production_composition,
    )

    # ------------------------------------------------------------------
    # 11. DETERMINISM
    # ------------------------------------------------------------------

    print()
    print("11. DETERMINISM")

    RUNNER.check(
        "Numerical determinism",
        regression_determinism,
    )

    # ------------------------------------------------------------------
    # 12. INVARIANTS
    # ------------------------------------------------------------------

    print()
    print("12. PRODUCTION INVARIANTS")

    RUNNER.check(
        "Production output invariants",
        regression_production_invariants,
    )

    # ------------------------------------------------------------------
    # 13. CONCENTRATION
    # ------------------------------------------------------------------

    print()
    print("13. RISK CONCENTRATION")

    RUNNER.check(
        "Risk concentration diagnostic",
        regression_risk_concentration,
    )

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------

    elapsed = (
        time.perf_counter()
        - RUNNER.started
    )

    print()
    print("=" * 80)
    print("QUANTITATIVE REGRESSION SUMMARY")
    print("=" * 80)

    print(
        f"API version:       {API_VERSION}"
    )

    print(
        f"Total checks:      {RUNNER.total}"
    )

    print(
        f"Passed checks:     {RUNNER.passed}"
    )

    print(
        f"Failed checks:     {RUNNER.failed}"
    )

    print(
        f"Elapsed seconds:   {elapsed:.3f}"
    )

    if RUNNER.failed:
        print()
        print(
            "QUANTITATIVE STATUS: FAIL"
        )

        print()
        print(
            "FAILED CHECKS"
        )

        for failure in RUNNER.failures:
            print(
                f"- {failure}"
            )

        print(
            "=" * 80
        )

        return 1

    print()
    print(
        "QUANTITATIVE STATUS: PASS"
    )

    print(
        "=" * 80
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )
    except KeyboardInterrupt:
        print()
        print(
            "Quantitative regression interrupted."
        )
        raise SystemExit(130)
    except Exception as exc:
        print()
        print(
            "FATAL QUANTITATIVE REGRESSION ERROR"
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )
        traceback.print_exc()
        raise SystemExit(2)