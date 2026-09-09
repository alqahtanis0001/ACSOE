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
    """A monotonic clock a test moves, and a sleep that moves it."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


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
async def test_concurrent_acquirers_are_serialised_and_stay_inside_the_budget() -> None:
    """Twenty coroutines, a bucket of five, and a refill of ten per second.

    Fifteen of them have to wait, and the elapsed time on the injected clock is the
    proof: fifteen tokens at ten per second is 1.5 seconds, and anything faster than
    that means somebody was granted a token the budget did not have.
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
