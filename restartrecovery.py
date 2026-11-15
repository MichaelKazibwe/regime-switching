
"""
======================================================================
restartrecovery.py

Phase 5H — Restart / State Recovery
======================================================================

Purpose
-------
Provide a controlled orchestration boundary for restoring explicitly
registered component state after process restart.

Safety principles
-----------------
1. Only explicitly registered components may be restored.
2. Component restoration must use the component's own from_dict()
   contract.
3. Failed restoration is fail-closed.
4. Failed restoration must not replace the existing live component.
5. Recovery never authorizes execution or broker submission.
6. Recovery is observational/orchestration only.
7. No automatic execution replay is performed.
8. Recovery health is explicit and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from audittrail import OperationalAuditTrail
from operationalevent import (
    OperationalEvent,
    OperationalEventType,
    OperationalSeverity,
    OperationalSource,
)


class RecoveryStatus(str, Enum):
    """Terminal status of a recovery attempt."""

    RECOVERED = "RECOVERED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class RecoveryResult:
    """Immutable result of a restart-recovery attempt."""

    api_version: str
    phase: str
    component: str
    status: RecoveryStatus
    healthy: bool
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    failed_components: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    # Recovery can never grant execution authority.
    execution_authorized: bool = False
    broker_submission_authorized: bool = False
    decision_mutation_authorized: bool = False


class RestartRecovery:
    """
    Controlled restart/state recovery orchestrator.

    Components are explicitly registered by name. Each component must
    expose a compatible class-level from_dict() restoration contract.
    """

    API_VERSION = "1.0.0"
    PHASE = "5H"
    COMPONENT = "RestartRecovery"

    def __init__(
        self,
        components: dict[str, Any],
        audit_trail: OperationalAuditTrail | None = None,
    ) -> None:
        if not isinstance(components, dict):
            raise TypeError("components must be a dictionary")

        if audit_trail is not None and not isinstance(
            audit_trail,
            OperationalAuditTrail,
        ):
            raise TypeError("audit_trail must be an OperationalAuditTrail")

        self.components: dict[str, Any] = dict(components)
        self.audit_trail = audit_trail
        self._last_result: RecoveryResult | None = None
        self.event_history: list[OperationalEvent] = []

    @staticmethod
    def _restore_component(
        current: Any,
        payload: Any,
    ) -> Any:
        """Restore a component without mutating the current instance."""

        if not isinstance(payload, dict):
            raise ValueError("persisted component state must be a dictionary")

        restore = getattr(type(current), "from_dict", None)

        if not callable(restore):
            raise TypeError(
                f"{type(current).__name__} does not provide from_dict()"
            )

        return restore(payload)

    def _record_event(self, event: OperationalEvent) -> None:
        """Record an immutable operational lifecycle event."""
        self.event_history.append(event)

    def _create_event(
        self,
        event_type: OperationalEventType,
        *,
        message: str,
        severity: OperationalSeverity,
        metadata: dict[str, Any] | None = None,
    ) -> OperationalEvent:
        """Create and record a canonical restart/recovery event."""
        event = OperationalEvent.create(
            event_type=event_type,
            severity=severity,
            source=OperationalSource.SYSTEM,
            message=message,
            metadata=metadata or {},
        )
        self._record_event(event)

        if self.audit_trail is not None:
            self.audit_trail.append(event)

        return event

    def restore(
        self,
        persisted_state: dict[str, Any],
    ) -> RecoveryResult:
        """
        Restore explicitly registered components.

        Restoration is transactional at the orchestrator boundary:
        component references are replaced only after successful
        reconstruction.
        """

        self._create_event(
            OperationalEventType.SYSTEM_RESTART,
            severity=OperationalSeverity.INFO,
            message="Restart recovery started.",
            metadata={
                "status": "STARTED",
                "component_count": len(self.components),
            },
        )

        if not isinstance(persisted_state, dict):
            result = RecoveryResult(
                api_version=self.API_VERSION,
                phase=self.PHASE,
                component=self.COMPONENT,
                status=RecoveryStatus.FAILED,
                healthy=False,
                failed_components=list(self.components),
                errors={
                    name: "persisted state must be a dictionary"
                    for name in self.components
                },
            )
            self._last_result = result

            self._create_event(
                OperationalEventType.SYSTEM_RECOVERY,
                severity=OperationalSeverity.ERROR,
                message="Restart recovery failed.",
                metadata={
                    "status": "FAILED",
                    "failed_components": sorted(set(result.failed_components)),
                    "errors": dict(result.errors),
                },
            )

            return result

        restored_components: dict[str, Any] = {}
        component_results: dict[str, dict[str, Any]] = {}
        failed_components: list[str] = []
        errors: dict[str, str] = {}

        # Reject unknown persisted components rather than silently
        # accepting state outside the explicit recovery registry.
        unknown = [
            name
            for name in persisted_state
            if name not in self.components
        ]

        for name in unknown:
            failed_components.append(name)
            errors[name] = "component is not explicitly registered"

        # Restore into temporary objects first. Nothing in the live
        # component registry is replaced until all requested restores
        # succeed.
        for name, current in self.components.items():
            if name not in persisted_state:
                failed_components.append(name)
                errors[name] = "persisted state is missing"
                continue

            try:
                restored = self._restore_component(
                    current,
                    persisted_state[name],
                )
            except Exception as exc:
                failed_components.append(name)
                errors[name] = f"{type(exc).__name__}: {exc}"
                continue

            restored_components[name] = restored
            component_results[name] = {
                "restored": True,
            }

        if failed_components:
            result = RecoveryResult(
                api_version=self.API_VERSION,
                phase=self.PHASE,
                component=self.COMPONENT,
                status=RecoveryStatus.FAILED,
                healthy=False,
                components=component_results,
                failed_components=sorted(set(failed_components)),
                errors=errors,
            )
            self._last_result = result

            self._create_event(
                OperationalEventType.SYSTEM_RECOVERY,
                severity=OperationalSeverity.ERROR,
                message="Restart recovery failed.",
                metadata={
                    "status": "FAILED",
                    "failed_components": sorted(set(failed_components)),
                    "errors": dict(errors),
                },
            )

            return result

        # Commit the reconstructed component objects only after every
        # registered component has restored successfully.
        self.components = restored_components

        result = RecoveryResult(
            api_version=self.API_VERSION,
            phase=self.PHASE,
            component=self.COMPONENT,
            status=RecoveryStatus.RECOVERED,
            healthy=True,
            components=component_results,
        )

        self._last_result = result

        self._create_event(
            OperationalEventType.SYSTEM_RECOVERY,
            severity=OperationalSeverity.INFO,
            message="Restart recovery completed successfully.",
            metadata={
                "status": "RECOVERED",
                "components": sorted(restored_components),
            },
        )

        return result

    def health_check(self) -> dict[str, Any]:
        """Return deterministic recovery health."""

        component_count = len(self.components)

        healthy = (
            component_count > 0
            and self._last_result is not None
            and self._last_result.status == RecoveryStatus.RECOVERED
            and self._last_result.healthy
        )

        return {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "healthy": healthy,
            "component_count": component_count,
            "last_status": (
                self._last_result.status.value
                if self._last_result is not None
                else None
            ),
            "execution_authorized": False,
            "broker_submission_authorized": False,
            "decision_mutation_authorized": False,
            "audit_trail_configured": self.audit_trail is not None,
        }

    def metadata(self) -> dict[str, Any]:
        """Return explicit operational safety metadata."""

        metadata = {
            "api_version": self.API_VERSION,
            "phase": self.PHASE,
            "component": self.COMPONENT,
            "execution_authorized": False,
            "broker_submission_authorized": False,
            "decision_mutation_authorized": False,
            "audit_trail": {
                "configured": self.audit_trail is not None,
            },
        }

        if self.audit_trail is not None:
            metadata["audit_trail"].update(
                self.audit_trail.metadata()
            )

        return metadata
