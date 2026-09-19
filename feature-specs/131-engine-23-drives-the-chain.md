# 131 — Engine 23 drives the registered chain over history

**Owner:** A — Platform (`research/backtest.py`, `cli/research.py`)

**Phase:** 7. Depends on 129. The artefacts it points at come from 135, with the capped skeptic from
136 (R2, ruled 2026-09-19).

## Goal

`acsoe research backtest` replays a window through the **registered** guard, opportunity and
manage chains, with the replay client and the paper broker, one tick at a time on an injected
clock. It writes every decision through engine 19 into a database of its own. The chain is
`bootstrap.py`'s, unchanged. Engine 23 is the driver and makes no decision.

## Implementation

1. **The tick schedule.**
   - A tick at every 15-minute bar close in the window, whether or not anything traded: engine 3
     owns the bar clock, and `data_guard` and `safety` must see the quiet bars.
   - Between bar closes, a tick every `timeframes.loop_tick_s` **only** while a position is open or
     an entry order rests, read from the store before each step.
   - `context.previous_now` is the previous tick's stamp. The schedule never skips a minute while
     exposure exists, because a stop touched in a skipped minute would be missed.
2. **Stepping.** Use the orchestrator's existing `tick()` with a settable clock. **If the
   orchestrator cannot be stepped this way without a change to `core/`, stop and escalate to the
   lead.** Do not edit `core/`.
3. **Models per fold.** At each fold boundary, point `models.prediction_run_id`,
   `models.anomaly_run_id` and `models.skeptic_run_id` at that fold's Phase 7 run directory, by
   building that tick's config, never by mutating a loaded one. Engines 8, 13 and 15 already reload
   when the run id changes. Each switch is written to the build log's run record with its tick.
4. **One database per run.** A tier's run owns its own SQLite file under `data/db/`. Engine 17 reads
   equity and block records across every run in a database, so two runs sharing one would read each
   other's rows.
5. **Mode `replay`, mode `running`.** The run starts idle, and the driver writes one `activate`
   command through the store before the first bar, exactly as an operator would.
6. **Resumable.** A run killed part-way restarts from its last recorded tick. The paper ledger is
   rebuilt from the store (invariant 2: the store is what a restarted daemon rebuilds from), and
   the driver records the restart.

## Scope Limits

- No engine, no gate and no threshold changes. The driver may not skip a tick the schedule
  requires in order to save time.
- It never writes to the archive (invariant 11) and never writes a relational row itself. Engine 19
  is the single writer.
- No parallelism inside a run. Two tiers run as two processes with two databases.

## Check When Done

- A replay of one committed day (spec 142's fixture) produces the same rows twice from a clean
  database.
- A minute tick occurs on every minute with an open position and on none without one, proven on a
  planted position.
- Killing and resuming reproduces the uninterrupted run's rows.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
