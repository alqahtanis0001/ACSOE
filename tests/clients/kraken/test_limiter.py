"""Spec 25 — the rate limiter serialises bursts without exceeding the budget.

Time and sleeping are injected, so the budget is asserted exactly rather than by
waiting. A test that slept for real would be slow *and* flaky, and it would assert
"about the right rate" rather than "never above the configured one".
"""

from __future__ import annotations

import asyncio

import pytest

from acsoe.clients.kraken import RateLimiter


class FakeTime:
    """A monotonic clock a test moves, and a sleep that moves it.

    Note what this sleep does *not* do: it never awaits, so it never suspends, so a
    coroutine waiting on it runs its whole critical section before the next one
    starts. That makes the budget arithmetic below exact and easy to read, and it
    quietly removes every trace of real concurrency. Where the concurrency is the
    subject, use `YieldingTime`.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class YieldingTime(FakeTime):
    """`FakeTime`, but the sleep hands control back to the event loop.

    `asyncio.sleep(0)` yields a single scheduling turn and waits no real time, so
    time stays injected while coroutines genuinely interleave — which is what makes
    the lock contended, and contention is what binds an `asyncio.Lock` to a loop.
    """

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


def build(capacity: float, refill: float) -> tuple[RateLimiter, FakeTime]:
    clock = FakeTime()
    return (
        RateLimiter(
            capacity=capacity,
            refill_per_second=refill,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        ),
        clock,
    )


@pytest.mark.asyncio
async def test_a_burst_within_the_capacity_never_waits() -> None:
    limiter, clock = build(5, 1)
    for _ in range(5):
        await limiter.acquire()
    assert clock.slept == []
    assert limiter.granted == 5


@pytest.mark.asyncio
async def test_a_burst_beyond_the_capacity_waits_for_the_refill() -> None:
    limiter, clock = build(3, 2)  # 2 tokens per second
    for _ in range(3):
        await limiter.acquire()
    await limiter.acquire()
    assert limiter.waits == 1
    assert clock.slept == [pytest.approx(0.5)]
    assert clock.now == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_twenty_acquirers_never_exceed_the_budget_between_them() -> None:
    """Twenty coroutines, a bucket of five, and a refill of ten per second.

    Fifteen of them have to wait, and the elapsed time on the injected clock is the
    proof: fifteen tokens at ten per second is 1.5 seconds, and anything faster than
    that means somebody was granted a token the budget did not have.

    **Renamed.** It used to say "serialised", and it has never demonstrated that:
    `FakeTime.sleep` never suspends, so these twenty run strictly one after another
    and the lock is never contended. The arithmetic it does prove is real and is worth
    keeping — the name was the part that overclaimed. Contention is covered by
    `test_one_limiter_survives_a_new_event_loop_every_tick_and_keeps_its_budget`,
    which uses `YieldingTime` for exactly that reason.
    """
    limiter, clock = build(5, 10)
    await asyncio.gather(*(limiter.acquire() for _ in range(20)))
    assert limiter.granted == 20
    assert clock.now == pytest.approx(1.5)
    assert limiter.tokens() == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_the_bucket_refills_no_further_than_its_capacity() -> None:
    limiter, clock = build(4, 1)
    await limiter.acquire(4)
    clock.now += 1_000
    assert limiter.tokens() == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_a_cost_larger_than_the_capacity_is_refused_rather_than_waited_on() -> None:
    limiter, _ = build(2, 1)
    with pytest.raises(ValueError, match="wait forever"):
        await limiter.acquire(3)


def test_a_nonsense_budget_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="capacity"):
        RateLimiter(capacity=0, refill_per_second=1)
    with pytest.raises(ValueError, match="refill_per_second"):
        RateLimiter(capacity=1, refill_per_second=0)


def test_one_limiter_survives_a_new_event_loop_every_tick_and_keeps_its_budget() -> None:
    """The daemon holds one limiter for its whole life and gets a new loop per tick.

    `platform/aio.py` runs one `asyncio.run` per engine call, deliberately, so every
    tick has its own event loop while this object is held across all of them. An
    `asyncio.Lock` binds itself to the first loop it needs a future on — which
    happens on **contention**, not on construction — and raises on every later one,
    so the daemon works for a few ticks and then stops. The bucket here is smaller
    than the burst so that the third acquirer genuinely waits and the lock is
    genuinely contended; with a bucket that is never short nothing waits, nothing
    binds and this test would pass against the broken version.

    **Both halves are asserted.** Not raising is the easy half, and "build a fresh
    limiter each tick" would satisfy it — while handing every tick a full bucket and
    removing the rate limit altogether. So the budget is asserted to have carried
    over: after three ticks of three acquisitions the count is nine and the tokens
    spent are real.

    Deliberately not `@pytest.mark.asyncio`: the point is the *absence* of an outer
    loop, which is the daemon's actual situation. Running this inside one would
    reuse a single loop and prove nothing.

    **And the injected sleep has to yield.** `FakeTime.sleep` only advances a
    counter, and an `async def` with no `await` in it never suspends — so the first
    acquirer runs the whole critical section before the second one starts, the lock
    is never contended, and this test passes against the broken limiter. It did,
    the first time I wrote it. `YieldingTime` adds one `await asyncio.sleep(0)`,
    which hands control back to the loop and waits no real time. Time is still
    injected; the concurrency is no longer accidentally removed with it.
    """
    clock = YieldingTime()
    limiter = RateLimiter(
        capacity=2,
        refill_per_second=1000.0,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    async def one_tick() -> None:
        await asyncio.gather(limiter.acquire(), limiter.acquire(), limiter.acquire())

    for _ in range(3):
        asyncio.run(one_tick())

    assert limiter.granted == 9
    assert limiter.waits >= 3
    assert clock.now > 0.0
