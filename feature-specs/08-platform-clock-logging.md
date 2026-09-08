# 08 — `platform/`: injected clock, structlog, directory creation

**Owner:** A — Platform

## Goal

A clock the whole system is given rather than reads, JSON logs on disk with secrets redacted,
and the runtime directories in place before anything writes to them.

## Implementation

1. Create `src/acsoe/platform/clock.py` implementing the `Clock` Protocol from
   `core/contracts.py`: a real UTC clock, and a fixed/controllable clock for tests and replay.
   The orchestrator holds it and stamps `context.now`; no engine ever sees it.
2. Create `src/acsoe/platform/logging.py` configuring `structlog` for JSON output, one event
   per line, written to `logs/` with daily rotation.
3. Add a redaction processor at the client boundary that removes API keys, signatures and
   nonces from any event before it is emitted. Redaction belongs here, not at call sites.
4. Bind `run_id` and `cycle_id` into the log context so every line inside the loop carries both.
5. Create `data/raw/`, `data/historical/`, `data/derived/`, `data/db/` and `logs/` at startup
   using `pathlib`, idempotently. Creating a directory is not owning the runtime data written
   into it — B and C write inside these.
6. Add `tests/platform/test_clock.py` (fixed clock is deterministic; the real clock returns
   timezone-aware UTC) and `tests/platform/test_logging.py` (a planted secret never appears in
   emitted output; directories are created idempotently).

## Scope Limits

- Do **not** let any engine construct or import the clock. It is injected.
- Do **not** log an API key, signature or nonce — the redaction test is the proof, not a
  code review.
- Do **not** commit anything under `logs/`; it is gitignored.
- Do **not** write application data into these directories here. Creation only.

## Check When Done

- The redaction test proves a planted key never reaches the log output.
- The fixed clock makes a replay deterministic across two runs.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
