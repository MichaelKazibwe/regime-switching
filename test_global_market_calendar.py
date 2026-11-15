import pytest
from global_market_calendar import (
    is_regular_session,
    latest_completed_session,
    next_close,
)


def test_hong_kong_lunch_is_not_an_open_session():
    assert is_regular_session("XHKG", "2026-10-30T11:00:00+08:00")
    assert not is_regular_session("XHKG", "2026-10-30T12:30:00+08:00")
    assert is_regular_session("XHKG", "2026-10-30T14:00:00+08:00")


def test_each_venue_has_its_own_completed_session():
    now = "2026-10-30T17:00:00Z"
    assert latest_completed_session("XHKG", now) == "2026-10-30"
    assert latest_completed_session("XLON", now) == "2026-10-30"
    assert latest_completed_session("XNYS", now) == "2026-10-29"
    assert latest_completed_session("XJSE", now) == "2026-10-30"


def test_next_fill_never_uses_decision_close():
    assert next_close("XNYS", "2026-10-30T20:00:00Z").startswith("2026-11-02T21:00")


def test_unaware_and_unsupported_markets_are_blocked():
    with pytest.raises(ValueError, match="Aware"):
        is_regular_session("XNYS", "2026-10-30")
    with pytest.raises(ValueError, match="unsupported"):
        is_regular_session("UNKNOWN", "2026-10-30T10:00:00Z")
