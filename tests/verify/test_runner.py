"""The runner and the criterion framework. Spec 00.

Result precedence, exit codes, `--live`, and - the one that matters most - that a
criterion which raises is reported FAIL rather than taking the whole run down with
it. One badly written check must never be able to hide the state of the other six.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


@pytest.fixture
def isolated_registry(verify_module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> dict[int, Any]:
    """A registry the test owns, so registering into it cannot leak."""
    registry: dict[int, list[Any]] = {
        p: [] for p in range(verify_module.MIN_PHASE, verify_module.MAX_PHASE + 1)
    }
    monkeypatch.setattr(verify_module, "_REGISTRY", registry)
    return registry


def _criterion(verify_module: ModuleType, name: str, outcome_fn: Any, live: bool = False) -> Any:
    return verify_module.Criterion(name, outcome_fn, live)


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


def test_there_are_exactly_three_results(verify_module: ModuleType) -> None:
    """PASS, FAIL, PENDING and nothing else. The three-valued result is what lets
    criteria exist before the code they judge."""
    assert {r.value for r in verify_module.Result} == {"PASS", "FAIL", "PENDING"}


def test_a_criterion_that_raises_is_reported_fail_not_a_crash(verify_module: ModuleType) -> None:
    """Spec 00 step 8. A check with a bug in it must degrade to one red line, not
    a traceback that hides the other six criteria."""

    def explodes(ctx: Any) -> Any:
        raise RuntimeError("the check itself is broken")

    outcome = verify_module.run_criterion(
        _criterion(verify_module, "explodes", explodes),
        verify_module.VerifyContext(root=Path.cwd()),
    )
    assert outcome.result is verify_module.Result.FAIL
    assert "criterion raised" in outcome.message
    assert "RuntimeError" in outcome.message
    assert "the check itself is broken" in outcome.message


def test_a_keyboard_interrupt_is_not_swallowed(verify_module: ModuleType) -> None:
    """`except Exception`, never `except BaseException`: a long verify run has to
    stay interruptible."""

    def interrupted(ctx: Any) -> Any:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        verify_module.run_criterion(
            _criterion(verify_module, "interrupted", interrupted),
            verify_module.VerifyContext(root=Path.cwd()),
        )


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def test_registering_the_same_name_twice_in_one_phase_is_refused(
    verify_module: ModuleType, isolated_registry: dict[int, Any]
) -> None:
    """Two criteria with one name means one of them is invisible in the report."""
    criterion = _criterion(verify_module, "duplicate", lambda ctx: verify_module.passed("ok"))
    verify_module.register(0, criterion)
    with pytest.raises(ValueError, match="already registered"):
        verify_module.register(0, criterion)


def test_registering_outside_the_phase_range_is_refused(
    verify_module: ModuleType, isolated_registry: dict[int, Any]
) -> None:
    with pytest.raises(ValueError, match="outside"):
        verify_module.register(9, _criterion(verify_module, "x", lambda ctx: None))


def test_docs_vocabulary_is_registered_in_every_phase(verify_module: ModuleType) -> None:
    """Spec 02 step 1. Every audit found a decision that reached three files and
    not the fourth, so the check runs in all nine phases, not just phase 0."""
    for phase in range(verify_module.MIN_PHASE, verify_module.MAX_PHASE + 1):
        names = [c.name for c in verify_module._REGISTRY[phase]]
        assert "docs_vocabulary" in names, phase


def test_each_phase_registers_its_own_criteria_and_no_others(
    verify_module: ModuleType,
) -> None:
    """Spec 00 scope limit: a phase's criteria belong to that phase alone.

    **Two criteria are exceptions and register everywhere**: `docs_vocabulary`
    from spec 02, and `toolchain_green`, which joined it at the Phase 1 close.
    Until then `toolchain_green` ran in phase 0 only, and `--phase 1` reported
    `7 PASS, 0 FAIL` on a tree where `pytest` was reporting two failures - no
    Phase 1 criterion made any claim about the suite, so a red suite was
    invisible to the gate that defines "done". Both are asserted into every
    phase's expected set below rather than special-cased, so a future change
    that drops one from a phase fails here.

    Phase 0's own five are frozen. Phase 1 added the eight console criteria of
    spec 16; phases 2 to 8 are still unwritten and carry only the two that
    register everywhere. The point of asserting the whole registry rather than
    one phase is that adding a criterion to the wrong phase is silent - it would
    simply never run, or run a phase too early.
    """
    every_phase = {"docs_vocabulary", "toolchain_green"}

    assert {c.name for c in verify_module._REGISTRY[0]} == every_phase | {
        "orchestrator_empty_registry",
        "db_migrates_from_empty",
        "seed_fixtures_present",
        "record_sample_valid",
        "is_gate_matches_registry",
    }
    assert {c.name for c in verify_module._REGISTRY[1]} == every_phase | {
        "console_renders_seeded_screens",
        "console_websocket_pushes_on_change",
        "console_commands_write_rows",
        "console_live_frame_amber",
        "console_tokens_no_raw_hex",
        "console_tabular_figures",
        "console_focus_and_reduced_motion",
        "console_restart_banner",
    }
    # `commands_round_trip` was registered by the lead at the phase opening rather
    # than by a spec: it judges the command-reader defect found at the Phase 1
    # close, which existed before any Phase 2 work began. The six below are spec 33.
    assert {c.name for c in verify_module._REGISTRY[2]} == every_phase | {
        "commands_round_trip",
        "recording_span_continuous",
        "candles_match_kraken_ohlc",
        "data_guard_blocks_bad_data",
        "historical_loader_reports_gaps",
        "console_shows_live_rows",
        "console_reads_persisted_mode",
    }
    # Spec 45, registered before three of the four engines they judge. Until they
    # existed `--phase 3` carried `every_phase` alone and printed "Phase 3 is green"
    # over a phase whose engines were unbuilt.
    assert {c.name for c in verify_module._REGISTRY[3]} == every_phase | {
        "cost_gate_uses_live_fee_tier",
        "risk_rejects_sub_ordermin",
        "universe_varies_with_balance",
        "safety_freezes_on_drawdown_without_opportunity_chain",
        "safety_escalates_on_sustained_outage",
        "safety_inputs_all_from_the_seed",
        "phase_3_gates_have_both_tests",
    }
    # Spec 48, registered first in Phase 4 and ahead of every subject it judges.
    # `replay_full_archive` is the project's first `--live` criterion and is in this
    # set because `_REGISTRY` holds it; `criteria_for(4, False)` is what leaves it out.
    assert {c.name for c in verify_module._REGISTRY[4]} == every_phase | {
        "memory_records_every_blocker",
        "memory_writes_safety_inputs_live",
        "rejections_survive_restart",
        "labelled_sample_replayed_from_archive",
        "labeller_matches_hand_verified_labels",
        "walkforward_folds_purged_and_embargoed",
        "console_history_reads_real_rows",
        "replay_full_archive",
    }
    for phase in range(5, verify_module.MAX_PHASE + 1):
        assert {c.name for c in verify_module._REGISTRY[phase]} == every_phase


# --------------------------------------------------------------------------- #
# --live
# --------------------------------------------------------------------------- #


def test_live_criteria_are_skipped_unless_live_is_passed(
    verify_module: ModuleType, isolated_registry: dict[int, Any]
) -> None:
    """`--live` is opt-in and never required for a phase to be green."""
    offline = _criterion(verify_module, "offline", lambda ctx: verify_module.passed("ok"))
    online = _criterion(verify_module, "online", lambda ctx: verify_module.passed("ok"), live=True)
    verify_module.register(0, offline)
    verify_module.register(0, online)

    to_run, skipped = verify_module.criteria_for(0, live=False)
    assert [c.name for c in to_run] == ["offline"]
    assert [c.name for c in skipped] == ["online"]

    to_run, skipped = verify_module.criteria_for(0, live=True)
    assert [c.name for c in to_run] == ["offline", "online"]
    assert skipped == []


def test_no_phase_zero_criterion_requires_the_network(verify_module: ModuleType) -> None:
    """Every criterion must run offline with no API key and pass on a fresh clone."""
    assert not any(c.live for c in verify_module._REGISTRY[0])


# --------------------------------------------------------------------------- #
# Exit codes
# --------------------------------------------------------------------------- #


def test_a_fail_exits_non_zero(
    verify_module: ModuleType, isolated_registry: dict[int, Any], capsys: Any
) -> None:
    verify_module.register(
        0, _criterion(verify_module, "broken", lambda ctx: verify_module.failed("nope"))
    )
    assert verify_module.main(["--phase", "0"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_pending_alone_exits_zero(
    verify_module: ModuleType, isolated_registry: dict[int, Any], capsys: Any
) -> None:
    """Mid-phase the bar is no FAIL. PENDING is expected until phase close, and the
    phase-close judgement is the lead's, from the printed counts - not the exit
    code's."""
    verify_module.register(
        0, _criterion(verify_module, "unbuilt", lambda ctx: verify_module.pending("not yet"))
    )
    assert verify_module.main(["--phase", "0"]) == 0
    out = capsys.readouterr().out
    assert "PENDING" in out
    assert "not green" in out


def test_all_pass_exits_zero_and_says_the_phase_is_green(
    verify_module: ModuleType, isolated_registry: dict[int, Any], capsys: Any
) -> None:
    verify_module.register(
        0, _criterion(verify_module, "fine", lambda ctx: verify_module.passed("all good"))
    )
    assert verify_module.main(["--phase", "0"]) == 0
    assert "is green" in capsys.readouterr().out


def test_one_fail_among_passes_still_exits_non_zero(
    verify_module: ModuleType, isolated_registry: dict[int, Any]
) -> None:
    verify_module.register(
        0, _criterion(verify_module, "fine", lambda ctx: verify_module.passed("ok"))
    )
    verify_module.register(
        0, _criterion(verify_module, "unbuilt", lambda ctx: verify_module.pending("not yet"))
    )
    verify_module.register(
        0, _criterion(verify_module, "broken", lambda ctx: verify_module.failed("nope"))
    )
    assert verify_module.main(["--phase", "0"]) == 1


def test_a_raising_criterion_makes_the_run_non_zero_without_stopping_it(
    verify_module: ModuleType, isolated_registry: dict[int, Any], capsys: Any
) -> None:
    """The other criteria still report. That is the whole reason for catching."""

    def explodes(ctx: Any) -> Any:
        raise ValueError("boom")

    verify_module.register(0, _criterion(verify_module, "explodes", explodes))
    verify_module.register(
        0, _criterion(verify_module, "fine", lambda ctx: verify_module.passed("still ran"))
    )
    assert verify_module.main(["--phase", "0"]) == 1
    out = capsys.readouterr().out
    assert "still ran" in out
    assert "criterion raised" in out


# --------------------------------------------------------------------------- #
# The command line
# --------------------------------------------------------------------------- #


def test_phase_is_required(verify_module: ModuleType) -> None:
    with pytest.raises(SystemExit):
        verify_module.main([])


@pytest.mark.parametrize("phase", ["-1", "9", "42"])
def test_a_phase_outside_the_range_is_refused(verify_module: ModuleType, phase: str) -> None:
    with pytest.raises(SystemExit):
        verify_module.main(["--phase", phase])


def test_live_is_accepted_and_changes_which_criteria_run(
    verify_module: ModuleType, isolated_registry: dict[int, Any], capsys: Any
) -> None:
    verify_module.register(
        0, _criterion(verify_module, "online", lambda ctx: verify_module.passed("ok"), live=True)
    )
    assert verify_module.main(["--phase", "0"]) == 0
    without = capsys.readouterr().out
    assert "1 live criteria skipped" in without
    assert "0 criteria:" in without

    assert verify_module.main(["--phase", "0", "--live"]) == 0
    with_live = capsys.readouterr().out
    assert "online" in with_live
    assert "1 criteria:" in with_live


# --------------------------------------------------------------------------- #
# The report
# --------------------------------------------------------------------------- #


def test_the_report_counts_every_result_and_names_every_criterion(
    verify_module: ModuleType,
) -> None:
    results = [
        (_criterion(verify_module, "a", None), verify_module.passed("ok")),
        (_criterion(verify_module, "b", None), verify_module.pending("later")),
        (_criterion(verify_module, "c", None), verify_module.failed("no")),
    ]
    report = verify_module.format_report(0, Path("/repo"), results, [])
    assert "1 PASS" in report
    assert "1 FAIL" in report
    assert "1 PENDING" in report
    for name in ("a", "b", "c"):
        assert name in report
    assert "has FAILs" in report


def test_an_empty_phase_reports_cleanly_rather_than_dividing_by_zero(
    verify_module: ModuleType,
) -> None:
    report = verify_module.format_report(5, Path("/repo"), [], [])
    assert "no criteria registered" in report
