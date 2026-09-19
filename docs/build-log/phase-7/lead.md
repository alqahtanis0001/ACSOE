# Phase 7 — lead

### Findings document before specs, and three claims corrected while writing it

**What happened.** The operator asked for `docs/dataset/phase-7-findings.md` before the specs: every
measured figure about the system's economics, with the simulation's slots marked, and nothing newly
measured. Three claims in the request, two of them first made by the lead, did not survive being
checked against their sources.

1. **"1 trade against 15 before friction"** (uncapped against capped skeptic). The run behind it
   (`q_funnel.out`, alphabetical, total friction 0.60%) charged tier-3 reference fees at zero
   spread. It is *after fees, before spread*. Corrected in the document.
2. **"The model's most confident calls are its most overconfident."** Nothing measured
   overconfidence by confidence level. The measured statement is narrower: over the full span, the
   calls that clear the 1.50% bar realised +0.32%. In the 1.5-year window the same selection
   realised +1.25%. The comparative claim is marked NOT MEASURED.
3. **"The simpler assumption inverted the sign."** True of the point estimate in seven of the eight
   matched cells that traded; the eighth (fees 0.50%, 6 months) went +0.43% to +0.06%. The two arms
   also differ in slippage, not only spread. The document states both.

Also found: **the funnel over the full 405-fold span was never computed past the cost stage**, so
that slot is NOT MEASURED. And **the tier-4 and tier-5 fee marks (0.55%, 0.45%) are the operator's
figures with no source on disk**; the document labels them so until the schedule fixture lands.

**Why it matters.** The chapter will be written from this document today. A claim that outruns its
source is the shape this project has caught in criteria for six phases, and a dissertation
paragraph is harder to recall than a criterion.

**Fix.** The document cites the file behind every figure. The reconnaissance scripts and their raw
outputs are committed beside it (`docs/dataset/phase-7-recon-2026-09-19/`), with terminal-only
outputs transcribed verbatim rather than re-run.

### Decision: the specs carry eight open rulings rather than defaults

**Decision.** Specs 126–143 were written with R1–R4 and R7–R10 marked RULING REQUIRED, each with the
lead's recommendation, instead of writing the recommendation in as if ruled.

*Rejected:* writing each recommendation in as the default, and letting the operator overturn it.

*Why:* R1 (the ranking) and R2 (the skeptic variant) change what the simulation measures by a factor
of four to fifteen in trade count (`phase-7-findings.md` §4, §5a). R8 to R10 define what the
evaluation's headline numbers mean. None of these is an engineering default.

*Objection:* the specs cannot all be claimed on approval. Specs 136, 138 and 139 stay held until
their rulings land, and B has one task. This is a plan with visible gaps rather than a complete one.

### The $60 figure: the operator's arithmetic holds as an upper bound, and tier 2 lowers it

**Agent:** Lead · **Date:** 2026-09-19

**What happened.** The lead and the operator disagreed about what the $60 figure for reaching tier 3
measures. The operator's arithmetic: a $1,000 balance bought and sold back generates $2,000 of
volume per round trip. At 1.20% round trip that costs about $12 in fees, so five round trips reach
$10,000 of volume for about $60 in fees. **The $60 is the fee cost of reaching tier 3, not the
volume.** That is right, and the figure had gone missing from the findings.

**Why it is an upper bound.** The arithmetic charges every trade at tier 1. The committed schedule
(`tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`) has a tier 2 from $2,500 of 30-day
volume, at 0.30%/0.60%. If the account is re-tiered as the volume accrues, the first $2,500 costs
$15 and the other $7,500 costs $33.75, about $49 in all. How quickly Kraken re-tiers is not on disk,
so the findings state $49 to $60. The cost is the volume times the average fee per side, so it does
not depend on the balance. It excludes the spread on the taker exits and the price risk while
holding.

**Fix.** Restored in `phase-7-findings.md` §R.1, with the wording that it is the fee cost made
explicit, and both figures shown.

### The seven rulings applied, and three things found while applying them

**Agent:** Lead · **Date:** 2026-09-19

R2, R4, R8, R9, R10b, R11 and R12 were written into specs 126 and 129–144, the task list, the
findings (§R.2, §R.4 to §R.9) and the tracker. Spec 75 is recorded as resolved in the tracker and in
the spec file. Three things surfaced while writing them in:

1. **Specs 135 and 136 could not both be built as written.** Spec 136 wrote the capped skeptic
   "into spec 135's run directory and manifest". But spec 135 creates that directory through
   `new_model_run_dir`, which refuses an existing directory, and its manifest carries a sha256 per
   file. A skeptic added afterwards is either refused or not covered by the manifest. **Fixed in the
   specs:** 136 writes to a staging directory, and 135's assembly runs after it, writing each run
   directory once and complete. A fold with no capped skeptic is refused, never assembled with the
   uncapped one.
2. ~~**R4 and "alphabetical as the baseline" together make four runs, not two.** Spec 143 described
   one run per tier. It now describes two rankings at two tiers, with the tiers in parallel and the
   folds in sequence within each run.~~ **SUPERSEDED 2026-09-19 by the operator: Phase 7 is TWO
   runs.** See the entry "Phase 7 is two runs" below.
3. **R10b's working form still left two choices open**: which overlap-robust interval, and how
   "widened for trials" is computed. Leaving them to the builder would mean choosing them after the
   code exists and closer to a result. **Chose, in spec 139:** HAC (Newey–West) on the per-trade
   series, with the lag set to the largest number of trades overlapping any one hold, computed from
   times alone; and Bonferroni over the ledger's trial count.
   *Rejected:* a block bootstrap (coarse at tens of trades, and it adds a seed and a resample count),
   and the deflated Sharpe ratio's expected-maximum offset (it needs a variance of Sharpe ratios
   across trials, which most ledger rows cannot supply). **Contestable, so it is flagged to the
   operator with the specs rather than settled silently.**

One reading is also flagged rather than assumed. R8's second benchmark is taken as the recommendation
worded it: the pairs held, **while** they were held, and cash otherwise. The other reading, the held
pairs bought and held over the whole window, would be a third series, not a replacement.

### The lead's own mutation harness left a mutant on disk, because it restored after the run and not in a `finally`

**Agent:** Lead · **Date:** 2026-09-19

**What happened.** Mutation-testing the `core/` change for D9 and F2, the harness wrote the first
mutant into `src/acsoe/core/orchestrator.py` and then crashed launching pytest. The interpreter path
was relative, `.venv/Scripts/python.exe`, and `CreateProcess` does not resolve it against the
working directory the way a shell does. The restore line came after the run, so it never
executed. The mutant (`context.mode` taken from the run state) sat in the shared checkout for
about a minute, with five teammates importing from it.

**Why.** The same shape `code-standards.md` records for B's rehearsal harness, from the other end.
That harness restored only at the end of the run; this one restored only after the subprocess
returned. Either way, the restore depended on the step that failed.

**Fix.** Restored from the byte copy taken before the sweep, with the hash verified equal. The sweep
was re-run with `sys.executable` and the restore in a `finally`, with the hash re-checked after
every arm. Both arms were killed by the tests written for them: M1 (mode from the run state) by
`test_context_mode_is_the_configured_mode_even_after_activate`, and M2 (seed ignored) by the two
seed tests. **Consequence for teammates:** any test run between about 05:08 and 05:09 local that
imported `acsoe.core.orchestrator` may have seen the mutant. None of the five had reported a test
run in that window.

### Spec 126 and the context half of 144: the contradicted-claim grep, with each hit's disposition

**Agent:** Lead · **Date:** 2026-09-19

Written: invariant 2's replay section, placed after the paper-mode rules and not inside them;
invariant 4 in the operator's words, verbatim, with the operator's record beneath it; invariant 4's
engine 7 paragraph; the architecture's two proxies; the Phase 7 seams in `ownership.md`; and the
glossary's buy-and-hold and Scout entries. The config keys follow when a-replay's model fields land
(spec 126 step 6).

The grep was for the claims the new rules contradict, over `AGENTS.md`, `README.md` and
`context/*.md`:

- **"less willing" / "never more"**
  - Invariant 4's own sentence: replaced (R12).
  - Invariant 14, "everything else in this document makes the system less willing to act": false
    after the ranking. Reworded: everything else either makes the system less willing or, in engine
    7's ordering, changes which candidate is examined without overriding a verdict. Invariant 14
    stays the one place a verdict is overridden.
  - Invariant 2's fallback sentence: about fallbacks, true, kept.
  - `engine-contracts.md` line 235 (engine 16): about engine 16, true, kept.
- **"no machine learning"**
  - `project-overview.md` and `README.md` count nine engines with no machine learning, engine 7 among
    them. **The count is kept at nine**; the retired-vocabulary table forbids the next number down
    beside "engines". A sentence says engine 7 is counted for its filter and that its ordering reads
    the predictor's output.
- **"fixed score" / "deterministic score"**
  - The glossary's Scout entry: rewritten.
  - Invariant 4's engine 7 paragraph: rewritten.
- **"never a constant"**
  - `AGENTS.md` fees and minimums: true, since the replay fee is a declared fixture, not a constant
    in code. A pointer bullet to invariant 2's replay section was added, because `AGENTS.md` is the
    file every agent reads first.
  - The glossary's hurdle entry: true, kept.
- **"no fallback" / "assumed spread" / "invalid"**
  - The paper-mode table rows: true for paper, which the replay rule does not touch.
  - Invariant 2's retired-tier paragraph: true.
  - `architecture-context.md` "The consequence": extended with the two named proxies.

**Held until the gate over `engine-contracts.md` finishes:** engine 7's prose there (spec 144 step
3). A gate in the worktree holds a copy of that file.

### Gate b4 (specs 136 and 135's modules) RED on one test, predicted before it finished

**Agent:** Lead · **Date:** 2026-09-19

**What happened.** `logs/verify/gate-b4-c-136-135-modules.log`: `toolchain_green` FAIL, pytest
`1 failed, 3522 passed, 3 skipped`. The one failure is
`tests/research/test_backtest.py::test_backtest_is_the_one_research_module_allowed_to_import_core`.

**Why.** `research/artefact_assembly.py` (spec 135) builds a `StoreClient` inside a function, so
research reaches `acsoe.clients`. Only `backtest.py` may. c-criteria's spec 138 hit the same test
earlier and fixed it by owning its own read. Spec 135 itself says "through
`StoreClient.new_model_run_dir`", and that is satisfied by injection, as `research/training.py`
already does. The spec wording invited the import; the boundary test is right.

**Fix.** Sent back to c-models: inject the store, and construct it in a `scripts/` entry. **This is
the first red on this boundary.** A second consecutive red after the fix is a stop, per the
operator's rule. The 26 assembled run directories are unaffected: they were produced by this code,
and the fix changes where the store is built, not what is written. The re-gate will say so.

### Gate b5 (engine 7's ranking, engine 20's promotion gate, the leaderboard screen) RED on one test: a mutation anchor that now occurs twice

**Agent:** Lead · **Date:** 2026-09-19

**What happened.** `logs/verify/gate-b5-b144-c139e20-140lb.log`: pytest `1 failed, 3576 passed`.
The failure is
`tests/verify/test_phase5_criteria.py::test_a_write_routed_around_the_store_client_is_a_fail`.
Its patcher refuses, because the anchor
`    from acsoe.clients.store.contracts import LeaderboardRow` now appears twice in engine 20. There
is one in the Phase 5 writer (line 531) and one in spec 139's new promotion writer (line 750).

**Why.** The patcher's exactly-once rule working as intended (code-standards.md: "a test that
anchors on a literal string must assert the literal occurs exactly once"). Without it, the
mutation would have gone into whichever import came first, and the Phase 5 criterion's proof could
have stopped being able to fail without anyone noticing. **The criterion is fine; its proof's
anchor went stale.**

**Fix.** Sent to c-eval, whose change made the anchor ambiguous: give the test an anchor unique in
the new file, keeping the mutation's meaning (a raw `sqlite3` route beside the store's
`LeaderboardRow`). Either widen the anchor with neighbouring lines, or mutate both writers in two
tests. **First red on this boundary.**

### Gate b6 (132, 133, 134, 138, `DOCUMENTED_TABLES`) RED on one test: the same stale-anchor shape as b5, in engine 19

**Agent:** Lead · **Date:** 2026-09-19

**What happened.** `logs/verify/gate-b6-132-133-134-138-doctables.log`: one failure,
`tests/verify/test_phase4_criteria.py::test_a_rejection_written_without_its_economics_is_a_fail`,
with "anchor appears 3 times, expected exactly once". The anchor is
`            economics[column] = None if value is None else str(value)` in engine 19.

**Why.** Spec 133 harvests the approval economics with the same statement engine 19 already used
for rejections, so the literal now occurs three times. The patcher refuses rather than mutating the
first match, which is why this is a red and not a proof that silently moved to the wrong writer.
The second instance of this shape tonight: **a new writer that copies an existing writer's idiom
makes every mutation anchored on that idiom ambiguous.** Neither author ran the Phase 3–5
criterion tests that read engine source, and both were caught by the gate.

**Fix.** Sent to c-eval, whose change caused it: re-anchor onto the rejection writer only, and add
a twin test that plants the same defect in the approval writer. First red on this boundary.

### The combined gate's first launch never ran, and its background task reported success

**Agent:** Lead · **Date:** 2026-09-19

**What happened.** The first launch of gate b67 passed the 463 fixture files as separate
arguments. The Windows command line overflowed, the interpreter never started (`exit 126`), and no
log was written. The background task still reported "completed (exit code 0)", because its last
command was a `tail` that ran regardless. **A gate that never ran reported a clean exit.**

**Why.** The wrapper chained `...; echo; tail` with no `set -e`, so the task's exit status was the
last command's, not the gate's. The lead noticed because the gate finished in seconds and not in
the 30 minutes a real one takes. It was confirmed by reading the output (`exit 126`, "cannot open
... log").

**Fix.** `gate.py` accepts a directory as one argument (copytree, and a directory hash for the
moved-in-main check). The re-launch was confirmed to have started by reading its log's file list
20 s in, not by the command returning. **The standing check after any launch: read the evidence
it has started, never the return code alone.** This is the operator's rule about confirming a
detached run is alive, applied to a gate.

### Phase 7 is two runs: tiers 3 and 5 on expected move. The four-run reading is withdrawn

**Agent:** Lead · **Date:** 2026-09-19

**Ruled by the operator:** two runs, tiers 3 and 5, on engine 8's expected-move ranking (operator ruling 2026-09-19, after the overnight build). No alphabetical run, now or later: alphabetical is the name of the limitation the ranking removed, not a rival ranking. A baseline run would answer whether ranking beats not ranking, which nobody will challenge. It would not answer whether the model has skill; the benchmark basket (R8) and the promotion gate (R10b) answer that. It is also required by no Phase 7 criterion.

**Where the four-run reading came from, so no future session rebuilds it.** The Phase 7 brief
said "Tiers 3 and 5. Two rankings: engine 8's expected move, and alphabetical as the baseline",
and "ALPHABETICAL AS THE BASELINE, same window, same tiers. Two configurations only." The lead
read "same tiers" as both rankings at both tiers, and wrote four runs into spec 143, the task
list and findings §R.6. The operator has since ruled two, and records that those lines conflict
with an earlier decision that there would be no alphabetical ranking. **Every live statement of
four runs has been rewritten or struck through; this entry is the authority.**

**Consequences recorded, not changed:**
- **The trial ledger** (spec 139, N = 1,679) counts four Phase 7 runs. Two will run, so it
  overcounts by two, in the harsher direction R9 asked for, and is left as committed. The effect
  on the Bonferroni quantile is negligible (1,679 against 1,677 trials).
- **Engine 7's alphabetical path still exists**, as the behaviour when `scout.rank_feature` is
  absent. That is also the committed `config/default.yaml`, where the key is absent. The run
  selects expected move through the driver's `--ranking expected_move`. Removing the path, or
  setting the key in the committed config, changes what the daemon does, so it is not done
  without a ruling.

### The previous lead was still running when its successor started; the b11 gate is void

**Agent:** Lead (new session) · **Date:** 2026-09-19

**What happened.** A new lead session was started from the handover, on the premise that the old
one had run out of context. Checking the processes before acting showed that the old session
(`claude.exe` PID 1056, started 04:19) was still alive and still working through the handover's
steps 1 and 2 itself: its `b11-140-shap-writer` gate had been running since 17:59. From 18:03,
c-eval applied spec 146 to engine 19 (the handover said "not applied"), swept it and edited the
README. So `engine.py` changed after the gate had copied it. The handover also disagreed with the
tree on steps 3 and 5, which were already done (`490f0d2`, `6f242e0`). The new lead stopped
without writing anything and asked the operator which session would continue.

**Why it mattered.** Two leads and two engine-19 writers in one tree, with competing gates and
commits, is the collision the ownership map and D15 exist to prevent. The handover had been
written as a snapshot and never updated while the old session carried on.

**Fix.** The operator closed PID 1056 after confirming no `mutate.py` was running. Checked
read-only before any write:
- every arm of `sweep140` (9) and `sweep146` (8) is in its original state;
- `engine.py`, `contracts.py` and `README.md` still hash `53e16db0`, `dcde37cd` and `5dd015bd`,
  as before the close;
- no process from 1056 survives;
- the recorder, supervisor, `funding.py`, `fees.py` and the manager are alive, and the raw
  files are being written.

**The b11 gate is void**, because `engine.py` moved under it. 140 is re-gated as **b12**, on
exactly the blobs b11 had captured. c-eval's `pre146/` copies hash `c0a7fd5b`, `603ee59e` and
`3b7d4601`, equal to b11's, and are passed to `gate.py` as `rel::alt`. So the 140 commit carries
the 140 state alone, and 146 follows as its own boundary.

**Found on the way, for Phase 8 (operator instruction).** `mutate.py` restores from an in-memory
copy in a `try/finally`, and a hard kill skips it. The fix is in the tracker's Open Questions.
