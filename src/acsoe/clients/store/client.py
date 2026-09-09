"""The one typed way in and out of SQLite.

Engines never open a file, never see a `sqlite3.Row`, and never build SQL. They call a
named method here and get a pydantic model back.

**The money boundary is this module and nowhere else.** `Decimal` in, exact decimal
string out; exact decimal string in, `Decimal` out. The schema additionally carries
`CHECK (typeof(col) = 'text')` on every money column, so a float that somehow reached a
write would be refused by the database rather than silently stored.

**No business logic.** These methods return rows and counts. Engine 17 `safety` decides
what a drawdown or a loss streak means; this file only knows how to fetch one.

**Nothing here reads a clock.** Every timestamp is passed in, ultimately from
`context.now`. That is what makes replay faithful.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from decimal import Decimal
from enum import Enum
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Self

from acsoe.clients.store.connection import close_connection, open_connection
from acsoe.clients.store.contracts import (
    BlockRecordRow,
    BlockStatus,
    CommandRow,
    DataGuardOutage,
    EquitySnapshotRow,
    LeaderboardRow,
    OrderIntent,
    OrderRow,
    OrderStatus,
    PositionRow,
    PositionStatus,
    RejectionRow,
    RunMode,
    RunRow,
    SystemMode,
    SystemModeRow,
    TradeRow,
)
from acsoe.clients.store.migrations import apply_migrations

#: Engine 4's registry name. `safety`'s outage counter looks for rows carrying it.
DATA_GUARD_ENGINE: Final = "data_guard"

#: Tables whose `updated_at` contributes to the console's poll watermark.
WATERMARK_TABLES: Final[tuple[str, ...]] = (
    "block_records",
    "commands",
    "equity_snapshots",
    "leaderboard",
    "orders",
    "positions",
    "rejections",
    "runs",
    "trades",
)

#: How many ticks the outage counter will walk back before giving up. Any real
#: threshold is two orders of magnitude below this; the bound only exists so a
#: pathological table cannot turn one read into a full scan of a year of ticks.
DEFAULT_OUTAGE_SCAN_LIMIT: Final = 5_000

_JSON_COLUMNS: Final[frozenset[str]] = frozenset({"fallbacks_used"})

#: Columns the schema stores as `INTEGER ... CHECK (col IN (0, 1))` and the contracts
#: model as `bool`. SQLite has no boolean type, so these read back as `0`/`1`.
#:
#: Converted here rather than left to pydantic. In lax mode pydantic accepts `0` and `1`
#: for a `bool` and this is unnecessary; in strict mode it refuses them. That difference
#: is normally settled by the model config and would not be worth a constant — except
#: that A observed `BlockRecordRow.is_primary — Input should be a valid boolean
#: [input_value=0, input_type=int]` from this module in one full-suite run, not
#: reproducible when the file was run alone, on a model that is not strict. A lax
#: validator behaving as a strict one is the signature of the known intermittent
#: pydantic-core fault in Known Risks, arriving as a wrong answer rather than as a crash.
#:
#: The hazard is not the failure, it is the diagnosis: a `ValidationError` naming a field
#: invites someone to loosen that field's type, which would silently accept a real bad
#: value forever. Converting at the boundary makes the whole class unreachable and costs
#: one dict lookup per row.
_BOOLEAN_COLUMNS: Final[frozenset[str]] = frozenset({"is_primary", "promoted"})


def money_to_text(value: Decimal) -> str:
    """The canonical stored form of a money value. One rule, in one place.

    **Plain decimal notation, never scientific.** `str(Decimal("1E+3"))` gives `"1E+3"`,
    which round-trips through `Decimal()` exactly but is unreadable in a database
    browser and compares unequal to `"1000"` under any SQL text comparison. `format(d,
    "f")` always writes the digits out.

    **Trailing zeros are preserved exactly as the `Decimal` carries them**, because they
    are the quantum: `Decimal("1000.00")` means cents and `Decimal("1000")` means units,
    and normalising the difference away would throw the precision the caller chose.
    A value that starts as `"1000.00"` in `config/default.yaml` therefore reaches
    `equity_snapshots` as `1000.00`, unchanged.

    **A non-finite value is refused.** `Decimal("NaN")` would store as the text `"NaN"`
    and read back as a `Decimal` that compares false against everything, including
    itself — a drawdown threshold that silently never trips.
    """
    if not value.is_finite():
        raise StoreError(f"refusing to store a non-finite money value: {value!r}")
    return format(value, "f")


def _to_sql(value: Any) -> Any:
    """Adapt a Python value for SQLite.

    `bool` is checked before anything else numeric because `bool` is a subclass of
    `int` and would otherwise be stored as `True`/`False` by the driver's own rules.
    """
    if isinstance(value, Decimal):
        return money_to_text(value)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return json.dumps(list(value))
    return value


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Turn a raw row into kwargs a contract model accepts.

    Two conversions, and both exist because SQLite's type system is narrower than the
    contracts': JSON text back to a tuple, and `0`/`1` back to `bool`. Everything else,
    money included, is handed to pydantic as stored.
    """
    data: dict[str, Any] = dict(row)
    for column in _JSON_COLUMNS & data.keys():
        raw = data[column]
        data[column] = tuple(json.loads(raw)) if raw else ()
    for column in _BOOLEAN_COLUMNS & data.keys():
        value = data[column]
        if value is not None:
            data[column] = bool(value)
    return data


class StoreError(RuntimeError):
    """The store could not do what was asked."""


class StoreClient:
    """SQLite and Parquet access for the whole system.

    Satisfies the `store` member of the `Clients` Protocol declared in `core/`.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = open_connection(self._db_path)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            close_connection(self._conn)
            self._conn = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def migrate(self, *, applied_at: int | None = None) -> list[int]:
        """Bring the database up to the latest schema. Returns the versions applied."""
        self.close()
        return apply_migrations(self._db_path, applied_at=applied_at)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a group of writes atomically."""
        conn = self.connection
        conn.execute("BEGIN")
        try:
            yield conn
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")

    # ------------------------------------------------------------------
    # Low-level write helpers
    # ------------------------------------------------------------------

    def _insert(self, table: str, payload: Mapping[str, Any]) -> int:
        columns = [name for name, value in payload.items() if not (name == "id" and value is None)]
        placeholders = ", ".join("?" for _ in columns)
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        )
        cursor = self.connection.execute(sql, [_to_sql(payload[c]) for c in columns])
        return int(cursor.lastrowid or 0)

    def _upsert(self, table: str, payload: Mapping[str, Any], key: Sequence[str]) -> None:
        """Insert, or update the row with the same primary key.

        Deliberately not `INSERT OR REPLACE`. `REPLACE` resolves a conflict on *any*
        unique index by deleting the conflicting row, so writing a second open position
        for a pair would silently delete the first one and quietly defeat
        `ux_positions_open_pair`. `ON CONFLICT (<pk>) DO UPDATE` resolves only the
        primary-key conflict and still raises on every other constraint, which is the
        whole point of having them.
        """
        columns = list(payload.keys())
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c not in key)
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {updates}"
        )
        self.connection.execute(sql, [_to_sql(payload[c]) for c in columns])

    # ------------------------------------------------------------------
    # Watermark — what the console polls (ui-context.md)
    # ------------------------------------------------------------------

    def watermark(self) -> int:
        """The highest `updated_at` across every console-rendered table.

        Monotonic as long as callers stamp `updated_at` from `context.now`. The console
        polls this at `console.poll_interval_ms` and pushes over its WebSocket only when
        it moves.
        """
        parts = " UNION ALL ".join(
            f"SELECT MAX(updated_at) AS m FROM {table}" for table in WATERMARK_TABLES
        )
        row = self.connection.execute(f"SELECT MAX(m) AS w FROM ({parts})").fetchone()
        return int(row["w"] or 0)

    # ------------------------------------------------------------------
    # The six reads engine 17 `safety` depends on
    # ------------------------------------------------------------------

    def latest_equity_snapshot(self) -> EquitySnapshotRow | None:
        """The most recent equity row, by `ts`.

        `safety` computes drawdown as `(peak_equity - equity) / peak_equity`. This
        method does not compute it: the client returns rows, `safety` decides.
        """
        row = self.connection.execute(
            "SELECT * FROM equity_snapshots ORDER BY ts DESC, id DESC LIMIT 1"
        ).fetchone()
        return None if row is None else EquitySnapshotRow(**_row_to_dict(row))

    def recent_closed_trades(self, limit: int) -> tuple[TradeRow, ...]:
        """Closed trades, most recent first, ordered by `closed_at`.

        `safety` walks this for the consecutive-loss limit. Ordered by `closed_at`
        rather than by insertion, because a trade opened earlier can close later.
        """
        rows = self.connection.execute(
            "SELECT * FROM trades ORDER BY closed_at DESC, trade_id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return tuple(TradeRow(**_row_to_dict(row)) for row in rows)

    def block_records_in_window(
        self,
        *,
        start_ts: int,
        end_ts: int,
        status: BlockStatus | None = None,
        blocked_by: str | None = None,
    ) -> tuple[BlockRecordRow, ...]:
        """Block records with `start_ts <= ts <= end_ts`, oldest first."""
        clauses = ["ts >= ?", "ts <= ?"]
        params: list[Any] = [int(start_ts), int(end_ts)]
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if blocked_by is not None:
            clauses.append("blocked_by = ?")
            params.append(blocked_by)
        sql = (
            "SELECT * FROM block_records "
            f"WHERE {' AND '.join(clauses)} ORDER BY ts ASC, id ASC"
        )
        rows = self.connection.execute(sql, params).fetchall()
        return tuple(BlockRecordRow(**_row_to_dict(row)) for row in rows)

    def count_block_records_in_window(
        self,
        *,
        start_ts: int,
        end_ts: int,
        status: BlockStatus | None = None,
        blocked_by: str | None = None,
    ) -> int:
        """How many block records fall in the window. `safety`'s error rate uses
        `status=BlockStatus.ERROR` over the trailing `safety.error_rate_window_s`."""
        return len(
            self.block_records_in_window(
                start_ts=start_ts, end_ts=end_ts, status=status, blocked_by=blocked_by
            )
        )

    def stored_consecutive_data_block_ticks_excluding_current_tick(
        self,
        *,
        current_tick: tuple[str, int] | None,
        scan_limit: int = DEFAULT_OUTAGE_SCAN_LIMIT,
    ) -> int:
        """The stored half of `safety`'s outage count. **Not the effective count.**

        The name is deliberately unwieldy. The number this returns is off by one from
        the number the breaker acts on, and the correction is the caller's:

            effective = stored + (1 if this tick is blocked by data_guard else 0)

        Engine 4 `data_guard` runs *before* engine 17 `safety` in the guard chain, so
        when `safety` runs, the current tick's block is already visible in
        `state["trading_blocked_by"]`. Engine 19 `memory` runs *later*, in the manage
        chain, so the store holds records only through tick T-1. Adding the current tick
        here would double-count it; omitting it in the caller fires the breaker a minute
        late. Neither is acceptable, so the boundary is in the method name.

        **`current_tick` has no default, and `safety` must pass its own
        `(run_id, cycle_id)`.** "Consecutive ticks through T-1" is not a question the
        table can answer without knowing T: a clean tick writes no `block_records` row,
        so an outage that ended two ticks ago is indistinguishable from one still
        running unless the walk is anchored to the current tick. `None` asks the other
        question — "what is the trailing run of ticks *in the table*" — which is right
        for inspecting a seeded fixture that has no current tick, and wrong for the
        breaker. See :meth:`stored_data_guard_outage_excluding_current_tick`.
        """
        return self.stored_data_guard_outage_excluding_current_tick(
            current_tick=current_tick, scan_limit=scan_limit
        ).length

    def stored_data_guard_outage_excluding_current_tick(
        self,
        *,
        current_tick: tuple[str, int] | None,
        scan_limit: int = DEFAULT_OUTAGE_SCAN_LIMIT,
    ) -> DataGuardOutage:
        """The trailing run of stored ticks carrying a `data_guard` block record.

        Three things this gets right that the obvious query does not:

        **Ordered by `ts`, never by `cycle_id`.** `cycle_id` restarts at 1 with each
        process, so ordering by it silently interleaves two runs — and surviving a
        restart is precisely why the counter lives in the store rather than in `state`.

        **Counts ticks, not rows.** The guard chain never breaks early, so `data_guard`
        and `safety` can both block on one tick and write two rows. That tick
        contributes one.

        **A clean tick ends the outage, and a clean tick leaves no row.** Invariant 14
        says "consecutive *ticks*", but an unblocked tick writes no `block_records` row
        at all — so two rows being adjacent in this table does not make their ticks
        adjacent in time. `cycle_id` increments by one per tick within a run, which is
        enough to reconstruct the missing ones. Walking backwards from a tick
        `(run, cycle)`, the tick immediately before it is:

        - `(run, cycle - 1)` when `cycle > 1`. If the next row back is anything else,
          at least one tick in between passed the guard and the run is broken there.
        - the last tick of the *previous* run when `cycle == 1`. Its identity is
          unknowable, so the crossing is allowed and the run continues — which is the
          behaviour the docs require, since a daemon that dies mid-outage must not reset
          the clock on an outage that is still happening.

        **`current_tick` is required, and `None` is a different question.** Without the
        anchor the walk starts at whatever the newest stored tick happens to be, and
        cannot tell "tick T-1 was blocked" from "tick T-1 was clean and therefore wrote
        nothing". Those give different answers, and the anchorless one over-counts —
        firing the breaker early and liquidating an account over an outage that already
        ended, which is why the parameter has no default and every caller has to say
        which question it is asking. With the anchor, the newest stored tick has to *be*
        `(run_id, cycle_id - 1)` or the run is empty. Pass `None` only when inspecting a
        database that has no current tick, such as a seeded fixture, where "the trailing
        run of stored ticks" is exactly the question being asked.

        **One residual blind spot, stated rather than hidden.** If a daemon's final tick
        before dying was *clean* and its first tick after restarting is blocked, nothing
        in `block_records` records that clean tick, and this counter joins the two runs'
        outages into one. The anchor cannot help: `cycle_id` restarts at 1, so there is
        no arithmetic that reaches back across the restart. It over-counts, which fires
        the breaker early rather than late. Closing it would mean reading the true tick
        timeline from `equity_snapshots`, which has a row for every tick — but
        `architecture-context.md` fixes this counter's source as `block_records`, so
        that is an escalation and not a decision to take here.
        """
        rows = self.connection.execute(
            """
            SELECT run_id,
                   cycle_id,
                   MIN(ts) AS ts,
                   MAX(CASE WHEN blocked_by = ? THEN 1 ELSE 0 END) AS has_data_guard
            FROM block_records
            GROUP BY run_id, cycle_id
            ORDER BY ts DESC, run_id DESC, cycle_id DESC
            LIMIT ?
            """,
            (DATA_GUARD_ENGINE, int(scan_limit)),
        ).fetchall()

        ticks: list[tuple[str, int]] = []
        timestamps: list[int] = []
        # Seeding the walk with the current tick is the whole anchor: the adjacency
        # check below then requires the newest stored tick to be the one immediately
        # before it, rather than accepting whatever row happens to be newest.
        previous: tuple[str, int] | None = current_tick
        for row in rows:
            if not int(row["has_data_guard"]):
                break
            run_id = str(row["run_id"])
            cycle_id = int(row["cycle_id"])
            if previous is not None:
                prior_run, prior_cycle = previous
                # Walking backwards in time, `previous` is the newer tick. The tick
                # immediately before it is (prior_run, prior_cycle - 1) unless
                # prior_cycle is 1, in which case the newer tick is the first of its
                # run and the one before it belongs to whatever ran before.
                if prior_cycle > 1 and (run_id, cycle_id) != (prior_run, prior_cycle - 1):
                    break
                if prior_cycle == 1 and run_id == prior_run:
                    break
            ticks.append((run_id, cycle_id))
            timestamps.append(int(row["ts"]))
            previous = (run_id, cycle_id)

        ticks.reverse()
        timestamps.reverse()
        return DataGuardOutage(
            ticks=tuple(ticks),
            first_ts=timestamps[0] if timestamps else None,
            last_ts=timestamps[-1] if timestamps else None,
        )

    def count_open_positions(self) -> int:
        """How many positions are open. Invariant 14 gates escalation on this."""
        row = self.connection.execute(
            "SELECT COUNT(*) AS n FROM positions WHERE status = ?",
            (PositionStatus.OPEN.value,),
        ).fetchone()
        return int(row["n"])

    def count_resting_orders(self, *, intent: OrderIntent | None = None) -> int:
        """How many orders are resting on the book.

        A resting post-only buy is exposure that has not happened yet, which is why
        invariant 14 escalates on open positions **or** resting entry orders.
        """
        if intent is None:
            row = self.connection.execute(
                "SELECT COUNT(*) AS n FROM orders WHERE status = ?",
                (OrderStatus.RESTING.value,),
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT COUNT(*) AS n FROM orders WHERE status = ? AND intent = ?",
                (OrderStatus.RESTING.value, intent.value),
            ).fetchone()
        return int(row["n"])

    # ------------------------------------------------------------------
    # Commands — the console and `safety` write, the orchestrator reads
    # ------------------------------------------------------------------

    def append_command(self, row: CommandRow) -> int:
        """Append a command row. Returns its id."""
        return self._insert("commands", row.model_dump())

    def pending_commands(self) -> tuple[CommandRow, ...]:
        """Rows never claimed, oldest first."""
        rows = self.connection.execute(
            "SELECT * FROM commands WHERE claimed_at IS NULL ORDER BY created_at ASC, id ASC"
        ).fetchall()
        return tuple(CommandRow(**_row_to_dict(row)) for row in rows)

    def claimed_unconsumed_commands(self) -> tuple[CommandRow, ...]:
        """Interrupted commands: claimed but never completed, oldest first.

        The orchestrator re-applies these before the first tick. Without it, a daemon
        killed part-way through a `close_all` would restart with the command marked done,
        the in-memory intent gone, and positions still open.
        """
        rows = self.connection.execute(
            "SELECT * FROM commands "
            "WHERE claimed_at IS NOT NULL AND consumed_at IS NULL "
            "ORDER BY created_at ASC, id ASC"
        ).fetchall()
        return tuple(CommandRow(**_row_to_dict(row)) for row in rows)

    def claim_command(self, command_id: int, *, claimed_at: int, run_id: str) -> bool:
        """Stamp `claimed_at`. Returns False if the row was already claimed.

        The `claimed_at IS NULL` guard is what gives idempotency: a row already claimed
        is never applied twice within a run.
        """
        cursor = self.connection.execute(
            "UPDATE commands SET claimed_at = ?, claimed_by_run_id = ?, updated_at = ? "
            "WHERE id = ? AND claimed_at IS NULL",
            (int(claimed_at), run_id, int(claimed_at), int(command_id)),
        )
        return cursor.rowcount == 1

    def mark_command_consumed(self, command_id: int, *, consumed_at: int) -> bool:
        """Stamp `consumed_at`, but only once the effect is actually complete.

        For `activate` and `freeze` that is immediate. For `close_all` it is only when
        every resting entry order is cancelled and every position closed.
        """
        cursor = self.connection.execute(
            "UPDATE commands SET consumed_at = ?, updated_at = ? "
            "WHERE id = ? AND consumed_at IS NULL",
            (int(consumed_at), int(consumed_at), int(command_id)),
        )
        return cursor.rowcount == 1

    # ------------------------------------------------------------------
    # The two writes `core/` makes — primitives only
    #
    # Invariant 0: `core/` imports nothing from the rest of the package. That is what
    # keeps the lead's shape and B's implementation apart, and it means the orchestrator
    # cannot construct a `RunRow` to hand to `write_run`. The command reader gets away
    # with duck-typing today only because it exclusively *reads* attributes off rows this
    # client hands it; a write is a different problem, because a write needs a
    # constructor.
    #
    # So these two take `str` and `int` and nothing else. No model, no enum, no import.
    # `tests/clients/store/test_core_entry_points.py` proves it by running the whole path
    # in a fresh interpreter that imports only `StoreClient`.
    # ------------------------------------------------------------------

    def start_run(
        self,
        run_id: str,
        *,
        mode: str,
        started_at: int,
        acsoe_version: str | None = None,
        config_digest: str | None = None,
    ) -> None:
        """Record one daemon process, at startup, before the first tick.

        **Refuses a duplicate `run_id` rather than upserting.** `write_run` upserts
        because the orchestrator legitimately writes that row more than once — stamping
        `ended_at` at shutdown, say. Starting a run is not that: `run_id` is minted once
        per process, so a second `start_run` with the same id is either a restart that
        cannot have happened or a bug, and an upsert would silently rewrite `started_at`
        and hide it. The console decides the current run from the newest `runs` row, so a
        rewritten `started_at` reorders the two rows it compares.

        **It does not write `system_mode` or `system_mode_at`, and the column list here
        is why.** Adding those columns to `runs` in spec 31 silently made `write_run` a
        writer of the system mode, so a shutdown rewrite from a startup-built `RunRow`
        would have reset a frozen daemon's persisted mode to NULL. A new entry point is
        exactly where that trap gets walked back into, so this one names its columns
        explicitly rather than dumping a payload. :meth:`set_system_mode` remains the
        only writer of both.

        Raises :class:`StoreError` on a duplicate `run_id` or an unrecognised `mode`. A
        bad mode is a defect rather than a missing row: writing nothing for a typo would
        leave the console reading a run that does not exist, silently and forever.
        """
        try:
            recognised = RunMode(mode)
        except ValueError as exc:
            legal = ", ".join(sorted(member.value for member in RunMode))
            raise StoreError(f"unknown run mode {mode!r}; expected one of {legal}") from exc

        try:
            self.connection.execute(
                "INSERT INTO runs "
                "(run_id, mode, started_at, acsoe_version, config_digest, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    recognised.value,
                    int(started_at),
                    acsoe_version,
                    config_digest,
                    int(started_at),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise StoreError(
                f"run {run_id!r} already exists. `run_id` is minted once per process, so "
                "starting it twice is a defect rather than a restart; use write_run to "
                "amend an existing row."
            ) from exc

    def set_system_mode(self, run_id: str, mode: SystemMode | str, *, at: int) -> bool:
        """Record the mode this run is actually in. Returns False if the run is unknown.

        **Written for the console to read, never for the daemon to resume from.** There
        is deliberately no method that reads this back into `state`: mode is still
        reached only through an `activate` command, so a crashed daemon comes back idle.

        The caller is the command reader in `core/`, which already owns
        `state["system"]["mode"]`. It is the single writer, and it calls this after the
        transition rather than before, so a mode that was never actually entered is
        never persisted.

        `updated_at` moves with the mode. `runs` is in :data:`WATERMARK_TABLES`, so
        without that bump the console would not repoll and the status band it feeds
        would sit stale on the previous reading — the exact failure spec 31 exists to
        end.

        A `False` return is a missing `runs` row, which is a defect or a race and not a
        mode. It is returned rather than raised because the command reader must not
        abort a `freeze` it has already applied to `state` over a bookkeeping write;
        the caller logs it.

        **`mode` may be a plain `str`, and that is a guarantee rather than an accident.**
        `SystemMode` is a `StrEnum`, so `SystemMode("running")` has always worked — but
        "it happens to work" is not something that should be load-bearing under the
        status band, and the caller is `core/`, which may not import the enum at all. The
        coercion is explicit and `test_core_entry_points.py` pins it.

        An unrecognised mode **raises**, unlike an unknown run. The two failures are not
        alike: a missing row is a race the caller should log and continue past, while a
        misspelled mode is a defect, and returning `False` for it would leave the console
        reading a stale mode with nothing anywhere saying why.
        """
        try:
            recognised = SystemMode(mode)
        except ValueError as exc:
            legal = ", ".join(sorted(member.value for member in SystemMode))
            raise StoreError(
                f"unknown system mode {mode!r}; expected one of {legal}"
            ) from exc

        cursor = self.connection.execute(
            "UPDATE runs SET system_mode = ?, system_mode_at = ?, updated_at = ? "
            "WHERE run_id = ?",
            (recognised.value, int(at), int(at), run_id),
        )
        return cursor.rowcount == 1

    def system_mode(self, run_id: str) -> SystemModeRow | None:
        """The persisted mode for one run, scoped by `run_id` so no previous run leaks.

        `None` means there is no such run. A row with `mode is None` means the run
        exists and no daemon has written a mode for it yet. Both render as an idle
        reading, but only the second is ordinary, and a reader that cannot tell them
        apart cannot log the first.
        """
        row = self.connection.execute(
            "SELECT run_id, system_mode, system_mode_at FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return SystemModeRow(
            run_id=str(row["run_id"]),
            mode=row["system_mode"],
            at=row["system_mode_at"],
        )

    # ------------------------------------------------------------------
    # Writes — engine 19 `memory` is the single writer of relational rows
    # ------------------------------------------------------------------

    def write_run(self, row: RunRow) -> None:
        """Insert or update one run row. **Does not write the system mode.**

        `system_mode` and `system_mode_at` are excluded so that :meth:`set_system_mode`
        is their only writer. The orchestrator writes this row at startup, when no mode
        has been decided, and stamps `ended_at` through it again at shutdown; if those
        two columns were in the payload, the shutdown write would carry whatever
        `system_mode` the caller's stale `RunRow` happened to hold and silently
        overwrite the real one. Excluded from the INSERT they default to NULL, and
        excluded from the `DO UPDATE` set they are left exactly as they were.
        """
        self._upsert(
            "runs",
            row.model_dump(exclude={"id", "system_mode", "system_mode_at"}),
            key=("run_id",),
        )

    def write_block_record(self, row: BlockRecordRow) -> int:
        """Append one guard blocker for one tick.

        Raises `sqlite3.IntegrityError` on a second `is_primary` row for the same
        `(run_id, cycle_id)`. That is the database refusing to let two engines both
        claim to have gated the opportunity chain, and it is not to be caught and
        smoothed over.
        """
        return self._insert("block_records", row.model_dump())

    def write_equity_snapshot(self, row: EquitySnapshotRow) -> int:
        return self._insert("equity_snapshots", row.model_dump())

    def write_position(self, row: PositionRow) -> None:
        self._upsert("positions", row.model_dump(), key=("position_id",))

    def write_order(self, row: OrderRow) -> None:
        self._upsert("orders", row.model_dump(), key=("userref",))

    def write_trade(self, row: TradeRow) -> None:
        self._upsert("trades", row.model_dump(), key=("trade_id",))

    def write_rejection(self, row: RejectionRow) -> int:
        return self._insert("rejections", row.model_dump())

    def write_leaderboard_entry(self, row: LeaderboardRow) -> int:
        return self._insert("leaderboard", row.model_dump())

    # ------------------------------------------------------------------
    # Reads the console and the trading engines need
    # ------------------------------------------------------------------

    def open_positions(self) -> tuple[PositionRow, ...]:
        rows = self.connection.execute(
            "SELECT * FROM positions WHERE status = ? ORDER BY opened_at ASC, position_id ASC",
            (PositionStatus.OPEN.value,),
        ).fetchall()
        return tuple(PositionRow(**_row_to_dict(row)) for row in rows)

    def position(self, position_id: str) -> PositionRow | None:
        row = self.connection.execute(
            "SELECT * FROM positions WHERE position_id = ?", (position_id,)
        ).fetchone()
        return None if row is None else PositionRow(**_row_to_dict(row))

    def resting_orders(self, *, intent: OrderIntent | None = None) -> tuple[OrderRow, ...]:
        if intent is None:
            rows = self.connection.execute(
                "SELECT * FROM orders WHERE status = ? ORDER BY placed_at ASC, userref ASC",
                (OrderStatus.RESTING.value,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM orders WHERE status = ? AND intent = ? "
                "ORDER BY placed_at ASC, userref ASC",
                (OrderStatus.RESTING.value, intent.value),
            ).fetchall()
        return tuple(OrderRow(**_row_to_dict(row)) for row in rows)

    def order_by_userref(self, userref: int) -> OrderRow | None:
        """The invariant 8 idempotency lookup: never place an order without this."""
        row = self.connection.execute(
            "SELECT * FROM orders WHERE userref = ?", (int(userref),)
        ).fetchone()
        return None if row is None else OrderRow(**_row_to_dict(row))

    def recent_rejections(self, limit: int) -> tuple[RejectionRow, ...]:
        rows = self.connection.execute(
            "SELECT * FROM rejections ORDER BY ts DESC, id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return tuple(RejectionRow(**_row_to_dict(row)) for row in rows)

    def equity_series(
        self, *, start_ts: int | None = None, end_ts: int | None = None
    ) -> tuple[EquitySnapshotRow, ...]:
        """The equity curve, oldest first. Phase 7 attribution reads the whole thing,
        cash periods included."""
        clauses: list[str] = []
        params: list[Any] = []
        if start_ts is not None:
            clauses.append("ts >= ?")
            params.append(int(start_ts))
        if end_ts is not None:
            clauses.append("ts <= ?")
            params.append(int(end_ts))
        where = f"WHERE {' AND '.join(clauses)} " if clauses else ""
        rows = self.connection.execute(
            f"SELECT * FROM equity_snapshots {where}ORDER BY ts ASC, id ASC",
            params,
        ).fetchall()
        return tuple(EquitySnapshotRow(**_row_to_dict(row)) for row in rows)

    def latest_runs(self, limit: int = 2) -> tuple[RunRow, ...]:
        """Most recent runs first.

        The console detects a silent restart by comparing the current `run_id` against
        the previous row's — the comparison is made here, in SQLite, because the console
        is a separate process with no memory across its own restarts.
        """
        rows = self.connection.execute(
            "SELECT * FROM runs ORDER BY started_at DESC, id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return tuple(RunRow(**_row_to_dict(row)) for row in rows)

    def leaderboard(self, limit: int = 50) -> tuple[LeaderboardRow, ...]:
        rows = self.connection.execute(
            "SELECT * FROM leaderboard ORDER BY trained_at DESC, id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return tuple(LeaderboardRow(**_row_to_dict(row)) for row in rows)
