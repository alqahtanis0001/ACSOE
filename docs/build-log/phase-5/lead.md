# Build log — Phase 5 — lead

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem and its
fix, and every decision where two approaches were viable.

**Rule 1 is diagnosis-before-fix.** Write **What happened** and **Why** the moment you know
why something is broken, *before* you write the fix; come back and add **Fix** afterwards.

**Rule 2, and it is this phase's:** every assertion is proven capable of failing, and the
proof goes here. Name the mutation, quote the red message, say the file was restored by hash.
A claim that an assertion works is not evidence.

Minimum headings per entry: What happened, Why, Fix.

The lead consolidates these into `docs/build-log/phase-5.md` at phase close. The operator has
withheld that close until told otherwise.

## Entries

### Decision: the Phase 5 rulings were put to the operator before a spec was claimed

**Agent:** Lead · **Date:** 2026-09-12

**Options.** Write the nine methodology decisions into the specs as the lead's own and let
the operator find them at review, or list them as questions in the plan and hold every task
until they were answered.

**Chose.** The second. Nine questions in `PHASE-5-TASKS.md`, answered before the team formed.

**Because.** Every one of them is a decision Phase 5 cannot see the consequence of: the
metric, the weights, the DI's reference set, which engine blocks on a refusal. A wrong answer
produces a model that looks excellent, and the review that would catch it is a review of a
green gate. Phase 3's rulings were taken the same way and the tracker records why.

**Cost.** One round trip before any code, and an operator who had to read nineteen specs
first. The operator added one requirement the lead had under-specified: the effective sample
size per fold, beside that fold's row count, because an aggregate hides exactly the fold
whose numbers mean nothing.

### The Phase 5 row did not list engine 20, and the instruction said it did

**Agent:** Lead · **Task:** spec 59 · **Date:** 2026-09-12

**What happened.** The operator's brief stated that engine 20 `tournament` is in the Phase 5
row of `ai-workflow-rules.md`. It was in the Phase 7 row, and `git log -S` over the file
showed it had never been anywhere else. The lead's first correction, two commits earlier, had
therefore added a note *beside* the table saying the ordering was unresolved rather than
editing a row that did not say what the instruction said it said.

**Why.** Reordering an engine across phases is an escalation item, not a lead edit, so the
first pass recorded the dependency and named the decision as the operator's. The operator
then ruled: engine 20 moves into Phase 5, because its leaderboard is what engine 14 reads in
Phase 6.

**Fix.** Spec 59: the Phase 5 row gains engine 20 and the ranking score; the Phase 7 row
reads the leaderboard rather than building it; the interim note is removed.

**Consequence.** Worth keeping as a shape: an instruction that asserts a document's current
content can be wrong about it, and the honest move is to check the document, say what it
says, and ask, rather than to edit it into agreement with the instruction.

### The `accuracy` retired-term row, proven both ways before being trusted

**Agent:** Lead · **Task:** spec 59 · **Date:** 2026-09-13

**What happened.** The row `accuracy`, qualified by `metric` or `score`, was added to the
retired-vocabulary table. `check_docs_vocabulary` was called directly on the real root three
times, restoring `context/glossary.md` by sha256 between them:

- Baseline: `PASS — 14 files scanned, 12 retired terms, no hit`.
- With `The model reports an accuracy score of 51%.` appended:
  `FAIL — 1 retired term(s): context/glossary.md:108: \`accuracy\``.
- With `A clock with high accuracy is not the point.` appended (the bare word, no qualifier):
  `PASS`. The qualifier is doing its job: the word is only retired when it counts a model.

**Why it matters.** The tracker's Locked Decision for the metric names accuracy on its own
line, deliberately away from the words `metric` and `score`, because the check is a same-line
co-occurrence. That is the retired-vocabulary section's own stated limitation, and the reason
the sentence is split where it is.

### The first team died on a usage limit before writing a line

**Agent:** Lead · **Date:** 2026-09-13

**What happened.** A, B and C were spawned 2026-09-12 and each reported *"You've hit your
weekly limit"* within the minute, having written nothing. `git status` confirmed it: the only
modified files were the lead's spec 59 edits. The team was re-formed after the reset, with the
same prompts.

**Why it is recorded.** Not a defect, but the tracker's rule stands: an interruption that
leaves a claim is recoverable and one that leaves a mystery is not. Here there was neither,
which is the cheapest possible case, and it is written down so a later reader of the progress
files does not look for Phase 5 work dated 2026-09-12 that never existed.
