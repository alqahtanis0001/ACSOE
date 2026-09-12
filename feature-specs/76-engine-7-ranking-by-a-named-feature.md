# 76 — Engine 7 `scout`: the ranking score, as a config-named feature

**Owner:** B — Store and trading

**Phase:** 5. `engines/scout/` is B's.

## Goal

`rank_universe` stops being the recorded absence it has been since Phase 3. It orders the
universe by a feature named in config, read from engine 5's output, with alphabetical order as
the tie-break and as the whole ordering while no feature is configured. Invariant 4: a
deterministic score over features, no model.

## The test the tracker named, and it is not optional

`rank_universe` is always handed an already-sorted sequence, because the engine builds its scan
set with `sorted`. A ranking that merely preserved arrival order would still answer
alphabetically end to end, and an end-to-end fixture cannot see the difference. **Test the
function directly, on input where arrival order and intended order disagree on every
element.** That test exists already for the alphabetical case; it gains the feature case.

## Implementation

1. `rank_universe(pairs, *, features, feature, descending)` in `engines/scout/contracts.py`:
   `features` is `state["feature"]["pairs"]` as engine 5 publishes it; `feature` is
   `scout.rank_feature` or `None`; `descending` is `scout.rank_descending`. With `feature`
   `None`, alphabetical, exactly as today. With a feature: sort by that value, then by pair
   name ascending as the tie-break. A pair whose value is null or absent sorts **after** every
   pair with a value, in alphabetical order among themselves, and is never dropped: a pair
   with no feature is still in the universe.
2. The engine reads the two keys through `context.config`, reads `state["feature"]` through a
   named constant with C's ownership beside it, and publishes `rank_feature` and
   `rank_descending` in `state["scout"]` (`null` and the configured direction when absent).
   `state["feature"]` absent while a feature is configured blocks with
   `scout_inputs_unavailable`: a configured ranking that silently fell back to alphabetical
   would be the placeholder score the operator refused in Phase 3.
3. `README.md`: the recorded-absence section rewritten as history, with the date the ruling
   landed and the feature it named.
4. `tests/engines/test_scout.py`, B lane: the direct test with a five-pair feature map whose
   intended order is the reverse of arrival on every element, both directions; nulls last;
   the block when the feature key is set and `state["feature"]` is absent; and the end-to-end
   tick through the real engines 5 and 7 that shows the candidate changing when the config
   key changes.

## Scope Limits

- Do **not** choose the feature. It arrives in `config/default.yaml` from the operator's
  ruling on spec 75; until then the key is absent and the ordering is alphabetical.
- Do **not** compute a score, a composite, or a normalisation. One named feature, one
  direction, one tie-break.
- Do **not** read a spread or a quote for the ranking. The universe filter already uses the
  live spread for tradability; the ranking is over features only.
- Do **not** touch engines 10 or 11 or `bootstrap.py`.

## Check When Done

- `scout_ranks_by_feature_not_arrival` PASS, observed FAIL against `tuple(pairs)`.
- Mutations observed red: nulls sorted first; the tie-break dropped; the direction ignored.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
