# ======================================================================
# PRODUCTION DECISION EXECUTION
# PHASE IV-B.3

# ======================================================================
"""
Production decision execution and regression boundary.
Phase IV-B.3 validates that the real production dependency graph
assembled by ProductionComposition and exposed through
ProductionIntegration can execute an end-to-end portfolio decision.
Design principles
-----------------
1. Real production components only.
2. No test doubles.
3. Deterministic regression data.
4. No duplicated portfolio mathematics.
5. PortfolioDecisionEngine remains the decision authority.
6. ProductionIntegration remains the integration boundary.
7. Failed and rejected decisions must not be silently treated as
   successful execution.
8. Live trading remains disabled.
"""

# ======================================================================

# SECTION 1
# IMPORTS

# ======================================================================
# ----------------------------------------------------------------------
# 1.1 STANDARD LIBRARY
# ----------------------------------------------------------------------
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
# ----------------------------------------------------------------------
# 1.2 NUMPY
# ----------------------------------------------------------------------
import numpy as np
import pandas as pd
from assetuniverse import AssetUniverse, PRODUCTION_ASSETS
# ----------------------------------------------------------------------
# 1.3 PRODUCTION INTEGRATION
# ----------------------------------------------------------------------
from productionintegration import (
    ProductionIntegration,
    ProductionIntegrationError,
)
# ----------------------------------------------------------------------
# 1.4 DECISION ENGINE
# ----------------------------------------------------------------------
from portfoliodecisionengine import (
    PortfolioDecisionStatus,
)

# ======================================================================

# SECTION 2
# EXCEPTIONS

# ======================================================================

class ProductionDecisionExecutionError(
    RuntimeError
):
    """
    Raised when Phase IV-B.3 cannot execute or validate a production
    portfolio decision.
    """
    pass

# ======================================================================

# SECTION 3
# EXECUTION RESULT

# ======================================================================

@dataclass(
    frozen=True
)

class ProductionDecisionExecutionResult:
    """
    Immutable representation of one production decision execution.
    """
    success: bool
    status: str
    approved: bool
    decision_id: str | None
    regime: str | None
    weights: dict[str, float]
    portfolio_return: float
    portfolio_variance: float
    portfolio_volatility: float
    gross_exposure: float
    net_exposure: float
    number_of_positions: int
    risk_contributions: dict[str, float]
    risk_contribution_pct: dict[str, float]
    scenario_results: dict[str, Any]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    diagnostics: dict[str, Any]
    tickers: tuple[str, ...] = tuple()
    # Retain the authoritative domain decision for end-to-end audit and
    # downstream consumers; summary fields alone are not a decision artifact.
    decision: Any = None

# ======================================================================

# SECTION 4
# PRODUCTION DECISION EXECUTION ENGINE

# ======================================================================

class ProductionDecisionExecution:
    """
    Phase IV-B.3 production decision execution boundary.
    This class creates deterministic production inputs and delegates
    all portfolio decision logic to ProductionIntegration.
    """
    # ------------------------------------------------------------------
    # 4.1 API METADATA
    # ------------------------------------------------------------------
    API_VERSION = (
        "1.0.0"
    )
    PHASE = (
        "IV-B.3"
    )
    LIVE_TRADING_ENABLED = False
    TEST_DOUBLES_ALLOWED = False
    MINIMUM_RETURN_HISTORY = 252
    DETERMINISTIC_HISTORY_LENGTH = 300

    @classmethod

    def production_tickers(cls) -> tuple[str, ...]:
        """Return the canonical ticker order from AssetUniverse.production()."""
        try:
            universe = AssetUniverse.production()
            tickers = tuple(universe.tickers)
        except Exception as exc:
            raise ProductionDecisionExecutionError(
                f"Unable to construct the canonical production universe: {exc}"
            ) from exc
        canonical = tuple(PRODUCTION_ASSETS)
        if not tickers or len(tickers) != len(canonical) or len(set(tickers)) != len(canonical):
            raise ProductionDecisionExecutionError(
                "Paper universe must match the registered qualified unique tickers."
            )
        if set(tickers) != set(canonical):
            raise ProductionDecisionExecutionError(
                "AssetUniverse.production() does not match assetuniverse.PRODUCTION_ASSETS."
            )
        return canonical

    @classmethod

    def production_asset_count(cls) -> int:
        return len(cls.production_tickers())

    # ==================================================================
    # 4.2 CONSTRUCTOR

    # ==================================================================

    def __init__(
        self,
        *,
        integration: (
            ProductionIntegration
            | None
        ) = None,
    ) -> None:
        """
        Initialize the production execution boundary.
        """
        self.integration = (
            integration
            if integration is not None
            else ProductionIntegration()
        )
        self.execution_count = 0
        self.success_count = 0
        self.approved_count = 0
        self.rejected_count = 0
        self.failed_count = 0
        self.last_result = None

    # ==================================================================

    # SECTION 5
    # DETERMINISTIC PRODUCTION INPUTS

    # ==================================================================
    # ------------------------------------------------------------------
    # 5.1 PORTFOLIO
    # ------------------------------------------------------------------

    @classmethod

    def build_portfolio(cls) -> dict[str, float]:
        """Build an equal-weight portfolio over the registry-qualified assets."""
        tickers = cls.production_tickers()
        weight = 1.0 / len(tickers)
        return {ticker: weight for ticker in tickers}
    # ------------------------------------------------------------------
    # 5.2 RETURNS
    # ------------------------------------------------------------------

    @classmethod

    def build_returns(cls) -> pd.DataFrame:
        """Build 300 deterministic daily return observations for all assets."""
        tickers = cls.production_tickers()
        periods = cls.DETERMINISTIC_HISTORY_LENGTH
        rng = np.random.default_rng(42)
        market_factor = rng.normal(0.0004, 0.0080, periods)
        defensive_factor = rng.normal(0.0001, 0.0040, periods)
        commodity_factor = rng.normal(0.0002, 0.0050, periods)
        idiosyncratic = rng.normal(0.0, 0.0025, (periods, len(tickers)))
        # Stable, transparent factor exposures; no external data dependency.
        exposures = {
            "SPY": (1.00, 0.10, 0.00), "QQQ": (1.20, -0.05, 0.00),
            "IWM": (1.15, 0.00, 0.00), "VEA": (0.85, 0.10, 0.00),
            "VWO": (1.00, 0.00, 0.10), "TLT": (-0.10, 1.20, 0.00),
            "IEF": (0.00, 0.80, 0.00), "SHY": (0.00, 0.25, 0.00),
            "LQD": (0.20, 0.45, 0.00), "HYG": (0.65, 0.10, 0.00),
            "GLD": (0.00, 0.10, 0.65), "SLV": (0.20, 0.00, 0.90),
            "DBC": (0.10, 0.00, 1.00), "VNQ": (0.80, 0.20, 0.00),
        }
        values = np.empty((periods, len(tickers)), dtype=float)
        for j, ticker in enumerate(tickers):
            mkt, defensive, commodity = exposures[ticker]
            values[:, j] = (
                mkt * market_factor
                + defensive * defensive_factor
                + commodity * commodity_factor
                + idiosyncratic[:, j]
            )
        index = pd.date_range("2024-01-01", periods=periods, freq="B")
        frame = pd.DataFrame(values, index=index, columns=tickers, dtype=float)
        if frame.shape != (periods, len(tickers)) or not np.isfinite(frame.to_numpy()).all():
            raise ProductionDecisionExecutionError("Deterministic return history is malformed.")
        return frame
    # ------------------------------------------------------------------
    # 5.3 PRICES
    # ------------------------------------------------------------------

    @classmethod

    def build_prices(cls, returns: pd.DataFrame | None = None) -> pd.DataFrame:
        """Build positive synthetic prices aligned exactly to supplied returns."""
        if returns is None:
            returns = cls.build_returns()
        gross_returns = 1.0 + returns
        if (gross_returns <= 0.0).any().any():
            raise ProductionDecisionExecutionError(
                "Synthetic return history contains a return at or below -100%."
            )
        prices = gross_returns.cumprod() * 100.0
        prices = prices.astype(float)
        if not np.isfinite(prices.to_numpy()).all() or (prices <= 0.0).any().any():
            raise ProductionDecisionExecutionError("Deterministic price history is malformed.")
        return prices
    # ------------------------------------------------------------------
    # 5.4 REGIMES
    # ------------------------------------------------------------------

    @classmethod

    def build_regimes(cls) -> list[str]:
        """Build a deterministic regime label for each return observation."""
        return ["EXPANSION"] * cls.DETERMINISTIC_HISTORY_LENGTH
    # ------------------------------------------------------------------
    # 5.5 MACRO DATA
    # ------------------------------------------------------------------

    @classmethod

    def build_macro_data(cls) -> dict[str, Any]:
        """Build valid scalar and historical macro observations."""
        index = pd.date_range("2024-01-01", periods=cls.DETERMINISTIC_HISTORY_LENGTH, freq="B")
        unemployment = np.linspace(4.00, 3.95, cls.DETERMINISTIC_HISTORY_LENGTH, dtype=float)
        return {
            "growth": 2.10,
            "inflation": 2.03,
            "yield_spread": 1.47,
            "unemployment": pd.Series(unemployment, index=index, dtype=float),
        }
    # ------------------------------------------------------------------
    # 5.6 SCENARIOS
    # ------------------------------------------------------------------

    @classmethod

    def build_scenarios(cls) -> dict[str, dict[str, float]]:
        """Return explicit scenario definitions understood by ScenarioEngine.
        Scenario shocks are additive changes to expected-return assumptions,
        not simulated price paths or realized P&L.
        """
        tickers = cls.production_tickers()
        base = {ticker: 0.0 for ticker in tickers}
        recession_shocks = {
            "SPY": -0.08, "QQQ": -0.11, "IWM": -0.12, "VEA": -0.08,
            "VWO": -0.10, "TLT": 0.04, "IEF": 0.025, "SHY": 0.005,
            "LQD": -0.025, "HYG": -0.09, "GLD": 0.035, "SLV": -0.06,
            "DBC": -0.10, "VNQ": -0.08,
        }
        return {"BASE": base, "RECESSION": recession_shocks}

    # ==================================================================

    # SECTION 6
    # EXECUTION

    # ==================================================================

    def execute(
        self,
        *,
        portfolio: dict[str, float] | None = None,
        returns: pd.DataFrame | None = None,
        prices: pd.DataFrame | None = None,
        regimes: Any = None,
        macro_data: dict[str, Any] | None = None,
        scenarios: dict[str, Any] | None = None,
    ) -> ProductionDecisionExecutionResult:
        """
        Execute the production decision pipeline.

        Supplying all five required data inputs (portfolio, returns,
        prices, regimes, and macro_data) executes against caller-provided
        observations.  ``scenarios`` is optional.  With no arguments, the
        deterministic synthetic fixture is retained for local regression
        and demonstration only.  Partial input envelopes fail closed and
        are never silently completed with synthetic observations.
        """
        self.execution_count += 1
        try:
            supplied = {
                "portfolio": portfolio,
                "returns": returns,
                "prices": prices,
                "regimes": regimes,
                "macro_data": macro_data,
            }
            present = {
                name: value is not None
                for name, value in supplied.items()
            }

            if not any(present.values()):
                # Compatibility path for deterministic regression fixtures.
                portfolio = self.build_portfolio()
                returns = self.build_returns()
                prices = self.build_prices(returns)
                regimes = self.build_regimes()
                macro_data = self.build_macro_data()
                scenarios = self.build_scenarios()
                input_mode = "SYNTHETIC_REGRESSION"
            else:
                missing = [
                    name
                    for name, is_present in present.items()
                    if not is_present
                ]
                if missing:
                    raise ProductionDecisionExecutionError(
                        "Production input envelope is incomplete; missing: "
                        + ", ".join(missing)
                    )
                if scenarios is None:
                    scenarios = self.build_scenarios()
                input_mode = "CALLER_SUPPLIED"

            result = (
                self.integration.run(
                    portfolio=portfolio,
                    returns=returns,
                    prices=prices,
                    regimes=regimes,
                    macro_data=macro_data,
                    scenarios=scenarios,
                )
            )
        except (
            ProductionIntegrationError,
            ProductionDecisionExecutionError,
        ) as exc:
            self.failed_count += 1
            execution_result = (
                ProductionDecisionExecutionResult(
                    success=False,
                    status=(
                        PortfolioDecisionStatus.FAILED.value
                    ),
                    approved=False,
                    decision_id=None,
                    regime=None,
                    weights={},
                    portfolio_return=0.0,
                    portfolio_variance=0.0,
                    portfolio_volatility=0.0,
                    gross_exposure=0.0,
                    net_exposure=0.0,
                    number_of_positions=0,
                    risk_contributions={},
                    risk_contribution_pct={},
                    scenario_results={},
                    warnings=tuple(),
                    errors=(
                        str(exc),
                    ),
                    diagnostics={
                        "exception_type": (
                            type(exc).__name__
                        )
                    },
                )
            )
            self.last_result = execution_result
            return execution_result
        decision = (
            result.decision
        )
        if decision is None:
            self.failed_count += 1
            execution_result = (
                ProductionDecisionExecutionResult(
                    success=False,
                    status=(
                        PortfolioDecisionStatus.FAILED.value
                    ),
                    approved=False,
                    decision_id=None,
                    regime=None,
                    weights={},
                    portfolio_return=0.0,
                    portfolio_variance=0.0,
                    portfolio_volatility=0.0,
                    gross_exposure=0.0,
                    net_exposure=0.0,
                    number_of_positions=0,
                    risk_contributions={},
                    risk_contribution_pct={},
                    scenario_results={},
                    warnings=tuple(
                        result.warnings
                    ),
                    errors=tuple(
                        result.errors
                    ),
                    diagnostics=dict(
                        result.diagnostics
                    ),
                )
            )
            self.last_result = execution_result
            return execution_result
        # --------------------------------------------------------------
        # STATUS COUNTERS
        # --------------------------------------------------------------
        if (
            decision.status
            == PortfolioDecisionStatus.APPROVED.value
        ):
            self.approved_count += 1
        elif (
            decision.status
            == PortfolioDecisionStatus.REJECTED.value
        ):
            self.rejected_count += 1
        else:
            self.failed_count += 1
        execution_success = (
            decision.status
            == PortfolioDecisionStatus.APPROVED.value
            and bool(
                decision.approved
            )
            and bool(
                result.success
            )
        )
        # --------------------------------------------------------------
        # FINAL RESULT
        # --------------------------------------------------------------
        execution_result = (
            ProductionDecisionExecutionResult(
                success=execution_success,
                status=decision.status,
                approved=bool(
                    decision.approved
                ),
                decision_id=(
                    decision.decision_id
                ),
                regime=decision.regime,
                weights=dict(
                    decision.weights
                ),
                portfolio_return=float(
                    decision.portfolio_return
                ),
                portfolio_variance=float(
                    decision.portfolio_variance
                ),
                portfolio_volatility=float(
                    decision.portfolio_volatility
                ),
                gross_exposure=float(
                    decision.gross_exposure
                ),
                net_exposure=float(
                    decision.net_exposure
                ),
                number_of_positions=int(
                    decision.number_of_positions
                ),
                risk_contributions=dict(
                    decision.risk_contributions
                ),
                risk_contribution_pct=dict(
                    decision.risk_contribution_pct
                ),
                scenario_results=dict(
                    decision.scenario_results
                ),
                warnings=tuple(
                    decision.warnings
                ),
                errors=tuple(
                    decision.errors
                ),
                diagnostics=dict(
                    decision.diagnostics,
                    input_mode=input_mode,
                ),
                tickers=tuple(getattr(decision, "tickers", ())),
                decision=decision,
            )
        )
        try:
            self.validate_result(execution_result)
        except ProductionDecisionExecutionError as exc:
            # A malformed APPROVED result is not a successful execution.
            # Preserve the upstream decision ID and diagnostics for audit,
            # but downgrade the execution boundary result to FAILED.
            self.failed_count += 1
            diagnostics = dict(execution_result.diagnostics)
            diagnostics["execution_validation_error"] = str(exc)
            execution_result = ProductionDecisionExecutionResult(
                success=False,
                status=PortfolioDecisionStatus.FAILED.value,
                approved=False,
                decision_id=execution_result.decision_id,
                regime=execution_result.regime,
                weights=dict(execution_result.weights),
                portfolio_return=execution_result.portfolio_return,
                portfolio_variance=execution_result.portfolio_variance,
                portfolio_volatility=execution_result.portfolio_volatility,
                gross_exposure=execution_result.gross_exposure,
                net_exposure=execution_result.net_exposure,
                number_of_positions=execution_result.number_of_positions,
                risk_contributions=dict(execution_result.risk_contributions),
                risk_contribution_pct=dict(execution_result.risk_contribution_pct),
                scenario_results=dict(execution_result.scenario_results),
                warnings=tuple(execution_result.warnings),
                errors=tuple(execution_result.errors) + (str(exc),),
                diagnostics=diagnostics,
                tickers=tuple(execution_result.tickers),
                decision=decision,
            )
        if execution_result.success:
            self.success_count += 1
        self.last_result = execution_result
        return execution_result

    # ==================================================================

    # SECTION 7
    # EXECUTION VALIDATION

    # ==================================================================

    @staticmethod

    def validate_result(
        result: ProductionDecisionExecutionResult,
    ) -> None:
        """
        Validate the complete Phase IV-B.3 execution result.
        """
        if result.status == (
            PortfolioDecisionStatus.APPROVED.value
        ):
            if not result.success:
                raise ProductionDecisionExecutionError(
                    (
                        "Execution returned APPROVED but "
                        "success=False."
                    )
                )
            if not result.approved:
                raise ProductionDecisionExecutionError(
                    (
                        "Execution returned APPROVED but "
                        "approved=False."
                    )
                )
            if not result.decision_id:
                raise ProductionDecisionExecutionError(
                    "Approved execution has no decision ID."
                )
            if not result.regime:
                raise ProductionDecisionExecutionError(
                    "Approved execution has no regime."
                )
            if not result.weights:
                raise ProductionDecisionExecutionError(
                    "Approved execution has no weights."
                )
            weight_sum = sum(
                result.weights.values()
            )
            if (
                not np.isfinite(weight_sum)
                or weight_sum <= 0.0
                or weight_sum > 1.0 + 1e-6
            ):
                raise ProductionDecisionExecutionError(
                    (
                        "Approved portfolio exposure must be in (0, 1]. "
                        f"Got total weight {weight_sum}."
                    )
                )
            if not result.risk_contributions:
                raise ProductionDecisionExecutionError(
                    (
                        "Approved execution contains no "
                        "risk contributions."
                    )
                )
            if not result.scenario_results:
                raise ProductionDecisionExecutionError(
                    (
                        "Approved execution contains no "
                        "scenario results."
                    )
                )
        elif result.status == (
            PortfolioDecisionStatus.REJECTED.value
        ):
            if result.approved:
                raise ProductionDecisionExecutionError(
                    (
                        "Rejected execution has approved=True."
                    )
                )
        elif result.status == (
            PortfolioDecisionStatus.FAILED.value
        ):
            if result.approved:
                raise ProductionDecisionExecutionError(
                    (
                        "Failed execution has approved=True."
                    )
                )
            if not result.errors:
                raise ProductionDecisionExecutionError(
                    (
                        "Failed execution contains no "
                        "diagnostic errors."
                    )
                )
        else:
            raise ProductionDecisionExecutionError(
                (
                    "Unknown production decision status: "
                    f"{result.status}"
                )
            )

    # ==================================================================

    # SECTION 8
    # HEALTH CHECK

    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return Phase IV-B.3 health information.
        """
        try:
            integration_health = (
                self.integration.health_check()
            )
        except Exception as exc:
            return {
                "api_version": (
                    self.API_VERSION
                ),
                "phase": (
                    self.PHASE
                ),
                "healthy": False,
                "error": str(
                    exc
                ),
            }
        return {
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
            ),
            "healthy": bool(
                integration_health.get(
                    "healthy",
                    False,
                )
            ),
            "integration_health": (
                integration_health
            ),
        }

    # ==================================================================

    # SECTION 9
    # METADATA

    # ==================================================================

    def metadata(
        self,
    ) -> dict[str, Any]:
        """
        Return Phase IV-B.3 metadata.
        """
        return {
            "module": (
                "productiondecisionexecution"
            ),
            "component": (
                "ProductionDecisionExecution"
            ),
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
            ),
            "production_only": True,
            "test_doubles_allowed": (
                self.TEST_DOUBLES_ALLOWED
            ),
            "live_trading_enabled": (
                self.LIVE_TRADING_ENABLED
            ),
            "deterministic_regression_data": True,
            "decision_engine_is_authoritative": True,
            "canonical_production_universe": True,
            "production_asset_count": self.production_asset_count(),
            "production_assets": list(self.production_tickers()),
            "minimum_return_history": self.MINIMUM_RETURN_HISTORY,
            "deterministic_history_length": self.DETERMINISTIC_HISTORY_LENGTH,
        }

    # ==================================================================

    # SECTION 10
    # SUMMARY

    # ==================================================================

    def summary(
        self,
    ) -> dict[str, Any]:
        """
        Return Phase IV-B.3 execution statistics.
        """
        last = (
            self.last_result
        )
        return {
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
            ),
            "execution_count": (
                self.execution_count
            ),
            "success_count": (
                self.success_count
            ),
            "approved_count": (
                self.approved_count
            ),
            "rejected_count": (
                self.rejected_count
            ),
            "failed_count": (
                self.failed_count
            ),
            "last_status": (
                None
                if last is None
                else last.status
            ),
            "last_approved": (
                None
                if last is None
                else last.approved
            ),
        }

# ======================================================================

# SECTION 11
# CONVENIENCE FACTORY

# ======================================================================

def build_production_decision_execution(
) -> ProductionDecisionExecution:
    """
    Construct the Phase IV-B.3 production execution boundary.
    """
    return ProductionDecisionExecution()

# ======================================================================

# SECTION 12
# REGRESSION TESTS

# ======================================================================

def test_production_decision_execution_metadata() -> None:
    """
    Verify Phase IV-B.3 metadata.
    """
    execution = (
        ProductionDecisionExecution()
    )
    metadata = (
        execution.metadata()
    )
    assert (
        metadata["api_version"]
        == "1.0.0"
    )
    assert (
        metadata["phase"]
        == "IV-B.3"
    )
    assert (
        metadata["production_only"]
        is True
    )
    assert (
        metadata["test_doubles_allowed"]
        is False
    )
    assert (
        metadata["live_trading_enabled"]
        is False
    )
    assert (
        metadata["deterministic_regression_data"]
        is True
    )

def test_production_decision_execution_health() -> None:
    """
    Verify the Phase IV-B.3 health interface.
    """
    execution = (
        ProductionDecisionExecution()
    )
    result = (
        execution.health_check()
    )
    assert isinstance(
        result,
        dict,
    )
    assert (
        result["api_version"]
        == "1.0.0"
    )
    assert (
        result["phase"]
        == "IV-B.3"
    )
    assert (
        "healthy"
        in result
    )

def test_production_decision_execution_data() -> None:
    """
    Verify deterministic regression input construction.
    """
    portfolio = (
        ProductionDecisionExecution
        .build_portfolio()
    )
    assert (
        tuple(portfolio)
        == ProductionDecisionExecution.production_tickers()
    )
    regimes = (
        ProductionDecisionExecution
        .build_regimes()
    )
    assert (
        len(regimes)
        == ProductionDecisionExecution.DETERMINISTIC_HISTORY_LENGTH
    )
    macro_data = (
        ProductionDecisionExecution
        .build_macro_data()
    )
    assert (
        macro_data["growth"]
        == 2.10
    )
    assert macro_data["inflation"] == 2.03
    assert "unemployment" in macro_data
    assert "yield_spread" in macro_data
    returns = ProductionDecisionExecution.build_returns()
    prices = ProductionDecisionExecution.build_prices()
    assert returns.shape == (300, len(PRODUCTION_ASSETS))
    assert prices.shape == returns.shape
    assert tuple(returns.columns) == ProductionDecisionExecution.production_tickers()
    assert np.isfinite(returns.to_numpy()).all()
    assert np.isfinite(prices.to_numpy()).all()
    scenarios = ProductionDecisionExecution.build_scenarios()
    assert set(scenarios) == {"BASE", "RECESSION"}
    assert all(set(shocks) == set(ProductionDecisionExecution.production_tickers()) for shocks in scenarios.values())

def test_production_decision_execution_allows_risk_reduced_exposure() -> None:
    """Risk-governor reductions may leave part of the portfolio in cash."""
    tickers = ProductionDecisionExecution.production_tickers()
    weights = {ticker: 0.5 / len(tickers) for ticker in tickers}
    result = ProductionDecisionExecutionResult(
        success=True,
        status=PortfolioDecisionStatus.APPROVED.value,
        approved=True,
        decision_id="PDEC-TEST-1",
        regime="EXPANSION",
        weights=weights,
        portfolio_return=0.01,
        portfolio_variance=0.001,
        portfolio_volatility=float(np.sqrt(0.001)),
        gross_exposure=0.5,
        net_exposure=0.5,
        number_of_positions=len(tickers),
        risk_contributions={ticker: 0.0 for ticker in tickers},
        risk_contribution_pct={ticker: 0.0 for ticker in tickers},
        scenario_results={"BASE": {"portfolio_return": 0.01}},
        warnings=tuple(),
        errors=tuple(),
        diagnostics={"risk_governance_action": "REDUCE"},
        tickers=tickers,
    )
    ProductionDecisionExecution.validate_result(result)


def test_production_decision_execution_summary() -> None:
    """
    Verify initial execution statistics.
    """
    execution = (
        ProductionDecisionExecution()
    )
    summary = (
        execution.summary()
    )
    assert (
        summary["execution_count"]
        == 0
    )
    assert (
        summary["success_count"]
        == 0
    )
    assert (
        summary["approved_count"]
        == 0
    )
    assert (
        summary["rejected_count"]
        == 0
    )
    assert (
        summary["failed_count"]
        == 0
    )

# ======================================================================

# SECTION 13
# REGRESSION ENTRY POINT

# ======================================================================

def run_regression_tests() -> None:
    """
    Run Phase IV-B.3 structural regression tests.
    """
    test_production_decision_execution_metadata()
    test_production_decision_execution_health()
    test_production_decision_execution_data()
    test_production_decision_execution_allows_risk_reduced_exposure()
    test_production_decision_execution_summary()
    print(
        "ProductionDecisionExecution Phase IV-B.3 "
        "structural tests passed."
    )

# ======================================================================

# SECTION 14
# MODULE ENTRY POINT

# ======================================================================
if __name__ == "__main__":
    print(
        "============================================================"
    )
    print(
        "PHASE IV-B.3 PRODUCTION DECISION EXECUTION"
    )
    print(
        "============================================================"
    )
    execution = (
        ProductionDecisionExecution()
    )
    print()
    print(
        "METADATA:"
    )
    print(
        execution.metadata()
    )
    print()
    print(
        "HEALTH CHECK:"
    )
    health = (
        execution.health_check()
    )
    print(
        health
    )
    print()
    if health.get(
        "healthy",
        False,
    ):
        print(
            "STATUS: HEALTHY"
        )
    else:
        print(
            "STATUS: UNHEALTHY"
        )
        print(
            "ERROR:",
            health.get(
                "error",
                "Unknown production execution error.",
            ),
        )
    print()
    run_regression_tests()
