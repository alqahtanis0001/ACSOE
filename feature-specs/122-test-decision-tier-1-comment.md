# 122 — `test_decision.py`'s tier comment repeats the false tier-1 claim

**Owner:** B — Store and trading

**Phase:** 6. Operator ruling S3 of 2026-09-18, and the ruling that evening that the stale prose
it left in other lanes goes back to its owner as a small spec each.

## Goal

The comment at `tests/engines/test_decision.py:78-80` no longer says the fake exchange's tier 1
makes the cost gate unreachable.

## Implementation

1. Read the comment as it stands:
   *"Tier 3, standing rule 8 of the Phase 6 task list: everything that drives a trade runs at tier
   3, because at tier 1 the cost gate is unreachable by construction and engine 10 would refuse
   every candidate here for a reason unrelated to engine 16."*
2. That is true of **Kraken's reference** tier 1 (invariant 5). It is **not** true of the fake
   exchange's tier 1. It was measured on 2026-09-18 on the committed subject: friction 0.708%,
   hurdle 1.062%, cleared, entry placed (`tests/fixtures/kraken/fee_tiers.json`'s `_comment`).
   Rewrite the comment so it gives the real reason this test runs at tier 3. Check what that is
   in the test before writing it. It may simply be rule 8 as written, and it may be that this
   test's fee constants matter.
3. **Also check the two constants under it**, `MAKER = "0.0022"` and `TAKER = "0.0038"`. They are
   invariant 5's *reference* tier-3 fees, not the fake's tier 3 (0.0011 / 0.0019). Report what
   they are for, and whether they should come from `fee_tier_profile(TIER_3)`. **Do not change
   them under this spec**: that changes what the test computes, so it is a finding for the lead.
4. A build-log entry.

## Scope Limits

- The comment only. No assertion, no constant and no fixture changes.
- Do not write a fee figure into the comment that no run measured.

## Check When Done

- The comment no longer says the fake's tier 1 is unreachable.
- Step 3's answer is in your progress file.
- `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase N`
