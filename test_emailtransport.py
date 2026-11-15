"""
Phase 5F.10 — Email Notification Transport tests.

These tests validate the SMTP-backed notification transport without
making real network connections.

Architecture:

    OperationalEvent
          |
          v
      AlertEngine
          |
          v
    EmailNotificationTransport
          |
          v
      Injected SMTP fake
"""

from __future__ import annotations

from email.message import EmailMessage
from typing import Any

import pytest

from alertengine import AlertStatus, NotificationChannel
from emailtransport import (
    API_VERSION,
    COMPONENT,
    PHASE,
    EmailNotificationTransport,
)
from operationalevent import OperationalEvent


def _build_event() -> OperationalEvent:
    """Build a deterministic operational event for transport tests."""

    return OperationalEvent(
        event_id="EMAIL-TEST-EVENT-001",
        event_type="HEALTH_FAILED",
        severity="CRITICAL",
        source="TEST",
        timestamp="2026-10-04T00:00:00+00:00",
        message="Email transport integration test event.",
    )


class FakeSMTP:
    """Deterministic SMTP fake used instead of a real network connection."""

    instances: list["FakeSMTP"] = []
    fail_on_send: bool = False
    fail_on_login: bool = False
    fail_on_starttls: bool = False

    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout: float,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in = False
        self.sent_messages: list[EmailMessage] = []
        self.closed = False

        type(self).instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        self.closed = True

    def starttls(self, *, context: Any) -> None:
        if type(self).fail_on_starttls:
            raise RuntimeError("STARTTLS_FAILURE")

        self.started_tls = True

    def login(
        self,
        username: str,
        password: str,
    ) -> None:
        if type(self).fail_on_login:
            raise RuntimeError("LOGIN_FAILURE")

        self.logged_in = True

    def send_message(
        self,
        message: EmailMessage,
    ) -> None:
        if type(self).fail_on_send:
            raise RuntimeError("SMTP_SEND_FAILURE")

        self.sent_messages.append(message)


@pytest.fixture(autouse=True)
def reset_fake_smtp() -> None:
    """Reset fake SMTP state before every test."""

    FakeSMTP.instances = []
    FakeSMTP.fail_on_send = False
    FakeSMTP.fail_on_login = False
    FakeSMTP.fail_on_starttls = False


def _build_transport(
    **kwargs: Any,
) -> EmailNotificationTransport:
    """Build a deterministic email transport."""

    defaults = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "sender": "alerts@example.com",
        "smtp_factory": FakeSMTP,
    }

    defaults.update(kwargs)

    return EmailNotificationTransport(**defaults)


def test_transport_constants() -> None:
    assert API_VERSION == "1.0.0"
    assert PHASE == "5F"
    assert COMPONENT == "EmailNotificationTransport"


def test_transport_uses_email_channel() -> None:
    transport = _build_transport()

    assert transport.channel == NotificationChannel.EMAIL


def test_invalid_smtp_host_is_rejected() -> None:
    with pytest.raises(ValueError):
        _build_transport(smtp_host="")


def test_invalid_smtp_port_is_rejected() -> None:
    with pytest.raises(ValueError):
        _build_transport(smtp_port=0)


def test_invalid_sender_is_rejected() -> None:
    with pytest.raises(ValueError):
        _build_transport(sender="")


def test_invalid_timeout_is_rejected() -> None:
    with pytest.raises(ValueError):
        _build_transport(timeout=0)


def test_message_contains_operational_event_identity() -> None:
    transport = _build_transport()

    event = _build_event()

    message = transport._build_message(
        event=event,
        recipient="ops@example.com",
    )

    assert message["From"] == "alerts@example.com"
    assert message["To"] == "ops@example.com"
    assert message["Subject"] == "[CRITICAL] HEALTH_FAILED"

    body = message.get_content()

    assert event.event_id in body
    assert event.event_type in body
    assert event.severity in body
    assert event.source in body
    assert event.timestamp in body
    assert event.message in body


def test_successful_send_returns_sent_result() -> None:
    transport = _build_transport()

    event = _build_event()

    result = transport.send(
        notification_id="ALERT-EMAIL-001",
        event=event,
        recipient="ops@example.com",
    )

    assert result.notification_id == "ALERT-EMAIL-001"
    assert result.event_id == event.event_id
    assert result.status == AlertStatus.SENT
    assert result.channel == NotificationChannel.EMAIL
    assert result.attempted is True
    assert result.delivered is True
    assert result.recipient == "ops@example.com"
    assert result.error is None

    assert len(FakeSMTP.instances) == 1

    smtp = FakeSMTP.instances[0]

    assert smtp.host == "smtp.example.com"
    assert smtp.port == 587
    assert smtp.timeout == 10.0
    assert smtp.started_tls is True
    assert len(smtp.sent_messages) == 1
    assert smtp.closed is True


def test_authenticated_send_uses_credentials() -> None:
    transport = _build_transport(
        username="smtp-user",
        password="smtp-password",
    )

    event = _build_event()

    result = transport.send(
        notification_id="ALERT-EMAIL-002",
        event=event,
        recipient="ops@example.com",
    )

    assert result.status == AlertStatus.SENT

    smtp = FakeSMTP.instances[0]

    assert smtp.logged_in is True


def test_starttls_failure_returns_failed_result() -> None:
    FakeSMTP.fail_on_starttls = True

    transport = _build_transport()

    event = _build_event()

    result = transport.send(
        notification_id="ALERT-EMAIL-003",
        event=event,
        recipient="ops@example.com",
    )

    assert result.status == AlertStatus.FAILED
    assert result.attempted is True
    assert result.delivered is False
    assert result.error == "STARTTLS_FAILURE"


def test_login_failure_returns_failed_result() -> None:
    FakeSMTP.fail_on_login = True

    transport = _build_transport(
        username="smtp-user",
        password="smtp-password",
    )

    event = _build_event()

    result = transport.send(
        notification_id="ALERT-EMAIL-004",
        event=event,
        recipient="ops@example.com",
    )

    assert result.status == AlertStatus.FAILED
    assert result.attempted is True
    assert result.delivered is False
    assert result.error == "LOGIN_FAILURE"


def test_send_failure_returns_failed_result() -> None:
    FakeSMTP.fail_on_send = True

    transport = _build_transport()

    event = _build_event()

    result = transport.send(
        notification_id="ALERT-EMAIL-005",
        event=event,
        recipient="ops@example.com",
    )

    assert result.status == AlertStatus.FAILED
    assert result.attempted is True
    assert result.delivered is False
    assert result.error == "SMTP_SEND_FAILURE"


def test_health_check_contains_no_credentials() -> None:
    transport = _build_transport(
        username="smtp-user",
        password="SUPER_SECRET_PASSWORD",
    )

    health = transport.health_check()

    assert health["healthy"] is True
    assert health["channel"] == NotificationChannel.EMAIL
    assert health["external_delivery"] is True
    assert health["smtp_host"] == "smtp.example.com"
    assert health["smtp_port"] == 587
    assert health["tls_enabled"] is True
    assert health["authenticated"] is True

    assert "SUPER_SECRET_PASSWORD" not in str(health)


def test_metadata_contains_no_credentials() -> None:
    transport = _build_transport(
        username="smtp-user",
        password="SUPER_SECRET_PASSWORD",
    )

    metadata = transport.metadata()

    assert metadata["api_version"] == API_VERSION
    assert metadata["phase"] == PHASE
    assert metadata["component"] == COMPONENT
    assert metadata["channel"] == NotificationChannel.EMAIL
    assert metadata["external_delivery"] is True
    assert metadata["execution_authority"] is False
    assert metadata["order_creation"] is False
    assert metadata["broker_submission"] is False
    assert metadata["credentials_exposed"] is False

    assert "SUPER_SECRET_PASSWORD" not in str(metadata)


def test_transport_does_not_expose_password_as_attribute() -> None:
    transport = _build_transport(
        username="smtp-user",
        password="SUPER_SECRET_PASSWORD",
    )

    assert transport.password == "SUPER_SECRET_PASSWORD"

    metadata = transport.metadata()
    health = transport.health_check()

    assert "SUPER_SECRET_PASSWORD" not in str(metadata)
    assert "SUPER_SECRET_PASSWORD" not in str(health)


def test_non_operational_event_is_rejected() -> None:
    transport = _build_transport()

    with pytest.raises(TypeError):
        transport.send(
            notification_id="ALERT-EMAIL-006",
            event="not-an-operational-event",  # type: ignore[arg-type]
            recipient="ops@example.com",
        )


def test_empty_recipient_is_rejected() -> None:
    transport = _build_transport()

    with pytest.raises(ValueError):
        transport.send(
            notification_id="ALERT-EMAIL-007",
            event=_build_event(),
            recipient="",
        )


def test_transport_has_no_execution_authority() -> None:
    transport = _build_transport()

    metadata = transport.metadata()

    assert metadata["execution_authority"] is False
    assert metadata["order_creation"] is False
    assert metadata["broker_submission"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))