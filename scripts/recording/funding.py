#!/usr/bin/env python
"""Standalone Kraken Futures funding-rate and open-interest poller.

This script imports **nothing** from ``src/acsoe/`` and nothing from the other
scripts either — like ``record.py``, it has to be copyable on its own onto a
machine with no project checkout. The few helpers it shares with the recorder
(the config reader, the source id, the lock, the line schema) are carried here as
copies for the same reason the archive mover carries its own filename parser.

It records **public** data only and holds no credentials.

## Why this exists

The spot recorder cannot see the perpetual-swap market, and the perpetual is
where the leverage sits. Two figures from it bear on a multi-hour barrier race
on the spot pair: the **funding rate**, which is the price the crowded side is
paying to stay in, and the **open interest**, which is how much is in. Funding
history is backfillable from the venue's REST endpoint at any later date. Open
interest is not: the venue publishes the current figure and no series, so an
hour not polled is an hour of open-interest history nobody can get back. That
asymmetry is the reason this is a live poller rather than a one-off download,
and why it polls open interest at all.

## What it records, and from where

Once an hour, on the hour, one ``GET`` of Kraken Futures' public ticker list::

    https://futures.kraken.com/derivatives/api/v3/tickers

and from it, for every perpetual whose underlying pair matches a tier 1 spot
pair and whose 24-hour quote volume clears ``--floor-usd``, one line carrying the
ticker entry **verbatim** — ``fundingRate``, ``fundingRatePrediction``,
``openInterest``, ``markPrice`` and the rest, exactly as the venue sent them.
Nothing is renamed and nothing is derived, so a change to the venue's field set
lands in the archive rather than in a translation table that silently stopped
matching.

With ``--backfill`` it also pulls each matched symbol's funding history once::

    https://futures.kraken.com/derivatives/api/v3/historical-funding-rates?symbol=

into a separate ``funding_history`` file dated by the day of the fetch, never
into a past day's file: the archive is append-only and a file for a finished day
is finished.

## Which spot pairs, and how a perpetual is matched to one

The tier 1 list is read from the recorder's own heartbeat — the newest
``heartbeat__*.ndjson`` beside the raw archive, last ``tier1`` beat — on every
poll, so a disk-guard degrade that shrinks tier 1 shrinks this list with it.
``--pairs`` overrides it. There is no default list in this file.

A spot symbol ``BASE/QUOTE`` matches a futures ticker whose ``tag`` is
``perpetual`` and whose ``pair`` is ``BASE:QUOTE`` — or the same with the
venue's own alias for the base, because Kraken Futures still calls Bitcoin
``XBT`` where the spot v2 socket calls it ``BTC``. That two-entry alias table is
the one piece of naming this file carries, and every poll writes down which spot
pairs matched which futures symbols and which matched nothing, so an alias that
is missing shows up as an unmatched pair in the archive rather than as a series
that quietly never existed. ``--symbols`` names futures symbols directly for the
case where the table is wrong.

Every matching perpetual is recorded, not the largest one. Where the venue lists
both an inverse (``PI_``) and a flexible (``PF_``) contract on the same pair,
both clear the floor or neither does, and choosing between them here would be a
decision the data can make later for free.

## Where the file goes

``<archive_dir>/funding/funding__<source_id>__<date>.jsonl`` by default —
``recorder.funding_dir`` in ``config/recorder.yaml`` or ``--out`` override it.
Under the archive directory, tagged by source like every other file, and in a
subdirectory of its own for one reason: ``scripts/recording_report.py`` measures
the raw archive's continuity as the distance between consecutive lines in every
``*.jsonl`` it finds there, and an hourly line in that directory would cut a
three-hour outage into three one-hour ones. That is the same argument that keeps
the heartbeat out of the archive, and it applies here with the same force.

## Line schema

The same seven keys as the raw archive, so a reader that already parses
``data/raw/`` parses this::

    v            int    always 1
    kind         str    "tick" | "gap" | "session"
    pair         str|None  the SPOT symbol the line is about, e.g. "BTC/USD"
    channel      str    "funding" | "funding_history" | "_recorder" for a marker
    ts_exchange  str|None  the venue's serverTime, or the rate's own timestamp
    ts_recv      str    ISO-8601 UTC ending "Z", wall clock at the poll
    payload      dict   {"futures_symbol", "endpoint", "ticker": <entry verbatim>}
                        or {"futures_symbol", "endpoint", "rate": <entry verbatim>}

A poll that fails after its retries is written as a ``gap`` marker naming the
slot it missed, so a missing hour in the series is a recorded outage and not an
absence a reader has to infer.

Usage::

    python scripts/recording/funding.py                  # poll hourly, forever
    python scripts/recording/funding.py --once           # one poll, then exit
    python scripts/recording/funding.py --once --backfill
    python scripts/recording/funding.py --pairs BTC/USD ETH/USD --floor-usd 5e6
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Self

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

SCHEMA_VERSION: Final = 1

FUTURES_TICKERS_URL: Final = "https://futures.kraken.com/derivatives/api/v3/tickers"
FUTURES_HISTORY_URL: Final = (
    "https://futures.kraken.com/derivatives/api/v3/historical-funding-rates"
)

RECORDER_CHANNEL: Final = "_recorder"
FUNDING_CHANNEL: Final = "funding"
HISTORY_CHANNEL: Final = "funding_history"
FUNDING_PREFIX: Final = "funding"
HISTORY_PREFIX: Final = "funding_history"

LINE_KEYS: Final = frozenset(
    {"v", "kind", "pair", "channel", "ts_exchange", "ts_recv", "payload"}
)
LINE_KINDS: Final = frozenset({"tick", "gap", "session"})

#: The venue's expiry grouping for a perpetual swap, as the ticker's ``tag``.
PERPETUAL_TAG: Final = "perpetual"

#: Where the spot socket and the futures venue disagree on a base asset's name.
#: Two entries, both long-standing, and every poll records which spot pairs
#: matched nothing so a third one cannot go unnoticed.
BASE_ALIASES: Final = {"BTC": "XBT", "DOGE": "XDG"}

DEFAULT_INTERVAL_S: Final = 3600
DEFAULT_FLOOR_USD: Final = 1_000_000.0
DEFAULT_FUNDING_SUBDIR: Final = "funding"
DEFAULT_ARCHIVE_DIR: Final = Path("data") / "raw"

HTTP_TIMEOUT_S: Final = 20.0
#: Attempts per slot before the slot is written down as a gap. Four attempts at
#: 5, 10, 20 and 40 seconds is a little over a minute, well inside the hour.
RETRY_DELAYS_S: Final = (5.0, 10.0, 20.0, 40.0)

CONFIG_CANDIDATES: Final = (
    Path("config") / "recorder.yaml",
    Path("config") / "default.yaml",
)
CONFIG_SECTION: Final = "recorder"

SOURCE_ID_ALLOWED: Final = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-"
)
SOURCE_ID_MAX: Final = 48
NAME_SEPARATOR: Final = "__"

#: One per output directory, same mechanism as the recorder's, different file so
#: the poller and the recorder can share a directory without fencing each other.
LOCK_FILENAME: Final = ".funding.lock"
HEARTBEAT_GLOB: Final = "heartbeat__*.ndjson"


class SchemaError(ValueError):
    """A line failed validation on write. Never suppressed."""


class ArchiveLockedError(RuntimeError):
    """Another poller already holds this output directory."""


class PollError(RuntimeError):
    """The venue could not be read, or answered with something that is not a
    ticker list."""


# --------------------------------------------------------------------------- #
# Configuration, source id, lock — copies of the recorder's, on purpose
# --------------------------------------------------------------------------- #


def _config_search_paths(explicit: Path | None) -> list[Path]:
    if explicit is not None:
        return [explicit]
    here = Path(__file__).resolve().parent.parent.parent
    paths: list[Path] = []
    for base in (Path.cwd(), here):
        for candidate in CONFIG_CANDIDATES:
            resolved = base / candidate
            if resolved not in paths:
                paths.append(resolved)
    return paths


def load_recorder_config(explicit: Path | None = None) -> dict[str, Any]:
    """The ``recorder:`` mapping, or ``{}`` — same contract as ``record.py``."""
    if explicit is not None and not explicit.is_file():
        raise FileNotFoundError(f"--config {explicit} does not exist")
    try:
        import yaml
    except ImportError:
        if explicit is not None:
            raise
        print(
            "PyYAML is not installed, so config/recorder.yaml was not read; "
            "using built-in defaults.",
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
    value = config.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _config_number(config: dict[str, Any], key: str) -> float | None:
    value = config.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def sanitise_source_id(raw: str) -> str:
    folded = "".join(char if char in SOURCE_ID_ALLOWED else "-" for char in raw.strip())
    while "--" in folded:
        folded = folded.replace("--", "-")
    folded = folded.strip("-.").lower()[:SOURCE_ID_MAX]
    if not folded:
        raise ValueError(
            f"source id {raw!r} contains nothing usable in a filename. Set "
            f"recorder.source_id in config/recorder.yaml or pass --source-id."
        )
    return folded


def default_source_id() -> str:
    return sanitise_source_id(socket.gethostname() or "unknown")


def _lock_exclusive(handle: Any) -> None:
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
    """One poller per output directory, enforced by the kernel. See the
    recorder's copy for why it is not a PID file."""

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
                f"another funding poller is already writing to {self._directory}.\n"
                f"  The lock is {self._path} and it is held by a live process.\n"
                f"  Stop the other poller, or start this one with a different --out."
            ) from exc
        self._handle = handle
        with contextlib.suppress(OSError):
            handle.seek(0)
            handle.truncate()
            handle.write(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "host": socket.gethostname(),
                        "acquired_at": utc_now_iso(),
                        "note": "diagnostic only; the lock is the OS lock on this file",
                    }
                ).encode()
                + b"\n"
            )
            handle.flush()
        return self

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


# --------------------------------------------------------------------------- #
# Time, names, lines
# --------------------------------------------------------------------------- #


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def utc_now_iso() -> str:
    return iso_z(utc_now())


def utc_date_from_iso(ts: str) -> str:
    return ts[:10]


def archive_filename(prefix: str, source_id: str, date: str) -> str:
    return f"{prefix}{NAME_SEPARATOR}{source_id}{NAME_SEPARATOR}{date}.jsonl"


def next_slot(now: datetime, interval_s: int) -> datetime:
    """The first interval boundary strictly after ``now``, counted from midnight
    UTC — so an hourly poller polls on the hour and two pollers on two machines
    poll the same instant."""
    if interval_s <= 0:
        raise ValueError("interval_s must be positive")
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = (now - midnight).total_seconds()
    slots = int(elapsed // interval_s) + 1
    return midnight + timedelta(seconds=slots * interval_s)


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
    """The raw archive's seven-key validator, verbatim in its rules."""
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


def _exchange_ts(value: object) -> str | None:
    """The venue's timestamp when it is one we can store, else null — never the
    receive time, which would turn a latency into zero."""
    if isinstance(value, str) and value.endswith("Z"):
        return value
    return None


class JsonlWriter:
    """Append-only, one file per UTC day per source, rotated by the line's own
    ``ts_recv``. Never truncates."""

    def __init__(self, out_dir: Path, *, prefix: str, source_id: str) -> None:
        self._out_dir = out_dir
        self._prefix = prefix
        self._source_id = source_id
        self._date: str | None = None
        self._handle: Any = None
        self.lines_written = 0

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

    def path_for(self, date: str) -> Path:
        return self._out_dir / archive_filename(self._prefix, self._source_id, date)

    def write(self, line: dict[str, Any]) -> None:
        validate_line(line)
        date = utc_date_from_iso(str(line["ts_recv"]))
        if date != self._date or self._handle is None:
            self.close()
            self._out_dir.mkdir(parents=True, exist_ok=True)
            self._handle = self.path_for(date).open("ab")
            self._date = date
        self._handle.write(json.dumps(line, separators=(",", ":")).encode("utf-8"))
        self._handle.write(b"\n")
        self._handle.flush()
        self.lines_written += 1

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


# --------------------------------------------------------------------------- #
# Which spot pairs — the recorder's heartbeat, never a written list
# --------------------------------------------------------------------------- #


def tier1_pairs_from_heartbeat(archive_dir: Path) -> tuple[str, ...]:
    """Tier 1 as the recorder last reported it.

    The newest heartbeat file by modification time, its last ``tier1`` beat. Read
    on every poll so a degrade is followed. Raises rather than returning an empty
    tuple when there is nothing to read, because "no tier 1" and "could not find
    the recorder" are different facts and only one of them is a reason to record
    nothing.
    """
    if not archive_dir.is_dir():
        raise RuntimeError(
            f"{archive_dir} does not exist, so there is no recorder heartbeat to read "
            f"tier 1 from. Pass --pairs, or --archive pointing at the raw archive."
        )
    beats = [path for path in archive_dir.glob(HEARTBEAT_GLOB) if path.is_file()]
    newest = max(beats, key=lambda path: path.stat().st_mtime, default=None)
    if newest is None:
        raise RuntimeError(
            f"no {HEARTBEAT_GLOB} in {archive_dir}. The recorder writes one beside its "
            f"archive; if it has never run here, pass --pairs."
        )
    pairs: tuple[str, ...] | None = None
    for raw in newest.read_bytes().splitlines():
        if not raw.strip():
            continue
        try:
            beat = json.loads(raw)
        except ValueError:
            continue  # a half-written final line after a kill; the previous one stands
        if not isinstance(beat, dict) or beat.get("tier") != "tier1":
            continue
        listed = beat.get("pairs")
        if isinstance(listed, list) and all(isinstance(item, str) for item in listed):
            pairs = tuple(listed)
    if pairs is None:
        raise RuntimeError(f"{newest} carries no tier1 beat with a pair list")
    return pairs


# --------------------------------------------------------------------------- #
# Matching a spot pair to its perpetual
# --------------------------------------------------------------------------- #


def perp_pairs_for(spot_symbol: str) -> tuple[str, ...]:
    """The futures ``pair`` strings a spot symbol may appear under."""
    if "/" not in spot_symbol:
        return ()
    base, quote = spot_symbol.split("/", 1)
    candidates = [f"{base}:{quote}"]
    alias = BASE_ALIASES.get(base)
    if alias is not None:
        candidates.append(f"{alias}:{quote}")
    return tuple(candidates)


def quote_volume_24h(ticker: dict[str, Any]) -> float | None:
    """The ticker's 24-hour volume in quote currency, or None when it says
    neither ``volumeQuote`` nor enough to derive it."""
    direct = ticker.get("volumeQuote")
    if isinstance(direct, (int, float)) and not isinstance(direct, bool) and direct >= 0:
        return float(direct)
    vol = ticker.get("vol24h")
    mark = ticker.get("markPrice")
    if (
        isinstance(vol, (int, float))
        and isinstance(mark, (int, float))
        and not isinstance(vol, bool)
        and not isinstance(mark, bool)
        and vol >= 0
        and mark > 0
    ):
        return float(vol) * float(mark)
    return None


class Matching:
    """What one poll matched, and what it did not. Not a ``@dataclass`` — this
    file is loaded by path in its tests, same as ``record.py``."""

    __slots__ = ("below_floor", "matched", "unmatched")

    def __init__(self) -> None:
        #: ``(spot_symbol, ticker)`` for every perpetual that cleared the floor.
        self.matched: list[tuple[str, dict[str, Any]]] = []
        #: Spot pairs with no perpetual listed at all.
        self.unmatched: list[str] = []
        #: Perpetuals that exist but did not clear the floor this poll.
        self.below_floor: list[dict[str, Any]] = []

    def summary(self) -> dict[str, Any]:
        by_spot: dict[str, list[str]] = {}
        for spot, ticker in self.matched:
            by_spot.setdefault(spot, []).append(str(ticker.get("symbol")))
        return {
            "matched": by_spot,
            "unmatched": list(self.unmatched),
            "below_floor": list(self.below_floor),
        }


def match_perpetuals(
    spot_pairs: Sequence[str],
    tickers: Iterable[Any],
    *,
    floor_usd: float,
    symbols: Sequence[str] | None = None,
) -> Matching:
    """Pair every tier 1 spot symbol with the perpetuals on its underlying.

    ``symbols`` names futures symbols directly and bypasses the pair match for
    them; they are attributed to the spot pair whose candidates they carry, or to
    their own symbol when none does.
    """
    wanted = set(symbols or ())
    by_pair: dict[str, list[dict[str, Any]]] = {}
    by_symbol: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        if not isinstance(ticker, dict):
            continue
        symbol = ticker.get("symbol")
        if isinstance(symbol, str):
            by_symbol[symbol] = ticker
        if ticker.get("tag") != PERPETUAL_TAG:
            continue
        pair = ticker.get("pair")
        if isinstance(pair, str):
            by_pair.setdefault(pair, []).append(ticker)

    result = Matching()
    seen: set[str] = set()
    for spot in spot_pairs:
        found = False
        for candidate in perp_pairs_for(spot):
            for ticker in by_pair.get(candidate, ()):
                symbol = str(ticker.get("symbol"))
                found = True
                volume = quote_volume_24h(ticker)
                if symbol in wanted or (volume is not None and volume >= floor_usd):
                    result.matched.append((spot, ticker))
                    seen.add(symbol)
                else:
                    result.below_floor.append(
                        {"spot_symbol": spot, "futures_symbol": symbol, "volume_quote": volume}
                    )
        if not found:
            result.unmatched.append(spot)
    for symbol in sorted(wanted - seen):
        named = by_symbol.get(symbol)
        if named is not None:
            result.matched.append((symbol, named))
    return result


# --------------------------------------------------------------------------- #
# The venue
# --------------------------------------------------------------------------- #


def fetch_json(url: str, *, timeout_s: float = HTTP_TIMEOUT_S) -> dict[str, Any]:
    """One GET, parsed. Raises :class:`PollError` on anything but a success
    envelope — the venue wraps errors in HTTP 200 like its spot sibling does."""
    request = urllib.request.Request(url, headers={"User-Agent": "acsoe-funding-poller/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = response.read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise PollError(f"{type(exc).__name__}: {exc}") from exc
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise PollError(f"the venue answered with something that is not JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise PollError("the venue answered with a JSON value that is not an object")
    if parsed.get("result") != "success":
        raise PollError(f"the venue answered {parsed.get('result')!r}: {parsed.get('error')!r}")
    return parsed


Fetch = Callable[[str], dict[str, Any]]


def funding_line(
    spot: str, ticker: dict[str, Any], *, server_time: object, ts_recv: str
) -> dict[str, Any]:
    return build_line(
        kind="tick",
        pair=spot,
        channel=FUNDING_CHANNEL,
        ts_exchange=_exchange_ts(server_time),
        ts_recv=ts_recv,
        payload={
            "futures_symbol": ticker.get("symbol"),
            "endpoint": FUTURES_TICKERS_URL,
            "ticker": ticker,
        },
    )


def history_lines(
    spot: str, symbol: str, rates: Iterable[Any], *, ts_recv: str
) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for rate in rates:
        if not isinstance(rate, dict):
            continue
        lines.append(
            build_line(
                kind="tick",
                pair=spot,
                channel=HISTORY_CHANNEL,
                ts_exchange=_exchange_ts(rate.get("timestamp")),
                ts_recv=ts_recv,
                payload={
                    "futures_symbol": symbol,
                    "endpoint": FUTURES_HISTORY_URL,
                    "rate": rate,
                },
            )
        )
    return lines


def gap_line(*, slot: str, reason: str, attempts: int, ts_recv: str) -> dict[str, Any]:
    return build_line(
        kind="gap",
        pair=None,
        channel=RECORDER_CHANNEL,
        ts_exchange=None,
        ts_recv=ts_recv,
        payload={
            "poller": FUNDING_CHANNEL,
            "slot": slot,
            "reason": reason,
            "attempts": attempts,
        },
    )


def session_line(event: str, extra: dict[str, Any], *, ts_recv: str) -> dict[str, Any]:
    return build_line(
        kind="session",
        pair=None,
        channel=RECORDER_CHANNEL,
        ts_exchange=None,
        ts_recv=ts_recv,
        payload={"event": event, "poller": FUNDING_CHANNEL, **extra},
    )


def poll_once(
    writer: JsonlWriter,
    spot_pairs: Sequence[str],
    *,
    floor_usd: float,
    symbols: Sequence[str] | None = None,
    fetch: Fetch = fetch_json,
    now_iso: Callable[[], str] = utc_now_iso,
) -> Matching:
    """One GET of the ticker list, one line per matched perpetual. Raises
    :class:`PollError` when the venue could not be read; writes nothing then."""
    answer = fetch(FUTURES_TICKERS_URL)
    tickers = answer.get("tickers")
    if not isinstance(tickers, list):
        raise PollError("the ticker list is missing from the venue's answer")
    matching = match_perpetuals(spot_pairs, tickers, floor_usd=floor_usd, symbols=symbols)
    ts_recv = now_iso()
    for spot, ticker in matching.matched:
        writer.write(funding_line(spot, ticker, server_time=answer.get("serverTime"), ts_recv=ts_recv))
    return matching


def backfill(
    writer: JsonlWriter,
    matching: Matching,
    *,
    fetch: Fetch = fetch_json,
    now_iso: Callable[[], str] = utc_now_iso,
) -> int:
    """Every matched symbol's published funding history, verbatim. Lines written."""
    written = 0
    for spot, ticker in matching.matched:
        symbol = ticker.get("symbol")
        if not isinstance(symbol, str):
            continue
        url = FUTURES_HISTORY_URL + "?" + urllib.parse.urlencode({"symbol": symbol})
        answer = fetch(url)
        rates = answer.get("rates")
        if not isinstance(rates, list):
            raise PollError(f"no rates in the funding history for {symbol}")
        for line in history_lines(spot, symbol, rates, ts_recv=now_iso()):
            writer.write(line)
            written += 1
    return written


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #


def resolve_storage(args: argparse.Namespace) -> tuple[Path, Path, str, float, int]:
    """``(archive_dir, out_dir, source_id, floor_usd, interval_s)`` — flag, then
    config, then default, per value."""
    config = load_recorder_config(Path(args.config) if args.config else None)
    archive_dir = Path(args.archive or _config_str(config, "archive_dir") or DEFAULT_ARCHIVE_DIR)
    out_dir = Path(
        args.out or _config_str(config, "funding_dir") or (archive_dir / DEFAULT_FUNDING_SUBDIR)
    )
    named = args.source_id or _config_str(config, "source_id")
    source_id = sanitise_source_id(named) if named else default_source_id()
    floor = args.floor_usd
    if floor is None:
        floor = _config_number(config, "funding_floor_usd")
    if floor is None:
        floor = DEFAULT_FLOOR_USD
    interval = args.interval_s
    if interval is None:
        configured = _config_number(config, "funding_interval_s")
        interval = int(configured) if configured is not None else DEFAULT_INTERVAL_S
    if interval <= 0:
        raise ValueError("the poll interval must be positive")
    return archive_dir, out_dir, source_id, float(floor), int(interval)


def _spot_pairs(args: argparse.Namespace, archive_dir: Path) -> tuple[str, ...]:
    if args.pairs:
        return tuple(dict.fromkeys(args.pairs))
    return tier1_pairs_from_heartbeat(archive_dir)


def _poll_with_retries(
    writer: JsonlWriter,
    spot_pairs: Sequence[str],
    *,
    slot: str,
    floor_usd: float,
    symbols: Sequence[str] | None,
    fetch: Fetch,
    sleep: Callable[[float], None],
) -> Matching | None:
    """Poll, retrying on the schedule in :data:`RETRY_DELAYS_S`. On final
    failure the slot is written as a gap marker and None is returned."""
    attempts = 0
    last_error = "unknown"
    for delay in (*RETRY_DELAYS_S, None):
        attempts += 1
        try:
            return poll_once(writer, spot_pairs, floor_usd=floor_usd, symbols=symbols, fetch=fetch)
        except PollError as exc:
            last_error = str(exc)
            print(f"poll for {slot} failed ({exc}); attempt {attempts}", file=sys.stderr, flush=True)
            if delay is not None:
                sleep(delay)
    writer.write(gap_line(slot=slot, reason=last_error, attempts=attempts, ts_recv=utc_now_iso()))
    return None


def run(args: argparse.Namespace, *, fetch: Fetch = fetch_json) -> int:
    archive_dir, out_dir, source_id, floor_usd, interval_s = resolve_storage(args)
    print(
        f"funding poller: archive {archive_dir}, output {out_dir}, source id {source_id!r}, "
        f"every {interval_s}s, floor {floor_usd:,.0f} quote/24h",
        file=sys.stderr,
        flush=True,
    )
    symbols = tuple(args.symbols) if args.symbols else None
    with (
        ArchiveLock(out_dir.resolve()),
        JsonlWriter(out_dir, prefix=FUNDING_PREFIX, source_id=source_id) as writer,
    ):
        spot_pairs = _spot_pairs(args, archive_dir)
        first = _poll_with_retries(
            writer,
            spot_pairs,
            slot=utc_now_iso(),
            floor_usd=floor_usd,
            symbols=symbols,
            fetch=fetch,
            sleep=time.sleep,
        )
        writer.write(
            session_line(
                "start",
                {
                    "endpoint": FUTURES_TICKERS_URL,
                    "interval_s": interval_s,
                    "floor_usd": floor_usd,
                    "spot_pairs": list(spot_pairs),
                    "spot_pairs_from": "--pairs" if args.pairs else "recorder heartbeat",
                    "symbols": list(symbols or ()),
                    "source_id": source_id,
                    **(first.summary() if first is not None else {"first_poll": "failed"}),
                },
                ts_recv=utc_now_iso(),
            )
        )
        if first is not None:
            print(json.dumps(first.summary(), indent=2), file=sys.stderr, flush=True)
            if args.backfill:
                with JsonlWriter(out_dir, prefix=HISTORY_PREFIX, source_id=source_id) as history:
                    written = backfill(history, first, fetch=fetch)
                print(f"backfilled {written} funding-rate rows", file=sys.stderr, flush=True)
        try:
            if not args.once:
                while True:
                    slot = next_slot(utc_now(), interval_s)
                    wait = (slot - utc_now()).total_seconds()
                    if wait > 0:
                        time.sleep(wait)
                    try:
                        spot_pairs = _spot_pairs(args, archive_dir)
                    except RuntimeError as exc:
                        print(f"{exc}; keeping the previous list", file=sys.stderr, flush=True)
                    _poll_with_retries(
                        writer,
                        spot_pairs,
                        slot=iso_z(slot),
                        floor_usd=floor_usd,
                        symbols=symbols,
                        fetch=fetch,
                        sleep=time.sleep,
                    )
        except KeyboardInterrupt:
            pass
        finally:
            writer.write(
                session_line(
                    "stop", {"lines_written": writer.lines_written}, ts_recv=utc_now_iso()
                )
            )
        print(f"{writer.lines_written} lines to {out_dir}", file=sys.stderr, flush=True)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="funding.py",
        description=(
            "Standalone Kraken Futures funding-rate and open-interest poller for the "
            "tier 1 spot pairs. Public data only; hourly; one file per day per source."
        ),
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        default=None,
        help="spot symbols to look up perpetuals for; default: the recorder's tier 1 heartbeat",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="futures symbols to record regardless of the pair match or the floor",
    )
    parser.add_argument(
        "--floor-usd",
        type=float,
        default=None,
        help=(
            f"24h quote volume a perpetual must clear to count as liquid. Overrides "
            f"recorder.funding_floor_usd; default {DEFAULT_FLOOR_USD:,.0f}"
        ),
    )
    parser.add_argument(
        "--interval-s",
        type=int,
        default=None,
        help=f"seconds between polls, aligned to midnight UTC. Default {DEFAULT_INTERVAL_S}",
    )
    parser.add_argument("--config", default=None, help="config file carrying a `recorder:` mapping")
    parser.add_argument(
        "--archive",
        default=None,
        help="the raw archive directory, where the recorder's heartbeat is read from",
    )
    parser.add_argument(
        "--out",
        default=None,
        help=f"output directory. Overrides recorder.funding_dir; default <archive>/{DEFAULT_FUNDING_SUBDIR}",
    )
    parser.add_argument("--source-id", default=None, help="goes into every filename")
    parser.add_argument("--once", action="store_true", help="poll once and exit")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="also fetch each matched symbol's published funding history, once, at start",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        return 0
    except ArchiveLockedError as exc:
        print(f"\nREFUSING TO START: {exc}\n", file=sys.stderr, flush=True)
        return 2
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"\nfunding poller: {exc}\n", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
