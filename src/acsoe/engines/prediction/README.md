# Engine 8 — `prediction`

**Number:** 8 · **Chain:** opportunity, after engine 7 and before engine 10 · **Gate:** no ·
**Runtime stage:** 3

For the one candidate engine 7 chose, loads the active predictor artefact, asks the
Dissimilarity Index whether this market looks like anything the model was trained on, and
only then predicts. Publishes three calibrated probabilities, the expected move as an exact
decimal string for engine 10 `cost`, the DI and its threshold, and per-feature attributions.

This is the live half of `research/training.py`. Every number it produces comes out of an
artefact that trainer wrote; nothing is fitted here and nothing is defaulted here.

## The order of the two model steps is the whole design

**The DI is scored before the prediction, never after it.** Predict-then-veto was
considered and rejected in the spec 59 rulings, and the reason is not efficiency. A
prediction made on a market state unlike anything in the training set is not a weak
prediction — it is a confident number produced by extrapolation, and every gate downstream
would then be reasoning about it. Scoring first means the refusal is recorded as *the model
declined to answer* rather than as *the model answered and we disagreed*, and those are
different research findings.

## It is not a gate and it halts the tick anyway

`is_gate` is `False` and stays `False` (spec 59 decision 3). The registry's Gate column is a
declaration `scripts/verify.py` checks against `engine-contracts.md`; contract rule 6
already lets any engine return `BLOCK`. Making this engine a gate would put a model output
in the position of a policy gate, which invariant 4 forbids.

A refusal publishes **no `expected_move_pct` at all** — the key is absent from the payload
rather than null. Engine 10 treats an absent key and a null identically and blocks either
way, so the chain fails closed without engine 8 knowing anything about engine 10. The
absence rather than the null is so that a log line reads as *no prediction happened* rather
than as *a prediction produced no move*.

## What it reads from `state`

| Key | Publisher | Used for |
|---|---|---|
| `state["scout"]["pair"]` | 7 `scout` (B) | the one candidate. Absent → `PASS`, nothing to refuse |
| `state["feature"]["pairs"][pair]` | 5 `feature` (C) | the candidate's feature row |
| `state["feature"]["bar_ts"]` | 5 `feature` (C) | the decision bar, echoed into the payload |
| `state["feature"]["feature_version"]` | 5 `feature` (C) | checked against the manifest's |
| `state["macro_context"]["features"]` | 6 `macro_context` (C) | the `macro_*` columns |

Every one of those names is declared in `contracts.py` and nowhere else. Contract rule 3:
this engine never imports another engine to find out what its keys are called.

## What it publishes

`state["prediction"]` carries `pair`, `bar_ts`, `model_run_id`, `feature_version`,
`p_target`, `p_stop`, `p_timeout`, `di`, `di_threshold`, `shap` and `reason_code`, plus
**`expected_move_pct` and `is_buy` when and only when it predicted.**

Those two are omitted rather than nulled on a refusal, and `is_buy` joined
`expected_move_pct` in spec 95. It was `bool = False` published on every path, so an engine
8 that refused — `di_refused`, an absent artefact, an incomplete vector — published
`is_buy: false` in exactly the payload a predictor that ran and called no BUY publishes. The
two are different facts with different readers: engine 15 `skeptic` blocks on the first and
passes on the second, and engine 14 `adaptive_router` is the first reader outside a gate.
Nothing failed open in between, because engine 8's own `BLOCK` already stopped the tick; what
was wrong was that the payload could not say which of the two had happened.

Engine 8 cannot publish a placeholder here even by mistake: the refusal helper takes no
`is_buy` argument, so the only code path that can set one is the path that scored a model.

`expected_move_pct` crosses as an **exact decimal string**, formatted once from the
arithmetic through `repr`, the same way `research/labelling.py` crosses the same boundary.
Engine 10 does `Decimal` arithmetic with it. A float crossing there would be rounded twice,
once on each side, and the two roundings would not agree.

The probabilities are floats, because they are model outputs rather than money.

## The three refusals

| Reason code | When |
|---|---|
| `prediction_unavailable` | no `models.prediction_run_id`, no directory, a failed hash, a feature list in the wrong order, a feature version that is not the manifest's, no `di.npz`, no readable calibrators, or no recorded `mean_timeout_return` |
| `prediction_inputs_incomplete` | a feature the manifest names arrived null, NaN or infinite. The message names up to eight of them |
| `di_refused` | the DI is strictly above the artefact's threshold |

One code covers six load failures because they are one fact to an operator — *there is no
usable model* — and the `reason` sentence names which. `prediction_inputs_incomplete` is
separate because it is a different fault with a different owner: the model is fine and the
inputs are not.

`di_refused` is the one refusal here that says nothing is broken. It is the model declining
to answer a question it was never trained on.

**On a fresh clone all of this blocks, and that is invariant 3 working.** There is no
`models/` directory at all, `models.prediction_run_id` is absent from `config/default.yaml`
by ruling, and the system refusing to trade is the correct behaviour rather than an error to
be worked around.

## Why a null input blocks rather than being passed through

LightGBM handles NaN natively and did so at fit time, so passing one through would run. The
reason not to: at fit time a NaN sat in a column with the rest of that column beside it, and
the model learned a direction for it. One live vector with a hole in it is a different
thing, and nothing at this point can tell an unfilled lookback from a feed that stopped.

## Attribution

`shap.TreeExplainer` over the loaded booster, per-feature contributions to the `target`
class, published under `data["shap"]` as `{feature: float}`.

**A failure to explain is not a failure to predict.** The attribution is a research output
and the prediction is the decision, so an exception in the explainer publishes an empty
mapping rather than turning a good prediction into a block. The emptiness is visible in
`state` rather than filled with a plausible set of zeros. `shap` is imported inside the
method: the engine must be importable, and must be able to block, on a machine where the
prediction path is never reached.

Writing attributions to Parquet and filling `rejections.shap_ref` is Phase 7 with the SHAP
view. Here they only cross `state`.

## The loaded artefact is held as a resource

Loading is file I/O plus a sha256 of every file in the directory, and repeating it on every
15-minute bar would be the same work for the same answer. The artefact is held on the engine
keyed by the run id it was loaded for, so pointing `models.prediction_run_id` at a different
run reloads — serving the old model under the new id is the failure this cache would
otherwise introduce. The `TreeExplainer` is dropped with it, for the same reason.

Loading happens on first use, never at import.

## What it never does

It never trains. It never reads `models/` by path — the directory comes from
`context.clients.store.model_run_dir(run_id)`. It never casts a `Decimal` to a `float` or
back on the way to the expected move. And it never builds its feature vector by iterating
the published row: the order is the **manifest's**, because a mapping has no order that
means anything and a vector assembled in the wrong order is every value in range and every
value in the wrong column, with nothing anywhere to notice.
