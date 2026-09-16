"""Engine 8 `prediction` — the live half of the walk-forward predictor. Spec 71.

For the one candidate engine 7 chose, load the active artefact, ask the Dissimilarity
Index whether this market looks like anything the model was trained on, and only then
predict. Three calibrated probabilities, the expected move as an exact decimal string for
engine 10, the DI, and per-feature attributions.

## The order of the two model steps is the whole design

**The DI is scored before the prediction, not after it.** The alternative — predict, then
veto — was considered and rejected in the spec 59 rulings, and the reason is not
efficiency. A prediction made on a market state unlike anything in the training set is not
a weak prediction; it is a confident number produced by extrapolation, and every gate
downstream would then be reasoning about it. Scoring the DI first means the refusal is
recorded as "the model declined to answer" rather than as "the model answered and we
disagreed", which are different research findings.

**It is not a gate and it halts the tick anyway.** `is_gate` stays `False` per spec 59
decision 3 — the registry's Gate column is a declaration `verify.py` checks — while
contract rule 6 already lets any engine return `BLOCK`. A refusal here publishes **no**
`expected_move_pct` at all, so engine 10 fails closed on an absent key rather than on
anything this engine has to tell it.

**A refusal publishes no `is_buy` either, spec 95.** There are exactly two places in this
module that build a `PredictionState`: `_blocked`, which takes no `is_buy` argument and so
cannot set one, and the single `OK` return, which sets it from `is_buy_call(move)` on a
model that has already scored. That is the invariant stated as a property of the code
rather than as a rule — adding an `is_buy` parameter to `_blocked` is what would break it,
and there is no reason to.

## What it refuses, and why each is a refusal rather than a default

Everything about the artefact is checked before anything is predicted: the run id, the
directory, every file's hash, the feature list in order, the feature version, and the
presence of a DI. Any of them missing or wrong blocks with `prediction_unavailable`. That
is invariant 3 read literally — on a fresh clone there is no `models/` at all, and the
system blocking is the correct behaviour rather than an error to work around.

A null in any feature the manifest names blocks with `prediction_inputs_incomplete`. The
alternative would be to let it through as LightGBM's own NaN handling, and the reason not
to is that the *training* rows with NaN were handled by LightGBM at fit time with the rest
of the column to compare against. One live vector with a hole in it is a different thing:
nothing here can tell an unfilled lookback from a feed that stopped.

## What it never does

It never trains. It never casts a `Decimal` to a `float` or back on the way to the
expected move — the arithmetic happens once in floats and is formatted once, through
`repr`, the way `research/labelling.py` crosses the same boundary. And it never reads
`models/` by path: the directory comes from `context.clients.store.model_run_dir(run_id)`,
which is the one place that knows where artefacts live.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

from acsoe.core.contracts import (
    BaseEngine,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.engines.prediction.contracts import (
    FEATURE_BAR_TS_FIELD,
    FEATURE_KEY,
    FEATURE_PAIRS_FIELD,
    FEATURE_VERSION_FIELD,
    KEY_DI_PERCENTILE,
    KEY_PREDICTION_RUN_ID,
    MACRO_CONTEXT_KEY,
    MACRO_FEATURES_FIELD,
    REASON_DI_PERCENTILE_MISMATCH,
    REASON_DI_REFUSED,
    REASON_INPUTS_INCOMPLETE,
    REASON_UNAVAILABLE,
    SCOUT_CANDIDATE_FIELD,
    SCOUT_KEY,
    STATE_KEY,
    PredictionState,
)

#: The three barriers in the order every artefact records them. Read from the manifest's
#: own `class_order` on every tick rather than assumed, because a model trained with a
#: different order would otherwise have its stop probability read as its target one — and
#: the numbers would all be in range.
_TARGET = "target"

#: Config keys for the barrier sizes the expected move is computed from. The same two the
#: labeller used, read from config rather than from the manifest so that a change to the
#: barriers turns into a refusal at the feature-version or metric level rather than into a
#: silently rescaled expected move.
KEY_TARGET_PCT = "barriers.target_pct"
KEY_STOP_PCT = "barriers.stop_pct"


class PredictionError(ValueError):
    """An artefact or an input this engine will not predict from. The message names which."""


@dataclass(frozen=True)
class _Artefact:
    """One loaded run, held on the engine between ticks.

    Held the way a client holds its stream: loading is file I/O plus a hash of every file
    in the directory, and doing that on every 15-minute bar would be the same work for the
    same answer. Keyed by the run id it was loaded for, so pointing
    `models.prediction_run_id` at a different run reloads rather than serving the old model
    under the new id — which is the failure this cache would otherwise introduce.
    """

    run_id: str
    directory: Path
    feature_names: tuple[str, ...]
    feature_version: str
    class_order: tuple[str, ...]
    mean_timeout_return: float
    scaler: Any
    booster: Any
    calibrators: Sequence[Any]
    di: Any


class PredictionEngine(BaseEngine):
    """Engine 8. Opportunity chain, after engine 7 and before engine 10. Not a gate."""

    name: ClassVar[str] = STATE_KEY
    number: ClassVar[int] = 8
    is_gate: ClassVar[bool] = False

    def __init__(self) -> None:
        self._artefact: _Artefact | None = None
        self._explainer: Any = None

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        scout = state.get(SCOUT_KEY) or {}
        pair = scout.get(SCOUT_CANDIDATE_FIELD)
        if not pair:
            # Nothing qualified this tick. Engine 7 already returned PASS and the chain
            # stopped; there is no candidate to refuse and PASS is the honest answer.
            return EngineResult(
                engine=self.name,
                status=EngineStatus.PASS,
                data={},
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        features = state.get(FEATURE_KEY) or {}
        bar_ts = int(features.get(FEATURE_BAR_TS_FIELD) or 0)

        try:
            artefact = self._load(context)
        except PredictionError as problem:
            return self._blocked(
                started, str(pair), bar_ts, REASON_UNAVAILABLE, str(problem)
            )

        published_version = features.get(FEATURE_VERSION_FIELD)
        if published_version is not None and str(published_version) != artefact.feature_version:
            return self._blocked(
                started,
                str(pair),
                bar_ts,
                REASON_UNAVAILABLE,
                f"engine 5 published feature version {published_version!r} and model run "
                f"{artefact.run_id!r} was trained on {artefact.feature_version!r}. The two "
                "names describe different quantities; a model scored across them produces "
                "numbers that look ordinary and mean nothing.",
                model_run_id=artefact.run_id,
            )

        mismatch = _di_percentile_complaint(context, artefact)
        if mismatch is not None:
            return self._blocked(
                started,
                str(pair),
                bar_ts,
                REASON_DI_PERCENTILE_MISMATCH,
                mismatch,
                model_run_id=artefact.run_id,
                feature_version=artefact.feature_version,
                di_threshold=float(artefact.di.threshold),
            )

        row = (features.get(FEATURE_PAIRS_FIELD) or {}).get(pair)
        macro = (state.get(MACRO_CONTEXT_KEY) or {}).get(MACRO_FEATURES_FIELD) or {}
        try:
            vector = _vector(artefact.feature_names, row, macro)
        except PredictionError as problem:
            return self._blocked(
                started,
                str(pair),
                bar_ts,
                REASON_INPUTS_INCOMPLETE,
                str(problem),
                model_run_id=artefact.run_id,
                feature_version=artefact.feature_version,
            )

        import numpy as np

        from acsoe.modelling import di as di_module

        scaled = np.asarray(
            artefact.scaler.transform([list(vector)]), dtype=np.float64
        )
        di_score = di_module.score(artefact.di, scaled[0])
        if di_score.refused:
            return self._blocked(
                started,
                str(pair),
                bar_ts,
                REASON_DI_REFUSED,
                f"the market state is unlike the training set: DI {di_score.di:.4f} "
                f"against a threshold of {di_score.threshold:.4f}. The model is declining "
                "to answer rather than extrapolating.",
                model_run_id=artefact.run_id,
                feature_version=artefact.feature_version,
                di=float(di_score.di),
                di_threshold=float(di_score.threshold),
            )

        probabilities = self._probabilities(artefact, scaled)
        by_class = dict(zip(artefact.class_order, probabilities, strict=True))
        move = self._expected_move(context, artefact, by_class)

        from acsoe.modelling.expected_move import is_buy_call

        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            data=PredictionState(
                pair=str(pair),
                bar_ts=bar_ts,
                model_run_id=artefact.run_id,
                feature_version=artefact.feature_version,
                p_target=float(by_class["target"]),
                p_stop=float(by_class["stop"]),
                p_timeout=float(by_class["timeout"]),
                # Formatted once from the arithmetic, through `repr`, the way
                # `research/labelling.py` crosses the same boundary. `Decimal(float)` would
                # carry the double's full binary expansion; `Decimal(repr(...))` carries
                # the shortest decimal that round-trips, which is the number that was
                # actually computed.
                expected_move_pct=format(Decimal(repr(move)), "f"),
                is_buy=is_buy_call(move),
                di=float(di_score.di),
                di_threshold=float(di_score.threshold),
                shap=self._attributions(artefact, scaled),
            ).to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------------ loading

    def _load(self, context: EngineContext) -> _Artefact:
        """The active artefact, loaded once per run id and verified every time it is.

        Every refusal below is a `PredictionError` whose message names the cause, because
        "there is no usable model" is one fact to an operator and *which* of the six ways
        is the thing they need to act on.
        """
        run_id = context.config.get(KEY_PREDICTION_RUN_ID)
        if run_id is None or not str(run_id).strip():
            raise PredictionError(
                f"{KEY_PREDICTION_RUN_ID} is not set, so there is no active model. It is "
                "the operator's to point at a trained run; nothing in this repository may "
                "choose which model trades."
            )
        run_id = str(run_id)
        if self._artefact is not None and self._artefact.run_id == run_id:
            return self._artefact

        store = getattr(context.clients, "store", None)
        if store is None or not hasattr(store, "model_run_dir"):
            raise PredictionError(
                "no store client with `model_run_dir` is available, so the artefact root "
                "cannot be located. Engine 8 never reads `models/` by path."
            )
        try:
            directory = Path(str(store.model_run_dir(run_id)))
        except Exception as problem:
            raise PredictionError(
                f"model run {run_id!r} could not be opened: {problem}"
            ) from problem

        artefact = _read(directory, run_id)
        self._artefact = artefact
        # Dropped rather than kept: a `TreeExplainer` is built around one booster, and
        # serving the previous run's explainer beside the new run's model would attribute
        # this prediction to the wrong tree splits without anything going wrong.
        self._explainer = None
        return artefact

    # ------------------------------------------------------------------ scoring

    def _probabilities(self, artefact: _Artefact, scaled: Any) -> Sequence[float]:
        from acsoe.modelling.calibration import apply_calibration

        raw = artefact.booster.predict(scaled)
        calibrated = apply_calibration(raw, list(artefact.calibrators))
        return [float(value) for value in calibrated[0]]

    def _expected_move(
        self, context: EngineContext, artefact: _Artefact, by_class: Mapping[str, float]
    ) -> float:
        from acsoe.modelling.expected_move import expected_move_pct

        return expected_move_pct(
            p_target=by_class["target"],
            p_stop=by_class["stop"],
            p_timeout=by_class["timeout"],
            target_pct=float(context.config.get(KEY_TARGET_PCT)),
            stop_pct=float(context.config.get(KEY_STOP_PCT)),
            mean_timeout_return=artefact.mean_timeout_return,
        )

    def _attributions(self, artefact: _Artefact, scaled: Any) -> dict[str, float]:
        """Per-feature contributions to the target class, published under `data["shap"]`.

        Imported here rather than at module scope: `shap` pulls in a large dependency tree
        and engine 8 must be importable — and must be able to *block* — on a machine where
        the prediction path is never reached.

        A failure to explain is **not** a failure to predict. The attribution is a research
        output; the prediction is the decision. An exception here returns an empty mapping
        rather than turning a good prediction into a block, and the emptiness is visible in
        `state` rather than swallowed into a plausible-looking set of zeros.
        """
        try:
            import shap

            if self._explainer is None:
                self._explainer = shap.TreeExplainer(artefact.booster)
            values = self._explainer.shap_values(scaled)
        except Exception:
            return {}

        index = artefact.class_order.index(_TARGET)
        contributions = _target_class_row(values, index)
        if contributions is None or len(contributions) != len(artefact.feature_names):
            return {}
        return {
            name: float(value)
            for name, value in zip(artefact.feature_names, contributions, strict=True)
        }

    # ------------------------------------------------------------------ results

    def _blocked(
        self,
        started: float,
        pair: str,
        bar_ts: int,
        reason_code: str,
        reason: str,
        *,
        model_run_id: str | None = None,
        feature_version: str | None = None,
        di: float | None = None,
        di_threshold: float | None = None,
    ) -> EngineResult:
        """A refusal, carrying neither `expected_move_pct` nor `is_buy`.

        The reason is the operator's sentence and the code travels in `data["reason_code"]`,
        which is the arrangement engine 4 set and `console/format.py` maps.

        **There is deliberately no `is_buy` parameter here**, spec 95. Every caller is a
        path on which the model did not score, so there is no call to report; leaving the
        field off the signature means no future refusal can report one by accident, which
        is exactly how `is_buy: bool = False` came to be published on six refusal paths.
        """
        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason=reason,
            data=PredictionState(
                pair=pair,
                bar_ts=bar_ts,
                model_run_id=model_run_id,
                feature_version=feature_version,
                di=di,
                di_threshold=di_threshold,
                reason_code=reason_code,
            ).to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


# --------------------------------------------------------------------------- #
# Reading an artefact directory
# --------------------------------------------------------------------------- #


def _read(directory: Path, run_id: str) -> _Artefact:
    """Verify and load one run directory, or say which of the six ways it is unusable."""
    import lightgbm as lgb

    from acsoe.modelling import di as di_module
    from acsoe.modelling.artefacts import ArtefactError, load_run
    from acsoe.modelling.calibration import CALIBRATORS_NAME, CalibrationError, from_json
    from acsoe.modelling.features import FEATURE_NAMES
    from acsoe.modelling.macro import macro_feature_names

    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise PredictionError(
            f"model run {run_id!r} has no manifest.json in {directory}. On a fresh clone "
            "there is no models/ at all and blocking is the correct behaviour."
        )

    # The expected list is rebuilt here rather than read from the manifest, which is the
    # whole point of the check: reading the order from the artefact and then checking the
    # artefact against it would agree with anything.
    expected = _expected_features(manifest_path, FEATURE_NAMES, macro_feature_names)
    try:
        loaded = load_run(directory, expected_features=expected)
    except ArtefactError as problem:
        raise PredictionError(f"model run {run_id!r} is unusable: {problem}") from problem

    di_path = directory / "di.npz"
    if not di_path.is_file():
        raise PredictionError(
            f"model run {run_id!r} carries no di.npz, so this market cannot be compared "
            "against the training set. That run was trained while "
            "`prediction.di_percentile` was absent, which is the operator's key; engine 8 "
            "will not predict without the refusal it exists to make."
        )

    try:
        di_fit = di_module.load(di_path)
    except di_module.DissimilarityError as problem:
        # A di.npz from before the ruling of 2026-09-15 carries no exclusion span. Its
        # threshold measures time proximity and refuses nearly every candidate, and it
        # cannot be corrected without refitting, so it is no DI at all.
        raise PredictionError(
            f"model run {run_id!r} has an unusable di.npz: {problem}"
        ) from problem

    try:
        calibrators = from_json((directory / CALIBRATORS_NAME).read_bytes())
    except (OSError, CalibrationError) as problem:
        raise PredictionError(
            f"model run {run_id!r} has no readable {CALIBRATORS_NAME}: {problem}"
        ) from problem

    mean_timeout = loaded.manifest.dataset.get("mean_timeout_return")
    if mean_timeout is None:
        raise PredictionError(
            f"model run {run_id!r} records no mean_timeout_return, so the expected move "
            "cannot be computed from its probabilities."
        )

    return _Artefact(
        run_id=run_id,
        directory=directory,
        feature_names=tuple(loaded.manifest.feature_names),
        feature_version=str(loaded.manifest.feature_version),
        class_order=tuple(loaded.manifest.class_order),
        mean_timeout_return=float(mean_timeout),
        scaler=loaded.scaler,
        booster=lgb.Booster(model_file=str(directory / "model.txt")),
        calibrators=calibrators,
        di=di_fit,
    )


def _expected_features(
    manifest_path: Path, feature_names: Sequence[str], macro_names: Any
) -> tuple[str, ...]:
    """`FEATURE_NAMES` plus the macro columns this run was trained with, in order.

    The macro *assets* come from the manifest, because which assets a run used is a
    property of that run rather than of today's config — but the **order and spelling**
    come from `modelling/macro.py`, which is the module both the trainer and engine 6 build
    them from. So a run trained on a different asset set is loaded correctly, and a run
    whose feature list was reordered is refused.
    """
    import json

    payload = json.loads(manifest_path.read_bytes().decode("utf-8"))
    assets = list((payload.get("dataset") or {}).get("macro_assets") or [])
    return (*feature_names, *macro_names(assets))


def _di_percentile_complaint(context: EngineContext, artefact: _Artefact) -> str | None:
    """The sentence to block with when the config's DI percentile is not the artefact's.

    **The threshold is baked into `di.npz` and this engine never computes one.** So once a run
    has been trained at some percentile, editing `prediction.di_percentile` changes nothing
    the running system does — the engine goes on refusing at the old line while the config
    claims a new one, and the operator reads a number that is not in use. B-2's rehearsal of
    engines 13 and 8 found that, and the ruling of 2026-09-13 is that it stops the tick.

    **Only when the key is present.** Absent is the committed state and it is not a
    disagreement: it means the operator has not chosen yet and the artefact's own percentile
    stands. `None` here is "no complaint", which is why the check reads as a sentence rather
    than as a boolean — the caller needs the words either way.
    """
    configured = context.config.get(KEY_DI_PERCENTILE)
    if configured is None:
        return None
    wanted = float(configured)
    fitted = float(artefact.di.percentile)
    if wanted == fitted:
        return None
    return (
        f"{KEY_DI_PERCENTILE} is {wanted:g} and model run {artefact.run_id!r} was fitted at "
        f"{fitted:g}. The DI threshold is baked into the artefact, so changing the key does "
        "not move it: the engine would refuse at the percentile it was trained on while the "
        "config claimed another. Retrain at the percentile you want, or point "
        "`models.prediction_run_id` at a run that was."
    )


def _vector(
    names: Sequence[str], row: Any, macro: Mapping[str, Any]
) -> tuple[float, ...]:
    """One feature vector in the manifest's order, or a refusal naming what is missing.

    **The order is the manifest's, never the state row's.** A mapping has no order that
    means anything, and building the vector by iterating the published row would hand the
    model whichever order engine 5 happened to serialise — every value in range, every
    value in the wrong column, and nothing anywhere to notice.
    """
    if not isinstance(row, Mapping):
        raise PredictionError(
            "engine 5 published no feature row for this candidate, so there is nothing to "
            "predict from. The pair is in the scan set and its longest lookback is "
            "unfilled, or the feature engine did not run this bar."
        )
    values: list[float] = []
    missing: list[str] = []
    for name in names:
        raw = macro.get(name) if name in macro else row.get(name)
        number = _as_float_or_none(raw)
        if number is None:
            missing.append(name)
        else:
            values.append(number)
    if missing:
        raise PredictionError(
            "the feature vector is incomplete: "
            + ", ".join(missing[:8])
            + (f" and {len(missing) - 8} more" if len(missing) > 8 else "")
            + ". A hole in one live vector is not the NaN LightGBM handled at fit time "
            "with the rest of the column beside it; nothing here can tell an unfilled "
            "lookback from a feed that stopped."
        )
    return tuple(values)


def _as_float_or_none(value: Any) -> float | None:
    """A feature value, with NaN and infinity read as absent.

    A NaN reaching the scaler produces a NaN in the scaled vector, which `modelling.di`
    refuses by raising — and a raise here would be an `ERROR` where a `BLOCK` is the
    honest answer. So the absence is detected as an absence.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _target_class_row(values: Any, index: int) -> Sequence[float] | None:
    """The target class's contributions out of whatever shape `shap` returned.

    `shap` has returned a list of per-class arrays and a single stacked array across its
    own versions, so both are read rather than one assumed. An unrecognised shape returns
    `None` and the attribution is published empty, because a wrong-axis slice would be a
    plausible set of numbers attributing the decision to the wrong features.
    """
    import numpy as np

    if isinstance(values, list):
        if index >= len(values):
            return None
        array = np.asarray(values[index], dtype=np.float64)
        return [float(v) for v in array[0]] if array.ndim == 2 else None

    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 3:
        # (rows, features, classes) in recent shap, which is the layout the constructor
        # documents; the row axis is first in both.
        return [float(v) for v in array[0, :, index]]
    return None
