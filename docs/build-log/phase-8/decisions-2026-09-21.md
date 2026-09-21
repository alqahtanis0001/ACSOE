# Phase 8 decisions, from 2026-09-21

Same shape as Phase 7's `overnight-decisions-2026-09-19.md`. **Every decision names the option
rejected.** **CONTESTABLE** marks a choice the lead would have had to argue for against a
competent objection. **STOPPED** marks something written down and deliberately not acted on.

---

### D1 — Phase 8's files mirror Phase 7's names exactly

**Chose.** `feature-specs/PHASE-8-TASKS.md`, `docs/build-log/phase-8/{lead.md, team-brief.md,
decisions-2026-09-21.md}`, `docs/dataset/phase-8-findings.md`.

**Rejected.** A new scheme (a single `phase-8/` directory holding specs, log and findings
together), which would read better in isolation and would break every cross-reference and habit
the previous seven phases built. The operator asked for the existing convention.

**Note.** Phase 7's decision log was named `overnight-decisions-<date>.md` because it was
written overnight. This one is `decisions-2026-09-21.md`: same place, same style, honest name.

### D2 — The Phase 8 scope conflict is recorded, not resolved by the lead

**What happened.** `ai-workflow-rules.md`'s Phase 8 row is *Live readiness*: `live_guard.py`,
`close_all` end to end, and a 7-day soak. The operator's stated goal is the **live UI and a real
activation button**. These are different bodies of work that share a phase number.

**Chose.** Carry both in the task list, each row marked by origin, and let the workflow row's
criteria remain what `verify.py --phase 8` judges. Flag the conflict to the operator.

**Rejected.** Rewriting the workflow row to match the operator's goal — that is a change to the
project's definition of done, and it is the operator's to make, not the lead's. Also rejected:
silently doing the UI work and leaving the row's criteria to fail at the close.

### D3 — The watchdog task is unregistered now, the scripts are kept

**Chose.** Unregister the `ACSOE-phase7-watchdog` scheduled task (both runs finished; it was
writing a heartbeat every minute against two dead runs). The watchdog script, its tests and its
mutation proof stay committed under `docs/build-log/phase-7/`, and its home directory with the
heartbeat and state history is left on disk as the record of the run.

**Rejected.** Leaving it registered "in case", which would have it fire every minute forever
against finished runs, and deleting its evidence, which is part of Phase 7's paper trail.

### D4 — `scout.rank_feature: expected_move` lands in the committed config; the alphabetical path stays

**Chose.** Set the key in `config/default.yaml`, so a daemon started from the committed config
ranks by engine 8's expected move without depending on a driver flag. **The alphabetical path is
left in place and is now unreachable by default** — unplugged, not deleted, as the operator
ruled. Its tests still exercise it directly.

**Why it was open.** The tracker carried this as an operator question since 2026-09-19: the
committed daemon ranked alphabetically and Phase 7 avoided it only because the replay driver
passed `--ranking expected_move`. "Correct only for as long as someone remembers that the flag is
doing the work" was the tracker's own warning.

**Rejected.** Deleting the alphabetical path (the operator forbade it, and it is the control the
ranking is measured against), and leaving the key absent (the defect the operator asked to fix).

### D4a — STOPPED: setting `scout.rank_feature` makes the daemon fail closed on a fresh clone

**What happened.** D4 was implemented: `scout.rank_feature: expected_move` written into
`config/default.yaml`, its two stale comment blocks corrected, and the scout test that pinned
the key's absence rewritten to keep the alphabetical path covered. **Then 34 of 63 scout tests
went red**, and not on anchors: the engine now publishes only a reason code where those tests
read `entered`.

**Why.** With the key set, engine 7 ranks through the shared function, which loads the
predictor and anomaly artefacts named by `models.*_run_id`. **Those keys are absent in the
committed config** and `models/` is gitignored, so on a fresh clone — and in the test fixtures —
the ranking cannot be scored, `_expected_move_ranking` raises `MissingInputError`, and engine 7
**BLOCKS every tick** with `scout_inputs_unavailable` instead of ranking alphabetically.
Verified directly: the committed config loads with `scout.rank_feature = expected_move` and all
three `models.*_run_id = None`.

**So the housekeeping item is not a one-line change.** It converts "a fresh clone ranks
alphabetically and runs" into "a fresh clone blocks at engine 7 on every tick". That is a change
to what the system does, which the operator's own rules make a stop.

**Chose.** Revert the config key and the test edits, leaving the tree green at 63 passed. Keep a
**docstring correction that is true of the reverted state**: it records that spec 75 is resolved
(R1, expected move), that the committed config does not set the key, and why setting it is not
one line. Report to the operator with options and costs.

**Rejected.** (a) Leaving the change in with 34 red tests — never. (b) Making engine 7 fall back
to alphabetical when the artefacts are missing: that is a fallback on the ranking path, and it
would silently trade a different system from the one Phase 7 measured. (c) Rewriting the 34
tests to supply artefacts: over an hour, in B's lane, and it changes what those tests prove.

### D4b — `rank_feature` lands by option C: `config/daemon.yaml`, with drift caught by a test

**Ruled by the operator, 2026-09-21**, over option B: *"B puts specific `models.*_run_id` values
into the config every clone gets. Those go stale the moment anything is retrained, and a
committed config that names particular artefacts will mislead a future session."*

**Chose.** `config/daemon.yaml`: an exact copy of `config/default.yaml` with one override,
`scout.rank_feature: expected_move`, started with `acsoe --config config/daemon.yaml engine`.
`config/default.yaml` is untouched, so a fresh clone still runs and still ranks alphabetically.

**The loader has no overlay.** `Config.load(path)` reads one file — there is no `extends`, no
include, no environment override for a config key (`platform/config.py` reads the environment
only for credentials). So option C is necessarily a **full second file**, and the operator named
the cost themselves: two files to keep in step.

**What answers that cost:** `tests/platform/test_daemon_config.py` flattens both files and fails,
naming the key, if they differ anywhere but the one declared override. Proven capable of failing
by two mutations applied to a **byte copy written to disk first** (the Phase 8 rule), restored and
hash-checked: a value changed in one file only, and the override itself changed. Both killed.

**Rejected.** (a) Adding overlay support to the loader so `daemon.yaml` could be three lines:
better engineering, but it is A's platform lane, it changes how every config in the project is
read, and it is over the hour the operator has not approved. (b) A copy without the drift test:
that is the two-files-drift failure the operator flagged, with nothing to catch it.

**STOPPED, and reported rather than invented.** `daemon.yaml` alone does not make the daemon
rank: ranking loads the artefacts named by `models.*_run_id`, those keys are absent, and engine 7
therefore still fails closed. **Which trained model a live daemon runs is the operator's
decision**, and the newest artefacts on this machine end their training on 2025-01-04, about
twenty months before today. The file says so in a comment where whoever starts the daemon will
read it.

### D7 — Phase 8's criteria are scoped to the ruled build, not to the phase's name

**Chose.** Four criteria, all PENDING on the day they were written:
`live_client_serves_the_stream` (F1), `pair_rules_key_on_engine_names` (F3),
`console_refuses_a_foreign_origin`, `daemon_reads_the_real_exchange` (the smoke run, judged on a
committed digest as Phase 7 judged its runs). Each is observed PENDING, PASS and FAIL by
`tests/verify/test_phase8_criteria.py`, with the FAIL arms aimed at the *plausible wrong
implementation* rather than at absence: a stream member that exists but is not callable; a
half-finished name migration; an Origin check that also refuses the operator's own kill switch; a
digest from the fake client.

**Rejected.** Writing the workflow row's criteria (`live_guard`, `close_all` live, the soak) as
well. The operator deferred all of it on 2026-09-21, and a criterion for work nobody is doing is
a PENDING that never moves — the thing that made "Phase 8 is green" meaningless before any of
this existed. A test asserts none of the deferred names is registered, so adding one later is a
deliberate act.

**Cost, stated.** `verify.py --phase 8` will not judge live readiness until those criteria are
written. The phase cannot be closed on this scope alone, and the task list says so.

### D5 — The lead edited `engines/scout/contracts.py`, which is B's lane

**Chose.** The lead made the one-line docstring correction itself, under the operator's explicit
instruction, with no B session running.

**Rejected.** Opening a b-store session for a docstring, which costs more than the change.

**Cost, stated.** Ownership rule 1 says write only inside your own paths, and this is an
exception to it. It is recorded here so the exception is visible rather than precedent: it is a
comment, it changes no behaviour, it was gated, and it was the operator's instruction.

### D6 — Costing is done from the code, not from memory

**Chose.** Every estimate in `docs/dataset/phase-8-findings.md` is grounded in a file and line
read for this purpose, by two read-only audits (the live client and the console). Where the code
does not settle a question, the estimate says so and gives a range.

**Rejected.** Estimating from the Phase 7 findings' descriptions of the defects. Phase 7's
"build estimate ran about 5 h over" was a sum of parts, not a measurement, and the lesson was
recorded then: *say "estimate" and measure before promising a time.*
