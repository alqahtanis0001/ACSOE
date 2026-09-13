"""Average-uniqueness sample weights, and the effective sample size beside every count.

**Twenty million labelled rows are nowhere near twenty million observations.** The
triple-barrier label at bar `t` looks forward up to 48 bars, and the label at bar `t+1`
looks forward over almost exactly the same 48 bars. Consecutive decision bars therefore
share nearly all of their outcome, and a model trained as though they were independent
draws is fitted to a handful of genuinely distinct episodes repeated hundreds of times.
It overfits, and every metric computed from those rows is confident about nothing.

The fix is the standard one and the operator confirmed it on 2026-09-12: weight each row
by how *unique* its label window is, and report the **effective sample size** — the sum
of the weights — on the same line as the row count, per fold as well as in aggregate.
A fold with 8,000 rows and an effective size of 300 is a fold whose numbers mean almost
nothing, and an aggregate figure hides exactly that fold. That per-fold requirement is
the operator's own addition to the ruling.

The arithmetic, in two steps:

1. **Concurrency.** For each bar in the series, how many labels' windows
   ``[decision_ts, label_window_end_ts]`` cover it.
2. **Uniqueness.** A row's weight is the mean of ``1 / concurrency`` over the bars of
   its own window. A row whose window nothing else overlaps weighs 1.0; a row sharing
   every bar of its window with 47 others weighs about 1/48.

Both are computed with prefix sums, so the whole thing is linear in rows after a sort —
which matters, because the real dataset is 20,331,237 rows and a quadratic version of
this is not a slow implementation, it is one that never finishes.

Nothing here reads the clock, the config or a client. Every input is an argument.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from typing import Final

__all__ = [
    "WeightError",
    "average_uniqueness",
    "concurrency",
    "effective_sample_size",
]

#: A weight can never exceed this. A row whose window overlaps nothing is one whole
#: observation and there is no such thing as more than one.
_MAX_WEIGHT: Final[float] = 1.0


class WeightError(ValueError):
    """Inputs that cannot describe label windows, said plainly rather than weighted."""


def _checked(
    decision_ts: Sequence[int], label_window_end_ts: Sequence[int]
) -> tuple[list[int], list[int]]:
    if len(decision_ts) != len(label_window_end_ts):
        raise WeightError(
            f"decision_ts has {len(decision_ts)} rows and label_window_end_ts has "
            f"{len(label_window_end_ts)}; they are two columns of one frame"
        )
    starts = [int(value) for value in decision_ts]
    ends = [int(value) for value in label_window_end_ts]
    for index, (start, end) in enumerate(zip(starts, ends, strict=True)):
        if end < start:
            raise WeightError(
                f"row {index} closes its label window at {end}, before its decision bar "
                f"at {start}. A window that ends before it opens covers no bars, and the "
                "weight it would get is a division by zero dressed up as a number."
            )
    return starts, ends


def concurrency(
    decision_ts: Sequence[int],
    label_window_end_ts: Sequence[int],
) -> tuple[list[int], list[int]]:
    """``(bars, counts)`` — how many label windows cover each distinct decision bar.

    ``bars`` is the sorted distinct ``decision_ts`` of the input, which is the grid the
    rows actually live on. Counting on that grid rather than on a synthetic contiguous
    one is deliberate: a hole in the archive is a period with no trades and therefore no
    decision bar, and counting it as an uncovered slot would inflate the uniqueness of
    every window that spans the hole — rewarding exactly the rows whose outcome is least
    observed.

    One pass with a difference array, so the cost is the sort.
    """
    starts, ends = _checked(decision_ts, label_window_end_ts)
    if not starts:
        return [], []
    bars = sorted(set(starts))
    delta = [0] * (len(bars) + 1)
    for start, end in zip(starts, ends, strict=True):
        low = bisect.bisect_left(bars, start)
        high = bisect.bisect_right(bars, end)  # exclusive
        if high <= low:
            continue
        delta[low] += 1
        delta[high] -= 1
    counts: list[int] = []
    running = 0
    for index in range(len(bars)):
        running += delta[index]
        counts.append(running)
    return bars, counts


def average_uniqueness(
    decision_ts: Sequence[int],
    label_window_end_ts: Sequence[int],
) -> list[float]:
    """One weight per row: the mean of ``1 / concurrency`` over the row's own window.

    Call it **per pair**. Two pairs' label windows overlap in wall-clock time and do not
    overlap in information — SOLUSD's next twelve hours and ADAUSD's next twelve hours
    are two observations, not one — so pooling them before counting concurrency would
    divide every weight by roughly the number of pairs and make the effective sample
    size a statement about how many pairs are listed.

    A row whose window covers no bar of the grid (possible only if the caller has
    filtered the frame after labelling it) weighs 0.0 rather than raising: it contributes
    nothing to training and nothing to the effective sample size, which is the truth
    about it.
    """
    starts, ends = _checked(decision_ts, label_window_end_ts)
    if not starts:
        return []
    bars, counts = concurrency(starts, ends)

    # Prefix sums of 1/concurrency, so a window's mean is two lookups and a division.
    prefix: list[float] = [0.0] * (len(bars) + 1)
    for index, count in enumerate(counts):
        # `count` is at least 1 for any bar inside at least one window, and a bar with a
        # count of 0 lies in none of them, so it can never be inside the slice a row
        # averages over. Guarding anyway: a zero here would be a silent inf.
        prefix[index + 1] = prefix[index] + (1.0 / count if count > 0 else 0.0)

    weights: list[float] = []
    for start, end in zip(starts, ends, strict=True):
        low = bisect.bisect_left(bars, start)
        high = bisect.bisect_right(bars, end)
        span = high - low
        if span <= 0:
            weights.append(0.0)
            continue
        weights.append(min((prefix[high] - prefix[low]) / span, _MAX_WEIGHT))
    return weights


def effective_sample_size(weights: Sequence[float]) -> float:
    """The sum of the weights: how many independent observations the rows amount to.

    Reported beside every row count, per fold and in aggregate. It is the number that
    makes an overlapping-label dataset honest about itself, and it is why a criterion
    asserting ``effective_sample_size == rows`` is asserting that the weights were never
    computed.
    """
    return float(sum(float(weight) for weight in weights))
