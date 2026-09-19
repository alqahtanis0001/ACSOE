"""The promotion bar and the deflated Sharpe ratio. Spec 139, fixed before any simulated figure.

Engine 20 `tournament` judges a finished run with this module, and `research/attribution.py`
may read it. It is arithmetic only: no store, no clock, no `state`, and nothing from `acsoe`
but itself, which is what lets both sides import it (architecture invariant 5).

**The statistics here were ruled on 2026-09-19 (R10, R10b) and fixed by spec 139 before any
simulated figure existed. They are not revisited after one does.** A change to any line below
that alters a verdict is a change to what "promoted" means, and it goes to the operator.

## The bar, as ruled

1. **The quantity.** Each closed trade's net return: `realised_pnl / (qty x entry_price)`.
   That is after both fees, the spread and slippage, exactly as the run recorded them.
   Liquidations count; nothing is excluded.
2. **Overlapping holds: HAC (Newey-West, Bartlett kernel)** on the per-trade series in entry
   order. For the mean of a series ``x_1..x_n`` with deviations ``d_t = x_t - mean``::

       gamma_j = (1/n) * sum_{t=j+1..n} d_t * d_{t-j}
       LRV     = gamma_0 + 2 * sum_{j=1..L} (1 - j/(L+1)) * gamma_j
       SE_HAC  = sqrt(LRV / n)

   The divisor is ``n`` throughout, with no small-sample correction: the textbook Newey-West
   estimator of the variance of a mean, and what `statsmodels` computes with
   ``cov_type="HAC", use_correction=False`` (a test holds the two equal).
3. **The lag L** is the largest number of *other* trades whose hold overlaps any single
   trade's hold. It is computed from entry and exit times alone, before any return is read, so
   it cannot be chosen after seeing the answer. Two holds overlap when each opens no later than
   the other closes, **endpoints included**: a trade closing on the tick another opens counts as
   overlapping, which can only lengthen the lag. It is at most ``n - 1`` by construction,
   which is also the largest lag at which an autocovariance exists.
4. **Widened for trials: Bonferroni over N**, N the committed trial ledger's count. The
   two-sided interval is taken at confidence ``1 - 0.05/N``, so the quantile is the Student-t
   quantile at ``1 - (0.05/N)/2`` with ``n - 1`` degrees of freedom for ``n`` trades.
5. **Promote only if** ``mean - q * SE_HAC > 0``. With fewer than ten trades there is no
   interval and no promotion, and the reason says so.

*Rejected by the spec, recorded here so nobody re-proposes them without the reason:* a block
bootstrap over clusters of overlapping trades (coarse at tens of trades, and a seed and a
resample count are further choices), and widening by the deflated Sharpe ratio's
expected-maximum offset (it needs the variance of Sharpe ratios across trials, which most
ledger rows cannot supply).

## The deflated Sharpe ratio, reported beside the verdict and never deciding it

Bailey, D. H. and Lopez de Prado, M. (2014), "The Deflated Sharpe Ratio: Correcting for
Selection Bias, Backtest Overfitting and Non-Normality", *Journal of Portfolio Management*
40(5), 94-107. With ``SR`` the per-period Sharpe ratio, ``T`` the number of periods, ``g3`` the
skewness and ``g4`` the (non-excess) kurtosis of the returns::

    SR0 = sqrt(V) * ((1 - gamma) * Z^-1(1 - 1/N) + gamma * Z^-1(1 - 1/(N e)))
    DSR = Z( (SR - SR0) * sqrt(T - 1) / sqrt(1 - g3 * SR + (g4 - 1)/4 * SR^2) )

``Z`` is the standard normal CDF, ``gamma`` the Euler-Mascheroni constant, ``e`` Euler's number
and ``N`` the trial count. ``SR0`` is the expected maximum Sharpe ratio of ``N`` trials with no
skill, and at ``N = 1`` it is zero (the formula's ``Z^-1(0)`` has no value, and the expected
maximum of one zero-skill trial is zero).

**Two inputs the paper leaves to the user, and what this module chose.** Both are stated so a
reader can disagree with them; neither can move the promotion verdict, which step 5 decides.

- *The periods are the trades.* The DSR is computed over the same per-trade net returns the
  bar judges, so ``T = n``, and the two numbers printed beside each other describe one series.
- *``V``, the variance of Sharpe ratios across the trials, is ``1 / (T - 1)``*: the variance of
  a Sharpe ratio estimate under the null of no skill. The ledger's trials are mostly counts
  and target rates rather than return series (spec 139, step 4), so the cross-trial variance
  the paper uses cannot be measured from it.

Moments are population moments (divisor ``n``), matching ``gamma_0`` above.

## A worked example, computed by hand

Ten trades, net returns in percent ``4, 3, 5, 2, 1, 0, -1, 1, 2, 3``, entered in that order.
Holds, in minutes: trade ``k`` opens at ``20 * (k // 2) + 5 * (k % 2)`` and closes ten minutes
later, so trades 0 and 1 overlap, 2 and 3 overlap, and so on, and no trade overlaps two others.

- **Lag.** Every trade overlaps exactly one other, so ``L = 1``.
- **Mean.** ``20 / 10 = 2`` percent.
- **Deviations** ``d = 2, 1, 3, 0, -1, -2, -3, -1, 0, 1``.
- ``gamma_0 = (4+1+9+0+1+4+9+1+0+1) / 10 = 30 / 10 = 3`` (percent squared).
- ``gamma_1 = (1*2 + 3*1 + 0*3 + (-1)*0 + (-2)(-1) + (-3)(-2) + (-1)(-3) + 0*(-1) + 1*0) / 10
  = 16 / 10 = 1.6``.
- ``LRV = 3 + 2 * (1 - 1/2) * 1.6 = 4.6``, so ``SE_HAC = sqrt(4.6 / 10) = sqrt(0.46)
  = 0.678233`` percent. The naive independent-trades SE would be ``sqrt(3/10) = 0.547723``.
- **At N = 1:** ``q = t_9^-1(0.975) = 2.262157``, lower bound ``2 - 2.262157 * 0.678233
  = 0.465730`` percent. **Promoted.**
- **At N = 20:** ``q = t_9^-1(1 - 0.00125) = 4.145789``, lower bound ``2 - 4.145789 * 0.678233
  = -0.811811`` percent. **Not promoted**: the edge does not survive twenty trials.
- **DSR.** Third central moment ``(8+1+27+0-1-8-27-1+0+1)/10 = 0``, so ``g3 = 0``; fourth
  ``(16+1+81+0+1+16+81+1+0+1)/10 = 19.8``, so ``g4 = 19.8 / 3^2 = 2.2``.
  ``SR = 2 / sqrt(3) = 1.154701``. ``V = 1/9``.
  At ``N = 1``: ``SR0 = 0``, ``DSR = Z(1.154701 * 3 / sqrt(1 + 1.2/4 * 4/3)) = Z(3.464102 /
  sqrt(1.4)) = Z(2.927700) = 0.998293``.
  At ``N = 20``: ``Z^-1(0.95) = 1.644854``, ``Z^-1(1 - 1/(20e)) = Z^-1(0.981606) = 2.088110``,
  ``SR0 = (1/3) * (0.422784 * 1.644854 + 0.577216 * 2.088110) = 0.633569``, ``DSR =
  Z((1.154701 - 0.633569) * 3 / sqrt(1.4)) = Z(1.321311) = 0.906801``.

`tests/modelling/test_promotion.py` holds the code to every one of these numbers.

## The Student-t quantile is computed here, not imported

`scipy` is not a dependency this project declares (`context/architecture-context.md`), so the
quantile inverts the t CDF through the regularised incomplete beta function (the continued
fraction of Numerical Recipes, section 6.4) by bisection to machine precision. A test holds it
to published values across the degrees of freedom and tail probabilities the bar will use.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist
from typing import Final

__all__ = [
    "EULER_MASCHERONI",
    "FAMILY_ALPHA",
    "MIN_TRADES",
    "DeflatedSharpe",
    "Hold",
    "PromotionVerdict",
    "Verdict",
    "bonferroni_quantile",
    "deflated_sharpe_ratio",
    "hac_standard_error",
    "overlap_lag",
    "promotion_verdict",
    "student_t_quantile",
]

#: The family-wise error rate the ruling names: a 95% interval, before the trial haircut.
FAMILY_ALPHA: Final = 0.05

#: Below this many trades there is no interval and no promotion (spec 139, step 4).
MIN_TRADES: Final = 10

EULER_MASCHERONI: Final = 0.5772156649015329


class Verdict:
    """What the bar concluded. Plain strings, so engine 20 maps them to its reason codes."""

    PROMOTED: Final = "promoted"
    TOO_FEW_TRADES: Final = "too_few_trades"
    LOWER_BOUND_NOT_ABOVE_ZERO: Final = "lower_bound_not_above_zero"


@dataclass(frozen=True, slots=True)
class Hold:
    """One closed trade, as the bar sees it: when it was held and what it netted."""

    opened_at: int
    closed_at: int
    net_return: float


@dataclass(frozen=True, slots=True)
class DeflatedSharpe:
    sharpe: float
    skewness: float
    kurtosis: float
    expected_max_sharpe: float
    deflated_sharpe: float


@dataclass(frozen=True, slots=True)
class PromotionVerdict:
    """Everything the bar computed, whatever it decided.

    ``lag`` is step 3's, computed from the holds' times whatever the trade count. Every
    interval field is ``None`` below ten trades.
    """

    verdict: str
    promoted: bool
    n_trades: int
    n_trials: int
    mean: float | None
    lag: int
    se_hac: float | None
    se_naive: float | None
    confidence: float
    quantile: float | None
    lower_bound: float | None
    deflated: DeflatedSharpe | None


# --------------------------------------------------------------------------- #
# Overlap and HAC
# --------------------------------------------------------------------------- #


def overlap_lag(holds: Sequence[tuple[int, int]]) -> int:
    """The largest number of other holds overlapping any one hold. Times only, no returns.

    Endpoints count as overlapping: ``a`` and ``b`` overlap when ``a.open <= b.close`` and
    ``b.open <= a.close``. Quadratic, which is nothing at the tens to hundreds of trades a run
    produces, and it has no sort order to get wrong.
    """
    worst = 0
    for index, (opened, closed) in enumerate(holds):
        if closed < opened:
            raise ValueError(f"hold {index} closes at {closed}, before it opens at {opened}")
        others = sum(
            1
            for other, (o_open, o_close) in enumerate(holds)
            if other != index and opened <= o_close and o_open <= closed
        )
        worst = max(worst, others)
    return worst


def hac_standard_error(values: Sequence[float], lag: int) -> float:
    """Newey-West standard error of the mean, Bartlett kernel, divisor ``n``, no correction.

    ``lag`` must be between 0 and ``n - 1``, which step 3's lag always is.
    """
    n = len(values)
    if n < 2:
        raise ValueError(f"an HAC standard error needs two values, got {n}")
    if not 0 <= lag <= n - 1:
        raise ValueError(f"lag {lag} is outside 0..{n - 1} for {n} values")
    mean = math.fsum(values) / n
    deviations = [value - mean for value in values]
    long_run = math.fsum(d * d for d in deviations) / n
    for j in range(1, lag + 1):
        gamma = math.fsum(deviations[t] * deviations[t - j] for t in range(j, n)) / n
        long_run += 2.0 * (1.0 - j / (lag + 1)) * gamma
    # The Bartlett weights keep `long_run` non-negative, and `math.sqrt` raises on a negative
    # rather than returning a NaN, so no guard is needed here to keep a bad value out.
    return math.sqrt(long_run / n)


# --------------------------------------------------------------------------- #
# The Student-t quantile
# --------------------------------------------------------------------------- #


def _betacf(a: float, b: float, x: float) -> float:
    """The continued fraction for the incomplete beta function, modified Lentz."""
    tiny = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 10_000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-16:
            return h
    raise ArithmeticError(f"the incomplete beta fraction did not converge for a={a}, b={b}, x={x}")


def _regularised_incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _student_t_upper_tail(t: float, df: int) -> float:
    """P(T > t) for t >= 0."""
    return 0.5 * _regularised_incomplete_beta(df / 2.0, 0.5, df / (df + t * t))


def student_t_quantile(p: float, df: int) -> float:
    """The ``p`` quantile of Student's t with ``df`` degrees of freedom, for ``0.9 <= p < 1``.

    Bisection on the upper tail, which is monotone, to the resolution of a double. Only the
    upper tail is needed: the bar's interval is symmetric and its narrowest is 95%, so ``p`` is
    never below 0.975. Below 0.9 the tail sits near one half and the subtraction ``1 - p``
    costs relative precision the upper tail does not, so the domain stops where the tests
    stop rather than extend to where nobody checked it.
    """
    if df < 1:
        raise ValueError(f"degrees of freedom must be at least 1, got {df}")
    if not 0.9 <= p < 1.0:
        raise ValueError(f"p must be in [0.9, 1), got {p}")
    tail = 1.0 - p
    low, high = 0.0, 1.0
    while _student_t_upper_tail(high, df) > tail:
        high *= 2.0
        if high > 1e12:
            raise ArithmeticError(f"no t quantile found for p={p}, df={df}")
    for _ in range(200):
        middle = 0.5 * (low + high)
        if middle in (low, high):
            break
        if _student_t_upper_tail(middle, df) > tail:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


def bonferroni_quantile(n_trades: int, n_trials: int) -> tuple[float, float]:
    """``(confidence, q)``: the two-sided ``1 - 0.05/N`` interval's t quantile at ``n - 1`` df."""
    if n_trials < 1:
        raise ValueError(f"a trial count must be at least 1, got {n_trials}")
    alpha = FAMILY_ALPHA / n_trials
    return 1.0 - alpha, student_t_quantile(1.0 - alpha / 2.0, n_trades - 1)


# --------------------------------------------------------------------------- #
# The deflated Sharpe ratio
# --------------------------------------------------------------------------- #


def deflated_sharpe_ratio(values: Sequence[float], n_trials: int) -> DeflatedSharpe | None:
    """Bailey and Lopez de Prado (2014), with ``V = 1/(T-1)``. See the module docstring.

    ``None`` when it has no value: fewer than two returns, or returns with no dispersion.
    """
    if n_trials < 1:
        raise ValueError(f"a trial count must be at least 1, got {n_trials}")
    n = len(values)
    if n < 2:
        return None
    mean = math.fsum(values) / n
    deviations = [value - mean for value in values]
    m2 = math.fsum(d**2 for d in deviations) / n
    if m2 <= 0.0:
        return None
    m3 = math.fsum(d**3 for d in deviations) / n
    m4 = math.fsum(d**4 for d in deviations) / n
    skewness = m3 / m2**1.5
    kurtosis = m4 / m2**2
    sharpe = mean / math.sqrt(m2)
    normal = NormalDist()
    if n_trials == 1:
        expected_max = 0.0
    else:
        expected_max = math.sqrt(1.0 / (n - 1)) * (
            (1.0 - EULER_MASCHERONI) * normal.inv_cdf(1.0 - 1.0 / n_trials)
            + EULER_MASCHERONI * normal.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
        )
    spread = 1.0 - skewness * sharpe + (kurtosis - 1.0) / 4.0 * sharpe * sharpe
    if spread <= 0.0:
        return None
    statistic = (sharpe - expected_max) * math.sqrt(n - 1) / math.sqrt(spread)
    return DeflatedSharpe(
        sharpe=sharpe,
        skewness=skewness,
        kurtosis=kurtosis,
        expected_max_sharpe=expected_max,
        deflated_sharpe=normal.cdf(statistic),
    )


# --------------------------------------------------------------------------- #
# The verdict
# --------------------------------------------------------------------------- #


def promotion_verdict(holds: Sequence[Hold], n_trials: int) -> PromotionVerdict:
    """Apply the bar. ``holds`` in any order; they are put in entry order here.

    Entry order is ``(opened_at, closed_at)``; ties beyond that keep the caller's order, so a
    caller that passes rows in `trade_id` order gets a reproducible series.
    """
    if n_trials < 1:
        raise ValueError(f"a trial count must be at least 1, got {n_trials}")
    ordered = sorted(holds, key=lambda hold: (hold.opened_at, hold.closed_at))
    lag = overlap_lag([(hold.opened_at, hold.closed_at) for hold in ordered])
    returns = [hold.net_return for hold in ordered]
    n = len(returns)
    confidence = 1.0 - FAMILY_ALPHA / n_trials
    deflated = deflated_sharpe_ratio(returns, n_trials)
    if n < MIN_TRADES:
        return PromotionVerdict(
            verdict=Verdict.TOO_FEW_TRADES,
            promoted=False,
            n_trades=n,
            n_trials=n_trials,
            mean=(math.fsum(returns) / n) if n else None,
            lag=lag,
            se_hac=None,
            se_naive=None,
            confidence=confidence,
            quantile=None,
            lower_bound=None,
            deflated=deflated,
        )
    mean = math.fsum(returns) / n
    se_hac = hac_standard_error(returns, lag)
    se_naive = hac_standard_error(returns, 0)
    _, quantile = bonferroni_quantile(n, n_trials)
    lower = mean - quantile * se_hac
    promoted = lower > 0.0
    return PromotionVerdict(
        verdict=Verdict.PROMOTED if promoted else Verdict.LOWER_BOUND_NOT_ABOVE_ZERO,
        promoted=promoted,
        n_trades=n,
        n_trials=n_trials,
        mean=mean,
        lag=lag,
        se_hac=se_hac,
        se_naive=se_naive,
        confidence=confidence,
        quantile=quantile,
        lower_bound=lower,
        deflated=deflated,
    )
