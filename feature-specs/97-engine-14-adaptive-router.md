# 97 — Engine 14 `adaptive_router`, and the leaderboard fixture it is proven on

**Owner:** C — Interface and models

**Phase:** 6. `engines/adaptive_router/` and `tests/fixtures/` are C's.

## Goal

Engine 14 reads the leaderboard engine 20 writes, the candidate's regime and its DI margin, and
publishes a weight per model version and the basis for each weight. It is honest about being inert:
today there is one real model, and in the fixed registry order nothing it publishes may change
whether the tick trades.

## Implementation

1. `engines/adaptive_router/engine.py`, `contracts.py`, `README.md`. `name = "adaptive_router"`,
   `number = 14`, `is_gate = False`. Opportunity chain, after 11, before 15.
2. **Reads**: `context.clients.store.leaderboard_entries(...)`; `state["regime"]["label"]`;
   `state["prediction"]` `model_run_id`, `di`, `di_threshold`, and `is_buy` (spec 95).
3. **The weighting rule is a methodology choice.** C proposes one in the build log before writing
   it — for example weight proportional to Brier skill against the base rate, clipped at zero —
   and the lead approves it before it is built. Whatever the rule, a model version whose Brier does
   not beat its base rate gets weight zero, and weights sum to one or are all zero with a reason.
   **The `leaderboard` table has no base-rate Brier column.** If the approved rule needs a
   quantity the schema does not hold, that is a schema question to the lead — not a number encoded
   into `notes` and parsed back out.
4. **Publishes** `{"weights": {model_version: float}, "active_model_run_id", "basis",
   "regime", "di_margin", "reason_code"}`. Statistics are floats; nothing here is money.
5. **Never blocks and never approves.** `OK` on every path that ran, including an empty leaderboard
   (all weights absent, `reason_code: leaderboard_empty`). It sits after engine 10, so by
   invariant 4 no weight may raise willingness to trade, and lowering it would be a veto only a
   gate may issue. Engine 15 does not read this payload. The README states both, and that the
   router is inert today because the walk-forward trained one predictor per fold.
6. **The fixture.** `tests/fixtures/leaderboard_sample.json`: rows for **at least two distinct
   `model_id`s**, with Briers and base rates chosen so the rule gives them visibly different
   weights, and a third version that does not beat its base rate. Its provenance line says it is
   fabricated to exercise weighting and describes no trained model. Listed in the fixtures README.
7. Tests in `tests/engines/test_adaptive_router.py`: weights computed from the fixture loaded into
   a real `StoreClient`, recomputed in the test from the rows rather than read back; a
   worse-than-base-rate model at zero; one model at weight one; an empty leaderboard; the chain
   through engines 14 and 15 with a weight changed and engine 15's verdict unchanged.
   **Every test that asserts the weights move names, in its docstring and assertion message, that
   it is asserting a property of the fixture, not of any trained model.**

## Scope Limits

- Do **not** select, load or swap the model engine 8 uses. `models.predictor_run_id` governs.
- Do **not** block, and do not publish anything engine 15, 16 or 18 reads to decide.
- Do **not** read `data/db/` in a test or criterion. The committed fixture only.
- Do **not** persist a previous bar's DI; that is the tracker's open schema question.

## Check When Done

- Mutations observed red, killing test named: weights normalised over a model with negative skill;
  the regime ignored if the approved rule uses it; engine 15 reading a weight.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
