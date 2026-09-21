# Phase 8 build log — Lead

Per `context/script-rules.md`: every non-trivial problem and its resolution, written **at
diagnosis, before the fix**. Decisions go in `decisions-2026-09-21.md`; this file is what went
wrong and what was learned.

### Phase 8 opened: files created, housekeeping done, costing first

**Agent:** Lead · **Date:** 2026-09-21

**What happened.** The operator closed Phase 7 on the write-up at `48faf18` and asked for Phase 8
to be **costed before anything is built**: the live UI, a real activation button, and the four
live-path defects Phase 7 recorded. They also asked that Phase 8 carry the same paper trail as
Phase 7, so a fresh session can pick it up from files alone.

**Created,** mirroring Phase 7's names and layout exactly:
- `feature-specs/PHASE-8-TASKS.md` (the shared task list, as Phase 7 had it)
- `docs/build-log/phase-8/lead.md` (this file)
- `docs/build-log/phase-8/decisions-2026-09-21.md` (as Phase 7's `overnight-decisions-2026-09-19.md`)
- `docs/build-log/phase-8/team-brief.md`
- `docs/dataset/phase-8-findings.md` (alongside `phase-7-findings.md`)

**Housekeeping.** The Phase 7 watchdog task is unregistered (both runs finished; no `ACSOE*`
task and no watchdog process remain). The stale `rank_universe` docstring is corrected and
gated. **The config key was attempted and reverted** — see the entry below; it is not the
one-line change it looks like.

### C0 done: Phase 8's criteria written PENDING-first, and scoped to the ruled build

**Agent:** Lead (C's lane, operator instruction; no C session running) · **Date:** 2026-09-21

**Why it was first.** `verify.py --phase 8` registered only `docs_vocabulary` and
`toolchain_green` and therefore reported *"Phase 8 is green: every criterion PASS, zero
PENDING"* while nothing of Phase 8 existed. The operator's words: a phase that reports green
before it starts cannot tell them anything at its close.

**Four criteria, all PENDING the day they were written**, each observed PENDING, PASS and FAIL
by `tests/verify/test_phase8_criteria.py` (20 tests): `live_client_serves_the_stream`,
`pair_rules_key_on_engine_names`, `console_refuses_a_foreign_origin`,
`daemon_reads_the_real_exchange`. The FAIL arms aim at the *plausible wrong implementation*
rather than at absence — a stream member that exists but is not callable, a half-finished name
migration, an Origin check that also refuses the operator's own kill switch, a digest from the
fake client.

**Two defects in my own criteria, caught by running them rather than by reading them.** The first
version FAILed where it should have been PENDING: it read spec 127's recording as a parsed object,
but the recording stores the response **verbatim as a string** under `payload`, so the mapper was
handed nothing and refused. A mapper that cannot read the real body at all is unbuilt work, not a
wrong implementation, so that path now reports PENDING and carries the refusal in its message.
The second used a helper name that does not exist (`seed_database`) and then a bare
`TemporaryDirectory`, which on Windows raises `PermissionError` during cleanup because the console
holds the database open; `console_workspace()` exists for exactly that and is now used.

**Deliberately not written:** criteria for `mode: live`, the live order surface, `close_all` live
or the soak. The operator deferred all four, and a test asserts none of those names is
registered. **Phase 8 cannot be closed on this scope alone**, which the task list states.

### `scout.rank_feature` by option C: a daemon config, with drift caught by a test

**Agent:** Lead · **Date:** 2026-09-21

**Ruled by the operator** over option B, because naming `models.*_run_id` in the file every clone
gets would go stale on any retrain and mislead a future session.

**What was built.** `config/daemon.yaml`, an exact copy of `config/default.yaml` with one
override (`scout.rank_feature: expected_move`), started with
`acsoe --config config/daemon.yaml engine`. The loader has no overlay — `Config.load(path)` reads
one file, and the only environment reads in `platform/config.py` are for credentials — so a full
second file is the only shape option C can take.

**The cost the operator named, and what answers it.** Two files drift.
`tests/platform/test_daemon_config.py` flattens both and fails, naming the key, if they differ
anywhere but the declared override. Proven capable of failing by two mutations applied to a byte
copy **written to disk first**, restored and hash-checked: both killed.

**Still open, and reported rather than invented:** `daemon.yaml` alone does not make the daemon
rank. Ranking loads the artefacts named by `models.*_run_id`, those keys are absent, and engine 7
still fails closed. Which trained model a live daemon runs is the operator's decision. The newest
artefacts on this machine end their training on **2025-01-04, about twenty months before today**,
which is a fact the live plan needs.

### `scout.rank_feature: expected_move` makes the daemon fail closed on a fresh clone

**Agent:** Lead · **Date:** 2026-09-21

**What happened.** The operator's housekeeping item 2 was implemented: the key set in
`config/default.yaml`, its two stale comment blocks corrected, and the scout test that pinned
the key's absence rewritten so the alphabetical path kept its coverage. **34 of 63 scout tests
then failed**, and not on stale anchors: tests that read `entered` from engine 7's payload got a
`KeyError`, because the engine was publishing a block instead of a universe.

**Why.** With the key set, engine 7 ranks through the shared function, which loads the predictor
and anomaly artefacts named by `models.*_run_id`. Those keys are **absent from the committed
config**, and `models/` is gitignored, so on a fresh clone and in every test fixture the ranking
cannot be scored: `_expected_move_ranking` raises `MissingInputError` and engine 7 BLOCKs with
`scout_inputs_unavailable` on every tick. Verified directly against the committed file:
`scout.rank_feature = expected_move` with all three `models.*_run_id = None`.

So the change converts *"a fresh clone ranks alphabetically and runs"* into *"a fresh clone
blocks at engine 7 forever"*. That is a change to what the system does, which is a stop under
the operator's own rules.

**Fix.** Reverted the config and the test edits; the tree is green at 63 passed. Kept a docstring
correction that is true of the reverted state. Reported to the operator with three options and
their costs (`docs/dataset/phase-8-findings.md`). **Not decided by the lead.**

**Scope conflict, recorded rather than resolved silently.** `ai-workflow-rules.md`'s Phase 8 row
is *Live readiness* — `live_guard.py`, `close_all` end to end, and a 7-day soak. The operator's
goal for this phase is the **live UI and activation control**. Both are in the task list, marked
by origin. The workflow row's criteria remain what `verify.py --phase 8` judges. Flagged for the
operator rather than decided by the lead.

**Nothing else is built.** The costing is in `docs/dataset/phase-8-findings.md` and no item in
it is approved.

### Report verification (draft v2): the findings document's tier 3 mean is by a different definition from the module's

**Agent:** Lead · **Task:** operator's remaining items for the report, draft v2 · **Date:** 2026-09-21

**What happened.** The report states the tier 3 mean net return per trade as −1.08%, computed by the
committed acceptance module; `docs/dataset/phase-7-findings.md:1309` states −0.70% for the same twelve
trades. Re-running `promotion_verdict` over the twelve `trades` rows, with holds built exactly as
`engines/tournament/engine.py:_holds` builds them, gives −1.0766%; `avg(trades.realised_pnl_pct)` gives
the same.

**Why.** −0.70% is the sum of realised PnL over the trade count and the *starting balance*
(−421.96 / 12 / 5,000 = −0.7033%), i.e. the −8.44% equity return divided by twelve. The module's mean is
over each trade's own entry notional. The findings row mixes the two: its tier 5 figure in the same cell,
−2.19%, is the per-trade mean. The pre-registered bar is in per-trade units, so −1.08% is the comparable
figure. Two more things found the same way: the findings' and the report's "mean overshoot 0.51 pp" on the
13 stops is 0.488 pp from the rows (median 0.163 is right), and the report's "Bitcoin rose 58.2%" has no
source in the repository (the partitions and the archive give +58.0% tick to tick, +58.1% by daily closes).

**Fix.** None to the code or the databases. Nothing in the report was edited, as instructed; the findings
file is left as written and the correction is proposed in `docs/report/verification_draft_v2.md` §1 for
the operator to apply or refuse. The full Chapter 6 check, with every query, is in that file; the
refused-candidate labels are `docs/report/data/refused_candidates_labelled.csv`; the console capture is
`docs/report/figures/fig5_5_console.png`, taken over a renamed *copy* of the tier 3 database with the
console's clock injected at 2025-01-03 23:46:30Z.

**Consequence.** The PDF also embeds a pre-completion render of the exposure figure (tier 3 "1876 h",
where the committed regeneration says 2184 h), and the console renders equity at full stored precision
and pluralises "60 entrys" — both real properties of the committed console, reported not changed.
