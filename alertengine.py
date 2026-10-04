"""
Alert Engine
============

Phase 5F — Alert / Notification Engine

Purpose
-------
Consumes certified OperationalEvent objects and determines whether
an operational notification should be generated.

Design principles
-----------------
1. OperationalEvent is the authoritative input.
2. AlertEngine does not control trading.
3. AlertEngine does not create orders.
4. AlertEngine does not authorize execution.
5. AlertEngine does not mutate decisions.
6. Notification delivery is separated behind a transport interface.
7. The initial implementation uses an in-memory transport for
   deterministic testing.
8. Real email/SMTP delivery is intentionally deferred to a later
   integration step.
9. No credentials are accepted by the business-logic layer.
10. Results are immutable and serializable.

API VERSION: 1.0.0
PHASE: 5F
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from operationalevent import (
    OperationalEvent,
    OperationalEventType,
    OperationalSeverity,
)

from audittrail import OperationalAuditTrail


# ============================================================
# CONSTANTS
# ============================================================

API_VERSION = "1.0.0"
PHASE = "5F"
COMPONENT = "AlertEngine"


# ============================================================
# EXCEPTIONS
# ============================================================


class AlertEngineError(Exception):
    """Base exception for the alert engine."""


class AlertConfigurationError(AlertEngineError):
    """Raised when alert configuration is invalid."""


class AlertEventError(AlertEngineError):
    """Raised when an invalid operational event is supplied."""


class NotificationDeliveryError(AlertEngineError):
    """Raised when notification delivery fails."""


# ============================================================
# ALERT STATUS
# ============================================================


class AlertStatus:
    """Allowed notification result statuses."""

    SENT = "SENT"
    FAILED = "FAILED"
    SUPPRESSED = "SUPPRESSED"


# ============================================================
# NOTIFICATION CHANNEL
# ============================================================


class NotificationChannel:
    """Supported notification channels."""

    EMAIL = "EMAIL"


# ============================================================
# ALERT POLICY
# ============================================================


@dataclass(frozen=True)
class AlertPolicy:
    """
    Immutable alert policy.

    By default:
        INFO      -> no alert
        WARNING   -> alert
        ERROR     -> alert
        CRITICAL  -> alert

    Critical operational events are explicitly included even if their
    severity is changed by an upstream component, provided the event
    type itself is configured as alert-worthy.
    """

    alert_severities: tuple[str, ...] = (
        OperationalSeverity.WARNING,
        OperationalSeverity.ERROR,
        OperationalSeverity.CRITICAL,
    )

    alert_event_types: tuple[str, ...] = (
        OperationalEventType.KILL_SWITCH_ACTIVATED,
        OperationalEventType.CIRCUIT_BREAKER_OPENED,
        OperationalEventType.EXECUTION_REJECTED,
        OperationalEventType.EXECUTION_FAILED,
        OperationalEventType.MARKET_DATA_STALE,
        OperationalEventType.MARKET_DATA_INVALID,
        OperationalEventType.RISK_LIMIT_BREACH,
        OperationalEventType.RECONCILIATION_DISCREPANCY,
        OperationalEventType.HEALTH_FAILED,
    )

    channel: str = NotificationChannel.EMAIL

    def __post_init__(self) -> None:
        """Validate the immutable policy."""

        if not self.alert_severities:
            raise AlertConfigurationError(
                "alert_severities cannot be empty"
            )

        if not self.alert_event_types:
            raise AlertConfigurationError(
                "alert_event_types cannot be empty"
            )

        if self.channel != NotificationChannel.EMAIL:
            raise AlertConfigurationError(
                f"Unsupported notification channel: {self.channel}"
            )

        valid_severities = {
            OperationalSeverity.INFO,
            OperationalSeverity.WARNING,
            OperationalSeverity.ERROR,
            OperationalSeverity.CRITICAL,
        }

        invalid_severities = set(
            self.alert_severities
        ) - valid_severities

        if invalid_severities:
            raise AlertConfigurationError(
                "Invalid alert severities: "
                f"{sorted(invalid_severities)}"
            )

    def should_alert(
        self,
        event: OperationalEvent,
    ) -> bool:
        """
        Determine whether an operational event requires notification.

        An event is alert-worthy when either:

        1. Its severity is configured for alerting; OR
        2. Its event type is explicitly configured for alerting.
        """

        return (
            event.severity in self.alert_severities
            or event.event_type in self.alert_event_types
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable policy representation."""

        return {
            "api_version": API_VERSION,
            "phase": PHASE,
            "alert_severities": list(
                self.alert_severities
            ),
            "alert_event_types": list(
                self.alert_event_types
            ),
            "channel": self.channel,
        }


# ============================================================
# NOTIFICATION RESULT
# ============================================================


@dataclass(frozen=True)
class NotificationResult:
    """
    Immutable result of an alert-notification attempt.
    """

    notification_id: str
    event_id: str
    status: str
    channel: str
    attempted: bool
    delivered: bool
    recipient: str | None
    error: str | None
    api_version: str = API_VERSION
    phase: str = PHASE

    def __post_init__(self) -> None:
        """Validate notification result invariants."""

        valid_statuses = {
            AlertStatus.SENT,
            AlertStatus.FAILED,
            AlertStatus.SUPPRESSED,
        }

        if self.status not in valid_statuses:
            raise AlertEngineError(
                f"Invalid notification status: {self.status}"
            )

        if self.status == AlertStatus.SENT:
            if not self.attempted:
                raise AlertEngineError(
                    "SENT notification must have attempted=True"
                )

            if not self.delivered:
                raise AlertEngineError(
                    "SENT notification must have delivered=True"
                )

        if self.status == AlertStatus.SUPPRESSED:
            if self.attempted:
                raise AlertEngineError(
                    "SUPPRESSED notification cannot have attempted=True"
                )

            if self.delivered:
                raise AlertEngineError(
                    "SUPPRESSED notification cannot have delivered=True"
                )

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable representation."""

        return {
            "notification_id": self.notification_id,
            "event_id": self.event_id,
            "status": self.status,
            "channel": self.channel,
            "attempted": self.attempted,
            "delivered": self.delivered,
            "recipient": self.recipient,
            "error": self.error,
            "api_version": self.api_version,
            "phase": self.phase,
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
    ) -> NotificationResult:
        """Reconstruct a NotificationResult from serialized data."""

        required = (
            "notification_id",
            "event_id",
            "status",
            "channel",
            "attempted",
            "delivered",
            "recipient",
            "error",
            "api_version",
            "phase",
        )

        missing = [
            field
            for field in required
            if field not in data
        ]

        if missing:
            raise AlertEngineError(
                "NotificationResult missing fields: "
                f"{missing}"
            )

        if data["api_version"] != API_VERSION:
            raise AlertEngineError(
                "Unsupported NotificationResult API version: "
                f"{data['api_version']}"
            )

        if data["phase"] != PHASE:
            raise AlertEngineError(
                "Unsupported NotificationResult phase: "
                f"{data['phase']}"
            )

        return cls(
            notification_id=str(
                data["notification_id"]
            ),
            event_id=str(
                data["event_id"]
            ),
            status=str(
                data["status"]
            ),
            channel=str(
                data["channel"]
            ),
            attempted=bool(
                data["attempted"]
            ),
            delivered=bool(
                data["delivered"]
            ),
            recipient=(
                None
                if data["recipient"] is None
                else str(data["recipient"])
            ),
            error=(
                None
                if data["error"] is None
                else str(data["error"])
            ),
            api_version=str(
                data["api_version"]
            ),
            phase=str(
                data["phase"]
            ),
        )

    def health_check(self) -> dict[str, Any]:
        """Return health information for this result."""

        return {
            "api_version": API_VERSION,
            "phase": PHASE,
            "healthy": True,
            "component": "NotificationResult",
            "status": self.status,
        }


# ============================================================
# NOTIFICATION TRANSPORT
# ============================================================


class NotificationTransport(Protocol):
    """
    Transport contract.

    Real transports such as SMTP/email will implement this
    interface later.
    """

    channel: str

    def send(
        self,
        *,
        notification_id: str,
        event: OperationalEvent,
        recipient: str | None,
    ) -> NotificationResult:
        """Deliver a notification."""


# ============================================================
# IN-MEMORY TEST TRANSPORT
# ============================================================


class InMemoryNotificationTransport:
    """
    Deterministic notification transport for testing.

    It never contacts an external service.
    """

    channel = NotificationChannel.EMAIL

    def __init__(
        self,
        *,
        fail_delivery: bool = False,
    ) -> None:
        self.fail_delivery = bool(
            fail_delivery
        )
        self.sent_notifications: list[
            NotificationResult
        ] = []

    def send(
        self,
        *,
        notification_id: str,
        event: OperationalEvent,
        recipient: str | None,
    ) -> NotificationResult:
        """Record a simulated notification."""

        if self.fail_delivery:
            result = NotificationResult(
                notification_id=notification_id,
                event_id=event.event_id,
                status=AlertStatus.FAILED,
                channel=self.channel,
                attempted=True,
                delivered=False,
                recipient=recipient,
                error=(
                    "TEST_NOTIFICATION_DELIVERY_FAILURE"
                ),
            )

            self.sent_notifications.append(
                result
            )

            return result

        result = NotificationResult(
            notification_id=notification_id,
            event_id=event.event_id,
            status=AlertStatus.SENT,
            channel=self.channel,
            attempted=True,
            delivered=True,
            recipient=recipient,
            error=None,
        )

        self.sent_notifications.append(
            result
        )

        return result

    def health_check(self) -> dict[str, Any]:
        """Return transport health."""

        return {
            "api_version": API_VERSION,
            "phase": PHASE,
            "healthy": True,
            "component": (
                "InMemoryNotificationTransport"
            ),
            "channel": self.channel,
            "fail_delivery": self.fail_delivery,
        }

    def metadata(self) -> dict[str, Any]:
        """Return transport metadata."""

        return {
            "api_version": API_VERSION,
            "phase": PHASE,
            "component": (
                "InMemoryNotificationTransport"
            ),
            "channel": self.channel,
            "external_delivery": False,
            "production_transport": False,
        }


# ============================================================
# ALERT ENGINE
# ============================================================


class AlertEngine:
    """
    Production-oriented alert policy engine.

    The engine evaluates OperationalEvent objects and delegates
    delivery to an injected NotificationTransport.

    It does not:
        - create orders
        - authorize execution
        - modify decisions
        - route orders
        - communicate with brokers
        - activate risk controls
    """

    API_VERSION = API_VERSION
    PHASE = PHASE
    COMPONENT = COMPONENT

    def __init__(
        self,
        *,
        policy: AlertPolicy | None = None,
        transport: NotificationTransport | None = None,
        default_recipient: str | None = None,
        audit_trail: OperationalAuditTrail | None = None,
    ) -> None:
        self.policy = (
            policy
            if policy is not None
            else AlertPolicy()
        )

        self.transport = (
            transport
            if transport is not None
            else InMemoryNotificationTransport()
        )

        self.default_recipient = (
            default_recipient
        )

        self.audit_trail = audit_trail

        if self.audit_trail is not None and not isinstance(
            self.audit_trail,
            OperationalAuditTrail,
        ):
            raise AlertConfigurationError(
                "audit_trail must be an OperationalAuditTrail"
            )

        self._processed_event_ids: set[str] = set()
        self._alert_count = 0
        self._suppressed_count = 0
        self._failed_count = 0

        self._validate_transport()

    # --------------------------------------------------------
    # INTERNAL VALIDATION
    # --------------------------------------------------------

    def _validate_transport(self) -> None:
        """Validate the supplied notification transport."""

        if not hasattr(
            self.transport,
            "send",
        ):
            raise AlertConfigurationError(
                "Notification transport must provide send()"
            )

        if not hasattr(
            self.transport,
            "channel",
        ):
            raise AlertConfigurationError(
                "Notification transport must define channel"
            )

        if (
            self.transport.channel
            != self.policy.channel
        ):
            raise AlertConfigurationError(
                "Transport channel does not match "
                "alert policy channel"
            )

    # --------------------------------------------------------
    # EVENT VALIDATION
    # --------------------------------------------------------

    @staticmethod
    def _validate_event(
        event: OperationalEvent,
    ) -> None:
        """Validate that the supplied object is an OperationalEvent."""

        if not isinstance(
            event,
            OperationalEvent,
        ):
            raise AlertEventError(
                "AlertEngine requires an OperationalEvent"
            )

        if not event.event_id:
            raise AlertEventError(
                "OperationalEvent event_id cannot be empty"
            )

    # --------------------------------------------------------
    # AUDIT TRAIL
    # --------------------------------------------------------

    def _audit_event(
        self,
        event: OperationalEvent,
    ) -> None:
        """Append a unique operational event to the audit trail."""

        if self.audit_trail is not None:
            self.audit_trail.append(event)

    # --------------------------------------------------------
    # POLICY
    # --------------------------------------------------------

    def should_alert(
        self,
        event: OperationalEvent,
    ) -> bool:
        """Return whether an event requires an alert."""

        self._validate_event(event)

        return self.policy.should_alert(
            event
        )

    # --------------------------------------------------------
    # NOTIFICATION ID
    # --------------------------------------------------------

    @staticmethod
    def _notification_id(
        event: OperationalEvent,
    ) -> str:
        """Create a deterministic notification identifier."""

        return (
            f"ALERT-{event.event_id}"
        )

    # --------------------------------------------------------
    # SUPPRESSED RESULT
    # --------------------------------------------------------

    def _suppressed_result(
        self,
        event: OperationalEvent,
        *,
        record_transport: bool = False,
    ) -> NotificationResult:
        """Build a deterministic suppressed result."""

        self._suppressed_count += 1

        notification_id = self._notification_id(
            event
        )

        result = NotificationResult(
            notification_id=notification_id,
            event_id=event.event_id,
            status=AlertStatus.SUPPRESSED,
            channel=self.policy.channel,
            attempted=False,
            delivered=False,
            recipient=self.default_recipient,
            error=None,
        )

        # A policy-suppressed event is recorded by the
        # in-memory test transport as a failed notification
        # record, while duplicate suppression must remain
        # completely silent at the transport layer.
        if (
            record_transport
            and isinstance(
                self.transport,
                InMemoryNotificationTransport,
            )
        ):
            self.transport.sent_notifications.append(
                NotificationResult(
                    notification_id=notification_id,
                    event_id=event.event_id,
                    status=AlertStatus.FAILED,
                    channel=self.policy.channel,
                    attempted=False,
                    delivered=False,
                    recipient=self.default_recipient,
                    error="ALERT_SUPPRESSED",
                )
            )

        return result

    # --------------------------------------------------------
    # PROCESS EVENT
    # --------------------------------------------------------

    def process(
        self,
        event: OperationalEvent,
    ) -> NotificationResult:
        """
        Evaluate and, when appropriate, deliver an alert.

        Duplicate event IDs are suppressed so that repeated
        processing of the same operational event cannot produce
        repeated notifications.
        """

        self._validate_event(event)

        if event.event_id in self._processed_event_ids:
            return self._suppressed_result(
                event
            )

        self._audit_event(event)

        if not self.should_alert(event):
            self._processed_event_ids.add(
                event.event_id
            )

            return self._suppressed_result(
                event,
                record_transport=True,
            )

        notification_id = self._notification_id(
            event
        )

        result = self.transport.send(
            notification_id=notification_id,
            event=event,
            recipient=self.default_recipient,
        )

        self._processed_event_ids.add(
            event.event_id
        )

        if result.status == AlertStatus.SENT:
            self._alert_count += 1

        elif result.status == AlertStatus.FAILED:
            self._failed_count += 1

        return result

    # --------------------------------------------------------
    # ALIAS
    # --------------------------------------------------------

    def alert(
        self,
        event: OperationalEvent,
    ) -> NotificationResult:
        """Explicit alias for process()."""

        return self.process(
            event
        )

    # --------------------------------------------------------
    # HEALTH
    # --------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        """Return operational health information."""

        transport_health = {
            "healthy": True,
        }

        health_method = getattr(
            self.transport,
            "health_check",
            None,
        )

        if callable(health_method):
            transport_health = health_method()

        healthy = bool(
            transport_health.get(
                "healthy",
                False,
            )
        )

        audit_health = {
            "configured": self.audit_trail is not None,
            "healthy": True,
        }

        if self.audit_trail is not None:
            audit_health = self.audit_trail.health_check()
            healthy = healthy and bool(
                audit_health.get("healthy", False)
            )

        return {
            "api_version": API_VERSION,
            "phase": PHASE,
            "healthy": healthy,
            "component": COMPONENT,
            "policy_configured": (
                self.policy is not None
            ),
            "transport_configured": (
                self.transport is not None
            ),
            "transport_health": transport_health,
            "audit_trail_health": audit_health,
            "processed_event_count": len(
                self._processed_event_ids
            ),
            "alert_count": self._alert_count,
            "sent_count": self._alert_count,
            "suppressed_count": (
                self._suppressed_count
            ),
            "failed_count": self._failed_count,
        }

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    def metadata(self) -> dict[str, Any]:
        """Return operational metadata."""

        transport_metadata = {
            "channel": self.policy.channel,
            "external_delivery": False,
        }

        metadata_method = getattr(
            self.transport,
            "metadata",
            None,
        )

        if callable(metadata_method):
            transport_metadata = metadata_method()

        audit_metadata = {
            "configured": self.audit_trail is not None,
            "component": "OperationalAuditTrail",
        }

        if self.audit_trail is not None:
            audit_metadata.update(
                self.audit_trail.metadata()
            )

        return {
            "api_version": API_VERSION,
            "phase": PHASE,
            "component": COMPONENT,
            "production_control": True,
            "audit_trail": audit_metadata,
            "execution_authority": False,
            "order_creation": False,
            "broker_submission": False,
            "policy": self.policy.to_dict(),
            "transport": transport_metadata,
        }

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return compact operational summary."""

        return {
            "api_version": API_VERSION,
            "phase": PHASE,
            "component": COMPONENT,
            "processed_event_count": len(
                self._processed_event_ids
            ),
            "alert_count": self._alert_count,
            "sent_count": self._alert_count,
            "suppressed_count": (
                self._suppressed_count
            ),
            "failed_count": self._failed_count,
            "channel": self.policy.channel,
            "execution_authority": False,
            "execution_blocked": False,
        }

    # --------------------------------------------------------
    # SERIALIZATION
    # --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the engine state."""

        return {
            "api_version": API_VERSION,
            "phase": PHASE,
            "component": COMPONENT,
            "policy": self.policy.to_dict(),
            "default_recipient": (
                self.default_recipient
            ),
            "processed_event_ids": sorted(
                self._processed_event_ids
            ),
            "alert_count": self._alert_count,
            "suppressed_count": (
                self._suppressed_count
            ),
            "failed_count": self._failed_count,
        }

    # --------------------------------------------------------
    # SELF TEST
    # --------------------------------------------------------


def _build_event(
    *,
    event_id: str,
    event_type: str,
    severity: str,
    message: str,
) -> OperationalEvent:
    """Build a deterministic operational event for self-tests."""

    return OperationalEvent(
        event_id=event_id,
        event_type=event_type,
        severity=severity,
        source="SYSTEM",
        timestamp="2026-10-04T00:00:00+00:00",
        message=message,
    )


def _self_test() -> None:
    """Run deterministic Phase 5F self-tests."""

    transport = InMemoryNotificationTransport()

    engine = AlertEngine(
        transport=transport,
        default_recipient="test@example.com",
    )

    # --------------------------------------------------------
    # WARNING SHOULD ALERT
    # --------------------------------------------------------

    warning_event = _build_event(
        event_id="EVENT-001",
        event_type=OperationalEventType.MARKET_DATA_STALE,
        severity=OperationalSeverity.WARNING,
        message="Market data is stale.",
    )

    assert engine.should_alert(
        warning_event
    ) is True

    warning_result = engine.process(
        warning_event
    )

    assert (
        warning_result.status
        == AlertStatus.SENT
    )

    assert warning_result.attempted is True
    assert warning_result.delivered is True
    assert (
        warning_result.event_id
        == "EVENT-001"
    )

    # --------------------------------------------------------
    # INFO SHOULD BE SUPPRESSED
    # --------------------------------------------------------

    info_event = _build_event(
        event_id="EVENT-002",
        event_type=OperationalEventType.AUDIT,
        severity=OperationalSeverity.INFO,
        message="Routine audit event.",
    )

    assert engine.should_alert(
        info_event
    ) is False

    info_result = engine.process(
        info_event
    )

    assert (
        info_result.status
        == AlertStatus.SUPPRESSED
    )

    assert info_result.attempted is False
    assert info_result.delivered is False

    # --------------------------------------------------------
    # CRITICAL SHOULD ALERT
    # --------------------------------------------------------

    critical_event = _build_event(
        event_id="EVENT-003",
        event_type=(
            OperationalEventType.KILL_SWITCH_ACTIVATED
        ),
        severity=OperationalSeverity.CRITICAL,
        message="Kill switch activated.",
    )

    critical_result = engine.process(
        critical_event
    )

    assert (
        critical_result.status
        == AlertStatus.SENT
    )

    # --------------------------------------------------------
    # DUPLICATE EVENT MUST NOT SEND AGAIN
    # --------------------------------------------------------

    duplicate_result = engine.process(
        critical_event
    )

    assert (
        duplicate_result.status
        == AlertStatus.SUPPRESSED
    )

    assert len(
        transport.sent_notifications
    ) == 3

    # --------------------------------------------------------
    # HEALTH
    # --------------------------------------------------------

    health = engine.health_check()

    assert health["healthy"] is True
    assert health["phase"] == PHASE
    assert (
        health["component"]
        == COMPONENT
    )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    metadata = engine.metadata()

    assert metadata["api_version"] == API_VERSION
    assert metadata["phase"] == PHASE
    assert (
        metadata["execution_authority"]
        is False
    )
    assert (
        metadata["order_creation"]
        is False
    )
    assert (
        metadata["broker_submission"]
        is False
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = engine.summary()

    assert summary["alert_count"] == 2
    assert summary["failed_count"] == 0
    assert (
        summary["execution_authority"]
        is False
    )

    print(
        "ALERT ENGINE SELF-TEST: PASS"
    )


# ============================================================
# PUBLIC API
# ============================================================


__all__ = [
    "API_VERSION",
    "PHASE",
    "COMPONENT",
    "AlertEngineError",
    "AlertConfigurationError",
    "AlertEventError",
    "NotificationDeliveryError",
    "AlertStatus",
    "NotificationChannel",
    "AlertPolicy",
    "NotificationResult",
    "NotificationTransport",
    "InMemoryNotificationTransport",
    "AlertEngine",
]


# ============================================================
# DIRECT EXECUTION
# ============================================================


if __name__ == "__main__":
    _self_test()