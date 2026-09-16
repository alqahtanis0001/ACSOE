"""Spec 73 — engine 15 `skeptic`.

The last gate, and the only one that reads the prediction. Every artefact here is trained
into a temporary root, never read from `models/`.

**The fixture trains four folds and uses the last, and that is not a convenience.** Spec 69:
a fold with no earlier out-of-sample BUY calls trains no skeptic, and the first fold of every
run is such a fold. A fixture pointed at fold 0 would exercise only the `skeptic_unavailable`
path, and every assertion below about vetoing would be unreachable — with the file green.
Both folds are used here, deliberately: the early one to prove the absence is reported, the
later one to prove the veto works.

The two things this file is really about are the two that would be lost silently. **It can
only veto** — there is no output that makes a trade more likely, asserted on the published
shape rather than on behaviour. And **a non-BUY call is `OK`, not a block** — a `BLOCK` there
would record a veto the skeptic never made, and the leaderboard would credit it with every
bar the predictor simply did not like.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import require_module
from tests.engines.test_prediction import (
    DI_PERCENTILE,
    MACRO_ARCHIVE,
    PAIR,
    Wrapped,
    bars,  # noqa: F401 - a fixture, used by name
    complete_state,
    context_with,
)

require_module("polars", reason="polars is not installed")
require_module("lightgbm", reason="lightgbm is not installed")
require_module("sklearn", reason="scikit-learn is not installed")

from acsoe.core.contracts import EngineStatus  # noqa: E402
from acsoe.engines.prediction.contracts import (  # noqa: E402
    KEY_PREDICTION_RUN_ID,
    REASON_DI_REFUSED,
)
from acsoe.engines.prediction.engine import PredictionEngine  # noqa: E402
from acsoe.engines.skeptic.contracts import (  # noqa: E402
    KEY_SKEPTIC_RUN_ID,
    KEY_VETO_THRESHOLD,
    NOT_A_BUY_CALL,
    REASON_UNAVAILABLE,
    REASON_VETO,
    SkepticState,
)
from acsoe.engines.skeptic.engine import SkepticEngine  # noqa: E402

#: Four folds, because fold 0 trains no skeptic and fold 1 onwards do.
FOLDS = 4

#: A threshold at the midpoint of the probability range, supplied through a wrapper and
#: **never written into `config/default.yaml`**. Absent is what this gate fails closed on.
#: Tests that need a specific side of the line set it from a measured `p_wrong` instead.
VETO_THRESHOLD = 0.5


@pytest.fixture(scope="module")
def trained_skeptic(tmp_path_factory: Any) -> tuple[Path, str, str]:
    """`(models root, a run with a skeptic, a run without one)`."""
    from tests.harness.doubles import load_default_config
    from tests.research.test_training import NOW, dataset_for

    from acsoe.research import training

    config = load_default_config()
    root = tmp_path_factory.mktemp("skeptic-models")
    report = training.train_walkforward(
        # With macro columns, so the skeptic's feature half is the predictor's whole
        # feature list the way it is live. Without them the macro half of `_vector`
        # never executes and a mutation in the spec 73 sweep survived because of it.
        dataset_for(config, random_walk=False, macro_archive=MACRO_ARCHIVE),
        config=Wrapped(config, **{"prediction.di_percentile": DI_PERCENTILE}),
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=FOLDS,
    )
    with_skeptic = [
        report.fold_runs[int(entry["fold_index"])]
        for entry in report.folds
        if entry.get("skeptic_rows")
    ]
    assert with_skeptic, "no fold trained a skeptic, so every veto assertion is unreachable"
    without = report.fold_runs[0]
    assert not (report.models_dir / without / "skeptic.txt").exists(), (
        "fold 0 trained a skeptic, so the reported-absence path is not being tested"
    )
    return report.models_dir, with_skeptic[-1], without


@pytest.fixture
def root(trained_skeptic: tuple[Path, str, str]) -> Path:
    return trained_skeptic[0]


@pytest.fixture
def run_id(trained_skeptic: tuple[Path, str, str]) -> str:
    return trained_skeptic[1]


@pytest.fixture
def run_without_skeptic(trained_skeptic: tuple[Path, str, str]) -> str:
    return trained_skeptic[2]


def predicted_state(
    engine_context: Any, bar_rows: list[dict[str, Any]], root: Path, run_id: str
) -> tuple[dict[str, Any], Any]:
    """`state` with engine 8's **real** output in it, not a hand-built prediction.

    Phase 3's ruling that no test hand-builds another engine's payload matters more here than
    anywhere: the skeptic's extra inputs are exactly engine 8's published fields, in exactly
    the manifest's order, and a fabricated prediction would let a mismatch between the two
    pass unnoticed. A prediction that engine 8 refused to make is no use either, so the
    fixture asserts it got one.
    """
    state, context = complete_state(engine_context, bar_rows, root, run_id)
    context = context_with(context, root, **{KEY_PREDICTION_RUN_ID: run_id})
    result = PredictionEngine().process(context, state)
    assert result.status is EngineStatus.OK, (result.data.get("reason_code"), result.reason)
    return {**state, "prediction": dict(result.data)}, context


def judged(
    state: dict[str, Any], context: Any, root: Path, run_id: str, **overrides: Any
) -> Any:
    settings = {KEY_SKEPTIC_RUN_ID: run_id, KEY_VETO_THRESHOLD: VETO_THRESHOLD, **overrides}
    return SkepticEngine().process(context_with(context, root, **settings), state)


def as_buy(state: dict[str, Any], *, is_buy: bool) -> dict[str, Any]:
    return {**state, "prediction": {**state["prediction"], "is_buy": is_buy}}


# --------------------------------------------------------------------------- #
# Registry, and invariant 4
# --------------------------------------------------------------------------- #


def test_it_matches_the_registry_table() -> None:
    engine = SkepticEngine()
    assert engine.name == "skeptic"
    assert engine.number == 15
    assert engine.is_gate is True


def test_there_is_no_published_field_that_makes_a_trade_more_likely() -> None:
    """Invariant 4, asserted on the published shape rather than on behaviour.

    A field an engine downstream could read as a reason to trade — an approval, a confidence,
    a margin — is a model output overriding a gate, and it would be reachable the moment
    somebody added it. The shape is the enforcement.
    """
    assert set(SkepticState.model_fields) == {
        "pair",
        "model_run_id",
        "p_wrong",
        "threshold",
        "vetoed",
        "reason",
        "reason_code",
    }


def test_the_executable_source_contains_no_approval_of_any_kind() -> None:
    """The same rule one level down, because a field is not the only way to approve.

    **Docstrings and comments are stripped first**, and that is not a loophole: the module's
    own prose explains at length that it must never approve, so a raw substring scan fails on
    the sentence forbidding the thing. Scanning the code with the prose removed is the check
    that means something — a name, a key or a literal an engine downstream could read.

    `research/training.py` carries the same assertion over its own source. Two halves of one
    guarantee: the trainer produces a probability of being **wrong**, and the engine turns
    that into a veto or into nothing at all.
    """
    import ast
    import inspect

    from acsoe.engines.skeptic import engine as module

    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(ast.fix_missing_locations(tree)).lower()
    # "boost" is deliberately not in this list: LightGBM's own `booster` contains it, and a
    # scan that flagged the model object would have to be relaxed by whoever met it next —
    # which is how a check stops being one.
    for forbidden in ("approv", "endors", "encourag", "confidence", "authoris", "authoriz"):
        assert forbidden not in code, (forbidden, "in the executable source of engine 15")


# --------------------------------------------------------------------------- #
# The refusals, each by its reason code
# --------------------------------------------------------------------------- #


def test_with_no_threshold_configured_it_blocks_rather_than_passing(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> None:
    """**Blocks, does not pass**, and that is the decision worth testing.

    A gate that failed open on an absent threshold would be the one gate meant to catch the
    predictor's mistakes, and the one gate not running — and the system would look like it
    had a skeptic.

    **The absent case is this test's to supply.** `skeptic.veto_threshold` was absent from
    `config/default.yaml` until the operator ruled `0.50` on 2026-09-14, so the precondition
    below is inverted from what it was: the committed config carries a value and the call
    below removes it. The threshold's value is deliberately not pinned here — it is
    provisional until the chain runs end to end, and the behaviour under test is what
    happens when there is no threshold at all, which no value can express.
    """
    from tests.harness.doubles import load_default_config

    assert load_default_config().get(KEY_VETO_THRESHOLD) is not None, (
        "the operator's veto threshold is absent from config/default.yaml. This test "
        "supplies the absent case itself, so an absent key here means the ruled value has "
        "been lost rather than that this test is stale."
    )
    state, context = predicted_state(engine_context, bars, root, run_id)
    result = judged(as_buy(state, is_buy=True), context, root, run_id, **{KEY_VETO_THRESHOLD: None})
    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert KEY_VETO_THRESHOLD in (result.reason or "")


def test_with_no_run_id_configured_it_blocks_with_skeptic_unavailable(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> None:
    from tests.harness.doubles import load_default_config

    assert load_default_config().get(KEY_SKEPTIC_RUN_ID) is None
    state, context = predicted_state(engine_context, bars, root, run_id)
    result = judged(as_buy(state, is_buy=True), context, root, run_id, **{KEY_SKEPTIC_RUN_ID: None})
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert KEY_SKEPTIC_RUN_ID in (result.reason or "")


def test_a_fold_that_trained_no_skeptic_blocks_and_says_so(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str,  # noqa: F811
    run_without_skeptic: str
) -> None:
    """Spec 69's reported absence, met from the other side.

    Fold 0 has no earlier out-of-sample BUY calls and correctly trains nothing. The gate
    blocks rather than guessing: a binary model invented in its place would be a coin flip
    with a manifest, and its vetoes would be indistinguishable from measured ones.
    """
    state, context = predicted_state(engine_context, bars, root, run_id)
    result = judged(as_buy(state, is_buy=True), context, root, run_without_skeptic)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert "no skeptic" in (result.reason or "")


def test_a_tampered_artefact_blocks_rather_than_judging_from_it(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str,  # noqa: F811
    tmp_path: Path
) -> None:
    copy = tmp_path / "models"
    shutil.copytree(root, copy)
    target = copy / run_id / "skeptic.txt"
    target.write_bytes(target.read_bytes() + b"\n")

    state, context = predicted_state(engine_context, bars, root, run_id)
    result = judged(as_buy(state, is_buy=True), context, copy, run_id)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert "skeptic.txt" in (result.reason or "")


def test_an_incomplete_input_blocks_rather_than_failing_open(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> None:
    """A learned veto scored on a partial vector is a refusal nobody can explain. The gate
    that cannot judge says so rather than waving the call through."""
    state, context = predicted_state(engine_context, bars, root, run_id)
    buying = as_buy(state, is_buy=True)
    broken = {**buying, "prediction": {**buying["prediction"], "p_target": None}}
    result = judged(broken, context, root, run_id)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert "p_target" in (result.reason or "")


# --------------------------------------------------------------------------- #
# A non-BUY call
# --------------------------------------------------------------------------- #


def test_a_non_buy_call_is_ok_and_not_a_veto(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> None:
    """The skeptic grades BUY calls and has no opinion about the rest.

    A `BLOCK` here would write a veto into the one table the research reads that never
    happened, and the leaderboard would credit the skeptic with every bar the predictor
    simply did not like. Turning a non-BUY into no trade is Phase 6's decision engine.
    """
    state, context = predicted_state(engine_context, bars, root, run_id)
    result = judged(as_buy(state, is_buy=False), context, root, run_id)
    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data["vetoed"] is False
    assert result.data["reason"] == NOT_A_BUY_CALL
    assert result.data["reason_code"] is None


def test_a_non_buy_call_does_not_load_the_model_at_all(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> None:
    """The cheap half of the same decision, and the one a result cannot show.

    An engine that loaded and scored before checking `is_buy` would return the same `OK` and
    pay a hash of every file in the directory on every non-BUY bar, which is most bars.
    """
    result = judged(
        as_buy(predicted_state(engine_context, bars, root, run_id)[0], is_buy=False),
        predicted_state(engine_context, bars, root, run_id)[1],
        root,
        "train-nothing-ever-wrote-this",
    )
    assert result.status is EngineStatus.OK, (
        "a non-BUY call reached the loader: the engine blocked on a run id that does not "
        "exist, which it should never have looked for"
    )


#: A marker for "the key is not in the published mapping at all", distinct from `None`.
_ABSENT = object()


@pytest.mark.parametrize(
    "published",
    [
        pytest.param(_ABSENT, id="absent"),
        pytest.param(None, id="none"),
        pytest.param("false", id="string-false"),
        pytest.param("true", id="string-true"),
        pytest.param(0, id="int-0"),
        pytest.param(1, id="int-1"),
    ],
)
def test_an_is_buy_that_is_not_a_boolean_blocks_rather_than_reading_as_non_buy(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str,  # noqa: F811
    published: Any,
) -> None:
    """Only an explicit `False` is a non-BUY call. Invariant 3.

    Absent, `None`, or a value that merely looks like a boolean is engine 8 having made no
    call. Read as "not a BUY" it returns `OK`, and that is the absence of a "no" taken as a
    yes. The falsy cases (`absent`, `none`, `int-0`) are the ones a truthiness check waves
    through as non-BUY; the truthy ones (`string-true`, `int-1`) are the ones it would score
    as though engine 8 had said BUY.

    **Spec 95 changed the sentence and not the verdict**, and the two assertions at the end
    hold that line. The block landed in spec 73, a phase before engine 8 stopped publishing
    `is_buy: false` on its refusals, and it is the reason nothing failed open in between.
    """
    state, context = predicted_state(engine_context, bars, root, run_id)
    prediction = {k: v for k, v in state["prediction"].items() if k != "is_buy"}
    if published is not _ABSENT:
        prediction["is_buy"] = published
    result = judged({**state, "prediction": prediction}, context, root, run_id)
    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert result.data["vetoed"] is False
    assert "engine 8 made no call" in (result.reason or "")
    assert NOT_A_BUY_CALL not in (result.reason or ""), (
        "the refusal sentence calls this a non-BUY call, which is the one thing it is "
        "not: spec 95 exists because those two facts used to be indistinguishable"
    )


def refused_prediction(
    engine_context: Any, bar_rows: list[dict[str, Any]], root: Path, run_id: str
) -> tuple[dict[str, Any], Any]:
    """`state` carrying a payload **the real engine 8 published when it refused**.

    The refusal is induced the way `tests/engines/test_prediction.py` induces it — one
    feature family moved far outside the training range, which is what an unprecedented
    market does to a feature vector — so the Dissimilarity Index declines and engine 8
    blocks with `di_refused`. Nothing here hand-builds the payload: spec 95 is a change to
    what engine 8 *publishes*, and a fabricated prediction would be this test agreeing
    with itself about the very field under test. That is the seam Phase 4 found twice in
    one day, and code-standards requires one test of it with no double on either side.
    """
    state, context = complete_state(engine_context, bar_rows, root, run_id)
    context = context_with(context, root, **{KEY_PREDICTION_RUN_ID: run_id})
    row = dict(state["feature"]["pairs"][PAIR])
    for name in row:
        if name.startswith(("log_return_", "realised_vol_", "volume_z_")):
            row[name] = 500.0
    state = {
        **state,
        "feature": {
            **state["feature"],
            "pairs": {**state["feature"]["pairs"], PAIR: row},
        },
    }
    result = PredictionEngine().process(context, state)
    assert result.status is EngineStatus.BLOCK, (
        "engine 8 did not refuse this candidate, so there is no refusal payload to hand "
        f"engine 15 and this test proves nothing: it returned {result.status}"
    )
    assert result.data["reason_code"] == REASON_DI_REFUSED, result.data["reason_code"]
    return {**state, "prediction": dict(result.data)}, context


def test_a_refusing_engine_8s_real_payload_blocks_naming_the_absence(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> None:
    """Spec 95, both halves of it, through the real producer and the real consumer.

    Before spec 95 this exact state reached engine 15 as `is_buy: false` — the payload of
    a predictor that ran and called no BUY — and only engine 15's own spec 73 hardening
    kept it from passing, because that hardening reads *three* cases and not two. Now the
    payload itself says which happened: the key is absent, and the gate's sentence names
    engine 8's refusal rather than describing a call that was never made.

    Live this tick never reaches engine 15 at all, because engine 8's `BLOCK` stops the
    opportunity chain under contract rule 6. That is exactly why the check belongs in a
    test: the safety net downstream is one an operator cannot see, and engine 14
    `adaptive_router` is about to read the same field from outside a gate.
    """
    state, context = refused_prediction(engine_context, bars, root, run_id)

    assert "is_buy" not in state["prediction"], (
        "engine 8's refusal published an is_buy, so the rest of this test would be "
        "measuring the old behaviour"
    )

    result = judged(state, context, root, run_id)
    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert result.data["vetoed"] is False, "an unreachable skeptic recorded a veto"
    assert result.data["p_wrong"] is None
    assert "engine 8 made no call" in (result.reason or "")
    assert "absent" in (result.reason or "")
    assert result.data["reason"] != NOT_A_BUY_CALL
    assert NOT_A_BUY_CALL not in (result.reason or ""), (
        "a refusal by engine 8 was reported as a non-BUY call, which is the conflation "
        "spec 95 removed from the payload"
    )


def test_a_candidate_with_no_prediction_published_blocks_rather_than_passing(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> None:
    """Scout named a pair and engine 8 published nothing about it. That is not "no
    candidate" — which still passes, below — and not a non-BUY call either."""
    state, context = predicted_state(engine_context, bars, root, run_id)
    bare = {**state, "scout": {**(state.get("scout") or {}), "pair": PAIR}, "prediction": {}}
    result = judged(bare, context, root, run_id)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert result.data["pair"] == PAIR


# --------------------------------------------------------------------------- #
# The veto itself
# --------------------------------------------------------------------------- #


@pytest.fixture
def measured(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> tuple[dict[str, Any], Any, float]:
    """One real BUY call, and the `p_wrong` the skeptic gives it.

    Measured rather than assumed, so the two tests below can put the threshold on either side
    of it. Anything else would be a test that passes because the number happened to fall the
    right way.
    """
    state, context = predicted_state(engine_context, bars, root, run_id)
    state = as_buy(state, is_buy=True)
    result = judged(state, context, root, run_id, **{KEY_VETO_THRESHOLD: 1.0})
    assert result.status is EngineStatus.OK, (result.data, result.reason)
    return state, context, float(result.data["p_wrong"])


def test_a_call_above_the_threshold_is_vetoed(
    measured: tuple[dict[str, Any], Any, float], root: Path, run_id: str
) -> None:
    """The reason carries `p_wrong` and the threshold, because a veto with no numbers is one
    nobody can argue with or check."""
    state, context, p_wrong = measured
    result = judged(state, context, root, run_id, **{KEY_VETO_THRESHOLD: p_wrong / 2})
    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_VETO
    assert result.data["vetoed"] is True
    assert result.data["p_wrong"] == pytest.approx(p_wrong)
    shown_p_wrong, shown_threshold = veto_numbers(result.reason)
    assert float(shown_p_wrong) == pytest.approx(p_wrong, rel=1e-5)
    assert float(shown_threshold) == pytest.approx(p_wrong / 2, rel=1e-5)


def test_the_same_call_below_the_threshold_is_not(
    measured: tuple[dict[str, Any], Any, float], root: Path, run_id: str
) -> None:
    """The pass half, one number apart from the block. Without it the test above is
    satisfied by a gate that vetoes everything."""
    state, context, p_wrong = measured
    result = judged(state, context, root, run_id, **{KEY_VETO_THRESHOLD: min(p_wrong * 2, 1.0)})
    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data["vetoed"] is False
    assert result.data["p_wrong"] == pytest.approx(p_wrong)


def test_a_p_wrong_exactly_on_the_threshold_is_not_vetoed(
    measured: tuple[dict[str, Any], Any, float], root: Path, run_id: str
) -> None:
    """The boundary, in the direction every other gate in this system rounds: the threshold
    is the last acceptable value, not the first refused one. Two comparisons differing by one
    character, and only the bar landing exactly on the line can tell them apart."""
    state, context, p_wrong = measured
    result = judged(state, context, root, run_id, **{KEY_VETO_THRESHOLD: p_wrong})
    assert result.status is EngineStatus.OK
    assert result.data["vetoed"] is False


def veto_numbers(reason: str | None) -> tuple[str, str]:
    """The two numbers a veto sentence prints, exactly as printed."""
    import re

    found = re.search(
        r"puts this call (\S+) likely to be wrong against a veto threshold of (\S+)\.$",
        reason or "",
    )
    assert found, ("not a veto sentence", reason)
    return found.group(1), found.group(2)


class _FixedBooster:
    """Stands in for the booster and returns one chosen score, in LightGBM's own shape.

    The real booster on this fixture scores near 1 and cannot be made to produce NaN, or a
    score four decimal places below its threshold, so this is the only way either property
    exists at all. It counts its calls, so a test that never reached the score cannot pass by
    blocking somewhere earlier.
    """

    def __init__(self, value: float) -> None:
        self.value = value
        self.calls = 0

    def predict(self, rows: Any) -> Any:
        import numpy as np

        self.calls += 1
        return np.asarray([self.value] * len(rows), dtype=np.float64)


def judged_with_score(
    engine_context: Any, bar_rows: list[dict[str, Any]], root: Path, run_id: str,
    score: float, threshold: float,
) -> tuple[Any, _FixedBooster]:
    """A real BUY call, the real skeptic loaded, and its booster swapped for `_FixedBooster`.

    Built from `predicted_state` rather than `measured`, which asserts an `OK` at a threshold
    of 1.0: a mutation to the comparison or the threshold would error that fixture, and every
    test below would go red on somebody else's assertion rather than its own.
    """
    import dataclasses

    state, context = predicted_state(engine_context, bar_rows, root, run_id)
    state = as_buy(state, is_buy=True)
    settings = {KEY_SKEPTIC_RUN_ID: run_id, KEY_VETO_THRESHOLD: threshold}
    engine = SkepticEngine()
    engine.process(context_with(context, root, **settings), state)
    assert engine._skeptic is not None, "the real skeptic did not load, so there is nothing to swap"

    booster = _FixedBooster(score)
    engine._skeptic = dataclasses.replace(engine._skeptic, booster=booster)
    result = engine.process(context_with(context, root, **settings), state)
    assert booster.calls == 1, "the score was never reached, so this proves nothing"
    return result, booster


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")], ids=str)
def test_a_non_finite_p_wrong_blocks_rather_than_passing(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str,  # noqa: F811
    score: float,
) -> None:
    """`nan > threshold` is `False`, so a comparison alone passes a NaN. So does `-inf`, and
    `inf` would be recorded as a measured veto. Each is a model that returned nonsense, and
    the gate says it cannot judge rather than judging from it."""
    import math

    assert not math.isfinite(score)
    result, _booster = judged_with_score(
        engine_context, bars, root, run_id, score, VETO_THRESHOLD
    )
    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert result.data["vetoed"] is False
    assert "non-finite" in (result.reason or "")
    json.dumps(result.data, allow_nan=False)


@pytest.mark.parametrize(
    ("score", "threshold"),
    [
        pytest.param(3.2e-5, 1.1e-5, id="both-tiny"),
        pytest.param(0.12345678, 0.12345671, id="equal-to-six-places"),
    ],
)
def test_a_veto_sentence_shows_two_numbers_that_differ(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str,  # noqa: F811
    score: float, threshold: float,
) -> None:
    """A veto whose own sentence cannot show the score was above the line is no sentence.

    Found in B-3's rehearsal: at `:.4f` a trained fixture's veto read "0.0000 likely to be
    wrong against a veto threshold of 0.0000". Both cases here print identically at four
    decimal places, and the second prints identically at six significant digits too.
    """
    assert f"{score:.4f}" == f"{threshold:.4f}", "this case would not catch a fixed :.4f"
    result, _booster = judged_with_score(engine_context, bars, root, run_id, score, threshold)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_VETO
    shown_p_wrong, shown_threshold = veto_numbers(result.reason)
    assert shown_p_wrong != shown_threshold
    assert float(shown_p_wrong) > float(shown_threshold)
    assert float(shown_p_wrong) == pytest.approx(score, rel=1e-6)
    assert float(shown_threshold) == pytest.approx(threshold, rel=1e-6)


def test_p_wrong_is_the_probability_of_being_wrong_and_not_of_being_right(
    measured: tuple[dict[str, Any], Any, float], root: Path, run_id: str
) -> None:
    """The one thing about this model no result can reveal on its own.

    The trained label is `wrong = label != "target"` and LightGBM's binary objective returns
    the probability of the positive class. Read as "the probability the call is right", the
    gate would veto exactly the good calls at a rate that looks entirely plausible. Recomputed
    here from the booster and the manifest's own input order rather than compared against
    what the engine reported about itself.
    """
    import lightgbm as lgb
    import numpy as np

    from acsoe.modelling.artefacts import load_run

    state, _context, p_wrong = measured
    manifest = json.loads((root / run_id / "manifest.json").read_bytes().decode("utf-8"))
    names = list(manifest["extras"]["skeptic"]["input_names"])
    feature_names = list(manifest["feature_names"])
    assert names == [*feature_names, "p_target", "p_stop", "p_timeout", "expected_move_pct"]

    loaded = load_run(root / run_id, expected_features=tuple(feature_names))
    row = state["feature"]["pairs"][PAIR]
    macro = state["macro_context"]["features"]
    raw = [
        float(macro[name]) if name in macro else float(row[name]) for name in feature_names
    ]
    scaled = list(loaded.scaler.transform([raw])[0])
    extras = [
        float(state["prediction"]["p_target"]),
        float(state["prediction"]["p_stop"]),
        float(state["prediction"]["p_timeout"]),
        float(state["prediction"]["expected_move_pct"]),
    ]
    booster = lgb.Booster(model_file=str(root / run_id / "skeptic.txt"))
    expected = float(
        np.asarray(booster.predict(np.asarray([scaled + extras], dtype=np.float64))).reshape(-1)[0]
    )
    assert p_wrong == pytest.approx(expected, abs=1e-12)


def test_the_vector_is_built_in_the_manifests_order_not_the_state_rows(
    measured: tuple[dict[str, Any], Any, float], root: Path, run_id: str
) -> None:
    """The same features, published in a different order, must score identically.

    A mapping has no order that means anything, and an engine that built its vector by
    iterating the published row would hand the model whichever order engines 5 and 6 happened
    to serialise: every value in range, every value in the wrong column, and a veto rate that
    looks entirely plausible.

    **Nothing about a single result can show this**, which is why it needs two. A mutation
    replacing the manifest's order with the row's survived the whole file until this test
    existed, because the fixture's row happens to be published in the manifest's order — as
    it is live, today, until somebody changes how engine 5 builds it.
    """
    state, context, p_wrong = measured
    row = state["feature"]["pairs"][PAIR]
    macro = state["macro_context"]["features"]
    assert len(row) > 1 and len(macro) > 1, "nothing to reverse, so this proves nothing"

    shuffled = {
        **state,
        "feature": {
            **state["feature"],
            "pairs": {
                **state["feature"]["pairs"],
                PAIR: dict(reversed(list(row.items()))),
            },
        },
        "macro_context": {
            **state["macro_context"],
            "features": dict(reversed(list(macro.items()))),
        },
    }
    result = judged(shuffled, context, root, run_id, **{KEY_VETO_THRESHOLD: 1.0})
    assert result.status is EngineStatus.OK, (result.data, result.reason)
    assert result.data["p_wrong"] == pytest.approx(p_wrong, abs=1e-12)


def test_the_published_payload_is_json_serialisable(
    measured: tuple[dict[str, Any], Any, float], root: Path, run_id: str
) -> None:
    state, context, _p_wrong = measured
    json.dumps(judged(state, context, root, run_id).data)


def test_with_no_candidate_it_passes_rather_than_blocking(engine_context: Any) -> None:
    result = SkepticEngine().process(engine_context, {"scout": {}, "prediction": {}})
    assert result.status is EngineStatus.PASS
    assert result.blocks_trading is False
