# 137 — A batched DI score (parked spec 102, resumed)

**Owner:** C — Interface and models

**Phase:** 7. Phase 7 prerequisite 5. **Required:** R1 was ruled expected move, batched
(2026-09-19), and R11 was ruled on the same day: the ranking skips pairs the anomaly and DI gates
would refuse. So the ranking scores every universe pair's DI on every bar.

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
- The engine-side use of it is spec 144, not this spec.

## Check When Done

- Row-by-row equivalence on a random batch and on the fold 404 reference.
- `di_leave_one_out_excludes_48_bars` still PASS.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
