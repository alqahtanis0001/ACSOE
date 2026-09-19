"""Spec 140 step 1 — engine 19 writes engine 8's SHAP as Parquet through the store.

On every tick engine 8 scored a candidate, approved or refused, engine 19 writes one
explanation through `StoreClient.write_shap` and sets `rejections.shap_ref` on a refusal of
that candidate. These tests use the real store with a real `derived_dir` and read every file
back through `read_shap`: no double stands in for the Parquet.

What must never happen, each with its own test: an explanation written for a tick engine 8
did not score (a refusal, an error, an empty explanation, no engine 8 at all), a `shap_ref` on
a rejection of a different pair, and a store refusal taking the tick down with it.
"""

from __future__ import annotations

import dataclasses
import functools
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.engines.test_memory_rows import balances, rows_in, tick
from tests.engines.test_trade_chain_rehearsal import (  # A's rehearsal harness, reused whole
    _close_stores,  # noqa: F401 - an autouse fixture: closes the rehearsal's store
    trained,  # noqa: F401 - a fixture, used by name
    window,  # noqa: F401 - a fixture, used by name
)

from acsoe.clients.store import StoreClient
from acsoe.clients.store.migrations import apply_migrations
from acsoe.engines.memory.engine import MemoryEngine

PAIR = "AAA/USD"
CONTRIBUTIONS = {"log_return_4": 0.0125, "realised_vol_16": -0.004, "bar_body_pct": 0.0}


@pytest.fixture
def shap_store(tmp_path: Path) -> Any:
    db = tmp_path / "acsoe.sqlite"
    apply_migrations(db)
    client = StoreClient(db, derived_dir=tmp_path / "derived")
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def context(engine_context: Any, shap_store: Any, fixed_now: Any) -> Any:
    object.__setattr__(engine_context.clients, "store", shap_store)
    return dataclasses.replace(engine_context, run_id="run-shap", now=fixed_now)


def prediction(pair: str = PAIR, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "pair": pair,
        "bar_ts": 1,
        "model_run_id": "train-x-f390",
        "p_target": 0.5,
        "expected_move_pct": "0.0183",
        "is_buy": True,
        "shap": dict(CONTRIBUTIONS),
    }
    payload.update(extra)
    return payload


def refused_at_cost(cycle_id: int, **extra: Any) -> dict[str, Any]:
    state = tick(
        cycle_id,
        **balances("500.00"),
        scout={"pair": PAIR},
        prediction=prediction(),
        cost={"pair": PAIR, "expected_move_pct": "0.0183", "friction_pct": "0.009",
              "net_edge_pct": "0.0093", "hurdle_pct": "0.0135", "clears_hurdle": False,
              "reason_code": "net_edge_below_hurdle"},
        trading_blocked_by="cost",
        block_reason="Net edge below the hurdle",
        block_status="BLOCK",
    )
    state.update(extra)
    return state


def files_under(store: Any) -> list[Path]:
    return sorted(Path(store.derived_dir).rglob("*.parquet"))


# --------------------------------------------------------------------------- #
# Written, and joined
# --------------------------------------------------------------------------- #


def test_a_refusal_after_engine_8_scored_writes_one_explanation_and_joins_it(
    context: Any, shap_store: Any
) -> None:
    result = MemoryEngine().process(context, refused_at_cost(7))
    (rejection,) = rows_in(shap_store.db_path, "rejections")
    ref = result.data["shap_ref"]
    assert rejection["shap_ref"] == ref == f"shap/run-shap/7/{PAIR.replace('/', '%2F')}.parquet"
    record = shap_store.read_shap(ref)
    assert (record.run_id, record.cycle_id, record.pair) == ("run-shap", 7, PAIR)
    assert record.model_run_id == "train-x-f390"
    assert record.contributions == tuple(CONTRIBUTIONS.items())
    assert len(files_under(shap_store)) == 1
    assert result.data["shap_skipped_reason"] is None


def test_an_approval_writes_its_explanation_with_no_rejection(
    context: Any, shap_store: Any
) -> None:
    state = tick(7, **balances("500.00"), scout={"pair": PAIR}, prediction=prediction())
    result = MemoryEngine().process(context, state)
    assert rows_in(shap_store.db_path, "rejections") == []
    assert shap_store.read_shap(result.data["shap_ref"]).pair == PAIR


# --------------------------------------------------------------------------- #
# Not written
# --------------------------------------------------------------------------- #


def test_an_engine_8_refusal_writes_none(context: Any, shap_store: Any) -> None:
    """A DI refusal publishes no `shap` (engine 8 scored nothing), so there is nothing to
    explain and the rejection carries no ref."""
    state = tick(
        7,
        **balances("500.00"),
        scout={"pair": PAIR},
        prediction={"pair": PAIR, "bar_ts": 1, "model_run_id": "m", "shap": None,
                    "reason_code": "di_refused"},
        trading_blocked_by="prediction",
        block_reason="DI refused",
        block_status="BLOCK",
    )
    result = MemoryEngine().process(context, state)
    assert files_under(shap_store) == []
    (rejection,) = rows_in(shap_store.db_path, "rejections")
    assert rejection["shap_ref"] is None
    assert result.data["shap_ref"] is None


def test_an_empty_explanation_is_not_written(context: Any, shap_store: Any) -> None:
    result = MemoryEngine().process(
        context, refused_at_cost(7, prediction=prediction(shap={}))
    )
    assert files_under(shap_store) == []
    # Not written because there is nothing to write, not because the store refused it:
    # an empty explanation is absent, and absent carries no skip reason.
    assert result.data["shap_skipped_reason"] is None
    (rejection,) = rows_in(shap_store.db_path, "rejections")
    assert rejection["shap_ref"] is None


def test_an_errored_engine_8_writes_none_whatever_its_payload_says(
    context: Any, shap_store: Any
) -> None:
    state = tick(
        7,
        **balances("500.00"),
        scout={"pair": PAIR},
        prediction=prediction(),
        trading_blocked_by="prediction",
        block_reason="unhandled",
        block_status="ERROR",
    )
    MemoryEngine().process(context, state)
    assert files_under(shap_store) == []


def test_a_tick_engine_8_did_not_run_writes_none(context: Any, shap_store: Any) -> None:
    MemoryEngine().process(context, tick(7, **balances("500.00")))
    assert files_under(shap_store) == []


def test_a_rejection_of_another_pair_gets_no_ref(context: Any, shap_store: Any) -> None:
    """The ref explains the pair engine 8 scored; a rejection of any other pair is a
    different decision."""
    state = refused_at_cost(7, prediction=prediction(pair="BBB/USD"))
    MemoryEngine().process(context, state)
    (rejection,) = rows_in(shap_store.db_path, "rejections")
    assert rejection["shap_ref"] is None
    assert len(files_under(shap_store)) == 1


# --------------------------------------------------------------------------- #
# A store refusal never loses the tick
# --------------------------------------------------------------------------- #


def test_a_store_without_a_parquet_root_skips_the_explanation_and_keeps_the_tick(
    engine_context: Any, migrated_db: Path, fixed_now: Any
) -> None:
    store = StoreClient(migrated_db)
    try:
        object.__setattr__(engine_context.clients, "store", store)
        context = dataclasses.replace(engine_context, run_id="run-shap", now=fixed_now)
        result = MemoryEngine().process(context, refused_at_cost(7))
    finally:
        store.close()
    (rejection,) = rows_in(migrated_db, "rejections")
    assert rejection["shap_ref"] is None
    assert result.data["shap_ref"] is None
    assert "derived_dir" in result.data["shap_skipped_reason"]
    assert result.data["written"]["equity_snapshots"] == 1


def test_a_non_finite_contribution_is_skipped_not_fatal(context: Any, shap_store: Any) -> None:
    state = refused_at_cost(7, prediction=prediction(shap={"x": float("nan")}))
    result = MemoryEngine().process(context, state)
    assert files_under(shap_store) == []
    assert result.data["shap_skipped_reason"]
    (rejection,) = rows_in(shap_store.db_path, "rejections")
    assert rejection["shap_ref"] is None


def test_a_second_write_for_one_tick_is_skipped_not_fatal(context: Any, shap_store: Any) -> None:
    """The store is write-once. A re-run of one tick (the same run and cycle) finds the file
    already there, and the skip is recorded rather than raised."""
    # No balance, so no equity row: the store is write-once there too, and this test is
    # about the explanation, not the equity series.
    MemoryEngine().process(context, tick(7, prediction=prediction()))
    again = MemoryEngine().process(context, tick(7, prediction=prediction()))
    assert again.data["shap_ref"] is None
    assert "overwrite" in again.data["shap_skipped_reason"]


# --------------------------------------------------------------------------- #
# Spec 140's Check When Done: a rehearsal tick refused at engine 10
# --------------------------------------------------------------------------- #


def test_a_rehearsed_refusal_at_engine_10_writes_an_explanation_that_reads_back(
    tmp_path: Path, trained: Any, window: Any, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """The real chain on A's rehearsal harness, its store given a real `derived_dir`. The
    entry bar's quote is widened until engine 10 refuses; engine 8 scored the candidate, so
    the rejection carries a ref, and the file reads back as engine 8's published
    contributions on that tick, recomputed from `state`."""
    import tests.engines.test_trade_chain_rehearsal as rehearsal_module

    monkeypatch.setattr(
        rehearsal_module,
        "StoreClient",
        functools.partial(StoreClient, derived_dir=tmp_path / "derived"),
    )
    rehearsal = rehearsal_module.build(tmp_path, trained, window)
    rehearsal.quote(rehearsal.bid, rehearsal.bid + WIDE_SPREAD)
    state = rehearsal.tick(rehearsal.entry_moment, check=False)
    assert state.get("trading_blocked_by") == "cost", (
        state.get("trading_blocked_by"), state.get("block_reason")
    )
    shap = state["prediction"]["shap"]
    assert shap, "engine 8 published no explanation on the refused tick"
    (rejection,) = [
        row for row in rehearsal.store.recent_rejections(10) if row.rejected_by == "cost"
    ]
    assert rejection.shap_ref is not None
    record = rehearsal.store.read_shap(rejection.shap_ref)
    assert record.pair == state["prediction"]["pair"] == rejection.pair
    assert record.model_run_id == state["prediction"]["model_run_id"]
    assert dict(record.contributions) == pytest.approx(dict(shap))
    assert [name for name, _ in record.contributions] == list(shap)


#: Wide enough that friction's spread term alone puts the entry bar's expected move below
#: the hurdle, narrow enough that engine 7 still admits the pair. Found by probing the
#: rehearsal's window, not derived; the test asserts it is engine 10 that refuses.
WIDE_SPREAD = Decimal("3.0")

