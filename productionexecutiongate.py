# ======================================================================
# PRODUCTION EXECUTION GATE
# PHASE IV-B.5
# ======================================================================

"""
Production execution authorization boundary for the institutional
portfolio stack.

Phase IV-B.5 sits immediately after:

    Phase IV-B.1
        Production Composition

    Phase IV-B.2
        Production Integration

    Phase IV-B.3
        Production Decision Execution

    Phase IV-B.4
        Production Risk Validation

and before any downstream execution infrastructure.

Design principles
-----------------
1. PortfolioDecisionEngine remains the authoritative decision source.
2. Phase IV-B.3 remains the authoritative decision-execution source.
3. Phase IV-B.4 remains the authoritative risk-validation source.
4. No execution authorization may be produced unless all required
   upstream controls have passed.
5. REJECTED decisions are hard stops.
6. FAILED decisions are hard stops.
7. Missing decision identifiers are hard stops.
8. Missing portfolio weights are hard stops.
9. Invalid risk validation is a hard stop.
10. Execution authorization is immutable.
11. This phase does not place orders.
12. This phase does not communicate with brokers.
13. This phase does not mutate portfolio state.
14. Live trading remains disabled.
15. Test doubles are not used by the production composition boundary.
16. The execution gate is deterministic.
17. The execution gate does not override upstream decisions.
18. The execution gate cannot convert REJECTED or FAILED into APPROVED.
19. Downstream execution must consume the authorization produced here.
20. Broker and OMS integration belong to later execution phases.
"""

# ======================================================================
# SECTION 1
# IMPORTS
# ======================================================================

# ----------------------------------------------------------------------
# 1.1 STANDARD LIBRARY
# ----------------------------------------------------------------------

from __future__ import annotations

from dataclasses import (
    dataclass,
)

from typing import (
    Any,
    Mapping,
)


# ----------------------------------------------------------------------
# 1.2 PRODUCTION DECISION EXECUTION
# ----------------------------------------------------------------------

from productiondecisionexecution import (
    ProductionDecisionExecution,
    ProductionDecisionExecutionResult,
)


# ----------------------------------------------------------------------
# 1.3 DECISION STATUS
# ----------------------------------------------------------------------

from portfoliodecisionengine import (
    PortfolioDecisionStatus,
)


# ======================================================================
# SECTION 2
# EXCEPTIONS
# ======================================================================


class ProductionExecutionGateError(
    RuntimeError
):
    """
    Raised when Phase IV-B.5 cannot safely authorize execution.
    """

    pass


# ======================================================================
# SECTION 3
# EXECUTION AUTHORIZATION STATUS
# ======================================================================


class ExecutionAuthorizationStatus:
    """
    Deterministic execution authorization states.
    """

    # ------------------------------------------------------------------
    # 3.1 AUTHORIZED
    # ------------------------------------------------------------------

    AUTHORIZED = (
        "AUTHORIZED"
    )

    # ------------------------------------------------------------------
    # 3.2 REJECTED
    # ------------------------------------------------------------------

    REJECTED = (
        "REJECTED"
    )

    # ------------------------------------------------------------------
    # 3.3 FAILED
    # ------------------------------------------------------------------

    FAILED = (
        "FAILED"
    )


# ======================================================================
# SECTION 4
# EXECUTION AUTHORIZATION
# ======================================================================


@dataclass(
    frozen=True
)
class ExecutionAuthorization:
    """
    Immutable representation of a Phase IV-B.5 execution authorization.

    This object is an authorization artifact only.

    It does not:
        - submit an order
        - route an order
        - mutate an account
        - communicate with a broker
        - communicate with an OMS
    """

    # ------------------------------------------------------------------
    # 4.1 STATUS
    # ------------------------------------------------------------------

    status: str

    # ------------------------------------------------------------------
    # 4.2 AUTHORIZATION
    # ------------------------------------------------------------------

    authorized: bool

    # ------------------------------------------------------------------
    # 4.3 DECISION ID
    # ------------------------------------------------------------------

    decision_id: str | None

    # ------------------------------------------------------------------
    # 4.4 REGIME
    # ------------------------------------------------------------------

    regime: str | None

    # ------------------------------------------------------------------
    # 4.5 PORTFOLIO WEIGHTS
    # ------------------------------------------------------------------

    weights: dict[str, float]

    # ------------------------------------------------------------------
    # 4.6 PORTFOLIO RISK
    # ------------------------------------------------------------------

    portfolio_volatility: float

    portfolio_variance: float

    # ------------------------------------------------------------------
    # 4.7 EXPOSURE
    # ------------------------------------------------------------------

    gross_exposure: float

    net_exposure: float

    # ------------------------------------------------------------------
    # 4.8 RISK CONTRIBUTIONS
    # ------------------------------------------------------------------

    risk_contributions: dict[str, float]

    risk_contribution_pct: dict[str, float]

    # ------------------------------------------------------------------
    # 4.9 VALIDATION
    # ------------------------------------------------------------------

    risk_validation_passed: bool

    # ------------------------------------------------------------------
    # 4.10 EXECUTION CONTROL
    # ------------------------------------------------------------------

    live_trading_enabled: bool

    broker_submission_enabled: bool

    # ------------------------------------------------------------------
    # 4.11 WARNINGS
    # ------------------------------------------------------------------

    warnings: tuple[str, ...]

    # ------------------------------------------------------------------
    # 4.12 ERRORS
    # ------------------------------------------------------------------

    errors: tuple[str, ...]

    # ------------------------------------------------------------------
    # 4.13 DIAGNOSTICS
    # ------------------------------------------------------------------

    diagnostics: dict[str, Any]

    # ------------------------------------------------------------------
    # 4.14 METADATA
    # ------------------------------------------------------------------

    api_version: str

    phase: str

    # ==================================================================
    # 4.15 DICTIONARY REPRESENTATION
    # ==================================================================

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        Convert the authorization into a serializable dictionary.
        """

        return {
            "status": self.status,
            "authorized": self.authorized,
            "decision_id": self.decision_id,
            "regime": self.regime,
            "weights": dict(
                self.weights
            ),
            "portfolio_volatility": (
                self.portfolio_volatility
            ),
            "portfolio_variance": (
                self.portfolio_variance
            ),
            "gross_exposure": (
                self.gross_exposure
            ),
            "net_exposure": (
                self.net_exposure
            ),
            "risk_contributions": dict(
                self.risk_contributions
            ),
            "risk_contribution_pct": dict(
                self.risk_contribution_pct
            ),
            "risk_validation_passed": (
                self.risk_validation_passed
            ),
            "live_trading_enabled": (
                self.live_trading_enabled
            ),
            "broker_submission_enabled": (
                self.broker_submission_enabled
            ),
            "warnings": tuple(
                self.warnings
            ),
            "errors": tuple(
                self.errors
            ),
            "diagnostics": dict(
                self.diagnostics
            ),
            "api_version": self.api_version,
            "phase": self.phase,
        }


# ======================================================================
# SECTION 5
# PRODUCTION EXECUTION GATE
# ======================================================================


class ProductionExecutionGate:
    """
    Phase IV-B.5 production execution authorization gate.

    The gate consumes the result produced by
    ProductionDecisionExecution.

    It does not independently make portfolio decisions.

    It does not alter the decision.

    It only determines whether the already-approved production
    decision satisfies the execution-boundary requirements.
    """

    # ==================================================================
    # 5.1 API METADATA
    # ==================================================================

    API_VERSION = (
        "1.0.0"
    )

    PHASE = (
        "IV-B.5"
    )

    # ==================================================================
    # 5.2 EXECUTION POLICY
    # ==================================================================

    LIVE_TRADING_ENABLED = (
        False
    )

    BROKER_SUBMISSION_ENABLED = (
        False
    )

    TEST_DOUBLES_ALLOWED = (
        False
    )

    PRODUCTION_ONLY = (
        True
    )

    # ==================================================================
    # 5.3 REQUIRED UPSTREAM PHASE
    # ==================================================================

    REQUIRED_DECISION_PHASE = (
        "IV-B.3"
    )

    REQUIRED_RISK_PHASE = (
        "IV-B.4"
    )

    # ==================================================================
    # 5.4 CONSTRUCTOR
    # ==================================================================

    def __init__(
        self,
        decision_execution: (
            ProductionDecisionExecution
            | None
        ) = None,
    ) -> None:
        """
        Initialize the Phase IV-B.5 execution gate.

        Parameters
        ----------
        decision_execution:
            Real Phase IV-B.3 production decision execution component.

        Notes
        -----
        If omitted, a real ProductionDecisionExecution instance is
        constructed.

        No test double is accepted or injected.
        """

        # --------------------------------------------------------------
        # 5.4.1 DECISION EXECUTION
        # --------------------------------------------------------------

        if (
            decision_execution
            is None
        ):

            decision_execution = (
                ProductionDecisionExecution()
            )

        # --------------------------------------------------------------
        # 5.4.2 TYPE VALIDATION
        # --------------------------------------------------------------

        if not isinstance(
            decision_execution,
            ProductionDecisionExecution,
        ):

            raise ProductionExecutionGateError(
                (
                    "Phase IV-B.5 requires a real "
                    "ProductionDecisionExecution instance. "
                    "Test doubles and incompatible objects are "
                    "not permitted."
                )
            )

        self.decision_execution = (
            decision_execution
        )

        # --------------------------------------------------------------
        # 5.4.3 STATE
        # --------------------------------------------------------------

        self.last_authorization = (
            None
        )

        self.authorized_count = (
            0
        )

        self.rejected_count = (
            0
        )

        self.failed_count = (
            0
        )

    # ==================================================================
    # SECTION 6
    # DECISION RESULT VALIDATION
    # ==================================================================

    # ------------------------------------------------------------------
    # 6.1 TYPE VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_result_type(
        result: ProductionDecisionExecutionResult,
    ) -> None:
        """
        Validate that the supplied result is a real Phase IV-B.3 result.
        """

        if not isinstance(
            result,
            ProductionDecisionExecutionResult,
        ):

            raise ProductionExecutionGateError(
                (
                    "Execution gate requires a "
                    "ProductionDecisionExecutionResult."
                )
            )

    # ------------------------------------------------------------------
    # 6.2 STATUS VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_status(
        result: ProductionDecisionExecutionResult,
    ) -> None:
        """
        Ensure that the upstream status is recognized.
        """

        valid_statuses = {
            PortfolioDecisionStatus.APPROVED.value,
            PortfolioDecisionStatus.REJECTED.value,
            PortfolioDecisionStatus.FAILED.value,
        }

        if (
            result.status
            not in valid_statuses
        ):

            raise ProductionExecutionGateError(
                (
                    "Unknown production decision status: "
                    f"{result.status}"
                )
            )

    # ------------------------------------------------------------------
    # 6.3 APPROVED RESULT VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_approved_result(
        result: ProductionDecisionExecutionResult,
    ) -> None:
        """
        Validate all mandatory fields of an approved result.
        """

        # --------------------------------------------------------------
        # DECISION ID
        # --------------------------------------------------------------

        if not result.decision_id:

            raise ProductionExecutionGateError(
                "Approved decision has no decision ID."
            )

        # --------------------------------------------------------------
        # REGIME
        # --------------------------------------------------------------

        if not result.regime:

            raise ProductionExecutionGateError(
                "Approved decision has no regime."
            )

        # --------------------------------------------------------------
        # WEIGHTS
        # --------------------------------------------------------------

        if not result.weights:

            raise ProductionExecutionGateError(
                "Approved decision has no portfolio weights."
            )

        # --------------------------------------------------------------
        # WEIGHT FINITENESS
        # --------------------------------------------------------------

        for (
            asset,
            weight,
        ) in result.weights.items():

            try:

                value = float(
                    weight
                )

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise ProductionExecutionGateError(
                    (
                        "Portfolio weight for "
                        f"'{asset}' is not numeric."
                    )
                ) from exc

            if not (
                value == value
            ):

                raise ProductionExecutionGateError(
                    (
                        "Portfolio weight for "
                        f"'{asset}' is NaN."
                    )
                )

        # --------------------------------------------------------------
        # RISK VALIDATION
        # --------------------------------------------------------------

        if not result.risk_contributions:

            raise ProductionExecutionGateError(
                (
                    "Approved decision contains no "
                    "risk contributions."
                )
            )

        # --------------------------------------------------------------
        # RISK CONTRIBUTION PERCENTAGES
        # --------------------------------------------------------------

        if not result.risk_contribution_pct:

            raise ProductionExecutionGateError(
                (
                    "Approved decision contains no "
                    "risk contribution percentages."
                )
            )

        # --------------------------------------------------------------
        # APPROVAL FLAG
        # --------------------------------------------------------------

        if not result.approved:

            raise ProductionExecutionGateError(
                (
                    "Decision status is APPROVED but "
                    "approved=False."
                )
            )

    # ==================================================================
    # SECTION 7
    # RISK VALIDATION BOUNDARY
    # ==================================================================

    # ------------------------------------------------------------------
    # 7.1 RISK VALIDATION EXTRACTION
    # ------------------------------------------------------------------

    @staticmethod
    def _risk_validation_passed(
        result: ProductionDecisionExecutionResult,
    ) -> bool:
        """
        Determine whether Phase IV-B.4 risk validation passed.

        The gate accepts explicit validation indicators from the
        diagnostics payload.

        No positive validation is inferred from missing information.
        """

        diagnostics = (
            result.diagnostics
        )

        if not isinstance(
            diagnostics,
            Mapping,
        ):

            return False

        # --------------------------------------------------------------
        # DIRECT FLAG
        # --------------------------------------------------------------

        for key in (
            "risk_validation_passed",
            "risk_validated",
            "validation_passed",
            "risk_validation",
        ):

            if key not in diagnostics:

                continue

            value = diagnostics[
                key
            ]

            if isinstance(
                value,
                bool,
            ):

                return value

            if isinstance(
                value,
                Mapping,
            ):

                if "healthy" in value:

                    return bool(
                        value["healthy"]
                    )

                if "passed" in value:

                    return bool(
                        value["passed"]
                    )

        # --------------------------------------------------------------
        # NESTED RISK VALIDATION
        # --------------------------------------------------------------

        for key in (
            "risk",
            "risk_validation_result",
            "validation",
        ):

            nested = diagnostics.get(
                key
            )

            if not isinstance(
                nested,
                Mapping,
            ):

                continue

            for nested_key in (
                "healthy",
                "passed",
                "approved",
                "valid",
            ):

                if nested_key in nested:

                    value = nested[
                        nested_key
                    ]

                    if isinstance(
                        value,
                        bool,
                    ):

                        return value

        # --------------------------------------------------------------
        # NO POSITIVE EVIDENCE
        # --------------------------------------------------------------

        return False

    # ==================================================================
    # SECTION 8
    # AUTHORIZATION CONSTRUCTION
    # ==================================================================

    # ------------------------------------------------------------------
    # 8.1 AUTHORIZED AUTHORIZATION
    # ------------------------------------------------------------------

    def _build_authorized(
        self,
        result: ProductionDecisionExecutionResult,
    ) -> ExecutionAuthorization:
        """
        Construct an execution authorization from a fully approved
        decision and successful risk validation.
        """

        authorization = (
            ExecutionAuthorization(
                status=(
                    ExecutionAuthorizationStatus.AUTHORIZED
                ),
                authorized=True,
                decision_id=result.decision_id,
                regime=result.regime,
                weights=dict(
                    result.weights
                ),
                portfolio_volatility=float(
                    result.portfolio_volatility
                ),
                portfolio_variance=float(
                    result.portfolio_variance
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
                risk_validation_passed=True,
                live_trading_enabled=(
                    self.LIVE_TRADING_ENABLED
                ),
                broker_submission_enabled=(
                    self.BROKER_SUBMISSION_ENABLED
                ),
                warnings=tuple(
                    result.warnings
                ),
                errors=tuple(),
                diagnostics=dict(
                    result.diagnostics
                ),
                api_version=(
                    self.API_VERSION
                ),
                phase=(
                    self.PHASE
                ),
            )
        )

        return authorization

    # ------------------------------------------------------------------
    # 8.2 REJECTED AUTHORIZATION
    # ------------------------------------------------------------------

    def _build_rejected(
        self,
        result: ProductionDecisionExecutionResult,
    ) -> ExecutionAuthorization:
        """
        Construct a non-authorizing rejection artifact.
        """

        authorization = (
            ExecutionAuthorization(
                status=(
                    ExecutionAuthorizationStatus.REJECTED
                ),
                authorized=False,
                decision_id=result.decision_id,
                regime=result.regime,
                weights=dict(
                    result.weights
                ),
                portfolio_volatility=float(
                    result.portfolio_volatility
                ),
                portfolio_variance=float(
                    result.portfolio_variance
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
                risk_validation_passed=False,
                live_trading_enabled=(
                    self.LIVE_TRADING_ENABLED
                ),
                broker_submission_enabled=(
                    self.BROKER_SUBMISSION_ENABLED
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
                api_version=(
                    self.API_VERSION
                ),
                phase=(
                    self.PHASE
                ),
            )
        )

        return authorization

    # ------------------------------------------------------------------
    # 8.3 FAILED AUTHORIZATION
    # ------------------------------------------------------------------

    def _build_failed(
        self,
        result: ProductionDecisionExecutionResult,
    ) -> ExecutionAuthorization:
        """
        Construct a failed non-authorizing artifact.
        """

        authorization = (
            ExecutionAuthorization(
                status=(
                    ExecutionAuthorizationStatus.FAILED
                ),
                authorized=False,
                decision_id=result.decision_id,
                regime=result.regime,
                weights=dict(
                    result.weights
                ),
                portfolio_volatility=float(
                    result.portfolio_volatility
                ),
                portfolio_variance=float(
                    result.portfolio_variance
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
                risk_validation_passed=False,
                live_trading_enabled=(
                    self.LIVE_TRADING_ENABLED
                ),
                broker_submission_enabled=(
                    self.BROKER_SUBMISSION_ENABLED
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
                api_version=(
                    self.API_VERSION
                ),
                phase=(
                    self.PHASE
                ),
            )
        )

        return authorization

    # ==================================================================
    # SECTION 9
    # EXECUTION AUTHORIZATION
    # ==================================================================

    def authorize(
        self,
        result: ProductionDecisionExecutionResult,
    ) -> ExecutionAuthorization:
        """
        Evaluate a Phase IV-B.3 result at the Phase IV-B.5 execution
        boundary.

        Only an APPROVED decision with explicit successful risk
        validation receives AUTHORIZED status.
        """

        # --------------------------------------------------------------
        # 9.1 TYPE
        # --------------------------------------------------------------

        self._validate_result_type(
            result
        )

        # --------------------------------------------------------------
        # 9.2 STATUS
        # --------------------------------------------------------------

        self._validate_status(
            result
        )

        # --------------------------------------------------------------
        # 9.3 FAILED
        # --------------------------------------------------------------

        if (
            result.status
            == PortfolioDecisionStatus.FAILED.value
        ):

            self.failed_count += 1

            authorization = (
                self._build_failed(
                    result
                )
            )

            self.last_authorization = (
                authorization
            )

            return authorization

        # --------------------------------------------------------------
        # 9.4 REJECTED
        # --------------------------------------------------------------

        if (
            result.status
            == PortfolioDecisionStatus.REJECTED.value
        ):

            self.rejected_count += 1

            authorization = (
                self._build_rejected(
                    result
                )
            )

            self.last_authorization = (
                authorization
            )

            return authorization

        # --------------------------------------------------------------
        # 9.5 APPROVED RESULT
        # --------------------------------------------------------------

        self._validate_approved_result(
            result
        )

        # --------------------------------------------------------------
        # 9.6 RISK VALIDATION
        # --------------------------------------------------------------

        risk_validation_passed = (
            self._risk_validation_passed(
                result
            )
        )

        if not risk_validation_passed:

            self.rejected_count += 1

            failed_validation = (
                ExecutionAuthorization(
                    status=(
                        ExecutionAuthorizationStatus.REJECTED
                    ),
                    authorized=False,
                    decision_id=result.decision_id,
                    regime=result.regime,
                    weights=dict(
                        result.weights
                    ),
                    portfolio_volatility=float(
                        result.portfolio_volatility
                    ),
                    portfolio_variance=float(
                        result.portfolio_variance
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
                    risk_validation_passed=False,
                    live_trading_enabled=(
                        self.LIVE_TRADING_ENABLED
                    ),
                    broker_submission_enabled=(
                        self.BROKER_SUBMISSION_ENABLED
                    ),
                    warnings=tuple(
                        result.warnings
                    ),
                    errors=(
                        "PHASE_IV_B4_RISK_VALIDATION_NOT_CONFIRMED",
                    ),
                    diagnostics=dict(
                        result.diagnostics
                    ),
                    api_version=(
                        self.API_VERSION
                    ),
                    phase=(
                        self.PHASE
                    ),
                )
            )

            self.last_authorization = (
                failed_validation
            )

            return failed_validation

        # --------------------------------------------------------------
        # 9.7 AUTHORIZE
        # --------------------------------------------------------------

        authorization = (
            self._build_authorized(
                result
            )
        )

        self.authorized_count += 1

        self.last_authorization = (
            authorization
        )

        return authorization

    # ==================================================================
    # SECTION 10
    # EXECUTION HARD STOP
    # ==================================================================

    def require_authorization(
        self,
        authorization: ExecutionAuthorization,
    ) -> None:
        """
        Require a valid authorization before downstream execution.

        This method does not execute anything.

        It simply enforces the Phase IV-B.5 hard-stop boundary.
        """

        if not isinstance(
            authorization,
            ExecutionAuthorization,
        ):

            raise ProductionExecutionGateError(
                (
                    "Invalid execution authorization object."
                )
            )

        if (
            authorization.status
            != ExecutionAuthorizationStatus.AUTHORIZED
        ):

            raise ProductionExecutionGateError(
                (
                    "Execution authorization denied. "
                    f"Status: {authorization.status}"
                )
            )

        if not authorization.authorized:

            raise ProductionExecutionGateError(
                "Execution authorization has authorized=False."
            )

        if not authorization.decision_id:

            raise ProductionExecutionGateError(
                "Execution authorization has no decision ID."
            )

        if not authorization.regime:

            raise ProductionExecutionGateError(
                "Execution authorization has no regime."
            )

        if not authorization.weights:

            raise ProductionExecutionGateError(
                "Execution authorization has no portfolio weights."
            )

        if not authorization.risk_validation_passed:

            raise ProductionExecutionGateError(
                (
                    "Execution authorization has not passed "
                    "Phase IV-B.4 risk validation."
                )
            )

    # ==================================================================
    # SECTION 11
    # HEALTH CHECK
    # ==================================================================

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Return the deterministic health state of Phase IV-B.5.
        """

        # --------------------------------------------------------------
        # 11.1 REQUIRED INTERFACE
        # --------------------------------------------------------------

        required_methods = (
            "execute",
            "validate_result",
            "health_check",
            "metadata",
            "summary",
        )

        missing_methods = [
            method
            for method in required_methods
            if not hasattr(
                self.decision_execution,
                method,
            )
        ]

        if missing_methods:

            return {
                "api_version": (
                    self.API_VERSION
                ),
                "phase": (
                    self.PHASE
                ),
                "healthy": False,
                "error": (
                    "ProductionDecisionExecution is missing "
                    f"required methods: {missing_methods}"
                ),
            }

        # --------------------------------------------------------------
        # 11.2 PRODUCTION POLICY
        # --------------------------------------------------------------

        if self.LIVE_TRADING_ENABLED:

            return {
                "api_version": (
                    self.API_VERSION
                ),
                "phase": (
                    self.PHASE
                ),
                "healthy": False,
                "error": (
                    "Live trading must remain disabled "
                    "during Phase IV-B.5."
                ),
            }

        if self.BROKER_SUBMISSION_ENABLED:

            return {
                "api_version": (
                    self.API_VERSION
                ),
                "phase": (
                    self.PHASE
                ),
                "healthy": False,
                "error": (
                    "Broker submission must remain disabled "
                    "during Phase IV-B.5."
                ),
            }

        # --------------------------------------------------------------
        # 11.3 UPSTREAM HEALTH
        # --------------------------------------------------------------

        try:

            upstream = (
                self.decision_execution
                .health_check()
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
                "error": (
                    "Unable to validate Phase IV-B.3 "
                    f"health: {exc}"
                ),
            }

        if not upstream.get(
            "healthy",
            False,
        ):

            return {
                "api_version": (
                    self.API_VERSION
                ),
                "phase": (
                    self.PHASE
                ),
                "healthy": False,
                "upstream_health": (
                    upstream
                ),
                "error": (
                    "Phase IV-B.3 production decision "
                    "execution is unhealthy."
                ),
            }

        # --------------------------------------------------------------
        # 11.4 HEALTHY
        # --------------------------------------------------------------

        return {
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
            ),
            "healthy": True,
            "production_only": (
                self.PRODUCTION_ONLY
            ),
            "live_trading_enabled": (
                self.LIVE_TRADING_ENABLED
            ),
            "broker_submission_enabled": (
                self.BROKER_SUBMISSION_ENABLED
            ),
            "decision_engine_authoritative": True,
            "risk_validation_required": True,
            "upstream_health": (
                upstream
            ),
        }

    # ==================================================================
    # SECTION 12
    # METADATA
    # ==================================================================

    def metadata(
        self,
    ) -> dict[str, Any]:
        """
        Return Phase IV-B.5 metadata.
        """

        return {
            "module": (
                "productionexecutiongate"
            ),
            "component": (
                "ProductionExecutionGate"
            ),
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
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
            "required_decision_phase": (
                self.REQUIRED_DECISION_PHASE
            ),
            "required_risk_phase": (
                self.REQUIRED_RISK_PHASE
            ),
            "decision_engine_authoritative": True,
            "risk_validation_required": True,
            "execution_enabled": False,
        }

    # ==================================================================
    # SECTION 13
    # SUMMARY
    # ==================================================================

    def summary(
        self,
    ) -> dict[str, Any]:
        """
        Return execution-gate state and counters.
        """

        last = (
            self.last_authorization
        )

        return {
            "api_version": (
                self.API_VERSION
            ),
            "phase": (
                self.PHASE
            ),
            "authorized_count": (
                self.authorized_count
            ),
            "rejected_count": (
                self.rejected_count
            ),
            "failed_count": (
                self.failed_count
            ),
            "last_status": (
                last.status
                if last is not None
                else None
            ),
            "last_authorized": (
                last.authorized
                if last is not None
                else False
            ),
            "live_trading_enabled": (
                self.LIVE_TRADING_ENABLED
            ),
            "broker_submission_enabled": (
                self.BROKER_SUBMISSION_ENABLED
            ),
        }


# ======================================================================
# SECTION 14
# CONVENIENCE FACTORY
# ======================================================================


def build_production_execution_gate(
) -> ProductionExecutionGate:
    """
    Construct the complete Phase IV-B.5 production execution gate.
    """

    return (
        ProductionExecutionGate()
    )


# ======================================================================
# SECTION 15
# REGRESSION TESTS
# ======================================================================


def test_execution_authorization_metadata() -> None:
    """
    Verify the immutable authorization metadata.
    """

    authorization = (
        ExecutionAuthorization(
            status=(
                ExecutionAuthorizationStatus.AUTHORIZED
            ),
            authorized=True,
            decision_id="TEST-DECISION",
            regime="expansion",
            weights={
                "SPY": 0.60,
                "TLT": 0.40,
            },
            portfolio_volatility=0.10,
            portfolio_variance=0.01,
            gross_exposure=1.0,
            net_exposure=1.0,
            risk_contributions={
                "SPY": 0.60,
                "TLT": 0.40,
            },
            risk_contribution_pct={
                "SPY": 0.60,
                "TLT": 0.40,
            },
            risk_validation_passed=True,
            live_trading_enabled=False,
            broker_submission_enabled=False,
            warnings=tuple(),
            errors=tuple(),
            diagnostics={
                "risk_validation_passed": True,
            },
            api_version="1.0.0",
            phase="IV-B.5",
        )
    )

    assert (
        authorization.status
        == "AUTHORIZED"
    )

    assert (
        authorization.authorized
        is True
    )

    assert (
        authorization.decision_id
        == "TEST-DECISION"
    )

    assert (
        authorization.live_trading_enabled
        is False
    )

    assert (
        authorization.broker_submission_enabled
        is False
    )

    payload = (
        authorization.to_dict()
    )

    assert (
        payload["phase"]
        == "IV-B.5"
    )


# ======================================================================
# SECTION 16
# PRODUCTION GATE STRUCTURAL TESTS
# ======================================================================


def test_production_execution_gate_metadata() -> None:
    """
    Verify Phase IV-B.5 metadata.
    """

    gate = (
        ProductionExecutionGate()
    )

    metadata = (
        gate.metadata()
    )

    assert (
        metadata["api_version"]
        == "1.0.0"
    )

    assert (
        metadata["phase"]
        == "IV-B.5"
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
        metadata["decision_engine_authoritative"]
        is True
    )

    assert (
        metadata["risk_validation_required"]
        is True
    )

    assert (
        metadata["execution_enabled"]
        is False
    )


# ======================================================================
# SECTION 17
# PRODUCTION GATE HEALTH TEST
# ======================================================================


def test_production_execution_gate_health() -> None:
    """
    Verify that Phase IV-B.5 exposes a deterministic health interface.

    The test uses the real Phase IV-B.3 production implementation.
    No test doubles are injected.
    """

    gate = (
        ProductionExecutionGate()
    )

    result = (
        gate.health_check()
    )

    assert (
        isinstance(
            result,
            dict,
        )
    )

    assert (
        "api_version"
        in result
    )

    assert (
        "phase"
        in result
    )

    assert (
        "healthy"
        in result
    )


# ======================================================================
# SECTION 18
# EXECUTION POLICY TEST
# ======================================================================


def test_execution_policy_is_disabled() -> None:
    """
    Verify that Phase IV-B.5 cannot directly submit live orders.
    """

    gate = (
        ProductionExecutionGate()
    )

    assert (
        gate.LIVE_TRADING_ENABLED
        is False
    )

    assert (
        gate.BROKER_SUBMISSION_ENABLED
        is False
    )

    metadata = (
        gate.metadata()
    )

    assert (
        metadata["execution_enabled"]
        is False
    )


# ======================================================================
# SECTION 19
# AUTHORIZATION HARD-STOP TEST
# ======================================================================


def test_execution_authorization_hard_stop() -> None:
    """
    Verify that non-authorized execution artifacts are hard-stopped.
    """

    gate = (
        ProductionExecutionGate()
    )

    rejected = (
        ExecutionAuthorization(
            status=(
                ExecutionAuthorizationStatus.REJECTED
            ),
            authorized=False,
            decision_id="REJECTED-TEST",
            regime="recession",
            weights={},
            portfolio_volatility=0.0,
            portfolio_variance=0.0,
            gross_exposure=0.0,
            net_exposure=0.0,
            risk_contributions={},
            risk_contribution_pct={},
            risk_validation_passed=False,
            live_trading_enabled=False,
            broker_submission_enabled=False,
            warnings=tuple(),
            errors=(
                "TEST_REJECTION",
            ),
            diagnostics={},
            api_version="1.0.0",
            phase="IV-B.5",
        )
    )

    try:

        gate.require_authorization(
            rejected
        )

    except ProductionExecutionGateError:

        pass

    else:

        raise AssertionError(
            (
                "Rejected authorization must "
                "produce a hard stop."
            )
        )


# ======================================================================
# SECTION 20
# REGRESSION ENTRY POINT
# ======================================================================


def run_regression_tests() -> None:
    """
    Run Phase IV-B.5 regression tests.
    """

    test_execution_authorization_metadata()

    test_production_execution_gate_metadata()

    test_production_execution_gate_health()

    test_execution_policy_is_disabled()

    test_execution_authorization_hard_stop()

    print(
        "ProductionExecutionGate Phase IV-B.5 "
        "tests passed."
    )


# ======================================================================
# SECTION 21
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    print(
        "============================================================"
    )

    print(
        "PHASE IV-B.5 PRODUCTION EXECUTION GATE"
    )

    print(
        "============================================================"
    )

    gate = (
        ProductionExecutionGate()
    )

    print()

    # ------------------------------------------------------------------
    # 21.1 METADATA
    # ------------------------------------------------------------------

    print(
        "METADATA:"
    )

    print(
        gate.metadata()
    )

    print()

    # ------------------------------------------------------------------
    # 21.2 HEALTH CHECK
    # ------------------------------------------------------------------

    print(
        "HEALTH CHECK:"
    )

    health = (
        gate.health_check()
    )

    print(
        health
    )

    print()

    # ------------------------------------------------------------------
    # 21.3 STATUS
    # ------------------------------------------------------------------

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
                "Unknown production execution-gate error.",
            ),
        )

    print()

    # ------------------------------------------------------------------
    # 21.4 SUMMARY
    # ------------------------------------------------------------------

    print(
        "SUMMARY:"
    )

    print(
        gate.summary()
    )

    print()

    # ------------------------------------------------------------------
    # 21.5 REGRESSION TESTS
    # ------------------------------------------------------------------

    run_regression_tests()