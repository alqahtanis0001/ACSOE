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

from pydantic import BaseModel, ConfigDict

from acsoe.clients.kraken.contracts import Money, money_text

__all__ = ["STATE_KEY", "MarketSensorState", "QuoteView"]

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
    """Bar openings inside the covered range in which nothing traded.

    **Reported, never filled.** A missing candle means no trades occurred; it is a fact
    about the market, and the feature layer decides what to do about it.
    """

    quotes: dict[str, dict[str, Any]] = {}
    stream_available: bool = True
    trades_seen: int = 0

    def to_state(self) -> dict[str, Any]:
        payload: dict[str, Any] = self.model_dump(mode="json")
        return payload
