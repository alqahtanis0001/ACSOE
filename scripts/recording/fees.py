#!/usr/bin/env python
"""Standalone Kraken fee-tier and pair-rules poller.

This script imports **nothing** from ``src/acsoe/`` and nothing from the other
scripts either — the same rule as ``funding.py`` and ``record.py``, so it can run
from a copy with no project checkout. The helpers it shares with them (the config
reader, the source id, the lock, the line schema, the heartbeat reader) are carried
here as copies, and so are the two it shares with ``clients/kraken/rest.py``: the
``.env`` reader and the request signer. A test compares the signer with the
package's, so the two copies cannot drift apart silently.

## Why this exists

A replay of a recorded day needs two things the recorder never captured. **The fee
tier**: engine 10 prices every candidate with the account's maker and taker fee,
and with no fee on record it blocks every pair. **The pair rules**: engine 7 excludes
every pair it has no ``ordermin``, ``costmin`` and tick size for. The eleven days
recorded before this script cannot be replayed for exactly those two reasons.

## What it records, and from where

Once an hour, on the hour, two calls, each written **verbatim**:

* ``GET /0/public/AssetPairs`` — every pair's rules, public, no credentials. Also
  the name map: the recorder speaks v2 (``BTC/USD``) and the private endpoint speaks
  REST keys (``XXBTZUSD``), and ``wsname`` is how one is found from the other.
* ``POST /0/private/TradeVolume`` with ``pair=<the tier 1 pairs, as REST keys>`` and
  ``fee_schedule=true`` — the account's fee per pair, maker and taker, and the
  schedule. **Fees come back only when ``pair`` is sent**, which is why the pair
  list is resolved first. Signed; needs ``KRAKEN_API_KEY`` and ``KRAKEN_API_SECRET``.

Nothing is renamed or derived. A change to either endpoint's shape lands in the
archive rather than in a mapping that silently stopped matching.

## Credentials, and what never leaves this process

The key pair is read from ``.env`` — **only** those two names, and only from that
file, never from the process environment — on every poll, so a rotated key is
picked up without a restart. No key is not a crash: ``AssetPairs`` is still
recorded, and ``TradeVolume`` is written as a ``gap`` naming the absence.

The key, the secret, the signature and the nonce are never printed, logged or
written. Every message bound for stderr or a gap marker goes through
:func:`redact` as a second line of defence. The account's 30-day ``volume`` goes
into the archive under ``data/raw/fees/``, which is gitignored, and nowhere else:
the stderr summary names the keys that came back, never a value.

**The nonce counts microseconds**, the scale ``clients/kraken/rest.py`` uses. The
engine daemon and this poller share one key, and Kraken requires a key's nonce to
increase. A poller counting milliseconds would sit three orders of magnitude below
the daemon's, and every call would be refused as a stale nonce for ever after the
daemon's first run.

## Where the file goes

``<archive_dir>/fees/fees__<source_id>__<date>.jsonl`` by default —
``recorder.fees_dir`` or ``--out`` override it. A subdirectory of its own for the
reason ``funding.py`` gives: ``recording_report.py`` measures continuity by the
distance between lines in every ``*.jsonl`` in the archive directory, and an hourly
line there would cut an outage into hour-long pieces.

## Line schema

The raw archive's seven keys::

    v            int    always 1
    kind         str    "tick" | "gap" | "session"
    pair         None   both calls cover many pairs
    channel      str    "asset_pairs" | "trade_volume" | "_recorder" for a marker
    ts_exchange  None   neither endpoint carries a server time
    ts_recv      str    ISO-8601 UTC ending "Z", wall clock when the answer arrived
    payload      dict   {"endpoint", "response": <Kraken's envelope verbatim>} and,
                        for trade_volume, "request" {"pair", "fee_schedule"},
                        "pairs" {v2 symbol: REST key} and "unmatched" [v2 symbols]

A call that fails after its retries is a ``gap`` marker naming the call and the slot.

Usage::

    python scripts/recording/fees.py                  # poll hourly, forever
    python scripts/recording/fees.py --once           # one poll, then exit
    python scripts/recording/fees.py --pairs BTC/USD ETH/USD --once
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import hmac
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Self

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

SCHEMA_VERSION: Final = 1

REST_URL: Final = "https://api.kraken.com"
ASSET_PAIRS_PATH: Final = "/0/public/AssetPairs"
TRADE_VOLUME_PATH: Final = "/0/private/TradeVolume"

RECORDER_CHANNEL: Final = "_recorder"
ASSET_PAIRS_CHANNEL: Final = "asset_pairs"
TRADE_VOLUME_CHANNEL: Final = "trade_volume"
POLLER_NAME: Final = "fees"
FEES_PREFIX: Final = "fees"

LINE_KEYS: Final = frozenset(
    {"v", "kind", "pair", "channel", "ts_exchange", "ts_recv", "payload"}
)
LINE_KINDS: Final = frozenset({"tick", "gap", "session"})

#: Where the v2 socket and the REST ``wsname`` disagree on an asset's name. The
#: same two entries ``funding.py`` carries, and every poll writes down which pairs
#: matched nothing, so a third one cannot go unnoticed.
BASE_ALIASES: Final = {"BTC": "XBT", "DOGE": "XDG"}

CREDENTIAL_NAMES: Final = ("KRAKEN_API_KEY", "KRAKEN_API_SECRET")

DEFAULT_INTERVAL_S: Final = 3600
DEFAULT_FEES_SUBDIR: Final = "fees"
DEFAULT_ARCHIVE_DIR: Final = Path("data") / "raw"

HTTP_TIMEOUT_S: Final = 20.0
#: Attempts per call per slot before it is written down as a gap. A little over a
#: minute in all, well inside the hour — the same schedule as ``funding.py``.
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

LOCK_FILENAME: Final = ".fees.lock"
HEARTBEAT_GLOB: Final = "heartbeat__*.ndjson"

#: What :func:`redact` puts where a credential was.
REDACTED: Final = "[REDACTED]"


class SchemaError(ValueError):
    """A line failed validation on write. Never suppressed."""


class ArchiveLockedError(RuntimeError):
    """Another fees poller already holds this output directory."""


class PollError(RuntimeError):
    """Kraken could not be read, or answered with an error or a non-envelope."""


# --------------------------------------------------------------------------- #
# Configuration, source id, lock — copies of the recorder's, on purpose
# --------------------------------------------------------------------------- #


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _config_search_paths(explicit: Path | None) -> list[Path]:
    if explicit is not None:
        return [explicit]
    paths: list[Path] = []
    for base in (Path.cwd(), _repo_root()):
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
                f"another fees poller is already writing to {self._directory}.\n"
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
# Credentials — a copy of the package's `.env` reader, narrowed to two names
# --------------------------------------------------------------------------- #


class Credentials:
    """The key pair, carried without ever being renderable. Not a ``@dataclass``.

    ``__repr__`` and ``__str__`` both return a constant: the commonest way a key
    reaches a log is an object holding it being formatted by something that meant
    no harm. Same reasoning as the package's own ``Credentials``.
    """

    __slots__ = ("key", "secret")

    def __init__(self, *, key: str, secret: str) -> None:
        self.key = key
        self.secret = secret

    def __repr__(self) -> str:
        return "Credentials(<redacted>)"

    __str__ = __repr__


def find_env_file(explicit: Path | None) -> Path | None:
    """``--env-file`` if given, else ``.env`` in the working directory, then at the
    repository root. None when there is none — a normal state, not an error."""
    if explicit is not None:
        return explicit
    for candidate in (Path.cwd() / ".env", _repo_root() / ".env"):
        if candidate.is_file():
            return candidate
    return None


def parse_env_credentials(text: str) -> Credentials | None:
    """The two credential names from ``.env`` text, or None if either is missing.

    The parsing rules are ``platform/config.py``'s ``parse_dotenv`` — ``KEY=VALUE``,
    ``#`` comments, an optional ``export``, optional matching quotes, no
    interpolation — and **every other name is ignored**, so nothing else in the file
    is ever held in this process.
    """
    found: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        if name not in CREDENTIAL_NAMES:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        found[name] = value
    key = found.get(CREDENTIAL_NAMES[0], "").strip()
    secret = found.get(CREDENTIAL_NAMES[1], "").strip()
    if not key or not secret:
        return None
    return Credentials(key=key, secret=secret)


def read_credentials(env_file: Path | None) -> Credentials | None:
    """Read afresh on every call, so a rotated key needs no restart."""
    if env_file is None or not env_file.is_file():
        return None
    try:
        return parse_env_credentials(env_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None


def redact(text: str, credentials: Credentials | None) -> str:
    """``text`` with either credential value replaced. The second line of defence:
    no message built here includes one, and this makes sure none escapes if a
    library's message ever does."""
    if credentials is None:
        return text
    for value in (credentials.key, credentials.secret):
        if value:
            text = text.replace(value, REDACTED)
    return text


def sign_request(*, path: str, nonce: int, form: Mapping[str, Any], secret: str) -> str:
    """Kraken's private-endpoint signature — a copy of ``clients/kraken/rest.py``'s.

    HMAC-SHA512 over the path and the SHA-256 of the nonce followed by the
    form-encoded body, keyed by the base64-decoded secret, returned base64. The
    scheme is the one Kraken's authentication guide gives. ``tests/scripts`` holds
    this copy equal to the package's on the same inputs.
    """
    try:
        decoded = base64.b64decode(secret, validate=True)
    except (ValueError, TypeError) as exc:
        raise PollError(
            "the API secret is not valid base64. The value itself is never rendered."
        ) from exc
    post = urllib.parse.urlencode({"nonce": nonce, **form})
    digest = hashlib.sha256(f"{nonce}{post}".encode()).digest()
    signature = hmac.new(decoded, path.encode() + digest, hashlib.sha512)
    return base64.b64encode(signature.digest()).decode()


class Nonce:
    """Strictly increasing, in **microseconds** — the package client's scale.

    One key, two processes: the engine daemon and this poller. Kraken refuses a
    nonce that does not exceed the key's last, so both have to count in the same
    unit or the lower one is refused for ever.
    """

    __slots__ = ("_clock", "_last")

    def __init__(self, clock: Callable[[], int] | None = None) -> None:
        self._clock = clock or (lambda: time.time_ns() // 1000)
        self._last = 0

    def next(self) -> int:
        self._last = max(self._clock(), self._last + 1)
        return self._last


# --------------------------------------------------------------------------- #
# Time, names, lines — copies of `funding.py`'s
# --------------------------------------------------------------------------- #


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def utc_now_iso() -> str:
    return iso_z(utc_now())


def archive_filename(prefix: str, source_id: str, date: str) -> str:
    return f"{prefix}{NAME_SEPARATOR}{source_id}{NAME_SEPARATOR}{date}.jsonl"


def next_slot(now: datetime, interval_s: int) -> datetime:
    """The first interval boundary strictly after ``now``, counted from midnight UTC,
    so an hourly poller polls on the hour."""
    if interval_s <= 0:
        raise ValueError("interval_s must be positive")
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = (now - midnight).total_seconds()
    slots = int(elapsed // interval_s) + 1
    return midnight + timedelta(seconds=slots * interval_s)


def build_line(
    *,
    kind: str,
    channel: str,
    ts_recv: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "v": SCHEMA_VERSION,
        "kind": kind,
        "pair": None,
        "channel": channel,
        "ts_exchange": None,
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
        date = str(line["ts_recv"])[:10]
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
# Which pairs — the recorder's heartbeat, never a written list
# --------------------------------------------------------------------------- #


def tier1_pairs_from_heartbeat(archive_dir: Path) -> tuple[str, ...]:
    """Tier 1 as the recorder last reported it — ``funding.py``'s reader, copied.

    The newest heartbeat file by modification time, its last ``tier1`` beat, read on
    every poll so a disk-guard degrade is followed. Raises rather than returning an
    empty tuple: "no tier 1" and "could not find the recorder" are different facts.
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


def _wsname_candidates(v2_symbol: str) -> tuple[str, ...]:
    """The ``wsname`` spellings a v2 symbol may carry in ``AssetPairs``."""
    if "/" not in v2_symbol:
        return ()
    base, quote = v2_symbol.split("/", 1)
    candidates = [f"{base}/{quote}"]
    aliased = f"{BASE_ALIASES.get(base, base)}/{BASE_ALIASES.get(quote, quote)}"
    if aliased not in candidates:
        candidates.append(aliased)
    return tuple(candidates)


def rest_names(
    spot_pairs: Sequence[str], asset_pairs_result: Mapping[str, Any]
) -> tuple[dict[str, str], list[str]]:
    """``{v2 symbol: AssetPairs result key}`` and the v2 symbols that matched none."""
    by_wsname: dict[str, str] = {}
    for key, entry in asset_pairs_result.items():
        if isinstance(entry, Mapping):
            wsname = entry.get("wsname")
            if isinstance(wsname, str):
                by_wsname.setdefault(wsname, str(key))
    mapped: dict[str, str] = {}
    unmatched: list[str] = []
    for spot in spot_pairs:
        for candidate in _wsname_candidates(spot):
            if candidate in by_wsname:
                mapped[spot] = by_wsname[candidate]
                break
        else:
            unmatched.append(spot)
    return mapped, unmatched


# --------------------------------------------------------------------------- #
# Kraken
# --------------------------------------------------------------------------- #


#: ``(method, url, headers, body) -> response body``. Injected in the tests; the
#: default is ``urllib``, so the script needs nothing beyond the standard library.
Transport = Callable[[str, str, dict[str, str], bytes | None], bytes]


def urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None
) -> bytes:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            data: bytes = response.read()
            return data
    except urllib.error.HTTPError as exc:
        # Kraken answers application errors with 200 and an envelope; a real HTTP
        # error carries nothing worth keeping, and its headers are never rendered.
        raise PollError(f"HTTP {exc.code} from {urllib.parse.urlsplit(url).path}") from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise PollError(f"{type(exc).__name__}: {exc}") from None


def parse_envelope(body: bytes) -> dict[str, Any]:
    """Kraken's ``{"error": [...], "result": ...}``, or :class:`PollError`.

    A populated ``error`` array is a failure even under HTTP 200, which is how
    Kraken reports every application error.
    """
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise PollError(f"the answer is not JSON: {exc}") from None
    if not isinstance(parsed, dict) or "error" not in parsed:
        raise PollError("the answer is not a Kraken envelope")
    errors = parsed.get("error")
    if not isinstance(errors, list):
        raise PollError("the envelope's error field is not a list")
    if errors:
        raise PollError("Kraken refused: " + "; ".join(str(error) for error in errors))
    if not isinstance(parsed.get("result"), dict):
        raise PollError("the envelope carries no result object")
    return parsed


def fetch_asset_pairs(transport: Transport) -> dict[str, Any]:
    body = transport(
        "GET",
        REST_URL + ASSET_PAIRS_PATH,
        {"User-Agent": "acsoe-fees-poller/1", "Accept": "application/json"},
        None,
    )
    return parse_envelope(body)


def trade_volume_form(rest_keys: Sequence[str]) -> dict[str, str]:
    """The request form, without the nonce. ``fee_schedule`` as the string Kraken's
    form encoding carries; whether it is honoured is read off the answer, never
    assumed — see the session marker's ``schedules_returned``."""
    return {"pair": ",".join(rest_keys), "fee_schedule": "true"}


def fetch_trade_volume(
    transport: Transport,
    credentials: Credentials,
    nonce: Nonce,
    rest_keys: Sequence[str],
) -> dict[str, Any]:
    form = trade_volume_form(rest_keys)
    value = nonce.next()
    headers = {
        "User-Agent": "acsoe-fees-poller/1",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "API-Key": credentials.key,
        "API-Sign": sign_request(
            path=TRADE_VOLUME_PATH, nonce=value, form=form, secret=credentials.secret
        ),
    }
    body = urllib.parse.urlencode({"nonce": value, **form}).encode()
    return parse_envelope(transport("POST", REST_URL + TRADE_VOLUME_PATH, headers, body))


# --------------------------------------------------------------------------- #
# One poll
# --------------------------------------------------------------------------- #


def gap_line(*, call: str, slot: str, reason: str, attempts: int, ts_recv: str) -> dict[str, Any]:
    return build_line(
        kind="gap",
        channel=RECORDER_CHANNEL,
        ts_recv=ts_recv,
        payload={
            "poller": POLLER_NAME,
            "call": call,
            "slot": slot,
            "reason": reason,
            "attempts": attempts,
        },
    )


def session_line(event: str, extra: dict[str, Any], *, ts_recv: str) -> dict[str, Any]:
    return build_line(
        kind="session",
        channel=RECORDER_CHANNEL,
        ts_recv=ts_recv,
        payload={"event": event, "poller": POLLER_NAME, **extra},
    )


class Poller:
    """One slot at a time. Holds the last good name map, and nothing else.

    Not a ``@dataclass`` — this file is loaded by path in its tests.

    The name map is kept across slots because it is a *naming* fact that changes
    only on a listing: if ``AssetPairs`` fails one hour, the previous hour's map
    still names ``BTC/USD`` correctly, and losing that hour's fee to it would lose
    a value for the sake of a spelling. It is never used to stand in for a fee or a
    rule — those are recorded as they came back, or as a gap.
    """

    __slots__ = ("_env_file", "_last_map", "_nonce", "_now_iso", "_sleep", "_transport", "writer")

    def __init__(
        self,
        writer: JsonlWriter,
        *,
        env_file: Path | None,
        transport: Transport = urllib_transport,
        nonce: Nonce | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now_iso: Callable[[], str] = utc_now_iso,
    ) -> None:
        self.writer = writer
        self._env_file = env_file
        self._transport = transport
        self._nonce = nonce or Nonce()
        self._sleep = sleep
        self._now_iso = now_iso
        self._last_map: tuple[dict[str, str], list[str]] | None = None

    def _retrying(
        self,
        call: str,
        slot: str,
        attempt: Callable[[], dict[str, Any]],
        credentials: Credentials | None,
    ) -> dict[str, Any] | None:
        attempts = 0
        last_error = "unknown"
        for delay in (*RETRY_DELAYS_S, None):
            attempts += 1
            try:
                return attempt()
            except PollError as exc:
                last_error = redact(str(exc), credentials)
                _say(f"{call} for {slot} failed ({last_error}); attempt {attempts}", credentials)
                if delay is not None:
                    self._sleep(delay)
        self.writer.write(
            gap_line(
                call=call, slot=slot, reason=last_error, attempts=attempts, ts_recv=self._now_iso()
            )
        )
        return None

    def poll(self, spot_pairs: Sequence[str], *, slot: str) -> dict[str, Any]:
        """Both calls for one slot. Returns a summary that carries no value."""
        summary: dict[str, Any] = {"slot": slot, "spot_pairs": len(spot_pairs)}

        envelope = self._retrying(
            ASSET_PAIRS_CHANNEL, slot, lambda: fetch_asset_pairs(self._transport), None
        )
        if envelope is not None:
            self.writer.write(
                build_line(
                    kind="tick",
                    channel=ASSET_PAIRS_CHANNEL,
                    ts_recv=self._now_iso(),
                    payload={"endpoint": ASSET_PAIRS_PATH, "response": envelope},
                )
            )
            self._last_map = rest_names(spot_pairs, envelope["result"])
            summary["asset_pairs"] = len(envelope["result"])
        else:
            summary["asset_pairs"] = "failed"

        if self._last_map is None:
            self.writer.write(
                gap_line(
                    call=TRADE_VOLUME_CHANNEL,
                    slot=slot,
                    reason="no AssetPairs answer yet, so no REST names to ask for fees by",
                    attempts=0,
                    ts_recv=self._now_iso(),
                )
            )
            summary["trade_volume"] = "no name map"
            return summary

        mapped, unmatched = self._last_map
        summary["unmatched"] = list(unmatched)
        credentials = read_credentials(self._env_file)
        if credentials is None:
            self.writer.write(
                gap_line(
                    call=TRADE_VOLUME_CHANNEL,
                    slot=slot,
                    reason=(
                        "credentials not set: KRAKEN_API_KEY and KRAKEN_API_SECRET are "
                        "read from .env only"
                    ),
                    attempts=0,
                    ts_recv=self._now_iso(),
                )
            )
            summary["trade_volume"] = "no credentials"
            return summary
        if not mapped:
            self.writer.write(
                gap_line(
                    call=TRADE_VOLUME_CHANNEL,
                    slot=slot,
                    reason="no tier 1 pair has a REST name, so there is nothing to ask for",
                    attempts=0,
                    ts_recv=self._now_iso(),
                )
            )
            summary["trade_volume"] = "no pairs"
            return summary

        rest_keys = [mapped[spot] for spot in spot_pairs if spot in mapped]
        answer = self._retrying(
            TRADE_VOLUME_CHANNEL,
            slot,
            lambda: fetch_trade_volume(self._transport, credentials, self._nonce, rest_keys),
            credentials,
        )
        if answer is None:
            summary["trade_volume"] = "failed"
            return summary
        form = trade_volume_form(rest_keys)
        self.writer.write(
            build_line(
                kind="tick",
                channel=TRADE_VOLUME_CHANNEL,
                ts_recv=self._now_iso(),
                payload={
                    "endpoint": TRADE_VOLUME_PATH,
                    "request": {"pair": rest_keys, "fee_schedule": form["fee_schedule"]},
                    "pairs": dict(mapped),
                    "unmatched": list(unmatched),
                    "response": answer,
                },
            )
        )
        result = answer["result"]
        fees = result.get("fees")
        summary["trade_volume"] = {
            # Key names only. `volume` and `inputs` are the account's and go into the
            # archive and nowhere else.
            "result_keys": sorted(result),
            "fees_pairs": sorted(fees) if isinstance(fees, dict) else None,
            "schedules_returned": isinstance(result.get("schedules"), list),
        }
        return summary


def _say(message: str, credentials: Credentials | None = None) -> None:
    print(redact(message, credentials), file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #


def resolve_storage(args: argparse.Namespace) -> tuple[Path, Path, str, int]:
    """``(archive_dir, out_dir, source_id, interval_s)`` — flag, then config, then
    default, per value."""
    config = load_recorder_config(Path(args.config) if args.config else None)
    archive_dir = Path(args.archive or _config_str(config, "archive_dir") or DEFAULT_ARCHIVE_DIR)
    out_dir = Path(
        args.out or _config_str(config, "fees_dir") or (archive_dir / DEFAULT_FEES_SUBDIR)
    )
    named = args.source_id or _config_str(config, "source_id")
    source_id = sanitise_source_id(named) if named else default_source_id()
    interval = args.interval_s
    if interval is None:
        configured = _config_number(config, "fees_interval_s")
        interval = int(configured) if configured is not None else DEFAULT_INTERVAL_S
    if interval <= 0:
        raise ValueError("the poll interval must be positive")
    return archive_dir, out_dir, source_id, int(interval)


def _spot_pairs(args: argparse.Namespace, archive_dir: Path) -> tuple[str, ...]:
    if args.pairs:
        return tuple(dict.fromkeys(args.pairs))
    return tier1_pairs_from_heartbeat(archive_dir)


def run(
    args: argparse.Namespace,
    *,
    transport: Transport = urllib_transport,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    archive_dir, out_dir, source_id, interval_s = resolve_storage(args)
    env_file = find_env_file(Path(args.env_file) if args.env_file else None)
    _say(
        f"fees poller: archive {archive_dir}, output {out_dir}, source id {source_id!r}, "
        f"every {interval_s}s, credentials file "
        f"{env_file.as_posix() if env_file is not None else 'none found'}"
    )
    with (
        ArchiveLock(out_dir.resolve()),
        JsonlWriter(out_dir, prefix=FEES_PREFIX, source_id=source_id) as writer,
    ):
        poller = Poller(writer, env_file=env_file, transport=transport, sleep=sleep)
        spot_pairs = _spot_pairs(args, archive_dir)
        first = poller.poll(spot_pairs, slot=utc_now_iso())
        writer.write(
            session_line(
                "start",
                {
                    "interval_s": interval_s,
                    "spot_pairs": list(spot_pairs),
                    "spot_pairs_from": "--pairs" if args.pairs else "recorder heartbeat",
                    "source_id": source_id,
                    "first_poll": first,
                },
                ts_recv=utc_now_iso(),
            )
        )
        _say(json.dumps(first, indent=2))
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
                        _say(f"{exc}; keeping the previous list")
                    poller.poll(spot_pairs, slot=iso_z(slot))
        except KeyboardInterrupt:
            pass
        finally:
            writer.write(
                session_line("stop", {"lines_written": writer.lines_written}, ts_recv=utc_now_iso())
            )
        _say(f"{writer.lines_written} lines to {out_dir}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fees.py",
        description=(
            "Standalone Kraken fee-tier and pair-rules poller for the tier 1 pairs: "
            "TradeVolume (signed) and AssetPairs, verbatim, hourly, one file per day."
        ),
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        default=None,
        help="v2 spot symbols to ask fees for; default: the recorder's tier 1 heartbeat",
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
        help=f"output directory. Overrides recorder.fees_dir; default <archive>/{DEFAULT_FEES_SUBDIR}",
    )
    parser.add_argument("--source-id", default=None, help="goes into every filename")
    parser.add_argument(
        "--env-file",
        default=None,
        help=(
            "the .env holding KRAKEN_API_KEY and KRAKEN_API_SECRET. Default: .env in the "
            "working directory, then at the repository root"
        ),
    )
    parser.add_argument("--once", action="store_true", help="poll once and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        return 0
    except ArchiveLockedError as exc:
        _say(f"\nREFUSING TO START: {exc}\n")
        return 2
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        _say(f"\nfees poller: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
