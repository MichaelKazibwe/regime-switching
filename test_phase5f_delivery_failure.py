"""
Phase 5F.11 — Delivery failure handling tests.

These tests verify that unexpected notification transport failures:
- become FAILED NotificationResults,
- never escape as unhandled exceptions,
- are counted as failed deliveries,
- preserve AuditTrail integration,
- mark the event as processed,
- prevent duplicate retry attempts,
- and preserve execution-layer isolation.
"""

from __future__ import annotations

from pathlib import Path

from alertengine import (
    AlertEngine,
    AlertStatus,
    NotificationChannel,
)
from audittrail import OperationalAuditTrail
from operationalevent import (
    OperationalEvent,
    OperationalEventType,
    OperationalSeverity,
    OperationalSource,
)


class RaisingTransport:
    """Transport that simulates an unexpected delivery exception."""

    channel = NotificationChannel.EMAIL

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error or RuntimeError("simulated SMTP failure")
        self.send_calls = 0

    def send(
        self,
        *,
        notification_id: str,
        event: OperationalEvent,
        recipient: str | None,
    ):
        self.send_calls += 1
        raise self.error

    def health_check(self) -> dict[str, object]:
        return {
            "healthy": True,
            "channel": NotificationChannel.EMAIL,
        }

    def metadata(self) -> dict[str, object]:
        return {
            "channel": NotificationChannel.EMAIL,
            "execution_authority": False,
            "order_creation": False,
            "broker_submission": False,
        }


def build_event(
    *,
    event_id: str = "DELIVERY-FAIL-001",
) -> OperationalEvent:
    return OperationalEvent(
        event_id=event_id,
        event_type=OperationalEventType.RISK_LIMIT_BREACH,
        severity=OperationalSeverity.CRITICAL,
        source=OperationalSource.RISK,
        timestamp="2026-01-01T12:00:00+00:00",
        message="Risk limit breached.",
        decision_id="DECISION-001",
        order_id=None,
        execution_id=None,
        fill_id=None,
        regime="EXPANSION",
        metadata={"test": True},
    )


def build_engine(
    *,
    transport: RaisingTransport,
    audit_trail: OperationalAuditTrail | None = None,
) -> AlertEngine:
    return AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
        audit_trail=audit_trail,
    )


def test_unexpected_transport_exception_becomes_failed_result() -> None:
    transport = RaisingTransport(
        RuntimeError("simulated transport failure"),
    )
    engine = build_engine(transport=transport)

    result = engine.process(build_event())

    assert result.status == AlertStatus.FAILED
    assert result.attempted is True
    assert result.delivered is False
    assert result.channel == NotificationChannel.EMAIL
    assert result.recipient == "recipient@test.local"
    assert result.error == "NOTIFICATION_DELIVERY_ERROR: RuntimeError"


def test_unexpected_transport_exception_does_not_escape() -> None:
    transport = RaisingTransport()
    engine = build_engine(transport=transport)

    result = engine.process(build_event())

    assert result.status == AlertStatus.FAILED


def test_failed_event_is_not_retried_as_duplicate() -> None:
    transport = RaisingTransport()
    engine = build_engine(transport=transport)

    event = build_event()

    first = engine.process(event)
    second = engine.process(event)

    assert first.status == AlertStatus.FAILED
    assert second.status == AlertStatus.SUPPRESSED
    assert transport.send_calls == 1


def test_unexpected_transport_failure_increments_failed_count() -> None:
    transport = RaisingTransport()
    engine = build_engine(transport=transport)

    engine.process(build_event())

    summary = engine.summary()

    assert summary["failed_count"] == 1
    assert summary["alert_count"] == 0
    assert summary["suppressed_count"] == 0


def test_failed_delivery_is_audited(
    tmp_path: Path,
) -> None:
    transport = RaisingTransport()
    audit_trail = OperationalAuditTrail(
        tmp_path / "delivery_failure.jsonl",
    )

    engine = build_engine(
        transport=transport,
        audit_trail=audit_trail,
    )

    event = build_event(
        event_id="DELIVERY-FAIL-AUDITED",
    )

    result = engine.process(event)

    assert result.status == AlertStatus.FAILED
    assert audit_trail.count() == 1

    record = audit_trail.read()[0]

    assert record.event["event_id"] == "DELIVERY-FAIL-AUDITED"
    assert audit_trail.verify()["healthy"] is True


def test_duplicate_after_failed_delivery_is_not_audited_twice(
    tmp_path: Path,
) -> None:
    transport = RaisingTransport()
    audit_trail = OperationalAuditTrail(
        tmp_path / "delivery_duplicate.jsonl",
    )

    engine = build_engine(
        transport=transport,
        audit_trail=audit_trail,
    )

    event = build_event(
        event_id="DELIVERY-FAIL-DUPLICATE",
    )

    first = engine.process(event)
    second = engine.process(event)

    assert first.status == AlertStatus.FAILED
    assert second.status == AlertStatus.SUPPRESSED
    assert transport.send_calls == 1
    assert audit_trail.count() == 1


def test_delivery_failure_preserves_execution_isolation() -> None:
    transport = RaisingTransport()
    engine = build_engine(transport=transport)

    result = engine.process(build_event())

    assert result.status == AlertStatus.FAILED

    metadata = engine.metadata()

    assert metadata["execution_authority"] is False
    assert metadata["order_creation"] is False
    assert metadata["broker_submission"] is False
