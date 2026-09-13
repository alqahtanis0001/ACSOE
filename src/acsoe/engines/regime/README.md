# Engine 12 — `regime`

**Number:** 12 · **Chain:** opportunity, before engine 13 · **Gate:** no · **Runtime stage:** 3

Classifies the candidate's market environment as one of `trending`, `choppy` or
`high_volatility`, from that pair's own feature row, and publishes it under
`state["regime"]` for engine 14 `adaptive_router` to read in Phase 6.

Rule-based. The HMM in the stack table is an optional upgrade and spec 66 puts it out of
scope.

## The rules, and why one is a percentile and the other is not

Applied in this order:

1. **`high_volatility`** when `vol_regime_rank` is at or above `regime.high_vol_percentile`.
2. otherwise **`trending`** when `efficiency_ratio_96` exceeds `regime.trend_efficiency`.
3. otherwise **`choppy`**.

`vol_regime_rank` is where this bar's short-window realised volatility sits inside the
long window's own distribution, 0 to 1, measured in `modelling/features.py`. So the
configured cutoff is a **position in the pair's own recent history**, not a quantity of
percent. That matters: an absolute volatility threshold would classify a $0.30 pair and a
$60,000 one by the same number, and would mean something different in 2018 than in 2024.

The structural reason it cannot drift back to an absolute number is worth stating.
**Engine 12 is handed one feature row.** It has no distribution of its own and could not
compute a percentile if it wanted to, so the only number it can compare against
`regime.high_vol_percentile` is one the feature layer already measured against the pair's
history.

The trend rule *is* an absolute cutoff, and that is legitimate, because the efficiency
ratio is already scale-free: net move over path length is 1.0 for a straight line and 0.0
for a round trip that went nowhere, on any pair at any price.

Both cutoffs are plumbing the lead chose and both are flagged **provisional** in
`config/default.yaml`: no gate reads the label and no order is sized from it.

## What it reads from `state`

| Key | Owner | Used for |
|---|---|---|
| `state["scout"]["pair"]` | engine 7 (B) | the candidate; absent means `PASS` |
| `state["feature"]["pairs"][pair]` | engine 5 (C) | the row the label is decided from |
| `state["feature"]["bar_ts"]` | engine 5 (C) | the bar being described |

Every key name is a named constant in `contracts.py` with its owning engine beside it.

## What it writes into `state["regime"]`

| Key | Meaning |
|---|---|
| `pair`, `bar_ts` | the candidate and the bar |
| `label` | one of the three, or `null` with a `reason` |
| `reason` | `no_feature_row` or `regime_inputs_incomplete` when `label` is null |
| `inputs` | the feature values the label was decided from |
| `thresholds` | the two cutoffs applied, so a label reads without the config beside it |
| `di_regime_shift` | **always `null`** — see below |

### `null` is not a fourth label and `choppy` is not a default

A candidate with no feature row, or whose longest lookback is unfilled, gets
`label: null` and a reason. Calling an unclassifiable market `choppy` would be a
judgement nobody made, and Phase 6's router would weight a model by it.

The same reasoning is why NaN is read as absent rather than compared: a NaN is False
against every threshold, so an unfilled input would fall through to `choppy` — a label
nobody measured, arriving through the branch that looks like a default.

### `di_regime_shift` is a declared placeholder

A Locked Decision says DI threshold crossings also feed the regime engine. They cannot
yet, and the reason is structural rather than unfinished work:

* engine 12 runs **before** engine 8 in the registry order, so this tick's DI does not
  exist when this engine runs;
* `state` is fresh every tick, so last bar's DI is not there either.

Nothing persists it. The field is published as `null` rather than omitted because an
absent key reads as an oversight and a null with this paragraph reads as a decision.
**Where a previous bar's DI would live is a schema question** — B's edit and the lead's
approval — and it is an open question for the operator. Phase 6's router is the first
reader that would need it. This engine does not reach into the store to answer it: an
engine inventing its own persistence is how a cross-chain key ends up with two meanings.

## Gate behaviour

**None. Engine 12 is not a gate and never blocks.** No regime is a reason to refuse a
trade; that is the router's business in Phase 6.

It raises on an absent `regime.high_vol_percentile` or `regime.trend_efficiency`, which
the orchestrator turns into `ERROR`. There is no default: a cutoff nobody set is not a
number to invent, even for a label nothing trades on.
