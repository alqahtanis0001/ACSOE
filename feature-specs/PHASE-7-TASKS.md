# Phase 7 — shared task list

## HANDOFF 1 — LIVE STATE, 2026-09-19 overnight (the lead updates this block at every boundary)

**The operator is asleep. The instruction: build, rehearse one calendar day of the window (96 bars,
same client, config and engines as the full run), then launch the six-month run detached.** If
the rehearsal shows anything the operator would want escalated, stop, write it down, and do not
launch. Take how-decisions; stop on anything that changes what the system does or what a number
means, or costs more than 3 h. **Every decision is logged in
`docs/build-log/phase-7/overnight-decisions-2026-09-19.md`, and the morning report reads it in
order.** Morning report order: the decision list, the run's status and progress, the recorder audit,
and anything stopped.

**If you are a fresh session after a lost connection: do not restart anything that is running.**
Check first, then resume from here:
- **Recording: SWITCHED OVER 2026-09-19 05:08:44Z** to the committed supervisor. It supervises
  `record.py` (P1 `instrument`), `funding.py` and `fees.py` (P2), all started by `master.bat` in
  its own console. PIDs at switchover: cmd 54168, supervisor 43264/40848, record.py 46220/46912,
  funding 18684/39376, fees 28860/34472. The recording manager (`serve.py`, port 8766) is PID
  52180. The supervisor restarts its own children; a whole-supervisor death needs `master.bat`. **A dead one of these is restarted, never a live one** (operator's
  reading of the standing rule).
- **The run, once launched:** two detached processes (tiers 3 and 5, expected move). The launch
  command, PIDs, logs and expected finish are written HERE when launched.
- **Gates** run in clean worktrees, `../ACSOE-gate` and `../ACSOE-gate2`, through `gate.py` (the
  lead's scratchpad; its logic is in D11). Logs: `logs/verify/gate-<label>.log`.

**Pushed state:** `04bc511` on origin/main (11:05 local). **Everything is committed except spec 145
and 140's SHAP writer**, both c-eval's in engine 19, in that order, each gated alone (operator
ruling). The boundaries so far: b1, b2, b3, b4 (red once), b5 (red once), b8 (engine 5 13× faster),
and b67 (132, 133, 134, 138, 141, 129, 131, 142, config; b6 red once). The Phase 7 criteria on the
committed tree: 4 PASS, 2 PENDING (the run's digest, and the SHAP writer).

**The path to launch:**
1. c-eval's 145 → its gate → commit.
2. c-eval's 140 writer → its gate → commit.
3. **The gating rehearsal** (a-replay):
   `python scripts/rehearse_replay_day.py --day 2024-10-20 --fixture tests/fixtures/phase7/rehearsal_2024-10-20 --out <dir> --tier 3 --fold 394`
   on the committed tree, about 1.6 h. It must SHOW the six launch preconditions (overnight log),
   `tree_unchanged`, and `ranking_stop` false.
4. **Launch:** four detached runs, `acsoe research backtest --db data/db/<name>.sqlite --ranking
   {expected_move|alphabetical} --fee-tier {3|5}`, from a detached worktree at the launch commit,
   through WMI (the Phase 5 pattern), each verified alive. Expected about 22–28 h per run after the
   engine 5 speed-up.

**The preliminary rehearsal is clean** (two passes; overnight log). Findings F4 (the capped skeptic
adds no selection beyond p_target), F5 (a target exit realises +2.0% against the label's +3.0%) and
F6 (the flat-pair feature residue, ranking-only) are recorded; none is a stop.

**Teammates (background agents in the lead's session; a fresh session has none, so re-spawn from
the team brief):**
- a-data: 127, 128, 130. Done.
- a-replay: 129, 131, 142, and the config fields.
- b-store: 132 and engine 7's half of 144.
- c-models: 137 and the modelling half of 144 (done); 136, then 135.
- c-eval: 139 (done); 133 (done); next 145, then 140's writer.
- c-criteria: 141, 138, and 140's screens (after the run).
- a-recorder: P1, P2 and P3 (built). The switchover waits on the lead's word.

**The team brief is committed at `docs/build-log/phase-7/team-brief.md`**: give it to any
re-spawned teammate. **The gate script is committed at `docs/build-log/phase-7/gate.py.txt`**:
copy it to a scratch location, and run it as `python gate.py <label> 7 <files...>`, with
`ACSOE_GATE_TREE=ACSOE-gate2` to select the second worktree.

**Operator rulings of the night that are not yet in the authority files:**
- P1, P2 and P3 approved.
- F-new-1 fixed (spec 145), before the run.
- 140's writer before the run.
- If C is the bottleneck, cut the SHAP writer rather than compress engine 19's three changes.
- The account's tier-1 fees were measured and recorded (tracker).

## HANDOFF 0, 2026-09-19 — specs written, every ruling answered, AWAITING OPERATOR APPROVAL TO BUILD. Nothing is claimed or built.

**Read this first.** Specs 126 to 144 were written by the lead from the Phase 7 row, the nine Phase 7
prerequisites, and the operator's rulings of 2026-09-19. They were revised twice the same day: first
for the second round of rulings (ranking, tiers, fee source, promotion bar), then for the last seven
(R2, R4, R8, R9, R10b, R11, R12). The findings document was revised with them (§R). The evidence
behind every choice is `docs/dataset/phase-7-findings.md` and the reconnaissance beside it. **No
teammate starts until the operator approves these specs.**

**The operator rules on the phase close after seeing the simulation's output, as in Phase 6.** The
lead does not close the phase and does not mark it green.

### Every ruling (2026-09-19), written into the documents by spec 126

- **Fees:** invariant 2 is amended to permit a declared fee scenario **in replay mode only**,
  enforced by a test.
- **Pair rules:** a genuine `AssetPairs` is recorded and committed with its URL and date. That
  also closes prerequisite 9.
- **DI and anomaly thresholds:** rebuilt from the Phase 5 study into new run directories, not
  refitted.
- **Spread:** declared, not modelled. The four-bucket table keyed on trailing 24-hour dollar volume
  is applied to every pair, recorded or not, with the interquartile ranges published as declared
  uncertainty (`phase-7-findings.md` §3).
- **The book:** a synthetic book served by a replay-only client, walked by engine 9 with its own
  arithmetic. The client is constructible only in replay mode (enforced by a test). Its parameters
  go on the `runs` row, and a digest goes on every trade and rejection.
- **R1, ranking:** engine 8's expected move, batched. **This closes spec 75.** Net-margin ranking
  is rejected on live feasibility. No alphabetical run (operator ruling 2026-09-19).
- **R2, skeptic:** the capped skeptic (13 folds).
- **R3, tiers:** 3 and 5.
- **R4, window:** six months, folds 379 to 404, ending at fold 404's test close (2025-01-04). That
  is **two runs: tiers 3 and 5 on expected move** (operator ruling 2026-09-19; the lead's earlier
  four-run reading is withdrawn). The tiers run in parallel on separate databases. Folds run in
  sequence within a run.
- **R7, the fee figures:** sourced. Kraken's schedule was fetched and committed on 2026-09-19. The
  2026 schedule applied to a 2023–24 window is a stated limitation.
- **R8, benchmarks:** both. BTC/USD buy-and-hold, and an equal-weighted basket of the pairs held
  while held. Each is reported against the equity curve including cash periods.
- **R9, trials:** every configuration ever evaluated against the out-of-sample data, listed one by
  one in a committed ledger, counted conservatively.
- **R10 and R10b, promotion bar:** fixed before anything runs. The interval allows for overlapping
  holds and is widened for trials, and a model is promoted only if its lower bound is above zero.
- **R11:** the ranking skips pairs the anomaly and DI gates would refuse.
- **R12:** invariant 4's wording, in the operator's words (spec 126 step 4).

### Deliberately not scheduled, and why

- **Prerequisites 2, 3 and 4** (the whole-dataset memory hazards in training). No full walk-forward
  runs in this plan, because nothing retrains a predictor. They stay open until a full rerun is
  planned. This contradicts the tracker's line that Phase 7's full walk-forward "pays the same cost
  again unless all six are fixed first". **That line assumed a full rerun this phase, and this plan
  has none.** Flagged for your confirmation; not yet answered.
- **The capped skeptic across all 405 folds** and Finding 1's full re-measurement: only the window's
  folds are trained (spec 136).
- **Specs 121 to 125** (stale prose from Phase 6) stay open with their owners, as in HANDOFF 12.

### Cost, from `phase-7-findings.md` and the reconnaissance

- **Build:** 12 to 17 hours of agent time across the specs below. This is the lead's estimate, not
  a measurement.
- **Run:** 7 to 15 hours per run for six months, at 1.5 to 3 s per bar tick. The alphabetical
  baseline skips the batched ranking (about 0.9 s per bar), so it should run faster. Spec 142
  replaces the estimate with a measurement before spec 143 launches.

## Tasks

Claim by writing the spec number in your progress file. Waves are dependency order.

### Lead — 4 tasks

| Spec | Task | Files | Acceptance | Wave |
|---|---|---|---|---|
| 126 | Rulings into the documents: invariant 2's replay fee and book rule, invariant 4 in the operator's words (R12), the proxies named, config keys, seams | `context/*`, `config/default.yaml` | `docs_vocabulary` PASS; the contradicted-claim grep recorded; every seam has a producer no later than its consumer | 0 |
| 144 | The ranking's contract: `engine-contracts.md`, `project-overview.md`, the ownership seam | `context/*` | invariant 4 as ruled; `docs_vocabulary` PASS | 0 |
| 134 | The `runs` row carries the replay scenario digest and the synthetic book's parameters | `core/orchestrator.py`, `tests/core/` | the replay row carries both; the paper row carries null | 2 |
| 143 | The two runs (tiers 3 and 5, expected move), the digests and the findings substitution | `tests/fixtures/`, `docs/dataset/phase-7-findings.md` | all four runs complete or stop with the cause; every pending marker substituted | 4 |

### A — Platform — 6 tasks

| Spec | Task | Files | Acceptance | Wave |
|---|---|---|---|---|
| 127 | Record a genuine `AssetPairs`; the survivorship count | `scripts/`, `tests/fixtures/kraken/` | parses through the live model; count and names in the build log | 1 |
| 128 | Weekly time-and-sales partitions | `scripts/`, `data/derived/trades_weekly/` | row counts reconcile; peak memory on `XBTUSD.csv` recorded | 1 |
| 130 | The bucket table script and fixture (the lead committed the fee schedule) | `scripts/`, `tests/fixtures/replay/` | reproduces the findings' table, or says why not | 1 |
| 129 | The replay client | `clients/kraken/`, `tests/clients/kraken/` | refused outside replay; engine 9's walk hand-checked on two buckets; no trade after `now` | 2 |
| 131 | Engine 23 drives the registered chain | `research/backtest.py`, `cli/research.py`, tests | identical reruns; minute ticks exactly while exposed; kill and resume identical | 3 |
| 142 | Rehearse one replayed day | tests, fixture | two clean runs identical; every recomputation equal; per-tick cost measured | 3 |

*A also has a separate task outside Phase 7, ordered by the operator on 2026-09-19: the recorder gap
audit, in `scripts/recording/`. It touches nothing Phase 7 builds, and it is reported in
`docs/build-log/phase-7/a-platform.md` under its own heading.*

### B — Store and trading — 2 tasks

| Spec | Task | Files | Acceptance | Wave |
|---|---|---|---|---|
| 132 | Migration 0006: approval economics on `trades`, the scenario on `runs` | `db/migrations/`, `clients/store/`, tests | pre-0006 rows read as absent; a float refused | 1 |
| 144 | Engine 7 ranks by expected move through the shared function | `engines/scout/`, tests | `rank_universe` tested directly on disagreeing orders; reversing the ranking changes no gate's verdict | 2 |

No filler is invented, per the run protocol.

### C — Interface and models — 9 tasks

| Spec | Task | Files | Acceptance | Wave |
|---|---|---|---|---|
| 141 | The Phase 7 criteria, PENDING first | `scripts/verify.py`, `tests/verify/` | each PENDING, PASS and FAIL observed | 1 |
| 135 | DI and anomaly artefacts assembled from the study (module in wave 1; the window's assembly runs after 136, so each run directory is written once and complete) | `research/` (new module), `modelling/artefacts.py`, tests | engines 8 and 13 load every assembled fold; identity equals the study's | 1 |
| 137 | Batched DI score | `modelling/di.py`, tests | row-by-row equivalence to `score` | 1 |
| 136 | The capped skeptic | `research/training.py`, tests | the disabled-cap replication equals the saved skeptics | 2 |
| 133 | Engine 19 records approval economics | `engines/memory/`, tests | the `trades` figures equal engine 10's published values, recomputed | 2 |
| 144 | The shared ranking function, skipping anomaly and DI refusals (R11) | `modelling/`, tests | the chosen pair's expected move equals engine 8's, recomputed | 2 |
| 138 | Alpha attribution against both benchmarks | `research/attribution.py`, tests | recovers a planted alpha and beta against each benchmark; reports a removed alpha as not significant | 3 |
| 139 | Deflated metric, the trial ledger and the promotion gate | `engines/tournament/`, `docs/dataset/`, `console/format.py`, tests | rejects the haircut-failing model; promotes it at one trial; the ledger lists every trial | 3 |
| 145 | Every gate's verdict on both sides: `approvals.details` and `rejections.details` (operator ruling 2026-09-19). After 133 is committed | `engines/memory/`, tests | recomputed from `state`; the refuser marked; four mutations killed | 2 |
| 140 (writer) | SHAP writer, BEFORE the run, after 145 | `engines/memory/`, tests | a refusal writes a SHAP row; an engine 8 refusal writes none | 2 |
| 140 (screens) | Research screens, AFTER the run | `console/`, tests | the SHAP view renders a written row | 5 |

## Read this before you claim anything

HANDOFF 12's standing rules carry over unchanged:

- claim before code;
- a build-log entry at diagnosis, before the fix;
- every assertion proven capable of failing, from a byte copy, verified by mutation and never by
  reading;
- one gate per spec boundary; the lead commits and pushes at every boundary;
- ask the lead before a baseline run;
- **the recorder, the recording manager and the funding poller are never stopped, restarted or
  reconfigured by Phase 7 work.** The one exception is the operator's recorder task above, on the
  operator's own instruction.

One addition for this phase: **a declared value is not a measurement.** Every number the replay
serves that the archive did not record (spread, depth, fee) is labelled as declared wherever it
appears, in code comments, fixtures, reports and messages alike.

**Phase 7 fails quietly, as Phase 5 did.** A wrong benchmark window or a miscounted trial produces a
plausible, flattering answer and nothing goes red. The standard is the spread-constant finding: a
flat 10 bps showed +0.3% to +0.6% where the bucket table showed −0.03% to −0.25% on the same run.
For every figure, ask what it returns when it is quietly wrong, and whether anyone downstream could
tell.
