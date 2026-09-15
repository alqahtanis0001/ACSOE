# Glossary

These terms have precise meanings in this codebase. Do not substitute your own.

## Exchange mechanics

**Order book** — the queue of resting buy and sell offers on a pair. Bids below, asks above.

**Spread** — the gap between the best bid and the best ask. An invisible cost paid whenever you cross it.

**Maker** — an order that rests in the book and adds liquidity. Cheaper fee. May never fill.

**Taker** — an order that crosses the book and removes liquidity. Higher fee. Fills immediately.

**Post-only** (`oflags=post`) — a limit order that Kraken cancels rather than allowing it to execute as a taker. Guarantees the maker fee. This is how every entry is placed.

**Round trip** — one buy plus one sell. Fees are charged per side, so a round trip pays twice.

**Slippage** — the difference between the price you expected and the price you got, because your order consumed more than one level of the book.

**Friction** — this project's umbrella term: fees + spread + slippage, expressed as a percentage of position value, for a complete round trip.

**Hurdle** — the minimum net edge a candidate must show before it is allowed to trade. Derived from friction, never a constant.

**Fee tier** — Kraken assigns it automatically from the better of your trailing 30-day volume or your Assets on Platform. You cannot choose it. Tier 1 is the default for a new account.

**`ordermin`** — a pair's minimum order size, expressed in units of the base currency. From `AssetPairs`.

**`costmin`** — a pair's minimum order value, expressed in the quote currency. From `AssetPairs`.

**Base and quote** — in `SOL/USD`, SOL is the base and USD is the quote. Minimums, decimals, and profit denomination all depend on which is which.

**`userref`** — a client-supplied integer attached to an order, used here for idempotency so a retry never double-places.

## Strategy

**Decision bar** — the 15-minute candle on which features are computed and candidates are born.

**Holding horizon** — 2 to 12 hours. Not the same as the decision bar.

**Loop tick** — the 1-minute cycle that manages open positions. Never generates new candidates.

**Triple barrier** — the labelling method. From a given bar, ask which of three lines price touches first: the profit target (+3%), the stop (−1.5%), or the timeout (48 bars). Three-class label. **What a bar means in that third line, and what happens when one candle touches two barriers, are both settled in `architecture-context.md` under Timeframes and Historical — do not answer either from this entry.**

**Meta-labeling** — training a second model to grade the first model's calls. It sees only the rows where the predictor said BUY, and learns when that call was wrong. This is the Skeptic.

**Dissimilarity Index (DI)** — a measure of how far a live feature vector sits from the model's training data. Computed from the distribution of pairwise distances within the scaled training set, thresholded at a rolling high percentile. Above threshold means the model has never seen conditions like this and must refuse to predict. **Fitted on the predictor's training set, never the Skeptic's subset.** The threshold's leave-one-out distribution excludes every reference row within 48 bars of the row being scored, across all pairs, because the macro columns are shared by every pair on a bar (operator ruling 2026-09-15; spec 68, amendment).

**Regime** — the classified market environment: trending, choppy, or high volatility. DI threshold crossings also signal a regime change.

**Adverse selection** — when your resting order fills because someone chose to sell to you right before the price fell. Measured here as the post-fill 5-minute move.

**Counterfactual** — a rejected candidate, logged with its reason. The record of a road not taken.

## Evaluation

**Walk-forward** — train on a window, test on the next period, roll forward, repeat. In this project the model is **retrained at each step at the same cadence the live system uses** (weekly), not fitted once.

**Purging and embargo** — removing training rows whose label window overlaps the test period, plus a buffer. Without this, the model sees the future and every result is invalid.

**Look-ahead bias** — using information at bar *t* that would not have existed until after bar *t*. The most common and most fatal defect in this kind of system.

**Beta** — the portion of returns explained by simply being exposed to the market. If Bitcoin rose 20% and you made 8%, your beta earned it and your skill lost.

**Alpha** — what is left after subtracting beta. The only number that matters for promotion.

**Deflated metric** — a performance score haircut for the number of models tried, so that picking the best of twenty is not mistaken for skill.

**Brier score** — how well-calibrated probabilities are. Lower is better. A model that says 70% should be right 70% of the time.

**Base-rate Brier** — the Brier a constant prediction of the fold's own target rate would earn, `p(1-p)`. The number every fold's Brier is reported beside; a model that does not beat it has learned nothing. Chosen as the primary comparison because, at a 23.89% target rate, a model that always predicts `stop` is right 51% of the time and a headline hit rate rewards the model that never trades.

**BUY call** — a decision bar on which the predictor's `expected_move_pct` is positive: `p_target × target − p_stop × stop + p_timeout × mean timeout return`, before friction. The cost gate applies friction afterwards. The skeptic trains only on the predictor's out-of-sample BUY calls.

**Uniqueness weight** — a row's sample weight in training: the mean, over its own label window, of one over the number of label windows covering each bar. Consecutive decision bars at a 48-bar horizon share almost all of their window, so twenty million rows are far fewer observations; the **effective sample size**, the sum of the weights, is reported beside every row count, per fold.

**Sharpe ratio** — return divided by the volatility endured to get it.

**Buy-and-hold** — the benchmark. Doing nothing. The thing this system has to beat to justify existing.

**Scout** — engine 7. Deterministic, no model. Builds the tradable universe from live pair rules and balance, then ranks what is left by a fixed score. The one candidate it emits goes to the judgement chain.

## Words that are easy to confuse

**Phase** — a build phase, 0 to 8, from `ai-workflow-rules.md`. What the operator means by "start phase N".

**Chain** — one of the four ordered engine lists in the registry. Never numbered; always named.

- **Guard chain** — 1, 2, 3, 4, 17. Every tick, every mode, never breaks early. Data in, and the account-level circuit breaker.
- **Opportunity chain** — 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, 16, 18. Only when the mode is `running` and nothing has blocked. Stops at the first block or PASS.
- **Manage chain** — 21, 22, 19. Every tick, every mode. Watches positions, exits them, records everything.
- **Offline chain** — 20, 23. Only via `acsoe research`. Never touched by the daemon.

**Stage** — a step in the runtime loop, 1 to 4, from `architecture-context.md`. Never used to mean a build phase.

**Script** — the build log. Each agent writes `docs/build-log/phase-N/<agent>.md`; the lead consolidates into `docs/build-log/phase-N.md` at phase close. When the operator says "update the progress tracker and script", this is the script.

**Execution offset bandit** — not an engine. A small pooled selector inside `engines/execution/` that learns how far below market to place a post-only limit, bucketed by spread tier, with its state in the store. **Deferred to Phase 7 by operator ruling 2026-09-16**: it needs a table that does not exist and a fill history that does not exist either. Phase 6 places every entry at the best bid, which is a recorded absence rather than a chosen rule.

**Paper broker** — `clients/paper/`, B's. The fill simulator and the paper ledger, implementing the same order surface the live Kraken client does and wrapping it in paper mode, so a mode difference never reaches an engine. Fills are pessimistic by rule: a resting post-only buy fills only on a trade strictly below its limit, and a market sell walks the bid side of the fetched book.

## Modes

**Paper** — the default. Full pipeline, simulated fills, no exchange mutation.

**Live** — real orders. Requires all three switches in `trading-invariants.md`.

**Replay** — offline. Historical data through the same engines with an injected clock.
