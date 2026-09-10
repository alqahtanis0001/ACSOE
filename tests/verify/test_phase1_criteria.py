"""The eight Phase 1 console criteria. Spec 16 step 6.

Same two-sided proof spec 01 established for Phase 0, and for the same reason:
these criteria are written *before* the console they judge, so both halves have to
be provable against something other than the console.

* **PENDING** against a tree where the subject does not exist. A criterion that
  cannot reach that state would make Phase 1 impossible to start - `verify.py`
  would go red on the first commit and stay red for reasons nobody caused.
* **PASS** against a fabricated minimal subject. A criterion asserted only in the
  PENDING direction can be one that never manages to check anything.
* **FAIL** wherever the criterion has a real failure mode. Every one of these
  eight does, and a check that has never gone red is a comment. The red
  directions here are the interesting ones: a console that stamps its own command
  consumed, an amber frame on a paper screen, a suppressed focus ring, a numeric
  column with no tabular figures, a socket that accepts and never pushes.

The fabricated console is a plain ASGI application. The criteria drive an
application the way uvicorn does rather than through an HTTP client - the
repository's network guard patches `httpx.Client.send` for every test, so a
`TestClient` would raise before reaching the in-process transport - and the
minimal subject for that is an ASGI callable, not a FastAPI one.
"""

from __future__ import annotations

import inspect
import re
import shutil
import sqlite3
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.verify.conftest import (
    CONSOLE_APP_MODULE,
    CONSOLE_CSS,
    TOKENS_CSS,
    fabricate_console,
)

PHASE1_CRITERIA = (
    "console_renders_seeded_screens",
    "console_websocket_pushes_on_change",
    "console_commands_write_rows",
    "console_live_frame_amber",
    "console_tokens_no_raw_hex",
    "console_tabular_figures",
    "console_focus_and_reduced_motion",
    "console_restart_banner",
)

#: Which "nothing built yet" tree each criterion is quiet against. The four
#: dynamic criteria need `unbuilt_tree`, because the editable install puts the
#: real `acsoe` on `sys.path` from any working directory and a criterion pointed
#: at a tree with no `src/` would import the developer's own console instead. The
#: four static ones read files off disk and `bare_tree` is the honest picture.
PENDING_TREES = (
    ("console_renders_seeded_screens", "unbuilt_tree"),
    ("console_websocket_pushes_on_change", "unbuilt_tree"),
    ("console_commands_write_rows", "unbuilt_tree"),
    ("console_live_frame_amber", "bare_tree"),
    ("console_tokens_no_raw_hex", "bare_tree"),
    ("console_tabular_figures", "bare_tree"),
    ("console_focus_and_reduced_motion", "bare_tree"),
    ("console_restart_banner", "unbuilt_tree"),
)


_DOCSTRING = re.compile(r"(\"\"\"|''')(?:.|\n)*?\1")
_COMMENT = re.compile(r"(?m)^\s*#.*$")


def run(verify_module: ModuleType, check: str, root: Path) -> Any:
    """One criterion against `root`, through the runner's exception guard."""
    return verify_module.run_criterion(
        verify_module.Criterion(check, getattr(verify_module, "check_" + check)),
        verify_module.VerifyContext(root=root),
    )


def variant_app(old: str, new: str) -> str:
    """The fabricated console with one behaviour swapped out.

    A targeted replacement on the good module rather than a second copy, so a
    fabrication that drifts from the one the PASS tests use cannot make a red test
    pass for the wrong reason. The assertion is what makes that true: a marker
    that no longer matches is a test error, not a silently unmodified module.
    """
    assert old in CONSOLE_APP_MODULE, old
    return CONSOLE_APP_MODULE.replace(old, new)


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def test_all_eight_criteria_are_registered_for_phase_1(verify_module: ModuleType) -> None:
    """The eight of spec 16, plus the two that register in every phase.

    `docs_vocabulary` has always run everywhere. `toolchain_green` joined it at the
    Phase 1 close: registered for phase 0 alone, it let `--phase 1` report
    `7 PASS, 0 FAIL` while `pytest` was reporting two failures, because no Phase 1
    criterion made any claim about the suite. Order matters here as well as
    membership - the report is read top to bottom, and `criteria_for` returns
    registration order.
    """
    to_run, _ = verify_module.criteria_for(1, False)
    names = [c.name for c in to_run]
    assert names == ["docs_vocabulary", "toolchain_green", *PHASE1_CRITERIA]


def test_no_phase_1_criterion_touches_a_gitignored_directory(verify_module: ModuleType) -> None:
    """`data/`, `logs/` and `models/` are gitignored.

    A criterion reading one of them passes only on the machine that produced it,
    which `ai-workflow-rules.md` calls a broken criterion. Asserted on the source
    of every Phase 1 check and the helpers they share, because the defect is a
    path literal and a path literal is exactly what a source scan catches.

    Docstrings and comments are stripped first. `console_app`'s docstring says
    what it exists to prevent - the console opening `data/db/acsoe.sqlite` - and a
    scan that cannot tell a warning about a path from a use of it would force the
    reasoning out of the file to keep the test quiet.
    """
    helpers = (
        "console_workspace",
        "seeded_console_db",
        "console_config",
        "console_app",
        "close_console",
    )
    forbidden = ('"data"', "'data'", "data/db", "logs/", "models/", "runtime_paths")
    for name in [*("check_" + c for c in PHASE1_CRITERIA), *helpers]:
        source = inspect.getsource(getattr(verify_module, name))
        code = _COMMENT.sub("", _DOCSTRING.sub("", source))
        for token in forbidden:
            assert token not in code, f"{name} references {token}"


# --------------------------------------------------------------------------- #
# Quiet on a tree with nothing built
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("criterion", "tree"), PENDING_TREES)
def test_pending_when_the_console_does_not_exist(
    verify_module: ModuleType, request: pytest.FixtureRequest, criterion: str, tree: str
) -> None:
    root = request.getfixturevalue(tree)
    outcome = run(verify_module, criterion, root)
    assert outcome.result is verify_module.Result.PENDING, f"{criterion}: {outcome.message}"


# --------------------------------------------------------------------------- #
# PASS against a fabricated minimal console
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("criterion", PHASE1_CRITERIA)
def test_pass_against_a_fabricated_console(
    verify_module: ModuleType, console_tree: Path, criterion: str
) -> None:
    outcome = run(verify_module, criterion, console_tree)
    assert outcome.result is verify_module.Result.PASS, f"{criterion}: {outcome.message}"


# --------------------------------------------------------------------------- #
# console_renders_seeded_screens
# --------------------------------------------------------------------------- #


def test_an_empty_screen_body_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """A 200 with nothing in it is a screen that did not render."""
    fabricate_console(
        tree_with_harness,
        app_module=variant_app('{{"rows": []}}', ""),
    )
    outcome = run(verify_module, "console_renders_seeded_screens", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "empty body" in outcome.message


def test_a_screen_that_is_not_routed_yet_is_pending_not_failed(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """Specs 19 to 22 landing one at a time must not turn the gate red."""
    fabricate_console(
        tree_with_harness,
        app_module=variant_app(
            'if path in ("/api/feed", "/api/history", "/api/research"):',
            'if path in ("/api/feed", "/api/research"):',
        ),
    )
    outcome = run(verify_module, "console_renders_seeded_screens", tree_with_harness)
    assert outcome.result is verify_module.Result.PENDING
    assert "/api/history" in outcome.message


# --------------------------------------------------------------------------- #
# console_websocket_pushes_on_change
# --------------------------------------------------------------------------- #


def test_a_socket_that_accepts_and_never_pushes_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The failure the criterion exists for: a live connection with a dead poller.

    An endpoint that accepts the handshake and then says nothing looks healthy
    from the browser and leaves the operator watching a frozen screen.
    """
    fabricate_console(
        tree_with_harness,
        app_module=variant_app("if current != seen:", "if False:"),
    )
    outcome = run(verify_module, "console_websocket_pushes_on_change", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "nothing was pushed" in outcome.message


def test_a_console_that_pushes_on_a_timer_rather_than_on_change_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The failure the old form of this criterion could not see.

    Until 2026-09-10 the criterion moved the watermark and waited for any push, so a
    console pushing unconditionally satisfied it — "a push arrived within the budget"
    is true of a console that pushes constantly, and that console is wrong: the
    operator gets a screen that refreshes forever and never tells them anything
    changed. The criterion now watches a quiet window first, and a push there is a
    failure rather than an early success.

    `if current != seen:` becomes `if True:`, which is exactly a poll loop that has
    stopped comparing.
    """
    fabricate_console(
        tree_with_harness,
        app_module=variant_app("if current != seen:", "if True:"),
    )
    outcome = run(verify_module, "console_websocket_pushes_on_change", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "pushing on a timer" in outcome.message


def test_both_windows_come_from_config_not_from_a_literal(
    verify_module: ModuleType, console_tree: Path
) -> None:
    """`ui-context.md` makes the poll interval configuration.

    A criterion carrying its own copy of 500 would stop testing the console the
    moment the operator retuned the file, so the windows are asserted to move with
    `config/default.yaml` rather than to be constants. The quiet window is the one
    that appears in the PASS message, because it is the one carrying an assertion —
    the timeout is a safety net and deliberately does not read like a claim.
    """
    config = console_tree / "config" / "default.yaml"
    text = config.read_text(encoding="utf-8")
    assert "poll_interval_ms: 500" in text
    config.write_text(
        text.replace("poll_interval_ms: 500", "poll_interval_ms: 250"), encoding="utf-8"
    )
    outcome = run(verify_module, "console_websocket_pushes_on_change", console_tree)
    assert outcome.result is verify_module.Result.PASS
    assert "silent through 500ms" in outcome.message


def test_the_pass_message_still_reports_the_measured_time(
    verify_module: ModuleType, console_tree: Path
) -> None:
    """The evidence half, kept deliberately when the assertion half was loosened.

    The timeout is now twenty poll intervals and asserts nothing about promptness, so
    without the measured figure in the message a console that had become slow could
    degrade all the way to the safety net without anyone seeing it. The number in the
    message is what keeps a promptness regression visible without making it a
    spurious FAIL on a loaded machine.
    """
    outcome = run(verify_module, "console_websocket_pushes_on_change", console_tree)
    assert outcome.result is verify_module.Result.PASS
    assert "ms after the watermark moved" in outcome.message


# --------------------------------------------------------------------------- #
# console_commands_write_rows
# --------------------------------------------------------------------------- #


def test_a_console_that_stamps_its_own_command_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The console announces an intention; only the daemon's reader may claim it.

    A console that wrote `claimed_at` and `consumed_at` itself would let a
    `close_all` be marked done without any liquidation having happened - the one
    failure the two-phase consumption of `architecture-context.md` exists to
    prevent.
    """
    fabricate_console(tree_with_harness, command_stamp="1")
    outcome = run(verify_module, "console_commands_write_rows", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "both must be null" in outcome.message


def test_each_command_writes_exactly_one_row(
    verify_module: ModuleType, console_tree: Path
) -> None:
    """Three posts, three rows - proved against the database, not the response."""
    outcome = run(verify_module, "console_commands_write_rows", console_tree)
    assert outcome.result is verify_module.Result.PASS
    assert "activate, freeze, close_all" in outcome.message


# --------------------------------------------------------------------------- #
# console_live_frame_amber
# --------------------------------------------------------------------------- #


def test_an_unconditional_frame_border_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """Amber is reserved. A border that is not keyed to live mode puts it on paper."""
    fabricate_console(
        tree_with_harness,
        console_css=CONSOLE_CSS.replace(
            'html[data-mode="live"] { border: 3px solid var(--live); }',
            "body { border: 3px solid var(--live); }",
        ),
    )
    outcome = run(verify_module, "console_live_frame_amber", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "outside the live selector" in outcome.message


def test_a_frame_that_is_not_three_pixels_of_live_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    fabricate_console(
        tree_with_harness,
        console_css=CONSOLE_CSS.replace(
            "border: 3px solid var(--live);", "border: 1px solid var(--accent);"
        ),
    )
    outcome = run(verify_module, "console_live_frame_amber", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "3px" in outcome.message


def test_a_page_that_does_not_say_which_mode_it_is_in_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    fabricate_console(
        tree_with_harness,
        app_module=variant_app('data-mode="{{mode}}"', 'data-mode="paper"'),
    )
    outcome = run(verify_module, "console_live_frame_amber", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "live" in outcome.message


# --------------------------------------------------------------------------- #
# console_tokens_no_raw_hex
# --------------------------------------------------------------------------- #


def test_a_hex_in_the_stylesheet_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    fabricate_console(
        tree_with_harness,
        console_css=CONSOLE_CSS + "\n.warning { color: #C2604F; }\n",
    )
    outcome = run(verify_module, "console_tokens_no_raw_hex", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "#C2604F" in outcome.message


def test_a_hex_outside_the_root_block_of_tokens_css_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The exception is the `:root` block, not the file."""
    fabricate_console(
        tree_with_harness,
        tokens_css=TOKENS_CSS + "\n.badge { background: #4E9A6B; }\n",
    )
    outcome = run(verify_module, "console_tokens_no_raw_hex", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "#4E9A6B" in outcome.message


def test_a_fragment_link_spelled_in_hex_digits_is_not_a_colour(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """`href="#feed"` is four hex digits and is not a colour.

    A bare `#[0-9a-f]{3,8}` pattern flags every fragment link whose id happens to
    be spelled in a-f - `#feed`, `#dad`, `#face` - and the console's own cycle feed
    is one of them. A colour in CSS is never preceded by a quote; a fragment
    reference always is, and that is the whole discriminator.
    """
    fabricate_console(tree_with_harness)
    template = tree_with_harness / "src" / "acsoe" / "console" / "templates"
    template.mkdir(parents=True, exist_ok=True)
    (template / "index.html").write_text(
        '<a href="#feed">Cycle feed</a><a href="#dad">History</a>\n', encoding="utf-8"
    )
    outcome = run(verify_module, "console_tokens_no_raw_hex", tree_with_harness)
    assert outcome.result is verify_module.Result.PASS, outcome.message


# --------------------------------------------------------------------------- #
# console_tabular_figures
# --------------------------------------------------------------------------- #


def test_a_numeric_cell_without_the_class_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    fabricate_console(
        tree_with_harness,
        app_module=variant_app('<td class="num">1000.00</td>', "<td>1000.00</td>"),
    )
    outcome = run(verify_module, "console_tabular_figures", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "1000.00" in outcome.message


def test_a_second_tabular_mechanism_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """One mechanism. Two is how one column quietly stops being tabular."""
    fabricate_console(
        tree_with_harness,
        console_css=CONSOLE_CSS + "\n.figure { font-variant-numeric: tabular-nums; }\n",
    )
    outcome = run(verify_module, "console_tabular_figures", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert ".figure" in outcome.message


# --------------------------------------------------------------------------- #
# console_focus_and_reduced_motion
# --------------------------------------------------------------------------- #


def test_a_suppressed_focus_ring_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """`outline: none` on `:focus-visible` is worse than no rule at all.

    It looks like the requirement was met, and a keyboard operator loses every
    signal about where they are on the page.
    """
    fabricate_console(
        tree_with_harness,
        console_css=CONSOLE_CSS.replace(
            ":focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }",
            ":focus-visible { outline: none; }",
        ),
    )
    outcome = run(verify_module, "console_focus_and_reduced_motion", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "suppressed" in outcome.message


def test_a_reduced_motion_block_that_drops_nothing_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    fabricate_console(
        tree_with_harness,
        console_css=CONSOLE_CSS.replace(
            ".flash { animation: none; }", ".flash { opacity: 1; }"
        ),
    )
    outcome = run(verify_module, "console_focus_and_reduced_motion", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "does not drop the change flash" in outcome.message


# --------------------------------------------------------------------------- #
# console_restart_banner
# --------------------------------------------------------------------------- #


def test_a_console_that_never_says_restarted_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The two states are not the same event and must not look the same.

    One is a system waiting to be started; the other is a system that stopped on
    its own at 3am and came back not trading.
    """
    fabricate_console(
        tree_with_harness,
        app_module=variant_app(
            "if len(rows) >= 2 and rows[0][0] != rows[1][0]:", "if False:"
        ),
    )
    outcome = run(verify_module, "console_restart_banner", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "restart banner" in outcome.message


def test_a_console_that_always_says_restarted_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The other half. A banner that is always on carries no information."""
    fabricate_console(
        tree_with_harness,
        app_module=variant_app(
            "if len(rows) >= 2 and rows[0][0] != rows[1][0]:", "if True:"
        ),
    )
    outcome = run(verify_module, "console_restart_banner", tree_with_harness)
    assert outcome.result is verify_module.Result.FAIL
    assert "first start" in outcome.message


def test_the_first_start_branch_really_is_a_single_run_row(
    verify_module: ModuleType, console_tree: Path
) -> None:
    """`runs.run_id` is `NOT NULL UNIQUE`, so two rows can never share one.

    Spec 16 asks for "plain `Idle` when the two `run_id`s match", and the schema
    forbids that state outright. The equivalent branch - and the one an operator
    actually meets - is the first ever start, where there is no previous row to
    differ from. This asserts the helper builds exactly that, so the criterion is
    not quietly testing something else.
    """
    seed = pytest.importorskip("sqlite3")
    assert seed is sqlite3
    with verify_module.root_import_path(console_tree), verify_module.console_workspace() as tmp:
        db_path, early = verify_module.seeded_console_db(tmp)
        assert early is None, early
        conn = sqlite3.connect(db_path)
        try:
            assert int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]) == 2
        finally:
            conn.close()
        assert verify_module._keep_only_latest_run(db_path) == 1
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT run_id FROM runs").fetchall()
        finally:
            conn.close()
    assert [r[0] for r in rows] == ["run-b"]


# --------------------------------------------------------------------------- #
# The workspace is actually removed. Found the hard way.
# --------------------------------------------------------------------------- #


def test_the_console_workspace_is_gone_after_the_block(verify_module: ModuleType) -> None:
    """The check that would have caught both temp-directory leaks, and did not exist.

    `console_workspace` ended in `shutil.rmtree(..., ignore_errors=True)`. That is
    right in intent - failing to delete a throwaway database is not a verdict about
    the console - and it made the failure invisible, so a workspace that survived
    said nothing at all. Roughly 450MB per run accumulated across two hundred and
    fifty runs and filled a 923GB disk; the symptom was another agent's progress
    file being truncated to zero bytes by `OSError: [Errno 28]`.

    Neither `PermissionError` handling nor `ignore_errors=True` catches that. Only
    asking whether the directory is gone does.
    """
    with verify_module.console_workspace() as tmp:
        (tmp / "acsoe.sqlite").write_bytes(b"not really a database")
        assert tmp.exists()
    assert not tmp.exists()


def test_a_workspace_still_held_open_is_reported_rather_than_swallowed(
    verify_module: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """A leak that cannot be seen is the case to design for.

    The visible leak - `verify.py` printing a `PermissionError` above its report on
    every phase-0 run - was two orders of magnitude smaller than the silent one, and
    it was fixed first precisely because it announced itself. So the surviving case
    now prints to stderr: not into the criterion's message, which must not turn a
    PASS into a FAIL over a directory, but somewhere a person will see it.
    """
    with verify_module.console_workspace() as tmp:
        db_path = tmp / "acsoe.sqlite"
        held = sqlite3.connect(db_path)
        held.execute("CREATE TABLE t (id INTEGER)")
        held.commit()
        try:
            assert db_path.exists()
        finally:
            pass
    survived = tmp.exists()
    held.close()
    shutil.rmtree(tmp, ignore_errors=True)
    if survived:
        assert "could not delete its workspace" in capsys.readouterr().err
