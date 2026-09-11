"""`scripts/archive_merge.py` — parse, never overwrite, and report overlaps.

The third of those is the one worth writing a test for. Two sources covering the
same hour is **information**: two independent observations of one market, whose
disagreement measures what a single recorder misses. A merger that quietly picked
one would destroy that and nothing would report it, because the surviving file is
perfectly valid. So the test asserts the overlap is *found and named with its
span*, not merely that both files survive.

The overlap assertion is built from spans that do not share a calendar day
boundary — one source's file starting mid-morning inside another's — because a
day-level implementation passes a same-day test while being wrong about every
partial overlap, which is the shape a real second recorder produces.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "archive_merge.py"


@pytest.fixture(scope="module")
def merger() -> ModuleType:
    spec = importlib.util.spec_from_file_location("acsoe_archive_merge_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def raw_line(stamp: str) -> str:
    return (
        f'{{"v":1,"kind":"tick","pair":"BTC/USD","channel":"book","ts_exchange":null,'
        f'"ts_recv":"{stamp}","payload":{{"channel":"book"}}}}\n'
    )


def summary_line(minute: str) -> str:
    return (
        f'{{"v":1,"kind":"summary","pair":"BTC/USD","minute":"{minute}",'
        f'"spread_bps":[1.0,2.0,3.0],"depth_bid_bps":null,"depth_ask_bps":null,'
        f'"mid":100.0,"updates":1,"samples":1,"depth_samples":0,"trades":0,'
        f'"volume":0.0,"quote_volume":0.0}}\n'
    )


def write(directory: Path, name: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def span_file(directory: Path, name: str, first: str, last: str) -> Path:
    return write(directory, name, raw_line(first) + raw_line(last))


# --------------------------------------------------------------------------- #
# Every file must parse
# --------------------------------------------------------------------------- #


def test_a_clean_file_parses(merger: ModuleType, tmp_path: Path) -> None:
    path = span_file(tmp_path, "kraken_v2__msi__2026-09-11.jsonl", *_two())
    ok, count, problem = merger.check_parses(path)
    assert (ok, count, problem) == (True, 2, None)


def test_a_corrupt_line_in_the_middle_fails_the_file(merger: ModuleType, tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "kraken_v2__msi__2026-09-11.jsonl",
        raw_line("2026-09-11T00:00:00.000000Z") + "{not json\n" + raw_line("2026-09-11T01:00:00.000000Z"),
    )
    ok, _count, problem = merger.check_parses(path)
    assert not ok
    assert "line 2 is not JSON" in problem


def test_a_line_that_is_not_an_object_fails_the_file(merger: ModuleType, tmp_path: Path) -> None:
    path = write(tmp_path, "kraken_v2__msi__2026-09-11.jsonl", "[1, 2, 3]\n")
    ok, _count, problem = merger.check_parses(path)
    assert not ok
    assert "not a JSON object" in problem


def test_a_truncated_final_line_is_tolerated_and_named(merger: ModuleType, tmp_path: Path) -> None:
    """The shape a forced kill leaves, and the archive already contains it.

    Refusing it would refuse real data, and repairing it is what invariant 11
    forbids. It is merged as is, and said out loud.
    """
    path = write(
        tmp_path,
        "kraken_v2__msi__2026-09-11.jsonl",
        raw_line("2026-09-11T00:00:00.000000Z") + '{"v":1,"kind":"tick","pair":"BTC',
    )
    ok, _count, problem = merger.check_parses(path)
    assert ok
    assert "truncated" in problem


def test_an_empty_file_is_refused(merger: ModuleType, tmp_path: Path) -> None:
    path = write(tmp_path, "kraken_v2__msi__2026-09-11.jsonl", "")
    ok, _count, problem = merger.check_parses(path)
    assert not ok
    assert "empty" in problem


def test_a_refused_file_is_not_merged(merger: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "foreign"
    dest = tmp_path / "main"
    dest.mkdir()
    write(source, "kraken_v2__vps__2026-09-11.jsonl", "{not json\n")
    span_file(source, "kraken_v2__vps__2026-09-12.jsonl", *_two("2026-09-12"))

    code = merger.run(
        merger.parse_args(["--source", str(source), "--dest", str(dest)])
    )
    assert code == 1, "a refused file must make the run report failure"
    assert [path.name for path in dest.glob("*.jsonl")] == ["kraken_v2__vps__2026-09-12.jsonl"]


# --------------------------------------------------------------------------- #
# Never overwrite
# --------------------------------------------------------------------------- #


def test_an_existing_name_is_skipped_not_overwritten(merger: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "foreign"
    dest = tmp_path / "main"
    span_file(source, "kraken_v2__msi__2026-09-11.jsonl", *_two())
    write(dest, "kraken_v2__msi__2026-09-11.jsonl", raw_line("2026-09-11T05:00:00.000000Z"))
    before = (dest / "kraken_v2__msi__2026-09-11.jsonl").read_bytes()

    merger.run(merger.parse_args(["--source", str(source), "--dest", str(dest)]))

    assert (dest / "kraken_v2__msi__2026-09-11.jsonl").read_bytes() == before
    assert (source / "kraken_v2__msi__2026-09-11.jsonl").is_file(), "the original was consumed"


def test_the_foreign_originals_are_never_deleted(merger: ModuleType, tmp_path: Path) -> None:
    """This script copies. Deleting the only other copy of an archive is
    `archive_move.py`'s job and it verifies before it does."""
    source = tmp_path / "foreign"
    dest = tmp_path / "main"
    dest.mkdir()
    original = span_file(source, "kraken_v2__vps__2026-09-11.jsonl", *_two())
    body = original.read_bytes()

    merger.run(merger.parse_args(["--source", str(source), "--dest", str(dest)]))

    assert original.read_bytes() == body
    assert (dest / original.name).read_bytes() == body


def test_a_copy_that_does_not_verify_is_not_left_under_a_real_name(
    merger: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "foreign"
    dest = tmp_path / "main"
    dest.mkdir()
    original = span_file(source, "kraken_v2__vps__2026-09-11.jsonl", *_two())

    monkeypatch.setattr(merger, "digest", lambda _path: "0" * 64)
    with pytest.raises(merger.MergeRefusedError):
        merger.copy_verified(original, dest / original.name)
    assert list(dest.iterdir()) == []


# --------------------------------------------------------------------------- #
# Overlapping coverage is reported, not resolved
# --------------------------------------------------------------------------- #


def _two(day: str = "2026-09-11") -> tuple[str, str]:
    return f"{day}T00:00:00.000000Z", f"{day}T23:00:00.000000Z"


def _coverage(merger: ModuleType, source_id: str, start: str, end: str) -> object:
    return merger.Coverage(
        path=Path(f"{source_id}.jsonl"),
        name=f"kraken_v2__{source_id}__2026-09-11.jsonl",
        source_id=source_id,
        day=None,
        start=datetime.fromisoformat(start).replace(tzinfo=UTC),
        end=datetime.fromisoformat(end).replace(tzinfo=UTC),
    )


def test_a_partial_overlap_between_two_sources_is_found(merger: ModuleType) -> None:
    """Not a same-day test: the spans start and end at different hours.

    A day-level implementation would pass a same-day assertion while being wrong
    about every real partial overlap, which is the shape two recorders actually
    produce.
    """
    left = _coverage(merger, "msi", "2026-09-11T00:00:00", "2026-09-11T11:00:00")
    right = _coverage(merger, "vps", "2026-09-11T06:00:00", "2026-09-11T20:00:00")
    found = merger.overlaps([left, right])
    assert len(found) == 1
    _a, _b, start, end = found[0]
    assert (start.hour, end.hour) == (6, 11)


def test_adjacent_spans_do_not_overlap(merger: ModuleType) -> None:
    """One source stopping exactly when another starts is a handover, not an
    overlap, and reporting it would train the operator to ignore the report."""
    left = _coverage(merger, "msi", "2026-09-11T00:00:00", "2026-09-11T12:00:00")
    right = _coverage(merger, "vps", "2026-09-11T12:00:00", "2026-09-11T23:00:00")
    assert merger.overlaps([left, right]) == []


def test_two_files_from_one_source_are_not_reported_as_an_overlap(merger: ModuleType) -> None:
    left = _coverage(merger, "msi", "2026-09-11T00:00:00", "2026-09-11T11:00:00")
    right = _coverage(merger, "msi", "2026-09-11T06:00:00", "2026-09-11T20:00:00")
    assert merger.overlaps([left, right]) == []


def test_an_overlap_is_reported_and_both_files_are_kept(
    merger: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end: the span is named in the output and neither file is dropped."""
    source = tmp_path / "foreign"
    dest = tmp_path / "main"
    span_file(
        dest,
        "kraken_v2__msi__2026-09-11.jsonl",
        "2026-09-11T00:00:00.000000Z",
        "2026-09-11T11:00:00.000000Z",
    )
    span_file(
        source,
        "kraken_v2__vps__2026-09-11.jsonl",
        "2026-09-11T06:00:00.000000Z",
        "2026-09-11T20:00:00.000000Z",
    )

    code = merger.run(merger.parse_args(["--source", str(source), "--dest", str(dest)]))
    out = capsys.readouterr().out

    assert code == 0
    assert "1 overlapping period(s)" in out
    assert "2026-09-11T06:00:00Z -> 2026-09-11T11:00:00Z" in out
    assert "msi and vps" in out
    assert len(list(dest.glob("*.jsonl"))) == 2, "the merger dropped one of the two sources"


def test_no_overlap_says_so(
    merger: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "foreign"
    dest = tmp_path / "main"
    span_file(dest, "kraken_v2__msi__2026-09-11.jsonl", *_two("2026-09-11"))
    span_file(source, "kraken_v2__vps__2026-09-13.jsonl", *_two("2026-09-13"))

    merger.run(merger.parse_args(["--source", str(source), "--dest", str(dest)]))
    assert "no overlapping coverage" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Spans
# --------------------------------------------------------------------------- #


def test_the_span_comes_from_the_first_and_last_line(merger: ModuleType, tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "kraken_v2__msi__2026-09-11.jsonl",
        "".join(raw_line(f"2026-09-11T{hour:02d}:00:00.000000Z") for hour in range(24)),
    )
    first, last = merger.read_span(path)
    assert (first.hour, last.hour) == (0, 23)


def test_a_summary_row_is_dated_by_its_minute(merger: ModuleType, tmp_path: Path) -> None:
    """Tier 2 rows carry no `ts_recv` at all, and this script merges that archive
    too."""
    path = write(
        tmp_path,
        "summary__msi__2026-09-11.jsonl",
        summary_line("2026-09-11T00:00:00Z") + summary_line("2026-09-11T18:00:00Z"),
    )
    first, last = merger.read_span(path)
    assert (first.hour, last.hour) == (0, 18)


def test_a_file_whose_lines_have_no_times_falls_back_to_its_filename(
    merger: ModuleType, tmp_path: Path
) -> None:
    coverage = merger.Coverage(
        path=tmp_path / "x.jsonl",
        name="kraken_v2__msi__2026-09-11.jsonl",
        source_id="msi",
        day=datetime(2026, 9, 11, tzinfo=UTC).date(),
        start=None,
        end=None,
    )
    span = coverage.span()
    assert span is not None
    assert span[0].isoformat().startswith("2026-09-11T00:00:00")


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_an_absent_destination_archive_is_refused(merger: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "foreign"
    span_file(source, "kraken_v2__vps__2026-09-11.jsonl", *_two())
    with pytest.raises(merger.MergeRefusedError, match="does not exist"):
        merger.run(
            merger.parse_args(["--source", str(source), "--dest", str(tmp_path / "absent")])
        )


def test_merging_a_directory_into_itself_is_refused(merger: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "foreign"
    span_file(source, "kraken_v2__vps__2026-09-11.jsonl", *_two())
    with pytest.raises(merger.MergeRefusedError, match="same directory"):
        merger.run(merger.parse_args(["--source", str(source), "--dest", str(source)]))


def test_a_dry_run_copies_nothing(merger: ModuleType, tmp_path: Path) -> None:
    source = tmp_path / "foreign"
    dest = tmp_path / "main"
    dest.mkdir()
    span_file(source, "kraken_v2__vps__2026-09-11.jsonl", *_two())

    merger.run(
        merger.parse_args(["--source", str(source), "--dest", str(dest), "--dry-run"])
    )
    assert list(dest.glob("*.jsonl")) == []
