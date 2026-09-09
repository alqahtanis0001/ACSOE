# 16 — Phase 1 criteria in `scripts/verify.py`

**Owner:** C — Interface and models

## Goal

The Phase 1 exit criteria from `context/ai-workflow-rules.md` exist as named, executable checks
that report PENDING until the console they judge is built, so the rest of Phase 1 has a gate to
build against from the first commit.

## Implementation

1. In `scripts/verify.py`, register the Phase 1 criteria against phase `1`:
   - `console_renders_seeded_screens` — builds the app over a seeded temporary database and
     asserts every screen answers: status band, open positions, cycle feed, history and the
     research views. A screen that raises, 500s, or returns an empty body is a FAIL.
   - `console_websocket_pushes_on_change` — connects, writes a row that moves the store
     watermark, and asserts a push arrives within **twice** `console.poll_interval_ms` read
     from config. Never a hardcoded interval.
   - `console_commands_write_rows` — posts each of Activate, Freeze and Close-all and asserts
     exactly one `commands` row each, with `source = 'console'`, the right `command`, and
     `claimed_at`/`consumed_at` both null.
   - `console_live_frame_amber` — asserts the rendered page carries the 3px `--live` frame
     under a live-mode config and **no border at all** under paper.
   - `console_tokens_no_raw_hex` — scans `src/acsoe/console/` and FAILs on any hex literal
     outside the `:root` token block in `static/tokens.css`.
   - `console_tabular_figures` — asserts every numeric column in the rendered markup carries
     the tabular-figure class, and that the class actually resolves to
     `font-variant-numeric: tabular-nums` in the stylesheet.
   - `console_focus_and_reduced_motion` — asserts a visible `:focus-visible` treatment exists
     and is not suppressed, and that a `prefers-reduced-motion: reduce` block drops the change
     flash.
   - `console_restart_banner` — seeds two `runs` rows and asserts the status band State reads
     `Idle — restarted, not trading` when the mode is idle, then reduces the database to a
     single `runs` row and asserts it reads plain `Idle`.
     **This is a presence test, not a value comparison.** An earlier draft of this spec asked
     for plain `Idle` "when the two `run_id`s match", which describes a state the schema
     forbids: `db/migrations/0001_initial.sql` declares `run_id TEXT NOT NULL UNIQUE`, so two
     rows always differ and the only run without a predecessor is the first one ever. The two
     states an operator actually meets are a system waiting to be started, which is the first
     run, and a system that stopped on its own, which is any run with a predecessor. Corrected
     2026-09-09 after C hit it building this criterion; the authority for the rule is the
     `## Restart is visible` section of `context/ui-context.md`, corrected in the same change.
     The helper that reduces the database to one row needs its own test proving it really
     leaves one row, or the negative half quietly becomes a test of something else.
2. Every criterion seeds its own temporary database through
   `acsoe.clients.store.seed.seed_database` and builds the app with an injected `db_path`.
   **No criterion may read `data/db/acsoe.sqlite`.** `data/` is gitignored, so a criterion that
   depends on it cannot pass on a fresh clone.
3. `console_live_frame_amber` fabricates a live-mode config object in the criterion rather than
   editing `config/default.yaml`. `platform/config.py` refuses `mode: live` until Phase 8 and
   that refusal is not to be weakened to make a criterion convenient.
4. The four static criteria — hex, tabular figures, focus, reduced motion — read the files under
   `src/acsoe/console/static/` and `templates/` directly. They must not require a browser, a
   headless engine, or a network fetch.
5. Each criterion reports PENDING, not FAIL, while its subject does not exist: no
   `console/static/tokens.css`, no rendered screen, no WebSocket endpoint yet.
6. Add `tests/verify/test_phase1_criteria.py` proving each criterion returns PENDING on an
   absent subject and PASS against a fabricated minimal subject, the same two-sided proof
   spec 01 established.

## Scope Limits

- Do **not** build any part of the console here. Every subject is specs 17 to 24.
- Do **not** weaken a criterion to make it pass. A criterion that cannot be expressed as a
  check is badly written and gets raised with the lead, not quietly softened.
- Do **not** add criteria for Phase 2 or later.
- Do **not** read `data/`, `logs/` or `models/` from any criterion, and do **not** touch the
  network or require an API key.
- Do **not** modify the Phase 0 criteria or the runner framework beyond registering new
  criteria. Phase 0 is closed and green.
- Do **not** write tests for another agent's code.

## Check When Done

- `python scripts/verify.py --phase 1` prints all eight criteria with no traceback on the
  current tree, reporting PENDING, and exits zero.
- Each criterion flips to PASS against a fabricated minimal subject in its unit test.
- No criterion references a path under `data/`, `logs/` or `models/`.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 1`
