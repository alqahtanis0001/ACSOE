"""Spec 13 - the seeded database.

Phase 3 tests engine 17 `safety` against this database, because every one of `safety`'s
six inputs is written by engine 19 `memory`, which is Phase 4. That makes the seed a
deliverable with a gate behind it rather than convenience data, and it is why the
assertions here are about *thresholds* rather than about counts.

Two properties are load-bearing and easy to break by tidying:

**Every fixture is a multiple of the injected threshold, never a constant.** The
operator's limits in `config/default.yaml` are provisional and will change. A fixture
pinned to a literal stops overshooting the moment a limit is raised, and Phase 3 then
fails for a reason that has nothing to do with the code under test. This exact defect
happened once: the seed's own default `max_errors_in_window` was 10 while the operator
set 20, so `seed_fixtures_present` failed on 13 ERROR rows against a limit of 20.
:func:`test_the_seed_overshoots_the_operators_own_configured_limits` is the regression
guard, and it reads the real config so it goes red the next time the two drift apart.

**The two seeded runs reuse `cycle_id` values.** If they did not overlap, ordering by
`cycle_id` would give the same answer as ordering by `ts` and the criterion that exists
to prove the difference would prove nothing. Do not tidy the run IDs apart.

Money is asserted with exact `Decimal` comparisons. `pytest.approx` is banned by
`code-standards.md` for anything involving money.
"""

from __future__ import annotations

import hashlib
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.store.client import DATA_GUARD_ENGINE, StoreClient
from acsoe.clients.store.contracts import BlockStatus, RunMode
from acsoe.clients.store.seed import (
    DEFAULT_SEED,
    SeedFixtures,
    SeedThresholds,
    seed_database,
)

# --------------------------------------------------------------------------- #
# Threshold sets
# --------------------------------------------------------------------------- #

#: Deliberately spread across two orders of magnitude. Each is injected the way
#: `scripts/verify.py` injects the operator's real numbers, and every fixture must
#: overshoot every one of them.
THRESHOLD_CASES: list[SeedThresholds] = [
    SeedThresholds(
        max_consecutive_data_blocks=1,
        max_drawdown_pct=Decimal("0.01"),
        max_consecutive_losses=1,
        error_rate_window_s=3600,
        max_errors_in_window=1,
    ),
    SeedThresholds(
        max_consecutive_data_blocks=15,
        max_drawdown_pct=Decimal("0.10"),
        max_consecutive_losses=5,
        error_rate_window_s=3600,
        max_errors_in_window=20,
    ),
    SeedThresholds(
        max_consecutive_data_blocks=30,
        max_drawdown_pct=Decimal("0.25"),
        max_consecutive_losses=12,
        error_rate_window_s=3600,
        max_errors_in_window=60,
    ),
    SeedThresholds(
        max_consecutive_data_blocks=60,
        max_drawdown_pct=Decimal("0.50"),
        max_consecutive_losses=40,
        error_rate_window_s=1800,
        max_errors_in_window=80,
    ),
]

THRESHOLD_IDS = [
    f"blocks{t.max_consecutive_data_blocks}-dd{t.max_drawdown_pct}"
    f"-loss{t.max_consecutive_losses}-err{t.max_errors_in_window}"
    for t in THRESHOLD_CASES
]


@pytest.fixture(params=THRESHOLD_CASES, ids=THRESHOLD_IDS)
def thresholds(request: pytest.FixtureRequest) -> SeedThresholds:
    value: SeedThresholds = request.param
    return value


@pytest.fixture
def seeded(tmp_path: Path, thresholds: SeedThresholds) -> SeedFixtures:
    """A seeded database under `tmp_path`. Never under `data/` - spec 13 forbids it."""
    return seed_database(tmp_path / "acsoe.sqlite", thresholds=thresholds)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------------- #
# The six fixtures Phase 3 reads
# --------------------------------------------------------------------------- #


def test_the_outage_run_is_past_the_block_limit_and_spans_two_runs(
    seeded: SeedFixtures, thresholds: SeedThresholds
) -> None:
    outage = seeded.consecutive_data_block_run

    assert outage.length > thresholds.max_consecutive_data_blocks
    assert outage.length == thresholds.outage_run_length
    assert len(outage.run_ids) == 2, "the restart is what makes the ts ordering matter"
    assert outage.first_ts < outage.last_ts


def test_at_least_one_position_is_open(seeded: SeedFixtures) -> None:
    assert seeded.open_positions


def test_at_least_one_entry_order_is_resting(seeded: SeedFixtures) -> None:
    assert seeded.resting_entry_orders


def test_the_latest_equity_row_is_in_drawdown_past_the_limit(
    seeded: SeedFixtures, thresholds: SeedThresholds
) -> None:
    """`safety` reads only the *latest* equity row.

    A drawdown parked in the middle of the series would satisfy a literal reading of
    "a series containing a drawdown" and still leave the breaker with nothing to trip
    on, so the trough is asserted to be the newest row.
    """
    drawdown = seeded.drawdown

    assert drawdown.drawdown_pct > thresholds.max_drawdown_pct
    assert isinstance(drawdown.equity, Decimal)
    assert isinstance(drawdown.peak_equity, Decimal)
    assert drawdown.equity < drawdown.peak_equity
    assert (drawdown.peak_equity - drawdown.equity) / drawdown.peak_equity == (
        drawdown.drawdown_pct
    )

    with _connect(seeded.db_path) as conn:
        newest = conn.execute(
            "SELECT ts, equity, peak_equity FROM equity_snapshots ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    assert int(newest["ts"]) == drawdown.trough_ts
    assert Decimal(str(newest["equity"])) == drawdown.equity
    assert Decimal(str(newest["peak_equity"])) == drawdown.peak_equity


def test_the_trailing_losing_streak_is_past_the_limit(
    seeded: SeedFixtures, thresholds: SeedThresholds
) -> None:
    streak = seeded.losing_streak

    assert streak.length > thresholds.max_consecutive_losses
    assert streak.length == thresholds.losing_streak_length
    assert all(isinstance(pnl, Decimal) for pnl in streak.realised_pnl)
    assert all(pnl < 0 for pnl in streak.realised_pnl)
    assert len(set(streak.trade_ids)) == streak.length


def test_error_rows_inside_the_window_are_past_the_error_limit(
    seeded: SeedFixtures, thresholds: SeedThresholds
) -> None:
    errors = seeded.error_blocks

    assert errors.count > thresholds.max_errors_in_window
    assert errors.count == thresholds.error_row_count
    assert (
        errors.window_end_ts - errors.window_start_ts
        == thresholds.error_rate_window_s * 1_000_000
    )

    with _connect(seeded.db_path) as conn:
        outside = conn.execute(
            "SELECT COUNT(*) AS n FROM block_records WHERE status = ? AND ts < ?",
            (BlockStatus.ERROR.value, errors.window_start_ts),
        ).fetchone()
    assert int(outside["n"]) == 0, "an ERROR row outside the window inflates nothing"


def test_an_unreachable_error_limit_is_refused_loudly(tmp_path: Path) -> None:
    """There is a ceiling, and it is arithmetic rather than a seed shortcoming.

    `block_records` carries one row per blocker per tick, so the most ERROR rows that
    can exist inside the window is ticks x engines - for anything that writes them,
    including the live engine 19. A `max_errors_in_window` above that is a breaker that
    can never fire, and the seed says so instead of quietly under-shooting and letting
    Phase 3 blame the engine.
    """
    unreachable = SeedThresholds(
        max_consecutive_data_blocks=15,
        max_drawdown_pct=Decimal("0.10"),
        max_consecutive_losses=5,
        error_rate_window_s=600,
        max_errors_in_window=120,
    )

    with pytest.raises(ValueError, match=r"ceiling is \d+") as caught:
        seed_database(tmp_path / "acsoe.sqlite", thresholds=unreachable)

    message = str(caught.value)
    assert "10-tick" in message
    assert "max_errors_in_window=120" in message
    assert "never fire" in message


def test_the_seed_reports_no_warnings_about_its_own_fixtures(seeded: SeedFixtures) -> None:
    """The seed re-reads what it wrote and complains if a fixture fell short.

    That self-check is derived from the rows, not from the loop counters that wrote
    them, so it and the assertions above disagree exactly when there is a bug.
    """
    assert seeded.warnings == ()


def test_trades_rejections_and_leaderboard_rows_are_all_present(seeded: SeedFixtures) -> None:
    """The console's cycle feed, history and leaderboard each need something honest."""
    assert seeded.trade_count > 0
    assert seeded.rejection_count > 0
    assert seeded.leaderboard_count > 0


# --------------------------------------------------------------------------- #
# The operator's own limits - the regression this file exists for
# --------------------------------------------------------------------------- #


def test_the_seed_overshoots_the_operators_own_configured_limits(
    tmp_path: Path, paper_config: Any
) -> None:
    """Against the live `config/default.yaml`, not against a case pinned in this file.

    `scripts/verify.py` injects exactly these five values into `SeedThresholds` before
    asserting `seed_fixtures_present`. Reproducing that here means the criterion cannot
    be the first thing to notice a drift between the operator's numbers and the seed.
    """
    configured = SeedThresholds(
        max_consecutive_data_blocks=int(paper_config.get("safety.max_consecutive_data_blocks")),
        max_drawdown_pct=Decimal(str(paper_config.get("safety.max_drawdown_pct"))),
        max_consecutive_losses=int(paper_config.get("safety.max_consecutive_losses")),
        error_rate_window_s=int(paper_config.get("safety.error_rate_window_s")),
        max_errors_in_window=int(paper_config.get("safety.max_errors_in_window")),
    )

    fixtures = seed_database(tmp_path / "acsoe.sqlite", thresholds=configured)

    assert fixtures.warnings == ()
    assert fixtures.consecutive_data_block_run.length > configured.max_consecutive_data_blocks
    assert fixtures.drawdown.drawdown_pct > configured.max_drawdown_pct
    assert fixtures.losing_streak.length > configured.max_consecutive_losses
    assert fixtures.error_blocks.count > configured.max_errors_in_window
    assert fixtures.open_positions
    assert fixtures.resting_entry_orders


# --------------------------------------------------------------------------- #
# The named fixtures describe the database, rather than a hope about it
# --------------------------------------------------------------------------- #


def test_every_named_fixture_matches_what_a_query_finds(seeded: SeedFixtures) -> None:
    """Spec 13 step 5: a Phase 3 test asks for "the outage run", not for a query.

    The accessor is only worth having if it agrees with the rows, so each one is
    checked against the SQL a Phase 3 test would otherwise have had to write.
    """
    with _connect(seeded.db_path) as conn:
        open_ids = [
            str(row["position_id"])
            for row in conn.execute(
                "SELECT position_id FROM positions WHERE status = 'open' ORDER BY opened_at"
            )
        ]
        resting = [
            int(row["userref"])
            for row in conn.execute(
                "SELECT userref FROM orders WHERE status = 'resting' AND intent = 'entry' "
                "ORDER BY placed_at"
            )
        ]
        errors = [
            int(row["id"])
            for row in conn.execute(
                "SELECT id FROM block_records WHERE status = ? AND ts >= ? AND ts <= ? "
                "ORDER BY ts, id",
                (
                    BlockStatus.ERROR.value,
                    seeded.error_blocks.window_start_ts,
                    seeded.error_blocks.window_end_ts,
                ),
            )
        ]
        counts = {
            table: int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
            for table in (
                "trades",
                "rejections",
                "leaderboard",
                "positions",
                "orders",
                "equity_snapshots",
                "block_records",
            )
        }

    assert sorted(seeded.open_positions) == sorted(open_ids)
    assert sorted(seeded.resting_entry_orders) == sorted(resting)
    assert sorted(seeded.error_blocks.ids) == sorted(errors)
    assert seeded.trade_count == counts["trades"]
    assert seeded.rejection_count == counts["rejections"]
    assert seeded.leaderboard_count == counts["leaderboard"]
    assert seeded.position_count == counts["positions"]
    assert seeded.order_count == counts["orders"]
    assert seeded.equity_snapshot_count == counts["equity_snapshots"]
    assert seeded.block_record_count == counts["block_records"]


def test_seed_now_is_the_newest_moment_in_the_database(seeded: SeedFixtures) -> None:
    """Phase 3 sets `context.now` from `seed_now`, so nothing may be newer than it."""
    with _connect(seeded.db_path) as conn:
        newest = max(
            int(conn.execute(f"SELECT MAX(ts) AS ts FROM {table}").fetchone()["ts"] or 0)
            for table in ("block_records", "equity_snapshots", "rejections")
        )
    assert newest == seeded.seed_now


# --------------------------------------------------------------------------- #
# The overlap that makes the fixture able to fail
# --------------------------------------------------------------------------- #


def test_the_two_runs_reuse_cycle_ids(seeded: SeedFixtures) -> None:
    """Load-bearing, and the first thing a tidy-minded reader would remove.

    `cycle_id` restarts at 1 with the process, so two runs necessarily collide. Without
    a collision in `block_records`, a counter grouping ticks by `cycle_id` alone and a
    partial unique index scoped to `cycle_id` alone would both survive this database
    unnoticed.
    """
    assert seeded.cycle_ids_shared_across_runs

    with _connect(seeded.db_path) as conn:
        shared = [
            int(row["cycle_id"])
            for row in conn.execute(
                "SELECT cycle_id FROM block_records GROUP BY cycle_id "
                "HAVING COUNT(DISTINCT run_id) > 1 ORDER BY cycle_id"
            )
        ]
    assert list(seeded.cycle_ids_shared_across_runs) == shared


def test_ordering_the_outage_by_cycle_id_gives_the_wrong_answer(seeded: SeedFixtures) -> None:
    """The seed is only useful to Phase 3 if a wrong implementation fails on it.

    `run_b` restarts at `cycle_id` 1 while `run_a` is in the hundreds, so a walk ordered
    by `cycle_id` descending never reaches the newest ticks and reports a shorter run.
    """
    with _connect(seeded.db_path) as conn:
        rows = conn.execute(
            """
            SELECT run_id, cycle_id,
                   MAX(CASE WHEN blocked_by = ? THEN 1 ELSE 0 END) AS dg
            FROM block_records
            GROUP BY run_id, cycle_id
            ORDER BY cycle_id DESC, run_id DESC
            """,
            (DATA_GUARD_ENGINE,),
        ).fetchall()

    by_cycle = 0
    for row in rows:
        if not int(row["dg"]):
            break
        by_cycle += 1

    assert by_cycle != seeded.consecutive_data_block_run.length


def test_a_tick_with_two_blockers_contributes_one_to_the_outage(seeded: SeedFixtures) -> None:
    """Invariant 12: the guard chain records every blocker, so a tick can hold two rows.

    The outage count is over ticks, never over rows, and the seed contains ticks that
    prove the two numbers differ.
    """
    outage = seeded.consecutive_data_block_run
    assert outage.double_blocker_ticks

    with _connect(seeded.db_path) as conn:
        placeholders = ",".join("(?,?)" for _ in outage.ticks)
        params: list[Any] = []
        for run_id, cycle_id in outage.ticks:
            params.extend((run_id, cycle_id))
        rows = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM block_records "
                f"WHERE (run_id, cycle_id) IN (VALUES {placeholders})",
                params,
            ).fetchone()["n"]
        )
        primaries = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM block_records WHERE is_primary = 1 "
                f"AND (run_id, cycle_id) IN (VALUES {placeholders})",
                params,
            ).fetchone()["n"]
        )

    assert rows > outage.length, "no tick carries a second blocker, so nothing is exercised"
    assert primaries == outage.length, "exactly one primary per tick"


def test_the_outage_ticks_are_in_ts_order(seeded: SeedFixtures) -> None:
    with _connect(seeded.db_path) as conn:
        moments = [
            int(
                conn.execute(
                    "SELECT MIN(ts) AS ts FROM block_records WHERE run_id = ? AND cycle_id = ?",
                    (run_id, cycle_id),
                ).fetchone()["ts"]
            )
            for run_id, cycle_id in seeded.consecutive_data_block_run.ticks
        ]
    assert moments == sorted(moments)
    assert moments[0] == seeded.consecutive_data_block_run.first_ts
    assert moments[-1] == seeded.consecutive_data_block_run.last_ts


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_seeding_twice_from_the_same_seed_is_byte_identical(tmp_path: Path) -> None:
    """Not merely "equivalent". Byte-identical, because the seed reads no clock.

    A wall-clock column anywhere in the seeded database would make every seeded copy
    differ from every other one in a way that has nothing to do with the seed, and the
    Phase 1 console would have no stable fixture to render.
    """
    first = seed_database(tmp_path / "first.sqlite")
    second = seed_database(tmp_path / "second.sqlite")

    assert _digest(first.db_path) == _digest(second.db_path)
    assert first.seed == second.seed == DEFAULT_SEED


def test_a_different_seed_produces_a_different_database(tmp_path: Path) -> None:
    """Otherwise the seed argument is decoration and the determinism test is vacuous."""
    first = seed_database(tmp_path / "first.sqlite", seed=DEFAULT_SEED)
    other = seed_database(tmp_path / "other.sqlite", seed=DEFAULT_SEED + 1)

    assert _digest(first.db_path) != _digest(other.db_path)


def test_re_seeding_an_existing_path_is_still_deterministic(tmp_path: Path) -> None:
    """The seed migrates the database it seeds, so a second call over a migrated file
    must not double-apply anything."""
    path = tmp_path / "acsoe.sqlite"
    seed_database(path)
    first = _digest(path)
    path.unlink()
    seed_database(path)

    assert _digest(path) == first


# --------------------------------------------------------------------------- #
# What the seed may never contain
# --------------------------------------------------------------------------- #


def test_no_seeded_run_is_ever_live(seeded: SeedFixtures) -> None:
    """Invariant 1: the default in every fixture is `paper`, with no exception."""
    with _connect(seeded.db_path) as conn:
        modes = {str(row["mode"]) for row in conn.execute("SELECT mode FROM runs")}
    assert modes == {RunMode.PAPER.value}
    assert RunMode.LIVE.value not in modes


def test_every_seeded_command_is_already_consumed(seeded: SeedFixtures) -> None:
    """A pending `activate` would start a daemon trading on boot, and an unconsumed
    `close_all` would liquidate: the orchestrator re-applies claimed-but-unconsumed rows
    before the first tick and acts on pending ones at the top of it."""
    with StoreClient(seeded.db_path) as store:
        assert store.pending_commands() == ()
        assert store.claimed_unconsumed_commands() == ()

    with _connect(seeded.db_path) as conn:
        unfinished = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM commands "
                "WHERE claimed_at IS NULL OR consumed_at IS NULL"
            ).fetchone()["n"]
        )
    assert unfinished == 0


def test_money_columns_come_back_as_text_not_as_numbers(seeded: SeedFixtures) -> None:
    """The database refuses a float in a money column; this proves nothing slipped past
    the client into a column SQLite would hand back as a `float`."""
    with _connect(seeded.db_path) as conn:
        for table, column in (
            ("equity_snapshots", "equity"),
            ("equity_snapshots", "peak_equity"),
            ("trades", "realised_pnl"),
            ("positions", "qty"),
            ("positions", "entry_price"),
            ("orders", "qty"),
        ):
            kinds = {
                str(row["kind"])
                for row in conn.execute(f"SELECT DISTINCT typeof({column}) AS kind FROM {table}")
            }
            assert kinds <= {"text"}, f"{table}.{column} stored a non-text value: {kinds}"


def test_rejection_reasons_are_written_for_the_operator(seeded: SeedFixtures) -> None:
    """Spec 13 step 6. The console renders `reason` verbatim, so it is a sentence; the
    machine-readable form lives beside it in `reason_code`."""
    with StoreClient(seeded.db_path) as store:
        rejections = store.recent_rejections(limit=200)

    assert rejections
    for row in rejections:
        assert " " in row.reason, f"{row.reason!r} reads like a log key, not a sentence"
        assert row.reason[0].isupper()
        assert "=" not in row.reason
        assert " " not in row.reason_code
        assert row.reason_code == row.reason_code.lower()


def test_every_seeded_equity_row_says_its_cash_is_the_start_of_tick_figure(
    seeded: SeedFixtures,
) -> None:
    """Spec 113. The seed writes `cash_source` itself, and it writes `cycle_start` on
    every row. Read from the column, so a row the database default filled would also
    pass. The seed module's own call site is what states the value."""
    with _connect(seeded.db_path) as conn:
        sources = [
            str(row["cash_source"])
            for row in conn.execute("SELECT cash_source FROM equity_snapshots")
        ]

    assert sources, "the seed writes an equity series"
    assert set(sources) == {"cycle_start"}
