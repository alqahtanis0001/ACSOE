# 62 — The store surface for model artefacts

**Owner:** B — Store and trading

**Phase:** 5. `clients/store/` is B's.

## Goal

An engine can reach a trained artefact without touching the filesystem, which contract rule 4
forbids, and engine 20 can write the leaderboard through the one client that writes SQLite.
Two methods and one audit.

## Implementation

1. `StoreClient.__init__` gains `models_dir: Path | None = None`. `model_run_dir(run_id) ->
   Path` returns `models_dir / run_id` when both exist and raises `StoreError` naming the run
   id and the root when either does not; an empty or traversal-shaped `run_id` raises before
   any path is built. No listing, no wildcard, no "latest".
2. `new_model_run_dir(run_id) -> Path` creates the directory and **refuses** an existing one
   with `StoreError`: a trained artefact is never overwritten (`code-standards.md`, Models).
3. Audit `write_leaderboard_entry` and `leaderboard()` against what spec 74 needs: `brier`,
   `n_trades`, `win_rate`, `training_run_id`, `fold`, `promoted`. Add nothing unless the audit
   finds a gap, and record the audit either way in the build log.
4. `tests/clients/store/test_store.py`, B lane. Every assertion on the message, not the type,
   because `StoreError` has one type and several causes.

## Scope Limits

- Do **not** read, parse or validate any artefact. The store hands back a path; what is in it
  is C's manifest (spec 63).
- Do **not** add a schema change or a migration.
- Do **not** touch `console/` or any engine.

## Check When Done

- Mutations: the refusal on an existing directory removed, observed red; `models_dir` absent
  returning a path anyway, observed red.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
