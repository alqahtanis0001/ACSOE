#!/usr/bin/env python
"""Reduce the operator's Kraken time-and-sales archive into 15-minute OHLCVT CSVs.

    python scripts/build_ohlcvt.py --pairs XBTUSD ETHUSD SOLUSD --write

Spec 54 as amended on 2026-09-11. The operator supplied Kraken's own published trade
history — roughly 27 GB across 1,119 pair files in
`data/historical/KRAKEN_TimeAndSales_Combined/` (`1INCH` to `HONEY`) and
`data/historical/TimeAndSales_Combined/` (`HPOS10I` onward). This reduces the pairs we
need into the seven-column shape `acsoe.research.historical.load_archive` reads.

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
import sys
import time
from collections.abc import Iterator
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
DEFAULT_PAIRS: Final = ("XBTUSD", "ETHUSD", "SOLUSD")
PROVENANCE_FILENAME: Final = "PROVENANCE.json"

#: How many intervals of already-passed bars stay open before being written out. Kraken's
#: export is time-ordered, so in practice nothing arrives late at all; this exists so
#: that a handful of out-of-order rows are absorbed rather than silently producing two
#: bars with the same timestamp, and anything older than the window is counted.
OPEN_BAR_WINDOW: Final = 8

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
            else:
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
        stats["preview"] = written[:3]
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
    parser.add_argument("--pairs", nargs="+", default=list(DEFAULT_PAIRS))
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
        "--skip-stability-check",
        action="store_true",
        help=(
            "read a source file without first confirming its size has settled. Only for "
            "an archive known to be complete: a file still being extracted ends in a "
            "half-line and produces a silently short final bar."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import json

    args = parse_args(argv)
    interval = args.interval_s
    if interval <= 0:
        print("--interval-s must be positive", file=sys.stderr)
        return 2

    directories = tuple(Path(directory) for directory in args.source_dir)
    out_dir = Path(args.out_dir)
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
        "pairs": {},
    }

    for pair in args.pairs:
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
