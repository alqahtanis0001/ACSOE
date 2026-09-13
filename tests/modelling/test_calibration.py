"""`modelling/calibration.py` — the half of calibration that live and replay must share.

The central test is :func:`test_the_stored_step_function_reproduces_scikit_learn_exactly`.
Everything else in this file is about refusals; that one is about the reason the module
exists. `research/training.py` fits with scikit-learn and stores two arrays; engine 8 reads
those arrays and interpolates, because architecture invariant 5 forbids it importing
`research/`. If the two disagree, the live probability differs from the backtested one — and
it lands on `expected_move_pct`, which is the number the cost gate prices a trade against.

"It should be the same" is the claim this module exists to stop anybody having to make, so
it is measured rather than asserted from the documentation.
"""

from __future__ import annotations

import pytest

from tests.conftest import require_module

np = require_module("numpy", reason="numpy is not installed")
require_module("sklearn", reason="scikit-learn is not installed")
calibration = require_module(
    "acsoe.modelling.calibration", reason="acsoe.modelling.calibration does not exist yet"
)

from sklearn.isotonic import IsotonicRegression  # noqa: E402


def fitted_models(seed: int = 3, rows: int = 500) -> tuple[list[object], object]:
    """Three isotonic regressions fitted the way `research/training.py` fits them."""
    generator = np.random.default_rng(seed)
    raw = generator.uniform(0.05, 0.95, size=(rows, 3))
    models: list[object] = []
    for index in range(3):
        model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        model.fit(raw[:, index], (generator.uniform(size=rows) < raw[:, index]).astype(float))
        models.append(model)
    return models, raw


def test_the_stored_step_function_reproduces_scikit_learn_exactly() -> None:
    """The whole point of the module, measured on 200 probes per class including the ends.

    `IsotonicRegression(out_of_bounds="clip").predict` interpolates linearly between its
    thresholds and clamps outside them, which is what `np.interp` does with its default
    `left` and `right`. That they agree is checkable rather than assumable, and the probes
    deliberately run past both ends of the fitted range, because the clamping behaviour is
    the part a reimplementation gets wrong.
    """
    models, _raw = fitted_models()
    steps = calibration.from_sklearn(models)
    probes = np.concatenate(
        [np.random.default_rng(11).uniform(0.0, 1.0, size=200), np.array([-0.5, 0.0, 1.0, 1.5])]
    )
    for index, (model, step) in enumerate(zip(models, steps, strict=True)):
        assert np.max(np.abs(model.predict(probes) - step.predict(probes))) == 0.0, index


def test_applying_the_calibrators_leaves_a_distribution() -> None:
    """Three independently calibrated probabilities do not sum to one, and an
    unrenormalised set scales every expected move by an unknown factor — the ranking
    between candidates survives it, so the BUY boundary moves while everything still looks
    internally consistent."""
    models, raw = fitted_models()
    out = calibration.apply_calibration(raw, calibration.from_sklearn(models))
    assert out.shape == raw.shape
    assert np.allclose(out.sum(axis=1), 1.0)
    assert (out > 0).all()


def test_a_class_that_could_not_be_calibrated_passes_through() -> None:
    """Isotonic on a constant target fits a constant, which would peg that class at 0 or 1
    for every live prediction. The identity is used instead, and the manifest records that
    the class was not calibratable on that fold."""
    raw = np.array([[0.2, 0.3, 0.5], [0.6, 0.1, 0.3]])
    out = calibration.apply_calibration(raw, [None, None, None])
    assert np.allclose(out, raw / raw.sum(axis=1, keepdims=True))


def test_the_json_form_round_trips_and_carries_no_pickle() -> None:
    """A pickle in an artefact directory is code that runs when a model is loaded, inside
    the process that places orders. An isotonic regression is a step function, and a step
    function is two arrays."""
    models, _raw = fitted_models()
    steps = calibration.from_sklearn(models)
    payload = calibration.to_json(steps)
    assert calibration.from_json(payload) == steps
    assert b"pickle" not in payload
    assert payload.endswith(b"\n")


def test_a_probability_matrix_of_the_wrong_width_is_refused() -> None:
    models, _raw = fitted_models()
    steps = calibration.from_sklearn(models)
    with pytest.raises(calibration.CalibrationError, match="one per class"):
        calibration.apply_calibration(np.zeros((4, 2)), steps)


def test_a_one_dimensional_input_is_refused() -> None:
    models, _raw = fitted_models()
    with pytest.raises(calibration.CalibrationError, match="2-D"):
        calibration.apply_calibration(np.zeros(3), calibration.from_sklearn(models))


def test_malformed_json_is_refused_by_message() -> None:
    with pytest.raises(calibration.CalibrationError, match="not readable JSON"):
        calibration.from_json(b"{")
    with pytest.raises(calibration.CalibrationError, match="not a list"):
        calibration.from_json(b'{"x": 1}')
