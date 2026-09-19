"""Spec 142's two scripts: the day cutter and the rehearsal's recomputation.

`scripts/cut_replay_fixture.py` copies a day's trades out of the partitions byte for byte.
`scripts/rehearse_replay_day.py` recomputes friction from the fixtures alone, and that
recomputation is only worth anything if it agrees with the chain when the chain is right
and disagrees when it is wrong. So it is checked here against the real replay client and
engine 9's real walk, and a planted wrong balance must break the agreement.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import ModuleType

import polars as pl
import pytest

from acsoe.clients.kraken.replay import ReplayKrakenClient
from acsoe.engines.order_book.contracts import walk_the_bid_side
from acsoe.engines.scout.contracts import ScoutUniverse
from acsoe.platform.clock import FixedClock
from tests.clients.kraken.replay_fixtures import FEE_FIXTURE, WEEK_0, write_scenario

REPO = Path(__file__).resolve().parents[2]
NOW = WEEK_0 + 10 * 86400 + 12 * 3600


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"acsoe_script_{name}", REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cutter() -> ModuleType:
    return load("cut_replay_fixture")


@pytest.fixture(scope="module")
def rehearsal() -> ModuleType:
    return load("rehearse_replay_day")


def _source(tmp_path: Path) -> Path:
    """Two partition weeks in spec 128's layout, with a manifest listing them."""
    source = tmp_path / "partitions"
    weeks = [WEEK_0, WEEK_0 + 7 * 86400]
    rows = {
        "XBTUSD": [(WEEK_0 + 100, "1.0", "2"), (WEEK_0 + 7 * 86400 + 5, "3.00", "4"), (WEEK_0 + 7 * 86400 + 5, "2.99", "1")],
        "THINUSD": [(WEEK_0 + 50, "7", "1")],
    }
    manifest = {
        "week_starts": [datetime.fromtimestamp(week, UTC).strftime("%Y-%m-%d") for week in weeks],
        "columns": {"ts": "int64", "price": "text", "volume": "text"},
        "row_order": "source file order",
        "pairs": {},
    }
    for pair, trades in rows.items():
        counts = {}
        for week in weeks:
            label = datetime.fromtimestamp(week, UTC).strftime("%Y-%m-%d")
            inside = [row for row in trades if week <= row[0] < week + 7 * 86400]
            counts[label] = len(inside)
            if inside:
                (source / pair).mkdir(parents=True, exist_ok=True)
                pl.DataFrame(
                    {"ts": [r[0] for r in inside], "price": [r[1] for r in inside], "volume": [r[2] for r in inside]},
                    schema={"ts": pl.Int64, "price": pl.Utf8, "volume": pl.Utf8},
                ).write_parquet(source / pair / f"{label}.parquet")
        manifest["pairs"][pair] = {"weeks": counts}
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return source


def test_the_cut_keeps_the_span_byte_for_byte_and_in_file_order(cutter: ModuleType, tmp_path: Path) -> None:
    source = _source(tmp_path)
    out = tmp_path / "day"
    # The start falls exactly on THIN's one trade (kept: the start is inclusive) and after
    # nothing else of THIN's; the end falls one second after XBT's last two (kept) and the
    # bound is exclusive.
    start = datetime.fromtimestamp(WEEK_0 + 50, UTC)
    end = datetime.fromtimestamp(WEEK_0 + 7 * 86400 + 6, UTC)
    written = cutter.cut(source, out, start=start, end=end)
    assert written["total_rows"] == 4
    assert written["pairs"]["XBTUSD"]["total_rows"] == 3
    assert written["pairs"]["THINUSD"]["total_rows"] == 1
    later = cutter.cut(source, tmp_path / "later", start=datetime.fromtimestamp(WEEK_0 + 51, UTC), end=end)
    assert "THINUSD" not in later["pairs"]
    second = pl.read_parquet(out / "XBTUSD" / datetime.fromtimestamp(WEEK_0 + 7 * 86400, UTC).strftime("%Y-%m-%d.parquet"))
    assert second["price"].to_list() == ["3.00", "2.99"]


def test_the_cut_refuses_an_existing_fixture_and_a_start_before_the_partitions(
    cutter: ModuleType, tmp_path: Path
) -> None:
    source = _source(tmp_path)
    start = datetime.fromtimestamp(WEEK_0, UTC)
    end = start + timedelta(days=1)
    cutter.cut(source, tmp_path / "day", start=start, end=end)
    with pytest.raises(SystemExit, match="written once"):
        cutter.cut(source, tmp_path / "day", start=start, end=end)
    with pytest.raises(SystemExit, match="do not reach back"):
        cutter.cut(source, tmp_path / "other", start=start - timedelta(days=1), end=end)


def test_the_recomputed_friction_agrees_with_the_chain_and_a_wrong_balance_breaks_it(
    rehearsal: ModuleType, tmp_path: Path
) -> None:
    """The rehearsal's exact-rational friction against the replay client's served spread and
    engine 9's own walk at the same balance: equal. The same recomputation at a balance off
    by one dollar: not equal. So the check can fail."""
    trades = {"THINUSD": [(NOW - 3600, "100", "30"), (NOW - 60, "101", "40")]}
    scenario = write_scenario(tmp_path, trades)
    client = ReplayKrakenClient.from_config(scenario.config, clock=FixedClock(datetime.fromtimestamp(NOW, UTC)), root=scenario.root)
    book = asyncio.run(client.order_book("THIN/USD", 10))
    quote = client.latest_quote("THIN/USD")
    assert quote is not None
    walk = walk_the_bid_side(book.bids, Decimal(5000))
    assert walk is not None
    fee = asyncio.run(client.trade_volume())
    chain = (
        Fraction(fee.maker_fee_pct) + Fraction(fee.taker_fee_pct)
        + Fraction((quote.ask - quote.bid) / ((quote.ask + quote.bid) / 2))
        + Fraction(walk.slippage_pct)
    )

    replay = scenario.config.get("replay")
    fixture = rehearsal.Fixture(
        Path(replay.partitions_dir), Path(replay.spread_table_file), FEE_FIXTURE,
        Path(replay.pair_names_file), 3,
    )
    friction, _spread, _slippage = fixture.friction("THIN/USD", NOW, Fraction(5000))
    assert rehearsal.close(friction, chain)
    wrong, _, _ = fixture.friction("THIN/USD", NOW, Fraction(4999))
    assert not rehearsal.close(wrong, chain)


def test_the_ledger_balance_counts_only_fills_closed_by_then(rehearsal: ModuleType) -> None:
    orders = [
        {"status": "filled", "closed_at": 100, "avg_fill_price": "10", "filled_qty": "2", "fee": "0.1", "intent": "entry"},
        {"status": "filled", "closed_at": 200, "avg_fill_price": "11", "filled_qty": "2", "fee": "0.2", "intent": "exit"},
        {"status": "cancelled", "closed_at": 150, "avg_fill_price": None, "filled_qty": "0", "fee": None, "intent": "entry"},
    ]
    assert rehearsal.usd_balance_at(orders, 99, Fraction(1000)) == 1000
    assert rehearsal.usd_balance_at(orders, 100, Fraction(1000)) == Fraction(1000) - 20 - Fraction(1, 10)
    assert rehearsal.usd_balance_at(orders, 200, Fraction(1000)) == (
        Fraction(1000) - 20 - Fraction(1, 10) + 22 - Fraction(2, 10)
    )


def test_the_tree_digest_moves_when_source_a_migration_or_a_model_file_changes(
    rehearsal: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rehearsal's guard against a shared checkout changing under it mid-run."""
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "db" / "migrations").mkdir(parents=True)
    model = tmp_path / "models" / "run-f1"
    model.mkdir(parents=True)
    source, migration, artefact = (
        tmp_path / "src" / "pkg" / "a.py", tmp_path / "db" / "migrations" / "0001.sql", model / "model.txt",
    )
    for path in (source, migration, artefact):
        path.write_text("one", encoding="utf-8")
    monkeypatch.setattr(rehearsal, "REPO", tmp_path)
    before = rehearsal.tree_digest([model])
    assert rehearsal.tree_digest([model]) == before
    for path in (source, migration, artefact):
        path.write_text("two", encoding="utf-8")
        after = rehearsal.tree_digest([model])
        assert after != before
        before = after


def test_a_grid_difference_above_the_cost_bar_is_a_stop_and_below_it_is_explained(
    rehearsal: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lead's ruling on F6: a disagreement or tie in which either pick clears the cost
    bar at the run's tier is a stop; one confined to pairs below it is listed, not a stop.
    `grid_order` is replaced here because its inputs live under `data/`."""
    from types import SimpleNamespace

    import acsoe.research.ranking_check as check

    order = [SimpleNamespace(pair="EURUSD", expected_move_pct=0.004655),
             SimpleNamespace(pair="XBTUSD", expected_move_pct=0.004655)]
    monkeypatch.setattr(check, "grid_order", lambda *_a, **_k: (394, order))
    names = tmp_path / "names.json"
    names.write_text(json.dumps({"pairs": {"EURUSD": {"v2_symbol": "EUR/USD"}, "XBTUSD": {"v2_symbol": "BTC/USD"}}}),
                     encoding="utf-8")
    log = tmp_path / "scout.jsonl"
    log.write_text(json.dumps({
        "bar_ts": 1729443600, "universe": ["BTC/USD", "EUR/USD"], "candidate": "BTC/USD",
        "ranked": [{"pair": "BTC/USD", "expected_move_pct": "0.004654988"}],
    }) + "\n", encoding="utf-8")

    class Config:
        def get(self, key: str) -> object:
            return {"trading.hurdle_multiple": "1.5", "prediction.di_percentile": 0.99,
                    "anomaly.threshold_percentile": 0.99}[key]

    below = rehearsal.ranking_check(log, Config(), names, fee_round_trip=Fraction(6, 1000))
    assert (below["agree"], len(below["tie_broken_by_name_spelling"]), below["stops"]) == (0, 1, [])
    above = rehearsal.ranking_check(log, Config(), names, fee_round_trip=Fraction(1, 1000))
    assert [stop["engine"] for stop in above["stops"]] == ["BTC/USD"]


MIGRATION_0007 = REPO / "db" / "migrations" / "0007_tick_tallies.sql"
TALLY_JSON = ("pairs", "excluded", "rank_skipped", "ranked", "rank_run_ids")
BAR_S = 1_729_382_400


def scout_ticks() -> list[tuple[int, str, dict[str, object]]]:
    """Four ticks as engine 7 publishes them: a candidate, no candidate, a block, an error."""
    chosen = ScoutUniverse(
        pairs=("BTC/USD", "ETH/USD"), scanned=3, excluded={"stale_quote": 1}, equity=Decimal("1000"),
        candidate="ETH/USD", rank_feature="expected_move", ranked=(("ETH/USD", Decimal("0.031")),
        ("BTC/USD", Decimal("0.004"))), rank_run_ids={"target": "run-1"},
    ).to_state_data()
    none_chosen = ScoutUniverse(
        pairs=("BTC/USD",), scanned=1, equity=Decimal("1000"), rank_feature="expected_move",
        reason_code="no_rankable_pair", rank_skipped={"no_prediction": 1},
    ).to_state_data()
    return [
        (1, "OK", chosen),
        (2, "PASS", none_chosen),
        (3, "BLOCK", {"reason_code": "scout_inputs_unavailable"}),
        (4, "ERROR", {"error": "boom"}),
    ]


def write_tally_case(root: Path, rows: list[tuple[int, str, dict[str, object]]]) -> tuple[Path, Path]:
    """The captured log for every tick, and a `scout_tallies` table (migration 0007's own
    SQL) holding `rows`, serialised the way spec 146 has engine 19 store them.

    The insert follows whatever columns 0007 declares, so the test reads the schema as
    committed rather than a copy of it. Engine 3's `closed_bar_ts` is the tick's bar."""
    log = root / "scout.jsonl"
    log.write_text("".join(
        json.dumps({"cycle_id": cycle, "status": status, "candidate": payload.get("pair"),
                    "closed_bar_ts": BAR_S + cycle * 900, "payload": payload}) + "\n"
        for cycle, status, payload in scout_ticks()
    ), encoding="utf-8")
    db = root / "a.sqlite"
    connection = sqlite3.connect(db)
    connection.executescript(MIGRATION_0007.read_text(encoding="utf-8"))
    columns = [str(row[1]) for row in connection.execute("PRAGMA table_info(scout_tallies)") if row[1] != "id"]
    for cycle, status, payload in rows:
        values: dict[str, object] = {
            "run_id": "replay-a", "cycle_id": cycle, "ts": 0, "updated_at": 0, "status": status,
            "closed_bar_ts": payload.get("stored_bar_s", BAR_S + cycle * 900), "candidate": payload.get("pair"),
            **{key: payload.get(key) for key in ("reason_code", "scanned", "entered", "equity", "rank_feature",
                                                 "rank_descending")},
            **{key: json.dumps(payload[key]) if payload.get(key) is not None else None for key in TALLY_JSON},
        }
        connection.execute(
            f"INSERT INTO scout_tallies ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            [values.get(column) for column in columns],
        )
    connection.commit()
    connection.close()
    return db, log


@pytest.mark.skipif(not MIGRATION_0007.exists(), reason="spec 146's migration has not landed")
def test_every_tick_engine_7_ran_has_its_tally_and_each_planted_defect_is_caught(
    rehearsal: ModuleType, tmp_path: Path
) -> None:
    faithful = [tick for tick in scout_ticks() if tick[1] != "ERROR"]
    (tmp_path / "ok").mkdir()
    report = rehearsal.tally_check(*write_tally_case(tmp_path / "ok", faithful))
    assert (report["ticks_engine_7_ran"], report["of_which_no_candidate"], report["engine_7_errored"]) == (3, 2, 1)
    assert (report["tally_rows"], report["counts_equal"], report["mismatched_count"]) == (3, True, 0)
    assert report["columns_not_in_table"] == []

    no_candidate_skipped = [tick for tick in faithful if tick[2].get("pair") is not None]
    ranked_only_with_a_candidate = [
        (cycle, status, payload if "pair" in payload else {k: v for k, v in payload.items() if k != "ranked"})
        for cycle, status, payload in faithful
    ]
    null_filled_as_zero = [
        (cycle, status, {"scanned": 0, "entered": 0, **payload}) for cycle, status, payload in faithful
    ]
    bar_one_bar_off = [
        (cycle, status, {**payload, "stored_bar_s": BAR_S + (cycle - 1) * 900}) for cycle, status, payload in faithful
    ]
    for name, rows in (("skip", no_candidate_skipped), ("ranked", ranked_only_with_a_candidate),
                       ("zero", null_filled_as_zero), ("bar", bar_one_bar_off)):
        (tmp_path / name).mkdir()
        planted = rehearsal.tally_check(*write_tally_case(tmp_path / name, rows))
        assert planted["mismatched_count"] > 0 or not planted["counts_equal"], name


def test_the_tally_check_reports_an_absent_table_rather_than_a_count(rehearsal: ModuleType, tmp_path: Path) -> None:
    db = tmp_path / "a.sqlite"
    sqlite3.connect(db).close()
    assert rehearsal.tally_check(db, tmp_path / "scout.jsonl")["table_present"] is False
