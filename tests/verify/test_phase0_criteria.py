"""The six Phase 0 criteria. Spec 01 step 4.

Each criterion is proved **twice**: PENDING against a tree where its subject does
not exist, and PASS against a minimal fabricated subject. That pairing is the
whole design. A criterion asserted only in the PENDING direction can be one that
never manages to check anything; a criterion asserted only in the PASS direction
can be one that would pass on an empty repository. Neither half is worth much
alone, and Phase 0's criteria are written before the code they judge, so both
halves have to be provable before that code exists.

A third direction is proved wherever a criterion has a real failure mode - a
missing table, a short outage run, a mismatched `is_gate` - because those are the
defects the gate exists to catch and a check that has never gone red is a comment.

One rule cuts across all six and is asserted on its own below: **a criterion that
cannot run because the interpreter lacks a project dependency reports FAIL, not
PENDING.** PENDING means the subject does not exist yet. A broken environment
reporting as orderly progress is worse than a red gate, because the phase sits at
"no FAIL" while nothing is actually being checked.
"""

from __future__ import annotations

import re
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import pytest

from tests.verify.conftest import (
    CHAINS_CONTRACT,
    DOCUMENTED_TABLES,
    EMPTY_BOOTSTRAP,
    EMPTY_OFFLINE_CHAIN,
    ENGINE_STUB,
    ORCHESTRATOR,
    RECORD_GAP,
    RECORD_SESSION,
    RECORD_TICK,
    SCALING_SEED_DEFAULT_ERRORS,
    SCALING_SEED_MODULE,
    SEED_MODULE,
    SEED_MODULE_WITHOUT_THRESHOLD_CLASS,
    fabricate_config,
    fabricate_package,
    migrations_module,
    offline_chain_module,
    registry_bootstrap,
    write_record_sample,
)


def run(verify_module: ModuleType, check: str, root: Path) -> Any:
    """Call one criterion against `root`, through the runner's exception guard.

    Routed through `run_criterion` rather than called directly so a criterion that
    raises shows up here as the FAIL the runner would print, not as a test error.
    """
    return verify_module.run_criterion(
        verify_module.Criterion(check, getattr(verify_module, "check_" + check)),
        verify_module.VerifyContext(root=root),
    )


#: How many engines `orchestrator_empty_registry` reported finding in the registry.
#:
#: **Read out of the message rather than matched as a substring**, and the difference is
#: a lesson rather than a preference. Two tests below used to assert
#: `"0 registered engines" in outcome.message`, and both went red the day the message
#: gained one clarifying word — a change that improved the report and broke nothing.
#: A substring match on an English sentence taxes exactly the improvements you most want
#: someone to make, and the tax is paid in red tests that look like regressions.
#:
#: What these tests care about is the **count**. The wording is a separate claim with a
#: separate hazard, and it has its own test — `test_the_engine_count_says_runtime_so_it_
#: cannot_be_read_against_the_registry_total` — so that "the number is right" and "the
#: sentence is unambiguous" fail independently and for their own reasons.
#: Two patterns because the two criteria word it in opposite orders —
#: `orchestrator_empty_registry` says "N registered runtime engines" and
#: `is_gate_matches_registry` says "N engines registered". That is not a defect worth
#: fixing (each reads well in its own sentence) but it is worth noticing: two lines of
#: one report describing the same kind of thing in two shapes is part of why their
#: differing totals read as a contradiction rather than as two different questions.
_ENGINE_COUNTS = (
    re.compile(r"(\d+) registered(?: \w+)? engines"),
    re.compile(r"(\d+) engines registered"),
)


def reported_engine_count(message: str) -> int:
    for pattern in _ENGINE_COUNTS:
        match = pattern.search(message)
        if match is not None:
            return int(match.group(1))
    raise AssertionError(f"no engine count in the message: {message!r}")


def sql_tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}


# --------------------------------------------------------------------------- #
# The fabrication actually shadows the installed package
# --------------------------------------------------------------------------- #


def test_fabrication_actually_shadows_the_real_package(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Everything below depends on this and none of it would fail loudly without it.

    The editable install is a plain `.pth` adding `src` to `sys.path` - no meta-path
    finder - so `root_import_path` inserting a fabricated `src` at `sys.path[0]`
    genuinely shadows the installed `acsoe`. If that install mechanism ever changes
    to something with import priority, every fabricated-subject test below would
    silently start testing the *real* package and keep passing while proving
    nothing. This asserts the shadowing directly.
    """
    fabricate_package(bare_tree, {"acsoe.marker": "VALUE = 'fabricated'\n"})
    with verify_module.root_import_path(bare_tree):
        import acsoe.marker  # type: ignore[import-not-found]

        assert acsoe.marker.VALUE == "fabricated"
        assert str(bare_tree) in str(Path(acsoe.marker.__file__ or "").resolve())

    # And the real interpreter is put back exactly as it was.
    import acsoe

    assert "marker" not in dir(acsoe)


# --------------------------------------------------------------------------- #
# Every criterion is quiet, not loud, on a tree with nothing built
# --------------------------------------------------------------------------- #

#: Each criterion with the tree that represents "its subject does not exist yet".
#:
#: Two of them need `unbuilt_tree` rather than `bare_tree`, and the reason is worth
#: stating: the editable install puts the real `acsoe` on `sys.path` from any
#: working directory, so a criterion pointed at a tree with no `src/` at all
#: happily imports the developer's own `bootstrap.py` and reports on that. Writing
#: an empty `src/acsoe/` into the tree restores the shadowing. `toolchain_green` is
#: the exact opposite - it keys off `src/` being absent - which is why this is a
#: table rather than one fixture for everybody.
PHASE0_SUBJECT_CRITERIA = [
    ("orchestrator_empty_registry", "unbuilt_tree"),
    ("db_migrates_from_empty", "bare_tree"),
    ("seed_fixtures_present", "bare_tree"),
    ("record_sample_valid", "bare_tree"),
    ("toolchain_green", "bare_tree"),
    ("is_gate_matches_registry", "unbuilt_tree"),
]


@pytest.mark.parametrize(("name", "tree_fixture"), PHASE0_SUBJECT_CRITERIA)
def test_every_criterion_is_pending_on_a_tree_with_nothing_built(
    verify_module: ModuleType, request: pytest.FixtureRequest, name: str, tree_fixture: str
) -> None:
    """Spec 01 step 2, and spec 00's "no traceback on a tree without src/".

    PENDING is what lets C write these before A, B and the lead build the things
    they judge. A criterion that FAILed here would make Phase 0 unstartable; one
    that raised would take the other six down with it.
    """
    root: Path = request.getfixturevalue(tree_fixture)
    outcome = run(verify_module, name, root)
    assert outcome.result is verify_module.Result.PENDING, f"{name}: {outcome.message}"
    assert outcome.message


@pytest.mark.parametrize(("name", "tree_fixture"), PHASE0_SUBJECT_CRITERIA)
def test_a_pending_message_names_the_missing_subject(
    verify_module: ModuleType, request: pytest.FixtureRequest, name: str, tree_fixture: str
) -> None:
    """A PENDING nobody can act on is indistinguishable from a check that is
    switched off. Every one of them names the file, module or symbol it wants."""
    root: Path = request.getfixturevalue(tree_fixture)
    message = run(verify_module, name, root).message
    assert any(cue in message for cue in ("does not exist", "no engine registry", "holds no"))


# --------------------------------------------------------------------------- #
# orchestrator_empty_registry
# --------------------------------------------------------------------------- #


def fabricate_orchestrator(root: Path, bootstrap: str = EMPTY_BOOTSTRAP) -> None:
    fabricate_package(
        root,
        {
            "acsoe.bootstrap": bootstrap,
            "acsoe.core.contracts": CHAINS_CONTRACT,
            "acsoe.core.orchestrator": ORCHESTRATOR,
        },
    )


def test_orchestrator_passes_against_a_minimal_registry_and_tick(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """An empty chain is valid - the orchestrator skips an unregistered engine and
    logs at debug level. Phase 0 registers none at all, so this is the shape the
    criterion has to accept."""
    fabricate_orchestrator(tree_with_harness)
    outcome = run(verify_module, "orchestrator_empty_registry", tree_with_harness)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    assert reported_engine_count(outcome.message) == 0


def test_the_engine_count_says_which_engines_it_counted(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """Two PASS lines in one report quote different totals, and both are right.

    `orchestrator_empty_registry` counts `acsoe.bootstrap`'s three **runtime** chains.
    `is_gate_matches_registry` counts those *plus* the offline chain in
    `cli/research.py`, where engine 23 `backtest` and engine 20 `tournament` live and are
    deliberately never registered in `bootstrap.py`. Nine and eleven, adjacent, in the
    report somebody reads to decide whether a phase closes — which invites either a hunt
    for a bug that does not exist, or a shrug that trains the reader past the day the
    numbers genuinely disagree.

    One word fixes it and one word is easy to tidy away, so it is pinned here rather
    than left to the comment at the call site. **This is a separate claim from the
    count**, which is why it is a separate test: the counts above read the number out of
    the message and no longer care how the sentence is worded, and this one cares about
    nothing else. Each fails for its own reason.

    Run against the real repository on purpose. The ambiguity only exists when both
    criteria are reporting real registries, and a fabricated tree would make the
    assertion true of a sentence nobody will ever read.
    """
    empty = run(verify_module, "orchestrator_empty_registry", repo_root)
    total = run(verify_module, "is_gate_matches_registry", repo_root)
    assert empty.result is verify_module.Result.PASS, empty.message
    assert total.result is verify_module.Result.PASS, total.message

    # The premise: the two counts really do differ, so the disambiguation is load
    # bearing rather than a precaution. If they ever coincide this test should be
    # reconsidered, not deleted - it would mean the offline chain had emptied.
    assert reported_engine_count(empty.message) != reported_engine_count(total.message)

    # **The difference is asked of the offline chain rather than written down here.** It
    # was a literal `1`, standing for engine 23 alone, and it went red the day engine 20
    # joined the chain - correctly, but for a reason that has nothing to do with what this
    # test is about. Replacing the 1 with a 2 would be the same mistake with a different
    # number; `cli/research.py` is the thing that knows, so it is the thing asked.
    from acsoe.cli.research import build_offline_chain

    offline = len(build_offline_chain())
    assert offline >= 1, "the offline chain is empty, so there is nothing to disambiguate"
    assert reported_engine_count(empty.message) + offline == reported_engine_count(
        total.message
    ), (
        "the two counts no longer differ by the size of the offline chain. One of them has "
        "started counting a set the other does not, and the report's two totals would then "
        "disagree for a reason nobody could name."
    )

    assert "runtime engines" in empty.message, (
        "the smaller count no longer says which engines it counted; beside "
        "is_gate_matches_registry's larger total it reads as a contradiction"
    )


def test_orchestrator_is_pending_when_a_chain_symbol_is_missing(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """A partially built registry is still an absent subject, and the message says
    which of the three symbols has not landed."""
    fabricate_orchestrator(tree_with_harness, bootstrap="GUARD_CHAIN = ()\n")
    outcome = run(verify_module, "orchestrator_empty_registry", tree_with_harness)
    assert outcome.result is verify_module.Result.PENDING
    assert "OPPORTUNITY_CHAIN" in outcome.message


def test_orchestrator_fails_when_a_tick_loses_the_persistent_system_region(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """`state["system"]` is the one region carried across ticks. A tick that
    returned a state without it would mean mode and `close_intent` were being
    rebuilt every minute - and an interrupted `close_all` would evaporate."""
    fabricate_package(
        tree_with_harness,
        {
            "acsoe.bootstrap": EMPTY_BOOTSTRAP,
            "acsoe.core.contracts": CHAINS_CONTRACT,
            "acsoe.core.orchestrator": ORCHESTRATOR.replace(
                '"system": {"mode": "idle", "close_intent": False},', ""
            ),
        },
    )
    outcome = run(verify_module, "orchestrator_empty_registry", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "system" in outcome.message


def test_orchestrator_fails_when_guard_blockers_is_absent_rather_than_empty(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The contract says an empty list on an unblocked tick, **never absent**.

    Absent and empty are the same thing to a careless reader and opposite things to
    engine 19, which writes one `block_records` row per entry. Absent would make the
    outage counter unbuildable.
    """
    fabricate_package(
        tree_with_harness,
        {
            "acsoe.bootstrap": EMPTY_BOOTSTRAP,
            "acsoe.core.contracts": CHAINS_CONTRACT,
            "acsoe.core.orchestrator": ORCHESTRATOR.replace('"guard_blockers": [],', ""),
        },
    )
    outcome = run(verify_module, "orchestrator_empty_registry", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "guard_blockers" in outcome.message


# --------------------------------------------------------------------------- #
# db_migrates_from_empty
# --------------------------------------------------------------------------- #


def fabricate_migrations(
    root: Path,
    created: tuple[str, ...] = DOCUMENTED_TABLES,
    declared: tuple[str, ...] | None = DOCUMENTED_TABLES,
) -> None:
    migrations = root / "db" / "migrations"
    migrations.mkdir(parents=True, exist_ok=True)
    (migrations / "0001_initial.sql").write_text("-- fabricated\n", encoding="utf-8")
    fabricate_package(
        root, {"acsoe.clients.store.migrations": migrations_module(created, declared)}
    )


def test_db_passes_against_a_runner_that_builds_the_documented_tables(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    fabricate_migrations(bare_tree)
    outcome = run(verify_module, "db_migrates_from_empty", bare_tree)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    assert "all 9 documented tables" in outcome.message


def test_db_is_pending_when_the_sql_exists_but_the_runner_does_not(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    """B's `.sql` and B's runner land separately; neither half alone is a subject."""
    (unbuilt_tree / "db" / "migrations").mkdir(parents=True)
    (unbuilt_tree / "db" / "migrations" / "0001_initial.sql").write_text("--\n", encoding="utf-8")
    outcome = run(verify_module, "db_migrates_from_empty", unbuilt_tree)
    assert outcome.result is verify_module.Result.PENDING
    assert "migrations" in outcome.message


def test_db_is_pending_when_the_directory_holds_no_sql(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    (bare_tree / "db" / "migrations").mkdir(parents=True)
    outcome = run(verify_module, "db_migrates_from_empty", bare_tree)
    assert outcome.result is verify_module.Result.PENDING
    assert "no .sql" in outcome.message


def test_db_fails_when_a_documented_table_is_missing(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """`block_records` is its own table for a reason: folding blocks into
    `rejections` would inflate the counterfactual dataset with feed outages. Losing
    it silently is exactly what this criterion is for."""
    short = tuple(t for t in DOCUMENTED_TABLES if t != "block_records")
    fabricate_migrations(bare_tree, created=short, declared=DOCUMENTED_TABLES)
    outcome = run(verify_module, "db_migrates_from_empty", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "block_records" in outcome.message


def test_db_fails_when_the_runner_declares_a_table_set_the_documents_do_not(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """The schema is B's and the storage model is the lead's. A drift between the
    two is a schema change that never went through the lead."""
    extra = (*DOCUMENTED_TABLES, "shadow_ledger")
    fabricate_migrations(bare_tree, created=extra, declared=extra)
    outcome = run(verify_module, "db_migrates_from_empty", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "shadow_ledger" in outcome.message


def test_db_migrates_into_a_temporary_file_and_never_into_data(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Spec 01 step 3, and the fresh-clone rule: `data/` is gitignored, so no
    criterion may read or write anything inside it."""
    fabricate_migrations(bare_tree)
    run(verify_module, "db_migrates_from_empty", bare_tree)
    assert not (bare_tree / "data").exists()


# --------------------------------------------------------------------------- #
# seed_fixtures_present
# --------------------------------------------------------------------------- #


def fabricate_seed(root: Path, module: str = SEED_MODULE, **thresholds: object) -> None:
    fabricate_config(root, **thresholds)
    fabricate_package(root, {"acsoe.clients.store.seed": module})


def test_seed_passes_when_all_six_fixtures_are_present(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Every one of `safety`'s inputs is written by engine 19, which is Phase 4, so
    Phase 3 tests the breaker against this seed. All six have to be there."""
    fabricate_seed(bare_tree)
    outcome = run(verify_module, "seed_fixtures_present", bare_tree)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    assert "all six fixtures present" in outcome.message
    assert "5 ticks over 2 run_ids" in outcome.message


def test_seed_is_pending_while_a_threshold_is_operator_required(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """A `null` marked OPERATOR REQUIRED is not a defect in anyone's work.

    The criterion cannot know whether the seed is past a limit nobody has set, and
    guessing a drawdown limit to make the check convenient would be inventing
    trading behaviour. So it reports PENDING naming the key - which is what turns
    the missing decision into a visible one.
    """
    fabricate_seed(bare_tree, max_drawdown_pct=None)
    outcome = run(verify_module, "seed_fixtures_present", bare_tree)
    assert outcome.result is verify_module.Result.PENDING
    assert "safety.max_drawdown_pct" in outcome.message
    assert "OPERATOR REQUIRED" in outcome.message


def test_seed_counts_a_double_blocked_tick_once(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Two guards blocking on one tick contributes one to the outage count.

    The fabricated seed's five-tick run carries seven block rows, two of them
    co-occurring `safety` blockers. A criterion counting *rows* would report seven
    and the breaker built on it would fire two ticks early.
    """
    fabricate_seed(bare_tree)
    seed = bare_tree / "seeded.sqlite"
    with verify_module.root_import_path(bare_tree):
        from acsoe.clients.store.seed import seed_database  # type: ignore[import-not-found]

        seed_database(seed)
    conn = sqlite3.connect(seed)
    try:
        assert verify_module._count(conn, "SELECT COUNT(*) FROM block_records") == 7
        length, run_ids, doubles = verify_module._seeded_block_run(conn)
    finally:
        conn.close()
    assert (length, run_ids, doubles) == (5, 2, 2)


def test_seed_fails_when_the_outage_run_does_not_beat_the_threshold(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """`safety` escalates once the count is *past* the limit, so a run merely equal
    to it proves nothing. The seed has to be strictly longer."""
    fabricate_seed(bare_tree, max_consecutive_data_blocks=5)
    outcome = run(verify_module, "seed_fixtures_present", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "not longer than" in outcome.message


def test_seed_fails_when_the_outage_run_sits_inside_one_run_id(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """The two-run property is the whole point of the fixture: the counter has to
    survive a restart, and ordering by `cycle_id` instead of `ts` would silently
    interleave two runs. A single-run seed can never prove that."""
    single_run = SEED_MODULE.replace('("run-b", 1, "safety")', '("run-a", 3, "safety")').replace(
        '("run-b", 2, None)', '("run-a", 4, None)'
    ).replace('("run-b", 3, None)', '("run-a", 5, None)')
    fabricate_seed(bare_tree, module=single_run)
    outcome = run(verify_module, "seed_fixtures_present", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "run_id" in outcome.message


def test_seed_fails_when_there_is_no_resting_entry_order(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Invariant 14 requires an open position **or a resting entry order** before
    `safety` escalates. A resting post-only buy is exposure that has not happened
    yet, and a seed without one cannot exercise that half of the precondition."""
    without = SEED_MODULE.replace(
        'conn.execute("INSERT INTO orders VALUES (?,?)", (1234, "resting"))', "pass"
    )
    fabricate_seed(bare_tree, module=without)
    outcome = run(verify_module, "seed_fixtures_present", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "resting entry order" in outcome.message


def test_seed_fails_when_the_fixture_accessor_disagrees_with_its_own_rows(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """The criterion derives all six from SQL *and* cross-checks the declared
    fixtures.

    A gate that trusted the accessor could not catch the case it exists for:
    `SeedFixtures` reporting an 18-tick outage while `block_records` holds five is
    precisely the defect, and asserting on the field alone reports PASS.
    """
    lying = SEED_MODULE.replace("_Run(len(OUTAGE))", "_Run(18)")
    fabricate_seed(bare_tree, module=lying)
    outcome = run(verify_module, "seed_fixtures_present", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "declares an outage run of 18" in outcome.message


def test_seed_hands_the_configured_thresholds_to_the_generator(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Spec 13 makes the seed's thresholds **injected, not read from config**, so
    handing it the real numbers is the criterion's job.

    This is a regression test for a real defect. The criterion loaded the config
    thresholds, asserted every fixture against them, and seeded with the module's
    own defaults - so the moment the operator raised `safety.max_errors_in_window`
    from 10 to 20 the seed went on generating 13 error rows and the criterion
    FAILed, accusing the seed of a shortfall the criterion had caused.

    The fabricated seed here scales every fixture off the injected threshold and
    defaults to `SCALING_SEED_DEFAULT_ERRORS`, far below what the config asks for.
    A criterion that does not inject falls back to that default and cannot pass.
    """
    fabricate_seed(
        bare_tree,
        module=SCALING_SEED_MODULE,
        max_consecutive_data_blocks=4,
        max_drawdown_pct=0.10,
        max_consecutive_losses=2,
        max_errors_in_window=9,
        error_rate_window_s=3600,
    )
    outcome = run(verify_module, "seed_fixtures_present", bare_tree)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    # 9 + 3, which is only reachable from the configured 9. The module default is
    # SCALING_SEED_DEFAULT_ERRORS, which would have produced 4 and FAILed.
    assert "12 ERROR blocks in the window" in outcome.message
    assert SCALING_SEED_DEFAULT_ERRORS + 3 < 9


def test_seed_fails_when_the_generator_has_no_threshold_class_to_inject(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """A `thresholds` argument with nothing to build one from is a broken seed
    surface, not an absent subject - so it is FAIL, and the criterion refuses
    before seeding rather than quietly falling back to the defaults."""
    fabricate_seed(bare_tree, module=SEED_MODULE_WITHOUT_THRESHOLD_CLASS)
    outcome = run(verify_module, "seed_fixtures_present", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "SeedThresholds" in outcome.message


def test_seed_fails_when_the_threshold_class_rejects_the_configured_keys(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """If the seed renames a threshold field, the criterion says so by name rather
    than crashing or silently seeding with defaults."""
    renamed = SCALING_SEED_MODULE.replace(
        "max_errors_in_window: int = 1", "max_engine_errors: int = 1"
    ).replace("thresholds.max_errors_in_window", "thresholds.max_engine_errors")
    fabricate_seed(bare_tree, module=renamed)
    outcome = run(verify_module, "seed_fixtures_present", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "max_errors_in_window" in outcome.message


# --------------------------------------------------------------------------- #
# record_sample_valid
# --------------------------------------------------------------------------- #


def test_record_sample_passes_on_a_sample_carrying_every_kind(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    write_record_sample(bare_tree, (RECORD_SESSION, RECORD_TICK, RECORD_GAP))
    outcome = run(verify_module, "record_sample_valid", bare_tree)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    assert "3 lines valid" in outcome.message


def test_record_sample_fails_when_a_kind_is_absent(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Order book and spread history can never be recovered retroactively, so the
    sample has to exercise the marker path. A ticks-only sample would let a
    validator that never handles a gap marker look correct."""
    write_record_sample(bare_tree, (RECORD_TICK,))
    outcome = run(verify_module, "record_sample_valid", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "gap" in outcome.message


def test_record_sample_fails_on_a_line_that_is_not_json(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    write_record_sample(bare_tree, (RECORD_SESSION, RECORD_TICK, RECORD_GAP, "{not json"))
    outcome = run(verify_module, "record_sample_valid", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "line 4" in outcome.message


def test_record_sample_fails_without_a_trailing_newline(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Recordings are append-only. A file whose last line has no newline makes the
    next appended line a corruption of the previous one, and invariant 11 forbids
    editing a recording in place to fix it."""
    path = write_record_sample(bare_tree, (RECORD_SESSION, RECORD_TICK, RECORD_GAP))
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")
    outcome = run(verify_module, "record_sample_valid", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "newline" in outcome.message


# --------------------------------------------------------------------------- #
# toolchain_green
# --------------------------------------------------------------------------- #


def make_toolchain_roots(verify_module: ModuleType, tree: Path) -> None:
    """Every directory the toolchain reads, so the existence guard lets a run through.

    Read off `TOOLCHAIN_ROOTS` rather than written out, for the reason the constant
    is itself derived: a hand-written list here would stop matching the moment the
    toolchain covered one more directory, and every test below would quietly become
    a test of the PENDING branch while still reading as a test of the retry logic.
    """
    for root in verify_module.TOOLCHAIN_ROOTS:
        (tree / root).mkdir(parents=True, exist_ok=True)


def test_toolchain_is_pending_before_src_exists(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    outcome = run(verify_module, "toolchain_green", bare_tree)
    assert outcome.result is verify_module.Result.PENDING
    assert "src/" in outcome.message


def test_toolchain_is_pending_when_any_one_covered_directory_is_absent(
    verify_module: ModuleType, bare_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each covered directory on its own, because the guard reads a list.

    An absent directory handed to ruff or mypy is exit 2 and "file or directory not
    found". That is a FAIL, and it reads as a broken environment - the same verdict
    the criterion gives when the toolchain is not installed - standing where "this
    has not been built yet" belongs. `_run_tool` is stubbed to a crash so that a
    guard which let the run through would be caught by the result rather than by
    however the real tools happened to behave.
    """
    monkeypatch.setattr(
        verify_module, "_interpreter_with_toolchain", lambda root: ("python.exe", [])
    )
    monkeypatch.setattr(
        verify_module,
        "_run_tool",
        lambda interpreter, args, root, env: (3221225477, "should never be reached"),
    )
    for absent in verify_module.TOOLCHAIN_ROOTS:
        tree = bare_tree / ("without-" + absent.strip("/"))
        tree.mkdir()
        for root in verify_module.TOOLCHAIN_ROOTS:
            if root != absent:
                (tree / root).mkdir(parents=True)
        outcome = run(verify_module, "toolchain_green", tree)
        assert outcome.result is verify_module.Result.PENDING, absent
        assert outcome.message == "does not exist yet: " + absent


def test_the_toolchain_reads_tests_and_scripts_and_not_src_alone(
    verify_module: ModuleType,
) -> None:
    """The widening itself, pinned so that narrowing it back goes red.

    All three commands were scoped to `src/` until Phase 4, and a file under `tests/`
    carrying a syntax error on the declared Python went unseen by the gate for a whole
    phase as a result. Nothing asserted the coverage, so nothing would have objected to
    it being written back - and it would have read as a tidy-up. `mypy` is asserted
    *not* to cover `tests/`, because that exclusion is a deliberate decision with a
    stated reason rather than an oversight, and an exclusion nobody wrote down gets
    quietly "fixed" by the next person who notices it.
    """
    covered = {name: set(args) for name, args, _max_exit in verify_module.TOOLCHAIN}

    assert "tests/" in covered["pytest"]
    assert {"src/", "scripts/"} <= covered["mypy"]
    assert {"src/", "tests/", "scripts/"} <= covered["ruff"]
    assert "tests/" not in covered["mypy"]
    assert set(verify_module.TOOLCHAIN_ROOTS) == {"src/", "tests/", "scripts/"}


def test_ruff_over_tests_catches_a_syntax_error_on_the_declared_python(
    verify_module: ModuleType, repo_root: Path, tmp_path: Path
) -> None:
    """The defect the widening was ruled for, end to end.

    `tests/scripts/test_fixture_bytes.py` was committed in Phase 4 carrying a
    backslash escape inside an f-string expression. That is legal from Python 3.12
    and a **SyntaxError on 3.11**, which is what `requires-python`, `python_version`
    and `target-version` all declare. The venv is 3.13, so pytest imported it and
    every test passed; `ruff check src/` cannot see a file under `tests/`. Nothing in
    the gate could report it.

    Two separate claims, and the defect needs both: that the project still declares
    3.11, and that ruff run under the project's own configuration refuses the form.
    Asserting only the second with an explicit `--target-version py311` would keep
    passing after somebody raised the floor in `pyproject.toml`, which is the change
    that would make this whole criterion stop meaning anything.
    """
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'target-version = "py311"' in pyproject
    assert 'requires-python = ">=3.11"' in pyproject

    offender = tmp_path / "carries_a_3_11_syntax_error.py"
    # The offending line is assembled rather than written out. A module that
    # *contains* the defect cannot be parsed by the interpreter the defect is about,
    # so on 3.11 this file would fail to import rather than run - and ruff, now that
    # it reads `tests/`, would flag this very module on every gate run.
    backslash = chr(92)
    offender.write_text(
        'raw = b""\n'
        'message = f"carries {raw.count(b\'' + backslash + 'x0d\')} CRLF"\n',
        encoding="utf-8",
    )
    done = subprocess.run(  # fixed argv, never a shell
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--output-format=concise",
            "--config",
            str(repo_root / "pyproject.toml"),
            str(offender),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    output = done.stdout + done.stderr
    assert done.returncode == 1, output
    assert "escape sequence" in output, output
    assert "Python 3.11" in output, output


def test_toolchain_fails_rather_than_pends_when_the_environment_lacks_the_tools(
    verify_module: ModuleType, bare_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule that matters most in this module.

    `src/` exists, so the *subject* exists; it is the environment that is broken.
    Reporting that as PENDING would let the phase sit at "no FAIL" while pytest,
    mypy and ruff were never run at all - a green-looking gate checking nothing.
    The message has to carry the fix, because the operator reading it is the person
    who has to apply it.
    """
    make_toolchain_roots(verify_module, bare_tree)
    monkeypatch.setattr(
        verify_module, "_interpreter_with_toolchain", lambda root: (None, ["mypy", "ruff"])
    )
    outcome = run(verify_module, "toolchain_green", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "mypy, ruff" in outcome.message
    assert ".venv" in outcome.message or "pip install" in outcome.message


def test_toolchain_does_not_recurse_into_itself(
    verify_module: ModuleType, bare_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`toolchain_green` shells out to pytest, and `pytest` runs this file. Without
    the guard the run forks forever."""
    monkeypatch.setenv(verify_module.RECURSION_GUARD_ENV, "1")
    outcome = run(verify_module, "toolchain_green", bare_tree)
    assert outcome.result is verify_module.Result.PENDING
    assert "subprocess" in outcome.message


# A returncode alone cannot tell "the suite failed" from "the suite passed and the
# process then died". The four below assert that distinction. The second case is the
# one that matters: it is indistinguishable from a flaky test through a returncode,
# and a memory fault filed as a flaky test gets re-run until it goes green.


def test_summary_line_is_read_from_the_end_of_the_output(verify_module: ModuleType) -> None:
    """The counts words also appear in the progress output above the summary."""
    assert verify_module.pytest_summary_line("520 passed in 12.68s") == "520 passed in 12.68s"
    assert (
        verify_module.pytest_summary_line("....\n=== 1 failed, 519 passed in 13.0s ===")
        == "1 failed, 519 passed in 13.0s"
    )
    assert verify_module.pytest_summary_line("Windows fatal exception") is None


def test_a_crash_after_every_test_passed_is_reported_as_a_crash(
    verify_module: ModuleType,
) -> None:
    """The insidious case, and the reason this code exists.

    pytest printed `520 passed` and the process then died of a memory fault. Through
    a returncode alone that reads as a failing suite, so the message has to say both
    that it crashed and that the tests had already passed - otherwise the next
    person re-runs it, sees green, and the fault stays in the tree.
    """
    message = verify_module.describe_exit(
        "pytest", 3221225477, ".....\n520 passed in 12.68s\nWindows fatal exception", 5
    )
    assert "CRASHED" in message
    assert "0xC0000005 ACCESS_VIOLATION" in message
    assert "520 passed in 12.68s" in message
    assert "NOT a test failure" in message


def test_an_ordinary_failing_suite_is_not_described_as_a_crash(
    verify_module: ModuleType,
) -> None:
    """The other direction. Exit 1 is a verdict pytest chose, and must read as one."""
    message = verify_module.describe_exit(
        "pytest", 1, "FAILED tests/x.py::test_y\n1 failed, 519 passed in 13.0s", 5
    )
    assert "CRASHED" not in message
    assert message.startswith("pytest exit 1: ")


def test_a_crash_is_recognised_per_tool_by_that_tools_own_exit_range(
    verify_module: ModuleType,
) -> None:
    """mypy and ruff return 0, 1 or 2; pytest returns 0 through 5. Above a tool's own
    range the value was not chosen by the tool - the process died before it could."""
    assert "CRASHED" not in verify_module.describe_exit("mypy", 2, "usage error", 2)
    assert "CRASHED" in verify_module.describe_exit("mypy", 3221226356, "", 2)
    assert "fatal signal 11" in verify_module.describe_exit("ruff", -11, "", 2)
    # pytest's own range stays a verdict, including the codes that are not 0 or 1.
    assert "CRASHED" not in verify_module.describe_exit("pytest", 5, "no tests ran", 5)


# The retry. There is a known intermittent native memory fault in the seed write
# path - not root-caused, suspected hardware - and the gate retries a *crash* once so
# that it is not the thing holding the phase. The four below pin the boundaries of
# that allowance, because a retry loop that grew a second attempt, or that started
# retrying verdicts, would turn the whole gate into the "re-run until green" habit
# `describe_exit` was written to prevent.

CRASH_OUTPUT = ".....\n520 passed in 12.68s\nWindows fatal exception"


def scripted_toolchain(
    verify_module: ModuleType,
    bare_tree: Path,
    monkeypatch: pytest.MonkeyPatch,
    results: list[tuple[int | None, str]],
) -> list[str]:
    """Drive `toolchain_green` against a fixed sequence of subprocess results.

    Returns the list of tool names actually invoked, in order, so a test can assert
    on how many attempts each command got rather than only on the message.
    """
    make_toolchain_roots(verify_module, bare_tree)
    monkeypatch.setattr(
        verify_module, "_interpreter_with_toolchain", lambda root: ("python.exe", [])
    )
    calls: list[str] = []
    remaining = list(results)

    def fake_run(
        interpreter: str, args: list[str], root: Path, env: dict[str, str]
    ) -> tuple[int | None, str]:
        calls.append(args[1])
        return remaining.pop(0)

    monkeypatch.setattr(verify_module, "_run_tool", fake_run)
    return calls


def test_a_crash_is_retried_once_and_a_clean_retry_passes_with_the_crash_named(
    verify_module: ModuleType, bare_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mitigation. A crash says nothing about the code, so the command runs
    again - but the PASS still names it, because a mitigated fault that stops being
    reported stops being a known risk and quietly becomes the normal noise level."""
    calls = scripted_toolchain(
        verify_module,
        bare_tree,
        monkeypatch,
        [(3221225477, CRASH_OUTPUT), (0, ""), (0, ""), (0, "")],
    )
    outcome = run(verify_module, "toolchain_green", bare_tree)
    assert outcome.result is verify_module.Result.PASS
    assert "RETRIED AFTER CRASH" in outcome.message
    assert "0xC0000005 ACCESS_VIOLATION" in outcome.message
    assert "520 passed in 12.68s" in outcome.message
    assert calls == ["pytest", "pytest", "mypy", "ruff"]


def test_a_second_crash_fails_and_the_retry_is_not_repeated(
    verify_module: ModuleType, bare_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bounded at one. Two crashes in a row is no longer noise worth absorbing, and
    a third attempt would be the first step of an unbounded loop."""
    calls = scripted_toolchain(
        verify_module,
        bare_tree,
        monkeypatch,
        [(3221225477, CRASH_OUTPUT), (3221226356, ""), (0, ""), (0, "")],
    )
    outcome = run(verify_module, "toolchain_green", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert outcome.message.startswith("CRASH - ")
    assert "the retry crashed too" in outcome.message
    assert calls == ["pytest", "pytest", "mypy", "ruff"]


def test_a_verdict_is_never_retried(
    verify_module: ModuleType, bare_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The line the retry must not cross. Exit 1 is pytest reporting on the code; it
    is the same answer every time, and running it again until it disagrees is the
    exact failure mode this whole criterion exists to stop."""
    calls = scripted_toolchain(
        verify_module,
        bare_tree,
        monkeypatch,
        [(1, "1 failed, 519 passed in 13.0s"), (0, ""), (0, "")],
    )
    outcome = run(verify_module, "toolchain_green", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert not outcome.message.startswith("CRASH - ")
    assert "pytest exit 1" in outcome.message
    assert calls == ["pytest", "mypy", "ruff"]


def test_a_failure_deposits_the_whole_captured_output_and_names_the_file(
    verify_module: ModuleType, bare_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The evidence fix. The message is one line; the diagnosis is a file.

    An `ERROR` puts the traceback naming the fixture that raised a hundred lines above
    the summary, so the three-line tail that survives into the message is precisely the
    part that says nothing. `toolchain_green` has been intermittently red on a quiescent
    tree since Phase 2 and every observation of it was a summary with the cause already
    discarded. Asserted on a line that could only have come from the middle of the
    output, because a test that checked the tail would pass on the old behaviour too.
    """
    buried = "E   fixture 'seeded_store' raised: PermissionError"
    output = "\n".join([buried, *[f"line {n}" for n in range(40)], "1 error in 9.0s"])
    scripted_toolchain(verify_module, bare_tree, monkeypatch, [(1, output), (0, ""), (0, "")])
    outcome = run(verify_module, "toolchain_green", bare_tree)

    assert outcome.result is verify_module.Result.FAIL
    assert "full output: " in outcome.message
    assert buried not in outcome.message

    deposited = sorted((bare_tree / verify_module.TOOLCHAIN_EVIDENCE_DIR).glob("*.log"))
    assert len(deposited) == 1
    written = deposited[0].read_text(encoding="utf-8")
    assert buried in written
    assert "1 error in 9.0s" in written
    assert "# tool:       pytest" in written
    assert deposited[0].as_posix() in outcome.message
    # Written as bytes with `\n`, so a traceback read on Windows is not doubly spaced.
    assert b"\r\n" not in deposited[0].read_bytes()


def test_a_verdict_on_the_retry_stands_as_the_verdict(
    verify_module: ModuleType, bare_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retry crashed first and then reported a real failure. The failure is the
    finding; the crash is context and is kept, not dropped."""
    calls = scripted_toolchain(
        verify_module,
        bare_tree,
        monkeypatch,
        [(3221225477, CRASH_OUTPUT), (1, "1 failed, 519 passed in 13.0s"), (0, ""), (0, "")],
    )
    outcome = run(verify_module, "toolchain_green", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "pytest exit 1" in outcome.message
    assert "the first attempt crashed" in outcome.message
    assert calls == ["pytest", "pytest", "mypy", "ruff"]


# --------------------------------------------------------------------------- #
# is_gate_matches_registry
# --------------------------------------------------------------------------- #


def fabricate_registry(root: Path, bootstrap: str, offline: str = EMPTY_OFFLINE_CHAIN) -> None:
    fabricate_package(
        root,
        {
            "acsoe.engine_stub": ENGINE_STUB,
            "acsoe.bootstrap": bootstrap,
            "acsoe.cli.research": offline,
        },
    )


def test_is_gate_parses_the_registry_out_of_the_document(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """`engine-contracts.md` is the authority and the table is parsed, not
    hardcoded, so a registry change moves the check with it."""
    rows = verify_module.parse_engine_registry(repo_root)
    assert len(rows) == 23
    assert rows["data_guard"].number == 4 and rows["data_guard"].is_gate
    assert rows["exchange"].number == 1 and not rows["exchange"].is_gate
    assert {name for name, row in rows.items() if row.is_gate} == {
        "data_guard",
        "safety",
        "scout",
        "anomaly",
        "cost",
        "risk",
        "skeptic",
    }


def test_is_gate_is_a_vacuous_pass_on_an_empty_registry(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Phase 0 registers no engines **by design**.

    Zero engines against zero rows is a satisfied assertion, not an absent one:
    every registry source was read and nothing disagreed. Reporting PENDING here
    would make Phase 0 structurally impossible to close, since a phase is green
    only when nothing is PENDING. The lead ruled this a vacuous PASS.

    The count in the message is the guard against that vacuous pass being mistaken
    for a real one - a reader sees exactly how much assurance is on offer, and a
    `0` in a phase where engines were supposed to be registered is itself the bug.
    """
    fabricate_registry(bare_tree, EMPTY_BOOTSTRAP)
    outcome = run(verify_module, "is_gate_matches_registry", bare_tree)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    assert outcome.message == "0 engines registered; 0 mismatches"


def test_is_gate_is_pending_while_a_registry_source_is_missing(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """An empty registry and an *absent* one are different states and must not
    report the same way: the first is a satisfied check, the second is a check that
    has not run."""
    fabricate_package(bare_tree, {"acsoe.engine_stub": ENGINE_STUB})
    outcome = run(verify_module, "is_gate_matches_registry", bare_tree)
    assert outcome.result is verify_module.Result.PENDING
    assert "acsoe.bootstrap" in outcome.message


def test_is_gate_is_pending_when_the_offline_builder_is_missing(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """The offline chain is deliberately unreachable from `bootstrap.py` - that is
    what keeps architecture invariant 5 true - so `cli/research.py` is a second
    source and its absence is its own PENDING."""
    fabricate_registry(bare_tree, EMPTY_BOOTSTRAP, offline="OFFLINE_CHAIN = ()\n")
    outcome = run(verify_module, "is_gate_matches_registry", bare_tree)
    assert outcome.result is verify_module.Result.PENDING
    assert "build_offline_chain" in outcome.message


def test_is_gate_passes_when_registered_engines_match_the_table(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    fabricate_registry(
        bare_tree,
        registry_bootstrap(
            guard='Engine("exchange", 1, False), Engine("data_guard", 4, True),',
            opportunity='Engine("cost", 10, True),',
            manage='Engine("memory", 19, False),',
        ),
    )
    outcome = run(verify_module, "is_gate_matches_registry", bare_tree)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    assert "4 engines registered; 0 mismatches" in outcome.message
    assert "2 gates" in outcome.message


def test_is_gate_fails_when_a_gate_is_registered_as_an_ordinary_engine(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """The failure this criterion exists for. `is_gate` is not decorative: a gate
    registered as an ordinary engine is a protection that silently is not one, and
    nothing else in the system would notice."""
    fabricate_registry(
        bare_tree, registry_bootstrap(guard='Engine("data_guard", 4, False),')
    )
    outcome = run(verify_module, "is_gate_matches_registry", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "data_guard" in outcome.message
    assert "1 mismatches" in outcome.message


def test_is_gate_fails_when_an_engine_number_disagrees_with_the_table(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """The numbers are identifiers, not execution order, and they join a decision to
    its logs. A duplicated or wrong one corrupts the audit trail rather than the
    run, which is why it has to be caught here."""
    fabricate_registry(bare_tree, registry_bootstrap(guard='Engine("safety", 7, True),'))
    outcome = run(verify_module, "is_gate_matches_registry", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "number=7" in outcome.message


def test_is_gate_fails_on_an_engine_that_is_not_in_the_registry_table(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Adding, removing or reordering an engine is an escalation, not a teammate
    change. An engine that registered itself without reaching the table is exactly
    that escalation having been skipped."""
    fabricate_registry(bare_tree, registry_bootstrap(guard='Engine("freelancer", 99, False),'))
    outcome = run(verify_module, "is_gate_matches_registry", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "freelancer" in outcome.message


def test_is_gate_covers_the_offline_chain_engines(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """`scripts/verify.py` sits outside both sides of the research boundary and may
    import either, which is what lets its assertion cover engines 20 and 23 as well
    as the registered ones. Proved by planting the mismatch **only** in the offline
    chain: a criterion reading `bootstrap.py` alone reports PASS here.
    """
    fabricate_registry(
        bare_tree,
        EMPTY_BOOTSTRAP,
        offline=offline_chain_module('Engine("backtest", 23, True),'),
    )
    outcome = run(verify_module, "is_gate_matches_registry", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "backtest" in outcome.message


def test_is_gate_counts_the_offline_engines_in_a_pass(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Engine 23 lives in `research/` and is registered only in `OFFLINE_CHAIN`, so
    it never appears in `bootstrap.py`. It still has to be counted."""
    fabricate_registry(
        bare_tree,
        registry_bootstrap(guard='Engine("exchange", 1, False),'),
        offline=offline_chain_module('Engine("tournament", 20, False), Engine("backtest", 23, False),'),
    )
    outcome = run(verify_module, "is_gate_matches_registry", bare_tree)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    assert "3 engines registered" in outcome.message


# --------------------------------------------------------------------------- #
# A broken environment is FAIL, never PENDING
# --------------------------------------------------------------------------- #


def test_a_missing_project_dependency_is_fail_not_pending(verify_module: ModuleType) -> None:
    """The rule, at the one place every criterion shares: `try_import`.

    A module of *ours* that has not been written is PENDING. A declared third-party
    dependency the interpreter does not have is FAIL, and the message carries the
    fix. Without that split, running the gate under a Python that lacks PyYAML
    would report a tidy row of PENDINGs and hide the real state completely.
    """
    module, outcome = verify_module.try_import("acsoe_nonexistent_module_xyz")
    assert module is None
    assert outcome.result is verify_module.Result.PENDING

    module, outcome = verify_module.try_import("tests.verify.needs_a_missing_dependency")
    assert module is None
    assert outcome.result is verify_module.Result.FAIL
    assert "no_such_third_party_package" in outcome.message
    assert "pip install" in outcome.message or ".venv" in outcome.message


def test_a_criterion_reports_fail_when_yaml_is_unavailable(
    verify_module: ModuleType, bare_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`config/default.yaml` is parsed with `pyyaml`, `safe_load` only.

    Run under an interpreter without it - the system Python rather than the project
    virtualenv, which is the realistic way this happens - `seed_fixtures_present`
    must go red rather than joining the PENDING column.
    """
    fabricate_config(bare_tree)

    def no_yaml(name: str) -> tuple[None, Any]:
        if name == "yaml":
            return None, verify_module.failed(
                "config needs `yaml`, which this interpreter does not have - "
                + verify_module.VENV_HINT
            )
        return verify_module.try_import(name)

    monkeypatch.setattr(verify_module, "try_import", no_yaml)
    outcome = run(verify_module, "seed_fixtures_present", bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "yaml" in outcome.message


# --------------------------------------------------------------------------- #
# The fresh-clone rule
# --------------------------------------------------------------------------- #


def test_no_registered_criterion_reads_data_models_or_logs(verify_module: ModuleType) -> None:
    """Spec 00 step 7. `data/`, `models/` and `logs/` are gitignored, so a criterion
    depending on anything inside one of them passes only on the machine that produced
    it - which is a broken criterion, not a passing phase.

    **Per registered criterion, not per line of the file.** This was a line scan over
    the whole of `scripts/verify.py`, which was correct only for as long as no
    criterion was `--live`. Phase 4 registers the project's first one:
    `replay_full_archive` reads `data/historical/` on purpose, spec 48 criterion 8
    names the directory, and `ai-workflow-rules.md` makes a `--live` criterion opt-in
    and never required for a phase to be green. A whole-file scan cannot tell that
    sanctioned read from a defect, so it is now walked the way the Phase 3 equivalent
    already walks it - `inspect.getsource` of each criterion the ordinary
    (non-`--live`) run would execute. That covers strictly more than the line scan did,
    because it reaches every phase's criteria rather than only the ones that happen to
    sit in this file's Phase 0 section.
    """
    import inspect

    seen = 0
    for phase in range(verify_module.MIN_PHASE, verify_module.MAX_PHASE + 1):
        to_run, _skipped = verify_module.criteria_for(phase, False)
        for criterion in to_run:
            seen += 1
            hits = gitignored_reads(inspect.getsource(criterion.check))
            assert hits == [], f"{criterion.name}: {hits}"
    assert seen, "no criteria were walked; the registry lookup is wrong, not the rule"


#: The three gitignored roots. A criterion that reads anything under one of them passes
#: only on the machine that produced it.
GITIGNORED_ROOTS: Final = ("data", "models", "logs")


def gitignored_reads(source: str) -> list[str]:
    """Every read of a repository-rooted gitignored path in `source`, off the syntax tree.

    **This was a substring scan for `"data"`, `"models"` and `"logs"` and that was wrong
    in the direction nobody notices until it is in the way.** Phase 5 is the first phase
    where a criterion routinely holds an `EngineResult` payload — `getattr(result,
    "data", {})` — and builds a temporary artefact root — `tmp / "run" / "models"`.
    Neither reads a gitignored path; both tripped the scan. `code-standards.md` records
    the same failure in `test_the_live_loop_does_not_import_research` and gives the same
    instruction: an over-strict rule is replaced with narrower, stronger assertions, never
    given an exception, because an exception keeps a check that cannot tell a path from a
    word and the next correct change meets it again.

    The rule is about **paths rooted at the repository**, and that is syntactically
    distinguishable:

    * ``ctx.root / "data"`` and anything below it — a division whose left operand chains
      back to `ctx.root`;
    * a string literal beginning ``data/``, ``models/`` or ``logs/``.

    A field called `data`, a keyword called `models_dir`, and a directory built under a
    `TemporaryDirectory` are none of those.

    **What it does not see, stated rather than implied.** ``ctx.root / name`` where `name`
    is a variable is not a hit, and cannot be: `docs_vocabulary` builds exactly that shape
    over the documentation files it scans, so flagging it would be the same over-strictness
    one turn later. A criterion that reached a gitignored directory through a computed name
    would pass this. That residual gap is the review's job rather than the scan's, and it is
    narrower than the one the substring version left — that one could not see
    ``os.path.join(root, "models")`` either, while also rejecting two shapes that were
    always fine.
    """
    import ast

    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError as exc:  # pragma: no cover - a criterion that does not parse
        return [f"could not be parsed: {exc}"]

    def rooted_at_repo(node: ast.AST) -> bool:
        """Whether this expression chains back to `ctx.root`, however many `/` deep."""
        if isinstance(node, ast.Attribute) and node.attr == "root":
            return True
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return rooted_at_repo(node.left)
        return False

    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and rooted_at_repo(
            node.left
        ):
            right = node.right
            if isinstance(right, ast.Constant) and right.value in GITIGNORED_ROOTS:
                hits.append(f"line {node.lineno}: ctx.root / {right.value!r}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for word in GITIGNORED_ROOTS:
                if node.value.startswith(word + "/"):
                    hits.append(f"line {node.lineno}: {node.value!r}")
    return hits


def test_the_gitignored_scan_tells_a_path_from_a_word(verify_module: ModuleType) -> None:
    """The detector, proved in both directions on the two cases that made it necessary.

    Without this, the narrowing above is a claim. The negatives are the two shapes that
    were false positives for a whole phase; the positives are the reads the rule exists to
    forbid.
    """
    del verify_module
    assert gitignored_reads('data = dict(getattr(result, "data", {}) or {})') == []
    assert gitignored_reads('run_dir = tmp / "run" / "models"') == []
    assert gitignored_reads("store = client(db, models_dir=tmp / 'artefacts')") == []

    assert gitignored_reads('archive = ctx.root / "data" / "historical"')
    assert gitignored_reads('artefacts = ctx.root / "models"')
    assert gitignored_reads('path = ctx.root / "data"')
    assert gitignored_reads('name = "models/run-1/manifest.json"')
    # And the gap, pinned so it is a known limit rather than a surprise: a computed
    # directory name is invisible to a syntax scan, and `docs_vocabulary` builds exactly
    # that shape over the documents it scans.
    assert gitignored_reads("path = ctx.root / chosen") == []


def test_the_only_criterion_reading_a_gitignored_path_is_live_only(
    verify_module: ModuleType,
) -> None:
    """The exception above is pinned, so it cannot widen by accident.

    `replay_full_archive` is allowed to read `data/historical/` **because it is
    `--live`**. Registering it as an ordinary criterion would admit a gitignored read
    into the path a phase has to pass on a fresh clone, and the scan above - which
    skips live criteria - would say nothing. This is the assertion that notices.
    """
    live = {
        criterion.name
        for criteria in verify_module._REGISTRY.values()
        for criterion in criteria
        if criterion.live
    }
    assert "replay_full_archive" in live, (
        "replay_full_archive reads data/historical/ and must be registered live=True"
    )


# --------------------------------------------------------------------------- #
# orchestrator_empty_registry really does tick over an empty registry
# --------------------------------------------------------------------------- #

#: An orchestrator that blocks whenever any engine is in the guard chain.
#:
#: Not contrived. A rehearsed engines 1 to 4 against the fake Kraken client, which
#: is REST-only, so `market_sensor` publishes no quotes and `data_guard` blocks
#: every tick with `no_market_data` - invariant 3 working exactly as intended. This
#: fabrication reproduces that outcome in one line.
BLOCKING_ORCHESTRATOR = """
from typing import Any


class Orchestrator:
    def __init__(self, *, config: Any, clock: Any, clients: Any, chains: Any) -> None:
        self.chains = chains

    def tick(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "system": {"mode": "idle", "close_intent": False},
            "cycle_id": 1,
            "guard_blockers": [],
        }
        for engine in self.chains.guard:
            state["guard_blockers"].append(engine.name)
            state.setdefault("trading_blocked_by", engine.name)
        return state
"""

ONE_GUARD_ENGINE = """
class _Engine:
    name = "data_guard"
    number = 4
    is_gate = True


GUARD_CHAIN: tuple[object, ...] = (_Engine(),)
OPPORTUNITY_CHAIN: tuple[object, ...] = ()
MANAGE_CHAIN: tuple[object, ...] = ()
"""


def test_a_registered_blocking_gate_does_not_fail_the_empty_registry_criterion(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The criterion is named for an empty registry and must test one.

    It used to build its `Chains` from the live `acsoe.bootstrap` and then assert
    that no guard blocked and that `trading_blocked_by` was absent. Both assertions
    are true only of an *empty* registry, and they held only because Phase 0
    registers nothing. Registering engines 1 to 4 - which block every tick against
    the REST-only fake client, correctly - would have turned a closed, green Phase 0
    criterion red for nobody's defect.

    Here the registry holds a gate that blocks and the orchestrator honours it. The
    criterion must still PASS, because the claim it makes is about an empty chain,
    and the assertions are unchanged: they run against chains the criterion builds
    empty itself.
    """
    fabricate_package(
        tree_with_harness,
        {
            "acsoe.bootstrap": ONE_GUARD_ENGINE,
            "acsoe.core.contracts": CHAINS_CONTRACT,
            "acsoe.core.orchestrator": BLOCKING_ORCHESTRATOR,
        },
    )
    outcome = run(verify_module, "orchestrator_empty_registry", tree_with_harness)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    assert "explicitly empty registry" in outcome.message
    assert reported_engine_count(outcome.message) == 1


def test_the_blocking_registry_really_would_have_failed_the_old_criterion(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The test above has to be able to fail, or it proves nothing about the change.

    Same fabrication, driven through the orchestrator directly with the *live*
    chains, which is what the criterion used to do. The blockers it produces are
    exactly what the two `failed(...)` branches refuse - so the fabrication is a
    real reproduction of the regression rather than a shape that could never have
    tripped it.
    """
    fabricate_package(
        tree_with_harness,
        {
            "acsoe.bootstrap": ONE_GUARD_ENGINE,
            "acsoe.core.contracts": CHAINS_CONTRACT,
            "acsoe.core.orchestrator": BLOCKING_ORCHESTRATOR,
        },
    )
    with verify_module.root_import_path(tree_with_harness):
        import acsoe.bootstrap as bootstrap
        from acsoe.core.contracts import Chains
        from acsoe.core.orchestrator import Orchestrator

        state = Orchestrator(
            config=None,
            clock=None,
            clients=None,
            chains=Chains(
                guard=bootstrap.GUARD_CHAIN,
                opportunity=bootstrap.OPPORTUNITY_CHAIN,
                manage=bootstrap.MANAGE_CHAIN,
            ),
        ).tick()

    assert state["guard_blockers"] == ["data_guard"]
    assert "trading_blocked_by" in state
