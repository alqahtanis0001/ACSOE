"""Engine 7's ranking by engine 8's expected move, computed once for both sides. Spec 144.

Operator ruling R1, 2026-09-19: engine 7 examines its filtered universe in descending order of
**the predictor's own expected move**, the number engine 10 compares against the hurdle. Not a
selected feature: it involves no search over candidates, so ranking by it chooses nothing a
study chose. Ruling R11, the same day: the ranking **skips every pair engines 13 and 8 would
refuse** — an incomplete vector, an anomaly score above the artefact's threshold, a DI above
the artefact's threshold — because the §4 grid the amendment rests on was measured that way,
and a simulation that ranked differently would no longer be described by it.

## Why this is here and not in engine 7

Engines never import each other (contract rule 3), and `modelling/` is the one package both
the engines and `research/` may import. So engine 7 calls this function, engines 13 and 8 then
re-judge the chosen pair **from scratch** exactly as they always have, and nothing either gate
decides depends on what this function said. Invariant 4 as amended in the operator's words
(spec 126 step 4) is what permits a model output to order the universe; it permits nothing
more, and this module publishes no verdict — only an order and the pairs it left out.

## Why the numbers are engine 8's by construction, and where they are not

Every step is the one the engines take, through the same functions:

* the vector is built in the **manifest's** order, macro columns from engine 6's mapping and
  the rest from engine 5's row, with ``None``, NaN and infinity read as absent — engines 8 and
  13's ``_vector`` rules, restated here because engine code cannot be imported;
* scaling is :meth:`Scaler.transform`, whose numpy and list paths are the same three cases
  in the same order;
* the anomaly score is ``-score_samples`` on the **predictor's scaler narrowed** to the
  detector's recorded inputs, as engine 13 scores it;
* the DI is :func:`modelling.di.score_many`, the batched form of engine 8's
  :func:`modelling.di.score`;
* probabilities are the booster's, through :func:`apply_calibration`, and the move is
  :func:`expected_move_pct` with the barriers engine 8 reads.

**One of those is equal within float, not bit for bit, and it is stated rather than hidden.**
Batching turns the DI's one-row matrix product into a many-row one, and BLAS may associate a
dot product differently between the two: measured, the batched DI differs from the per-row one
in the last few units in the last place (spec 137). So a pair whose DI sits within about
1e-15 of its threshold could be ranked by this function and refused by engine 8, or the
reverse. Engine 8 re-judges regardless, so the cost of that coincidence is one bar on which the
candidate is refused rather than one on which a refused pair trades. Everything else — the
scaling, the forest, the booster, the calibration, the move — is per-row arithmetic that a
batch does not reorder, and the tests hold it to engine 8's published value exactly.

Pure arithmetic over loaded artefacts. No clock, no config, no client, no ``state``: engine 7
reads the config and the state and hands the values in; the store hands the directories in.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt

from acsoe.modelling import di as di_module
from acsoe.modelling.artefacts import ArtefactError, Scaler, load_run
from acsoe.modelling.calibration import (
    CALIBRATORS_NAME,
    CalibrationError,
    IsotonicStep,
    apply_calibration,
    from_json,
)
from acsoe.modelling.expected_move import ExpectedMoveError, expected_move_pct
from acsoe.modelling.features import FEATURE_NAMES, MARKET_QUALITY_FEATURES
from acsoe.modelling.macro import macro_feature_names

__all__ = [
    "EXCLUDED_ANOMALY_INPUTS_INCOMPLETE",
    "EXCLUDED_DI_REFUSED",
    "EXCLUDED_MARKET_ANOMALOUS",
    "EXCLUDED_PREDICTION_INPUTS_INCOMPLETE",
    "RankedPair",
    "Ranking",
    "RankingArtefacts",
    "RankingError",
    "load_ranking_artefacts",
    "rank_by_expected_move",
]

#: Why a pair was left out of the ranking, in the order the chain would have refused it:
#: engine 13 runs before engine 8. Spelled as the gates' own reason codes, so a reader of
#: engine 7's published exclusions and a reader of the gates' refusals read one vocabulary.
EXCLUDED_ANOMALY_INPUTS_INCOMPLETE: Final = "anomaly_inputs_incomplete"
EXCLUDED_MARKET_ANOMALOUS: Final = "market_anomalous"
EXCLUDED_PREDICTION_INPUTS_INCOMPLETE: Final = "prediction_inputs_incomplete"
EXCLUDED_DI_REFUSED: Final = "di_refused"

#: The detector's filename, as the trainer writes it and engine 13 reads it.
_ANOMALY_MODEL_NAME: Final = "anomaly.joblib"
_DI_NAME: Final = "di.npz"
_MODEL_NAME: Final = "model.txt"


class RankingError(ValueError):
    """An artefact the ranking will not score from. Every message names which cause.

    Engine 7 turns it into ``scout_inputs_unavailable``, as for any other missing input: a
    ranking that cannot be computed is not a ranking that may fall back to another order.
    """


@dataclass(frozen=True)
class RankingArtefacts:
    """The predictor, its calibrators and DI, and the anomaly detector, loaded and verified.

    Built only by :func:`load_ranking_artefacts`, which makes the checks engines 8 and 13
    make before either predicts. Held by the caller between ticks, keyed by the two run ids.
    """

    feature_names: tuple[str, ...]
    class_order: tuple[str, ...]
    mean_timeout_return: float
    scaler: Scaler
    booster: Any
    calibrators: tuple[IsotonicStep | None, ...]
    di: di_module.DiFit
    anomaly_input_names: tuple[str, ...]
    anomaly_scaler: Scaler
    anomaly_model: Any
    anomaly_threshold: float


@dataclass(frozen=True, slots=True)
class RankedPair:
    """One pair both gates would pass, with the numbers it was ranked on."""

    pair: str
    #: A float, exactly engine 8's arithmetic. Engine 8 formats its own with
    #: ``Decimal(repr(value))``; a caller publishing this one should do the same.
    expected_move_pct: float
    p_target: float
    p_stop: float
    p_timeout: float
    di: float
    anomaly_score: float


@dataclass(frozen=True, slots=True)
class Ranking:
    """The order, and every pair left out of it with the reason.

    ``ranked`` is expected move descending, ties by pair name ascending. A pair is in exactly
    one of the two, which the tests hold.
    """

    ranked: tuple[RankedPair, ...]
    excluded: tuple[tuple[str, str], ...]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def load_ranking_artefacts(prediction_dir: Path, anomaly_dir: Path) -> RankingArtefacts:
    """Verify and load the two runs the chain would judge with.

    ``prediction_dir`` is what engine 8 loads (``models.prediction_run_id``) and
    ``anomaly_dir`` what engine 13 loads (``models.anomaly_run_id``). They are the same
    directory in every Phase 7 run and are taken separately because the two keys are.

    The refusals are engine 8's and engine 13's: every file's hash, the feature list in the
    order engine 8 rebuilds it, a ``di.npz`` fitted with its exclusion span, readable
    calibrators, a recorded ``mean_timeout_return``, a recorded anomaly threshold, and
    detector inputs that are exactly ``MARKET_QUALITY_FEATURES``. A ranking loaded from an
    artefact either gate would refuse would order the universe by numbers no gate uses.
    """
    import joblib  # type: ignore[import-untyped]
    import lightgbm as lgb

    expected = _expected_features(prediction_dir)
    try:
        loaded = load_run(prediction_dir, expected_features=expected)
    except ArtefactError as problem:
        raise RankingError(f"the prediction run is unusable: {problem}") from problem
    di_path = prediction_dir / _DI_NAME
    if not di_path.is_file():
        raise RankingError(
            f"{prediction_dir} carries no {_DI_NAME}, so no pair's DI can be scored and "
            "engine 8 would refuse every candidate"
        )
    try:
        di_fit = di_module.load(di_path)
    except di_module.DissimilarityError as problem:
        raise RankingError(f"{di_path} is unusable: {problem}") from problem
    try:
        calibrators = from_json((prediction_dir / CALIBRATORS_NAME).read_bytes())
    except (OSError, CalibrationError) as problem:
        raise RankingError(
            f"{prediction_dir} has no readable {CALIBRATORS_NAME}: {problem}"
        ) from problem
    mean_timeout = loaded.manifest.dataset.get("mean_timeout_return")
    if mean_timeout is None:
        raise RankingError(
            f"{prediction_dir} records no mean_timeout_return, so no expected move can be "
            "computed from its probabilities"
        )

    try:
        detector_run = load_run(anomaly_dir, expected_features=_manifest_features(anomaly_dir))
    except ArtefactError as problem:
        raise RankingError(f"the anomaly run is unusable: {problem}") from problem
    recorded = detector_run.manifest.extras.get("anomaly")
    if not isinstance(recorded, Mapping):
        raise RankingError(f"{anomaly_dir} carries no anomaly detector")
    threshold = recorded.get("threshold")
    if threshold is None:
        raise RankingError(
            f"{anomaly_dir} records no anomaly threshold; nothing here invents the number "
            "that decides when a market is broken"
        )
    inputs = tuple(str(name) for name in recorded.get("input_names") or ())
    if set(inputs) != set(MARKET_QUALITY_FEATURES):
        raise RankingError(
            f"{anomaly_dir}'s detector was fitted on inputs other than the market-quality "
            "features engine 13 computes"
        )
    model_path = anomaly_dir / _ANOMALY_MODEL_NAME
    if not model_path.is_file():
        raise RankingError(f"{anomaly_dir} has no {_ANOMALY_MODEL_NAME}")

    return RankingArtefacts(
        feature_names=tuple(loaded.manifest.feature_names),
        class_order=tuple(loaded.manifest.class_order),
        mean_timeout_return=float(mean_timeout),
        scaler=loaded.scaler,
        booster=lgb.Booster(model_file=str(prediction_dir / _MODEL_NAME)),
        calibrators=tuple(calibrators),
        di=di_fit,
        anomaly_input_names=inputs,
        anomaly_scaler=detector_run.scaler.subset(inputs),
        anomaly_model=joblib.load(model_path),
        anomaly_threshold=float(threshold),
    )


def _read_manifest(directory: Path) -> Mapping[str, Any]:
    path = directory / "manifest.json"
    if not path.is_file():
        raise RankingError(f"{directory} has no manifest.json")
    try:
        payload = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as problem:
        raise RankingError(f"{path} is not readable JSON: {problem}") from problem
    if not isinstance(payload, Mapping):
        raise RankingError(f"{path} is not a JSON object")
    return payload


def _expected_features(directory: Path) -> tuple[str, ...]:
    """``FEATURE_NAMES`` plus the run's macro columns, in the order engine 8 rebuilds them.

    The assets come from the manifest and the order and spelling from `modelling/macro.py`,
    so a reordered artefact is refused here as engine 8 refuses it.
    """
    dataset = _read_manifest(directory).get("dataset") or {}
    assets = list(dataset.get("macro_assets") or [])
    return (*FEATURE_NAMES, *macro_feature_names(assets))


def _manifest_features(directory: Path) -> tuple[str, ...]:
    """The run's own list, which is what engine 13 hands ``load_run``."""
    return tuple(str(name) for name in _read_manifest(directory).get("feature_names") or ())


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #


def rank_by_expected_move(
    rows: Mapping[str, Mapping[str, Any] | None],
    macro: Mapping[str, Any],
    artefacts: RankingArtefacts,
    *,
    target_pct: float,
    stop_pct: float,
) -> Ranking:
    """Order ``rows``' pairs by expected move, leaving out every pair a gate would refuse.

    :param rows: engine 5's feature row per pair, for **the pairs engine 7's filter kept** and
        no others. The universe filter is engine 7's; this function never widens it.
    :param macro: engine 6's macro columns (``state["macro_context"]["features"]``).
    :param target_pct: ``barriers.target_pct``, as engine 8 reads it.
    :param stop_pct: ``barriers.stop_pct``, as engine 8 reads it.

    Refusals are checked in chain order — engine 13's inputs and threshold, then engine 8's
    inputs and DI — and a pair is recorded against the first that refuses it. An anomaly
    score or a DI **exactly on** its threshold passes, as it does at the gates.

    Raises :class:`RankingError` when a probability set cannot describe a prediction, which
    is engine 8 raising on the same input: an unrankable universe is not an order to guess.
    """
    excluded: list[tuple[str, str]] = []
    anomaly_ok: list[tuple[str, tuple[float, ...]]] = []
    for pair in sorted(rows):
        row = rows[pair]
        vector = _vector(artefacts.anomaly_input_names, row, {})
        if vector is None:
            excluded.append((pair, EXCLUDED_ANOMALY_INPUTS_INCOMPLETE))
            continue
        anomaly_ok.append((pair, vector))

    scores = _anomaly_scores(artefacts, [vector for _pair, vector in anomaly_ok])
    predictable: list[tuple[str, tuple[float, ...], float]] = []
    for (pair, _anomaly_vector), score in zip(anomaly_ok, scores, strict=True):
        if score > artefacts.anomaly_threshold:
            excluded.append((pair, EXCLUDED_MARKET_ANOMALOUS))
            continue
        full = _vector(artefacts.feature_names, rows[pair], macro)
        if full is None:
            excluded.append((pair, EXCLUDED_PREDICTION_INPUTS_INCOMPLETE))
            continue
        predictable.append((pair, full, score))

    if not predictable:
        return Ranking(ranked=(), excluded=tuple(sorted(excluded)))

    scaled = np.asarray(
        artefacts.scaler.transform(
            np.asarray([vector for _pair, vector, _score in predictable], dtype=np.float64)
        ),
        dtype=np.float64,
    )
    di_scores = di_module.score_many(artefacts.di, scaled)
    keep = [index for index, scored in enumerate(di_scores) if not scored.refused]
    excluded.extend(
        (predictable[index][0], EXCLUDED_DI_REFUSED)
        for index, scored in enumerate(di_scores)
        if scored.refused
    )
    ranked: list[RankedPair] = []
    if keep:
        probabilities = apply_calibration(
            np.asarray(artefacts.booster.predict(scaled[keep]), dtype=np.float64),
            list(artefacts.calibrators),
        )
        for position, index in enumerate(keep):
            pair, _full, anomaly_score = predictable[index]
            by_class = dict(
                zip(
                    artefacts.class_order,
                    (float(value) for value in probabilities[position]),
                    strict=True,
                )
            )
            try:
                move = expected_move_pct(
                    p_target=by_class["target"],
                    p_stop=by_class["stop"],
                    p_timeout=by_class["timeout"],
                    target_pct=target_pct,
                    stop_pct=stop_pct,
                    mean_timeout_return=artefacts.mean_timeout_return,
                )
            except ExpectedMoveError as problem:
                raise RankingError(f"{pair}: {problem}") from problem
            ranked.append(
                RankedPair(
                    pair=pair,
                    expected_move_pct=move,
                    p_target=by_class["target"],
                    p_stop=by_class["stop"],
                    p_timeout=by_class["timeout"],
                    di=float(di_scores[index].di),
                    anomaly_score=float(anomaly_score),
                )
            )
    ranked.sort(key=lambda entry: (-entry.expected_move_pct, entry.pair))
    return Ranking(ranked=tuple(ranked), excluded=tuple(sorted(excluded)))


def _anomaly_scores(
    artefacts: RankingArtefacts, vectors: Sequence[tuple[float, ...]]
) -> list[float]:
    """``-score_samples``, larger is more anomalous: engine 13's orientation."""
    if not vectors:
        return []
    scaled = artefacts.anomaly_scaler.transform(np.asarray(vectors, dtype=np.float64))
    values: npt.NDArray[np.float64] = np.asarray(
        -artefacts.anomaly_model.score_samples(scaled), dtype=np.float64
    )
    return [float(value) for value in values]


def _vector(
    names: Sequence[str], row: Mapping[str, Any] | None, macro: Mapping[str, Any]
) -> tuple[float, ...] | None:
    """One vector in ``names`` order, or ``None`` when any value is absent.

    Engine 8's rule and engine 13's, which differ only in engine 8 also reading ``macro``:
    a name present in ``macro`` is read from it, every other name from the row.
    """
    if not isinstance(row, Mapping):
        return None
    values: list[float] = []
    for name in names:
        number = _as_float_or_none(macro.get(name) if name in macro else row.get(name))
        if number is None:
            return None
        values.append(number)
    return tuple(values)


def _as_float_or_none(value: Any) -> float | None:
    """NaN and infinity read as absent, exactly as engines 8 and 13 read them."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number
