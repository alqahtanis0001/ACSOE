# 28 — Engine 3 `market_sensor`

**Owner:** A — Platform

## Goal

Built 15-minute candles and the `bar_closed` signal: the decision bar the whole opportunity chain
hangs off, produced from recorded data and proved against a committed Kraken OHLC fixture.

## Implementation

1. Create `src/acsoe/engines/market_sensor/` — `engine.py`, `contracts.py`, `README.md`.
   `name = "market_sensor"`, `number = 3`, `is_gate = False`, **guard** chain.
2. `contracts.py` carries **two seams** from `ownership.md`, both consumed by C: the decision-bar
   tick (`bar_closed`) and the 15-minute candles. Land this file early so C can mock it.
3. Build candles with `polars`. Publish into `state["market_sensor"]`, including `bar_closed`,
   which is true only on a closed 15-minute boundary — `architecture-context.md`: new candidates
   are born only when a bar closes, and the loop tick is one minute, so this is false on fourteen
   ticks in fifteen.
4. **A missing candle means no trades, not an error.** Never interpolate one into existence; mark
   it and let the feature layer decide.
5. Prove the build against a committed Kraken OHLC fixture for **three pairs**: every OHLC field
   within one `tick_size` for that pair *as reported by `AssetPairs`* — not a constant — and
   volume within 0.1%.
6. Write `README.md`, and batch the `bootstrap.py` registration request to the lead.

## Scope Limits

- Do **not** compute an indicator, a feature or a signal. Engine 5 `feature` is Phase 5.
- Do **not** make this a gate; engine 4 decides.
- Do **not** take `tick_size` from a constant or a config key. It comes from `AssetPairs` through
  spec 25, per rule 2 of `trading-invariants.md`.
- Do **not** interpolate a missing candle.
- Do **not** widen the timeframe set. Decision bar 15 minutes, loop tick 1 minute; both are locked
  decisions and both live in config.
- Do **not** register the engine yourself.

## Check When Done

- Built candles match the committed fixture for three pairs, every OHLC field within one
  `tick_size` from `AssetPairs` and volume within 0.1%.
- `bar_closed` is true exactly on a 15-minute boundary and false on the other fourteen ticks —
  asserted with the injected clock, never by waiting.
- A gap in the input produces a marked missing candle, not an interpolated one.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
