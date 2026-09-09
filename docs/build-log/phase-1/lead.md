# Build log — Phase 1 — lead

Entries the lead owns directly. Consolidated into `docs/build-log/phase-1.md` at phase close.

Minimum headings per entry: What happened, Why, Fix.

## Entries

### `verify.py --phase 1` reported the phase green before it existed

**Agent:** Lead · **Task:** Phase 1 planning · **Date:** 2026-09-09

**What happened.** Establishing a baseline before writing the specs, `python scripts/verify.py
--phase 1` printed `1 criteria: 1 PASS, 0 FAIL, 0 PENDING` and the line `Phase 1 is green: every
criterion PASS, zero PENDING` — against a tree with no console in it at all.

**Why.** `docs_vocabulary` registers on every phase by design, and it was the only criterion
registered for phase 1. A phase whose criteria have not been written yet has nothing to report,
and the runner correctly summarised an empty set as satisfied. The runner is not wrong; the
registry was empty.

**Fix.** Sequenced spec 16 — the Phase 1 criteria — first, ahead of every console spec, and said
so in `feature-specs/PHASE-1-TASKS.md`. Same reasoning that put `verify.py` first in Phase 0:
criteria exist so they can report PENDING while the subject is missing, and PENDING is what
stops an empty phase looking finished.

**Consequence.** Worth stating plainly, because it generalises: a green phase gate means
something only once that phase's criteria are registered. Phases 2 through 8 will each print the
same vacuous green until their first spec lands. That is not a bug to fix in the runner — a
runner that FAILed on an unregistered phase would make every future phase start red for no
reason — but it is a trap for anyone reading a gate result without checking the criterion count.

### Decision: A and B sit Phase 1 out

**Agent:** Lead · **Date:** 2026-09-09

**Options.** Run all three teammates, finding some platform and store work to justify the
headcount; or run only C and accept a single-worker phase.

**Chose.** C alone. A and B have no Phase 1 tasks.

**Because.** `ownership.md` says Phase 1 is almost entirely C's and forbids filler work, so the
question was whether "almost" concealed anything real. Checked rather than assumed, before the
phase opened. For A: `cli/console.py` already loads config, ensures runtime directories,
configures logging and calls `create_app(config)`; `ConsoleConfig` already carries `port`,
`poll_interval_ms` and `stale_after_ms` with the quarter-of-stale validator; `platform/paths.py`
already resolves `data/db/`. For B: every read the console needs already exists on `StoreClient`
— `watermark`, `latest_equity_snapshot`, `open_positions`, `recent_rejections`,
`block_records_in_window`, `recent_closed_trades`, `latest_runs`, `leaderboard`,
`append_command`. Phase 1 consumes B's Phase 0 surface, which is the entire point of building the
console against the seeded schema.

**Cost.** A longer wall-clock phase with one worker instead of four, and a single point of
failure if C blocks. Mitigated by the operator checkpoint after spec 18 rather than by adding
people. The one design constraint this forced: spec 17 makes `db_path` and `clock` keyword-only
with defaults on `create_app`, so the signature stays call-compatible and A's entry point needs
no edit — a phase with no A in it must not require an A change.

### The undesigned console screens, resolved without inventing one

**Agent:** Lead · **Task:** specs 21, 22 · **Date:** 2026-09-09

**What happened.** Phase 1's criteria name history, the research views, the leaderboard and the
SHAP view. `ui-context.md` designs none of them, and the Phase 0 close had already flagged this
as a scope question for the operator rather than something C should resolve.

**Why.** Two different problems were hiding under one heading. History and the leaderboard have
no *design* but do have *data*: the Phase 0 seed carries trades, rejections and leaderboard rows,
and `ui-context.md` already says an undesigned screen inherits the cycle feed's table treatment.
The SHAP view has neither — `rejections.shap_ref` points at a Parquet artefact the training
pipeline does not write until Phase 5.

**Fix.** Specced 21 and 22's leaderboard normally under the inherited treatment, and specced the
SHAP pane as an honest empty state naming Phase 5 as its producer, with an explicit ban on a
placeholder chart, a chart of zeros, or sample explanations. Put the call to the operator at
approval rather than deciding it silently. The operator confirmed: keep the empty state, do not
design a view for data that arrives in Phase 5.

**Consequence.** A view that reads a path which will not exist for four phases cannot be
verified now, so building one would have meant a criterion that could not honestly pass. The
empty state is the verifiable option as well as the truthful one.

### Operator additions at approval: four tests that can fail

**Agent:** Lead · **Date:** 2026-09-09

**What happened.** The operator approved the nine specs with four amendments, all of the same
shape: an assertion that could not distinguish a working implementation from a broken one.

**Fix.** Folded into the specs before C started.

- **Spec 20.** The two-run seed reuses `cycle_id` values deliberately, so the feed's ordering
  test must assert that ordering by `ts` yields a *different* sequence than ordering by
  `cycle_id` would — not merely that the `ts` ordering looks right. The weaker form would pass
  against a seed where both orderings coincide, at which point it asserts nothing. Same
  reasoning as B's Phase 0 overlap fixture: a fixture that cannot fail is not a fixture.
- **Spec 19.** Staleness reads the injected clock, never wall time. A test that renders a figure
  and waits for it to age is a race that passes on a fast machine; with `FixedClock` the test can
  sit one microsecond either side of `console.stale_after_ms`.
- **Spec 17.** The reader's read-only connection is proven by attempting a real `INSERT` and a
  real `UPDATE`, not by asserting the URI contains `mode=ro`. Checking the string proves only
  that the code says what it meant to do — a typo, a fallback that reopens read-write, or a later
  refactor would all still pass. Spec 14's network guard set this precedent.
- **Spec 22.** Confirmed as specced.

**Consequence.** Three of the four are the same defect class the project keeps finding: an
assertion written from the implementer's side, which is satisfied by the code as written rather
than by the behaviour being correct. Worth watching for in review.

## Carried into this phase from Phase 0

Recorded here so they are decided rather than rediscovered. Neither is a defect.

- **Widening `TOOLCHAIN` beyond `src/`.** `mypy --strict scripts/` reports 2 errors in
  `verify.py` — `candidate` bound to a `Path` in one loop and a `str` in the next, at the top of
  `_interpreter_with_toolchain` — and `ruff check tests/` reports 2 violations (`UP031` in
  `tests/core/test_contracts.py`, `SIM300` in `tests/db/test_migrations.py`). None is reachable
  by the gate that implements them. Deferred from Phase 0 deliberately: changing what every
  phase's gate asserts belongs at a phase boundary.
- **The console screens with no design.** `ui-context.md` specifies the status band, open
  positions and the cycle feed. History, the research views, the leaderboard and the SHAP view
  are named in the Phase 1 criteria and designed nowhere, and their upstream engines do not exist
  until Phase 4 and Phase 5. C should not resolve this by inventing a screen; it is a scope
  question for the operator.
