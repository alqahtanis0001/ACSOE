# 57 — The console reads real rows

**Owner:** C — Interface and models

**Phase:** 4. `console/` is C under the permanent ownership map.

## Goal

The history screen renders trades and rejections written by a live engine 19 rather than by
the Phase 0 seed, and the cycle feed stops scanning the whole of `block_records`.

## Implementation

1. Point the cycle feed at the most-recent-N read B adds in spec 51. It has been a full-table
   scan since Phase 1; engine 19 now writes a row per guard per tick, which is when that stops
   being harmless. Recorded in the tracker as a **before Phase 4** item.
2. The history screen reads `trades` and `rejections` as engine 19 writes them. A rejection
   with a `reason_code` absent from `REASON_PROSE` renders *No reason was recorded.* —
   silently, with no error anywhere — so confirm every code engine 19 can write is in the map,
   and add the missing ones.
3. **CORRECTED 2026-09-11 — the empty state CANNOT yet show the scan tally, and this step was wrong to say it could.** It could not before:
   the console is a separate process reading SQLite and never saw the in-memory state where
   the tally lived for one tick. A stale comment in `console/reader.py` naming the wrong
   engine is fixed by this same change. Both are carried from the Phase 3 handoff.
4. Tests in `tests/console/`, C lane.

## Rules this spec is held to

- **Every assertion must be proven capable of failing**, with the mutation and the red message
  recorded in `docs/build-log/phase-4/c-interface.md`. Name at least: the history screen
  reading the seed rather than the live rows — a test that passes against a seeded database is
  not testing what this spec is for, and the seed and the live rows must therefore be
  distinguishable by value in the fixture.
- A rendering test that asserts only that the page returns 200 cannot fail for the reason it
  exists. Assert a value that came from a live row.

## Scope Limits

- Do **not** change the design tokens, the number rules or the layout. `ui-context.md` holds
  those and Phase 1 settled them.
- Do **not** add a store method. That is B, spec 51.
- Do **not** let the console write anything except a command row.

## Check When Done

- `console_history_reads_real_rows` is PASS.
- Every Phase 1 and Phase 2 console criterion still PASSes unchanged.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 4`
