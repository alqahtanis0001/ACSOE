# 142 — Rehearse one replayed day end to end before the long run

**Owner:** A — Platform

**Phase:** 7. After 129, 131, 133, 134 and 135. **The long run (143) does not start until this is
green.**

## Goal

One historical day, chosen because the offline funnel says a candidate clears the cost gate on it,
runs through every registered chain against the replay client and the paper broker. It produces an
entry, a fill or a cancellation, minute-by-minute management and an exit, all recorded. Each row is
checked by recomputation, not read back.

## Implementation

1. Commit the day's slice as a fixture: the weekly partitions cut to one day plus the 96-bar
   lookback, the pair rules, and the scenario fixtures. Spec 141's pipeline criterion reuses it.
2. Run it twice from a clean database, and once killed and resumed.
3. For every trade:
   - recompute the friction and hurdle from the scenario fixtures and the synthetic book, and
     require equality with the `trades` row;
   - recompute the fill from the partition's trades under the broker's strictly-below rule.
4. Record the per-tick cost at the real pair count. It replaces the sum-of-parts estimate of 1.5 to
   3 s per bar tick, and becomes the run-time figure for spec 143.

## Scope Limits

- Any defect found is reported to its owner, not fixed in another lane. Phase 6's rehearsals found
  two defects reachable only end to end, and that is what this is for.
- No threshold, gate or schedule change to make the day trade.

## Check When Done

- Two clean runs identical, and the resumed run identical to both.
- Every recomputation equal.
- The measured per-tick cost recorded in `docs/build-log/phase-7/a-platform.md`.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
