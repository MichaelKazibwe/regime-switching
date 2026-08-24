from __future__ import annotations

from typing import Any

import pytest

from portfoliodecisionengine import (
    PortfolioDecisionStatus,
)
from productiondecisionexecution import (
    ProductionDecisionExecutionResult,
)
from productionexecutiongate import (
    ExecutionAuthorization,
    ExecutionAuthorizationStatus,
    ProductionExecutionGate,
    ProductionExecutionGateError,
)
from productionriskvalidation import (
    ProductionRiskValidation,
    ProductionRiskValidationResult,
)


# ============================================================================
# PHASE IV-D
# PRODUCTION RISK VALIDATION / EXECUTION AUTHORITY REGRESSION
# ============================================================================
#
# Design goals
# -----------
#
# 1. Use the real ProductionDecisionExecutionResult contract.
# 2. Use the real ProductionRiskValidation contract.
# 3. Verify that compliant risk validation can produce an approved result.
# 4. Verify that missing / failed validation cannot authorize execution.
# 5. Verify that the execution hard-stop remains fail-closed.
# 6. Verify serialization of the authoritative risk-validation result.
# 7. Verify deterministic behavior.
#
# IMPORTANT
# ---------
#
# ProductionExecutionGate currently consumes risk-validation evidence from
# the ProductionDecisionExecutionResult diagnostics payload.
#
# This test file therefore tests the CURRENT Phase IV-B.4 / IV-B.5 boundary
# exactly as implemented. It does not silently assume that Phase IV-D
# integration has already been implemented.
# ============================================================================


# ============================================================================
# SECTION 1
# DETERMINISTIC RISK-BUDGET RESULT
# ============================================================================


class RegressionRiskBudget:
    """
    Deterministic representation of an existing RiskBudgetEngine result.

    ProductionRiskValidation explicitly consumes the existing risk-budget
    result rather than calculating risk budgets independently.
    """

    def __init__(
        self,
        *,
        within_tolerance: bool = True,
        budget_error: float = 0.0,
    ) -> None:

        self.within_tolerance = bool(
            within_tolerance
        )

        self.budget_error = float(
            budget_error
        )

        self.diagnostics = {
            "source": (
                "RiskBudgetEngine"
            ),
        }


# ============================================================================
# SECTION 2
# DETERMINISTIC AUTHORITATIVE DECISION
# ============================================================================


class RegressionDecision:
    """
    Deterministic authoritative portfolio decision used only by the
    ProductionRiskValidation regression tests.

    This mirrors the deterministic regression object already used by the
    productionriskvalidation module.
    """

    def __init__(
        self,
        *,
        status: str = (
            PortfolioDecisionStatus.APPROVED.value
        ),
        decision_id: str = (
            "PDEC-IV-D-000001"
        ),
        regime: str = "neutral",
        weights: dict[str, float] | None = None,
        volatility: float = 0.10,
        gross_exposure: float = 1.0,
        net_exposure: float = 0.20,
    ) -> None:

        self.status = status

        self.approved = (
            status
            == PortfolioDecisionStatus.APPROVED.value
        )

        self.decision_id = decision_id

        self.regime = regime

        self.weights = (
            dict(weights)
            if weights is not None
            else {
                "SPY": 0.50,
                "TLT": 0.30,
                "GLD": 0.20,
            }
        )

        self.portfolio_return = 0.05

        self.portfolio_variance = (
            float(volatility) ** 2
        )

        self.portfolio_volatility = (
            float(volatility)
        )

        self.gross_exposure = (
            float(gross_exposure)
        )

        self.net_exposure = (
            float(net_exposure)
        )

        self.number_of_positions = (
            len(self.weights)
        )

        self.risk_contributions = {
            ticker: (
                abs(weight)
                * 0.01
            )
            for ticker, weight
            in self.weights.items()
        }

        total_rc = sum(
            self.risk_contributions.values()
        )

        if total_rc > 0:

            self.risk_contribution_pct = {
                ticker: (
                    value
                    / total_rc
                )
                for ticker, value
                in self.risk_contributions.items()
            }

        else:

            self.risk_contribution_pct = {}

        self.scenario_results = {
            "BASE": {
                "portfolio_return": 0.05,
            },
            "RECESSION": {
                "portfolio_return": -0.02,
            },
        }

        self.warnings: tuple[str, ...] = ()

        self.errors: tuple[str, ...] = ()

        self.diagnostics: dict[str, Any] = {}


# ============================================================================
# SECTION 3
# REAL PRODUCTION DECISION EXECUTION RESULT
# ============================================================================


def build_execution_result(
    *,
    diagnostics: dict[str, Any] | None = None,
    status: str = (
        PortfolioDecisionStatus.APPROVED.value
    ),
    approved: bool = True,
    success: bool = True,
) -> ProductionDecisionExecutionResult:
    """
    Construct the real production execution-result dataclass.

    ProductionExecutionGate explicitly rejects objects that are not
    ProductionDecisionExecutionResult instances.
    """

    weights = {
        "SPY": 0.50,
        "TLT": 0.30,
        "GLD": 0.20,
    }

    risk_contributions = {
        "SPY": 0.005,
        "TLT": 0.003,
        "GLD": 0.002,
    }

    risk_contribution_pct = {
        "SPY": 0.50,
        "TLT": 0.30,
        "GLD": 0.20,
    }

    return ProductionDecisionExecutionResult(
        success=bool(success),
        status=status,
        approved=bool(approved),
        decision_id="PDEC-IV-D-000001",
        regime="neutral",
        weights=weights,
        portfolio_return=0.05,
        portfolio_variance=0.01,
        portfolio_volatility=0.10,
        gross_exposure=1.0,
        net_exposure=0.20,
        number_of_positions=3,
        risk_contributions=risk_contributions,
        risk_contribution_pct=risk_contribution_pct,
        scenario_results={
            "BASE": {
                "portfolio_return": 0.05,
            },
            "RECESSION": {
                "portfolio_return": -0.02,
            },
        },
        warnings=(),
        errors=(),
        diagnostics=(
            dict(
                diagnostics
                or {}
            )
        ),
    )


# ============================================================================
# SECTION 4
# AUTHORITATIVE RISK VALIDATOR
# ============================================================================


def build_validator() -> ProductionRiskValidation:
    """
    Construct a deterministic production risk validator.

    These limits mirror the existing production regression configuration.
    """

    return ProductionRiskValidation(
        max_portfolio_volatility=0.15,
        max_net_exposure=1.0,
        max_position_weight=0.60,
        fail_closed=True,
    )


def build_approved_validation_result() -> ProductionRiskValidationResult:
    """
    Execute the real ProductionRiskValidation against a compliant
    authoritative decision.
    """

    validator = build_validator()

    decision = RegressionDecision()

    risk_budget = RegressionRiskBudget(
        within_tolerance=True,
        budget_error=0.0,
    )

    result = validator.validate(
        decision,
        risk_budget_result=risk_budget,
        regime_max_leverage=1.0,
    )

    return result


# ============================================================================
# SECTION 5
# RISK VALIDATION REGRESSION
# ============================================================================


def test_authoritative_validator_returns_real_result() -> None:
    """
    A valid production decision must produce the real immutable
    ProductionRiskValidationResult type.
    """

    result = (
        build_approved_validation_result()
    )

    assert isinstance(
        result,
        ProductionRiskValidationResult,
    )


def test_authoritative_validator_approves_compliant_decision() -> None:
    """
    A fully compliant decision must be approved.
    """

    result = (
        build_approved_validation_result()
    )

    assert result.approved is True

    assert result.status == (
        ProductionRiskValidation.APPROVED
    )

    assert result.errors == ()

    assert result.risk_budget_compliant is True

    assert result.volatility_compliant is True

    assert result.gross_exposure_compliant is True

    assert result.net_exposure_compliant is True

    assert result.concentration_compliant is True

    assert result.numerical_integrity_compliant is True


def test_authoritative_validator_requires_risk_budget() -> None:
    """
    Risk validation must fail closed when the existing risk-budget result
    is absent.
    """

    validator = build_validator()

    decision = RegressionDecision()

    result = validator.validate(
        decision,
        risk_budget_result=None,
        regime_max_leverage=1.0,
    )

    assert result.approved is False

    assert result.status == (
        ProductionRiskValidation.REJECTED
    )

    assert result.risk_budget_compliant is False


def test_authoritative_validator_rejects_excessive_leverage() -> None:
    """
    Gross exposure above the regime leverage limit must be rejected.
    """

    validator = build_validator()

    decision = RegressionDecision(
        gross_exposure=1.20,
    )

    risk_budget = RegressionRiskBudget()

    result = validator.validate(
        decision,
        risk_budget_result=risk_budget,
        regime_max_leverage=1.0,
    )

    assert result.approved is False

    assert result.gross_exposure_compliant is False


def test_authoritative_validator_rejects_excessive_concentration() -> None:
    """
    A position above the configured concentration limit must be rejected.
    """

    validator = build_validator()

    decision = RegressionDecision(
        weights={
            "SPY": 0.80,
            "TLT": 0.10,
            "GLD": 0.10,
        },
    )

    risk_budget = RegressionRiskBudget()

    result = validator.validate(
        decision,
        risk_budget_result=risk_budget,
        regime_max_leverage=1.0,
    )

    assert result.approved is False

    assert result.concentration_compliant is False


def test_authoritative_validator_rejects_non_approved_decision() -> None:
    """
    A rejected upstream decision cannot become an approved risk result.
    """

    validator = build_validator()

    decision = RegressionDecision(
        status=(
            PortfolioDecisionStatus.REJECTED.value
        ),
    )

    risk_budget = RegressionRiskBudget()

    result = validator.validate(
        decision,
        risk_budget_result=risk_budget,
        regime_max_leverage=1.0,
    )

    assert result.approved is False


# ============================================================================
# SECTION 6
# RISK VALIDATION SERIALIZATION
# ============================================================================


def test_risk_validation_result_serializes() -> None:
    """
    The authoritative risk result must expose a complete serializable
    representation.
    """

    result = (
        build_approved_validation_result()
    )

    payload = result.to_dict()

    assert isinstance(
        payload,
        dict,
    )

    assert payload["approved"] is True

    assert payload["status"] == (
        ProductionRiskValidation.APPROVED
    )

    assert payload["decision_id"] == (
        "PDEC-IV-D-000001"
    )

    assert payload["regime"] == "neutral"

    assert payload["risk_budget_compliant"] is True

    assert payload["volatility_compliant"] is True

    assert payload["gross_exposure_compliant"] is True

    assert payload["net_exposure_compliant"] is True

    assert payload["concentration_compliant"] is True

    assert payload["numerical_integrity_compliant"] is True

    assert isinstance(
        payload["checks"],
        list,
    )

    assert isinstance(
        payload["diagnostics"],
        dict,
    )


# ============================================================================
# SECTION 7
# EXECUTION GATE TYPE CONTRACT
# ============================================================================


def test_execution_gate_requires_real_execution_result() -> None:
    """
    ProductionExecutionGate must reject duck-typed objects.

    This documents the actual production type contract discovered during
    the initial Phase IV-D test run.
    """

    gate = ProductionExecutionGate()

    class InvalidExecutionResult:
        pass

    with pytest.raises(
        ProductionExecutionGateError
    ):
        gate.authorize(
            InvalidExecutionResult()
        )


# ============================================================================
# SECTION 8
# EXECUTION GATE — MISSING VALIDATION
# ============================================================================


def test_execution_gate_rejects_missing_risk_validation() -> None:
    """
    Missing validation evidence must never authorize execution.
    """

    gate = ProductionExecutionGate()

    result = build_execution_result(
        diagnostics={}
    )

    authorization = gate.authorize(
        result
    )

    assert isinstance(
        authorization,
        ExecutionAuthorization,
    )

    assert authorization.status == (
        ExecutionAuthorizationStatus.REJECTED
    )

    assert authorization.authorized is False

    assert authorization.risk_validation_passed is False


def test_execution_gate_rejects_false_validation() -> None:
    """
    Explicit failed validation must reject execution.
    """

    gate = ProductionExecutionGate()

    result = build_execution_result(
        diagnostics={
            "risk_validation_passed": False,
        }
    )

    authorization = gate.authorize(
        result
    )

    assert authorization.status == (
        ExecutionAuthorizationStatus.REJECTED
    )

    assert authorization.authorized is False

    assert authorization.risk_validation_passed is False


# ============================================================================
# SECTION 9
# EXECUTION GATE — VALIDATION RESULT
# ============================================================================


def test_execution_gate_accepts_serialized_approved_validation() -> None:
    """
    The gate must accept positive evidence represented by the serialized
    authoritative ProductionRiskValidationResult.
    """

    validation_result = (
        build_approved_validation_result()
    )

    assert validation_result.approved is True

    gate = ProductionExecutionGate()

    result = build_execution_result(
        diagnostics={
            "risk_validation_result": (
                validation_result.to_dict()
            ),
        }
    )

    authorization = gate.authorize(
        result
    )

    assert authorization.status == (
        ExecutionAuthorizationStatus.AUTHORIZED
    )

    assert authorization.authorized is True

    assert authorization.risk_validation_passed is True


def test_execution_gate_rejects_serialized_rejected_validation() -> None:
    """
    A serialized rejected risk-validation result cannot authorize
    execution.
    """

    validator = build_validator()

    decision = RegressionDecision(
        gross_exposure=1.20,
    )

    rejected_result = validator.validate(
        decision,
        risk_budget_result=RegressionRiskBudget(),
        regime_max_leverage=1.0,
    )

    assert rejected_result.approved is False

    gate = ProductionExecutionGate()

    result = build_execution_result(
        diagnostics={
            "risk_validation_result": (
                rejected_result.to_dict()
            ),
        }
    )

    authorization = gate.authorize(
        result
    )

    assert authorization.status == (
        ExecutionAuthorizationStatus.REJECTED
    )

    assert authorization.authorized is False

    assert authorization.risk_validation_passed is False


# ============================================================================
# SECTION 10
# VALIDATION INDICATOR HARDENING
# ============================================================================


@pytest.mark.parametrize(
    "diagnostics",
    [
        {},
        {
            "risk_validation_passed": False,
        },
        {
            "risk_validation_passed": None,
        },
        {
            "risk_validation_passed": 1,
        },
        {
            "risk_validation_passed": 0,
        },
        {
            "risk_validation_passed": "True",
        },
        {
            "risk_validation_passed": "PASS",
        },
        {
            "risk_validation_result": {},
        },
        {
            "risk_validation_result": {
                "approved": False,
            },
        },
        {
            "risk_validation_result": {
                "passed": False,
            },
        },
    ],
)
def test_execution_gate_fails_closed(
    diagnostics: dict[str, Any],
) -> None:
    """
    Only explicit boolean-positive validation evidence may authorize
    execution.

    All ambiguous, missing, false, or malformed states must fail closed.
    """

    gate = ProductionExecutionGate()

    result = build_execution_result(
        diagnostics=diagnostics
    )

    authorization = gate.authorize(
        result
    )

    assert authorization.authorized is False

    assert authorization.risk_validation_passed is False

    assert authorization.status == (
        ExecutionAuthorizationStatus.REJECTED
    )


# ============================================================================
# SECTION 11
# HARD EXECUTION STOP
# ============================================================================


def test_require_authorization_rejects_failed_validation() -> None:
    """
    require_authorization() must provide the final hard stop.
    """

    gate = ProductionExecutionGate()

    result = build_execution_result(
        diagnostics={}
    )

    authorization = gate.authorize(
        result
    )

    assert authorization.authorized is False

    with pytest.raises(
        ProductionExecutionGateError
    ):
        gate.require_authorization(
            authorization
        )


def test_require_authorization_accepts_authorized_result() -> None:
    """
    A genuinely authorized execution result must pass the hard-stop
    boundary.
    """

    validation_result = (
        build_approved_validation_result()
    )

    gate = ProductionExecutionGate()

    result = build_execution_result(
        diagnostics={
            "risk_validation_result": (
                validation_result.to_dict()
            ),
        }
    )

    authorization = gate.authorize(
        result
    )

    assert authorization.authorized is True

    assert authorization.status == (
        ExecutionAuthorizationStatus.AUTHORIZED
    )

    gate.require_authorization(
        authorization
    )


# ============================================================================
# SECTION 12
# AUTHORIZATION INTEGRITY
# ============================================================================


def test_authorized_result_preserves_decision_identity() -> None:
    """
    Authorization must preserve the upstream decision identity.
    """

    validation_result = (
        build_approved_validation_result()
    )

    gate = ProductionExecutionGate()

    result = build_execution_result(
        diagnostics={
            "risk_validation_result": (
                validation_result.to_dict()
            ),
        }
    )

    authorization = gate.authorize(
        result
    )

    assert authorization.authorized is True

    assert authorization.decision_id == (
        result.decision_id
    )

    assert authorization.regime == (
        result.regime
    )

    assert authorization.weights == (
        result.weights
    )


def test_authorized_result_preserves_risk_values() -> None:
    """
    The execution authorization must not alter the validated portfolio
    risk values.
    """

    validation_result = (
        build_approved_validation_result()
    )

    gate = ProductionExecutionGate()

    result = build_execution_result(
        diagnostics={
            "risk_validation_result": (
                validation_result.to_dict()
            ),
        }
    )

    authorization = gate.authorize(
        result
    )

    assert authorization.authorized is True

    assert authorization.portfolio_volatility == pytest.approx(
        result.portfolio_volatility
    )

    assert authorization.portfolio_variance == pytest.approx(
        result.portfolio_variance
    )

    assert authorization.gross_exposure == pytest.approx(
        result.gross_exposure
    )

    assert authorization.net_exposure == pytest.approx(
        result.net_exposure
    )


# ============================================================================
# SECTION 13
# DETERMINISM
# ============================================================================


def test_risk_validation_is_deterministic() -> None:
    """
    Identical validation inputs must produce identical risk results.
    """

    first = (
        build_approved_validation_result()
    )

    second = (
        build_approved_validation_result()
    )

    assert first == second


def test_execution_authorization_is_deterministic() -> None:
    """
    Identical execution inputs must produce identical authorization
    results.
    """

    validation_result = (
        build_approved_validation_result()
    )

    diagnostics = {
        "risk_validation_result": (
            validation_result.to_dict()
        ),
    }

    gate_one = ProductionExecutionGate()

    gate_two = ProductionExecutionGate()

    result_one = build_execution_result(
        diagnostics=diagnostics
    )

    result_two = build_execution_result(
        diagnostics=diagnostics
    )

    authorization_one = gate_one.authorize(
        result_one
    )

    authorization_two = gate_two.authorize(
        result_two
    )

    assert authorization_one == (
        authorization_two
    )


# ============================================================================
# SECTION 14
# MASTER PHASE IV-D INVARIANTS
# ============================================================================


def test_phase_iv_d_master_fail_closed_invariant() -> None:
    """
    MASTER INVARIANT

    No positive risk-validation evidence
    =
    No execution authorization.
    """

    gate = ProductionExecutionGate()

    invalid_diagnostics = [
        {},
        {
            "risk_validation_passed": False,
        },
        {
            "risk_validation_passed": None,
        },
        {
            "risk_validation_passed": 1,
        },
        {
            "risk_validation_passed": "True",
        },
        {
            "risk_validation_result": {},
        },
        {
            "risk_validation_result": {
                "approved": False,
            },
        },
    ]

    for diagnostics in invalid_diagnostics:

        result = build_execution_result(
            diagnostics=diagnostics
        )

        authorization = gate.authorize(
            result
        )

        assert authorization.authorized is False

        assert authorization.status == (
            ExecutionAuthorizationStatus.REJECTED
        )

        assert authorization.risk_validation_passed is False


def test_phase_iv_d_master_success_invariant() -> None:
    """
    MASTER SUCCESS INVARIANT

    A compliant authoritative risk-validation result can be represented
    at the execution boundary and results in authorization.
    """

    validation_result = (
        build_approved_validation_result()
    )

    assert validation_result.approved is True

    assert validation_result.status == (
        ProductionRiskValidation.APPROVED
    )

    gate = ProductionExecutionGate()

    result = build_execution_result(
        diagnostics={
            "risk_validation_result": (
                validation_result.to_dict()
            ),
        }
    )

    authorization = gate.authorize(
        result
    )

    assert authorization.authorized is True

    assert authorization.status == (
        ExecutionAuthorizationStatus.AUTHORIZED
    )

    assert authorization.risk_validation_passed is True


# ============================================================================
# SECTION 15
# HEALTH / METADATA
# ============================================================================


def test_production_risk_validation_health() -> None:
    """
    The validator must remain healthy before and after validation.
    """

    validator = build_validator()

    assert validator.health_check() is True

    result = (
        build_approved_validation_result()
    )

    assert result.approved is True

    assert validator.health_check() is True


def test_production_execution_gate_health() -> None:
    """
    The execution gate must report healthy under the existing production
    policy.
    """

    gate = ProductionExecutionGate()

    health = gate.health_check()

    assert isinstance(
        health,
        dict,
    )

    assert health["healthy"] is True


# ============================================================================
# SECTION 16
# TEST ENTRY POINT
# ============================================================================


if __name__ == "__main__":
    raise SystemExit(
        pytest.main(
            [
                __file__,
                "-q",
            ]
        )
    )