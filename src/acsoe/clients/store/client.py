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
import os
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from decimal import Decimal
from enum import Enum
from pathlib import Path, PureWindowsPath
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


def _validated_run_id(run_id: str) -> str:
    """A training run id that is safe to use as one directory name, or a refusal.

    **Checked before any path is built**, which is the point rather than a nicety: a
    run id is a string that arrives from a config key, a CLI flag or a manifest, and
    `Path("models") / "../../etc"` is a perfectly well-formed path that reads and writes
    outside the artefact root. Joining first and validating the result afterwards is the
    version of this check that has been wrong in every system that has ever had it.

    Each refusal carries its own message, because `StoreError` has one type and several
    causes and a caller — or a test — cannot tell them apart from the type alone.

    A leading dot is legal: `.` and `..` are refused by name, but a run id may start with
    one, and inventing a rule against it would refuse ids the trainer is entitled to mint.
    """
    if run_id.strip() == "":
        raise StoreError("refusing an empty run id: an artefact directory needs a name")
    if run_id != run_id.strip():
        raise StoreError(
            f"refusing run id {run_id!r}: it has leading or trailing whitespace, which "
            "would make two ids that print identically name two directories"
        )
    if "\x00" in run_id:
        raise StoreError(f"refusing run id {run_id!r}: it contains a null byte")
    if run_id in {os.curdir, os.pardir}:
        raise StoreError(
            f"refusing run id {run_id!r}: it names a directory relative to the artefact "
            "root rather than a run inside it"
        )
    if "/" in run_id or "\\" in run_id:
        raise StoreError(
            f"refusing run id {run_id!r}: a run id is one directory name, not a path. "
            "A separator here would put an artefact outside the artefact root."
        )
    if PureWindowsPath(run_id).drive or PureWindowsPath(run_id).is_absolute():
        raise StoreError(
            f"refusing run id {run_id!r}: it is absolute or carries a drive, so joining "
            "it to the artefact root would discard the root entirely"
        )
    return run_id


class StoreClient:
    """SQLite and Parquet access for the whole system.

    Satisfies the `store` member of the `Clients` Protocol declared in `core/`.
    """

    def __init__(self, db_path: Path, *, models_dir: Path | None = None) -> None:
        self._db_path = Path(db_path)
        self._models_dir = None if models_dir is None else Path(models_dir)
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def models_dir(self) -> Path | None:
        """The artefact root, or `None` when this client was built without one.

        `None` is not an error at construction time and must not become one: a fresh
        clone has no `models/`, the console builds a store to render rows and never asks
        for an artefact, and the seed generator writes no model at all. The refusal
        belongs at the moment someone asks for a run directory, which is where it can
        name the run id nobody can serve.
        """
        return self._models_dir

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

    def peak_equity(self) -> Decimal | None:
        """The running maximum equity the store holds, or `None` on an empty series.

        Engine 19 `memory` needs this every tick and must not recompute it from `state`,
        which is rebuilt fresh each tick and therefore has no memory of a peak reached
        before the last restart. Reading it here costs one indexed row.

        **The peak is carried forward on the row, not aggregated over the column.** The
        obvious query, `SELECT MAX(peak_equity) FROM equity_snapshots`, is wrong and
        wrong silently: money is stored as an exact decimal *string*, so SQLite compares
        it lexicographically and decides `'9.50'` is larger than `'10000.00'`. That
        returns a plausible number, a too-small peak, and therefore a drawdown smaller
        than the real one — the circuit breaker sits quiet through exactly the loss it
        exists to stop. The comparison has to happen in `Decimal`, and the cheapest way
        to have it already done is the newest row's own `peak_equity`, which is the
        running maximum by construction and is the same value engine 17 `safety` reads
        through :meth:`latest_equity_snapshot`. Both readers therefore see one number.
        """
        snapshot = self.latest_equity_snapshot()
        return None if snapshot is None else snapshot.peak_equity

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

    def recent_block_records(self, limit: int) -> tuple[BlockRecordRow, ...]:
        """The most recent `limit` block record **rows**, newest first.

        **Ordered by `ts`, never by `cycle_id`.** `cycle_id` is minted per tick within a
        run and restarts at 1 with the process, so a `cycle_id` ordering over a
        cross-restart sequence puts the *old* run's high cycle numbers in front of the
        new run's low ones and reports a stale tick as the newest thing that happened.
        B's Phase 0 seed reuses `cycle_id` values across two `run_id`s deliberately, so
        the two orderings genuinely disagree there.

        **The limit is the caller's and there is no default.** This read replaces
        `block_records_in_window(start_ts=0, end_ts=<maxint>)`, which materialised a
        `BlockRecordRow` for every row in the table. That was harmless while the table
        held nothing but the Phase 0 seed and stops being harmless the moment engine 19
        `memory` starts writing a row per guard per tick. `idx_block_records_ts` serves
        the ordering, so the cost is the limit and not the table.

        **A row is a blocker, not a tick.** The guard chain never breaks early, so one
        tick can produce several rows and `limit` rows can be fewer than `limit` ticks.
        A caller that wants one row per tick wants :meth:`recent_blocked_ticks`, which
        never returns a tick it has only half of.
        """
        rows = self.connection.execute(
            "SELECT * FROM block_records ORDER BY ts DESC, id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return tuple(BlockRecordRow(**_row_to_dict(row)) for row in rows)

    def recent_blocked_ticks(self, limit: int) -> tuple[BlockRecordRow, ...]:
        """One row per blocked tick, newest tick first, at most `limit` ticks.

        What the console's cycle feed renders: a tick on which `data_guard` and `safety`
        both blocked is **one thing that happened**, not two. The row kept is the primary
        blocker — the one that gated the opportunity chain — falling back to the lowest
        `id` on the tick when nothing on it is marked primary, which is what a seeded
        fixture or a partially-written tick looks like.

        **Why this is not `recent_block_records` with a dictionary over it.** Truncating
        rows and *then* grouping can cut a tick in half: the oldest tick in the window
        keeps whichever of its rows survived the limit, and if the primary row was the
        one cut, the feed renders that tick as blocked by the wrong engine. Nothing
        raises and the row looks well-formed. This method picks whole ticks first and
        reads only their rows, so a tick is either absent or complete.

        **Bounded the same way, by `ts`.** The first statement is the newest `limit`
        ticks by `ts`; the second reads back only rows at or after the oldest of those
        timestamps. Engine 19 stamps every row it writes for a tick with the same
        `context.now`, which is what makes the second bound exact. Were a tick ever
        written across two timestamps it would appear as two entries in the first
        statement and this method would return fewer than `limit` ticks — it under-fills,
        it does not mis-attribute.
        """
        # The tie-break after `ts DESC` is `cycle_id` then `run_id`, the opposite order
        # from the outage walk below. Within one `ts` either is arbitrary and both are
        # deterministic, and the difference is deliberate: C's
        # `test_an_outage_counted_by_cycle_id_is_a_fail` proves the Phase 3 outage
        # criterion can fail by rewriting that walk's ORDER BY *by its literal text*, and
        # a second identical clause in this file makes the anchor ambiguous. Do not
        # "tidy" the two into one wording.
        wanted = self.connection.execute(
            """
            SELECT DISTINCT run_id, cycle_id, ts
            FROM block_records
            ORDER BY ts DESC, cycle_id DESC, run_id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        if not wanted:
            return ()

        ticks = {(str(row["run_id"]), int(row["cycle_id"])) for row in wanted}
        oldest_ts = min(int(row["ts"]) for row in wanted)
        rows = self.connection.execute(
            "SELECT * FROM block_records WHERE ts >= ? ORDER BY ts DESC, id ASC",
            (oldest_ts,),
        ).fetchall()

        chosen: dict[tuple[str, int], BlockRecordRow] = {}
        for raw in rows:
            tick = (str(raw["run_id"]), int(raw["cycle_id"]))
            if tick not in ticks:
                continue
            record = BlockRecordRow(**_row_to_dict(raw))
            held = chosen.get(tick)
            # Rows arrive ascending by `id` within a tick, so the first one seen is
            # already the lowest-id fallback; only a primary displaces it.
            if held is None or (record.is_primary and not held.is_primary):
                chosen[tick] = record
        return tuple(
            sorted(
                chosen.values(),
                key=lambda row: (row.ts, row.run_id, row.cycle_id),
                reverse=True,
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

    def filled_orders(self) -> tuple[OrderRow, ...]:
        """Every order that filled, oldest first. The **recorded half** of the paper
        broker's ledger, and the thing a restart rebuilds that ledger from.

        The ledger needs the fills themselves — the quantity, the average price and the
        fee on each — rather than a total, which is why this hands back rows.

        **It is not the whole ledger, and the docstring used to say it was.** Invariant 2,
        as the operator amended it on 2026-09-16 (spec 103): in paper mode the balance is
        `paper.starting_balances` adjusted by every fill **the broker has executed**,
        recorded or not. The two differ for exactly one tick — the broker decides a resting
        entry's fill when engine 21 asks for it, part-way through a tick, and engine 19
        records it at the end of that tick — so the broker adds the fills it holds and this
        store has not seen yet on top of these rows. A balance counting only *recorded*
        fills lagged the broker's own knowledge by a tick, counted the same cash twice on
        the fill tick, and froze the account on the next one.

        **The restart is the other half of that amendment, and it is what this read is
        for.** A restarted daemon holds no executed fills of its own, so the store is the
        whole ledger. A fill the broker executed and engine 19 never recorded — a process
        that died between the two — is absent from what this returns, and must be absent
        from the rebuilt positions too, so the two still agree.

        **Deliberately not a `SUM()`.** Money columns are TEXT with a `typeof` check, so
        SQLite would either compare and add them lexicographically or coerce them to
        floats, and `code-standards.md` forbids arithmetic on a money column in SQL for
        exactly that reason. The rows come back as exact `Decimal` through `OrderRow` and
        the addition happens in Python. It is the same defect `peak_equity` was written
        to avoid, in the one direction that silently changes a balance.

        `filled_qty > 0` is not filtered here: `OrderStatus.FILLED` with a zero quantity
        is a contradiction A's `OrderState` refuses at its own boundary, and filtering it
        away here would hide a row that should be looked at.

        Ordered by `placed_at` then `userref` so two callers see one order. Addition is
        commutative, so the order does not change the balance — it changes whether a
        difference between two runs is reproducible.
        """
        rows = self.connection.execute(
            "SELECT * FROM orders WHERE status = ? ORDER BY placed_at ASC, userref ASC",
            (OrderStatus.FILLED.value,),
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

    def leaderboard_entries(
        self, *, model_id: str, model_version: str, fold: str | None
    ) -> tuple[LeaderboardRow, ...]:
        """Every leaderboard row for one model version and one fold, oldest first.

        **The existence read engine 20 `tournament` needs, and the one thing spec 62's
        audit found missing.** Spec 74 requires engine 20 to be idempotent on
        `(model_id, model_version, fold)` and to report how many rows it wrote and how
        many it found. The only read that existed was :meth:`leaderboard`, which is the
        console's: newest 50 by `trained_at`. Deciding "have I written this fold already"
        from a truncating window is the rows-versus-ticks defect of spec 51 again — a
        walk-forward with more folds than the limit would silently start writing
        duplicates, and the duplicate looks exactly like a second training run.

        **It returns every match rather than the first**, because nothing stops there
        being two. There is no unique index on those three columns; adding one is a
        schema change and spec 62 forbids one this phase. So idempotency here is the
        caller's to enforce and this method's to make enforceable, and a reader that
        collapsed two rows into one would hide the very state that proves the convention
        was broken. Raised for the lead in `context/progress/b-store.md`.

        `fold IS ?` and never `fold = ?`. `fold` is nullable, SQL equality against NULL
        is NULL rather than true, and `fold = NULL` therefore matches nothing at all —
        so the aggregate row every model version has, the one with no fold, would look
        absent on every check and be rewritten on every run.
        """
        rows = self.connection.execute(
            "SELECT * FROM leaderboard WHERE model_id = ? AND model_version = ? "
            "AND fold IS ? ORDER BY id ASC",
            (str(model_id), str(model_version), fold),
        ).fetchall()
        return tuple(LeaderboardRow(**_row_to_dict(row)) for row in rows)

    def all_leaderboard_rows(self, *, model_id: str) -> tuple[LeaderboardRow, ...]:
        """**Every** row for one model, oldest first. No limit, and that is the point.

        The enumeration engine 14 `adaptive_router` weights from, added on the lead's
        ruling of 2026-09-16 after C-models found there was no read it could use.

        Neither of the two that existed can do this job, and the reasons are different:

        - :meth:`leaderboard_entries` takes `model_version` as an **argument**. It is an
          existence check — "have I written this fold already" — so it cannot enumerate
          the versions engine 14 has to compare.
        - :meth:`leaderboard` is the **console's** read and truncates to the newest 50
          by `trained_at`. My own docstring above is the argument against reusing it:
          deciding anything from a truncating window is the rows-versus-ticks defect of
          spec 51 again. C worked out the consequence precisely, and it is worse here
          than for the existence check. A model version outside the newest fifty gets
          **no weight because nobody looked**, not zero weight for having no edge, and
          the two are indistinguishable downstream — **the weights would still sum to
          one, over the wrong set.** A real run has 405 folds.

        Scoped by `model_id` rather than returning the whole table, because that is what
        makes "no limit" safe: one model's folds are bounded by its walk-forward, where
        the table as a whole is bounded by nothing. There is no `LIMIT` to get wrong and
        no window to fall out of.

        `ORDER BY id ASC` is insertion order and is deliberately not `trained_at`:
        `trained_at` is not unique across folds written in one run, so ordering on it
        alone leaves ties SQLite may break differently between two reads of a database
        nothing wrote to. Every money and metric column comes back typed through
        `LeaderboardRow`, so a caller never sees a raw row.

        Empty is a real answer and is not an error: a fresh database has trained
        nothing. Engine 14 refuses on it with `leaderboard_empty` rather than weighting
        an empty set.
        """
        rows = self.connection.execute(
            "SELECT * FROM leaderboard WHERE model_id = ? ORDER BY id ASC",
            (str(model_id),),
        ).fetchall()
        return tuple(LeaderboardRow(**_row_to_dict(row)) for row in rows)

    # ------------------------------------------------------------------
    # Trained artefacts — `models/<run_id>/`
    #
    # Contract rule 4: an engine never touches the filesystem directly, so engines 8,
    # 13 and 15 reach a trained artefact through here and never by building a path.
    # This client hands back a **path and nothing else**. It does not open the
    # manifest, does not verify a hash and does not know what a scaler is: the layout
    # is `modelling/artefacts.py`'s (C's), and a store that also parsed artefacts would
    # be two owners in one file.
    #
    # There is deliberately no listing, no wildcard and no "latest". A run id is
    # configured — `models.prediction_run_id` and its two siblings — and an engine that
    # could ask for "the newest artefact" would silently change model between two ticks
    # of the same daemon, which is the opposite of a result anyone can reproduce.
    # ------------------------------------------------------------------

    def _artefact_root(self, run_id: str, *, create: bool) -> Path:
        """The configured artefact root, or a refusal naming the run nobody can serve.

        **`create` is the whole difference between the two public methods**, and it is a
        parameter rather than two copies of this because the `models_dir is None` refusal
        below is common to both and must stay common: no configured root is a
        misconfiguration in either direction, and a writer that invented one would put
        artefacts wherever the process happened to be running.

        A *reader* refuses a missing root. A *writer* creates it. Ruled by the lead on
        2026-09-13 after B raised it: `platform/paths.py` creates `models/` at startup
        beside `data/` and `logs/`, but C's trainer runs as
        `python -m acsoe.research.training`, which never goes through A's startup path —
        so a writer that demanded the root already exist would refuse the first training
        run on every fresh clone, reporting a misconfiguration where there was only an
        empty tree.

        The asymmetry is deliberate and the two must not drift into agreement. For a
        reader, a missing root and a missing run are different facts with the same
        remedy only by coincidence: on a fresh clone the root is absent because nothing
        has trained, and creating it to then report the run missing inside it would turn
        a true message into a less true one and leave an empty directory behind.
        """
        root = self._models_dir
        if root is None:
            raise StoreError(
                f"cannot reach model run {run_id!r}: this store was built with no "
                "models_dir, so there is no artefact root to look in"
            )
        if root.is_dir():
            return root
        if not create:
            raise StoreError(
                f"cannot reach model run {run_id!r}: the artefact root {root} does not "
                "exist. A fresh clone has no models/ until something trains."
            )
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StoreError(
                f"could not create the artefact root {root} for model run {run_id!r}: {exc}"
            ) from exc
        return root

    def model_run_dir(self, run_id: str) -> Path:
        """The directory holding one training run's artefacts. Read-only access.

        Raises :class:`StoreError` — naming the run id and the root — when the run id is
        unusable, when no artefact root was configured, when the root does not exist, or
        when that run has never been trained. The last is the ordinary case on a fresh
        clone and is what makes engines 8, 13 and 15 block rather than predict, per
        spec 59 decision 9.
        """
        name = _validated_run_id(run_id)
        root = self._artefact_root(run_id, create=False)
        path = root / name
        if not path.is_dir():
            raise StoreError(
                f"model run {run_id!r} is not in the artefact root {root}: no directory "
                f"{path}. Train it, or point models.*_run_id at a run that exists."
            )
        return path

    def new_model_run_dir(self, run_id: str) -> Path:
        """Create the directory for a training run that has not been written yet.

        **An existing directory is refused, never reused and never overwritten.**
        `code-standards.md`: every trained artefact is written to `models/<run_id>/` and
        never overwritten, because a model whose files came from two runs cannot be
        reproduced from its config plus its data and is therefore not a result. The
        refusal is the whole safety property of this method; a caller that wants to
        retrain mints a new run id.

        The refusal is `mkdir(exist_ok=False)` itself rather than a prior `exists()`
        check, so it is atomic: two trainers racing for one run id cannot both be told
        the directory is free. That is the one property here worth protecting, and a
        `path.exists()` guard in front of it would quietly throw it away.

        **A missing artefact root is created; a missing run directory is not reused.**
        Those are the two halves of this method and they pull in opposite directions on
        purpose. The lead ruled on 2026-09-13 that the root is created, because C's
        trainer runs as `python -m acsoe.research.training` and never touches A's startup
        path, so demanding the root already exist would refuse the first training run on
        every fresh clone. `parents=False` stays on this `mkdir` even so: the root is
        created deliberately, by :meth:`_artefact_root`, and letting this call create it
        as a side effect of `parents=True` would also silently create any *other* missing
        ancestor — which is only reachable through a run id shaped like a path, and
        `_validated_run_id` refuses those precisely so this line never has to.
        """
        name = _validated_run_id(run_id)
        root = self._artefact_root(run_id, create=True)
        path = root / name
        try:
            path.mkdir(parents=False, exist_ok=False)
        except FileExistsError as exc:
            raise StoreError(
                f"refusing to write model run {run_id!r}: {path} already exists. A "
                "trained artefact is never overwritten; mint a new run id."
            ) from exc
        except OSError as exc:
            raise StoreError(
                f"could not create the directory for model run {run_id!r} under {root}: {exc}"
            ) from exc
        return path
