# 136 — The 13-fold skeptic cap, implemented and trained for the window

**Owner:** C — Interface and models

**Phase:** 7. Phase 7 prerequisite 1, ruled 2026-09-16 (spec 83). **R2 ruled 2026-09-19: the
simulation runs the capped skeptic.** In the operator's words, 1.6% passing at a 58% hit rate
against 6.2% at 41% is a difference in this data at the step that decides the funnel's end, not a
difference in principle. The window's folds are 379 to 404 (R4). Fold 379's cap reaches back to fold
366.

## Goal

`research/training.py` trains fold *k*'s skeptic only on the eligible BUY calls of folds *k*−13 to
*k*−1, with the purge and embargo unchanged. Capped skeptics exist for every fold in the simulation
window, inside that fold's Phase 7 run directory (spec 135).

## Implementation

1. **The cap in the trainer**, under `training.skeptic_cap_folds` (lead's key). Filter the
   out-of-sample calls by fold index before `_skeptic_training_rows`. Nothing else in the selection
   changes.
2. **Replication proven first.** With the cap disabled, retrain two early folds and require the
   training identity and every probability to equal the saved `skeptic.txt`'s. On 2026-09-19,
   folds 20 and 40 matched exactly (`docs/dataset/phase-7-recon-2026-09-19/scripts/q_capped.py`).
3. **Train the window's folds** (379 to 404) with the cap. Write each skeptic, with its training
   identity and row count, to a staging directory under `data/derived/` that spec 135's assembly
   reads. It is not written into a run directory directly: those are written once and complete by
   spec 135. Measured 2026-09-19: about 28 s a fold
   alone, about 50 s with six running at once.
4. **Re-measure what Finding 1 caveats**, over the window's folds only:
   - the survivor target rate at 0.50, 0.60 and 0.70;
   - the no-skill band;
   - the matched-count comparison against `p_target`.

   The all-405-fold re-measurement stays outstanding and is said to be.

## Scope Limits

- No predictor retraining. Prerequisites 2 to 4 (the whole-dataset memory hazards) are not touched
  here, because no full walk-forward runs in this plan.
- The cap is the ruled 13 folds. No other window is tried.

## Check When Done

- The disabled-cap replication equal to the saved skeptics on two folds.
- A capped fold's training identity recomputed independently from the out-of-sample file equals
  its manifest's.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
