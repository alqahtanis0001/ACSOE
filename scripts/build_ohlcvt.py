#!/usr/bin/env python
"""Reduce the operator's Kraken time-and-sales archive into 15-minute OHLCVT CSVs.

    python scripts/build_ohlcvt.py --plan            # what would be built, and what it costs
    python scripts/build_ohlcvt.py --write           # build every qualifying pair
    python scripts/build_ohlcvt.py --pairs XBTUSD --write

Spec 54 as amended on 2026-09-11. The operator supplied Kraken's own published trade
history — roughly 27 GB across 1,119 pair files in
`data/historical/KRAKEN_TimeAndSales_Combined/` (`1INCH` to `HONEY`) and
`data/historical/TimeAndSales_Combined/` (`HPOS10I` onward). This reduces the pairs we
need into the seven-column shape `acsoe.research.historical.load_archive` reads.

## Which pairs, and why that is no longer a list in this file

It **enumerates the archive**. It used to carry `DEFAULT_PAIRS = ("XBTUSD", "ETHUSD",
"SOLUSD")`, so three of 1,119 pairs were ever built, and the other 1,116 sat on disk
unread while every downstream claim about breadth quietly meant three. A hardcoded pair
list in a script whose whole job is reading an archive is a cap disguised as a default.

The selection rule is two conditions, both stated rather than assumed:

* **Quote currency.** The file name ends in the quote suffix (`USD` by default). The
  archive spells the pair the way Kraken does, so `XBTUSD` is USD-quoted and `XBTUSDT`
  is not — and the suffix test says so without a translation table.
* **At least `--min-years` of history**, measured as the span between the first and the
  last trade in the file, read from the two ends without parsing the middle. Two years
  is the default because a walk-forward with any meaningful number of folds cannot be
  cut from less, and a pair that cannot support the evaluation is a pair whose bars
  would only ever be discarded later — after the disk and the hours had been spent.

Neither condition is a judgement about the pair. Both are recorded per pair in the
provenance, together with the ones that were rejected and by which condition, so
"why is this pair not in the dataset" is answerable without re-running anything.

## What the source is

**Time-and-sales, not OHLCVT.** Three columns, no header, `timestamp,price,volume`, with
the timestamp in whole epoch seconds. One row is one trade. So the reduction to bars is
still ours — that is written down rather than implied — but it now runs on Kraken's own
published trade history rather than on our three-day WebSocket recording, and the `T` of
OHLCVT becomes a **real count of trades in the interval** rather than something we had no
way to know.

## One whole class of hazard disappeared with the source, and here is why

`scripts/build_archive.py`, which this supersedes, had to separate three kinds of hole:
an interval with no trades, an interval nobody was recording, and a row built from an
interval the recorder only partly covered. It measured them, and on the recording
`missing_quiet` was **zero on all three pairs** — every hole was an outage.

Against Kraken's published archive that distinction does not exist. **Kraken never stops
watching, so a hole can only mean no trades occurred**, which is exactly what
`research/historical.py` assumes and what makes the triple barrier safe to walk across
one. `missing_quiet` is therefore the only category here, and the provenance says the
other two are gone and why, rather than dropping them silently.

## A quiet interval still produces no row

Nothing is forward-filled, resampled or interpolated, and there is no flag that asks for
it. A zero-volume bar at the previous close is interpolation wearing a different hat and
it fabricates the barrier touches Phase 4 labels.

## Streaming, and never sorting

`XBTUSD.csv` is 2.7 GB and `ETHUSD.csv` is 1.7 GB. Every file is read one line at a time
and no file is ever read into memory or sorted. Bars are emitted as the stream passes
each interval and only a short window of open bars is held, so memory does not grow with
the length of the history.

Rows arriving out of order are **counted and reported**, never silently absorbed and
never silently dropped: `late_rows` in the provenance is the number of trades that
arrived after their interval had already been written out, and a non-zero value means
the bars it touched are short. Kraken's export is ordered and it has been zero in
practice; the counter exists so that "it was ordered" stays a measurement rather than an
assumption.

## Never write into the source

Invariant 11, in its strongest form: 27 GB the operator obtained once, treated as
read-only. Nothing here ever opens a source file for writing.

Output goes to the **top level** of `data/historical/`, never inside either source
directory. The operator's own files live one level down, in
`KRAKEN_TimeAndSales_Combined/` and `TimeAndSales_Combined/`, so source and derived
never share a directory — and the derived files carry an `_15` suffix the source files
do not, so `XBTUSD.csv` (three-column time-and-sales) and `XBTUSD_15.csv` (seven-column
OHLCVT) cannot be confused for one another even if they ever did. Two archives in one
directory under one naming convention is a silent wrong-source defect, and that is the
thing being avoided rather than the directory nesting itself.

The top level rather than a subdirectory because that is where `scripts/verify.py`'s
`replay_full_archive` criterion looks — a non-recursive `data/historical/*.csv`, which
is also what keeps it from sweeping up 1,119 source files. Agreement with the criterion
is worth more here than a tidier tree.

## The file may still be being extracted

Extraction was still running when the archive first appeared: one directory grew from
408 to 605 files in a few minutes and `XBTUSD.csv` had not landed yet. A truncated final
line is not a parse error — it is a silently short last bar. So this checks that a pair
file's size is stable before reading it, and refuses rather than guessing when it is not.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

DEFAULT_SOURCE_DIRS: Final = (
    Path("data") / "historical" / "KRAKEN_TimeAndSales_Combined",
    Path("data") / "historical" / "TimeAndSales_Combined",
)
DEFAULT_OUT_DIR: Final = Path("data") / "historical"
DEFAULT_INTERVAL_S: Final = 900

#: There is deliberately no default pair list. See the docstring: the three that used
#: to be here were a cap on the whole project wearing a default's clothes.
DEFAULT_QUOTE_SUFFIX: Final = "USD"
DEFAULT_MIN_YEARS: Final = 2.0
SECONDS_PER_YEAR: Final = 365.25 * 24 * 60 * 60

PROVENANCE_FILENAME: Final = "PROVENANCE.json"

#: Bytes of a built CSV per bar, measured on the three pairs built on 2026-09-11
#: (20,769,108 B / 361,584 rows, 19,329,563 / 339,125, 8,526,539 / 158,539). Used only
#: to estimate the cost of a build before it runs; nothing reads it afterwards.
MEASURED_BYTES_PER_BAR: Final = 57

#: Bytes of source per trade, measured the same way (XBTUSD.csv, 2.7 GB / 92,716,525
#: trades). Used only to turn a file size into an estimated trade count in `--plan`.
MEASURED_BYTES_PER_TRADE: Final = 29

#: `barriers.timeout_bars` in `config/default.yaml`. The last bars of every series
#: cannot be labelled, because the timeout horizon runs off the end of the data — so a
#: labelled-row estimate that ignores it overstates by exactly this much per pair.
LABEL_HORIZON_BARS: Final = 48

#: How many intervals of already-passed bars stay open before being written out. Kraken's
#: export is time-ordered, so in practice nothing arrives late at all; this exists so
#: that a handful of out-of-order rows are absorbed rather than silently producing two
#: bars with the same timestamp, and anything older than the window is counted.
OPEN_BAR_WINDOW: Final = 8

#: How many rows a dry run keeps, to show what it would have written.
PREVIEW_ROWS: Final = 3

PROVENANCE_NOTE: Final = (
    "Bars are reduced from Kraken's own published time-and-sales archive, supplied by "
    "the operator: three columns, timestamp,price,volume, one row per trade. The bars "
    "themselves are NOT Kraken's published OHLCVT - the reduction to 15-minute "
    "intervals is ours - but every price and every quantity in them is a real trade "
    "Kraken published, and the `trades` column is a real count of trades in the "
    "interval. Confirming these bars against Kraken's own published OHLCVT is a --live "
    "task."
)

NO_INTERPOLATION_NOTE: Final = (
    "An interval in which nothing traded has NO row here, exactly as a Kraken archive "
    "contains only intervals in which trades occurred. Nothing is forward-filled, "
    "resampled or interpolated, and no flag asks for it."
)

COVERAGE_NOTE: Final = (
    "Every hole here means no trades occurred. That is a stronger statement than the "
    "archive built from data/raw/ by scripts/build_archive.py could make, and the "
    "difference is the source rather than the code: our WebSocket recorder stopped - "
    "restarts, dropped connections, one disk-full - so a hole there was usually an "
    "outage, measured at missing_quiet=0 on all three pairs. Kraken never stops "
    "watching. The `missing_not_recorded` and `partial_rows` categories that artefact "
    "carried do not exist for this one and are absent rather than reported as zero."
)


class Bar:
    """One interval's accumulating OHLCVT.

    Open and close are decided by the trade's timestamp with **file order** breaking a
    tie, which is the only ordering time-and-sales offers: there is no trade id in this
    format, and two trades stamped the same second are routine. That matches engine 3's
    `build_candles`, which also breaks ties by input order.
    """

    __slots__ = ("close", "close_key", "high", "low", "open", "open_key", "trades", "ts", "volume")

    def __init__(self, ts: int, price: Decimal, qty: Decimal, key: tuple[int, int]) -> None:
        self.ts = ts
        self.open = price
        self.close = price
        self.high = price
        self.low = price
        self.volume = qty
        self.trades = 1
        self.open_key = key
        self.close_key = key

    def add(self, price: Decimal, qty: Decimal, key: tuple[int, int]) -> None:
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        if key < self.open_key:
            self.open_key = key
            self.open = price
        if key > self.close_key:
            self.close_key = key
            self.close = price
        self.volume += qty
        self.trades += 1

    def csv_row(self) -> str:
        return ",".join(
            (
                str(self.ts),
                plain(self.open),
                plain(self.high),
                plain(self.low),
                plain(self.close),
                plain(self.volume),
                str(self.trades),
            )
        )


def plain(value: Decimal) -> str:
    """A `Decimal` as plain decimal text, never scientific notation.

    `str(Decimal("1E-8"))` is `1E-8`. `read_archive_rows` would parse that back, but no
    Kraken archive contains it, and a file only our own loader can read is not
    archive-shaped.
    """
    return f"{value:f}"


def find_pair_file(pair: str, directories: tuple[Path, ...]) -> Path:
    """Locate one pair's time-and-sales file across the operator's two directories.

    The archive is split alphabetically, so which directory a pair lives in is not
    something a caller should have to know. Raises rather than returning `None`: a
    missing pair is a stop, not a series with no rows in it.
    """
    for directory in directories:
        candidate = directory / f"{pair}.csv"
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(directory) for directory in directories)
    raise FileNotFoundError(f"no time-and-sales file for {pair!r} under: {searched}")


class ArchivePair:
    """One pair file in the operator's archive, described from its two ends.

    `first_ts` and `last_ts` are read from the first and last lines only. The middle of
    the file is not touched, so describing all 1,119 pairs costs a few seconds rather
    than a full pass over 27 GB.

    Not a ``@dataclass``: this script is loaded by path in
    `tests/scripts/test_build_ohlcvt.py`, and a module executed that way is absent from
    ``sys.modules``, where `dataclasses` looks its own module up while processing the
    class. The decorator raises ``AttributeError: 'NoneType' object has no attribute
    '__dict__'`` at import time, and every test in the file then errors in its fixture.
    """

    __slots__ = ("first_ts", "last_ts", "pair", "path", "size_bytes")

    def __init__(
        self,
        *,
        pair: str,
        path: Path,
        size_bytes: int,
        first_ts: int | None,
        last_ts: int | None,
    ) -> None:
        self.pair = pair
        self.path = path
        self.size_bytes = size_bytes
        self.first_ts = first_ts
        self.last_ts = last_ts

    @property
    def span_s(self) -> int:
        if self.first_ts is None or self.last_ts is None:
            return 0
        return max(0, self.last_ts - self.first_ts)

    @property
    def span_years(self) -> float:
        return self.span_s / SECONDS_PER_YEAR

    @property
    def intervals(self) -> int:
        """Bars the span could hold if every interval had a trade. The ceiling on rows."""
        return self.span_s // DEFAULT_INTERVAL_S + 1 if self.span_s else 0

    @property
    def estimated_trades(self) -> int:
        return self.size_bytes // MEASURED_BYTES_PER_TRADE


def first_and_last_timestamp(path: Path, *, tail_bytes: int = 4096) -> tuple[int | None, int | None]:
    """The epoch seconds of the first and last parsable row, without reading the file.

    The last line is found by seeking to the end, which is why this is cheap. A file
    whose final line is truncated — extraction still running — gives up that line and
    uses the one before it, so a half-written row cannot silently shorten a span.
    """
    size = path.stat().st_size
    if size == 0:
        return None, None
    first: int | None = None
    last: int | None = None
    with path.open("rb") as handle:
        for raw in handle:
            first = _timestamp_of(raw)
            if first is not None:
                break
        # Seek near the end and iterate what is left, rather than `read()` the tail.
        # The bytes touched are the same; the difference is that this file then calls
        # `read` nowhere at all, which is what `test_no_source_file_is_ever_read_whole_
        # or_sorted` checks over the parsed module — and a check that cannot tell
        # `read(4096)` from `read()` is worth more kept literal than argued with.
        handle.seek(max(0, size - tail_bytes))
        for raw in handle:
            stamp = _timestamp_of(raw)
            if stamp is not None:
                last = stamp
    return first, last


def _timestamp_of(raw: bytes) -> int | None:
    parts = raw.strip().split(b",")
    if len(parts) < 3:
        return None
    try:
        return int(float(parts[0]))
    except ValueError:
        return None


def describe_archive(directories: Sequence[Path], *, quote_suffix: str) -> list[ArchivePair]:
    """Every pair file in the archive that is quoted in `quote_suffix`, described.

    Sorted by pair, so two runs of `--plan` are comparable line for line and a
    diff between them shows what the archive gained rather than how it was walked.
    """
    found: dict[str, ArchivePair] = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.csv")):
            pair = path.stem
            if not pair.endswith(quote_suffix) or pair in found:
                continue
            first, last = first_and_last_timestamp(path)
            found[pair] = ArchivePair(
                pair=pair,
                path=path,
                size_bytes=path.stat().st_size,
                first_ts=first,
                last_ts=last,
            )
    return [found[pair] for pair in sorted(found)]


def select_pairs(
    described: Sequence[ArchivePair], *, min_years: float
) -> tuple[list[ArchivePair], list[ArchivePair]]:
    """Split the described archive into what qualifies and what does not.

    Both halves are returned. The rejected half is written into the provenance rather
    than discarded, because "1,119 files, 413 USD-quoted, 300 with two years" is a
    fact about the dataset and the reader should not have to re-derive it.
    """
    kept = [pair for pair in described if pair.span_years >= min_years]
    rejected = [pair for pair in described if pair.span_years < min_years]
    return kept, rejected


def wait_for_stable_size(path: Path, *, settle_s: float = 2.0, attempts: int = 3) -> int:
    """The file's size, once it has stopped changing. Raises if it has not.

    Extraction of this archive was still running when it first appeared, and a file
    still being written ends in a half-line. That is not a parse error — the truncated
    row is skipped — it is a **silently short final bar**, which is exactly the kind of
    defect this phase exists to keep out. So the size is checked rather than assumed,
    and an unstable file stops the build for that pair instead of quietly producing a
    wrong last row.
    """
    previous = path.stat().st_size
    for _ in range(attempts):
        time.sleep(settle_s)
        current = path.stat().st_size
        if current == previous:
            return current
        previous = current
    raise RuntimeError(
        f"{path} is still growing ({previous} bytes and counting). Extraction has not "
        "finished; a file still being written ends in a half-line and produces a "
        "silently short final bar. Re-run when it has settled."
    )


def iter_trades(path: Path, counters: dict[str, Any]) -> Iterator[tuple[int, Decimal, Decimal]]:
    """Stream `(timestamp, price, volume)` out of one time-and-sales file.

    One line at a time. Never `read()`, never `readlines()`, never sorted: `XBTUSD.csv`
    is 2.7 GB.

    Money is built from the literal text with `Decimal`, never via `float`. A price that
    has been through binary floating point is not the price that traded, and volume is
    summed across every trade in an interval so a float there compounds.

    A malformed line — including the half-written final line of a file still being
    extracted — is skipped rather than raising, and `counters["malformed_rows"]` is
    incremented. Counted, not swallowed: a skipped row that nothing reports is a bar
    quietly missing volume, and the count is what makes the silence visible.
    """
    with path.open("r", encoding="utf-8", newline="") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 3:
                counters["malformed_rows"] += 1
                continue
            try:
                seconds = int(float(parts[0]))
                price = Decimal(parts[1])
                volume = Decimal(parts[2])
            except (ValueError, InvalidOperation):
                counters["malformed_rows"] += 1
                continue
            yield seconds, price, volume


def reduce_pair(
    path: Path, *, interval_s: int, out: Path | None
) -> dict[str, Any]:
    """Reduce one pair's trades to 15-minute bars, writing them as they close.

    Bars are written in ascending timestamp order as the stream passes them, so memory
    is bounded by :data:`OPEN_BAR_WINDOW` rather than by the length of the history. A
    bar is created only for an interval a trade actually fell in — the range between two
    bars is never walked — which is what makes "a quiet interval produces no row" true by
    construction rather than by a filtering step somebody could later remove.
    """
    if interval_s <= 0:
        raise ValueError("interval_s must be positive")

    open_bars: dict[int, Bar] = {}
    written: list[str] = []
    stats: dict[str, Any] = {
        "trades": 0,
        "malformed_rows": 0,
        "out_of_order_rows": 0,
        "late_rows": 0,
        "rows": 0,
        "first_ts": None,
        "last_ts": None,
        "first_trade_ts": None,
        "last_trade_ts": None,
    }
    handle = None
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        handle = out.open("w", encoding="utf-8", newline="\n")

    def flush(up_to: int) -> None:
        for ts in sorted(bucket for bucket in open_bars if bucket <= up_to):
            bar = open_bars.pop(ts)
            row = bar.csv_row()
            stats["rows"] += 1
            if stats["first_ts"] is None:
                stats["first_ts"] = ts
            stats["last_ts"] = ts
            if handle is not None:
                handle.write(row + "\n")
            elif len(written) < PREVIEW_ROWS:
                # Only the preview is kept. Holding every row of a dry run was
                # affordable at three pairs and is not at four hundred: the archive's
                # largest pair alone is 361,584 rows.
                written.append(row)

    try:
        highest_bucket = -1
        previous_ts = -1
        for sequence, (seconds, price, volume) in enumerate(iter_trades(path, stats)):
            stats["trades"] += 1
            if stats["first_trade_ts"] is None:
                stats["first_trade_ts"] = seconds
            stats["last_trade_ts"] = seconds
            if seconds < previous_ts:
                stats["out_of_order_rows"] += 1
            previous_ts = seconds

            bucket = (seconds // interval_s) * interval_s
            if bucket > highest_bucket:
                highest_bucket = bucket
                flush(highest_bucket - OPEN_BAR_WINDOW * interval_s)
            bar = open_bars.get(bucket)
            if bar is None:
                if stats["last_ts"] is not None and bucket <= stats["last_ts"]:
                    # Its interval has already been written out. Counted, never
                    # silently dropped and never appended as a second row with a
                    # timestamp the file already carries.
                    stats["late_rows"] += 1
                    continue
                open_bars[bucket] = Bar(bucket, price, volume, (seconds, sequence))
            else:
                bar.add(price, volume, (seconds, sequence))
        flush(highest_bucket)
    finally:
        if handle is not None:
            handle.close()

    stats["expected_intervals"] = (
        ((stats["last_ts"] - stats["first_ts"]) // interval_s) + 1
        if stats["first_ts"] is not None and stats["last_ts"] is not None
        else 0
    )
    stats["missing_quiet"] = stats["expected_intervals"] - stats["rows"]
    for key in ("first_ts", "last_ts"):
        value = stats[key]
        stats[f"{key}_iso"] = (
            datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")
            if value is not None
            else None
        )
    if out is None:
        stats["preview"] = written[:PREVIEW_ROWS]
    return stats


def archive_filename(pair: str, interval_s: int) -> str:
    """`XBTUSD` at 900s becomes `XBTUSD_15.csv`.

    The pair is Kraken's own spelling, taken from the source file name and never
    translated — this archive came from Kraken and `XBTUSD` is what Kraken calls it.
    The `_15` suffix is what the source files do not have, so a derived file can never
    be mistaken for a source file even if the two ever sit in one directory.
    """
    return f"{pair}_{interval_s // 60}.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="build_ohlcvt.py",
        description=(
            "Reduce Kraken's published time-and-sales archive into 15-minute OHLCVT "
            "CSVs that acsoe.research.historical.load_archive can read."
        ),
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        default=None,
        help=(
            "build only these pairs, by their archive spelling. Omit it and every pair "
            "in the archive that clears --quote-suffix and --min-years is built."
        ),
    )
    parser.add_argument(
        "--quote-suffix",
        default=DEFAULT_QUOTE_SUFFIX,
        help="a pair qualifies when its archive name ends in this",
    )
    parser.add_argument(
        "--min-years",
        type=float,
        default=DEFAULT_MIN_YEARS,
        help="a pair qualifies when its first and last trade are this far apart",
    )
    parser.add_argument(
        "--source-dir",
        nargs="+",
        default=[str(directory) for directory in DEFAULT_SOURCE_DIRS],
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--interval-s", type=int, default=DEFAULT_INTERVAL_S)
    parser.add_argument(
        "--write",
        action="store_true",
        help="without this the script reports what it would write and touches nothing",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help=(
            "describe what would be built and what it would cost — pairs, bars, disk "
            "and wall clock — by reading the two ends of each file, and exit without "
            "reducing anything. A dry run without --plan still reads all 27 GB."
        ),
    )
    parser.add_argument(
        "--measure",
        action="store_true",
        help=(
            "with --plan, reduce a few real pairs to measure this machine's throughput "
            "and the fill ratio, instead of reporting the ceiling and an unknown wall "
            "clock"
        ),
    )
    parser.add_argument(
        "--measure-pairs",
        type=int,
        default=6,
        help="how many pairs --measure reduces, spread across the size distribution",
    )
    parser.add_argument(
        "--measure-size-cap-mb",
        type=float,
        default=150.0,
        help="the largest pair --measure is allowed to reduce, so the sample is cheap",
    )
    parser.add_argument(
        "--skip-stability-check",
        action="store_true",
        help=(
            "read a source file without first confirming its size has settled. Only for "
            "an archive known to be complete: a file still being extracted ends in a "
            "half-line and produces a silently short final bar."
        ),
    )
    return parser.parse_args(argv)


def measure_sample(
    kept: Sequence[ArchivePair], *, interval_s: int, count: int, size_cap: int
) -> tuple[float, list[tuple[str, float]]]:
    """Reduce a few real pairs and return `(bytes per second, fill ratios)`.

    Two things are measured here and neither can be reasoned out from the file sizes.

    **Throughput**, because estimating a build's wall clock from a rate somebody
    measured on another machine is how a nine-hour job gets started as if it were one.

    **Fill ratio** — bars actually produced over intervals the span could hold — because
    the alternative is to report the ceiling as the answer. The ceiling assumes every
    15-minute interval of every pair's life contained a trade, which is true of BTC and
    nowhere near true of the tail: a pair that trades in business hours is empty two
    thirds of the time and produces no row for any of it. The pairs sampled are spread
    across the size distribution below `size_cap` so the ratio is not read off the
    liquid end alone, and every sampled pair's own ratio is reported rather than only
    the median, because the spread between them is the honest error bar.
    """
    affordable = [pair for pair in kept if pair.size_bytes <= size_cap]
    if not affordable or count <= 0:
        return 0.0, []
    ordered = sorted(affordable, key=lambda pair: pair.size_bytes)
    step = max(1, len(ordered) // count)
    chosen = ordered[::step][:count]
    measured: list[tuple[str, float]] = []
    total_bytes = 0
    started = time.monotonic()
    for pair in chosen:
        stats = reduce_pair(pair.path, interval_s=interval_s, out=None)
        total_bytes += pair.size_bytes
        expected = stats["expected_intervals"]
        if expected:
            measured.append((pair.pair, stats["rows"] / expected))
    elapsed = max(1e-6, time.monotonic() - started)
    return total_bytes / elapsed, measured


def report_plan(
    kept: Sequence[ArchivePair],
    rejected: Sequence[ArchivePair],
    *,
    quote_suffix: str,
    min_years: float,
    interval_s: int,
    throughput_bps: float | None,
    fills: Sequence[tuple[str, float]] = (),
) -> None:
    """What a full build would produce and what it would cost. Estimates, named as such."""
    total_bytes = sum(pair.size_bytes for pair in kept)
    # A pair cannot have more bars than it has trades, and it cannot have more than one
    # per interval of its life. The smaller of the two is the ceiling: it still assumes
    # every interval traded, which no pair below the top of the book manages.
    ceiling_bars = sum(min(pair.intervals, pair.estimated_trades) for pair in kept)
    fill = statistics.median(ratio for _pair, ratio in fills) if fills else 1.0
    estimate_bars = int(ceiling_bars * fill)
    labelled = max(0, estimate_bars - LABEL_HORIZON_BARS * len(kept))
    print(
        f"archive: {len(kept) + len(rejected)} pairs ending in {quote_suffix!r}, "
        f"{len(kept)} with at least {min_years:g} years of history, "
        f"{len(rejected)} without",
        file=sys.stderr,
    )
    print(
        f"to read: {total_bytes / 1e9:.1f} GB of source, "
        f"~{sum(pair.estimated_trades for pair in kept) / 1e6:.0f}M trades",
        file=sys.stderr,
    )
    if fills:
        print(
            "measured fill (bars produced / intervals in span), on "
            + ", ".join(f"{pair} {ratio:.0%}" for pair, ratio in fills)
            + f" -> using {fill:.0%}",
            file=sys.stderr,
        )
    else:
        print(
            "fill ratio not measured, so the figures below are the ceiling and the real "
            "counts will be lower. Re-run --plan --measure.",
            file=sys.stderr,
        )
    print(
        f"to write: ~{estimate_bars:,} bars ({ceiling_bars:,} is the ceiling, every "
        f"{interval_s // 60}-minute interval of every span holding a trade), "
        f"{estimate_bars * MEASURED_BYTES_PER_BAR / 1e9:.2f} GB of CSV "
        f"({ceiling_bars * MEASURED_BYTES_PER_BAR / 1e9:.2f} GB at the ceiling)",
        file=sys.stderr,
    )
    print(
        f"labelled rows: ~{labelled:,} — the estimate above less {LABEL_HORIZON_BARS} "
        f"bars per pair, which the triple barrier cannot label because its timeout "
        f"horizon runs off the end of each series",
        file=sys.stderr,
    )
    if throughput_bps is None:
        print(
            "wall clock: not measured. Re-run --plan --measure to time one real "
            "reduction on this machine.",
            file=sys.stderr,
        )
    else:
        seconds = total_bytes / throughput_bps
        print(
            f"wall clock: ~{seconds / 3600:.1f} h at the measured "
            f"{throughput_bps / 1e6:.1f} MB/s, single process, one pair at a time",
            file=sys.stderr,
        )
    if kept:
        longest = max(kept, key=lambda pair: pair.size_bytes)
        print(
            f"largest pair: {longest.pair} at {longest.size_bytes / 1e9:.2f} GB, "
            f"{longest.span_years:.1f} years",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    import json

    args = parse_args(argv)
    interval = args.interval_s
    if interval <= 0:
        print("--interval-s must be positive", file=sys.stderr)
        return 2

    directories = tuple(Path(directory) for directory in args.source_dir)
    out_dir = Path(args.out_dir)

    described = describe_archive(directories, quote_suffix=args.quote_suffix)
    kept, rejected = select_pairs(described, min_years=args.min_years)
    selection: dict[str, Any]
    if args.pairs is not None:
        selected = list(args.pairs)
        selection = {"rule": "explicit --pairs", "pairs": selected}
    else:
        selected = [pair.pair for pair in kept]
        selection = {
            "rule": (
                f"every archive file ending in {args.quote_suffix!r} whose first and "
                f"last trade are at least {args.min_years:g} years apart"
            ),
            "quote_suffix": args.quote_suffix,
            "min_years": args.min_years,
            "scanned": len(described),
            "selected": len(kept),
            "rejected_too_short": {
                pair.pair: round(pair.span_years, 3) for pair in rejected
            },
        }

    if args.plan:
        throughput: float | None = None
        fills: list[tuple[str, float]] = []
        if args.measure and kept:
            print(
                f"reducing {args.measure_pairs} sample pairs under "
                f"{args.measure_size_cap_mb:g} MB, for throughput and fill ...",
                file=sys.stderr,
            )
            throughput, fills = measure_sample(
                kept,
                interval_s=interval,
                count=args.measure_pairs,
                size_cap=int(args.measure_size_cap_mb * 1e6),
            )
        report_plan(
            kept,
            rejected,
            quote_suffix=args.quote_suffix,
            min_years=args.min_years,
            interval_s=interval,
            throughput_bps=throughput,
            fills=fills,
        )
        return 0

    provenance: dict[str, Any] = {
        "schema_version": 1,
        "built_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "built_by": "scripts/build_ohlcvt.py",
        "interval_s": interval,
        "source": "Kraken published time-and-sales, supplied by the operator",
        "source_dirs": [str(directory) for directory in directories],
        "provenance": PROVENANCE_NOTE,
        "interpolation": NO_INTERPOLATION_NOTE,
        "coverage": COVERAGE_NOTE,
        # The one machine-readable form of the paragraph above, so a consumer does not
        # have to parse prose to learn whether it may walk a barrier across a hole.
        # `research/replay.py` reads exactly this key and reports `unknown` when it is
        # absent — never "quiet", which is the assumption that costs the labels.
        "holes_mean_no_trades": True,
        "has_order_book": False,
        "has_spread": False,
        # Which pairs were built and why those. Written down because "the dataset is
        # every USD pair with two years of history" is a claim a reader should be able
        # to check against the artefact rather than against a commit message.
        "selection": selection,
        "pairs": {},
    }

    for index, pair in enumerate(selected, start=1):
        try:
            source = find_pair_file(pair, directories)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if not args.skip_stability_check:
            try:
                wait_for_stable_size(source)
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                return 1

        name = archive_filename(pair, interval)
        target = out_dir / name if args.write else None
        stats = reduce_pair(source, interval_s=interval, out=target)
        provenance["pairs"][pair] = {
            "file": name,
            "source_file": str(source),
            **{key: value for key, value in stats.items() if key != "preview"},
        }
        print(
            f"[{index}/{len(selected)}] "
            f"{pair}: {stats['trades']} trades -> {stats['rows']} bars, "
            f"{stats['first_ts_iso']} to {stats['last_ts_iso']}, "
            f"{stats['missing_quiet']} quiet intervals with no row, "
            f"{stats['out_of_order_rows']} out-of-order rows, "
            f"{stats['late_rows']} late rows, "
            f"{stats['malformed_rows']} malformed rows"
            + ("" if args.write else "  (dry run, nothing written)"),
            file=sys.stderr,
        )

    if not args.write:
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    # `newline="\n"` is not decoration. `Path.write_text` opens in TEXT mode, and text
    # mode on Windows translates every `\n` to `\r\n` — so a bare call writes a CRLF
    # artefact into a file something else reads back. Lead's standing rule, 2026-09-11:
    # when writing a file, write bytes or pass `newline`, never a bare `write_text`.
    (out_dir / PROVENANCE_FILENAME).write_text(
        json.dumps(provenance, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {out_dir / PROVENANCE_FILENAME}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
