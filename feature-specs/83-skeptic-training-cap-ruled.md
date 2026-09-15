# 83 — The skeptic's training cap, ruled, and Finding 1's caveat

**Owner:** Lead

**Phase:** 6. Phase 7 prerequisite 1, ruled during Phase 6 so Phase 7 is not blocked on its first
day. No code this phase.

## Goal

The methodology ruling is recorded where Phase 7 will read it, and the finding it invalidates
carries its caveat everywhere it is stated.

## Implementation

1. `context/progress-tracker.md`, prerequisite 1, **RULED by the operator 2026-09-16**: fold *k*'s
   skeptic trains on the eligible out-of-sample BUY calls of the **last 13 folds** only — a rolling
   window matching the predictor's locked past-only 90-day window. Chosen because it mirrors a
   Locked Decision rather than introducing a second convention, bounds memory by construction
   rather than by an arbitrary row count, and needs no sampling seed. The purge and embargo are
   unchanged and apply inside the window.
2. Same entry: **the cap is Phase 7 work, not Phase 6.** Capping changes what the skeptic is
   trained on, so re-measuring means retraining 405 skeptics, and that belongs with Phase 7's full
   run rather than costing this phase hours. `research/training.py` is C's and is untouched here.
3. **Finding 1 gains a caveat wherever it is stated** — the tracker's Findings section and
   `docs/build-log/phase-5.md`'s summary: the skeptic's **0.531** survivor target rate was measured
   on the **uncapped** skeptic, which is code that will no longer exist once the cap lands, and it
   must be re-measured before it is cited anywhere, including in the dissertation. A correcting
   entry, not an edit to the original (`script-rules.md` rule 6).
4. State the shape plainly, because this project keeps catching it: **a finding measured on code
   that no longer exists is a claim, not a measurement.**

## Scope Limits

- Do **not** implement the cap, and do not let a teammate implement it as a convenience.
- Do **not** re-run the veto sweep this phase.
- Do **not** edit Finding 1's original wording. Correct it with a new entry beside it.

## Check When Done

- The ruling, its Phase 7 placement and the caveat are in the tracker; the caveat is also in the
  Phase 5 build log.
- `docs_vocabulary` PASS; `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
