#!/usr/bin/env python
"""Merge a foreign archive into the main one, and report where they overlap.

A "foreign" archive is any directory of recorder output that was written
somewhere else: a second machine, a VPS recording the same pairs from a different
network, a drive that came back from cold storage. Bringing one in is mostly a
file copy, and the three interesting parts are what this script exists for.

## It never overwrites

Filenames carry their source (``kraken_v2__<source_id>__2026-09-11.jsonl``), so a
collision only happens when the same source recorded the same day twice — which
means one of the two files is not what its name says. Both are kept and the
operator is told. A merge that overwrites is a merge that can delete a day of
order-book data on the strength of a name, and order-book data cannot be
re-recorded.

## It parses every line before it copies anything

A file that does not parse is a file that will fail in the middle of a replay
weeks from now, on a machine that no longer has the original. The check is cheap
relative to the copy and is done first, for the whole file: a partial final line
from a killed recorder is reported as exactly that and the file is still merged,
because a truncated tail is a known, harmless shape that the archive already
contains. Anything else — a corrupt line in the middle, a line that is not a JSON
object, a file that is not JSONL at all — refuses that file and merges the rest.

## It reports overlapping coverage instead of resolving it

**Two sources covering the same hour is information, not a conflict.** It is two
independent observations of one market, and the disagreement between them is a
measurement of what a single recorder misses — dropped frames, reconnect gaps, a
network that saw a different side of an exchange outage. A merger that silently
picked one would destroy exactly the comparison that makes a second recorder worth
running. So overlaps are printed, with their spans, and both files are kept.

Coverage is read from the files themselves: the first and last line of each, which
is two reads regardless of how big the file is. The filename's date is used only
when a file's own lines cannot supply a span.

Usage::

    python scripts/archive_merge.py --source E:/from-vps/raw --dry-run
    python scripts/archive_merge.py --source E:/from-vps/raw
    python scripts/archive_merge.py --source E:/from-vps/raw --dest E:/acsoe/raw
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

DEFAULT_ARCHIVE_DIR: Final = Path("data") / "raw"

CONFIG_CANDIDATES: Final = (
    Path("config") / "recorder.yaml",
    Path("config") / "default.yaml",
)
CONFIG_SECTION: Final = "recorder"

NAME_SEPARATOR: Final = "__"
PARTIAL_SUFFIX: Final = ".partial"
CHUNK: Final = 8 * 1024 * 1024

#: How much of the end of a file to read when looking for its last complete line.
#: One raw line is a book frame, a few kilobytes at most; 256 KiB is several
#: hundred of them and bounds the read on a 2 GB file to something instant.
TAIL_BYTES: Final = 256 * 1024


class MergeRefusedError(RuntimeError):
    """The merge cannot safely start. Nothing has been copied."""


class Coverage:
    """One archive file's span, and where it came from.

    Not a ``@dataclass`` — see the note on ``ArchiveFile`` in
    ``scripts/archive_move.py`` and on ``PairStat`` in ``scripts/record.py``.
    """

    __slots__ = ("day", "end", "name", "path", "source_id", "start")

    def __init__(
        self,
        *,
        path: Path,
        name: str,
        source_id: str,
        day: date | None,
        start: datetime | None,
        end: datetime | None,
    ) -> None:
        self.path = path
        self.name = name
        self.source_id = source_id
        self.day = day
        self.start = start
        self.end = end

    def span(self) -> tuple[datetime, datetime] | None:
        """The interval this file covers, from its own lines or from its date."""
        if self.start is not None and self.end is not None and self.end >= self.start:
            return self.start, self.end
        if self.day is not None:
            midnight = datetime(self.day.year, self.day.month, self.day.day, tzinfo=UTC)
            return midnight, midnight.replace(hour=23, minute=59, second=59)
        return None


# --------------------------------------------------------------------------- #
# Names and times
# --------------------------------------------------------------------------- #


def parse_archive_name(name: str) -> tuple[str | None, str | None, date | None]:
    """``(prefix, source_id, day)``. Understands the pre-source_id shape too.

    Duplicated from ``scripts/archive_move.py`` rather than shared, for the same
    reason its config reader is duplicated: ``scripts/`` is not a package, because
    ``record.py`` must stay copyable to a bare server on its own.
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


def line_time(line: dict[str, Any]) -> datetime | None:
    """When a line happened.

    A raw line carries ``ts_recv``; a tier 2 summary row carries ``minute`` and no
    ``ts_recv`` at all. Both archives are merged by this script, so both are read.
    """
    for key in ("ts_recv", "minute"):
        value = line.get(key)
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
    return None


# --------------------------------------------------------------------------- #
# Does it parse?
# --------------------------------------------------------------------------- #


def check_parses(path: Path) -> tuple[bool, int, str | None]:
    """``(ok, lines, problem)``. Reads the whole file once.

    A truncated final line is tolerated and named in ``problem``: the recorder
    flushes every line and a forced kill costs at most a partial last one, so that
    shape is already in the committed archive and refusing it would refuse real
    data. A malformed line anywhere else fails the file.
    """
    count = 0
    last_line = b""
    try:
        with path.open("rb") as handle:
            for raw in handle:
                last_line = raw
                if not raw.strip():
                    continue
                count += 1
                if not raw.endswith(b"\n"):
                    break  # the final line; judged below
                try:
                    parsed = json.loads(raw)
                except ValueError as exc:
                    return False, count, f"line {count} is not JSON: {exc}"
                if not isinstance(parsed, dict):
                    return False, count, f"line {count} is not a JSON object"
    except OSError as exc:
        return False, count, f"could not be read: {exc}"

    if count == 0:
        return False, 0, "is empty, so it carries no coverage and nothing to merge"
    if last_line and not last_line.endswith(b"\n"):
        try:
            json.loads(last_line)
        except ValueError:
            return True, count, (
                "its final line is truncated - the shape a forced kill leaves. "
                "Merged as is; a recording is never repaired (invariant 11)."
            )
    return True, count, None


def read_span(path: Path) -> tuple[datetime | None, datetime | None]:
    """``(first, last)`` timestamps, from the first and last lines only."""
    first: datetime | None = None
    last: datetime | None = None
    try:
        with path.open("rb") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                # An unreadable first line has already been reported by
                # `check_parses`; here it only means the span falls back to the
                # filename's date.
                with contextlib.suppress(ValueError):
                    first = line_time(json.loads(raw))
                break
            size = path.stat().st_size
            handle.seek(max(0, size - TAIL_BYTES))
            tail = handle.read()
        for raw in reversed(tail.split(b"\n")):
            if not raw.strip():
                continue
            try:
                last = line_time(json.loads(raw))
            except ValueError:
                continue
            if last is not None:
                break
    except OSError:
        return None, None
    return first, last


# --------------------------------------------------------------------------- #
# Overlap
# --------------------------------------------------------------------------- #


def overlaps(files: list[Coverage]) -> list[tuple[Coverage, Coverage, datetime, datetime]]:
    """Every pair of files from *different* sources whose spans intersect.

    Two files from the same source overlapping is a defect worth seeing too, but
    it is not what this reports: same-source same-day is a filename collision and
    is refused before it gets here, and same-source different-day spans cannot
    overlap unless a clock moved. Different sources overlapping is the ordinary,
    expected, useful case — two recorders watching one market — and it is
    reported so that nobody later mistakes the doubled coverage for duplicated
    data.
    """
    found: list[tuple[Coverage, Coverage, datetime, datetime]] = []
    far_future = datetime.max.replace(tzinfo=UTC)
    ordered = sorted(files, key=lambda item: (item.span() or (far_future, far_future))[0])
    for index, left in enumerate(ordered):
        left_span = left.span()
        if left_span is None:
            continue
        for right in ordered[index + 1 :]:
            right_span = right.span()
            if right_span is None or right.source_id == left.source_id:
                continue
            start = max(left_span[0], right_span[0])
            end = min(left_span[1], right_span[1])
            if start < end:
                found.append((left, right, start, end))
    return found


# --------------------------------------------------------------------------- #
# Copy, verified
# --------------------------------------------------------------------------- #


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
    """Copy, read the copy back off the destination, and only then name it.

    The same shape as ``scripts/archive_move.py``. The stakes are lower here —
    this script never deletes the original — but a corrupt file under a real
    archive name is still a file somebody will replay in six months.
    """
    partial = target.with_name(target.name + PARTIAL_SUFFIX)
    hasher = hashlib.sha256()
    written = 0
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
        source_hash = hasher.hexdigest()
        if digest(partial) != source_hash:
            raise MergeRefusedError(f"{source.name} did not arrive intact; nothing was kept")
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return source_hash, written


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #


def load_recorder_config(explicit: Path | None = None) -> dict[str, Any]:
    """The ``recorder:`` mapping, or ``{}``. Duplicated on purpose; see above."""
    if explicit is not None and not explicit.is_file():
        raise FileNotFoundError(f"--config {explicit} does not exist")
    try:
        import yaml  # optional
    except ImportError:
        if explicit is not None:
            raise
        return {}
    here = Path(__file__).resolve().parent.parent
    searched: list[Path] = (
        [explicit]
        if explicit is not None
        else [base / candidate for base in (Path.cwd(), here) for candidate in CONFIG_CANDIDATES]
    )
    for path in searched:
        if not path.is_file():
            continue
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get(CONFIG_SECTION), dict):
            return dict(loaded[CONFIG_SECTION])
    return {}


def _config_str(config: dict[str, Any], key: str) -> str | None:
    value = config.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def survey(
    directory: Path, *, read_lines: bool
) -> tuple[list[Coverage], list[tuple[str, str]], list[tuple[str, str]]]:
    """``(coverage, refused, noted)`` for every ``*.jsonl`` in a directory.

    ``refused`` is files that did not parse and are therefore not in ``coverage``;
    ``noted`` is files that parsed with something worth saying about them, and
    those *are* merged. The two lists are separate because conflating them is how
    a refusal ends up printed as a note.

    ``read_lines`` is False for the destination archive, which may be tens of
    gigabytes and is not the thing being validated: its spans come from its first
    and last lines, which is two reads a file, and its names are trusted.
    """
    coverage: list[Coverage] = []
    refused: list[tuple[str, str]] = []
    noted: list[tuple[str, str]] = []
    for path in sorted(directory.glob("*.jsonl")):
        if not path.is_file():
            continue
        _prefix, source_id, day = parse_archive_name(path.name)
        if read_lines:
            ok, _count, problem = check_parses(path)
            if not ok:
                refused.append((path.name, problem or "did not parse"))
                continue
            if problem is not None:
                noted.append((path.name, problem))
        start, end = read_span(path)
        coverage.append(
            Coverage(
                path=path,
                name=path.name,
                # A file with no source in its name is still a source: the machine
                # that wrote the original archive. Naming it "unnamed" rather than
                # None keeps it comparable in the overlap report instead of
                # dropping it out of it.
                source_id=source_id or "unnamed",
                day=day,
                start=start,
                end=end,
            )
        )
    return coverage, refused, noted


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #


def _fmt(moment: datetime | None) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ") if moment is not None else "?"


def run(args: argparse.Namespace) -> int:
    config = load_recorder_config(Path(args.config) if args.config else None)
    dest = Path(args.dest or _config_str(config, "archive_dir") or DEFAULT_ARCHIVE_DIR)
    source = Path(args.source)

    if not source.is_dir():
        raise MergeRefusedError(f"the foreign archive {source} does not exist")
    if not dest.is_dir():
        raise MergeRefusedError(
            f"the destination archive {dest} does not exist. It is not created for "
            f"you: merging into a directory that is not the archive you meant is how "
            f"a day of recordings ends up somewhere nobody looks."
        )
    if source.resolve() == dest.resolve():
        raise MergeRefusedError(f"the source and destination are the same directory ({dest})")

    print(f"merging {source.resolve()}")
    print(f"     -> {dest.resolve()}")

    incoming, refused, noted = survey(source, read_lines=True)
    existing, _, _ = survey(dest, read_lines=False)
    existing_names = {item.name for item in existing}

    for name, why in noted:
        print(f"  note  {name}: {why}")
    for name, why in refused:
        print(f"  REFUSE {name}: {why}")

    collisions = [item for item in incoming if item.name in existing_names]
    mergeable = [item for item in incoming if item.name not in existing_names]
    for item in collisions:
        print(
            f"  SKIP  {item.name}: already in the destination. Nothing is overwritten "
            f"- same source, same day, two different files means one is not what its "
            f"name says. Compare them by hand."
        )

    print(
        f"{len(incoming)} readable foreign files, {len(mergeable)} to merge, "
        f"{len(collisions)} name collisions, {len(refused)} refused"
    )

    # Overlap is computed over what the archive will look like AFTER the merge,
    # which is the only question worth answering. Collisions are left out: they
    # are not being merged.
    pairs = overlaps(existing + mergeable)
    if pairs:
        print(f"\n{len(pairs)} overlapping period(s) - two sources covering one span:")
        for left, right, start, end in pairs:
            hours = (end - start).total_seconds() / 3600.0
            print(
                f"  {left.source_id} and {right.source_id} both cover "
                f"{_fmt(start)} -> {_fmt(end)} ({hours:.1f}h)\n"
                f"      {left.name}\n"
                f"      {right.name}"
            )
        print(
            "  Both are kept. Overlapping coverage is two independent observations\n"
            "  of one market, and the difference between them measures what a single\n"
            "  recorder misses. Choose between them in the analysis, where the choice\n"
            "  is visible, not here where it would be silent."
        )
    else:
        print("\nno overlapping coverage: every period is covered by at most one source.")

    if not mergeable:
        print("\nnothing to merge.")
        return 1 if refused else 0

    if args.dry_run:
        print("")
        for item in mergeable:
            print(f"  would merge  {item.name}  {_fmt(item.start)} -> {_fmt(item.end)}")
        print(f"dry run: nothing was copied. {len(mergeable)} files would merge.")
        return 1 if refused else 0

    print("")
    merged = 0
    failed = 0
    for item in mergeable:
        target = dest / item.name
        try:
            file_hash, size = copy_verified(item.path, target)
        except (OSError, MergeRefusedError) as exc:
            print(f"  FAIL  {item.name}: {exc}")
            failed += 1
            continue
        merged += 1
        print(f"  MERGE {item.name}  {size / 1e6:.1f} MB  sha256 {file_hash[:16]}...")

    print(
        f"\nmerged {merged} of {len(mergeable)} files; {failed} failed, "
        f"{len(refused)} refused. The originals in {source} are untouched."
    )
    return 1 if (failed or refused) else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="archive_merge.py",
        description=(
            "Merge a foreign archive into the main one. Verifies every file parses, "
            "never overwrites an existing file, and reports any period two sources "
            "both cover rather than choosing between them."
        ),
    )
    parser.add_argument("--source", required=True, help="the foreign archive directory")
    parser.add_argument(
        "--dest",
        default=None,
        help=f"the main archive. Default: recorder.archive_dir, else {DEFAULT_ARCHIVE_DIR}",
    )
    parser.add_argument(
        "--config", default=None, help="config file carrying a `recorder:` mapping"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse, report collisions and overlaps, and copy nothing",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except MergeRefusedError as exc:
        print(f"\nREFUSING TO MERGE: {exc}\n", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted. Any file mid-copy left a .partial behind; the foreign "
              "originals are untouched.", file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
