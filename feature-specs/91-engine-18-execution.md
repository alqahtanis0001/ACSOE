# 91 — Engine 18 `execution`

**Owner:** B — Store and trading

**Phase:** 6. `engines/execution/` is B's.

> **RULED BY THE OPERATOR 2026-09-16 — the execution offset bandit is deferred to Phase 7.**
> Phase 6 places every entry **at the best bid**: joining the bid never crosses while the spread
> is positive, and `data_guard` already refuses a crossed book. The bandit is a Locked Decision
> that is absent from the Phase 6 row, needs a table that does not exist, and learns from a fill
> history that does not exist either. The README states the fixed rule as a **recorded absence**,
> so nobody reads best-bid placement as a choice someone defended.

## Goal

On a tick where every gate passed, engine 18 places exactly one post-only limit buy for the
approved quantity, idempotently, through the order surface, and publishes the order for engine 19
to record. It never places a market entry, never chases, and never places without checking the
`userref` first.

## Implementation

1. `engines/execution/engine.py`, `contracts.py`, `README.md`. `name = "execution"`, `number = 18`,
   `is_gate = False`.
2. Reads: `state["scout"]["pair"]`; `state["risk"]` `qty` (absent means no approval — raise, never
   default); `state["market_sensor"]["quotes"][pair]` bid; pair rules from `state["exchange"]` for
   `pair_decimals`. Under spec 90 option 2, reads engine 16's intent instead.
3. **`userref`** is deterministic from `(pair, closed_bar_ts)`, in Kraken's signed 32-bit range,
   so a re-run of the same tick produces the same `userref`. Before placing: `store.order_by_userref`
   and the client's `query_orders`. Found and for this pair and bar: publish it, place nothing.
   Found for a different pair: raise — a collision is a defect, not a retry.
4. Price: the best bid, rounded **down** to `pair_decimals`. `add_order` with `post_only=True`.
5. Publishes `{"pair", "userref", "orders": [OrderRow-shaped payload], "placed": bool,
   "reason_code"}`; `orders` carries the row engine 19 writes — status `resting` or `rejected`,
   `intent: entry`, `oflags: post`, `placed_at` from `context.now`. A rejection (post-only would
   cross) is published and recorded, and the candidate is abandoned on this tick. Reason codes to C
   (spec 99): at least `entry_placed`, `entry_already_placed`, `post_only_would_cross`.
6. A `PASS` never follows a placement — `OK` with `placed: true` — so the orchestrator does not
   read a placed order as "nothing to do".
7. Tests in `tests/engines/test_execution.py`: placement against the paper broker at tier 3 through
   real upstream engines' `state`; the same tick twice places once; a cross rejected and recorded;
   an absent `qty` raises; a market order is never constructed (assert on the request type).

## Scope Limits

- Do **not** place a market or taker entry, under any condition or flag. Invariant 8.
- Do **not** replace, re-price or re-place an entry. Cancelling a stale one is engine 21's.
- Do **not** re-size. The quantity is engine 11's.
- Do **not** write a relational row. Engine 19 records.
- Do **not** build the bandit unless the operator rules it into this phase.

## Check When Done

- Mutations observed red, killing test named: the `userref` check removed; price rounded up;
  `post_only` false.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
