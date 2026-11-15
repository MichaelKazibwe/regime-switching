"""
Phase 5E — Circuit Breaker Regression Tests.

Standalone certification suite for the production CircuitBreaker.
"""

import pytest

from circuitbreaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerStateError,
)
from operationalevent import (
    OperationalEvent,
    OperationalEventType,
    OperationalSeverity,
    OperationalSource,
)


# ============================================================
# INITIAL STATE
# ============================================================

def test_initial_state_is_closed():
    breaker = CircuitBreaker()

    assert breaker.is_open() is False
    assert breaker.state().open is False
    assert breaker.state().failure_count == 0
    assert breaker.state().threshold == 5


def test_custom_threshold_is_preserved():
    breaker = CircuitBreaker(threshold=3)

    assert breaker.state().threshold == 3


def test_invalid_threshold_is_rejected():
    with pytest.raises(CircuitBreakerStateError):
        CircuitBreaker(threshold=0)

    with pytest.raises(CircuitBreakerStateError):
        CircuitBreaker(threshold=-1)

    with pytest.raises(CircuitBreakerStateError):
        CircuitBreaker(threshold=True)


# ============================================================
# FAILURE COUNTING
# ============================================================

def test_failure_increments_counter():
    breaker = CircuitBreaker(threshold=3)

    breaker.record_failure("TEST_FAILURE")

    assert breaker.is_open() is False
    assert breaker.state().failure_count == 1
    assert breaker.state().last_failure_reason == "TEST_FAILURE"


def test_failure_below_threshold_does_not_open():
    breaker = CircuitBreaker(threshold=3)

    breaker.record_failure("FAILURE_1")
    breaker.record_failure("FAILURE_2")

    assert breaker.is_open() is False
    assert breaker.state().failure_count == 2


def test_threshold_failure_opens_circuit():
    breaker = CircuitBreaker(threshold=3)

    breaker.record_failure("FAILURE_1")
    breaker.record_failure("FAILURE_2")
    event = breaker.record_failure("FAILURE_3")

    assert breaker.is_open() is True
    assert breaker.state().failure_count == 3
    assert event.event_type == OperationalEventType.CIRCUIT_BREAKER_OPENED
    assert event.severity == OperationalSeverity.CRITICAL
    assert event.source == OperationalSource.CIRCUIT_BREAKER


# ============================================================
# SUCCESS / RECOVERY SEMANTICS
# ============================================================

def test_success_resets_closed_failure_counter():
    breaker = CircuitBreaker(threshold=3)

    breaker.record_failure("FAILURE_1")
    breaker.record_failure("FAILURE_2")

    assert breaker.state().failure_count == 2

    breaker.record_success()

    assert breaker.is_open() is False
    assert breaker.state().failure_count == 0
    assert breaker.state().last_failure_at is None
    assert breaker.state().last_failure_reason is None


def test_success_does_not_automatically_close_open_circuit():
    breaker = CircuitBreaker(threshold=2)

    breaker.record_failure("FAILURE_1")
    breaker.record_failure("FAILURE_2")

    assert breaker.is_open() is True

    breaker.record_success()

    assert breaker.is_open() is True
    assert breaker.state().failure_count == 2


def test_open_circuit_remains_open_after_additional_failure():
    breaker = CircuitBreaker(threshold=1)

    breaker.record_failure("INITIAL_FAILURE")

    assert breaker.is_open() is True

    breaker.record_failure("ADDITIONAL_FAILURE")

    assert breaker.is_open() is True
    assert breaker.state().failure_count == 2


# ============================================================
# HARD EXECUTION BLOCK
# ============================================================

def test_require_closed_passes_when_closed():
    breaker = CircuitBreaker()

    breaker.require_closed()


def test_require_closed_blocks_when_open():
    breaker = CircuitBreaker(threshold=1)

    breaker.record_failure("BLOCKING_FAILURE")

    with pytest.raises(CircuitBreakerOpenError):
        breaker.require_closed()


# ============================================================
# EXPLICIT OPEN / RESET
# ============================================================

def test_explicit_open_blocks_circuit():
    breaker = CircuitBreaker(threshold=10)

    event = breaker.open("MANUAL_OPERATIONAL_BLOCK")

    assert breaker.is_open() is True
    assert breaker.state().opened_at is not None
    assert event.event_type == OperationalEventType.CIRCUIT_BREAKER_OPENED
    assert event.source == OperationalSource.CIRCUIT_BREAKER


def test_explicit_open_is_idempotent():
    breaker = CircuitBreaker()

    breaker.open("FIRST_OPEN")

    event = breaker.open("SECOND_OPEN")

    assert breaker.is_open() is True
    assert event.event_type == OperationalEventType.CIRCUIT_BREAKER_OPENED


def test_reset_closes_open_circuit():
    breaker = CircuitBreaker(threshold=1)

    breaker.record_failure("FAILURE")

    assert breaker.is_open() is True

    event = breaker.reset("OPERATOR_RESET")

    assert breaker.is_open() is False
    assert breaker.state().failure_count == 0
    assert breaker.state().opened_at is None
    assert breaker.state().last_failure_at is None
    assert breaker.state().last_failure_reason is None
    assert breaker.state().last_reset_at is not None
    assert event.event_type == OperationalEventType.CIRCUIT_BREAKER_CLOSED
    assert event.source == OperationalSource.CIRCUIT_BREAKER


def test_reset_is_idempotent_when_closed():
    breaker = CircuitBreaker()

    event = breaker.reset("NOOP_RESET")

    assert breaker.is_open() is False
    assert breaker.state().failure_count == 0
    assert event.event_type == OperationalEventType.CIRCUIT_BREAKER_CLOSED


def test_reset_allows_new_failure_cycle():
    breaker = CircuitBreaker(threshold=2)

    breaker.record_failure("FAILURE_1")
    breaker.record_failure("FAILURE_2")

    assert breaker.is_open() is True

    breaker.reset("RECOVERY_RESET")

    assert breaker.is_open() is False

    breaker.record_failure("NEW_FAILURE_1")

    assert breaker.is_open() is False
    assert breaker.state().failure_count == 1


# ============================================================
# OPERATIONAL EVENT CONTRACT
# ============================================================

def test_open_event_is_valid_operational_event():
    breaker = CircuitBreaker(threshold=1)

    event = breaker.record_failure("TEST_FAILURE")

    assert isinstance(event, OperationalEvent)
    assert event.event_type == OperationalEventType.CIRCUIT_BREAKER_OPENED
    assert event.severity == OperationalSeverity.CRITICAL
    assert event.source == OperationalSource.CIRCUIT_BREAKER


def test_close_event_is_valid_operational_event():
    breaker = CircuitBreaker(threshold=1)

    breaker.record_failure("TEST_FAILURE")
    event = breaker.reset("TEST_RESET")

    assert isinstance(event, OperationalEvent)
    assert event.event_type == OperationalEventType.CIRCUIT_BREAKER_CLOSED
    assert event.severity == OperationalSeverity.WARNING
    assert event.source == OperationalSource.CIRCUIT_BREAKER


def test_event_history_is_serializable():
    breaker = CircuitBreaker(threshold=2)

    breaker.record_failure("FAILURE_1")
    breaker.record_failure("FAILURE_2")

    payload = breaker.to_dict()

    assert isinstance(payload["event_history"], list)
    assert len(payload["event_history"]) >= 2


# ============================================================
# SERIALIZATION / RESTART
# ============================================================

def test_serialization_roundtrip():
    breaker = CircuitBreaker(threshold=3)

    breaker.record_failure("FAILURE_1")
    breaker.record_failure("FAILURE_2")

    payload = breaker.to_dict()

    restored = CircuitBreaker.from_dict(payload)

    assert restored.state() == breaker.state()
    assert restored.summary() == breaker.summary()
    assert restored.metadata() == breaker.metadata()


def test_open_state_survives_restart():
    breaker = CircuitBreaker(threshold=2)

    breaker.record_failure("FAILURE_1")
    breaker.record_failure("FAILURE_2")

    assert breaker.is_open() is True

    restored = CircuitBreaker.from_dict(
        breaker.to_dict()
    )

    assert restored.is_open() is True

    with pytest.raises(CircuitBreakerOpenError):
        restored.require_closed()


def test_closed_state_survives_restart():
    breaker = CircuitBreaker(threshold=3)

    breaker.record_failure("FAILURE_1")

    restored = CircuitBreaker.from_dict(
        breaker.to_dict()
    )

    assert restored.is_open() is False
    assert restored.state().failure_count == 1


# ============================================================
# FAIL-CLOSED RESTORATION
# ============================================================

def test_missing_api_version_is_rejected():
    breaker = CircuitBreaker()

    payload = breaker.to_dict()
    payload.pop("api_version")

    with pytest.raises(CircuitBreakerStateError):
        CircuitBreaker.from_dict(payload)


def test_invalid_api_version_is_rejected():
    breaker = CircuitBreaker()

    payload = breaker.to_dict()
    payload["api_version"] = "999.0.0"

    with pytest.raises(CircuitBreakerStateError):
        CircuitBreaker.from_dict(payload)


def test_invalid_phase_is_rejected():
    breaker = CircuitBreaker()

    payload = breaker.to_dict()
    payload["phase"] = "INVALID"

    with pytest.raises(CircuitBreakerStateError):
        CircuitBreaker.from_dict(payload)


def test_missing_state_is_rejected():
    breaker = CircuitBreaker()

    payload = breaker.to_dict()
    payload.pop("state")

    with pytest.raises(CircuitBreakerStateError):
        CircuitBreaker.from_dict(payload)


def test_negative_failure_count_is_rejected():
    breaker = CircuitBreaker()

    payload = breaker.to_dict()
    payload["state"]["failure_count"] = -1

    with pytest.raises(CircuitBreakerStateError):
        CircuitBreaker.from_dict(payload)


def test_zero_threshold_is_rejected():
    breaker = CircuitBreaker()

    payload = breaker.to_dict()
    payload["state"]["threshold"] = 0

    with pytest.raises(CircuitBreakerStateError):
        CircuitBreaker.from_dict(payload)


def test_open_state_without_timestamp_is_rejected():
    breaker = CircuitBreaker(threshold=1)

    breaker.record_failure("FAILURE")

    payload = breaker.to_dict()
    payload["state"]["opened_at"] = None

    with pytest.raises(CircuitBreakerStateError):
        CircuitBreaker.from_dict(payload)


def test_closed_state_with_open_timestamp_is_rejected():
    breaker = CircuitBreaker()

    payload = breaker.to_dict()
    payload["state"]["opened_at"] = "2026-01-01T00:00:00+00:00"

    with pytest.raises(CircuitBreakerStateError):
        CircuitBreaker.from_dict(payload)


def test_threshold_reached_but_closed_state_is_rejected():
    breaker = CircuitBreaker(threshold=2)

    payload = breaker.to_dict()
    payload["state"]["failure_count"] = 2

    with pytest.raises(CircuitBreakerStateError):
        CircuitBreaker.from_dict(payload)


def test_invalid_event_history_is_rejected():
    breaker = CircuitBreaker()

    payload = breaker.to_dict()
    payload["event_history"] = [
        {
            "invalid": "event",
        }
    ]

    with pytest.raises(
        (
            TypeError,
            ValueError,
            CircuitBreakerStateError,
        )
    ):
        CircuitBreaker.from_dict(payload)


# ============================================================
# HEALTH / METADATA
# ============================================================

def test_health_check():
    breaker = CircuitBreaker(threshold=3)

    health = breaker.health_check()

    assert health["healthy"] is True
    assert health["api_version"] == "1.0.0"
    assert health["phase"] == "5E"
    assert health["component"] == "CircuitBreaker"
    assert health["production_control"] is True
    assert health["execution_authority"] is False
    assert health["execution_blocked"] is False


def test_health_check_reports_open_block():
    breaker = CircuitBreaker(threshold=1)

    breaker.record_failure("FAILURE")

    health = breaker.health_check()

    assert health["healthy"] is True
    assert health["open"] is True
    assert health["execution_blocked"] is True


def test_metadata():
    breaker = CircuitBreaker(threshold=4)

    metadata = breaker.metadata()

    assert metadata["module"] == "circuitbreaker"
    assert metadata["component"] == "CircuitBreaker"
    assert metadata["api_version"] == "1.0.0"
    assert metadata["phase"] == "5E"
    assert metadata["production_control"] is True
    assert metadata["execution_authority"] is False
    assert metadata["automatic_recovery"] is False
    assert metadata["threshold"] == 4


# ============================================================
# EXECUTION BOUNDARY
# ============================================================

def test_circuit_breaker_does_not_create_execution_artifacts():
    breaker = CircuitBreaker(threshold=1)

    breaker.record_failure("TEST_FAILURE")

    assert not hasattr(breaker, "order")
    assert not hasattr(breaker, "broker")
    assert not hasattr(breaker, "oms")
    assert not hasattr(breaker, "execution_engine")
    assert not hasattr(breaker, "authorized_order")


def test_circuit_breaker_has_no_execution_authority():
    breaker = CircuitBreaker()

    metadata = breaker.metadata()

    assert metadata["execution_authority"] is False


# ============================================================
# FULL LIFECYCLE
# ============================================================

def test_full_lifecycle():
    breaker = CircuitBreaker(threshold=2)

    # Initial state.
    assert breaker.is_open() is False

    # First failure.
    breaker.record_failure("FAILURE_1")

    assert breaker.is_open() is False
    assert breaker.state().failure_count == 1

    # Second failure opens circuit.
    breaker.record_failure("FAILURE_2")

    assert breaker.is_open() is True

    # Execution must be blocked.
    with pytest.raises(CircuitBreakerOpenError):
        breaker.require_closed()

    # Persist and restart.
    restored = CircuitBreaker.from_dict(
        breaker.to_dict()
    )

    assert restored.is_open() is True

    # Explicit recovery.
    restored.reset("FULL_LIFECYCLE_RESET")

    assert restored.is_open() is False
    assert restored.state().failure_count == 0

    # Execution boundary is clear again.
    restored.require_closed()

    # New failure cycle works.
    restored.record_failure("NEW_FAILURE")

    assert restored.is_open() is False
    assert restored.state().failure_count == 1