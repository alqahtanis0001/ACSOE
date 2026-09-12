# 77 — Register the Phase 5 engines, verify, report

**Owner:** Lead

**Phase:** 5. `bootstrap.py`, `config/default.yaml` and the tracker are the lead's.

## Goal

Engines 5, 6, 12, 13, 8 and 15 join the opportunity chain in registry order, engine 20 is
confirmed in the offline chain, the operator's ruled values land in the YAML, and the phase is
verified on a quiet tree.

## Implementation

1. **Last, after every C spec is green and each new engine has been driven through two real
   orchestrator ticks by an agent that did not build it.** A half-wired engine in the live
   chain turns every other criterion's failure into a puzzle; that deferral has paid three
   times.
2. `OPPORTUNITY_CHAIN` becomes `5, 6, 7, 12, 13, 8, 10, 11, 15` with the registry table's
   order kept and 9, 14, 16, 18 still absent for Phase 6. The module docstring says which
   holes remain and why.
3. `cli/research.py`'s `OFFLINE_CHAIN` carries `(TournamentEngine(), BacktestEngine())` in
   registry order, landed by A under spec 61; the lead confirms the invariant-5 reachability
   guard is green with both.
4. The operator's values, once ruled, into `config/default.yaml` one line each:
   `prediction.di_percentile`, `anomaly.threshold_percentile`, `skeptic.veto_threshold`,
   `scout.rank_feature`. Each PENDING criterion turns to PASS without a code change, which is
   what the two-sided proof was for.
5. **Before the gate: ask every teammate for an explicit stop and wait for it.** Then run, in
   order, `--phase 0` through `--phase 5`, each redirected to a file under `logs/verify/` and
   read from the file. Phases 0 to 4 must report the same counts they reported at the Phase 4
   close.
6. Report to the operator in the run-protocol's order, with the verbatim `--phase 5` output,
   and stop. Do not consolidate the build logs and do not close the phase.

## Scope Limits

- Do **not** register before the rehearsal. Same rule as specs 47 and 58.
- Do **not** paste a value the operator has not ruled.
- Do **not** touch a teammate's file to make a criterion pass. Send the FAIL to its owner.
- Do **not** close the phase or consolidate the build logs. The operator has withheld both.

## Check When Done

- `is_gate_matches_registry` reports 15 engines registered, 0 mismatches, 7 gates.
- Phases 0 to 4 unchanged; `--phase 5` every criterion PASS, zero PENDING, or the report
  says exactly which are PENDING and on what.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
