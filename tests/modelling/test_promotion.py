"""Spec 139 — the promotion bar and the deflated Sharpe ratio, `modelling/promotion.py`.

The bar was fixed before any simulated figure existed, so these tests hold the arithmetic to
numbers computed outside the code: the module docstring's worked example (by hand), published
Student-t quantiles, and `statsmodels`' own Newey-West estimate. The two fabricated models of
spec 139's Check When Done are here too: one whose edge survives a single trial and not the
ledger's count, and one whose overlapping trades look significant only when treated as
independent.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pytest

from acsoe.modelling import promotion
from acsoe.modelling.promotion import (
    Hold,
    Verdict,
    bonferroni_quantile,
    deflated_sharpe_ratio,
    hac_standard_error,
    overlap_lag,
    promotion_verdict,
    student_t_quantile,
)
from tests.conftest import require_module

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs" / "dataset" / "phase-7-trial-ledger.json"

#: The worked example of the module docstring: returns in percent, holds in minutes.
EXAMPLE_RETURNS = (4, 3, 5, 2, 1, 0, -1, 1, 2, 3)


def example_holds() -> list[Hold]:
    return [
        Hold(20 * (k // 2) + 5 * (k % 2), 20 * (k // 2) + 5 * (k % 2) + 10, value / 100)
        for k, value in enumerate(EXAMPLE_RETURNS)
    ]


def ledger_trial_count() -> int:
    """The committed ledger's count, which is what the gate is given."""
    count = json.loads(LEDGER.read_bytes().decode("utf-8"))["trial_count"]
    assert isinstance(count, int)
    return count


# --------------------------------------------------------------------------- #
# The worked example, number by number
# --------------------------------------------------------------------------- #


def test_the_worked_example_at_one_trial_equals_the_hand_computation() -> None:
    verdict = promotion_verdict(example_holds(), 1)
    assert verdict.lag == 1
    assert verdict.mean == pytest.approx(0.02, abs=1e-15)
    assert round(verdict.se_hac * 100, 6) == 0.678233  # type: ignore[operator]
    assert round(verdict.se_naive * 100, 6) == 0.547723  # type: ignore[operator]
    assert round(verdict.quantile, 6) == 2.262157  # type: ignore[arg-type]
    assert round(verdict.lower_bound * 100, 6) == 0.465730  # type: ignore[operator]
    assert verdict.verdict == Verdict.PROMOTED
    assert verdict.promoted is True
    assert verdict.deflated is not None
    assert round(verdict.deflated.sharpe, 6) == 1.154701
    assert round(verdict.deflated.kurtosis, 6) == 2.2
    assert abs(verdict.deflated.skewness) < 1e-12
    assert verdict.deflated.expected_max_sharpe == 0.0
    assert round(verdict.deflated.deflated_sharpe, 6) == 0.998293


def test_the_worked_example_at_twenty_trials_equals_the_hand_computation() -> None:
    verdict = promotion_verdict(example_holds(), 20)
    assert round(verdict.confidence, 6) == 0.9975
    assert round(verdict.quantile, 6) == 4.145789  # type: ignore[arg-type]
    assert round(verdict.lower_bound * 100, 6) == -0.811811  # type: ignore[operator]
    assert verdict.verdict == Verdict.LOWER_BOUND_NOT_ABOVE_ZERO
    assert verdict.promoted is False
    assert verdict.deflated is not None
    assert round(verdict.deflated.expected_max_sharpe, 6) == 0.633569
    assert round(verdict.deflated.deflated_sharpe, 6) == 0.906801


def test_the_docstring_states_the_numbers_the_tests_hold_the_code_to() -> None:
    """A worked example the code has drifted from is worse than none, so both are pinned."""
    text = promotion.__doc__ or ""
    for figure in (
        "0.678233", "0.547723", "2.262157", "0.465730", "4.145789", "-0.811811",
        "1.154701", "0.998293", "0.633569", "0.906801", "16 / 10 = 1.6", "30 / 10 = 3",
    ):
        assert figure in text, figure


def test_the_gamma_one_of_the_example_is_what_the_docstring_says() -> None:
    """The HAC term the example turns on, computed independently of the module."""
    values = [v / 100 for v in EXAMPLE_RETURNS]
    mean = sum(values) / len(values)
    d = [v - mean for v in values]
    gamma1 = sum(d[t] * d[t - 1] for t in range(1, len(d))) / len(d)
    assert gamma1 * 1e4 == pytest.approx(1.6, abs=1e-12)
    assert hac_standard_error(values, 1) == pytest.approx(math.sqrt(4.6e-4 / 10), abs=1e-15)


# --------------------------------------------------------------------------- #
# HAC against statsmodels, and the overlap lag
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("lag", [0, 1, 3, 7])
def test_hac_equals_statsmodels_newey_west_without_correction(lag: int) -> None:
    sm = require_module("statsmodels.api", reason="statsmodels is not installed")
    np = require_module("numpy", reason="numpy is not installed")
    generator = random.Random(20260919 + lag)
    values = [generator.gauss(0.001, 0.02) for _ in range(37)]
    fitted = sm.OLS(np.asarray(values), np.ones(len(values))).fit(
        cov_type="HAC", cov_kwds={"maxlags": lag, "use_correction": False}
    )
    assert hac_standard_error(values, lag) == pytest.approx(float(fitted.bse[0]), rel=1e-10)


def test_overlap_counts_touching_endpoints_and_nothing_else() -> None:
    assert overlap_lag([(0, 10), (20, 30)]) == 0
    assert overlap_lag([(0, 10), (10, 20)]) == 1  # closes on the tick the next opens
    assert overlap_lag([(0, 10), (11, 20)]) == 0
    # One long hold spans three short ones: it overlaps three others.
    assert overlap_lag([(0, 100), (1, 2), (10, 20), (50, 60), (200, 300)]) == 3


def test_a_hold_closing_before_it_opens_is_refused() -> None:
    with pytest.raises(ValueError, match="closes at 5, before it opens at 9"):
        overlap_lag([(9, 5)])


def test_every_hold_overlapping_every_other_gives_the_largest_lag_the_series_has() -> None:
    holds = [Hold(0, 1000, 0.01 + 0.001 * k) for k in range(12)]
    verdict = promotion_verdict(holds, 1)
    assert verdict.lag == 11
    assert verdict.se_hac is not None


def test_a_lag_outside_the_series_is_refused() -> None:
    with pytest.raises(ValueError, match=r"lag 3 is outside 0\.\.2 for 3 values"):
        hac_standard_error([0.01, 0.02, 0.03], 3)


def test_the_series_is_put_in_entry_order_before_anything_is_computed() -> None:
    holds = example_holds()
    shuffled = holds[:]
    random.Random(7).shuffle(shuffled)
    assert shuffled != holds
    assert promotion_verdict(shuffled, 20) == promotion_verdict(holds, 20)


# --------------------------------------------------------------------------- #
# The Student-t quantile
# --------------------------------------------------------------------------- #

#: `scipy.stats.t.ppf`, computed on 2026-09-19 in a scratch session (scipy is not a declared
#: dependency, so it is not imported here). The first three are also the classic table values.
PUBLISHED = (
    (0.975, 9, 2.262157162798205),
    (0.975, 1, 12.706204736174694),
    (0.975, 2, 4.302652729749462),
    (0.99875, 9, 4.145788828443257),
    (0.9999, 30, 4.23398595727206),
    (0.999975, 200, 4.145815565758617),
    (0.95, 5, 2.0150483733330233),
    (0.99999975, 45, 5.862134247649195),
)


@pytest.mark.parametrize(("p", "df", "expected"), PUBLISHED)
def test_the_t_quantile_matches_published_values(p: float, df: int, expected: float) -> None:
    assert student_t_quantile(p, df) == pytest.approx(expected, rel=1e-10)


@pytest.mark.parametrize("p", [0.5, 0.89, 1.0])
def test_the_t_quantile_refuses_outside_the_tested_domain(p: float) -> None:
    with pytest.raises(ValueError, match=r"p must be in \[0\.9, 1\)"):
        student_t_quantile(p, 9)


def test_bonferroni_widens_with_the_trial_count() -> None:
    confidence_1, q_1 = bonferroni_quantile(30, 1)
    confidence_n, q_n = bonferroni_quantile(30, 1000)
    assert confidence_1 == pytest.approx(0.95)
    assert confidence_n == pytest.approx(1 - 0.05 / 1000)
    assert q_n > q_1
    assert q_1 == pytest.approx(student_t_quantile(0.975, 29), rel=1e-15)
    assert q_n == pytest.approx(student_t_quantile(1 - 0.025 / 1000, 29), rel=1e-15)


# --------------------------------------------------------------------------- #
# Spec 139's Check When Done
# --------------------------------------------------------------------------- #

#: Fifteen non-overlapping trades whose unwidened 95% lower bound is above zero.
HAIRCUT_RETURNS = (
    0.004, -0.002, 0.006, 0.001, 0.003, -0.001, 0.005, 0.002, 0.000, 0.004, 0.003, -0.002,
    0.006, 0.001, 0.002,
)


def haircut_holds() -> list[Hold]:
    return [Hold(100 * k, 100 * k + 10, value) for k, value in enumerate(HAIRCUT_RETURNS)]


def test_an_edge_that_does_not_survive_the_ledgers_trial_count_is_rejected() -> None:
    trials = ledger_trial_count()
    assert trials > 1
    verdict = promotion_verdict(haircut_holds(), trials)
    # The unwidened 95% bound is above zero, so the rejection is the haircut's doing.
    assert verdict.mean - student_t_quantile(0.975, 14) * verdict.se_hac > 0  # type: ignore[operator]
    assert verdict.lower_bound is not None and verdict.lower_bound <= 0
    assert verdict.verdict == Verdict.LOWER_BOUND_NOT_ABOVE_ZERO
    assert verdict.promoted is False


def test_the_same_edge_at_one_trial_is_promoted() -> None:
    verdict = promotion_verdict(haircut_holds(), 1)
    assert verdict.lower_bound is not None and verdict.lower_bound > 0
    assert verdict.verdict == Verdict.PROMOTED
    assert verdict.promoted is True


def overlapping_holds() -> list[Hold]:
    """32 trades in blocks of four near-identical returns, each overlapping the next four."""
    returns = [
        (value + 0.1 * i - 1.2) / 100 for value in (3, 3, -1, 3, 2, -1, 3, 2) for i in range(4)
    ]
    return [Hold(10 * k, 10 * k + 25, value) for k, value in enumerate(returns)]


def test_overlapping_trades_significant_only_when_treated_as_independent_are_rejected() -> None:
    holds = overlapping_holds()
    verdict = promotion_verdict(holds, 1)
    assert verdict.lag == 4
    naive_lower = verdict.mean - verdict.quantile * verdict.se_naive  # type: ignore[operator]
    assert naive_lower > 0, "the fixture must look significant when trades are independent"
    assert verdict.lower_bound is not None and verdict.lower_bound <= 0
    assert verdict.verdict == Verdict.LOWER_BOUND_NOT_ABOVE_ZERO
    assert verdict.promoted is False


def test_fewer_than_ten_trades_gives_no_interval_and_no_promotion() -> None:
    holds = [Hold(100 * k, 100 * k + 10, 0.05) for k in range(9)]
    verdict = promotion_verdict(holds, 1)
    assert verdict.verdict == Verdict.TOO_FEW_TRADES
    assert verdict.promoted is False
    assert (verdict.se_hac, verdict.quantile, verdict.lower_bound) == (None, None, None)
    assert verdict.lag == 0
    assert verdict.n_trades == 9


def test_ten_trades_is_enough_for_an_interval() -> None:
    verdict = promotion_verdict(example_holds(), 1)
    assert verdict.n_trades == promotion.MIN_TRADES == 10
    assert verdict.lower_bound is not None


def test_no_trades_is_too_few_rather_than_a_crash() -> None:
    verdict = promotion_verdict([], 1)
    assert verdict.verdict == Verdict.TOO_FEW_TRADES
    assert verdict.mean is None
    assert verdict.deflated is None


def test_a_trial_count_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 1, got 0"):
        promotion_verdict(example_holds(), 0)


def test_the_deflated_sharpe_has_no_value_on_a_flat_series() -> None:
    assert deflated_sharpe_ratio([0.01] * 12, 5) is None
    assert deflated_sharpe_ratio([0.01], 5) is None


def test_a_lower_bound_of_exactly_zero_is_not_above_zero() -> None:
    """"Promote only if the lower bound is above zero": break-even trades have a lower bound
    of exactly zero (no dispersion, so no width), and zero is not above zero."""
    holds = [Hold(100 * k, 100 * k + 10, 0.0) for k in range(12)]
    verdict = promotion_verdict(holds, 1)
    assert verdict.lower_bound == 0.0
    assert verdict.promoted is False
    assert verdict.verdict == Verdict.LOWER_BOUND_NOT_ABOVE_ZERO


def test_the_deflated_sharpe_on_a_skewed_series_matches_the_formula_worked_separately() -> None:
    """The worked example has no skew, so its sign could be wrong without the example
    noticing. Here the skew is not zero and every term is recomputed from the paper's formula
    without the module's helpers."""
    values = [0.03, -0.01, -0.01, -0.01, 0.00, 0.05, -0.02, 0.01, 0.00, -0.01, 0.02]
    trials = 7
    n = len(values)
    mean = sum(values) / n
    m2 = sum((v - mean) ** 2 for v in values) / n
    g3 = (sum((v - mean) ** 3 for v in values) / n) / m2**1.5
    g4 = (sum((v - mean) ** 4 for v in values) / n) / m2**2
    sr = mean / math.sqrt(m2)
    from statistics import NormalDist

    z = NormalDist()
    gamma = 0.5772156649015329
    sr0 = math.sqrt(1 / (n - 1)) * (
        (1 - gamma) * z.inv_cdf(1 - 1 / trials) + gamma * z.inv_cdf(1 - 1 / (trials * math.e))
    )
    expected = z.cdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr**2))
    assert abs(g3) > 0.5, "the fixture must be skewed for the sign to matter"
    result = deflated_sharpe_ratio(values, trials)
    assert result is not None
    assert result.skewness == pytest.approx(g3, rel=1e-12)
    assert result.deflated_sharpe == pytest.approx(expected, rel=1e-12)


def test_the_deflated_sharpe_falls_as_trials_rise() -> None:
    values = [value / 100 for value in EXAMPLE_RETURNS]
    one = deflated_sharpe_ratio(values, 1)
    many = deflated_sharpe_ratio(values, 1000)
    assert one is not None and many is not None
    assert many.deflated_sharpe < one.deflated_sharpe
    assert many.expected_max_sharpe > 0.0
