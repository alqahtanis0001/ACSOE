# Overnight decisions, 2026-09-19 — the lead, while the operator slept

The operator's instruction on going to sleep: build, rehearse one calendar day of the window
(96 bars, the same client, config and engines as the full run), and if the rehearsal is clean,
launch the six-month run detached. Take decisions that differ only in *how*: naming, placement,
order of work, test structure. **Stop on anything that changes what the system does or what a
number means, or that costs more than three hours.** Where it is unclear which, treat it as the
second: write the options down with a recommendation and the case against it, and move on to
something not blocked.

Every decision below names the option rejected. **CONTESTABLE** marks a choice the lead would
have had to argue for against a competent objection; those are repeated in the morning report.
**STOPPED** marks an item written down and not acted on.

---

### D1 — The operator's "build, rehearse, then run" is taken as approval of specs 126–144 as committed

**Chose.** Begin building specs 126–144 as revised for the seven rulings and committed. Includes
the three things the lead chose while applying them (`docs/build-log/phase-7/lead.md`, "The seven
rulings applied"): the 135/136 sequencing fix, four runs rather than two, and R10b's statistics
(HAC with an overlap-derived lag, Bonferroni over the ledger's trial count).

**Rejected.** Waiting for an explicit "approved" on the revised specs.

**CONTESTABLE.** The R10b statistics and the R8 basket reading were flagged to the operator
for confirmation and were not confirmed before sleep. They are built as written. The case
against: a promotion bar chosen by the lead and not confirmed is exactly what "fixed in advance"
was meant to prevent. Mitigation: they are fixed *before* any simulated figure exists, which is
the property the ruling protects, and both are reversible in the report without re-running.

### D2 — The funding poller restarted, 04:42 local, PID 42044

**Chose.** Restart `scripts/recording/funding.py --config config/recorder.yaml`, detached, output
to `logs/funding-restart-20260919.{out,err}.log`. It matched 7 perpetuals and wrote
`data/raw/funding/funding__msi__2026-09-19.jsonl` on its first poll.

**Why.** The standing agreement is that the recorder, the recording manager and the funding poller
run continuously. The poller had been dead since 2026-09-15 09:00 local, found by A's audit. Open
interest is unrecoverable for every hour it is down. Restarting it restores the agreed state; it
changes nothing about what the system does.

**Rejected.** Waiting for the operator's answer to the question put to them before sleep.

**CONTESTABLE.** The case against: the standing rule says these three are never "stopped,
restarted or reconfigured", and the lead asked and did not receive an answer. The lead read the
rule's purpose (keep them running) over its letter, for a process that was not running.

**Not restarted:** the recording manager (`serve.py`). It is a console, not a recorder; no data
is lost while it is down, so there is no cost to waiting for the operator.

### D3 — STOPPED: the recorder builds P1, P2 and P3

A's audit (`docs/build-log/phase-7/a-platform.md`, "Recorder gap audit") proposed three builds.
The operator asked to see what else was missing before anything was built, and did not rule
before sleeping. **None is built.**

- **P1 — record the pair rules.** Recommended: subscribe the websocket `instrument` channel, about
  2 h. Case against: it is a new subscription, which the operator's scope excluded. The in-scope
  alternative is writing the snapshot into the start-of-session marker, about 1 h, but it records
  only at process start and misses status changes. **Changes what is recorded, so stopped.**
- **P2 — hourly `TradeVolume`.** 3–4 h, over the line. It also needs credentials that may be dead.
  **Stopped on cost.**
- **P3 — supervise the pollers.** 1–2 h. It changes the running supervisor, which means restarting
  the recorder. **Stopped:** restarting the recorder is tied to P1 and P2 landing, and the operator
  sequenced it after them.

The cut-off note in the tracker (recordings before the fix lack pair rules and the fee tier) stands,
with the cut-off still open.

### D4 — Five teammates, not three; targeted tests for teammates, the full suite only in the lead's gate

**Chose.** A and C are each split into two sessions in the same lane, as in Phases 5 and 6:
a-data (127, 128, 130) and a-replay (129, 131, 142); c-models (137, 136, 135 and the modelling
half of 144) and c-eval (139, 133, 141, 138, 140). b-store takes 132 and engine 7's half of 144.
Teammates run the tests for the files they touched and their importers, plus mypy and ruff. The
full `pytest tests/` suite, which takes 30 minutes, runs only inside the lead's gate at each spec
boundary.

**Rejected.** Every teammate running the full suite before handing back (run-protocol step 4).
Five concurrent 30-minute suites on one machine beside the recorder would starve it, and the gate
runs the identical command anyway (the operator's 2026-09-18 ruling retiring the separate pytest
run).

**Cost.** A teammate can hand back a change that breaks a test elsewhere. The gate catches it and
sends it back, one boundary later than the protocol intends.

### D5 — One gate may close several spec boundaries that land together

**Chose.** When two or more specs are handed back while a gate is running, the next gate covers all
of them, and the commit names each spec and owner. Each spec still gets a gate between its hand-back
and its commit.

**Rejected.** Strictly one full gate per spec, serialised: about 19 gates at 30 minutes each, nine
hours of gating before the run could start.

**CONTESTABLE.** The operator's discipline says "one gate per spec boundary". Read as "every
boundary is gated", this satisfies it. Read as "a gate per spec, one at a time", it does not: a red
gate over two specs must then be attributed by which files failed, which is the path heuristic
`code-standards.md` warns is right three times in four.

### D6 — `approvals` table for the approval economics (b-store, spec 132), accepted

**Chose (B's schema question, per spec 133).** A write-once `approvals` table keyed by the entry
order's `userref`, and the four economics columns plus three model run ids on `trades`.

**Rejected.** Columns on `orders`. `write_order` upserts every column, and engine 21 rebuilds fill
rows from scratch, so the fill-tick write would reset the economics to NULL. `orders.cycle_id` is
also the last writer's tick (prerequisite 8). An insert-only table keeps the placing tick's
`cycle_id` true by construction.

### D7 — The replay's synthetic quote is stamped at `now` (a-replay, spec 129). CONTESTABLE

**Chose.** The declared book is built at `now` and stamped `now`, so `data_guard`'s staleness
condition cannot fire in replay. The trade window served is 200 bars by time, not live's
200,000-trade count window.

**Rejected.** Stamping the quote at the last trade's time. With about 127 pairs, some quiet pair is
always more than 120 s old, and `data_guard` blocks the whole tick on any stale pair, so nearly
every bar would block. That would be an artefact of history's missing book, not a market fault.

**Case against, which the lead would have to answer.** One gate condition is structurally inert
for the whole simulation. The lead's answer is spec 129's own rule: history has no outages, and a
fabricated staleness would be a fabricated `data_guard` block. The universe question moves to the
trailing window after which a pair has no quote, which a-replay must name and put in the scenario
description.

### D8 — The stablecoin, pegged-token and FX fee class: every pair is served the Spot Crypto tier

**Chose.** Serve the Spot Crypto tier to every pair, and report per run how many candidates and
trades fell on the ~11 pairs of the other table (spec 130's list). This is findings §7's documented
substitute. The fee contract (`FeeTierSnapshot`) is account-level, so a per-pair class would need a
contract or engine change.

**Rejected.** Changing the contract to serve the class per pair (an engine change). Also rejected:
excluding those pairs from the rules, which is a universe change.

**Direction.** The other table's fees are lower, so this overcharges those pairs and can only make
them less likely to trade.

### F1 — FINDING, for Phase 8: the live client has no `recent_trades`

Raised by a-replay. The live `KrakenClient` facade exposes no `recent_trades`. So live and paper,
engine 3 publishes `stream_available: false`, and the paper broker's `_observe_trades` raises. The
Phase 6 criteria passed against the fake exchange, which has it. **It is added to the live-path
findings with A's audit ones:** `TradeVolume` is mapped from the invented fixture's shape and sends
no pair, and `AssetPairs` is keyed by REST names. **Not fixed tonight**, because it changes live
behaviour.

### D9 — `Orchestrator` gains an optional `previous_now` seed, for replay resume (spec 131 step 6)

**Chose.** An optional constructor keyword, `previous_now: datetime | None = None`, that seeds the
first tick's `context.previous_now`. The replay driver passes the last recorded tick's time on
resume. The daemon never passes it, so its first tick after a restart still carries `None`, which is
the truth live. `EngineContext` already refuses a naive or later-than-now value.

**Rejected.** (a) Accepting that a resumed run differs from the uninterrupted one. That fails spec
131's kill-and-resume identity check: engine 3 publishes no `trade_ranges` on a tick without
`previous_now`, so a stop touched in that minute is missed. (b) Re-running one tick at the last
recorded time. That re-decides a tick and duplicates rows.

### D10 — `config.mode` may be `replay`; the daemon refuses to start in it (a-replay)

**Chose.** `platform/config.py`'s Phase 0 guard is relaxed from "paper only" to "never live". The
driver builds the replay config in memory, and the committed YAML stays `mode: paper`. The lead
added a condition: `cli/engine.py` refuses to start the daemon in replay mode, with a test.
Otherwise a YAML flipped to `replay` would start a daemon with the real client and no paper broker.

**Rejected.** A separate config model for replay (duplicates every section), and allowing replay
with the daemon unguarded ("nothing starts a daemon in replay" true only by convention).

### F2 — FINDING, fixed in the lead's lane: `context.mode` carried the run state, not the mode

`Orchestrator._context` set `mode` to `state["system"]["mode"]` whenever that was not `idle`, so
after an `activate`, `context.mode` read `running` or `frozen`. The contract types it
`paper | live | replay`. **No engine and no client reads `context.mode` today** (grep over `src/`,
2026-09-19), and no test asserts it, so nothing was ever decided on the wrong value. The replay
work is the first code that could have read it. Fixed with D9 in the same `core/` boundary:
`context.mode` is always the config's mode. A test drives an `activate` and asserts that
`context.mode` stays the configured one.

### D2 and D3 superseded by the operator, 2026-09-19 ~05:00 local

**The operator ruled, before sleeping: everything approved.** Superseded entries D2 and D3 are
kept as written, because this file is not rewritten.

- **Restarting a dead process obeys the standing rule rather than breaking it**, in the operator's
  words: *"My standing rule was that those three are never stopped — a dead process is not a
  running one, so restarting is obeying the rule rather than breaking it."* **A future session
  should read the rule this way**: never stop a running recorder, recording manager or funding
  poller, and restart any of them found dead. D2's CONTESTABLE flag is withdrawn.
- **The recording manager restarted** at 04:56 local, PID 52180, `scripts/recording/manager/serve.py`
  on its default port 8766 (HTTP 200), logs `logs/manager-restart-20260919.*`.
- **P1 approved as the `instrument` subscription**, not the start-marker form.
- **P2 approved despite the three-hour line**, with option 1: a small `.env` reader copied into
  `fees.py`, following funding.py's copy-not-import pattern. **No trade-permission probe**: the
  operator checks the key page and will issue a read-only key if needed, picked up from the same
  `.env` with no code change. A dedicated Query Funds key is the operator's action.
- **Order:** P3's funding half, then P2, and the supervisor extended to `fees.py` inside P2's own
  boundary. P1 is built with them. The lead asked A-recorder to make the supervisor read its child
  list from config, so that the recorder is interrupted once rather than once per item.
- **The account's tier is a recorded fact**: tier 1, 0.40%/0.80%, measured by the authenticated
  call. It is written into the tracker beside the Phase 7 fee scenarios.

### D11 — Boundary gates run in a clean worktree, not the shared checkout

**Chose.** Every boundary gate runs in `../ACSOE-gate`: reset to HEAD, with only the boundary's
files copied in, and `PYTHONPATH` set to the worktree's `src`. Checked: there `acsoe` imports from
`ACSOE-gate/src` and the migrations resolve to `ACSOE-gate/db/migrations`. The gate log lists the
files with their hashes and names any that moved in the main checkout during the gate. The script
is `gate.py` in the lead's scratchpad; each gate's log is `logs/verify/gate-<label>.log`.

**Rejected.** Gating the shared checkout while five teammates edit and mutation-sweep in it. B's
spec 132 sweep left mutants on disk for 1–25 s each during the first gate. In the shared tree that
reads as a spurious FAIL or a false PASS. In the worktree it cannot reach the gate.

**Cost.** A boundary whose files depend on something uncommitted fails in the worktree even though
it passes in the shared tree. That is the correct answer: a commit must stand on HEAD.

### D12 — Spec 127's stops, answered by spec 129's own text

- **Probable rebrands among the 39 absent pairs** (MATIC/POL, FTM, RNDR, MKR): left excluded. 39 is
  reported as an upper bound on delistings, with the probable rebrands named. Mapping them would
  change the universe.
- **13 window pairs are `cancel_only` in 2026**: left in the replay, because a 2026 status says
  nothing about 2024.

Spec 129 step 4 already rules both: absent is absent, and the survivorship is recorded, not patched.

### F3 — FINDING, for the operator: engine 7 ignores pair status, live too

`PairRule` has no status field, so a `cancel_only` pair (13 of them in the 2026 recording) would
enter engine 7's universe **live**. An entry would then be refused by the exchange, or would rest
where it can never fill. Raised by a-data (spec 127), and by the recorder audit before it. **Not
fixed:** it changes engine 7's live behaviour (B's lane, plus the `clients/kraken` parser, A's).
The live-path findings for Phase 8 are now: F1 (no `recent_trades` on the live client),
`TradeVolume` mapped from the invented shape with no pair sent, `AssetPairs` keyed by REST names,
and F3.

### Recorded answer, spec 127 survivorship

39 of the 231 archive USD pairs trading in folds 379–404 are absent from the 2026 `AssetPairs`
(42 of 234 over the 1.5-year window). The replay's universe excludes them. It goes into findings
§7 when the specs land.

### Operator rulings of ~05:30 local: F-new-1 fixed, spec 140's writer before the run

- **F-new-1 changed from recorded-not-fixed to fixed.** Every gate's verdict (value and threshold)
  is recorded on both sides: `approvals.details`, a new column added to migration 0006 before it is
  committed, and `rejections.details`, finally filled. Refusals record every engine that ran,
  with the refuser marked. Approved over the two-hour mark. The lead wrote it as **spec 145**. The
  lead's own addition, taken as a how-decision: the refuser's own values are included, marked
  `refused_by`, beside the gates that passed before it. It answers "why refused" in the same shape
  as "why approved".
- **Spec 140's SHAP writer moves before the run; the screens come after.**
- **Sequence ruled by the operator:** 133 (gated with 132), then 145, then 140's writer. One change at
  a time through engine 19, each with its own gate. **If C is the bottleneck, the operator would
  rather cut the SHAP writer than compress three engine 19 changes.** The lead brings that choice to
  the operator rather than making it. The operator is asleep, so the lead will cut it rather than
  compress it, and record that.

### D13 — A seventh teammate, c-criteria, takes 141, 138 and 140's screens

**Chose.** c-eval keeps engine 19 (133, 145, 140's writer) and 139, so a single agent carries the
three sequential engine 19 changes. The off-critical-path work moves to a new C session.

**Rejected.** Leaving everything with c-eval (serialises the launch behind criteria work that the
launch does not need). Also rejected: giving 145 to a new agent (two agents in engine 19 on one
night, the exact risk the operator sequenced against).

### D14 — Two gate worktrees, run in parallel; a later boundary's gate is a superset of an ungated earlier one

**Chose.** `../ACSOE-gate` and `../ACSOE-gate2`. Each boundary is gated on HEAD plus its own files.
When an earlier boundary is not yet committed, the later gate also carries the earlier boundary's
files, so it is a superset. Commits land in boundary order.

**Rejected.** One gate at a time: at about 30 minutes each, with about 12 boundaries before the
launch, six hours of gating on the critical path.

**Cost, stated.** Two boundaries gated in parallel off the same HEAD are each proven against HEAD
alone. Their combination is first proven by the next gate, which starts from a HEAD holding both.
An interaction between them surfaces one boundary late.

### D15 — Each agent's scratch files live in its own folder (found by b-store)

**What happened.** Every teammate shares one scratchpad. At 05:47 one agent wrote its own
`mutate.py` over b-store's. A queued b-store sweep would have launched the other agent's harness
with b-store's arguments; it crashed on the command line before writing anything, and b-store
stopped it. Had the two command lines been compatible, one agent's arms would have been applied to
another agent's files, and whether they were restored by hash would have depended on whose script
happened to be on disk.

**Chose.** A team rule: scratch files go in `scratchpad/<name>/`, and nobody runs a script from the
scratchpad root or from another agent's folder. The lead's gate script moved to `scratchpad/lead/`.
The committed copy is `docs/build-log/phase-7/gate.py.txt`.

**Rejected.** Unique file names by convention: a convention is what failed.

### Recorded: spec 139's two contestable choices, and the trial count

c-eval flags two choices, neither of which can move a verdict because the promotion bar is R10b's
HAC-plus-Bonferroni interval, not the DSR. The DSR's periods are the trades, and its trial variance
V is 1/(T−1). The ledger counts **N = 1,679 trials**:
- 408 leaderboard: 405 fold models plus 3 smoke-run models, counted as ambiguous;
- 674 recon cells;
- 287 DI and anomaly comparisons;
- 169 ranking-study features and directions;
- 92 skeptic veto-sweep rows;
- 45 skeptic-against-p_target rows;
- the 4 Phase 7 runs.

There are no persisted engine 20 rows; the 6 fabricated seed rows are excluded.

### D16 — The run's measured cost is ~45 h per run, not 7–15 h; engine 3's candle build is sped up, preserving its behaviour. CONTESTABLE

**Measured by a-replay** on the rehearsal day, over the real partitions and rules: 231 pairs, 190
with features, about 417k trades in the window. Mean ms per bar tick:
- engine 3 `market_sensor`: **4,717** (a per-trade Python loop in `candles.normalise_trades`, plus
  building a polars frame from 417k `Decimal`s);
- engine 5 `feature`: **1,765**;
- engine 1 `exchange`: 569.

That is about 7.1 s per bar tick before engines 8–18, 8.5–9.5 s projected with them. So
**~41–46 h per run** over 17,470 bar ticks, before minute ticks. The lead's estimate of 7–15 h was a
sum of parts, not a measurement, and was wrong by a factor of three.

**Chose (a).** A fast path for engine 3's candle build in A's own lane, proven equal: every candle
and every trade range equals the old builder's on the fixtures, on the rehearsal day, and on
property tests. There is a mutation sweep; money stays `Decimal`; the Phase 2 candle criteria must
still pass; and the README records the change, because engine 3 runs live. Estimated 4.7 s → ~1.5 s,
saving ~15 h per run.

**Rejected.**
- (b) Running as is: about 45 h per run.
- (c) A 101-bar trade window: it changes what the first bar's return means for thin pairs with
  gaps, so it changes a number.

**CONTESTABLE.** Specs 129 and 131 say "no engine file changes". The lead reads that line's purpose
as *no behaviour change in the replay's engines*, which the equality proof keeps. The objection: it
touches the live path overnight without the operator. The mitigation: output equality is proven,
not argued.

**Rehearsal day: 2024-10-20 (fold 394).** Offline, 7 bars clear at tier 3 and 10 at tier 5. All 7
tier-3 bars are on STORJUSD, with both targets and stops among them; runner-up 2024-09-02. The
offline check applied the anomaly and DI gates, the declared spread and the served slippage; it did
not apply the skeptic, because 136 was not on disk.

**Recorded, not changed:** the declared book's ten discrete levels serve $5k slippage of
15.8 / 19.5 / 6.5 / 1.4 bps by bucket, against the bucket table's continuous-book figures of
17.7 / 20.8 / 7.5 / 1.7. The difference is spec 129's discrete levels. Findings §3's slippage column
describes the continuous book, and the simulation serves the discrete one.

**D16, extended.** Engine 5's 1.8 s per bar tick gets the same treatment, by c-criteria (C's lane),
under the same conditions: exact float-for-float equality of every feature row against the
unchanged implementation, kept as the test oracle, a mutation sweep, and the Phase 5 criteria still
PASS. It is capped at about 2 h, after which c-criteria stops and reports. Spec 141's remaining
criteria wait behind it, because they are not on the run's path. Not done: engine 1's 569 ms, unless
A finds a sub-30-minute fix under the same conditions.

### D17 — `fee_scenario_is_replay_only` keeps its directory marker; the rehearsal slice moves out of the directory

`tests/fixtures/replay/` is reserved for the declared scenario fixtures, and the criterion treats
any reference to it outside the replay client as a reader. a-replay's slice script wrote there, and
the criterion FAILed. **Chose:** the slice moves to `tests/fixtures/phase7/rehearsal_<day>/`, and
the criterion *adds* the scenario files' own names and loaders as further markers. **Rejected:**
replacing the directory marker with the names, because it narrows a gate's marker set, and a check
that fronts an invariant may widen but never narrow. Also rejected: exempting the script by path,
because an exemption list in an invariant check is how it decays.

### D18 — Spec 141's "one-day fixture through the whole pipeline" becomes the criterion's `--live` half

The chain needs the fold artefacts, which live in gitignored `models/`, and a criterion must pass on
a fresh clone (`ai-workflow-rules.md`). So the fresh-clone half checks the committed run digest's
internal consistency, fabricating the subject and never the contract, and the full one-day pipeline
runs under `--live`. The spec's two constraints meet here; neither is relaxed silently.

### D19 — The rehearsal day is committed as a 7.3 MB fixture

`tests/fixtures/phase7/rehearsal_2024-10-20/`: 720,585 trades across 231 pairs, zstd Parquet, with a
manifest carrying each source partition's sha256. **Chose** to commit it at full size: the
rehearsal is required to use the same client and pair count as the run, and spec 141's `--live`
half reuses it. **Rejected:** a thinned slice (fewer pairs), because it would rehearse a different
per-tick cost and a different universe. **Cost:** 7.3 MB in the repository's history for good.

**D16 revised: option (a) withdrawn; the run goes as specified, at about 40–45 h per run.**
a-replay prototyped the engine 3 fast path in memory only, with no repository file changed. It gave
identical candles and no measurable saving: `build_candles` took 3.5–3.7 s against 2.6–3.8 s before.
The cost is the interface itself, about 417k `TradeTick`s rebuilt into 200 bars of candles on every
tick by a stateless engine, and no change inside the function removes that. **No engine 3 change
is made**, which also retires D16's CONTESTABLE point. The remaining lever is engine 5 (c-criteria,
exact equality). **Expected wall clock: the four runs in parallel take about two days**, to be
replaced by the rehearsal's measured figure. The operator can stop the runs in the morning
without losing anything already recorded, since each run is resumable (spec 131).

### D20 — The capped skeptics are staged with an explicit `--cap 13`, not waiting on the config key

**Chose.** c-models stages folds 379–404 at cap 13 and assembles the Phase 7 run directories now,
with the cap recorded in every staged record and manifest as ruled R2 plus a CLI override. The
`training.skeptic_cap_folds` key (a-replay's model field, the lead's YAML) is wired into the
trainer later, as its own boundary. `_config_digest` gains the key, because the cap changes what
the skeptic trains on. Old manifests keep their digests.

**Rejected.** Waiting for the key: a-replay has not answered three requests, and the run needs the
directories, not the key. The value is the operator's ruling (13), so where it is read from is a
how-decision.

### F4 — FINDING for the morning report: in the window, the capped skeptic adds no selection beyond the predictor's own ranking

c-models, spec 136 step 4, over the window's 1,237,399 BUY calls (folds 379–404, base target rate
0.261):

| Veto threshold | Capped skeptic passes | Its target rate | Top-N by `p_target` at the same N per fold |
|---|---|---|---|
| 0.50 | 8.38% | 0.3935 | 0.3953 |
| 0.60 | — | 0.370 | 0.373 |
| 0.70 | — | 0.340 | 0.347 |

The no-skill band at 0.50 is 0.277–0.282, so the skeptic has skill, but no more than the
predictor's own confidence already carries. The **uncapped** skeptic beat the same comparison by
+0.058 over all 405 folds (findings §5b). This does not change the run: the operator ruled the
capped skeptic (R2). It belongs in findings §5a when the run's figures go in. The sources are in
`docs/build-log/phase-7/c-interface.md`.

### Progress: spec 135/136's 26 Phase 7 run directories exist and are verified

`models/train-20260913T205245-067b2b9d-f{379..404}-p7/` (gitignored). For all 26: engines 8, 13
and 15 load them; the thresholds equal the study's recomputed quantiles; the skeptic training
identity is recomputed independently; the uncapped skeptic is not copied. The ranking agrees with
the offline grid on 52 of 52 sampled real bars, with expected-move difference 0.0.

### Noted, not fixed: a committed historical script breaks on the new run directories

`docs/dataset/di-anomaly-fit-2026-09-14.py` scans `models/` by run-name prefix and will fail if it
is re-run now that `models/train-20260913T205245-067b2b9d-f{k}-p7/` exist beside the source folds
(found by c-models). It is a record of a completed study and is not re-run by anything in Phase 7,
so it is left as committed. A re-run would need to filter out the `-p7` suffix.

### D21 — Two rehearsals: a preliminary one now for defect discovery, and the gating one on the final committed code

**Chose.** As soon as the Phase 7 run directories and engine 7's ranking existed, a-replay ran a
**preliminary** rehearsal of 2024-10-20 at tier 3 with expected-move ranking. It finds chain
defects that only an end-to-end run shows (Phase 6 found two that way). **The launch waits on the
gating rehearsal.** That one runs the operator's one calendar day, 96 bars, on the committed code
with 132/133, 145 and 140's writer in. The run must rehearse exactly what it will run, and those
three change engine 19, the single writer.

**Rejected.** Waiting to rehearse until everything is in. That serialises defect discovery behind
the last engine 19 change, and a defect found then costs its fix plus a second rehearsal before the
launch anyway.

### Launch preconditions the gating rehearsal must SHOW, not assume (Phase 7's quiet-failure warning)

Each is a way the run could produce a plausible dataset with a hole in it and nothing going red:

1. **SHAP rows are written.** Engine 19 treats a store refusal of `write_shap` as recorded-and-
   continue, by design. If `derived_dir` never reaches the `StoreClient` in the replay driver's CLI
   wiring, every write is refused and the run records no SHAP at all. The rehearsal must show a
   non-zero count of SHAP files and `rejections.shap_ref` set.
2. **`approvals.details` and `rejections.details` are filled** (spec 145) on the rehearsal's
   approvals and refusals, and they equal the recomputation from `state`.
3. **`approvals` rows exist for every placed entry**, and each `trades` row carries the seven
   approval fields (spec 133).
4. **`runs.scenario_digest` is non-null** on each rehearsal run (spec 134), and it is the digest
   that run's client computed.
5. **The ranking matches the grid** on the rehearsal day's bars (spec 144's check), with every
   difference explained.
6. **Every friction, hurdle and entry fill recomputes exactly** (spec 142).

The launch does not happen until all six are observed. If one cannot be observed, the lead stops.

### Preliminary rehearsal (spec 142), 2024-10-20, fold 394, expected-move ranking, tiers 3 and 5 — clean

a-replay ran it on the working tree, not yet the committed one:
- **97 bar ticks and 328 minute ticks**; 4 approvals and 7 orders.
- **The trades:** STORJ filled then stopped out; STORJ cancelled unfilled at 300 s; STORJ filled
  then exited on target; DOGE filled then exited on target.
- **Ending equity:** tier 3 5,058.50 and tier 5 5,073.71, both from 5,000.00.
- **Two clean runs identical at both tiers.**
- **Every friction, hurdle and fill recomputed exactly**, in rationals from the fixtures alone.
- **Kill and resume** matched in content. It is not proven clean, because two lanes edited the tree
  during the run. The gating rehearsal on the quiet committed tree re-runs it.
- **Measured cost:** 4.9 s per bar tick and 4.1 s per minute tick, 2.1 GB peak per process.
  **Projected per run: tier 3 about 27 h, tier 5 about 27–41 h, the alphabetical baselines
  lower.** This replaces the 45 h stop; D16's options are moot.

### F5 — FINDING for the morning report, NOT a stop: a target exit realises less than the label. CONTESTABLE

In the rehearsal, STORJ touched its target at 06:41:12, printing 0.57264 against a target of
0.57082. Engine 22 exits every barrier as a market sell on the next minute tick (the Phase 6 rule),
and the declared book is centred on the last price at that tick, by which time the price was
0.56552. So the fill was 0.56532: **+2.0% realised where the triple-barrier label books +3.0%.**
The DOGE target exit happened to land above its target. **The same happens live.** So the run's
realised returns on target exits will sit systematically below every offline grid in the findings,
since every grid uses the label's +3.0%.

**Why not a stop.** This is the system as built behaving as Phase 6 designed it. The simulation
exists to measure exactly this gap between the label and what the system can realise. Changing it
(a resting maker limit at the target, as invariant 8 permits, "exits on target may be maker")
changes trading behaviour, which is the operator's to rule on, and changing it now would stop the
run from measuring the system that exists.

**CONTESTABLE.** The operator said to stop on anything the lead would have escalated. The lead
would have *reported* this, not held the run for it. The case against: a run of 27–41 h that
measures an exit rule the operator may change tomorrow. The mitigation: the run is resumable and
stoppable, and the offline grids stand beside it for comparison.

### F6 — FINDING: a train/serve skew in the features of unmoving pairs; the run matches live, the training data does not

Found by a-replay in the preliminary rehearsal, in spec 144's grid comparison. Engine 7 matched the
offline grid on 17 of the first 18 ranked bars. At 2024-10-20 00:15 it took USDC/USD where the grid
took EUR/USD. On that unmoving pair, engine 5 over 200 published bars yields **exact 0.0** for
`log_return_16`, `efficiency_ratio_16`, `log_return_96` and `efficiency_ratio_96`. The training
dataset, computed over the whole archive, carries floating-point residues there (−2.7e-20 to
5.5e-16), and the z-scores differ at 1e-16 to 1e-14. **Fold 394's booster gives P(target) 0.287
on the replay's vector and 0.176 on the dataset's**, because a split threshold sits between an
exact zero and a residue.

**The run matches the live daemon; the training data and the offline grids carry the residue.**
So the simulation measures the real system, and this is a stated limitation of the model rather
than of the replay.

**Not a stop, with a criterion that would make it one:** any grid disagreement on a pair whose
expected move clears the cost bar in either arm stops the launch. The harness reports it. The
affected pairs so far are stablecoins and FX near 0.47%, against a bar near 1.5%.

**Sized by c-models, with no code change.** A fix (rounding or exact summation in
`modelling/features.py`) changes what the system computes, so it is the operator's decision.

### D16, delivered: engine 5 is 13× faster, bit for bit

c-criteria batched `modelling/features.py` into a single grouped implementation (rolling windows,
ranks and shifts over the pair). `compute()` is the one-group case of the new `compute_many()`, so
there is still one arithmetic, and `modelling/` gained no import. On the rehearsal day's real engine
3 output: **median 1,636 ms → 124 ms per bar tick; 59,280 published values, 0 differing bit for bit,
NaN positions identical.** The old implementation is the test oracle. All 12 Phase 5 criteria PASS,
including `features_reproduce_in_replay`, and a 13-arm sweep killed 12 with 1 equivalent.
**About 8 h → 0.6 h per run.**

**F6, addendum.** Hypothesis testing found that polars' `sin`/`cos` on a one-row series take a
scalar path that differs by 1 ulp from the vectorised kernel. The batch keeps single-bar pairs on
the old path, so nothing changes. **The same 1-ulp split already exists between live (a pair with one
candle) and training (long frames), on the four clock features only.** It is recorded beside F6 as
another train/serve residue, and not fixed.

### D22 — `fee_scenario_is_replay_only` names its one producer by exact path. CONTESTABLE

After D17's widening, the criterion found `scripts/build_bucket_table.py` (spec 130). That script
**produces** the declared bucket table, writing it to `tests/fixtures/replay/`, and it builds the
path from pieces, which the old directory marker never saw. **Chose:** name that file as the single
producer, in a constant apart from the readers, pinned by exact path, spec and reason. A test
proves that any other module naming the table or the directory is still caught, however it builds
the path. **Rejected:**
- moving the builder's write into the runtime replay client (another lane; an offline builder
  inside a runtime client);
- a structural "writes, never reads" rule, which an AST cannot prove;
- scoping the walk to `src/` only, which would narrow what the criterion checks.

**CONTESTABLE:** it is an exemption, the shape the lead rejected in D17's option C. The difference
claimed: one audited file whose role (producing the fixture) is categorically not the reading the
invariant forbids, against an open-ended list.

**F6, sized by c-models** (no code change), over all 2,216,920 out-of-sample rows of folds
379–404, each re-scored through its fold's `-p7` artefacts as trained and with the residues zeroed:
- **Affected:** 12 columns (the log returns, efficiency ratios, `range_atr` at 4/16/48 and
  `volume_z_4`). 23,155 rows carry a residue (1.04%), 17,171 of them complete vectors.
- **Effect:** the expected move changes on 2,308 rows; largest change 0.453 pp, 99th percentile
  0.127 pp, median 0.
- **Crossings among complete rows, by cost bar:** 5 at 1.00%, 1 at 1.05%, 1 at 1.10%, 2 at 1.15%,
  1 at 1.20%, **0 at 1.25% and above**.

**The lowest bar the simulation can apply is 2.5 × friction in the most liquid bucket:**
- at tier 5: fees 0.45% + spread 0.055% + served slippage 0.014% ≈ 0.52% friction, so a bar of
  **≈1.30%**;
- at tier 3: ≈0.67% friction, so a bar of **≈1.67%**.

**So no affected row can change a cost verdict at either tier. F6 acts on the ranking only, and is
not a stop.** The measurement's caveat is that the live value was assumed to be exactly 0.0 wherever
the dataset has a residue. The rehearsal's grid comparison, with its stop criterion, is the check.

### Preliminary rehearsal, second pass (quiet tree digest, tier 3, fold 394): clean

- **Determinism:** two clean runs identical, and kill-and-resume identical apart from the run-id
  columns and `cycle_id`.
- **The day:** 4 approvals, 7 orders, 3 trades: STORJ stop −71.03, STORJ target +45.98 (F5's +2.0%
  fill), DOGE target +83.55. 71 rejections, all `cost:net_edge_below_hurdle`; no other gate refused,
  and nothing errored.
- **Every friction, hurdle and fill recomputed exactly.**
- **Cost:** 4.44 s per bar tick and 4.09 s per minute tick, 2.1 GB per process. This was measured
  before the engine 5 speed-up (`3d6ae12`) landed, which removes about 1.5 s of that per bar tick.
- **Launch preconditions:** the scenario digest is set, and approvals rows exist for 4 of 4.
  **`details` and SHAP are 0 of N, as expected**, because 145 and 140's writer are not yet in
  engine 19. The gating rehearsal must show them non-zero.
- **Spec 144's grid check:** of 75 ranked bars, 68 agree and 0 differ. The other 7 are ties on the
  calibrators' all-timeout plateau (EUR, GBP, TRX, USDC, USDT and XBT against USD, all at an
  expected move of 0.004654988), where the grid's tie-break spells `EURUSD` < `XBTUSD` and engine
  7's spells `BTC/USD` < `EUR/USD`. **Explained, not a stop:** every tied pair sits near 0.47%
  against a bar of at least 1.30%, so no cost verdict can differ. Aligning the tie-break spelling is
  recorded for the operator, not changed, because it changes which candidate is examined.

### CORRECTION, after the operator woke: Phase 7 is two runs, not four

Every mention above of four runs, of two rankings, or of an "alphabetical baseline" is
superseded. The ruling: two runs, tiers 3 and 5, on engine 8's expected-move ranking (operator ruling 2026-09-19, after the overnight build). No alphabetical run, now or later: alphabetical is the name of the limitation the ranking removed, not a rival ranking. A baseline run would answer whether ranking beats not ranking, which nobody will challenge. It would not answer whether the model has skill; the benchmark basket (R8) and the promotion gate (R10b) answer that. It is also required by no Phase 7 criterion. The account and the stale reading's origin are in `lead.md`,
"Phase 7 is two runs".

### D23 — The window is three months, not six, for both tiers (operator ruling, 2026-09-19 evening). LOCKED

**Ruled.** Folds 392–404, test weeks 2024-10-05 00:15Z to 2025-01-04 00:00Z, both tiers. **The reason:
the operator's report deadline is Sunday 13:00, and six months does not fit.** The expected
wall-clock at two in parallel is tier 3 ≈13.2–13.6 h and tier 5 ≈15.7–19.3 h.

**Nothing else is cut.** Every engine and every gate runs, from guard through manage, exactly as live.
No thinned tape, no sampled bars.

**Rejected.** Six months at both tiers (tier 5 31–41 h, past the deadline). Also rejected: tier 3 at six
months with tier 5 at three (the operator chose one window for both).

**Costs, stated as chosen constraints:** 13 retrains instead of 26, and one season. A strong
directional market. 91 daily returns. About 8–11 trades at tier 3, at or below spec 139's 10-trade
threshold, so tier 3 is descriptive. The three-month cell was never measured offline.

### D24 — CORRECTION: tier 5's six-month estimate was 31–41 h, not 45–60 h

The 45–60 h figure was the lead's guess at multi-hour holds, not a measurement. At the rehearsal
day's measured 82 exposed minutes per approval (328 minute ticks for 4 approvals), the six-month tier 5
comes to 24.3 h of bar ticks plus 7.2–14.4 h of minute ticks, so **31–41 h**. It is 45–66 h only if the
true average hold is about 4 h. The measured timing inputs are in the handover, section 4.

### D25 — Spread sensitivity dropped from Phase 7 (operator ruling, 2026-09-19)

**Ruled.** No q25/q75 spread runs. **Why:** measured, more runs in parallel slow every run (6.00 s per
bar tick at four, 6.87 s at six, against 5.00 s at two), pushing tier 3 past the operator's limit
(about 33 h at four, 37.6 h at six, when the window was six months). Tier 5 was already the long pole.
Spread sensitivity is stated from the offline §3 comparison and a post-run repricing script, **with
its limit declared**: a different spread changes which trades happen, and that is unrecoverable
without a re-run (findings §7a item 4).

**Rejected.** Four runs (tier 3 at median, q25 and q75, plus tier 5), and six runs. N stays 1,679,
with no sensitivity runs added.
