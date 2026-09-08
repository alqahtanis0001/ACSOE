# 03 — Package skeleton and `pyproject.toml`

**Owner:** A — Platform

## Goal

`pip install -e ".[dev]"` produces an importable `acsoe` package with the directory layout of
`context/architecture-context.md`, and the three quality commands run against it.

## Implementation

1. Create `pyproject.toml` with a src layout, Python 3.11+, and the runtime dependencies
   named in the stack table of `context/architecture-context.md`. Do not add a dependency
   that is not in that table; a new dependency is an escalation to the lead.
2. Add a `dev` extra: `pytest`, `pytest-asyncio`, `hypothesis`, `mypy`, `ruff`.
3. Configure `mypy` for `--strict` on `src/`, and `ruff` with the rules the standards imply:
   no bare except, no mutable default arguments, `pathlib` over string paths.
4. Create the package tree with `__init__.py` where needed:
   `src/acsoe/{core,platform,engines,clients,research,console,cli}/`, plus
   `src/acsoe/clients/{kraken,store,recorder}/`.
5. Create empty-but-present `db/migrations/`, `config/`, and `feature-specs/` if absent.
6. Add console-script entry points for `acsoe` pointing at `src/acsoe/cli/`.
7. Add `tests/platform/test_packaging.py` asserting `import acsoe` works and the expected
   subpackages are importable.

## Scope Limits

- Do **not** implement anything inside `core/` — that is lead-only.
- Do **not** implement config, clock, logging or the CLI here; specs 07, 08 and 09 own those.
- Do **not** add a dependency outside the architecture stack table.
- Do **not** create `data/`, `logs/` or `models/` here; spec 08 owns directory creation.

## Check When Done

- `pip install -e ".[dev]"` succeeds from a clean virtualenv.
- `import acsoe` and each subpackage import succeeds.
- `mypy --strict src/` and `ruff check src/` run and are green on the skeleton.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
