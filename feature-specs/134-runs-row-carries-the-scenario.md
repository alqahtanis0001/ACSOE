# 134 — The `runs` row carries the replay scenario

**Owner:** Lead (`core/` writes the `runs` row at startup)

**Phase:** 7. After 132 (the column) and 129 (the digest).

## Goal

Every replay run's `runs` row names the scenario that priced it, so a result can never be read
without its declared inputs.

## Implementation

1. The orchestrator's `_record_run` writes `scenario_digest` and `scenario_description`. It takes
   them from the clients object when the replay client exposes them, and leaves them null
   otherwise.
2. Engine 19 needs nothing new. Every trade and rejection joins to its run by `run_id`.

## Scope Limits

- No mode branch in any engine. The value comes from the client layer through the existing
  clients object.
- Paper and live runs write null, never a placeholder.

## Check When Done

- A replay run's `runs` row carries the digest spec 129 computes. A paper run's carries null.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
