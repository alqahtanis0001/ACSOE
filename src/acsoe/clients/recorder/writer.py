"""The append-only JSONL writer with daily UTC rotation.

Opens in binary append mode and never truncates, seeks or rewrites. If the process
is killed mid-line the partial line stays; it is not repaired, because repairing a
recording is exactly what invariant 11 forbids.

This is `context.clients.recorder`, and engine 2 is the only engine permitted to
touch it — contract rule 4.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Self

import orjson

from acsoe.clients.recorder.contracts import validate_line

__all__ = ["JsonlRecorder", "utc_date_from_iso"]


def utc_date_from_iso(ts: str) -> str:
    """The UTC calendar date of an ISO timestamp, for daily file rotation."""
    return ts[:10]


class JsonlRecorder:
    """Append-only JSONL, rotated by UTC date.

    :param out_dir: normally ``data/raw/``. Created if missing.
    :param prefix: file stem. Matches ``scripts/record.py``'s default so the engine's
        output lands in the same daily files as the day-one recorder's and the archive
        stays one dataset.

    Rotation is driven by the **line's own** ``ts_recv``, not by the wall clock.
    Nothing in this package reads a clock, and a line's date is a property of the
    line: rotating on wall time would put a frame received at 23:59:59.9 into
    tomorrow's file if the write happened a tenth of a second later.
    """

    def __init__(self, out_dir: Path, *, prefix: str = "kraken_v2") -> None:
        self._out_dir = out_dir
        self._prefix = prefix
        self._date: str | None = None
        self._handle: IO[bytes] | None = None
        self.lines_written = 0
        self.bytes_written = 0

    def __enter__(self) -> Self:
        self._out_dir.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def out_dir(self) -> Path:
        return self._out_dir

    def path_for(self, date: str) -> Path:
        return self._out_dir / f"{self._prefix}_{date}.jsonl"

    @property
    def current_path(self) -> Path | None:
        return None if self._date is None else self.path_for(self._date)

    def append(self, line: Mapping[str, Any]) -> None:
        """Validate, then write. Raises ``SchemaError`` and writes nothing on a bad line.

        Named ``append`` rather than ``write`` because that is the whole contract:
        there is no other verb on this object. `tests/harness/fake_kraken.py`'s
        ``FakeRecorder`` exposes the same one method, so an engine written against
        either works against the other.
        """
        record = dict(line)
        validate_line(record)
        date = utc_date_from_iso(str(record["ts_recv"]))
        if date != self._date:
            self._rotate(date)
        handle = self._handle
        if handle is None:  # pragma: no cover - _rotate always sets it
            raise RuntimeError("recorder has no open file")
        payload = orjson.dumps(record)
        handle.write(payload)
        handle.write(b"\n")
        handle.flush()
        self.lines_written += 1
        self.bytes_written += len(payload) + 1

    def _rotate(self, date: str) -> None:
        if self._handle is not None:
            self._handle.close()
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._handle = self.path_for(date).open("ab")
        self._date = date

    def close(self) -> None:
        """Close the open file. Idempotent.

        Worth calling even on Windows-hostile paths: an open handle on a file inside
        a directory something is about to remove is a ``PermissionError`` at
        collection time rather than a warning.
        """
        if self._handle is not None:
            self._handle.close()
            self._handle = None
