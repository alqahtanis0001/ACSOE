# 140 — Research screens: the leaderboard and the SHAP view, with a writer for the SHAP rows

**Owner:** C — Interface and models (`console/`, engine 19)

**Phase:** 7. The Phase 7 row's third criterion.

## Goal

The console renders the leaderboard, including promotion verdicts, and a SHAP view per decision.
**Today nothing writes SHAP.** Engine 8 publishes per-feature contributions in `state`, and
`rejections.shap_ref` exists, but no writer fills it (checked 2026-09-19). The view needs rows
before it can render them.

## Implementation

1. **Engine 19 persists engine 8's published SHAP** for every tick on which engine 8 scored a
   candidate, approved or refused. It writes Parquet through the store (architecture: SHAP in
   Parquet joined by decision id, never in SQLite), keyed by `(run_id, cycle_id)` and the pair, and
   sets `rejections.shap_ref` on a refusal. The approval side joins through spec 133's row.
2. **The leaderboard screen** under `ui-context.md`'s table treatment for undesigned screens:
   brier against base-rate brier, effective sample size, the deflated metric, promoted, and the
   reason.
3. **The SHAP view:** for a chosen decision, the features by absolute contribution with their
   signs, in the number rules' formats. **No placeholder chart**: a decision with no SHAP row says
   so, as spec 22's empty state already does.

## Scope Limits

- Read-only console, as ever: no command added.
- SHAP is computed only where engine 8 already computes it. No new explainer and no per-pair SHAP.

## Check When Done

- A rehearsal tick with a refusal at engine 10 writes a SHAP row, and the view renders it. A tick
  where engine 8 refused writes none.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
