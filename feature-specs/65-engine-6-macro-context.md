# 65 — Engine 6 `macro_context`

**Owner:** C — Interface and models

**Phase:** 5. `engines/macro_context/` is C's.

## Goal

The market-wide context every candidate is judged against: BTC and ETH feature rows selected
out of `state["feature"]`, renamed with a `macro_` prefix, and published under
`state["macro_context"]`. Deterministic, no model, never a gate.

## Implementation

1. `engines/macro_context/engine.py`, `contracts.py`, `README.md`. `name = "macro_context"`,
   `number = 6`, `is_gate = False`.
2. The macro pairs come from `config.macro`, a mapping of asset to `{live, archive}` names.
   Live, the engine reads `state["feature"]["pairs"][live_name]`; offline, spec 67's dataset
   builder joins the same columns from the archive pair by `decision_ts`. Same feature names,
   same arithmetic, two spellings of one pair, both in config and neither guessed.
3. Publishes `{"bar_ts", "available": bool, "missing": [asset...], "features": {macro_<asset>_<name>: float | null}}`.
   When a macro pair is absent from `state["feature"]` the engine publishes `available: false`
   with the missing assets named, and returns `OK`. It does not block: what to do about a
   missing context is a judgement for the engines that read it, and engine 8 will find its
   feature vector incomplete and act on that.
4. The macro feature names live in **`modelling/macro.py`** (amended 2026-09-13: `research/`
   may not import an engine's `contracts.py` under invariant 5, so the one place both sides
   can read is `modelling/`), derived from `modelling.features.FEATURE_NAMES` and the
   configured assets; `engines/macro_context/contracts.py` re-exports them. The offline
   builder and the engine cannot disagree about a column name.
5. `tests/engines/test_macro_context.py`, C lane, fixtures taken from engine 5's real output.

## Scope Limits

- Do **not** compute anything new. Selection and renaming only.
- Do **not** block, and do **not** substitute a stale or previous-bar macro row.
- Do **not** hardcode a pair name. Both spellings come from config.

## Check When Done

- A test with the ETH pair absent proves `available: false` and `missing == ["eth"]` while the
  BTC columns are still published.
- Mutation observed red: a missing macro pair silently published as zeros.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
