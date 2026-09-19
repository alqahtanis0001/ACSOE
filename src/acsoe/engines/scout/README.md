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
soften or override this gate. **The universe filter contains no model**, so there is nothing
in it for one to override. That absence is the property being protected, not a coincidence.

**The ordering may read a model, since 2026-09-19** (operator ruling R1, spec 144). With
`scout.rank_feature: expected_move`, the filtered universe is examined in order of engine 8's
expected move. Pairs engines 13 and 8 would refuse are skipped (R11). Invariant 4 as amended
in the operator's words (R12) permits a model's output to order candidates for examination,
provided every gate judges the chosen candidate independently. Which pairs are tradable
never depends on the model. See the ordering section.

## Inputs

| Value | Read from | Published by |
|---|---|---|
| `ordermin`, `costmin`, `tick_size`, `lot_decimals`, `base`, `quote` | `state["exchange"]["pair_rules"]["pairs"]` | 1 `exchange` (A), from `AssetPairs` |
| Per-currency spendable balance | `state["exchange"]["balances"]` | 1 `exchange` (A) |
| `bid`, `ask` | `state["market_sensor"]["quotes"][pair]` | 3 `market_sensor` (A) |
| Total account equity | `store.latest_equity_snapshot()` | 19 `memory`, Phase 4 |
| The feature vector per pair | `state["feature"]["pairs"][pair]` | 5 `feature` (C), Phase 5 |
| Macro columns, for the expected-move ranking | `state["macro_context"]["features"]` | 6 `macro_context` (C) |
| The predictor and the anomaly detector, for the expected-move ranking | `store.model_run_dir(models.prediction_run_id)`, `store.model_run_dir(models.anomaly_run_id)` | trained runs (C) |

Configuration: `trading.risk_fraction_per_trade`, `barriers.stop_pct`, `barriers.target_pct`,
`trading.allow_crypto_quoted`, `trading.base_reporting_currency`,
`trading.stable_quote_currencies`, `scout.rank_feature`, `scout.rank_descending`, and, for
the expected-move ranking only, `models.prediction_run_id` and `models.anomaly_run_id`.

**`state["feature"]` is read only when `scout.rank_feature` names a feature.** With no
feature configured the engine never touches it and its absence is not a fault — which is
what lets engine 7 run unchanged on a tree where engine 5 does not exist. With one
configured and engine 5 silent, the engine blocks; see the ordering section.

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

## One candidate, or none

`state["scout"]["pair"]` carries the single pair the judgement chain will consider. Engines
10 `cost` and 11 `risk` read it directly, and the cross-chain key table in
`engine-contracts.md` fixes that name — **it may not be renamed.** One candidate leaves this
engine, never several.

**`pair` is absent from the payload, never null, when there is no candidate.** Engines 10
and 11 reach it through a `_require` that treats a published `None` exactly like an absent
key, so a null would be handled correctly today; the omission is about tomorrow, when some
consumer reads it without that guard. The same shape `RiskSizing` uses for `qty` on a
rejection.

### PASS, OK and BLOCK are three different answers

| Situation | Status | `pair` | `reason_code` |
|---|---|---|---|
| A pair qualified | `OK` | the candidate | none |
| The universe was computed and is empty | **`PASS`** | absent | `empty_universe` |
| The universe could not be computed at all | `BLOCK` | absent | `scout_inputs_unavailable` |

**An empty universe is `PASS`, not `BLOCK`, and the distinction is the whole reason
`EngineStatus` has both.** `PASS` means "nothing to do this cycle; not an error", and the
orchestrator stops the opportunity chain on it *without* setting `trading_blocked_by`.
Nothing qualifying is this system's honest default state on a small account — the console
renders it as *"Scanned 412 pairs. 38 entered the tradable universe. None qualified."*

Recording that as a block would fill `block_records` with a normal Tuesday and corrupt
engine 17 `safety`'s error rate, which counts those rows. A breaker tripped by ordinary
quiet days is a breaker nobody can leave switched on.

`BLOCK` is reserved for the gate failure invariant 3 describes: this engine could not reach
the data to compute a universe at all — no pair rules, no equity snapshot, no quotes for any
pair.

## The ordering is a feature named in config, and alphabetical until one is named

**Spec 76, Phase 5.** The universe is ordered by the feature at `scout.rank_feature`, in the
direction at `scout.rank_descending`, read from `state["feature"]["pairs"]` as engine 5
publishes it. Invariant 4: a deterministic score over features, with no model in it and
therefore nothing here for a model to override.

The rules, in full, because each of them is a decision and not an implementation detail:

- **One feature, one direction, one tie-break.** No composite, no normalisation, no formula.
  Spec 59 decision 7 made the ranking a *named feature* rather than a score precisely so that
  the choice is the operator's and is visible in one config key.
- **The tie-break is the pair name ascending, in both directions.** Two pairs the feature
  rates equally order by name whichever end of the feature is being taken. `reverse=True`
  would reverse the tie-break with the feature, so the pair taken would move on a flag that
  is meant to order by the feature alone.
- **A pair with no value sorts last and is never dropped.** Null, absent from the feature
  map, and NaN are one fact — this pair has no value for this feature — and it sorts after
  every pair that has one, alphabetically among themselves. A pair with no feature is still
  tradable, and dropping it would silently shrink the universe the filter just computed.
  NaN is included because `modelling/features.py` yields it for an unfilled lookback and it
  compares false against everything including itself, so a NaN left in a sort key orders
  unpredictably rather than loudly.
- **Three ways of being unable to rank, and all three block** with
  `scout_inputs_unavailable`: `state["feature"]` absent, its `pairs` map absent, and
  `scout.rank_feature` naming a feature that is not in engine 5's published `feature_names`.
  Falling back to alphabetical would report a ranking that did not happen, and would be right
  on exactly the ticks where alphabetical agreed — see the history below for why that shape is
  the one thing this engine may not do.

  **The third is the one that hides, and it was missed on the first pass.** A misspelt feature
  name finds no value for any pair, the no-value rule then orders every pair alphabetically
  among themselves, and the engine publishes the misspelt name beside a ranking it never
  performed: no exception, no null, and a candidate that is a real pair from the real universe.
  The per-pair question — does *this pair* have a value — and the whole-universe question —
  does this *feature* exist — are different, and answering both by returning "no value" is what
  made it silent. The empty feature name is the same defect at length zero and was refused from
  the start; a typo of length fourteen behaved differently for no reason anyone would defend.
- **The engine publishes what it used**: `rank_feature` and `rank_descending` in
  `state["scout"]`. `rank_feature` is **null rather than omitted** when nothing is
  configured, because null is the answer — the ordering was alphabetical for want of a key —
  and the spec 75 study's alphabetical control is exactly that distinction.
- **`pairs` stays in scan order and carries no ranking.** The ranking is expressed by
  `pair` and `rank_feature`, in one place. Two expressions of one ordering disagree silently
  the first time a consumer reads `pairs[0]`.

### The history, because the next reader will look for a score

From Phase 3 until spec 76 this ordering was **alphabetical and recorded as an absence
rather than a design.** The operator ruled on 2026-09-10, and the reasoning is worth quoting
rather than summarising, because it is what shaped the rule above about blocking:

> A deterministic score over features is meaningless before features exist, and a
> placeholder score would be a check whose output resembles the claim while the claim is
> untrue — this phase has produced enough of those. The universe filter is the contribution;
> ranking one candidate out of a filtered set is a Phase 5 decision made with real features
> in front of us.

Phase 5 closed it. The mechanism is here; **the feature itself is not chosen by this engine
and is not chosen by B.** It arrives in `config/default.yaml` from the operator's ruling on
the spec 75 ranking study, and the committed config carries `scout.rank_descending` with no
`scout.rank_feature` — so on every tick today the ordering is alphabetical and the engine
publishes `rank_feature: null`. That is the same recorded absence as before, now with the
mechanism behind it built and tested.

### The expected-move ranking (spec 144, operator rulings R1 and R11, 2026-09-19)

`scout.rank_feature: expected_move` is **not a feature name**. It names the predictor's own
output, so the engine matches it before the check against engine 5's `feature_names`.

- **The arithmetic is C's `modelling/ranking.py`.** Engines never import each other, and
  `modelling/` is the package both sides may import. The function loads the runs named by
  `models.prediction_run_id` and `models.anomaly_run_id`, through `store.model_run_dir` as
  engines 8 and 13 do. It scores **only the filtered universe**, and only when that universe
  is non-empty. It skips a pair with an incomplete vector, an anomaly score over the
  detector's threshold, or a DI over the predictor's (R11). The artefacts are loaded once
  per pair of run ids and reloaded when either changes.
- **A skipped pair is dropped from the order, not sorted last.** This is the opposite of the
  feature rule. It **stays in `pairs`**, because it is tradable; it is just not examined. The
  skips are published per code in `rank_skipped`, apart from `excluded`, so
  `scanned == entered + sum(excluded)` still holds.
- **The ranking never blocks on a ranking value.** A universe skipped entirely is a `PASS`
  with `no_rankable_pair`, not `empty_universe`, because the account could trade those pairs.
  Being unable to rank at all blocks with `scout_inputs_unavailable`. That covers no run id,
  a run the store cannot open, an artefact the function refuses, a ranking it cannot
  compute, or the module itself missing. It never falls back to alphabetical, because that
  would report a ranking that did not happen.
- **Published:** `ranked` (the whole order, each pair with its expected move as an exact
  decimal string, as engine 8 publishes it), `rank_skipped`, and `rank_run_ids`.
- **Every gate re-judges the chosen pair from scratch.** No gate reads this ordering.
  `test_the_real_ranking_chooses_engine_8s_best_pair_and_reversing_it_moves_no_verdict`
  (`tests/engines/test_scout_ranking.py`) proves it with no double. It uses the real
  function, a real trained run and the real engines 13 and 8. The chosen pair's expected
  move equals engine 8's recomputed value, and reversing the order moves the candidate and
  no gate's verdict on any pair.
- **With `scout.rank_feature` absent the ordering is alphabetical, exactly as before.** That
  is the operator's baseline for the Phase 7 simulation, and the model is never loaded.

### One thing to know before trusting any ordering test here

Found by mutation rather than by reading, in Phase 3, and it is why spec 76's central test is
a direct one: the engine builds its scan set as `sorted(...)`, so `rank_universe` is always
handed an already-ordered sequence. A ranking that merely returned `tuple(pairs)` therefore
answers alphabetically end to end and leaves every *behavioural* ordering test green. Only a
direct call on input whose arrival order and intended order disagree on **every** element can
tell "orders by the feature" from "preserves what it was given".
`test_rank_universe_orders_by_the_named_feature_and_not_by_arrival` is that call, and
`feature-specs/PHASE-5-TASKS.md` names the seam directly and calls the test not optional.

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
