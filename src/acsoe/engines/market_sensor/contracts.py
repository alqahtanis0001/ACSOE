"""What engine 3 `market_sensor` publishes into ``state["market_sensor"]``.

Two seams from `context/ownership.md` live here, and one cross-chain key the lead has
ratified:

* ``bar_closed`` — the decision-bar tick. Read by engine 5 `feature` (C), which returns
  ``PASS`` when it is false, which is what stops the opportunity chain on the fourteen
  ticks in fifteen where no bar closed. **No other engine may infer the bar boundary
  for itself**, and the orchestrator does not know about bars at all.
* ``candles`` — the closed 15-minute candles. Read by C.
* ``quotes[pair]["spread_pct"]`` — the live spread. Read by engine 4 `data_guard` (A)
  and engine 10 `cost` (B). Ratified by the lead on 2026-09-09: engine 1 is the
  *account* engine, engine 3 is the *market-data* engine, and engine 4 blocks on three
  market-data faults that should all arrive from one place.
* ``trade_ranges[pair]`` — the low, the high and the trade count since the previous
  tick. Spec 85, Phase 6. Read by the fill simulator (B, spec 88) and by engines 21
  `position_manager` and 22 `exit` (B, specs 92 and 93), so that all three agree about
  what the market did *between* one-minute ticks rather than each sampling a quote.

**The mixed cadence is deliberate.** ``quotes`` is per tick; ``bar_closed`` and
``candles`` are per bar. They sit in one engine because they are both statements about
the market feed, and splitting them would give engine 4 two sources for three faults.

**Money crosses `state` as an exact decimal string.** Never a `float`: the validator in
`core/contracts.py` refuses a `Decimal` and *accepts* a `float`, so the reflexive cast
on hitting that refusal is the dangerous mistake.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from acsoe.clients.kraken.contracts import Money, money_text

__all__ = ["STATE_KEY", "MarketSensorState", "QuoteView", "TradeRange"]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "market_sensor"


class QuoteView(BaseModel):
    """Top of book for one pair, as of this tick.

    ``spread_pct`` is ``(ask - bid) / mid``, where ``mid`` is ``(ask + bid) / 2``. That
    is a **single full-spread term expressed as a ratio of price**, which is the shape
    invariant 5 needs: ``friction = maker + taker + spread + slippage``, every term a
    decimal ratio. The raw ``bid``, ``ask`` and ``spread`` are published beside it so a
    consumer that wants a different convention can compute one rather than reverse a
    division.

    **``spread_pct`` may be negative.** A crossed book is a real thing a feed produces
    during a fault and engine 4 blocks on exactly that; clamping it here would delete
    the evidence the gate exists to see.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    ts: str
    bid: Money
    ask: Money
    spread: Money
    spread_pct: Money
    age_s: float
    """How old this quote is, against ``context.now``. Engine 4's staleness input."""

    def state_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "ts": self.ts,
            "bid": money_text(self.bid),
            "ask": money_text(self.ask),
            "spread": money_text(self.spread),
            "spread_pct": money_text(self.spread_pct),
            "age_s": self.age_s,
        }


class TradeRange(BaseModel):
    """What one pair actually traded between the previous tick and this one. Spec 85.

    Top-of-book quotes sampled once a minute miss both of the things Phase 6 has to
    know: a resting post-only buy fills when the market **trades through** its price,
    and a stop or target is touched when the market **trades to** it — and both
    happen between ticks. This is the trade record of that interval, so engines 21
    and 22 and the fill simulator read one source rather than three readings of a
    quote.

    **It is trades, not quotes.** A book that quoted 100 and never traded there has
    no range here.

    ``trades`` is refused at zero, and that is the whole of the absent-is-not-zero
    rule made structural: a pair that did not trade has **no** ``TradeRange``, and a
    consumer asking for a silent pair gets a ``KeyError`` rather than a range of
    nothing with a copied price in it. A range of ``{"low": p, "high": p,
    "trades": 0}`` would tell a barrier check that the market touched ``p``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    low: Money
    high: Money
    trades: int
    since_ts: int
    """``context.previous_now`` in microseconds — the real stamp of the previous tick,
    not ``now`` minus a configured interval. The window is ``(since_ts, now]``,
    half-open at the bottom, so consecutive ticks tile it without overlapping and no
    trade is counted in two ranges. Because it is the real stamp, a loop that ran late
    produces a longer range rather than a hole: no trade falls between two ticks."""

    @field_validator("low", "high")
    @classmethod
    def _positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("a traded price is positive")
        return value

    @field_validator("trades")
    @classmethod
    def _at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError(
                "a range with no trades in it is not a range; a pair that did not "
                "trade since the previous tick is absent from trade_ranges"
            )
        return value

    @model_validator(mode="after")
    def _low_is_not_above_high(self) -> TradeRange:
        if self.low > self.high:
            raise ValueError(f"low {self.low} is above high {self.high}")
        return self

    def state_dict(self) -> dict[str, Any]:
        """Exactly the four keys spec 85 names, and no ``pair``.

        The map key already carries the pair. A second copy inside the value is one
        more thing that can disagree with it, and nothing reads it.
        """
        return {
            "low": money_text(self.low),
            "high": money_text(self.high),
            "trades": self.trades,
            "since_ts": self.since_ts,
        }


def spread_ratio(bid: Decimal, ask: Decimal) -> Decimal:
    """``(ask - bid) / mid``. Raises on a non-positive mid rather than returning zero.

    A zero or negative mid is not a spread of zero — it is an unusable quote, and
    invariant 3 says the absence of a "no" is never a "yes".
    """
    mid = (ask + bid) / Decimal(2)
    if mid <= 0:
        raise ValueError("a quote whose mid price is not positive is unusable")
    return (ask - bid) / mid


class MarketSensorState(BaseModel):
    """The whole of ``state["market_sensor"]``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bar_closed: bool
    """True only on the tick where a decision bar completed."""

    closed_bar_ts: int | None
    """The opening second of the bar that just closed, or None when none did."""

    interval_s: int
    candles: tuple[dict[str, Any], ...] = ()
    """Closed candles only, oldest first. **The in-progress bar is never here** —
    publishing a partial bar as a candle is look-ahead, and invariant 10 forbids it."""

    missing_bars: tuple[int, ...] = ()
    """Bar openings inside the covered range in which **no subscribed pair traded at all**.

    **Reported, never filled.** A missing candle means no trades occurred; it is a fact
    about the market, and the feature layer decides what to do about it.

    **Pooled across pairs, deliberately, and the name undersells it.** The timestamps are
    the union over every pair with published candles, so a bar is listed only when the
    whole subscription was silent — a feed-level fault, which is what engine 4
    `data_guard` blocks on. One pair going quiet for a bar is ordinary and is absent from
    this tuple; engine 5 counts each pair's holes from that pair's own candles, which are
    published here with the pair on every one.

    Measured 2026-09-13: with two pairs, one missing two bars the other traded in, this is
    empty; at 234 pairs it is empty on essentially every tick. Ruled by the lead the same
    day — a per-pair reading would make `data_guard` block on every thin pair's ordinary
    silence, which is most ticks.
    """

    quotes: dict[str, dict[str, Any]] = {}

    trade_ranges: dict[str, dict[str, Any]] = {}
    """Per pair, what actually **traded** between the previous tick and this one:
    ``{"low", "high", "trades", "since_ts"}``, prices as exact decimal strings and
    ``since_ts`` in microseconds. Spec 85, read by the fill simulator and by engines
    21 `position_manager` and 22 `exit`.

    **A pair with no trade since the previous tick is absent**, never
    ``{"trades": 0}`` with a copied price — no trade means no range, and a range of
    zero trades at a copied price would tell a barrier check the market touched it.
    :class:`TradeRange` refuses ``trades=0`` so the rule cannot be broken here.

    **Empty on the first tick of a process, and on the first tick after a restart.**
    The window is ``(context.previous_now, context.now]`` and ``previous_now`` is
    ``None`` on both, which is the truth rather than an inconvenience: nothing
    observed the span while the process was down. An interval with no start is not an
    interval, and the honest answer is nothing rather than an invented beginning.

    **Trades, not quotes.** A book that quoted a price and never traded there has no
    range here."""

    stream_available: bool = True
    trades_seen: int = 0

    def to_state(self) -> dict[str, Any]:
        payload: dict[str, Any] = self.model_dump(mode="json")
        return payload
