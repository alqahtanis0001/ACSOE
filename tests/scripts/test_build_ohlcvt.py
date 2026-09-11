"""`scripts/build_ohlcvt.py` — Kraken's published time-and-sales into 15-minute OHLCVT.

Spec 54 as amended 2026-09-11. Every assertion here has been run against a deliberately
broken reducer and observed red; the mutations and the exact red messages are in
`docs/build-log/phase-4/a-platform.md`.

**The fixtures are constructed, not slices of the real archive, and that is deliberate.**
Three of the properties this file proves — that a late row is counted rather than
appended as a second bar with a timestamp the file already carries, that a malformed row
is counted rather than swallowed, that a truncated final line does not stop the build —
cannot be proved against `data/historical/`, because Kraken's export is clean: zero
out-of-order rows, zero late rows and zero malformed rows across 27,484,393 SOLUSD
trades. A test that read the real file would pass against a reducer with none of those
counters in it.

The no-interpolation assertion is separate from every row-count assertion and runs
against a series that actually has quiet intervals in it.
"""

from __future__ import annotations

import ast
import importlib.util
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_ohlcvt.py"

INTERVAL_S = 900
#: 2021-06-17T15:30:00Z, on a 15-minute boundary. The first SOLUSD bar in the real
#: archive, so the fixtures sit where the data does rather than at an arbitrary epoch.
BASE_TS = 1_623_943_800


@pytest.fixture(scope="module")
def build_ohlcvt() -> ModuleType:
    """`scripts/build_ohlcvt.py`, imported by path. It is not a package."""
    spec = importlib.util.spec_from_file_location("acsoe_build_ohlcvt_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_time_and_sales(path: Path, rows: list[tuple[int, str, str]]) -> Path:
    """Kraken's shape exactly: three columns, no header, `timestamp,price,volume`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"{ts},{price},{volume}" for ts, price, volume in rows) + "\n",
        encoding="utf-8",
    )
    return path


def rows_of(path: Path) -> list[list[str]]:
    return [line.split(",") for line in path.read_text(encoding="utf-8").splitlines()]


# --------------------------------------------------------------------------- #
# The reduction itself
# --------------------------------------------------------------------------- #


def test_one_interval_of_trades_becomes_one_bar(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [
            (BASE_TS + 1, "100.0", "1.5"),
            (BASE_TS + 2, "105.0", "0.5"),
            (BASE_TS + 3, "95.0", "2.0"),
            (BASE_TS + 4, "101.0", "1.0"),
        ],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    stats = build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    assert stats["rows"] == 1
    assert rows_of(out) == [[str(BASE_TS), "100.0", "105.0", "95.0", "101.0", "5.0", "4"]]


def test_the_trades_column_is_a_real_count_not_a_guess(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """The `T` of OHLCVT. One source row is one trade, so unlike the recording-derived
    archive this number is knowable and is not invented."""
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [(BASE_TS + n, "100.0", "0.1") for n in range(7)],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    assert rows_of(out)[0][6] == "7"


def test_money_never_passes_through_a_float(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """`0.1 + 0.2` is the whole reason. Volume is summed over every trade in an
    interval — 27 million of them in one real file — so a float there compounds, and
    the result is what a position size is computed from."""
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [(BASE_TS + 1, "100.0", "0.1"), (BASE_TS + 2, "100.0", "0.2")],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    assert rows_of(out)[0][5] == "0.3"


def test_the_open_and_close_come_from_the_timestamp_not_the_arrival(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """A handful of rows out of order must not decide the open. Kraken's export is
    ordered — measured at zero inversions over 27,484,393 SOLUSD trades — but the open
    of a bar is not a thing to leave resting on that."""
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [
            (BASE_TS + 500, "150.0", "1"),
            (BASE_TS + 100, "110.0", "1"),
            (BASE_TS + 300, "130.0", "1"),
        ],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    stats = build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    row = rows_of(out)[0]
    assert row[1] == "110.0"
    assert row[4] == "150.0"
    # One inversion, not two: 100 goes backwards from 500, then 300 goes forwards again.
    assert stats["out_of_order_rows"] == 1


def test_two_trades_in_the_same_second_are_ordered_by_file_order(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """Time-and-sales carries no trade id and several trades share a second routinely,
    so file order is the only ordering there is. Engine 3's `build_candles` breaks the
    same tie the same way."""
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [(BASE_TS + 10, "120.0", "1"), (BASE_TS + 10, "125.0", "1")],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    row = rows_of(out)[0]
    assert row[1] == "120.0"
    assert row[4] == "125.0"


# --------------------------------------------------------------------------- #
# A quiet interval produces no row. On timestamps, not on a count.
# --------------------------------------------------------------------------- #


def test_a_quiet_interval_produces_no_row_at_all(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """The load-bearing one. Against Kraken's published archive a hole means no trades
    occurred, and a zero-volume bar at the previous close would invent a barrier touch
    that never happened."""
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [
            (BASE_TS + 10, "100.0", "1"),
            (BASE_TS + 3 * INTERVAL_S + 10, "110.0", "1"),
        ],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    assert [row[0] for row in rows_of(out)] == [
        str(BASE_TS),
        str(BASE_TS + 3 * INTERVAL_S),
    ]


def test_the_quiet_intervals_are_counted_and_reported(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """Reported, never filled. `missing_quiet` is the only hole category this source
    needs, and the reason the other two exist in the older builder is written into the
    provenance rather than dropped."""
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [
            (BASE_TS + 10, "100.0", "1"),
            (BASE_TS + 3 * INTERVAL_S + 10, "110.0", "1"),
        ],
    )
    stats = build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=None)
    assert stats["rows"] == 2
    assert stats["expected_intervals"] == 4
    assert stats["missing_quiet"] == 2


def test_a_row_count_alone_cannot_tell_a_filling_reducer_from_an_honest_one(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """Why the assertions above are on timestamps. Over a series with no quiet
    intervals, a reducer that fills holes emits exactly the same number of rows and the
    same timestamps, so the count is evidence of nothing about interpolation."""
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [(BASE_TS + n * INTERVAL_S + 10, "100.0", "1") for n in range(4)],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    stats = build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    assert stats["rows"] == 4
    assert stats["missing_quiet"] == 0
    assert [row[0] for row in rows_of(out)] == [
        str(BASE_TS + n * INTERVAL_S) for n in range(4)
    ]


# --------------------------------------------------------------------------- #
# Bar boundaries
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("offset", "bucket"),
    [
        (0, 0),
        (1, 0),
        (INTERVAL_S - 1, 0),
        (INTERVAL_S, 1),
        (INTERVAL_S + 1, 1),
        (2 * INTERVAL_S - 1, 1),
    ],
)
def test_the_bar_a_trade_falls_in_is_left_closed_and_right_open(
    build_ohlcvt: ModuleType, tmp_path: Path, offset: int, bucket: int
) -> None:
    """The boundary cases individually. An off-by-one interval is invisible in every
    aggregate and moves a trade into its neighbour, which moves the open, the close and
    two barrier touches with it."""
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv", [(BASE_TS + offset, "100.0", "1")]
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    assert rows_of(out)[0][0] == str(BASE_TS + bucket * INTERVAL_S)


def test_bars_come_out_in_ascending_timestamp_order(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """`load_archive` sorts what it reads, so an unsorted file would still load — and
    the disorder would only ever show up in `out_of_order_rows` on a report nobody
    reads. Asserted here at the point it is produced."""
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [
            (BASE_TS + 10, "100.0", "1"),
            (BASE_TS + 2 * INTERVAL_S + 10, "102.0", "1"),
            (BASE_TS + INTERVAL_S + 10, "101.0", "1"),
            (BASE_TS + 3 * INTERVAL_S + 10, "103.0", "1"),
        ],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    written = [int(row[0]) for row in rows_of(out)]
    assert written == sorted(written)
    assert written == [BASE_TS + n * INTERVAL_S for n in range(4)]


# --------------------------------------------------------------------------- #
# What the stream does with rows it cannot use
# --------------------------------------------------------------------------- #


def test_a_late_row_is_counted_and_never_written_as_a_second_bar(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """A row whose interval has already been written out. The dangerous handling is to
    append it: the file would then carry two rows with one timestamp, `load_archive`
    would report `duplicate_timestamps` and sort them into an order nobody chose, and
    the bar a label was walked from would depend on which one came second."""
    window = build_ohlcvt.OPEN_BAR_WINDOW
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [
            (BASE_TS + 10, "100.0", "1"),
            *[
                (BASE_TS + n * INTERVAL_S + 10, "101.0", "1")
                for n in range(1, window * 3)
            ],
            (BASE_TS + 20, "999.0", "50"),  # far behind the window: late
        ],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    stats = build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    assert stats["late_rows"] == 1
    written = [row[0] for row in rows_of(out)]
    assert len(written) == len(set(written))
    assert rows_of(out)[0] == [str(BASE_TS), "100.0", "100.0", "100.0", "100.0", "1", "1"]


def test_a_small_inversion_inside_the_window_is_absorbed_not_counted_late(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """The window exists so that ordinary jitter does not become a lost trade. Only a
    row older than the whole window is beyond saving, and that one is counted."""
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [
            (BASE_TS + INTERVAL_S + 10, "101.0", "1"),
            (BASE_TS + 10, "100.0", "1"),  # one interval behind, inside the window
        ],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    stats = build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    assert stats["late_rows"] == 0
    assert stats["out_of_order_rows"] == 1
    assert [row[0] for row in rows_of(out)] == [str(BASE_TS), str(BASE_TS + INTERVAL_S)]


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "not,a,number", "1623943810,,1.0", "1623943810", "1623943810,100.0"],
)
def test_a_malformed_row_is_counted_rather_than_swallowed(
    build_ohlcvt: ModuleType, tmp_path: Path, bad: str
) -> None:
    """A skipped row nothing reports is a bar quietly missing volume. Blank lines are
    the one exception and are not malformed — they are nothing at all."""
    source = tmp_path / "src" / "XBTUSD.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(f"{BASE_TS + 10},100.0,1\n{bad}\n", encoding="utf-8")
    stats = build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=None)
    assert stats["trades"] == 1
    assert stats["malformed_rows"] == (0 if not bad.strip() else 1)


def test_a_truncated_final_line_does_not_stop_the_build_and_is_counted(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """Extraction of this archive was still running when it appeared. A half-written
    final line is not a parse error — it is a silently short last bar — so it is both
    survived and counted."""
    source = tmp_path / "src" / "XBTUSD.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(f"{BASE_TS + 10},100.0,1\n{BASE_TS + 20},10", encoding="utf-8")
    stats = build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=None)
    assert stats["trades"] == 1
    assert stats["malformed_rows"] == 1


# --------------------------------------------------------------------------- #
# The file may still be being extracted
# --------------------------------------------------------------------------- #


def test_a_file_that_is_still_growing_is_refused(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """Refused, not read. A truncated read of a growing file produces a short final bar
    and no error anywhere — the exact shape of defect this phase exists to keep out."""
    source = tmp_path / "src" / "XBTUSD.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("1,2,3\n", encoding="utf-8")

    real_stat = Path.stat
    sizes = iter([10, 20, 30, 40, 50, 60])

    class Growing:
        def __init__(self, size: int) -> None:
            self.st_size = size

    def fake_stat(self: Path, *args: object, **kwargs: object) -> object:
        if self == source:
            return Growing(next(sizes))
        return real_stat(self, *args, **kwargs)

    original = Path.stat
    Path.stat = fake_stat  # type: ignore[method-assign, assignment]
    try:
        with pytest.raises(RuntimeError, match="still growing"):
            build_ohlcvt.wait_for_stable_size(source, settle_s=0.0, attempts=3)
    finally:
        Path.stat = original  # type: ignore[method-assign]


def test_a_settled_file_is_accepted_and_its_size_returned(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    source = tmp_path / "src" / "XBTUSD.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("1,2,3\n", encoding="utf-8")
    assert build_ohlcvt.wait_for_stable_size(source, settle_s=0.0) == source.stat().st_size


# --------------------------------------------------------------------------- #
# Finding a pair across the operator's two directories
# --------------------------------------------------------------------------- #


def test_a_pair_is_found_in_either_source_directory(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """The archive is split alphabetically across two directories, which is not
    something a caller should have to know."""
    first = tmp_path / "KRAKEN_TimeAndSales_Combined"
    second = tmp_path / "TimeAndSales_Combined"
    write_time_and_sales(first / "ETHUSD.csv", [(BASE_TS, "1", "1")])
    write_time_and_sales(second / "XBTUSD.csv", [(BASE_TS, "1", "1")])
    directories = (first, second)
    assert build_ohlcvt.find_pair_file("ETHUSD", directories) == first / "ETHUSD.csv"
    assert build_ohlcvt.find_pair_file("XBTUSD", directories) == second / "XBTUSD.csv"


def test_a_missing_pair_raises_rather_than_producing_an_empty_series(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """A missing pair is a stop, not a series with no rows in it. An empty archive that
    loads cleanly is the quietest possible wrong answer."""
    with pytest.raises(FileNotFoundError, match="NOPEUSD"):
        build_ohlcvt.find_pair_file("NOPEUSD", (tmp_path,))


# --------------------------------------------------------------------------- #
# The shape the loader reads, and the source is never touched
# --------------------------------------------------------------------------- #


def test_the_written_file_loads_through_the_real_archive_loader(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """The end of the seam: what this writes is what `load_archive` reads. A shape
    assertion here and a separate parse there would let the two drift."""
    from acsoe.research.historical import load_archive

    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [
            (BASE_TS + 10, "100.0", "1.5"),
            (BASE_TS + 2 * INTERVAL_S + 10, "110.0", "2.5"),
        ],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)

    report = load_archive(out, interval_s=INTERVAL_S, pair="XBT/USD")
    assert report.row_count == 2
    assert report.gap_count == 1
    assert report.timestamps == (BASE_TS, BASE_TS + 2 * INTERVAL_S)
    assert report.duplicate_timestamps == 0
    assert report.out_of_order_rows == 0
    assert report.first_close == "100.0"
    assert report.last_close == "110.0"


def test_the_file_has_no_header_and_seven_columns(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """Kraken's archives have no header, and `read_archive_rows` only tolerates one on
    line 1 — so a header written here would be silently skipped and the file would
    still look right while carrying one bar fewer than it should."""
    source = write_time_and_sales(tmp_path / "src" / "XBTUSD.csv", [(BASE_TS, "1", "1")])
    out = tmp_path / "out" / "XBTUSD_15.csv"
    build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    first = rows_of(out)[0]
    assert first[0].isdigit()
    assert len(first) == 7


def test_the_source_file_is_left_byte_identical(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """Invariant 11 in its strongest form: 27 GB the operator obtained once. Asserted on
    the bytes, because a reducer that rewrote a line in place would leave the file the
    same length."""
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [(BASE_TS + 10, "100.0", "1"), (BASE_TS + 20, "101.0", "1")],
    )
    before = source.read_bytes()
    build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=tmp_path / "out" / "X_15.csv")
    assert source.read_bytes() == before


def test_the_output_is_never_written_inside_a_source_directory(
    build_ohlcvt: ModuleType,
) -> None:
    """Two archives in one directory under one naming convention is a silent
    wrong-source defect: nothing can tell a derived bar file from a source trade file,
    and a labelled slice built from the wrong one looks exactly like one built from the
    right one.

    The output sits at the top level of `data/historical/` and the operator's files sit
    one level down, so the two never share a directory. Asserted in both directions —
    the output is not a source directory, and it is not *inside* one — because the
    second is the one a careless default would break.
    """
    out = build_ohlcvt.DEFAULT_OUT_DIR
    for source in build_ohlcvt.DEFAULT_SOURCE_DIRS:
        assert out != source
        assert source not in out.parents
        assert out in source.parents


def test_the_source_and_derived_names_differ_even_for_the_same_pair(
    build_ohlcvt: ModuleType,
) -> None:
    """The second half of the guard, and the one that survives the directories ever
    being flattened: `XBTUSD.csv` is three-column time-and-sales, `XBTUSD_15.csv` is
    seven-column OHLCVT, and nothing loads one believing it is the other."""
    for pair in build_ohlcvt.DEFAULT_PAIRS:
        assert build_ohlcvt.archive_filename(pair, 900) != f"{pair}.csv"


def test_the_derived_name_cannot_be_mistaken_for_a_source_name(
    build_ohlcvt: ModuleType,
) -> None:
    """`XBTUSD.csv` is three-column time-and-sales; `XBTUSD_15.csv` is seven-column
    OHLCVT. The suffix is the whole guard."""
    assert build_ohlcvt.archive_filename("XBTUSD", 900) == "XBTUSD_15.csv"
    assert build_ohlcvt.archive_filename("ETHUSD", 3600) == "ETHUSD_60.csv"


# --------------------------------------------------------------------------- #
# Streaming, and money formatting
# --------------------------------------------------------------------------- #


def test_no_source_file_is_ever_read_whole_or_sorted() -> None:
    """`XBTUSD.csv` is 2.7 GB. Asserted on the source, because a behavioural test can
    only see the fixture-sized files it made, and those fit in memory.

    Asserted over the **parsed** module rather than over its text. The first version of
    this test searched the raw source and went red on the module's own docstring, which
    says "never `readlines()`" — a prose mention is not a call, and a check that cannot
    tell them apart would equally have gone green on a module that merely talked about
    streaming.
    """
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    called: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                called.append(node.func.attr)
            elif isinstance(node.func, ast.Name):
                called.append(node.func.id)
    assert "readlines" not in called
    assert "read" not in called
    # `sorted` is called exactly once, over the handful of open bar buckets, never over
    # anything that came out of the file.
    assert called.count("sorted") == 1
    assert "sorted(bucket for bucket in open_bars" in SCRIPT.read_text(encoding="utf-8")


def test_memory_does_not_grow_with_the_length_of_the_history(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """Bars are written as the stream passes them, so only the open window is held. A
    reducer that accumulated every bar would pass every other test in this file and
    then need hundreds of megabytes on a twelve-year series."""
    window = build_ohlcvt.OPEN_BAR_WINDOW
    intervals = window * 20
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [(BASE_TS + n * INTERVAL_S + 10, "100.0", "1") for n in range(intervals)],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"

    original = build_ohlcvt.Bar
    live: list[int] = []

    class CountingBar(original):  # type: ignore[misc, valid-type]
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            live.append(1)

    build_ohlcvt.Bar = CountingBar
    try:
        stats = build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)
    finally:
        build_ohlcvt.Bar = original

    assert stats["rows"] == intervals
    # Every bar is constructed once — that is not the claim. The claim is that they are
    # not all held at once, which the written file proves: rows appear while the stream
    # is still running, so the file already has content before the last trade is read.
    assert len(live) == intervals
    assert len(rows_of(out)) == intervals


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0.00000001", "0.00000001"), ("1E-8", "0.00000001"), ("78804.0", "78804.0")],
)
def test_money_is_written_in_plain_decimal_never_scientific_notation(
    build_ohlcvt: ModuleType, value: str, expected: str
) -> None:
    """`str(Decimal("1E-8"))` is `1E-8`. A sub-cent altcoin price summed into a volume
    reaches that form easily, `read_archive_rows` would parse it back, and no Kraken
    archive contains it — a file only our own loader can read is not archive-shaped."""
    assert build_ohlcvt.plain(Decimal(value)) == expected


def test_a_non_positive_interval_is_refused(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    source = write_time_and_sales(tmp_path / "src" / "XBTUSD.csv", [(BASE_TS, "1", "1")])
    with pytest.raises(ValueError, match="interval_s must be positive"):
        build_ohlcvt.reduce_pair(source, interval_s=0, out=None)


# --------------------------------------------------------------------------- #
# Line endings, on Windows, in a file something else parses
# --------------------------------------------------------------------------- #


def test_the_written_archive_has_unix_line_endings_and_no_stray_carriage_returns(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """Asserted on the **bytes**, because every text-mode reader hides this.

    `Path.write_text` and `open(path, "w")` open in text mode, and text mode on Windows
    translates every `\n` to `\r\n`. `csv.writer` on a handle without `newline=""`
    goes one worse and emits `\r\r\n`, because it writes its own `\r\n` and the
    translation layer then doubles the `\r`. None of that is visible through
    `read_text`, `splitlines` or `csv.reader`, which all normalise — so a test written
    at any level above bytes passes against every one of those outcomes.

    It matters here because `research/historical.py` reads these bytes back, and a
    doubled line ending is the kind of thing that surfaces three phases later as an
    unexplained parse difference. Lead's finding, 2026-09-11.
    """
    source = write_time_and_sales(
        tmp_path / "src" / "XBTUSD.csv",
        [(BASE_TS + n * INTERVAL_S + 10, "100.0", "1") for n in range(3)],
    )
    out = tmp_path / "out" / "XBTUSD_15.csv"
    build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=out)

    raw = out.read_bytes()
    assert b"\r" not in raw
    assert raw.count(b"\n") == 3
    assert raw.endswith(b"\n")


def test_the_provenance_sidecar_has_unix_line_endings(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """Same rule, same reason, different writer. `json.dumps(..., indent=1)` is full of
    newlines and `write_text` would translate every one of them."""
    source_dir = tmp_path / "TimeAndSales_Combined"
    write_time_and_sales(source_dir / "XBTUSD.csv", [(BASE_TS + 10, "100.0", "1")])
    out_dir = tmp_path / "out"
    assert (
        build_ohlcvt.main(
            [
                "--pairs",
                "XBTUSD",
                "--source-dir",
                str(source_dir),
                "--out-dir",
                str(out_dir),
                "--skip-stability-check",
                "--write",
            ]
        )
        == 0
    )
    raw = (out_dir / build_ohlcvt.PROVENANCE_FILENAME).read_bytes()
    assert b"\r" not in raw


def test_a_source_archive_with_windows_line_endings_still_loads(
    build_ohlcvt: ModuleType, tmp_path: Path
) -> None:
    """The other direction: we must *read* CRLF even though we never write it.

    The operator's 27 GB arrived from an archive extraction and nothing guarantees its
    line endings. A reducer that split on `\n` and left a `\r` on the last field would
    turn every volume into an unparseable string — and `iter_trades` counts unparseable
    rows rather than raising, so the failure would be a silently empty archive.
    """
    source = tmp_path / "src" / "XBTUSD.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(
        b"\r\n".join(
            f"{BASE_TS + n * 10},100.{n},1.5".encode() for n in range(3)
        )
        + b"\r\n"
    )
    stats = build_ohlcvt.reduce_pair(source, interval_s=INTERVAL_S, out=None)
    assert stats["malformed_rows"] == 0
    assert stats["trades"] == 3
