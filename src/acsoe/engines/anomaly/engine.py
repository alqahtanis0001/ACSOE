"""Engine 13 `anomaly` — is the candidate's market broken. Spec 72.

A **data-quality** gate, protected by invariant 4 the same way `data_guard` is: it can only
veto. There is no output of this engine that makes a trade more likely, and there is no
input to it that says anything about whether the trade is good.

## What it cannot see, and why that is structural

`contracts.py` names `state["scout"]` and `state["feature"]` and nothing else. It does not
name `state["prediction"]`, so this engine could not read a probability if it wanted to —
contract rule 3 means an engine has no way to reach another engine's keys except by naming
them. A gate that could see the prediction would be a gate with an opinion about the trade,
which is exactly the thing invariant 4 keeps out of the gate chain.

It reads the market-quality features only: velocity, volume and trade-count z-scores, range
measures and the lookback fill. **No spread.** `trading-invariants.md` describes this
engine's inputs as velocity, volume and spread; the historical archive is OHLCVT and carries
no book, so the detector was never fitted on one and reading a live spread here would score
a live vector against a model that has never seen that column.

## The threshold is the artefact's, and the artefact's is the operator's

Nothing is learned or adapted live. The threshold was computed at training time as the
`anomaly.threshold_percentile` quantile of that fold's own training scores, and that key is
absent from `config/default.yaml` by ruling. A run trained without it records no threshold,
and this engine blocks with `anomaly_unavailable` rather than inventing one: a data-quality
gate that cannot tell a broken market from an ordinary one has no basis for letting anything
through.

## The score's direction

Larger is more anomalous, and above the threshold is a block. The artefact records that
orientation in its own manifest. A sign that flipped between the two would produce a gate
that blocks exactly the ordinary markets and passes the broken ones, with a refusal rate that
looks entirely reasonable.
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
from acsoe.engines.anomaly.contracts import (
    FEATURE_BAR_TS_FIELD,
    FEATURE_KEY,
    FEATURE_PAIRS_FIELD,
    KEY_ANOMALY_RUN_ID,
    REASON_INPUTS_INCOMPLETE,
    REASON_MARKET_ANOMALOUS,
    REASON_UNAVAILABLE,
    SCOUT_CANDIDATE_FIELD,
    SCOUT_KEY,
    STATE_KEY,
    AnomalyState,
)

#: The filename the trainer writes the detector under. The one artefact in a run directory
#: that is not a text format, because scikit-learn has no text dump for an isolation forest;
#: `load_run` verifies its sha256 before this engine unpickles it.
MODEL_NAME = "anomaly.joblib"


class AnomalyError(ValueError):
    """An artefact or an input this gate will not score from. The message names which."""


@dataclass(frozen=True)
class _Detector:
    """One loaded detector, held between ticks and keyed by the run id it was loaded for."""

    run_id: str
    input_names: tuple[str, ...]
    threshold: float
    scaler: Any
    model: Any


class AnomalyEngine(BaseEngine):
    """Gate 13. Opportunity chain, after engine 12 and before engine 15."""

    name: ClassVar[str] = STATE_KEY
    number: ClassVar[int] = 13
    is_gate: ClassVar[bool] = True

    def __init__(self) -> None:
        self._detector: _Detector | None = None

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        scout = state.get(SCOUT_KEY) or {}
        pair = scout.get(SCOUT_CANDIDATE_FIELD)
        if not pair:
            return EngineResult(
                engine=self.name,
                status=EngineStatus.PASS,
                data={},
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        features = state.get(FEATURE_KEY) or {}
        bar_ts = int(features.get(FEATURE_BAR_TS_FIELD) or 0)

        try:
            detector = self._load(context)
        except AnomalyError as problem:
            return self._blocked(started, str(pair), bar_ts, REASON_UNAVAILABLE, str(problem))

        row = (features.get(FEATURE_PAIRS_FIELD) or {}).get(pair)
        try:
            vector = _vector(detector.input_names, row)
        except AnomalyError as problem:
            return self._blocked(
                started,
                str(pair),
                bar_ts,
                REASON_INPUTS_INCOMPLETE,
                str(problem),
                model_run_id=detector.run_id,
            )

        score = _score(detector, vector)
        if score > detector.threshold:
            return self._blocked(
                started,
                str(pair),
                bar_ts,
                REASON_MARKET_ANOMALOUS,
                f"the market state scores {score:.4f} against an anomaly threshold of "
                f"{detector.threshold:.4f}. This is a judgement about the market rather "
                "than about the candidate.",
                model_run_id=detector.run_id,
                score=score,
                threshold=detector.threshold,
                anomalous=True,
            )

        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            data=AnomalyState(
                pair=str(pair),
                bar_ts=bar_ts,
                model_run_id=detector.run_id,
                score=score,
                threshold=detector.threshold,
                anomalous=False,
            ).to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------------ loading

    def _load(self, context: EngineContext) -> _Detector:
        run_id = context.config.get(KEY_ANOMALY_RUN_ID)
        if run_id is None or not str(run_id).strip():
            raise AnomalyError(
                f"{KEY_ANOMALY_RUN_ID} is not set, so there is no anomaly detector. A "
                "data-quality gate that cannot tell a broken market from an ordinary one "
                "has no basis for letting anything through."
            )
        run_id = str(run_id)
        if self._detector is not None and self._detector.run_id == run_id:
            return self._detector

        store = getattr(context.clients, "store", None)
        if store is None or not hasattr(store, "model_run_dir"):
            raise AnomalyError(
                "no store client with `model_run_dir` is available, so the artefact root "
                "cannot be located. Engine 13 never reads `models/` by path."
            )
        try:
            directory = Path(str(store.model_run_dir(run_id)))
        except Exception as problem:
            raise AnomalyError(
                f"model run {run_id!r} could not be opened: {problem}"
            ) from problem

        self._detector = _read(directory, run_id)
        return self._detector

    def _blocked(
        self,
        started: float,
        pair: str,
        bar_ts: int,
        reason_code: str,
        reason: str,
        *,
        model_run_id: str | None = None,
        score: float | None = None,
        threshold: float | None = None,
        anomalous: bool = False,
    ) -> EngineResult:
        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason=reason,
            data=AnomalyState(
                pair=pair,
                bar_ts=bar_ts,
                model_run_id=model_run_id,
                score=score,
                threshold=threshold,
                anomalous=anomalous,
                reason_code=reason_code,
            ).to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


# --------------------------------------------------------------------------- #
# Reading an artefact directory
# --------------------------------------------------------------------------- #


def _read(directory: Path, run_id: str) -> _Detector:
    """Verify and load one run's detector, or say which way it is unusable."""
    # **Permanent, by the lead's ruling of 2026-09-13, not a placeholder.** `joblib.*` is
    # deliberately not in `pyproject.toml`'s mypy overrides: this project runs
    # `warn_unused_ignores`, so an override would turn this line into an error rather than
    # remove it. Same treatment as pyarrow, and joblib is a declared dependency either way.
    import joblib  # type: ignore[import-untyped]

    from acsoe.modelling.artefacts import ArtefactError, load_run
    from acsoe.modelling.features import MARKET_QUALITY_FEATURES

    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise AnomalyError(
            f"model run {run_id!r} has no manifest.json in {directory}. On a fresh clone "
            "there is no models/ at all and blocking is the correct behaviour."
        )
    try:
        # The **run's** feature list, read from its own manifest, because this engine reads
        # only a subset of it and cannot rebuild the macro half. The check that matters here
        # is the sha256 of every file, which `load_run` does either way; the narrower list
        # below is checked against `MARKET_QUALITY_FEATURES` separately, which is the
        # assertion this engine actually depends on.
        loaded = load_run(directory, expected_features=_manifest_features(manifest_path))
    except ArtefactError as problem:
        raise AnomalyError(f"model run {run_id!r} is unusable: {problem}") from problem

    recorded = loaded.manifest.extras.get("anomaly")
    if not isinstance(recorded, Mapping):
        raise AnomalyError(
            f"model run {run_id!r} carries no anomaly detector. That fold had too few "
            "complete market-quality rows to fit one, and a detector with no model is not "
            "something to approximate."
        )
    threshold = recorded.get("threshold")
    if threshold is None:
        raise AnomalyError(
            f"model run {run_id!r} records no anomaly threshold. It was trained while "
            "`anomaly.threshold_percentile` was absent, which is the operator's key; "
            "nothing here invents the number that decides when a market is broken."
        )

    names = tuple(str(name) for name in recorded.get("input_names") or ())
    if set(names) != set(MARKET_QUALITY_FEATURES):
        raise AnomalyError(
            f"model run {run_id!r} was fitted on a different set of inputs from the market-"
            "quality features this engine computes. A vector built from one list and scored "
            "by a model fitted on another is every value in range and every value in the "
            "wrong column."
        )

    model_path = directory / MODEL_NAME
    if not model_path.is_file():
        raise AnomalyError(
            f"model run {run_id!r} has no {MODEL_NAME}, so there is nothing to score with."
        )
    return _Detector(
        run_id=run_id,
        input_names=names,
        threshold=float(threshold),
        # Narrowed here rather than at every score: the bounds for these columns and no
        # others, which is what `research/training.py` fitted on.
        scaler=loaded.scaler.subset(names),
        model=joblib.load(model_path),
    )


def _manifest_features(manifest_path: Path) -> tuple[str, ...]:
    """The run's own feature list, for `load_run`'s order check.

    Engine 8 rebuilds this list from `FEATURE_NAMES` plus the macro columns and compares,
    which is the check that catches a reordered artefact. Engine 13 cannot: it has no macro
    vector and no business having one. What it checks instead is its **own** inputs against
    `MARKET_QUALITY_FEATURES`, above, which is the list it actually builds a row from.
    """
    import json

    payload = json.loads(manifest_path.read_bytes().decode("utf-8"))
    return tuple(str(name) for name in payload.get("feature_names") or ())


def _vector(names: Sequence[str], row: Any) -> tuple[float, ...]:
    """One market-quality vector in the artefact's own order, or a refusal naming the gaps."""
    if not isinstance(row, Mapping):
        raise AnomalyError(
            "engine 5 published no feature row for this candidate, so there is nothing to "
            "judge the market by."
        )
    values: list[float] = []
    missing: list[str] = []
    for name in names:
        number = _as_float_or_none(row.get(name))
        if number is None:
            missing.append(name)
        else:
            values.append(number)
    if missing:
        raise AnomalyError(
            "the market-quality vector is incomplete: "
            + ", ".join(missing[:8])
            + (f" and {len(missing) - 8} more" if len(missing) > 8 else "")
            + ". A gate that scored a partial vector would be reporting the feature "
            "pipeline's gaps as a healthy market."
        )
    return tuple(values)


def _score(detector: _Detector, vector: Sequence[float]) -> float:
    """The anomaly score, oriented so that **larger is more anomalous**.

    `score_samples` returns the opposite, which is why the negation is here and is written
    once. The artefact's threshold was computed from negated training scores, so a sign that
    disagreed with it would block exactly the calm markets.
    """
    scaled = detector.scaler.transform([list(vector)])
    return float(-detector.model.score_samples(scaled)[0])


def _as_float_or_none(value: Any) -> float | None:
    """A feature value, with NaN and infinity read as absent.

    A NaN reaching `score_samples` raises, and a raise here would be an `ERROR` where a
    `BLOCK` is the honest answer.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number
