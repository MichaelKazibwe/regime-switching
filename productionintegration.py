# ======================================================================
# PRODUCTION INTEGRATION
# PHASE IV-B.2
# ======================================================================

"""
Production integration boundary for the institutional portfolio stack.

Phase IV-B.2 proves that the production dependency graph assembled by
ProductionComposition can execute an end-to-end portfolio decision.

Design principles
-----------------
1. ProductionComposition owns dependency construction.
2. ProductionIntegration owns integration validation.
3. PortfolioDecisionEngine owns decision orchestration.
4. PortfolioOptimizer owns portfolio optimization.
5. RiskBudgetEngine owns risk budgeting.
6. No optimization logic is duplicated here.
7. No trading or broker execution occurs in this phase.
8. Test doubles are not permitted at the production boundary.
9. Failures must remain explicit and auditable.
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
import numpy as np

# ----------------------------------------------------------------------
# 1.2 PRODUCTION COMPOSITION
# ----------------------------------------------------------------------

from productioncomposition import (
    ProductionComposition,
    ProductionCompositionError,
)


# ----------------------------------------------------------------------
# 1.3 DECISION ENGINE
# ----------------------------------------------------------------------

from portfoliodecisionengine import (
    PortfolioDecision,
    PortfolioDecisionStatus,
)


# ======================================================================
# SECTION 2
# EXCEPTIONS
# ======================================================================


class ProductionIntegrationError(
    RuntimeError
):
    """
    Raised when the Phase IV-B.2 production integration boundary
    cannot safely execute a portfolio decision.
    """

    pass


# ======================================================================
# SECTION 3
# INTEGRATION RESULT
# ======================================================================


@dataclass(
    frozen=True
)
class ProductionIntegrationResult:
    """
    Immutable result returned by the Phase IV-B.2 integration layer.
    """

    success: bool

    status: str

    approved: bool

    decision: PortfolioDecision | None

    diagnostics: dict[str, Any]

    errors: tuple[str, ...]

    warnings: tuple[str, ...]


# ======================================================================
# SECTION 4
# PRODUCTION INTEGRATION ENGINE
# ======================================================================


class ProductionIntegration:
    """
    Production integration boundary for PortfolioDecisionEngine.

    This class does not implement portfolio mathematics.

    It validates the production dependency graph, validates production
    inputs, invokes PortfolioDecisionEngine, and validates the resulting
    decision.
    """

    # ------------------------------------------------------------------
    # 4.1 API METADATA
    # ------------------------------------------------------------------

    API_VERSION = (
        "1.0.0"
    )

    PHASE = (
        "IV-B.2"
    )

    # ------------------------------------------------------------------
    # 4.2 REQUIRED ENGINE COMPONENTS
    # ------------------------------------------------------------------

    REQUIRED_COMPONENTS = (
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
    )

    # ==================================================================
    # 4.3 CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        *,
        composition: (
            ProductionComposition
            | None
        ) = None,
    ) -> None:
        """
        Initialize the production integration boundary.

        Parameters
        ----------
        composition:
            Optional ProductionComposition instance.

            If omitted, a real production composition is constructed.
        """

        self.composition = (
            composition
            if composition is not None
            else ProductionComposition()
        )

        self.engine = None

        self.last_result = None

        self.execution_count = 0

        self.success_count = 0

        self.failure_count = 0

    # ==================================================================
    # SECTION 5
    # ENGINE CONSTRUCTION
    # ==================================================================

    # ------------------------------------------------------------------
    # 5.1 BUILD ENGINE
    # ------------------------------------------------------------------

    def _build_engine(
        self,
    ) -> Any:
        """
        Construct the production decision engine.
        """

        if self.engine is not None:
            return self.engine

        try:

            engine = (
                self.composition.build_engine()
            )

        except ProductionCompositionError as exc:

            raise ProductionIntegrationError(
                (
                    "Unable to construct the Phase IV-B.2 "
                    "production decision engine: "
                    f"{exc}"
                )
            ) from exc

        if engine is None:

            raise ProductionIntegrationError(
                "ProductionComposition returned None."
            )

        self.engine = engine

        return engine

    # ==================================================================
    # SECTION 6
    # DEPENDENCY VALIDATION
    # ==================================================================

    # ------------------------------------------------------------------
    # 6.1 COMPONENT EXISTENCE
    # ------------------------------------------------------------------

    def _validate_dependencies(
        self,
        engine: Any,
    ) -> None:
        """
        Validate the complete production dependency graph.
        """

        missing: list[str] = []

        for name in (
            self.REQUIRED_COMPONENTS
        ):

            component = getattr(
                engine,
                name,
                None,
            )

            if component is None:

                missing.append(
                    name
                )

        if missing:

            raise ProductionIntegrationError(
                (
                    "Production dependency validation failed. "
                    "Missing components: "
                    + ", ".join(
                        missing
                    )
                )
            )

        # --------------------------------------------------------------
        # OPTIMIZER
        # --------------------------------------------------------------

        optimizer = getattr(
            engine,
            "optimizer",
            None,
        )

        if optimizer is None:

            raise ProductionIntegrationError(
                "PortfolioOptimizer is unavailable."
            )

        # --------------------------------------------------------------
        # RISK BUDGET ENGINE
        # --------------------------------------------------------------

        risk_budget_engine = getattr(
            optimizer,
            "risk_budget_engine",
            None,
        )

        if risk_budget_engine is None:

            raise ProductionIntegrationError(
                (
                    "PortfolioOptimizer does not contain a "
                    "production risk_budget_engine."
                )
            )

        # --------------------------------------------------------------
        # OPTIMIZER CONSTRAINTS
        # --------------------------------------------------------------

        if getattr(
            optimizer,
            "constraints",
            None,
        ) is None:

            raise ProductionIntegrationError(
                (
                    "PortfolioOptimizer does not contain "
                    "production constraints."
                )
            )

    # ==================================================================
    # SECTION 7
    # INPUT VALIDATION
    # ==================================================================

    # ------------------------------------------------------------------
    # 7.1 PORTFOLIO
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_portfolio(
        portfolio: Any,
    ) -> None:
        """
        Validate the portfolio input.
        """

        if portfolio is None:

            raise ProductionIntegrationError(
                "Portfolio input cannot be None."
            )

        if not isinstance(
            portfolio,
            dict,
        ):

            raise ProductionIntegrationError(
                (
                    "Portfolio input must be a "
                    "dictionary of ticker weights."
                )
            )

        if not portfolio:

            raise ProductionIntegrationError(
                "Portfolio input cannot be empty."
            )

        for ticker, weight in (
            portfolio.items()
        ):

            if not isinstance(
                ticker,
                str,
            ):

                raise ProductionIntegrationError(
                    "Portfolio ticker names must be strings."
                )

            try:

                numeric_weight = float(
                    weight
                )

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise ProductionIntegrationError(
                    (
                        f"Invalid portfolio weight for "
                        f"'{ticker}': {weight}"
                    )
                ) from exc

            if not (
                numeric_weight
                == numeric_weight
            ):

                raise ProductionIntegrationError(
                    (
                        f"Portfolio weight for "
                        f"'{ticker}' is NaN."
                    )
                )

    # ------------------------------------------------------------------
    # 7.2 RETURNS
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_returns(
        returns: Any,
    ) -> None:
        """
        Validate the returns input.
        """

        if returns is None:

            raise ProductionIntegrationError(
                "Returns input cannot be None."
            )

        if not hasattr(
            returns,
            "columns",
        ):

            raise ProductionIntegrationError(
                (
                    "Returns input must expose "
                    "a columns attribute."
                )
            )

        if len(
            returns.columns
        ) == 0:

            raise ProductionIntegrationError(
                "Returns input contains no assets."
            )

    # ------------------------------------------------------------------
    # 7.3 REGIMES
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_regimes(
        regimes: Any,
    ) -> None:
        """
        Validate regime information.
        """

        if regimes is None:

            raise ProductionIntegrationError(
                "Regime information cannot be None."
            )

        if not regimes:

            raise ProductionIntegrationError(
                "Regime information cannot be empty."
            )

    # ------------------------------------------------------------------
    # 7.4 MACRO DATA
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_macro_data(
        macro_data: Any,
    ) -> None:
        """
        Validate macroeconomic input required by MacroRegimeModel.

        Required fields
        ---------------
        unemployment:
            Historical unemployment series.

        yield_spread:
            Current yield-curve spread.

        inflation:
            Current inflation measure.
        """

        if macro_data is None:

            raise ProductionIntegrationError(
                "Macro data cannot be None."
            )

        if not isinstance(
            macro_data,
            dict,
        ):

            raise ProductionIntegrationError(
                "Macro data must be a dictionary."
            )

        required = (
            "unemployment",
            "yield_spread",
            "inflation",
        )

        missing = [
            key
            for key in required
            if key not in macro_data
        ]

        if missing:

            raise ProductionIntegrationError(
                "Macro data is missing required fields: "
                + ", ".join(missing)
                + "."
            )

        unemployment = (
            macro_data["unemployment"]
        )

        if unemployment is None:

            raise ProductionIntegrationError(
                "Macro data 'unemployment' cannot be None."
            )

        try:

            if len(unemployment) == 0:

                raise ProductionIntegrationError(
                    "Macro data 'unemployment' cannot be empty."
                )

        except TypeError as exc:

            raise ProductionIntegrationError(
                "Macro data 'unemployment' must be a "
                "non-empty historical series."
            ) from exc

        try:

            yield_spread = float(
                macro_data["yield_spread"]
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise ProductionIntegrationError(
                "Macro data 'yield_spread' must be numeric."
            ) from exc

        if not np.isfinite(
            yield_spread
        ):

            raise ProductionIntegrationError(
                "Macro data 'yield_spread' must be finite."
            )

        try:

            inflation = float(
                macro_data["inflation"]
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise ProductionIntegrationError(
                "Macro data 'inflation' must be numeric."
            ) from exc

        if not np.isfinite(
            inflation
        ):

            raise ProductionIntegrationError(
                "Macro data 'inflation' must be finite."
            )

    # ==================================================================
    # SECTION 8
    # DECISION VALIDATION
    # ==================================================================

    # ------------------------------------------------------------------
    # 8.1 BASIC RESULT VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_decision(
        decision: PortfolioDecision,
    ) -> None:
        """
        Validate a PortfolioDecision returned by the production engine.
        """

        if decision is None:

            raise ProductionIntegrationError(
                "PortfolioDecisionEngine returned None."
            )

        if not isinstance(
            decision,
            PortfolioDecision,
        ):

            raise ProductionIntegrationError(
                (
                    "PortfolioDecisionEngine returned an "
                    f"unexpected object type: "
                    f"{type(decision).__name__}"
                )
            )

        if not decision.decision_id:

            raise ProductionIntegrationError(
                "Decision does not contain a decision_id."
            )

        # --------------------------------------------------------------
        # APPROVED DECISIONS
        # --------------------------------------------------------------

        if (
            decision.status
            == PortfolioDecisionStatus.APPROVED.value
        ):

            if not decision.approved:

                raise ProductionIntegrationError(
                    (
                        "Decision status is APPROVED but "
                        "approved=False."
                    )
                )

            if decision.regime is None:

                raise ProductionIntegrationError(
                    "Approved decision has no regime."
                )

            if not decision.tickers:

                raise ProductionIntegrationError(
                    "Approved decision contains no tickers."
                )

            if not decision.weights:

                raise ProductionIntegrationError(
                    "Approved decision contains no weights."
                )

            weight_total = sum(
                float(value)
                for value in decision.weights.values()
            )

            if abs(
                weight_total - 1.0
            ) > 1e-6:

                raise ProductionIntegrationError(
                    (
                        "Approved decision weights do not "
                        f"sum to one. Got {weight_total}."
                    )
                )

        # --------------------------------------------------------------
        # REJECTED DECISIONS
        # --------------------------------------------------------------

        elif (
            decision.status
            == PortfolioDecisionStatus.REJECTED.value
        ):

            if decision.approved:

                raise ProductionIntegrationError(
                    (
                        "Decision status is REJECTED but "
                        "approved=True."
                    )
                )

        # --------------------------------------------------------------
        # FAILED DECISIONS
        # --------------------------------------------------------------

        elif (
            decision.status
            == PortfolioDecisionStatus.FAILED.value
        ):

            if decision.approved:

                raise ProductionIntegrationError(
                    (
                        "Decision status is FAILED but "
                        "approved=True."
                    )
                )

            if not decision.errors:

                raise ProductionIntegrationError(
                    (
                        "FAILED decision contains no "
                        "diagnostic errors."
                    )
                )

    # ==================================================================
    # SECTION 9
    # PRODUCTION DECISION EXECUTION
    # ==================================================================

    def run(
        self,
        *,
        portfolio: dict[str, float],
        returns: Any,
        regimes: Any,
        macro_data: dict[str, Any],
        scenarios: Any = None,
    ) -> ProductionIntegrationResult:
        """
        Execute one production portfolio decision.
        """

        self.execution_count += 1

        try:

            # ----------------------------------------------------------
            # INPUT VALIDATION
            # ----------------------------------------------------------

            self._validate_portfolio(
                portfolio
            )

            self._validate_returns(
                returns
            )

            self._validate_regimes(
                regimes
            )

            self._validate_macro_data(
                macro_data
            )

            # ----------------------------------------------------------
            # ENGINE
            # ----------------------------------------------------------

            engine = (
                self._build_engine()
            )

            # ----------------------------------------------------------
            # DEPENDENCY VALIDATION
            # ----------------------------------------------------------

            self._validate_dependencies(
                engine
            )

            # ----------------------------------------------------------
            # DECISION
            # ----------------------------------------------------------

            decision = (
                engine.decide(
                    portfolio=portfolio,
                    returns=returns,
                    regimes=regimes,
                    macro_data=macro_data,
                    scenarios=scenarios,
                )
            )

            # ----------------------------------------------------------
            # RESULT VALIDATION
            # ----------------------------------------------------------

            self._validate_decision(
                decision
            )

            self.success_count += 1

            result = (
                ProductionIntegrationResult(
                    success=True,
                    status=decision.status,
                    approved=bool(
                        decision.approved
                    ),
                    decision=decision,
                    diagnostics=dict(
                        decision.diagnostics
                    ),
                    errors=tuple(
                        decision.errors
                    ),
                    warnings=tuple(
                        decision.warnings
                    ),
                )
            )

            self.last_result = result

            return result

        except Exception as exc:

            self.failure_count += 1

            result = (
                ProductionIntegrationResult(
                    success=False,
                    status=(
                        PortfolioDecisionStatus.FAILED.value
                    ),
                    approved=False,
                    decision=None,
                    diagnostics={
                        "exception_type": (
                            type(exc).__name__
                        )
                    },
                    errors=(
                        str(exc),
                    ),
                    warnings=tuple(),
                )
            )

            self.last_result = result

            return result

    # ==================================================================
    # SECTION 10
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return Phase IV-B.2 integration health.
        """

        try:

            engine = (
                self._build_engine()
            )

            self._validate_dependencies(
                engine
            )

            engine_health = (
                engine.health_check()
            )

            healthy = bool(
                engine_health.get(
                    "healthy",
                    False,
                )
            )

            return {
                "api_version": (
                    self.API_VERSION
                ),
                "phase": (
                    self.PHASE
                ),
                "healthy": healthy,
                "engine_health": (
                    engine_health
                ),
            }

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

    # ==================================================================
    # SECTION 11
    # METADATA
    # ==================================================================

    def metadata(
        self,
    ) -> dict[str, Any]:
        """
        Return Phase IV-B.2 integration metadata.
        """

        return {
            "module": (
                "productionintegration"
            ),
            "component": (
                "ProductionIntegration"
            ),
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
            ),
            "production_only": True,
            "test_doubles_allowed": False,
            "live_trading_enabled": False,
            "strict_dependency_validation": True,
            "fail_fast_dependency_validation": True,
            "required_components": list(
                self.REQUIRED_COMPONENTS
            ),
        }

    # ==================================================================
    # SECTION 12
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict[str, Any]:
        """
        Return integration execution statistics.
        """

        last = self.last_result

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
            "failure_count": (
                self.failure_count
            ),
            "last_status": (
                None
                if last is None
                else last.status
            ),
            "last_success": (
                None
                if last is None
                else last.success
            ),
            "last_approved": (
                None
                if last is None
                else last.approved
            ),
        }


# ======================================================================
# SECTION 13
# CONVENIENCE FACTORY
# ======================================================================


def build_production_integration(
) -> ProductionIntegration:
    """
    Construct the Phase IV-B.2 production integration boundary.
    """

    return ProductionIntegration()


# ======================================================================
# SECTION 14
# REGRESSION TESTS
# ======================================================================


def test_production_integration_metadata() -> None:
    """
    Verify Phase IV-B.2 metadata.
    """

    integration = (
        ProductionIntegration()
    )

    metadata = (
        integration.metadata()
    )

    assert (
        metadata["api_version"]
        == "1.0.0"
    )

    assert (
        metadata["phase"]
        == "IV-B.2"
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


def test_production_integration_health() -> None:
    """
    Verify the deterministic health-check interface.
    """

    integration = (
        ProductionIntegration()
    )

    result = (
        integration.health_check()
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
        == "IV-B.2"
    )

    assert (
        "healthy"
        in result
    )


def test_production_integration_summary() -> None:
    """
    Verify initial integration statistics.
    """

    integration = (
        ProductionIntegration()
    )

    summary = (
        integration.summary()
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
        summary["failure_count"]
        == 0
    )


# ======================================================================
# SECTION 15
# REGRESSION ENTRY POINT
# ======================================================================


def run_regression_tests() -> None:
    """
    Run Phase IV-B.2 regression tests.
    """

    test_production_integration_metadata()

    test_production_integration_health()

    test_production_integration_summary()

    print(
        "ProductionIntegration Phase IV-B.2 tests passed."
    )


# ======================================================================
# SECTION 16
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    print(
        "============================================================"
    )

    print(
        "PHASE IV-B.2 PRODUCTION INTEGRATION"
    )

    print(
        "============================================================"
    )

    integration = (
        ProductionIntegration()
    )

    print()

    print(
        "METADATA:"
    )

    print(
        integration.metadata()
    )

    print()

    print(
        "HEALTH CHECK:"
    )

    health = (
        integration.health_check()
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
                "Unknown integration error.",
            ),
        )

    print()

    run_regression_tests()