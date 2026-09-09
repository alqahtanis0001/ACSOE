# 19 — Status band and open positions

**Owner:** C — Interface and models

## Goal

The hero of the interface: a fixed band that answers *is this safe, and what is it doing?* in
under two seconds, and the open-positions region beneath it — both rendered from the seeded
database.

## Implementation

1. Add `GET /api/state` to `src/acsoe/console/app.py`, returning the status-band and
   open-position view models built by spec 17's reader.
2. Status-band fields, in the order `ui-context.md` sets them: Balance, Mode, State, Data age,
   and the power control. Balance comes from `latest_equity_snapshot`; Mode from `config.mode`;
   State from the reader's restart-aware state; Data age from the store watermark measured
   against `console.stale_after_ms`.
3. **State reads `Idle — restarted, not trading`** when the reader reports a changed `run_id`
   and an idle mode, and keeps reading it until the operator activates or freezes. Text only,
   no colour — amber is reserved for live mode, and the words have to carry the meaning anyway.
   A system waiting to be started and a system that stopped on its own are not the same event
   and must not look the same.
4. The open-positions region renders **only when at least one open position exists**. Columns:
   pair, quantity, entry, last, unrealised, target, stop, timeout. Every numeric cell carries
   spec 18's `.num` class; numbers are right-aligned within their column.
5. Percentages are explicitly signed with U+2212 for negatives, through spec 17's
   `format.py`. Colour reinforces the sign; it is never the only signal.
6. Any figure older than `console.stale_after_ms` renders at 50% opacity with its age beside it.
   Stale data must look stale. **The age comes from the clock injected into `create_app`, never
   from a direct read of wall time** — spec 17 item 6. A test that renders a figure and waits for
   it to age is a race; a test that hands the app a `FixedClock` and moves it is deterministic,
   and it can sit exactly on both sides of the threshold.
7. The band is fixed and never scrolls. The positions region scrolls with the rest of the page.

## Scope Limits

- Do **not** build the cycle feed, history or research views — specs 20, 21 and 22.
- Do **not** open a WebSocket here. This endpoint is a plain `GET`; spec 23 layers the socket on
  top of the same view models so the two can never disagree.
- The power control is **markup only** in this spec. The three commands and their write path are
  spec 24.
- Do **not** restore or infer the mode from the store. Mode comes from config and the command
  table; a daemon always starts idle and never restores its mode.
- Do **not** add or change a store method, and do **not** add a config key.
- Do **not** use a raw hex, and do **not** use `--live` for the restart state.
- Do **not** render a position that is not `status = 'open'`. Closed positions are history.

## Check When Done

- Against the seeded database the band renders every field, and the positions region renders the
  seeded open position; against a database with no open positions the region is absent entirely,
  not an empty table.
- Two tests on the State field: differing `run_id`s with idle mode renders
  `Idle — restarted, not trading`; matching `run_id`s renders plain `Idle`.
- Staleness is tested with an injected `FixedClock`, not by sleeping: with the clock set one
  microsecond inside `console.stale_after_ms` the figure renders normally, and one microsecond
  outside it renders at 50% opacity with its age shown. Neither test reads wall time, and
  neither sleeps.
- Every numeric cell carries the tabular-figure class; a negative percentage renders with U+2212.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 1`
