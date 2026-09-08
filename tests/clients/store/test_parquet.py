"""Spec 12 step 7 - the columnar half of the store.

`data/derived/` holds built candles, feature snapshots and SHAP rows; SQLite holds
relational records. The split is fixed by `architecture-context.md` and this file only
covers the mechanics of the Parquet side.

The one rule with teeth is the timestamp type. `code-standards.md` fixes timestamps at
UTC microseconds, matching the integer microseconds the SQLite side stores. A column
written at second resolution loses the sub-second ordering a replay needs, and a naive
column loses the offset - both surface later as a look-ahead bug that looks like a data
bug, so they are refused at write time instead.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from acsoe.clients.store.parquet import (
    TIMESTAMP_TYPE,
    ParquetError,
    ParquetStore,
    check_timestamp_columns,
)


@pytest.fixture
def parquet(tmp_path: Path) -> ParquetStore:
    """Never `data/derived/` itself - a test writing into the real tree is a defect."""
    return ParquetStore(tmp_path / "derived")


def candles() -> pa.Table:
    moments = [
        dt.datetime(2026, 9, 8, 12, 0, tzinfo=dt.UTC),
        dt.datetime(2026, 9, 8, 12, 15, tzinfo=dt.UTC),
    ]
    return pa.table(
        {
            "ts": pa.array(moments, type=TIMESTAMP_TYPE),
            "pair": pa.array(["XBT/USD", "XBT/USD"]),
            "close": pa.array([61250.0, 61310.5], type=pa.float64()),
        }
    )


def test_a_table_round_trips_through_a_file(parquet: ParquetStore) -> None:
    written = parquet.write("candles/xbtusd.parquet", candles())

    assert written.is_file()
    assert parquet.exists("candles/xbtusd.parquet")
    assert parquet.read("candles/xbtusd.parquet").equals(candles())


def test_writing_creates_the_parent_directories(parquet: ParquetStore) -> None:
    assert not parquet.root.exists()

    parquet.write("features/2026/09/snapshot.parquet", candles())

    assert (parquet.root / "features" / "2026" / "09" / "snapshot.parquet").is_file()


@pytest.mark.parametrize(
    "column_type",
    [
        pytest.param(pa.timestamp("s", tz="UTC"), id="second-resolution"),
        pytest.param(pa.timestamp("ns", tz="UTC"), id="nanosecond-resolution"),
        pytest.param(pa.timestamp("us"), id="naive"),
        pytest.param(pa.timestamp("us", tz="Europe/London"), id="not-utc"),
    ],
)
def test_a_timestamp_that_is_not_utc_microseconds_is_refused(
    parquet: ParquetStore, column_type: pa.DataType
) -> None:
    table = pa.table({"ts": pa.array([0, 900_000_000], type=pa.int64()).cast(column_type)})

    with pytest.raises(ParquetError, match="timestamps must be"):
        parquet.write("bad.parquet", table)

    assert not parquet.exists("bad.parquet"), "a refused write leaves no file behind"


def test_a_table_with_no_timestamp_column_is_fine(parquet: ParquetStore) -> None:
    """The check is about timestamp columns, not about requiring one."""
    check_timestamp_columns(pa.table({"pair": pa.array(["XBT/USD"])}))


def test_a_path_that_escapes_the_root_is_refused(parquet: ParquetStore) -> None:
    """`data/derived/` is the boundary. A relative path climbing out of it would let a
    caller write anywhere on the machine, and `pathlib` will happily resolve it."""
    with pytest.raises(ParquetError, match="escapes the parquet root"):
        parquet.path_for(Path("..") / "raw" / "escaped.parquet")


def test_reading_a_file_that_is_not_there_raises(parquet: ParquetStore) -> None:
    with pytest.raises(ParquetError, match="no parquet file"):
        parquet.read("candles/missing.parquet")


def test_exists_is_false_before_the_first_write(parquet: ParquetStore) -> None:
    assert parquet.exists("candles/xbtusd.parquet") is False
