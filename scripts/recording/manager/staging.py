"""Staging, verification, and the merge into the main archive.

**Nothing enters the main archive without passing through here first.** A file
arrives in a staging directory, is parsed from end to end, is copied with its
bytes read back off the destination, and only then is it named as an archive file.
A truncated transfer — a dropped SSH connection, a disk that filled, a USB stick
pulled early — dies in staging and the main archive never learns it existed.

The alternative, writing the transfer straight into `data/raw/`, fails in the way
that costs most: the file is *there*, it has the right name, every tool globs it,
and it is short. Nothing reports it, because a short JSONL file is a valid JSONL
file. It would be found months later by somebody replaying the day.

## What is checked, in order

1. **The name parses.** A file whose name carries no source and no date cannot be
   placed in the archive, because every piece of arithmetic over the archive —
   coverage, gaps, eligibility to move — reads the date out of the name.
2. **Every line parses.** End to end, once. A malformed line in the middle refuses
   the file. A truncated *final* line is tolerated and named: the recorder flushes
   every line, so a forced kill costs at most a partial last one, and that shape is
   already in the committed archive. Refusing it would refuse real data, and
   repairing it is what invariant 11 forbids.
3. **Nothing is overwritten.** Names carry their source, so a collision means the
   same source recorded the same day twice — one of the two files is not what its
   name says. Both are kept and the operator is told.
4. **The copy is read back.** Hashed on the way out, hashed again off the
   destination, and only then renamed into place.

## Overlapping coverage is reported, never resolved

Two sources covering one hour is an **independent observation**, and the
difference between them is the only measurement there is of what a single recorder
misses — a dropped subscription, a reconnect gap, a network that saw a different
side of an exchange outage. A merger that quietly kept one would destroy exactly
the comparison that makes a second recorder worth running. Both are kept, and the
overlap is reported with its exact span.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

NAME_SEPARATOR: Final = "__"
PARTIAL_SUFFIX: Final = ".partial"
CHUNK: Final = 8 * 1024 * 1024
TAIL_BYTES: Final = 256 * 1024


class StagingError(RuntimeError):
    """The import cannot safely proceed. Nothing has entered the archive."""


class Verdict:
    """One staged file and what was decided about it.

    Not a ``@dataclass`` — see ``registry.Source`` for why the decorator cannot be
    used in a module loaded by path.
    """

    __slots__ = ("detail", "lines", "name", "note", "path", "source_id", "span", "state")

    def __init__(
        self,
        *,
        path: Path,
        name: str,
        state: str,
        detail: str,
        source_id: str | None = None,
        lines: int = 0,
        span: tuple[float | None, float | None] = (None, None),
        note: str | None = None,
    ) -> None:
        self.path = path
        self.name = name
        #: `merged` | `refused` | `collision` | `staged`
        self.state = state
        self.detail = detail
        self.source_id = source_id
        self.lines = lines
        self.span = span
        self.note = note

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "detail": self.detail,
            "source_id": self.source_id,
            "lines": self.lines,
            "first": _iso(self.span[0]),
            "last": _iso(self.span[1]),
            "note": self.note,
        }


def _iso(moment: float | None) -> str | None:
    if moment is None:
        return None
    return datetime.fromtimestamp(moment, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Names and times
# --------------------------------------------------------------------------- #


def parse_archive_name(name: str) -> tuple[str | None, str | None, str | None]:
    """``(prefix, source_id, date text)``, each None when unreadable."""
    if not name.endswith(".jsonl"):
        return None, None, None
    stem = name[: -len(".jsonl")]
    if NAME_SEPARATOR in stem:
        parts = stem.split(NAME_SEPARATOR)
        if len(parts) != 3:
            return None, None, None
        prefix, source_id, tail = parts
        return prefix or None, source_id or None, _valid_day(tail)
    if len(stem) > 11 and stem[-11] == "_":
        return stem[:-11] or None, None, _valid_day(stem[-10:])
    return None, None, None


def _valid_day(text: str) -> str | None:
    try:
        datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None
    return text


def line_time(line: dict[str, Any]) -> float | None:
    for key in ("ts_recv", "minute"):
        value = line.get(key)
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return None
    return None


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #


def verify_parses(path: Path) -> tuple[bool, int, str | None, tuple[float | None, float | None]]:
    """``(ok, lines, problem, (first, last))``. Reads the whole file once."""
    count = 0
    first: float | None = None
    last: float | None = None
    truncated = False
    try:
        with path.open("rb") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                count += 1
                if not raw.endswith(b"\n"):
                    # The final line. Judged below, not here: a partial tail is a
                    # known, harmless shape and the rest of the file is real data.
                    try:
                        json.loads(raw)
                    except ValueError:
                        truncated = True
                        count -= 1
                    break
                try:
                    parsed = json.loads(raw)
                except ValueError as exc:
                    return False, count, f"line {count} is not JSON: {exc}", (first, last)
                if not isinstance(parsed, dict):
                    return False, count, f"line {count} is not a JSON object", (first, last)
                moment = line_time(parsed)
                if moment is not None:
                    if first is None:
                        first = moment
                    last = moment
    except OSError as exc:
        return False, count, f"could not be read: {exc}", (first, last)

    if count == 0:
        return False, 0, "is empty, so it carries no coverage and nothing to merge", (None, None)
    if truncated:
        return (
            True,
            count,
            (
                "its final line is truncated - the shape a forced kill leaves. Merged "
                "as is; a recording is never repaired (invariant 11)."
            ),
            (first, last),
        )
    return True, count, None, (first, last)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(CHUNK)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest()


def copy_verified(source: Path, target: Path) -> tuple[str, int]:
    """Copy, read the copy back off the destination, and only then name it."""
    partial = target.with_name(target.name + PARTIAL_SUFFIX)
    hasher = hashlib.sha256()
    written = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as src, partial.open("wb") as dst:
            while True:
                block = src.read(CHUNK)
                if not block:
                    break
                hasher.update(block)
                dst.write(block)
                written += len(block)
            dst.flush()
            os.fsync(dst.fileno())
        expected = hasher.hexdigest()
        if digest(partial) != expected:
            raise StagingError(
                f"{source.name} did not arrive intact: what was written back does not "
                f"match what was read. Nothing was placed in the archive."
            )
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return hasher.hexdigest(), written


# --------------------------------------------------------------------------- #
# The merge
# --------------------------------------------------------------------------- #


def existing_spans(archive_dir: Path) -> list[dict[str, Any]]:
    """``(source, first, last)`` for everything already in the archive.

    From each file's first and last lines only — two reads a file, whatever its
    size. The archive is tens of gigabytes and is not the thing being validated
    here; it is the thing being compared against.
    """
    found: list[dict[str, Any]] = []
    if not archive_dir.is_dir():
        return found
    for path in sorted(archive_dir.glob("*.jsonl")):
        if not path.is_file():
            continue
        _prefix, source_id, day = parse_archive_name(path.name)
        first, last = _edges(path)
        if first is None and day is not None:
            midnight = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
            first = midnight.timestamp()
            last = midnight.timestamp() + 86_399
        found.append(
            {
                "name": path.name,
                "source_id": source_id or "unnamed",
                "first": first,
                "last": last,
            }
        )
    return found


def _edges(path: Path) -> tuple[float | None, float | None]:
    first: float | None = None
    last: float | None = None
    try:
        size = path.stat().st_size
        if size == 0:
            return None, None
        with path.open("rb") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                try:
                    parsed = json.loads(raw)
                except ValueError:
                    break
                if isinstance(parsed, dict):
                    first = line_time(parsed)
                break
            handle.seek(max(0, size - TAIL_BYTES))
            tail = handle.read()
        for raw in reversed(tail.split(b"\n")):
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                last = line_time(parsed)
                if last is not None:
                    break
    except OSError:
        return None, None
    return first, last


def find_overlaps(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every pair of files from *different* sources whose spans intersect.

    Different sources only. Two files from one source overlapping is a filename
    collision, which is refused before it reaches here; two sources overlapping is
    the ordinary, expected and useful case, and it is reported so that nobody
    later mistakes doubled coverage for duplicated data.
    """
    usable = [item for item in spans if item["first"] is not None and item["last"] is not None]
    usable.sort(key=lambda item: item["first"])
    found: list[dict[str, Any]] = []
    for index, left in enumerate(usable):
        for right in usable[index + 1 :]:
            if right["source_id"] == left["source_id"]:
                continue
            if right["first"] > left["last"]:
                # Sorted by start, so nothing after this one can overlap either.
                break
            start = max(left["first"], right["first"])
            end = min(left["last"], right["last"])
            if start < end:
                found.append(
                    {
                        "left": left["name"],
                        "right": right["name"],
                        "left_source": left["source_id"],
                        "right_source": right["source_id"],
                        "from": _iso(start),
                        "to": _iso(end),
                        "hours": (end - start) / 3600.0,
                    }
                )
    return found


def merge(staging_dir: Path, archive_dir: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Verify everything in staging, merge what passes, report the rest.

    Returns a report rather than raising: a run where one file of six was corrupt
    should merge the other five and say clearly which one it did not, because
    refusing the batch means somebody re-transfers 12 GB to recover from one bad
    file.
    """
    if not staging_dir.is_dir():
        raise StagingError(f"the staging directory {staging_dir} does not exist")
    if not archive_dir.is_dir():
        raise StagingError(
            f"the archive {archive_dir} does not exist. It is not created here: "
            f"merging into a directory that is not the archive you meant is how a day "
            f"of recordings ends up somewhere nobody looks."
        )

    verdicts: list[Verdict] = []
    accepted: list[dict[str, Any]] = []

    for path in sorted(staging_dir.glob("*.jsonl")):
        if not path.is_file():
            continue
        _prefix, source_id, day = parse_archive_name(path.name)
        if day is None:
            verdicts.append(
                Verdict(
                    path=path,
                    name=path.name,
                    state="refused",
                    detail=(
                        "its name carries no UTC date, and every piece of arithmetic "
                        "over the archive reads the date out of the name"
                    ),
                )
            )
            continue

        ok, lines, problem, span = verify_parses(path)
        if not ok:
            verdicts.append(
                Verdict(
                    path=path,
                    name=path.name,
                    state="refused",
                    detail=problem or "did not parse",
                    source_id=source_id,
                    lines=lines,
                )
            )
            continue

        target = archive_dir / path.name
        if target.exists():
            verdicts.append(
                Verdict(
                    path=path,
                    name=path.name,
                    state="collision",
                    detail=(
                        "a file of that name is already in the archive. Nothing is ever "
                        "overwritten: same source and same day with two different files "
                        "means one of them is not what its name says. Both are kept; "
                        "compare them by hand."
                    ),
                    source_id=source_id,
                    lines=lines,
                    span=span,
                    note=problem,
                )
            )
            continue

        if dry_run:
            verdicts.append(
                Verdict(
                    path=path,
                    name=path.name,
                    state="staged",
                    detail="verified and ready to merge; nothing was copied",
                    source_id=source_id,
                    lines=lines,
                    span=span,
                    note=problem,
                )
            )
        else:
            try:
                _hash, size = copy_verified(path, target)
            except (OSError, StagingError) as exc:
                verdicts.append(
                    Verdict(
                        path=path,
                        name=path.name,
                        state="refused",
                        detail=str(exc),
                        source_id=source_id,
                        lines=lines,
                        span=span,
                    )
                )
                continue
            verdicts.append(
                Verdict(
                    path=path,
                    name=path.name,
                    state="merged",
                    detail=f"{size / 1e6:.1f} MB, {lines} lines",
                    source_id=source_id,
                    lines=lines,
                    span=span,
                    note=problem,
                )
            )
        accepted.append(
            {
                "name": path.name,
                "source_id": source_id or "unnamed",
                "first": span[0],
                "last": span[1],
                "date": day,
            }
        )

    overlaps = find_overlaps(existing_spans(archive_dir) + [
        item for item in accepted if not (archive_dir / item["name"]).exists()
    ])

    merged = [item for item in verdicts if item.state == "merged"]
    return {
        "staging_dir": staging_dir.as_posix(),
        "archive_dir": archive_dir.as_posix(),
        "dry_run": dry_run,
        "files": [item.as_dict() for item in verdicts],
        "merged": len(merged),
        "refused": len([item for item in verdicts if item.state == "refused"]),
        "collisions": len([item for item in verdicts if item.state == "collision"]),
        "dates": sorted({item["date"] for item in accepted if item["date"]}),
        "sources": sorted({item["source_id"] for item in accepted}),
        "overlaps": overlaps,
    }
