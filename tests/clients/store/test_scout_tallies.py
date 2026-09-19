"""Spec 146: migration 0007. One row per tick for engine 7's universe step, no-candidate ticks included.

The properties tested here, each by a test that can fail:
- 0007 migrates from empty and from a 0006 database holding rows, and touches none of them;
- a tally round-trips exactly, and its JSON columns come back byte for byte;
- absent is `None`, never zero, which is what a BLOCK payload looks like;
- one tick has one tally, and a second write raises;
- a float is refused where the value is exact: `equity`, and each expected move in `ranked`;
- engine 7's own identity holds on the row: `scanned == entered + sum(excluded)`;
- nothing is derived: there is no status, and the bar is engine 3's `closed_bar_ts`
  in whole seconds, as published (the lead's ruling);
- the payload field names are engine 7's own, read from its contract rather than retyped.
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import ScoutTallyRow
from acsoe.clients.store.migrations import apply_migrations, default_migrations_dir
from acsoe.engines.scout.contracts import (
    CANDIDATE_FIELD,
    RANK_DESCENDING_FIELD,
    RANK_FEATURE_FIELD,
    RANK_RUN_IDS_FIELD,
    RANK_SKIPPED_FIELD,
    RANKED_FIELD,
    ScoutUniverse,
)

#: Canonical JSON, as engine 19 writes it: sorted keys, no whitespace. The key order and
#: the decimal strings are what "byte for byte" is about.
PAIRS = '["BTC/USD","ETH/USD","SOL/USD"]'
EXCLUDED = '{"crypto_quoted":1,"no_live_quote":2}'
SKIPPED = '{"di_refused":1}'
RANKED = (
    '[{"expected_move_pct":"0.031","pair":"ETH/USD"},'
    '{"expected_move_pct":"0.01200","pair":"SOL/USD"}]'
)
RUN_IDS = '{"anomaly":"run-x","prediction":"run-x"}'


def ok_tally(**overrides: Any) -> ScoutTallyRow:
    fields: dict[str, Any] = {
        "run_id": "run-a",
        "cycle_id": 15,
        "ts": 1_000_000,
        "closed_bar_ts": 1_726_000_200,
        "reason_code": None,
        "candidate": "ETH/USD",
        "scanned": 6,
        "entered": 3,
        "equity": Decimal("5000.00"),
        "pairs": PAIRS,
        "excluded": EXCLUDED,
        "rank_feature": "expected_move",
        "rank_descending": True,
        "rank_skipped": SKIPPED,
        "ranked": RANKED,
        "rank_run_ids": RUN_IDS,
        "updated_at": 1_000_000,
    }
    fields.update(overrides)
    return ScoutTallyRow(**fields)


def blocked_tally(**overrides: Any) -> ScoutTallyRow:
    """A BLOCK payload carries only its reason code, so everything else is absent."""
    fields: dict[str, Any] = {
        "run_id": "run-a",
        "cycle_id": 16,
        "ts": 1_060_000,
        "reason_code": "scout_inputs_unavailable",
        "updated_at": 1_060_000,
    }
    fields.update(overrides)
    return ScoutTallyRow(**fields)


# --------------------------------------------------------------------------- #
# The migration
# --------------------------------------------------------------------------- #


def test_0007_migrates_from_a_0006_database_holding_rows_and_touches_none_of_them(
    tmp_path: Path,
) -> None:
    real = sorted(default_migrations_dir().glob("*.sql"))
    assert real[6].name == "0007_tick_tallies.sql", [path.name for path in real]
    staged = tmp_path / "migrations"
    staged.mkdir()
    for path in real[:6]:
        (staged / path.name).write_bytes(path.read_bytes())
    db_path = tmp_path / "db.sqlite"
    assert apply_migrations(db_path, migrations_dir=staged) == [1, 2, 3, 4, 5, 6]

    conn = sqlite3.connect(db_path)
    try:
        assert not conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'scout_tallies'"
        ).fetchall(), "the table must not exist before 0007"
        conn.execute(
            "INSERT INTO approvals (userref, run_id, cycle_id, ts, pair, friction_pct, "
            "details, updated_at) VALUES (11, 'run-a', 3, 900, 'SOL/USD', '0.006125', "
            "'{\"v\":1}', 900)"
        )
        conn.commit()
        before = conn.execute("SELECT * FROM approvals").fetchall()
    finally:
        conn.close()

    (staged / real[6].name).write_bytes(real[6].read_bytes())
    assert apply_migrations(db_path, migrations_dir=staged) == [7]

    with StoreClient(db_path) as store:
        assert store.scout_tallies("run-a") == ()
        after = store.connection.execute("SELECT * FROM approvals").fetchall()
        store.write_scout_tally(ok_tally())
        assert len(store.scout_tallies("run-a")) == 1
    assert [tuple(row) for row in after] == before, "0007 changed an existing row"


def test_0007_migrates_from_empty(tmp_path: Path) -> None:
    applied = apply_migrations(tmp_path / "fresh.sqlite")
    assert applied[-1] == 7
    with StoreClient(tmp_path / "fresh.sqlite") as store:
        store.write_scout_tally(blocked_tally())
        assert store.scout_tallies("run-a") == (blocked_tally().model_copy(update={"id": 1}),)


# --------------------------------------------------------------------------- #
# Round trip, byte for byte
# --------------------------------------------------------------------------- #


def test_a_tally_round_trips_exactly_with_its_json_byte_for_byte(store: StoreClient) -> None:
    written = ok_tally()
    row_id = store.write_scout_tally(written)

    (read,) = store.scout_tallies("run-a")

    assert read == written.model_copy(update={"id": row_id})
    assert read.closed_bar_ts == 1_726_000_200, "stored as published, in seconds"
    for name, text in (
        ("pairs", PAIRS),
        ("excluded", EXCLUDED),
        ("rank_skipped", SKIPPED),
        ("ranked", RANKED),
        ("rank_run_ids", RUN_IDS),
    ):
        assert getattr(read, name) == text, name
    assert format(read.equity or Decimal(0), "f") == "5000.00"
    assert read.rank_descending is True
    # The stored cell is exactly the text given, with the quantum in "0.01200" intact.
    (raw,) = store.connection.execute("SELECT ranked, equity FROM scout_tallies").fetchall()
    assert (raw["ranked"], raw["equity"]) == (RANKED, "5000.00")


def test_a_blocked_tick_is_absent_everywhere_never_zero(store: StoreClient) -> None:
    store.write_scout_tally(blocked_tally())
    (read,) = store.scout_tallies("run-a")
    for name in (
        "closed_bar_ts", "candidate", "scanned", "entered", "equity", "pairs", "excluded",
        "rank_feature", "rank_descending", "rank_skipped", "ranked", "rank_run_ids",
    ):
        assert getattr(read, name) is None, name
    raw = store.connection.execute("SELECT scanned, entered, equity FROM scout_tallies").fetchone()
    assert tuple(raw) == (None, None, None)


def test_a_no_candidate_pass_tick_is_recorded(store: StoreClient) -> None:
    """The ticks that used to leave no row: a universe the ranking skipped entirely."""
    tally = ok_tally(
        candidate=None,
        reason_code="no_rankable_pair",
        ranked="[]",
        rank_skipped='{"di_refused":2,"market_anomalous":1}',
    )
    store.write_scout_tally(tally)
    (read,) = store.scout_tallies("run-a")
    assert (read.candidate, read.reason_code) == (None, "no_rankable_pair")
    assert read.ranked == "[]"


def test_the_reader_is_per_run_ordered_by_ts_and_unlimited(store: StoreClient) -> None:
    # cycle_id restarts, so the ts order and the cycle_id order disagree on purpose.
    store.write_scout_tally(blocked_tally(cycle_id=2, ts=3_000))
    store.write_scout_tally(blocked_tally(cycle_id=9, ts=1_000))
    store.write_scout_tally(blocked_tally(run_id="run-b", cycle_id=1, ts=2_000))
    for cycle in range(100, 160):
        store.write_scout_tally(blocked_tally(cycle_id=cycle, ts=10_000 + cycle))

    rows = store.scout_tallies("run-a")
    assert [row.ts for row in rows][:2] == [1_000, 3_000]
    assert len(rows) == 62, "a window truncated the run"
    assert {row.run_id for row in rows} == {"run-a"}


# --------------------------------------------------------------------------- #
# Write-once
# --------------------------------------------------------------------------- #


def test_a_second_tally_for_one_tick_is_refused(store: StoreClient) -> None:
    store.write_scout_tally(ok_tally())
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        store.write_scout_tally(ok_tally(scanned=7, entered=4))
    (read,) = store.scout_tallies("run-a")
    assert read.scanned == 6
    # The same cycle_id in another run is another tick.
    store.write_scout_tally(ok_tally(run_id="run-b"))


# --------------------------------------------------------------------------- #
# Exact values refuse floats
# --------------------------------------------------------------------------- #


def test_a_float_equity_is_refused_by_model_and_database(store: StoreClient) -> None:
    with pytest.raises(ValidationError, match="money must never be a float"):
        ok_tally(equity=5000.0)
    store.write_scout_tally(ok_tally())
    with pytest.raises(sqlite3.IntegrityError, match=r"typeof\(equity\)"):
        store.connection.execute("UPDATE scout_tallies SET equity = 5000.0")


@pytest.mark.parametrize(
    ("ranked", "fragment"),
    [
        ('[{"expected_move_pct":0.031,"pair":"ETH/USD"}]', "never a JSON number"),
        ('[{"expected_move_pct":"NaN","pair":"ETH/USD"}]', "not finite"),
        ('[{"expected_move_pct":"abc","pair":"ETH/USD"}]', "not a decimal"),
        ('[{"pair":"ETH/USD"}]', "exactly {pair, expected_move_pct}"),
        ('{"ETH/USD":"0.031"}', "must be a JSON list"),
    ],
)
def test_a_ranked_list_that_is_not_exact_is_refused(ranked: str, fragment: str) -> None:
    with pytest.raises(ValidationError, match=fragment):
        ok_tally(ranked=ranked)


@pytest.mark.parametrize(
    ("field", "text", "fragment"),
    [
        ("pairs", '{"BTC/USD":1}', "list of pair names"),
        ("excluded", '{"crypto_quoted":1.5}', "non-negative integer"),
        ("excluded", '{"crypto_quoted":true}', "non-negative integer"),
        ("rank_skipped", '{"di_refused":-1}', "non-negative integer"),
        ("rank_skipped", "[]", "JSON object"),
        ("rank_run_ids", '{"prediction":3}', "name to run id"),
        ("pairs", "not json", "not JSON"),
    ],
)
def test_a_json_field_of_the_wrong_shape_is_refused(field: str, text: str, fragment: str) -> None:
    with pytest.raises(ValidationError, match=fragment):
        ok_tally(**{field: text})


def test_the_database_refuses_invalid_json_from_hand_written_sql(store: StoreClient) -> None:
    store.write_scout_tally(ok_tally())
    with pytest.raises(sqlite3.IntegrityError, match="json_valid"):
        store.connection.execute("UPDATE scout_tallies SET ranked = '[{'")


# --------------------------------------------------------------------------- #
# Engine 7's identities
# --------------------------------------------------------------------------- #


def test_a_tally_that_does_not_add_up_is_refused() -> None:
    with pytest.raises(ValidationError, match="the tally does not add up"):
        ok_tally(scanned=7)
    # With any of the three absent, there is nothing to check.
    ok_tally(scanned=None)


def test_nothing_derived_is_stored_there_is_no_status(store: StoreClient) -> None:
    """The lead's ruling: engine 7 publishes no status, so the tally has none. The outcome
    is read from `reason_code` and `candidate`, and neither the model nor the table offers
    a status to fill in."""
    assert "status" not in ScoutTallyRow.model_fields
    columns = {row["name"] for row in store.connection.execute("PRAGMA table_info(scout_tallies)")}
    assert "status" not in columns
    assert "bar_ts" not in columns and "closed_bar_ts" in columns
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        blocked_tally(status="BLOCK")


def test_a_negative_closed_bar_is_refused(store: StoreClient) -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        ok_tally(closed_bar_ts=-1)
    store.write_scout_tally(ok_tally())
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed: closed_bar_ts"):
        store.connection.execute("UPDATE scout_tallies SET closed_bar_ts = -1")


# --------------------------------------------------------------------------- #
# The field names are engine 7's
# --------------------------------------------------------------------------- #


def test_every_published_scout_field_maps_to_a_tally_column() -> None:
    """Read engine 7's real payload keys off its own contract, so a rename there goes red
    here instead of silently recording NULL. `pair` is stored as `candidate`, which is the
    one deliberate rename, and it is named here."""
    payload = ScoutUniverse(
        pairs=("ETH/USD",), scanned=1, candidate="ETH/USD", equity=Decimal("1")
    ).to_state_data()
    renamed = {CANDIDATE_FIELD: "candidate"}
    columns = set(ScoutTallyRow.model_fields)
    for key in payload:
        assert renamed.get(key, key) in columns, f"engine 7 publishes {key!r} and no column holds it"
    for key in (RANK_FEATURE_FIELD, RANK_DESCENDING_FIELD, RANKED_FIELD, RANK_SKIPPED_FIELD,
                RANK_RUN_IDS_FIELD):
        assert key in columns, key
    assert json.loads(RANKED)[0].keys() == {CANDIDATE_FIELD, "expected_move_pct"}, (
        "the ranked entry shape must be engine 7's own"
    )
