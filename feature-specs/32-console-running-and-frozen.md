# 32 — The status band reads Running and Frozen

**Owner:** C — Interface and models

## Goal

The Phase 1 debt, paid: the status band stops rendering only the two idle readings and shows the
mode the daemon is actually in, read as a fact rather than inferred.

## Implementation

1. Read the persisted mode through spec 31's store accessor, scoped to the current `run_id`, in
   `src/acsoe/console/reader.py`.
2. Render `Running` and `Frozen` in the status band's State field alongside the two existing idle
   readings. Text only, no colour — **amber stays reserved for live mode** and appears nowhere
   else in the interface.
3. **Remove the spec 19 test asserting the field never renders `Running` or `Frozen`.** It exists
   to enforce the Phase 1 deferral, the operator has ended that deferral, and leaving it would
   make this spec unbuildable. Replace it with tests asserting all four readings.

   **Record the deletion in `docs/build-log/phase-2/c-interface.md`, with the reason**, before or
   in the same change. Deleting a test to make a spec pass is normally the exact thing this
   project refuses, so this one needs a written trail saying which decision retired it and when —
   the operator's Phase 2 approval on 2026-09-09. A test removed silently is indistinguishable
   from a test removed because it was inconvenient, and six months from now the build log is the
   only thing that can tell the two apart.
4. Restart detection is unchanged and stays a **presence** test — whether the current run has a
   previous `runs` row — because `run_id` is `UNIQUE` and two rows always differ.
5. **Never infer the mode from the `commands` trail.** That was considered and rejected at the
   Phase 1 close: a transition leaving no claimed row would make the band confidently wrong, and
   for the element answering *is this safe* silent beats wrong. Read the persisted value, or
   render an idle reading; there is no third path.
6. If B's accessor has not landed yet, agree the shape against spec 31's `contracts.py`, mock it,
   and keep building. Do not wait, and do not write in B's directory.

## Scope Limits

- Do **not** write into `clients/store/` or `core/`.
- Do **not** derive, guess or infer a mode. A missing value renders an idle reading.
- Do **not** use the reserved `--live` amber for `Running` — it means real money is at risk, and
  nothing else.
- Do **not** redesign the status band. `ui-context.md` fixes its fields and their order.
- Do **not** weaken the restart-banner behaviour while adding the two new readings.

## Check When Done

- Four tests, one per reading: `Idle`, `Idle — restarted, not trading`, `Running`, `Frozen`.
- A database with no persisted mode renders an idle reading and does not raise.
- The restart banner still behaves per spec 19, asserted in both directions.
- A grep proves the console still contains no path that reads the `commands` table to decide mode.
- `docs/build-log/phase-2/c-interface.md` carries an entry naming the deleted spec 19 test, the
  operator decision that retired it, and the date.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
