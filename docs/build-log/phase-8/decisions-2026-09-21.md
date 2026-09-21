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

### D8 — The daemon runs fold 404's artefacts; the drift test widens to exactly four keys

**Ruled by the operator, 2026-09-21.** `models.prediction_run_id`, `anomaly_run_id` and
`skeptic_run_id` are set to `train-20260913T205245-067b2b9d-f404-p7` in `config/daemon.yaml`
**only**. One directory carries all three artefact kinds, so the three keys take one value.

**Chose.** Widen `DECLARED_OVERRIDES` in `tests/platform/test_daemon_config.py` from one key to
four, and keep the test failing on anything else. Two new tests: the run ids are asserted **by
value and the directory is asserted to exist on disk** (a run id naming a missing directory fails
the same way as an absent key, only later and less legibly), and `default.yaml` is asserted to
name no artefacts at all.

**Proven capable of failing**, on a byte copy written to disk first, restored and hash-checked:
an unlisted risk value changed only in the daemon file, an unlisted safety limit likewise,
`mode` flipped to `live`, and a declared key given a *different* value. All four killed.

**Recorded, not fixed (operator ruling):** fold 404's training data ends 2025-01-04, so the live
screens will show a twenty-month-stale model's decisions against today's market. The phase
demonstrates the system working, not trading well. Nothing is retrained.

### D9 — F2 shares a key with `fees.py`, and the nonce risk is smaller than it was recorded as

**What the question was.** Phase 7 recorded that the daemon and `fees.py` share one API key and
that "nonces can collide once the daemon runs". F2 puts a private `TradeVolume` call on the
daemon's side, so the operator asked whether F2 triggers it.

**Measured, not assumed.** Both sides already count **microseconds** — the client takes
`to_micros(clock.now())` then `max(candidate, last + 1)`; `fees.py` uses `time_ns() // 1000` and
its docstring says it chose that scale for this reason. The daemon re-reads the fee tier on a
60-second TTL, so about two private calls a minute; `fees.py` polls hourly. A daemon making two
calls a minute cannot run measurably ahead of wall clock, so **a collision needs two calls inside
the same microsecond.**

**Consequence if the separate key is skipped:** the lower nonce is rejected, one hourly poll
fails, `fees.py` writes it as a `gap` naming the absence, and the next hour succeeds. **The
daemon is unaffected; the recorder is not affected at all** — `record.py` and `funding.py` use
the public websocket and no credentials. The cost is occasional, *visible* gaps in the recorded
fee history.

**Chose.** Report it as **0.5 h of plumbing (a `KRAKEN_READONLY_*` pair with fallback) plus about
10 minutes of the operator's time**, recommended but not blocking, and let the operator decide.
**Rejected:** treating it as blocking (the evidence does not support it), and ignoring it (the
operator asked, and the gap is in the recorded fee history they will later analyse).

### D10 — OPEN, for the operator: `data_guard` blocks every tick against the real universe

**Found by the smoke run**, 2026-09-21 04:42–05:04Z, the daemon in paper mode against the real
Kraken exchange. **This is a WHAT decision and the lead has not taken it.**

**What happened.** The daemon started, consumed the console's `activate` row, reached
`mode: running`, and engine 2 derived a subscription of **the USD universe in v2 names**
(`0G/USD`, `1INCH/USD`, `ADA/USD`, … **668 pairs**, out of the 1,450 `AssetPairs` returns) which
the v2 feed accepted. Quotes arrived and accumulated — `quote_count` 0 → 235 over the run — and
engine 19 wrote an equity row every tick. **Then 18 of the 22 ticks were blocked by
`data_guard`**: tick 1 for having no quote at all yet, and 17 naming one stale pair each, **9
distinct pairs**, the repeats getting steadily worse because a pair that stops quoting never
recovers:

```
tick  4  AEVO/USD 172s old, past the 120s the guard allows
tick 14  COOKIE/USD 130s → 15  192s → 16  253s → 17  315s → 19  438s
tick  9  CSPR/USD 144s → 21  306s → 22  369s
```

**22 ticks, 0 `scout_tallies`, 0 rejections, 0 orders.**

**Why.** `data_guard` judges the *tick* on the oldest published quote across **every subscribed
pair**, against `data_guard.max_data_age_s: 120`. With 668 pairs — only 235 of which had quoted
at all by the last tick — there is always some illiquid pair that has not traded for two minutes,
so the guard blocks the whole tick permanently. Phase 6 never saw it because the fake exchange serves four pairs; Phase 7 never saw
it because D7 stamps the replay's synthetic quote at `now`, which was recorded at the time as
making one gate condition "structurally inert for the whole simulation". **Live, nothing makes it
inert, and the system as configured cannot trade at all.**

**Options, with the lead's recommendation:**

| Option | What it does | Cost | Case against |
|---|---|---|---|
| **(a) Judge the candidate's data, not the whole subscription** (recommended) | `data_guard` blocks when the data behind *this tick's decision* is stale, and records per-pair staleness for the rest | engine 4 change + engine 7 seam, a gate, ~2–3 h | It is a change to a gate's meaning, and gates are the operator's. Also needs care: the guard runs *before* a candidate exists, so "the candidate's data" means the universe engine 7 will consider |
| **(b) Exclude stale pairs from the universe instead of blocking the tick** | engine 7 drops a pair with no fresh quote (it already has `no_live_quote`); the guard stops looking at pairs nobody is trading | engine 4 + engine 7, ~2–3 h | Moves a data-quality judgement into the universe filter, where a *pair* problem is already handled but a *feed* problem is not |
| **(c) Narrow the subscription** | engine 2 subscribes to the liquid subset | ~1 h | Changes the tradable universe, which is a Locked Decision, and hides a feed fault rather than judging it |
| **(d) Raise `max_data_age_s`** | e.g. 600 s | minutes | Does not fix it — `COOKIE/USD` reached 438 s and `CSPR/USD` 369 s inside a 21-minute run, both still climbing — and it weakens the staleness rule for the pair actually being traded |

**Skipped and continued, per the operator's overnight instruction.** No smoke digest is
committed, so `daemon_reads_the_real_exchange` stays **PENDING** rather than being made to pass
on a run that never reached the funnel.

### D11 — OPEN, for the operator: in paper mode the screens show the paper ledger, not the real wallet

**Found by the same run.** The operator asked to see *my real wallet balance* on screen. The run
fetched the real account (`private_calls_enabled: true`, `Balance` and `TradeVolume` both HTTP
200), but the equity the console renders is **5,000.00 USD** — `paper.starting_balances`, the
paper broker's own ledger.

**Why, and it is deliberate.** Invariant 2's paper-ledger ruling (2026-09-16) makes the paper
broker the authority on its own cash: *"In paper mode the balance is always the paper broker's…
whether or not the real Balance fetch succeeded"*, because a fetched balance plus simulated fills
describes no account that exists. So paper-against-real gives real market data, real pair rules,
real fees and **simulated cash** — by design.

**Options:** (a) render the real fetched balance beside the paper ledger, labelled as the
exchange's (console + a payload field, ~1–1.5 h, and the numbers must never be added together);
(b) accept it and label the figure "paper cash" on screen (~15 min); (c) `mode: live`, which the
operator deferred. **Recommendation: (b) now, (a) when the main window is built** — the cheap fix
removes the misreading, and the full fix belongs with the wallet panel.

### D12 — The smoke run needed a clean database, and the seeded one is restored afterwards

**What happened.** The first smoke attempt ran against `data/db/acsoe.sqlite`, which held the
**Phase 0 seed** — deliberately carrying a 20% drawdown, an 8-loss streak and two open positions
so that Phase 3 could test `safety` against them. The daemon read that history, `safety`
escalated `close_all` on cycle 4, and engine 1 errored every tick with
`PaperBrokerError: no pair rules for XBT/USD` — the seed names its positions `XBT/USD` while the
client now serves the v2 name `BTC/USD`.

**Chose.** Move the seeded database aside (a byte copy was taken first), run the smoke on a fresh
one, and restore the seeded file afterwards. **Rejected:** adding a `--db` flag to `acsoe engine`
(a CLI change, A's lane, and more than the run needed), and running on the seed (the account state
freezes the daemon before it reaches the market, which measures nothing).

**Recorded, not fixed — and worth a ruling later:** the Phase 0 seed names pairs `XBT/USD` where
the engines and the v2 feed use `BTC/USD`. Nothing in the test suite catches it because the fake
client's own fixture is keyed `BTC/USD`; it only appears when a daemon reads seeded positions
through a client serving v2 names.

### D15 — CORRECTED: the three silent ticks are by design, and the run was too short to reach the funnel anyway

**This entry was first written as an OPEN defect — "three ticks left no record of why nothing
happened" — and that was wrong.** It is corrected here rather than deleted, because the wrong
version was committed (`cc642d7`) and because the way it was wrong is the point.

**What is actually true.** Ticks **3, 5 and 8** were `running`, carry no `data_guard` block, and
produced nothing. The opportunity chain is 5 `feature` → 6 `macro_context` → 7 `scout`, and
engine 5 **returns PASS, not BLOCK, when no decision bar closed on that tick** — its own comment
says so: *"Fourteen ticks out of fifteen end here. PASS, not BLOCK: nothing is wrong, there is
simply no new candidate, and the orchestrator stops the chain on a PASS without recording a
blocker."* `decision_bar_s: 900`. The daemon ticks every 60 s. So 14 ticks in 15 **are supposed
to** end silently at engine 5, and those three are three of them. Nothing is missing.

**And the fact that matters much more, which the wrong version obscured.** The run spanned
04:42:00–05:03:32Z and therefore crossed **exactly one** 15-minute bar boundary, 05:00:00Z. The
tick that carried that closed bar is **cycle 19 at 05:00:26 — and it was blocked by `data_guard`,
`COOKIE/USD` 438 s stale.** So the smoke run's verdict on the funnel rests on **one** tick, not
twenty: exactly one tick could ever have produced a candidate, and D10 took it.

**Consequences, both ways.**
- **D10 is not softened.** The one tick that mattered was blocked, and `COOKIE/USD` and
  `CSPR/USD` were still climbing when the run ended, so the next bar would have been blocked too.
- **But the run cannot support a stronger claim than that.** A 21-minute run at a 15-minute
  decision bar is not evidence about the funnel; it is evidence about the guard. Any statement of
  the form "the system would have found no candidate" is unsupported, and none is made. **The
  ruling on D10 should be followed by a run of at least a few hours**, so that several bar closes
  are observed rather than one.

**What is left of the original point, and it is small.** The console cannot distinguish "no
decision bar closed" from any other silence, because neither is written anywhere. That is a
labelling gap in the main window rather than a missing record, it belongs with the main-window
work, and it is **not** an OPEN decision: the system's behaviour is correct and documented.

**The lesson, recorded because it is the second time tonight.** Both wrong versions came from
describing a run from my own summary of it instead of from the run and the code — the same error
as the "~1,450 pairs" figure an hour earlier. Reading `engines/feature/engine.py` took two
minutes and turned a fabricated defect into the single most useful number in the run.

### D16 — F3 is pushed to a branch, because "safe" and "gated" are two different things

**The conflict.** Standing practice: *a push, not a commit, is what makes work safe* — never leave
hours of work in a working tree overnight. Project rule: **`main` takes only gated boundaries**,
and F3's gate is not obtainable on this machine tonight. Doing either one alone breaks the other.

**Chose.** Push F3 to **`phase-8-f3-ungated`** (`ce54fa6`), with the refusal in the commit
*subject* so it cannot be missed: `UNGATED: DO NOT MERGE WITHOUT A GREEN GATE`. The commit body
lists the evidence and names it as evidence about the content rather than a gate. Then restore the
same four files into `main`'s working tree, **unstaged**, verified byte-identical to the gated blob
(`2779ca6166dcdf52`), so the morning's gate has files to copy and the tree is exactly as it was.

**Rejected:**
- *Commit it to `main` anyway, noting the gate could not run* — this is the one thing the project
  forbids the lead to do, and "the machine was broken" is precisely the excuse that would make the
  rule meaningless. The rule exists for nights like this.
- *Leave it in the working tree only* — one power cut and F3 is gone, which is the exact failure
  the standing practice was written after.
- *Stash it* — a stash is local, unpushed and easy for the next session to miss; it is not safe in
  the sense the practice means.

**Cost, stated.** There is now a branch that must be merged or deleted; a branch left to rot is
its own kind of mess. The handover names it, its hash and its precondition in the item-3 row.

### D13 — F3's re-keying broke a recording script's drop report, and it is joined rather than re-keyed

### D13 — F3's re-keying broke a recording script's drop report, and it is joined rather than re-keyed

**What happened.** The F3 gate went **red**, and it caught two things nothing local had:
`src/acsoe/clients/kraken/rest.py:266` annotated `WS_ASSET_ALIASES: Final` **without importing
`Final`** — invisible at runtime because `from __future__ import annotations` makes the
annotation a string, so every test passed while `mypy --strict` and `ruff` both named it; and two
tests in `tests/scripts/test_record_asset_pairs.py` failed, because `check_rules()` in
`scripts/record_asset_pairs.py` computes its dropped-pair list as `set(result) -
set(snapshot.pairs)`. With the snapshot keyed by the v2 symbol, that subtraction names **every**
pair as dropped instead of the unparsable ones.

**Chose.** A public `engine_pair_names(result) -> {rest_key: v2_symbol}` in the client, built
through the same `_engine_names` the snapshot uses, and `check_rules` **joins** through it. The
report keeps naming drops by their REST key, which is what a reader of the report holds.

**Rejected:**
- *Leave `map_asset_pairs` keyed by REST names and translate in the engines instead* — that is
  F3 undone; the whole defect is that four separate places would each have to translate.
- *Re-key the report to v2 symbols* — the report exists to be read beside a raw Kraken response,
  and a dropped pair the reader cannot find in that response is a worse report.
- *Duplicate the name rule inside the script* — two copies of a naming rule is how they drift,
  and `fees.py` already has a third for its own purpose.

**Ownership, stated.** `scripts/` and `clients/kraken/` are A's lane, edited by the lead as
`829e4cc` already did, under the overnight instruction and with no A session running. The change
to `check_rules` is the lead keeping an existing diagnostic **true** under F3, not changing what
it reports — so it is a HOW decision, recorded here rather than left as an OPEN item.

**Second-order finding, recorded not acted on.** Nothing else in `src/` or `scripts/` consumes
`PairRulesSnapshot.pairs` by REST key — checked by grep, not assumed — so this was the only
caller F3 broke.

### D14 — The committed access-control test differs from the gated blob in line endings only

**What happened.** `tests/console/test_access_control.py` was written with CRLF; `.gitattributes`
normalises it to LF on commit, so the blob the gate hashed (`817110fadb2373c3`) is **not** the
blob that is committed. The gate's verdict therefore stands on a file that differs from the
committed one by every line ending.

**Chose.** Record it, and close the phase's work with a **gate on the pushed tree itself** rather
than re-gating the boundary. A gate that copies working-tree files can always differ from the
commit this way; a gate that resets to a pushed commit and copies nothing cannot.

**Rejected.** Calling it immaterial and saying nothing — it is immaterial *here*, because the
tests are line-ending agnostic and both ran green, but the reason it is immaterial has to be
stated rather than assumed. Also rejected: re-gating the same content twice for a whitespace
difference, which buys nothing the closing gate does not.

**Carried forward.** Phase 7 already learned this for generated files and fixed it with an
explicit `newline="\n"` writer. The same rule belongs on hand-written files: write LF.

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
