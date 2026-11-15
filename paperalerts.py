"""Optional email notifications for paper-cycle exceptions and rejections."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from alertengine import AlertEngine, AlertPolicy
from emailtransport import EmailNotificationTransport
from operationalevent import (
    OperationalEvent,
    OperationalEventType,
    OperationalSeverity,
    OperationalSource,
)
from paperconfig import PaperRuntimeConfig


def notify_operator(
    config: PaperRuntimeConfig,
    *,
    cycle_id: str,
    status: str,
    message: str,
    decision_id: str | None = None,
) -> dict[str, Any] | None:
    """Send an optional email and return its auditable delivery result.

    The persistent local alert file remains the primary record. Email
    delivery is best-effort and does not change execution or cycle status.
    """
    if not (config.smtp_host and config.smtp_sender and config.smtp_recipient):
        return None

    event = OperationalEvent(
        event_id=f"PAPER-{cycle_id}-{status}",
        event_type=(
            OperationalEventType.EXECUTION_FAILED
            if status == "FAILED"
            else OperationalEventType.EXECUTION_REJECTED
        ),
        severity=(
            OperationalSeverity.ERROR
            if status == "FAILED"
            else OperationalSeverity.WARNING
        ),
        source=OperationalSource.SYSTEM,
        timestamp=datetime.now(timezone.utc).isoformat(),
        message=message,
        decision_id=decision_id,
        metadata={"cycle_id": cycle_id, "status": status},
    )
    transport = EmailNotificationTransport(
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        sender=config.smtp_sender,
        username=config.smtp_username,
        password=config.smtp_password,
        use_tls=config.smtp_use_tls,
    )
    engine = AlertEngine(
        policy=AlertPolicy(),
        transport=transport,
        default_recipient=config.smtp_recipient,
    )
    return engine.process(event).to_dict()
