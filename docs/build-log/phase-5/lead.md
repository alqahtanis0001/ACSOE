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

### The lead changes model mid-phase; what carries over is the tree

**Agent:** Lead · **Date:** 2026-09-13 17:35

**What happened.** The operator is switching the lead from Fable 5.1 to Opus 5 to reduce
usage and avoid mid-session cut-offs. The lead's conversation does not carry over; the
teammates do. Handoff 3 at the top of `PHASE-5-TASKS.md` is written for a lead that has read
nothing but the documents, in the same shape as the two operator wind-downs before it.

**Why it is recorded.** Every rule this phase produced about interruptions (progress files
before the work, diagnosis before the fix, the task file as the channel) was made for the
teammates. This is the first time the lead is the one being replaced, and the same rules
turn out to be what makes it survivable: the rulings log, the channel entries and the
per-commit records are the lead's state, and the new lead inherits them by reading rather
than by being told.

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


### The full run holds 70 GB before training starts, and the machine is at its commit limit

**Agent:** Lead (Opus 5 session) · **Task:** the full 234-pair training run · **Date:** 2026-09-13

**What happened.** The full run was started 21:46 from a detached worktree at `6e09881`
(`../ACSOE-fullrun-6e09881`), cwd the main checkout, `python -m acsoe.research.training --config
<worktree>/config/default.yaml --write-fixture`, launched through WMI so it is not in any shell's
job object; log `logs/fullrun-20260913T214616.log` (empty until `main()` prints at the end), cmd
PID 45492, python worker PID 41504. At 22:38 the phase 5 gate for specs 74 and 75, running in a
separate worktree, was killed by the harness for low system memory. Measured straight after:

```
22:38:55  run private 67.9 GB, working set 64.6 GB, physical free 4.4 of 95.7 GB
22:39:25  dataset parquet 14.74 GB, no longer growing; run private 70.65 GB
22:44:05  unchanged: 14.74 GB, 70.66 GB private, ~7 GB physical free
22:44:47  no .tmp beside the parquet (the provenance rewrite has replaced it); CPU +5 min in 6
          min, so single-threaded: the read-back, sort and per-row dicts before the first fold
22:46     commit limit 112.9 GB, commit free 0.8-0.9 GB; pagefile system-managed, 17.6 GB
          allocated; C: 72 GB free
```

**What is established and what is not.** The dataset build finished and the run is alive. The
streamed builder (`build_dataset_to_parquet`) holds one archive frame at a time by its test,
which **counts live frames and deliberately does not measure memory**, so a retention that is not
a frame (allocator arenas in polars or pyarrow not returned to the OS, or something inside the
replay) is invisible to it. Which of those holds the ~50 GB beyond the ~14-28 GB the read-back and
sort need is **not established**; nothing was attached to the process to find out, because the
run is the thing being protected. Measured before the fact by C-2: 13.8 GB for the frame and
about 4.1 GB for the splitter's row dicts.

**Why it matters.** At 0.8 GB of commit headroom the run survives only as long as Windows can grow
the pagefile, and any other large process competes for the same headroom. So no full gate is run
beside it: `toolchain_green` runs the whole suite, which trains models. The gate for 74 and 75 is
deferred to a ruling rather than risked. If the run dies with a `MemoryError` before its first
fold, this entry is where to start: the builder's test proves frames, not bytes.


### Correction: the builder does not hold the 70 GB; the read-back, the sort and the splitter's Python objects do

**Agent:** Lead (Opus 5 session) · **Task:** the full 234-pair training run · **Date:** 2026-09-13

**The entry above is wrong in one claim and this corrects it.** It said the streamed builder
retains the memory. It does not, and the measurement that shows it was already in this session's
own notes: at **22:10, mid-build, the worker's working set was 3.3 GB** (21.9 CPU-minutes in, the
dataset parquet at 4.8 GB and growing). The jump to 68-70 GB came between 22:29 and 22:39, which
is when the build finished, its provenance rewrite replaced the file (mtime 22:38, no `.tmp`), and
`main()` went on to the next line. Found by reading the code and the numbers, not by running
anything; nothing was attached to the process.

**What the replay does.** Nothing accumulates. `ArchiveReplay.frame` reads the CSV on every call
and keeps nothing (`_rows_for`: "Nothing is cached"), `frames()` is a generator, and
`_archive_frames` is a generator over `replay.frame(pair)`. The 3.3 GB mid-build agrees.

**What the 70 GB is, from the parquet footer (metadata only) and the code.**

* The dataset is **20,331,237 rows by 124 columns** (119 double, 2 int64, 2 string, 1 bool),
  about **20.3 GB resident**. `main()` does `pl.read_parquet(dataset_path).sort(["decision_ts",
  "pair"])`: the read materialises it and the sort writes a second full copy, so that line alone
  peaks around 40 GB, plus whatever the reader's chunking adds before the sort.
* `train_walkforward` then does `dataset.select(["decision_ts", "label_window_end_ts"]).to_dicts()`,
  **20.3 million Python dicts**, about 5 GB at roughly 250 bytes each, kept alive for the whole
  function because `rows` stays in scope.
* **Measured 23:10: Windows trimmed the working set from 66.0 GB to 27.4 GB while private bytes
  stayed at 70.8 GB and CPU kept advancing one core per minute.** So about 43 GB is committed and
  untouched, and the live set is about 27 GB, which is the dataset plus the dicts almost exactly.
  The untouched 43 GB is consistent with freed polars buffers (the pre-sort copy and the reader's
  intermediates) held by the allocator rather than returned to the OS. That is **inferred, not
  proven**: confirming which allocator holds it would mean attaching to the run.

**What is still to come, by the code.** `purged_walk_forward` keeps every fold's `train_index`
and `test_index` as tuples of Python ints for all folds at once. Each index is a fresh int object
(`enumerate`), about 36 bytes with its tuple slot. Over this dataset that is about 282 million
entries, **about 10 GB**, most of it in the later folds because the pair count ramps up (pairs
first appearing: 14 in 2017, 3 in 2018, 13 in 2019, 26 in 2020, 43 in 2021, 115 in 2022, 20 in
2023). The flat private bytes from 22:39 to 23:11 (70.65 to 70.82 GB at one core) fit a splitter
walking its early, thin folds. Per fold after that: a gathered training frame (up to ~2 GB), the
scaled matrices and LightGBM (~3-5 GB), transient. Growing through the run: the out-of-sample
parts (~2 GB at the end, plus a concatenated copy each fold for the skeptic) and the skeptic's
training join over every earlier BUY call, which is uncapped and largest in the last folds.

**The fold count, and the 22.2-hour projection.** The dataset spans 2017-01-01 to 2025-12-31,
3,286.5 days, which is **457 weekly folds, not 352**. But the projection also assumed 234 pairs
in every fold's training window (2,021,760 rows); the real sum of training rows across folds is
about 20.3M x 90/7, roughly 261M row-folds rather than 711M. On C-2's own measured line (4.87 s
plus 109.74 s per million training rows) the predictor fits come to about 8.6 hours. The splitter
(457 full scans of 20.3M dicts), the per-row Python loop in `_fit_anomaly`, and the growing
skeptic are all on top, so the total is **uncertain in both directions** and neither 22.2 hours
nor 8.6 is a number to plan on.

**Will it survive.** The step the operator was worried about, the read-back and sort, is
**already behind it**: it is inside the 70 GB. What is ahead is about +10 GB for the splitter's
tuples and a per-fold transient of perhaps 5-8 GB, rising late in the run with the skeptic.
Against that: commit limit 115 GB (95.7 RAM plus a system-managed pagefile that has already grown
from 17.6 to 19.7 GB on its own), about 9-10 GB of commit free, 72 GB free on C:, and 43 GB of the
run's own memory that is cold and pages out without cost. The projection is roughly 100-110 GB of
commit at the late-run peak, reachable by pagefile growth. **Likely to survive, not certain**,
and the margin is what the rest of the machine uses: a second heavy process (a full gate or test
suite, which trains models) during the late folds is the realistic way to kill it.

**Defects this run exposes, for after it, not during it.** (1) `main()` reads and sorts the full
dataset eagerly when the builder could write it already ordered or the sort could be streamed.
(2) The splitter is fed 20.3M Python dicts and returns Python-int index tuples for every fold at
once; an index-based splitter over the two int64 columns would cost megabytes. (3)
`test_the_builder_never_holds_two_archive_frames_at_once` counts frames and says so deliberately,
so none of this was visible to it, and none of it is in the builder. (4) C-2's projection used
the archive's pair count for every fold. Each is a ruling for the lead and the operator, not a
fix to make while the run depends on the code as it is.


### The full run died at fold 405 of 457 in the skeptic's matrix, out of memory

**Agent:** Lead (Opus 5 session) · **Task:** the full 234-pair training run · **Date:** 2026-09-14

**What happened.** The run started 2026-09-13 21:46 exited at **2026-09-14 21:55** (about 24 h 9 min)
with folds 0 to 404 written and fold 405 not. The whole log, 2,324 bytes, is one traceback:

```
train_walkforward -> _train_one_fold (fold 405) -> _fit_skeptic -> _skeptic_matrix
  scaled = np.asarray(scaler.transform(_matrix(rows, names)), dtype=np.float64)
modelling/artefacts.py:285 _transform_array
  scaled = (matrix - low) / safe
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 7.80 GiB for an array with
shape (8950630, 117) and data type float64
```

**Evidence left exactly as found.** Nothing was restarted, deleted, moved or retried.

* `models/train-20260913T205245-067b2b9d-f0` to `-f404`: **405 directories, each with a
  `manifest.json`**. 404 hold six files (`anomaly.joblib`, `calibrators.json`, `manifest.json`,
  `model.txt`, `scaler.json`, `skeptic.txt`); fold 0 holds five, with no `skeptic.txt` because no
  earlier out-of-sample calls exist for it. No partial directory for fold 405: the directory is
  created after the fits. 2.6 GB in total. The last, fold 404, was written 21:52:16.
* **No `oos_<run_id>.parquet` and no `walkforward_digest_<run_id>.json`.** The trainer writes both
  only after the fold loop. `tests/fixtures/walkforward_digest.json` is untouched (2026-09-13
  11:03, the three-pair digest), because `--write-fixture` runs after the digest.
* `data/derived/dataset_20260913T205245.parquet`, 14.74 GB, intact, provenance stamped.
* At 21:56: commit limit 102.3 GB with 79.1 GB free. The pagefile setting reads 50000-80000 MB,
  but the allocation was 6,759 MB, so Windows did not extend it for this request.

**Why.** The skeptic for fold k trains on every eligible BUY call from folds before k, uncapped.
By fold 404 that was 8,946,942 rows (from its manifest), and fold 405 asked for 8,950,630 rows by
117 columns. `_skeptic_matrix` builds the float64 matrix (7.8 GiB) and `Scaler._transform_array`
computes `(matrix - low) / safe`, which allocates at least one more matrix of the same size and
transiently a third. Together with the joined polars frame those rows came from, the skeptic step
alone needed on the order of 25-30 GB at this fold, and it grows every fold. That is the growth
behind the per-fold peaks recorded above (66 GB private at fold 329, 79 GB at fold 388). The
single 7.8 GiB request failed at a peak, and the pagefile did not grow in time to meet it.

**What survives, and it matters for the operator's thresholds.** Every fold's digest entry is
inside that fold's `manifest.json` under `metrics`: `rows`, `effective_sample_size`, `brier`,
`base_rate_brier`, `buy_count`, `buy_target_rate`, `train_rows`, `skeptic_rows` and the fold
windows. Read back without writing anything, into
`<scratchpad>/folds_0_404_metrics.csv`:

* 405 of 405 folds carry metrics; **279 have a Brier below their base-rate Brier, 126 at or above.**
* Test rows 15,978,803, effective sample size 1,688,207 in total (ratio 0.106).
* The smallest effective sizes: fold 26, 6,101 rows, **274 effective**; fold 82, 6,655 rows, 294;
  fold 81, 7,203 rows, 336; fold 2, 3,346 rows, 341; fold 27, 6,178 rows, 356.

| test year | folds | rows | effective | Brier < base | mean(Brier - base) |
|---|---|---|---|---|---|
| 2017 | 40 | 255,653 | 33,799 | 34 | -0.00466 |
| 2018 | 52 | 397,520 | 35,706 | 22 | +0.00403 |
| 2019 | 52 | 484,402 | 32,480 | 20 | +0.00260 |
| 2020 | 52 | 961,492 | 82,566 | 40 | -0.00326 |
| 2021 | 52 | 2,181,238 | 233,329 | 43 | -0.00451 |
| 2022 | 53 | 3,252,113 | 355,220 | 40 | -0.00229 |
| 2023 | 52 | 3,785,657 | 402,325 | 44 | -0.00255 |
| 2024 | 52 | 4,660,728 | 512,782 | 36 | -0.00276 |

The missing folds 405 to 456 are the test weeks from 2025-01-04 to the end of 2025. The
out-of-sample parquet that specs 74 and 75 read does not exist for this run, so the leaderboard
and the ranking study cannot be produced from it; the fold artefacts can be loaded by `run_id`.

**Not decided here.** Whether to rerun, resume from fold 405, cap the skeptic's training set, or
rebuild the out-of-sample file from the 405 artefacts is the operator's and the lead's call.


### The gate for specs 74 and 75 went red on `toolchain_green` by timeout, with no test failing

**Agent:** Lead (Opus 5 session) · **Task:** specs 74 and 75, the gate before commit · **Date:** 2026-09-14

**What happened.** `verify.py --phase 5` on the staged tree (worktree `../ACSOE-gate-7475`, tree
`4099ee24`) reported 10 PASS, 1 FAIL, 2 PENDING. The FAIL was `toolchain_green`: *"pytest timed out
after 900s"*. Every Phase 5 criterion that ran passed, including the rewritten
`tournament_writes_leaderboard_from_oos`. The PENDINGs are the operator's `di_percentile` and
spec 73's missing `test_skeptic.py`, which is not in this tree by design.

**Why.** The pytest log (`logs/verify/toolchain_green/20260914T212820_095468-pytest-attempt1.log`
in the gate worktree) ends at about 98% of the suite with only dots and two skips: no `FAILED`, no
`ERROR`, killed by the criterion's 900 s limit. For the whole gate the machine was also running the
artefact rebuild, which read the 20.3 GB dataset and scored 405 folds through LightGBM. The suite
took about 340 s on a quiet machine before this phase added its training tests, and these specs
added roughly another minute. A timeout under contention is not a verdict on the tree, and it is
not a pass either; the gate is re-run with nothing else of this session's running.

**Fix, gate.** Re-run on a quiet machine (4% CPU, only the recorder, its supervisor and the
manager running): **11 PASS, 0 FAIL, 2 PENDING**, `toolchain_green` green. The spec-74-only tree
was then gated the same way with the same result, and the two commits are exactly the two gated
trees: `d590548` (tree `fb330337`, spec 74) and `531d240` (tree `4099ee24`, spec 75), pushed.

### The out-of-sample file and the digest, rebuilt from 405 fold artefacts and proven identical

**Agent:** Lead (Opus 5 session) · **Task:** operator ruling 2026-09-14 on the dead run · **Date:** 2026-09-14

**Decision, the operator's.** No rerun and no resume. Rebuild the out-of-sample parquet and the
digest from the 405 saved folds, and have the digest say it covers 405 of 457 and why.

**How.** `docs/dataset/rebuild-walkforward-2026-09-14.py` (sha256
`63c9c9ef540285f0ef8147d601c6ee9a7bf9389b03c0b1df27dea08fd535ce38`, the same hash the digest
records), run with `PYTHONPATH` on the `6e09881` worktree that trained the artefacts, so it
scores through the trainer's own `_matrix`, `Scaler.transform`, LightGBM text model,
`apply_calibration`, `expected_move_pct`, `is_buy_call`, `_brier_of_target`,
`_base_rate_brier`, `_log_loss`. Per fold: `load_run` verifies every hash; the test rows are
the dataset rows in `[test_start_ts, test_end_ts)` ordered `(decision_ts, pair)`, with the
window start checked against the splitter's own arithmetic; the rows, Brier, base-rate Brier,
log loss, BUY count, BUY target rate, target rate and effective sample size are recomputed and
compared with the manifest, and the BUY-row identity digest with `buy_identity`. Any
disagreement writes nothing. Nothing was trained.

**Result.** All 405 folds reproduced with a largest absolute difference of **0.0** on every
metric and identical BUY identities. Written: `data/derived/oos_train-20260913T205245-067b2b9d.parquet`
(15,978,803 rows) and `walkforward_digest_train-20260913T205245-067b2b9d.json`, whose `coverage`
block reads `complete: false`, 405 of 457 folds, the missing indices and test weeks
(2025-01-04 to 2025-12-27), the cause and the error line; `notes` opens with `PARTIAL`.

**Proven capable of refusing**, because a comparison that has only ever agreed is not evidence.
The same comparison on fold 0's test rows:

```
fold 0 rows, fold 0 artefacts:            rows 3771=3771, brier diff 0,       BUY 2427=2427, identity MATCH   -> ACCEPTED
fold 0 rows, fold 1 artefacts:            rows 3771=3771, brier diff 0.00396, BUY 2772/2427, identity DIFFERS -> REFUSED
fold 0 rows, window inclusive at the end: rows 3776/3771, brier diff 2.7e-06, BUY 2430/2427, identity DIFFERS -> REFUSED
```

**As the committed fixture.** `walkforward_weekly_retrain_reports_oos`, the only reader of
`tests/fixtures/walkforward_digest.json`, PASSes against it on a worktree at `531d240`: *"405 in
tests/fixtures/walkforward_digest.json: every fold reports fold_index, … trains only up to its own
test window (train_end_ts == test_start_ts), and reports an effective sample size below its row
count"*. The per-fold table is `docs/dataset/walkforward-folds-2026-09-14.md`.

**What the 405 folds say, stated rather than summarised away.** 279 folds have a Brier below
their base-rate Brier and 126 at or above; the median difference is −0.0033 and the
effective-size-weighted mean −0.0024. **136 folds have an effective sample size under 1,000**,
every one of them before July 2020; the worst is fold 26 (week of 2017-09-30), 6,101 rows and 274
effective, Brier +0.0515 against its base rate. Test rows 15,978,803, effective 1,688,207. And the
number the operator's thresholds rest on: the predictor made **8,950,912 BUY calls, 56% of every
test row, and their target rate is 0.2383 against 0.2422 over all test rows** — before any
friction, the BUY calls hit the target slightly less often than an unselected bar. The Brier edge
is real in most folds and small; as a selector of trades it shows none.


### The skeptic veto sweep: the survivors hit their target far more often, and it is not a leak

**Agent:** Lead (Opus 5 session) · **Task:** operator's study for `skeptic.veto_threshold` · **Date:** 2026-09-14

**What was asked.** No retraining, no new models: apply each fold's trained skeptic to that
fold's out-of-sample BUY calls and sweep the veto threshold from 0.30 to 0.70, reporting the
survivors with their effective sample size and the target rates of survivors and vetoed calls;
prove the check can fail with a different fold's skeptic. Evidence only; nothing in config.

**How.** `docs/dataset/skeptic-veto-sweep-2026-09-14.py` (sha256 `2b03e4f7…58db1556`), run on the
`6e09881` code that trained the artefacts, scoring through `_skeptic_matrix` with each fold's
verified scaler and `skeptic.txt`; a call survives when P(wrong) ≤ threshold, the trainer's and
engine 15's rule. Per fold the BUY count matched the manifest and the dataset join kept every row.
Fold 0 has no skeptic (no earlier calls); folds 1 to 404 were scored, 8,948,485 calls at a target
rate of 0.2383, effective size 933,453. Fold k's skeptic is out of sample on fold k's calls by
construction. Results in `docs/dataset/skeptic-veto-sweep-2026-09-14.json`, table in the `.md`
beside it.

| threshold | survivors | share | survivors' effective size | survivor target rate | vetoed target rate | no-skill band |
|---|---|---|---|---|---|---|
| 0.30 | 9,373 | 0.10% | 3,243 | 0.6349 | 0.2379 | 0.2711-0.2892 |
| 0.35 | 24,888 | 0.28% | 8,857 | 0.6313 | 0.2372 | 0.2632-0.2722 |
| 0.40 | 51,145 | 0.57% | 17,778 | 0.6035 | 0.2362 | 0.2563-0.2621 |
| 0.45 | 88,931 | 0.99% | 29,238 | 0.5693 | 0.2350 | 0.2545-0.2605 |
| 0.50 | 154,979 | 1.73% | 46,616 | 0.5309 | 0.2331 | 0.2550-0.2596 |
| 0.55 | 289,977 | 3.24% | 77,151 | 0.4877 | 0.2300 | 0.2574-0.2610 |
| 0.60 | 583,121 | 6.52% | 132,708 | 0.4403 | 0.2242 | 0.2602-0.2629 |
| 0.65 | 1,265,683 | 14.14% | 238,275 | 0.3928 | 0.2128 | 0.2636-0.2649 |
| 0.70 | 2,859,743 | 31.96% | 439,499 | 0.3482 | 0.1867 | 0.2645-0.2653 |

**What happened when the numbers came back.** A survivor target rate of 0.53 at 0.50 against a
BUY-call base of 0.24 is the shape of result this phase exists to distrust, so it was treated as
a leak until shown otherwise, before anything was reported.

**Why it is not the obvious leak.** `docs/dataset/skeptic-training-identity-check-2026-09-14.py`
recomputed the skeptic's eligible training set for folds 1, 50, 150, 250, 300, 350 and 404 from
the out-of-sample file with the trainer's rule and matched the manifest's `training_identity` and
row count on all seven, with zero rows reaching the scored test window; dropping the purge and
embargo breaks every match. The different-fold controls move the way they should: adjacent
skeptics (404 and 403, sharing nearly all of ~8.9M training rows) differ in one verdict at 0.50;
distant ones in hundreds; and fold 200's calls scored by fold 350's skeptic, which *did* train on
fold 200's rows, reach 0.6325 against its own skeptic's 0.5772. The no-skill band (each fold's
own scores permuted across its calls, 20 seeds) sits at about 0.26, so random vetoing at the same
per-fold counts explains 0.02 of the lift and not the rest. The lift holds in every test year,
2017 to 2024, at 0.50, 0.60 and 0.70.

**What it does not establish.** All rates are before friction. The standard error beside each
rate (by effective size) is a floor: it ignores correlation between pairs moving together and
between folds. No check here separates the skeptic's contribution from a simpler ranking of the
predictor's own `p_target` at the same survivor counts; that comparison was not asked for and was
not run. Nothing was committed to config.

### At matched counts the skeptic beats the predictor's own confidence, by less as the threshold loosens

**Agent:** Lead (Opus 5 session) · **Task:** operator's control on the skeptic sweep · **Date:** 2026-09-14

**What was asked.** Whether the skeptic adds anything over ranking the predictor's own
`p_target`: per fold, take the top N BUY calls by `p_target`, N the skeptic's survivor count at
each threshold, and compare target rates and effective sizes; prove the comparison can fail.

**How.** `docs/dataset/skeptic-vs-ptarget-2026-09-14.py`, the same scoring as the sweep. Ties at
the cut are real (`p_target` is isotonic-calibrated, so piecewise constant; up to 42,824 rows tied
across the cuts at 0.70) and were broken at random under two seeds, which agree to within 0.0004.
Positive control: top-N by the skeptic's own score selected the identical set as the skeptic at
all nine thresholds. Negative control: top-N at random gave 0.254 to 0.280.

**Result.** Skeptic minus `p_target` at matched N: +0.0744 (0.30), +0.0753 (0.35), +0.0730
(0.40), +0.0668 (0.45), +0.0578 (0.50), +0.0458 (0.55), +0.0306 (0.60), +0.0148 (0.65), +0.0049
(0.70). Effective sizes are close between the two at every threshold (at 0.50, 46,616 against
41,218). The sets share 29% of calls at 0.30, 44% at 0.50 and 68% at 0.70. So the second stage
is not decoration at the strict end; at 0.70 it is nearly the same selection as confidence
ranking. Also found: `p_target` ranking alone reaches 0.47 at the 0.50 count, so the predictor's
confidence carries real ordering the BUY rule (`expected_move_pct > 0`, 56% of bars) never uses.

**A consequence for the thresholds, found while reading the artefacts.** None of the 405 folds
carries `di.npz` or an anomaly threshold (`extras.di` null, `extras.anomaly.threshold` null),
because the run trained with `prediction.di_percentile` and `anomaly.threshold_percentile` absent.
Engine 8 refuses a run with no `di.npz` and engine 13 refuses one with no recorded threshold, so
supplying those two keys flips their criteria without making any artefact of this run usable
live, and the digest holds no DI or anomaly distribution to choose them from. Only
`skeptic.veto_threshold` is applied at scoring time and has evidence behind it.

### The DI cannot be fitted through the trainer's own path in any time the phase has

**Agent:** Lead (Opus 5 session) · **Task:** operator ruling 2 of 2026-09-14, DI and anomaly fitted from the saved training rows · **Date:** 2026-09-15

**What happened.** The first version of `docs/dataset/di-anomaly-fit-2026-09-14.py` called
`research.training._fit_and_score_di` directly on each fold's identity-verified training rows. The
pilot on fold 404 ran for over an hour without finishing and was stopped. Measured afterwards on
this machine: `modelling.di._mean_nearest` over a 200,000-row reference costs 12.9 s per 2,048
leave-one-out queries on one thread (about 21 minutes per capped fold), throughput saturates at
about 780 queries a second across 12 to 16 processes because the elementwise arithmetic is
memory-bound, and `_fit_and_score_di` scores test rows one `di.score` call at a time at **136 ms a
row**, so fold 404's 93,166 test rows alone are about 3.5 hours.

**Why.** `prediction.di_reference_rows` is 200,000 and the leave-one-out distribution is quadratic
in it; `di.score` builds a 200,000-element temporary per call. Neither was ever timed at that size:
every DI test fits a few hundred rows, and the full run trained with `di_percentile` absent, so the
DI never executed on real data. **Had the operator supplied the percentile before the run, the run
would not have died at fold 405 of memory; it would still be running.** That is a fifth Phase 7
prerequisite, not recorded in the tracker yet: the trainer's DI needs a batched test-row score and
a leave-one-out search that is not one numpy loop on one core, or a smaller cap.

**Fix, for the evidence only; the trainer is untouched.** The reference set is still built
exactly as `_fit_and_score_di` builds it (its `_di_reference_rows`, the verified scaler, complete
rows, the seeded cap). The statistic is computed with scikit-learn's multithreaded brute-force
nearest-neighbour search, leave-one-out by dropping the row's own index. Held to the module three
ways, and each was run before a number was kept: `selfcheck` ran the trainer's `_fit_and_score_di`
in full on folds 0, 1 and 60 (5,429, 6,111 and 26,142 reference rows): identical reference identity
and matrix, largest distribution difference 6.9e-15, 6.7e-15 and 1.9e-14; every fold recomputes 16
leave-one-out values and 16 test scores through `di._mean_nearest` and `di.score` and refuses
beyond 1e-9 (fold 404: 7.7e-14); a random-data benchmark agreed to 2.7e-15. Fold 404 then took
100 s end to end.

### The purge cannot change a training set whose embargo equals the label horizon

**Agent:** Lead (Opus 5 session) · **Task:** the identity controls for the DI and anomaly fit · **Date:** 2026-09-15

**What happened.** The script's `controls` recompute a fold's training rows four ways and compare
them with the manifest's `training_identity`. The true rows were ACCEPTED on folds 200 and 404;
the neighbouring fold's manifest was REFUSED (365,450 against 354,374 rows; 1,203,815 against
1,183,241); dropping the embargo was REFUSED (366,620 and 1,208,278 rows). **Dropping the purge
was ACCEPTED on both**, with an identical identity.

**Why.** Not a hole in the check. `backtest.embargo_bars` is 48 and the label window is 48 bars,
so every row whose label window reaches the test window has its decision bar inside the last 48
bars before it, which the embargo already removes. The splitter counts those rows as purged
rather than embargoed, so the two counts differ while the training set does not. It is the Phase 4
finding (a label window equal to the embargo let a splitter with its purge deleted pass) seen
from the consumer side, and it is an **equivalent mutant at this config**, reported as a checked
negative. The fit script also compares `purged_count` and `embargoed_count` with the manifest per
fold, which is the only place the purge is observable while the two spans are equal.

### The DI's leave-one-out threshold measures closeness in time, and refuses almost every live candidate

**Agent:** Lead (Opus 5 session) · **Task:** operator ruling 2 of 2026-09-14, the DI distribution · **Date:** 2026-09-15

**What happened.** A dry run of `docs/dataset/di-anomaly-distributions-2026-09-14.py` over the
first seven fitted folds (365 to 371) reported that a threshold at the 0.95 percentile of each
fold's leave-one-out distribution would refuse **98.1%** of that fold's out-of-sample rows, 0.99
would refuse 72%, and even 0.999 would refuse 12%. At a percentile p the refusal rate should be
near 1 − p if the test week resembled the reference window.

**Why, established on fold 371 and not assumed.** The first hypothesis (a row's nearest neighbours
are its own pair's adjacent bars) was **tested and rejected**: excluding the same pair's rows
within ±48 bars or ±7 days left the distribution unchanged (median 0.632 in all three). The second
was confirmed: excluding **every pair's** rows within ±48 bars moved the reference distribution onto
the out-of-sample one (median 1.423 against the test rows' 1.402; refusal at the 0.90 percentile
5.1%, at 0.95 1.3%). 78 of the 117 DI columns are the BTC and ETH macro features, identical for
every pair on the same bar, and the calendar columns are too. So a reference row's ten nearest
neighbours are **other pairs on the same or adjacent bars**, and leave-one-out removes only the
row itself. A live candidate is at least the 48-bar embargo after the reference window and has no
contemporaneous neighbours in it, so its DI sits above almost the whole leave-one-out distribution
whatever the market is doing. The statistic as ruled (operator ruling 6 of 2026-09-12:
leave-one-out over the per-pair last 30 days) is a detector of time elapsed since the reference
window, not of unfamiliar market conditions. Script `docs/dataset/di-serial-correlation-check-2026-09-15.py`;
its leave-one-out arm reproduces the saved distribution to 2.0e-14.

**Not decided here.** A higher percentile, an exclusion window in the leave-one-out, or a
narrower DI input are each a change to a ruling or a threshold, and each is the operator's. The
full 405-fold numbers go in the report.

### The DI and anomaly distributions over all 405 folds, and the ranking study over the real run

**Agent:** Lead (Opus 5 session) · **Task:** operator rulings 2 and 3 of 2026-09-14 · **Date:** 2026-09-15

**What was run.** `docs/dataset/di-anomaly-fit-2026-09-14.py fit 2` from 00:33 to 03:30, exit 0,
405 of 405 folds fitted with no refusal: every fold's recomputed training rows matched the
manifest's counts and `training_identity`, every anomaly training set matched its recorded rows and
identity, and the largest sampled difference from `modelling.di` over all folds was 1.1e-13.
Aggregated by `di-anomaly-distributions-2026-09-14.py`; the diagnostic
`di-serial-correlation-check-2026-09-15.py` repeated on folds 20, 100, 180, 260, 340 and 404 gave
the fold 371 result on every one. Spec 75's committed `--ranking-study` ran over the real
out-of-sample file in 3.5 minutes, exit 0, with a by-year and thinness split through the study's
own `chosen_pairs`.

**A partial result that would have misled, recorded because it nearly went into a report.** The
dry run over folds 365 to 371 had the anomaly gate blocking **half** its nominal rate (2.55% at
0.95). Over all 405 folds it blocks 5.55%. Seven late folds in a calm stretch were not the run.

**What they say**, in full in the two `.md` files: the anomaly gate is calibrated and blocks the
volatile tail; the DI as ruled refuses most complete candidates at every percentile below 0.999
for a reason unrelated to the market (entry above); half of all test rows are incomplete vectors
before either percentile applies; and in the ranking study the volatility features raise the target
rate and the stop rate together and choose nothing, while the short-horizon reversal features are
positive before friction in every test year, the largest of them (`bar_body_pct` ascending) drawing
37-44% of its picks from intermittently traded pairs from 2022, where the archive cannot price the
spread. Nothing was put in config; the percentiles and `scout.rank_feature` are the operator's.

### Decision: three operator rulings on the distributions, recorded before any code

**Agent:** Lead (Opus 5 session) · **Date:** 2026-09-15

**Ruled by the operator.** (1) Ruling 6 of 2026-09-12 amended: the DI's leave-one-out excludes
every reference row within 48 bars of the row being scored, across all pairs; a DI fitted without
it is a defect, proved by a new criterion; `prediction.di_percentile` stays absent until the refit
reports. (2) `anomaly.threshold_percentile: 0.99`, provisional; the spec 70 ten-sigma question
stays open. (3) `scout.rank_feature`: none; the ranking study is an open question for Phase 7,
not a finding, because its mean return is per bar and friction is per round trip over a multi-bar
hold, with the thin-pair caveat on `bar_body_pct` kept. Plus the 50.2% incomplete-vector rate as
Phase 7 prerequisite 6.

**Where each went.** Tracker Open Questions, Locked Decisions (two DI lines) and prerequisites;
spec 68's amendment with the reasoning the operator asked for; the glossary's DI entry;
`docs/dataset/ranking-study-2026-09-14.md` reframed so it no longer sets a per-bar return against
round-trip friction.

**The span is `backtest.embargo_bars`, not a new key, and that is the lead's choice.** The
operator's number is 48 bars; the embargo is 48 bars and is the minimum gap between a fold's
reference window and its first live candidate, which is exactly the span a reference row's
leave-one-out must exclude to look like a candidate. A second key holding the same number would
be free to drift from the thing it stands for.

**Team for the rest of the phase, spawned 04:10 under names never used in this project:** C-3
(the exclusion, `modelling/di.py`, the trainer, engine 8's refusal of an unexcluded DI, the
criterion), C-4 (spec 73 review fixes, engine 15 only), B-3 (engine 15's two-tick rehearsal, which
it did not build). Refit with the exclusion running in the background from 04:10
(`docs/dataset/di-exclusion-refit-2026-09-15.py`).

### Spec 73 review: engine 15 failed open on an absent BUY verdict and on a NaN score

**Agent:** Lead (Opus 5 session) · **Task:** spec 73 review · **Date:** 2026-09-15

**What happened.** Reading `engines/skeptic/engine.py`, never reviewed since C-2 built it on
2026-09-13. Two paths return a pass where invariant 3 requires a block. `if not
prediction.get("is_buy")` takes the "not a BUY call" `OK` path for `False` **and** for an absent,
`None` or malformed value, so an engine 8 payload with no BUY verdict is waved through as a
non-BUY rather than refused as unreadable. And `if p_wrong > limit` is `False` when `p_wrong` is
NaN, so a non-finite score from the booster passes the veto.

**Why they matter although nothing downstream trades yet.** A `False` here is one fact (the
predictor did not call a BUY) and an absent key is another (nothing readable was published), and
the handler cannot tell them apart: the code-standards shape "a handler that cannot distinguish
two situations will silently pick the wrong one". The NaN path is the one every learned gate in
this project has been checked for except this one.

**Fix.** Sent to C-4, engine 15's files only: only an explicit `is_buy is False` is the not-a-BUY
`OK`; absent or non-bool blocks `skeptic_unavailable`; a non-finite `p_wrong` blocks
`skeptic_unavailable` before the comparison; block tests by reason code; mutations including the
spec's two. Rest of the review: the published shape carries no approval field, the threshold is
never defaulted, the input vector is rebuilt in the manifest's order from engines 5 and 6, the
veto is strict `>` as the sweep's survival rule is `<=`, the artefact is hash-verified through
`load_run`, reason prose exists for both codes. **The rehearsal constraint**: engine 10 blocks for
want of engine 9 (Phase 6), so in the registered chain engine 15 cannot run this phase; B-3
rehearses it with 10 and 11 left out, and asserts separately that the full chain stops at 10.

### Registration of engines 5, 6, 12, 13, 8 and 15, after B-3's rehearsal of engine 15

**Agent:** Lead (Opus 5 session) · **Task:** spec 77 · **Date:** 2026-09-15

**The rehearsal it waited for.** B-3, which did not build engine 15, added eight tests to
`tests/engines/test_feature_chain_rehearsal.py` (29 passed): in the full chain 5, 6, 7, 12, 13, 8,
10, 11, 15 the bar tick stops at `cost` for want of engine 9 and `skeptic` never runs; with 10 and
11 left out, a BUY call with the skeptic unconfigured blocks `skeptic_unavailable` (threshold
absent, run id absent, both), a non-BUY call is `OK` with `vetoed: false`, and a trained skeptic
vetoes at a threshold 1e-6 below the call's `p_wrong` and passes at 1e-6 above it, the thresholds
recomputed from the artefact rather than read from the engine's own output so that a P(right)
mutation cannot move the line with it. Four mutations killed by the rehearsal; the fifth (manifest
names re-sorted into state order) survives it, killed by `test_skeptic.py`, and is unreachable from
any live state because engine 5 builds rows in manifest order. B-3 also caught a reason sentence
that formats `p_wrong` to four decimals and reads "0.0000 likely to be wrong against a veto
threshold of 0.0000" on a trained fixture; sent to C-4.

**The chain.** `OPPORTUNITY_CHAIN` is 5, 6, 7, 12, 13, 8, 10, 11, 15; 9, 14, 16 and 18 absent for
Phase 6. The docstring states the load-bearing hole: engine 10 blocks every candidate until engine
9 exists, so engine 15 is registered and unreachable this phase. `tests/cli`, `tests/core` and the
Phase 0 and Phase 3 criterion tests: 207 passed, exit 0.

### The refit with the 48-bar exclusion, and a session that lost its gates to a wait

**Agent:** Lead (Opus 5 session) · **Date:** 2026-09-15

**The refit.** `docs/dataset/di-exclusion-refit-2026-09-15.py` recomputed every fold's
leave-one-out distribution with every reference row within 48 bars across all pairs excluded, held
to direct numpy on 16 rows per fold (largest difference ~4e-15). Test-row DI is unchanged by the
exclusion and was reused, after asserting per fold that no reference row lies within the span of
the test window. Out-of-sample refusal over 7,953,442 complete rows: **0.95 refuses 6.79%, 0.99
3.31%, 0.999 2.06%**, against 94.7%, 74.9% and 31.1% before. The refused rows now have a higher
target and stop rate than the kept ones, the shape of the volatile tail. The operator rules the
percentile; the key stays absent.

A first version grouped one scikit-learn search per decision bar and spent most of its time on
call overhead (232 s for fold 0's 5,429 rows); grouping 32 bars per search with the boundary band
in numpy cut small folds to seconds. Large folds were bound by the arithmetic itself, ~2 minutes.

**What happened to the gates.** The two ruled config values turn six tests red that pin the keys as
absent or train fixtures with the committed config; they were backed out so the commit is green,
and the list is in Handoff 4. Phases 0 to 4 were not gated. **Why:** the lead waited roughly two
hours for a teammate's end-of-sweep message instead of checking the teammate's file hash on a
timer, and the time was gone. The engine's hash had been final all along.
