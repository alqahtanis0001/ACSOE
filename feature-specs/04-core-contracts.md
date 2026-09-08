# 04 — `core/` contracts and Protocols

**Owner:** Lead

## Goal

The fixed engine interface of `context/engine-contracts.md` exists in code, and `core/`
imports nothing else in the package.

## Implementation

1. Create `src/acsoe/core/contracts.py` with `EngineStatus`, `EngineContext`,
   `EngineResult`, `BaseEngine` and `State`, exactly as specified in
   `context/engine-contracts.md`. No extra parameters, return types or side channels.
2. `EngineStatus` is a `StrEnum`. Add a test asserting `str(EngineStatus.ERROR) == "ERROR"`:
   the entire reason for the change is that `(str, Enum)` silently yields
   `"EngineStatus.ERROR"` into a column `safety` filters on.
3. In the same module declare `Config`, `Clock` and `Clients` as `typing.Protocol`s.
   `platform/` and `clients/` provide implementations; `core/` never imports them.
4. `EngineResult.data` must be JSON-serialisable; add a validator rejecting numpy arrays,
   dataframes and model objects.
5. `reason` is mandatory when `blocks_trading` is true; enforce it in the model.
6. Add `tests/core/test_contracts.py` covering the JSON-serialisable rule, the mandatory
   reason, and that importing `acsoe.core` pulls in nothing from `acsoe.platform`,
   `acsoe.clients`, `acsoe.engines` or `acsoe.research`.

## Scope Limits

- Do **not** implement the orchestrator here; spec 05 owns it.
- Do **not** implement `Config`, `Clock` or `Clients` concretely — Protocols only.
- Do **not** add a field, method or status to the interface. Changing it is an escalation to
  the operator, not a lead decision.
- Do **not** import anything from the rest of the package, directly or via `TYPE_CHECKING`
  that leaks at runtime.

## Check When Done

- The import-isolation test proves `acsoe.core` has no intra-package imports.
- `EngineResult(blocks_trading=True)` without a reason raises.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
