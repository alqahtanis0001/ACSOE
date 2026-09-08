"""Parquet access for `data/derived/`.

The columnar half of the store. `context/architecture-context.md` splits the two by
shape and the split is not negotiable: relational records — trades, positions, orders,
equity snapshots, block records, rejections — live in SQLite, and built candles, feature
snapshots and SHAP explanations live here. Never put a large array in SQLite; never put
a relational record in Parquet.

Timestamps are `timestamp('us', tz='UTC')`, matching the integer microseconds the SQLite
side stores. A naive or second-resolution timestamp column is refused at write time
rather than discovered during a replay, because a silently truncated timestamp is a
look-ahead bug that looks like a data bug.
"""

from __future__ import annotations

from pathlib import Path

# pyarrow ships no py.typed marker, so `--strict` cannot see through it. The ignore is
# deliberately local rather than a `pyarrow.*` entry in the mypy overrides: the project
# runs with `warn_unused_ignores`, and a global override would turn this line into an
# error rather than removing the need for it.
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

#: The only timestamp type this project writes.
TIMESTAMP_TYPE: pa.DataType = pa.timestamp("us", tz="UTC")


class ParquetError(RuntimeError):
    """A Parquet read or write was refused."""


def check_timestamp_columns(table: pa.Table) -> None:
    """Raise unless every timestamp column is microsecond-resolution UTC."""
    for field in table.schema:
        if not pa.types.is_timestamp(field.type):
            continue
        if field.type != TIMESTAMP_TYPE:
            raise ParquetError(
                f"column {field.name!r} is {field.type}; timestamps must be "
                f"{TIMESTAMP_TYPE} (UTC, microseconds)"
            )


class ParquetStore:
    """Reads and writes Parquet under one root, usually `data/derived/`."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, relative: str | Path) -> Path:
        """Resolve a path under the root, refusing anything that escapes it."""
        candidate = (self._root / Path(relative)).resolve()
        root = self._root.resolve()
        if root != candidate and root not in candidate.parents:
            raise ParquetError(f"path escapes the parquet root: {relative!r}")
        return candidate

    def exists(self, relative: str | Path) -> bool:
        return self.path_for(relative).is_file()

    def write(self, relative: str | Path, table: pa.Table) -> Path:
        """Write a table, creating parent directories. Returns the path written."""
        check_timestamp_columns(table)
        path = self.path_for(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, path)
        return path

    def read(self, relative: str | Path) -> pa.Table:
        """Read a table back."""
        path = self.path_for(relative)
        if not path.is_file():
            raise ParquetError(f"no parquet file at {path}")
        return pq.read_table(path)
