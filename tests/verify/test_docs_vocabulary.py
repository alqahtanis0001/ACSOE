"""`docs_vocabulary`, and the proof that it fails when it should. Spec 02.

The negative test is the point of this module. A check that has never been shown
to fail is not a check - and this one is a grep over prose, which is exactly the
kind of thing that can quietly stop matching anything at all and go on reporting
PASS forever.

So every rule the criterion implements is proved in both directions: a planted term
in a current-state section FAILs, the same term in the decision history stays
quiet, a qualified term without its cue stays quiet and with its cue FAILs, and the
qualifier is proved to come from the table rather than from the code by editing the
table and watching the behaviour change.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

TRACKER = Path("context") / "progress-tracker.md"
RULES = Path("context") / "ai-workflow-rules.md"


def insert_after_heading(path: Path, heading: str, text: str) -> None:
    """Plant `text` immediately below `heading`, inside that section."""
    lines = path.read_text(encoding="utf-8").splitlines()
    index = next(i for i, line in enumerate(lines) if line.strip() == heading)
    lines.insert(index + 1, text)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def run(verify_module: ModuleType, root: Path):  # type: ignore[no-untyped-def]
    return verify_module.check_docs_vocabulary(verify_module.VerifyContext(root=root))


# --------------------------------------------------------------------------- #
# The current tree
# --------------------------------------------------------------------------- #


def test_passes_on_the_real_repository(verify_module: ModuleType, repo_root: Path) -> None:
    outcome = run(verify_module, repo_root)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    assert "no hit" in outcome.message


def test_the_term_list_is_parsed_from_the_table_not_hardcoded(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """Spec 02 step 2. Adding a row to the table is all it takes to extend the
    check, so the terms must come out of the document."""
    table = verify_module.parse_retired_terms(repo_root)
    terms = {entry.term for entry in table.terms}
    assert {"two-chain", "INGEST_CHAIN", 'state["system_mode"]', "24 bars", "eight"} <= terms
    assert "chain 1" in terms and "chain 2" in terms and "always chain" in terms


def test_a_row_with_no_qualifier_parses_as_an_unconditional_term(
    verify_module: ModuleType, repo_root: Path
) -> None:
    table = verify_module.parse_retired_terms(repo_root)
    by_term = {entry.term: entry for entry in table.terms}
    assert by_term["INGEST_CHAIN"].qualifiers == ()
    assert by_term["eight"].qualifiers  # the one row that carries cues


# --------------------------------------------------------------------------- #
# The negative test
# --------------------------------------------------------------------------- #


def test_a_planted_term_in_a_current_state_section_fails(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """The whole point. Without this the criterion could match nothing forever."""
    insert_after_heading(
        bare_tree / TRACKER,
        "## Locked Decisions",
        "- The orchestrator runs INGEST_CHAIN before everything else.",
    )
    outcome = run(verify_module, bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "INGEST_CHAIN" in outcome.message
    assert "progress-tracker.md" in outcome.message


def test_the_report_names_the_file_the_line_and_the_term(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """A hit nobody can locate is a hit nobody fixes. Spec 02 step 7."""
    insert_after_heading(
        bare_tree / TRACKER, "## Locked Decisions", "- Chain 2 is exactly three engines."
    )
    outcome = run(verify_module, bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    hit = outcome.message.split(": ", 1)[1]
    file_part, line_part, _ = hit.split(":", 2)
    assert file_part == "context/progress-tracker.md"
    assert int(line_part) > 0


def test_the_same_term_in_the_decision_history_stays_quiet(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """That section is the record of superseded decisions and is *meant* to name
    retired terms.

    Planted with `insert_after_heading` rather than appended to the file. The first
    draft of this test appended at EOF assuming `## Decision history` was the last
    section; it is not - `## Architecture Decisions`, `## Known Risks` and
    `## Session Notes` follow it - so the plant landed in current-state text and the
    test failed. The criterion was right and the test was wrong, which is worth a
    comment because the next person will assume the same thing.
    """
    insert_after_heading(
        bare_tree / TRACKER,
        "## Decision history",
        "- INGEST_CHAIN was renamed to GUARD_CHAIN by the fifth audit.",
    )
    outcome = run(verify_module, bare_tree)
    assert outcome.result is verify_module.Result.PASS, outcome.message


def test_only_the_decision_history_is_excluded_from_the_tracker(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Excluding the whole tracker is how a stale claim survived three audits
    inside a section labelled Architecture Decisions. Both plants land in the same
    file; only the one below `## Decision history` is forgiven."""
    tracker = bare_tree / TRACKER
    insert_after_heading(
        tracker, "## Decision history", "- INGEST_CHAIN, mentioned in history, is fine."
    )
    insert_after_heading(tracker, "## Open Questions", "- What replaced INGEST_CHAIN?")
    outcome = run(verify_module, bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert outcome.message.count("INGEST_CHAIN") == 1


def test_strikethrough_is_ignored(verify_module: ModuleType, bare_tree: Path) -> None:
    """Spec 02 step 5. A struck-through mention is already marked superseded."""
    insert_after_heading(
        bare_tree / TRACKER, "## Locked Decisions", "- ~~INGEST_CHAIN~~ is now `GUARD_CHAIN`."
    )
    assert run(verify_module, bare_tree).result is verify_module.Result.PASS


def test_a_plant_in_agents_md_is_caught(verify_module: ModuleType, bare_tree: Path) -> None:
    """Twice now a rule has landed in `context/` and missed the entry point every
    agent reads first, so `AGENTS.md` and `README.md` are scanned too."""
    append(bare_tree / "AGENTS.md", "The timeout is 24 bars.")
    outcome = run(verify_module, bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "AGENTS.md" in outcome.message


# --------------------------------------------------------------------------- #
# Word boundaries
# --------------------------------------------------------------------------- #


def test_the_current_plural_is_not_mistaken_for_the_retired_singular(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """`paper.starting_balance` is retired and `paper.starting_balances` is
    current, and the retired string is a prefix of the live one. Without a trailing
    word boundary the check fails on the very file that defines the rule."""
    insert_after_heading(
        bare_tree / TRACKER,
        "## Locked Decisions",
        "- Balance falls back to `paper.starting_balances`, a per-currency map.",
    )
    assert run(verify_module, bare_tree).result is verify_module.Result.PASS

    insert_after_heading(
        bare_tree / TRACKER, "## Locked Decisions", "- Balance falls back to `paper.starting_balance`."
    )
    assert run(verify_module, bare_tree).result is verify_module.Result.FAIL


@pytest.mark.parametrize(
    "sentence",
    [
        "- No ensemble weight may override a gate.",
        "- The eighth audit found five issues.",
        "- Weight is a column heading, not a count.",
    ],
)
def test_the_retired_count_does_not_match_inside_another_word(
    verify_module: ModuleType, bare_tree: Path, sentence: str
) -> None:
    """`eight` is a substring of "weight" and of "eighth", and both appear in the
    real documents in current-state sections."""
    insert_after_heading(bare_tree / TRACKER, "## Locked Decisions", sentence)
    assert run(verify_module, bare_tree).result is verify_module.Result.PASS, sentence


def test_matching_is_case_insensitive(verify_module: ModuleType, bare_tree: Path) -> None:
    """A stale `Chain 2` at the start of a sentence is the same defect."""
    insert_after_heading(bare_tree / TRACKER, "## Locked Decisions", "- Chain 2 holds 21, 22, 19.")
    assert run(verify_module, bare_tree).result is verify_module.Result.FAIL


# --------------------------------------------------------------------------- #
# Qualifiers
# --------------------------------------------------------------------------- #


def test_a_qualified_term_without_its_cue_stays_quiet(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """`eight` is retired only when it counts engines. It is a perfectly good word
    in any other sentence, and a bare-token match would make it unusable across
    every document - which is what it did on first run."""
    insert_after_heading(
        bare_tree / TRACKER,
        "## Open Questions",
        "- Eight config values are trading behaviour the lead may not invent.",
    )
    assert run(verify_module, bare_tree).result is verify_module.Result.PASS


def test_a_qualified_term_with_its_cue_fails(verify_module: ModuleType, bare_tree: Path) -> None:
    """The actual historical defect: both cues on one line."""
    insert_after_heading(
        bare_tree / TRACKER,
        "## Locked Decisions",
        "- Twenty-three engines run in a fixed order. Eight contain no models.",
    )
    outcome = run(verify_module, bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "`eight`" in outcome.message


def test_the_qualifier_is_data_in_the_table_not_a_rule_in_the_code(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Spec 02's scope limit forbids hardcoding the term list, and a term-specific
    rule in code is a hardcode wearing a disguise.

    Proved by editing the table: blank the `eight` row's qualifier column in the
    fixture tree and the bare word starts matching, with no code change. If the
    qualifier were special-cased in the checker, this would still pass.
    """
    rules = bare_tree / RULES
    text = rules.read_text(encoding="utf-8")
    original = "| `eight` | `machine learning`, `non-ML`, or `engines` |"
    assert original in text, "the retired-term table has been reshaped; update this test"
    rules.write_text(text.replace(original, "| `eight` | — |"), encoding="utf-8")

    insert_after_heading(
        bare_tree / TRACKER, "## Open Questions", "- Eight config values are unset."
    )
    outcome = run(verify_module, bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "`eight`" in outcome.message


# --------------------------------------------------------------------------- #
# Excluded regions
# --------------------------------------------------------------------------- #


def test_the_retired_vocabulary_section_is_excluded(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """A section whose job is to catalogue superseded things necessarily names
    them - the table, and the prose explaining the table. A quotation of a defect
    is the one thing that will always look exactly like the defect."""
    insert_after_heading(
        bare_tree / RULES,
        "## Retired vocabulary",
        "For example, INGEST_CHAIN was renamed and `chain 1` had no name.",
    )
    assert run(verify_module, bare_tree).result is verify_module.Result.PASS


def test_the_exclusion_is_a_section_and_not_the_whole_file(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """"Never a whole file" is the lead's condition on the exclusion. A term in a
    different section of the same document is still a hit."""
    insert_after_heading(
        bare_tree / RULES, "## Build order", "The orchestrator runs INGEST_CHAIN first."
    )
    outcome = run(verify_module, bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "ai-workflow-rules.md" in outcome.message


def test_a_section_after_the_excluded_one_is_still_scanned(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """`## Decision history` is not the tracker's last section. The exclusion must
    stop at the next `## ` heading, so `## Architecture Decisions`,
    `## Known Risks` and `## Session Notes` are current-state text and are scanned.

    This is the case that broke the first draft of the test above, so it is asserted
    directly rather than left as an assumption.
    """
    insert_after_heading(
        bare_tree / TRACKER, "## Known Risks", "- INGEST_CHAIN may still be referenced."
    )
    outcome = run(verify_module, bare_tree)
    assert outcome.result is verify_module.Result.FAIL
    assert "INGEST_CHAIN" in outcome.message


def test_a_subheading_does_not_end_an_excluded_section(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """`### What this check does not catch` sits inside `## Retired vocabulary`.
    Only the next `## ` ends the region."""
    excluded = verify_module.section_lines(repo_root / RULES, "## Retired vocabulary")
    lines = (repo_root / RULES).read_text(encoding="utf-8").splitlines()
    subheading = next(
        i for i, line in enumerate(lines, start=1) if line.startswith("### What this check")
    )
    assert subheading in excluded


def test_a_missing_retired_term_table_is_a_failure_not_a_pass(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """If the table is deleted the check must go red, not silently start passing
    because it has nothing left to look for."""
    rules = bare_tree / RULES
    rules.write_text("# Development Workflow\n\nNothing here.\n", encoding="utf-8")
    outcome = verify_module.run_criterion(
        verify_module.Criterion("docs_vocabulary", verify_module.check_docs_vocabulary),
        verify_module.VerifyContext(root=bare_tree),
    )
    assert outcome.result is verify_module.Result.FAIL
    assert "criterion raised" in outcome.message
