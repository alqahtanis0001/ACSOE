"""The one rate limiter, shared by both transports.

A token bucket, and nothing cleverer. Kraken counts calls against a per-account
budget that refills over time, which is exactly what a bucket models: a burst is
allowed up to the capacity and then the caller waits at the refill rate.

Two properties are the point of the class and both are asserted by its tests.

**It serialises.** Acquisitions are taken under a lock and granted in arrival
order, so twenty coroutines that all want a token do not each look at a full
bucket at the same moment and all decide they may go. A limiter that permits that
is not a limiter, it is a counter.

**Time and sleeping are injected.** The default is ``time.monotonic`` and
``asyncio.sleep``; a test passes a clock it controls and a sleep that advances it,
so the budget is asserted exactly rather than by waiting and hoping. ``monotonic``
rather than wall time, because a wall-clock step backwards would refill the bucket
for free.

The budget itself is a constructor argument with no default. A rate limit is an
operational parameter, and picking one here would be a literal in the one file
whose job is to stop the system exceeding it.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

__all__ = ["RateLimiter"]


class RateLimiter:
    """A token bucket with an injectable clock.

    :param capacity: the largest burst permitted, in tokens.
    :param refill_per_second: tokens added per second, up to ``capacity``.
    :param monotonic: the time source. Monotonic seconds, never wall time.
    :param sleep: how to wait. Injected so a test never actually waits.
    """

    def __init__(
        self,
        *,
        capacity: float,
        refill_per_second: float,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_per_second <= 0:
            raise ValueError("refill_per_second must be positive")
        self._capacity = float(capacity)
        self._refill_per_second = float(refill_per_second)
        self._monotonic = monotonic
        self._sleep = sleep
        self._tokens = float(capacity)
        self._updated_at = monotonic()
        self._lock = asyncio.Lock()
        self._lock_loop: asyncio.AbstractEventLoop | None = None
        self._granted = 0
        self._waits = 0

    def _loop_lock(self) -> asyncio.Lock:
        """The lock, belonging to the loop that is running right now.

        **The limiter outlives the event loop and the lock cannot.** The runtime
        loop is synchronous and ``platform/aio.py`` runs one ``asyncio.run`` per
        engine call, so there is a fresh loop every tick — while this object is
        held for the life of the daemon, because the budget is an account-level
        fact and a limiter rebuilt each tick would hand every tick a full bucket
        and remove the rate limit entirely.

        An ``asyncio.Lock`` binds to the first loop it needs a future on and raises
        on any later one. It binds on *contention*, not on construction, so the
        failure arrives after however many ticks it takes for the bucket to run
        short — which is a daemon that works and then stops, not one that never
        started.

        Replacing the lock when the loop changes is safe because concurrency only
        ever exists inside one ``asyncio.run``: the previous loop is closed and
        nothing can still be waiting. The token state is deliberately **not**
        touched here — it is the thing that has to survive.
        """
        loop = asyncio.get_running_loop()
        if self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    @property
    def capacity(self) -> float:
        return self._capacity

    @property
    def granted(self) -> int:
        """How many acquisitions have been granted. Diagnostics only."""
        return self._granted

    @property
    def waits(self) -> int:
        """How many acquisitions had to wait for a refill."""
        return self._waits

    def tokens(self) -> float:
        """Tokens available right now, without taking any."""
        self._refill()
        return self._tokens

    def _refill(self) -> None:
        now = self._monotonic()
        elapsed = now - self._updated_at
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_second)
            self._updated_at = now

    async def acquire(self, cost: float = 1.0) -> None:
        """Take ``cost`` tokens, waiting for a refill if the bucket is short.

        Raises ``ValueError`` when ``cost`` exceeds the capacity, because that
        request can never be satisfied and waiting forever is worse than saying so.
        """
        if cost <= 0:
            raise ValueError("cost must be positive")
        if cost > self._capacity:
            raise ValueError(
                f"a cost of {cost} can never be granted by a bucket of capacity "
                f"{self._capacity}; it would wait forever"
            )
        async with self._loop_lock():
            self._refill()
            if self._tokens < cost:
                self._waits += 1
                await self._sleep((cost - self._tokens) / self._refill_per_second)
                self._refill()
            # Deducted unconditionally, and the balance is allowed to go very
            # slightly negative. **This is not a rounding shortcut, it is what
            # makes the method terminate.** The obvious version re-checks
            # `tokens >= cost` in a loop and sleeps the shortfall again if it is
            # still short — and floating point guarantees it eventually will be:
            # after one wait the refill lands a few ulps under `cost`, the next
            # shortfall is ~1e-16, the sleep for it is ~1e-17, and adding that to
            # a clock already at 0.6 changes nothing at all. The loop then spins
            # forever with no CPU time attributable to it and no error, which is
            # what a hung test suite looks like. Carrying the fraction of a token
            # forward instead is exact over any number of calls, because the next
            # refill starts from the deficit.
            self._tokens -= cost
            self._granted += 1
