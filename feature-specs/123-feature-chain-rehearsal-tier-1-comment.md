# 123 — `test_feature_chain_rehearsal.py`'s tier comment repeats the false tier-1 claim

**Owner:** B — Store and trading

**Phase:** 6. Operator ruling S3 of 2026-09-18, and the ruling that evening that the stale prose
it left in other lanes goes back to its owner as a small spec each.

## Goal

The comment on `REGISTRY_FEE_TIER` at `tests/engines/test_feature_chain_rehearsal.py:1824-1826`
no longer says the fake exchange's tier 1 makes the cost gate unreachable.

## Implementation

1. Read the comment as it stands:
   *"The fee tier this section runs at, by name. Ruling 8 of the Phase 6 task list: at tier 1 the
   cost gate is unreachable by construction, so a chain meant to reach engine 15 has to say which
   tier let it through."*
2. The second half is right: a chain meant to reach engine 15 must name its tier. The first half
   is true of **Kraken's reference** tier 1 (invariant 5) and **not** of the fake's. It was
   measured on 2026-09-18 on the committed subject: friction 0.708%, hurdle 1.062%, cleared
   (`tests/fixtures/kraken/fee_tiers.json`'s `_comment`). Rewrite it to say why this section runs
   at tier 3, without the false reason.
3. A build-log entry.

## Scope Limits

- The comment only. `REGISTRY_FEE_TIER` stays `TIER_3`, and no assertion changes.
- Do not write a fee figure into the comment that no run measured.

## Check When Done

- The comment no longer says the fake's tier 1 is unreachable.
- `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase N`
