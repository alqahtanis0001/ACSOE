# 34 — Engine 10 `cost`

**Owner:** B — Store and trading

**Phase:** 3 — Economics. **Built concurrently during Phase 2** against a mocked Kraken client, by
operator decision on 2026-09-09. It does **not** count toward Phase 2's gate, and Phase 3 stays
closed until Phase 2 is green and this engine is wired to A's real client.

## Goal

The gate that refuses a trade whose expected move does not survive its own friction: fees from the
live tier, spread, and slippage, netted against the move and compared to a hurdle.

## Implementation

1. Create `src/acsoe/engines/cost/` — `engine.py`, `contracts.py`, `README.md`.
   `name = "cost"`, `number = 10`, **`is_gate = True`**, **opportunity** chain, stage 3, exactly as
   the registry table in `context/engine-contracts.md` has it.
2. **Compute net edge from the fee tier the client returns, never from a constant.** The tier
   arrives through `context.clients.kraken` and reaches this engine as `state["exchange"]`'s fee
   tier, published by A's engine 1. Reference friction is ~1.25% round trip at tier 1 and ~0.65% at
   tier 3 — those are *locked decisions used for reasoning about the design*, and they are not
   values to write into the code.
3. Block when net edge falls below the configured hurdle, with an operator-readable reason:
   "Net edge −0.21% after fees", never `cost_gate_fail`.
4. Money is `Decimal` throughout. A float in a sizing or edge calculation is a defect.
5. **Agree the fee-tier and pair-rule shape with A up front**, against
   `src/acsoe/clients/kraken/contracts.py` from spec 25, then build against a mock of it. Do not
   wait for A's client to land and do not write in A's directory.
6. The spread half of this engine cannot be backtested from the historical archives, which are
   OHLCVT only. Say so in the `README.md`.
7. Batch the `bootstrap.py` registration request to the lead; that file is lead-only.

## Scope Limits

- Do **not** hardcode a fee, a tier threshold, or a spread. Rule 2 of `trading-invariants.md`: if a
  value cannot be fetched, live mode blocks the trade.
- Do **not** weaken or bypass the hurdle to make a test pass. Invariants outrank tests.
- Do **not** write into `src/acsoe/clients/kraken/`, `core/`, or `bootstrap.py`.
- Do **not** implement the universe filter — that is engine 7 `scout`, which stays in Phase 3
  proper because it needs a real tradable universe.
- Do **not** register this engine or claim Phase 3 is started. It is Phase 2 concurrent work.
- Do **not** let this engine's presence change any Phase 2 criterion.

## Check When Done

- **A block test and a pass test**, both required for a gate. Net edge below the hurdle blocks;
  above it passes.
- A test proving the fee comes from the client: change the tier the mock returns, and the computed
  net edge changes. A constant would pass a single-value test and fail this one.
- The blocking reason is operator prose carrying the actual number.
- No `float` appears in any edge or sizing path.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
