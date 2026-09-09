"""The only module in the console that touches the store.

Everything above this file renders view models; nothing above it sees a
``sqlite3.Row``, a table name or a `StoreClient`. Keeping that seam in one module
is what makes the two properties below structural rather than conventional.

**The connection is read-only.** Not "the console does not happen to write" — the
SQLite connection is opened through a ``file:...?mode=ro`` URI, so a write is
refused by the database engine rather than by an author's discipline. Spec 24
opens its own narrow read-write connection for the ``commands`` table alone, and
nothing else in the console has one. ``tests/console/test_reader.py`` proves this
by *attempting* a real ``INSERT`` and a real ``UPDATE`` and asserting SQLite
raises on each: a guard that has never been shown to fire is not a guard.

**Time comes from an injected clock.** The console is a separate process from the
daemon, so it does not have ``context.now`` — but the reason engines never read a
clock applies unchanged. Staleness computed from ``datetime.now()`` makes every
test of it a race that passes on a fast machine and fails on a slow one; with a
``FixedClock`` the boundary is exact and a test can sit one microsecond either
side of it.

Restart detection is made **server-side in SQLite**, per ``ui-context.md``: the
console has no memory across its own restarts, so it may never be derived from
anything this process or the browser remembers.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Final, Self

from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import (
    BlockRecordRow,
    LeaderboardRow,
    PositionRow,
    RejectionRow,
    TradeRow,
    to_micros,
)
from acsoe.console.format import (
    direction,
    format_age,
    format_clock_time,
    format_engine_name,
    format_metric,
    format_money,
    format_optional_pct,
    format_outcome,
    format_rate_pct,
    format_signed_pct,
    format_timestamp,
    operator_reason,
)
from acsoe.console.views import (
    IDLE,
    IDLE_RESTARTED,
    SHAP_PRODUCED_IN_PHASE,
    FeedRowView,
    FeedStage,
    FeedSummary,
    HistoryView,
    LeaderboardEntryView,
    PositionView,
    RejectionRowView,
    ResearchView,
    ShapPane,
    Staleness,
    StatusBand,
    TradeRowView,
)
from acsoe.platform.clock import Clock

__all__ = [
    "DEFAULT_FEED_LIMIT",
    "DEFAULT_HISTORY_LIMIT",
    "DEFAULT_LEADERBOARD_LIMIT",
    "SHAP_EMPTY_STATE",
    "ConsoleReader",
    "ReadOnlyStore",
    "open_readonly_connection",
]

#: How many rows each screen asks for. Display limits, not thresholds: they
#: govern how much of a list is drawn and nothing about trading, so they are
#: constants here rather than config keys. `console.port`,
#: `console.poll_interval_ms` and `console.stale_after_ms` are the console's three
#: keys and only the lead adds a fourth.
DEFAULT_FEED_LIMIT: Final = 60
DEFAULT_HISTORY_LIMIT: Final = 100
DEFAULT_LEADERBOARD_LIMIT: Final = 25

#: The whole `ts` range, for the reads that take an explicit window.
#:
#: The console is built against a **seeded** database whose timestamps have no
#: relationship to wall time, so a window anchored on the clock would render an
#: empty cycle feed against a perfectly good seed and look like a bug in the
#: screen. Ordering and limiting therefore happen here, on the rows that come
#: back, rather than in a `WHERE ts >=` the console cannot pick honestly.
_TS_MIN: Final = 0
_TS_MAX: Final = 9_223_372_036_854_775_807

_MICROS_PER_MILLI: Final = 1_000

_BLOCK_OUTCOME: Final = "Blocked"
_REJECTED_OUTCOME: Final = "Rejected"

#: Which engines' rejections prove a candidate reached the cost gate. `cost` is
#: engine 7 and the gate itself; nothing else in the seed's `rejected_by` values
#: implies it. Named here rather than inferred, so a new engine does not silently
#: change a count on the empty state.
_COST_STAGE_ENGINES: Final = frozenset({"cost"})

#: What a stage line says when nothing in the store records it.
_NOT_RECORDED: Final = "not recorded yet \N{EM DASH} the universe filter arrives in Phase 2"

#: The SHAP pane's whole content. Written once, here, so the API payload and the
#: page cannot disagree about what is missing or about which phase produces it.
SHAP_EMPTY_STATE: Final = (
    "Per-decision feature attribution arrives with the predictor in Phase "
    f"{SHAP_PRODUCED_IN_PHASE}. Nothing has been trained and nothing has been "
    "explained yet, so there is nothing here to show."
)


def _feed_order(row: FeedRowView) -> tuple[int, int]:
    """Sort key for the feed. ``ts`` first, always.

    ``cycle_id`` is only ever the tiebreak *within* one timestamp, never the
    primary key — it restarts at 1 with each process, so a cross-restart sequence
    ordered by it interleaves two runs.
    """
    return (row.ts, row.cycle_id)


def _feed_headline(rejections: int, blocked: int) -> str:
    """The one sentence at the top of the empty state.

    A statement of what happened, never "No results". ``ui-context.md``: a console
    that looks empty most of the time is not broken, it is telling the truth, and
    the design's job is to make stillness legible rather than make it look like a
    failure.
    """
    if rejections or blocked:
        return (
            f"{rejections} candidate(s) refused and {blocked} tick(s) blocked in this window."
        )
    return "No tick has been recorded yet. Nothing has been scanned, refused or blocked."


def open_readonly_connection(db_path: Path) -> sqlite3.Connection:
    """Open ``db_path`` read-only.

    ``Path.as_uri()`` rather than string formatting: it percent-encodes, so a
    database under a directory containing a ``#`` or a space produces a URI SQLite
    parses as one path instead of silently truncating at the fragment. The target
    OS is Windows and ``C:\\Users\\...`` is exactly the shape that breaks naive
    concatenation.

    There is deliberately **no fallback to a writable connection**. A reader that
    quietly reopened read-write when ``mode=ro`` failed would satisfy every test
    that checks the URI and none of the ones that matter.
    """
    resolved = Path(db_path).resolve()
    connection = sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


class ReadOnlyStore(StoreClient):
    """B's store client over a read-only connection.

    A subclass rather than a second implementation of the reads. Every query the
    console needs already exists on `StoreClient`, `clients/store/` is B's
    directory, and a parallel set of SELECTs in the console would be a second
    statement of the schema that drifts the first time a column is renamed.
    Overriding where the connection comes from is the smallest change that makes
    the console structurally incapable of writing.
    """

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = open_readonly_connection(self._db_path)
        return self._conn


class ConsoleReader:
    """Composes every screen out of the reads `StoreClient` already exposes."""

    def __init__(
        self,
        db_path: Path,
        *,
        clock: Clock,
        stale_after_ms: int,
        feed_limit: int = DEFAULT_FEED_LIMIT,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        leaderboard_limit: int = DEFAULT_LEADERBOARD_LIMIT,
    ) -> None:
        if stale_after_ms <= 0:
            raise ValueError("console.stale_after_ms must be positive")
        self._store = ReadOnlyStore(Path(db_path))
        self._clock = clock
        self._stale_after_ms = int(stale_after_ms)
        self._feed_limit = int(feed_limit)
        self._history_limit = int(history_limit)
        self._leaderboard_limit = int(leaderboard_limit)

    # -- lifecycle ------------------------------------------------------

    @property
    def db_path(self) -> Path:
        return self._store.db_path

    @property
    def store(self) -> ReadOnlyStore:
        """The read-only client, for the negative test that attempts a write."""
        return self._store

    @property
    def stale_after_ms(self) -> int:
        return self._stale_after_ms

    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- time -----------------------------------------------------------

    def now_micros(self) -> int:
        """The injected clock, in the store's own unit. The only time source here."""
        return to_micros(self._clock.now())

    def staleness(self, ts: int, *, now: int | None = None) -> Staleness:
        """How old ``ts`` is, judged in microseconds.

        Strictly greater than the threshold is stale, so a figure exactly at
        ``console.stale_after_ms`` is still fresh. The boundary has to be
        somewhere and this is the one a `FixedClock` test can sit either side of.
        """
        moment = self.now_micros() if now is None else now
        age_us = moment - int(ts)
        threshold_us = self._stale_after_ms * _MICROS_PER_MILLI
        return Staleness(
            age_us=age_us,
            stale_after_ms=self._stale_after_ms,
            is_stale=age_us > threshold_us,
            age_text=format_age(age_us // _MICROS_PER_MILLI),
        )

    # -- watermark ------------------------------------------------------

    def watermark(self) -> int:
        """The highest ``updated_at`` across every console-rendered table."""
        return self._store.watermark()

    # -- status band ----------------------------------------------------

    def status_band(self, *, mode: str) -> StatusBand:
        """The band, including the restart reading.

        ``mode`` is paper, live or replay and comes from the injected `Config`;
        the State field is a different thing entirely and is derived here.

        **The restart reading is a presence test, and the schema is why.**
        ``db/migrations/0001_initial.sql`` declares ``run_id TEXT NOT NULL
        UNIQUE``, so no database can ever hold two rows carrying the same
        ``run_id``: two rows always differ, and the only run without a predecessor
        is the first one ever. Asking whether the current and previous ``run_id``s
        *differ* describes a state the schema forbids and would make the negative
        half of the check impossible to build, so the question asked here is
        whether a previous ``runs`` row exists at all.

        The State field takes one of :data:`~acsoe.console.views.IDLE_READINGS`
        and nothing else this phase. See that constant for why ``running`` and
        ``frozen`` wait for Phase 2.
        """
        runs = self._store.latest_runs(2)
        current = runs[0] if runs else None
        previous = runs[1] if len(runs) > 1 else None
        restarted = previous is not None

        equity = self._store.latest_equity_snapshot()
        watermark = self._store.watermark()
        # A watermark of 0 is an empty database, not a figure written at the epoch.
        watermark_ts = watermark if watermark > 0 else None

        return StatusBand(
            mode=str(mode),
            state=IDLE_RESTARTED if restarted else IDLE,
            restarted=restarted,
            run_id=None if current is None else current.run_id,
            previous_run_id=None if previous is None else previous.run_id,
            balance=None if equity is None else equity.equity,
            balance_text="" if equity is None else format_money(equity.equity),
            currency=None if equity is None else equity.currency,
            open_position_count=self._store.count_open_positions(),
            resting_order_count=self._store.count_resting_orders(),
            equity_ts=None if equity is None else equity.ts,
            staleness=None if equity is None else self.staleness(equity.ts),
            watermark_ts=watermark_ts,
            data_staleness=None if watermark_ts is None else self.staleness(watermark_ts),
        )

    # -- open positions -------------------------------------------------

    def positions(self) -> tuple[PositionView, ...]:
        """The open-positions region. Empty when nothing is open, never a stub row."""
        now = self.now_micros()
        return tuple(self._position_view(row, now) for row in self._store.open_positions())

    def _position_view(self, row: PositionRow, now: int) -> PositionView:
        pnl_pct = _unrealised_pct(row)
        return PositionView(
            position_id=row.position_id,
            pair=row.pair,
            base=row.base,
            quote=row.quote,
            qty=row.qty,
            qty_text=format_money(row.qty),
            entry_price=row.entry_price,
            entry_price_text=format_money(row.entry_price),
            last_price=row.last_price,
            last_price_text="" if row.last_price is None else format_money(row.last_price),
            target_price=row.target_price,
            target_price_text=format_money(row.target_price),
            stop_price=row.stop_price,
            stop_price_text=format_money(row.stop_price),
            unrealised_pnl=row.unrealised_pnl,
            unrealised_pnl_text=(
                "" if row.unrealised_pnl is None else format_money(row.unrealised_pnl)
            ),
            unrealised_pnl_pct_text="" if pnl_pct is None else format_signed_pct(pnl_pct),
            direction=direction(row.unrealised_pnl),
            opened_at=row.opened_at,
            timeout_at=row.timeout_at,
            staleness=self.staleness(row.updated_at, now=now),
        )

    # -- cycle feed -----------------------------------------------------

    def feed(self, limit: int | None = None) -> tuple[FeedRowView, ...]:
        """The cycle feed, newest first: refused candidates and blocked ticks.

        Two orderings would be defensible and only one is correct. **Ordered by
        ``ts``, never by ``cycle_id``** — the counter is minted per tick *within a
        run* and restarts at 1 with the process, so ordering a cross-restart
        sequence by it silently interleaves two runs. B's Phase 0 seed
        deliberately reuses ``cycle_id`` values across two ``run_id``s, so the two
        orderings genuinely disagree there and a test can prove it.

        **One blocked tick renders one row**, no matter how many guards blocked on
        it: the guard chain records every blocker, so a tick where ``data_guard``
        and ``safety`` both blocked has two ``block_records`` rows and one thing
        happened. The row kept is the primary blocker — the one that set
        ``state["trading_blocked_by"]`` — falling back to the earliest row on the
        tick when the seed or a live run left none marked.

        A blocked tick that *also* had a candidate produces one row from each
        source, which is two rows here and is not a duplicate: the guard blocked
        and a candidate was refused, and folding them together would mean anyone
        counting refused trades was also counting feed outages.
        """
        count = self._feed_limit if limit is None else int(limit)
        rows: list[FeedRowView] = [
            _rejection_feed_row(row) for row in self._store.recent_rejections(count)
        ]
        rows.extend(_block_feed_row(row) for row in self._blocked_ticks())
        rows.sort(key=_feed_order, reverse=True)
        return tuple(rows[:count])

    def _blocked_ticks(self) -> list[BlockRecordRow]:
        """One `block_records` row per tick, keyed on ``(run_id, cycle_id)``."""
        chosen: dict[tuple[str, int], BlockRecordRow] = {}
        for row in self._store.block_records_in_window(start_ts=_TS_MIN, end_ts=_TS_MAX):
            tick = (row.run_id, row.cycle_id)
            held = chosen.get(tick)
            if held is None or (row.is_primary and not held.is_primary):
                chosen[tick] = row
        return list(chosen.values())

    def feed_summary(self) -> FeedSummary:
        """What the system did, for the state the console is in most of the time.

        Four stages, in the order ``ui-context.md`` writes them. Two of them have
        **no source in the store at all**: nothing records how many pairs were
        scanned on a tick or how many entered the tradable universe, because the
        universe filter is engine 4 and its counts are Phase 2. Those lines say so.
        They do not show a zero — a zero in that column would read as "no pair
        qualified", which is a result, when the truth is that nobody counted.
        """
        rejections = self._store.recent_rejections(self._feed_limit)
        blocked = self._blocked_ticks()
        reached_cost = sum(1 for row in rejections if row.rejected_by in _COST_STAGE_ENGINES)
        cleared = self._store.count_open_positions()
        stages = (
            FeedStage(label="Pairs scanned", count=None, detail=_NOT_RECORDED),
            FeedStage(label="Entered the tradable universe", count=None, detail=_NOT_RECORDED),
            FeedStage(
                label="Reached the cost gate",
                count=reached_cost,
                detail="candidates the cost engine judged in this window",
            ),
            FeedStage(
                label="Cleared it",
                count=cleared,
                detail="positions currently open",
            ),
        )
        return FeedSummary(
            stages=stages,
            rejection_count=len(rejections),
            blocked_tick_count=len(blocked),
            headline=_feed_headline(len(rejections), len(blocked)),
        )

    # -- history --------------------------------------------------------

    def history(self, limit: int | None = None) -> HistoryView:
        """Closed trades and past rejections, newest first, in two tables.

        Two tables rather than one interleaved list. A closed trade carries a
        quantity, an exit price and two fees; a refused candidate carries an
        expected move and a hurdle and never had a quantity at all. One table would
        have meant a row of blank cells for whichever kind each column did not
        belong to, which is the shape that makes an operator stop reading.
        """
        count = self._history_limit if limit is None else int(limit)
        return HistoryView(
            trades=tuple(
                _trade_history_row(row) for row in self._store.recent_closed_trades(count)
            ),
            rejections=tuple(
                _rejection_history_row(row) for row in self._store.recent_rejections(count)
            ),
        )

    # -- research -------------------------------------------------------

    def leaderboard(self, limit: int | None = None) -> tuple[LeaderboardEntryView, ...]:
        count = self._leaderboard_limit if limit is None else int(limit)
        return tuple(_leaderboard_view(row) for row in self._store.leaderboard(count))

    def research(self, limit: int | None = None) -> ResearchView:
        """The leaderboard, and the SHAP pane's honest absence.

        The SHAP pane is an **empty state and nothing else**, confirmed by the
        operator on 2026-09-09. No placeholder chart, no chart of zeros, no sample
        explanation: a figure that looks like attribution and is not is worse than
        no figure, and `ui-context.md` leaves the visualisation undesigned on
        purpose. Nothing here reads ``models/`` or any Parquet file — none exists.
        """
        return ResearchView(
            leaderboard=self.leaderboard(limit),
            shap=ShapPane(
                available=False,
                produced_in_phase=SHAP_PRODUCED_IN_PHASE,
                message=SHAP_EMPTY_STATE,
            ),
        )


# --------------------------------------------------------------------------- #
# Row to view
# --------------------------------------------------------------------------- #


def _unrealised_pct(row: PositionRow) -> Decimal | None:
    """Unrealised PnL as a ratio of the position's cost.

    `Decimal` throughout. The obvious shortcut - divide two floats and multiply by
    a hundred - is how a 0.3% move renders as 0.30000000000000004%.
    """
    if row.unrealised_pnl is None:
        return None
    cost = row.entry_price * row.qty
    if cost == 0:
        return None
    return row.unrealised_pnl / cost


def _rejection_feed_row(row: RejectionRow) -> FeedRowView:
    """One candidate refused. The reason is prose, never a code."""
    return FeedRowView(
        kind="rejection",
        ts=row.ts,
        time_text=format_clock_time(row.ts),
        run_id=row.run_id,
        cycle_id=row.cycle_id,
        engine=row.rejected_by,
        pair=row.pair,
        outcome=f"{_REJECTED_OUTCOME} by {format_engine_name(row.rejected_by)}",
        reason=operator_reason(row.reason_code, row.reason),
    )


def _block_feed_row(row: BlockRecordRow) -> FeedRowView:
    """A blocked tick. ``pair`` is null because most blocked ticks had no candidate.

    The outcome names the **blocker**, which is the whole information content of a
    block row: an operator looking at a still screen needs to know whether the feed
    went stale or the account breaker tripped.
    """
    return FeedRowView(
        kind="block",
        ts=row.ts,
        time_text=format_clock_time(row.ts),
        run_id=row.run_id,
        cycle_id=row.cycle_id,
        engine=row.blocked_by,
        pair=None,
        outcome=f"{_BLOCK_OUTCOME} by {format_engine_name(row.blocked_by)}",
        # `block_records` has no `reason_code` column - unlike `rejections`, the
        # reason is the only text the row carries. It is passed as both arguments
        # so that a row whose `block_reason` turns out to be a bare code still gets
        # a lookup in REASON_PROSE rather than going straight to the fallback.
        reason=operator_reason(row.block_reason, row.block_reason),
    )


def _trade_history_row(row: TradeRow) -> TradeRowView:
    return TradeRowView(
        pair=row.pair,
        opened_at=row.opened_at,
        opened_text=format_timestamp(row.opened_at),
        closed_at=row.closed_at,
        closed_text=format_timestamp(row.closed_at),
        outcome=format_outcome(str(row.outcome.value)),
        qty=row.qty,
        qty_text=format_money(row.qty),
        entry_price=row.entry_price,
        entry_price_text=format_money(row.entry_price),
        exit_price=row.exit_price,
        exit_price_text=format_money(row.exit_price),
        entry_fee=row.entry_fee,
        entry_fee_text=format_money(row.entry_fee),
        exit_fee=row.exit_fee,
        exit_fee_text=format_money(row.exit_fee),
        realised_pnl=row.realised_pnl,
        realised_pnl_text=format_money(row.realised_pnl),
        realised_pnl_pct=row.realised_pnl_pct,
        realised_pnl_pct_text=format_signed_pct(row.realised_pnl_pct),
        direction=direction(row.realised_pnl),
        reporting_currency=row.reporting_currency,
    )


def _rejection_history_row(row: RejectionRow) -> RejectionRowView:
    return RejectionRowView(
        ts=row.ts,
        time_text=format_timestamp(row.ts),
        run_id=row.run_id,
        cycle_id=row.cycle_id,
        pair=row.pair,
        rejected_by=row.rejected_by,
        rejected_by_text=format_engine_name(row.rejected_by),
        reason=operator_reason(row.reason_code, row.reason),
        expected_move_pct_text=format_optional_pct(row.expected_move_pct),
        friction_pct_text=format_optional_pct(row.friction_pct),
        net_edge_pct_text=format_optional_pct(row.net_edge_pct),
        hurdle_pct_text=format_optional_pct(row.hurdle_pct),
        net_edge_direction=direction(row.net_edge_pct),
    )


def _leaderboard_view(row: LeaderboardRow) -> LeaderboardEntryView:
    return LeaderboardEntryView(
        model_id=row.model_id,
        model_version=row.model_version,
        trained_at=row.trained_at,
        trained_at_text=format_timestamp(row.trained_at),
        fold=row.fold,
        n_trades=row.n_trades,
        win_rate=row.win_rate,
        win_rate_text=format_rate_pct(row.win_rate),
        sharpe=row.sharpe,
        sharpe_text=format_metric(row.sharpe),
        deflated_sharpe=row.deflated_sharpe,
        deflated_sharpe_text=format_metric(row.deflated_sharpe),
        brier=row.brier,
        brier_text=format_metric(row.brier),
        net_pnl=row.net_pnl,
        net_pnl_text="" if row.net_pnl is None else format_money(row.net_pnl),
        reporting_currency=row.reporting_currency,
        promoted=row.promoted,
    )
