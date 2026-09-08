# Trading Invariants

These rules protect real money. They outrank tests, deadlines, convenience, and your own judgement.

**If a gate blocks something and a test fails, the test is wrong.** Never weaken, disable, comment out, add a bypass flag to, or delete a gate to make anything pass. If you believe an invariant is incorrect, stop and escalate to the lead. Do not edit it yourself.

## 1. Live trading requires three independent switches

All three must be true, or the system runs in paper mode:

1. Environment variable `ACSOE_LIVE=1`
2. Config field `mode: live`
3. A file at `config/LIVE_CONFIRMED` containing today's date in `YYYY-MM-DD`

The default in every config file, every test fixture, and every example is `paper`. No code path may promote paper to live implicitly. Any missing, malformed, or stale switch means paper.

## 2. Nothing is hardcoded that the exchange can tell us

| Value | Source | On fetch failure |
|---|---|---|
| Maker and taker fee | `POST /0/private/TradeVolume` | Block trading |
| `ordermin`, `costmin`, tick size, decimals | `GET /0/public/AssetPairs` | Block that pair |
| Balances | `POST /0/private/Balance` | Block trading |
| Spread | Live order book | Block that pair |

There is no default fee. There is no fallback minimum. A stale cache beyond its TTL is a fetch failure. Blocking is always the correct response to not knowing a cost.

## 3. Every gate is fail-closed

A gate that errors blocks. A gate that cannot reach its data blocks. A gate that returns an unparseable result blocks. Absence of a "no" is never a "yes".

Gate engines: 4 (data guard), 7 (scout), 10 (cost), 11 (risk), 13 (anomaly), 15 (skeptic), 17 (safety).

## 4. No model output may bypass a gate

No confidence score, probability, ensemble weight, or router decision may skip, soften, or override engines 4, 10, 11, 13, or 17. A model may only ever make the system *less* willing to trade, never more.

## 5. A trade must clear the live cost hurdle

Required net edge = expected move − (live maker fee + live taker fee + measured spread + estimated slippage), and this must exceed the configured hurdle multiple of total friction.

Reference values, for sanity-checking only — never for use in code:

- Kraken tier 1 (fresh account): maker 0.40%, taker 0.80%. Friction ≈ 1.25% round trip. Break-even win rate ≈ 61%.
- Kraken tier 3: maker 0.22%, taker 0.38%. Friction ≈ 0.65% round trip. Break-even win rate ≈ 54%.

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
