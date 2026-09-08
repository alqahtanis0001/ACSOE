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

_POSITION_INSERT = (
    "INSERT INTO positions (position_id, run_id, cycle_id, pair, base, quote, side, "
    "status, qty, entry_price, target_price, stop_price, timeout_at, opened_at, "
    "updated_at) VALUES (?, 'run-a', 1, ?, 'SOL', 'USD', 'long', ?, '1.00000000', "
    "'100.00', '103.00', '98.50', 9999, 1000, 1000)"
)


# --------------------------------------------------------------------------- #
# Applying migrations
# --------------------------------------------------------------------------- #


def test_fresh_database_migrates_from_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.sqlite"
    assert not db_path.exists()

    applied = apply_migrations(db_path)

    assert applied == [1]
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
    assert EXPECTED_TABLES == ALL_TABLES - {BOOKKEEPING_TABLE}
    assert indexes == EXPECTED_INDEXES


def test_user_version_records_the_applied_schema(migrated_db: Path) -> None:
    conn = open_connection(migrated_db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
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
    money_names = {
        "equity",
        "peak_equity",
        "cash",
        "positions_value",
        "unrealised_pnl",
        "realised_pnl_cum",
        "realised_pnl",
        "realised_pnl_pct",
        "realised_pnl_quote",
        "qty",
        "filled_qty",
        "entry_price",
        "exit_price",
        "limit_price",
        "avg_fill_price",
        "target_price",
        "stop_price",
        "last_price",
        "entry_fee",
        "exit_fee",
        "fee",
        "fx_rate_entry",
        "fx_rate_exit",
        "net_pnl",
        "expected_move_pct",
        "friction_pct",
        "net_edge_pct",
        "hurdle_pct",
    }
    conn = open_connection(migrated_db)
    try:
        offenders: list[str] = []
        checked = 0
        for table in sorted(EXPECTED_TABLES):
            create_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()["sql"]
            if "STRICT" not in create_sql:
                offenders.append(f"{table} is not STRICT")
            for column in conn.execute(f"PRAGMA table_info({table})"):
                if column["name"] not in money_names:
                    continue
                checked += 1
                if column["type"].upper() != "ANY":
                    offenders.append(f"{table}.{column['name']} is {column['type']}, not ANY")
                if f"typeof({column['name']}) = 'text'" not in create_sql:
                    offenders.append(f"{table}.{column['name']} has no typeof CHECK")
    finally:
        close_connection(conn)
    assert offenders == []
    assert checked == 29


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
