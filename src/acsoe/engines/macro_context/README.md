# Engine 6 — `macro_context`

**Number:** 6 · **Chain:** opportunity, after engine 5 · **Gate:** no · **Runtime stage:** 2

The market-wide backdrop every candidate is judged against: BTC's and ETH's feature rows,
selected out of `state["feature"]`, renamed with a `macro_` prefix, and published for
engines 8, 12 and 15 to read alongside the candidate's own row.

A candidate's own features say what that pair is doing. They say nothing about whether
the whole market is doing it, and a 2% move while Bitcoin is up 3% is a different event
from the same move while Bitcoin is flat.

## It computes nothing

Selection and renaming only. The rows are engine 5's, which are
`modelling.features.compute`'s, which is the function `research/training.py` calls — so a
macro column in the training set and the same column live are the same arithmetic over
the same pair, differing only in whether the candles came from the stream or the archive.

## Two spellings of one pair, both from config

Kraken calls the same market `BTC/USD` on the live stream and `XBTUSD` in the downloadable
archive. Neither spelling is derivable from the other, so both are named under `macro` in
`config/default.yaml`:

```yaml
macro:
  btc: {live: "BTC/USD", archive: "XBTUSD"}
  eth: {live: "ETH/USD", archive: "ETHUSD"}
```

This engine reads the `live` one; spec 67's offline dataset builder reads the `archive`
one and joins the same columns by `decision_ts`. A hardcoded either would work in exactly
one of the two modes the same code has to run in. **No pair name appears in this
package.**

## What it reads from `state`

`state["feature"]`, and nothing else. Every key name is a named constant in
`contracts.py` with the owning engine beside it.

| Field | Used for |
|---|---|
| `bar_ts` | the bar the payload describes, and whether a bar closed at all |
| `pairs[live_pair]` | the macro asset's feature row |

## What it writes into `state["macro_context"]`

| Key | Meaning |
|---|---|
| `bar_ts` | the decision bar, echoed from engine 5 |
| `available` | false when any configured asset had no row this bar |
| `missing` | the assets with no row, by **asset** name |
| `assets` | every configured asset, sorted |
| `pairs` | `{asset: live pair}`, so a missing asset traces to the config line |
| `features` | `macro_<asset>_<feature>` to value, every configured column present |

### The column names live in `contracts.py`

`macro_feature_names(assets)` and `macro_column(asset, feature)` are the only places a
macro column name is built. Spec 67's dataset builder uses the same functions. If the two
spelled a name differently, the predictor would train on `macro_btc_log_return_4` and be
handed something else live, and the artefact's feature-order check would be the only
thing that noticed — at load time, as a refusal, with the cause nowhere in the message.

The asset order is **sorted**, not the config file's order. The configured mapping is a
YAML dict whose iteration order is the file's, so reordering two lines would otherwise
permute the trained feature order, and a model handed its columns permuted returns
confident nonsense with nothing raising.

### A missing asset is `null`, never absent and never zero

Absent would make a downstream feature-order check fail with a shape complaint rather
than a missing-data one. Zero is a number the model learns from and cannot tell from a
genuinely flat market.

## Gate behaviour

**None. Engine 6 is not a gate, never blocks, and never substitutes.**

A missing macro pair is `available: false` with the asset named. What to do about a
missing context is a judgement for the engines that read it: engine 8 will find its
feature vector incomplete and block with `prediction_inputs_incomplete`, naming the
features, which is a better message than anything this engine could produce.

**It never substitutes a stale or previous-bar macro row.** That would be worse than
either blocking or reporting: stale data presented as current, on the one input whose job
is to say whether the whole market moved.

It does raise on an empty or malformed `macro` section, which the orchestrator turns into
`ERROR`. A pair name nobody has set is not something to guess at.
