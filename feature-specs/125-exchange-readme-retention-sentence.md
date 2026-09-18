# 125 — Engine 1's README says engines 21 and 22 read the retained values

**Owner:** A — Platform

**Phase:** 6. **Not on the operator's list of 2026-09-18 evening.** The lead added it as the same
class: A's own spec 109 finding 2 (`context/progress/a-platform.md:95-131`) left this sentence
unwritten *"because which correct fact to write depends on the ruling"*, and the operator gave
that ruling the same day (S1). The lead flagged the addition to the operator rather than folding
it in silently.

## Goal

`src/acsoe/engines/exchange/README.md`, section "Retained last-known-good values", no longer says
*"engines 21 and 22 read it from the client directly in Phase 6"*.

## Implementation

1. Replace that clause with what is true since S1:
   - engine 22 reads only the retained `AssetPairs`;
   - engine 21 reads neither;
   - the retained balance is kept because invariant 14 authorises it, deliberately wider than the
     code.

   Point at invariant 14 for the reasons rather than restating them.
2. Keep the paragraph's point, which is correct: engine 1 publishes that a value is retained and
   how stale it is, never the value, so a gate cannot reach it.
3. Mark finding 2 in `context/progress/a-platform.md` as answered, with this spec's number. The
   marker has to move.
4. A build-log entry.

## Scope Limits

- The README and A's own progress file only. No code changes.
- Retention of the balance stays; invariant 14 was not amended.

## Check When Done

- `grep -n "engines 21 and 22 read it" src/acsoe/engines/exchange/README.md` finds nothing.
- `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase N`
