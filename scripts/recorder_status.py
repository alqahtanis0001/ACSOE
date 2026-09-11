#!/usr/bin/env python
"""Is the recorder still running, and when did it last write?

**The recorder has died unnoticed twice.** Once to an `Errno 28` and once to a
stop nobody noticed for about fifteen hours — 01:12Z to 15:44Z on 2026-09-11. In
both cases the data for those hours is simply gone: order book and spread cannot
be backfilled, Kraken's free archives carry OHLCV and no bid, ask, spread or
depth, and the market does not come back. The cost of not noticing is measured in
hours of an irreplaceable input, so noticing has to be one command.

Run it by hand, or on a schedule with `--max-age-s`, which makes it exit non-zero
when the recorder has gone quiet — that is the form a cron job or a Task Scheduler
action can alert on.

## What "last wrote" means, and why two answers are given

The **archive** answers "when did market data last land on disk". It is the
number that matters, because it is the thing that cannot be recovered.

The **heartbeat** answers "when was the recorder last alive", from the
`heartbeat__<source>__<date>.ndjson` file the recorder writes beside its archive.
It exists because the archive alone cannot tell a dead recorder from a quiet
market: both produce no lines. The heartbeat also carries what the recorder was
subscribed to *at that moment*, which a session marker written at startup cannot
— a disk-guard degrade changes the pair list mid-run.

Reading both is what separates the three states that matter and look identical
from outside:

| archive | heartbeat | what it is |
|---|---|---|
| recent | recent | recording normally |
| stale | recent | **alive but receiving nothing** — a dead subscription or a disconnect |
| stale | stale | the process is gone |

The second row is the one a process check (`is record.py in the task list?`)
cannot see at all, and it is the failure that produces a silent hole in a running
system.

Usage::

    python scripts/recorder_status.py
    python scripts/recorder_status.py --max-age-s 300      # exit 1 if quiet
    python scripts/recorder_status.py --dir data/summaries
    python scripts/recorder_status.py --json
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

DEFAULT_DIRS: Final = (Path("data") / "raw", Path("data") / "summaries")

CONFIG_CANDIDATES: Final = (
    Path("config") / "recorder.yaml",
    Path("config") / "default.yaml",
)
CONFIG_SECTION: Final = "recorder"

HEARTBEAT_GLOB: Final = "heartbeat__*.ndjson"
LOCK_FILENAME: Final = ".recorder.lock"

#: How much of the end of a file to read when looking for its last line. One raw
#: line is a book frame; 256 KiB is several hundred of them, and it means this
#: script costs the same on a 2 GB file as on an empty one.
TAIL_BYTES: Final = 256 * 1024

DEFAULT_MAX_AGE_S: Final = 0.0

#: How far ahead of this machine's clock a timestamp may be before it is called a
#: clock problem. A live recorder appends while this script reads, so the newest
#: line is routinely milliseconds into the "future"; five seconds is far beyond
#: that and far below anything a real clock skew would produce.
CLOCK_TOLERANCE_S: Final = 5.0


def parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def last_line(path: Path) -> bytes | None:
    """The last non-blank line of a file, read from its tail.

    Tolerates a truncated final line by falling back to the one before it: the
    recorder flushes every line, so a forced kill costs at most a partial last
    one, and refusing to answer because of it would defeat the purpose — a
    truncated tail is *evidence of the kill this script exists to report*.
    """
    try:
        size = path.stat().st_size
        if size == 0:
            return None
        with path.open("rb") as handle:
            handle.seek(max(0, size - TAIL_BYTES))
            tail = handle.read()
    except OSError:
        return None
    for candidate in reversed(tail.split(b"\n")):
        if candidate.strip():
            return candidate
    return None


def last_record(path: Path) -> dict[str, Any] | None:
    """The last parsable line of a file, as an object."""
    raw = last_line(path)
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        # A truncated final line. Not an error and not silence: step back one.
        try:
            with path.open("rb") as handle:
                size = path.stat().st_size
                handle.seek(max(0, size - TAIL_BYTES))
                lines = [line for line in handle.read().split(b"\n") if line.strip()]
        except OSError:
            return None
        for candidate in reversed(lines[:-1]):
            try:
                parsed = json.loads(candidate)
            except ValueError:
                continue
            return parsed if isinstance(parsed, dict) else None
        return None
    return parsed if isinstance(parsed, dict) else None


def record_time(record: dict[str, Any] | None) -> datetime | None:
    """When a line happened. Raw lines carry `ts_recv`, summary rows carry
    `minute`, heartbeats carry `ts`."""
    if record is None:
        return None
    for key in ("ts_recv", "ts", "minute"):
        value = record.get(key)
        if isinstance(value, str) and value:
            moment = parse_iso(value)
            if moment is not None:
                return moment
    return None


def newest(paths: list[Path]) -> Path | None:
    """The newest file by modification time, not by name.

    By mtime rather than by filename date on purpose: a merged archive can hold a
    file whose name is later than anything the local recorder wrote, and "the
    newest name" would then report a foreign recorder's coverage as this one's
    liveness.
    """
    return max(paths, key=lambda path: path.stat().st_mtime, default=None)


def inspect(directory: Path, *, now: datetime) -> dict[str, Any]:
    """Everything this script knows about one output directory."""
    report: dict[str, Any] = {
        "directory": directory.as_posix(),
        "exists": directory.is_dir(),
        "lock_present": (directory / LOCK_FILENAME).exists(),
        "archive": None,
        "heartbeat": None,
    }
    if not directory.is_dir():
        return report

    archive = newest([path for path in directory.glob("*.jsonl") if path.is_file()])
    if archive is not None:
        moment = record_time(last_record(archive))
        report["archive"] = {
            "file": archive.name,
            "size_bytes": archive.stat().st_size,
            "last_line_at": moment.isoformat().replace("+00:00", "Z") if moment else None,
            "age_s": (now - moment).total_seconds() if moment else None,
        }

    beat_file = newest([path for path in directory.glob(HEARTBEAT_GLOB) if path.is_file()])
    if beat_file is not None:
        beat = last_record(beat_file) or {}
        moment = record_time(beat)
        report["heartbeat"] = {
            "file": beat_file.name,
            "source_id": beat.get("source_id"),
            "tier": beat.get("tier"),
            "pair_count": beat.get("pair_count"),
            "pairs": beat.get("pairs"),
            "connected": beat.get("connected"),
            "stopping": bool(beat.get("stopping")),
            "lines_written": beat.get("lines_written"),
            "last_beat_at": moment.isoformat().replace("+00:00", "Z") if moment else None,
            "age_s": (now - moment).total_seconds() if moment else None,
        }
    return report


def verdict(report: dict[str, Any], *, max_age_s: float) -> tuple[str, bool]:
    """``(one line for a human, healthy)``.

    ``max_age_s`` of 0 means "report, do not judge": there is no defensible
    default staleness for an archive whose write rate depends entirely on which
    pairs are subscribed and how busy the market is, and inventing one would
    produce an alert that is either useless or wrong.
    """
    directory = report["directory"]
    if not report["exists"]:
        return f"{directory}: does not exist", False

    archive = report["archive"]
    beat = report["heartbeat"]
    archive_age = archive["age_s"] if archive else None
    beat_age = beat["age_s"] if beat else None

    if archive is None and beat is None:
        return f"{directory}: nothing here — no archive file and no heartbeat", False

    parts = []
    if archive is not None:
        parts.append(
            f"archive {archive['file']} last wrote "
            f"{_ago(archive_age)} ({archive['size_bytes'] / 1e6:.1f} MB)"
        )
    else:
        parts.append("no archive file")
    if beat is not None:
        state = "stopped cleanly" if beat["stopping"] else (
            "connected" if beat["connected"] else "DISCONNECTED"
        )
        parts.append(
            f"heartbeat {_ago(beat_age)}, {state}, "
            f"{beat['pair_count']} pairs, source {beat['source_id']}"
        )
    else:
        parts.append("no heartbeat file")

    line = f"{directory}: " + "; ".join(parts)

    if max_age_s <= 0:
        return line, True

    stale_archive = archive_age is None or archive_age > max_age_s
    stale_beat = beat_age is None or beat_age > max_age_s

    if stale_beat and stale_archive:
        note = f"DEAD: nothing written for longer than {max_age_s:.0f}s."
        return f"{line}\n  {note}", False
    if stale_archive and not stale_beat:
        # The state a process check cannot see: the process is there, and the data
        # is not.
        note = (
            f"ALIVE BUT RECEIVING NOTHING: the recorder is beating but no market data "
            f"has landed for {_ago(archive_age)}. A subscription has died or the socket "
            f"is down. This is a hole in the archive being created right now, and it "
            f"will not be recoverable."
        )
        return f"{line}\n  {note}", False
    if stale_beat and not stale_archive:
        note = (
            "the archive is current but the heartbeat is not. Either this recorder "
            "predates heartbeats, or another writer is filling the archive."
        )
        return f"{line}\n  {note}", True
    return line, True


def _ago(seconds: float | None) -> str:
    if seconds is None:
        return "never"
    if seconds < -CLOCK_TOLERANCE_S:
        return f"{-seconds:.0f}s IN THE FUTURE — check the clock on the recording machine"
    if seconds < 0:
        # A live recorder writes while this script reads. `now` is taken once, at
        # the start, so the last line of a busy archive is routinely a few
        # milliseconds *after* it. That is the recorder working, not a clock
        # problem, and reporting it as one would train the operator to ignore the
        # message that means a real clock problem.
        return "just now"
    if seconds < 90:
        return f"{seconds:.0f}s ago"
    if seconds < 5400:
        return f"{seconds / 60:.1f} min ago"
    return f"{seconds / 3600:.1f} h ago"


def load_recorder_config(explicit: Path | None = None) -> dict[str, Any]:
    """The ``recorder:`` mapping, or ``{}``. Duplicated from `record.py`, which
    must stay copyable to a bare server on its own, so `scripts/` is not a
    package and there is nothing to import from."""
    if explicit is not None and not explicit.is_file():
        raise FileNotFoundError(f"--config {explicit} does not exist")
    try:
        import yaml  # optional
    except ImportError:
        if explicit is not None:
            raise
        return {}
    here = Path(__file__).resolve().parent.parent
    searched = (
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


def run(args: argparse.Namespace) -> int:
    if args.dir:
        directories = [Path(item) for item in args.dir]
    else:
        config = load_recorder_config(Path(args.config) if args.config else None)
        directories = [
            Path(_config_str(config, "archive_dir") or DEFAULT_DIRS[0]),
            Path(_config_str(config, "summary_dir") or DEFAULT_DIRS[1]),
        ]

    now = datetime.now(UTC)
    reports = [inspect(directory, now=now) for directory in directories]

    if args.json:
        print(json.dumps({"checked_at": now.isoformat().replace("+00:00", "Z"), "directories": reports}, indent=2))

    healthy = True
    for report in reports:
        line, ok = verdict(report, max_age_s=args.max_age_s)
        healthy = healthy and ok
        if not args.json:
            print(line)
    if args.max_age_s <= 0 and not args.json:
        print(
            "\n(no --max-age-s given, so nothing is judged stale. Pass one to make "
            "this exit non-zero when the recorder has gone quiet.)"
        )
    return 0 if healthy else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="recorder_status.py",
        description=(
            "Report how long ago the recorder last wrote, from its newest archive file "
            "and its heartbeat. Exits non-zero with --max-age-s when it has gone quiet."
        ),
    )
    parser.add_argument(
        "--dir",
        action="append",
        default=None,
        help="an output directory to check. Repeatable. Default: both from the config.",
    )
    parser.add_argument(
        "--max-age-s",
        type=float,
        default=DEFAULT_MAX_AGE_S,
        help=(
            "treat anything older than this as stale and exit non-zero. 0, the default, "
            "reports without judging: there is no defensible default staleness for an "
            "archive whose write rate depends on which pairs are subscribed."
        ),
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--config", default=None, help="config file carrying a `recorder:` mapping"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
