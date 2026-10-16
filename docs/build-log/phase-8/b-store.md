# Phase 8 — Agent B build log

### A zero ask was caught twice, so the positivity check had no test of its own

**Agent:** B · **Task:** D10, engine 21 per-pair hold · **Date:** 2026-10-16

**What happened.** I wrote the per-pair liveness predicate in engine 21 and tested a
malformed quote with "a zero ask". A mutation that changed `price <= 0` to `price < 0`
survived the whole file.

**Why.** The baseline bid is 99.99. Against a zero ask, that bid is above the ask, so the
crossed-book check holds the position whatever the positivity check does. The test was
green for the wrong reason. A zero **bid** is the only shape that just the positivity check
catches, because zero is not above any ask.

**Fix.** Added a "zero bid" case to `test_a_malformed_quote_holds_its_position_and_errors_nothing`
and kept the zero-ask case. The id comment says which check each case reaches.

**Consequence.** I ran the arms without touching the shared tree. `shadow_mutate.py` in my
scratch folder copies `src/` and symlinks `db/` and `config/`. It then puts the copy first
on `PYTHONPATH`, which shadows the editable install, and runs the repo's tests unchanged.
Teammates were editing the same checkout, so mutating it in place was not an option.

### Decision: a malformed price holds one position rather than erroring the tick

**Agent:** B · **Date:** 2026-10-16

**Options.** Engine 21 could parse a quote's bid and ask with `_money`, which raises on a
float, and let `process` turn that into ERROR. Or it could treat an unparseable,
non-finite, float or non-positive price as "not a price", so the quote is not live and
that one position is held.

**Chose.** The second. The predicate returns "not live" for those prices.

**Because.** The ERROR path decides no barrier for *any* position. A bad quote on one pair
would then freeze every stop again, which is exactly what the operator's ruling ended. Both
options are fail-closed for the affected position. Only the second stays scoped to it.
Engine 7 makes the same choice: an unusable quote is an exclusion, not a tick-level block.

**Cost.** A float price on a held pair no longer shows up as an engine error. It still
errors the tick through marking if it is the **bid**, because `_bid` is unchanged, so the
defect stays visible for the field that values money.
