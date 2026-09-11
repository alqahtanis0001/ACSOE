#!/usr/bin/env python
"""Keep a recorder alive, and show one honest block of text while it does.

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

## What it shows

One block, refreshed in place, and that is the entire interface of a node:

    RECORDING — vps-fra-1
    started    2026-09-11T17:40:02Z
    uptime     3h 12m
    today      41283 MB
    last write 0s ago
    restarts   2

No buttons and no commands, on purpose. A node is a machine that records; every
decision about it is taken on the master, and an interface that invited a decision
here would be an interface that lets somebody stop a recorder from the wrong
keyboard.

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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

#: Exit code `record.py` uses for "another recorder holds this archive". Waiting
#: is the correct response and it is not a failure, so it is spelled out rather
#: than left as a magic 2 in a comparison.
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

DEFAULT_ARCHIVE_DIR: Final = Path("data") / "raw"
DEFAULT_LOG_DIR: Final = Path("logs")

CONFIG_CANDIDATES: Final = (
    Path("config") / "recorder.yaml",
    Path("recorder.yaml"),
    Path("config") / "default.yaml",
)
CONFIG_SECTION: Final = "recorder"

LOCK_FILENAME: Final = ".recorder.lock"
HEARTBEAT_GLOB: Final = "heartbeat__*.ndjson"

#: How much of the end of a file to read when looking for its last line.
TAIL_BYTES: Final = 256 * 1024

STATUS_LINES: Final = 6


# --------------------------------------------------------------------------- #
# Config — the same reader `record.py` carries, and duplicated for the same
# reason: these two files are a node package and neither may import the other.
# --------------------------------------------------------------------------- #


def load_recorder_config(explicit: Path | None = None) -> dict[str, Any]:
    """The ``recorder:`` mapping, or ``{}``."""
    if explicit is not None and not explicit.is_file():
        raise FileNotFoundError(f"--config {explicit} does not exist")
    try:
        import yaml  # optional; absent on a bare server
    except ImportError:
        if explicit is not None:
            raise
        return {}
    here = Path(__file__).resolve().parent
    searched = (
        [explicit]
        if explicit is not None
        else [
            base / candidate
            for base in (Path.cwd(), here, here.parent, here.parent.parent)
            for candidate in CONFIG_CANDIDATES
        ]
    )
    for path in searched:
        if not path.is_file():
            continue
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get(CONFIG_SECTION), dict):
            return dict(loaded[CONFIG_SECTION])
    return {}


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
) -> str:
    """The six lines, exactly. The whole interface of a node."""
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


def supervise(args: argparse.Namespace) -> int:
    recorder = find_recorder(args.recorder)
    config = load_recorder_config(Path(args.config) if args.config else None)
    source_id = args.source_id or config_str(config, "source_id") or _hostname()
    archive_dir = Path(args.out or config_str(config, "archive_dir") or DEFAULT_ARCHIVE_DIR)
    log = Log(Path(args.log_dir), source_id=source_id)
    screen = Screen(ansi=False if args.no_ansi else None)

    command = recorder_command(args, recorder)
    started = utc_now()
    restarts = 0
    backoff = args.backoff_s
    state = "starting"

    log.event(
        "supervisor_started",
        source_id=source_id,
        archive=archive_dir.as_posix(),
        recorder=recorder.as_posix(),
        command=" ".join(command[1:]),
    )

    deadline = time.monotonic() + args.duration_s if args.duration_s > 0 else None
    try:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                log.event("supervisor_duration_reached")
                return 0

            launched_at = time.monotonic()
            log.event("recorder_launching", attempt=restarts + 1)
            try:
                child = subprocess.Popen(
                    command,
                    stdout=log.handle,
                    stderr=subprocess.STDOUT,
                    cwd=str(Path.cwd()),
                )
            except OSError as exc:
                log.event("recorder_launch_failed", error=f"{type(exc).__name__}: {exc}")
                state = f"cannot launch the recorder: {exc}"
                _sleep_showing(
                    screen,
                    log,
                    seconds=backoff,
                    source_id=source_id,
                    started=started,
                    archive_dir=archive_dir,
                    restarts=restarts,
                    state=state,
                    refresh_s=args.refresh_s,
                    deadline=deadline,
                )
                backoff = min(backoff * BACKOFF_FACTOR, args.max_backoff_s)
                restarts += 1
                continue

            state = "recording"
            code = _wait_showing(
                child,
                screen,
                seconds_deadline=deadline,
                source_id=source_id,
                started=started,
                archive_dir=archive_dir,
                restarts=restarts,
                state=state,
                refresh_s=args.refresh_s,
            )
            if code is None:
                # The duration ran out while the recorder was healthy. Stop it the
                # way a person would, and let it write its own stop marker.
                log.event("supervisor_stopping_recorder")
                _terminate(child)
                log.event("recorder_exited", code=child.returncode, reason="supervisor_stop")
                return 0

            ran_for = time.monotonic() - launched_at
            log.event("recorder_exited", code=code, ran_for_s=f"{ran_for:.1f}")

            if code == EXIT_ARCHIVE_LOCKED:
                # Not a crash. Another live recorder holds the archive, and the
                # right answer is to wait rather than to fight it for the lock.
                state = "waiting: the archive is locked by another live recorder"
                log.event("archive_locked", retry_in_s=LOCKED_RETRY_S)
                _sleep_showing(
                    screen,
                    log,
                    seconds=LOCKED_RETRY_S,
                    source_id=source_id,
                    started=started,
                    archive_dir=archive_dir,
                    restarts=restarts,
                    state=state,
                    refresh_s=args.refresh_s,
                    deadline=deadline,
                )
                continue

            if ran_for >= args.healthy_run_s:
                # It ran long enough to count. Whatever ended it is a new fault,
                # not a continuation of an old one, so it starts from the floor.
                backoff = args.backoff_s
                log.event("backoff_reset", after_healthy_run_s=f"{ran_for:.1f}")

            restarts += 1
            state = f"restarting in {backoff:.0f}s after exit code {code}"
            log.event("restarting", backoff_s=f"{backoff:.1f}", restarts=restarts)
            _sleep_showing(
                screen,
                log,
                seconds=backoff,
                source_id=source_id,
                started=started,
                archive_dir=archive_dir,
                restarts=restarts,
                state=state,
                refresh_s=args.refresh_s,
                deadline=deadline,
            )
            backoff = min(backoff * BACKOFF_FACTOR, args.max_backoff_s)
    except KeyboardInterrupt:
        log.event("supervisor_interrupted")
        print("\nstopping the recorder …", flush=True)
        return 0
    finally:
        log.close()


def _hostname() -> str:
    import socket

    return socket.gethostname().lower() or "unknown"


def _terminate(child: subprocess.Popen[bytes]) -> None:
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


def _render(
    screen: Screen,
    *,
    source_id: str,
    started: datetime,
    archive_dir: Path,
    restarts: int,
    state: str,
) -> None:
    screen.draw(
        status_block(
            source_id=source_id,
            started=started,
            now=utc_now(),
            today_mb=today_bytes(archive_dir) / 1e6,
            last_write=last_write_age_s(archive_dir),
            restarts=restarts,
            state=state,
        )
    )


def _wait_showing(
    child: subprocess.Popen[bytes],
    screen: Screen,
    *,
    seconds_deadline: float | None,
    refresh_s: float,
    **block: Any,
) -> int | None:
    """Wait for the child, refreshing the block. The exit code, or None on deadline."""
    while True:
        _render(screen, **block)
        try:
            return child.wait(timeout=refresh_s)
        except subprocess.TimeoutExpired:
            pass
        if seconds_deadline is not None and time.monotonic() >= seconds_deadline:
            return None


def _sleep_showing(
    screen: Screen,
    log: Log,
    *,
    seconds: float,
    refresh_s: float,
    deadline: float | None,
    **block: Any,
) -> None:
    del log
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if deadline is not None and time.monotonic() >= deadline:
            return
        _render(screen, **block)
        time.sleep(min(refresh_s, max(0.0, end - time.monotonic())))
    _render(screen, **block)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="supervise.py",
        description=(
            "Keep a recorder running. Relaunches it after a backoff when it exits, "
            "waits rather than crash-loops when the archive is locked by another "
            "live recorder, logs every launch and exit, and shows one status block."
        ),
    )
    parser.add_argument("--recorder", default=None, help="path to record.py")
    parser.add_argument("--config", default=None, help="config file carrying `recorder:`")
    parser.add_argument("--source-id", default=None, help="overrides recorder.source_id")
    parser.add_argument("--out", default=None, help="overrides recorder.archive_dir")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="where the log goes")
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
