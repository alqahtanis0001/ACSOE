# Engine 10 — `cost`

**Gate.** Opportunity chain, runtime stage 3. Owner: B.

The gate that refuses a trade whose expected move does not survive its own friction.

## The rule

Invariant 5 of `context/trading-invariants.md`, which this engine is the only
implementation of:

```
friction  = live_maker_fee + live_taker_fee + measured_spread + estimated_slippage
net_edge  = expected_move - friction
TRADE ONLY IF net_edge > hurdle_multiple x friction
```

`net_edge` is what the engine computes. **The rule is the third line.** They are not the
same thing, and the third line is not adjustable to make anything pass.

Friction assumes **maker on entry, taker on exit** — the worst realistic round trip,
because a stop must always exit as a taker. Both rates are added once.

## Inputs read from `state`

| Value | Read from | Published by |
|---|---|---|
| Candidate pair | `state["scout"]["pair"]` | 7 `scout` (B, Phase 3 proper) |
| Expected move | `state["prediction"]["expected_move_pct"]` | 8 `prediction` (C) |
| Maker fee | `state["exchange"]["fees"]["maker_pct"]` | 1 `exchange` (A) |
| Taker fee | `state["exchange"]["fees"]["taker_pct"]` | 1 `exchange` (A) |
| Measured spread | `state["exchange"]["pairs"][pair]["spread_pct"]` | 1 `exchange` (A) |
| Estimated slippage | `state["order_book"]["estimated_slippage_pct"]` | 9 `order_book` (C) |
| Fallbacks that fired | `state["exchange"]["fallbacks_used"]` | 1 `exchange` (A) |

Configuration: `trading.hurdle_multiple`, and nothing else.

**Only the fee-tier path is ratified.** Spec 34 fixes it in prose; the other four are B's
proposal and are declared as `Final` constants in `contracts.py` so re-pointing one is a
single-line edit. The open question is in `context/progress/b-store.md`.

**Money crosses `state` as an exact decimal string, never a `Decimal` and never a
`float`.** `EngineResult.data` refuses a `Decimal` outright — its JSON check allows only
`None | str | int | float | bool` — and a `float` would pass that check having already
lost precision. Every money field of `CostInputs` is `Money`, the `Decimal` that raises
on a `float` rather than coercing it.

## Output written to `state["cost"]`

`pair`, `expected_move_pct`, `friction_pct`, `net_edge_pct`, `hurdle_pct`,
`clears_hurdle`, `reason_code`, `fallbacks_used`.

The four percentage names are the `rejections` column names, deliberately: engine 19
`memory` fills that table from this payload, and a translation step between the engine
that computes a number and the table that stores it is a place for them to stop meaning
the same thing.

## Gate conditions

Blocks when:

- `net_edge <= hurdle_multiple x friction` — `reason_code` `net_edge_below_hurdle`.
- The spread alone exceeds the expected move — `reason_code` `spread_wider_than_move`.
  Strictly a subset of the first, distinguished because it tells the operator the market
  is the problem rather than the candidate.
- Any input is absent, null or unparseable — `reason_code` `cost_inputs_unavailable`.
  Invariant 3: a gate that cannot reach its data blocks, and absence of a "no" is never
  a "yes". A published `null` is treated exactly as an absent key, so a failed
  order-book fetch can never be read as a spread of zero.

The reason is always operator prose carrying the actual number — "Net edge −0.21% after
fees" — because `console/format.py`'s `operator_reason` prefers a stored prose reason
over the generic sentence keyed on the code, and no code-keyed mapping can carry a
number.

## Two things worth knowing before you change this

**At tier 1 this gate is unreachable, by construction.** With `hurdle_multiple: 1.5`,
`net_edge > 1.5 x friction` rearranges to `expected_move > 2.5 x friction`. Tier 1
friction is around 1.25% round trip, so a candidate needs an expected move above roughly
3.125% while the target barrier is 3.0%. Nothing clears the cost gate at tier 1 with
these barriers, and the system is built to be able to report that honestly rather than to
be tuned until it disappears. A pass test therefore has to use a better tier — which is
the same lever the "the fee is fetched, not constant" test pulls.

**The spread half of this engine cannot be backtested.** The historical archives are
OHLCVT only: open, high, low, close, volume, trades. They carry no bid, no ask and no
book depth, so neither `measured_spread` nor `estimated_slippage` can be reconstructed
from them at any resolution. A backtest of this gate is therefore a backtest of the fee
half with an assumed spread — and invariant 2 says in as many words that an assumed
spread invalidates the cost gate. Engine 2 `market_data_recorder` exists because of this:
spread and book history have to be collected forward from day one, since they cannot be
recovered retroactively. Until enough has accumulated, any walk-forward result that
includes this gate is an upper bound on performance, not an estimate of it, and must be
reported as such.
