"""
======================================================================
test_phase5h_restart_recovery.py

Phase 5H — Restart / State Recovery Contract Tests
======================================================================
"""

from __future__ import annotations

import copy

import pytest

from restartrecovery import RestartRecovery, RecoveryStatus


class _SerializableComponent:
    API_VERSION = "1.0.0"

    def __init__(self, value: int = 0) -> None:
        self.value = value

    def to_dict(self) -> dict:
        return {
            "api_version": self.API_VERSION,
            "state": {"value": self.value},
        }

    @classmethod
    def from_dict(cls, payload: dict):
        if payload.get("api_version") != cls.API_VERSION:
            raise ValueError("incompatible api_version")
        state = payload.get("state")
        if not isinstance(state, dict) or "value" not in state:
            raise ValueError("invalid persisted state")
        return cls(value=int(state["value"]))


class _FailingComponent(_SerializableComponent):
    @classmethod
    def from_dict(cls, payload: dict):
        raise ValueError("corrupted persisted state")


def test_recovery_restores_explicitly_registered_components() -> None:
    original = _SerializableComponent(value=42)
    recovery = RestartRecovery(
        components={"example": _SerializableComponent()},
    )

    result = recovery.restore(
        {"example": copy.deepcopy(original.to_dict())}
    )

    assert result.status == RecoveryStatus.RECOVERED
    assert result.healthy is True
    assert result.components["example"]["restored"] is True
    assert recovery.components["example"].value == 42


def test_recovery_requires_explicit_component_registration() -> None:
    recovery = RestartRecovery(components={})

    result = recovery.restore(
        {"unregistered": _SerializableComponent(value=7).to_dict()}
    )

    assert result.status == RecoveryStatus.FAILED
    assert result.healthy is False
    assert "unregistered" in result.failed_components


def test_corrupted_component_state_fails_closed() -> None:
    recovery = RestartRecovery(
        components={"example": _SerializableComponent()},
    )

    result = recovery.restore(
        {
            "example": {
                "api_version": "1.0.0",
                "state": {"unexpected": 123},
            }
        }
    )

    assert result.status == RecoveryStatus.FAILED
    assert result.healthy is False
    assert result.failed_components == ["example"]
    assert recovery.components["example"].value == 0


def test_component_restore_exception_fails_closed_without_mutation() -> None:
    recovery = RestartRecovery(
        components={"example": _FailingComponent(value=11)},
    )

    result = recovery.restore(
        {"example": _SerializableComponent(value=99).to_dict()}
    )

    assert result.status == RecoveryStatus.FAILED
    assert result.healthy is False
    assert result.failed_components == ["example"]
    assert recovery.components["example"].value == 11


def test_incompatible_api_version_is_rejected() -> None:
    recovery = RestartRecovery(
        components={"example": _SerializableComponent()},
    )

    result = recovery.restore(
        {
            "example": {
                "api_version": "999.0.0",
                "state": {"value": 42},
            }
        }
    )

    assert result.status == RecoveryStatus.FAILED
    assert result.healthy is False
    assert result.failed_components == ["example"]
    assert recovery.components["example"].value == 0


def test_recovery_is_idempotent_for_same_persisted_state() -> None:
    original = _SerializableComponent(value=42)
    payload = original.to_dict()

    recovery = RestartRecovery(
        components={"example": _SerializableComponent()},
    )

    first = recovery.restore(copy.deepcopy({"example": payload}))
    second = recovery.restore(copy.deepcopy({"example": payload}))

    assert first.status == RecoveryStatus.RECOVERED
    assert second.status == RecoveryStatus.RECOVERED
    assert recovery.components["example"].value == 42


def test_recovery_does_not_authorize_execution() -> None:
    recovery = RestartRecovery(
        components={"example": _SerializableComponent()},
    )

    result = recovery.restore(
        {"example": _SerializableComponent(value=42).to_dict()}
    )

    assert result.execution_authorized is False
    assert result.broker_submission_authorized is False
    assert result.decision_mutation_authorized is False


def test_empty_component_registry_is_unhealthy() -> None:
    recovery = RestartRecovery(components={})

    health = recovery.health_check()

    assert health["healthy"] is False
    assert health["component_count"] == 0


def test_health_check_reports_recovery_state() -> None:
    recovery = RestartRecovery(
        components={"example": _SerializableComponent()},
    )

    health_before = recovery.health_check()
    assert health_before["healthy"] is False

    recovery.restore(
        {"example": _SerializableComponent(value=42).to_dict()}
    )

    health_after = recovery.health_check()

    assert health_after["healthy"] is True
    assert health_after["component_count"] == 1


def test_recovery_result_has_operational_metadata() -> None:
    recovery = RestartRecovery(
        components={"example": _SerializableComponent()},
    )

    result = recovery.restore(
        {"example": _SerializableComponent(value=42).to_dict()}
    )

    assert result.api_version == "1.0.0"
    assert result.phase == "5H"
    assert result.component == "RestartRecovery"


def test_successful_recovery_emits_restart_and_recovery_events() -> None:
    from operationalevent import OperationalEventType

    recovery = RestartRecovery(
        components={"example": _SerializableComponent()},
    )

    result = recovery.restore(
        {"example": _SerializableComponent(value=42).to_dict()}
    )

    assert result.status == RecoveryStatus.RECOVERED

    events = recovery.event_history

    assert len(events) == 2
    assert events[0].event_type == OperationalEventType.SYSTEM_RESTART
    assert events[1].event_type == OperationalEventType.SYSTEM_RECOVERY

    assert events[0].metadata["status"] == "STARTED"
    assert events[1].metadata["status"] == "RECOVERED"


def test_failed_recovery_emits_restart_and_failed_recovery_events() -> None:
    from operationalevent import OperationalEventType

    recovery = RestartRecovery(
        components={"example": _SerializableComponent()},
    )

    result = recovery.restore(
        {
            "example": {
                "api_version": "999.0.0",
                "state": {"value": 42},
            }
        }
    )

    assert result.status == RecoveryStatus.FAILED

    events = recovery.event_history

    assert len(events) == 2
    assert events[0].event_type == OperationalEventType.SYSTEM_RESTART
    assert events[1].event_type == OperationalEventType.SYSTEM_RECOVERY

    assert events[0].metadata["status"] == "STARTED"
    assert events[1].metadata["status"] == "FAILED"


def test_recovery_events_use_system_source() -> None:
    from operationalevent import OperationalSource

    recovery = RestartRecovery(
        components={"example": _SerializableComponent()},
    )

    recovery.restore(
        {"example": _SerializableComponent(value=42).to_dict()}
    )

    assert all(
        event.source == OperationalSource.SYSTEM
        for event in recovery.event_history
    )


def test_recovery_event_history_is_serialized_operational_events() -> None:
    from operationalevent import OperationalEvent

    recovery = RestartRecovery(
        components={"example": _SerializableComponent()},
    )

    recovery.restore(
        {"example": _SerializableComponent(value=42).to_dict()}
    )

    assert all(
        isinstance(event, OperationalEvent)
        for event in recovery.event_history
    )


def test_failed_recovery_does_not_commit_component_state() -> None:
    recovery = RestartRecovery(
        components={
            "example": _SerializableComponent(value=11),
            "failing": _FailingComponent(value=22),
        },
    )

    result = recovery.restore(
        {
            "example": _SerializableComponent(value=99).to_dict(),
            "failing": _SerializableComponent(value=88).to_dict(),
        }
    )

    assert result.status == RecoveryStatus.FAILED

    # Transactional recovery: no component is committed when the
    # overall recovery attempt fails.
    assert recovery.components["example"].value == 11
    assert recovery.components["failing"].value == 22
