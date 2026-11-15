# ======================================================================
# PRODUCTION EXECUTION GATE
# PHASE IV-B.5 + PHASE 5D KILL SWITCH
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

and before downstream execution infrastructure.

Phase 5D introduces the Kill Switch as an additional execution veto.

Execution authorization sequence
--------------------------------

    Production Decision
            |
            v
    Decision validation
            |
            v
    Risk validation
            |
            v
    Kill Switch
       /        \
   ACTIVE      RELEASED
      |            |
      v            v
  REJECTED     AUTHORIZED
      |
      v
require_authorization()
      |
      v
HARD STOP

Design principles
-----------------
1. PortfolioDecisionEngine remains the authoritative decision source.
2. Phase IV-B.3 remains the authoritative decision-execution source.
3. Phase IV-B.4 remains the authoritative risk-validation source.
4. Phase 5D KillSwitch is an execution veto only.
5. No execution authorization may be produced unless all required
   upstream controls have passed.
6. REJECTED decisions are hard stops.
7. FAILED decisions are hard stops.
8. Missing decision identifiers are hard stops.
9. Missing portfolio weights are hard stops.
10. Invalid risk validation is a hard stop.
11. An active Kill Switch is a hard stop.
12. Execution authorization is immutable.
13. This phase does not place orders.
14. This phase does not route orders.
15. This phase does not communicate with brokers.
16. This phase does not mutate portfolio state.
17. Live trading remains disabled.
18. Broker submission remains disabled.
19. Test doubles are not permitted at the production boundary.
20. The execution gate is deterministic.
21. The execution gate does not override upstream decisions.
22. The Kill Switch does not modify upstream decisions.
23. The Kill Switch does not create an independent authorization.
24. Downstream execution must consume the authorization produced here.
25. Broker and OMS integration belong to downstream execution phases.
"""

# ======================================================================
# SECTION 1
# IMPORTS
# ======================================================================

from __future__ import annotations

from dataclasses import (
    dataclass,
)

from typing import (
    Any,
    Mapping,
)


# ----------------------------------------------------------------------
# 1.1 PRODUCTION DECISION EXECUTION
# ----------------------------------------------------------------------

from productiondecisionexecution import (
    ProductionDecisionExecution,
    ProductionDecisionExecutionResult,
)


# ----------------------------------------------------------------------
# 1.2 DECISION STATUS
# ----------------------------------------------------------------------

from portfoliodecisionengine import (
    PortfolioDecisionStatus,
)


# ----------------------------------------------------------------------
# 1.3 PHASE 5D KILL SWITCH
# ----------------------------------------------------------------------

from circuitbreaker import CircuitBreaker
from killswitch import KillSwitch

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

    AUTHORIZED = (
        "AUTHORIZED"
    )

    REJECTED = (
        "REJECTED"
    )

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

    status: str

    authorized: bool

    decision_id: str | None

    regime: str | None

    weights: dict[str, float]

    portfolio_volatility: float

    portfolio_variance: float

    gross_exposure: float

    net_exposure: float

    risk_contributions: dict[str, float]

    risk_contribution_pct: dict[str, float]

    risk_validation_passed: bool

    live_trading_enabled: bool

    broker_submission_enabled: bool

    warnings: tuple[str, ...]

    errors: tuple[str, ...]

    diagnostics: dict[str, Any]

    api_version: str

    phase: str

    # ==================================================================
    # DICTIONARY REPRESENTATION
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

    It determines whether the already-approved production decision
    satisfies the execution-boundary requirements.

    Phase 5D adds the Kill Switch as a final veto before an
    AUTHORIZED artifact can be created.
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

    KILL_SWITCH_PHASE = (
        "5D"
    )

    CIRCUIT_BREAKER_PHASE = (
        "5E"
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
        kill_switch: (
            KillSwitch
            | None
        ) = None,
        circuit_breaker: (
            CircuitBreaker
            |  None
        ) = None,
    ) -> None:
        """
        Initialize the Phase IV-B.5 execution gate.

        Parameters
        ----------
        decision_execution:
            Real Phase IV-B.3 production decision execution component.

        kill_switch:
            Phase 5D production KillSwitch.

            If omitted, a new released KillSwitch is created.

        No test double is accepted for the production decision
        execution component.
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
        # 5.4.3 KILL SWITCH
        # --------------------------------------------------------------

        if (
            kill_switch
            is None
        ):

            kill_switch = (
                KillSwitch()
            )

        if not isinstance(
            kill_switch,
            KillSwitch,
        ):

            raise ProductionExecutionGateError(
                (
                    "Phase 5D requires a real KillSwitch instance. "
                    "Incompatible objects are not permitted."
                )
            )

        self.kill_switch = (
            kill_switch
        )

        if circuit_breaker is None:
            circuit_breaker = CircuitBreaker()

        if not isinstance(
            circuit_breaker,
            CircuitBreaker,
        ):
            raise ProductionExecutionGateError(
                (
                    "Phase IV-B.5 requires a real CircuitBreaker "
                    "instance. Incompatible objects are not "
                    "permitted."
                )
            )
        self.circuit_breaker = circuit_breaker

        # --------------------------------------------------------------
        # 5.4.4 STATE
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

        if not result.decision_id:

            raise ProductionExecutionGateError(
                "Approved decision has no decision ID."
            )

        if not result.regime:

            raise ProductionExecutionGateError(
                "Approved decision has no regime."
            )

        if not result.weights:

            raise ProductionExecutionGateError(
                "Approved decision has no portfolio weights."
            )

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

        if not result.risk_contributions:

            raise ProductionExecutionGateError(
                (
                    "Approved decision contains no "
                    "risk contributions."
                )
            )

        if not result.risk_contribution_pct:

            raise ProductionExecutionGateError(
                (
                    "Approved decision contains no "
                    "risk contribution percentages."
                )
            )

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
        # DIRECT FLAGS
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

                if nested_key not in nested:

                    continue

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

        return (
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

        return (
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

        return (
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

    # ------------------------------------------------------------------
    # 8.4 KILL SWITCH REJECTION
    # ------------------------------------------------------------------

    def _build_kill_switch_rejection(
        self,
        result: ProductionDecisionExecutionResult,
    ) -> ExecutionAuthorization:
        """
        Construct a non-authorizing artifact when the Phase 5D
        Kill Switch is active.

        Risk validation has already passed at this point.

        Therefore risk_validation_passed remains True.

        The rejection reason explicitly identifies the Kill Switch.
        """

        diagnostics = dict(
            result.diagnostics
        )

        diagnostics[
            "kill_switch_active"
        ] = True

        diagnostics[
            "kill_switch_phase"
        ] = self.KILL_SWITCH_PHASE

        return (
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
                errors=(
                    "PHASE_5D_KILL_SWITCH_ACTIVE",
                ),
                diagnostics=diagnostics,
                api_version=(
                    self.API_VERSION
                ),
                phase=(
                    self.PHASE
                ),
            )
        )

    def _build_circuit_breaker_rejection(
        self,
        result: ProductionDecisionExecutionResult,
    ) -> ExecutionAuthorization:
        """
        Construct a non-authorizing rejection when the Phase 5E
        circuit breaker is OPEN.
        """

        diagnostics = dict(
            result.diagnostics
        )

        diagnostics.update(
            {
                "circuit_breaker_open": True,
                "circuit_breaker_phase": (
                    self.CIRCUIT_BREAKER_PHASE
                ),
                "execution_blocked": True,
            }
        )

        authorization = ExecutionAuthorization(
            status=(
                ExecutionAuthorizationStatus.REJECTED
            ),
            authorized=False,
            decision_id=result.decision_id,
            regime=result.regime,
            weights=dict(result.weights),
            portfolio_volatility=(
                result.portfolio_volatility
            ),
            portfolio_variance=(
                result.portfolio_variance
            ),
            gross_exposure=(
                result.gross_exposure
            ),
            net_exposure=(
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
            errors=(
                "PHASE_5E_CIRCUIT_BREAKER_OPEN",
            ),
            diagnostics=diagnostics,
            api_version=self.API_VERSION,
            phase=self.PHASE,
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

        Authorization requires:

            1. valid production result;
            2. recognized status;
            3. APPROVED status;
            4. valid approved-result fields;
            5. successful Phase IV-B.4 risk validation;
            6. released Phase 5D Kill Switch.

        Only after all six conditions are satisfied can AUTHORIZED
        status be produced.
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
        # 9.7 KILL SWITCH
        # --------------------------------------------------------------

        if self.kill_switch.is_active():

            self.rejected_count += 1

            authorization = (
                self._build_kill_switch_rejection(
                    result
                )
            )

            self.last_authorization = (
                authorization
            )

            return authorization

        # --------------------------------------------------------------
        # 9.8 CIRCUIT BREAKER
        # --------------------------------------------------------------

        if self.circuit_breaker.is_open():

            self.rejected_count += 1

            authorization = (
                self._build_circuit_breaker_rejection(
                    result
                )
            )

            self.last_authorization = (
                authorization
            )

            return authorization

        # --------------------------------------------------------------
        # 9.9 AUTHORIZE
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

        The Kill Switch must itself be healthy before the execution
        gate reports healthy.

        An ACTIVE Kill Switch is operationally valid and therefore does
        not make the gate unhealthy. It makes execution blocked.
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
        # 11.3 KILL SWITCH HEALTH
        # --------------------------------------------------------------

        try:

            kill_switch_health = (
                self.kill_switch.health_check()
            )

            circuit_breaker_health = (
            self.circuit_breaker.health_check()
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
                    "Unable to validate Phase 5D Kill Switch "
                    f"health: {exc}"
                ),
            }

        if not kill_switch_health.get(
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
                "kill_switch_health": (
                    kill_switch_health
                ),
                "error": (
                    "Phase 5D Kill Switch is unhealthy."
                ),
            }

        # --------------------------------------------------------------
        # 11.4 UPSTREAM HEALTH
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
                "kill_switch_health": (
                    kill_switch_health
                ),
                "error": (
                    "Phase IV-B.3 production decision "
                    "execution is unhealthy."
                ),
            }

        # --------------------------------------------------------------
        # 11.5 HEALTHY
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
            "kill_switch_enabled": True,
            "kill_switch_active": (
                self.kill_switch.is_active()
            ),
            "execution_blocked": (
                self.kill_switch.is_active()
                or self.circuit_breaker.is_open()
            ),
            "upstream_health": (
                upstream
            ),
            "kill_switch_health": (
                kill_switch_health
            ),
            "circuit_breaker_health": (
                circuit_breaker_health
            ),
            "circuit_breaker_open": (
                self.circuit_breaker.is_open()
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
            "kill_switch_enabled": True,
            "kill_switch_phase": (
                self.KILL_SWITCH_PHASE
            ),
            "kill_switch_active": (
                self.kill_switch.is_active()
            ),
            "execution_blocked": (
                self.kill_switch.is_active()
            ),
            "circuit_breaker_enabled": True,
            "circuit_breaker_phase": self.CIRCUIT_BREAKER_PHASE,
            "circuit_breaker_open": (
                self.circuit_breaker.is_open()
            ),

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
            "kill_switch_active": (
                self.kill_switch.is_active()
            ),
            "execution_blocked": (
                self.kill_switch.is_active()
            ),
            "circuit_breaker_open": (
                self.circuit_breaker.is_open()
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

    The returned gate contains a released Phase 5D Kill Switch.
    """

    return (
        ProductionExecutionGate()
    )


# ======================================================================
# SECTION 15
# MODULE EXPORTS
# ======================================================================


__all__ = [
    "ExecutionAuthorization",
    "ExecutionAuthorizationStatus",
    "ProductionExecutionGate",
    "ProductionExecutionGateError",
    "build_production_execution_gate",
]


# ======================================================================
# SECTION 16
# MODULE SELF-TEST
# ======================================================================


def _self_test() -> None:
    """
    Minimal deterministic production-boundary self-test.

    This test deliberately does not submit, route, or execute orders.
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
        metadata["live_trading_enabled"]
        is False
    )

    assert (
        metadata["broker_submission_enabled"]
        is False
    )

    assert (
        metadata["kill_switch_enabled"]
        is True
    )

    assert (
        gate.kill_switch.is_active()
        is False
    )

    health = (
        gate.health_check()
    )

    assert (
        health["healthy"]
        is True
    )

    assert (
        health["kill_switch_active"]
        is False
    )

    assert (
        health["execution_blocked"]
        is False
    )

    rejected = (
        ExecutionAuthorization(
            status=(
                ExecutionAuthorizationStatus.REJECTED
            ),
            authorized=False,
            decision_id="SELF-TEST-REJECTED",
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
                "SELF_TEST_REJECTION",
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
            "Rejected authorization must be hard-stopped."
        )


# ======================================================================
# SECTION 17
# MODULE ENTRY POINT
# ======================================================================


if __name__ == "__main__":

    _self_test()

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
    print("METADATA:")
    print(
        gate.metadata()
    )

    print()
    print("HEALTH CHECK:")
    print(
        gate.health_check()
    )

    print()
    print("SUMMARY:")
    print(
        gate.summary()
    )

    print()
    print(
        "PRODUCTION EXECUTION GATE SELF-TEST: PASS"
    )