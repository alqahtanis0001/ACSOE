# 73 — Engine 15 `skeptic`

**Owner:** C — Interface and models

**Phase:** 5. `engines/skeptic/` is C's.

## Goal

The last gate before the decision: a learned opinion about this specific trade, which can only
say no. It reads the predictor's call, scores how likely the call is to be wrong, and vetoes
above `skeptic.veto_threshold`.

## Implementation

1. `engines/skeptic/engine.py`, `contracts.py`, `README.md`. `name = "skeptic"`,
   `number = 15`, `is_gate = True`.
2. Loads the artefact for `models.skeptic_run_id` through the store, verifying the hash.
   Missing key, directory, hash, or a fold that produced no skeptic (spec 69) blocks with
   `skeptic_unavailable`. `skeptic.veto_threshold` absent blocks with the same code and a
   reason naming the key.
3. Reads `state["prediction"]`: when `is_buy` is false the engine returns `OK` with
   `{"vetoed": false, "reason": "not a BUY call"}`, because the skeptic grades BUY calls and
   has no opinion about the rest, and the decision engine in Phase 6 is what turns a non-BUY
   into no trade. When true, inputs are the feature row plus the three probabilities plus
   `expected_move_pct`, in the manifest's order; `p_wrong` above the threshold blocks with
   reason code `skeptic_veto` and a reason carrying `p_wrong` and the threshold.
4. Publishes `{"pair", "model_run_id", "p_wrong", "threshold", "vetoed"}`.
5. Reason codes into `REASON_PROSE`, enumerated by the existing test.
6. `tests/engines/test_skeptic.py`, C lane: block and pass differing in one input; the
   not-a-BUY pass; every unavailable shape by reason code.

## Scope Limits

- Do **not** approve. There is no output of this engine that makes a trade more likely.
  Invariant 4.
- Do **not** default the threshold.
- Do **not** train, adapt, or read the store for outcomes. Live learning is out of scope.

## Check When Done

- `anomaly_and_skeptic_have_both_tests` sees both tests.
- Mutation observed red: the veto comparison inverted; the threshold read from a constant.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
