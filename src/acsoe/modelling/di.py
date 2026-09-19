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
  set, at ``prediction.di_percentile``, where "one" is **every reference row within the
  exclusion span of the row being scored, across all pairs** (ruling of 2026-09-15,
  amending ruling 6);
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

**Leaving out the row alone is not enough, and the ruling of 2026-09-15 says so.** 78 of
the 117 columns are BTC and ETH macro features, identical for every pair on the same bar,
and the calendar columns are too; consecutive bars of one pair carry nearly identical
rolling features. So a reference row's nearest neighbours were its own moment's rows —
the same bar on other pairs, the adjacent bars on its own — and the threshold measured
**time proximity**, not distributional distance. A live candidate has no such neighbours:
it sits at least the embargo after the reference window. Measured over 405 folds, the
row-only threshold at the 0.95 percentile refused 94.7% of out-of-sample rows, and
excluding every pair within 48 bars put the reference distribution on the test one
(``docs/dataset/di-anomaly-distributions-2026-09-14.md``). So :func:`fit` excludes every
reference row whose ``decision_ts`` is within ``exclusion_s`` of the scored row's,
inclusive, and the caller passes the same span a live candidate is guaranteed:
``backtest.embargo_bars x timeframes.decision_bar_s``. **A DI fitted without the
exclusion is the defect, not a variant**, which is why :func:`load` refuses one.

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
    "score_many",
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
    #: The leave-one-out statistic for each reference row, with every row within
    #: ``exclusion_s`` of it left out.
    distribution: npt.NDArray[np.float64]
    threshold: float
    neighbours: int
    percentile: float
    #: ``decision_ts`` of every reference row, in row order: what the exclusion was
    #: measured against.
    decision_ts: npt.NDArray[np.int64]
    #: The span, in seconds, inside which reference rows were left out of one another's
    #: neighbours. Always positive; a DI without one measures time proximity.
    exclusion_s: int

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
    decision_ts: npt.NDArray[np.int64] | None = None,
    exclusion_s: int | None = None,
) -> npt.NDArray[np.float64]:
    """Mean distance from each query row to its ``neighbours`` nearest reference rows.

    With ``decision_ts`` and ``exclusion_s`` (queries being the reference itself), every
    reference row within ``exclusion_s`` of the query row's timestamp, inclusive, is set
    to infinity before the nearest are taken. The caller has checked that each row keeps
    at least ``neighbours`` finite candidates.
    """
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
        if decision_ts is not None and exclusion_s is not None:
            stamps = decision_ts[start : start + block.shape[0]]
            near = np.abs(decision_ts[None, :] - stamps[:, None]) <= exclusion_s
            distances[near] = np.inf
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
    decision_ts: Sequence[int] | npt.NDArray[np.int64],
    exclusion_s: int,
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
    :param decision_ts: one ``decision_ts`` per row, in row order.
    :param exclusion_s: the span, in seconds, inside which reference rows are left out of
        each other's neighbours, across all pairs. The caller reads it from config
        (``backtest.embargo_bars x timeframes.decision_bar_s``); **never defaulted here**,
        because a DI fitted without it measures time proximity rather than distance.
    """
    matrix = _as_matrix(reference)
    if len(identity) != matrix.shape[0]:
        raise DissimilarityError(
            f"identity has {len(identity)} entries against {matrix.shape[0]} reference "
            "rows; the identity is the proof of which rows were seen and a mismatch "
            "makes it a proof of nothing"
        )
    stamps = np.asarray(decision_ts, dtype=np.int64)
    if stamps.ndim != 1 or stamps.shape[0] != matrix.shape[0]:
        raise DissimilarityError(
            f"decision_ts has shape {stamps.shape} against {matrix.shape[0]} reference "
            "rows; the exclusion is measured from each row's own timestamp, and a "
            "misaligned one excludes the wrong neighbours"
        )
    if neighbours <= 0:
        raise DissimilarityError("neighbours must be positive")
    if matrix.shape[0] <= neighbours:
        raise DissimilarityError(
            f"{matrix.shape[0]} reference rows cannot support {neighbours} neighbours "
            "with one row left out. Either the window is too short or the subsample is "
            "too small; both are a stop rather than a smaller k chosen here."
        )
    if exclusion_s <= 0:
        raise DissimilarityError(
            f"exclusion_s must be positive; got {exclusion_s!r}. Leaving out only the row "
            "itself keeps its same-moment neighbours — the same bar on every other pair, "
            "the adjacent bars on its own — so the threshold would measure time proximity "
            "rather than distance."
        )
    if not 0.0 < percentile < 1.0:
        raise DissimilarityError(
            f"percentile must be in (0, 1); got {percentile!r}. It is "
            "`prediction.di_percentile` and it is the operator's to supply."
        )
    ordered = np.sort(stamps)
    excluded = np.searchsorted(ordered, stamps + exclusion_s, side="right") - np.searchsorted(
        ordered, stamps - exclusion_s, side="left"
    )
    candidates = matrix.shape[0] - excluded
    short = int((candidates < neighbours).sum())
    if short:
        raise DissimilarityError(
            f"{short} reference rows keep fewer than {neighbours} neighbours once every "
            f"row within {exclusion_s} s of them is left out (fewest: "
            f"{int(candidates.min())}). The reference window is too short for the "
            "exclusion span; that is a stop rather than a narrower span or a smaller k "
            "chosen here."
        )

    distribution = _mean_nearest(
        matrix,
        matrix,
        neighbours=neighbours,
        exclude_self=True,
        decision_ts=stamps,
        exclusion_s=int(exclusion_s),
    )
    threshold = float(np.quantile(distribution, percentile))
    return DiFit(
        reference=matrix,
        identity=tuple(str(value) for value in identity),
        distribution=distribution,
        threshold=threshold,
        neighbours=int(neighbours),
        percentile=float(percentile),
        decision_ts=stamps,
        exclusion_s=int(exclusion_s),
    )


def score(fitted: DiFit, vector: Sequence[float] | npt.NDArray[np.float64]) -> DiScore:
    """The DI of one scaled feature vector, and whether it is above the threshold.

    Strictly greater than the threshold is a refusal. A value exactly on it is accepted,
    which is the same direction every other gate in this system rounds: the threshold is
    the last acceptable value, not the first refused one.

    No exclusion here: a scored row — a test row offline, a live candidate in engine 8 —
    is never within the span of the reference window, which is what the span was chosen
    to match.
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


def score_many(
    fitted: DiFit, rows: Sequence[Sequence[float]] | npt.NDArray[np.float64]
) -> list[DiScore]:
    """The DI of many scaled feature vectors, in row order: :func:`score` for each. Spec 137.

    Engine 7 ranks its universe by expected move and skips every pair the DI would refuse
    (rulings R1 and R11 of 2026-09-19), so it scores every universe pair on every bar. Looped
    through :func:`score` that cost 14.5 s a bar for 127 pairs against fold 404's reference;
    one call here, 0.9 s. The saving is the matrix product: :func:`_mean_nearest` computes a
    whole chunk of query rows against the reference at once, and one row at a time it
    squares and sums the entire reference again for every row.

    **The same statistic through the same function, and that is the point rather than a
    tidiness.** Engine 8 keeps :func:`score` for its one candidate, and the two must agree
    about which pairs are refused, so both call :func:`_mean_nearest`. The one numerical
    difference is that a many-row matrix product may associate a dot product differently
    from a one-row one, which moves a DI in its last few units in the last place.
    ``tests/modelling/test_di.py`` holds every value to :func:`score` at 1e-12 and every
    refusal exactly. A row within that distance of its threshold could land on the other
    side of the strict ``>``; that is inherent to any reassociation, and neither rounding has
    the better claim.

    Refuses what :func:`score` refuses, and a non-finite row by its position, because a caller
    scoring a universe needs to know which pair's vector had the hole. **It never skips one**:
    a batch that quietly dropped an unscorable row would return fewer scores than rows with
    nothing saying which were missing, and a caller aligning them against its pairs would
    misattribute every score after the gap.
    """
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.size == 0 and matrix.ndim <= 2:
        # A universe with no complete vector is not an error, and `np.asarray([])` is 1-D.
        return []
    if matrix.ndim != 2:
        raise DissimilarityError(
            f"expected a 2-D matrix of feature vectors, one per row, got shape {matrix.shape}. "
            "One vector is `score`'s job."
        )
    if matrix.shape[1] != fitted.width:
        raise DissimilarityError(
            f"the vectors have {matrix.shape[1]} features against the reference set's "
            f"{fitted.width}. The DI is scored on the same columns in the same order the "
            "predictor was trained on."
        )
    finite = np.isfinite(matrix).all(axis=1)
    if not finite.all():
        first = int(np.flatnonzero(~finite)[0])
        raise DissimilarityError(
            f"row {first} carries NaN or infinity ({int((~finite).sum())} rows do). The caller "
            "leaves an incomplete vector out rather than scoring it: a NaN compared against "
            "the threshold is False, and a refusal that silently never fires is worse than none."
        )
    values = _mean_nearest(matrix, fitted.reference, neighbours=fitted.neighbours, exclude_self=False)
    return [
        DiScore(di=float(value), threshold=fitted.threshold, refused=float(value) > fitted.threshold)
        for value in values
    ]


def save(fitted: DiFit, path: Path) -> None:
    """Write the fit to ``di.npz``, identity and exclusion span included.

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
        decision_ts=np.asarray(fitted.decision_ts, dtype=np.int64),
        exclusion_s=np.int64(fitted.exclusion_s),
    )


def load(path: Path) -> DiFit:
    """Read ``di.npz`` back, refusing one fitted without the exclusion span.

    A ``di.npz`` written before the ruling of 2026-09-15 carries no ``exclusion_s``. Its
    threshold was taken over a leave-one-out that kept every same-moment neighbour, so it
    measures time proximity and refuses nearly every live candidate. It is refused rather
    than loaded with a default span, because the threshold inside it cannot be corrected
    without refitting.
    """
    with np.load(path) as payload:
        if "exclusion_s" not in payload.files:
            raise DissimilarityError(
                f"{path.name} records no exclusion_s. It was fitted with a leave-one-out "
                "that left out only the row itself, so its threshold measures time "
                "proximity rather than distributional distance; retrain it."
            )
        exclusion_s = int(payload["exclusion_s"])
        if exclusion_s <= 0:
            raise DissimilarityError(
                f"{path.name} records exclusion_s {exclusion_s}, which is not positive. A "
                "DI whose leave-one-out excludes no span measures time proximity rather "
                "than distributional distance; retrain it."
            )
        if "decision_ts" not in payload.files:
            raise DissimilarityError(
                f"{path.name} records an exclusion span but no decision_ts, so the "
                "exclusion it claims cannot be checked against its reference rows"
            )
        joined = str(payload["identity"])
        return DiFit(
            reference=np.asarray(payload["reference"], dtype=np.float64),
            identity=tuple(joined.split("\n")) if joined else (),
            distribution=np.asarray(payload["distribution"], dtype=np.float64),
            threshold=float(payload["threshold"]),
            neighbours=int(payload["neighbours"]),
            percentile=float(payload["percentile"]),
            decision_ts=np.asarray(payload["decision_ts"], dtype=np.int64),
            exclusion_s=exclusion_s,
        )
