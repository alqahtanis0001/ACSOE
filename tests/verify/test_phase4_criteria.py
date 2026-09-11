"""The seven Phase 4 criteria, each proved three ways. Spec 48.

* **PENDING** against a tree where the subject does not exist. A criterion that cannot
  reach that state makes a phase impossible to start.
* **PASS** against the subject as it actually is.
* **FAIL**, deliberately induced. *A check nobody has seen fail is a comment.* Every
  induced failure is written up in `docs/build-log/phase-4/c-interface.md`.

Phase 4 is the phase where a mistake looks like success, so the third of those carries
more weight here than in any earlier phase. A purging bug or a short embargo produces a
model that appears excellent and is worthless; a missed block record makes the circuit
breaker inert. Neither crashes, neither turns a test red, and neither is visible to an
operator — so every induced failure below is a *plausible* wrong implementation rather
than a broken one. An engine that raises proves nothing about a criterion.

**Fabricate the subject; never fabricate the contract.** `phase4_tree` carries the real
`src/acsoe`, the real `db/migrations/`, the real `config/` and the real test harness, and
a FAIL is induced by changing exactly one line in that copy. A tree assembled the other
way round — fabricated contracts with a real engine dropped in — is how
`check_data_guard_blocks_bad_data` came to have a body that never executed while both
halves of its proof passed.
"""

from __future__ import annotations

import json
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
from tests.verify.test_phase3_criteria import patch_module

PHASE4_CRITERIA = (
    "memory_records_every_blocker",
    "memory_writes_safety_inputs_live",
    "rejections_survive_restart",
    "labelled_sample_replayed_from_archive",
    "labeller_matches_hand_verified_labels",
    "walkforward_folds_purged_and_embargoed",
    "console_history_reads_real_rows",
)

MEMORY_ENGINE = "acsoe.engines.memory.engine"
LABELLING = "acsoe.research.labelling"
WALKFORWARD = "acsoe.research.walkforward"

_NO_PYCACHE = shutil.ignore_patterns("__pycache__", "*.pyc")


@pytest.fixture
def phase4_tree(bare_tree: Path, repo_root: Path) -> Path:
    """The real package, harness, fixtures, migrations and config, copied.

    Deliberately not a fabricated `acsoe`: these criteria drive the real engine 19 into
    the real store, and the real labeller over the real committed fixtures.
    """
    shutil.copytree(repo_root / "src" / "acsoe", bare_tree / "src" / "acsoe", ignore=_NO_PYCACHE)
    shutil.copytree(repo_root / "config", bare_tree / "config")
    shutil.copytree(repo_root / "db", bare_tree / "db", ignore=_NO_PYCACHE)
    tests = bare_tree / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "__init__.py").write_text("", encoding="utf-8")
    shutil.copytree(repo_root / "tests" / "harness", tests / "harness", ignore=_NO_PYCACHE)
    shutil.copytree(repo_root / "tests" / "fixtures", tests / "fixtures", ignore=_NO_PYCACHE)
    return bare_tree


def drop_fixture(root: Path, name: str) -> None:
    """Remove one committed evidence file from a copied tree."""
    path = root / "tests" / "fixtures" / name
    if not path.exists():
        raise AssertionError(f"{name} is not in the copied tree; the fixture is wrong")
    path.unlink()


# --------------------------------------------------------------------------- #
# Registration and the rules that apply to all seven
# --------------------------------------------------------------------------- #


def test_all_seven_criteria_are_registered_for_phase_4(verify_module: ModuleType) -> None:
    to_run, skipped = verify_module.criteria_for(4, False)
    names = [c.name for c in to_run]
    assert names == ["docs_vocabulary", "toolchain_green", *PHASE4_CRITERIA]
    assert [c.name for c in skipped] == ["replay_full_archive"]


def test_the_live_criterion_runs_only_with_live(verify_module: ModuleType) -> None:
    """`replay_full_archive` reads `data/historical/`. It may never run in the ordinary
    path, because `data/` is gitignored and a phase must be green on a fresh clone."""
    to_run, _ = verify_module.criteria_for(4, True)
    assert "replay_full_archive" in [c.name for c in to_run]


def test_no_phase_4_criterion_hardcodes_an_exchange_value(verify_module: ModuleType) -> None:
    """`AGENTS.md` rule 1. A remembered fee, tier threshold or order minimum is stale,
    and a criterion naming a Kraken pair is one that stops working when the universe
    changes."""
    import inspect

    for name in PHASE4_CRITERIA:
        source = inspect.getsource(getattr(verify_module, "check_" + name))
        for forbidden in ("XBT", "XXBTZUSD", "BTC/USD", "ETH/USD", "SOL/USD"):
            assert forbidden not in source, f"{name} names a pair rather than reading one"


def test_every_phase_4_criterion_is_pending_on_an_unbuilt_tree(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    """The state the phase opened in. Not one of them may FAIL there: a phase that has
    not been built is unfinished, not broken, and a FAIL is a stop at any point."""
    for name in PHASE4_CRITERIA:
        assert_pending(run(verify_module, name, unbuilt_tree), verify_module)


def test_every_phase_4_criterion_passes_against_the_real_repository(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """The middle observation, and the one that stops the file being a set of PENDING
    assertions dressed as a proof."""
    for name in PHASE4_CRITERIA:
        assert_pass(run(verify_module, name, repo_root), verify_module)


# --------------------------------------------------------------------------- #
# memory_records_every_blocker
# --------------------------------------------------------------------------- #


def test_a_memory_engine_that_needs_a_candidate_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """**The defect that makes the circuit breaker inert**, and it is otherwise
    competent code.

    An implementer reading invariant 12 as "rejections are logged" writes a block record
    only where a candidate was rejected. Every rejection still reaches storage, every
    count still adds up, no test about rejections goes red — and `block_records` is empty
    on exactly the ticks `safety`'s outage counter counts, because `data_guard` blocks in
    the guard chain before the opportunity chain has run at all.
    """
    patch_module(
        phase4_tree,
        MEMORY_ENGINE,
        "        for index, entry in enumerate(blockers):",
        "        scout_key, pair_field = CANDIDATE_PAIR_PATH\n"
        "        if not (state.get(scout_key) or {}).get(pair_field):\n"
        "            return 0\n"
        "        for index, entry in enumerate(blockers):",
    )
    outcome = run(verify_module, "memory_records_every_blocker", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "no candidate ever existed" in outcome.message


def test_a_memory_engine_writing_one_row_per_tick_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """The guard chain never breaks early, so a tick can carry two blockers. Keeping the
    primary alone passes a naive count and loses half of invariant 12's record."""
    patch_module(
        phase4_tree,
        MEMORY_ENGINE,
        "        for index, entry in enumerate(blockers):",
        "        for index, entry in enumerate(blockers[:1]):",
    )
    outcome = run(verify_module, "memory_records_every_blocker", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "two guards blocked" in outcome.message


def test_a_memory_engine_writing_a_row_on_every_tick_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """A row on every tick makes the outage run indistinguishable from the uptime."""
    patch_module(
        phase4_tree,
        MEMORY_ENGINE,
        "        blockers = state.get(GUARD_BLOCKERS_KEY)",
        '        blockers = state.get(GUARD_BLOCKERS_KEY) or [\n'
        '            {"engine": "none", "reason": "", "status": "BLOCK"}\n'
        "        ]",
    )
    outcome = run(verify_module, "memory_records_every_blocker", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "unblocked tick wrote" in outcome.message


def test_a_memory_engine_that_flattens_the_status_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """`safety` counts the error rate with `status = 'ERROR'`. An engine recording every
    blocker as a BLOCK leaves that count reading zero forever, and nothing raises."""
    patch_module(
        phase4_tree,
        MEMORY_ENGINE,
        '                    status=BlockStatus(str(entry["status"])),',
        "                    status=BlockStatus.BLOCK,",
    )
    outcome = run(verify_module, "memory_records_every_blocker", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "reads zero forever" in outcome.message


# --------------------------------------------------------------------------- #
# memory_writes_safety_inputs_live
# --------------------------------------------------------------------------- #


def test_a_peak_equity_recomputed_from_this_tick_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """**The named mutation of spec 50**, and the reason the criterion replays two
    equity ticks rather than one.

    An engine taking the maximum of the current tick alone reports a peak equal to the
    current equity, a drawdown of permanently zero, and a breaker that never fires on a
    drawdown again. The equity curve on the console still looks plausible. A one-tick
    replay could not tell the two implementations apart.
    """
    patch_module(
        phase4_tree,
        MEMORY_ENGINE,
        "        peak = equity if previous is None else max(previous.peak_equity, equity)",
        "        peak = equity",
    )
    outcome = run(verify_module, "memory_writes_safety_inputs_live", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "drawdown_pct" in outcome.message


def test_a_memory_engine_that_drops_the_closed_trades_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """`safety`'s loss streak is the trailing run of `trades`. An engine that recorded
    no trade leaves the streak at zero, which reads as a healthy account."""
    patch_module(
        phase4_tree,
        MEMORY_ENGINE,
        "        for row in self._rows(exiting, CLOSED_TRADES_FIELD):",
        "        for row in self._rows(exiting, CLOSED_TRADES_FIELD)[:0]:",
    )
    outcome = run(verify_module, "memory_writes_safety_inputs_live", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "consecutive_losses" in outcome.message


def test_a_memory_engine_that_drops_the_resting_orders_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """Invariant 14's escalation precondition is *open positions **or** resting entry
    orders*. An outage with no position but a live post-only buy is still exposure, and
    an engine that never recorded the order makes that case unreachable."""
    patch_module(
        phase4_tree,
        MEMORY_ENGINE,
        "        rows = self._rows(manager, ORDERS_FIELD)",
        "        rows = self._rows(manager, ORDERS_FIELD)[:0]",
    )
    outcome = run(verify_module, "memory_writes_safety_inputs_live", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "resting_entry_orders" in outcome.message


# --------------------------------------------------------------------------- #
# rejections_survive_restart
# --------------------------------------------------------------------------- #


def test_a_rejection_written_without_its_economics_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """The row survives the restart and the columns do not.

    This is what a criterion that counted rows would pass against: the rejection is
    there, the join works, the history screen renders a line — and the numbers that made
    the refusal analysable are gone.
    """
    patch_module(
        phase4_tree,
        MEMORY_ENGINE,
        "            economics[column] = None if value is None else str(value)",
        "            economics[column] = None",
    )
    outcome = run(verify_module, "rejections_survive_restart", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "only counts rows" in outcome.message


def test_a_rejection_stamped_with_the_reading_run_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """A rejection must carry the run that wrote it. Stamping it with whatever run is
    reading makes every restart look like it happened inside one process, and the
    Phase 7 attribution groups by `run_id`."""
    patch_module(
        phase4_tree,
        MEMORY_ENGINE,
        "                run_id=context.run_id,\n                ts=ts,\n                pair=str(pair),",
        '                run_id="whoever-is-reading",\n                ts=ts,\n                pair=str(pair),',
    )
    outcome = run(verify_module, "rejections_survive_restart", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "run that wrote it" in outcome.message


def test_rejections_survive_restart_is_pending_without_engine_19(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """The engine's absence is unfinished work, not a broken store."""
    (phase4_tree / "src" / "acsoe" / "engines" / "memory" / "engine.py").unlink()
    outcome = run(verify_module, "rejections_survive_restart", phase4_tree)
    assert_pending(outcome, verify_module)
    assert "spec 49" in outcome.message


# --------------------------------------------------------------------------- #
# labelled_sample_replayed_from_archive
# --------------------------------------------------------------------------- #


def test_a_missing_parquet_is_pending_not_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    drop_fixture(phase4_tree, "labelled_sample.parquet")
    outcome = run(verify_module, "labelled_sample_replayed_from_archive", phase4_tree)
    assert_pending(outcome, verify_module)
    assert "spec 56" in outcome.message


def test_a_parquet_with_no_provenance_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """**The question spec 56 asks of this criterion: would it still pass if the parquet
    had been written by hand?**

    Here it is, written by hand — the same columns, the same labels, all three outcomes
    present — and with nothing in it saying where it came from. Without the provenance
    assertion the criterion would accept it.
    """
    import polars as pl

    target = phase4_tree / "tests" / "fixtures" / "labelled_sample.parquet"
    frame = pl.read_parquet(target)
    frame.write_parquet(target)  # rewritten, losing the key-value metadata
    outcome = run(verify_module, "labelled_sample_replayed_from_archive", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "acsoe_provenance" in outcome.message


def test_a_parquet_labelled_under_different_barriers_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """A fixture labelled at a 5% target is evidence about a system nobody is building,
    and every one of its rows is internally consistent."""
    import polars as pl

    target = phase4_tree / "tests" / "fixtures" / "labelled_sample.parquet"
    metadata = pl.read_parquet_metadata(target)
    provenance = json.loads(metadata["acsoe_provenance"])
    provenance["target_pct"] = "0.05"
    frame = pl.read_parquet(target)
    frame.write_parquet(target, metadata={"acsoe_provenance": json.dumps(provenance)})
    outcome = run(verify_module, "labelled_sample_replayed_from_archive", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "different barriers" in outcome.message


def test_a_parquet_whose_labels_run_into_the_end_of_the_series_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """Labelling a bar whose window runs past the end of the data records an outcome
    that has not happened yet — invariant 10 with a different face.

    Induced by moving the stated series end backwards rather than by adding a row, which
    is the same claim from the fixture's side and needs no fabricated label.
    """
    import polars as pl

    target = phase4_tree / "tests" / "fixtures" / "labelled_sample.parquet"
    metadata = pl.read_parquet_metadata(target)
    provenance = json.loads(metadata["acsoe_provenance"])
    frame = pl.read_parquet(target)
    provenance["span_end_ts"] = max(int(v) for v in frame["decision_ts"].to_list()) + 900
    frame.write_parquet(target, metadata={"acsoe_provenance": json.dumps(provenance)})
    outcome = run(verify_module, "labelled_sample_replayed_from_archive", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "timeout horizon" in outcome.message


def test_a_parquet_missing_an_outcome_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """All three outcomes must occur, or the criterion cannot tell a labeller that emits
    one from a labeller that emits three."""
    import polars as pl

    target = phase4_tree / "tests" / "fixtures" / "labelled_sample.parquet"
    metadata = pl.read_parquet_metadata(target)
    frame = pl.read_parquet(target).filter(pl.col("label") != "timeout")
    frame.write_parquet(target, metadata={"acsoe_provenance": metadata["acsoe_provenance"]})
    outcome = run(verify_module, "labelled_sample_replayed_from_archive", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "no `timeout` label" in outcome.message


# --------------------------------------------------------------------------- #
# labeller_matches_hand_verified_labels
# --------------------------------------------------------------------------- #


def test_a_missing_hand_verified_fixture_is_pending(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    drop_fixture(phase4_tree, "labels_hand_verified.json")
    outcome = run(verify_module, "labeller_matches_hand_verified_labels", phase4_tree)
    assert_pending(outcome, verify_module)
    assert "spec 52" in outcome.message


def test_a_labeller_that_labels_a_bar_past_the_end_of_the_series_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """The exclusion rule removed. Every remaining label is still correct, and three
    bars now carry an outcome that has not happened yet."""
    patch_module(
        phase4_tree,
        LABELLING,
        "    if last_ts < window_end:\n        return None\n\n    # The scan starts at index + 1.",
        "    if False:\n        return None\n\n    # The scan starts at index + 1.",
    )
    outcome = run(verify_module, "labeller_matches_hand_verified_labels", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "expected to be excluded" in outcome.message


def test_a_labeller_that_reads_the_decision_bar_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """Look-ahead within one bar.

    The fixture carries a decision bar whose own low sweeps through the stop, so a
    labeller scanning it answers `stop` at bar 0 where the truth is a touch on a later
    bar. It is chosen for that, and it is why the entry is in the fixture.
    """
    patch_module(phase4_tree, LABELLING, "    scan_from = index + 1", "    scan_from = index")
    outcome = run(verify_module, "labeller_matches_hand_verified_labels", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "hand-verified" in outcome.message


def test_a_labeller_counting_the_timeout_in_rows_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """Ruling 2. The archives hold only intervals in which trades occurred, so 48
    existing rows can span days — counting rows stretches a 12-hour horizon over
    precisely the gaps the loader refuses to interpolate away."""
    patch_module(
        phase4_tree,
        LABELLING,
        "    scan_to = bisect.bisect_right(stamps, window_end)",
        "    scan_to = min(len(stamps), index + 1 + settings.timeout_bars)",
    )
    outcome = run(verify_module, "labeller_matches_hand_verified_labels", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "hand-verified" in outcome.message


def test_a_labeller_that_prefers_the_target_on_an_ambiguous_bar_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """Ruling 1 reversed. OHLC carries no intra-bar ordering, and calling it a `target`
    invents the favourable one on exactly the bars where the market was most violent."""
    patch_module(
        phase4_tree,
        LABELLING,
        "        label = LABEL_STOP if (hit_stop or ambiguous) else LABEL_TARGET",
        "        label = LABEL_TARGET if hit_target else LABEL_STOP",
    )
    outcome = run(verify_module, "labeller_matches_hand_verified_labels", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "hand-verified" in outcome.message


def test_a_fixture_with_no_excluded_entry_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """The criterion guards its own evidence.

    Drop the entries that must be excluded and the labeller still reproduces every
    remaining row — but the fixture has stopped being able to catch a labeller that
    labels a bar past the end of the series, and nothing else would say so.
    """
    path = phase4_tree / "tests" / "fixtures" / "labels_hand_verified.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    kept = [e for e in document["entries"] if e["expected_label"] is not None]
    document["entries"] = kept + kept[: 20 - len(kept)]
    path.write_text(json.dumps(document), encoding="utf-8")
    outcome = run(verify_module, "labeller_matches_hand_verified_labels", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "no entry that must be excluded" in outcome.message


# --------------------------------------------------------------------------- #
# walkforward_folds_purged_and_embargoed
#
# The two mutations spec 48 names for this criterion, and the third spec 53 adds.
# If any of them left it green, the criterion would be judging fold indices rather
# than label windows and would have to be rewritten before anything else proceeded.
# --------------------------------------------------------------------------- #


def test_an_embargo_of_zero_is_a_fail(verify_module: ModuleType, phase4_tree: Path) -> None:
    """Named in spec 48. **An end-to-end test cannot see this**, because the fold
    indices do not overlap whether or not the embargo ran."""
    patch_module(
        phase4_tree,
        WALKFORWARD,
        "        return self.embargo_bars * interval_s",
        "        return 0",
    )
    outcome = run(verify_module, "walkforward_folds_purged_and_embargoed", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "only the embargo can" in outcome.message


def test_a_purge_that_is_a_no_op_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """The other named one. A splitter with no purge in it reports a Sharpe the live
    system will never see, and the Phase 7 promotion gate passes it."""
    patch_module(
        phase4_tree,
        WALKFORWARD,
        "            if window_end >= test_start_ts:\n                purged += 1\n                continue",
        "            if False:\n                purged += 1\n                continue",
    )
    outcome = run(verify_module, "walkforward_folds_purged_and_embargoed", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "straddler" in outcome.message


def test_a_purge_on_the_decision_bar_timestamp_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """Spec 53's third, and the most dangerous of the three.

    Unlike the no-op, this splitter purges confidently and reports a non-zero
    `purged_count`. Every summary it prints looks healthy; it simply drops the wrong
    rows. It is caught only because the criterion constructs a row with its decision bar
    early and its label window late, on purpose.
    """
    patch_module(
        phase4_tree,
        WALKFORWARD,
        "            if window_end >= test_start_ts:",
        "            if decision_ts >= test_start_ts:",
    )
    outcome = run(verify_module, "walkforward_folds_purged_and_embargoed", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "straddler" in outcome.message


def test_a_splitter_that_truncates_everything_after_the_test_window_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """The embargo is a bounded span, not a truncation.

    Without this the criterion would pass against a splitter that dropped every training
    row after the test window — which satisfies the embargo assertion and throws away
    data the walk-forward is meant to reuse.
    """
    patch_module(
        phase4_tree,
        WALKFORWARD,
        "        if decision_ts < embargo_end:",
        "        if True:",
    )
    outcome = run(verify_module, "walkforward_folds_purged_and_embargoed", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "after_embargo" in outcome.message


def test_a_splitter_reporting_one_count_for_both_mechanisms_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """Two mechanisms, two numbers. A splitter that folded them into one would look
    healthy on the day the purge stopped working."""
    patch_module(
        phase4_tree,
        WALKFORWARD,
        "            embargoed += 1",
        "            purged += 1",
    )
    outcome = run(verify_module, "walkforward_folds_purged_and_embargoed", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "the same mechanism" in outcome.message


def test_the_walkforward_criterion_is_pending_without_the_module(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    (phase4_tree / "src" / "acsoe" / "research" / "walkforward.py").unlink()
    outcome = run(verify_module, "walkforward_folds_purged_and_embargoed", phase4_tree)
    assert_pending(outcome, verify_module)
    assert "spec 53" in outcome.message


# --------------------------------------------------------------------------- #
# console_history_reads_real_rows
# --------------------------------------------------------------------------- #


def test_a_console_that_only_shows_the_seed_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """The whole point of spec 57: a history screen that renders the seeded rows and
    never reaches the live ones passes every Phase 1 criterion unchanged."""
    patch_module(
        phase4_tree,
        "acsoe.console.reader",
        "_rejection_history_row(row) for row in self._store.recent_rejections(count)",
        "_rejection_history_row(row)\n                for row in self._store.recent_rejections(count)\n                if row.run_id != \"verify-phase-4-console\"",
    )
    outcome = run(verify_module, "console_history_reads_real_rows", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "still showing the seed" in outcome.message


def test_a_reason_code_missing_from_the_prose_map_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """The console's one genuinely silent failure.

    A code absent from `REASON_PROSE` renders *No reason was recorded.* — no error, no
    log line, just a row with an empty reason column. Induced by making the stored prose
    unusable so the map is consulted, and then removing the entry it would have found.
    """
    patch_module(
        phase4_tree,
        MEMORY_ENGINE,
        '                reason=str(state.get(BLOCK_REASON_KEY) or ""),',
        '                reason="",',
    )
    patch_module(
        phase4_tree,
        "acsoe.console.format",
        '    "net_edge_below_hurdle":',
        '    "net_edge_below_hurdle_renamed":',
    )
    outcome = run(verify_module, "console_history_reads_real_rows", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "REASON_PROSE" in outcome.message


# --------------------------------------------------------------------------- #
# replay_full_archive — the `--live` criterion, whose PENDING branch got harder
# to reach the moment the operator supplied a real archive
# --------------------------------------------------------------------------- #


def test_replay_full_archive_is_pending_when_no_archive_directory_exists(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """**Observed, not reasoned about.**

    `data/historical/` is gitignored and it exists on this machine, so on the real
    repository this branch is unreachable — which is precisely why it has to be reached
    somewhere. `phase4_tree` is a checkout without it, which is what a fresh clone looks
    like and what the operator sees before downloading anything.

    PENDING and not FAIL: an opt-in criterion that FAILed on a missing archive would make
    `--live` unusable for every other check in every other phase, so the operator would
    stop passing it and the live checks would quietly stop running.
    """
    assert not (phase4_tree / "data").exists()
    outcome = run(verify_module, "replay_full_archive", phase4_tree)
    assert_pending(outcome, verify_module)
    assert "data/historical" in outcome.message


def test_replay_full_archive_is_pending_when_the_directory_holds_no_csv(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """The second, different absence.

    A directory that exists and holds nothing is not the same fact as no directory at
    all — the operator has made the folder and not filled it, or has put the source
    time-and-sales files one level down and no derived bars at the top. Both are
    unfinished work rather than a broken replay, and the messages differ so the operator
    can tell which one they are looking at.
    """
    (phase4_tree / "data" / "historical").mkdir(parents=True)
    outcome = run(verify_module, "replay_full_archive", phase4_tree)
    assert_pending(outcome, verify_module)
    assert "no .csv archive" in outcome.message


def test_replay_full_archive_passes_over_a_real_archive(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """PASS against archive-shaped CSVs, built here rather than copied.

    Two pairs, deliberately, with a hole in one of them: the criterion reports a span and
    a gap count across every archive it finds, and a single-file fixture could not tell a
    criterion that summed them from one that read only the first.
    """
    directory = phase4_tree / "data" / "historical"
    directory.mkdir(parents=True)
    step = 900
    start = 1_700_000_000 - (1_700_000_000 % step)
    complete = "\n".join(
        f"{start + i * step},100,101,99,100,1.5,7" for i in range(40)
    )
    # One hole of three bars, so `gap_count` has something to count.
    holed = "\n".join(
        f"{start + i * step},50,51,49,50,2.5,3" for i in range(40) if not 10 <= i < 13
    )
    (directory / "AAAUSD_15.csv").write_bytes((complete + "\n").encode("utf-8"))
    (directory / "BBBUSD_15.csv").write_bytes((holed + "\n").encode("utf-8"))

    outcome = run(verify_module, "replay_full_archive", phase4_tree)
    assert_pass(outcome, verify_module)
    assert "2 archive(s)" in outcome.message
    assert "77 bars" in outcome.message
    assert "1 gap run(s)" in outcome.message


def test_an_archive_that_does_not_parse_is_a_fail_not_a_pending(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """The one case here that *is* a failure rather than unfinished work.

    An absent archive is the operator not having downloaded one. A present archive that
    is not Kraken OHLCVT is a real defect in whatever produced it, and reporting it as
    PENDING would let a corrupt file sit in `data/historical/` indefinitely with the
    criterion politely saying nothing.

    The first line is valid and the second is not, deliberately — see the test below for
    why a file whose *only* line is garbage takes a different path.
    """
    directory = phase4_tree / "data" / "historical"
    directory.mkdir(parents=True)
    (directory / "AAAUSD_15.csv").write_bytes(
        b"1700000100,100,101,99,100,1.5,7\nnot,a,timestamp,at,all,here\n"
    )

    outcome = run(verify_module, "replay_full_archive", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "did not load" in outcome.message


def test_a_single_garbage_line_reports_as_an_empty_archive(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """Pinned because it surprised me, not because it is wrong.

    `read_archive_rows` tolerates a header row — some mirrors add one — by skipping a
    first line that is not a timestamp. So a file whose **only** line is garbage is read
    as "a header and no bars" and reaches this criterion as an *empty* archive rather
    than as a parse failure. The verdict is FAIL either way and nothing is hidden from
    the gate; what changes is the sentence the operator reads, and this test is here so
    the next person to meet that sentence finds an explanation rather than a puzzle.
    """
    directory = phase4_tree / "data" / "historical"
    directory.mkdir(parents=True)
    (directory / "AAAUSD_15.csv").write_bytes(b"not,a,timestamp,at,all,here\n")

    outcome = run(verify_module, "replay_full_archive", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "was empty" in outcome.message


def test_an_empty_archive_file_is_a_fail(
    verify_module: ModuleType, phase4_tree: Path
) -> None:
    """A zero-row archive parses cleanly and reports a span of nothing.

    Without this the criterion would PASS over a directory of empty files and print
    `1 archive(s), 0 bars` — technically true, and exactly the shape of a build script
    that ran and produced nothing.
    """
    directory = phase4_tree / "data" / "historical"
    directory.mkdir(parents=True)
    (directory / "AAAUSD_15.csv").write_bytes(b"")

    outcome = run(verify_module, "replay_full_archive", phase4_tree)
    assert_fail(outcome, verify_module)
    assert "empty" in outcome.message
