# 21 — History screen

**Owner:** C — Interface and models

## Goal

Closed trades and past rejections, so the operator can answer *why was that rejected?* — the
interface's stated secondary question — without opening the database.

## Implementation

1. Add `GET /api/history` to `src/acsoe/console/app.py`, reading `recent_closed_trades` and
   `recent_rejections` through spec 17's reader, bounded by a row limit.
2. Trades table: pair, opened, closed, quantity, entry, exit, outcome, realised P&L and realised
   P&L percent, entry and exit fees. Outcome renders as the operator word — target, stop,
   timeout, liquidation — not a code.
3. Rejections table: time, pair, the engine that rejected it, the operator-prose reason from
   spec 20's mapping, and — where the row carries them — expected move, friction, net edge and
   hurdle.
4. Table treatment is the one `ui-context.md` sets for screens it has not designed: left-aligned
   labels, right-aligned tabular numbers, hairline separators, **no cards**. Every numeric cell
   carries spec 18's `.num` class.
5. Money renders at the stored `Decimal`'s own precision through spec 17's `format.py`, never
   re-rounded and never through `float`. Percentages are explicitly signed with U+2212.
6. Colour reinforces the sign and is never the only signal — a red-green colourblind operator
   must lose nothing on this screen.
7. Empty state in the same spirit as the cycle feed: say what there is none of, not "No results".

## Scope Limits

- Do **not** draw a chart, an equity curve, or any attribution. Phase 7 owns evaluation, and an
  equity chart here would be a screen no context file has designed.
- Do **not** add export, CSV download, or a filter beyond the row limit. `ui-context.md` does not
  design one, so adding one is inventing a screen.
- Do **not** restate the cycle feed here. History is closed trades and past rejections; the feed
  is the current run's ticks.
- Do **not** add or change a store method, and do **not** add a config key.
- Do **not** compute a derived metric — win rate, expectancy, Sharpe. Those are Phase 7's, and a
  number computed in the view layer is a number nothing verifies.
- Do **not** use a raw hex or a card treatment.

## Check When Done

- Both tables render from the seeded trades and rejections, newest first.
- The seeded losing-trade streak is visible and each row's sign is legible without colour.
- Against a migrated-but-empty database both tables render an empty state, and "No results"
  appears nowhere.
- Every numeric column carries the tabular-figure class; no money value passes through `float`.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 1`
