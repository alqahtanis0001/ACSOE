# Phase 7 — shared task list

## HANDOFF 0, 2026-09-19 — specs drafted and revised for four rulings, AWAITING OPERATOR APPROVAL. Nothing is claimed or built.

**Read this first.** Specs 126 to 144 were written by the lead from the Phase 7 row, the nine Phase 7
prerequisites, and the operator's rulings of 2026-09-19. They were revised the same day for the
second round of rulings (ranking, tiers, fee source, promotion bar), and the findings document was
revised with them (§R). The evidence behind every choice is
`docs/dataset/phase-7-findings.md` (committed `93403b7`) and the reconnaissance beside it. **No
teammate starts until the operator approves these specs and answers the rulings below.**

### Rulings already made (2026-09-19), written into the documents by spec 126

- **Fees:** invariant 2 is amended to permit a declared fee scenario **in replay mode only**,
  enforced by a test. The operator supplies the schedule with its URL and date.
- **Pair rules:** a genuine `AssetPairs` is recorded now and committed with its URL and date. That
  also closes prerequisite 9.
- **DI and anomaly thresholds:** rebuilt from the Phase 5 study into new run directories, not
  refitted.
- **Spread:** declared, not modelled. The form was delegated to the lead's recommendation: the
  liquidity-bucket table (`phase-7-findings.md` §3).
- **The book:** a synthetic book served by a replay-only client, so engine 9 still does its own
  arithmetic. This was the operator's stated preference, and the lead agreed on the seams.
- **R1, ranking:** engine 8's expected move, batched. Invariant 4 is amended narrowly in the
  operator's words (spec 126 step 4, spec 144). Net-margin ranking is rejected on live feasibility.
- **R3, tiers:** 3 and 5.
- **R7, the fee figures:** sourced. Kraken's schedule was fetched and committed 2026-09-19, and it
  agrees with the operator's figures. The 9 July 2026 restructuring is sourced beside it.
- **R10, the promotion bar:** set in advance. Its operational form is R10b below.

### Rulings required before the specs they block

| # | Question | Blocks | Lead's recommendation |
|---|---|---|---|
| R2 | Simulate the capped skeptic, or the uncapped one as trained | 126 step 5, 136 | Capped: it is the ruled one, and in this window it passes 4× as many calls; about 25 min to train |
| R4 | The window: 6 months or 12 (the tiers are ruled) | 135, 136 (folds in scope), 143 | 6 months, tiers 3 and 5 in parallel, in a separate unattended session after the build |
| R8 | The benchmark for attribution | 138 | BTC/USD buy-and-hold, plus an equal-weighted basket of the pairs held while held |
| R9 | What counts as a trial for the deflated metric | 139 | Every leaderboard row plus every reconnaissance grid cell, in a committed ledger |
| R10b | The promotion bar's operational form: which interval, and how it is widened for trials | 139, 143 | A covariance allowing for overlapping holds, widened by the deflated-metric haircut; promote only if the lower bound is above zero |
| R11 | Does the expected-move ranking skip pairs the anomaly and DI gates would refuse? | 144, 137 | Yes (b): it is the arrangement the 46-trade figure was measured under; the gates still re-judge the chosen pair |
| R12 | Words carving out invariant 4's "less willing, never more" sentence, which the ranking contradicts | 126 step 4 | None proposed: the operator's words |

### Deliberately not scheduled, and why

- **Prerequisites 2, 3 and 4** (the whole-dataset memory hazards in training). No full walk-forward
  runs in this plan, because nothing retrains a predictor. They stay open until a full rerun is
  planned. This contradicts the tracker's line that Phase 7's full walk-forward "pays the same cost
  again unless all six are fixed first". **That line assumed a full rerun this phase, and this plan
  has none.** Flagged for your confirmation.
- **Prerequisite 5 (spec 137)** is now required under R11 (b).
- **The capped skeptic across all 405 folds** and Finding 1's full re-measurement: only the window's
  folds are trained (spec 136).
- **Specs 121 to 125** (stale prose from Phase 6) stay open with their owners, as in HANDOFF 12.

### Cost, from `phase-7-findings.md` and the reconnaissance

- **Build:** 12 to 17 hours of agent time across the specs below. This is the lead's estimate, not
  a measurement.
- **Run:** 7 to 15 hours per tier for six months, at 1.5 to 3 s per bar tick. That figure is a sum
  of measured parts; spec 142 replaces it with a measurement before spec 143 launches.

## Tasks

Claim by writing the spec number in your progress file. Waves are dependency order.

### Lead — 4 tasks

| Spec | Task | Files | Acceptance | Wave |
|---|---|---|---|---|
| 126 | Rulings into the documents: invariant 2's replay fee and book rule, the proxies named, R1 and R2 recorded once ruled, config keys, seams | `context/*`, `config/default.yaml` | `docs_vocabulary` PASS; the contradicted-claim grep recorded; every seam has a producer no later than its consumer | 0 |
| 144 | The ranking's contract: invariant 4 and `engine-contracts.md` text, the ownership seam (after R11 and R12) | `context/*` | the amendment in the operator's words; `docs_vocabulary` PASS | 0 |
| 134 | The `runs` row carries the replay scenario digest | `core/orchestrator.py`, `tests/core/` | the replay row carries the digest; the paper row carries null | 2 |
| 143 | The run, the digests and the findings substitution | `tests/fixtures/`, `docs/dataset/phase-7-findings.md` | both runs complete or stop with the cause; every pending marker substituted | 4 |

### A — Platform — 6 tasks

| Spec | Task | Files | Acceptance | Wave |
|---|---|---|---|---|
| 127 | Record a genuine `AssetPairs`; the survivorship count | `scripts/`, `tests/fixtures/kraken/` | parses through the live model; count and names in the build log | 1 |
| 128 | Weekly time-and-sales partitions | `scripts/`, `data/derived/trades_weekly/` | row counts reconcile; peak memory on `XBTUSD.csv` recorded | 1 |
| 130 | The bucket table script and fixture (the lead commits the fee schedule) | `scripts/`, `tests/fixtures/replay/` | reproduces the findings' table, or says why not | 1 |
| 129 | The replay client | `clients/kraken/`, `tests/clients/kraken/` | refused outside replay; engine 9's walk hand-checked on two buckets; no trade after `now` | 2 |
| 131 | Engine 23 drives the registered chain | `research/backtest.py`, `cli/research.py`, tests | identical reruns; minute ticks exactly while exposed; kill and resume identical | 3 |
| 142 | Rehearse one replayed day | tests, fixture | two clean runs identical; every recomputation equal; per-tick cost measured | 3 |


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
| 135 | DI and anomaly artefacts assembled from the study | `research/` (new module), `modelling/artefacts.py`, tests | engines 8 and 13 load every assembled fold; identity equals the study's | 1 |
| 136 | The capped skeptic (held on R2) | `research/training.py`, tests | the disabled-cap replication equals the saved skeptics | 2 |
| 133 | Engine 19 records approval economics | `engines/memory/`, tests | the `trades` figures equal engine 10's published values, recomputed | 2 |
| 138 | Alpha attribution (held on R8) | `research/attribution.py`, tests | recovers a planted alpha and beta; reports a removed alpha as not significant | 3 |
| 139 | Deflated metric and promotion gate (held on R9 and R10) | `engines/tournament/`, `console/format.py`, tests | rejects the haircut-failing model; promotes it at one trial | 3 |
| 140 | SHAP writer and research screens | `engines/memory/`, `console/`, tests | a refusal writes a SHAP row that renders; an engine 8 refusal writes none | 3 |
| 137 | Batched DI score | `modelling/di.py`, tests | row-by-row equivalence to `score` | 1 |
| 144 | The shared ranking function (after R11) | `modelling/`, tests | the chosen pair's expected move equals engine 8's, recomputed | 2 |

## Read this before you claim anything

HANDOFF 12's standing rules carry over unchanged:

- claim before code;
- a build-log entry at diagnosis;
- every assertion proven capable of failing, from a byte copy;
- ask the lead before a baseline run;
- **the recorder, the recording manager and the funding poller are never stopped, restarted or
  reconfigured.**

One addition for this phase: **a declared value is not a measurement.** Every number the replay
serves that the archive did not record (spread, depth, fee) is labelled as declared wherever it
appears, in code comments, fixtures, reports and messages alike.
