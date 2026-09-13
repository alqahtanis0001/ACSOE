"""Engine 5 `feature` — the first engine of the opportunity chain, and its cadence.

**It shapes inputs and publishes outputs. It computes nothing.** Every number it emits
comes from `modelling.features.compute`, which `research/training.py` also calls, and
that is the entire point: the live loop and the training pipeline may not import each
other (architecture invariant 5), so the only way a backtest can describe the system
that actually trades is for both to run the same function over differently-shaped
inputs. `features_reproduce_in_replay` is the criterion that asks whether they agree.

**It is what stops the opportunity chain on fourteen ticks out of fifteen.** The loop
ticks every minute and a candidate is only born when a 15-minute bar closes. Engine 3
`market_sensor` owns that clock and publishes `bar_closed`; this engine returns `PASS`
when it is false and the chain stops here. No other engine may infer the bar boundary
for itself, and the orchestrator does not know about bars at all — cadence is a property
of the candle stream, not of `core/`.

**It is not a gate and it never blocks.** A pair with too little history is *reported*,
with null features and its name in `pairs_with_short_history`; a pair that did not trade
in the decision bar gets the row of its most recent closed bar and a `row_ts` saying so.
Refusing is engine 7's business and engine 13's. Engine 5 dropping a pair would make it
invisible to the gate that is supposed to consider it, which is a silent narrowing of
the universe that nothing downstream could detect.

**Money becomes float here, and only here, on the live path.** Engine 3 publishes candles
with money as exact decimal strings (contract rule 8). Features are model inputs rather
than money, so the conversion happens once, at this boundary — the same single conversion
the offline builder makes from the archive's `Decimal` columns, which is what lets the
two paths be compared for exact equality rather than for closeness.

It reads no clock, constructs no client, imports no other engine, caches nothing across
ticks, and writes exactly one `state` key.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

import polars as pl

from acsoe.core.contracts import (
    BaseEngine,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.engines.feature.contracts import (
    BAR_CLOSED_FIELD,
    CANDLE_MONEY_FIELDS,
    CANDLE_PAIR_FIELD,
    CANDLE_TRADES_FIELD,
    CANDLE_TS_FIELD,
    CANDLES_FIELD,
    CLOSED_BAR_TS_FIELD,
    INTERVAL_FIELD,
    KEY_MAX_LOOKBACK_BARS,
    KEY_MIN_LOOKBACK_FILL,
    MARKET_SENSOR_KEY,
    STATE_KEY,
    FeatureState,
    MissingInputError,
)
from acsoe.modelling.features import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    MAX_LOOKBACK_BARS,
    compute,
)

_CANDLE_SCHEMA: dict[str, Any] = {
    CANDLE_TS_FIELD: pl.Int64,
    **dict.fromkeys(CANDLE_MONEY_FIELDS, pl.Float64),
    CANDLE_TRADES_FIELD: pl.Int64,
}


class FeatureEngine(BaseEngine):
    """Engine 5. Opportunity chain, first. Not a gate."""

    name: ClassVar[str] = STATE_KEY
    number: ClassVar[int] = 5
    is_gate: ClassVar[bool] = False

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        sensor = state.get(MARKET_SENSOR_KEY) or {}
        if not sensor.get(BAR_CLOSED_FIELD):
            # Fourteen ticks out of fifteen end here. PASS, not BLOCK: nothing is wrong,
            # there is simply no new candidate, and the orchestrator stops the chain on
            # a PASS without recording a blocker.
            return EngineResult(
                engine=self.name,
                status=EngineStatus.PASS,
                data={},
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        bar_ts = sensor.get(CLOSED_BAR_TS_FIELD)
        if bar_ts is None:
            raise MissingInputError(
                f"state[{MARKET_SENSOR_KEY!r}][{BAR_CLOSED_FIELD!r}] is true and "
                f"{CLOSED_BAR_TS_FIELD!r} is absent. Engine 3 owns the decision-bar "
                "clock and publishes both together; a bar that closed without a "
                "timestamp is a shape it cannot produce, and guessing which bar it was "
                "would date every feature row in this tick to a bar nobody chose."
            )
        interval_s = sensor.get(INTERVAL_FIELD)
        if not interval_s:
            raise MissingInputError(
                f"state[{MARKET_SENSOR_KEY!r}][{INTERVAL_FIELD!r}] is absent. It is the "
                "grid engine 3 built the candles on and every lookback window is a "
                "multiple of it."
            )

        # No defaults. `Config.get` raises on an absent key, the orchestrator turns that
        # into ERROR, and ERROR blocks — the honest answer for a threshold nobody set.
        min_fill = float(context.config.get(KEY_MIN_LOOKBACK_FILL))
        max_lookback = int(context.config.get(KEY_MAX_LOOKBACK_BARS))
        if max_lookback < MAX_LOOKBACK_BARS:
            raise MissingInputError(
                f"modelling.features.MAX_LOOKBACK_BARS is {MAX_LOOKBACK_BARS} and "
                f"`{KEY_MAX_LOOKBACK_BARS}` is {max_lookback}. The longest window must "
                "fit inside what engine 3 publishes, or the live path can never fill it "
                "while the offline builder fills it every time — the two paths then "
                "differ on every bar, silently, with the offline number looking right."
            )

        by_pair = self._group(sensor.get(CANDLES_FIELD) or (), bar_ts=int(bar_ts))

        rows: dict[str, dict[str, float | None]] = {}
        row_ts: dict[str, int] = {}
        short: list[str] = []
        gaps: dict[str, int] = {}

        for pair in sorted(by_pair):
            candles = by_pair[pair]
            frame = pl.DataFrame(candles, schema=_CANDLE_SCHEMA).sort(CANDLE_TS_FIELD)
            gaps[pair] = _gaps_in_range(
                [int(ts) for ts in frame[CANDLE_TS_FIELD]], interval_s=int(interval_s)
            )
            computed = compute(
                frame, interval_s=int(interval_s), min_lookback_fill=min_fill
            )
            if computed.height == 0:
                continue
            last = computed.tail(1).to_dicts()[0]
            row_ts[pair] = int(last[CANDLE_TS_FIELD])
            row = {name: _jsonable(last.get(name)) for name in FEATURE_NAMES}
            rows[pair] = row
            if _covers_less_than_the_longest_window(row):
                short.append(pair)

        payload = FeatureState(
            bar_ts=int(bar_ts),
            interval_s=int(interval_s),
            feature_version=FEATURE_VERSION,
            feature_names=FEATURE_NAMES,
            pairs=rows,
            row_ts=row_ts,
            pairs_with_short_history=tuple(short),
            gaps_in_range=gaps,
        )
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            data=payload.to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    @staticmethod
    def _group(
        candles: Sequence[Mapping[str, Any]], *, bar_ts: int
    ) -> dict[str, list[dict[str, Any]]]:
        """Candles by pair, money cast to float, nothing later than the closed bar.

        The ``ts <= bar_ts`` filter is belt and braces and is deliberately not trusted
        away: engine 3 does not publish the in-progress bar, so in a correct system this
        removes nothing. It is here because if that ever changed, every feature in the
        phase would quietly start reading a partial bar — a look-ahead defect that makes
        a backtest *better*, which is the direction nothing downstream questions.
        """
        grouped: dict[str, list[dict[str, Any]]] = {}
        for candle in candles:
            pair = candle.get(CANDLE_PAIR_FIELD)
            ts = candle.get(CANDLE_TS_FIELD)
            if pair is None or ts is None:
                raise MissingInputError(
                    "a candle in state[market_sensor][candles] carries no "
                    f"{CANDLE_PAIR_FIELD!r} or no {CANDLE_TS_FIELD!r}: {candle!r}"
                )
            if int(ts) > bar_ts:
                continue
            row: dict[str, Any] = {CANDLE_TS_FIELD: int(ts)}
            for field in CANDLE_MONEY_FIELDS:
                value = candle.get(field)
                if value is None:
                    raise MissingInputError(
                        f"a candle for {pair} at {ts} carries no {field!r}"
                    )
                # The one conversion. `float("20.24")` and `float(Decimal("20.24"))` are
                # the same double, which is what makes the live and offline paths
                # comparable for exact equality.
                row[field] = float(value)
            row[CANDLE_TRADES_FIELD] = int(candle.get(CANDLE_TRADES_FIELD) or 0)
            grouped.setdefault(str(pair), []).append(row)
        return grouped


def _jsonable(value: Any) -> float | None:
    """A feature value as it crosses ``state``: a float, or `null` for NaN.

    Contract rule 8 requires `data` to be JSON-serialisable and a float NaN is not — it
    survives `json.dumps` only as the non-standard `NaN` token, which some readers
    accept and some reject. `null` is the honest spelling of "not computable from the
    bars that were there", and it is never a zero: a zero is a value a model will
    happily learn from.
    """
    if value is None:
        return None
    number = float(value)
    return None if math.isnan(number) or math.isinf(number) else number


def _covers_less_than_the_longest_window(row: Mapping[str, float | None]) -> bool:
    """Whether this pair's history fails to fill the longest lookback.

    Read off the published row rather than recounted, so that the list and the nulls can
    never disagree: the counter for the longest window is itself a feature, and it is the
    same number the blanking rule inside `modelling.features` used.
    """
    counter = f"bars_in_lookback_{MAX_LOOKBACK_BARS}"
    filled = row.get(counter)
    return filled is None or float(filled) < float(MAX_LOOKBACK_BARS)


def _gaps_in_range(stamps: Sequence[int], *, interval_s: int) -> int:
    """Bar slots inside this pair's own covered range that hold no candle.

    Bounded by the first and last candle present, the same rule engine 3's
    `missing_bar_timestamps` uses: a bar before the data starts or after it ends is not
    missing, it is outside the range.

    Counted here per pair rather than read through from engine 3's `missing_bars`,
    which pools every pair's timestamps before looking for holes — so a slot is only
    absent from that union when no pair anywhere traded in it, and on a multi-pair tick
    it reports nearly nothing and reports it identically for every pair.
    """
    if len(stamps) < 2 or interval_s <= 0:
        return 0
    present = set(stamps)
    first, last = min(present), max(present)
    return sum(
        1 for ts in range(first, last + interval_s, interval_s) if ts not in present
    )
