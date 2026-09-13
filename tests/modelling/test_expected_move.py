"""The expected move, and the sign conventions that make it wrong quietly.

Everything here is a small number times another small number, which is the regime the
project has already been burned in twice: `SELECT MAX(peak_equity)` over decimal strings
returned *a* peak, plausible and too small, and a hardcoded `900` where
`timeframes.decision_bar_s` belonged returned *a* gap count, plausible and wrong. So the
tests below are about the ways this returns a number that is in range and not the right
one — a flipped stop sign, an unnormalised distribution, a timeout assumed flat.
"""

from __future__ import annotations

import pytest

from tests.conftest import require_module

moves = require_module(
    "acsoe.modelling.expected_move",
    reason="acsoe.modelling.expected_move does not exist yet",
)

TARGET = 0.03
STOP = 0.015


def move(p_target: float, p_stop: float, p_timeout: float, timeout_return: float = 0.0) -> float:
    return moves.expected_move_pct(
        p_target=p_target,
        p_stop=p_stop,
        p_timeout=p_timeout,
        target_pct=TARGET,
        stop_pct=STOP,
        mean_timeout_return=timeout_return,
    )


def test_the_arithmetic_is_the_one_the_glossary_states() -> None:
    assert move(0.5, 0.3, 0.2, -0.002) == pytest.approx(
        0.5 * 0.03 - 0.3 * 0.015 + 0.2 * -0.002
    )


def test_the_break_even_mix_is_the_one_the_invariants_predict() -> None:
    """Invariant 5: with +3% / -1.5% barriers and no timeout mass, the expected move
    turns positive above a one-in-three target rate. Pinned because it is the number a
    reader can check by hand against the invariant, and because a flipped stop sign
    moves it to zero — a value that still reads as plausible."""
    assert move(1 / 3, 2 / 3, 0.0) == pytest.approx(0.0, abs=1e-15)
    assert move(0.34, 0.66, 0.0) > 0
    assert move(0.33, 0.67, 0.0) < 0


def test_a_buy_call_is_a_strictly_positive_expected_move() -> None:
    """Nothing else. No threshold on a probability, no cut-off anybody tuned: engine 10
    `cost` applies friction afterwards and is the only place selectivity lives."""
    assert moves.is_buy_call(1e-12)
    assert not moves.is_buy_call(0.0)
    assert not moves.is_buy_call(-1e-12)


def test_the_timeout_term_is_not_assumed_flat() -> None:
    """A timeout closes at whatever the price is twelve hours later, and across this
    dataset that has a sign. Assuming zero would bias every expected move in the same
    direction — small, consistent, and exactly the kind of error that survives."""
    assert move(0.3, 0.5, 0.2, -0.004) < move(0.3, 0.5, 0.2, 0.0) < move(0.3, 0.5, 0.2, 0.004)


def test_a_negative_stop_is_refused_rather_than_added_to_the_edge() -> None:
    """The stop is given as a positive magnitude and subtracted here. A caller passing
    `-0.015` would *add* the loss, and the result would still be a plausible small
    positive number that no downstream check could question."""
    with pytest.raises(moves.ExpectedMoveError, match="positive magnitude"):
        moves.expected_move_pct(
            p_target=0.4,
            p_stop=0.4,
            p_timeout=0.2,
            target_pct=TARGET,
            stop_pct=-STOP,
            mean_timeout_return=0.0,
        )


def test_probabilities_that_do_not_sum_to_one_are_refused() -> None:
    """An unrenormalised calibrator scales every expected move by an unknown factor, and
    the ranking between candidates survives it — so the BUY/no-BUY boundary moves while
    everything still looks internally consistent."""
    with pytest.raises(moves.ExpectedMoveError, match="sum to"):
        move(0.5, 0.3, 0.05)


def test_a_probability_outside_zero_to_one_is_refused() -> None:
    with pytest.raises(moves.ExpectedMoveError, match="outside"):
        move(1.4, -0.4, 0.0)


def test_a_nan_probability_is_refused() -> None:
    """`NaN > 0` is False, so a NaN expected move would read as "not a BUY call" and the
    candidate would be dropped silently rather than blocked with a reason."""
    with pytest.raises(moves.ExpectedMoveError, match="p_target is NaN"):
        move(float("nan"), 0.5, 0.5)


def test_a_non_positive_target_is_refused() -> None:
    with pytest.raises(moves.ExpectedMoveError, match="target_pct"):
        moves.expected_move_pct(
            p_target=0.4,
            p_stop=0.4,
            p_timeout=0.2,
            target_pct=0.0,
            stop_pct=STOP,
            mean_timeout_return=0.0,
        )


def test_the_result_is_a_float_and_formats_through_repr_without_a_second_cast() -> None:
    """Engine 8 publishes this as an exact decimal string under a fixed cross-chain key.

    The probabilities are model output and are floats by nature, so the product is a
    float whatever the barriers are stored as; wrapping it in `Decimal` afterwards would
    dress a float up as an exact number. The conversion happens once, through `repr`, the
    way the labeller formats `return_pct`.
    """
    value = move(0.5, 0.3, 0.2, -0.002)
    assert isinstance(value, float)
    assert float(repr(value)) == value
