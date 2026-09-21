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
