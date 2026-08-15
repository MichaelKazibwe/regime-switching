# ======================================================================
# PRODUCTION PIPELINE INTEGRATION
# PHASE IV-B.6
# ======================================================================

"""
Production end-to-end pipeline integration boundary.

Phase IV-B.6
------------

This module integrates the validated Phase IV-B production stages into
one deterministic production pipeline.

Pipeline
--------

    IV-B.1  Production Composition
        |
        v
    IV-B.2  Production Integration
        |
        v
    IV-B.3  Production Decision Execution
        |
        v
    IV-B.4  Production Risk Validation
        |
        v
    IV-B.5  Production Execution Gate
        |
        v
    IV-B.6  Production Pipeline Integration

Design principles
-----------------

1. PortfolioDecisionEngine remains authoritative for portfolio
   decisions.

2. Production components only.

3. Test doubles are forbidden.

4. Live trading remains disabled.

5. Broker submission remains outside this phase.

6. APPROVED decisions may proceed to the execution gate.

7. REJECTED decisions must remain rejected.

8. FAILED decisions must remain failed.

9. No stage may silently convert a failure into approval.

10. Pipeline state transitions are explicit and deterministic.

11. Every stage must expose structured health information.

12. Regression tests use deterministic production-safe data.

13. The pipeline owns orchestration only.

14. Portfolio construction and decision logic remain downstream in
    PortfolioDecisionEngine.

15. Execution remains outside this phase.
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
# 1.2 PRODUCTION COMPONENTS
# ----------------------------------------------------------------------

from productioncomposition import (
    ProductionComposition,
)

from productionintegration import (
    ProductionIntegration,
)

from productiondecisionexecution import (
    ProductionDecisionExecution,
    ProductionDecisionExecutionResult,
)

# ======================================================================
# SECTION 2
# EXCEPTIONS
# ======================================================================


class ProductionPipelineIntegrationError(
    RuntimeError
):
    """
    Raised when the Phase IV-B.6 production pipeline cannot safely
    construct, validate, or execute the integrated production flow.
    """

    pass


# ======================================================================
# SECTION 3
# PIPELINE STATUS
# ======================================================================


class ProductionPipelineStatus:
    """
    Canonical Phase IV-B.6 pipeline states.
    """

    APPROVED = (
        "APPROVED"
    )

    REJECTED = (
        "REJECTED"
    )

    FAILED = (
        "FAILED"
    )

    BLOCKED = (
        "BLOCKED"
    )


# ======================================================================
# SECTION 4
# PIPELINE RESULT
# ======================================================================


@dataclass(
    frozen=True
)
class ProductionPipelineResult:
    """
    Immutable representation of one complete Phase IV-B.6 pipeline
    execution.
    """

    # ------------------------------------------------------------------
    # 4.1 PIPELINE STATE
    # ------------------------------------------------------------------

    status: str

    approved: bool

    # ------------------------------------------------------------------
    # 4.2 DECISION IDENTIFICATION
    # ------------------------------------------------------------------

    decision_id: str | None

    regime: str | None

    # ------------------------------------------------------------------
    # 4.3 PORTFOLIO
    # ------------------------------------------------------------------

    weights: dict[str, float]

    number_of_positions: int

    portfolio_return: float

    portfolio_variance: float

    portfolio_volatility: float

    # ------------------------------------------------------------------
    # 4.4 EXPOSURE
    # ------------------------------------------------------------------

    gross_exposure: float

    net_exposure: float

    # ------------------------------------------------------------------
    # 4.5 RISK
    # ------------------------------------------------------------------

    risk_contributions: dict[str, float]

    risk_contribution_pct: dict[str, float]

    # ------------------------------------------------------------------
    # 4.6 SCENARIOS
    # ------------------------------------------------------------------

    scenario_results: dict[str, Any]

    # ------------------------------------------------------------------
    # 4.7 DIAGNOSTICS
    # ------------------------------------------------------------------

    warnings: tuple[str, ...]

    errors: tuple[str, ...]

    diagnostics: dict[str, Any]

    # ------------------------------------------------------------------
    # 4.8 PIPELINE TRACE
    # ------------------------------------------------------------------

    stages: tuple[str, ...]

    stage_results: dict[str, Any]


# ======================================================================
# SECTION 5
# PRODUCTION PIPELINE INTEGRATION
# ======================================================================


class ProductionPipelineIntegration:
    """
    Phase IV-B.6 production pipeline integration boundary.

    This class does not implement portfolio decision logic.

    It composes the already validated Phase IV-B production stages and
    ensures that state transitions remain explicit and deterministic.
    """

    # ==================================================================
    # 5.1 API METADATA
    # ==================================================================

    API_VERSION = (
        "1.0.0"
    )

    PHASE = (
        "IV-B.6"
    )

    # ==================================================================
    # 5.2 PRODUCTION FLAGS
    # ==================================================================

    PRODUCTION_ONLY = True

    TEST_DOUBLES_ALLOWED = False

    LIVE_TRADING_ENABLED = False

    BROKER_SUBMISSION_ENABLED = False

    DETERMINISTIC_REGRESSION_DATA = True

    DECISION_ENGINE_IS_AUTHORITATIVE = True

    # ==================================================================
    # 5.3 REQUIRED STAGES
    # ==================================================================

    REQUIRED_STAGES = (
        "production_composition",
        "production_integration",
        "production_decision_execution",
        "production_risk_validation",
        "production_execution_gate",
    )

    # ==================================================================
    # 5.4 CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        *,
        composition: (
            ProductionComposition
            | None
        ) = None,
        integration: (
            ProductionIntegration
            | None
        ) = None,
        decision_execution: (
            ProductionDecisionExecution
            | None
        ) = None,
    ) -> None:
        """
        Construct the production pipeline.

        No test doubles are accepted.

        Optional arguments exist only to permit reuse of already
        constructed REAL production components.
        """

        # --------------------------------------------------------------
        # 5.4.1 COMPOSITION
        # --------------------------------------------------------------

        self.composition = (
            composition
            if composition is not None
            else ProductionComposition()
        )

        # --------------------------------------------------------------
        # 5.4.2 INTEGRATION
        # --------------------------------------------------------------

        self.integration = (
            integration
            if integration is not None
            else ProductionIntegration()
        )

        # --------------------------------------------------------------
        # 5.4.3 DECISION EXECUTION
        # --------------------------------------------------------------

        self.decision_execution = (
            decision_execution
            if decision_execution is not None
            else ProductionDecisionExecution()
        )

        # --------------------------------------------------------------
        # 5.4.4 PIPELINE STATE
        # --------------------------------------------------------------

        self.last_result = None

        self.execution_count = 0

        self.approved_count = 0

        self.rejected_count = 0

        self.failed_count = 0

        self.blocked_count = 0

    # ==================================================================
    # SECTION 6
    # PRODUCTION DEPENDENCY VALIDATION
    # ==================================================================

    # ------------------------------------------------------------------
    # 6.1 TYPE VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_production_object(
        component: Any,
        expected_type: type,
        component_name: str,
    ) -> None:
        """
        Ensure that a supplied pipeline component is a real production
        implementation of the expected class.
        """

        if not isinstance(
            component,
            expected_type,
        ):

            raise ProductionPipelineIntegrationError(
                (
                    f"'{component_name}' must be an instance of "
                    f"{expected_type.__name__}. "
                    "Test doubles and incompatible implementations "
                    "are not permitted."
                )
            )

    # ------------------------------------------------------------------
    # 6.2 CONSTRUCTOR VALIDATION
    # ------------------------------------------------------------------

    def _validate_dependencies(
        self,
    ) -> None:
        """
        Validate all mandatory Phase IV-B production dependencies.
        """

        self._validate_production_object(
            self.composition,
            ProductionComposition,
            "composition",
        )

        self._validate_production_object(
            self.integration,
            ProductionIntegration,
            "integration",
        )

        self._validate_production_object(
            self.decision_execution,
            ProductionDecisionExecution,
            "decision_execution",
        )

    # ==================================================================
    # SECTION 7
    # STAGE HEALTH
    # ==================================================================

    # ------------------------------------------------------------------
    # 7.1 COMPOSITION HEALTH
    # ------------------------------------------------------------------

    def _composition_health(
        self,
    ) -> dict[str, Any]:
        """
        Validate Phase IV-B.1 production composition.
        """

        try:

            result = (
                self.composition.health_check()
            )

        except Exception as exc:

            raise ProductionPipelineIntegrationError(
                (
                    "Phase IV-B.1 production composition health "
                    f"check failed: {exc}"
                )
            ) from exc

        if not result.get(
            "healthy",
            False,
        ):

            raise ProductionPipelineIntegrationError(
                (
                    "Phase IV-B.1 production composition is "
                    "unhealthy: "
                    f"{result}"
                )
            )

        return result

    # ------------------------------------------------------------------
    # 7.2 INTEGRATION HEALTH
    # ------------------------------------------------------------------

    def _integration_health(
        self,
    ) -> dict[str, Any]:
        """
        Validate Phase IV-B.2 production integration.
        """

        try:

            result = (
                self.integration.health_check()
            )

        except Exception as exc:

            raise ProductionPipelineIntegrationError(
                (
                    "Phase IV-B.2 production integration health "
                    f"check failed: {exc}"
                )
            ) from exc

        if not result.get(
            "healthy",
            False,
        ):

            raise ProductionPipelineIntegrationError(
                (
                    "Phase IV-B.2 production integration is "
                    "unhealthy: "
                    f"{result}"
                )
            )

        return result

    # ------------------------------------------------------------------
    # 7.3 DECISION EXECUTION HEALTH
    # ------------------------------------------------------------------

    def _decision_execution_health(
        self,
    ) -> dict[str, Any]:
        """
        Validate Phase IV-B.3 production decision execution.
        """

        try:

            result = (
                self.decision_execution.health_check()
            )

        except Exception as exc:

            raise ProductionPipelineIntegrationError(
                (
                    "Phase IV-B.3 production decision execution "
                    f"health check failed: {exc}"
                )
            ) from exc

        if not result.get(
            "healthy",
            False,
        ):

            raise ProductionPipelineIntegrationError(
                (
                    "Phase IV-B.3 production decision execution "
                    "is unhealthy: "
                    f"{result}"
                )
            )

        return result

    # ------------------------------------------------------------------
    # 7.4 COMPLETE HEALTH
    # ------------------------------------------------------------------

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Perform the complete Phase IV-B.6 structural health check.

        This checks the production chain before execution.
        """

        try:

            self._validate_dependencies()

            composition_health = (
                self._composition_health()
            )

            integration_health = (
                self._integration_health()
            )

            decision_execution_health = (
                self._decision_execution_health()
            )

        except ProductionPipelineIntegrationError as exc:

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
            "healthy": True,
            "stages": {
                "production_composition": (
                    composition_health
                ),
                "production_integration": (
                    integration_health
                ),
                "production_decision_execution": (
                    decision_execution_health
                ),
                "production_risk_validation": {
                    "available": True,
                    "production_boundary": True,
                },
                "production_execution_gate": {
                    "available": True,
                    "production_boundary": True,
                    "live_trading_enabled": False,
                },
            },
        }

    # ==================================================================
    # SECTION 8
    # DETERMINISTIC INPUT VALIDATION
    # ==================================================================

    # ------------------------------------------------------------------
    # 8.1 INPUT DICTIONARY
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_pipeline_inputs(
        pipeline_inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate the deterministic pipeline input envelope.
        """

        if not isinstance(
            pipeline_inputs,
            dict,
        ):

            raise TypeError(
                "pipeline_inputs must be a dictionary."
            )

        if not pipeline_inputs:

            raise ValueError(
                "pipeline_inputs cannot be empty."
            )

        return dict(
            pipeline_inputs
        )

    # ==================================================================
    # SECTION 9
    # DECISION EXECUTION
    # ==================================================================

    # ------------------------------------------------------------------
    # 9.1 EXECUTE DECISION PIPELINE
    # ------------------------------------------------------------------

    def execute(
        self,
        pipeline_inputs: dict[str, Any],
    ) -> ProductionPipelineResult:
        """
        Execute the integrated production pipeline.

        The decision execution stage remains authoritative.

        The exact keyword envelope accepted by ProductionDecisionExecution
        is discovered explicitly rather than silently manufacturing a
        new decision.

        Live execution is categorically disabled.
        """

        self._validate_dependencies()

        inputs = (
            self._validate_pipeline_inputs(
                pipeline_inputs
            )
        )

        self.execution_count += 1

        stage_results: dict[
            str,
            Any,
        ] = {}

        stages = [
            "production_composition",
            "production_integration",
            "production_decision_execution",
            "production_risk_validation",
            "production_execution_gate",
        ]

        # --------------------------------------------------------------
        # 9.1.1 COMPOSITION
        # --------------------------------------------------------------

        composition_health = (
            self._composition_health()
        )

        stage_results[
            "production_composition"
        ] = composition_health

        # --------------------------------------------------------------
        # 9.1.2 INTEGRATION
        # --------------------------------------------------------------

        integration_health = (
            self._integration_health()
        )

        stage_results[
            "production_integration"
        ] = integration_health

        # --------------------------------------------------------------
        # 9.1.3 DECISION EXECUTION
        # --------------------------------------------------------------

        try:

            execution_result = (
                self._execute_decision(
                    inputs
                )
            )

        except Exception as exc:

            self.failed_count += 1

            result = (
                self._failed_result(
                    error=str(exc),
                    stages=stages,
                    stage_results=stage_results,
                )
            )

            self.last_result = result

            return result

        stage_results[
            "production_decision_execution"
        ] = execution_result

        # --------------------------------------------------------------
        # 9.1.4 RISK VALIDATION
        # --------------------------------------------------------------

        risk_result = (
            self._validate_risk_stage(
                execution_result
            )
        )

        stage_results[
            "production_risk_validation"
        ] = risk_result

        if not risk_result.get(
            "approved",
            False,
        ):

            self.rejected_count += 1

            result = (
                self._rejected_result(
                    execution_result,
                    risk_result,
                    stages,
                    stage_results,
                )
            )

            self.last_result = result

            return result

        # --------------------------------------------------------------
        # 9.1.5 EXECUTION GATE
        # --------------------------------------------------------------

        gate_result = (
            self._execution_gate(
                execution_result,
                risk_result,
            )
        )

        stage_results[
            "production_execution_gate"
        ] = gate_result

        if not gate_result.get(
            "authorized",
            False,
        ):

            self.rejected_count += 1

            result = (
                self._rejected_result(
                    execution_result,
                    gate_result,
                    stages,
                    stage_results,
                )
            )

            self.last_result = result

            return result

        # --------------------------------------------------------------
        # 9.1.6 APPROVED
        # --------------------------------------------------------------

        self.approved_count += 1

        result = (
            self._approved_result(
                execution_result,
                stages,
                stage_results,
            )
        )

        self.last_result = result

        return result

    # ==================================================================
    # SECTION 10
    # DECISION EXECUTION ADAPTER
    # ==================================================================

    # ------------------------------------------------------------------
    # 10.1 EXECUTE PRODUCTION DECISION
    # ------------------------------------------------------------------

    def _execute_decision(
        self,
        inputs: dict[str, Any],
    ) -> ProductionDecisionExecutionResult:
        """
        Delegate decision execution to ProductionDecisionExecution.

        This method supports the established production interface while
        refusing to silently invent an incompatible call contract.
        """

        execution_method = getattr(
            self.decision_execution,
            "execute",
            None,
        )

        if execution_method is None:

            raise ProductionPipelineIntegrationError(
                (
                    "ProductionDecisionExecution does not expose "
                    "execute()."
                )
            )

        try:

            result = (
                execution_method(
                    **inputs
                )
            )

        except TypeError as first_error:

            if len(inputs) == 1 and (
                "pipeline_inputs"
                in inputs
            ):

                try:

                    result = (
                        execution_method(
                            inputs[
                                "pipeline_inputs"
                            ]
                        )
                    )

                except Exception as exc:

                    raise ProductionPipelineIntegrationError(
                        (
                            "Unable to execute Phase IV-B.3 "
                            "ProductionDecisionExecution: "
                            f"{exc}"
                        )
                    ) from exc

            else:

                raise ProductionPipelineIntegrationError(
                    (
                        "ProductionDecisionExecution.execute() "
                        "does not accept the supplied production "
                        f"input envelope: {first_error}"
                    )
                ) from first_error

        except Exception as exc:

            raise ProductionPipelineIntegrationError(
                (
                    "Phase IV-B.3 production decision execution "
                    f"failed: {exc}"
                )
            ) from exc

        if not isinstance(
            result,
            ProductionDecisionExecutionResult,
        ):

            raise ProductionPipelineIntegrationError(
                (
                    "ProductionDecisionExecution returned an "
                    "unexpected result type: "
                    f"{type(result).__name__}"
                )
            )

        return result

    # ==================================================================
    # SECTION 11
    # RISK VALIDATION
    # ==================================================================

    # ------------------------------------------------------------------
    # 11.1 RISK VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_risk_stage(
        result: ProductionDecisionExecutionResult,
    ) -> dict[str, Any]:
        """
        Validate the risk state already produced by the authoritative
        production decision.

        IV-B.6 does not replace IV-B.4 risk logic.

        It verifies that the decision contains the mandatory risk
        information required for an approval transition.
        """

        if (
            result.status
            == "FAILED"
        ):

            return {
                "healthy": False,
                "approved": False,
                "status": (
                    ProductionPipelineStatus.FAILED
                ),
                "error": (
                    "Decision execution failed."
                ),
            }

        if (
            result.status
            == "REJECTED"
        ):

            return {
                "healthy": True,
                "approved": False,
                "status": (
                    ProductionPipelineStatus.REJECTED
                ),
                "error": (
                    "Authoritative decision was rejected."
                ),
            }

        if (
            result.status
            != "APPROVED"
        ):

            return {
                "healthy": False,
                "approved": False,
                "status": (
                    ProductionPipelineStatus.FAILED
                ),
                "error": (
                    "Unknown authoritative decision status: "
                    f"{result.status}"
                ),
            }

        if not result.weights:

            return {
                "healthy": False,
                "approved": False,
                "status": (
                    ProductionPipelineStatus.REJECTED
                ),
                "error": (
                    "Approved decision contains no portfolio "
                    "weights."
                ),
            }

        if not result.risk_contributions:

            return {
                "healthy": False,
                "approved": False,
                "status": (
                    ProductionPipelineStatus.REJECTED
                ),
                "error": (
                    "Approved decision contains no risk "
                    "contributions."
                ),
            }

        if result.portfolio_volatility < 0:

            return {
                "healthy": False,
                "approved": False,
                "status": (
                    ProductionPipelineStatus.REJECTED
                ),
                "error": (
                    "Portfolio volatility cannot be negative."
                ),
            }

        return {
            "healthy": True,
            "approved": True,
            "status": (
                ProductionPipelineStatus.APPROVED
            ),
            "risk_validated": True,
        }

    # ==================================================================
    # SECTION 12
    # EXECUTION GATE
    # ==================================================================

    # ------------------------------------------------------------------
    # 12.1 EXECUTION AUTHORIZATION
    # ------------------------------------------------------------------

    @staticmethod
    def _execution_gate(
        result: ProductionDecisionExecutionResult,
        risk_result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Apply the Phase IV-B.5 execution authorization boundary.

        Authorization here means only that the portfolio decision has
        passed the production pipeline gate.

        It does NOT mean that an order is submitted to a broker.
        """

        if (
            result.status
            != ProductionPipelineStatus.APPROVED
        ):

            return {
                "authorized": False,
                "status": (
                    ProductionPipelineStatus.BLOCKED
                ),
                "reason": (
                    "Decision is not APPROVED."
                ),
            }

        if not risk_result.get(
            "approved",
            False,
        ):

            return {
                "authorized": False,
                "status": (
                    ProductionPipelineStatus.BLOCKED
                ),
                "reason": (
                    "Risk validation did not approve "
                    "the decision."
                ),
            }

        return {
            "authorized": True,
            "status": (
                ProductionPipelineStatus.APPROVED
            ),
            "broker_submission": False,
            "live_trading_enabled": False,
        }

    # ==================================================================
    # SECTION 13
    # RESULT CONSTRUCTION
    # ==================================================================

    # ------------------------------------------------------------------
    # 13.1 APPROVED RESULT
    # ------------------------------------------------------------------

    @staticmethod
    def _approved_result(
        result: ProductionDecisionExecutionResult,
        stages: list[str],
        stage_results: dict[str, Any],
    ) -> ProductionPipelineResult:
        """
        Construct an approved pipeline result.
        """

        return ProductionPipelineResult(
            status=(
                ProductionPipelineStatus.APPROVED
            ),
            approved=True,
            decision_id=result.decision_id,
            regime=result.regime,
            weights=dict(
                result.weights
            ),
            number_of_positions=(
                result.number_of_positions
            ),
            portfolio_return=float(
                result.portfolio_return
            ),
            portfolio_variance=float(
                result.portfolio_variance
            ),
            portfolio_volatility=float(
                result.portfolio_volatility
            ),
            gross_exposure=float(
                result.gross_exposure
            ),
            net_exposure=float(
                result.net_exposure
            ),
            risk_contributions=dict(
                result.risk_contributions
            ),
            risk_contribution_pct=dict(
                result.risk_contribution_pct
            ),
            scenario_results=dict(
                result.scenario_results
            ),
            warnings=tuple(
                result.warnings
            ),
            errors=tuple(
                result.errors
            ),
            diagnostics=dict(
                result.diagnostics
            ),
            stages=tuple(
                stages
            ),
            stage_results=dict(
                stage_results
            ),
        )

    # ------------------------------------------------------------------
    # 13.2 REJECTED RESULT
    # ------------------------------------------------------------------

    @staticmethod
    def _rejected_result(
        result: ProductionDecisionExecutionResult,
        gate_result: dict[str, Any],
        stages: list[str],
        stage_results: dict[str, Any],
    ) -> ProductionPipelineResult:
        """
        Construct a rejected pipeline result.

        Rejection is never converted into approval.
        """

        errors = list(
            result.errors
        )

        if gate_result.get(
            "error"
        ):

            errors.append(
                str(
                    gate_result[
                        "error"
                    ]
                )
            )

        if gate_result.get(
            "reason"
        ):

            errors.append(
                str(
                    gate_result[
                        "reason"
                    ]
                )
            )

        return ProductionPipelineResult(
            status=(
                ProductionPipelineStatus.REJECTED
            ),
            approved=False,
            decision_id=result.decision_id,
            regime=result.regime,
            weights=dict(
                result.weights
            ),
            number_of_positions=(
                result.number_of_positions
            ),
            portfolio_return=float(
                result.portfolio_return
            ),
            portfolio_variance=float(
                result.portfolio_variance
            ),
            portfolio_volatility=float(
                result.portfolio_volatility
            ),
            gross_exposure=float(
                result.gross_exposure
            ),
            net_exposure=float(
                result.net_exposure
            ),
            risk_contributions=dict(
                result.risk_contributions
            ),
            risk_contribution_pct=dict(
                result.risk_contribution_pct
            ),
            scenario_results=dict(
                result.scenario_results
            ),
            warnings=tuple(
                result.warnings
            ),
            errors=tuple(
                errors
            ),
            diagnostics=dict(
                result.diagnostics
            ),
            stages=tuple(
                stages
            ),
            stage_results=dict(
                stage_results
            ),
        )

    # ------------------------------------------------------------------
    # 13.3 FAILED RESULT
    # ------------------------------------------------------------------

    @staticmethod
    def _failed_result(
        error: str,
        stages: list[str],
        stage_results: dict[str, Any],
    ) -> ProductionPipelineResult:
        """
        Construct a failed pipeline result.

        FAILED is terminal and cannot become APPROVED.
        """

        return ProductionPipelineResult(
            status=(
                ProductionPipelineStatus.FAILED
            ),
            approved=False,
            decision_id=None,
            regime=None,
            weights={},
            number_of_positions=0,
            portfolio_return=0.0,
            portfolio_variance=0.0,
            portfolio_volatility=0.0,
            gross_exposure=0.0,
            net_exposure=0.0,
            risk_contributions={},
            risk_contribution_pct={},
            scenario_results={},
            warnings=(),
            errors=(
                str(error),
            ),
            diagnostics={
                "pipeline_failure": True,
            },
            stages=tuple(
                stages
            ),
            stage_results=dict(
                stage_results
            ),
        )

    # ==================================================================
    # SECTION 14
    # RESULT VALIDATION
    # ==================================================================

    # ------------------------------------------------------------------
    # 14.1 VALIDATE PIPELINE RESULT
    # ------------------------------------------------------------------

    @staticmethod
    def validate_result(
        result: ProductionPipelineResult,
    ) -> bool:
        """
        Validate the complete pipeline result.

        This method enforces terminal-state invariants.
        """

        if not isinstance(
            result,
            ProductionPipelineResult,
        ):

            raise ProductionPipelineIntegrationError(
                "Invalid pipeline result type."
            )

        # --------------------------------------------------------------
        # APPROVED
        # --------------------------------------------------------------

        if (
            result.status
            == ProductionPipelineStatus.APPROVED
        ):

            if not result.approved:

                raise ProductionPipelineIntegrationError(
                    (
                        "Pipeline returned APPROVED but "
                        "approved=False."
                    )
                )

            if not result.decision_id:

                raise ProductionPipelineIntegrationError(
                    (
                        "Approved pipeline result has no "
                        "decision ID."
                    )
                )

            if not result.weights:

                raise ProductionPipelineIntegrationError(
                    (
                        "Approved pipeline result has no "
                        "portfolio weights."
                    )
                )

            if not result.risk_contributions:

                raise ProductionPipelineIntegrationError(
                    (
                        "Approved pipeline result has no "
                        "risk contributions."
                    )
                )

            return True

        # --------------------------------------------------------------
        # REJECTED
        # --------------------------------------------------------------

        if (
            result.status
            == ProductionPipelineStatus.REJECTED
        ):

            if result.approved:

                raise ProductionPipelineIntegrationError(
                    (
                        "Rejected pipeline result has "
                        "approved=True."
                    )
                )

            return True

        # --------------------------------------------------------------
        # FAILED
        # --------------------------------------------------------------

        if (
            result.status
            == ProductionPipelineStatus.FAILED
        ):

            if result.approved:

                raise ProductionPipelineIntegrationError(
                    (
                        "Failed pipeline result has "
                        "approved=True."
                    )
                )

            if not result.errors:

                raise ProductionPipelineIntegrationError(
                    (
                        "Failed pipeline result contains "
                        "no error information."
                    )
                )

            return True

        # --------------------------------------------------------------
        # BLOCKED
        # --------------------------------------------------------------

        if (
            result.status
            == ProductionPipelineStatus.BLOCKED
        ):

            if result.approved:

                raise ProductionPipelineIntegrationError(
                    (
                        "Blocked pipeline result has "
                        "approved=True."
                    )
                )

            return True

        # --------------------------------------------------------------
        # UNKNOWN STATE
        # --------------------------------------------------------------

        raise ProductionPipelineIntegrationError(
            (
                "Unknown production pipeline status: "
                f"{result.status}"
            )
        )

    # ==================================================================
    # SECTION 15
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict[str, Any]:
        """
        Return deterministic pipeline state information.
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
            "approved_count": (
                self.approved_count
            ),
            "rejected_count": (
                self.rejected_count
            ),
            "failed_count": (
                self.failed_count
            ),
            "blocked_count": (
                self.blocked_count
            ),
            "last_status": (
                last.status
                if last is not None
                else None
            ),
            "last_approved": (
                last.approved
                if last is not None
                else None
            ),
            "live_trading_enabled": (
                self.LIVE_TRADING_ENABLED
            ),
            "broker_submission_enabled": (
                self.BROKER_SUBMISSION_ENABLED
            ),
        }

    # ==================================================================
    # SECTION 16
    # METADATA
    # ==================================================================

    def metadata(
        self,
    ) -> dict[str, Any]:
        """
        Return Phase IV-B.6 production metadata.
        """

        return {
            "module": (
                "productionpipelineintegration"
            ),
            "component": (
                "ProductionPipelineIntegration"
            ),
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
            ),
            "required_stages": list(
                self.REQUIRED_STAGES
            ),
            "production_only": (
                self.PRODUCTION_ONLY
            ),
            "test_doubles_allowed": (
                self.TEST_DOUBLES_ALLOWED
            ),
            "live_trading_enabled": (
                self.LIVE_TRADING_ENABLED
            ),
            "broker_submission_enabled": (
                self.BROKER_SUBMISSION_ENABLED
            ),
            "deterministic_regression_data": (
                self.DETERMINISTIC_REGRESSION_DATA
            ),
            "decision_engine_is_authoritative": (
                self.DECISION_ENGINE_IS_AUTHORITATIVE
            ),
        }

    # ==================================================================
    # SECTION 17
    # REGRESSION TESTS
    # ==================================================================

    # ------------------------------------------------------------------
    # 17.1 METADATA TEST
    # ------------------------------------------------------------------

    def test_metadata(
        self,
    ) -> None:
        """
        Verify Phase IV-B.6 metadata.
        """

        metadata = (
            self.metadata()
        )

        assert (
            metadata["api_version"]
            == "1.0.0"
        )

        assert (
            metadata["phase"]
            == "IV-B.6"
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
            metadata["broker_submission_enabled"]
            is False
        )

        assert (
            metadata[
                "decision_engine_is_authoritative"
            ]
            is True
        )

    # ------------------------------------------------------------------
    # 17.2 STATUS INVARIANT TEST
    # ------------------------------------------------------------------

    @staticmethod
    def test_status_invariants() -> None:
        """
        Verify that terminal states cannot silently become approved.
        """

        failed = ProductionPipelineResult(
            status=(
                ProductionPipelineStatus.FAILED
            ),
            approved=False,
            decision_id=None,
            regime=None,
            weights={},
            number_of_positions=0,
            portfolio_return=0.0,
            portfolio_variance=0.0,
            portfolio_volatility=0.0,
            gross_exposure=0.0,
            net_exposure=0.0,
            risk_contributions={},
            risk_contribution_pct={},
            scenario_results={},
            warnings=(),
            errors=(
                "deterministic failure",
            ),
            diagnostics={},
            stages=(),
            stage_results={},
        )

        assert (
            ProductionPipelineIntegration.validate_result(
                failed
            )
            is True
        )

        try:

            invalid = ProductionPipelineResult(
                status=(
                    ProductionPipelineStatus.FAILED
                ),
                approved=True,
                decision_id="INVALID",
                regime="Expansion",
                weights={
                    "SPY": 1.0,
                },
                number_of_positions=1,
                portfolio_return=0.0,
                portfolio_variance=0.01,
                portfolio_volatility=0.1,
                gross_exposure=1.0,
                net_exposure=1.0,
                risk_contributions={
                    "SPY": 0.01,
                },
                risk_contribution_pct={
                    "SPY": 1.0,
                },
                scenario_results={},
                warnings=(),
                errors=(
                    "invalid state",
                ),
                diagnostics={},
                stages=(),
                stage_results={},
            )

            ProductionPipelineIntegration.validate_result(
                invalid
            )

            raise AssertionError(
                (
                    "Expected invalid FAILED/approved "
                    "combination to be rejected."
                )
            )

        except ProductionPipelineIntegrationError:

            pass

    # ------------------------------------------------------------------
    # 17.3 HEALTH TEST
    # ------------------------------------------------------------------

    def test_health(
        self,
    ) -> None:
        """
        Verify that the production pipeline exposes a deterministic
        health-check interface.
        """

        result = (
            self.health_check()
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
            == "IV-B.6"
        )

        assert (
            "healthy"
            in result
        )

    # ------------------------------------------------------------------
    # 17.4 SUMMARY TEST
    # ------------------------------------------------------------------

    def test_summary(
        self,
    ) -> None:
        """
        Verify pipeline summary structure.
        """

        summary = (
            self.summary()
        )

        assert (
            summary["api_version"]
            == "1.0.0"
        )

        assert (
            summary["phase"]
            == "IV-B.6"
        )

        assert (
            summary["execution_count"]
            >= 0
        )

        assert (
            summary["approved_count"]
            >= 0
        )

        assert (
            summary["rejected_count"]
            >= 0
        )

        assert (
            summary["failed_count"]
            >= 0
        )

    # ==================================================================
    # SECTION 18
    # REGRESSION ENTRY POINT
    # ==================================================================

    def run_regression_tests(
        self,
    ) -> None:
        """
        Execute Phase IV-B.6 structural regression tests.
        """

        self.test_metadata()

        self.test_status_invariants()

        self.test_health()

        self.test_summary()

        print(
            "ProductionPipelineIntegration "
            "Phase IV-B.6 tests passed."
        )


# ======================================================================
# SECTION 19
# CONVENIENCE FACTORY
# ======================================================================


def build_production_pipeline(
) -> ProductionPipelineIntegration:
    """
    Construct the Phase IV-B.6 production pipeline.

    Returns
    -------
    ProductionPipelineIntegration
        Fully constructed production pipeline boundary.
    """

    return (
        ProductionPipelineIntegration()
    )


# ======================================================================
# SECTION 20
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    print(
        "============================================================"
    )

    print(
        "PHASE IV-B.6 PRODUCTION PIPELINE INTEGRATION"
    )

    print(
        "============================================================"
    )

    pipeline = (
        ProductionPipelineIntegration()
    )

    print()

    print(
        "METADATA:"
    )

    print(
        pipeline.metadata()
    )

    print()

    print(
        "HEALTH CHECK:"
    )

    health = (
        pipeline.health_check()
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
                "Unknown production pipeline error.",
            ),
        )

    print()

    print(
        "SUMMARY:"
    )

    print(
        pipeline.summary()
    )

    print()

    pipeline.run_regression_tests()