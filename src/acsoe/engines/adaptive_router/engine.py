"""Engine 14 `adaptive_router` — a weight per model version, and nothing else. Spec 97.

Reads the leaderboard engine 20 `tournament` writes, weights each model version by how
far its Brier beats its own base rate, and publishes the weights with the basis for each
one. It also reports the candidate's regime and DI margin, which it does **not** use.

## It is inert today, and saying so is the point

The walk-forward trains one predictor per fold and there is one model family, so on the
real table every version has exactly one row and the weight set has one member at 1.0.
Nothing downstream reads this payload: engine 15 does not, engine 16 copies
`active_model_run_id` into the order intent as provenance and never judges it, and engine
18 places what engine 16 composed. So in the fixed registry order **nothing this engine
publishes can change whether the tick trades**, which is what invariant 4 requires of
anything sitting after engine 10 `cost`.

That is not a reason to build it loosely. The arithmetic is what Phase 7's promotion gate
will read, and a weighting rule that is wrong while it is inert is a rule that is wrong
when it stops being inert, with no event in between to prompt anyone to check it.

## Why Brier skill against the base rate, and not inverse Brier

Approved by the lead, 2026-09-16. `skill = 1 - brier / base_rate_brier`, clipped below at
zero, normalised across versions; all zero with a reason code when nothing beats its base
rate. The alternatives both pay a model for having no edge — Brier is bounded and
positive, so `1 / brier` hands a respectable weight to a model *worse than always
predicting the base rate*, and spec 67's first real run came in at or slightly worse than
base rate on two folds of three. Neither inverse-Brier nor a rank could express spec 97's
own requirement that such a model gets zero.

**The base rate is not `win_rate * (1 - win_rate)`**, and the near-miss is recorded in the
build log because it is in range and plausible: `brier` and `base_rate_brier` are computed
over **every** fold row while `win_rate` is over the **BUY subset** only, so a skill score
built from those two divides quantities measured on different populations.

## What it will not do

It never selects, loads or swaps the model engine 8 uses — `models.prediction_run_id` is
the operator's. It never blocks and never approves. It never persists a previous bar's DI.
And it publishes **no weights at all** rather than a weight set over rows it knows are
incomplete: see `_read_leaderboard`.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from acsoe.core.contracts import (
    BaseEngine,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.engines.adaptive_router.contracts import (
    DI_FIELD,
    DI_THRESHOLD_FIELD,
    LEADERBOARD_ENUMERATION,
    MODEL_ID,
    PREDICTION_KEY,
    PREDICTION_RUN_ID_FIELD,
    REASON_LEADERBOARD_EMPTY,
    REASON_LEADERBOARD_TRUNCATED,
    REASON_LEADERBOARD_UNREADABLE,
    REASON_NO_MODEL_BEATS_ITS_BASE_RATE,
    REGIME_KEY,
    REGIME_LABEL_FIELD,
    STATE_KEY,
    RouterState,
)

#: The limit passed to the console's windowed read when it is the only one available.
#: **Not a threshold and not tuning**: nothing is weighted from a windowed read at all —
#: a full window publishes no weights and `leaderboard_truncated`. It exists so the
#: fallback can *detect* that it cannot see the whole table, and the number only has to
#: be large enough that the detection is not the normal case.
_WINDOWED_PROBE = 500


class AdaptiveRouterEngine(BaseEngine):
    """Engine 14. Opportunity chain, after engine 11 and before engine 15. Not a gate."""

    name: ClassVar[str] = STATE_KEY
    number: ClassVar[int] = 14

    #: Not a gate, and `is_gate_matches_registry` asserts this exact value. It could not
    #: be one: invariant 4 forbids a model output overriding a gate, and a weight is the
    #: purest form of model output in this system.
    is_gate: ClassVar[bool] = False

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        prediction = _mapping(state.get(PREDICTION_KEY))
        regime = _mapping(state.get(REGIME_KEY)).get(REGIME_LABEL_FIELD)
        partial = RouterState(
            active_model_run_id=_text(prediction.get(PREDICTION_RUN_ID_FIELD)),
            regime=None if regime is None else str(regime),
            di_margin=_di_margin(prediction),
        )

        rows, problem = self._read_leaderboard(context)
        if problem is not None:
            return self._published(partial.model_copy(update={"reason_code": problem}), started)
        if not rows:
            return self._published(
                partial.model_copy(update={"reason_code": REASON_LEADERBOARD_EMPTY}), started
            )

        return self._published(
            _weigh(partial, _one_row_per_version(rows)), started
        )

    # ------------------------------------------------------------------ inputs

    def _read_leaderboard(
        self, context: EngineContext
    ) -> tuple[Sequence[Any], str | None]:
        """Every leaderboard row, or a reason code saying why they cannot all be seen.

        **Two reads, and the fallback is deliberately unable to produce weights.** The
        enumeration named by `LEADERBOARD_ENUMERATION` is the one engine 14 needs and is
        queued with B. Until it exists the only enumerating read is the console's
        `leaderboard(limit=...)`, which truncates — and weighting from a truncated window
        is the defect B's own docstring on `leaderboard_entries` warns about, arriving at
        a different caller. A version outside the window would be **absent because nobody
        looked**, not zero because it had no edge, and the weights would still sum to one
        over the wrong set. Nothing downstream could tell.

        So a windowed read that comes back exactly full publishes no weights. **The check
        stays after the real read lands** rather than being deleted with the fallback: it
        is then the assertion that the fallback is unreachable, which is the standing rule
        for a workaround for something that has since been fixed.
        """
        store = getattr(context.clients, "store", None)
        if store is None:
            return (), REASON_LEADERBOARD_UNREADABLE

        enumerate_all = getattr(store, LEADERBOARD_ENUMERATION, None)
        if callable(enumerate_all):
            # `model_id` is required rather than defaulted, and B is right that it should
            # be: the read has no `LIMIT`, which is the point of it, and "no limit" is
            # only safe because one model's rows are bounded by its walk-forward. The
            # table as a whole is bounded by nothing, so a family added in Phase 7 would
            # silently widen every caller's result set. Stating the scope at the call
            # site is the same argument as refusing the truncating window: the caller
            # must be able to see what it is getting.
            #
            # **No length check on this path.** It was here and it was wrong — the read
            # is unlimited, so "came back exactly full" is not a fact about it, and the
            # comparison fires on a model that genuinely has exactly `_WINDOWED_PROBE`
            # rows and costs that tick all of its weights. Over 405 folds that is not
            # impossible. Found by B3 reading the code rather than by a test, because no
            # fixture would have had exactly that many rows. The assertion that the
            # fallback is unreachable belongs in a test, and is one; a heuristic that
            # cannot distinguish a full window from a coincidence is not an assertion.
            return list(enumerate_all(model_id=MODEL_ID)), None

        windowed = getattr(store, "leaderboard", None)
        if not callable(windowed):
            return (), REASON_LEADERBOARD_UNREADABLE
        rows = list(windowed(limit=_WINDOWED_PROBE))
        if len(rows) == _WINDOWED_PROBE:
            return rows, REASON_LEADERBOARD_TRUNCATED
        return rows, None

    # ------------------------------------------------------------------ result

    def _published(self, published: RouterState, started: float) -> EngineResult:
        """Always `OK`, always `blocks_trading=False`.

        Every path that ran returns this, including the ones that publish no weights.
        Engine 14 is not a gate, and a non-gate that refused on its own criteria would
        make `is_gate` wrong — the principle the operator applied to engine 16. There is
        nothing here for a downstream engine to fail closed on, because there is nothing
        here a downstream engine reads to decide.
        """
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            data=published.to_state_data(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


# --------------------------------------------------------------------------- #
# Reading the rows
# --------------------------------------------------------------------------- #


def _one_row_per_version(rows: Sequence[Any]) -> dict[str, list[Any]]:
    """Rows grouped by `model_version`, with duplicate `(version, fold)` rows collapsed.

    **Duplicates are not folds and must not be averaged as folds.** B's
    `leaderboard_entries` docstring records that there is no unique index on
    `(model_id, model_version, fold)` and that it deliberately returns every match, so
    that a broken idempotency convention stays visible rather than being collapsed by the
    reader. The same rows reaching a mean-over-folds would weight one fold twice, which is
    a weighting decision made by a duplicate row rather than by a measurement.

    So the latest row per `(version, fold)` by `updated_at` wins, and how many were
    collapsed is reported in `basis`. Absorbed silently, the duplicate would change the
    weight and leave nothing to notice it by.
    """
    latest: dict[tuple[str, str | None], Any] = {}
    for row in rows:
        # Only this engine's own model family. The leaderboard is keyed on
        # `(model_id, model_version, fold)` and nothing stops a second family appearing
        # in it; weighting across families would put a predictor's Brier in a
        # distribution with a score measured on a different question, and normalising
        # would then hand part of the predictor's weight to it. There is one family
        # today, which is exactly why this would have been unnoticeable.
        if str(getattr(row, "model_id", "") or "") != MODEL_ID:
            continue
        version = str(getattr(row, "model_version", "") or "")
        if not version:
            continue
        fold = getattr(row, "fold", None)
        key = (version, None if fold is None else str(fold))
        held = latest.get(key)
        if held is None or _stamp(row) >= _stamp(held):
            latest[key] = row
    grouped: dict[str, list[Any]] = {}
    for (version, _fold), row in latest.items():
        grouped.setdefault(version, []).append(row)
    return grouped


def _stamp(row: Any) -> int:
    """`updated_at` as an integer, or 0 for a row that does not carry a usable one.

    0 rather than a raise, and it is a tie-break rather than a value anyone reads: two
    rows with no usable stamp keep whichever came last out of the store, which is the
    same answer the caller would have reached without this function.
    """
    value = getattr(row, "updated_at", None)
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _number(value: Any) -> float | None:
    """A float, or `None` for anything that is not a finite number.

    A bool is refused explicitly: `isinstance(True, int)` is true in Python, so a boolean
    reaching a metric field would otherwise score as 1.0 and weight a model on it.
    """
    import math

    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _di_margin(prediction: Mapping[str, Any]) -> float | None:
    """`di_threshold - di`, positive when the candidate sits inside the reference set.

    Provenance only. Absent whenever either half is — engine 8 publishes neither on a
    load failure, and a margin computed from one of them would be a number about nothing.
    """
    di = _number(prediction.get(DI_FIELD))
    threshold = _number(prediction.get(DI_THRESHOLD_FIELD))
    if di is None or threshold is None:
        return None
    return threshold - di


# --------------------------------------------------------------------------- #
# The weighting rule
# --------------------------------------------------------------------------- #


def _weigh(partial: RouterState, grouped: Mapping[str, Sequence[Any]]) -> RouterState:
    """Brier skill against each version's own base rate, clipped at zero, normalised.

    **Per version, aggregated across that version's folds as an unweighted mean of the
    per-fold skills.** Lead ruling, and the reasoning is that the question is "how good is
    this model version" while each fold is one out-of-sample measurement of it — and an
    unweighted mean is the only aggregation of the three considered that does not encode a
    second, unstated judgement. A most-recent-fold rule encodes recency and a
    fold-count-weighted mean quietly rewards a version for having been around longer.

    **It is inert on the real table today and the fixture is what exercises it.** Engine
    20 writes one row per `(version, fold)` and the fold's artefact run id *is* the model
    version, so every real version has exactly one fold and all three aggregations agree.
    `tests/engines/test_adaptive_router.py` carries a version with several folds so the
    mean is actually computed, and says in its own message that it is asserting a property
    of the fixture.

    A version whose base rate is missing gets **weight zero and is named in the basis**,
    never a defaulted base rate: choosing a default is choosing the line at which a model
    counts as having edge, and that is not this lane's to choose.
    """
    skills: dict[str, float] = {}
    basis: dict[str, Any] = {
        "rule": "mean over folds of max(0, 1 - brier / base_rate_brier), normalised",
        "versions": {},
    }
    for version, rows in sorted(grouped.items()):
        per_fold: list[float] = []
        unscored: list[str] = []
        for row in rows:
            skill = _fold_skill(row)
            if skill is None:
                unscored.append(str(getattr(row, "fold", None)))
            else:
                per_fold.append(skill)
        mean = sum(per_fold) / len(per_fold) if per_fold else 0.0
        skills[version] = mean
        basis["versions"][version] = {
            "folds_scored": len(per_fold),
            "folds_unscored": sorted(unscored),
            "mean_skill": mean,
        }

    total = sum(skills.values())
    if total <= 0.0:
        return partial.model_copy(
            update={
                "weights": dict.fromkeys(skills, 0.0),
                "basis": basis,
                "reason_code": REASON_NO_MODEL_BEATS_ITS_BASE_RATE,
            }
        )
    return partial.model_copy(
        update={
            "weights": {version: skill / total for version, skill in skills.items()},
            "basis": basis,
            "reason_code": None,
        }
    )


def _fold_skill(row: Any) -> float | None:
    """One fold's Brier skill, or `None` when it cannot be measured.

    **`base_rate_brier` is a column B is adding in migration 0004 and does not exist
    yet**, so today this returns `None` for every row and every weight is zero with
    `no_model_beats_its_base_rate`. That is the correct behaviour rather than a stub: a
    version whose base rate cannot be read has not been shown to have edge, and weighting
    it anyway would be the defaulting this rule exists to avoid. When the column lands,
    nothing here changes — `getattr` starts finding it.

    A base rate of zero is a fold whose every row had the same outcome; the skill score is
    undefined there rather than infinite, and the fold is reported unscored.
    """
    brier = _number(getattr(row, "brier", None))
    base_rate = _number(getattr(row, "base_rate_brier", None))
    if brier is None or base_rate is None or base_rate <= 0.0:
        return None
    return max(0.0, 1.0 - brier / base_rate)


__all__ = ["AdaptiveRouterEngine"]
