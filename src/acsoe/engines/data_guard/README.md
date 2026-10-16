# Engine 4 — `data_guard`

**Number:** 4 · **Chain:** guard · **Gate:** **YES** · **Runtime stage:** 1

The first real gate in the system: the engine that refuses to let the loop trade on data
it does not trust, and the block the outage counter is later derived from.

**It judges the feed, never one pair** (D10, operator ruling 2026-09-21). Every condition
below is a statement about the whole subscription: the freshest quote is past the bound,
every quoted pair is crossed, nothing arrived, no pair traded in a bar. One thin pair that
is stale or crossed is that pair's problem, and it is handled per pair downstream — see
[Who judges one pair](#who-judges-one-pair). Until D10 the tick was judged on its *oldest*
quote, and against Kraken's 668 USD pairs some thin pair was always past the bound: the first
smoke run against the real exchange was blocked on 18 of its 22 ticks.

## What it reads from `state`

`state["market_sensor"]`, and nothing else:

| Field | Used for |
|---|---|
| `quotes[pair]["age_s"]` | the heartbeat (freshest age) and the fresh-pair count |
| `quotes[pair]["spread_pct"]` | a crossed book on every pair |
| `missing_bars` | a decision bar in which no subscribed pair traded |
| `stream_available` | wording of the no-data block |

It reads no other engine's output and it never touches a client. Every market-data fault
it judges arrives from one place — which is why the lead ratified the live spread as
engine 3's rather than engine 1's on 2026-09-09.

## What it writes into `state["data_guard"]`

| Key | Meaning |
|---|---|
| `blocked` | Whether this tick was refused |
| `reason_code` | The **primary** finding's code, or `null` |
| `findings` | **Every** finding, each with `reason_code`, `detail` and `pair` (always `null` now: no finding names one pair) |
| `max_data_age_s` | The threshold applied, echoed so a block is readable without the config. **Also the value engine 16 re-checks the chosen pair against**, because engine 16 may not read config |
| `freshest_quote_age_s` | **The heartbeat**: the youngest quote's age, or `null` when no quote carried one. Past `max_data_age_s`, the tick blocks |
| `oldest_quote_age_s` | The oldest quote's age, or `null`. **Recorded, never judged** — one thin pair's silence is not the feed's |
| `pairs_seen` | Quoted pairs this tick |
| `fresh_pairs` | Quoted pairs whose `age_s` is within `max_data_age_s` (the bound itself is fresh). Age only: a crossed but recent quote counts as fresh here |
| `missing_bars` | Decision bars in the published window in which no subscribed pair traded |

`fresh_pairs` over `pairs_seen` is **the fresh-pair fraction** the operator asked to have
recorded with no screen yet (ruling 2026-09-21). It is published on every tick, passing or
blocked: a figure that only appeared when trading stopped would say nothing about the ticks
on which it did not. The quoted pairs that are not fresh are the ones engine 7 excludes for
staleness under `no_live_quote`. **Publishing it in `state` is not persisting it** — `state`
is discarded at the end of the tick, and where (if anywhere) a run's rows keep it is engine
19's and the schema's business, not this engine's.

Every finding is published, not only the one that became the `reason`. A tick can be
stale **and** carry a crossed book, and an operator looking at why trading stopped should
see both rather than whichever the engine happened to check first.

## What it blocks on

| Condition | `reason_code` |
|---|---|
| **The heartbeat**: even the *freshest* quote is older than `data_guard.max_data_age_s`, or no quote carries an `age_s` at all | `market_data_stale` |
| Nothing has arrived at all | `no_market_data` |
| **Every** quoted pair's book is crossed (bid above ask) | `negative_spread` |
| A decision bar in the published window in which no subscribed pair traded | `missing_candle` |

The first three of those are named by the phase criteria. **`no_market_data` is the
fail-closed case invariant 3 requires** — a gate that cannot reach its data blocks — and
it is a separate code from `market_data_stale` on purpose: "Market data is older than the
guard allows" is a *false sentence* when there is none, and it would send an operator
looking for a lagging feed rather than an absent one.

**The heartbeat** (D10 fix 2). Not a zero-quotes test: if 600 of 668 pairs went quiet and
68 kept quoting, "nothing arrived" would never fire, engine 7 would exclude 600 pairs and
nobody would be told the feed was sick. Instead, the tick blocks when no pair has quoted
within the bound — the freshest quote's age is the feed's pulse. The comparison is `>`: a
quote exactly `max_data_age_s` old is alive, the same `<=` engines 7 and 21 use per pair.
**Quotes that carry no `age_s` cannot show the feed is alive** — engine 3 stamps one on every
quote, so this is a defect upstream, and the absence of a no is never a yes (invariant 3).
An age-less quote is skipped when finding the freshest; if every quote is age-less, the
tick blocks.

**Every pair crossed.** A crossed book on all of them at once is not a market but a corrupt
feed — a bid/ask swap in a parser, say. Left to engine 7 alone it would read as every pair
excluded under `no_live_quote`: an empty universe, a quiet PASS, and the parser defect
hidden behind it. One crossed pair among good ones is that pair's.

## Who judges one pair

The per-pair halves of what this engine used to judge moved, in the same change, to the
engines that judge pairs. **All of them read the one bound, `data_guard.max_data_age_s`** —
`MAX_DATA_AGE_KEY` in `contracts.py` — and because engines do not import each other each
names the string itself; `test_the_staleness_key_is_shared_by_the_three_gates` asserts they
agree (D10 fix 1: two numbers meaning "too old" drift the moment one is tuned).

| Engine | What it does with one stale or crossed pair |
|---|---|
| 7 `scout` | Excludes it from the universe under the existing `no_live_quote` reason |
| 16 `decision` | Re-checks the **chosen** pair's quote before any order (D10 fix 3), against this engine's published `max_data_age_s` |
| 21 `position_manager` | Decides no barrier for a position whose **own** pair's quote is absent, age-less, stale or crossed, and publishes `hold_reason: pair_quote_not_live` on that position's row. Every other position is managed normally. A liquidation never holds |

The tick-level manage-chain hold, `data_guard_blocked`, is still this engine's: it happens
only when this gate blocks, i.e. when the *feed* cannot be trusted.

Every code has a matching entry in `REASON_PROSE` in `console/format.py`. **A code that
is not in that map renders as "No reason was recorded." silently, with no error
anywhere** — so the codes are fixed, were agreed with Agent C, and
`tests/engines/test_data_guard.py` asserts the map contains every one the engine can
emit, deriving the list from this engine's own constants so it cannot decay.

## What it does not block on

- **One stale, crossed or age-less pair among live ones.** That pair is excluded by engine
  7, refused by engine 16 if chosen, and held by engine 21 if a position is on it — see
  [Who judges one pair](#who-judges-one-pair). A half-dead feed (some pairs quiet, some
  quoting) passes here and is visible in `fresh_pairs`.
- **A zero spread.** This gate blocks on a *crossed* book. A zero or absent spread is
  engine 10's refusal to make — invariant 2 says an assumed spread invalidates the cost
  gate — and that is a different refusal in a different place.
- **A failed exchange fetch.** Engine 1 reports those; engines 10 and 11 block on them.
  This gate judges *market data*, not the account picture.
- **The outage count.** Counting consecutive blocked ticks and escalating is engine 17
  `safety`, which is Phase 3. This engine does not write to `block_records` either —
  engine 19 `memory` is the single writer of relational rows, in Phase 4.

## What `missing_bars` counts, and what it therefore blocks on

**A bar in which *no subscribed pair traded at all*.** Engine 3 pools the timestamps
across every pair it published candles for, so this gate fires on a whole-subscription
silence — a feed-level fault — and never on one pair being quiet, which is ordinary
market behaviour and is the feature layer's to mark.

That is the ruling of 2026-09-13, taken after C-2 observed that the field pools pairs and
A measured what the pooling does: with two pairs, one missing two bars the other traded
in, the field is empty; at the 234 pairs the archive now holds it is empty on essentially
every tick. The union stays deliberately. A per-pair reading here would block the tick
every time any thin pair skipped a bar, which is most ticks, and a gate that blocks
always is a gate that gets disabled.

So read the reason string as "the feed went silent", not "some pair had a hole". The
counterpart sentences are in `engines/market_sensor/README.md` and in both engines'
`contracts.py`.

## The missing-candle rule is not a contradiction

`architecture-context.md` says a missing candle in the **historical archive** means no
trades occurred and is *not* a data error, and spec 30 forbids the loader from
interpolating one. Both of those hold, and so does this gate.

**The loader must never *invent* a bar. This gate must never *act* on a series with a
hole in it.** Fail-closed points in opposite directions for labelling and for trading: a
synthesised candle poisons a label, and acting on a gap risks money on a price nobody
observed. Someone "fixing" one of them by breaking the other is the hazard worth naming,
which is why it is stated here, next to the constant in `contracts.py`, and in a test.

## It has no escape hatch

`is_gate = True`, matching the registry table, which `is_gate_matches_registry` asserts.
There is no bypass parameter, no warn-only mode, and no model output that can override it
— invariant 4. `AGENTS.md`: invariants outrank tests, and a test that fails because a gate
blocked is the test that is wrong.

**A block here does not stop the guard chain.** `safety` still runs on the same tick and
every blocker is recorded; the orchestrator owns that, and this engine simply reports
honestly. `tests/engines/test_data_guard.py` proves it by driving the **real**
`Orchestrator` with a second guard behind this one — an engine cannot prove a property of
the chain it sits in.

**A block does not stop recording either.** Engine 2 has already run and the archive is
written regardless: a block says the data cannot be *traded on*, not that it is not worth
keeping. Data recorded during an outage is how the outage gets analysed.

## Thresholds

`data_guard.max_data_age_s`, from config, and nothing else.

**A missing key raises.** `config.get` refuses rather than returning `None`, the
orchestrator turns that into `ERROR`, and `ERROR` blocks. That is the correct fail-closed
answer for a threshold nobody has set, and a `KeyError` naming the key is better
documentation of the gap than a placeholder would be. Until the operator supplied it
(120 s, 2026-09-09) `data_guard_blocks_bad_data` reported **PENDING naming the key** rather
than FAIL — because a *configured* data guard did not exist yet, which is what PENDING
means. Engines 7 and 21 read the same key with no default either; engine 16 reads this
engine's published copy.

## The fixtures

`BAD_DATA_SCENARIOS` in `contracts.py` maps `clean`, `stale`, `negative_spread`,
`missing_candle` and `no_market_data` to a `state` ready to hand to this engine.

They live in this engine's contracts module rather than in `scripts/verify.py` because
the fields they set belong to engines 1 and 3 — a gate that hardcoded another engine's
field names in a fixture would be asserting on a shape it does not own.

**Each bad scenario differs from `clean` in exactly one respect**, asserted by a test. A
fixture that was stale *and* crossed would let a gate that only checked staleness pass the
negative-spread case.

**Every scenario quotes one pair, and with one pair the oldest quote and the freshest are
the same quote** — which is how the engine judged the oldest for a fortnight while
`REASON_STALE` said "the freshest", and no test could tell. The D10 tests in
`tests/engines/test_data_guard.py` therefore re-quote the clean scenario across several
pairs (`several(...)`): a half-dead feed that passes with its fraction recorded, a dead one
a single age away from it, and every-pair-crossed one pair away from three-of-four.

**Use `bad_data_state(name)` if you intend to modify one.** It returns a deep copy;
`dict(BAD_DATA_SCENARIOS[name])` copies only the outer layer and shares
`state["market_sensor"]` with the module-level fixture, so a caller that writes into it
silently changes every consumer that runs afterwards. That happened once in this engine's
own tests, and the failure surfaced three tests away from the cause.
