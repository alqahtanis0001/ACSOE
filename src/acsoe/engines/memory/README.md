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
| `state["scout"]["pair"]` | 7 `scout` (B) | the candidate the rejection is about |
| `state["<blocker>"]["reason_code"]` and its economics | the gate that refused | the `rejections` columns |
| `state["exchange"]["balances"]` | 1 `exchange` (A) | cash, and therefore whether an equity row can be written at all |
| `state["position_manager"]` | 21 (B), Phase 6 | positions, resting orders, position value, `hold_reason` |
| `state["exit"]["closed_trades"]` | 22 (B), Phase 6 | one `trades` row per closed round trip |

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
absent-is-not-zero case for each (spec 50).

Both were proved capable of failing by mutation rather than by review; the mutations
and the messages they produced are in `docs/build-log/phase-4/c-interface.md`.
