#!/usr/bin/env python
"""Standalone Kraken WebSocket v2 recorder. Two tiers, no hardcoded pair list.

This script imports **nothing** from ``src/acsoe/``. That is deliberate and it is
not laziness: order-book and spread history cannot be recovered retroactively, so
recording has to start on day one, before the engine framework exists. Engines 1
and 2 supersede it in Phase 2 and this script keeps running regardless.

It records **public** market data only and therefore holds no credentials. There
is no API key anywhere in this file and none is needed: Kraken's ``instrument``,
``book``, ``ticker`` and ``trade`` channels on ``wss://ws.kraken.com/v2`` are
unauthenticated.

## Two tiers, because one tier cannot be both complete and affordable

**Tier 1 — full raw.** Every ``book``, ``ticker`` and ``trade`` update for a small
configurable list of pairs, written verbatim to ``data/raw/`` exactly as this
script has always written it. This is the microstructure dataset. It is not
summarised and it is not deleted.

**Tier 2 — summaries.** Every *other* pair in the quote currency whose 24-hour
volume clears a configurable floor, reduced to **one row per pair per minute** in
``data/summaries/``: median spread with its 25th and 75th percentiles, median
depth at a configurable notional on both sides, trade count, volume, and the
number of raw updates the row was built from. A couple of hundred bytes a row, so
the whole tradable universe costs tens of megabytes a day rather than terabytes.

**Why per minute and not per decision bar.** A minute divides 1, 5 and 15 evenly,
so one recording rolls up into any candle size the research later asks for.
Bucketing at the decision bar would mean re-recording the market to change the
bar, and the market does not come back.

### Rolling up: re-aggregate, never average the medians

A roll-up to 5 or 15 minutes MUST re-aggregate from the stored percentiles
weighted by the stored counts — treat each minute as a small empirical
distribution pinned at ``spread_bps`` with weight ``samples``, and take the
weighted quantile across the minutes being combined. **Averaging the per-minute
medians is wrong.** The median of a union is not the mean of the medians; the
error moves with how unevenly updates are spread across the minutes, so a quiet
minute carrying four quotes would weigh the same as a busy one carrying four
thousand. The result is a spread estimate that is subtly too low in exactly the
volatile windows the cost model cares about, and **nothing downstream would fail
to say so** — the number simply comes out optimistic and every gate that reads it
inherits the optimism. The stored ``samples`` and ``updates`` counts exist for no
other reason.

The weighted-quantile roll-up is itself an approximation — three quantiles is not
the minute's full sample — and that is the price of a 200-byte row. The bound is
honest and stated: it interpolates between stored order statistics. The
mean-of-medians is not an approximation, it is a different and wrong quantity.

## Both pair lists are derived, never written down

There is no default pair list in this file. At startup the recorder subscribes to
Kraken's own ``instrument`` channel for the pairs that exist and are online, then
takes a ``ticker`` **snapshot** of every one of them in the target quote currency
and ranks by 24-hour quote volume (``volume`` x ``vwap``). Tier 1 is the top N of
that ranking; tier 2 is everything below it that clears the volume floor.

Deriving from the ``instrument`` channel rather than from REST ``AssetPairs`` also
removes a naming hazard: the WebSocket v2 API calls Bitcoin ``BTC/USD`` and
Dogecoin ``DOGE/USD`` where REST calls them ``XBT/USD`` and ``XDG/USD``. Asking
the socket we are about to subscribe on which symbols it has means there is no
translation table to get wrong and no pair silently missing because a rename was
not in it.

Both derived lists are written into both archives as a ``session`` marker before
any market data, so a replay always knows what was subscribed and what was not.

## The disk guard

A recorder that dies of ``Errno 28`` loses everything from that moment on. One
that degrades loses only the least valuable part. This has already happened once.
So free space is checked every ``--disk-check-s``, and below ``--disk-floor-gb``
tier 1 drops to its top three pairs — loudly, in the log and as a ``session``
marker in the archive — while tier 2, two orders of magnitude cheaper and covering
the whole universe, keeps running untouched.

The degrade is **sticky for the life of the process**: it never un-degrades on its
own. A guard that re-expanded as soon as space was freed would oscillate around
the floor and cut the archive into interleaved fragments of two different
subscription sets, which is worse to replay than one clean recorded step down.

## One writer per archive, enforced by the operating system

Two recorders appending to one archive directory is silent corruption: the lines
interleave, `ts_recv` stops being monotonic within a file, and the duplicate
`session` markers make a replay believe the subscription set changed when it did
not. Nothing downstream would report it, because every individual line is valid.

So the recorder takes an **exclusive OS-level lock** on a ``.recorder.lock`` file
in each output directory and refuses to start if it cannot get it. The lock is an
`fcntl.flock` on POSIX and an `msvcrt.locking` byte-range lock on Windows —
**never a PID file**. A PID file survives its process: a machine that loses power
mid-recording comes back with a stale PID file and an archive that no recorder
will write to until somebody notices and deletes it by hand, which is the outage
this lock exists to prevent rather than to cause. A kernel lock is released when
the file handle is closed, and every path out of a process closes its handles,
including a `SIGKILL` and a power cut.

## Where the files go, and what they are called

The output directories come from ``config/recorder.yaml`` (``recorder.archive_dir``
and ``recorder.summary_dir``), overridable with ``--out`` and ``--summary-out``,
defaulting to ``data/raw`` and ``data/summaries``. A missing config file, a
missing key, or an absent PyYAML all fall through to those defaults — the script
has to keep running when it is the only file on the machine.

Each file is **one UTC calendar day of one source**::

    kraken_v2__<source_id>__2026-09-11.jsonl
    summary__<source_id>__2026-09-11.jsonl

``source_id`` comes from ``recorder.source_id`` or ``--source-id`` and defaults to
the hostname. It is in the name because a file named only by its date collides
with the same date recorded on another machine, and the two ways out of a
collision — overwrite, or concatenate — either lose a day or produce a file whose
lines are out of order across the seam with nothing saying where the seam is.
With the source in the name, two machines' archives merge by copying files into
one directory, and ``scripts/archive_merge.py`` can say which periods two sources
both cover instead of picking one.

The day boundary is enforced two ways. Every line is routed to the file for the
date the line itself carries, and a background task additionally rolls the open
files over when the UTC date changes, so a **stream that goes quiet across
midnight still closes yesterday's file** rather than holding it open until the
next frame. Rotation happens mid-run: the recorder is meant to run for months
without a restart, and a restart is the only other way to get a new file.

A run that starts at midday **appends to that date's existing file** rather than
opening a second one. The writer opens in binary append mode and never truncates,
so one file covers exactly one day no matter how many times the process was
restarted inside it — which is what makes merging, moving and gap-accounting
arithmetic over whole files rather than over ranges inside them.

## Line schemas

``data/raw/`` — one JSON object per line, exactly these seven keys, unchanged::

    v            int    always 1
    kind         str    "tick" | "gap" | "session"
    pair         str|None  Kraken v2 symbol, null when the frame names no single one
    channel      str    Kraken's channel name, or "_recorder" for a marker
    ts_exchange  str|None  ISO-8601 UTC ending "Z", copied verbatim from the payload
    ts_recv      str    ISO-8601 UTC ending "Z", recorder wall clock at frame read
    payload      dict   the Kraken frame verbatim, or the marker's own object

``data/summaries/`` — ``gap`` and ``session`` markers use those same seven keys,
and a summary row uses these fourteen::

    v                int    always 1
    kind             str    always "summary"
    pair             str    Kraken v2 symbol
    minute           str    ISO-8601 UTC ending "Z", the minute's START, inclusive
    spread_bps       list   [p25, p50, p75] of (ask-bid)/mid in basis points
    depth_bid_bps    float|None  median distance from mid, in bps, at which resting
                                 bid notional reaches --depth-notional-usd
    depth_ask_bps    float|None  the same on the ask side
    mid              float|None  median mid price, so bps convert back into money
    updates          int    raw book updates consumed for this pair this minute
    samples          int    of those, how many yielded a usable spread
    depth_samples    int    of those, how many books were deep enough to fill the notional
    trades           int    trades seen this minute
    volume           float  base-currency volume traded this minute
    quote_volume     float  quote-currency volume traded this minute

``updates`` minus ``samples`` is not noise to be ignored: it is one-sided and
crossed books, and a pair where those two diverge is a pair whose spread series is
thinner than its update count suggests.

Recordings are immutable (invariant 11). Nothing here edits, backfills,
interpolates or reorders a line. A break in the stream is written down as a
``gap`` marker rather than silently healed. A summary row is a reduction computed
once, at the time, from frames that were never stored; it is not a later cleaning
pass over something already written, which is what invariant 11 forbids.

**Floats in the summary rows, deliberately.** These are distribution statistics for
research. No order size, order price or fee is ever computed from them; anything on
the order path reads ``Decimal`` from ``AssetPairs`` through engine 1. Carrying
``Decimal`` through several thousand book updates a second would cost more than the
precision is worth to a median.

Usage::

    python scripts/record.py                          # derive both tiers, record
    python scripts/record.py --dry-run --measure-s 90 # derive, measure, report, exit
    python scripts/record.py --tier1-pairs BTC/USD ETH/USD
    python scripts/record.py --tier2-floor-usd 10000 --disk-floor-gb 40
    python scripts/record.py --out E:/acsoe/raw --source-id vps-fra-1
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import math
import os
import random
import shutil
import signal
import socket
import sys
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Self

import orjson
import websockets
from websockets.asyncio.client import connect

# The single-instance lock is an OS lock, and the two operating systems spell it
# differently. Imported at module scope rather than inside the lock so that a
# platform with neither fails loudly at import, where it is obvious, instead of
# silently recording without a lock.
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

SCHEMA_VERSION: Final = 1
KRAKEN_WS_V2_URL: Final = "wss://ws.kraken.com/v2"

#: ``channel`` value for lines the recorder wrote about itself rather than about
#: the market. Reserved: no Kraken channel may ever be called this.
RECORDER_CHANNEL: Final = "_recorder"

#: ``channel`` value for a Kraken method response (a subscribe/unsubscribe ack).
#: Those frames carry ``method`` instead of ``channel``.
ACK_CHANNEL: Final = "_ack"

LINE_KEYS: Final = frozenset(
    {"v", "kind", "pair", "channel", "ts_exchange", "ts_recv", "payload"}
)
LINE_KINDS: Final = frozenset({"tick", "gap", "session"})

SUMMARY_KEYS: Final = frozenset(
    {
        "v",
        "kind",
        "pair",
        "minute",
        "spread_bps",
        "depth_bid_bps",
        "depth_ask_bps",
        "mid",
        "updates",
        "samples",
        "depth_samples",
        "trades",
        "volume",
        "quote_volume",
    }
)

#: Tier 1 keeps everything. Tier 2 needs `book` for spread and depth and `trade`
#: for count and volume; `ticker` would add a 24-hour aggregate the summary does
#: not use, so it is not subscribed and the bandwidth is not spent.
TIER1_CHANNELS: Final = ("book", "ticker", "trade")
TIER2_CHANNELS: Final = ("book", "trade")

DEFAULT_DEPTH: Final = 10
DEFAULT_QUOTE: Final = "USD"
DEFAULT_TIER1_COUNT: Final = 10

#: What tier 1 falls back to when the disk guard fires. Three, because three pairs
#: of full book is what this machine has demonstrably sustained.
DEGRADED_TIER1_COUNT: Final = 3

DEFAULT_TIER2_FLOOR_USD: Final = 100_000.0
DEFAULT_DEPTH_NOTIONAL_USD: Final = 10_000.0
DEFAULT_SUMMARY_INTERVAL_S: Final = 60
DEFAULT_DISK_FLOOR_GB: Final = 25.0
DEFAULT_DISK_CHECK_S: Final = 30.0

DEFAULT_OUT_DIR: Final = Path("data") / "raw"
DEFAULT_SUMMARY_DIR: Final = Path("data") / "summaries"

#: Where the `recorder:` mapping is looked for, in order, relative to both the
#: working directory and the repository this file sits in. `recorder.yaml` is
#: first because `default.yaml` is `extra="forbid"` in the package's own loader —
#: a `recorder:` key there needs a matching pydantic section or nothing starts.
#: Both are read so that moving the keys into the main config later costs nothing
#: here.
CONFIG_CANDIDATES: Final = (
    Path("config") / "recorder.yaml",
    Path("config") / "default.yaml",
)

#: The config section this script reads. Everything outside it is ignored, so the
#: same reader works against either file.
CONFIG_SECTION: Final = "recorder"

#: Characters allowed in a ``source_id``. Deliberately excludes ``_``: the
#: filename separator is ``__``, and an underscore inside the source id would make
#: ``kraken_v2__a__b__2026-09-11.jsonl`` ambiguous to split. Excludes the path
#: separators for the obvious reason — a source id reaches a filename directly.
SOURCE_ID_ALLOWED: Final = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-"
)
SOURCE_ID_MAX: Final = 48

#: The filename separator. Two characters, not one, because ``kraken_v2`` already
#: contains a single underscore and the name has to split unambiguously into
#: prefix, source and date.
NAME_SEPARATOR: Final = "__"

#: The single-instance lock file, one per output directory. Dot-prefixed and not
#: ``.jsonl``, so every ``*.jsonl`` glob in the project steps over it.
LOCK_FILENAME: Final = ".recorder.lock"

#: How often the midnight roller checks whether the UTC date has moved on. The
#: line-level rotation already handles a busy stream; this bounds how long a
#: *quiet* one can hold yesterday's file open after midnight.
MIDNIGHT_CHECK_S: Final = 10.0

#: How often each tier writes a heartbeat. One a minute per tier is ~0.6 MB a day
#: against 17 GB of recording.
DEFAULT_HEARTBEAT_S: Final = 60.0

#: The heartbeat file's prefix, and its extension.
#:
#: **Not ``.jsonl``, and that is the whole design.** Every consumer in this
#: project finds recordings with ``glob("*.jsonl")``, and a heartbeat is not a
#: recording — it is a statement about the *recorder*. Two things would go wrong
#: if it carried that extension.
#:
#: `scripts/recording_report.py` measures continuity by the distance between
#: consecutive lines: a stretch longer than the silence threshold with no line is
#: reported as time the recorder was not running. A heartbeat every minute makes
#: that distance never exceed a minute, so a recorder that is alive but whose
#: *subscription* has silently died — connected, pinging, receiving nothing —
#: would report as fully recorded. That is precisely a defect that looks like
#: success, and `recording_span_continuous` is the only thing that currently
#: catches it.
#:
#: The second is smaller and still real: `build_archive.py` and `ohlc_fixture.py`
#: would both read heartbeats as frames and have to learn to skip them.
#:
#: So the heartbeat sits beside the archive, in the same directory, under a name
#: nothing else globs. `scripts/recorder_status.py` reads it.
HEARTBEAT_PREFIX: Final = "heartbeat"
HEARTBEAT_SUFFIX: Final = ".ndjson"

#: Symbols per subscribe message. Kraken accepts a list; several hundred symbols in
#: one frame is a large message for no benefit, and a rejected oversized subscribe
#: would take a whole tier down rather than one chunk of it.
SUBSCRIBE_CHUNK: Final = 50

#: How long the startup snapshot may take before the recorder stops waiting for
#: stragglers and records which symbols never answered.
DISCOVERY_TIMEOUT_S: Final = 60.0

BACKOFF_INITIAL_S: Final = 1.0
BACKOFF_MAX_S: Final = 60.0
BACKOFF_FACTOR: Final = 2.0

BYTES_PER_GB: Final = 1_000_000_000


class SchemaError(ValueError):
    """A line failed validation on write. Never suppressed: a malformed line in an
    append-only recording is unfixable later, so the recorder refuses to write it."""


class ArchiveLockedError(RuntimeError):
    """Another recorder already holds this archive directory.

    Not a warning and not a retry: two writers on one archive is the corruption
    this lock exists to prevent, and a second recorder that waited would just be
    a second recorder starting late.
    """


# --------------------------------------------------------------------------- #
# Configuration — read without importing anything from the package
# --------------------------------------------------------------------------- #


def _config_search_paths(explicit: Path | None) -> list[Path]:
    """Where to look for the ``recorder:`` mapping.

    The working directory first, then the repository this file sits in, so that
    ``python scripts/record.py`` from anywhere finds the committed config while a
    copy of this file dropped into a server's home directory beside its own
    ``config/recorder.yaml`` finds that one.
    """
    if explicit is not None:
        return [explicit]
    here = Path(__file__).resolve().parent.parent
    paths: list[Path] = []
    for base in (Path.cwd(), here):
        for candidate in CONFIG_CANDIDATES:
            resolved = base / candidate
            if resolved not in paths:
                paths.append(resolved)
    return paths


def load_recorder_config(explicit: Path | None = None) -> dict[str, Any]:
    """The ``recorder:`` mapping, or ``{}``.

    Returns an empty mapping rather than raising when there is no config, no
    ``recorder:`` key, or no PyYAML installed. That is the standalone property
    doing its job: every key here has a safe default, none of them is a trading
    threshold, and a recorder that refused to start because a file about *where to
    put files* was missing would be an outage in the one process whose data cannot
    be backfilled.

    An explicitly named ``--config`` that does not exist **is** an error, because
    the operator naming a file is a statement that it should be there.
    """
    if explicit is not None and not explicit.is_file():
        # Checked before PyYAML, and separately from "the file had no recorder
        # section": a named file that is absent and a named file that is present
        # but silent are different mistakes and must not share a message.
        raise FileNotFoundError(f"--config {explicit} does not exist")
    try:
        import yaml  # optional; absent on a bare server
    except ImportError:
        if explicit is not None:
            raise
        print(
            "PyYAML is not installed, so config/recorder.yaml was not read; "
            "using built-in defaults for the output directories and source id.",
            file=sys.stderr,
            flush=True,
        )
        return {}

    for path in _config_search_paths(explicit):
        if not path.is_file():
            continue
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            continue
        section = loaded.get(CONFIG_SECTION)
        if isinstance(section, dict):
            return section
    return {}


def _config_str(config: dict[str, Any], key: str) -> str | None:
    """A non-empty string from the config, or None.

    Empty string and None both mean "not set". They are not distinguished because
    the alternative — an empty ``archive_dir`` meaning the current directory —
    would turn a blank line in a config file into an archive written to the
    repository root.
    """
    value = config.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def default_source_id() -> str:
    """This machine's hostname, sanitised into something that can be a filename."""
    return sanitise_source_id(socket.gethostname() or "unknown")


def sanitise_source_id(raw: str) -> str:
    """A source id that is safe in a filename and unambiguous to split back out.

    Anything outside :data:`SOURCE_ID_ALLOWED` becomes a hyphen, which folds the
    separators, the spaces and the underscores a hostname might carry. Lowercased,
    because a source id that is ``VPS-1`` on one file and ``vps-1`` on another is
    two sources on a case-insensitive filesystem and one on a case-sensitive one,
    and the archive has to mean the same thing wherever it is read.
    """
    folded = "".join(char if char in SOURCE_ID_ALLOWED else "-" for char in raw.strip())
    # Collapse runs and trim, so "my_host!!" and "my-host" are not two sources.
    while "--" in folded:
        folded = folded.replace("--", "-")
    folded = folded.strip("-.").lower()[:SOURCE_ID_MAX]
    if not folded:
        raise ValueError(
            f"source id {raw!r} contains nothing usable in a filename. Set "
            f"recorder.source_id in config/recorder.yaml or pass --source-id."
        )
    return folded


# --------------------------------------------------------------------------- #
# The single-instance lock
# --------------------------------------------------------------------------- #


def _lock_exclusive(handle: Any) -> None:
    """Take a non-blocking exclusive OS lock on the first byte. Raises OSError."""
    if sys.platform == "win32":
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: Any) -> None:
    if sys.platform == "win32":
        handle.seek(0)
        with contextlib.suppress(OSError):
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        with contextlib.suppress(OSError):
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class ArchiveLock:
    """One writer per archive directory, enforced by the kernel.

    Not a ``@dataclass`` — see :class:`PairStat` for why that decorator cannot be
    used in this file.

    **Not a PID file, and the difference is the whole point.** A PID file is a
    claim a process writes down and is responsible for removing, so it outlives
    every death that does not run cleanup: a power cut, an ``Errno 28``, a
    ``SIGKILL`` — and this recorder has already been killed by two of those three.
    The archive would then be locked against every future recorder until a human
    noticed, which converts a recoverable crash into an indefinite outage in the
    one dataset that cannot be backfilled. It is also unsound in the other
    direction: PIDs are reused, so a stale file can name a live and entirely
    unrelated process.

    A kernel lock has neither failure. It is attached to an open file handle, and
    the kernel closes every handle a dying process holds, however it dies. The
    contents of the file are written for a human reading it and are never consulted
    to decide whether the lock is held.
    """

    __slots__ = ("_directory", "_handle", "_path")

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._path = directory / LOCK_FILENAME
        self._handle: Any = None

    @property
    def path(self) -> Path:
        return self._path

    def acquire(self) -> Self:
        self._directory.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+b")
        try:
            _lock_exclusive(handle)
        except OSError as exc:
            handle.close()
            raise ArchiveLockedError(
                f"another recorder is already writing to {self._directory}.\n"
                f"  The lock is {self._path} and it is held by a live process.\n"
                f"  {self._holder_note()}\n"
                f"  Two recorders appending to one archive interleave their lines and\n"
                f"  duplicate their session markers, and nothing downstream reports it.\n"
                f"  Stop the other recorder, or start this one with a different --out."
            ) from exc
        self._handle = handle
        self._stamp()
        return self

    def _stamp(self) -> None:
        """Write who holds it. Diagnostic only — nothing reads this to decide."""
        handle = self._handle
        if handle is None:  # pragma: no cover - acquire sets it before calling
            return
        note = orjson.dumps(
            {
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "acquired_at": utc_now_iso(),
                "note": "diagnostic only; the lock is the OS lock on this file, not this text",
            }
        )
        with contextlib.suppress(OSError):
            handle.seek(0)
            handle.truncate()
            handle.write(note + b"\n")
            handle.flush()

    def _holder_note(self) -> str:
        """What the lock file says about its holder, if it can be read at all.

        On Windows the locked byte range cannot be read by another process, so
        this frequently cannot answer and says so rather than guessing.
        """
        try:
            text = self._path.read_bytes().decode("utf-8", "replace").strip()
        except OSError:
            return "The lock file could not be read, which is itself normal on Windows."
        return f"It reports: {text}" if text else "It carries no holder note."

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        _unlock(handle)
        handle.close()

    def __enter__(self) -> Self:
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


def utc_now_iso() -> str:
    """Current UTC time as ``YYYY-MM-DDTHH:MM:SS.ffffffZ``.

    Not injected, because this script is not an engine. Invariant 9 constrains
    engines, which receive ``context.now``; this is the process that produces
    timestamps in the first place.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def utc_date_from_iso(ts: str) -> str:
    """The UTC calendar date of an ISO timestamp, for daily file rotation."""
    return ts[:10]


def current_utc_date() -> str:
    """Today's UTC calendar date. What the midnight roller compares against."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


def archive_filename(prefix: str, source_id: str, date: str) -> str:
    """``<prefix>__<source_id>__<date>.jsonl``.

    One function so that the writer, the mover and the merger cannot disagree
    about the name; the other two scripts carry their own copy of the parser
    rather than importing this one, because this file must stay copyable alone.
    """
    return f"{prefix}{NAME_SEPARATOR}{source_id}{NAME_SEPARATOR}{date}.jsonl"


def _first_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def extract_pair(payload: dict[str, Any]) -> str | None:
    """The single symbol a frame concerns, or None.

    Kraken v2 delivers ``data`` as a list, and a frame may carry several symbols.
    Reading a symbol out of the payload is not a mutation of it — the payload is
    still written verbatim — but a frame covering two pairs has no single pair,
    so it gets null rather than a guess.
    """
    data = payload.get("data")
    if isinstance(data, list) and data:
        symbols: set[str] = set()
        for item in data:
            symbol = _first_str(item.get("symbol")) if isinstance(item, dict) else None
            if symbol is not None:
                symbols.add(symbol)
        if len(symbols) == 1:
            return symbols.pop()
        return None
    if isinstance(data, dict):
        return _first_str(data.get("symbol"))
    result = payload.get("result")
    if isinstance(result, dict):
        return _first_str(result.get("symbol"))
    return None


def extract_channel(payload: dict[str, Any]) -> str:
    """Kraken's own channel name, or a reserved marker for a method response."""
    channel = _first_str(payload.get("channel"))
    if channel is not None:
        return channel
    if _first_str(payload.get("method")) is not None:
        return ACK_CHANNEL
    return "_unknown"


def extract_ts_exchange(payload: dict[str, Any]) -> str | None:
    """The exchange's own timestamp, copied verbatim, or None when there is none.

    Book snapshots and heartbeats carry no timestamp. That absence is recorded as
    null rather than filled in with the receive time, which would silently turn a
    measurement of network latency into zero.
    """
    data = payload.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return _first_str(data[0].get("timestamp"))
    if isinstance(data, dict):
        return _first_str(data.get("timestamp"))
    return None


def build_line(
    *,
    kind: str,
    pair: str | None,
    channel: str,
    ts_exchange: str | None,
    ts_recv: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "v": SCHEMA_VERSION,
        "kind": kind,
        "pair": pair,
        "channel": channel,
        "ts_exchange": ts_exchange,
        "ts_recv": ts_recv,
        "payload": payload,
    }


def validate_line(line: dict[str, Any]) -> None:
    """Validate on write. Raises :class:`SchemaError` on anything malformed.

    Spec 10 step 4. A recording is append-only, so a line that is wrong when
    written is wrong forever — validation has to happen before the bytes hit the
    file, not in a later cleaning pass that invariant 11 forbids anyway.
    """
    keys = set(line)
    if keys != LINE_KEYS:
        missing = sorted(LINE_KEYS - keys)
        extra = sorted(keys - LINE_KEYS)
        raise SchemaError(f"line keys wrong: missing={missing} extra={extra}")
    if line["v"] != SCHEMA_VERSION:
        raise SchemaError(f"unknown schema version {line['v']!r}")
    if line["kind"] not in LINE_KINDS:
        raise SchemaError(f"unknown kind {line['kind']!r}")
    if line["pair"] is not None and not isinstance(line["pair"], str):
        raise SchemaError(f"pair must be a string or null, got {type(line['pair']).__name__}")
    if not isinstance(line["channel"], str) or not line["channel"]:
        raise SchemaError("channel must be a non-empty string")
    if line["kind"] in ("gap", "session") and line["channel"] != RECORDER_CHANNEL:
        raise SchemaError(f"a {line['kind']} marker must use channel {RECORDER_CHANNEL!r}")
    for field in ("ts_exchange", "ts_recv"):
        value = line[field]
        if field == "ts_recv" and value is None:
            raise SchemaError("ts_recv may not be null")
        if value is None:
            continue
        if not isinstance(value, str) or not value.endswith("Z"):
            raise SchemaError(f"{field} must be an ISO-8601 UTC string ending 'Z', got {value!r}")
    if not isinstance(line["payload"], dict):
        raise SchemaError(f"payload must be an object, got {type(line['payload']).__name__}")


def validate_summary_line(line: dict[str, Any]) -> None:
    """The summary archive's own validator.

    ``gap`` and ``session`` markers are the same seven-key lines the raw archive
    uses — a replay must be able to read this archive's subscription set and its
    outages the same way it reads the other one's — so they go straight to
    :func:`validate_line`. Only ``kind == "summary"`` is new.
    """
    if line.get("kind") != "summary":
        validate_line(line)
        return
    keys = set(line)
    if keys != SUMMARY_KEYS:
        missing = sorted(SUMMARY_KEYS - keys)
        extra = sorted(keys - SUMMARY_KEYS)
        raise SchemaError(f"summary keys wrong: missing={missing} extra={extra}")
    if line["v"] != SCHEMA_VERSION:
        raise SchemaError(f"unknown schema version {line['v']!r}")
    if not isinstance(line["pair"], str) or not line["pair"]:
        raise SchemaError("a summary row must name one pair")
    minute = line["minute"]
    if not isinstance(minute, str) or not minute.endswith("Z"):
        raise SchemaError(f"minute must be an ISO-8601 UTC string ending 'Z', got {minute!r}")
    spread = line["spread_bps"]
    if not isinstance(spread, list) or len(spread) != 3:
        raise SchemaError("spread_bps must be [p25, p50, p75]")
    if any(not isinstance(value, (int, float)) for value in spread):
        raise SchemaError("spread_bps percentiles must be numbers")
    if not spread[0] <= spread[1] <= spread[2]:
        raise SchemaError(f"spread_bps percentiles are not ordered: {spread!r}")
    for key in ("updates", "samples", "depth_samples", "trades"):
        value = line[key]
        if not isinstance(value, int) or value < 0:
            raise SchemaError(f"{key} must be a count, got {value!r}")
    if line["samples"] > line["updates"]:
        raise SchemaError("samples cannot exceed the updates they were drawn from")
    if line["depth_samples"] > line["samples"]:
        raise SchemaError("depth_samples cannot exceed samples")


def raw_date(line: dict[str, Any]) -> str:
    """Which day's raw file a line belongs in."""
    return utc_date_from_iso(str(line["ts_recv"]))


def summary_date(line: dict[str, Any]) -> str:
    """Which day's summary file a line belongs in.

    A summary row is stamped with the minute it covers; a marker is stamped with
    the wall clock. Rotation reads whichever the line carries, so a row for the
    last minute of a day never lands in the next day's file because it was written
    a fraction of a second late.
    """
    minute = line.get("minute")
    if isinstance(minute, str):
        return utc_date_from_iso(minute)
    return utc_date_from_iso(str(line["ts_recv"]))


class JsonlWriter:
    """Append-only JSONL writer. One file per UTC day per source.

    Opens in binary append mode and never truncates, seeks or rewrites. If the
    process is killed mid-line the partial line stays; it is not repaired, because
    repairing a recording is exactly what invariant 11 forbids. **Append is what
    makes a mid-day start land in that day's existing file** rather than in a
    second file for the same date: the day, not the run, is the unit.

    Rotation happens on two triggers and both are needed. Every write routes to
    the file for the date the *line* carries, which keeps a summary row for
    23:59 out of the next day's file when it is flushed a second late. And
    :meth:`roll_to` closes the open file when the wall-clock UTC date moves on,
    which is what closes yesterday's file when the stream has gone quiet and no
    line is arriving to trigger the first rule.

    The validator and the date function are injected because there are now two
    archives with two schemas, and a writer that knew only one of them would let
    the other be written unvalidated.
    """

    def __init__(
        self,
        out_dir: Path,
        *,
        prefix: str = "kraken_v2",
        source_id: str | None = None,
        validator: Callable[[dict[str, Any]], None] = validate_line,
        date_of: Callable[[dict[str, Any]], str] = raw_date,
    ) -> None:
        self._out_dir = out_dir
        self._prefix = prefix
        self._source_id = sanitise_source_id(source_id) if source_id else default_source_id()
        self._validator = validator
        self._date_of = date_of
        self._date: str | None = None
        self._handle: Any = None
        self.lines_written = 0
        self.bytes_written = 0
        self.rotations = 0

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

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def open_date(self) -> str | None:
        """The UTC date of the file currently open, or None when none is."""
        return self._date if self._handle is not None else None

    def path_for(self, date: str) -> Path:
        return self._out_dir / archive_filename(self._prefix, self._source_id, date)

    def roll_to(self, date: str) -> bool:
        """Close the open file and open ``date``'s. True when it actually rolled.

        Called by the midnight roller with today's UTC date. A writer with nothing
        open is left alone — opening a file here would create an empty one for a
        tier that has not written a line, and an empty file in the archive is a
        claim about coverage that nothing made.
        """
        if self._handle is None or date == self._date:
            return False
        self._rotate(date)
        return True

    def write(self, line: dict[str, Any]) -> None:
        self._validator(line)
        date = self._date_of(line)
        if date != self._date:
            self._rotate(date)
        assert self._handle is not None
        encoded = orjson.dumps(line)
        self._handle.write(encoded)
        self._handle.write(b"\n")
        self._handle.flush()
        self.lines_written += 1
        self.bytes_written += len(encoded) + 1

    def _rotate(self, date: str) -> None:
        if self._handle is not None:
            self._handle.close()
            self.rotations += 1
        self._out_dir.mkdir(parents=True, exist_ok=True)
        # "ab", never "wb": a run starting mid-day appends to that day's file.
        self._handle = self.path_for(date).open("ab")
        self._date = date

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


# --------------------------------------------------------------------------- #
# Pair discovery — the thing that used to be a three-element tuple
# --------------------------------------------------------------------------- #


class PairStat:
    """One pair as Kraken described it in the startup snapshot.

    Not a ``@dataclass``, and that is not a style choice. This script is loaded by
    path in `tests/platform/test_record_format.py` — it is not a package and must
    not become one — and a module executed that way is absent from ``sys.modules``,
    where `dataclasses` looks its own module up. The decorator raises
    ``AttributeError: 'NoneType' object has no attribute '__dict__'`` on import, and
    the failure lands in the fixture rather than in a test, which is the shape of
    error that is hardest to read.
    """

    __slots__ = ("quote_volume_24h", "symbol", "trades_24h")

    def __init__(self, *, symbol: str, quote_volume_24h: float, trades_24h: int) -> None:
        self.symbol = symbol
        self.quote_volume_24h = quote_volume_24h
        self.trades_24h = trades_24h


def subscriptions(
    channels: Sequence[str], pairs: Sequence[str], depth: int
) -> list[dict[str, Any]]:
    """The subscribe payloads, chunked, in a stable order — so a session marker is
    comparable between runs and a replay can reconstruct exactly what was asked
    for."""
    subs: list[dict[str, Any]] = []
    for channel in channels:
        for start in range(0, len(pairs), SUBSCRIBE_CHUNK):
            chunk = list(pairs[start : start + SUBSCRIBE_CHUNK])
            params: dict[str, Any] = {"channel": channel, "symbol": chunk}
            if channel == "book":
                params["depth"] = depth
            subs.append({"method": "subscribe", "params": params})
    return subs


def quote_volume_24h(entry: dict[str, Any]) -> float | None:
    """24-hour volume in the quote currency, from a ticker snapshot entry.

    ``volume`` is in the base currency and ``vwap`` is the 24-hour volume-weighted
    average price, so their product is the only figure that means the same thing
    across pairs. Ranking on ``volume`` alone would put a cheap coin that trades in
    millions of units above Bitcoin.
    """
    volume = entry.get("volume")
    vwap = entry.get("vwap")
    if not isinstance(volume, (int, float)) or not isinstance(vwap, (int, float)):
        return None
    if volume < 0 or vwap <= 0:
        return None
    return float(volume) * float(vwap)


async def discover_pairs(
    url: str,
    *,
    quote: str = DEFAULT_QUOTE,
    timeout_s: float = DISCOVERY_TIMEOUT_S,
) -> tuple[tuple[PairStat, ...], tuple[str, ...]]:
    """Ask Kraken which pairs exist and how much each of them trades.

    Returns the ranked statistics and the symbols that were online but produced no
    ticker snapshot before the deadline. That second list is returned rather than
    dropped: a pair missing from both tiers because its snapshot was late is a hole
    in the universe, and a hole nobody is told about is the failure this whole
    change exists to end.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    online: list[str] = []
    stats: dict[str, PairStat] = {}

    async with connect(url, max_size=None) as ws:
        await ws.send(
            orjson.dumps({"method": "subscribe", "params": {"channel": "instrument"}}).decode()
        )
        while loop.time() < deadline and not online:
            frame = await asyncio.wait_for(
                ws.recv(), timeout=max(1.0, deadline - loop.time())
            )
            payload = orjson.loads(frame)
            if not isinstance(payload, dict):
                continue
            if payload.get("channel") != "instrument" or payload.get("type") != "snapshot":
                continue
            data = payload.get("data")
            pairs = data.get("pairs") if isinstance(data, dict) else None
            if not isinstance(pairs, list):
                raise RuntimeError("the instrument snapshot carried no pair list")
            for item in pairs:
                if not isinstance(item, dict):
                    continue
                symbol = _first_str(item.get("symbol"))
                if symbol is None or item.get("quote") != quote:
                    continue
                if item.get("status") != "online":
                    continue
                online.append(symbol)

        if not online:
            raise RuntimeError(f"no online {quote}-quoted pair in the instrument snapshot")

        await ws.send(
            orjson.dumps({"method": "unsubscribe", "params": {"channel": "instrument"}}).decode()
        )
        for sub in subscriptions(("ticker",), sorted(online), DEFAULT_DEPTH):
            await ws.send(orjson.dumps(sub).decode())

        while len(stats) < len(online):
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                frame = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except TimeoutError:
                break
            payload = orjson.loads(frame)
            if not isinstance(payload, dict) or payload.get("channel") != "ticker":
                continue
            entries = payload.get("data")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                symbol = _first_str(entry.get("symbol"))
                if symbol is None or symbol in stats:
                    continue
                volume = quote_volume_24h(entry)
                if volume is None:
                    continue
                trades = entry.get("trades")
                stats[symbol] = PairStat(
                    symbol=symbol,
                    quote_volume_24h=volume,
                    trades_24h=trades if isinstance(trades, int) else 0,
                )

    ranked = tuple(sorted(stats.values(), key=lambda stat: -stat.quote_volume_24h))
    unranked = tuple(sorted(symbol for symbol in online if symbol not in stats))
    return ranked, unranked


async def discover_with_retry(
    url: str, *, quote: str, timeout_s: float = DISCOVERY_TIMEOUT_S
) -> tuple[tuple[PairStat, ...], tuple[str, ...]]:
    """Keep asking until the exchange answers. Never fall back to a written list.

    There is deliberately no "if the snapshot fails, record these three pairs"
    branch here. A hardcoded fallback is how a recorder ends up quietly recording
    three pairs for months, which is the defect this file was rewritten to remove.
    Failing to reach Kraken is a reason to wait and retry, not a reason to invent a
    universe.
    """
    backoff = BACKOFF_INITIAL_S
    attempt = 0
    while True:
        attempt += 1
        try:
            return await discover_pairs(url, quote=quote, timeout_s=timeout_s)
        except (
            OSError,
            TimeoutError,
            RuntimeError,
            websockets.exceptions.WebSocketException,
        ) as exc:
            delay = min(backoff, BACKOFF_MAX_S) * (0.5 + random.random())
            print(
                f"pair discovery failed ({type(exc).__name__}: {exc}); retrying in "
                f"{delay:.1f}s (attempt {attempt}). Nothing is recorded until it succeeds.",
                file=sys.stderr,
                flush=True,
            )
            await asyncio.sleep(delay)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX_S)


def derive_tiers(
    ranked: Sequence[PairStat],
    *,
    tier1_count: int,
    tier2_floor_usd: float,
    tier1_override: Sequence[str] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split the ranked universe into the full-raw tier and the summary tier.

    An explicit ``tier1_override`` is honoured verbatim, including a symbol the
    snapshot did not rank — the operator naming a pair is a stronger signal than
    the ranking — and tier 2 is then everything else above the floor.
    """
    if tier1_count < 0:
        raise ValueError("tier1_count cannot be negative")
    if tier1_override is not None:
        tier1 = tuple(dict.fromkeys(tier1_override))
    else:
        tier1 = tuple(stat.symbol for stat in ranked[:tier1_count])
    chosen = set(tier1)
    tier2 = tuple(
        stat.symbol
        for stat in ranked
        if stat.symbol not in chosen and stat.quote_volume_24h >= tier2_floor_usd
    )
    return tier1, tier2


# --------------------------------------------------------------------------- #
# Tier 2 — the summariser
# --------------------------------------------------------------------------- #


def significant(value: float, digits: int = 8) -> float:
    """Round to significant figures rather than to decimal places.

    One summary file carries prices from 100,000 down to 0.000001. Rounding to a
    fixed number of decimal places either wastes bytes on the large ones or
    destroys the small ones outright.
    """
    if value == 0.0 or not math.isfinite(value):
        return value
    return round(value, -math.floor(math.log10(abs(value))) + (digits - 1))


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile of an already-sorted sequence."""
    if not sorted_values:
        raise ValueError("a quantile of nothing is not zero, it is undefined")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = q * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[int(position)]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


class BookState:
    """One pair's visible book, maintained from Kraken v2 ``book`` frames.

    Kraken sends a snapshot and then deltas, with ``qty == 0`` meaning the level is
    gone. Nothing here reaches disk: the book exists only long enough to produce a
    spread and a depth sample, which is the whole bargain of tier 2.
    """

    __slots__ = ("asks", "bids", "depth")

    def __init__(self, depth: int) -> None:
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.depth = depth

    def reset(self) -> None:
        self.bids.clear()
        self.asks.clear()

    def apply(self, entry: dict[str, Any]) -> None:
        self._side(self.bids, entry.get("bids"))
        self._side(self.asks, entry.get("asks"))
        self._truncate()

    @staticmethod
    def _side(book: dict[float, float], levels: object) -> None:
        if not isinstance(levels, list):
            return
        for level in levels:
            if not isinstance(level, dict):
                continue
            price = level.get("price")
            qty = level.get("qty")
            if not isinstance(price, (int, float)) or not isinstance(qty, (int, float)):
                continue
            if qty <= 0:
                book.pop(float(price), None)
            else:
                book[float(price)] = float(qty)

    def _truncate(self) -> None:
        """Keep the subscribed depth and no more.

        Kraken removes levels as they fall out of the window, but one missed
        removal would otherwise leave a stale price sitting at the top of the book
        for the life of the process, poisoning every spread sample after it.
        """
        if len(self.bids) > self.depth:
            for price in sorted(self.bids, reverse=True)[self.depth :]:
                del self.bids[price]
        if len(self.asks) > self.depth:
            for price in sorted(self.asks)[self.depth :]:
                del self.asks[price]

    def sample(self, notional: float) -> tuple[float, float, float | None, float | None] | None:
        """``(spread_bps, mid, bid_depth_bps, ask_depth_bps)``, or None.

        None when the book is one-sided or crossed. A crossed book is a transient
        Kraken publishes during fast markets; it is not a spread, so it is counted
        (``updates`` minus ``samples``) rather than recorded as a negative one.

        The depth figure is **how far from mid the book must be walked before the
        resting notional reaches** ``notional``, in basis points, each side
        independently. That is the number a cost model needs: not "is there depth"
        but "what does this size cost to fill". ``None`` on a side means the visible
        book never reached the notional at all, which is itself the finding.
        """
        if not self.bids or not self.asks:
            return None
        best_bid = max(self.bids)
        best_ask = min(self.asks)
        if best_ask <= best_bid:
            return None
        mid = (best_bid + best_ask) / 2.0
        if mid <= 0.0:
            return None
        spread_bps = (best_ask - best_bid) / mid * 10_000.0
        bid_depth = self._walk(sorted(self.bids.items(), reverse=True), mid, notional)
        ask_depth = self._walk(sorted(self.asks.items()), mid, notional)
        return spread_bps, mid, bid_depth, ask_depth

    @staticmethod
    def _walk(
        levels: Iterable[tuple[float, float]], mid: float, notional: float
    ) -> float | None:
        filled = 0.0
        for price, qty in levels:
            filled += price * qty
            if filled >= notional:
                return abs(price - mid) / mid * 10_000.0
        return None


class PairMinute:
    """One pair's accumulator for one minute. Reset at each flush, never carried."""

    __slots__ = (
        "depth_ask",
        "depth_bid",
        "mids",
        "quote_volume",
        "spreads",
        "trades",
        "updates",
        "volume",
    )

    def __init__(self) -> None:
        self.spreads: list[float] = []
        self.mids: list[float] = []
        self.depth_bid: list[float] = []
        self.depth_ask: list[float] = []
        self.updates = 0
        self.trades = 0
        self.volume = 0.0
        self.quote_volume = 0.0

    def empty(self) -> bool:
        return self.updates == 0 and self.trades == 0


class Summariser:
    """Tier 2. Turns a firehose nobody can afford to store into one row a minute.

    The rows are computed from frames that are never written down, and that trade
    is worth stating plainly: tier 2 pairs have no raw history and never will. What
    they have is a spread and depth distribution per minute, which is what the cost
    model actually reads.
    """

    def __init__(
        self,
        *,
        writer: JsonlWriter,
        depth: int,
        depth_notional_usd: float,
        interval_s: int = DEFAULT_SUMMARY_INTERVAL_S,
    ) -> None:
        if interval_s <= 0:
            raise ValueError("interval_s must be positive")
        self._writer = writer
        self._depth = depth
        self._notional = depth_notional_usd
        self._interval_s = interval_s
        self._books: dict[str, BookState] = {}
        self._minutes: dict[str, PairMinute] = {}
        self._bucket = self.bucket_of(datetime.now(UTC))
        self.rows_written = 0

    def bucket_of(self, moment: datetime) -> datetime:
        """The start of the interval a moment falls in, on the UTC hour boundary."""
        into_hour = moment.minute * 60 + moment.second
        return moment.replace(microsecond=0) - timedelta(seconds=into_hour % self._interval_s)

    def _minute(self, symbol: str) -> PairMinute:
        minute = self._minutes.get(symbol)
        if minute is None:
            minute = PairMinute()
            self._minutes[symbol] = minute
        return minute

    def handle(self, payload: dict[str, Any], ts_recv: str) -> None:
        """Sink signature shared with the raw writer; the receive time is unused
        here because a summary row is stamped with the minute it covers."""
        del ts_recv
        channel = payload.get("channel")
        if channel == "book":
            self._book(payload)
        elif channel == "trade":
            self._trade(payload)

    def _book(self, payload: dict[str, Any]) -> None:
        entries = payload.get("data")
        if not isinstance(entries, list):
            return
        is_snapshot = payload.get("type") == "snapshot"
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            symbol = _first_str(entry.get("symbol"))
            if symbol is None:
                continue
            state = self._books.get(symbol)
            if state is None:
                state = BookState(self._depth)
                self._books[symbol] = state
            if is_snapshot:
                state.reset()
            state.apply(entry)
            minute = self._minute(symbol)
            minute.updates += 1
            sample = state.sample(self._notional)
            if sample is None:
                continue
            spread_bps, mid, bid_depth, ask_depth = sample
            minute.spreads.append(spread_bps)
            minute.mids.append(mid)
            if bid_depth is not None:
                minute.depth_bid.append(bid_depth)
            if ask_depth is not None:
                minute.depth_ask.append(ask_depth)

    def _trade(self, payload: dict[str, Any]) -> None:
        entries = payload.get("data")
        if not isinstance(entries, list):
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            symbol = _first_str(entry.get("symbol"))
            price = entry.get("price")
            qty = entry.get("qty")
            if symbol is None:
                continue
            if not isinstance(price, (int, float)) or not isinstance(qty, (int, float)):
                continue
            minute = self._minute(symbol)
            minute.trades += 1
            minute.volume += float(qty)
            minute.quote_volume += float(price) * float(qty)

    def flush_due(self, now: datetime) -> int:
        """Write out the interval that has just closed, if one has. Rows written."""
        bucket = self.bucket_of(now)
        if bucket <= self._bucket:
            return 0
        written = self._flush(self._bucket)
        self._bucket = bucket
        return written

    def flush_all(self, now: datetime) -> int:
        """Write the interval in progress. Called once, on shutdown.

        The partial minute is written rather than dropped, and its ``updates`` count
        is what says it is partial. Dropping it would put a hole in the series at
        every restart, and a hole is indistinguishable from a market that stopped
        quoting.
        """
        written = self._flush(self._bucket)
        self._bucket = self.bucket_of(now)
        return written

    def _flush(self, bucket: datetime) -> int:
        minute_iso = bucket.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        written = 0
        for symbol in sorted(self._minutes):
            minute = self._minutes[symbol]
            if minute.empty():
                continue
            spreads = sorted(minute.spreads)
            mids = sorted(minute.mids)
            bids = sorted(minute.depth_bid)
            asks = sorted(minute.depth_ask)
            row: dict[str, Any] = {
                "v": SCHEMA_VERSION,
                "kind": "summary",
                "pair": symbol,
                "minute": minute_iso,
                "spread_bps": [
                    significant(quantile(spreads, 0.25), 6),
                    significant(quantile(spreads, 0.50), 6),
                    significant(quantile(spreads, 0.75), 6),
                ]
                if spreads
                else [0.0, 0.0, 0.0],
                "depth_bid_bps": significant(quantile(bids, 0.50), 6) if bids else None,
                "depth_ask_bps": significant(quantile(asks, 0.50), 6) if asks else None,
                "mid": significant(quantile(mids, 0.50)) if mids else None,
                "updates": minute.updates,
                "samples": len(spreads),
                "depth_samples": min(len(bids), len(asks)),
                "trades": minute.trades,
                "volume": significant(minute.volume),
                "quote_volume": significant(minute.quote_volume, 6),
            }
            self._writer.write(row)
            written += 1
        self._minutes.clear()
        self.rows_written += written
        return written


# --------------------------------------------------------------------------- #
# The connection
# --------------------------------------------------------------------------- #


class Stream:
    """One WebSocket connection, one tier.

    Two connections rather than one, so that a tier-2 problem — a subscribe
    rejected for one of several hundred symbols, a slow consumer, a degrade —
    cannot take tier 1 down with it. Tier 1 is the dataset that cannot be
    reconstructed; it gets a socket of its own.
    """

    def __init__(
        self,
        *,
        label: str,
        writer: JsonlWriter,
        sink: Callable[[dict[str, Any], str], None],
        url: str,
        pairs: Sequence[str],
        channels: Sequence[str],
        depth: int,
        session_extra: dict[str, Any] | None = None,
        ping_interval: float = 20.0,
        ping_timeout: float = 20.0,
    ) -> None:
        self._label = label
        self._writer = writer
        self._sink = sink
        self._url = url
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._pairs = tuple(pairs)
        self._channels = tuple(channels)
        self._depth = depth
        self._session_extra = dict(session_extra or {})
        self._subs = subscriptions(self._channels, self._pairs, depth)
        self._ws: Any = None
        self._stopping = asyncio.Event()
        #: Set when a connection drops; consumed by the next successful connect,
        #: which is what turns a reconnect into a recorded gap rather than a
        #: silent resume.
        self._disconnected_at: str | None = None
        self._disconnect_reason: str | None = None
        self._attempt = 0
        #: Reconnect delay. Reset on a *successful connect*, not on a clean
        #: return from the session loop — see the comment in `_session`.
        self._backoff = BACKOFF_INITIAL_S
        self.frames = 0

    @property
    def pairs(self) -> tuple[str, ...]:
        return self._pairs

    @property
    def connected(self) -> bool:
        """Whether a socket is open right now. Read by the heartbeat.

        A recorder that is alive but disconnected is a third state, distinct from
        both "running" and "dead", and it is the one a process check cannot see.
        """
        return self._ws is not None

    def stop(self) -> None:
        self._stopping.set()

    def write_marker(self, event: str, extra: dict[str, Any] | None = None) -> None:
        """A ``session`` marker for this tier, carrying what it subscribed to."""
        payload: dict[str, Any] = {
            "event": event,
            "tier": self._label,
            "url": self._url,
            "subscriptions": [sub["params"] for sub in self._subs],
            **self._session_extra,
            **(extra or {}),
        }
        self._writer.write(
            build_line(
                kind="session",
                pair=None,
                channel=RECORDER_CHANNEL,
                ts_exchange=None,
                ts_recv=utc_now_iso(),
                payload=payload,
            )
        )

    async def drop_to(self, pairs: Sequence[str]) -> None:
        """Shrink this stream's subscription set, in place, on the live socket.

        Used by the disk guard. Unsubscribes the dropped symbols if the socket is
        up, and rewrites ``_subs`` either way, so a later reconnect asks for the
        reduced set rather than quietly restoring the full one.
        """
        keep = tuple(pair for pair in self._pairs if pair in set(pairs))
        dropped = tuple(pair for pair in self._pairs if pair not in set(keep))
        if not dropped:
            return
        self._pairs = keep
        self._subs = subscriptions(self._channels, self._pairs, self._depth)
        ws = self._ws
        if ws is None:
            return
        for channel in self._channels:
            for start in range(0, len(dropped), SUBSCRIBE_CHUNK):
                message = {
                    "method": "unsubscribe",
                    "params": {
                        "channel": channel,
                        "symbol": list(dropped[start : start + SUBSCRIBE_CHUNK]),
                    },
                }
                with contextlib.suppress(OSError, websockets.exceptions.WebSocketException):
                    await ws.send(orjson.dumps(message).decode())

    def _write_gap(self) -> None:
        """Record the break. Called on reconnect, never on disconnect.

        Writing it on reconnect is what makes ``gap_ms`` truthful: the length of a
        gap is not known until it ends, and a marker written at disconnect time
        would have to be edited afterwards, which is forbidden.
        """
        if self._disconnected_at is None:
            return
        reconnected_at = utc_now_iso()
        gap_ms = int(
            (
                datetime.fromisoformat(reconnected_at.replace("Z", "+00:00"))
                - datetime.fromisoformat(self._disconnected_at.replace("Z", "+00:00"))
            ).total_seconds()
            * 1000
        )
        self._writer.write(
            build_line(
                kind="gap",
                pair=None,
                channel=RECORDER_CHANNEL,
                ts_exchange=None,
                ts_recv=reconnected_at,
                payload={
                    "tier": self._label,
                    "reason": self._disconnect_reason or "unknown",
                    "disconnected_at": self._disconnected_at,
                    "reconnected_at": reconnected_at,
                    "gap_ms": gap_ms,
                    "attempt": self._attempt,
                },
            )
        )
        self._disconnected_at = None
        self._disconnect_reason = None

    def _handle(self, raw: str | bytes) -> None:
        ts_recv = utc_now_iso()
        self.frames += 1
        payload = orjson.loads(raw)
        if not isinstance(payload, dict):
            # Kraken v2 sends objects. Anything else is handed on rather than
            # dropped, wrapped so the schema still holds and nothing is lost.
            payload = {"_nonobject": payload}
        self._sink(payload, ts_recv)

    async def _session(self) -> None:
        async with connect(
            self._url,
            max_size=None,
            ping_interval=self._ping_interval,
            ping_timeout=self._ping_timeout,
        ) as ws:
            self._ws = ws
            try:
                self._write_gap()
                # Reset here, on a successful connect. Resetting after `_session`
                # returns is wrong: `_session` only ever returns normally when the
                # recorder is stopping, so the backoff would compound across
                # independent, individually successful reconnects. A process that
                # drops once an hour would, half a day later, be waiting a full
                # minute to reconnect after a fault it recovers from instantly, and
                # that minute is order-book data nothing can recover.
                self._attempt = 0
                self._backoff = BACKOFF_INITIAL_S
                for sub in self._subs:
                    await ws.send(orjson.dumps(sub).decode())
                while not self._stopping.is_set():
                    receive = asyncio.ensure_future(ws.recv())
                    stop = asyncio.ensure_future(self._stopping.wait())
                    done, pending = await asyncio.wait(
                        {receive, stop}, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in pending:
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
                    if receive in done:
                        self._handle(receive.result())
            finally:
                self._ws = None

    async def run(self) -> None:
        self.write_marker("start")
        try:
            if not self._pairs:
                # An empty tier still writes its markers, so the archive says the
                # tier existed and was empty rather than saying nothing at all.
                await self._stopping.wait()
                return
            while not self._stopping.is_set():
                try:
                    await self._session()
                except (OSError, websockets.exceptions.WebSocketException) as exc:
                    self._attempt += 1
                    if self._disconnected_at is None:
                        self._disconnected_at = utc_now_iso()
                        self._disconnect_reason = f"{type(exc).__name__}: {exc}"
                    # Jitter, so a Kraken-side outage does not produce a
                    # thundering herd of reconnects on the same second.
                    delay = min(self._backoff, BACKOFF_MAX_S) * (0.5 + random.random())
                    print(
                        f"[{self._label}] disconnected ({type(exc).__name__}), "
                        f"reconnecting in {delay:.1f}s (attempt {self._attempt})",
                        file=sys.stderr,
                        flush=True,
                    )
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._stopping.wait(), timeout=delay)
                    self._backoff = min(self._backoff * BACKOFF_FACTOR, BACKOFF_MAX_S)
        finally:
            self.write_marker("stop")


def make_raw_sink(writer: JsonlWriter) -> Callable[[dict[str, Any], str], None]:
    """Tier 1's sink: the frame, verbatim, into the append-only archive."""

    def sink(payload: dict[str, Any], ts_recv: str) -> None:
        writer.write(
            build_line(
                kind="tick",
                pair=extract_pair(payload),
                channel=extract_channel(payload),
                ts_exchange=extract_ts_exchange(payload),
                ts_recv=ts_recv,
                payload=payload,
            )
        )

    return sink


# --------------------------------------------------------------------------- #
# The disk guard
# --------------------------------------------------------------------------- #


async def disk_guard(
    *,
    stream: Stream,
    path: Path,
    floor_bytes: int,
    interval_s: float,
    keep: int,
    stopping: asyncio.Event,
) -> None:
    """Degrade tier 1 rather than let the process die of a full disk.

    Sticky: once it has fired it does not fire again and does not reverse. The
    module docstring says why re-expanding would be worse than staying small.
    """
    degraded = False
    while not stopping.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stopping.wait(), timeout=interval_s)
        if stopping.is_set():
            return
        if degraded:
            continue
        try:
            free = shutil.disk_usage(path).free
        except OSError as exc:  # pragma: no cover - the path exists by construction
            print(f"disk guard could not read free space: {exc}", file=sys.stderr, flush=True)
            continue
        if free >= floor_bytes:
            continue
        kept = stream.pairs[:keep]
        dropped = stream.pairs[keep:]
        degraded = True
        if not dropped:
            continue
        banner = "!" * 72
        print(
            f"\n{banner}\n"
            f"DISK GUARD: {free / BYTES_PER_GB:.1f} GB free is below the "
            f"{floor_bytes / BYTES_PER_GB:.1f} GB floor.\n"
            f"Tier 1 drops to {', '.join(kept)} and STOPS recording {', '.join(dropped)}.\n"
            f"Tier 2 continues. This is in the archive as a session marker and it will "
            f"NOT reverse on its own.\n{banner}\n",
            file=sys.stderr,
            flush=True,
        )
        await stream.drop_to(kept)
        stream.write_marker(
            "tier1_degraded",
            {
                "free_bytes": free,
                "floor_bytes": floor_bytes,
                "kept": list(kept),
                "dropped": list(dropped),
            },
        )


# --------------------------------------------------------------------------- #
# The heartbeat — is this thing still on?
# --------------------------------------------------------------------------- #


def heartbeat_filename(source_id: str, date: str) -> str:
    return f"{HEARTBEAT_PREFIX}{NAME_SEPARATOR}{source_id}{NAME_SEPARATOR}{date}{HEARTBEAT_SUFFIX}"


class HeartbeatWriter:
    """One line a minute per tier, saying the recorder is alive and what it holds.

    Not a ``@dataclass`` — see :class:`PairStat`.

    **This exists because the recorder has died unnoticed twice.** Both times the
    symptom was a gap discovered days later in data that cannot be backfilled. The
    archive itself is a poor liveness signal: a dead recorder and a quiet market
    both produce no lines, and the difference only becomes visible once enough
    time has passed that it is already too late to act on.

    Append-only like everything else here, and rotated daily so it never grows
    without bound. It is a separate file rather than a marker in the archive for
    the reason spelled out on :data:`HEARTBEAT_PREFIX`.
    """

    __slots__ = ("_date", "_handle", "_out_dir", "_source_id", "beats")

    def __init__(self, out_dir: Path, *, source_id: str) -> None:
        self._out_dir = out_dir
        self._source_id = source_id
        self._date: str | None = None
        self._handle: Any = None
        self.beats = 0

    def path_for(self, date: str) -> Path:
        return self._out_dir / heartbeat_filename(self._source_id, date)

    def beat(self, payload: dict[str, Any]) -> None:
        stamp = utc_now_iso()
        date = utc_date_from_iso(stamp)
        if date != self._date or self._handle is None:
            self.close()
            self._out_dir.mkdir(parents=True, exist_ok=True)
            self._handle = self.path_for(date).open("ab")
            self._date = date
        self._handle.write(
            orjson.dumps({"v": SCHEMA_VERSION, "source_id": self._source_id, "ts": stamp, **payload})
        )
        self._handle.write(b"\n")
        self._handle.flush()
        self.beats += 1

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


async def heartbeat_loop(
    *,
    writers: Sequence[HeartbeatWriter],
    sample: Callable[[], Sequence[dict[str, Any]]],
    stopping: asyncio.Event,
    interval_s: float = DEFAULT_HEARTBEAT_S,
) -> int:
    """Write one heartbeat per tier per interval. Returns beats written.

    Beats immediately on entry rather than after the first interval, so a recorder
    that dies thirty seconds in still leaves a record of having started — and so
    `recorder_status.py` has something to read the moment the process is up.
    """
    written = 0
    while True:
        for writer, payload in zip(writers, sample(), strict=False):
            writer.beat(payload)
            written += 1
        if stopping.is_set():
            return written
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stopping.wait(), timeout=interval_s)
        if stopping.is_set():
            # One final beat on the way out, carrying `stopping: True`, so a clean
            # shutdown is distinguishable from a kill in the heartbeat file alone.
            for writer, payload in zip(writers, sample(), strict=False):
                writer.beat({**payload, "stopping": True})
                written += 1
            return written


# --------------------------------------------------------------------------- #
# Midnight
# --------------------------------------------------------------------------- #


async def midnight_roller(
    *,
    writers: Sequence[JsonlWriter],
    stopping: asyncio.Event,
    interval_s: float = MIDNIGHT_CHECK_S,
    now: Callable[[], str] = current_utc_date,
) -> int:
    """Close yesterday's files when the UTC date changes. Returns rotations made.

    The per-line rule in :meth:`JsonlWriter.write` already rotates a busy stream
    at the boundary, so on a normal day this task does nothing. It exists for the
    days that are not normal: a tier with no traffic across midnight, a tier 1
    degraded to three pairs during a quiet hour, a reconnect loop spanning the
    boundary. In all of those the previous day's file would otherwise stay open
    until the next frame arrived — possibly hours — and a file held open is a file
    that cannot be moved, merged or counted, which is the whole reason the day is
    the unit.
    """
    rotated = 0
    while not stopping.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stopping.wait(), timeout=interval_s)
        if stopping.is_set():
            break
        date = now()
        for writer in writers:
            if writer.roll_to(date):
                rotated += 1
                print(
                    f"rolled {writer.out_dir} over to {date} (UTC date changed)",
                    file=sys.stderr,
                    flush=True,
                )
    return rotated


# --------------------------------------------------------------------------- #
# Measurement — what the two tiers will actually cost
# --------------------------------------------------------------------------- #


def envelope_bytes() -> int:
    """The recorder's own per-line overhead, measured rather than assumed."""
    payload = {"x": 1}
    line = build_line(
        kind="tick",
        pair="BTC/USD",
        channel="book",
        ts_exchange=utc_now_iso(),
        ts_recv=utc_now_iso(),
        payload=payload,
    )
    return len(orjson.dumps(line)) - len(orjson.dumps(payload)) + 1


def summary_row_bytes() -> int:
    """One summary row's size on disk, measured from a representative row."""
    row = {
        "v": SCHEMA_VERSION,
        "kind": "summary",
        "pair": "MATIC/USD",
        "minute": "2026-09-11T16:44:00Z",
        "spread_bps": [1.23456, 2.34567, 4.56789],
        "depth_bid_bps": 12.3456,
        "depth_ask_bps": 13.4567,
        "mid": 0.12345678,
        "updates": 1234,
        "samples": 1230,
        "depth_samples": 1100,
        "trades": 12,
        "volume": 12345.678,
        "quote_volume": 15234.5,
    }
    return len(orjson.dumps(row)) + 1


async def measure_stream(
    url: str,
    pairs: Sequence[str],
    channels: Sequence[str],
    depth: int,
    seconds: float,
    *,
    settle_s: float = 8.0,
) -> tuple[int, int]:
    """``(wire_bytes, frames)`` over ``seconds``, after the snapshots have flushed.

    The settle is not optional: every subscription opens with a full book snapshot,
    and counting those as steady-state traffic overstates the rate several-fold on
    a short sample.
    """
    if not pairs or seconds <= 0:
        return 0, 0
    wire = 0
    frames = 0
    loop = asyncio.get_running_loop()
    async with connect(url, max_size=None) as ws:
        for sub in subscriptions(channels, pairs, depth):
            await ws.send(orjson.dumps(sub).decode())
        settle_end = loop.time() + settle_s
        while loop.time() < settle_end:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(ws.recv(), timeout=max(0.1, settle_end - loop.time()))
        end = loop.time() + seconds
        while loop.time() < end:
            try:
                frame = await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - loop.time()))
            except TimeoutError:
                continue
            wire += len(frame if isinstance(frame, bytes) else frame.encode())
            frames += 1
    return wire, frames


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #


def describe_tiers(
    ranked: Sequence[PairStat],
    tier1: Sequence[str],
    tier2: Sequence[str],
    unranked: Sequence[str],
) -> str:
    volumes = {stat.symbol: stat.quote_volume_24h for stat in ranked}
    lines = [
        f"ranked {len(ranked)} online pairs from the startup ticker snapshot",
        f"tier 1 (full raw, {len(tier1)}): "
        + ", ".join(f"{pair} ({volumes.get(pair, 0.0) / 1e6:.1f}M/24h)" for pair in tier1),
        f"tier 2 (summaries, {len(tier2)}): "
        + (
            ", ".join(tier2[:8]) + (" ..." if len(tier2) > 8 else "")
            if tier2
            else "none above the floor"
        ),
    ]
    if unranked:
        lines.append(
            f"{len(unranked)} online pairs produced no ticker snapshot and are in "
            f"NEITHER tier: {', '.join(unranked[:12])}"
            + (" ..." if len(unranked) > 12 else "")
        )
    return "\n".join(lines)


def existing_ancestor(path: Path) -> Path:
    """The nearest existing directory at or above ``path``.

    ``shutil.disk_usage`` needs a path that exists, and a configurable archive
    directory may legitimately not exist yet on a first run. Reporting free space
    on the parent is the right answer: it is the same filesystem.
    """
    current = path.resolve()
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


async def report_cost(
    args: argparse.Namespace,
    tier1: Sequence[str],
    tier2: Sequence[str],
    out_dir: Path,
) -> None:
    """What the two tiers cost per day, measured on the live socket.

    Measured rather than modelled, because book update rates do not follow volume:
    on 2026-09-11 XRP/USD published twice as many book updates a second as BTC/USD
    on a quarter of the volume. Any per-pair estimate from the ticker is wrong by
    multiples, in an unpredictable direction.
    """
    overhead = envelope_bytes()
    seconds = float(args.measure_s)
    print(
        f"measuring each tier for {seconds:.0f}s on the live socket (plus settle) ...",
        file=sys.stderr,
        flush=True,
    )
    wire1, frames1 = await measure_stream(args.url, tier1, TIER1_CHANNELS, args.depth, seconds)
    day = 86400.0 / seconds
    tier1_gb = (wire1 + frames1 * overhead) * day / BYTES_PER_GB
    print(
        f"tier 1: {len(tier1)} pairs, {frames1 / seconds:.1f} frames/s, "
        f"{wire1 * day / BYTES_PER_GB:.2f} GB/day on the wire, "
        f"{tier1_gb:.2f} GB/day written (envelope {overhead} B/line)",
        file=sys.stderr,
        flush=True,
    )

    sample = list(tier2[: args.measure_tier2_sample])
    wire2, frames2 = await measure_stream(args.url, sample, TIER2_CHANNELS, args.depth, seconds)
    if sample:
        scale = len(tier2) / len(sample)
        print(
            f"tier 2: {len(tier2)} pairs, measured on a {len(sample)}-pair sample -> "
            f"{frames2 / seconds * scale:.0f} frames/s and "
            f"{wire2 * day * scale / BYTES_PER_GB:.1f} GB/day INBOUND, none of it written",
            file=sys.stderr,
            flush=True,
        )
    rows_per_day = len(tier2) * (86400 // args.summary_interval_s)
    tier2_gb = rows_per_day * summary_row_bytes() / BYTES_PER_GB
    print(
        f"tier 2: {rows_per_day} rows/day x {summary_row_bytes()} B = "
        f"{tier2_gb:.3f} GB/day written",
        file=sys.stderr,
        flush=True,
    )

    total = tier1_gb + tier2_gb
    free = shutil.disk_usage(existing_ancestor(out_dir)).free
    runway = (free - args.disk_floor_gb * BYTES_PER_GB) / BYTES_PER_GB / total if total else 0.0
    print(
        f"total {total:.2f} GB/day written; {free / BYTES_PER_GB:.1f} GB free, so "
        f"{runway:.1f} days before the {args.disk_floor_gb:.0f} GB floor degrades tier 1",
        file=sys.stderr,
        flush=True,
    )


def resolve_storage(args: argparse.Namespace) -> tuple[Path, Path, str]:
    """``(raw_dir, summary_dir, source_id)``, from the flag, then the config, then
    the built-in default — in that order, per value."""
    config = load_recorder_config(Path(args.config) if args.config else None)
    raw_dir = Path(args.out or _config_str(config, "archive_dir") or DEFAULT_OUT_DIR)
    summary_dir = Path(
        args.summary_out or _config_str(config, "summary_dir") or DEFAULT_SUMMARY_DIR
    )
    named = args.source_id or _config_str(config, "source_id")
    source_id = sanitise_source_id(named) if named else default_source_id()
    return raw_dir, summary_dir, source_id


async def _run(args: argparse.Namespace) -> int:
    raw_dir, summary_dir, source_id = resolve_storage(args)
    print(
        f"archive {raw_dir} / summaries {summary_dir}, source id {source_id!r} "
        f"(files are {archive_filename('kraken_v2', source_id, current_utc_date())})",
        file=sys.stderr,
        flush=True,
    )

    ranked, unranked = await discover_with_retry(args.url, quote=args.quote)
    tier1, tier2 = derive_tiers(
        ranked,
        tier1_count=args.tier1_count,
        tier2_floor_usd=args.tier2_floor_usd,
        tier1_override=args.tier1_pairs,
    )
    print(describe_tiers(ranked, tier1, tier2, unranked), file=sys.stderr, flush=True)

    if args.dry_run:
        if args.measure_s > 0:
            await report_cost(args, tier1, tier2, raw_dir)
        return 0

    session_extra: dict[str, Any] = {
        "quote": args.quote,
        "tier1": list(tier1),
        "tier2": list(tier2),
        "tier1_count": args.tier1_count,
        "tier2_floor_usd": args.tier2_floor_usd,
        "depth": args.depth,
        "depth_notional_usd": args.depth_notional_usd,
        "summary_interval_s": args.summary_interval_s,
        "derived_from": "ws v2 instrument snapshot + ticker snapshot, 24h volume x vwap",
        "unranked": list(unranked),
        "snapshot_at": utc_now_iso(),
        # In the marker as well as in the filename. A file can be renamed; a line
        # inside an append-only archive cannot, so this is the copy that survives.
        "source_id": source_id,
    }

    stopping = asyncio.Event()
    # One lock per distinct output directory, taken before a single byte is
    # written and held for the life of the process. `dict.fromkeys` rather than a
    # set so that a configuration pointing both tiers at one directory takes one
    # lock rather than deadlocking against itself.
    lock_dirs = list(dict.fromkeys((raw_dir.resolve(), summary_dir.resolve())))
    with (
        contextlib.ExitStack() as locks,
        JsonlWriter(raw_dir, source_id=source_id) as raw_writer,
        JsonlWriter(
            summary_dir,
            prefix="summary",
            source_id=source_id,
            validator=validate_summary_line,
            date_of=summary_date,
        ) as summary_writer,
        HeartbeatWriter(raw_dir, source_id=source_id) as raw_heartbeat,
        HeartbeatWriter(summary_dir, source_id=source_id) as summary_heartbeat,
    ):
        for directory in lock_dirs:
            locks.enter_context(ArchiveLock(directory))
        summariser = Summariser(
            writer=summary_writer,
            depth=args.depth,
            depth_notional_usd=args.depth_notional_usd,
            interval_s=args.summary_interval_s,
        )
        tier1_stream = Stream(
            label="tier1",
            writer=raw_writer,
            sink=make_raw_sink(raw_writer),
            url=args.url,
            pairs=tier1,
            channels=TIER1_CHANNELS,
            depth=args.depth,
            session_extra=session_extra,
            ping_interval=args.ping_interval,
            ping_timeout=args.ping_timeout,
        )
        tier2_stream = Stream(
            label="tier2",
            writer=summary_writer,
            sink=summariser.handle,
            url=args.url,
            pairs=tier2,
            channels=TIER2_CHANNELS,
            depth=args.depth,
            session_extra=session_extra,
            ping_interval=args.ping_interval,
            ping_timeout=args.ping_timeout,
        )

        def stop() -> None:
            stopping.set()
            tier1_stream.stop()
            tier2_stream.stop()

        loop = asyncio.get_running_loop()
        with contextlib.suppress(NotImplementedError):
            for signame in ("SIGINT", "SIGTERM"):
                sig = getattr(signal, signame, None)
                if sig is not None:
                    loop.add_signal_handler(sig, stop)

        async def flush_loop() -> None:
            while not stopping.is_set():
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stopping.wait(), timeout=1.0)
                if stopping.is_set():
                    break
                summariser.flush_due(datetime.now(UTC))
            summariser.flush_all(datetime.now(UTC))

        def heartbeat_sample() -> list[dict[str, Any]]:
            """One payload per tier, in the writers' order.

            Sampled at beat time rather than held, so a degraded tier 1 reports its
            reduced pair list from the next beat onward. The pair list is in every
            beat and not only in the session marker because the question
            `recorder_status.py` answers is "what is it recording *now*", and a
            marker written at startup cannot answer that after a disk-guard
            degrade.
            """
            return [
                {
                    "tier": "tier1",
                    "pairs": list(tier1_stream.pairs),
                    "pair_count": len(tier1_stream.pairs),
                    "frames": tier1_stream.frames,
                    "lines_written": raw_writer.lines_written,
                    "bytes_written": raw_writer.bytes_written,
                    "archive_dir": raw_dir.as_posix(),
                    "open_date": raw_writer.open_date,
                    "connected": tier1_stream.connected,
                },
                {
                    "tier": "tier2",
                    "pairs": list(tier2_stream.pairs),
                    "pair_count": len(tier2_stream.pairs),
                    "frames": tier2_stream.frames,
                    "lines_written": summariser.rows_written,
                    "bytes_written": summary_writer.bytes_written,
                    "archive_dir": summary_dir.as_posix(),
                    "open_date": summary_writer.open_date,
                    "connected": tier2_stream.connected,
                },
            ]

        tasks = [
            asyncio.ensure_future(tier1_stream.run()),
            asyncio.ensure_future(tier2_stream.run()),
            asyncio.ensure_future(flush_loop()),
            asyncio.ensure_future(
                heartbeat_loop(
                    writers=(raw_heartbeat, summary_heartbeat),
                    sample=heartbeat_sample,
                    stopping=stopping,
                    interval_s=args.heartbeat_s,
                )
            ),
            asyncio.ensure_future(
                midnight_roller(
                    writers=(raw_writer, summary_writer),
                    stopping=stopping,
                    interval_s=args.midnight_check_s,
                )
            ),
            asyncio.ensure_future(
                disk_guard(
                    stream=tier1_stream,
                    path=raw_dir,
                    floor_bytes=int(args.disk_floor_gb * BYTES_PER_GB),
                    interval_s=args.disk_check_s,
                    keep=args.degraded_tier1_count,
                    stopping=stopping,
                )
            ),
        ]
        gathered = asyncio.gather(*tasks)
        try:
            if args.duration_s > 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(gathered), timeout=args.duration_s)
                stop()
            await gathered
        except KeyboardInterrupt:
            stop()
            await gathered
        print(
            f"tier 1: {raw_writer.lines_written} lines "
            f"({raw_writer.bytes_written / BYTES_PER_GB:.3f} GB) to {raw_dir}; "
            f"tier 2: {summariser.rows_written} summary rows to {summary_dir}; "
            f"source id {source_id}, {raw_writer.rotations + summary_writer.rotations} "
            f"daily rotations",
            file=sys.stderr,
            flush=True,
        )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="record.py",
        description=(
            "Standalone two-tier Kraken WebSocket v2 recorder. Public data only. "
            "Both pair lists are derived from a live snapshot; there is no default "
            "pair list in this file."
        ),
    )
    parser.add_argument("--url", default=KRAKEN_WS_V2_URL, help="Kraken WebSocket v2 endpoint")
    parser.add_argument(
        "--quote", default=DEFAULT_QUOTE, help="quote currency both tiers are drawn from"
    )
    parser.add_argument(
        "--tier1-pairs",
        nargs="+",
        default=None,
        help=(
            "override tier 1 with these symbols instead of the top --tier1-count by "
            "24h quote volume. Kraken v2 spelling, e.g. BTC/USD (not XBT/USD)."
        ),
    )
    parser.add_argument(
        "--tier1-count",
        type=int,
        default=DEFAULT_TIER1_COUNT,
        help="how many of the most liquid pairs get full raw recording",
    )
    parser.add_argument(
        "--tier2-floor-usd",
        type=float,
        default=DEFAULT_TIER2_FLOOR_USD,
        help="24h quote volume a pair must clear to be summarised at all",
    )
    parser.add_argument(
        "--depth-notional-usd",
        type=float,
        default=DEFAULT_DEPTH_NOTIONAL_USD,
        help="the notional the summary's depth figure is measured at, each side",
    )
    parser.add_argument(
        "--summary-interval-s",
        type=int,
        default=DEFAULT_SUMMARY_INTERVAL_S,
        help="seconds per summary row. 60 divides 1, 5 and 15 minutes evenly.",
    )
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="order book depth")
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "config file carrying a `recorder:` mapping. Default: config/recorder.yaml "
            "then config/default.yaml, looked for in the working directory and beside "
            "this script. A named file that does not exist is an error; the defaults "
            "being absent is not."
        ),
    )
    parser.add_argument(
        "--out",
        default=None,
        help=(
            f"tier 1 output directory. Overrides recorder.archive_dir; "
            f"default {DEFAULT_OUT_DIR}"
        ),
    )
    parser.add_argument(
        "--summary-out",
        default=None,
        help=(
            f"tier 2 output directory. Overrides recorder.summary_dir; "
            f"default {DEFAULT_SUMMARY_DIR}"
        ),
    )
    parser.add_argument(
        "--source-id",
        default=None,
        help=(
            "which machine this recording came from; it goes into every filename. "
            "Overrides recorder.source_id; defaults to the hostname."
        ),
    )
    parser.add_argument(
        "--heartbeat-s",
        type=float,
        default=DEFAULT_HEARTBEAT_S,
        help=(
            "how often each tier writes a liveness line to "
            "heartbeat__<source>__<date>.ndjson beside its archive. Read by "
            "scripts/recorder_status.py. Deliberately not written into the archive "
            "itself: it would mask a dead subscription in recording_report.py."
        ),
    )
    parser.add_argument(
        "--midnight-check-s",
        type=float,
        default=MIDNIGHT_CHECK_S,
        help=(
            "how often the UTC date is checked so a quiet stream still closes "
            "yesterday's file at midnight"
        ),
    )
    parser.add_argument(
        "--disk-floor-gb",
        type=float,
        default=DEFAULT_DISK_FLOOR_GB,
        help="free space below which tier 1 degrades to its top pairs",
    )
    parser.add_argument(
        "--disk-check-s",
        type=float,
        default=DEFAULT_DISK_CHECK_S,
        help="how often free space is checked, in seconds",
    )
    parser.add_argument(
        "--degraded-tier1-count",
        type=int,
        default=DEGRADED_TIER1_COUNT,
        help="how many tier 1 pairs survive a disk-guard degrade",
    )
    parser.add_argument(
        "--ping-interval",
        type=float,
        default=20.0,
        help="keepalive ping interval in seconds",
    )
    parser.add_argument(
        "--ping-timeout",
        type=float,
        default=20.0,
        help=(
            "keepalive pong deadline in seconds. Lowering it below the round trip to Kraken "
            "deliberately induces a disconnect, which is how the reconnect and gap-marker path "
            "is exercised against the live exchange rather than against a mock."
        ),
    )
    parser.add_argument(
        "--duration-s",
        type=float,
        default=0.0,
        help="stop after this many seconds; 0 runs until interrupted",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="derive both tiers, report, and exit without recording anything",
    )
    parser.add_argument(
        "--measure-s",
        type=float,
        default=0.0,
        help=(
            "with --dry-run, measure each tier live for this many seconds and report "
            "GB/day"
        ),
    )
    parser.add_argument(
        "--measure-tier2-sample",
        type=int,
        default=120,
        help="how many tier 2 pairs to measure before scaling to the whole tier",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 0
    except ArchiveLockedError as exc:
        # A refusal, printed as a refusal. A traceback here would read as a crash,
        # and the operator's next move — find the other recorder — is in the text.
        print(f"\nREFUSING TO START: {exc}\n", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
