# 95 — Engine 8's `is_buy` says which of two things happened, and engine 15 reads it

**Owner:** C — Interface and models

**Phase:** 6, by operator ruling 2026-09-15 (ruling 6 of 2026-09-16). `engines/prediction/` and
`engines/skeptic/` are C's.

## Goal

`PredictionState.is_buy` is `bool = False` and `to_state()` publishes it unconditionally, so a
refusing engine 8 — `di_refused`, an absent artefact, an incomplete vector — publishes
`is_buy: false` exactly as a predictor that ran and called no BUY does. At the end of this spec a
refusal publishes **no** `is_buy` key, following `expected_move_pct`, and engine 15's read lands in
the same change so its spec 73 hardening does not start reporting a refusal as a non-BUY.

## Implementation

1. `engines/prediction/contracts.py`: `is_buy: bool | None = None`; `to_state()` omits the key
   when `None`, in the same shape and with the same docstring reasoning as `expected_move_pct`.
   Every refusal path leaves it `None`; every path that scored the model sets `True` or `False`.
2. `engines/prediction/engine.py`: confirm by reading every return path which of the two it is;
   no path may set `False` as a placeholder.
3. `engines/skeptic/engine.py`: an absent `is_buy` is already a block (`skeptic_unavailable`);
   check the reason sentence says "engine 8 made no call" rather than "not a BUY call", because
   now the payload can say so. `is_buy is False` stays the one non-BUY pass.
4. READMEs of both engines, and the cross-chain key row for `state["prediction"]` gains `is_buy`
   (spec 80, lead) — engine 14 is its first reader outside a gate.
5. Tests: `tests/engines/test_prediction.py` — every refusal shape publishes no `is_buy` key, a
   scored non-BUY publishes `False`; `tests/engines/test_skeptic.py` — a refusing engine 8's real
   payload reaches engine 15 as a block naming the absence, not as "not a BUY call".

## Scope Limits

- Do **not** change the BUY definition (`expected_move_pct > 0`) or any threshold.
- Do **not** make engine 15 pass on an absent `is_buy`. It blocks.
- Do **not** land one engine's half without the other.

## Check When Done

- Mutations observed red, killing test named: `is_buy` defaulting back to `False`; `to_state`
  emitting `None` instead of omitting; engine 15 treating absent as non-BUY.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
