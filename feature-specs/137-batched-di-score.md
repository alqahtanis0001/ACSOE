# 137 — A batched DI score (parked spec 102, resumed only if R1 is expected move)

**Owner:** C — Interface and models

**Phase:** 7. Phase 7 prerequisite 5. **Conditional:** built only if the operator rules R1 to rank
engine 7's universe by engine 8's expected move, which also needs invariant 4 amended (spec 126
step 4). Under `log_return_4`, engine 8 scores one candidate per bar and this spec stays parked.

## Goal

`modelling/di.py` exposes a public function that scores many vectors in one call and returns
exactly what `score` returns for each.

Measured on 2026-09-19 with fold 404's artefacts and 127 pairs
(`docs/dataset/phase-7-recon-2026-09-19/scripts/q_rank_timing.py`):

| Scoring | DI time per bar | Everything per bar |
|---|---|---|
| Looped, as engine 8 scores one candidate today | 14.5 s | 15.3 s |
| Batched through `_mean_nearest` | 0.90 s | 0.91 s |

## Implementation

1. Resume spec 102's parked partial diffs, as named in `context/progress/c-interface.md`.
2. `score_many(fitted, rows)` returns a list of `DiScore`. It refuses a non-finite row exactly as
   `score` does, and reports which row.
3. An equivalence test holds `score_many` to `score` row by row, at the 1e-12 tolerance already
   used for the module.

## Scope Limits

- No change to the statistic, the exclusion, the threshold or its direction (strictly greater
  refuses).
- The engine-side change, scoring every pair, belongs to the invariant 4 amendment's own specs.
  It is not made here.

## Check When Done

- Row-by-row equivalence on a random batch and on the fold 404 reference.
- `di_leave_one_out_excludes_48_bars` still PASS.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
