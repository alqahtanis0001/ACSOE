"""The expected move a BUY call is decided on, computed once for both sides.

The predictor does not predict price. It predicts which of three barriers price touches
first, and the expected move is what turns those three probabilities back into a number
the cost gate can price against friction:

.. code-block:: text

    expected_move_pct = p_target * target_pct
                      - p_stop   * stop_pct
                      + p_timeout * mean_timeout_return

``mean_timeout_return`` is the mean ``return_pct`` of the **timeout** rows in the fold's
own training window, and it is a measured number rather than zero. A timeout is not a
flat outcome: the position is closed at whatever the price is twelve hours later, and
across this dataset that has a sign. Assuming zero would bias every expected move in the
same direction, which is the kind of error that survives because it is small and
consistent.

A **BUY call** is ``expected_move_pct > 0``, before friction. Nothing else: no threshold
on a probability, no cut-off anybody tuned. Engine 10 `cost` applies friction afterwards
and is the thing that decides whether the trade pays for itself — invariant 5 — and this
number is deliberately the naive one so that the gate is the only place selectivity
lives.

The same function serves `research/training.py` and engine 8 `prediction`, because a
BUY call in the backtest and a BUY call live have to be the same event. If the trainer
computed this one way and the engine another, every skeptic training row would be
selected by a rule the live loop does not use.

**Floats in, float out, and the string conversion happens once at the caller.** The
probabilities are model output and are floats by nature, so the product is a float
whatever the barriers are stored as; wrapping the result in ``Decimal`` afterwards would
dress up a float as an exact number. Engine 8 formats it with ``repr`` at the ``state``
boundary, the way the labeller formats ``return_pct``, and nothing casts it twice.
"""

from __future__ import annotations

__all__ = ["ExpectedMoveError", "expected_move_pct", "is_buy_call"]


class ExpectedMoveError(ValueError):
    """Inputs that cannot describe a three-barrier prediction."""


#: How far the three probabilities may sum from 1.0 before this is not a distribution.
#: Generous enough for float noise through a calibrator and a renormalisation, tight
#: enough that two classes summing to 1 with a third left at zero is caught.
_SUM_TOLERANCE = 1e-6


def expected_move_pct(
    *,
    p_target: float,
    p_stop: float,
    p_timeout: float,
    target_pct: float,
    stop_pct: float,
    mean_timeout_return: float,
) -> float:
    """The expected move before friction, as a decimal fraction (``0.012`` is 1.2%).

    :param target_pct: ``barriers.target_pct``, positive (``0.03``).
    :param stop_pct: ``barriers.stop_pct``, given **positive** (``0.015``) and
        subtracted here. A caller passing a negative stop would add the loss to the
        expected move, and the result would still look like a plausible small number —
        which is why the sign is asserted rather than assumed.
    """
    for name, value in (
        ("p_target", p_target),
        ("p_stop", p_stop),
        ("p_timeout", p_timeout),
    ):
        if value != value:
            raise ExpectedMoveError(f"{name} is NaN")
        if not 0.0 <= value <= 1.0:
            raise ExpectedMoveError(f"{name} is {value!r}, outside [0, 1]")
    total = p_target + p_stop + p_timeout
    if abs(total - 1.0) > _SUM_TOLERANCE:
        raise ExpectedMoveError(
            f"the three probabilities sum to {total!r}, not 1.0. They are one "
            "distribution over which barrier is touched first; a set that does not sum "
            "to one is a calibrator that was not renormalised, and the expected move "
            "computed from it is scaled by an unknown factor."
        )
    if target_pct <= 0:
        raise ExpectedMoveError(f"target_pct must be positive; got {target_pct!r}")
    if stop_pct <= 0:
        raise ExpectedMoveError(
            f"stop_pct must be given as a positive magnitude; got {stop_pct!r}. It is "
            "subtracted here, so a negative value would turn the stop into a gain."
        )
    if mean_timeout_return != mean_timeout_return:
        raise ExpectedMoveError("mean_timeout_return is NaN")
    return p_target * target_pct - p_stop * stop_pct + p_timeout * mean_timeout_return


def is_buy_call(move_pct: float) -> bool:
    """A BUY call is a positive expected move. Strictly positive: zero is not an edge."""
    return move_pct > 0.0
