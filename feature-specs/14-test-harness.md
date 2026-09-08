# 14 — Test harness, `conftest.py`, fixture structure

**Owner:** C — Interface and models

## Goal

Shared pytest scaffolding so every agent writes tests the same way, and a fixtures directory
whose committed evidence actually survives `.gitignore`.

## Implementation

1. Create `tests/` root scaffolding, `tests/conftest.py`, and `tests/harness/`.
2. Provide shared fixtures: a fixed `Clock`, a temporary migrated database, a temporary
   config with `mode: paper`, a built `EngineContext`, and a `state` dict with `system`
   initialised — the shapes every agent's tests will need.
3. Establish the layout each agent mirrors: `tests/<area>/test_*.py` matching the source path
   its owner owns.
4. Create `tests/fixtures/` structure and document in its README which agent deposits which
   evidence file: A deposits `record_sample.jsonl`, `recording_report.json` and
   `soak_digest.json`; C deposits `labelled_sample.parquet`.
5. Confirm — by actually staging one — that a `.jsonl` and a `.parquet` under `tests/fixtures/`
   are committable despite the global ignores, via the `!tests/fixtures/**` negation.
6. Add a `conftest` guard that fails any test attempting a network call, so "no test touches
   the network" is enforced rather than asserted.
7. **Prove the guard catches a real attempted call.** Add a negative test that genuinely
   attempts an outbound connection — a socket connect and an `httpx` request — and asserts the
   guard fires on each. A guard that has never been shown to fail is not a guard, it is a
   comment; the same reasoning as spec 02's `docs_vocabulary` negative test. Cover both the
   socket layer and the HTTP client layer, because a guard that only patches one is bypassed
   by the other.

## Scope Limits

- Do **not** write tests for another agent's code. Each agent owns the tests mirroring the
  source it owns.
- Do **not** put engine logic or fake exchange behaviour here; spec 15 owns the fake client.
- Do **not** create fixtures inside `data/`.
- Do **not** relax the network guard for convenience.

## Check When Done

- `pytest tests/ -q` collects and runs on an otherwise empty tree.
- A test that attempts a network call fails with a clear message from the guard.
- A `.jsonl` staged under `tests/fixtures/` is actually tracked by git.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
