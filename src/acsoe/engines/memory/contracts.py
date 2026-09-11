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
    "BALANCES_FIELD",
    "BLOCK_REASON_KEY",
    "CANDIDATE_PAIR_PATH",
    "CLOSED_TRADES_FIELD",
    "CYCLE_ID_KEY",
    "ECONOMICS_FIELDS",
    "EXCHANGE_KEY",
    "EXIT_KEY",
    "GUARD_BLOCKERS_KEY",
    "HOLD_REASON_FIELD",
    "ORDERS_FIELD",
    "POSITIONS_FIELD",
    "POSITIONS_VALUE_FIELD",
    "POSITION_MANAGER_KEY",
    "REASON_CODE_FIELD",
    "SCOUT_KEY",
    "STATE_KEY",
    "TRADING_BLOCKED_BY_KEY",
    "UNREALISED_PNL_FIELD",
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
#: chain, which is what makes the tick a *rejection* rather than only a block.
TRADING_BLOCKED_BY_KEY: Final = "trading_blocked_by"
BLOCK_REASON_KEY: Final = "block_reason"

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

#: Engine 22 `exit` (B), Phase 6. Round trips that closed on this tick.
EXIT_KEY: Final = "exit"
CLOSED_TRADES_FIELD: Final = "closed_trades"

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

#: Every table engine 19 writes, in the order it writes them. The order is load-bearing:
#: `positions` and `trades` are written **before** `equity_snapshots`, because the
#: snapshot's ``open_position_count`` and ``realised_pnl_cum`` are read back out of the
#: store after this tick's rows have landed.
WRITTEN_TABLES: Final[tuple[str, ...]] = (
    "block_records",
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
