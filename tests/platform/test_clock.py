"""Spec 08 — the injected clock.

Invariant 9 exists so replay is faithful. A clock that is deterministic in name
only makes a replay that is reproducible in name only, so the determinism is
asserted here rather than assumed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from acsoe.platform.clock import Clock, FixedClock, SystemClock


def test_system_clock_returns_timezone_aware_utc() -> None:
    moment = SystemClock().now()
    assert moment.tzinfo is not None
    assert moment.utcoffset() == timedelta(0)


def test_system_clock_moves_forward() -> None:
    clock = SystemClock()
    first = clock.now()
    second = clock.now()
    assert second >= first


def test_both_clocks_satisfy_the_protocol() -> None:
    for clock in (SystemClock(), FixedClock(datetime(2026, 1, 1, tzinfo=UTC))):
        assert isinstance(clock, Clock)


def test_fixed_clock_is_deterministic_across_two_runs() -> None:
    """The replay guarantee: two runs from the same start produce the same series."""

    def run() -> list[datetime]:
        clock = FixedClock(datetime(2026, 9, 8, 12, 0, tzinfo=UTC))
        stamps = [clock.now()]
        for _ in range(5):
            clock.advance(timedelta(minutes=15))
            stamps.append(clock.now())
        return stamps

    assert run() == run()


def test_fixed_clock_does_not_move_on_its_own() -> None:
    clock = FixedClock(datetime(2026, 9, 8, 12, 0, tzinfo=UTC))
    assert clock.now() == clock.now() == datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def test_fixed_clock_advance_returns_the_new_instant() -> None:
    clock = FixedClock(datetime(2026, 9, 8, 12, 0, tzinfo=UTC))
    assert clock.advance(timedelta(hours=1)) == datetime(2026, 9, 8, 13, 0, tzinfo=UTC)


def test_fixed_clock_refuses_to_run_backwards() -> None:
    """Invariant 10. A clock that can rewind lets bar t be computed after bar t+1
    has been seen, which is look-ahead with extra steps."""
    clock = FixedClock(datetime(2026, 9, 8, 12, 0, tzinfo=UTC))
    with pytest.raises(ValueError, match="backwards"):
        clock.advance(timedelta(seconds=-1))


def test_fixed_clock_can_be_repositioned_explicitly() -> None:
    clock = FixedClock(datetime(2026, 9, 8, 12, 0, tzinfo=UTC))
    clock.set(datetime(2026, 1, 1, tzinfo=UTC))
    assert clock.now() == datetime(2026, 1, 1, tzinfo=UTC)


def test_fixed_clock_refuses_a_naive_datetime() -> None:
    """A naive datetime silently encodes whoever wrote the fixture's timezone."""
    with pytest.raises(ValueError, match="naive"):
        FixedClock(datetime(2026, 9, 8, 12, 0))  # noqa: DTZ001


def test_fixed_clock_normalises_a_non_utc_datetime() -> None:
    east = timezone(timedelta(hours=2))
    clock = FixedClock(datetime(2026, 9, 8, 14, 0, tzinfo=east))
    assert clock.now() == datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    assert clock.now().utcoffset() == timedelta(0)
