"""Applying a fitted calibrator: the half of calibration that live and replay must share.

LightGBM's raw multiclass output is not calibrated. An `expected_move_pct` computed from
uncalibrated probabilities is a number in the right range and the wrong size, and it lands
directly on the cost gate's hurdle — so the calibration has to be there, and it has to be
**the same calibration** in the backtest and on the tick.

**Fitting stays in `research/`; applying lives here, and the split is not arbitrary.**
Fitting happens once, offline, over a held-out tail of a training window. Applying happens
on every tick, inside an engine, and again over every out-of-sample row of every fold. That
second one is `modelling/`'s own test — "the arithmetic that must agree between live and
replay" — and the first is not.

It was written the other way first, beside the fitting in `research/training.py`, because
fitting and applying read as one job. They are not, and engine 8 would have had to
reimplement "read `calibrators.json`, interpolate, renormalise" because architecture
invariant 5 forbids it importing `research/`. The two implementations would have agreed on
almost every vector, and where they disagreed the live probability would differ from the
backtested one by a few per cent, on the input the cost gate prices a trade against.

The stored form is **two arrays per class and no pickle**. An isotonic regression is a step
function; a pickle in an artefact directory is code that runs when a model is loaded, inside
the process that places orders.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict

__all__ = [
    "CALIBRATORS_NAME",
    "CalibrationError",
    "IsotonicStep",
    "apply_calibration",
    "from_json",
    "from_sklearn",
    "to_json",
]

CALIBRATORS_NAME = "calibrators.json"

#: Probabilities are floored here before renormalising. Zero is not a probability anybody
#: should act on and it makes the log loss infinite; this is small enough to be invisible
#: in any decision and large enough to keep the arithmetic finite.
_FLOOR = 1e-9


class CalibrationError(ValueError):
    """A calibrator that cannot be read or applied. Every message names which cause."""


class IsotonicStep(BaseModel):
    """One class's fitted step function, as the two arrays `scikit-learn` exposes.

    `x` are the thresholds the fit found and `y` the calibrated value at each. Between
    them the value is linearly interpolated and outside them it is clamped, which is what
    `IsotonicRegression(out_of_bounds="clip").predict` does — asserted against the real
    thing in `tests/modelling/test_calibration.py`, because "it should be the same" is the
    claim this module exists to stop anybody having to make.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    x: tuple[float, ...]
    y: tuple[float, ...]

    def predict(self, values: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        if not self.x:
            raise CalibrationError("an isotonic step function with no thresholds")
        return np.interp(values, np.asarray(self.x), np.asarray(self.y))


def from_sklearn(fitted: Sequence[Any]) -> list[IsotonicStep | None]:
    """Convert fitted `IsotonicRegression` objects to the stored form.

    `None` for a class the fit could not learn — one whose calibration tail was entirely
    that class or entirely not. Isotonic on a constant target fits a constant, which would
    peg the class at 0 or 1 for every live prediction, so the identity is used instead and
    the manifest records that the class was not calibratable on that fold.
    """
    out: list[IsotonicStep | None] = []
    for model in fitted:
        if model is None:
            out.append(None)
            continue
        out.append(
            IsotonicStep(
                x=tuple(float(value) for value in model.X_thresholds_),
                y=tuple(float(value) for value in model.y_thresholds_),
            )
        )
    return out


def apply_calibration(
    raw: npt.NDArray[np.float64], steps: Sequence[IsotonicStep | None]
) -> npt.NDArray[np.float64]:
    """Calibrate every row of `raw` and **renormalise**.

    The renormalisation is not tidiness. Three independently calibrated probabilities do
    not sum to one, and an unrenormalised set scales every expected move by an unknown
    factor: the *ranking* between candidates survives it, so the BUY boundary moves while
    everything still looks internally consistent. `modelling.expected_move` refuses a set
    that does not sum to one, which is the assertion that keeps this line honest.
    """
    matrix = np.asarray(raw, dtype=np.float64)
    if matrix.ndim != 2:
        raise CalibrationError(f"expected a 2-D probability matrix, got shape {matrix.shape}")
    if matrix.shape[1] != len(steps):
        raise CalibrationError(
            f"{matrix.shape[1]} columns against {len(steps)} calibrators; one per class"
        )
    out = np.empty_like(matrix)
    for index, step in enumerate(steps):
        column = matrix[:, index]
        out[:, index] = column if step is None else step.predict(column)
    np.clip(out, _FLOOR, 1.0, out=out)
    return out / out.sum(axis=1, keepdims=True)


def to_json(steps: Sequence[IsotonicStep | None]) -> bytes:
    payload = [None if step is None else step.model_dump(mode="json") for step in steps]
    return json.dumps(payload, sort_keys=True).encode("utf-8") + b"\n"


def from_json(payload: bytes) -> list[IsotonicStep | None]:
    try:
        entries = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"{CALIBRATORS_NAME} is not readable JSON: {exc}") from exc
    if not isinstance(entries, list):
        raise CalibrationError(f"{CALIBRATORS_NAME} is not a list, one entry per class")
    return [None if entry is None else IsotonicStep.model_validate(entry) for entry in entries]
