"""Spec 131 end to end: `acsoe research backtest` over the registered chains, no double.

The real dispatcher, config loader, replay client, paper broker, store, `bootstrap.py`
chains and `core/` orchestrator, over fabricated partitions and fabricated fold run
directories. The run directories hold a manifest and nothing else, so engines 13, 8 and
15 refuse on every bar, as a fresh clone's would. That is enough to prove what this spec
owns: that the driver ticks the chain deterministically, that a killed run resumes to the
same rows, and that a position keeps the minute ticks coming. The economics, with real
models, are spec 142's rehearsal.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import yaml
from tests.clients.kraken.replay_fixtures import FEE_FIXTURE, REPO, WEEK_0, write_scenario

from acsoe.cli import main as cli_main

BAR = 900
DAY = 86400
#: Fold 379 is the second partition week; the run below takes its first hours.
FOLD_START = WEEK_0 + 7 * DAY
BEGIN = FOLD_START + 3 * DAY
UNTIL = BEGIN + 3 * 3600

#: Columns that differ between two processes by construction, never by decision.
PROCESS_COLUMNS = frozenset({"id", "run_id", "cycle_id", "claimed_by_run_id", "created_by_run_id"})
#: Two clean runs are separate databases, so each names its run differently; nothing
#: else may differ between them, row ids and tick numbers included.
RUN_COLUMNS = frozenset({"run_id", "claimed_by_run_id", "created_by_run_id"})


def steady(price: str, qty: str, start: int, end: int, every: int) -> list[tuple[int, str, str]]:
    return [(ts, price, qty) for ts in range(start, end, every)]


def trades(
    thin_crash_at: int | None = None, thin_dip_at: int | None = None
) -> dict[str, list[tuple[int, str, str]]]:
    start, end = WEEK_0 + 60, WEEK_0 + 3 * 7 * DAY
    thin = steady("100", "5", start, end, 300)
    if thin_crash_at is not None:
        thin = [row if row[0] < thin_crash_at else (row[0], "97", "5") for row in thin]
    if thin_dip_at is not None:
        # One print through the stop and straight back: only a trade range sees it.
        thin = sorted([*thin, (thin_dip_at, "97", "1"), (thin_dip_at + 10, "100", "1")])
    return {
        "XBTUSD": steady("50000", "0.01", start, end, 60),
        "ETHUSD": steady("3000", "0.2", start + 20, end, 60),
        "THINUSD": thin,
    }


def write_run(
    tmp_path: Path, *, thin_crash_at: int | None = None, thin_dip_at: int | None = None
) -> Path:
    """The scenario, a YAML config carrying its `replay:` section, and fold 379's run dir."""
    scenario = write_scenario(tmp_path, trades(thin_crash_at, thin_dip_at))
    raw = yaml.safe_load((REPO / "config" / "default.yaml").read_text(encoding="utf-8"))
    replay = copy.deepcopy(scenario.config.get("replay").model_dump())
    raw["replay"] = replay
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    run_dir = tmp_path / "models" / "test-f379-p7"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"fold": {"fold_index": 379, "test_start_ts": FOLD_START, "test_end_ts": FOLD_START + 7 * DAY}}),
        encoding="utf-8",
    )
    assert FEE_FIXTURE.is_file()
    return config_path


def backtest(config: Path, db: Path, *extra: str) -> int:
    return cli_main.main(
        ["--config", str(config), "research", "backtest", "--db", str(db),
         "--begin", _iso(BEGIN), "--until", _iso(UNTIL), "--ranking", "alphabetical", *extra]
    )


def _iso(moment: int) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(moment, UTC).isoformat()


def rows(db: Path, *, drop: frozenset[str] = RUN_COLUMNS) -> dict[str, list[tuple[Any, ...]]]:
    """Every decision table, each row minus `drop`, sorted, so two databases compare."""
    connection = sqlite3.connect(db)
    try:
        # Run identity differs between databases and processes by construction (each
        # process names its own run), and a SHAP reference or a detail can carry it in
        # text, so every run id of this database is replaced by one placeholder.
        run_ids = [str(row[0]) for row in connection.execute("SELECT run_id FROM runs")]

        def neutral(value: Any) -> Any:
            if isinstance(value, str):
                for run_id in run_ids:
                    value = value.replace(run_id, "<run>")
            return value

        dumped: dict[str, list[tuple[Any, ...]]] = {}
        for table in ("rejections", "block_records", "equity_snapshots", "orders", "positions", "trades"):
            cursor = connection.execute(f"SELECT * FROM {table}")
            names = [column[0] for column in cursor.description]
            keep = [index for index, name in enumerate(names) if name not in drop]
            dumped[table] = sorted(
                (tuple(neutral(row[index]) for index in keep) for row in cursor.fetchall()), key=repr
            )
        return dumped
    finally:
        connection.close()


def ticks(db: Path) -> list[dict[str, Any]]:
    record = db.with_name(db.name + ".runrecord.jsonl")
    return [
        entry
        for entry in (json.loads(line) for line in record.read_text(encoding="utf-8").splitlines())
        if entry["event"] == "tick"
    ]


def plant_position(db: Path) -> None:
    """An open THIN/USD position, stop 98.5, and the filled entry order it came from."""
    from acsoe.clients.store.client import StoreClient
    from acsoe.clients.store.contracts import (
        OrderIntent,
        OrderRow,
        OrderSide,
        OrderStatus,
        OrderType,
        PositionRow,
        PositionStatus,
    )

    db.parent.mkdir(parents=True, exist_ok=True)
    store = StoreClient(db)
    store.migrate()
    placed = (BEGIN - BAR) * 1_000_000
    store.write_order(
        OrderRow(
            userref=1001, order_id="paper-1001", run_id="planted", cycle_id=1,
            position_id="planted-1", pair="THIN/USD", side=OrderSide.BUY,
            intent=OrderIntent.ENTRY, order_type=OrderType.LIMIT, oflags="post",
            status=OrderStatus.FILLED, qty="10", limit_price="100", filled_qty="10",
            avg_fill_price="100", fee="2.2", placed_at=placed, closed_at=placed,
            updated_at=placed,
        )
    )
    store.write_position(
        PositionRow(
            position_id="planted-1", run_id="planted", cycle_id=1, pair="THIN/USD", base="THIN",
            quote="USD", status=PositionStatus.OPEN, qty="10", entry_price="100",
            target_price="103", stop_price="98.5", timeout_at=(BEGIN + DAY) * 1_000_000,
            entry_userref=1001, opened_at=placed, updated_at=placed,
        )
    )
    store.close()


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_two_clean_runs_write_identical_rows(workdir: Path) -> None:
    config = write_run(workdir)
    assert backtest(config, workdir / "data" / "db" / "a.sqlite") == 0
    assert backtest(config, workdir / "data" / "db" / "b.sqlite") == 0
    first, second = rows(workdir / "data" / "db" / "a.sqlite"), rows(workdir / "data" / "db" / "b.sqlite")
    assert first == second
    # Each database names its own run, so four runs over one window never share a
    # `run_id` (engine 19's SHAP files are keyed by it under one shared directory).
    names = []
    for db in ("a", "b"):
        connection = sqlite3.connect(workdir / "data" / "db" / f"{db}.sqlite")
        try:
            names.append(connection.execute("SELECT run_id FROM runs").fetchone()[0])
        finally:
            connection.close()
    assert names[0] != names[1]
    assert names[0].startswith("replay-a-")
    # Something was recorded on every tick. Engine 7 cannot size on the first (no equity
    # row exists yet, as on any fresh run), and from the second on the chain reaches
    # engine 13, which cannot load a manifest-only run directory and errors: one
    # `engine_errored` block record per bar (invariant 12).
    errored = [row for row in rows(workdir / "data" / "db" / "a.sqlite")["block_records"] if "anomaly" in row]
    assert len(errored) == 12
    assert len(first["equity_snapshots"]) == 13
    assert [entry["bar_tick"] for entry in ticks(workdir / "data" / "db" / "a.sqlite")] == [True] * 13


def test_the_runs_row_is_written_in_replay_mode(workdir: Path) -> None:
    config = write_run(workdir)
    db = workdir / "data" / "db" / "a.sqlite"
    assert backtest(config, db) == 0
    connection = sqlite3.connect(db)
    try:
        modes = connection.execute("SELECT mode FROM runs").fetchall()
    finally:
        connection.close()
    assert modes == [("replay",)]


def test_a_killed_run_resumed_writes_the_uninterrupted_rows(workdir: Path) -> None:
    config = write_run(workdir)
    whole, split = workdir / "data" / "db" / "whole.sqlite", workdir / "data" / "db" / "split.sqlite"
    assert backtest(config, whole) == 0
    assert backtest(config, split, "--max-ticks", "5") == 0
    assert backtest(config, split, "--resume") == 0
    assert rows(whole, drop=PROCESS_COLUMNS) == rows(split, drop=PROCESS_COLUMNS)
    assert [entry["tick_s"] for entry in ticks(whole)] == [entry["tick_s"] for entry in ticks(split)]


def test_a_second_run_into_one_database_is_refused(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_run(workdir)
    db = workdir / "data" / "db" / "a.sqlite"
    assert backtest(config, db) == 0
    assert backtest(config, db) == 2
    assert "a run never shares one" in capsys.readouterr().err


def test_a_run_without_a_database_is_refused(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = write_run(workdir)
    assert cli_main.main(["--config", str(config), "research", "backtest"]) == 2
    assert "--db is required" in capsys.readouterr().err


def test_a_planted_position_brings_minute_ticks_until_its_stop_exits_it(workdir: Path) -> None:
    """A THIN/USD position planted before the run, with its stop at 98.5. THIN trades at
    100 until the crash, then at 97. The driver ticks every minute from the first bar
    close while the position is open, the chain's own engines 21 and 22 exit it at the
    stop, and from the next bar on the run is bar closes only."""
    crash = BEGIN + 20 * 60
    config = write_run(workdir, thin_crash_at=crash)
    db = workdir / "data" / "db" / "planted.sqlite"
    plant_position(db)
    assert backtest(config, db, "--resume") == 0
    record = ticks(db)
    stamps = [entry["tick_s"] for entry in record]
    exits = [entry["tick_s"] for entry in record if not entry["exposed_after"]]
    exited = exits[0]
    assert crash <= exited <= crash + 5 * 60
    # Every minute from the first tick to the exit, then bar closes only.
    assert stamps[: stamps.index(exited) + 1] == list(range(stamps[0], exited + 60, 60))
    assert all(stamp % BAR == 0 for stamp in stamps[stamps.index(exited) + 1 :])


def test_a_run_killed_with_a_position_open_resumes_to_the_same_exit(workdir: Path) -> None:
    """Killed on the minute before the stop is touched, with the position open. THIN
    prints once at 97, through the stop, and straight back to 100 inside that minute, so
    only the trade range can see it. The uninterrupted run exits on that minute; the
    resumed one must too."""
    config = write_run(workdir, thin_dip_at=BEGIN + 20 * 60 + 30)
    whole, split = workdir / "data" / "db" / "whole.sqlite", workdir / "data" / "db" / "split.sqlite"
    for db in (whole, split):
        plant_position(db)
    assert backtest(config, whole, "--resume") == 0
    assert backtest(config, split, "--resume", "--max-ticks", "21") == 0
    assert backtest(config, split, "--resume") == 0
    assert [entry["tick_s"] for entry in ticks(whole)] == [entry["tick_s"] for entry in ticks(split)]
    assert rows(whole, drop=PROCESS_COLUMNS) == rows(split, drop=PROCESS_COLUMNS)


def test_a_planted_resting_entry_brings_minute_ticks_until_its_window_cancels_it(workdir: Path) -> None:
    """A post-only buy resting below the market: exposure too (spec 131 step 1 names a
    resting entry as well as an open position). Engine 21 cancels it at
    `trading.entry_unfilled_window_s`, and the minute ticks stop with it."""
    from acsoe.clients.store.client import StoreClient
    from acsoe.clients.store.contracts import (
        OrderIntent,
        OrderRow,
        OrderSide,
        OrderStatus,
        OrderType,
    )

    config = write_run(workdir)
    db = workdir / "data" / "db" / "resting.sqlite"
    db.parent.mkdir(parents=True)
    store = StoreClient(db)
    store.migrate()
    placed = BEGIN * 1_000_000
    store.write_order(
        OrderRow(
            userref=2002, run_id="planted", cycle_id=1, pair="THIN/USD", side=OrderSide.BUY,
            intent=OrderIntent.ENTRY, order_type=OrderType.LIMIT, oflags="post",
            status=OrderStatus.RESTING, qty="10", limit_price="90", filled_qty="0",
            placed_at=placed, updated_at=placed,
        )
    )
    store.close()
    assert backtest(config, db, "--resume") == 0
    record = ticks(db)
    stamps = [entry["tick_s"] for entry in record]
    first_flat = next(entry["tick_s"] for entry in record if not entry["exposed_after"])
    assert first_flat == BEGIN + 300
    assert stamps[:6] == list(range(BEGIN, BEGIN + 360, 60))
    assert all(stamp % BAR == 0 for stamp in stamps[6:])


def test_each_fold_config_points_all_three_model_keys_at_the_fold(workdir: Path) -> None:
    from acsoe.cli.research import fold_config
    from acsoe.platform.config import derive_config, load_config
    from acsoe.research.backtest import FoldWindow

    base = derive_config(load_config(REPO / "config" / "default.yaml", load_env=False), {"mode": "replay"})
    built = fold_config(base, FoldWindow(fold=381, run_id="r-f381-p7", test_start_s=0, test_end_s=1))
    assert [built.get(f"models.{name}_run_id") for name in ("prediction", "anomaly", "skeptic")] == [
        "r-f381-p7"
    ] * 3
    assert base.get("models.prediction_run_id") is None


def test_a_resume_starts_after_the_later_of_the_run_record_and_the_store(workdir: Path) -> None:
    """A tick can reach the run record without an equity or block row (a position with no
    mark writes no equity row), and a tick can reach the store without its record line (a
    kill between engine 19's commit and the append). The later of the two is never re-run."""
    from acsoe.cli.research import _last_recorded_tick_s
    from acsoe.clients.store.client import StoreClient

    config = write_run(workdir)
    db = workdir / "data" / "db" / "a.sqlite"
    assert backtest(config, db, "--max-ticks", "3") == 0
    store = StoreClient(db)
    try:
        record = db.with_name(db.name + ".runrecord.jsonl")
        last = _last_recorded_tick_s(store, record)
        assert last == BEGIN + 2 * BAR
        with record.open("a", encoding="utf-8", newline=chr(10)) as handle:
            handle.write(json.dumps({"event": "tick", "tick_s": BEGIN + 3 * BAR}) + chr(10))
        assert _last_recorded_tick_s(store, record) == BEGIN + 3 * BAR
        assert _last_recorded_tick_s(store, workdir / "absent.jsonl") == BEGIN + 2 * BAR
    finally:
        store.close()


def test_the_committed_rehearsal_day_replays_to_identical_rows_twice(workdir: Path) -> None:
    """Spec 131's first check, on spec 142's committed day, with the real recorded rules,
    the committed bucket table and fee schedule, and every partition of the day's slice.
    Two bar ticks per run keep it to seconds; `scripts/rehearse_replay_day.py` runs the
    whole day. The run directory holds a manifest only, so the chain stops at engine 13."""
    day = REPO / "tests" / "fixtures" / "phase7" / "rehearsal_2024-10-20"
    raw = yaml.safe_load((REPO / "config" / "default.yaml").read_text(encoding="utf-8"))
    fixtures = REPO / "tests" / "fixtures"
    raw["replay"] = {
        "asset_pairs_file": (fixtures / "kraken" / "asset_pairs_recorded_2026-09-19.json").as_posix(),
        "instrument_file": (fixtures / "kraken" / "instrument_recorded_2026-09-19.json").as_posix(),
        "pair_names_file": (fixtures / "kraken" / "pair_names_recorded_2026-09-19.json").as_posix(),
        "spread_table_file": (fixtures / "replay" / "spread_book_table_2026-09-19.json").as_posix(),
        "fee_schedule_file": FEE_FIXTURE.as_posix(),
        "fee_tier": 3,
        "partitions_dir": day.as_posix(),
        "first_fold": 394,
        "last_fold": 394,
        "run_id_format": "rehearsal-f{fold}",
    }
    config = workdir / "config.yaml"
    config.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    fold_start = 1729296000  # 2024-10-19 00:00 UTC, fold 394's test week
    run_dir = workdir / "models" / "rehearsal-f394"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"fold": {"fold_index": 394, "test_start_ts": fold_start, "test_end_ts": fold_start + 7 * DAY}}),
        encoding="utf-8",
    )
    dbs = [workdir / "data" / "db" / name for name in ("a.sqlite", "b.sqlite")]
    for db in dbs:
        assert cli_main.main(
            ["--config", str(config), "research", "backtest", "--db", str(db), "--ranking", "alphabetical",
             "--begin", "2024-10-20T00:00:00", "--until", "2024-10-20T00:15:00"]
        ) == 0
    first, second = rows(dbs[0]), rows(dbs[1])
    assert first == second
    assert len(first["equity_snapshots"]) == 2


def test_a_replay_runs_store_can_write_shap_under_the_derived_root(workdir: Path) -> None:
    """Launch precondition 1: the store a replay run uses has the derived root, so engine
    19's SHAP writes land rather than being refused."""
    from acsoe.cli.research import replay_store
    from acsoe.platform.paths import ensure_runtime_directories

    paths = ensure_runtime_directories(workdir)
    store = replay_store(workdir / "data" / "db" / "shap.sqlite", paths)
    try:
        assert store.derived_dir == paths.derived
        ref = store.write_shap(
            run_id="replay-shap-test", cycle_id=1, ts=BEGIN * 1_000_000, pair="THIN/USD",
            model_run_id="run-x", contributions={"log_return_4": 0.25, "range_atr_4": -0.1},
        )
    finally:
        store.close()
    written = list((paths.derived / "shap").rglob("*.parquet"))
    assert len(written) == 1
    assert "replay-shap-test" in ref
