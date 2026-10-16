# Evidence pack 03 — testing method, results on disk, Phase 7 and Phase 8 as they will read, defects and limitations, the claims check

**Read at commit `9f5a1449378c10e8f8f87ec27732914a0a19e92f` (`9f5a144`), `main`, clean tree, 2026-09-20T15:33Z–16:00Z.** Run databases read through `file:PATH?mode=ro&immutable=1` (the main file, as at the last checkpoint). `pytest --collect-only -q` was the only command run against the tree; nothing else was executed, built or changed.

## Contents

- [A. Testing method](#a-testing-method)
- [B. Results on disk today](#b-results-on-disk-today)
- [C. Phase 7 as it will read when finished](#c-phase-7-as-it-will-read-when-finished)
- [D. Phase 8 as it will read when finished](#d-phase-8-as-it-will-read-when-finished)
- [E. Known defects and limitations, as recorded](#e-known-defects-and-limitations-as-recorded)
- [F. Claims to confirm or correct](#f-claims-to-confirm-or-correct)

---

## A. Testing method

### A.1 Test collection

`.venv/Scripts/python.exe -m pytest --collect-only -q tests/` at HEAD: **3,928 tests collected in 20.56 s**. By top-level folder under `tests/`:

| Folder | Tests | | Folder | Tests |
|---|---|---|---|---|
| `engines/` | 913 | | `harness/` | 86 |
| `clients/` | 608 | | `cli/` | 68 |
| `verify/` | 494 | | `core/` | 65 |
| `research/` | 398 | | `db/` | 48 |
| `console/` | 376 | | | |
| `platform/` | 348 | | | |
| `scripts/` | 336 | | | |
| `modelling/` | 188 | | **Total** | **3,928** |

(The last gate on record ran the suite: `toolchain_green` reported `3309 passed, 2 skipped` at the Phase 6 close, `logs/verify/phase6-20260918-phase6-close-lead-verify.log`, tracker Phase Status. Phase 7 added the rest.)

### A.2 Kinds of test present, one example each

| Kind | Example path | What it is |
|---|---|---|
| Unit, per engine, with a block test and a pass test for every gate | `tests/engines/test_cost.py`, `tests/engines/test_safety.py` | `context/run-protocol.md` line 172: "For any gate engine, you must also have written one test proving it blocks and one proving it passes." |
| Property-based (`hypothesis`) | `tests/clients/paper/test_fills.py`, `tests/clients/store/test_store.py`, `tests/db/test_migrations.py`, `tests/modelling/test_features_batched.py`, `tests/platform/test_packaging.py` | files importing `hypothesis` (grep) |
| Replay / reproduction | `tests/research/test_labelling.py` (the labeller against `labels_hand_verified.json`), `tests/research/test_walkforward.py`, `tests/research/test_replay.py`, `tests/research/test_chain_replay.py`, `tests/verify/test_phase5_criteria.py` (`features_reproduce_in_replay`) | exact-reproduction assertions, A.4 |
| End to end through the real orchestrator and registry ("rehearsals") | `tests/engines/test_guard_chain_rehearsal.py`, `test_feature_chain_rehearsal.py`, `test_trade_chain_rehearsal.py`, `test_manage_chain_rehearsal.py`; the paper trade round trips in `tests/verify/test_phase6_criteria.py` | `src/acsoe/bootstrap.py` lines 41–51, 163–167 |
| Harness / fixture based | `tests/harness/fake_kraken.py` (fake exchange over `tests/fixtures/kraken/*.json`), `tests/harness/market_script.py`, `tests/harness/network_guard.py` (the autouse guard that fails any test touching the network), `tests/harness/doubles.py` | `tests/harness/` listing |
| Executable phase criteria (the gate) | `scripts/verify.py` (15,312 lines, 64 `check_*` functions) with its own tests `tests/verify/test_phase{0..7}_criteria.py`, each criterion proved PENDING on an absent subject, PASS on a fabricated one, and FAIL on a planted defect | `context/ai-workflow-rules.md` lines 15–43; `feature-specs/141-phase-7-criteria.md` "Check When Done" |
| Documentation consistency | `tests/verify/test_docs_vocabulary.py` and the `docs_vocabulary` criterion | pack 01 §B.6 |

### A.3 Mutation testing

- **The harness.** Each agent runs its own copy of a small script (`mutate.py`, kept in the session scratchpad, not committed; the lead's watchdog variant is committed as text at `docs/build-log/phase-7/mutate_phase7_watchdog.py.txt`). Method as recorded (`docs/build-log/phase-7/c-interface.md` lines 136–142): "each mutation applied from a byte copy in the scratchpad, `PYTHONDONTWRITEBYTECODE=1`, the named tests run with `-x`, the file restored before the next mutation and the restore verified by sha256 (every arm `restored=True`), a pytest summary line required for every verdict. Baseline green before each sweep." The anchor must occur exactly once in the file (`a-platform.md` lines 1088–1091). A JSON verdict per arm with the restored file's sha256 is what the committed sweep logs hold (e.g. `logs/verify/b103-sweep-all-paper.json`: `"arm": "N1-executed-fills-not-counted", "verdict": "KILLED", "summary": "8 failed, 69 passed", "restored": {"src/acsoe/clients/paper/broker.py": "98c0df71…"}`).
- **The green baseline rule.** The named tests must pass on the unmutated file before any arm is applied (`c-interface.md` line 141; every sweep entry states its baseline count).
- **Known defect of the harness (Phase 8 item):** the original bytes are held in memory and restored in `try/finally`, so a hard kill leaves the mutant on disk (`context/progress-tracker.md` lines 1677–1686; fix: write the byte copy to disk first).
- **Latest sweep per engine or module, from the committed build logs and sweep JSONs** (kill rate = killed / applied; "checked negative" = a survivor shown to be an equivalent mutant and recorded as such):

| Engine / module | Applied | Killed | Survivors → outcome | Equivalent (checked negative) | Source |
|---|---|---|---|---|---|
| Engine 7 `scout`, spec 144 ranking (`tests/engines/test_scout_ranking.py`, `test_scout.py`, baseline 84) | 22 | 22 | none | 1 assertion not mutable in B's lane, stated | `docs/build-log/phase-7/b-store.md` lines 161–210 |
| Engine 19 `memory`, spec 133 approvals (baseline 70) | 11 | 11 | none | — | `c-interface.md` lines 171–178 |
| Engine 19 `memory`, spec 145 verdict snapshots (baseline 81) | 13 | 13 | none | — | `c-interface.md` line 1138 |
| Engine 19 `memory`, spec 140 SHAP writer (baseline 92) | 9 | 9 | none | — | `c-interface.md` line 1167 |
| Engine 19 `memory`, spec 146 tallies (baseline 88) | 8 | 8 | none | — | `c-interface.md` line 1191 |
| Engine 20 `tournament`, the promotion gate (baseline 61) | 12 | 11 → 12 | E3 (zero entry notional accepted) survived, test added, killed | — | `c-interface.md` lines 340–354 |
| `modelling/promotion.py` + `research/trial_ledger.py`, spec 139 (baseline 48) | 30 | 27 → 29 | P9 (`>=` vs `>`) and P15 (DSR skew sign) survived, tests added, killed | P19 unreachable guard, removed | `c-interface.md` lines 144–169 |
| `research/attribution.py`, spec 138 (baseline stated) | 24 | 24 | one first-pass survivor, then killed | — | `c-interface.md` lines 484–518 |
| `modelling/ranking.py`, spec 144's modelling half (baseline 13) | 18 | 18 | R16a equivalent | 1 (R16a) | `c-interface.md` lines 286–300 |
| `modelling/di.py` batched score, spec 137 (baseline 31) | 10 | 10 | none | — | `c-interface.md` lines 231–236 |
| DI exclusion (K arms) | 8 | 8 | none | — | `c-interface.md` line 311 |
| `research/skeptic_cap.py`, spec 136 (`tests/research/test_skeptic_cap.py`) | 14 | 13 | S2, S4, S12, S14 killed once tests existed | S5 | `c-interface.md` lines 573–584 |
| `research/artefact_assembly.py`, spec 135 | 17 | 13 (+3 new tests) | A10, A13, A17, A11b killed by new tests | — | `c-interface.md` lines 605–616 |
| Engine 5 `feature` batched (`compute_many`), D16 (102 tests) | 13 | 12 | two first-pass survivors resolved | 1 (`min_samples=2`) | `c-interface.md` lines 979–988 |
| Replay client and driver, specs 129/131 (`clients/kraken/replay*.py`, `research/backtest.py`, `cli/research.py`, `platform/config.py`, `cli/engine.py`) | 38 | 37 | M35 survived, test added, killed | 1 (M29) | `a-platform.md` lines 1086–1149 (full arm table) |
| Store migration 0006, spec 132 (B) | 13 | 13 | one only after the test was widened | — | `b-store.md` lines 60–89 |
| Paper broker ledger, spec 103 (B), `logs/verify/b103-sweep-all-paper.json` | 11 arms N1–N11 | all KILLED (N0 control SURVIVED as designed) | — | — | JSON |
| Position manager fill-tick mark, spec 106 (B), `logs/verify/b106-sweep-*.json` | P1, P1b, P2, P3 | killed | P1 survived the criterion until spec 107 (recorded) | — | JSON; tracker lines 347–351 |
| Phase 7 watchdog (lead) | (its own sweep, "mutation proof") | — | — | — | commit `6f9120b`; `docs/build-log/phase-7/mutate_phase7_watchdog.py.txt` |

Recorded limitation of the method (`context/progress-tracker.md` lines 652–679, "a defect mutation testing structurally cannot reach"): the engine 14 truncation-tripwire false positive at exactly `_WINDOWED_PROBE` rows, found by code review, not by any sweep.

### A.4 Reproducibility checks and what "exact" means in each

| Check | Asserts | Tolerance | Source |
|---|---|---|---|
| `labeller_matches_hand_verified_labels` (Phase 4) | the labeller reproduces every row of 20 hand-verified labels | exact: "all 20 hand-verified labels reproduced exactly" | `scripts/verify.py` lines 7449, 7586; `tests/fixtures/labels_hand_verified.json` |
| `labelled_sample_replayed_from_archive` (Phase 4) | the committed labelled slice equals a fresh replay of the archive slice | row equality; provenance inside the parquet | `tests/fixtures/README.md` |
| `features_reproduce_in_replay` (Phase 5) | engine 5's live path and `modelling.features` agree over the same candles; a lookback is time not rows | **relative tolerance 1e-9** (`FEATURE_REASSOCIATION_TOLERANCE`) for float re-association; the message says "agree EXACTLY" when the difference is zero | `verify.py` lines 8456, 8777–8802 |
| `compute_many` versus per-pair `compute` (D16) | the batched feature arithmetic is bit-identical to the oracle | bit-for-bit ("13× faster, bit for bit") | `c-interface.md` line 913; `tests/modelling/features_oracle.py` |
| Batched DI equals per-row DI | on fold 404's real reference set | within 2.4e-14 | `c-interface.md` line 205 |
| Walk-forward digest rebuilt from artefacts | each fold's rebuilt rows, Brier, base-rate Brier, log loss, buy count, buy target rate, target rate, effective sample size and buy identity reproduce the manifest | `largest_absolute_differences` all 0.0; `tolerance` stated in the digest's `rebuilt_from_artefacts` block | `tests/fixtures/walkforward_digest.json` |
| Capped-skeptic replication | with the cap disabled, `research/skeptic_cap.py` reproduces an early fold's saved uncapped skeptic: same training identity, same row count, same probability on every BUY call | exact (probabilities differ by 0) | `skeptic_cap.py` lines 18–24; findings line 477 |
| Kill-and-resume identity (spec 142) | a run killed and resumed writes the same rows as an uninterrupted run | byte-identical on every table once `shap_ref` (which embeds the process's cycle number) is excluded; 71 of 71 refs match once run and cycle segments are ignored | `docs/build-log/phase-7/lead.md` "The gating rehearsals pass everything but kill-and-resume"; tracker lines 1647–1658 |
| Grid comparison, engine 7 versus the offline ranking | 75 bars of 2024-10-20 | 68 of 75 agree; 7 differ inside a tie on the FX/stablecoin plateau (F6, no cost verdict changes) | `a-platform.md` line 1465; overnight decisions F6 |
| Candles from recorded trades (Phase 2, amended) | built 15 m candles equal an independent reduction sharing no code | largest difference 0 on the committed fixture; tolerance one `tick_size` from the recorded 2026 `AssetPairs` (spec 141 step 5), never engaged | `context/ai-workflow-rules.md` lines 141–155 |

### A.5 Committed fixtures

| Fixture | Size | Provenance |
|---|---|---|
| `tests/fixtures/book_sample.jsonl` | 347,917 B | 30 s of live Kraken v2 book traffic for ADA/USD and BTC/USD cut from `data/raw/kraken_v2__msi__2026-09-16.jsonl` by `scripts/cut_book_fixture.py`, window opening 00:17:06.100Z, 48 ms after a reconnect so one `snapshot` per pair precedes every delta; header line with sha256 of the body (`tests/fixtures/README.md`) |
| `tests/fixtures/walkforward_digest.json` | 2,412,035 B | the partial digest of run `train-20260913T205245-067b2b9d`, 405 of 457 folds, rebuilt from the fold artefacts by `docs/dataset/rebuild-walkforward-2026-09-14.py` (script sha256 `63c9c9ef…`), `coverage.complete: false` |
| `tests/fixtures/leaderboard_sample.json` | 5,709 B | **fabricated**, and says so in capitals in its `provenance` field; exists because the real leaderboard cannot exercise engine 14's weighting rule |
| `tests/fixtures/record_sample.jsonl` | 10,168 B | 25 redacted lines of the day-one recorder carrying a genuine `gap` marker (Phase 0, A) |
| `tests/fixtures/recording_report.json` / `_full_archive.json` | 5,106 B / 9,268 B | digests of the real recording: a 24.07 h clean span at 0.99977 recorded; the full 47.24 h archive at 0.762 |
| `tests/fixtures/labelled_sample.parquet` / `candles_sample.parquet` / `labels_hand_verified.json` | 25,190 / 34,412 / 136,261 B | a labelled slice replayed from the archive with provenance inside the parquet; its OHLCVT input with one deliberate hole; 20 hand-verified labels with their own candle windows |
| `tests/fixtures/kraken/` | `asset_pairs.json` 1,836 B (invented Phase 0 data, honest provenance block since 2026-09-18); `asset_pairs_recorded_2026-09-19.json` 782,864 B, `instrument_recorded_2026-09-19.json` 646,507 B, `pair_names_recorded_2026-09-19.json` 106,424 B (genuine recordings, spec 127); `balance.json`, `order_book.json`, `trade_volume.json`, `fee_tiers.json`, `ohlc.json` (the fake exchange's responses) |
| `tests/fixtures/replay/` | `kraken_fee_schedule_2026-09-19.json` and its `.html.gz` raw page; the restructure article `.html.gz`; `spread_book_table_2026-09-19.json`; `kraken_fee_schedule_2026-09-19.pair_classes.json` |
| `tests/fixtures/phase7/rehearsal_2024-10-20/` | one day of weekly-partition trades per pair (234 directories; "committed as a 7.3 MB fixture", D19) | spec 142's rehearsal day |

### A.6 Static toolchain

`pyproject.toml`: **mypy `strict = true`**, `python_version = "3.11"`, `warn_unreachable`, `warn_unused_ignores`, `disallow_any_generics`, `no_implicit_reexport`; numpy and polars are skipped (`follow_imports = "skip"`, `follow_imports_for_stubs = true`) because numpy 2.5's stubs use PEP 695 syntax mypy rejects under 3.11 — the cost stated in the file: "`polars` and `numpy` are `Any` to mypy". Six third-party packages `ignore_missing_imports`. **ruff** `target-version = "py311"`, line length 100, `src = ["src", "tests", "scripts"]`, rule families E, W, F, I, UP, B, C4, PTH, DTZ (naive `datetime.now()` is a lint error), SIM, RET, ARG, TID (relative imports banned), T20 (no `print` outside CLI, scripts and tests), RUF, A, ISC, PIE, N; ignores E501 and RUF012. pytest: `asyncio_mode = "strict"`, `filterwarnings = ["error::DeprecationWarning:acsoe.*"]`. The gate command since 2026-09-17 is `verify.py` alone with `mypy --strict src/ scripts/` and `ruff check src/ tests/ scripts/` before it (tracker lines 536–537; `TOOLCHAIN` widened 2026-09-11, tracker lines 1213–1236). `mypy --strict` is deliberately not run over `tests/` (about 1,680 test functions without return annotations; a test asserts the exclusion).

### A.7 Line counts and dependencies

Python lines (`find … -name '*.py' | xargs cat | wc -l`, excluding `__pycache__`):

| Package | Lines | | Package | Lines |
|---|---|---|---|---|
| `src/acsoe/engines` | 15,437 | | `src/acsoe/core` | 860 |
| `src/acsoe/clients` | 9,882 | | `src/acsoe/bootstrap.py` | 235 |
| `src/acsoe/research` | 8,521 | | **`src/` total (139 files)** | **43,979** |
| `src/acsoe/console` (+2,431 lines of CSS/JS/HTML) | 2,936 | | **`tests/` total (159 files)** | **82,785** |
| `src/acsoe/modelling` | 2,910 | | **`scripts/` total (29 files)** | **32,145**, of which `verify.py` 15,312 |
| `src/acsoe/platform` | 1,872 | | | |
| `src/acsoe/cli` | 1,323 | | | |

Dependencies (`pyproject.toml` `[project]`, all named in the stack table of `context/architecture-context.md` lines 5–23): `websockets>=13.0`, `httpx>=0.27`, `tenacity>=9.0`, `pydantic>=2.9`, `polars>=1.9`, `numpy>=1.26`, `pyarrow>=17.0`, `duckdb>=1.1`, `orjson>=3.10`, `fastapi>=0.115`, `uvicorn>=0.31`, `structlog>=24.4`, `pyyaml>=6.0` (safe_load only), `lightgbm>=4.5`, `scikit-learn>=1.5`, `shap>=0.46`, `joblib>=1.4`; extra `research`: `hmmlearn>=0.3.2`, `statsmodels>=0.14`; extra `dev`: `pytest>=8.3`, `pytest-asyncio>=0.24`, `hypothesis>=6.112`, `mypy>=1.11`, `ruff>=0.6`, `types-PyYAML>=6.0`. `requires-python >= 3.11`; the venv runs CPython 3.13.5 and polars 1.44.1 (tracker line 1663). `scipy` is not a dependency, which is why `promotion.py` implements its own Student-t quantile (lines 100–105).

### A.8 The paper trade proof

- **What it is:** the Phase 6 criteria `paper_trade_round_trip_target`, `paper_trade_round_trip_stop`, `paper_trade_round_trip_timeout` in `scripts/verify.py` (plus `paper_equity_continuous_across_fill`, `equity_row_never_values_positions_it_does_not_hold`, `escalation_completes_during_outage`). Each drives one complete paper trade through `bootstrap.build_chains()` under the real orchestrator against the fake Kraken client and B's paper broker, with engine 19 recording to a real `StoreClient`: a post-only entry past all eight gates, a simulated fill at its limit, the minute-by-minute watch, and an exit on target, stop or timeout, "with every order, position, trade and equity row reconciled against figures recomputed from the book and the live fee tier" (tracker lines 524–532). The Phase 6 gate: **13 criteria, 13 PASS, 0 FAIL, 0 PENDING** (`logs/verify/phase6-20260918-phase6-close-lead-verify.log`).
- **At which fee tier, and why:** the fake exchange's **tier 3**, which charges maker 0.11% / taker 0.19% (not Kraken's reference 0.22/0.38): "engine 10 computed friction 0.308% and a hurdle of 0.462% (a bar of 0.770% on the expected move)" (tracker lines 113–120, operator ruling S3). Every trade-driving criterion states the friction and hurdle engine 10 computed in its own run (`_run_regime`, `verify.py` lines 11122–11134) and names Kraken's reference tier 1 as a separate sentence. Why not tier 1: at Kraken's reference tier 1 (friction ≈ 1.25%, bar 3.125% > the 3.0% target) the cost gate is unreachable, so a criterion needing a trade cannot run there; and a fresh clone with an empty `.env` has no fee tier at all, so every pair blocks at the cost gate against the real client (tracker lines 94–104). Measured, not argued: at the fake's own tier 1 (0.25/0.45) the gate clears (friction 0.708%, hurdle 1.062%), so "the fake's tier 1 is not a no-trade regime and no message may say it is" (tracker lines 214–219). **The Phase 6 criteria therefore prove the machinery, not the economics** (tracker line 103–104).
- The first real paper trade walk-through is `docs/build-log/phase-6/first-paper-trade.md`; it found that the database held no record of why the trade was taken (F-new-1), fixed by spec 133/145 for Phase 7.

---

## B. Results on disk today

Every number names its file and the command that produced it. "[T]" means the output was transcribed from the terminal into `docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt`.

### B.1 The walk-forward digest

- File: `tests/fixtures/walkforward_digest.json` (identical content to `data/derived/walkforward_digest_train-20260913T205245-067b2b9d.json`). Command: `python -m acsoe.research.training --config config/default.yaml` (the original run, log `logs/fullrun-20260913T214616.log`), then `docs/dataset/rebuild-walkforward-2026-09-14.py`.
- **Folds trained: 405 of 457** (`coverage.folds_written 405`, `folds_expected 457`, `complete: false`, `missing_fold_indices [405, 456]`, `missing_test_weeks ["2025-01-04", "2025-12-27"]`).
- **Why it stopped** (`coverage.error` and `why`, verbatim): "numpy._core._exceptions._ArrayMemoryError: Unable to allocate 7.80 GiB for an array with shape (8950630, 117) and data type float64" — "The training run died during fold 405 of 457 (index 405) in _fit_skeptic -> _skeptic_matrix, when the scaler's transform of the skeptic's uncapped training matrix could not allocate. The skeptic for fold k trains on every eligible BUY call from folds before k, so its matrix grows every fold; by fold 404 it held 8,946,942 rows. … By operator ruling of 2026-09-14 the run was not rerun or resumed, and this digest covers the folds that exist."
- **The partial marker:** `notes` begins "PARTIAL: covers 405 of 457 folds; see `coverage`." and `docs/dataset/walkforward-folds-2026-09-14.md` opens "**PARTIAL: 405 of 457 folds.**"
- **Per-fold out-of-sample summary:** the table in `walkforward-folds-2026-09-14.md` (test week, rows with effective sample size beside them, Brier, base-rate Brier, difference, BUY calls, BUY target rate) and the CSV `walkforward_folds.csv` in pack 04 (every per-fold metric). Aggregate: 20,331,237 rows, effective sample size 2,119,251; 117 features, version `f1`; `config_digest 067b2b9d…`. Examples: fold 0 (2017-04-01) Brier 0.1840 vs base 0.1883; fold 392 (2024-10-05) Brier 0.14742 vs base 0.15106, 70,161 rows, effective 6,414, 35,292 BUY calls at 0.1668 target rate; fold 404 is the last (test 2024-12-28 → 2025-01-04). Calibration: isotonic per class (A.4 of pack 02); the digest does not carry a separate calibration score beyond Brier and log loss.

### B.2 The offline funnel over the 1.5-year window

`docs/dataset/phase-7-findings.md` §1a (source `outputs/q_window.out`, script `q_window.py`): 53,022 decision bars → **74** clear the 1.50% cost bar → 48 complete feature vector → 47 anomaly → 31 DI → 2 skeptic (uncapped, 0.50) → **1** one position per pair. Arm: alphabetical candidate, tier-3 reference fees, zero spread. At 10 bps spread: 29, 18, 18, 5, 2, 1; at 25 bps: 10, 5, 5, 1, 0, 0. In chain order (§1b, `outputs/q_funnel.out`): 53,022 → 20,223 pass anomaly (incl. incomplete vectors) → 19,807 pass DI → 31 pass cost at 0.60% friction → 17 pass risk → 1 uncapped skeptic / 15 capped. CSV: `funnel_1p5y.csv`.

### B.3 Predictor BUY-call skill

`docs/dataset/skeptic-veto-sweep-2026-09-14.json` `meta`: `all_buy_calls 8,950,912` (target rate 0.2383159), of which 8,948,485 with a skeptic (fold 0 has none); `all_test_rows_target_rate 0.242158`. Findings §5b / tracker Finding 1: "**8,948,485 out-of-sample BUY calls** hit the target at **0.2383**, against **0.2422** over all test rows — *below* the base rate". Command: `python docs/dataset/skeptic-veto-sweep-2026-09-14.py`.

### B.4 Skeptic veto sweep

Same file, `sweep` (uncapped skeptic, all 405 folds, before friction), CSV `skeptic_sweep.csv`:

| Threshold | Survivors | Share | Survivor target rate | No-skill band |
|---|---|---|---|---|
| 0.30 | 9,373 | 0.10% | 0.6349 ± 0.0085 | 0.2711–0.2892 |
| 0.40 | 51,145 | 0.57% | 0.6035 ± 0.0037 | 0.2563–0.2621 |
| **0.50** | **154,979** | 1.73% | **0.5309 ± 0.0023** | **0.2550–0.2596** |
| 0.60 | 583,121 | 6.52% | 0.4403 ± 0.0014 | 0.2602–0.2629 |
| 0.70 | 2,859,743 | 31.96% | 0.3482 ± 0.0007 | 0.2645–0.2653 |

Against the predictor's confidence at matched counts (`docs/dataset/skeptic-vs-ptarget-2026-09-14.md`): at 0.50, skeptic 0.5309 vs top-N by `p_target` 0.4731, margin +0.0578, **44%** of calls in both sets; at 0.30 +0.0744 (29% overlap); at 0.70 +0.0049 (68%). **Caveat carried by the tracker (Finding 1 caveat, lines 1266–1276):** these describe the uncapped skeptic; the capped skeptic in the window passes 8.38% at 0.3935 against 0.3953 for `p_target` ranking — "no detectable difference" (F4).

### B.5 Realised return on calls clearing the 1.50% bar

Findings §6 (sources [T] `2026-09-18_q_net.py`, `outputs/q_window.out`): full span, 405 folds, 938 alphabetical candidates clearing 1.50% at tier-3 fees and zero spread: realised **+0.320%** before friction (−0.28% after the 0.60% fee, interval [−0.42%, −0.14%]); the 1.5-year window: 74 calls, **+1.251%**; with one position per pair: 34, +0.781%; the final 365 days: 71, +1.177%; the span excluding the window: ~+0.24% (derived). "**71 of the window's 74 calls fall in its final 365 days.**" (§6a).

### B.6 Tier 1 no-trade proof

Findings §2 "Tier 1 is provably zero. FINAL." (quoted in full in pack 01 §B.5): the bar at tier 1 is 2.5 × 1.20% = **3.0%** before spread; the expected move is a weighted average of 3.0%, −1.5% and the fold's mean timeout return `m`, with the calibrated probabilities renormalised to sum to one (`modelling/calibration.py`, `apply_calibration`), and **`m` lies between 0.17% and 0.54% in all 405 fold manifests**, so the expected move can never exceed 3.0% and the gate needs strictly more. Observed maximum over 15,978,803 rows: **2.9999999930%** (`outputs/2026-09-18_q_em.log`).

### B.7 Spread inversion

Findings §3 (flat: `outputs/q_funnel.out`; bucket: [T] `q_bucket.py`), both arms `log_return_4` ascending, capped skeptic 0.50, one position per pair, at most three open: flat 10 bps gives +0.29% to +0.55% per trade (three cells nominally significant: +0.51% ± 0.44%, +0.49% ± 0.36%, +0.36% ± 0.31% at 0.40% fees); the bucket table on the same candidates gives −0.32% to +0.06% where n ≥ 12, and −0.67% on the two 3-trade cells; no bucket cell's interval excludes zero. Mechanism: in the flat arm at 0.60%/12 months only 11 of 65 trades are on recorded pairs, whose recorded median spreads are 24.7 bps (up to 127.4) against 10 charged; the 54 unrecorded-pair trades netted +0.48%, the 11 recorded −0.05% ([T] `q_picks.py`).

### B.8 Ranking study

Findings §4 table (CSV `ranking_study.csv`), all with the bucket table, capped skeptic 0.50, one position per pair: at 0.60% fees / 12 months — alphabetical 1 trade (−2.17%, n = 1); `log_return_4` 3 (−0.67%, not meaningful); expected move **46 (35 pairs), −0.20% ± 0.65%**; net margin 55, −0.10% ± 0.60%. At 0.40% / 12 months: 12, 58, 254, 283. Alphabetical concentration: 1INCHUSD on 29,857 of 53,022 bars (56.3%), AAVEUSD 20,082 (37.9%), 17 pairs ever the candidate; "about 126 pairs per bar were passed over on their name alone". The per-feature study over 405 folds is `docs/dataset/ranking-study-2026-09-14.md` (`python -m acsoe.research.training --ranking-study …`, exit 0 in 3.5 min): control alphabetical +0.025% mean barrier return per bar; `bar_body_pct` ascending +0.417% but 21–44% of its bars on intermittently traded pairs; the operator ruled no studied feature (2026-09-15) and then expected move (2026-09-19).

### B.9 The expected-move grid behind the invariant 4 amendment

The expected-move column of §4 (B.8 above; CSV `expected_move_grid.csv`): 22 / 46 / 71 / 119 / 150 / 254 trades across fees {0.60, 0.50, 0.40}% × windows {6, 12} months, net per trade −0.26% to −0.08%, every interval including zero. **Sample-size criterion** (§8, lines 831–838): "Below about ten trades, and wherever the trades come from two or three pairs, an interval says nothing about the system"; every such cell is marked "interval not meaningful" or shows its n. The amendment's stated criterion was sample size, not return (§R.2, lines 83–95); the residual circularity is §R.9.

### B.10 Power calculation

Findings §7b "What the promotion bar can find at these trade counts" (lines 687–710): minimum mean net return per trade `q × SD / √n` with `q` the Student-t quantile at `1 − 0.05/1,679` and SD ≈ 2.2–2.3% from the §4 cells: **tier 3, n = 10–11: q = 7.71–7.19, 4.9–5.5%**; **tier 5, n = 27–55: q = 5.05–4.56, 1.35–2.14%**. A single target exit after tier-3 friction returns about +2.3% by the label, and **about +2.0% as realised** by the exit rule (F5; the four tier-3 target exits realised +1.40%, +2.52%, +2.40%, +2.61%). "**So a non-promotion is the expected outcome of this design, not a finding about skill.**"

### B.11 Tier 5 final rows; tier 3 rows so far

Both from the run databases (`select … from trades order by closed_at`; times UTC from the microsecond columns). CSVs `trades_tier5.csv`, `trades_tier3.csv`, `equity_tier*.csv`.

**Tier 5 — every trade (final: the run is frozen and can take no more):**

| # | Pair | Entry (UTC) | Exit (UTC) | Outcome | Entry → exit price | Net PnL (USD) | Return |
|---|---|---|---|---|---|---|---|
| 1 | STORJ/USD | 2024-10-19 08:31 | 08:36 | stop | 0.65060 → 0.637418 | −82.23 | −2.470% |
| 2 | STORJ/USD | 09:03 | 10:08 | stop | 0.63957 → 0.629062 | −68.37 | −2.088% |
| 3 | STORJ/USD | 10:18 | 10:24 | stop | 0.63217 → 0.620885 | −72.00 | −2.230% |
| 4 | STORJ/USD | 11:31 | 11:45 | stop | 0.61067 → 0.600021 | −69.62 | −2.189% |
| 5 | STORJ/USD | 2024-10-20 04:34 | 05:22 | stop | 0.56423 → 0.555556 | −62.19 | −1.983% |

Realised sum −354.41; friction per trade 0.635–0.638% (0.518% on the fifth, a different bucket), hurdle 0.952–0.956% (0.777%); expected move at entry 1.71% (1.87%). **Freeze:** `commands` row 2, `freeze` by `safety`, reason `safety: loss_streak`, `created_at 1729402200000000` = **2024-10-20T05:30:00Z**, claimed and consumed at 05:45Z; `runs.system_mode = frozen`, `system_mode_at` 05:45Z; `block_records` from 05:30Z: `blocked_by safety`, `block_reason "Safety breaker: 5 consecutive losses, limit 5"`, 5,128 rows so far. **Equity at the freeze and since:** 4,645.588515155844495159903843 (cash only, `realised_pnl_cum −354.4114848441555048400961582`, −7.09% from 5,000; peak 5,014.178865839436002424812500). The check that fired: `SafetyCondition.LOSS_STREAK` (`consecutive_losses >= 5`, `engines/safety/engine.py` lines 269–270), not the drawdown (7.1% < 10%).

**Tier 3 — the nine trades so far (run in progress; last checkpointed equity ts 2024-12-08T00:45Z):**

| # | Pair | Entry (UTC) | Exit (UTC) | Held | Outcome | Entry → exit | Net PnL | Return | Fold model |
|---|---|---|---|---|---|---|---|---|---|
| 1 | STORJ/USD | 2024-10-20 04:34 | 05:22 | 48 min | stop | 0.56423 → 0.555552 | −71.03 | −2.132% | f394 |
| 2 | STORJ/USD | 05:49 | 06:42 | 53 min | target | 0.55419 → 0.565317 | +45.98 | +1.400% | f394 |
| 3 | DOGE/USD | 13:20 | 17:10 | 3.8 h | target | 0.1373091 → 0.141610 | +83.55 | +2.520% | f394 |
| 4 | NEAR/USD | 2024-10-25 23:46 | 10-26 02:47 | 3.0 h | target | 4.1028 → 4.226463 | +80.98 | +2.403% | f394 |
| 5 | DOGE/USD | 2024-11-14 22:31 | 22:35 | 4 min | stop | 0.3807854 → 0.374707 | −75.00 | −2.190% | f397 |
| 6 | DOGE/USD | 22:46 | 23:00 | 14 min | stop | 0.3779927 → 0.371706 | −76.16 | −2.257% | f397 |
| 7 | CRV/USD | 2024-11-15 05:17 | 06:19 | 62 min | target | 0.27892 → 0.287896 | +86.61 | +2.606% | f397 |
| 8 | OXT/USD | 2024-11-25 22:33 | 22:39 | 6 min | stop | 0.10854 → 0.106613 | −80.03 | −2.368% | f399 |
| 9 | APT/USD | 2024-12-02 03:47 | 03:57 | 10 min | stop | 13.1304 → 12.913097 | −74.84 | −2.249% | f400 |

Sum −79.94 (`realised_pnl_cum`); equity 4,920.06 (−1.60%); peak 5,143.94; 13 approvals, 9 fills, 4 cancelled at the 300 s window (LCX/USD, OCEAN/USD, EWT/USD and one STORJ/USD); no open position; `system_mode running`. All 6,045 rejections name the cost gate.

### B.12 Per-tick cost

From the run records (`wall_ms` of every `bar_tick: true` event, grouped by test week) and the weekly trade counts in `data/derived/trades_weekly/manifest.json` (CSV `tick_cost.csv`):

| Week | Trades on the tape (all pairs) | Tier 3 mean bar-tick wall (ms) | Tier 5 mean (ms) |
|---|---|---|---|
| 2024-10-05 (early) | 1,492,305 | 4,141 | 4,124 |
| 2024-10-12 | 2,051,055 | 5,181 | 5,164 |
| 2024-11-09 | 6,413,690 | 13,274 | 12,579 |
| 2024-11-30 (late) | 8,454,294 | 18,010 | 16,543 |
| 2024-12-07 (partial) | 5,997,128 | 14,068 | 13,918 |

Cost tracked the tape: a 5.7× rise in weekly trade volume from the first to the ninth week against a 4.3× rise in mean bar-tick time. The rehearsal's pre-launch measurement was 5.00 s per bar tick at two runs in parallel on 2024-10-20 (`docs/build-log/phase-7/handover-2026-09-19.md` §4), which the first weeks reproduce; the November weeks (the post-election volume surge on the tape) were not in the estimate.

---

## C. Phase 7 as it will read when finished

Written in the past tense as the report will, with one placeholder token per figure that does not exist yet. Every token is listed at the end of this section with what fills it and which script writes it.

### C.1 The final report scripts per run

- **`python -m acsoe.research.attribution --db data/db/phase7-t3-expected_move.sqlite --root . --json <out.json>`** (`src/acsoe/research/attribution.py` `main`, lines 943–965; spec 138). Read-only (`mode=ro`). It computes, per run: the daily equity grid from `equity_snapshots` including flat days; the **BTC/USD buy-and-hold** series and the **equal-weighted basket of the pairs held while held, cash otherwise**, both marked from the same weekly partitions with no fees; an OLS regression of daily equity returns on each benchmark's daily returns with HAC (Newey–West) covariance, lag = max(most grid days any hold spans − 1, `floor(4 (n/100)^(2/9))`), alpha and beta with t-intervals on the residual degrees of freedom, alpha "significant" only if its 95% interval excludes zero, and the effective sample size `n × (se_ols / se_hac)²`; per-trade statistics (count, pairs, target/stop/timeout mix, net per trade with an interval only at ≥ 10 trades, expected move at entry beside realised return); coverage (share of bars refused for an incomplete vector, the survivorship count, the scenario digest); the funnel in chain order from `block_records`, `rejections` and `scout_tallies`. Output: the report rendered to stdout and, with `--json`, a JSON file. Fields: `AttributionReport.to_dict()` (`regressions` per benchmark with `alpha`, `beta`, `alpha_interval`, `lag`, `effective_sample_size`, `significant`; `trades`; `coverage`; `funnel`; the two `OVERLAP_STATEMENT` and `JOIN_STATEMENT` sentences carried verbatim).
- **The promotion gate:** engine 20 through `acsoe research` with `promote_run_id` and `ledger_path` (`engines/tournament/engine.py` lines 156–169, 274–310): reads the run's closed trades, computes `net_return = realised_pnl / (qty × entry_price)`, calls `promotion_verdict(holds, trials = 1679)`, and **writes one leaderboard row** (`promoted 0/1`, the reason code, the DSR in `deflated_sharpe`).
- **The committed digest per run** (spec 143 step 4): equity series, trades, funnel counts and scenario under `tests/fixtures/`, judged by `backtest_emits_alpha_report` (spec 141 step 1, which recomputes the report's figures from the digest's series). **NOT FOUND yet on disk**: no Phase 7 run digest exists under `tests/fixtures/` (the directory holds only `phase7/rehearsal_2024-10-20/`).

### C.2 The four pre-registered statistics per tier

**As implemented** (`src/acsoe/modelling/promotion.py`, quoted from the committed file):

> 1. **The quantity.** Each closed trade's net return: `realised_pnl / (qty x entry_price)`. That is after both fees, the spread and slippage, exactly as the run recorded them. Liquidations count; nothing is excluded.
> 2. **Overlapping holds: HAC (Newey-West, Bartlett kernel)** on the per-trade series in entry order. … `gamma_j = (1/n) * sum_{t=j+1..n} d_t * d_{t-j}`; `LRV = gamma_0 + 2 * sum_{j=1..L} (1 - j/(L+1)) * gamma_j`; `SE_HAC = sqrt(LRV / n)`.
> 3. **The lag L** is the largest number of *other* trades whose hold overlaps any single trade's hold. It is computed from entry and exit times alone, before any return is read … endpoints included.
> 4. **Widened for trials: Bonferroni over N**, N the committed trial ledger's count. The two-sided interval is taken at confidence `1 - 0.05/N`, so the quantile is the Student-t quantile at `1 - (0.05/N)/2` with `n - 1` degrees of freedom for `n` trades.
> 5. **Promote only if** `mean - q * SE_HAC > 0`. With fewer than ten trades there is no interval and no promotion, and the reason says so.

The code (lines 385–433): `lag = overlap_lag(...)`; `se_hac = hac_standard_error(returns, lag)`; `se_naive = hac_standard_error(returns, 0)`; `_, quantile = bonferroni_quantile(n, n_trials)`; `lower = mean - quantile * se_hac`; `promoted = lower > 0.0`; below `MIN_TRADES = 10` → `Verdict.TOO_FEW_TRADES`. The DSR (lines 339–377, Bailey and López de Prado 2014 with `T = n` and `V = 1/(T−1)`) is reported beside the verdict and never decides it. `N = 1,679` from `docs/dataset/phase-7-trial-ledger.json` (`by_family`: recon 674, leaderboard 408, di_anomaly 287, ranking_study 169, skeptic_sweep 92, skeptic_vs_p_target 45, phase_7_runs 4 — the last counts four runs where two ran, the deliberate overcount of two).

**What the report will say, with tokens:**

| Statistic | Tier 3 | Tier 5 (final rows) | Expected verdict and why |
|---|---|---|---|
| Headline: HAC-widened, Bonferroni N = 1,679, two-sided 95% family, lower bound | n = [[T3_TRADES]] trades; mean net [[T3_MEAN_NET]]; HAC lag [[T3_HAC_LAG]]; SE_HAC [[T3_SE_HAC]]; q = [[T3_Q]]; lower bound [[T3_LOWER]] | n = 5 → **no interval** (`too_few_trades`); mean net = −2.192% (arithmetic mean of the five stored returns: −2.470, −2.088, −2.230, −2.189, −1.983 → −2.192%) | Tier 3: expected `too_few_trades` if n < 10, else `lower_bound_not_above_zero` — the pre-registered minimum mean net per trade at n = 10–11 is 4.9–5.5% (B.10), more than double a single target exit. Tier 5: `too_few_trades`, final. |
| Unadjusted p (naive independent-trades interval) | mean ± t₀.₉₇₅,ₙ₋₁ × SE_naive: [[T3_NAIVE_INTERVAL]], p = [[T3_NAIVE_P]] | not reported below ten trades | The module computes `se_naive = hac_standard_error(returns, 0)`; the naive p-value itself is **not a field of the committed code** — a post-run computation the writer must derive from `mean` and `se_naive` (token stays). |
| Overlap count behind the HAC lag | [[T3_HAC_LAG]] (the largest number of other trades whose hold overlaps any single trade's hold; from the nine trades so far it is **0**: no two of the nine holds overlap — entries 05:49 after the 05:22 exit, 22:46 after 22:35, 05:17 after 23:00) | 0 (the five STORJ holds never overlap: each entered after the previous exit) | Lag 0 makes SE_HAC = SE_naive; the report should say so. |
| **BH-FDR over the family** | **NOT IMPLEMENTED** — no Benjamini–Hochberg procedure exists in the repository (grep `Benjamini`, `Hochberg`, `FDR`, `false discovery` over `src/`, `docs/`, `feature-specs/`, `context/`: no hits). The committed family correction is Bonferroni over N = 1,679. If the report is to show a BH-FDR figure it is a post-run computation outside the pre-registration: [[T3_BH_FDR_Q]] | n/a | The report must not present BH-FDR as pre-registered. |
| Deflated Sharpe ratio | SR [[T3_SR]], skew [[T3_SKEW]], kurtosis [[T3_KURT]], SR₀ [[T3_SR0]], **DSR [[T3_DSR]]** | with n = 5 the DSR is computable (n ≥ 2, dispersion > 0): [[T5_DSR]] | Reported beside the verdict; never deciding it. |

### C.3 The promotion gate

Spec 139's rule as implemented (C.2): promote only if the Bonferroni-widened HAC lower bound is above zero; **fewer than ten trades: no interval**, `promotion_too_few_trades`, console prose "Fewer than ten trades, too few to judge, so not promoted". Expected verdict per tier and why:

- **Tier 5: not promoted, `promotion_too_few_trades`** — final, five trades. Its leaderboard row will carry `n_trades 5`, `promoted 0`, `deflated_sharpe [[T5_DSR]]`.
- **Tier 3: not promoted.** With [[T3_TRADES]] trades: if under ten, `promotion_too_few_trades`; if ten or more, `promotion_lower_bound_not_above_zero`, because the required mean net of 4.9–5.5% per trade exceeds what any mix of the realised outcomes (+1.4% to +2.6% on targets, −2.1% to −2.4% on stops) can average. The pre-registration says: "**Tier 3 cannot clear the bar.** … The only exception is a degenerate run in which every trade returns the same amount" (findings lines 700–702). Row: `n_trades [[T3_TRADES]]`, `promoted 0`, reason [[T3_PROMOTION_REASON]], `deflated_sharpe [[T3_DSR]]`.

### C.4 R8 baskets

- **Pairs held while held, cash otherwise** (`attribution.py` docstring): "Between two consecutive ticks of the run the basket earns the mean of the price returns of the pairs with a position open at the first of the two ticks (`opened_at <= t < closed_at`), rebalanced to equal weights at every tick, and nothing when no position is open. Marked from the same partitions, with no fees." Result per run: alpha [[T3_ALPHA_BASKET]] (interval [[T3_ALPHA_BASKET_CI]]), beta [[T3_BETA_BASKET]]; tier 5 [[T5_ALPHA_BASKET]], [[T5_BETA_BASKET]]. Tier 5's basket is non-zero on 2024-10-19/20 only.
- **BTC/USD buy-and-hold**: "Bought at the first tick of the run's window and held to the last, marked from the same time-and-sales partitions the run replayed, with no fees." Result: alpha [[T3_ALPHA_BTC]] ([[T3_ALPHA_BTC_CI]]), beta [[T3_BETA_BTC]], HAC lag [[T3_REG_LAG]], effective days [[T3_REG_ESS]]; tier 5 [[T5_ALPHA_BTC]], [[T5_BETA_BTC]].
- **The window's BTC move, readable now from the archive:** `data/historical/XBTUSD_15.csv`, close of the last 15-minute bar of each UTC day (CSV `btc_window.csv`): **2024-10-05 close 62,055.5 → 2025-01-03 close 98,111.1, +58.1%** (2024-10-04 62,081.0; 2025-01-04's last bar 98,208.9). The attribution marks BTC from the weekly partitions at the run's own ticks, so its figure will differ at the third digit; the direction is fixed: the benchmark rose roughly 58% while both runs ended below their start.
- **Two secondary baskets** ("the held pairs bought and held over the whole window, and the equal-weighted universe", findings lines 724–725) are post-run arithmetic over stored rows, not in `attribution.py`: [[T3_BASKET_HELD_WHOLE]], [[T3_BASKET_UNIVERSE]], [[T5_BASKET_HELD_WHOLE]], [[T5_BASKET_UNIVERSE]].

### C.5 The cost-adaptive claim

What the tier 3 versus tier 5 comparison **will show**: the same models, window, code, declared spread and depth and seed capital, differing only in the fee tier (`docs/dataset/phase-7-findings.md` lines 933–935), so any difference is attributable to cost alone. It will show that the cheaper tier's lower hurdle (0.78–0.96% against 1.00–1.18%) **admitted candidates the dearer tier refused** — the four STORJ/USD entries of 2024-10-19 08:31–11:45 that tier 5 took and tier 3 did not — and that those extra trades were all stops, tripping the loss-streak breaker on 2024-10-20 and ending tier 5's trading on day 15 of 91 (findings Part II §4.5). It will show tier 3 examining [[T3_CANDIDATE_TICKS]] candidate ticks and refusing [[T3_REJECTIONS]] at the cost gate (6,045 so far), against tier 5's 1,452 examined and 1,445 refused before its freeze.

What it **will not show**: that tier 3 is "safer" or "better" — the difference is [[T3_FINAL_EQUITY]] against 4,645.59 on a handful of trades; that the tiers differ in skill — they share every model; anything about the skeptic, the risk gate or the router — no rejection in either run names any gate but `cost` (findings Part II §4.3); tier 5's behaviour after 2024-10-20 — it recorded nothing but guard-chain blocks for 76 of 91 days.

**The one trade from the same fate qualifier:** trade 5 of tier 5 and trade 1 of tier 3 are the **same STORJ/USD entry** — `userref 1902893928`, entered 2024-10-20T04:34:00Z at 0.56423, both stopped at 05:22:00Z (tier 5 exit 0.555556, −62.19 / −1.983%; tier 3 exit 0.555552, −71.03 / −2.132%; the quantities differ, 5,559.37 against 5,904.45, because tier 5's equity was already lower). It is the one candidate both tiers approved on the same tick; it met the same fate, a stop. The sentence the report can write: "on the one candidate both configurations approved, both lost; the difference between the runs is entirely in the candidates only the cheaper tier admitted."

**The DOGE and CRV sequence (tier 3):** two DOGE/USD stops four minutes apart on 2024-11-14 (22:31→22:35, −75.00; 22:46→23:00, −76.16), then a CRV/USD target on 2024-11-15 05:17→06:19 (+86.61). It illustrates immediate re-entry into a pair that just stopped out (findings Part II §6.3, flagged as "the item closest to fitting") and that a loss streak of two does not trip a breaker set at five.

### C.6 What tonight will change and what it will not

- **Already final (tier 5):** the five trades, the freeze timestamp, equity 4,645.59, `promotion_too_few_trades`, the funnel over its first 15 days (1,461 tallies), 5,128+ safety block records. Only the row counts of block records and equity snapshots grow until the window ends; nothing else can change.
- **Pending (tier 3):** [[T3_TRADES]] (9 so far; projected 10–12, findings Part II §5 "PROJECTION, NOT A RESULT"), [[T3_FINAL_EQUITY]] (4,920.06 so far), [[T3_MEAN_NET]], the rejection and tally counts, and the fills/cancels. The run had about 2,500 bar ticks left at 15:33Z (2024-12-08T08:00Z reached of 2025-01-04); at the observed ~14 s per bar tick that is roughly 10 hours.
- **Post-run computations from stored per-trial statistics:** everything in C.2–C.4 — the attribution report per run, the promotion verdict per run (engine 20), the two secondary baskets, any naive p or BH-FDR figure. None of these has been computed yet (findings Part II line 993: "nothing has been computed from the runs yet").
- **CSVs in pack 04 whose data is not on disk yet:** none carry a header-only row — every listed CSV has data. **NOT YET:** the four post-run figure sets above have no CSV because no script has produced them.

**Placeholder tokens, what fills each, and which script writes it:**

| Token | Fills with | Written by |
|---|---|---|
| `[[T3_TRADES]]` | tier 3 closed-trade count at window end | `trades` table; `attribution.py` `trades.count` |
| `[[T3_MEAN_NET]]` | mean of `realised_pnl / (qty × entry_price)` over tier 3 trades | `promotion.py` `PromotionVerdict.mean` via engine 20; `attribution.py` net per trade |
| `[[T3_HAC_LAG]]` | overlap lag over tier 3 holds | `promotion.py` `overlap_lag` |
| `[[T3_SE_HAC]]`, `[[T3_Q]]`, `[[T3_LOWER]]` | HAC SE, Bonferroni-t quantile at N = 1,679, lower bound | `promotion.py` `promotion_verdict` |
| `[[T3_NAIVE_INTERVAL]]`, `[[T3_NAIVE_P]]` | mean ± t × `se_naive`; the implied two-sided p | `se_naive` from `promotion_verdict`; the p is the writer's arithmetic (not a field) |
| `[[T3_BH_FDR_Q]]` | a BH-adjusted q if the report chooses to add one | **no script** — not pre-registered |
| `[[T3_SR]]`, `[[T3_SKEW]]`, `[[T3_KURT]]`, `[[T3_SR0]]`, `[[T3_DSR]]`, `[[T5_DSR]]` | the `DeflatedSharpe` dataclass fields | `promotion.py` `deflated_sharpe_ratio` |
| `[[T3_PROMOTION_REASON]]` | `promotion_too_few_trades` or `promotion_lower_bound_not_above_zero` | engine 20's leaderboard row |
| `[[T3_ALPHA_BTC]]`, `[[T3_ALPHA_BTC_CI]]`, `[[T3_BETA_BTC]]`, `[[T3_REG_LAG]]`, `[[T3_REG_ESS]]`, `[[T5_ALPHA_BTC]]`, `[[T5_BETA_BTC]]` | the BTC buy-and-hold regression | `attribution.py` `regress` |
| `[[T3_ALPHA_BASKET]]`, `[[T3_ALPHA_BASKET_CI]]`, `[[T3_BETA_BASKET]]`, `[[T5_ALPHA_BASKET]]`, `[[T5_BETA_BASKET]]` | the held-while-held basket regression | `attribution.py` |
| `[[T3_BASKET_HELD_WHOLE]]`, `[[T3_BASKET_UNIVERSE]]`, `[[T5_BASKET_HELD_WHOLE]]`, `[[T5_BASKET_UNIVERSE]]` | the two secondary baskets | post-run script, **not yet written** |
| `[[T3_CANDIDATE_TICKS]]`, `[[T3_REJECTIONS]]` | tier 3's final tally and rejection counts | `scout_tallies`, `rejections` |
| `[[T3_FINAL_EQUITY]]` | tier 3's last equity row | `equity_snapshots` |

---

## D. Phase 8 as it will read when finished

### D.1 The Phase 8 scope, verbatim

The phase row, `context/ai-workflow-rules.md` line 138:

> | **8 — Live readiness** | `platform/live_guard.py` (A), `close_all` end-to-end (Lead's reader plus B's exit engine), soak test | All three live switches proven individually required; kill switch halts a running loop within one tick, cancels every resting entry order and closes every position, and closes nothing it should not; a daemon killed part-way through a `close_all` finishes the liquidation on restart rather than coming back with the command marked consumed and positions still open; `tests/fixtures/soak_digest.json` shows **one unbroken `run_id` with a contiguous `cycle_id` sequence** spanning at least 7 continuous days in paper, with zero unhandled exceptions — a positive assertion, because a digest that only counts exceptions cannot tell a clean run from a daemon that died on day 2 and sat idle for five; and `--live` checks the real log in `logs/`; no secret appears in any log, artefact, or committed file |

The tracker's Phase Status row: "| 8 — Live readiness | Blocked on 7 | — |" (`context/progress-tracker.md` line 842). The kill-switch definition: `context/architecture-context.md` lines 258–260 ("**The kill switch is `close_all`. There is no fourth mechanism.** … Phase 8 verifies `close_all`, not something separate."). The Phase 8 items the tracker's Open Questions hold (lines 1628–1697) are quoted in pack 01's context and listed in D.4.

### D.2 What Phase 8 will produce that the report can cite

| Deliverable | Token | What the repository will hold |
|---|---|---|
| The three live switches, each proven individually required (`ACSOE_LIVE=1`, `mode: live`, `config/LIVE_CONFIRMED` dated today) | [[P8_SWITCHES_PROVEN]] | `platform/live_guard.py` and its tests; a Phase 8 criterion |
| A live order placed, or not | [[P8_LIVE_ORDER]] | the live client's order refusal removed (`rest.ORDER_CALLS`, tracker line 917); the decision whether any real order was ever sent is the operator's — **the pre-registered plan does not require one** |
| `close_all` exercised end to end: halts within one tick, cancels every resting entry, closes every position, completes across a restart | [[P8_CLOSE_ALL]] | a Phase 8 criterion driving the reader plus engine 22 |
| The unattended paper soak: one unbroken `run_id`, contiguous `cycle_id`s, ≥ 7 days, zero unhandled exceptions | duration [[P8_SOAK_DAYS]], ticks [[P8_SOAK_TICKS]] | `tests/fixtures/soak_digest.json` |
| The log secret check | [[P8_NO_SECRET]] | a criterion over `logs/`, artefacts and the committed tree |

### D.3 What Phase 8 will not prove

No statistical result and no profitability: the soak runs in paper at the account's own tier, which is **tier 1, a no-trade regime** at the current barriers (pack 02 §A.5; findings §2), so the seven-day run is expected to record zero trades and to prove uptime, recording and the breakers only. It does not revisit the Phase 7 verdicts, does not add trials to the ledger, and does not change any threshold.

### D.4 Fixes scheduled for Phase 8

| Item | Recorded at | Token for its status in the report |
|---|---|---|
| The loss-streak breaker's missing recovery path: record the clear's timestamp and count only losses closed after it | tracker lines 1628–1646 (OPEN, Phase 8); findings Part II §4.1, §6.1 | [[P8_BREAKER_RECOVERY]] |
| A separate read-only API key for `fees.py` (one key, two nonce counters today) | handover §8; `a-platform.md` line 801 | [[P8_FEES_KEY]] |
| `scout.rank_feature` in the committed config (the daemon ranks alphabetically today; the ruling is whether to set `expected_move` and whether to remove the alphabetical path) | tracker lines 1687–1697 (OPEN for the operator) | [[P8_RANK_FEATURE_COMMITTED]] |
| The mutation harness's byte copy written to disk before mutating (a hard kill leaves a mutant) | tracker lines 1677–1686 | [[P8_MUTATE_BYTE_COPY]] |
| The rehearsal identity check masking the process segments inside `shap_ref` | tracker lines 1647–1658 | [[P8_SHAP_REF_MASK]] |
| The non-deterministic native crash in polars (two Windows modules, heap-corruption signature, no WHEA errors) — not chased in Phase 7 | tracker lines 1659–1676 | [[P8_NATIVE_FAULT]] |
| The live-path findings: no `recent_trades` on the live client (F1); `TradeVolume` mapped from the invented shape with no pair; `AssetPairs` keyed by REST names; engine 7 ignores pair status (F3: 13 `cancel_only` pairs would enter the universe live) | overnight decisions F1, F3 (lines 141–148, 230–238); handover §8 | [[P8_LIVE_PATH_FIXES]] |
| Engine 7 skipping a pair that already holds a position (today engine 11 refuses it after six engines ran) | tracker lines 642–644, 948–949 | [[P8_SCOUT_SKIPS_HELD]] |
| `kraken.rest_*` request budget revised against the documented limits "before Phase 8" | `config/default.yaml` lines 155–164 | [[P8_RATE_LIMITS]] |

---

## E. Known defects and limitations, as recorded

| # | Defect / limitation | Where recorded | Status |
|---|---|---|---|
| 1 | The loss-streak breaker trips correctly but has no recovery path (recomputes from the last 500 trades; an operator clear cannot reset it; a replay has no operator) | tracker 1628–1646; findings Part II §4.1, §6.1; `edfa788` | OPEN, Phase 8; not changed during the runs |
| 2 | `cycle_id` on `orders` and `positions` is overwritten by every later tick (prerequisite 8 / F-new-2); joins must use `placed_at` / `opened_at` | migration 0006 lines 23–25; `attribution.py` `JOIN_STATEMENT`; spec 138 step 5 | RECORDED; `approvals` is insert-only so its `cycle_id` is the placing tick |
| 3 | Engine 14 `adaptive_router` is inert: one model per fold, no persisted leaderboard rows, weights never real | `adaptive_router/README.md` lines 6–22; tracker lines 66–69, 105–111 | RECORDED; provenance only |
| 4 | The committed daemon ranks alphabetically (`scout.rank_feature` absent); only the replay flag ranks by expected move | tracker 1687–1697; `default.yaml` 348–351 (stale comment) | OPEN for the operator |
| 5 | Engine 7 blocks on tick 1 of every fresh run (`scout_inputs_unavailable`: no equity row yet) — one bar lost per run, 2024-10-05T00:15Z at both tiers | findings lines 817–821; `d5f5a49`; `scout_tallies` row 1 | RECORDED, by design |
| 6 | Target exits sell at market on the next minute tick and realise less than the +3.0% label (rehearsal +2.0%; run +1.40% to +2.61%) | `a-platform.md` 1310–1332 (F5); findings Part II §6.2 | RECORDED; changing it is the operator's |
| 7 | The funding poller died 2026-09-15 08:00Z and nothing restarted it until 2026-09-19 04:42 local | `a-platform.md` 83–99; overnight D2; `config/recorder.yaml` 99–100 | FIXED (supervised since 2026-09-19); the four-day hole in open-interest history is unrecoverable |
| 8 | Recording gaps: ~10 h 2026-09-08/09 (no recorder); disk-full outage 2026-09-09T13:06Z; 308 min 2026-09-17 03:13–08:20Z (network); 62.79 s switchover 2026-09-19 05:08:44Z | tracker Known Risks 2236; line 1109; tracker 32–48 | RECORDED, unrecoverable (invariant 11) |
| 9 | `fees.py` and the daemon share one API key with two nonce counters | `a-platform.md` 801; handover §8 | OPEN (operator action) |
| 10 | An intermittent native memory fault on this machine: seen in pydantic-core, `sqlite3`, pure-Python pyyaml, CPython's `ast.walk`, and (Phase 7) polars' row export and candle build; ~20% of full-suite runs crashed in Phase 0–2; two native crashes on 2026-09-19 in `ntdll.dll` and `python313.dll`; hardware suspected, root cause not established; mitigated by a crash-aware retry in `toolchain_green` and, for the runs, an auto-resume watchdog (never needed: 0 resumes) | tracker Known Risks 2240–2298 (the full account, "moves into the dissertation's limitations chapter"); tracker 1659–1676 | OPEN, Phase 8; "the limitation is on the evidence-gathering apparatus, not on the system under test" |
| 11 | 2026 substitutes applied to a 2024 window: spread and depth from 7.36 days of September 2026; pair rules and the fee schedule as of 2026-09-19; Kraken restructured tiers 2026-07-09 | findings §7, §7a items 1–3 | RECORDED, declared on every `runs` row |
| 12 | The residual circularity of the expected-move grid: the amendment to rank by expected move was decided with a grid computed on the same out-of-sample data in view | findings §R.2 "What remains", §R.9 | RECORDED as a limitation of the evaluation |
| 13 | Spread sensitivity runs (q25/q75) dropped from Phase 7 (D25); a different spread changes which trades happen, unrecoverable without a re-run | findings §7a item 4, Part II §6.5; overnight D25 | RECORDED |
| 14 | The window cut from six months to three (D23) for the report deadline: 13 retrains not 26, one season, 91 daily returns, tier 3 at or below the ten-trade threshold | findings §R.6, §7b items 1–4; overnight D23 | LOCKED |
| 15 | Excluded pairs' identities are on the `runs` row (42 names) but per-tick exclusions are counted by reason, not named | `architecture-context.md` 159; `runs.scenario_description` | RECORDED (the claims list's wording is corrected in pack 02 §C.5) |
| 16 | The leaderboard is empty on a fresh clone (`data/db/` gitignored; engine 20 has written no persisted row); engine 14 returns `leaderboard_empty` | tracker 66–69; trial ledger "Leaderboard" judgement | RECORDED |
| 17 | The walk-forward died at fold 405 (uncapped skeptic matrix, 7.80 GiB); no 2025 test week | digest `coverage`; findings §7 "2025" | RECORDED; not rerun by ruling 2026-09-14 |
| 18 | 50.2% of out-of-sample rows carry an incomplete feature vector and are refused before prediction; the surviving population is the more liquid half | tracker Finding 3 (1343–1358) | RECORDED (prerequisite 6) |
| 19 | Engine 9's slippage rests on an evenly-spread-book assumption fitted to one depth point per pair; the one real walk on file is a single BTC/USD 30 s fixture; for a tenth of recorded pairs the book held $10k in under 19% of minutes | findings §7 "The order book"; `tests/fixtures/README.md` | RECORDED |
| 20 | The fee schedule's FX/stablecoin/pegged class is served the Spot Crypto tier (overcharged, conservative) and those pairs top the ranking on most bars (EUR/USD, AUD/USD, USDC/USD, USDT/USD, GBP/USD = 3,692 of 6,045 tier 3 rejections) | overnight D8; findings Part II §4.4, §6.6 | RECORDED |
| 21 | F6 train/serve skew: exact zeros live where the training dataset carries floating-point residues on unmoving pairs; changes a ranking tie, never a cost verdict | overnight F6; `c-interface.md` line 1011 | RECORDED, not fixed (operator's decision) |
| 22 | `data_guard` is structurally inert in replay (the declared quote is stamped `now`, D7), so the run is no evidence the guard works | findings Part II §4.8 | RECORDED |
| 23 | Tier 5's funnel describes its first 15 days only (`scout_tallies` stop while frozen) | findings Part II §4.9 | RECORDED |
| 24 | Only the cost gate ever refused anything in either run, so the runs say nothing about how often the skeptic, risk or router would refuse | findings Part II §4.3 | RECORDED |
| 25 | The DI-feeds-regime Locked Decision is not implemented (`di_regime_shift` null) | `regime/README.md` line 70; pack 02 §B.6 | RECORDED absence |
| 26 | `platform/live_guard.py` does not exist; live mode is refused by the config loader | `platform/config.py` 11–14, 982–986 | Phase 8 |
| 27 | Engine 7 ignores pair status (F3); no `recent_trades` on the live client (F1); `TradeVolume`/`AssetPairs` mapping on the live path | overnight F1, F3; handover §8 | Phase 8 |
| 28 | The kill-and-resume identity check reports false on `shap_ref`'s embedded cycle number; the launch precondition was judged met by hand on the five rehearsals' evidence | tracker 1647–1658; findings lines 806–816 | OPEN, Phase 8 |
| 29 | The trial ledger overcounts by two (four runs counted, two ran) — deliberate, in the harsher direction | findings §R.8, lines 714–718 | RECORDED |
| 30 | Every phase gate was a retried measurement on hardware with a known intermittent fault; the retry covers crashes, not wrong verdicts | tracker Known Risks (the "Why this moves it into the dissertation's limitations chapter" paragraph) | RECORDED |
| 31 | The first paper trade's engine 9 slippage was 0 because the book was pinned to one level — not evidence about slippage | tracker lines 70–72 | RECORDED |
| 32 | Phase 2's original candle criterion described checking against Kraken with a fetched tolerance; it checked a local reduction with an invented one (FINDING; row amended 2026-09-18) | `ai-workflow-rules.md` 141–155 | RECORDED |
| 33 | `max_concurrent_positions: 3` is inert at $5,000 (the balance binds at one position) | tracker 2037–2039 | RECORDED |
| 34 | The paper broker's trade window is bounded by count, not time; an entry older than the window cannot see the trade that would fill it (pessimistic) | `clients/paper/broker.py` docstring "The window is bounded by count" | RECORDED |

---

## F. Claims to confirm or correct

Verdicts: **CONFIRMED** (source), **CORRECTED** (right value and source), **NOT FOUND** (where looked). Count at the end.

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | 23 engines in three runtime chains: guard 1,2,3,4,17; opportunity 5,6,7,12,13,8,9,10,11,14,15,16,18; manage 21,22,19; offline 20,23 | **CONFIRMED** | `src/acsoe/bootstrap.py` lines 114–120, 174–188, 217–221; `cli/research.py` 104–108, 133–148; `engine-contracts.md` 198–222 |
| 2 | Decision bar 15 minutes, loop tick 1 minute | **CONFIRMED** | `config/default.yaml` 39–40 |
| 3 | Triple barrier +3% / −1.5% / 48 bars | **CONFIRMED** | `default.yaml` 44–46 |
| 4 | Fees from `TradeVolume`, minimums from `AssetPairs`, never hardcoded | **CONFIRMED** | `trading-invariants.md` 19–28; `rest.py` 99–102; `AGENTS.md` lines 5–8 |
| 5 | Money stored as exact decimal strings in ANY columns | **CONFIRMED** | migration 0001 lines 11–23 (`ANY` with `CHECK (typeof(col) = 'text')`) |
| 6 | Archive: 1,119 raw pairs, 234 USD-quoted pairs with two years or more, 20,331,237 labelled bars, 2017-01-01 to 2025-12-31 | **CONFIRMED** | `scripts/build_ohlcvt.py` 9, 379 (1,119; 413 USD-quoted scanned); `labelled-dataset-2026-09-12.json` `meta` and `total`; `PROJECT-STATE.md` 819–821 |
| 7 | Label split 23.89% target, 51.27% stop, 24.84% timeout, 0.376% both | **CONFIRMED** | `labelled-dataset-2026-09-12.json` `total` (4,857,764 / 10,424,046 / 5,049,427 / 76,522 of 20,331,237); `PROJECT-STATE.md` §10 |
| 8 | 405 of 457 folds; out of memory in the skeptic's uncapped matrix build; digest rebuilt from artefacts and marked partial | **CONFIRMED** | `tests/fixtures/walkforward_digest.json` `coverage` (7.80 GiB, `_fit_skeptic -> _skeptic_matrix`, 8,946,942 rows), `rebuilt_from_artefacts`, `notes "PARTIAL…"` |
| 9 | 50.2% of test rows carry incomplete feature vectors from 48- and 96-bar lookbacks | **CONFIRMED** | tracker Finding 3: 8,025,361 of 15,978,803 |
| 10 | Funnel over 53,022 bars: 74, 48, 47, 31, 2, 1 | **CONFIRMED** | findings §1a (alphabetical, tier-3 reference fees, zero spread, uncapped skeptic) |
| 11 | 8.95M BUY calls at 0.2383 target rate against 0.2422 for all rows | **CONFIRMED** | `skeptic-veto-sweep-2026-09-14.json` `meta`: 8,950,912 (all) / 8,948,485 (with a skeptic) at 0.2383 vs 0.2422 |
| 12 | Skeptic at 0.50 lifts survivors to 0.531 against 0.255–0.260; beats `p_target` ranking at matched counts with 44% overlap | **CONFIRMED, with the caveat the tracker attaches** | findings §5b; tracker Finding 1 — measured on the **uncapped** skeptic; the capped skeptic in the window shows no detectable difference against `p_target` (F4) |
| 13 | +0.32% across 405 folds, +1.25% in the 1.5-year window | **CONFIRMED** | findings §6 (938 calls +0.320%; 74 calls +1.251%) |
| 14 | Tier 1 max observed expected move 2.9999999930%; mean timeout return 0.17–0.54% | **CONFIRMED** | findings §2, `outputs/2026-09-18_q_em.log` |
| 15 | Account measured at tier 1, 0.40% maker, 0.80% taker, 19 September 2026 | **CONFIRMED** | `data/raw/fees/fees__msi__2026-09-19.jsonl` first `TradeVolume` line 05:08:45Z (`fees.XXBTZUSD.fee 0.8000`, `fees_maker.XXBTZUSD.fee 0.4000`); tracker lines 21–30 |
| 16 | Kraken restructured tiers on 9 July 2026; tier 3 needs $10k volume or $20k held, tier 4 $25k or $50k, tier 5 $50k or $100k | **CONFIRMED** | `kraken_fee_schedule_2026-09-19.json` `_provenance.restructure` and `spot_crypto` rows 3–5 (also futures-volume alternatives ≥ $10M/$15M/$25M) |
| 17 | Flat 10 bps spread gives +0.3% to +0.6% per trade; the bucket table gives −0.03% to −0.25% on the same run | **CORRECTED** | findings §3: flat cells run **+0.29% to +0.55%**; bucket cells with n ≥ 12 run **−0.32% to +0.06%**, and the two 3-trade cells at 0.60% fees show −0.67% (interval not meaningful). "−0.03% to −0.25%" matches only the 12-month cells at 0.40% and 0.50% fees |
| 18 | Spread bucket table over 185 USD pairs recorded 2026-09-11 to 2026-09-19, 7.36 days | **CONFIRMED** | `spread_book_table_2026-09-19.json` `_provenance` (`recorded_usd_pairs 185`, `days 7.3556`). Note the findings' prose §3 says "187 USD pairs for 7.4 days" from the earlier reconnaissance aggregate; the committed fixture's 185 is the figure the runs used |
| 19 | Pair rules snapshot of 2026-09-19 excludes 39 of the window's 231 pairs | **CONFIRMED** | findings §7a item 2; overnight "Recorded answer, spec 127 survivorship"; the 42-of-234 list on the `runs` row |
| 20 | Phase 7 window: folds 392–404, test weeks 2024-10-05 to 2025-01-04, 13 retrained models | **CONFIRMED** | spec 143 lines 21–25; runrecord `fold_switch` events; `models/train-…-f392-p7` … `-f404-p7` (26 Phase 7 run directories, c-interface line 726) |
| 21 | HAC lag from overlapping holds; Bonferroni over N = 1,679 two-sided 95%; N overcounts by two deliberately | **CONFIRMED** | `promotion.py` 16–35; ledger `trial_count 1679`, `phase_7_runs 4`; findings §R.8, lines 714–718 |
| 22 | Power: tier 3 needs 2.6–3.3% mean net per trade at n = 16–22; tier 5 needs 1.0–1.2% at n = 71–100; a single target exit realises about 2.0% | **CORRECTED** | The committed pre-registration (findings §7b lines 695–698) is for the **three-month** window: **tier 3 4.9–5.5% at n = 10–11; tier 5 1.35–2.14% at n = 27–55**. The figures in the claim (n = 16–22, n = 71–100) are not on disk in any committed document — they match no table in `phase-7-findings.md`, the handover or the build logs (they may be the six-month estimate before D23, which was never committed). "About 2.0%" for a realised target exit is CONFIRMED (F5) |
| 23 | Tier 5 froze 2024-10-20 05:30Z, day 15 of 91, five consecutive losses, all STORJ/USD stops, equity 4,645.59 from 5,000 | **CONFIRMED** | DB `commands` row 2 and `block_records` first ts (1729402200000000); five `trades` rows all STORJ/USD `stop`; latest equity 4645.5885…; findings Part II §2, §4.5 ("day 15 of 91" = 15 days after the 2024-10-05 start) |
| 24 | `safety.max_consecutive_losses` is 5; invariant 14 freezes rather than liquidates; the drawdown limit is 10% | **CONFIRMED** | `default.yaml` 76–78; `trading-invariants.md` 254–258 |
| 25 | Tier 3 had two consecutive DOGE stops on 14 November and a CRV target on 15 November | **CONFIRMED** | DB `trades`: DOGE/USD closed 2024-11-14T22:35Z and 23:00Z (stop, stop); CRV/USD closed 2024-11-15T06:19Z (target) |
| 26 | The loss-streak check reads the last 500 closed trades and holds no state, so an operator clear cannot reset it | **CONFIRMED** | `engines/safety/contracts.py` line 50 `LOSS_STREAK_SCAN_LIMIT = 500`; `engine.py` 241–258; tracker 1628–1646 |
| 27 | Engine 7 found a candidate on 4,382 of 4,456 ticks at tier 3's halfway point and 4,372 were refused, nearly all by the cost gate | **NOT FOUND** | No document holds 4,382 / 4,456 / 4,372 (grep over `docs/build-log/phase-7/*.md`, the tracker, the findings). The committed halfway-ish snapshot is findings Part II §4.2: 6,118 tallies, 6,029 with a candidate, 6,016 refused (6,006 `net_edge_below_hurdle`, 10 `spread_wider_than_move`). Today's DB: 6,148 / 6,059 / 6,045. The shape of the claim (nearly every tick examined and refused at the cost gate) is confirmed; the numbers are not on disk |
| 28 | Runs launched 2026-09-19 23:12 local; findings document pushed before the launch (give both timestamps) | **CONFIRMED** | Process creation 2026-09-19T22:12:24Z = 23:12:24 BST (`Win32_Process`; `launch.json`); `bf702f7` LAUNCHED 23:14:23 +0100. Findings pushed `9c42fba` 17:21:48 +0100 (§7a) and `490f0d2` 18:01:06 +0100 (§7b), both before launch |
| 29 | Alphabetical made 1INCHUSD the candidate on 56% of bars and discarded 126 candidates unexamined | **CONFIRMED** | findings §4: 29,857 of 53,022 bars (56.3%); "about 126 pairs per bar were passed over on their name alone" (mean 126.6 pairs per bar) |
| 30 | Expected-move ranking gives about 46 trades over 12 months at tier 3 with net roughly zero | **CONFIRMED** | findings §4: 46 (35 pairs), −0.20% ± 0.65% at 0.60% fees, 12 months |
| 31 | Recording started 8 September 2026: tier 1 full book for about 10 pairs, per-minute summaries for about 139 more; only about 7 pairs replayable | **CONFIRMED** | first frame 2026-09-08T16:01:22Z (`recording_report_full_archive.json`); tier 1 = 10 pairs and tier 2 = 139 pairs on 2026-09-11 19:48Z (heartbeat line 1 of each tier; 170 today); "The replayable universe is about 7 pairs" (`a-platform.md` line 153). Note: the two-tier recorder began 2026-09-11; 8–11 September was the single-tier day-one recorder |
| 32 | Funding poller dead 15 to 19 September; gaps of 15 hours on 10–11 September and 308 minutes on 17 September | **CORRECTED in part** | Funding poller: CONFIRMED (last poll 2026-09-15 08:00Z, restarted 2026-09-19 04:42 local; files for 13, 14, 15, 19, 20 only). 308 minutes on 2026-09-17: CONFIRMED (03:13–08:20Z). **"15 hours on 10–11 September": NOT FOUND** — the recorded gaps are the ~10-hour silence of 2026-09-08T16:02Z→09-09T02:04Z and the disk-full outage of 2026-09-09T13:06Z; the file ends show the old recorder writing through 09-10T23:59:59Z and to 09-11T19:46:17Z with a 105 s hand-over to the two-tier recorder |
| 33 | `hurdle_multiple` 1.5, so expected move must exceed 2.5 × friction; tier 1 friction about 1.25%, bar about 3.125% | **CONFIRMED** | `default.yaml` 87–91; `trading-invariants.md` 179; findings §2 gives the fetched-schedule form (fees 1.20%, bar 3.0% before spread) |
| 34 | Engine 16 is in the chain as a gate, or was retired | **CONFIRMED — a gate** | operator ruling 2026-09-16: `trading-invariants.md` 137–142; `engine-contracts.md` 230–238; `decision/engine.py` line 121 `is_gate = True` |
| 35 | The paper broker lives in `src/acsoe/clients/paper/` | **CONFIRMED** | `broker.py`, `fills.py`, `README.md` there; `ownership.md` 270–281 |
| 36 | Entries are post-only limit at the best bid, resting window 300 s, filled only when a trade prints strictly below the limit; stop and target in the same tick resolves to stop; both measured from the fill price | **CONFIRMED** | `execution/engine.py` 5–7, 55–60; `default.yaml` 95; `fills.py` 17–19, 77–100; `position_manager/engine.py` 401–442, 585–620 |
| 37 | The veto-only Skeptic and the recorded rejected-trade dataset are not found in the meta-labelling literature | **NOT FOUND** | No literature search log, note or bibliography exists in the repository: grep for `meta-label`, `literature`, `novel`, `no prior` over `docs/`, `context/`, `docs/dataset/*.md` and the Phase 7 build logs finds only the glossary's definition, invariant 4's description, and findings line 727–728 ("No claim is made that any of these is the standard benchmark … No source was verified for such a claim", about the benchmarks). The only literature citations in the code are López de Prado (`walkforward.py` line 46) and Bailey and López de Prado 2014 (`promotion.py` 46–48). The absence claim is the writer's to establish, not the repository's |

**Counts: CONFIRMED 32 (of which 2 carry a stated caveat: 12, 18), CORRECTED 3 (17, 22, 32 — 32 partly), NOT FOUND 2 (27, 37). Total 37.**
