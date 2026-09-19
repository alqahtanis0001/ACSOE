#!/usr/bin/env python
"""Partition Kraken's time-and-sales archive into weekly Parquet files for replay. Spec 128.

    python scripts/partition_trades.py --pairs XBTUSD --out-dir <scratch> --write
    python scripts/partition_trades.py --write --workers 4

The replay client (spec 129) serves the trades of one week at a time and never reads a
whole pair file. Some source files run to 2.7 GB, and the Phase 5 run died of exactly an
eager whole-file read (Phase 7 prerequisite 2). So this reads each source file **once,
as a stream**, and writes

    data/derived/trades_weekly/<PAIR>/<week-start>.parquet

with three columns: ``ts`` (int64, epoch seconds as published), ``price`` and
``volume`` (text, **byte for byte as published**). A price that has been through a
float is not the price that traded, so neither value is parsed into a number on the
way through. It is only checked, so that a row the models' bars were not built from
cannot reach the replay.

## Which trades, and from which file

**The pairs are the dataset's pairs**: every pair in `data/historical/PROVENANCE.json`,
which `scripts/build_ohlcvt.py` wrote when it built the bars the models were trained on.
Each pair's source file is resolved **by `build_ohlcvt.find_pair_file` itself**, loaded
by path from that script, over its own `DEFAULT_SOURCE_DIRS`, so the two scripts cannot
drift. The result is then compared with the `source_file` the provenance recorded, and a
disagreement refuses the pair. The replay must see the trades the models were trained
on, and this comparison is the check that it does.

**The window** is the simulation's: folds 379 to 404, test weeks from 2024-07-06 00:00
UTC to 2025-01-04 00:00 UTC (`phase-7-findings.md` §R.6), half-open.

**The warm-up** is measured, not assumed. Engine 5's longest window is 96 bars, but it
is not the longest reach back:

- ``vol_regime_rank`` ranks ``realised_vol_4`` over a 96-bar window, so it reads 99
  bars;
- every bar's return is taken from the previous **existing** bar's close, which on a
  thin pair has no bound in time;
- engine 3 publishes the last ``market_sensor.published_bars`` (200) existing candles
  per pair, which is everything engine 5 can ever be shown.

The anomaly inputs are columns of the same feature frame. So "200 existing bars before
the window" covers every input the chain reads. Measured over the `*_15.csv` bars on
2026-09-19, that reaches 4.4 days back for the median pair and **100.6 days** back for
the worst (LSKUSD, then POLUSD at 98.3). :data:`WARMUP_WEEKS` is therefore 15 weeks
(105 days), and partitions start at 2024-03-23. How much of it the replay serves is the
replay's choice. This script only guarantees that it is on disk.

**Weeks start on the fold grid**: Saturday 00:00 UTC, at the window start plus a whole
number of weeks. So fold *k*'s test week is exactly one file.

## Nothing is invented

Nothing is interpolated, filled or resampled. A week with no trades has **no file**,
and the manifest lists it as empty. A reader cannot confuse "no trades" with "not
partitioned".

## What it refuses

It refuses rather than quietly producing a short or wrong partition:

1. **A source that resolves differently from the provenance.** Described above.
2. **A row the bar builder would not have kept.** That is a row with the wrong number
   of fields, a timestamp that is not a whole number of seconds, or a price or volume
   `Decimal` cannot read. `build_ohlcvt.py` counted and skipped such rows, and counted
   zero on every one of these files. A skipped row here would be a silent difference
   between what the models saw and what the replay serves, so any such row refuses the
   pair rather than being skipped.
3. **A row inside the window that arrives after its week has been written.** The export
   is time-ordered, and out-of-order rows within one week are kept in file order and
   counted. But a row for a week already closed can only be dropped or appended out of
   place, and both would be silent.
4. **A count that does not reconcile.** Rows are counted three times, independently:
   once from the stream as they are selected, once from the written files' own Parquet
   metadata after they are closed, and once from the ``trades`` column of the models'
   own `<PAIR>_15.csv` bars over the same window. The pair is refused, and its
   directory is never given its final name, unless every week and the total agree.
5. **An output directory that already exists.** Partitions are written once.

## Memory

Bounded by the CSV block size, not by the file. pyarrow's streaming reader parses one
block at a time, each week's file is appended to as its rows arrive, and nothing holds a
whole file or a whole week. The peak working set is measured, reported per pair and
written into the manifest. `tests/scripts/test_partition_trades.py` asserts, on
synthetic files one and four times as large, that it does not grow with file size.

## Never write into the source

Invariant 11. The source files are opened for reading only, and the output must lie
outside `data/historical/`.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import shutil
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import ModuleType
from typing import Any, BinaryIO, Final

import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.csv as pacsv  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
BUILD_OHLCVT: Final = REPO_ROOT / "scripts" / "build_ohlcvt.py"

DEFAULT_PROVENANCE: Final = Path("data") / "historical" / "PROVENANCE.json"
DEFAULT_OUT_DIR: Final = Path("data") / "derived" / "trades_weekly"
HISTORICAL_DIR: Final = Path("data") / "historical"
MANIFEST_FILENAME: Final = "MANIFEST.json"

#: The simulation window, `phase-7-findings.md` §R.6: folds 379 to 404, half-open.
WINDOW_START: Final = datetime(2024, 7, 6, tzinfo=UTC)
WINDOW_END: Final = datetime(2025, 1, 4, tzinfo=UTC)

#: Measured, see the module docstring: 200 existing bars before the window reach back
#: at most 100.6 days (LSKUSD) across the dataset's pairs. 15 weeks is 105 days.
WARMUP_WEEKS: Final = 15

WEEK_S: Final = 7 * 24 * 60 * 60

#: pyarrow's CSV block. Memory is bounded by this, not by the file.
DEFAULT_BLOCK_BYTES: Final = 16 * 1024 * 1024

SCHEMA: Final = pa.schema(
    [("ts", pa.int64()), ("price", pa.string()), ("volume", pa.string())]
)

#: A plain decimal, as Kraken writes every price and volume in this archive. A value
#: that does not match is checked with `Decimal` before it is refused, so the test is
#: exactly the bar builder's and not a narrower one.
PLAIN_DECIMAL: Final = r"^[0-9]+(\.[0-9]+)?$"


class PartitionError(RuntimeError):
    """A pair that cannot be partitioned faithfully. The message names why."""


# --------------------------------------------------------------------------- #
# The week grid
# --------------------------------------------------------------------------- #


def epoch(moment: datetime) -> int:
    return int(moment.timestamp())


def iso_date(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, tz=UTC).strftime("%Y-%m-%d")


def week_starts(start: int, end: int) -> list[int]:
    """Every week start in ``[start, end)``, on the grid that ``start`` sits on."""
    if (end - start) % WEEK_S:
        raise PartitionError("the window must be a whole number of weeks")
    return list(range(start, end, WEEK_S))


# --------------------------------------------------------------------------- #
# Source resolution, borrowed from the bar builder rather than copied
# --------------------------------------------------------------------------- #


def load_build_ohlcvt() -> ModuleType:
    """`scripts/build_ohlcvt.py`, imported by path. It is not a package."""
    spec = importlib.util.spec_from_file_location("acsoe_build_ohlcvt_script", BUILD_OHLCVT)
    if spec is None or spec.loader is None:
        raise PartitionError(f"cannot load {BUILD_OHLCVT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_sources(
    provenance: dict[str, Any], directories: Sequence[Path], builder: ModuleType
) -> dict[str, Path]:
    """Each provenance pair's source file, resolved as the bar builder resolves it.

    Refuses a pair whose resolution disagrees with the ``source_file`` the provenance
    recorded. Comparing the two is what makes "the trades the models were trained on"
    a checked statement rather than a hope.
    """
    resolved: dict[str, Path] = {}
    for pair, entry in sorted(provenance["pairs"].items()):
        source = Path(builder.find_pair_file(pair, tuple(directories)))
        recorded = Path(str(entry["source_file"]).replace("\\", "/"))
        if source.as_posix() != recorded.as_posix():
            raise PartitionError(
                f"{pair}: the bar builder resolves {source.as_posix()} but "
                f"PROVENANCE.json recorded {recorded.as_posix()}; the replay would not "
                "serve the trades the models were trained on"
            )
        resolved[pair] = source
    return resolved


# --------------------------------------------------------------------------- #
# Memory
# --------------------------------------------------------------------------- #


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_uint32),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_working_set_bytes() -> int | None:
    """This process's peak working set. The Win32 counter on Windows, else ``None``.

    Windows is the target OS, and there is no psutil in the venv. Elsewhere this reports
    nothing rather than a number from a different measure.
    """
    if sys.platform != "win32":
        return None
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.K32GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_ProcessMemoryCounters),
        ctypes.c_uint32,
    ]
    kernel32.K32GetProcessMemoryInfo.restype = ctypes.c_int
    if not kernel32.K32GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        return None
    return int(counters.PeakWorkingSetSize)


# --------------------------------------------------------------------------- #
# One pair
# --------------------------------------------------------------------------- #


class HashingReader:
    """A read-only file wrapper that hashes every byte pyarrow reads through it.

    The source's sha256 goes into the manifest, and hashing in the same pass is what
    keeps this to one read of a 2.7 GB file. :meth:`drain` hashes anything the parser
    did not ask for, so the digest always covers the whole file.
    """

    def __init__(self, handle: BinaryIO) -> None:
        self._handle = handle
        self._digest = hashlib.sha256()
        self.bytes_read = 0
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        chunk = self._handle.read(size)
        self._digest.update(chunk)
        self.bytes_read += len(chunk)
        return chunk

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def writable(self) -> bool:
        return False

    def close(self) -> None:
        self.closed = True

    def drain(self) -> None:
        while self.read(1024 * 1024):
            pass

    def hexdigest(self) -> str:
        return self._digest.hexdigest()


def _check_decimals(column: Any, name: str, pair: str) -> None:
    """Refuse a value `Decimal` cannot read. The regex is a fast path, never the test."""
    plain = pc.match_substring_regex(column, PLAIN_DECIMAL)
    if pc.all(plain).as_py() in (True, None):
        return
    odd = pc.filter(column, pc.invert(plain)).to_pylist()
    for text in odd:
        try:
            value = Decimal(text)
        except (InvalidOperation, TypeError) as exc:
            raise PartitionError(f"{pair}: {name} {text!r} is not a decimal") from exc
        if not value.is_finite():
            raise PartitionError(f"{pair}: {name} {text!r} is not a finite decimal")


def _write_slice(writer: Any, table: Any) -> None:
    """One slice of one week, appended to that week's file. A seam for the tests."""
    writer.write_table(table)


def partition_pair(
    pair: str,
    source: Path,
    out_root: Path,
    *,
    start: int,
    end: int,
    block_bytes: int = DEFAULT_BLOCK_BYTES,
    bars_csv: Path | None = None,
) -> dict[str, Any]:
    """Stream one source file into ``out_root/pair/<week>.parquet``. Returns its stats.

    Writes into ``<pair>.partial`` and renames it to ``<pair>`` only after the counts
    reconcile, so a directory under its final name is always a complete one. With
    ``bars_csv``, the models' own bars are a further count the window must agree with.
    """
    started = time.monotonic()
    final_dir = out_root / pair
    partial_dir = out_root / f"{pair}.partial"
    if final_dir.exists():
        raise PartitionError(f"{final_dir} already exists; partitions are written once")
    if partial_dir.exists():
        shutil.rmtree(partial_dir)
    partial_dir.mkdir(parents=True)

    grid = week_starts(start, end)
    counted: dict[int, int] = dict.fromkeys(grid, 0)
    stats: dict[str, Any] = {
        "source_rows": 0,
        "rows_before_window": 0,
        "rows_after_window": 0,
        "out_of_order_rows": 0,
    }
    writer: Any = None
    open_week: int | None = None
    previous_ts: int | None = None

    def close_writer() -> None:
        nonlocal writer
        if writer is not None:
            writer.close()
            writer = None

    read_options = pacsv.ReadOptions(
        column_names=["ts", "price", "volume"], block_size=block_bytes, use_threads=False
    )
    # No invalid-row handler: a row with the wrong number of fields raises, and the
    # pair is refused. The bar builder skipped such rows (and counted none in this
    # archive); skipping one here would be a silent difference, so it is a stop.
    parse_options = pacsv.ParseOptions(quote_char=False)
    convert_options = pacsv.ConvertOptions(
        column_types={"ts": pa.int64(), "price": pa.string(), "volume": pa.string()},
        strings_can_be_null=False,
        quoted_strings_can_be_null=False,
    )
    try:
        with source.open("rb") as raw:
            reader = HashingReader(raw)
            try:
                stream = pacsv.open_csv(
                    reader,
                    read_options=read_options,
                    parse_options=parse_options,
                    convert_options=convert_options,
                )
            except pa.ArrowInvalid as exc:
                raise PartitionError(f"{pair}: {exc}") from exc
            while True:
                try:
                    batch = stream.read_next_batch()
                except StopIteration:
                    break
                except pa.ArrowInvalid as exc:
                    # A timestamp that is not a whole number of seconds lands here.
                    raise PartitionError(f"{pair}: {exc}") from exc
                if batch.num_rows == 0:
                    continue
                stamps = batch.column("ts").to_numpy(zero_copy_only=False)
                stats["source_rows"] += int(batch.num_rows)
                steps = np.diff(stamps)
                stats["out_of_order_rows"] += int((steps < 0).sum())
                if previous_ts is not None and stamps[0] < previous_ts:
                    stats["out_of_order_rows"] += 1
                previous_ts = int(stamps[-1])

                stats["rows_before_window"] += int((stamps < start).sum())
                stats["rows_after_window"] += int((stamps >= end).sum())
                inside = (stamps >= start) & (stamps < end)
                if not inside.any():
                    continue
                table = pa.Table.from_batches([batch]).filter(pa.array(inside))
                _check_decimals(table.column("price"), "price", pair)
                _check_decimals(table.column("volume"), "volume", pair)
                weeks = start + ((stamps[inside] - start) // WEEK_S) * WEEK_S

                floor = open_week if open_week is not None else int(weeks[0])
                running = np.maximum.accumulate(np.maximum(weeks, floor))
                if (weeks < running).any():
                    late = int(stamps[inside][np.argmax(weeks < running)])
                    raise PartitionError(
                        f"{pair}: a trade at {late} arrived after its week had been "
                        "written; the export is not in time order here"
                    )
                # `weeks` is non-decreasing, so each week is one contiguous run.
                boundaries = np.flatnonzero(np.diff(weeks)) + 1
                for lo, hi in zip(
                    [0, *boundaries.tolist()], [*boundaries.tolist(), len(weeks)], strict=True
                ):
                    week = int(weeks[lo])
                    if week != open_week:
                        close_writer()
                        writer = pq.ParquetWriter(
                            partial_dir / f"{iso_date(week)}.parquet", SCHEMA
                        )
                        open_week = week
                    _write_slice(writer, table.slice(lo, hi - lo))
                    counted[week] += hi - lo
            reader.drain()
            stats["source_sha256"] = reader.hexdigest()
            stats["source_bytes"] = reader.bytes_read
    finally:
        close_writer()

    written = reconcile(pair, partial_dir, counted)
    in_window = sum(counted.values())
    bar_trades: int | None = None
    if bars_csv is not None:
        bar_trades = trades_in_bars(bars_csv, start=start, end=end)
        if bar_trades != in_window:
            raise PartitionError(
                f"{pair}: {in_window} trades in the window, but the models' bars in "
                f"{bars_csv.name} count {bar_trades}"
            )
    partial_dir.rename(final_dir)
    stats.update(
        {
            "pair": pair,
            "source_file": source.as_posix(),
            "rows_in_window": in_window,
            "rows_written": sum(written.values()),
            "trades_in_bars": bar_trades,
            "weeks": {iso_date(week): rows for week, rows in counted.items()},
            "empty_weeks": [iso_date(week) for week, rows in counted.items() if rows == 0],
            "peak_working_set_bytes": peak_working_set_bytes(),
            "seconds": round(time.monotonic() - started, 3),
        }
    )
    return stats


def reconcile(pair: str, directory: Path, counted: dict[int, int]) -> dict[int, int]:
    """The rows each written file says it holds, which must equal the stream's count.

    Read from the files' own Parquet metadata after they are closed, never from the
    counter that decided what to write, so a writer that dropped or duplicated a row is
    caught here rather than trusted.
    """
    expected = {iso_date(week): rows for week, rows in counted.items() if rows}
    on_disk = {path.stem: int(pq.read_metadata(path).num_rows) for path in directory.glob("*.parquet")}
    if on_disk != expected:
        missing = sorted(set(expected) - set(on_disk))
        extra = sorted(set(on_disk) - set(expected))
        differ = sorted(
            f"{week}: counted {expected[week]}, file holds {on_disk[week]}"
            for week in set(expected) & set(on_disk)
            if expected[week] != on_disk[week]
        )
        raise PartitionError(
            f"{pair}: written partitions do not reconcile with the stream. "
            f"missing {missing}, unexpected {extra}, differing {differ}"
        )
    return {week: rows for week, rows in counted.items() if rows}


def trades_in_bars(bars_csv: Path, *, start: int, end: int) -> int:
    """The trade count the models' own bars record inside ``[start, end)``.

    `build_ohlcvt.py` wrote a real trade count into the seventh column of every bar, and
    the window's edges are whole weeks, so they fall on bar boundaries. This is a third
    count of the same rows, made by a different program on a different day, and it is
    the one that ties the partitions to what the models were trained on.
    """
    total = 0
    with bars_csv.open("r", encoding="utf-8", newline="") as handle:
        for line in handle:
            fields = line.rstrip("\r\n").split(",")
            if len(fields) != 7:
                raise PartitionError(f"{bars_csv}: a bar with {len(fields)} fields")
            if start <= int(fields[0]) < end:
                total += int(fields[6])
    return total


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #


def script_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="partition_trades.py", description=__doc__.split("\n")[0])
    parser.add_argument("--pairs", nargs="+", default=None, help="only these pairs")
    parser.add_argument("--provenance", default=str(DEFAULT_PROVENANCE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--window-start", default=WINDOW_START.isoformat())
    parser.add_argument("--window-end", default=WINDOW_END.isoformat())
    parser.add_argument("--warmup-weeks", type=int, default=WARMUP_WEEKS)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--block-mb", type=float, default=DEFAULT_BLOCK_BYTES / 2**20)
    parser.add_argument(
        "--write", action="store_true", help="without this, report the plan and touch nothing"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_root = Path(args.out_dir)
    if out_root.resolve().is_relative_to((REPO_ROOT / HISTORICAL_DIR).resolve()):
        print("the output may not lie inside data/historical/ (invariant 11)", file=sys.stderr)
        return 2
    window_start = datetime.fromisoformat(args.window_start)
    window_end = datetime.fromisoformat(args.window_end)
    start = epoch(window_start - timedelta(weeks=args.warmup_weeks))
    end = epoch(window_end)
    try:
        week_starts(start, end)
    except PartitionError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    builder = load_build_ohlcvt()
    provenance = json.loads(Path(args.provenance).read_bytes())
    directories = tuple(Path(directory) for directory in builder.DEFAULT_SOURCE_DIRS)
    try:
        sources = resolve_sources(provenance, directories, builder)
    except (PartitionError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.pairs is not None:
        unknown = sorted(set(args.pairs) - set(sources))
        if unknown:
            print(f"not dataset pairs: {unknown}", file=sys.stderr)
            return 2
        sources = {pair: sources[pair] for pair in args.pairs}

    print(
        f"{len(sources)} pairs, {iso_date(start)} (warm-up {args.warmup_weeks} weeks) to "
        f"{iso_date(end)}, {len(week_starts(start, end))} weeks, into {out_root}",
        file=sys.stderr,
    )
    if not args.write:
        return 0

    out_root.mkdir(parents=True, exist_ok=True)
    manifest_path = out_root / MANIFEST_FILENAME
    if manifest_path.exists():
        print(f"{manifest_path} already exists; partitions are written once", file=sys.stderr)
        return 1
    block = int(args.block_mb * 2**20)
    results: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    jobs = {
        pair: {
            "pair": pair,
            "source": source,
            "out_root": out_root,
            "start": start,
            "end": end,
            "block_bytes": block,
            "bars_csv": Path(args.provenance).parent / provenance["pairs"][pair]["file"],
        }
        for pair, source in sources.items()
    }

    def report(done: int, pair: str, outcome: dict[str, Any] | PartitionError) -> None:
        if isinstance(outcome, PartitionError):
            failures[pair] = str(outcome)
            print(f"[{done}/{len(jobs)}] {pair}: REFUSED: {outcome}", file=sys.stderr)
            return
        results[pair] = outcome
        peak = outcome["peak_working_set_bytes"]
        print(
            f"[{done}/{len(jobs)}] {pair}: {outcome['source_rows']:,} source rows, "
            f"{outcome['rows_in_window']:,} in the window over "
            f"{len(outcome['weeks']) - len(outcome['empty_weeks'])} weeks, "
            f"{outcome['seconds']:.1f}s"
            + (f", peak working set {peak / 2**20:.0f} MiB" if peak else ""),
            file=sys.stderr,
        )

    if args.workers <= 1:
        # In process. Also what the tests drive: a module loaded by path cannot be
        # re-imported by name in a spawned worker.
        for done, (pair, job) in enumerate(jobs.items(), start=1):
            try:
                report(done, pair, partition_pair(**job))
            except PartitionError as exc:
                report(done, pair, exc)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(partition_pair, **job): pair for pair, job in jobs.items()}
            for done, future in enumerate(as_completed(futures), start=1):
                try:
                    report(done, futures[future], future.result())
                except PartitionError as exc:
                    report(done, futures[future], exc)
    if failures:
        print(f"{len(failures)} pairs refused; no manifest written", file=sys.stderr)
        return 1

    manifest = {
        "schema_version": 1,
        "built_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "built_by": "scripts/partition_trades.py",
        "script_sha256": script_sha256(),
        "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
        "warmup_weeks": args.warmup_weeks,
        "warmup_basis": (
            "200 existing 15-minute bars before the window start, engine 3's "
            "market_sensor.published_bars, reach back at most 100.6 days (LSKUSD) over "
            "the dataset's pairs, measured 2026-09-19; 15 weeks is 105 days"
        ),
        "partitions_start": iso_date(start),
        "partitions_end_exclusive": iso_date(end),
        "week_starts": [iso_date(week) for week in week_starts(start, end)],
        "columns": {
            "ts": "int64, epoch seconds, as published",
            "price": "text, byte for byte as published",
            "volume": "text, byte for byte as published",
        },
        "row_order": "source file order; ties within a second keep file order",
        "source_dirs": [directory.as_posix() for directory in directories],
        "source_resolution": (
            "scripts/build_ohlcvt.py find_pair_file over its DEFAULT_SOURCE_DIRS, checked "
            "equal to data/historical/PROVENANCE.json source_file per pair"
        ),
        "interpolation": (
            "none. A week with no trades has no file and is listed in empty_weeks."
        ),
        "pairs": dict(sorted(results.items())),
    }
    manifest_path.write_bytes((json.dumps(manifest, indent=1) + "\n").encode("utf-8"))
    print(f"wrote {manifest_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
