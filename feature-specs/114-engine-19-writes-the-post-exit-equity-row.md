# 114 — Engine 19 builds the exit-cycle equity row by filtering, and records the cash source

**Owner:** C — Interface and models

**Phase:** 6. Operator ruling 2026-09-17 on Q-C1. Follows spec 113.

## Goal

On a tick where engine 22 closed positions, engine 19's equity row describes the account **after**
those sales, built only by filtering and summing facts other engines published:

- **positions value / unrealised PnL:** engine 21's position rows, minus every `position_id` that
  appears in `state["exit"]["positions"]` with status `closed`, summing the remaining rows'
  `value` and `unrealised_pnl`;
- **cash:** engine 1's start-of-cycle balance in the reporting currency, plus the `net_proceeds` of
  every row in `state["exit"]["closed_trades"]`;
- **`cash_source = 'after_exit'`.**

On any other tick the row is written exactly as today, from engine 1's balance and engine 21's
totals, with `cash_source = 'cycle_start'`.

## The partial-mark edge — the operator's first concern

Today an unmarked position makes engine 21 omit its totals and engine 19 write no row. **Under
filtering, a remaining (not closed) position whose row has no `value` must produce the same
outcome: no equity row, with the reason recorded.** A closed position with no mark is dropped
anyway and does not block the row. **A test must fail if a partial mark silently yields an equity
row missing one position's value** — that defect would look like a working row.

## Implementation

1. `src/acsoe/engines/memory/engine.py` `_write_equity`: the exit-cycle branch above; no other
   arithmetic on account figures. If engine 22 closed positions but engine 1 published no balance
   (the outage liquidation), no row, as today.
2. `cash_source` written on every row. **Rows on exit ticks, totals on every other tick**
   (operator, 2026-09-17); spec 113's sum test guards the seam between the two. If engine 19's
   trade-row validation refuses spec 113's `net_proceeds`, accepting it is part of this spec (a
   how-choice, operator-approved) — record it in the build log.
3. Tests with the real orchestrator: the stop and target legs' exit-cycle rows equal the true
   post-exit account (recomputed from the stored trade and the remaining positions),
   `'after_exit'` there and `'cycle_start'` elsewhere; the partial-mark test above; a two-position
   case where one closes and one stays open. Mutations (a closed position not dropped; a remaining
   unmarked position treated as worth zero; proceeds not added; the wrong source label), killing
   test named.
4. The criteria turn PASS: `round_trip_target`, `round_trip_stop`, `triggered_stop_holds` and
   `equity_row_never_values_positions_it_does_not_hold`. Record the before and after messages.

## Scope Limits

- Do not edit engines 21 or 22 or the store. No change to peak or drawdown arithmetic beyond the
  inputs.

## Check When Done

- `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
