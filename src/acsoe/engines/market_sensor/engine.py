"""Engine 3 `market_sensor` — the decision-bar clock and the market-data view.

Third in the guard chain, and **not a gate**. It publishes three things engine 4 and
the opportunity chain hang off:

* ``bar_closed`` — true only on the tick where a 15-minute decision bar completed.
  Engine 5 `feature` returns ``PASS`` when it is false, and that is what stops the
  opportunity chain on the fourteen ticks in fifteen where no bar closed. **No other
  engine may infer the bar boundary for itself**, and the orchestrator does not know
  about bars at all: cadence is a property of the candle stream, not of `core/`.
* ``candles`` — the closed 15-minute candles, built from trades.
* ``quotes`` — top of book per pair, per tick, carrying ``spread_pct``. Ratified as
  engine 3's by the lead on 2026-09-09: engine 1 is the *account* engine and engine 3
  is the *market-data* engine, and engine 4 blocks on three market-data faults that
  should all arrive from one place.

**The mixed cadence is deliberate**: ``quotes`` is per tick and ``bar_closed`` is per
bar. They live together because they are both statements about the market feed.

**A missing candle is never invented.** A bar in which nothing traded produces no
candle; its timestamp is reported in ``missing_bars`` and the feature layer decides.
**A partial bar is never published as a candle** either — that is look-ahead, and
invariant 10 forbids it.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, ClassVar

from acsoe.core.contracts import (
    BaseEngine,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.engines.market_sensor.candles import (
    Candle,
    bar_open_seconds,
    build_candles,
    missing_bar_timestamps,
)
from acsoe.engines.market_sensor.contracts import (
    MarketSensorState,
    QuoteView,
    spread_ratio,
)

__all__ = ["MarketSensorEngine", "bar_closed_on"]


def bar_closed_on(now_s: int, *, interval_s: int, tick_s: int) -> bool:
    """Did a decision bar complete between the previous tick and this one?

    Stateless by construction, which is the requirement: `state` is fresh every tick
    and an engine may not carry anything across cycles, so there is nowhere to keep
    "the bar we last saw".

    It is **not** ``now % interval == 0``. ``context.now`` is stamped from a real clock
    and carries microseconds, so an exact-boundary test would essentially never fire.
    Asking whether the bar index changed since one tick ago fires exactly once per bar
    in a regular loop, and still fires — once — if the loop ran late or skipped a tick,
    which is the behaviour that matters when the daemon has been busy.
    """
    if interval_s <= 0 or tick_s <= 0:
        raise ValueError("interval_s and tick_s must be positive")
    return (now_s // interval_s) != ((now_s - tick_s) // interval_s)


class MarketSensorEngine(BaseEngine):
    """15-minute candles, the `bar_closed` signal, and the live spread."""

    name: ClassVar[str] = "market_sensor"
    number: ClassVar[int] = 3
    #: Registry table in `context/engine-contracts.md` marks engine 3 with no Gate.
    is_gate: ClassVar[bool] = False

    # ARG002: `state` is unused and stays in the signature — the interface is fixed.
    # This engine reads the feed, not another engine's output.
    def process(self, context: EngineContext, state: State) -> EngineResult:  # noqa: ARG002
        started = time.perf_counter()

        # A missing key here raises `ConfigKeyError`, the orchestrator turns it into
        # ERROR, and ERROR blocks. That is the correct fail-closed behaviour for a
        # threshold nobody has set, and it is why no default appears in this file.
        interval_s = int(context.config.get("timeframes.decision_bar_s"))
        tick_s = int(context.config.get("timeframes.loop_tick_s"))
        published_bars = int(context.config.get("market_sensor.published_bars"))

        now_s = int(context.now.timestamp())
        closed = bar_closed_on(now_s, interval_s=interval_s, tick_s=tick_s)
        closed_bar_ts = (now_s // interval_s) * interval_s - interval_s if closed else None

        stream = context.clients.kraken
        recent = getattr(stream, "recent_trades", None)
        if not callable(recent):
            # A client with no stream — C's fake Kraken client is exactly that. The
            # bar clock still runs, because it is arithmetic over `context.now` and
            # owes nothing to the feed. Reported, not raised: engine 4 decides whether
            # missing data blocks, and raising here would take the guard chain to
            # ERROR on a tick where nothing is wrong.
            payload = MarketSensorState(
                bar_closed=closed,
                closed_bar_ts=closed_bar_ts,
                interval_s=interval_s,
                stream_available=False,
            )
            return EngineResult(
                engine=self.name,
                status=EngineStatus.OK,
                data=payload.to_state(),
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        trades = tuple(recent())
        candles = build_candles(trades, interval_s=interval_s)
        # The bar containing `now` is still open. Publishing it as a candle would put a
        # partial high, low and close in front of the feature engine — look-ahead by
        # any other name, and invariant 10 forbids it.
        current_bar = bar_open_seconds(now_s, interval_s=interval_s)
        closed_candles = [candle for candle in candles if candle.ts < current_bar]
        missing = missing_bar_timestamps(closed_candles, interval_s=interval_s)

        payload = MarketSensorState(
            bar_closed=closed,
            closed_bar_ts=closed_bar_ts,
            interval_s=interval_s,
            candles=tuple(
                candle.state_dict() for candle in self._latest(closed_candles, published_bars)
            ),
            missing_bars=tuple(missing),
            quotes=self._quotes(context, trades),
            stream_available=True,
            trades_seen=len(trades),
        )
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            data=payload.to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    @staticmethod
    def _latest(candles: list[Candle], published_bars: int) -> list[Candle]:
        """The most recent ``published_bars`` per pair, oldest first.

        Bounded per pair rather than overall, so a busy pair cannot push a quiet one
        out of `state` entirely and leave a consumer looking at nothing.
        """
        by_pair: dict[str, list[Candle]] = {}
        for candle in candles:
            by_pair.setdefault(candle.pair, []).append(candle)
        kept: list[Candle] = []
        for pair_candles in by_pair.values():
            kept.extend(pair_candles[-published_bars:])
        kept.sort(key=lambda candle: (candle.pair, candle.ts))
        return kept

    @staticmethod
    def _quotes(context: EngineContext, trades: tuple[Any, ...]) -> dict[str, dict[str, Any]]:
        """Top of book for every pair the stream knows about.

        The pair set comes from the trades seen this window plus anything the stream
        will answer for. A pair with no quote is simply absent — **not present with a
        zero spread**, which is the one shape the cost gate must never be handed.
        """
        latest_quote = getattr(context.clients.kraken, "latest_quote", None)
        if not callable(latest_quote):
            return {}
        now_s = context.now.timestamp()
        quotes: dict[str, dict[str, Any]] = {}
        for pair in sorted({str(getattr(trade, "pair", "")) for trade in trades} - {""}):
            quote = latest_quote(pair)
            if quote is None:
                continue
            try:
                ratio = spread_ratio(Decimal(quote.bid), Decimal(quote.ask))
            except (ValueError, ArithmeticError):
                # An unusable quote is left out rather than published as a zero.
                continue
            quotes[pair] = QuoteView(
                pair=pair,
                ts=quote.ts.isoformat().replace("+00:00", "Z"),
                bid=quote.bid,
                ask=quote.ask,
                spread=quote.ask - quote.bid,
                spread_pct=ratio,
                age_s=now_s - quote.ts.timestamp(),
            ).state_dict()
        return quotes
