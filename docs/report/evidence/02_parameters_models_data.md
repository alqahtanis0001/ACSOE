# Evidence pack 02 — parameters, models, data

**Read at commit `9f5a1449378c10e8f8f87ec27732914a0a19e92f` (`9f5a144`), `main`, clean tree, 2026-09-20T15:33Z–15:55Z.** Run databases read through `file:PATH?mode=ro&immutable=1` (main file only, as at SQLite's last checkpoint). No file outside `docs/report/` was written; no process was touched.

## Contents

- [A. Configuration, verbatim](#a-configuration-verbatim)
  - [A.1 config/default.yaml in full](#a1-configdefaultyaml-in-full)
  - [A.2 Tier profiles](#a2-tier-profiles)
  - [A.3 The spread bucket table](#a3-the-spread-bucket-table)
  - [A.4 The fee schedule file](#a4-the-fee-schedule-file)
  - [A.5 The measured account tier](#a5-the-measured-account-tier)
  - [A.6 Triple barrier, decision bar, loop tick, lookbacks](#a6-triple-barrier-decision-bar-loop-tick-lookbacks)
  - [A.7 Safety limits and what each triggers](#a7-safety-limits-and-what-each-triggers)
  - [A.8 scout.rank_feature: committed versus run](#a8-scoutrank_feature-committed-versus-run)
  - [A.9 The hurdle](#a9-the-hurdle)
- [B. Models and learning](#b-models-and-learning)
  - [B.1 Engine 8, the predictor](#b1-engine-8-the-predictor)
  - [B.2 Does the live daemon retrain?](#b2-does-the-live-daemon-retrain)
  - [B.3 Engine 15, the skeptic](#b3-engine-15-the-skeptic)
  - [B.4 The Dissimilarity Index](#b4-the-dissimilarity-index)
  - [B.5 Engine 13, anomaly](#b5-engine-13-anomaly)
  - [B.6 Engine 12, regime](#b6-engine-12-regime)
  - [B.7 Engine 14, adaptive router](#b7-engine-14-adaptive-router)
  - [B.8 Engine 20, tournament](#b8-engine-20-tournament)
  - [B.9 Walk-forward](#b9-walk-forward)
  - [B.10 Labels](#b10-labels)
  - [B.11 SHAP](#b11-shap)
  - [B.12 Engine 19, memory: approval and rejection rows](#b12-engine-19-memory-approval-and-rejection-rows)
  - [B.13 Position sizing and exits](#b13-position-sizing-and-exits)
- [C. Data](#c-data)
  - [C.1 The historical archive](#c1-the-historical-archive)
  - [C.2 Live recording](#c2-live-recording)
  - [C.3 Funding and fee pollers](#c3-funding-and-fee-pollers)
  - [C.4 Phase 7's declared substitutes](#c4-phase-7s-declared-substitutes)
  - [C.5 The excluded pairs](#c5-the-excluded-pairs)

---

## A. Configuration, verbatim

### A.1 config/default.yaml in full

372 lines, last changed 2026-09-19 08:22 local (file mtime); committed.

*Verbatim from `config/default.yaml`, lines 1–372:*

```yaml
# ACSOE default configuration.
#
# Percentages are decimals: 0.03 means 3%. Durations are seconds unless the key
# name says otherwise. Money values are Decimal — quote them so YAML does not
# parse them as floats.
#
# NOTHING the exchange can tell us appears in this file. No fee, no order
# minimum, no tick size, no precision. Those are fetched at runtime, every time.
# See rule 2 of context/trading-invariants.md.
#
# A key whose value is `null` is OPERATOR REQUIRED: the context files name the
# key but never specify its value, and it is trading behaviour, so the lead may
# not invent one. The loader must REFUSE TO START while any of them is null,
# naming the key. That is fail-closed and deliberate — a plausible default here
# is a number that silently decides how much money is at risk.
#
# As of 2026-09-08 there are none left: the operator supplied all nine. They are
# marked "Operator-chosen" and are PROVISIONAL — starting values to make Phase 3
# runnable, to be revised once the economics are measured rather than assumed.
# The refusal machinery stays; it is what protects the tenth such key.

mode: paper                      # paper | live | replay. Phase 0 accepts paper only:
                                 # platform/live_guard.py is a Phase 8 deliverable, and
                                 # the absence of the guard is not permission.

console:
  port: 8765                     # README default; the config is the source of truth
  poll_interval_ms: 500          # ui-context.md; watermark poll, not browser polling
  stale_after_ms: 120000         # ui-context.md; two loop ticks. A figure older than
                                 # this renders at 50% opacity with its age beside it.
                                 # Validation: poll_interval_ms <= stale_after_ms / 4

logging:
  level: "INFO"                  # requested by A, spec 08
  retention_days: 14             # daily rotation in logs/. Covers Phase 8's 7-day soak
                                 # plus slack, so the run log outlives the run it proves.

timeframes:
  decision_bar_s: 900            # 15 minutes. Candidates are born only on a closed bar.
  loop_tick_s: 60                # 1 minute. Manages positions and entry orders; never
                                 # generates a signal.

barriers:                        # Locked decisions; triple-barrier labelling
  target_pct: 0.03               # +3%
  stop_pct: 0.015                # -1.5%
  timeout_bars: 48               # 48 x 15m = 12h, consistent with the 2-12h horizon

dataset:                         # Which labelled rows and pairs form the training dataset.
                                 # Two operator rulings of 2026-09-12, recorded under Locked
                                 # Decisions in context/progress-tracker.md. Neither is a
                                 # trading threshold: no gate reads either and no order is
                                 # sized from them. Both decide what Phase 5 learns from.
  decision_start_date: "2017-01-01"
                                 # Decision bars before this UTC calendar date are excluded
                                 # from labelling. The archive begins 2013-10-07 and its
                                 # earliest bars are single trades of 0.1 BTC in fifteen
                                 # minutes: real, but a market no position could have been
                                 # taken in at any size, and a model trained on them learns
                                 # patterns that do not transfer. The exclusion is about
                                 # TRADABILITY, not data quality. research/labelling.py
                                 # applies it and reports how many rows it removed, per pair.
  min_labelled_rows: 0           # A pair with fewer labelled rows than this is left out of
                                 # the dataset by engine 23 `backtest`. 0 means NO FLOOR and
                                 # 0 is the value today: the eleven pairs under 20,000 rows
                                 # are kept. A cross-sectional model may want a floor; that
                                 # decision is deferred behind this named knob, not
                                 # overlooked. It is 0 rather than null because a null key
                                 # in this file means OPERATOR REQUIRED and stops every
                                 # process at load (see the header above).

safety:                          # Engine 17, the circuit breaker. Guard chain, every tick.
  max_consecutive_data_blocks: 15   # invariant 14. One full decision bar at a 1m tick:
                                    # long enough that a websocket reconnect never
                                    # liquidates the account, short enough that nothing
                                    # is carried through a second bar on bad data.
  max_drawdown_pct: 0.10            # Operator-chosen 2026-09-08. Invariant 14's "configured
                                    # drawdown limits". Provisional — see the tracker.
  max_consecutive_losses: 5         # Operator-chosen 2026-09-08. At a ~61% break-even win
                                    # rate a 5-loss run is roughly a 1-in-100 event.
  error_rate_window_s: 3600         # architecture-context.md specifies "the trailing hour"
                                    # for the error rate, so this one is specified, not
                                    # operator-required. B caught that it was wrongly null.
  max_errors_in_window: 20          # Operator-chosen 2026-09-08. 20 engine errors inside the
                                    # 3600s window trips the breaker.

trading:
  hurdle_multiple: 1.5           # Operator-chosen 2026-09-08. Invariant 5 requires
                                 # net_edge > hurdle_multiple x friction, so a candidate
                                 # needs expected_move > 2.5 x friction. At tier 1 that is
                                 # 3.125%, above the 3% target barrier — nothing clears the
                                 # cost gate at tier 1 by design. See the tracker.
  risk_fraction_per_trade: 0.01  # Operator-chosen 2026-09-08. 1% of total equity.
  max_concurrent_positions: 3    # Operator-chosen 2026-09-08. Note the balance binds first
                                 # at $5,000: one position is ~$3,333 notional. See tracker.
  entry_unfilled_window_s: 300   # Operator-chosen 2026-09-08. 5 minutes, a third of a
                                 # decision bar, then cancel and abandon. Never chase.
  base_reporting_currency: USD   # Operator-chosen 2026-09-08.
  allow_crypto_quoted: false     # invariant 7. Crypto-quoted pairs are a second
                                 # directional bet the system did not choose to make.
  stable_quote_currencies:       # Operator-chosen 2026-09-10. Requested by A, spec 39.
                                 # Which quote currencies count as STABLE. Invariant 7 disables
                                 # crypto-quoted pairs and defines one as a pair whose quote is
                                 # "BTC, ETH, or any non-stable asset" — that sentence needs
                                 # this set, and nothing in the repo held it. Kraken does not
                                 # supply it: AssetPairs carries no asset class, so it is not
                                 # derivable at runtime and must be stated.
                                 #
                                 # CURRENCIES, NOT PAIRS. This does not name what may be
                                 # traded; the tradable universe is still computed per tick by
                                 # engine 7 from balances and live prices, which is a Locked
                                 # Decision. This only says which quote currencies are not a
                                 # second directional bet.
                                 #
                                 # The two stablecoins are here on the operator's ruling and
                                 # are the judgement call in this list: a peg is an issuer's
                                 # promise, not a central bank's, so USDC and USDT carry a
                                 # depeg risk that the seven fiats do not. PROVISIONAL, like
                                 # the other operator-chosen values, and revisable.
    - USD
    - EUR
    - GBP
    - CAD
    - AUD
    - CHF
    - JPY
    - USDC
    - USDT

paper:
  starting_balances: {USD: "5000.00"}   # Operator-chosen 2026-09-08. Currency-to-amount
                                 # map; amounts are quoted strings, parsed as Decimal.

order_book:                      # Engine 9 `order_book`. Requested by C, spec 96.
  depth: 10                      # Levels a side engine 9 walks when it estimates the
                                 # slippage a taker exit would pay. Chosen by the lead
                                 # 2026-09-16 at C's request, and it is NOT an arbitrary
                                 # ten: `scripts/record.py` subscribes the book at that
                                 # depth, so every frame in `data/raw/` carries at most
                                 # ten levels a side, and the committed fixture engine 9
                                 # is validated against inherits that limit.
                                 #
                                 # A deeper value would configure the engine to walk past
                                 # anything the evidence can hold, and the failure is
                                 # silent in the direction that matters: the walk ends
                                 # early, the book reads as thin, `book_too_thin` fires,
                                 # and nothing says the configuration was the cause. It
                                 # would also make that refusal one the fixture can never
                                 # exercise honestly.
                                 #
                                 # PROVISIONAL, and tied to the recorder: whoever changes
                                 # `record.py`'s subscription depth changes this, and
                                 # `platform/config.py` bounds it at MAX_BOOK_DEPTH so the
                                 # two cannot silently diverge.

kraken:                          # Client tuning. Requested by A, spec 25.
                                 # NOTHING here is a value the exchange can tell us: no fee,
                                 # no order minimum, no tick size, no precision. What is here
                                 # is OUR OWN self-imposed request budget and timeout, chosen
                                 # by the lead, and it is explicitly NOT a claim about what
                                 # Kraken permits — a remembered published rate limit is
                                 # exactly the stale knowledge AGENTS.md warns about.
                                 # Deliberately conservative: under the real ceiling costs
                                 # latency, over it costs a ban mid-session. Flagged for
                                 # revision against the documented limits before Phase 8.
  rest_capacity: 15              # Token-bucket depth for REST. The burst allowance.
  rest_refill_per_s: 0.5         # Sustained rate: one request every two seconds, far below
                                 # what a loop tick needs at one decision per fifteen minutes.
  rest_timeout_s: 10             # HTTP timeout. An order of magnitude above a healthy round
                                 # trip, short enough that a hung socket cannot outlive the
                                 # one-minute loop tick.
  cache_ttl_s:                   # Lead-chosen 2026-09-10, spec 37. How long a fetched snapshot may
                                 # price a decision before it must be fetched again. OUR OWN
                                 # re-fetch interval, not a claim about anything Kraken
                                 # publishes or permits.
                                 #
                                 # Invariant 2: a cache stale beyond its TTL COUNTS AS A FAILED
                                 # FETCH. It is not returned, and in live mode the trade blocks.
                                 # Separate from the last-known-good retention in
                                 # `clients/kraken/`, which keeps the same values FOREVER, past
                                 # any TTL, and may be read only by invariant 14's emergency
                                 # liquidation. Two mechanisms, two readers; do not merge them.
                                 #
                                 # Two keys and not one, because the two values change on
                                 # different timescales.
    asset_pairs: 300             # Pair rules change when Kraken lists or delists something.
    trade_volume: 60             # The fee tier can move on a single trade, and it prices the
                                 # cost gate, so it is re-read on the timescale of the loop.

data_guard:                      # Engine 4, the first real gate. Requested by A, spec 29.
  max_data_age_s: 120            # Operator-chosen 2026-09-09. The staleness threshold: market
                                 # data older than this blocks the tick. Two loop ticks at
                                 # loop_tick_s 60, so a single missed tick is tolerated and a
                                 # second consecutive one is not. Distinct from
                                 # console.stale_after_ms, which is a rendering rule about
                                 # fading a figure and decides nothing about trading.

market_sensor:                   # Engine 3. Requested by A, spec 28.
  published_bars: 200            # How many recent closed 15m candles reach `state` each tick.
                                 # A PLUMBING BOUND, NOT A TRADING THRESHOLD — no gate reads
                                 # it and no money depends on it, which is why the lead may
                                 # choose it and it is not OPERATOR REQUIRED. 200 covers the
                                 # 48-bar holding horizon plus the lookback a Phase 5
                                 # indicator is likely to want, and is bounded so `state`
                                 # stays serialisable. Raising it is a lead edit.

backtest:
  training_window_days: 90       # Locked decision: rolling 90-day cap
  retrain_interval_days: 7       # Locked decision: weekly, matching the live cadence
  embargo_bars: 48               # Lead-chosen 2026-09-11, spec 58. Invariant 10 requires folds
                                 # to be purged AND embargoed; it does not name the embargo's
                                 # length and nothing else in the repository did.
                                 #
                                 # PROVISIONAL and flagged to the operator, like
                                 # market_sensor.published_bars and kraken.cache_ttl_s. It is a
                                 # research-methodology bound rather than a trading threshold:
                                 # no gate reads it and no order is sized from it. It does
                                 # decide whether a model is honestly validated, which is why
                                 # it is written down with its reasoning rather than defaulted
                                 # quietly.
                                 #
                                 # 48 is one full label horizon, matching barriers.timeout_bars.
                                 # The purge already removes every training row whose label
                                 # window literally overlaps the test window; the embargo exists
                                 # for the serial correlation that survives the purge, so a span
                                 # equal to the horizon is the defensible starting value.
                                 # Raising it costs training rows; lowering it risks a leak that
                                 # no test can see from the outside.
                                 #
                                 # NOT OPTIONAL AT THE POINT OF USE. This is a leaf key, so
                                 # Config.get returns None rather than raising while it is
                                 # absent (A, spec 58 handoff). Whatever reads it must refuse a
                                 # None explicitly. A zero or absent embargo is exactly the
                                 # Phase 4 defect that looks like success.

# --- Phase 5: models. Lead-authored 2026-09-13 after A's spec 61 fields landed. ---------
#
# TWO KEYS ARE DELIBERATELY ABSENT, NOT NULL: models.*_run_id and scout.rank_feature.
# Each is an optional leaf on the config model, so an absent key reads as None and the
# engine that needs it fails closed (blocks with a reason naming the key) while the
# Phase 5 criterion that judges it reports PENDING. Writing either as `null` is a
# different thing: a null in this file means OPERATOR REQUIRED and stops every process
# at load. Absent and null are one character apart in a diff and behave in opposite
# directions. The run ids point at artefacts under models/, which is gitignored, so a
# fresh clone has none; the ranking feature waits on the Phase 7 question of whether any
# ranking feature pays for a trade (operator ruling 2026-09-15), and engine 7 ranks
# alphabetically meanwhile.
#
# THE THREE THRESHOLDS ARE NOW SUPPLIED AND ALL THREE ARE PROVISIONAL:
# skeptic.veto_threshold (0.50, ruled 2026-09-14), anomaly.threshold_percentile (0.99)
# and prediction.di_percentile (0.99, both ruled 2026-09-15). Each was withheld until the
# walk-forward had reported (operator ruling 2026-09-12: a value chosen before there is a
# distribution to place it on is a guess), each is chosen from that distribution, and each
# is revisited once the chain runs end to end. The reasoning sits with the key.

models:
  dir: models                    # The artefact root. One directory per training run,
                                 # never overwritten; see architecture-context.md.

features:                        # modelling/features.py, spec 63.
  version: "f1"                  # Written into every manifest; a model trained on f1
                                 # features refuses to load against f2 names.
  max_lookback_bars: 192         # 48 hours of 15m bars. Bounded by
                                 # market_sensor.published_bars (200) and validated
                                 # against it at load, because a lookback engine 3 does
                                 # not publish can never be filled live.
  min_lookback_fill: 0.8         # A window with less than 80% of its expected bars
                                 # present yields NaN for every feature over it. The
                                 # feature layer marks a gap; it never interpolates one.

macro:                           # Engine 6, spec 65, and spec 67's offline join. Two
                                 # spellings of one pair: what the live stream keys
                                 # candles by, and what the archive file is called.
                                 # PROVISIONAL on the live side: the committed fixtures
                                 # spell it BTC/USD and the real stream must agree; if
                                 # it does not, this line changes, not the code.
  btc: {live: "BTC/USD", archive: "XBTUSD"}
  eth: {live: "ETH/USD", archive: "ETHUSD"}

prediction:                      # Engine 8 and the DI, specs 67, 68, 71. Plumbing.
  di_window_days: 30             # Locked decision: 30-day per-pair window for the DI
                                 # reference set, taken from the end of each fold's
                                 # training window.
  di_neighbours: 10              # k for the mean k-nearest distance.
  di_reference_rows: 200000      # Subsample cap on the reference set, seeded from
                                 # seeds.train, so the DI fit stays tractable per fold.
  calibration_days: 14           # The held-out tail of the training window the
                                 # calibrator is fitted on. Never the test window.
  threads: 4                     # Fixed, because LightGBM determinism needs a fixed
                                 # thread count as well as a seed.
  di_percentile: 0.99            # OPERATOR, ruled 2026-09-15, PROVISIONAL until the chain
                                 # runs end to end. With the 48-bar exclusion (spec 68
                                 # amendment) the DI refuses 3.31% of complete out-of-sample
                                 # rows against 1% nominal, over the 405 fitted folds -
                                 # roughly three times nominal, which is the right direction
                                 # for an out-of-distribution refusal, and nothing like the
                                 # 74.9% it refused at this percentile before the exclusion.
                                 # 0.95 rejected: 6.79%, too much for a gate meant to catch
                                 # genuinely unfamiliar conditions.
                                 # docs/dataset/di-exclusion-refit-2026-09-15.json.

anomaly:                         # Engine 13, specs 70, 72.
  threshold_percentile: 0.99     # OPERATOR, ruled 2026-09-15, PROVISIONAL. 1.24% blocked out
                                 # of sample against 1% nominal, stable by year (0.9% to
                                 # 1.8%), and what it blocks is the volatile tail (stop rate
                                 # 0.67 against 0.50). 0.95 rejected: 5.55% blocked, including
                                 # BUY calls with better pre-friction returns than the ones
                                 # kept. The spec 70 ten-sigma question stays open - a
                                 # ten-sigma volume spike scores at the 0.904 quantile and
                                 # this threshold does not block it.

skeptic:                         # Engine 15, specs 69, 73.
  veto_threshold: 0.50           # OPERATOR, ruled 2026-09-14 from the veto sweep,
                                 # PROVISIONAL until the chain runs end to end. At 0.50 the
                                 # survivors hit the target at 0.531 against 0.473 for the
                                 # same number of the predictor's most confident calls, the
                                 # two sets share only 44% of calls, and the survivors beat
                                 # the vetoed calls in every test year 2017 to 2024.

regime:                          # Engine 12, spec 66. Percentile-relative rules, chosen
                                 # by the lead as plumbing: no gate reads the label and
                                 # no order is sized from it. PROVISIONAL.
  high_vol_percentile: 0.9       # Short-window realised volatility above the 90th
                                 # percentile of its own long-window distribution.
  trend_efficiency: 0.3          # Net move over path length above 0.3 reads as
                                 # trending; below, choppy.

training:                        # research/training.py, spec 67. LightGBM hyperparameters
                                 # as CONFIG rather than module constants, because a run
                                 # must be reproducible from its config plus its data and a
                                 # tree count in a constant is a number the manifest cannot
                                 # prove. Plumbing the lead chooses, PROVISIONAL, and written
                                 # into every manifest: no gate reads them and no order is
                                 # sized from them. Lead-chosen 2026-09-13.
  num_trees: 400                 # Boosting rounds per fold.
  learning_rate: 0.05            # Shrinkage per round; strictly inside 0 and 1.
  num_leaves: 31                 # LightGBM's default; must exceed 1, because a single leaf
                                 # is a model that returns the base rate and would report a
                                 # Brier equal to the base-rate Brier, reading as "no edge"
                                 # when the truth is "never allowed one" (A-2's bound).
  min_data_in_leaf: 200          # Rows per leaf; large, because rows overlap at a 48-bar
                                 # horizon and the effective sample is far smaller than the
                                 # row count (uniqueness weights, spec 59 decision 5).
  skeptic_cap_folds: 13          # OPERATOR, ruled 2026-09-16 (spec 83); applied from Phase 7
                                 # (R2, 2026-09-19): fold k's skeptic trains only on folds
                                 # k-13..k-1. The Phase 7 window's skeptics were staged with
                                 # --cap 13 before this key landed (D20); same value.

scout:                           # Engine 7's ranking, spec 76.
  rank_descending: true          # Direction for rank_feature when it is set.
  # rank_feature: OPERATOR, absent until spec 75's study reports. Alphabetical until
  # then, and the engine publishes rank_feature: null so nobody reads a choice into it.

replay:                          # Phase 7, specs 126, 129, 131. Read ONLY by the offline replay
                                 # (invariant 2, "In replay mode"); the replay client refuses
                                 # construction in paper and live. Every value it serves that the
                                 # archive did not record is DECLARED, never measured.
  asset_pairs_file: tests/fixtures/kraken/asset_pairs_recorded_2026-09-19.json   # spec 127
  instrument_file: tests/fixtures/kraken/instrument_recorded_2026-09-19.json     # spec 127
  pair_names_file: tests/fixtures/kraken/pair_names_recorded_2026-09-19.json     # spec 127
  spread_table_file: tests/fixtures/replay/spread_book_table_2026-09-19.json    # spec 130, declared
  fee_schedule_file: tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json  # fetched 2026-09-19, declared
  fee_tier: 3                    # R3, operator 2026-09-19: tiers 3 and 5, one per run. The driver's
                                 # --fee-tier sets each run's tier; this file is never edited between runs.
  partitions_dir: data/derived/trades_weekly   # spec 128, runtime output (gitignored)
  first_fold: 379                # R4, operator 2026-09-19: six months ending at fold 404's
  last_fold: 404                 # test close, 2025-01-04 00:00 UTC.
  run_id_format: "train-20260913T205245-067b2b9d-f{fold}-p7"   # spec 135's run directories

seeds:
  global: 20260908               # Every random seed comes from config, so a training run
  train: 20260908                # is reproducible from its config plus its data.
  seed_generator: 20260908       # B's fixture generator, so seeding twice is identical.
```

### A.2 Tier profiles

**There are no tier profile files.** A run's tier is a command-line flag, `--fee-tier N`, which the driver writes over the committed `replay.fee_tier: 3` (`src/acsoe/cli/research.py` lines 749–753: `tier = int(args.fee_tier) …; run_config = derive_config(committed, {"mode": "replay", "replay.fee_tier": tier, "scout.rank_feature": ranking})`). `config/default.yaml` lines 362–363: "`fee_tier: 3` # R3, operator 2026-09-19: tiers 3 and 5, one per run. The driver's `--fee-tier` sets each run's tier; this file is never edited between runs." The tier selects one row of the fee schedule fixture (A.4); the replay client serves that row's maker and taker through the `TradeVolume` surface (`src/acsoe/clients/kraken/replay.py` lines 32–33). The two runs as launched (`docs/build-log/phase-7/launch_phase7.ps1.txt` lines 39–42, 49):

```
$runs = @(
    @{ name = 't3-expected_move'; ranking = 'expected_move'; tier = 3 },
    @{ name = 't5-expected_move'; ranking = 'expected_move'; tier = 5 }
)
… $extra = '--begin 2024-10-05T00:15:00'
```

What each run recorded on its own `runs.scenario_description.fee` (pack 01 §A.4): tier 3 `maker_fee_pct "0.0022", taker_fee_pct "0.0038", volume_30d_served "10000"`; tier 5 `maker_fee_pct "0.0015", taker_fee_pct "0.003", volume_30d_served "50000"`; both `table "spot_crypto"`, `file tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`, `sha256 ee77a8c4…`. Everything else — spread table, depth, pair rules, partitions, quote rule, ranking, run-id format — is identical between the two scenario descriptions.

### A.3 The spread bucket table

File: `tests/fixtures/replay/spread_book_table_2026-09-19.json`. Built by `scripts/build_bucket_table.py` (script sha256 `50f2144264d7448a027b157a937bc8f17c77872adf6f0ca334bb40d06a43608c`) from the recorder's minute summaries (`data/summaries/summary_2026-09-11.jsonl` and `summary__msi__2026-09-11.jsonl` … `summary__msi__2026-09-19.jsonl`, ten files, each listed with bytes read and sha256 in the fixture's `_provenance.sources`). Recording span `2026-09-11T16:13:00Z` to `2026-09-19T00:45:00Z`, **7.3556 days**; **185 recorded USD pairs**. Definitions (verbatim from `_provenance.definitions`): `spread_bps`: "per pair, the median over clean, schema-2 minutes with samples of the minute's p50 spread; per bucket, the median of those per-pair medians"; `depth_bid_bps_to_10k_from_mid`: "per pair, the median over the same minutes where the book reached $10,000 of depth_bid_bps: the distance from the mid, in bps, at which resting bids first add up to $10,000; per bucket, the median of those"; `usd_day`: "the pair's summed quote_volume over every summary row in the span, divided by the span in days". Its statement: "DECLARED, NOT MEASURED. … It is a declared scenario value applied to a different period, never a measurement of that period. The interquartile ranges are the declared uncertainty of each value."

| Bucket (trailing 24 h USD volume) | Recorded pairs | Spread bps median (q25–q75) | Depth to $10k from mid, bps median (q25–q75) | Pairs with depth | Slippage at $5k, check only (bps) |
|---|---|---|---|---|---|
| < $10k | 16 | **30.3952** (12.1729–35.9997) | 86.2069 (39.3895–141.881) | 11 (5 never reached $10k) | 17.73 |
| $10k–$100k | 49 | **25.7732** (11.1576–39.2157) | 100.539 (45.307–176.391) | 43 (6 never) | 20.81 |
| $100k–$1M | 84 | **12.31675** (7.23851–19.5503) | 35.1523 (21.6415–62.61555) | 83 | 7.45 |
| $1M–$10M | 36 | **5.52274** (2.70234–9.41811) | 8.94658 (5.26593–15.8635) | 36 | 1.67 |
| > $10M | 0 | mapped from the $1M–$10M row | mapped | — | — |

The served book is ten evenly spaced levels from the half-spread to the depth distance (`scenario_description.spread_book_table.levels_per_side 10`, `depth_notional_usd 10000`), so the served $5k slippage is 15.8 / 19.5 / 6.5 / 1.4 bps, slightly below the continuous check figures (`docs/dataset/phase-7-findings.md` line 639). The same table is `spread_buckets.csv` in pack 04.

### A.4 The fee schedule file

`tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`. Provenance block (verbatim fields): `source_url "https://www.kraken.com/features/fee-schedule"`, `fetched_at_utc "2026-09-19T02:59:51Z"`, `http_status 200`, `raw_page "kraken_fee_schedule_2026-09-19.html.gz"` (committed beside it, uncompressed sha256 `032c56fe…`), `extracted_by "docs/dataset/phase-7-recon-2026-09-19/scripts/extract_fee_schedule.py"`. Restructure note: "On July 9, 2026, Kraken changed how the fee tier is determined: the best of spot volume, futures volume and Assets on Platform, across the platform." (`support.kraken.com/articles/cross-platform-fee-tier-changes`, fetched 2026-09-19T03:00:49Z, raw page `kraken_cross_platform_fee_tiers_2026-09-19.html.gz`). Use: "A DECLARED fee scenario for offline replay only … nothing on disk dates any earlier schedule, so applying it to a 2023-24 window is a stated assumption."

Spot Crypto table, tiers 1–5 (the full 17-row table incl. Pro tiers is `fee_schedule.csv` in pack 04):

| Tier | Spot 30-day volume OR | Futures 30-day volume OR | Assets on Platform | Maker | Taker |
|---|---|---|---|---|---|
| 1 | $0+ | < $5M | N/A | 0.40% | 0.80% |
| 2 | $2.5K+ | ≥ $5M | N/A | 0.30% | 0.60% |
| 3 | $10K+ | ≥ $10M | 20k | 0.22% | 0.38% |
| 4 | $25K+ | ≥ $15M | 50k | 0.20% | 0.35% |
| 5 | $50K+ | ≥ $25M | 100k | 0.15% | 0.30% |

The file also carries the "Spot Maker Rebate Program" table and the "Stablecoin, Pegged Token & FX Pairs" table (0.20%/0.20% at $0+). Every pair in the runs was served the Spot Crypto row (lead decision D8: "the FX, stablecoin and pegged-token pairs are overcharged by this, the conservative direction", findings line 641).

### A.5 The measured account tier

- Record: `data/raw/fees/fees__msi__2026-09-19.jsonl`, first `trade_volume` line, `ts_recv "2026-09-19T05:08:45.806613Z"`, `endpoint "/0/private/TradeVolume"`, request `pair [USDTZUSD, XXBTZUSD, USDCUSD]` with `fee_schedule "true"`, response `error: []`. Result: `volume "0.00000"`, `inputs {domain_spot_volume_30d "0.00000", domain_assets_on_platform "36.45635", domain_futures_volume_30d "0.00000"}`; `fees.XXBTZUSD {fee "0.8000", nextfee "0.6000", nextvolume "2500.00000"}` (taker), `fees_maker.XXBTZUSD {fee "0.4000", nextfee "0.3000"}`; the stablecoin/FX pairs (USDCUSD, USDTZUSD, ZEURZUSD) show `0.2000` on both sides. That is **tier 1 of the Spot Crypto table: maker 0.40%, taker 0.80%**, and the account's 30-day volume is zero. The poll repeats hourly; the 2026-09-20T15:00:00Z line shows the same tier with `domain_assets_on_platform "41.75914"`.
- Recorded in `context/progress-tracker.md` lines 21–30: "On 2026-09-19 one read-only authenticated `TradeVolume` call (pair BTC/USD, HTTP 200, empty error list) returned **tier 1: maker 0.40%, taker 0.80%**. That was measured on the account, not assumed. … At the account's own tier the cost gate cannot pass anything at the current barriers."
- The log summary (`logs/fees__msi__2026-09-19.log`): slot `2026-09-19T05:08:44.837865Z`, `spot_pairs 10, asset_pairs 1450, schedules_returned: true`, `fees_pairs [ADAUSD, HYPEUSD, SOLUSD, USDCUSD, USDTZUSD, XETHZUSD, XXBTZUSD, XXRPZUSD, XZECZUSD, ZEURZUSD]`.

### A.6 Triple barrier, decision bar, loop tick, lookbacks

| Parameter | Value | Source |
|---|---|---|
| Target barrier | `barriers.target_pct: 0.03` (+3%) | `config/default.yaml` line 44 |
| Stop barrier | `barriers.stop_pct: 0.015` (−1.5%) | line 45 |
| Timeout | `barriers.timeout_bars: 48` (48 × 15 min = 12 h); a time, not a row count | line 46; `context/architecture-context.md` lines 95–102 |
| Decision bar | `timeframes.decision_bar_s: 900` (15 minutes) | line 39 |
| Loop tick | `timeframes.loop_tick_s: 60` (1 minute) | line 40 |
| Feature lookbacks | `LOOKBACK_BARS = (4, 16, 48, 96)` bars: one hour, four hours, twelve hours, one day | `src/acsoe/modelling/features.py` line 106 |
| Max lookback / published bars | `features.max_lookback_bars: 192`; `market_sensor.published_bars: 200`; `features.min_lookback_fill: 0.8` (a window under 80% filled yields NaN) | `default.yaml` lines 198, 262, 266 |
| Training window / retrain cadence / embargo | 90 days before the test window; weekly; 48 bars | lines 207–209 |
| DI window / neighbours / reference cap / calibration tail | 30 days per pair; k = 10; 200,000 rows; 14 days | lines 280–287 |

### A.7 Safety limits and what each triggers

`config/default.yaml` lines 71–84 and `context/trading-invariants.md` invariant 14 (lines 240–281):

| Limit | Value | Triggers | Source |
|---|---|---|---|
| `safety.max_consecutive_data_blocks` | 15 ticks (one decision bar) | **`close_all`** (liquidate) — the only `safety` escalation; only when open positions or resting entries exist | `default.yaml` 72; invariants 246–252 |
| `safety.max_drawdown_pct` | 0.10 | **`freeze`** (stop opening, keep managing); drawdown = `(peak_equity − equity) / peak_equity` from the latest snapshot | `default.yaml` 76; invariants 254–258; `engines/safety/engine.py` 232–239 |
| `safety.max_consecutive_losses` | 5 | **`freeze`**; a loss is `realised_pnl < 0`, counted backwards over the last 500 closed trades until a non-loss | `default.yaml` 78; `safety/engine.py` 241–258; `LOSS_STREAK_SCAN_LIMIT = 500` (`safety/contracts.py` 50) |
| `safety.max_errors_in_window` / `error_rate_window_s` | 20 in 3,600 s | **`freeze`**; counts `block_records.status = 'ERROR'` in the trailing hour | `default.yaml` 80–84 |
| Operator `Close all` | — | `close_all` | `architecture-context.md` 258 |

Tripping comparisons (`safety/engine.py` lines 266–274): `drawdown_pct >= max_drawdown_pct`, `consecutive_losses >= max_consecutive_losses`, `errors_in_window >= max_errors_in_window`. A suppressed `close_all` falls back to the strongest unsuppressed action (invariants 260–279). What tripped tier 5: the loss streak, not the drawdown (equity −7.1% < 10%).

### A.8 scout.rank_feature: committed versus run

- **Not in the committed config.** `config/default.yaml` lines 348–351: `scout:` / `rank_descending: true` / `# rank_feature: OPERATOR, absent until spec 75's study reports. Alphabetical until then, and the engine publishes rank_feature: null so nobody reads a choice into it.` The tracker records the YAML comment as stale and the question as open (`context/progress-tracker.md` lines 1687–1697: "**OPEN, for the operator's ruling (2026-09-19): the committed daemon still ranks alphabetically.** … **Phase 7 avoids it only because the replay driver passes `--ranking expected_move`.**").
- **The daemon as committed ranks alphabetically**: `src/acsoe/engines/scout/contracts.py` `rank_universe` ("With `feature` `None` the ordering is alphabetical", tracker line 1690); `context/trading-invariants.md` line 161: "Without the key, it orders alphabetically, which is the Phase 7 baseline."
- **The runs rank by expected move**, read from their own rows: `runs.scenario_description.ranking = "expected_move"`, `alphabetical_baseline = false` (both databases); every `scout_tallies` row carries `rank_feature = "expected_move"`, `rank_descending = 1` (the export in pack 04 `candidates_per_tick_tier*.csv` was built from those rows; the approval snapshot in pack 01 §C.9 shows `"rank_descending": true, "rank_feature": "expected_move"`). The driver sets it: `cli/research.py` lines 608–611 `RANKINGS = {"expected_move": "expected_move", "alphabetical": None}` and line 752.

### A.9 The hurdle

`trading.hurdle_multiple: 1.5` (`default.yaml` line 87 with its comment: "a candidate needs expected_move > 2.5 x friction. At tier 1 that is 3.125%, above the 3% target barrier — nothing clears the cost gate at tier 1 by design"). The rule (`context/trading-invariants.md` lines 167–175):

*Verbatim from `context/trading-invariants.md`, lines 165–175:*

````markdown
## 5. A trade must clear the live cost hurdle

```
friction  = live_maker_fee + live_taker_fee + measured_spread + estimated_slippage
net_edge  = expected_move − friction
TRADE ONLY IF net_edge > hurdle_multiple × friction
```

`net_edge` is what you compute. The rule is the third line. They are not the same thing.

Friction assumes **maker on entry, taker on exit** — the worst realistic case, since a stop must always exit as a taker. Never assume a maker exit when sizing the hurdle, even though target exits may achieve one.
````

The implementation, `src/acsoe/engines/cost/engine.py`, the module docstring and the one comparison:

*Verbatim from `src/acsoe/engines/cost/engine.py`, lines 1–30:*

````python
"""Engine 10 `cost` — the gate that refuses a trade which cannot pay for itself.

Invariant 5, verbatim, because this engine is the only implementation of it:

```
friction  = live_maker_fee + live_taker_fee + measured_spread + estimated_slippage
net_edge  = expected_move - friction
TRADE ONLY IF net_edge > hurdle_multiple x friction
```

"`net_edge` is what you compute. The rule is the third line. They are not the same
thing." The third line is the one thing in this module that may not be adjusted to make
anything pass.

**Friction assumes maker on entry and taker on exit.** A stop must always exit as a
taker, so that is the worst realistic round trip, and sizing the hurdle against a maker
exit would price a cost the system will not always achieve. Both rates are added once.

**Nothing here is a constant.** No fee, no tier threshold, no spread. They arrive
through `state["exchange"]`, published by engine 1 from the live client. `hurdle_multiple`
is the single configured input, and it is a multiplier on measured friction rather than a
percentage of its own — `glossary.md`: "Hurdle — the minimum net edge a candidate must
show before it is allowed to trade. Derived from friction, never a constant."

**At tier 1 this gate is unreachable, by construction, and that is not a bug.** With
`hurdle_multiple: 1.5`, `net_edge > 1.5 x friction` rearranges to
`expected_move > 2.5 x friction`; tier 1 friction is around 1.25% round trip, so a
candidate needs an expected move above roughly 3.125% while the target barrier is 3.0%.
The system is designed to report honestly that no edge survives tier 1 fees at a fresh
account. Any pass test written against this engine therefore has to use a better tier,
````

*Verbatim from `src/acsoe/engines/cost/engine.py`, lines 100–125:*

```python
        try:
            inputs = self._read_inputs(state)
            hurdle_multiple = self._read_hurdle_multiple(context)
        except MissingInputError as missing:
            return self._blocked_on_missing_input(str(missing), state, started)

        friction = (
            inputs.maker_fee_pct + inputs.taker_fee_pct + inputs.spread_pct + inputs.slippage_pct
        )
        net_edge = inputs.expected_move_pct - friction
        hurdle = hurdle_multiple * friction

        # Invariant 5's third line, and the only comparison in this file. Strictly
        # greater than: a candidate that exactly equals the hurdle has not beaten it,
        # and "with margin to spare" is the project's stated posture.
        clears = net_edge > hurdle

        assessment = CostAssessment(
            pair=inputs.pair,
            expected_move_pct=inputs.expected_move_pct,
            friction_pct=friction,
            net_edge_pct=net_edge,
            hurdle_pct=hurdle,
            clears_hurdle=clears,
            reason_code=None if clears else self._reason_code(inputs),
        )
```

Friction composition as recorded on a real approval (pack 01 §C.9): tier 3 friction `0.006689770529027686723613674725` = maker 0.0022 + taker 0.0038 + bucket spread ($1M–$10M row, 5.52274 bps = 0.0005522…) + served slippage 0.0001374965… ; hurdle = 1.5 × friction = `0.01003465579354153…`; the cost bar on the expected move is therefore 2.5 × friction ≈ 1.67% in the most liquid bucket at tier 3 and ≈ 1.30% at tier 5 (findings line 748–749). Reference figures for a reader: tier 1 friction "≈ 1.25% round trip", bar 3.125% (`trading-invariants.md` line 179; `default.yaml` line 90); with the fetched schedule's 1.20% fees and no spread the bar is exactly 3.0% (findings §2, lines 313–318).

---

## B. Models and learning

### B.1 Engine 8, the predictor

- **Algorithm and library:** LightGBM multiclass classifier over the three barrier classes, `objective="multiclass", num_class=3` (`src/acsoe/research/training.py` lines 812–814; `CLASS_ORDER = ("target", "stop", "timeout")` line 108), `n_estimators = training.num_trees` (line 815). Hyperparameters from config (`default.yaml` lines 327–342): 400 trees, learning rate 0.05, 31 leaves, `min_data_in_leaf 200`, 4 threads, seed 20260908. Artefact serialised as `"lightgbm-multiclass-text"` (line 1832). Rows weighted by average uniqueness (`modelling/weights.py`; `training.py` lines 19–22).
- **Feature count and list:** 117 columns = 39 own features + 78 macro features (the same 39 for BTC and for ETH, prefixed `macro_btc_`/`macro_eth_`) (`tests/fixtures/walkforward_digest.json` `feature_names` len 117, first `bar_range_pct`, last `macro_eth_vol_regime_rank`; `src/acsoe/modelling/di.py` line 37: "78 of the 117 columns are BTC and ETH macro features"). `FEATURE_VERSION = "f1"`. The 39 own features (`features.py` `FEATURE_NAMES`, built by `_build_names`, lines 124–186):

| Feature | Definition (from `features.py` names and docstrings) |
|---|---|
| `bar_range_pct`, `bar_body_pct` | The decision bar's own (high−low)/close and |close−open|/close; no lookback, never NaN |
| `hour_sin`, `hour_cos`, `weekday_sin`, `weekday_cos` | Clock fields, circular encodings; identical across pairs on a bar |
| For each lookback n ∈ {4, 16, 48, 96} bars: `bars_in_lookback_n` | how many bars actually exist inside the last `n × 900 s` (a window of time, not rows; NaN for every feature of a window under 80% filled) |
| `log_return_n` | log(close_t / close_{t−n}) over the window |
| `realised_vol_n` | standard deviation of bar log returns in the window |
| `efficiency_ratio_n` | net move over path length (1.0 a straight line, 0.0 a round trip) |
| `range_atr_n` | average true range over the window relative to price |
| `volume_z_n`, `trades_z_n` | z-scores of this bar's volume and trade count against the window |
| `high_low_position_n` | where the close sits between the window's low and high |
| `vol_regime_rank` | rank of the 4-bar realised volatility inside the 96-bar window's own distribution (feeds engine 12) |

Constraints stated in the module docstring (lines 14–47): OHLCVT only (no bid, ask, depth or spread, so every feature reproduces in replay); a feature at bar t uses closed bars at or before t; a lookback is a window of time; no pair identity in any feature; names ordered and versioned into every manifest.

- **Training window and retrain cadence:** `backtest.training_window_days: 90`, past-only; `retrain_interval_days: 7` (`default.yaml` 207–208; ruling 1 of 2026-09-12, tracker lines 1585–1595). Fold 392: `train_start 2024-07-07`, `train_end = test_start 2024-10-05`, `test_end 2024-10-12`, 964,482 training rows (effective 101,038), 3,612 purged, 1,947 embargoed, 70,161 test rows (`data/derived/walkforward_digest_…json` fold 392).
- **Calibration:** one isotonic regression per class (`sklearn.isotonic.IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)`) fitted on the held-out last `prediction.calibration_days: 14` days of the training window, never the test window (`training.py` lines 772–787, 985–1010); applied identically live and offline through `modelling/calibration.py` (its docstring lines 1–22), stored as two arrays per class, no pickle; probabilities floored at 1e-9 and renormalised to sum to one.
- **What it publishes:** `p_target`, `p_stop`, `p_timeout`, `expected_move_pct` (exact decimal string), `is_buy` (only when scored), `di`, `di_threshold`, `shap`, `model_run_id` (`src/acsoe/engines/prediction/contracts.py` lines 148–159; pack 01 §C.9 shows a real payload).
- **The expected move formula, verbatim** (`src/acsoe/modelling/expected_move.py` lines 1–34):

*Verbatim from `src/acsoe/modelling/expected_move.py`, lines 1–34:*

```python
"""The expected move a BUY call is decided on, computed once for both sides.

The predictor does not predict price. It predicts which of three barriers price touches
first, and the expected move is what turns those three probabilities back into a number
the cost gate can price against friction:

.. code-block:: text

    expected_move_pct = p_target * target_pct
                      - p_stop   * stop_pct
                      + p_timeout * mean_timeout_return

``mean_timeout_return`` is the mean ``return_pct`` of the **timeout** rows in the fold's
own training window, and it is a measured number rather than zero. A timeout is not a
flat outcome: the position is closed at whatever the price is twelve hours later, and
across this dataset that has a sign. Assuming zero would bias every expected move in the
same direction, which is the kind of error that survives because it is small and
consistent.

A **BUY call** is ``expected_move_pct > 0``, before friction. Nothing else: no threshold
on a probability, no cut-off anybody tuned. Engine 10 `cost` applies friction afterwards
and is the thing that decides whether the trade pays for itself — invariant 5 — and this
number is deliberately the naive one so that the gate is the only place selectivity
lives.

The same function serves `research/training.py` and engine 8 `prediction`, because a
BUY call in the backtest and a BUY call live have to be the same event. If the trainer
computed this one way and the engine another, every skeptic training row would be
selected by a rule the live loop does not use.

**Floats in, float out, and the string conversion happens once at the caller.** The
probabilities are model output and are floats by nature, so the product is a float
whatever the barriers are stored as; wrapping the result in ``Decimal`` afterwards would
dress up a float as an exact number. Engine 8 formats it with ``repr`` at the ``state``
```

`mean_timeout_return` per fold lies between 0.17% and 0.54% across the 405 manifests (findings line 320).

### B.2 Does the live daemon retrain?

**No. It never retrains.** Evidence:

- grep `retrain` over `src/acsoe/engines`, `cli`, `core`, `platform`: the only hits are a config field name (`platform/config.py` line 440 `retrain_interval_days`), two comments about manifests, and an error message in `engines/prediction/engine.py` line 521 ("Retrain at the percentile you want, or point …"). No engine or CLI path trains.
- Engines 8, 13 and 15 load the run named in `models.prediction_run_id`, `models.anomaly_run_id`, `models.skeptic_run_id` and block when it is absent (`context/architecture-context.md` lines 175–176). Those keys are **absent from the committed config** by design (`default.yaml` lines 237–246), so a fresh clone's daemon blocks on every bar tick with `prediction_unavailable` etc.
- `src/acsoe/engines/skeptic/engine.py` lines 62–67 ("## It never learns"): "Nothing here trains, adapts, or reads the store for outcomes. The model is the artefact's and the threshold is the artefact's manifest plus the operator's config. Live learning is out of scope for this phase".
- Training is `python -m acsoe.research.training` (offline, `research/training.py` `main`, line 100 `__all__`), and for Phase 7 the per-fold artefacts were assembled offline (`research/artefact_assembly.py`, `research/skeptic_cap.py`) into `models/train-20260913T205245-067b2b9d-f{fold}-p7/`; the **replay** switches the three `models.*_run_id` keys at each fold boundary (`cli/research.py` `fold_config`, lines 646–660; 10 `fold_switch` events in each runrecord). That is how "the backtest retrains at the same cadence the live system does" (success criterion 3, `project-overview.md` line 40) is realised: the *evaluation* uses weekly-retrained models; the live daemon would have to be pointed at a new run id by the operator. The report must not say the live system retrains.

### B.3 Engine 15, the skeptic

- **Training rows and why only those:** `research/training.py` `_fit_skeptic` docstring, lines 1280–1292: "Meta-labelling: how likely is this BUY call to be wrong. … The label is `wrong = label != "target"` and the inputs are the feature vector plus the predictor's own three probabilities and its expected move. **It can only veto.**" Rows are the predictor's **out-of-sample BUY calls from earlier folds only**, purged and embargoed against this fold's test window (lines 1284–1287). Only BUY calls, because the skeptic grades the calls the system would act on (`glossary.md` line 45; `trading-invariants.md` line 163). Algorithm: LightGBM `objective="binary"`, `n_estimators = training.num_trees` (`training.py` lines 1335–1337).
- **The cap and how it is applied:** `training.skeptic_cap_folds: 13` (`default.yaml` lines 343–346): fold k's skeptic trains only on folds k−13 … k−1. "The cap is a filter on the out-of-sample calls **in front of** `_skeptic_training_rows`, and nothing in that selection changes" (`training.py` 1284–1286). The Phase 7 window's skeptics were staged with `--cap 13` by `research/skeptic_cap.py` through the trainer's own `_fit_skeptic`, replicated first against an early fold's saved uncapped skeptic ("same training identity, same row count, same probability on every one of that fold's BUY calls", `skeptic_cap.py` lines 18–24). The Phase 5 walk-forward trained every skeptic uncapped, which is why it died at fold 405 (8,946,942 rows in the matrix; pack 03 §B.1).
- **Veto threshold:** `skeptic.veto_threshold: 0.50` (`default.yaml` 312–317, ruled 2026-09-14 from the sweep, PROVISIONAL). A NaN or infinite `p_wrong` blocks with `skeptic_unavailable` (engine docstring lines 47–51); an absent `is_buy` blocks; an explicit `is_buy: false` is `OK, vetoed: false`.
- **What it publishes:** `p_wrong`, `threshold`, `vetoed`, `model_run_id` — "there is no `approved`, no confidence and no margin a downstream engine could widen a threshold with" (engine docstring lines 8–12). Real values on the approved STORJ tick: `p_wrong 0.2662825593750926`, `threshold 0.5`, `vetoed false` (pack 01 §C.9).
- **Measured selection:** uncapped, all 405 folds, at 0.50: survivors 154,979 (1.73%) hit the target at 0.5309 against a no-skill band 0.255–0.260 and 0.4731 for the predictor's own top-N by `p_target` (44% overlap) — `docs/dataset/skeptic-veto-sweep-2026-09-14.md`, `skeptic-vs-ptarget-2026-09-14.md`, findings §5b. **Capped, in the simulation window** (folds 379–404, 1,237,399 BUY calls): passes 8.38% at 0.3935 target rate against 0.3953 for top-N by `p_target` — "no detectable difference" (F4, findings lines 732–741). The run's own skeptic never refused anything because the cost gate stopped every refused tick first (pack 03 §B.11).

### B.4 The Dissimilarity Index

*Verbatim from `src/acsoe/modelling/di.py`, lines 1–52:*

```python
"""The Dissimilarity Index: how far a live feature vector sits from what was trained on.

A model asked to predict on market conditions unlike anything in its training set does
not report uncertainty; it extrapolates, confidently. The DI is the refusal: measure how
far this candidate's scaled feature vector is from the reference set, and when it is
further than almost everything the model was fitted on, **do not predict**. Engine 8
turns that into a ``BLOCK`` with reason code ``di_refused`` and publishes no
``expected_move_pct``, so engine 10 fails closed on the absent key.

The reading is fixed by the operator, 2026-09-12, and is not this module's to reinterpret:

* the reference set is the **predictor's training rows for the fold**, restricted per
  pair to the last ``prediction.di_window_days`` of the training window;
* the statistic is the **mean distance to the k nearest** reference rows, Euclidean on
  MinMax-scaled features;
* the threshold is that statistic's **leave-one-out** distribution over the reference
  set, at ``prediction.di_percentile``, where "one" is **every reference row within the
  exclusion span of the row being scored, across all pairs** (ruling of 2026-09-15,
  amending ruling 6);
* it is refitted at every weekly retrain.

**Never the skeptic's BUY subset.** Fitted on BUY rows the DI learns that "normal" means
a BUY-shaped setup and then vetoes every ordinary market state. Nothing goes red: the
veto rate is high, the few trades that survive look clean, and the leaderboard flatters
the model. That is why :func:`fit` records the **identity** of the rows it saw and why
the criterion checks identity rather than a row count — two sets of the same size are
indistinguishable by count, and on a fold where most calls are BUY they usually are.

Leave-one-out matters for the same reason a fitted threshold usually does not: scoring a
reference row against a set that contains it gives a nearest neighbour at distance zero,
which drags every statistic down and puts the threshold below where the live scores will
land. The veto then almost never fires, which looks exactly like a well-behaved model.

**Leaving out the row alone is not enough, and the ruling of 2026-09-15 says so.** 78 of
the 117 columns are BTC and ETH macro features, identical for every pair on the same bar,
and the calendar columns are too; consecutive bars of one pair carry nearly identical
rolling features. So a reference row's nearest neighbours were its own moment's rows —
the same bar on other pairs, the adjacent bars on its own — and the threshold measured
**time proximity**, not distributional distance. A live candidate has no such neighbours:
it sits at least the embargo after the reference window. Measured over 405 folds, the
row-only threshold at the 0.95 percentile refused 94.7% of out-of-sample rows, and
excluding every pair within 48 bars put the reference distribution on the test one
(``docs/dataset/di-anomaly-distributions-2026-09-14.md``). So :func:`fit` excludes every
reference row whose ``decision_ts`` is within ``exclusion_s`` of the scored row's,
inclusive, and the caller passes the same span a live candidate is guaranteed:
``backtest.embargo_bars x timeframes.decision_bar_s``. **A DI fitted without the
exclusion is the defect, not a variant**, which is why :func:`load` refuses one.

Pure arithmetic. No clock, no config, no client; every input is an argument.
"""

from __future__ import annotations
```

Parameters: `prediction.di_window_days 30`, `di_neighbours 10`, `di_reference_rows 200000`, `di_percentile 0.99` (`default.yaml` 280–299). With the 48-bar all-pairs exclusion the DI refuses 3.31% of complete out-of-sample rows at 0.99 (against 74.9% before the exclusion, and 94.7% at 0.95 row-only) — `docs/dataset/di-exclusion-refit-2026-09-15.json` (405 folds refitted, largest difference from direct numpy 9.1e-15) and tracker Finding 2 (lines 1315–1341). Engine 8 blocks with `di_refused` and publishes no expected move, so engine 10 fails closed on the absent key (`engine-contracts.md` line 249). Real values: `di 1.539 < di_threshold 2.277` on the approved STORJ tick.

### B.5 Engine 13, anomaly

- **Algorithm:** scikit-learn `IsolationForest` (`research/training.py` lines 1546–1566), fitted per fold on the training window's rows over the 21 **market-quality features** only (`features.py` `MARKET_QUALITY_FEATURES`: `bar_range_pct` and, for each lookback, `bars_in_lookback`, `realised_vol`, `range_atr`, `volume_z`, `trades_z`) — "velocity, volume, trade count, range and window fill … **No spread**" (`features.py` lines 188–197). `n_estimators` is sklearn's default and deliberately not a config key (`training.py` line 1566 comment); the subsample size is anchored to IsolationForest's own default (line 1459). Serialised with `joblib` (the one binary artefact; `pyproject.toml` comment; manifest sha256 guards a swapped file).
- **Threshold:** the `anomaly.threshold_percentile: 0.99` quantile of the fold's own training scores, computed at training time and stored in the artefact; larger is more anomalous; above the threshold blocks with `market_anomalous` (`engines/anomaly/engine.py` docstring lines 22–34; `default.yaml` 301–309: "1.24% blocked out of sample against 1% nominal, stable by year (0.9% to 1.8%) … what it blocks is the volatile tail (stop rate 0.67 against 0.50)"). It cannot read `state["prediction"]` by construction (contracts name only `scout` and `feature`). Real values: `score 0.3969 < threshold 0.6474` (pack 01 §C.9).

### B.6 Engine 12, regime

*Verbatim from `src/acsoe/engines/regime/engine.py`, lines 1–28:*

```python
"""Engine 12 `regime` — what kind of market the candidate is in.

Three labels: `trending`, `choppy`, `high_volatility`. Rule-based in Phase 5; the HMM in
the stack table is an optional upgrade and spec 66 puts it explicitly out of scope.

**The volatility rule is percentile-relative to the pair's own trailing window, and it
could not be otherwise here.** An absolute volatility cutoff would classify a $0.30 pair
and a $60,000 one by the same number, and would mean something different in 2018 than in
2024. So the comparison is against `vol_regime_rank` — where this bar's short-window
realised volatility sits inside the long window's own distribution, measured in
`modelling/features.py` — and the configured `regime.high_vol_percentile` is a position
in that distribution rather than a quantity of percent. Engine 12 is handed **one feature
row** and therefore has no distribution of its own, which is the structural reason an
absolute threshold cannot creep back in.

**The trend rule is an absolute cutoff and that is legitimate**, because the efficiency
ratio is already scale-free: net move over path length is 1.0 for a straight line and 0.0
for a round trip that went nowhere, on any pair at any price.

**It is not a gate and it never blocks.** No regime is a reason to refuse a trade; that
is the router's business in Phase 6. An unclassifiable candidate gets `label: null` with
a reason, never a default label — calling an unknown market `choppy` would be a judgement
nobody made, and Phase 6's router would weight a model by it.

**It does not read the DI.** `di_regime_shift` is published as `null`; the reasoning is in
`contracts.py` and the README, and the short of it is that engine 12 runs before engine 8
and nothing persists the previous bar's DI. Reading the store to find one would be an
engine inventing its own persistence for a cross-chain key.
```

Config: `regime.high_vol_percentile 0.9`, `regime.trend_efficiency 0.3` (`default.yaml` 319–325). States: `trending`, `choppy`, `high_volatility`, or `null` with a reason. **Downstream use:** none that decides anything — engine 14 copies the label as provenance (`adaptive_router/README.md` "What it reads"), the console shows it, and `di_regime_shift` is a declared placeholder published as `null` (README line 70). The Locked Decision "DI threshold crossings also feed the regime engine" (tracker line 1551) is therefore **not implemented**; engine 12 runs before engine 8 and nothing persists the previous bar's DI (engine docstring lines 24–28). Every stored snapshot in the runs shows `"regime": {"label": "trending"}` on the approved and refused STORJ ticks.

### B.7 Engine 14, adaptive router

*Verbatim from `src/acsoe/engines/adaptive_router/README.md`, lines 1–62:*

````markdown
# Engine 14 — `adaptive_router`

A weight per trained model version, and the basis for each. Opportunity chain, after
engine 11 `risk` and before engine 15 `skeptic`. **Not a gate.** Spec 97.

## It is inert today, and that is stated rather than discovered

The walk-forward trains one predictor per fold and the leaderboard holds one model family,
so on the real table every model version has exactly one row and the published weight set
has one member at 1.0. Nothing downstream reads this payload to decide anything: engine 15
does not read it at all, engine 16 `decision` copies `active_model_run_id` into the order
intent as provenance and never judges it, and engine 18 places what engine 16 composed.

So **in the fixed registry order nothing this engine publishes can change whether the tick
trades.** That is not an accident of the current wiring — it is what invariant 4 requires
of anything sitting after engine 10 `cost`. A weight that raised willingness to trade would
be a model output overriding a gate; one that lowered it would be a veto, and only a gate
may issue one.

The arithmetic is still built as though it mattered, because it is what Phase 7's promotion
gate will read. A weighting rule that is wrong while it is inert is wrong when it stops
being inert, with no event in between to prompt anyone to check it.

## What it reads

| Key | Owner | Used for |
|---|---|---|
| the leaderboard, through the store | 20 `tournament` (C), via B's client | every row it weights |
| `state["prediction"]["model_run_id"]` | 8 `prediction` (C) | `active_model_run_id`, echoed not chosen |
| `state["prediction"]["di"]`, `["di_threshold"]` | 8 `prediction` (C) | `di_margin`, provenance only |
| `state["regime"]["label"]` | 12 `regime` (C) | `regime`, provenance only |

Every one of those names is declared in `contracts.py` and nowhere else. Contract rule 3.

## What it publishes

`state["adaptive_router"]` carries `active_model_run_id`, `basis`, `regime`, `di_margin`
and `reason_code`, plus **`weights` when and only when there are weights**. Omitted rather
than nulled, following `expected_move_pct` and `is_buy`: a consumer reading the key on a
tick where nothing could be weighted should get a `KeyError` rather than an empty mapping
it has to interpret. An empty mapping and "every weight is zero" are different facts, and
the second is published as an actual mapping of zeros.

Every value here is a **float**, because these are statistics. Nothing in this engine is
money and nothing in it is a `Decimal`.

There is deliberately **no `pair` and no bar timestamp.** Engine 16's coherence walk checks
any payload carrying either against this tick's candidate, and this payload is about model
versions rather than about the candidate — so a `pair` here would be a field engine 16
checks and nothing produces from the candidate.

## The weighting rule

Approved by the lead, 2026-09-16.

```
skill(fold)    = max(0, 1 - brier / base_rate_brier)
skill(version) = mean over that version's folds
weight         = skill / sum(skill), or all zero with a reason code
```

**Why skill against the base rate, and not inverse Brier.** Brier is bounded and always
````

**Has it ever weighted anything real? No.** Tracker lines 66–69: "**Engine 14 `adaptive_router` has never weighted anything real.** On the first paper trade it returned `leaderboard_empty`: the drive's database held no leaderboard rows. … **Phase 7's attribution must not read a router verdict as a judgement.**" The trial ledger confirms engine 20 has written no persisted leaderboard row: "the only database on disk (data/db/acsoe.sqlite) holds the six fabricated Phase 0 seed rows" (`docs/dataset/phase-7-trial-ledger.md`, "Leaderboard" judgement). In the runs it publishes provenance only (`active_model_run_id`, `di_margin`, `regime`); the approval snapshot in pack 01 §C.9 carries no `weights` field. The leaderboard fixture that exercises its weighting rule is fabricated and says so (`tests/fixtures/README.md`, "`leaderboard_sample.json` is **fabricated, and it is the one file here that is.**").

### B.8 Engine 20, tournament

*Verbatim from `src/acsoe/engines/tournament/README.md`, lines 1–75:*

```markdown
# Engine 20 — `tournament`

**Number:** 20 · **Chain:** offline (`OFFLINE_CHAIN`, through `acsoe research`) ·
**Gate:** no

Scores every trained model version against realised outcomes and writes one `leaderboard` row
per version, so Phase 6's adaptive router has something to weight by and Phase 7's promotion
gate has something to judge.

**In Phase 5 the realised outcomes are the labels.** From Phase 6 they will also be trades.
That is why `n_trades` counts BUY *calls* rather than fills: nothing has been filled, and a
column reporting zero would make every model look untraded rather than untested.

## What it reads

Two files and one table, and nothing else.

| Source | Used for |
|---|---|
| the training digest, from `acsoe research --digest` | the run id, `created_at`, each fold's run id, and the numbers every fold is cross-checked against |
| `oos_<run_id>.parquet` beside it | every number on a row: `n_trades`, `win_rate`, `net_pnl` and `brier` |
| `leaderboard`, through `StoreClient` | whether this fold has already been written |

It reads **no archive** — `architecture-context.md` — and has no `state` inputs at all, which
is why its contracts module names none.

The out-of-sample path is derived from the digest's own `run_id` rather than configured. The
two files are one run's output, and a caller that could point at a mismatched pair would
produce a leaderboard scoring one model against another model's calls.

## What it writes

One `LeaderboardRow` per fold:

| Column | Value |
|---|---|
| `model_id` | `"predictor"` |
| `model_version` | **the fold's own artefact run id**, `<run_id>-f<fold>` as the trainer wrote it |
| `training_run_id` | the parent training run id, which groups a walk-forward's folds |
| `trained_at` | the digest's `created_at` |
| `updated_at` | `context.now`, when the row was written |
| `fold` | the fold index |
| `n_trades` | BUY calls in that fold's test window |
| `win_rate` | target rate among them |
| `brier` | recomputed from the fold's out-of-sample `p_target` and labels |
| `net_pnl` | the sum of `return_pct` over BUY calls, as an exact decimal string |
| `reporting_currency` | `trading.base_reporting_currency` |
| `promoted` | always `false` |
| `sharpe`, `deflated_sharpe`, `alpha`, `beta` | always `null` |

**Every number comes from the out-of-sample rows, selected by `fold_index`.** The file carries
the **calibrated** `p_target` the trainer scored, so the Brier is recomputable and is
recomputed; a row whose trade columns came from one file and whose headline metric came from
another would have nothing to say when the two stopped describing the same rows. (An earlier
version copied the Brier from the digest on the belief that only the trainer saw calibrated
probabilities. It did not; the out-of-sample file does.)

**The digest is then a cross-check, and a disagreement writes nothing.** Per fold, the digest's
row count, BUY count, Brier and base-rate Brier must match what the rows give; the folds the
out-of-sample file carries must be the folds the digest lists; and a fold the digest calls
empty must have no rows. Every fold is checked before any row is written, so a disagreement on
the last fold leaves the table as it was. A wrong boundary upstream — a row moved into the
neighbouring fold — shows up here as exactly this kind of disagreement.

**`updated_at` is `context.now`, not `trained_at`.** `leaderboard` is one of the tables the
console's poll watermark reads, and the watermark moves only for rows stamped from the injected
clock. A row stamped with its training time lands under the current watermark, and an open
console would never push it.

`net_pnl` crosses as `Decimal(repr(value))` — the shortest decimal that round-trips, which is
the number that was computed, rather than the double's full binary expansion. The same
crossing `research/labelling.py` makes.

## What it will not do
```

The promotion gate half (README "## The promotion gate, spec 139", and `engines/tournament/engine.py` lines 274–310): given `promote_run_id` and `ledger_path`, it reads the run's closed trades through the store, computes `net_return = realised_pnl / (qty × entry_price)` per trade, calls `modelling.promotion.promotion_verdict(holds, trials)` with the ledger's `trial_count` (checked against its own rows, `_ledger_trial_count` line 640), and writes one leaderboard row with `promoted` and a reason code (`promotion_too_few_trades` / `promotion_lower_bound_not_above_zero` / `promotion_no_ledger` / `promotion_bad_trade`), the DSR beside it. **It has not yet been run against either Phase 7 database** (findings Part II line 993: "nothing has been computed from the runs yet").

### B.9 Walk-forward

*Verbatim from `src/acsoe/research/walkforward.py`, lines 1–70:*

```python
"""The purged, embargoed walk-forward splitter. Spec 53.

Invariant 10: *walk-forward folds are purged and embargoed; overlapping label windows
must not straddle a train/test boundary.*

## Why this is the most dangerous module in the project

A splitter that forgets to purge produces a model that looks excellent and is worthless,
and **nothing fails to say so**. There is no crash, no red test and no operator-visible
symptom. A backtest run on leaked folds reports a Sharpe the live system will never see,
the Phase 7 promotion gate passes it, and the first honest number arrives from a real
account.

The defect is invisible to every end-to-end check, and the reason is worth stating
exactly: **the fold *indices* do not overlap whether or not the purge ran.** The leak is
in the **label windows**. A decision bar comfortably inside the training period can have
a label built entirely from bars inside the test period, and only a test that constructs
such a row on purpose can see it.

## Purge

Every label carries ``label_window_end_ts`` — the instant its outcome became known.
`research/labelling.py` emits it: the touch for a barrier that was hit, the horizon for
a timeout. **A training row whose window ends at or after the start of the test window is
dropped.**

Purging on ``decision_ts`` instead is the most plausible wrong implementation, and it
passes any test that does not deliberately place a decision bar early and its label
window late.

## Embargo

The last ``backtest.embargo_bars`` bars before the test window are dropped from training
even when their label windows closed before the test window opened. This exists because
serial correlation carries information across the boundary even where no label window
literally straddles it, so purging alone is not enough. It is a gap between the end of
training and the start of testing, and it is counted separately from the purge so that
the day one mechanism stops working the other's number cannot cover for it.

**There is no default for ``backtest.embargo_bars``.** It is read from config and a
missing key raises. An embargo that quietly defaulted to zero is precisely the defect
this module exists to prevent, and it would be indistinguishable from a working one in
every output.

## The training set is the past only. Operator ruling 1, 2026-09-12.

A fold trains on the ``backtest.training_window_days`` before its test window and on
**nothing after it**. Every row whose decision bar post-dates the test window is counted
in ``after_test_count`` and never trains in that fold.

What was built first trained on a window of the same length on both sides of the test
window, which is purged cross-validation in the López de Prado sense laid over rolling
test windows. That is legitimate for hyperparameter selection, but it lets a model see
data from after the period it is scored on, so it reports a number better than the same
model would achieve live and nothing says so. The project's goal is a system that trades,
so the validation must answer "would this have worked if I had been trading it", and
only a past-only fold answers that. The phase criterion
``walkforward_trains_on_the_past_only`` proves it on every fold rather than trusting the
arithmetic here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

__all__ = [
    "DECISION_TS_FIELD",
    "KEY_EMBARGO_BARS",
```

Facts from the digest (`tests/fixtures/walkforward_digest.json`; per-fold CSV in pack 04): 457 folds planned, 405 trained; fold 0's test week begins **2017-04-01** (train 2017-01-01 → 2017-04-01, 3,771 test rows, effective 576); test window = 7 days; training window = 90 days before `test_start`, `train_end = test_start`; purge on `label_window_end_ts` (rows whose label window ends at or after the test start are dropped: fold 392 purged 3,612), embargo `backtest.embargo_bars: 48` bars before the test window (fold 392 embargoed 1,947); rows after the test window counted in `after_test_count` and never trained on (fold 392: 5,489,739). The pre-2017 exclusion is `dataset.decision_start_date: "2017-01-01"` applied by `research/labelling.py` before any fold is built (`default.yaml` 53–61; tracker ruling 2, lines 1596–1608: 92,791 labelled rows removed, 0.45%, across the six pairs whose history predates 2017). Phase 7 uses folds 392–404: test weeks 2024-10-05 … 2024-12-28, the last ending 2025-01-04 00:00Z.

### B.10 Labels

Rules as written in `src/acsoe/research/labelling.py` (module docstring) and the implementation of the both-barriers rule:

*Verbatim from `src/acsoe/research/labelling.py`, lines 1–48:*

```python
"""Triple-barrier labelling. Spec 52.

Turns a series of closed 15-minute candles into labels: ``target`` at
``barriers.target_pct``, ``stop`` at ``barriers.stop_pct``, ``timeout`` at
``barriers.timeout_bars``. **Every one of those three values comes from
``config/default.yaml`` and none of them is written into this module.**

## Research only. Never the live path.

A label is built from bars *after* the decision bar, so it is future information by
construction. Invariant 10 confines it to the training pipeline: nothing in
``acsoe.engines``, ``acsoe.core``, ``acsoe.clients`` or ``acsoe.cli`` may import this
module, and this module imports nothing from them.
``tests/research/test_labelling.py`` asserts both directions.

## Two lead rulings, because the obvious reading is silently wrong

**1. A bar that touches both barriers is labelled ``stop``.** An OHLC candle whose high
reaches the target and whose low reaches the stop does not say which came first, and the
archive carries no intra-bar sequence to recover it from. Labelling it ``target``
invents the favourable ordering on exactly the bars where the market was most violent,
and a model trained on that learns an edge that does not exist. The pessimistic reading
is the only one that cannot flatter the strategy. Every such row carries ``ambiguous``,
and :class:`LabelledSeries` reports the count — a slice where that number is large is a
slice whose labels are mostly an assumption.

**2. The timeout barrier is a time, not a count of rows.** The archives contain only
intervals in which trades occurred, so 48 *existing rows* can span days across a quiet
period. The horizon is ``decision_ts + timeout_bars * interval_s``; the walk visits
whatever candles exist inside that window and stops at its end. Counting rows silently
stretches a 12-hour horizon into a multi-day one over precisely the gaps
``research/historical.py`` refuses to interpolate away.

## Three further rules, each of which is a label that would otherwise be fabricated

**A decision bar whose window runs past the end of the series is not labelled at all.**
It is excluded, never labelled ``timeout``. Labelling it records an outcome that has not
happened yet, which is invariant 10 with a different face.

**The decision bar itself is never inspected for a touch.** Its own high and low are
inside the bar the decision was made on; reading them is look-ahead within one bar.

**A window containing no candles at all is excluded**, and this one is a judgement
rather than a rule handed down: a ``timeout`` label needs a terminal price to compute a
return from, and across a multi-day hole there is none. Excluding is the reading that
invents nothing. The count is reported so the decision is visible rather than silent.

## One dataset rule, which is about tradability and not about data
```

*Verbatim from `src/acsoe/research/labelling.py`, lines 325–385:*

```python
    window_end = settings.timeout_at(decision_ts, interval_s)

    # Excluded, never labelled `timeout`: the outcome has not happened yet.
    if last_ts < window_end:
        return None

    # The scan starts at index + 1. The decision bar's own high and low are inside the
    # bar the decision was made on, and reading them is look-ahead within one bar.
    scan_from = index + 1
    scan_to = bisect.bisect_right(stamps, window_end)
    in_window = max(0, scan_to - scan_from)
    if in_window == 0:
        return None

    for position in range(scan_from, scan_to):
        row = rows[position]
        high = Decimal(str(row["high"]))
        low = Decimal(str(row["low"]))
        hit_target = high >= target_price
        hit_stop = low <= stop_price
        if not (hit_target or hit_stop):
            continue
        # Ruling 1. Both barriers inside one bar carries no ordering, and the
        # pessimistic reading is the only one that cannot flatter the strategy.
        ambiguous = hit_target and hit_stop
        label = LABEL_STOP if (hit_stop or ambiguous) else LABEL_TARGET
        touch_price = stop_price if label == LABEL_STOP else target_price
        touch_ts = int(row["ts"])
        return Label(
            pair=pair,
            decision_ts=decision_ts,
            close=close,
            target_price=target_price,
            stop_price=stop_price,
            label=label,
            touch_ts=touch_ts,
            # Elapsed *bars*, computed from the timestamps, so a gap inside the window
            # does not compress the horizon into however many rows happened to exist.
            bars_elapsed=(touch_ts - decision_ts) // interval_s,
            touch_price=touch_price,
            label_window_end_ts=touch_ts,
            return_pct=float((touch_price - close) / close),
            ambiguous=ambiguous,
            candles_in_window=in_window,
        )

    terminal = rows[scan_to - 1]
    terminal_ts = int(terminal["ts"])
    terminal_close = Decimal(str(terminal["close"]))
    return Label(
        pair=pair,
        decision_ts=decision_ts,
        close=close,
        target_price=target_price,
        stop_price=stop_price,
        label=LABEL_TIMEOUT,
        touch_ts=terminal_ts,
        bars_elapsed=(terminal_ts - decision_ts) // interval_s,
        touch_price=terminal_close,
        # The horizon, not the last candle. They differ whenever the window ends inside
        # a gap, and the splitter must purge on the later of the two.
```

The authority for the rule is `context/architecture-context.md` lines 115–122: "A candle whose high reaches the target and whose low reaches the stop does not say which came first … **The label is `stop`.** Ruled by the lead 2026-09-11, spec 52, and flagged to the operator as overturnable." Count decided this way: **76,522 of 20,331,237 labelled bars (0.376%)** (`docs/dataset/labelled-dataset-2026-09-12.json` `total.ambiguous`). The live engine 21 applies the same tie-break per tick (B.13).

### B.11 SHAP

- **Where TreeSHAP runs:** in engine 8 on the live loop path, `src/acsoe/engines/prediction/engine.py` lines 328–344: `import shap` lazily; `self._explainer = shap.TreeExplainer(artefact.booster)`; `values = self._explainer.shap_values(scaled)`; the target class's contributions are published under `data["shap"]`; a failure to explain is not a failure to predict (line 334). The explainer is dropped when the run id changes (lines 298–301).
- **Writer:** engine 19, `src/acsoe/engines/memory/engine.py` `_write_shap` (lines 558–594) calls `StoreClient.write_shap` (`src/acsoe/clients/store/client.py` lines 1349–1420): one Parquet file per decision at `shap/<run_id>/<cycle_id>/<pair>.parquet` under `data/derived/`, **write-once** (a second writer of a path is refused), refusing a blank pair, an empty or non-finite contribution. The relative path is the `shap_ref` a `rejections` row carries (client comment lines 1332–1335).
- **Does a rejection row carry attribution? Yes, when engine 8 scored.** `rejections.shap_ref TEXT` (migration 0001 line 306); in the tier 3 database all 6,035 `net_edge_below_hurdle` rows have a non-null `shap_ref` (query `sum(shap_ref is not null)` = 6,035 of 6,035), e.g. `shap/replay-phase7-t3-expected_move-20241005T001500Z/1575/STORJ%2FUSD.parquet`. The `approvals` table has **no** `shap_ref` column (migration 0006 lines 61–76): the approving tick's SHAP is written to the same Parquet path keyed by `(run_id, cycle_id, pair)` and is reachable by that key, but no approval row stores the reference (`memory/engine.py` line 802 attaches `shap_ref` to the rejection row only). That is the first-refusing-gate asymmetry the report should state: a refusal names its refuser and its SHAP path; an approval names every verdict but not a SHAP path.
- **The rejections schema, verbatim** (migration 0001 lines 280–316):

*Verbatim from `db/migrations/0001_initial.sql`, lines 280–316:*

```sql
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
```

### B.12 Engine 19, memory: approval and rejection rows

After spec 145 (`feature-specs/145-per-gate-verdict-snapshot.md`, quoted in pack 03 context), an **approval row** carries the placing tick's economics (`expected_move_pct`, `friction_pct`, `net_edge_pct`, `hurdle_pct`), the three model run ids, and `details` — every opportunity-chain engine's verdict fields (`VERDICT_FIELDS`, spec 145 step 2). A **rejection row** carries the same economics, `rejected_by`, `reason_code`, the operator sentence `reason`, `shap_ref`, and `details` with `"refused_by": <engine>` and only the engines that ran. The asymmetry: a rejection is keyed by the **first refusing gate** and says nothing about gates after it (stop-at-first-block, `orchestrator.py` line 503), so "how close did the skeptic come" is answerable only on ticks that reached the skeptic; an approval lists all of them.

**One real approval row** (tier 3, `approvals` primary key 1902893928), as JSON (the `details` value is the stored canonical JSON, pretty-printed here; every number is as stored):

```json
{
  "userref": 1902893928,
  "run_id": "replay-phase7-t3-expected_move-20241005T001500Z",
  "cycle_id": 1458,
  "ts": 1729398600000000,
  "pair": "STORJ/USD",
  "expected_move_pct": "0.01872379704121122",
  "friction_pct": "0.006689770529027686723613674725",
  "net_edge_pct": "0.01203402651218353327638632528",
  "hurdle_pct": "0.01003465579354153008542051209",
  "prediction_run_id": "train-20260913T205245-067b2b9d-f394-p7",
  "anomaly_run_id": "train-20260913T205245-067b2b9d-f394-p7",
  "skeptic_run_id": "train-20260913T205245-067b2b9d-f394-p7",
  "details": {
    "details_version": 1,
    "engines": {
      "adaptive_router": {"active_model_run_id": "train-20260913T205245-067b2b9d-f394-p7", "di_margin": 0.7374784529838772, "regime": "trending"},
      "anomaly": {"anomalous": false, "model_run_id": "train-20260913T205245-067b2b9d-f394-p7", "score": 0.39686900172854206, "threshold": 0.6474051905957353},
      "cost": {"clears_hurdle": true, "expected_move_pct": "0.01872379704121122", "friction_pct": "0.006689770529027686723613674725", "hurdle_pct": "0.01003465579354153008542051209", "net_edge_pct": "0.01203402651218353327638632528"},
      "decision": {"checked": ["scout", "prediction", "order_book", "cost", "risk", "adaptive_router", "skeptic"], "coherent": true},
      "order_book": {"basis_notional": "5000.00", "best_bid": "0.5642341510385699999717805", "depth": 10, "estimated_slippage_pct": "0.0001374965290276866236136747246", "fill_price": "0.5641565708012433131130910639", "levels_consumed": 5},
      "prediction": {"di": 1.5391261576207993, "di_threshold": 2.2766046106046764, "expected_move_pct": "0.01872379704121122", "is_buy": true, "model_run_id": "train-20260913T205245-067b2b9d-f394-p7", "p_stop": 0.24405431012065293, "p_target": 0.7443552828189702, "p_timeout": 0.01159040706037683},
      "regime": {"label": "trending"},
      "risk": {"approved": true, "notional": "3333.333333332467721776455957", "qty": "5904.45105471", "risk_amount": "50.0000"},
      "scout": {"pair": "STORJ/USD", "rank_descending": true, "rank_feature": "expected_move", "rank_run_ids": {"anomaly": "train-20260913T205245-067b2b9d-f394-p7", "prediction": "train-20260913T205245-067b2b9d-f394-p7"}, "rank_skipped": {"anomaly_inputs_incomplete": 151}, "ranked": [{"expected_move_pct": "0.01872379704121122", "pair": "STORJ/USD"}, {"expected_move_pct": "0.005784416733650414", "pair": "DOGE/USD"}, {"expected_move_pct": "0.005415237289566027", "pair": "ETH/USD"}, {"expected_move_pct": "0.004654988236116681", "pair": "AUD/USD"}, {"expected_move_pct": "0.004654988236116681", "pair": "BTC/USD"}, {"expected_move_pct": "0.004654988236116681", "pair": "EUR/USD"}, {"expected_move_pct": "0.004654988236116681", "pair": "GBP/USD"}, {"expected_move_pct": "0.004654988236116681", "pair": "USDC/USD"}, {"expected_move_pct": "0.004654988236116681", "pair": "USDT/USD"}, {"expected_move_pct": "0.0044255683370391435", "pair": "TRX/USD"}, {"expected_move_pct": "0.0032444820423100573", "pair": "SC/USD"}, {"expected_move_pct": "0.0032440973203785896", "pair": "AXS/USD"}, {"expected_move_pct": "0.002980795480383277", "pair": "XRP/USD"}, {"expected_move_pct": "0.002145091606608557", "pair": "SAND/USD"}, {"expected_move_pct": "0.001948110331129862", "pair": "SEI/USD"}, {"expected_move_pct": "0.0017748100144818636", "pair": "SHIB/USD"}, {"expected_move_pct": "0.0016842313882936967", "pair": "XLM/USD"}, {"expected_move_pct": "0.00046021258950333026", "pair": "APT/USD"}, {"expected_move_pct": "0.00018520420881387874", "pair": "SUI/USD"}, {"expected_move_pct": "-0.000021717169588452746", "pair": "SOL/USD"}, {"expected_move_pct": "-0.00014560419798555972", "pair": "AAVE/USD"}, {"expected_move_pct": "-0.00029768713612469814", "pair": "PEPE/USD"}, {"expected_move_pct": "-0.00063596346839138", "pair": "LTC/USD"}, {"expected_move_pct": "-0.0007942213241133565", "pair": "XMR/USD"}, {"expected_move_pct": "-0.0009569271759825638", "pair": "CRV/USD"}, {"expected_move_pct": "-0.0010622063866964346", "pair": "KSM/USD"}, {"expected_move_pct": "-0.0010960341602361855", "pair": "SCRT/USD"}, {"expected_move_pct": "-0.0012083894346282644", "pair": "ATOM/USD"}, {"expected_move_pct": "-0.0012083894346282644", "pair": "DOT/USD"}, {"expected_move_pct": "-0.0013517692068797278", "pair": "NEAR/USD"}, {"expected_move_pct": "-0.0013887822332512693", "pair": "ICP/USD"}, {"expected_move_pct": "-0.0014343330698202523", "pair": "RUNE/USD"}, {"expected_move_pct": "-0.0016282585927286672", "pair": "LUNA/USD"}, {"expected_move_pct": "-0.001629162526092104", "pair": "FET/USD"}, {"expected_move_pct": "-0.0018544936437983324", "pair": "BONK/USD"}, {"expected_move_pct": "-0.0022650883993839436", "pair": "ADA/USD"}, {"expected_move_pct": "-0.0033306151484158632", "pair": "AVAX/USD"}, {"expected_move_pct": "-0.003504771685280723", "pair": "BCH/USD"}, {"expected_move_pct": "-0.0036875200584974054", "pair": "LINK/USD"}]},
      "skeptic": {"model_run_id": "train-20260913T205245-067b2b9d-f394-p7", "p_wrong": 0.2662825593750926, "threshold": 0.5, "vetoed": false}
    }
  },
  "updated_at": 1729398600000000
}
```

**One real rejection row** (tier 3, `rejections.id` 1457):

```json
{
  "id": 1457,
  "cycle_id": 1575,
  "run_id": "replay-phase7-t3-expected_move-20241005T001500Z",
  "ts": 1729406700000000,
  "pair": "STORJ/USD",
  "rejected_by": "cost",
  "reason_code": "net_edge_below_hurdle",
  "reason": "Net edge +0.74% after fees, below the +1.00% hurdle on +0.67% friction",
  "expected_move_pct": "0.014040017904735795",
  "friction_pct": "0.006689078153393524242326864972",
  "net_edge_pct": "0.007350939751342270757673135028",
  "hurdle_pct": "0.01003361723009028636349029746",
  "candidate_score": null,
  "shap_ref": "shap/replay-phase7-t3-expected_move-20241005T001500Z/1575/STORJ%2FUSD.parquet",
  "details": {
    "details_version": 1,
    "engines": {
      "anomaly": {"anomalous": false, "model_run_id": "train-20260913T205245-067b2b9d-f394-p7", "score": 0.4848729679716602, "threshold": 0.6474051905957353},
      "cost": {"clears_hurdle": false, "expected_move_pct": "0.014040017904735795", "friction_pct": "0.006689078153393524242326864972", "hurdle_pct": "0.01003361723009028636349029746", "net_edge_pct": "0.007350939751342270757673135028"},
      "order_book": {"basis_notional": "4974.948236299813003810342525", "best_bid": "0.5636743056752899999718085", "depth": 10, "estimated_slippage_pct": "0.0001368041533935241423268649725", "fill_price": "0.5635971926891124093826404271", "levels_consumed": 5},
      "prediction": {"di": 1.128873509266778, "di_threshold": 2.2766046106046764, "expected_move_pct": "0.014040017904735795", "is_buy": true, "model_run_id": "train-20260913T205245-067b2b9d-f394-p7", "p_stop": 0.3473125880552217, "p_target": 0.6396309716563389, "p_timeout": 0.013056440288439575},
      "regime": {"label": "trending"},
      "scout": {"pair": "STORJ/USD", "rank_descending": true, "rank_feature": "expected_move", "rank_run_ids": {"anomaly": "train-20260913T205245-067b2b9d-f394-p7", "prediction": "train-20260913T205245-067b2b9d-f394-p7"}, "rank_skipped": {"anomaly_inputs_incomplete": 154}, "ranked": [{"expected_move_pct": "0.014040017904735795", "pair": "STORJ/USD"}, {"expected_move_pct": "0.006054629837699787", "pair": "SAND/USD"}, {"expected_move_pct": "0.0053137294755432", "pair": "ETH/USD"}, {"expected_move_pct": "0.004944951599262274", "pair": "GALA/USD"}, {"expected_move_pct": "0.004654988236116681", "pair": "AUD/USD"}, {"expected_move_pct": "0.004654988236116681", "pair": "BTC/USD"}, {"expected_move_pct": "0.004654988236116681", "pair": "EUR/USD"}, {"expected_move_pct": "0.004654988236116681", "pair": "GBP/USD"}, {"expected_move_pct": "0.004654988236116681", "pair": "USDC/USD"}, {"expected_move_pct": "0.004654988236116681", "pair": "USDT/USD"}, {"expected_move_pct": "0.00427880988461774", "pair": "SC/USD"}, {"expected_move_pct": "0.004256523306781836", "pair": "TRX/USD"}, {"expected_move_pct": "0.004051391613446933", "pair": "RARE/USD"}, {"expected_move_pct": "0.0035921170752115203", "pair": "AXS/USD"}, {"expected_move_pct": "0.0025771842991843884", "pair": "CRV/USD"}, {"expected_move_pct": "0.0017361410037753985", "pair": "XLM/USD"}, {"expected_move_pct": "0.0003417483843388357", "pair": "XRP/USD"}, {"expected_move_pct": "-0.0006078588070513752", "pair": "SHIB/USD"}, {"expected_move_pct": "-0.0006722732866493212", "pair": "XMR/USD"}, {"expected_move_pct": "-0.0009264478152505877", "pair": "UNI/USD"}, {"expected_move_pct": "-0.0010766435361154454", "pair": "ADA/USD"}, {"expected_move_pct": "-0.0012719635632453916", "pair": "DOT/USD"}, {"expected_move_pct": "-0.0012719635632453916", "pair": "LTC/USD"}, {"expected_move_pct": "-0.0013974399781271475", "pair": "SOL/USD"}, {"expected_move_pct": "-0.0014218847526719757", "pair": "SCRT/USD"}, {"expected_move_pct": "-0.0014928322341107166", "pair": "APT/USD"}, {"expected_move_pct": "-0.0014928322341107166", "pair": "NEAR/USD"}, {"expected_move_pct": "-0.0015945409703804062", "pair": "DOGE/USD"}, {"expected_move_pct": "-0.001629162526092104", "pair": "LUNA/USD"}, {"expected_move_pct": "-0.001629162526092104", "pair": "SUI/USD"}, {"expected_move_pct": "-0.0018806992117545618", "pair": "INJ/USD"}, {"expected_move_pct": "-0.0018820274794385658", "pair": "FET/USD"}, {"expected_move_pct": "-0.001982792414504099", "pair": "SEI/USD"}, {"expected_move_pct": "-0.00202367471037014", "pair": "AVAX/USD"}, {"expected_move_pct": "-0.0021911829369995976", "pair": "BONK/USD"}, {"expected_move_pct": "-0.0031856160759855126", "pair": "LINK/USD"}]}
    },
    "refused_by": "cost"
  },
  "updated_at": 1729406700000000
}
```

The trade that the approval above became (`trades` row `trade-pos-1902893928`) copies the four economics and three run ids onto the trade (migration 0006 lines 80–93): `expected_move_pct "0.01872379704121122"`, `friction_pct "0.006689770529027686723613674725"`, `net_edge_pct "0.01203402651218353327638632528"`, `hurdle_pct "0.01003465579354153008542051209"`, all three run ids `…-f394-p7`.

### B.13 Position sizing and exits

**Engine 11's sizing rule** (`src/acsoe/engines/risk/engine.py` lines 1–22):

*Verbatim from `src/acsoe/engines/risk/engine.py`, lines 1–30:*

````python
"""Engine 11 `risk` — sizes a position, and refuses one that cannot be placed honestly.

## The sizing

Invariant 6: "Risk per trade never exceeds the configured fraction of total account
equity." **Risk, not notional.** The money at risk on a position is the distance to its
stop, so:

```
risk_amount = equity x trading.risk_fraction_per_trade
notional    = risk_amount / barriers.stop_pct
qty         = round_down(notional / ask, lot_decimals)
```

Reading `risk_fraction_per_trade` as a fraction of *notional* rather than of money at
risk would size a position 66 times smaller than intended at the configured stop, which
is the kind of error that looks conservative and quietly makes the whole system
untestable. The committed config carries the arithmetic as a comment on
`max_concurrent_positions` — "the balance binds first at $5,000: one position is ~$3,333
notional" — and $5,000 x 1% / 1.5% is $3,333.33, so the intended reading is not inferred
here, it is stated there.

## The refusal

**A position below `ordermin` or `costmin` is rejected, not rounded up.** Invariant 6
says so, spec 35 says so "under any flag or config key", and there is no code path in
this module that could do otherwise: on a rejection the payload has no `qty` field at
all. Rounding up silently increases the money at risk beyond what the sizing decided,
which is the opposite of what a risk gate is for.

````

With `risk_fraction_per_trade 0.01`, `stop_pct 0.015` and 5,000 equity: `risk_amount 50`, `notional 3,333.33` (the real row: `"risk_amount": "50.0000", "notional": "3333.333333332467721776455957", "qty": "5904.45105471"`). `max_concurrent_positions: 3` is inert at this balance because the second position would need cash the account no longer holds (tracker lines 2037–2039).

**Stop and target from the fill price** (`src/acsoe/engines/position_manager/engine.py` lines 399–442): `entry_price = _money(filled.avg_fill_price)`; `target_price = entry_price × (1 + target_pct)`, `stop_price = entry_price × (1 − stop_pct)`, `timeout_at = filled_at + timeout_bars × bar_s`. README §"Barriers are measured from the fill" (line 77). Barrier detection per tick from engine 3's `trade_ranges` (low/high since the previous tick), with **stop winning when both were touched in one tick**:

*Verbatim from `src/acsoe/engines/position_manager/engine.py`, lines 585–622:*

```python
    ) -> tuple[dict[str, str], ...]:
        """Which positions reached a barrier this tick.

        **Stop wins when both were touched in one tick.** The same rule the training
        labels use, and for the same reason: within one tick the order of the two prints
        is unknown, and resolving the ambiguity to `target` would count as a win a trade
        that may well have stopped out first. Resolving it to `stop` cannot flatter the
        strategy, and it keeps the live outcome and the label computed the same way,
        which is the only thing that makes the backtest comparable.

        A pair with **no** `trade_ranges` entry did not trade this tick. It is absent
        rather than a range of zero — spec 85's `TradeRange` refuses a zero count — so
        no price barrier can fire and only the timeout can.
        """
        sensor = state.get(MARKET_SENSOR_KEY)
        ranges = sensor.get(TRADE_RANGES_FIELD) if isinstance(sensor, dict) else None
        ranges = ranges if isinstance(ranges, dict) else {}

        triggered: list[dict[str, str]] = []
        for position, row in marked:
            pair = str(row["pair"])
            stop_price = Decimal(str(row["stop_price"]))
            target_price = Decimal(str(row["target_price"]))
            traded = ranges.get(pair)

            barrier: str | None = None
            if isinstance(traded, dict):
                low = traded.get(TRADE_RANGE_LOW_FIELD)
                high = traded.get(TRADE_RANGE_HIGH_FIELD)
                if low is not None and _money(low) <= stop_price:
                    barrier = Barrier.STOP
                elif high is not None and _money(high) >= target_price:
                    barrier = Barrier.TARGET
            if barrier is None and now >= int(row["timeout_at"]):
                barrier = Barrier.TIMEOUT
            if barrier is not None:
                triggered.append(
                    {POSITION_ID_FIELD: str(position.position_id), BARRIER_FIELD: barrier}
```

**The timeout:** 48 bars from the fill (`timeout_at`), checked as `now >= timeout_at` (line 618); no trade in either run reached it (all nine tier 3 trades and five tier 5 trades closed on `stop` or `target`).

**Exit at market, and why a resting limit was not used** (`src/acsoe/engines/exit/engine.py` lines 15–24):

*Verbatim from `src/acsoe/engines/exit/engine.py`, lines 15–24:*

```python
## Every exit is a taker, in Phase 6, and that is a recorded choice

Invariant 8 **permits** a maker exit on target and requires an immediate one on stop.
Phase 6 takes every exit as a market sell, including on target. Two reasons, and neither
is that it is easier: invariant 5's friction already assumes a taker exit when it prices
the hurdle, so a maker target exit would make every trade cheaper than the gate that
approved it priced — never a defect in itself, but it means no trade is *rejected* for
the want of it. And a resting maker exit is a second order to manage, cancel and
reconcile, with its own window and its own failure to survive a restart, for a saving
the gate never counted on. Written here so nobody reads it as an oversight.
```

The consequence, measured: the four tier 3 target exits realised +1.40%, +2.52%, +2.40% and +2.61% against the label's +3.0% (F5; `docs/build-log/phase-7/a-platform.md` lines 1310–1332, findings Part II lines 996, 1105–1112). Invariant 8 permits a maker exit on target; changing it now would be "changing the system to help it pass its own test" (findings line 757).

**Entry:** one post-only limit buy at the best bid rounded down to `pair_decimals`, `oflags=post`, `userref = userref_for(pair, bar)` (`engines/execution/engine.py` lines 5–7, 166–176, 229–243); cancelled and abandoned after `trading.entry_unfilled_window_s: 300` s (`default.yaml` 95); the paper broker fills it only on a trade **strictly below** the limit (`clients/paper/fills.py` lines 77–100):

*Verbatim from `src/acsoe/clients/paper/fills.py`, lines 1–30:*

```python
"""The fill rules, as pure functions. No clock, no I/O, no state.

Everything here is arithmetic over values the broker hands it, so each rule can be
tested at its boundary without a store, a client or a tick. The broker decides *when*
to ask; this module decides *what the answer is*, and the two are separated because the
rules are the part a reader has to be able to check against the spec by eye.

## Every rule is the pessimistic reading, and that is the whole design

A simulator that flatters the strategy is worse than no simulator, because it produces
a number somebody will put in a dissertation. Each rule below therefore resolves its
ambiguity against the strategy:

- **A post-only buy at or above the best ask is rejected**, not repriced and not filled.
  Kraken cancels such an order outright — invariant 8 says so and calls it the intended
  behaviour — so the simulator does the same thing rather than inventing a kinder one.
- **A resting buy at L fills only when a trade printed strictly below L.** A trade *at*
  L is not a fill. Queue position is unknown: somebody else's order may have been at
  that price first and taken the whole print. Requiring a strictly better price is the
  only assumption that cannot be optimistic. Spec 88 names the boundary explicitly and
  two tests pin it, one tick each side.
- **Partial fills are not simulated.** An order fills in full or not at all. This is the
  one rule that is not obviously pessimistic in both directions and it is the operator's
  spec rather than a choice made here: a half-filled entry would need a partial position,
  a partial exit and a re-quote, and none of those exist in Phase 6.
- **A market sell walks the bid side level by level** and pays the volume-weighted
  average of what it actually eats, never the top of book. If the fetched depth cannot
  absorb the quantity the remainder is priced at the **worst fetched level** and the
  fill records ``book_depth_exhausted``, so a liquidation into a thin book is expensive
  in the simulator exactly as it would be in life.
```

---

## C. Data

### C.1 The historical archive

| Fact | Value | Source |
|---|---|---|
| Source | Kraken's downloadable time-and-sales archives (`data/historical/KRAKEN_TimeAndSales_Combined/`, `TimeAndSales_Combined/`), reduced to 15-minute OHLCVT by `scripts/build_ohlcvt.py` | `architecture-context.md` lines 107–113; `data/derived/trades_weekly/manifest.json` `source_dirs`; `docs/dataset/labelled-dataset-2026-09-12.json` `meta.archive_built_by` |
| Raw pair files | **1,119** pair files, "roughly 27 GB" | `scripts/build_ohlcvt.py` lines 9, 17, 379 ("1,119 files, 413 USD-quoted, 300 with two years") |
| USD-suffixed files scanned / selected by the two-year rule | 413 scanned; **234** selected ("every archive file ending in 'USD' whose first and last trade are at least 2 years apart") | `labelled-dataset-2026-09-12.json` `meta.archive_selection`, `pairs_scanned 413`, `pairs_selected 234`; `docs/PROJECT-STATE.md` line 820–821 |
| Archive built | 2026-09-11T22:34:49Z | `meta.archive_built_at` |
| Date range of labelled decision bars | 2017-01-01 to 2025-12-31 UTC (`first_decision_ts 1483228800`, `last_decision_ts 1767181500`); the archive itself begins 2013-10-07 | `total`; `PROJECT-STATE.md` 819–820 |
| Bars replayed | 20,443,861 | `total.bars` |
| Labelled decision bars | **20,331,237** | `total.labelled` |
| Label split | target 4,857,764 (23.89%); stop 10,424,046 (51.27%); timeout 5,049,427 (24.84%); of which both-barriers-touched → stop 76,522 (0.376%) | `total`; `PROJECT-STATE.md` §10 table |
| Exclusions | 93,475 before 2017-01-01 (92,791 of them previously labelled); 6,658 past the series end; 12,491 empty windows | `total`; `PROJECT-STATE.md` 823–828 |
| Incomplete feature vectors (test rows) | **8,025,361 of 15,978,803 out-of-sample rows (50.2%)** carry an unfilled 48- or 96-bar lookback; 26% in 2017, 61% in 2023; cause: the pair did not trade in every bar of the window (a lookback is a window of time and a missing bar is no trade) | tracker Finding 3, lines 1343–1358; `docs/dataset/di-anomaly-distributions-2026-09-14.md` |
| Out-of-sample rows / decision bars (405 folds) | 15,978,803 rows; 271,667 bars, mean 58.8 pairs per bar | findings lines 174–175 |
| The 1.5-year window | folds 326–404, 2023-07-01 to 2025-01-04, 53,022 decision bars, 6,712,659 pair-bars, 234 distinct pairs | findings lines 177–179 |
| Weekly partitions for the replay | 41 weeks, 2024-03-23 to 2024-12-28 (15 warm-up weeks before the 2024-07-06 window start); 234 pairs; `interpolation: none` | `data/derived/trades_weekly/manifest.json` |

The largest pairs and the eleven thin pairs are tabulated in `docs/PROJECT-STATE.md` §10 (lines 863–896).

### C.2 Live recording

| Fact | Value | Source |
|---|---|---|
| Start | first frame 2026-09-08T16:01:22Z (`kraken_v2_2026-09-08.jsonl`); `scripts/record.py` first committed 2026-09-08 17:24 +0100 | `tests/fixtures/recording_report_full_archive.json` `span.start_iso`; `git log` |
| Two-tier recorder | live from 2026-09-11T19:48:02Z (`session start` line of `kraken_v2__msi__2026-09-11.jsonl`); the previous single recorder's file ends 2026-09-11T19:46:17Z (a 105 s hand-over, read from the two file ends only) | file head/tail; `logs/supervisor__msi__2026-09-11.log` |
| Tiers | **Tier 1, full raw:** every `book`, `ticker`, `trade` frame for the top-N pairs by 24-hour quote volume — **10 pairs**: BTC/USD, USDT/USD, ETH/USD, XRP/USD, SOL/USD, ZEC/USD, USDC/USD, NEAR/USD, EUR/USD, HYPE/USD (the set on 2026-09-11 and today). **Tier 2, per-minute summaries:** every other USD pair above the volume floor — **139 pairs on 2026-09-11 19:48Z**, 137 in the 17:12 restart log, **170 today**; each summary row carries mid OHLC from the book, spread and depth samples, trade counts and a "clean minute" flag; no per-tick bid/ask, no prints, no book | `scripts/record.py` lines 16–50, 92–93; `data/raw/heartbeat__msi__2026-09-11.ndjson` line 1; `data/summaries/heartbeat__msi__2026-09-11.ndjson` line 1; `data/summaries/heartbeat__msi__2026-09-20.ndjson` last line; `logs/recorder-20260911-171206.err.log` |
| Volume today | tier 1: 22,020,347 frames, 7.54 GB written for 2026-09-20 by 15:42Z; tier 2: 164,970,197 frames consumed, 248,841 lines | heartbeats |
| Instrument channel switchover | **2026-09-19 05:08:44Z**: last line of the old recorder 05:08:44.099Z; new recorder's start marker 05:09:44.991Z; first `instrument` snapshot (1,450 pairs) 05:09:47.133Z; gap across the switchover **62.79 s**. Recordings before it carry no pair rules and no fee tier; after it both are recorded | `context/progress-tracker.md` lines 32–48; `docs/build-log/phase-7/a-platform.md` §"The one switchover" (line 1187) |
| Known gap 1 | ~10 hours, 2026-09-08T16:02:17Z to 2026-09-09T02:04Z: no recorder running (36,122 of the full archive's 40,471 missing seconds) | tracker line 1109; `docs/build-log/phase-2.md` lines 467, 748 |
| Known gap 2 | disk-full outage at 2026-09-09T13:06:37Z with restarts either side; the clean 24 h span starts an hour later (`recording_report.json`: 24.07 h, recorded fraction 0.99977, 9 gaps totalling 20.25 s) | tracker line 1109; `tests/fixtures/recording_report.json` |
| Known gap 3 | **2026-09-17 03:13–08:20Z (308 minutes)**: network down; heartbeat `connected: false` throughout; unrecoverable | tracker Known Risks line 2236 |
| Known gap 4 | the 62.79 s switchover gap of 2026-09-19 | above |
| Gaps not on record | a "15-hour gap on 10–11 September" (the claims list) — **NOT FOUND**: neither the tracker, `docs/build-log/phase-2.md`, `phase-6.md` nor `a-platform.md` records it, and the file ends show the old recorder writing through 2026-09-10T23:59:59Z and until 2026-09-11T19:46:17Z. (Whether the interior of those files has holes was not scanned — multi-GB files.) | grep for `15 hours`, `fifteen hours`, `2026-09-10` |
| Replayable coverage | "The replayable universe is about 7 pairs": tier 2 pairs have no per-tick bid/ask, prints or book, so in a replay of the recording engines 3 and 7 see only the 10 tier-1 pairs, 3 of which are stable or FX | `a-platform.md` lines 148–156 (recorder gap audit, item 3) |

### C.3 Funding and fee pollers

- **`scripts/recording/fees.py`** (docstring lines 1–47): once an hour on the hour, `GET /0/public/AssetPairs` (verbatim) and `POST /0/private/TradeVolume` with `pair=<the tier 1 pairs as REST keys>` and `fee_schedule=true` (verbatim response); credentials read from `.env` only, redacted everywhere; output `data/raw/fees/fees__msi__<date>.jsonl`; a missing key writes a `gap` marker instead of crashing. Started 2026-09-19T05:08:45Z (P2, operator ruling 2026-09-19). Known limit: one API key shared with the daemon, two nonce counters (`a-platform.md` line 801; handover open question).
- **`scripts/recording/funding.py`** (docstring lines 1–50): public data only, no credentials; once an hour `GET https://futures.kraken.com/derivatives/api/v3/tickers`; for every perpetual whose underlying matches a tier-1 spot pair and clears `funding_floor_usd: 1000000`, one verbatim line (`fundingRate`, `fundingRatePrediction`, `openInterest`, `markPrice`, …); `--backfill` pulls funding history. Open interest is not backfillable, funding rate is.
- **Known outage:** the funding poller died 2026-09-15 08:00Z and nothing restarted it until 2026-09-19 04:42 local (D2): `a-platform.md` lines 83–99 ("**Finding 3: the funding poller is not running, and nothing restarts it.** … The last funding file is `data/raw/funding/funding__msi__2026-09-15.jsonl`, whose last poll was 2026-09-15 08:00Z"); `docs/build-log/phase-7/overnight-decisions-2026-09-19.md` §D2 "The funding poller restarted, 04:42 local, PID 42044". The file listing confirms: `funding__msi__2026-09-13`, `-14`, `-15`, then `-19`, `-20` — no 16, 17, 18. The supervisor now lists both pollers (`config/recorder.yaml` lines 93–104: "Added 2026-09-19 after the funding poller died on 2026-09-15 with nothing to bring it back").

### C.4 Phase 7's declared substitutes

*Verbatim from `docs/dataset/phase-7-findings.md`, lines 628–667:*

```markdown
## 7a. The declared substitutes the chain simulation runs on (written before launch, 2026-09-19)

The simulation is **two runs: tier 3 and tier 5, engine 8's expected-move ranking, the median
column of the bucket table, over the three months ending 2025-01-04** (operator rulings
2026-09-19). Every input below that the 2023–24
archive does not hold is either **declared** or **recorded in 2026**, and each is named with its
source and date. None is a measurement of the period it is applied to.

| Input | What the run uses | Source and date |
|---|---|---|
| **Spread** | Per pair, the **median** spread of its liquidity bucket, keyed on the pair's trailing 24-hour dollar volume computed from the replayed trades: 30.4 bps (< $10k), 25.8 ($10k–100k), 12.3 ($100k–1M), 5.5 ($1M–10M); the > $10M bucket uses the $1M–10M row. Served as half the spread either side of the last traded price. A pair with no trade in 24 h has **no quote**, never a zero spread. | `tests/fixtures/replay/spread_book_table_2026-09-19.json`, built by `scripts/build_bucket_table.py` from the recorder's minute summaries of 185 recorded USD pairs, 2026-09-11 16:13Z to 2026-09-19 00:45Z (7.36 days). Per pair, the median of each clean minute's median spread; per bucket, the median of the per-pair medians. The interquartile ranges are published there as declared uncertainty. |
| **Book depth** | Per bucket, the median bid depth to $10,000 from mid: 86.2 / 100.5 / 35.2 / 8.9 bps. Laid as 10 evenly spaced levels from the half-spread to that depth, and walked by engine 9 with its own arithmetic. That serves $5k slippage of 15.8 / 19.5 / 6.5 / 1.4 bps. | Same fixture and recording span. The table's continuous-book check figures (17.7 / 20.8 / 7.5 / 1.7) differ because the served book is ten discrete levels. |
| **Pair rules** | Kraken's `AssetPairs` as recorded (REST, verbatim), keyed by the engines' names through the websocket `instrument` snapshot captured with it. The 2026 tick sizes apply, finer than 2024's on 15 pairs. | `tests/fixtures/kraken/asset_pairs_recorded_2026-09-19.json`, `instrument_recorded_2026-09-19.json` and `pair_names_recorded_2026-09-19.json`, captured 2026-09-19 (spec 127). |
| **Fee tier** | Kraken's **Spot Crypto** schedule, served to every pair (D8): tier 3 at 0.22% maker / 0.38% taker, tier 5 at 0.15% / 0.30%. The FX, stablecoin and pegged-token pairs are overcharged by this, the conservative direction. | `tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`, fetched 2026-09-19T02:59:51Z from kraken.com/features/fee-schedule, with the raw page and the 9 July 2026 restructuring article committed beside it. |

**Declared limitations, stated before any figure exists:**

1. **Every substitute is 2026 applied to 2024.** The spread and depth come from 7.4 days of
   September 2026; the pair rules and the fee schedule are as of 2026-09-19. Liquidity, pair rules
   and Kraken's fees in July 2024 to January 2025 are not on disk, and the run does not know them.
2. **Survivorship: 39 of the 231 archive USD pairs trading in the window are absent from the 2026
   rules and are excluded from the universe** (42 of 234 over the 1.5-year window; spec 127). Some
   are probable rebrands (MATIC/POL, FTM, MKR, and RNDR in the 1.5-year count), so 39 is an upper
   bound on delistings. The universe is therefore biased towards pairs that still trade in 2026,
   the survivors. Pairs that failed between 2024 and 2026 cannot be traded in the simulation even
   if they were candidates in 2024. That can flatter or harm the result, and the direction is not
   known.
3. **The fee schedule is 2026's too.** Kraken restructured its tiers on 9 July 2026, and nothing on
   disk dates any earlier schedule. Fees are the input the result is most sensitive to (§4: under
   the ruled ranking, 46 trades at 0.60% fees against 254 at 0.40% over 12 months).
4. **Spread sensitivity was NOT run through the chain** (operator ruling 2026-09-19: the extra
   runs would push the tier-3 run past 32 hours). **A different spread changes WHICH trades
   happen, not only what they earn.** Spread is part of friction, friction decides the cost gate,
   and the gates after it, the entry fills and the account's path follow from that. So the effect
   of a different spread on the trade set is **unrecoverable without a re-run.** What is available
   instead:
   - the offline flat-against-bucket comparison of §3, which found that a constant spread inverted
     the sign of the result;
   - a post-run script that re-prices the trades that did happen under another spread, which
     answers what they would have earned and nothing about which trades would have happened.
```

Applied to the window 2024-10-05T00:15Z … 2025-01-04T00:00Z, every tick, both tiers (`runs.scenario_description` in each database: "DECLARED, not measured. The spread and depth come from a liquidity-bucket table built from a 2026 recording and applied uniformly to every pair of a 2023-24 window. The fee is Kraken's schedule fetched 2026-09-19, applied at one tier to every pair. The pair rules are a 2026 recording. Only the trades are the period's own record."). Dates of the data: spread and depth 2026-09-11 16:13Z to 2026-09-19 00:45Z; pair rules 2026-09-19 (`asset_pairs_recorded_2026-09-19.json` sha256 `153dcb89…`, `instrument_recorded_2026-09-19.json` `69b51f36…`, `pair_names_recorded_2026-09-19.json` `2f43ebdb…`); fees fetched 2026-09-19T02:59:51Z; the restructure dated 2026-07-09.

### C.5 The excluded pairs

- **The rule:** a pair with no entry in the recorded 2026 `AssetPairs` has no `ordermin`, `costmin` or tick size, and engine 7 excludes it as `pair_rules_missing` (`engines/scout/contracts.py` line 244; `context/architecture-context.md` lines 142–144: "The pair rules are a genuine `AssetPairs` recorded in 2026 (spec 127). That is a recording of another period, not a proxy, and the survivorship it causes is reported.").
- **The count:** **39 of the 231 archive USD pairs trading in the window** (folds 379–404) are absent from the 2026 rules; **42 of 234** over the 1.5-year window — `docs/dataset/phase-7-findings.md` lines 648–654 (§7a item 2) and `overnight-decisions-2026-09-19.md` "Recorded answer, spec 127 survivorship" (lines 240–244). Some are probable rebrands (MATIC/POL, FTM, MKR, RNDR), so 39 is an upper bound on delistings; the direction of the bias is not known.
- **Their identities are stored on the `runs` row** (`scenario_description.partitions.archive_pairs_without_rules`, both databases), 42 names: AGLDUSD, AIRUSD, ANTUSD, BITUSD, BONDUSD, BSXUSD, CSMUSD, EOSUSD, ETHWUSD, FARMUSD, FTMUSD, GALUSD, GARIUSD, ICXUSD, INTRUSD, KARUSD, KILTUSD, KINTUSD, LUNA2USD, MATICUSD, MCUSD, MKRUSD, MOONUSD, MVUSD, MXCUSD, NODLUSD, NYMUSD, OXYUSD, PSTAKEUSD, REPUSD, REPV2USD, RNDRUSD, ROOKUSD, SDNUSD, STEPUSD, TEERUSD, TOKEUSD, TUSDUSD, TVKUSD, USTUSD, WAVESUSD, XRTUSD. (The claims list's "excluded pairs' identities not stored in the run" is therefore **not correct for the scenario description**; what the `scout_tallies` rows do not store is which pair was excluded for which per-tick reason — they hold counts by reason only, `architecture-context.md` line 159.)
