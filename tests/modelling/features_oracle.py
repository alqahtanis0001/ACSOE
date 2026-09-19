"""The feature arithmetic as it stood before engine 5 was batched: the oracle, kept in tests.

Copied verbatim from `src/acsoe/modelling/features.py` at HEAD `5ed78d6` (spec 64's per-pair
`compute`, and engine 5's per-pair loop over it), on 2026-09-19, when lead decision D16 moved both
onto one grouped implementation (`compute_many`). It is never imported by `src/`. Its one job is to
be the unchanged implementation the new one must equal **bit for bit**, float for float with every
NaN in the same place (`test_features_batched.py`). If the arithmetic is ever changed on purpose,
`FEATURE_VERSION` moves and this file is retired with it; it is not to be edited to follow.
"""

from __future__ import annotations

import math
from typing import Any

import polars as pl

from acsoe.modelling.features import (
    _RANK_SIG_FIGS,
    FEATURE_NAMES,
    LOOKBACK_BARS,
    MAX_LOOKBACK_BARS,
    REGIME_LONG_BARS,
    REGIME_SHORT_BARS,
    FeatureError,
    _require_columns,
    features_for_lookback,
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
    frame = _add_regime_rank(frame, interval_s=interval_s)

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


def _add_regime_rank(frame: pl.DataFrame, *, interval_s: int) -> pl.DataFrame:
    """Where this bar's short-window volatility sits inside the long window's own history.

    ``0.0`` means calmer than anything in the window, ``1.0`` the most volatile bar in it.
    Engine 12 `regime` compares it against ``regime.high_vol_percentile``, so the cutoff
    the operator sets is a percentile of the pair's own recent distribution rather than a
    number of percent — which is the whole of spec 66's "never absolute" rule, and it is
    enforced here by engine 12 having no distribution to compute one from.

    The rank is taken over the **raw** short-window volatilities, before the under-filled
    windows are blanked, and the rank feature is then blanked with the long window like
    any other. Ranking after blanking would rank NaNs, which sort last and would make a
    bar with no history look like the most volatile one on record.

    ``rolling_rank_by`` is marked unstable in polars and is used deliberately: computing
    an empirical percentile any other way over twenty million rows means a per-row Python
    callback. If it ever changes, `test_the_regime_rank_is_a_position_inside_its_own_window`
    is what goes red.

    **The volatilities are rounded to ten significant figures before being ranked**, and
    that line is load-bearing rather than tidy. A rank has no tolerance: it asks only
    which value is larger, so on a window whose values are all equal to thirteen decimal
    places the answer is decided by the last bit. `rolling_std_by` over a genuinely
    constant series does not return a constant — it returns values differing at a
    relative 1e-13, because a sliding variance is computed incrementally — so on a quiet,
    tightly-ranged market the rank became pure noise and a 0.9 cutoff labelled roughly one
    such bar in ten `high_volatility`, for no reason and with nothing going red. Rounding
    makes genuine ties tie exactly, and ``average`` ranking then gives them the middle
    rank, which is the honest percentile of a value in a constant distribution.

    Significant figures rather than an absolute tolerance, because realised volatility
    spans orders of magnitude across 234 pairs and only a relative measure means the same
    thing on a $0.30 pair and a $60,000 one. Real differences between bars are many orders
    of magnitude above the tenth significant figure; the observed noise is at the
    thirteenth.
    """
    span = f"{REGIME_LONG_BARS * interval_s}s"
    source = f"realised_vol_{REGIME_SHORT_BARS}"
    counter = f"bars_in_lookback_{REGIME_LONG_BARS}"
    rank = (
        pl.col(source)
        .round_sig_figs(_RANK_SIG_FIGS)
        .rolling_rank_by("_dt", window_size=span, closed="right")
    )
    # `rolling_rank_by` counts from 1, and its window holds at most as many values as
    # the candle counter reports, so the ratio lands in (0, 1].
    return frame.with_columns(
        pl.when(pl.col(counter) > 0)
        .then(rank / pl.col(counter))
        .otherwise(float("nan"))
        .alias("vol_regime_rank")
    )


_OLD_SCHEMA: dict[str, Any] = {
    "ts": pl.Int64,
    **dict.fromkeys(("open", "high", "low", "close", "volume"), pl.Float64),
    "trades": pl.Int64,
}


def old_engine_rows(
    candles: list[dict[str, Any]], *, bar_ts: int, interval_s: int, min_lookback_fill: float
) -> tuple[dict[str, dict[str, float | None]], dict[str, int], list[str]]:
    """Engine 5's per-pair loop as it was: `(rows, row_ts, pairs_with_short_history)`."""
    by_pair: dict[str, list[dict[str, Any]]] = {}
    for candle in candles:
        if int(candle["ts"]) > bar_ts:
            continue
        row: dict[str, Any] = {"ts": int(candle["ts"])}
        for field in ("open", "high", "low", "close", "volume"):
            row[field] = float(candle[field])
        row["trades"] = int(candle.get("trades") or 0)
        by_pair.setdefault(str(candle["pair"]), []).append(row)
    rows: dict[str, dict[str, float | None]] = {}
    row_ts: dict[str, int] = {}
    short: list[str] = []
    for pair in sorted(by_pair):
        frame = pl.DataFrame(by_pair[pair], schema=_OLD_SCHEMA).sort("ts")
        computed = compute(frame, interval_s=interval_s, min_lookback_fill=min_lookback_fill)
        if computed.height == 0:
            continue
        last = computed.tail(1).to_dicts()[0]
        row_ts[pair] = int(last["ts"])
        values: dict[str, float | None] = {}
        for name in FEATURE_NAMES:
            value = last.get(name)
            number = None if value is None else float(value)
            values[name] = (
                None if number is None or math.isnan(number) or math.isinf(number) else number
            )
        rows[pair] = values
        filled = values.get(f"bars_in_lookback_{MAX_LOOKBACK_BARS}")
        if filled is None or float(filled) < float(MAX_LOOKBACK_BARS):
            short.append(pair)
    return rows, row_ts, short
