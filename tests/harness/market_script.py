"""A market a criterion can script tick by tick. Spec 100 step 1.

`FakeKrakenClient` answers the four REST calls and nothing else, which is enough for a
gate but not for a round trip: engine 3 `market_sensor` reads a *stream* — a rolling
window of executed trades and a top-of-book quote per pair — and everything downstream of
it, including the paper broker's fills and the console's mark, moves when those move.

So this is the stream half, and it is **scripted rather than simulated**. A criterion says
what traded and when; nothing here decides what the market does. That distinction is the
whole design: a simulator would be a second opinion about price, sitting between the
criterion and the engines, and when a round trip came out wrong there would be two places
to look.

## What is deliberately not here

**No fills, no orders, no ledger.** B's paper broker owns all three (spec 88, operator
ruling 1 of 2026-09-16) and this feeds it rather than duplicating it. A harness that
decided fills would be a third implementation of one fill rule.

**No clock.** The market reads the same injected `Clock` the orchestrator holds, so a
criterion advances time in one place and the feed follows. Asking a test to advance two
things in step is asking it to forget.

## The one non-obvious correctness requirement, and it is not realism

:func:`bar_trades` reconstructs a bar from trades, and **the number of trades per bar has
to vary**. `modelling/features.py` computes `trades_z_*`, a z-score of the trade count
over a lookback; a z-score over a constant series divides by zero, yields NaN, publishes
as null, and engine 13 `anomaly` then correctly refuses the whole market-quality vector as
incomplete. A fixture with a fixed trade count therefore cannot exhibit the property the
criterion is about, which is worse than no fixture.

Found by B twice while building `test_feature_chain_rehearsal.py` — once on a constructed
series with four trades a bar, and again on the archive where `min(trades, 24)` saturated
every bar at the ceiling and made the count constant a second time. The modulus below is
B's fix, restated here rather than imported so the harness does not depend on a test file.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from tests.harness.fake_kraken import FakeKrakenClient

__all__ = [
    "MAX_TRADES_PER_BAR",
    "Bar",
    "ScriptedMarket",
    "bar_trades",
]


class _Clock(Protocol):
    def now(self) -> datetime: ...


#: The ceiling on reconstructed trades per bar. The count only has to *vary*; a bar
#: carrying the several hundred trades a real one does would make every criterion slow
#: for nothing.
MAX_TRADES_PER_BAR = 24


@dataclass(frozen=True)
class Bar:
    """One decision bar a criterion plants, as OHLCVT.

    `Decimal` on the four prices and the volume because they become `TradeTick.price` and
    `TradeTick.qty`, which are `Money` and refuse a float outright.
    """

    ts: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trades: int

    @classmethod
    def flat(cls, ts: int, price: str, *, volume: str = "12.0", trades: int = 40) -> Bar:
        """A bar that opened, traded and closed at one price.

        For the stretches of a scripted market a criterion does not care about — the
        bars before the candidate, the bars a position is simply held through. The high
        and the low equal the close, so nothing here can touch a barrier by accident,
        which is the property that makes a *planted* touch the only touch.
        """
        value = Decimal(price)
        return cls(
            ts=ts,
            open=value,
            high=value,
            low=value,
            close=value,
            volume=Decimal(volume),
            trades=trades,
        )


def bar_trades(bar: Bar, *, pair: str, interval_s: int) -> list[Any]:
    """Trades that rebuild `bar` exactly, in a count that varies bar to bar.

    `build_candles` takes the first price as the open, the last as the close, the maximum
    as the high and the minimum as the low. On a well-formed bar the high is never below
    the open or the close and the low is never above them, so leading with those four
    reproduces all four and any number of filler trades at the close leaves them
    untouched.

    The quantities sum to the bar's volume exactly, with the remainder on the last trade
    rather than spread by rounding: volume reaches `volume_z_*` and a bar whose trades do
    not add up is a bar whose feature row is quietly wrong.
    """
    from acsoe.clients.kraken.contracts import TradeTick

    count = 4 + bar.trades % (MAX_TRADES_PER_BAR - 3)
    part = (bar.volume / count).quantize(Decimal("1e-12"))
    quantities = [part] * (count - 1) + [bar.volume - (count - 1) * part]
    prices = [bar.open, bar.high, bar.low, bar.close]
    prices += [bar.close] * (count - 4)
    step = max(interval_s // (count + 1), 1)
    out: list[Any] = []
    for offset, (price, qty) in enumerate(zip(prices, quantities, strict=True), start=1):
        out.append(
            TradeTick(
                pair=pair,
                ts=datetime.fromtimestamp(bar.ts + offset * step, tz=UTC),
                price=price,
                qty=qty,
            )
        )
    return out


@dataclass
class _PairScript:
    bars: list[Bar] = field(default_factory=list)
    extra: list[Any] = field(default_factory=list)
    quote: tuple[Decimal, Decimal] | None = None


class ScriptedMarket(FakeKrakenClient):
    """The fake Kraken client plus the stream surface, driven by an injected clock.

    One object serves engines 1 and 3, which is how the daemon runs: engine 1 reads
    balances, fees and pair rules off the REST half and engine 3 reads trades and quotes
    off the stream half. Two objects would let a criterion give the account engine one
    view of the world and the market engine another.

    **Everything the stream reports is filtered by `clock.now()`**, so a criterion that
    plants a whole market up front and then advances the clock sees exactly the trades
    that had happened by each tick. Handing an engine a trade from the future is
    look-ahead, and it is the failure that is hardest to see from the outside because
    every number involved is real.
    """

    def __init__(
        self,
        *,
        clock: _Clock,
        interval_s: int,
        published_bars: int,
        pairs: Sequence[str] = (),
    ) -> None:
        super().__init__()
        self._clock = clock
        self._interval_s = interval_s
        self._published_bars = published_bars
        self._scripts: dict[str, _PairScript] = {pair: _PairScript() for pair in pairs}
        self._drained_to: datetime | None = None
        self._gaps: list[Mapping[str, Any]] = []
        self._subscription: tuple[str, ...] = ()

    @property
    def clock(self) -> _Clock:
        """The clock the stream reads. The same object the orchestrator holds.

        Exposed so a criterion advances time in one place: a test that had to move the
        clock and then tell the market about it is a test that will forget.
        """
        return self._clock

    # -- scripting -------------------------------------------------------- #

    def _script(self, pair: str) -> _PairScript:
        return self._scripts.setdefault(pair, _PairScript())

    @property
    def pairs(self) -> tuple[str, ...]:
        return tuple(self._scripts)

    def plant(self, pair: str, bars: Iterable[Bar]) -> None:
        """Plant whole decision bars. Each becomes the trades that rebuild it."""
        self._script(pair).bars.extend(bars)

    def plant_trade(self, pair: str, *, at: datetime, price: str, qty: str = "0.5") -> None:
        """One scripted trade at an exact moment.

        This is how a barrier touch is planted. A criterion that wanted a stop to trigger
        on a particular minute has to put a trade at that price on that minute, because
        that is the only thing engines 21 and 22 can see — and `market_sensor`'s per-tick
        trade range is built from exactly these, so a touch planted between two ticks is
        still seen, which is the property `context.previous_now` exists for.
        """
        from acsoe.clients.kraken.contracts import TradeTick

        self._script(pair).extra.append(
            TradeTick(pair=pair, ts=at, price=Decimal(price), qty=Decimal(qty))
        )

    def set_quote(self, pair: str, *, bid: str, ask: str) -> None:
        """Pin the top of book for a pair.

        Unpinned, the quote follows the last trade the clock has reached, which is what
        keeps a position's mark moving as the market moves. Pinned, it stays put — which
        is how a criterion produces the crossed or stale book engine 4 blocks on.
        """
        self._script(pair).quote = (Decimal(bid), Decimal(ask))

    def record_gap(self, gap: Mapping[str, Any]) -> None:
        """Record a break in the stream. Marked, never healed — invariant 11."""
        self._gaps.append(dict(gap))

    # -- the stream lifecycle --------------------------------------------- #
    #
    # Declared nowhere in `MarketStreamProtocol` and reached anyway: engine 2 takes
    # `set_subscription` with `getattr` and `PaperBroker` forwards all four to the
    # client it wraps, unconditionally. In paper mode the broker **is** the stream every
    # engine sees, so a client missing one of these raises inside the guard chain rather
    # than degrading. See the build log entry of 2026-09-16.

    def start(self) -> None:
        """A no-op. Nothing here connects to anything and there is nothing to start."""

    def stop(self) -> None:
        """A no-op, and deliberately not an error on a stream that never started."""

    def set_subscription(self, pairs: Sequence[str]) -> bool:
        """Accept a subscription, and report it back unchanged.

        Engine 2 sets the scope and then **reads `subscription` back** to learn what it
        is actually recording. A stream that accepted one list and reported another
        would make that read-back meaningless while looking like it worked, so this
        stores exactly what it was given.

        Returns whether the scope changed, which is what the real client returns.
        """
        wanted = tuple(pairs)
        changed = wanted != self._subscription
        self._subscription = wanted
        return changed

    @property
    def subscription(self) -> tuple[str, ...]:
        return self._subscription

    # -- the stream surface ----------------------------------------------- #

    def _trades_through_now(self, pair: str) -> list[Any]:
        now = self._clock.now()
        script = self._scripts[pair]
        out: list[Any] = []
        for bar in script.bars:
            out.extend(bar_trades(bar, pair=pair, interval_s=self._interval_s))
        out.extend(script.extra)
        out = [trade for trade in out if trade.ts <= now]
        out.sort(key=lambda trade: trade.ts)
        return out

    def recent_trades(self) -> tuple[Any, ...]:
        """The rolling window engine 3 rebuilds its candles from, oldest first.

        Trimmed to `market_sensor.published_bars`, because that is the window the live
        stream keeps and a harness that kept more would let a feature lookback fill here
        that could never fill in the daemon. Non-consuming: engine 3 rebuilds the same
        open bar on each of the fifteen ticks it spans.
        """
        now = self._clock.now()
        floor = now - timedelta(seconds=self._published_bars * self._interval_s)
        out: list[Any] = []
        for pair in self._scripts:
            out.extend(trade for trade in self._trades_through_now(pair) if trade.ts > floor)
        out.sort(key=lambda trade: trade.ts)
        return tuple(out)

    def drain_trades(self) -> tuple[Any, ...]:
        """Consuming: every trade since the last call, oldest first."""
        previous = self._drained_to
        self._drained_to = self._clock.now()
        out = [
            trade
            for pair in self._scripts
            for trade in self._trades_through_now(pair)
            if previous is None or trade.ts > previous
        ]
        out.sort(key=lambda trade: trade.ts)
        return tuple(out)

    def drain(self) -> tuple[Any, ...]:
        """Raw frames. Empty here, and that is honest rather than lazy.

        Engine 2 `market_data_recorder` writes what this returns into the archive, and no
        Phase 6 criterion judges the archive — `recording_span_continuous` does, in Phase
        2, against a committed report. Fabricating raw frames would put invented JSONL in
        front of the one engine whose whole job is to write down what actually arrived.
        """
        return ()

    def drain_gaps(self) -> tuple[Mapping[str, Any], ...]:
        """Consuming, so engine 2 stays stateless across cycles."""
        out = tuple(self._gaps)
        self._gaps = []
        return out

    @property
    def gaps(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._gaps)

    @property
    def connected(self) -> bool:
        return True

    def latest_quote(self, pair: str) -> Any:
        """Top of book, or `None` when the stream has never seen the pair.

        `None` and not a zeroed quote: absent is not zero, and engine 4 has to be able to
        tell a pair with no data from a pair with a zero spread. That is the fake being
        no kinder than the real client, which is the rule the whole harness is built on.
        """
        from acsoe.clients.kraken.contracts import QuoteTick

        script = self._scripts.get(pair)
        if script is None:
            return None
        now = self._clock.now()
        if script.quote is not None:
            bid, ask = script.quote
            return QuoteTick(pair=pair, ts=now, bid=bid, ask=ask)
        trades = self._trades_through_now(pair)
        if not trades:
            return None
        last = trades[-1]
        # A symmetric two-basis-point book around the last trade. Arbitrary and
        # deliberately so: a criterion that cares about the spread pins it with
        # `set_quote`, and one that does not needs *a* book rather than a realistic one.
        half = (last.price * Decimal("0.0001")).quantize(Decimal("1e-8"))
        return QuoteTick(pair=pair, ts=last.ts, bid=last.price - half, ask=last.price + half)
