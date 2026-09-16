"""Spec 11 — the schema and the forward-only migration runner.

The constraint tests here are the point of the file. `is_primary` uniqueness, one open
position per pair, and "money is never a float" are all financial rules that used to be
conventions enforced by nobody; each one now has a test that proves the *database*
refuses the bad write, not that the client happens not to make it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from acsoe.clients.store.connection import close_connection, open_connection
from acsoe.clients.store.migrations import (
    ALL_TABLES,
    BOOKKEEPING_TABLE,
    EXPECTED_INDEXES,
    EXPECTED_TABLES,
    MigrationError,
    MigrationIntegrityError,
    apply_migrations,
    default_migrations_dir,
    discover_migrations,
    schema_objects,
)


def _block_record(
    *,
    run_id: str = "run-a",
    cycle_id: int = 1,
    ts: int = 1_000,
    blocked_by: str = "data_guard",
    is_primary: int = 1,
    status: str = "BLOCK",
) -> tuple[object, ...]:
    return (cycle_id, run_id, ts, blocked_by, "reason", is_primary, status, ts)


_BLOCK_INSERT = (
    "INSERT INTO block_records "
    "(cycle_id, run_id, ts, blocked_by, block_reason, is_primary, status, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)

#: Every money column in the schema, pinned as a **set** rather than as a count.
#:
#: A count silently accepts a swap: drop one money column, add an unrelated one, and the
#: total is unchanged while the test stays green. Pinning the pairs makes both directions
#: visible — an added money column that nobody declared `ANY`, and a money column that
#: quietly stopped being one.
#:
#: The four `*_pct` columns on `rejections` and `realised_pnl_pct` on `trades` are here
#: deliberately. `code-standards.md` allows `float` for "features, indicators, model
#: inputs and statistics", and these are none of those: net edge, friction and the hurdle
#: are the arithmetic of invariant 5, computed from live fees, and they decide whether a
#: trade happens. `fx_rate_entry`/`fx_rate_exit` are here because invariant 7 converts
#: PnL through them into the reporting currency.
EXPECTED_MONEY_COLUMNS: frozenset[tuple[str, str]] = frozenset(
    {
        ("equity_snapshots", "equity"),
        ("equity_snapshots", "peak_equity"),
        ("equity_snapshots", "cash"),
        ("equity_snapshots", "positions_value"),
        ("equity_snapshots", "unrealised_pnl"),
        ("equity_snapshots", "realised_pnl_cum"),
        ("leaderboard", "net_pnl"),
        ("orders", "qty"),
        ("orders", "limit_price"),
        ("orders", "filled_qty"),
        ("orders", "avg_fill_price"),
        ("orders", "fee"),
        ("positions", "qty"),
        ("positions", "entry_price"),
        ("positions", "target_price"),
        ("positions", "stop_price"),
        ("positions", "last_price"),
        ("positions", "unrealised_pnl"),
        ("rejections", "expected_move_pct"),
        ("rejections", "friction_pct"),
        ("rejections", "net_edge_pct"),
        ("rejections", "hurdle_pct"),
        ("trades", "qty"),
        ("trades", "entry_price"),
        ("trades", "exit_price"),
        ("trades", "entry_fee"),
        ("trades", "exit_fee"),
        ("trades", "realised_pnl"),
        ("trades", "realised_pnl_pct"),
        ("trades", "realised_pnl_quote"),
        ("trades", "fx_rate_entry"),
        ("trades", "fx_rate_exit"),
    }
)

_POSITION_INSERT = (
    "INSERT INTO positions (position_id, run_id, cycle_id, pair, base, quote, side, "
    "status, qty, entry_price, target_price, stop_price, timeout_at, opened_at, "
    "updated_at) VALUES (?, 'run-a', 1, ?, 'SOL', 'USD', 'long', ?, '1.00000000', "
    "'100.00', '103.00', '98.50', 9999, 1000, 1000)"
)


# --------------------------------------------------------------------------- #
# Applying migrations
# --------------------------------------------------------------------------- #


def _migration_files() -> list[Path]:
    """Every migration file, by name, counted without going through the parser.

    `discover_migrations` is the thing under test in half this module, so an
    expectation derived from it would agree with it by construction. A plain glob is an
    independent count: it is wrong only if a file is missing from the directory, which
    is a different failure and one worth catching.
    """
    return sorted(default_migrations_dir().glob("*.sql"))


def test_fresh_database_migrates_from_empty(tmp_path: Path) -> None:
    """The expectation is derived from `db/migrations/`, not hardcoded.

    It used to read `assert applied == [1]`, which meant every migration ever added
    broke this test and the next person to add one would edit the literal — the one
    edit that makes the assertion agree with whatever just happened rather than with
    what should have happened. Deriving it keeps the two properties that actually
    matter, and both are still asserted here: **every** migration in the directory was
    applied, and they were applied in ascending contiguous order from 1. A migration
    silently skipped, applied twice, or applied out of order still fails.
    """
    expected = list(range(1, len(_migration_files()) + 1))
    assert len(expected) >= 4, (
        "0002 is spec 31's, 0003 is the hold-reason ruling's and 0004 is the "
        "base-rate-Brier ruling's; a shorter list means one went missing"
    )
    db_path = tmp_path / "fresh.sqlite"
    assert not db_path.exists()

    applied = apply_migrations(db_path)

    assert applied == expected
    assert db_path.is_file()


def test_migrating_twice_is_a_no_op(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.sqlite"
    apply_migrations(db_path)

    conn = open_connection(db_path)
    before = schema_objects(conn)
    close_connection(conn)

    assert apply_migrations(db_path) == []

    conn = open_connection(db_path)
    assert schema_objects(conn) == before
    close_connection(conn)


def test_table_and_index_sets_match_the_contract(migrated_db: Path) -> None:
    conn = open_connection(migrated_db)
    try:
        tables, indexes = schema_objects(conn)
    finally:
        close_connection(conn)

    assert tables == ALL_TABLES
    assert ALL_TABLES - {BOOKKEEPING_TABLE} == EXPECTED_TABLES
    assert indexes == EXPECTED_INDEXES


def test_user_version_records_the_applied_schema(migrated_db: Path) -> None:
    """`PRAGMA user_version` is the highest migration on disk, derived not hardcoded.

    This is the field an operator reads to ask "which schema is in this file", so what
    it must equal is the newest migration, not a number that was true once.
    """
    latest = len(_migration_files())
    conn = open_connection(migrated_db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == latest
    finally:
        close_connection(conn)


def test_applied_at_is_null_unless_a_caller_supplies_one(tmp_path: Path) -> None:
    """The runner reads no clock. Spec 13 needs two seedings to be byte-identical, and
    a wall-clock column would break that on its own."""
    default_path = tmp_path / "default.sqlite"
    stamped_path = tmp_path / "stamped.sqlite"
    apply_migrations(default_path)
    apply_migrations(stamped_path, applied_at=1_700_000_000_000_000)

    for path, expected in ((default_path, None), (stamped_path, 1_700_000_000_000_000)):
        conn = open_connection(path)
        try:
            row = conn.execute(
                f"SELECT applied_at FROM {BOOKKEEPING_TABLE} WHERE version = 1"
            ).fetchone()
        finally:
            close_connection(conn)
        assert row["applied_at"] == expected


def test_editing_an_applied_migration_is_refused(tmp_path: Path) -> None:
    """Forward-only means an applied file may never change. Two databases claiming the
    same schema version with different schemas in them is the failure this prevents."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_initial.sql").write_text("CREATE TABLE a (x INTEGER);", encoding="utf-8")
    db_path = tmp_path / "db.sqlite"
    apply_migrations(db_path, migrations_dir=migrations)

    (migrations / "0001_initial.sql").write_text(
        "CREATE TABLE a (x INTEGER, y INTEGER);", encoding="utf-8"
    )

    with pytest.raises(MigrationIntegrityError, match="forward-only"):
        apply_migrations(db_path, migrations_dir=migrations)


def test_a_failing_migration_leaves_no_partial_schema(tmp_path: Path) -> None:
    """The schema and its bookkeeping row commit together or not at all."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_broken.sql").write_text(
        "CREATE TABLE good (x INTEGER);\nCREATE TABLE good (x INTEGER);\n", encoding="utf-8"
    )
    db_path = tmp_path / "db.sqlite"

    with pytest.raises(sqlite3.DatabaseError):
        apply_migrations(db_path, migrations_dir=migrations)

    conn = open_connection(db_path)
    try:
        tables, _ = schema_objects(conn)
    finally:
        close_connection(conn)
    assert "good" not in tables


@pytest.mark.parametrize(
    ("filename", "match"),
    [
        ("1_initial.sql", "NNNN_lower_snake_case"),
        ("0001-Initial.sql", "NNNN_lower_snake_case"),
        ("0002_second.sql", "contiguous"),
    ],
)
def test_malformed_migration_sets_are_refused(tmp_path: Path, filename: str, match: str) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / filename).write_text("CREATE TABLE a (x INTEGER);", encoding="utf-8")

    with pytest.raises(MigrationError, match=match):
        discover_migrations(migrations)


def test_a_duplicate_migration_version_is_refused(tmp_path: Path) -> None:
    """Two files claiming version 1. Found by a wide branch sweep with no test on it.

    Silent if unrefused: `found` is a dict keyed on version, so the second file simply
    overwrites the first and `discover_migrations` returns a set that looks contiguous
    and well-formed while one migration has vanished from it. The database then records
    a `schema_migrations` row whose checksum belongs to a file nobody applied.
    """
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_initial.sql").write_text("CREATE TABLE a (x INTEGER);", encoding="utf-8")
    (migrations / "0001_also_initial.sql").write_text(
        "CREATE TABLE b (x INTEGER);", encoding="utf-8"
    )

    # On the message, not the bare type: all five refusal branches in this function
    # raise `MigrationError`, so `pytest.raises(MigrationError)` alone would be
    # satisfied by any of them and this test would pass for the wrong reason.
    with pytest.raises(MigrationError, match="duplicate migration version 0001"):
        discover_migrations(migrations)


def test_a_directory_with_no_migrations_is_refused(tmp_path: Path) -> None:
    """An empty directory is not an empty schema. Also a survivor of the wide sweep.

    Unrefused it returns `()`, and an empty tuple satisfies the contiguity check
    trivially — `expected` and `actual` are both `[]`. `apply_migrations` would then
    report success over a database with no tables in it, which surfaces later as
    `no such table` from whichever engine got there first.
    """
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "README.md").write_text("not a migration", encoding="utf-8")

    with pytest.raises(MigrationError, match="no migration files in"):
        discover_migrations(migrations)


def test_a_missing_migrations_directory_is_refused(tmp_path: Path) -> None:
    """Distinct from the empty directory above, and the messages say which is which.

    This branch was killed in the wide sweep only by a Phase 4 engine test that happens
    to construct a store over a path that does not exist. That test asserts something
    else entirely and could be rewritten tomorrow, taking the only coverage of this
    branch with it. The coverage now lives next to the code it is about.
    """
    with pytest.raises(MigrationError, match="migrations directory not found"):
        discover_migrations(tmp_path / "nowhere")


def test_non_sql_files_beside_the_migrations_are_ignored(tmp_path: Path) -> None:
    """The skip is behaviour, not a refusal, and it is the reason the two directory
    failures above are reachable at all.

    Killed in the wide sweep only by a research import-boundary test that happens to
    walk this directory — incidental coverage of a path that decides whether a stray
    `.md`, a `.gitkeep` or an editor backup file turns a working checkout into a
    `migration filename must be NNNN_lower_snake_case.sql` crash at startup.
    """
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_initial.sql").write_text("CREATE TABLE a (x INTEGER);", encoding="utf-8")
    (migrations / "README.md").write_text("notes", encoding="utf-8")
    (migrations / "notes.txt").write_text("scratch", encoding="utf-8")
    (migrations / "0002_not_really.sql.bak").write_text("backup", encoding="utf-8")

    found = discover_migrations(migrations)

    assert [(m.version, m.name) for m in found] == [(1, "initial")]


def test_the_real_migrations_directory_is_discoverable() -> None:
    migrations = discover_migrations(default_migrations_dir())
    assert [m.version for m in migrations] == list(range(1, len(migrations) + 1))
    assert migrations[0].name == "initial"


# --------------------------------------------------------------------------- #
# Constraints that enforce a financial rule
# --------------------------------------------------------------------------- #


def test_a_second_primary_block_record_for_one_tick_raises(migrated_db: Path) -> None:
    """Invariant 12: `is_primary` marks the one blocker that gated the opportunity
    chain. Two of them on one tick would leave the audit trail unable to say which
    block stopped the pipeline."""
    conn = open_connection(migrated_db)
    try:
        conn.execute(_BLOCK_INSERT, _block_record(blocked_by="data_guard"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_BLOCK_INSERT, _block_record(blocked_by="safety"))
    finally:
        close_connection(conn)


def test_a_second_non_primary_block_record_for_one_tick_is_allowed(migrated_db: Path) -> None:
    """The guard chain never breaks early, so two guards can block on one tick. Only the
    *primary* is unique."""
    conn = open_connection(migrated_db)
    try:
        conn.execute(_BLOCK_INSERT, _block_record(blocked_by="data_guard", is_primary=1))
        conn.execute(_BLOCK_INSERT, _block_record(blocked_by="safety", is_primary=0))
        count = conn.execute("SELECT COUNT(*) AS n FROM block_records").fetchone()["n"]
    finally:
        close_connection(conn)
    assert count == 2


def test_the_same_cycle_id_in_a_different_run_may_also_be_primary(migrated_db: Path) -> None:
    """The constraint is one primary per *tick*, and a tick is `(run_id, cycle_id)`.

    `cycle_id` restarts at 1 with each process, so scoping this to `cycle_id` alone
    would reject the second run of any seeded outage that spans a restart — which is
    exactly the fixture Phase 3 counts against.
    """
    conn = open_connection(migrated_db)
    try:
        conn.execute(_BLOCK_INSERT, _block_record(run_id="run-a", cycle_id=1, ts=1_000))
        conn.execute(_BLOCK_INSERT, _block_record(run_id="run-b", cycle_id=1, ts=2_000))
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM block_records WHERE is_primary = 1"
        ).fetchone()["n"]
    finally:
        close_connection(conn)
    assert count == 2


def test_two_open_positions_on_one_pair_raise(migrated_db: Path) -> None:
    """Invariant 6, "one open position per pair", enforced by the database."""
    conn = open_connection(migrated_db)
    try:
        conn.execute(_POSITION_INSERT, ("pos-1", "SOL/USD", "open"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_POSITION_INSERT, ("pos-2", "SOL/USD", "open"))
    finally:
        close_connection(conn)


def test_a_closed_position_does_not_block_a_new_one_on_the_same_pair(migrated_db: Path) -> None:
    conn = open_connection(migrated_db)
    try:
        conn.execute(_POSITION_INSERT, ("pos-1", "SOL/USD", "closed"))
        conn.execute(_POSITION_INSERT, ("pos-2", "SOL/USD", "closed"))
        conn.execute(_POSITION_INSERT, ("pos-3", "SOL/USD", "open"))
        count = conn.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"]
    finally:
        close_connection(conn)
    assert count == 3


def test_two_equity_snapshots_for_one_tick_raise(migrated_db: Path) -> None:
    insert = (
        "INSERT INTO equity_snapshots (cycle_id, run_id, ts, currency, equity, "
        "peak_equity, cash, positions_value, unrealised_pnl, realised_pnl_cum, "
        "open_position_count, updated_at) VALUES "
        "(1, 'run-a', ?, 'USD', '100.00', '100.00', '100.00', '0.00', '0.00', '0.00', 0, 1)"
    )
    conn = open_connection(migrated_db)
    try:
        conn.execute(insert, (1_000,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, (2_000,))
    finally:
        close_connection(conn)


def test_a_float_in_a_money_column_is_refused_by_the_database(migrated_db: Path) -> None:
    """SQLite is dynamically typed: a column declared TEXT will store a float unless
    something stops it. A drifting float equity series moves the drawdown threshold that
    liquidates the account, so the schema stops it."""
    conn = open_connection(migrated_db)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="typeof"):
            conn.execute(
                "INSERT INTO equity_snapshots (cycle_id, run_id, ts, currency, equity, "
                "peak_equity, cash, positions_value, unrealised_pnl, realised_pnl_cum, "
                "open_position_count, updated_at) VALUES "
                "(1, 'run-a', 1, 'USD', ?, '100.00', '100.00', '0.00', '0.00', '0.00', 0, 1)",
                (100.0,),
            )
    finally:
        close_connection(conn)


def test_every_money_column_is_declared_any_with_a_text_check(migrated_db: Path) -> None:
    """A blanket sweep, so a money column added later cannot quietly become a float.

    `ANY` rather than `TEXT` is not a slip. A `TEXT` column has TEXT affinity, which
    converts an inserted float to text *before* any CHECK runs, so `TEXT` enforces
    nothing at all; `ANY` stores the value as given and the CHECK then sees a REAL and
    refuses it. The contents are guaranteed text more strongly, not less.
    """
    conn = open_connection(migrated_db)
    try:
        offenders: list[str] = []
        found: set[tuple[str, str]] = set()
        for table in sorted(EXPECTED_TABLES):
            create_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()["sql"]
            if "STRICT" not in create_sql:
                offenders.append(f"{table} is not STRICT")
            for column in conn.execute(f"PRAGMA table_info({table})"):
                name = str(column["name"])
                if str(column["type"]).upper() != "ANY":
                    continue
                found.add((table, name))
                if f"typeof({name}) = 'text'" not in create_sql:
                    offenders.append(f"{table}.{name} has no typeof CHECK")
    finally:
        close_connection(conn)

    assert offenders == []
    assert found == EXPECTED_MONEY_COLUMNS


def test_an_unrecognised_command_can_be_stored(migrated_db: Path) -> None:
    """`architecture-context.md` says an unrecognised command is ignored and logged as a
    warning. A CHECK on the column would make that path unreachable and its test
    unwritable, so there deliberately is not one."""
    conn = open_connection(migrated_db)
    try:
        conn.execute(
            "INSERT INTO commands (command, source, created_at, updated_at) "
            "VALUES ('go_faster', 'console', 1, 1)"
        )
        stored = conn.execute("SELECT command FROM commands").fetchone()["command"]
    finally:
        close_connection(conn)
    assert stored == "go_faster"


def test_live_mode_is_not_present_anywhere_in_a_fresh_database(migrated_db: Path) -> None:
    conn = open_connection(migrated_db)
    try:
        rows = conn.execute("SELECT COUNT(*) AS n FROM runs WHERE mode = 'live'").fetchone()
    finally:
        close_connection(conn)
    assert rows["n"] == 0


# --------------------------------------------------------------------------- #
# 0002 — the persisted system mode (spec 31)
# --------------------------------------------------------------------------- #

_RUN_INSERT = (
    "INSERT INTO runs (run_id, mode, started_at, updated_at) VALUES (?, 'paper', 1000, 1000)"
)


def test_a_new_run_row_has_no_system_mode(migrated_db: Path) -> None:
    """NULL is "no daemon has written a mode for this run yet", and it is a different
    fact from 'idle', which is a daemon actively reporting that it is idle. The column
    is nullable and has no default precisely so the two are not collapsed."""
    conn = open_connection(migrated_db)
    try:
        conn.execute(_RUN_INSERT, ("run-a",))
        row = conn.execute(
            "SELECT system_mode, system_mode_at FROM runs WHERE run_id = 'run-a'"
        ).fetchone()
    finally:
        close_connection(conn)
    assert row["system_mode"] is None
    assert row["system_mode_at"] is None


def test_an_unrecognised_system_mode_is_refused(migrated_db: Path) -> None:
    """Unlike `commands.command`, this column carries a CHECK. There is no "ignore it
    and log a warning" path for a status band: a mode the console cannot render is a
    reading it would have to invent, so the database refuses the write instead."""
    conn = open_connection(migrated_db)
    try:
        conn.execute(_RUN_INSERT, ("run-a",))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE runs SET system_mode = 'trading' WHERE run_id = 'run-a'")
    finally:
        close_connection(conn)


def test_the_system_mode_columns_did_not_disturb_the_existing_runs_contract(
    migrated_db: Path,
) -> None:
    """0002 is additive: `runs.mode` still means paper/live/replay and still refuses
    anything else. Two columns named for a "mode" on one row is exactly the collision
    that reads fine and is wrong, so both CHECKs are asserted together here."""
    conn = open_connection(migrated_db)
    try:
        conn.execute(_RUN_INSERT, ("run-a",))
        conn.execute("UPDATE runs SET system_mode = 'frozen' WHERE run_id = 'run-a'")
        row = conn.execute("SELECT mode, system_mode FROM runs WHERE run_id = 'run-a'").fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE runs SET mode = 'frozen' WHERE run_id = 'run-a'")
    finally:
        close_connection(conn)
    assert (row["mode"], row["system_mode"]) == ("paper", "frozen")


# --------------------------------------------------------------------------- #
# 0003 — the manage chain's hold reason on a position (lead ruling 2026-09-16)
#
# The console is a separate process and reads this file, so a hold that lives
# only in `state` is one it can never render. Engine 19 `memory` is the only
# writer; these tests are about what the database itself carries and refuses.
# --------------------------------------------------------------------------- #

def test_a_new_position_row_has_no_hold_reason(migrated_db: Path) -> None:
    """NULL means the manage chain did not hold, never "unknown".

    The column is nullable with no default precisely so the writer states the fact
    every tick rather than inheriting one, and so a reader may treat NULL as an
    answer rather than as missing information.
    """
    conn = open_connection(migrated_db)
    try:
        conn.execute(_POSITION_INSERT, ("pos-a", "SOL/USD", "open"))
        row = conn.execute(
            "SELECT hold_reason FROM positions WHERE position_id = 'pos-a'"
        ).fetchone()
    finally:
        close_connection(conn)
    assert row["hold_reason"] is None


@pytest.mark.parametrize("blank", ["", " ", "\t", "\n", "\r\n  "])
def test_a_blank_hold_reason_is_refused(migrated_db: Path, blank: str) -> None:
    """The one thing the database can enforce about condition 3 of the ruling.

    Whether a hold *happened* is a property of the tick and not of the row, so no
    CHECK can enforce "cleared when it did not hold". A blank string is enforceable
    and is the way "unknown" normally gets past a nullable column: non-null, so every
    `IS NOT NULL` read calls it a hold, and blank, so it renders as nothing.

    `trim()` rather than `<> ''`, so the database refuses exactly what `PositionRow`
    refuses — a constraint the two layers disagree about is one of them not applying it.
    The tab and the newlines are what pay for the parametrisation rather than three kinds
    of space: SQLite's **one-argument** `trim()` strips spaces and nothing else, so the
    obvious CHECK let both through, and this case is what found it.
    """
    conn = open_connection(migrated_db)
    try:
        conn.execute(_POSITION_INSERT, ("pos-a", "SOL/USD", "open"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE positions SET hold_reason = ? WHERE position_id = 'pos-a'", (blank,)
            )
    finally:
        close_connection(conn)


def test_the_hold_reason_column_enumerates_no_reasons(migrated_db: Path) -> None:
    """A reason the database has never seen is stored, not refused.

    Unlike `runs.system_mode`, the hold reasons are not a closed set: engine 21
    declares them and `console/format.py` maps them, and a CHECK here would be a third
    copy that only another migration could correct. The list is enforced at test time
    by spec 99's walk over every engine's codes, not at runtime by SQLite.
    """
    conn = open_connection(migrated_db)
    try:
        conn.execute(_POSITION_INSERT, ("pos-a", "SOL/USD", "open"))
        conn.execute(
            "UPDATE positions SET hold_reason = 'a_reason_engine_21_does_not_have_yet' "
            "WHERE position_id = 'pos-a'"
        )
        stored = conn.execute(
            "SELECT hold_reason FROM positions WHERE position_id = 'pos-a'"
        ).fetchone()["hold_reason"]
    finally:
        close_connection(conn)
    assert stored == "a_reason_engine_21_does_not_have_yet"


def test_0003_did_not_disturb_the_existing_positions_contract(migrated_db: Path) -> None:
    """0003 is additive. The two constraints on `positions` that carry money rules —
    invariant 6's one-open-position-per-pair index and the long-only CHECK — still
    refuse what they refused before, asserted here alongside a written hold reason so
    the additive claim is made on a row that actually uses the new column."""
    conn = open_connection(migrated_db)
    try:
        conn.execute(_POSITION_INSERT, ("pos-a", "SOL/USD", "open"))
        conn.execute(
            "UPDATE positions SET hold_reason = 'data_guard_blocked' "
            "WHERE position_id = 'pos-a'"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_POSITION_INSERT, ("pos-b", "SOL/USD", "open"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE positions SET side = 'short' WHERE position_id = 'pos-a'")
        row = conn.execute(
            "SELECT side, status, hold_reason FROM positions WHERE position_id = 'pos-a'"
        ).fetchone()
    finally:
        close_connection(conn)
    assert (row["side"], row["status"], row["hold_reason"]) == (
        "long",
        "open",
        "data_guard_blocked",
    )


# --------------------------------------------------------------------------- #
# 0004 — `leaderboard.base_rate_brier` (lead ruling 2026-09-16)
#
# The null hypothesis `brier` is measured against: the score a model predicting
# the fold's own class frequency every time would have got. Engine 20 already
# computes it per fold and discarded it for want of a column.
# --------------------------------------------------------------------------- #

_LEADERBOARD_INSERT = (
    "INSERT INTO leaderboard (model_id, model_version, trained_at, n_trades, "
    "promoted, updated_at) VALUES ('predictor', ?, 1000, 5, 0, 1000)"
)


def test_a_new_leaderboard_row_has_no_base_rate_brier(migrated_db: Path) -> None:
    """NULL means "not recorded", never "no baseline".

    There is no honest default: `0.0` is a perfect baseline and would make every row
    written before 0004 look skill-less, and `0.25` is the balanced-fold value and
    would be a guess about folds nobody measured. Engine 14 must read the absence as
    an absence — absent is never zero.
    """
    conn = open_connection(migrated_db)
    try:
        conn.execute(_LEADERBOARD_INSERT, ("v1",))
        row = conn.execute("SELECT base_rate_brier FROM leaderboard").fetchone()
    finally:
        close_connection(conn)
    assert row["base_rate_brier"] is None


def test_the_base_rate_brier_is_a_real_and_deliberately_not_a_money_column(
    migrated_db: Path,
) -> None:
    """A statistic, so `REAL` is correct — `code-standards.md` allows float for
    "features, indicators, model inputs and statistics", and every other metric on this
    table is `REAL` for the same reason.

    The second assertion is the one that matters: `EXPECTED_MONEY_COLUMNS` is the set a
    money column must be in, and a money column added as `REAL` is exactly the defect
    `test_every_money_column_is_declared_any_with_a_text_check` exists to catch. This
    one is not money and says so here rather than relying on nobody adding it later.
    """
    conn = open_connection(migrated_db)
    try:
        conn.execute(_LEADERBOARD_INSERT, ("v1",))
        conn.execute("UPDATE leaderboard SET base_rate_brier = 0.245")
        row = conn.execute("SELECT base_rate_brier FROM leaderboard").fetchone()
        declared = {
            str(column["name"]): str(column["type"])
            for column in conn.execute("PRAGMA table_info(leaderboard)")
        }
    finally:
        close_connection(conn)
    assert row["base_rate_brier"] == 0.245
    assert isinstance(row["base_rate_brier"], float)
    assert declared["base_rate_brier"] == "REAL"
    assert ("leaderboard", "base_rate_brier") not in EXPECTED_MONEY_COLUMNS


def test_0004_did_not_disturb_the_existing_leaderboard_contract(migrated_db: Path) -> None:
    """0004 is additive. `net_pnl` is still the one money column on this table and
    still refuses a number, asserted beside a written `base_rate_brier` so the claim is
    made on a row that actually uses the new column."""
    conn = open_connection(migrated_db)
    try:
        conn.execute(_LEADERBOARD_INSERT, ("v1",))
        conn.execute("UPDATE leaderboard SET base_rate_brier = 0.25, net_pnl = '10.00'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE leaderboard SET net_pnl = 10.0")
        row = conn.execute("SELECT net_pnl, base_rate_brier FROM leaderboard").fetchone()
    finally:
        close_connection(conn)
    assert (row["net_pnl"], row["base_rate_brier"]) == ("10.00", 0.25)
