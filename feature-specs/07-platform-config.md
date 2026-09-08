# 07 — `platform/config.py`: model, loader, validation

**Owner:** A — Platform

## Goal

`config/default.yaml` is parsed into a validated pydantic `Config` at startup, and the process
refuses to start on an invalid one.

## Implementation

1. Create `src/acsoe/platform/config.py` with a pydantic v2 model covering every key in
   `config/default.yaml`, satisfying the `Config` Protocol declared in `core/contracts.py`.
2. Load from `config/default.yaml` using `pathlib`. Environment variables are read here and
   nowhere else in the system.
3. Parse with `yaml.safe_load` from `pyyaml` — never `yaml.load`. The stack table now carries
   the row; the lead approved it after C escalated its absence.
4. Validate and refuse to start with a clear message when: a required key is missing; a
   percentage is outside a sane range; `console.poll_interval_ms > console.stale_after_ms / 4`;
   `paper.starting_balances` is not a currency-to-amount map.
5. **Refuse to start while any OPERATOR REQUIRED key is null**, naming the key and saying the
   operator must set it. Those keys are trading behaviour the context files never valued, so
   they are present-and-null rather than defaulted. Model them as required fields that reject
   `None`; do not supply a fallback. This is the config equivalent of a fail-closed gate.
6. **Force paper mode in Phase 0.** `platform/live_guard.py` is a Phase 8 deliverable, so
   until it exists the loader refuses to start if `mode` is anything but `paper`, with a
   message naming invariant 1 and Phase 8. Fail closed: no code path may promote paper to
   live implicitly, and the absence of the guard is not permission.
7. Money-valued config uses `Decimal`, never `float`.
8. Add `tests/platform/test_config.py` covering each rejection above, including `mode: live`.

## Scope Limits

- Do **not** implement the three live switches. That is `live_guard.py`, Phase 8.
- Do **not** add a key to `config/default.yaml`; request it from the lead.
- Do **not** read an environment variable anywhere outside this module.
- Do **not** use `float` for a money value.

## Check When Done

- A config with `mode: live` is refused with a message naming Phase 8.
- A poll interval above a quarter of the stale threshold is refused.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
