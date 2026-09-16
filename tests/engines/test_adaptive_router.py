"""Spec 97 — engine 14 `adaptive_router`.

**Every assertion here about weights moving is a property of
`tests/fixtures/leaderboard_sample.json`, not of any trained model**, and each one says so
in its own message. The fixture is fabricated and its provenance field says so in the file:
the real leaderboard cannot exercise this rule, because the walk-forward trains one
predictor per fold, so every real model version has exactly one row and every aggregation
across folds gives the same answer.

**The expected weights are recomputed in this module from the rows** rather than read back
from what engine 14 published, and rather than read from the fixture's own `expected`
block. That block exists so a human can see at a glance what the file is for; importing it
would be checking engine 14 against a number somebody typed. Ruling 7, and the shape that
caught Phase 5's calibrator: recompute what the number was supposed to be computed from.

**The rows are real `LeaderboardRow`s written into a real `StoreClient`**, per spec 97
step 7, and read back through B's `all_leaderboard_rows`. They were a stand-in dataclass
until migration 0004 landed `base_rate_brier`, guarded by a test asserting the column was
still missing — which went red the moment it arrived and said in its own message what to
do. That is the whole value of a tripwire on a mock: the mock cannot outlive the thing it
stood in for without somebody being told.
"""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.store.contracts import LeaderboardRow
from acsoe.core.contracts import EngineStatus
from acsoe.engines.adaptive_router.contracts import (
    ACTIVE_MODEL_FIELD,
    BASIS_FIELD,
    DI_MARGIN_FIELD,
    LEADERBOARD_ENUMERATION,
    MODEL_ID,
    REASON_LEADERBOARD_EMPTY,
    REASON_LEADERBOARD_TRUNCATED,
    REASON_LEADERBOARD_UNREADABLE,
    REASON_NO_MODEL_BEATS_ITS_BASE_RATE,
    WEIGHTS_FIELD,
    RouterState,
)
from acsoe.engines.adaptive_router.engine import AdaptiveRouterEngine

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "leaderboard_sample.json"

#: Exact, because the weights are ratios of small exact decimals and a tolerance here
#: would hide a rule that normalised over the unclipped negative skill — which is spec
#: 97's first named mutation and moves the answer in the fourth decimal.
TOLERANCE = 1e-12


def _row(**overrides: Any) -> LeaderboardRow:
    """One real `LeaderboardRow`, defaulted to the shape engine 20 writes.

    The real model rather than a look-alike, so that a field engine 20 stops writing, or
    a constraint the row model gains, reaches these tests instead of being absorbed by a
    double that agrees with whoever wrote it.
    """
    fields: dict[str, Any] = {
        "model_id": MODEL_ID,
        "model_version": "train-stand-in",
        "training_run_id": "train-stand-in",
        "trained_at": 1,
        "fold": "0",
        "n_trades": 0,
        "win_rate": None,
        "brier": None,
        "base_rate_brier": None,
        "net_pnl": None,
        "reporting_currency": "USD",
        "promoted": False,
        "updated_at": 1,
    }
    fields.update(overrides)
    return LeaderboardRow(**fields)


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_bytes().decode("utf-8"))


def _row_objects() -> list[LeaderboardRow]:
    """The fixture's rows as real `LeaderboardRow`s, in file order."""
    return [
        _row(
            model_id=row["model_id"],
            model_version=row["model_version"],
            training_run_id=row["training_run_id"],
            trained_at=row["trained_at"],
            fold=row["fold"],
            n_trades=row["n_trades"],
            win_rate=row["win_rate"],
            brier=row["brier"],
            base_rate_brier=row["base_rate_brier"],
            net_pnl=Decimal(row["net_pnl"]),
            reporting_currency=row["reporting_currency"],
            promoted=row["promoted"],
            updated_at=row["updated_at"],
        )
        for row in _fixture()["rows"]
    ]


def _expected_weights(rows: list[LeaderboardRow]) -> dict[str, float]:
    """The weights recomputed from the rows, independently of the engine.

    Written from the rule as the README states it rather than by calling anything in
    `engines/adaptive_router/`, so this is a second implementation and not a restatement.
    """
    latest: dict[tuple[str, str | None], LeaderboardRow] = {}
    for row in rows:
        if row.model_id != MODEL_ID:
            continue
        key = (row.model_version, row.fold)
        held = latest.get(key)
        if held is None or row.updated_at >= held.updated_at:
            latest[key] = row
    folds: dict[str, list[float]] = defaultdict(list)
    for (version, _fold), row in latest.items():
        if row.brier is None or row.base_rate_brier is None or row.base_rate_brier <= 0:
            folds[version].append(0.0)
        else:
            folds[version].append(max(0.0, 1.0 - row.brier / row.base_rate_brier))
    skills = {version: sum(values) / len(values) for version, values in folds.items()}
    total = sum(skills.values())
    if total <= 0:
        return dict.fromkeys(skills, 0.0)
    return {version: skill / total for version, skill in skills.items()}


class _Store:
    """B's `all_leaderboard_rows(*, model_id)`, modelled faithfully — **including that it
    filters by family itself.**

    The method is reached by name through `LEADERBOARD_ENUMERATION` rather than written
    as a literal, so renaming the constant renames the double with it; otherwise this
    file would go on testing a method engine 14 had stopped calling.

    Filtering here rather than returning everything is the honest model, and it has a
    consequence worth stating: on this path **engine 14's own family filter is
    redundant**, because the store has already applied it. That is why
    `test_a_second_model_family_is_not_weighted` drives the *windowed* store instead —
    the fallback read returns every family, so there the engine's filter is the only
    thing standing between a second family and the normalisation. A double that filtered
    on both paths would make that test green against an engine with no filter at all.
    """

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        self.asked_for: list[str] = []
        setattr(self, LEADERBOARD_ENUMERATION, self._all)

    def _all(self, *, model_id: str) -> list[Any]:
        self.asked_for.append(model_id)
        return [row for row in self._rows if row.model_id == model_id]


class _WindowedOnlyStore:
    """A store with only the console's truncating read, which is the state today."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def leaderboard(self, limit: int = 50) -> list[Any]:
        return list(self._rows[:limit])


def _context(engine_context: Any, store: Any) -> Any:
    object.__setattr__(engine_context.clients, "store", store)
    return engine_context


def _state(**extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "prediction": {
            "model_run_id": "train-20260913T120000-aaaa",
            "di": 0.94,
            "di_threshold": 1.02,
            "is_buy": True,
        },
        "regime": {"label": "trending"},
    }
    state.update(extra)
    return state


def _run(engine_context: Any, store: Any, **extra: Any) -> Any:
    return AdaptiveRouterEngine().process(_context(engine_context, store), _state(**extra))


# --------------------------------------------------------------------------- #
# Registry, and invariant 4
# --------------------------------------------------------------------------- #


def test_it_matches_the_registry_table() -> None:
    engine = AdaptiveRouterEngine()
    assert engine.name == "adaptive_router"
    assert engine.number == 14
    assert engine.is_gate is False


def test_there_is_no_published_field_that_makes_a_trade_more_likely() -> None:
    """Invariant 4 on the published shape rather than on behaviour, the way engine 15
    does it. Engine 14 sits after engine 10 `cost`, so a weight that raised willingness
    to trade would be a model output overriding a gate; one that lowered it would be a
    veto, and only a gate may issue one. A field somebody added later would be reachable
    the moment it existed, so the shape is the enforcement."""
    assert set(RouterState.model_fields) == {
        "weights",
        "active_model_run_id",
        "basis",
        "regime",
        "di_margin",
        "reason_code",
    }


def test_engine_fifteen_does_not_read_this_payload() -> None:
    """Spec 97 step 5, asserted on engine 15's source rather than on engine 14's.

    The claim is about the *consumer*, and mutating engine 14 could never show it. Engine
    15's contracts module names every key it is allowed to reach — contract rule 3 — so
    the absence of this engine's key there is the structural form of "the skeptic's
    verdict does not depend on a weight".
    """
    import acsoe.engines.skeptic.contracts as skeptic_contracts
    import acsoe.engines.skeptic.engine as skeptic_engine

    for module in (skeptic_contracts, skeptic_engine):
        source = Path(module.__file__ or "").read_bytes().decode("utf-8")
        assert "adaptive_router" not in source, (
            f"{module.__name__} names engine 14's state key, so a weight can reach the "
            "last gate before the decision"
        )


def test_the_payload_carries_no_pair_and_no_bar_timestamp(engine_context: Any) -> None:
    """Engine 16's coherence walk checks any payload carrying a `pair` or a bar stamp
    against this tick's candidate. This payload is about model versions rather than about
    the candidate, so carrying either would give engine 16 a field to check that nothing
    here derives from the candidate — agreed with B2 by message before either side landed.
    """
    published = _run(engine_context, _Store(_row_objects())).data
    assert "pair" not in published
    assert "bar_ts" not in published
    assert "closed_bar_ts" not in published


# --------------------------------------------------------------------------- #
# It never blocks, on any path
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "store",
    [
        pytest.param(_Store([]), id="empty-leaderboard"),
        pytest.param(_Store(_row_objects()), id="rows-present"),
        pytest.param(object(), id="no-read-at-all"),
        pytest.param(_WindowedOnlyStore(_row_objects()), id="windowed-only"),
    ],
)
def test_it_returns_ok_on_every_path_that_ran(engine_context: Any, store: Any) -> None:
    """Spec 97 step 5. A non-gate that refused on its own criteria would make `is_gate`
    wrong — the principle the operator applied to engine 16 — and there is nothing here
    for a downstream engine to fail closed on, because nothing downstream reads it to
    decide."""
    result = _run(engine_context, store)
    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.reason is None


# --------------------------------------------------------------------------- #
# The weighting rule, recomputed from the fixture
# --------------------------------------------------------------------------- #


def test_the_weights_are_the_rule_applied_to_the_fixtures_rows(engine_context: Any) -> None:
    """**A property of `leaderboard_sample.json`, not of any trained model.**

    The expected weights are recomputed here from the fixture's rows by a second
    implementation of the rule, never read back from what engine 14 published and never
    imported from the fixture's own `expected` block — a number somebody typed is not a
    check on the code that produces it.
    """
    rows = _row_objects()
    result = _run(engine_context, _Store(rows))
    published = result.data[WEIGHTS_FIELD]
    expected = _expected_weights(rows)

    assert set(published) == set(expected), (
        "engine 14 weighted a different set of model versions than the fixture's rows "
        f"describe: {sorted(published)} against {sorted(expected)}"
    )
    for version, weight in expected.items():
        assert published[version] == pytest.approx(weight, abs=TOLERANCE), (
            f"the weight for {version} is a property of the fixture's briers and base "
            "rates, and it moved"
        )
    assert sum(published.values()) == pytest.approx(1.0, abs=TOLERANCE)


def test_a_version_worse_than_its_base_rate_gets_zero_and_does_not_inflate_the_others(
    engine_context: Any,
) -> None:
    """Spec 97's first named mutation: weights normalised over a model with negative skill.

    **A property of the fixture.** `...cccc` carries brier 0.25 against a base rate of
    0.2, so its raw skill is -0.25. Clipped it contributes nothing; unclipped it would
    *shrink the denominator* and push both other weights above their true share — which
    is a defect that leaves the weights summing to one and every value in range.
    """
    rows = _row_objects()
    published = _run(engine_context, _Store(rows)).data[WEIGHTS_FIELD]
    worse = "train-20260913T120000-cccc"

    assert published[worse] == 0.0, (
        "the fixture's below-base-rate version was given weight, so the clip at zero is "
        "not being applied"
    )
    # The control: with the negative skill left unclipped the denominator would be 0.30
    # rather than 0.55, so the best version would read 1.5 rather than 0.818.
    unclipped_denominator = 0.45 + 0.1 + (1.0 - 0.25 / 0.2)
    assert published["train-20260913T120000-aaaa"] != pytest.approx(
        0.45 / unclipped_denominator, abs=1e-6
    ), "the weights are normalised over an unclipped negative skill"


def test_the_mean_across_a_versions_folds_is_unweighted(engine_context: Any) -> None:
    """The aggregation the lead ruled on, and the fixture is the only thing that can show
    it — on the real table every version has exactly one fold, so the three candidate
    aggregations agree and none of them is tested.

    `...aaaa` has two folds with skills 0.5 and 0.4. The unweighted mean is 0.45; a
    most-recent-fold rule gives 0.4 and a best-fold rule gives 0.5. **A property of the
    fixture.**
    """
    rows = _row_objects()
    result = _run(engine_context, _Store(rows))
    basis = result.data[BASIS_FIELD]["versions"]["train-20260913T120000-aaaa"]

    assert basis["folds_scored"] == 2, (
        "the fixture no longer carries a multi-fold version, so the aggregation across "
        "folds is unreached and this test proves nothing"
    )
    assert basis["mean_skill"] == pytest.approx(0.45, abs=TOLERANCE)
    assert basis["mean_skill"] != pytest.approx(0.4, abs=1e-6), "most-recent-fold rule"
    assert basis["mean_skill"] != pytest.approx(0.5, abs=1e-6), "best-fold rule"


def test_a_second_model_family_is_not_weighted(engine_context: Any) -> None:
    """Spec 97's 'at least two distinct model_ids', and what it is for.

    **A property of the fixture.** `some_other_family` carries the best score in the file
    — brier 0.01, skill 0.95 — so if engine 14 weighted across families it would take
    most of the predictor's weight. There is one family on the real table today, which is
    exactly why this would have gone unnoticed.
    """
    rows = _row_objects()
    families = {row.model_id for row in rows}
    assert len(families) >= 2, "the fixture no longer carries a second model family"

    # The **windowed** read, deliberately: it returns every family, so engine 14's own
    # filter is the only thing excluding this row. B's `all_leaderboard_rows` filters by
    # family itself, so driving that path here would test the store rather than the
    # engine and would stay green against an engine with no filter at all.
    published = _run(engine_context, _WindowedOnlyStore(rows)).data[WEIGHTS_FIELD]
    assert "other-20260913T120000-zzzz" not in published
    assert all(version.startswith("train-") for version in published)


def test_the_enumeration_is_asked_for_this_engines_own_family(
    engine_context: Any,
) -> None:
    """`all_leaderboard_rows` takes `model_id` as a **required** keyword, and B is right
    that it should: the read has no `LIMIT`, and "no limit" is only safe because one
    model's rows are bounded by its walk-forward while the table is bounded by nothing.
    A default would hide the scope at the call site, which is the same fault as the
    truncating window — the caller cannot see what it is getting.

    Asserted on what the store was **asked**, not on what came back, because a filtered
    result is equally consistent with the engine filtering afterwards.
    """
    store = _Store(_row_objects())
    _run(engine_context, store)
    assert store.asked_for == [MODEL_ID]


def test_a_duplicate_row_for_one_fold_is_collapsed_to_the_latest(
    engine_context: Any,
) -> None:
    """Duplicates are not folds, and averaging them would let a duplicate row change a
    weight.

    **A property of the fixture.** `...bbbb` appears twice for fold 0: the superseded row
    carries brier 0.02 (skill 0.9) and the surviving one 0.18 (skill 0.1). Averaged as
    two folds the version would score 0.5; keeping the older row it would score 0.9. B's
    `leaderboard_entries` returns every match on purpose, so that a broken idempotency
    convention stays visible rather than being collapsed silently by the reader — engine
    14 collapses it deliberately and reports how many it collapsed.
    """
    rows = _row_objects()
    result = _run(engine_context, _Store(rows))
    basis = result.data[BASIS_FIELD]["versions"]["train-20260913T120000-bbbb"]

    assert basis["folds_scored"] == 1, "the duplicate was counted as a second fold"
    assert basis["mean_skill"] == pytest.approx(0.1, abs=TOLERANCE), (
        "the superseded duplicate won, or was averaged with the row that supersedes it"
    )


def test_one_model_version_alone_takes_the_whole_weight(engine_context: Any) -> None:
    """The degenerate case, which is the **real** table's case today: one version, weight
    1.0. Without it the normalisation could divide by a count rather than by the sum and
    nothing above would notice, because every other test here has three versions."""
    only = [row for row in _row_objects() if row.model_version.endswith("bbbb")]
    published = _run(engine_context, _Store(only)).data[WEIGHTS_FIELD]
    assert published == {"train-20260913T120000-bbbb": 1.0}


def test_every_version_at_or_below_its_base_rate_is_all_zero_with_a_reason(
    engine_context: Any,
) -> None:
    """Spec 97 step 3: weights sum to one **or are all zero with a reason**. Zero is a
    finding — the leaderboard saying nothing here has edge — rather than a fault, so it
    is `OK` with a code and an actual mapping of zeros rather than an absent one."""
    hopeless = [row for row in _row_objects() if row.model_version.endswith("cccc")]
    result = _run(engine_context, _Store(hopeless))
    assert result.status is EngineStatus.OK
    assert result.data["reason_code"] == REASON_NO_MODEL_BEATS_ITS_BASE_RATE
    assert result.data[WEIGHTS_FIELD] == {"train-20260913T120000-cccc": 0.0}


def test_a_version_with_no_base_rate_gets_zero_rather_than_a_default(
    engine_context: Any,
) -> None:
    """Choosing a default base rate is choosing the line at which a model counts as
    having edge, and that is the operator's.

    **Not a corner case: every leaderboard row written before migration 0004 has none**,
    and B's migration comment says why there is no honest default — `0.0` is a perfect
    baseline and would make every pre-existing model look skill-less, `0.25` is the
    balanced-fold value and would be a guess about folds nobody measured. Absence read as
    absence.
    """
    blind = [_row(model_version="train-no-base-rate", brier=0.01, base_rate_brier=None)]
    result = _run(engine_context, _Store(blind))
    assert result.data[WEIGHTS_FIELD] == {"train-no-base-rate": 0.0}
    assert result.data[BASIS_FIELD]["versions"]["train-no-base-rate"]["folds_scored"] == 0
    assert result.data["reason_code"] == REASON_NO_MODEL_BEATS_ITS_BASE_RATE


# --------------------------------------------------------------------------- #
# Reading the leaderboard
# --------------------------------------------------------------------------- #


def test_an_empty_leaderboard_publishes_no_weights(engine_context: Any) -> None:
    """A fresh clone, and not an error. The key is **absent**, not an empty mapping: an
    empty mapping and 'every weight is zero' are different facts and the second is
    published as a mapping of zeros."""
    result = _run(engine_context, _Store([]))
    assert result.data["reason_code"] == REASON_LEADERBOARD_EMPTY
    assert WEIGHTS_FIELD not in result.data


def test_a_store_with_no_enumerating_read_publishes_no_weights(
    engine_context: Any,
) -> None:
    """Not the same fact as an empty leaderboard, and they must not share a code: one
    means nothing has been trained, the other means engine 14 cannot see what has."""
    result = _run(engine_context, object())
    assert result.data["reason_code"] == REASON_LEADERBOARD_UNREADABLE
    assert WEIGHTS_FIELD not in result.data


def test_a_full_window_publishes_no_weights_rather_than_a_partial_distribution(
    engine_context: Any,
) -> None:
    """The defect this prevents is that **the weights would still sum to one, over the
    wrong set.**

    A version outside the window is absent because nobody looked, not zero because it had
    no edge, and nothing downstream can tell those apart. So a read that comes back
    exactly full publishes nothing at all. The fixture is padded past the probe here
    because the real fixture is six rows and the property is about the window, not about
    these rows.
    """
    from acsoe.engines.adaptive_router.engine import _WINDOWED_PROBE

    padded = [
        _row(
            model_version=f"train-{index:04d}",
            brier=0.1,
            base_rate_brier=0.2,
            updated_at=index + 1,
        )
        for index in range(_WINDOWED_PROBE)
    ]
    result = _run(engine_context, _WindowedOnlyStore(padded))
    assert result.data["reason_code"] == REASON_LEADERBOARD_TRUNCATED
    assert WEIGHTS_FIELD not in result.data


def test_a_window_that_did_not_fill_is_weighted_normally(engine_context: Any) -> None:
    """The other half. Without it, `leaderboard_truncated` is satisfied by an engine that
    refuses every windowed read, which would make the fallback useless rather than
    cautious."""
    result = _run(engine_context, _WindowedOnlyStore(_row_objects()))
    assert result.data["reason_code"] is None
    assert result.data[WEIGHTS_FIELD]


# --------------------------------------------------------------------------- #
# Provenance, which is published and never used
# --------------------------------------------------------------------------- #


def test_the_regime_and_di_margin_are_published(engine_context: Any) -> None:
    """Spec 97 step 4. `di_margin` is `di_threshold - di`, positive when the candidate
    sits inside the reference set."""
    published = _run(engine_context, _Store(_row_objects())).data
    assert published["regime"] == "trending"
    assert published[DI_MARGIN_FIELD] == pytest.approx(1.02 - 0.94)
    assert published[ACTIVE_MODEL_FIELD] == "train-20260913T120000-aaaa"


def test_the_regime_does_not_change_a_single_weight(engine_context: Any) -> None:
    """The lead assented to the regime being provenance only, and this is what holds it
    there. The leaderboard carries one Brier per version over the whole out-of-sample
    window with no regime breakdown, so a regime-conditional weight would be invented
    rather than measured — and an engine that quietly grew one would still publish a
    plausible distribution."""
    rows = _row_objects()
    weights = [
        _run(engine_context, _Store(rows), regime={"label": label}).data[WEIGHTS_FIELD]
        for label in ("trending", "choppy", "high_volatility")
    ]
    assert weights[0] == weights[1] == weights[2], (
        "the weights moved with the regime, which is a methodology this project has no "
        "measurement for"
    )


def test_an_absent_di_publishes_no_margin_rather_than_a_number(
    engine_context: Any,
) -> None:
    """Engine 8 publishes neither `di` nor `di_threshold` on a load failure, and a margin
    computed from one of them would be a number about nothing."""
    published = _run(
        engine_context, _Store(_row_objects()), prediction={"model_run_id": None}
    ).data
    assert published[DI_MARGIN_FIELD] is None
    assert published[ACTIVE_MODEL_FIELD] is None


# --------------------------------------------------------------------------- #
# The stand-in, and the tripwire that retires it
# --------------------------------------------------------------------------- #


def test_the_rows_these_tests_use_are_the_real_row_model() -> None:
    """What the retired stand-in tripwire handed over to.

    `_Row`, a dataclass carrying `base_rate_brier` when `LeaderboardRow` had no such
    field, was guarded by a test asserting the column was still missing — it went red the
    moment migration 0004 landed and its message said to re-point these tests at the real
    model and delete it. This is the assertion that replaces it, so the file cannot drift
    back to a look-alike without something objecting.
    """
    assert "base_rate_brier" in LeaderboardRow.model_fields
    assert all(isinstance(row, LeaderboardRow) for row in _row_objects())


def test_the_fixture_is_declared_fabricated() -> None:
    """Spec 97 step 6. The provenance line is not decoration: these numbers describe no
    trained model, and a reader who took them for a measurement would conclude the
    predictor beats its base rate by a wide margin."""
    doc = _fixture()
    assert "FABRICATED" in doc["provenance"]
    assert "no trained model" in doc["provenance"]
    assert doc["rule_under_test"]
    for row in doc["rows"]:
        assert row["why"], "a fixture row that does not say what it is for"
