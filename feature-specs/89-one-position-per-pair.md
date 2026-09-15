# 89 — Engine 11 refuses a second position, or a second entry, on one pair

**Owner:** B — Store and trading

**Phase:** 6. `engines/risk/` is B's.

## Goal

Invariant 6 says one open position per pair. **Nothing in `src/` enforces it** — engine 11 counts
open positions against `trading.max_concurrent_positions` and never asks which pair they are on,
and engine 7 does not look. It has been unreachable because nothing could open a position. Phase
6 makes it reachable, so the gate lands before engine 18 does.

## Implementation

1. `engines/risk/engine.py`: block when the candidate pair already has an **open position** or a
   **resting entry order** in the store. The resting entry counts for the same reason it counts for
   `safety`'s escalation: a post-only buy on the book is a position that has not filled yet.
2. Reason codes `position_open_on_pair` and `entry_resting_on_pair`, each a `Final` in
   `contracts.py`; a reason sentence naming the pair and the existing `position_id` or `userref`.
3. Store reads through existing `StoreClient` methods (`open_positions`, `resting_orders(intent=
   entry)`); if a per-pair read is needed, add it to the store with its own test, no migration.
4. `README.md` updated.
5. Tests in `tests/engines/test_risk.py`: block on an open position, block on a resting entry, pass
   when the only open position is on another pair, pass when the pair's previous position is
   closed. Every `state` from engines 1 and 3's real output, per the Phase 3 ruling.
6. Tell C the two codes by message for `REASON_PROSE` (spec 99).

## Scope Limits

- Do **not** move the check into engine 7, 16 or 18. It is a gate's refusal and only a gate may
  refuse (invariant 3, `is_gate`).
- Do **not** change sizing, the concurrency count, or the balance fallback.
- No schema change.

## Check When Done

- Each block test differs from its pass test in one input. Mutations observed red: the pair
  comparison removed; resting entries not counted.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
