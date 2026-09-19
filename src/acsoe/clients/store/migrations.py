"""Forward-only SQLite migrations.

`db/migrations/NNNN_name.sql` holds the schema. This module applies the pending ones
in numeric order and records what it applied in `schema_migrations`.

Forward-only means exactly that: there are no down-migrations, and an already-applied
file may never be edited. The checksum recorded at apply time is verified on every
subsequent run, so editing an applied migration fails loudly on the next startup
instead of leaving two databases claiming the same schema version with different
schemas in them.

`EXPECTED_TABLES` and `EXPECTED_INDEXES` are maintained by hand rather than read back
out of the database. That is deliberate: if they were derived from the migrations they
would agree with the migrations by construction and could not catch a table that was
never written. They are the contract; `tests/db/test_migrations.py` asserts the
migrations produce exactly them.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from acsoe.clients.store.connection import close_connection, open_connection

BOOKKEEPING_TABLE = "schema_migrations"

MIGRATION_FILENAME = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")

#: The ten relational tables of `context/architecture-context.md`. `approvals` comes from
#: migration 0006 (spec 132). The set does not include :data:`BOOKKEEPING_TABLE`, so it is
#: exactly the set a caller wants to compare against.
EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "approvals",
        "block_records",
        "commands",
        "equity_snapshots",
        "leaderboard",
        "orders",
        "positions",
        "rejections",
        "runs",
        "trades",
    }
)

#: Everything the schema owns, bookkeeping included.
ALL_TABLES: frozenset[str] = EXPECTED_TABLES | {BOOKKEEPING_TABLE}

#: Every named index. Auto-created indexes backing PRIMARY KEY and UNIQUE column
#: constraints are named `sqlite_autoindex_*` by SQLite and are excluded.
EXPECTED_INDEXES: frozenset[str] = frozenset(
    {
        "idx_approvals_run_cycle",
        "idx_block_records_blocked_by_ts",
        "idx_block_records_run_cycle",
        "idx_block_records_status_ts",
        "idx_block_records_ts",
        "idx_commands_pending",
        "idx_commands_unconsumed",
        "idx_equity_snapshots_ts",
        "idx_leaderboard_model",
        "idx_leaderboard_trained_at",
        "idx_orders_order_id",
        "idx_orders_position_id",
        "idx_orders_status",
        "idx_positions_pair_status",
        "idx_positions_status",
        "idx_rejections_rejected_by",
        "idx_rejections_run_cycle",
        "idx_rejections_ts",
        "idx_runs_started_at",
        "idx_trades_closed_at",
        "idx_trades_pair",
        "ux_block_records_primary",
        "ux_equity_snapshots_tick",
        "ux_positions_open_pair",
    }
)


class MigrationError(RuntimeError):
    """A migration could not be discovered or applied."""


class MigrationIntegrityError(MigrationError):
    """An already-applied migration file no longer matches its recorded checksum."""


@dataclass(frozen=True)
class Migration:
    """One migration file, parsed."""

    version: int
    name: str
    path: Path
    sql: str
    checksum: str


def default_migrations_dir() -> Path:
    """`db/migrations/` at the repository root.

    Resolved from this file's location: `src/acsoe/clients/store/migrations.py` sits
    four directories below the root. An editable install keeps the source tree in
    place, which is how spec 03 installs the package.
    """
    return Path(__file__).resolve().parents[4] / "db" / "migrations"


def discover_migrations(migrations_dir: Path | None = None) -> tuple[Migration, ...]:
    """Parse every migration file in numeric order."""
    directory = Path(migrations_dir) if migrations_dir is not None else default_migrations_dir()
    if not directory.is_dir():
        raise MigrationError(f"migrations directory not found: {directory}")

    found: dict[int, Migration] = {}
    for path in sorted(directory.iterdir()):
        if path.suffix != ".sql" or not path.is_file():
            continue
        match = MIGRATION_FILENAME.match(path.name)
        if match is None:
            raise MigrationError(
                f"migration filename must be NNNN_lower_snake_case.sql, got: {path.name}"
            )
        version = int(match.group("version"))
        if version in found:
            raise MigrationError(
                f"duplicate migration version {version:04d}: "
                f"{found[version].path.name} and {path.name}"
            )
        # `read_text` applies universal newlines, so a CRLF checkout and an LF
        # checkout of the same file produce the same checksum.
        sql = path.read_text(encoding="utf-8")
        found[version] = Migration(
            version=version,
            name=match.group("name"),
            path=path,
            sql=sql,
            checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        )

    if not found:
        raise MigrationError(f"no migration files in {directory}")

    ordered = tuple(found[version] for version in sorted(found))
    expected = list(range(1, len(ordered) + 1))
    actual = [m.version for m in ordered]
    if actual != expected:
        raise MigrationError(f"migration versions must be contiguous from 1, got {actual}")
    return ordered


def _ensure_bookkeeping(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {BOOKKEEPING_TABLE} (
            version    INTEGER PRIMARY KEY,
            name       TEXT    NOT NULL,
            checksum   TEXT    NOT NULL,
            applied_at INTEGER
        )
        """
    )


def applied_migrations(conn: sqlite3.Connection) -> dict[int, str]:
    """Map applied version to the checksum recorded when it was applied."""
    _ensure_bookkeeping(conn)
    rows = conn.execute(
        f"SELECT version, checksum FROM {BOOKKEEPING_TABLE} ORDER BY version"
    ).fetchall()
    return {int(row["version"]): str(row["checksum"]) for row in rows}


def apply_migrations(
    db_path: Path,
    *,
    migrations_dir: Path | None = None,
    applied_at: int | None = None,
) -> list[int]:
    """Bring `db_path` up to the latest schema. Returns the versions applied.

    A fresh file returns every version; an already-current database returns `[]`, so
    "re-migrating is a no-op" is a check on the return value rather than on a diff.

    `applied_at` is injected rather than read from a clock. Nothing in this package
    reads a clock, and spec 13 requires two seedings of the same seed to be
    byte-identical — a wall-clock column would break that on its own.
    """
    migrations = discover_migrations(migrations_dir)
    conn = open_connection(db_path)
    try:
        return _apply(conn, migrations, applied_at)
    finally:
        close_connection(conn)


def _apply(
    conn: sqlite3.Connection,
    migrations: tuple[Migration, ...],
    applied_at: int | None,
) -> list[int]:
    already = applied_migrations(conn)

    for migration in migrations:
        recorded = already.get(migration.version)
        if recorded is not None and recorded != migration.checksum:
            raise MigrationIntegrityError(
                f"migration {migration.version:04d}_{migration.name} has changed since it "
                f"was applied (recorded {recorded[:12]}, file {migration.checksum[:12]}). "
                "Migrations are forward-only: add a new file instead of editing an "
                "applied one."
            )

    applied: list[int] = []
    for migration in migrations:
        if migration.version in already:
            continue
        try:
            conn.executescript(_transactional_script(migration, applied_at))
        except sqlite3.DatabaseError:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        applied.append(migration.version)

    return applied


def _transactional_script(migration: Migration, applied_at: int | None) -> str:
    """Wrap one migration and its bookkeeping row into a single atomic script.

    `Connection.executescript` commits any pending transaction *before* it runs, so a
    `BEGIN` issued around the call is discarded and the migration would apply
    statement by statement in autocommit. The `BEGIN` has to be inside the script.

    The bookkeeping insert goes in the same script rather than in a following
    statement. Split across two transactions, a crash in between would leave a
    database whose schema had been applied and whose `schema_migrations` row had not,
    and the next run would try to create tables that already exist.

    The values interpolated here are a parsed integer, a name matched against
    `[a-z0-9_]+`, and a hex digest, so there is nothing to inject; `executescript`
    takes no parameters.
    """
    applied_at_sql = "NULL" if applied_at is None else str(int(applied_at))
    return (
        "BEGIN;\n"
        f"{migration.sql}\n"
        f"INSERT INTO {BOOKKEEPING_TABLE} (version, name, checksum, applied_at)\n"
        f"VALUES ({migration.version}, '{migration.name}', "
        f"'{migration.checksum}', {applied_at_sql});\n"
        f"PRAGMA user_version = {migration.version};\n"
        "COMMIT;\n"
    )


def schema_objects(conn: sqlite3.Connection) -> tuple[frozenset[str], frozenset[str]]:
    """The table and named-index sets actually present, for verification.

    `sqlite_*` internals and the auto-indexes SQLite creates for PRIMARY KEY and
    UNIQUE column constraints are excluded — they are not part of the contract.
    """
    tables = frozenset(
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    )
    indexes = frozenset(
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
        )
    )
    return tables, indexes
