# 69 — The skeptic, trained only on the predictor's out-of-sample BUY calls

**Owner:** C — Interface and models

**Phase:** 5. Training in `research/training.py`; the artefact under its own `run_id` per fold.

## Goal

A meta-labelling model that grades the predictor's BUY calls: given the feature vector and the
predictor's probabilities, how likely is this call to be wrong. It sees only rows where the
predictor said BUY, and only calls the predictor made **out of sample**.

## Implementation

1. **The training rows for fold `k`** are the BUY rows of spec 67's OOS file from folds
   strictly before `k`, subject to the same purge and embargo against fold `k`'s test window
   that the predictor's rows are subject to. In-sample BUY calls are never used: a skeptic
   trained on the predictor's own training-set calls learns the predictor's overfit, not its
   mistakes. The first folds have no history and produce no skeptic; the digest says so per
   fold and engine 15 blocks with `skeptic_unavailable` for a model version without one.
2. **The label** is `wrong = label != "target"`. Inputs are the feature vector plus the three
   predictor probabilities plus `expected_move_pct`, in a manifest-recorded order. LightGBM
   binary, `seeds.train`, weights carried over from spec 67.
3. **Identity proof.** The skeptic manifest records the hash of its training rows'
   `(pair, decision_ts, fold_of_origin)`; `skeptic_trains_only_on_predictor_buy_rows` checks
   every one is a BUY row in the OOS file with `fold_of_origin < k`.
4. **Reported per fold**: rows, effective sample size, the veto rate at
   `skeptic.veto_threshold` on fold `k`'s own OOS BUY calls, and the target rate among the
   calls that survive the veto beside the target rate among all BUY calls. The second pair of
   numbers is the only thing that says whether the skeptic helps.
5. `tests/research/test_skeptic_training.py`, C lane.

## Scope Limits

- Do **not** train on non-BUY rows, and do **not** train on in-sample calls.
- Do **not** let the skeptic approve. Its output is a probability of being wrong; engine 15
  turns it into a veto or nothing. Invariant 4.
- Do **not** default `skeptic.veto_threshold`. Absent means the veto-rate numbers are not
  computed and the criterion reports PENDING naming the key; training itself still runs.

## Check When Done

- `skeptic_trains_only_on_predictor_buy_rows` PASS, and observed FAIL with an in-sample BUY
  row injected and with a `stop`-labelled non-BUY row injected.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
