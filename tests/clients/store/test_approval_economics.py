"""Spec 132: migration 0006. Why a trade was approved, and which scenario priced a run.

Three properties matter here, and each has a test that can fail.

1. **Absent is never zero.** A database holding rows written before 0006 migrates, and
   those rows read every new field as `None`. That covers a hand-built pre-0006 database
   and the Phase 0 seed carried across the migration.
2. **Every new field round-trips exactly**, down to the quantum. The assertions are on the
   rendered string, because `Decimal("0.01000") == Decimal("0.01")` and a store that
   normalised trailing zeros would pass an equality.
3. **A float is refused**, at the model boundary and again by the database.

Beside them sit the two write-once properties the migration's design rests on. A second
approval for one entry raises. And `write_run` can never erase a run's scenario.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from acsoe.clients.store.client import StoreClient, StoreError
from acsoe.clients.store.connection import close_connection, open_connection
from acsoe.clients.store.contracts import (
    ApprovalRow,
    RunMode,
    RunRow,
    TradeOutcome,
    TradeRow,
)
from acsoe.clients.store.migrations import apply_migrations, default_migrations_dir
from acsoe.clients.store.seed import seed_database

#: The seven fields 0006 adds to `trades`, and the same seven on `approvals`.
ECONOMICS = ("expected_move_pct", "friction_pct", "net_edge_pct", "hurdle_pct")
RUN_IDS = ("prediction_run_id", "anomaly_run_id", "skeptic_run_id")
TRADE_FIELDS = ECONOMICS + RUN_IDS
RUN_FIELDS = ("scenario_digest", "scenario_description")

#: Values chosen so that a store which normalised the quantum, or truncated, or swapped
#: two columns, would render a different string for each. No two are equal.
ECONOMIC_VALUES = {
    "expected_move_pct": "0.01840",
    "friction_pct": "0.006125",
    "net_edge_pct": "0.012275",
    "hurdle_pct": "0.0091875",
}
#: Spec 145's snapshot. It is canonical JSON, and the store treats it as opaque text. The
#: exact string must come back byte for byte, with the key order and the decimal string
#: intact.
DETAILS = '{"details_version":1,"cost":{"friction_pct":"0.006125"},"skeptic":{"p_wrong":0.31}}'
RUN_ID_VALUES = {
    "prediction_run_id": "train-x-f404-p7",
    "anomaly_run_id": "train-x-f404-p7a",
    "skeptic_run_id": "train-x-f404-p7s",
}


def _trade(**extra: Any) -> TradeRow:
    return TradeRow(
        trade_id="t-1",
        position_id="p-1",
        run_id="run-a",
        cycle_id=7,
        pair="SOL/USD",
        base="SOL",
        quote="USD",
        qty=Decimal("1.00000000"),
        entry_price=Decimal("100.00"),
        exit_price=Decimal("103.00"),
        entry_fee=Decimal("0.22"),
        exit_fee=Decimal("0.39"),
        entry_userref=11,
        exit_userref=12,
        opened_at=1_000,
        closed_at=2_000,
        outcome=TradeOutcome.TARGET,
        realised_pnl=Decimal("2.39"),
        realised_pnl_pct=Decimal("0.0239"),
        realised_pnl_quote=Decimal("2.39"),
        reporting_currency="USD",
        fx_rate_entry=Decimal("1"),
        fx_rate_exit=Decimal("1"),
        updated_at=2_000,
        **extra,
    )


def _approval(**overrides: Any) -> ApprovalRow:
    fields: dict[str, Any] = {
        "userref": 11,
        "run_id": "run-a",
        "cycle_id": 3,
        "ts": 900,
        "pair": "SOL/USD",
        **{name: Decimal(value) for name, value in ECONOMIC_VALUES.items()},
        **RUN_ID_VALUES,
        "details": DETAILS,
        "updated_at": 900,
    }
    fields.update(overrides)
    return ApprovalRow(**fields)


def _staged_before_0006(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A copy of the real migrations directory without 0006, a database migrated to 0005,
    and the 0006 file to add afterwards. The rows a test writes then really predate it."""
    real = sorted(default_migrations_dir().glob("*.sql"))
    sixth = real[5]
    assert sixth.name == "0006_approval_economics.sql", [path.name for path in real]
    staged = tmp_path / "migrations"
    staged.mkdir()
    for path in real[:5]:
        (staged / path.name).write_bytes(path.read_bytes())
    db_path = tmp_path / "db.sqlite"
    assert apply_migrations(db_path, migrations_dir=staged) == [1, 2, 3, 4, 5]
    return staged, db_path, sixth


# --------------------------------------------------------------------------- #
# 1. Absent is never zero
# --------------------------------------------------------------------------- #


def test_rows_written_before_0006_read_every_new_field_as_absent(tmp_path: Path) -> None:
    """A trade and a run written under 0005 read `None` for every 0006 field, not zero.

    The rows are inserted by hand, naming only the columns 0005 had, so the new columns do
    not exist when they are written. Nothing backfills them from `rejections` (spec 132's
    scope limit), and the columns they already had are untouched.
    """
    staged, db_path, sixth = _staged_before_0006(tmp_path)
    conn = open_connection(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
        assert not columns & set(TRADE_FIELDS), "the rows below must predate the columns"
        conn.execute(
            "INSERT INTO trades (trade_id, run_id, cycle_id, pair, base, quote, side, qty, "
            "entry_price, exit_price, entry_fee, exit_fee, opened_at, closed_at, outcome, "
            "realised_pnl, realised_pnl_pct, realised_pnl_quote, reporting_currency, "
            "fx_rate_entry, fx_rate_exit, updated_at) VALUES ('t-1', 'run-a', 7, "
            "'SOL/USD', 'SOL', 'USD', 'long', '1.00000000', '100.00', '103.00', '0.22', "
            "'0.39', 1000, 2000, 'target', '2.39', '0.0239', '2.39', 'USD', '1', '1', 2000)"
        )
        conn.execute(
            "INSERT INTO runs (run_id, mode, started_at, updated_at) "
            "VALUES ('run-a', 'replay', 1, 1)"
        )
    finally:
        close_connection(conn)

    (staged / sixth.name).write_bytes(sixth.read_bytes())
    assert apply_migrations(db_path, migrations_dir=staged) == [6]

    with StoreClient(db_path) as store:
        (trade,) = store.recent_closed_trades(5)
        (run,) = store.latest_runs(5)
        assert store.approval(11) is None, "nothing was inferred into approvals"
        # Spec 145: the table 0006 creates carries `details`, nullable, and an approval
        # written without one reads back absent.
        details_column = {
            row["name"]: row for row in store.connection.execute("PRAGMA table_info(approvals)")
        }["details"]
        assert details_column["notnull"] == 0 and details_column["dflt_value"] is None
        store.write_approval(_approval(details=None))
        written = store.approval(11)
        assert written is not None and written.details is None

    for name in TRADE_FIELDS:
        assert getattr(trade, name) is None, f"trades.{name} read {getattr(trade, name)!r}"
    for name in RUN_FIELDS:
        assert getattr(run, name) is None, f"runs.{name} read {getattr(run, name)!r}"
    # 0006 touched no existing money.
    assert format(trade.realised_pnl, "f") == "2.39"
    assert format(trade.entry_price, "f") == "100.00"


def test_the_seeded_database_carried_across_0006_reads_every_new_field_as_absent(
    tmp_path: Path,
) -> None:
    """Migrate-from-seed. The Phase 0 seed's every trade and run, copied into a database
    that stops at 0005, migrates to 0006. Every row then reads the new fields as absent,
    and every column it already had is byte-for-byte the same.

    The seed writes at the latest schema, so its rows are copied across on the columns
    they share with 0005. That is the one way to hold real seeded rows in a database older
    than the migration under test.
    """
    seeded = seed_database(tmp_path / "seeded.sqlite")
    staged, db_path, sixth = _staged_before_0006(tmp_path)

    source = sqlite3.connect(seeded.db_path)
    target = sqlite3.connect(db_path)
    copied: dict[str, list[tuple[Any, ...]]] = {}
    try:
        for table in ("runs", "trades"):
            shared = [row[1] for row in target.execute(f"PRAGMA table_info({table})")]
            rows = source.execute(
                f"SELECT {', '.join(shared)} FROM {table} ORDER BY rowid"
            ).fetchall()
            assert rows, f"the seed wrote no {table}; this test would prove nothing"
            target.executemany(
                f"INSERT INTO {table} ({', '.join(shared)}) "
                f"VALUES ({', '.join('?' for _ in shared)})",
                rows,
            )
            copied[table] = rows
        target.commit()
    finally:
        source.close()
        target.close()

    (staged / sixth.name).write_bytes(sixth.read_bytes())
    assert apply_migrations(db_path, migrations_dir=staged) == [6]

    with StoreClient(db_path) as store:
        trades = store.recent_closed_trades(10_000)
        runs = store.latest_runs(10_000)
    assert len(trades) == len(copied["trades"])
    assert len(runs) == len(copied["runs"])
    for trade in trades:
        assert all(getattr(trade, name) is None for name in TRADE_FIELDS), trade.trade_id
    for run in runs:
        assert all(getattr(run, name) is None for name in RUN_FIELDS), run.run_id

    check = sqlite3.connect(db_path)
    try:
        for table, before in copied.items():
            shared = [row[1] for row in check.execute(f"PRAGMA table_info({table})")][
                : len(before[0])
            ]
            after = check.execute(
                f"SELECT {', '.join(shared)} FROM {table} ORDER BY rowid"
            ).fetchall()
            assert after == before, f"0006 changed an existing {table} value"
    finally:
        check.close()


# --------------------------------------------------------------------------- #
# 2. Every new field round-trips exactly
# --------------------------------------------------------------------------- #


def test_an_approval_round_trips_every_field_to_the_quantum(store: StoreClient) -> None:
    written = _approval()
    store.write_approval(written)

    read = store.approval(11)

    assert read == written
    assert read is not None
    for name, value in ECONOMIC_VALUES.items():
        assert format(getattr(read, name), "f") == value, name
    for name, value in RUN_ID_VALUES.items():
        assert getattr(read, name) == value, name
    assert read.details == DETAILS, "the snapshot must come back byte for byte"
    assert (read.run_id, read.cycle_id, read.ts, read.pair) == ("run-a", 3, 900, "SOL/USD")
    assert store.approval(12) is None, "an unknown userref is None, not another row"


def test_an_approval_with_nothing_recorded_reads_back_absent(store: StoreClient) -> None:
    """Spec 133's scope limit. A placing tick whose economics were absent records them as
    absent, and the store gives back `None` rather than a zero or a blank."""
    store.write_approval(
        _approval(**dict.fromkeys((*TRADE_FIELDS, "details")))
    )
    read = store.approval(11)
    assert read is not None
    assert read.details is None
    assert all(getattr(read, name) is None for name in TRADE_FIELDS)


def test_a_trade_round_trips_its_approval_economics_to_the_quantum(store: StoreClient) -> None:
    written = _trade(
        **{name: Decimal(value) for name, value in ECONOMIC_VALUES.items()},
        **RUN_ID_VALUES,
    )
    store.write_trade(written)

    (read,) = store.recent_closed_trades(5)

    assert read == written
    for name, value in ECONOMIC_VALUES.items():
        assert format(getattr(read, name), "f") == value, name
    for name, value in RUN_ID_VALUES.items():
        assert getattr(read, name) == value, name


def test_a_run_round_trips_its_scenario(store: StoreClient) -> None:
    store.start_run(
        "run-replay",
        mode="replay",
        started_at=1_000,
        scenario_digest="sha256:abc123",
        scenario_description="fee tier 3; bucket table v1 (declared); folds 379-404",
    )
    store.start_run("run-paper", mode="paper", started_at=2_000)

    by_id = {run.run_id: run for run in store.latest_runs(5)}

    assert by_id["run-replay"].scenario_digest == "sha256:abc123"
    assert by_id["run-replay"].scenario_description == (
        "fee tier 3; bucket table v1 (declared); folds 379-404"
    )
    assert by_id["run-paper"].scenario_digest is None
    assert by_id["run-paper"].scenario_description is None


# --------------------------------------------------------------------------- #
# 3. A float is refused, at the boundary and by the database
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", ECONOMICS)
def test_a_float_economic_is_refused_by_both_row_models(name: str) -> None:
    with pytest.raises(ValidationError, match="money must never be a float"):
        _approval(**{name: 0.0184})
    with pytest.raises(ValidationError, match="money must never be a float"):
        _trade(**{name: 0.0184})


@pytest.mark.parametrize(("table", "name"), [(t, n) for t in ("approvals", "trades") for n in ECONOMICS])
def test_a_float_economic_is_refused_by_the_database(
    store: StoreClient, table: str, name: str
) -> None:
    """Behind the model, the schema refuses a float too, so hand-written SQL cannot store
    one either. The row exists first, so the refusal is the CHECK and not a missing row."""
    if table == "approvals":
        store.write_approval(_approval())
        key = "userref = 11"
    else:
        store.write_trade(_trade())
        key = "trade_id = 't-1'"
    with pytest.raises(sqlite3.IntegrityError, match=f"typeof\\({name}\\)"):
        store.connection.execute(f"UPDATE {table} SET {name} = ? WHERE {key}", (0.0184,))


# --------------------------------------------------------------------------- #
# Write-once, and blank is not absent
# --------------------------------------------------------------------------- #


def test_a_second_approval_for_one_entry_is_refused(store: StoreClient) -> None:
    """The approval is a fact about the placing tick. An upsert would let a later tick
    rewrite `cycle_id` and the economics, which is the overwrite `orders` suffers and the
    reason the table exists."""
    store.write_approval(_approval())

    with pytest.raises(sqlite3.IntegrityError, match=r"UNIQUE|PRIMARY"):
        store.write_approval(_approval(cycle_id=9, expected_move_pct=Decimal("0.5")))

    read = store.approval(11)
    assert read is not None
    assert read.cycle_id == 3
    assert format(read.expected_move_pct or Decimal(0), "f") == "0.01840"


def test_write_run_never_erases_a_runs_scenario(store: StoreClient) -> None:
    """`start_run` is the scenario's one writer. A shutdown `write_run` built from a
    `RunRow` that never carried it leaves it exactly as it was."""
    store.start_run(
        "run-replay", mode="replay", started_at=1_000, scenario_digest="sha256:abc123",
        scenario_description="declared scenario",
    )
    store.write_run(
        RunRow(run_id="run-replay", mode=RunMode.REPLAY, started_at=1_000, ended_at=5_000,
               updated_at=5_000)
    )
    store.write_run(
        RunRow(run_id="run-replay", mode=RunMode.REPLAY, started_at=1_000, ended_at=6_000,
               updated_at=6_000, scenario_digest="sha256:other")
    )

    (run,) = store.latest_runs(1)
    assert run.ended_at == 6_000, "the shutdown write itself landed"
    assert run.scenario_digest == "sha256:abc123"
    assert run.scenario_description == "declared scenario"


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_scenario_is_refused_rather_than_stored_as_a_placeholder(
    store: StoreClient, blank: str
) -> None:
    for name in RUN_FIELDS:
        with pytest.raises(StoreError, match=f"{name} is a value or None"):
            store.start_run("run-x", mode="replay", started_at=1, **{name: blank})
    assert store.latest_runs(5) == ()
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        store.connection.execute(
            "INSERT INTO runs (run_id, mode, started_at, updated_at, scenario_digest) "
            "VALUES ('run-y', 'replay', 1, 1, ?)",
            (blank,),
        )


@pytest.mark.parametrize("name", RUN_IDS)
def test_a_blank_model_run_id_is_refused_by_models_and_database(
    store: StoreClient, name: str
) -> None:
    with pytest.raises(ValidationError, match="a model run id is a value or None"):
        _approval(**{name: " "})
    with pytest.raises(ValidationError, match="a model run id is a value or None"):
        _trade(**{name: ""})
    store.write_approval(_approval())
    store.write_trade(_trade())
    for table, key in (("approvals", "userref = 11"), ("trades", "trade_id = 't-1'")):
        with pytest.raises(sqlite3.IntegrityError, match=f"CHECK constraint failed: {name}"):
            store.connection.execute(f"UPDATE {table} SET {name} = ' ' WHERE {key}")


@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_approval_details_is_refused_by_model_and_database(
    store: StoreClient, blank: str
) -> None:
    """Spec 145. `None` says the snapshot was not recorded, and a blank string says nothing."""
    with pytest.raises(ValidationError, match="an approval's details is a value or None"):
        _approval(details=blank)
    store.write_approval(_approval())
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed: details"):
        store.connection.execute("UPDATE approvals SET details = ? WHERE userref = 11", (blank,))
