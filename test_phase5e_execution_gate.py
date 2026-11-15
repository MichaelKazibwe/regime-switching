"""
Phase 5E — Circuit Breaker / ProductionExecutionGate Integration.

Verifies that the CircuitBreaker is a veto inside the existing
ProductionExecutionGate and does not become a second execution
authority.
"""

import pytest

from circuitbreaker import CircuitBreaker
from killswitch import KillSwitch

from productionexecutiongate import (
    ExecutionAuthorizationStatus,
    ProductionExecutionGate,
    ProductionExecutionGateError,
)


def _approved_result():
    """
    Construct a genuinely execution-authorizable production result.

    This reuses the certified Phase IV-D construction path and attaches
    the authoritative positive risk-validation evidence required by
    ProductionExecutionGate.
    """

    from test_phase_iv_d_production_gate import (
        build_approved_validation_result,
        build_execution_result,
    )

    validation_result = build_approved_validation_result()

    assert validation_result.approved is True

    result = build_execution_result(
        diagnostics={
            "risk_validation_result": (
                validation_result.to_dict()
            ),
        },
    )

    assert result.status == "APPROVED"
    assert result.approved is True
    assert result.success is True
    assert result.decision_id

    return result


def test_default_gate_has_closed_circuit_breaker():
    gate = ProductionExecutionGate()

    assert isinstance(
        gate.circuit_breaker,
        CircuitBreaker,
    )

    assert gate.circuit_breaker.is_open() is False


def test_default_gate_has_released_kill_switch():
    gate = ProductionExecutionGate()

    assert isinstance(
        gate.kill_switch,
        KillSwitch,
    )

    assert gate.kill_switch.is_active() is False


def test_closed_circuit_does_not_block_by_itself():
    gate = ProductionExecutionGate()

    assert gate.circuit_breaker.is_open() is False

    health = gate.health_check()

    assert health["circuit_breaker_open"] is False


def test_open_circuit_is_reported_as_execution_block():
    gate = ProductionExecutionGate()

    gate.circuit_breaker.open(
        "PHASE5E_TEST"
    )

    health = gate.health_check()

    assert health["circuit_breaker_open"] is True
    assert health["execution_blocked"] is True


def test_metadata_reports_circuit_breaker():
    gate = ProductionExecutionGate()

    metadata = gate.metadata()

    assert metadata["circuit_breaker_enabled"] is True
    assert metadata["circuit_breaker_phase"] == "5E"
    assert metadata["circuit_breaker_open"] is False


def test_summary_reports_circuit_breaker():
    gate = ProductionExecutionGate()

    summary = gate.summary()

    assert summary["circuit_breaker_open"] is False
    assert summary["execution_blocked"] is False


def test_open_circuit_rejects_approved_result():
    gate = ProductionExecutionGate()

    result = _approved_result()

    gate.circuit_breaker.open(
        "PHASE5E_EXECUTION_BLOCK"
    )

    authorization = gate.authorize(
        result
    )

    assert (
        authorization.status
        == ExecutionAuthorizationStatus.REJECTED
    )

    assert authorization.authorized is False

    assert (
        "PHASE_5E_CIRCUIT_BREAKER_OPEN"
        in authorization.errors
    )

    assert (
        authorization.diagnostics[
            "circuit_breaker_open"
        ]
        is True
    )


def test_open_circuit_hard_stops_authorization():
    gate = ProductionExecutionGate()

    result = _approved_result()

    gate.circuit_breaker.open(
        "PHASE5E_HARD_STOP"
    )

    authorization = gate.authorize(
        result
    )

    with pytest.raises(
        ProductionExecutionGateError
    ):
        gate.require_authorization(
            authorization
        )


def test_reset_circuit_restores_gate_state():
    gate = ProductionExecutionGate()

    gate.circuit_breaker.open(
        "PHASE5E_RESET_TEST"
    )

    assert gate.circuit_breaker.is_open() is True

    gate.circuit_breaker.reset(
        "PHASE5E_OPERATOR_RESET"
    )

    assert gate.circuit_breaker.is_open() is False

    health = gate.health_check()

    assert health["circuit_breaker_open"] is False


def test_kill_switch_and_circuit_breaker_are_independent():
    gate = ProductionExecutionGate()

    gate.circuit_breaker.open(
        "PHASE5E_INDEPENDENCE"
    )

    assert gate.kill_switch.is_active() is False
    assert gate.circuit_breaker.is_open() is True

    gate.circuit_breaker.reset(
        "PHASE5E_INDEPENDENCE_RESET"
    )

    gate.kill_switch.activate(
        "PHASE5D_INDEPENDENCE"
    )

    assert gate.kill_switch.is_active() is True
    assert gate.circuit_breaker.is_open() is False


def test_circuit_breaker_does_not_create_execution_artifacts():
    gate = ProductionExecutionGate()

    gate.circuit_breaker.open(
        "PHASE5E_NO_EXECUTION"
    )

    assert not hasattr(
        gate.circuit_breaker,
        "order",
    )

    assert not hasattr(
        gate.circuit_breaker,
        "broker",
    )

    assert not hasattr(
        gate.circuit_breaker,
        "oms",
    )

    assert not hasattr(
        gate.circuit_breaker,
        "execution_engine",
    )