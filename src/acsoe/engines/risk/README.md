# Engine 11 — `risk`

**Gate.** Opportunity chain, runtime stage 3. Owner: B.

Sizes a position from the configured risk parameters, and refuses one that cannot be
placed legitimately.

## The sizing

Invariant 6: "Risk per trade never exceeds the configured fraction of total account
equity." **Risk, not notional.**

```
risk_amount = equity x trading.risk_fraction_per_trade
notional    = risk_amount / barriers.stop_pct
qty         = round_down(notional / price, lot_decimals)
```

The money at risk on a position is the distance to its stop, so a fixed fraction of
equity divided by the stop distance is the notional that puts exactly that fraction at
risk. Reading `risk_fraction_per_trade` as a fraction of *notional* instead would size a
position 66 times smaller at the configured stop — an error that looks conservative and
quietly makes the system untestable.

That reading is not inferred. `config/default.yaml` states the arithmetic in a comment on
`max_concurrent_positions`: "the balance binds first at $5,000: one position is ~$3,333
notional", and $5,000 x 1% / 1.5% is $3,333.33.

## Inputs

| Value | Read from | Published by |
|---|---|---|
| Candidate pair | `state["scout"]["pair"]` | 7 `scout` (B) |
| `ordermin`, `costmin`, `lot_decimals` | `state["exchange"]["pairs"][pair]` | 1 `exchange` (A), from `AssetPairs` |
| Reference price | `state["exchange"]["pairs"][pair]["last_price"]` | 1 `exchange` (A) |
| Quote currency | `state["exchange"]["pairs"][pair]["quote"]` | 1 `exchange` (A) |
| Quote balance | `state["exchange"]["balances"][quote]` | 1 `exchange` (A) |
| Total equity | `store.latest_equity_snapshot()` | 19 `memory`, Phase 4 |
| Open position count | `store.count_open_positions()` | 19 `memory`, Phase 4 |

Configuration: `trading.risk_fraction_per_trade`, `trading.max_concurrent_positions`,
`barriers.stop_pct`, `trading.base_reporting_currency`.

**Equity comes from the store, not from the balance.** Invariant 6 sizes against *total
account equity* — cash plus the value of open positions — and only engine 19 computes
that. Sizing against a single currency's cash would shrink the risk budget every time a
position opened, which is not what a fixed fraction of equity means. No snapshot is a
block, never a fallback to the balance: a fallback there would let the system size a trade
against an equity figure nothing had computed, which is the optimistic kind invariant 2
forbids.

**The open-position count comes from the store too**, for the same structural reason
engine 17 reads the store: this gate runs in the opportunity chain and the manage chain
runs after it, so `state["position_manager"]` does not exist yet.

## Output written to `state["risk"]`

On approval: `pair`, `approved`, `qty`, `notional`, `risk_amount`, `ordermin`, `costmin`,
`reason_code`, `fallbacks_used`.

**On a rejection, `qty` is absent from the payload entirely** — not `null`, not zero, not
the minimum. There is no field an execution engine could read a size out of, and no field
a later refactor could quietly start filling with `ordermin`.

## Gate conditions

In order, because the order is part of the behaviour:

1. **Portfolio already full** — `max_concurrent_positions`. Checked before sizing, so a
   refused candidate never has a quantity computed for it at all.
2. **Notional exceeds the quote balance** — `insufficient_quote_balance`. Invariant 6:
   never allocate cash the account does not hold in that pair's quote currency. Rejected
   rather than capped to fit: a position quietly resized is no longer the position the
   sizing rule chose, which is the same objection as rounding up to a minimum.
3. **Quantity below `ordermin`** — `below_ordermin`. Rejected, never rounded up.
4. **Position value below `costmin`** — `costmin` is tested on the rounded quantity's real
   value, not on the notional the sizing asked for, because rounding down can drop the
   value below the minimum even when the request cleared it.
5. Any input absent, null or unparseable — `risk_inputs_unavailable`. A published `null`
   `ordermin` means the `AssetPairs` fetch failed, and invariant 2 gives pair rules no
   fallback at all; it must never be readable as zero, which would make every position
   trivially large enough.

## Two rules that are easy to get subtly wrong

**Rounding is down, and it happens before the minimum is tested.** Rounding to nearest
would round a quantity one ulp below `ordermin` *up to* `ordermin` — the rounding-up
defect arriving through a rounding mode rather than an explicit bump. And rounding after
the check would let a quantity that passed `ordermin` be rounded below it and placed
anyway. The number compared against the minimum has to be the number that would actually
be sent.

**Nothing here is remembered.** `AGENTS.md` says any remembered order minimum is stale.
There is no constant, no config key and no cache for `ordermin`, `costmin`, tick size or
precision in this engine, and a test reads the source to prove it — because a constant
that happened to match the fixture would satisfy every behavioural test in the file.
