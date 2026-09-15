# 98 — Engine 19 records what engines 18 and 22 publish

**Owner:** C — Interface and models

**Phase:** 6. `engines/memory/` is C's.

## Goal

Engine 19 already reads `positions`, `orders`, `positions_value`, `unrealised_pnl` and
`hold_reason` from engine 21 and `closed_trades` from engine 22. It does not read the entry order
engine 18 places (opportunity chain, same tick) or the exit orders and closed positions engine 22
publishes, so under the single-writer rule those rows would never reach the store. At the end of
this spec every row 18, 21 and 22 publish is recorded, once, on the tick it happened.

## Implementation

1. `engines/memory/contracts.py`: `EXECUTION_KEY = "execution"` and exit's `ORDERS_FIELD` and
   `POSITIONS_FIELD` reads, each line naming its owner, as the file already does.
2. `engines/memory/engine.py`: orders from 18, 21 and 22; positions from 21 and 22. The write order
   stays load-bearing — positions and trades before the equity snapshot — and orders from 18 are
   written before 21's, so a placement and its same-tick cancel land in that order.
3. **Absent means nothing to record**, as it already does: engine 18 absent on the fourteen ticks
   in fifteen with no bar, and absent on a bar tick where the chain stopped earlier.
4. An upsert on `userref` and `position_id` is the store's existing behaviour; a row published by
   two engines on one tick (a placement 21 immediately cancels) is written twice in order and the
   final row is the later state. Test it rather than assume it.
5. Agree the exact payload shapes with B **by message before either side lands** (specs 91, 93) —
   a seam agreed by message needs one test with no double on either side, per code-standards, so
   one test drives the real engines 18, 21, 22 and 19 once they exist and skips with a failing
   tripwire until they do.
6. Tests in `tests/engines/test_memory_rows.py`: each new source recorded; absent sources record
   nothing and no zero; the same-tick placement-then-cancel ordering.

## Scope Limits

- Do **not** record a rejection for anything 18, 21 or 22 publishes. None of them is a gate.
- Do **not** compute a position, a fill, a price or a PnL. Engine 19 records.
- No schema change.

## Check When Done

- Mutations observed red, killing test named: execution's orders not read; exit's positions not
  read; orders written after positions (if order is load-bearing for a read), 18 after 21.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
