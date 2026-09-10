# 46 — Operator prose for engine 7's reason codes

**Owner:** C — Interface and models

**Phase:** 3 — Economics. Small, and it gates B's spec 44.

## Goal

Every `reason_code` engine 7 `scout` emits reaches the console as a sentence an operator can
act on, rather than as *"No reason was recorded."*

## Implementation

1. Add the codes B fixes in specs 43 and 44 to `REASON_PROSE` in
   `src/acsoe/console/format.py`. `outside_universe` already exists; the per-exclusion codes
   — no pair rules, no live quote, quote currency not held, crypto-quoted disabled, below
   the minimums at this equity, barriers not expressible on the tick grid — do not.
2. **Take B's code strings verbatim**, as you did for engines 4, 10 and 11. The producer and
   the consumer cannot drift if neither retypes the other's string.
3. **Add nothing the row did not carry.** Every entry is a plain restatement of what the
   code already says: no number, no threshold, no cause. A sentence invented in the view
   layer is a sentence nothing verifies. The engines write prose carrying the actual figure,
   and `operator_reason` already prefers that over the mapping.
4. `cost_inputs_unavailable` and `risk_inputs_unavailable` are already present. Confirm they
   still match what specs 40 and 41 leave those engines emitting.
5. The console's empty state renders from engine 7's exclusion tally — *"Scanned 412 pairs.
   38 entered the tradable universe."* Confirm the existing counts-based empty state reads
   the tally B publishes in `state["scout"]`, and say in the build log if it does not; **do
   not rebuild the empty state here.**

## Scope Limits

- Do **not** invent a code. Every key comes from B's `contracts.py`.
- Do **not** put a number, a threshold or a cause into a prose string.
- Do **not** change the existing entries for engines 4, 10, 11, 13 or 15.
- Do **not** rebuild, restyle or extend the empty state. Report a mismatch; do not fix it
  inside this spec.
- Do **not** write in `src/acsoe/engines/`.

## Check When Done

- A test enumerates the codes declared in `engines/scout/contracts.py` and asserts every one
  is a key in `REASON_PROSE`. Enumerated, never listed by hand — a hand-written list drifts
  the first time B adds a code, and it drifts silently, which is the failure mode this seam
  is known for.
- No prose string contains a digit.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 3`
