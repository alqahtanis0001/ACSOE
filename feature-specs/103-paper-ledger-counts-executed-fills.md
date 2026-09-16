# 103 — The paper ledger counts every fill the broker has executed

**Owner:** B — Store and trading

**Phase:** 6. Operator ruling 2026-09-16, amending the paper-ledger ruling of the same day
(invariant 2, "Amended by the operator 2026-09-16"). Found by A's spec 87 rehearsal:
`docs/build-log/phase-6/a-platform.md`, "every paper fill inflates `peak_equity`".

## Goal

`PaperBroker.balance()` reports `paper.starting_balances` adjusted by every fill the broker has
executed, recorded by engine 19 or not, so paper equity on a fill tick equals equity on the tick
before it within the fill's own cost, and a paper trade no longer freezes the account.

## Implementation

1. Build-log entry first: the diagnosis is A's; record in `docs/build-log/phase-6/b-store.md`
   where in `src/acsoe/clients/paper/broker.py` the ledger and the fill decision disagree about
   *when*, before changing anything.
2. `src/acsoe/clients/paper/broker.py`: the balance includes executed-but-unrecorded fills. The
   broker decides fills lazily when engine 21 asks, and engine 1 reads the balance at the top of
   the tick, so the fix must make both reads agree on the same fill **whichever order they are
   asked in** — decide it once, remember it for the tick, and never count it twice once engine 19
   has recorded it.
3. Restart: a fill executed and never recorded (the process died between the two) is absent from
   the rebuilt ledger **and** from the rebuilt positions. Prove it with a test, do not assume it.
4. `tests/clients/paper/`: the balance on the fill tick reflects the spend before the store has
   recorded it; the same fill is not double-counted after it is recorded; the restart case above.
   Each proven red by a mutation from a byte copy, killing test named.
5. **No engine changes.** Engine 21's valuation is correct against a live exchange and stays as it
   is; no engine branches on mode.

## Scope Limits

- Do not edit engines 1, 19, 21 or 22, `core/`, or `bootstrap.py`.
- Do not edit `tests/engines/test_trade_chain_rehearsal.py` — it is A's. Its strict `xfail` on
  finding 1 will XPASS and fail once this lands; **that is expected**, and A converts it to a
  plain assertion in its own lane.
- Do not write the equity-continuity criterion — it is C's, spec 105.
- Do not register anything.

## Check When Done

- A's `test_a_filled_position_is_watched_across_quiet_ticks` passes with its `xfail` removed (A
  runs it); every new broker test observed red under its mutation.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
