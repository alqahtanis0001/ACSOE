"""Triple-barrier labelling. Spec 52.

Turns a series of closed 15-minute candles into labels: ``target`` at
``barriers.target_pct``, ``stop`` at ``barriers.stop_pct``, ``timeout`` at
``barriers.timeout_bars``. **Every one of those three values comes from
``config/default.yaml`` and none of them is written into this module.**

## Research only. Never the live path.

A label is built from bars *after* the decision bar, so it is future information by
construction. Invariant 10 confines it to the training pipeline: nothing in
``acsoe.engines``, ``acsoe.core``, ``acsoe.clients`` or ``acsoe.cli`` may import this
module, and this module imports nothing from them.
``tests/research/test_labelling.py`` asserts both directions.

## Two lead rulings, because the obvious reading is silently wrong

**1. A bar that touches both barriers is labelled ``stop``.** An OHLC candle whose high
reaches the target and whose low reaches the stop does not say which came first, and the
archive carries no intra-bar sequence to recover it from. Labelling it ``target``
invents the favourable ordering on exactly the bars where the market was most violent,
and a model trained on that learns an edge that does not exist. The pessimistic reading
is the only one that cannot flatter the strategy. Every such row carries ``ambiguous``,
and :class:`LabelledSeries` reports the count — a slice where that number is large is a
slice whose labels are mostly an assumption.

**2. The timeout barrier is a time, not a count of rows.** The archives contain only
intervals in which trades occurred, so 48 *existing rows* can span days across a quiet
period. The horizon is ``decision_ts + timeout_bars * interval_s``; the walk visits
whatever candles exist inside that window and stops at its end. Counting rows silently
stretches a 12-hour horizon into a multi-day one over precisely the gaps
``research/historical.py`` refuses to interpolate away.

## Three further rules, each of which is a label that would otherwise be fabricated

**A decision bar whose window runs past the end of the series is not labelled at all.**
It is excluded, never labelled ``timeout``. Labelling it records an outcome that has not
happened yet, which is invariant 10 with a different face.

**The decision bar itself is never inspected for a touch.** Its own high and low are
inside the bar the decision was made on; reading them is look-ahead within one bar.

**A window containing no candles at all is excluded**, and this one is a judgement
rather than a rule handed down: a ``timeout`` label needs a terminal price to compute a
return from, and across a multi-day hole there is none. Excluding is the reading that
invents nothing. The count is reported so the decision is visible rather than silent.
"""

from __future__ import annotations

import bisect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, Protocol

import polars as pl

__all__ = [
    "BARRIER_LABELS",
    "LABEL_COLUMNS",
    "LABEL_STOP",
    "LABEL_TARGET",
    "LABEL_TIMEOUT",
    "Barriers",
    "Label",
    "LabelledSeries",
    "label_candles",
    "label_frame",
    "label_series",
    "read_barriers",
]

LABEL_TARGET: Final = "target"
LABEL_STOP: Final = "stop"
LABEL_TIMEOUT: Final = "timeout"

#: The three outcomes. There is no fourth and spec 52 forbids inventing one.
BARRIER_LABELS: Final[tuple[str, ...]] = (LABEL_TARGET, LABEL_STOP, LABEL_TIMEOUT)

KEY_TARGET_PCT: Final = "barriers.target_pct"
KEY_STOP_PCT: Final = "barriers.stop_pct"
KEY_TIMEOUT_BARS: Final = "barriers.timeout_bars"

#: Columns of the frame :func:`label_frame` returns, in order.
LABEL_COLUMNS: Final[tuple[str, ...]] = (
    "pair",
    "decision_ts",
    "close",
    "target_price",
    "stop_price",
    "label",
    "touch_ts",
    "bars_elapsed",
    "touch_price",
    "label_window_end_ts",
    "return_pct",
    "ambiguous",
    "candles_in_window",
)


class _Config(Protocol):
    """Just enough of ``acsoe.core.contracts.Config`` to read three thresholds.

    Declared structurally rather than imported. ``core`` is the live path and invariant
    10 keeps this module out of it in both directions; a `Protocol` gives the same type
    checking with no import edge.
    """

    def get(self, dotted_key: str, /) -> Any: ...


@dataclass(frozen=True, slots=True)
class Barriers:
    """The three thresholds, as exact decimals and an integer bar count."""

    target_pct: Decimal
    stop_pct: Decimal
    timeout_bars: int

    def timeout_at(self, decision_ts: int, interval_s: int) -> int:
        """The instant the window closes. **A time, not a row count.** Ruling 2."""
        return decision_ts + self.timeout_bars * interval_s


def _decimal(value: Any, key: str) -> Decimal:
    """A config threshold as an exact ``Decimal``.

    ``repr`` on a float, never ``Decimal(float)``. YAML parses ``0.015`` into a float, and
    ``Decimal(0.015)`` is ``0.01499999999999999944488848768742172978818416595458984375``
    — which moves the stop barrier in the sixteenth decimal and makes every hand-verified
    price disagree with the labeller for a reason nobody would find.
    """
    if value is None:
        raise ValueError(f"config key `{key}` is null; a barrier cannot be defaulted")
    if isinstance(value, float):
        return Decimal(repr(value))
    return Decimal(str(value))


def read_barriers(config: _Config) -> Barriers:
    """The three barrier settings from config. Never a literal in this module."""
    return Barriers(
        target_pct=_decimal(config.get(KEY_TARGET_PCT), KEY_TARGET_PCT),
        stop_pct=_decimal(config.get(KEY_STOP_PCT), KEY_STOP_PCT),
        timeout_bars=int(config.get(KEY_TIMEOUT_BARS)),
    )


@dataclass(frozen=True, slots=True)
class Label:
    """One labelled decision bar.

    ``label_window_end_ts`` is the seam with `research/walkforward.py`: it is the instant
    at which this row's outcome became known, and it is what the splitter purges on. For
    a touched barrier that is the touch; for a timeout it is the horizon, which is later
    than the last candle whenever the window ends inside a gap. **Purging on
    ``decision_ts`` instead is the most plausible wrong implementation in the project.**
    """

    pair: str
    decision_ts: int
    close: Decimal
    target_price: Decimal
    stop_price: Decimal
    label: str
    touch_ts: int
    bars_elapsed: int
    touch_price: Decimal
    label_window_end_ts: int
    return_pct: float
    ambiguous: bool
    candles_in_window: int

    def as_row(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "decision_ts": self.decision_ts,
            "close": str(self.close),
            "target_price": str(self.target_price),
            "stop_price": str(self.stop_price),
            "label": self.label,
            "touch_ts": self.touch_ts,
            "bars_elapsed": self.bars_elapsed,
            "touch_price": str(self.touch_price),
            "label_window_end_ts": self.label_window_end_ts,
            "return_pct": self.return_pct,
            "ambiguous": self.ambiguous,
            "candles_in_window": self.candles_in_window,
        }


@dataclass(frozen=True, slots=True)
class LabelledSeries:
    """Labels for one pair, plus the counts that say how much to trust them."""

    pair: str
    labels: tuple[Label, ...]
    considered: int
    """Decision bars offered to the labeller."""

    excluded_past_end: int
    """Bars whose window ran past the end of the series. Excluded, never `timeout`."""

    excluded_empty_window: int
    """Bars whose window contained no candle at all."""

    @property
    def ambiguous_count(self) -> int:
        """How many labels were decided by ruling 1 rather than by the data."""
        return sum(1 for label in self.labels if label.ambiguous)

    def counts(self) -> dict[str, int]:
        return {name: sum(1 for x in self.labels if x.label == name) for name in BARRIER_LABELS}


def _candle(row: Mapping[str, Any] | Sequence[Any]) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    raise TypeError("a candle must be a mapping with ts, open, high, low, close")


def label_candles(
    candles: Sequence[Mapping[str, Any]],
    *,
    pair: str,
    decision_ts: int,
    config: _Config,
    interval_s: int,
    barriers: Barriers | None = None,
) -> Label | None:
    """Label one decision bar against the candle window around it.

    ``candles`` must be ascending by ``ts`` and must include the decision bar itself.
    Returns ``None`` when the bar is excluded — its window runs past the end of what was
    supplied, or the window holds no candle at all.

    This is the single-bar entry point, and it is what the hand-verified fixture and its
    phase criterion drive. :func:`label_frame` is the same walk over a whole series.
    """
    settings = barriers if barriers is not None else read_barriers(config)
    rows = [_candle(row) for row in candles]
    stamps = [int(row["ts"]) for row in rows]
    index = bisect.bisect_left(stamps, decision_ts)
    if index >= len(stamps) or stamps[index] != decision_ts:
        raise ValueError(f"{pair}: no candle at decision_ts {decision_ts}")
    return _label_at(
        pair=pair,
        rows=rows,
        stamps=stamps,
        index=index,
        settings=settings,
        interval_s=interval_s,
        last_ts=stamps[-1],
    )


def _label_at(
    *,
    pair: str,
    rows: Sequence[Mapping[str, Any]],
    stamps: Sequence[int],
    index: int,
    settings: Barriers,
    interval_s: int,
    last_ts: int,
) -> Label | None:
    decision = rows[index]
    decision_ts = int(decision["ts"])
    close = Decimal(str(decision["close"]))
    target_price = close * (Decimal(1) + settings.target_pct)
    stop_price = close * (Decimal(1) - settings.stop_pct)
    window_end = settings.timeout_at(decision_ts, interval_s)

    # Excluded, never labelled `timeout`: the outcome has not happened yet.
    if last_ts < window_end:
        return None

    # The scan starts at index + 1. The decision bar's own high and low are inside the
    # bar the decision was made on, and reading them is look-ahead within one bar.
    scan_from = index + 1
    scan_to = bisect.bisect_right(stamps, window_end)
    in_window = max(0, scan_to - scan_from)
    if in_window == 0:
        return None

    for position in range(scan_from, scan_to):
        row = rows[position]
        high = Decimal(str(row["high"]))
        low = Decimal(str(row["low"]))
        hit_target = high >= target_price
        hit_stop = low <= stop_price
        if not (hit_target or hit_stop):
            continue
        # Ruling 1. Both barriers inside one bar carries no ordering, and the
        # pessimistic reading is the only one that cannot flatter the strategy.
        ambiguous = hit_target and hit_stop
        label = LABEL_STOP if (hit_stop or ambiguous) else LABEL_TARGET
        touch_price = stop_price if label == LABEL_STOP else target_price
        touch_ts = int(row["ts"])
        return Label(
            pair=pair,
            decision_ts=decision_ts,
            close=close,
            target_price=target_price,
            stop_price=stop_price,
            label=label,
            touch_ts=touch_ts,
            # Elapsed *bars*, computed from the timestamps, so a gap inside the window
            # does not compress the horizon into however many rows happened to exist.
            bars_elapsed=(touch_ts - decision_ts) // interval_s,
            touch_price=touch_price,
            label_window_end_ts=touch_ts,
            return_pct=float((touch_price - close) / close),
            ambiguous=ambiguous,
            candles_in_window=in_window,
        )

    terminal = rows[scan_to - 1]
    terminal_ts = int(terminal["ts"])
    terminal_close = Decimal(str(terminal["close"]))
    return Label(
        pair=pair,
        decision_ts=decision_ts,
        close=close,
        target_price=target_price,
        stop_price=stop_price,
        label=LABEL_TIMEOUT,
        touch_ts=terminal_ts,
        bars_elapsed=(terminal_ts - decision_ts) // interval_s,
        touch_price=terminal_close,
        # The horizon, not the last candle. They differ whenever the window ends inside
        # a gap, and the splitter must purge on the later of the two.
        label_window_end_ts=window_end,
        return_pct=float((terminal_close - close) / close),
        ambiguous=False,
        candles_in_window=in_window,
    )


def label_series(
    candles: Sequence[Mapping[str, Any]],
    *,
    pair: str,
    config: _Config,
    interval_s: int,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> LabelledSeries:
    """Label every decision bar in ``candles``, or those inside ``[start_ts, end_ts]``.

    The bound is on which bars are *labelled*, never on which are *looked at*: a
    decision bar at the end of the requested range still walks forward into candles
    after it, which is what makes the horizon real rather than an artefact of the slice.
    """
    settings = read_barriers(config)
    rows = [_candle(row) for row in candles]
    stamps = [int(row["ts"]) for row in rows]
    if not stamps:
        return LabelledSeries(pair, (), 0, 0, 0)
    last_ts = stamps[-1]

    first = 0 if start_ts is None else bisect.bisect_left(stamps, start_ts)
    final = len(stamps) if end_ts is None else bisect.bisect_right(stamps, end_ts)

    labels: list[Label] = []
    past_end = 0
    empty = 0
    for index in range(first, final):
        window_end = settings.timeout_at(stamps[index], interval_s)
        if last_ts < window_end:
            past_end += 1
            continue
        label = _label_at(
            pair=pair,
            rows=rows,
            stamps=stamps,
            index=index,
            settings=settings,
            interval_s=interval_s,
            last_ts=last_ts,
        )
        if label is None:
            empty += 1
            continue
        labels.append(label)
    return LabelledSeries(
        pair=pair,
        labels=tuple(labels),
        considered=max(0, final - first),
        excluded_past_end=past_end,
        excluded_empty_window=empty,
    )


def label_frame(
    frame: pl.DataFrame,
    *,
    pair: str,
    config: _Config,
    interval_s: int,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> tuple[pl.DataFrame, LabelledSeries]:
    """The frame `research/historical.py` produces, labelled.

    Returns ``(labels, series)``. The frame carries :data:`LABEL_COLUMNS`; money is a
    string in it, exactly as it is everywhere else money leaves this package, because a
    parquet float column is a price that has already lost precision.
    """
    rows = frame.select(["ts", "open", "high", "low", "close"]).to_dicts()
    series = label_series(
        rows, pair=pair, config=config, interval_s=interval_s, start_ts=start_ts, end_ts=end_ts
    )
    payload = [label.as_row() for label in series.labels]
    if not payload:
        return pl.DataFrame(schema=dict.fromkeys(LABEL_COLUMNS, pl.Utf8)), series
    return pl.DataFrame(payload).select(LABEL_COLUMNS), series
