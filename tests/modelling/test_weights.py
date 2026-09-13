"""Average-uniqueness weights, and the effective sample size beside every row count.

Spec 63's fifth named mutation is **weights computed without the label window (all
ones)**, and the shape of that defect is what these tests are built around: it does not
crash, it does not change a single prediction, and it makes every metric in the phase
describe a dataset roughly fifty times larger than the one that exists.

The five-row case below is hand-verified rather than taken from the implementation. Its
working, in full, so a later reader can check it without re-deriving anything:

    bars                0    900   1800  2700  3600
    row 0  [   0, 1800]  x     x     x
    row 1  [ 900, 2700]        x     x     x
    row 2  [1800, 3600]              x     x     x
    row 3  [2700, 4500]                    x     x
    row 4  [3600, 5400]                          x
    concurrency         1     2     3     3     3

    w0 = mean(1/1, 1/2, 1/3) = 0.611111
    w1 = mean(1/2, 1/3, 1/3) = 0.388889
    w2 = mean(1/3, 1/3, 1/3) = 0.333333
    w3 = mean(1/3, 1/3)      = 0.333333
    w4 = mean(1/3)           = 0.333333

    effective sample size    = 2.0, against five rows
"""

from __future__ import annotations

import math

import pytest

from tests.conftest import require_module

weights = require_module(
    "acsoe.modelling.weights", reason="acsoe.modelling.weights does not exist yet"
)

DECISION = [0, 900, 1800, 2700, 3600]
END = [1800, 2700, 3600, 4500, 5400]
EXPECTED = [11.0 / 18.0, 7.0 / 18.0, 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]


def test_concurrency_counts_overlapping_windows_per_bar() -> None:
    bars, counts = weights.concurrency(DECISION, END)
    assert bars == DECISION
    assert counts == [1, 2, 3, 3, 3]


def test_the_hand_verified_case() -> None:
    computed = weights.average_uniqueness(DECISION, END)
    assert len(computed) == len(EXPECTED)
    for index, (got, want) in enumerate(zip(computed, EXPECTED, strict=True)):
        assert math.isclose(got, want, rel_tol=0, abs_tol=1e-12), (index, got, want)


def test_the_effective_sample_size_is_far_below_the_row_count() -> None:
    """The number that has to appear beside every row count.

    This is the assertion the "all ones" mutation fails: five rows whose label windows
    overlap almost completely are two observations, and an implementation returning 1.0
    per row reports five. On the real dataset the same mistake turns 20,331,237 rows
    into a claim of 20,331,237 independent draws when the true figure is orders of
    magnitude smaller, and every Brier, log loss and confidence interval computed from
    it is wrong in the flattering direction.
    """
    computed = weights.average_uniqueness(DECISION, END)
    ess = weights.effective_sample_size(computed)
    assert math.isclose(ess, 2.0, rel_tol=0, abs_tol=1e-12)
    assert ess < len(DECISION)


def test_windows_that_overlap_nothing_weigh_one() -> None:
    """The control. Without it an implementation returning a constant small weight would
    satisfy the overlap assertion above and be wrong on every isolated row."""
    computed = weights.average_uniqueness([0, 100_000], [900, 100_900])
    assert computed == [1.0, 1.0]


def test_no_weight_ever_exceeds_one() -> None:
    """A row is at most one whole observation. A weight above 1.0 would be a row
    counted as more than it is, which is the same error as the all-ones mutation in the
    other direction and is far harder to notice."""
    computed = weights.average_uniqueness(DECISION, END)
    assert max(computed) <= 1.0


def test_a_longer_horizon_lowers_every_weight() -> None:
    """The property the whole thing exists for, asserted as a comparison rather than as
    a number: widening the label window makes rows share more of their outcome, so every
    weight falls and the effective sample size falls with it."""
    short = weights.average_uniqueness(DECISION, [d + 900 for d in DECISION])
    long = weights.average_uniqueness(DECISION, [d + 3600 for d in DECISION])
    assert weights.effective_sample_size(long) < weights.effective_sample_size(short)


def test_mismatched_columns_are_refused() -> None:
    with pytest.raises(weights.WeightError, match="two columns of one frame"):
        weights.average_uniqueness([0, 900], [1800])


def test_a_window_that_closes_before_it_opens_is_refused() -> None:
    """Not weighted as zero and not silently skipped: it is a labeller bug, and the
    weight it would otherwise get is a division by zero wearing a number's clothes."""
    with pytest.raises(weights.WeightError, match="before its decision bar"):
        weights.average_uniqueness([1800], [900])


def test_no_rows_gives_no_weights() -> None:
    assert weights.average_uniqueness([], []) == []
    assert weights.effective_sample_size([]) == 0.0


def test_a_hole_in_the_series_does_not_inflate_uniqueness() -> None:
    """Concurrency is counted on the bars that exist, not on a synthetic contiguous grid.

    A period with no trades has no decision bar, so counting it as an uncovered slot
    would raise the uniqueness of every window spanning the hole — rewarding exactly the
    rows whose outcome is least observed. Two rows whose windows both span a large hole
    and cover the same two real bars must weigh the same as if the hole were not there.
    """
    with_hole = weights.average_uniqueness([0, 900], [900_000, 900_900])
    dense = weights.average_uniqueness([0, 900], [1800, 2700])
    assert with_hole == dense
