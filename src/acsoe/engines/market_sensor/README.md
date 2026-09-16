# Engine 3 — `market_sensor`

**Number:** 3 · **Chain:** guard · **Gate:** no · **Runtime stage:** 1

The decision-bar clock and the market-data view. Everything the opportunity chain hangs
off starts here.

## What it reads from `state`

**Nothing.** It reads the feed and the injected clock, not another engine's output.
`trade_ranges` needs to know when the previous tick was, and that arrives on
`context.previous_now` — a `core/` field, not `state` and not another engine.

## What it writes into `state["market_sensor"]`

| Key | Cadence | Meaning |
|---|---|---|
| `bar_closed` | per bar | True only on the tick where a 15-minute decision bar completed |
| `closed_bar_ts` | per bar | The opening second of the bar that just closed, or `null` |
| `interval_s` | — | The decision bar in seconds, from config |
| `candles` | per bar | Closed candles, oldest first: `pair`, `ts`, `open`, `high`, `low`, `close`, `volume`, `trades` |
| `missing_bars` | per bar | Bar openings inside the covered range in which nothing traded |
| `quotes` | **per tick** | Per pair: `bid`, `ask`, `spread`, `spread_pct`, `age_s` |
| `trade_ranges` | **per tick** | Per pair: `low`, `high`, `trades`, `since_ts` — what **traded** since the previous tick |
| `stream_available`, `trades_seen` | per tick | Feed health |

Money is an exact decimal string everywhere — never a `float`. The validator in
`core/contracts.py` refuses a `Decimal` and *accepts* a `float`, so the reflexive cast
on hitting that refusal is the dangerous mistake.

## `trade_ranges` — what happened *between* ticks

Spec 85, Phase 6. Read by the fill simulator (B, spec 88) and by engines 21
`position_manager` and 22 `exit`.

A resting post-only buy fills when the market **trades through** its price, and a
position's stop or target is touched when the market **trades to** it. Both happen
between one-minute ticks, and a top-of-book quote sampled once a minute misses both:
the quote says where the book was at the instant it was read, not where the market
went in the fifty-nine seconds nobody looked. So engine 3, which already drains every
trade to build candles, also reports per pair the lowest and highest price that
actually traded and how many trades there were.

**It is trades, not quotes.** A book that quoted 100 and never traded there produces
no range at 100. That is the whole point of the field and it is the one thing a reader
is most likely to assume the other way round.

**A pair with no trade since the previous tick is absent.** Never `{"trades": 0}`, and
never a copied price. `TradeRange` refuses a zero count at construction, so the rule
is structural rather than remembered: a consumer asking for a silent pair gets a
`KeyError`, which is a question it has to answer, rather than a range of nothing at a
price the market never traded at — which would tell a barrier check the market touched
it.

**The window is `(since_ts, now]`**, half-open at the bottom. Consecutive ticks
therefore tile the timeline with no overlap, so **a range never spans two ticks** and
no trade is ever counted twice. Closed at the top at `context.now`, because a trade
stamped after the tick is clock skew and using it would be look-ahead.

**The first tick of a process publishes no ranges at all**, and so does the first
tick after a restart. There is no previous tick to measure from, and the honest answer
to "what traded since a moment that never happened" is nothing, rather than an
invented start. That second case is the one that matters: a position restored from the
store would otherwise be checked against a window the stream had only just begun to
observe.

**`since_ts` is `context.previous_now`** — the real stamp of the previous tick, in
microseconds. It is **not** `context.now` minus `loop_tick_s`. That arithmetic is what
`bar_closed` uses and it is sound there, because `bar_closed` asks about an *index* and
fires exactly once however late the loop ran. An *interval* is different: on an
overshoot the trades inside it would fall in no range at all, and a stop touched there
would be missed by engines 21 and 22. `EngineContext.previous_now` was added to `core/`
in Phase 6 for exactly this, after A found the hole while building this field. Because
it is the real stamp, a late loop produces a **longer** range rather than a hole.

### The mixed cadence is deliberate

`quotes` and `trade_ranges` are per tick; `bar_closed` and `candles` are per bar. That looks like two
engines squashed into one and is not. They are both statements about the **market
feed**, and engine 4 `data_guard` blocks on three market-data faults — stale data, a
negative spread, a missing candle — which should all arrive from one place rather than
two. The lead ratified this on 2026-09-09: **engine 1 is the account engine and engine
3 is the market-data engine**, so the live spread lives here and not on engine 1.

## `bar_closed` — the one boolean the opportunity chain depends on

Engine 5 `feature` is first in the opportunity chain and returns `PASS` when
`bar_closed` is false, which stops the chain on roughly fourteen ticks in fifteen. **No
other engine may infer the bar boundary for itself**, and the orchestrator does not know
about bars at all: cadence is a property of the candle stream, not of `core/`.

It is **not** `now % interval == 0`. `context.now` is stamped from a real clock and
carries microseconds, so an exact-boundary test would essentially never fire. The test
is whether the bar *index* changed since one tick ago:

```
bar_closed = (now // interval) != ((now - loop_tick) // interval)
```

Stateless by construction, which is the requirement — `state` is fresh every tick and an
engine may not carry anything across cycles, so there is nowhere to keep "the bar we
last saw". It fires exactly once per bar in a regular loop, and still fires **once** if
the loop ran late or skipped a tick, which is the case that matters when the daemon has
been busy.

## Candles come from trades, and only from trades

A candle is a statement about what *traded*. Building from a ticker stream would
manufacture a candle for every quiet minute, which is the same lie as interpolating one.

`polars` does the grouping — it is the columnar part and where it earns its keep — with
`pl.Decimal` columns, so open/high/low/close/volume come back as exact `Decimal`s and
never touch binary float. A `float` price arriving at `build_candles` is **refused**,
not rounded into place.

### A missing candle is reported, never invented

**A bar in which nothing traded produces no candle.** Its timestamp appears in
`missing_bars`; nothing fills, forward-fills, resamples or smooths one into existence,
and there is deliberately no flag that does.

**`missing_bars` is bars in which *no subscribed pair traded at all*, not bars a
particular pair missed.** The timestamps are pooled across every pair this engine
published candles for, so a bar is only listed when the whole subscription was silent —
which is a feed-level fault and is what engine 4 `data_guard` blocks on. A single pair
going quiet for a bar is ordinary market behaviour, it is not listed here, and marking it
is the feature layer's job: engine 5 counts each pair's holes from that pair's own
candles, which this engine already publishes with the pair on every one.

Measured rather than assumed, 2026-09-13, and stated because the name suggests otherwise:
with two pairs, one of them missing two bars the other traded in, this field is empty.
With 234 pairs it is empty on essentially every tick. Ruled by the lead the same day after
C-2 raised it from the consumer side — the union stays, because a per-pair reading here
would have `data_guard` block permanently on the ordinary fact that a thin pair did not
trade.

This is load-bearing rather than tidy. Phase 4's triple-barrier labelling walks forward
from each decision bar to decide whether the target, the stop or the timeout came first.
A synthesised candle at a price that never traded invents a barrier touch that never
happened, and the label built from it is a fabricated outcome the model then learns
from. **That error is invisible to any test that only checks the series is continuous**,
which is why `tests/engines/test_market_sensor.py` asserts the *absence* separately from
the gap report: no candle carries a timestamp that had no trade.

### The in-progress bar is never published

The bar containing `now` is still open. Publishing its high, low and close would put a
partial bar in front of the feature engine — look-ahead by another name, and invariant
10 forbids it.

### `published_bars` bounds the payload per pair

`market_sensor.published_bars` from config. Bounded **per pair** rather than overall, so
a busy pair cannot push a quiet one out of `state` entirely and leave a consumer looking
at nothing. It is a plumbing bound, not a trading threshold — no gate reads it.

The trade window itself lives in the **client**, not here: `recent_trades()` returns a
rolling window without draining it, because engine 3 has to rebuild the same 15-minute
bar on each of the fifteen ticks that bar spans and an engine is stateless across
cycles. The window is bounded by count; a longer history belongs in `data/derived/`
through the replay path.

## `spread_pct`

`(ask - bid) / mid`, with `mid = (ask + bid) / 2`. A **single full-spread term expressed
as a ratio of price**, which is the shape invariant 5 needs — `friction = maker + taker +
spread + slippage`, every term a decimal ratio. Raw `bid`, `ask` and `spread` are
published beside it so a consumer wanting a different convention can compute one rather
than reverse a division.

**It may be negative.** A crossed book is a real thing a feed produces during a fault
and engine 4 blocks on exactly that; clamping it here would delete the evidence the gate
exists to see.

**A pair with no quote is absent, not present with a zero spread.** A zero spread is the
one shape the cost gate must never be handed — invariant 2 says an assumed spread
invalidates that gate outright.

## It is not a gate

`is_gate = False`, matching the registry table. It never blocks. A client with no stream
— C's fake Kraken client is exactly that — is **reported, not raised**: the bar clock
still runs, because it is arithmetic over `context.now` and owes nothing to the feed,
and `stream_available` says the rest is missing. Engine 4 decides whether missing data
blocks.

A missing config key is the opposite: `config.get` raises, the orchestrator turns it
into `ERROR`, and `ERROR` blocks. That is the correct fail-closed behaviour for a
threshold nobody has set, and it is why **no default for any config value appears in
this engine**.

## The committed fixture

`tests/fixtures/kraken/ohlc.json`, built by `scripts/ohlc_fixture.py`, holds real
recorded Kraken `trade` frames for **BTC/USD, ETH/USD and SOL/USD** across three bars,
plus the OHLCV those trades imply. `candles_match_kraken_ohlc` feeds the trades to
`build_candles` and compares, within one `tick_size` **read from `AssetPairs`** — never
a constant — and 0.1% on volume.

Its honesty is bounded and the fixture says so in its own `provenance` field: **the
trades are real; the `ohlc` half is a reference computation, not Kraken's own published
OHLC.** `scripts/record.py` subscribes to `book`, `ticker` and `trade`, so the archive
contains no OHLC channel to compare against, and no live call can be made. The expected
values come from a deliberately naive pure-Python reduction in `scripts/ohlc_fixture.py`
that shares no code with the `polars` implementation under test — which catches a bug in
the bucketing, the grouping or the `Decimal` handling, and cannot catch a shared
misunderstanding of what a candle is. Confirming these bars against Kraken's published
OHLC is a `--live` task.

**Frame duplicates are dropped when building that fixture; trade duplicates are not.**
Two `record.py` processes ran concurrently from 2026-09-09T13:19:34Z, so part of the
archive holds each frame twice. Two recorders produce byte-identical *frames*, whereas
two genuinely identical trades arrive inside one frame — so de-duplicating at the trade
level would silently delete real volume. The recording itself is never edited;
invariant 11.
