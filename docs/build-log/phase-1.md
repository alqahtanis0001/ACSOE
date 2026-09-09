# Build log — Phase 1: Interface

Written by the agents as work happens, per `context/script-rules.md`.
Record every non-trivial problem and its fix. This cannot be reconstructed later.

The per-agent files are `docs/build-log/phase-1/c-interface.md` and
`docs/build-log/phase-1/lead.md`. A and B did no Phase 1 work; their files carry a line saying
so rather than being absent, because an empty file and a missing file mean different things.

## Phase 1 summary

*Written by the lead at phase close, 2026-09-09.*

**Built.** The whole operator console, against the Phase 0 seed and nothing else. One HTML page
serving a fixed status band, an open-positions region, the cycle feed, history and the research
views; a WebSocket that pushes when the store's watermark moves; and three commands that write
rows to the `commands` table. Nine specs, 16 to 24, all by Agent C. The phase is green —
`python scripts/verify.py --phase 1` reports 9 criteria, 9 PASS, 0 FAIL, 0 PENDING — and the
lead re-verified independently of C's report: `pytest` 707 passed, `mypy --strict src/` clean
across 35 source files, `ruff check src/` clean.

**Verify output.**

```
ACSOE verify - phase 1
repo: C:\Users\saad2\Documents\GitHub\ACSOE

PASS    docs_vocabulary                     14 files scanned, 9 retired terms, no hit
PASS    console_renders_seeded_screens      all 5 screens answered over a seeded database
PASS    console_websocket_pushes_on_change  pushed 517ms after the watermark moved, inside the 1000ms budget
PASS    console_commands_write_rows         one correct unclaimed row each for activate, freeze, close_all
PASS    console_live_frame_amber            live renders a 3px var(--live) frame and paper declares no border anywhere
PASS    console_tokens_no_raw_hex           11 hex values, all inside the src/acsoe/console/static/tokens.css token block; 12 console files scanned
PASS    console_tabular_figures             21 numeric cell(s) carry `.num`, and `.num` is the only tabular-figure rule
PASS    console_focus_and_reduced_motion    2 visible `:focus-visible` rule(s); the reduced-motion block drops the flash
PASS    console_restart_banner              a changed run_id reads the restart banner; a first start reads plain `Idle`

9 criteria: 9 PASS, 0 FAIL, 0 PENDING
Phase 1 is green: every criterion PASS, zero PENDING.
```

**Headcount.** One teammate. `ownership.md` says Phase 1 is almost entirely C's and forbids
filler work, so the lead checked whether "almost" concealed anything real before opening the
phase. It did not: A's `cli/console.py`, `ConsoleConfig` and `platform/paths.py` already provided
everything the console entry point needed, and every store read the console required already
existed on `StoreClient`. A and B sat the phase out. The one design constraint that followed is
worth keeping: spec 17 made `db_path` and `clock` keyword-only with defaults on `create_app`, so
a phase with no A in it required no A change.

**Problems of note.** Four are worth reading in full below.

The recurring theme is *assertions that could not fail.* The operator caught the pattern at spec
approval and amended three specs over it; C then found five more instances in its own work — a
history test that walked a pydantic model's fields instead of its rows and so had never asserted
ordering at all, a truthiness assertion against a model that is always truthy, and two docstrings
promising test modules that a crash had taken before they were written, leaving a green suite
whose green meant nothing. Every replacement asserts on the real keys, behind guards that stop a
degenerate fixture satisfying them in both directions at once.

Two documents described a state the schema forbids. `ui-context.md` and spec 16 both asked
whether the current and previous `run_id`s *differ*; `run_id` is `UNIQUE`, so they always do. The
prose one paragraph later was right and the mechanism was wrong, in both files, and they agreed
with each other — which is precisely the defect class `docs_vocabulary` cannot catch, because a
rule that has just been written has no retired token to grep for. It was found by someone trying
to build the negative half of a test.

The status band cannot tell Running from Frozen, and C stopped rather than guess. The operator
ruled it deferred to Phase 2 with the approach fixed: the `core/` command reader persists the
mode it already owns. Deriving it from the trail of claimed `commands` rows was considered and
rejected — it is inference, and a transition leaving no claimed row makes the band confidently
wrong rather than silent, which for the one element answering *is this safe* is the wrong failure
mode.

The intermittent native fault carried over from Phase 0 was re-opened with evidence. Its recorded
signature was wrong: it is not confined to pydantic's `model_dump`, and it has now been seen in
`sqlite3`'s C extension and — as a bogus `TypeError` from pure-Python pyyaml — in ordinary
interpreter state. Three unrelated libraries, one of them not compiled, which is what memory
corruption looks like and is not what a library defect looks like.

**Deliberately deferred.**

- **Running and Frozen in the status band → Phase 2**, where a daemon first runs. Not optional:
  a band reading `Idle` over a running system is actively wrong, and spec 19 carries a test
  asserting the field never renders either word this phase so the deferral is enforced rather
  than remembered.
- **The SHAP pane stays an empty state → Phase 5**, when the training pipeline first writes an
  attribution artefact. The operator confirmed this explicitly at approval and again at the
  checkpoint. No placeholder chart, no chart of zeros, no sample explanations.
- **The cycle feed's full scan of `block_records` → before Phase 4.** Harmless while the table
  holds a seed; engine 19 `memory` starts writing a row per guard per tick in Phase 4.
- **Widening `TOOLCHAIN` beyond `src/`, and registering `toolchain_green` for every phase →
  Phase 2 boundary, operator's call.** These interact and should be taken together, along with
  the intermittent fault: registering the toolchain check everywhere also spreads that crash
  across every phase's gate.

**Found and not deferred.** The `core/` command reader does not work. `orchestrator.py` looks up
`store.claim_pending_commands`, which `StoreClient` does not have, so the lookup returns `None`
and a daemon wired to the real store would silently ignore every Activate, Freeze and Close-all
ever written. The startup re-application of claimed-but-unconsumed rows is not wired at all. This
is Phase 0 work in a lead-only file, it was invisible to every gate because the only
implementations of that shape are test doubles, and it is fixed before any Phase 2 work begins.
Full entry in the lead's file.

**Process.** Three IDE crashes killed the working session mid-phase. None cost code: each time
the tree was re-assessed against the gate rather than against the agent's transcript, and C was
restarted from verified state. Twice they did cost C's build log and progress file, because the
code had landed and the documentation had not — which is an argument for the write-as-you-work
rule in `script-rules.md` rather than against it. The rule is what made the loss recoverable in
minutes instead of being gone.
