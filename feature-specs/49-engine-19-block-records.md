# 49 — Engine 19 `memory`, part 1: the block record on every blocked tick

**Owner:** C — Interface and models

**Phase:** 4. `engines/memory/` is C's under the permanent ownership map.

## Goal

Engine 19 `memory` exists as a real `BaseEngine` in the manage chain and writes one
`block_records` row per entry in `state["guard_blockers"]`, on every blocked tick. The
circuit breaker in engine 17 `safety` has read that table since Phase 3 and nothing has ever
written to it outside the Phase 0 seed.

## What this engine is for, stated once

`safety` derives its outage count from `block_records`. **A missed row does not fail — it
makes the breaker inert, silently, with every test green.** That is the failure mode this
whole spec is arranged around.

## Implementation

1. `src/acsoe/engines/memory/contracts.py` — pydantic models for what engine 19 puts in
   `state["memory"]`. Money fields typed as the annotated `Money` decimal per engine contract
   rule 8; nothing crosses `state` as a float.
2. `src/acsoe/engines/memory/engine.py` — `MemoryEngine(BaseEngine)`, `name = "memory"`,
   `number = 19`, `is_gate = False`. In `process`:
   - for each entry in `state["guard_blockers"]`, in chain order, write one `block_records`
     row through `context.clients.store` carrying `cycle_id`, `context.run_id`,
     `ts` from `context.now`, `blocked_by`, `block_reason`, `status`, and `is_primary` set on
     the **first entry only**;
   - write **nothing** to that table when `state["guard_blockers"]` is empty;
   - never read the clock, never construct a client, never import another engine, and write
     exactly one `state` key, its own.
3. `src/acsoe/engines/memory/README.md` — purpose, inputs read from `state`, outputs written,
   and the statement that it is not a gate.
4. `state["memory"]` reports what was written this tick — counts per table — so the console
   and the log can see the engine working on a tick that wrote nothing.
5. `tests/engines/test_memory.py` — C's own tests. At minimum: the candidate-less blocked
   tick, the two-guards-at-once tick, the unblocked tick, and a tick whose `status` is
   `ERROR` rather than `BLOCK` reaching the column as the string `ERROR` and not the
   repr of the enum member.

## Rules this spec is held to

- **Every assertion must be proven capable of failing.** Write the assertion, break the thing
  it tests, watch it go red, record that it went red in
  `docs/build-log/phase-4/c-interface.md`, then fix it. For this spec name at least these
  mutations and their results: write no row when the blocker list is empty; set `is_primary`
  on every row; write only the primary blocker; write only on ticks that had a candidate.
- **A double must be capable of exhibiting the property under test.** A store double that
  accepts any row and remembers nothing cannot fail a test about what was written. Use the
  real `StoreClient` against a temporary database.
- The unique index `ux_block_records_primary` is `(run_id, cycle_id)` — a second primary on
  one tick fails at the database. Do not catch that exception to keep a tick alive; a write
  that violates it is a defect in this engine, and contract rule 7 says an uncaught exception
  becomes `ERROR`.

## Scope Limits

- Do **not** write `positions`, `orders`, `equity_snapshots`, `trades` or `rejections` here.
  That is spec 50, deliberately split so this one can be verified on its own.
- Do **not** register the engine in `bootstrap.py`. Registration is the lead's, spec 58.
- Do **not** change `block_records` columns or indexes. A schema change goes through the
  lead and B.
- Do **not** touch `engines/safety/`. If `safety` reads something this engine does not write,
  that is a finding for the lead, not an edit.
- Do **not** infer the bar boundary, read the clock, or write `state["system"]`.

## Check When Done

- `memory_records_every_blocker` is PASS.
- Every test in `tests/engines/test_memory.py` has been observed to fail against a broken
  engine, with the mutation and the red message recorded in the build log.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 4`
