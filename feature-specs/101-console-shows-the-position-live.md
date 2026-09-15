# 101 — The console shows the position live

**Owner:** C — Interface and models

**Phase:** 6. `console/` is C's.

## Goal

The open-positions region, built in Phase 1 against seeded rows, renders a position that a real
daemon opened through engines 18, 21 and 19 — its mark and unrealised PnL changing tick by tick,
its age shown, stale figures faded — pushed over the WebSocket without a page reload.

## Implementation

1. Hand check first, recorded in the build log: a daemon against the fake client at tier 3 opens a
   position; the console reads it. Note every field that renders wrong, empty or stale.
2. Fix what step 1 found in `console/reader.py`, `payloads.py`, `views.py`; the number rules of
   `ui-context.md` hold (signed percentages, U+2212, tabular figures, quote-currency precision from
   `AssetPairs`, 50% opacity past `console.stale_after_ms`).
3. `hold_reason` rendered on the position when the manage chain held, through `REASON_PROSE`.
4. The region is absent — not a stub row — when no position is open, as today.
5. Tests in `tests/console/`: a position written by real engine 19 from real engine 21 payloads
   renders; a second tick's mark moves the rendered unrealised PnL and the WebSocket pushes within
   twice `console.poll_interval_ms`; a held position shows its reason.

## Scope Limits

- Do **not** add a command, a button or any write path. The console places no order.
- Do **not** compute PnL in the browser or the reader beyond formatting what engine 21 published.
- Do **not** use `--live` (amber) styling for paper.

## Check When Done

- `console_shows_position_live` PASS; mutation observed red: the reader serving the previous tick's
  mark.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
