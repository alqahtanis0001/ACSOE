"""The injected clock.

Invariant 9: engines receive ``context.now`` and never call ``datetime.now()``.
That is what makes historical replay faithful and what makes look-ahead bias
structurally impossible rather than merely discouraged. The orchestrator holds
the clock, stamps ``context.now`` once per tick, and no engine ever sees it.

Two implementations:

* :class:`SystemClock` — the real UTC clock, used by ``acsoe engine`` in paper
  and live modes.
* :class:`FixedClock` — a controllable clock for tests and replay. It only
  moves when something moves it, so a replay produces byte-identical results
  across two runs.

Both return timezone-aware UTC. A naive datetime is refused rather than assumed
to be UTC: an off-by-one-timezone timestamp on a trade is the kind of defect that
survives every test and shows up in a dissertation's results table.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Structural match for the ``Clock`` Protocol declared in ``core/contracts.py``.

    Declared here as well so ``platform/`` stays importable on its own and so a
    conformance test has something to check against. ``core/`` remains the
    authority on the shape; this must not diverge from it.
    """

    def now(self) -> datetime:
        """The current instant, timezone-aware and in UTC."""
        ...


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError(
            "a naive datetime has no defined instant; pass a timezone-aware "
            "UTC datetime rather than letting the local timezone be guessed"
        )
    return moment.astimezone(UTC)


class SystemClock:
    """The real clock. UTC, timezone-aware, monotonic only as far as the OS is."""

    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)

    def __repr__(self) -> str:
        return "SystemClock()"


class FixedClock:
    """A clock that only moves when it is moved.

    Used by tests and by replay. Construction normalises to UTC and refuses a
    naive datetime, so a fixture cannot silently encode the author's timezone.
    """

    __slots__ = ("_now",)

    def __init__(self, at: datetime) -> None:
        self._now = _as_utc(at)

    def now(self) -> datetime:
        return self._now

    def set(self, at: datetime) -> None:
        """Jump to an absolute instant."""
        self._now = _as_utc(at)

    def advance(self, delta: timedelta) -> datetime:
        """Move forward by ``delta`` and return the new instant.

        Refuses to go backwards. Replay walks a timeline forward; a clock that
        can rewind would let a feature at bar *t* be computed after a later bar
        had already been seen, which is exactly the look-ahead invariant 10
        forbids.
        """
        if delta < timedelta(0):
            raise ValueError("a clock does not run backwards; use set() if you mean to reposition")
        self._now = self._now + delta
        return self._now

    def __repr__(self) -> str:
        return f"FixedClock({self._now.isoformat()})"
