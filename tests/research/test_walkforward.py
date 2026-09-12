"""The purged, embargoed walk-forward splitter. Spec 53.

**Every test here constructs its rows.** An end-to-end test cannot see the difference
between a correct embargo and none at all, because the fold *indices* do not overlap in
either case — the leak is in the label windows, and a window that straddles a boundary
has to be placed there deliberately. A test that read a real labelled slice and asserted
"the folds do not overlap" would pass against a splitter with no purge in it.

Four rows recur throughout, and each exists to be distinguishable from the others:

* ``safe`` — decision bar and label window both a month inside training. Must survive,
  or the file is passing a splitter that returns an empty training set.
* ``straddler`` — decision bar two days inside training, label window ending **inside**
  the test window. Must be purged. A splitter purging on ``decision_ts`` keeps it.
* ``embargoed`` — decision bar two bars before the test window, inside the embargo span,
  with a label window that closed before the test window opened. Nothing about its
  window straddles anything, so only the embargo can remove it.
* ``before_embargo`` — one bar older than the embargo span. Must survive, or the embargo
  has become a truncation of everything near the boundary.
* ``after_test`` — a day after the test window. **Must never train**, by operator ruling
  1 of 2026-09-12: a fold trains on the past only. Before that ruling this row was named
  ``after_embargo`` and was required to *survive*, which is the two-sided design the
  ruling retired.

The middle two are what make the embargo assertion independent of the purge assertion.
Every assertion was proved capable of failing by mutation; the mutations and their red
messages are in `docs/build-log/phase-4/c-interface.md` and, for the past-only rule,
`docs/build-log/phase-4/lead.md`.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from typing import Any

import pytest

from acsoe.research.walkforward import (
    DECISION_TS_FIELD,
    KEY_EMBARGO_BARS,
    LABEL_WINDOW_END_FIELD,
    MissingSettingError,
    purged_walk_forward,
    read_settings,
)

INTERVAL_S = 900
DAY = 86_400
ORIGIN = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())


@pytest.fixture
def settings(paper_config: Any) -> Any:
    return read_settings(paper_config)


@pytest.fixture
def boundary(settings: Any) -> dict[str, int]:
    """The one constructed fold, in seconds, derived from the committed config."""
    test_start = ORIGIN + settings.training_window_s
    test_end = test_start + settings.test_window_s
    return {
        "test_start": test_start,
        "test_end": test_end,
        "embargo_start": test_start - settings.embargo_s(INTERVAL_S),
    }


def label(label_id: str, decision_ts: int, window_end_ts: int) -> dict[str, Any]:
    return {
        "label_id": label_id,
        DECISION_TS_FIELD: decision_ts,
        LABEL_WINDOW_END_FIELD: window_end_ts,
        "label": "target",
    }


@pytest.fixture
def rows(boundary: dict[str, int]) -> list[dict[str, Any]]:
    return [
        label("safe", boundary["test_start"] - 30 * DAY, boundary["test_start"] - 29 * DAY),
        # Comfortably inside training by its decision bar; its label window ends a day
        # *inside* the test window. This is the leak, and `decision_ts` says nothing
        # about it.
        label("straddler", boundary["test_start"] - 2 * DAY, boundary["test_start"] + DAY),
        label("in_test", boundary["test_start"] + 2 * DAY, boundary["test_start"] + 3 * DAY),
        # Inside the embargo span before the test window, label closed in time.
        label(
            "embargoed",
            boundary["test_start"] - 2 * INTERVAL_S,
            boundary["test_start"] - INTERVAL_S,
        ),
        # One bar older than the embargo span, label closed before the span opens.
        label(
            "before_embargo",
            boundary["embargo_start"] - INTERVAL_S,
            boundary["embargo_start"] - 1,
        ),
        label("after_test", boundary["test_end"] + DAY, boundary["test_end"] + 2 * DAY),
    ]


def names(rows: list[dict[str, Any]], index: tuple[int, ...]) -> list[str]:
    return [str(rows[i]["label_id"]) for i in index]


def one_fold(rows: list[dict[str, Any]], config: Any, boundary: dict[str, int]) -> Any:
    folds = purged_walk_forward(
        rows,
        config=config,
        interval_s=INTERVAL_S,
        test_start_ts=boundary["test_start"],
        test_end_ts=boundary["test_end"],
    )
    assert len(folds) == 1
    return folds[0]


# --------------------------------------------------------------------------- #
# The test the operator named, and it is not optional
# --------------------------------------------------------------------------- #


def test_a_training_row_whose_label_window_straddles_the_boundary_is_purged(
    rows: list[dict[str, Any]], paper_config: Any, boundary: dict[str, int]
) -> None:
    """Asserted **by identity**, not by counting.

    A count assertion passes against a splitter that dropped the wrong row, and on a
    dataset this small it would also pass against one that dropped a row at random.
    """
    fold = one_fold(rows, paper_config, boundary)

    assert "straddler" not in names(rows, fold.train_index)
    assert "safe" in names(rows, fold.train_index)
    assert fold.purged_count == 1


def test_a_training_row_inside_the_embargo_span_is_dropped(
    rows: list[dict[str, Any]], paper_config: Any, boundary: dict[str, int]
) -> None:
    """And the row one bar older than the span is not.

    Both halves are necessary. Without the second, a splitter that dropped everything
    near the boundary would pass — and that is not an embargo, it is a truncation.
    """
    fold = one_fold(rows, paper_config, boundary)
    train = names(rows, fold.train_index)

    assert "embargoed" not in train
    assert "before_embargo" in train
    assert fold.embargoed_count == 1


# --------------------------------------------------------------------------- #
# Operator ruling 1, 2026-09-12: the training set is the past only
# --------------------------------------------------------------------------- #


def test_a_row_after_the_test_window_never_trains(
    rows: list[dict[str, Any]], paper_config: Any, boundary: dict[str, int]
) -> None:
    """By identity, and counted in its own column.

    The two-sided splitter this replaced kept this row deliberately, and a test in this
    file required it to. A model that trains on rows from after the period it is scored
    on reports a number the live system will never see.
    """
    fold = one_fold(rows, paper_config, boundary)

    assert "after_test" not in names(rows, fold.train_index)
    assert fold.after_test_count == 1
    assert fold.summary()["after_test"] == 1
    assert fold.out_of_window_count == 0
    assert fold.train_end_ts == boundary["test_start"]


def test_no_training_row_post_dates_its_test_window_on_rolling_folds(
    paper_config: Any, settings: Any
) -> None:
    """Every fold, every training row, both timestamps.

    The label window end is checked as well as the decision bar: a row whose decision
    bar precedes the test window and whose outcome was known only inside it is the
    purge's job, and a past-only rule that forgot the purge would still fail here.
    """
    span = settings.training_window_s + 60 * DAY
    rolling = [
        label(f"row-{i}", ORIGIN + i * 6 * 3600, ORIGIN + i * 6 * 3600 + 12 * 3600)
        for i in range(span // (6 * 3600))
    ]

    folds = purged_walk_forward(rolling, config=paper_config, interval_s=INTERVAL_S)

    assert len(folds) >= 4
    for fold in folds:
        assert fold.train_index, f"fold {fold.fold_index} trained on nothing"
        for i in fold.train_index:
            assert rolling[i][DECISION_TS_FIELD] < fold.test_start_ts
            assert rolling[i][LABEL_WINDOW_END_FIELD] < fold.test_start_ts
    # The assertion above is vacuous unless rows after the test window exist and were
    # seen. The first fold has sixty days of them.
    assert folds[0].after_test_count > 0


def test_the_purge_and_the_embargo_are_counted_separately(
    rows: list[dict[str, Any]], paper_config: Any, boundary: dict[str, int]
) -> None:
    """Two mechanisms, two numbers.

    A splitter reporting them in one column is one whose two mechanisms are the same
    mechanism, and the day the purge stops working the total would still look healthy.
    """
    fold = one_fold(rows, paper_config, boundary)

    assert (fold.purged_count, fold.embargoed_count) == (1, 1)
    assert fold.summary()["purged"] == 1
    assert fold.summary()["embargoed"] == 1


def test_the_test_index_holds_only_rows_inside_the_test_window(
    rows: list[dict[str, Any]], paper_config: Any, boundary: dict[str, int]
) -> None:
    fold = one_fold(rows, paper_config, boundary)

    assert names(rows, fold.test_index) == ["in_test"]
    assert set(fold.train_index) & set(fold.test_index) == set()


def test_a_label_window_ending_exactly_at_the_test_start_is_purged(
    paper_config: Any, boundary: dict[str, int]
) -> None:
    """`>=`, not `>`. A window closing at the instant the test window opens was resolved
    by the first bar of the test period, and off-by-one here is a leak of exactly one
    observation per fold that nothing would ever report."""
    exact = [
        label("exact", boundary["test_start"] - DAY, boundary["test_start"]),
        label("in_test", boundary["test_start"] + DAY, boundary["test_start"] + 2 * DAY),
    ]
    fold = one_fold(exact, paper_config, boundary)

    assert names(exact, fold.train_index) == []
    assert fold.purged_count == 1


def test_a_label_window_ending_one_second_earlier_survives(
    paper_config: Any, boundary: dict[str, int]
) -> None:
    """The other side of the same boundary, so the test above cannot be satisfied by a
    splitter that purges everything."""
    exact = [
        label("just_before", boundary["test_start"] - DAY, boundary["test_start"] - 1),
        label("in_test", boundary["test_start"] + DAY, boundary["test_start"] + 2 * DAY),
    ]
    fold = one_fold(exact, paper_config, boundary)

    assert names(exact, fold.train_index) == ["just_before"]
    assert fold.purged_count == 0


# --------------------------------------------------------------------------- #
# The settings, none of which may be defaulted
# --------------------------------------------------------------------------- #


def test_a_null_embargo_raises_rather_than_defaulting_to_zero(paper_config: Any) -> None:
    """An embargo that silently became zero would be indistinguishable from a working
    one in every output the backtest produces."""

    class NullEmbargo:
        def get(self, key: str, /) -> Any:
            return None if key == KEY_EMBARGO_BARS else paper_config.get(key)

    with pytest.raises(MissingSettingError, match=KEY_EMBARGO_BARS):
        read_settings(NullEmbargo())


def test_a_label_without_a_window_end_raises(
    paper_config: Any, boundary: dict[str, int]
) -> None:
    """A splitter that fell back to `decision_ts` when the window end was missing would
    produce leaked folds that look correct, so the absence is a stop."""
    broken = [{DECISION_TS_FIELD: boundary["test_start"] - DAY}]

    with pytest.raises(MissingSettingError, match=LABEL_WINDOW_END_FIELD):
        purged_walk_forward(
            broken,
            config=paper_config,
            interval_s=INTERVAL_S,
            test_start_ts=boundary["test_start"],
            test_end_ts=boundary["test_end"],
        )


def test_half_a_test_window_is_refused(paper_config: Any, boundary: dict[str, int]) -> None:
    with pytest.raises(MissingSettingError, match="both"):
        purged_walk_forward(
            [], config=paper_config, interval_s=INTERVAL_S, test_start_ts=boundary["test_start"]
        )


# --------------------------------------------------------------------------- #
# Rolling folds, and the empty one that must not be dropped
# --------------------------------------------------------------------------- #


def test_rolling_folds_advance_by_the_test_window(paper_config: Any, settings: Any) -> None:
    """Test windows roll forward by `backtest.retrain_interval_days` and never overlap."""
    span = settings.training_window_s + 40 * DAY
    rolling = [
        label(f"row-{i}", ORIGIN + i * DAY, ORIGIN + i * DAY + 6 * 3600)
        for i in range(span // DAY)
    ]

    folds = purged_walk_forward(rolling, config=paper_config, interval_s=INTERVAL_S)

    assert len(folds) >= 2
    starts = [fold.test_start_ts for fold in folds]
    assert starts == sorted(starts)
    assert all(
        later - earlier == settings.test_window_s
        for earlier, later in itertools.pairwise(starts)
    )
    for fold in folds:
        assert set(fold.train_index) & set(fold.test_index) == set()


def test_a_fold_that_comes_out_empty_is_reported_not_dropped(
    paper_config: Any, boundary: dict[str, int]
) -> None:
    """Spec 53. A run that quietly produced four folds where the caller expected twelve
    reports metrics over a third of the data with nothing anywhere saying so."""
    only_straddlers = [
        label("straddler", boundary["test_start"] - DAY, boundary["test_start"] + DAY),
        label("in_test", boundary["test_start"] + DAY, boundary["test_start"] + 2 * DAY),
    ]
    fold = one_fold(only_straddlers, paper_config, boundary)

    assert fold.train_index == ()
    assert fold.is_empty is True
    assert fold.summary()["empty"] is True
    assert fold.purged_count == 1


def test_the_splitter_accepts_the_frame_the_labeller_produces(
    paper_config: Any, boundary: dict[str, int]
) -> None:
    """The seam with `research/labelling.py`, exercised through the real frame rather
    than through a hand-built list of dicts that happens to have the right keys."""
    import polars as pl

    frame = pl.DataFrame(
        [
            label("safe", boundary["test_start"] - 30 * DAY, boundary["test_start"] - 29 * DAY),
            label("straddler", boundary["test_start"] - DAY, boundary["test_start"] + DAY),
            label("in_test", boundary["test_start"] + DAY, boundary["test_start"] + 2 * DAY),
        ]
    )

    folds = purged_walk_forward(
        frame,
        config=paper_config,
        interval_s=INTERVAL_S,
        test_start_ts=boundary["test_start"],
        test_end_ts=boundary["test_end"],
    )

    assert folds[0].train_index == (0,)
    assert folds[0].purged_count == 1
