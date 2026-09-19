"""What engine 19 `memory` reads out of ``state`` and what it publishes back into it.

Engine 19 is the **single writer of relational rows** — `architecture-context.md` says
so, and it is why the manage chain's "always runs" guarantee is sufficient for
invariant 12. Every other engine describes what happened; this one records it.

**Every key name this engine reads lives here and nowhere else.** Engine 19 touches more
of ``state`` than any other engine — the guard chain's blockers, engine 1's balances,
engines 18, 21 and 22's positions, orders and closes, and whichever gate refused the
candidate — and contract rule 3 forbids it importing another engine to find out what
those keys are called. So they are named here, once, with the engine that owns each one
written beside it. A key renamed upstream without a matching change here does not raise:
engine 19 simply records nothing, silently, which is the failure mode this whole engine
is arranged around.

**Money.** ``MemoryState`` reports money as :data:`Money`, the annotated ``Decimal``
that refuses a float, and :meth:`MemoryState.to_state_data` converts it to an exact
decimal string on the way into ``state``. Contract rule 8: ``state`` carries no
``Decimal``, and an engine that hits that refusal and reflexively casts to ``float``
publishes an equity figure that has already lost precision.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.store.contracts import Money

__all__ = [
    "APPROVAL_TRADE_FIELDS",
    "BALANCES_FIELD",
    "BLOCK_REASON_KEY",
    "BLOCK_STATUS_KEY",
    "CANDIDATE_PAIR_PATH",
    "CLOSED_TRADES_FIELD",
    "COST_KEY",
    "CYCLE_ID_KEY",
    "ECONOMICS_FIELDS",
    "EXCHANGE_KEY",
    "EXECUTION_KEY",
    "EXIT_KEY",
    "GUARD_BLOCKERS_KEY",
    "HOLD_REASON_FIELD",
    "MODEL_RUN_ID_FIELD",
    "MODEL_RUN_KEYS",
    "NET_PROCEEDS_FIELD",
    "ORDERS_FIELD",
    "PAIR_FIELD",
    "PLACED_FIELD",
    "POSITIONS_FIELD",
    "POSITIONS_VALUE_FIELD",
    "POSITION_ID_FIELD",
    "POSITION_MANAGER_KEY",
    "POSITION_STATUS_FIELD",
    "POSITION_VALUE_FIELD",
    "REASON_CODE_FIELD",
    "REASON_ENGINE_ERRORED",
    "SCOUT_KEY",
    "STATE_KEY",
    "TRADING_BLOCKED_BY_KEY",
    "UNREALISED_PNL_FIELD",
    "USERREF_FIELD",
    "WRITTEN_TABLES",
    "MemoryState",
    "MissingInputError",
]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "memory"

# --------------------------------------------------------------------------- #
# What engine 19 reads. Each line names the engine that owns the key.
# --------------------------------------------------------------------------- #

#: Written by the orchestrator at the top of every tick — an empty list on an unblocked
#: tick, never absent. Each entry is ``{"engine", "reason", "status"}`` in chain order.
GUARD_BLOCKERS_KEY: Final = "guard_blockers"

#: The tick's cycle number. A tick is ``(run_id, cycle_id)``; ``run_id`` is on the
#: context and ``cycle_id`` is in ``state``, because ``EngineContext`` has no such field.
CYCLE_ID_KEY: Final = "cycle_id"

#: Set by the orchestrator to the **first** blocker of either chain, and the reason it
#: gave. A blocker that is not one of ``guard_blockers`` came from the opportunity
#: chain, which is what makes the tick a *rejection* rather than only a block — unless
#: its status is ``ERROR``, in which case nothing was refused (see ``BLOCK_STATUS_KEY``).
TRADING_BLOCKED_BY_KEY: Final = "trading_blocked_by"
BLOCK_REASON_KEY: Final = "block_reason"

#: Set by the orchestrator beside the two keys above: ``BLOCK`` or ``ERROR``, absent on an
#: unblocked tick. It is the **only** thing that tells an opportunity-chain engine that
#: raised from one that refused. Rule 7 empties a raising engine's payload, and an empty
#: payload is also exactly what a gate that blocked without its ``reason_code`` looks like
#: — two facts with different right answers, so engine 19 reads this key and never infers
#: an error from the emptiness. Invariant 12 and contract rule 7, operator ruling
#: 2026-09-16.
BLOCK_STATUS_KEY: Final = "block_status"

#: The ``block_records.block_reason`` of an opportunity-chain engine that returned
#: ``ERROR``. **Engine 19's code, not the engine's**: a ``reason_code`` is a decision an
#: engine made and an error is the absence of one, so the errored engine is never asked
#: for a code and never credited with one. No ``rejections`` row carries it, because no
#: candidate was refused. `console/format.py`'s ``REASON_PROSE`` maps it, in the change
#: that introduced it (spec 104).
REASON_ENGINE_ERRORED: Final = "engine_errored"

#: Engine 7 `scout` (B). Which pair the tick is considering. ``None`` on a tick where
#: the opportunity chain never produced a candidate, which is most of them.
SCOUT_KEY: Final = "scout"
CANDIDATE_PAIR_PATH: Final = (SCOUT_KEY, "pair")

#: Every gate publishes one. `console/format.py`'s ``REASON_PROSE`` maps it to operator
#: prose, and **a code absent from that map renders "No reason was recorded." silently**.
REASON_CODE_FIELD: Final = "reason_code"

#: Engine 1 `exchange` (A). The balances fetched this tick, keyed by currency, each an
#: exact decimal string. Absent when the fetch failed — invariant 2 — and that absence
#: is why a tick can legitimately produce no equity row.
EXCHANGE_KEY: Final = "exchange"
BALANCES_FIELD: Final = "balances"

#: Engine 21 `position_manager` (B), Phase 6. Open positions, resting orders, the value
#: they carry, and why the manage chain held this tick.
POSITION_MANAGER_KEY: Final = "position_manager"
POSITIONS_FIELD: Final = "positions"
ORDERS_FIELD: Final = "orders"
POSITIONS_VALUE_FIELD: Final = "positions_value"
UNREALISED_PNL_FIELD: Final = "unrealised_pnl"
HOLD_REASON_FIELD: Final = "hold_reason"

#: On a position row, and on a closed position row engine 22 publishes. Read here to
#: match engine 21's marks against the positions engine 22 closed on the same tick.
POSITION_ID_FIELD: Final = "position_id"
POSITION_STATUS_FIELD: Final = "status"

#: Engine 18 `execution` (B), Phase 6, spec 98. The entry order it placed — or the
#: rejection row for one the exchange refused — on the **opportunity** chain, the same
#: tick. Engine 19 is the single writer of relational rows, so an order engine 18
#: published and engine 19 does not read is an order that never reaches the store.
#:
#: Absent on the fourteen ticks in fifteen with no decision bar, and absent on a bar tick
#: where the chain stopped at an earlier gate. **Absent means nothing to record**, never a
#: zero — the distinction `sources_present` exists to keep visible.
EXECUTION_KEY: Final = "execution"

#: Engine 22 `exit` (B), Phase 6. Round trips that closed on this tick, the exit orders it
#: placed, and the positions it closed.
#:
#: `ORDERS_FIELD` and `POSITIONS_FIELD` are read from **three** publishers between them —
#: 18, 21 and 22 for orders, 21 and 22 for positions — and the field names are the same on
#: each because the row shapes are the store's, not the publisher's. The write **order**
#: is what separates them, and it is load-bearing: see `WRITTEN_TABLES` below.
EXIT_KEY: Final = "exit"
CLOSED_TRADES_FIELD: Final = "closed_trades"

# --------------------------------------------------------------------------- #
# The two payload facts that are not columns — spec 113, read by spec 114
# --------------------------------------------------------------------------- #
#
# Both arrive on rows engine 19 also stores, and **neither is a column**. `_Row` in
# `clients/store/contracts.py` is `extra="forbid"`, so engine 19 takes each off its own
# copy of the row before validating the stored row. Getting that wrong is not a small
# mistake: the validation error is converted by contract rule 7 into an `ERROR` result,
# and the whole tick — positions, orders, trades, block records, equity — is recorded
# nowhere. That is what the tree did for 26 tests between specs 113 and 114.
#
# They are payload facts rather than columns because the store can always recompute
# them: `net_proceeds` from the trade's own `qty`, `exit_price` and `exit_fee`, and
# `value` from the position's `qty` and `last_price`. A column would be a second copy of
# a number already stored, free to disagree with it.

#: Engine 21 `position_manager` (B), spec 113. Per marked position row: `qty *
#: last_price` as an exact decimal string, **present exactly when `last_price` is**. On a
#: tick where engine 22 closed positions, engine 19 sums it over the rows that remain
#: open rather than reading `POSITIONS_VALUE_FIELD`, which was computed before the sale.
#:
#: **A remaining position without one means no equity row** (operator ruling 2026-09-17),
#: exactly as an absent `POSITIONS_VALUE_FIELD` does on an ordinary tick and for the same
#: reason: a partial sum is the account minus one position, which is a drawdown that did
#: not happen. A *closed* position without one is dropped anyway and blocks nothing.
POSITION_VALUE_FIELD: Final = "value"

#: Engine 22 `exit` (B), spec 113. Per closed trade row: `qty * exit_price - exit_fee` as
#: an exact decimal string — the cash that sale put into the account, and a fact about a
#: sale engine 22 executed rather than a figure about anyone else's position. Engine 19
#: adds it to engine 1's start-of-tick balance to build the exit tick's cash.
NET_PROCEEDS_FIELD: Final = "net_proceeds"

#: The economics a rejection carries, as ``(rejections column, publisher's field)``.
#: Harvested from whichever engine blocked, **where it published them** — engine 10
#: `cost` publishes all four, engine 11 `risk` publishes none, and a rejection from
#: `risk` with four nulls is the honest record rather than a gap.
ECONOMICS_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("expected_move_pct", "expected_move_pct"),
    ("friction_pct", "friction_pct"),
    ("net_edge_pct", "net_edge_pct"),
    ("hurdle_pct", "hurdle_pct"),
)

# --------------------------------------------------------------------------- #
# Why an entry was approved — spec 133, with B's migration 0006 (spec 132)
# --------------------------------------------------------------------------- #

#: Engine 18 `execution` (B). `placed` is **this tick's** placement and nothing else, so it
#: is the one signal that the economics in `state` right now are the ones that approved an
#: entry. An order found already recorded publishes `placed: false` and gets no approval.
PLACED_FIELD: Final = "placed"
USERREF_FIELD: Final = "userref"
PAIR_FIELD: Final = "pair"

#: Engine 10 `cost` (B). The four economics come from its payload, through
#: `ECONOMICS_FIELDS`: they are the figures it compared against the hurdle.
COST_KEY: Final = "cost"

#: Engines 8 `prediction`, 13 `anomaly` and 15 `skeptic` (C) each publish the model run
#: they scored with as `model_run_id`, as ``(approvals column, state key)``.
MODEL_RUN_ID_FIELD: Final = "model_run_id"
MODEL_RUN_KEYS: Final[tuple[tuple[str, str], ...]] = (
    ("prediction_run_id", "prediction"),
    ("anomaly_run_id", "anomaly"),
    ("skeptic_run_id", "skeptic"),
)

#: The columns an `approvals` row hands to the `trades` row of the same entry, by name.
APPROVAL_TRADE_FIELDS: Final[tuple[str, ...]] = (
    *(column for column, _ in ECONOMICS_FIELDS),
    *(column for column, _ in MODEL_RUN_KEYS),
)

#: Every table engine 19 writes, in the order it writes them. The order is load-bearing
#: three times over, and every one of the three is silent when it is wrong; a fourth rule,
#: below them, is kept for clarity rather than because anything breaks today.
#:
#: 1. `positions` and `trades` before `equity_snapshots`, because the snapshot's
#:    ``open_position_count`` and ``realised_pnl_cum`` are read back out of the store
#:    after this tick's rows have landed.
#: 2. **Within `positions`: engine 21's rows, then engine 22's.** Both publish rows for
#:    the same `position_id` on a tick where a position is marked and then closed, and
#:    `write_position` upserts, so whichever engine 19 writes *last* is the stored state.
#:    Engine 22 runs after 21 in the manage chain, so closed must win. The other order
#:    records a position closed this tick as still open with a mark on it — a row the
#:    console renders and `safety` counts. Lead ruling, 2026-09-16.
#: 3. **Within `orders`: engine 18's, then 21's, then 22's.** Same upsert, same reason,
#:    keyed on `userref`: an entry 18 placed and 21 immediately cancelled must end as
#:    cancelled. 18 runs on the opportunity chain and 21 and 22 on the manage chain, so
#:    this is chain order, not a preference.
#: 4. **`approvals` before `trades`**, which reads them. An entry cannot be placed and
#:    closed on one tick, so today the order changes nothing; it is kept so that it never
#:    has to be reasoned about.
WRITTEN_TABLES: Final[tuple[str, ...]] = (
    "block_records",
    "approvals",
    "positions",
    "orders",
    "trades",
    "rejections",
    "equity_snapshots",
)


class MissingInputError(Exception):
    """An input engine 19 needs is present but unusable.

    **Raised, not swallowed.** Contract rule 7 turns an uncaught exception into an
    ``ERROR`` result, which is exactly the right outcome: "engine 21 published nothing
    because it is Phase 6" and "engine 21 published something engine 19 could not read"
    are two different facts, and a broad ``except`` that treated the second as the first
    would record a tick as clean when the writer had failed on it.
    """


class MemoryState(BaseModel):
    """What engine 19 publishes, so a tick that wrote nothing is still legible.

    The counts are per table and are always present, zeros included. That is the point:
    the console and the log need to be able to tell "engine 19 ran and there was nothing
    to record" from "engine 19 did not run", and a payload that omitted the zeros makes
    those two look identical.

    ``sources_present`` names which upstream keys engine 19 actually found. Engines 18,
    21 and 22 are Phase 6, so their keys are absent for now, and *absent* must read as
    nothing-to-record rather than as record-a-zero. Publishing which sources were seen
    is what keeps that distinction visible to somebody reading a log line rather than
    the code.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cycle_id: int
    run_id: str
    written: dict[str, int]
    sources_present: tuple[str, ...] = ()
    equity: Money | None = None
    peak_equity: Money | None = None
    equity_skipped_reason: str | None = None
    """Why no `equity_snapshots` row was written, or ``None`` when one was.

    A tick with no equity information writes no row rather than a zero — a zero equity
    row is a 100% drawdown and trips the breaker — so the skip has to say why, or a
    silent gap in the curve is indistinguishable from a silent bug."""

    hold_reason: str | None = None

    def to_state_data(self) -> dict[str, Any]:
        """The JSON-serialisable payload for ``state["memory"]``. Money as strings."""
        return {
            "cycle_id": self.cycle_id,
            "run_id": self.run_id,
            "written": dict(self.written),
            "sources_present": list(self.sources_present),
            "equity": None if self.equity is None else format(self.equity, "f"),
            "peak_equity": (
                None if self.peak_equity is None else format(self.peak_equity, "f")
            ),
            "equity_skipped_reason": self.equity_skipped_reason,
            "hold_reason": self.hold_reason,
            "rows_written": sum(self.written.values()),
        }


def decimal_field(payload: Any, field: str, *, where: str) -> Decimal:
    """One money field out of a ``state`` payload, as an exact ``Decimal``.

    ``state`` carries money as an exact decimal string, so this refuses a ``float``
    rather than coercing one: a float that has already been constructed has already lost
    precision, and coercing it preserves the wrong number exactly.
    """
    value = payload.get(field) if hasattr(payload, "get") else None
    if value is None:
        return Decimal(0)
    if isinstance(value, float):
        raise MissingInputError(
            f"{where}.{field} crossed state as a float; money is an exact decimal string"
        )
    try:
        return Decimal(str(value))
    except ArithmeticError as exc:
        raise MissingInputError(f"{where}.{field} is not a decimal: {value!r}") from exc
