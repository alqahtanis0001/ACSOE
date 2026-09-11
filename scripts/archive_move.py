#!/usr/bin/env python
"""Move finished archive files off the recording disk, verifying every byte first.

The recorder writes ~17 GB a day and the machine it runs on has days of runway,
not months. Something has to take completed days off that disk. The dangerous
version of that something is a one-line ``shutil.move`` in a scheduled task: it
will eventually run on a morning when the external drive is asleep, the network
share has not reconnected, or the mount point exists as an empty local directory
because the drive behind it is gone. It will then "succeed" — copying into the
local filesystem or into nothing at all — and delete the only copy of a day of
order-book data that cannot be re-recorded, because the market does not come back.

So this script is built around one rule: **the original is deleted only after the
copy has been read back off the destination and found identical.** Everything else
here serves that rule.

## What it refuses to do

- **Run against an unreachable destination.** The destination must already exist
  and must pass a write-read-delete probe. It is never created. Creating it is
  precisely the failure being guarded against: ``E:/archive`` on a disconnected
  drive is an absent path, and ``mkdir -p`` turns it into a real local directory
  that silently accepts 17 GB nobody will ever look for.
- **Move a file it cannot date.** Eligibility is a UTC calendar date, read out of
  the filename. A file whose name does not carry one is reported and left alone.
- **Move today's file, at any ``--older-than-days``.** It is open and being
  appended to.
- **Overwrite anything.** A name already present at the destination is reported
  and skipped, including when the two files are byte-identical — that case is a
  half-finished previous run, and deciding whether the source is redundant is the
  operator's call, not this script's.
- **Delete a source whose copy did not verify.** The partial copy is removed and
  the source is left exactly where it was.

## The bound on "verified", stated honestly

The check is: hash the source as it is read, write the copy to a ``.partial``
name, flush and ``fsync`` it, read it back from the destination and hash that,
compare, and only then rename into place and unlink the source. That catches a
truncated write, a full destination, a silently short copy, a failed rename and a
destination that is not where it appears to be.

It does **not** prove the bytes are durable on the far side forever — a read-back
can still be served from the operating system's cache, and no portable Python can
force it not to be. It is a check that the copy arrived, not a warranty against
later bit rot. Two copies on two disks is the answer to that, and this script
leaves you able to make one: run it with ``--keep`` and it copies without deleting.

Usage::

    python scripts/archive_move.py --dest E:/acsoe/archive --dry-run
    python scripts/archive_move.py --dest E:/acsoe/archive
    python scripts/archive_move.py --dest //nas/acsoe/raw --older-than-days 2
    python scripts/archive_move.py --dest E:/acsoe/archive --keep     # copy only
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Final

DEFAULT_ARCHIVE_DIR: Final = Path("data") / "raw"
DEFAULT_OLDER_THAN_DAYS: Final = 7

CONFIG_CANDIDATES: Final = (
    Path("config") / "recorder.yaml",
    Path("config") / "default.yaml",
)
CONFIG_SECTION: Final = "recorder"

NAME_SEPARATOR: Final = "__"
PARTIAL_SUFFIX: Final = ".partial"
PROBE_NAME: Final = ".archive_move_probe"
LOCK_FILENAME: Final = ".recorder.lock"

#: 8 MiB. Large enough that a 2 GB file is not 250,000 syscalls, small enough
#: that the process footprint does not depend on the size of a day's recording.
CHUNK: Final = 8 * 1024 * 1024

#: Headroom the destination must have beyond the bytes being moved. A destination
#: filled exactly to the last byte is a destination the next run cannot use, and
#: the filesystem's own metadata needs room the file sizes do not account for.
FREE_SPACE_MARGIN: Final = 1024 * 1024 * 1024


class MoveRefusedError(RuntimeError):
    """The move cannot safely start. Nothing has been copied or deleted."""


class ArchiveFile:
    """One archive file and what its name says about it.

    Not a ``@dataclass``. ``scripts/`` is not a package and these modules are
    loaded by path in the tests, which leaves them absent from ``sys.modules``
    where ``dataclasses`` looks its own module up; the decorator then raises
    ``AttributeError: 'NoneType' object has no attribute '__dict__'`` at import and
    the failure surfaces in a fixture rather than in a test. The same note is on
    ``PairStat`` in ``scripts/record.py``.
    """

    __slots__ = ("day", "path", "prefix", "size", "source_id")

    def __init__(
        self,
        *,
        path: Path,
        prefix: str | None,
        source_id: str | None,
        day: date | None,
        size: int,
    ) -> None:
        self.path = path
        self.prefix = prefix
        self.source_id = source_id
        self.day = day
        self.size = size


# --------------------------------------------------------------------------- #
# Names
# --------------------------------------------------------------------------- #


def parse_archive_name(name: str) -> tuple[str | None, str | None, date | None]:
    """``(prefix, source_id, day)`` from a filename, each None when unreadable.

    Two shapes are understood. The current one carries the source::

        kraken_v2__msi__2026-09-11.jsonl  ->  ("kraken_v2", "msi", 2026-09-11)

    and the original one, which the existing archive is still full of, does not::

        kraken_v2_2026-09-11.jsonl        ->  ("kraken_v2", None, 2026-09-11)

    The older shape is read rather than rejected because the 7.1 GB already on
    disk is written that way and is the only raw sample there is. A file this
    cannot date comes back ``(.., .., None)`` and is never eligible to move.
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


def scan(directory: Path) -> list[ArchiveFile]:
    """Every ``*.jsonl`` in a directory, with what its name says, sorted by name."""
    found: list[ArchiveFile] = []
    for path in sorted(directory.glob("*.jsonl")):
        if not path.is_file():
            continue
        prefix, source_id, day = parse_archive_name(path.name)
        found.append(
            ArchiveFile(
                path=path,
                prefix=prefix,
                source_id=source_id,
                day=day,
                size=path.stat().st_size,
            )
        )
    return found


def eligible(
    files: list[ArchiveFile], *, today: date, older_than_days: int
) -> tuple[list[ArchiveFile], list[tuple[ArchiveFile, str]]]:
    """``(movable, [(skipped, why), ...])``.

    ``older_than_days`` is a distance in whole UTC days: at 7, a file dated the
    8th of the month becomes eligible on the 15th. At 0 everything but today is
    eligible; today's file is never eligible at any value, because the recorder
    has it open and is appending to it.
    """
    if older_than_days < 0:
        raise ValueError("--older-than-days cannot be negative")
    cutoff = today - timedelta(days=older_than_days)
    movable: list[ArchiveFile] = []
    skipped: list[tuple[ArchiveFile, str]] = []
    for item in files:
        if item.day is None:
            skipped.append((item, "its name carries no UTC date, so its age is unknown"))
        elif item.day >= today:
            skipped.append((item, "it is today's file and is still being written"))
        elif item.day > cutoff:
            skipped.append((item, f"dated {item.day}, newer than the {cutoff} cutoff"))
        else:
            movable.append(item)
    return movable, skipped


# --------------------------------------------------------------------------- #
# Is the destination actually there?
# --------------------------------------------------------------------------- #


def check_destination(dest: Path, *, need_bytes: int) -> None:
    """Refuse unless the destination is real, writable and has room.

    Deliberately does not create it. A mover that creates its own destination
    cannot tell an unplugged drive from a first run, and the two need opposite
    responses.
    """
    if not dest.exists():
        raise MoveRefusedError(
            f"the destination {dest} does not exist.\n"
            f"  It is NOT created for you, on purpose: on a disconnected drive or an\n"
            f"  unmounted share this path is absent in exactly the same way, and\n"
            f"  creating it would write a day of recordings into a local directory\n"
            f"  wearing the missing drive's name. Mount it, then run this again."
        )
    if not dest.is_dir():
        raise MoveRefusedError(f"the destination {dest} is not a directory")

    probe = dest / PROBE_NAME
    try:
        with probe.open("wb") as handle:
            handle.write(b"acsoe archive_move reachability probe\n")
            handle.flush()
            os.fsync(handle.fileno())
        read_back = probe.read_bytes()
        probe.unlink()
    except OSError as exc:
        raise MoveRefusedError(
            f"the destination {dest} exists but could not be written to: {exc}.\n"
            f"  A read-only mount, a share that has dropped its credentials, or a\n"
            f"  full disk all look like this. Nothing has been copied or deleted."
        ) from exc
    if read_back != b"acsoe archive_move reachability probe\n":
        raise MoveRefusedError(
            f"the destination {dest} did not read back what was just written to it.\n"
            f"  Whatever is behind that path is not storing bytes reliably. Refusing."
        )

    free = shutil.disk_usage(dest).free
    if free < need_bytes + FREE_SPACE_MARGIN:
        raise MoveRefusedError(
            f"the destination {dest} has {free / 1e9:.1f} GB free and the move needs "
            f"{(need_bytes + FREE_SPACE_MARGIN) / 1e9:.1f} GB "
            f"({need_bytes / 1e9:.1f} GB of files plus "
            f"{FREE_SPACE_MARGIN / 1e9:.1f} GB headroom).\n"
            f"  Refusing before the first copy rather than half way through the run."
        )


# --------------------------------------------------------------------------- #
# Copy, verify, and only then delete
# --------------------------------------------------------------------------- #


def digest(path: Path) -> tuple[str, int]:
    """``(sha256, size)`` of a file, read in chunks."""
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            block = handle.read(CHUNK)
            if not block:
                break
            hasher.update(block)
            size += len(block)
    return hasher.hexdigest(), size


def copy_verified(source: Path, target: Path) -> tuple[str, int]:
    """Copy to ``target``, prove the copy is identical, return ``(sha256, size)``.

    Writes to ``target.partial`` and renames only after the read-back matches, so
    an interrupted run never leaves a short file under a real archive name. Raises
    ``OSError`` or ``MoveRefusedError``; the caller has not deleted anything yet and
    must not.
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

        # Read it back off the destination rather than trusting the write. This
        # is the assertion the whole script exists for, so it is a separate open
        # of a separate path and not a reuse of anything above.
        copy_hash, copy_size = digest(partial)
        if copy_hash != source_hash or copy_size != written:
            raise MoveRefusedError(
                f"{source.name} did not arrive intact: wrote {written} bytes with "
                f"sha256 {source_hash[:16]}..., read back {copy_size} bytes with "
                f"sha256 {copy_hash[:16]}.... The source has NOT been touched."
            )
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return source_hash, written


def move_one(item: ArchiveFile, dest: Path, *, keep: bool) -> tuple[bool, str]:
    """``(moved, message)`` for one file. Never raises for an ordinary refusal."""
    target = dest / item.path.name
    if target.exists():
        return False, (
            f"SKIP  {item.path.name}: a file of that name is already at the "
            f"destination. Nothing is ever overwritten; compare them and remove "
            f"one by hand."
        )
    try:
        file_hash, size = copy_verified(item.path, target)
    except (OSError, MoveRefusedError) as exc:
        return False, f"FAIL  {item.path.name}: {exc}"

    if keep:
        return True, f"COPY  {item.path.name}  {size / 1e6:.1f} MB  sha256 {file_hash[:16]}..."

    try:
        item.path.unlink()
    except OSError as exc:
        return True, (
            f"COPY  {item.path.name}: verified at the destination but the original "
            f"could not be deleted ({exc}). Both copies exist; delete the original "
            f"by hand. No data is at risk."
        )
    return True, f"MOVE  {item.path.name}  {size / 1e6:.1f} MB  sha256 {file_hash[:16]}..."


# --------------------------------------------------------------------------- #
# Config — the same three-key reader as the recorder, deliberately duplicated
# --------------------------------------------------------------------------- #


def load_recorder_config(explicit: Path | None = None) -> dict[str, Any]:
    """The ``recorder:`` mapping, or ``{}``.

    A copy of the reader in ``scripts/record.py`` rather than an import of it.
    ``scripts/`` is not a package and must not become one: ``record.py`` has to
    stay a single file that can be copied to a bare server on its own, and a
    shared helper module would quietly end that.
    """
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


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #


def run(args: argparse.Namespace) -> int:
    config = load_recorder_config(Path(args.config) if args.config else None)
    source_dir = Path(args.source or _config_str(config, "archive_dir") or DEFAULT_ARCHIVE_DIR)
    dest_text = args.dest or _config_str(config, "move_dest")
    if not dest_text:
        raise MoveRefusedError(
            "no destination. Pass --dest, or set recorder.move_dest in "
            "config/recorder.yaml. There is deliberately no default: a mover with a "
            "default destination is a mover that will one day run against a path "
            "nobody chose."
        )
    dest = Path(dest_text)
    older = args.older_than_days
    if older is None:
        configured = config.get("move_after_days")
        older = configured if isinstance(configured, int) else DEFAULT_OLDER_THAN_DAYS

    if not source_dir.is_dir():
        raise MoveRefusedError(f"the source archive {source_dir} does not exist")
    if dest.exists() and source_dir.resolve() == dest.resolve():
        raise MoveRefusedError(
            f"the source and destination are the same directory ({dest}). That move "
            f"would verify a file against itself and then delete it."
        )

    today = datetime.now(UTC).date()
    files = scan(source_dir)
    movable, skipped = eligible(files, today=today, older_than_days=older)
    total = sum(item.size for item in movable)

    print(f"source      {source_dir.resolve()}")
    print(f"destination {dest}")
    print(f"today is    {today} UTC; moving files dated {today - timedelta(days=older)} or older")
    print(
        f"{len(files)} archive files, {len(movable)} eligible "
        f"({total / 1e9:.2f} GB), {len(skipped)} skipped"
    )
    for item, why in skipped:
        print(f"  keep  {item.path.name}: {why}")
    if (source_dir / LOCK_FILENAME).exists():
        print(
            f"  note  {LOCK_FILENAME} is present, so a recorder may be running here. "
            f"That is fine: today's file is never eligible."
        )
    if not movable:
        print("nothing to move.")
        return 0

    # The destination is checked even on a dry run. "Would this work?" is the
    # question a dry run is asked, and the destination being absent is the most
    # likely reason the answer is no.
    check_destination(dest, need_bytes=total)
    print(f"destination is reachable, writable, and has room for {total / 1e9:.2f} GB")

    if args.dry_run:
        for item in movable:
            print(f"  would move  {item.path.name}  {item.size / 1e6:.1f} MB")
        print(f"dry run: nothing was copied or deleted. {len(movable)} files would move.")
        return 0

    moved = 0
    failed = 0
    for item in movable:
        done, message = move_one(item, dest, keep=args.keep)
        print(f"  {message}")
        if done:
            moved += 1
        else:
            failed += 1

    verb = "copied" if args.keep else "moved"
    print(f"{verb} {moved} of {len(movable)} files; {failed} not {verb}.")
    if failed:
        print(
            "every file that was not moved is still in the source directory, "
            "unmodified. Nothing was deleted without a verified copy."
        )
    return 1 if failed else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="archive_move.py",
        description=(
            "Move archive files older than N UTC days to another location, verifying "
            "each one arrived intact before deleting the original, and refusing to "
            "run at all if the destination is not reachable."
        ),
    )
    parser.add_argument(
        "--source",
        default=None,
        help=f"the archive to move out of. Default: recorder.archive_dir, else {DEFAULT_ARCHIVE_DIR}",
    )
    parser.add_argument(
        "--dest",
        default=None,
        help="where files go. Default: recorder.move_dest. Never created for you.",
    )
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=None,
        help=(
            f"a file is eligible once its UTC date is this many whole days behind "
            f"today's. Default: recorder.move_after_days, else {DEFAULT_OLDER_THAN_DAYS}. "
            f"Today's file is never eligible at any value."
        ),
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help=(
            "copy and verify, but do not delete the originals. This is how you end up "
            "with two copies on two disks, which is the only real answer to bit rot."
        ),
    )
    parser.add_argument(
        "--config", default=None, help="config file carrying a `recorder:` mapping"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would move, including whether the destination is reachable",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except MoveRefusedError as exc:
        print(f"\nREFUSING TO MOVE: {exc}\n", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted. Any file mid-copy left a .partial behind and its "
              "original is untouched.", file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
