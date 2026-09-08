# ACSOE — Adaptive Crypto Spot Opportunity Engine

## What this is

A fully automated spot trading system for Kraken. It scans the exchange, finds candidates, subjects each one to a chain of gates, and buys only when the expected move beats every cost with margin to spare. It then manages the position until exit and learns from both the trades it took and the ones it refused.

This is a Master's dissertation project. Its value is the rigour of the rejection machinery and the honesty of the evaluation, not the size of the profit.

## Core philosophy

**Reject first; execute only with verified net edge.**

Most of the system exists to say no. Nine of the twenty-three engines contain no machine learning at all — 1 `exchange`, 2 `market_data_recorder`, 3 `market_sensor`, 4 `data_guard`, 7 `scout`, 10 `cost`, 11 `risk`, 16 `decision` and 17 `safety`. The components that protect capital are auditable arithmetic, not models anyone has to trust.

## What makes it different from a retail bot

1. **It does not predict price.** It predicts which of three barriers price touches first: a profit target, a stop, or a timeout.
2. **Multi-stage fail-closed gating.** Any gate can halt the pipeline. Nothing overrides a gate.
3. **The Skeptic.** A second model whose only job is to find reasons not to trade, plus a dissimilarity check that refuses to predict on market conditions it has never seen.
4. **Rejected-trade memory.** Every refused candidate is logged with its reason and its SHAP explanation, creating a counterfactual dataset.
5. **Cost-adaptive selectivity.** The trade hurdle is computed from the live Kraken fee tier, so the system is stricter when the account is small and loosens automatically as the tier improves.
6. **Alpha, not profit.** Models are promoted on returns that survive subtracting benchmark exposure and a multiple-testing haircut.

## The loop

1. Stream and record market data for every Kraken pair.
2. Build 15-minute candles. Verify them or freeze.
3. Compute features per pair and read BTC/ETH for macro context.
4. Build the tradable universe from live pair rules and current balance.
5. Scout one candidate.
6. Run it through four gates: is the market tradable, how far will it move, does it beat the fees, why should we say no.
7. Enter with a post-only limit order or abandon.
8. Watch the position every minute until target, stop, or timeout.
9. Exit, log the outcome, update the leaderboard.

## Success criteria

1. The system runs unattended in paper mode for weeks without crashing or corrupting state.
2. Every trade and every rejection is logged with a machine-readable reason.
3. The backtest retrains at the same cadence the live system does.
4. Reported performance separates benchmark exposure from selection skill.
5. No gate can be bypassed by any model output.
6. A user clicks Activate and the system runs autonomously.

**A negative result is a valid result.** If the honest conclusion is that no net edge survives Kraken's fees at this account size, that is a finding, not a failure. The system must be built so it can report that truthfully.

## Build order

Structure, then interface, then backend. Nine phases, each gated by an executable check. See `ai-workflow-rules.md`.

## In scope

- Kraken Pro spot markets only
- All Kraken pairs in the scan, filtered down by live economics
- Paper mode as the default operating mode
- Long-only positions
- Historical training from Kraken's downloadable OHLCVT archives
- Live recording of order book and spread data
- A local read-only web console with an Activate button

## Out of scope

- Margin, futures, leverage, and short selling
- Market making and cross-exchange arbitrage
- Cash-and-carry and funding-rate strategies
- Any exchange other than Kraken
- Multi-user accounts, billing, or deployment beyond a single local machine
- Managing anyone else's money
