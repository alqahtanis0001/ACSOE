# 88 — The fill simulator and the paper ledger

**Owner:** B — Store and trading

**Phase:** 6. Named in the Phase 6 row and owned by nobody until this phase; assigned to B by
operator ruling 2026-09-16 (spec 80 step 3 records it in `ownership.md` before this is built).

> **RULED BY THE OPERATOR 2026-09-16 — the simulator's home.** The simulator is B's and lives in
> the client layer as a **paper broker**, `src/acsoe/clients/paper/`, implementing A's order
> surface (spec 84) and wrapping the real Kraken client in paper mode (A wires it, spec 86).
> Engines 18, 21 and 22 call `context.clients.kraken.add_order / cancel_order / query_orders`
> identically in every mode. This corrects the operator's earlier ruling that it live under
> `engines/execution/`, which contract rule 3 forbids: a resting post-only entry fills on a later
> tick that only engine 21 sees, and neither 21 nor 22 may import another engine. The correction
> is the operator's own and is recorded as such in the tracker (spec 80).
>
> **RULED BY THE OPERATOR 2026-09-16 — what balance paper mode spends.** In paper mode the balance
> is **always** the paper ledger: `paper.starting_balances` adjusted by every recorded fill,
> whether or not the real fetch works, because no simulated fill spends the real account.
> Invariant 2's table is reworded to say so (spec 80). Recorded as a defect found in planning:
> the invariant promised an adjustment nothing implemented, so engine 11 sized against cash an
> earlier paper fill had already spent and engine 19's equity counted that cash twice.

## Goal

In paper mode an order goes to a simulator that fills it by a stated, pessimistic rule against
recorded market data, never mutating the exchange, and the account the rest of the system reads is
the paper ledger those fills produce.

## Implementation

*Written against the recommended home. If the operator rules otherwise, this spec is rewritten
before it is claimed.*

1. `clients/paper/broker.py`: `PaperBroker(real: KrakenClient-like, store: StoreClient, config)`.
   Delegates every read call (`asset_pairs`, `trade_volume`, `order_book`, quotes, stream,
   last-known-good retention) to `real`. Implements spec 84's `OrderClientProtocol` and
   `balance()`.
2. **No in-memory order book of its own that a restart can lose.** Resting orders are the store's
   `orders` rows (written by engine 19); the broker reads them. What it accepted this tick but 19
   has not yet recorded it holds only until the tick's end, keyed by `userref`.
3. `clients/paper/fills.py`, pure functions, no clock, no I/O:
   - **Post-only placement.** A buy limit at or above the best ask is **rejected** with
     `post_only_would_cross` — Kraken cancels such an order and so does the simulator.
   - **A resting post-only buy at L fills in full at L only when a trade printed strictly below
     L** after the order was placed. Touching L is not a fill: queue position is unknown and the
     pessimistic reading cannot flatter the strategy. Partial fills are not simulated, and the
     README says so.
   - **Where the broker sees trades.** A client cannot read `state`, so it cannot read spec 85's
     `trade_ranges`. It does not need to: engine 3 drains trades through `clients.kraken`, which in
     paper mode *is* the broker, so the broker observes the same drained tuple engine 3 builds
     `trade_ranges` from and the two cannot disagree about which trades happened. Trades drained
     before an order's `placed_at` never fill it — engine 18 places after engine 3 has drained on
     the same tick. A test asserts the broker and engine 3 agree on the range for one tick.
   - **A market sell walks the bid side** of the order book fetched that tick, level by level,
     for the full quantity; fill price is the volume-weighted average. If the fetched depth cannot
     absorb the quantity, the remainder is priced at the worst fetched level and the fill records
     `book_depth_exhausted`.
   - Fees: maker rate on a post-only fill, taker on a market fill, from the fee tier the real
     client returns **that tick**. No fee tier, no fill priced — see Scope Limits.
4. `balance()` in paper mode: the paper ledger — `paper.starting_balances` minus every filled
   entry's notional and fee, plus every filled exit's proceeds less fee, from the store's `orders`
   rows, per currency, exact `Decimal`. Reads money from the store as strings; never `SUM()` in SQL
   over a money column (code-standards).
5. `README.md` in `clients/paper/`: every fill rule above and why each is the pessimistic reading.
6. Tests in `tests/clients/paper/`: each fill rule's boundary (a trade exactly at L does not fill;
   one tick below does); post-only cross rejected; bid walk against a two-level and a thin book;
   ledger after a round trip equals starting balance plus realised PnL to the cent; a restart
   rebuilds the same ledger from the store. Hypothesis over book walks and ledger arithmetic.

## Scope Limits

- Do **not** mutate the exchange in any mode. No transport call from any order method.
- Do **not** fill a resting order on a touch, a quote, or a mid.
- Do **not** invent a fee. If a fill needs a fee and no fee tier is available (a liquidation during
  an outage), stop and escalate with the options — do not choose one.
- Do **not** write any relational row. Engine 19 is the single writer.
- Do **not** simulate live-only behaviour (expiry, partial fills, rate limits) beyond what is here.

## Check When Done

- Mutations observed red, killing test named for each: fill on touch; post-only cross accepted;
  bid walk using the ask side; ledger adding an entry's notional instead of subtracting it.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
