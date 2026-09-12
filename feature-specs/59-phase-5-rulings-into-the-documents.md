# 59 — Phase 5 rulings into the documents

**Owner:** Lead

**Phase:** 5. `context/*`, `config/default.yaml` and `feature-specs/` are the lead's.

## Goal

Every decision Phase 5 rests on is written into the file that has authority over it
**before** a teammate builds against it, so no agent has to infer trading or methodology
behaviour from a spec. Nine decisions, each flagged to the operator as overturnable.

## The nine decisions

1. **Engine 20 `tournament` is Phase 5 work.** Its leaderboard is what engine 14
   `adaptive_router` reads in Phase 6, so a model phase that closes without it leaves Phase 6
   nothing to weight by. The Phase 5 row of `ai-workflow-rules.md` gains engine 20; the Phase 7
   row keeps attribution, the deflated metric and the promotion gate, all of which *read* the
   leaderboard engine 20 writes. The interim note under the phase table is replaced by this.
2. **One shared leaf package, `src/acsoe/modelling/`, owned by C.** Feature arithmetic, the
   Dissimilarity Index arithmetic, the artefact manifest and the sample-weight arithmetic are
   needed by both the live engines and `research/training.py`, and invariant 5 forbids either
   side importing the other. `modelling/` imports nothing from `acsoe` except `core.contracts`
   types, reads no `state`, touches no client and holds no engine. Added to the repository
   layout in `architecture-context.md` and to the roster in `ownership.md`, with a seam row.
3. **Engine 8 `prediction` blocks on a DI refusal**, under contract rule 6, with reason code
   `di_refused`, and publishes no `expected_move_pct` on that tick. It stays a non-gate in the
   registry table: `is_gate` is a declaration `verify.py` checks against the table, and rule 6
   already lets any engine halt the tick. The alternative, skeptic applying the veto, would run
   the cost and risk gates on a prediction the DI has already distrusted and could lose the
   refusal from the counterfactual record whenever cost blocked first.
4. **The metric is decided before anything trains.** Primary: the **Brier score of the
   calibrated P(target)** on each out-of-sample fold, reported beside the **base-rate Brier**
   `p(1-p)` for that fold. Secondary: multiclass log loss. Decision metric: the **target rate
   among BUY calls** (rows where `expected_move_pct > 0`) per fold, reported beside the
   break-even rates in invariant 5. **Accuracy is never computed or reported**: at a 23.89%
   target rate and 51.27% stop rate, a model that always says `stop` scores 51%.
5. **Sample weights are average-uniqueness weights.** At a 48-bar horizon consecutive rows
   overlap almost completely and twenty million rows is not twenty million observations. Each
   row's weight is the mean over its label window of `1 / concurrency`, computed per pair; the
   effective sample size `sum(weights)` is reported beside every row count.
6. **The DI reference set** is the predictor's training rows for the fold, MinMax-scaled with
   the predictor's scaler, restricted per pair to the last `prediction.di_window_days` days of
   the training window. The DI of a vector is its mean distance to its `prediction.di_neighbours`
   nearest reference rows; the threshold is the `prediction.di_percentile` quantile of the same
   statistic computed leave-one-out over the reference rows. "Rolling" means the reference set
   moves with each weekly retrain. This is the lead's reading of the locked decision and is
   flagged as such.
7. **Engine 7's ranking is a config-named feature, not a formula**, read from
   `scout.rank_feature` with a direction under `scout.rank_descending`. While the key is absent
   the ordering stays alphabetical and the engine publishes `rank_feature: null`. The feature
   is chosen by the operator from the ranking study in spec 75, not guessed.
8. **`lightgbm`, `scikit-learn` and `shap` move into the base install.** Engines 8, 13 and 15
   import them at load time on the live path; the `research` extra keeps `hmmlearn` and
   `statsmodels`. The `pyproject.toml` comment said "before Phase 5"; this is Phase 5.
9. **Three values are the operator's and are absent, not defaulted, until supplied**:
   `prediction.di_percentile`, `anomaly.threshold_percentile`, `skeptic.veto_threshold`. Each
   engine fails closed while its key is absent and the criterion that judges it reports PENDING
   naming the key, exactly as `data_guard.max_data_age_s` did in Phase 2.

## Implementation

1. `context/ai-workflow-rules.md`: engine 20 into the Phase 5 row; Phase 7 row reworded to
   consume the leaderboard; the interim note removed; `accuracy` added to the retired-vocabulary
   table qualified by `metric` or `score`, so a document that reports it goes red.
2. `context/architecture-context.md`: `modelling/` in the layout with its import rule; a
   `models/<run_id>/` paragraph under Storage naming the manifest, the feature order, the scaler
   and the never-overwrite rule; invariant 5 extended by one sentence naming `modelling/` as
   importable from both sides.
3. `context/ownership.md`: `modelling/` and the Phase 5 criteria under C; seam rows for the
   feature vector (C to B, engine 7 reads it), the artefact directory (B's store surface, C
   reads), the leaderboard (C engine 20 writes, Phase 6 engine 14 reads) and the ranking feature
   (config, lead writes, B reads).
4. `context/engine-contracts.md`: cross-chain key rows for `state["feature"]["pairs"][pair]`,
   `state["prediction"]["di"]` and `state["regime"]["label"]`. Nothing else in that file changes.
5. `context/progress-tracker.md`: decisions 3 to 7 under Locked Decisions as lead rulings of
   2026-09-12, each marked overturnable; the three operator-required keys under Open Questions.
6. `config/default.yaml`: sections `models`, `features`, `macro`, `prediction`, `anomaly`,
   `skeptic` and the two `scout` keys, authored by the lead **after A's spec 61 lands the
   fields** (the landing rule in `code-standards.md`). The three operator keys are omitted,
   with a comment saying which criterion reports PENDING on them.
7. `context/glossary.md`: entries for *uniqueness weight*, *base-rate Brier* and *BUY call*.

## Scope Limits

- Do **not** write code. This spec is documents and the YAML only.
- Do **not** change `trading-invariants.md`. Nothing in Phase 5 moves money.
- Do **not** paste a YAML key before its model field exists. Every section is
  `extra="forbid"` and a half-landed key breaks every test that loads the committed config.
- Do **not** decide the ranking feature here. Spec 75 produces the evidence; the operator rules.

## Check When Done

- `docs_vocabulary` PASS with the new `accuracy` row, and observed FAIL against a line reading
  "accuracy score" reinstated in a context file.
- `python scripts/verify.py --phase 4` still 10/10.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
