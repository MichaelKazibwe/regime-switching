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

    @staticmethod
    def build_portfolio() -> dict[str, float]:
        """
        Return deterministic portfolio input.

        The values intentionally remain simple so that regression
        failures can be diagnosed without ambiguity.
        """

        return {
            "SPY": 0.50,
            "TLT": 0.30,
            "GLD": 0.20,
        }

    # ------------------------------------------------------------------
    # 5.2 RETURNS
    # ------------------------------------------------------------------

    @staticmethod
    def build_returns() -> Any:
        """
        Construct deterministic return observations.

        The resulting object intentionally exposes a pandas-like
        DataFrame interface required by the production forecasting
        and covariance stack.
        """

        try:

            import pandas as pd

        except ImportError as exc:

            raise ProductionDecisionExecutionError(
                (
                    "pandas is required for the Phase IV-B.3 "
                    "production regression dataset."
                )
            ) from exc

        values = np.array(
            [
                [0.010, 0.005, 0.003],
                [0.012, 0.004, 0.006],
                [-0.008, 0.009, 0.002],
                [0.007, -0.003, 0.005],
                [0.011, 0.006, 0.004],
                [-0.004, 0.008, 0.003],
                [0.009, 0.002, 0.007],
                [0.006, -0.002, 0.004],
                [0.013, 0.005, 0.006],
                [-0.006, 0.010, 0.002],
                [0.008, 0.004, 0.005],
                [0.010, 0.003, 0.004],
            ],
            dtype=float,
        )

        index = pd.date_range(
            "2024-01-01",
            periods=len(values),
            freq="D",
        )

        return pd.DataFrame(
            values,
            index=index,
            columns=[
                "SPY",
                "TLT",
                "GLD",
            ],
        )

    # ------------------------------------------------------------------
    # 5.3 REGIMES
    # ------------------------------------------------------------------

    @staticmethod
    def build_regimes() -> list[str]:
        """
        Construct deterministic regime history.
        """

        return [
            "EXPANSION",
            "EXPANSION",
            "EXPANSION",
            "EXPANSION",
            "EXPANSION",
            "EXPANSION",
            "EXPANSION",
            "EXPANSION",
            "EXPANSION",
            "EXPANSION",
            "EXPANSION",
            "EXPANSION",
        ]

    # ------------------------------------------------------------------
    # 5.4 MACRO DATA
    # ------------------------------------------------------------------

    @staticmethod
    def build_macro_data() -> dict[str, float]:
        """
        Construct deterministic macroeconomic input.
        """

        return {
            "growth": 2.0,
            "inflation": 2.0,
        }

    # ------------------------------------------------------------------
    # 5.5 SCENARIOS
    # ------------------------------------------------------------------

    @staticmethod
    def build_scenarios() -> list[str]:
        """
        Construct deterministic scenario set.
        """

        return [
            "BASE",
            "RECESSION",
        ]

    # ==================================================================
    # SECTION 6
    # EXECUTION
    # ==================================================================

    def execute(
        self,
    ) -> ProductionDecisionExecutionResult:
        """
        Execute the deterministic production decision pipeline.
        """

        self.execution_count += 1

        try:

            portfolio = (
                self.build_portfolio()
            )

            returns = (
                self.build_returns()
            )

            regimes = (
                self.build_regimes()
            )

            macro_data = (
                self.build_macro_data()
            )

            scenarios = (
                self.build_scenarios()
            )

            result = (
                self.integration.run(
                    portfolio=portfolio,
                    returns=returns,
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

        if result.success:

            self.success_count += 1

        # --------------------------------------------------------------
        # FINAL RESULT
        # --------------------------------------------------------------

        execution_result = (
            ProductionDecisionExecutionResult(
                success=bool(
                    result.success
                ),
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
                    decision.diagnostics
                ),
            )
        )

        self.last_result = (
            execution_result
        )

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

            if not np.isclose(
                weight_sum,
                1.0,
                atol=1e-6,
            ):

                raise ProductionDecisionExecutionError(
                    (
                        "Approved portfolio weights do not "
                        f"sum to one. Got {weight_sum}."
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
        portfolio
        == {
            "SPY": 0.50,
            "TLT": 0.30,
            "GLD": 0.20,
        }
    )

    regimes = (
        ProductionDecisionExecution
        .build_regimes()
    )

    assert (
        len(regimes)
        == 12
    )

    macro_data = (
        ProductionDecisionExecution
        .build_macro_data()
    )

    assert (
        macro_data["growth"]
        == 2.0
    )

    assert (
        macro_data["inflation"]
        == 2.0
    )


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