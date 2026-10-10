"""
operationalevent.py

Phase 5B — Institutional Operational Event Model.

Provides a canonical immutable event representation for:
    - risk events
    - execution events
    - system health events
    - data-quality events
    - operational control events
    - recovery events
    - operator events

The module does not:
    - execute orders
    - communicate with brokers
    - send alerts
    - write files
    - mutate trading state

It is deliberately infrastructure-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4


API_VERSION = "1.0.0"


class OperationalEventError(Exception):
    """Raised when an operational event is invalid."""


class OperationalEventType:
    """Canonical operational event classifications."""

    SYSTEM_START = "SYSTEM_START"
    SYSTEM_STOP = "SYSTEM_STOP"
    SYSTEM_RESTART = "SYSTEM_RESTART"
    SYSTEM_RECOVERY = "SYSTEM_RECOVERY"

    HEALTH_CHECK = "HEALTH_CHECK"
    HEALTH_DEGRADED = "HEALTH_DEGRADED"
    HEALTH_FAILED = "HEALTH_FAILED"

    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    MARKET_DATA_INVALID = "MARKET_DATA_INVALID"
    MARKET_DATA_RECOVERED = "MARKET_DATA_RECOVERED"

    RISK_PASS = "RISK_PASS"
    RISK_REDUCE = "RISK_REDUCE"
    RISK_REJECT = "RISK_REJECT"
    RISK_LIMIT_BREACH = "RISK_LIMIT_BREACH"

    EXECUTION_AUTHORIZED = "EXECUTION_AUTHORIZED"
    EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
    EXECUTION_SUBMITTED = "EXECUTION_SUBMITTED"
    EXECUTION_FILLED = "EXECUTION_FILLED"
    EXECUTION_PARTIAL = "EXECUTION_PARTIAL"
    EXECUTION_REJECTED = "EXECUTION_REJECTED"
    EXECUTION_FAILED = "EXECUTION_FAILED"

    RECONCILIATION_MATCHED = "RECONCILIATION_MATCHED"
    RECONCILIATION_DISCREPANCY = "RECONCILIATION_DISCREPANCY"

    KILL_SWITCH_ACTIVATED = "KILL_SWITCH_ACTIVATED"
    KILL_SWITCH_RELEASED = "KILL_SWITCH_RELEASED"

    CIRCUIT_BREAKER_OPENED = "CIRCUIT_BREAKER_OPENED"
    CIRCUIT_BREAKER_CLOSED = "CIRCUIT_BREAKER_CLOSED"

    CONFIGURATION_CHANGED = "CONFIGURATION_CHANGED"
    OPERATOR_ACTION = "OPERATOR_ACTION"

    AUDIT = "AUDIT"


class OperationalSeverity:
    """Canonical severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class OperationalSource:
    """Canonical source classifications."""

    SYSTEM = "SYSTEM"
    MARKET_DATA = "MARKET_DATA"
    RISK = "RISK"
    EXECUTION = "EXECUTION"
    RECONCILIATION = "RECONCILIATION"
    POST_TRADE = "POST_TRADE"
    KILL_SWITCH = "KILL_SWITCH"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    OPERATOR = "OPERATOR"
    CONFIGURATION = "CONFIGURATION"


@dataclass(frozen=True)
class OperationalEvent:
    """
    Immutable operational event.

    Every event receives a globally unique event_id unless one is
    explicitly supplied during validated deserialization.
    """

    event_id: str
    event_type: str
    severity: str
    source: str
    timestamp: str

    message: str

    decision_id: str | None = None
    order_id: str | None = None
    execution_id: str | None = None
    fill_id: str | None = None

    regime: str | None = None

    metadata: Mapping[str, Any] | None = None

    API_VERSION = API_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id:
            raise OperationalEventError(
                "event_id must be a non-empty string."
            )

        if not isinstance(self.event_type, str) or not self.event_type:
            raise OperationalEventError(
                "event_type must be a non-empty string."
            )

        if not isinstance(self.severity, str) or not self.severity:
            raise OperationalEventError(
                "severity must be a non-empty string."
            )

        if not isinstance(self.source, str) or not self.source:
            raise OperationalEventError(
                "source must be a non-empty string."
            )

        if not isinstance(self.message, str) or not self.message:
            raise OperationalEventError(
                "message must be a non-empty string."
            )

        if not isinstance(self.timestamp, str) or not self.timestamp:
            raise OperationalEventError(
                "timestamp must be a non-empty ISO timestamp."
            )

        try:
            datetime.fromisoformat(self.timestamp)
        except ValueError as exc:
            raise OperationalEventError(
                "timestamp must be a valid ISO-8601 timestamp."
            ) from exc

        if self.metadata is None:
            metadata = {}
        else:
            if not isinstance(self.metadata, Mapping):
                raise OperationalEventError(
                    "metadata must be a mapping."
                )

            metadata = dict(self.metadata)

        for key in metadata:
            if not isinstance(key, str) or not key:
                raise OperationalEventError(
                    "metadata keys must be non-empty strings."
                )

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(metadata),
        )

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        severity: str,
        source: str,
        message: str,
        decision_id: str | None = None,
        order_id: str | None = None,
        execution_id: str | None = None,
        fill_id: str | None = None,
        regime: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> "OperationalEvent":
        """Create a new operational event."""

        return cls(
            event_id=str(uuid4()),
            event_type=event_type,
            severity=severity,
            source=source,
            timestamp=timestamp or datetime.now(UTC).isoformat(),
            message=message,
            decision_id=decision_id,
            order_id=order_id,
            execution_id=execution_id,
            fill_id=fill_id,
            regime=regime,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a defensive serialized representation."""

        return {
            "api_version": self.API_VERSION,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "source": self.source,
            "timestamp": self.timestamp,
            "message": self.message,
            "decision_id": self.decision_id,
            "order_id": self.order_id,
            "execution_id": self.execution_id,
            "fill_id": self.fill_id,
            "regime": self.regime,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "OperationalEvent":
        """Restore an event from serialized state."""

        if not isinstance(payload, Mapping):
            raise OperationalEventError(
                "Serialized operational event must be a mapping."
            )

        version = payload.get("api_version")

        if version != cls.API_VERSION:
            raise OperationalEventError(
                f"Unsupported operational event API version: {version!r}"
            )

        required = (
            "event_id",
            "event_type",
            "severity",
            "source",
            "timestamp",
            "message",
        )

        missing = [
            key
            for key in required
            if key not in payload
        ]

        if missing:
            raise OperationalEventError(
                f"Missing required event fields: {missing}"
            )

        return cls(
            event_id=payload["event_id"],
            event_type=payload["event_type"],
            severity=payload["severity"],
            source=payload["source"],
            timestamp=payload["timestamp"],
            message=payload["message"],
            decision_id=payload.get("decision_id"),
            order_id=payload.get("order_id"),
            execution_id=payload.get("execution_id"),
            fill_id=payload.get("fill_id"),
            regime=payload.get("regime"),
            metadata=payload.get("metadata", {}),
        )

    def metadata_summary(self) -> dict[str, Any]:
        """Return safe event metadata."""

        return {
            "api_version": self.API_VERSION,
            "event_type": self.event_type,
            "severity": self.severity,
            "source": self.source,
        }

    def health_check(self) -> bool:
        """Validate the event's immutable state."""

        if not self.event_id:
            return False

        if not self.event_type:
            return False

        if not self.severity:
            return False

        if not self.source:
            return False

        if not self.message:
            return False

        try:
            datetime.fromisoformat(self.timestamp)
        except ValueError:
            return False

        return True


PUBLIC_METHODS = (
    "create",
    "to_dict",
    "from_dict",
    "metadata_summary",
    "health_check",
)


def metadata() -> dict[str, Any]:
    """Return module metadata."""

    return {
        "module": "operationalevent",
        "api_version": API_VERSION,
        "class": "OperationalEvent",
        "immutable": True,
        "broker_independent": True,
        "execution_independent": True,
        "serializable": True,
        "public_methods": list(PUBLIC_METHODS),
    }


def health_check() -> bool:
    """Validate module-level health."""

    event = OperationalEvent.create(
        event_type=OperationalEventType.HEALTH_CHECK,
        severity=OperationalSeverity.INFO,
        source=OperationalSource.SYSTEM,
        message="Operational event health check.",
    )

    return event.health_check()