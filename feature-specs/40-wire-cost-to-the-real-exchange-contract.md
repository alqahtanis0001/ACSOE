# 40 — Wire engine 10 `cost` to the real `state["exchange"]`

**Owner:** B — Store and trading

**Phase:** 3 — Economics. The engine exists and is green. It is green against a
`state["exchange"]` that no engine publishes.

## Goal

Engine 10 reads the payload engine 1 `exchange` actually writes, and is proved against
engine 1's own output rather than against a dictionary its tests built by hand.

## Implementation

The audit against `src/acsoe/engines/exchange/contracts.py` found three mismatches. Every
one of them is a `BLOCK` on a live tick, so the gate is currently fail-closed in the least
useful possible way — it refuses everything, for the wrong reason, and says so in prose that
names a key nothing writes.

1. **The fee tier key.** `EXCHANGE_FEES_KEY` is `"fees"`; engine 1 publishes `"fee_tier"`.
   Change the constant.
2. **The fee field names.** The engine reads `maker_pct` and `taker_pct`;
   `FeeTierSnapshot.state_dict()` writes `maker_fee_pct` and `taker_fee_pct`. Lift both into
   named `Final` constants beside the others rather than leaving them as string literals in
   `_read_inputs`, so the next mismatch is one edit and is greppable.
3. **`fallbacks_used` does not exist on `state["exchange"]`.** Engine 1 deliberately applies
   no paper-mode fallback — it publishes `failed_fetches`, a list of `{call, kind, reason}`,
   and leaves the fallback decision to the consumer that has to record it. So `_fallbacks()`
   reads a key nothing writes and returns `()` on every tick, silently.
   - After spec 37 there is **no fee-tier fallback in any mode**. A failed `TradeVolume` is
     a block, full stop.
   - Keep the `fallbacks_used` field on `CostAssessment` — it is a real `rejections` column —
     and source it from fallbacks *this engine applied*, which in Phase 3 is none. Delete
     the dead read rather than repointing it at `failed_fetches`: a failed fetch is not a
     fallback, and putting one in that column would misreport the record invariant 2 asks
     for.
   - When the block is caused by an absent fee tier and `failed_fetches` names
     `trade_volume`, put **that call's reason** into the operator sentence. "Cost gate could
     not price this candidate: missing exchange.fee_tier" is true but sends the operator to
     the wrong place; the useful sentence names the call that failed and why.
4. `state["market_sensor"]["quotes"][pair]["spread_pct"]` was audited and is **correct** as
   written. Change nothing there.
5. Rewrite the module docstring of `engines/cost/contracts.py`. Its *"The state paths below
   are ratified"* section is now false for two of the four paths: they were ratified as
   *positions in the cross-chain key table*, and the table names `state["exchange"]`'s fee
   tier without fixing its field names, which is the gap this spec closes. Say what was
   actually ratified and what was assumed.
6. Update `engines/cost/README.md`: the fee tier has no fallback in any mode, and why.

## Scope Limits

- Do **not** change the arithmetic. `friction = maker + taker + spread + slippage`,
  `net_edge = expected_move − friction`, `TRADE ONLY IF net_edge > hurdle_multiple ×
  friction`. Invariant 5's third line is untouchable and this spec does not go near it.
- Do **not** add a fee fallback, a default tier, or a "last known fee". Spec 37 retired
  "assume tier 1" and there is no replacement.
- Do **not** widen this into engine 9's slippage or engine 8's expected move. Both are C's
  and both are Phase 5; they stay mocked and this engine keeps blocking without them.
- Do **not** write in `src/acsoe/engines/exchange/`, `clients/kraken/`, `core/`, or
  `bootstrap.py`. If engine 1's payload is wrong, that is an escalation to the lead.
- Do **not** relax a test to accommodate the new shape. `test_cost.py:376` asserts
  `fallbacks_used == ["fee_tier_assumed_tier_1"]`. **Delete that test. Do not edit it.**
  Operator ruling 2026-09-10: the tier 1 fallback is retired, so the assertion has no
  subject — there is no longer a thing it could be rewritten to assert. A test edited down
  until it passes again would be a test about nothing, which is worse than an absent one
  because it reads as coverage. Record the deletion and its reason in the build log, as
  spec 32 did for the test it removed.
- Do **not** leave a single test that hand-builds `state["exchange"]`. See the Check When
  Done below; this is a rewrite of the fixtures, not a repoint of four constants.

## Check When Done

- **The seam is driven end to end with no double on either side.** One test constructs A's
  real `ExchangeEngine`, runs it against C's fake Kraken client, takes `result.data`
  verbatim as `state["exchange"]`, and runs this gate on it — reaching a real net-edge
  comparison, not a missing-input block. This is the check the spec exists for: every
  current test builds that dict by hand, and the shape it builds disagrees with the
  publisher. A seam exercised only through a stand-in is not tested; the stand-in is.
- **Every test that hand-builds `state["exchange"]` is rewritten**, not only the one above.
  Operator ruling 2026-09-10. Each fixture builds the payload from engine 1's actual output,
  or from a committed fixture derived from that output — never from a literal typed to match
  what this engine expects. A mock that agrees with its caller is what hid this for a whole
  phase, and **it is the third time this shape has appeared in this project**: the command
  reader whose every test used a store double, the criterion held to a fabricated
  `EngineContext` whose body never once executed, and now this. Both sides passing their own
  tests while disagreeing with each other is the failure mode, and the only thing that
  catches it is refusing the double on one side. Where a test needs a *specific* fee, it
  varies the fake client's fixture and lets engine 1 publish the result; it does not
  shortcut the publisher.
- The existing block test and pass test both still pass through that real payload.
- The fee is still proved fetched, not constant: change the tier the fake returns, and the
  net edge changes — now asserted through engine 1's output rather than a hand-built dict.
- A tick where `trade_volume` failed blocks, and the operator sentence names
  `trade_volume` and its reason, not a state key.
- No `float` in any edge path. `fallbacks_used` is `[]` and no test asserts otherwise.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 3`
