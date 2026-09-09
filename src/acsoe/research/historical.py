"""Kraken OHLCVT archive loader — offline only.

Ingests one pair's downloadable Kraken OHLCVT archive from ``data/historical/`` and
reports honest gap statistics, so Phase 4's replay and labelling have a real dataset to
stand on.

**Offline only.** This module imports nothing from ``acsoe.engines``,
``acsoe.core``, ``acsoe.clients`` or ``acsoe.cli``, and the live loop never imports
from ``acsoe.research``. Architecture invariant 5.

## A missing candle means no trades occurred. It is not a data error.

Kraken's archives contain only intervals in which trades happened, so a hole is a
**fact about the market** — a quiet period — and it is information, not damage. This
loader marks every hole and **never** interpolates, forward-fills, resamples or
otherwise synthesises one, and there is deliberately no flag that does.

That is stated this strongly because it is exactly the kind of thing an implementer
fixes helpfully. A gap looks like missing data, forward-filling makes the series
continuous, every downstream chart looks tidier, and nothing fails.

**It is load-bearing for Phase 4's triple-barrier labelling**, which walks forward from
each decision bar to decide whether the target, the stop or the timeout came first. A
synthesised candle at a price that never traded invents a barrier touch that never
happened, and the label built from it is a fabricated outcome the model then learns
from. **That error is invisible to every test that only checks the series is
continuous** — which is why the report exposes its own ``timestamps`` and the phase
criterion asserts, separately from the gap count, that no timestamp in the output was
absent from the input.

## These archives are OHLCVT only: no book, no spread.

Bid, ask, depth and spread do not exist in this data and cannot be recovered for it.
Engine 9 ``order_book`` and the spread component of engine 10 ``cost`` therefore
**cannot be backtested from this source**, and a backtest that silently assumes zero
spread is invalid. The report carries that statement in a field rather than leaving it
to a docstring nobody reads at the point of use.

## Money

``Decimal`` at the boundary — open, high, low, close and volume are exact. Gap
statistics and durations are ordinary integers and floats, per the Phase 0 decision.
"""

from __future__ import annotations

import csv
import itertools
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

import polars as pl
from pydantic import BaseModel, ConfigDict

__all__ = [
    "OHLCVT_COLUMNS",
    "ArchiveReport",
    "GapRun",
    "bucket_label",
    "gap_runs",
    "load_archive",
    "read_archive_rows",
]

#: Kraken's downloadable OHLCVT CSV has no header and these columns in this order.
#: The trailing ``trades`` column is the T in OHLCVT.
OHLCVT_COLUMNS: Final = ("ts", "open", "high", "low", "close", "volume", "trades")

#: Gap length buckets, in bars. Reported as counts so a run of one quiet bar and a
#: multi-day outage are never added together into a single meaningless number.
_BUCKETS: Final = ((1, 1, "1 bar"), (2, 4, "2-4 bars"), (5, 16, "5-16 bars"),
                   (17, 96, "17-96 bars"), (97, None, "97+ bars"))

_MONEY_COLUMNS: Final = ("open", "high", "low", "close", "volume")
_DECIMAL_DTYPE: Final = pl.Decimal(38, 12)

NO_BOOK_NOTE: Final = (
    "Kraken's OHLCVT archives are OHLCVT only: no bid, no ask, no depth, no spread. "
    "Engine 9 `order_book` and the spread component of engine 10 `cost` cannot be "
    "backtested from this source, and a backtest that silently assumes zero spread is "
    "invalid."
)

NO_INTERPOLATION_NOTE: Final = (
    "A missing candle means no trades occurred. It is marked here and never "
    "interpolated: no row in this output carries a timestamp the archive did not."
)


class ArchiveError(ValueError):
    """The archive could not be read as Kraken OHLCVT."""


class GapRun(BaseModel):
    """One maximal run of consecutive bars in which nothing traded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: int
    """The first missing bar's opening second."""

    end: int
    """The last missing bar's opening second."""

    bars: int

    @property
    def seconds(self) -> int:
        return self.end - self.start

    def as_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "bars": self.bars}


class ArchiveReport(BaseModel):
    """What one archive contained, and every hole in it.

    ``gap_count`` counts **runs**, not missing bars. Three holes of 1, 2 and 4 bars are
    three gaps and seven missing bars, and reporting seven would be the signature of a
    loader that had lost the distinction — which is exactly what the phase criterion
    fabricates to catch.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    """The archive's **file name**, never its full path: a report that only makes
    sense on the machine that produced it is a broken report."""

    pair: str
    interval_s: int

    row_count: int
    """Rows read from the archive. Equal to the number of candles emitted, always:
    this loader neither drops a row nor invents one."""

    timestamps: tuple[int, ...]
    """Every emitted candle's opening second, ascending. **The archive's own.**

    Exposed so the caller can assert the thing the gap count cannot: that no timestamp
    in the output was absent from the input. Counting gaps correctly while also
    emitting filled rows would satisfy every other field here.
    """

    first_ts: int | None
    last_ts: int | None
    expected_bars: int
    """How many bars the span would hold if every one had traded."""

    present_bars: int
    missing_bars: int
    gap_count: int
    duration_buckets: dict[str, int]
    largest_gap_bars: int
    largest_gap: dict[str, Any] | None
    gaps: tuple[dict[str, Any], ...]

    duplicate_timestamps: int
    """Rows sharing a timestamp with an earlier row. Reported, never merged."""

    out_of_order_rows: int
    """Rows whose timestamp went backwards. Reported; the output is sorted."""

    first_close: str | None
    last_close: str | None
    """Exact decimal strings. Money never leaves this module as a float."""

    has_order_book: bool = False
    has_spread: bool = False
    book_note: str = NO_BOOK_NOTE
    interpolation_note: str = NO_INTERPOLATION_NOTE
    derived_path: str | None = None

    def digest(self) -> dict[str, Any]:
        """The committable form: everything except the full timestamp list.

        `data/historical/` is gitignored, so the committed evidence is small. The
        timestamps are what a *criterion* checks in memory, not what gets checked in.
        """
        payload = self.model_dump(mode="json")
        payload.pop("timestamps", None)
        return payload


def bucket_label(bars: int) -> str:
    """Which duration bucket a gap of ``bars`` missing bars falls in."""
    for low, high, label in _BUCKETS:
        if bars >= low and (high is None or bars <= high):
            return label
    raise ValueError(f"no bucket for a gap of {bars} bars")  # pragma: no cover


def gap_runs(timestamps: Sequence[int], *, interval_s: int) -> list[GapRun]:
    """Maximal runs of consecutive missing bars between the first and last timestamp.

    **Runs, not bars.** A loader that returned one entry per missing bar would report
    seven for holes of 1, 2 and 4 — which is the arithmetic the phase criterion exists
    to catch.

    Bounded by the data: bars before the archive starts or after it ends are not
    missing, they are outside the range.
    """
    if interval_s <= 0:
        raise ValueError("interval_s must be positive")
    if len(timestamps) < 2:
        return []
    present = set(timestamps)
    runs: list[GapRun] = []
    run_start: int | None = None
    previous: int | None = None
    for ts in range(min(present), max(present) + interval_s, interval_s):
        if ts in present:
            if run_start is not None and previous is not None:
                runs.append(
                    GapRun(
                        start=run_start,
                        end=previous,
                        bars=(previous - run_start) // interval_s + 1,
                    )
                )
                run_start = None
            continue
        if run_start is None:
            run_start = ts
        previous = ts
    if run_start is not None and previous is not None:  # pragma: no cover - defensive
        runs.append(
            GapRun(start=run_start, end=previous, bars=(previous - run_start) // interval_s + 1)
        )
    return runs


def _decimal(value: str, column: str, line: int) -> Decimal:
    try:
        return Decimal(value.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ArchiveError(f"line {line}: {column} is not a decimal number: {value!r}") from exc


def read_archive_rows(path: Path) -> list[dict[str, Any]]:
    """Parse a Kraken OHLCVT CSV into plain rows, with `Decimal` money.

    Read with :mod:`csv` rather than with `polars`, deliberately. The money columns
    have to become `Decimal` **without ever passing through a float**, and the cheapest
    way to guarantee that is never to hand the text to a numeric parser in the first
    place. `polars` does the columnar work afterwards, on values that are already
    exact.

    A header row is tolerated — some mirrors add one — and is skipped rather than
    parsed as a bar.
    """
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_number, fields in enumerate(csv.reader(handle), start=1):
            if not fields or not any(field.strip() for field in fields):
                continue
            if len(fields) < 6:
                raise ArchiveError(
                    f"line {line_number}: expected at least 6 OHLCVT columns, got {len(fields)}"
                )
            head = fields[0].strip()
            if line_number == 1 and not head.lstrip("-").isdigit():
                continue  # a header row
            try:
                ts = int(float(head))
            except ValueError as exc:
                raise ArchiveError(
                    f"line {line_number}: {head!r} is not a unix timestamp"
                ) from exc
            row: dict[str, Any] = {"ts": ts}
            for index, column in enumerate(_MONEY_COLUMNS, start=1):
                row[column] = _decimal(fields[index], column, line_number)
            row["trades"] = int(float(fields[6])) if len(fields) > 6 and fields[6].strip() else 0
            rows.append(row)
    return rows


def to_frame(rows: Iterable[Mapping[str, Any]]) -> pl.DataFrame:
    """The rows as a `polars` frame with exact `Decimal` money columns, sorted by time.

    Sorting is the only reordering that happens. Nothing is added, nothing is dropped,
    and no value is recomputed — so the frame's timestamps are exactly the archive's.
    """
    materialised = list(rows)
    if not materialised:
        return pl.DataFrame(
            schema={
                "ts": pl.Int64,
                **dict.fromkeys(_MONEY_COLUMNS, _DECIMAL_DTYPE),
                "trades": pl.Int64,
            }
        )
    return pl.DataFrame(
        {
            "ts": [int(row["ts"]) for row in materialised],
            **{
                column: [row[column] for row in materialised]
                for column in _MONEY_COLUMNS
            },
            "trades": [int(row["trades"]) for row in materialised],
        },
        schema_overrides=dict.fromkeys(_MONEY_COLUMNS, _DECIMAL_DTYPE),
    ).sort("ts")


def load_archive(
    path: Path | str,
    *,
    interval_s: int,
    pair: str | None = None,
    derived_dir: Path | None = None,
) -> ArchiveReport:
    """Ingest one archive and report what it held, holes included.

    :param derived_dir: when given, the built frame is written there as Parquet —
        rebuildable from the archive, never checked in. Omitted by default so that
        merely *reading* an archive has no side effect on disk, which matters because
        a phase criterion calls this.

    Returns an :class:`ArchiveReport`. **It never returns a repaired series**, and
    there is no parameter that asks it to.
    """
    archive = Path(path)
    if not archive.is_file():
        raise ArchiveError(f"archive not found: {archive}")
    if interval_s <= 0:
        raise ValueError("interval_s must be positive")

    rows = read_archive_rows(archive)
    frame = to_frame(rows)
    timestamps = [int(value) for value in frame["ts"].to_list()]

    seen: set[int] = set()
    duplicates = 0
    for ts in timestamps:
        if ts in seen:
            duplicates += 1
        seen.add(ts)
    original = [int(row["ts"]) for row in rows]
    out_of_order = sum(
        1 for previous, current in itertools.pairwise(original) if current < previous
    )

    runs = gap_runs(timestamps, interval_s=interval_s)
    buckets: dict[str, int] = {}
    for run in runs:
        label = bucket_label(run.bars)
        buckets[label] = buckets.get(label, 0) + 1
    largest = max(runs, key=lambda run: run.bars, default=None)

    first_ts = timestamps[0] if timestamps else None
    last_ts = timestamps[-1] if timestamps else None
    expected = (
        ((last_ts - first_ts) // interval_s) + 1
        if first_ts is not None and last_ts is not None
        else 0
    )

    derived_path: str | None = None
    if derived_dir is not None:
        derived_dir.mkdir(parents=True, exist_ok=True)
        target = derived_dir / f"{archive.stem}.parquet"
        frame.write_parquet(target)
        derived_path = target.name

    return ArchiveReport(
        path=archive.name,
        pair=pair or archive.stem,
        interval_s=interval_s,
        row_count=len(timestamps),
        timestamps=tuple(timestamps),
        first_ts=first_ts,
        last_ts=last_ts,
        expected_bars=expected,
        present_bars=len(set(timestamps)),
        missing_bars=sum(run.bars for run in runs),
        gap_count=len(runs),
        duration_buckets=buckets,
        largest_gap_bars=largest.bars if largest is not None else 0,
        largest_gap=largest.as_dict() if largest is not None else None,
        gaps=tuple(run.as_dict() for run in runs),
        duplicate_timestamps=duplicates,
        out_of_order_rows=out_of_order,
        first_close=str(rows[0]["close"]) if rows else None,
        last_close=str(rows[-1]["close"]) if rows else None,
        derived_path=derived_path,
    )
