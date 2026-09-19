# 134 — The `runs` row carries the replay scenario

**Owner:** Lead (`core/` writes the `runs` row at startup)

**Phase:** 7. After 132 (the column) and 129 (the digest).

## Goal

Every replay run's `runs` row names the scenario that priced it, so a result can never be read
without its declared inputs.

## Implementation

1. The orchestrator's `_record_run` writes `scenario_digest` and `scenario_description`. It takes
   them from the clients object when the replay client exposes them, and leaves them null
   otherwise. **The description carries the synthetic book's parameters** (the bucket table's
   identity and each bucket's spread and depth as served), the fee tier and schedule, the rules
   file, the partition manifest, the window, the ranking, and whether the run is the alphabetical
   baseline. The digest covers the same inputs.
2. **Every trade and rejection carries the digest through its `run_id`.** The scenario is fixed for
   the life of a run, so the run's digest is each row's digest, and engine 19 needs nothing new. A
   test proves the join: every `trades` and `rejections` row of a replay run resolves to a `runs`
   row with a non-null digest, and none resolves to a paper run's null.

## Scope Limits

- No mode branch in any engine. The value comes from the client layer through the existing
  clients object.
- Paper and live runs write null, never a placeholder.

## Check When Done

- A replay run's `runs` row carries the digest spec 129 computes. A paper run's carries null.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
