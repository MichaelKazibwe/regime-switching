"""
Phase 5E — Production Circuit Breaker.

The CircuitBreaker is an operational safety control that automatically
blocks execution after a configured number of explicitly recorded
operational failures.

Design principles
-----------------
1. The circuit breaker is NOT an execution authority.
2. It does not create orders.
3. It does not route orders.
4. It does not communicate with a broker.
5. It does not modify portfolio decisions.
6. ProductionExecutionGate remains the sole execution authority.
7. State is serializable and restart-safe.
8. An OPEN circuit survives restart until explicitly reset.
9. Operational transitions are represented using OperationalEvent.
10. Invalid persisted state is rejected rather than silently repaired.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from typing import Any, Mapping

from exceptions import TradingSystemError
from operationalevent import (
    OperationalEvent,
    OperationalEventType,
    OperationalSeverity,
    OperationalSource,
)


class CircuitBreakerError(TradingSystemError):
    """Base exception for CircuitBreaker failures."""


class CircuitBreakerStateError(CircuitBreakerError):
    """Raised when persisted or constructed state is invalid."""


class CircuitBreakerOpenError(CircuitBreakerError):
    """Raised when execution is attempted while the circuit is open."""


@dataclass(frozen=True)
class CircuitBreakerState:
    """
    Immutable circuit-breaker state.

    A circuit has two operational states:

        CLOSED
        OPEN

    An OPEN circuit remains open until explicitly reset.
    """

    open: bool
    failure_count: int
    threshold: int
    opened_at: str | None
    last_failure_at: str | None
    last_failure_reason: str | None
    last_reset_at: str | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the immutable state."""
        return {
            "open": self.open,
            "failure_count": self.failure_count,
            "threshold": self.threshold,
            "opened_at": self.opened_at,
            "last_failure_at": self.last_failure_at,
            "last_failure_reason": self.last_failure_reason,
            "last_reset_at": self.last_reset_at,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "CircuitBreakerState":
        """Restore state with strict validation."""

        if not isinstance(payload, Mapping):
            raise CircuitBreakerStateError(
                "CircuitBreakerState payload must be a mapping."
            )

        required = {
            "open",
            "failure_count",
            "threshold",
            "opened_at",
            "last_failure_at",
            "last_failure_reason",
            "last_reset_at",
        }

        missing = required.difference(payload)

        if missing:
            raise CircuitBreakerStateError(
                "CircuitBreakerState is missing required fields: "
                f"{sorted(missing)}"
            )

        open_state = payload["open"]
        failure_count = payload["failure_count"]
        threshold = payload["threshold"]

        if not isinstance(open_state, bool):
            raise CircuitBreakerStateError(
                "CircuitBreakerState 'open' must be boolean."
            )

        if (
            isinstance(failure_count, bool)
            or not isinstance(failure_count, int)
            or failure_count < 0
        ):
            raise CircuitBreakerStateError(
                "CircuitBreakerState 'failure_count' must be "
                "a non-negative integer."
            )

        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, int)
            or threshold <= 0
        ):
            raise CircuitBreakerStateError(
                "CircuitBreakerState 'threshold' must be "
                "a positive integer."
            )

        timestamps = (
            "opened_at",
            "last_failure_at",
            "last_reset_at",
        )

        for field in timestamps:
            value = payload[field]

            if value is not None and not isinstance(value, str):
                raise CircuitBreakerStateError(
                    f"CircuitBreakerState '{field}' must be "
                    "a string or None."
                )

        reason = payload["last_failure_reason"]

        if reason is not None and not isinstance(reason, str):
            raise CircuitBreakerStateError(
                "CircuitBreakerState 'last_failure_reason' must be "
                "a string or None."
            )

        if open_state and payload["opened_at"] is None:
            raise CircuitBreakerStateError(
                "An OPEN circuit must have 'opened_at'."
            )

        if not open_state and payload["opened_at"] is not None:
            raise CircuitBreakerStateError(
                "A CLOSED circuit cannot have 'opened_at'."
            )

        if failure_count >= threshold and not open_state:
            raise CircuitBreakerStateError(
                "A circuit at or above its threshold must be OPEN."
            )

        if failure_count == 0 and payload["last_failure_at"] is not None:
            raise CircuitBreakerStateError(
                "A zero-failure circuit cannot have 'last_failure_at'."
            )

        if failure_count == 0 and reason is not None:
            raise CircuitBreakerStateError(
                "A zero-failure circuit cannot have "
                "'last_failure_reason'."
            )

        return cls(
            open=open_state,
            failure_count=failure_count,
            threshold=threshold,
            opened_at=payload["opened_at"],
            last_failure_at=payload["last_failure_at"],
            last_failure_reason=reason,
            last_reset_at=payload["last_reset_at"],
        )


class CircuitBreaker:
    """
    Production operational circuit breaker.

    The breaker records explicitly reported operational failures.

    Once the configured threshold is reached:

        CLOSED -> OPEN

    An OPEN circuit blocks authorization through its consumer.

    Recovery is explicit:

        OPEN -> CLOSED

    The breaker itself does not execute or route orders.
    """

    API_VERSION = "1.0.0"
    PHASE = "5E"
    COMPONENT = "CircuitBreaker"

    PUBLIC_METHODS = (
        "record_failure",
        "record_success",
        "open",
        "reset",
        "is_open",
        "require_closed",
        "state",
        "summary",
        "metadata",
        "health_check",
        "to_dict",
        "from_dict",
    )

    def __init__(
        self,
        threshold: int = 5,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, int)
            or threshold <= 0
        ):
            raise CircuitBreakerStateError(
                "threshold must be a positive integer."
            )

        self._clock = clock or (lambda: datetime.now(timezone.utc))

        initial_clock = self._clock()
        if not isinstance(initial_clock, datetime):
            raise TypeError(
                "clock must return a datetime."
            )
        if (
            initial_clock.tzinfo is None
            or initial_clock.utcoffset() is None
        ):
            raise ValueError(
                "clock must return a timezone-aware datetime."
            )

        self._state = CircuitBreakerState(
            open=False,
            failure_count=0,
            threshold=threshold,
            opened_at=None,
            last_failure_at=None,
            last_failure_reason=None,
            last_reset_at=None,
        )

        self._event_history: list[OperationalEvent] = []
        self._failure_events = 0
        self._success_events = 0
        self._open_count = 0
        self._reset_count = 0

    # ============================================================
    # INTERNAL HELPERS
    # ============================================================

    def _utc_now(self) -> str:
        """Return a timezone-aware UTC ISO-8601 timestamp."""
        current = self._clock()

        if not isinstance(current, datetime):
            raise TypeError(
                "clock must return a datetime."
            )

        if (
            current.tzinfo is None
            or current.utcoffset() is None
        ):
            raise ValueError(
                "clock must return a timezone-aware datetime."
            )

        return current.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _validate_reason(reason: str) -> str:
        if not isinstance(reason, str):
            raise TypeError("reason must be a string.")

        normalized = reason.strip()

        if not normalized:
            raise ValueError("reason must not be empty.")

        return normalized

    def _record_event(
        self,
        event: OperationalEvent,
    ) -> OperationalEvent:
        self._event_history.append(event)
        return event

    def _create_event(
        self,
        *,
        event_type: str,
        severity: str,
        message: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> OperationalEvent:
        event = OperationalEvent.create(
            event_type=event_type,
            severity=severity,
            source=OperationalSource.CIRCUIT_BREAKER,
            message=message,
            metadata=metadata,
            timestamp=self._utc_now(),
        )

        return self._record_event(event)

    # ============================================================
    # STATE
    # ============================================================

    def state(self) -> CircuitBreakerState:
        """Return the current immutable state."""
        return self._state

    def is_open(self) -> bool:
        """Return True when the circuit is OPEN."""
        return self._state.open

    # ============================================================
    # FAILURE / SUCCESS RECORDING
    # ============================================================

    def record_failure(
        self,
        reason: str,
    ) -> OperationalEvent:
        """
        Record an operational failure.

        A failure increments the failure counter.

        If the threshold is reached, the circuit transitions
        from CLOSED to OPEN.
        """

        reason = self._validate_reason(reason)

        timestamp = self._utc_now()

        new_failure_count = self._state.failure_count + 1

        if self._state.open:
            event = self._create_event(
                event_type=OperationalEventType.CIRCUIT_BREAKER_OPENED,
                severity=OperationalSeverity.WARNING,
                message="Failure recorded while circuit is already OPEN.",
                metadata={
                    "idempotent": True,
                    "failure_count": new_failure_count,
                    "threshold": self._state.threshold,
                    "reason": reason,
                },
            )

            self._failure_events += 1

            self._state = CircuitBreakerState(
                open=True,
                failure_count=new_failure_count,
                threshold=self._state.threshold,
                opened_at=self._state.opened_at,
                last_failure_at=timestamp,
                last_failure_reason=reason,
                last_reset_at=self._state.last_reset_at,
            )

            return event

        self._failure_events += 1

        if new_failure_count >= self._state.threshold:
            self._state = CircuitBreakerState(
                open=True,
                failure_count=new_failure_count,
                threshold=self._state.threshold,
                opened_at=timestamp,
                last_failure_at=timestamp,
                last_failure_reason=reason,
                last_reset_at=self._state.last_reset_at,
            )

            self._open_count += 1

            return self._create_event(
                event_type=OperationalEventType.CIRCUIT_BREAKER_OPENED,
                severity=OperationalSeverity.CRITICAL,
                message=(
                    "Circuit breaker OPEN: failure threshold reached."
                ),
                metadata={
                    "failure_count": new_failure_count,
                    "threshold": self._state.threshold,
                    "reason": reason,
                    "transition": "CLOSED_TO_OPEN",
                },
            )

        self._state = CircuitBreakerState(
            open=False,
            failure_count=new_failure_count,
            threshold=self._state.threshold,
            opened_at=None,
            last_failure_at=timestamp,
            last_failure_reason=reason,
            last_reset_at=self._state.last_reset_at,
        )

        return self._create_event(
            event_type=OperationalEventType.AUDIT,
            severity=OperationalSeverity.WARNING,
            message="Circuit breaker failure recorded.",
            metadata={
                "failure_count": new_failure_count,
                "threshold": self._state.threshold,
                "reason": reason,
                "circuit_open": False,
            },
        )

    def record_success(self) -> OperationalEvent:
        """
        Record a successful operational check.

        Success does not automatically close an OPEN circuit.

        This is deliberate: recovery from an operational failure
        requires explicit reset.
        """

        self._success_events += 1

        if self._state.open:
            return self._create_event(
                event_type=OperationalEventType.AUDIT,
                severity=OperationalSeverity.INFO,
                message=(
                    "Successful operational check recorded while "
                    "circuit remains OPEN."
                ),
                metadata={
                    "circuit_open": True,
                    "failure_count": self._state.failure_count,
                    "threshold": self._state.threshold,
                    "automatic_recovery": False,
                },
            )

        timestamp = self._utc_now()

        self._state = CircuitBreakerState(
            open=False,
            failure_count=0,
            threshold=self._state.threshold,
            opened_at=None,
            last_failure_at=None,
            last_failure_reason=None,
            last_reset_at=self._state.last_reset_at,
        )

        return self._create_event(
            event_type=OperationalEventType.AUDIT,
            severity=OperationalSeverity.INFO,
            message="Circuit breaker operational check succeeded.",
            metadata={
                "circuit_open": False,
                "failure_count": 0,
                "threshold": self._state.threshold,
                "timestamp": timestamp,
            },
        )

    # ============================================================
    # OPEN / RESET
    # ============================================================

    def open(
        self,
        reason: str,
    ) -> OperationalEvent:
        """
        Explicitly open the circuit.

        This is useful when an external operational condition
        requires immediate blocking without waiting for the
        failure threshold.
        """

        reason = self._validate_reason(reason)

        timestamp = self._utc_now()

        if self._state.open:
            return self._create_event(
                event_type=OperationalEventType.CIRCUIT_BREAKER_OPENED,
                severity=OperationalSeverity.WARNING,
                message="Circuit breaker is already OPEN.",
                metadata={
                    "idempotent": True,
                    "reason": reason,
                    "failure_count": self._state.failure_count,
                    "threshold": self._state.threshold,
                },
            )

        self._state = CircuitBreakerState(
            open=True,
            failure_count=self._state.failure_count,
            threshold=self._state.threshold,
            opened_at=timestamp,
            last_failure_at=self._state.last_failure_at,
            last_failure_reason=reason,
            last_reset_at=self._state.last_reset_at,
        )

        self._open_count += 1

        return self._create_event(
            event_type=OperationalEventType.CIRCUIT_BREAKER_OPENED,
            severity=OperationalSeverity.CRITICAL,
            message="Circuit breaker explicitly OPENED.",
            metadata={
                "reason": reason,
                "failure_count": self._state.failure_count,
                "threshold": self._state.threshold,
                "transition": "CLOSED_TO_OPEN",
                "explicit": True,
            },
        )

    def reset(
        self,
        reason: str = "operator_reset",
    ) -> OperationalEvent:
        """
        Explicitly close/reset the circuit.

        Reset clears the failure counter.

        An OPEN circuit does not automatically recover.
        """

        reason = self._validate_reason(reason)

        timestamp = self._utc_now()

        if not self._state.open:
            return self._create_event(
                event_type=OperationalEventType.CIRCUIT_BREAKER_CLOSED,
                severity=OperationalSeverity.INFO,
                message="Circuit breaker is already CLOSED.",
                metadata={
                    "idempotent": True,
                    "reason": reason,
                    "failure_count": self._state.failure_count,
                },
            )

        self._state = CircuitBreakerState(
            open=False,
            failure_count=0,
            threshold=self._state.threshold,
            opened_at=None,
            last_failure_at=None,
            last_failure_reason=None,
            last_reset_at=timestamp,
        )

        self._reset_count += 1

        return self._create_event(
            event_type=OperationalEventType.CIRCUIT_BREAKER_CLOSED,
            severity=OperationalSeverity.WARNING,
            message="Circuit breaker explicitly CLOSED.",
            metadata={
                "reason": reason,
                "previous_failure_count": self._state.failure_count,
                "transition": "OPEN_TO_CLOSED",
                "explicit": True,
            },
        )

    # ============================================================
    # EXECUTION SAFETY
    # ============================================================

    def require_closed(self) -> None:
        """
        Hard-stop when the circuit is OPEN.

        This method does not execute anything.
        """

        if self._state.open:
            raise CircuitBreakerOpenError(
                "Circuit breaker is OPEN; execution is blocked."
            )

    # ============================================================
    # HEALTH / METADATA
    # ============================================================

    def health_check(self) -> dict[str, Any]:
        """Return operational health information."""

        return {
            "healthy": True,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "open": self._state.open,
            "failure_count": self._state.failure_count,
            "threshold": self._state.threshold,
            "execution_blocked": self._state.open,
            "production_control": True,
            "execution_authority": False,
            "automatic_recovery": False,
        }

    def metadata(self) -> dict[str, Any]:
        """Return immutable component metadata."""

        return {
            "module": "circuitbreaker",
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "production_control": True,
            "execution_authority": False,
            "automatic_recovery": False,
            "execution_blocked": self._state.open,
            "threshold": self._state.threshold,
            "public_methods": self.PUBLIC_METHODS,
        }

    def summary(self) -> dict[str, Any]:
        """Return compact operational state."""

        return {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "open": self._state.open,
            "failure_count": self._state.failure_count,
            "threshold": self._state.threshold,
            "failure_events": self._failure_events,
            "success_events": self._success_events,
            "open_count": self._open_count,
            "reset_count": self._reset_count,
            "execution_blocked": self._state.open,
            "last_failure_reason": self._state.last_failure_reason,
        }

    # ============================================================
    # PERSISTENCE
    # ============================================================

    def to_dict(self) -> dict[str, Any]:
        """Serialize complete circuit-breaker state."""

        return {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "state": self._state.to_dict(),
            "failure_events": self._failure_events,
            "success_events": self._success_events,
            "open_count": self._open_count,
            "reset_count": self._reset_count,
            "event_history": [
                event.to_dict()
                for event in self._event_history
            ],
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "CircuitBreaker":
        """Restore a circuit breaker from serialized state."""

        if not isinstance(payload, Mapping):
            raise CircuitBreakerStateError(
                "CircuitBreaker payload must be a mapping."
            )

        if payload.get("api_version") != cls.API_VERSION:
            raise CircuitBreakerStateError(
                "Unsupported CircuitBreaker API version: "
                f"{payload.get('api_version')}"
            )

        if payload.get("phase") != cls.PHASE:
            raise CircuitBreakerStateError(
                "Unsupported CircuitBreaker phase: "
                f"{payload.get('phase')}"
            )

        if payload.get("component") != cls.COMPONENT:
            raise CircuitBreakerStateError(
                "Invalid CircuitBreaker component."
            )

        state_payload = payload.get("state")

        if not isinstance(state_payload, Mapping):
            raise CircuitBreakerStateError(
                "CircuitBreaker 'state' must be a mapping."
            )

        state = CircuitBreakerState.from_dict(
            state_payload
        )

        counters = (
            "failure_events",
            "success_events",
            "open_count",
            "reset_count",
        )

        values: dict[str, int] = {}

        for field in counters:
            value = payload.get(field)

            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise CircuitBreakerStateError(
                    f"CircuitBreaker '{field}' must be "
                    "a non-negative integer."
                )

            values[field] = value

        history = payload.get("event_history")

        if not isinstance(history, list):
            raise CircuitBreakerStateError(
                "CircuitBreaker 'event_history' must be a list."
            )

        restored_events: list[OperationalEvent] = []

        for event_payload in history:
            if not isinstance(event_payload, Mapping):
                raise CircuitBreakerStateError(
                    "Each event history entry must be a mapping."
                )

            try:
                restored_events.append(
                    OperationalEvent.from_dict(
                        event_payload
                    )
                )
            except Exception as exc:
                raise CircuitBreakerStateError(
                    "Invalid operational event in circuit-breaker "
                    "event history."
                ) from exc

        instance = cls(
            threshold=state.threshold
        )

        instance._state = state
        instance._failure_events = values["failure_events"]
        instance._success_events = values["success_events"]
        instance._open_count = values["open_count"]
        instance._reset_count = values["reset_count"]
        instance._event_history = restored_events

        return instance


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitBreakerOpenError",
    "CircuitBreakerState",
    "CircuitBreakerStateError",
]


def _self_test() -> None:
    """Minimal standalone production self-test."""

    breaker = CircuitBreaker(
        threshold=2
    )

    assert breaker.is_open() is False

    breaker.record_failure(
        "TEST_FAILURE_1"
    )

    assert breaker.is_open() is False

    breaker.record_failure(
        "TEST_FAILURE_2"
    )

    assert breaker.is_open() is True

    try:
        breaker.require_closed()
    except CircuitBreakerOpenError:
        pass
    else:
        raise AssertionError(
            "OPEN circuit did not block execution."
        )

    restored = CircuitBreaker.from_dict(
        breaker.to_dict()
    )

    assert restored.is_open() is True

    restored.reset(
        "SELF_TEST_RESET"
    )

    assert restored.is_open() is False

    restored.require_closed()

    print(
        "CIRCUIT BREAKER SELF-TEST: PASS"
    )


if __name__ == "__main__":
    _self_test()