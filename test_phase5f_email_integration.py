"""
Phase 5F.10.2 — AlertEngine / EmailNotificationTransport integration tests.

These tests exercise the production integration boundary without contacting
a real SMTP server or using real credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from alertengine import (
    AlertEngine,
    AlertStatus,
    NotificationChannel,
)
from audittrail import OperationalAuditTrail
from emailtransport import EmailNotificationTransport
from operationalevent import (
    OperationalEvent,
    OperationalEventType,
    OperationalSeverity,
)


# ============================================================
# DETERMINISTIC SMTP TEST DOUBLE
# ============================================================


@dataclass
class FakeSMTP:
    """Deterministic SMTP double used by integration tests."""

    host: str
    port: int
    timeout: float

    fail_starttls: bool = False
    fail_login: bool = False
    fail_send: bool = False

    starttls_called: bool = False
    login_called: bool = False
    send_called: bool = False

    username: str | None = None
    password: str | None = None
    message = None

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False

    def starttls(self, *, context) -> None:
        self.starttls_called = True

        if self.fail_starttls:
            raise RuntimeError("TEST_STARTTLS_FAILURE")

    def login(self, username: str, password: str) -> None:
        self.login_called = True
        self.username = username
        self.password = password

        if self.fail_login:
            raise RuntimeError("TEST_LOGIN_FAILURE")

    def send_message(self, message) -> None:
        self.send_called = True
        self.message = message

        if self.fail_send:
            raise RuntimeError("TEST_SEND_FAILURE")


# ============================================================
# TEST FIXTURES
# ============================================================


def build_event(
    *,
    event_id: str,
    event_type: str = OperationalEventType.MARKET_DATA_STALE,
    severity: str = OperationalSeverity.WARNING,
    message: str = "Market data is stale.",
) -> OperationalEvent:
    """Build a deterministic operational event."""

    return OperationalEvent(
        event_id=event_id,
        event_type=event_type,
        severity=severity,
        source="SYSTEM",
        timestamp="2026-10-04T00:00:00+00:00",
        message=message,
    )


def build_transport(
    smtp: FakeSMTP,
) -> EmailNotificationTransport:
    """Build EmailNotificationTransport around the fake SMTP instance."""

    def factory(
        host: str,
        port: int,
        *,
        timeout: float,
    ) -> FakeSMTP:
        assert host == "smtp.test.local"
        assert port == 587
        assert timeout == 10.0
        return smtp

    return EmailNotificationTransport(
        smtp_host="smtp.test.local",
        smtp_port=587,
        sender="alerts@test.local",
        username="test-user",
        password="test-secret",
        use_tls=True,
        timeout=10.0,
        smtp_factory=factory,
    )


# ============================================================
# SUCCESSFUL ALERT DELIVERY
# ============================================================


def test_alertengine_delivers_alert_through_email_transport() -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
    )

    transport = build_transport(smtp)

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
    )

    event = build_event(
        event_id="EMAIL-INTEGRATION-001",
    )

    result = engine.process(event)

    assert result.status == AlertStatus.SENT
    assert result.channel == NotificationChannel.EMAIL
    assert result.attempted is True
    assert result.delivered is True
    assert result.recipient == "recipient@test.local"
    assert result.event_id == "EMAIL-INTEGRATION-001"
    assert result.notification_id == "ALERT-EMAIL-INTEGRATION-001"

    assert smtp.starttls_called is True
    assert smtp.login_called is True
    assert smtp.send_called is True


def test_email_transport_receives_alert_message_content() -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
    )

    transport = build_transport(smtp)

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
    )

    event = build_event(
        event_id="EMAIL-INTEGRATION-002",
        event_type=OperationalEventType.RISK_LIMIT_BREACH,
        severity=OperationalSeverity.CRITICAL,
        message="Portfolio risk limit breached.",
    )

    result = engine.process(event)

    assert result.status == AlertStatus.SENT
    assert smtp.message is not None

    assert smtp.message["From"] == "alerts@test.local"
    assert smtp.message["To"] == "recipient@test.local"

    assert "CRITICAL" in smtp.message["Subject"]
    assert "RISK_LIMIT_BREACH" in smtp.message["Subject"]

    body = smtp.message.get_content()

    assert "EMAIL-INTEGRATION-002" in body
    assert "RISK_LIMIT_BREACH" in body
    assert "CRITICAL" in body
    assert "Portfolio risk limit breached." in body


# ============================================================
# DELIVERY FAILURE
# ============================================================


def test_alertengine_converts_smtp_failure_to_failed_result() -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
        fail_send=True,
    )

    transport = build_transport(smtp)

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
    )

    event = build_event(
        event_id="EMAIL-INTEGRATION-003",
    )

    result = engine.process(event)

    assert result.status == AlertStatus.FAILED
    assert result.attempted is True
    assert result.delivered is False
    assert result.recipient == "recipient@test.local"
    assert result.error == "TEST_SEND_FAILURE"

    assert smtp.send_called is True


def test_alertengine_handles_starttls_failure() -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
        fail_starttls=True,
    )

    transport = build_transport(smtp)

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
    )

    event = build_event(
        event_id="EMAIL-INTEGRATION-004",
    )

    result = engine.process(event)

    assert result.status == AlertStatus.FAILED
    assert result.attempted is True
    assert result.delivered is False
    assert result.error == "TEST_STARTTLS_FAILURE"

    assert smtp.starttls_called is True
    assert smtp.login_called is False
    assert smtp.send_called is False


def test_alertengine_handles_login_failure() -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
        fail_login=True,
    )

    transport = build_transport(smtp)

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
    )

    event = build_event(
        event_id="EMAIL-INTEGRATION-005",
    )

    result = engine.process(event)

    assert result.status == AlertStatus.FAILED
    assert result.attempted is True
    assert result.delivered is False
    assert result.error == "TEST_LOGIN_FAILURE"

    assert smtp.starttls_called is True
    assert smtp.login_called is True
    assert smtp.send_called is False


# ============================================================
# POLICY / IDEMPOTENCY
# ============================================================


def test_suppressed_event_does_not_attempt_email_delivery() -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
    )

    transport = build_transport(smtp)

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
    )

    event = build_event(
        event_id="EMAIL-INTEGRATION-006",
        event_type=OperationalEventType.AUDIT,
        severity=OperationalSeverity.INFO,
        message="Routine audit event.",
    )

    result = engine.process(event)

    assert result.status == AlertStatus.SUPPRESSED
    assert result.attempted is False
    assert result.delivered is False

    assert smtp.starttls_called is False
    assert smtp.login_called is False
    assert smtp.send_called is False


def test_duplicate_alert_is_not_emailed_twice() -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
    )

    transport = build_transport(smtp)

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
    )

    event = build_event(
        event_id="EMAIL-INTEGRATION-007",
    )

    first = engine.process(event)

    assert first.status == AlertStatus.SENT
    assert smtp.send_called is True

    send_count_after_first = int(smtp.send_called)

    second = engine.process(event)

    assert second.status == AlertStatus.SUPPRESSED
    assert second.attempted is False
    assert second.delivered is False

    assert int(smtp.send_called) == send_count_after_first


# ============================================================
# AUDIT TRAIL + EMAIL INTEGRATION
# ============================================================


def test_email_delivery_preserves_audittrail_integration(
    tmp_path: Path,
) -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
    )

    transport = build_transport(smtp)

    audit_trail = OperationalAuditTrail(
        tmp_path / "email_alerts.jsonl",
    )

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
        audit_trail=audit_trail,
    )

    event = build_event(
        event_id="EMAIL-INTEGRATION-008",
    )

    result = engine.process(event)

    assert result.status == AlertStatus.SENT
    assert smtp.send_called is True

    assert audit_trail.count() == 1

    records = audit_trail.read()

    assert len(records) == 1
    assert records[0].event["event_id"] == "EMAIL-INTEGRATION-008"

    verification = audit_trail.verify()

    assert verification["healthy"] is True


def test_failed_email_delivery_is_still_audited(
    tmp_path: Path,
) -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
        fail_send=True,
    )

    transport = build_transport(smtp)

    audit_trail = OperationalAuditTrail(
        tmp_path / "email_failure.jsonl",
    )

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
        audit_trail=audit_trail,
    )

    event = build_event(
        event_id="EMAIL-INTEGRATION-009",
    )

    result = engine.process(event)

    assert result.status == AlertStatus.FAILED
    assert result.attempted is True
    assert result.delivered is False

    assert audit_trail.count() == 1
    assert audit_trail.read()[0].event["event_id"] == (
        "EMAIL-INTEGRATION-009"
    )


# ============================================================
# OPERATIONAL BOUNDARY
# ============================================================


def test_alertengine_email_integration_has_no_execution_authority() -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
    )

    transport = build_transport(smtp)

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
    )

    metadata = engine.metadata()

    assert metadata["execution_authority"] is False
    assert metadata["order_creation"] is False
    assert metadata["broker_submission"] is False

    assert metadata["transport"]["channel"] == (
        NotificationChannel.EMAIL
    )


def test_alertengine_health_includes_email_transport_health() -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
    )

    transport = build_transport(smtp)

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
    )

    health = engine.health_check()

    assert health["healthy"] is True
    assert health["transport_configured"] is True

    transport_health = health["transport_health"]

    assert transport_health["healthy"] is True
    assert transport_health["channel"] == NotificationChannel.EMAIL
    assert transport_health["external_delivery"] is True


# ============================================================
# CREDENTIAL BOUNDARY
# ============================================================


def test_alertengine_metadata_does_not_expose_email_password() -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
    )

    transport = build_transport(smtp)

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
    )

    metadata_text = repr(engine.metadata())
    health_text = repr(engine.health_check())

    assert "test-secret" not in metadata_text
    assert "test-secret" not in health_text


# ============================================================
# CONTRACT CHECK
# ============================================================


def test_email_transport_satisfies_alertengine_transport_contract() -> None:
    smtp = FakeSMTP(
        host="smtp.test.local",
        port=587,
        timeout=10.0,
    )

    transport = build_transport(smtp)

    engine = AlertEngine(
        transport=transport,
        default_recipient="recipient@test.local",
    )

    event = build_event(
        event_id="EMAIL-INTEGRATION-010",
    )

    result = engine.process(event)

    assert result.channel == NotificationChannel.EMAIL
    assert result.event_id == event.event_id
    assert result.notification_id == (
        f"ALERT-{event.event_id}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
