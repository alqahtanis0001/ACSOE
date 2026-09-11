# 50 — Engine 19 `memory`, part 2: equity, positions, orders, trades and rejections

**Owner:** C — Interface and models

**Phase:** 4.

## Goal

Engine 19 writes the remaining five tables `safety`, the console and Phase 7 attribution
read: `equity_snapshots`, `positions`, `orders`, `trades` and `rejections`. After this spec
`safety` reading **live** rows reaches the same six totals it reached against the Phase 0
seed, and the forward dependency Phase 3 was forced to seed around is closed.

## Implementation

1. **`equity_snapshots`, one row per tick.** Currency is `trading.base_reporting_currency`.
   `equity`, `peak_equity`, `cash`, `positions_value`, `unrealised_pnl`, `realised_pnl_cum`
   are exact decimal strings; `open_position_count` is an integer. `peak_equity` is the
   running maximum **read from the store**, never recomputed from `state`, which is fresh
   every tick. A tick with no equity information available writes no row rather than a zero —
   a zero equity row is a 100% drawdown and trips the breaker.
2. **`positions` and `orders`.** Engine 19 persists what engines 18, 21 and 22 publish in
   `state`. Those engines are Phase 6; until they exist the keys are absent and engine 19
   writes nothing for them. **Absent must mean nothing-to-record, never record-a-zero.**
3. **`trades`.** One row per closed round trip, written when the manage chain reports a
   close. Phase 6 produces those closes; the write path and its tests exist now.
4. **`rejections`.** One row per rejected candidate: `pair`, `rejected_by`, `reason_code`,
   `reason`, the economics columns where the blocking engine published them, and
   `(run_id, cycle_id)` so it joins to the block record for the tick. Invariant 12: a
   rejection that does not reach storage counts as a defect equal to a lost trade.
5. `tests/engines/test_memory_rows.py` — C tests, including the absent-is-not-zero case for
   each of the five tables.

## The seam this spec closes, and how to prove it

Phase 3 proved `safety` against the Phase 0 seed because engine 19 did not exist. The proof
that the seam is real is **the same six numbers from live rows**: drawdown, losing-trade
streak, error blocks, outage ticks, open positions, resting orders. Drive real ticks, let
engine 19 write, then read the six inputs of `safety` and compare against the totals of the
seed. Equal numbers from two independent producers is the assertion; the tables being
non-empty is not.

## Rules this spec is held to

- **Every assertion must be proven capable of failing**, with the mutation and the red message
  recorded in `docs/build-log/phase-4/c-interface.md`. Name at least: `peak_equity`
  recomputed from the current tick instead of read from the store; a zero equity row written
  when no equity is available; a rejection written without its `reason_code`.
- Money is `Decimal` end to end and an exact decimal string in SQLite. The money columns are
  declared `ANY` with a `typeof` CHECK precisely so a float is refused rather than quietly
  stringified. Do not defeat that by formatting a float.
- **A handler that cannot distinguish two situations will silently pick the wrong one.** The
  key is absent because the engine is Phase 6, and the key is absent because the engine failed
  this tick, are two different facts. Do not conflate them into one broad `except`.

## Scope Limits

- Do **not** implement engines 18, 21 or 22, or simulate a fill. Phase 6 owns those. This spec
  persists what they will publish and is tested against fabricated `state` payloads built
  from the **real** contracts, never from an invented shape.
- Do **not** write `block_records` here — spec 49.
- Do **not** change the schema.
- Do **not** compute a metric, train anything, or write to `leaderboard`.

## Check When Done

- `memory_writes_safety_inputs_live` and `rejections_survive_restart` are PASS.
- The six totals from live rows equal the six from the Phase 0 seed, and that comparison has
  been observed to fail against a broken writer.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 4`
