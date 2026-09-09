"""What engine 4 `data_guard` publishes, and the fixtures that exercise it.

The reason codes are the important half of this module. A gate's ``reason`` is what an
operator reads and what Phase 4 stores in ``block_records.block_reason``, and every code
here has a matching entry in ``REASON_PROSE`` in ``console/format.py`` — **a code that
is not in that map renders as "No reason was recorded." silently, with no error
anywhere.** They were agreed with Agent C on 2026-09-09 and are fixed: change one here
without changing it there and the console goes quiet about a block that happened.

``BAD_DATA_SCENARIOS`` lives here rather than in `scripts/verify.py` deliberately, and
the reason is C's: the fields those fixtures set belong to engines 1 and 3, and a gate
that hardcoded another engine's field names in a test fixture would be asserting on a
shape it does not own. Building them from this module's own reader means the fixtures
and the engine cannot drift apart — if the shape of ``state["market_sensor"]`` changes,
both move together or both break.
"""

from __future__ import annotations

import copy
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "BAD_DATA_SCENARIOS",
    "REASON_MISSING_CANDLE",
    "REASON_NEGATIVE_SPREAD",
    "REASON_NO_MARKET_DATA",
    "REASON_STALE",
    "STATE_KEY",
    "DataGuardState",
    "Finding",
    "bad_data_state",
]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "data_guard"

# --------------------------------------------------------------------------- #
# Reason codes — mirrored in `console/format.py`'s REASON_PROSE
# --------------------------------------------------------------------------- #

REASON_STALE: Final = "market_data_stale"
"""The freshest quote is older than ``data_guard.max_data_age_s``."""

REASON_NO_MARKET_DATA: Final = "no_market_data"
"""Nothing has arrived at all. Distinct from stale on purpose: "the feed is behind" and
"there is no feed" are different things to an operator, and merging them would make the
second read as the first. Invariant 3 — a gate that cannot reach its data blocks."""

REASON_NEGATIVE_SPREAD: Final = "negative_spread"
"""A crossed book: the bid is above the ask."""

REASON_MISSING_CANDLE: Final = "missing_candle"
"""A decision bar inside the published window produced no candle.

**This is not a contradiction of `architecture-context.md`**, which says a missing
candle in the *historical archive* means no trades occurred and is not a data error, and
it is not a contradiction of spec 30, which forbids the loader from inventing one. Both
hold. The loader must never **invent** a bar; this gate must never **act** on a series
with a hole in it. Fail-closed points in opposite directions for labelling and for
trading, and someone "fixing" one of them by breaking the other is the hazard worth
naming here.
"""


class Finding(BaseModel):
    """One thing wrong with this tick's market data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason_code: str
    detail: str
    """Written for an operator, not for a log line. It names the pair or the bar."""

    pair: str | None = None


class DataGuardState(BaseModel):
    """The whole of ``state["data_guard"]``.

    Every finding is published, not only the one that became the ``reason``. A tick can
    be stale *and* carry a crossed book, and an operator looking at why trading stopped
    should see both rather than whichever the engine happened to check first.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    blocked: bool
    reason_code: str | None = None
    findings: tuple[dict[str, Any], ...] = ()
    max_data_age_s: float | None = None
    """The threshold applied, echoed so a block can be understood without the config."""

    oldest_quote_age_s: float | None = None
    pairs_seen: int = 0
    missing_bars: int = 0

    def to_state(self) -> dict[str, Any]:
        payload: dict[str, Any] = self.model_dump(mode="json")
        return payload


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

_PAIR: Final = "BTC/USD"
_BAR: Final = 900
_BASE_TS: Final = 1_700_000_000


def _quote(*, bid: str, ask: str, spread_pct: str, age_s: float) -> dict[str, Any]:
    """One entry of ``state["market_sensor"]["quotes"]``, in engine 3's own shape."""
    return {
        "pair": _PAIR,
        "ts": "2026-03-01T00:00:00.000000Z",
        "bid": bid,
        "ask": ask,
        "spread": str(float(ask) - float(bid)),
        "spread_pct": spread_pct,
        "age_s": age_s,
    }


def _candle(index: int) -> dict[str, Any]:
    price = 100 + index
    return {
        "pair": _PAIR,
        "ts": _BASE_TS + index * _BAR,
        "open": f"{price}.0",
        "high": f"{price}.5",
        "low": f"{price}.0",
        "close": f"{price}.2",
        "volume": "1.5",
        "trades": 7,
    }


def _market_sensor(
    *,
    quotes: dict[str, dict[str, Any]],
    missing_bars: tuple[int, ...] = (),
    stream_available: bool = True,
) -> dict[str, Any]:
    return {
        "bar_closed": True,
        "closed_bar_ts": _BASE_TS + 3 * _BAR,
        "interval_s": _BAR,
        "candles": tuple(_candle(index) for index in range(4)),
        "missing_bars": missing_bars,
        "quotes": quotes,
        "stream_available": stream_available,
        "trades_seen": 120,
    }


def _state(market_sensor: dict[str, Any]) -> dict[str, Any]:
    """A `state` as the orchestrator hands it to engine 4: engines 1 to 3 have run."""
    return {
        "system": {"mode": "running", "close_intent": False},
        "cycle_id": 1,
        "guard_blockers": [],
        "market_sensor": market_sensor,
    }


_HEALTHY_QUOTE: Final = _quote(bid="50000.0", ask="50000.2", spread_pct="0.000004", age_s=1.0)

#: One `state` per condition the phase criteria name, plus the pass case.
#:
#: The clean case is not optional: three block cases without it would be satisfied by a
#: gate that refuses everything, and a pass case without them by a gate that refuses
#: nothing. Each bad case differs from `clean` in **exactly one** respect, so a block
#: cannot be attributed to the wrong fault.
BAD_DATA_SCENARIOS: Final[dict[str, dict[str, Any]]] = {
    "clean": _state(_market_sensor(quotes={_PAIR: _HEALTHY_QUOTE})),
    "stale": _state(
        _market_sensor(
            quotes={
                _PAIR: _quote(
                    bid="50000.0", ask="50000.2", spread_pct="0.000004", age_s=86_400.0
                )
            }
        )
    ),
    "negative_spread": _state(
        _market_sensor(
            quotes={
                _PAIR: _quote(bid="50000.5", ask="50000.0", spread_pct="-0.00001", age_s=1.0)
            }
        )
    ),
    "missing_candle": _state(
        _market_sensor(
            quotes={_PAIR: _HEALTHY_QUOTE}, missing_bars=(_BASE_TS + 2 * _BAR,)
        )
    ),
    "no_market_data": _state(_market_sensor(quotes={}, stream_available=False)),
}


def bad_data_state(name: str) -> dict[str, Any]:
    """A fresh **deep** copy of one scenario, safe to modify.

    ``BAD_DATA_SCENARIOS`` is module-level and its values are nested dicts, so
    ``dict(BAD_DATA_SCENARIOS[name])`` copies only the outer layer — a caller that then
    writes ``state["market_sensor"]["missing_bars"]`` mutates the shared fixture for
    everything that runs afterwards, and the failure surfaces somewhere unrelated. That
    happened once in this engine's own tests, which is why this exists.

    Use this whenever a scenario is going to be modified. Reading one is safe either
    way, which is why `scripts/verify.py` is correct as written.
    """
    if name not in BAD_DATA_SCENARIOS:
        raise KeyError(f"unknown scenario {name!r}; expected one of {sorted(BAD_DATA_SCENARIOS)}")
    return copy.deepcopy(BAD_DATA_SCENARIOS[name])
