# 42 — Engine 17 `safety`: the ratified `CONDITION_ACTION`, proved in the real guard chain

**Owner:** B — Store and trading

**Phase:** 3 — Economics.

## Goal

The policy table B implemented as a reading of a contradiction becomes the policy the
operator chose, and the engine is proved running where it actually runs — last in the guard
chain, on every tick, against a real orchestrator and a real store.

## Implementation

1. **Apply the ruling to `CONDITION_ACTION` in `engines/safety/contracts.py`.** The operator
   ruled on 2026-09-10, and spec 37 has already written it into invariant 14:

   | Condition | Action |
   |---|---|
   | `DRAWDOWN` | `FREEZE` |
   | `LOSS_STREAK` | `FREEZE` |
   | `ERROR_RATE` | `FREEZE` |
   | `DATA_OUTAGE` | `CLOSE_ALL` |

   Two rows change; `ERROR_RATE` and `DATA_OUTAGE` are as B implemented them. **`close_all`
   is reserved for the invariant 14 data-outage escalation and nothing else.** A drawdown
   breach freezes: it stops new positions while the manage chain keeps watching the open
   ones, and the operator decides whether to liquidate.
2. **Replace the "OPEN QUESTION / pending the ruling" comment block above the table** with
   the ruling and its reasoning: a drawdown is a statement about *past* trades and
   liquidating on it realises a paper loss on the system's own authority; a data outage is a
   statement about *present* knowledge, and unknown exposure is worse than a bad fill. Cite
   invariant 14 as the authority rather than restating it.
3. **`BOUNDARY_SOURCE` is already ratified and does not change.** Drawdown, loss streak and
   error rate trip *at* the limit; the outage is the only strictly-greater one.
4. **The `has_exposure` precondition now guards the outage escalation only.** With drawdown
   and loss streak emitting `freeze`, `_emit`'s `close_all` branch is reached by one
   condition. Keep the precondition where it is — invariant 14 still requires it — but make
   the suppression reasons name the right condition, because they are read by an operator
   trying to understand why the breaker did nothing.
5. **Freeze idempotency is now load-bearing in a way it was not.** Three of the four
   conditions emit `freeze`, and `freeze` is suppressed unless the mode is `running`. A
   drawdown that persists across a thousand ticks must produce exactly one row. This was
   already the rule; it is now the common path rather than the rare one, and the test has to
   cover the case where two conditions trip on the same tick.
6. **Two conditions tripping at once, one of them the outage.** The engine must emit
   `close_all`, not `freeze` — the more severe action wins and the two are not both emitted.
   Make that explicit in the code and in `engines/safety/README.md`; it is currently
   implicit in the iteration order, which is not a decision anyone took.
7. Update `engines/safety/README.md` and `context/progress/b-store.md`: the open question is
   closed, and the answer is recorded with its date.

## Scope Limits

- Do **not** edit `context/trading-invariants.md`. Spec 37 owns that; if it disagrees with
  this table, escalate rather than reconciling in the code.
- Do **not** add a condition, a threshold, or an override. Five thresholds, four conditions.
- Do **not** make `close_all` reachable from any condition other than the data outage.
- Do **not** read any input from `state` other than `trading_blocked_by` and
  `state["system"]`. The six inputs come from the store, and in this phase from the Phase 0
  seed. A live engine 19 is Phase 4 and may not be touched.
- Do **not** order the outage count by `cycle_id`, and do **not** count rows instead of
  ticks. Unchanged and untouchable.
- Do **not** write `state["system"]` or change the mode directly.
- Do **not** register the engine. That is spec 47 and it is the lead's.

## Check When Done

- **A block test and a pass test for each of the four conditions**, and the emitted command
  asserted for each: drawdown → `freeze`, loss streak → `freeze`, error rate → `freeze`,
  outage → `close_all`. A table-driven test that asserts only "a row was written" would pass
  against the pre-ruling table and is not sufficient.
- It **freezes** on the seeded drawdown — the seed carries drawdown 0.2000 against a 0.10
  limit — **on a tick where the opportunity chain never runs**, proving the breaker is not
  gated behind the other gates. This is the assertion the pre-ruling table could not
  satisfy; it should now be literal.
- The seeded drawdown emits **no** `close_all`, even though the seed also carries two open
  positions and two resting entry orders. Assert the absence explicitly.
- `close_all` on the tick **after** `safety.max_consecutive_data_blocks` consecutive
  `data_guard` blocks and **not one tick before**, counted from the seeded `block_records`
  ordered by `ts`, across a run spanning two `run_id`s with reused `cycle_id` values — and a
  companion assertion that ordering by `cycle_id` gives a *different* answer, so the fixture
  is proved to discriminate.
- Drawdown and outage tripping on the same tick emits `close_all` and not `freeze`.
- No second command while a condition persists, asserted across several ticks, for a
  `freeze` condition and for the `close_all` condition separately.
- **The engine runs in a real guard chain with a real `StoreClient`**, not through a double:
  a test drives the orchestrator over an empty database and asserts `safety` trips nothing
  and writes nothing, and over the seeded database and asserts it trips. B deferred exactly
  this check in Phase 2 and it is now due.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 3`
