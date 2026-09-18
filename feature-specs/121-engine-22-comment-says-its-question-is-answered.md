# 121 — Engine 22's contract comment says its question was answered

**Owner:** B — Store and trading

**Phase:** 6. Operator ruling of 2026-09-18 evening: stale prose that says a question is open when
it has been answered goes back to its owner as a small spec. That is how D3 and D8 went stale two
days earlier.

## Goal

`src/acsoe/engines/exit/contracts.py:159-166`, the comment on `FALLBACK_ASSET_PAIRS_RETAINED`, no
longer ends *"Escalated to the lead rather than decided here."* It records that the escalation
was answered.

## Implementation

1. In `src/acsoe/engines/exit/contracts.py`, replace the last sentence of the comment above
   `FALLBACK_ASSET_PAIRS_RETAINED` with the ruling. The operator ruled on 2026-09-18 (S1 of
   `docs/build-log/phase-6/overnight-decisions-2026-09-18-night.md`) that engine 22 stays as
   built and never reads a balance. Invariant 14 keeps its balance authorisation deliberately
   wider than the code and records why. Point at invariant 14 and do not paraphrase it.
2. Read `src/acsoe/engines/exit/engine.py`'s module docstring (the paragraph beginning "**This
   engine never reads a balance**") and `src/acsoe/engines/exit/README.md`. If either still reads
   as an open question, give it the same one-line pointer.
3. A build-log entry in `docs/build-log/phase-6/b-store.md` or `phase-7/b-store.md`, whichever
   phase is open when this is done.

## Scope Limits

- **Prose only.** No code, no constant, no payload, no test assertion changes.
- `FALLBACK_ASSET_PAIRS_RETAINED` keeps its name and value, and no `balance_last_known_good`
  constant is added. The ruling was that engine 22 stays as built.
- Do not restate invariant 14's reasons; point at it.

## Check When Done

- `grep -n "Escalated to the lead" src/acsoe/engines/exit/` finds nothing.
- `git diff --stat` touches only comments and docstrings in `engines/exit/`, and the build log.
- `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase N`
