# 36 — Engine 17 `safety`

**Owner:** B — Store and trading

**Phase:** 3 — Economics. **Built concurrently during Phase 2** against the Phase 0 seed, by
operator decision on 2026-09-09. It does **not** count toward Phase 2's gate, and Phase 3 stays
closed until Phase 2 is green and this engine is wired to the real client.

## Goal

The circuit breaker on the account: the engine that freezes the system, or liquidates it, when the
account is in a state no candidate-level judgement should be allowed to override.

## Implementation

1. Create `src/acsoe/engines/safety/` — `engine.py`, `contracts.py`, `README.md`.
   `name = "safety"`, `number = 17`, **`is_gate = True`**, and it runs in the **guard** chain,
   stage 1 — **not** stage 3. It is a gatekeeper on the account, not a judgement about a candidate,
   so it runs on every tick in every mode.
2. **All six inputs come from the store, and every one of them from the Phase 0 seed.** The table
   in `architecture-context.md` under *What engine 17 `safety` reads* is fixed and is the contract:
   equity drawdown from `equity_snapshots`; consecutive losses from `trades` ordered by
   `closed_at`; error rate from `block_records` with `status = 'ERROR'` in the trailing hour; open
   positions from `positions`; resting entry orders from `orders`; and consecutive data blocks from
   `block_records`.
   **Every one of those producers is engine 19 `memory`, which is Phase 4.** Nothing here may touch
   a live engine 19 — that is a forward dependency, and the Phase 0 seed exists precisely to
   resolve it.
3. `state` is fresh every tick and `safety` runs *before* the manage chain, so
   `state["position_manager"]` and `state["exit"]` do not exist when it runs. Read the store.
4. **The outage count is the number of consecutive most-recent `cycle_id`s that have any
   `data_guard` row, not the number of rows.** A tick where two guards blocked contributes one.
   **Order by `ts`, never by `cycle_id`** — `cycle_id` restarts with each process, and the seed
   deliberately spans two `run_id`s to catch exactly that. A tick is `(run_id, cycle_id)`, never
   `cycle_id` alone.
5. `safety` cannot write `state["system"]`. When it must freeze, it writes a `freeze` or
   `close_all` row to the `commands` table through the store client with
   `source = CommandSource.SAFETY`, and the orchestrator consumes it at the top of the next tick.
6. **Idempotency: it emits a row only when that row would actually change the state.** It runs
   every tick, so re-emitting while a condition persists would flood the table and re-trigger a
   liquidation that is already under way.
7. It emits `close_all` on the tick **after** `safety.max_consecutive_data_blocks` consecutive
   `data_guard` blocks and **not one tick before** — and only because the seed also carries an open
   position and a resting entry order, which invariant 14 requires.
8. Thresholds come from `config/default.yaml`, all five under `safety`. They exist and are set.

## Scope Limits

- Do **not** read any input from a live engine 19 `memory`, or from `state`. All six come from the
  store, and in this phase from the seed.
- Do **not** order the outage count by `cycle_id`, and do **not** count rows instead of ticks.
- Do **not** write `state["system"]` or change the mode directly. Write a command row.
- Do **not** re-emit a command while the condition persists.
- Do **not** weaken, bypass, or add an override to this breaker. It is the one thing that is not
  gated behind the other gates.
- Do **not** write into `core/`, `bootstrap.py`, or `clients/kraken/`.
- Do **not** register this engine or treat Phase 3 as started.

## Check When Done

- **A block test and a pass test for each of the six inputs.** A gate with only a happy path is
  incomplete, and this one has six independent trip conditions.
- It freezes on the seeded drawdown **on a tick where the opportunity chain never runs**, proving
  the breaker is not gated behind the other gates.
- It emits **no second command** while the condition persists — asserted across several ticks.
- It emits `close_all` on the tick after `max_consecutive_data_blocks` and **not one tick before**,
  counted from the seeded `block_records` ordered by `ts`, across a run that spans two `run_id`s
  with reused `cycle_id` values. Assert that ordering by `cycle_id` would give a different answer,
  so the fixture is proven to discriminate.
- Every one of the six inputs is read from the seed, asserted by a test that fails if any read
  reaches `state` instead of the store.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
