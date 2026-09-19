# Engine 5 — `feature`

**Number:** 5 · **Chain:** opportunity, first · **Gate:** no · **Runtime stage:** 2

Computes the feature vector for every pair engine 3 published candles for, on the tick
where a decision bar closed, and publishes it under `state["feature"]`. On every other
tick it returns `PASS` and the opportunity chain stops here.

## It computes nothing

Every number comes from `modelling.features.compute`, which `research/training.py` also
calls. That is the whole design: architecture invariant 5 keeps the live loop and
`research/` from importing each other, so the only way a backtest can describe the system
that actually trades is for both sides to run one function over differently-shaped
inputs. `modelling/` is the package both may import, and
`features_reproduce_in_replay` is the criterion that asks whether they agreed.

**One call a tick, since 2026-09-19 (lead decision D16).** The engine hands every pair's
candles to `modelling.features.compute_many` at once, rather than calling `compute` once per
pair. Each window is taken within its own pair, and a pair's row is bit for bit what `compute`
returns for that pair alone. That is proven against the per-pair implementation kept as the
oracle in `tests/modelling/features_oracle.py`. The per-pair loop spent ~8 ms of polars overhead
on every pair, about 1.6 s a tick at 190 pairs.

This engine's job is the shaping: group by pair, turn decimal strings into floats, drop
anything later than the closed bar, and turn NaN into `null` on the way into `state`.

## It is the cadence

The loop ticks every minute; a candidate is only born when a 15-minute bar closes.
Engine 3 `market_sensor` owns that clock and publishes `bar_closed`. Engine 5 returns
`PASS` when it is false, the chain stops, and roughly fourteen ticks in fifteen end here.
**No other engine may infer the bar boundary for itself** and the orchestrator does not
know about bars at all — cadence is a property of the candle stream, not of `core/`.

## What it reads from `state`

`state["market_sensor"]`, and nothing else. Every key name is a named constant in
`contracts.py` with the owning engine beside it, so a rename upstream is a change in one
place rather than a silent empty payload.

| Field | Used for |
|---|---|
| `bar_closed` | whether to run at all |
| `closed_bar_ts` | which bar the row describes, and the cut-off for what may be read |
| `interval_s` | the grid every lookback window is a multiple of |
| `candles` | the OHLCVT input, money as exact decimal strings |

`interval_s` comes from `state` rather than from `timeframes.decision_bar_s` on purpose:
engine 3 built the candles on that grid, and two readers of one config key can still
disagree if one is stale, while a value travelling with the data cannot.

## What it writes into `state["feature"]`

| Key | Meaning |
|---|---|
| `bar_ts` | the decision bar that closed on this tick |
| `interval_s` | echoed, so a reader needs no config to interpret a lookback |
| `feature_version` | `modelling.features.FEATURE_VERSION`; an artefact records the version it was trained at and engine 8 refuses one that disagrees |
| `feature_names` | the ordered names, so a consumer never imports the modelling package to read a row |
| `pairs[pair]` | the feature row: floats and `null`, **never NaN** |
| `row_ts[pair]` | the bar that row actually describes |
| `pairs_with_short_history` | pairs whose candles do not cover the longest lookback |
| `gaps_in_range[pair]` | bar slots inside that pair's own range holding no candle |

`state["feature"]["pairs"][pair]` is a **cross-chain key** fixed in
`context/engine-contracts.md`. Engine 7 `scout` (B) ranks on it and engines 6, 8, 12 and
13 read it. Its shape may not be changed without the lead.

### `null`, never NaN, and never zero

`data` must be JSON-serialisable (contract rule 8) and a float NaN is not — it survives
`json.dumps` only as a non-standard token some readers accept and some reject. `null` is
the honest spelling of *not computable from the bars that were there*. It is never a
zero, because a zero is a value a model will happily learn from and is indistinguishable
downstream from a genuinely quiet market.

### `row_ts`, and why a pair can be behind

A pair that had **no trades** in the decision bar has no candle there, and nothing may
invent one. Rather than dropping the pair or dating a row to a bar it has no data for,
the row is that pair's most recent closed bar at or before `bar_ts`, and `row_ts` says
which. A consumer that cares about staleness compares the two.

### `gaps_in_range` is counted here, not read through

Engine 3's `missing_bars` pools every pair's timestamps before looking for holes, so a
slot is absent from that union only when *no pair anywhere* traded in it. On a
multi-pair tick it therefore reports nearly nothing and reports it identically for every
pair. This engine counts each pair's holes from that pair's own candles, bounded by its
own first and last candle — a bar before the data starts or after it ends is not
missing, it is outside the range.

## Gate behaviour

**None. Engine 5 is not a gate and never blocks.** A pair with too little history is
reported with null features and its name in `pairs_with_short_history`; a pair that did
not trade in the bar gets an older `row_ts`. Refusing is engine 7's business and engine
13's. Dropping a pair here would make it invisible to the gate that is supposed to
consider it — a silent narrowing of the universe nothing downstream could detect.

It does raise, and the raise is deliberate, on two shapes engine 3 cannot actually
produce: `bar_closed` true with no `closed_bar_ts`, and a missing `interval_s`. The
orchestrator turns a raise into `ERROR`, which blocks. That is the correct fail-closed
answer when the engine owning the decision-bar clock has published something
unreadable, because every alternative involves guessing at what the market did.

The same applies to `features.min_lookback_fill` and `features.max_lookback_bars`: no
defaults, `Config.get` raises on an absent key, and `MAX_LOOKBACK_BARS` exceeding the
configured ceiling raises too. The longest window has to fit inside what engine 3
publishes, or the live path can never fill it while the offline builder fills it every
time, and the two paths differ on every bar with the offline number looking right.

## Money

Engine 3 publishes candle money as exact decimal strings. **This engine is the one place
on the live path where that becomes a float**, because features are model inputs rather
than money. `float("20.24")` and `float(Decimal("20.24"))` are the same double, which is
what lets the live path and the offline builder be compared for exact equality rather
than for closeness.
