# 124 — `test_order_book.py`'s helper docstring repeats the false tier-1 claim

**Owner:** C — Interface and models

**Phase:** 6. Operator ruling S3 of 2026-09-18, and the ruling that evening that the stale prose
it left in other lanes goes back to its owner as a small spec each.

## Goal

The docstring at `tests/engines/test_order_book.py:969-974` no longer says the fake exchange's tier
1 makes the cost gate unreachable.

## Implementation

1. Read the docstring as it stands:
   *"Everything engine 10 needs except engine 9's contribution. The spread comes from engine 3's
   key, the fees from A's engine 1 at tier 3, and the expected move from engine 8's key. Tier 3
   because at tier 1 the cost gate is unreachable by construction and a pass test there would
   prove nothing."*
2. The last sentence is true of **Kraken's reference** tier 1 (invariant 5) and **not** of the
   fake's. It was measured on 2026-09-18 on the committed subject: friction 0.708%, hurdle
   1.062%, cleared (`tests/fixtures/kraken/fee_tiers.json`'s `_comment`). Check whether this
   helper's pass tests would in fact pass at the fake's tier 1, and state the real reason for tier
   3. Report it if the answer is that nothing here depends on the tier.
3. A build-log entry.

## Scope Limits

- The docstring only. The helper keeps `fee_tier=TIER_3`, and no assertion changes.
- Do not write a fee figure into the docstring that no run measured.

## Check When Done

- The docstring no longer says the fake's tier 1 is unreachable.
- `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase N`
