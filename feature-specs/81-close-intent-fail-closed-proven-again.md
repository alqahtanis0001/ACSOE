# 81 — `close_intent`'s fail-closed default, proven again once 21 and 22 exist

**Owner:** Lead

**Phase:** 6. `src/acsoe/core/` and `tests/core/` are the lead's.

## Goal

`_clear_close_intent_if_finished` treats a missing `position_manager` or `exit` result as "not
finished". Today that default is exercised by the absent case, because the manage chain is engine
19 alone. When 21 and 22 are registered the absent case stops occurring in the real registry.
At the end of this spec every test that proves the default is shown, by mutation, still able to
fail, and the shapes a *present* payload can take are covered as well as the absent one.

## Implementation

1. Mutate `Orchestrator._flag` to return `True` on a missing payload and on a missing field, each
   separately, from a byte copy with the hash compared in the same statement. Record which tests
   in `tests/core/test_orchestrator.py` go red for each. **If a mutation survives, fix the tests,
   not the code.**
2. The present-payload shapes the real engines can produce and the absent case cannot stand in
   for, each with its own test: engine 21 **raised** (contract rule 7 gives `ERROR` and `data={}`,
   so the payload is present and empty); engine 21 published the flag as `False`; engine 22
   published it as `None`.
3. **Finding to test before touching code:** `_flag` returns `bool(payload.get(field, False))`, so
   a non-boolean truthy value — the string `"false"`, a non-empty list — reads as *finished* and
   clears the intent. That is a fail-open on the kill switch, reachable by any publisher that
   serialises a flag as text. Write the test that feeds `"false"`, observe it clear the intent,
   record the red, then change `_flag` to accept only `is True`.
4. One test that goes through `acsoe.bootstrap.build_chains()` rather than `Chains(...)` built by
   hand, so the tripwire is attached to the registry the daemon actually runs (code-standards:
   a test whose purpose is "this goes red when X changes" must reach X through X's code path).
   It lands with spec 82's registration and asserts the manage chain's order is 21, 22, 19.
5. Build-log entry at diagnosis for step 3, before the fix.

## Scope Limits

- Do **not** change when the intent clears beyond the `is True` tightening. Both flags true is
  still the only condition.
- Do **not** touch engines 21 or 22; this is the orchestrator's half of the seam.
- Do **not** delete any existing close-intent test. Narrow or strengthen.

## Check When Done

- Every mutation in steps 1 and 3 observed red, named in the build log with the failing tests.
- `pytest tests/core -q` green after the fix.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
