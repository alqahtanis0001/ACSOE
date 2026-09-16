"""What engine 21 `position_manager` reads out of `state` and writes back into it.

Every path is a `Final` constant, so re-pointing one is a single greppable edit. That is
not a style preference: engine 11 read `state["exchange"]["pairs"]` for two phases, one
level shallower than engine 1 publishes it, and every live tick blocked. The constants
are what made that repair small when it was finally found.

## The published payload is engine 19's, field for field

`positions`, `orders`, `positions_value`, `unrealised_pnl` and `hold_reason` are the
names `engines/memory/contracts.py` already reads — `POSITIONS_FIELD`, `ORDERS_FIELD`,
`POSITIONS_VALUE_FIELD`, `UNREALISED_PNL_FIELD`, `HOLD_REASON_FIELD`. They are restated
here rather than imported because contract rule 3 forbids one engine importing another,
and a test asserts the two spellings agree so the restatement cannot drift.

`positions` and `orders` carry **store-contract row payloads minus `run_id`, `cycle_id`
and `updated_at`**. Engine 19's `_stamped` sets those three itself and says why: a row
carrying somebody else's `run_id` cannot be joined to the block record for the tick, and
`(run_id, cycle_id)` is the join. So this engine must not set them, and does not.

## Absent is not zero, in two places, and they are different absences

`positions_value` and `unrealised_pnl` are **omitted entirely** on a tick where a mark
could not be taken. Engine 19 then skips the equity row rather than writing a false one,
and its own docstring is explicit that a zero equity row is a 100% drawdown that trips
the circuit breaker.

`hold_reason` is **null rather than omitted** on a tick that did not hold. Null is the
answer here — "I considered holding and did not" — where an omission would be
indistinguishable from an engine that had not run. That is the same distinction engine 7
draws between `pair` (omitted when there is none) and `rank_feature` (null).
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.store.contracts import Money

__all__ = [
    "BARRIER_FIELD",
    "CLOSE_INTENT_FIELD",
    "DATA_GUARD_NAME",
    "ENTRY_ORDERS_CANCELLED_FIELD",
    "EXCHANGE_KEY",
    "EXCHANGE_PAIR_RULES_KEY",
    "EXECUTION_KEY",
    "EXECUTION_ORDERS_FIELD",
    "HOLD_DATA_GUARD_BLOCKED",
    "HOLD_REASON_FIELD",
    "MARKET_SENSOR_KEY",
    "ORDERS_FIELD",
    "PAIR_RULES_PAIRS_KEY",
    "POSITIONS_FIELD",
    "POSITIONS_VALUE_FIELD",
    "POSITION_ID_FIELD",
    "QUOTES_FIELD",
    "QUOTE_BID_FIELD",
    "REASON_POSITION_UNRECORDABLE",
    "STATE_KEY",
    "SYSTEM_KEY",
    "TRADE_RANGES_FIELD",
    "TRADE_RANGE_HIGH_FIELD",
    "TRADE_RANGE_LOW_FIELD",
    "TRADING_BLOCKED_BY_KEY",
    "TRIGGERED_FIELD",
    "UNREALISED_PNL_FIELD",
    "Barrier",
    "ManagedPositions",
    "position_id_for",
]

# --------------------------------------------------------------------------- #
# What it reads
# --------------------------------------------------------------------------- #

#: The orchestrator's own region of `state`. Engine 21 reads `close_intent` from it and
#: never writes it — `core/` owns that key and clears it only when both manage-chain
#: engines report finished.
SYSTEM_KEY: Final = "system"
CLOSE_INTENT_FIELD: Final = "close_intent"

#: Set by the orchestrator to the name of the **first** guard that blocked. Engine 21
#: holds on exactly one value of it and on nothing else.
TRADING_BLOCKED_BY_KEY: Final = "trading_blocked_by"

#: The one blocker that holds exits. Invariant 14: the manage chain holds while the guard
#: is rejecting data, because a barrier computed from rejected data is a fabricated
#: trigger acting on real money. **A block by any other engine does not hold** — a `cost`
#: or `safety` block is a statement about whether to *open* something, and a position
#: already open still has to be managed.
DATA_GUARD_NAME: Final = "data_guard"

#: Engine 3 `market_sensor` (A). Marks come from `quotes` and barriers from
#: `trade_ranges`, and the two are different readings on purpose — see the engine.
MARKET_SENSOR_KEY: Final = "market_sensor"
QUOTES_FIELD: Final = "quotes"
TRADE_RANGES_FIELD: Final = "trade_ranges"

#: A position is marked at the **bid**: what a sale would actually receive. The ask would
#: value every holding at a price nobody is offering to pay.
QUOTE_BID_FIELD: Final = "bid"

#: Spec 85's per-tick traded range. `low` and `high` are what the market *traded*, not
#: what it quoted, which is the whole reason engine 21 can decide a barrier at all: a
#: book that quoted 100 and never traded there did not touch 100.
TRADE_RANGE_LOW_FIELD: Final = "low"
TRADE_RANGE_HIGH_FIELD: Final = "high"

#: Engine 18 `execution` (B), when it ran. **Read only when present**: on fourteen ticks
#: in fifteen the opportunity chain did not run at all, and on the fifteenth it may have
#: blocked at any gate. An entry placed this tick is not in the store yet — engine 19
#: writes at the end of the manage chain — so this is the only way to see it.
EXECUTION_KEY: Final = "execution"
EXECUTION_ORDERS_FIELD: Final = "orders"

#: Engine 1 `exchange` (A). `base` and `quote` for a position row come from here; there
#: is no other publisher of them and a pair name may not be split on a slash.
EXCHANGE_KEY: Final = "exchange"
EXCHANGE_PAIR_RULES_KEY: Final = "pair_rules"
PAIR_RULES_PAIRS_KEY: Final = "pairs"

# --------------------------------------------------------------------------- #
# What it writes
# --------------------------------------------------------------------------- #

STATE_KEY: Final = "position_manager"

#: Engine 19's names, restated rather than imported (contract rule 3) and pinned by a
#: test against `engines/memory/contracts.py` so the restatement cannot drift.
POSITIONS_FIELD: Final = "positions"
ORDERS_FIELD: Final = "orders"
POSITIONS_VALUE_FIELD: Final = "positions_value"
UNREALISED_PNL_FIELD: Final = "unrealised_pnl"
HOLD_REASON_FIELD: Final = "hold_reason"

#: What engine 22 acts on: one entry per position that reached a barrier.
TRIGGERED_FIELD: Final = "triggered"
POSITION_ID_FIELD: Final = "position_id"
BARRIER_FIELD: Final = "barrier"

#: Half of the kill switch's completion signal. The orchestrator requires the boolean
#: `True` exactly — spec 81 fixed a truthiness fail-open here — and absent or false
#: always means "not finished", so a failed cancel is retried on the next tick.
ENTRY_ORDERS_CANCELLED_FIELD: Final = "entry_orders_cancelled"

#: A fill this engine could not turn into a position row, because the pair rules it needs
#: for `base` and `quote` were not published this tick. See the engine: nothing is
#: published for that order, so it stays resting in the store and the fill is picked up
#: again next tick. Flagged to C for `REASON_PROSE` (spec 99).
REASON_POSITION_UNRECORDABLE: Final = "position_unrecordable"

#: The one hold reason engine 21 emits today. Named, not spelled inline, because the
#: console renders it and engine 19 records it.
HOLD_DATA_GUARD_BLOCKED: Final = "data_guard_blocked"


class Barrier:
    """Which barrier a position reached.

    The three spellings are `TradeOutcome`'s — `target`, `stop`, `timeout` — because
    engine 22 writes one of them into `trades.outcome` and two vocabularies for one fact
    is how a `trades` table ends up with both "stop" and "stopped" in it. They are not
    imported as that enum because `TradeOutcome` also carries `liquidation`, which is
    never a *barrier*: a liquidation is a decision about the account, not something the
    market did to a price.
    """

    TARGET: Final = "target"
    STOP: Final = "stop"
    TIMEOUT: Final = "timeout"


def position_id_for(userref: int) -> str:
    """The position a filled entry becomes, named from the order that opened it.

    Deterministic, so re-running one tick upserts the same row rather than opening a
    second position on the same fill. `userref` is already the system's idempotency token
    under invariant 8 and is already unique per `(pair, bar)`, so deriving from it needs
    no new uniqueness argument of its own.
    """
    return f"pos-{userref}"


class ManagedPositions(BaseModel):
    """What engine 21 publishes into `state["position_manager"]`.

    A model rather than a dict so the absent-is-not-zero rules are structural. `to_state`
    is the only place the payload is assembled, so there is one answer to "is this field
    omitted or null" per field rather than one per call site.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    positions: tuple[dict[str, Any], ...] = ()
    orders: tuple[dict[str, Any], ...] = ()
    positions_value: Money | None = None
    unrealised_pnl: Money | None = None
    triggered: tuple[dict[str, str], ...] = ()
    hold_reason: str | None = None
    entry_orders_cancelled: bool = False
    reason_code: str | None = None

    def to_state(self) -> dict[str, Any]:
        """The JSON-serialisable payload, money as exact decimal strings.

        `positions_value` and `unrealised_pnl` are **omitted** when they are `None`, not
        emitted as null: engine 19 skips the equity row on an absent field and would
        write a zero-equity row on a null one, which is a 100% drawdown and trips the
        breaker. `hold_reason` is emitted as null, because there the null is the answer.
        """
        payload: dict[str, Any] = {
            POSITIONS_FIELD: [dict(row) for row in self.positions],
            ORDERS_FIELD: [dict(row) for row in self.orders],
            TRIGGERED_FIELD: [dict(entry) for entry in self.triggered],
            HOLD_REASON_FIELD: self.hold_reason,
            ENTRY_ORDERS_CANCELLED_FIELD: self.entry_orders_cancelled,
            "reason_code": self.reason_code,
        }
        if self.positions_value is not None:
            payload[POSITIONS_VALUE_FIELD] = format(self.positions_value, "f")
        if self.unrealised_pnl is not None:
            payload[UNREALISED_PNL_FIELD] = format(self.unrealised_pnl, "f")
        return payload
