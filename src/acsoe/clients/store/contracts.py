"""Typed rows for every table in `db/migrations/`.

This module is the seam named in `context/ownership.md`: B produces it, A and C consume
it. Nothing outside `clients/store/` should ever see a raw `sqlite3.Row`.

**Money.** Every monetary field is :data:`Money`, which is a `Decimal` that *refuses a
float*. Pydantic would otherwise happily coerce `0.1` into `Decimal('0.1000000000000000055...')`,
and a drifting equity series moves the drawdown threshold that liquidates the account.
The rule is `Decimal` in Python, exact decimal string in SQLite, and conversion in exactly
one place — :mod:`acsoe.clients.store.client`.

**Time.** Timestamps are integer microseconds since the Unix epoch, UTC. They originate
from `context.now`; nothing in this package reads a clock. :func:`to_micros` and
:func:`from_micros` are the only conversions.

**Ticks.** A tick is `(run_id, cycle_id)`. `cycle_id` restarts at 1 with each process, so
it identifies nothing on its own and is never an ordering key — cross-restart sequences
order by `ts`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Final

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

MICROSECONDS_PER_SECOND: Final = 1_000_000


def _reject_float(value: Any) -> Any:
    """Refuse a float where money is expected.

    A float that has already been constructed has already lost precision, so coercing it
    to `Decimal` preserves the wrong number exactly. The only safe response is to refuse
    it at the boundary and make the caller say what it meant.
    """
    if isinstance(value, float):
        raise ValueError(
            "money must never be a float — pass a Decimal or an exact decimal string"
        )
    return value


#: A `Decimal` that refuses a float. Every money field in this module uses it.
Money = Annotated[Decimal, BeforeValidator(_reject_float)]

#: Microseconds since the Unix epoch, UTC. Never a naive datetime, never a float.
Micros = int


def to_micros(moment: datetime) -> int:
    """Convert a timezone-aware UTC datetime to microseconds since the epoch."""
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware; naive datetimes are a defect")
    return int(moment.astimezone(UTC).timestamp() * MICROSECONDS_PER_SECOND)


def from_micros(micros: int) -> datetime:
    """Convert microseconds since the epoch to a timezone-aware UTC datetime."""
    return datetime.fromtimestamp(micros / MICROSECONDS_PER_SECOND, tz=UTC)


class RunMode(StrEnum):
    """The three modes of `context/architecture-context.md`."""

    PAPER = "paper"
    LIVE = "live"
    REPLAY = "replay"


class SystemMode(StrEnum):
    """`state["system"]["mode"]`, persisted for the console — spec 31.

    A different axis from :class:`RunMode`. `RunMode` is paper/live/replay and says
    which world the daemon is trading in; `SystemMode` is idle/running/frozen and says
    whether it is trading at all. `ui-context.md` is explicit that confusing the two is
    what left the Phase 1 status band unable to render Running.

    **This value is written for the console to read, never for the daemon to resume
    from.** Mode is still never restored from the store: a daemon always starts `idle`
    and only reaches `running` through an `activate` command, so a crashed daemon comes
    back not trading with the manage chain still watching whatever is open. Nothing may
    read this back into `state`.

    There is no `FROZEN_CLOSING`. `frozen` plus `close_intent` is a distinguishable
    state in `state["system"]`, but the console's status band renders exactly four
    readings and that is not one of them, so persisting `close_intent` would be an
    unused column and a second thing the command reader must remember to write. If a
    reader ever needs it, it is another additive column and another migration.
    """

    IDLE = "idle"
    RUNNING = "running"
    FROZEN = "frozen"


class BlockStatus(StrEnum):
    """`block_records.status`. `safety`'s error rate counts the ERROR rows."""

    BLOCK = "BLOCK"
    ERROR = "ERROR"


class PositionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class OrderStatus(StrEnum):
    """`orders.status`. `safety` counts RESTING; engine 21 cancels them."""

    PENDING = "pending"
    RESTING = "resting"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderIntent(StrEnum):
    ENTRY = "entry"
    EXIT = "exit"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    LIMIT = "limit"
    MARKET = "market"


class TradeOutcome(StrEnum):
    """Which barrier the position hit, plus the invariant 14 liquidation."""

    TARGET = "target"
    STOP = "stop"
    TIMEOUT = "timeout"
    LIQUIDATION = "liquidation"


class CommandName(StrEnum):
    """The three commands of `context/architecture-context.md`'s command table.

    The `commands.command` column deliberately carries no CHECK constraint and
    :class:`CommandRow` deliberately types it as `str`: an unrecognised command must be
    storable so that the orchestrator's "ignore it and log a warning" path is reachable
    and testable. This enum is for writers, not for readers.
    """

    ACTIVATE = "activate"
    FREEZE = "freeze"
    CLOSE_ALL = "close_all"


class CommandSource(StrEnum):
    """The two writers of the command table: the console, and engine 17 `safety`."""

    CONSOLE = "console"
    SAFETY = "safety"


class _Row(BaseModel):
    """Base for every row model."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)


class RunRow(_Row):
    """One daemon process. Written by the orchestrator at startup, before the first tick.

    **`system_mode` and `system_mode_at` are read-only on this model.** They are carried
    here because the table carries them, so a `SELECT *` round trip validates and so a
    caller that already has a `RunRow` need not make a second query — but
    :meth:`StoreClient.write_run` deliberately does not write them, and
    :meth:`StoreClient.set_system_mode` is their only writer.

    That split is the point rather than an oversight. The orchestrator writes this row
    once at startup, when no mode has been decided yet, and the command reader sets the
    mode later on a tick of its own. If `write_run` also wrote these columns, any
    subsequent run-row write — stamping `ended_at`, say — would carry whatever
    `system_mode` the caller happened to have and silently overwrite the real one. One
    column, one writer. A read-modify-write through `write_run` is therefore a no-op on
    the mode, which is the behaviour a caller expects and not a clobber.
    """

    id: int | None = None
    run_id: str
    mode: RunMode
    started_at: Micros
    ended_at: Micros | None = None
    acsoe_version: str | None = None
    config_digest: str | None = None
    updated_at: Micros
    system_mode: SystemMode | None = None
    system_mode_at: Micros | None = None


class SystemModeRow(_Row):
    """The persisted system mode for one run — spec 31's seam with C's console.

    Returned by :meth:`StoreClient.system_mode`. The two nulls are different facts and
    the console must not collapse them:

    - The method returns `None` when **there is no `runs` row for that `run_id`**. That
      is a defect or a race, not a mode.
    - It returns this model with `mode is None` when **the run exists and no daemon has
      written a mode for it yet**. That is the ordinary case before the first command is
      read, and the console renders an idle reading for it.

    Both render as an idle reading, per spec 32 — "a missing value renders idle and
    never raises" — but only one of them is normal, and a reader that cannot tell them
    apart cannot log the abnormal one.
    """

    run_id: str
    mode: SystemMode | None = None
    at: Micros | None = None


class CommandRow(_Row):
    """One command. Two-phase consumption: `claimed_at`, then `consumed_at`.

    A row with `claimed_at` set and `consumed_at` null is an interrupted command and is
    re-applied at startup — without that, a daemon killed between reading `close_all` and
    finishing the liquidation restarts with the command marked done and positions open.
    """

    id: int | None = None
    command: str
    source: CommandSource
    reason: str | None = None
    payload: str | None = None
    created_at: Micros
    created_by_run_id: str | None = None
    claimed_at: Micros | None = None
    claimed_by_run_id: str | None = None
    consumed_at: Micros | None = None
    updated_at: Micros


class BlockRecordRow(_Row):
    """One guard blocker on one tick. Written by engine 19 `memory`.

    The guard chain never breaks early, so two guards can block on the same tick and
    produce two rows. `is_primary` marks the first — the one that gated the opportunity
    chain — and the database enforces at most one per `(run_id, cycle_id)`.
    """

    id: int | None = None
    cycle_id: int
    run_id: str
    ts: Micros
    blocked_by: str
    block_reason: str
    is_primary: bool
    status: BlockStatus
    updated_at: Micros


class EquitySnapshotRow(_Row):
    """One tick of the equity curve. `safety` reads the latest `equity` and `peak_equity`.

    The cash and unrealised components are stored rather than derived because the Phase 7
    alpha attribution reads the full curve *including cash periods*.
    """

    id: int | None = None
    cycle_id: int
    run_id: str
    ts: Micros
    currency: str
    equity: Money
    peak_equity: Money
    cash: Money
    positions_value: Money
    unrealised_pnl: Money
    realised_pnl_cum: Money
    open_position_count: int
    updated_at: Micros


class PositionRow(_Row):
    """One position. `safety` counts the open ones; the console renders them.

    `hold_reason` (migration 0003) is why the manage chain placed no exit on the tick
    that last wrote this row, and it belongs with `last_price` and `unrealised_pnl`
    rather than with `opened_at` and `closed_at`: all three are facts about **now**,
    overwritten every tick, not events. Engine 19 `memory` is the only writer.

    **`None` means "did not hold", never "unknown".** Engine 21 publishes null on every
    tick it did not hold — including throughout a liquidation, which never holds — and
    engine 19 writes that null through. A hold left in place after the hold ended would
    render an hour-old reason forever, which is worse than rendering nothing: the console
    would assert a paused manage chain over one running normally.
    """

    position_id: str
    run_id: str
    cycle_id: int
    pair: str
    base: str
    quote: str
    side: str = "long"
    status: PositionStatus
    qty: Money
    entry_price: Money
    target_price: Money
    stop_price: Money
    timeout_at: Micros
    entry_userref: int | None = None
    last_price: Money | None = None
    unrealised_pnl: Money | None = None
    hold_reason: str | None = None
    opened_at: Micros
    closed_at: Micros | None = None
    trade_id: str | None = None
    updated_at: Micros

    @field_validator("side")
    @classmethod
    def _long_only(cls, value: str) -> str:
        if value != "long":
            raise ValueError("the system is long-only; see context/project-overview.md")
        return value

    @field_validator("hold_reason")
    @classmethod
    def _a_hold_reason_or_null(cls, value: str | None) -> str | None:
        """Refuse a blank hold reason; `None` is the way to say "did not hold".

        Mirrors migration 0003's CHECK, deliberately down to `trim()`. A blank string is
        the usual way "unknown" gets past a nullable column: it is non-null, so every
        `is not None` read calls it a hold, and it renders as nothing, so the console
        shows a held position with no reason on it.
        """
        if value is not None and not value.strip():
            raise ValueError(
                "hold_reason is a reason or None; None means the manage chain did not "
                "hold, and a blank string means neither"
            )
        return value


class OrderRow(_Row):
    """One order, including a resting post-only entry.

    Keyed by `userref` so the invariant 8 idempotency check is a primary-key lookup.
    """

    userref: int
    order_id: str | None = None
    run_id: str
    cycle_id: int
    position_id: str | None = None
    pair: str
    side: OrderSide
    intent: OrderIntent
    order_type: OrderType
    oflags: str = ""
    status: OrderStatus
    qty: Money
    limit_price: Money | None = None
    filled_qty: Money
    avg_fill_price: Money | None = None
    fee: Money | None = None
    placed_at: Micros
    closed_at: Micros | None = None
    updated_at: Micros


class TradeRow(_Row):
    """One closed round trip. `safety` reads the trailing run ordered by `closed_at`.

    Invariant 7 requires FX exposure against the reporting currency to be recorded per
    trade rather than absorbed into PnL, hence both PnL figures and both FX rates.
    Invariant 2 and invariant 14 require any tolerated fetch failure or paper-mode
    fallback to be recorded here, so a fill is never mistaken for one priced on good data.
    """

    trade_id: str
    position_id: str | None = None
    run_id: str
    cycle_id: int
    pair: str
    base: str
    quote: str
    side: str = "long"
    qty: Money
    entry_price: Money
    exit_price: Money
    entry_fee: Money
    exit_fee: Money
    entry_userref: int | None = None
    exit_userref: int | None = None
    opened_at: Micros
    closed_at: Micros
    outcome: TradeOutcome
    realised_pnl: Money
    realised_pnl_pct: Money
    realised_pnl_quote: Money
    reporting_currency: str
    fx_rate_entry: Money
    fx_rate_exit: Money
    fallbacks_used: tuple[str, ...] = ()
    updated_at: Micros

    @field_validator("side")
    @classmethod
    def _long_only(cls, value: str) -> str:
        if value != "long":
            raise ValueError("the system is long-only; see context/project-overview.md")
        return value


class RejectionRow(_Row):
    """One candidate refused, with its reason and its SHAP row.

    Not the same thing as a block record: a rejection is one *candidate*, a block record
    is one *tick*, and most blocked ticks never had a candidate. They join on
    `(run_id, cycle_id)`.

    `reason` is written for the operator because the console renders it — "Net edge
    -0.21% after fees", not `cost_gate_fail`. `reason_code` is the machine-readable one.
    """

    id: int | None = None
    cycle_id: int
    run_id: str
    ts: Micros
    pair: str
    rejected_by: str
    reason_code: str
    reason: str
    expected_move_pct: Money | None = None
    friction_pct: Money | None = None
    net_edge_pct: Money | None = None
    hurdle_pct: Money | None = None
    candidate_score: float | None = None
    shap_ref: str | None = None
    details: str | None = None
    updated_at: Micros


class LeaderboardRow(_Row):
    """One trained model version, ranked.

    The metrics are statistics, so `float` is correct for them. `net_pnl` is money.

    `base_rate_brier` (migration 0004) is the score a model predicting the fold's own
    class frequency every time would have got — the null hypothesis `brier` is measured
    against. **`None` means "not recorded", never "no baseline"**: every row written
    before 0004 has none, and engine 14 must read the absence as an absence. It is
    deliberately not derived from `win_rate * (1 - win_rate)`, which is a plausible
    number answering a different question — `brier` is over every row of the fold and
    `win_rate` is over the BUY subset only.
    """

    id: int | None = None
    model_id: str
    model_version: str
    training_run_id: str | None = None
    trained_at: Micros
    fold: str | None = None
    n_trades: int
    win_rate: float | None = None
    sharpe: float | None = None
    deflated_sharpe: float | None = None
    alpha: float | None = None
    beta: float | None = None
    brier: float | None = None
    base_rate_brier: float | None = None
    net_pnl: Money | None = None
    reporting_currency: str | None = None
    promoted: bool = False
    notes: str | None = None
    updated_at: Micros


class DataGuardOutage(_Row):
    """What :meth:`StoreClient.stored_consecutive_data_block_ticks_excluding_current_tick`
    counts, returned in full for callers that need the detail as well as the number.

    `ticks` are `(run_id, cycle_id)` pairs in `ts` order, oldest first.
    """

    ticks: tuple[tuple[str, int], ...] = Field(default=())
    first_ts: Micros | None = None
    last_ts: Micros | None = None

    @property
    def length(self) -> int:
        return len(self.ticks)
