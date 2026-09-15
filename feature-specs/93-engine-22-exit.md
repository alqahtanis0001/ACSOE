# 93 — Engine 22 `exit`

**Owner:** B — Store and trading

**Phase:** 6. `engines/exit/` is B's.

## Goal

Every tick, engine 22 exits the positions engine 21 triggered, and when `close_intent` is set it
exits **every** open position as a taker regardless of the guard and regardless of a failed fetch —
invariant 14 — publishing the orders, the closed positions, the closed trades and the one flag the
orchestrator reads.

## Implementation

1. `engines/exit/engine.py`, `contracts.py`, `README.md`. `name = "exit"`, `number = 22`,
   `is_gate = False`. Manage chain, after 21, before 19.
2. **Ordinary tick.** For each entry in `state["position_manager"]["triggered"]`: a market sell for
   the position's full quantity through `context.clients.kraken.add_order`, `userref` deterministic
   from `(position_id, "exit")` and checked first (invariant 8). All exits are taker in Phase 6;
   invariant 8 *permits* a maker target exit and does not require one, and friction already
   assumes a taker exit. The README says so.
3. **The hold.** When `trading_blocked_by == "data_guard"` and `close_intent` is not set, place no
   exit of any kind, even if a trigger is somehow present. Belt and braces with engine 21, because
   a trigger computed from rejected data is a fabricated trigger acting on real money.
4. **Liquidation (`close_intent` set).** Every open position in the store, as a market sell,
   whatever `data_guard` said. Quantity rounded **down** to `lot_decimals` from pair rules; if this
   tick's `AssetPairs` failed, from `clients.kraken.last_known_good_asset_pairs()` **past its TTL** —
   the only place in the system that may read it. Every tolerated failure is recorded on the trade's
   `fallbacks_used` (`asset_pairs_last_known_good`, `balance_last_known_good`, and whatever the fill
   records). `userref` idempotency still applies. `positions_closed` is `True` only when no open
   position remains after this tick's exits.
5. **A filled exit** → the position closed (`status: closed`, `closed_at`, `trade_id`) and a trade:
   `exit_price`, both fees, `outcome` (`target`, `stop`, `timeout`, or `liquidation` — all four
   already in `TradeOutcome`), `realised_pnl` and `realised_pnl_pct` exact `Decimal`,
   `reporting_currency` from config, FX rates `1` only when quote equals the reporting currency
   (engine 11 refuses any other pair today, `no_fx_rate`).
6. **Publishes** `{"orders", "positions", "closed_trades", "positions_closed", "reason_code"}`.
   `closed_trades` is `CLOSED_TRADES_FIELD`, which engine 19 already reads; `orders` and
   `positions` are new reads for engine 19 (spec 98, C) — agree the shapes with C by message
   before either side lands.
7. Tests in `tests/engines/test_exit.py`: an exit per barrier; no exit on a `data_guard` tick with a
   triggered stop; the same position exited once `close_intent` is set; a liquidation with
   `data_guard` blocking **and** the balance fetch failing **and** `AssetPairs` failing, using the
   retained rules and recording each fallback; `positions_closed` false when an exit is rejected;
   the same tick twice exits once.

## Scope Limits

- Do **not** read `last_known_good_*` outside a liquidation.
- Do **not** open, add to, or re-enter a position. The override applies only to exiting.
- Do **not** round a quantity up, even to clear dust.
- Do **not** invent a fee when the fee tier is unavailable during a liquidation — escalate
  (spec 88's scope limit is the same one from the other side).
- Do **not** write a relational row. Engine 19 records.

## Check When Done

- Mutations observed red, killing test named: exit placed during a hold; liquidation held on
  `data_guard`; retained rules read outside a liquidation; `positions_closed` true with a position
  still open; quantity rounded up.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
