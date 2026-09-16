# 106 — Engine 11's balance fallback removed; engine 21's fill-tick mark stored

**Owner:** B — Store and trading

**Phase:** 6. Operator rulings 2026-09-16 (invariant 2, "The last fallback was removed").

## Goal

Engine 11 `risk` blocks when engine 1 published no balance, in every mode, exactly as it does on
any other missing input. And a position engine 21 opens on this tick is stored with the mark its
own code says it has.

## Implementation

1. Build-log entry first, in `docs/build-log/phase-6/b-store.md`: what the branch would have done
   if reached (the lead's worked example — after one executed fill, the affordability check at
   `engines/risk/engine.py` compares against the raw `paper.starting_balances`, 5,000, not the
   ~1,664 the account holds, and approves a candidate invariant 6 forbids), and why "dead code
   behind engine 7" was the wrong reassurance.
2. `src/acsoe/engines/risk/engine.py`: `_balances` returns the published map or raises
   `MissingInputError`; the paper branch, `PAPER_STARTING_BALANCES_KEY` and `PAPER_MODE` go if
   nothing else uses them. `src/acsoe/engines/risk/contracts.py`: `FALLBACK_BALANCE_FROM_PAPER`
   goes; decide whether `fallbacks_used` on `RiskSizing` still has a producer — if it has none,
   say so in the build log and remove it only if engine 19 and the console do not read it
   (they are C's; if they do, keep the field, always empty, and report). `README.md`: the
   "balance fallback" section is replaced by the rule and the reason.
3. `tests/engines/test_risk.py`: the fallback tests become block tests — **the test that would
   have caught the defect is a paper-mode tick with no published balance, after a fill, that must
   block**, not merely "no balance blocks". A block and a pass per case, as for every gate.
4. `src/acsoe/engines/position_manager/`: C found that a position opened by this tick's fill is
   stored with `last_price` and `unrealised_pnl` NULL, while `_mark`'s docstring says `last_price`
   on such a position is the fill price and the equity row values it there. Make the stored row
   agree with the valuation — `last_price` the fill price and `unrealised_pnl` zero on the fill
   tick — **or**, if you find a reason that is wrong, stop and report rather than change the
   docstring to match. A test pinning the stored row on the fill tick, red under a mutation.
5. Mutations from byte copies, killing test named, per `code-standards.md`. Before choosing any
   control line, grep `tests/` for its text (your spec 94 lesson). Spec 105's criterion reads
   `positions.last_price` on the fill tick; run `tests/verify/test_phase6_criteria.py` after step
   4 and report what it says.

## Scope Limits

- Do not edit engine 7, 9, 10, 19, the broker, `core/`, `bootstrap.py`, `context/*` or the
  console.
- Do not add a replacement fallback of any kind.
- Do not register anything.

## Check When Done

- A paper tick with no published balance blocks engine 11, with the reason naming the absence.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
