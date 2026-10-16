# Evidence pack 01 — the system

**Read at commit `9f5a1449378c10e8f8f87ec27732914a0a19e92f` (`9f5a144`), branch `main`, working tree clean, between 2026-09-20T15:33:30Z and 2026-09-20T15:50Z.** Every fact below names its file (and line range where wording matters). Nothing in the tree was changed; the two Phase 7 runs, the recorder, the recording manager, the supervisor, `funding.py` and `fees.py` were not touched. Run databases were read through `file:PATH?mode=ro&immutable=1`, one short query per connection. **Caveat on that URI:** `immutable=1` reads the main database file and not the write-ahead log, so every database figure here is as at SQLite's last checkpoint, a few dozen ticks behind the live process; the run-record files (`*.runrecord.jsonl`) are the live tail and are quoted separately.

## Contents

- [A. Repo and machine state](#a-repo-and-machine-state)
  - [A.1 Branch, HEAD, status, log](#a1-branch-head-status-log)
  - [A.2 Uncommitted and untracked files](#a2-uncommitted-and-untracked-files)
  - [A.3 Alive processes](#a3-alive-processes)
  - [A.4 The two Phase 7 runs, from their own stored state](#a4-the-two-phase-7-runs-from-their-own-stored-state)
  - [A.5 Timeline facts from git](#a5-timeline-facts-from-git)
- [B. What the system is, verbatim](#b-what-the-system-is-verbatim)
  - [B.1 The canonical description](#b1-the-canonical-description)
  - [B.2 The invariants](#b2-the-invariants)
  - [B.3 The Locked Decisions](#b3-the-locked-decisions)
  - [B.4 The research question and the promotion bar, every occurrence](#b4-the-research-question-and-the-promotion-bar-every-occurrence)
  - [B.5 The pre-registration section and the six FINAL sections](#b5-the-pre-registration-section-and-the-six-final-sections)
  - [B.6 Retired vocabulary](#b6-retired-vocabulary)
  - [B.7 Abbreviations and named components](#b7-abbreviations-and-named-components)
  - [B.8 Ethics and safety material](#b8-ethics-and-safety-material)
- [C. Architecture](#c-architecture)
  - [C.1 The engine registry, verbatim](#c1-the-engine-registry-verbatim)
  - [C.2 The offline chain, verbatim](#c2-the-offline-chain-verbatim)
  - [C.3 One row per engine](#c3-one-row-per-engine)
  - [C.4 The orchestrator loop, verbatim](#c4-the-orchestrator-loop-verbatim)
  - [C.5 The console](#c5-the-console)
  - [C.6 The client layer](#c6-the-client-layer)
  - [C.7 The database](#c7-the-database)
  - [C.8 The reason-code prose map](#c8-the-reason-code-prose-map)
  - [C.9 Two complete tick traces from stored rows](#c9-two-complete-tick-traces-from-stored-rows)

---

## A. Repo and machine state

### A.1 Branch, HEAD, status, log

- Branch: `main`. HEAD: `9f5a1449378c10e8f8f87ec27732914a0a19e92f`. `git status --porcelain --untracked-files=all` printed nothing (clean; 0 untracked).
- Commit count: **277** (`git rev-list --count HEAD`). First commit `1f1551d` 2026-09-08 14:02:27 +0100. Last commit `9f5a144` 2026-09-20 16:27:43 +0100.
- `git log --oneline -30` (read at 15:33Z):

```
9f5a144 docs: findings Part II, written from the live runs: the simulation as built and why tiers 3 and 5; what is running and where it has reached; every recorded decision checked against what ran; the findings so far; tier 3's outlook marked PROJECTION NOT A RESULT; future work with its fitting warning (lead)
edfa788 docs: Phase 8 finding, from running the system: the loss-streak breaker trips correctly on five consecutive losses, but its recovery path does not exist; the check recomputes from trade history every tick and holds no state, so an operator reactivation cannot reset it; fix by recording the clear's timestamp (lead)
830f642 docs: F7, live: tier 5 froze on a 5-loss streak at 2024-10-20 05:30Z and has taken no trade since (2,248 blocked ticks); five stops on STORJ/USD; nothing un-freezes a replay; the run is not stopped (lead)
bf702f7 docs: LAUNCHED both Phase 7 runs at 19c5a11 (t3 python 17956, t5 python 55944), the PID table filled in; the kill-and-resume precondition judged met by hand on the five rehearsals' evidence, declared in the findings; a-replay's shap_ref exclusion as a Phase 8 tracker item (lead)
c14e08f docs: all five gating rehearsals completed and pass every precondition except kill-and-resume, which differs only in the cycle number embedded in shap_ref; every other table byte-identical (lead)
2fafc70 docs: handover current state: launch ruled (19c5a11 with SHAP, caps 40/8); five isolated gating rehearsals running; the watchdog task registered and firing under Task Scheduler (lead)
0643721 docs: the launch check refuses SHAP files older than the rehearsal (run ids repeat between rehearsals of one day and SHAP is write-once); 36 of 36 violations caught (lead)
2a8d50c docs: the A/B stated as the operator corrected it: a lower rate, enough to launch on, exonerating nothing; expected 0.96 crashes per arm, P(0 in both) about 0.15 (lead)
e63891d docs: the A/B result (neither arm crashed, 1,700 ticks each), the decision it drove (launch 19c5a11 with SHAP, caps 40 and 8), recorded in the build log and the findings; the stale-SHAP hole in the check found before use (lead)
d291925 docs: tracker: the event-log finding as a Phase 8 item (two native crashes in two modules, consistent with heap corruption, no WHEA errors in 30 days), by operator ruling (lead)
6f9120b docs: the Phase 7 auto-resume watchdog (operator ruling, option A modified), with its tests and mutation proof (lead)
969053d docs: the A/B's decision rule, fixed by the operator before any result (lead)
6ff8cbd docs: second rehearsal crash (engine 3 build_candles, polars construction), rate about 1.8 per process-hour on 19c5a11 against 0 in 4,288 ticks on the morning's code; stopped for the operator, not launched (lead)
11d4fff docs: findings 7b, before launch: the intermittent polars fault, the auto-resume ruling with every resume counted and reported, and each run's first bar skipped by design; tracker: the native fault as a Phase 8 item, with the operator's machine note (lead)
0719b36 docs: the gating rehearsal crashed natively in polars (intermittent: two repros clean); rehearsal rerun and stress runs going; launch held for the operator's ruling on crash recovery (lead)
7cb89ae docs: the launch check also asserts the ranking the run recorded on its runs row (scenario_description), in both modes; added before the rehearsal's report exists; 35 of 35 violations caught (lead)
d5f5a49 docs: the dry run's tick-1 block diagnosed: engine 7 has no equity row to size against on a fresh store, one bar per run, recorded not changed (lead)
d87d0d3 docs: handover current state: final code 19c5a11 (146 committed); the gating rehearsal and the dry run starting (lead)
19c5a11 B+C+A+Lead: engine 7's universe step stored on every tick it ran (spec 146): migration 0007 scout_tallies and the store (b-store), engine 19's writer (c-eval), scout_tallies in DOCUMENTED_TABLES (C), the storage-model rows (lead), and the rehearsal's tally check (a-replay)
323ed60 docs: handover current state: 140 committed at 93e5ea1, b13 gating 146 (lead)
93e5ea1 C: engine 19 writes SHAP for every decision engine 8 explained, before the run (spec 140 writer, c-eval)
3efe958 docs: the launch-precondition check, committed before the gating rehearsal runs: it FAILS (not counts) on no SHAP files or unresolved shap_ref, unfilled details, missing tallies or digest, and on any run not ranked by expected move as the run itself recorded it (operator's assertion); proven 31 of 31 violations caught, plus the live-run mode (lead)
ce2cb0e docs: handover current-state block: new lead took over, previous session closed by the operator, b11 void and 140 re-gated as b12 on its exact blobs, 146's engine 19 half found applied; the mutation harness's hard-kill restore gap recorded for Phase 8 (lead)
b27d117 docs: handover step 5 marked done (lead)
6f242e0 docs: the launcher passes --begin 2024-10-05T00:15:00 for the three-month window, and its dry run ticks inside the window; the handover's pointer fixed (lead)
d535313 docs: the task list points at the handover file as the authority; the handover records the findings as written (lead)
490f0d2 docs: findings written for launch: the three-month window (R.6, 6a, 7a), and 7b stated before any figure: the window's limitations, the promotion bar expected unreachable at these trade counts, N = 1,679, the benchmarks with no claimed citation, F4 as no detectable difference, F6 measured against calculated, F5; spec 143 and the task list set to three months (lead)
287a812 docs: handover updated: the window is three months (locked), nothing else cut; tier 5 correction; measured timing inputs; remaining steps; the launcher needs --begin; decisions D23-D25 (lead)
91d10e4 docs: Phase 7 handover for the next session; the launcher (two runs), status script and gate script committed (lead)
9c42fba docs: findings 7a, the declared substitutes the chain simulation runs on, with sources, dates and declared limitations, written before launch (lead)
```

Commits per calendar day (`git log --format=%ad --date=short | sort | uniq -c`): 09-08: 21, 09-09: 37, 09-10: 41, 09-11: 26, 09-12: 3, 09-13: 42, 09-14: 3, 09-15: 5, 09-16: 28, 09-17: 8, 09-18: 12, 09-19: 48, 09-20: 3.

### A.2 Uncommitted and untracked files

**None.** The working tree was clean at every read. No file quoted in this pack carries an uncommitted change. (The runs execute from a detached worktree at `C:\Users\saad2\Documents\GitHub\ACSOE-run-19c5a11`, HEAD `19c5a11c39cf523c28c39c78e5b371f9a4b1c051`, whose `data\` and `models\` are junctions into this checkout — `docs/build-log/phase-7/launch_phase7.ps1.txt` lines 3–5, 19–24. So the code the runs execute is commit `19c5a11`, twelve commits behind HEAD; every commit since is documentation.)

### A.3 Alive processes

Read with `Get-CimInstance Win32_Process` at 2026-09-20T15:36Z. The venv's `python.exe` is a launcher that starts the real interpreter as its own child, so each run shows two PIDs; the working process is the second (`launch_phase7.ps1.txt` line 66).

| Role | PID (launcher → worker) | Start (UTC) | Command line (abridged) | Last line of its own log / heartbeat |
|---|---|---|---|---|
| Tier 3 run | 58480 → **17956** (7,099 MB working set) | 2026-09-19T22:12:24Z | `python -m acsoe.cli.main --config config/default.yaml research backtest --db data\db\phase7-t3-expected_move.sqlite --ranking expected_move --fee-tier 3 --log-dir "…\ACSOE-run-19c5a11\phase7-runs\logs-t3-expected_move" --begin 2024-10-05T00:15:00` | `data/db/phase7-t3-expected_move.sqlite.runrecord.jsonl` last line at 15:33Z: `{"bar_tick": true, "event": "tick", "exposed_after": false, "fold": 401, "tick_s": 1733644800, "wall_ms": 9847.353}` (= 2024-12-08T08:00:00Z) |
| Tier 5 run | 53356 → **55944** (6,741 MB) | 2026-09-19T22:12:24Z | same with `--db data\db\phase7-t5-expected_move.sqlite --fee-tier 5 --log-dir …logs-t5-expected_move` | runrecord last line: `{"bar_tick": true, "event": "tick", "exposed_after": false, "fold": 401, "tick_s": 1734061500, "wall_ms": 9403.64}` (= 2024-12-13T03:45:00Z) |
| Recorder (`scripts/record.py --config config\recorder.yaml`) | 49212 → 28060 | 2026-09-19T15:01:57Z | tier 1 full raw + tier 2 summaries, one process, two sockets | tier-1 heartbeat `data/raw/heartbeat__msi__2026-09-20.ndjson` last line: `ts 2026-09-20T15:42:03Z, tier1, 10 pairs [BTC/USD, USDT/USD, ETH/USD, XRP/USD, SOL/USD, ZEC/USD, USDC/USD, NEAR/USD, EUR/USD, HYPE/USD], frames 22,020,347, bytes_written 7,535,432,953, connected: true`. Tier-2 heartbeat `data/summaries/heartbeat__msi__2026-09-20.ndjson` last line: `ts 2026-09-20T15:40:03Z, tier2, pair_count 170, frames 164,970,197, connected: true, checksum_failures 25, resubscribes 3, checksum_unverifiable [LUNA/USD]` |
| Supervisor (`scripts/recording/supervise.py --config config\recorder.yaml`) | 16644 → 40832 | 2026-09-19T15:01:57Z | parent of the recorder, `fees.py` and `funding.py` | `logs/supervisor__msi__2026-09-19.log` last line: `[tier2] disconnected (ConnectionClosedError), reconnecting in 0.6s (attempt 1)` |
| `fees.py` (`scripts/recording/fees.py --config config\recorder.yaml`) | 33864 → 7240 | 2026-09-19T15:01:57Z | hourly `AssetPairs` + `TradeVolume` poll | `logs/fees__msi__2026-09-19.log` last block: slot `2026-09-19T15:01:57Z`, `spot_pairs 10, asset_pairs 1450, schedules_returned: true`; newest archive file `data/raw/fees/fees__msi__2026-09-20.jsonl`, last line `ts_recv 2026-09-20T15:00:00.497858Z`, endpoint `/0/private/TradeVolume` |
| `funding.py` (`scripts/recording/funding.py --config config\recorder.yaml`) | 12920 → 34416 | 2026-09-19T15:01:57Z | hourly Kraken Futures funding/OI poll | `logs/funding__msi__2026-09-19.log` ends with a closed JSON summary; newest file `data/raw/funding/funding__msi__2026-09-20.jsonl` |
| Recording manager (`scripts/recording/manager/serve.py`) | 52180 → 27480 | 2026-09-19T03:56:23Z | — | NOT FOUND: no log file named for the manager under `logs/` (the older `logs/manager-restart-20260919.*.log` are both empty) |

The supervisor restart at 15:01:57Z on 2026-09-19 is the switchover the tracker records (`context/progress-tracker.md` lines 32–48: cut-off 05:08:44Z for the first start of the new recorder; the 15:01Z start is a later restart of the same supervisor tree — the fee log shows two slots, `05:08:44Z` and `15:01:57Z`, each preceded by a `fees poller:` start banner).

### A.4 The two Phase 7 runs, from their own stored state

Sources: each run's SQLite (`data/db/phase7-t{3,5}-expected_move.sqlite`, read-only, immutable — main file only), its `*.runrecord.jsonl` beside it, and the launch record `…\ACSOE-run-19c5a11\phase7-runs\launch.json`. The window is folds 392–404 (13 folds), 2024-10-05T00:15Z to 2025-01-04T00:00Z (`feature-specs/143-the-simulation-run.md` lines 21–25; the `runs` row's `scenario_description.window.begin_s = 1728087300` = 2024-10-05T00:15:00Z, `first_fold 379, last_fold 404` from `config/default.yaml` lines 365–366 with `--begin` cutting the start).

| | Tier 3 | Tier 5 |
|---|---|---|
| `runs.run_id` | `replay-phase7-t3-expected_move-20241005T001500Z` | `replay-phase7-t5-expected_move-20241005T001500Z` |
| `runs.mode` / `system_mode` / `system_mode_at` | `replay` / **`running`** / 1728087300000000 (2024-10-05T00:15Z) | `replay` / **`frozen`** / 1729403100000000 (2024-10-20T05:45Z) |
| `runs.scenario_digest` | `1eb6860e…867b53` | `e89b0e28…a176fe` |
| Fee served (scenario_description.fee) | tier 3, maker `0.0022`, taker `0.0038`, `volume_30d_served 10000` | tier 5, maker `0.0015`, taker `0.003`, `volume_30d_served 50000` |
| Folds done of 13 (runrecord `fold_switch` events) | 10 switches: folds 392→401 started, so **9 complete (392–400), fold 401 in progress** | same: 9 complete, 401 in progress |
| Current fold / test week | 401: test week 2024-12-07 → 2024-12-14 | 401 |
| Simulated time reached (runrecord tail) | 2024-12-08T08:00Z | 2024-12-13T03:45Z |
| Ticks done (runrecord `tick` events, 15:33Z) | 6,789 | (`event` counts read for t3 only; t5's tail tick is 1734061500) |
| Bar ticks so far (runrecord, 15:41Z) | 6,200 of 8,736 | 6,665 of 8,736 |
| Equity rows in DB (checkpointed) | 6,760 | 6,741 |
| Trades closed (DB) | **9** | **5** |
| Approvals (DB) | 13 | 7 |
| Orders (DB): entries filled / cancelled; exits | 9 / 4; 9 market exits | 5 / 2; 5 market exits |
| Rejections (DB) | 6,045 (6,035 `net_edge_below_hurdle`, 10 `spread_wider_than_move`, all `rejected_by = cost`) | 1,445 (all `cost` / `net_edge_below_hurdle`) |
| `block_records` (DB) | 0 | 5,128, all `blocked_by = safety`, `block_reason = "Safety breaker: 5 consecutive losses, limit 5"`, `status BLOCK`, first ts 1729402200000000 (2024-10-20T05:30Z), last 1734016500000000 |
| `scout_tallies` (DB) | 6,148 rows (6,059 with a candidate; 38 `empty_universe`; 50 `no_rankable_pair`; 1 `scout_inputs_unavailable` — tick 1) | 1,461 (1,452 with a candidate; 8 `empty_universe`; 1 `scout_inputs_unavailable`) |
| Latest equity row (DB) | ts 2024-12-08T00:45Z, cycle 6760: equity **4920.055882804568922191840340**, peak 5143.937791027744879131675441, cash = equity, positions_value 0, realised_pnl_cum −79.94411719543107780815965967, open 0 | ts 2024-12-12T15:15Z, cycle 6741: equity **4645.588515155844495159903843**, peak 5014.178865839436002424812500, realised_pnl_cum −354.4114848441555048400961582, open 0 |
| Commands (DB) | 1: `activate` by `console` at 1728087300 ("replay driver: activate before the first tick of this process") | 2: the same `activate`; then `freeze` by `safety`, reason `safety: loss_streak`, created_at 1729402200000000 (05:30Z), claimed/consumed 1729403100000000 (05:45Z) |
| Resumes | **0** — one `run` event in the runrecord, `resume_after_s: null`, run_id without `-resumed`; no `resumes.jsonl` in `…\phase7-runs\logs-t3-expected_move\` | **0** — same |
| Crashes | **0** — a single process since launch (PID start 22:12:24Z = launch time in `launch.json`); `docs/build-log/phase-7/lead.md` "No crashes and no resumes on either run since launch" (Part II entry, 2026-09-20 16:25) | 0 |

The tier 3 `runs.system_mode` is `running`; the tier 5 row says `frozen` since 2024-10-20T05:45Z. Findings Part II (`docs/dataset/phase-7-findings.md` lines 942–957) gives the lead's own 16:25-local snapshot of the same rows (6,127 / 6,587 bar ticks; 9 / 5 trades; 4,920.06 / 4,645.59); the DB and runrecord reads above are later and agree on every final-shaped number.

### A.5 Timeline facts from git

| Event | Date | Source |
|---|---|---|
| First commit | 2026-09-08 14:02:27 +0100 (`1f1551d`) | `git log --reverse` |
| Commit count at HEAD | 277 | `git rev-list --count HEAD` |
| Recorder (`scripts/record.py`) first committed | 2026-09-08 17:24:22 +0100 (`afaf2f5`) | `git log --reverse -- scripts/record.py` |
| First recorded frame on disk | 2026-09-08T16:01:22Z | `tests/fixtures/recording_report_full_archive.json` `span.start_iso` (committed digest of `data/raw/kraken_v2_2026-09-08.jsonl`) |
| Two-tier recorder committed | 2026-09-11 17:22:38 +0100 (`1646cb2`) | `git log` |
| Two-tier recorder's first session marker | 2026-09-11T19:48:02Z | first line of `data/raw/kraken_v2__msi__2026-09-11.jsonl` (file head only) |
| Archive build (full OHLCVT rebuild) | 2026-09-11T22:34:49Z; committed 2026-09-12 02:10:58 +0100 (`ef8f1f0`) | `docs/dataset/labelled-dataset-2026-09-12.json` `meta.archive_built_at`; `git log` |
| Walk-forward training run started | 2026-09-13T20:52:45Z (run id `train-20260913T205245-067b2b9d`) | `tests/fixtures/walkforward_digest.json` `created_at` |
| Fee tier measured on the account | 2026-09-19T05:08:45.806613Z (first `TradeVolume` line, HTTP 200, `error: []`) | `data/raw/fees/fees__msi__2026-09-19.jsonl`; recorded in the tracker's commit `228cea3` 2026-09-19 06:11:43 +0100 |
| Findings document pushed before launch | `9c42fba` 2026-09-19 17:21:48 +0100 (7a); `490f0d2` 2026-09-19 18:01:06 +0100 (7b) | `git log` |
| Launch commit (code the runs execute) | `19c5a11` 2026-09-19 19:16:15 +0100 | `git log` |
| Runs launched | 2026-09-19T22:12:24Z = 23:12:24 local (process creation); `bf702f7` "LAUNCHED" committed 23:14:23 +0100 | `Win32_Process.CreationDate`; `git log` |
| Tier 5 froze (simulated time) | 2024-10-20T05:30Z; found 2026-09-20 05:05 local (`830f642` commit) | DB `commands` row 2; `docs/build-log/phase-7/lead.md` F7 entry |

---

## B. What the system is, verbatim

### B.1 The canonical description

*Verbatim from `context/project-overview.md`, lines 1–23:*

```markdown
# ACSOE — Adaptive Crypto Spot Opportunity Engine

## What this is

A fully automated spot trading system for Kraken. It scans the exchange, finds candidates, subjects each one to a chain of gates, and buys only when the expected move beats every cost with margin to spare. It then manages the position until exit and learns from both the trades it took and the ones it refused.

This is a Master's dissertation project. Its value is the rigour of the rejection machinery and the honesty of the evaluation, not the size of the profit.

## Core philosophy

**Reject first; execute only with verified net edge.**

Most of the system exists to say no. Nine of the twenty-three engines contain no machine learning at all — 1 `exchange`, 2 `market_data_recorder`, 3 `market_sensor`, 4 `data_guard`, 7 `scout`, 10 `cost`, 11 `risk`, 16 `decision` and 17 `safety`. The components that protect capital are auditable arithmetic, not models anyone has to trust. Engine 7 is counted for its universe filter, which contains no model; since 2026-09-19 its *ordering* reads the predictor's expected move (invariant 4, amended), and every gate still judges the chosen pair itself.

## What makes it different from a retail bot

1. **It does not predict price.** It predicts which of three barriers price touches first: a profit target, a stop, or a timeout.
2. **Multi-stage fail-closed gating.** Any gate can halt the pipeline. No model output ever overrides one. The single deliberate override in the whole system is an emergency liquidation, which can only reduce exposure, never open a position — invariant 14.
3. **The Skeptic.** A second model whose only job is to find reasons not to trade, plus a dissimilarity check that refuses to predict on market conditions it has never seen.
4. **Rejected-trade memory.** Every refused candidate is logged with its reason and its SHAP explanation, creating a counterfactual dataset.
5. **Cost-adaptive selectivity.** The trade hurdle is computed from the live Kraken fee tier, so the system is stricter when the account is small and loosens automatically as the tier improves.
6. **Alpha, not profit.** Models are promoted on returns that survive subtracting benchmark exposure and a multiple-testing haircut.

```

A second, one-paragraph form written for a reader outside the project, `docs/PROJECT-STATE.md` §1 (lines 15–25):

*Verbatim from `docs/PROJECT-STATE.md`, lines 17–25:*

```markdown
ACSOE is a fully automated spot trading system for Kraken, built as a Master's dissertation
project. It streams and records market data for every Kraken pair, builds 15-minute candles
from that stream, computes a tradable universe from live pair rules and the current account
balance, picks one candidate per decision bar, and puts that candidate through a chain of
independent gates. It buys only when the expected move beats every cost with a configured
margin to spare, holds with a profit target, a stop and a timeout, and records both the
trades it took and — equally — every candidate it refused, with a machine-readable reason.
It is long-only, spot-only, single-exchange, and runs in paper mode by default behind three
independent switches that must all be thrown before a real order can reach the exchange.
```

### B.2 The invariants

The fourteen trading invariants are `context/trading-invariants.md` in full (381 lines). Reproduced verbatim so the report's quotations can be checked against one copy:

*Verbatim from `context/trading-invariants.md`, lines 1–381:*

````markdown
# Trading Invariants

These rules protect real money. They outrank tests, deadlines, convenience, and your own judgement.

**If a gate blocks something and a test fails, the test is wrong.** Never weaken, disable, comment out, add a bypass flag to, or delete a gate to make anything pass. If you believe an invariant is incorrect, stop and escalate to the lead. Do not edit it yourself.

## 1. Live trading requires three independent switches

Implemented in `platform/live_guard.py`, owned by Agent A, and called once at startup and again whenever mode is read. All three conditions must be true, or the system runs in paper mode.

They are three independent *conditions*, not three read paths — reading all three through the config layer is correct and does not violate the environment-variable rule.

1. Environment variable `ACSOE_LIVE=1`
2. Config field `mode: live`
3. A file at `config/LIVE_CONFIRMED` whose contents equal `context.now` in UTC formatted `YYYY-MM-DD`. Compared against the injected clock, never a direct clock read.

The default in every config file, every test fixture, and every example is `paper`. No code path may promote paper to live implicitly. Any missing, malformed, or stale switch means paper.

## 2. Nothing is hardcoded that the exchange can tell us

| Value | Source |
|---|---|
| Maker and taker fee | `POST /0/private/TradeVolume` |
| `ordermin`, `costmin`, tick size, decimals | `GET /0/public/AssetPairs` |
| Balances | `POST /0/private/Balance` |
| Spread | Live order book |

There is no hardcoded fee, minimum, tick size or precision anywhere in the codebase.

**A cache stale beyond its TTL counts as a failed fetch, and is retained anyway.** Those are two rules sharing a word, and collapsing them into one breaks the kill switch:

- *For trading*, a stale value does not exist. It may never price a hurdle, size a position, or satisfy a gate. That is all "counts as a failed fetch" means.
- *For an emergency liquidation*, it is the last thing the system knows, and knowing it beats being stuck. `clients/kraken/` **retains the last successful balances and the last successful `AssetPairs` metadata** — exactly what rule 14 authorises using, and nothing else — with the timestamp each was fetched, and never discards them on a failure. Only rule 14 may read them.

**Spread and the fee tier are deliberately not retained.** Their only possible reader is the cost gate, and the paper-mode table below says in as many words that an assumed spread invalidates that gate. A retained stale spread would be a loaded gun pointed at the one input that must never have a fallback, and a liquidation does not need it: it sells as a taker at whatever the book is, having already decided that getting flat beats getting a good price.

Discarding on failure would make rule 14 unimplementable at exactly the moment it is needed, so retention is a requirement on Agent A's client, not an optimisation.

### What a failed fetch does, by mode

**In live mode, a failed fetch always blocks.** Blocking is the correct response to not knowing a cost. The single exception is an emergency liquidation under rule 14, which must be able to complete during the outage that triggered it. Nothing else below applies to live mode.

**In paper mode**, so that a fresh clone with an empty `.env` can still start, run its loop, record market data and build candles:

| Failed fetch | In paper mode |
|---|---|
| Fee tier | Block that pair. No fallback — see below |
| Balance | Read from the **paper broker**, the authority on its own cash — see below. If the broker cannot answer, **block**. No fallback — not to `paper.starting_balances`, not to anything (operator ruling 2026-09-16) |
| Pair rules | Block that pair. No fallback — a wrong `ordermin` produces invalid orders |
| Spread | Block that pair. No fallback — an assumed spread invalidates the cost gate |

**Every row blocks. There is no paper-mode fallback left in this table.** Paper mode differs from live in one respect only: the balance comes from the paper broker rather than the exchange. When the broker cannot answer — for example a fill is due and the fee tier needed to charge it did not return — that is a failed fetch like any other, engine 1 publishes no balance, and every consumer refuses on the absence.

**The last fallback was removed by the operator on 2026-09-16.** Engine 11 `risk`, finding no published balance in paper mode, used the raw `paper.starting_balances` config map — unadjusted by any fill — in its invariant 6 affordability check. After one executed fill that check would approve a second candidate against 5,000 the account no longer holds. The branch was unreachable, because engine 7 excludes every pair when the balance is absent and stops the chain first; **that was the wrong reassurance**, since it made engine 7's handling load-bearing for an invariant engine 7 does not own. The branch's own docstring deferred the fill adjustment to Phase 6, and Phase 6 put the ledger in the broker instead, so what remained was a second answer to the account question, and the wrong one. Engine 11 now blocks on an absent balance, as it does on every other missing input.

### The paper ledger, ruled by the operator 2026-09-16

**In paper mode the balance is always the paper broker's: its opening `paper.starting_balances` adjusted by every fill the broker has executed — whether or not the real `Balance` fetch succeeded, and whether or not engine 19 has recorded the fill yet (amended 2026-09-16, below).** It is served by the paper broker in `clients/paper/`, so the mode difference stays in the client layer and no engine branches on mode to get an account.

The row above used to promise a fallback "adjusted by simulated fills" that fired only on a *failed* fetch, and **nothing implemented the adjustment**. Two consequences, both found in Phase 6 planning before any position existed. A simulated fill never touches the fetched cash, so engine 11 would size a second position against cash the first had already spent — invariant 6 says never allocate cash the account does not hold. And engine 19's equity is cash plus positions value, so the same cash was counted twice, in the series that moves the drawdown threshold engine 17 freezes on.

With real credentials in paper mode the fetch *succeeds* and returns the real account's cash, which no simulated fill spends either. A fetched balance plus simulated fills describes no account that exists, which is why the ledger is unconditional in paper rather than a failure path. Live mode is unchanged: it reads the exchange, and a failed fetch blocks.

**Amended by the operator 2026-09-16 — *when* a fill enters the ledger.** **The broker's reported balance includes every fill it has executed, including fills engine 19 has not yet recorded.** The broker is the authority on its own cash: a fill it has executed is money it has spent, whether or not the store has caught up. The ruling as first written — the ledger adjusted by every fill *the store has recorded* — is superseded on exactly this point, and the paragraph above already states the amended form.

The operator records the amendment as their own, and names the gap: the original ruling said what the balance is adjusted *by* and not *when*. The broker decides a resting entry's fill when engine 21 asks for it, part-way through a tick, and engine 19 records it at the end of that tick; a balance counting only recorded fills therefore lagged the broker's own knowledge by one tick. Engine 21 counts a position opened by this tick's fill in the portfolio value — correctly, since a live exchange's fetched balance already reflects a fill that printed before the tick — so on the fill tick paper equity counted the notional twice: once as unspent cash and once as the position. `peak_equity` took the inflated figure, engine 17 read a 40% drawdown the next tick and froze the account, and every later tick stayed frozen. **Every paper trade would have frozen the account.** Found by A's spec 87 rehearsal; see the tracker.

**The criterion that would have caught it is now required**: equity on the fill tick equals equity on the tick before it, within the fill's own cost, proven capable of failing by breaking the broker so the fill is excluded.

**The store remains what a restarted daemon rebuilds the ledger from.** A fill the broker executed and the store never recorded — a process that died between the two — must be absent from the rebuilt ledger *and* from the rebuilt positions, so the two still agree; the fix must prove that rather than assume it.

**A fallback's legitimacy is per-reader, not per-key.** The row above licenses the balance on one stated ground — a fallback is only legitimate where the value it stands in for cannot change the answer to *"can this trade pay for itself"* — and that test is applied to **the reader**, not to the key. Engine 11 `risk` sizing a position satisfies it. Engine 9 `order_book` does **not**: there the balance *is* the basis notional, the basis notional sets how deep the walk goes, the walk sets the estimated slippage, and slippage is one of the four terms of `friction`. A stood-in balance would therefore price the hurdle, which is the one thing this rule forbids. So engine 9 omits its estimate and publishes `no_quote_balance`, and engine 10 — a gate — refuses on the absent key.

Two engines reading one key and answering differently is not an inconsistency to tidy away; it is this rule working. Raised by C-models while building engine 9, Phase 6, 2026-09-16, and recorded here rather than in that engine's README so the next reader of a fallback applies the test to their own use of it. The same shape as the config rule in `code-standards.md`: the landing order is universal, the resting state is per-reader.

**The per-reader test above is now moot for the balance**: no reader substitutes one. Engine 11's use of it was removed on 2026-09-16 (above) — not because the test was misapplied to engine 11's sizing, but because the branch also fed the affordability check, and asking *what the branch would do if reached* rather than *whether it could be reached* is what found that. The principle stands for any future fallback: judge it by its reader, and judge the reader by every answer the substituted value touches.

**A ledger balance is not recorded as a fallback fired.** It is what the account *is* in paper mode, not a substitute for something that failed, and the run's mode already says every figure derived from it is simulated.

**The fee-tier row named a tier and told the system to ~~assume~~ it. That is retired, 2026-09-10.**
It was never implementable.
`AssetPairs` carries no fee schedule, so there was no runtime source the named tier could be read from,
and the only way to honour the row was to write a fee percentage into the code — which is the hardcoded
fee `AGENTS.md` forbids in its first paragraph, and which would be stale the day it was written.
A fee nobody fetched invalidates the cost gate for exactly the reason a spread nobody measured does:
both are terms of `friction`, and a gate priced on a guess is not a gate.
**A confirmed pair with no fee data blocks that pair.**

*The retired wording is deliberately not quoted here.* `scripts/verify.py`'s `docs_vocabulary`
criterion carries a row for it, qualified so it only fires on a line that also tells the system to
assume one — and a quotation of a defect is the one thing that will always look exactly like the
defect. `context/ai-workflow-rules.md`'s own retired-vocabulary section is the one place licensed to
name it, because cataloguing superseded things is that section's whole job.

The consequence, stated plainly rather than left to be discovered: with an empty `.env` the private calls fail, `TradeVolume` returns nothing, and **every pair blocks at the cost gate**. A fresh clone still runs the loop, still records the order book, and still builds candles — which is what the recording exists for and cannot be recovered later — but it takes no paper trades and produces no rejection rows past the cost gate. That is the honest description of an unauthenticated clone, and it is preferable to one that generates a research dataset priced on a fee somebody guessed.

Every decision affected by a fallback records which fallback fired. A fallback is never optimistic: it may only make the system less willing to trade.

Since 2026-09-16 no paper-mode fallback remains, so the rule above binds only rule 14's liquidation, which is the one place in this document where a stale value is used. A failed fetch blocks in paper mode exactly as in live.

### In replay mode: declared scenario inputs, ruled by the operator 2026-09-19

**Replay mode may read a declared fee scenario and a declared book. Paper and live may not, and
nothing above relaxes for them.** The historical archive holds trades only: no `TradeVolume`
response, no spread and no book were ever recorded for it. So a replay of it can price the cost
gate only from inputs somebody declared. The operator ruled that those inputs are permitted **in
replay mode only**, as follows:

- **The fee** comes from a committed scenario fixture carrying its source URL and capture time:
  Kraken's published schedule, fetched 2026-09-19
  (`tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`). It is served at one tier per run
  through the `TradeVolume` surface of the replay client (`clients/kraken/`, spec 129). An absent
  fixture or tier is a failed fetch, and engine 10 blocks exactly as it would live.
- **The spread and depth** come from the declared liquidity-bucket table (spec 130;
  `docs/dataset/phase-7-findings.md` §3). The replay client serves it as a synthetic book around
  the last traded price, and engine 9 walks that book with its own arithmetic. Every pair takes its
  bucket's value, recorded or not. A pair with no recent trade has no quote, never a zero spread.
- **They are declared inputs to an offline experiment, never a fallback.** Nothing substitutes
  them for a failed fetch; they are what a replay run is *defined* on. **Every run records their
  identity**: the `runs` row carries the scenario digest and description (spec 134), and every trade
  and rejection reaches it through its `run_id`.
- **Enforced by a test, not by convention.** The replay client refuses construction outside replay
  mode, and a Phase 7 criterion proves both that refusal and that no module outside the replay
  client imports the scenario fixtures (spec 141, `fee_scenario_is_replay_only`). The daemon
  refuses to start in replay mode.
- **The account's own tier is a different thing.** It is a recorded fact (tier 1, measured
  2026-09-19; see the tracker). Tiers 3 and 5 in the Phase 7 simulation are scenarios.

The paper-mode rules above do not move by a word.

## 3. Every gate is fail-closed

A gate that errors blocks. A gate that cannot reach its data blocks, subject only to the emergency liquidation in rule 14. A gate that returns an unparseable result blocks. Absence of a "no" is never a "yes".

Gate engines: 4 (data guard), 7 (scout), 10 (cost), 11 (risk), 13 (anomaly), 15 (skeptic), 16 (decision), 17 (safety).

**Engine 16 `decision` became a gate by operator ruling 2026-09-16.** It blocks on exactly one
condition, and the condition is deterministic arithmetic over `state`: **every approving engine
judged *this* tick's candidate** — the same pair engine 7 chose and the same decision bar. A pair
disagreement, a payload carrying a previous bar, an absent input where the chain says the engine
ran, or an approval carrying no quantity all block. Its other work — composing the order intent
engine 18 reads — is composition, not decision, and its README says so in those words.

## 4. No model output may bypass a gate

No confidence score, probability, ensemble weight, or router decision may skip, soften, or override engines 4, 7, 10, 11, 13, 16, or 17. A model may never cause a trade that a gate would refuse, and may never soften, bypass or override a gate's verdict. A model's output may order candidates for examination, provided every gate judges the chosen candidate independently and no gate's verdict is influenced by the ordering. Ordering changes which candidate is examined, never whether an examined candidate is approved.

*Amended by the operator 2026-09-19* to permit engine 7 to rank by engine 8's expected move. The
sentence it replaced said a model may only ever make the system less willing to trade, never more.
The ranking raises trades from 3 to 46 at tier 3 with the net unchanged at roughly zero. **It was
amended to obtain a sample large enough to measure rather than a more favourable result, and had
the net moved from negative to positive the operator would have treated that as a warning and not
amended.** The evidence and the residual circularity are `docs/dataset/phase-7-findings.md` §R.2
and §R.9; the implementation is spec 144.

Engine 16 joined that list with its gate status on 2026-09-16: it contains no model — its check is
a comparison of pair names and bar timestamps — so nothing a model publishes may override it.

Rule 14 describes the one override in the system. It is not a model output, and it moves the system towards less exposure, so it does not weaken this rule.

**Engine 7 `scout`'s universe filter is deterministic and is protected.** The filter is arithmetic over `ordermin`, `costmin`, tick size, live spread and balance. It contains no model, so nothing may override it. **Its ordering reads the predictor's output** (amended 2026-09-19, above). With `scout.rank_feature: expected_move` it examines the filtered universe in descending order of engine 8's expected move. It skips pairs with an incomplete vector, and pairs the anomaly or DI gate would refuse, using the same artefacts and the same shared arithmetic in `modelling/`. Engines 13, 8, 10, 11, 15 and 16 then judge the one chosen pair from scratch, exactly as before. Without the key, it orders alphabetically, which is the Phase 7 baseline. A failure to score is `scout_inputs_unavailable`, and a ranking value never blocks.

Gate 13 `anomaly` and gate 15 `skeptic` are both machine-learned, and they are treated differently on purpose. Anomaly is unsupervised outlier detection over *market data* — velocity, volume, spread — and its output is a threshold on a distance. It judges whether the market is broken, not whether this trade is good, so it is a data-quality gate like `data_guard` and is protected. Skeptic is supervised meta-labelling over the *predictor's own calls* — a learned opinion about this specific trade. That is what makes it a model in the sense rule 4 means, and why it is excused from the list: "a model must not override it" is meaningless for a model. Both can only veto, never approve. Both remain fail-closed under rule 3.

## 5. A trade must clear the live cost hurdle

```
friction  = live_maker_fee + live_taker_fee + measured_spread + estimated_slippage
net_edge  = expected_move − friction
TRADE ONLY IF net_edge > hurdle_multiple × friction
```

`net_edge` is what you compute. The rule is the third line. They are not the same thing.

Friction assumes **maker on entry, taker on exit** — the worst realistic case, since a stop must always exit as a taker. Never assume a maker exit when sizing the hurdle, even though target exits may achieve one.

Reference values, for sanity-checking only — never for use in code:

- Kraken tier 1 (fresh account): maker 0.40%, taker 0.80%. Friction ≈ 1.25% round trip.
- Kraken tier 3: maker 0.22%, taker 0.38%. Friction ≈ 0.65% round trip.

Break-even win rate, given the +3% / −1.5% barriers: at tier 1 a win nets +1.75% and a loss costs −2.75%, so p = 2.75 / 4.50 ≈ **61%**. At tier 3 a win nets +2.35% and a loss costs −2.15%, so p = 2.15 / 4.50 ≈ **48%**.

## 6. Position sizing rules

- Risk per trade never exceeds the configured fraction of total account equity.
- A position smaller than the pair's `ordermin` or `costmin` is a **rejection**, logged with a reason. Never round up to meet a minimum.
- Never allocate cash the account does not hold in that pair's quote currency.
- One open position per pair. A configured maximum of concurrent positions across the portfolio.

## 7. Quote currency rules

All Kraken quote currencies are scanned, but:

- A pair is only executable if the account holds spendable balance in that quote currency.
- Crypto-quoted pairs (quote is BTC, ETH, or any non-stable asset) are **disabled by default** behind `allow_crypto_quoted: false`. Profit in such a pair is denominated in a volatile asset, which is a second directional bet the system did not choose to make.
- All PnL, equity, risk limits, and reporting are expressed in a single `base_reporting_currency`, converted at the trade timestamp.
- Fiat-quoted pairs carry FX exposure against the reporting currency. This must be recorded per trade, not silently absorbed into PnL.

## 8. Entry and exit rules

- Entry is always a **post-only limit** order (`oflags=post`). If it would cross the book, Kraken cancels it — that is the intended behaviour.
- If an entry order is unfilled after the configured window, cancel it and abandon the candidate. **Never chase with a market order.**
- That cancellation still happens while the manage chain is holding on a `data_guard` block. It is a decision about elapsed time, not about price: it reads `context.now`, needs no market data, and reduces exposure. The hold suppresses **exits**, never this.
- A `close_all` cancels every resting entry order immediately, regardless of that window, before positions are closed. An uncancelled post-only limit is not a position, so it survives a liquidation and can fill minutes later — re-opening exposure after the emergency stop was pulled. The kill switch is not complete until the book is clear of both.
- Exits on target may be maker. Exits on stop must be immediate and may be taker.
- Every order carries a `userref` for idempotency. Never place an order without checking whether that `userref` already exists.

## 9. Time is injected, never read

Engines receive `context.now` and must never call `datetime.now()`, `time.time()`, or equivalent. This is what makes historical replay faithful and what prevents look-ahead bias. A direct clock call inside an engine is a defect.

## 10. No look-ahead, ever

- A feature at bar *t* may only use data available at the close of bar *t*.
- Labels use future data by definition and may only exist in the training pipeline, never in the live path.
- Walk-forward folds are purged and embargoed; overlapping label windows must not straddle a train/test boundary.
- Any model fitted on data the live system would not have had is invalid, and results derived from it must be discarded.

## 11. Recorded data is immutable

Raw market recordings are append-only. Never edit, backfill, interpolate, or "clean" a recorded file in place. Corrections belong in a derived layer with the original preserved.

## 12. Rejections are logged before the pipeline stops

When a gate blocks, the memory engine still runs. A rejection that is not written to storage is lost research data and counts as a defect equal to a lost trade.

**The guard chain records every blocker, not just the one that stopped the pipeline.** The guard chain never breaks early, so two guards can block on the same tick — typically `data_guard` on bad data and `safety` on an account condition. `state["trading_blocked_by"]` holds the first, because that is what gates the opportunity chain, but engine 19 writes one `block_records` row per blocker with `is_primary` set on the first only.

Without that, a `safety` block co-occurring with a `data_guard` block would leave no trace in `block_records` at all, and this rule would promise more than it delivered. The command row `safety` writes is a record of the *decision*; the block row is the record of the *evaluation*, and research needs both.

**An engine that errored is recorded too, and it is the tick this rule most needs.** Ruled by the operator 2026-09-16. When an opportunity-chain engine returns `ERROR`, engine 19 writes a `block_records` row with `blocked_by` the engine's name, `status = 'ERROR'`, and `block_reason` the code `engine_errored` — **never a `reason_code` the engine did not produce.** A reason code is a decision the engine made; an error is the absence of a decision, and the two must not share a field. No `rejections` row is written for it, because no candidate was refused, and the rest of the tick — positions, orders, equity — is recorded exactly as on any other tick. `engine_errored` is mapped in `REASON_PROSE` in the same change that introduces it.

Before this ruling the tick was lost: contract rule 7 empties an erroring engine's payload, engine 19 refused to write a rejection with no `reason_code`, and it raised — so no rejection, no block record and no equity row were written. Each rule was reasonable alone. Found by A's spec 87 rehearsal, reachable only by running the chain end to end. A consequence stated rather than discovered: these rows carry `status = 'ERROR'`, so engine 17's error rate now counts opportunity-chain errors as well as guard-chain ones — which is what an error-rate breaker is for.

## 13. Secrets never enter the repo

API keys come from the environment only. Never logged, never committed, never written into config files, never echoed in error messages or console output. The web console holds no credentials and cannot place orders.

## 14. Emergency liquidation is the one deliberate override

Everything else in this document either makes the system less willing to act or, in engine 7's ordering (invariant 4, amended 2026-09-19), changes which candidate is examined without overriding any verdict. This rule is the single place where a verdict is overridden to make the system *more* willing to act, and it exists because **unknown exposure is worse than a bad fill**.

### When it fires

`close_intent` is set in exactly two ways: an operator presses Close all, or engine 17 `safety` escalates. **`safety` escalates on exactly one condition:**

- **A sustained data outage.** Once `data_guard` has blocked more than `safety.max_consecutive_data_blocks` consecutive ticks — default **15** — `safety` writes `close_all`. The manage chain holds exits while the guard is rejecting data, and a hold that never ends is a position carried indefinitely on data nobody trusts. Fifteen one-minute ticks is one full decision bar: long enough that a websocket reconnect never liquidates the account, short enough that nothing is carried through a second bar.

`safety` escalates only when there are **open positions or resting entry orders**. A resting post-only buy is exposure that has not happened yet; left on the book through a blackout it can open a position into a market the system has already declared untrustworthy.

**At the committed config a `safety` escalation can never find a resting entry, and a test says so.** `trading.entry_unfilled_window_s` (300s) is shorter than `safety.max_consecutive_data_blocks` × `timeframes.loop_tick_s` (900s), and invariant 8 cancels a stale entry even during a `data_guard` hold, so the entry is always gone before the escalation. The resting-entry clause above is therefore reachable only through the operator's own Close all, which is what `escalation_completes_during_outage` exercises. `test_a_resting_entry_is_cancelled_by_its_window_before_safety_could_escalate` in `tests/engines/test_safety.py` asserts that relationship from the config. **It forbids no change: if either value moves, the test firing is the notice that this clause has become reachable through an escalation and needs its own test.** Operator ruling 2026-09-17 (finding F1 of the overnight log).

### The drawdown and loss-streak limits freeze. They do not liquidate

Ruled by the operator, 2026-09-10. Breaching `safety.max_drawdown_pct` or `safety.max_consecutive_losses` makes `safety` write a **`freeze`** row, not a `close_all`. So does the error-rate limit. `close_all` is reserved for the data-outage escalation above and for the operator's own Close all button.

Freeze stops new positions while the manage chain keeps watching the open ones, and the operator decides whether to liquidate.

### A suppressed escalation never swallows a freeze that was independently due

Ruled by the operator, 2026-09-10. `safety` emits at most one command per tick and the more
severe action wins — but `close_all` has its own suppressions: it is not written when there is
no exposure to close, or when `close_intent` is already set. **When the winning action is
suppressed, `safety` emits the strongest action that is not suppressed**, rather than emitting
nothing.

Without this, drawdown plus a data outage on an account with no open position emits nothing,
while the drawdown alone emits `freeze`. More bad conditions would produce less action, which
is the wrong direction for a circuit breaker and is the one shape this rule exists to forbid.

The practical difference is *persistence*, not blocking: `safety` returns `BLOCK` on any tripped
condition either way, so the opportunity chain stops regardless. What was being lost is the
`frozen` mode itself — the console rendered a running system, and the block was re-derived every
tick instead of recorded once. A breaker whose state cannot be read is a breaker the operator
cannot act on.

Found by Agent B while implementing spec 42, against the literal spec, and escalated rather than
fixed: it is a change to what the breaker does.

**The distinction is what the condition is a statement about.** A drawdown or a losing streak is a statement about *past* trades: the data is trustworthy, the positions are being managed correctly, and the strategy is losing. Liquidating on that turns an unrealised loss into a realised one on the system's own authority, at whatever price the book happens to hold, and it does so at the moment the system has the least evidence it is reading the market correctly. A sustained data outage is a statement about *present* knowledge — the system no longer knows what it holds or what it is worth — and that is the case this rule was written for. Unknown exposure is worse than a bad fill; a known bad position is not.

An earlier version of this section listed the drawdown and loss-streak limits alongside the outage as escalation conditions. Engine 17 could not be built against it: the Phase 0 seed carries a breached drawdown, a breached streak, an open position and a resting order all at once, so under that reading the seeded drawdown liquidated the account while the Phase 3 exit criterion required it to freeze, and no fixture could satisfy both. The contradiction is what surfaced the decision.

### What it overrides

When `close_intent` is set the liquidation proceeds regardless of:

- **A `data_guard` block.** The manage chain normally holds when the guard rejects the tick's data, placing no target, stop or timeout exit. A liquidation is not held. The system stops reasoning about price quality and gets flat.
- **A failed fetch, in any mode.** This is the case that matters most and is the easiest to miss: a feed outage is what triggers the escalation, and the same outage is likely failing the balance and order-book fetches. If rule 2's live-mode block applied here, `close_all` would be blocked by the exact condition it exists to answer. During a liquidation, engines 21 and 22 may use the last known good balances and the cached `AssetPairs` metadata **past its TTL**. This is the only place in the system where a stale cache is acceptable.

  **The balance half of that authorisation is deliberately wider than the code.** Ruled by
  the operator 2026-09-18 (S1 of `docs/build-log/phase-6/overnight-decisions-2026-09-18-night.md`).
  Neither engine reads the retained balance: engine 22 sizes a liquidation from the
  `positions` row and reads only the retained `AssetPairs`, and engine 21 reads neither.
  The grant is kept anyway, so that an exit path which does need cash later — a
  quote-currency sweep, say — is already covered, and removing it can never happen
  invisibly to whoever needs it. **Reading it today would change what the liquidation
  does**, for two reasons the first reader must know. The paper ledger holds no base
  currency (`clients/paper/fills.py`, quote side only), so a liquidation capped at the
  account's base holding would sell nothing and retry forever, and `close_intent` would
  never clear. And in paper mode the retained balance is **the real exchange account's**,
  forwarded by the paper broker from the wrapped Kraken client, not the paper ledger's.

Constraints that still hold during a liquidation:

- Quantities are still rounded **down** using the cached `lot_decimals`. Rounding down leaves dust; rounding up produces an order Kraken rejects, and a rejected order during an emergency is worse than dust.
- Every order still carries a `userref` and is still checked for idempotency. A liquidation that double-sells is not a liquidation.
- The override applies only to exiting. It never permits an entry, and it never relaxes a gate for a new position.
- Every fetch failure tolerated under this rule is recorded on the resulting trade (`fallbacks_used`), so the fill is never mistaken for one priced on good data.
````

The eight architecture invariants (numbered 0–7) are `context/architecture-context.md` lines 291–300:

*Verbatim from `context/architecture-context.md`, lines 291–300:*

```markdown
## Invariants

0. `core/` holds contracts and the orchestrator and nothing else, and **imports nothing from the rest of the package**. `core/contracts.py` declares `Config`, `Clock` and `Clients` as `typing.Protocol`s; `platform/` and `clients/` provide the concrete implementations. That is what makes the lead-versus-A boundary work: the lead owns the shape, A owns the implementation, and neither writes in the other's directory.
1. Engines are stateless across cycles. All state lives in the `state` dict or the store.
2. Engines never call the network directly; they use injected clients.
3. Engines never read the clock; they use `context.now`.
4. Engines never import each other. Communication is through `state` only.
5. Research code never imports from the live loop path, and the live loop never imports from `research/`. This constrains `src/acsoe/` only. `scripts/verify.py` is neither — it is allowed to import both, which is how it checks the offline chain. **`modelling/` is the one package both sides import** (operator ruling 2026-09-12): it holds the arithmetic that must agree between live and replay, imports nothing from `acsoe` but `core/contracts.py` types, reads no `state`, opens no client and holds no engine, and a test walks its import graph to keep it that way.
6. Anything slower than the loop tick belongs offline, not in an engine.
7. Credentials exist only in the environment.
```

### B.3 The Locked Decisions

*Verbatim from `context/progress-tracker.md`, lines 1540–1624:*

```markdown
## Locked Decisions

Settled with evidence. Do not relitigate. Changing one requires the operator, not an agent.

- Kraken Pro, spot only. No margin, futures, leverage, or shorting.
- Fees read live from `TradeVolume`. Minimums read live from `AssetPairs`. Never hardcoded.
- Reference friction: ~1.25% round trip at tier 1, ~0.65% at tier 3.
- Break-even win rate: ~61% at tier 1, ~48% at tier 3.
- Decision bar 15 minutes; hold 2–12 hours; loop tick 1 minute.
- Triple-barrier labels: +3% / −1.5% / 48-bar timeout.
- Post-only limit entry, cancel if unfilled, never chase.
- Tradable universe computed per tick from `ordermin`, `costmin`, tick size, live spread and balance. No account-size thresholds.
- All Kraken quote currencies scanned; crypto-quoted pairs disabled by default.
- DI fitted on the predictor's training set, MinMax-scaled, rolling percentile threshold, 30-day per-pair window; its leave-one-out excludes every row within 48 bars across all pairs (operator, 2026-09-15).
- DI threshold crossings also feed the regime engine.
- Alpha attribution uses the full equity curve including cash periods, not trade windows.
- Execution offset bandit pooled by spread tier, not per pair.
- Promotion metric haircut for the number of models tried.
- Backtest training window is the 90 days **before** each test window and nothing after it — past-only, never two-sided; retrains weekly during walk-forward. Operator ruling 2026-09-12; the earlier wording *capped at a rolling 90 days* was read as two-sided and is retired.
- Decision bars before `dataset.decision_start_date` (2017-01-01) are excluded from the labelled dataset. A tradability exclusion, not a data-quality one: the 2013–2016 bars are real but describe a market no position could have been taken in. Operator ruling 2026-09-12.
- Every pair that clears the archive's two-year rule is in the dataset, thin ones included. `dataset.min_labelled_rows` is the per-pair floor, 0 today (no floor); a cross-sectional model may want one, and the decision is deferred behind that named knob. Operator ruling 2026-09-12.
- An LLM is not the predictor. Any alternative method must first clear the fee hurdle.
- Build order is structure, then interface, then backend.
- Console is built against the real schema with seeded fake data, so no rework when real data arrives.
- Paper mode until a validated model exists. A readiness gate, not an account-size gate.

### Lead rulings of 2026-09-12 for Phase 5, each confirmed by the operator the same day and overturnable by the operator only

- **Engine 20 `tournament` is Phase 5 work.** Its leaderboard is what engine 14 reads in Phase 6.
- **`src/acsoe/modelling/` is the one package both the live loop and `research/` import**, C-owned, so live and replay compute from one implementation. Invariant 5 in `architecture-context.md` says so.
- **Engine 8 `prediction` blocks on a DI refusal** under contract rule 6, reason code `di_refused`, publishing no `expected_move_pct`, and stays a non-gate in the registry. The alternative put the veto after cost and risk had already run on a distrusted prediction.
- **The evaluation number is the Brier of P(target) against the fold's base-rate Brier**, with log loss beside it and the BUY-call target rate against the break-even rates in invariant 5.
  Accuracy is never computed: the base rate is 23.89% and a model that always predicts `stop` is right 51% of the time. Retired as a term in `ai-workflow-rules.md`.
- **Rows are weighted by average uniqueness**, and the effective sample size is reported **per fold on the same line as that fold's row count** and in aggregate. Operator addition: a fold with 8,000 rows and an effective size of 300 is a fold whose numbers mean almost nothing, and an aggregate hides exactly that fold.
- **The DI reference set** is the predictor's training rows for the fold, per pair the last `prediction.di_window_days`, mean k-nearest distance, thresholded at `prediction.di_percentile` of the leave-one-out distribution, refitted each weekly retrain. **Amended by the operator 2026-09-15: the leave-one-out excludes every reference row within 48 bars (`backtest.embargo_bars`) of the row being scored, across all pairs, not the row alone** — 78 of the 117 DI columns are shared by every pair on a bar, so excluding the row alone left near-identical same-moment neighbours and the threshold measured time proximity rather than distributional distance. Spec 68, amendment.
- **Engine 7's ranking is a config-named feature**, `scout.rank_feature` with `scout.rank_descending`; alphabetical while absent, and the engine says so. The feature is ruled after spec 75's study reports. **Ruled 2026-09-19 (R1): engine 8's expected move, not a studied feature.** Spec 75 is resolved; see Open Questions, and spec 144.
- **`lightgbm`, `scikit-learn` and `shap` are base dependencies** from Phase 5; `hmmlearn` and `statsmodels` stay in the `research` extra.

### Operator rulings of 2026-09-12, recorded here so Phase 5 inherits them rather than asking

Context: the same day, the historical loader was pointed at the whole archive instead of
three hand-picked pairs — 234 USD-quoted pairs with at least two years of history,
20,443,861 bars — and the labelled dataset was measured over all of it. The measurement
surfaced three things the operator ruled on.

**RULING 1 — The walk-forward is past-only, not two-sided.** A fold trains on the 90 days
before its test window and nothing after it. What was built trained on 90 days on both sides
of the test window, which is purged cross-validation: legitimate for hyperparameter selection,
but it lets a model see data from after the period it is scored on, so it reports a number
better than the same model would achieve live and nothing says so. The project's goal is a
system that trades, so the validation must answer "would this have worked if I had been
trading it". **Applied:** `research/walkforward.py` now sets `train_end = test_start` and
counts every row after the test window in `Fold.after_test_count` rather than training on it;
the embargo moved to the training side of the boundary (the last `embargo_bars` before the test
window). The Locked Decision above was reworded, and the retired wording is now a
`docs_vocabulary` row. A new Phase 4 criterion, `walkforward_trains_on_the_past_only`, proves
on every rolling fold that no training row's decision bar or label window end post-dates its
test window, with mutation proofs in `tests/verify/test_phase4_criteria.py`. Measured effect on
the three original pairs: median training rows fell from ~17,175 to
~8,586, which is the ruling doing what it says.

**RULING 2 — Exclude decision bars before 2017-01-01.** The archive begins 2013-10-07 and the
earliest bars are single trades of 0.1 BTC in fifteen minutes. Those bars are real but describe
a market no position could have been taken in at any size, and a model trained on them will
learn patterns that do not transfer. **The exclusion is about tradability, not data quality.**
**Applied:** `dataset.decision_start_date: "2017-01-01"` in `config/default.yaml`, read by
`research/labelling.py` with no default (a null raises), applied in `label_series`, and
reported per pair as `LabelledSeries.excluded_before_start` and by engine 23 as
`excluded_before_start_by_pair`. **Cost, measured:** 92,791 labelled rows
removed (0.45% of 20,424,028), across the 6 pairs whose history
predates 2017 — XBTUSD 46,671, ETHUSD 25,973,
LTCUSD 10,411, ETCUSD 7,221, ZECUSD 2,724,
REPUSD 475. The dataset is 20,331,237 rows. Both figures are in
`docs/PROJECT-STATE.md` section 10 and `docs/dataset/`.

**RULING 3 — Keep the eleven thin pairs; add the floor as a named knob.** Eleven of 234 pairs
carry fewer than 20,000 labelled rows (TUSDUSD 4,659 and ETHPYUSD 4,812 the
smallest). They stay. `dataset.min_labelled_rows` is the per-pair floor, reads `0` today so
nothing is excluded, and engine 23 names any pair it leaves out in `pairs_below_floor`. A
cross-sectional model may want a floor; that decision is deferred with a named knob, not
overlooked. **One deviation from the ruling's letter, stated:** the operator asked for a
default of null. `platform/config.py` refuses every null key at load — null means OPERATOR
REQUIRED and stops the process, which is the right rule for a trading threshold and is
documented as deliberately not special-cased — so the absence of a floor is spelled `0`, with
the reason in the YAML comment and in `DatasetConfig`.
```

### B.4 The research question and the promotion bar, every occurrence

**"Research question" as a phrase does not occur** in `context/*.md`, `docs/*.md`, `docs/dataset/phase-7-findings.md`, specs 138/139/143 or the Phase 7 build logs (grep for `research question`, case-insensitive: no hits). The question is stated in these places, each quoted:

1. `context/project-overview.md` lines 45: "**A negative result is a valid result.** If the honest conclusion is that no net edge survives Kraken's fees at this account size, that is a finding, not a failure. The system must be built so it can report that truthfully."
2. `docs/PROJECT-STATE.md` lines 27–39: "The question it asks is deliberately not the usual one. Most trading research asks whether price can be predicted … ACSOE asks whether a prediction **survives the cost of acting on it**. … the interesting quantity is not whether a model beats a coin flip but whether its edge is still positive once friction, slippage, spread and a hurdle multiple have been subtracted from it first. … it makes a negative result a valid result".
3. `context/project-overview.md` line 7: "Its value is the rigour of the rejection machinery and the honesty of the evaluation, not the size of the profit."

**The promotion bar**, every occurrence as written:

1. `docs/dataset/phase-7-findings.md` lines 108–115 (R.4): "**R.4 The promotion bar is set before anything runs.** In the operator's words: *a model is promoted only if the lower bound of the 95% interval on net return per trade is above zero, after friction, on the deflated metric.* The operator expects nothing to pass it, and setting it in advance is the point. **Its working form was ruled on 2026-09-19 (R10b), as proposed:** the interval is computed allowing for overlapping holds, then widened for the number of trials, and a model is promoted only if the widened interval's lower bound is above zero. The operator notes that this is stricter than the original wording, which is correct. The exact statistics are fixed in spec 139 and committed as code with a worked example before any simulated figure exists."
2. `feature-specs/139-deflated-metric-and-promotion-gate.md` lines 45–62 (quoted in full in evidence pack 03 §C.2): "**The bar, RULED 2026-09-19 before anything runs (R10). … Promote only if** `mean − q × SE_HAC > 0`. With fewer than ten trades there is no interval, the model is not promoted, and the reason code says why."
3. `src/acsoe/modelling/promotion.py` lines 11–36 ("## The bar, as ruled") and lines 385–433 (`promotion_verdict`), quoted in pack 03 §C.2.
4. `context/progress-tracker.md` Locked Decisions line 1553: "Promotion metric haircut for the number of models tried."
5. `context/glossary.md` line 65–67: "**Alpha** — what is left after subtracting beta. The only number that matters for promotion." / "**Deflated metric** — a performance score haircut for the number of models tried, so that picking the best of twenty is not mistaken for skill."
6. `context/ai-workflow-rules.md` line 137 (the Phase 7 row): "promotion gate rejects a model whose edge does not survive the trial haircut".
7. `docs/dataset/phase-7-findings.md` lines 687–710 ("What the promotion bar can find at these trade counts: expected to be unreachable"), quoted in B.5 below.

### B.5 The pre-registration section and the six FINAL sections

**The pre-registration section** is `docs/dataset/phase-7-findings.md` §7b, "Stated before any simulated figure exists (written 2026-09-19, before launch)", lines 669–821. Its opening sentence: "Everything in this section was written before either run began, so none of it was chosen after a result was seen."

*Verbatim from `docs/dataset/phase-7-findings.md`, lines 669–821:*

```markdown
## 7b. Stated before any simulated figure exists (written 2026-09-19, before launch)

Everything in this section was written before either run began, so none of it was chosen after a
result was seen.

### The three-month window: chosen constraints, with their cost

1. **Three months and 13 retrained models, not six and 26.** The claim that the system was tested
   across weekly retraining rests on 13 retrains and one season.
2. **The window sits inside a strong directional market** (§6a), and three months narrows that
   warning further. The alpha regression has **91 daily returns**.
3. **Expected trades: about 8–11 at tier 3 and 27–55 at tier 5.** Tier 3 is at or below spec 139's
   10-trade threshold, below which the promotion gate reports no interval, so **tier 3's result is
   descriptive.**
4. **The three-month cell was never measured offline.** Those estimates are scaled from the six- and
   twelve-month cells of §4 (22 and 46 trades at 0.60% fees), with a 3-in-4 entry fill rate taken
   from the rehearsal.

### What the promotion bar can find at these trade counts: expected to be unreachable

The bar is fixed (§R.4, spec 139): the lower bound of an interval widened by Bonferroni over **N =
1,679 trials** must exceed zero. The minimum mean net return per trade that could clear it is
`q × SD / √n`. Here `q` is the committed code's Student-t quantile at confidence `1 − 0.05/N`, and SD
is the per-trade standard deviation of the §4 expected-move cells (about 2.2–2.3%). HAC can only
widen the standard error, so these are lower bounds:

| Tier | Expected n | q | Minimum mean net return per trade |
|---|---|---|---|
| 3 | 10–11 (fewer gives no interval) | 7.71–7.19 | **4.9–5.5%** |
| 5 | 27–55 | 5.05–4.56 | **1.35–2.14%** |

- **Tier 3 cannot clear the bar.** The required mean exceeds the net return of a single target exit
  (about +2.3% after tier-3 friction), so no possible mix of outcomes reaches it. The only exception
  is a degenerate run in which every trade returns the same amount.
- **Tier 5 cannot plausibly clear it.** Ignoring timeouts, it needs a target-hit rate of roughly 76–94%.
  The skeptic's survivors hit targets at 0.39–0.58 (§5), and the expected-move cells net −0.26% to
  −0.17% per trade (§4).

**So a non-promotion is the expected outcome of this design, not a finding about skill.** It follows
from the trade counts and the pre-registered trial count. The run's value is its record (the funnel,
the approvals and refusals with every gate's numbers, the equity curve against both benchmarks), not
a promotion verdict.

### The trial count

**N = 1,679, pre-registered** (`docs/dataset/phase-7-trial-ledger.json`). It is built by a script
from the committed outputs, counting every configuration ever evaluated on the out-of-sample data.
The ledger counts **four** Phase 7 runs (two rankings at two tiers, as first planned). **Two run**, so
the ledger **overcounts by two, deliberately, in the harsher direction**. N is not changed after any
figure exists.

### The benchmarks

- **BTC/USD buy-and-hold** over the run's own window.
- **An equal-weighted basket of the pairs the run held, while it held them, cash otherwise** (R8).
- **Two secondary baskets, computed after the run from stored data:** the held pairs bought and held
  over the whole window, and the equal-weighted universe.

**No claim is made that any of these is the standard benchmark in the crypto backtesting
literature.** No source was verified for such a claim.

### Measured before the run, and stated with their limits

- **F4, the capped skeptic against the predictor's own confidence, in the simulation window.** Over
  1,237,399 out-of-sample BUY calls (folds 379–404), the capped skeptic at 0.50 passes 8.38%
  (about 103,700 calls) at a target rate of 0.3935. The same number of calls taken by the
  predictor's own `p_target`, per fold, reaches 0.3953.
  - The difference, 0.0018, is about 0.8–1.2 standard errors under an independent-binomial
    approximation. The two sets overlap heavily and share 48-bar label windows, so the true band is
    wider.
  - **Stated as: no detectable difference.** Not "the skeptic adds nothing". No formal test was run.
  - The uncapped skeptic did beat the same comparison over all 405 folds (+0.058, §5b).
  - Source: `docs/build-log/phase-7/c-interface.md` (c-models).
- **F6, a train/serve skew in the features of unmoving pairs.** Engine 5 over 200 published bars
  yields exact zeros where the training dataset carries floating-point residues.
  - **Measured** (c-models, all 2,216,920 out-of-sample rows of folds 379–404 re-scored with the
    residues zeroed): 12 columns affected; 23,155 rows carry a residue; the expected move changes on
    2,308 rows, by at most 0.453 pp. **No complete row crosses a cost bar of 1.25% or above.** The
    measurement assumes live yields exactly 0.0 wherever the dataset has a residue.
  - **Calculated, not measured:** the lowest cost bar the simulation can apply, 2.5 × friction in the
    most liquid bucket, is **about 1.30% at tier 5** and **about 1.67% at tier 3**. This is arithmetic
    from the declared table and the fee schedule.
  - So F6 can change which pair is ranked first, and **cannot change a cost verdict.** The run matches
    what the live daemon computes; it is the training data and the offline grids that carry the
    residue.
- **F5, the target exit.** A target exit sells at market on the next minute's tick, as built. In the
  rehearsal, one target exit realised +2.0% where the label books +3.0%. **The run's realised returns
  on targets are expected to sit below every offline grid in this document**, because the grids use
  the label's +3.0%. The run measures the exit rule as built. Changing it now would be changing the
  system to help it pass its own test.

### How the runs were run: two facts stated before launch

- **An intermittent native fault, and resumes.** The gating rehearsal on the final code
  (`19c5a11`) crashed once, 2026-09-19: an access violation in polars' row export to Python
  (`export.rs:59`), 54 ticks into the day. Two identical reruns of the same span on the same code
  ran cleanly, so the fault is not deterministic.
  - **By operator ruling**, a watchdog resumes a run whose process has died, with its exact
    command plus `--resume`. It never touches a live one.
  - **A resume does not change the result.** The rehearsal's kill-and-resume check shows a
    resumed run writes the same rows as an uninterrupted one.
  - **Every resume is recorded** (run, tick, time, number), and **the count per run is reported
    with the results.**
  - **An A/B test decided that SHAP stays in.** A second rehearsal also crashed, in engine 3's
    candle build, a different polars entry point. The operator then fixed a decision rule before
    any result, and the same full day ran four times at the commit without the SHAP writer
    (`3efe958`) and four times at the launch commit (`19c5a11`), in parallel. **Neither arm
    crashed** (1,700 ticks each). **That exonerates nothing.**
    - At the observed rate on the launch commit (2 crashes in 3,531 ticks, about 1 in 1,765),
      each arm expected about 0.96 crashes.
    - Zero in one arm has a probability of about 0.38. Zero in both, if the rates were equal,
      about 0.15. So zero in both is ordinary whether or not the writer is implicated.
    - What the A/B established is that **the rate is lower than the first estimate** (1 in
      about 900 ticks): low enough to launch on, not low enough to clear anything.
    - For comparison: 0 crashes in 5,988 ticks on earlier code.
    - The two crashes faulted in two different Windows modules, with no hardware errors logged.
      That is consistent with heap corruption, and leaves the machine as suspect as the library.

    **By the pre-set rule, the runs launch with SHAP**, with the watchdog allowed up to 40
    resumes per run and 8 per hour. The loop detector is unchanged: two consecutive resumes
    dying at the same tick stop a run.
- **The loss-streak breaker trips correctly; its recovery path does not exist.** Found by running
  the system on 2026-09-20, not by reading the code: the tier-5 run froze on `loss_streak` at
  2024-10-20 05:30Z, after five consecutive stops, and stayed frozen for the rest of the window.
  - **What the check measures, correctly:** `safety._loss_streak` counts a **consecutive** streak
    — losses counted backwards from the most recent closed trade until any non-losing trade
    breaks the run — **not** a running total. A single winning closed trade resets it to zero,
    however many losses came before. That is the intended rule, implemented correctly.
  - **What it cannot do:** it **recomputes from trade history every tick and holds no state.** It
    has no reference to the system mode, the `commands` table, or any clear event. So **an
    operator reactivation cannot reset it**: the same five losses are counted again on the next
    tick and the freeze re-trips.
  - **The gap is the recovery path.** The intended behaviour is that clearing a freeze starts a
    **fresh** streak — the operator has seen those five and decided to continue, so the system
    should count from zero and freeze again only on five new consecutive losses. It cannot,
    because the count comes from history and history does not change. **The fix:** record the
    clear's timestamp and count only losses closed after it. Phase 8; not changed during the runs.
- **One launch precondition was judged met by hand, and is declared here rather than left
  silent.** The gating rehearsal's `kill-and-resume identical` check was false. The cause is the
  check, not the system: `rejections.shap_ref` embeds the writing tick's cycle number, and a
  resumed process restarts `cycle_id` at 1 by design. The harness excludes `cycle_id` and
  `run_id` as columns, but not the copy of them inside that path.
  - **Evidence, in all five gating rehearsals:** with `shap_ref` excluded, **every table is
    byte-identical** between the uninterrupted run and the killed-and-resumed one, and the 71
    SHAP refs match one for one once the run and cycle segments are ignored.
  - So a resume changes no decision, and the operator ruled the precondition met on that
    evidence. Every other precondition was met by the committed check script. Correcting the
    harness's exclusion rule is a Phase 8 item.
- **Each run's first decision bar is skipped by design.** On a fresh database engine 7 has no
  stored equity to size positions against until engine 19 writes the first row at the end of
  tick 1. Engine 7 fails closed rather than fall back to a balance, so it blocks tick 1
  (`scout_inputs_unavailable`). That is one bar per run, 2024-10-05 00:15Z, the same at both
  tiers.
```

**The six findings marked FINAL** ("Findings the simulation will not change", §10, lines 853–866) and each section's own text:

*Verbatim from `docs/dataset/phase-7-findings.md`, lines 853–866:*

```markdown
## 10. Findings the simulation will not change

- **The tier-1 proof (§2).** Structural: the calibration and barriers cap the expected move at
  3.0%, and the gate needs strictly more. The observed 2.9999999930% corroborates it.
- **The spread inversion (§3).** A constant spread made thin-pair trades look profitable; a
  liquidity-dependent spread removed the gain.
- **Alphabetical ordering's concentration (§4).** One pair on 56% of bars.
- **The capped against uncapped skeptic (§5a)**, and the 2026-09-14 sweep for the skeptic it
  measured (§5b).
- **The overconfidence of cost-clearing calls over the full span (§6).** +0.32% realised against at
  least 1.50% expected, **with its caveat (§6a)**: about +0.25% before 2024 and about +1.2% in 2024.
- **The fee schedule (§R.3).** The figures, and the fact that nothing dates a schedule before 9 July
  2026.
```

(i) §2 "Tier 1 is provably zero. FINAL." lines 311–329:

*Verbatim from `docs/dataset/phase-7-findings.md`, lines 311–329:*

```markdown
### Tier 1 is provably zero. FINAL.

**The primary proof is structural, not observed.** At tier 1's fees (0.40% + 0.80% = 1.20%, the
fetched schedule and invariant 5 agreeing), the cost bar is 2.5 × 1.20% = **3.0%** before any
spread or slippage, and spread and slippage only raise it. The expected move is

`p_target × 3.0% − p_stop × 1.5% + p_timeout × m`,

where `m` is the fold's mean timeout return. The calibrated probabilities are renormalised to sum
to one (`modelling/calibration.py`, `apply_calibration`), and `m` lies between 0.17% and 0.54% in
all 405 fold manifests. So the expected move is a weighted average of 3.0%, −1.5% and `m`, and can
never exceed 3.0%. The gate needs it to be **strictly greater** than 3.0%, so no candidate at tier 1
can clear, whatever the market does and whatever the model learns. This holds for any model the
calibration and the barriers allow, not only the 405 trained.

**Corroboration, observed.** Over all 15,978,803 out-of-sample rows, the highest expected move the
model produced is **2.9999999930%** (`outputs/2026-09-18_q_em.log`): at the bound, and never past
it.
```

(ii) §3 "The spread inversion. FINAL, as the offline comparison it is." lines 332–421:

*Verbatim from `docs/dataset/phase-7-findings.md`, lines 332–421:*

```markdown
## 3. The spread inversion. FINAL, as the offline comparison it is.

**The finding.** A single constant spread applied to every pair produced a positive and, in three
cells, nominally significant return per trade. A spread that depends on each pair's liquidity,
applied to the same candidates, produced returns consistent with zero and slightly negative. **The
simpler assumption inverted the sign of the point estimate** in seven of the eight matched cells
that traded.

**The arms.** Both arms rank by `log_return_4` ascending, use the capped skeptic at 0.50, and
apply one position per pair with at most three open. They differ in one respect:

- **Flat:** tier fees plus a constant 10 bps of spread for every pair, no slippage (`q_funnel.py`).
- **Bucket:** tier fees plus a spread and a slippage looked up from the pair's trailing 24-hour
  dollar volume, using the declared table below (`q_bucket.py`).

The bucket arm therefore also adds slippage. Slippage is a liquidity cost of the same kind, and the
table shows it scales with the same volume buckets.

| Fees | Window | Flat 10 bps: trades, net per trade | Bucket table: trades, pairs, net per trade |
|---|---|---|---|
| 0.60% | 6 months | 18, +0.55% ± 1.04% | 0 |
| 0.60% | 12 months | 24, +0.43% ± 0.91% | 3, 3 pairs, −0.67% (interval not meaningful) |
| 0.60% | 18 months | 28, +0.53% ± 0.83% | 3, 3 pairs, −0.67% (interval not meaningful) |
| 0.50% | 6 months | 48, +0.43% ± 0.64% | 12, 10 pairs, +0.06% ± 1.34% |
| 0.50% | 12 months | 65, +0.39% ± 0.55% | 23, 17 pairs, −0.19% ± 0.93% |
| 0.50% | 18 months | 79, +0.29% ± 0.50% | 26, 20 pairs, −0.25% ± 0.87% |
| 0.40% | 6 months | 102, **+0.51% ± 0.44%** | 36, 22 pairs, −0.32% ± 0.72% |
| 0.40% | 12 months | 147, **+0.49% ± 0.36%** | 58, 35 pairs, −0.03% ± 0.58% |
| 0.40% | 18 months | 197, **+0.36% ± 0.31%** | 71, 42 pairs, −0.15% ± 0.52% |

Sources: flat, `outputs/q_funnel.out` (rows `log_return_4 asc`, `cap@0.50`, at total friction =
fees + 0.10%); bucket, [T] `q_bucket.py`. **Bold** marks the flat cells whose interval excludes
zero. No bucket cell's interval excludes zero.

**Where the positive result came from.** Take the flat arm at 0.60% total friction over 12 months:
65 trades. **Only 11 of them are on a pair the recorder measured.** Those 11 pairs' recorded median
spreads are 24.7 bps at the median and up to 127.4 bps, against the 10 bps the flat arm charged
them. Those 11 trades netted −0.05%; the 54 on unrecorded pairs netted +0.48% ([T] `q_picks.py`).
The most-traded pairs were BSXUSD (13 trades), HDXUSD (10), STORJUSD (4) and CQTUSD (4), all thin.
The ranking favours the pair that fell furthest over the last four bars. On a thin pair that is
often a print at the bid, which later prints at the ask repay. That gain is the spread itself, and
the flat constant did not charge it. **The positive result came from pricing thin pairs as if
they were liquid.**

**The declared table** (bps; the median of per-pair medians in each bucket, with the interquartile
range across pairs). Source: [T] `q_bucket.py`; per-pair values from `q_depth.py`.

| Pair's trailing 24-hour volume | Recorded pairs | Spread | Spread IQR | Slippage at $5,000 |
|---|---|---|---|---|
| under $10k | 16 | 30.4 | 12.2–36.0 | ~17.7 |
| $10k–$100k | 49 | 25.8 | 11.2–39.2 | ~20.8 |
| $100k–$1M | 84 | 12.3 | 7.2–19.4 | ~7.5 |
| $1M–$10M | 36 | 5.5 | 2.7–9.4 | ~1.7 |
| over $10M | 0 | *mapped to the $1M–$10M row* | | |

- Slippage is modelled as a book whose notional is spread evenly out to the recorded $10,000
  depth. On that assumption it is a quarter of the upper bound (depth to $10,000 minus half the
  spread), because engine 9 walks the whole quote balance ($5,000) rather than the position.
- No recorded pair exceeds $10M a day because BTC, ETH and SOL are recorded as full books rather
  than as summaries, so that bucket borrows the next one's values.
- The IQRs are wide, and they are the declared uncertainty of every value in the table.

**Coverage.** The recording holds 187 USD pairs for **7.4 days**, 2026-09-11 16:13 to 2026-09-19
00:45 UTC ([T] `q_spread_agg.py`). Of the archive's 231 USD pairs, **72 were recorded**; the rest,
including the alphabetical candidate 1INCHUSD, take their bucket's value ([T] `q_spread_extrap.py`).
Candidates by bucket over the 1.5 years, from the 0th (thinnest) to the 4th:

| Ranking | under $10k | $10k–$100k | $100k–$1M | $1M–$10M | over $10M |
|---|---|---|---|---|---|
| Alphabetical | 3,851 | 20,265 | 22,444 | 6,423 | 39 |
| `log_return_4` ascending | 3,557 | 18,431 | 23,924 | 6,501 | 609 |

**Why a fitted spread model was not used instead.** A regression of log spread on the five
predictors the archive can reproduce explained 84% of spread variance as differences between pairs.
It predicted a held-out pair's spread only to within a factor of 3.3 to 6.4 at 95%, or 3.1 to 4.2
for its average level. It backcast 1INCHUSD at 25 bps with a band of 7.7 to 84 bps, wide enough
that the cost gate's verdict would come from the model's error rather than the market ([T]
`q_spread_fit.py`, `q_spread_extrap.py`). The bucket table is a declared lookup, not a fitted model.
It gets the direction right (thin pairs cost more) without claiming per-pair precision the data
cannot support.

**Under the ruled ranking.** Both arms above rank by `log_return_4`, computed before §R.2. The same
flat-against-bucket comparison under expected-move ranking is **NOT MEASURED**. The finding stands
as a statement about the arms it names. That a constant spread flatters thin-pair trades does not
depend on which ranking produced the candidates.

**Why this is FINAL.** The inversion is a comparison between two spread assumptions over identical
candidates and outcomes. The simulation runs one arm, the bucket table, and does not repeat the
comparison. **SIMULATED VALUE PENDING:** the bucket arm's chain figures, which add entry fills.
```

(iii) §4 alphabetical concentration (the FINAL paragraph and the ranking table) lines 424–466:

*Verbatim from `docs/dataset/phase-7-findings.md`, lines 424–466:*

```markdown
## 4. The ranking comparison

**How much alphabetical ordering constrains the system.** Over the 1.5 years the alphabetical
candidate was **1INCHUSD on 29,857 of 53,022 bars (56.3%)** and AAVEUSD on 20,082 (37.9%). 17
pairs were ever the candidate, and six of them account for 53,009 of the 53,022 bars
(`outputs/q_window.out`, `outputs/q_funnel.out`). With a mean of 126.6 pairs present per bar,
**about 126 pairs per bar were passed over on their name alone.** FINAL: this is a property of the
ordering, not of the market.

**Trades by ranking**, all under the declared bucket spread and slippage, capped skeptic at 0.50,
one position per pair with at most three open. Sources: alphabetical and `log_return_4`, [T]
`q_bucket.py`; expected move and net margin, [T] `q_emrank.py`.

| Fees | Window | Alphabetical | `log_return_4` ascending | Expected move | Net margin |
|---|---|---|---|---|---|
| 0.60% | 6 months | 0 | 0 | 22 (18 pairs), −0.21% ± 0.95% | 28 (22 pairs), −0.30% ± 0.84% |
| 0.60% | 12 months | 1 (1 pair), −2.17% (n = 1) | 3 (3 pairs), −0.67% (interval not meaningful) | 46 (35 pairs), −0.20% ± 0.65% | 55 (40 pairs), −0.10% ± 0.60% |
| 0.50% | 6 months | 1 (1 pair), −2.07% (n = 1) | 12 (10 pairs), +0.06% ± 1.34% | 71 (47 pairs), −0.26% ± 0.52% | 83 (51 pairs), −0.14% ± 0.48% |
| 0.50% | 12 months | 3 (2 pairs), −2.11% (interval not meaningful) | 23 (17 pairs), −0.19% ± 0.93% | 119 (75 pairs), −0.11% ± 0.40% | 145 (76 pairs), +0.04% ± 0.37% |
| 0.40% | 6 months | 3 (2 pairs), −2.01% (interval not meaningful) | 36 (22 pairs), −0.32% ± 0.72% | 150 (70 pairs), −0.17% ± 0.35% | 173 (74 pairs), −0.24% ± 0.33% |
| 0.40% | 12 months | 12 (2 pairs), −0.94% ± 1.14% | 58 (35 pairs), −0.03% ± 0.58% | 254 (110 pairs), −0.08% ± 0.27% | 283 (111 pairs), −0.06% ± 0.26% |

- **Expected move:** the pair with the highest expected move among those the anomaly and DI gates
  pass.
- **Net margin:** the highest expected move minus 2.5 × its own friction, which is exactly what
  engine 10 tests.

**Expected move is the ruled ranking** (§R.2, with invariant 4 amended). The trade counts it gives
at each friction are this document's best offline statement of what the simulated system will do,
before entry fills are modelled. In the table above, anomaly and DI are applied to every pair before
the choice. The engine arrangement that achieves this without any gate's verdict depending on the
ranking is fixed in spec 144. **Net margin is rejected**, on live feasibility (§R.2), and its
column is kept only as a measured comparison.

**The finding: the ranking changes how many trades are taken, not what each trade earns.** Across
the three rankings other than alphabetical, wherever there are enough trades for an interval, every net per
trade lies between −0.32% and +0.06%, and every interval includes zero. Alphabetical ordering
yields too few trades to say anything about its return. Its point estimates are worse, but they
rest on one to twelve trades on two pairs.

**SIMULATED VALUE PENDING:** the expected-move ranking's chain trade count, pair count and net per
trade at tiers 3 and 5 over the three months (§R.6).
```

(iv) §5a capped against uncapped, FINAL, lines 471–495, and (v) §5b the veto sweep, FINAL for the skeptic it measured, lines 496–537:

*Verbatim from `docs/dataset/phase-7-findings.md`, lines 469–537:*

```markdown
## 5. The skeptic

### 5a. Capped against uncapped, over the 1.5-year window. FINAL.

The operator ruled on 2026-09-16 that the skeptic trains on a rolling window of the last 13 folds'
BUY calls. The walk-forward trained it on every earlier fold's calls, uncapped. For the 79 folds of
the window, capped skeptics were trained in memory with the trainer's own row selection and model
settings. The replication was first shown to reproduce the trainer exactly: on folds 20 and 40,
retrained uncapped, the training rows and identity matched the manifests and the probabilities
differed by 0 ([T] `q_capped.py validate`). Scored on the window's 3,751,522 out-of-sample BUY calls
(base target rate 0.2438; [T] `q_capped_compare.py`):

| Veto threshold | Uncapped: passing | Uncapped: target rate | Capped: passing | Capped: target rate |
|---|---|---|---|---|
| 0.50 | **1.57%** | **0.581** | **6.22%** | **0.408** |
| 0.60 | 5.93% | 0.469 | 17.29% | 0.366 |
| 0.70 | 33.60% | 0.353 | 41.89% | 0.327 |

At 0.50 the two sets share 49,032 calls, and the two skeptics' scores correlate at 0.83. At a
matched pass rate the uncapped skeptic ranks better: at about 6% passing, uncapped at 0.60 reaches
0.469 against capped at 0.50's 0.408.

**In the funnel** (§1b; alphabetical, tier-3 reference fees, **zero spread**, 18 months): the
uncapped skeptic leaves **1 trade** and the capped one **15**. That comparison is after fees and
before spread. Ranked by `log_return_4` at the same friction: 52 against 79
(`outputs/q_funnel.out`).

### 5b. The veto sweep of 2026-09-14, uncapped skeptic, all 405 folds. FINAL for the skeptic it measured.

**Every figure in 5b describes the uncapped skeptic.** The capped skeptic's sweep across all 405
folds is **NOT MEASURED** (capped skeptics exist for folds 326 to 404 only).

Out-of-sample BUY calls, folds 1 to 404: 8,948,485, target rate 0.2383 (all test rows 0.2422).
Survivors are calls with P(wrong) ≤ threshold. The no-skill band shuffles each fold's own scores
across its calls, 20 times. Source: `docs/dataset/skeptic-veto-sweep-2026-09-14.md`.

| Threshold | Survivors | Share | Survivor target rate | No-skill band |
|---|---|---|---|---|
| 0.30 | 9,373 | 0.10% | 0.6349 ± 0.0085 | 0.2711–0.2892 |
| 0.40 | 51,145 | 0.57% | 0.6035 ± 0.0037 | 0.2563–0.2621 |
| 0.50 | 154,979 | 1.73% | 0.5309 ± 0.0023 | 0.2550–0.2596 |
| 0.60 | 583,121 | 6.52% | 0.4403 ± 0.0014 | 0.2602–0.2629 |
| 0.70 | 2,859,743 | 31.96% | 0.3482 ± 0.0007 | 0.2645–0.2653 |

At 0.50 the survivors beat the vetoed calls in every test year from 2017 to 2024 (0.43 to 0.58
against 0.19 to 0.27).

**Against the predictor's own confidence at matched counts.** For each fold, the top N BUY calls by
calibrated `p_target` were taken, where N is the skeptic's survivor count in that fold. Source:
`docs/dataset/skeptic-vs-ptarget-2026-09-14.md`.

| Threshold | N | Skeptic target rate | Top N by `p_target` | Skeptic's margin | Calls in both sets |
|---|---|---|---|---|---|
| 0.30 | 9,373 | 0.6349 | 0.5605 | +0.0744 | 29% |
| 0.50 | 154,979 | 0.5309 | 0.4731 | +0.0578 | 44% |
| 0.60 | 583,121 | 0.4403 | 0.4097 | +0.0306 | 47% |
| 0.70 | 2,859,743 | 0.3482 | 0.3433 | +0.0049 | 68% |

The skeptic adds selection beyond the predictor's own ranking at the strict end, and almost none
at the loose end.

**Two caveats that travel with 5b:**

- All its rates are before friction.
- The progress tracker's Finding 1 requires every number measured on the uncapped skeptic to be
  re-measured on the capped one before it is cited as describing the ruled system. §5a shows that
  in this window the two differ by a factor of four in pass rate.

---
```

(vi) §6 the overconfidence of cost-clearing calls, with its §6a caveat, lines 539–605:

*Verbatim from `docs/dataset/phase-7-findings.md`, lines 539–605:*

```markdown
## 6. The predictor's overconfidence

Candidates that clear the cost bar carry expected moves of at least the bar (1.50% at tier 3) and
at most just under 3.0% (§2). What they realise, before any friction:

| Set | Calls | Realised mean | Source |
|---|---|---|---|
| Alphabetical candidates clearing 1.50%, full span | 938 | **+0.320%** | [T] `2026-09-18_q_net.py` |
| The same, 1.5-year window | 74 | +1.251% | `outputs/q_window.out` |
| The same, one position per pair, 1.5-year window | 34 | +0.781% | `outputs/q_window.out` |
| All out-of-sample BUY calls (expected move > 0), full span | 8,950,912 | target rate 0.2383 against 0.2422 for all rows | `skeptic-veto-sweep-2026-09-14.md` |

**Across the full span, the calls confident enough to clear the cost gate realised about a fifth of
the smallest expected move they could carry**: +0.32% against at least 1.50%. The fee of 0.60% was
charged against that +0.32% and left −0.28% per trade, with an interval excluding zero
([−0.42%, −0.14%]). **That shortfall between what the model promises and what the market delivers
is what the cost gate is left to absorb**, and at every tier the gate is priced on the promise.

**The window was kinder.** The same selection realised +1.25% there, and +0.78% with one position
per pair. The shortfall is real across eight years, and its size varies by period.

The period difference has a section of its own, §6a.

**Whether the most confident calls are the most overconfident is NOT MEASURED.** That would need
the realised return by expected-move decile, or a calibration curve of expected move against
realised return, and neither was computed. The measured statement is narrower: the calls above the
bar realise far less than the bar.

**SIMULATED VALUE PENDING:** the chain trades' mean expected move at entry beside their realised
return. That comparison needs the approval record Phase 7 prerequisite 7 adds.

### 6a. The shortfall depends on the period. A caveat on §6, raised here rather than waited for

The same selection (the alphabetical candidate clearing 1.50%, tier-3 fees, zero spread) realised
very different means in different periods:

| Period | Calls | Realised mean | How obtained |
|---|---|---|---|
| Full span, 405 folds (2017-04 to 2025-01) | 938 | +0.320% | measured ([T] `2026-09-18_q_net.py`) |
| The 1.5-year window (2023-07 to 2025-01) | 74 | +1.251% | measured (`outputs/q_window.out`) |
| The final 365 days (2024) | 71 | +1.177% | measured ([T] `2026-09-18_q_net.py`) |
| Full span **excluding** the final 365 days | 867 | about +0.25% | derived: (938 × 0.320 − 71 × 1.177) / 867 |
| Full span **excluding** the 1.5-year window | 864 | about +0.24% | derived: (938 × 0.320 − 74 × 1.251) / 864 |

- The two derived rows are arithmetic on the published means, which are rounded to three decimals.
  They are not a recomputation.
- **71 of the window's 74 calls fall in its final 365 days.** The window's strength is
  essentially 2024's.

**What this means.** The full-span shortfall (+0.32% realised against at least 1.50% expected) is
an average over periods that behave very differently: about +0.25% before 2024, about +1.2% in
2024. It is therefore a caveat on §6. It is possibly a property of the early years rather than of
the model. The skeptic's survivor target rates at 0.50 point the same way (§5b): 0.58 and 0.57 in
2023 and 2024, against 0.43 to 0.51 in 2017 to 2022.

**What cannot be separated from what is on disk.** Two explanations fit:

- a model that improves as its training history lengthens and the universe widens;
- a market in 2023–24 that happened to reward the same calls.

The per-year realised mean of cost-clearing calls, for years other than the final 365 days, is
**NOT MEASURED**, and neither is any control that separates the two explanations.

**Why it matters for the simulation.** The simulated window is the three months ending 2025-01-04
(folds 392 to 404), inside the strong period, and narrower still (§7b). A simulated result, favourable or not, describes that period. It must not
be read as the full span's behaviour.
```

The sixth item in §10 is the fee schedule (§R.3, lines 100–106):

*Verbatim from `docs/dataset/phase-7-findings.md`, lines 100–106:*

```markdown
**R.3 The fee schedule is sourced.** Kraken's published schedule was fetched on 2026-09-19 and is
committed with its URL and fetch time (`tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`,
extracted verbatim from the committed raw page). It agrees with the figures the operator had from a
web search: tier 3 0.22%/0.38%, tier 4 0.20%/0.35%, tier 5 0.15%/0.30%. **Kraken restructured its
fee tiers on 9 July 2026.** Its support article, committed beside the schedule, says tiers are now
set by the best of spot volume, futures volume and assets on platform. **Nothing on disk dates any
earlier schedule, so the 2026 schedule is applied to a 2023–24 window.**
```

### B.6 Retired vocabulary

The `docs_vocabulary` criterion in `scripts/verify.py` parses this table (`context/ai-workflow-rules.md` lines 59–70) and FAILs any phase whose `AGENTS.md`, `README.md` or `context/*.md` contains a retired term outside strikethrough and outside the two excluded sections:

*Verbatim from `context/ai-workflow-rules.md`, lines 47–70:*

```markdown
## Retired vocabulary

Every audit of these documents has found the same class of defect: a decision that reached three files and not the fourth, leaving an agent to follow the stale copy in good faith. It is not caught by reading, because each file is self-consistent. It is caught by grep.

`scripts/verify.py` therefore carries a `docs_vocabulary` criterion in **every** phase. It scans `AGENTS.md`, `README.md` and `context/*.md`, and FAILs if any of these appear outside `~~strikethrough~~` and outside the two excluded regions below.

**Two regions are excluded, for one reason: a section whose job is to catalogue superseded things necessarily names them.** The exclusion is always the smallest section that does that job, ending at the next `## ` heading — never a whole file.

The first is this `## Retired vocabulary` section. It defines the terms, so it names them in the table and in any prose explaining the table, including a quotation of the historical defect a row exists to catch. A quotation of a defect is the one thing that will always look exactly like the defect. **This exclusion holds only while this section stays short and wholly about the check** — if current-state material ever accumulates here, re-narrow it, because a blanket exclusion over mixed content is precisely how a stale claim survived three audits inside the tracker.

The second is the `## Decision history` section of `context/progress-tracker.md` — the record of superseded decisions, which is *meant* to name retired terms. Everything else in the tracker (Current Goal, Locked Decisions, Architecture Decisions, Known Risks) is current-state text and is scanned like any other file. Excluding the whole tracker is how a stale claim about the memory engine survived three audits inside a section labelled Architecture Decisions.

| Retired term | Only a hit when the same line also contains | Superseded by |
|---|---|---|
| `two-chain` | — | three runtime chains: guard, opportunity, manage |
| `chain 1`, `chain 2`, `always chain` | — | the chains have names; use them |
| `INGEST_CHAIN` | — | `GUARD_CHAIN` |
| `state["system_mode"]` | — | `state["system"]["mode"]` |
| `paper.starting_balance` (singular) | — | `paper.starting_balances`, a per-currency map |
| `24 bars` | — | 48 bars |
| `eight` | `machine learning`, `non-ML`, or `engines` | nine — `scout` is deterministic |
| `tier 1` | `assume` | a pair with no fee data blocks; there is no fee fallback |
| `90 days either side` | — | the walk-forward trains on the 90 days **before** its test window and nothing after it, operator ruling 1 of 2026-09-12 |
| `accuracy` | `metric` or `score` | the Brier of P(target) against the fold's base-rate Brier, operator ruling 2026-09-12: at a 23.89% target rate a model that always predicts `stop` scores 51%, so a document reporting accuracy is reporting the model that never trades |
```

Additional terms the repository treats as superseded in prose (not enforced by the checker): "dissimilarity_index" as a reason code (retired by spec 71; the code is `di_refused`, `src/acsoe/console/format.py` comment at the `di_refused` entry); `outside_universe`, `insufficient_depth`, `meta_label_veto`, `no_candidate_cleared`, `outlier_market_state` (retired from `REASON_PROSE` by spec 120, tracker lines 485–494); "the mode" for `state["system"]["mode"]` versus `context.mode` (engine-contracts.md line 321: `context.mode` is always the configured mode, never the run state).

### B.7 Abbreviations and named components

From `context/glossary.md` (the whole file is reproduced at the end of this subsection), the invariants, and the code:

| Term | Expansion / meaning | Source |
|---|---|---|
| ACSOE | Adaptive Crypto Spot Opportunity Engine | `AGENTS.md` line 17; `README.md` line 1 |
| OHLCVT | Open, high, low, close, volume, trade count — the seven-column bar format of Kraken's archives | `src/acsoe/modelling/features.py` lines 14–16 ("open, high, low, close, volume and trade count") |
| DI | Dissimilarity Index: mean distance to the k nearest MinMax-scaled training rows, thresholded at a leave-one-out percentile; refuses prediction on unfamiliar conditions | `context/glossary.md` line 47; `src/acsoe/modelling/di.py` lines 1–52 |
| HAC | Heteroskedasticity-and-autocorrelation-consistent (Newey–West, Bartlett kernel) standard error, used because overlapping holds are not independent | `src/acsoe/modelling/promotion.py` lines 16–25 |
| BH-FDR | Benjamini–Hochberg false-discovery-rate control over a family of tests. **NOT FOUND in the repository**: no `Benjamini`, `Hochberg`, `FDR` or `false discovery` string exists in `src/`, `docs/`, `context/` or `feature-specs/`. The committed multiple-testing correction is **Bonferroni** over N = 1,679 (`promotion.py` lines 32–35). See pack 03 §C.2. |
| DSR | Deflated Sharpe Ratio (Bailey and López de Prado 2014), reported beside the verdict and never deciding it | `promotion.py` lines 44–57 |
| Brier score; base-rate Brier | Calibration score of P(target); the Brier a constant prediction of the fold's own target rate would earn, `p(1−p)` | `glossary.md` lines 69–71 |
| BUY call | A decision bar on which `expected_move_pct > 0` before friction | `glossary.md` line 73 |
| Expected move | `p_target × target − p_stop × stop + p_timeout × mean timeout return` | `src/acsoe/modelling/expected_move.py` lines 9–13 |
| Friction; hurdle; net edge | `friction = maker + taker + spread + slippage`; `net_edge = expected_move − friction`; trade only if `net_edge > hurdle_multiple × friction` | `trading-invariants.md` lines 167–171 |
| The Skeptic | Engine 15: a second LightGBM (binary) model trained on the predictor's own out-of-sample BUY calls to predict "wrong"; can only veto | `glossary.md` line 45; `src/acsoe/engines/skeptic/engine.py` lines 1–12; `research/training.py` lines 1280–1292 |
| The cost gate | Engine 10 `cost` | `src/acsoe/engines/cost/engine.py` lines 6–8 |
| The predictor | Engine 8 `prediction`: LightGBM multiclass over three barrier classes with isotonic calibration | `research/training.py` lines 812–814, 985–1010 |
| Anomaly gate | Engine 13: scikit-learn IsolationForest over the 21 market-quality features | `research/training.py` lines 1546–1566; `features.py` `MARKET_QUALITY_FEATURES` |
| Guard / opportunity / manage / offline chain | The four engine lists | `glossary.md` lines 87–92 |
| Decision bar; loop tick | 15-minute candle on which candidates are born; 1-minute cycle that manages positions | `glossary.md` lines 37–41 |
| Triple barrier | Label: which of +3% target, −1.5% stop, 48-bar timeout is touched first | `glossary.md` line 43 |
| Meta-labelling | Training a second model to grade the first's calls (the Skeptic) | `glossary.md` line 45 |
| Walk-forward; purge; embargo | Rolling train-then-test with weekly retraining; dropping training rows whose label window reaches the test window; a 48-bar buffer before the test window | `glossary.md` lines 57–59; `research/walkforward.py` |
| SHAP | SHapley Additive exPlanations; `shap.TreeExplainer` per-feature attributions written per decision | `src/acsoe/engines/prediction/engine.py` lines 328–344 |
| Post-only; maker; taker; `oflags=post` | Limit order Kraken cancels rather than lets execute as a taker; adds/removes liquidity | `glossary.md` lines 11–15 |
| `ordermin`; `costmin`; `userref` | Minimum order size (base units); minimum order value (quote units); client-supplied integer for idempotency | `glossary.md` lines 27–33 |
| Uniqueness weight; effective sample size | Sample weight from label-window overlap; the sum of weights | `glossary.md` line 75 |
| Alpha; beta; buy-and-hold | Return after benchmark exposure; exposure-explained return; the benchmark | `glossary.md` lines 63–79 |
| Paper broker | `clients/paper/`: the fill simulator and paper ledger wrapping the Kraken client in paper mode | `glossary.md` line 100 |
| Replay client | `clients/kraken/replay.py`: history served through the live client's surfaces, replay mode only | `replay.py` lines 1–40 |
| Declared (scenario input) | A value the archive never recorded, supplied by a committed fixture and labelled as such: the fee schedule, the bucket table, the 2026 pair rules | `trading-invariants.md` lines 101–129 |
| Scenario digest | sha256 of the declared inputs, written on the `runs` row | migration 0006 lines 54–59 |
| `cycle_id`; `run_id` | Tick counter restarting at 1 per process; the process identity | `architecture-context.md` lines 214–217 |
| Freeze; `close_all`; `close_intent` | Stop opening, keep managing; the kill switch (cancel every resting entry, sell every position as a taker); the persistent flag | `architecture-context.md` lines 254–262 |
| Phase (0–8); stage (1–4) | Build phase; runtime loop stage | `glossary.md` lines 85–94 |
| Agent A / B / C / Lead | The four coding agents that built the system (Platform; Store and trading; Interface and models; core and registry) | `context/run-protocol.md` lines 125–130 |
| FX, AoP | Foreign-exchange pairs (e.g. EUR/USD); Assets on Platform (Kraken's tier criterion) | `tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json` |
| WAL | SQLite write-ahead log (the `-wal` files beside each database) | `data/db/` listing |
| WMI | Windows Management Instrumentation (`Win32_Process.Create`, how the runs were launched detached) | `launch_phase7.ps1.txt` line 4 |

The glossary in full:

*Verbatim from `context/glossary.md`, lines 1–108:*

```markdown
# Glossary

These terms have precise meanings in this codebase. Do not substitute your own.

## Exchange mechanics

**Order book** — the queue of resting buy and sell offers on a pair. Bids below, asks above.

**Spread** — the gap between the best bid and the best ask. An invisible cost paid whenever you cross it.

**Maker** — an order that rests in the book and adds liquidity. Cheaper fee. May never fill.

**Taker** — an order that crosses the book and removes liquidity. Higher fee. Fills immediately.

**Post-only** (`oflags=post`) — a limit order that Kraken cancels rather than allowing it to execute as a taker. Guarantees the maker fee. This is how every entry is placed.

**Round trip** — one buy plus one sell. Fees are charged per side, so a round trip pays twice.

**Slippage** — the difference between the price you expected and the price you got, because your order consumed more than one level of the book.

**Friction** — this project's umbrella term: fees + spread + slippage, expressed as a percentage of position value, for a complete round trip.

**Hurdle** — the minimum net edge a candidate must show before it is allowed to trade. Derived from friction, never a constant.

**Fee tier** — Kraken assigns it automatically from the better of your trailing 30-day volume or your Assets on Platform. You cannot choose it. Tier 1 is the default for a new account.

**`ordermin`** — a pair's minimum order size, expressed in units of the base currency. From `AssetPairs`.

**`costmin`** — a pair's minimum order value, expressed in the quote currency. From `AssetPairs`.

**Base and quote** — in `SOL/USD`, SOL is the base and USD is the quote. Minimums, decimals, and profit denomination all depend on which is which.

**`userref`** — a client-supplied integer attached to an order, used here for idempotency so a retry never double-places.

## Strategy

**Decision bar** — the 15-minute candle on which features are computed and candidates are born.

**Holding horizon** — 2 to 12 hours. Not the same as the decision bar.

**Loop tick** — the 1-minute cycle that manages open positions. Never generates new candidates.

**Triple barrier** — the labelling method. From a given bar, ask which of three lines price touches first: the profit target (+3%), the stop (−1.5%), or the timeout (48 bars). Three-class label. **What a bar means in that third line, and what happens when one candle touches two barriers, are both settled in `architecture-context.md` under Timeframes and Historical — do not answer either from this entry.**

**Meta-labeling** — training a second model to grade the first model's calls. It sees only the rows where the predictor said BUY, and learns when that call was wrong. This is the Skeptic.

**Dissimilarity Index (DI)** — a measure of how far a live feature vector sits from the model's training data. Computed from the distribution of pairwise distances within the scaled training set, thresholded at a rolling high percentile. Above threshold means the model has never seen conditions like this and must refuse to predict. **Fitted on the predictor's training set, never the Skeptic's subset.** The threshold's leave-one-out distribution excludes every reference row within 48 bars of the row being scored, across all pairs, because the macro columns are shared by every pair on a bar (operator ruling 2026-09-15; spec 68, amendment).

**Regime** — the classified market environment: trending, choppy, or high volatility. DI threshold crossings also signal a regime change.

**Adverse selection** — when your resting order fills because someone chose to sell to you right before the price fell. Measured here as the post-fill 5-minute move.

**Counterfactual** — a rejected candidate, logged with its reason. The record of a road not taken.

## Evaluation

**Walk-forward** — train on a window, test on the next period, roll forward, repeat. In this project the model is **retrained at each step at the same cadence the live system uses** (weekly), not fitted once.

**Purging and embargo** — removing training rows whose label window overlaps the test period, plus a buffer. Without this, the model sees the future and every result is invalid.

**Look-ahead bias** — using information at bar *t* that would not have existed until after bar *t*. The most common and most fatal defect in this kind of system.

**Beta** — the portion of returns explained by simply being exposed to the market. If Bitcoin rose 20% and you made 8%, your beta earned it and your skill lost.

**Alpha** — what is left after subtracting beta. The only number that matters for promotion.

**Deflated metric** — a performance score haircut for the number of models tried, so that picking the best of twenty is not mistaken for skill.

**Brier score** — how well-calibrated probabilities are. Lower is better. A model that says 70% should be right 70% of the time.

**Base-rate Brier** — the Brier a constant prediction of the fold's own target rate would earn, `p(1-p)`. The number every fold's Brier is reported beside; a model that does not beat it has learned nothing. Chosen as the primary comparison because, at a 23.89% target rate, a model that always predicts `stop` is right 51% of the time and a headline hit rate rewards the model that never trades.

**BUY call** — a decision bar on which the predictor's `expected_move_pct` is positive: `p_target × target − p_stop × stop + p_timeout × mean timeout return`, before friction. The cost gate applies friction afterwards. The skeptic trains only on the predictor's out-of-sample BUY calls.

**Uniqueness weight** — a row's sample weight in training: the mean, over its own label window, of one over the number of label windows covering each bar. Consecutive decision bars at a 48-bar horizon share almost all of their window, so twenty million rows are far fewer observations; the **effective sample size**, the sum of the weights, is reported beside every row count, per fold.

**Sharpe ratio** — return divided by the volatility endured to get it.

**Buy-and-hold** — the benchmark. Doing nothing. The thing this system has to beat to justify existing. Phase 7 reports two (operator ruling R8, 2026-09-19): BTC/USD bought and held over the run's window, and an equal-weighted basket of the pairs the run held while it held them. Each is compared with the run's equity curve including cash periods. Spec 138 is the authority.

**Scout** — engine 7. Deterministic, no model. Builds the tradable universe from live pair rules and balance with no model, then orders what is left: by engine 8's expected move, skipping pairs the anomaly or DI gate would refuse, when `scout.rank_feature` is `expected_move` (invariant 4, amended 2026-09-19), and alphabetically otherwise. The one candidate it emits goes to the judgement chain.

## Words that are easy to confuse

**Phase** — a build phase, 0 to 8, from `ai-workflow-rules.md`. What the operator means by "start phase N".

**Chain** — one of the four ordered engine lists in the registry. Never numbered; always named.

- **Guard chain** — 1, 2, 3, 4, 17. Every tick, every mode, never breaks early. Data in, and the account-level circuit breaker.
- **Opportunity chain** — 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, 16, 18. Only when the mode is `running` and nothing has blocked. Stops at the first block or PASS.
- **Manage chain** — 21, 22, 19. Every tick, every mode. Watches positions, exits them, records everything.
- **Offline chain** — 20, 23. Only via `acsoe research`. Never touched by the daemon.

**Stage** — a step in the runtime loop, 1 to 4, from `architecture-context.md`. Never used to mean a build phase.

**Script** — the build log. Each agent writes `docs/build-log/phase-N/<agent>.md`; the lead consolidates into `docs/build-log/phase-N.md` at phase close. When the operator says "update the progress tracker and script", this is the script.

**Execution offset bandit** — not an engine. A small pooled selector inside `engines/execution/` that learns how far below market to place a post-only limit, bucketed by spread tier, with its state in the store. **Deferred to Phase 7 by operator ruling 2026-09-16**: it needs a table that does not exist and a fill history that does not exist either. Phase 6 places every entry at the best bid, which is a recorded absence rather than a chosen rule.

**Paper broker** — `clients/paper/`, B's. The fill simulator and the paper ledger, implementing the same order surface the live Kraken client does and wrapping it in paper mode, so a mode difference never reaches an engine. Fills are pessimistic by rule: a resting post-only buy fills only on a trade strictly below its limit, and a market sell walks the bid side of the fetched book.

## Modes

**Paper** — the default. Full pipeline, simulated fills, no exchange mutation.

**Live** — real orders. Requires all three switches in `trading-invariants.md`.

**Replay** — offline. Historical data through the same engines with an injected clock.
```

### B.8 Ethics and safety material

- **Personal data:** the repository holds none that it names. The recorded archive is public exchange market data (book, ticker, trade frames); the only account-specific data is the operator's own fee tier and assets-on-platform figure returned by `TradeVolume`, written to `data/raw/fees/` which is gitignored (`scripts/recording/fees.py` lines 44–47: "The account's 30-day `volume` goes into the archive under `data/raw/fees/`, which is gitignored, and nowhere else: the stderr summary names the keys that came back, never a value"). No user table, no name, no email exists in the schema (`db/migrations/`, pack 01 §C.7). Rule 5 of `context/script-rules.md` (line 491): "Never put a key, a secret, or an account balance in here."
- **API keys:** environment only. `trading-invariants.md` invariant 13 (lines 236–238): "API keys come from the environment only. Never logged, never committed, never written into config files, never echoed in error messages or console output. The web console holds no credentials and cannot place orders." `.env.example` (10 lines) names `KRAKEN_API_KEY`, `KRAKEN_API_SECRET`, `ACSOE_LIVE=0` and says "Use a READ-ONLY key until Phase 8". `.env` exists on disk (676 bytes, not read for this pack) and is gitignored. Logging redacts by key name and by value at the client boundary (`src/acsoe/platform/logging.py` lines 6–18, 35–41, 117–133). `fees.py` reads the two names from `.env` only and passes every stderr line through `redact` (`fees.py` lines 36–44).
- **Live trading default and what stops an accident:** `config/default.yaml` line 22 `mode: paper`. `platform/live_guard.py` **does not exist** (`ls src/acsoe/platform/` — no such file; it is the Phase 8 deliverable, `ai-workflow-rules.md` line 138). Until it does, the config loader **refuses `mode: live` outright**: `src/acsoe/platform/config.py` lines 11–14 ("**Mode.** `live` is refused. `platform/live_guard.py` … is a Phase 8 deliverable, and until it exists the loader refuses to start in live mode. The absence of the guard is not permission") and lines 982–986 (the raise). The daemon wraps the Kraken client in the paper broker only when `config.mode == "paper"` (`cli/engine.py` lines 126–132, "`== "paper"`, not `!= "live"`"), and the real client's four order methods refuse until Phase 8 (`cli/engine.py` lines 95–99; tracker line 917 "The live client's order refusal stays as the one copy to remove in Phase 8"). Invariant 1 (three independent switches) is the designed guard; today the loader's refusal is the stricter, single, operative one.
- **Risk to the operator's own funds, as stated:** `README.md` "Disclaimer" (last lines): "Research software for a dissertation. It can lose money. Nothing here is financial advice, and it is not intended to manage anyone else's funds." `context/project-overview.md` line 68: out of scope "Managing anyone else's money". `context/progress-tracker.md` Known Risks line 2238: "**A read-and-trade Kraken key exists on the dev machine.** Use a separate read-only key until Phase 8. The three live switches are the only thing between a bug and real money." The handover (`docs/build-log/phase-7/handover-2026-09-19.md` lines 330–331) records the open action "A separate read-only key for `fees.py`: the operator's action. Until then, nonces can collide once the daemon runs." The measured account holds `domain_assets_on_platform` 36.46 (2026-09-19) to 41.76 (2026-09-20) USD-equivalent per the fee poll (`data/raw/fees/*.jsonl`, `inputs` block), so the exposure of the real account is tens of dollars; the paper account is 5,000 USD (`config/default.yaml` line 130).

---

## C. Architecture

### C.1 The engine registry, verbatim

*Verbatim from `src/acsoe/bootstrap.py`, lines 96–120:*

```python
#: Engines 1, 2, 3, 4, 17. Every tick, every mode, never breaks early.
#: Ingestion plus the account-level circuit breaker. Freeze must not stop data
#: collection, and a bad-data block must not stop ``safety`` evaluating.
#:
#: Order is the registry table's, not alphabetical and not dependency-inferred: 1
#: ``exchange`` publishes the account picture, 2 ``market_data_recorder`` records raw
#: frames, 3 ``market_sensor`` builds candles and quotes, and 4 ``data_guard`` judges
#: what 1 and 3 produced — so the gate has to come last of the four. Engine 17
#: **Engine 17 ``safety`` joins at the end in Phase 3, and last is load-bearing**: it
#: reads the current tick's ``state["trading_blocked_by"]``, which ``data_guard`` sets,
#: so it cannot precede the engine whose verdict it counts. It is a gatekeeper on the
#: *account* rather than a judgement about a candidate, which is why it belongs in the
#: guard chain at all — a freeze must not stop data collection, and a bad-data block
#: must not stop ``safety`` evaluating.
#:
#: Constructors take no arguments and hold no resources. The WebSocket stream owns a
#: thread and needs ``start()``/``stop()``, but it lives on the client rather than on an
#: engine, which keeps that a ``cli/engine.py`` lifecycle concern.
GUARD_CHAIN: tuple[BaseEngine, ...] = (
    ExchangeEngine(),
    MarketDataRecorderEngine(),
    MarketSensorEngine(),
    DataGuardEngine(),
    SafetyEngine(),
)
```

*Verbatim from `src/acsoe/bootstrap.py`, lines 122–188:*

```python
#: Engines 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, 16, 18. Only when the mode is
#: ``running`` and nothing has blocked. Stops at the first block or PASS.
#:
#: **Phase 3 registers 7, 10 and 11**, in the registry table's order and not in a
#: contiguous run: 5, 6, 12, 13, 8 and 9 sit between them and do not exist yet. The
#: orchestrator skips an unregistered engine, so the chain is 7 -> 10 -> 11 until they
#: land, and the *relative* order is what the table fixes. Inserting the missing six
#: later is an edit to this tuple and to nothing else.
#:
#: The order is not arbitrary and is not dependency-inferred. 7 ``scout`` chooses the
#: candidate pair and must run first, because 10 and 11 both read
#: ``state["scout"]["pair"]`` and neither invents one when it is absent — a `PASS` tick
#: with an empty universe publishes no ``pair`` and the cost gate then fails closed,
#: which `tests/engines/test_scout.py` asserts rather than assumes. 10 ``cost`` before
#: 11 ``risk`` because the cheaper question comes first: cost needs a fee tier and a
#: spread, risk needs a price, an order book and the account's balances, and there is no
#: sense sizing a position the edge cannot pay for.
#:
#: **Phase 5 registers 5, 6, 12, 13, 8 and 15, spec 77**, into their registry positions:
#: the chain is now 5 -> 6 -> 7 -> 12 -> 13 -> 8 -> 10 -> 11 -> 15, with 9 ``order_book``,
#: 14 ``adaptive_router``, 16 ``decision`` and 18 ``execution`` still absent for Phase 6.
#: Engine 5 ``feature`` is first and returns ``PASS`` on every tick where no decision bar
#: closed, so from here the rest of the chain runs only on bar ticks. Engines 13, 8 and 15
#: fail closed on a fresh clone, which has no ``models/`` and therefore no run ids, so
#: all three block on every bar tick there. The operator's three thresholds are no longer
#: among the reasons: ``prediction.di_percentile``, ``anomaly.threshold_percentile`` and
#: ``skeptic.veto_threshold`` were ruled on 2026-09-14 and 2026-09-15 and are in
#: ``config/default.yaml``, all three provisional until the chain runs end to end.
#:
#: In Phase 5 engine 10 blocked every candidate for want of engine 9's slippage estimate,
#: so engine 15 was rehearsed with 10 and 11 left out. That hole is closed.
#:
#: **Phase 6 registers 9, 14, 16 and 18, spec 82, and the chain is now complete** — the
#: registry table's order with no holes. 9 ``order_book`` sits before 10 ``cost``, which
#: reads its ``estimated_slippage_pct`` and refuses when it is absent (engine 9 never
#: blocks on its own). 14 ``adaptive_router`` sits after 11 ``risk`` and before 15
#: ``skeptic``; nothing it publishes may change whether a gate blocks (invariant 4).
#: 16 ``decision`` is a **gate** (operator ruling 2026-09-16): it refuses unless every
#: approving engine judged this tick's pair and bar, and it composes the one order intent
#: 18 ``execution`` reads — so 18 is last, and places a post-only entry only on an intent.
#:
#: Registration was held until two rehearsals, each by an agent that did not build the
#: engines, were green: B's spec 94 over 9 and 14 (``test_feature_chain_rehearsal.py``, on
#: a thin recorded book where engine 9's estimate is non-zero, so engine 10's use of it is
#: proven by recomputation) and A's spec 87 over 18, 21 and 22
#: (``test_trade_chain_rehearsal.py``, every upstream engine real). Those rehearsals found
#: two defects between engines, both fixed before this registration: a paper fill counted
#: twice in equity (spec 103) and an errored opportunity-chain tick left unrecorded
#: (spec 104). Every trade the chain can produce in a test is at a fee tier the fake client
#: supplies. At Kraken's *reference* tier 1 (invariant 5) the cost gate is unreachable at
#: the current barriers; the fake's own tier 1 is not (measured 2026-09-18, operator
#: ruling S3).
OPPORTUNITY_CHAIN: tuple[BaseEngine, ...] = (
    FeatureEngine(),
    MacroContextEngine(),
    ScoutEngine(),
    RegimeEngine(),
    AnomalyEngine(),
    PredictionEngine(),
    OrderBookEngine(),
    CostEngine(),
    RiskEngine(),
    AdaptiveRouterEngine(),
    SkepticEngine(),
    DecisionEngine(),
    ExecutionEngine(),
)
```

*Verbatim from `src/acsoe/bootstrap.py`, lines 190–235:*

```python
#: Engines 21, 22, 19. Every tick, every mode. Watches positions, exits them, records
#: everything — including on the fourteen ticks in fifteen where no bar closed.
#:
#: **Phase 4 registered 19 `memory`, spec 58; Phase 6 registers 21 `position_manager` and
#: 22 `exit`, spec 82, and the chain is complete.** The order is load-bearing: 21 watches
#: the positions and resting entries and publishes the triggers and marks, 22 reads those
#: triggers and places the exits (or, with `close_intent` set, liquidates regardless of a
#: `data_guard` hold, invariant 14), and 19 runs **last** because it records what 21 and 22
#: did on this tick — an engine cannot record a decision that has not been taken yet. The
#: orchestrator clears `close_intent` only when 21 reports `entry_orders_cancelled` and 22
#: reports `positions_closed`.
#:
#: Registration was held until engine 19 had been driven through **two real orchestrator
#: ticks** by an agent that did not build it — B, in
#: `tests/engines/test_manage_chain_rehearsal.py` — the same deferral Phase 2 and Phase 3
#: both took and the third time it paid. Two ticks rather than one because `state` is
#: fresh every tick except `state["system"]`, so an engine quietly depending on something
#: surviving passes a single-tick test and fails the second. The rehearsal's mutation N5
#: measured that rather than asserting it: with `cycle_id` cached on the engine across
#: ticks, the single-tick test still passes and five two-tick assertions fail.
#:
#: One thing the rehearsal established that is worth knowing before reading this chain.
#: `ux_equity_snapshots_tick` has now been **seen to fire**: two orchestrators sharing one
#: `run_id` — a process restarting under a reused id — each mint `cycle_id` 1, which is
#: the same tick by the only identity the schema recognises. Contract rule 7 turns the
#: `IntegrityError` into `ERROR`, the tick completes, engine 19 publishes nothing, and the
#: first tick's row survives untouched. That is the fail-closed outcome, not a defect.
MANAGE_CHAIN: tuple[BaseEngine, ...] = (
    PositionManagerEngine(),
    ExitEngine(),
    MemoryEngine(),
)


def build_chains() -> Chains:
    """Assemble the three runtime chains for the orchestrator.

    A named structure rather than three positional sequences: transposing ``guard`` with
    ``manage`` would type-check, pass a smoke test, and silently stop watching open
    positions.
    """
    return Chains(
        guard=GUARD_CHAIN,
        opportunity=OPPORTUNITY_CHAIN,
        manage=MANAGE_CHAIN,
    )
```

Each engine's `is_gate` as declared in its `engine.py` (grep of `is_gate` across `src/acsoe/engines/*/engine.py`): `exchange` False (line 69), `market_data_recorder` False (85), `market_sensor` False (135), `data_guard` **True** (79), `safety` **True** (104), `feature` False (88), `macro_context` False (59), `scout` **True** (174), `regime` False (68), `anomaly` **True** (94), `prediction` False (136), `order_book` False (104), `cost` **True** (95), `risk` **True** (180), `adaptive_router` False (91), `skeptic` **True** (134), `decision` **True** (121), `execution` False (188), `position_manager` False (171), `exit` False (177), `memory` False (145), `tournament` False (149). Eight gates, matching the registry table in `context/engine-contracts.md` lines 198–222, which `scripts/verify.py`'s `is_gate_matches_registry` asserts.

### C.2 The offline chain, verbatim

*Verbatim from `src/acsoe/cli/research.py`, lines 90–108:*

```python
#: Engine 20 ``tournament`` lands **here**, after engine 23, and never in
#: ``bootstrap.py``. C owns the class (spec 74); this names where it plugs in.
#:
#: Until it exists :func:`build_offline_chain` returns engine 23 alone, and
#: ``tests/cli/test_entrypoints.py`` carries the tripwire that goes red the moment
#: the module becomes importable and this file has not been updated. That is the
#: standing rule for a seam agreed by message: **a mock for a module that does not
#: exist yet needs a test that fails once it does.** A landed engine 20 that
#: nobody registered would leave `acsoe research` reporting a clean run of a chain
#: with a missing member, which is exactly the shape of failure this phase is
#: about — nothing red, and a leaderboard that is simply never written.
TOURNAMENT_MODULE: Final = "acsoe.engines.tournament.engine"
TOURNAMENT_ATTR: Final = "TournamentEngine"

#: The offline chain, in registry order: 23 ``backtest``, then 20 ``tournament``.
#:
#: Order is not alphabetical and not numeric. Engine 20 scores what engine 23's
#: run produced, so 23 runs first — `context/engine-contracts.md` fixes it.
OFFLINE_CHAIN: tuple[BaseEngine, ...] = (BacktestEngine(),)
```

*Verbatim from `src/acsoe/cli/research.py`, lines 133–148:*

```python
def build_offline_chain(*, digest_path: Path | None = None) -> tuple[BaseEngine, ...]:
    """Return the offline chain in registry order.

    Called by ``acsoe research`` and by ``scripts/verify.py``, which is why it
    takes no required argument: the criterion inspects ``is_gate`` on engines it
    never runs.

    ``digest_path`` is engine 20's training digest, passed from ``--digest``
    (spec 74). It is threaded through rather than read from config because a
    digest names one training run's output file, not a system-wide setting.
    """
    chain: tuple[BaseEngine, ...] = OFFLINE_CHAIN
    tournament = _tournament_engine(digest_path)
    if tournament is not None:
        chain = (*chain, tournament)
    return chain
```

Engine 23 `backtest` is `acsoe.research.backtest.BacktestEngine` (import at `cli/research.py` line 78); engine 20 is resolved by name from `acsoe.engines.tournament.engine.TournamentEngine` (lines 101–102). The registered chains are driven over history by `run_backtest` (lines 487–637): the same `Orchestrator` and `build_chains()` as the daemon, a `ReplayKrakenClient` wrapped in the `PaperBroker` (lines 552–559), and `_replay_orchestrator` (lines 640–663).

### C.3 One row per engine

All 23 numbers exist; **none is retired**. Engine 16 became a gate by operator ruling 2026-09-16 (`trading-invariants.md` lines 137–142); engine 8 stays a non-gate but halts the tick on `di_refused` under contract rule 6 (`engine-contracts.md` line 249). Engine 23 has no `engines/` directory: it lives in `src/acsoe/research/backtest.py` and is registered only in `cli/research.py` (`engine-contracts.md` line 224). The same table is `engines.csv` in pack 04.

| # | Module | Chain | Gate | Purpose (README first paragraph) | State keys read | State keys written | Reason codes (`contracts.py`) |
|---|---|---|---|---|---|---|---|
| 1 | `exchange` | guard | no | "The account picture, fetched fresh every tick and published for everything downstream: what the account holds, what it is charged, and what each pair's rules are." | nothing | `state["exchange"]`: `balances`, `fee_tier{maker_fee_pct, taker_fee_pct}`, `pair_rules.pairs[pair]{ordermin, costmin, tick_size, lot_decimals, pair_decimals, base, quote}`, `failed_fetches`, retained values | none (not a gate) |
| 2 | `market_data_recorder` | guard | no | "Every tick it drains whatever the WebSocket stream buffered since the last tick and appends it, verbatim, to the append-only archive in `data/raw/`." | `state["exchange"]` | `state["market_data_recorder"]` | none; never blocks |
| 3 | `market_sensor` | guard | no | "The decision-bar clock and the market-data view. Everything the opportunity chain hangs off starts here." | the stream (client) | `state["market_sensor"]`: `bar_closed`, `closed_bar_ts`, `interval_s`, `candles`, `quotes[pair]{bid, ask, spread_pct}`, `trade_ranges[pair]{low, high, count}` | none |
| 4 | `data_guard` | guard | **yes** | "The first real gate in the system: the engine that refuses to let the loop trade on data it does not trust" | `market_sensor`, `exchange` | `state["data_guard"]` | `market_data_stale`, `no_market_data`, `negative_spread`, `missing_candle` |
| 17 | `safety` | guard | **yes** | "The circuit breaker on the account" | the store only (`equity_snapshots`, `trades`, `block_records`, `positions`, `orders`) plus `state["trading_blocked_by"]` | `state["safety"]`; `freeze`/`close_all` command rows | `safety_inputs_unavailable`; conditions `drawdown`, `loss_streak`, `error_rate`, data outage |
| 5 | `feature` | opportunity | no | "Computes the feature vector for every pair engine 3 published candles for, on the tick where a decision bar closed … On every other tick it returns `PASS`" | `market_sensor` (`bar_closed`, `closed_bar_ts`, `interval_s`, `candles`) | `state["feature"]`: `pairs[pair]`, `bar_ts`, `row_ts`, `feature_names`, `gaps_in_range` | none (PASS on a non-bar tick) |
| 6 | `macro_context` | opportunity | no | "BTC's and ETH's feature rows, selected out of `state["feature"]`, renamed with a `macro_` prefix" | `feature` | `state["macro_context"].features` | none |
| 7 | `scout` | opportunity | **yes** | "The tradable universe: which Kraken pairs this account could legitimately trade **right now**" then one candidate ordered by expected move | `exchange` (`pair_rules`, `balances`), `market_sensor.quotes`, `feature` | `state["scout"]`: `pair`, `pairs`, `scanned`, `entered`, `excluded{reason: count}`, `rank_feature`, `rank_descending`, `ranked[]`, `rank_skipped`, `rank_run_ids` | `pair_rules_missing`, `no_live_quote`, `crypto_quoted`, `quote_not_provably_stable`, `no_quote_balance`, `no_fx_rate`, `insufficient_quote_balance`, `below_ordermin`, `below_costmin`, `barriers_below_tick_size`, `scout_inputs_unavailable`, `empty_universe`, `no_rankable_pair` |
| 12 | `regime` | opportunity | no | "Three labels: `trending`, `choppy`, `high_volatility`. Rule-based … It is not a gate and it never blocks." | `scout.pair`, `feature` | `state["regime"]`: `label`, `di_regime_shift` (always null) | `no_feature_row`, `regime_inputs_incomplete` (label null, no block) |
| 13 | `anomaly` | opportunity | **yes** | "is the candidate's market broken. A **data-quality** gate" | `scout.pair`, `feature` | `state["anomaly"]`: `score`, `threshold`, `anomalous`, `model_run_id` | `anomaly_unavailable`, `anomaly_inputs_incomplete`, `market_anomalous` |
| 8 | `prediction` | opportunity | no (halts on DI) | the predictor: calibrated barrier probabilities, expected move, DI, SHAP | `scout.pair`, `feature`, `macro_context` | `state["prediction"]`: `p_target`, `p_stop`, `p_timeout`, `expected_move_pct`, `is_buy`, `di`, `di_threshold`, `shap`, `model_run_id` | `prediction_unavailable`, `prediction_inputs_incomplete`, `di_refused`, `di_percentile_mismatch` |
| 9 | `order_book` | opportunity | no | "Estimates the slippage the candidate's **exit** would pay … the fourth term of invariant 5's friction" | `scout.pair`, `exchange.balances`, `exchange.pair_rules`, config `order_book.depth` | `state["order_book"]`: `estimated_slippage_pct`, `basis_notional`, `levels_consumed`, `best_bid`, `fill_price`, `depth` | `book_fetch_failed`, `book_unusable`, `book_too_thin`, `no_quote_balance`, `order_book_inputs_unavailable` (all mean "no estimate"; engine 10 refuses on the absence) |
| 10 | `cost` | opportunity | **yes** | the hurdle: `friction = maker + taker + spread + slippage`; trade only if `net_edge > hurdle_multiple × friction` | `exchange.fee_tier`, `exchange.failed_fetches`, `market_sensor.quotes[pair].spread_pct`, `prediction.expected_move_pct`, `order_book.estimated_slippage_pct`, `scout.pair`; config `trading.hurdle_multiple` | `state["cost"]`: `expected_move_pct`, `friction_pct`, `net_edge_pct`, `hurdle_pct`, `clears_hurdle`, `reason_code` | `net_edge_below_hurdle`, `spread_wider_than_move`, `cost_inputs_unavailable` |
| 11 | `risk` | opportunity | **yes** | "sizes a position, and refuses one that cannot be placed honestly" | `exchange` (`pair_rules`, `balances`), `market_sensor.quotes` (`ask`, `bid`), `scout.pair`, the store (equity, open positions, resting orders) | `state["risk"]`: `approved`, `qty`, `notional`, `risk_amount` (`qty` absent on a refusal) | `below_ordermin`, `below_costmin`, `insufficient_quote_balance`, `max_concurrent_positions`, `no_fx_rate`, `position_open_on_pair`, `entry_resting_on_pair`, `risk_inputs_unavailable` |
| 14 | `adaptive_router` | opportunity | no | "A weight per trained model version … **It is inert today, and that is stated rather than discovered**" | the leaderboard (store), `prediction` (`model_run_id`, `di`, `di_threshold`), `regime.label` | `state["adaptive_router"]`: `active_model_run_id`, `basis`, `regime`, `di_margin`, `weights` (only when any), `reason_code` | `leaderboard_empty`, `leaderboard_unreadable`, `leaderboard_truncated`, `no_model_beats_its_base_rate` |
| 15 | `skeptic` | opportunity | **yes** | "A learned opinion about this specific trade: how likely is the predictor's BUY call to be wrong. … It can only veto" | `scout.pair`, `feature`, `macro_context.features`, `prediction` (`is_buy`, `expected_move_pct`, probabilities) | `state["skeptic"]`: `p_wrong`, `threshold`, `vetoed`, `model_run_id` | `skeptic_unavailable`, `skeptic_veto` |
| 16 | `decision` | opportunity | **yes** (ruling 2026-09-16) | "decides one thing: whether every approving engine judged *this* tick's candidate … composes the order intent" | `market_sensor.closed_bar_ts`, `scout.pair`, `risk` (`approved`, `qty`), `cycle_id`, payloads of `prediction`, `order_book`, `cost`, `adaptive_router`, `skeptic` | `state["decision"]`: `intent`, `checked[]`, `coherent` | `pair_disagreement`, `stale_bar`, `input_missing`, `no_approved_quantity`, `decision_inputs_unavailable` |
| 18 | `execution` | opportunity | no | "places **exactly one** post-only limit buy, for the quantity engine 11 approved, at the best bid, under a `userref` derived from the pair and the bar" | `decision.intent`, `market_sensor.quotes[pair].bid`, `exchange.pair_rules.pairs[pair].pair_decimals` | `state["execution"]`: `orders[]`, `placed`, `userref`, `pair` | `entry_placed`, `entry_already_placed`, `post_only_would_cross`, `entry_unrecorded_at_exchange`, `entry_recovered_from_exchange`, `entry_at_exchange_is_not_a_limit` |
| 21 | `position_manager` | manage | no | "runs **every tick, in every mode, and never stops** … a position that exists has to be watched" | `system.close_intent`, `trading_blocked_by`, `market_sensor` (`quotes`, `trade_ranges`), `execution.orders`, `exchange.pair_rules`, the store | `state["position_manager"]`: `positions[]{value}`, `orders`, `positions_value`, `unrealised_pnl`, `triggered[]{position_id, barrier}`, `entry_orders_cancelled`, `hold_reason` | `position_unrecordable`; hold `data_guard_blocked` |
| 22 | `exit` | manage | no | "the only engine in this system that sells" — market sells on triggered barriers; liquidation on `close_intent` | `system.close_intent`, `trading_blocked_by`, `position_manager.triggered`, `exchange.pair_rules` (`lot_decimals`) | `state["exit"]`: `orders`, `positions`, `closed_trades[]{net_proceeds}`, `positions_closed` | `exits_placed`, `nothing_to_exit`, `data_guard_blocked`, `exit_already_placed`, `exit_incomplete` |
| 19 | `memory` | manage | no | "The single writer of relational rows" | `guard_blockers`, `cycle_id`, `trading_blocked_by`, `block_reason`, `block_status`, `scout`, `exchange.balances`, `position_manager`, `execution`, `exit`, `cost`, `prediction.shap`, `market_sensor.closed_bar_ts` | `state["memory"]` (counts, `shap_ref`); tables `block_records`, `rejections`, `approvals`, `positions`, `orders`, `trades`, `equity_snapshots`, `scout_tallies`; SHAP parquet | `engine_errored` (the `block_reason` it writes for an errored engine) |
| 20 | `tournament` | offline | no | "Scores every trained model version against realised outcomes and writes one `leaderboard` row per version"; hosts the promotion gate | the training digest, the out-of-sample parquet, the leaderboard; for the gate the run's trades and the trial ledger | `leaderboard` rows | `tournament_no_digest`, `tournament_no_oos`, `tournament_no_store`, `tournament_digest_mismatch`, `promotion_too_few_trades`, `promotion_lower_bound_not_above_zero`, `promotion_no_ledger`, `promotion_bad_trade` |
| 23 | `backtest` | offline | no | `research/backtest.py`: replays the archive through the registered chains (`ChainReplay`) under the real orchestrator | the archive via the replay client | store rows through engine 19, like any run | none |

### C.4 The orchestrator loop, verbatim

The contract's pseudocode (`context/engine-contracts.md` lines 95–145):

*Verbatim from `context/engine-contracts.md`, lines 95–145:*

````markdown
### The three runtime chains

Every tick runs the guard and manage chains. The opportunity chain runs only when the system is `running` and nothing has already blocked.

```
# 0. Read commands. Sets state["system"]["mode"] and close_intent.
consume_commands()

# 1. GUARD — every tick, every mode. Never breaks early.
state["guard_blockers"] = []
for engine in GUARD_CHAIN:                     # exactly: 1, 2, 3, 4, 17
    result = run(engine)
    state[engine.name] = result.data
    if result.blocks_trading:
        state["guard_blockers"].append(              # every blocker, for engine 19
            {"engine": engine.name, "reason": result.reason,
             "status": result.status})
        if "trading_blocked_by" not in state:        # the first one is primary
            state["trading_blocked_by"] = engine.name
            state["block_reason"] = result.reason
            state["block_status"] = result.status
        # the chain still finishes; only the opportunity chain is skipped

# 2. OPPORTUNITY — only if running and nothing blocked. May stop early.
if state["system"]["mode"] == "running" and "trading_blocked_by" not in state:
    for engine in OPPORTUNITY_CHAIN:           # 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, 16, 18
        result = run(engine)
        state[engine.name] = result.data
        if result.blocks_trading:
            state["trading_blocked_by"] = engine.name
            state["block_reason"] = result.reason
            state["block_status"] = result.status    # BLOCK or ERROR; see rule 7
            break
        if result.status is PASS:
            break                              # no candidate this cycle

# 3. MANAGE — every tick, every mode. Never stops.
#    Every engine still runs and still records. But 21 and 22 must not place
#    an exit when the guard rejected the data this tick, unless close_intent
#    is set. See "When the guard rejects the data, the manage chain holds".
for engine in MANAGE_CHAIN:                    # exactly: 21, 22, 19
    result = run(engine)
    state[engine.name] = result.data

# 4. Clear close_intent only once the close actually finished.
if state["system"]["close_intent"] \
        and state.get("position_manager", {}).get("entry_orders_cancelled") \
        and state.get("exit", {}).get("positions_closed"):
    state["system"]["close_intent"] = False
    mark_command_consumed()
```
````

The implementation, `src/acsoe/core/orchestrator.py`: `tick` (lines 201–223), the guard chain (457–478), the opportunity chain with the block/PASS stop (482–505), the manage chain (509–519), and the `close_intent` clearance (523–575):

*Verbatim from `src/acsoe/core/orchestrator.py`, lines 201–223:*

```python
    def tick(self) -> State:
        """Run one full tick and return the finished ``state``.

        ``state`` is a fresh dict every tick. Nothing survives to the next tick except
        ``state["system"]``, which this object carries across.
        """
        self._cycle_id += 1
        context = self._context()

        state: State = {
            "system": self._system,
            "cycle_id": self._cycle_id,
            "guard_blockers": [],
        }

        self._consume_commands()

        self._run_guard_chain(context, state)
        self._run_opportunity_chain(context, state)
        self._run_manage_chain(context, state)
        self._clear_close_intent_if_finished(state)

        return state
```

*Verbatim from `src/acsoe/core/orchestrator.py`, lines 455–519:*

```python
    # ---------------------------------------------------------------- step 1: guard

    def _run_guard_chain(self, context: EngineContext, state: State) -> None:
        """Every tick, every mode. Never breaks early.

        A block here does not stop the chain: `data_guard` rejecting the tick's data
        must not prevent `safety` from evaluating the account. Every blocker is recorded
        for engine 19; the first is the primary one that gates the opportunity chain.
        """
        for engine in self._chains.guard:
            result = self._run(engine, context, state)
            state[engine.name] = result.data
            if result.blocks_trading:
                state["guard_blockers"].append(
                    {
                        "engine": engine.name,
                        "reason": result.reason,
                        "status": str(result.status),
                    }
                )
                if "trading_blocked_by" not in state:
                    state["trading_blocked_by"] = engine.name
                    state["block_reason"] = result.reason
                    state["block_status"] = str(result.status)

    # ---------------------------------------------------------- step 2: opportunity

    def _run_opportunity_chain(self, context: EngineContext, state: State) -> None:
        """Only when running and nothing has blocked. Stops at the first block or PASS."""
        if self._system["mode"] != "running":
            self._log("opportunity_skipped", reason=f"mode is {self._system['mode']}")
            return
        if "trading_blocked_by" in state:
            self._log("opportunity_skipped", reason=f"blocked by {state['trading_blocked_by']}")
            return

        for engine in self._chains.opportunity:
            result = self._run(engine, context, state)
            state[engine.name] = result.data
            if result.blocks_trading:
                # The status travels with the name and the reason. An opportunity-chain
                # engine that raised has an empty payload (rule 7), and without this key
                # engine 19 could tell that apart from a BLOCK only by the emptiness -
                # which is also what a BLOCK with a missing reason_code looks like.
                # Invariant 12, operator ruling 2026-09-16.
                state["trading_blocked_by"] = engine.name
                state["block_reason"] = result.reason
                state["block_status"] = str(result.status)
                break
            if result.status is EngineStatus.PASS:
                break

    # --------------------------------------------------------------- step 3: manage

    def _run_manage_chain(self, context: EngineContext, state: State) -> None:
        """Every tick, every mode. Never stops.

        Engines 21 and 22 decide for themselves whether to place an exit — they read
        ``state["trading_blocked_by"]`` and ``state["system"]["close_intent"]`` and hold
        when the guard rejected the data. The orchestrator does not make that decision
        for them; it only guarantees they are given the chance to.
        """
        for engine in self._chains.manage:
            result = self._run(engine, context, state)
            state[engine.name] = result.data
```

*Verbatim from `src/acsoe/core/orchestrator.py`, lines 521–575:*

```python
    # ---------------------------------------------------------- step 4: close_intent

    def _clear_close_intent_if_finished(self, state: State) -> None:
        """Clear ``close_intent`` only when both engines report the close finished.

        A missing key reads as "not finished", never as "finished" — the same fail-closed
        default the gates use. An unregistered manage chain therefore cannot silently
        discard a pending liquidation, and a failed cancel or close survives into the
        next tick and is retried.
        """
        if not self._system.get("close_intent"):
            return

        cancelled = self._flag(state, "position_manager", "entry_orders_cancelled")
        closed = self._flag(state, "exit", "positions_closed")
        if cancelled and closed:
            self._system["close_intent"] = False
            self._log("close_all_complete")
            # Phase two of the two-phase consumption, and the only place it happens for
            # `close_all`. This called `store.mark_close_all_consumed` until the Phase 1
            # close — another method the store has never had, so the row stayed claimed
            # and unconsumed after a *successful* liquidation and was re-applied by the
            # startup replay on the next restart, closing an account that was already
            # flat. The id is the one carried from the tick that accepted the command.
            store = self._store()
            if store is not None and self._pending_close_all_id is not None:
                self._consume(store, self._pending_close_all_id, _to_micros(self._clock.now()))
            self._pending_close_all_id = None
        else:
            self._log("close_all_pending", cancelled=cancelled, closed=closed)

    @staticmethod
    def _flag(state: State, engine_name: str, field: str) -> bool:
        """Only the boolean ``True`` means finished. Everything else means not.

        This read `bool(payload.get(field, False))` until spec 81, which is a
        fail-open on the kill switch: `bool("false")` is `True`, and so is `bool(1)`,
        so a publisher that serialised ``entry_orders_cancelled`` through anything
        text-shaped would clear `close_intent` **with entry orders still resting on the
        book**, and the orchestrator would then mark the `close_all` row consumed. Four
        of seven present-but-not-`True` shapes cleared a liquidation; the other three
        (`[]`, `{}`, `0`) happened to be falsy, which is what made the hole easy to read
        past.

        It was unreachable until Phase 6 because the manage chain was engine 19 alone
        and both payloads were always absent — the branch stopped being dead on exactly
        the change that gave it something to be wrong about. `engine-contracts.md` says
        these two fields are booleans and that absent or false always means "not
        finished"; a value of any other *type* is a publisher whose shape changed, and
        the fail-closed reading of a changed shape is also "not finished".
        """
        payload = state.get(engine_name)
        if not isinstance(payload, dict):
            return False
        return payload.get(field) is True
```

What goes into `state`: the fresh dict per tick holds `system` (the one persistent region: `mode`, `close_intent`), `cycle_id`, `guard_blockers`, then each engine's `data` under its own name, plus `trading_blocked_by`, `block_reason`, `block_status` set by the first blocker (`engine-contracts.md` lines 261–268). An uncaught exception becomes `ERROR` with `blocks_trading=True` and an empty payload (`orchestrator.py` lines 173–197).

### C.5 The console

- Port **8765** from `config/default.yaml` line 27 (`console.port: 8765`; `README.md`: "default http://127.0.0.1:8765"). Poll interval 500 ms, stale-after 120,000 ms (lines 28–29).
- It is a FastAPI app (`src/acsoe/console/app.py`) with routes `/health`, `/` (HTML), `/api/state`, `/api/feed`, `/api/history`, `/api/research`, a WebSocket `/ws`, and `POST /api/command/{name}` (lines 228–284). One template, `templates/index.html`, with panes headed **Open positions, Cycle feed, Refused candidates, Closed trades, Leaderboard, Explanations**, and a status band.
- **How it reads state:** only from SQLite, through a read-only connection: `src/acsoe/console/reader.py` lines 7–13: "**The connection is read-only.** … the SQLite connection is opened through a `file:...?mode=ro` URI, so a write is refused by the database engine rather than by an author's discipline. Spec 24 opens its own narrow read-write connection for the `commands` table alone". The commands connection sits behind a SQLite authorizer that denies every table but `commands` (tracker line 855). Time comes from an injected clock (reader lines 15–20). Restart detection compares `run_id` against the previous `runs` row server-side (lines 22–25). It pushes on a watermark (`MAX(updated_at)` across the rendered tables, migration 0001 lines 32–33).
- It holds no credentials and cannot place an order (`README.md`; invariant 13). Its three commands are `activate`, `freeze`, `close_all` (`architecture-context.md` lines 252–262).

### C.6 The client layer

**Kraken client** (`src/acsoe/clients/kraken/`: `rest.py`, `ws.py`, `client.py`, `limiter.py`, `contracts.py`, `errors.py`, `replay.py`, `replay_scenario.py`). Endpoints as string literals in `rest.py` lines 99–102: public `GET /0/public/AssetPairs`, `GET /0/public/Depth`; private `POST /0/private/TradeVolume`, `POST /0/private/Balance`. WebSocket v2 at `wss://ws.kraken.com/v2` (`ws.py` line 56), channels `book`, `ticker`, `trade` and `instrument`. The four order calls (`add_order`, `cancel_order`, `query_orders`, `open_orders`) exist on the surface (spec 84) and **refuse until Phase 8** (`cli/engine.py` lines 95–99). Rate limiting is the project's own token bucket (`config/default.yaml` lines 165–170). Retention of last-known-good `Balance` and `AssetPairs` for invariant 14 lives here (`trading-invariants.md` lines 30–37).

**Paper broker** (`src/acsoe/clients/paper/broker.py`, `fills.py`): wraps the real client, forwards every read and stream call, answers the four order calls itself, never makes a transport call from an order method, never writes a relational row (`broker.py` lines 1–30). Fill rules are pure functions (`fills.py` lines 1–30): a post-only buy at or above the best ask is rejected; a resting buy at L fills in full at L only when a trade prints **strictly below** L; partial fills are not simulated; a market sell walks the bid side of the fetched book. The paper ledger is quote-side only (`fills.py` line 188). Fees come from the fee tier the wrapped client returns on the fill tick, with no fallback.

**Replay client** (`replay.py` lines 1–40, quoted in full in pack 02 §C.4's context): refuses construction outside replay mode; serves the period's real trades from the weekly partitions never past `now`; a **synthetic book** per pair — centred on the last traded price, half the bucket's spread either side, ten evenly spaced bid levels from the half-spread out to the bucket's depth-to-$10,000 distance (`replay_scenario.py`, `BOOK_LEVELS`; `docs/dataset/phase-7-findings.md` lines 639–641); a pair with no trade in the trailing 24 h has no quote, never a zero spread; the quote is stamped `now` (D7); pair rules from the recorded 2026 snapshot; the fee from the declared schedule via the `TradeVolume` surface; no balance and no order (the broker answers both).

**Paper versus live, where the difference lives.** `context/architecture-context.md` lines 283–289: "The same engine code runs in all three modes. Mode differences live only in the client layer." `cli/engine.py` line 131: `if config.mode == "paper": kraken = PaperBroker(real, store=store, config=config, clock=clock)`. Live and replay get the bare client (line 95); the replay CLI wraps `ReplayKrakenClient` in the same `PaperBroker` (`cli/research.py` lines 552–553).

**Engines 18, 21 and 22 run the same code in both modes — CONFIRMED.** `broker.py` lines 8–12: "Engines 18, 21 and 22 call `context.clients.kraken.add_order / cancel_order / query_orders / open_orders` identically in every mode and never learn which object they hold — which is the property that makes a paper run and a live run the same code path rather than two." The three engine modules contain no mode branch (grep `mode` in `engines/execution/engine.py`, `engines/position_manager/engine.py`, `engines/exit/engine.py`: no read of `context.mode` — the only occurrences are in docstrings). One qualification the report must carry: the live client's order methods refuse today, so the live path has never executed an order end to end (Phase 8).

### C.7 The database

Seven forward-only migrations in `db/migrations/`, reproduced verbatim. The money rule as written (0001 lines 11–23): "Money is an exact decimal string. … Money columns are therefore declared `ANY` with `CHECK (typeof(col) = 'text')`, which is the only declaration in SQLite that actually refuses a float."

*Verbatim from `db/migrations/0001_initial.sql`, lines 1–347:*

```sql
-- 0001_initial.sql — the full Phase 0 relational schema.
--
-- Forward-only. Never edit an applied migration; add a new numbered file instead.
--
-- Conventions, and why:
--
--   Every table is STRICT. Without it SQLite's dynamic typing lets any column hold any
--   type: a text `ts` sorts as text, an integer `cycle_id` can arrive as a string, and
--   the ordering the outage counter depends on quietly stops being numeric.
--
--   Money is an exact decimal string. `Decimal` in Python, exact string in SQLite,
--   conversion only at the store-client boundary. A float equity series drifts, and a
--   drifting equity series moves the drawdown threshold that liquidates the account.
--
--   Money columns are therefore declared `ANY` with `CHECK (typeof(col) = 'text')`,
--   which is the only declaration in SQLite that actually refuses a float. This looks
--   wrong and is not: a column declared `TEXT` has TEXT *affinity*, so an inserted
--   float is silently converted to text BEFORE any CHECK runs — `0.1 + 0.2` lands as
--   the string '0.3' and `typeof()` reports 'text'. Declaring `TEXT` enforces nothing.
--   STRICT does not close it either; its TEXT columns convert numbers the same way.
--   `ANY` is the one type that stores a value as given, so the CHECK sees a real REAL
--   and rejects it. The *contents* of these columns are guaranteed TEXT far more
--   strongly than a `TEXT` declaration would have guaranteed it.
--
--   Timestamps are INTEGER microseconds since the Unix epoch, UTC. They come from
--   `context.now`; nothing here reads a clock.
--
--   `cycle_id` is INTEGER and is minted per tick *within a run*, restarting at 1 with
--   each process. It is never unique on its own and never an ordering key: a tick is
--   identified by `(run_id, cycle_id)` and a cross-restart sequence is ordered by `ts`.
--
--   `updated_at` is on every table the console renders. `MAX(updated_at)` across those
--   tables is the monotonic watermark `ui-context.md` has the console poll.

-- ---------------------------------------------------------------------------
-- runs — one row per daemon process, written by the orchestrator at startup.
-- The console detects a silent restart by comparing the current `run_id` against
-- the `run_id` of the previous row (`ui-context.md`, "Restart is visible").
-- ---------------------------------------------------------------------------
CREATE TABLE runs (
    id             INTEGER PRIMARY KEY,
    run_id         TEXT    NOT NULL UNIQUE,
    mode           TEXT    NOT NULL CHECK (mode IN ('paper', 'live', 'replay')),
    started_at     INTEGER NOT NULL,
    ended_at       INTEGER,
    acsoe_version  TEXT,
    config_digest  TEXT,
    updated_at     INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_runs_started_at ON runs (started_at);

-- ---------------------------------------------------------------------------
-- commands — the console and engine 17 `safety` write; the orchestrator reads.
--
-- Consumption is two-phase so a crash cannot swallow a kill switch:
-- `claimed_at` is stamped when the reader applies the effect to state["system"],
-- `consumed_at` only when the effect is complete. A row with `claimed_at` set and
-- `consumed_at` null is an interrupted command and is re-applied at startup.
--
-- `command` deliberately carries NO CHECK constraint. An unrecognised command is
-- ignored and logged as a warning by the reader (`architecture-context.md`); a CHECK
-- here would make that case unreachable and untestable.
-- ---------------------------------------------------------------------------
CREATE TABLE commands (
    id                INTEGER PRIMARY KEY,
    command           TEXT    NOT NULL,
    source            TEXT    NOT NULL CHECK (source IN ('console', 'safety')),
    reason            TEXT,
    payload           TEXT,
    created_at        INTEGER NOT NULL,
    created_by_run_id TEXT,
    claimed_at        INTEGER,
    claimed_by_run_id TEXT,
    consumed_at       INTEGER,
    updated_at        INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_commands_pending ON commands (created_at)
    WHERE claimed_at IS NULL;

CREATE INDEX idx_commands_unconsumed ON commands (created_at)
    WHERE consumed_at IS NULL;

-- ---------------------------------------------------------------------------
-- block_records — one row per guard blocker per tick, written by engine 19 `memory`.
--
-- Columns are fixed by `context/architecture-context.md` because engine 17 `safety`
-- derives its outage count from this table.
--
-- The partial unique index enforces invariant 12's "is_primary on the first only":
-- two engines each claiming to have gated the opportunity chain would destroy the
-- audit trail, so a second primary for one tick fails at the database rather than
-- being resolved by whichever write landed last.
--
-- It is scoped `(run_id, cycle_id)`, not `(cycle_id)`. `cycle_id` restarts with the
-- process, so two runs necessarily reuse the same low values — and the Phase 3
-- criterion requires a seeded outage run spanning two `run_id`s precisely so that
-- ordering by `ts` rather than `cycle_id` is actually exercised. A tick is
-- `(run_id, cycle_id)`; the constraint is one primary per tick.
-- ---------------------------------------------------------------------------
CREATE TABLE block_records (
    id           INTEGER PRIMARY KEY,
    cycle_id     INTEGER NOT NULL,
    run_id       TEXT    NOT NULL,
    ts           INTEGER NOT NULL,
    blocked_by   TEXT    NOT NULL,
    block_reason TEXT    NOT NULL,
    is_primary   INTEGER NOT NULL CHECK (is_primary IN (0, 1)),
    status       TEXT    NOT NULL CHECK (status IN ('BLOCK', 'ERROR')),
    updated_at   INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_block_records_ts ON block_records (ts);

CREATE INDEX idx_block_records_run_cycle ON block_records (run_id, cycle_id);

-- `safety`'s error rate: rows in the trailing hour with status = 'ERROR'.
CREATE INDEX idx_block_records_status_ts ON block_records (status, ts);

-- `safety`'s outage count: the trailing run of ticks carrying a `data_guard` row.
CREATE INDEX idx_block_records_blocked_by_ts ON block_records (blocked_by, ts);

CREATE UNIQUE INDEX ux_block_records_primary ON block_records (run_id, cycle_id)
    WHERE is_primary = 1;

-- ---------------------------------------------------------------------------
-- equity_snapshots — one row per tick, written by engine 19 `memory`.
--
-- `safety` reads the latest row's `equity` and `peak_equity`; drawdown is
-- (peak_equity - equity) / peak_equity. The Phase 7 alpha attribution reads the full
-- curve *including cash periods*, which is why the cash and unrealised components are
-- stored rather than derived from trades.
-- ---------------------------------------------------------------------------
CREATE TABLE equity_snapshots (
    id                  INTEGER PRIMARY KEY,
    cycle_id            INTEGER NOT NULL,
    run_id              TEXT    NOT NULL,
    ts                  INTEGER NOT NULL,
    currency            TEXT    NOT NULL,
    equity              ANY     NOT NULL CHECK (typeof(equity) = 'text'),
    peak_equity         ANY     NOT NULL CHECK (typeof(peak_equity) = 'text'),
    cash                ANY     NOT NULL CHECK (typeof(cash) = 'text'),
    positions_value     ANY     NOT NULL CHECK (typeof(positions_value) = 'text'),
    unrealised_pnl      ANY     NOT NULL CHECK (typeof(unrealised_pnl) = 'text'),
    realised_pnl_cum    ANY     NOT NULL CHECK (typeof(realised_pnl_cum) = 'text'),
    open_position_count INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_equity_snapshots_ts ON equity_snapshots (ts);

CREATE UNIQUE INDEX ux_equity_snapshots_tick
    ON equity_snapshots (run_id, cycle_id);

-- ---------------------------------------------------------------------------
-- positions — what the console renders and what `safety` counts.
--
-- The partial unique index is invariant 6, "one open position per pair", enforced by
-- the database rather than by convention.
-- ---------------------------------------------------------------------------
CREATE TABLE positions (
    position_id    TEXT    PRIMARY KEY,
    run_id         TEXT    NOT NULL,
    cycle_id       INTEGER NOT NULL,
    pair           TEXT    NOT NULL,
    base           TEXT    NOT NULL,
    quote          TEXT    NOT NULL,
    side           TEXT    NOT NULL CHECK (side = 'long'),
    status         TEXT    NOT NULL CHECK (status IN ('open', 'closed')),
    qty            ANY     NOT NULL CHECK (typeof(qty) = 'text'),
    entry_price    ANY     NOT NULL CHECK (typeof(entry_price) = 'text'),
    target_price   ANY     NOT NULL CHECK (typeof(target_price) = 'text'),
    stop_price     ANY     NOT NULL CHECK (typeof(stop_price) = 'text'),
    timeout_at     INTEGER NOT NULL,
    entry_userref  INTEGER,
    last_price     ANY     CHECK (last_price IS NULL OR typeof(last_price) = 'text'),
    unrealised_pnl ANY     CHECK (unrealised_pnl IS NULL OR typeof(unrealised_pnl) = 'text'),
    opened_at      INTEGER NOT NULL,
    closed_at      INTEGER,
    trade_id       TEXT,
    updated_at     INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_positions_status ON positions (status);

CREATE INDEX idx_positions_pair_status ON positions (pair, status);

CREATE UNIQUE INDEX ux_positions_open_pair ON positions (pair)
    WHERE status = 'open';

-- ---------------------------------------------------------------------------
-- orders — every order, including a resting post-only entry.
--
-- Keyed by `userref` so the invariant 8 idempotency check ("never place an order
-- without checking whether that userref already exists") is a primary-key lookup
-- rather than a scan.
--
-- `safety` counts rows where status = 'resting'; engine 21 cancels them.
-- ---------------------------------------------------------------------------
CREATE TABLE orders (
    userref        INTEGER PRIMARY KEY,
    order_id       TEXT,
    run_id         TEXT    NOT NULL,
    cycle_id       INTEGER NOT NULL,
    position_id    TEXT,
    pair           TEXT    NOT NULL,
    side           TEXT    NOT NULL CHECK (side IN ('buy', 'sell')),
    intent         TEXT    NOT NULL CHECK (intent IN ('entry', 'exit')),
    order_type     TEXT    NOT NULL CHECK (order_type IN ('limit', 'market')),
    oflags         TEXT    NOT NULL DEFAULT '',
    status         TEXT    NOT NULL CHECK (
                       status IN ('pending', 'resting', 'filled',
                                  'cancelled', 'rejected', 'expired')),
    qty            ANY     NOT NULL CHECK (typeof(qty) = 'text'),
    limit_price    ANY     CHECK (limit_price IS NULL OR typeof(limit_price) = 'text'),
    filled_qty     ANY     NOT NULL CHECK (typeof(filled_qty) = 'text'),
    avg_fill_price ANY     CHECK (avg_fill_price IS NULL OR typeof(avg_fill_price) = 'text'),
    fee            ANY     CHECK (fee IS NULL OR typeof(fee) = 'text'),
    placed_at      INTEGER NOT NULL,
    closed_at      INTEGER,
    updated_at     INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_orders_status ON orders (status);

CREATE INDEX idx_orders_order_id ON orders (order_id);

CREATE INDEX idx_orders_position_id ON orders (position_id);

-- ---------------------------------------------------------------------------
-- trades — one row per closed round trip.
--
-- `safety` reads the trailing run ordered by `closed_at`, using `realised_pnl` and
-- `outcome`, for the consecutive-loss limit.
--
-- Invariant 7 requires FX exposure against the reporting currency to be recorded per
-- trade rather than silently absorbed into PnL, hence both the quote-currency and
-- reporting-currency PnL and the two FX rates.
--
-- Invariant 2 and invariant 14 both require that any tolerated fetch failure or
-- paper-mode fallback is recorded on the resulting trade, so the fill is never
-- mistaken for one priced on good data. `fallbacks_used` is a JSON array of names.
-- ---------------------------------------------------------------------------
CREATE TABLE trades (
    trade_id           TEXT    PRIMARY KEY,
    position_id        TEXT,
    run_id             TEXT    NOT NULL,
    cycle_id           INTEGER NOT NULL,
    pair               TEXT    NOT NULL,
    base               TEXT    NOT NULL,
    quote              TEXT    NOT NULL,
    side               TEXT    NOT NULL CHECK (side = 'long'),
    qty                ANY     NOT NULL CHECK (typeof(qty) = 'text'),
    entry_price        ANY     NOT NULL CHECK (typeof(entry_price) = 'text'),
    exit_price         ANY     NOT NULL CHECK (typeof(exit_price) = 'text'),
    entry_fee          ANY     NOT NULL CHECK (typeof(entry_fee) = 'text'),
    exit_fee           ANY     NOT NULL CHECK (typeof(exit_fee) = 'text'),
    entry_userref      INTEGER,
    exit_userref       INTEGER,
    opened_at          INTEGER NOT NULL,
    closed_at          INTEGER NOT NULL,
    outcome            TEXT    NOT NULL CHECK (
                           outcome IN ('target', 'stop', 'timeout', 'liquidation')),
    realised_pnl       ANY     NOT NULL CHECK (typeof(realised_pnl) = 'text'),
    realised_pnl_pct   ANY     NOT NULL CHECK (typeof(realised_pnl_pct) = 'text'),
    realised_pnl_quote ANY     NOT NULL CHECK (typeof(realised_pnl_quote) = 'text'),
    reporting_currency TEXT    NOT NULL,
    fx_rate_entry      ANY     NOT NULL CHECK (typeof(fx_rate_entry) = 'text'),
    fx_rate_exit       ANY     NOT NULL CHECK (typeof(fx_rate_exit) = 'text'),
    fallbacks_used     TEXT    NOT NULL DEFAULT '[]',
    updated_at         INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_trades_closed_at ON trades (closed_at);

CREATE INDEX idx_trades_pair ON trades (pair);

-- ---------------------------------------------------------------------------
-- rejections — one candidate refused, with its reason and its SHAP row.
--
-- Distinct from `block_records`: a rejection is one *candidate*, a block record is one
-- *tick*, and most blocked ticks never had a candidate at all. They join on
-- (run_id, cycle_id).
--
-- `reason_code` is machine-readable for research; `reason` is written for the operator,
-- because the console renders it ("Net edge -0.21% after fees", not `cost_gate_fail`).
-- The economics columns are exact decimal strings: they are derived from live fees and
-- they gate a trade, so they are money, not statistics.
-- ---------------------------------------------------------------------------
CREATE TABLE rejections (
    id                INTEGER PRIMARY KEY,
    cycle_id          INTEGER NOT NULL,
    run_id            TEXT    NOT NULL,
    ts                INTEGER NOT NULL,
    pair              TEXT    NOT NULL,
    rejected_by       TEXT    NOT NULL,
    reason_code       TEXT    NOT NULL,
    reason            TEXT    NOT NULL,
    expected_move_pct ANY     CHECK (expected_move_pct IS NULL OR typeof(expected_move_pct) = 'text'),
    friction_pct      ANY     CHECK (friction_pct IS NULL OR typeof(friction_pct) = 'text'),
    net_edge_pct      ANY     CHECK (net_edge_pct IS NULL OR typeof(net_edge_pct) = 'text'),
    hurdle_pct        ANY     CHECK (hurdle_pct IS NULL OR typeof(hurdle_pct) = 'text'),
    candidate_score   REAL,
    shap_ref          TEXT,
    details           TEXT,
    updated_at        INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_rejections_ts ON rejections (ts);

CREATE INDEX idx_rejections_run_cycle ON rejections (run_id, cycle_id);

CREATE INDEX idx_rejections_rejected_by ON rejections (rejected_by);

-- ---------------------------------------------------------------------------
-- leaderboard — trained model versions ranked by out-of-sample performance.
--
-- Metrics are statistics, so REAL is correct for them (`code-standards.md`: float is
-- fine for features, indicators, model inputs and statistics). `net_pnl` is money and
-- is therefore an exact decimal string like every other money column.
-- ---------------------------------------------------------------------------
CREATE TABLE leaderboard (
    id                 INTEGER PRIMARY KEY,
    model_id           TEXT    NOT NULL,
    model_version      TEXT    NOT NULL,
    training_run_id    TEXT,
    trained_at         INTEGER NOT NULL,
    fold               TEXT,
    n_trades           INTEGER NOT NULL,
    win_rate           REAL,
    sharpe             REAL,
    deflated_sharpe    REAL,
    alpha              REAL,
    beta               REAL,
    brier              REAL,
    net_pnl            ANY     CHECK (net_pnl IS NULL OR typeof(net_pnl) = 'text'),
    reporting_currency TEXT,
    promoted           INTEGER NOT NULL CHECK (promoted IN (0, 1)),
    notes              TEXT,
    updated_at         INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_leaderboard_model ON leaderboard (model_id, model_version);

CREATE INDEX idx_leaderboard_trained_at ON leaderboard (trained_at);
```

*Verbatim from `db/migrations/0002_persisted_system_mode.sql`, lines 1–66:*

```sql
-- 0002_persisted_system_mode.sql — spec 31.
--
-- Forward-only and purely additive: two nullable columns on `runs`. No existing
-- column or table is altered, nothing is dropped, and no table is added — so the
-- documented table set of `architecture-context.md` is unchanged and
-- `db_migrates_from_empty` needs no lead edit.
--
-- WHY A COLUMN ON `runs` AND NOT A SINGLE-ROW STATE TABLE
--
--   Spec 31 offers both shapes and requires the value to be readable **by
--   `run_id`**, so the console can tell *this* run's mode from a previous one's.
--
--   A single-row state table can only satisfy that by carrying a `run_id` column
--   of its own and having every reader compare it — which is `runs`' identity,
--   re-implemented with no UNIQUE constraint behind it. On `runs` the scoping is
--   structural rather than conventional: one row per daemon process, `run_id`
--   already UNIQUE, so a previous run's mode cannot leak into this run's read
--   because it is physically in a different row. There is no query you can get
--   wrong.
--
--   Three further consequences, all in the same direction:
--
--   - Lifecycle matches exactly. Mode is a property of one daemon process and
--     `runs` is one row per daemon process. A global single-row table would hold
--     one row for a thing whose natural cardinality is N, and would need its own
--     answer to "whose mode is this".
--   - `runs` is already in `StoreClient.WATERMARK_TABLES`, so persisting a mode
--     moves the console's poll watermark for free. A new table would have to be
--     added to that tuple, changing behaviour under every existing watermark test
--     mid-phase.
--   - A new table is a lead escalation (`db_migrates_from_empty` asserts the
--     documented table set, and `architecture-context.md` carries the storage
--     table). A column is not. Same result, no gate to reopen.
--
-- WHY THE COLUMN IS NOT CALLED `mode`
--
--   `runs.mode` already exists and holds paper/live/replay. The system mode is a
--   different axis entirely — idle/running/frozen — and `ui-context.md` says so in
--   as many words. Two columns called `mode` on one row is the kind of collision
--   that reads fine and is wrong.
--
-- WHY `system_mode_at` IS SEPARATE FROM `updated_at`
--
--   `runs.updated_at` is bumped by any write to the row, so it cannot answer "how
--   old is this mode reading" — the one question an operator asks of a status band
--   that might be stale. Recording it costs a nullable integer; not recording it
--   destroys the fact, and this migration is forward-only.
--
-- THIS VALUE IS WRITTEN FOR THE CONSOLE TO READ, NOT FOR THE DAEMON TO RESUME FROM.
--
--   Mode is still never restored from the store. A daemon always starts `idle` and
--   only reaches `running` through an `activate` command; a crashed daemon comes
--   back not trading. Nothing may read this column back into `state["system"]`.
--   The writer is the command reader in `core/`, which is already the single
--   writer of `state["system"]["mode"]`; the reader is the console.

-- NULL means "no daemon has written a mode for this run yet", which the console
-- renders as an idle reading. It is a distinct fact from 'idle', which means a
-- daemon actively reported being idle, and the two are deliberately not collapsed:
-- inferring one from the other is how a band ends up confidently wrong.
ALTER TABLE runs ADD COLUMN system_mode TEXT
    CHECK (system_mode IS NULL OR system_mode IN ('idle', 'running', 'frozen'));

-- Microseconds since the Unix epoch, UTC, from `context.now`. Nothing in this
-- package reads a clock.
ALTER TABLE runs ADD COLUMN system_mode_at INTEGER;
```

*Verbatim from `db/migrations/0003_position_hold_reason.sql`, lines 1–89:*

```sql
-- 0003_position_hold_reason.sql — the lead's ruling of 2026-09-16 on C's escalation.
--
-- Forward-only and purely additive: one nullable column on `positions`. No existing
-- column or table is altered, nothing is dropped, and no table is added — so the
-- documented table set of `architecture-context.md` and `EXPECTED_TABLES` are
-- unchanged, as are `EXPECTED_INDEXES` and every existing CHECK.
--
-- WHY THE DATABASE HAS TO CARRY IT AT ALL
--
--   Spec 101 asks the console to render *why* the manage chain held. Engine 21
--   publishes `hold_reason` into `state["position_manager"]`, engine 19 republishes it
--   into `state["memory"]`, and `state` is rebuilt from nothing every tick. The console
--   is a **separate process** reading this SQLite file, so a value that only ever lives
--   in `state` is a value the console can never see.
--
-- WHY IT IS NOT INFERRED FROM `block_records`
--
--   A `data_guard` row for the tick is *almost* the same fact and is not the same fact.
--   It says the guard rejected the tick's data; it does not say the manage chain held,
--   which is engine 21's decision and which invariant 14 suspends outright during a
--   liquidation — `hold_reason` is null throughout one while the block row is still
--   written. Inferring one from the other was explicitly rejected, on the same grounds
--   `engine-contracts.md` already rejected inferring the system mode from the `commands`
--   trail: a derived reading is confidently wrong in exactly the cases that matter.
--
-- WHY A COLUMN ON `positions` AND NOT A NEW TABLE
--
--   The hold is per position and is read per position: the console renders it on the
--   position row it is already drawing, and a position is the only thing that can be
--   held. `positions` is already in `StoreClient.WATERMARK_TABLES`, so writing a hold
--   moves the console's poll watermark for free. A new table would need adding to that
--   tuple, would change behaviour under every existing watermark test mid-phase, and is
--   a lead escalation in its own right because `db_migrates_from_empty` asserts the
--   documented table set.
--
-- THE THREE CONDITIONS OF THE RULING, AND THE SECOND IS THE ONE THAT MATTERS
--
--   1. **Engine 19 `memory` is the only writer** (spec 98, C). Engine 21 decides the
--      hold and publishes it; engine 22 never touches it; nothing else writes this
--      column. One writer is what stops two engines disagreeing about one tick.
--
--   2. **It is cleared to NULL on every tick that did not hold.** This column is a fact
--      about *now*, exactly like `last_price`, and not an event log. A hold written once
--      and never cleared renders an hour-old hold forever, so the console would report a
--      paused manage chain over one that is running normally — worse than rendering
--      nothing, because it is an assertion rather than an absence. There is no CHECK that
--      can enforce this: "was there a hold on the tick that wrote this row" is not a
--      property of the row. It is a property of the writer, and it is pinned by engine
--      19's tests.
--
--   3. **NULL means "did not hold", never "unknown".** The two are not collapsed here for
--      the same reason `runs.system_mode` does not collapse NULL and 'idle'. Because NULL
--      is load-bearing, the one thing the database *can* refuse is the empty string —
--      the usual way "unknown" gets smuggled past a nullable column as a non-null value
--      that renders as nothing. It is refused below.
--
-- WHY THERE IS NO CHECK ENUMERATING THE HOLD REASONS
--
--   `runs.system_mode` carries one because idle/running/frozen is a closed set the
--   console must render as a status band. Hold reasons are not a closed set: engine 21
--   declares them in `engines/position_manager/contracts.py` and the console maps them in
--   `console/format.py`'s `REASON_PROSE`. A CHECK would be a **third** copy of that list
--   and the only one that cannot be corrected without another migration, so it would be
--   the copy that drifts. The list is already enforced where it can be kept true: spec
--   99's walking test fails at test time on a code the console cannot render, rather than
--   the database failing at runtime on a hold it has never seen.

-- NULL means the manage chain did not hold on the tick that last wrote this row. It does
-- not mean "unknown" and it does not mean "not checked". A non-null value is one of
-- engine 21's hold reasons, rendered by the console through `REASON_PROSE`.
--
-- The CHECK refuses a blank string only: '', '   ' and a lone tab are none of them a hold
-- reason and none of them NULL. Each renders as nothing in the console while being a
-- non-null value that every `IS NOT NULL` read takes as "held".
--
-- The second argument to `trim()` is not decoration. **SQLite's one-argument `trim()`
-- strips spaces and nothing else** — not tabs, not newlines — so `trim(char(9)) <> ''` is
-- true and a tab would have passed a CHECK written the obvious way. This was found by the
-- parametrised test rather than by reading, which is why the parametrisation carries a tab
-- and not three kinds of space. The character set below is the ASCII whitespace Python's
-- `str.strip()` removes, so the database refuses what `PositionRow._a_hold_reason_or_null`
-- refuses. Python remains the stricter of the two on exotic Unicode whitespace, which is
-- the safe direction: the row model is the only supported way in.
ALTER TABLE positions ADD COLUMN hold_reason TEXT
    CHECK (
        hold_reason IS NULL
        OR trim(hold_reason, ' ' || char(9) || char(10) || char(11) || char(12) || char(13))
           <> ''
    );
```

*Verbatim from `db/migrations/0004_leaderboard_base_rate_brier.sql`, lines 1–47:*

```sql
-- 0004_leaderboard_base_rate_brier.sql — approved by the lead 2026-09-16.
--
-- Forward-only and purely additive: one nullable column on `leaderboard`. No existing
-- column or table is altered, nothing is dropped, and no table is added — so the
-- documented table set of `architecture-context.md`, `EXPECTED_TABLES` and
-- `EXPECTED_INDEXES` are all unchanged and `db_migrates_from_empty` needs no edit.
--
-- WHAT IT IS
--
--   The Brier score of the **base rate** on the same fold: the score a model that
--   ignored its inputs and predicted the fold's own class frequency every time would
--   have got. It is the null hypothesis `brier` is measured against — a Brier of 0.24
--   is skill on a balanced fold and is worse than doing nothing on a fold that was 90%
--   one class.
--
-- WHY IT IS A COLUMN AND NOT A DERIVATION
--
--   Engine 20 `tournament` already computes it per fold and **discards it for want of
--   a column**, so this is recovering a number the system has rather than adding work.
--
--   C nearly derived it instead, as `win_rate * (1 - win_rate)`, and caught the reason
--   that is wrong before it shipped: `brier` is computed over **every** row of the
--   fold, and `win_rate` is over the **BUY subset only**. Two different populations, so
--   the derived figure would be a plausible number that answers a different question —
--   and engine 14's weighting rule would rank models against a baseline none of them
--   was measured on. Worth stating in the schema, because the derivation will look
--   reasonable again to the next person who wants to avoid a migration.
--
-- WHY `REAL` AND NOT AN EXACT DECIMAL STRING
--
--   It is a statistic, and `code-standards.md` allows `float` for "features,
--   indicators, model inputs and statistics". Every other metric on this table is
--   `REAL` for the same reason; `net_pnl` is the one money column here and stays an
--   exact decimal string. A money column added as `REAL` is the defect
--   `test_every_money_column_is_declared_any_with_a_text_check` exists to catch, and
--   this is deliberately not one.
--
-- WHY NULLABLE
--
--   Every row written before this migration has no value for it, and there is no
--   honest default: `0.0` is a perfect baseline, which would make every existing model
--   look skill-less, and `0.25` is the balanced-fold value, which would be a guess
--   about folds nobody measured. NULL means "not recorded", and engine 14 must treat it
--   as an absence rather than as a baseline — absent is never zero, invariant 3's
--   posture applied to a statistic.

ALTER TABLE leaderboard ADD COLUMN base_rate_brier REAL;
```

*Verbatim from `db/migrations/0005_equity_cash_source.sql`, lines 1–58:*

```sql
-- 0005_equity_cash_source.sql — the operator's ruling of 2026-09-17 on Q-C1 (spec 113).
--
-- Forward-only and additive: one column on `equity_snapshots`. No existing column or
-- table is altered, nothing is dropped, and no table or index is added, so the
-- documented table set of `architecture-context.md`, `EXPECTED_TABLES` and
-- `EXPECTED_INDEXES` are unchanged.
--
-- WHAT IT RECORDS
--
--   Where the row's `cash` came from.
--
--   'cycle_start' means engine 1's balance as fetched at the start of the tick. That
--   is the whole cash figure on any tick where engine 22 sold nothing.
--
--   'after_exit' means that balance plus the `net_proceeds` of every sale engine 22
--   made on the tick. Engine 19 builds it by filtering and summing (spec 114).
--
-- WHY THE ROW HAS TO SAY SO
--
--   C's spec 100 criteria found the exit tick's row mixing three moments: cash from the
--   start of the tick, positions value from before the sale, and the open-position count
--   from after it. The ruled fix has engine 19 describe the account after the sale on
--   that tick. The row then means something different on exit ticks from what it means
--   on every other tick. A reader of the curve, such as the Phase 7 attribution, the
--   console or a criterion, needs to know which meaning a row has without re-deriving it
--   from `trades`.
--
-- WHY A CLOSED SET, WHEN 0003 REFUSED ONE FOR `hold_reason`
--
--   0003 refused to enumerate hold reasons because engine 21 may add one, the console
--   maps them in `REASON_PROSE`, and a CHECK would be a third copy that only a migration
--   can correct. Here the two values are the complete answer to a yes-or-no question:
--   did this tick's cash include this tick's sales? A third value would be a new design,
--   and a new design should need a migration. `CashSource` in
--   `clients/store/contracts.py` is the Python copy of the same two values.
--
-- WHY `NOT NULL DEFAULT 'cycle_start'`
--
--   SQLite's `ALTER TABLE ... ADD COLUMN ... NOT NULL` needs a non-null default, and
--   the default is also the backfill. It is the true label for every existing row:
--   before this migration engine 19 always took cash from engine 1's start-of-tick
--   balance, the exit tick included. Those exit-tick rows are the ones the finding
--   showed to be wrong, and 'cycle_start' is exactly what they were built from, so the
--   label describes them honestly.
--
--   A nullable column was rejected. NULL would be a third answer meaning "not recorded",
--   and the first of those rows would render the same as an honest 'cycle_start' in
--   every query that forgets to handle it.
--
--   Rebuilding the table to get NOT NULL with no default was rejected too. That is the
--   twelve-step copy, drop and rename, and it must recreate
--   `ux_equity_snapshots_tick`, the index that has already caught two orchestrators
--   sharing one `run_id` (`bootstrap.py`). It would also buy nothing: every write goes through
--   `EquitySnapshotRow`, whose `model_dump()` always carries the column, so the
--   database default is reached only by hand-written SQL.

ALTER TABLE equity_snapshots ADD COLUMN cash_source TEXT NOT NULL DEFAULT 'cycle_start'
    CHECK (cash_source IN ('cycle_start', 'after_exit'));
```

*Verbatim from `db/migrations/0006_approval_economics.sql`, lines 1–98:*

```sql
-- 0006_approval_economics.sql — spec 132, Phase 7 prerequisite 7 (F-new-1).
--
-- Forward-only and additive. No existing column is altered and nothing is dropped. Adds
-- one table (`approvals`), one index on it, seven columns on `trades` and two on `runs`.
-- `EXPECTED_TABLES` and `EXPECTED_INDEXES` gain the table and its index in the same
-- change.
--
-- WHY
--
--   Before this migration an approved trade left no record of why it was approved. Only
--   `rejections` carried expected move, friction, net edge and hurdle, so the
--   counterfactual dataset recorded the reasons for one side of the decision only.
--   This migration makes the other side recordable. Engine 19 (C, spec 133) writes it.
--
-- `approvals` — THE PLACING TICK'S ECONOMICS, HELD UNTIL THE TRADE IS WRITTEN
--
--   The economics exist in `state` only on the tick engine 18 places the entry. The
--   `trades` row is written ticks later, when engine 22 closes the position, and by then
--   `state` no longer holds them. So engine 19 writes one row here on the placing tick,
--   keyed by the entry order's `userref`. When it writes the trade it copies the row
--   onto `trades`.
--
--   Insert-only. The primary key refuses a second approval for one entry. That is why
--   `cycle_id` here is always the tick that placed the order. On `orders` the same column
--   is overwritten by every later tick (prerequisite 8, F-new-2).
--
--   Columns on `orders` were rejected. `StoreClient.write_order` upserts every column,
--   and engine 21 builds its fill and cancel rows from scratch, so the fill-tick write
--   would put NULL over the economics. `docs/build-log/phase-7/b-store.md` has the whole
--   decision.
--
-- THE ECONOMICS ARE MONEY-SHAPED, AND ABSENT IS NEVER ZERO
--
--   They are declared ANY with a text CHECK, as on `rejections`. They are the arithmetic
--   of invariant 5, computed from live fees, and they decide whether a trade happens, so
--   a float must never reach them. NULL means "not recorded". Every `trades` row written
--   before this migration reads NULL. Nothing backfills them from `rejections`, because
--   the two tables mean different things.
--
-- THE THREE MODEL RUN IDS
--
--   These are the runs engines 8, 13 and 15 loaded on the approving tick. NULL means "not
--   recorded". A blank string is refused, because that is how "unknown" gets past a
--   nullable column. The same rule as `positions.hold_reason` (0003).
--
-- `approvals.details` — EVERY GATE'S VERDICT ON THE APPROVING TICK (SPEC 145)
--
--   Operator ruling 2026-09-19. Canonical JSON written by engine 19: each engine that
--   judged the candidate, with the value it computed and the threshold it compared
--   against. This is the approval-side twin of `rejections.details`, which is
--   unchanged. NULL means not recorded. A blank string is refused, as for the run ids.
--   Added while 0006 is still uncommitted, so no 0007 is needed.
--
-- `runs.scenario_digest` AND `runs.scenario_description` — THE LEAD'S SPEC 134
--
--   These name the declared replay scenario that priced a run: the fee schedule and tier,
--   the synthetic book's bucket table, the rules file and the window. The orchestrator
--   writes them at startup through `StoreClient.start_run`. They are NULL for paper and
--   live runs. They are never a placeholder, so a blank string is refused here too.

CREATE TABLE approvals (
    userref           INTEGER PRIMARY KEY,
    run_id            TEXT    NOT NULL,
    cycle_id          INTEGER NOT NULL,
    ts                INTEGER NOT NULL,
    pair              TEXT    NOT NULL,
    expected_move_pct ANY     CHECK (expected_move_pct IS NULL OR typeof(expected_move_pct) = 'text'),
    friction_pct      ANY     CHECK (friction_pct IS NULL OR typeof(friction_pct) = 'text'),
    net_edge_pct      ANY     CHECK (net_edge_pct IS NULL OR typeof(net_edge_pct) = 'text'),
    hurdle_pct        ANY     CHECK (hurdle_pct IS NULL OR typeof(hurdle_pct) = 'text'),
    prediction_run_id TEXT    CHECK (prediction_run_id IS NULL OR trim(prediction_run_id) <> ''),
    anomaly_run_id    TEXT    CHECK (anomaly_run_id IS NULL OR trim(anomaly_run_id) <> ''),
    skeptic_run_id    TEXT    CHECK (skeptic_run_id IS NULL OR trim(skeptic_run_id) <> ''),
    details           TEXT    CHECK (details IS NULL OR trim(details) <> ''),
    updated_at        INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_approvals_run_cycle ON approvals (run_id, cycle_id);

ALTER TABLE trades ADD COLUMN expected_move_pct ANY
    CHECK (expected_move_pct IS NULL OR typeof(expected_move_pct) = 'text');
ALTER TABLE trades ADD COLUMN friction_pct ANY
    CHECK (friction_pct IS NULL OR typeof(friction_pct) = 'text');
ALTER TABLE trades ADD COLUMN net_edge_pct ANY
    CHECK (net_edge_pct IS NULL OR typeof(net_edge_pct) = 'text');
ALTER TABLE trades ADD COLUMN hurdle_pct ANY
    CHECK (hurdle_pct IS NULL OR typeof(hurdle_pct) = 'text');
ALTER TABLE trades ADD COLUMN prediction_run_id TEXT
    CHECK (prediction_run_id IS NULL OR trim(prediction_run_id) <> '');
ALTER TABLE trades ADD COLUMN anomaly_run_id TEXT
    CHECK (anomaly_run_id IS NULL OR trim(anomaly_run_id) <> '');
ALTER TABLE trades ADD COLUMN skeptic_run_id TEXT
    CHECK (skeptic_run_id IS NULL OR trim(skeptic_run_id) <> '');

ALTER TABLE runs ADD COLUMN scenario_digest TEXT
    CHECK (scenario_digest IS NULL OR trim(scenario_digest) <> '');
ALTER TABLE runs ADD COLUMN scenario_description TEXT
    CHECK (scenario_description IS NULL OR trim(scenario_description) <> '');
```

*Verbatim from `db/migrations/0007_tick_tallies.sql`, lines 1–81:*

```sql
-- 0007_tick_tallies.sql — spec 146, operator ruling 2026-09-19 (Q8).
--
-- Forward-only and additive: one table and one index. No existing table or column is
-- touched. `EXPECTED_TABLES` and `EXPECTED_INDEXES` gain them in the same change.
--
-- WHY
--
--   The funnel in `phase-7-findings.md` has to be fillable from stored rows. Until now
--   engine 7's universe step lived in `state["scout"]` for exactly one tick, and a tick
--   with no candidate left no row anywhere. Counting those ticks meant arithmetic on
--   absences. This table records one row per tick on which engine 7 ran and did not
--   error. Engine 19 writes it from engine 7's published payload, verbatim (spec 146,
--   C's half).
--
-- NOT A REJECTION
--
--   A tally is a fact about a tick, not a refused candidate, so it never goes into
--   `rejections` (invariant 12, and the Phase 3 deferral recorded in the tracker, which
--   rejected putting it there for this reason). It is its own table, joined on
--   `(run_id, cycle_id)`.
--
-- ONE ROW PER TICK, WRITTEN ONCE
--
--   `UNIQUE (run_id, cycle_id)`. `write_scout_tally` inserts and never upserts, so a
--   second write for one tick raises. A tick is `(run_id, cycle_id)` and never `cycle_id`
--   alone, which restarts with the process (`architecture-context.md`).
--
-- ABSENT IS NULL, NEVER ZERO
--
--   Every payload field is nullable. A field engine 7 did not publish is NULL, which is
--   what a BLOCK payload looks like: it carries only `reason_code`. A zero `scanned` on a
--   blocked tick would put a number in the funnel that means something else entirely.
--   Only the tick's identity and `updated_at` are required.
--
-- THE JSON COLUMNS ARE STORED AS GIVEN
--
--   `pairs`, `excluded`, `rank_skipped`, `ranked` and `rank_run_ids` are TEXT, JSON as
--   engine 19 serialised it, and they come back byte for byte. `StoreClient` checks their
--   shape on the way in (`ScoutTallyRow`). In particular, each expected move in `ranked`
--   must be an exact decimal string, never a JSON number. The CHECK here is only
--   `json_valid`, a backstop for hand-written SQL.
--
-- `equity` IS MONEY
--
--   It is declared ANY with a text CHECK like every money column, so a float is refused.
--
-- NO STATUS COLUMN, AND THE BAR IS ENGINE 3's (THE LEAD'S RULING, 2026-09-19)
--
--   Engine 7 publishes no status, and spec 146 stores its payload verbatim, so no status
--   is derived here. `reason_code` and `candidate` together carry the outcome: a
--   candidate, `empty_universe`, `no_rankable_pair`, or `scout_inputs_unavailable`. An
--   errored engine 7 writes no tally, and its `block_records` row records that tick.
--
--   `closed_bar_ts` is engine 3's published `closed_bar_ts`, stored verbatim: whole
--   seconds, the opening second of the bar that just closed. It is NULL when engine 3
--   published none. Named for its source, so nobody reads it as microseconds or as the
--   bar's close.

CREATE TABLE scout_tallies (
    id              INTEGER PRIMARY KEY,
    run_id          TEXT    NOT NULL,
    cycle_id        INTEGER NOT NULL,
    ts              INTEGER NOT NULL,
    closed_bar_ts   INTEGER CHECK (closed_bar_ts IS NULL OR closed_bar_ts >= 0),
    reason_code     TEXT    CHECK (reason_code IS NULL OR trim(reason_code) <> ''),
    candidate       TEXT    CHECK (candidate IS NULL OR trim(candidate) <> ''),
    scanned         INTEGER CHECK (scanned IS NULL OR scanned >= 0),
    entered         INTEGER CHECK (entered IS NULL OR entered >= 0),
    equity          ANY     CHECK (equity IS NULL OR typeof(equity) = 'text'),
    pairs           TEXT    CHECK (pairs IS NULL OR json_valid(pairs)),
    excluded        TEXT    CHECK (excluded IS NULL OR json_valid(excluded)),
    rank_feature    TEXT    CHECK (rank_feature IS NULL OR trim(rank_feature) <> ''),
    rank_descending INTEGER CHECK (rank_descending IS NULL OR rank_descending IN (0, 1)),
    rank_skipped    TEXT    CHECK (rank_skipped IS NULL OR json_valid(rank_skipped)),
    ranked          TEXT    CHECK (ranked IS NULL OR json_valid(ranked)),
    rank_run_ids    TEXT    CHECK (rank_run_ids IS NULL OR json_valid(rank_run_ids)),
    updated_at      INTEGER NOT NULL,
    UNIQUE (run_id, cycle_id)
) STRICT;

CREATE INDEX idx_scout_tallies_ts ON scout_tallies (ts);
```

Column list per table as read from a run database (`pragma_table_info`), for cross-checking: `runs` (id, run_id, mode, started_at, ended_at, acsoe_version, config_digest, updated_at, system_mode, system_mode_at, scenario_digest, scenario_description); `commands` (id, command, source, reason, payload, created_at, created_by_run_id, claimed_at, claimed_by_run_id, consumed_at, updated_at); `block_records` (id, cycle_id, run_id, ts, blocked_by, block_reason, is_primary, status, updated_at); `equity_snapshots` (id, cycle_id, run_id, ts, currency, equity, peak_equity, cash, positions_value, unrealised_pnl, realised_pnl_cum, open_position_count, updated_at, cash_source); `positions` (position_id, run_id, cycle_id, pair, base, quote, side, status, qty, entry_price, target_price, stop_price, timeout_at, entry_userref, last_price, unrealised_pnl, opened_at, closed_at, trade_id, updated_at, hold_reason); `orders` (userref, order_id, run_id, cycle_id, position_id, pair, side, intent, order_type, oflags, status, qty, limit_price, filled_qty, avg_fill_price, fee, placed_at, closed_at, updated_at); `trades` (trade_id, position_id, run_id, cycle_id, pair, base, quote, side, qty, entry_price, exit_price, entry_fee, exit_fee, entry_userref, exit_userref, opened_at, closed_at, outcome, realised_pnl, realised_pnl_pct, realised_pnl_quote, reporting_currency, fx_rate_entry, fx_rate_exit, fallbacks_used, updated_at, expected_move_pct, friction_pct, net_edge_pct, hurdle_pct, prediction_run_id, anomaly_run_id, skeptic_run_id); `rejections` (id, cycle_id, run_id, ts, pair, rejected_by, reason_code, reason, expected_move_pct, friction_pct, net_edge_pct, hurdle_pct, candidate_score, shap_ref, details, updated_at); `approvals` (userref, run_id, cycle_id, ts, pair, expected_move_pct, friction_pct, net_edge_pct, hurdle_pct, prediction_run_id, anomaly_run_id, skeptic_run_id, details, updated_at); `scout_tallies` (id, run_id, cycle_id, ts, closed_bar_ts, reason_code, candidate, scanned, entered, equity, pairs, excluded, rank_feature, rank_descending, rank_skipped, ranked, rank_run_ids, updated_at); `leaderboard` (id, model_id, model_version, training_run_id, trained_at, fold, n_trades, win_rate, sharpe, deflated_sharpe, alpha, beta, brier, net_pnl, reporting_currency, promoted, notes, updated_at, base_rate_brier); `schema_migrations`.

### C.8 The reason-code prose map

`src/acsoe/console/format.py`, the `REASON_PROSE` mapping (65 entries; the committed file interleaves comments recording who wrote each sentence and why). The block, located by `awk '/^REASON_PROSE/,/^}/'` over the file (407 lines including comments), with the comments stripped for an appendix:

```python
REASON_PROSE: Final[Mapping[str, str]] = {
    "net_edge_below_hurdle": "Net edge did not clear the hurdle after fees",
    "cost_inputs_unavailable": "The cost gate could not price this candidate",
    "risk_inputs_unavailable": "The risk gate could not size this candidate",
    "safety_inputs_unavailable": "The safety breaker could not read its inputs",
    "scout_inputs_unavailable": "The scout could not read the pairs it needs",
    "spread_wider_than_move": "The spread is wider than the expected move",
    "below_ordermin": "Position would be below the pair's minimum order size",
    "below_costmin": "Position value would be below the pair's minimum order value",
    "insufficient_quote_balance": "Not enough quote currency held to open this position",
    "max_concurrent_positions": "Already holding the maximum number of positions",
    "position_open_on_pair": "This pair already holds an open position",
    "entry_resting_on_pair": "This pair already has an entry order resting on the book",
    "pair_rules_missing": "The exchange did not report rules for this pair",
    "no_live_quote": "No live price for this pair",
    "crypto_quoted": "This pair is priced in a volatile asset",
    "quote_not_provably_stable": "The stable currencies are not configured, so this pair's quote cannot be trusted",
    "no_quote_balance": "The account holds none of this pair's quote currency",
    "no_fx_rate": "No exchange rate to value this pair's quote currency",
    "empty_universe": "No pair was tradable on this bar",
    "no_rankable_pair": "Every tradable pair was one the market checks would refuse on this bar",
    "barriers_below_tick_size": "This pair's price steps are too coarse for a stop",
    "market_anomalous": "Trading conditions on this pair look broken",
    "skeptic_veto": "A second model expects this entry to fail",
    "tournament_no_digest": "No training digest was given, so no models were ranked",
    "tournament_no_oos": "The training run's out-of-sample rows are missing, so no models were ranked",
    "tournament_no_store": "No database is open, so the rankings could not be saved",
    "tournament_digest_mismatch": "The training run's summary and its out-of-sample rows disagree, so no models were ranked",
    "promotion_too_few_trades": "Fewer than ten trades, too few to judge, so not promoted",
    "promotion_lower_bound_not_above_zero": "The edge did not stay above zero once overlapping trades and every configuration tried were allowed for, so not promoted",
    "promotion_no_ledger": "The count of configurations tried is missing, so nothing was judged",
    "promotion_bad_trade": "A trade's return could not be worked out in one currency, so nothing was judged",
    "skeptic_unavailable": "No second-opinion model is loaded, so this entry was not judged",
    "anomaly_unavailable": "No market-health model is loaded, so conditions were not checked",
    "anomaly_inputs_incomplete": "Some market-health inputs were missing for this pair",
    "di_refused": "Conditions are unlike anything in training",
    "prediction_unavailable": "No usable model is loaded, so nothing was predicted",
    "di_percentile_mismatch": "The refusal threshold setting does not match the loaded model, so it was not used",
    "prediction_inputs_incomplete": "Some inputs the model needs were missing for this pair",
    "market_data_stale": "Market data is older than the guard allows",
    "negative_spread": "The order book is crossed",
    "missing_candle": "No pair traded for a whole decision bar",
    "no_market_data": "No market data has arrived",
    "no_feature_row": "No feature row for this pair on this bar, so the market was not classified",
    "regime_inputs_incomplete": "The inputs that classify the market have not filled yet for this pair",
    "position_unrecordable": "An entry filled before the exchange published this pair's rules, so the position is recorded on the next tick",
    "pair_disagreement": "Two engines judged different pairs on this bar, so no entry was made",
    "stale_bar": "One of the approvals came from an earlier decision bar",
    "input_missing": "An engine this check needs published nothing for this bar",
    "no_approved_quantity": "The risk gate approved an entry without a size, so none was placed",
    "decision_inputs_unavailable": "The final coherence check could not read what it needs",
    "entry_placed": "A post-only buy is resting on the book",
    "entry_already_placed": "This entry was already placed, so nothing was sent again",
    "post_only_would_cross": "The price moved before the order rested, so it was not placed",
    "entry_unrecorded_at_exchange": "An order is resting at the exchange and this system cannot tell when it was placed, so it was left unrecorded; find it by its reference",
    "entry_recovered_from_exchange": "An order already at the exchange was matched to this entry and recorded",
    "entry_at_exchange_is_not_a_limit": "The exchange reports this entry with no limit price, so it was not recorded",
    "data_guard_blocked": "Exits are paused while this tick's market data is rejected; the position is still watched",
    "exits_placed": "Exit orders are resting at the exchange for this position",
    "nothing_to_exit": "No position reached a barrier on this bar",
    "exit_already_placed": "The exit for this position was already placed",
    "exit_incomplete": "This position could not be exited and is still open; the attempt repeats next bar",
    "book_fetch_failed": "The order book could not be read, so slippage is unknown",
    "book_unusable": "The order book came back malformed, so slippage was not estimated from it",
    "book_too_thin": "The order book is too shallow to price this size within the depth fetched",
    "order_book_inputs_unavailable": "The order-book check could not read what it needs to price this size",
    "leaderboard_empty": "No model has been through the tournament yet",
    "leaderboard_unreadable": "The model leaderboard could not be read in full, so no weights were applied",
    "leaderboard_truncated": "The model leaderboard is longer than could be read, so no weights were applied",
    "no_model_beats_its_base_rate": "No model is currently beating its own base rate",
    "engine_errored": "A check failed with an error before it could decide, so nothing was traded; the log for this tick says why",
}
```

(The listing above strips the interleaved comments for an appendix; the commented original is in the source dump, `docs/ACSOE_source_dump.md`, under `src/acsoe/console/format.py`. `operator_reason` prefers a row's own stored sentence over this map — tracker lines 406–410 — so a console row shows the engine's sentence with the figures, e.g. `Net edge +0.74% after fees, below the +1.00% hurdle on +0.67% friction`.) Two prose defects on record: `exits_placed` says "resting" although every exit is a market sell (F-new-3, tracker line 934), and `engine 12`'s two codes rendered as silence until spec 99 (tracker "Findings — Phase 6").

### C.9 Two complete tick traces from stored rows

Both from the tier 3 database. The `details` column is spec 145's per-engine verdict snapshot (canonical JSON, `details_version: 1`); the money fields are exact decimal strings. The opportunity chain stops at the first block, so a rejection's snapshot lists only the engines that ran.

**(a) A tick ending in an approval — STORJ/USD, 2024-10-20T04:30:00Z (bar close), tier 3, `approvals.userref = 1902893928`, `cycle_id 1458`, `ts 1729398600000000`.** Engines in chain order, each one's verdict as stored in `approvals.details`:

| Engine | Verdict / published numbers |
|---|---|
| 7 `scout` | pair `STORJ/USD`; `rank_feature expected_move`, descending; `rank_skipped {anomaly_inputs_incomplete: 151}`; ranked list of 39 pairs, top: STORJ/USD `0.01872379704121122`, DOGE/USD `0.005784…`, ETH/USD `0.005415…`, then AUD/USD, BTC/USD, EUR/USD, GBP/USD, USDC/USD, USDT/USD all at `0.004654988236116681` (the calibrators' low plateau), …, LINK/USD `−0.0036875…` |
| 12 `regime` | `label: trending` |
| 13 `anomaly` | `score 0.39686900172854206` < `threshold 0.6474051905957353` → `anomalous: false`; `model_run_id train-20260913T205245-067b2b9d-f394-p7` |
| 8 `prediction` | `p_target 0.7443552828189702`, `p_stop 0.24405431012065293`, `p_timeout 0.01159040706037683`; `expected_move_pct "0.01872379704121122"` (1.872%); `is_buy true`; `di 1.5391261576207993` < `di_threshold 2.2766046106046764` |
| 9 `order_book` | `basis_notional "5000.00"`, `best_bid "0.5642341510385699999717805"`, `depth 10`, `levels_consumed 5`, `fill_price "0.5641565708012433131130910639"`, `estimated_slippage_pct "0.0001374965290276866236136747246"` (0.0137%) |
| 10 `cost` | `friction_pct "0.006689770529027686723613674725"` (0.669% = maker 0.22 + taker 0.38 + bucket spread ≈ 0.055 + slippage 0.0137), `net_edge_pct "0.01203402651218353327638632528"`, `hurdle_pct "0.01003465579354153008542051209"` (= 1.5 × friction), `clears_hurdle true` |
| 11 `risk` | `approved true`, `risk_amount "50.0000"` (1% of 5,000), `notional "3333.333333332467721776455957"` (= 50 / 0.015), `qty "5904.45105471"` |
| 14 `adaptive_router` | `active_model_run_id …-f394-p7`, `di_margin 0.7374784529838772`, `regime trending` (provenance only) |
| 15 `skeptic` | `p_wrong 0.2662825593750926` ≤ `threshold 0.5` → `vetoed false` |
| 16 `decision` | `coherent true`; `checked [scout, prediction, order_book, cost, risk, adaptive_router, skeptic]` |
| 18 `execution` | placed the post-only limit buy `userref 1902893928` (the `approvals` primary key); `orders` row `entry / limit / filled`; the trade `trade-pos-1902893928` opened 04:34:00Z at `0.56423`, closed 05:22:00Z on `stop` at `0.5555518150311922848306709018`, `realised_pnl −71.03401721374955039005608425` (−2.132%); `entry_fee 7.32923052091785126`, `exit_fee 12.46486830078651684732562425` |

**(b) A tick ending in a rejection at the cost gate — STORJ/USD, 2024-10-20T06:45:00Z, tier 3, `rejections.id 1457`, `cycle_id 1575`, `ts 1729406700000000`.** `rejected_by cost`, `reason_code net_edge_below_hurdle`, `reason "Net edge +0.74% after fees, below the +1.00% hurdle on +0.67% friction"`, `shap_ref shap/replay-phase7-t3-expected_move-20241005T001500Z/1575/STORJ%2FUSD.parquet`, `details.refused_by = "cost"`:

| Engine | Verdict / published numbers |
|---|---|
| 7 `scout` | pair `STORJ/USD`; `rank_skipped {anomaly_inputs_incomplete: 154}`; ranked top: STORJ/USD `0.014040017904735795`, SAND/USD `0.006054…`, ETH/USD `0.005313…`, GALA/USD `0.004944…`, then the FX/stablecoin plateau at `0.004654988236116681` |
| 12 `regime` | `trending` |
| 13 `anomaly` | `score 0.4848729679716602` < `threshold 0.6474051905957353`, `anomalous false` |
| 8 `prediction` | `p_target 0.6396309716563389`, `p_stop 0.3473125880552217`, `p_timeout 0.013056440288439575`; `expected_move_pct "0.014040017904735795"` (1.404%); `is_buy true`; `di 1.128873509266778` < `2.2766046106046764` |
| 9 `order_book` | `basis_notional "4974.948236299813003810342525"` (the cash after the morning's two trades), `best_bid "0.5636743056752899999718085"`, `levels_consumed 5`, `estimated_slippage_pct "0.0001368041533935241423268649725"` |
| 10 `cost` | `friction_pct "0.006689078153393524242326864972"`, `net_edge_pct "0.007350939751342270757673135028"` (0.735%), `hurdle_pct "0.01003361723009028636349029746"` (1.003%): **0.735% < 1.003%, `clears_hurdle false` → BLOCK**; engines 11, 14, 15, 16, 18 never ran (absent from the snapshot) |

Both rows are reproduced as JSON in pack 02 §B.12. The reason sentence's rounding (+0.74% shown for 0.7351%) is the console's `format_signed_pct`.
