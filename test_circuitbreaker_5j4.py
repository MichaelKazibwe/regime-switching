"""
5J.4 CircuitBreaker clock-boundary certification tests.
"""

from datetime import datetime, timezone

import pytest

from circuitbreaker import CircuitBreaker


FIXED_NOW = datetime(
    2026, 10, 5, 12, 34, 56, 789000, tzinfo=timezone.utc
)


def test_injected_clock_controls_failure_timestamp():
    breaker = CircuitBreaker(
        threshold=2,
        clock=lambda: FIXED_NOW,
    )

    event = breaker.record_failure("TEST_FAILURE")

    expected = FIXED_NOW.isoformat()

    assert breaker.state().last_failure_at == expected
    assert event.timestamp == expected


def test_injected_clock_controls_open_timestamp():
    breaker = CircuitBreaker(
        threshold=1,
        clock=lambda: FIXED_NOW,
    )

    breaker.record_failure("OPEN_TEST")

    assert breaker.state().opened_at == FIXED_NOW.isoformat()
    assert breaker.state().last_failure_at == FIXED_NOW.isoformat()


def test_injected_clock_controls_reset_timestamp():
    breaker = CircuitBreaker(
        threshold=1,
        clock=lambda: FIXED_NOW,
    )

    breaker.record_failure("OPEN_TEST")
    event = breaker.reset("RESET_TEST")

    assert breaker.state().last_reset_at == FIXED_NOW.isoformat()
    assert event.timestamp == FIXED_NOW.isoformat()


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        CircuitBreaker(
            clock=lambda: datetime(2026, 10, 5, 12, 0, 0)
        )


def test_clock_must_return_datetime():
    with pytest.raises(TypeError, match="datetime"):
        CircuitBreaker(clock=lambda: "2026-10-05T12:00:00+00:00")


def test_default_clock_remains_utc_aware():
    breaker = CircuitBreaker(threshold=1)

    breaker.record_failure("DEFAULT_CLOCK_TEST")

    timestamp = breaker.state().last_failure_at

    assert timestamp is not None

    parsed = datetime.fromisoformat(timestamp)

    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None


def test_serialization_preserves_state_with_injected_clock():
    breaker = CircuitBreaker(
        threshold=1,
        clock=lambda: FIXED_NOW,
    )

    breaker.record_failure("SERIALIZATION_TEST")

    payload = breaker.to_dict()
    restored = CircuitBreaker.from_dict(payload)

    assert restored.state() == breaker.state()
