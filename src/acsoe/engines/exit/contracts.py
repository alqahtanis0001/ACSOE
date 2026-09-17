"""What engine 22 `exit` reads out of `state` and writes back into it.

Every path is a `Final` constant, for the reason `engines/position_manager/contracts.py`
gives: engine 11 read `state["exchange"]["pairs"]` one level shallower than engine 1
publishes it for two phases, and every live tick blocked. A constant makes that repair a
single greppable edit.

## The published payload is engine 19's, field for field

`orders`, `positions` and `closed_trades` are the names `engines/memory/contracts.py`
already reads — `ORDERS_FIELD`, `POSITIONS_FIELD`, `CLOSED_TRADES_FIELD`. They are
restated here rather than imported because contract rule 3 forbids one engine importing
another, and a test asserts the two spellings agree so the restatement cannot drift.

Every row carries a **store-contract row payload minus `run_id`, `cycle_id` and
`updated_at`**. Engine 19's `_stamped` sets those three itself: a row carrying somebody
else's `run_id` cannot be joined to the block record for the tick, and `(run_id,
cycle_id)` is the join.

## `positions_closed` is half of the kill switch's completion signal

The orchestrator requires the boolean `True` exactly — spec 81 fixed a truthiness
fail-open on this pair of flags — and absent or false always means "not finished", so a
liquidation that could not complete is retried on the next tick. It is published on
every tick, including ordinary ones, because a field that appears only during a
liquidation is a field whose absence has two meanings.

## The exit `userref`, and why it is not engine 18's function

Invariant 8 applies to every order, not only entries, so an exit needs an identifier
chosen **before** the order exists. Engine 18 has one and this engine may not import it
(contract rule 3), so :func:`exit_userref_for` is the same construction over a different
input: a `blake2b` digest, never `hash()`, which Python salts per process and which
would therefore compute a different identifier after a restart — invariant 8's exact
failure, arriving through a builtin that looks pure.

The input is the `position_id`, which is what makes one exit one exit: a position is
closed once. It is **not** the barrier, because a position triggered on `stop` this tick
and re-triggered on `timeout` next tick is one exit, and hashing the barrier would place
a second market sell for a position already being sold.
"""

from __future__ import annotations

import hashlib
from decimal import ROUND_DOWN, Decimal
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.kraken.contracts import USERREF_MAX

__all__ = [
    "CLOSED_TRADES_FIELD",
    "CLOSE_INTENT_FIELD",
    "DATA_GUARD_NAME",
    "EXCHANGE_KEY",
    "EXCHANGE_PAIR_RULES_KEY",
    "FALLBACK_ASSET_PAIRS_RETAINED",
    "LOT_DECIMALS_FIELD",
    "NET_PROCEEDS_FIELD",
    "ORDERS_FIELD",
    "PAIR_RULES_PAIRS_KEY",
    "POSITIONS_CLOSED_FIELD",
    "POSITIONS_FIELD",
    "POSITION_ID_FIELD",
    "POSITION_MANAGER_KEY",
    "REASON_DATA_GUARD_BLOCKED",
    "REASON_EXITS_PLACED",
    "REASON_EXIT_ALREADY_PLACED",
    "REASON_EXIT_INCOMPLETE",
    "REASON_NOTHING_TO_EXIT",
    "STATE_KEY",
    "SYSTEM_KEY",
    "TRADING_BLOCKED_BY_KEY",
    "TRIGGERED_BARRIER_FIELD",
    "TRIGGERED_FIELD",
    "ExitState",
    "exit_userref_for",
    "round_down_to_lot",
    "trade_id_for",
]

# --------------------------------------------------------------------------- #
# What it reads
# --------------------------------------------------------------------------- #

#: The orchestrator's own region of `state`. Engine 22 reads `close_intent` and never
#: writes it: `core/` owns that key and clears it only when engines 21 and 22 both
#: report finished.
SYSTEM_KEY: Final = "system"
CLOSE_INTENT_FIELD: Final = "close_intent"

#: Set by the orchestrator to the name of the **first** guard that blocked.
TRADING_BLOCKED_BY_KEY: Final = "trading_blocked_by"

#: The one blocker that holds exits, and only when `close_intent` is not set. A barrier
#: computed from data engine 4 has just rejected is a fabricated trigger acting on real
#: money. A block by any other engine does not hold: a `cost` or `safety` block is a
#: statement about whether to *open* something, and a position already open still has to
#: be got out of.
DATA_GUARD_NAME: Final = "data_guard"

#: Engine 21 (B), immediately before this engine in the manage chain. `triggered` is the
#: only thing engine 22 acts on during an ordinary tick — engine 22 decides no barriers
#: of its own, so the two cannot disagree about whether one was touched.
POSITION_MANAGER_KEY: Final = "position_manager"
TRIGGERED_FIELD: Final = "triggered"
POSITION_ID_FIELD: Final = "position_id"
TRIGGERED_BARRIER_FIELD: Final = "barrier"

#: Engine 1 `exchange` (A). `lot_decimals` is the grid an exit quantity is rounded
#: **down** onto. There is no other publisher of it and no default for it anywhere:
#: invariant 2 gives pair rules no fallback in any mode except the one below.
EXCHANGE_KEY: Final = "exchange"
EXCHANGE_PAIR_RULES_KEY: Final = "pair_rules"
PAIR_RULES_PAIRS_KEY: Final = "pairs"
LOT_DECIMALS_FIELD: Final = "lot_decimals"

# --------------------------------------------------------------------------- #
# What it writes
# --------------------------------------------------------------------------- #

STATE_KEY: Final = "exit"

#: Engine 19's names, restated rather than imported (contract rule 3) and pinned by a
#: test against `engines/memory/contracts.py` so the restatement cannot drift.
ORDERS_FIELD: Final = "orders"
POSITIONS_FIELD: Final = "positions"
CLOSED_TRADES_FIELD: Final = "closed_trades"

#: Half of the kill switch's completion signal. See the module docstring.
POSITIONS_CLOSED_FIELD: Final = "positions_closed"

#: On every `closed_trades` row: `qty * exit_price - exit_fee`, as an exact decimal
#: string, computed from the `qty`, `exit_price` and `exit_fee` the same row carries.
#: The cash the sale put into the account. Engine 19 adds it to engine 1's start-of-tick
#: balance to build the exit tick's equity row (spec 114).
#:
#: **A fact about a sale this engine executed, and nothing else** (operator ruling
#: 2026-09-17). It reads neither engine 21's valuation nor engine 1's balance. The
#: withdrawn first design had this engine subtract engine 21's marks, which tied it to a
#: valuation method it does not own. That result would have changed silently whenever
#: engine 21's method did.
#:
#: It is not a `trades` column. Engine 19 reads it off the payload, and the store keeps
#: `qty`, `exit_price` and `exit_fee`, from which it can always be recomputed.
NET_PROCEEDS_FIELD: Final = "net_proceeds"

# --------------------------------------------------------------------------- #
# The one fallback, and the one this engine deliberately does not have
# --------------------------------------------------------------------------- #

#: Recorded on every trade whose exit quantity was rounded with `AssetPairs` metadata
#: retained past its TTL. Invariant 14 authorises exactly this and nothing wider, and
#: invariant 2 requires the trade to say so, so a fill is never mistaken for one priced
#: on good data.
#:
#: **There is deliberately no `balance_last_known_good` beside it**, although spec 93
#: names one. Engine 22 never reads a balance: an exit's quantity is the position's,
#: from the `positions` row, and capping it at the account's base holding would be
#: wrong in paper mode by construction — the paper ledger is **quote-side only** by the
#: spec 88 ruling, so the base balance of every paper position is zero and every paper
#: exit would round to nothing. A fallback constant nothing emits is worse than an
#: absent one: it reads as a behaviour the system has. Escalated to the lead rather than
#: decided here.
FALLBACK_ASSET_PAIRS_RETAINED: Final = "asset_pairs_last_known_good"

# --------------------------------------------------------------------------- #
# Reason codes
# --------------------------------------------------------------------------- #

#: At least one exit was placed this tick. Engine 22 is not a gate, so this is not an
#: approval; `reason_code` is how every engine says what it did.
REASON_EXITS_PLACED: Final = "exits_placed"

#: Nothing reached a barrier and no liquidation is running, so nothing was placed. The
#: ordinary tick, and distinct from the hold below: here the engine looked and there was
#: nothing to do.
REASON_NOTHING_TO_EXIT: Final = "nothing_to_exit"

#: `data_guard` blocked and this is not a liquidation, so **no exit of any kind** was
#: placed — not a target, not a stop, not a timeout. Spelled exactly as engine 21's hold
#: reason, because it is the same fact about the same tick and two vocabularies for one
#: fact is how a `trades` table ends up with both "stop" and "stopped" in it.
REASON_DATA_GUARD_BLOCKED: Final = "data_guard_blocked"

#: Every exit this tick asked for was already at the exchange under its own `userref`,
#: so nothing new was placed. Invariant 8, and the ordinary case on a re-run of one tick
#: rather than an error.
REASON_EXIT_ALREADY_PLACED: Final = "exit_already_placed"

#: At least one position could not be exited — a fill the pair rules could not describe,
#: a fee tier nobody could fetch, an order the exchange refused. `positions_closed` is
#: `False` beside it and the liquidation is retried next tick. Never a silent partial.
REASON_EXIT_INCOMPLETE: Final = "exit_incomplete"


def exit_userref_for(position_id: str) -> int:
    """The exit order's identifier, derived from the position and nothing else.

    Deterministic across processes — see the module docstring on why not `hash()` — and
    in `[1, USERREF_MAX - 1]` for the reasons `userref_for` gives on the entry side:
    zero is what a missing integer field decays to, and a negative `userref` reads as a
    typo in every operator query this system will ever be asked.

    **A collision with an entry's `userref` is a defect, not a retry.** Both live in one
    `orders` table keyed by `userref`, and a 31-bit digest over a small daily order set
    collides with vanishing probability — so the caller compares what it finds and
    raises rather than assuming, exactly as engine 18 does.
    """
    digest = hashlib.blake2b(f"{position_id}|exit".encode(), digest_size=8).digest()
    return 1 + int.from_bytes(digest, "big") % (USERREF_MAX - 1)


def round_down_to_lot(quantity: Decimal, lot_decimals: int) -> Decimal:
    """The largest quantity on the pair's lot grid that is not above `quantity`.

    Restated rather than imported from `engines/risk/contracts.py`, which has the same
    four lines: contract rule 3 forbids one engine importing another, and the two are
    pinned against each other by a test so the restatement cannot drift.

    **Always down, and invariant 14 repeats it for the liquidation specifically.**
    Rounding up leaves dust behind and produces an order Kraken rejects, and a rejected
    order during an emergency is worse than dust: the position stays open through the
    outage the liquidation was fired to end.
    """
    if lot_decimals < 0:
        raise ValueError(f"lot_decimals must not be negative, got {lot_decimals}")
    return quantity.quantize(Decimal(1).scaleb(-lot_decimals), rounding=ROUND_DOWN)


def trade_id_for(position_id: str) -> str:
    """The closed round trip's identifier, named from the position it closes.

    Deterministic, so re-running one tick upserts the same `trades` row rather than
    recording a second round trip for one position. `position_id` is already unique per
    position and is already derived from the entry's `userref`, so this needs no
    uniqueness argument of its own.
    """
    return f"trade-{position_id}"


class ExitState(BaseModel):
    """What engine 22 publishes into `state["exit"]`.

    A model rather than a dict so the field set is one decision in one place. Unlike
    engine 21's payload nothing here is conditionally omitted: every field is a list or
    a boolean, and an empty list and an absent list would mean the same thing to engine
    19 — which is exactly why engine 21 omits its two *scalars* and this engine omits
    nothing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    orders: tuple[dict[str, Any], ...] = ()
    positions: tuple[dict[str, Any], ...] = ()
    closed_trades: tuple[dict[str, Any], ...] = ()
    positions_closed: bool = False
    reason_code: str | None = None

    def to_state(self) -> dict[str, Any]:
        return {
            ORDERS_FIELD: [dict(row) for row in self.orders],
            POSITIONS_FIELD: [dict(row) for row in self.positions],
            CLOSED_TRADES_FIELD: [dict(row) for row in self.closed_trades],
            POSITIONS_CLOSED_FIELD: self.positions_closed,
            "reason_code": self.reason_code,
        }
