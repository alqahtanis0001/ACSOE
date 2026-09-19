"""Spec 145 — every gate's verdict, recorded on both sides of every decision.

Engine 19 writes a snapshot of every judging engine's published verdict into
`approvals.details` on the placing tick and into `rejections.details` on a refusal, the
refuser marked. These tests hold four properties against the real store:

* the snapshot is each engine's payload **restricted to `VERDICT_FIELDS`**, recomputed here
  from `state` and never read back from the row;
* on a refusal it stops at the refuser, which is marked, and no engine after it appears;
* a field an engine did not publish is **absent**, never null-filled, and values are copied
  exactly as published (money stays a decimal string, a statistic stays a float);
* an engine that errored records only its status, and a malformed payload never fails the tick.

A contract walk holds `VERDICT_FIELDS` to what each engine actually publishes.
"""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
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

from acsoe.engines.memory.contracts import DETAILS_VERSION, VERDICT_FIELDS
from acsoe.engines.memory.engine import MemoryEngine

PAIR = "AAA/USD"
USERREF = 881_001

#: Every judging engine's payload as it publishes it, with one extra key each that is not a
#: verdict field, so a snapshot that copied whole payloads would be caught.
PAYLOADS: dict[str, dict[str, Any]] = {
    "scout": {"pair": PAIR, "rank_feature": "expected_move", "rank_descending": True,
              "ranked": [{"pair": PAIR, "expected_move_pct": "0.0183"}], "rank_skipped": {},
              "rank_run_ids": {"prediction": "p-1"}, "scanned": 127, "pairs": [PAIR]},
    "regime": {"label": "trending", "inputs": {"vol": 0.1}},
    "anomaly": {"score": 0.41, "threshold": 0.65, "anomalous": False, "model_run_id": "a-1",
                "bar_ts": 1},
    "prediction": {"p_target": 0.52, "p_stop": 0.3, "p_timeout": 0.18,
                   "expected_move_pct": "0.018300", "is_buy": True, "di": 1.2,
                   "di_threshold": 1.9, "model_run_id": "p-1", "shap": {"f": 0.1}},
    "order_book": {"estimated_slippage_pct": "0.00012", "basis_notional": "5000.00",
                   "best_bid": "100.10", "fill_price": "100.08", "levels_consumed": 2,
                   "depth": 10, "quote_currency": "USD"},
    "cost": {"expected_move_pct": "0.018300", "friction_pct": "0.00650",
             "net_edge_pct": "0.011800", "hurdle_pct": "0.009750", "clears_hurdle": True,
             "pair": PAIR},
    "risk": {"approved": True, "qty": "3.5", "notional": "350.35", "risk_amount": "5.25",
             "ordermin": "0.1"},
    "adaptive_router": {"active_model_run_id": "p-1", "di_margin": 0.7, "regime": "trending",
                        "weights": {"p-1": 1.0}},
    "skeptic": {"p_wrong": 0.44, "threshold": 0.5, "vetoed": False, "model_run_id": "s-1",
                "reason": "ok"},
    "decision": {"coherent": True, "checked": ["cost", "risk"], "intent": {"qty": "3.5"}},
}


def restricted(state: dict[str, Any], engines: list[str]) -> dict[str, Any]:
    """The expected snapshot's `engines`, recomputed from `state` without engine 19's code."""
    fields = dict(VERDICT_FIELDS)
    return {
        engine: {k: v for k, v in state[engine].items() if k in fields[engine]}
        for engine in engines
    }


def approving_tick(cycle_id: int) -> dict[str, Any]:
    state = tick(cycle_id, **balances("500.00"), **json.loads(json.dumps(PAYLOADS)))
    state["execution"] = {"pair": PAIR, "userref": USERREF, "placed": True, "orders": []}
    return state


def refusing_tick(cycle_id: int, refuser: str, **extra: Any) -> dict[str, Any]:
    """The opportunity chain stopped at `refuser`: every engine after it is absent, as the
    orchestrator leaves `state`."""
    order = [engine for engine, _ in VERDICT_FIELDS]
    present = order[: order.index(refuser) + 1]
    state = tick(
        cycle_id,
        **balances("500.00"),
        **{k: json.loads(json.dumps(PAYLOADS[k])) for k in present},
        trading_blocked_by=refuser,
        block_reason="refused",
        block_status="BLOCK",
    )
    state[refuser]["reason_code"] = f"{refuser}_refused"
    state.update(extra)
    return state


def details_of(migrated_db: Path, table: str) -> dict[str, Any]:
    (row,) = rows_in(migrated_db, table)
    assert isinstance(row["details"], str)
    return json.loads(row["details"])


# --------------------------------------------------------------------------- #
# The contract walk
# --------------------------------------------------------------------------- #


def published_keys(engine: str) -> set[str]:
    """What an engine can publish: its state model's fields and its `*_FIELD` key names."""
    module = importlib.import_module(f"acsoe.engines.{engine}.contracts")
    keys: set[str] = set()
    for name, value in vars(module).items():
        if name.endswith("_FIELD") and isinstance(value, str):
            keys.add(value)
        if (
            inspect.isclass(value)
            and issubclass(value, BaseModel)
            and value.__module__ == module.__name__
            and callable(getattr(value, "to_state", None) or getattr(value, "to_state_data", None))
        ):
            keys.update(value.model_fields)
    return keys


@pytest.mark.parametrize(("engine", "fields"), VERDICT_FIELDS)
def test_every_listed_field_is_one_the_engine_publishes(
    engine: str, fields: tuple[str, ...]
) -> None:
    missing = sorted(set(fields) - published_keys(engine))
    assert missing == [], f"engine {engine} publishes no {missing}; a rename records nothing"


def test_the_fields_are_in_chain_order_and_exclude_shap() -> None:
    assert [engine for engine, _ in VERDICT_FIELDS] == [
        "scout", "regime", "anomaly", "prediction", "order_book", "cost", "risk",
        "adaptive_router", "skeptic", "decision",
    ]
    assert "shap" not in dict(VERDICT_FIELDS)["prediction"]


# --------------------------------------------------------------------------- #
# The approval side
# --------------------------------------------------------------------------- #


def test_an_approval_records_every_engines_verdict_restricted_to_its_fields(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    state = approving_tick(3)
    MemoryEngine().process(context_at(0), state)
    details = details_of(migrated_db, "approvals")
    assert details == {
        "details_version": DETAILS_VERSION,
        "engines": restricted(state, [engine for engine, _ in VERDICT_FIELDS]),
    }
    assert "refused_by" not in details


def test_values_are_copied_exactly_as_published(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    MemoryEngine().process(context_at(0), approving_tick(3))
    engines = details_of(migrated_db, "approvals")["engines"]
    assert engines["cost"]["friction_pct"] == "0.00650", "money stays an exact decimal string"
    assert isinstance(engines["anomaly"]["score"], float)
    assert engines["prediction"]["expected_move_pct"] == "0.018300"


def test_the_snapshot_is_canonical_json(context_at: Any, migrated_db: Path) -> None:  # noqa: F811
    MemoryEngine().process(context_at(0), approving_tick(3))
    (row,) = rows_in(migrated_db, "approvals")
    parsed = json.loads(row["details"])
    assert row["details"] == json.dumps(parsed, sort_keys=True, separators=(",", ":"))


def test_an_unpublished_field_is_absent_never_null(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    state = approving_tick(3)
    del state["prediction"]["di"]
    del state["risk"]["risk_amount"]
    MemoryEngine().process(context_at(0), state)
    engines = details_of(migrated_db, "approvals")["engines"]
    assert "di" not in engines["prediction"]
    assert "risk_amount" not in engines["risk"]


def test_an_engine_absent_from_state_is_absent_from_the_snapshot(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    state = approving_tick(3)
    del state["regime"]
    MemoryEngine().process(context_at(0), state)
    assert "regime" not in details_of(migrated_db, "approvals")["engines"]


# --------------------------------------------------------------------------- #
# The refusal side
# --------------------------------------------------------------------------- #


def test_a_refusal_at_the_skeptic_records_every_engine_before_it_and_the_skeptic(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    """Spec 145's named case."""
    state = refusing_tick(5, "skeptic")
    # A stale key from an engine after the refuser must not be recorded even if present.
    state["decision"] = json.loads(json.dumps(PAYLOADS["decision"]))
    MemoryEngine().process(context_at(0), state)
    details = details_of(migrated_db, "rejections")
    assert details["refused_by"] == "skeptic"
    assert list(details["engines"]) == sorted(
        ["scout", "regime", "anomaly", "prediction", "order_book", "cost", "risk",
         "adaptive_router", "skeptic"]
    )
    order = [engine for engine, _ in VERDICT_FIELDS]
    assert details["engines"] == restricted(state, order[: order.index("skeptic") + 1])


def test_a_refusal_at_the_cost_gate_records_the_cost_gates_own_values(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    state = refusing_tick(6, "cost")
    state["cost"]["clears_hurdle"] = False
    MemoryEngine().process(context_at(0), state)
    details = details_of(migrated_db, "rejections")
    assert details["refused_by"] == "cost"
    assert details["engines"]["cost"]["clears_hurdle"] is False
    assert "risk" not in details["engines"]


def test_an_errored_engine_records_its_status_and_nothing_else(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    """Engine 13 raised on an earlier tick-shaped state and a refusal happened later: the
    errored payload is not read, whatever it says. Here the errored engine is a guard-free
    opportunity engine the orchestrator left a payload for."""
    state = approving_tick(3)
    state["trading_blocked_by"] = "adaptive_router"
    state["block_status"] = "ERROR"
    state["block_reason"] = "unhandled"
    MemoryEngine().process(context_at(0), state)
    # An errored opportunity engine is recorded as a block, not a rejection or approval.
    assert rows_in(migrated_db, "rejections") == []
    (approval,) = rows_in(migrated_db, "approvals")
    engines = json.loads(approval["details"])["engines"]
    assert engines["adaptive_router"] == {"status": "ERROR"}


def test_a_malformed_payload_is_recorded_as_unreadable_and_the_tick_is_kept(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    state = refusing_tick(7, "cost")
    state["regime"] = ["not", "a", "mapping"]
    MemoryEngine().process(context_at(0), state)
    details = details_of(migrated_db, "rejections")
    assert details["engines"]["regime"] == {"status": "UNREADABLE"}
    assert details["engines"]["cost"]["friction_pct"] == "0.00650"


def test_an_unserialisable_value_still_writes_a_row(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    state = refusing_tick(8, "cost")
    state["anomaly"]["score"] = object()
    MemoryEngine().process(context_at(0), state)
    details = details_of(migrated_db, "rejections")
    assert details == {
        "details_version": DETAILS_VERSION, "unserialisable": True, "refused_by": "cost"
    }


# --------------------------------------------------------------------------- #
# Spec 145's Check When Done: the real chain
# --------------------------------------------------------------------------- #


def test_a_rehearsed_approvals_details_equal_every_engines_payload_restricted(
    tmp_path: Path, trained: Any, window: Any  # noqa: F811
) -> None:
    """The whole chain approves and places one entry (A's rehearsal harness). The approval's
    `details` must equal each engine's published payload on that tick, restricted to
    `VERDICT_FIELDS`, recomputed here from `state`."""
    from tests.engines.test_trade_chain_rehearsal import build, the_entry

    rehearsal = build(tmp_path, trained, window)
    entry, placing = the_entry(rehearsal)
    approval = rehearsal.store.approval(entry.userref)
    assert approval is not None and approval.details is not None
    engines = [engine for engine, _ in VERDICT_FIELDS if engine in placing]
    assert "cost" in engines and "skeptic" in engines and "decision" in engines
    assert json.loads(approval.details) == {
        "details_version": DETAILS_VERSION,
        "engines": restricted(placing, engines),
    }
