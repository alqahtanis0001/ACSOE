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
qty         = round_down(notional / ask, lot_decimals)
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
| `ordermin`, `costmin`, `lot_decimals` | `state["exchange"]["pair_rules"]["pairs"][pair]` | 1 `exchange` (A), from `AssetPairs` |
| Quote currency | `state["exchange"]["pair_rules"]["pairs"][pair]["quote"]` | 1 `exchange` (A) |
| Quote balance | `state["exchange"]["balances"][quote]` | 1 `exchange` (A) |
| Entry price — **ask** for sizing, **bid** for `costmin` | `state["market_sensor"]["quotes"][pair]` | 3 `market_sensor` (A) |
| Total equity | `store.latest_equity_snapshot()` | 19 `memory`, Phase 4 |
| Open position count | `store.count_open_positions()` | 19 `memory`, Phase 4 |
| Open positions, per pair | `store.open_positions()` | 19 `memory`, Phase 4 |
| Resting entry orders, per pair | `store.resting_orders(intent=entry)` | 19 `memory`, Phase 4 |

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
runs after it, so `state["position_manager"]` does not exist yet. The per-pair reads
added by spec 89 are there for the same reason and from the same tables.

## Output written to `state["risk"]`

On approval: `pair`, `approved`, `qty`, `notional`, `value_at_bid`, `risk_amount`,
`ordermin`, `costmin`, `reason_code`, `fallbacks_used`.

`notional` and `value_at_bid` are **two different numbers and both are published**.
`notional` is `qty x ask`, the cash the order commits at the worst price the buy could
pay. `value_at_bid` is `qty x bid`, what the position is immediately worth and the figure
`costmin` was actually tested against. They are equal only on a zero spread, and
publishing one of them under both names would put the number a decision was *not* made on
into the record of that decision.

**Open for Phase 6: does `value_at_bid` need a column?** The other percentage fields on
this payload are named after `rejections` columns deliberately, so that engine 19 `memory`
fills the table with no translation step between the engine that computes a number and the
table that stores it. `value_at_bid` has no column, because it did not exist when the
schema was written. Two readings, and the decision belongs with engines 16 and 18 in Phase
6 rather than here:

- **Transient.** It is derivable from `qty` and the bid, and the only decision it feeds —
  the `costmin` test — already records its outcome in `reason_code` and its number in the
  rejection prose. Nothing needs to read it back.
- **A column.** It is the figure a real gate decision was made on, and the rejection prose
  is text rather than a queryable number, so research asking "how close were the refused
  candidates to `costmin`" would have to parse sentences.

Noted here now, while the reason it exists is fresh, rather than left for Phase 6 to
reconstruct. A schema change is the lead's approval either way.

**On a rejection, `qty` is absent from the payload entirely** — not `null`, not zero, not
the minimum. There is no field an execution engine could read a size out of, and no field
a later refactor could quietly start filling with `ordermin`.

## Gate conditions

In order, because the order is part of the behaviour:

1. **This pair already has an open position** — `position_open_on_pair`. Invariant 6's
   last clause, "one open position per pair". Checked before sizing, so a refused
   candidate never has a quantity computed for it at all. See below.
2. **This pair already has an entry order resting on the book** —
   `entry_resting_on_pair`. Same rule, same clause; see below.
3. **Portfolio already full** — `max_concurrent_positions`. Also checked before sizing.
   Asked *after* the two per-pair refusals since the lead's ruling of 2026-09-16; see
   below for why the order changed.
4. **Notional exceeds the quote balance** — `insufficient_quote_balance`. Invariant 6:
   never allocate cash the account does not hold in that pair's quote currency. Rejected
   rather than capped to fit: a position quietly resized is no longer the position the
   sizing rule chose, which is the same objection as rounding up to a minimum.
5. **The quote currency is not the reporting currency** — `no_fx_rate`. Affordability
   cannot be *computed*: the notional is in `trading.base_reporting_currency` and the
   balance is in the pair's quote currency, and nothing publishes a rate between them.
   **Ruled by the operator on 2026-09-10**, after it surfaced while engine 7 `scout` was
   being written. This engine has carried the comparison since spec 35 and no test ever
   reached it, because no fixture had such a pair with a balance in its quote currency.
   Refusing claims nothing about the world; inventing a rate or assuming parity would.
   Engine 7 excludes such a pair from the universe under the same code.
6. **Quantity below `ordermin`** — `below_ordermin`. Rejected, never rounded up.
7. **Position value below `costmin`** — `costmin` is tested on the rounded quantity's real
   value **at the bid**, not on the notional the sizing asked for, because rounding down
   can drop the value below the minimum even when the request cleared it.
8. Any input absent, null or unparseable — `risk_inputs_unavailable`. A published `null`
   `ordermin` means the `AssetPairs` fetch failed, and invariant 2 gives pair rules no
   fallback at all; it must never be readable as zero, which would make every position
   trivially large enough.

## One position per pair — spec 89, and it was enforced nowhere

Invariant 6 ends with "One open position per pair. A configured maximum of concurrent
positions across the portfolio." Until spec 89 this engine implemented the second
sentence and **nothing in `src/` implemented the first**: the portfolio cap counts open
positions and never asks which pair they are on, and engine 7 `scout` does not look
either. The gap was invisible because it was unreachable — no engine in phases 0 to 5
could open a position — and Phase 6 makes it reachable, so the gate lands before engine
18 does rather than after.

**A resting entry order refuses a candidate exactly as an open position does.** That is
not an extension of the invariant; it is the reading invariant 14 already applies to
`safety`'s escalation precondition, in as many words: "a resting post-only buy is
exposure that has not happened yet". The arithmetic is unforgiving. A second entry placed
beside an unfilled one is not a second chance at the same trade, it is double the money
at risk from the moment both fill, and by then there is no gate left between them and the
account.

Two reason codes rather than one, because the two states are cleared by different
actions: a position is exited and an order is cancelled, and an operator reading the
rejection row has to know which. Both sentences name the pair and the identifier — the
`position_id` or the `userref`, the latter being the key invariant 8 makes the
idempotency lookup on and the only handle a cancellation has.

Four states deliberately do **not** refuse, each pinned by a test that differs from its
refusing twin in one field:

- **A closed position on the pair.** Otherwise the rule would read "this pair has ever
  been traded", which would walk the system out of every pair it had exited once and
  would look, from the rejection rows alone, exactly like the rule working.
- **A filled entry order.** Whatever it bought is a `positions` row, and that row is what
  the first check reads. Counting the order too would refuse on the same exposure twice.
- **A cancelled entry order.** It is off the book.
- **A resting *exit* order.** The system getting out of something must never stop it
  getting in, and engine 22 will be writing those constantly — a check that read `orders`
  without filtering `intent` would refuse every candidate on a pair being exited.

**Order against the portfolio cap: the per-pair rule is asked first.** Both can be true
at once and either is a correct refusal, so the order decides only which `reason_code`
the rejection row carries — nothing is weakened either way, and no quantity is computed
for a refused candidate either way.

Spec 89 shipped with the cap first, on the argument that a rejection recorded as
`max_concurrent_positions` before spec 89 should still read that way after it. **The lead
reversed it on 2026-09-16**, because that argument weighed continuity against a history
that does not exist and ignored the one number that decides the question: the cap is
**inert at this balance**. `max_concurrent_positions` is 3, and `config/default.yaml`
says on that very key that the balance binds first — at $5,000, 1% risk against a 1.5%
stop is ~$3,333 notional, so the account affords one position. Cap-first therefore does
not shadow the specific clause on a rare tie; with one position open it shadows it on
*every* tick on that pair, which is exactly where invariant 6's per-pair clause is the
rule doing the work. And there were no pre-spec-89 rows to protect: no engine in phases 0
to 5 could open a position, so nothing has ever written a `max_concurrent_positions` row
from a real portfolio.

The cost is the mirror of the old one and is smaller: a query counting how often the
*cap* fires now undercounts. That query is uninteresting while the cap is inert, and a
balance large enough for the cap to bind would bind it on pairs the account does not
already hold, where no per-pair refusal exists to shadow it. Pinned by
`test_a_full_portfolio_that_also_holds_this_pair_reports_the_pair_rule`.

## The entry price: a lead ruling, not a default

**Sizing uses the ask. `costmin` uses the bid.** Ruled by the lead on 2026-09-10 under
spec 41, and recorded here rather than left in the code because it was *decided*.

It had to be decided because there was nothing to correct. Until spec 41 this engine read
`state["exchange"]["pairs"][pair]["last_price"]`, and **nothing in this system has ever
published a price into `state["exchange"]`**: `AssetPairs` carries none, engine 1 fetches
none, and the only `last_price` in the codebase is a column on an open position row. So
the repair was not a re-pointed key. Someone had to choose which price a buy is sized at,
and the choice is a trading decision.

The reasoning, in full, so the next agent can see it was reasoned:

- **The quantity comes from the ask** because the entry is a buy and the ask is the worst
  price that buy could pay. A higher assumed price yields *fewer* units for the same
  money, so the position is never larger than the sizing chose. Sizing at the bid would
  buy more units than the money covers.
- **`costmin` is tested at the bid** because the bid is the lowest the resulting position
  could be valued at. Rounding down and then valuing at the lower side is fail-closed on
  both edges: a marginal position is refused rather than admitted.
- **It does not double-count the spread against engine 10.** The cost gate charges the
  spread as *friction on a round trip*; this gate uses the book to answer *how many units
  the money buys*. Two different questions asked of the same data, and neither answer
  substitutes for the other.

The price comes from `state["market_sensor"]["quotes"][pair]` — engine 3, the market-data
engine, the same publisher the cost gate reads its spread from. **An absent quote, an
absent pair or a non-positive price is a block.** Never a fallback, and never a price
carried over from a previous tick: invariant 2 gives the spread no fallback in any mode,
and a stale price is a fabricated one.

## The balance fallback — the only one left in the system

Spec 37 retired invariant 2's fee-tier row on 2026-09-10. Pair rules block, the spread
blocks, and the fee tier now blocks too, so **balance is the last remaining paper-mode
fallback in this project — and until spec 41 nothing implemented it.** It fell between two
correct decisions: engine 1 deliberately applies no fallback of its own, on the stated
grounds that the consumer is the one that has to record which fired, and the consumer was
reading a `fallbacks_used` key engine 1 never published.

| Mode | `state["exchange"]["balances"]` absent | Recorded on the decision |
|---|---|---|
| `paper` | Size against `paper.starting_balances` | `balance_from_paper_starting_balances` |
| `live` | **Block** | — |
| `replay` | **Block** | — |

`live` blocks because invariant 2 says a failed fetch always blocks in live mode, and the
one exception in that document is rule 14's emergency liquidation, which is not this.
`replay` blocks because the table in invariant 2 is a *paper-mode* table and a gate that
is unsure refuses; that reading is the implementer's and is flagged as such rather than
presented as settled.

Three things this fallback is not:

- **It is not the "currency missing from the map" case.** A `balances` map that was
  published and simply names no EUR is an account holding nothing in EUR, not an outage.
  That blocks, and it never reaches the fallback. Only an *absent* `balances` — engine 1's
  `null`, meaning the `Balance` call failed — does.
- **It is not silent.** Invariant 2: every decision affected by a fallback records which
  one fired. That includes rejections, which are the rows this system produces most of: a
  candidate refused on a tick where the fallback fired carries it too.
- **It is not yet adjusted by fills.** Invariant 2 says the map is used "adjusted by
  simulated fills". The fill simulator is **Phase 6** and does not exist, so this engine
  uses the configured map exactly as written. The gap is recorded here rather than left to
  be discovered: a paper account that has traded will size against its starting balance
  until Phase 6 lands.

## Two rules that are easy to get subtly wrong

**Rounding is down, and it happens before the minimum is tested.** Rounding to nearest
would round a quantity one ulp below `ordermin` *up to* `ordermin` — the rounding-up
defect arriving through a rounding mode rather than an explicit bump. And rounding after
the check would let a quantity that passed `ordermin` be rounded below it and placed
anyway. The number compared against the minimum has to be the number that would actually
be sent.

**The sizing arithmetic exists twice, and one test holds it together.** Engine 7 `scout`
asks whether a position is possible *at all* — the tradable universe — using this same
`target_notional / ask`, round down, value at the bid. Contract rule 3 forbids one engine
importing another, so the arithmetic is written twice on purpose, and two copies only stay
honest while something compares them. **`test_the_sizing_agrees_with_engine_eleven` in
`tests/engines/test_scout.py`** runs this engine over the same published state as `scout`
and requires `scout` to include a pair if and only if this engine approves it, over a table
straddling `ordermin` by one lot increment in each direction. If you change the sizing here,
that is the test that should stop you. `engines/scout/README.md` names it too.

**Nothing here is remembered.** `AGENTS.md` says any remembered order minimum is stale.
There is no constant, no config key and no cache for `ordermin`, `costmin`, tick size or
precision in this engine, and a test reads the source to prove it — because a constant
that happened to match the fixture would satisfy every behavioural test in the file.
