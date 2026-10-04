from __future__ import annotations

from typing import Any, Mapping


API_VERSION = "1.0.0"
PHASE = "5G"
COMPONENT = "OperationalHealthAggregator"


class OperationalHealthAggregator:
    """
    Aggregate health information from existing operational components.

    This component is observational only. It does not authorize execution,
    create orders, submit to brokers, or mutate trading decisions.
    """

    def __init__(
        self,
        *,
        components: Mapping[str, Any] | None = None,
    ) -> None:
        if components is None:
            components = self._default_components()

        self.components = dict(components)

    @staticmethod
    def _default_components() -> dict[str, Any]:
        """
        Construct the default operational health dependencies.

        Imports are intentionally local so the aggregator does not create
        unnecessary module-import coupling at import time.
        """
        from alertengine import AlertEngine
        from circuitbreaker import CircuitBreaker
        from killswitch import KillSwitch

        import structuredlogging

        return {
            "structured_logging": structuredlogging,
            "kill_switch": KillSwitch(),
            "circuit_breaker": CircuitBreaker(),
            "alert_engine": AlertEngine(),
        }

    @staticmethod
    def _check_component(component: Any) -> dict[str, Any]:
        """Safely evaluate one component's health."""
        health_method = getattr(component, "health_check", None)

        if not callable(health_method):
            return {
                "healthy": False,
                "error": "Component does not expose health_check()",
            }

        try:
            result = health_method()
        except Exception as exc:
            return {
                "healthy": False,
                "error": (
                    f"{type(exc).__name__}: {exc}"
                ),
            }

        if not isinstance(result, dict):
            return {
                "healthy": False,
                "error": "health_check() did not return a dictionary",
            }

        if "healthy" not in result:
            return {
                **result,
                "healthy": False,
                "error": "health_check() result is missing 'healthy'",
            }

        return result

    def health_check(self) -> dict[str, Any]:
        """Return aggregated operational health information."""
        component_health: dict[str, dict[str, Any]] = {}

        for name, component in self.components.items():
            component_health[name] = self._check_component(component)

        healthy =  bool(component_health) and all(
            bool(result.get("healthy", False))
            for result in component_health.values()
        )

        return {
            "api_version": API_VERSION,
            "phase": PHASE,
            "component": COMPONENT,
            "healthy": healthy,
            "components": component_health,
        }

    def metadata(self) -> dict[str, Any]:
        """Return non-execution operational metadata."""
        return {
            "module": "operationalhealth",
            "component": COMPONENT,
            "api_version": API_VERSION,
            "phase": PHASE,
            "execution_authority": False,
            "order_creation": False,
            "broker_submission": False,
            "decision_mutation": False,
        }

    def summary(self) -> dict[str, Any]:
        """Return a compact operational health summary."""
        health = self.health_check()

        return {
            "api_version": API_VERSION,
            "phase": PHASE,
            "healthy": health["healthy"],
            "component_count": len(health["components"]),
            "failed_components": [
                name
                for name, result in health["components"].items()
                if not result.get("healthy", False)
            ],
        }
