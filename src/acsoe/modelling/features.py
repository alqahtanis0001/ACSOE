"""The feature vector, computed once for the live loop and for the training pipeline.

One function, two callers. Engine 5 `feature` shapes engine 3's published candles and
calls :func:`compute`; `research/training.py` shapes the historical archive and calls
the same :func:`compute`. That is the whole reason `modelling/` exists as a package
both sides may import, and `features_reproduce_in_replay` is the criterion that asks
whether the two really did get the same numbers.

Five constraints, each of which is a defect this project has already met somewhere:

**OHLCVT only.** The historical archives carry open, high, low, close, volume and trade
count and nothing else. There is no bid, no ask, no depth and no spread in them; those
exist only in the live recording, going forward, and can never be recovered for the
past. A feature reading one would be computable live and **not** computable in replay,
so every backtest number it touched would describe a model the live loop cannot
reproduce. `architecture-context.md` states it as a Phase 5 rule and
`features_reproduce_in_replay` asserts it on this module's syntax tree.

**A feature at bar `t` uses bars at or before `t`.** Closed bars only. The in-progress
bar never enters, because engine 3 never publishes it. Invariant 10, and it is the most
fatal defect in this kind of system precisely because it makes everything look better.

**A lookback is a window of time, not a count of rows.** The archive only contains
intervals in which trades occurred, so a missing candle means *no trades*, not a data
error, and nothing may interpolate one into existence. That leaves two readings of "the
last 32 bars", identical on every contiguous series and different on exactly the quiet
periods this market has most of: taking the previous 32 *rows* reaches back across a
six-hour hole into a different market, while taking the rows inside ``32 * interval_s``
*seconds* reports nine bars and says so. It is the same rule the timeout barrier is held
to in `architecture-context.md`, arriving one layer down. Every window here is
``n * interval_s`` seconds, ``bars_in_lookback_<n>`` is itself a feature, and a window
whose fill falls below ``min_lookback_fill`` yields NaN for every feature computed over
**that** window.

**No pair identity.** No feature encodes which pair a row belongs to. Every one is a
return, a ratio, a z-score, a position within the pair's own window, or a clock field.
The predictor is pooled across 234 pairs, and a pooled model that can memorise a pair
name has learned which pairs went up in the training window rather than anything that
transfers.

**Named, ordered and versioned.** :data:`FEATURE_NAMES` is an ordered tuple and
:data:`FEATURE_VERSION` is a string written into every artefact's manifest. A model
without its exact feature order is unusable — `code-standards.md` says so — and the
order is fixed here rather than anywhere a caller could re-derive it.

``float`` and ``numpy`` throughout. These are model inputs, not money.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

import polars as pl

__all__ = [
    "FEATURE_NAMES",
    "FEATURE_VERSION",
    "LOOKBACK_BARS",
    "MARKET_QUALITY_FEATURES",
    "MAX_LOOKBACK_BARS",
    "OHLCVT_COLUMNS",
    "FeatureError",
    "compute",
    "features_for_lookback",
    "lookback_of",
]


class FeatureError(ValueError):
    """A frame this module cannot compute features from, said plainly.

    Raised rather than worked around. A caller handing in a frame with no ``high``
    column has a bug, and returning a frame of NaNs would let that bug reach a training
    run as a model that simply performs badly.
    """


#: The columns :func:`compute` reads, and the only columns it may ever read. Engine 3
#: publishes all seven and `research/historical.py` parses all seven out of the archive.
OHLCVT_COLUMNS: Final[tuple[str, ...]] = (
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trades",
)

#: The lookback windows, in bars, at a 15-minute decision bar: one hour, four hours,
#: twelve hours and one day.
#:
#: Twelve hours is the holding horizon and one day is the longest window that still
#: leaves room inside `market_sensor.published_bars` (200) for the live path to fill it.
#: That ceiling is not decorative: engine 3 publishes the smaller number of bars, so a
#: lookback longer than it could never be filled live and the live and offline paths
#: would differ on every bar — by design, silently, with the offline number being the
#: one that looks right. `features.max_lookback_bars` is the configured bound and
#: spec 61's validator refuses a value above `market_sensor.published_bars`.
LOOKBACK_BARS: Final[tuple[int, ...]] = (4, 16, 48, 96)

#: The longest window any feature reads, in bars. Asserted against
#: `features.max_lookback_bars` by the caller that has the config; this module takes no
#: config, so it publishes the number and lets the engine and the trainer check it.
MAX_LOOKBACK_BARS: Final[int] = max(LOOKBACK_BARS)

#: Bumped whenever a name, an order or an arithmetic changes. It is written into every
#: manifest and engine 8 refuses an artefact whose version is not the one it computes,
#: because a model fed the same feature names computed a different way is a model being
#: given inputs it has never seen with nothing saying so.
FEATURE_VERSION: Final[str] = "f1"


#: The per-lookback feature stems, in the order they appear for each window.
_LOOKBACK_STEMS: Final[tuple[str, ...]] = (
    "bars_in_lookback",
    "log_return",
    "realised_vol",
    "efficiency_ratio",
    "range_atr",
    "volume_z",
    "trades_z",
    "high_low_position",
)

#: Features that describe the bar itself or the clock, and therefore have no lookback
#: and never go NaN for want of history.
_BAR_FEATURES: Final[tuple[str, ...]] = (
    "bar_range_pct",
    "bar_body_pct",
)
_CLOCK_FEATURES: Final[tuple[str, ...]] = (
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
)


def _build_names() -> tuple[str, ...]:
    names: list[str] = [*_BAR_FEATURES, *_CLOCK_FEATURES]
    for bars in LOOKBACK_BARS:
        names.extend(f"{stem}_{bars}" for stem in _LOOKBACK_STEMS)
    return tuple(names)


#: The ordered feature list. Order is part of the contract: a model without its exact
#: feature order is unusable, so this tuple is what goes into a manifest and what an
#: engine checks a loaded artefact against, element by element.
FEATURE_NAMES: Final[tuple[str, ...]] = _build_names()


#: The subset engine 13 `anomaly` is fitted on: velocity, volume, trade count, range and
#: window fill. Market-data quality, never anything about whether the trade is good —
#: invariant 4 protects `anomaly` as a data-quality gate precisely because it judges the
#: market and not the candidate.
#:
#: **No spread, and its absence is declared rather than implied.** `trading-invariants.md`
#: describes anomaly's inputs as velocity, volume and spread. The archive carries no
#: spread, so the detector is fitted without one; spec 70 writes that into the artefact's
#: manifest and into engine 13's README. If a spread input is wanted later, that is a
#: stop and a question, not a reach for the recorder.
MARKET_QUALITY_FEATURES: Final[tuple[str, ...]] = (
    "bar_range_pct",
    *(
        f"{stem}_{bars}"
        for bars in LOOKBACK_BARS
        for stem in ("bars_in_lookback", "realised_vol", "range_atr", "volume_z", "trades_z")
    ),
)


def features_for_lookback(bars: int) -> tuple[str, ...]:
    """Every feature computed over the ``bars``-bar window, that window's counter first.

    Exposed so nothing downstream has to parse a name. When a window's fill falls below
    ``min_lookback_fill`` these are the columns that go NaN — and only these: a bar's own
    range and the hour of the day are known whatever the history behind them looks like,
    and blanking them too would throw away the rows a short-history pair *can* be judged
    on.
    """
    if bars not in LOOKBACK_BARS:
        raise FeatureError(f"{bars} is not one of the lookbacks {LOOKBACK_BARS}")
    return tuple(f"{stem}_{bars}" for stem in _LOOKBACK_STEMS)


def lookback_of(name: str) -> int | None:
    """The lookback a feature belongs to, or ``None`` for a bar or clock feature."""
    for bars in LOOKBACK_BARS:
        if name.endswith(f"_{bars}") and name in features_for_lookback(bars):
            return bars
    return None


def _require_columns(candles: pl.DataFrame) -> None:
    absent = [name for name in OHLCVT_COLUMNS if name not in candles.columns]
    if absent:
        raise FeatureError(
            "candles are missing " + ", ".join(absent) + "; compute() reads exactly "
            + ", ".join(OHLCVT_COLUMNS)
        )
    floats = ("open", "high", "low", "close", "volume")
    wrong = [
        name
        for name in floats
        if candles.schema[name] not in (pl.Float64, pl.Float32)
    ]
    if wrong:
        raise FeatureError(
            "expected Float64 for " + ", ".join(wrong) + ", got "
            + ", ".join(f"{name}={candles.schema[name]}" for name in wrong)
            + ". Money is cast to float once, in the caller: engine 5 from the decimal "
            "strings engine 3 publishes and the offline builder from the archive's "
            "Decimal columns. Casting here instead would let the two callers arrive "
            "with different precision and the two paths would stop agreeing."
        )


def compute(
    candles: pl.DataFrame,
    *,
    interval_s: int,
    min_lookback_fill: float,
) -> pl.DataFrame:
    """Features for every closed bar in ``candles``, one row per bar, keyed by ``ts``.

    :param candles: one pair's closed candles, columns :data:`OHLCVT_COLUMNS`, money
        already cast to ``Float64``. Sorted by ``ts`` on the way in; duplicates are a
        caller's bug and raise.
    :param interval_s: the decision-bar grid, ``timeframes.decision_bar_s``. Every
        lookback window is ``n * interval_s`` seconds wide.
    :param min_lookback_fill: ``features.min_lookback_fill``. A window holding a smaller
        fraction of its bars than this yields NaN for every feature over that window.

    The frame that comes back carries ``ts`` and one ``Float64`` column per
    :data:`FEATURE_NAMES`, in that order. NaN means "not computable from what was
    there", never zero: a zero is a value a model will happily learn from, and the
    absence of history is not a quiet market.

    **Nothing is interpolated, forward-filled or resampled**, and there is no parameter
    that asks for it. A hole in the archive is a period with no trades; inventing a bar
    there fabricates the one thing the data is honest about.
    """
    if interval_s <= 0:
        raise FeatureError("interval_s must be positive")
    if not 0.0 < min_lookback_fill <= 1.0:
        raise FeatureError("min_lookback_fill must be in (0, 1]")
    _require_columns(candles)

    if candles.height == 0:
        return pl.DataFrame(
            schema={"ts": pl.Int64, **dict.fromkeys(FEATURE_NAMES, pl.Float64)}
        )

    frame = candles.sort("ts")
    stamps = frame["ts"]
    if stamps.n_unique() != frame.height:
        raise FeatureError(
            "candles carry duplicate timestamps; one bar per decision slot, and a "
            "duplicate would be counted twice inside every window that covers it"
        )

    frame = frame.with_columns(
        pl.from_epoch("ts", time_unit="s").alias("_dt"),
        pl.lit(1, dtype=pl.Int64).alias("_one"),
        # The log return **of this bar**: from the previous *existing* bar's close.
        # Across a hole this is a single jump rather than a series of small steps, which
        # is the truth about what the price did while nobody traded, and the window that
        # contains it will usually be under-filled and blanked anyway.
        (pl.col("close").log() - pl.col("close").log().shift(1)).alias("_r"),
    ).with_columns(
        pl.col("_r").abs().alias("_abs_r"),
        ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("bar_range_pct"),
        ((pl.col("close") - pl.col("open")) / pl.col("open")).alias("bar_body_pct"),
    )

    # Clock fields, from `ts` alone. Encoded as sine/cosine pairs so that 23:45 and
    # 00:00 sit next to each other, which they do; a raw hour number puts them at
    # opposite ends of the range and asks a tree to learn the wrap-around from data.
    seconds_of_day = pl.col("ts") % 86_400
    weekday = ((pl.col("ts") // 86_400) + 4) % 7  # 1970-01-01 was a Thursday
    frame = frame.with_columns(
        (seconds_of_day / 86_400 * (2 * math.pi)).sin().alias("hour_sin"),
        (seconds_of_day / 86_400 * (2 * math.pi)).cos().alias("hour_cos"),
        (weekday / 7 * (2 * math.pi)).sin().alias("weekday_sin"),
        (weekday / 7 * (2 * math.pi)).cos().alias("weekday_cos"),
    )

    for bars in LOOKBACK_BARS:
        frame = _add_lookback(frame, bars=bars, interval_s=interval_s)

    # Blank each window that is too empty to mean anything, and blank only that window.
    for bars in LOOKBACK_BARS:
        counter = f"bars_in_lookback_{bars}"
        enough = pl.col(counter) >= (min_lookback_fill * bars)
        blanked = [name for name in features_for_lookback(bars) if name != counter]
        frame = frame.with_columns(
            [
                pl.when(enough)
                .then(pl.col(name))
                .otherwise(float("nan"))
                .alias(name)
                for name in blanked
            ]
        )

    return frame.select(
        ["ts", *[pl.col(name).cast(pl.Float64).alias(name) for name in FEATURE_NAMES]]
    )


def _add_lookback(frame: pl.DataFrame, *, bars: int, interval_s: int) -> pl.DataFrame:
    """One window's eight features.

    ``closed="right"`` makes the window ``(t - bars * interval_s, t]``, which holds
    exactly ``bars`` candles on a contiguous series — the bar at ``t`` and the
    ``bars - 1`` before it — and fewer across a hole. That is the whole mechanism: the
    window is defined in seconds and the count of what fell inside it is reported.
    """
    span = f"{bars * interval_s}s"
    net = pl.col("_r").rolling_sum_by("_dt", window_size=span, closed="right")
    path = pl.col("_abs_r").rolling_sum_by("_dt", window_size=span, closed="right")
    lowest = pl.col("low").rolling_min_by("_dt", window_size=span, closed="right")
    highest = pl.col("high").rolling_max_by("_dt", window_size=span, closed="right")
    volume_mean = pl.col("volume").rolling_mean_by("_dt", window_size=span, closed="right")
    volume_std = pl.col("volume").rolling_std_by(
        "_dt", window_size=span, closed="right", min_samples=2
    )
    trades_mean = pl.col("trades").cast(pl.Float64).rolling_mean_by(
        "_dt", window_size=span, closed="right"
    )
    trades_std = pl.col("trades").cast(pl.Float64).rolling_std_by(
        "_dt", window_size=span, closed="right", min_samples=2
    )

    return frame.with_columns(
        pl.col("_one")
        .rolling_sum_by("_dt", window_size=span, closed="right")
        .cast(pl.Float64)
        .alias(f"bars_in_lookback_{bars}"),
        net.alias(f"log_return_{bars}"),
        pl.col("_r")
        .rolling_std_by("_dt", window_size=span, closed="right", min_samples=2)
        .alias(f"realised_vol_{bars}"),
        # Net move over path length: 1.0 is a straight line, 0.0 is a round trip that
        # went nowhere. It is the trend/chop measure engine 12 `regime` reads, and it is
        # scale-free, so it means the same thing on a $0.30 pair and a $60,000 one.
        pl.when(path > 0)
        .then(net.abs() / path)
        .otherwise(float("nan"))
        .alias(f"efficiency_ratio_{bars}"),
        ((pl.col("high") - pl.col("low")) / pl.col("close"))
        .rolling_mean_by("_dt", window_size=span, closed="right")
        .alias(f"range_atr_{bars}"),
        pl.when(volume_std > 0)
        .then((pl.col("volume") - volume_mean) / volume_std)
        .otherwise(float("nan"))
        .alias(f"volume_z_{bars}"),
        pl.when(trades_std > 0)
        .then((pl.col("trades").cast(pl.Float64) - trades_mean) / trades_std)
        .otherwise(float("nan"))
        .alias(f"trades_z_{bars}"),
        pl.when(highest > lowest)
        .then((pl.col("close") - lowest) / (highest - lowest))
        .otherwise(float("nan"))
        .alias(f"high_low_position_{bars}"),
    )


def feature_matrix(frame: pl.DataFrame, names: Sequence[str]) -> list[list[float]]:
    """``frame``'s feature columns as plain rows, in ``names`` order.

    A small helper rather than a caller's list comprehension, because the order is the
    part that goes wrong: a model fed its features in a permuted order produces
    confident nonsense and nothing raises.
    """
    absent = [name for name in names if name not in frame.columns]
    if absent:
        raise FeatureError("frame is missing " + ", ".join(absent))
    columns = [frame[name].cast(pl.Float64).to_list() for name in names]
    return [[float(column[row]) for column in columns] for row in range(frame.height)]
