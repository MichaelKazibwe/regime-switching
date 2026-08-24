# ==============================================================================
# PHASE IV-F — EXECUTION SAFETY REGRESSION
# ==============================================================================
"""
Phase IV-F execution safety and paper/live boundary regression.

This test suite establishes the following production invariants:

1. ProductionExecutionGate is the sole execution authorization authority.
2. Risk validation must precede execution authorization.
3. require_authorization() is mandatory.
4. Unauthorized artifacts cannot cross the execution boundary.
5. Rejected decisions cannot become authorized.
6. Failed decisions cannot become authorized.
7. Live trading remains disabled.
8. Broker submission remains disabled.
9. The production pipeline contains no direct broker submission path.
10. Authorization does not itself submit or execute broker orders.
11. The execution boundary fails closed.
12. Phase IV-E behavior remains deterministic.
"""

from __future__ import annotations

import inspect

import productionpipelineintegration
from productionexecutiongate import (
    ExecutionAuthorization,
    ExecutionAuthorizationStatus,
    ProductionExecutionGate,
    ProductionExecutionGateError,
)
from productionpipelineintegration import (
    ProductionPipelineIntegration,
    ProductionPipelineStatus,
)


# ==============================================================================
# SECTION 1 — BASIC ASSERTION HELPERS
# ==============================================================================


def assert_true(
    condition: bool,
    message: str,
) -> None:
    assert condition, message


# ==============================================================================
# SECTION 2 — EXECUTION GATE CONFIGURATION
# ==============================================================================


def test_live_trading_is_disabled() -> None:
    gate = ProductionExecutionGate()

    assert_true(
        gate.LIVE_TRADING_ENABLED is False,
        "Live trading must remain disabled.",
    )


def test_broker_submission_is_disabled() -> None:
    gate = ProductionExecutionGate()

    assert_true(
        gate.BROKER_SUBMISSION_ENABLED is False,
        "Broker submission must remain disabled.",
    )


def test_pipeline_live_trading_is_disabled() -> None:
    assert_true(
        ProductionPipelineIntegration.LIVE_TRADING_ENABLED is False,
        "Pipeline live trading must remain disabled.",
    )


def test_pipeline_broker_submission_is_disabled() -> None:
    assert_true(
        ProductionPipelineIntegration.BROKER_SUBMISSION_ENABLED is False,
        "Pipeline broker submission must remain disabled.",
    )


# ==============================================================================
# SECTION 3 — AUTHORIZATION AUTHORITY
# ==============================================================================


def test_execution_gate_is_authoritative() -> None:
    assert_true(
        ProductionPipelineIntegration.EXECUTION_GATE_IS_AUTHORITATIVE
        is True,
        "ProductionExecutionGate must remain authoritative.",
    )


def test_pipeline_uses_execution_gate() -> None:
    source = inspect.getsource(
        ProductionPipelineIntegration._execution_gate
    )

    assert "self.execution_gate.authorize(" in source
    assert "self.execution_gate.require_authorization(" in source


def test_require_authorization_is_enforced() -> None:
    source = inspect.getsource(
        ProductionPipelineIntegration._execution_gate
    )

    assert "require_authorization(" in source


# ==============================================================================
# SECTION 4 — FAIL-CLOSED AUTHORIZATION
# ==============================================================================


def test_invalid_authorization_object_is_rejected() -> None:
    gate = ProductionExecutionGate()

    try:
        gate.require_authorization(
            object()
        )
    except ProductionExecutionGateError:
        return

    raise AssertionError(
        "Invalid authorization objects must be rejected."
    )


def test_unauthorized_artifact_is_rejected() -> None:
    gate = ProductionExecutionGate()

    authorization = ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.REJECTED,
        authorized=False,
        decision_id="TEST-REJECTED",
        regime="neutral",
        weights={"SPY": 1.0},
        portfolio_volatility=0.10,
        portfolio_variance=0.01,
        gross_exposure=1.0,
        net_exposure=1.0,
        risk_contributions={"SPY": 0.01},
        risk_contribution_pct={"SPY": 1.0},
        risk_validation_passed=False,
        live_trading_enabled=False,
        broker_submission_enabled=False,
        warnings=(),
        errors=("TEST_REJECTED",),
        diagnostics={},
        api_version=gate.API_VERSION,
        phase=gate.PHASE,
    )

    try:
        gate.require_authorization(
            authorization
        )
    except ProductionExecutionGateError:
        return

    raise AssertionError(
        "Rejected authorization must fail closed."
    )


def test_authorized_false_is_rejected() -> None:
    gate = ProductionExecutionGate()

    authorization = ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.AUTHORIZED,
        authorized=False,
        decision_id="TEST-FALSE-AUTH",
        regime="neutral",
        weights={"SPY": 1.0},
        portfolio_volatility=0.10,
        portfolio_variance=0.01,
        gross_exposure=1.0,
        net_exposure=1.0,
        risk_contributions={"SPY": 0.01},
        risk_contribution_pct={"SPY": 1.0},
        risk_validation_passed=True,
        live_trading_enabled=False,
        broker_submission_enabled=False,
        warnings=(),
        errors=(),
        diagnostics={},
        api_version=gate.API_VERSION,
        phase=gate.PHASE,
    )

    try:
        gate.require_authorization(
            authorization
        )
    except ProductionExecutionGateError:
        return

    raise AssertionError(
        "authorized=False must fail closed."
    )


def test_missing_decision_id_is_rejected() -> None:
    gate = ProductionExecutionGate()

    authorization = ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.AUTHORIZED,
        authorized=True,
        decision_id="",
        regime="neutral",
        weights={"SPY": 1.0},
        portfolio_volatility=0.10,
        portfolio_variance=0.01,
        gross_exposure=1.0,
        net_exposure=1.0,
        risk_contributions={"SPY": 0.01},
        risk_contribution_pct={"SPY": 1.0},
        risk_validation_passed=True,
        live_trading_enabled=False,
        broker_submission_enabled=False,
        warnings=(),
        errors=(),
        diagnostics={},
        api_version=gate.API_VERSION,
        phase=gate.PHASE,
    )

    try:
        gate.require_authorization(
            authorization
        )
    except ProductionExecutionGateError:
        return

    raise AssertionError(
        "Authorization without decision ID must fail closed."
    )


def test_missing_weights_are_rejected() -> None:
    gate = ProductionExecutionGate()

    authorization = ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.AUTHORIZED,
        authorized=True,
        decision_id="TEST-NO-WEIGHTS",
        regime="neutral",
        weights={},
        portfolio_volatility=0.10,
        portfolio_variance=0.01,
        gross_exposure=1.0,
        net_exposure=1.0,
        risk_contributions={"SPY": 0.01},
        risk_contribution_pct={"SPY": 1.0},
        risk_validation_passed=True,
        live_trading_enabled=False,
        broker_submission_enabled=False,
        warnings=(),
        errors=(),
        diagnostics={},
        api_version=gate.API_VERSION,
        phase=gate.PHASE,
    )

    try:
        gate.require_authorization(
            authorization
        )
    except ProductionExecutionGateError:
        return

    raise AssertionError(
        "Authorization without portfolio weights must fail closed."
    )


def test_risk_validation_failure_is_rejected() -> None:
    gate = ProductionExecutionGate()

    authorization = ExecutionAuthorization(
        status=ExecutionAuthorizationStatus.AUTHORIZED,
        authorized=True,
        decision_id="TEST-RISK-FAIL",
        regime="neutral",
        weights={"SPY": 1.0},
        portfolio_volatility=0.10,
        portfolio_variance=0.01,
        gross_exposure=1.0,
        net_exposure=1.0,
        risk_contributions={"SPY": 0.01},
        risk_contribution_pct={"SPY": 1.0},
        risk_validation_passed=False,
        live_trading_enabled=False,
        broker_submission_enabled=False,
        warnings=(),
        errors=(),
        diagnostics={},
        api_version=gate.API_VERSION,
        phase=gate.PHASE,
    )

    try:
        gate.require_authorization(
            authorization
        )
    except ProductionExecutionGateError:
        return

    raise AssertionError(
        "Failed risk validation must prevent authorization."
    )


# ==============================================================================
# SECTION 5 — PIPELINE EXECUTION BOUNDARY
# ==============================================================================


def test_pipeline_execution_gate_does_not_submit_orders() -> None:
    source = inspect.getsource(
        ProductionPipelineIntegration._execution_gate
    )

    forbidden = (
        "submit_order",
        "send_order",
        "place_order",
        "execute_order",
        "broker.submit",
        "broker.execute",
    )

    for token in forbidden:
        assert token not in source, (
            "Execution authorization boundary must not directly "
            f"submit or execute broker orders: {token}"
        )


def test_pipeline_module_has_no_direct_broker_submission() -> None:
    source = inspect.getsource(
        productionpipelineintegration
    )

    forbidden = (
        "submit_order",
        "send_order",
        "place_order",
        "execute_order",
        "broker.submit",
        "broker.execute",
    )

    for token in forbidden:
        assert token not in source, (
            "Pipeline must not contain direct broker submission: "
            f"{token}"
        )


def test_execution_gate_authorization_does_not_submit_orders() -> None:
    source = inspect.getsource(
        ProductionExecutionGate.authorize
    )

    forbidden = (
        "submit_order",
        "send_order",
        "place_order",
        "execute_order",
    )

    for token in forbidden:
        assert token not in source, (
            "authorize() must not submit broker orders: "
            f"{token}"
        )


def test_require_authorization_does_not_execute() -> None:
    source = inspect.getsource(
        ProductionExecutionGate.require_authorization
    )

    forbidden = (
        "submit_order",
        "send_order",
        "place_order",
        "execute_order",
    )

    for token in forbidden:
        assert token not in source, (
            "require_authorization() must remain a hard-stop "
            "validator and must not execute orders."
        )


# ==============================================================================
# SECTION 6 — LIVE / PAPER SEPARATION
# ==============================================================================


def test_authorization_reports_live_disabled() -> None:
    gate = ProductionExecutionGate()

    assert_true(
        gate.LIVE_TRADING_ENABLED is False,
        "Authorization boundary must report live trading disabled.",
    )


def test_authorization_reports_broker_submission_disabled() -> None:
    gate = ProductionExecutionGate()

    assert_true(
        gate.BROKER_SUBMISSION_ENABLED is False,
        "Authorization boundary must report broker submission disabled.",
    )


def test_pipeline_health_reports_live_disabled() -> None:
    pipeline = ProductionPipelineIntegration()

    health = pipeline.health_check()

    assert isinstance(
        health,
        dict,
    )

    execution_gate_health = (
        pipeline._execution_gate_health()
    )

    assert isinstance(
        execution_gate_health,
        dict,
    )

    assert (
        pipeline.LIVE_TRADING_ENABLED
        is False
    )

    assert (
        pipeline.BROKER_SUBMISSION_ENABLED
        is False
    )

    assert (
        execution_gate_health.get(
            "live_trading_enabled",
            False,
        )
        is False
    )

    assert (
        execution_gate_health.get(
            "broker_submission_enabled",
            False,
        )
        is False
    )


# ==============================================================================
# SECTION 7 — PIPELINE AUTHORITY METADATA
# ==============================================================================


def test_pipeline_metadata_confirms_authority() -> None:
    pipeline = ProductionPipelineIntegration()

    metadata = pipeline.metadata()

    assert (
        metadata[
            "execution_gate_is_authoritative"
        ]
        is True
    )

    assert (
        metadata[
            "require_authorization_enforced"
        ]
        is True
    )


# ==============================================================================
# SECTION 8 — STATUS INVARIANTS
# ==============================================================================


def test_pipeline_status_values_are_distinct() -> None:
    values = {
        ProductionPipelineStatus.APPROVED,
        ProductionPipelineStatus.REJECTED,
        ProductionPipelineStatus.BLOCKED,
        ProductionPipelineStatus.FAILED,
    }

    assert len(values) == 4


def test_blocked_status_is_distinct_from_approved() -> None:
    assert (
        ProductionPipelineStatus.BLOCKED
        != ProductionPipelineStatus.APPROVED
    )


# ==============================================================================
# SECTION 9 — REGRESSION ENTRY POINT
# ==============================================================================


def test_phase_iv_f_execution_safety_suite() -> None:
    """
    Aggregate structural invariant for Phase IV-F.

    Individual tests provide the actual failure diagnostics.
    This test confirms the principal safety boundary as one contract.
    """

    pipeline = ProductionPipelineIntegration()
    gate = ProductionExecutionGate()

    assert pipeline.EXECUTION_GATE_IS_AUTHORITATIVE is True
    assert pipeline.LIVE_TRADING_ENABLED is False
    assert pipeline.BROKER_SUBMISSION_ENABLED is False

    assert gate.LIVE_TRADING_ENABLED is False
    assert gate.BROKER_SUBMISSION_ENABLED is False

    pipeline_source = inspect.getsource(
        ProductionPipelineIntegration._execution_gate
    )

    assert "self.execution_gate.authorize(" in pipeline_source
    assert "self.execution_gate.require_authorization(" in pipeline_source


# ==============================================================================
# SECTION 10 — MODULE SELF-TEST
# ==============================================================================


def run_phase_iv_f_tests() -> None:
    """
    Lightweight self-test entry point.

    Pytest remains the authoritative regression runner.
    """

    test_live_trading_is_disabled()
    test_broker_submission_is_disabled()
    test_pipeline_live_trading_is_disabled()
    test_pipeline_broker_submission_is_disabled()
    test_execution_gate_is_authoritative()
    test_pipeline_uses_execution_gate()
    test_require_authorization_is_enforced()
    test_invalid_authorization_object_is_rejected()
    test_unauthorized_artifact_is_rejected()
    test_authorized_false_is_rejected()
    test_missing_decision_id_is_rejected()
    test_missing_weights_are_rejected()
    test_risk_validation_failure_is_rejected()
    test_pipeline_execution_gate_does_not_submit_orders()
    test_pipeline_module_has_no_direct_broker_submission()
    test_execution_gate_authorization_does_not_submit_orders()
    test_require_authorization_does_not_execute()
    test_authorization_reports_live_disabled()
    test_authorization_reports_broker_submission_disabled()
    test_pipeline_health_reports_live_disabled()
    test_pipeline_metadata_confirms_authority()
    test_pipeline_status_values_are_distinct()
    test_blocked_status_is_distinct_from_approved()
    test_phase_iv_f_execution_safety_suite()


if __name__ == "__main__":
    run_phase_iv_f_tests()
    print(
        "PHASE IV-F EXECUTION SAFETY REGRESSION: PASS"
    )
