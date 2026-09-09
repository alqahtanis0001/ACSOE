# 20 — Cycle feed and the empty state

**Owner:** C — Interface and models

## Goal

The single most-viewed screen in the product: one column, newest first, showing what the system
actually did each tick — including, and especially, when it did nothing.

## Implementation

1. Add `GET /api/feed` to `src/acsoe/console/app.py`, composed in spec 17's reader from
   `recent_rejections` and `block_records_in_window`.
2. **A tick is `(run_id, cycle_id)`, never `cycle_id` alone.** `cycle_id` restarts at 1 with each
   process, so every join between a rejection and a block record uses both columns. **Order by
   `ts`, never by `cycle_id`** — ordering a cross-restart sequence by `cycle_id` silently
   interleaves two runs, and the Phase 0 seed deliberately spans two `run_id`s to catch exactly
   that.
3. Each row renders `time · pair · outcome · reason`, per the `ui-context.md` layout.
4. Reasons are written for the operator, not the log: "Net edge −0.21% after fees", never
   `cost_gate_fail`. Map `reason_code` to operator prose in `src/acsoe/console/format.py`. A
   code with no mapping falls back to the row's stored `reason` text — never to the bare code,
   and never to an invented sentence.
5. A blocked tick with no candidate renders as a **block row** naming the blocker, not as a
   rejection. The two tables are separate on purpose: folding blocks into rejections would mean
   anyone counting refused trades was also counting feed outages. A blocked tick that *did* have
   a candidate produces one row from each table, joined on the tick.
6. **The empty state is the main state.** When nothing qualified, do not render "No results" —
   render what the system did, in the shape `ui-context.md` gives: pairs scanned, how many
   entered the tradable universe, how many reached the cost gate, how many cleared it. Stillness
   is information. In Phase 1 those counts come from the seeded rows; where the seed carries no
   count for a stage, the line says so rather than showing a zero that looks like a result.
7. The feed scrolls beneath the fixed status band, newest first.

## Scope Limits

- Do **not** fold `block_records` into `rejections` or render one as the other.
- Do **not** order by `cycle_id`, and do **not** join on `cycle_id` alone.
- Do **not** invent a reason string for a `reason_code` the seed does not carry. An unmapped
  code shows its stored `reason`; a genuinely ambiguous one is an open question in
  `context/progress/c-interface.md` and a stop, not a guess.
- Do **not** build the WebSocket (spec 23) or the commands (spec 24).
- Do **not** add or change a store method, and do **not** add a config key.
- Do **not** paginate infinitely or hold the whole table in memory — the feed is a bounded
  recent window.
- Do **not** use a raw hex, and do **not** animate the feed. New rows appear; they do not fly in.

## Check When Done

- Against the seeded database the feed renders both rejection rows and candidate-less block
  rows, newest first.
- A seed spanning two `run_id`s with reused `cycle_id` values orders correctly by `ts`, with no
  interleaving — one test asserting exactly this.
- A tick where two guards blocked renders as one tick, not two.
- Against a migrated-but-empty database the empty state renders and states what the system did,
  and the string "No results" appears nowhere.
- An unmapped `reason_code` falls back to its stored `reason` rather than the code.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 1`
