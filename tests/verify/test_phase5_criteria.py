"""The eleven Phase 5 criteria. Spec 60.

Three observations per criterion, and the third is the one that matters here:

* **PENDING** against a tree where the subject does not exist. A criterion that cannot
  reach that state makes a phase impossible to start.
* **PASS** against the subject as it actually is.
* **FAIL**, deliberately induced against a *plausible* wrong implementation.

**Phase 5 fails quietly, and that changes what a FAIL observation has to be.** Every
phase before this one failed loudly. Here a DI fitted on the wrong rows vetoes ordinary
markets and flatters what survives; a leaked feature makes the Brier beautiful; a lookback
counted in rows produces a number rather than an error. So every induced failure below is
something a careful person would plausibly write, never something broken — an engine that
raises proves nothing about the criterion watching it. One mutation in the spec 63 sweep
was rejected for exactly that: it killed seven tests by raising a polars error, which is a
body count rather than a result.

**Where this file is honestly incomplete, stated rather than implied.** Four criteria have
subjects today and carry all three observations. Seven judge `research/training.py`
(spec 67), engines 13, 15 and 20 (specs 72, 73, 74), and they carry the PENDING
observation plus an assertion that their PENDING names the module or engine that owes
them. Their PASS and FAIL halves are observed when those subjects land, which is the same
sequencing every phase has used, and the criteria are written now so that each spec is
told what to build by the failure rather than by a message.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import ModuleType

import pytest

from tests.verify.test_phase2_criteria import (
    assert_fail,
    assert_pass,
    assert_pending,
    run,
)

#: Registered in this order, and the order is read top to bottom in the report.
PHASE5_CRITERIA = (
    "features_reproduce_in_replay",
    "feature_lookbacks_are_time_not_rows",
    "predictor_trains_and_calibrates",
    "training_is_reproducible_from_config_and_data",
    "di_fitted_on_predictor_training_set",
    "skeptic_trains_only_on_predictor_buy_rows",
    "walkforward_weekly_retrain_reports_oos",
    "anomaly_and_skeptic_have_both_tests",
    "scout_ranks_by_feature_not_arrival",
    "tournament_writes_leaderboard_from_oos",
    "walkforward_trains_on_the_past_only",
)

#: Whose subjects exist today and which therefore carry all three observations.
BUILT = (
    "features_reproduce_in_replay",
    "feature_lookbacks_are_time_not_rows",
    "predictor_trains_and_calibrates",
    "training_is_reproducible_from_config_and_data",
    "walkforward_weekly_retrain_reports_oos",
    "scout_ranks_by_feature_not_arrival",
    "walkforward_trains_on_the_past_only",
)

#: Still waiting on a spec, each with the module or engine its PENDING line must name.
AWAITED = {
    "skeptic_trains_only_on_predictor_buy_rows": "spec 69",
    "anomaly_and_skeptic_have_both_tests": "test_anomaly.py",
    "tournament_writes_leaderboard_from_oos": "`tournament`",
}

#: Waiting on the **operator** rather than on an agent, which is a different state and has
#: a different right answer: nobody is late, and the criterion must say which key it is
#: waiting for rather than accusing the trainer of not writing a DI it was right not to
#: write. Spec 59 decision 7.
WITHHELD = {"di_fitted_on_predictor_training_set": "prediction.di_percentile"}

_NO_PYCACHE = shutil.ignore_patterns("__pycache__", "*.pyc")


@pytest.fixture
def phase5_tree(bare_tree: Path, repo_root: Path) -> Path:
    """The real package, config, migrations, harness and fixtures, copied.

    Deliberately not a fabricated `acsoe`: these criteria drive the real engine 5 over the
    real engine 3's contract, the real feature module and the real ranking function, and a
    FAIL is induced by changing exactly one line in the copy. A tree assembled the other
    way round — fabricated contracts with a real module dropped in — is how
    `check_data_guard_blocks_bad_data` came to have a body that never executed while both
    halves of its proof passed.
    """
    shutil.copytree(repo_root / "src" / "acsoe", bare_tree / "src" / "acsoe", ignore=_NO_PYCACHE)
    shutil.copytree(repo_root / "config", bare_tree / "config")
    shutil.copytree(repo_root / "db", bare_tree / "db", ignore=_NO_PYCACHE)
    tests = bare_tree / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "__init__.py").write_bytes(b"")
    shutil.copytree(repo_root / "tests" / "harness", tests / "harness", ignore=_NO_PYCACHE)
    shutil.copytree(repo_root / "tests" / "fixtures", tests / "fixtures", ignore=_NO_PYCACHE)
    return bare_tree


def patch(root: Path, relative: str, old: str, new: str) -> None:
    """Replace exactly one occurrence of `old` in a copied file.

    **Exactly one.** A patcher that takes the first of several matches mutates something
    other than what it claims to, watches the wrong assertion stay green, and reports a
    proof that has itself stopped being able to fail.

    **Line endings are normalised to LF first, and that is not tidiness.** This repository
    has 136 tracked files that are CRLF in the working tree from before this phase, while
    every file written this session is LF — `.gitattributes` normalises on the way into
    the index, so `git status` says nothing and the two live side by side. A multi-line
    anchor written with `\\n` therefore matches a file created this session and silently
    matches **nothing** in an older one, and the failure is "anchor appears 0 times" a
    long way from the cause. Normalising the copy makes the anchor mean the same thing in
    both. The copy is a throwaway tree, so rewriting its endings costs nothing.
    """
    path = root / relative
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    count = text.count(old)
    if count != 1:
        raise AssertionError(f"{relative}: anchor appears {count} times, expected exactly 1")
    path.write_bytes(text.replace(old, new).encode("utf-8"))


# --------------------------------------------------------------------------- #
# Registration, and the rules that apply to all eleven
# --------------------------------------------------------------------------- #


def test_all_eleven_criteria_are_registered_for_phase_5(verify_module: ModuleType) -> None:
    to_run, skipped = verify_module.criteria_for(5, False)
    assert [c.name for c in to_run] == [
        "docs_vocabulary",
        "toolchain_green",
        *PHASE5_CRITERIA,
    ]
    assert skipped == [], "no Phase 5 criterion is --live; all eleven run on a fresh clone"


def test_registering_phase_5_left_every_earlier_phase_alone(
    verify_module: ModuleType,
) -> None:
    """Adding a criterion to the wrong phase is otherwise silent.

    The counts are pinned rather than the names, because the names are pinned by each
    phase's own file and duplicating them here would mean two places to edit and one of
    them forgotten.
    """
    assert [len(verify_module.criteria_for(phase, True)[0]) for phase in range(5)] == [
        7,
        10,
        9,
        9,
        11,
    ]


def test_every_phase_5_criterion_is_pending_on_an_unbuilt_tree(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    """The state the phase opened in. **Not one of them may FAIL there**: a phase that has
    not been built is unfinished rather than broken, and a FAIL is a stop at any point."""
    for name in PHASE5_CRITERIA:
        assert_pending(run(verify_module, name, unbuilt_tree), verify_module)


def test_the_built_criteria_pass_against_the_real_repository(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """The middle observation, and what stops this file being PENDING assertions dressed
    as a proof.

    Slow: five of these train a predictor over a constructed 140-day dataset. That is the
    cost of a criterion that judges a model rather than a file, and the alternative — a
    committed artefact — would be read from `models/`, which is gitignored, so the
    criterion would pass only on the machine that produced it.
    """
    for name in BUILT:
        assert_pass(run(verify_module, name, repo_root), verify_module)


def test_the_awaited_criteria_name_their_subject_and_never_fail(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """A PENDING that does not say what to build sends its reader to the task list.

    Asserted against the **real** repository rather than an empty tree, because that is
    where the message will actually be read, and because a criterion that reported PENDING
    on an empty tree and FAILed on a half-built one would stop the phase for work nobody
    had started.
    """
    for name, expected in AWAITED.items():
        outcome = run(verify_module, name, repo_root)
        assert_pending(outcome, verify_module)
        assert expected in outcome.message, (name, outcome.message)


def test_a_criterion_waiting_on_the_operator_names_the_key_and_never_fails(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """Waiting on the operator is not the same state as waiting on an agent.

    `prediction.di_percentile` is absent by ruling until the walk-forward reports, and the
    trainer correctly fits no DI without it. A criterion that FAILed here would be accusing
    the trainer of not writing a file it was right not to write — which it did, for one
    run, because the helper tested `value is None` while an absent key arrives as a
    sentinel. Absent and present-but-null are two facts and only one of them can happen
    under this ruling.
    """
    for name, key in WITHHELD.items():
        outcome = run(verify_module, name, repo_root)
        assert_pending(outcome, verify_module)
        assert key in outcome.message, (name, outcome.message)


def test_no_phase_5_criterion_computes_accuracy(verify_module: ModuleType) -> None:
    """Operator ruling, 2026-09-12, and the reason is arithmetic rather than taste: the
    base rate is 23.89%, so a model that always predicts `stop` scores 51% and a criterion
    reporting accuracy would be reporting the model that never trades.

    The word appears in the file only as the thing being refused — in `FORBIDDEN_METRIC`
    and in the messages that name it — so the check is that nothing *computes* one.
    """
    import inspect

    for name in PHASE5_CRITERIA:
        source = inspect.getsource(getattr(verify_module, "check_" + name))
        lowered = source.lower()
        assert "correct /" not in lowered
        assert "hit_rate" not in lowered
        for phrase in ("accuracy =", "accuracy=", '"accuracy":'):
            assert phrase not in lowered, (name, phrase)


def test_no_phase_5_criterion_reads_a_gitignored_path(verify_module: ModuleType) -> None:
    """`data/`, `models/` and `logs/` are gitignored, so a criterion depending on one
    passes only on the machine that produced it. Every artefact these criteria judge is
    trained inside the criterion into a temporary directory."""
    import inspect

    # Through the same detector Phase 0's cross-phase check uses, rather than a second
    # spelling of the rule here. Two checks of one rule drift, and the one that drifts is
    # the copy nobody is looking at.
    from tests.verify.test_phase0_criteria import gitignored_reads

    for name in PHASE5_CRITERIA:
        source = inspect.getsource(getattr(verify_module, "check_" + name))
        assert gitignored_reads(source) == [], (name, gitignored_reads(source))


# --------------------------------------------------------------------------- #
# features_reproduce_in_replay
# --------------------------------------------------------------------------- #


def test_a_feature_module_reading_a_spread_is_a_fail(
    verify_module: ModuleType, phase5_tree: Path
) -> None:
    """The archive is OHLCVT. A feature reading the book is computable live and not in
    replay, so every backtest number it touched describes a model the live loop cannot
    reproduce — and it would reproduce *beautifully* in every test that only ever runs the
    live path."""
    patch(
        phase5_tree,
        "src/acsoe/modelling/features.py",
        '        ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("bar_range_pct"),',
        '        ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("spread"),',
    )
    outcome = run(verify_module, "features_reproduce_in_replay", phase5_tree)
    assert_fail(outcome, verify_module)
    assert "book-derived" in outcome.message


def test_an_engine_5_that_changes_a_number_is_a_fail(
    verify_module: ModuleType, phase5_tree: Path
) -> None:
    """The criterion's central claim: engine 5 may group, cast, truncate and turn NaN into
    null, and it may not move a bit. A rounding on the way out is the plausible version of
    this — it looks like tidying and it silently decorrelates the live features from the
    trained ones.
    """
    patch(
        phase5_tree,
        "src/acsoe/engines/feature/engine.py",
        "    return None if math.isnan(number) or math.isinf(number) else number",
        "    return None if math.isnan(number) or math.isinf(number) else round(number, 6)",
    )
    outcome = run(verify_module, "features_reproduce_in_replay", phase5_tree)
    assert_fail(outcome, verify_module)
    assert "the very same candles" in outcome.message


def test_a_lookback_longer_than_the_published_window_is_a_fail(
    verify_module: ModuleType, phase5_tree: Path
) -> None:
    """The live path is handed `market_sensor.published_bars` candles. A longer lookback
    can never be filled live while the offline builder fills it every time, so the two
    differ on every bar with the offline number being the one that looks right."""
    patch(
        phase5_tree,
        "src/acsoe/modelling/features.py",
        "LOOKBACK_BARS: Final[tuple[int, ...]] = (4, 16, 48, 96)",
        "LOOKBACK_BARS: Final[tuple[int, ...]] = (4, 16, 48, 400)",
    )
    outcome = run(verify_module, "features_reproduce_in_replay", phase5_tree)
    assert_fail(outcome, verify_module)
    assert "MAX_LOOKBACK_BARS" in outcome.message


def test_a_missing_candles_fixture_is_pending_not_a_fail(
    verify_module: ModuleType, phase5_tree: Path
) -> None:
    """An absent committed fixture is work not yet done, not a broken subject."""
    (phase5_tree / "tests" / "fixtures" / "candles_sample.parquet").unlink()
    assert_pending(
        run(verify_module, "features_reproduce_in_replay", phase5_tree), verify_module
    )


# --------------------------------------------------------------------------- #
# feature_lookbacks_are_time_not_rows
# --------------------------------------------------------------------------- #


def test_a_lookback_counted_in_rows_is_a_fail(
    verify_module: ModuleType, phase5_tree: Path
) -> None:
    """Spec 63's first named mutation, in its plausible form: `rolling_sum` where
    `rolling_sum_by` belongs, which is what someone reaching for the row-based API
    actually writes. It does not raise — it reports a full window across a hole and
    computes every z-score over a stretch of market on the far side of a period with no
    trades.
    """
    patch(
        phase5_tree,
        "src/acsoe/modelling/features.py",
        '        pl.col("_one")\n        .rolling_sum_by("_dt", window_size=span, closed="right")\n',
        '        pl.col("_one")\n        .rolling_sum(window_size=bars, min_samples=1)\n',
    )
    outcome = run(verify_module, "feature_lookbacks_are_time_not_rows", phase5_tree)
    assert_fail(outcome, verify_module)
    assert "counted in ROWS" in outcome.message


def test_an_underfilled_window_that_keeps_its_value_is_a_fail(
    verify_module: ModuleType, phase5_tree: Path
) -> None:
    """A number computed over a mostly-absent window is indistinguishable from one
    computed over a full window, which is why it is NaN rather than a value."""
    patch(
        phase5_tree,
        "src/acsoe/modelling/features.py",
        '                .otherwise(float("nan"))\n                .alias(name)',
        "                .otherwise(pl.col(name))\n                .alias(name)",
    )
    outcome = run(verify_module, "feature_lookbacks_are_time_not_rows", phase5_tree)
    assert_fail(outcome, verify_module)
    assert "filled, below" in outcome.message


def test_a_feature_module_with_no_fill_counter_is_pending(
    verify_module: ModuleType, phase5_tree: Path
) -> None:
    """PENDING rather than FAIL: a module without the counter has not implemented the
    contract yet, and the message says which name is missing."""
    patch(
        phase5_tree,
        "src/acsoe/modelling/features.py",
        '    "bars_in_lookback",\n',
        '    "window_fill",\n',
    )
    outcome = run(verify_module, "feature_lookbacks_are_time_not_rows", phase5_tree)
    assert_pending(outcome, verify_module)
    assert "bars_in_lookback_<n>" in outcome.message


# --------------------------------------------------------------------------- #
# scout_ranks_by_feature_not_arrival
# --------------------------------------------------------------------------- #


def test_a_ranking_that_preserves_arrival_order_is_a_fail(
    verify_module: ModuleType, phase5_tree: Path
) -> None:
    """The seam the tracker named before the phase opened, and the exact mutation spec 76
    asks for: `tuple(pairs)`.

    Engine 7 builds its scan set with `sorted`, so this function is always handed an
    already-ordered sequence and a ranking that returned its input would still answer
    alphabetically end to end. The criterion's ascending call is where that stops working.
    """
    patch(
        phase5_tree,
        "src/acsoe/engines/scout/contracts.py",
        "    names = list(pairs)\n",
        "    names = list(pairs)\n    return tuple(names)\n",
    )
    outcome = run(verify_module, "scout_ranks_by_feature_not_arrival", phase5_tree)
    assert_fail(outcome, verify_module)
    assert "ascending" in outcome.message


def test_a_ranking_that_drops_pairs_without_a_value_is_a_fail(
    verify_module: ModuleType, phase5_tree: Path
) -> None:
    """A dropped pair is one engine 7 silently never considered. Engine 5 publishes a null
    feature rather than omitting the pair precisely so this cannot happen upstream, and
    this is the same guarantee at the other end."""
    # Mutated in the **ranked** branch only. Dropping in `names` would also empty the
    # alphabetical answer, and the criterion would then FAIL on its unconfigured
    # assertion instead — a kill for the wrong reason, which is the shape that makes a
    # sweep confident and wrong.
    patch(
        phase5_tree,
        "src/acsoe/engines/scout/contracts.py",
        "    return tuple(sorted(names, key=ordering))",
        "    return tuple(\n"
        "        sorted(\n"
        "            (n for n in names if _feature_value(features, n, feature) is not None),\n"
        "            key=ordering,\n"
        "        )\n"
        "    )",
    )
    outcome = run(verify_module, "scout_ranks_by_feature_not_arrival", phase5_tree)
    assert_fail(outcome, verify_module)
    assert "never dropped" in outcome.message


def test_a_configured_rank_feature_is_a_fail_until_the_operator_rules(
    verify_module: ModuleType, phase5_tree: Path
) -> None:
    """`scout.rank_feature` is the operator's after spec 75's study reports. An agent
    filling it in would be choosing the ranking the study exists to inform, and the
    alphabetical ordering would stop being a recorded absence and become a claim."""
    config = phase5_tree / "config" / "default.yaml"
    text = config.read_bytes().decode("utf-8")
    assert "\nscout:" in text, "the scout section is where rank_feature would be set"
    config.write_bytes(
        text.replace("\nscout:", '\nscout:\n  rank_feature: "log_return_4"', 1).encode("utf-8")
    )
    outcome = run(verify_module, "scout_ranks_by_feature_not_arrival", phase5_tree)
    assert_fail(outcome, verify_module)
    assert "spec 75" in outcome.message


# --------------------------------------------------------------------------- #
# walkforward_trains_on_the_past_only, re-registered
# --------------------------------------------------------------------------- #


def test_the_past_only_criterion_is_the_same_check_under_both_phases(
    verify_module: ModuleType,
) -> None:
    """Re-registered **unchanged**, which is the point: the Phase 5 gate goes red if a
    Phase 5 change weakens the past-only walk-forward.

    Asserted as object identity rather than by name, because a copy that drifted would
    satisfy a name check while checking something else.
    """
    fourth = {c.name: c for c in verify_module.criteria_for(4, True)[0]}
    fifth = {c.name: c for c in verify_module.criteria_for(5, True)[0]}
    assert (
        fourth["walkforward_trains_on_the_past_only"].check
        is fifth["walkforward_trains_on_the_past_only"].check
    )


def test_a_two_sided_walk_forward_fails_the_phase_5_gate(
    verify_module: ModuleType, phase5_tree: Path
) -> None:
    """The whole reason for the re-registration: spec 67 reads `research/walkforward.py`
    and never edits it, and this is what makes that instruction enforceable rather than
    remembered.

    The mutation is the defect operator ruling 1 corrected — training on both sides of the
    test window, which is purged cross-validation: legitimate for choosing
    hyperparameters, and it lets a model see data from after the period it is scored on.
    """
    patch(
        phase5_tree,
        "src/acsoe/research/walkforward.py",
        "            after_test += 1\n            continue",
        "            after_test += 1\n            train.append(index)\n            continue",
    )
    assert_fail(
        run(verify_module, "walkforward_trains_on_the_past_only", phase5_tree), verify_module
    )
