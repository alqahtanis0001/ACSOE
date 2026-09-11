"""What the archive actually covers: hours per source per UTC day, and the holes.

Every number on the Coverage and Gaps screens comes from here, and all of them are
measured from the files rather than assumed from their names. A file named
``kraken_v2__msi__2026-09-11.jsonl`` might hold twenty-four hours or forty
seconds, and the difference is the entire question those screens exist to answer.

## Hours recorded, and what the number means

For each file: the span from its first line to its last, **minus the time inside
`gap` markers**. A gap marker is written on reconnect and carries the measured
length of the break, so subtracting it is not an estimate — it is the recorder's
own record of time it was not receiving.

What the number therefore means is *hours of stream actually captured on that
day*. A day where the recorder started at 09:00 reads 15h, not 24h, and that is
the truth an operator needs: the missing nine hours are missing.

## Why this is fast enough to run on a page load

The obvious implementation parses every line of every file, which is 21 GB and
several minutes. Instead:

* the first and last lines come from a head read and a tail seek, so the span
  costs two reads whatever the file size;
* gap markers are found by searching raw bytes in 8 MB chunks — `bytes.find` is
  memchr-backed, and a 1.8 GB file scans in about 1.4 seconds — and only the few
  lines that match are parsed;
* every result is cached against the file's `(size, mtime)`, so only the file
  being written to is ever re-scanned.

The cache is a plain JSON file and deleting it costs one rescan. It is never
authoritative about anything: if it disagrees with the file it is discarded,
because the file is the record and the cache is a convenience.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Final

NAME_SEPARATOR: Final = "__"

#: Bytes read from the head of a file to find its first line, and from the tail to
#: find its last. One raw line is a book frame, a few kilobytes at most.
EDGE_BYTES: Final = 256 * 1024

CHUNK: Final = 8 * 1024 * 1024

#: What is searched for to find a gap marker, before anything is parsed.
#:
#: **Deliberately `"gap"` and not `"kind":"gap"`.** The recorder writes with
#: `orjson`, which emits compact separators, so the archive on this machine says
#: `"kind":"gap"` with no space — and a needle written that way found every marker
#: in it and **none at all** in a file produced by `json.dumps`, which writes
#: `"kind": "gap"`. That failure is silent and it is the worst shape a failure
#: here can take: the span is still right, so the day reports MORE hours recorded
#: than were recorded, and an operator reads a gap-free day over a recorder that
#: was disconnected for an hour.
#:
#: This archive will eventually hold files merged from machines that are not this
#: one, so matching one serialiser's spacing is not good enough. Every candidate
#: line is parsed and checked properly; the needle only decides which lines are
#: worth parsing, and a false positive costs one `json.loads`.
GAP_NEEDLE: Final = b'"gap"'

CACHE_FILENAME: Final = ".coverage-cache.json"
CACHE_VERSION: Final = 1

#: A file modified within this many seconds is measured fresh every time and is
#: never cached.
#:
#: The cache key is `(name, size, mtime_ns)`, which is not quite enough on its
#: own. Windows updates the system clock in ~15.6 ms steps, so two writes in quick
#: succession can share an `st_mtime_ns` exactly — and if they also happen to
#: produce the same length, which a rewrite of the same day easily does, the key
#: collides and a stale measurement is served as current. A test caught it;
#: `archive_move.py` and the merge both produce same-length rewrites, so it was
#: reachable in production too.
#:
#: Rather than hashing every file to make the key exact, which would defeat the
#: cache entirely, a file that has just been touched is simply not cached. That
#: costs nothing worth having: the cache exists to avoid rescanning the settled
#: archive, and the file currently being appended to has to be re-measured on
#: every request anyway.
CACHE_SETTLE_S: Final = 3.0


class FileCoverage:
    """One archive file, measured. Not a ``@dataclass`` — see ``registry.Source``."""

    __slots__ = (
        "day",
        "first_ts",
        "gap_count",
        "gap_seconds",
        "last_ts",
        "name",
        "prefix",
        "size",
        "source_id",
    )

    def __init__(
        self,
        *,
        name: str,
        prefix: str | None,
        source_id: str,
        day: date | None,
        size: int,
        first_ts: float | None,
        last_ts: float | None,
        gap_seconds: float,
        gap_count: int,
    ) -> None:
        self.name = name
        self.prefix = prefix
        self.source_id = source_id
        self.day = day
        self.size = size
        self.first_ts = first_ts
        self.last_ts = last_ts
        self.gap_seconds = gap_seconds
        self.gap_count = gap_count

    @property
    def span_seconds(self) -> float:
        if self.first_ts is None or self.last_ts is None:
            return 0.0
        return max(0.0, self.last_ts - self.first_ts)

    @property
    def recorded_seconds(self) -> float:
        """Span minus measured gaps, floored at zero.

        Floored rather than allowed negative: gap markers are measured
        independently of the span and a pathological file could in principle
        subtract more than it spans. Negative hours would be nonsense on a screen
        whose whole job is to be believed.
        """
        return max(0.0, self.span_seconds - self.gap_seconds)

    @property
    def recorded_hours(self) -> float:
        return self.recorded_seconds / 3600.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_id": self.source_id,
            "day": self.day.isoformat() if self.day else None,
            "size": self.size,
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
            "gap_seconds": self.gap_seconds,
            "gap_count": self.gap_count,
            "recorded_hours": self.recorded_hours,
        }


# --------------------------------------------------------------------------- #
# Names and times
# --------------------------------------------------------------------------- #


def parse_archive_name(name: str) -> tuple[str | None, str | None, date | None]:
    """``(prefix, source_id, day)``. Understands the pre-source_id shape too.

    The same parser `archive_move.py` and `archive_merge.py` carry, duplicated for
    the same reason they duplicate it: `scripts/` is not a package because
    `record.py` has to stay copyable to a bare server on its own.
    """
    if not name.endswith(".jsonl"):
        return None, None, None
    stem = name[: -len(".jsonl")]
    if NAME_SEPARATOR in stem:
        parts = stem.split(NAME_SEPARATOR)
        if len(parts) != 3:
            return None, None, None
        prefix, source_id, tail = parts
        return prefix or None, source_id or None, _parse_day(tail)
    if len(stem) > 11 and stem[-11] == "_":
        return stem[:-11] or None, None, _parse_day(stem[-10:])
    return None, None, None


def _parse_day(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=UTC).date()
    except ValueError:
        return None


def line_time(line: dict[str, Any]) -> float | None:
    """When a line happened, as epoch seconds.

    A raw line carries `ts_recv`; a tier 2 summary row carries `minute` and no
    `ts_recv` at all. Both archives are measured by this module.
    """
    for key in ("ts_recv", "minute"):
        value = line.get(key)
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return None
    return None


# --------------------------------------------------------------------------- #
# Measuring one file
# --------------------------------------------------------------------------- #


def _first_line_time(handle: Any) -> float | None:
    handle.seek(0)
    head = handle.read(EDGE_BYTES)
    for raw in head.split(b"\n"):
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return line_time(parsed)
    return None


def _last_line_time(handle: Any, size: int) -> float | None:
    handle.seek(max(0, size - EDGE_BYTES))
    tail = handle.read()
    for raw in reversed(tail.split(b"\n")):
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except ValueError:
            # The final line of a file the recorder was killed in the middle of.
            # Step back one; it is not an error and it is not the end of the data.
            continue
        if isinstance(parsed, dict):
            return line_time(parsed)
    return None


def _scan_gaps(handle: Any) -> tuple[float, int]:
    """``(seconds inside gap markers, how many)``.

    Searches raw bytes in chunks and parses only the lines that match, so the cost
    is a read rather than 30 million `json.loads` calls. The overlap carried
    between chunks is the needle's length, so a marker straddling a chunk boundary
    is still found.
    """
    handle.seek(0)
    seconds = 0.0
    count = 0
    carry = b""
    overlap = len(GAP_NEEDLE)
    while True:
        chunk = handle.read(CHUNK)
        if not chunk:
            break
        window = carry + chunk
        position = 0
        while True:
            found = window.find(GAP_NEEDLE, position)
            if found < 0:
                break
            position = found + 1
            start = window.rfind(b"\n", 0, found) + 1
            end = window.find(b"\n", found)
            if end < 0:
                # The line runs past this window and cannot be parsed here. It is
                # not counted: counting an unparsed candidate would inflate the
                # gap count with book frames that merely contain the word.
                continue
            try:
                line = json.loads(window[start:end])
            except ValueError:
                continue
            if not isinstance(line, dict) or line.get("kind") != "gap":
                continue
            count += 1
            payload = line.get("payload")
            if isinstance(payload, dict):
                gap_ms = payload.get("gap_ms")
                if isinstance(gap_ms, (int, float)) and gap_ms > 0:
                    seconds += float(gap_ms) / 1000.0
        carry = window[-overlap:] if len(window) >= overlap else window
    return seconds, count


def measure(path: Path) -> FileCoverage:
    """Everything this module knows about one archive file."""
    prefix, source_id, day = parse_archive_name(path.name)
    size = path.stat().st_size
    first: float | None = None
    last: float | None = None
    gap_seconds = 0.0
    gap_count = 0
    if size:
        with path.open("rb") as handle:
            first = _first_line_time(handle)
            last = _last_line_time(handle, size)
            gap_seconds, gap_count = _scan_gaps(handle)
    return FileCoverage(
        name=path.name,
        prefix=prefix,
        # A file with no source in its name still came from a machine: the one
        # that wrote the original archive. Naming it keeps it in the grid instead
        # of dropping it out of every total.
        source_id=source_id or "unnamed",
        day=day,
        size=size,
        first_ts=first,
        last_ts=last,
        gap_seconds=gap_seconds,
        gap_count=gap_count,
    )


# --------------------------------------------------------------------------- #
# The cache
# --------------------------------------------------------------------------- #


class Cache:
    """Measurements keyed by `(name, size, mtime)`. Convenience, never authority."""

    __slots__ = ("_dirty", "_entries", "_path")

    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: dict[str, dict[str, Any]] = {}
        self._dirty = False
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                loaded = None
            if isinstance(loaded, dict) and loaded.get("version") == CACHE_VERSION:
                entries = loaded.get("entries")
                if isinstance(entries, dict):
                    self._entries = {
                        key: value for key, value in entries.items() if isinstance(value, dict)
                    }

    @staticmethod
    def _key(path: Path) -> str:
        """Name, size, and modification time **in nanoseconds**.

        `int(st_mtime)` truncates to the second and was wrong: a file rewritten
        within the same second to the same length — which a merge or a move can
        produce, and which a test produced immediately — keeps its key, and the
        stale measurement is served as if it were current. Coverage would then
        report yesterday's hours for a file that had changed. Nanoseconds cost
        nothing and remove the whole class of collision.
        """
        stat = path.stat()
        return f"{path.name}|{stat.st_size}|{stat.st_mtime_ns}"

    def measure(self, path: Path) -> FileCoverage:
        if self._too_recent(path):
            # Just written, so its key cannot be trusted to change next time.
            # Measured fresh and deliberately not stored.
            return measure(path)
        key = self._key(path)
        entry = self._entries.get(key)
        if entry is not None:
            return FileCoverage(
                name=path.name,
                prefix=entry.get("prefix"),
                source_id=str(entry.get("source_id", "unnamed")),
                day=_parse_day(str(entry.get("day"))) if entry.get("day") else None,
                size=int(entry.get("size", 0)),
                first_ts=entry.get("first_ts"),
                last_ts=entry.get("last_ts"),
                gap_seconds=float(entry.get("gap_seconds", 0.0)),
                gap_count=int(entry.get("gap_count", 0)),
            )
        measured = measure(path)
        self._entries[key] = {
            "prefix": measured.prefix,
            "source_id": measured.source_id,
            "day": measured.day.isoformat() if measured.day else None,
            "size": measured.size,
            "first_ts": measured.first_ts,
            "last_ts": measured.last_ts,
            "gap_seconds": measured.gap_seconds,
            "gap_count": measured.gap_count,
        }
        self._dirty = True
        return measured

    @staticmethod
    def _too_recent(path: Path) -> bool:
        try:
            return (time.time() - path.stat().st_mtime) < CACHE_SETTLE_S
        except OSError:  # pragma: no cover - the caller stat()s it immediately after
            return True

    def save(self) -> None:
        if not self._dirty:
            return
        # Keep only the most recent entries. The key carries size and mtime, so a
        # file appended to all day leaves one entry per scan; without a bound the
        # cache would grow forever with measurements of files that no longer exist
        # in that state.
        entries = dict(list(self._entries.items())[-4000:])
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"version": CACHE_VERSION, "entries": entries}), encoding="utf-8"
            )
        except OSError:
            # A cache that cannot be written is not a failure worth stopping for.
            return
        self._dirty = False


# --------------------------------------------------------------------------- #
# Scanning a directory, and the grid
# --------------------------------------------------------------------------- #


def scan_directory(directory: Path, *, cache: Cache | None = None) -> list[FileCoverage]:
    """Measure every ``*.jsonl`` in a directory."""
    if not directory.is_dir():
        return []
    found: list[FileCoverage] = []
    for path in sorted(directory.glob("*.jsonl")):
        if not path.is_file():
            continue
        try:
            found.append(cache.measure(path) if cache is not None else measure(path))
        except OSError:
            continue
    return found


def build_grid(files: list[FileCoverage]) -> dict[str, Any]:
    """Sources down the side, UTC dates across, hours in each cell.

    Every date between the first and the last is present, including the ones
    nothing covered. **That is the point of the grid** — a grid built only from
    the dates that have files cannot show a missing week, because a missing week
    has no files in it, and the hole would close up silently between two columns
    that look adjacent.
    """
    by_source: dict[str, dict[str, float]] = {}
    files_by_cell: dict[str, dict[str, list[str]]] = {}
    days: set[date] = set()
    undated: list[str] = []

    for item in files:
        if item.day is None:
            undated.append(item.name)
            continue
        days.add(item.day)
        key = item.day.isoformat()
        by_source.setdefault(item.source_id, {})
        by_source[item.source_id][key] = by_source[item.source_id].get(key, 0.0) + (
            item.recorded_hours
        )
        files_by_cell.setdefault(item.source_id, {}).setdefault(key, []).append(item.name)

    if days:
        first, last = min(days), max(days)
        span = [
            (first + timedelta(days=offset)).isoformat()
            for offset in range((last - first).days + 1)
        ]
    else:
        span = []

    return {
        "dates": span,
        "sources": sorted(by_source),
        "cells": by_source,
        "files": files_by_cell,
        "undated": sorted(undated),
        "total_hours": sum(sum(row.values()) for row in by_source.values()),
    }


def find_gaps(grid: dict[str, Any], *, covered_threshold_h: float = 0.0) -> dict[str, Any]:
    """Dates nothing covered, and dates exactly one source covered.

    The second list is not a failure and is not shown as one. It is the list of
    days for which there is **no second observation** — nothing to compare the
    recording against, so a dropped subscription or a bad feed on that day cannot
    be detected at all, then or ever. That is worth knowing and it is not worth
    an alarm.

    ``covered_threshold_h`` is what counts as covered. Zero means any recording at
    all, which is the honest default: a day with four minutes on it is a day with
    four minutes on it, not an empty day, and rounding it away would hide the
    shape of a recorder that is crash-looping.
    """
    dates: list[str] = list(grid.get("dates", []))
    cells: dict[str, dict[str, float]] = grid.get("cells", {})
    uncovered: list[str] = []
    single: list[dict[str, Any]] = []
    multiple: list[dict[str, Any]] = []

    for day in dates:
        covering = [
            {"source_id": source, "hours": hours[day]}
            for source, hours in cells.items()
            if hours.get(day, 0.0) > covered_threshold_h
        ]
        if not covering:
            uncovered.append(day)
        elif len(covering) == 1:
            single.append({"date": day, "source_id": covering[0]["source_id"], **covering[0]})
        else:
            multiple.append(
                {
                    "date": day,
                    "sources": sorted(item["source_id"] for item in covering),
                    "hours": {item["source_id"]: item["hours"] for item in covering},
                }
            )

    return {
        "uncovered": uncovered,
        "single_source": single,
        "multiple_sources": multiple,
        "dates_examined": len(dates),
    }
