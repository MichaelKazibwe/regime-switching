"""
Production Kill Switch
======================

Phase 5D — Operational Kill Switch.

The kill switch is a production safety control that can block downstream
execution authorization when activated.

Architectural rules
-------------------
1. The kill switch does NOT authorize orders.
2. The kill switch does NOT create AuthorizedOrder objects.
3. The kill switch does NOT route orders.
4. The kill switch does NOT communicate with a broker.
5. ProductionExecutionGate remains the sole execution authority.
6. An ACTIVE kill switch must survive serialization/restart.
7. State restoration is fail-closed.
8. Activation and release generate immutable operational events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from exceptions import RiskLimitBreach
from operationalevent import (
    OperationalEvent,
    OperationalEventType,
    OperationalSeverity,
    OperationalSource,
)


@dataclass(frozen=True)
class KillSwitchState:
    """
    Immutable representation of kill-switch state.
    """

    active: bool
    activation_timestamp: Optional[str]
    release_timestamp: Optional[str]
    activation_reason: Optional[str]
    release_reason: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize kill-switch state."""
        return {
            "active": self.active,
            "activation_timestamp": self.activation_timestamp,
            "release_timestamp": self.release_timestamp,
            "activation_reason": self.activation_reason,
            "release_reason": self.release_reason,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "KillSwitchState":
        """Restore kill-switch state with strict validation."""
        if not isinstance(data, dict):
            raise TypeError(
                "KillSwitchState data must be a dictionary."
            )

        if "active" not in data:
            raise ValueError(
                "Serialized kill-switch state must contain "
                "'active'."
            )

        active = data["active"]

        if not isinstance(active, bool):
            raise ValueError(
                "Serialized kill-switch 'active' value "
                "must be boolean."
            )

        activation_timestamp = data.get(
            "activation_timestamp"
        )
        release_timestamp = data.get(
            "release_timestamp"
        )
        activation_reason = data.get(
            "activation_reason"
        )
        release_reason = data.get(
            "release_reason"
        )

        for name, value in (
            (
                "activation_timestamp",
                activation_timestamp,
            ),
            (
                "release_timestamp",
                release_timestamp,
            ),
            (
                "activation_reason",
                activation_reason,
            ),
            (
                "release_reason",
                release_reason,
            ),
        ):
            if value is not None and not isinstance(
                value,
                str,
            ):
                raise ValueError(
                    f"Serialized '{name}' must be "
                    "a string or None."
                )

        if active and activation_timestamp is None:
            raise ValueError(
                "An active kill switch must contain "
                "an activation timestamp."
            )

        return cls(
            active=active,
            activation_timestamp=activation_timestamp,
            release_timestamp=release_timestamp,
            activation_reason=activation_reason,
            release_reason=release_reason,
        )


class KillSwitch:
    """
    Institutional production kill switch.

    The kill switch determines whether execution authorization
    should be blocked, but it never performs authorization or
    execution itself.
    """

    API_VERSION = "1.0.0"

    PHASE = "5D"

    COMPONENT = "KillSwitch"

    PUBLIC_METHODS = (
        "activate",
        "release",
        "is_active",
        "require_clear",
        "state",
        "summary",
        "metadata",
        "health_check",
        "to_dict",
        "from_dict",
    )

    def __init__(
        self,
        active: bool = False,
        activation_timestamp: Optional[str] = None,
        release_timestamp: Optional[str] = None,
        activation_reason: Optional[str] = None,
        release_reason: Optional[str] = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """
        Initialize the kill switch.

        Parameters
        ----------
        active:
            Initial switch state.

        activation_timestamp:
            Timestamp associated with activation.

        release_timestamp:
            Timestamp associated with release.

        activation_reason:
            Reason supplied when the switch was activated.

        release_reason:
            Reason supplied when the switch was released.
        """
        if not isinstance(active, bool):
            raise TypeError(
                "active must be a boolean."
            )

        if active and activation_timestamp is None:
            raise ValueError(
                "An active kill switch must provide "
                "an activation timestamp."
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

        self._state = KillSwitchState(
            active=active,
            activation_timestamp=activation_timestamp,
            release_timestamp=release_timestamp,
            activation_reason=activation_reason,
            release_reason=release_reason,
        )

        self.activation_count = 1 if active else 0
        self.release_count = 0

        self.event_history: list[
            dict[str, Any]
        ] = []

    # ==================================================================
    # INTERNAL HELPERS
    # ==================================================================

    def _utc_now(self) -> str:
        """Return a timezone-aware UTC timestamp."""
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
    def _validate_reason(
        reason: Optional[str],
        field_name: str,
    ) -> Optional[str]:
        """Validate an optional operational reason."""
        if reason is None:
            return None

        if not isinstance(reason, str):
            raise TypeError(
                f"{field_name} must be a string or None."
            )

        cleaned = reason.strip()

        if not cleaned:
            raise ValueError(
                f"{field_name} cannot be empty."
            )

        return cleaned

    def _create_event(
        self,
        event_type: str,
        severity: str,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> OperationalEvent:
        """
        Create an operational event using the certified
        Phase 5B OperationalEvent factory.
        """
        return OperationalEvent.create(
            event_type=event_type,
            severity=severity,
            source=OperationalSource.KILL_SWITCH,
            message=message,
            metadata=metadata or {},
            timestamp=self._utc_now(),
        )

    def _record_event(
        self,
        event: OperationalEvent,
    ) -> OperationalEvent:
        """
        Retain the serialized event locally.

        The component does not own the global audit trail.
        """
        self.event_history.append(
            event.to_dict()
        )

        return event

    # ==================================================================
    # STATE
    # ==================================================================

    def state(self) -> KillSwitchState:
        """Return immutable current state."""
        return self._state

    def is_active(self) -> bool:
        """Return True when the kill switch is active."""
        return self._state.active

    def require_clear(self) -> None:
        """
        Require the kill switch to be released.

        Raises
        ------
        RiskLimitBreach
            If the kill switch is active.
        """
        if self.is_active():
            raise RiskLimitBreach(
                "Production kill switch is ACTIVE. "
                "Execution authorization is blocked."
            )

    # ==================================================================
    # ACTIVATION
    # ==================================================================

    def activate(
        self,
        reason: Optional[str] = None,
    ) -> OperationalEvent:
        """
        Activate the kill switch.

        Activation is idempotent.
        """
        reason = self._validate_reason(
            reason,
            "reason",
        )

        if self._state.active:
            event = self._create_event(
                event_type=(
                    OperationalEventType
                    .KILL_SWITCH_ACTIVATED
                ),
                severity=(
                    OperationalSeverity.WARNING
                ),
                message=(
                    "Kill switch activation requested "
                    "while already active."
                ),
                metadata={
                    "active": True,
                    "idempotent": True,
                    "reason": reason,
                },
            )

            return self._record_event(event)

        timestamp = self._utc_now()

        self._state = KillSwitchState(
            active=True,
            activation_timestamp=timestamp,
            release_timestamp=(
                self._state.release_timestamp
            ),
            activation_reason=reason,
            release_reason=(
                self._state.release_reason
            ),
        )

        self.activation_count += 1

        event = self._create_event(
            event_type=(
                OperationalEventType
                .KILL_SWITCH_ACTIVATED
            ),
            severity=(
                OperationalSeverity.CRITICAL
            ),
            message="Production kill switch activated.",
            metadata={
                "active": True,
                "idempotent": False,
                "reason": reason,
            },
        )

        return self._record_event(event)

    # ==================================================================
    # RELEASE
    # ==================================================================

    def release(
        self,
        reason: Optional[str] = None,
    ) -> OperationalEvent:
        """
        Release the kill switch.

        Release is idempotent.
        """
        reason = self._validate_reason(
            reason,
            "reason",
        )

        if not self._state.active:
            event = self._create_event(
                event_type=(
                    OperationalEventType
                    .KILL_SWITCH_RELEASED
                ),
                severity=OperationalSeverity.INFO,
                message=(
                    "Kill switch release requested "
                    "while already released."
                ),
                metadata={
                    "active": False,
                    "idempotent": True,
                    "reason": reason,
                },
            )

            return self._record_event(event)

        timestamp = self._utc_now()

        self._state = KillSwitchState(
            active=False,
            activation_timestamp=(
                self._state.activation_timestamp
            ),
            release_timestamp=timestamp,
            activation_reason=(
                self._state.activation_reason
            ),
            release_reason=reason,
        )

        self.release_count += 1

        event = self._create_event(
            event_type=(
                OperationalEventType
                .KILL_SWITCH_RELEASED
            ),
            severity=(
                OperationalSeverity.WARNING
            ),
            message="Production kill switch released.",
            metadata={
                "active": False,
                "idempotent": False,
                "reason": reason,
            },
        )

        return self._record_event(event)

    # ==================================================================
    # SUMMARY
    # ==================================================================

    def summary(self) -> dict[str, Any]:
        """Return a concise operational summary."""
        return {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "active": self._state.active,
            "activation_timestamp": (
                self._state.activation_timestamp
            ),
            "release_timestamp": (
                self._state.release_timestamp
            ),
            "activation_reason": (
                self._state.activation_reason
            ),
            "release_reason": (
                self._state.release_reason
            ),
            "activation_count": (
                self.activation_count
            ),
            "release_count": (
                self.release_count
            ),
            "event_count": len(
                self.event_history
            ),
        }

    # ==================================================================
    # METADATA
    # ==================================================================

    def metadata(self) -> dict[str, Any]:
        """Return component metadata."""
        return {
            "module": "killswitch",
            "component": self.COMPONENT,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "production_control": True,
            "execution_authority": False,
            "order_authorization": False,
            "broker_submission": False,
            "broker_routing": False,
            "account_mutation": False,
            "public_methods": list(
                self.PUBLIC_METHODS
            ),
        }

    # ==================================================================
    # HEALTH
    # ==================================================================

    def health_check(self) -> dict[str, Any]:
        """
        Return kill-switch health information.

        An active kill switch is an intentional safety state,
        not a component failure.
        """
        return {
            "healthy": True,
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "active": self._state.active,
            "production_control": True,
            "execution_authority": False,
            "execution_blocked": self._state.active,
        }

    # ==================================================================
    # SERIALIZATION
    # ==================================================================

    def to_dict(self) -> dict[str, Any]:
        """Serialize complete kill-switch state."""
        return {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "state": self._state.to_dict(),
            "activation_count": (
                self.activation_count
            ),
            "release_count": (
                self.release_count
            ),
            "event_history": list(
                self.event_history
            ),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "KillSwitch":
        """
        Restore kill-switch state strictly.

        Restoration is fail-closed. Malformed critical state
        raises rather than silently defaulting to RELEASED.
        """
        if not isinstance(data, dict):
            raise TypeError(
                "KillSwitch state must be a dictionary."
            )

        api_version = data.get(
            "api_version"
        )

        if api_version != cls.API_VERSION:
            raise ValueError(
                "Unsupported KillSwitch API version: "
                f"{api_version!r}."
            )

        state_data = data.get("state")

        if not isinstance(
            state_data,
            dict,
        ):
            raise ValueError(
                "Serialized KillSwitch must contain "
                "a valid 'state' dictionary."
            )

        state = KillSwitchState.from_dict(
            state_data
        )

        activation_count = data.get(
            "activation_count"
        )

        release_count = data.get(
            "release_count"
        )

        event_history = data.get(
            "event_history"
        )

        if (
            not isinstance(
                activation_count,
                int,
            )
            or isinstance(
                activation_count,
                bool,
            )
        ):
            raise ValueError(
                "activation_count must be an integer."
            )

        if (
            not isinstance(
                release_count,
                int,
            )
            or isinstance(
                release_count,
                bool,
            )
        ):
            raise ValueError(
                "release_count must be an integer."
            )

        if activation_count < 0:
            raise ValueError(
                "activation_count cannot be negative."
            )

        if release_count < 0:
            raise ValueError(
                "release_count cannot be negative."
            )

        if not isinstance(
            event_history,
            list,
        ):
            raise ValueError(
                "event_history must be a list."
            )

        for event in event_history:
            if not isinstance(
                event,
                dict,
            ):
                raise ValueError(
                    "Serialized event history entries "
                    "must be dictionaries."
                )

            OperationalEvent.from_dict(
                event
            )

        restored = cls(
            active=state.active,
            activation_timestamp=(
                state.activation_timestamp
            ),
            release_timestamp=(
                state.release_timestamp
            ),
            activation_reason=(
                state.activation_reason
            ),
            release_reason=(
                state.release_reason
            ),
        )

        restored.activation_count = (
            activation_count
        )

        restored.release_count = (
            release_count
        )

        restored.event_history = [
            dict(event)
            for event in event_history
        ]

        return restored


__all__ = [
    "KillSwitch",
    "KillSwitchState",
]