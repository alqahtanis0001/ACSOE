"""Spec 30 — the Kraken OHLCVT archive loader.

**The most important assertion in this file is the negative one.** A loader that
counted gaps correctly *and* emitted filled rows would satisfy every gap test here and
still poison Phase 4's triple-barrier labels, because a synthesised candle at a price
that never traded invents a barrier touch that never happened. So
`test_no_timestamp_in_the_output_was_absent_from_the_input` is written separately from
the gap count, and it is the one to keep if anything ever has to go.

The fabricated archives use holes of **different sizes** on purpose: a loader that
reported the number of missing *bars* rather than the number of *gaps* reports a
different number and is caught.
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

import pytest

from acsoe.research.historical import (
    ArchiveError,
    ArchiveReport,
    bucket_label,
    gap_runs,
    load_archive,
    read_archive_rows,
)

INTERVAL = 900
BASE = 1_700_000_000
MODULE = Path(__file__).resolve().parents[2] / "src" / "acsoe" / "research" / "historical.py"


def write_archive(path: Path, *, bars: int = 48, holes: tuple[tuple[int, int], ...] = ()) -> list[int]:
    """A Kraken OHLCVT CSV: `ts,open,high,low,close,volume,trades`, no header."""
    skipped: set[int] = set()
    for start, length in holes:
        skipped.update(range(start, start + length))
    lines: list[str] = []
    timestamps: list[int] = []
    for index in range(bars):
        if index in skipped:
            continue
        ts = BASE + index * INTERVAL
        timestamps.append(ts)
        price = 100 + index
        lines.append(f"{ts},{price}.0,{price}.5,{price}.0,{price}.2,1.5,7")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return timestamps


# --------------------------------------------------------------------------- #
# Gaps: counted as runs, never as bars
# --------------------------------------------------------------------------- #


def test_three_holes_of_different_sizes_report_exactly_three_gaps(tmp_path: Path) -> None:
    """Holes of 1, 2 and 4 bars. A loader counting missing *bars* reports 7."""
    archive = tmp_path / "XBTUSD_15.csv"
    timestamps = write_archive(archive, holes=((10, 1), (20, 2), (33, 4)))
    report = load_archive(archive, interval_s=INTERVAL)

    assert report.gap_count == 3
    assert report.missing_bars == 7
    assert report.row_count == len(timestamps)
    assert report.largest_gap_bars == 4
    assert report.duration_buckets == {"1 bar": 1, "2-4 bars": 2}


def test_an_archive_with_no_holes_reports_no_gaps(tmp_path: Path) -> None:
    archive = tmp_path / "XBTUSD_15.csv"
    timestamps = write_archive(archive)
    report = load_archive(archive, interval_s=INTERVAL)
    assert report.gap_count == 0
    assert report.missing_bars == 0
    assert report.largest_gap is None
    assert report.expected_bars == len(timestamps)


def test_gaps_are_bounded_by_the_data_rather_than_extrapolated(tmp_path: Path) -> None:
    """A bar before the archive starts or after it ends is outside the range, not
    missing."""
    archive = tmp_path / "XBTUSD_15.csv"
    write_archive(archive, bars=5)
    report = load_archive(archive, interval_s=INTERVAL)
    assert report.gap_count == 0
    assert report.first_ts == BASE
    assert report.last_ts == BASE + 4 * INTERVAL


def test_a_single_run_is_one_gap_however_long(tmp_path: Path) -> None:
    archive = tmp_path / "XBTUSD_15.csv"
    write_archive(archive, bars=200, holes=((10, 100),))
    report = load_archive(archive, interval_s=INTERVAL)
    assert report.gap_count == 1
    assert report.missing_bars == 100
    assert report.duration_buckets == {"97+ bars": 1}


def test_gap_runs_are_maximal(tmp_path: Path) -> None:
    present = [BASE, BASE + INTERVAL, BASE + 5 * INTERVAL]
    runs = gap_runs(present, interval_s=INTERVAL)
    assert len(runs) == 1
    assert runs[0].bars == 3
    assert runs[0].start == BASE + 2 * INTERVAL
    assert runs[0].end == BASE + 4 * INTERVAL


@pytest.mark.parametrize(
    ("bars", "label"),
    [(1, "1 bar"), (2, "2-4 bars"), (4, "2-4 bars"), (5, "5-16 bars"), (500, "97+ bars")],
)
def test_bucket_boundaries(bars: int, label: str) -> None:
    assert bucket_label(bars) == label


# --------------------------------------------------------------------------- #
# Nothing is ever invented
# --------------------------------------------------------------------------- #


def test_no_timestamp_in_the_output_was_absent_from_the_input(tmp_path: Path) -> None:
    """Separate from the gap count, and deliberately so.

    Counting gaps correctly while also emitting filled rows would pass every other
    assertion in this file. A synthesised candle at a price that never traded invents a
    barrier touch that never happened, and Phase 4 would label that fabricated outcome
    as real. It is invisible to any check that only asks whether the series is
    continuous.
    """
    archive = tmp_path / "XBTUSD_15.csv"
    timestamps = write_archive(archive, holes=((10, 1), (20, 2), (33, 4)))
    report = load_archive(archive, interval_s=INTERVAL)

    assert set(report.timestamps) - set(timestamps) == set()
    assert list(report.timestamps) == timestamps
    assert len(report.timestamps) == report.row_count


def test_the_series_is_left_discontinuous_on_purpose(tmp_path: Path) -> None:
    """The positive statement of the same thing: after loading, consecutive output
    timestamps are *not* all one interval apart, and that is correct."""
    archive = tmp_path / "XBTUSD_15.csv"
    write_archive(archive, holes=((10, 1),))
    report = load_archive(archive, interval_s=INTERVAL)
    steps = {second - first for first, second in itertools.pairwise(report.timestamps)}
    assert steps == {INTERVAL, 2 * INTERVAL}


def test_the_loader_offers_no_way_to_fill_a_gap() -> None:
    """There is no correct value to put there, so there is no flag that puts one.

    Asserted on the module's AST rather than on its text: the docstring says the word
    "interpolate" a great deal, on purpose, and a substring scan would either fail on
    the prose or force the prose to stop saying the thing it exists to say.
    """
    import inspect

    parameters = set(inspect.signature(load_archive).parameters)
    assert parameters == {"path", "interval_s", "pair", "derived_dir"}

    banned = {"forward_fill", "fill_null", "fill_nan", "upsample", "interpolate", "ffill"}
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            called.add(node.attr)
        elif isinstance(node, ast.Name):
            called.add(node.id)
    assert banned & called == set(), banned & called


def test_the_report_says_in_its_own_fields_that_it_has_no_book_or_spread(
    tmp_path: Path,
) -> None:
    """A backtest that silently assumes zero spread is invalid, so the statement lives
    in a field rather than in a docstring nobody reads at the point of use."""
    archive = tmp_path / "XBTUSD_15.csv"
    write_archive(archive, bars=4)
    report = load_archive(archive, interval_s=INTERVAL)
    assert report.has_order_book is False
    assert report.has_spread is False
    assert "no spread" in report.book_note
    assert "never" in report.interpolation_note


# --------------------------------------------------------------------------- #
# Money and parsing
# --------------------------------------------------------------------------- #


def test_money_is_read_as_decimal_and_never_through_a_float(tmp_path: Path) -> None:
    from decimal import Decimal

    archive = tmp_path / "XBTUSD_15.csv"
    archive.write_text(f"{BASE},0.1,0.3,0.1,0.30000000000000004,1.5,7\n", encoding="utf-8")
    rows = read_archive_rows(archive)
    assert rows[0]["close"] == Decimal("0.30000000000000004")
    assert isinstance(rows[0]["open"], Decimal)


def test_a_header_row_is_skipped_rather_than_parsed_as_a_bar(tmp_path: Path) -> None:
    archive = tmp_path / "XBTUSD_15.csv"
    archive.write_text(
        "time,open,high,low,close,volume,trades\n"
        f"{BASE},100.0,100.5,100.0,100.2,1.5,7\n",
        encoding="utf-8",
    )
    report = load_archive(archive, interval_s=INTERVAL)
    assert report.row_count == 1


def test_a_malformed_line_is_a_failure_rather_than_a_dropped_bar(tmp_path: Path) -> None:
    archive = tmp_path / "XBTUSD_15.csv"
    archive.write_text(f"{BASE},100.0,100.5\n", encoding="utf-8")
    with pytest.raises(ArchiveError, match="6 OHLCVT columns"):
        load_archive(archive, interval_s=INTERVAL)


def test_a_missing_archive_is_a_failure(tmp_path: Path) -> None:
    with pytest.raises(ArchiveError, match="not found"):
        load_archive(tmp_path / "nothing.csv", interval_s=INTERVAL)


def test_duplicate_and_out_of_order_rows_are_reported_never_merged(tmp_path: Path) -> None:
    archive = tmp_path / "XBTUSD_15.csv"
    archive.write_text(
        f"{BASE + INTERVAL},101.0,101.5,101.0,101.2,1.0,3\n"
        f"{BASE},100.0,100.5,100.0,100.2,1.5,7\n"
        f"{BASE},100.0,100.5,100.0,100.9,2.5,9\n",
        encoding="utf-8",
    )
    report = load_archive(archive, interval_s=INTERVAL)
    assert report.row_count == 3
    assert report.duplicate_timestamps == 1
    assert report.out_of_order_rows == 1
    assert report.present_bars == 2


# --------------------------------------------------------------------------- #
# Derived output
# --------------------------------------------------------------------------- #


def test_parquet_is_written_only_when_asked(tmp_path: Path) -> None:
    """Merely *reading* an archive has no side effect on disk, which matters because a
    phase criterion calls this."""
    archive = tmp_path / "XBTUSD_15.csv"
    write_archive(archive, bars=8, holes=((3, 2),))
    derived = tmp_path / "derived"

    report = load_archive(archive, interval_s=INTERVAL)
    assert report.derived_path is None
    assert not derived.exists()

    report = load_archive(archive, interval_s=INTERVAL, derived_dir=derived)
    assert report.derived_path == "XBTUSD_15.parquet"
    assert (derived / "XBTUSD_15.parquet").is_file()


def test_the_parquet_holds_exactly_the_archives_rows(tmp_path: Path) -> None:
    import polars as pl

    archive = tmp_path / "XBTUSD_15.csv"
    timestamps = write_archive(archive, bars=12, holes=((4, 3),))
    derived = tmp_path / "derived"
    load_archive(archive, interval_s=INTERVAL, derived_dir=derived)

    frame = pl.read_parquet(derived / "XBTUSD_15.parquet")
    assert frame["ts"].to_list() == timestamps


def test_the_digest_is_small_and_carries_no_machine_specific_path(tmp_path: Path) -> None:
    archive = tmp_path / "XBTUSD_15.csv"
    write_archive(archive, bars=8, holes=((3, 2),))
    digest = load_archive(archive, interval_s=INTERVAL).digest()
    assert "timestamps" not in digest
    assert digest["path"] == "XBTUSD_15.csv"
    assert str(tmp_path) not in repr(digest)


def test_the_report_model_is_frozen() -> None:
    assert ArchiveReport.model_config["frozen"] is True


# --------------------------------------------------------------------------- #
# Offline only
# --------------------------------------------------------------------------- #


def test_the_module_imports_nothing_from_the_live_loop() -> None:
    """Architecture invariant 5, asserted on the source rather than on behaviour.

    An import test that only checked `sys.modules` would pass on a tree where
    something else had already imported the live loop.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = ("acsoe.engines", "acsoe.core", "acsoe.clients", "acsoe.cli", "acsoe.console")
    offenders = [
        name for name in imported for prefix in forbidden if name.startswith(prefix)
    ]
    assert offenders == [], offenders


def test_the_live_loop_does_not_import_research() -> None:
    """The other direction of invariant 5, which is the one that actually costs money
    if it breaks: a live engine reaching into research code."""
    src = MODULE.resolve().parents[2]
    offenders: list[str] = []
    for area in ("engines", "core", "clients", "cli", "console"):
        for module in (src / "acsoe" / area).rglob("*.py"):
            text = module.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith(("import acsoe.research", "from acsoe.research")):
                    offenders.append(f"{module.name}: {stripped}")
    assert offenders == [], offenders
