"""Engine 23 `backtest` — replay the archive and label it, and drive the chain. Offline only.

**Two jobs since Phase 7.** `BacktestEngine` below is Phase 4's labeller and is unchanged.
`ChainReplay`, at the end of this module, is spec 131's driver: it steps the registered
guard, opportunity and manage chains over a window of history, one tick at a time on an
injected clock, and decides nothing but *when* the next tick is and *which fold's* models
are in force. `acsoe research backtest` (in `cli/research.py`) wires it. The paragraphs
below describe the labeller as Phase 4 built it.

Spec 55. In **this** phase a backtest is **replay plus triple-barrier labelling and
nothing more**: it produces the dataset Phase 5 trains on. It does not run historical
data through the twenty-three engines, because engines 5 to 16 do not exist yet — that
is Phase 6 and Phase 7 work and the phase gate forbids it here.

## Where this engine is registered, and where it must never be

`OFFLINE_CHAIN` in `acsoe.cli.research`, and nowhere else. **Never `bootstrap.py`.**
That is the whole mechanism keeping architecture invariant 5 true: `bootstrap.py` builds
the three runtime chains, so the live loop never imports from `research/`, and the only
module that assembles the offline chain is a CLI entry point the daemon never loads.

This module is the **one** module under `research/` that imports from `acsoe.core`, and
it has to: an engine is a `BaseEngine`. `historical.py` and `replay.py` import nothing
from the live loop at all and there are tests asserting it of each. The direction that
costs money is the other one — a live engine reaching into research code — and
`test_the_live_loop_does_not_import_research` guards it.

## No spread. Say so in the output, not in a docstring.

The archives are OHLCVT: open, high, low, close, volume, trade count. There is no bid,
no ask, no depth and no spread in this data and none can be recovered for it, so engine
9 `order_book` and the spread half of engine 10 `cost` **cannot be backtested from this
source**, and a backtest that silently assumes zero spread is invalid. That statement
travels in `state["backtest"]` rather than sitting here where nobody reads it at the
point of use.

## The labeller is C's, and this engine fails closed without it

`research/labelling.py` belongs to C (spec 52). This engine calls it through
:data:`LABELLER_ATTR` on :data:`LABELLER_MODULE` and **refuses rather than inventing a
label** when it is absent — an unlabelled slice that reports success is exactly the
Phase 4 failure mode, and a labeller stubbed out here would be a second, worse labeller
nobody knew about. The import is late and by name so that this module stays importable,
and therefore registrable and inspectable by `is_gate_matches_registry`, before C's
module exists.

**The barriers never cross this seam.** `label_frame` takes the `Config` and reads
`barriers.target_pct`, `barriers.stop_pct` and `barriers.timeout_bars` itself, so there
is exactly one place in the project that turns those three keys into thresholds. This
engine reads them only to *report* them, and through C's own `read_barriers`, so the
report cannot disagree with the labels — a second reader converting `0.015` a different
way moves the stop barrier in the sixteenth decimal and nothing would ever find it.
"""

from __future__ import annotations

import importlib
import itertools
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Final, Protocol, runtime_checkable

from acsoe.core.contracts import (
    BaseEngine,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.research.historical import NO_BOOK_NOTE
from acsoe.research.replay import ArchiveReplay

__all__ = [
    "DEFAULT_ARCHIVE_DIR",
    "DEFAULT_DERIVED_DIR",
    "LABELLER_ATTR",
    "LABELLER_MODULE",
    "STATE_KEY",
    "BacktestEngine",
    "ChainReplay",
    "FoldWindow",
    "Labeller",
    "ReplaySummary",
    "closed_bar_open",
    "fold_for_tick",
    "next_tick_s",
    "replay_bounds",
]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "backtest"

#: Where `scripts/build_ohlcvt.py` puts the 15-minute bars it reduces from the
#: operator's Kraken time-and-sales archive, and where `scripts/verify.py`'s
#: `replay_full_archive` looks. The operator's own 27 GB of source files live one
#: level down, in `KRAKEN_TimeAndSales_Combined/` and `TimeAndSales_Combined/`, so
#: the non-recursive `*.csv` glob that reads this directory sees only derived bars.
DEFAULT_ARCHIVE_DIR: Final = Path("data") / "historical"

#: Where the labelled slice is written. `data/derived/` is rebuildable output; nothing
#: here is ever written back into `data/historical/` or `data/raw/`. Invariant 11.
DEFAULT_DERIVED_DIR: Final = Path("data") / "derived"

LABELLER_MODULE: Final = "acsoe.research.labelling"
LABELLER_ATTR: Final = "label_frame"

#: Operator rulings 2 and 3 of 2026-09-12, both under `dataset:` in config/default.yaml.
KEY_DECISION_START_DATE: Final = "dataset.decision_start_date"
KEY_MIN_LABELLED_ROWS: Final = "dataset.min_labelled_rows"

NO_SPREAD_NOTE: Final = (
    "This backtest models no spread, because the archive contains none. Engine 9 "
    "`order_book` and the spread component of engine 10 `cost` cannot be backtested "
    "from an OHLCVT source, and a backtest that silently assumes zero spread is invalid."
)

PHASE_NOTE: Final = (
    "A backtest in Phase 4 is replay plus triple-barrier labelling and nothing more. "
    "Engines 5 to 16 do not exist yet, so no candidate is scored, no cost gate is "
    "applied and no trade is simulated. This produces the dataset Phase 5 trains on."
)


@runtime_checkable
class Labeller(Protocol):
    """The seam to C's `acsoe.research.labelling.label_frame`, spec 52.

    Takes the `polars` frame `research/historical.py` produces — which is exactly what
    :meth:`ArchiveReplay.frame` hands over — and returns ``(labels, series)``: a frame
    of labelled rows and a summary object carrying the counts that say how much to
    trust them.

    Everything after the frame is keyword-only, which is C's choice and the right one:
    ``pair`` and ``interval_s`` are both scalars about the same series and a positional
    call would let a caller transpose them into something that still runs.
    """

    def __call__(
        self,
        frame: Any,
        *,
        pair: str,
        config: Any,
        interval_s: int,
    ) -> tuple[Any, Any]:
        ...


def _rows_of(labels: Any) -> list[dict[str, Any]]:
    """One pair's labelled rows as plain dicts, from whatever `label_frame` returned.

    `label_frame` returns a `polars` frame, and `to_dicts` is the direct route. A
    sequence of mappings is accepted too, because a caller injecting a double should
    not have to build a frame to do it.

    What is **not** flexible is what happens when the shape is wrong: it raises. A
    labeller whose output cannot be read must stop the run, not produce rows of `None`
    that Phase 5 would train on — nothing would crash and nothing would go red.
    """
    to_dicts = getattr(labels, "to_dicts", None)
    if callable(to_dicts):
        rows = to_dicts()
        if isinstance(rows, list):
            return [dict(row) for row in rows]
    if isinstance(labels, Sequence) and not isinstance(labels, (str, bytes)):
        materialised = list(labels)
        if all(isinstance(row, Mapping) for row in materialised):
            return [dict(row) for row in materialised]
    raise TypeError(
        f"{LABELLER_MODULE}.{LABELLER_ATTR} returned a {type(labels).__name__}, which is "
        "neither a polars frame nor a sequence of mappings. Labelled rows that cannot be "
        "read are not labels, and an unreadable result must stop the run rather than "
        "become a slice of nulls."
    )


def _height(labels: Any) -> int:
    """How many labelled rows one pair produced, without materialising them.

    The point of asking a frame for its height instead of calling :func:`_rows_of` is
    the whole of spec 78: `to_dicts()` on twenty million rows is what cost 51.9 GB.
    A double that returns a sequence of mappings is still supported, and for that the
    only honest answer is its length.
    """
    height = getattr(labels, "height", None)
    if isinstance(height, int):
        return height
    return len(_rows_of(labels))


def _arrow_table(labels: Any, *, pair: str) -> Any:
    """One pair's labelled rows as an arrow table, for the writer.

    Takes the frame's own arrow buffers when there is a frame — no Python objects are
    built at all on that path — and falls back to building a table from mappings for an
    injected double.
    """
    # Local ignore rather than a `pyarrow.*` mypy override, following the decision B
    # recorded in `clients/store/parquet.py`: this project runs `warn_unused_ignores`,
    # so a global override turns every existing local ignore into an error instead of
    # removing the need for one. Adding the override is exactly what I did first, and
    # it made B's two lines red.
    import pyarrow as pa  # type: ignore[import-untyped]

    to_arrow = getattr(labels, "to_arrow", None)
    if callable(to_arrow):
        return to_arrow()
    rows = _rows_of(labels)
    if not rows:
        raise ValueError(f"{pair}: no rows to write")
    return pa.Table.from_pylist(rows)


class _SliceWriter:
    """One parquet file, written pair by pair instead of all at once.

    Spec 78. Engine 23 used to accumulate every labelled row of every pair in one
    Python list and write once at the end, which needed about 50 GB of memory to
    produce a 429 MB file over the 234-pair archive. This holds one pair at a time.

    **The schema is established by the first pair and every later pair is cast to it.**
    That is not defensive decoration. `label_frame` builds `pl.DataFrame(payload)` per
    pair, so polars infers the dtypes **per pair**, and a column that happens to be
    entirely null for one thin pair infers as `Null` where another pair has `Int64`.
    Measured across five real archive pairs and all five agree — which is evidence that
    the common case is fine, not a guarantee about the 234th. A parquet writer needs
    one fixed schema for the file, so the choice is to cast or to crash, and a cast
    that cannot be done raises here naming the pair and the schema rather than writing
    a row group whose types silently disagree with the rest of the file.

    Opened lazily, on the first pair that has rows, so a run that labels nothing writes
    no file at all — which is what the accumulating version did and what the tests
    assert.
    """

    def __init__(self, target: Path) -> None:
        self._target = target
        self._writer: Any = None
        self._schema: Any = None
        self.rows_written = 0
        self.pairs_written: list[str] = []

    @property
    def target(self) -> Path:
        return self._target

    def write(self, pair: str, labels: Any) -> None:
        import pyarrow.parquet as pq  # type: ignore[import-untyped]

        table = _arrow_table(labels, pair=pair)
        if table.num_rows == 0:
            return
        if self._writer is None:
            self._target.parent.mkdir(parents=True, exist_ok=True)
            self._schema = table.schema
            # `compression="zstd"` because that is what `polars.write_parquet` used
            # before spec 78 and pyarrow's own default is snappy. Measured on the full
            # archive: the same 20,331,237 rows came out at 667 MB under snappy against
            # 429 MB under zstd. Nothing downstream reads the codec, but a slice that
            # silently grew by half would be a change to the artefact made by an
            # implementation detail of the writer rather than by anyone's decision.
            self._writer = pq.ParquetWriter(self._target, self._schema, compression="zstd")
        elif table.schema != self._schema:
            try:
                table = table.cast(self._schema)
            except (ValueError, TypeError) as exc:
                raise RuntimeError(
                    f"{pair}: its labelled frame has a schema the slice cannot hold. "
                    f"The file was opened as {self._schema} and this pair produced "
                    f"{table.schema}. A row group written under a coerced schema is a "
                    "column that means something different for some pairs than for "
                    "others, and nothing downstream would report it."
                ) from exc
        self._writer.write_table(table)
        self.rows_written += table.num_rows
        self.pairs_written.append(pair)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None

    @property
    def wrote_anything(self) -> bool:
        return bool(self.pairs_written)


def _labelled_rows_floor(context: EngineContext) -> int:
    """``dataset.min_labelled_rows``, the per-pair floor. ``0`` is no floor.

    Read once per run and refused when null or negative rather than defaulted: a floor
    that silently became zero would be the same as no floor, and the knob exists so
    that the decision is visible.
    """
    value = context.config.get(KEY_MIN_LABELLED_ROWS)
    if value is None:
        raise RuntimeError(
            f"config key `{KEY_MIN_LABELLED_ROWS}` is null. It has no default here: write "
            "0 for no floor, so the absence of one is a stated value rather than a hole."
        )
    floor = int(value)
    if floor < 0:
        raise RuntimeError(
            f"config key `{KEY_MIN_LABELLED_ROWS}` is {floor}; it cannot be negative"
        )
    return floor


class BacktestEngine(BaseEngine):
    """Replay the archive, label it, write the slice, report what it produced.

    The archive directory, the output directory and the labeller are all injectable so
    that a test can drive the real engine over a fabricated archive. **The barriers are
    not injectable**: they come from `config.barriers` on every run, because a barrier
    written into a test is a barrier that can disagree with the one the operator chose,
    and the label is the thing the whole of Phase 5 believes.
    """

    name: ClassVar[str] = "backtest"
    number: ClassVar[int] = 23
    is_gate: ClassVar[bool] = False

    def __init__(
        self,
        *,
        archive_dir: Path | str = DEFAULT_ARCHIVE_DIR,
        derived_dir: Path | str = DEFAULT_DERIVED_DIR,
        labeller: Labeller | None = None,
        write_slice: bool = True,
    ) -> None:
        self._archive_dir = Path(archive_dir)
        self._derived_dir = Path(derived_dir)
        self._labeller = labeller
        self._write_slice = write_slice

    def _resolve_labeller(self) -> Labeller:
        """C's labeller, imported late and by name.

        Late so that this module is importable — and so the engine is registrable and
        inspectable by `is_gate_matches_registry` — before `research/labelling.py`
        exists. Raising here is the point: it becomes `ERROR` at the caller, and an
        absent labeller must stop the run rather than produce an unlabelled slice that
        reports success.
        """
        if self._labeller is not None:
            return self._labeller
        try:
            module = importlib.import_module(LABELLER_MODULE)
        except ImportError as exc:
            raise RuntimeError(
                f"{LABELLER_MODULE} does not exist yet (spec 52, owned by C). Engine 23 "
                "refuses to run rather than write an unlabelled slice: a backtest that "
                "reports success over unlabelled data is the Phase 4 failure that looks "
                "like success."
            ) from exc
        labeller = getattr(module, LABELLER_ATTR, None)
        if not callable(labeller):
            raise RuntimeError(
                f"{LABELLER_MODULE} exists but has no callable {LABELLER_ATTR!r}. "
                "Engine 23 calls exactly that name; the seam is recorded in "
                "context/ownership.md."
            )
        return labeller  # type: ignore[no-any-return]

    # ARG002: `state` is unused and stays in the signature — the interface is fixed,
    # and this engine reads nothing from the tick. It runs in the offline chain, where
    # there is no guard chain, no manage chain and no other engine to read from: the
    # archive on disk is the entire input. Same reason engines 1 and 3 carry this.
    def process(self, context: EngineContext, state: State) -> EngineResult:  # noqa: ARG002
        started = time.perf_counter()

        interval_s = int(context.config.get("timeframes.decision_bar_s"))

        replay = ArchiveReplay.from_directory(self._archive_dir, interval_s=interval_s)
        report = replay.report
        labeller = self._resolve_labeller()

        floor = _labelled_rows_floor(context)

        per_pair: dict[str, int] = {}
        outcomes: dict[str, int] = {}
        ambiguous = 0
        considered = 0
        before_start = 0
        before_start_by_pair: dict[str, int] = {}
        below_floor: dict[str, int] = {}
        total_rows = 0
        # Spec 78. Opened on the first pair that has rows and closed in the `finally`
        # below, so an exception part-way through leaves a closed, readable parquet of
        # the pairs that did finish rather than a truncated file with no footer.
        slice_writer = _SliceWriter(self._slice_target(context)) if self._write_slice else None
        try:
            for pair in report.pairs:
                # One call per pair, never one call over the merged stream. A barrier
                # walked across a pair boundary steps from an XBTUSD bar to an ETHUSD
                # bar at a completely different price level, and every label after the
                # boundary is fabricated — with an identical row count either way.
                labels, series = labeller(
                    replay.frame(pair),
                    pair=pair,
                    config=context.config,
                    interval_s=interval_s,
                )
                # The height rather than the rows. `to_dicts()` over twenty million
                # rows is what spec 78 exists to remove, and every number below only
                # ever needed a count.
                pair_height = _height(labels)
                # The cutoff's cost, per pair, whether or not the pair makes the
                # dataset: operator ruling 2 asks for the number, and a pair dropped by
                # the floor would otherwise take its number with it.
                removed = int(getattr(series, "excluded_before_start", 0))
                before_start_by_pair[pair] = removed
                before_start += removed
                if floor and pair_height < floor:
                    # Below `dataset.min_labelled_rows`. Reported by name with its
                    # count, never silently absent from `pairs`: a dataset that quietly
                    # lost a pair looks exactly like one that never had it.
                    below_floor[pair] = pair_height
                    continue
                per_pair[pair] = pair_height
                total_rows += pair_height
                considered += int(getattr(series, "considered", 0))
                ambiguous += int(getattr(series, "ambiguous_count", 0))
                for name, count in (getattr(series, "counts", dict)() or {}).items():
                    outcomes[name] = outcomes.get(name, 0) + int(count)
                if slice_writer is not None and pair_height:
                    slice_writer.write(pair, labels)
                # This pair's rows are released here, and that line is the whole spec:
                # what used to live until the end of the run now lives until the end of
                # the iteration.
                del labels, series
        finally:
            # Closed on every path, so a run that raises part-way leaves a readable
            # parquet of the pairs that did finish rather than a file with no footer.
            if slice_writer is not None:
                slice_writer.close()

        written: str | None = None
        if slice_writer is not None and slice_writer.wrote_anything:
            written = slice_writer.target.as_posix()
            if slice_writer.rows_written != total_rows:
                # The report and the file are two records of one thing. A dataset whose
                # stated size disagrees with its own parquet is worse than either
                # number alone, and this can only fire if a later edit lets a pair be
                # counted and not written, or written and not counted.
                raise RuntimeError(
                    f"the slice holds {slice_writer.rows_written} rows and the report "
                    f"counted {total_rows}; they are the same rows and must agree"
                )

        data: dict[str, Any] = {
            "archive_dir": self._archive_dir.as_posix(),
            "pairs": list(report.pairs),
            "bars_replayed": report.bar_count,
            "labelled_rows": total_rows,
            "labelled_rows_by_pair": per_pair,
            "decision_bars_considered": considered,
            "label_counts": outcomes,
            # Ruling 1: a bar that touched both barriers is labelled `stop`, because
            # OHLC carries no intra-bar ordering and the pessimistic reading is the
            # only one that cannot flatter the strategy. Reported, because a slice
            # where most labels were decided by a ruling rather than by the data is a
            # slice a reader is entitled to distrust.
            "ambiguous_labels": ambiguous,
            # Ruling 2, 2026-09-12: decision bars before `dataset.decision_start_date`
            # are excluded for tradability, not data quality, and the cost is reported
            # per pair rather than absorbed into a smaller row count.
            "decision_start_date": str(context.config.get(KEY_DECISION_START_DATE)),
            "excluded_before_start": before_start,
            "excluded_before_start_by_pair": before_start_by_pair,
            # Ruling 3, 2026-09-12: a per-pair floor that is 0 today, so nothing is
            # excluded, and a named knob rather than an overlooked question.
            "min_labelled_rows": floor,
            "pairs_below_floor": below_floor,
            "first_ts": report.first_ts,
            "last_ts": report.last_ts,
            "span_seconds": report.span_seconds,
            "gap_count": sum(a.gap_count for a in report.archives.values()),
            "interval_s": interval_s,
            "barriers": self._barriers(context),
            # Three statements carried in the output rather than in a docstring,
            # because each one is a limit on what a reader may conclude from the rows.
            "has_order_book": False,
            "has_spread": False,
            "book_note": NO_BOOK_NOTE,
            "spread_note": NO_SPREAD_NOTE,
            # How much of this result was priced on an exact spread and how much on
            # an approximation, per tier, from the replay that produced it.
            #
            # `has_spread: False` above is a yes-or-no about a source that has none;
            # this is the arithmetic for a source that has some. They are not the
            # same statement and the second cannot be derived from the first: a
            # replay reading the recorder's own archive will have tier 1 exact
            # spreads for its ten most liquid pairs and tier 2 minute medians for
            # the other 137, and `has_spread: True` would then be true and useless.
            # A reader asked to weigh a backtest needs the fraction, not the flag.
            "spread_provenance": report.spread_provenance(),
            "phase_note": PHASE_NOTE,
            # And the one that decides whether a barrier may be walked across a hole.
            # `None` means unknown and a consumer must treat it as `False` would be
            # treated: invariant 3, the absence of a "no" is never a "yes".
            "holes_mean_no_trades": report.holes_mean_no_trades,
            "provenance": report.provenance,
            "slice_path": written,
        }

        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK if total_rows else EngineStatus.PASS,
            blocks_trading=False,
            data=data,
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    def _barriers(self, context: EngineContext) -> dict[str, Any]:
        """The three barriers, for the report only, read through **C's own reader**.

        `label_frame` reads them itself, so this engine must not become a second reader
        of the same three keys. `read_barriers` converts a YAML float with `repr` rather
        than `str` — `Decimal(0.015)` is `0.01499999999999999944...` — and a report that
        converted them the other way would disagree with the labels in the sixteenth
        decimal, which is a discrepancy nobody would ever chase down.

        Money crosses `state` as an exact decimal string. `EngineResult` refuses a
        `Decimal` in `data` and *accepts* a `float`, and the reflexive cast on hitting
        that refusal is what publishes a barrier that has already lost precision.
        """
        module = importlib.import_module(LABELLER_MODULE)
        barriers = module.read_barriers(context.config)
        return {
            "target_pct": str(barriers.target_pct),
            "stop_pct": str(barriers.stop_pct),
            "timeout_bars": int(barriers.timeout_bars),
        }

    def _slice_target(self, context: EngineContext) -> Path:
        """Where this run's labelled slice goes. Same convention as before spec 78.

        Named by ``run_id`` rather than overwritten, because two runs with different
        barriers produce different labels and a single well-known filename would let
        the second silently replace the first while every count in `state` still
        looked right.

        **The stamp comes from ``context.now``, not from the clock.** It used to read
        ``datetime.now(tz=UTC)`` here, which is a direct clock read inside an engine and
        invariant 9 forbids one without qualification. It could not bias a label — it
        only names a file — but "it is only a filename" is the argument that puts the
        second one somewhere that matters, and the injected clock makes a replay's
        output name reproducible from its inputs, which is the property invariant 9 is
        really protecting.
        """
        stamp = context.now.strftime("%Y%m%dT%H%M%SZ")
        return self._derived_dir / f"labelled_{context.run_id}_{stamp}.parquet"


# --------------------------------------------------------------------------- #
# Phase 7, spec 131: engine 23 drives the registered chains over history
# --------------------------------------------------------------------------- #
#
# Everything below is the *driver*. It makes no decision: it chooses when the next tick
# happens, which fold's models are in force, and nothing else. The chains are
# `bootstrap.py`'s, unchanged, and the orchestrator is `core/`'s, unchanged, stepped one
# tick at a time on an injected clock. Engine 19 writes every row.
#
# It is written against callables and duck types rather than the store, the clients or
# `bootstrap.py`, because this module is under `research/` and architecture invariant 5
# keeps the live loop's modules out of it. `cli/research.py` is the one place allowed
# to import both sides, and it does the wiring.


@dataclass(frozen=True)
class FoldWindow:
    """One fold's test week and the Phase 7 run directory that scores it."""

    fold: int
    run_id: str
    test_start_s: int
    test_end_s: int

    def holds_bar(self, bar_open_s: int) -> bool:
        return self.test_start_s <= bar_open_s < self.test_end_s


def closed_bar_open(tick_s: int, *, bar_s: int) -> int:
    """The opening second of the latest bar closed at or before `tick_s`.

    The bar a decision on this tick is about. Its fold is the one whose test window
    holds that opening, which is how the out-of-sample file assigned rows to folds.
    """
    return (tick_s // bar_s) * bar_s - bar_s


def fold_for_tick(folds: Sequence[FoldWindow], tick_s: int, *, bar_s: int) -> FoldWindow:
    bar_open = closed_bar_open(tick_s, bar_s=bar_s)
    matches = [fold for fold in folds if fold.holds_bar(bar_open)]
    if len(matches) != 1:
        raise RuntimeError(
            f"{len(matches)} folds hold the bar opening at {bar_open}; exactly one must, "
            "or the driver would score a bar with a model it was not tested with"
        )
    return matches[0]


def replay_bounds(folds: Sequence[FoldWindow], *, bar_s: int) -> tuple[int, int]:
    """The first and last tick of a window: the close of its first bar and of its last.

    Checked contiguous, because a gap between two folds' test weeks would be a week the
    driver silently skipped.
    """
    ordered = sorted(folds, key=lambda fold: fold.test_start_s)
    for earlier, later in itertools.pairwise(ordered):
        if earlier.test_end_s != later.test_start_s:
            raise RuntimeError(
                f"fold {earlier.fold} ends at {earlier.test_end_s} and fold {later.fold} "
                f"starts at {later.test_start_s}; the window must be contiguous"
            )
    return ordered[0].test_start_s + bar_s, ordered[-1].test_end_s


def next_tick_s(
    last_s: int | None, *, exposed: bool, start_s: int, end_s: int, bar_s: int, loop_s: int
) -> int | None:
    """When the next tick happens, or `None` once the window is over.

    Spec 131 step 1. A tick at every bar close, whether or not anything traded, because
    engine 3 owns the bar clock and engines 4 and 17 must see the quiet bars. Between bar
    closes, a tick every `loop_s` **only** while exposure exists (an open position or a
    resting order), because a stop touched in a skipped minute would be missed. The
    minute grid and the bar grid coincide (`loop_s` divides `bar_s`, which the config
    enforces), so an exposed run still lands exactly on every bar close.
    """
    if last_s is None:
        candidate = start_s
    elif exposed:
        candidate = last_s + loop_s
    else:
        candidate = (last_s // bar_s + 1) * bar_s
    return candidate if candidate <= end_s else None


@dataclass
class ReplaySummary:
    ticks: int = 0
    bar_ticks: int = 0
    minute_ticks: int = 0
    first_tick_s: int | None = None
    last_tick_s: int | None = None
    fold_switches: list[tuple[int, int, str]] = field(default_factory=list)
    finished: bool = False


class ChainReplay:
    """Engine 23's chain mode: step the registered orchestrator over a window.

    :param tick: runs one orchestrator tick. The orchestrator itself is untouched.
    :param set_clock: moves the injected clock the orchestrator and the clients share.
    :param use_config: points the config view at a freshly built per-fold config.
    :param exposed: reads the store: is a position open or an order resting?
    :param activate: writes one `activate` command through the store, as an operator
        would, before the first tick of a process.
    :param record: appends one line to the run record, a JSON-able mapping.
    :param config_for: builds the config for one fold, never by mutating a loaded one.
    """

    def __init__(
        self,
        *,
        folds: Sequence[FoldWindow],
        bar_s: int,
        loop_s: int,
        tick: Callable[[], Any],
        set_clock: Callable[[int], None],
        use_config: Callable[[Any], None],
        config_for: Callable[[FoldWindow], Any],
        exposed: Callable[[], bool],
        activate: Callable[[int], None],
        record: Callable[[Mapping[str, Any]], None],
        wall: Callable[[], float] = time.perf_counter,
    ) -> None:
        if bar_s <= 0 or loop_s <= 0 or bar_s % loop_s:
            raise ValueError("the loop tick must divide the decision bar")
        self._folds = tuple(sorted(folds, key=lambda fold: fold.test_start_s))
        self._bar_s = bar_s
        self._loop_s = loop_s
        self._tick = tick
        self._set_clock = set_clock
        self._use_config = use_config
        self._config_for = config_for
        self._exposed = exposed
        self._activate = activate
        self._record = record
        self._wall = wall
        self.start_s, self.end_s = replay_bounds(self._folds, bar_s=bar_s)

    def run(
        self,
        *,
        resume_after_s: int | None = None,
        begin_s: int | None = None,
        stop_after_s: int | None = None,
        max_ticks: int | None = None,
    ) -> ReplaySummary:
        """Tick from the window's start, or from the tick after `resume_after_s`.

        `begin_s` and `stop_after_s` cut a sub-window out of the ruled one, the
        rehearsal's one day (spec 142): the first tick is the first bar close at or
        after `begin_s`, and the last is at or before `stop_after_s`. `max_ticks` exists
        for a test that kills a run part-way. None of the three skips a tick the
        schedule requires inside the span it runs: they bound the run, never thin it.
        """
        summary = ReplaySummary()
        end_s = self.end_s if stop_after_s is None else min(self.end_s, stop_after_s)
        start_s = self.start_s
        if begin_s is not None:
            aligned = -(-begin_s // self._bar_s) * self._bar_s
            if aligned < self.start_s or aligned > self.end_s:
                raise ValueError("begin_s lies outside the window the folds cover")
            start_s = aligned
        last_s = resume_after_s
        exposed = self._exposed() if resume_after_s is not None else False
        current: FoldWindow | None = None
        activated = False
        while True:
            tick_s = next_tick_s(
                last_s,
                exposed=exposed,
                start_s=start_s,
                end_s=end_s,
                bar_s=self._bar_s,
                loop_s=self._loop_s,
            )
            if tick_s is None:
                summary.finished = True
                break
            if max_ticks is not None and summary.ticks >= max_ticks:
                break
            fold = fold_for_tick(self._folds, tick_s, bar_s=self._bar_s)
            if fold != current:
                self._use_config(self._config_for(fold))
                summary.fold_switches.append((tick_s, fold.fold, fold.run_id))
                self._record(
                    {"event": "fold_switch", "tick_s": tick_s, "fold": fold.fold,
                     "run_id": fold.run_id}
                )
                current = fold
            self._set_clock(tick_s)
            if not activated:
                # Before this process's first tick, exactly as an operator would press
                # Activate. On a resume the new process starts idle like any restarted
                # daemon, so it is written again, and the run record says it was a restart.
                self._activate(tick_s)
                self._record(
                    {"event": "restart" if resume_after_s is not None else "start",
                     "tick_s": tick_s, "resume_after_s": resume_after_s}
                )
                activated = True
            started = self._wall()
            self._tick()
            wall_ms = (self._wall() - started) * 1000.0
            exposed = self._exposed()
            bar_tick = tick_s % self._bar_s == 0
            self._record(
                {"event": "tick", "tick_s": tick_s, "fold": fold.fold, "bar_tick": bar_tick,
                 "exposed_after": exposed, "wall_ms": round(wall_ms, 3)}
            )
            summary.ticks += 1
            summary.bar_ticks += int(bar_tick)
            summary.minute_ticks += int(not bar_tick)
            summary.first_tick_s = summary.first_tick_s or tick_s
            summary.last_tick_s = tick_s
            last_s = tick_s
        return summary
