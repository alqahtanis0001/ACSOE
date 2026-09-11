"""`acsoe.research.replay` — archive in, decision bars out.

Spec 54. Every assertion here has been run against a deliberately broken version of the
thing it tests and observed red; the mutations and their messages are in
`docs/build-log/phase-4/a-platform.md`. A test nobody has seen fail is a claim.

**The no-interpolation assertions are separate from every count assertion, and run
against a series that actually has holes.** A reducer that fills holes and one that does
not produce the same row count on a series with no holes, so a count is not evidence and
a hole-free fixture cannot produce evidence either. The assertions are on the
timestamps.
"""

from __future__ import annotations

import ast
import itertools
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from acsoe.platform.clock import FixedClock, SystemClock
from acsoe.research.historical import ArchiveError
from acsoe.research.replay import (
    COVERAGE_UNKNOWN_NOTE,
    PROVENANCE_FILENAME,
    ArchiveReplay,
    DecisionBar,
    SettableClock,
    load_provenance,
    pair_from_filename,
)

MODULE = Path(__file__).resolve().parents[2] / "src" / "acsoe" / "research" / "replay.py"

INTERVAL_S = 900
BASE_TS = 1_700_000_000

#: Bar indices that are absent from the fixture archive. Three holes of different
#: lengths — 1, 2 and 4 bars — so a reducer that reported missing *bars* rather than
#: *gaps* says 7 and is caught, and so that "the timestamps are contiguous" and "the
#: timestamps are the archive's" are visibly different claims.
HOLES = ((10, 1), (20, 2), (33, 4))
BARS = 48


def holed_indices() -> list[int]:
    skipped: set[int] = set()
    for start, length in HOLES:
        skipped.update(range(start, start + length))
    return [index for index in range(BARS) if index not in skipped]


def write_archive(path: Path, indices: list[int]) -> list[int]:
    """A headerless Kraken-shaped OHLCVT CSV with a row for each given bar index.

    Prices are distinct per bar so that a bar carrying another bar's close is visible
    in an assertion rather than only in a count.
    """
    lines: list[str] = []
    timestamps: list[int] = []
    for index in indices:
        ts = BASE_TS + index * INTERVAL_S
        timestamps.append(ts)
        price = 100 + index
        lines.append(f"{ts},{price}.0,{price}.5,{price - 1}.0,{price}.2,1.5,7")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return timestamps


@pytest.fixture
def holed_archive(tmp_path: Path) -> tuple[Path, list[int]]:
    """An archive with three holes in it. **Every test about interpolation uses this
    one**, because a hole-free archive cannot tell a filling reducer from an honest
    one."""
    directory = tmp_path / "historical"
    timestamps = write_archive(directory / "BTCUSD_15.csv", holed_indices())
    return directory, timestamps


@pytest.fixture
def clock() -> FixedClock:
    """Parked in 2000, nowhere near the fixture's 2023 timestamps, so a clock that was
    never moved is obvious rather than plausible."""
    return FixedClock(datetime(2000, 1, 1, tzinfo=UTC))


# --------------------------------------------------------------------------- #
# No interpolation. Asserted on timestamps, separately from any count.
# --------------------------------------------------------------------------- #


def test_no_replayed_bar_carries_a_timestamp_the_archive_did_not(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """The single most important assertion in this file.

    A synthesised candle at a price that never traded invents a barrier touch that
    never happened, and the label built from it is a fabricated outcome the model then
    learns from. Nothing crashes and nothing else goes red.
    """
    directory, timestamps = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    emitted = [bar.ts for bar in replay.bars()]
    assert set(emitted) - set(timestamps) == set()
    assert emitted == timestamps


def test_the_holes_are_still_holes_in_the_replayed_series(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """Stated from the other side, and deliberately not the same assertion as the one
    above: that one forbids an invented timestamp, this one requires the specific
    intervals to be absent. A reducer that filled only *some* holes satisfies neither,
    but a reducer that shifted every bar one interval left satisfies the first."""
    directory, _ = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    emitted = {bar.ts for bar in replay.bars()}
    for start, length in HOLES:
        for offset in range(length):
            missing = BASE_TS + (start + offset) * INTERVAL_S
            assert missing not in emitted, f"bar {start + offset} was filled in"


def test_consecutive_bars_are_not_assumed_to_be_one_interval_apart(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """The property the lead's timeout-barrier ruling rests on: the series is not on a
    regular grid, so elapsed time must come from `ts` and never from the row index."""
    directory, _ = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    bars = list(replay.bars())
    steps = {second.ts - first.ts for first, second in itertools.pairwise(bars)}
    assert steps != {INTERVAL_S}, "the fixture has holes; a regular grid means they were filled"
    assert max(steps) == 5 * INTERVAL_S  # the 4-bar hole, plus the bar that follows it


def test_the_row_count_alone_would_not_have_caught_a_filling_reducer(
    tmp_path: Path, clock: FixedClock
) -> None:
    """Why the count assertions and the timestamp assertions are separate tests.

    On an archive with no holes, a reducer that fills holes and one that does not emit
    the same number of rows and the same timestamps. The count is therefore evidence of
    nothing about interpolation, and this test exists to say so rather than to leave the
    separation looking like style.
    """
    directory = tmp_path / "historical"
    timestamps = write_archive(directory / "BTCUSD_15.csv", list(range(BARS)))
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    bars = list(replay.bars())
    assert len(bars) == BARS == len(timestamps)
    assert [bar.ts for bar in bars] == timestamps


# --------------------------------------------------------------------------- #
# Bar boundaries and money
# --------------------------------------------------------------------------- #


def test_a_bars_timestamp_is_its_opening_second_and_close_is_one_interval_later(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """Off by one interval in either direction is a whole bar of look-ahead or a whole
    bar of blindness, and the arithmetic is invisible in any aggregate."""
    directory, timestamps = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    bars = list(replay.bars())
    assert bars[0].ts == timestamps[0] == BASE_TS
    assert bars[0].close_ts == BASE_TS + INTERVAL_S
    for bar in bars:
        assert bar.close_ts - bar.ts == INTERVAL_S
        assert bar.ts % INTERVAL_S == BASE_TS % INTERVAL_S


def test_money_arrives_as_exact_decimals_carrying_the_archives_own_text(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """Exact `Decimal`, never `pytest.approx`. A price that has been through binary
    floating point is not the price that traded."""
    directory, _ = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    bar = next(iter(replay.bars()))
    assert bar.open == Decimal("100.0")
    assert bar.high == Decimal("100.5")
    assert bar.low == Decimal("99.0")
    assert bar.close == Decimal("100.2")
    assert isinstance(bar.open, Decimal)
    assert bar.state_dict()["open"] == "100.0"


def test_the_index_is_a_position_in_the_series_and_not_a_position_in_time(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """`index` counts rows; `ts` counts seconds. Conflating them is how a timeout
    barrier measured in rows silently becomes a timeout measured in days."""
    directory, _ = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    bars = list(replay.bars())
    assert [bar.index for bar in bars] == list(range(len(bars)))
    across_the_hole = next(bar for bar in bars if bar.ts == BASE_TS + 37 * INTERVAL_S)
    assert across_the_hole.index == 30
    assert across_the_hole.ts - BASE_TS == 37 * INTERVAL_S


# --------------------------------------------------------------------------- #
# The injected clock
# --------------------------------------------------------------------------- #


def test_the_clock_is_moved_to_each_bars_close_as_it_is_yielded(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """The whole anti-look-ahead mechanism: there is no reading of this clock from
    which a later bar is visible."""
    directory, _ = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    for bar in replay.bars():
        assert clock.now() == datetime.fromtimestamp(bar.close_ts, tz=UTC)
        assert clock.now().timestamp() > bar.ts


def test_replay_never_reads_wall_time(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """Asserted on the source, not on behaviour. A behavioural check would pass on a
    module that called `datetime.now()` and then threw the answer away, and would keep
    passing right up until somebody used it."""
    text = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "now"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "datetime"
        ):
            offenders.append(ast.unparse(node))
    assert offenders == [], offenders

    directory, _ = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    list(replay.bars())
    assert clock.now().year == 2023


def test_a_read_only_clock_is_not_a_replay_clock() -> None:
    """`SystemClock` satisfies `Clock` and must not satisfy `SettableClock`. If it did,
    injecting one would stamp every bar with wall time and the replay would quietly
    stop being a replay while every other test here still passed."""
    assert isinstance(FixedClock(datetime(2000, 1, 1, tzinfo=UTC)), SettableClock)
    assert not isinstance(SystemClock(), SettableClock)


def test_replay_without_a_clock_still_yields_the_same_bars(
    holed_archive: tuple[Path, list[int]]
) -> None:
    """The clock is an injection, not a dependency. A caller that only wants the frame
    is not forced to invent one."""
    directory, timestamps = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S)
    assert [bar.ts for bar in replay.bars()] == timestamps


# --------------------------------------------------------------------------- #
# Several pairs
# --------------------------------------------------------------------------- #


def test_several_pairs_merge_into_one_ascending_stream(
    tmp_path: Path, clock: FixedClock
) -> None:
    directory = tmp_path / "historical"
    write_archive(directory / "BTCUSD_15.csv", [0, 2, 4])
    write_archive(directory / "ETHUSD_15.csv", [1, 2, 3])
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    bars = list(replay.bars())
    assert [bar.ts for bar in bars] == sorted(bar.ts for bar in bars)
    assert [(bar.ts - BASE_TS) // INTERVAL_S for bar in bars] == [0, 1, 2, 2, 3, 4]
    assert [bar.pair for bar in bars] == [
        "BTCUSD", "ETHUSD", "BTCUSD", "ETHUSD", "ETHUSD", "BTCUSD"
    ]


def test_a_tie_between_two_pairs_is_broken_by_pair_name_not_by_arrival(
    tmp_path: Path, clock: FixedClock
) -> None:
    """Two runs over the same archives must produce byte-identical output, or a training
    set is not reproducible from its config plus its data — the one property
    `seeds.global` exists to give it.

    **The pairs go in deliberately out of order.** The first version of this test built
    them through `from_directory`, which globs in name order, and the rows therefore
    went into the sort already sorted; Python's sort is stable, so deleting the pair
    name from the sort key changed nothing and the mutation survived all 43 tests. A
    tie-break can only be tested by an input whose arrival order is not already the
    answer.
    """
    rows = {
        pair: [
            {
                "ts": BASE_TS,
                "open": Decimal("1"),
                "high": Decimal("1"),
                "low": Decimal("1"),
                "close": Decimal("1"),
                "volume": Decimal("1"),
                "trades": 1,
            }
        ]
        for pair in ("SOLUSD", "BTCUSD", "ETHUSD")
    }
    assert list(rows) == ["SOLUSD", "BTCUSD", "ETHUSD"]
    replay = ArchiveReplay(
        rows=rows,
        archives={},
        interval_s=INTERVAL_S,
        clock=clock,
    )
    first = [bar.pair for bar in replay.bars()]
    second = [bar.pair for bar in replay.bars()]
    assert first == second == ["BTCUSD", "ETHUSD", "SOLUSD"]


def test_one_pair_can_be_replayed_on_its_own(tmp_path: Path, clock: FixedClock) -> None:
    directory = tmp_path / "historical"
    write_archive(directory / "BTCUSD_15.csv", [0, 1])
    write_archive(directory / "ETHUSD_15.csv", [0, 1, 2])
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    assert [bar.pair for bar in replay.bars("ETHUSD")] == ["ETHUSD"] * 3


# --------------------------------------------------------------------------- #
# The gap report travels with the frame
# --------------------------------------------------------------------------- #


def test_the_gap_report_is_exposed_alongside_the_frame(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """Three gaps, not seven missing bars. The holes differ in size precisely so that a
    report which added them together is caught."""
    directory, timestamps = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    report = replay.report.archives["BTCUSD"]
    assert report.gap_count == len(HOLES)
    assert report.missing_bars == sum(length for _, length in HOLES)
    assert report.row_count == len(timestamps)
    assert replay.frame("BTCUSD").height == len(timestamps)
    assert [int(ts) for ts in replay.frame("BTCUSD")["ts"].to_list()] == timestamps


def test_the_report_carries_the_no_book_and_no_interpolation_statements(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """Carried in a field rather than left in a docstring nobody reads at the point of
    use. A backtest that silently assumes zero spread is invalid."""
    directory, _ = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    assert replay.report.has_order_book is False
    assert replay.report.has_spread is False
    assert "no spread" in replay.report.book_note
    assert "never" in replay.report.interpolation_note


# --------------------------------------------------------------------------- #
# Coverage: a hole here is not a hole in Kraken's archive
# --------------------------------------------------------------------------- #


def test_without_a_sidecar_coverage_is_unknown_and_not_assumed_quiet(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """The dangerous default. "No sidecar" must not silently become "every hole is a
    quiet market", because that is what makes a triple barrier walk across an outage
    and return a timeout the market never gave."""
    directory, _ = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    assert replay.report.coverage_known is False
    assert replay.report.coverage == {}
    assert replay.report.coverage_note == COVERAGE_UNKNOWN_NOTE
    assert "unknown" in replay.report.coverage_note


def test_a_sidecar_classifies_the_holes_by_timestamp(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    directory, _ = holed_archive
    not_recorded = [BASE_TS + 20 * INTERVAL_S, BASE_TS + 21 * INTERVAL_S]
    (directory / PROVENANCE_FILENAME).write_text(
        json.dumps(
            {
                "provenance": "real trades, our reduction",
                "pairs": {
                    "BTC/USD": {
                        "file": "BTCUSD_15.csv",
                        "missing_quiet_ts": [BASE_TS + 10 * INTERVAL_S],
                        "missing_not_recorded_ts": not_recorded,
                        "partial_rows_ts": [BASE_TS],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    assert replay.report.coverage_known is True
    assert replay.report.provenance == "real trades, our reduction"
    coverage = replay.report.coverage["BTCUSD"]
    assert coverage.missing_not_recorded_ts == tuple(not_recorded)
    assert coverage.missing_quiet_ts == (BASE_TS + 10 * INTERVAL_S,)
    assert coverage.unusable_ts == frozenset({*not_recorded, BASE_TS})


def test_a_damaged_sidecar_reports_unknown_rather_than_stopping_the_replay(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """Two situations that must not be conflated the wrong way round. A damaged note
    about the holes is not a damaged archive, so the replay continues — but it must
    report `unknown`, never `known` with an empty classification, which would read as
    "no holes are suspect"."""
    directory, _ = holed_archive
    (directory / PROVENANCE_FILENAME).write_text("{not json", encoding="utf-8")
    assert load_provenance(directory) is None
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    assert replay.report.coverage_known is False
    assert replay.report.bar_count == len(holed_indices())


def test_the_sidecar_is_not_replayed_as_an_archive(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """It sits in the same directory and is not a CSV. A glob of `*` would hand
    `read_archive_rows` a JSON file and fail on its first line."""
    directory, timestamps = holed_archive
    (directory / PROVENANCE_FILENAME).write_text(json.dumps({"pairs": {}}), encoding="utf-8")
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    assert replay.report.pairs == ("BTCUSD",)
    assert replay.report.bar_count == len(timestamps)


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_a_missing_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ArchiveError, match="archive directory not found"):
        ArchiveReplay.from_directory(tmp_path / "nope", interval_s=INTERVAL_S)


def test_a_directory_with_no_csv_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "historical"
    directory.mkdir()
    (directory / PROVENANCE_FILENAME).write_text("{}", encoding="utf-8")
    with pytest.raises(ArchiveError, match=r"no \*\.csv archive found"):
        ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S)


def test_no_archives_at_all_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ArchiveError, match="no archive was given"):
        ArchiveReplay.from_archives([], interval_s=INTERVAL_S)


@pytest.mark.parametrize("interval", [0, -900])
def test_a_non_positive_interval_is_refused(
    holed_archive: tuple[Path, list[int]], interval: int
) -> None:
    directory, _ = holed_archive
    with pytest.raises(ValueError, match="interval_s must be positive"):
        ArchiveReplay.from_directory(directory, interval_s=interval)


def test_a_decision_bar_refuses_an_unknown_field() -> None:
    """`extra="forbid"`. A typo'd field silently dropped is a bar carrying a default
    nobody chose."""
    with pytest.raises(ValueError, match="close_price"):
        DecisionBar(
            pair="BTCUSD",
            ts=BASE_TS,
            interval_s=INTERVAL_S,
            open=Decimal("1"),
            high=Decimal("1"),
            low=Decimal("1"),
            close=Decimal("1"),
            volume=Decimal("1"),
            trades=1,
            index=0,
            close_price=Decimal("1"),  # type: ignore[call-arg]
        )


# --------------------------------------------------------------------------- #
# Naming, and invariant 5
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("BTCUSD_15.csv", "BTCUSD"),
        ("XBTUSD_1440.csv", "XBTUSD"),
        ("ETHUSD.csv", "ETHUSD"),
        ("SOME_PAIR_15.csv", "SOME_PAIR"),
        ("SOME_PAIR.csv", "SOME_PAIR"),
    ],
)
def test_the_pair_is_taken_from_the_file_name_without_inventing_a_spelling(
    name: str, expected: str
) -> None:
    """Only the interval suffix is stripped. `AGENTS.md` is explicit that remembered
    Kraken naming is stale, so `XBTUSD` is not silently rewritten to `BTC/USD`."""
    assert pair_from_filename(Path(name)) == expected


def test_replay_imports_nothing_from_the_live_loop() -> None:
    """Architecture invariant 5, asserted on the source rather than on behaviour. An
    import test that only checked `sys.modules` would pass on a tree where something
    else had already imported the live loop."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = ("acsoe.engines", "acsoe.core", "acsoe.clients", "acsoe.cli", "acsoe.console")
    offenders = [name for name in imported for prefix in forbidden if name.startswith(prefix)]
    assert offenders == [], offenders
    assert "acsoe.research.historical" in imported


def test_nothing_in_replay_opens_a_socket() -> None:
    """"No network" as a property of the source, not an absence somebody remembers to
    keep. The only I/O here is reading files the caller named."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported & {"socket", "http", "urllib", "requests", "httpx", "websockets"} == set()


# --------------------------------------------------------------------------- #
# Does a hole mean no trades? Three answers, and the third is the point.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("flag", [True, False])
def test_the_sidecar_says_whether_a_hole_means_no_trades(
    holed_archive: tuple[Path, list[int]], clock: FixedClock, flag: bool
) -> None:
    """Kraken's published archive says True — it never stops watching, so an absent
    interval had no trades in it, and a triple barrier is safe to walk across one. An
    archive built from our recording says False, because the recorder did stop."""
    directory, _ = holed_archive
    (directory / PROVENANCE_FILENAME).write_text(
        json.dumps({"holes_mean_no_trades": flag, "pairs": {}}), encoding="utf-8"
    )
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    assert replay.report.holes_mean_no_trades is flag


def test_a_sidecar_that_never_heard_of_the_question_answers_unknown_not_no(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    """The third value, and the reason the field is `bool | None` rather than `bool`.

    A sidecar written before this key existed has not measured anything, and reporting
    `False` for it would claim a measurement that was never taken. `None` is the honest
    answer and a consumer must treat it as it would treat `False`: invariant 3, the
    absence of a "no" is never a "yes".
    """
    directory, _ = holed_archive
    (directory / PROVENANCE_FILENAME).write_text(
        json.dumps({"provenance": "written before the key existed", "pairs": {}}),
        encoding="utf-8",
    )
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    assert replay.report.holes_mean_no_trades is None
    assert replay.report.coverage_known is True
    assert "UNKNOWN" in replay.report.summary()


@pytest.mark.parametrize("value", ["true", 1, "yes", [], {}, None])
def test_a_non_boolean_answer_is_unknown_rather_than_truthy(
    holed_archive: tuple[Path, list[int]], clock: FixedClock, value: object
) -> None:
    """Read as `isinstance(..., bool)`, never as truthiness. `"false"` is a true string
    and `0` is a false int, and either reading would turn a damaged sidecar into a
    confident wrong answer about whether a barrier may be walked across a hole."""
    directory, _ = holed_archive
    (directory / PROVENANCE_FILENAME).write_text(
        json.dumps({"holes_mean_no_trades": value, "pairs": {}}), encoding="utf-8"
    )
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    assert replay.report.holes_mean_no_trades is None


def test_no_sidecar_at_all_is_also_unknown(
    holed_archive: tuple[Path, list[int]], clock: FixedClock
) -> None:
    directory, _ = holed_archive
    replay = ArchiveReplay.from_directory(directory, interval_s=INTERVAL_S, clock=clock)
    assert replay.report.holes_mean_no_trades is None
    assert "a hole means UNKNOWN" in replay.report.summary()
