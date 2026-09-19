"""Spec 140's store surface: one decision's SHAP attributions, in Parquet, written once.

`architecture-context.md` keeps SHAP in Parquet, joined by decision id, never in SQLite.
The properties tested here are the ones engine 19 and the console depend on:
- the round trip is exact and keeps order;
- `(run_id, cycle_id, pair)` is unique because it is the path;
- nothing is ever overwritten;
- an empty or non-finite explanation is refused rather than stored;
- a ref cannot read outside the Parquet root.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from acsoe.clients.store.client import StoreClient, StoreError
from acsoe.clients.store.contracts import ShapRecord

#: Deliberately not in name order, so a reader that sorted would fail the order assertion.
CONTRIBUTIONS = {"vol_48": 0.0125, "log_return_4": -0.25, "bar_body_pct": 1e-17, "macro_btc_x": 3.0}


@pytest.fixture
def shap_store(tmp_path: Path) -> StoreClient:
    return StoreClient(tmp_path / "acsoe.sqlite", derived_dir=tmp_path / "derived")


def write(store: StoreClient, **overrides: object) -> str:
    fields: dict[str, object] = {
        "run_id": "run-a",
        "cycle_id": 7,
        "ts": 1_726_000_000_123_456,
        "pair": "BTC/USD",
        "model_run_id": "train-x-f404-p7",
        "contributions": CONTRIBUTIONS,
    }
    fields.update(overrides)
    return store.write_shap(**fields)  # type: ignore[arg-type]


def test_an_explanation_round_trips_exactly_and_in_the_order_written(
    shap_store: StoreClient, tmp_path: Path
) -> None:
    ref = write(shap_store)

    assert ref == "shap/run-a/7/BTC%2FUSD.parquet"
    assert (tmp_path / "derived" / ref).is_file()
    assert shap_store.read_shap(ref) == ShapRecord(
        run_id="run-a",
        cycle_id=7,
        ts=1_726_000_000_123_456,
        pair="BTC/USD",
        model_run_id="train-x-f404-p7",
        contributions=tuple(CONTRIBUTIONS.items()),
    )


def test_the_timestamp_is_stored_as_utc_microseconds(shap_store: StoreClient, tmp_path: Path) -> None:
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    from acsoe.clients.store.parquet import TIMESTAMP_TYPE

    ref = write(shap_store)
    schema = pq.read_schema(tmp_path / "derived" / ref)
    assert schema.field("ts").type == TIMESTAMP_TYPE
    assert schema.field("contribution").type.bit_width == 64


def test_no_model_run_id_reads_back_absent(shap_store: StoreClient) -> None:
    assert shap_store.read_shap(write(shap_store, model_run_id=None)).model_run_id is None


def test_each_decision_gets_its_own_file_and_none_is_overwritten(shap_store: StoreClient) -> None:
    first = write(shap_store)
    others = {
        write(shap_store, pair="ETH/USD"),
        write(shap_store, cycle_id=8),
        write(shap_store, run_id="run-b"),
    }
    assert first not in others and len(others) == 3

    with pytest.raises(StoreError, match="refusing to overwrite the SHAP explanation"):
        write(shap_store, contributions={"vol_48": 9.0})
    assert shap_store.read_shap(first).contributions == tuple(CONTRIBUTIONS.items())


def test_an_empty_explanation_is_refused_and_writes_nothing(
    shap_store: StoreClient, tmp_path: Path
) -> None:
    with pytest.raises(StoreError, match="refusing an empty SHAP explanation"):
        write(shap_store, contributions={})
    assert not (tmp_path / "derived").exists() or not any((tmp_path / "derived").rglob("*.parquet"))


@pytest.mark.parametrize(
    ("value", "fragment"),
    [(math.nan, "not finite"), (math.inf, "not finite"), (True, "not a number"), ("0.1", "not a number")],
)
def test_a_contribution_that_is_not_a_finite_number_is_refused(
    shap_store: StoreClient, value: object, fragment: str
) -> None:
    with pytest.raises(StoreError, match=fragment):
        write(shap_store, contributions={"vol_48": 0.1, "bad": value})


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"run_id": "../escape"}, "a run id is one directory name"),
        ({"run_id": ""}, "refusing an empty run id"),
        ({"pair": " "}, "blank pair"),
    ],
)
def test_an_unusable_key_is_refused(
    shap_store: StoreClient, overrides: dict[str, object], fragment: str
) -> None:
    with pytest.raises(StoreError, match=fragment):
        write(shap_store, **overrides)


def test_a_ref_outside_the_root_or_missing_is_refused(shap_store: StoreClient, tmp_path: Path) -> None:
    write(shap_store)
    with pytest.raises(StoreError, match="escapes the parquet root"):
        shap_store.read_shap("../acsoe.sqlite")
    with pytest.raises(StoreError, match="no parquet file"):
        shap_store.read_shap("shap/run-a/7/NOPE.parquet")


def test_a_client_without_a_parquet_root_refuses_both_directions(tmp_path: Path) -> None:
    bare = StoreClient(tmp_path / "acsoe.sqlite")
    assert bare.derived_dir is None
    with pytest.raises(StoreError, match=r"cannot write a SHAP explanation: .* no Parquet root"):
        write(bare)
    with pytest.raises(StoreError, match=r"cannot read a SHAP explanation: .* no Parquet root"):
        bare.read_shap("shap/run-a/7/BTC%2FUSD.parquet")


def test_a_file_holding_two_decisions_is_refused(shap_store: StoreClient, tmp_path: Path) -> None:
    """A ref names one decision. A file that mixes two cannot be attributed to either."""
    import pyarrow as pa  # type: ignore[import-untyped]
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    ref = write(shap_store)
    path = tmp_path / "derived" / ref
    table = pq.read_table(path)
    mixed = table.set_column(
        table.schema.get_field_index("pair"),
        "pair",
        pa.array(["BTC/USD"] * (table.num_rows - 1) + ["ETH/USD"]),
    )
    pq.write_table(mixed, path)
    with pytest.raises(StoreError, match="holds 2 decisions"):
        shap_store.read_shap(ref)
