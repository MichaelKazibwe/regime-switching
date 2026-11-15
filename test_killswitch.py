"""
Phase 5D — Kill Switch Regression Tests
=======================================

Tests the standalone production kill switch before integration with
ProductionExecutionGate.

Certification areas
-------------------
1. Initial state
2. Activation
3. Release
4. Idempotency
5. require_clear()
6. Operational events
7. Serialization
8. Restart preservation
9. Fail-closed restoration
10. Health / metadata contracts
11. No execution authority
"""

from __future__ import annotations

from killswitch import KillSwitch
from exceptions import RiskLimitBreach
from operationalevent import (
    OperationalEvent,
    OperationalEventError,
    OperationalEventType,
    OperationalSeverity,
    OperationalSource,
)


# ======================================================================
# INITIAL STATE
# ======================================================================


def test_initial_state_is_released() -> None:
    """Kill switch must start released by default."""
    switch = KillSwitch()

    assert switch.is_active() is False
    assert switch.state().active is False

    summary = switch.summary()

    assert summary["active"] is False
    assert summary["activation_count"] == 0
    assert summary["release_count"] == 0
    assert summary["event_count"] == 0


# ======================================================================
# ACTIVATION
# ======================================================================


def test_activation_changes_state() -> None:
    """Activation must move the switch into ACTIVE state."""
    switch = KillSwitch()

    event = switch.activate(
        "Emergency risk test"
    )

    assert switch.is_active() is True
    assert switch.state().active is True
    assert switch.state().activation_timestamp is not None
    assert (
        switch.state().activation_reason
        == "Emergency risk test"
    )

    assert event.event_type == (
        OperationalEventType.KILL_SWITCH_ACTIVATED
    )

    assert event.severity == (
        OperationalSeverity.CRITICAL
    )

    assert event.source == (
        OperationalSource.KILL_SWITCH
    )


# ======================================================================
# REQUIRE CLEAR
# ======================================================================


def test_require_clear_blocks_when_active() -> None:
    """An active switch must block execution authorization."""
    switch = KillSwitch()

    switch.activate(
        "Block execution test"
    )

    try:
        switch.require_clear()
    except RiskLimitBreach:
        pass
    else:
        raise AssertionError(
            "Active kill switch did not raise "
            "RiskLimitBreach."
        )


def test_require_clear_passes_when_released() -> None:
    """A released switch must permit downstream authorization."""
    switch = KillSwitch()

    switch.require_clear()

    switch.activate(
        "Temporary block"
    )

    switch.release(
        "Temporary block removed"
    )

    switch.require_clear()


# ======================================================================
# RELEASE
# ======================================================================


def test_release_changes_state() -> None:
    """Release must return the switch to RELEASED."""
    switch = KillSwitch()

    switch.activate(
        "Release test"
    )

    event = switch.release(
        "Risk cleared"
    )

    assert switch.is_active() is False
    assert switch.state().active is False
    assert switch.state().release_timestamp is not None
    assert (
        switch.state().release_reason
        == "Risk cleared"
    )

    assert event.event_type == (
        OperationalEventType.KILL_SWITCH_RELEASED
    )

    assert event.source == (
        OperationalSource.KILL_SWITCH
    )


# ======================================================================
# IDEMPOTENCY
# ======================================================================


def test_activation_is_idempotent() -> None:
    """
    Activating an already-active switch must not create
    another state transition.
    """
    switch = KillSwitch()

    switch.activate(
        "First activation"
    )

    first_timestamp = (
        switch.state().activation_timestamp
    )

    first_count = (
        switch.activation_count
    )

    second = switch.activate(
        "Second activation"
    )

    assert switch.is_active() is True

    assert (
        switch.state().activation_timestamp
        == first_timestamp
    )

    assert (
        switch.activation_count
        == first_count
    )

    assert second.event_type == (
        OperationalEventType.KILL_SWITCH_ACTIVATED
    )

    assert (
        second.metadata["idempotent"]
        is True
    )


def test_release_is_idempotent() -> None:
    """
    Releasing an already-released switch must not create
    another state transition.
    """
    switch = KillSwitch()

    switch.release(
        "Already clear"
    )

    assert switch.is_active() is False

    first_count = (
        switch.release_count
    )

    second = switch.release(
        "Still clear"
    )

    assert switch.is_active() is False

    assert (
        switch.release_count
        == first_count
    )

    assert second.event_type == (
        OperationalEventType.KILL_SWITCH_RELEASED
    )

    assert (
        second.metadata["idempotent"]
        is True
    )


# ======================================================================
# OPERATIONAL EVENT CONTRACT
# ======================================================================


def test_activation_event_is_valid_operational_event() -> None:
    """Activation events must conform to Phase 5B."""
    switch = KillSwitch()

    event = switch.activate(
        "Operational event test"
    )

    assert isinstance(
        event,
        OperationalEvent,
    )

    assert event.event_id
    assert event.timestamp

    serialized = event.to_dict()

    restored = OperationalEvent.from_dict(
        serialized
    )

    assert (
        restored.event_id
        == event.event_id
    )

    assert (
        restored.event_type
        == event.event_type
    )

    assert (
        restored.source
        == OperationalSource.KILL_SWITCH
    )


# ======================================================================
# SERIALIZATION
# ======================================================================


def test_serialization_roundtrip() -> None:
    """Kill-switch state must survive serialization."""
    switch = KillSwitch()

    switch.activate(
        "Serialization test"
    )

    payload = switch.to_dict()

    restored = KillSwitch.from_dict(
        payload
    )

    assert restored.is_active() is True

    assert (
        restored.state().activation_timestamp
        == switch.state().activation_timestamp
    )

    assert (
        restored.state().activation_reason
        == switch.state().activation_reason
    )

    assert (
        restored.activation_count
        == switch.activation_count
    )

    assert (
        restored.release_count
        == switch.release_count
    )

    assert (
        len(restored.event_history)
        == len(switch.event_history)
    )


# ======================================================================
# RESTART SAFETY
# ======================================================================


def test_active_state_survives_restart() -> None:
    """
    An ACTIVE kill switch must remain ACTIVE after restoration.
    """
    original = KillSwitch()

    original.activate(
        "Restart safety test"
    )

    persisted = original.to_dict()

    restarted = KillSwitch.from_dict(
        persisted
    )

    assert restarted.is_active() is True

    try:
        restarted.require_clear()
    except RiskLimitBreach:
        pass
    else:
        raise AssertionError(
            "Restarted ACTIVE kill switch "
            "allowed authorization."
        )


def test_released_state_survives_restart() -> None:
    """
    A RELEASED kill switch must remain RELEASED after restoration.
    """
    original = KillSwitch()

    original.activate(
        "Restart release test"
    )

    original.release(
        "Risk cleared"
    )

    persisted = original.to_dict()

    restarted = KillSwitch.from_dict(
        persisted
    )

    assert restarted.is_active() is False

    restarted.require_clear()


# ======================================================================
# FAIL-CLOSED RESTORATION
# ======================================================================


def test_missing_api_version_is_rejected() -> None:
    """Missing API version must not silently restore state."""
    switch = KillSwitch()

    payload = switch.to_dict()

    del payload["api_version"]

    try:
        KillSwitch.from_dict(payload)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Missing API version was accepted."
        )


def test_invalid_api_version_is_rejected() -> None:
    """Unknown API versions must be rejected."""
    switch = KillSwitch()

    payload = switch.to_dict()

    payload["api_version"] = "999.0.0"

    try:
        KillSwitch.from_dict(payload)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Invalid API version was accepted."
        )


def test_missing_state_is_rejected() -> None:
    """Missing critical state must be rejected."""
    switch = KillSwitch()

    payload = switch.to_dict()

    del payload["state"]

    try:
        KillSwitch.from_dict(payload)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Missing kill-switch state was accepted."
        )


def test_active_state_without_timestamp_is_rejected() -> None:
    """
    ACTIVE state without an activation timestamp must be
    rejected rather than repaired into a valid state.
    """
    switch = KillSwitch()

    payload = switch.to_dict()

    payload["state"]["active"] = True
    payload["state"]["activation_timestamp"] = None

    try:
        KillSwitch.from_dict(payload)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Malformed ACTIVE state was accepted."
        )


def test_negative_counters_are_rejected() -> None:
    """Invalid lifecycle counters must be rejected."""
    switch = KillSwitch()

    payload = switch.to_dict()

    payload["activation_count"] = -1

    try:
        KillSwitch.from_dict(payload)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Negative activation count was accepted."
        )


def test_invalid_event_history_is_rejected() -> None:
    """Malformed operational event history must be rejected."""
    switch = KillSwitch()

    payload = switch.to_dict()

    payload["event_history"] = [
        {"invalid": "event"}
    ]

    try:
        KillSwitch.from_dict(payload)
    except (
        TypeError,
        ValueError,
        OperationalEventError,
    ):
        pass
    else:
        raise AssertionError(
            "Invalid event history was accepted."
        )


# ======================================================================
# HEALTH / METADATA
# ======================================================================


def test_health_check() -> None:
    """Health contract must remain available in both states."""
    switch = KillSwitch()

    health = switch.health_check()

    assert health["healthy"] is True
    assert health["production_control"] is True
    assert health["execution_authority"] is False
    assert health["execution_blocked"] is False

    switch.activate(
        "Health test"
    )

    health = switch.health_check()

    assert health["healthy"] is True
    assert health["execution_blocked"] is True


def test_metadata() -> None:
    """Metadata must explicitly establish architectural boundaries."""
    switch = KillSwitch()

    metadata = switch.metadata()

    assert metadata["component"] == "KillSwitch"
    assert metadata["api_version"] == "1.0.0"
    assert metadata["phase"] == "5D"

    assert metadata["production_control"] is True

    assert metadata["execution_authority"] is False
    assert metadata["order_authorization"] is False
    assert metadata["broker_submission"] is False
    assert metadata["broker_routing"] is False
    assert metadata["account_mutation"] is False


# ======================================================================
# SIDE-EFFECT BOUNDARY
# ======================================================================


def test_kill_switch_does_not_create_execution_artifacts() -> None:
    """
    The kill switch must remain an operational control only.

    It must not expose order, routing, broker, or execution
    responsibilities.
    """
    switch = KillSwitch()

    public_methods = set(
        switch.PUBLIC_METHODS
    )

    forbidden = {
        "authorize",
        "submit_order",
        "route_order",
        "execute_order",
        "execute",
        "place_order",
    }

    assert public_methods.isdisjoint(
        forbidden
    )


# ======================================================================
# FULL LIFECYCLE
# ======================================================================


def test_full_lifecycle() -> None:
    """
    Complete lifecycle:

        RELEASED
           ↓
        ACTIVE
           ↓
        restart
           ↓
        ACTIVE
           ↓
        RELEASED
    """
    switch = KillSwitch()

    assert switch.is_active() is False

    switch.activate(
        "Full lifecycle activation"
    )

    assert switch.is_active() is True

    restarted = KillSwitch.from_dict(
        switch.to_dict()
    )

    assert restarted.is_active() is True

    restarted.release(
        "Full lifecycle release"
    )

    assert restarted.is_active() is False

    restarted.require_clear()


# ======================================================================
# RUN DIRECTLY
# ======================================================================


if __name__ == "__main__":
    import pytest

    raise SystemExit(
        pytest.main(
            [__file__, "-v"]
        )
    )