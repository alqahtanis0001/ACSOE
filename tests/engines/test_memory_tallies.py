"""Spec 146 — engine 19 stores engine 7's universe step on every tick it ran.

One `scout_tallies` row per tick engine 7 ran and did not error, **including ticks with no
candidate**, copied from engine 7's published payload verbatim: nothing recomputed, a field
engine 7 did not publish stored as NULL, never zero. The funnel's universe step then comes
from rows, not from arithmetic on absences. Against the real store throughout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.engines.test_memory_rows import (
    balances,
    context_at,  # noqa: F401 - a fixture, used by name
    rows_in,
    tick,
)
from tests.engines.test_trade_chain_rehearsal import (  # A's rehearsal harness, reused whole
    _close_stores,  # noqa: F401 - an autouse fixture: closes the rehearsal's store
    trained,  # noqa: F401 - a fixture, used by name
    window,  # noqa: F401 - a fixture, used by name
)

from acsoe.engines.memory.engine import MemoryEngine

PAIR = "AAA/USD"

#: Engine 7's payload as `ScoutUniverse.to_state_data` publishes it, with a candidate.
WITH_CANDIDATE: dict[str, Any] = {
    "pairs": [PAIR, "BBB/USD"],
    "scanned": 5,
    "entered": 2,
    "excluded": {"below_costmin": 2, "no_live_quote": 1},
    "equity": "5000.00",
    "reason_code": None,
    "rank_feature": "expected_move",
    "rank_descending": True,
    "ranked": [{"pair": PAIR, "expected_move_pct": "0.018300"},
               {"pair": "BBB/USD", "expected_move_pct": "0.0041"}],
    "rank_skipped": {},
    "rank_run_ids": {"prediction": "p-1", "anomaly": "a-1"},
    "pair": PAIR,
}


def no_candidate(reason: str = "no_rankable_pair") -> dict[str, Any]:
    payload = {k: v for k, v in WITH_CANDIDATE.items() if k != "pair"}
    payload.update(reason_code=reason, ranked=[], rank_skipped={"incomplete_vector": 2})
    return payload


def sensor(closed_bar_ts: int | None) -> dict[str, Any]:
    return {"bar_closed": closed_bar_ts is not None, "closed_bar_ts": closed_bar_ts,
            "interval_s": 900}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def expected_row(payload: dict[str, Any], closed_bar_ts: int | None) -> dict[str, Any]:
    """The row engine 19 must write, recomputed from the payload without engine 19's code."""
    return {
        "candidate": payload.get("pair"),
        "scanned": payload.get("scanned"),
        "entered": payload.get("entered"),
        "equity": payload.get("equity"),
        "reason_code": payload.get("reason_code"),
        "rank_feature": payload.get("rank_feature"),
        "rank_descending": (
            None if payload.get("rank_descending") is None else int(payload["rank_descending"])
        ),
        "pairs": None if payload.get("pairs") is None else canonical(payload["pairs"]),
        "excluded": None if payload.get("excluded") is None else canonical(payload["excluded"]),
        "rank_skipped": (
            None if payload.get("rank_skipped") is None else canonical(payload["rank_skipped"])
        ),
        "ranked": None if payload.get("ranked") is None else canonical(payload["ranked"]),
        "rank_run_ids": (
            None if payload.get("rank_run_ids") is None else canonical(payload["rank_run_ids"])
        ),
        "closed_bar_ts": closed_bar_ts,
    }


def stored(migrated_db: Path) -> list[dict[str, Any]]:
    keys = list(expected_row(WITH_CANDIDATE, None))
    return [{k: row[k] for k in keys} for row in rows_in(migrated_db, "scout_tallies")]


def test_a_tick_with_a_candidate_is_stored_verbatim(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    state = tick(3, **balances("500.00"), scout=dict(WITH_CANDIDATE),
                 market_sensor=sensor(1_720_000_000))
    result = MemoryEngine().process(context_at(0), state)
    assert result.data["written"]["scout_tallies"] == 1
    assert stored(migrated_db) == [expected_row(WITH_CANDIDATE, 1_720_000_000)]
    (row,) = rows_in(migrated_db, "scout_tallies")
    assert (row["run_id"], row["cycle_id"]) == ("run-rows", 3)


def test_a_no_candidate_tick_is_stored_too(context_at: Any, migrated_db: Path) -> None:  # noqa: F811
    """The ticks the funnel could not count before."""
    payload = no_candidate()
    state = tick(4, **balances("500.00"), scout=payload, market_sensor=sensor(1_720_000_900))
    MemoryEngine().process(context_at(0), state)
    assert stored(migrated_db) == [expected_row(payload, 1_720_000_900)]
    assert stored(migrated_db)[0]["candidate"] is None


def test_a_blocked_engine_7_stores_only_what_it_published(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    """A BLOCK payload is only its reason code: every count is NULL, never zero."""
    payload = {"reason_code": "scout_inputs_unavailable"}
    state = tick(5, **balances("500.00"), scout=payload, market_sensor=sensor(None),
                 trading_blocked_by="scout", block_reason="inputs", block_status="BLOCK")
    MemoryEngine().process(context_at(0), state)
    (row,) = stored(migrated_db)
    assert row["reason_code"] == "scout_inputs_unavailable"
    for column in ("scanned", "entered", "equity", "pairs", "excluded", "ranked", "candidate",
                   "closed_bar_ts"):
        assert row[column] is None, column


def test_an_errored_engine_7_writes_no_tally(context_at: Any, migrated_db: Path) -> None:  # noqa: F811
    state = tick(6, **balances("500.00"), scout=dict(WITH_CANDIDATE),
                 trading_blocked_by="scout", block_reason="unhandled", block_status="ERROR")
    MemoryEngine().process(context_at(0), state)
    assert rows_in(migrated_db, "scout_tallies") == []


def test_a_tick_engine_7_did_not_run_writes_no_tally(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    MemoryEngine().process(context_at(0), tick(7, **balances("500.00")))
    assert rows_in(migrated_db, "scout_tallies") == []


def test_the_ranked_moves_stay_exact_decimal_strings(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    state = tick(8, **balances("500.00"), scout=dict(WITH_CANDIDATE),
                 market_sensor=sensor(1_720_000_000))
    MemoryEngine().process(context_at(0), state)
    (row,) = rows_in(migrated_db, "scout_tallies")
    assert json.loads(row["ranked"])[0]["expected_move_pct"] == "0.018300"


def test_a_tally_is_never_a_rejection(context_at: Any, migrated_db: Path) -> None:  # noqa: F811
    MemoryEngine().process(context_at(0), tick(9, **balances("500.00"), scout=no_candidate()))
    assert rows_in(migrated_db, "rejections") == []


def test_a_rehearsed_run_stores_one_tally_per_tick_engine_7_ran(
    tmp_path: Path, trained: Any, window: Any  # noqa: F811
) -> None:
    """Spec 146's Check When Done on A's harness: every tick where engine 7 ran has exactly
    one row, candidate or not, equal to engine 7's payload on that tick recomputed from
    `state`. The warm-up tick closes no bar, so engine 7 does not run on it."""
    from tests.engines.test_trade_chain_rehearsal import build, the_entry

    rehearsal = build(tmp_path, trained, window)
    states = [the_entry(rehearsal)[1]]
    assert rehearsal.orchestrator is not None
    run_id = rehearsal.orchestrator.run_id
    ran = [s for s in states if "scout" in s]
    rows = rehearsal.store.scout_tallies(run_id)
    assert len(rows) == len(ran) == 1
    for state, row in zip(ran, rows, strict=True):
        want = expected_row(state["scout"], state["market_sensor"].get("closed_bar_ts"))
        got = {
            "candidate": row.candidate, "scanned": row.scanned, "entered": row.entered,
            "equity": None if row.equity is None else format(row.equity, "f"),
            "reason_code": row.reason_code, "rank_feature": row.rank_feature,
            "rank_descending": None if row.rank_descending is None else int(row.rank_descending),
            "pairs": row.pairs, "excluded": row.excluded, "rank_skipped": row.rank_skipped,
            "ranked": row.ranked, "rank_run_ids": row.rank_run_ids,
            "closed_bar_ts": row.closed_bar_ts,
        }
        assert got == want
        assert row.cycle_id == state["cycle_id"]

