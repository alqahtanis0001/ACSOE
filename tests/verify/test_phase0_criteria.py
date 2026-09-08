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

import sqlite3
from pathlib import Path
from types import ModuleType
from typing import Any

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
    assert "0 registered engines" in outcome.message


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


def test_toolchain_is_pending_before_src_exists(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    outcome = run(verify_module, "toolchain_green", bare_tree)
    assert outcome.result is verify_module.Result.PENDING
    assert "src/" in outcome.message


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
    (bare_tree / "src").mkdir()
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


def test_no_phase_zero_criterion_reads_data_models_or_logs(repo_root: Path) -> None:
    """Spec 00 step 7. `data/`, `models/` and `logs/` are gitignored, so a criterion
    depending on anything inside one of them passes only on the machine that
    produced it - which is a broken criterion, not a passing phase."""
    source = (repo_root / "scripts" / "verify.py").read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "gitignore" in stripped:
            continue
        for forbidden in ('"data"', "'data'", '"models"', '"logs"'):
            assert forbidden not in stripped, line
