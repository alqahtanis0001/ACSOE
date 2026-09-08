# 09 — CLI: `acsoe engine`, `acsoe console`, `acsoe research`

**Owner:** A — Platform

## Goal

Three entry points exist. Two start real processes; the third is an honest stub that says the
offline chain has no engines yet.

## Implementation

1. Create `src/acsoe/cli/` with a dispatcher and one module per command.
2. `acsoe engine` — loads config, builds the clock, logging, clients and the orchestrator,
   and runs the tick loop at `timeframes.loop_tick_s`. In Phase 0 the registry is empty, so it
   ticks and does nothing, cleanly, and shuts down on interrupt without leaving a partial write.
3. `acsoe console` — starts the FastAPI app on `console.port`. In Phase 0 the app is a
   placeholder; C builds it in Phase 1. It must start and serve a health response.
4. `acsoe research` — assembles `OFFLINE_CHAIN` in `src/acsoe/cli/research.py` and runs it.
   In Phase 0 it reports that no offline engines are registered and exits zero. This file, not
   `bootstrap.py`, is where engines 20 and 23 are registered from Phase 4 onward, so the live
   loop never imports from `research/`.
5. Add `tests/cli/test_entrypoints.py` asserting each command starts and exits cleanly, and
   that `acsoe research` reports the empty offline chain rather than raising.

## Scope Limits

- Do **not** register any engine in `bootstrap.py` — that is lead-only.
- Do **not** build the console UI; Phase 1 and agent C own it.
- Do **not** import from `research/` in the engine or console entry points.
- Do **not** implement the tick loop's chain logic; it belongs to the orchestrator.

## Check When Done

- `acsoe engine` ticks against an empty registry and stops cleanly on interrupt.
- `acsoe console` serves a health response on the configured port.
- `acsoe research` reports no offline engines and exits zero.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
