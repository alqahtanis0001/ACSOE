"""Triple-barrier labelling. Spec 52.

Two kinds of test here, and both are needed.

**Constructed windows**, where every price is chosen to sit a known distance from a
barrier. That is the only way to test a boundary: real data almost never lands exactly on
one, and `>=` against `>` is invisible until it does.

**The twenty hand-verified labels**, drawn from the real archive and checked against the
printed candle window by hand rather than by running the labeller and saving its output.
A fixture built the second way proves only that the labeller equals itself. The working
for three of them is in `docs/build-log/phase-4/c-interface.md`.

Every mutation spec 52 names was applied and observed red; they are recorded in the same
build log.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.research.labelling import (
    LABEL_STOP,
    LABEL_TARGET,
    LABEL_TIMEOUT,
    label_candles,
    label_series,
    read_barriers,
)

INTERVAL = 900
T0 = 1_700_000_000 - (1_700_000_000 % INTERVAL)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "labels_hand_verified.json"


def candle(index: int, *, high: str, low: str, close: str = "100", open_: str = "100") -> dict[str, Any]:
    return {
        "ts": T0 + index * INTERVAL,
        "open": Decimal(open_),
        "high": Decimal(high),
        "low": Decimal(low),
        "close": Decimal(close),
        "volume": Decimal("1"),
        "trades": 1,
    }


def flat(index: int) -> dict[str, Any]:
    """A bar that touches neither barrier: a whole 1% inside both."""
    return candle(index, high="100.5", low="99.5")


def series(*bars: dict[str, Any], length: int = 60) -> list[dict[str, Any]]:
    """The supplied bars, padded with quiet ones out to `length`.

    Padded because the horizon is 48 bars and a decision bar whose window runs past the
    end of the series is excluded — a fixture that stopped at bar 10 would test the
    exclusion rule on every case rather than the case it meant to.
    """
    by_index = {int((bar["ts"] - T0) // INTERVAL): bar for bar in bars}
    return [by_index.get(i, flat(i)) for i in range(length)]


@pytest.fixture
def barriers(paper_config: Any) -> Any:
    return read_barriers(paper_config)


# --------------------------------------------------------------------------- #
# The barrier prices, which everything else is measured against
# --------------------------------------------------------------------------- #


def test_barrier_prices_come_from_the_decision_bar_close(
    paper_config: Any, barriers: Any
) -> None:
    """Exact `Decimal`. A float target of 103.00000000000001 never touches."""
    label = label_candles(
        series(candle(3, high="103", low="99.9")),
        pair="AAA/USD",
        decision_ts=T0,
        config=paper_config,
        interval_s=INTERVAL,
    )

    assert label is not None
    assert label.target_price == Decimal("100") * (Decimal(1) + barriers.target_pct)
    assert label.stop_price == Decimal("100") * (Decimal(1) - barriers.stop_pct)
    assert label.target_price == Decimal("103.00")
    assert label.stop_price == Decimal("98.500")


def test_the_thresholds_are_read_from_config_not_written_into_the_module(
    paper_config: Any,
) -> None:
    """Change the config, and every barrier moves with it."""

    class Doubled:
        def get(self, key: str, /) -> Any:
            if key == "barriers.target_pct":
                return 0.06
            return paper_config.get(key)

    label = label_candles(
        series(candle(3, high="106", low="99.9")),
        pair="AAA/USD",
        decision_ts=T0,
        config=Doubled(),
        interval_s=INTERVAL,
    )

    assert label is not None
    assert label.target_price == Decimal("106.00")
    assert label.label == LABEL_TARGET


# --------------------------------------------------------------------------- #
# The touch, and the boundary it sits on
# --------------------------------------------------------------------------- #


def test_a_high_exactly_at_the_target_is_a_touch(paper_config: Any) -> None:
    """`>=`, not `>`. A limit order resting at the target fills when the price reaches
    it, so requiring the high to *exceed* it discards a real fill."""
    label = label_candles(
        series(candle(5, high="103.00", low="99.9")),
        pair="AAA/USD",
        decision_ts=T0,
        config=paper_config,
        interval_s=INTERVAL,
    )

    assert label is not None
    assert label.label == LABEL_TARGET
    assert label.bars_elapsed == 5


def test_a_high_one_cent_below_the_target_is_not_a_touch(paper_config: Any) -> None:
    """The other side of the same boundary, so the test above cannot be satisfied by a
    labeller that calls everything a touch."""
    label = label_candles(
        series(candle(5, high="102.99", low="99.9")),
        pair="AAA/USD",
        decision_ts=T0,
        config=paper_config,
        interval_s=INTERVAL,
    )

    assert label is not None
    assert label.label == LABEL_TIMEOUT


def test_a_low_exactly_at_the_stop_is_a_touch(paper_config: Any) -> None:
    label = label_candles(
        series(candle(2, high="100.5", low="98.500")),
        pair="AAA/USD",
        decision_ts=T0,
        config=paper_config,
        interval_s=INTERVAL,
    )

    assert label is not None
    assert label.label == LABEL_STOP
    assert label.bars_elapsed == 2


def test_the_first_barrier_touched_wins_not_the_better_one(paper_config: Any) -> None:
    """A stop on bar 2 and a target on bar 5 is a `stop`.

    Scanning for the target first and returning it would be the same defect as ruling 1
    spread over two bars, and it flatters every losing trade into a winner.
    """
    label = label_candles(
        series(candle(2, high="100.5", low="98.4"), candle(5, high="104", low="99.9")),
        pair="AAA/USD",
        decision_ts=T0,
        config=paper_config,
        interval_s=INTERVAL,
    )

    assert label is not None
    assert label.label == LABEL_STOP
    assert label.bars_elapsed == 2


def test_a_target_before_a_stop_is_a_target(paper_config: Any) -> None:
    """The symmetric case, so the test above is not satisfied by a labeller that always
    answers `stop`."""
    label = label_candles(
        series(candle(2, high="104", low="99.9"), candle(5, high="100.5", low="98.4")),
        pair="AAA/USD",
        decision_ts=T0,
        config=paper_config,
        interval_s=INTERVAL,
    )

    assert label is not None
    assert label.label == LABEL_TARGET
    assert label.bars_elapsed == 2


# --------------------------------------------------------------------------- #
# Ruling 1 — both barriers inside one bar
# --------------------------------------------------------------------------- #


def test_a_bar_touching_both_barriers_is_labelled_stop(paper_config: Any) -> None:
    """The lead's ruling. OHLC carries no intra-bar ordering, and the pessimistic
    reading is the only one that cannot flatter the strategy."""
    label = label_candles(
        series(candle(4, high="104", low="98.0")),
        pair="AAA/USD",
        decision_ts=T0,
        config=paper_config,
        interval_s=INTERVAL,
    )

    assert label is not None
    assert label.label == LABEL_STOP
    assert label.ambiguous is True


def test_an_unambiguous_stop_is_not_flagged_ambiguous(paper_config: Any) -> None:
    """`ambiguous` counts the rows decided by the ruling rather than by the data, so a
    labeller that flagged every `stop` would make the count meaningless — and the count
    is how a reader judges how much of a slice is assumption."""
    label = label_candles(
        series(candle(4, high="100.5", low="98.0")),
        pair="AAA/USD",
        decision_ts=T0,
        config=paper_config,
        interval_s=INTERVAL,
    )

    assert label is not None
    assert label.label == LABEL_STOP
    assert label.ambiguous is False


# --------------------------------------------------------------------------- #
# The decision bar is never inspected
# --------------------------------------------------------------------------- #


def test_the_decision_bar_s_own_high_and_low_are_never_a_touch(paper_config: Any) -> None:
    """Look-ahead within one bar.

    The decision bar here sweeps from 96 to 105 — through both barriers — and nothing
    after it goes anywhere. A labeller that scanned the decision bar answers `stop` at
    bar 0; the correct answer is `timeout`.
    """
    rows = series()
    rows[0] = candle(0, high="105", low="96", close="100")

    label = label_candles(
        rows, pair="AAA/USD", decision_ts=T0, config=paper_config, interval_s=INTERVAL
    )

    assert label is not None
    assert label.label == LABEL_TIMEOUT
    assert label.bars_elapsed == 48


# --------------------------------------------------------------------------- #
# Ruling 2 — the timeout is a time, not a count of rows
# --------------------------------------------------------------------------- #


def test_the_horizon_is_a_time_so_a_gap_does_not_stretch_it(paper_config: Any) -> None:
    """Twenty candles in a 48-bar window, then a touch **past** the horizon.

    Counting rows would keep walking until it had seen 48 *rows* and would find that
    touch, turning a 12-hour horizon into a multi-day one over precisely the holes
    `research/historical.py` refuses to interpolate away. The label must be `timeout`.
    """
    inside = [flat(i) for i in range(20)]
    # Nothing between bar 20 and bar 60: a quiet stretch the archive simply has no rows
    # for. Bar 60 is past the 48-bar horizon and sails through the target.
    outside = [candle(60, high="110", low="99.9"), candle(61, high="110", low="99.9")]

    label = label_candles(
        [*inside, *outside],
        pair="AAA/USD",
        decision_ts=T0,
        config=paper_config,
        interval_s=INTERVAL,
    )

    assert label is not None
    assert label.label == LABEL_TIMEOUT
    assert label.candles_in_window == 19
    # The terminal bar is the last one *inside* the window, not the 48th row.
    assert label.touch_ts == T0 + 19 * INTERVAL
    # ...but the window end the splitter purges on is the horizon itself, which is later.
    assert label.label_window_end_ts == T0 + 48 * INTERVAL


def test_bars_elapsed_is_measured_in_time_not_in_rows(paper_config: Any) -> None:
    """Two candles exist between the decision bar and the touch; thirty bars passed."""
    rows = [flat(0), flat(1), candle(30, high="104", low="99.9"), *[flat(i) for i in range(31, 60)]]

    label = label_candles(
        rows, pair="AAA/USD", decision_ts=T0, config=paper_config, interval_s=INTERVAL
    )

    assert label is not None
    assert label.label == LABEL_TARGET
    assert label.bars_elapsed == 30
    # Every candle *present in the window*, not the two the walk looked at before the
    # touch: bar 1, then bars 30 to 48. The count says how much of the horizon had data
    # underneath it, so it does not stop where the scan does.
    assert label.candles_in_window == 20


# --------------------------------------------------------------------------- #
# The seam with the splitter, which is the field with the least to say for itself
# and the most riding on it
# --------------------------------------------------------------------------- #


def test_a_touched_label_reports_the_touch_as_its_window_end(paper_config: Any) -> None:
    """`label_window_end_ts` is when the outcome became known, not when the bet was made.

    **This test exists because a mutation survived without it.** Every other assertion
    in this file is about the label — which barrier, when, how many bars — so setting
    the window end to `decision_ts` changed nothing any of them could see. It changes
    everything downstream: the splitter purges a training row whose window ends at or
    after the test window starts, and a window that ends where it began never straddles
    anything, so nothing is ever purged.
    """
    label = label_candles(
        series(candle(6, high="104", low="99.9")),
        pair="AAA/USD",
        decision_ts=T0,
        config=paper_config,
        interval_s=INTERVAL,
    )

    assert label is not None
    assert label.label == LABEL_TARGET
    assert label.label_window_end_ts == label.touch_ts
    assert label.label_window_end_ts == T0 + 6 * INTERVAL
    assert label.label_window_end_ts > label.decision_ts


def test_the_seam_the_splitter_purges_on_is_the_later_of_the_touch_and_the_horizon(
    paper_config: Any,
) -> None:
    """The seam end to end: real labeller, real splitter, one straddling row.

    Neither module's own tests can see a producer that exports the wrong field — three
    tests prove the splitter purges correctly, and all three keep passing when its input
    stops telling the truth. So this one drives both.

    The decision bar sits a day before the test window and its target is touched inside
    it. Purged on the label window end, the row is dropped. Purged on `decision_ts` —
    which is what a labeller reporting `decision_ts` as its window end forces, whatever
    the splitter does — it survives, and the model trains on the period it is about to
    be scored over.
    """
    from acsoe.research.walkforward import purged_walk_forward, read_settings

    settings = read_settings(paper_config)
    # The decision bar is placed so the touch lands after the test window opens.
    decision_ts = T0
    rows = series(candle(20, high="104", low="99.9"))
    label = label_candles(
        rows, pair="AAA/USD", decision_ts=decision_ts, config=paper_config, interval_s=INTERVAL
    )
    assert label is not None
    assert label.label == LABEL_TARGET

    test_start = label.touch_ts - INTERVAL  # the touch lands one bar inside the test window
    folds = purged_walk_forward(
        [
            {
                "decision_ts": label.decision_ts,
                "label_window_end_ts": label.label_window_end_ts,
            },
            {
                "decision_ts": test_start + INTERVAL,
                "label_window_end_ts": test_start + 2 * INTERVAL,
            },
        ],
        config=paper_config,
        interval_s=INTERVAL,
        test_start_ts=test_start,
        test_end_ts=test_start + settings.test_window_s,
    )

    assert folds[0].train_index == ()
    assert folds[0].purged_count == 1


# --------------------------------------------------------------------------- #
# Exclusion, never a fabricated outcome
# --------------------------------------------------------------------------- #


def test_a_bar_whose_window_runs_past_the_end_of_the_series_is_excluded(
    paper_config: Any,
) -> None:
    """Not labelled `timeout`. Labelling it records an outcome that has not happened
    yet, which is invariant 10 with a different face."""
    rows = [flat(i) for i in range(40)]

    assert (
        label_candles(
            rows, pair="AAA/USD", decision_ts=T0, config=paper_config, interval_s=INTERVAL
        )
        is None
    )


def test_a_bar_whose_window_ends_exactly_at_the_last_candle_is_labelled(
    paper_config: Any,
) -> None:
    """The boundary of the rule above. Without this, a labeller that excluded everything
    would pass the exclusion test."""
    rows = [flat(i) for i in range(49)]

    label = label_candles(
        rows, pair="AAA/USD", decision_ts=T0, config=paper_config, interval_s=INTERVAL
    )

    assert label is not None
    assert label.label == LABEL_TIMEOUT


def test_a_window_with_no_candles_in_it_is_excluded(paper_config: Any) -> None:
    """A `timeout` needs a terminal price to compute a return from, and across a
    multi-day hole there is none. Excluding invents nothing."""
    rows = [flat(0), *[flat(i) for i in range(50, 110)]]

    assert (
        label_candles(
            rows, pair="AAA/USD", decision_ts=T0, config=paper_config, interval_s=INTERVAL
        )
        is None
    )


def test_the_series_reports_what_it_excluded_and_why(paper_config: Any) -> None:
    """Counts, not silence. A slice that quietly dropped a third of its bars would show
    up nowhere."""
    rows = [flat(i) for i in range(60)]

    result = label_series(rows, pair="AAA/USD", config=paper_config, interval_s=INTERVAL)

    assert result.considered == 60
    # Bars 12 to 59 have windows running past bar 59.
    assert result.excluded_past_end == 48
    assert len(result.labels) == 12
    assert result.excluded_empty_window == 0


# --------------------------------------------------------------------------- #
# The twenty hand-verified labels
# --------------------------------------------------------------------------- #


def hand_verified() -> list[dict[str, Any]]:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = document["entries"]
    return entries


def test_the_fixture_carries_twenty_entries_covering_every_case() -> None:
    """The fixture is evidence and this is the check that it is still evidence.

    Without it, dropping the ambiguous entry or the excluded ones would leave the
    comparison test passing over a fixture that no longer exercises the rulings.
    """
    entries = hand_verified()

    assert len(entries) == 20
    labels = [entry["expected_label"] for entry in entries]
    assert {LABEL_TARGET, LABEL_STOP, LABEL_TIMEOUT} <= set(labels)
    assert None in labels
    assert any(entry.get("ambiguous") for entry in entries)
    assert any(
        entry.get("candles_in_window") is not None
        and entry["candles_in_window"] < entry["expected_bars_elapsed"]
        for entry in entries
        if entry["expected_label"] is not None
    )


@pytest.mark.parametrize("index", range(20))
def test_the_labeller_reproduces_each_hand_verified_label(
    index: int, paper_config: Any
) -> None:
    """One test per entry, so a failure names the bar rather than the fixture.

    Parametrised over `range(20)` rather than over the fixture's contents: a
    parametrisation driven by the file would silently shrink to nothing if the file did.
    """
    entry = hand_verified()[index]
    candles = [
        {
            "ts": int(row["ts"]),
            "open": Decimal(str(row["open"])),
            "high": Decimal(str(row["high"])),
            "low": Decimal(str(row["low"])),
            "close": Decimal(str(row["close"])),
            "volume": Decimal(str(row["volume"])),
            "trades": int(row["trades"]),
        }
        for row in entry["candles"]
    ]

    label = label_candles(
        candles,
        pair=entry["pair"],
        decision_ts=int(entry["decision_ts"]),
        config=paper_config,
        interval_s=int(entry["interval_s"]),
    )

    if entry["expected_label"] is None:
        assert label is None, f"{entry['note']}: expected exclusion, got {label}"
        return
    assert label is not None, entry["note"]
    assert label.label == entry["expected_label"], entry["note"]
    assert label.touch_ts == entry["expected_touch_ts"], entry["note"]
    assert label.bars_elapsed == entry["expected_bars_elapsed"], entry["note"]
    assert label.target_price == Decimal(entry["target_price"]), entry["note"]
    assert label.stop_price == Decimal(entry["stop_price"]), entry["note"]
    assert label.ambiguous is bool(entry["ambiguous"]), entry["note"]
    assert label.candles_in_window == entry["candles_in_window"], entry["note"]


# --------------------------------------------------------------------------- #
# Invariant 10 — this module may not be reachable from the live path
# --------------------------------------------------------------------------- #


def test_nothing_in_the_live_path_imports_the_labeller() -> None:
    """A label is future information by construction.

    Asserted by reading the source of every live-path module rather than by checking
    `sys.modules`: an import that has not happened in this process is invisible there,
    and the whole risk is an import somebody adds later.
    """
    root = Path(__file__).resolve().parents[2] / "src" / "acsoe"
    offenders = []
    for package in ("engines", "core", "clients", "cli"):
        for path in (root / package).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "research.labelling" in text or "research import labelling" in text:
                offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"invariant 10: the live path imports the labeller: {offenders}"


def test_the_labeller_imports_nothing_from_the_live_path() -> None:
    """The other direction. A research module reaching into `acsoe.engines` would make
    the live path a dependency of the training pipeline and invert invariant 5."""
    source = (
        Path(__file__).resolve().parents[2] / "src" / "acsoe" / "research" / "labelling.py"
    ).read_text(encoding="utf-8")
    import re

    imports = re.findall(r"^\s*(?:from|import)\s+(acsoe[\w.]*)", source, re.MULTILINE)
    assert imports == [], f"labelling.py imports from the package: {imports}"
