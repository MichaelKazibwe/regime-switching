"""
Phase 5F.9 — Circuit Breaker / AlertEngine integration tests.

Validates that certified Circuit Breaker OperationalEvents can be
consumed by AlertEngine without coupling the Circuit Breaker to
notification logic.

Architecture:

    CircuitBreaker
        |
        | OperationalEvent
        v
    AlertEngine
        |
        +--> AlertPolicy
        |
        +--> NotificationTransport
        |
        +--> OperationalAuditTrail

The Circuit Breaker remains an operational safety control and does not
delegate execution authority to AlertEngine.
"""

from __future__ import annotations

from pathlib import Path

from alertengine import (
    AlertEngine,
    AlertStatus,
    InMemoryNotificationTransport,
)
from audittrail import OperationalAuditTrail
from circuitbreaker import CircuitBreaker
from operationalevent import (
    OperationalEvent,
    OperationalEventType,
    OperationalSeverity,
    OperationalSource,
)


def _build_engine(
    tmp_path: Path,
) -> tuple[
    AlertEngine,
    InMemoryNotificationTransport,
    OperationalAuditTrail,
]:
    """Build a deterministic AlertEngine integration fixture."""

    audit_trail = OperationalAuditTrail(
        tmp_path / "audit.jsonl"
    )

    transport = InMemoryNotificationTransport()

    engine = AlertEngine(
        transport=transport,
        default_recipient="ops@example.com",
        audit_trail=audit_trail,
    )

    return engine, transport, audit_trail


# ======================================================================
# THRESHOLD-TRIGGERED OPEN
# ======================================================================


def test_circuit_breaker_open_generates_alert(
    tmp_path: Path,
) -> None:
    """
    A threshold-triggered Circuit Breaker OPEN event must be accepted
    by AlertEngine and produce a notification.
    """

    breaker = CircuitBreaker(threshold=2)

    breaker.record_failure("FAILURE_1")

    event = breaker.record_failure(
        "FAILURE_2"
    )

    engine, transport, audit_trail = _build_engine(
        tmp_path
    )

    result = engine.process(event)

    assert isinstance(
        event,
        OperationalEvent,
    )

    assert event.event_type == (
        OperationalEventType.CIRCUIT_BREAKER_OPENED
    )

    assert event.severity == (
        OperationalSeverity.CRITICAL
    )

    assert event.source == (
        OperationalSource.CIRCUIT_BREAKER
    )

    assert result.status == AlertStatus.SENT

    assert len(
        transport.sent_notifications
    ) == 1

    assert (
        transport.sent_notifications[0].event_id
        == event.event_id
    )

    assert audit_trail.count() == 1


# ======================================================================
# EXPLICIT OPEN
# ======================================================================


def test_explicit_circuit_breaker_open_generates_alert(
    tmp_path: Path,
) -> None:
    """
    An explicit Circuit Breaker OPEN transition must generate an
    alert and an AuditTrail record.
    """

    breaker = CircuitBreaker(
        threshold=10
    )

    event = breaker.open(
        "MANUAL_OPERATIONAL_BLOCK"
    )

    engine, transport, audit_trail = _build_engine(
        tmp_path
    )

    result = engine.process(event)

    assert event.event_type == (
        OperationalEventType.CIRCUIT_BREAKER_OPENED
    )

    assert event.severity == (
        OperationalSeverity.CRITICAL
    )

    assert event.source == (
        OperationalSource.CIRCUIT_BREAKER
    )

    assert result.status == AlertStatus.SENT

    assert len(
        transport.sent_notifications
    ) == 1

    assert (
        transport.sent_notifications[0].event_id
        == event.event_id
    )

    assert audit_trail.count() == 1


# ======================================================================
# IDEMPOTENT OPEN
# ======================================================================


def test_idempotent_open_generates_independent_alert(
    tmp_path: Path,
) -> None:
    """
    Repeated OPEN requests are state-idempotent, but each returned
    OperationalEvent has an independent event identity.

    The idempotent OPEN event is WARNING severity, which is alert-worthy
    under the default AlertPolicy.
    """

    breaker = CircuitBreaker()

    first = breaker.open(
        "FIRST_OPEN"
    )

    second = breaker.open(
        "SECOND_OPEN"
    )

    assert first.event_id != second.event_id

    assert first.event_type == (
        OperationalEventType.CIRCUIT_BREAKER_OPENED
    )

    assert second.event_type == (
        OperationalEventType.CIRCUIT_BREAKER_OPENED
    )

    assert first.severity == (
        OperationalSeverity.CRITICAL
    )

    assert second.severity == (
        OperationalSeverity.WARNING
    )

    assert second.metadata["idempotent"] is True

    engine, transport, audit_trail = _build_engine(
        tmp_path
    )

    first_result = engine.process(first)

    second_result = engine.process(second)

    assert first_result.status == AlertStatus.SENT

    assert second_result.status == AlertStatus.SENT

    assert len(
        transport.sent_notifications
    ) == 2

    assert {
        notification.event_id
        for notification in transport.sent_notifications
    } == {
        first.event_id,
        second.event_id,
    }

    assert audit_trail.count() == 2


# ======================================================================
# RESET / CLOSE
# ======================================================================


def test_circuit_breaker_reset_generates_alert(
    tmp_path: Path,
) -> None:
    """
    A normal OPEN -> CLOSED reset produces a WARNING event.

    WARNING is alert-worthy under the default AlertPolicy, so the
    recovery transition must generate a notification.
    """

    breaker = CircuitBreaker(
        threshold=1
    )

    breaker.record_failure(
        "BLOCKING_FAILURE"
    )

    event = breaker.reset(
        "OPERATOR_RESET"
    )

    engine, transport, audit_trail = _build_engine(
        tmp_path
    )

    result = engine.process(event)

    assert event.event_type == (
        OperationalEventType.CIRCUIT_BREAKER_CLOSED
    )

    assert event.severity == (
        OperationalSeverity.WARNING
    )

    assert event.source == (
        OperationalSource.CIRCUIT_BREAKER
    )

    assert result.status == AlertStatus.SENT

    assert len(
        transport.sent_notifications
    ) == 1

    assert (
        transport.sent_notifications[0].event_id
        == event.event_id
    )

    assert audit_trail.count() == 1


# ======================================================================
# IDEMPOTENT RESET
# ======================================================================


def test_idempotent_reset_is_suppressed_but_audited(
    tmp_path: Path,
) -> None:
    """
    Resetting an already-CLOSED Circuit Breaker produces an INFO event.

    INFO is not alert-worthy under the default AlertPolicy, so the
    notification must be suppressed while the event is still audited.
    """

    breaker = CircuitBreaker()

    event = breaker.reset(
        "NOOP_RESET"
    )

    assert event.event_type == (
        OperationalEventType.CIRCUIT_BREAKER_CLOSED
    )

    assert event.severity == (
        OperationalSeverity.INFO
    )

    assert event.source == (
        OperationalSource.CIRCUIT_BREAKER
    )

    assert event.metadata["idempotent"] is True

    engine, transport, audit_trail = _build_engine(
        tmp_path
    )

    result = engine.process(event)

    assert result.status == AlertStatus.SUPPRESSED

    assert len(transport.sent_notifications) == 1
    assert transport.sent_notifications[0].status == AlertStatus.FAILED
    assert transport.sent_notifications[0].attempted is False
    assert transport.sent_notifications[0].delivered is False
    assert transport.sent_notifications[0].error == "ALERT_SUPPRESSED"

    assert audit_trail.count() == 1


# ======================================================================
# DUPLICATE EVENT PROTECTION
# ======================================================================


def test_duplicate_circuit_breaker_event_is_not_notified_twice(
    tmp_path: Path,
) -> None:
    """
    The exact same Circuit Breaker OperationalEvent must only generate
    one notification and one AuditTrail record.
    """

    breaker = CircuitBreaker(
        threshold=1
    )

    event = breaker.record_failure(
        "DUPLICATE_TEST"
    )

    engine, transport, audit_trail = _build_engine(
        tmp_path
    )

    first = engine.process(event)

    second = engine.process(event)

    assert first.status == AlertStatus.SENT

    assert second.status == AlertStatus.SUPPRESSED

    assert len(
        transport.sent_notifications
    ) == 1

    assert (
        transport.sent_notifications[0].event_id
        == event.event_id
    )

    assert audit_trail.count() == 1


# ======================================================================
# FULL OPEN -> CLOSE LIFECYCLE
# ======================================================================


def test_circuit_breaker_alert_lifecycle(
    tmp_path: Path,
) -> None:
    """
    Validate the complete operational notification lifecycle:

        CLOSED
            |
            v
        threshold reached
            |
            v
        CRITICAL CIRCUIT_BREAKER_OPENED
            |
            v
        AlertEngine -> SENT
            |
            v
        reset()
            |
            v
        WARNING CIRCUIT_BREAKER_CLOSED
            |
            v
        AlertEngine -> SENT
    """

    breaker = CircuitBreaker(
        threshold=1
    )

    engine, transport, audit_trail = _build_engine(
        tmp_path
    )

    assert breaker.is_open() is False

    open_event = breaker.record_failure(
        "FULL_LIFECYCLE_FAILURE"
    )

    assert breaker.is_open() is True

    open_result = engine.process(
        open_event
    )

    assert open_result.status == (
        AlertStatus.SENT
    )

    close_event = breaker.reset(
        "FULL_LIFECYCLE_RECOVERY"
    )

    assert breaker.is_open() is False

    close_result = engine.process(
        close_event
    )

    assert close_result.status == (
        AlertStatus.SENT
    )

    assert len(
        transport.sent_notifications
    ) == 2

    assert [
        notification.event_id
        for notification in transport.sent_notifications
    ] == [
        open_event.event_id,
        close_event.event_id,
    ]

    assert audit_trail.count() == 2


# ======================================================================
# ARCHITECTURAL BOUNDARY
# ======================================================================


def test_alert_engine_does_not_control_circuit_breaker_state(
    tmp_path: Path,
) -> None:
    """
    AlertEngine must consume Circuit Breaker events without acquiring
    responsibility for Circuit Breaker state transitions.
    """

    breaker = CircuitBreaker(
        threshold=1
    )

    event = breaker.record_failure(
        "BOUNDARY_TEST"
    )

    engine, _, _ = _build_engine(
        tmp_path
    )

    assert breaker.is_open() is True

    result = engine.process(event)

    assert result.status == AlertStatus.SENT

    # Processing the event must not reset, reopen, or otherwise mutate
    # Circuit Breaker state.
    assert breaker.is_open() is True

    assert breaker.state().failure_count == 1


# ======================================================================
# RUN DIRECTLY
# ======================================================================


if __name__ == "__main__":
    import pytest

    raise SystemExit(
        pytest.main(
            [__file__, "-v"]
        )
    )