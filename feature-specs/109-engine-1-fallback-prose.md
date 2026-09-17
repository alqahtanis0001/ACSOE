# 109 — Engine 1 and the Kraken client no longer describe paper-mode fallbacks

**Owner:** A — Platform

**Phase:** 6. Found by B during spec 108, 2026-09-17. Prose only.

## Goal

A's lane states invariant 2 as it now stands: no paper-mode fallback exists; in paper mode the
balance comes from the paper broker, and a failed fetch blocks every consumer.

## Implementation

1. `src/acsoe/clients/kraken/README.md` (around line 55), `src/acsoe/engines/exchange/README.md`
   (around line 64), `src/acsoe/engines/exchange/contracts.py` (around line 17),
   `src/acsoe/engines/exchange/engine.py` (around line 117) and `tests/engines/test_exchange.py`
   (around line 12) say "invariant 2's paper-mode fallbacks are the consumer's decision". Rewrite
   each to point at invariant 2 rather than restate it: engine 1 reports the failed call and
   substitutes nothing, and no consumer substitutes either.
2. Grep A's lane for any other remnant (`fallback`, `starting_balances`) and fix the prose; list it.
3. Count CRLF in Python before editing; write bytes.

## Scope Limits

- Prose only. No behaviour, no payload, no test assertion changes.
- Nothing outside A's lane.

## Check When Done

- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
