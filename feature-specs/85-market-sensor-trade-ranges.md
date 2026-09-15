# 85 — Engine 3 publishes each pair's trade range since the previous tick

**Owner:** A — Platform

**Phase:** 6. `engines/market_sensor/` is A's.

## Goal

A resting post-only buy fills when the market trades through its price, and a position's stop or
target is touched when the market trades to it — both *between* one-minute ticks. Top-of-book
quotes sampled once a minute miss both. Engine 3 already drains every trade to build candles; at
the end of this spec it also publishes, per pair, the lowest and highest trade price and the trade
count since the previous tick, so engines 21 and 22 and the fill simulator read one source.

## Implementation

1. `engines/market_sensor/contracts.py`: `MarketSensorState.trade_ranges: dict[str, dict]`, per
   pair `{"low", "high", "trades", "since_ts"}`, prices as exact decimal strings, `since_ts` the
   previous tick's `context.now` as microseconds. A pair with **no trade since the previous tick is
   absent**, never `{"trades": 0}` with a copied price — no trade means no range.
2. The first tick after start has no previous tick: publish no ranges and say so in the README,
   rather than inventing a start.
3. `engines/market_sensor/engine.py`: computed from the same drained trades the candle builder
   consumes, so the range and the candles cannot disagree about which trades happened.
4. `README.md`: the field, the absent-pair rule, and that the range is **trades**, not quotes.
5. Tests in `tests/engines/test_market_sensor.py`: two ticks over a fake stream whose trades are
   known, asserting low, high and count; a silent pair absent; a range never spanning two ticks.

## Scope Limits

- Do **not** decide what a range means for a fill or a barrier. That is B's (specs 88, 92).
- Do **not** change `quotes`, `candles`, `missing_bars` or `bar_closed`.
- Do **not** publish a range for a pair that is not subscribed.

## Check When Done

- Mutation observed red: a range carried across two ticks; the absent pair published as zero.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
