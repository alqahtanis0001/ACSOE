"""Engine 15 `skeptic` — the last gate, and it can only say no. Spec 73.

A learned opinion about this specific trade: how likely is the predictor's BUY call to be
wrong. Above `skeptic.veto_threshold` the call is vetoed.

## It can only veto, and that is structural rather than careful

There is no output of this engine that makes a trade more likely. `SkepticState` publishes
`p_wrong`, `threshold` and `vetoed`, and nothing else; there is no `approved`, no confidence
and no margin a downstream engine could widen a threshold with. Invariant 4 — a model output
may refuse a trade and may never authorise one — and the reason it is written into the
published shape rather than into a rule is that a rule is a thing somebody can forget.

The training path is held to the same line: `research/training.py` produces a probability of
being **wrong**, and the only thing an engine can do with that is refuse.

## It reads the prediction, and engine 13 must not

The two gates are deliberate opposites. The skeptic's whole job is to grade the predictor's
own call, so it must see the call. The anomaly gate judges whether the *market* is broken and
must not see the call, or it becomes a second opinion about the trade wearing a data-quality
badge. Each engine's contracts module names exactly what it is allowed to reach.

## A non-BUY call is `OK`, not a block

The skeptic grades BUY calls. Asked about a call nobody made, it is answering a different
question, so it returns `OK` with `vetoed: false` and says why in `data`. **Turning a non-BUY
into no trade is the decision engine's job in Phase 6.** A `BLOCK` here would write a veto
into the one table the research reads that never happened, and the leaderboard would then
attribute to the skeptic every bar the predictor simply did not like.

**Only an explicit `is_buy: false` is a non-BUY call.** An absent, `None` or non-boolean
`is_buy` blocks with `skeptic_unavailable`: engine 8 published no usable verdict, and reading
that as "not a BUY" is absence of a "no" taken as a yes. Invariant 3. With no candidate pair
at all the engine still returns `PASS` — there is nothing on this tick to grade.

## A non-finite score blocks

`p_wrong` that is NaN or infinite blocks with `skeptic_unavailable` before it is compared.
`nan > threshold` is `False`, so without the check a model that returned nonsense would pass
every call.

## The threshold is the operator's

`skeptic.veto_threshold` is absent from `config/default.yaml` by ruling until the
walk-forward reports. Absent, this gate blocks with `skeptic_unavailable` naming the key —
it does not pass. A learned veto with no threshold cannot tell a bad call from a good one,
and failing open would mean the one gate meant to catch the predictor's mistakes was the one
gate not running.

## It never learns

Nothing here trains, adapts, or reads the store for outcomes. The model is the artefact's and
the threshold is the artefact's manifest plus the operator's config. Live learning is out of
scope for this phase and would make every leaderboard row a statement about a model that no
longer exists.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from acsoe.core.contracts import (
    BaseEngine,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.engines.skeptic.contracts import (
    FEATURE_KEY,
    FEATURE_PAIRS_FIELD,
    KEY_SKEPTIC_RUN_ID,
    KEY_VETO_THRESHOLD,
    MACRO_CONTEXT_KEY,
    MACRO_FEATURES_FIELD,
    NOT_A_BUY_CALL,
    PREDICTION_EXPECTED_MOVE_FIELD,
    PREDICTION_IS_BUY_FIELD,
    PREDICTION_KEY,
    PREDICTION_PAIR_FIELD,
    PREDICTION_PROBABILITY_FIELDS,
    REASON_UNAVAILABLE,
    REASON_VETO,
    SCOUT_CANDIDATE_FIELD,
    SCOUT_KEY,
    STATE_KEY,
    SkepticState,
)

#: The filename `research/training.py` writes the skeptic under. Text rather than a pickle,
#: for the reason the predictor is: a pickle in an artefact directory is code that runs when
#: a model is loaded, inside the process that places orders.
MODEL_NAME = "skeptic.txt"

#: The index of the "wrong" class in the skeptic's own output. The label is
#: `wrong = label != "target"`, fitted as a binary LightGBM objective, so a booster's single
#: column is the probability of the positive class — which is *wrong*, not right.
_WRONG = 1


class SkepticError(ValueError):
    """An artefact or an input this gate will not judge from. The message names which."""


@dataclass(frozen=True)
class _Skeptic:
    """One loaded skeptic, held between ticks and keyed by the run id it was loaded for."""

    run_id: str
    input_names: tuple[str, ...]
    feature_names: tuple[str, ...]
    scaler: Any
    booster: Any


class SkepticEngine(BaseEngine):
    """Gate 15. Opportunity chain, the last gate before the decision."""

    name: ClassVar[str] = STATE_KEY
    number: ClassVar[int] = 15
    is_gate: ClassVar[bool] = True

    def __init__(self) -> None:
        self._skeptic: _Skeptic | None = None

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        prediction = state.get(PREDICTION_KEY) or {}
        scout = state.get(SCOUT_KEY) or {}
        pair = prediction.get(PREDICTION_PAIR_FIELD) or scout.get(SCOUT_CANDIDATE_FIELD)
        if not pair:
            return EngineResult(
                engine=self.name,
                status=EngineStatus.PASS,
                data={},
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        is_buy = prediction.get(PREDICTION_IS_BUY_FIELD)
        if not isinstance(is_buy, bool):
            # Absent, None, or not a boolean at all: engine 8 did not say whether this was a
            # BUY. Read as "not a BUY", that would be absence of a "no" taken as a pass.
            return self._blocked(
                started,
                str(pair),
                REASON_UNAVAILABLE,
                f"engine 8 published no usable BUY verdict for this candidate "
                f"({PREDICTION_KEY}.{PREDICTION_IS_BUY_FIELD} is {is_buy!r}), so there is no "
                "call to grade and no way to know there was none.",
            )
        if is_buy is False:
            # Not a block. The skeptic grades BUY calls and has no opinion about the rest;
            # the decision engine in Phase 6 is what turns a non-BUY into no trade. A veto
            # recorded here would be one the skeptic never made.
            return EngineResult(
                engine=self.name,
                status=EngineStatus.OK,
                blocks_trading=False,
                data=SkepticState(
                    pair=str(pair), vetoed=False, reason=NOT_A_BUY_CALL
                ).to_state(),
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        threshold = context.config.get(KEY_VETO_THRESHOLD)
        if threshold is None:
            return self._blocked(
                started,
                str(pair),
                REASON_UNAVAILABLE,
                f"{KEY_VETO_THRESHOLD} is not set, so there is no line at which a call is "
                "refused. It is the operator's after the walk-forward reports; failing open "
                "would mean the gate meant to catch the predictor's mistakes is the one gate "
                "not running.",
            )

        try:
            skeptic = self._load(context)
        except SkepticError as problem:
            return self._blocked(started, str(pair), REASON_UNAVAILABLE, str(problem))

        row = (state.get(FEATURE_KEY) or {}).get(FEATURE_PAIRS_FIELD) or {}
        macro = (state.get(MACRO_CONTEXT_KEY) or {}).get(MACRO_FEATURES_FIELD) or {}
        try:
            vector = _vector(skeptic, row.get(pair), macro, prediction)
        except SkepticError as problem:
            return self._blocked(
                started,
                str(pair),
                REASON_UNAVAILABLE,
                str(problem),
                model_run_id=skeptic.run_id,
            )

        p_wrong = _score(skeptic, vector)
        if not math.isfinite(p_wrong):
            # Before the comparison, because `nan > limit` is False and a NaN would pass.
            return self._blocked(
                started,
                str(pair),
                REASON_UNAVAILABLE,
                f"the skeptic returned a non-finite score ({p_wrong!r}) for this call, and a "
                "probability that is not a number cannot be held against a threshold.",
                model_run_id=skeptic.run_id,
            )
        limit = float(threshold)
        if p_wrong > limit:
            shown_p_wrong, shown_limit = _distinct(p_wrong, limit)
            return self._blocked(
                started,
                str(pair),
                REASON_VETO,
                f"the skeptic puts this call {shown_p_wrong} likely to be wrong against a veto "
                f"threshold of {shown_limit}.",
                model_run_id=skeptic.run_id,
                p_wrong=p_wrong,
                threshold=limit,
                vetoed=True,
            )

        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            data=SkepticState(
                pair=str(pair),
                model_run_id=skeptic.run_id,
                p_wrong=p_wrong,
                threshold=limit,
                vetoed=False,
            ).to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------------ loading

    def _load(self, context: EngineContext) -> _Skeptic:
        run_id = context.config.get(KEY_SKEPTIC_RUN_ID)
        if run_id is None or not str(run_id).strip():
            raise SkepticError(
                f"{KEY_SKEPTIC_RUN_ID} is not set, so there is no skeptic to judge this "
                "call with."
            )
        run_id = str(run_id)
        if self._skeptic is not None and self._skeptic.run_id == run_id:
            return self._skeptic

        store = getattr(context.clients, "store", None)
        if store is None or not hasattr(store, "model_run_dir"):
            raise SkepticError(
                "no store client with `model_run_dir` is available, so the artefact root "
                "cannot be located. Engine 15 never reads `models/` by path."
            )
        try:
            directory = Path(str(store.model_run_dir(run_id)))
        except Exception as problem:
            raise SkepticError(
                f"model run {run_id!r} could not be opened: {problem}"
            ) from problem

        self._skeptic = _read(directory, run_id)
        return self._skeptic

    def _blocked(
        self,
        started: float,
        pair: str,
        reason_code: str,
        reason: str,
        *,
        model_run_id: str | None = None,
        p_wrong: float | None = None,
        threshold: float | None = None,
        vetoed: bool = False,
    ) -> EngineResult:
        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason=reason,
            data=SkepticState(
                pair=pair,
                model_run_id=model_run_id,
                p_wrong=p_wrong,
                threshold=threshold,
                vetoed=vetoed,
                reason_code=reason_code,
            ).to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


# --------------------------------------------------------------------------- #
# Reading an artefact directory
# --------------------------------------------------------------------------- #


def _read(directory: Path, run_id: str) -> _Skeptic:
    """Verify and load one run's skeptic, or say which way it is unusable."""
    import lightgbm as lgb

    from acsoe.modelling.artefacts import ArtefactError, load_run

    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise SkepticError(
            f"model run {run_id!r} has no manifest.json in {directory}. On a fresh clone "
            "there is no models/ at all and blocking is the correct behaviour."
        )
    try:
        loaded = load_run(directory, expected_features=_manifest_features(manifest_path))
    except ArtefactError as problem:
        raise SkepticError(f"model run {run_id!r} is unusable: {problem}") from problem

    recorded = loaded.manifest.extras.get("skeptic")
    if not isinstance(recorded, Mapping):
        raise SkepticError(
            f"model run {run_id!r} carries no skeptic. Spec 69: a fold with no earlier "
            "out-of-sample BUY calls trains none, and the first fold of every run is such "
            "a fold. That is a reported absence, not a fault — and a gate that guessed in "
            "its place would be a coin flip with a manifest."
        )
    names = tuple(str(name) for name in recorded.get("input_names") or ())
    if not names:
        raise SkepticError(
            f"model run {run_id!r} records no skeptic input order. Engine 15 builds the same "
            "vector live and a permuted order is confident nonsense with nothing to notice "
            "it."
        )

    model_path = directory / MODEL_NAME
    if not model_path.is_file():
        raise SkepticError(
            f"model run {run_id!r} has no {MODEL_NAME}, so there is nothing to judge with."
        )
    return _Skeptic(
        run_id=run_id,
        input_names=names,
        feature_names=tuple(loaded.manifest.feature_names),
        scaler=loaded.scaler,
        booster=lgb.Booster(model_file=str(model_path)),
    )


def _manifest_features(manifest_path: Path) -> tuple[str, ...]:
    """The run's own feature list, for `load_run`'s hash and order check.

    The check that matters to this engine is that its **input order** is the manifest's,
    which is `_vector` below; `load_run`'s own order check is what verifies the artefact is
    internally consistent and every file's hash matches.
    """
    import json

    payload = json.loads(manifest_path.read_bytes().decode("utf-8"))
    return tuple(str(name) for name in payload.get("feature_names") or ())


def _vector(
    skeptic: _Skeptic, row: Any, macro: Mapping[str, Any], prediction: Mapping[str, Any]
) -> tuple[float, ...]:
    """The skeptic's input vector: scaled features, then the predictor's own call.

    **In the manifest's recorded order, never the state row's.** The trained order is
    `feature_names` followed by `p_target, p_stop, p_timeout, expected_move_pct`, and engine
    15 rebuilds exactly that. A mapping has no order that means anything, and a vector
    assembled from one would be every value in range and every value in the wrong column.

    **Assembled from two publishers**, the same two engine 8 reads: the pair's own features
    from engine 5 and the `macro_*` columns from engine 6. The skeptic's feature half is the
    predictor's *whole* feature list, because it was trained on exactly that. Looking every
    name up in the pair's row alone leaves every macro column missing and blocks every call —
    which is what this did until the spec 73 mutation sweep pointed at it.
    """
    if not isinstance(row, Mapping):
        raise SkepticError(
            "engine 5 published no feature row for this candidate, so the call cannot be "
            "judged on what the predictor saw."
        )
    features: list[float] = []
    missing: list[str] = []
    for name in skeptic.feature_names:
        number = _as_float_or_none(macro.get(name) if name in macro else row.get(name))
        if number is None:
            missing.append(name)
        else:
            features.append(number)

    extras: list[float] = []
    for name in (*PREDICTION_PROBABILITY_FIELDS, PREDICTION_EXPECTED_MOVE_FIELD):
        number = _as_float_or_none(prediction.get(name))
        if number is None:
            missing.append(name)
        else:
            extras.append(number)

    if missing:
        raise SkepticError(
            "the skeptic's input vector is incomplete: "
            + ", ".join(missing[:8])
            + (f" and {len(missing) - 8} more" if len(missing) > 8 else "")
            + ". A learned veto scored on a partial vector is a refusal nobody can explain, "
            "and failing open here would be the gate not running."
        )

    expected = (*skeptic.feature_names, *PREDICTION_PROBABILITY_FIELDS,
                PREDICTION_EXPECTED_MOVE_FIELD)
    if tuple(skeptic.input_names) != expected:
        raise SkepticError(
            f"model run {skeptic.run_id!r} records an input order this engine cannot "
            "rebuild. It is the feature list followed by the predictor's three "
            "probabilities and its expected move; anything else is a model trained on a "
            "vector nothing here can reproduce."
        )
    scaled = skeptic.scaler.transform([features])[0]
    return (*(float(value) for value in scaled), *extras)


def _score(skeptic: _Skeptic, vector: Sequence[float]) -> float:
    """The probability that the predictor's call is **wrong**.

    LightGBM's binary objective returns one column, the probability of the positive class,
    and the positive class here is `wrong = label != "target"`. A reading of this as "the
    probability the call is right" would veto exactly the good calls, at a rate that looks
    entirely plausible.
    """
    import numpy as np

    raw = skeptic.booster.predict(np.asarray([list(vector)], dtype=np.float64))
    values = np.asarray(raw, dtype=np.float64)
    if values.ndim == 2 and values.shape[1] > 1:
        return float(values[0][_WRONG])
    return float(values.reshape(-1)[0])


def _distinct(p_wrong: float, limit: float) -> tuple[str, str]:
    """The two numbers of a veto sentence, at the fewest significant digits that tell them apart.

    Six to start, more only when six would print the same string twice. A fixed `:.4f` read
    "0.0000 likely to be wrong against a veto threshold of 0.0000" on a trained fixture: a
    refusal whose own sentence cannot show that the score was above the line.
    """
    for digits in range(6, 18):
        shown = (f"{p_wrong:.{digits}g}", f"{limit:.{digits}g}")
        if shown[0] != shown[1]:
            return shown
    return repr(p_wrong), repr(limit)


def _as_float_or_none(value: Any) -> float | None:
    """A number, with NaN, infinity and booleans read as absent.

    Strings are parsed: `expected_move_pct` crosses `state` as an exact decimal string for
    engine 10's `Decimal` arithmetic, and the skeptic was trained on a float. This is the one
    place that conversion happens, and it happens through `float(str)` rather than through a
    `Decimal` round trip because the trained value was a double.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number
