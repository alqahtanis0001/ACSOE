# Engine 19 — `memory`

**Manage chain, last of three. Not a gate. Runs every tick, in every mode.**

The single writer of relational rows. `block_records`, `positions`, `orders`, `trades`,
`rejections` and `equity_snapshots` are all written here, from `state`, and by nothing
else. Every other engine describes what happened; this one records it.

Keeping one writer is what makes the manage chain's "always runs" guarantee sufficient
for invariant 12, and it is why this engine sits underneath the whole of engine 17
`safety`'s input surface.

## Why a missed row is worse than a crash

`safety` derives its outage count from `block_records`. **A missed row does not fail —
it makes the circuit breaker inert, silently, with every test green.** No crash, no red
test, nothing an operator could see. The same holds one table over: invariant 12 puts a
rejection that never reached storage on the same footing as a lost trade.

Two rules follow, and both read as pedantic until you notice each one is a defect that
leaves the suite green.

**A block record on every blocked tick, candidate or not.** Reading invariant 12 as
"rejections are logged" and writing a row only where a candidate was rejected empties
the table on exactly the ticks the outage counter counts — `data_guard` blocks before
the opportunity chain ever runs, so most blocked ticks never had a candidate at all.

**Absent means nothing-to-record, never record-a-zero.** Engines 18, 21 and 22 are
Phase 6. Their `state` keys are absent today, and absent is not a position count of
zero, not an equity of zero, and not a closed trade. A zero equity row is a 100%
drawdown against any earlier peak and would freeze the account on the first tick of a
fresh install.

## What it reads from `state`

Every key is named in `contracts.py`, with the engine that owns it beside it, because
contract rule 3 forbids importing another engine to find out what a key is called.

| Key | Owner | Used for |
|---|---|---|
| `state["guard_blockers"]` | orchestrator | one `block_records` row each, `is_primary` on the first |
| `state["cycle_id"]` | orchestrator | the tick half of `(run_id, cycle_id)` |
| `state["trading_blocked_by"]`, `state["block_reason"]` | orchestrator | whether this tick was a *rejection* and what the operator is told |
| `state["block_status"]` | orchestrator | `BLOCK` or `ERROR`: whether the opportunity-chain blocker refused or raised. Read, never inferred from an empty payload |
| `state["scout"]["pair"]` | 7 `scout` (B) | the candidate the rejection is about |
| `state["<blocker>"]["reason_code"]` and its economics | the gate that refused | the `rejections` columns |
| `state["exchange"]["balances"]` | 1 `exchange` (A) | cash, and therefore whether an equity row can be written at all |
| `state["position_manager"]` | 21 (B), Phase 6 | positions, resting orders, position value, `hold_reason` |
| `state["execution"]["orders"]` | 18 (B), Phase 6 | the entry order it placed, on the **opportunity** chain, same tick |
| `state["exit"]["closed_trades"]` | 22 (B), Phase 6 | one `trades` row per closed round trip; each row's `net_proceeds` is the exit tick's cash |
| `state["exit"]["orders"]`, `["positions"]` | 22 (B), Phase 6 | the exit orders it placed and the positions it closed — the `position_id`s dropped from engine 21's valuation |
| `state["position_manager"]["positions"][*]["value"]` | 21 (B), Phase 6 | per-row `qty × last_price`, summed over the positions that remain open on an exit tick |

## An opportunity-chain engine that errored

Operator ruling 2026-09-16, invariant 12 and contract rule 7; spec 104. When
`state["block_status"]` is `ERROR` and the primary blocker is **not** a guard, engine 19
writes one `block_records` row: `blocked_by` the engine's name, `status` `ERROR`,
`block_reason` the code `engine_errored` (`REASON_ENGINE_ERRORED` in `contracts.py`, mapped in
`console/format.py`'s `REASON_PROSE`), `is_primary` true. **No `rejections` row**, because
no candidate was refused, and **no `reason_code` is read or required**: a code is a decision
and an error is the absence of one. Positions, orders and the equity row are written as on
any other tick.

Before the ruling this tick was lost: rule 7 empties a raising engine's payload, engine 19
read that as a refusal with no code and raised, and the tick had no rejection, no block
record and no equity row. Engine 17's error rate now counts these rows too.

Two neighbouring cases keep their treatment, and the tests name them apart:

- **A guard that errored** is recorded from `state["guard_blockers"]` as before, and gets no
  second row.
- **A `BLOCK` with no `reason_code`** is a gate breaking its contract. It still raises, because
  the console renders a rejection with no code as silence. It looks exactly like an errored
  engine's empty payload, which is why the status is read rather than inferred.

## What it writes into `state`

`state["memory"]` only — contract rule 2. It carries per-table counts (zeros included,
so "ran and had nothing to record" is distinguishable from "did not run"), which
upstream sources were present this tick, the equity and peak it wrote, why it wrote no
equity row when it did not, and `hold_reason` passed through for the console.

## Order of writes, which is load-bearing

`block_records` → `positions` → `orders` → `trades` → `rejections` →
`equity_snapshots`.

The snapshot is last because its `open_position_count` and `realised_pnl_cum` are read
back **out of the store** once this tick's rows have landed. `peak_equity` is likewise
the running maximum read from storage, never recomputed from `state`: `state` is fresh
every tick and has never seen the series, so an engine taking the maximum of this tick
alone reports a peak equal to the current equity, a drawdown of permanently zero, and a
breaker that never fires on a drawdown again.

**Within `positions` and `orders` the publisher order is chain order, and it decides
which row survives the upsert.** Three engines publish orders and two publish positions,
and the store upserts on `userref` and `position_id`, so the row engine 19 writes *last*
is the stored state.

- **positions: 21, then 22.** Engine 21 marks every open position and engine 22 closes
  the ones that hit a barrier, both on the same tick and both for the same
  `position_id`. Engine 22 runs after 21, so closed must win. The other order stores a
  position closed this tick as open with a mark on it — a row the console renders as
  live and `safety` counts towards its escalation precondition.
- **orders: 18, then 21, then 22.** An entry engine 18 placed and engine 21 immediately
  cancelled must end as cancelled. Written the other way it is stored as resting, which
  is a live post-only buy to everything that reads the table, and invariant 8 exists
  for exactly that order.

**An open position with no mark writes no equity row at all.** `positions_value` and
`unrealised_pnl` absent means engine 21 could not take a mark this tick — spec 92 has it
publish them absent, never zero — and `equity = cash + 0` would drop the position's whole
value out of that tick of the series. On a fully invested account that is a drawdown
approaching 100% against a `safety.max_drawdown_pct` of 0.10, so the account freezes over
a missing quote. The count that decides comes from `store.count_open_positions()` after
this tick's positions have landed: with nothing open, an absent mark is not a missing
mark and the row stands on cash alone. The skip names itself in
`equity_skipped_reason`, because a silent gap in the equity curve is indistinguishable
from a silent bug.

## The exit-cycle equity row

Operator ruling 2026-09-17 on C's Q-C1; specs 113 (B) and 114 (C). **On a tick where
engine 22 closed positions the equity row describes the account *after* those sales**, and
engine 19 builds it by filtering and summing facts other engines published, doing no
arithmetic on account figures of its own:

- **positions value and unrealised PnL** — engine 21's position rows, minus every
  `position_id` that appears in `state["exit"]["positions"]` as closed, summing the
  remaining rows' `value` and `unrealised_pnl`;
- **cash** — engine 1's start-of-tick balance in the reporting currency, plus the
  `net_proceeds` of every row in `state["exit"]["closed_trades"]`;
- **`cash_source = 'after_exit'`**. On every other tick the row is built from engine 1's
  balance and engine 21's totals exactly as before, and says `'cycle_start'`.

Before the ruling the exit tick's row mixed three moments that never coexisted: cash from
engine 1 at the start of the tick, positions value from engine 21 before the sale, and the
open-position count from the store after it. On C's stop leg it read equity 4945.02 with 0
open positions beside a positions value of 3281.10, against a true 4938.79, and on the
target leg it moved `peak_equity` to a figure the account never held. The criterion
`equity_row_never_values_positions_it_does_not_hold` is the observable form of it.

**No engine reads another engine's valuation method.** An earlier design had engine 22
subtract engine 21's marks and was withdrawn for exactly that coupling: engine 22's figure
would have changed silently whenever engine 21's method did. `value` and `net_proceeds`
are each a fact about something their publisher did.

**`value` and `net_proceeds` are payload facts, not columns.** `_Row` is `extra="forbid"`,
so engine 19 takes each off its own copy of the row before validating the stored row.
Between specs 113 and 114 it did not, the validation raised, contract rule 7 turned that
into an `ERROR`, and **the whole tick went unrecorded** — positions, orders, trades, block
records and equity alike. Neither figure became a column, because the store can always
recompute both from columns it already keeps.

**Three things make the exit tick write no row**, and each is the fail-closed reading of a
hole that would otherwise look like a complete row:

- **a remaining position with no `value` or `unrealised_pnl`** — the operator's first
  concern. Summing only the rows that carry a mark gives the account minus one holding: a
  plausible row that is short by a whole position. An absent *total* does this already on
  an ordinary tick and filtering must not become a way around it. A **closed** position
  with no mark is dropped and blocks nothing, which matters because the tick that sells a
  position is the tick its quote is most likely to be missing;
- **engine 21's remaining rows not covering what the account still holds**, counted from
  the store after this tick's rows landed — the same hole arriving through a position
  engine 21 never published;
- **a closed trade with no `net_proceeds`** — a sale whose proceeds are absent is not a
  sale that paid nothing.

If engine 22 closed positions but engine 1 published no balance — the outage liquidation —
there is no row, exactly as on any other tick with no balance.

**`positions.hold_reason` is written on every position engine 21 marked, and set to
`None` on every tick that did not hold.** The clearing is the load-bearing half:
`write_position` upserts every column, so writing null is what removes the previous
tick's reason, and skipping the assignment instead would render an hour-old hold forever
— reporting a paused manage chain over one running normally.

## What it deliberately does not do

- It is **not a gate**. It never blocks and never sets `blocks_trading`.
- It reads no clock. `context.now` is already stamped, which is what makes replay
  faithful.
- It constructs no client and imports no other engine.
- It does not catch the `IntegrityError` from `ux_block_records_primary`. A second
  primary row for one tick is a defect in this engine, and contract rule 7 turning it
  into an `ERROR` result is the visible symptom that catching it would suppress.
- It does not infer the bar boundary and does not write `state["system"]`.

## Tests

`tests/engines/test_memory.py` — the block record on every blocked tick (spec 49).
`tests/engines/test_memory_rows.py` — the five live-row tables, including the
absent-is-not-zero case for each (spec 50), what engines 18 and 22 publish (spec 98), and
the errored-engine tick, one test of it through the real orchestrator and a real raising
engine (spec 104).

Both were proved capable of failing by mutation rather than by review; the mutations
and the messages they produced are in `docs/build-log/phase-4/c-interface.md` and, for
specs 98 and 104, `docs/build-log/phase-6/c-interface.md`.
