"""Engine 5's batched feature path equals the per-pair path it replaced, bit for bit.

Lead decision D16, 2026-09-19: engine 5 cost ~1.8 s a bar tick at 190 pairs, almost all of it
per-pair polars overhead, so `modelling.features.compute` moved onto one grouped implementation
(`compute_many`) and engine 5 calls it once a tick. **It must not change a single output value.**
The unchanged implementation is kept in `tests/modelling/features_oracle.py`, never in `src/`, and
every comparison here is on the bits of each float, with NaN positions compared as positions:
`==` would call two NaNs different and `pytest.approx` would forgive a last-bit drift, and the
last bit is exactly what an incremental rolling sum can change (see `_add_regime_rank`).
"""

from __future__ import annotations

import math
import random
import struct
from typing import Any

import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from acsoe.engines.feature.engine import FeatureEngine
from acsoe.modelling import features
from tests.modelling import features_oracle as oracle

INTERVAL = 900
SCHEMA = {
    "ts": pl.Int64, "open": pl.Float64, "high": pl.Float64, "low": pl.Float64,
    "close": pl.Float64, "volume": pl.Float64, "trades": pl.Int64,
}


def bits(value: Any) -> bytes | None:
    """A float's exact bytes, one canonical NaN, and `None` kept as `None`."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.encode("utf-8")
    number = float(value)
    if math.isnan(number):
        return b"nan"
    return struct.pack("<d", number)


def assert_frames_identical(expected: pl.DataFrame, got: pl.DataFrame, where: str) -> None:
    assert expected.columns == got.columns, where
    assert expected.height == got.height, where
    for column in expected.columns:
        want = [bits(v) for v in expected[column].to_list()]
        have = [bits(v) for v in got[column].to_list()]
        if want != have:
            index = next(i for i, (a, b) in enumerate(zip(want, have, strict=True)) if a != b)
            raise AssertionError(
                f"{where}: {column} row {index}: {expected[column][index]!r} != "
                f"{got[column][index]!r}"
            )


def synthetic_candles(pairs: int, bars: int, seed: int, end: int = 1_729_382_400) -> list[dict[str, Any]]:
    """Pairs of every shape a tick holds: dense, holed, nearly empty, a single bar, and a
    constant price (the case whose rolling variance is decided by the last bit)."""
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for p in range(pairs):
        price = 10 ** rng.uniform(-2, 4.7)
        density = rng.choice([1.0, 0.95, 0.6, 0.25, 0.05])
        constant = rng.random() < 0.08
        n = bars if rng.random() > 0.1 else rng.randint(1, 60)
        for k in range(n):
            if rng.random() > density and k != n - 1:
                continue
            ts = end - (n - 1 - k) * INTERVAL
            if not constant:
                price *= math.exp(rng.gauss(0, 0.01))
            wiggle = 0.0 if constant else 1.0
            open_ = price * (1 + wiggle * rng.gauss(0, 0.002))
            high = max(open_, price) * (1 + wiggle * abs(rng.gauss(0, 0.003)))
            low = min(open_, price) * (1 - wiggle * abs(rng.gauss(0, 0.003)))
            rows.append(
                {
                    "pair": f"P{p:03d}/USD", "ts": ts, "open": open_, "high": high,
                    "low": low, "close": price,
                    "volume": 0.0 if constant else rng.expovariate(1.0),
                    "trades": 1 if constant else rng.randint(1, 200),
                }
            )
    rng.shuffle(rows)
    return rows


def per_pair(rows: list[dict[str, Any]]) -> dict[str, pl.DataFrame]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["pair"], []).append({k: v for k, v in row.items() if k != "pair"})
    return {pair: pl.DataFrame(items, schema=SCHEMA) for pair, items in grouped.items()}


# --------------------------------------------------------------------------- #
# compute and compute_many against the oracle
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("fill", [0.5, 1.0, 0.01])
def test_compute_equals_the_oracle_on_every_row_of_every_pair(seed: int, fill: float) -> None:
    for pair, frame in per_pair(synthetic_candles(40, 220, seed)).items():
        assert_frames_identical(
            oracle.compute(frame, interval_s=INTERVAL, min_lookback_fill=fill),
            features.compute(frame, interval_s=INTERVAL, min_lookback_fill=fill),
            f"{pair} seed {seed} fill {fill}",
        )


@pytest.mark.parametrize("seed", range(4))
def test_compute_many_equals_the_oracle_pair_by_pair(seed: int) -> None:
    rows = synthetic_candles(60, 220, seed)
    batched = features.compute_many(
        pl.DataFrame(rows, schema={"pair": pl.Utf8, **SCHEMA}),
        interval_s=INTERVAL, min_lookback_fill=0.5,
    )
    assert batched.columns == ["pair", "ts", *features.FEATURE_NAMES]
    frames = per_pair(rows)
    assert batched["pair"].unique().sort().to_list() == sorted(frames)
    for pair, frame in frames.items():
        assert_frames_identical(
            oracle.compute(frame, interval_s=INTERVAL, min_lookback_fill=0.5),
            batched.filter(pl.col("pair") == pair).drop("pair"),
            f"{pair} seed {seed}",
        )


candle = st.fixed_dictionaries(
    {
        "gap": st.integers(min_value=1, max_value=12),
        "close": st.floats(min_value=1e-4, max_value=1e5, allow_nan=False),
        "up": st.floats(min_value=0.0, max_value=0.05, allow_nan=False),
        "down": st.floats(min_value=0.0, max_value=0.05, allow_nan=False),
        "body": st.floats(min_value=-0.02, max_value=0.02, allow_nan=False),
        "volume": st.floats(min_value=0.0, max_value=1e6, allow_nan=False),
        "trades": st.integers(min_value=0, max_value=1000),
    }
)


@settings(max_examples=200, deadline=None)
@given(
    series=st.lists(st.lists(candle, min_size=1, max_size=130), min_size=1, max_size=4),
    fill=st.sampled_from([0.01, 0.5, 0.75, 1.0]),
)
def test_the_batched_path_equals_the_oracle_on_arbitrary_series(
    series: list[list[dict[str, Any]]], fill: float
) -> None:
    rows: list[dict[str, Any]] = []
    for index, bars in enumerate(series):
        ts = 1_700_000_100 // INTERVAL * INTERVAL
        for bar in bars:
            ts += bar["gap"] * INTERVAL
            close = bar["close"]
            open_ = close * (1 + bar["body"])
            rows.append(
                {
                    "pair": f"H{index}", "ts": ts, "open": open_,
                    "high": max(open_, close) * (1 + bar["up"]),
                    "low": min(open_, close) * (1 - bar["down"]),
                    "close": close, "volume": bar["volume"], "trades": bar["trades"],
                }
            )
    batched = features.compute_many(
        pl.DataFrame(rows, schema={"pair": pl.Utf8, **SCHEMA}),
        interval_s=INTERVAL, min_lookback_fill=fill,
    )
    for pair, frame in per_pair(rows).items():
        expected = oracle.compute(frame, interval_s=INTERVAL, min_lookback_fill=fill)
        assert_frames_identical(
            expected, features.compute(frame, interval_s=INTERVAL, min_lookback_fill=fill), pair
        )
        assert_frames_identical(expected, batched.filter(pl.col("pair") == pair).drop("pair"), pair)


def test_a_pair_with_a_single_bar_equals_that_pair_computed_alone() -> None:
    """Hypothesis found this one: polars' `sin` over a one-row series takes a scalar path
    that can differ in the last bit from the vectorised kernel a batched row meets."""
    ts0 = 1_700_000_100 // INTERVAL * INTERVAL
    bar = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0.0, "trades": 0}
    rows = [
        {"pair": "H0", "ts": ts0 + INTERVAL, **bar},
        {"pair": "H0", "ts": ts0 + 2 * INTERVAL, **bar},
        {"pair": "H1", "ts": ts0 + 3 * INTERVAL, **bar},
    ]
    batched = features.compute_many(
        pl.DataFrame(rows, schema={"pair": pl.Utf8, **SCHEMA}), interval_s=INTERVAL,
        min_lookback_fill=0.01,
    )
    for pair, frame in per_pair(rows).items():
        assert_frames_identical(
            oracle.compute(frame, interval_s=INTERVAL, min_lookback_fill=0.01),
            batched.filter(pl.col("pair") == pair).drop("pair"),
            pair,
        )


def test_a_window_never_reaches_into_another_pairs_rows() -> None:
    """Two pairs on the same bars: each is computed as if the other did not exist."""
    rows = synthetic_candles(2, 120, 3)
    alone = {
        pair: features.compute_many(
            pl.DataFrame([r for r in rows if r["pair"] == pair], schema={"pair": pl.Utf8, **SCHEMA}),
            interval_s=INTERVAL, min_lookback_fill=0.5,
        )
        for pair in {r["pair"] for r in rows}
    }
    together = features.compute_many(
        pl.DataFrame(rows, schema={"pair": pl.Utf8, **SCHEMA}),
        interval_s=INTERVAL, min_lookback_fill=0.5,
    )
    for pair, frame in alone.items():
        assert_frames_identical(frame, together.filter(pl.col("pair") == pair), pair)


def test_a_duplicate_bar_within_one_pair_is_refused_and_across_pairs_is_not() -> None:
    base = {"ts": 1_700_000_100, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
            "volume": 1.0, "trades": 1}
    schema = {"pair": pl.Utf8, **SCHEMA}
    across = pl.DataFrame([{"pair": "A", **base}, {"pair": "B", **base}], schema=schema)
    assert features.compute_many(across, interval_s=INTERVAL, min_lookback_fill=0.5).height == 2
    within = pl.DataFrame([{"pair": "A", **base}, {"pair": "A", **base}], schema=schema)
    with pytest.raises(features.FeatureError, match="duplicate timestamp within one pair"):
        features.compute_many(within, interval_s=INTERVAL, min_lookback_fill=0.5)
    with pytest.raises(features.FeatureError, match="duplicate timestamps"):
        features.compute(within.drop("pair"), interval_s=INTERVAL, min_lookback_fill=0.5)


def test_compute_many_without_its_key_and_when_empty() -> None:
    with pytest.raises(features.FeatureError, match="no 'pair' column"):
        features.compute_many(
            pl.DataFrame(schema=SCHEMA), interval_s=INTERVAL, min_lookback_fill=0.5
        )
    empty = features.compute_many(
        pl.DataFrame(schema={"pair": pl.Utf8, **SCHEMA}), interval_s=INTERVAL,
        min_lookback_fill=0.5,
    )
    assert empty.height == 0
    assert empty.columns == ["pair", "ts", *features.FEATURE_NAMES]


# --------------------------------------------------------------------------- #
# Engine 5 against its own old per-pair loop
# --------------------------------------------------------------------------- #


def sensor_candles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """As engine 3 publishes them: money as decimal strings."""
    return [
        {**row, **{f: repr(row[f]) for f in ("open", "high", "low", "close", "volume")}}
        for row in rows
    ]


@pytest.mark.parametrize("seed", range(3))
def test_engine_5_publishes_exactly_what_the_per_pair_loop_published(
    engine_context: Any, seed: int
) -> None:
    rows = synthetic_candles(190, 200, 100 + seed)
    bar_ts = max(r["ts"] for r in rows)
    # One later candle for one pair: the look-ahead filter must drop it on both paths.
    rows.append({**rows[0], "ts": bar_ts + INTERVAL})
    candles = sensor_candles(rows)
    fill = float(engine_context.config.get("features.min_lookback_fill"))
    want_rows, want_ts, want_short = oracle.old_engine_rows(
        candles, bar_ts=bar_ts, interval_s=INTERVAL, min_lookback_fill=fill
    )
    result = FeatureEngine().process(
        engine_context,
        {"market_sensor": {"bar_closed": True, "closed_bar_ts": bar_ts, "interval_s": INTERVAL,
                           "candles": candles}},
    )
    data = result.data
    assert list(data["pairs"]) == list(want_rows)
    for pair, row in want_rows.items():
        got = data["pairs"][pair]
        assert list(got) == list(row), pair
        assert [bits(v) for v in got.values()] == [bits(v) for v in row.values()], pair
    assert data["row_ts"] == want_ts
    assert list(data["pairs_with_short_history"]) == want_short


def test_compute_many_returns_rows_by_pair_then_time() -> None:
    """The order its docstring promises, which a caller taking the last row may rely on."""
    rows = synthetic_candles(30, 120, 5)
    batched = features.compute_many(
        pl.DataFrame(rows, schema={"pair": pl.Utf8, **SCHEMA}), interval_s=INTERVAL,
        min_lookback_fill=0.5,
    )
    keys = list(zip(batched["pair"].to_list(), batched["ts"].to_list(), strict=True))
    assert keys == sorted(keys)


def test_a_candle_missing_a_money_field_is_refused_by_name(engine_context: Any) -> None:
    from acsoe.engines.feature.contracts import MissingInputError

    candles = sensor_candles(synthetic_candles(3, 20, 9))
    bar_ts = max(c["ts"] for c in candles)
    broken = next(c for c in candles if c["ts"] <= bar_ts)
    del broken["close"]
    with pytest.raises(MissingInputError, match=r"carries no 'close'"):
        FeatureEngine().process(
            engine_context,
            {"market_sensor": {"bar_closed": True, "closed_bar_ts": bar_ts,
                               "interval_s": INTERVAL, "candles": candles}},
        )
