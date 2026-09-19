#!/usr/bin/env python
"""Keep a recorder alive, and its pollers, and show one honest block of text while it does.

**Nothing ever runs `record.py` directly.** Every `.bat`, every startup shortcut,
every ssh session runs this. The recorder has died unnoticed twice — once to an
`Errno 28` and once to a stop nobody noticed for about fifteen hours — and in both
cases the hours lost are gone for good: order book and spread cannot be
backfilled, Kraken's free archives carry OHLCV and no bid, ask, spread or depth,
and the market does not come back. A process that restarts itself is worth more
than any amount of monitoring that tells you afterwards.

This file imports nothing from `acsoe` and nothing from its own directory. It is
half of a node package — the other half is `record.py` — and both have to survive
being copied to a bare machine with no checkout.

## What it does when the recorder exits

It restarts it, after a backoff that grows while failures keep happening and
resets once a run has lasted long enough to count as healthy. A flat one-second
retry against a permanent fault is a log file growing at a megabyte a minute; a
backoff that never resets turns a machine that drops its network once an hour into
one waiting ten minutes to reconnect by the evening, and those minutes are
order-book data nothing can recover.

**Exit code 2 is not a crash and is not retried the same way.** That is the
recorder refusing to start because another live recorder holds the archive lock,
and the correct response is to wait quietly and look again, not to hammer a
directory somebody else is correctly writing to. It is reported as `waiting`
rather than as a restart, and it does not count toward the backoff.

## The pollers

The same supervision, for every script listed under ``recorder.pollers`` in the
config — the funding poller is the first. **This exists because the funding poller
was started by hand, and when the machine went down on 2026-09-15 nothing brought
it back**: four days of open interest, which the venue publishes as no series, are
gone. Each listed poller gets the recorder's backoff, the recorder's healthy-run
reset and the recorder's exit-code-2 wait (every script here uses 2 for "another
live process holds my lock"). Its output goes to a log of its own,
``logs/<name>__<source>__<date>.log``, so the recorder's stays readable.

The list is **re-read while the supervisor runs**, every ``--reload-s``. A newly
listed poller starts on the next pass and a delisted one is stopped, **without
restarting the supervisor or the recorder** — the recorder is the one process whose
interrupted minutes cannot be recovered, so adding a poller must not cost any. A
config that cannot be read — missing, half-saved, a YAML error, a malformed list —
changes nothing: the running set is kept and the failure is logged, because a
reader that treated "unreadable" as "empty" would stop every poller on an editor's
save. A change to *this file* still needs a restart; a change to the list does not.

A poller is named by bare filename only and is looked for beside this file, then
one directory up — the same rule as the recorder, for the same reason: a script
found somewhere unexpected is a script writing somewhere unexpected.

    recorder:
      pollers:
        - script: funding.py
        - script: fees.py
          args: ["--interval-s", "3600"]

## What it shows

One block, refreshed in place, and that is the entire interface of a node:

    RECORDING — vps-fra-1
    started    2026-09-11T17:40:02Z
    uptime     3h 12m
    today      41283 MB
    last write 0s ago
    restarts   2
    funding    running · restarts 0

Six lines for the recorder and one per listed poller, so a node with no pollers
shows the six it always has. No buttons and no commands, on purpose. A node is a
machine that records; every decision about it is taken on the master, and an
interface that invited a decision here would be an interface that lets somebody
stop a recorder from the wrong keyboard.

The recorder's own output does not go to this terminal — it would overwrite the
block on every frame. It goes to the log, with every launch, exit code and
restart beside it.

Usage::

    python supervise.py                                  # a node package
    python scripts/recording/supervise.py                # in the repository
    python supervise.py --config recorder.yaml -- --tier1-count 4
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

#: Exit code `record.py` uses for "another recorder holds this archive". Waiting
#: is the correct response and it is not a failure, so it is spelled out rather
#: than left as a magic 2 in a comparison. Every poller uses it for its own lock.
EXIT_ARCHIVE_LOCKED: Final = 2

DEFAULT_BACKOFF_S: Final = 5.0
DEFAULT_MAX_BACKOFF_S: Final = 300.0
BACKOFF_FACTOR: Final = 2.0

#: A run that lasted this long is treated as healthy, and the backoff resets when
#: it ends. Without it the backoff compounds across independent, individually
#: successful days and a machine that drops its network once an hour ends the day
#: waiting five minutes to reconnect from a fault it recovers from instantly.
HEALTHY_RUN_S: Final = 120.0

#: How long to wait before looking again when the archive is locked by somebody
#: else. Short, because the other recorder stopping is the expected outcome.
LOCKED_RETRY_S: Final = 30.0

DEFAULT_REFRESH_S: Final = 1.0

#: How often the pollers list is re-read. A new poller waits at most this long to
#: start; the read is one small YAML file, so it costs nothing worth measuring.
DEFAULT_RELOAD_S: Final = 30.0

DEFAULT_ARCHIVE_DIR: Final = Path("data") / "raw"
DEFAULT_LOG_DIR: Final = Path("logs")

CONFIG_CANDIDATES: Final = (
    Path("config") / "recorder.yaml",
    Path("recorder.yaml"),
    Path("config") / "default.yaml",
)
CONFIG_SECTION: Final = "recorder"
POLLERS_KEY: Final = "pollers"

#: The recorder's name in the event log. Its events keep the names they have had
#: since Phase 0 — ``recorder_launching``, ``recorder_exited`` — and a poller's are
#: ``<name>_launching``, ``<name>_exited``.
RECORDER_NAME: Final = "recorder"

#: Scripts that may not be listed as a poller. Listing the recorder would start a
#: second one against the same archive; listing this file would supervise itself.
NOT_POLLERS: Final = frozenset({"record.py", "supervise.py"})

LOCK_FILENAME: Final = ".recorder.lock"
HEARTBEAT_GLOB: Final = "heartbeat__*.ndjson"

#: How much of the end of a file to read when looking for its last line.
TAIL_BYTES: Final = 256 * 1024

STATUS_LINES: Final = 6


# --------------------------------------------------------------------------- #
# Config — the same reader `record.py` carries, and duplicated for the same
# reason: these two files are a node package and neither may import the other.
# --------------------------------------------------------------------------- #


def _config_search_paths(explicit: Path | None) -> list[Path]:
    if explicit is not None:
        return [explicit]
    here = Path(__file__).resolve().parent
    return [
        base / candidate
        for base in (Path.cwd(), here, here.parent, here.parent.parent)
        for candidate in CONFIG_CANDIDATES
    ]


def locate_recorder_config(explicit: Path | None = None) -> tuple[dict[str, Any], Path | None]:
    """The ``recorder:`` mapping and the file it came from, or ``({}, None)``.

    The path is returned so the pollers list can be re-read from the same file for
    the life of the process, rather than searched for again — a search that could
    land on a different file halfway through a run.
    """
    if explicit is not None and not explicit.is_file():
        raise FileNotFoundError(f"--config {explicit} does not exist")
    try:
        import yaml  # optional; absent on a bare server
    except ImportError:
        if explicit is not None:
            raise
        return {}, None
    for path in _config_search_paths(explicit):
        if not path.is_file():
            continue
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get(CONFIG_SECTION), dict):
            return dict(loaded[CONFIG_SECTION]), path
    return {}, None


def load_recorder_config(explicit: Path | None = None) -> dict[str, Any]:
    """The ``recorder:`` mapping, or ``{}``."""
    return locate_recorder_config(explicit)[0]


def reread_section(path: Path) -> dict[str, Any] | None:
    """The ``recorder:`` mapping in ``path``, or None when it cannot be read as one.

    Tolerant where :func:`locate_recorder_config` is strict, on purpose. At startup
    a broken config is a mistake to stop on; mid-run it is most often an editor
    halfway through a save, and the answer to that is to keep what is running and
    look again, never to act on a file nobody finished writing.
    """
    try:
        import yaml
    except ImportError:
        return None
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    if isinstance(loaded, dict) and isinstance(loaded.get(CONFIG_SECTION), dict):
        return dict(loaded[CONFIG_SECTION])
    return None


def config_str(config: dict[str, Any], key: str) -> str | None:
    value = config.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def find_recorder(explicit: str | None) -> Path:
    """Where `record.py` is.

    Beside this file in a node package, one directory up in the repository. Named
    rather than searched beyond those two, because a recorder found somewhere
    unexpected is a recorder writing somewhere unexpected.
    """
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise FileNotFoundError(f"--recorder {path} does not exist")
        return path
    here = Path(__file__).resolve().parent
    for candidate in (here / "record.py", here.parent / "record.py"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "record.py was not found beside supervise.py or one directory up. "
        "Pass --recorder with its path."
    )


def default_poller_dirs() -> tuple[Path, ...]:
    """Beside this file, then one directory up — the recorder's own rule."""
    here = Path(__file__).resolve().parent
    return (here, here.parent)


class PollerSpec:
    """One ``recorder.pollers`` entry. Not a ``@dataclass`` — see :class:`Screen`."""

    __slots__ = ("args", "name", "script")

    def __init__(self, *, script: str, args: tuple[str, ...]) -> None:
        self.script = script
        self.args = args
        #: The script's stem. Unique within the list; it names the log file and
        #: the events, so two entries sharing one would share both.
        self.name = Path(script).stem

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PollerSpec):
            return NotImplemented
        return (self.script, self.args) == (other.script, other.args)

    def __hash__(self) -> int:
        return hash((self.script, self.args))

    def __repr__(self) -> str:
        return f"PollerSpec(script={self.script!r}, args={self.args!r})"


def parse_pollers(section: dict[str, Any]) -> tuple[dict[str, PollerSpec] | None, str | None]:
    """The listed pollers by name, or ``(None, problem)`` when the list is unusable.

    **All or nothing.** One bad entry makes the whole list unusable, and the caller
    keeps the set it is already running. Applying the valid entries and dropping the
    bad one would *stop* whatever the bad entry used to be — a typo in one line
    silently stopping a poller that was recording is exactly the failure this file
    exists to prevent.

    An absent key is an empty list, not a problem: it is what a node package with no
    pollers has.
    """
    raw = section.get(POLLERS_KEY)
    if raw is None:
        return {}, None
    if not isinstance(raw, list):
        return None, f"recorder.{POLLERS_KEY} is not a list"
    specs: dict[str, PollerSpec] = {}
    for index, entry in enumerate(raw):
        where = f"recorder.{POLLERS_KEY}[{index}]"
        if not isinstance(entry, dict):
            return None, f"{where} is not a mapping with a `script` key"
        unknown = set(entry) - {"script", "args"}
        if unknown:
            return None, f"{where} has unknown keys {sorted(unknown)}"
        script = entry.get("script")
        if not isinstance(script, str) or not script.strip():
            return None, f"{where}.script is missing"
        script = script.strip()
        if (
            Path(script).name != script
            or "/" in script
            or "\\" in script
            or script in {".", ".."}
            or not script.endswith(".py")
        ):
            return None, f"{where}.script must be a bare .py filename, not {script!r}"
        if script in NOT_POLLERS:
            return None, f"{where}.script {script!r} cannot be a poller"
        args = entry.get("args", [])
        if args is None:
            args = []
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            return None, f"{where}.args must be a list of strings"
        spec = PollerSpec(script=script, args=tuple(args))
        if spec.name in specs or spec.name == RECORDER_NAME:
            return None, f"{where}: the name {spec.name!r} is already taken"
        specs[spec.name] = spec
    return specs, None


def resolve_script(script: str, search: Sequence[Path]) -> Path:
    """The first ``search`` directory holding ``script``. Raises FileNotFoundError."""
    for directory in search:
        candidate = directory / script
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"{script} was not found in {', '.join(path.as_posix() for path in search)}"
    )


# --------------------------------------------------------------------------- #
# Reading the archive, for the status block only
# --------------------------------------------------------------------------- #


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def last_line(path: Path) -> bytes | None:
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


def last_write_age_s(directory: Path) -> float | None:
    """Seconds since the newest line in the newest archive file, or None.

    Read from the line's own timestamp rather than from the file's mtime, because
    mtime moves when a file is copied and this number is the one an operator uses
    to decide whether anything is being recorded at all.
    """
    files = [path for path in directory.glob("*.jsonl") if path.is_file()]
    if not files:
        return None
    newest = max(files, key=lambda path: path.stat().st_mtime)
    raw = last_line(newest)
    if raw is None:
        return None
    try:
        line = json.loads(raw)
    except ValueError:
        # A partial final line: the recorder is mid-write, which is the healthiest
        # possible answer to "when did it last write".
        return 0.0
    if not isinstance(line, dict):
        return None
    for key in ("ts_recv", "ts", "minute"):
        value = line.get(key)
        if isinstance(value, str) and value:
            try:
                moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            return max(0.0, (utc_now() - moment).total_seconds())
    return None


def today_bytes(directory: Path) -> int:
    """Bytes in files carrying today's UTC date in their name.

    By name and not by mtime: a file moved in from elsewhere has a fresh mtime and
    is not today's recording, and counting it would report a machine as recording
    when it is only holding somebody else's data.
    """
    today = utc_now().strftime("%Y-%m-%d")
    total = 0
    for path in directory.glob("*.jsonl"):
        if today in path.name and path.is_file():
            total += path.stat().st_size
    return total


# --------------------------------------------------------------------------- #
# The status block
# --------------------------------------------------------------------------- #


def enable_ansi() -> bool:
    """Turn on virtual-terminal processing so the block can redraw in place.

    Returns whether it worked. When it does not — a pipe, a file, an old console —
    the block is printed afresh each time instead of being redrawn, which is
    uglier and still correct. A status display that garbles the terminal is worse
    than one that scrolls.
    """
    if not sys.stdout.isatty():
        return False
    if sys.platform != "win32":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError):  # pragma: no cover - not Windows, or no console
        return False


def human_uptime(seconds: float) -> str:
    hours, rest = divmod(int(max(0.0, seconds)), 3600)
    minutes = rest // 60
    return f"{hours}h {minutes:02d}m"


def status_block(
    *,
    source_id: str,
    started: datetime,
    now: datetime,
    today_mb: float,
    last_write: float | None,
    restarts: int,
    state: str,
    pollers: Sequence[tuple[str, str]] = (),
    config_problem: str | None = None,
) -> str:
    """The recorder's six lines, then one per poller. The whole interface of a node."""
    age = f"{last_write:.0f}s ago" if last_write is not None else "never"
    lines = [
        f"RECORDING — {source_id}",
        f"started    {iso(started)}",
        f"uptime     {human_uptime((now - started).total_seconds())}",
        f"today      {today_mb:.0f} MB",
        f"last write {age}",
        f"restarts   {restarts}",
    ]
    if state != "recording":
        # A seventh line only when there is something the six cannot say. The
        # block stays six lines in the normal case, which is what makes a change
        # in it visible at a glance.
        lines.append(f"state      {state}")
    for name, poller_state in pollers:
        lines.append(f"{name:<10} {poller_state}")
    if config_problem is not None:
        lines.append(f"pollers    list not applied: {config_problem}")
    return "\n".join(lines)


class Screen:
    """Redraws the block in place, or reprints it. Not a ``@dataclass``.

    ``scripts/`` is not a package and these files are loaded by path in the tests,
    which leaves them absent from ``sys.modules`` where ``dataclasses`` looks its
    own module up; the decorator then raises at import and the failure lands in a
    fixture rather than in a test. Same note as ``PairStat`` in ``record.py``.
    """

    __slots__ = ("_ansi", "_drawn", "_stream")

    def __init__(self, stream: Any = None, *, ansi: bool | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._ansi = enable_ansi() if ansi is None else ansi
        self._drawn = 0

    def draw(self, block: str) -> None:
        lines = block.split("\n")
        if self._ansi and self._drawn:
            self._stream.write(f"\x1b[{self._drawn}A")
            # The block can shrink by a line — a poller delisted — and the old last
            # line would otherwise stay on screen below the new block.
            if len(lines) < self._drawn:
                self._stream.write("\x1b[J")
        for line in lines:
            # Clear to end of line, so a shorter line does not leave the tail of a
            # longer one behind it — which is how a stale number survives a redraw.
            self._stream.write(line + ("\x1b[K" if self._ansi else "") + "\n")
        if not self._ansi:
            self._stream.write("\n")
        self._stream.flush()
        self._drawn = len(lines)


# --------------------------------------------------------------------------- #
# The log
# --------------------------------------------------------------------------- #


class Log:
    """Every launch, exit code and restart, and the recorder's own output.

    One file per UTC day, appended, never truncated — the same rule the archive
    follows, for the same reason: this is the record of why an hour is missing.
    """

    __slots__ = ("_date", "_directory", "_handle", "_source_id")

    def __init__(self, directory: Path, *, source_id: str) -> None:
        self._directory = directory
        self._source_id = source_id
        self._date: str | None = None
        self._handle: Any = None

    @property
    def directory(self) -> Path:
        return self._directory

    @property
    def source_id(self) -> str:
        return self._source_id

    def path_for(self, date: str) -> Path:
        return self._directory / f"supervisor__{self._source_id}__{date}.log"

    def event(self, message: str, **fields: Any) -> None:
        stamp = utc_now()
        date = stamp.strftime("%Y-%m-%d")
        if date != self._date or self._handle is None:
            self.close()
            self._directory.mkdir(parents=True, exist_ok=True)
            self._handle = self.path_for(date).open("a", encoding="utf-8", errors="replace")
            self._date = date
        detail = " ".join(f"{key}={value}" for key, value in fields.items())
        self._handle.write(f"{iso(stamp)} {message}{' ' + detail if detail else ''}\n")
        self._handle.flush()

    @property
    def handle(self) -> Any:
        """The open file, for the child process to write its own output into."""
        if self._handle is None:
            self.event("log_opened")
        return self._handle

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


# --------------------------------------------------------------------------- #
# One supervised process
# --------------------------------------------------------------------------- #


#: Builds a process from a command and the file its output goes to. Injected so the
#: restart path can be tested against a process that exits on cue.
Launcher = Callable[[list[str], Any], Any]


def _popen(command: list[str], output: Any) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        command,
        stdout=output,
        stderr=subprocess.STDOUT,
        cwd=str(Path.cwd()),
    )


class Child:
    """One supervised process: the recorder, or one poller. Not a ``@dataclass``.

    Driven by :meth:`step` on every pass of the loop and never blocks in it, so one
    child waiting out a backoff cannot stop another from being watched. The rules are
    the recorder's rules, unchanged, for every child: a backoff that doubles while
    failures continue, a reset after a healthy run, and exit code 2 — somebody else
    holds the lock — answered by waiting rather than by counting a restart.
    """

    __slots__ = (
        "_backoff",
        "_command",
        "_healthy_run_s",
        "_launched_at",
        "_launcher",
        "_locked_state",
        "_max_backoff_s",
        "_next_launch_at",
        "_output",
        "_owns_output",
        "_process",
        "_running_state",
        "_start_backoff_s",
        "name",
        "restarts",
        "spec",
        "state",
    )

    def __init__(
        self,
        *,
        name: str,
        command: Callable[[], list[str]],
        output: Callable[[], Any],
        owns_output: bool,
        backoff_s: float,
        max_backoff_s: float,
        healthy_run_s: float,
        running_state: str = "running",
        locked_state: str = "waiting: its lock is held by another live process",
        spec: PollerSpec | None = None,
        launcher: Launcher = _popen,
    ) -> None:
        self.name = name
        self.spec = spec
        self._command = command
        self._output = output
        self._owns_output = owns_output
        self._start_backoff_s = backoff_s
        self._backoff = backoff_s
        self._max_backoff_s = max_backoff_s
        self._healthy_run_s = healthy_run_s
        self._running_state = running_state
        self._locked_state = locked_state
        self._launcher = launcher
        self._process: Any = None
        self._launched_at = 0.0
        self._next_launch_at = 0.0
        self.restarts = 0
        self.state = "starting"

    @property
    def running(self) -> bool:
        return self._process is not None

    @property
    def backoff_s(self) -> float:
        return self._backoff

    def step(self, now: float, log: Log) -> None:
        """Launch if due, or look at the running process once. Never waits."""
        if self._process is None:
            if now >= self._next_launch_at:
                self._launch(now, log)
            return
        code = self._process.poll()
        if code is None:
            self.state = self._running_state
            return
        self._exited(int(code), now, log)

    def _launch(self, now: float, log: Log) -> None:
        log.event(f"{self.name}_launching", attempt=self.restarts + 1)
        output: Any = None
        try:
            command = self._command()
            output = self._output()
            self._process = self._launcher(command, output)
        except OSError as exc:
            # FileNotFoundError included: a listed poller whose script is not there
            # yet. Never launched with the missing path — Python would exit 2 for
            # "can't open file", and 2 is the lock wait, which would hide the fault.
            log.event(f"{self.name}_launch_failed", error=f"{type(exc).__name__}: {exc}")
            self.state = f"cannot launch: {exc}"
            self.restarts += 1
            self._next_launch_at = now + self._backoff
            self._backoff = min(self._backoff * BACKOFF_FACTOR, self._max_backoff_s)
            return
        finally:
            # The child holds its own copy of the handle; ours is closed at once so a
            # poller's log file is not held open by the supervisor for a month.
            if self._owns_output and output is not None:
                output.close()
        self._launched_at = now
        self.state = self._running_state

    def _exited(self, code: int, now: float, log: Log) -> None:
        self._process = None
        ran_for = now - self._launched_at
        log.event(f"{self.name}_exited", code=code, ran_for_s=f"{ran_for:.1f}")

        if code == EXIT_ARCHIVE_LOCKED:
            # Not a crash. Another live process holds the lock, and the right answer
            # is to wait rather than to fight it for the lock.
            self.state = self._locked_state
            log.event(
                "archive_locked" if self.name == RECORDER_NAME else f"{self.name}_locked",
                retry_in_s=LOCKED_RETRY_S,
            )
            self._next_launch_at = now + LOCKED_RETRY_S
            return

        if ran_for >= self._healthy_run_s:
            # It ran long enough to count. Whatever ended it is a new fault, not a
            # continuation of an old one, so it starts from the floor.
            self._backoff = self._start_backoff_s
            log.event(
                "backoff_reset" if self.name == RECORDER_NAME else f"{self.name}_backoff_reset",
                after_healthy_run_s=f"{ran_for:.1f}",
            )

        self.restarts += 1
        self.state = f"restarting in {self._backoff:.0f}s after exit code {code}"
        log.event(
            "restarting" if self.name == RECORDER_NAME else f"{self.name}_restarting",
            backoff_s=f"{self._backoff:.1f}",
            restarts=self.restarts,
        )
        self._next_launch_at = now + self._backoff
        self._backoff = min(self._backoff * BACKOFF_FACTOR, self._max_backoff_s)

    def stop(self, log: Log, reason: str) -> None:
        """Ask the process to end, then insist. Nothing to do when none is running."""
        process = self._process
        if process is None:
            return
        _terminate(process)
        log.event(f"{self.name}_exited", code=process.returncode, reason=reason)
        self._process = None


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #


def recorder_command(args: argparse.Namespace, recorder: Path) -> list[str]:
    command = [sys.executable, str(recorder)]
    if args.config:
        command += ["--config", str(args.config)]
    if args.source_id:
        command += ["--source-id", args.source_id]
    if args.out:
        command += ["--out", args.out]
    command += list(args.recorder_args or ())
    return command


def poller_command(args: argparse.Namespace, script: Path, spec: PollerSpec) -> list[str]:
    """The config and the source id the recorder gets, then the entry's own args.

    Not ``--out``: to the recorder it is the archive directory, to a poller it is
    the poller's own output directory, and passing one meaning to the other would
    write a poller's lines into the raw archive.
    """
    command = [sys.executable, str(script)]
    if args.config:
        command += ["--config", str(args.config)]
    if args.source_id:
        command += ["--source-id", args.source_id]
    command += list(spec.args)
    return command


def poller_log_path(log_dir: Path, name: str, source_id: str) -> Path:
    """``<name>__<source>__<date>.log``, dated by the launch, like the supervisor's."""
    return log_dir / f"{name}__{source_id}__{utc_now().strftime('%Y-%m-%d')}.log"


class Supervisor:
    """The recorder and the listed pollers, one pass at a time. Not a ``@dataclass``."""

    __slots__ = (
        "_args",
        "_config_path",
        "_launcher",
        "_log",
        "_search",
        "_source_id",
        "config_problem",
        "pollers",
        "recorder",
    )

    def __init__(
        self,
        args: argparse.Namespace,
        *,
        recorder: Path,
        log: Log,
        source_id: str,
        config_path: Path | None,
        search: Sequence[Path],
        launcher: Launcher = _popen,
    ) -> None:
        self._args = args
        self._log = log
        self._source_id = source_id
        self._config_path = config_path
        self._search = tuple(search)
        self._launcher = launcher
        command = recorder_command(args, recorder)
        self.recorder = Child(
            name=RECORDER_NAME,
            command=lambda: list(command),
            output=lambda: log.handle,
            owns_output=False,
            backoff_s=args.backoff_s,
            max_backoff_s=args.max_backoff_s,
            healthy_run_s=args.healthy_run_s,
            running_state="recording",
            locked_state="waiting: the archive is locked by another live recorder",
            launcher=launcher,
        )
        self.pollers: dict[str, Child] = {}
        self.config_problem: str | None = None

    def _poller(self, spec: PollerSpec) -> Child:
        args = self._args
        search = self._search
        log_dir = self._log.directory
        source_id = self._source_id

        def command() -> list[str]:
            return poller_command(args, resolve_script(spec.script, search), spec)

        def output() -> Any:
            log_dir.mkdir(parents=True, exist_ok=True)
            return poller_log_path(log_dir, spec.name, source_id).open("ab")

        return Child(
            name=spec.name,
            command=command,
            output=output,
            owns_output=True,
            backoff_s=args.backoff_s,
            max_backoff_s=args.max_backoff_s,
            healthy_run_s=args.healthy_run_s,
            spec=spec,
            launcher=self._launcher,
        )

    def reload(self) -> None:
        """Re-read ``recorder.pollers`` and bring the running set into line with it.

        Touches pollers only. The recorder is not in either set this adds to or
        removes from, which is what makes it safe to call on every pass.
        """
        if self._config_path is None:
            return
        section = reread_section(self._config_path)
        if section is None:
            self._set_problem(f"{self._config_path.as_posix()} could not be read")
            return
        specs, problem = parse_pollers(section)
        if specs is None:
            self._set_problem(problem or "the list is unusable")
            return
        if self.config_problem is not None:
            self._log.event("pollers_config_readable_again")
        self.config_problem = None

        for name in sorted(set(self.pollers) - set(specs)):
            self._log.event("poller_delisted", name=name)
            self.pollers.pop(name).stop(self._log, "delisted")
        for name, spec in sorted(specs.items()):
            current = self.pollers.get(name)
            if current is not None and current.spec == spec:
                continue
            if current is not None:
                # Same name, different script args: the entry changed, so the old
                # process is stopped and the new one started from a clean backoff.
                self._log.event("poller_changed", name=name)
                current.stop(self._log, "changed")
            else:
                self._log.event("poller_listed", name=name, script=spec.script)
            self.pollers[name] = self._poller(spec)

    def _set_problem(self, problem: str) -> None:
        if problem != self.config_problem:
            self._log.event("pollers_config_not_applied", problem=problem)
        self.config_problem = problem

    def step(self, now: float) -> None:
        self.recorder.step(now, self._log)
        for name in sorted(self.pollers):
            self.pollers[name].step(now, self._log)

    def stop_all(self, reason: str) -> None:
        self.recorder.stop(self._log, reason)
        for name in sorted(self.pollers):
            self.pollers[name].stop(self._log, reason)

    def poller_lines(self) -> list[tuple[str, str]]:
        return [
            (name, f"{child.state} · restarts {child.restarts}")
            for name, child in sorted(self.pollers.items())
        ]


def supervise(args: argparse.Namespace, *, launcher: Launcher = _popen) -> int:
    recorder = find_recorder(args.recorder)
    config, config_path = locate_recorder_config(Path(args.config) if args.config else None)
    source_id = args.source_id or config_str(config, "source_id") or _hostname()
    archive_dir = Path(args.out or config_str(config, "archive_dir") or DEFAULT_ARCHIVE_DIR)
    log = Log(Path(args.log_dir), source_id=source_id)
    screen = Screen(ansi=False if args.no_ansi else None)
    poller_dirs = (
        tuple(Path(path) for path in args.poller_dir)
        if args.poller_dir
        else default_poller_dirs()
    )
    supervisor = Supervisor(
        args,
        recorder=recorder,
        log=log,
        source_id=source_id,
        config_path=config_path,
        search=poller_dirs,
        launcher=launcher,
    )
    started = utc_now()

    log.event(
        "supervisor_started",
        source_id=source_id,
        archive=archive_dir.as_posix(),
        recorder=recorder.as_posix(),
        command=" ".join(recorder_command(args, recorder)[1:]),
        config=config_path.as_posix() if config_path is not None else "none",
    )

    deadline = time.monotonic() + args.duration_s if args.duration_s > 0 else None
    next_reload = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                # Stop every child the way a person would, and let each write its own
                # stop marker.
                log.event("supervisor_stopping_recorder")
                supervisor.stop_all("supervisor_stop")
                log.event("supervisor_duration_reached")
                return 0
            if now >= next_reload:
                supervisor.reload()
                next_reload = now + args.reload_s
            supervisor.step(now)
            screen.draw(
                status_block(
                    source_id=source_id,
                    started=started,
                    now=utc_now(),
                    today_mb=today_bytes(archive_dir) / 1e6,
                    last_write=last_write_age_s(archive_dir),
                    restarts=supervisor.recorder.restarts,
                    state=supervisor.recorder.state,
                    pollers=supervisor.poller_lines(),
                    config_problem=supervisor.config_problem,
                )
            )
            time.sleep(args.refresh_s)
    except KeyboardInterrupt:
        # Not stopped from here: Ctrl+C reaches every child in the console group, and
        # the recorder writes its own stop marker on it. A forced terminate now would
        # race that marker.
        log.event("supervisor_interrupted")
        print("\nstopping the recorder …", flush=True)
        return 0
    finally:
        log.close()


def _hostname() -> str:
    import socket

    return socket.gethostname().lower() or "unknown"


def _terminate(child: Any) -> None:
    """Ask, then insist.

    The archive is append-only and every line is flushed, so a forced kill costs
    at most a partial final line — which the merge tooling already recognises and
    tolerates. Hanging forever waiting for a clean exit costs the next hour.
    """
    child.terminate()
    try:
        child.wait(timeout=20)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=20)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="supervise.py",
        description=(
            "Keep a recorder running, and the pollers listed under recorder.pollers. "
            "Relaunches each after a backoff when it exits, waits rather than "
            "crash-loops when its lock is held by another live process, logs every "
            "launch and exit, and shows one status block."
        ),
    )
    parser.add_argument("--recorder", default=None, help="path to record.py")
    parser.add_argument("--config", default=None, help="config file carrying `recorder:`")
    parser.add_argument("--source-id", default=None, help="overrides recorder.source_id")
    parser.add_argument("--out", default=None, help="overrides recorder.archive_dir")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="where the log goes")
    parser.add_argument(
        "--poller-dir",
        action="append",
        default=None,
        help=(
            "where listed pollers are looked for, in order; repeatable. Default: "
            "beside this file, then one directory up"
        ),
    )
    parser.add_argument(
        "--reload-s",
        type=float,
        default=DEFAULT_RELOAD_S,
        help="how often recorder.pollers is re-read, so a newly listed poller starts",
    )
    parser.add_argument(
        "--backoff-s",
        type=float,
        default=DEFAULT_BACKOFF_S,
        help="first wait before a relaunch; doubles while failures continue",
    )
    parser.add_argument(
        "--max-backoff-s",
        type=float,
        default=DEFAULT_MAX_BACKOFF_S,
        help="the ceiling that wait grows to",
    )
    parser.add_argument(
        "--healthy-run-s",
        type=float,
        default=HEALTHY_RUN_S,
        help=(
            "a run lasting this long resets the backoff, so an hourly network blip "
            "does not compound into a ten-minute wait by the evening"
        ),
    )
    parser.add_argument(
        "--refresh-s", type=float, default=DEFAULT_REFRESH_S, help="status block refresh"
    )
    parser.add_argument(
        "--duration-s",
        type=float,
        default=0.0,
        help="stop after this many seconds; 0 supervises until interrupted",
    )
    parser.add_argument(
        "--no-ansi",
        action="store_true",
        help="reprint the block instead of redrawing it in place",
    )
    parser.add_argument(
        "recorder_args",
        nargs="*",
        default=None,
        help="everything after `--` is passed to record.py unchanged",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # The status block carries an em dash. A Windows console is cp1252 by default
    # and would raise on it, which would be a supervisor that dies of its own
    # heading — so the stream is put into UTF-8 with replacement before anything
    # is printed.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(OSError, ValueError):
                reconfigure(encoding="utf-8", errors="replace")
    try:
        return supervise(parse_args(argv))
    except (FileNotFoundError, OSError) as exc:
        print(f"\n{type(exc).__name__}: {exc}\n", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    raise SystemExit(main())
