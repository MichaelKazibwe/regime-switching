"""
5J.4 KillSwitch clock-boundary certification tests.
"""

from datetime import datetime, timezone

import pytest

from killswitch import KillSwitch


FIXED_NOW = datetime(
    2026, 10, 5, 12, 34, 56, 789000, tzinfo=timezone.utc
)


def test_injected_clock_controls_activation_timestamp():
    switch = KillSwitch(
        clock=lambda: FIXED_NOW,
    )

    event = switch.activate("TEST_ACTIVATION")

    expected = FIXED_NOW.isoformat()

    assert switch.state().activation_timestamp == expected
    assert event.timestamp == expected


def test_injected_clock_controls_release_timestamp():
    switch = KillSwitch(
        clock=lambda: FIXED_NOW,
    )

    switch.activate("TEST_ACTIVATION")
    event = switch.release("TEST_RELEASE")

    assert switch.state().release_timestamp == FIXED_NOW.isoformat()
    assert event.timestamp == FIXED_NOW.isoformat()


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        KillSwitch(
            clock=lambda: datetime(2026, 10, 5, 12, 0, 0)
        )


def test_clock_must_return_datetime():
    with pytest.raises(TypeError, match="datetime"):
        KillSwitch(
            clock=lambda: "2026-10-05T12:00:00+00:00"
        )


def test_default_clock_remains_utc_aware():
    switch = KillSwitch()

    event = switch.activate("DEFAULT_CLOCK_TEST")

    parsed = datetime.fromisoformat(event.timestamp)

    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None


def test_serialization_preserves_state_with_injected_clock():
    switch = KillSwitch(
        clock=lambda: FIXED_NOW,
    )

    switch.activate("SERIALIZATION_TEST")

    payload = switch.to_dict()
    restored = KillSwitch.from_dict(payload)

    assert restored.state() == switch.state()
