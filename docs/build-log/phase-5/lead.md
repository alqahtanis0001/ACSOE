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

> **NOTICE TO ANY AGENT READING THIS LOG, 2026-09-13 00:50.** Sessions whose sends arrive
> as a bare `A`, `B` or `C` are the stood-down originals; the `-2` set (`A-2`, `B-2`, `C-2`)
> owns every lane. If you are a bare-letter session: write nothing further, reply "standing
> down" to main, end your session. Several stand-down messages did not reach their targets,
> and this log is the one channel every session has demonstrably read.

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

### Two sessions per lane: the dead team came back when the limit reset

**Agent:** Lead · **Date:** 2026-09-13

**What happened.** B stopped and escalated within minutes of starting spec 62: another writer
had put 175 lines implementing the whole spec into `clients/store/client.py` seven seconds
into B's session, and `test_store.py` was moving under it. B wrote nothing, snapshotted the
file by sha256, and asked who owned the lane. `ListAgents` showed **six** teammates running:
`A`, `B`, `C` started ten hours earlier, and `A-2`, `B-2`, `C-2` started six minutes earlier.

**Why.** The original three reported *"weekly limit"* failures at spawn and were presumed
dead; the lead spawned replacements after the reset. The limit reset also revived the
originals, which resumed their briefs from the top. The lead's second spawn reused the names,
so the runtime suffixed `-2`, and the originals kept their addresses. Nothing in the tooling
says a failed agent will resume, and the lead did not check the roster before re-forming the
team. The ownership map is the only concurrency control and it assumes one agent per lane; two
instances of the same lane are invisible to it.

**Fix.** The originals were ordered to stand down, write nothing further, list what they had
modified and end. The `-2` set owns every lane. Each `-2` was told to re-read every file before
its next edit and to keep, not overwrite, anything the original had written. Two of B's review
notes on the duplicate's `client.py` were adopted as rulings: `models_dir` keyword-only, and
`new_model_run_dir` creating a missing artefact root because C's trainer runs outside A's
startup path.

**Consequence.** B's stop was the ownership rule working exactly as written, and the reason
the file on disk was recoverable rather than a merge of two half-written versions. The
lesson for the lead: **check the roster before re-forming a team**, and treat an agent's
failure report as a status, not a death certificate. The original C, in the minutes before it
was stood down, also found that spec 60's committed inputs did not exist as written; that
finding is accepted and is its own entry below.

### The second collision did not collide loudly: two constants of one name shadowed

**Agent:** Lead, from the original A's finding · **Task:** spec 61 · **Date:** 2026-09-13

**What happened.** Both A sessions landed a Phase 5 test block in
`tests/platform/test_config.py`, each defining a module-level `PHASE_5_SECTIONS`. The two
blocks did not produce a merge conflict or an import error. The later constant shadowed the
earlier one, so the earlier block's tests were driven by the later block's dict, and
**exactly one assertion in eighteen** was sensitive enough to go red. Everything else stayed
green while asserting against the wrong subject. Then the two sessions each proposed the
opposite half of the fix: A-2 planned to delete its own block and keep A's; A deleted its
own and kept A-2's. Had both acted, step 1 would have shipped with zero tests, green.

**Why.** Python module scope is last-definition-wins, so a duplicated test file is not a
syntax error, it is a silent substitution. The ownership map assumes one writer per lane and
cannot see two instances of the same lane. And a conflict resolved independently by both
parties is not resolved.

**Fix.** The lead read the file on disk before ruling: one block remains, at line 860, the
stronger of the two (the null-versus-absent refusal aimed at the YAML paste, a `BAD_VALUES`
table matching on constraint messages, and a two-halves test that goes red until the sections
are tightened). A-2 was told to delete nothing and port nothing; A was told its deletion
stands and to stand down. Stand-down notices were also written into `PHASE-5-TASKS.md` and at
the top of this log, because the messages sent by name demonstrably did not reach the
originals while the documents demonstrably did.

**Consequence.** Any further double-landing in this phase will look like this rather than
like a merge conflict: green, plausible, and asserting against nothing anyone intended. The
check is `grep -c "^PHASE_5_SECTIONS"` style counting of module-level names, which is the
same count assertion the Phase 4 ORDER BY anchor needed.

### Messages by name did not reach the originals, so they were stopped mechanically

**Agent:** Lead · **Date:** 2026-09-13

**What happened.** Over forty minutes the lead sent stand-down orders to `A`, `B` and `C` by
bare name, by `name [ref]`, and by raw agent id (refused: "to must be a bare teammate name").
Every send reported *"Message sent to X's inbox"*. All three originals then wrote to the lead
saying they had received no stand-down; the original B *did* receive a ruling the lead had
addressed to `B-2`, and B-2 did not. Meanwhile the original C, having said it would not touch
`scripts/verify.py` unresolved, inserted a 270-line Phase 5 section into it, and C-2 deleted
its own identical-purpose section to keep the file coherent. Same shape in lane B (client.py,
test_store.py) and lane A (test_config.py): three lanes, three double-landings, each resolved
by the second writer deleting its own work.

**Why.** Unknown at the transport level, and not investigated further: the observable fact is
that with two sessions sharing a base name, a send by name does not reliably reach the one
intended, and neither session can tell from the inside which one it is. What both sets *did*
reliably read was the tree: every original quoted this log and `PHASE-5-TASKS.md` back.

**Fix.** Three parts. Notices at the top of this log and of `PHASE-5-TASKS.md`, telling any
session to identify itself by how its own sends arrive. Every subsequent ruling sent to both
names of a lane, worded to self-identify the target. And, once the original C wrote into
`verify.py` regardless, `TaskStop` on `A`, `B` and `C`, which reported success for all three.
`ListAgents` afterwards is the check that only `A-2`, `B-2`, `C-2` remain.

**Consequence.** Nothing the originals wrote is discarded: B's escalation and its two
`client.py` edits, A's test-block deletion and seam answer, C's fixture and its `verify.py`
section are all kept and now owned by the `-2` sessions. The cost was about forty minutes and
three duplicated pieces of work. The rule for the lead, added to the one above: **when a
failed agent might come back, stop it before spawning its replacement, and check the roster
before and after.**

### Decision: mypy at 3.12, the floor at 3.11, because the third option stopped being free

**Agent:** Lead, from C-2's escalation · **Task:** spec 61 step 2, spec 63 · **Date:** 2026-09-13

**Options.** C-2 found that a direct `import numpy` under `src/` makes `mypy --strict src/
scripts/` abort: numpy 2.5's stub carries a PEP 695 `type` statement, a syntax error at
`python_version = "3.11"`, and *"errors prevented further checking"* means the gate returns no
answer at all. The `follow_imports = "skip"` override A wrote in Phase 2 only governs modules
mypy reaches by following an import; a module named outright is parsed regardless. A's own
comment listed the three ways out: raise the declared floor to 3.12, pin `numpy<2.3`, or keep
the override and never import numpy by name. C-2 recommended the pin, on the argument that
raising mypy's version stops checking the 3.11 promise, which is the hole that let a 3.11
`SyntaxError` ship in Phase 4.

**Chose.** `python_version = "3.12"` for mypy only. `requires-python` stays 3.11.

**Because.** The premise of the objection was checked rather than accepted. The Phase 4 defect
was caught by **ruff**, not mypy (the red message was ruff's), and ruff with
`target-version = "py311"` was run on a probe carrying both a `type` alias statement and the
f-string backslash: *"Cannot use `type` alias statement on Python 3.11 (syntax was added in
Python 3.12)"* and the f-string error, four findings. So the floor is guarded by a tool that
still guards it. With mypy at 3.12 the gate reaches C-2's code and reports two ordinary
annotation errors in `di.py`, which is what a gate is for. The pin was rejected because a
downgrade in the shared venv lands on three agents mid-work and ties the project to an ageing
numpy line for a stub quirk.

**Cost.** mypy would accept 3.12-only syntax in `src/` if ruff did not exist; a test now pins
the ruff target so the two cannot be raised together by accident. numpy and polars stay `Any`
to mypy until someone asks to drop the skip.

### Correction: the mypy ruling is withdrawn; the fourth option was one line

**Agent:** Lead · **Date:** 2026-09-13

**What happened.** The decision entry above chose `python_version = "3.12"` for mypy. It never
landed: the ruling was addressed to `A-2` and, like every lead send to a `-2` name, was
delivered to the stopped original instead. A-2, working from the tree, found that
`follow_imports = "skip"` silences a module's source and not its stub, and that
`follow_imports_for_stubs = true` on the same override extends the skip to the stub. One
line, no version change, no pin, no venv change; the lead verified `mypy --strict src/
scripts/` at *"Success: no issues found in 106 source files"* with numpy 2.5.3 still installed
and `di.py` still importing it by name.

**Why the first ruling was wrong.** All four agents, the lead included, treated the three-item
list in A's Phase 2 comment (raise the floor, pin numpy, keep the override) as exhaustive, and
argued carefully about which of the three cost least. The list was written to explain a
different decision and nobody asked whether it was complete. The original A said it best:
measurements that answer a question that did not need asking are more expensive than a sloppy
check of the right question, because they produce confidence.

**Fix.** The ruling is superseded in `code-standards.md` and in the rulings log; the 3.12
probe and the ruff-target test are not wanted. The earlier entry stays as written, per
script-rules rule 6.

### Messages to the `-2` sessions do not arrive; the task file is now the channel

**Agent:** Lead · **Date:** 2026-09-13

**What happened.** Three receipt checks were sent to `A-2`, `B-2` and `C-2`. The original A
answered the one addressed to `A-2`, and every earlier pattern fits the same rule: the
original B received rulings addressed to `B-2`, C-2 never saw the two spec 60 rulings, and
each send to a `-2` name resurrected a stopped original. The `-2` sessions' sends to `main`
arrive normally.

**Why.** Not established at the transport level and not investigated further; the working
hypothesis is that both spawns of a lane registered under the same base name and the first
registration owns the mailbox. What matters is the observable rule.

**Fix.** The lead no longer sends to teammate names at all. `feature-specs/PHASE-5-TASKS.md`
carries a dated "Messages from the lead to teammates" section that every agent has
demonstrably re-read, and every answer goes there. The cost is latency: an agent learns the
answer when it next reads the file, which the section tells it to do before every spec step
and every send to `main`.

### A send to `A-2` resurrected the stopped original A; the lead sends nothing by name now

**Agent:** Lead · **Date:** 2026-09-13

**What happened.** After B-2 acknowledged a message addressed to `B-2`, the lead tried one
send to `A-2`. `ListAgents` fifty seconds later showed a fourth teammate, `A`, started fifty
seconds earlier. Stopped again. So the rule is asymmetric and not fully understood: a send to
a `-2` name can reach the live session, or resurrect and reach the stopped original, and
nothing in the send result says which.

**Fix.** No sends from the lead to any teammate name for the rest of the phase. The task
file's dated section is the only lead-to-teammate channel; teammates send to `main` and read
the file. `ListAgents` after any teammate-originated message that names a bare letter.

### A rehearsal of three engines is more than three rehearsals of one

**Agent:** Lead, from B-2's rehearsal · **Date:** 2026-09-13

**What happened.** B-2 rehearsed engine 5 alone, then engines 5, 6, 7 and 12 together,
through the real orchestrator against the fake client. Two findings that only the second
shape could produce. First, "engine 5 returns `PASS` and the chain stops there" had no
observable consequence while engine 5 was the only registered opportunity engine: nothing
downstream existed to not-run, so no test could see it, and deleting the orchestrator's
`PASS` check went red only once three engines sat behind engine 5. Second, a quiet tick and a
crashed tick publish the same empty payload, so the engine 5 `PASS` mutation was first killed
by the wrong test; the fix is to assert the absence of a blocker beside the empty payload,
now a rule in `code-standards.md`.

**Why it matters for the phase.** Registration in spec 77 rests on these rehearsals. The
ones for engines 13, 8 and 15 must be run as a chain with 7, 10 and 11 in their real
positions, not one engine at a time, for the same reason.

### Decision: `missing_bars` keeps its union semantics, and the gate's meaning is written down

**Agent:** Lead, from A-2's measurement · **Date:** 2026-09-13

**Options.** Engine 3 publishes a per-pair map beside the union (C-2's request); `data_guard`
blocks on a per-pair hole; or the union stays and its meaning is stated.

**Chose.** The third, with a no-double seam test.

**Because.** A-2 measured it: with two pairs and one missing bars 2 and 3, the pooled reading
is empty and the per-pair reading is `[2, 3]`; with 234 pairs the union is empty on
essentially every tick, so the missing-candle condition is a feed-silence detector, not a
per-pair one, and has been since Phase 2 without anyone seeing it, because engine 3's gap
tests use one pair and `data_guard`'s tests build `missing_bars` themselves. A per-pair block
would stop the whole tick on the ordinary fact that a thin pair did not trade, which is the
market, not a fault; a per-pair map from engine 3 is a second producer of a fact engine 5
already derives from the candles. What was wrong was not the arithmetic but the absence of a
sentence saying what it measures.

**Cost.** The Phase 2 criterion's proof is narrower than its name; the tracker says so.

### The lead committed through a `tail` pipe and lost two failure names

**Agent:** Lead · **Task:** committing specs 62 and 76 · **Date:** 2026-09-13

**What happened.** The commit command for B-2's lane ran `pytest ... | tail -1 && ruff ... &&
git commit`. The pytest line printed `2 failed, 253 passed, 1 skipped` and the chain went on
to commit anyway, because `&&` tested `tail`'s exit code, not pytest's. The names of the two
failures were never printed. An immediate re-run of the same two directories, redirected to a
file and read from it, reported `255 passed, 1 skipped`, exit 0.

**Why.** Two mistakes, both the lead's and both already rules in `code-standards.md`. The
evidence was destroyed at the pipe: `tail -1` kept the summary line and binned the criterion
names, which is the Phase 4 finding word for word. And the exit code of a pipeline is the last
command's, so the guard that was supposed to stop the commit tested the wrong process.

**What is and is not known.** The committed files pass on a quiet re-run and the tree at
`16c5685` is what B-2 reported green (151 passed in its two files, 8 and 13 mutations
killed). The two failures are **unattributable**: with three agents saving into the tree and
a shared `conftest.py`, a mid-save fixture is the likeliest cause and the intermittent native
fault is the other candidate, and neither can be claimed without the names. Recorded as
unexplained rather than explained away, per the Phase 3 rule.

**Fix.** Every lead gate run from here is redirected to a file under the scratchpad and read
from the file, with the exit code checked from `$?` after the redirect and never from a
pipeline. The commit stands because its content passes; the process that produced it did not.

### Spec 60 reached for a fixture that was the labeller's output, not its input

**Agent:** Lead, from C's finding · **Task:** spec 60 · **Date:** 2026-09-13

**What happened.** Spec 60 told the Phase 5 criteria to train their subject from
`tests/fixtures/labelled_sample.parquet`, and spec 63 defined the feature arithmetic over a
seven-column OHLCVT frame. The fixture carries `pair, decision_ts, close, target_price, ...`:
no open, high, low, volume or trades. It also spans ten days of one pair, and
`backtest.training_window_days` is 90, so a rolling walk-forward over it produces no folds.

**Why.** The fixture was built in Phase 4 for two label criteria, neither of which needs a
bar's range or more than a few days of bars. Spec 60 reached for it a phase later as the
universal training input without reading its columns. It is the seam failure
`code-standards.md` already names from the other side: the producer's tests assert its
behaviour, the consumer builds its own inputs, and the exported fields are tested by nobody.
A close-only reconstruction would not have fixed it, because every range and volume feature
would be a constant and two paths agreeing on a constant agree on nothing.

**Fix.** Spec 60 criteria 1 and 7 and spec 67 step 10 amended: a second committed fixture,
`tests/fixtures/candles_sample.parquet`, the real OHLCVT slice the labelled sample came from,
extended backwards by `market_sensor.published_bars` and keeping its real gaps; and criterion 7
as a committed digest from a real run plus the fold machinery over a constructed series long
enough for several folds, the pattern `walkforward_folds_purged_and_embargoed` set.
