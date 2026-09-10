"""`sweep_stale_workspaces` must not delete a workspace another run is using.

This is the defect that spent two phases being called an intermittent native memory
fault. B hypothesised it, the lead reproduced it first try, and it is in
`scripts/verify.py`, which is mine.

**The mechanism.** The old sweeper deleted every `acsoe-verify-*` directory it could,
relying on a docstring's claim that "a directory another verify run is using right now
simply will not delete". That is a POSIX assumption written as a fact about Windows.
Windows refuses to unlink an *open* file — but a SQLite database **between connections
is not open**, and every criterion in `verify.py` seeds, closes and reopens, so it is
unlocked for that whole window. `ignore_errors=True` then guaranteed *partial*
deletion: the call removes what it can and skips the rest.

Two signatures, one bug. Directory gone before the next connection opens gives
`unable to open database file`; directory surviving with its database deleted gives a
fresh empty database from `sqlite3.connect` and then `no such table`.

**Why nobody caught it.** The standing mitigation — re-run the named test in isolation —
passes every time, because in isolation nothing else is sweeping. The mitigation
confirmed the wrong diagnosis on every application. And there were no tests for this
function at all, which is the other half of the answer.

Every test here operates on a fabricated temp root, never the real one.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture
def temp_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the sweeper at a directory of our own, never the machine's real one.

    A test that swept the real temp directory would delete the workspaces of whatever
    else is running — which is the bug, committed by its own regression test.
    """
    root = tmp_path / "fake-temp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(root))
    return root


def make_workspace(root: Path, verify_module: ModuleType, name: str = "console") -> Path:
    """A workspace the way `verify.py` mints them, with a real seeded-looking database."""
    path = root / f"{verify_module.WORKSPACE_PREFIX}{name}"
    path.mkdir()
    db = path / "acsoe.sqlite"
    conn = sqlite3.connect(db)
    try:
        conn.execute("CREATE TABLE equity_snapshots (id INTEGER PRIMARY KEY, equity TEXT)")
        conn.execute("INSERT INTO equity_snapshots (equity) VALUES ('1000.00')")
        conn.commit()
    finally:
        conn.close()
    return path


def set_mtime(path: Path, when: float) -> None:
    """Stamp a whole tree at an absolute instant."""
    for entry in sorted(path.rglob("*"), reverse=True):
        os.utime(entry, (when, when))
    os.utime(path, (when, when))


def backdate(path: Path, seconds: float) -> None:
    """Age a whole tree so it looks like a leftover from a run that finished.

    Relative to **now**, which is what a caller means by "an hour old". Tests reasoning
    about the cutoff itself must use `set_mtime` against `PROCESS_STARTED_AT` instead:
    the cutoff is anchored to when `verify.py` was imported, and in a session lasting
    minutes that is a long way behind `time.time()`. Getting that wrong is what made
    the first version of `test_the_cutoff_is_this_process_rather_than_a_fixed_age` pass
    alone and fail in a full run — an assertion about the clock rather than about the
    code, which is the same shape as a fixture pinned to a literal.
    """
    set_mtime(path, time.time() - seconds)


# --------------------------------------------------------------------------- #
# The regression. This test fails against the code as it stood.
# --------------------------------------------------------------------------- #


def test_a_workspace_this_run_is_using_survives_the_sweep(
    verify_module: ModuleType, temp_root: Path
) -> None:
    """The bug, stated as the property it violated.

    The workspace is freshly created and its database connection is **closed**, which
    is exactly the state every criterion here spends most of its time in: seed, close,
    reopen. The old sweeper deleted it, and the next `sqlite3.connect` reported
    `unable to open database file`.
    """
    workspace = make_workspace(temp_root, verify_module)
    db = workspace / "acsoe.sqlite"
    assert db.is_file()

    removed, _freed = verify_module.sweep_stale_workspaces(report=False)

    assert workspace.is_dir(), "the sweep deleted a workspace belonging to a live run"
    assert db.is_file(), "the sweep deleted a live database out of a surviving directory"
    assert removed == 0

    # And it is still a usable database rather than a fresh empty one, which is the
    # second signature: a deleted file inside a surviving directory makes
    # `sqlite3.connect` create an empty database and the next statement say
    # `no such table`.
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT equity FROM equity_snapshots").fetchone() == ("1000.00",)
    finally:
        conn.close()


def test_a_workspace_being_written_to_now_survives_even_if_it_was_created_long_ago(
    verify_module: ModuleType, temp_root: Path
) -> None:
    """The case a naive mtime check gets wrong, and it is not a corner.

    A directory's mtime changes when an entry is added to or removed from it — **not**
    when a file inside it is written. So a long-running run's workspace carries the
    mtime of the moment it was created, and reading only that would leave the bug
    exactly where it was for any run outlasting the safety margin. `toolchain_green`
    alone takes ninety seconds.

    Here the directory is aged an hour and the database is then touched now.
    """
    workspace = make_workspace(temp_root, verify_module)
    backdate(workspace, seconds=3600)
    db = workspace / "acsoe.sqlite"
    now = time.time()
    os.utime(db, (now, now))

    removed, _freed = verify_module.sweep_stale_workspaces(report=False)

    assert workspace.is_dir(), (
        "the sweep read only the directory's mtime, so a run that has been going longer "
        "than the safety margin is deleted underneath itself"
    )
    assert db.is_file()
    assert removed == 0


# --------------------------------------------------------------------------- #
# The positive half. A sweeper that has stopped sweeping is the same defect.
# --------------------------------------------------------------------------- #


def test_a_leftover_from_a_finished_run_is_still_removed(
    verify_module: ModuleType, temp_root: Path
) -> None:
    """Without this the fix is indistinguishable from deleting the function.

    `remove_workspace`'s own docstring records why the sweeper exists: a connection the
    criteria never closed leaked roughly 450MB per run, silently, until the disk was
    full. Making the sweep safe must not make it inert.
    """
    stale = make_workspace(temp_root, verify_module, name="stale")
    backdate(stale, seconds=3600)

    removed, freed = verify_module.sweep_stale_workspaces(report=False)

    assert not stale.exists(), "a leftover from a run that finished an hour ago was kept"
    assert removed == 1
    assert freed > 0


def test_the_live_one_survives_while_the_stale_one_beside_it_goes(
    verify_module: ModuleType, temp_root: Path
) -> None:
    """Both halves in one sweep, because each alone is satisfiable by a broken sweeper:
    delete everything passes the second test, delete nothing passes the first."""
    live = make_workspace(temp_root, verify_module, name="live")
    stale = make_workspace(temp_root, verify_module, name="stale")
    backdate(stale, seconds=3600)

    removed, _freed = verify_module.sweep_stale_workspaces(report=False)

    assert live.is_dir()
    assert (live / "acsoe.sqlite").is_file()
    assert not stale.exists()
    assert removed == 1


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #


def test_nothing_outside_the_prefix_is_touched(
    verify_module: ModuleType, temp_root: Path
) -> None:
    """`pytest-of-*` belongs to pytest and the rest of the temp directory belongs to
    the machine. Age them past the cutoff so only the prefix check can save them."""
    others = []
    for name in ("pytest-of-saad2", "tmpabcdef", "acsoe-something-else"):
        directory = temp_root / name
        directory.mkdir()
        (directory / "payload.txt").write_text("keep me", encoding="utf-8")
        backdate(directory, seconds=3600)
        others.append(directory)

    verify_module.sweep_stale_workspaces(report=False)

    for directory in others:
        assert directory.is_dir(), f"{directory.name} is not this script's to delete"


def test_a_file_sharing_the_prefix_is_not_removed(
    verify_module: ModuleType, temp_root: Path
) -> None:
    """The glob matches names, and only directories are workspaces."""
    stray = temp_root / f"{verify_module.WORKSPACE_PREFIX}notes.txt"
    stray.write_text("not a workspace", encoding="utf-8")
    backdate(stray.parent, seconds=0)
    os.utime(stray, (time.time() - 3600, time.time() - 3600))

    verify_module.sweep_stale_workspaces(report=False)

    assert stray.is_file()


# --------------------------------------------------------------------------- #
# The margin, and the direction it errs in
# --------------------------------------------------------------------------- #


def test_a_directory_inside_the_safety_margin_is_kept(
    verify_module: ModuleType, temp_root: Path
) -> None:
    """Filesystem and system clocks do not agree to better than a second or two on
    Windows, and coarser on FAT-derived filesystems. The margin is a minute because the
    two errors are not symmetric: keeping a leftover one run too long costs disk, and
    deleting a live database costs a wrong verdict on a trading gate.

    Aged past this process's start but well inside the margin, so only the margin can
    save it.
    """
    # Stamped *between* the cutoff and this process's start, which is the only band the
    # margin is responsible for. Ageing it relative to `time.time()` instead would put
    # it after `PROCESS_STARTED_AT` in any session lasting more than a moment, and it
    # would then survive because it is newer than this process — passing without the
    # margin being involved at all. That is the shape this whole phase has been about,
    # so it is worth avoiding in the test written to prove the fix.
    margin = verify_module.SWEEP_SAFETY_MARGIN_S
    started = verify_module.PROCESS_STARTED_AT

    # Both sides of the margin in one sweep, and that is not tidiness. Asserting only
    # the kept half is satisfiable by a margin of zero: the fixture is expressed in
    # terms of the margin, so shrinking the margin shrinks the fixture with it and the
    # directory lands exactly on `PROCESS_STARTED_AT`, which is kept either way. The
    # test would pass while the thing it names had been deleted. Pairing it with a
    # directory *outside* the margin is what makes the number load-bearing.
    inside = make_workspace(temp_root, verify_module, name="inside")
    outside = make_workspace(temp_root, verify_module, name="outside")
    set_mtime(inside, started - margin / 2)
    set_mtime(outside, started - margin * 2)

    removed, _freed = verify_module.sweep_stale_workspaces(report=False)

    assert inside.is_dir(), "a directory inside the clock-skew margin was deleted"
    assert not outside.exists(), "the margin is swallowing directories it should not protect"
    assert removed == 1


def test_the_cutoff_is_this_process_rather_than_a_fixed_age(
    verify_module: ModuleType, temp_root: Path
) -> None:
    """The ordering is the whole argument, so it is worth asserting directly.

    A run that has not finished has written to its workspace since this process
    started, so its directory cannot predate this process. That is why no lock file or
    inter-process protocol is needed — and why the constant is a *process start time*
    rather than "anything older than an hour", which would be a guess about how long a
    run takes.
    """
    assert time.time() >= verify_module.PROCESS_STARTED_AT
    assert verify_module.SWEEP_SAFETY_MARGIN_S > 0

    cutoff = verify_module.PROCESS_STARTED_AT - verify_module.SWEEP_SAFETY_MARGIN_S

    # Stamped against the cutoff itself, not against `time.time()`. `PROCESS_STARTED_AT`
    # is captured when `verify.py` is imported — session start for the shared fixture —
    # so in a run lasting minutes "ninety seconds ago" is comfortably *newer* than the
    # cutoff, and the first version of this test asserted the opposite. It passed alone
    # and failed in a full suite, which is the tell.
    workspace = make_workspace(temp_root, verify_module)
    set_mtime(workspace, cutoff - 30)
    assert verify_module._predates_this_run(workspace, cutoff)

    now = time.time()
    os.utime(workspace / "acsoe.sqlite", (now, now))
    assert not verify_module._predates_this_run(workspace, cutoff)


def test_an_unreadable_entry_is_left_alone(
    verify_module: ModuleType, temp_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"I cannot tell whose this is" must answer no, not yes.

    The old code's failure was treating "try it and see" as a safety check. An entry
    that will not stat is one we know nothing about, and the safe answer to "may I
    delete this" is never the optimistic one.
    """
    workspace = make_workspace(temp_root, verify_module)
    backdate(workspace, seconds=3600)

    def refuse(self: Path, *args: object, **kwargs: object) -> os.stat_result:
        raise OSError("stat refused")

    # Undone before the assertions: leaving it patched would break the test's own
    # `is_dir()` and report a failure that says nothing about the sweeper.
    with monkeypatch.context() as blind:
        blind.setattr(Path, "stat", refuse)
        removed, _freed = verify_module.sweep_stale_workspaces(report=False)

    assert workspace.is_dir()
    assert removed == 0


def test_one_unreadable_entry_does_not_stop_the_rest_of_the_sweep(
    verify_module: ModuleType, temp_root: Path
) -> None:
    """The suppression used to wrap the loop rather than the body.

    So a single leftover that would not stat aborted the sweep, and every workspace
    after it alphabetically was kept forever — silently reintroducing the 450MB-per-run
    leak this function exists to prevent, through its own error handling. Two stale
    workspaces, the first unreadable: the second must still go.
    """
    first = make_workspace(temp_root, verify_module, name="aaa-unreadable")
    second = make_workspace(temp_root, verify_module, name="zzz-stale")
    backdate(first, seconds=3600)
    backdate(second, seconds=3600)

    real_stat = Path.stat

    def refuse_the_first(self: Path, *args: object, **kwargs: object) -> os.stat_result:
        if self == first or first in self.parents:
            raise OSError("stat refused")
        return real_stat(self, *args, **kwargs)

    with pytest.MonkeyPatch.context() as blind:
        blind.setattr(Path, "stat", refuse_the_first)
        removed, _freed = verify_module.sweep_stale_workspaces(report=False)

    assert not second.exists(), (
        "an unreadable entry earlier in the sort order stopped the sweep reaching this one"
    )
    assert removed == 1
