# 05 — Three-chain orchestrator, command reader, empty registry

**Owner:** Lead

## Goal

One tick runs the guard, opportunity and manage chains with the semantics of
`context/engine-contracts.md`, reads pending commands two-phase, and completes cleanly
against an empty registry.

## Implementation

1. Create `src/acsoe/core/orchestrator.py`.
2. Mint `run_id` once per process and `cycle_id` once per tick. Write one `runs` row at
   startup carrying `run_id` and the start timestamp, before the first tick — the console
   compares against it to detect a restart.
3. `state` is a fresh dict every tick. Only `state["system"]` — `mode` and `close_intent` —
   carries across. Mode always starts `idle` and is never restored from the store.
4. Step 0: consume commands. Stamp `claimed_at` when read and apply the effect; stamp
   `consumed_at` only when the effect is complete — immediately for `activate` and `freeze`,
   and for `close_all` only when both completion flags are true. On startup, re-apply every
   row with `claimed_at` set and `consumed_at` null, before the first tick. An unrecognised
   command is logged as a warning and ignored.
5. Step 1: the guard chain, every tick in every mode, never breaking early. Initialise
   `state["guard_blockers"] = []`; append an entry for **every** engine that blocks; set
   `trading_blocked_by` and `block_reason` from the first only.
6. Step 2: the opportunity chain, only when mode is `running` and nothing has blocked.
   Break on the first block or PASS.
7. Step 3: the manage chain, every tick in every mode.
8. Step 4: clear `close_intent` only when `state["position_manager"]["entry_orders_cancelled"]`
   and `state["exit"]["positions_closed"]` are both true, then stamp `consumed_at`. A missing
   key reads as "not finished".
9. An unregistered engine in any chain is skipped and logged at debug. An empty chain is valid.
10. Create `src/acsoe/bootstrap.py` with the three runtime chains as empty ordered registries
    and the wiring to build them. It must not import from `research/`.
11. Add `tests/core/test_orchestrator.py`: an empty-registry tick completes; two guard
    blockers both land in `guard_blockers` with the first as primary; the opportunity chain is
    skipped when blocked and when not `running`; the manage chain runs regardless; a fake
    engine raising becomes ERROR with `blocks_trading` true; `close_intent` survives a tick
    where a completion flag is missing.

## Scope Limits

- Do **not** implement any engine. Phase 0 registers none.
- Do **not** implement the store; the reader and the `runs` write go through the `Clients`
  Protocol and are exercised against a fake in tests.
- Do **not** put the decision-bar clock in the orchestrator — cadence belongs to engine 3.
- Do **not** let an engine write `state["system"]`. The orchestrator is its only writer.
- Do **not** register engines 20 or 23; the offline chain is assembled in `cli/research.py`.

## Check When Done

- `python scripts/verify.py --phase 0` reports `orchestrator_empty_registry` as PASS.
- The two-blocker test proves every guard blocker is recorded with the first as primary.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
