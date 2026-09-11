"""`scripts/build_archive.py` — real recorded trades into a Kraken-shaped archive.

Spec 54. Every assertion here has been run against a deliberately broken builder and
observed red; the mutations and their red messages are in
`docs/build-log/phase-4/a-platform.md`.

**The recordings here are constructed, and that is not incidental.** Two properties this
file exists to prove — that de-duplication is at the frame level, and that it is *not* at
the trade level — cannot be proved against `data/raw/`, because the real recording
currently contains **zero** duplicate trade frames and zero repeated trade ids. A test
that read the real archive would pass against a builder with no de-duplication in it at
all, and against one that de-duplicated trades and destroyed volume. So the duplicates
are put there on purpose.

The no-interpolation assertion is separate from every row-count assertion and runs
against a recording that actually has quiet intervals in it.
"""

from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_archive.py"

INTERVAL_S = 900
#: 2026-09-09T00:00:00Z, on a 15-minute boundary.
BASE_TS = 1_788_912_000


@pytest.fixture(scope="module")
def build_archive() -> ModuleType:
    """`scripts/build_archive.py`, imported by path. It is not a package."""
    spec = importlib.util.spec_from_file_location("acsoe_build_archive_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def iso(seconds: float) -> str:
    from datetime import UTC, datetime

    return (
        datetime.fromtimestamp(seconds, tz=UTC).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
    )


def trade_frame(
    trades: list[tuple[float, str, str, int]],
    *,
    pair: str = "BTC/USD",
    ts_recv: float | None = None,
) -> str:
    """One recorded `trade` line in exactly the shape `record.py` writes.

    ``trades`` is ``(epoch seconds, price, qty, trade_id)``. The frame's
    ``ts_exchange`` is the first trade's timestamp, as the recorder sets it.
    """
    data = [
        {
            "symbol": pair,
            "side": "buy",
            "price": float(price),
            "qty": float(qty),
            "ord_type": "market",
            "trade_id": trade_id,
            "timestamp": iso(seconds),
        }
        for seconds, price, qty, trade_id in trades
    ]
    line = {
        "v": 1,
        "kind": "tick",
        "pair": pair,
        "channel": "trade",
        "ts_exchange": iso(trades[0][0]),
        "ts_recv": iso(ts_recv if ts_recv is not None else trades[0][0] + 0.04),
        "payload": {"channel": "trade", "type": "update", "data": data},
    }
    return json.dumps(line)


def book_frame(seconds: float, *, pair: str = "BTC/USD") -> str:
    """A non-trade line. Only its `ts_recv` matters: coverage is measured over every
    line in the recording, not only the trade frames."""
    line = {
        "v": 1,
        "kind": "tick",
        "pair": pair,
        "channel": "book",
        "ts_exchange": iso(seconds),
        "ts_recv": iso(seconds),
        "payload": {"channel": "book", "type": "update", "data": []},
    }
    return json.dumps(line)


def compact(line: str) -> str:
    """The same line as `orjson` writes it: no space after a colon or a comma.

    `record.py` uses `orjson`; these helpers use the standard library's `json`, which
    spaces its separators. The two must both be readable, which is the point of the
    parametrisation below.
    """
    return json.dumps(json.loads(line), separators=(",", ":"))


def write_recording(directory: Path, lines: list[str], name: str = "rec.jsonl") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def cover(start: int, end: int, *, step: int = 60) -> list[str]:
    """Book frames once a minute over `[start, end)`, so those minutes count as
    recorded. Without them every interval classifies as `not_recorded`."""
    return [book_frame(second) for second in range(start, end, step)]


# --------------------------------------------------------------------------- #
# The reduction itself
# --------------------------------------------------------------------------- #


def test_one_interval_of_trades_becomes_one_bar(build_archive: ModuleType, tmp_path: Path) -> None:
    path = write_recording(
        tmp_path / "raw",
        [
            trade_frame([(BASE_TS + 1, "100.0", "1.5", 1)]),
            trade_frame([(BASE_TS + 2, "105.0", "0.5", 2)]),
            trade_frame([(BASE_TS + 3, "95.0", "2.0", 3)]),
            trade_frame([(BASE_TS + 4, "101.0", "1.0", 4)]),
        ],
    )
    bars, _minutes, stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    bar = bars["BTC/USD"][BASE_TS]
    assert bar.open == Decimal("100.0")
    assert bar.high == Decimal("105.0")
    assert bar.low == Decimal("95.0")
    assert bar.close == Decimal("101.0")
    assert bar.volume == Decimal("5.0")
    assert bar.trades == 4
    assert stats["trades_reduced"] == 4


def test_money_never_passes_through_a_float(build_archive: ModuleType, tmp_path: Path) -> None:
    """`0.1 + 0.2` is the whole reason. Volume is summed across every trade in a bar,
    so a float there compounds, and the result reaches an order size."""
    path = write_recording(
        tmp_path / "raw",
        [trade_frame([(BASE_TS + n, "100.0", "0.1", n) for n in range(1, 4)])],
    )
    bars, _minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    volume = bars["BTC/USD"][BASE_TS].volume
    assert isinstance(volume, Decimal)
    assert volume == Decimal("0.3")
    assert str(volume) == "0.3"


def test_the_open_and_close_come_from_the_exchange_clock_not_the_file_order(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """A reconnect replays frames and two recorders interleave, so file order is not
    exchange order. An open taken from "the first row I saw" would be a different
    number depending on how the recording was stitched together."""
    path = write_recording(
        tmp_path / "raw",
        [
            trade_frame([(BASE_TS + 500, "150.0", "1", 3)]),  # latest, written first
            trade_frame([(BASE_TS + 100, "110.0", "1", 1)]),  # earliest
            trade_frame([(BASE_TS + 300, "130.0", "1", 2)]),
        ],
    )
    bars, _minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    bar = bars["BTC/USD"][BASE_TS]
    assert bar.open == Decimal("110.0")
    assert bar.close == Decimal("150.0")


def test_two_trades_in_the_same_second_are_ordered_by_trade_id(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """Kraken stamps several trades with one timestamp routinely. `trade_id` is the
    exchange's own sequence and is the only ordering available."""
    path = write_recording(
        tmp_path / "raw",
        [trade_frame([(BASE_TS + 10, "120.0", "1", 9), (BASE_TS + 10, "125.0", "1", 7)])],
    )
    bars, _minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    bar = bars["BTC/USD"][BASE_TS]
    assert bar.open == Decimal("125.0")
    assert bar.close == Decimal("120.0")


# --------------------------------------------------------------------------- #
# A quiet interval produces no row. Asserted on timestamps, not on a count.
# --------------------------------------------------------------------------- #


def test_a_quiet_interval_produces_no_row_at_all(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """The load-bearing one. A zero-volume bar at the previous close is interpolation
    wearing a different hat, and it fabricates the barrier touches Phase 4 labels."""
    path = write_recording(
        tmp_path / "raw",
        [
            trade_frame([(BASE_TS + 10, "100.0", "1", 1)]),
            # intervals 1 and 2 are silent
            trade_frame([(BASE_TS + 3 * INTERVAL_S + 10, "110.0", "1", 2)]),
        ],
    )
    bars, _minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    emitted = sorted(bars["BTC/USD"])
    assert emitted == [BASE_TS, BASE_TS + 3 * INTERVAL_S]
    assert BASE_TS + INTERVAL_S not in bars["BTC/USD"]
    assert BASE_TS + 2 * INTERVAL_S not in bars["BTC/USD"]


def test_the_written_csv_has_no_row_for_a_quiet_interval(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """Asserted on the file, because the bars dict and the file are two places a hole
    could be filled and only one of them is what the loader reads."""
    path = write_recording(
        tmp_path / "raw",
        [
            trade_frame([(BASE_TS + 10, "100.0", "1", 1)]),
            trade_frame([(BASE_TS + 3 * INTERVAL_S + 10, "110.0", "1", 2)]),
        ],
    )
    bars, _minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    out = tmp_path / "historical" / "BTCUSD_15.csv"
    rows = build_archive.write_archive(bars["BTC/USD"], out)
    assert rows == 2
    written = [line.split(",")[0] for line in out.read_text(encoding="utf-8").splitlines()]
    assert written == [str(BASE_TS), str(BASE_TS + 3 * INTERVAL_S)]


def test_a_row_count_alone_cannot_tell_a_filling_reducer_from_an_honest_one(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """Why the assertions above are on timestamps. Over a recording with no quiet
    intervals, a builder that fills holes emits exactly the same number of rows."""
    path = write_recording(
        tmp_path / "raw",
        [
            trade_frame([(BASE_TS + n * INTERVAL_S + 10, "100.0", "1", n)])
            for n in range(4)
        ],
    )
    bars, _minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert len(bars["BTC/USD"]) == 4
    assert sorted(bars["BTC/USD"]) == [BASE_TS + n * INTERVAL_S for n in range(4)]


# --------------------------------------------------------------------------- #
# Bar boundaries
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("offset", "expected_bucket"),
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
    build_archive: ModuleType, tmp_path: Path, offset: int, expected_bucket: int
) -> None:
    """The boundary cases individually, because an off-by-one interval is invisible in
    any aggregate and moves a trade into the neighbouring bar."""
    path = write_recording(
        tmp_path / "raw", [trade_frame([(BASE_TS + offset, "100.0", "1", 1)])]
    )
    bars, _minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert sorted(bars["BTC/USD"]) == [BASE_TS + expected_bucket * INTERVAL_S]


def test_a_sub_second_timestamp_does_not_move_a_trade_across_a_boundary(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """The last microsecond of a bar belongs to that bar. Rounding rather than flooring
    would put it in the next one."""
    path = write_recording(
        tmp_path / "raw",
        [trade_frame([(BASE_TS + INTERVAL_S - 0.000001, "100.0", "1", 1)])],
    )
    bars, _minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert sorted(bars["BTC/USD"]) == [BASE_TS]


# --------------------------------------------------------------------------- #
# De-duplication: frames yes, trades never
# --------------------------------------------------------------------------- #


def test_the_same_frame_from_two_recorders_is_counted_once(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """Two recorders write the same Kraken frame. `ts_recv` differs — it is each
    recorder's own arrival clock — so the lines are not byte-identical and only a
    digest over the payload can see that they are the same frame."""
    trades = [(BASE_TS + 10, "100.0", "2.5", 1)]
    path = write_recording(
        tmp_path / "raw",
        [
            trade_frame(trades, ts_recv=BASE_TS + 10.041),
            trade_frame(trades, ts_recv=BASE_TS + 10.087),
        ],
    )
    bars, _minutes, stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert stats["frame_duplicates_dropped"] == 1
    assert bars["BTC/USD"][BASE_TS].volume == Decimal("2.5")
    assert bars["BTC/USD"][BASE_TS].trades == 1


def test_hashing_the_whole_recorded_line_would_find_no_duplicate_at_all(
    build_archive: ModuleType,
) -> None:
    """Why "by exact bytes" means the bytes of the frame Kraken sent and not the bytes
    of the recorded line. This is the finding, asserted so it cannot quietly regress."""
    trades = [(BASE_TS + 10, "100.0", "2.5", 1)]
    first = trade_frame(trades, ts_recv=BASE_TS + 10.041)
    second = trade_frame(trades, ts_recv=BASE_TS + 10.087)
    assert first != second
    payload_first = json.loads(first)
    payload_second = json.loads(second)
    assert build_archive.frame_digest(
        payload_first["payload"], payload_first["ts_exchange"]
    ) == build_archive.frame_digest(payload_second["payload"], payload_second["ts_exchange"])


def test_two_identical_trades_inside_one_frame_are_both_kept(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """The mutation this file exists to kill. Two genuinely identical trades — same
    price, same quantity, same timestamp — arrive inside **one** frame, and
    de-duplicating at the trade level would silently delete half the volume."""
    path = write_recording(
        tmp_path / "raw",
        [
            trade_frame(
                [
                    (BASE_TS + 10, "100.0", "2.5", 11),
                    (BASE_TS + 10, "100.0", "2.5", 12),
                ]
            )
        ],
    )
    bars, _minutes, stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert bars["BTC/USD"][BASE_TS].volume == Decimal("5.0")
    assert bars["BTC/USD"][BASE_TS].trades == 2
    assert stats["frame_duplicates_dropped"] == 0


def test_a_repeated_trade_id_is_reported_and_never_dropped(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """A `trade_id` seen twice in two different frames would be a real double count and
    the reader is entitled to know. It is still not a licence to de-duplicate trades:
    the count is reported and the volume is left alone."""
    path = write_recording(
        tmp_path / "raw",
        [
            trade_frame([(BASE_TS + 10, "100.0", "1", 55)]),
            trade_frame([(BASE_TS + 20, "100.0", "1", 55)]),
        ],
    )
    bars, _minutes, stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert stats["repeated_trade_ids"] == 1
    assert stats["frame_duplicates_dropped"] == 0
    assert bars["BTC/USD"][BASE_TS].volume == Decimal("2")


# --------------------------------------------------------------------------- #
# Coverage: which holes mean what
# --------------------------------------------------------------------------- #


def test_an_interval_nobody_recorded_is_not_called_quiet(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """The finding that reshaped this script. A hole in a real Kraken archive can only
    mean no trades; a hole here can mean the recorder was down, and reading the second
    as the first makes a triple barrier walk across an outage."""
    covered = cover(BASE_TS, BASE_TS + INTERVAL_S) + cover(
        BASE_TS + 2 * INTERVAL_S, BASE_TS + 3 * INTERVAL_S
    )
    path = write_recording(
        tmp_path / "raw",
        [
            *covered,
            trade_frame([(BASE_TS + 10, "100.0", "1", 1)]),
            trade_frame([(BASE_TS + 2 * INTERVAL_S + 10, "110.0", "1", 2)]),
        ],
    )
    _bars, minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert (
        build_archive.classify_interval(
            BASE_TS, interval_s=INTERVAL_S, recorded_minutes=minutes
        )
        == "complete"
    )
    assert (
        build_archive.classify_interval(
            BASE_TS + INTERVAL_S, interval_s=INTERVAL_S, recorded_minutes=minutes
        )
        == "not_recorded"
    )


def test_a_partly_recorded_interval_is_neither_complete_nor_absent(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """The row that looks complete and is not: real trades over an interval the
    recorder only partly covered, so the volume is understated and the true high or low
    may never have been seen."""
    path = write_recording(
        tmp_path / "raw",
        [
            *cover(BASE_TS, BASE_TS + 300),  # five of the fifteen minutes
            trade_frame([(BASE_TS + 10, "100.0", "1", 1)]),
        ],
    )
    _bars, minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert (
        build_archive.classify_interval(
            BASE_TS, interval_s=INTERVAL_S, recorded_minutes=minutes
        )
        == "partial"
    )


def test_the_span_report_separates_the_three_kinds_of_hole(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """`missing_quiet` is the only figure that means what a hole in Kraken's archive
    means, and it is reported apart from the other two rather than summed with them."""
    covered = cover(BASE_TS, BASE_TS + 2 * INTERVAL_S) + cover(
        BASE_TS + 3 * INTERVAL_S, BASE_TS + 4 * INTERVAL_S
    )
    path = write_recording(
        tmp_path / "raw",
        [
            *covered,
            trade_frame([(BASE_TS + 10, "100.0", "1", 1)]),
            # interval 1 is fully recorded and had no trade: genuinely quiet
            # interval 2 was never recorded
            trade_frame([(BASE_TS + 3 * INTERVAL_S + 10, "110.0", "1", 2)]),
        ],
    )
    bars, minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    span = build_archive._span(bars["BTC/USD"], INTERVAL_S, minutes)
    assert span["missing_quiet_ts"] == [BASE_TS + INTERVAL_S]
    assert span["missing_not_recorded_ts"] == [BASE_TS + 2 * INTERVAL_S]
    assert span["missing_quiet"] == 1
    assert span["missing_not_recorded"] == 1


# --------------------------------------------------------------------------- #
# The recording is never written to
# --------------------------------------------------------------------------- #


def test_the_recording_is_left_byte_identical(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """Invariant 11: recorded data is immutable and corrections live in a derived
    layer. Asserted on the bytes, because a builder that rewrote a line in place would
    leave the file the same length."""
    raw = tmp_path / "raw"
    path = write_recording(
        raw,
        [
            trade_frame([(BASE_TS + 10, "100.0", "1", 1)]),
            trade_frame([(BASE_TS + 20, "100.0", "1", 1)]),
        ],
    )
    before = path.read_bytes()
    bars, _minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    build_archive.write_archive(bars["BTC/USD"], tmp_path / "historical" / "BTCUSD_15.csv")
    assert path.read_bytes() == before


def test_nothing_in_the_builder_opens_a_recording_for_writing() -> None:
    """The behavioural test above can only see the files it happened to make. This one
    sees every path through the module."""
    text = SCRIPT.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("#", '"')):
            continue
        assert 'open("w' not in stripped
        assert '.open("w"' not in stripped
        assert "'w'" not in stripped or "write_text" in stripped


# --------------------------------------------------------------------------- #
# The CSV shape the loader reads
# --------------------------------------------------------------------------- #


def test_the_written_file_loads_through_the_real_archive_loader(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """The end of the seam: what this script writes is what `load_archive` reads. A
    shape assertion here and a separate parse there would let the two drift."""
    from acsoe.research.historical import load_archive

    path = write_recording(
        tmp_path / "raw",
        [
            trade_frame([(BASE_TS + 10, "100.0", "1.5", 1)]),
            trade_frame([(BASE_TS + 2 * INTERVAL_S + 10, "110.0", "2.5", 2)]),
        ],
    )
    bars, _minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    out = tmp_path / "historical" / "BTCUSD_15.csv"
    build_archive.write_archive(bars["BTC/USD"], out)

    report = load_archive(out, interval_s=INTERVAL_S, pair="BTC/USD")
    assert report.row_count == 2
    assert report.gap_count == 1
    assert report.timestamps == (BASE_TS, BASE_TS + 2 * INTERVAL_S)
    assert report.first_close == "100.0"
    assert report.last_close == "110.0"


def test_the_file_has_no_header(build_archive: ModuleType, tmp_path: Path) -> None:
    """Kraken's archives have none, and `read_archive_rows` only tolerates one on line
    1 — a header written here would be parsed away silently and the file would still
    look right."""
    path = write_recording(tmp_path / "raw", [trade_frame([(BASE_TS + 10, "100.0", "1", 1)])])
    bars, _minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    out = tmp_path / "historical" / "BTCUSD_15.csv"
    build_archive.write_archive(bars["BTC/USD"], out)
    first = out.read_text(encoding="utf-8").splitlines()[0]
    assert first.split(",")[0].isdigit()
    assert len(first.split(",")) == 7


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0.00000001", "0.00000001"), ("1E-8", "0.00000001"), ("78804.0", "78804.0")],
)
def test_money_is_written_in_plain_decimal_never_scientific_notation(
    build_archive: ModuleType, value: str, expected: str
) -> None:
    """`str(Decimal("1E-8"))` is `1E-8`. `read_archive_rows` would parse it back, but no
    Kraken archive contains it and a file that only our own loader can read is not
    archive-shaped."""
    assert build_archive._plain(Decimal(value)) == expected


@pytest.mark.parametrize(
    ("pair", "interval", "expected"),
    [("BTC/USD", 900, "BTCUSD_15.csv"), ("ETH/USD", 3600, "ETHUSD_60.csv")],
)
def test_the_file_is_named_after_the_symbol_the_recording_used(
    build_archive: ModuleType, pair: str, interval: int, expected: str
) -> None:
    assert build_archive.archive_filename(pair, interval) == expected


# --------------------------------------------------------------------------- #
# Odds and ends the streaming reader has to survive
# --------------------------------------------------------------------------- #


def test_a_truncated_final_line_does_not_stop_the_build(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """`record.py` is still running while this reads, so the last line of the newest
    file can be half-written. Losing that one trade is correct; losing the build is
    not."""
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    path = raw / "rec.jsonl"
    good = trade_frame([(BASE_TS + 10, "100.0", "1", 1)])
    path.write_text(good + "\n" + good[: len(good) // 2], encoding="utf-8")
    bars, _minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert bars["BTC/USD"][BASE_TS].trades == 1


def test_non_trade_frames_are_ignored_by_the_reduction(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """A `_ack` line carries `"channel":"trade"` inside its payload and is not a trade
    frame. The prefilter is a byte search and cannot tell; the decoder must."""
    ack = json.dumps(
        {
            "v": 1,
            "kind": "tick",
            "pair": "BTC/USD",
            "channel": "_ack",
            "ts_exchange": None,
            "ts_recv": iso(BASE_TS),
            "payload": {"method": "subscribe", "result": {"channel": "trade"}, "success": True},
        }
    )
    path = write_recording(
        tmp_path / "raw", [ack, trade_frame([(BASE_TS + 10, "100.0", "1", 1)])]
    )
    _bars, _minutes, stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert stats["trade_frames_read"] == 1


def test_only_the_requested_pairs_are_reduced(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    path = write_recording(
        tmp_path / "raw",
        [
            trade_frame([(BASE_TS + 10, "100.0", "1", 1)], pair="BTC/USD"),
            trade_frame([(BASE_TS + 10, "50.0", "1", 2)], pair="ETH/USD"),
        ],
    )
    bars, _minutes, _stats = build_archive.build_bars(
        [path], interval_s=INTERVAL_S, pairs=("ETH/USD",)
    )
    assert sorted(bars) == ["ETH/USD"]


# --------------------------------------------------------------------------- #
# The cheap prefilter and the exact check must agree
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("style", ["spaced", "compact"])
def test_a_trade_frame_is_found_whichever_way_its_json_was_written(
    build_archive: ModuleType, tmp_path: Path, style: str
) -> None:
    """The defect this parametrisation exists for, and it failed silently.

    The prefilter is a raw byte search run before any decoding, so it is a **second,
    weaker definition** of "this is a trade frame". It used to be
    `b'"channel":"trade"'`, which matched only `orjson`'s compact separators: one space
    after the colon and the builder read every byte of a 7 GB recording, found zero
    trade frames, and reported success over an empty archive. A prefilter narrower than
    the check it stands in front of fails invisibly.
    """
    line = trade_frame([(BASE_TS + 10, "100.0", "1.5", 1)])
    path = write_recording(tmp_path / "raw", [compact(line) if style == "compact" else line])
    bars, _minutes, stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert stats["trade_frames_read"] == 1
    assert bars["BTC/USD"][BASE_TS].volume == Decimal("1.5")


@pytest.mark.parametrize("style", ["spaced", "compact"])
def test_coverage_is_measured_whichever_way_its_json_was_written(
    build_archive: ModuleType, tmp_path: Path, style: str
) -> None:
    """The same defect one field along. `ts_recv` is read out of the undecoded bytes
    because coverage is measured over every line in a 22-million-line recording, and
    matching `b'"ts_recv":"'` made the whole coverage classification depend on the
    serialiser. Every interval would have classified as `not_recorded`, which reads as
    "the recorder was down for the entire history" — plausible enough to be believed."""
    lines = cover(BASE_TS, BASE_TS + INTERVAL_S)
    if style == "compact":
        lines = [compact(line) for line in lines]
    path = write_recording(tmp_path / "raw", lines)
    _bars, minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert (
        build_archive.classify_interval(
            BASE_TS, interval_s=INTERVAL_S, recorded_minutes=minutes
        )
        == "complete"
    )


def test_a_line_with_no_ts_recv_at_all_contributes_no_coverage(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """A bounded search, so a line without the field cannot walk into the next one and
    return sixteen characters of something else as a minute."""
    path = write_recording(tmp_path / "raw", ['{"v":1,"kind":"tick","channel":"book"}'])
    _bars, minutes, _stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert minutes == frozenset()


def test_the_same_frame_with_its_keys_in_a_different_order_is_one_frame(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """`sort_keys=True` in `frame_digest`, and the only test that can see it.

    Two writers can serialise one object's keys in different orders while meaning the
    same frame. Every other fixture in this file builds its frames with one `json.dumps`
    call, so the two copies of a duplicate always had their keys in the same order and a
    mutation dropping `sort_keys` survived all 38 tests. A canonicaliser is invisible to
    any test whose inputs come from one generator: to test one, the two forms have to be
    built by hand.
    """
    line = json.loads(trade_frame([(BASE_TS + 10, "100.0", "2.5", 1)]))
    reordered = dict(reversed(list(line["payload"].items())))
    assert list(reordered) != list(line["payload"])

    assert build_archive.frame_digest(
        line["payload"], line["ts_exchange"]
    ) == build_archive.frame_digest(reordered, line["ts_exchange"])

    second = dict(line)
    second["payload"] = reordered
    second["ts_recv"] = iso(BASE_TS + 10.09)
    path = write_recording(tmp_path / "raw", [json.dumps(line), json.dumps(second)])
    bars, _minutes, stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert stats["frame_duplicates_dropped"] == 1
    assert bars["BTC/USD"][BASE_TS].volume == Decimal("2.5")


def test_two_genuinely_different_frames_are_not_collapsed(
    build_archive: ModuleType, tmp_path: Path
) -> None:
    """The other direction, so the canonicalisation above cannot be over-applied: a
    digest that ignored the trade data would make every frame identical and the whole
    archive one bar."""
    path = write_recording(
        tmp_path / "raw",
        [
            trade_frame([(BASE_TS + 10, "100.0", "1", 1)]),
            trade_frame([(BASE_TS + 11, "100.0", "1", 2)]),
        ],
    )
    bars, _minutes, stats = build_archive.build_bars([path], interval_s=INTERVAL_S)
    assert stats["frame_duplicates_dropped"] == 0
    assert bars["BTC/USD"][BASE_TS].trades == 2
