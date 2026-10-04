
"""
Phase 5F.8 — Kill Switch / AlertEngine integration tests.

Validates that certified Kill Switch OperationalEvents can be consumed
by AlertEngine without coupling the Kill Switch to notification logic.

Architecture:

    KillSwitch
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

The Kill Switch remains an operational safety control and does not
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
from killswitch import KillSwitch
from operationalevent import (
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
# ACTIVATION
# ======================================================================


def test_kill_switch_activation_generates_alert(
    tmp_path: Path,
) -> None:
    """
    A real Kill Switch activation event must be accepted by AlertEngine
    and produce a notification.
    """

    switch = KillSwitch()

    event = switch.activate(
        "Emergency risk condition"
    )

    engine, transport, audit_trail = _build_engine(
        tmp_path
    )

    result = engine.process(event)

    assert event.event_type == (
        OperationalEventType.KILL_SWITCH_ACTIVATED
    )

    assert event.severity == (
        OperationalSeverity.CRITICAL
    )

    assert event.source == (
        OperationalSource.KILL_SWITCH
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
# RELEASE
# ======================================================================


def test_kill_switch_release_generates_alert(
    tmp_path: Path,
) -> None:
    """
    A normal Kill Switch release event has WARNING severity
    and must therefore be alerted under the default AlertPolicy.
    """

    switch = KillSwitch()

    switch.activate(
        "Temporary emergency"
    )

    event = switch.release(
        "Risk condition cleared"
    )

    engine, transport, audit_trail = _build_engine(
        tmp_path
    )

    result = engine.process(event)

    assert event.event_type == (
        OperationalEventType.KILL_SWITCH_RELEASED
    )

    assert event.severity == (
        OperationalSeverity.WARNING
    )

    assert event.source == (
        OperationalSource.KILL_SWITCH
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
# IDEMPOTENT ACTIVATION
# ======================================================================


def test_idempotent_activation_produces_independent_events(
    tmp_path: Path,
) -> None:
    """
    Repeated activation is state-idempotent but each returned
    OperationalEvent has its own event identity.

    AlertEngine must process both unique events independently.
    """

    switch = KillSwitch()

    first = switch.activate(
        "First activation"
    )

    second = switch.activate(
        "Repeated activation"
    )

    assert first.event_id != second.event_id

    assert first.event_type == (
        OperationalEventType.KILL_SWITCH_ACTIVATED
    )

    assert second.event_type == (
        OperationalEventType.KILL_SWITCH_ACTIVATED
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
# IDEMPOTENT RELEASE
# ======================================================================


def test_idempotent_release_is_suppressed_but_audited(
    tmp_path: Path,
) -> None:
    """
    Releasing an already-released Kill Switch generates an INFO event.

    The default AlertPolicy does not alert on INFO, so the notification
    must be suppressed while the operational event is still audited.
    """

    switch = KillSwitch()

    event = switch.release(
        "Already clear"
    )

    assert event.event_type == (
        OperationalEventType.KILL_SWITCH_RELEASED
    )

    assert event.severity == (
        OperationalSeverity.INFO
    )

    assert event.source == (
        OperationalSource.KILL_SWITCH
    )

    assert event.metadata["idempotent"] is True

    engine, transport, audit_trail = _build_engine(
        tmp_path
    )

    result = engine.process(event)

    assert result.status == AlertStatus.SUPPRESSED

    assert len(
        transport.sent_notifications
    ) == 1

    suppressed_notification = (
        transport.sent_notifications[0]
    )

    assert (
        suppressed_notification.event_id
    == event.event_id
    )

    assert suppressed_notification.attempted is False

    assert suppressed_notification.delivered is False

    assert suppressed_notification.error == (
    "ALERT_SUPPRESSED"
    )

    assert audit_trail.count() == 1

# ======================================================================
# DUPLICATE EVENT PROTECTION
# ======================================================================


def test_duplicate_kill_switch_event_is_not_notified_twice(
    tmp_path: Path,
) -> None:
    """
    The exact same OperationalEvent must only generate one notification
    and one AuditTrail record.
    """

    switch = KillSwitch()

    event = switch.activate(
        "Duplicate protection test"
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
# FULL LIFECYCLE
# ======================================================================


def test_kill_switch_alert_lifecycle(
    tmp_path: Path,
) -> None:
    """
    Validate the complete operational notification lifecycle:

        RELEASED
            |
            v
        activate()
            |
            v
        CRITICAL KILL_SWITCH_ACTIVATED
            |
            v
        AlertEngine -> SENT
            |
            v
        release()
            |
            v
        WARNING KILL_SWITCH_RELEASED
            |
            v
        AlertEngine -> SENT
    """

    switch = KillSwitch()

    engine, transport, audit_trail = _build_engine(
        tmp_path
    )

    assert switch.is_active() is False

    activation_event = switch.activate(
        "Full lifecycle emergency"
    )

    assert switch.is_active() is True

    activation_result = engine.process(
        activation_event
    )

    assert activation_result.status == (
        AlertStatus.SENT
    )

    release_event = switch.release(
        "Full lifecycle recovery"
    )

    assert switch.is_active() is False

    release_result = engine.process(
        release_event
    )

    assert release_result.status == (
        AlertStatus.SENT
    )

    assert len(
        transport.sent_notifications
    ) == 2

    assert [
        notification.event_id
        for notification in transport.sent_notifications
    ] == [
        activation_event.event_id,
        release_event.event_id,
    ]

    assert audit_trail.count() == 2


# ======================================================================
# ARCHITECTURAL BOUNDARY
# ======================================================================


def test_alert_engine_does_not_control_kill_switch_state(
    tmp_path: Path,
) -> None:
    """
    AlertEngine must consume Kill Switch events without acquiring
    responsibility for Kill Switch state transitions.
    """

    switch = KillSwitch()

    event = switch.activate(
        "Boundary test"
    )

    engine, _, _ = _build_engine(
        tmp_path
    )

    assert switch.is_active() is True

    result = engine.process(event)

    assert result.status == AlertStatus.SENT

    # Processing the event must not release or otherwise mutate
    # Kill Switch state.
    assert switch.is_active() is True

    assert switch.activation_count == 1

    assert switch.release_count == 0


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
