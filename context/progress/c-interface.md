# Progress — c-interface

Your file. Only you write here. The lead merges into `context/progress-tracker.md`.
Never edit the tracker directly.

## Current Task

- **Claimed: specs 00, 01, 02, 14, 15.** Building in that order — `scripts/verify.py`
  runner first, because nothing else in Phase 0 can be reported complete until it runs.

## Completed

- None yet.

## In Progress

- 00 — `scripts/verify.py` runner and criterion framework.
- 01 — the six Phase 0 criteria.
- 02 — `docs_vocabulary`, registered for every phase.
- 14 — test harness, `tests/conftest.py`, `tests/fixtures/` structure, network guard.
- 15 — fake Kraken client.

## Blocked On

- Nothing. Every seam below is mocked and building continues against the mock.

## Open Questions

Unresolved requirements go here and that unit of work stops. Never guess at trading behaviour.

- **Config key names for the `safety` thresholds.** Spec 06 fixes
  `safety.max_consecutive_data_blocks` but leaves the drawdown limit, loss-streak limit and
  error-rate window in prose. `seed_fixtures_present` has to read the first two to assert the
  seed is *past* them, and B's seed has to write past the same numbers. Proposed to the lead:
  `safety.max_drawdown_pct`, `safety.max_consecutive_losses`, `safety.error_rate_window_s`,
  `safety.max_errors_in_window`. **That criterion reports PENDING naming the missing key until
  the lead rules.** Not guessed at.

## Escalations To Lead

Anything touching `core/`, `bootstrap.py`, the engine registry, an invariant, a dependency, or another agent's schema.

- **No YAML library in the architecture stack table.** `config/default.yaml` is YAML;
  `architecture-context.md`'s stack table has no `pyyaml` row, and `ai-workflow-rules.md`
  makes a dependency outside that table an escalation. Spec 07 has A parsing that file.
  Either the table gains a row or the config stops being YAML. Raised with the lead and with A.
- **Entry-point shapes in `core/`, `bootstrap.py` and `cli/research.py`.**
  `orchestrator_empty_registry` and `is_gate_matches_registry` must reach into the lead's and
  A's code from outside. Proposed the smallest surface (module-level `GUARD_CHAIN`,
  `OPPORTUNITY_CHAIN`, `MANAGE_CHAIN`, an `Orchestrator` with a single-tick method, and
  `OFFLINE_CHAIN` in `cli/research.py`) rather than assuming one. Both criteria report PENDING
  with an explicit "symbol not found" message until they exist, so a wrong guess cannot show
  up as a false PASS.

## Verification

Paste the real output of your last run. Never report a task complete without it.

```
pytest tests/ -q
mypy --strict src/
ruff check src/
python scripts/verify.py --phase 0
```

- Not run yet.

## Notes For Next Session

- Recorder line schema received from A and pinned: seven outer keys, `kind` in
  `{tick, gap, session}`, `_recorder` channel on markers.
