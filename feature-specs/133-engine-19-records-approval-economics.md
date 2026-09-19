# 133 — Engine 19 records why a trade was approved

**Owner:** C — Interface and models

**Phase:** 7. Phase 7 prerequisite 7, with B's migration (spec 132).

## Goal

When engine 18 places an entry that later fills, the resulting `trades` row carries the approving
tick's expected move, friction, net edge and hurdle, read from what engines 8 and 10 published on
that tick. **Today the counterfactual dataset records reasons for one side of the decision only.**

## Implementation

1. On the placing tick, engine 19 reads the economics from `state` using the same harvesting it
   already applies to rejections (`ECONOMICS_FIELDS`). It persists them with the order, so that
   they reach the `trades` row when the fill arrives on a later tick. The fill tick's `state` no
   longer holds them, which is why `state` alone cannot carry them.
2. Where they persist between placement and fill is B's schema question. **Agree the column with
   B.** Do not route them through a new `state` key.
3. The model run ids the placing tick used come from engines 8, 13 and 15's published payloads.

## Scope Limits

- Engine 19 remains the single writer. No other engine writes these.
- A fill whose placing tick's economics are absent records them as absent, never as zero, and is
  never refused for it.
- No change to what any gate decides.

## Check When Done

- A round trip through the rehearsal harness produces a `trades` row whose four figures equal
  engine 10's published values on the placing tick, recomputed rather than read back.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
