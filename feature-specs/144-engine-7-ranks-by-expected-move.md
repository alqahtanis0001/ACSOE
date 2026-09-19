# 144 — Engine 7 orders its universe by engine 8's expected move

**Owner:** Lead (the contract and the registry); B (engine 7); C (the shared scoring function in
`modelling/`)

**Phase:** 7. Operator ruling 2026-09-19 (R1): the ranking is the predictor's expected move,
batched. Invariant 4 is amended in the operator's words (spec 126).

## Goal

Engine 7 examines its filtered universe in descending order of expected move. **Every gate still
judges the chosen candidate independently.** Engines 13 and 8 run after engine 7 on that one pair
exactly as today, and no gate's verdict depends on the ranking.

## The arrangement, and the question it leaves (R11)

**The registry order does not change.** Engine 7 computes the ranking itself, through a pure
function in `modelling/`. Engines never import each other, and `modelling/` is the one package both
sides may import. That function scores every universe pair with the fold's predictor and
calibrators (about 1 ms for 127 pairs, batched). Engines 13 and 8 then re-judge the chosen pair from
scratch, as they do today.

**RULING REQUIRED (R11): does the ranking skip pairs the anomaly and DI gates would refuse?**

- **(a) No.** Rank by expected move alone. The cleanest separation: the ranking never consults a
  gate criterion. But a top-ranked pair that engine 13 or 8 then refuses loses the bar, and the
  trade count for this arrangement is **NOT MEASURED**.
- **(b) Yes.** Rank only among pairs whose anomaly score and DI would pass, computed batched with
  the same artefacts (about 0.9 s per bar, spec 137). The gates still re-judge the chosen pair,
  independently and with the same result. This is the arrangement the 46-trade figure in
  `phase-7-findings.md` §4 was measured under, and so the one the amendment was decided on.

**Lead's recommendation: (b).** It is the arrangement the operator's decision rests on. The gates'
verdicts are unaffected, because each re-computes its own verdict for the chosen pair from the same
artefact.

## Implementation (after R11)

1. **C:** `modelling/ranking.py` (or a function in an existing module). Given the feature rows of the
   universe and the loaded artefacts, return pairs ordered by expected move descending, ties by
   name. Under (b), exclude pairs whose batched anomaly score or DI exceeds the artefact's
   threshold. It uses `modelling.expected_move`, `modelling.calibration` and, under (b),
   `modelling.di` (spec 137) exactly as engines 8 and 13 do, so the numbers are identical by
   construction.
2. **B:** engine 7's `rank_universe` takes that order when `scout.rank_feature` names
   `expected_move`. It loads the artefacts through `store.model_run_dir`, as engines 8, 13 and 15 do.
   It publishes the ranked list's top values for the console, and **it never blocks on a ranking
   value**. A failure to score is `scout_inputs_unavailable`, as for any other missing input.
3. **Lead:** `engine-contracts.md` (engine 7's row and prose), `project-overview.md`'s list of
   engines with no machine learning, and the ownership seam for the ranking function. See spec 126
   step 4 for the retired-vocabulary hazard in that count.

## Scope Limits

- No registry reorder, and no change to what engines 13, 8, 10, 11, 15 or 16 decide.
- Net-margin ranking is not built (§R.2: rejected on live feasibility).
- The ranking uses only the active fold's artefacts, never another fold's.

## Check When Done

- For a fixed tick, the ranking's expected move for the chosen pair equals engine 8's published
  value for it, recomputed rather than read back.
- Mutating the ranking (reversing it) changes the candidate and changes no gate's verdict on any
  given pair.
- `rank_universe` is tested directly on input where arrival order and the intended order disagree
  on every element.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
