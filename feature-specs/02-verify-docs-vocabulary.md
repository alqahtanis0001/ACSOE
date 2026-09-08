# 02 — `docs_vocabulary` criterion

**Owner:** C — Interface and models

## Goal

The retired-vocabulary check specified in `context/ai-workflow-rules.md` runs as a criterion
in every phase, so a renamed term that reached three files and not the fourth fails loudly
instead of being found by the next audit.

## Implementation

1. In `scripts/verify.py`, add a `docs_vocabulary` criterion registered for **every** phase,
   0 to 8.
2. Parse the retired-term table out of `context/ai-workflow-rules.md` rather than hardcoding
   the terms, so adding a row to that table is all it takes to extend the check.
3. Scan `AGENTS.md`, `README.md` and `context/*.md`.
4. Ignore text inside `~~strikethrough~~`, and ignore the retired-term table itself, which
   necessarily names every term.
5. Ignore exactly one region: the `## Decision history` section of
   `context/progress-tracker.md`, ending at the next `## ` heading. Every other part of the
   tracker — Current Goal, Locked Decisions, Architecture Decisions, Known Risks — is
   current-state text and is scanned like any other file.
6. FAIL with file, line number and the matched term for each hit. PASS with a count of files
   scanned when there are none.
7. Add `tests/verify/test_docs_vocabulary.py` with a **negative test**: plant a retired term
   in a current-state section of a fixture tracker and assert FAIL; plant one in the decision
   history and assert it stays quiet. A check that has never been shown to fail is not a check.

## Scope Limits

- Do **not** edit any context file to make the check pass. A hit is a real defect and goes to
  the lead.
- Do **not** hardcode the term list.
- Do **not** widen the exclusion back to the whole tracker.
- Do **not** attempt to detect unpropagated *new* rules. This check finds stale tokens only;
  that limit is documented in `ai-workflow-rules.md` and the manual procedure covers the rest.

## Check When Done

- `python scripts/verify.py --phase 0` includes `docs_vocabulary` and it PASSes on the
  current tree.
- The negative test proves it FAILs on a planted term in a current-state section and stays
  quiet on one in the decision history.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
