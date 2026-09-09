# 29 — Engine 4 `data_guard`

**Owner:** A — Platform

## Goal

The first real gate in the system: the engine that refuses to let the loop trade on data it does
not trust, and reports the block the outage counter is later derived from.

## Implementation

1. Create `src/acsoe/engines/data_guard/` — `engine.py`, `contracts.py`, `README.md`.
   `name = "data_guard"`, `number = 4`, **`is_gate = True`**, **guard** chain. The registry table
   in `engine-contracts.md` marks it `Y`, and `is_gate_matches_registry` asserts the match.
2. Block on each of the three conditions the phase criteria name: **stale data**, a **negative
   spread**, and a **missing candle**. Each returns `blocks_trading=True` with a reason written
   for an operator, not a log line.
3. `blocks_trading` without a reason must raise — that is already enforced by `core/contracts.py`
   and this engine must not work around it.
4. A block here does **not** stop the guard chain. `safety` still runs on the same tick, and every
   blocker is recorded — the orchestrator handles that; this engine simply reports honestly.
5. Thresholds come from `config/default.yaml`. **A key you need that does not exist is a request
   to the lead, not a literal in your engine** — only the lead adds a config key.
6. Write `README.md` covering, explicitly, what it blocks on and what it does not.
7. Batch the `bootstrap.py` registration request to the lead with specs 26 to 28.

## Scope Limits

- Do **not** weaken, bypass or add an escape hatch to this gate. `AGENTS.md`: invariants outrank
  tests, and a test that fails because a gate blocked is the test that is wrong.
- Do **not** write to `block_records`. Engine 19 `memory` is the single writer of relational rows
  and is Phase 4; this engine reports into `state` and the orchestrator records the blocker.
- Do **not** implement the outage counter or any `safety` behaviour — engine 17 is Phase 3.
- Do **not** add a config key yourself.
- Do **not** let a block stop data collection: recording continues through a block.

## Check When Done

- **One block test and one pass test for each of the three conditions** — six tests. A gate with
  only a happy path is incomplete, per the definition of done.
- Injected stale data, an injected negative spread and an injected missing candle each block with
  a distinct operator-readable reason.
- Clean data passes and does not set `trading_blocked_by`.
- On a tick where this blocks, a second guard engine still runs.
- `is_gate_matches_registry` passes with `is_gate = True`.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
