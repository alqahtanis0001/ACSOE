# 72 — Engine 13 `anomaly`

**Owner:** C — Interface and models

**Phase:** 5. `engines/anomaly/` is C's.

## Goal

A data-quality gate: is the candidate's market broken. Unsupervised, over market-data
features only, protected by invariant 4 like `data_guard`, and able only to veto.

## Implementation

1. `engines/anomaly/engine.py`, `contracts.py`, `README.md`. `name = "anomaly"`,
   `number = 13`, `is_gate = True`.
2. Loads the artefact for `models.anomaly_run_id` through the store, verifying the hash, and
   holds it as a resource keyed by run id. Missing key, directory, hash or threshold blocks
   with `anomaly_unavailable`.
3. Reads the candidate's `MARKET_QUALITY_FEATURES` from `state["feature"]`, scales with the
   manifest's scaler, scores. Score above the manifest threshold blocks with reason code
   `market_anomalous` and a reason carrying the score and threshold. A null in any input
   blocks with `anomaly_inputs_incomplete`. Otherwise `OK` with `{"pair", "score",
   "threshold", "anomalous": false}`.
4. Reason codes into `console/format.py`'s `REASON_PROSE` with operator wording, enumerated
   out of this module by the existing test, so a code without prose goes red.
5. `tests/engines/test_anomaly.py`, C lane: a block test and a pass test that differ in one
   input, plus the three unavailable-shaped blocks each asserting the reason code.

## Scope Limits

- Do **not** read the prediction, the label, or anything about whether the trade is good. This
  gate judges the market, not the candidate.
- Do **not** read a spread. The archive has none, so the artefact was never fitted on one.
- Do **not** learn or adapt live. The threshold is the artefact's.

## Check When Done

- `anomaly_and_skeptic_have_both_tests` sees both tests.
- `is_gate_matches_registry` reports no mismatch once spec 77 registers it.
- Mutation observed red: the comparison inverted (block below threshold).
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
