# 22 — Research views: leaderboard, and the SHAP pane's honest empty state

**Owner:** C — Interface and models

## Goal

The research pane rendering the seeded leaderboard, and a SHAP pane that tells the truth about
having no attribution data yet rather than inventing one.

## Implementation

1. Add `GET /api/research` to `src/acsoe/console/app.py`, reading `leaderboard(limit)` through
   spec 17's reader.
2. Leaderboard table: model id, model version, trained at, fold, number of trades, win rate and
   the remaining stored metrics, newest training run first. Same table treatment as spec 21 —
   left-aligned labels, right-aligned tabular numbers, hairline separators, no cards.
3. **The SHAP pane renders an empty state, deliberately.** `rejections.shap_ref` is the join key
   and the Parquet it points at is written by the training pipeline in **Phase 5**. There is no
   attribution data in the Phase 0 seed and there will be none until then. The pane names what
   is missing and which phase produces it, in the same voice as the cycle feed's empty state.
4. Both panes are sections of the single page from spec 18, switched client-side. No second
   page, no route that serves separate HTML.
5. Numbers follow every rule in `ui-context.md`: tabular figures, explicit signs, U+2212,
   `Decimal` precision, never `float`.

## Scope Limits

- Do **not** compute a metric, a ranking, or a trial haircut. The promotion gate is Phase 7's
  and a number computed in the view layer is a number nothing verifies.
- Do **not** read `models/`, any Parquet file, or any SHAP artefact. None exist yet, and a view
  that reads a path which will not exist until Phase 5 is a view that cannot be verified now.
- **Do not fabricate SHAP values, and do not render a placeholder chart, a chart of zeros, or
  sample explanations.** A chart that looks like attribution but is not is worse than no chart.
- Do **not** design a SHAP visualisation. `ui-context.md` explicitly leaves it undesigned; if
  the operator wants one now, that is a lead escalation, not a decision taken here.
- Do **not** add or change a store method, and do **not** add a config key.
- Do **not** use a raw hex or a card treatment.

## Check When Done

- The leaderboard renders from the seeded rows, newest training run first, with tabular figures
  on every numeric column.
- The SHAP pane renders its empty state, naming Phase 5 as the producer, and a test asserts it
  emits no fabricated attribution row and no chart element.
- Against a migrated-but-empty database the leaderboard renders an empty state, not "No results".
- Both panes are reachable from the one page without a full page load.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 1`
