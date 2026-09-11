"""The recorder's storage and lifecycle: the lock, the day, and the name.

Three properties, all of which fail silently in production if they break, which
is why each one is asserted against an observable artefact rather than against a
return value.

**The lock.** Two recorders on one archive interleave their lines and duplicate
their session markers. Every individual line stays valid, so nothing downstream
reports it and the damage is found months later by somebody replaying the day.
The lock is asserted across two real processes, because an in-process assertion
would prove nothing: the whole question is what the *operating system* does, and
a same-process second acquire can succeed on some platforms while a second
process correctly fails.

**The day.** A file must cover exactly one UTC calendar date. Two triggers make
that true — the line's own date on every write, and a wall-clock roll at midnight
for a stream that has gone quiet — and they are tested separately, because the
first one hides the second: with frames arriving continuously the roller never
fires, so an end-to-end test of a busy recorder passes with the roller deleted.

**The name.** `source_id` in the filename is what stops two machines' archives
colliding. The test that matters is not that the name has the right shape, it is
that a second run on the same day appends to the same file while a different
source gets a different one.

`scripts/record.py` is loaded by path — it is deliberately not a package.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_PY = REPO_ROOT / "scripts" / "record.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("acsoe_record_storage_script", RECORD_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


record = _load()


def line(stamp: str) -> dict[str, object]:
    return record.build_line(
        kind="tick",
        pair="BTC/USD",
        channel="book",
        ts_exchange=None,
        ts_recv=stamp,
        payload={"channel": "book"},
    )


# --------------------------------------------------------------------------- #
# Source-tagged filenames
# --------------------------------------------------------------------------- #


def test_the_filename_carries_the_prefix_the_source_and_the_date() -> None:
    assert (
        record.archive_filename("kraken_v2", "vps-fra-1", "2026-09-11")
        == "kraken_v2__vps-fra-1__2026-09-11.jsonl"
    )
    assert (
        record.archive_filename("summary", "msi", "2026-09-11") == "summary__msi__2026-09-11.jsonl"
    )


def test_the_name_splits_back_into_exactly_three_parts() -> None:
    """Which is why the separator is `__` and a source id may not contain one.

    `kraken_v2` already has a single underscore in it. If the source id could too,
    `kraken_v2__my_host__2026-09-11` would still split into three on `__` but
    `kraken__v2__host__date` would not, and a name that cannot be parsed back is a
    name that `archive_move.py` cannot date and will refuse to move.
    """
    name = record.archive_filename("kraken_v2", record.sanitise_source_id("my_host 01"), "2026-09-11")
    prefix, source, tail = name[: -len(".jsonl")].split(record.NAME_SEPARATOR)
    assert (prefix, source, tail) == ("kraken_v2", "my-host-01", "2026-09-11")


def test_the_source_id_defaults_to_the_hostname() -> None:
    import socket

    assert record.default_source_id() == record.sanitise_source_id(socket.gethostname())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MSI", "msi"),
        ("vps-fra-1", "vps-fra-1"),
        ("my_host", "my-host"),
        ("host.example.com", "host.example.com"),
        ("a/b\\c", "a-b-c"),
        ("  spaced  name  ", "spaced-name"),
        ("...trimmed...", "trimmed"),
    ],
)
def test_sanitise_source_id(raw: str, expected: str) -> None:
    assert record.sanitise_source_id(raw) == expected


def test_a_source_id_that_survives_nothing_is_refused() -> None:
    """Rather than becoming an empty segment in a filename nobody can parse."""
    with pytest.raises(ValueError, match="nothing usable in a filename"):
        record.sanitise_source_id("///")


def test_two_sources_recording_one_day_write_two_files(tmp_path: Path) -> None:
    """The whole reason the source is in the name."""
    for source in ("msi", "vps-fra-1"):
        with record.JsonlWriter(tmp_path, source_id=source) as writer:
            writer.write(line("2026-09-11T12:00:00.000000Z"))
    assert sorted(path.name for path in tmp_path.glob("*.jsonl")) == [
        "kraken_v2__msi__2026-09-11.jsonl",
        "kraken_v2__vps-fra-1__2026-09-11.jsonl",
    ]


def test_a_run_starting_mid_day_appends_to_that_days_file(tmp_path: Path) -> None:
    """One file per day, not one file per run.

    Three separate writer lifetimes on one date produce one file with three lines.
    If this ever becomes three files, every piece of arithmetic over the archive —
    gap accounting, the mover's eligibility, the merger's coverage — changes from
    "a file is a day" to "a file is part of a day", silently.
    """
    for hour in ("00", "12", "23"):
        with record.JsonlWriter(tmp_path, source_id="msi") as writer:
            writer.write(line(f"2026-09-11T{hour}:00:00.000000Z"))
    files = sorted(tmp_path.glob("*.jsonl"))
    assert [path.name for path in files] == ["kraken_v2__msi__2026-09-11.jsonl"]
    assert files[0].read_text(encoding="utf-8").count("\n") == 3


# --------------------------------------------------------------------------- #
# One file per UTC day
# --------------------------------------------------------------------------- #


def test_a_line_is_written_to_the_file_for_its_own_date(tmp_path: Path) -> None:
    with record.JsonlWriter(tmp_path, source_id="msi") as writer:
        writer.write(line("2026-09-11T23:59:59.900000Z"))
        writer.write(line("2026-09-12T00:00:00.100000Z"))
        writer.write(line("2026-09-12T00:00:01.100000Z"))
    assert writer.path_for("2026-09-11").read_text(encoding="utf-8").count("\n") == 1
    assert writer.path_for("2026-09-12").read_text(encoding="utf-8").count("\n") == 2


def test_a_late_line_still_lands_in_its_own_days_file(tmp_path: Path) -> None:
    """A summary row for 23:59, flushed a second after midnight, is yesterday's.

    The rotation follows the line, not the clock, so the row does not get filed
    under a day it does not describe. Rotating back is allowed: the file is opened
    in append mode and nothing is truncated.
    """
    with record.JsonlWriter(tmp_path, source_id="msi") as writer:
        writer.write(line("2026-09-11T23:59:59.000000Z"))
        writer.write(line("2026-09-12T00:00:02.000000Z"))
        writer.write(line("2026-09-11T23:59:59.500000Z"))
    assert writer.path_for("2026-09-11").read_text(encoding="utf-8").count("\n") == 2
    assert writer.path_for("2026-09-12").read_text(encoding="utf-8").count("\n") == 1


def test_roll_to_closes_the_old_file_and_opens_the_new_one(tmp_path: Path) -> None:
    writer = record.JsonlWriter(tmp_path, source_id="msi")
    with writer:
        writer.write(line("2026-09-11T23:59:59.000000Z"))
        assert writer.open_date == "2026-09-11"
        assert writer.roll_to("2026-09-12") is True
        assert writer.open_date == "2026-09-12"
        # Idempotent: rolling to the date already open does nothing.
        assert writer.roll_to("2026-09-12") is False
        writer.write(line("2026-09-12T00:00:01.000000Z"))
    assert writer.path_for("2026-09-11").read_text(encoding="utf-8").count("\n") == 1
    assert writer.path_for("2026-09-12").read_text(encoding="utf-8").count("\n") == 1


def test_roll_to_does_not_open_a_file_for_a_writer_that_has_written_nothing(
    tmp_path: Path,
) -> None:
    """An empty file in the archive is a claim about coverage that nothing made.

    Tier 2 with no pairs above the volume floor, or tier 1 during a long
    disconnect, has no open file. Midnight must not create one for it.
    """
    with record.JsonlWriter(tmp_path, source_id="msi") as writer:
        assert writer.roll_to("2026-09-12") is False
    assert list(tmp_path.glob("*.jsonl")) == []


@pytest.mark.asyncio
async def test_the_midnight_roller_rotates_a_silent_stream(tmp_path: Path) -> None:
    """The case the per-line rule cannot reach.

    No line arrives after 23:59, so nothing triggers the write-time rotation. The
    roller has to close yesterday's file on the clock alone, mid-run, with no
    restart — which is the property that makes "a file is one calendar day" true
    for a quiet pair as well as a busy one.
    """
    import asyncio

    writer = record.JsonlWriter(tmp_path, source_id="msi")
    with writer:
        writer.write(line("2026-09-11T23:59:59.000000Z"))
        assert writer.open_date == "2026-09-11"

        stopping = asyncio.Event()
        dates = iter(["2026-09-11", "2026-09-12", "2026-09-12"])
        task = asyncio.ensure_future(
            record.midnight_roller(
                writers=(writer,),
                stopping=stopping,
                interval_s=0.01,
                now=lambda: next(dates, "2026-09-12"),
            )
        )
        for _ in range(200):
            await asyncio.sleep(0.01)
            if writer.open_date == "2026-09-12":
                break
        stopping.set()
        rotated = await task

    assert rotated == 1, "the roller did not close yesterday's file"
    assert writer.path_for("2026-09-11").is_file()
    assert writer.path_for("2026-09-12").is_file()
    # Yesterday's file is closed and complete: exactly the one line, and it is
    # the line that belongs to that day.
    yesterday = writer.path_for("2026-09-11").read_text(encoding="utf-8").splitlines()
    assert len(yesterday) == 1
    assert json.loads(yesterday[0])["ts_recv"].startswith("2026-09-11")


def test_current_utc_date_is_utc_not_local() -> None:
    assert record.current_utc_date() == datetime.now(UTC).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# The configurable archive directory
# --------------------------------------------------------------------------- #


def _args(argv: list[str]) -> object:
    return record.parse_args(argv)


def test_the_flag_beats_the_config_beats_the_default(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "recorder.yaml"
    config.write_text(
        "recorder:\n"
        "  archive_dir: from-config/raw\n"
        "  summary_dir: from-config/summaries\n"
        "  source_id: from-config\n",
        encoding="utf-8",
    )
    raw, summary, source = record.resolve_storage(
        _args(["--config", str(config)])
    )
    assert raw == Path("from-config/raw")
    assert summary == Path("from-config/summaries")
    assert source == "from-config"

    raw, summary, source = record.resolve_storage(
        _args(["--config", str(config), "--out", "E:/flag", "--source-id", "FLAG_ONE"])
    )
    assert raw == Path("E:/flag")
    assert summary == Path("from-config/summaries"), "an unset flag must not clear the config"
    assert source == "flag-one"


def test_with_no_config_anywhere_the_defaults_apply(tmp_path: Path, monkeypatch) -> None:
    """`cwd` is an empty directory, so neither candidate file exists."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(record, "CONFIG_CANDIDATES", (Path("nowhere.yaml"),))
    raw, summary, _source = record.resolve_storage(_args([]))
    assert raw == record.DEFAULT_OUT_DIR
    assert summary == record.DEFAULT_SUMMARY_DIR


def test_an_empty_config_value_does_not_become_the_current_directory(tmp_path: Path) -> None:
    """A blank `archive_dir:` must fall through to the default, not to `Path("")`.

    `Path("")` is the working directory, so the failure mode is 17 GB a day into
    the repository root rather than an error anybody would notice.
    """
    config = tmp_path / "recorder.yaml"
    config.write_text('recorder:\n  archive_dir: ""\n  source_id: "  "\n', encoding="utf-8")
    raw, _summary, source = record.resolve_storage(_args(["--config", str(config)]))
    assert raw == record.DEFAULT_OUT_DIR
    assert source == record.default_source_id()


def test_the_config_may_also_live_in_the_main_config_file(tmp_path: Path) -> None:
    """So moving the keys into `config/default.yaml` later costs nothing here.

    It cannot go there today: `Config` in `platform/config.py` is `extra="forbid"`
    and an unmodelled `recorder:` key would make the whole system refuse to start.
    The reader looks in both files so that whoever adds the pydantic section does
    not also have to change three scripts.
    """
    default = tmp_path / "default.yaml"
    default.write_text("mode: paper\nrecorder:\n  archive_dir: from-default\n", encoding="utf-8")
    assert record.load_recorder_config(default) == {"archive_dir": "from-default"}


def test_a_config_file_without_a_recorder_section_is_not_an_error(tmp_path: Path) -> None:
    config = tmp_path / "recorder.yaml"
    config.write_text("something_else:\n  key: 1\n", encoding="utf-8")
    assert record.load_recorder_config(config) == {}


def test_a_named_config_that_does_not_exist_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        record.load_recorder_config(tmp_path / "absent.yaml")


# --------------------------------------------------------------------------- #
# The single-instance lock
# --------------------------------------------------------------------------- #

LOCK_PROBE = """
import importlib.util, sys, time
from pathlib import Path

spec = importlib.util.spec_from_file_location("rec", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules["rec"] = module
spec.loader.exec_module(module)

directory = Path(sys.argv[2])
if sys.argv[3] == "hold":
    with module.ArchiveLock(directory):
        print("HELD", flush=True)
        time.sleep(float(sys.argv[4]))
    print("RELEASED", flush=True)
else:
    try:
        with module.ArchiveLock(directory):
            print("ACQUIRED", flush=True)
    except module.ArchiveLockedError as exc:
        print("REFUSED", flush=True)
        print(str(exc), flush=True)
        raise SystemExit(2) from None
"""


def _probe_path(tmp_path: Path) -> Path:
    probe = tmp_path / "lock_probe.py"
    probe.write_text(textwrap.dedent(LOCK_PROBE), encoding="utf-8")
    return probe


def _try_acquire(probe: Path, directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(probe), str(RECORD_PY), str(directory), "try"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_a_second_recorder_on_one_archive_is_refused(tmp_path: Path) -> None:
    """Across two real processes, because the assertion is about the kernel."""
    probe = _probe_path(tmp_path)
    archive = tmp_path / "raw"
    archive.mkdir()

    holder = subprocess.Popen(
        [sys.executable, "-I", str(probe), str(RECORD_PY), str(archive), "hold", "30"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "HELD"

        second = _try_acquire(probe, archive)
        assert second.returncode == 2, second.stdout + second.stderr
        assert "REFUSED" in second.stdout
        assert "already writing to" in second.stdout
        # The message has to tell the operator what to do about it.
        assert "--out" in second.stdout
    finally:
        holder.kill()
        holder.wait(timeout=30)


def test_a_different_archive_directory_is_not_blocked(tmp_path: Path) -> None:
    """The lock is per archive, not per machine. Two recorders writing two
    archives — the usual way to record a second quote currency — is fine."""
    probe = _probe_path(tmp_path)
    first = tmp_path / "raw"
    second = tmp_path / "other"
    first.mkdir()
    second.mkdir()

    holder = subprocess.Popen(
        [sys.executable, "-I", str(probe), str(RECORD_PY), str(first), "hold", "30"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "HELD"
        result = _try_acquire(probe, second)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "ACQUIRED" in result.stdout
    finally:
        holder.kill()
        holder.wait(timeout=30)


def test_the_lock_is_released_when_the_holder_is_killed_without_cleanup(tmp_path: Path) -> None:
    """**The reason this is an OS lock and not a PID file.**

    The holder is killed outright: no `finally`, no `atexit`, no signal handler
    runs — the shape of a power cut, an `Errno 28`, or the forced kill this
    recorder needs on Windows because `loop.add_signal_handler` raises on the
    Proactor loop. A PID file would still be sitting there and every future
    recorder would refuse to start, turning a recoverable crash into an
    indefinite outage in the one dataset that cannot be backfilled.

    The lock file is deliberately still on disk when the assertion runs, so this
    cannot pass for the trivial reason that cleanup removed it.
    """
    probe = _probe_path(tmp_path)
    archive = tmp_path / "raw"
    archive.mkdir()

    holder = subprocess.Popen(
        [sys.executable, "-I", str(probe), str(RECORD_PY), str(archive), "hold", "300"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "HELD"
    holder.kill()
    holder.wait(timeout=30)

    lock_file = archive / record.LOCK_FILENAME
    assert lock_file.is_file(), "the stale lock file must still be there, or this proves nothing"

    result = _try_acquire(probe, archive)
    assert result.returncode == 0, (
        f"a killed recorder left the archive locked. That is the PID-file failure "
        f"this lock exists to avoid.\n{result.stdout}{result.stderr}"
    )
    assert "ACQUIRED" in result.stdout


def test_the_lock_file_is_not_mistaken_for_an_archive_file(tmp_path: Path) -> None:
    """Every consumer globs `*.jsonl`. The lock must not match, and must not be
    picked up by the report, the builder or the fixture generator."""
    archive = tmp_path / "raw"
    with record.ArchiveLock(archive):
        assert (archive / record.LOCK_FILENAME).is_file()
        assert list(archive.glob("*.jsonl")) == []


def test_the_lock_creates_the_archive_directory(tmp_path: Path) -> None:
    """It is taken before the first byte is written, which is before the writer
    has had a chance to make the directory."""
    archive = tmp_path / "deep" / "nested" / "raw"
    with record.ArchiveLock(archive):
        assert archive.is_dir()


def test_releasing_and_reacquiring_in_one_process_works(tmp_path: Path) -> None:
    archive = tmp_path / "raw"
    lock = record.ArchiveLock(archive)
    lock.acquire()
    lock.release()
    lock.release()  # idempotent; a double release must not raise
    with record.ArchiveLock(archive):
        pass


def test_the_lock_note_names_the_process_holding_it(tmp_path: Path) -> None:
    """Diagnostic only. Nothing reads it to decide whether the lock is held —
    that would be a PID file wearing a different hat."""
    archive = tmp_path / "raw"
    with record.ArchiveLock(archive) as lock:
        if sys.platform == "win32":
            pytest.skip("the locked byte range is unreadable by design on Windows")
        note = json.loads(lock.path.read_text(encoding="utf-8"))
        assert note["pid"] == os.getpid()
        assert note["acquired_at"].endswith("Z")
