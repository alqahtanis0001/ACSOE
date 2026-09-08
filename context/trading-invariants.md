# Trading Invariants

These rules protect real money. They outrank tests, deadlines, convenience, and your own judgement.

**If a gate blocks something and a test fails, the test is wrong.** Never weaken, disable, comment out, add a bypass flag to, or delete a gate to make anything pass. If you believe an invariant is incorrect, stop and escalate to the lead. Do not edit it yourself.

## 1. Live trading requires three independent switches

All three must be true, or the system runs in paper mode:

1. Environment variable `ACSOE_LIVE=1`
2. Config field `mode: live`
3. A file at `config/LIVE_CONFIRMED` whose contents equal `context.now` in UTC formatted `YYYY-MM-DD`. Compared against the injected clock, never a direct clock read.

The default in every config file, every test fixture, and every example is `paper`. No code path may promote paper to live implicitly. Any missing, malformed, or stale switch means paper.

## 2. Nothing is hardcoded that the exchange can tell us

| Value | Source | On fetch failure |
|---|---|---|
| Maker and taker fee | `POST /0/private/TradeVolume` | Block trading |
| `ordermin`, `costmin`, tick size, decimals | `GET /0/public/AssetPairs` | Block that pair |
| Balances | `POST /0/private/Balance` | Block trading |

**In paper mode**, a failed fee or balance fetch does not block. Fall back to **tier 1** — the worst tier — and log that the fallback occurred on every affected decision. Never fall back to a better tier, and never apply this exception in live mode. This exists so a fresh clone with an empty `.env` can still run the pipeline and generate research data.
| Spread | Live order book | Block that pair |

There is no default fee. There is no fallback minimum. A stale cache beyond its TTL is a fetch failure. Blocking is always the correct response to not knowing a cost.

## 3. Every gate is fail-closed

A gate that errors blocks. A gate that cannot reach its data blocks. A gate that returns an unparseable result blocks. Absence of a "no" is never a "yes".

Gate engines: 4 (data guard), 7 (scout), 10 (cost), 11 (risk), 13 (anomaly), 15 (skeptic), 17 (safety).

## 4. No model output may bypass a gate

No confidence score, probability, ensemble weight, or router decision may skip, soften, or override engines 4, 10, 11, 13, or 17. A model may only ever make the system *less* willing to trade, never more.

Gates 7 (scout) and 15 (skeptic) are deliberately absent from that list: they are themselves model-driven, so "a model must not override them" is meaningless. They remain fail-closed under rule 3 like every other gate.

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

## 13. Secrets never enter the repo

API keys come from the environment only. Never logged, never committed, never written into config files, never echoed in error messages or console output. The web console holds no credentials and cannot place orders.
