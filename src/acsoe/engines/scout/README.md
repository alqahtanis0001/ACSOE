# Engine 7 — `scout`

**Gate.** Opportunity chain, runtime stage 2. Owner: B.

The tradable universe: which Kraken pairs this account could legitimately trade **right
now**. Not which it likes — that is the candidate, and it is spec 44.

## The universe is computed, never configured

A Locked Decision, and this engine is its only implementation:

> Tradable universe computed per tick from `ordermin`, `costmin`, tick size, live spread
> and balance. **No account-size thresholds.**

So there is no pair list in this engine, no config key holding one, no hardcoded symbol,
and no comparison of a balance against a literal. Every number the filter uses arrives from
`AssetPairs`, the live book, the account, or a configured *ratio* — and a ratio is a policy,
not a pair. `test_no_pair_name_or_exchange_value_is_written_into_the_engine_source` parses
the module's AST and asserts it, because a symbol that happened to match the fixture would
satisfy every behavioural test in the file.

**Recomputed from scratch every tick.** Nothing is cached and nothing carries across: a
pair that entered last tick has to earn it again on this one, because the balance, the book
and the pair rules can all have moved.

## Deterministic and protected

Invariant 4: no confidence score, probability, ensemble weight or router decision may skip,
soften or override this gate. It contains no model, so there is nothing here for one to
override — and that absence is the property being protected rather than a coincidence.

## Inputs

| Value | Read from | Published by |
|---|---|---|
| `ordermin`, `costmin`, `tick_size`, `lot_decimals`, `base`, `quote` | `state["exchange"]["pair_rules"]["pairs"]` | 1 `exchange` (A), from `AssetPairs` |
| Per-currency spendable balance | `state["exchange"]["balances"]` | 1 `exchange` (A) |
| `bid`, `ask` | `state["market_sensor"]["quotes"][pair]` | 3 `market_sensor` (A) |
| Total account equity | `store.latest_equity_snapshot()` | 19 `memory`, Phase 4 |

Configuration: `trading.risk_fraction_per_trade`, `barriers.stop_pct`, `barriers.target_pct`,
`trading.allow_crypto_quoted`, `trading.base_reporting_currency`,
`trading.stable_quote_currencies`.

**Equity comes from the store, not from a balance**, for the reason engine 11 gives:
invariant 6 sizes against cash plus the value of open positions, and only engine 19 computes
that. No snapshot is a **block**, never a fallback — a fallback there would let the system
decide what it can trade against an equity figure nothing had computed.

## The exclusions, in the order they are applied

A pair enters only if every rule passes. It is attributed to the **first** rule it fails and
to exactly one, which is what makes the tally exhaustive.

| # | Reason code | The pair is excluded because |
|---|---|---|
| 1 | `pair_rules_missing` | `AssetPairs` does not list it, or its rules are unparseable. Invariant 2 gives pair rules no fallback in any mode: a wrong `ordermin` produces invalid orders. |
| 2 | `no_live_quote` | There is no live top-of-book, or the price is not positive. **Never read as a zero spread** — invariant 2 says an assumed spread invalidates the cost gate, and zero is the most optimistic value the field can take. |
| 3 | `crypto_quoted` | Its quote is a non-stable asset and `trading.allow_crypto_quoted` is false. Invariant 7: profit denominated in a volatile asset is a second directional bet the system did not choose to make. |
| 4 | `quote_not_provably_stable` | `trading.stable_quote_currencies` is **absent**, so no quote can be shown stable. See below — this is a separate code on purpose. |
| 5 | `no_quote_balance` | The account holds nothing spendable in that quote currency. Invariant 7, and **positive**, not merely present: a currency in the map with nothing in it is a drained account, not a held one. |
| 6 | `barriers_below_tick_size` | The barriers are not expressible on the pair's tick grid. See below. |
| 7 | `no_fx_rate` | Affordability cannot be **computed**: the position's cost is in the reporting currency and the balance is in the pair's quote currency, and nothing publishes a rate between them. See below. |
| 8 | `insufficient_quote_balance` | The account holds some of the quote currency but less than the position this equity would size. Invariant 6. Both sides are computed; neither is a literal. |
| 9 | `below_ordermin` | The position is below the pair's minimum order size, after rounding **down** to `lot_decimals`. |
| 10 | `below_costmin` | The same position is worth less than the pair's minimum order value, **at the bid**. |

Codes 7 to 10 are engine 11 `risk`'s, reused deliberately rather than duplicated under new
names: it is the same arithmetic and it means the same thing, so it should read the same on
the console.

`scout_inputs_unavailable` is **not** in that list. It is a statement about the tick — the
gate could not reach its data at all — rather than about a pair, and counting it in the tally
would put it in an arithmetic it does not belong to.

## Publish the counts, not just the survivors

`state["scout"]` carries `pairs`, `scanned`, `entered` and `excluded` (a code-to-count map).
The console's most-viewed screen state is the one where nothing qualified — *"Scanned 412
pairs. 38 entered the tradable universe."* — and it renders from these numbers rather than
from a log line.

**`scanned == entered + sum(excluded)` is an identity, and a test asserts it**, including on
a tick where four different rules fire at once. A pair that fell out of the filter without a
code would leave that sentence silently untrue.

## Two rules that need their reasoning stated

### The tick grid, which is what `tick_size` is doing in the Locked Decision

`target_pct` and `stop_pct` of the entry price must each exceed one `tick_size`. On a pair
whose tick is coarse relative to its price, a −1.5% stop rounds onto the entry price itself
and **the position has no stop at all**. Excluding such a pair is the only fail-closed
answer, and it is arithmetic over the pair's own rules rather than a threshold anyone chose.

The comparison is `<=`, not `<`: a tick exactly equal to the stop distance puts the stop on
the first step away from the entry, which is the smallest expressible stop rather than a
usable one. `test_the_tick_grid_boundary_is_strict` pins that, because an implementation
using `<` passes every other test in the file.

**Both barriers are checked, not just the nearer one.** The stop is nearer under the
committed config and would bind on its own, but "the stop is always nearer" is a property of
two numbers the operator may retune, and an engine that assumed it would stop enforcing the
target silently the day they crossed.

### Two crypto-quoted codes, and why not one

Invariant 7 defines a crypto-quoted pair as one whose quote is "BTC, ETH, or **any
non-stable asset**". That sentence needs a set of stable assets. `AssetPairs` carries no
asset class, so it is not derivable at runtime; the set is
`trading.stable_quote_currencies`, supplied by the operator.

**When that set is absent, a quote that cannot be shown stable is excluded** — the lead's
ruling of 2026-09-10. `scout` is the sole authority on the tradable universe, so its errors
run in one direction: over-including risks a trade the operator explicitly disabled, while
under-including costs an opportunity that recurs on the next tick and every tick after.

Engine 2 `market_data_recorder` gets the **opposite** answer for the same question, and that
asymmetry is deliberate rather than an inconsistency: for a recorder the irreversible error
is losing order-book history that cannot be recovered afterwards. *Fail-closed is not a
direction — it is a question about which error is irreversible.*

The two codes are separate because a universe that shrank **by policy** and one that shrank
**because nobody supplied a config key** look identical from the outside, and only the second
is a fault somebody must fix.

**Absent and empty are different answers.** An absent key means nobody has decided; an empty
set is an operator saying "none of them are", which is a decision and excludes under the
ordinary `crypto_quoted` code.

## The sizing arithmetic exists twice, on purpose

Engine 11 `risk` sizes the position; this filter asks whether a position is possible at all.
Contract rule 3 forbids one engine importing another, so the arithmetic is written twice —
identically, including which side of the book each question is asked of:

```
target_notional = equity x risk_fraction_per_trade / stop_pct
qty             = round_down(target_notional / ask, lot_decimals)
value           = qty x bid
```

The **ask** prices the entry, because it is the worst price a buy could pay and a higher
assumed price yields fewer units; the **bid** values the position, because it is the lowest
it could be worth. The lead's ruling of 2026-09-10.

**`test_the_sizing_agrees_with_engine_eleven` in `tests/engines/test_scout.py` is what holds
the two copies together.** It runs the real engine 11 over the same published state and
requires `scout` to include a pair if and only if `risk` approves it, over a table that
straddles `ordermin` by one lot increment in each direction. If you change the sizing here,
that is the test that should stop you. Engine 11's `README.md` names it too.

## Affordability across currencies: ruled, not guessed

**A pair whose affordability cannot be computed is excluded, under `no_fx_rate`.** Ruled by
the operator on 2026-09-10.

`target_notional` derives from equity, which invariant 7 expresses in
`trading.base_reporting_currency`; the balance it must be compared against is in the pair's
**quote** currency. Comparing them needs an FX rate. Invariant 7 says one is converted "at
the trade timestamp", so the intent exists and only the mechanism is missing — nothing in
this system publishes a rate.

I escalated rather than choosing, and declined to mint a code on the grounds that it would
be inventing trading behaviour. **The lead ruled the other way and the distinction is worth
keeping:** what was refused to Agent A was *inventing a fact about the world* — a heuristic
that would claim to know which quotes are crypto and be wrong on real Kraken data.
**Excluding a pair you cannot prove affordable claims nothing.** It is the same shape as
`quote_not_provably_stable` above, which is why the two read as siblings.

**Engine 11 `risk` carries the identical comparison and the identical refusal.** It has had
it since spec 35; no test ever reached it, because no fixture had a pair whose quote is not
the reporting currency *and* a balance in it. It surfaced while this engine was being
written — the third caller of the same arithmetic — rather than by anything failing.

**It costs nothing today, and that is the point rather than a caveat.** No pair reaches it
while `allow_crypto_quoted` is false and every fixture quote is the reporting currency. It
closes the hole before that flag is ever turned on — and
`test_a_crypto_quoted_pair_is_excluded_unless_the_operator_allows_it` is the test that used
to walk straight through it, which is how it was found.
