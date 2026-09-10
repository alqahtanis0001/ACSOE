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
| Maker fee | `state["exchange"]["fee_tier"]["maker_fee_pct"]` | 1 `exchange` (A) |
| Taker fee | `state["exchange"]["fee_tier"]["taker_fee_pct"]` | 1 `exchange` (A) |
| Measured spread | `state["market_sensor"]["quotes"][pair]["spread_pct"]` | 3 `market_sensor` (A) |
| Estimated slippage | `state["order_book"]["estimated_slippage_pct"]` | 9 `order_book` (C) |
| Why a call failed, for the block sentence only | `state["exchange"]["failed_fetches"]` | 1 `exchange` (A) |

Configuration: `trading.hurdle_multiple`, and nothing else.

**One path was ratified and three were assumed. Corrected 2026-09-10 by spec 40.** What
the lead ratified on 2026-09-09 was a set of *positions* in `engine-contracts.md`'s
cross-chain key table — which engine publishes each value, under which state key. That
table says the fee tier arrives on `state["exchange"]` from engine 1; it does not fix
engine 1's field names, and it never did. The field names below `state["exchange"]` were
B's assumption, written against an engine 1 that did not exist yet, and the Phase 3 audit
found three of them wrong: `exchange.fees` was really `exchange.fee_tier`, `maker_pct` and
`taker_pct` were really `maker_fee_pct` and `taker_fee_pct`, and `fallbacks_used` was
nothing at all. Every one of them blocked every live tick.

The spread path *was* ratified, and it is the one that was right. B proposed it on
`state["exchange"]` and the lead re-pointed it to `state["market_sensor"]`: engine 1
`exchange` is the *account* engine (balances, fee tier, pair rules); engine 3
`market_sensor` is the *market-data* engine, and spread is market data.

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
number. The one exception to "name the input" is the fee tier: when `trade_volume` is
named in `failed_fetches`, the sentence quotes *that call and its reason* instead of
`exchange.fee_tier`. The state key is true and useless — it sends the operator to look at
a `None` — while the call is the thing they can act on.

## The fee tier has no fallback, in any mode

**A confirmed pair with no fee data blocks that pair.** Not in live mode only: in paper
mode too, and this engine applies no fallback at all.

Invariant 2's paper-mode table used to carry a fee-tier row that named a tier and told the
system to assume it. **The operator retired that row on 2026-09-10 (spec 37), because it
was never implementable.** `AssetPairs` carries no fee schedule, so there was no runtime
source the named tier could have been read from, and the only way to honour the row was to
write a fee percentage into the code — which `AGENTS.md` forbids in its first paragraph
and which would have been stale the day it was written. A fee nobody fetched invalidates
this gate for exactly the reason a spread nobody measured does: both are terms of
`friction`, and a gate priced on a guess is not a gate.

The consequence is worth stating plainly rather than leaving to be discovered: with an
empty `.env` the private calls fail, `TradeVolume` returns nothing, and **every pair blocks
here**. A fresh clone still runs the loop, still records the order book and still builds
candles — which is what the recording exists for and cannot be recovered later — but it
takes no paper trades and produces no rejection rows past this gate. That is the honest
description of an unauthenticated clone, and it beats one that generates a research
dataset priced on a fee somebody guessed.

So `fallbacks_used` on this engine's payload is **always empty**, and it is kept rather
than removed because it is a real `rejections` column that engine 19 fills. It records
fallbacks *this engine applied*. It is **not** a copy of engine 1's `failed_fetches`, and
the distinction is the whole reason the old dead read was deleted rather than re-pointed:
a failed fetch is the opposite of a fallback. Nothing was substituted, so nothing was
traded on, and writing one into that column would misreport exactly the thing invariant 2
asks to be recorded. **Balance is the only paper-mode fallback left in this system**, and
it belongs to engine 11 `risk`, not here.

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
