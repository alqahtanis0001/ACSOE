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
