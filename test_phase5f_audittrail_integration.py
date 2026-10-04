"""
Phase 5F.7 — AlertEngine / OperationalAuditTrail integration tests.
"""

from __future__ import annotations

from unittest.mock import Mock

from audittrail import OperationalAuditTrail
from alertengine import (
    AlertEngine,
    AlertStatus,
    InMemoryNotificationTransport,
)
from operationalevent import (
    OperationalEvent,
    OperationalEventType,
    OperationalSeverity,
)


def make_event(
    *,
    event_id: str,
    severity: str,
    event_type: str,
    message: str,
) -> OperationalEvent:
    return OperationalEvent(
        event_id=event_id,
        event_type=event_type,
        severity=severity,
        source="SYSTEM",
        timestamp="2026-10-04T00:00:00+00:00",
        message=message,
    )


def test_alert_engine_audits_unique_event(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    trail = OperationalAuditTrail(audit_path)

    transport = InMemoryNotificationTransport()

    engine = AlertEngine(
        transport=transport,
        default_recipient="test@example.com",
        audit_trail=trail,
    )

    event = make_event(
        event_id="5F7-EVENT-001",
        severity=OperationalSeverity.WARNING,
        event_type=OperationalEventType.MARKET_DATA_STALE,
        message="Market data is stale.",
    )

    result = engine.process(event)

    assert result.status == AlertStatus.SENT

    assert trail.count() == 1
    assert trail.verify()["healthy"] is True

    record = trail.read()[0]

    assert record.sequence == 1
    assert record.event["event_id"] == event.event_id
    assert record.event["message"] == event.message
    assert record.event["event_type"] == event.event_type


def test_suppressed_event_is_still_audited(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    trail = OperationalAuditTrail(audit_path)

    engine = AlertEngine(
        transport=InMemoryNotificationTransport(),
        default_recipient="test@example.com",
        audit_trail=trail,
    )

    event = make_event(
        event_id="5F7-EVENT-002",
        severity=OperationalSeverity.INFO,
        event_type=OperationalEventType.SYSTEM_START,
        message="Routine system start.",
    )

    result = engine.process(event)

    assert result.status == AlertStatus.SUPPRESSED
    assert result.attempted is False
    assert result.delivered is False

    assert trail.count() == 1
    assert trail.read()[0].event["event_id"] == event.event_id
    assert trail.verify()["healthy"] is True


def test_duplicate_event_is_not_audited_twice(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    trail = OperationalAuditTrail(audit_path)

    transport = InMemoryNotificationTransport()

    engine = AlertEngine(
        transport=transport,
        default_recipient="test@example.com",
        audit_trail=trail,
    )

    event = make_event(
        event_id="5F7-EVENT-003",
        severity=OperationalSeverity.CRITICAL,
        event_type=OperationalEventType.KILL_SWITCH_ACTIVATED,
        message="Kill switch activated.",
    )

    first = engine.process(event)
    second = engine.process(event)

    assert first.status == AlertStatus.SENT
    assert second.status == AlertStatus.SUPPRESSED

    assert trail.count() == 1
    assert trail.verify()["healthy"] is True

    assert len(transport.sent_notifications) == 1


def test_multiple_unique_events_preserve_audit_chain(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    trail = OperationalAuditTrail(audit_path)

    engine = AlertEngine(
        transport=InMemoryNotificationTransport(),
        default_recipient="test@example.com",
        audit_trail=trail,
    )

    events = [
        make_event(
            event_id="5F7-EVENT-101",
            severity=OperationalSeverity.INFO,
            event_type=OperationalEventType.SYSTEM_START,
            message="System started.",
        ),
        make_event(
            event_id="5F7-EVENT-102",
            severity=OperationalSeverity.WARNING,
            event_type=OperationalEventType.MARKET_DATA_STALE,
            message="Market data stale.",
        ),
        make_event(
            event_id="5F7-EVENT-103",
            severity=OperationalSeverity.ERROR,
            event_type=OperationalEventType.EXECUTION_FAILED,
            message="Execution failed.",
        ),
    ]

    results = [engine.process(event) for event in events]

    assert results[0].status == AlertStatus.SUPPRESSED
    assert results[1].status == AlertStatus.SENT
    assert results[2].status == AlertStatus.SENT

    assert trail.count() == 3

    records = trail.read()

    assert [record.sequence for record in records] == [1, 2, 3]

    assert [
        record.event["event_id"]
        for record in records
    ] == [
        "5F7-EVENT-101",
        "5F7-EVENT-102",
        "5F7-EVENT-103",
    ]

    verification = trail.verify()

    assert verification["healthy"] is True
    assert verification["records"] == 3


def test_audit_failure_prevents_notification(tmp_path):
    """
    Audit failure must occur before notification delivery.

    This ensures we do not send an operational alert for an event that
    could not be durably recorded in the configured audit trail.
    """
    trail = OperationalAuditTrail(
        tmp_path / "audit.jsonl"
    )

    trail.append = Mock(
        side_effect=RuntimeError("AUDIT_WRITE_FAILURE")
    )

    transport = InMemoryNotificationTransport()

    engine = AlertEngine(
        transport=transport,
        default_recipient="test@example.com",
        audit_trail=trail,
    )

    event = make_event(
        event_id="5F7-EVENT-FAIL",
        severity=OperationalSeverity.CRITICAL,
        event_type=OperationalEventType.KILL_SWITCH_ACTIVATED,
        message="Kill switch activated.",
    )

    try:
        engine.process(event)
    except RuntimeError as exc:
        assert str(exc) == "AUDIT_WRITE_FAILURE"
    else:
        raise AssertionError(
            "Expected audit failure to propagate"
        )

    assert trail.append.call_count == 1
    assert len(transport.sent_notifications) == 0
    assert engine.summary()["processed_event_count"] == 0


def test_health_and_metadata_report_audit_configuration(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    trail = OperationalAuditTrail(audit_path)

    engine = AlertEngine(
        transport=InMemoryNotificationTransport(),
        default_recipient="test@example.com",
        audit_trail=trail,
    )

    health = engine.health_check()

    assert health["healthy"] is True
    assert health["audit_trail_health"]["healthy"] is True
    assert health["audit_trail_health"]["module"] == "audittrail"

    metadata = engine.metadata()

    assert metadata["audit_trail"]["configured"] is True
    assert metadata["audit_trail"]["api_version"] == "1.0.0"
    assert metadata["audit_trail"]["module"] == "audittrail"
