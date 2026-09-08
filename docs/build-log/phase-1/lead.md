# Build log — Phase 1 — lead

Entries the lead owns directly. Consolidated into `docs/build-log/phase-1.md` at phase close.

Minimum headings per entry: What happened, Why, Fix.

## Entries

*None yet.*

## Carried into this phase from Phase 0

Recorded here so they are decided rather than rediscovered. Neither is a defect.

- **Widening `TOOLCHAIN` beyond `src/`.** `mypy --strict scripts/` reports 2 errors in
  `verify.py` — `candidate` bound to a `Path` in one loop and a `str` in the next, at the top of
  `_interpreter_with_toolchain` — and `ruff check tests/` reports 2 violations (`UP031` in
  `tests/core/test_contracts.py`, `SIM300` in `tests/db/test_migrations.py`). None is reachable
  by the gate that implements them. Deferred from Phase 0 deliberately: changing what every
  phase's gate asserts belongs at a phase boundary.
- **The console screens with no design.** `ui-context.md` specifies the status band, open
  positions and the cycle feed. History, the research views, the leaderboard and the SHAP view
  are named in the Phase 1 criteria and designed nowhere, and their upstream engines do not exist
  until Phase 4 and Phase 5. C should not resolve this by inventing a screen; it is a scope
  question for the operator.
