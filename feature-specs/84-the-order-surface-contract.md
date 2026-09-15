# 84 — The order surface: one contract for paper and live

**Owner:** A — Platform

**Phase:** 6. `clients/kraken/` is A's.

## Goal

Engines 18, 21 and 22 place, cancel and query orders through one typed surface on
`context.clients.kraken`, identical in paper and live, so the same engine code runs in every mode
and the mode difference lives in the client layer (`architecture-context.md`, Modes). Today the
Kraken client has no order method at all.

## Implementation

1. `clients/kraken/contracts.py`: pydantic models, money as `Money`, every one `extra="forbid"`:
   - `OrderRequest` — `pair`, `side` (`buy`/`sell`), `order_type` (`limit`/`market`), `qty`,
     `limit_price` (required for `limit`, absent for `market`), `post_only: bool`, `userref: int`
     (Kraken's signed 32-bit range, refused outside it).
   - `OrderAck` — `userref`, `order_id`, `status` (`resting`, `filled`, `rejected`), `reason`
     when rejected (a post-only order that would cross is a rejection naming that cause).
   - `OrderState` — `userref`, `order_id`, `status` (`resting`, `filled`, `cancelled`,
     `rejected`, `expired`), `filled_qty`, `avg_fill_price`, `fee`, `closed_at`.
   - `OrderClientProtocol` — `add_order(request) -> OrderAck`, `cancel_order(userref) -> OrderState`,
     `query_orders(userrefs) -> tuple[OrderState, ...]`, `open_orders() -> tuple[OrderState, ...]`.
     Async, like every other call on the client.
2. `clients/kraken/client.py` and `rest.py`: the four methods on the **live** client **raise
   `KrakenUnavailableError` naming Phase 8** and make no request. Live order placement is Phase 8
   work; a live client that refuses is fail-closed, and one that half-works is not.
3. A test that the live refusal names the method and makes zero transport calls, with a counting
   transport — a double that can exhibit the property under test.
4. Hand the contract to B by message the moment it lands; spec 88 implements the paper side of it.

## Scope Limits

- Do **not** implement `AddOrder`, `CancelOrder` or `QueryOrders` against Kraken. Phase 8.
- Do **not** write a fill rule. Fills are the simulator's (spec 88, B).
- Do **not** add a fourth client to `Clients`; that is a `core/` change and is not needed.
- Do **not** hardcode any fee, minimum or precision in the models.

## Check When Done

- The live refusal test red when the refusal is replaced by a transport call (mutation recorded).
- `userref` bound refused at both edges, asserting the constraint message, not the field name.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
