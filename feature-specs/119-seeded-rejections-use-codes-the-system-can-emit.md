# 119 — Every seeded rejection uses an `(engine, code)` pair the live system can emit

**Owner:** B — Store and trading

**Phase:** 6. Operator ruling of 2026-09-16, scheduled after the Phase 6 gate; the finding is in
`context/progress-tracker.md` under "the Phase 0 seed's refusal vocabulary is invented". **B's
half lands first; C's spec 120 retires the orphaned prose afterwards.**

## Goal

`clients/store/seed.py` writes no `(engine, code)` pair that the live engines cannot produce, so
the console's rejection feed stops displaying a refusal vocabulary the system has never been able
to emit.

## The finding, in one paragraph

The seed was written in Phase 0, before any engine existed, so plausible codes were invented — and
that was correct at the time. Nothing has compared the two since: `REASON_PROSE` maps both
vocabularies, so the console renders every row and looks right. Spec 99's walking test walks
**engines**, so it proves no engine code is unmapped and cannot prove that no mapped code is
unproduced. The sharpest case is engine 9 `order_book`, which **cannot refuse at all** — it
publishes no estimate and engine 10 `cost` refuses on the absence — so the seeded row shows a trade
stopped by an engine structurally incapable of stopping one.

## Implementation

1. Build-log entry first, at diagnosis.
2. **Derive the truth from the engines, not from the finding's list.** Read each engine's
   `contracts.py` for the codes it actually publishes; the tracker's list is a statement *about*
   the code and may itself have drifted since 2026-09-16. Report any disagreement you find.
3. Repoint every seeded rejection to a pair the live chain can produce. The tracker fixes one of
   them: **engine 9's row becomes engine 10 refusing on the absent estimate.** The others are
   yours to map, and each mapping is a how-choice to record with the option rejected.
4. Keep the seed's *purpose* intact: it must still exercise the console's rejection feed and the
   Phase 3 fixtures, so do not reduce the variety of reasons — swap invented codes for real ones,
   never delete rows to make the problem go away. `seed_fixtures_present` must still PASS with the
   same six fixtures.
5. **A test that fails on today's seed**: walk every `(engine, code)` the seed writes and assert
   each code appears in that engine's own `contracts.py`. That is the check nothing has today, and
   it is what stops the two vocabularies drifting apart again. Observe it red before the fix.
6. Do **not** touch `console/format.py`: every code stays mapped until C's spec 120, because the
   seeded rows exist and must render — an unmapped code renders "No reason was recorded." silently.

## Scope Limits

- `clients/store/seed.py`, `tests/clients/store/**`, `tests/db/**`, B's records. Nothing in C's or
  A's lanes; no engine changes; no schema change.
- Do not invent a code to fit a row. If no engine can produce a refusal of that shape, the row's
  reason is wrong and the row changes, not the vocabulary.

## Check When Done

- The new walking test observed red on the pre-fix seed, green after.
- `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6` (13 criteria, 13 PASS, 0 FAIL, 0 PENDING)
