# 26 — Engine 1 `exchange`

**Owner:** A — Platform

## Goal

The first engine in the guard chain: account state, balances, the live fee tier and the live pair
rules, fetched through spec 25's client and published into `state` for every engine downstream.

## Implementation

1. Create `src/acsoe/engines/exchange/` with the three files every engine directory carries:
   `engine.py`, `contracts.py`, `README.md`.
2. `engine.py` subclasses `BaseEngine` with `name = "exchange"`, `number = 1`, `is_gate = False`,
   in the **guard** chain — matching the registry table in `context/engine-contracts.md` exactly,
   because `is_gate_matches_registry` asserts it.
3. Publish into `state["exchange"]`: balances per currency, the fee tier from `TradeVolume`, and
   pair rules from `AssetPairs` — `ordermin`, `costmin`, tick size, precision.
4. **Retain last-known-good values** for the emergency-liquidation path, per the seam row in
   `ownership.md`. They are retained *only* for that use, and this spec does not consume them;
   engines 21 and 22 do, in Phase 6.
5. Reads the clock only through `context.now`, and the network only through
   `context.clients.kraken`. Never constructs a client.
6. Register the engine in `src/acsoe/bootstrap.py` — **that file is lead-only. Batch the request
   with specs 27 to 29 and hand it to the lead**, per ownership rule 2.
7. Write `README.md`: what it does, inputs, outputs, and that it is not a gate.

## Scope Limits

- Do **not** write to `bootstrap.py` or `core/`. Registration is a lead task.
- Do **not** make this a gate. Engine 1 reports; engine 4 `data_guard` decides.
- Do **not** hardcode any exchange-supplied value, and do **not** substitute a default when a
  fetch fails — paper mode has narrow explicit fallbacks under rule 2 of
  `trading-invariants.md`, and inventing a new one here is out of scope.
- Do **not** place an order or mutate anything on the exchange.
- Do **not** read or write the `commands` table.

## Check When Done

- The engine runs in the guard chain and populates `state["exchange"]` against C's fake client.
- Fee tier and `ordermin` in `state` change when the fixture changes — proving they are fetched.
- A failed fetch produces a documented, tested outcome rather than a silent default.
- `is_gate_matches_registry` still passes with the engine registered.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
