# 82 — Register the Phase 6 engines

**Owner:** Lead

**Phase:** 6. `src/acsoe/bootstrap.py` is lead-only.

## Goal

The opportunity chain is 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, (16), 18 and the manage chain is
21, 22, 19, in the registry table's order, each engine registered only after it has been driven
through two real orchestrator ticks by an agent that did not build it.

## Implementation

1. Hold registration of 9 and 14 until B's spec 94 rehearsal is green; of 18, 21 and 22 until A's
   spec 87 rehearsal is green. The same deferral as Phases 2 to 5.
2. `OPPORTUNITY_CHAIN` gains `OrderBookEngine` between `PredictionEngine` and `CostEngine`,
   `AdaptiveRouterEngine` between `RiskEngine` and `SkepticEngine`, `DecisionEngine` after
   `SkepticEngine` and `ExecutionEngine` last. **Engine 16 is a gate** by the operator's ruling of
   2026-09-16, so `is_gate_matches_registry` only passes once the lead's edit to the Gate column
   (spec 80) and B's `is_gate = True` (spec 90) are both in.
3. `MANAGE_CHAIN` becomes `(PositionManagerEngine(), ExitEngine(), MemoryEngine())`. Order is
   load-bearing: 22 reads the triggers 21 published this tick, and 19 records what both did.
4. Rewrite the module docstring's per-phase paragraphs so none describes a hole that no longer
   exists — in particular the paragraph saying engine 15 is unreachable for want of engine 9.
5. `is_gate_matches_registry` and spec 81's registry tripwire both run against the new chains.

## Scope Limits

- Do **not** register an engine whose rehearsal is not green.
- Do **not** reorder any engine already registered.
- Do **not** import anything from `acsoe.research`.

## Check When Done

- `is_gate_matches_registry` PASS, naming the new engine count and zero mismatches.
- Spec 81's bootstrap test green and asserting 21, 22, 19.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
