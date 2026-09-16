# Trading Invariants

These rules protect real money. They outrank tests, deadlines, convenience, and your own judgement.

**If a gate blocks something and a test fails, the test is wrong.** Never weaken, disable, comment out, add a bypass flag to, or delete a gate to make anything pass. If you believe an invariant is incorrect, stop and escalate to the lead. Do not edit it yourself.

## 1. Live trading requires three independent switches

Implemented in `platform/live_guard.py`, owned by Agent A, and called once at startup and again whenever mode is read. All three conditions must be true, or the system runs in paper mode.

They are three independent *conditions*, not three read paths — reading all three through the config layer is correct and does not violate the environment-variable rule.

1. Environment variable `ACSOE_LIVE=1`
2. Config field `mode: live`
3. A file at `config/LIVE_CONFIRMED` whose contents equal `context.now` in UTC formatted `YYYY-MM-DD`. Compared against the injected clock, never a direct clock read.

The default in every config file, every test fixture, and every example is `paper`. No code path may promote paper to live implicitly. Any missing, malformed, or stale switch means paper.

## 2. Nothing is hardcoded that the exchange can tell us

| Value | Source |
|---|---|
| Maker and taker fee | `POST /0/private/TradeVolume` |
| `ordermin`, `costmin`, tick size, decimals | `GET /0/public/AssetPairs` |
| Balances | `POST /0/private/Balance` |
| Spread | Live order book |

There is no hardcoded fee, minimum, tick size or precision anywhere in the codebase.

**A cache stale beyond its TTL counts as a failed fetch, and is retained anyway.** Those are two rules sharing a word, and collapsing them into one breaks the kill switch:

- *For trading*, a stale value does not exist. It may never price a hurdle, size a position, or satisfy a gate. That is all "counts as a failed fetch" means.
- *For an emergency liquidation*, it is the last thing the system knows, and knowing it beats being stuck. `clients/kraken/` **retains the last successful balances and the last successful `AssetPairs` metadata** — exactly what rule 14 authorises using, and nothing else — with the timestamp each was fetched, and never discards them on a failure. Only rule 14 may read them.

**Spread and the fee tier are deliberately not retained.** Their only possible reader is the cost gate, and the paper-mode table below says in as many words that an assumed spread invalidates that gate. A retained stale spread would be a loaded gun pointed at the one input that must never have a fallback, and a liquidation does not need it: it sells as a taker at whatever the book is, having already decided that getting flat beats getting a good price.

Discarding on failure would make rule 14 unimplementable at exactly the moment it is needed, so retention is a requirement on Agent A's client, not an optimisation.

### What a failed fetch does, by mode

**In live mode, a failed fetch always blocks.** Blocking is the correct response to not knowing a cost. The single exception is an emergency liquidation under rule 14, which must be able to complete during the outage that triggered it. Nothing else below applies to live mode.

**In paper mode**, so that a fresh clone with an empty `.env` can still start, run its loop, record market data and build candles:

| Failed fetch | Paper-mode fallback |
|---|---|
| Fee tier | Block that pair. No fallback — see below |
| Balance | The **paper ledger** — see below. It is not a fallback that waits for a failed fetch |
| Pair rules | Block that pair. No fallback — a wrong `ordermin` produces invalid orders |
| Spread | Block that pair. No fallback — an assumed spread invalidates the cost gate |

**Balance is the only row of the four that does not block, and since 2026-09-16 it is not a fallback either — it is the paper ledger, below.** Three of the four rows block, and that is the table working rather than an oversight: standing in for a value is only legitimate where it cannot change the answer to *"can this trade pay for itself"*, and the balance is the only one of the four that qualifies.

### The paper ledger, ruled by the operator 2026-09-16

**In paper mode the balance is always `paper.starting_balances` adjusted by every fill the broker has executed — whether or not the real `Balance` fetch succeeded, and whether or not engine 19 has recorded the fill yet (amended 2026-09-16, below).** It is served by the paper broker in `clients/paper/`, so the mode difference stays in the client layer and no engine branches on mode to get an account.

The row above used to promise a fallback "adjusted by simulated fills" that fired only on a *failed* fetch, and **nothing implemented the adjustment**. Two consequences, both found in Phase 6 planning before any position existed. A simulated fill never touches the fetched cash, so engine 11 would size a second position against cash the first had already spent — invariant 6 says never allocate cash the account does not hold. And engine 19's equity is cash plus positions value, so the same cash was counted twice, in the series that moves the drawdown threshold engine 17 freezes on.

With real credentials in paper mode the fetch *succeeds* and returns the real account's cash, which no simulated fill spends either. A fetched balance plus simulated fills describes no account that exists, which is why the ledger is unconditional in paper rather than a failure path. Live mode is unchanged: it reads the exchange, and a failed fetch blocks.

**Amended by the operator 2026-09-16 — *when* a fill enters the ledger.** **The broker's reported balance includes every fill it has executed, including fills engine 19 has not yet recorded.** The broker is the authority on its own cash: a fill it has executed is money it has spent, whether or not the store has caught up. The sentence above that says the ledger is adjusted by every fill *the store has recorded* is superseded on exactly this point.

The operator records the amendment as their own, and names the gap: the original ruling said what the balance is adjusted *by* and not *when*. The broker decides a resting entry's fill when engine 21 asks for it, part-way through a tick, and engine 19 records it at the end of that tick; a balance counting only recorded fills therefore lagged the broker's own knowledge by one tick. Engine 21 counts a position opened by this tick's fill in the portfolio value — correctly, since a live exchange's fetched balance already reflects a fill that printed before the tick — so on the fill tick paper equity counted the notional twice: once as unspent cash and once as the position. `peak_equity` took the inflated figure, engine 17 read a 40% drawdown the next tick and froze the account, and every later tick stayed frozen. **Every paper trade would have frozen the account.** Found by A's spec 87 rehearsal; see the tracker.

**The criterion that would have caught it is now required**: equity on the fill tick equals equity on the tick before it, within the fill's own cost, proven capable of failing by breaking the broker so the fill is excluded.

**The store remains what a restarted daemon rebuilds the ledger from.** A fill the broker executed and the store never recorded — a process that died between the two — must be absent from the rebuilt ledger *and* from the rebuilt positions, so the two still agree; the fix must prove that rather than assume it.

**A fallback's legitimacy is per-reader, not per-key.** The row above licenses the balance on one stated ground — a fallback is only legitimate where the value it stands in for cannot change the answer to *"can this trade pay for itself"* — and that test is applied to **the reader**, not to the key. Engine 11 `risk` sizing a position satisfies it. Engine 9 `order_book` does **not**: there the balance *is* the basis notional, the basis notional sets how deep the walk goes, the walk sets the estimated slippage, and slippage is one of the four terms of `friction`. A stood-in balance would therefore price the hurdle, which is the one thing this rule forbids. So engine 9 omits its estimate and publishes `no_quote_balance`, and engine 10 — a gate — refuses on the absent key.

Two engines reading one key and answering differently is not an inconsistency to tidy away; it is this rule working. Raised by C-models while building engine 9, Phase 6, 2026-09-16, and recorded here rather than in that engine's README so the next reader of a fallback applies the test to their own use of it. The same shape as the config rule in `code-standards.md`: the landing order is universal, the resting state is per-reader.

**A ledger balance is not recorded as a fallback fired.** It is what the account *is* in paper mode, not a substitute for something that failed, and the run's mode already says every figure derived from it is simulated. The rule below — every decision affected by a fallback records which fallback fired — is unchanged for the three rows that block and for live mode.

**The fee-tier row named a tier and told the system to ~~assume~~ it. That is retired, 2026-09-10.**
It was never implementable.
`AssetPairs` carries no fee schedule, so there was no runtime source the named tier could be read from,
and the only way to honour the row was to write a fee percentage into the code — which is the hardcoded
fee `AGENTS.md` forbids in its first paragraph, and which would be stale the day it was written.
A fee nobody fetched invalidates the cost gate for exactly the reason a spread nobody measured does:
both are terms of `friction`, and a gate priced on a guess is not a gate.
**A confirmed pair with no fee data blocks that pair.**

*The retired wording is deliberately not quoted here.* `scripts/verify.py`'s `docs_vocabulary`
criterion carries a row for it, qualified so it only fires on a line that also tells the system to
assume one — and a quotation of a defect is the one thing that will always look exactly like the
defect. `context/ai-workflow-rules.md`'s own retired-vocabulary section is the one place licensed to
name it, because cataloguing superseded things is that section's whole job.

The consequence, stated plainly rather than left to be discovered: with an empty `.env` the private calls fail, `TradeVolume` returns nothing, and **every pair blocks at the cost gate**. A fresh clone still runs the loop, still records the order book, and still builds candles — which is what the recording exists for and cannot be recovered later — but it takes no paper trades and produces no rejection rows past the cost gate. That is the honest description of an unauthenticated clone, and it is preferable to one that generates a research dataset priced on a fee somebody guessed.

Every decision affected by a fallback records which fallback fired. A fallback is never optimistic: it may only make the system less willing to trade.

These are the paper-mode fallbacks, and rule 14 is the only other exception in this document. Where any other rule here says a failed fetch blocks, it means live mode, and this section is what governs paper.

## 3. Every gate is fail-closed

A gate that errors blocks. A gate that cannot reach its data blocks, subject only to the paper-mode fallbacks in rule 2 and to the emergency liquidation in rule 14. A gate that returns an unparseable result blocks. Absence of a "no" is never a "yes".

Gate engines: 4 (data guard), 7 (scout), 10 (cost), 11 (risk), 13 (anomaly), 15 (skeptic), 16 (decision), 17 (safety).

**Engine 16 `decision` became a gate by operator ruling 2026-09-16.** It blocks on exactly one
condition, and the condition is deterministic arithmetic over `state`: **every approving engine
judged *this* tick's candidate** — the same pair engine 7 chose and the same decision bar. A pair
disagreement, a payload carrying a previous bar, an absent input where the chain says the engine
ran, or an approval carrying no quantity all block. Its other work — composing the order intent
engine 18 reads — is composition, not decision, and its README says so in those words.

## 4. No model output may bypass a gate

No confidence score, probability, ensemble weight, or router decision may skip, soften, or override engines 4, 7, 10, 11, 13, 16, or 17. A model may only ever make the system *less* willing to trade, never more.

Engine 16 joined that list with its gate status on 2026-09-16: it contains no model — its check is
a comparison of pair names and bar timestamps — so nothing a model publishes may override it.

Rule 14 describes the one override in the system. It is not a model output, and it moves the system towards less exposure, so it does not weaken this rule.

**Engine 7 `scout` is deterministic and is protected.** Its universe filter is arithmetic over `ordermin`, `costmin`, tick size, live spread and balance, and its candidate ranking is a deterministic score over features. It contains no model, so nothing may override it.

Gate 13 `anomaly` and gate 15 `skeptic` are both machine-learned, and they are treated differently on purpose. Anomaly is unsupervised outlier detection over *market data* — velocity, volume, spread — and its output is a threshold on a distance. It judges whether the market is broken, not whether this trade is good, so it is a data-quality gate like `data_guard` and is protected. Skeptic is supervised meta-labelling over the *predictor's own calls* — a learned opinion about this specific trade. That is what makes it a model in the sense rule 4 means, and why it is excused from the list: "a model must not override it" is meaningless for a model. Both can only veto, never approve. Both remain fail-closed under rule 3.

## 5. A trade must clear the live cost hurdle

```
friction  = live_maker_fee + live_taker_fee + measured_spread + estimated_slippage
net_edge  = expected_move − friction
TRADE ONLY IF net_edge > hurdle_multiple × friction
```

`net_edge` is what you compute. The rule is the third line. They are not the same thing.

Friction assumes **maker on entry, taker on exit** — the worst realistic case, since a stop must always exit as a taker. Never assume a maker exit when sizing the hurdle, even though target exits may achieve one.

Reference values, for sanity-checking only — never for use in code:

- Kraken tier 1 (fresh account): maker 0.40%, taker 0.80%. Friction ≈ 1.25% round trip.
- Kraken tier 3: maker 0.22%, taker 0.38%. Friction ≈ 0.65% round trip.

Break-even win rate, given the +3% / −1.5% barriers: at tier 1 a win nets +1.75% and a loss costs −2.75%, so p = 2.75 / 4.50 ≈ **61%**. At tier 3 a win nets +2.35% and a loss costs −2.15%, so p = 2.15 / 4.50 ≈ **48%**.

## 6. Position sizing rules

- Risk per trade never exceeds the configured fraction of total account equity.
- A position smaller than the pair's `ordermin` or `costmin` is a **rejection**, logged with a reason. Never round up to meet a minimum.
- Never allocate cash the account does not hold in that pair's quote currency.
- One open position per pair. A configured maximum of concurrent positions across the portfolio.

## 7. Quote currency rules

All Kraken quote currencies are scanned, but:

- A pair is only executable if the account holds spendable balance in that quote currency.
- Crypto-quoted pairs (quote is BTC, ETH, or any non-stable asset) are **disabled by default** behind `allow_crypto_quoted: false`. Profit in such a pair is denominated in a volatile asset, which is a second directional bet the system did not choose to make.
- All PnL, equity, risk limits, and reporting are expressed in a single `base_reporting_currency`, converted at the trade timestamp.
- Fiat-quoted pairs carry FX exposure against the reporting currency. This must be recorded per trade, not silently absorbed into PnL.

## 8. Entry and exit rules

- Entry is always a **post-only limit** order (`oflags=post`). If it would cross the book, Kraken cancels it — that is the intended behaviour.
- If an entry order is unfilled after the configured window, cancel it and abandon the candidate. **Never chase with a market order.**
- That cancellation still happens while the manage chain is holding on a `data_guard` block. It is a decision about elapsed time, not about price: it reads `context.now`, needs no market data, and reduces exposure. The hold suppresses **exits**, never this.
- A `close_all` cancels every resting entry order immediately, regardless of that window, before positions are closed. An uncancelled post-only limit is not a position, so it survives a liquidation and can fill minutes later — re-opening exposure after the emergency stop was pulled. The kill switch is not complete until the book is clear of both.
- Exits on target may be maker. Exits on stop must be immediate and may be taker.
- Every order carries a `userref` for idempotency. Never place an order without checking whether that `userref` already exists.

## 9. Time is injected, never read

Engines receive `context.now` and must never call `datetime.now()`, `time.time()`, or equivalent. This is what makes historical replay faithful and what prevents look-ahead bias. A direct clock call inside an engine is a defect.

## 10. No look-ahead, ever

- A feature at bar *t* may only use data available at the close of bar *t*.
- Labels use future data by definition and may only exist in the training pipeline, never in the live path.
- Walk-forward folds are purged and embargoed; overlapping label windows must not straddle a train/test boundary.
- Any model fitted on data the live system would not have had is invalid, and results derived from it must be discarded.

## 11. Recorded data is immutable

Raw market recordings are append-only. Never edit, backfill, interpolate, or "clean" a recorded file in place. Corrections belong in a derived layer with the original preserved.

## 12. Rejections are logged before the pipeline stops

When a gate blocks, the memory engine still runs. A rejection that is not written to storage is lost research data and counts as a defect equal to a lost trade.

**The guard chain records every blocker, not just the one that stopped the pipeline.** The guard chain never breaks early, so two guards can block on the same tick — typically `data_guard` on bad data and `safety` on an account condition. `state["trading_blocked_by"]` holds the first, because that is what gates the opportunity chain, but engine 19 writes one `block_records` row per blocker with `is_primary` set on the first only.

Without that, a `safety` block co-occurring with a `data_guard` block would leave no trace in `block_records` at all, and this rule would promise more than it delivered. The command row `safety` writes is a record of the *decision*; the block row is the record of the *evaluation*, and research needs both.

**An engine that errored is recorded too, and it is the tick this rule most needs.** Ruled by the operator 2026-09-16. When an opportunity-chain engine returns `ERROR`, engine 19 writes a `block_records` row with `blocked_by` the engine's name, `status = 'ERROR'`, and `block_reason` the code `engine_errored` — **never a `reason_code` the engine did not produce.** A reason code is a decision the engine made; an error is the absence of a decision, and the two must not share a field. No `rejections` row is written for it, because no candidate was refused, and the rest of the tick — positions, orders, equity — is recorded exactly as on any other tick. `engine_errored` is mapped in `REASON_PROSE` in the same change that introduces it.

Before this ruling the tick was lost: contract rule 7 empties an erroring engine's payload, engine 19 refused to write a rejection with no `reason_code`, and it raised — so no rejection, no block record and no equity row were written. Each rule was reasonable alone. Found by A's spec 87 rehearsal, reachable only by running the chain end to end. A consequence stated rather than discovered: these rows carry `status = 'ERROR'`, so engine 17's error rate now counts opportunity-chain errors as well as guard-chain ones — which is what an error-rate breaker is for.

## 13. Secrets never enter the repo

API keys come from the environment only. Never logged, never committed, never written into config files, never echoed in error messages or console output. The web console holds no credentials and cannot place orders.

## 14. Emergency liquidation is the one deliberate override

Everything else in this document makes the system less willing to act. This rule is the single place where the system is made *more* willing to act, and it exists because **unknown exposure is worse than a bad fill**.

### When it fires

`close_intent` is set in exactly two ways: an operator presses Close all, or engine 17 `safety` escalates. **`safety` escalates on exactly one condition:**

- **A sustained data outage.** Once `data_guard` has blocked more than `safety.max_consecutive_data_blocks` consecutive ticks — default **15** — `safety` writes `close_all`. The manage chain holds exits while the guard is rejecting data, and a hold that never ends is a position carried indefinitely on data nobody trusts. Fifteen one-minute ticks is one full decision bar: long enough that a websocket reconnect never liquidates the account, short enough that nothing is carried through a second bar.

`safety` escalates only when there are **open positions or resting entry orders**. A resting post-only buy is exposure that has not happened yet; left on the book through a blackout it can open a position into a market the system has already declared untrustworthy.

### The drawdown and loss-streak limits freeze. They do not liquidate

Ruled by the operator, 2026-09-10. Breaching `safety.max_drawdown_pct` or `safety.max_consecutive_losses` makes `safety` write a **`freeze`** row, not a `close_all`. So does the error-rate limit. `close_all` is reserved for the data-outage escalation above and for the operator's own Close all button.

Freeze stops new positions while the manage chain keeps watching the open ones, and the operator decides whether to liquidate.

### A suppressed escalation never swallows a freeze that was independently due

Ruled by the operator, 2026-09-10. `safety` emits at most one command per tick and the more
severe action wins — but `close_all` has its own suppressions: it is not written when there is
no exposure to close, or when `close_intent` is already set. **When the winning action is
suppressed, `safety` emits the strongest action that is not suppressed**, rather than emitting
nothing.

Without this, drawdown plus a data outage on an account with no open position emits nothing,
while the drawdown alone emits `freeze`. More bad conditions would produce less action, which
is the wrong direction for a circuit breaker and is the one shape this rule exists to forbid.

The practical difference is *persistence*, not blocking: `safety` returns `BLOCK` on any tripped
condition either way, so the opportunity chain stops regardless. What was being lost is the
`frozen` mode itself — the console rendered a running system, and the block was re-derived every
tick instead of recorded once. A breaker whose state cannot be read is a breaker the operator
cannot act on.

Found by Agent B while implementing spec 42, against the literal spec, and escalated rather than
fixed: it is a change to what the breaker does.

**The distinction is what the condition is a statement about.** A drawdown or a losing streak is a statement about *past* trades: the data is trustworthy, the positions are being managed correctly, and the strategy is losing. Liquidating on that turns an unrealised loss into a realised one on the system's own authority, at whatever price the book happens to hold, and it does so at the moment the system has the least evidence it is reading the market correctly. A sustained data outage is a statement about *present* knowledge — the system no longer knows what it holds or what it is worth — and that is the case this rule was written for. Unknown exposure is worse than a bad fill; a known bad position is not.

An earlier version of this section listed the drawdown and loss-streak limits alongside the outage as escalation conditions. Engine 17 could not be built against it: the Phase 0 seed carries a breached drawdown, a breached streak, an open position and a resting order all at once, so under that reading the seeded drawdown liquidated the account while the Phase 3 exit criterion required it to freeze, and no fixture could satisfy both. The contradiction is what surfaced the decision.

### What it overrides

When `close_intent` is set the liquidation proceeds regardless of:

- **A `data_guard` block.** The manage chain normally holds when the guard rejects the tick's data, placing no target, stop or timeout exit. A liquidation is not held. The system stops reasoning about price quality and gets flat.
- **A failed fetch, in any mode.** This is the case that matters most and is the easiest to miss: a feed outage is what triggers the escalation, and the same outage is likely failing the balance and order-book fetches. If rule 2's live-mode block applied here, `close_all` would be blocked by the exact condition it exists to answer. During a liquidation, engines 21 and 22 may use the last known good balances and the cached `AssetPairs` metadata **past its TTL**. This is the only place in the system where a stale cache is acceptable.

Constraints that still hold during a liquidation:

- Quantities are still rounded **down** using the cached `lot_decimals`. Rounding down leaves dust; rounding up produces an order Kraken rejects, and a rejected order during an emergency is worse than dust.
- Every order still carries a `userref` and is still checked for idempotency. A liquidation that double-sells is not a liquidation.
- The override applies only to exiting. It never permits an entry, and it never relaxes a gate for a new position.
- Every fetch failure tolerated under this rule is recorded on the resulting trade, exactly as a paper-mode fallback is, so the fill is never mistaken for one priced on good data.
