# 112 — A test that says when invariant 14's resting-entry clause becomes reachable

**Owner:** B — Store and trading

**Phase:** 6. Operator ruling 2026-09-17 on open question Q2 (finding F1).

## Goal

A test in engine 17's tests asserting that `trading.entry_unfilled_window_s` is less than
`safety.max_consecutive_data_blocks × timeframes.loop_tick_s`, all three read from the committed
config — so that if either value changes, the test firing is the notice that invariant 14's
"or resting entry orders" escalation clause has become reachable and is untested.

## Implementation

1. In `tests/engines/test_safety*.py` (whichever file holds engine 17's escalation tests), add the
   test, reading the three values through the real config loader from `config/default.yaml`,
   never as literals.
2. Its comment, in substance: while this holds, a resting entry is always cancelled by its
   unfilled window (invariant 8, even during a `data_guard` hold) before `safety` can escalate, so
   invariant 14's resting-entry clause is reachable only through an operator Close all, which
   `escalation_completes_during_outage` exercises. If this test fires, the clause has become
   reachable through a `safety` escalation and needs its own test. **This test does not forbid the
   change; it makes it visible** (A's Phase 5 rule: assert the unreachable path is unreachable
   rather than delete it).
3. Prove it can fail: a copied config with the window raised above the product turns it red, with
   the message naming all three values.
4. Report the test's exact name to the lead, who adds a one-line pointer to invariant 14.

## Scope Limits

- No config value changes. No engine changes. B's lane only.

## Check When Done

- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
