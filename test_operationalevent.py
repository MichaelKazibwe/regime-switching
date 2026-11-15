"""
Phase 5B — Operational Event Model Regression
"""

from __future__ import annotations

import pytest

from operationalevent import (
    OperationalEvent,
    OperationalEventError,
    OperationalEventType,
    OperationalSeverity,
    OperationalSource,
    health_check,
    metadata,
)


def build_event() -> OperationalEvent:
    return OperationalEvent.create(
        event_type=OperationalEventType.RISK_REDUCE,
        severity=OperationalSeverity.WARNING,
        source=OperationalSource.RISK,
        message="Portfolio risk reduced.",
        decision_id="decision-001",
        regime="EXPANSION",
        metadata={
            "portfolio_volatility": 0.18,
            "risk_scale": 0.75,
        },
    )


def test_event_creation():
    event = build_event()

    assert event.event_id
    assert event.event_type == "RISK_REDUCE"
    assert event.severity == "WARNING"
    assert event.source == "RISK"
    assert event.decision_id == "decision-001"
    assert event.regime == "EXPANSION"


def test_event_is_immutable():
    event = build_event()

    with pytest.raises(Exception):
        event.message = "mutated"


def test_metadata_is_immutable():
    event = build_event()

    with pytest.raises(TypeError):
        event.metadata["risk_scale"] = 0.10


def test_to_dict_returns_defensive_copy():
    event = build_event()

    payload = event.to_dict()

    payload["metadata"]["risk_scale"] = 999.0

    assert event.metadata["risk_scale"] == 0.75


def test_serialization_roundtrip():
    event = build_event()

    restored = OperationalEvent.from_dict(
        event.to_dict()
    )

    assert restored.event_id == event.event_id
    assert restored.event_type == event.event_type
    assert restored.severity == event.severity
    assert restored.source == event.source
    assert restored.message == event.message
    assert restored.decision_id == event.decision_id
    assert restored.regime == event.regime
    assert dict(restored.metadata) == dict(event.metadata)


def test_invalid_version_rejected():
    payload = build_event().to_dict()

    payload["api_version"] = "999.0.0"

    with pytest.raises(OperationalEventError):
        OperationalEvent.from_dict(payload)


def test_missing_required_field_rejected():
    payload = build_event().to_dict()

    del payload["event_id"]

    with pytest.raises(OperationalEventError):
        OperationalEvent.from_dict(payload)


def test_invalid_timestamp_rejected():
    payload = build_event().to_dict()

    payload["timestamp"] = "not-a-timestamp"

    with pytest.raises(OperationalEventError):
        OperationalEvent.from_dict(payload)


def test_invalid_metadata_rejected():
    payload = build_event().to_dict()

    payload["metadata"] = "invalid"

    with pytest.raises(OperationalEventError):
        OperationalEvent.from_dict(payload)


def test_health_check():
    event = build_event()

    assert event.health_check() is True
    assert health_check() is True


def test_module_metadata():
    result = metadata()

    assert result["module"] == "operationalevent"
    assert result["api_version"] == "1.0.0"
    assert result["immutable"] is True
    assert result["serializable"] is True


def test_distinct_events_have_distinct_ids():
    first = build_event()
    second = build_event()

    assert first.event_id != second.event_id


def test_event_does_not_execute():
    event = build_event()

    public = set(event.__class__.__dict__)

    forbidden = {
        "execute",
        "submit_order",
        "send_order",
        "place_order",
        "broker",
    }

    assert public.isdisjoint(forbidden)