# 102 — The DI's fitting and scoring path, at size

**Owner:** C — Interface and models

**Phase:** 6, pulled forward by operator ruling 2026-09-16. Phase 7 prerequisite 5, and the part of
prerequisite 4 that attaches to it. `modelling/di.py` and `tests/modelling/`, `tests/research/`.

## Goal

`di.score` costs about 1.13 ms a row in the suite and 136 ms a row at the full run's reference
size, and the leave-one-out over a 200,000-row reference takes about 20 minutes of one core. It is
the test suite's largest single cost — 3.1 s per trained fold, paid on every Phase 6 gate run. At
the end of this spec the same numbers come out faster, and a test proves they are the same numbers.
Pure optimisation; no methodology changes.

## Implementation

1. **Measure first**, recorded in the build log: `di.fit` and `di.score` at the suite's sizes and at
   fold 404's (93,166 test rows against its reference), each run in its own process and in both
   orders — the benchmark control from `code-standards.md`.
2. `modelling/di.py`: a batched `score_many(fitted, matrix)` over test rows in chunks that bound
   memory, and a leave-one-out that is batched and bounded (chunked distance blocks, optionally
   parallel across cores). **The 48-bar cross-pair exclusion is unchanged** and
   `di_leave_one_out_excludes_48_bars` stays green. `research/training.py` calls the batched form.
   Engine 8 scores one vector and may keep `score`.
3. **Equivalence, recomputed rather than trusted:** a test fits and scores the same reference and
   test rows through the old per-row path, kept as a private reference implementation in the test
   module, and through the new path, asserting identical refusals and DI values within a stated
   float tolerance justified in the docstring. Mutations: the exclusion span off by one bar; a chunk
   boundary dropping a row; neighbours `k` miscounted at a chunk edge.
4. **Prerequisite 4, the part that fits here.** A peak-memory test over `fit` and `score_many` at a
   size large enough to show growth, asserting peak does not scale with the number of test rows
   (chunking) — measured with `tracemalloc` or process RSS in a subprocess, stated which and why.
   **A whole-run per-fold memory test is deliberately not written here**: the skeptic's training set
   grows every fold by design until prerequisite 1 is ruled (spec 83), so such a test cannot be
   green today and would be written against a methodology not yet chosen. Say so in the build log.
5. Report the suite time before and after, both orders.

## Scope Limits

- Do **not** change `k`, the percentile, the window, the exclusion, the scaler or what is refused.
- Do **not** cap the skeptic's training set. That waits on spec 83's ruling.
- Do **not** change `research/walkforward.py`.
- Do **not** add a dependency outside `architecture-context.md`'s stack.

## Check When Done

- The equivalence test and all three mutations observed red; `di_leave_one_out_excludes_48_bars`
  and `di_fitted_on_predictor_training_set` PASS on `--phase 5`.
- Suite and per-fold times before and after, both orders, in the build log.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
