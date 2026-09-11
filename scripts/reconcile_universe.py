#!/usr/bin/env python
"""Which pairs does the recorder record, and which does the daemon actually use?

Two lists, derived by two different rules, and **nothing in the system compares
them**:

- `scripts/record.py` ranks every online USD pair by 24-hour quote volume from a
  startup `ticker` snapshot, gives the top N full raw recording and summarises the
  rest above a volume floor. It writes both lists into its own archive as a
  `session` marker.
- Engine 2 `market_data_recorder` derives its subscription from the quote
  currencies the **account actually holds**, through `subscription_scope()` in
  `engines/market_data_recorder/contracts.py`, and re-derives it every tick as the
  balance moves.

Those rules can disagree, and the disagreement is invisible. The dangerous
direction is **a pair the daemon subscribed to that the recorder never recorded**:
the system can then take a position in a pair with no order-book or spread history
at all, which is exactly the input engine 9 `order_book` and the spread half of
engine 10 `cost` are calibrated on, and which cannot be backfilled afterwards. The
other direction — recorded but never used — costs disk and nothing else, and is
reported second because it is not a problem, only a fact.

This is a **script and not an engine**, and that is a rule rather than a
convenience. See `context/architecture-context.md`, "Two records, two writers": the
archive has one writer and the store has one writer, so anything that reads across
the boundary reads both and writes neither. An engine doing this work would need
read access to both and would have a `state` key to write its findings into, and
the first time it wrote a row the single-writer rule would be gone.

## What it reads

The archive side reads the recorder's own `session` markers.

The daemon side reads `logs/acsoe.jsonl` — and its rotated siblings — for the
per-tick line `run_loop` in `src/acsoe/cli/engine.py` writes:

    {"event": "tick_market_snapshot",
     "subscription": ["BTC/USD", "ETH/USD", ...], "subscription_count": 2,
     "subscription_derived": true, "quotes": [...],
     "run_id": "...", "cycle_id": 41, "ts": "2026-09-11T16:44:00.000000Z"}

It is written **every tick and unconditionally**, including when the subscription
is empty. That matters here: "the daemon ran and subscribed to nothing" and "the
daemon was not running" are different facts, and a line that appeared only when
there was something to say would collapse them into one.

`--daemon-pairs` still supplies the list by hand, for comparing against a machine
whose log you do not have.

Usage::

    python scripts/reconcile_universe.py
    python scripts/reconcile_universe.py --archive data/raw --log logs/acsoe.jsonl
    python scripts/reconcile_universe.py --daemon-pairs BTC/USD ETH/USD SOL/USD
    python scripts/reconcile_universe.py --json
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

DEFAULT_ARCHIVE_DIR: Final = Path("data") / "raw"
DEFAULT_SUMMARY_DIR: Final = Path("data") / "summaries"
DEFAULT_LOG: Final = Path("logs") / "acsoe.jsonl"

CONFIG_CANDIDATES: Final = (
    Path("config") / "recorder.yaml",
    Path("config") / "default.yaml",
)
CONFIG_SECTION: Final = "recorder"

#: The log event this script reads. Written by `run_loop` in
#: `src/acsoe/cli/engine.py`, which owns the constant; a test asserts the two
#: agree, so the seam is pinned rather than remembered.
SUBSCRIPTION_EVENT: Final = "tick_market_snapshot"

#: Field names accepted as "the daemon's pair list", in order of preference.
#: Deliberately liberal: engine 2 does not log yet, and a reporting script that
#: refused to read a reasonable variant would be a script that reports nothing on
#: the day somebody finally adds the line under a slightly different name.
SUBSCRIPTION_FIELDS: Final = ("subscription", "pairs", "scope", "symbols")

RECORDER_CHANNEL: Final = "_recorder"


class Snapshot:
    """One recorder session marker, flattened.

    Not a ``@dataclass`` — ``scripts/`` is loaded by path in the tests and the
    decorator raises at import there. See ``PairStat`` in ``scripts/record.py``.
    """

    __slots__ = ("event", "file", "source_id", "tier1", "tier2", "ts", "unranked")

    def __init__(
        self,
        *,
        file: str,
        ts: str | None,
        event: str,
        source_id: str | None,
        tier1: tuple[str, ...],
        tier2: tuple[str, ...],
        unranked: tuple[str, ...],
    ) -> None:
        self.file = file
        self.ts = ts
        self.event = event
        self.source_id = source_id
        self.tier1 = tier1
        self.tier2 = tier2
        self.unranked = unranked


# --------------------------------------------------------------------------- #
# The recorder's side: its own session markers
# --------------------------------------------------------------------------- #


def read_session_markers(directory: Path) -> list[Snapshot]:
    """Every `session` marker in every archive file in a directory.

    Session markers are written before any market data and on every reconnect, so
    they sit at the head of each file — but `tier1_degraded` can appear anywhere,
    and it is the one that matters most, because it is the moment the recorder
    stopped recording pairs it had been recording. So the whole file is scanned.
    Markers are a few hundred lines against a gigabyte, and the scan is by
    substring before any JSON parsing, so the cost is a read rather than a parse.
    """
    found: list[Snapshot] = []
    needle = b'"kind":"session"'
    loose = b'"session"'
    for path in sorted(directory.glob("*.jsonl")):
        if not path.is_file():
            continue
        try:
            with path.open("rb") as handle:
                for raw in handle:
                    if needle not in raw and loose not in raw:
                        continue
                    try:
                        line = json.loads(raw)
                    except ValueError:
                        continue
                    if not isinstance(line, dict) or line.get("kind") != "session":
                        continue
                    payload = line.get("payload")
                    if not isinstance(payload, dict):
                        continue
                    found.append(
                        Snapshot(
                            file=path.name,
                            ts=line.get("ts_recv"),
                            event=str(payload.get("event", "?")),
                            source_id=payload.get("source_id"),
                            tier1=_strings(payload.get("tier1") or payload.get("kept")),
                            tier2=_strings(payload.get("tier2")),
                            unranked=_strings(payload.get("unranked")),
                        )
                    )
        except OSError:
            continue
    return found


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def latest_recorded(snapshots: list[Snapshot]) -> tuple[set[str], set[str], Snapshot | None]:
    """``(tier1, tier2, the marker they came from)`` for the most recent session.

    The *most recent* marker, not the union of all of them, and the difference is
    the point: after a disk-guard degrade the recorder is recording three pairs,
    not the ten it started with, and a union would report the seven it dropped as
    still covered. A degrade is exactly when this comparison matters most.
    """
    usable = [item for item in snapshots if item.tier1 or item.tier2]
    if not usable:
        return set(), set(), None
    latest = max(usable, key=lambda item: item.ts or "")
    return set(latest.tier1), set(latest.tier2), latest


# --------------------------------------------------------------------------- #
# The daemon's side: its structured log
# --------------------------------------------------------------------------- #


def log_files(log_path: Path) -> list[Path]:
    """The named log and its rotated siblings, the live file last.

    `TimedRotatingFileHandler` renames yesterday's file to
    `acsoe.jsonl.2026-09-10` at midnight, so a script reading only the named path
    sees today and nothing else. That is fine for "what is the subscription now"
    and wrong for every question about a window — and the failure is silent: the
    answer is simply drawn from less data than the operator asked for.
    """
    if not log_path.parent.is_dir():
        return []
    siblings = sorted(
        path for path in log_path.parent.glob(log_path.name + "*") if path.is_file()
    )
    rotated = [path for path in siblings if path != log_path]
    return rotated + ([log_path] if log_path.is_file() else [])


def read_daemon_subscription(
    log_path: Path,
) -> tuple[set[str], dict[str, Any] | None, int]:
    """``(pairs, the line they came from, lines scanned)``.

    Takes the **last** matching line, because the scope is re-derived every tick
    as the balance moves and the current one is the only one worth comparing.
    """
    best: dict[str, Any] | None = None
    scanned = 0
    for path in log_files(log_path):
        try:
            with path.open("rb") as handle:
                for raw in handle:
                    scanned += 1
                    if b'"' not in raw:
                        continue
                    try:
                        line = json.loads(raw)
                    except ValueError:
                        continue
                    if isinstance(line, dict) and _subscription_of(line) is not None:
                        best = line
        except OSError:
            continue
    if best is None:
        return set(), None, scanned
    return set(_subscription_of(best) or ()), best, scanned


def _subscription_of(line: dict[str, Any]) -> tuple[str, ...] | None:
    """The pair list a log line carries, or None if it carries none.

    A line qualifies either by naming the canonical event, or by carrying a field
    whose name is one of :data:`SUBSCRIPTION_FIELDS` holding a list of strings
    that look like Kraken v2 symbols. The second rule is what lets this work
    against whatever engine 2 eventually emits without a coordinated change.
    """
    named = line.get("event") == SUBSCRIPTION_EVENT
    for field in SUBSCRIPTION_FIELDS:
        value = line.get(field)
        if not isinstance(value, list):
            continue
        items = tuple(item for item in value if isinstance(item, str) and item)
        if len(items) != len(value):
            continue
        if named:
            # An EMPTY list from the canonical event is an answer, not an absence:
            # it says the daemon ran this tick and subscribed to nothing. Requiring
            # a non-empty list here would render that as "no pair list found",
            # which is the message for a daemon that never logged at all.
            return items
        if items and all("/" in item for item in items):
            return items
    return None


# --------------------------------------------------------------------------- #
# The comparison
# --------------------------------------------------------------------------- #


def compare(
    *, recorded_raw: set[str], recorded_summary: set[str], daemon: set[str]
) -> dict[str, Any]:
    """What each side has that the other does not.

    Three buckets rather than two, because "recorded" is not one thing. A pair in
    tier 2 has a per-minute spread and depth distribution and **no raw history at
    all**; that is enough to calibrate a cost model and not enough to backtest
    engine 9. So a daemon pair covered only by tier 2 is reported separately from
    one covered by neither — it is a smaller problem, not the same one.
    """
    recorded = recorded_raw | recorded_summary
    return {
        "recorded_tier1": sorted(recorded_raw),
        "recorded_tier2": sorted(recorded_summary),
        "daemon": sorted(daemon),
        "daemon_only": sorted(daemon - recorded),
        "daemon_summary_only": sorted((daemon & recorded_summary) - recorded_raw),
        "recorded_only": sorted(recorded - daemon),
        "both_full": sorted(daemon & recorded_raw),
    }


def report(result: dict[str, Any], *, have_daemon_list: bool) -> tuple[list[str], bool]:
    """``(lines, clean)``."""
    lines: list[str] = []
    lines.append(
        f"recorder: {len(result['recorded_tier1'])} pairs at full raw, "
        f"{len(result['recorded_tier2'])} summarised"
    )
    if not have_daemon_list:
        lines.append(
            "daemon:   NO PAIR LIST FOUND.\n"
            f"  Nothing in the log carries a '{SUBSCRIPTION_EVENT}' line, so there is\n"
            f"  nothing here to compare against. This is NOT a clean result - it is the\n"
            f"  absence of one.\n"
            f"  The daemon writes that line every tick, from run_loop in\n"
            f"  src/acsoe/cli/engine.py. If the log has none, either the daemon has not\n"
            f"  run since that was added, or it is writing to a different log directory.\n"
            f"  Pass --daemon-pairs to compare against a list you supply instead."
        )
        return lines, False

    lines.append(f"daemon:   {len(result['daemon'])} pairs subscribed")

    clean = True
    if result["daemon_only"]:
        clean = False
        lines.append(
            f"\n  {len(result['daemon_only'])} PAIR(S) THE DAEMON USES AND THE RECORDER DOES NOT RECORD:"
        )
        lines.append("    " + ", ".join(result["daemon_only"]))
        lines.append(
            "    These have no order book and no spread history, in either tier. Engine 9\n"
            "    `order_book` and the spread half of engine 10 `cost` have nothing to read\n"
            "    for them, and the history cannot be backfilled - Kraken's free archives\n"
            "    carry OHLCV and no bid, ask, spread or depth. Every hour this stands is an\n"
            "    hour of input lost for a pair the system may trade."
        )
    if result["daemon_summary_only"]:
        clean = False
        lines.append(
            f"\n  {len(result['daemon_summary_only'])} pair(s) the daemon uses that are SUMMARISED ONLY:"
        )
        lines.append("    " + ", ".join(result["daemon_summary_only"]))
        lines.append(
            "    These have a per-minute spread and depth distribution and no raw frames.\n"
            "    Enough to calibrate a cost model; not enough to backtest engine 9. Raise\n"
            "    --tier1-count, or name them with --tier1-pairs, if they are to be traded."
        )
    if result["recorded_only"]:
        lines.append(
            f"\n  {len(result['recorded_only'])} pair(s) recorded that the daemon does not use "
            f"(disk, and nothing else):"
        )
        shown = result["recorded_only"][:12]
        lines.append(
            "    " + ", ".join(shown) + (" ..." if len(result["recorded_only"]) > 12 else "")
        )
    if clean:
        lines.append(
            "\n  every pair the daemon subscribes to is recorded at full raw. Nothing to do."
        )
    return lines, clean


# --------------------------------------------------------------------------- #
# Config and wiring
# --------------------------------------------------------------------------- #


def load_recorder_config(explicit: Path | None = None) -> dict[str, Any]:
    """The ``recorder:`` mapping, or ``{}``. Duplicated from `record.py`, which has
    to stay copyable to a bare server on its own — so `scripts/` is not a package
    and there is nothing to import from."""
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
    config = load_recorder_config(Path(args.config) if args.config else None)
    archive = Path(args.archive or _config_str(config, "archive_dir") or DEFAULT_ARCHIVE_DIR)
    summaries = Path(args.summaries or _config_str(config, "summary_dir") or DEFAULT_SUMMARY_DIR)
    log_path = Path(args.log)

    raw_markers = read_session_markers(archive) if archive.is_dir() else []
    summary_markers = read_session_markers(summaries) if summaries.is_dir() else []
    tier1, tier2_from_raw, latest = latest_recorded(raw_markers)
    _t1, tier2_from_summary, _latest2 = latest_recorded(summary_markers)
    tier2 = tier2_from_raw | tier2_from_summary

    if args.daemon_pairs:
        daemon = set(args.daemon_pairs)
        source_line: dict[str, Any] | None = {"event": "--daemon-pairs", "ts": "(supplied)"}
        scanned = 0
    else:
        daemon, source_line, scanned = read_daemon_subscription(log_path)

    result = compare(recorded_raw=tier1, recorded_summary=tier2, daemon=daemon)
    result["archive_dir"] = archive.as_posix()
    result["summary_dir"] = summaries.as_posix()
    result["log"] = log_path.as_posix()
    result["log_lines_scanned"] = scanned
    result["recorder_marker"] = (
        {"file": latest.file, "ts": latest.ts, "event": latest.event, "source_id": latest.source_id}
        if latest is not None
        else None
    )
    result["daemon_line_ts"] = source_line.get("ts") if source_line else None
    result["checked_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    lines, clean = report(result, have_daemon_list=source_line is not None)
    result["clean"] = clean

    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if clean else 1

    print(f"archive   {archive}  ({len(raw_markers)} session markers)")
    print(f"summaries {summaries}  ({len(summary_markers)} session markers)")
    print(f"log       {log_path}  ({scanned} lines scanned)")
    if latest is not None:
        print(f"recorder's latest session marker: {latest.event} at {latest.ts} in {latest.file}")
        if latest.event == "tier1_degraded":
            print(
                "  NOTE: the recorder is DEGRADED. Tier 1 is whatever survived the disk\n"
                "  guard, not what it started with, and the guard never reverses on its own."
            )
    else:
        print("recorder: no session marker found — has it ever run against this archive?")
    if source_line is not None and not args.daemon_pairs:
        print(f"daemon's latest subscription line: {source_line.get('event')} at {source_line.get('ts')}")
    print("")
    for line in lines:
        print(line)
    return 0 if clean else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="reconcile_universe.py",
        description=(
            "Compare the pairs the recorder records against the pairs the daemon "
            "subscribes to. Reads the archive's session markers and the daemon's "
            "structured log; writes nothing to either."
        ),
    )
    parser.add_argument("--archive", default=None, help="tier 1 archive directory")
    parser.add_argument("--summaries", default=None, help="tier 2 summary directory")
    parser.add_argument("--log", default=str(DEFAULT_LOG), help="the daemon's structured log")
    parser.add_argument(
        "--daemon-pairs",
        nargs="+",
        default=None,
        help=(
            "compare against this list instead of the log. Use it until engine 2 logs "
            "its subscription."
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
