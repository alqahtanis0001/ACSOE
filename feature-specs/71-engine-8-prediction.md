# 71 — Engine 8 `prediction`, with the DI inside it

**Owner:** C — Interface and models

**Phase:** 5. `engines/prediction/` is C's.

## Goal

The live half of spec 67: for the candidate pair, load the active predictor artefact, refuse
to predict when the DI says the market looks like nothing in the training set, and otherwise
publish three calibrated probabilities, `expected_move_pct` as an exact decimal string for
engine 10, the DI, and per-feature attributions.

## Implementation

1. `engines/prediction/engine.py`, `contracts.py`, `README.md`. `name = "prediction"`,
   `number = 8`, `is_gate = False`, and it stays that way, per spec 59 decision 3.
2. **Loading.** The active run id is `models.prediction_run_id`; the directory comes from
   `context.clients.store.model_run_dir(run_id)`; the manifest is verified by
   `modelling.artefacts.load`, which refuses a feature list that is not `FEATURE_NAMES` plus
   the macro names in order. The loaded artefact is held on the engine as a resource, the way
   the stream is held on a client, keyed by the run id it was loaded for; a changed run id
   reloads. **A missing key, a missing directory, a failed hash or a feature-order mismatch
   blocks** with reason code `prediction_unavailable` and a reason naming which. That is
   invariant 3 on a fresh clone with no `models/`.
3. **Input.** The candidate from `state["scout"]["pair"]`, its feature row from
   `state["feature"]["pairs"][pair]`, the macro columns from `state["macro_context"]`. A null
   in any feature the manifest names blocks with `prediction_inputs_incomplete`, naming the
   features. NaN handling is LightGBM's at training time and is not repeated live.
4. **The DI first.** Scale with the manifest's scaler, score with `modelling.di.score`
   against the artefact. Above threshold: `BLOCK`, reason code `di_refused`, reason carrying
   the DI and the threshold to four decimals, `data` carrying `di`, `di_threshold` and no
   `expected_move_pct`. Contract rule 6, spec 59 decision 3.
5. **Otherwise** predict, calibrate, and compute `expected_move_pct` with the function
   `modelling/` exports, then publish it as an exact decimal string under the fixed cross-chain
   key. Probabilities are floats; the expected move is money-shaped and crosses `state` as a
   string.
6. **Attribution.** `shap.TreeExplainer` over the loaded model gives per-feature contributions
   for the target class; published under `data["shap"]` as `{feature: float}`. Writing them to
   Parquet and filling `rejections.shap_ref` is Phase 7 with the SHAP view; here they only
   cross `state`.
7. Publishes `{"pair", "bar_ts", "model_run_id", "feature_version", "p_target", "p_stop",
   "p_timeout", "expected_move_pct", "is_buy", "di", "di_threshold", "shap"}`.
8. `tests/engines/test_prediction.py`, C lane. The artefact in every test is trained in a
   fixture from the committed sample into `tmp_path`, never read from `models/`. Fixtures for
   `state` are engines 5, 6 and 7's real output.

## Scope Limits

- Do **not** train here. Load only, in the constructor path or on first use, never at import.
- Do **not** make this engine a registry gate. `is_gate` stays `False`.
- Do **not** publish `expected_move_pct` on a DI refusal or a load failure. An absent key is
  how engine 10 fails closed.
- Do **not** cast a `Decimal` to `float` or a `float` to `Decimal` on the way to
  `expected_move_pct`; format from the arithmetic once, through `repr`, as the labeller does.

## Check When Done

- A block test for each of `prediction_unavailable`, `prediction_inputs_incomplete` and
  `di_refused`, each asserting the reason code and not only the status; a pass test with a
  candidate the DI accepts.
- The Phase 3 criterion `cost_gate_uses_live_fee_tier` still PASSes with engine 8 registered
  ahead of engine 10 (spec 77).
- Mutations observed red: the DI scored after prediction instead of before; the feature order
  taken from the state row instead of the manifest; the veto comparison flipped.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
