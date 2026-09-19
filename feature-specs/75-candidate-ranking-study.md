# 75 — The candidate-ranking study, for the operator's ruling on engine 7

> **RESOLVED 2026-09-19 by operator ruling R1.** Engine 7 ranks by engine 8's expected move, batched,
> with invariant 4 amended. No feature from this study was adopted: `log_return_4` was rejected
> because it was chosen from this study, which was computed over the same out-of-sample data the
> Phase 7 report uses. The ruling, its reasoning and the recorded circularity are in
> `context/progress-tracker.md` (Open Questions, the entry marked RESOLVED 2026-09-19). The
> implementation is spec 144. The study below stands as it was written and run.

**Owner:** C — Interface and models

**Phase:** 5. `research/training.py` gains a `--ranking-study` mode; the report lands in
`docs/dataset/`.

## Goal

The evidence the operator asked for before choosing engine 7's ranking score: for every
feature, what happens when the pair ranked first by that feature on each bar is the one taken.
The operator rules; nobody guesses.

## Implementation

1. Over spec 67's OOS file: on each decision bar with two or more pairs present, rank the pairs
   by each feature in turn, both directions, and take the first. Report per feature and
   direction: bars covered, the target rate of the taken pair, the stop rate, the timeout rate,
   the mean `return_pct`, the fraction of taken pairs whose DI refused, and the same numbers
   for the **alphabetical** choice that stands in today, which is the control.
2. A second table conditions on BUY calls only: the target rate among taken pairs the
   predictor would have called BUY. ~~beside the break-even rates.~~ **Amended 2026-09-13,
   the same ruling spec 67 carries:** no break-even rate is computed. Friction is live fees
   plus the measured spread plus slippage, none of which exists offline, and invariant 5's
   reference figures are marked for sanity-checking and never for use in code. The report
   carries the formula, both barriers and `friction: null`, and the comparison is the
   reader's.
3. Written to `docs/dataset/ranking-study-<date>.json` with the provenance block the other
   dataset reports carry, and summarised as one table in `docs/build-log/phase-5/c-interface.md`.
4. **No feature is recommended in the report.** It is a table; the recommendation, if any, is
   the lead's in the plan and the decision is the operator's.

## Scope Limits

- Do **not** change `rank_universe` or anything under `engines/scout/`. That is B's, spec 76,
  and it waits on the ruling.
- Do **not** compute a composite score. One feature at a time; a composite is a formula
  nobody asked for.
- Do **not** run this on in-sample predictions. The OOS file only.

## Check When Done

- The report exists, its alphabetical control row is present, and every feature in
  `FEATURE_NAMES` appears twice (both directions).
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
