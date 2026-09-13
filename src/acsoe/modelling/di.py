"""The Dissimilarity Index: how far a live feature vector sits from what was trained on.

A model asked to predict on market conditions unlike anything in its training set does
not report uncertainty; it extrapolates, confidently. The DI is the refusal: measure how
far this candidate's scaled feature vector is from the reference set, and when it is
further than almost everything the model was fitted on, **do not predict**. Engine 8
turns that into a ``BLOCK`` with reason code ``di_refused`` and publishes no
``expected_move_pct``, so engine 10 fails closed on the absent key.

The reading is fixed by the operator, 2026-09-12, and is not this module's to reinterpret:

* the reference set is the **predictor's training rows for the fold**, restricted per
  pair to the last ``prediction.di_window_days`` of the training window;
* the statistic is the **mean distance to the k nearest** reference rows, Euclidean on
  MinMax-scaled features;
* the threshold is that statistic's **leave-one-out** distribution over the reference
  set, at ``prediction.di_percentile``;
* it is refitted at every weekly retrain.

**Never the skeptic's BUY subset.** Fitted on BUY rows the DI learns that "normal" means
a BUY-shaped setup and then vetoes every ordinary market state. Nothing goes red: the
veto rate is high, the few trades that survive look clean, and the leaderboard flatters
the model. That is why :func:`fit` records the **identity** of the rows it saw and why
the criterion checks identity rather than a row count — two sets of the same size are
indistinguishable by count, and on a fold where most calls are BUY they usually are.

Leave-one-out matters for the same reason a fitted threshold usually does not: scoring a
reference row against a set that contains it gives a nearest neighbour at distance zero,
which drags every statistic down and puts the threshold below where the live scores will
land. The veto then almost never fires, which looks exactly like a well-behaved model.

Pure arithmetic. No clock, no config, no client; every input is an argument.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt

__all__ = [
    "DiFit",
    "DiScore",
    "DissimilarityError",
    "fit",
    "load",
    "save",
    "score",
]

#: Rows per chunk when the pairwise distances are computed. The reference set is capped
#: by `prediction.di_reference_rows`, so this bounds peak memory rather than runtime.
_CHUNK: Final = 512


class DissimilarityError(ValueError):
    """A refusal to fit or to score. Every message names which of the several causes."""


@dataclass(frozen=True, slots=True)
class DiFit:
    """A fitted DI: what it saw, what the leave-one-out distances looked like, and where
    the line is."""

    reference: npt.NDArray[np.float64]
    #: ``(pair, decision_ts)`` of every reference row, as ``"pair|ts"``, in row order.
    #: The proof of which rows were seen, and the reason this is an artefact rather than
    #: a number.
    identity: tuple[str, ...]
    #: The leave-one-out statistic for each reference row.
    distribution: npt.NDArray[np.float64]
    threshold: float
    neighbours: int
    percentile: float

    @property
    def rows(self) -> int:
        return int(self.reference.shape[0])

    @property
    def width(self) -> int:
        return int(self.reference.shape[1])


@dataclass(frozen=True, slots=True)
class DiScore:
    di: float
    threshold: float
    refused: bool


def _as_matrix(rows: Sequence[Sequence[float]] | npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.ndim != 2:
        raise DissimilarityError(
            f"expected a 2-D matrix of scaled features, got shape {matrix.shape}"
        )
    if matrix.size and not np.isfinite(matrix).all():
        raise DissimilarityError(
            "the reference matrix carries NaN or infinity. A distance to a NaN is a NaN, "
            "and a NaN compared against a threshold is False — so an unfilled feature "
            "would silently mean 'not dissimilar' and the refusal would never fire. Drop "
            "the incomplete rows before fitting, and block on an incomplete live vector "
            "rather than scoring it."
        )
    return matrix


def _mean_nearest(
    queries: npt.NDArray[np.float64],
    reference: npt.NDArray[np.float64],
    *,
    neighbours: int,
    exclude_self: bool,
) -> npt.NDArray[np.float64]:
    """Mean distance from each query row to its ``neighbours`` nearest reference rows."""
    out = np.empty(queries.shape[0], dtype=np.float64)
    take = neighbours + (1 if exclude_self else 0)
    for start in range(0, queries.shape[0], _CHUNK):
        block = queries[start : start + _CHUNK]
        # (block, reference) Euclidean distances, computed without materialising the
        # full difference tensor.
        squared = (
            np.sum(block**2, axis=1)[:, None]
            - 2.0 * block @ reference.T
            + np.sum(reference**2, axis=1)[None, :]
        )
        np.maximum(squared, 0.0, out=squared)  # floating-point noise, not negative space
        distances = np.sqrt(squared)
        if exclude_self:
            rows = np.arange(block.shape[0])
            distances[rows, start + rows] = np.inf
        nearest = np.partition(distances, take - 1, axis=1)[:, :take]
        nearest.sort(axis=1)
        out[start : start + block.shape[0]] = nearest[:, :neighbours].mean(axis=1)
    return out


def fit(
    reference: Sequence[Sequence[float]] | npt.NDArray[np.float64],
    identity: Sequence[str],
    *,
    neighbours: int,
    percentile: float,
) -> DiFit:
    """Fit the DI on the predictor's training rows, already scaled by its scaler.

    :param reference: the scaled feature rows. Caller-supplied and caller-restricted:
        this function takes the rows it is given and records exactly which they were.
    :param identity: ``"pair|decision_ts"`` per row, in row order.
    :param neighbours: ``prediction.di_neighbours``.
    :param percentile: ``prediction.di_percentile``, in ``(0, 1)``. **Never defaulted.**
        The operator has withheld it until the walk-forward reports, and a default here
        would be this repository inventing the number that decides when a model is
        allowed to refuse a trade.
    """
    matrix = _as_matrix(reference)
    if len(identity) != matrix.shape[0]:
        raise DissimilarityError(
            f"identity has {len(identity)} entries against {matrix.shape[0]} reference "
            "rows; the identity is the proof of which rows were seen and a mismatch "
            "makes it a proof of nothing"
        )
    if neighbours <= 0:
        raise DissimilarityError("neighbours must be positive")
    if matrix.shape[0] <= neighbours:
        raise DissimilarityError(
            f"{matrix.shape[0]} reference rows cannot support {neighbours} neighbours "
            "with one row left out. Either the window is too short or the subsample is "
            "too small; both are a stop rather than a smaller k chosen here."
        )
    if not 0.0 < percentile < 1.0:
        raise DissimilarityError(
            f"percentile must be in (0, 1); got {percentile!r}. It is "
            "`prediction.di_percentile` and it is the operator's to supply."
        )

    distribution = _mean_nearest(
        matrix, matrix, neighbours=neighbours, exclude_self=True
    )
    threshold = float(np.quantile(distribution, percentile))
    return DiFit(
        reference=matrix,
        identity=tuple(str(value) for value in identity),
        distribution=distribution,
        threshold=threshold,
        neighbours=int(neighbours),
        percentile=float(percentile),
    )


def score(fitted: DiFit, vector: Sequence[float] | npt.NDArray[np.float64]) -> DiScore:
    """The DI of one scaled feature vector, and whether it is above the threshold.

    Strictly greater than the threshold is a refusal. A value exactly on it is accepted,
    which is the same direction every other gate in this system rounds: the threshold is
    the last acceptable value, not the first refused one.
    """
    row = np.asarray(vector, dtype=np.float64)
    if row.ndim != 1:
        raise DissimilarityError(f"expected one feature vector, got shape {row.shape}")
    if row.shape[0] != fitted.width:
        raise DissimilarityError(
            f"the vector has {row.shape[0]} features against the reference set's "
            f"{fitted.width}. The DI is scored on the same columns in the same order the "
            "predictor was trained on."
        )
    if not np.isfinite(row).all():
        raise DissimilarityError(
            "the feature vector carries NaN or infinity. The caller blocks on an "
            "incomplete vector; scoring one would compare a NaN against the threshold, "
            "which is False, and a refusal that silently never fires is worse than none."
        )
    value = float(
        _mean_nearest(
            row[None, :], fitted.reference, neighbours=fitted.neighbours, exclude_self=False
        )[0]
    )
    return DiScore(di=value, threshold=fitted.threshold, refused=value > fitted.threshold)


def save(fitted: DiFit, path: Path) -> None:
    """Write the fit to ``di.npz``, identity included.

    The identity array is the point of saving it at all: `di_fitted_on_predictor_training_set`
    reads it back and checks every reference row against the fold's training index. Its
    size is bounded by ``prediction.di_reference_rows``, so it costs the same order as
    the reference matrix itself.

    **Identity is stored as one newline-joined string, not as an object array**, so that
    :func:`load` never needs ``allow_pickle``. An object array in an ``.npz`` is
    unpickled on load, which is arbitrary code running inside the process that places
    orders — the same objection that keeps the scaler in JSON. A join is enough because
    an identity entry is ``"pair|decision_ts"`` and neither half can contain a newline.
    """
    if any("\n" in entry for entry in fitted.identity):
        raise DissimilarityError(
            "an identity entry contains a newline, which is the one character the joined "
            "encoding cannot carry"
        )
    np.savez_compressed(
        path,
        reference=fitted.reference,
        identity=np.array("\n".join(fitted.identity)),
        distribution=fitted.distribution,
        threshold=np.float64(fitted.threshold),
        neighbours=np.int64(fitted.neighbours),
        percentile=np.float64(fitted.percentile),
    )


def load(path: Path) -> DiFit:
    with np.load(path) as payload:
        joined = str(payload["identity"])
        return DiFit(
            reference=np.asarray(payload["reference"], dtype=np.float64),
            identity=tuple(joined.split("\n")) if joined else (),
            distribution=np.asarray(payload["distribution"], dtype=np.float64),
            threshold=float(payload["threshold"]),
            neighbours=int(payload["neighbours"]),
            percentile=float(payload["percentile"]),
        )
