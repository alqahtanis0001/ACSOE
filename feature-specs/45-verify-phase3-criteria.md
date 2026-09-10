# 45 — The Phase 3 exit criteria in `scripts/verify.py`

**Owner:** C — Interface and models

**Phase:** 3 — Economics. **This spec lands early**, alongside spec 37. `verify.py` must
exist before A and B can report anything complete — the same sequencing as Phase 0.

## Goal

`python scripts/verify.py --phase 3` becomes the executable form of the Phase 3 row of
`ai-workflow-rules.md`. Today it registers nothing for phase 3, so the gate is silent.

## Implementation

Register these criteria for phase 3. Each is one named check printing PASS, FAIL or PENDING,
each runs offline with no network and no API key, and each passes on a fresh clone.

1. `cost_gate_uses_live_fee_tier` — the cost engine computes net edge from the fee tier the
   fake Kraken client returns rather than a constant, and blocks below the hurdle. **Change
   the tier and assert the net edge changes**; a constant satisfies a single-value check.
2. `risk_rejects_sub_ordermin` — a position one increment below `ordermin` is **rejected**,
   and the returned quantity is absent rather than bumped. A check asserting only "no order
   was placed" passes against a rounding implementation and is not sufficient.
3. `universe_varies_with_balance` — the universe filter yields **different pair counts** at
   a $10 balance and at a $5,000 balance, over the same fixture set. Assert both counts and
   assert they differ.
4. `safety_freezes_on_drawdown_without_opportunity_chain` — `safety` freezes on the seeded
   drawdown **on a tick where the opportunity chain never runs**, proving the breaker is not
   gated behind the other gates, and **re-emits no command while the condition persists**.
   Per the spec 37 ruling this is a `freeze` and **not** a `close_all`; assert the absence of
   the `close_all` too, because the seed carries the open position and the resting order that
   would have permitted one.
5. `safety_escalates_on_sustained_outage` — `safety` emits `close_all` on the tick **after**
   `safety.max_consecutive_data_blocks` consecutive `data_guard` blocks and **not one tick
   before**, counted from the Phase 0 seeded `block_records` — **not** from a live engine 19,
   whose implementation is Phase 4 and which Phase 3 may not depend on — ordered by `ts` so a
   seeded run spanning two `run_id`s still counts as consecutive, and emitted only because
   the seed also carries an open position and a resting entry order.
6. `safety_inputs_all_from_the_seed` — every one of `safety`'s six inputs is read from the
   Phase 0 seed and none from a live engine. Assert the reads reach the store, not `state`.
7. `phase_3_gates_have_both_tests` — each of engines 7, 10, 11 and 17 has at least one test
   proving it blocks and one proving it passes. A gate with only a happy path is incomplete,
   and this is the criterion that notices.

## Rules this spec is held to

- **Fabricate the subject a criterion judges. Never fabricate a contract it is held to.**
  Import the real `core/contracts.py`, the real `clients/store/contracts.py` and the real
  engine `contracts.py` modules. `check_data_guard_blocks_bad_data` fabricated an
  `EngineContext` and its body never once executed; that is the failure this rule exists to
  stop and it cost a phase to find.
- **Prove each criterion twice**, as in Phases 0 to 2: PENDING against a tree where the
  subject does not exist, PASS against a fabricated subject. Then **make each one FAIL on
  purpose** and record what you did in the build log. A check nobody has seen fail is a
  comment.
- **A gate satisfied by the shape of the evidence rather than by its content will accept
  fabricated evidence of the right shape.** Phase 2 produced that rule at the cost of a
  criterion that would have passed a 47%-recorded archive. Ask of every criterion above:
  would it still pass if the thing it names were false?

## Scope Limits

- Do **not** write, patch, or "fix" any engine. If a criterion FAILs, it goes back to its
  owning agent.
- Do **not** register a criterion that needs the network, an API key, or anything under
  `data/`, `models/` or `logs/` — all three are gitignored and a criterion must pass on a
  fresh clone.
- Do **not** depend on a live engine 19 `memory` anywhere in criteria 4, 5 or 6. Phase 3
  reads the Phase 0 seed; that is the whole reason the seed carries those six fixtures.
- Do **not** widen `TOOLCHAIN` beyond `src/`. Still deferred, still the operator's.
- Do **not** change any Phase 0, 1 or 2 criterion.

## Check When Done

- `python scripts/verify.py --phase 3` reports all seven criteria, PENDING where the subject
  is absent and PASS where it is present. No FAIL that is not a real defect.
- Each criterion has been observed PENDING, observed PASS, and **observed FAIL**, with the
  induced failure recorded in `docs/build-log/phase-3/c-interface.md`.
- Phases 0, 1 and 2 still report exactly what they reported before this spec.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 3`
