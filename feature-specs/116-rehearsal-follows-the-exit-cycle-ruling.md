# 116 — A's trade-chain rehearsal follows the exit-cycle ruling

**Owner:** A — Platform

**Phase:** 6. Consequence of the operator's ruling of 2026-09-17 (specs 113, 114). Found by C while
building spec 114, reported rather than worked around: the file is A's.

## Goal

`tests/engines/test_trade_chain_rehearsal.py` is green again, and its equity expectation states the
**ruled** behaviour — the account after the exits engine 22 executed — derived independently.

## Why it is red

Two causes, both in the rehearsal itself, neither fixed by engine 19:

1. `check_recorded` builds its *expectation* by re-validating engine 21's and engine 22's published
   rows through `PositionRow` / `TradeRow`, whose `_Row` is `extra="forbid"`. Spec 113 added
   `value` to a position row and `net_proceeds` to a trade row, so the validation raises.
2. Its equity block asserts the pre-exit reading directly — cash from `state["exchange"]`,
   `positions_value` / `unrealised_pnl` from engine 21's totals — which on an exit tick is exactly
   what the ruling changes.

## Implementation

1. Build-log entry first.
2. Strip `value` before `PositionRow.model_validate` and `net_proceeds` before
   `TradeRow.model_validate`. They are payload facts, not columns.
3. The equity expectation: on a tick where engine 22 closed positions, cash is engine 1's balance
   plus the `net_proceeds` of the published `closed_trades`, and `positions_value` /
   `unrealised_pnl` are the sums over engine 21's rows **less** every `position_id` that
   `state["exit"]["positions"]` carries as closed; on any other tick, the totals as today. Also
   assert `cash_source` is `after_exit` on an exit tick and `cycle_start` otherwise.
4. **Derive it from the rule** — `context/engine-contracts.md`, "The exit-cycle equity row" — and
   from the published payloads. **Do not copy engine 19's implementation and do not copy C's probe
   patch**: the rehearsal's value is that it is a *second* derivation of the same rule, so a defect
   in engine 19's arithmetic still has something to disagree with.
5. Prove it can fail: mutate engine 19 in a copied tree so it ignores engine 22's facts (the
   pre-exit row), and confirm the rehearsal goes red naming the equity row; restore by hash.
6. C measured `7 passed in 65.72s` with an equivalent change (probe only, restored by hash
   `79cc6747dfe3`); that is the expected outcome, not the patch to apply.

## Scope Limits

- `tests/engines/test_trade_chain_rehearsal.py`, A's progress file and build log only.
- Do not edit engines 19, 21, 22, the store models, or C's or B's tests.
- Do not weaken any assertion to make the file green; if the ruled behaviour and the rehearsal
  disagree, that is a finding — stop and report it.

## Check When Done

- `tests/engines/test_trade_chain_rehearsal.py` green, and red under the engine 19 mutation above.
- `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/`
