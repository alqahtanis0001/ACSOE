# 110 — The store client's ledger docstring matches the spec 103 amendment

**Owner:** B — Store and trading

**Phase:** 6. Found by B during spec 108, 2026-09-17. Prose only.

## Goal

`src/acsoe/clients/store/client.py`'s `filled_orders` docstring (around line 942) no longer says
the paper balance is adjusted by every *recorded* fill: since spec 103 the paper broker counts
every fill it has executed, recorded or not, and the store is what a restart rebuilds from.

## Implementation

1. Rewrite the docstring to say what `filled_orders` is for now (the recorded half of the
   broker's ledger, and the restart source), pointing at invariant 2.
2. Grep B's lane for any other pre-103 wording and fix it; list it.

## Scope Limits

- Prose only. Nothing outside B's lane.

## Check When Done

- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
