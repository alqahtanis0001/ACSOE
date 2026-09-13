"""`modelling/features.py` — the arithmetic engine 5 and the trainer share.

Three of spec 63's five named mutations are answered here, and each is answered by a
test that goes red on its own rather than by a mutation run alone:

* **a lookback counted in rows** — :func:`test_a_hole_shortens_the_window_rather_than_stretching_it`
  builds a hole and asserts the counter reports what is inside the *seconds*, not what
  is inside the previous *n rows*;
* **the in-progress bar included** and **a feature reading `close` of bar `t+1`** — both
  are look-ahead, and :func:`test_a_feature_at_bar_t_is_unchanged_by_bars_after_t`
  catches either by computing the same bar twice, once over a frame that ends there and
  once over a frame that continues.

The look-ahead test is the one worth reading twice. It needs no mutation to justify it
and it fails for the right reason: any feature that touches a later bar changes when
later bars appear, and no feature that respects invariant 10 can.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from tests.conftest import require_module

pl = require_module("polars", reason="polars is not installed")
features = require_module(
    "acsoe.modelling.features", reason="acsoe.modelling.features does not exist yet"
)

INTERVAL_S = 900
MIN_FILL = 0.8

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "candles_sample.parquet"


def synthetic(stamps: list[int]) -> pl.DataFrame:
    """Candles at exactly `stamps`, deterministic and deliberately not flat.

    A constant series makes every range, volume and efficiency feature zero or NaN, and
    a test comparing zeros passes against arithmetic that never ran. The wobble is a
    fixed function of the row index, so two calls with the same stamps produce the same
    frame and a test can compare two computations exactly.
    """
    rows = []
    price = 100.0
    for index, ts in enumerate(stamps):
        price = price * (1.0 + 0.0013 * ((index % 7) - 3))
        rows.append(
            {
                "ts": ts,
                "open": price * 0.999,
                "high": price * 1.004,
                "low": price * 0.996,
                "close": price,
                "volume": 1000.0 + 37.0 * (index % 11),
                "trades": 20 + (index % 5),
            }
        )
    return pl.DataFrame(rows)


def contiguous(count: int, *, start: int = 1_700_000_000) -> pl.DataFrame:
    if count == 0:
        # An empty frame still has to carry the OHLCVT columns: a pair engine 3
        # published nothing for is a frame with no rows, not a frame with no schema,
        # and `compute` is right to refuse the second.
        return pl.DataFrame(
            schema={
                "ts": pl.Int64,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
                "trades": pl.Int64,
            }
        )
    return synthetic([start + i * INTERVAL_S for i in range(count)])


def compute(frame: pl.DataFrame) -> pl.DataFrame:
    return features.compute(frame, interval_s=INTERVAL_S, min_lookback_fill=MIN_FILL)


def row_at(computed: pl.DataFrame, ts: int) -> dict[str, float]:
    matching = computed.filter(pl.col("ts") == ts)
    assert matching.height == 1, f"expected one feature row at {ts}, got {matching.height}"
    return matching.to_dicts()[0]


def is_nan(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


# --------------------------------------------------------------------------- #
# The contract itself
# --------------------------------------------------------------------------- #


def test_feature_names_are_ordered_unique_and_versioned() -> None:
    names = features.FEATURE_NAMES
    assert isinstance(names, tuple)
    assert len(set(names)) == len(names), "a duplicated feature name silently drops a column"
    assert names, "an empty feature list would make every artefact check vacuous"
    assert isinstance(features.FEATURE_VERSION, str) and features.FEATURE_VERSION


def test_the_output_columns_are_exactly_ts_plus_the_named_features_in_order() -> None:
    """Order is the contract, not a coincidence of how the frame was built.

    A model handed its columns permuted returns confident nonsense and nothing raises,
    so the order is asserted as a sequence rather than as a set.
    """
    computed = compute(contiguous(300))
    assert computed.columns == ["ts", *features.FEATURE_NAMES]


def test_no_feature_is_named_after_an_input_the_archive_does_not_have() -> None:
    forbidden = ("spread", "bid", "ask", "depth")
    offenders = [
        name for name in features.FEATURE_NAMES if any(word in name for word in forbidden)
    ]
    assert offenders == [], offenders


def test_no_feature_encodes_pair_identity() -> None:
    """`compute` is given no pair name, so it cannot encode one.

    Asserted on the signature rather than on the output, because that is where the
    property actually lives: a pooled model that can memorise a pair name has learned
    which pairs went up in the training window and nothing that transfers, and the only
    durable way to prevent it is for the arithmetic never to be told.
    """
    import inspect

    parameters = set(inspect.signature(features.compute).parameters)
    assert "pair" not in parameters
    assert parameters == {"candles", "interval_s", "min_lookback_fill"}


def test_market_quality_features_are_a_subset_of_the_feature_list() -> None:
    """Engine 13 `anomaly` is fitted on this subset; a name outside the list would make
    its artefact unloadable against a manifest written from `FEATURE_NAMES`."""
    assert set(features.MARKET_QUALITY_FEATURES) <= set(features.FEATURE_NAMES)
    assert features.MARKET_QUALITY_FEATURES, "an empty subset would fit on nothing"


def test_max_lookback_bars_is_the_largest_window_actually_computed() -> None:
    """The number engine 5 and the trainer check against `features.max_lookback_bars`.

    Derived from `LOOKBACK_BARS` rather than written twice, and asserted here so that
    adding a longer window without updating the bound is red rather than silent: the
    live path publishes `market_sensor.published_bars` candles, so a lookback longer
    than that can never be filled live while the offline path fills it every time.
    """
    assert max(features.LOOKBACK_BARS) == features.MAX_LOOKBACK_BARS
    for bars in features.LOOKBACK_BARS:
        assert f"bars_in_lookback_{bars}" in features.FEATURE_NAMES


# --------------------------------------------------------------------------- #
# Look-ahead
# --------------------------------------------------------------------------- #


def test_a_feature_at_bar_t_is_unchanged_by_bars_after_t() -> None:
    """Invariant 10, and the reason it is the most fatal defect in this kind of system.

    Compute the same bar twice: once over a frame that **ends** at it, and once over a
    frame that carries a hundred more bars after it. Every feature must be identical.

    Any feature that reads `close` of bar `t+1`, or that includes an in-progress bar,
    changes between the two — and it changes in the direction that makes a backtest look
    better, which is why nothing downstream would ever question it. This test needs no
    mutation to justify it: it fails on contact with the defect it is named for.
    """
    frame = contiguous(400)
    cutoff = int(frame["ts"][299])

    truncated = compute(frame.head(300))
    full = compute(frame)

    early = row_at(truncated, cutoff)
    late = row_at(full, cutoff)

    differing = [
        name
        for name in features.FEATURE_NAMES
        if not (is_nan(early[name]) and is_nan(late[name])) and early[name] != late[name]
    ]
    assert differing == [], (
        "these features changed when bars AFTER the one they describe arrived, which "
        f"means they read the future: {differing[:6]}"
    )


def test_the_look_ahead_assertion_can_fail() -> None:
    """Proof the test above is capable of going red, without editing `features.py`.

    The same comparison, run against a deliberately future-reading column computed here:
    next bar's close. If the detector could not see that, it could not see a real
    look-ahead either — and a test nobody has watched fail is a claim, not a check.
    """
    frame = contiguous(400)
    cutoff = int(frame["ts"][299])

    def with_leak(source: pl.DataFrame) -> pl.DataFrame:
        return source.select(
            "ts", pl.col("close").shift(-1).alias("leak")
        )

    early = with_leak(frame.head(300)).filter(pl.col("ts") == cutoff).to_dicts()[0]
    late = with_leak(frame).filter(pl.col("ts") == cutoff).to_dicts()[0]

    assert is_nan(early["leak"]), "the last row of a truncated frame has no next bar"
    assert not is_nan(late["leak"])
    assert early["leak"] != late["leak"]


# --------------------------------------------------------------------------- #
# Lookbacks are windows of time
# --------------------------------------------------------------------------- #


def test_a_contiguous_window_reports_exactly_its_own_bar_count() -> None:
    """The control for the hole test below. Without it, an implementation that always
    reported a short window would pass the hole assertion and be wrong everywhere."""
    computed = compute(contiguous(400))
    last = row_at(computed, int(contiguous(400)["ts"][399]))
    for bars in features.LOOKBACK_BARS:
        assert last[f"bars_in_lookback_{bars}"] == float(bars), bars


def test_a_hole_shortens_the_window_rather_than_stretching_it() -> None:
    """Spec 63's first named mutation: a lookback counted in rows.

    The series has a hole of a third of the longest window immediately behind the bar
    under test. A window of `n` bars is `n * interval_s` seconds, so the counter reports
    only what fell inside those seconds. An implementation taking the previous `n`
    **rows** reports a full window every time and quietly computes a z-score over a
    stretch of market on the far side of a period with no trades.
    """
    longest = features.MAX_LOOKBACK_BARS
    tail = longest // 4
    # The hole must be wider than `longest - tail`, or the window still reaches past it
    # and the expected count is a sum of two runs rather than one. Getting that wrong is
    # how this test first went red against a correct implementation: with a 32-bar hole
    # the 96-bar window legitimately held 40 pre-hole bars plus the 24 after it, and 64
    # is the right answer. A hole of a full window makes the arithmetic unambiguous.
    hole = longest
    start = 1_700_000_000
    stamps = [start + i * INTERVAL_S for i in range(longest * 3)]
    resume = stamps[-1] + (hole + 1) * INTERVAL_S
    stamps += [resume + i * INTERVAL_S for i in range(tail)]

    computed = compute(synthetic(stamps))
    last = row_at(computed, stamps[-1])

    counter = f"bars_in_lookback_{longest}"
    assert last[counter] == float(tail), (
        f"{counter} reported {last[counter]} over a window containing a {hole}-bar hole; "
        f"a row-counted lookback would report {longest} and a time-counted one {tail}"
    )
    assert last[counter] < longest

    # And the partial case, which is the one a row-counted implementation gets most
    # plausibly wrong: a hole narrower than the window leaves bars on both sides of it,
    # and the count is what fell inside the seconds rather than the previous n rows.
    narrow_hole = longest // 3
    narrow = [start + i * INTERVAL_S for i in range(longest * 3)]
    narrow_resume = narrow[-1] + (narrow_hole + 1) * INTERVAL_S
    narrow += [narrow_resume + i * INTERVAL_S for i in range(tail)]
    partial = row_at(compute(synthetic(narrow)), narrow[-1])
    assert partial[counter] == float(longest - narrow_hole), partial[counter]


def test_an_underfilled_window_yields_nan_for_that_window_and_only_that_window() -> None:
    """A number computed over a window that is mostly absent is indistinguishable from
    one computed over a full window, so it is NaN — never zero, which a model would
    happily learn from.

    **Only that window.** A bar's own range and the hour of the day are known whatever
    the history behind them looks like, and the short lookbacks may still be full while
    the long one is not. Blanking everything would throw away the rows a short-history
    pair can legitimately be judged on, which is the opposite of what spec 64 asks for
    when it says such a pair is reported and never dropped.
    """
    longest = features.MAX_LOOKBACK_BARS
    shortest = min(features.LOOKBACK_BARS)
    # Exactly enough history to fill the shortest window and nowhere near the longest.
    computed = compute(contiguous(shortest + 2))
    last = row_at(computed, int(contiguous(shortest + 2)["ts"][shortest + 1]))

    for name in features.features_for_lookback(longest):
        if name == f"bars_in_lookback_{longest}":
            assert last[name] == float(shortest + 2)
            continue
        assert is_nan(last[name]), f"{name} carries a value over a nearly empty window"

    for name in ("bar_range_pct", "hour_sin", "weekday_cos"):
        assert not is_nan(last[name]), f"{name} needs no history and must not be blanked"


def test_the_counter_itself_is_never_blanked() -> None:
    """`bars_in_lookback_<n>` reports the truth about its own window even when the
    window is too empty for anything else. Blanking it would hide the very fact that
    explains why every other feature over that window is NaN."""
    computed = compute(contiguous(3))
    last = row_at(computed, int(contiguous(3)["ts"][2]))
    for bars in features.LOOKBACK_BARS:
        assert last[f"bars_in_lookback_{bars}"] == 3.0


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_a_frame_missing_an_ohlcvt_column_is_refused() -> None:
    frame = contiguous(200).drop("high")
    with pytest.raises(features.FeatureError, match="missing high"):
        compute(frame)


def test_decimal_money_is_refused_rather_than_silently_cast() -> None:
    """The cast to float happens once, in the caller.

    Engine 5 casts from the decimal strings engine 3 publishes and the offline builder
    casts from the archive's `Decimal` columns. Doing it here instead would let the two
    callers arrive with different precision and the two paths would stop agreeing —
    which is exactly the failure `features_reproduce_in_replay` exists to catch, so it
    must not be possible to reach it by accident.
    """
    from decimal import Decimal

    frame = contiguous(200).with_columns(
        pl.col("close").cast(pl.Decimal(38, 12)).alias("close")
    )
    with pytest.raises(features.FeatureError, match="expected Float64"):
        compute(frame)
    assert Decimal("1") == 1  # the import is load-bearing for the cast above, not decoration


def test_duplicate_timestamps_are_refused() -> None:
    frame = contiguous(50)
    doubled = pl.concat([frame, frame.tail(1)]).sort("ts")
    with pytest.raises(features.FeatureError, match="duplicate timestamps"):
        compute(doubled)


def test_an_empty_frame_gives_an_empty_frame_with_the_right_columns() -> None:
    """Not a raise: a pair engine 3 published nothing for is normal, and the caller
    needs a frame it can concatenate rather than an exception to catch."""
    empty = contiguous(0)
    computed = compute(empty)
    assert computed.height == 0
    assert computed.columns == ["ts", *features.FEATURE_NAMES]


@pytest.mark.parametrize("fill", [0.0, -1.0, 1.5])
def test_an_impossible_fill_threshold_is_refused(fill: float) -> None:
    with pytest.raises(features.FeatureError, match="min_lookback_fill"):
        features.compute(contiguous(200), interval_s=INTERVAL_S, min_lookback_fill=fill)


def test_a_non_positive_interval_is_refused() -> None:
    with pytest.raises(features.FeatureError, match="interval_s"):
        features.compute(contiguous(200), interval_s=0, min_lookback_fill=MIN_FILL)


# --------------------------------------------------------------------------- #
# Over the committed archive slice
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not FIXTURE.is_file(), reason="candles_sample.parquet is not committed")
def test_the_committed_slice_computes_a_full_feature_row_at_its_last_bar() -> None:
    """Real archive data with its real hole, not a synthesised series.

    The fixture is the OHLCVT slice the labelled sample was produced from, extended back
    by `market_sensor.published_bars` so the first labelled bar has a full lookback
    behind it. If the longest window cannot be filled at the end of it, the fixture is
    too short for anything Phase 5 does and this says so here rather than at the point
    a model trains on nothing.
    """
    frame = pl.read_parquet(FIXTURE).with_columns(
        [pl.col(c).cast(pl.Float64) for c in ("open", "high", "low", "close", "volume")]
    )
    computed = compute(frame)
    assert computed.height == frame.height
    last = row_at(computed, int(frame["ts"].max()))
    unfilled = [name for name in features.FEATURE_NAMES if is_nan(last[name])]
    assert unfilled == [], unfilled
