# 44 — Engine 7 `scout`, part 2: one candidate, or none

**Owner:** B — Store and trading

**Phase:** 3 — Economics. Zero ML.

## Goal

Engine 7 turns the universe from spec 43 into the single candidate the judgement chain
considers, or stops the chain when nothing qualifies — and publishes
`state["scout"]["pair"]`, which engines 10 and 11 already read.

## Implementation

1. **Ranking is deterministic and contains no model.** Invariant 4: *"Its universe filter is
   arithmetic over `ordermin`, `costmin`, tick size, live spread and balance, and its
   candidate ranking is a deterministic score over features. It contains no model, so
   nothing may override it."* Same inputs, same tick, same answer, always.
2. **THE SCORE IS AN OPERATOR RULING AND IS NOT YET MADE.** No context file specifies it,
   and `AGENTS.md` forbids inventing trading behaviour. This spec does **not** authorise
   choosing one. Until the operator fixes it, implement the ranking as a named function with
   the ordering the operator supplies, isolated in one place in `contracts.py` the way
   `CONDITION_ACTION` is, so the ruling is one edit. **If work reaches this step before the
   ruling arrives, stop and record it as an open question — do not pick a plausible score.**
   That is how a placeholder becomes a decision nobody took, which is exactly what happened
   to `CONDITION_ACTION`.
3. **The tie-break is fixed here regardless**, because it is determinism rather than
   strategy: equal scores break on pair name, ascending, so the candidate does not depend on
   the iteration order of a dictionary. State it in the `README.md`.
4. **One candidate leaves this engine.** `state["scout"]["pair"]` carries it, and the
   cross-chain key table in `engine-contracts.md` fixes that name — engines 10 and 11 read
   it and it may not be renamed.
5. **An empty universe is `PASS`, not `BLOCK`.** The distinction is the whole reason
   `EngineStatus` has both: `PASS` means "nothing to do this cycle; not an error", and the
   orchestrator's opportunity chain stops on it without setting `trading_blocked_by`. Nothing
   qualifying is this system's honest default state — the console renders it as *"Scanned
   412 pairs. 38 entered the tradable universe. None qualified."* — and recording it as a
   block would fill `block_records` with a normal Tuesday and corrupt `safety`'s error rate.
6. **`BLOCK` is reserved for a gate failure**: this engine could not reach the data it needs
   to compute a universe at all — `pair_rules` absent, no equity snapshot, no quotes for any
   pair. That is invariant 3, and it is a different fact from "nothing qualified".
   `state["scout"]["pair"]` is **absent**, not null, in both cases.
7. Every exclusion reason and the no-candidate reason emit a `reason_code`. `outside_universe`
   already exists in C's `REASON_PROSE`; anything new goes to C — spec 46 — before this
   task is reported complete. A code absent from that map renders as "No reason was
   recorded." silently, with no error anywhere.
8. Extend `README.md` with the candidate contract, the `PASS`-versus-`BLOCK` rule and the
   tie-break.

## Scope Limits

- Do **not** choose the ranking score. It is the operator's, and step 2 is a stop.
- Do **not** emit more than one candidate. The judgement chain considers one.
- Do **not** return `BLOCK` when the universe is merely empty.
- Do **not** let any model output, confidence, or router decision reach this engine.
  Invariant 4 — it is protected precisely because it has no model of its own.
- Do **not** read `state["feature"]` or `state["macro_context"]` in Phase 3. Both are C's
  and both are Phase 5; engine 5 returning `PASS` on a non-bar tick is what stops the chain
  before this engine on fourteen ticks in fifteen.
- Do **not** rename `state["scout"]["pair"]`.
- Do **not** write in `core/`, `bootstrap.py`, or `console/format.py`.

## Check When Done

- **A block test and a pass test**, both required for a gate: a tick where `pair_rules` is
  absent returns `BLOCK` with `blocks_trading=True` and a reason; a tick with a populated
  universe returns `OK` and publishes exactly one `state["scout"]["pair"]`.
- **A third test for the middle case**: a tick where the universe is empty returns `PASS`,
  `blocks_trading=False`, and no `pair` key. Assert the status is `PASS` and not `BLOCK` —
  this is the assertion that would quietly be wrong forever.
- Determinism: the same inputs produce the same candidate across repeated runs and across a
  shuffled input ordering. Shuffle the pair mapping and assert the answer is unchanged.
- The tie-break fires: two pairs with an identical score resolve to the alphabetically first.
- Engines 10 and 11 read the published pair without a translation step — one test runs
  scout, then the cost gate, on the same `state`.
- Every `reason_code` this engine emits is present in `console/format.py`'s `REASON_PROSE`,
  asserted by a test that enumerates the codes rather than listing them by hand.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 3`
