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
from acsoe.console.format import format_age, format_money, format_signed_pct
from acsoe.console.views import (
    IDLE,
    IDLE_RESTARTED,
    FeedRowView,
    HistoryRowView,
    LeaderboardEntryView,
    PositionView,
    Staleness,
    StatusBand,
)
from acsoe.platform.clock import Clock

__all__ = [
    "DEFAULT_FEED_LIMIT",
    "DEFAULT_HISTORY_LIMIT",
    "DEFAULT_LEADERBOARD_LIMIT",
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
        """The band, including the restart comparison.

        ``mode`` is paper, live or replay and comes from the injected `Config`;
        the State field is a different thing entirely and is derived here.
        """
        runs = self._store.latest_runs(2)
        current = runs[0] if runs else None
        previous = runs[1] if len(runs) > 1 else None
        restarted = current is not None and previous is not None and previous.run_id != current.run_id

        equity = self._store.latest_equity_snapshot()
        staleness = None if equity is None else self.staleness(equity.ts)

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
            staleness=staleness,
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
            opened_at=row.opened_at,
            timeout_at=row.timeout_at,
            staleness=self.staleness(row.updated_at, now=now),
        )

    # -- cycle feed -----------------------------------------------------

    def feed(self, limit: int | None = None) -> tuple[FeedRowView, ...]:
        """The cycle feed, newest first: refused candidates and blocked ticks.

        A blocked tick that also had a candidate produces one row in each source
        and therefore two rows here, joined by ``(run_id, cycle_id)``. That is the
        truth of what happened on that tick and not a duplicate: the guard blocked
        and a candidate was refused.
        """
        count = self._feed_limit if limit is None else int(limit)
        rows: list[FeedRowView] = [
            _rejection_feed_row(row) for row in self._store.recent_rejections(count)
        ]
        blocks = self._store.block_records_in_window(start_ts=_TS_MIN, end_ts=_TS_MAX)
        rows.extend(_block_feed_row(row) for row in blocks if row.is_primary)
        rows.sort(key=lambda row: (row.ts, row.cycle_id), reverse=True)
        return tuple(rows[:count])

    # -- history --------------------------------------------------------

    def history(self, limit: int | None = None) -> tuple[HistoryRowView, ...]:
        """Closed trades and past rejections, newest first."""
        count = self._history_limit if limit is None else int(limit)
        rows: list[HistoryRowView] = [
            _trade_history_row(row) for row in self._store.recent_closed_trades(count)
        ]
        rows.extend(_rejection_history_row(row) for row in self._store.recent_rejections(count))
        rows.sort(key=lambda row: row.ts, reverse=True)
        return tuple(rows[:count])

    # -- research -------------------------------------------------------

    def leaderboard(self, limit: int | None = None) -> tuple[LeaderboardEntryView, ...]:
        count = self._leaderboard_limit if limit is None else int(limit)
        return tuple(_leaderboard_view(row) for row in self._store.leaderboard(count))


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
    return FeedRowView(
        kind="rejection",
        ts=row.ts,
        run_id=row.run_id,
        cycle_id=row.cycle_id,
        pair=row.pair,
        outcome=_REJECTED_OUTCOME,
        reason=row.reason,
    )


def _block_feed_row(row: BlockRecordRow) -> FeedRowView:
    """A blocked tick. ``pair`` is null because most blocked ticks had no candidate."""
    return FeedRowView(
        kind="block",
        ts=row.ts,
        run_id=row.run_id,
        cycle_id=row.cycle_id,
        pair=None,
        outcome=_BLOCK_OUTCOME,
        reason=row.block_reason,
    )


def _trade_history_row(row: TradeRow) -> HistoryRowView:
    return HistoryRowView(
        kind="trade",
        ts=row.closed_at,
        pair=row.pair,
        outcome=str(row.outcome.value),
        reason="",
        qty_text=format_money(row.qty),
        entry_price_text=format_money(row.entry_price),
        exit_price_text=format_money(row.exit_price),
        realised_pnl=row.realised_pnl,
        realised_pnl_text=format_money(row.realised_pnl),
        realised_pnl_pct_text=format_signed_pct(row.realised_pnl_pct),
        reporting_currency=row.reporting_currency,
    )


def _rejection_history_row(row: RejectionRow) -> HistoryRowView:
    return HistoryRowView(
        kind="rejection",
        ts=row.ts,
        pair=row.pair,
        outcome=_REJECTED_OUTCOME,
        reason=row.reason,
        qty_text="",
        entry_price_text="",
        exit_price_text="",
        realised_pnl=None,
        realised_pnl_text="",
        realised_pnl_pct_text=(
            "" if row.net_edge_pct is None else format_signed_pct(row.net_edge_pct)
        ),
        reporting_currency=None,
    )


def _leaderboard_view(row: LeaderboardRow) -> LeaderboardEntryView:
    return LeaderboardEntryView(
        model_id=row.model_id,
        model_version=row.model_version,
        trained_at=row.trained_at,
        fold=row.fold,
        n_trades=row.n_trades,
        win_rate=row.win_rate,
        sharpe=row.sharpe,
        deflated_sharpe=row.deflated_sharpe,
        brier=row.brier,
        net_pnl=row.net_pnl,
        net_pnl_text="" if row.net_pnl is None else format_money(row.net_pnl),
        reporting_currency=row.reporting_currency,
        promoted=row.promoted,
    )
