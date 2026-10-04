from __future__ import annotations



def test_health_aggregator_returns_overall_health():
    from operationalhealth import OperationalHealthAggregator

    aggregator = OperationalHealthAggregator()

    result = aggregator.health_check()

    assert isinstance(result, dict)
    assert "healthy" in result
    assert "components" in result
    assert isinstance(result["components"], dict)


def test_health_aggregator_contains_required_operational_components():
    from operationalhealth import OperationalHealthAggregator

    aggregator = OperationalHealthAggregator()

    result = aggregator.health_check()

    components = result["components"]

    assert "structured_logging" in components
    assert "kill_switch" in components
    assert "circuit_breaker" in components
    assert "alert_engine" in components


def test_healthy_components_produce_healthy_system():
    from operationalhealth import OperationalHealthAggregator

    aggregator = OperationalHealthAggregator()

    result = aggregator.health_check()

    assert result["healthy"] is True

    for component_health in result["components"].values():
        assert isinstance(component_health, dict)
        assert "healthy" in component_health


def test_component_failure_makes_system_unhealthy():
    from operationalhealth import OperationalHealthAggregator

    class BrokenComponent:
        def health_check(self):
            raise RuntimeError("component unavailable")

    aggregator = OperationalHealthAggregator(
        components={
            "broken": BrokenComponent(),
        }
    )

    result = aggregator.health_check()

    assert result["healthy"] is False
    assert "broken" in result["components"]
    assert result["components"]["broken"]["healthy"] is False


def test_component_health_exception_is_contained():
    from operationalhealth import OperationalHealthAggregator

    class BrokenComponent:
        def health_check(self):
            raise RuntimeError("boom")

    aggregator = OperationalHealthAggregator(
        components={
            "broken": BrokenComponent(),
        }
    )

    result = aggregator.health_check()

    broken = result["components"]["broken"]

    assert broken["healthy"] is False
    assert "error" in broken


def test_health_aggregator_has_no_execution_authority():
    from operationalhealth import OperationalHealthAggregator

    aggregator = OperationalHealthAggregator()

    metadata = aggregator.metadata()

    assert metadata["execution_authority"] is False
    assert metadata["order_creation"] is False
    assert metadata["broker_submission"] is False


def test_kill_switch_active_is_not_component_failure():
    from operationalhealth import OperationalHealthAggregator

    class ActiveKillSwitch:
        def health_check(self):
            return {
                "healthy": True,
                "active": True,
                "execution_blocked": True,
            }

    aggregator = OperationalHealthAggregator(
        components={
            "kill_switch": ActiveKillSwitch(),
        }
    )

    result = aggregator.health_check()

    assert result["healthy"] is True
    assert result["components"]["kill_switch"]["healthy"] is True
    assert result["components"]["kill_switch"]["active"] is True


def test_malformed_component_health_is_unhealthy():
    from operationalhealth import OperationalHealthAggregator

    class MalformedComponent:
        def health_check(self):
            return "healthy"

    aggregator = OperationalHealthAggregator(
        components={
            "malformed": MalformedComponent(),
        }
    )

    result = aggregator.health_check()

    assert result["healthy"] is False
    assert result["components"]["malformed"]["healthy"] is False
    assert "error" in result["components"]["malformed"]


def test_missing_healthy_field_is_unhealthy():
    from operationalhealth import OperationalHealthAggregator

    class MissingHealthComponent:
        def health_check(self):
            return {
                "component": "missing-health",
            }

    aggregator = OperationalHealthAggregator(
        components={
            "missing_health": MissingHealthComponent(),
        }
    )

    result = aggregator.health_check()

    assert result["healthy"] is False
    assert result["components"]["missing_health"]["healthy"] is not True


def test_empty_component_registry_is_unhealthy():
    from operationalhealth import OperationalHealthAggregator

    aggregator = OperationalHealthAggregator(
        components={}
    )

    result = aggregator.health_check()

    assert result["healthy"] is False
    assert result["components"] == {}
