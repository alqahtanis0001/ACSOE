"""Archive in, decision bars out — offline only.

Spec 54. Reads one or more Kraken OHLCVT archives from ``data/historical/`` through
:func:`acsoe.research.historical.load_archive`, and yields the decision-bar series the
labeller consumes, in timestamp order, against an **injected clock**.

**Offline only.** This module imports nothing from ``acsoe.engines``, ``acsoe.core``,
``acsoe.clients``, ``acsoe.cli`` or ``acsoe.console``, and nothing in any of those
imports it. Architecture invariant 5. ``acsoe.platform`` is not in that list and is
imported for the clock, which is the whole mechanism by which a replay is faithful.

## The clock is what makes this a replay rather than a read

Invariant 9: engines receive ``context.now`` and never call ``datetime.now()``. Replay
is the reason that invariant exists. As each bar is yielded the clock is moved to that
bar's **close** — ``ts + interval_s`` — because the close is the first instant at which
the bar is a fact. A consumer that reads the clock therefore sees replay time, and a
consumer that reaches for a bar it has not been given yet is reaching into the future of
a clock that has not got there. Look-ahead becomes structurally awkward instead of
merely discouraged.

Nothing here sleeps, waits or paces. Replay time advances because a bar was consumed.

## A hole is not a row, and this module will not make it one

:func:`acsoe.research.historical.load_archive` never interpolates and neither does this.
Bars come out with the archive's own timestamps and no others, which means the series is
**not** on a regular grid: consecutive bars can be fifteen minutes or three days apart.
Every consumer must take the gap from the timestamps rather than from the row index. The
lead's Phase 4 ruling that the timeout barrier is a time and not a count of rows is the
same fact seen from the labeller's side.

## A hole in *our* archive does not mean what a hole in Kraken's means

Kraken never stops watching, so a hole in Kraken's published archive can only mean no
trades occurred. An archive built by ``scripts/build_archive.py`` out of a recording has
holes of a second kind — intervals nobody was watching — and rows of a third kind: real
trades over an interval the recorder only partly covered, whose volume is understated
and whose high or low may never have been seen.

The seven-column CSV has nowhere to say which is which, so the builder writes
``PROVENANCE.json`` beside the CSVs and this module reads it and carries it on the
report. When the sidecar is **absent** the coverage is *unknown* and is reported as
unknown — never as "all holes are quiet", which would be a guess dressed as a fact.

## No book, no spread

OHLCVT is open, high, low, close, volume and trade count. There is no bid, no ask, no
depth and no spread in this data and none can be recovered for it, so engine 9
``order_book`` and the spread half of engine 10 ``cost`` cannot be backtested from this
source. The statement travels on the report rather than sitting in a docstring nobody
reads at the point of use.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

import polars as pl
from pydantic import BaseModel, ConfigDict

from acsoe.research.historical import (
    NO_BOOK_NOTE,
    NO_INTERPOLATION_NOTE,
    ArchiveError,
    ArchiveReport,
    load_archive,
    read_archive_rows,
    to_frame,
)

__all__ = [
    "COVERAGE_UNKNOWN_NOTE",
    "PROVENANCE_FILENAME",
    "ArchiveReplay",
    "DecisionBar",
    "ReplayReport",
    "load_provenance",
    "pair_from_filename",
]

#: The sidecar `scripts/build_archive.py` writes beside the CSVs. Absent for a real
#: downloaded Kraken archive, which is correct: Kraken's holes need no explaining.
PROVENANCE_FILENAME: Final = "PROVENANCE.json"

COVERAGE_UNKNOWN_NOTE: Final = (
    "No PROVENANCE.json sits beside these archives, so it is not known whether a hole "
    "means no trades occurred or means nobody was watching. It is reported as unknown "
    "rather than assumed to be quiet: assuming quiet is what makes a triple barrier "
    "walk across an outage and return a timeout the market never gave."
)


@runtime_checkable
class SettableClock(Protocol):
    """A clock replay is allowed to move. ``platform.clock.FixedClock`` satisfies it.

    Deliberately not ``platform.clock.Clock``: that one only reads. Replay has to
    *write* the instant, and typing the parameter as the read-only protocol would let a
    ``SystemClock`` be injected, at which point every bar would be stamped with wall
    time and the replay would silently stop being a replay.
    """

    def now(self) -> datetime:
        ...

    def set(self, at: datetime) -> None:
        ...


class DecisionBar(BaseModel):
    """One closed bar of the replayed series.

    The same seven fields engine 3's ``Candle`` publishes, plus the pair's interval and
    the bar's position in its own series. It is **not** engine 3's ``Candle``: importing
    that would pull ``acsoe.engines`` into this module and break invariant 5, and the
    two shapes agreeing is a property worth keeping rather than a duplication worth
    removing.

    ``index`` is the position in **this pair's** series, not a position in time. Bars
    ``index`` 7 and 8 can be fifteen minutes or three days apart, because the archive
    contains only intervals in which trades occurred. Anything that needs elapsed time
    must subtract ``ts``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    ts: int
    """The bar's **opening** second, UTC."""

    interval_s: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trades: int
    index: int

    @property
    def close_ts(self) -> int:
        """The first second at which this bar is a fact. What the clock is set to."""
        return self.ts + self.interval_s

    def state_dict(self) -> dict[str, Any]:
        """JSON-safe, money as exact decimal strings. Never a float: a price that has
        been through binary floating point is not the price that traded."""
        return {
            "pair": self.pair,
            "ts": self.ts,
            "interval_s": self.interval_s,
            "open": f"{self.open:f}",
            "high": f"{self.high:f}",
            "low": f"{self.low:f}",
            "close": f"{self.close:f}",
            "volume": f"{self.volume:f}",
            "trades": self.trades,
            "index": self.index,
        }


class PairCoverage(BaseModel):
    """What the builder knew about one pair's holes, when it wrote a sidecar.

    ``missing_quiet_ts`` are the only holes that mean what a hole in Kraken's own
    archive means. The other two lists, and ``partial_rows_ts``, are artefacts of an
    archive built from a recording. All three are timestamps rather than counts so that
    a consumer can exclude by identity instead of trusting an arithmetic.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    missing_quiet_ts: tuple[int, ...] = ()
    missing_not_recorded_ts: tuple[int, ...] = ()
    missing_partially_recorded_ts: tuple[int, ...] = ()
    partial_rows_ts: tuple[int, ...] = ()

    @property
    def unusable_ts(self) -> frozenset[int]:
        """Every interval in the span that is an artefact of the recording rather than
        a fact about the market — the holes nobody watched, and the rows that look
        complete and are not."""
        return frozenset(
            self.missing_not_recorded_ts
            + self.missing_partially_recorded_ts
            + self.partial_rows_ts
        )


class ReplayReport(BaseModel):
    """Everything a caller needs to judge the series it is about to be given."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    interval_s: int
    pairs: tuple[str, ...]
    archives: dict[str, ArchiveReport]
    """The gap report per pair, straight from `load_archive`. Never summarised into a
    single number: three holes of 1, 2 and 4 bars are three gaps and seven missing bars,
    and a report that added them would have lost the distinction."""

    bar_count: int
    first_ts: int | None
    last_ts: int | None

    coverage_known: bool
    """False when no sidecar was found. A real Kraken archive has none and does not need
    one; an archive built from a recording without one cannot be trusted about its own
    holes."""

    holes_mean_no_trades: bool | None = None
    """Whether a hole in this archive means no trades occurred.

    **Three values, not two, and the third is the point.** ``True`` is Kraken's own
    published history, where the only reason an interval is absent is that nothing
    traded in it — that is what makes a triple barrier safe to walk across a hole.
    ``False`` is an archive built from our WebSocket recording, where a hole is usually
    an outage. ``None`` is *unknown*, and a consumer must treat it as ``False`` would be
    treated: an absent answer is not a yes. Invariant 3.
    """

    coverage: dict[str, PairCoverage] = {}
    coverage_note: str = COVERAGE_UNKNOWN_NOTE
    provenance: str | None = None

    has_order_book: bool = False
    has_spread: bool = False
    book_note: str = NO_BOOK_NOTE
    interpolation_note: str = NO_INTERPOLATION_NOTE

    @property
    def span_seconds(self) -> int:
        if self.first_ts is None or self.last_ts is None:
            return 0
        return self.last_ts - self.first_ts

    def summary(self) -> str:
        """One line for `acsoe research` and for a criterion's PASS message."""
        if self.first_ts is None or self.last_ts is None:
            return "0 bars over 0 pairs"
        first = datetime.fromtimestamp(self.first_ts, tz=UTC).isoformat()
        last = datetime.fromtimestamp(self.last_ts, tz=UTC).isoformat()
        gaps = sum(report.gap_count for report in self.archives.values())
        holes = {True: "no trades", False: "NOT ONLY no trades", None: "UNKNOWN"}[
            self.holes_mean_no_trades
        ]
        return (
            f"{self.bar_count} bars over {len(self.pairs)} pair(s), "
            f"{first} to {last}, {gaps} gap(s), "
            f"coverage {'known' if self.coverage_known else 'UNKNOWN'}, "
            f"a hole means {holes}"
        )


def pair_from_filename(path: Path) -> str:
    """``BTCUSD_15.csv`` becomes ``BTCUSD``.

    Only the interval suffix is stripped. No attempt is made to reinsert a ``/`` or to
    translate a spelling: ``AGENTS.md`` is explicit that remembered Kraken naming is
    stale, and inventing ``BTC/USD`` out of ``XBTUSD`` is exactly the kind of guess that
    would then have to be unguessed. A caller who knows the pair passes ``pairs=``.
    """
    stem = path.stem
    head, sep, tail = stem.rpartition("_")
    if sep and tail.isdigit():
        return head
    return stem


def load_provenance(directory: Path) -> dict[str, Any] | None:
    """The builder's sidecar, or ``None`` when there is none.

    A malformed sidecar is ``None`` as well, and deliberately not an exception: the
    sidecar is extra information about holes, and a replay whose archives are fine must
    not be stopped by a damaged note about them. The consequence — coverage reported as
    unknown — is the safe one, because unknown is what makes a consumer exclude rather
    than assume.
    """
    path = directory / PROVENANCE_FILENAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _coverage_from(payload: dict[str, Any] | None) -> dict[str, PairCoverage]:
    if not payload:
        return {}
    pairs = payload.get("pairs")
    if not isinstance(pairs, dict):
        return {}
    coverage: dict[str, PairCoverage] = {}
    for pair, block in pairs.items():
        if not isinstance(block, dict):
            continue
        file_name = block.get("file")
        key = str(file_name) if isinstance(file_name, str) else str(pair)
        coverage[key] = PairCoverage(
            missing_quiet_ts=tuple(block.get("missing_quiet_ts") or ()),
            missing_not_recorded_ts=tuple(block.get("missing_not_recorded_ts") or ()),
            missing_partially_recorded_ts=tuple(
                block.get("missing_partially_recorded_ts") or ()
            ),
            partial_rows_ts=tuple(block.get("partial_rows_ts") or ()),
        )
    return coverage


class ArchiveReplay:
    """One or more archives, replayed as a single time-ordered decision-bar series.

    Construct with :meth:`from_directory` or :meth:`from_archives`. Neither touches the
    network, and there is no code path here that could: nothing in this module opens a
    socket, and the only I/O is reading files the caller named.
    """

    __slots__ = ("_clock", "_frames", "_interval_s", "_report", "_rows")

    def __init__(
        self,
        *,
        rows: Mapping[str, Sequence[Mapping[str, Any]]],
        archives: Mapping[str, ArchiveReport],
        interval_s: int,
        clock: SettableClock | None = None,
        coverage: Mapping[str, PairCoverage] | None = None,
        provenance: str | None = None,
        holes_mean_no_trades: bool | None = None,
    ) -> None:
        if interval_s <= 0:
            raise ValueError("interval_s must be positive")
        # Bars are built from the parsed rows and the frame from the same rows, so the
        # two can never disagree. Money keeps the archive's own precision on the way to
        # a bar: `to_frame` widens it to Decimal(38, 12), which is exact but is not the
        # text the archive carried, and a price that reads differently from the file it
        # came out of is a thing somebody will eventually have to explain.
        self._rows = {pair: list(items) for pair, items in rows.items()}
        self._frames = {pair: to_frame(items) for pair, items in self._rows.items()}
        self._interval_s = interval_s
        self._clock = clock

        timestamps = [
            int(row["ts"]) for items in self._rows.values() for row in items
        ]
        self._report = ReplayReport(
            interval_s=interval_s,
            pairs=tuple(sorted(self._frames)),
            archives=dict(archives),
            bar_count=len(timestamps),
            first_ts=min(timestamps) if timestamps else None,
            last_ts=max(timestamps) if timestamps else None,
            coverage_known=coverage is not None,
            holes_mean_no_trades=holes_mean_no_trades,
            coverage=dict(coverage or {}),
            coverage_note=(
                "Holes and thin rows are classified in PROVENANCE.json beside the "
                "archives. `missing_quiet_ts` are the only holes that mean no trades "
                "occurred; `missing_not_recorded_ts` were never watched and "
                "`partial_rows_ts` are rows built from a partly covered interval."
                if coverage is not None
                else COVERAGE_UNKNOWN_NOTE
            ),
            provenance=provenance,
        )

    @classmethod
    def from_archives(
        cls,
        archives: Mapping[str, Path] | Sequence[Path],
        *,
        interval_s: int,
        clock: SettableClock | None = None,
        derived_dir: Path | None = None,
        coverage: Mapping[str, PairCoverage] | None = None,
        provenance: str | None = None,
        holes_mean_no_trades: bool | None = None,
    ) -> ArchiveReplay:
        """Load named archives. ``archives`` maps pair to path, or is just paths.

        Each file goes through :func:`load_archive`, so the gap report on the result is
        the loader's own rather than a second opinion computed here.
        """
        if isinstance(archives, Mapping):
            named = {str(pair): Path(path) for pair, path in archives.items()}
        else:
            named = {pair_from_filename(Path(path)): Path(path) for path in archives}
        if not named:
            raise ArchiveError("no archive was given to replay")

        rows: dict[str, list[dict[str, Any]]] = {}
        reports: dict[str, ArchiveReport] = {}
        for pair, path in named.items():
            # The gap report is the loader's own, not a second opinion computed here —
            # which costs a second parse of the file. Deliberate: a report this module
            # derived for itself could agree with a bug in this module, and the gap
            # report is the artefact a criterion judges the archive by.
            reports[pair] = load_archive(
                path, interval_s=interval_s, pair=pair, derived_dir=derived_dir
            )
            rows[pair] = sorted(read_archive_rows(path), key=lambda item: int(item["ts"]))
        return cls(
            rows=rows,
            archives=reports,
            interval_s=interval_s,
            clock=clock,
            coverage=coverage,
            provenance=provenance,
            holes_mean_no_trades=holes_mean_no_trades,
        )

    @classmethod
    def from_directory(
        cls,
        directory: Path | str,
        *,
        interval_s: int,
        clock: SettableClock | None = None,
        pairs: Mapping[str, str] | None = None,
        derived_dir: Path | None = None,
    ) -> ArchiveReplay:
        """Every ``*.csv`` in ``directory``, with the sidecar picked up if it is there.

        ``*.csv`` and not ``*`` on purpose: the sidecar is JSON and sits in the same
        directory, and a glob that swept it up would hand `read_archive_rows` a file
        that is not a CSV and fail on the first line.

        :param pairs: optional map from file stem to the pair name to report, for when
            the file name is not the name the caller wants to see.
        """
        base = Path(directory)
        if not base.is_dir():
            raise ArchiveError(f"archive directory not found: {base}")
        paths = sorted(base.glob("*.csv"))
        if not paths:
            raise ArchiveError(f"no *.csv archive found in {base}")

        named: dict[str, Path] = {}
        for path in paths:
            key = pair_from_filename(path)
            named[(pairs or {}).get(path.stem, key)] = path

        payload = load_provenance(base)
        by_file = _coverage_from(payload)
        coverage: dict[str, PairCoverage] | None = None
        if payload is not None:
            coverage = {
                pair: by_file[path.name]
                for pair, path in named.items()
                if path.name in by_file
            }
        note = payload.get("provenance") if payload else None
        # Read as a strict `is True`, never as truthiness. A sidecar from before this
        # key existed has no answer, and "absent" must arrive as `None` — the unknown
        # case — rather than as `False`, which would claim the builder had measured
        # something it never looked at.
        flag = payload.get("holes_mean_no_trades") if payload else None
        return cls.from_archives(
            named,
            interval_s=interval_s,
            clock=clock,
            derived_dir=derived_dir,
            coverage=coverage,
            provenance=str(note) if isinstance(note, str) else None,
            holes_mean_no_trades=flag if isinstance(flag, bool) else None,
        )

    @property
    def report(self) -> ReplayReport:
        """The gap report and the coverage caveat, alongside the frame."""
        return self._report

    def frame(self, pair: str) -> pl.DataFrame:
        """One pair's archive as a `polars` frame, ascending, with exact `Decimal`
        money. The archive's own timestamps and no others."""
        return self._frames[pair]

    def frames(self) -> dict[str, pl.DataFrame]:
        return dict(self._frames)

    def bars(self, pair: str | None = None) -> Iterator[DecisionBar]:
        """Yield decision bars in timestamp order, advancing the injected clock.

        With ``pair``, one pair's series. Without it, every pair merged into a single
        ascending stream, ties broken by pair name so that two runs over the same
        archives produce byte-identical output — a replay that reordered simultaneous
        bars between runs would make a training set irreproducible from its config plus
        its data.

        **The tie-break is the only thing ordering simultaneous bars, deliberately.**
        This used to iterate `sorted(self._rows)` as well, so the rows went in in name
        order and Python's stable sort delivered the same result with or without the
        second element of the key. Two mechanisms for one guarantee, and a mutation that
        deleted the tie-break left all 43 tests green — no input could distinguish them.
        The redundancy is gone rather than an assertion added: there was nothing to
        assert against.

        The clock is moved to each bar's **close** before it is yielded. A consumer that
        reads the clock while holding a bar sees the first instant at which that bar was
        knowable, which is the whole anti-look-ahead mechanism: there is no reading of
        this clock from which a later bar is visible.
        """
        selected = [pair] if pair is not None else list(self._rows)
        ordered: list[tuple[int, str, int, Mapping[str, Any]]] = []
        for name in selected:
            for index, row in enumerate(self._rows[name]):
                ordered.append((int(row["ts"]), name, index, row))
        ordered.sort(key=lambda item: (item[0], item[1]))

        for ts, name, index, row in ordered:
            bar = DecisionBar(
                pair=name,
                ts=ts,
                interval_s=self._interval_s,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                trades=int(row["trades"]),
                index=index,
            )
            if self._clock is not None:
                self._clock.set(datetime.fromtimestamp(bar.close_ts, tz=UTC))
            yield bar
