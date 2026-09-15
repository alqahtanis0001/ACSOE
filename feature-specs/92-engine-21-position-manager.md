# 92 — Engine 21 `position_manager`

**Owner:** B — Store and trading

**Phase:** 6. `engines/position_manager/` is B's.

## Goal

Every tick, in every mode, engine 21 turns resting entries into positions when they fill, cancels
entries that outran their window, marks every open position to the market, decides which positions
have reached a barrier, holds exits when `data_guard` rejected the tick's data, and cancels every
resting entry when `close_intent` is set — publishing everything engine 19 records and the one flag
the orchestrator reads.

## Implementation

1. `engines/position_manager/engine.py`, `contracts.py`, `README.md`. `name = "position_manager"`,
   `number = 21`, `is_gate = False`. Manage chain, first.
2. **Inputs.** Resting entries and open positions from the store (`resting_orders(intent=entry)`,
   `open_positions()`), because on fourteen ticks in fifteen the opportunity chain did not run.
   This tick's placement from `state["execution"]["orders"]` when present. Fills through
   `context.clients.kraken.query_orders`. Prices from `state["market_sensor"]["quotes"]` (mark at
   the **bid**, what a sale would receive) and `["trade_ranges"]` (spec 85).
3. **Entry filled** → a new open position: `entry_price` the fill price; `target_price` =
   `entry_price × (1 + barriers.target_pct)`; `stop_price` = `entry_price × (1 − barriers.stop_pct)`;
   `timeout_at` = fill time + `barriers.timeout_bars × timeframes.decision_bar_s`. **Lead ruling,
   flagged to the operator as overturnable:** barriers are measured from the **fill**, not from
   the decision bar's close the label was measured from, because engine 11 sized the quantity
   against the stop distance from the price actually paid, and a stop placed from another price
   risks a different amount than the one approved. The README states the difference from the label.
4. **Entry unfilled past `trading.entry_unfilled_window_s`** from `placed_at` → `cancel_order`,
   status `cancelled`, candidate abandoned. **Never replaced and never chased.** This runs on a
   `data_guard`-blocked tick as well — invariant 8: it is a decision about elapsed time, needs no
   market data, and reduces exposure.
5. **Barrier decision**, per open position, unless held: stop touched when the tick's trade `low`
   ≤ `stop_price`; target touched when `high` ≥ `target_price`; **both in one tick → stop**, the
   same both-barriers rule the labels use; timeout when `context.now` ≥ `timeout_at`. Published as
   `triggered: [{"position_id", "barrier"}]`. Engine 22 acts on it.
6. **The hold.** When `state["trading_blocked_by"] == "data_guard"` and `close_intent` is not set:
   no barrier is decided, `triggered` is empty, `hold_reason` names why (e.g.
   `data_guard_blocked`). A block by any other engine does not hold. `hold_reason` is null on every
   tick that did not hold, and null during a liquidation, which never holds.
7. **`close_intent` set** → cancel **every** resting entry, regardless of the window, before
   anything else. `entry_orders_cancelled` is `True` only when none remains after this tick's
   cancels (a failed cancel leaves it `False` and the orchestrator retries next tick). Absent or
   false always means "not finished".
8. **Publishes** `{"positions", "orders", "positions_value", "unrealised_pnl", "triggered",
   "hold_reason", "entry_orders_cancelled"}`, money as exact decimal strings; `positions` and
   `orders` carry the full row payloads engine 19's contracts already read (`POSITIONS_FIELD`,
   `ORDERS_FIELD`, `POSITIONS_VALUE_FIELD`, `UNREALISED_PNL_FIELD`, `HOLD_REASON_FIELD`).
   `positions_value` and `unrealised_pnl` are **absent**, never zero, on a tick where a mark could
   not be taken — engine 19 skips an equity row rather than recording a false one.
9. Reason and hold codes to C by message (spec 99).
10. Tests in `tests/engines/test_position_manager.py`: each step's block and pass pair differing in
    one input; a stop and target touched in one tick resolves to stop; the hold on `data_guard` and
    the absence of a hold on a `cost` block; the stale-entry cancel still happening during a hold;
    `close_intent` cancelling a fresh entry inside its window; `entry_orders_cancelled` false when a
    cancel fails. Every upstream `state` from the real engines.

## Scope Limits

- Do **not** place an exit. Engine 22 places exits.
- Do **not** write a relational row. Engine 19 records.
- Do **not** read last tick's decisions from `state`. The store.
- Do **not** hold on any blocker other than `data_guard`, and never hold a liquidation.
- Do **not** assert three concurrent positions in a test at the committed balance.

## Check When Done

- Mutations observed red, killing test named: both-barriers resolves to target; hold on any
  blocker; stale-entry cancel suppressed during a hold; `entry_orders_cancelled` true with an entry
  still resting.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
