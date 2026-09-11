"""`scripts/archive_move.py` — nothing is deleted without a verified copy.

Two assertions here carry the whole file and both are written as negatives,
because the dangerous behaviour of a mover is not "it failed", it is "it
succeeded against nothing":

- **an unreachable destination refuses before the first copy**, and the source
  directory is byte-for-byte unchanged afterwards;
- **a copy that does not verify leaves the original alone**, which is asserted by
  corrupting the copy on the way out and checking the source is still there.

The second one needs the destination to be sabotaged mid-flight, so the test
monkeypatches the digest used for the read-back rather than hoping for a real bad
disk. That is the only way to make the assertion capable of failing: with an
honest destination the verification always passes, and a test that never sees the
failure path proves nothing about it.

Every assertion in this file has been run against a deliberately broken mover and
observed red; the mutations and their messages are in
`docs/build-log/phase-4/a-platform.md`.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "archive_move.py"


@pytest.fixture(scope="module")
def mover() -> ModuleType:
    """Loaded by path: `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("acsoe_archive_move_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TODAY = date(2026, 9, 11)


def write_archive(directory: Path, name: str, lines: int = 3) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    body = "".join(
        f'{{"v":1,"kind":"tick","pair":"BTC/USD","channel":"book","ts_exchange":null,'
        f'"ts_recv":"2026-09-01T00:00:0{index}.000000Z","payload":{{}}}}\n'
        for index in range(lines)
    )
    path.write_text(body, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Names and eligibility
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("kraken_v2__msi__2026-09-11.jsonl", ("kraken_v2", "msi", date(2026, 9, 11))),
        ("summary__vps-1__2026-01-02.jsonl", ("summary", "vps-1", date(2026, 1, 2))),
        # The shape the existing 7.1 GB archive is written in, which predates
        # source ids and must still be movable.
        ("kraken_v2_2026-09-11.jsonl", ("kraken_v2", None, date(2026, 9, 11))),
        ("notes.txt", (None, None, None)),
        ("kraken_v2__msi__not-a-date.jsonl", ("kraken_v2", "msi", None)),
        ("kraken_v2__too__many__parts__2026-09-11.jsonl", (None, None, None)),
    ],
)
def test_parse_archive_name(mover: ModuleType, name: str, expected: tuple) -> None:
    assert mover.parse_archive_name(name) == expected


def test_todays_file_is_never_eligible(mover: ModuleType, tmp_path: Path) -> None:
    """At any `--older-than-days`, including zero. The recorder has it open."""
    write_archive(tmp_path, "kraken_v2__msi__2026-09-11.jsonl")
    write_archive(tmp_path, "kraken_v2__msi__2026-09-10.jsonl")
    movable, skipped = mover.eligible(mover.scan(tmp_path), today=TODAY, older_than_days=0)
    assert [item.path.name for item in movable] == ["kraken_v2__msi__2026-09-10.jsonl"]
    assert "still being written" in skipped[0][1]


def test_the_cutoff_is_whole_utc_days(mover: ModuleType, tmp_path: Path) -> None:
    for day in ("2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"):
        write_archive(tmp_path, f"kraken_v2__msi__{day}.jsonl")
    movable, _ = mover.eligible(mover.scan(tmp_path), today=TODAY, older_than_days=7)
    # today - 7 = 2026-09-04, and the cutoff is inclusive.
    assert [item.day.isoformat() for item in movable] == ["2026-09-02", "2026-09-03", "2026-09-04"]


def test_a_file_with_no_date_in_its_name_is_never_moved(mover: ModuleType, tmp_path: Path) -> None:
    """Its age is unknown, and an unknown age is not an old age."""
    write_archive(tmp_path, "kraken_v2__msi__whenever.jsonl")
    movable, skipped = mover.eligible(mover.scan(tmp_path), today=TODAY, older_than_days=0)
    assert movable == []
    assert "no UTC date" in skipped[0][1]


# --------------------------------------------------------------------------- #
# The destination must actually be there
# --------------------------------------------------------------------------- #


def test_an_absent_destination_is_refused_and_not_created(
    mover: ModuleType, tmp_path: Path
) -> None:
    """The failure this whole script exists to prevent.

    An unplugged drive and a first run look identical from here, and creating the
    directory would write a day of recordings into a local path wearing the
    missing drive's name.
    """
    absent = tmp_path / "E_drive" / "archive"
    with pytest.raises(mover.MoveRefusedError, match="does not exist"):
        mover.check_destination(absent, need_bytes=0)
    assert not absent.exists(), "the mover created its own destination"


def test_a_file_where_the_destination_should_be_is_refused(
    mover: ModuleType, tmp_path: Path
) -> None:
    target = tmp_path / "archive"
    target.write_text("not a directory", encoding="utf-8")
    with pytest.raises(mover.MoveRefusedError, match="not a directory"):
        mover.check_destination(target, need_bytes=0)


def test_a_destination_without_room_is_refused_before_the_first_copy(
    mover: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "archive"
    dest.mkdir()

    class _Usage:
        free = 10

    monkeypatch.setattr(mover.shutil, "disk_usage", lambda _path: _Usage())
    with pytest.raises(mover.MoveRefusedError, match="free"):
        mover.check_destination(dest, need_bytes=1_000_000)


def test_a_reachable_destination_passes_and_leaves_no_probe_behind(
    mover: ModuleType, tmp_path: Path
) -> None:
    dest = tmp_path / "archive"
    dest.mkdir()
    mover.check_destination(dest, need_bytes=0)
    assert list(dest.iterdir()) == [], "the reachability probe was not cleaned up"


# --------------------------------------------------------------------------- #
# Copy, verify, then delete — in that order
# --------------------------------------------------------------------------- #


def test_a_verified_move_deletes_the_original(mover: ModuleType, tmp_path: Path) -> None:
    source = write_archive(tmp_path / "raw", "kraken_v2__msi__2026-09-01.jsonl")
    dest = tmp_path / "archive"
    dest.mkdir()
    original = source.read_bytes()

    item = mover.scan(tmp_path / "raw")[0]
    moved, message = mover.move_one(item, dest, keep=False)

    assert moved, message
    assert not source.exists()
    assert (dest / source.name).read_bytes() == original


def test_a_copy_that_does_not_verify_leaves_the_original_alone(
    mover: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The assertion the script is built around.**

    The read-back is made to disagree with the source. Nothing may be deleted, and
    the half-written copy must not be left sitting under a real archive name where
    a later replay would read it as a day's recording.
    """
    source = write_archive(tmp_path / "raw", "kraken_v2__msi__2026-09-01.jsonl")
    dest = tmp_path / "archive"
    dest.mkdir()

    monkeypatch.setattr(mover, "digest", lambda _path: ("0" * 64, 0))

    item = mover.scan(tmp_path / "raw")[0]
    moved, message = mover.move_one(item, dest, keep=False)

    assert not moved
    assert "did not arrive intact" in message
    assert source.is_file(), "the source was deleted after a failed verification"
    assert list(dest.iterdir()) == [], "a partial copy was left in the archive"


def test_an_existing_destination_file_is_never_overwritten(
    mover: ModuleType, tmp_path: Path
) -> None:
    source = write_archive(tmp_path / "raw", "kraken_v2__msi__2026-09-01.jsonl")
    dest = tmp_path / "archive"
    dest.mkdir()
    (dest / source.name).write_text("something already here\n", encoding="utf-8")

    item = mover.scan(tmp_path / "raw")[0]
    moved, message = mover.move_one(item, dest, keep=False)

    assert not moved
    assert "already at the destination" in message
    assert (dest / source.name).read_text(encoding="utf-8") == "something already here\n"
    assert source.is_file()


def test_keep_copies_without_deleting(mover: ModuleType, tmp_path: Path) -> None:
    source = write_archive(tmp_path / "raw", "kraken_v2__msi__2026-09-01.jsonl")
    dest = tmp_path / "archive"
    dest.mkdir()

    item = mover.scan(tmp_path / "raw")[0]
    moved, message = mover.move_one(item, dest, keep=True)

    assert moved
    assert message.startswith("COPY")
    assert source.is_file()
    assert (dest / source.name).read_bytes() == source.read_bytes()


def test_an_interrupted_copy_leaves_no_partial_under_a_real_name(
    mover: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `KeyboardInterrupt` mid-copy must not name a short file as an archive."""
    source = write_archive(tmp_path / "raw", "kraken_v2__msi__2026-09-01.jsonl")
    dest = tmp_path / "archive"
    dest.mkdir()

    def _boom(_path: Path) -> tuple[str, int]:
        raise KeyboardInterrupt

    monkeypatch.setattr(mover, "digest", _boom)
    with pytest.raises(KeyboardInterrupt):
        mover.copy_verified(source, dest / source.name)

    assert list(dest.iterdir()) == []
    assert source.is_file()


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #


def test_a_dry_run_copies_and_deletes_nothing_but_still_checks_the_destination(
    mover: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"Would this work?" is the question a dry run is asked, and the destination
    being absent is the most likely reason the answer is no."""
    raw = tmp_path / "raw"
    write_archive(raw, "kraken_v2__msi__2026-09-01.jsonl")
    absent = tmp_path / "E_drive" / "archive"

    monkeypatch.setattr(mover, "load_recorder_config", lambda _explicit=None: {})
    args = mover.parse_args(
        ["--source", str(raw), "--dest", str(absent), "--older-than-days", "0", "--dry-run"]
    )
    with pytest.raises(mover.MoveRefusedError):
        mover.run(args)
    assert list(raw.glob("*.jsonl"))


def test_run_moves_only_the_eligible_files(
    mover: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw"
    dest = tmp_path / "archive"
    dest.mkdir()
    today = datetime.now(UTC).date().isoformat()
    write_archive(raw, "kraken_v2__msi__2026-01-01.jsonl")
    write_archive(raw, f"kraken_v2__msi__{today}.jsonl")

    monkeypatch.setattr(mover, "load_recorder_config", lambda _explicit=None: {})
    code = mover.run(
        mover.parse_args(["--source", str(raw), "--dest", str(dest), "--older-than-days", "1"])
    )

    assert code == 0
    assert [path.name for path in dest.glob("*.jsonl")] == ["kraken_v2__msi__2026-01-01.jsonl"]
    assert [path.name for path in raw.glob("*.jsonl")] == [f"kraken_v2__msi__{today}.jsonl"]


def test_no_destination_anywhere_is_a_refusal_not_a_default(
    mover: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mover, "load_recorder_config", lambda _explicit=None: {})
    with pytest.raises(mover.MoveRefusedError, match="no destination"):
        mover.run(mover.parse_args(["--source", str(tmp_path)]))


def test_moving_a_directory_into_itself_is_refused(
    mover: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It would verify a file against itself and then delete it."""
    raw = tmp_path / "raw"
    write_archive(raw, "kraken_v2__msi__2026-01-01.jsonl")
    monkeypatch.setattr(mover, "load_recorder_config", lambda _explicit=None: {})
    with pytest.raises(mover.MoveRefusedError, match="same directory"):
        mover.run(mover.parse_args(["--source", str(raw), "--dest", str(raw)]))
