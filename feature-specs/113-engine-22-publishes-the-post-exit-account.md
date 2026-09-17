# 113 — Engines 22 and 21 publish the facts engine 19 needs for the exit-cycle row; migration 0005

**Owner:** B — Store and trading

**Phase:** 6. Operator ruling 2026-09-17 on C's finding Q-C1 (exit-cycle equity row). **This
replaces the first version of this spec, which the operator withdrew**: that version had engine 22
subtract engine 21's valuation of the positions it closed, which ties engine 22 to how engine 21
values positions and would change silently if engine 21's method ever did.

## Goal

Each engine publishes only what it knows, so engine 19 can build the exit-cycle equity row by
filtering and summing:

- **Engine 22** publishes, on each `closed_trades` row, the **net proceeds** of that sale:
  `qty × exit_price − exit_fee`. A fact about a sale it executed. It reads neither engine 21 nor
  engine 1 to produce it.
- **Engine 21** publishes, on each position row, the position's **value**: `qty × last_price` —
  the multiplication it already performs for its own `positions_value` total — present exactly when
  `last_price` is present (a position opened by this tick's fill included, at its fill price).
- **The store** can record where an equity row's cash came from.

## The finding, in one paragraph

On C's stop leg the exit-tick row read cash 1663.92 (engine 1, start of tick), positions value
3281.10 (engine 21, before the sale), open positions 0 (store, after it): three moments that never
coexisted, equity 4945.02 against a true 4938.79. On the target leg it moved `peak_equity` to a
figure the account never held. Not paper-only.

## Implementation

1. Build-log entry first.
2. `src/acsoe/engines/exit/`: `net_proceeds` on every `closed_trades` row, exact decimal string,
   computed from the same `qty`, `exit_price` and `exit_fee` the row already carries. Name fixed by
   the lead in `engine-contracts.md`. Check whether engine 19's `_write_trades` / `TradeRow`
   validation refuses an unknown key on a trade row; if it does, **report it** — engine 19 is C's,
   and the lead routes the change rather than B editing it.
3. `src/acsoe/engines/position_manager/`: `value` on every position row that carries
   `last_price`, and absent on a row that does not. No change to `positions_value`,
   `unrealised_pnl`, or when the totals are omitted.
4. `db/migrations/0005_equity_cash_source.sql`: `equity_snapshots.cash_source TEXT NOT NULL`, CHECK
   allowing exactly `'cycle_start'` and `'after_exit'`; existing rows backfilled `'cycle_start'`.
   `EquityRow.cash_source` in `clients/store/contracts.py`; the seed writes `'cycle_start'`. Schema
   change approved by the operator's ruling. `EXPECTED_TABLES` / migration tests updated.
5. Tests: `net_proceeds` recomputed from the row's own fields; `value` recomputed per row, present
   iff `last_price` is, and the per-row values summing exactly to `positions_value` whenever the
   total is present; the migration's CHECK and backfill. Mutations (net proceeds without the fee;
   value on a row with no mark; value from `entry_price`), killing test named.
6. **The sum test must be proven capable of failing** (operator, 2026-09-17). Engine 19 values
   positions from the totals on ordinary ticks and from the rows on exit ticks, so this test is the
   only thing that keeps the two paths from drifting. A test asserting two numbers agree, where
   both come from one source, can pass while measuring nothing. So: a mutation that makes the
   per-row values disagree with `positions_value` — e.g. the row value computed from `entry_price`
   while the total still uses the bid, or the total summed over one row fewer — must turn the sum
   test red, **and it must be the sum test that kills it**, named in the build log.

## Scope Limits

- Engine 22 reads neither engine 21's nor engine 1's payload for this. No other new figures.
- Do not edit engine 19, engine 1, `core/`, or other lanes. Engine 19's use of these is spec 114 (C).
- No change to what engine 22 sells or when, or to engine 21's barriers.

## Check When Done

- `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
