"""The supervisor's pollers: `scripts/recording/supervise.py`.

Loaded by path: it is half of a node package and must not become a package. The
restart rules are driven through an injected launcher and explicit monotonic times,
so a backoff is asserted to the second without sleeping through it. One test runs
real child processes end to end, because the property that matters most — a poller
listed while the supervisor runs starts without the recorder being relaunched — is a
property of the loop, and a loop is only proved by running it.

The six-line block and the locked exit code are pinned in `test_recording_manager.py`
and are not repeated here.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SUPERVISE_PY = REPO_ROOT / "scripts" / "recording" / "supervise.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("acsoe_supervise_pollers", SUPERVISE_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


supervise = _load()


# --------------------------------------------------------------------------- #
# Doubles
# --------------------------------------------------------------------------- #


class FakeProcess:
    """A process that exits when told to. `poll()` answers None until then."""

    def __init__(self, command: list[str]) -> None:
        self.command = command
        self.returncode: int | None = None
        self.terminated = False

    def exit(self, code: int) -> None:
        self.returncode = code

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        if self.returncode is None:
            self.returncode = -15

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        assert self.returncode is not None
        return self.returncode

    def kill(self) -> None:  # pragma: no cover - terminate always succeeds here
        self.returncode = -9


class FakeLauncher:
    def __init__(self) -> None:
        self.launched: list[FakeProcess] = []

    def __call__(self, command: list[str], output: Any) -> FakeProcess:
        del output
        process = FakeProcess(command)
        self.launched.append(process)
        return process

    def by_script(self, name: str) -> list[FakeProcess]:
        return [process for process in self.launched if Path(process.command[1]).name == name]


class Output:
    def close(self) -> None:
        pass


def _log(tmp_path: Path) -> Any:
    return supervise.Log(tmp_path / "logs", source_id="test")


def _events(tmp_path: Path) -> list[str]:
    return [
        line.split(" ", 2)[1]
        for path in sorted((tmp_path / "logs").glob("supervisor__*.log"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _child(
    launcher: FakeLauncher,
    *,
    name: str = "funding",
    command: Any = None,
    backoff_s: float = 5.0,
    healthy_run_s: float = 120.0,
) -> Any:
    return supervise.Child(
        name=name,
        command=command or (lambda: ["python", f"{name}.py"]),
        output=Output,
        owns_output=True,
        backoff_s=backoff_s,
        max_backoff_s=40.0,
        healthy_run_s=healthy_run_s,
        launcher=launcher,
    )


# --------------------------------------------------------------------------- #
# The restart path
# --------------------------------------------------------------------------- #


def test_a_crashed_poller_is_relaunched_after_a_backoff_that_doubles(tmp_path: Path) -> None:
    launcher = FakeLauncher()
    log = _log(tmp_path)
    child = _child(launcher)

    child.step(0.0, log)
    assert len(launcher.launched) == 1
    assert child.state == "running"

    launcher.launched[0].exit(1)
    child.step(1.0, log)
    assert child.restarts == 1
    assert child.state == "restarting in 5s after exit code 1"

    child.step(5.9, log)
    assert len(launcher.launched) == 1, "relaunched before its backoff was up"
    child.step(6.0, log)
    assert len(launcher.launched) == 2, "not relaunched once the backoff was up"

    launcher.launched[1].exit(1)
    child.step(7.0, log)
    assert child.state == "restarting in 10s after exit code 1", "the backoff did not double"
    child.step(16.9, log)
    assert len(launcher.launched) == 2
    child.step(17.0, log)
    assert len(launcher.launched) == 3

    events = _events(tmp_path)
    assert events.count("funding_launching") == 3
    assert events.count("funding_exited") == 2
    assert events.count("funding_restarting") == 2


def test_a_healthy_run_resets_the_backoff(tmp_path: Path) -> None:
    launcher = FakeLauncher()
    log = _log(tmp_path)
    child = _child(launcher, healthy_run_s=100.0)

    child.step(0.0, log)
    launcher.launched[0].exit(1)
    child.step(1.0, log)
    child.step(6.0, log)
    assert child.backoff_s == 10.0, "one failure doubles the 5s floor"

    launcher.launched[1].exit(1)
    child.step(500.0, log)
    assert child.state == "restarting in 5s after exit code 1"
    assert "funding_backoff_reset" in _events(tmp_path)


def test_exit_code_two_waits_for_the_lock_and_is_not_a_restart(tmp_path: Path) -> None:
    """At the switchover the hand-started poller may still hold the funding lock. The
    supervised one must wait for it, not crash-loop against it."""
    launcher = FakeLauncher()
    log = _log(tmp_path)
    child = _child(launcher)

    child.step(0.0, log)
    launcher.launched[0].exit(supervise.EXIT_ARCHIVE_LOCKED)
    child.step(1.0, log)
    assert child.restarts == 0
    assert child.backoff_s == 5.0
    assert child.state.startswith("waiting")

    child.step(1.0 + supervise.LOCKED_RETRY_S - 0.1, log)
    assert len(launcher.launched) == 1
    child.step(1.0 + supervise.LOCKED_RETRY_S, log)
    assert len(launcher.launched) == 2
    assert "funding_locked" in _events(tmp_path)


def test_a_missing_script_is_a_launch_failure_and_never_launched(tmp_path: Path) -> None:
    """Python exits 2 for "can't open file", and 2 is the lock wait. So a missing
    script must never reach the launcher, or it would sit in `waiting` for ever."""
    launcher = FakeLauncher()
    log = _log(tmp_path)

    def missing() -> list[str]:
        raise FileNotFoundError("fees.py was not found in here")

    child = _child(launcher, name="fees", command=missing)
    child.step(0.0, log)
    assert launcher.launched == []
    assert child.restarts == 1
    assert child.state.startswith("cannot launch")
    child.step(4.9, log)
    child.step(5.0, log)
    assert child.restarts == 2, "the launch was not retried after its backoff"
    assert "fees_launch_failed" in _events(tmp_path)


def test_the_recorder_keeps_its_phase_zero_event_names(tmp_path: Path) -> None:
    """The supervisor log is how a missing hour is explained later; renaming its
    events would split that record in two."""
    launcher = FakeLauncher()
    log = _log(tmp_path)
    child = _child(launcher, name="recorder")
    child.step(0.0, log)
    launcher.launched[0].exit(1)
    child.step(1.0, log)
    launcher.launched[0].exit(supervise.EXIT_ARCHIVE_LOCKED)
    child.step(6.0, log)
    launcher.launched[1].exit(supervise.EXIT_ARCHIVE_LOCKED)
    child.step(7.0, log)
    events = _events(tmp_path)
    for name in ("recorder_launching", "recorder_exited", "restarting", "archive_locked"):
        assert name in events, name


# --------------------------------------------------------------------------- #
# The list
# --------------------------------------------------------------------------- #


def test_an_absent_list_is_no_pollers_and_no_problem() -> None:
    assert supervise.parse_pollers({}) == ({}, None)
    assert supervise.parse_pollers({"pollers": None}) == ({}, None)


def test_a_valid_list_is_read_by_name() -> None:
    specs, problem = supervise.parse_pollers(
        {"pollers": [{"script": "funding.py"}, {"script": "fees.py", "args": ["--once"]}]}
    )
    assert problem is None
    assert specs is not None
    assert sorted(specs) == ["fees", "funding"]
    assert specs["fees"].args == ("--once",)


@pytest.mark.parametrize(
    "pollers",
    [
        "funding.py",
        ["funding.py"],
        [{"script": "funding.py", "extra": 1}],
        [{"args": []}],
        [{"script": "../funding.py"}],
        [{"script": "sub/funding.py"}],
        [{"script": "C:\\funding.py"}],
        [{"script": "funding.sh"}],
        [{"script": "record.py"}],
        [{"script": "supervise.py"}],
        [{"script": "recorder.py"}],
        [{"script": "funding.py", "args": "--once"}],
        [{"script": "funding.py", "args": [1]}],
        [{"script": "funding.py"}, {"script": "funding.py", "args": ["--once"]}],
    ],
)
def test_one_bad_entry_makes_the_whole_list_unusable(pollers: object) -> None:
    specs, problem = supervise.parse_pollers({"pollers": pollers})
    assert specs is None
    assert problem


def _write_config(path: Path, pollers: str) -> None:
    path.write_text(f"recorder:\n  source_id: test\n{pollers}", encoding="utf-8")


FUNDING_ONLY = "  pollers:\n    - script: funding.py\n"
FUNDING_AND_FEES = "  pollers:\n    - script: funding.py\n    - script: fees.py\n"


def _supervisor(tmp_path: Path, launcher: FakeLauncher, config: Path) -> Any:
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    for name in ("record.py", "funding.py", "fees.py"):
        (scripts / name).write_text("", encoding="utf-8")
    args = supervise.parse_args(["--config", str(config), "--log-dir", str(tmp_path / "logs")])
    return supervise.Supervisor(
        args,
        recorder=scripts / "record.py",
        log=_log(tmp_path),
        source_id="test",
        config_path=config,
        search=(scripts,),
        launcher=launcher,
    )


def test_a_newly_listed_poller_starts_without_relaunching_the_recorder(tmp_path: Path) -> None:
    config = tmp_path / "recorder.yaml"
    _write_config(config, FUNDING_ONLY)
    launcher = FakeLauncher()
    sup = _supervisor(tmp_path, launcher, config)

    sup.reload()
    sup.step(0.0)
    assert len(launcher.by_script("record.py")) == 1
    assert len(launcher.by_script("funding.py")) == 1
    assert launcher.by_script("fees.py") == []

    _write_config(config, FUNDING_AND_FEES)
    sup.reload()
    sup.step(1.0)
    assert len(launcher.by_script("fees.py")) == 1, "the newly listed poller did not start"
    assert len(launcher.by_script("record.py")) == 1, "the recorder was relaunched"
    assert len(launcher.by_script("funding.py")) == 1, "a running poller was relaunched"
    assert not any(process.terminated for process in launcher.launched)
    assert "poller_listed" in _events(tmp_path)


def test_an_unreadable_config_changes_nothing(tmp_path: Path) -> None:
    """A half-saved file must never read as an empty list and stop every poller."""
    config = tmp_path / "recorder.yaml"
    _write_config(config, FUNDING_ONLY)
    launcher = FakeLauncher()
    sup = _supervisor(tmp_path, launcher, config)
    sup.reload()
    sup.step(0.0)

    for broken in ("recorder: [unclosed\n", "not a mapping\n", ""):
        config.write_text(broken, encoding="utf-8")
        sup.reload()
        sup.step(1.0)
        assert sup.config_problem is not None
        assert sorted(sup.pollers) == ["funding"]
    config.unlink()
    sup.reload()
    assert sorted(sup.pollers) == ["funding"]
    assert not any(process.terminated for process in launcher.launched)

    _write_config(config, "  pollers:\n    - script: funding.py\n    - script: ../x.py\n")
    sup.reload()
    assert sup.config_problem is not None
    assert sorted(sup.pollers) == ["funding"], "one bad entry stopped a good one"

    _write_config(config, FUNDING_ONLY)
    sup.reload()
    assert sup.config_problem is None
    assert "pollers_config_not_applied" in _events(tmp_path)


def test_a_delisted_poller_is_stopped_and_the_recorder_is_not(tmp_path: Path) -> None:
    config = tmp_path / "recorder.yaml"
    _write_config(config, FUNDING_AND_FEES)
    launcher = FakeLauncher()
    sup = _supervisor(tmp_path, launcher, config)
    sup.reload()
    sup.step(0.0)

    _write_config(config, FUNDING_ONLY)
    sup.reload()
    sup.step(1.0)
    assert sorted(sup.pollers) == ["funding"]
    assert launcher.by_script("fees.py")[0].terminated
    assert not launcher.by_script("record.py")[0].terminated
    assert not launcher.by_script("funding.py")[0].terminated


def test_a_poller_gets_the_config_and_source_but_never_the_archive_out(tmp_path: Path) -> None:
    args = supervise.parse_args(
        ["--config", "c.yaml", "--source-id", "msi", "--out", "E:/raw"]
    )
    spec = supervise.PollerSpec(script="funding.py", args=("--once",))
    command = supervise.poller_command(args, Path("funding.py"), spec)
    assert command[1:] == ["funding.py", "--config", "c.yaml", "--source-id", "msi", "--once"]
    assert "--out" not in command


def test_the_block_shows_one_line_per_poller() -> None:
    from datetime import UTC, datetime

    block = supervise.status_block(
        source_id="msi",
        started=datetime(2026, 9, 19, tzinfo=UTC),
        now=datetime(2026, 9, 19, tzinfo=UTC),
        today_mb=1.0,
        last_write=0.0,
        restarts=0,
        state="recording",
        pollers=[("fees", "running · restarts 0"), ("funding", "waiting · restarts 0")],
    )
    lines = block.split("\n")
    assert len(lines) == 8
    assert lines[6] == "fees       running · restarts 0"
    assert lines[7] == "funding    waiting · restarts 0"


# --------------------------------------------------------------------------- #
# End to end, with real processes
# --------------------------------------------------------------------------- #


def test_the_loop_supervises_real_children_and_picks_up_a_new_poller(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    marks = tmp_path / "marks"
    marks.mkdir()

    def child_script(name: str, body: str) -> None:
        (scripts / name).write_text(
            "import pathlib, sys, time, uuid\n"
            f"pathlib.Path({str(marks)!r}, {name!r} + '.' + uuid.uuid4().hex).write_text('x')\n"
            + body,
            encoding="utf-8",
        )

    child_script("record.py", "time.sleep(60)\n")
    child_script("crashy.py", "sys.exit(1)\n")
    child_script("late.py", "time.sleep(60)\n")

    config = tmp_path / "recorder.yaml"
    _write_config(config, "  pollers:\n    - script: crashy.py\n")

    def list_late() -> None:
        time.sleep(1.5)
        _write_config(config, "  pollers:\n    - script: crashy.py\n    - script: late.py\n")

    writer = threading.Thread(target=list_late)
    writer.start()
    args = supervise.parse_args(
        [
            "--recorder", str(scripts / "record.py"),
            "--config", str(config),
            "--log-dir", str(tmp_path / "logs"),
            "--out", str(tmp_path / "raw"),
            "--poller-dir", str(scripts),
            "--backoff-s", "0.2",
            "--max-backoff-s", "0.4",
            "--refresh-s", "0.05",
            "--reload-s", "0.2",
            "--duration-s", "6",
            "--no-ansi",
        ]
    )
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        assert supervise.supervise(args) == 0
    writer.join()

    def launches(name: str) -> int:
        return len(list(marks.glob(f"{name}.*")))

    assert launches("record.py") == 1, "the recorder was relaunched by a poller change"
    assert launches("crashy.py") >= 3, "a crashing poller was not restarted"
    assert launches("late.py") == 1, "a poller listed mid-run was not started"
    events = _events(tmp_path)
    assert events.count("recorder_launching") == 1
    assert "poller_listed" in events
    assert events[-1] == "supervisor_duration_reached"
    assert list((tmp_path / "logs").glob("crashy__test__*.log")), "the poller had no log of its own"
