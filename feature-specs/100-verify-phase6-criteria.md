# 100 — The Phase 6 exit criteria in `scripts/verify.py`

**Owner:** C — Interface and models

**Phase:** 6. `scripts/verify.py`, `tests/verify/` and `tests/harness/` are C's.

## Goal

Every clause of the Phase 6 row is a named criterion that reports PENDING while its subject is
absent, PASS when the real engines satisfy it, and has been **observed to FAIL** against a
mutation — driving the real orchestrator, the real `bootstrap` chains once registered, a real
`StoreClient`, the fake Kraken client at **tier 3**, and B's paper broker. Written early so the
engines are built against them, as `verify.py` has been every phase.

## Implementation

1. **Harness, `tests/harness/`:** a named tier-3 fee profile on `FakeKrakenClient` — maker and
   taker fees as fixture data, never in `src/` — and book, trade and quote feeds the criteria can
   script tick by tick.
2. **The subject that produces a trade.** A fabricated world in a temp directory: candles with a
   planted pattern that precedes target touches, trained through the real `research/training.py`
   into a real `models/<run_id>/` for engines 8, 13 and 15 — so a candidate is a real BUY with an
   expected move above the tier-3 bar of 1.625%, not refused by the DI or the anomaly gate, and not
   vetoed. **Fabricate the subject, never the contract**: every engine, contract and config model
   is the real one. If a real BUY cannot be produced honestly, that is the finding, raised to the
   lead, not routed around with a hand-built `state`.
3. Criteria, each registered for phase 6. **Every criterion that drives a trade says in its PASS
   and FAIL message that it ran at fee tier 3, and that tier 1 is a no-trade regime at the current
   barriers** (ruling 1):
   - `paper_trade_round_trip_target`, `_stop`, `_timeout` — through all four gates: post-only entry,
     simulated fill, minute-by-minute watch, the exit, every row engine 19 wrote read back and
     reconciled against the trade (entry, exit, fees, realised PnL to the cent).
   - `unfilled_entry_cancels_without_chasing` — cancelled at `trading.entry_unfilled_window_s`, no
     market order ever constructed, no second entry on the pair.
   - `triggered_stop_holds_on_data_guard_block` — no exit order, `hold_reason` recorded by engine 19;
     and the same position with `close_intent` set exits.
   - `escalation_completes_during_outage` — `safety` escalates after
     `safety.max_consecutive_data_blocks`; entry orders cancelled and positions closed **while
     `data_guard` is still blocking and the balance fetch is still failing**; the orchestrator
     clears `close_intent` and consumes the command; each tolerated fallback on the trade.
   - `console_shows_position_live` — spec 101's subject.
   - `order_book_slippage_on_recorded_book` — engine 9 against `book_sample.jsonl`, thin and deep,
     against a walk the criterion recomputes from the fixture rather than a number it stores.
   - `adaptive_router_weights_on_fixture` — engine 14 against `leaderboard_sample.json`, weights
     recomputed from the rows; the message names it as a property of the fixture.
4. Each criterion proved three ways in `tests/verify/test_phase6_criteria.py`: PENDING on an absent
   subject; PASS on the real one; FAIL on a named mutation (e.g. the hold removed from 21; the
   liquidation reading fresh balances only; engine 9 walking the ask) with the red message quoted
   in the build log. A mutation that survives means the criterion is rewritten.
5. `tests/verify/test_runner.py`'s phase-6 list updated in the same change.
6. **Runtime.** Record each criterion's wall time. Training a subject per criterion multiplies the
   suite's largest cost; share one trained subject across criteria within a run where that does
   not let one criterion's state leak into another's verdict, and say which.

## Scope Limits

- Do **not** read `data/`, `models/` or `logs/`. Fresh-clone rule.
- Do **not** hand-build any engine's `state` payload in a criterion.
- Do **not** change `hurdle_multiple` or any threshold to produce a trade.
- Do **not** assert anything at tier 1 except, if useful, that no trade occurs.

## Check When Done

- `python scripts/verify.py --phase 6` lists every criterion; mid-phase no FAIL.
- Every criterion's FAIL observed and quoted in the build log.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
