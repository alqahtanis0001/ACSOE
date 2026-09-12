"""Engine 23 `backtest` — replay the archive and label it. Offline only.

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
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
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
    "Labeller",
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
        rows: list[dict[str, Any]] = []
        for pair in report.pairs:
            # One call per pair, never one call over the merged stream. A barrier
            # walked across a pair boundary steps from an XBTUSD bar to an ETHUSD bar
            # at a completely different price level, and every label after the boundary
            # is fabricated — with an identical row count either way.
            labels, series = labeller(
                replay.frame(pair),
                pair=pair,
                config=context.config,
                interval_s=interval_s,
            )
            pair_rows = _rows_of(labels)
            # The cutoff's cost, per pair, whether or not the pair makes the dataset:
            # operator ruling 2 asks for the number, and a pair dropped by the floor
            # would otherwise take its number with it.
            removed = int(getattr(series, "excluded_before_start", 0))
            before_start_by_pair[pair] = removed
            before_start += removed
            if floor and len(pair_rows) < floor:
                # Below `dataset.min_labelled_rows`. Reported by name with its count,
                # never silently absent from `pairs`: a dataset that quietly lost a
                # pair looks exactly like one that never had it.
                below_floor[pair] = len(pair_rows)
                continue
            per_pair[pair] = len(pair_rows)
            rows.extend(pair_rows)
            considered += int(getattr(series, "considered", 0))
            ambiguous += int(getattr(series, "ambiguous_count", 0))
            for name, count in (getattr(series, "counts", dict)() or {}).items():
                outcomes[name] = outcomes.get(name, 0) + int(count)

        written: str | None = None
        if self._write_slice and rows:
            written = self._write(rows, context)

        data: dict[str, Any] = {
            "archive_dir": self._archive_dir.as_posix(),
            "pairs": list(report.pairs),
            "bars_replayed": report.bar_count,
            "labelled_rows": len(rows),
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
            status=EngineStatus.OK if rows else EngineStatus.PASS,
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

    def _write(self, rows: Sequence[dict[str, Any]], context: EngineContext) -> str:
        """Write the labelled slice to `data/derived/`, named by the run.

        Named by ``run_id`` rather than overwritten, because two runs with different
        barriers produce different labels and a single well-known filename would let
        the second silently replace the first while every count in `state` still
        looked right.
        """
        import polars as pl

        self._derived_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        target = self._derived_dir / f"labelled_{context.run_id}_{stamp}.parquet"
        pl.DataFrame(list(rows)).write_parquet(target)
        return target.as_posix()
