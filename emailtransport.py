"""
Phase 5F.10 — Email Notification Transport.

Provides an SMTP-backed implementation of the AlertEngine
NotificationTransport protocol.

Architecture:

    OperationalEvent
          |
          v
      AlertEngine
          |
          v
    NotificationTransport
          |
          v
    EmailNotificationTransport
          |
          v
          SMTP

Design constraints:

1. Does not create orders.
2. Does not authorize execution.
3. Does not route orders.
4. Does not mutate trading decisions.
5. Does not own AlertEngine policy.
6. Does not store SMTP credentials in AlertEngine.
7. Supports dependency injection for deterministic tests.
8. Converts SMTP failures into NotificationResult objects.
9. Never raises transport errors through the AlertEngine boundary.
10. Keeps external email delivery isolated from business logic.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Callable

from alertengine import (
    AlertStatus,
    NotificationChannel,
    NotificationResult,
)
from operationalevent import OperationalEvent


API_VERSION = "1.0.0"
PHASE = "5F"
COMPONENT = "EmailNotificationTransport"


class EmailNotificationTransport:
    """
    SMTP-backed NotificationTransport implementation.

    SMTP connectivity is performed only when send() is called.

    The SMTP client factory is injectable so tests can use a deterministic
    fake client without making network connections.
    """

    channel = NotificationChannel.EMAIL

    def __init__(
        self,
        *,
        smtp_host: str,
        smtp_port: int = 587,
        sender: str,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        timeout: float = 10.0,
        smtp_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not isinstance(smtp_host, str) or not smtp_host.strip():
            raise ValueError("smtp_host must be a non-empty string")

        if not isinstance(smtp_port, int) or smtp_port <= 0:
            raise ValueError("smtp_port must be a positive integer")

        if not isinstance(sender, str) or not sender.strip():
            raise ValueError("sender must be a non-empty string")

        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout must be positive")

        if username is not None and not isinstance(username, str):
            raise TypeError("username must be a string or None")

        if password is not None and not isinstance(password, str):
            raise TypeError("password must be a string or None")

        self.smtp_host = smtp_host.strip()
        self.smtp_port = smtp_port
        self.sender = sender.strip()
        self.username = username
        self.password = password
        self.use_tls = bool(use_tls)
        self.timeout = float(timeout)

        self._smtp_factory = (
            smtp_factory
            if smtp_factory is not None
            else smtplib.SMTP
        )

    def _build_message(
        self,
        *,
        event: OperationalEvent,
        recipient: str,
    ) -> EmailMessage:
        """Build an email from a certified OperationalEvent."""

        if not isinstance(event, OperationalEvent):
            raise TypeError("event must be an OperationalEvent")

        if not isinstance(recipient, str) or not recipient.strip():
            raise ValueError("recipient must be a non-empty string")

        message = EmailMessage()

        message["From"] = self.sender
        message["To"] = recipient.strip()

        message["Subject"] = (
            f"[{event.severity}] "
            f"{event.event_type}"
        )

        message.set_content(
            "\n".join(
                [
                    "Operational Alert",
                    "",
                    f"Event ID: {event.event_id}",
                    f"Event Type: {event.event_type}",
                    f"Severity: {event.severity}",
                    f"Source: {event.source}",
                    f"Timestamp: {event.timestamp}",
                    "",
                    f"Message: {event.message}",
                ]
            )
        )

        return message

    def send(
        self,
        *,
        notification_id: str,
        event: OperationalEvent,
        recipient: str,
    ) -> NotificationResult:
        """
        Deliver an OperationalEvent by email.

        SMTP/network failures are converted into FAILED results rather
        than escaping through the transport boundary.
        """

        if not isinstance(event, OperationalEvent):
            raise TypeError("event must be an OperationalEvent")

        message = self._build_message(
            event=event,
            recipient=recipient,
        )

        try:
            with self._smtp_factory(
                self.smtp_host,
                self.smtp_port,
                timeout=self.timeout,
            ) as smtp:

                if self.use_tls:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)

                if self.username is not None:
                    smtp.login(
                        self.username,
                        self.password or "",
                    )

                smtp.send_message(message)

            return NotificationResult(
                notification_id=notification_id,
                event_id=event.event_id,
                status=AlertStatus.SENT,
                channel=NotificationChannel.EMAIL,
                attempted=True,
                delivered=True,
                recipient=recipient,
                error=None,
                api_version=API_VERSION,
                phase=PHASE,
            )

        except Exception as exc:
            return NotificationResult(
                notification_id=notification_id,
                event_id=event.event_id,
                status=AlertStatus.FAILED,
                channel=NotificationChannel.EMAIL,
                attempted=True,
                delivered=False,
                recipient=recipient,
                error=str(exc),
                api_version=API_VERSION,
                phase=PHASE,
            )

    def health_check(self) -> dict[str, Any]:
        """Return non-secret operational transport health."""

        return {
            "api_version": API_VERSION,
            "phase": PHASE,
            "component": COMPONENT,
            "healthy": True,
            "channel": NotificationChannel.EMAIL,
            "external_delivery": True,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "tls_enabled": self.use_tls,
            "authenticated": self.username is not None,
        }

    def metadata(self) -> dict[str, Any]:
        """Return transport metadata without exposing credentials."""

        return {
            "api_version": API_VERSION,
            "phase": PHASE,
            "component": COMPONENT,
            "channel": NotificationChannel.EMAIL,
            "external_delivery": True,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "tls_enabled": self.use_tls,
            "authenticated": self.username is not None,
            "execution_authority": False,
            "order_creation": False,
            "broker_submission": False,
            "credentials_exposed": False,
        }