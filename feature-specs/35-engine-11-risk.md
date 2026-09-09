# 35 — Engine 11 `risk`

**Owner:** B — Store and trading

**Phase:** 3 — Economics. **Built concurrently during Phase 2** against a mocked Kraken client, by
operator decision on 2026-09-09. It does **not** count toward Phase 2's gate, and Phase 3 stays
closed until Phase 2 is green and this engine is wired to A's real client.

## Goal

The gate that sizes a position and refuses one that cannot be placed legitimately — in particular,
one below the exchange's own minimum.

## Implementation

1. Create `src/acsoe/engines/risk/` — `engine.py`, `contracts.py`, `README.md`.
   `name = "risk"`, `number = 11`, **`is_gate = True`**, **opportunity** chain, stage 3, per the
   registry table.
2. Size the position from the configured risk parameters and the balance published by A's engine 1
   into `state["exchange"]`.
3. **A position below `ordermin` is rejected, not rounded up.** This is the behaviour the Phase 3
   criterion names explicitly. Rounding up to reach the minimum silently increases the money at
   risk beyond what the sizing decided, which is the opposite of what a risk gate is for. Reject
   with an operator-readable reason naming the shortfall.
4. `ordermin`, `costmin`, tick size and precision come from `AssetPairs` at runtime through the
   client contract. **Never a constant, and never a config key** — `AGENTS.md` is explicit that any
   remembered order minimum is stale.
5. Money is `Decimal` throughout. Float drift in an order quantity produces a Kraken rejection that
   is miserable to diagnose, which is the reason for the Phase 0 Decimal decision.
6. **Agree the pair-rule shape with A up front** against `src/acsoe/clients/kraken/contracts.py`,
   then build against a mock. Do not wait, and do not write in A's directory.
7. Batch the `bootstrap.py` registration request to the lead.

## Scope Limits

- Do **not** round a sub-minimum position up to the minimum, under any flag or config key.
- Do **not** hardcode `ordermin`, `costmin`, a tick size or a precision.
- Do **not** place, size against, or reference a live order. Execution is engine 18, Phase 6.
- Do **not** implement the universe filter; engine 7 `scout` stays in Phase 3 proper.
- Do **not** write into `clients/kraken/`, `core/`, or `bootstrap.py`.
- Do **not** register this engine or treat Phase 3 as started.

## Check When Done

- **A block test and a pass test.** A position one increment below `ordermin` is rejected; one at
  or above it passes.
- The rejection test asserts the position was **rejected**, not resized — the returned quantity is
  absent, not bumped. A test that only checked "did not place" would pass against a rounding
  implementation.
- Changing `ordermin` in the mock changes which sizes are rejected, proving the value is fetched.
- No `float` appears in any sizing path.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
