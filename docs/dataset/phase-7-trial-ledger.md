# Phase 7 trial ledger

Every configuration evaluated against the out-of-sample data, one row per trial (spec 139, ruling R9). **Built by `python -m acsoe.research.trial_ledger` from the committed outputs; never typed by hand.** The JSON beside this file is the same ledger, and the promotion gate reads its `trial_count`.

**Trial count: 1679.** It errs high on purpose.

## The rule

A trial is a selection (a rule deciding which rows, bars or calls would be traded) evaluated on the out-of-sample data and reported with any statistic of what it selected. Each reported (selection, sample) is one row. Where it is unclear whether two reports are one trial or two, they are two. The count errs high on purpose: a larger count makes the Bonferroni haircut harsher and a result harder to claim.

## Judgements made under the rule

- Funnels: every stage a line reports counts, because each stage is a different selection (the gates up to that point).
- Sub-windows (a year, a 6-, 12- or 18-month slice) of a selection count separately.
- A selection and its complement reported with their own outcomes (survivors and vetoed; kept and refused) count as two.
- The same selection reported in two files or two lines counts twice: nothing on disk proves two reports were one computation. Examples: q_window's (a)/(b) counts and their detail lines; the ranking study's rows and the by-year study's 'all' rows; the skeptic's own survivors in the skeptic-against-p_target comparison; q_hold against q_window's (b) column.
- The two tie-breaking seeds of the p_target comparison count as two.
- Counts without an outcome (rows above an expected-move bar, a gate's refusal share) count, because a count of what a selection would have traded is a statistic of that selection.
- Spec 139 lists the DI at 0.95, 0.99 and 0.999 and the anomaly gate at 0.95 and 0.99. The committed study evaluated seven percentiles of each and a 3x3 joint grid, so every one evaluated is counted, not only the ones the spec named.
- Whether an output shows every cell its script evaluated: the loops of q_funnel, q_bucket, q_emrank, q_hold, q_picks, q_capped_compare, 2026-09-18_q_net and 2026-09-18_q_year were read against their outputs on 2026-09-19, and each prints one line per cell it evaluated, zero-trade cells included. Where a script could have been run more than once before its output was saved, only the saved run is visible, and it is what is counted.
- Anything computed before 2026-09-19 in a session and never committed cannot be counted from the outputs. The ledger counts what the committed outputs show and the smoke-run models seen on disk; it cannot see more.
- Leaderboard. Engine 20 has written no persisted leaderboard row for the walk-forward: the only database on disk (data/db/acsoe.sqlite) holds the six fabricated Phase 0 seed rows. The rows engine 20 would write are one per trained fold, and the committed walk-forward table (walkforward-folds-2026-09-14.md, rebuilt from the fold artefacts) lists them, so each fold there is counted as one leaderboard row.
- The three fold models of a three-pair smoke training run exist only on disk under models/. Whether they count as evaluated on the out-of-sample data is unclear, so they count.

## By family

| Family | Trials |
|---|---|
| di_anomaly | 287 |
| leaderboard | 408 |
| phase_7_runs | 4 |
| ranking_study | 169 |
| recon | 674 |
| skeptic_sweep | 92 |
| skeptic_vs_p_target | 45 |

## Excluded, with the reason

| Source | Where | Why it counts nothing |
|---|---|---|
| data/db/acsoe.sqlite (gitignored) | leaderboard | six rows, model versions v0.1 to v0.6 of training runs seed-train-0000 to 0005: the Phase 0 seed's fabricated rows, evaluated on nothing |
| tests/fixtures/leaderboard_sample.json | whole file | the committed Phase 6 fixture: fabricated rows for engine 14's criterion |
| docs/dataset/phase-7-recon-2026-09-19/outputs/2026-09-18_q_spread.log | whole file | measures spread and depth on the 2026 recording; selects no trade |
| docs/dataset/phase-7-recon-2026-09-19/outputs/q_ticks.out | whole file | compares price grids between the archive and the 2026 recording; selects no trade |
| docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | section q_spread_agg.py | measures spread on the 2026 recording; selects no trade |
| docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | section q_spread_fit.py | fits a spread model on the 2026 recording; selects no trade |
| docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | section q_spread_extrap.py | backcasts spread levels for five pairs; selects no trade |
| docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | section q_depth.py | measures depth on the 2026 recording; selects no trade |
| docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | section q_capped.py validate 20,40 | checks the capped-skeptic replication reproduces two saved skeptics exactly; an identity check, not a selection |
| docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | section q_di_rebuild.py 404,360,326 | rebuilds three DI references and checks their identity; selects no trade |
| docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | section q_timing.py | times the engines; selects no trade |
| docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | section q_rank_timing.py | times the ranking; selects no trade |
| docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | section probe_load.py 404 | probes artefact loading and memory; selects no trade |
| docs/dataset/ranking-study-2026-09-13.json | whole file | computed on the constructed two-pair series of tests/research/test_training.py (its own meta.source says so), not on the walk-forward's out-of-sample rows |
| docs/dataset/skeptic-veto-sweep-2026-09-14.json | no_skill_survivor_target_rate_* (every sweep row) | 20 permutations of each fold's own scores: a null distribution, not a configuration anyone could adopt |
| docs/dataset/di-anomaly-distributions-2026-09-14.json | folds[*] and coverage | per-fold threshold values and coverage counts; they select nothing |
| docs/dataset/labelled-dataset-2026-09-12.json | whole file | dataset statistics; selects nothing |
| docs/dataset/labelled-dataset-2026-09-12-before-cutoff.json | whole file | dataset statistics; selects nothing |
| docs/dataset/folds-three-pairs-2026-09-12.json | whole file | fold construction; selects nothing |

## Every trial

| # | Family | Source | Where | Configuration | Reported |
|---|---|---|---|---|---|
| 1 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 11 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 0 | test week 2017-04-01 |
| 2 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 12 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 1 | test week 2017-04-08 |
| 3 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 13 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 2 | test week 2017-04-15 |
| 4 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 14 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 3 | test week 2017-04-22 |
| 5 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 15 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 4 | test week 2017-04-29 |
| 6 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 16 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 5 | test week 2017-05-06 |
| 7 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 17 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 6 | test week 2017-05-13 |
| 8 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 18 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 7 | test week 2017-05-20 |
| 9 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 19 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 8 | test week 2017-05-27 |
| 10 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 20 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 9 | test week 2017-06-03 |
| 11 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 21 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 10 | test week 2017-06-10 |
| 12 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 22 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 11 | test week 2017-06-17 |
| 13 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 23 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 12 | test week 2017-06-24 |
| 14 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 24 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 13 | test week 2017-07-01 |
| 15 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 25 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 14 | test week 2017-07-08 |
| 16 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 26 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 15 | test week 2017-07-15 |
| 17 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 27 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 16 | test week 2017-07-22 |
| 18 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 28 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 17 | test week 2017-07-29 |
| 19 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 29 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 18 | test week 2017-08-05 |
| 20 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 30 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 19 | test week 2017-08-12 |
| 21 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 31 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 20 | test week 2017-08-19 |
| 22 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 32 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 21 | test week 2017-08-26 |
| 23 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 33 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 22 | test week 2017-09-02 |
| 24 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 34 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 23 | test week 2017-09-09 |
| 25 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 35 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 24 | test week 2017-09-16 |
| 26 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 36 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 25 | test week 2017-09-23 |
| 27 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 37 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 26 | test week 2017-09-30 |
| 28 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 38 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 27 | test week 2017-10-07 |
| 29 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 39 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 28 | test week 2017-10-14 |
| 30 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 40 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 29 | test week 2017-10-21 |
| 31 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 41 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 30 | test week 2017-10-28 |
| 32 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 42 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 31 | test week 2017-11-04 |
| 33 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 43 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 32 | test week 2017-11-11 |
| 34 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 44 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 33 | test week 2017-11-18 |
| 35 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 45 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 34 | test week 2017-11-25 |
| 36 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 46 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 35 | test week 2017-12-02 |
| 37 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 47 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 36 | test week 2017-12-09 |
| 38 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 48 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 37 | test week 2017-12-16 |
| 39 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 49 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 38 | test week 2017-12-23 |
| 40 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 50 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 39 | test week 2017-12-30 |
| 41 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 51 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 40 | test week 2018-01-06 |
| 42 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 52 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 41 | test week 2018-01-13 |
| 43 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 53 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 42 | test week 2018-01-20 |
| 44 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 54 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 43 | test week 2018-01-27 |
| 45 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 55 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 44 | test week 2018-02-03 |
| 46 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 56 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 45 | test week 2018-02-10 |
| 47 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 57 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 46 | test week 2018-02-17 |
| 48 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 58 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 47 | test week 2018-02-24 |
| 49 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 59 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 48 | test week 2018-03-03 |
| 50 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 60 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 49 | test week 2018-03-10 |
| 51 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 61 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 50 | test week 2018-03-17 |
| 52 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 62 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 51 | test week 2018-03-24 |
| 53 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 63 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 52 | test week 2018-03-31 |
| 54 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 64 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 53 | test week 2018-04-07 |
| 55 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 65 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 54 | test week 2018-04-14 |
| 56 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 66 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 55 | test week 2018-04-21 |
| 57 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 67 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 56 | test week 2018-04-28 |
| 58 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 68 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 57 | test week 2018-05-05 |
| 59 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 69 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 58 | test week 2018-05-12 |
| 60 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 70 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 59 | test week 2018-05-19 |
| 61 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 71 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 60 | test week 2018-05-26 |
| 62 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 72 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 61 | test week 2018-06-02 |
| 63 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 73 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 62 | test week 2018-06-09 |
| 64 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 74 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 63 | test week 2018-06-16 |
| 65 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 75 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 64 | test week 2018-06-23 |
| 66 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 76 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 65 | test week 2018-06-30 |
| 67 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 77 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 66 | test week 2018-07-07 |
| 68 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 78 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 67 | test week 2018-07-14 |
| 69 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 79 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 68 | test week 2018-07-21 |
| 70 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 80 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 69 | test week 2018-07-28 |
| 71 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 81 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 70 | test week 2018-08-04 |
| 72 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 82 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 71 | test week 2018-08-11 |
| 73 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 83 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 72 | test week 2018-08-18 |
| 74 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 84 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 73 | test week 2018-08-25 |
| 75 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 85 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 74 | test week 2018-09-01 |
| 76 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 86 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 75 | test week 2018-09-08 |
| 77 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 87 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 76 | test week 2018-09-15 |
| 78 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 88 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 77 | test week 2018-09-22 |
| 79 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 89 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 78 | test week 2018-09-29 |
| 80 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 90 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 79 | test week 2018-10-06 |
| 81 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 91 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 80 | test week 2018-10-13 |
| 82 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 92 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 81 | test week 2018-10-20 |
| 83 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 93 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 82 | test week 2018-10-27 |
| 84 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 94 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 83 | test week 2018-11-03 |
| 85 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 95 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 84 | test week 2018-11-10 |
| 86 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 96 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 85 | test week 2018-11-17 |
| 87 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 97 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 86 | test week 2018-11-24 |
| 88 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 98 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 87 | test week 2018-12-01 |
| 89 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 99 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 88 | test week 2018-12-08 |
| 90 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 100 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 89 | test week 2018-12-15 |
| 91 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 101 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 90 | test week 2018-12-22 |
| 92 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 102 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 91 | test week 2018-12-29 |
| 93 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 103 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 92 | test week 2019-01-05 |
| 94 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 104 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 93 | test week 2019-01-12 |
| 95 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 105 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 94 | test week 2019-01-19 |
| 96 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 106 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 95 | test week 2019-01-26 |
| 97 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 107 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 96 | test week 2019-02-02 |
| 98 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 108 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 97 | test week 2019-02-09 |
| 99 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 109 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 98 | test week 2019-02-16 |
| 100 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 110 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 99 | test week 2019-02-23 |
| 101 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 111 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 100 | test week 2019-03-02 |
| 102 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 112 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 101 | test week 2019-03-09 |
| 103 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 113 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 102 | test week 2019-03-16 |
| 104 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 114 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 103 | test week 2019-03-23 |
| 105 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 115 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 104 | test week 2019-03-30 |
| 106 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 116 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 105 | test week 2019-04-06 |
| 107 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 117 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 106 | test week 2019-04-13 |
| 108 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 118 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 107 | test week 2019-04-20 |
| 109 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 119 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 108 | test week 2019-04-27 |
| 110 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 120 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 109 | test week 2019-05-04 |
| 111 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 121 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 110 | test week 2019-05-11 |
| 112 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 122 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 111 | test week 2019-05-18 |
| 113 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 123 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 112 | test week 2019-05-25 |
| 114 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 124 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 113 | test week 2019-06-01 |
| 115 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 125 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 114 | test week 2019-06-08 |
| 116 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 126 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 115 | test week 2019-06-15 |
| 117 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 127 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 116 | test week 2019-06-22 |
| 118 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 128 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 117 | test week 2019-06-29 |
| 119 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 129 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 118 | test week 2019-07-06 |
| 120 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 130 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 119 | test week 2019-07-13 |
| 121 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 131 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 120 | test week 2019-07-20 |
| 122 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 132 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 121 | test week 2019-07-27 |
| 123 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 133 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 122 | test week 2019-08-03 |
| 124 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 134 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 123 | test week 2019-08-10 |
| 125 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 135 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 124 | test week 2019-08-17 |
| 126 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 136 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 125 | test week 2019-08-24 |
| 127 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 137 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 126 | test week 2019-08-31 |
| 128 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 138 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 127 | test week 2019-09-07 |
| 129 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 139 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 128 | test week 2019-09-14 |
| 130 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 140 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 129 | test week 2019-09-21 |
| 131 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 141 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 130 | test week 2019-09-28 |
| 132 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 142 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 131 | test week 2019-10-05 |
| 133 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 143 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 132 | test week 2019-10-12 |
| 134 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 144 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 133 | test week 2019-10-19 |
| 135 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 145 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 134 | test week 2019-10-26 |
| 136 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 146 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 135 | test week 2019-11-02 |
| 137 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 147 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 136 | test week 2019-11-09 |
| 138 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 148 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 137 | test week 2019-11-16 |
| 139 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 149 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 138 | test week 2019-11-23 |
| 140 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 150 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 139 | test week 2019-11-30 |
| 141 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 151 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 140 | test week 2019-12-07 |
| 142 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 152 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 141 | test week 2019-12-14 |
| 143 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 153 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 142 | test week 2019-12-21 |
| 144 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 154 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 143 | test week 2019-12-28 |
| 145 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 155 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 144 | test week 2020-01-04 |
| 146 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 156 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 145 | test week 2020-01-11 |
| 147 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 157 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 146 | test week 2020-01-18 |
| 148 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 158 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 147 | test week 2020-01-25 |
| 149 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 159 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 148 | test week 2020-02-01 |
| 150 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 160 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 149 | test week 2020-02-08 |
| 151 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 161 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 150 | test week 2020-02-15 |
| 152 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 162 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 151 | test week 2020-02-22 |
| 153 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 163 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 152 | test week 2020-02-29 |
| 154 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 164 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 153 | test week 2020-03-07 |
| 155 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 165 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 154 | test week 2020-03-14 |
| 156 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 166 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 155 | test week 2020-03-21 |
| 157 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 167 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 156 | test week 2020-03-28 |
| 158 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 168 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 157 | test week 2020-04-04 |
| 159 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 169 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 158 | test week 2020-04-11 |
| 160 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 170 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 159 | test week 2020-04-18 |
| 161 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 171 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 160 | test week 2020-04-25 |
| 162 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 172 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 161 | test week 2020-05-02 |
| 163 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 173 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 162 | test week 2020-05-09 |
| 164 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 174 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 163 | test week 2020-05-16 |
| 165 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 175 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 164 | test week 2020-05-23 |
| 166 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 176 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 165 | test week 2020-05-30 |
| 167 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 177 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 166 | test week 2020-06-06 |
| 168 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 178 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 167 | test week 2020-06-13 |
| 169 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 179 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 168 | test week 2020-06-20 |
| 170 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 180 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 169 | test week 2020-06-27 |
| 171 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 181 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 170 | test week 2020-07-04 |
| 172 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 182 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 171 | test week 2020-07-11 |
| 173 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 183 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 172 | test week 2020-07-18 |
| 174 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 184 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 173 | test week 2020-07-25 |
| 175 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 185 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 174 | test week 2020-08-01 |
| 176 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 186 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 175 | test week 2020-08-08 |
| 177 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 187 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 176 | test week 2020-08-15 |
| 178 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 188 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 177 | test week 2020-08-22 |
| 179 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 189 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 178 | test week 2020-08-29 |
| 180 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 190 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 179 | test week 2020-09-05 |
| 181 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 191 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 180 | test week 2020-09-12 |
| 182 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 192 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 181 | test week 2020-09-19 |
| 183 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 193 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 182 | test week 2020-09-26 |
| 184 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 194 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 183 | test week 2020-10-03 |
| 185 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 195 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 184 | test week 2020-10-10 |
| 186 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 196 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 185 | test week 2020-10-17 |
| 187 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 197 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 186 | test week 2020-10-24 |
| 188 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 198 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 187 | test week 2020-10-31 |
| 189 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 199 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 188 | test week 2020-11-07 |
| 190 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 200 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 189 | test week 2020-11-14 |
| 191 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 201 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 190 | test week 2020-11-21 |
| 192 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 202 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 191 | test week 2020-11-28 |
| 193 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 203 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 192 | test week 2020-12-05 |
| 194 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 204 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 193 | test week 2020-12-12 |
| 195 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 205 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 194 | test week 2020-12-19 |
| 196 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 206 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 195 | test week 2020-12-26 |
| 197 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 207 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 196 | test week 2021-01-02 |
| 198 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 208 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 197 | test week 2021-01-09 |
| 199 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 209 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 198 | test week 2021-01-16 |
| 200 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 210 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 199 | test week 2021-01-23 |
| 201 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 211 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 200 | test week 2021-01-30 |
| 202 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 212 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 201 | test week 2021-02-06 |
| 203 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 213 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 202 | test week 2021-02-13 |
| 204 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 214 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 203 | test week 2021-02-20 |
| 205 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 215 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 204 | test week 2021-02-27 |
| 206 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 216 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 205 | test week 2021-03-06 |
| 207 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 217 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 206 | test week 2021-03-13 |
| 208 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 218 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 207 | test week 2021-03-20 |
| 209 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 219 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 208 | test week 2021-03-27 |
| 210 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 220 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 209 | test week 2021-04-03 |
| 211 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 221 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 210 | test week 2021-04-10 |
| 212 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 222 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 211 | test week 2021-04-17 |
| 213 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 223 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 212 | test week 2021-04-24 |
| 214 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 224 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 213 | test week 2021-05-01 |
| 215 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 225 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 214 | test week 2021-05-08 |
| 216 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 226 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 215 | test week 2021-05-15 |
| 217 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 227 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 216 | test week 2021-05-22 |
| 218 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 228 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 217 | test week 2021-05-29 |
| 219 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 229 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 218 | test week 2021-06-05 |
| 220 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 230 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 219 | test week 2021-06-12 |
| 221 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 231 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 220 | test week 2021-06-19 |
| 222 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 232 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 221 | test week 2021-06-26 |
| 223 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 233 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 222 | test week 2021-07-03 |
| 224 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 234 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 223 | test week 2021-07-10 |
| 225 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 235 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 224 | test week 2021-07-17 |
| 226 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 236 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 225 | test week 2021-07-24 |
| 227 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 237 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 226 | test week 2021-07-31 |
| 228 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 238 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 227 | test week 2021-08-07 |
| 229 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 239 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 228 | test week 2021-08-14 |
| 230 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 240 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 229 | test week 2021-08-21 |
| 231 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 241 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 230 | test week 2021-08-28 |
| 232 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 242 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 231 | test week 2021-09-04 |
| 233 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 243 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 232 | test week 2021-09-11 |
| 234 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 244 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 233 | test week 2021-09-18 |
| 235 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 245 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 234 | test week 2021-09-25 |
| 236 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 246 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 235 | test week 2021-10-02 |
| 237 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 247 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 236 | test week 2021-10-09 |
| 238 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 248 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 237 | test week 2021-10-16 |
| 239 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 249 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 238 | test week 2021-10-23 |
| 240 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 250 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 239 | test week 2021-10-30 |
| 241 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 251 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 240 | test week 2021-11-06 |
| 242 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 252 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 241 | test week 2021-11-13 |
| 243 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 253 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 242 | test week 2021-11-20 |
| 244 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 254 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 243 | test week 2021-11-27 |
| 245 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 255 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 244 | test week 2021-12-04 |
| 246 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 256 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 245 | test week 2021-12-11 |
| 247 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 257 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 246 | test week 2021-12-18 |
| 248 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 258 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 247 | test week 2021-12-25 |
| 249 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 259 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 248 | test week 2022-01-01 |
| 250 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 260 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 249 | test week 2022-01-08 |
| 251 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 261 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 250 | test week 2022-01-15 |
| 252 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 262 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 251 | test week 2022-01-22 |
| 253 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 263 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 252 | test week 2022-01-29 |
| 254 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 264 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 253 | test week 2022-02-05 |
| 255 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 265 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 254 | test week 2022-02-12 |
| 256 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 266 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 255 | test week 2022-02-19 |
| 257 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 267 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 256 | test week 2022-02-26 |
| 258 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 268 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 257 | test week 2022-03-05 |
| 259 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 269 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 258 | test week 2022-03-12 |
| 260 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 270 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 259 | test week 2022-03-19 |
| 261 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 271 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 260 | test week 2022-03-26 |
| 262 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 272 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 261 | test week 2022-04-02 |
| 263 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 273 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 262 | test week 2022-04-09 |
| 264 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 274 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 263 | test week 2022-04-16 |
| 265 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 275 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 264 | test week 2022-04-23 |
| 266 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 276 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 265 | test week 2022-04-30 |
| 267 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 277 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 266 | test week 2022-05-07 |
| 268 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 278 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 267 | test week 2022-05-14 |
| 269 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 279 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 268 | test week 2022-05-21 |
| 270 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 280 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 269 | test week 2022-05-28 |
| 271 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 281 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 270 | test week 2022-06-04 |
| 272 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 282 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 271 | test week 2022-06-11 |
| 273 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 283 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 272 | test week 2022-06-18 |
| 274 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 284 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 273 | test week 2022-06-25 |
| 275 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 285 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 274 | test week 2022-07-02 |
| 276 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 286 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 275 | test week 2022-07-09 |
| 277 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 287 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 276 | test week 2022-07-16 |
| 278 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 288 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 277 | test week 2022-07-23 |
| 279 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 289 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 278 | test week 2022-07-30 |
| 280 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 290 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 279 | test week 2022-08-06 |
| 281 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 291 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 280 | test week 2022-08-13 |
| 282 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 292 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 281 | test week 2022-08-20 |
| 283 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 293 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 282 | test week 2022-08-27 |
| 284 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 294 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 283 | test week 2022-09-03 |
| 285 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 295 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 284 | test week 2022-09-10 |
| 286 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 296 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 285 | test week 2022-09-17 |
| 287 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 297 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 286 | test week 2022-09-24 |
| 288 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 298 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 287 | test week 2022-10-01 |
| 289 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 299 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 288 | test week 2022-10-08 |
| 290 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 300 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 289 | test week 2022-10-15 |
| 291 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 301 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 290 | test week 2022-10-22 |
| 292 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 302 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 291 | test week 2022-10-29 |
| 293 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 303 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 292 | test week 2022-11-05 |
| 294 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 304 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 293 | test week 2022-11-12 |
| 295 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 305 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 294 | test week 2022-11-19 |
| 296 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 306 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 295 | test week 2022-11-26 |
| 297 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 307 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 296 | test week 2022-12-03 |
| 298 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 308 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 297 | test week 2022-12-10 |
| 299 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 309 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 298 | test week 2022-12-17 |
| 300 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 310 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 299 | test week 2022-12-24 |
| 301 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 311 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 300 | test week 2022-12-31 |
| 302 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 312 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 301 | test week 2023-01-07 |
| 303 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 313 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 302 | test week 2023-01-14 |
| 304 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 314 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 303 | test week 2023-01-21 |
| 305 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 315 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 304 | test week 2023-01-28 |
| 306 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 316 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 305 | test week 2023-02-04 |
| 307 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 317 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 306 | test week 2023-02-11 |
| 308 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 318 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 307 | test week 2023-02-18 |
| 309 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 319 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 308 | test week 2023-02-25 |
| 310 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 320 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 309 | test week 2023-03-04 |
| 311 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 321 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 310 | test week 2023-03-11 |
| 312 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 322 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 311 | test week 2023-03-18 |
| 313 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 323 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 312 | test week 2023-03-25 |
| 314 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 324 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 313 | test week 2023-04-01 |
| 315 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 325 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 314 | test week 2023-04-08 |
| 316 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 326 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 315 | test week 2023-04-15 |
| 317 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 327 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 316 | test week 2023-04-22 |
| 318 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 328 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 317 | test week 2023-04-29 |
| 319 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 329 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 318 | test week 2023-05-06 |
| 320 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 330 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 319 | test week 2023-05-13 |
| 321 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 331 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 320 | test week 2023-05-20 |
| 322 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 332 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 321 | test week 2023-05-27 |
| 323 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 333 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 322 | test week 2023-06-03 |
| 324 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 334 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 323 | test week 2023-06-10 |
| 325 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 335 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 324 | test week 2023-06-17 |
| 326 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 336 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 325 | test week 2023-06-24 |
| 327 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 337 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 326 | test week 2023-07-01 |
| 328 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 338 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 327 | test week 2023-07-08 |
| 329 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 339 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 328 | test week 2023-07-15 |
| 330 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 340 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 329 | test week 2023-07-22 |
| 331 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 341 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 330 | test week 2023-07-29 |
| 332 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 342 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 331 | test week 2023-08-05 |
| 333 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 343 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 332 | test week 2023-08-12 |
| 334 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 344 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 333 | test week 2023-08-19 |
| 335 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 345 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 334 | test week 2023-08-26 |
| 336 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 346 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 335 | test week 2023-09-02 |
| 337 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 347 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 336 | test week 2023-09-09 |
| 338 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 348 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 337 | test week 2023-09-16 |
| 339 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 349 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 338 | test week 2023-09-23 |
| 340 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 350 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 339 | test week 2023-09-30 |
| 341 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 351 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 340 | test week 2023-10-07 |
| 342 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 352 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 341 | test week 2023-10-14 |
| 343 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 353 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 342 | test week 2023-10-21 |
| 344 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 354 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 343 | test week 2023-10-28 |
| 345 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 355 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 344 | test week 2023-11-04 |
| 346 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 356 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 345 | test week 2023-11-11 |
| 347 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 357 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 346 | test week 2023-11-18 |
| 348 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 358 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 347 | test week 2023-11-25 |
| 349 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 359 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 348 | test week 2023-12-02 |
| 350 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 360 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 349 | test week 2023-12-09 |
| 351 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 361 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 350 | test week 2023-12-16 |
| 352 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 362 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 351 | test week 2023-12-23 |
| 353 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 363 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 352 | test week 2023-12-30 |
| 354 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 364 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 353 | test week 2024-01-06 |
| 355 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 365 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 354 | test week 2024-01-13 |
| 356 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 366 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 355 | test week 2024-01-20 |
| 357 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 367 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 356 | test week 2024-01-27 |
| 358 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 368 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 357 | test week 2024-02-03 |
| 359 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 369 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 358 | test week 2024-02-10 |
| 360 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 370 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 359 | test week 2024-02-17 |
| 361 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 371 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 360 | test week 2024-02-24 |
| 362 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 372 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 361 | test week 2024-03-02 |
| 363 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 373 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 362 | test week 2024-03-09 |
| 364 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 374 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 363 | test week 2024-03-16 |
| 365 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 375 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 364 | test week 2024-03-23 |
| 366 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 376 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 365 | test week 2024-03-30 |
| 367 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 377 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 366 | test week 2024-04-06 |
| 368 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 378 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 367 | test week 2024-04-13 |
| 369 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 379 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 368 | test week 2024-04-20 |
| 370 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 380 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 369 | test week 2024-04-27 |
| 371 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 381 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 370 | test week 2024-05-04 |
| 372 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 382 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 371 | test week 2024-05-11 |
| 373 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 383 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 372 | test week 2024-05-18 |
| 374 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 384 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 373 | test week 2024-05-25 |
| 375 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 385 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 374 | test week 2024-06-01 |
| 376 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 386 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 375 | test week 2024-06-08 |
| 377 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 387 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 376 | test week 2024-06-15 |
| 378 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 388 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 377 | test week 2024-06-22 |
| 379 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 389 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 378 | test week 2024-06-29 |
| 380 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 390 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 379 | test week 2024-07-06 |
| 381 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 391 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 380 | test week 2024-07-13 |
| 382 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 392 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 381 | test week 2024-07-20 |
| 383 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 393 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 382 | test week 2024-07-27 |
| 384 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 394 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 383 | test week 2024-08-03 |
| 385 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 395 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 384 | test week 2024-08-10 |
| 386 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 396 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 385 | test week 2024-08-17 |
| 387 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 397 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 386 | test week 2024-08-24 |
| 388 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 398 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 387 | test week 2024-08-31 |
| 389 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 399 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 388 | test week 2024-09-07 |
| 390 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 400 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 389 | test week 2024-09-14 |
| 391 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 401 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 390 | test week 2024-09-21 |
| 392 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 402 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 391 | test week 2024-09-28 |
| 393 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 403 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 392 | test week 2024-10-05 |
| 394 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 404 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 393 | test week 2024-10-12 |
| 395 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 405 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 394 | test week 2024-10-19 |
| 396 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 406 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 395 | test week 2024-10-26 |
| 397 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 407 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 396 | test week 2024-11-02 |
| 398 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 408 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 397 | test week 2024-11-09 |
| 399 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 409 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 398 | test week 2024-11-16 |
| 400 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 410 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 399 | test week 2024-11-23 |
| 401 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 411 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 400 | test week 2024-11-30 |
| 402 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 412 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 401 | test week 2024-12-07 |
| 403 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 413 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 402 | test week 2024-12-14 |
| 404 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 414 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 403 | test week 2024-12-21 |
| 405 | leaderboard | docs/dataset/walkforward-folds-2026-09-14.md | line 415 | predictor, walk-forward train-20260913T205245-067b2b9d, fold 404 | test week 2024-12-28 |
| 406 | leaderboard | models/ (gitignored; seen on disk 2026-09-19) | train-20260913T100124-067b2b9d-f0 | predictor, three-pair smoke run, train-20260913T100124-067b2b9d-f0 | evaluated on its own test week |
| 407 | leaderboard | models/ (gitignored; seen on disk 2026-09-19) | train-20260913T100124-067b2b9d-f1 | predictor, three-pair smoke run, train-20260913T100124-067b2b9d-f1 | evaluated on its own test week |
| 408 | leaderboard | models/ (gitignored; seen on disk 2026-09-19) | train-20260913T100124-067b2b9d-f2 | predictor, three-pair smoke run, train-20260913T100124-067b2b9d-f2 | evaluated on its own test week |
| 409 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 4 | q_funnel: 18m, alphabetical, total friction 0.40%, flat 10 bps where the arm says so; gates through anomaly | 20223 pass |
| 410 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 4 | q_funnel: 18m, alphabetical, total friction 0.40%, flat 10 bps where the arm says so; gates through DI | 19807 pass |
| 411 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 4 | q_funnel: 18m, alphabetical, total friction 0.40%, flat 10 bps where the arm says so; gates through cost | 129 pass |
| 412 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 4 | q_funnel: 18m, alphabetical, total friction 0.40%, flat 10 bps where the arm says so; gates through risk | 64 pass |
| 413 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 5 | q_funnel: 18m, alphabetical, total friction 0.40%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 414 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 6 | q_funnel: 18m, alphabetical, total friction 0.40%, uncapped skeptic veto at 0.60, one per pair, at most three open | 17 trades |
| 415 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 7 | q_funnel: 18m, alphabetical, total friction 0.40%, uncapped skeptic veto at 0.70, one per pair, at most three open | 49 trades |
| 416 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 8 | q_funnel: 18m, alphabetical, total friction 0.40%, capped skeptic veto at 0.50, one per pair, at most three open | 35 trades |
| 417 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 9 | q_funnel: 18m, alphabetical, total friction 0.40%, capped skeptic veto at 0.60, one per pair, at most three open | 47 trades |
| 418 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 10 | q_funnel: 18m, alphabetical, total friction 0.40%, capped skeptic veto at 0.70, one per pair, at most three open | 58 trades |
| 419 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 11 | q_funnel: 18m, alphabetical, total friction 0.50%, flat 10 bps where the arm says so; gates through anomaly | 20223 pass |
| 420 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 11 | q_funnel: 18m, alphabetical, total friction 0.50%, flat 10 bps where the arm says so; gates through DI | 19807 pass |
| 421 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 11 | q_funnel: 18m, alphabetical, total friction 0.50%, flat 10 bps where the arm says so; gates through cost | 52 pass |
| 422 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 11 | q_funnel: 18m, alphabetical, total friction 0.50%, flat 10 bps where the arm says so; gates through risk | 24 pass |
| 423 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 12 | q_funnel: 18m, alphabetical, total friction 0.50%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 424 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 13 | q_funnel: 18m, alphabetical, total friction 0.50%, uncapped skeptic veto at 0.60, one per pair, at most three open | 10 trades |
| 425 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 14 | q_funnel: 18m, alphabetical, total friction 0.50%, uncapped skeptic veto at 0.70, one per pair, at most three open | 22 trades |
| 426 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 15 | q_funnel: 18m, alphabetical, total friction 0.50%, capped skeptic veto at 0.50, one per pair, at most three open | 18 trades |
| 427 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 16 | q_funnel: 18m, alphabetical, total friction 0.50%, capped skeptic veto at 0.60, one per pair, at most three open | 20 trades |
| 428 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 17 | q_funnel: 18m, alphabetical, total friction 0.50%, capped skeptic veto at 0.70, one per pair, at most three open | 23 trades |
| 429 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 18 | q_funnel: 18m, alphabetical, total friction 0.60%, flat 10 bps where the arm says so; gates through anomaly | 20223 pass |
| 430 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 18 | q_funnel: 18m, alphabetical, total friction 0.60%, flat 10 bps where the arm says so; gates through DI | 19807 pass |
| 431 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 18 | q_funnel: 18m, alphabetical, total friction 0.60%, flat 10 bps where the arm says so; gates through cost | 31 pass |
| 432 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 18 | q_funnel: 18m, alphabetical, total friction 0.60%, flat 10 bps where the arm says so; gates through risk | 17 pass |
| 433 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 19 | q_funnel: 18m, alphabetical, total friction 0.60%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 434 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 20 | q_funnel: 18m, alphabetical, total friction 0.60%, uncapped skeptic veto at 0.60, one per pair, at most three open | 7 trades |
| 435 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 21 | q_funnel: 18m, alphabetical, total friction 0.60%, uncapped skeptic veto at 0.70, one per pair, at most three open | 16 trades |
| 436 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 22 | q_funnel: 18m, alphabetical, total friction 0.60%, capped skeptic veto at 0.50, one per pair, at most three open | 15 trades |
| 437 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 23 | q_funnel: 18m, alphabetical, total friction 0.60%, capped skeptic veto at 0.60, one per pair, at most three open | 16 trades |
| 438 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 24 | q_funnel: 18m, alphabetical, total friction 0.60%, capped skeptic veto at 0.70, one per pair, at most three open | 17 trades |
| 439 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 25 | q_funnel: 18m, alphabetical, total friction 0.70%, flat 10 bps where the arm says so; gates through anomaly | 20223 pass |
| 440 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 25 | q_funnel: 18m, alphabetical, total friction 0.70%, flat 10 bps where the arm says so; gates through DI | 19807 pass |
| 441 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 25 | q_funnel: 18m, alphabetical, total friction 0.70%, flat 10 bps where the arm says so; gates through cost | 5 pass |
| 442 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 25 | q_funnel: 18m, alphabetical, total friction 0.70%, flat 10 bps where the arm says so; gates through risk | 4 pass |
| 443 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 26 | q_funnel: 18m, alphabetical, total friction 0.70%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 444 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 27 | q_funnel: 18m, alphabetical, total friction 0.70%, uncapped skeptic veto at 0.60, one per pair, at most three open | 3 trades |
| 445 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 28 | q_funnel: 18m, alphabetical, total friction 0.70%, uncapped skeptic veto at 0.70, one per pair, at most three open | 4 trades |
| 446 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 29 | q_funnel: 18m, alphabetical, total friction 0.70%, capped skeptic veto at 0.50, one per pair, at most three open | 4 trades |
| 447 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 30 | q_funnel: 18m, alphabetical, total friction 0.70%, capped skeptic veto at 0.60, one per pair, at most three open | 4 trades |
| 448 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 31 | q_funnel: 18m, alphabetical, total friction 0.70%, capped skeptic veto at 0.70, one per pair, at most three open | 4 trades |
| 449 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 32 | q_funnel: 18m, alphabetical, total friction 0.85%, flat 10 bps where the arm says so; gates through anomaly | 20223 pass |
| 450 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 32 | q_funnel: 18m, alphabetical, total friction 0.85%, flat 10 bps where the arm says so; gates through DI | 19807 pass |
| 451 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 32 | q_funnel: 18m, alphabetical, total friction 0.85%, flat 10 bps where the arm says so; gates through cost | 1 pass |
| 452 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 32 | q_funnel: 18m, alphabetical, total friction 0.85%, flat 10 bps where the arm says so; gates through risk | 1 pass |
| 453 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 33 | q_funnel: 18m, alphabetical, total friction 0.85%, uncapped skeptic veto at 0.50, one per pair, at most three open | 0 trades |
| 454 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 34 | q_funnel: 18m, alphabetical, total friction 0.85%, uncapped skeptic veto at 0.60, one per pair, at most three open | 0 trades |
| 455 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 35 | q_funnel: 18m, alphabetical, total friction 0.85%, uncapped skeptic veto at 0.70, one per pair, at most three open | 1 trades |
| 456 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 36 | q_funnel: 18m, alphabetical, total friction 0.85%, capped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 457 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 37 | q_funnel: 18m, alphabetical, total friction 0.85%, capped skeptic veto at 0.60, one per pair, at most three open | 1 trades |
| 458 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 38 | q_funnel: 18m, alphabetical, total friction 0.85%, capped skeptic veto at 0.70, one per pair, at most three open | 1 trades |
| 459 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 39 | q_funnel: 18m, log_return_4 asc, total friction 0.40%, flat 10 bps where the arm says so; gates through anomaly | 21707 pass |
| 460 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 39 | q_funnel: 18m, log_return_4 asc, total friction 0.40%, flat 10 bps where the arm says so; gates through DI | 21196 pass |
| 461 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 39 | q_funnel: 18m, log_return_4 asc, total friction 0.40%, flat 10 bps where the arm says so; gates through cost | 586 pass |
| 462 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 39 | q_funnel: 18m, log_return_4 asc, total friction 0.40%, flat 10 bps where the arm says so; gates through risk | 494 pass |
| 463 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 40 | q_funnel: 18m, log_return_4 asc, total friction 0.40%, uncapped skeptic veto at 0.50, one per pair, at most three open | 281 trades |
| 464 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 41 | q_funnel: 18m, log_return_4 asc, total friction 0.40%, uncapped skeptic veto at 0.60, one per pair, at most three open | 446 trades |
| 465 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 42 | q_funnel: 18m, log_return_4 asc, total friction 0.40%, uncapped skeptic veto at 0.70, one per pair, at most three open | 492 trades |
| 466 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 43 | q_funnel: 18m, log_return_4 asc, total friction 0.40%, capped skeptic veto at 0.50, one per pair, at most three open | 420 trades |
| 467 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 44 | q_funnel: 18m, log_return_4 asc, total friction 0.40%, capped skeptic veto at 0.60, one per pair, at most three open | 481 trades |
| 468 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 45 | q_funnel: 18m, log_return_4 asc, total friction 0.40%, capped skeptic veto at 0.70, one per pair, at most three open | 492 trades |
| 469 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 46 | q_funnel: 18m, log_return_4 asc, total friction 0.50%, flat 10 bps where the arm says so; gates through anomaly | 21707 pass |
| 470 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 46 | q_funnel: 18m, log_return_4 asc, total friction 0.50%, flat 10 bps where the arm says so; gates through DI | 21196 pass |
| 471 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 46 | q_funnel: 18m, log_return_4 asc, total friction 0.50%, flat 10 bps where the arm says so; gates through cost | 258 pass |
| 472 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 46 | q_funnel: 18m, log_return_4 asc, total friction 0.50%, flat 10 bps where the arm says so; gates through risk | 224 pass |
| 473 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 47 | q_funnel: 18m, log_return_4 asc, total friction 0.50%, uncapped skeptic veto at 0.50, one per pair, at most three open | 136 trades |
| 474 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 48 | q_funnel: 18m, log_return_4 asc, total friction 0.50%, uncapped skeptic veto at 0.60, one per pair, at most three open | 203 trades |
| 475 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 49 | q_funnel: 18m, log_return_4 asc, total friction 0.50%, uncapped skeptic veto at 0.70, one per pair, at most three open | 222 trades |
| 476 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 50 | q_funnel: 18m, log_return_4 asc, total friction 0.50%, capped skeptic veto at 0.50, one per pair, at most three open | 197 trades |
| 477 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 51 | q_funnel: 18m, log_return_4 asc, total friction 0.50%, capped skeptic veto at 0.60, one per pair, at most three open | 218 trades |
| 478 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 52 | q_funnel: 18m, log_return_4 asc, total friction 0.50%, capped skeptic veto at 0.70, one per pair, at most three open | 224 trades |
| 479 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 53 | q_funnel: 18m, log_return_4 asc, total friction 0.60%, flat 10 bps where the arm says so; gates through anomaly | 21707 pass |
| 480 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 53 | q_funnel: 18m, log_return_4 asc, total friction 0.60%, flat 10 bps where the arm says so; gates through DI | 21196 pass |
| 481 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 53 | q_funnel: 18m, log_return_4 asc, total friction 0.60%, flat 10 bps where the arm says so; gates through cost | 100 pass |
| 482 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 53 | q_funnel: 18m, log_return_4 asc, total friction 0.60%, flat 10 bps where the arm says so; gates through risk | 84 pass |
| 483 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 54 | q_funnel: 18m, log_return_4 asc, total friction 0.60%, uncapped skeptic veto at 0.50, one per pair, at most three open | 52 trades |
| 484 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 55 | q_funnel: 18m, log_return_4 asc, total friction 0.60%, uncapped skeptic veto at 0.60, one per pair, at most three open | 76 trades |
| 485 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 56 | q_funnel: 18m, log_return_4 asc, total friction 0.60%, uncapped skeptic veto at 0.70, one per pair, at most three open | 84 trades |
| 486 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 57 | q_funnel: 18m, log_return_4 asc, total friction 0.60%, capped skeptic veto at 0.50, one per pair, at most three open | 79 trades |
| 487 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 58 | q_funnel: 18m, log_return_4 asc, total friction 0.60%, capped skeptic veto at 0.60, one per pair, at most three open | 83 trades |
| 488 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 59 | q_funnel: 18m, log_return_4 asc, total friction 0.60%, capped skeptic veto at 0.70, one per pair, at most three open | 84 trades |
| 489 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 60 | q_funnel: 18m, log_return_4 asc, total friction 0.70%, flat 10 bps where the arm says so; gates through anomaly | 21707 pass |
| 490 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 60 | q_funnel: 18m, log_return_4 asc, total friction 0.70%, flat 10 bps where the arm says so; gates through DI | 21196 pass |
| 491 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 60 | q_funnel: 18m, log_return_4 asc, total friction 0.70%, flat 10 bps where the arm says so; gates through cost | 35 pass |
| 492 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 60 | q_funnel: 18m, log_return_4 asc, total friction 0.70%, flat 10 bps where the arm says so; gates through risk | 30 pass |
| 493 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 61 | q_funnel: 18m, log_return_4 asc, total friction 0.70%, uncapped skeptic veto at 0.50, one per pair, at most three open | 21 trades |
| 494 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 62 | q_funnel: 18m, log_return_4 asc, total friction 0.70%, uncapped skeptic veto at 0.60, one per pair, at most three open | 29 trades |
| 495 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 63 | q_funnel: 18m, log_return_4 asc, total friction 0.70%, uncapped skeptic veto at 0.70, one per pair, at most three open | 30 trades |
| 496 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 64 | q_funnel: 18m, log_return_4 asc, total friction 0.70%, capped skeptic veto at 0.50, one per pair, at most three open | 28 trades |
| 497 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 65 | q_funnel: 18m, log_return_4 asc, total friction 0.70%, capped skeptic veto at 0.60, one per pair, at most three open | 30 trades |
| 498 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 66 | q_funnel: 18m, log_return_4 asc, total friction 0.70%, capped skeptic veto at 0.70, one per pair, at most three open | 30 trades |
| 499 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 67 | q_funnel: 18m, log_return_4 asc, total friction 0.85%, flat 10 bps where the arm says so; gates through anomaly | 21707 pass |
| 500 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 67 | q_funnel: 18m, log_return_4 asc, total friction 0.85%, flat 10 bps where the arm says so; gates through DI | 21196 pass |
| 501 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 67 | q_funnel: 18m, log_return_4 asc, total friction 0.85%, flat 10 bps where the arm says so; gates through cost | 7 pass |
| 502 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 67 | q_funnel: 18m, log_return_4 asc, total friction 0.85%, flat 10 bps where the arm says so; gates through risk | 4 pass |
| 503 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 68 | q_funnel: 18m, log_return_4 asc, total friction 0.85%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 504 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 69 | q_funnel: 18m, log_return_4 asc, total friction 0.85%, uncapped skeptic veto at 0.60, one per pair, at most three open | 4 trades |
| 505 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 70 | q_funnel: 18m, log_return_4 asc, total friction 0.85%, uncapped skeptic veto at 0.70, one per pair, at most three open | 4 trades |
| 506 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 71 | q_funnel: 18m, log_return_4 asc, total friction 0.85%, capped skeptic veto at 0.50, one per pair, at most three open | 4 trades |
| 507 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 72 | q_funnel: 18m, log_return_4 asc, total friction 0.85%, capped skeptic veto at 0.60, one per pair, at most three open | 4 trades |
| 508 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 73 | q_funnel: 18m, log_return_4 asc, total friction 0.85%, capped skeptic veto at 0.70, one per pair, at most three open | 4 trades |
| 509 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 76 | q_funnel: 12m, alphabetical, total friction 0.40%, flat 10 bps where the arm says so; gates through anomaly | 14635 pass |
| 510 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 76 | q_funnel: 12m, alphabetical, total friction 0.40%, flat 10 bps where the arm says so; gates through DI | 14301 pass |
| 511 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 76 | q_funnel: 12m, alphabetical, total friction 0.40%, flat 10 bps where the arm says so; gates through cost | 103 pass |
| 512 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 76 | q_funnel: 12m, alphabetical, total friction 0.40%, flat 10 bps where the arm says so; gates through risk | 50 pass |
| 513 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 77 | q_funnel: 12m, alphabetical, total friction 0.40%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 514 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 78 | q_funnel: 12m, alphabetical, total friction 0.40%, uncapped skeptic veto at 0.60, one per pair, at most three open | 17 trades |
| 515 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 79 | q_funnel: 12m, alphabetical, total friction 0.40%, uncapped skeptic veto at 0.70, one per pair, at most three open | 42 trades |
| 516 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 80 | q_funnel: 12m, alphabetical, total friction 0.40%, capped skeptic veto at 0.50, one per pair, at most three open | 30 trades |
| 517 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 81 | q_funnel: 12m, alphabetical, total friction 0.40%, capped skeptic veto at 0.60, one per pair, at most three open | 36 trades |
| 518 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 82 | q_funnel: 12m, alphabetical, total friction 0.40%, capped skeptic veto at 0.70, one per pair, at most three open | 45 trades |
| 519 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 83 | q_funnel: 12m, alphabetical, total friction 0.50%, flat 10 bps where the arm says so; gates through anomaly | 14635 pass |
| 520 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 83 | q_funnel: 12m, alphabetical, total friction 0.50%, flat 10 bps where the arm says so; gates through DI | 14301 pass |
| 521 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 83 | q_funnel: 12m, alphabetical, total friction 0.50%, flat 10 bps where the arm says so; gates through cost | 51 pass |
| 522 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 83 | q_funnel: 12m, alphabetical, total friction 0.50%, flat 10 bps where the arm says so; gates through risk | 23 pass |
| 523 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 84 | q_funnel: 12m, alphabetical, total friction 0.50%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 524 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 85 | q_funnel: 12m, alphabetical, total friction 0.50%, uncapped skeptic veto at 0.60, one per pair, at most three open | 10 trades |
| 525 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 86 | q_funnel: 12m, alphabetical, total friction 0.50%, uncapped skeptic veto at 0.70, one per pair, at most three open | 21 trades |
| 526 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 87 | q_funnel: 12m, alphabetical, total friction 0.50%, capped skeptic veto at 0.50, one per pair, at most three open | 18 trades |
| 527 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 88 | q_funnel: 12m, alphabetical, total friction 0.50%, capped skeptic veto at 0.60, one per pair, at most three open | 19 trades |
| 528 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 89 | q_funnel: 12m, alphabetical, total friction 0.50%, capped skeptic veto at 0.70, one per pair, at most three open | 22 trades |
| 529 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 90 | q_funnel: 12m, alphabetical, total friction 0.60%, flat 10 bps where the arm says so; gates through anomaly | 14635 pass |
| 530 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 90 | q_funnel: 12m, alphabetical, total friction 0.60%, flat 10 bps where the arm says so; gates through DI | 14301 pass |
| 531 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 90 | q_funnel: 12m, alphabetical, total friction 0.60%, flat 10 bps where the arm says so; gates through cost | 31 pass |
| 532 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 90 | q_funnel: 12m, alphabetical, total friction 0.60%, flat 10 bps where the arm says so; gates through risk | 17 pass |
| 533 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 91 | q_funnel: 12m, alphabetical, total friction 0.60%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 534 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 92 | q_funnel: 12m, alphabetical, total friction 0.60%, uncapped skeptic veto at 0.60, one per pair, at most three open | 7 trades |
| 535 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 93 | q_funnel: 12m, alphabetical, total friction 0.60%, uncapped skeptic veto at 0.70, one per pair, at most three open | 16 trades |
| 536 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 94 | q_funnel: 12m, alphabetical, total friction 0.60%, capped skeptic veto at 0.50, one per pair, at most three open | 15 trades |
| 537 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 95 | q_funnel: 12m, alphabetical, total friction 0.60%, capped skeptic veto at 0.60, one per pair, at most three open | 16 trades |
| 538 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 96 | q_funnel: 12m, alphabetical, total friction 0.60%, capped skeptic veto at 0.70, one per pair, at most three open | 17 trades |
| 539 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 97 | q_funnel: 12m, alphabetical, total friction 0.70%, flat 10 bps where the arm says so; gates through anomaly | 14635 pass |
| 540 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 97 | q_funnel: 12m, alphabetical, total friction 0.70%, flat 10 bps where the arm says so; gates through DI | 14301 pass |
| 541 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 97 | q_funnel: 12m, alphabetical, total friction 0.70%, flat 10 bps where the arm says so; gates through cost | 5 pass |
| 542 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 97 | q_funnel: 12m, alphabetical, total friction 0.70%, flat 10 bps where the arm says so; gates through risk | 4 pass |
| 543 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 98 | q_funnel: 12m, alphabetical, total friction 0.70%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 544 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 99 | q_funnel: 12m, alphabetical, total friction 0.70%, uncapped skeptic veto at 0.60, one per pair, at most three open | 3 trades |
| 545 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 100 | q_funnel: 12m, alphabetical, total friction 0.70%, uncapped skeptic veto at 0.70, one per pair, at most three open | 4 trades |
| 546 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 101 | q_funnel: 12m, alphabetical, total friction 0.70%, capped skeptic veto at 0.50, one per pair, at most three open | 4 trades |
| 547 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 102 | q_funnel: 12m, alphabetical, total friction 0.70%, capped skeptic veto at 0.60, one per pair, at most three open | 4 trades |
| 548 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 103 | q_funnel: 12m, alphabetical, total friction 0.70%, capped skeptic veto at 0.70, one per pair, at most three open | 4 trades |
| 549 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 104 | q_funnel: 12m, alphabetical, total friction 0.85%, flat 10 bps where the arm says so; gates through anomaly | 14635 pass |
| 550 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 104 | q_funnel: 12m, alphabetical, total friction 0.85%, flat 10 bps where the arm says so; gates through DI | 14301 pass |
| 551 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 104 | q_funnel: 12m, alphabetical, total friction 0.85%, flat 10 bps where the arm says so; gates through cost | 1 pass |
| 552 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 104 | q_funnel: 12m, alphabetical, total friction 0.85%, flat 10 bps where the arm says so; gates through risk | 1 pass |
| 553 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 105 | q_funnel: 12m, alphabetical, total friction 0.85%, uncapped skeptic veto at 0.50, one per pair, at most three open | 0 trades |
| 554 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 106 | q_funnel: 12m, alphabetical, total friction 0.85%, uncapped skeptic veto at 0.60, one per pair, at most three open | 0 trades |
| 555 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 107 | q_funnel: 12m, alphabetical, total friction 0.85%, uncapped skeptic veto at 0.70, one per pair, at most three open | 1 trades |
| 556 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 108 | q_funnel: 12m, alphabetical, total friction 0.85%, capped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 557 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 109 | q_funnel: 12m, alphabetical, total friction 0.85%, capped skeptic veto at 0.60, one per pair, at most three open | 1 trades |
| 558 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 110 | q_funnel: 12m, alphabetical, total friction 0.85%, capped skeptic veto at 0.70, one per pair, at most three open | 1 trades |
| 559 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 111 | q_funnel: 12m, log_return_4 asc, total friction 0.40%, flat 10 bps where the arm says so; gates through anomaly | 14588 pass |
| 560 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 111 | q_funnel: 12m, log_return_4 asc, total friction 0.40%, flat 10 bps where the arm says so; gates through DI | 14217 pass |
| 561 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 111 | q_funnel: 12m, log_return_4 asc, total friction 0.40%, flat 10 bps where the arm says so; gates through cost | 385 pass |
| 562 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 111 | q_funnel: 12m, log_return_4 asc, total friction 0.40%, flat 10 bps where the arm says so; gates through risk | 313 pass |
| 563 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 112 | q_funnel: 12m, log_return_4 asc, total friction 0.40%, uncapped skeptic veto at 0.50, one per pair, at most three open | 176 trades |
| 564 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 113 | q_funnel: 12m, log_return_4 asc, total friction 0.40%, uncapped skeptic veto at 0.60, one per pair, at most three open | 278 trades |
| 565 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 114 | q_funnel: 12m, log_return_4 asc, total friction 0.40%, uncapped skeptic veto at 0.70, one per pair, at most three open | 311 trades |
| 566 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 115 | q_funnel: 12m, log_return_4 asc, total friction 0.40%, capped skeptic veto at 0.50, one per pair, at most three open | 287 trades |
| 567 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 116 | q_funnel: 12m, log_return_4 asc, total friction 0.40%, capped skeptic veto at 0.60, one per pair, at most three open | 307 trades |
| 568 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 117 | q_funnel: 12m, log_return_4 asc, total friction 0.40%, capped skeptic veto at 0.70, one per pair, at most three open | 313 trades |
| 569 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 118 | q_funnel: 12m, log_return_4 asc, total friction 0.50%, flat 10 bps where the arm says so; gates through anomaly | 14588 pass |
| 570 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 118 | q_funnel: 12m, log_return_4 asc, total friction 0.50%, flat 10 bps where the arm says so; gates through DI | 14217 pass |
| 571 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 118 | q_funnel: 12m, log_return_4 asc, total friction 0.50%, flat 10 bps where the arm says so; gates through cost | 186 pass |
| 572 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 118 | q_funnel: 12m, log_return_4 asc, total friction 0.50%, flat 10 bps where the arm says so; gates through risk | 156 pass |
| 573 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 119 | q_funnel: 12m, log_return_4 asc, total friction 0.50%, uncapped skeptic veto at 0.50, one per pair, at most three open | 93 trades |
| 574 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 120 | q_funnel: 12m, log_return_4 asc, total friction 0.50%, uncapped skeptic veto at 0.60, one per pair, at most three open | 139 trades |
| 575 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 121 | q_funnel: 12m, log_return_4 asc, total friction 0.50%, uncapped skeptic veto at 0.70, one per pair, at most three open | 154 trades |
| 576 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 122 | q_funnel: 12m, log_return_4 asc, total friction 0.50%, capped skeptic veto at 0.50, one per pair, at most three open | 147 trades |
| 577 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 123 | q_funnel: 12m, log_return_4 asc, total friction 0.50%, capped skeptic veto at 0.60, one per pair, at most three open | 151 trades |
| 578 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 124 | q_funnel: 12m, log_return_4 asc, total friction 0.50%, capped skeptic veto at 0.70, one per pair, at most three open | 156 trades |
| 579 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 125 | q_funnel: 12m, log_return_4 asc, total friction 0.60%, flat 10 bps where the arm says so; gates through anomaly | 14588 pass |
| 580 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 125 | q_funnel: 12m, log_return_4 asc, total friction 0.60%, flat 10 bps where the arm says so; gates through DI | 14217 pass |
| 581 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 125 | q_funnel: 12m, log_return_4 asc, total friction 0.60%, flat 10 bps where the arm says so; gates through cost | 80 pass |
| 582 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 125 | q_funnel: 12m, log_return_4 asc, total friction 0.60%, flat 10 bps where the arm says so; gates through risk | 66 pass |
| 583 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 126 | q_funnel: 12m, log_return_4 asc, total friction 0.60%, uncapped skeptic veto at 0.50, one per pair, at most three open | 40 trades |
| 584 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 127 | q_funnel: 12m, log_return_4 asc, total friction 0.60%, uncapped skeptic veto at 0.60, one per pair, at most three open | 58 trades |
| 585 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 128 | q_funnel: 12m, log_return_4 asc, total friction 0.60%, uncapped skeptic veto at 0.70, one per pair, at most three open | 66 trades |
| 586 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 129 | q_funnel: 12m, log_return_4 asc, total friction 0.60%, capped skeptic veto at 0.50, one per pair, at most three open | 65 trades |
| 587 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 130 | q_funnel: 12m, log_return_4 asc, total friction 0.60%, capped skeptic veto at 0.60, one per pair, at most three open | 65 trades |
| 588 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 131 | q_funnel: 12m, log_return_4 asc, total friction 0.60%, capped skeptic veto at 0.70, one per pair, at most three open | 66 trades |
| 589 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 132 | q_funnel: 12m, log_return_4 asc, total friction 0.70%, flat 10 bps where the arm says so; gates through anomaly | 14588 pass |
| 590 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 132 | q_funnel: 12m, log_return_4 asc, total friction 0.70%, flat 10 bps where the arm says so; gates through DI | 14217 pass |
| 591 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 132 | q_funnel: 12m, log_return_4 asc, total friction 0.70%, flat 10 bps where the arm says so; gates through cost | 29 pass |
| 592 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 132 | q_funnel: 12m, log_return_4 asc, total friction 0.70%, flat 10 bps where the arm says so; gates through risk | 24 pass |
| 593 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 133 | q_funnel: 12m, log_return_4 asc, total friction 0.70%, uncapped skeptic veto at 0.50, one per pair, at most three open | 16 trades |
| 594 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 134 | q_funnel: 12m, log_return_4 asc, total friction 0.70%, uncapped skeptic veto at 0.60, one per pair, at most three open | 23 trades |
| 595 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 135 | q_funnel: 12m, log_return_4 asc, total friction 0.70%, uncapped skeptic veto at 0.70, one per pair, at most three open | 24 trades |
| 596 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 136 | q_funnel: 12m, log_return_4 asc, total friction 0.70%, capped skeptic veto at 0.50, one per pair, at most three open | 24 trades |
| 597 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 137 | q_funnel: 12m, log_return_4 asc, total friction 0.70%, capped skeptic veto at 0.60, one per pair, at most three open | 24 trades |
| 598 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 138 | q_funnel: 12m, log_return_4 asc, total friction 0.70%, capped skeptic veto at 0.70, one per pair, at most three open | 24 trades |
| 599 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 139 | q_funnel: 12m, log_return_4 asc, total friction 0.85%, flat 10 bps where the arm says so; gates through anomaly | 14588 pass |
| 600 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 139 | q_funnel: 12m, log_return_4 asc, total friction 0.85%, flat 10 bps where the arm says so; gates through DI | 14217 pass |
| 601 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 139 | q_funnel: 12m, log_return_4 asc, total friction 0.85%, flat 10 bps where the arm says so; gates through cost | 7 pass |
| 602 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 139 | q_funnel: 12m, log_return_4 asc, total friction 0.85%, flat 10 bps where the arm says so; gates through risk | 4 pass |
| 603 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 140 | q_funnel: 12m, log_return_4 asc, total friction 0.85%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 604 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 141 | q_funnel: 12m, log_return_4 asc, total friction 0.85%, uncapped skeptic veto at 0.60, one per pair, at most three open | 4 trades |
| 605 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 142 | q_funnel: 12m, log_return_4 asc, total friction 0.85%, uncapped skeptic veto at 0.70, one per pair, at most three open | 4 trades |
| 606 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 143 | q_funnel: 12m, log_return_4 asc, total friction 0.85%, capped skeptic veto at 0.50, one per pair, at most three open | 4 trades |
| 607 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 144 | q_funnel: 12m, log_return_4 asc, total friction 0.85%, capped skeptic veto at 0.60, one per pair, at most three open | 4 trades |
| 608 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 145 | q_funnel: 12m, log_return_4 asc, total friction 0.85%, capped skeptic veto at 0.70, one per pair, at most three open | 4 trades |
| 609 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 148 | q_funnel: 6m, alphabetical, total friction 0.40%, flat 10 bps where the arm says so; gates through anomaly | 8831 pass |
| 610 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 148 | q_funnel: 6m, alphabetical, total friction 0.40%, flat 10 bps where the arm says so; gates through DI | 8636 pass |
| 611 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 148 | q_funnel: 6m, alphabetical, total friction 0.40%, flat 10 bps where the arm says so; gates through cost | 53 pass |
| 612 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 148 | q_funnel: 6m, alphabetical, total friction 0.40%, flat 10 bps where the arm says so; gates through risk | 27 pass |
| 613 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 149 | q_funnel: 6m, alphabetical, total friction 0.40%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 614 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 150 | q_funnel: 6m, alphabetical, total friction 0.40%, uncapped skeptic veto at 0.60, one per pair, at most three open | 10 trades |
| 615 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 151 | q_funnel: 6m, alphabetical, total friction 0.40%, uncapped skeptic veto at 0.70, one per pair, at most three open | 23 trades |
| 616 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 152 | q_funnel: 6m, alphabetical, total friction 0.40%, capped skeptic veto at 0.50, one per pair, at most three open | 14 trades |
| 617 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 153 | q_funnel: 6m, alphabetical, total friction 0.40%, capped skeptic veto at 0.60, one per pair, at most three open | 18 trades |
| 618 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 154 | q_funnel: 6m, alphabetical, total friction 0.40%, capped skeptic veto at 0.70, one per pair, at most three open | 23 trades |
| 619 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 155 | q_funnel: 6m, alphabetical, total friction 0.50%, flat 10 bps where the arm says so; gates through anomaly | 8831 pass |
| 620 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 155 | q_funnel: 6m, alphabetical, total friction 0.50%, flat 10 bps where the arm says so; gates through DI | 8636 pass |
| 621 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 155 | q_funnel: 6m, alphabetical, total friction 0.50%, flat 10 bps where the arm says so; gates through cost | 25 pass |
| 622 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 155 | q_funnel: 6m, alphabetical, total friction 0.50%, flat 10 bps where the arm says so; gates through risk | 11 pass |
| 623 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 156 | q_funnel: 6m, alphabetical, total friction 0.50%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 624 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 157 | q_funnel: 6m, alphabetical, total friction 0.50%, uncapped skeptic veto at 0.60, one per pair, at most three open | 5 trades |
| 625 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 158 | q_funnel: 6m, alphabetical, total friction 0.50%, uncapped skeptic veto at 0.70, one per pair, at most three open | 10 trades |
| 626 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 159 | q_funnel: 6m, alphabetical, total friction 0.50%, capped skeptic veto at 0.50, one per pair, at most three open | 6 trades |
| 627 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 160 | q_funnel: 6m, alphabetical, total friction 0.50%, capped skeptic veto at 0.60, one per pair, at most three open | 7 trades |
| 628 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 161 | q_funnel: 6m, alphabetical, total friction 0.50%, capped skeptic veto at 0.70, one per pair, at most three open | 10 trades |
| 629 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 162 | q_funnel: 6m, alphabetical, total friction 0.60%, flat 10 bps where the arm says so; gates through anomaly | 8831 pass |
| 630 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 162 | q_funnel: 6m, alphabetical, total friction 0.60%, flat 10 bps where the arm says so; gates through DI | 8636 pass |
| 631 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 162 | q_funnel: 6m, alphabetical, total friction 0.60%, flat 10 bps where the arm says so; gates through cost | 13 pass |
| 632 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 162 | q_funnel: 6m, alphabetical, total friction 0.60%, flat 10 bps where the arm says so; gates through risk | 6 pass |
| 633 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 163 | q_funnel: 6m, alphabetical, total friction 0.60%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 634 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 164 | q_funnel: 6m, alphabetical, total friction 0.60%, uncapped skeptic veto at 0.60, one per pair, at most three open | 4 trades |
| 635 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 165 | q_funnel: 6m, alphabetical, total friction 0.60%, uncapped skeptic veto at 0.70, one per pair, at most three open | 6 trades |
| 636 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 166 | q_funnel: 6m, alphabetical, total friction 0.60%, capped skeptic veto at 0.50, one per pair, at most three open | 4 trades |
| 637 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 167 | q_funnel: 6m, alphabetical, total friction 0.60%, capped skeptic veto at 0.60, one per pair, at most three open | 5 trades |
| 638 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 168 | q_funnel: 6m, alphabetical, total friction 0.60%, capped skeptic veto at 0.70, one per pair, at most three open | 6 trades |
| 639 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 169 | q_funnel: 6m, alphabetical, total friction 0.70%, flat 10 bps where the arm says so; gates through anomaly | 8831 pass |
| 640 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 169 | q_funnel: 6m, alphabetical, total friction 0.70%, flat 10 bps where the arm says so; gates through DI | 8636 pass |
| 641 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 169 | q_funnel: 6m, alphabetical, total friction 0.70%, flat 10 bps where the arm says so; gates through cost | 2 pass |
| 642 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 169 | q_funnel: 6m, alphabetical, total friction 0.70%, flat 10 bps where the arm says so; gates through risk | 1 pass |
| 643 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 170 | q_funnel: 6m, alphabetical, total friction 0.70%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 644 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 171 | q_funnel: 6m, alphabetical, total friction 0.70%, uncapped skeptic veto at 0.60, one per pair, at most three open | 1 trades |
| 645 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 172 | q_funnel: 6m, alphabetical, total friction 0.70%, uncapped skeptic veto at 0.70, one per pair, at most three open | 1 trades |
| 646 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 173 | q_funnel: 6m, alphabetical, total friction 0.70%, capped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 647 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 174 | q_funnel: 6m, alphabetical, total friction 0.70%, capped skeptic veto at 0.60, one per pair, at most three open | 1 trades |
| 648 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 175 | q_funnel: 6m, alphabetical, total friction 0.70%, capped skeptic veto at 0.70, one per pair, at most three open | 1 trades |
| 649 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 176 | q_funnel: 6m, alphabetical, total friction 0.85%, flat 10 bps where the arm says so; gates through anomaly | 8831 pass |
| 650 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 176 | q_funnel: 6m, alphabetical, total friction 0.85%, flat 10 bps where the arm says so; gates through DI | 8636 pass |
| 651 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 176 | q_funnel: 6m, alphabetical, total friction 0.85%, flat 10 bps where the arm says so; gates through cost | 0 pass |
| 652 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 176 | q_funnel: 6m, alphabetical, total friction 0.85%, flat 10 bps where the arm says so; gates through risk | 0 pass |
| 653 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 177 | q_funnel: 6m, alphabetical, total friction 0.85%, uncapped skeptic veto at 0.50, one per pair, at most three open | 0 trades |
| 654 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 178 | q_funnel: 6m, alphabetical, total friction 0.85%, uncapped skeptic veto at 0.60, one per pair, at most three open | 0 trades |
| 655 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 179 | q_funnel: 6m, alphabetical, total friction 0.85%, uncapped skeptic veto at 0.70, one per pair, at most three open | 0 trades |
| 656 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 180 | q_funnel: 6m, alphabetical, total friction 0.85%, capped skeptic veto at 0.50, one per pair, at most three open | 0 trades |
| 657 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 181 | q_funnel: 6m, alphabetical, total friction 0.85%, capped skeptic veto at 0.60, one per pair, at most three open | 0 trades |
| 658 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 182 | q_funnel: 6m, alphabetical, total friction 0.85%, capped skeptic veto at 0.70, one per pair, at most three open | 0 trades |
| 659 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 183 | q_funnel: 6m, log_return_4 asc, total friction 0.40%, flat 10 bps where the arm says so; gates through anomaly | 6562 pass |
| 660 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 183 | q_funnel: 6m, log_return_4 asc, total friction 0.40%, flat 10 bps where the arm says so; gates through DI | 6395 pass |
| 661 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 183 | q_funnel: 6m, log_return_4 asc, total friction 0.40%, flat 10 bps where the arm says so; gates through cost | 255 pass |
| 662 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 183 | q_funnel: 6m, log_return_4 asc, total friction 0.40%, flat 10 bps where the arm says so; gates through risk | 198 pass |
| 663 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 184 | q_funnel: 6m, log_return_4 asc, total friction 0.40%, uncapped skeptic veto at 0.50, one per pair, at most three open | 99 trades |
| 664 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 185 | q_funnel: 6m, log_return_4 asc, total friction 0.40%, uncapped skeptic veto at 0.60, one per pair, at most three open | 173 trades |
| 665 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 186 | q_funnel: 6m, log_return_4 asc, total friction 0.40%, uncapped skeptic veto at 0.70, one per pair, at most three open | 197 trades |
| 666 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 187 | q_funnel: 6m, log_return_4 asc, total friction 0.40%, capped skeptic veto at 0.50, one per pair, at most three open | 183 trades |
| 667 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 188 | q_funnel: 6m, log_return_4 asc, total friction 0.40%, capped skeptic veto at 0.60, one per pair, at most three open | 192 trades |
| 668 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 189 | q_funnel: 6m, log_return_4 asc, total friction 0.40%, capped skeptic veto at 0.70, one per pair, at most three open | 198 trades |
| 669 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 190 | q_funnel: 6m, log_return_4 asc, total friction 0.50%, flat 10 bps where the arm says so; gates through anomaly | 6562 pass |
| 670 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 190 | q_funnel: 6m, log_return_4 asc, total friction 0.50%, flat 10 bps where the arm says so; gates through DI | 6395 pass |
| 671 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 190 | q_funnel: 6m, log_return_4 asc, total friction 0.50%, flat 10 bps where the arm says so; gates through cost | 135 pass |
| 672 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 190 | q_funnel: 6m, log_return_4 asc, total friction 0.50%, flat 10 bps where the arm says so; gates through risk | 110 pass |
| 673 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 191 | q_funnel: 6m, log_return_4 asc, total friction 0.50%, uncapped skeptic veto at 0.50, one per pair, at most three open | 59 trades |
| 674 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 192 | q_funnel: 6m, log_return_4 asc, total friction 0.50%, uncapped skeptic veto at 0.60, one per pair, at most three open | 98 trades |
| 675 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 193 | q_funnel: 6m, log_return_4 asc, total friction 0.50%, uncapped skeptic veto at 0.70, one per pair, at most three open | 109 trades |
| 676 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 194 | q_funnel: 6m, log_return_4 asc, total friction 0.50%, capped skeptic veto at 0.50, one per pair, at most three open | 102 trades |
| 677 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 195 | q_funnel: 6m, log_return_4 asc, total friction 0.50%, capped skeptic veto at 0.60, one per pair, at most three open | 105 trades |
| 678 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 196 | q_funnel: 6m, log_return_4 asc, total friction 0.50%, capped skeptic veto at 0.70, one per pair, at most three open | 110 trades |
| 679 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 197 | q_funnel: 6m, log_return_4 asc, total friction 0.60%, flat 10 bps where the arm says so; gates through anomaly | 6562 pass |
| 680 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 197 | q_funnel: 6m, log_return_4 asc, total friction 0.60%, flat 10 bps where the arm says so; gates through DI | 6395 pass |
| 681 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 197 | q_funnel: 6m, log_return_4 asc, total friction 0.60%, flat 10 bps where the arm says so; gates through cost | 62 pass |
| 682 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 197 | q_funnel: 6m, log_return_4 asc, total friction 0.60%, flat 10 bps where the arm says so; gates through risk | 49 pass |
| 683 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 198 | q_funnel: 6m, log_return_4 asc, total friction 0.60%, uncapped skeptic veto at 0.50, one per pair, at most three open | 27 trades |
| 684 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 199 | q_funnel: 6m, log_return_4 asc, total friction 0.60%, uncapped skeptic veto at 0.60, one per pair, at most three open | 42 trades |
| 685 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 200 | q_funnel: 6m, log_return_4 asc, total friction 0.60%, uncapped skeptic veto at 0.70, one per pair, at most three open | 49 trades |
| 686 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 201 | q_funnel: 6m, log_return_4 asc, total friction 0.60%, capped skeptic veto at 0.50, one per pair, at most three open | 48 trades |
| 687 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 202 | q_funnel: 6m, log_return_4 asc, total friction 0.60%, capped skeptic veto at 0.60, one per pair, at most three open | 48 trades |
| 688 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 203 | q_funnel: 6m, log_return_4 asc, total friction 0.60%, capped skeptic veto at 0.70, one per pair, at most three open | 49 trades |
| 689 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 204 | q_funnel: 6m, log_return_4 asc, total friction 0.70%, flat 10 bps where the arm says so; gates through anomaly | 6562 pass |
| 690 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 204 | q_funnel: 6m, log_return_4 asc, total friction 0.70%, flat 10 bps where the arm says so; gates through DI | 6395 pass |
| 691 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 204 | q_funnel: 6m, log_return_4 asc, total friction 0.70%, flat 10 bps where the arm says so; gates through cost | 23 pass |
| 692 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 204 | q_funnel: 6m, log_return_4 asc, total friction 0.70%, flat 10 bps where the arm says so; gates through risk | 18 pass |
| 693 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 205 | q_funnel: 6m, log_return_4 asc, total friction 0.70%, uncapped skeptic veto at 0.50, one per pair, at most three open | 10 trades |
| 694 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 206 | q_funnel: 6m, log_return_4 asc, total friction 0.70%, uncapped skeptic veto at 0.60, one per pair, at most three open | 17 trades |
| 695 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 207 | q_funnel: 6m, log_return_4 asc, total friction 0.70%, uncapped skeptic veto at 0.70, one per pair, at most three open | 18 trades |
| 696 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 208 | q_funnel: 6m, log_return_4 asc, total friction 0.70%, capped skeptic veto at 0.50, one per pair, at most three open | 18 trades |
| 697 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 209 | q_funnel: 6m, log_return_4 asc, total friction 0.70%, capped skeptic veto at 0.60, one per pair, at most three open | 18 trades |
| 698 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 210 | q_funnel: 6m, log_return_4 asc, total friction 0.70%, capped skeptic veto at 0.70, one per pair, at most three open | 18 trades |
| 699 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 211 | q_funnel: 6m, log_return_4 asc, total friction 0.85%, flat 10 bps where the arm says so; gates through anomaly | 6562 pass |
| 700 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 211 | q_funnel: 6m, log_return_4 asc, total friction 0.85%, flat 10 bps where the arm says so; gates through DI | 6395 pass |
| 701 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 211 | q_funnel: 6m, log_return_4 asc, total friction 0.85%, flat 10 bps where the arm says so; gates through cost | 7 pass |
| 702 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 211 | q_funnel: 6m, log_return_4 asc, total friction 0.85%, flat 10 bps where the arm says so; gates through risk | 4 pass |
| 703 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 212 | q_funnel: 6m, log_return_4 asc, total friction 0.85%, uncapped skeptic veto at 0.50, one per pair, at most three open | 1 trades |
| 704 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 213 | q_funnel: 6m, log_return_4 asc, total friction 0.85%, uncapped skeptic veto at 0.60, one per pair, at most three open | 4 trades |
| 705 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 214 | q_funnel: 6m, log_return_4 asc, total friction 0.85%, uncapped skeptic veto at 0.70, one per pair, at most three open | 4 trades |
| 706 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 215 | q_funnel: 6m, log_return_4 asc, total friction 0.85%, capped skeptic veto at 0.50, one per pair, at most three open | 4 trades |
| 707 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 216 | q_funnel: 6m, log_return_4 asc, total friction 0.85%, capped skeptic veto at 0.60, one per pair, at most three open | 4 trades |
| 708 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out | line 217 | q_funnel: 6m, log_return_4 asc, total friction 0.85%, capped skeptic veto at 0.70, one per pair, at most three open | 4 trades |
| 709 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 14 | q_window: 2024 reproduction of the alphabetical 1.5% bar count | 71 |
| 710 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 18 | q_window: alphabetical, 18m, tier 3 reference fees, spread 0 bps (total friction 0.60%); (a) clears the cost bar | 74 bars |
| 711 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 18 | q_window: alphabetical, 18m, tier 3 reference fees, spread 0 bps (total friction 0.60%); (b) and one position per pair | 34 trades |
| 712 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 19 | q_window: alphabetical, 18m, upper bound arm (a), reported again with its return | n 74 |
| 713 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 20 | q_window: alphabetical, 18m, upper bound arm (b), reported again with its return | n 34 |
| 714 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 21 | q_window: alphabetical, 18m, tier 3 reference fees, spread 10 bps (total friction 0.70%); (a) clears the cost bar | 29 bars |
| 715 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 21 | q_window: alphabetical, 18m, tier 3 reference fees, spread 10 bps (total friction 0.70%); (b) and one position per pair | 12 trades |
| 716 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 22 | q_window: alphabetical, 18m, upper bound arm (a), reported again with its return | n 29 |
| 717 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 23 | q_window: alphabetical, 18m, upper bound arm (b), reported again with its return | n 12 |
| 718 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 24 | q_window: alphabetical, 18m, tier 3 reference fees, spread 25 bps (total friction 0.85%); (a) clears the cost bar | 10 bars |
| 719 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 24 | q_window: alphabetical, 18m, tier 3 reference fees, spread 25 bps (total friction 0.85%); (b) and one position per pair | 6 trades |
| 720 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 25 | q_window: alphabetical, 18m, upper bound arm (a), reported again with its return | n 10 |
| 721 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 26 | q_window: alphabetical, 18m, upper bound arm (b), reported again with its return | n 6 |
| 722 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.20% | 1961 bars |
| 723 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.25% | 1108 bars |
| 724 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.30% | 659 bars |
| 725 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.35% | 428 bars |
| 726 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.40% | 298 bars |
| 727 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.45% | 197 bars |
| 728 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.50% | 128 bars |
| 729 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.55% | 98 bars |
| 730 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.60% | 74 bars |
| 731 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.65% | 44 bars |
| 732 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.70% | 29 bars |
| 733 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.75% | 19 bars |
| 734 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.80% | 16 bars |
| 735 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.85% | 10 bars |
| 736 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.90% | 2 bars |
| 737 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 0.95% | 1 bars |
| 738 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 1.00% | 0 bars |
| 739 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 1.05% | 0 bars |
| 740 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 1.10% | 0 bars |
| 741 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 1.15% | 0 bars |
| 742 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 29 | q_window: alphabetical, 18m, clears the cost bar at total friction 1.20% | 0 bars |
| 743 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 30 | q_window: 18m, maximum expected move over any pair | 2.8105% |
| 744 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 30 | q_window: 18m, maximum expected move of the alphabetical candidate | 2.4424% |
| 745 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 33 | q_window: alphabetical, 18m, tier 3 reference fees, spread 0 bps; gates through cost | 74 pass |
| 746 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 33 | q_window: alphabetical, 18m, tier 3 reference fees, spread 0 bps; gates through complete vector | 48 pass |
| 747 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 33 | q_window: alphabetical, 18m, tier 3 reference fees, spread 0 bps; gates through anomaly | 47 pass |
| 748 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 33 | q_window: alphabetical, 18m, tier 3 reference fees, spread 0 bps; gates through DI | 31 pass |
| 749 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 33 | q_window: alphabetical, 18m, tier 3 reference fees, spread 0 bps; gates through uncapped skeptic | 2 pass |
| 750 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 33 | q_window: alphabetical, 18m, tier 3 reference fees, spread 0 bps; gates through one per pair | 1 pass |
| 751 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 34 | q_window: alphabetical, 18m, tier 3 reference fees, spread 10 bps; gates through cost | 29 pass |
| 752 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 34 | q_window: alphabetical, 18m, tier 3 reference fees, spread 10 bps; gates through complete vector | 18 pass |
| 753 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 34 | q_window: alphabetical, 18m, tier 3 reference fees, spread 10 bps; gates through anomaly | 18 pass |
| 754 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 34 | q_window: alphabetical, 18m, tier 3 reference fees, spread 10 bps; gates through DI | 5 pass |
| 755 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 34 | q_window: alphabetical, 18m, tier 3 reference fees, spread 10 bps; gates through uncapped skeptic | 2 pass |
| 756 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 34 | q_window: alphabetical, 18m, tier 3 reference fees, spread 10 bps; gates through one per pair | 1 pass |
| 757 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 35 | q_window: alphabetical, 18m, tier 3 reference fees, spread 25 bps; gates through cost | 10 pass |
| 758 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 35 | q_window: alphabetical, 18m, tier 3 reference fees, spread 25 bps; gates through complete vector | 5 pass |
| 759 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 35 | q_window: alphabetical, 18m, tier 3 reference fees, spread 25 bps; gates through anomaly | 5 pass |
| 760 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 35 | q_window: alphabetical, 18m, tier 3 reference fees, spread 25 bps; gates through DI | 1 pass |
| 761 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 35 | q_window: alphabetical, 18m, tier 3 reference fees, spread 25 bps; gates through uncapped skeptic | 0 pass |
| 762 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_window.out | line 35 | q_window: alphabetical, 18m, tier 3 reference fees, spread 25 bps; gates through one per pair | 0 pass |
| 763 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/2026-09-18_q_em.log | line 6 | q_em: all folds, any pair, expected move above 1.250% | 72935 rows |
| 764 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/2026-09-18_q_em.log | line 7 | q_em: all folds, any pair, expected move above 1.500% | 39311 rows |
| 765 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/2026-09-18_q_em.log | line 8 | q_em: all folds, any pair, expected move above 1.550% | 33841 rows |
| 766 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/2026-09-18_q_em.log | line 9 | q_em: all folds, any pair, expected move above 1.625% | 26268 rows |
| 767 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/2026-09-18_q_em.log | line 10 | q_em: all folds, any pair, expected move above 1.750% | 19740 rows |
| 768 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/2026-09-18_q_em.log | line 11 | q_em: all folds, any pair, expected move above 2.000% | 10858 rows |
| 769 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/2026-09-18_q_em.log | line 12 | q_em: all folds, any pair, expected move above 2.500% | 1981 rows |
| 770 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/2026-09-18_q_em.log | line 13 | q_em: all folds, any pair, expected move above 3.000% | 0 rows |
| 771 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/2026-09-18_q_bars.log | line 4 | q_bars: all folds, the best pair on each bar clears 1.500% | 8303 bars |
| 772 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/2026-09-18_q_bars.log | line 5 | q_bars: all folds, the alphabetical candidate clears 1.500% | 938 bars |
| 773 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 1 | q_capped: fold 326 BUY calls, capped skeptic veto at 0.5 | veto share 0.986 |
| 774 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 1 | q_capped: fold 326 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.989 |
| 775 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 2 | q_capped: fold 332 BUY calls, capped skeptic veto at 0.5 | veto share 0.959 |
| 776 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 2 | q_capped: fold 332 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.987 |
| 777 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 3 | q_capped: fold 338 BUY calls, capped skeptic veto at 0.5 | veto share 0.991 |
| 778 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 3 | q_capped: fold 338 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.991 |
| 779 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 4 | q_capped: fold 344 BUY calls, capped skeptic veto at 0.5 | veto share 0.965 |
| 780 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 4 | q_capped: fold 344 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.984 |
| 781 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 5 | q_capped: fold 350 BUY calls, capped skeptic veto at 0.5 | veto share 0.944 |
| 782 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 5 | q_capped: fold 350 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.988 |
| 783 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 6 | q_capped: fold 356 BUY calls, capped skeptic veto at 0.5 | veto share 0.971 |
| 784 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 6 | q_capped: fold 356 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.988 |
| 785 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 7 | q_capped: fold 362 BUY calls, capped skeptic veto at 0.5 | veto share 0.954 |
| 786 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 7 | q_capped: fold 362 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.991 |
| 787 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 8 | q_capped: fold 368 BUY calls, capped skeptic veto at 0.5 | veto share 0.978 |
| 788 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 8 | q_capped: fold 368 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.984 |
| 789 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 9 | q_capped: fold 374 BUY calls, capped skeptic veto at 0.5 | veto share 0.970 |
| 790 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 9 | q_capped: fold 374 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.989 |
| 791 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 10 | q_capped: fold 380 BUY calls, capped skeptic veto at 0.5 | veto share 0.974 |
| 792 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 10 | q_capped: fold 380 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.984 |
| 793 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 11 | q_capped: fold 386 BUY calls, capped skeptic veto at 0.5 | veto share 0.966 |
| 794 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 11 | q_capped: fold 386 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.986 |
| 795 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 12 | q_capped: fold 392 BUY calls, capped skeptic veto at 0.5 | veto share 0.990 |
| 796 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 12 | q_capped: fold 392 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.990 |
| 797 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 13 | q_capped: fold 398 BUY calls, capped skeptic veto at 0.5 | veto share 0.939 |
| 798 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 13 | q_capped: fold 398 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.987 |
| 799 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 14 | q_capped: fold 404 BUY calls, capped skeptic veto at 0.5 | veto share 0.993 |
| 800 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_0.txt | line 14 | q_capped: fold 404 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.993 |
| 801 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 1 | q_capped: fold 327 BUY calls, capped skeptic veto at 0.5 | veto share 0.980 |
| 802 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 1 | q_capped: fold 327 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.984 |
| 803 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 2 | q_capped: fold 333 BUY calls, capped skeptic veto at 0.5 | veto share 0.986 |
| 804 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 2 | q_capped: fold 333 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.986 |
| 805 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 3 | q_capped: fold 339 BUY calls, capped skeptic veto at 0.5 | veto share 0.986 |
| 806 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 3 | q_capped: fold 339 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.988 |
| 807 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 4 | q_capped: fold 345 BUY calls, capped skeptic veto at 0.5 | veto share 0.934 |
| 808 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 4 | q_capped: fold 345 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.985 |
| 809 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 5 | q_capped: fold 351 BUY calls, capped skeptic veto at 0.5 | veto share 0.978 |
| 810 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 5 | q_capped: fold 351 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.986 |
| 811 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 6 | q_capped: fold 357 BUY calls, capped skeptic veto at 0.5 | veto share 0.981 |
| 812 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 6 | q_capped: fold 357 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.989 |
| 813 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 7 | q_capped: fold 363 BUY calls, capped skeptic veto at 0.5 | veto share 0.867 |
| 814 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 7 | q_capped: fold 363 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.982 |
| 815 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 8 | q_capped: fold 369 BUY calls, capped skeptic veto at 0.5 | veto share 0.924 |
| 816 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 8 | q_capped: fold 369 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.982 |
| 817 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 9 | q_capped: fold 375 BUY calls, capped skeptic veto at 0.5 | veto share 0.976 |
| 818 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 9 | q_capped: fold 375 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.985 |
| 819 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 10 | q_capped: fold 381 BUY calls, capped skeptic veto at 0.5 | veto share 0.964 |
| 820 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 10 | q_capped: fold 381 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.988 |
| 821 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 11 | q_capped: fold 387 BUY calls, capped skeptic veto at 0.5 | veto share 0.979 |
| 822 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 11 | q_capped: fold 387 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.989 |
| 823 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 12 | q_capped: fold 393 BUY calls, capped skeptic veto at 0.5 | veto share 0.964 |
| 824 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 12 | q_capped: fold 393 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.977 |
| 825 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 13 | q_capped: fold 399 BUY calls, capped skeptic veto at 0.5 | veto share 0.869 |
| 826 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_1.txt | line 13 | q_capped: fold 399 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.983 |
| 827 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 1 | q_capped: fold 328 BUY calls, capped skeptic veto at 0.5 | veto share 0.987 |
| 828 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 1 | q_capped: fold 328 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.991 |
| 829 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 2 | q_capped: fold 334 BUY calls, capped skeptic veto at 0.5 | veto share 0.944 |
| 830 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 2 | q_capped: fold 334 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.973 |
| 831 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 3 | q_capped: fold 340 BUY calls, capped skeptic veto at 0.5 | veto share 0.983 |
| 832 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 3 | q_capped: fold 340 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.991 |
| 833 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 4 | q_capped: fold 346 BUY calls, capped skeptic veto at 0.5 | veto share 0.936 |
| 834 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 4 | q_capped: fold 346 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.987 |
| 835 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 5 | q_capped: fold 352 BUY calls, capped skeptic veto at 0.5 | veto share 0.907 |
| 836 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 5 | q_capped: fold 352 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.986 |
| 837 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 6 | q_capped: fold 358 BUY calls, capped skeptic veto at 0.5 | veto share 0.984 |
| 838 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 6 | q_capped: fold 358 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.990 |
| 839 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 7 | q_capped: fold 364 BUY calls, capped skeptic veto at 0.5 | veto share 0.961 |
| 840 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 7 | q_capped: fold 364 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.976 |
| 841 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 8 | q_capped: fold 370 BUY calls, capped skeptic veto at 0.5 | veto share 0.986 |
| 842 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 8 | q_capped: fold 370 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.994 |
| 843 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 9 | q_capped: fold 376 BUY calls, capped skeptic veto at 0.5 | veto share 0.971 |
| 844 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 9 | q_capped: fold 376 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.973 |
| 845 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 10 | q_capped: fold 382 BUY calls, capped skeptic veto at 0.5 | veto share 0.964 |
| 846 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 10 | q_capped: fold 382 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.989 |
| 847 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 11 | q_capped: fold 388 BUY calls, capped skeptic veto at 0.5 | veto share 0.948 |
| 848 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 11 | q_capped: fold 388 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.969 |
| 849 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 12 | q_capped: fold 394 BUY calls, capped skeptic veto at 0.5 | veto share 0.960 |
| 850 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 12 | q_capped: fold 394 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.983 |
| 851 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 13 | q_capped: fold 400 BUY calls, capped skeptic veto at 0.5 | veto share 0.891 |
| 852 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_2.txt | line 13 | q_capped: fold 400 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.984 |
| 853 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 1 | q_capped: fold 329 BUY calls, capped skeptic veto at 0.5 | veto share 0.988 |
| 854 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 1 | q_capped: fold 329 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.990 |
| 855 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 2 | q_capped: fold 335 BUY calls, capped skeptic veto at 0.5 | veto share 0.973 |
| 856 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 2 | q_capped: fold 335 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.973 |
| 857 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 3 | q_capped: fold 341 BUY calls, capped skeptic veto at 0.5 | veto share 0.979 |
| 858 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 3 | q_capped: fold 341 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.982 |
| 859 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 4 | q_capped: fold 347 BUY calls, capped skeptic veto at 0.5 | veto share 0.945 |
| 860 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 4 | q_capped: fold 347 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.988 |
| 861 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 5 | q_capped: fold 353 BUY calls, capped skeptic veto at 0.5 | veto share 0.904 |
| 862 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 5 | q_capped: fold 353 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.986 |
| 863 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 6 | q_capped: fold 359 BUY calls, capped skeptic veto at 0.5 | veto share 0.984 |
| 864 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 6 | q_capped: fold 359 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.991 |
| 865 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 7 | q_capped: fold 365 BUY calls, capped skeptic veto at 0.5 | veto share 0.956 |
| 866 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 7 | q_capped: fold 365 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.982 |
| 867 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 8 | q_capped: fold 371 BUY calls, capped skeptic veto at 0.5 | veto share 0.987 |
| 868 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 8 | q_capped: fold 371 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.991 |
| 869 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 9 | q_capped: fold 377 BUY calls, capped skeptic veto at 0.5 | veto share 0.956 |
| 870 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 9 | q_capped: fold 377 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.971 |
| 871 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 10 | q_capped: fold 383 BUY calls, capped skeptic veto at 0.5 | veto share 0.581 |
| 872 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 10 | q_capped: fold 383 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.924 |
| 873 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 11 | q_capped: fold 389 BUY calls, capped skeptic veto at 0.5 | veto share 0.973 |
| 874 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 11 | q_capped: fold 389 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.985 |
| 875 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 12 | q_capped: fold 395 BUY calls, capped skeptic veto at 0.5 | veto share 0.962 |
| 876 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 12 | q_capped: fold 395 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.983 |
| 877 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 13 | q_capped: fold 401 BUY calls, capped skeptic veto at 0.5 | veto share 0.864 |
| 878 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_3.txt | line 13 | q_capped: fold 401 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.985 |
| 879 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 1 | q_capped: fold 330 BUY calls, capped skeptic veto at 0.5 | veto share 0.983 |
| 880 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 1 | q_capped: fold 330 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.983 |
| 881 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 2 | q_capped: fold 336 BUY calls, capped skeptic veto at 0.5 | veto share 0.991 |
| 882 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 2 | q_capped: fold 336 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.993 |
| 883 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 3 | q_capped: fold 342 BUY calls, capped skeptic veto at 0.5 | veto share 0.977 |
| 884 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 3 | q_capped: fold 342 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.985 |
| 885 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 4 | q_capped: fold 348 BUY calls, capped skeptic veto at 0.5 | veto share 0.964 |
| 886 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 4 | q_capped: fold 348 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.976 |
| 887 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 5 | q_capped: fold 354 BUY calls, capped skeptic veto at 0.5 | veto share 0.933 |
| 888 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 5 | q_capped: fold 354 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.986 |
| 889 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 6 | q_capped: fold 360 BUY calls, capped skeptic veto at 0.5 | veto share 0.927 |
| 890 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 6 | q_capped: fold 360 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.982 |
| 891 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 7 | q_capped: fold 366 BUY calls, capped skeptic veto at 0.5 | veto share 0.890 |
| 892 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 7 | q_capped: fold 366 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.977 |
| 893 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 8 | q_capped: fold 372 BUY calls, capped skeptic veto at 0.5 | veto share 0.960 |
| 894 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 8 | q_capped: fold 372 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.991 |
| 895 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 9 | q_capped: fold 378 BUY calls, capped skeptic veto at 0.5 | veto share 0.816 |
| 896 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 9 | q_capped: fold 378 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.956 |
| 897 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 10 | q_capped: fold 384 BUY calls, capped skeptic veto at 0.5 | veto share 0.927 |
| 898 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 10 | q_capped: fold 384 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.968 |
| 899 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 11 | q_capped: fold 390 BUY calls, capped skeptic veto at 0.5 | veto share 0.989 |
| 900 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 11 | q_capped: fold 390 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.993 |
| 901 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 12 | q_capped: fold 396 BUY calls, capped skeptic veto at 0.5 | veto share 0.927 |
| 902 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 12 | q_capped: fold 396 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.954 |
| 903 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 13 | q_capped: fold 402 BUY calls, capped skeptic veto at 0.5 | veto share 0.846 |
| 904 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_4.txt | line 13 | q_capped: fold 402 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.980 |
| 905 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 1 | q_capped: fold 331 BUY calls, capped skeptic veto at 0.5 | veto share 0.988 |
| 906 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 1 | q_capped: fold 331 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.990 |
| 907 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 2 | q_capped: fold 337 BUY calls, capped skeptic veto at 0.5 | veto share 0.986 |
| 908 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 2 | q_capped: fold 337 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.994 |
| 909 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 3 | q_capped: fold 343 BUY calls, capped skeptic veto at 0.5 | veto share 0.980 |
| 910 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 3 | q_capped: fold 343 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.990 |
| 911 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 4 | q_capped: fold 349 BUY calls, capped skeptic veto at 0.5 | veto share 0.944 |
| 912 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 4 | q_capped: fold 349 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.979 |
| 913 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 5 | q_capped: fold 355 BUY calls, capped skeptic veto at 0.5 | veto share 0.891 |
| 914 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 5 | q_capped: fold 355 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.983 |
| 915 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 6 | q_capped: fold 361 BUY calls, capped skeptic veto at 0.5 | veto share 0.907 |
| 916 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 6 | q_capped: fold 361 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.984 |
| 917 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 7 | q_capped: fold 367 BUY calls, capped skeptic veto at 0.5 | veto share 0.710 |
| 918 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 7 | q_capped: fold 367 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.935 |
| 919 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 8 | q_capped: fold 373 BUY calls, capped skeptic veto at 0.5 | veto share 0.908 |
| 920 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 8 | q_capped: fold 373 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.986 |
| 921 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 9 | q_capped: fold 379 BUY calls, capped skeptic veto at 0.5 | veto share 0.883 |
| 922 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 9 | q_capped: fold 379 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.954 |
| 923 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 10 | q_capped: fold 385 BUY calls, capped skeptic veto at 0.5 | veto share 0.908 |
| 924 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 10 | q_capped: fold 385 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.957 |
| 925 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 11 | q_capped: fold 391 BUY calls, capped skeptic veto at 0.5 | veto share 0.972 |
| 926 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 11 | q_capped: fold 391 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.995 |
| 927 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 12 | q_capped: fold 397 BUY calls, capped skeptic veto at 0.5 | veto share 0.907 |
| 928 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 12 | q_capped: fold 397 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.978 |
| 929 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 13 | q_capped: fold 403 BUY calls, capped skeptic veto at 0.5 | veto share 0.627 |
| 930 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/q_capped_log_5.txt | line 13 | q_capped: fold 403 BUY calls, uncapped skeptic veto at 0.5 | veto share 0.974 |
| 931 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 15 | q_year: final 365 days, alphabetical-candidate clears 1.5% | 71 bars |
| 932 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 16 | q_year: final 365 days, any-pair clears 1.5% | 2195 bars |
| 933 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 22 | q_net: all years, alphabetical candidate clears 1.5%, spread 0 bps | 938 trades |
| 934 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 23 | q_net: all years, alphabetical candidate clears 1.5%, spread 5 bps | 681 trades |
| 935 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 24 | q_net: all years, alphabetical candidate clears 1.5%, spread 10 bps | 541 trades |
| 936 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 25 | q_net: all years, alphabetical candidate clears 1.5%, spread 25 bps | 253 trades |
| 937 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 26 | q_net: 2024, alphabetical candidate clears 1.5%, spread 0 bps | 71 trades |
| 938 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 27 | q_net: 2024, alphabetical candidate clears 1.5%, spread 5 bps | 43 trades |
| 939 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 28 | q_net: 2024, alphabetical candidate clears 1.5%, spread 10 bps | 29 trades |
| 940 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 29 | q_net: 2024, alphabetical candidate clears 1.5%, spread 25 bps | 10 trades |
| 941 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 34 | q_hold: alphabetical, 18m, total friction 0.30%, one position per pair | 267 trades |
| 942 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 35 | q_hold: alphabetical, 18m, total friction 0.35%, one position per pair | 187 trades |
| 943 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 36 | q_hold: alphabetical, 18m, total friction 0.40%, one position per pair | 127 trades |
| 944 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 37 | q_hold: alphabetical, 18m, total friction 0.45%, one position per pair | 87 trades |
| 945 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 38 | q_hold: alphabetical, 18m, total friction 0.50%, one position per pair | 55 trades |
| 946 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 39 | q_hold: alphabetical, 18m, total friction 0.55%, one position per pair | 43 trades |
| 947 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 40 | q_hold: alphabetical, 18m, total friction 0.60%, one position per pair | 34 trades |
| 948 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 41 | q_hold: alphabetical, 18m, total friction 0.70%, one position per pair | 12 trades |
| 949 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 42 | q_hold: alphabetical, 18m, total friction 0.85%, one position per pair | 6 trades |
| 950 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 126 | q_capped_compare: 18m BUY calls, uncapped skeptic veto at 0.5 | 58720 survive |
| 951 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 127 | q_capped_compare: 18m BUY calls, capped skeptic veto at 0.5 | 233371 survive |
| 952 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 128 | q_capped_compare: 18m BUY calls, uncapped skeptic veto at 0.6 | 222343 survive |
| 953 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 129 | q_capped_compare: 18m BUY calls, capped skeptic veto at 0.6 | 648670 survive |
| 954 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 130 | q_capped_compare: 18m BUY calls, uncapped skeptic veto at 0.7 | 1260510 survive |
| 955 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 131 | q_capped_compare: 18m BUY calls, capped skeptic veto at 0.7 | 1571388 survive |
| 956 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 132 | q_capped_compare: 18m BUY calls surviving both skeptics at 0.5 | 49032 survive |
| 957 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 138 | q_picks: log_return_4 asc, flat 10 bps, total friction 0.60%, 12m; every trade | 65 trades |
| 958 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 138 | q_picks: log_return_4 asc, flat 10 bps, total friction 0.60%, 12m; trades on a recorded pair | 11 trades |
| 959 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 138 | q_picks: log_return_4 asc, flat 10 bps, total friction 0.60%, 12m; trades on an unrecorded pair | net reported |
| 960 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 140 | q_picks: log_return_4 asc, flat 10 bps, total friction 0.60%, 18m; every trade | 79 trades |
| 961 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 140 | q_picks: log_return_4 asc, flat 10 bps, total friction 0.60%, 18m; trades on a recorded pair | 11 trades |
| 962 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 140 | q_picks: log_return_4 asc, flat 10 bps, total friction 0.60%, 18m; trades on an unrecorded pair | net reported |
| 963 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 142 | q_picks: log_return_4 asc, flat 10 bps, total friction 0.70%, 12m; every trade | 24 trades |
| 964 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 142 | q_picks: log_return_4 asc, flat 10 bps, total friction 0.70%, 12m; trades on a recorded pair | 3 trades |
| 965 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 142 | q_picks: log_return_4 asc, flat 10 bps, total friction 0.70%, 12m; trades on an unrecorded pair | net reported |
| 966 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 144 | q_picks: log_return_4 asc, flat 10 bps, total friction 0.70%, 18m; every trade | 28 trades |
| 967 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 144 | q_picks: log_return_4 asc, flat 10 bps, total friction 0.70%, 18m; trades on a recorded pair | 3 trades |
| 968 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 144 | q_picks: log_return_4 asc, flat 10 bps, total friction 0.70%, 18m; trades on an unrecorded pair | net reported |
| 969 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 157 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 6m; gates through anomaly | 8831 pass |
| 970 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 157 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 6m; gates through DI | 8636 pass |
| 971 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 157 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 6m; gates through cost | 0 pass |
| 972 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 157 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 6m; gates through risk | 0 pass |
| 973 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 157 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 6m; gates through capped skeptic at 0.50 | 0 pass |
| 974 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 158 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 12m; gates through anomaly | 14635 pass |
| 975 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 158 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 12m; gates through DI | 14301 pass |
| 976 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 158 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 12m; gates through cost | 1 pass |
| 977 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 158 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 12m; gates through risk | 1 pass |
| 978 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 158 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 12m; gates through capped skeptic at 0.50 | 1 pass |
| 979 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 159 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 18m; gates through anomaly | 20223 pass |
| 980 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 159 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 18m; gates through DI | 19807 pass |
| 981 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 159 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 18m; gates through cost | 1 pass |
| 982 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 159 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 18m; gates through risk | 1 pass |
| 983 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 159 | q_bucket: alphabetical, fees 0.60%, declared bucket spread and slippage, 18m; gates through capped skeptic at 0.50 | 1 pass |
| 984 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 160 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 6m; gates through anomaly | 8831 pass |
| 985 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 160 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 6m; gates through DI | 8636 pass |
| 986 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 160 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 6m; gates through cost | 3 pass |
| 987 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 160 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 6m; gates through risk | 3 pass |
| 988 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 160 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 6m; gates through capped skeptic at 0.50 | 1 pass |
| 989 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 161 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 12m; gates through anomaly | 14635 pass |
| 990 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 161 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 12m; gates through DI | 14301 pass |
| 991 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 161 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 12m; gates through cost | 5 pass |
| 992 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 161 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 12m; gates through risk | 5 pass |
| 993 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 161 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 12m; gates through capped skeptic at 0.50 | 3 pass |
| 994 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 162 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 18m; gates through anomaly | 20223 pass |
| 995 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 162 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 18m; gates through DI | 19807 pass |
| 996 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 162 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 18m; gates through cost | 5 pass |
| 997 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 162 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 18m; gates through risk | 5 pass |
| 998 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 162 | q_bucket: alphabetical, fees 0.50%, declared bucket spread and slippage, 18m; gates through capped skeptic at 0.50 | 3 pass |
| 999 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 163 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 6m; gates through anomaly | 8831 pass |
| 1000 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 163 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 6m; gates through DI | 8636 pass |
| 1001 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 163 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 6m; gates through cost | 15 pass |
| 1002 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 163 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 6m; gates through risk | 15 pass |
| 1003 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 163 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 6m; gates through capped skeptic at 0.50 | 3 pass |
| 1004 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 164 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 12m; gates through anomaly | 14635 pass |
| 1005 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 164 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 12m; gates through DI | 14301 pass |
| 1006 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 164 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 12m; gates through cost | 31 pass |
| 1007 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 164 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 12m; gates through risk | 24 pass |
| 1008 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 164 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 12m; gates through capped skeptic at 0.50 | 12 pass |
| 1009 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 165 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 18m; gates through anomaly | 20223 pass |
| 1010 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 165 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 18m; gates through DI | 19807 pass |
| 1011 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 165 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 18m; gates through cost | 31 pass |
| 1012 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 165 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 18m; gates through risk | 24 pass |
| 1013 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 165 | q_bucket: alphabetical, fees 0.40%, declared bucket spread and slippage, 18m; gates through capped skeptic at 0.50 | 12 pass |
| 1014 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 168 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 6m; gates through anomaly | 6562 pass |
| 1015 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 168 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 6m; gates through DI | 6395 pass |
| 1016 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 168 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 6m; gates through cost | 0 pass |
| 1017 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 168 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 6m; gates through risk | 0 pass |
| 1018 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 168 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 6m; gates through capped skeptic at 0.50 | 0 pass |
| 1019 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 169 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 12m; gates through anomaly | 14588 pass |
| 1020 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 169 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 12m; gates through DI | 14217 pass |
| 1021 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 169 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 12m; gates through cost | 3 pass |
| 1022 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 169 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 12m; gates through risk | 3 pass |
| 1023 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 169 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 12m; gates through capped skeptic at 0.50 | 3 pass |
| 1024 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 170 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 18m; gates through anomaly | 21707 pass |
| 1025 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 170 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 18m; gates through DI | 21196 pass |
| 1026 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 170 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 18m; gates through cost | 4 pass |
| 1027 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 170 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 18m; gates through risk | 4 pass |
| 1028 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 170 | q_bucket: log_return_4 asc, fees 0.60%, declared bucket spread and slippage, 18m; gates through capped skeptic at 0.50 | 3 pass |
| 1029 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 171 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 6m; gates through anomaly | 6562 pass |
| 1030 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 171 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 6m; gates through DI | 6395 pass |
| 1031 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 171 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 6m; gates through cost | 14 pass |
| 1032 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 171 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 6m; gates through risk | 13 pass |
| 1033 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 171 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 6m; gates through capped skeptic at 0.50 | 12 pass |
| 1034 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 172 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 12m; gates through anomaly | 14588 pass |
| 1035 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 172 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 12m; gates through DI | 14217 pass |
| 1036 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 172 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 12m; gates through cost | 27 pass |
| 1037 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 172 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 12m; gates through risk | 24 pass |
| 1038 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 172 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 12m; gates through capped skeptic at 0.50 | 23 pass |
| 1039 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 173 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 18m; gates through anomaly | 21707 pass |
| 1040 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 173 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 18m; gates through DI | 21196 pass |
| 1041 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 173 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 18m; gates through cost | 33 pass |
| 1042 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 173 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 18m; gates through risk | 29 pass |
| 1043 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 173 | q_bucket: log_return_4 asc, fees 0.50%, declared bucket spread and slippage, 18m; gates through capped skeptic at 0.50 | 26 pass |
| 1044 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 174 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 6m; gates through anomaly | 6562 pass |
| 1045 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 174 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 6m; gates through DI | 6395 pass |
| 1046 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 174 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 6m; gates through cost | 49 pass |
| 1047 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 174 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 6m; gates through risk | 39 pass |
| 1048 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 174 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 6m; gates through capped skeptic at 0.50 | 36 pass |
| 1049 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 175 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 12m; gates through anomaly | 14588 pass |
| 1050 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 175 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 12m; gates through DI | 14217 pass |
| 1051 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 175 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 12m; gates through cost | 75 pass |
| 1052 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 175 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 12m; gates through risk | 62 pass |
| 1053 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 175 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 12m; gates through capped skeptic at 0.50 | 58 pass |
| 1054 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 176 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 18m; gates through anomaly | 21707 pass |
| 1055 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 176 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 18m; gates through DI | 21196 pass |
| 1056 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 176 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 18m; gates through cost | 96 pass |
| 1057 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 176 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 18m; gates through risk | 81 pass |
| 1058 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 176 | q_bucket: log_return_4 asc, fees 0.40%, declared bucket spread and slippage, 18m; gates through capped skeptic at 0.50 | 71 pass |
| 1059 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 181 | q_emrank: ranked by expected_move, fees 0.60%, declared bucket spread and slippage, 6m; clears the cost gate | 26 bars |
| 1060 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 181 | q_emrank: ranked by expected_move, fees 0.60%, declared bucket spread and slippage, 6m; capped skeptic at 0.50, one per pair, at most three open | 22 trades |
| 1061 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 182 | q_emrank: ranked by expected_move, fees 0.60%, declared bucket spread and slippage, 12m; clears the cost gate | 55 bars |
| 1062 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 182 | q_emrank: ranked by expected_move, fees 0.60%, declared bucket spread and slippage, 12m; capped skeptic at 0.50, one per pair, at most three open | 46 trades |
| 1063 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 183 | q_emrank: ranked by net_margin, fees 0.60%, declared bucket spread and slippage, 6m; clears the cost gate | 33 bars |
| 1064 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 183 | q_emrank: ranked by net_margin, fees 0.60%, declared bucket spread and slippage, 6m; capped skeptic at 0.50, one per pair, at most three open | 28 trades |
| 1065 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 184 | q_emrank: ranked by net_margin, fees 0.60%, declared bucket spread and slippage, 12m; clears the cost gate | 70 bars |
| 1066 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 184 | q_emrank: ranked by net_margin, fees 0.60%, declared bucket spread and slippage, 12m; capped skeptic at 0.50, one per pair, at most three open | 55 trades |
| 1067 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 185 | q_emrank: ranked by expected_move, fees 0.50%, declared bucket spread and slippage, 6m; clears the cost gate | 107 bars |
| 1068 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 185 | q_emrank: ranked by expected_move, fees 0.50%, declared bucket spread and slippage, 6m; capped skeptic at 0.50, one per pair, at most three open | 71 trades |
| 1069 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 186 | q_emrank: ranked by expected_move, fees 0.50%, declared bucket spread and slippage, 12m; clears the cost gate | 182 bars |
| 1070 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 186 | q_emrank: ranked by expected_move, fees 0.50%, declared bucket spread and slippage, 12m; capped skeptic at 0.50, one per pair, at most three open | 119 trades |
| 1071 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 187 | q_emrank: ranked by net_margin, fees 0.50%, declared bucket spread and slippage, 6m; clears the cost gate | 167 bars |
| 1072 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 187 | q_emrank: ranked by net_margin, fees 0.50%, declared bucket spread and slippage, 6m; capped skeptic at 0.50, one per pair, at most three open | 83 trades |
| 1073 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 188 | q_emrank: ranked by net_margin, fees 0.50%, declared bucket spread and slippage, 12m; clears the cost gate | 280 bars |
| 1074 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 188 | q_emrank: ranked by net_margin, fees 0.50%, declared bucket spread and slippage, 12m; capped skeptic at 0.50, one per pair, at most three open | 145 trades |
| 1075 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 189 | q_emrank: ranked by expected_move, fees 0.40%, declared bucket spread and slippage, 6m; clears the cost gate | 270 bars |
| 1076 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 189 | q_emrank: ranked by expected_move, fees 0.40%, declared bucket spread and slippage, 6m; capped skeptic at 0.50, one per pair, at most three open | 150 trades |
| 1077 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 190 | q_emrank: ranked by expected_move, fees 0.40%, declared bucket spread and slippage, 12m; clears the cost gate | 443 bars |
| 1078 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 190 | q_emrank: ranked by expected_move, fees 0.40%, declared bucket spread and slippage, 12m; capped skeptic at 0.50, one per pair, at most three open | 254 trades |
| 1079 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 191 | q_emrank: ranked by net_margin, fees 0.40%, declared bucket spread and slippage, 6m; clears the cost gate | 358 bars |
| 1080 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 191 | q_emrank: ranked by net_margin, fees 0.40%, declared bucket spread and slippage, 6m; capped skeptic at 0.50, one per pair, at most three open | 173 trades |
| 1081 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 192 | q_emrank: ranked by net_margin, fees 0.40%, declared bucket spread and slippage, 12m; clears the cost gate | 565 bars |
| 1082 | recon | docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt | line 192 | q_emrank: ranked by net_margin, fees 0.40%, declared bucket spread and slippage, 12m; capped skeptic at 0.50, one per pair, at most three open | 283 trades |
| 1083 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[0] | rank by (alphabetical control) ascending, all folds | 271645 bars, target rate 0.257129709731451 |
| 1084 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[1] | rank by bar_range_pct descending, all folds | 271645 bars, target rate 0.31237092528851995 |
| 1085 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[2] | rank by bar_range_pct ascending, all folds | 271645 bars, target rate 0.23431316608073036 |
| 1086 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[3] | rank by bar_body_pct descending, all folds | 271645 bars, target rate 0.2276905520072153 |
| 1087 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[4] | rank by bar_body_pct ascending, all folds | 271645 bars, target rate 0.3748090338493254 |
| 1088 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[5] | rank by hour_sin descending, all folds | 271645 bars, target rate 0.257129709731451 |
| 1089 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[6] | rank by hour_sin ascending, all folds | 271645 bars, target rate 0.257129709731451 |
| 1090 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[7] | rank by hour_cos descending, all folds | 271645 bars, target rate 0.257129709731451 |
| 1091 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[8] | rank by hour_cos ascending, all folds | 271645 bars, target rate 0.257129709731451 |
| 1092 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[9] | rank by weekday_sin descending, all folds | 271645 bars, target rate 0.257129709731451 |
| 1093 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[10] | rank by weekday_sin ascending, all folds | 271645 bars, target rate 0.257129709731451 |
| 1094 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[11] | rank by weekday_cos descending, all folds | 271645 bars, target rate 0.257129709731451 |
| 1095 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[12] | rank by weekday_cos ascending, all folds | 271645 bars, target rate 0.257129709731451 |
| 1096 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[13] | rank by bars_in_lookback_4 descending, all folds | 271645 bars, target rate 0.2562277973089878 |
| 1097 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[14] | rank by bars_in_lookback_4 ascending, all folds | 271645 bars, target rate 0.24937694417346168 |
| 1098 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[15] | rank by log_return_4 descending, all folds | 271645 bars, target rate 0.24462809917355371 |
| 1099 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[16] | rank by log_return_4 ascending, all folds | 271645 bars, target rate 0.33196635314472933 |
| 1100 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[17] | rank by realised_vol_4 descending, all folds | 271645 bars, target rate 0.30808592096302156 |
| 1101 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[18] | rank by realised_vol_4 ascending, all folds | 271645 bars, target rate 0.06810727235914521 |
| 1102 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[19] | rank by efficiency_ratio_4 descending, all folds | 271645 bars, target rate 0.21020817611220527 |
| 1103 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[20] | rank by efficiency_ratio_4 ascending, all folds | 271645 bars, target rate 0.18952309079865265 |
| 1104 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[21] | rank by range_atr_4 descending, all folds | 271645 bars, target rate 0.30536545859485725 |
| 1105 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[22] | rank by range_atr_4 ascending, all folds | 271645 bars, target rate 0.10532496456772626 |
| 1106 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[23] | rank by volume_z_4 descending, all folds | 271645 bars, target rate 0.23246516593347935 |
| 1107 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[24] | rank by volume_z_4 ascending, all folds | 271645 bars, target rate 0.22202138820887554 |
| 1108 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[25] | rank by trades_z_4 descending, all folds | 271645 bars, target rate 0.23542859246442968 |
| 1109 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[26] | rank by trades_z_4 ascending, all folds | 271645 bars, target rate 0.2231036831158313 |
| 1110 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[27] | rank by high_low_position_4 descending, all folds | 271645 bars, target rate 0.19684514715897586 |
| 1111 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[28] | rank by high_low_position_4 ascending, all folds | 271645 bars, target rate 0.25487308803769626 |
| 1112 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[29] | rank by bars_in_lookback_16 descending, all folds | 271645 bars, target rate 0.2425224097627418 |
| 1113 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[30] | rank by bars_in_lookback_16 ascending, all folds | 271645 bars, target rate 0.24642824274328629 |
| 1114 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[31] | rank by log_return_16 descending, all folds | 271645 bars, target rate 0.26071159049494746 |
| 1115 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[32] | rank by log_return_16 ascending, all folds | 271645 bars, target rate 0.31786706915275453 |
| 1116 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[33] | rank by realised_vol_16 descending, all folds | 271645 bars, target rate 0.3166559296140183 |
| 1117 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[34] | rank by realised_vol_16 ascending, all folds | 271645 bars, target rate 0.03371311822415285 |
| 1118 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[35] | rank by efficiency_ratio_16 descending, all folds | 271645 bars, target rate 0.248684864437041 |
| 1119 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[36] | rank by efficiency_ratio_16 ascending, all folds | 271645 bars, target rate 0.17127132838815365 |
| 1120 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[37] | rank by range_atr_16 descending, all folds | 271645 bars, target rate 0.3126691085792118 |
| 1121 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[38] | rank by range_atr_16 ascending, all folds | 271645 bars, target rate 0.036297373410149276 |
| 1122 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[39] | rank by volume_z_16 descending, all folds | 271645 bars, target rate 0.22705737267389423 |
| 1123 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[40] | rank by volume_z_16 ascending, all folds | 271645 bars, target rate 0.21892175449575732 |
| 1124 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[41] | rank by trades_z_16 descending, all folds | 271645 bars, target rate 0.23307993889083178 |
| 1125 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[42] | rank by trades_z_16 ascending, all folds | 271645 bars, target rate 0.2145189493640597 |
| 1126 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[43] | rank by high_low_position_16 descending, all folds | 271645 bars, target rate 0.18133961604299728 |
| 1127 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[44] | rank by high_low_position_16 ascending, all folds | 271645 bars, target rate 0.24264021056894108 |
| 1128 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[45] | rank by bars_in_lookback_48 descending, all folds | 271645 bars, target rate 0.23344070385981705 |
| 1129 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[46] | rank by bars_in_lookback_48 ascending, all folds | 271645 bars, target rate 0.24582819488670876 |
| 1130 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[47] | rank by log_return_48 descending, all folds | 271645 bars, target rate 0.27915477921552023 |
| 1131 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[48] | rank by log_return_48 ascending, all folds | 271645 bars, target rate 0.2961880395368956 |
| 1132 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[49] | rank by realised_vol_48 descending, all folds | 271645 bars, target rate 0.3194132047341199 |
| 1133 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[50] | rank by realised_vol_48 ascending, all folds | 271645 bars, target rate 0.03005761195678183 |
| 1134 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[51] | rank by efficiency_ratio_48 descending, all folds | 271645 bars, target rate 0.2591507298128072 |
| 1135 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[52] | rank by efficiency_ratio_48 ascending, all folds | 271645 bars, target rate 0.15760643486903864 |
| 1136 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[53] | rank by range_atr_48 descending, all folds | 271645 bars, target rate 0.31249608864510664 |
| 1137 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[54] | rank by range_atr_48 ascending, all folds | 271645 bars, target rate 0.03335235325516759 |
| 1138 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[55] | rank by volume_z_48 descending, all folds | 271645 bars, target rate 0.2245099302398351 |
| 1139 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[56] | rank by volume_z_48 ascending, all folds | 271645 bars, target rate 0.21461098124390288 |
| 1140 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[57] | rank by trades_z_48 descending, all folds | 271645 bars, target rate 0.22833845644131126 |
| 1141 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[58] | rank by trades_z_48 ascending, all folds | 271645 bars, target rate 0.20538202433322902 |
| 1142 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[59] | rank by high_low_position_48 descending, all folds | 271645 bars, target rate 0.18117395865927957 |
| 1143 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[60] | rank by high_low_position_48 ascending, all folds | 271645 bars, target rate 0.22386570708093284 |
| 1144 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[61] | rank by bars_in_lookback_96 descending, all folds | 271645 bars, target rate 0.22717149220489977 |
| 1145 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[62] | rank by bars_in_lookback_96 ascending, all folds | 271645 bars, target rate 0.24735960536729923 |
| 1146 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[63] | rank by log_return_96 descending, all folds | 271645 bars, target rate 0.2856154171805113 |
| 1147 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[64] | rank by log_return_96 ascending, all folds | 271645 bars, target rate 0.27960021351396125 |
| 1148 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[65] | rank by realised_vol_96 descending, all folds | 271645 bars, target rate 0.31699092565664744 |
| 1149 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[66] | rank by realised_vol_96 ascending, all folds | 271645 bars, target rate 0.028301643689374 |
| 1150 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[67] | rank by efficiency_ratio_96 descending, all folds | 271645 bars, target rate 0.26403578199488303 |
| 1151 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[68] | rank by efficiency_ratio_96 ascending, all folds | 271645 bars, target rate 0.1435439636290011 |
| 1152 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[69] | rank by range_atr_96 descending, all folds | 271645 bars, target rate 0.3122273555559646 |
| 1153 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[70] | rank by range_atr_96 ascending, all folds | 271645 bars, target rate 0.03146385908078558 |
| 1154 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[71] | rank by volume_z_96 descending, all folds | 271645 bars, target rate 0.2257762889064772 |
| 1155 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[72] | rank by volume_z_96 ascending, all folds | 271645 bars, target rate 0.21268935559277735 |
| 1156 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[73] | rank by trades_z_96 descending, all folds | 271645 bars, target rate 0.2282464245614681 |
| 1157 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[74] | rank by trades_z_96 ascending, all folds | 271645 bars, target rate 0.20580537098050763 |
| 1158 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[75] | rank by high_low_position_96 descending, all folds | 271645 bars, target rate 0.18937215851570985 |
| 1159 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[76] | rank by high_low_position_96 ascending, all folds | 271645 bars, target rate 0.21247952290673489 |
| 1160 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[77] | rank by vol_regime_rank descending, all folds | 271645 bars, target rate 0.21368329989508367 |
| 1161 | ranking_study | docs/dataset/ranking-study-2026-09-14.json | rankings[78] | rank by vol_regime_rank ascending, all folds | 271645 bars, target rate 0.2147876824532018 |
| 1162 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[0].all | rank by (alphabetical control) ascending, all folds, reported again by the by-year study | 271645 bars |
| 1163 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[0].by_year.2017 | rank by (alphabetical control) ascending, test year 2017 | 26356 bars |
| 1164 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[0].by_year.2018 | rank by (alphabetical control) ascending, test year 2018 | 34785 bars |
| 1165 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[0].by_year.2019 | rank by (alphabetical control) ascending, test year 2019 | 35019 bars |
| 1166 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[0].by_year.2020 | rank by (alphabetical control) ascending, test year 2020 | 35115 bars |
| 1167 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[0].by_year.2021 | rank by (alphabetical control) ascending, test year 2021 | 34977 bars |
| 1168 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[0].by_year.2022 | rank by (alphabetical control) ascending, test year 2022 | 35007 bars |
| 1169 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[0].by_year.2023 | rank by (alphabetical control) ascending, test year 2023 | 35025 bars |
| 1170 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[0].by_year.2024 | rank by (alphabetical control) ascending, test year 2024 | 35073 bars |
| 1171 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[0].by_year.2025 | rank by (alphabetical control) ascending, test year 2025 | 288 bars |
| 1172 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[1].all | rank by bar_body_pct ascending, all folds, reported again by the by-year study | 271645 bars |
| 1173 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[1].by_year.2017 | rank by bar_body_pct ascending, test year 2017 | 26356 bars |
| 1174 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[1].by_year.2018 | rank by bar_body_pct ascending, test year 2018 | 34785 bars |
| 1175 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[1].by_year.2019 | rank by bar_body_pct ascending, test year 2019 | 35019 bars |
| 1176 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[1].by_year.2020 | rank by bar_body_pct ascending, test year 2020 | 35115 bars |
| 1177 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[1].by_year.2021 | rank by bar_body_pct ascending, test year 2021 | 34977 bars |
| 1178 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[1].by_year.2022 | rank by bar_body_pct ascending, test year 2022 | 35007 bars |
| 1179 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[1].by_year.2023 | rank by bar_body_pct ascending, test year 2023 | 35025 bars |
| 1180 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[1].by_year.2024 | rank by bar_body_pct ascending, test year 2024 | 35073 bars |
| 1181 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[1].by_year.2025 | rank by bar_body_pct ascending, test year 2025 | 288 bars |
| 1182 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[2].all | rank by log_return_4 ascending, all folds, reported again by the by-year study | 271645 bars |
| 1183 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[2].by_year.2017 | rank by log_return_4 ascending, test year 2017 | 26356 bars |
| 1184 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[2].by_year.2018 | rank by log_return_4 ascending, test year 2018 | 34785 bars |
| 1185 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[2].by_year.2019 | rank by log_return_4 ascending, test year 2019 | 35019 bars |
| 1186 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[2].by_year.2020 | rank by log_return_4 ascending, test year 2020 | 35115 bars |
| 1187 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[2].by_year.2021 | rank by log_return_4 ascending, test year 2021 | 34977 bars |
| 1188 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[2].by_year.2022 | rank by log_return_4 ascending, test year 2022 | 35007 bars |
| 1189 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[2].by_year.2023 | rank by log_return_4 ascending, test year 2023 | 35025 bars |
| 1190 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[2].by_year.2024 | rank by log_return_4 ascending, test year 2024 | 35073 bars |
| 1191 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[2].by_year.2025 | rank by log_return_4 ascending, test year 2025 | 288 bars |
| 1192 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[3].all | rank by log_return_16 ascending, all folds, reported again by the by-year study | 271645 bars |
| 1193 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[3].by_year.2017 | rank by log_return_16 ascending, test year 2017 | 26356 bars |
| 1194 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[3].by_year.2018 | rank by log_return_16 ascending, test year 2018 | 34785 bars |
| 1195 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[3].by_year.2019 | rank by log_return_16 ascending, test year 2019 | 35019 bars |
| 1196 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[3].by_year.2020 | rank by log_return_16 ascending, test year 2020 | 35115 bars |
| 1197 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[3].by_year.2021 | rank by log_return_16 ascending, test year 2021 | 34977 bars |
| 1198 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[3].by_year.2022 | rank by log_return_16 ascending, test year 2022 | 35007 bars |
| 1199 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[3].by_year.2023 | rank by log_return_16 ascending, test year 2023 | 35025 bars |
| 1200 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[3].by_year.2024 | rank by log_return_16 ascending, test year 2024 | 35073 bars |
| 1201 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[3].by_year.2025 | rank by log_return_16 ascending, test year 2025 | 288 bars |
| 1202 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[4].all | rank by high_low_position_16 ascending, all folds, reported again by the by-year study | 271645 bars |
| 1203 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[4].by_year.2017 | rank by high_low_position_16 ascending, test year 2017 | 26356 bars |
| 1204 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[4].by_year.2018 | rank by high_low_position_16 ascending, test year 2018 | 34785 bars |
| 1205 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[4].by_year.2019 | rank by high_low_position_16 ascending, test year 2019 | 35019 bars |
| 1206 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[4].by_year.2020 | rank by high_low_position_16 ascending, test year 2020 | 35115 bars |
| 1207 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[4].by_year.2021 | rank by high_low_position_16 ascending, test year 2021 | 34977 bars |
| 1208 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[4].by_year.2022 | rank by high_low_position_16 ascending, test year 2022 | 35007 bars |
| 1209 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[4].by_year.2023 | rank by high_low_position_16 ascending, test year 2023 | 35025 bars |
| 1210 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[4].by_year.2024 | rank by high_low_position_16 ascending, test year 2024 | 35073 bars |
| 1211 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[4].by_year.2025 | rank by high_low_position_16 ascending, test year 2025 | 288 bars |
| 1212 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[5].all | rank by bars_in_lookback_96 ascending, all folds, reported again by the by-year study | 271645 bars |
| 1213 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[5].by_year.2017 | rank by bars_in_lookback_96 ascending, test year 2017 | 26356 bars |
| 1214 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[5].by_year.2018 | rank by bars_in_lookback_96 ascending, test year 2018 | 34785 bars |
| 1215 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[5].by_year.2019 | rank by bars_in_lookback_96 ascending, test year 2019 | 35019 bars |
| 1216 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[5].by_year.2020 | rank by bars_in_lookback_96 ascending, test year 2020 | 35115 bars |
| 1217 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[5].by_year.2021 | rank by bars_in_lookback_96 ascending, test year 2021 | 34977 bars |
| 1218 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[5].by_year.2022 | rank by bars_in_lookback_96 ascending, test year 2022 | 35007 bars |
| 1219 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[5].by_year.2023 | rank by bars_in_lookback_96 ascending, test year 2023 | 35025 bars |
| 1220 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[5].by_year.2024 | rank by bars_in_lookback_96 ascending, test year 2024 | 35073 bars |
| 1221 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[5].by_year.2025 | rank by bars_in_lookback_96 ascending, test year 2025 | 288 bars |
| 1222 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[6].all | rank by realised_vol_16 descending, all folds, reported again by the by-year study | 271645 bars |
| 1223 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[6].by_year.2017 | rank by realised_vol_16 descending, test year 2017 | 26356 bars |
| 1224 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[6].by_year.2018 | rank by realised_vol_16 descending, test year 2018 | 34785 bars |
| 1225 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[6].by_year.2019 | rank by realised_vol_16 descending, test year 2019 | 35019 bars |
| 1226 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[6].by_year.2020 | rank by realised_vol_16 descending, test year 2020 | 35115 bars |
| 1227 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[6].by_year.2021 | rank by realised_vol_16 descending, test year 2021 | 34977 bars |
| 1228 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[6].by_year.2022 | rank by realised_vol_16 descending, test year 2022 | 35007 bars |
| 1229 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[6].by_year.2023 | rank by realised_vol_16 descending, test year 2023 | 35025 bars |
| 1230 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[6].by_year.2024 | rank by realised_vol_16 descending, test year 2024 | 35073 bars |
| 1231 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[6].by_year.2025 | rank by realised_vol_16 descending, test year 2025 | 288 bars |
| 1232 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[7].all | rank by range_atr_4 descending, all folds, reported again by the by-year study | 271645 bars |
| 1233 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[7].by_year.2017 | rank by range_atr_4 descending, test year 2017 | 26356 bars |
| 1234 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[7].by_year.2018 | rank by range_atr_4 descending, test year 2018 | 34785 bars |
| 1235 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[7].by_year.2019 | rank by range_atr_4 descending, test year 2019 | 35019 bars |
| 1236 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[7].by_year.2020 | rank by range_atr_4 descending, test year 2020 | 35115 bars |
| 1237 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[7].by_year.2021 | rank by range_atr_4 descending, test year 2021 | 34977 bars |
| 1238 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[7].by_year.2022 | rank by range_atr_4 descending, test year 2022 | 35007 bars |
| 1239 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[7].by_year.2023 | rank by range_atr_4 descending, test year 2023 | 35025 bars |
| 1240 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[7].by_year.2024 | rank by range_atr_4 descending, test year 2024 | 35073 bars |
| 1241 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[7].by_year.2025 | rank by range_atr_4 descending, test year 2025 | 288 bars |
| 1242 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[8].all | rank by bar_range_pct descending, all folds, reported again by the by-year study | 271645 bars |
| 1243 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[8].by_year.2017 | rank by bar_range_pct descending, test year 2017 | 26356 bars |
| 1244 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[8].by_year.2018 | rank by bar_range_pct descending, test year 2018 | 34785 bars |
| 1245 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[8].by_year.2019 | rank by bar_range_pct descending, test year 2019 | 35019 bars |
| 1246 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[8].by_year.2020 | rank by bar_range_pct descending, test year 2020 | 35115 bars |
| 1247 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[8].by_year.2021 | rank by bar_range_pct descending, test year 2021 | 34977 bars |
| 1248 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[8].by_year.2022 | rank by bar_range_pct descending, test year 2022 | 35007 bars |
| 1249 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[8].by_year.2023 | rank by bar_range_pct descending, test year 2023 | 35025 bars |
| 1250 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[8].by_year.2024 | rank by bar_range_pct descending, test year 2024 | 35073 bars |
| 1251 | ranking_study | docs/dataset/ranking-study-2026-09-14-by-year.json | rows[8].by_year.2025 | rank by bar_range_pct descending, test year 2025 | 288 bars |
| 1252 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[0] survivors | uncapped skeptic, all folds, survivors at veto 0.3 | 9373 calls, target rate 0.6349087805398484 |
| 1253 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[0] vetoed | uncapped skeptic, all folds, calls vetoed at 0.3 | 8939112 calls, target rate 0.23788906549106892 |
| 1254 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[1] survivors | uncapped skeptic, all folds, survivors at veto 0.35 | 24888 calls, target rate 0.6313484410157506 |
| 1255 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[1] vetoed | uncapped skeptic, all folds, calls vetoed at 0.35 | 8923597 calls, target rate 0.23720871751604203 |
| 1256 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[2] survivors | uncapped skeptic, all folds, survivors at veto 0.4 | 51145 calls, target rate 0.6034607488513051 |
| 1257 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[2] vetoed | uncapped skeptic, all folds, calls vetoed at 0.4 | 8897340 calls, target rate 0.23620587726219297 |
| 1258 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[3] survivors | uncapped skeptic, all folds, survivors at veto 0.45 | 88931 calls, target rate 0.5692503176620076 |
| 1259 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[3] vetoed | uncapped skeptic, all folds, calls vetoed at 0.45 | 8859554 calls, target rate 0.2349829348068763 |
| 1260 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[4] survivors | uncapped skeptic, all folds, survivors at veto 0.5 | 154979 calls, target rate 0.530929996967331 |
| 1261 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[4] vetoed | uncapped skeptic, all folds, calls vetoed at 0.5 | 8793506 calls, target rate 0.23314762052814883 |
| 1262 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[5] survivors | uncapped skeptic, all folds, survivors at veto 0.55 | 289977 calls, target rate 0.4877283370750094 |
| 1263 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[5] vetoed | uncapped skeptic, all folds, calls vetoed at 0.55 | 8658508 calls, target rate 0.22995162676987768 |
| 1264 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[6] survivors | uncapped skeptic, all folds, survivors at veto 0.6 | 583121 calls, target rate 0.44027740383213776 |
| 1265 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[6] vetoed | uncapped skeptic, all folds, calls vetoed at 0.6 | 8365364 calls, target rate 0.22422610659858913 |
| 1266 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[7] survivors | uncapped skeptic, all folds, survivors at veto 0.65 | 1265683 calls, target rate 0.39282110923509284 |
| 1267 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[7] vetoed | uncapped skeptic, all folds, calls vetoed at 0.65 | 7682802 calls, target rate 0.2128495567112103 |
| 1268 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[8] survivors | uncapped skeptic, all folds, survivors at veto 0.7 | 2859743 calls, target rate 0.3481854838004674 |
| 1269 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | sweep[8] vetoed | uncapped skeptic, all folds, calls vetoed at 0.7 | 6088742 calls, target rate 0.18669652943087423 |
| 1270 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2017[0] survivors | uncapped skeptic, test year 2017, survivors at 0.5 | 16655 calls |
| 1271 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2017[0] vetoed | uncapped skeptic, test year 2017, vetoed at 0.5 | 113610 calls |
| 1272 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2017[1] survivors | uncapped skeptic, test year 2017, survivors at 0.6 | 33811 calls |
| 1273 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2017[1] vetoed | uncapped skeptic, test year 2017, vetoed at 0.6 | 96454 calls |
| 1274 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2017[2] survivors | uncapped skeptic, test year 2017, survivors at 0.7 | 63609 calls |
| 1275 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2017[2] vetoed | uncapped skeptic, test year 2017, vetoed at 0.7 | 66656 calls |
| 1276 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2018[0] survivors | uncapped skeptic, test year 2018, survivors at 0.5 | 5376 calls |
| 1277 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2018[0] vetoed | uncapped skeptic, test year 2018, vetoed at 0.5 | 162010 calls |
| 1278 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2018[1] survivors | uncapped skeptic, test year 2018, survivors at 0.6 | 16425 calls |
| 1279 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2018[1] vetoed | uncapped skeptic, test year 2018, vetoed at 0.6 | 150961 calls |
| 1280 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2018[2] survivors | uncapped skeptic, test year 2018, survivors at 0.7 | 50336 calls |
| 1281 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2018[2] vetoed | uncapped skeptic, test year 2018, vetoed at 0.7 | 117050 calls |
| 1282 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2019[0] survivors | uncapped skeptic, test year 2019, survivors at 0.5 | 3135 calls |
| 1283 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2019[0] vetoed | uncapped skeptic, test year 2019, vetoed at 0.5 | 254272 calls |
| 1284 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2019[1] survivors | uncapped skeptic, test year 2019, survivors at 0.6 | 12018 calls |
| 1285 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2019[1] vetoed | uncapped skeptic, test year 2019, vetoed at 0.6 | 245389 calls |
| 1286 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2019[2] survivors | uncapped skeptic, test year 2019, survivors at 0.7 | 46106 calls |
| 1287 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2019[2] vetoed | uncapped skeptic, test year 2019, vetoed at 0.7 | 211301 calls |
| 1288 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2020[0] survivors | uncapped skeptic, test year 2020, survivors at 0.5 | 6718 calls |
| 1289 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2020[0] vetoed | uncapped skeptic, test year 2020, vetoed at 0.5 | 644559 calls |
| 1290 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2020[1] survivors | uncapped skeptic, test year 2020, survivors at 0.6 | 31395 calls |
| 1291 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2020[1] vetoed | uncapped skeptic, test year 2020, vetoed at 0.6 | 619882 calls |
| 1292 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2020[2] survivors | uncapped skeptic, test year 2020, survivors at 0.7 | 151611 calls |
| 1293 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2020[2] vetoed | uncapped skeptic, test year 2020, vetoed at 0.7 | 499666 calls |
| 1294 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2021[0] survivors | uncapped skeptic, test year 2021, survivors at 0.5 | 24844 calls |
| 1295 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2021[0] vetoed | uncapped skeptic, test year 2021, vetoed at 0.5 | 1216012 calls |
| 1296 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2021[1] survivors | uncapped skeptic, test year 2021, survivors at 0.6 | 109814 calls |
| 1297 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2021[1] vetoed | uncapped skeptic, test year 2021, vetoed at 0.6 | 1131042 calls |
| 1298 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2021[2] survivors | uncapped skeptic, test year 2021, survivors at 0.7 | 490815 calls |
| 1299 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2021[2] vetoed | uncapped skeptic, test year 2021, vetoed at 0.7 | 750041 calls |
| 1300 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2022[0] survivors | uncapped skeptic, test year 2022, survivors at 0.5 | 27072 calls |
| 1301 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2022[0] vetoed | uncapped skeptic, test year 2022, vetoed at 0.5 | 1772457 calls |
| 1302 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2022[1] survivors | uncapped skeptic, test year 2022, survivors at 0.6 | 113035 calls |
| 1303 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2022[1] vetoed | uncapped skeptic, test year 2022, vetoed at 0.6 | 1686494 calls |
| 1304 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2022[2] survivors | uncapped skeptic, test year 2022, survivors at 0.7 | 566383 calls |
| 1305 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2022[2] vetoed | uncapped skeptic, test year 2022, vetoed at 0.7 | 1233146 calls |
| 1306 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2023[0] survivors | uncapped skeptic, test year 2023, survivors at 0.5 | 30054 calls |
| 1307 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2023[0] vetoed | uncapped skeptic, test year 2023, vetoed at 0.5 | 2207078 calls |
| 1308 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2023[1] survivors | uncapped skeptic, test year 2023, survivors at 0.6 | 100358 calls |
| 1309 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2023[1] vetoed | uncapped skeptic, test year 2023, vetoed at 0.6 | 2136774 calls |
| 1310 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2023[2] survivors | uncapped skeptic, test year 2023, survivors at 0.7 | 552641 calls |
| 1311 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2023[2] vetoed | uncapped skeptic, test year 2023, vetoed at 0.7 | 1684491 calls |
| 1312 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2024[0] survivors | uncapped skeptic, test year 2024, survivors at 0.5 | 41125 calls |
| 1313 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2024[0] vetoed | uncapped skeptic, test year 2024, vetoed at 0.5 | 2423508 calls |
| 1314 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2024[1] survivors | uncapped skeptic, test year 2024, survivors at 0.6 | 166265 calls |
| 1315 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2024[1] vetoed | uncapped skeptic, test year 2024, vetoed at 0.6 | 2298368 calls |
| 1316 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2024[2] survivors | uncapped skeptic, test year 2024, survivors at 0.7 | 938242 calls |
| 1317 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | by_test_year_at_0.5_0.6_0.7.2024[2] vetoed | uncapped skeptic, test year 2024, vetoed at 0.7 | 1526391 calls |
| 1318 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[0].by_threshold[0] own | fold 404 calls, own skeptic (fold 404), survivors at 0.5 | 25 calls |
| 1319 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[0].by_threshold[0] other | fold 404 calls, other skeptic (fold 403), survivors at 0.5 | 24 calls |
| 1320 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[0].by_threshold[1] own | fold 404 calls, own skeptic (fold 404), survivors at 0.6 | 26 calls |
| 1321 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[0].by_threshold[1] other | fold 404 calls, other skeptic (fold 403), survivors at 0.6 | 26 calls |
| 1322 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[0].by_threshold[2] own | fold 404 calls, own skeptic (fold 404), survivors at 0.7 | 26 calls |
| 1323 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[0].by_threshold[2] other | fold 404 calls, other skeptic (fold 403), survivors at 0.7 | 26 calls |
| 1324 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[1].by_threshold[0] own | fold 404 calls, own skeptic (fold 404), survivors at 0.5 | 25 calls |
| 1325 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[1].by_threshold[0] other | fold 404 calls, other skeptic (fold 250), survivors at 0.5 | 18 calls |
| 1326 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[1].by_threshold[1] own | fold 404 calls, own skeptic (fold 404), survivors at 0.6 | 26 calls |
| 1327 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[1].by_threshold[1] other | fold 404 calls, other skeptic (fold 250), survivors at 0.6 | 25 calls |
| 1328 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[1].by_threshold[2] own | fold 404 calls, own skeptic (fold 404), survivors at 0.7 | 26 calls |
| 1329 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[1].by_threshold[2] other | fold 404 calls, other skeptic (fold 250), survivors at 0.7 | 26 calls |
| 1330 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[2].by_threshold[0] own | fold 300 calls, own skeptic (fold 300), survivors at 0.5 | 243 calls |
| 1331 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[2].by_threshold[0] other | fold 300 calls, other skeptic (fold 150), survivors at 0.5 | 419 calls |
| 1332 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[2].by_threshold[1] own | fold 300 calls, own skeptic (fold 300), survivors at 0.6 | 583 calls |
| 1333 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[2].by_threshold[1] other | fold 300 calls, other skeptic (fold 150), survivors at 0.6 | 792 calls |
| 1334 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[2].by_threshold[2] own | fold 300 calls, own skeptic (fold 300), survivors at 0.7 | 1209 calls |
| 1335 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[2].by_threshold[2] other | fold 300 calls, other skeptic (fold 150), survivors at 0.7 | 1669 calls |
| 1336 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[3].by_threshold[0] own | fold 200 calls, own skeptic (fold 200), survivors at 0.5 | 719 calls |
| 1337 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[3].by_threshold[0] other | fold 200 calls, other skeptic (fold 350), survivors at 0.5 | 400 calls |
| 1338 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[3].by_threshold[1] own | fold 200 calls, own skeptic (fold 200), survivors at 0.6 | 2072 calls |
| 1339 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[3].by_threshold[1] other | fold 200 calls, other skeptic (fold 350), survivors at 0.6 | 1902 calls |
| 1340 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[3].by_threshold[2] own | fold 200 calls, own skeptic (fold 200), survivors at 0.7 | 5275 calls |
| 1341 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | different_fold_controls[3].by_threshold[2] other | fold 200 calls, other skeptic (fold 350), survivors at 0.7 | 5752 calls |
| 1342 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | meta.all_buy_calls | every BUY call, all folds, no skeptic | 8950912 calls |
| 1343 | skeptic_sweep | docs/dataset/skeptic-veto-sweep-2026-09-14.json | meta.buy_calls_without_a_skeptic | BUY calls of the fold with no skeptic | 2427 calls |
| 1344 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[0].control_topN_by_skeptic_score | control_topN_by_skeptic_score, matched to the skeptic's survivor count at 0.3 | 9373 calls, target rate 0.6349087805398484 |
| 1345 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[0].control_topN_random | control_topN_random, matched to the skeptic's survivor count at 0.3 | 9373 calls, target rate 0.279846367225008 |
| 1346 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[0].skeptic | skeptic, matched to the skeptic's survivor count at 0.3 | 9373 calls, target rate 0.6349087805398484 |
| 1347 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[0].topN_by_p_target_seed_20260914 | topN_by_p_target_seed_20260914, matched to the skeptic's survivor count at 0.3 | 9373 calls, target rate 0.5605462498666383 |
| 1348 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[0].topN_by_p_target_seed_7 | topN_by_p_target_seed_7, matched to the skeptic's survivor count at 0.3 | 9373 calls, target rate 0.5608663181478716 |
| 1349 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[1].control_topN_by_skeptic_score | control_topN_by_skeptic_score, matched to the skeptic's survivor count at 0.35 | 24888 calls, target rate 0.6313484410157506 |
| 1350 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[1].control_topN_random | control_topN_random, matched to the skeptic's survivor count at 0.35 | 24888 calls, target rate 0.26651398264223725 |
| 1351 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[1].skeptic | skeptic, matched to the skeptic's survivor count at 0.35 | 24888 calls, target rate 0.6313484410157506 |
| 1352 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[1].topN_by_p_target_seed_20260914 | topN_by_p_target_seed_20260914, matched to the skeptic's survivor count at 0.35 | 24888 calls, target rate 0.5560109289617486 |
| 1353 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[1].topN_by_p_target_seed_7 | topN_by_p_target_seed_7, matched to the skeptic's survivor count at 0.35 | 24888 calls, target rate 0.5558100289296046 |
| 1354 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[2].control_topN_by_skeptic_score | control_topN_by_skeptic_score, matched to the skeptic's survivor count at 0.4 | 51145 calls, target rate 0.6034607488513051 |
| 1355 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[2].control_topN_random | control_topN_random, matched to the skeptic's survivor count at 0.4 | 51145 calls, target rate 0.25807019258969593 |
| 1356 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[2].skeptic | skeptic, matched to the skeptic's survivor count at 0.4 | 51145 calls, target rate 0.6034607488513051 |
| 1357 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[2].topN_by_p_target_seed_20260914 | topN_by_p_target_seed_20260914, matched to the skeptic's survivor count at 0.4 | 51145 calls, target rate 0.5305112914263369 |
| 1358 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[2].topN_by_p_target_seed_7 | topN_by_p_target_seed_7, matched to the skeptic's survivor count at 0.4 | 51145 calls, target rate 0.530902336494281 |
| 1359 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[3].control_topN_by_skeptic_score | control_topN_by_skeptic_score, matched to the skeptic's survivor count at 0.45 | 88931 calls, target rate 0.5692503176620076 |
| 1360 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[3].control_topN_random | control_topN_random, matched to the skeptic's survivor count at 0.45 | 88931 calls, target rate 0.25436574422867164 |
| 1361 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[3].skeptic | skeptic, matched to the skeptic's survivor count at 0.45 | 88931 calls, target rate 0.5692503176620076 |
| 1362 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[3].topN_by_p_target_seed_20260914 | topN_by_p_target_seed_20260914, matched to the skeptic's survivor count at 0.45 | 88931 calls, target rate 0.5025244290517368 |
| 1363 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[3].topN_by_p_target_seed_7 | topN_by_p_target_seed_7, matched to the skeptic's survivor count at 0.45 | 88931 calls, target rate 0.5028167905454791 |
| 1364 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[4].control_topN_by_skeptic_score | control_topN_by_skeptic_score, matched to the skeptic's survivor count at 0.5 | 154979 calls, target rate 0.530929996967331 |
| 1365 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[4].control_topN_random | control_topN_random, matched to the skeptic's survivor count at 0.5 | 154979 calls, target rate 0.25641538531026786 |
| 1366 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[4].skeptic | skeptic, matched to the skeptic's survivor count at 0.5 | 154979 calls, target rate 0.530929996967331 |
| 1367 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[4].topN_by_p_target_seed_20260914 | topN_by_p_target_seed_20260914, matched to the skeptic's survivor count at 0.5 | 154979 calls, target rate 0.47310925996425324 |
| 1368 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[4].topN_by_p_target_seed_7 | topN_by_p_target_seed_7, matched to the skeptic's survivor count at 0.5 | 154979 calls, target rate 0.473386716910033 |
| 1369 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[5].control_topN_by_skeptic_score | control_topN_by_skeptic_score, matched to the skeptic's survivor count at 0.55 | 289977 calls, target rate 0.4877283370750094 |
| 1370 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[5].control_topN_random | control_topN_random, matched to the skeptic's survivor count at 0.55 | 289977 calls, target rate 0.2587687989047407 |
| 1371 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[5].skeptic | skeptic, matched to the skeptic's survivor count at 0.55 | 289977 calls, target rate 0.4877283370750094 |
| 1372 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[5].topN_by_p_target_seed_20260914 | topN_by_p_target_seed_20260914, matched to the skeptic's survivor count at 0.55 | 289977 calls, target rate 0.4418695275832221 |
| 1373 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[5].topN_by_p_target_seed_7 | topN_by_p_target_seed_7, matched to the skeptic's survivor count at 0.55 | 289977 calls, target rate 0.44213506588453566 |
| 1374 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[6].control_topN_by_skeptic_score | control_topN_by_skeptic_score, matched to the skeptic's survivor count at 0.6 | 583121 calls, target rate 0.44027740383213776 |
| 1375 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[6].control_topN_random | control_topN_random, matched to the skeptic's survivor count at 0.6 | 583121 calls, target rate 0.2610898938642237 |
| 1376 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[6].skeptic | skeptic, matched to the skeptic's survivor count at 0.6 | 583121 calls, target rate 0.44027740383213776 |
| 1377 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[6].topN_by_p_target_seed_20260914 | topN_by_p_target_seed_20260914, matched to the skeptic's survivor count at 0.6 | 583121 calls, target rate 0.4097057043049384 |
| 1378 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[6].topN_by_p_target_seed_7 | topN_by_p_target_seed_7, matched to the skeptic's survivor count at 0.6 | 583121 calls, target rate 0.4098411821903173 |
| 1379 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[7].control_topN_by_skeptic_score | control_topN_by_skeptic_score, matched to the skeptic's survivor count at 0.65 | 1265683 calls, target rate 0.39282110923509284 |
| 1380 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[7].control_topN_random | control_topN_random, matched to the skeptic's survivor count at 0.65 | 1265683 calls, target rate 0.26382435412342586 |
| 1381 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[7].skeptic | skeptic, matched to the skeptic's survivor count at 0.65 | 1265683 calls, target rate 0.39282110923509284 |
| 1382 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[7].topN_by_p_target_seed_20260914 | topN_by_p_target_seed_20260914, matched to the skeptic's survivor count at 0.65 | 1265683 calls, target rate 0.3779880112160786 |
| 1383 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[7].topN_by_p_target_seed_7 | topN_by_p_target_seed_7, matched to the skeptic's survivor count at 0.65 | 1265683 calls, target rate 0.37805674880677076 |
| 1384 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[8].control_topN_by_skeptic_score | control_topN_by_skeptic_score, matched to the skeptic's survivor count at 0.7 | 2859743 calls, target rate 0.3481854838004674 |
| 1385 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[8].control_topN_random | control_topN_random, matched to the skeptic's survivor count at 0.7 | 2859743 calls, target rate 0.26473253016092707 |
| 1386 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[8].skeptic | skeptic, matched to the skeptic's survivor count at 0.7 | 2859743 calls, target rate 0.3481854838004674 |
| 1387 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[8].topN_by_p_target_seed_20260914 | topN_by_p_target_seed_20260914, matched to the skeptic's survivor count at 0.7 | 2859743 calls, target rate 0.34325392176849456 |
| 1388 | skeptic_vs_p_target | docs/dataset/skeptic-vs-ptarget-2026-09-14.json | by_threshold[8].topN_by_p_target_seed_7 | topN_by_p_target_seed_7, matched to the skeptic's survivor count at 0.7 | 2859743 calls, target rate 0.34325916699507614 |
| 1389 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | all_rows | every out-of-sample row, no gate | all: 15978803 rows, target rate 0.242158064030203 |
| 1390 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[0].kept | anomaly gate at percentile 0.8, kept | kept: 6310411 rows, target rate 0.2195690581802041 |
| 1391 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[0].refused | anomaly gate at percentile 0.8, refused | refused: 1678787 rows, target rate 0.2765687368320103 |
| 1392 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[0].buy_kept | anomaly gate at percentile 0.8, buy kept | buy_kept: 3493601 rows, target rate 0.2015962899025962 |
| 1393 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[0].buy_refused | anomaly gate at percentile 0.8, buy refused | buy_refused: 928085 rows, target rate 0.26856484050491064 |
| 1394 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[1].kept | anomaly gate at percentile 0.9, kept | kept: 7128639 rows, target rate 0.22392801767630538 |
| 1395 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[1].refused | anomaly gate at percentile 0.9, refused | refused: 860559 rows, target rate 0.29465614792245504 |
| 1396 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[1].buy_kept | anomaly gate at percentile 0.9, buy kept | buy_kept: 3960857 rows, target rate 0.2061235737619409 |
| 1397 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[1].buy_refused | anomaly gate at percentile 0.9, buy refused | buy_refused: 460829 rows, target rate 0.2975550583839125 |
| 1398 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[2].kept | anomaly gate at percentile 0.95, kept | kept: 7546015 rows, target rate 0.22703585932442488 |
| 1399 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[2].refused | anomaly gate at percentile 0.95, refused | refused: 443183 rows, target rate 0.3083489213259534 |
| 1400 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[2].buy_kept | anomaly gate at percentile 0.95, buy kept | buy_kept: 4194391 rows, target rate 0.20973366574551586 |
| 1401 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[2].buy_refused | anomaly gate at percentile 0.95, buy refused | buy_refused: 227295 rows, target rate 0.3248773620185222 |
| 1402 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[3].kept | anomaly gate at percentile 0.975, kept | kept: 7758893 rows, target rate 0.2289983893320864 |
| 1403 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[3].refused | anomaly gate at percentile 0.975, refused | refused: 230305 rows, target rate 0.31739215388289443 |
| 1404 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[3].buy_kept | anomaly gate at percentile 0.975, buy kept | buy_kept: 4309560 rows, target rate 0.21218175405377812 |
| 1405 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[3].buy_refused | anomaly gate at percentile 0.975, buy refused | buy_refused: 112126 rows, target rate 0.34905374311042936 |
| 1406 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[4].kept | anomaly gate at percentile 0.99, kept | kept: 7890430 rows, target rate 0.23046095079735832 |
| 1407 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[4].refused | anomaly gate at percentile 0.99, refused | refused: 98768 rows, target rate 0.31827109995140124 |
| 1408 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[4].buy_kept | anomaly gate at percentile 0.99, buy kept | buy_kept: 4376930 rows, target rate 0.21407973168407993 |
| 1409 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[4].buy_refused | anomaly gate at percentile 0.99, buy refused | buy_refused: 44756 rows, target rate 0.3694700151934936 |
| 1410 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[5].kept | anomaly gate at percentile 0.995, kept | kept: 7936490 rows, target rate 0.23102064010664664 |
| 1411 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[5].refused | anomaly gate at percentile 0.995, refused | refused: 52708 rows, target rate 0.3107308188510283 |
| 1412 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[5].buy_kept | anomaly gate at percentile 0.995, buy kept | buy_kept: 4398980 rows, target rate 0.21485003341683753 |
| 1413 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[5].buy_refused | anomaly gate at percentile 0.995, buy refused | buy_refused: 22706 rows, target rate 0.37113538271822427 |
| 1414 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[6].kept | anomaly gate at percentile 0.999, kept | kept: 7977208 rows, target rate 0.23147572433864078 |
| 1415 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[6].refused | anomaly gate at percentile 0.999, refused | refused: 11990 rows, target rate 0.2786488740617181 |
| 1416 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[6].buy_kept | anomaly gate at percentile 0.999, buy kept | buy_kept: 4416825 rows, target rate 0.2155122740882874 |
| 1417 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | anomaly[6].buy_refused | anomaly gate at percentile 0.999, buy refused | buy_refused: 4861 rows, target rate 0.343139271754783 |
| 1418 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[0].kept | di gate at percentile 0.8, kept | kept: 49063 rows, target rate 0.18188859221816847 |
| 1419 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[0].refused | di gate at percentile 0.8, refused | refused: 7904379 rows, target rate 0.2323668943505872 |
| 1420 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[0].buy_kept | di gate at percentile 0.8, buy kept | buy_kept: 26471 rows, target rate 0.16822182766045862 |
| 1421 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[0].buy_refused | di gate at percentile 0.8, buy refused | buy_refused: 4368342 rows, target rate 0.21672776536269367 |
| 1422 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[1].kept | di gate at percentile 0.9, kept | kept: 165413 rows, target rate 0.19281434953721896 |
| 1423 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[1].refused | di gate at percentile 0.9, refused | refused: 7788029 rows, target rate 0.23288896330509298 |
| 1424 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[1].buy_kept | di gate at percentile 0.9, buy kept | buy_kept: 89087 rows, target rate 0.17933031755474985 |
| 1425 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[1].buy_refused | di gate at percentile 0.9, buy refused | buy_refused: 4305726 rows, target rate 0.2172033241316331 |
| 1426 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[2].kept | di gate at percentile 0.95, kept | kept: 422734 rows, target rate 0.2034186982830811 |
| 1427 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[2].refused | di gate at percentile 0.95, refused | refused: 7530708 rows, target rate 0.23366302345011916 |
| 1428 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[2].buy_kept | di gate at percentile 0.95, buy kept | buy_kept: 227262 rows, target rate 0.1908370075067543 |
| 1429 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[2].buy_refused | di gate at percentile 0.95, buy refused | buy_refused: 4167551 rows, target rate 0.21783152743661685 |
| 1430 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[3].kept | di gate at percentile 0.975, kept | kept: 912478 rows, target rate 0.20928285394277998 |
| 1431 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[3].refused | di gate at percentile 0.975, refused | refused: 7040964 rows, target rate 0.23500674055427637 |
| 1432 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[3].buy_kept | di gate at percentile 0.975, buy kept | buy_kept: 489318 rows, target rate 0.19601567896541716 |
| 1433 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[3].buy_refused | di gate at percentile 0.975, buy refused | buy_refused: 3905495 rows, target rate 0.21899400716170422 |
| 1434 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[4].kept | di gate at percentile 0.99, kept | kept: 1993745 rows, target rate 0.21375200940942798 |
| 1435 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[4].refused | di gate at percentile 0.99, refused | refused: 5959697 rows, target rate 0.23817871948859146 |
| 1436 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[4].buy_kept | di gate at percentile 0.99, buy kept | buy_kept: 1067104 rows, target rate 0.19956442858428045 |
| 1437 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[4].buy_refused | di gate at percentile 0.99, buy refused | buy_refused: 3327709 rows, target rate 0.22184572028383492 |
| 1438 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[5].kept | di gate at percentile 0.995, kept | kept: 3085779 rows, target rate 0.21655568982743092 |
| 1439 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[5].refused | di gate at percentile 0.995, refused | refused: 4867663 rows, target rate 0.2418813709987729 |
| 1440 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[5].buy_kept | di gate at percentile 0.995, buy kept | buy_kept: 1654063 rows, target rate 0.20113985984814364 |
| 1441 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[5].buy_refused | di gate at percentile 0.995, buy refused | buy_refused: 2740750 rows, target rate 0.22566669707196935 |
| 1442 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[6].kept | di gate at percentile 0.999, kept | kept: 5479809 rows, target rate 0.2226011892020324 |
| 1443 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[6].refused | di gate at percentile 0.999, refused | refused: 2473633 rows, target rate 0.25299953550102217 |
| 1444 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[6].buy_kept | di gate at percentile 0.999, buy kept | buy_kept: 2974385 rows, target rate 0.2066820536009965 |
| 1445 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | di[6].buy_refused | di gate at percentile 0.999, buy refused | buy_refused: 1420428 rows, target rate 0.23685959443210075 |
| 1446 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[0].passing | anomaly at 0.95 and DI at 0.95, passing | passing: 419841 rows, target rate 0.20271483728363832 |
| 1447 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[0].passing_buy_calls | anomaly at 0.95 and DI at 0.95, passing buy calls | passing_buy_calls: 225926 rows, target rate 0.18997370820534157 |
| 1448 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[1].passing | anomaly at 0.95 and DI at 0.99, passing | passing: 1964945 rows, target rate 0.21244462313194518 |
| 1449 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[1].passing_buy_calls | anomaly at 0.95 and DI at 0.99, passing buy calls | passing_buy_calls: 1053953 rows, target rate 0.19807145100398216 |
| 1450 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[2].passing | anomaly at 0.95 and DI at 0.995, passing | passing: 3028950 rows, target rate 0.21491341884151274 |
| 1451 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[2].passing_buy_calls | anomaly at 0.95 and DI at 0.995, passing buy calls | passing_buy_calls: 1627704 rows, target rate 0.19919838004944387 |
| 1452 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[3].passing | anomaly at 0.99 and DI at 0.95, passing | passing: 422475 rows, target rate 0.2033587786259542 |
| 1453 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[3].passing_buy_calls | anomaly at 0.99 and DI at 0.95, passing buy calls | passing_buy_calls: 227176 rows, target rate 0.19074638166003452 |
| 1454 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[4].passing | anomaly at 0.99 and DI at 0.99, passing | passing: 1990436 rows, target rate 0.21358486281397643 |
| 1455 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[4].passing_buy_calls | anomaly at 0.99 and DI at 0.99, passing buy calls | passing_buy_calls: 1065908 rows, target rate 0.19937555586410835 |
| 1456 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[5].passing | anomaly at 0.99 and DI at 0.995, passing | passing: 3078432 rows, target rate 0.21632343998503134 |
| 1457 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[5].passing_buy_calls | anomaly at 0.99 and DI at 0.995, passing buy calls | passing_buy_calls: 1651313 rows, target rate 0.20085713610926578 |
| 1458 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[6].passing | anomaly at 0.995 and DI at 0.95, passing | passing: 422621 rows, target rate 0.20339263784809558 |
| 1459 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[6].passing_buy_calls | anomaly at 0.995 and DI at 0.95, passing buy calls | passing_buy_calls: 227227 rows, target rate 0.19080478992373265 |
| 1460 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[7].passing | anomaly at 0.995 and DI at 0.99, passing | passing: 1992532 rows, target rate 0.2136909219023835 |
| 1461 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[7].passing_buy_calls | anomaly at 0.995 and DI at 0.99, passing buy calls | passing_buy_calls: 1066692 rows, target rate 0.19950463676487684 |
| 1462 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[8].passing | anomaly at 0.995 and DI at 0.995, passing | passing: 3082914 rows, target rate 0.21647733280915393 |
| 1463 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | joint[8].passing_buy_calls | anomaly at 0.995 and DI at 0.995, passing buy calls | passing_buy_calls: 1653102 rows, target rate 0.20104688034979087 |
| 1464 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.anomaly | anomaly refusal for an incomplete vector, all folds | incomplete: 7989605 rows, target rate 0.2527690668061813 |
| 1465 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.di | di refusal for an incomplete vector, all folds | incomplete: 8025361 rows, target rate 0.2521700892956716 |
| 1466 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2017.anomaly_incomplete_share | anomaly incomplete, test year 2017 | share 0.26045232639234833 |
| 1467 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2017.buy_calls_di_incomplete_share | buy calls di incomplete, test year 2017 | share 0.27928953748673496 |
| 1468 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2017.di_incomplete_share | di incomplete, test year 2017 | share 0.2641227458403906 |
| 1469 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2018.anomaly_incomplete_share | anomaly incomplete, test year 2018 | share 0.324802262872731 |
| 1470 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2018.buy_calls_di_incomplete_share | buy calls di incomplete, test year 2018 | share 0.36073389193874605 |
| 1471 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2018.di_incomplete_share | di incomplete, test year 2018 | share 0.3255849067999426 |
| 1472 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2019.anomaly_incomplete_share | anomaly incomplete, test year 2019 | share 0.4587157853954489 |
| 1473 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2019.buy_calls_di_incomplete_share | buy calls di incomplete, test year 2019 | share 0.44522361222694057 |
| 1474 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2019.di_incomplete_share | di incomplete, test year 2019 | share 0.4603541296579467 |
| 1475 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2020.anomaly_incomplete_share | anomaly incomplete, test year 2020 | share 0.5105610142235111 |
| 1476 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2020.buy_calls_di_incomplete_share | buy calls di incomplete, test year 2020 | share 0.5193513490156499 |
| 1477 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2020.di_incomplete_share | di incomplete, test year 2020 | share 0.5114742980300947 |
| 1478 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2021.anomaly_incomplete_share | anomaly incomplete, test year 2021 | share 0.277238872387946 |
| 1479 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2021.buy_calls_di_incomplete_share | buy calls di incomplete, test year 2021 | share 0.278000176705408 |
| 1480 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2021.di_incomplete_share | di incomplete, test year 2021 | share 0.2800447698976433 |
| 1481 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2022.anomaly_incomplete_share | anomaly incomplete, test year 2022 | share 0.5141495044569863 |
| 1482 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2022.buy_calls_di_incomplete_share | buy calls di incomplete, test year 2022 | share 0.5361981070704379 |
| 1483 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2022.di_incomplete_share | di incomplete, test year 2022 | share 0.5171931934654573 |
| 1484 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2023.anomaly_incomplete_share | anomaly incomplete, test year 2023 | share 0.6036413543735245 |
| 1485 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2023.buy_calls_di_incomplete_share | buy calls di incomplete, test year 2023 | share 0.6160040381138066 |
| 1486 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2023.di_incomplete_share | di incomplete, test year 2023 | share 0.6059393404130196 |
| 1487 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2024.anomaly_incomplete_share | anomaly incomplete, test year 2024 | share 0.5405516613936008 |
| 1488 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2024.buy_calls_di_incomplete_share | buy calls di incomplete, test year 2024 | share 0.5365671872559367 |
| 1489 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2024.di_incomplete_share | di incomplete, test year 2024 | share 0.5423178173998616 |
| 1490 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2025.anomaly_incomplete_share | anomaly incomplete, test year 2025 | share 0.540729672518989 |
| 1491 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2025.buy_calls_di_incomplete_share | buy calls di incomplete, test year 2025 | share 0.09237726098191215 |
| 1492 | di_anomaly | docs/dataset/di-anomaly-distributions-2026-09-14.json | incomplete.by_year.2025.di_incomplete_share | di incomplete, test year 2025 | share 0.5416261984808866 |
| 1493 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.95.kept | DI with the any-pair 48-bar exclusion at 0.95, kept | kept: 7413465 rows, target rate 0.227606119405703 |
| 1494 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.95.refused | DI with the any-pair 48-bar exclusion at 0.95, refused | refused: 539977 rows, target rate 0.2931421153123189 |
| 1495 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.95.by_year.2017 | DI with the exclusion at 0.95, refused, test year 2017 | share 0.07572705117790414 |
| 1496 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.95.by_year.2018 | DI with the exclusion at 0.95, refused, test year 2018 | share 0.05747911326042098 |
| 1497 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.95.by_year.2019 | DI with the exclusion at 0.95, refused, test year 2019 | share 0.0860303748935504 |
| 1498 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.95.by_year.2020 | DI with the exclusion at 0.95, refused, test year 2020 | share 0.07633311473175883 |
| 1499 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.95.by_year.2021 | DI with the exclusion at 0.95, refused, test year 2021 | share 0.06398612421093844 |
| 1500 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.95.by_year.2022 | DI with the exclusion at 0.95, refused, test year 2022 | share 0.07707117144355978 |
| 1501 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.95.by_year.2023 | DI with the exclusion at 0.95, refused, test year 2023 | share 0.05125927908528141 |
| 1502 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.95.by_year.2024 | DI with the exclusion at 0.95, refused, test year 2024 | share 0.07237149008388963 |
| 1503 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.95.by_year.2025 | DI with the exclusion at 0.95, refused, test year 2025 | share 0.043246767358470065 |
| 1504 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.99.kept | DI with the any-pair 48-bar exclusion at 0.99, kept | kept: 7689977 rows, target rate 0.22961941238575875 |
| 1505 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.99.refused | DI with the any-pair 48-bar exclusion at 0.99, refused | refused: 263465 rows, target rate 0.3031598124988139 |
| 1506 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.99.by_year.2017 | DI with the exclusion at 0.99, refused, test year 2017 | share 0.03252640129975629 |
| 1507 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.99.by_year.2018 | DI with the exclusion at 0.99, refused, test year 2018 | share 0.01829152253976783 |
| 1508 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.99.by_year.2019 | DI with the exclusion at 0.99, refused, test year 2019 | share 0.0465819652411012 |
| 1509 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.99.by_year.2020 | DI with the exclusion at 0.99, refused, test year 2020 | share 0.032630543466226056 |
| 1510 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.99.by_year.2021 | DI with the exclusion at 0.99, refused, test year 2021 | share 0.02972629764559028 |
| 1511 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.99.by_year.2022 | DI with the exclusion at 0.99, refused, test year 2022 | share 0.05238689604023082 |
| 1512 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.99.by_year.2023 | DI with the exclusion at 0.99, refused, test year 2023 | share 0.01897958618135268 |
| 1513 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.99.by_year.2024 | DI with the exclusion at 0.99, refused, test year 2024 | share 0.032134513626657896 |
| 1514 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.99.by_year.2025 | DI with the exclusion at 0.99, refused, test year 2025 | share 0.00010866021949364337 |
| 1515 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.999.kept | DI with the any-pair 48-bar exclusion at 0.999, kept | kept: 7789472 rows, target rate 0.23035361061699688 |
| 1516 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.999.refused | DI with the any-pair 48-bar exclusion at 0.999, refused | refused: 163970 rows, target rate 0.3129047996584741 |
| 1517 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.999.by_year.2017 | DI with the exclusion at 0.999, refused, test year 2017 | share 0.01669103709721094 |
| 1518 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.999.by_year.2018 | DI with the exclusion at 0.999, refused, test year 2018 | share 0.006015082483497703 |
| 1519 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.999.by_year.2019 | DI with the exclusion at 0.999, refused, test year 2019 | share 0.030531465166634207 |
| 1520 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.999.by_year.2020 | DI with the exclusion at 0.999, refused, test year 2020 | share 0.01833698142454413 |
| 1521 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.999.by_year.2021 | DI with the exclusion at 0.999, refused, test year 2021 | share 0.01796251147205902 |
| 1522 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.999.by_year.2022 | DI with the exclusion at 0.999, refused, test year 2022 | share 0.04217607702982425 |
| 1523 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.999.by_year.2023 | DI with the exclusion at 0.999, refused, test year 2023 | share 0.011139971491081332 |
| 1524 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.999.by_year.2024 | DI with the exclusion at 0.999, refused, test year 2024 | share 0.015181711251684235 |
| 1525 | di_anomaly | docs/dataset/di-exclusion-refit-2026-09-15.json | percentiles.0.999.by_year.2025 | DI with the exclusion at 0.999, refused, test year 2025 | share 0.0 |
| 1526 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].any_pair_48_bars.out_of_sample_refused_at.0.5 | fold 20 DI, any pair 48 bars threshold at 0.5, refused | share 0.5265486725663717 |
| 1527 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].any_pair_48_bars.out_of_sample_refused_at.0.9 | fold 20 DI, any pair 48 bars threshold at 0.9, refused | share 0.1571758368603309 |
| 1528 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].any_pair_48_bars.out_of_sample_refused_at.0.95 | fold 20 DI, any pair 48 bars threshold at 0.95, refused | share 0.12543285879184302 |
| 1529 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].any_pair_48_bars.out_of_sample_refused_at.0.99 | fold 20 DI, any pair 48 bars threshold at 0.99, refused | share 0.1042708734128511 |
| 1530 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].any_pair_48_bars.out_of_sample_refused_at.0.999 | fold 20 DI, any pair 48 bars threshold at 0.999, refused | share 0.09426702577914582 |
| 1531 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].any_pair_7_days.out_of_sample_refused_at.0.5 | fold 20 DI, any pair 7 days threshold at 0.5, refused | share 0.4440169295883032 |
| 1532 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].any_pair_7_days.out_of_sample_refused_at.0.9 | fold 20 DI, any pair 7 days threshold at 0.9, refused | share 0.13447479799923048 |
| 1533 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].any_pair_7_days.out_of_sample_refused_at.0.95 | fold 20 DI, any pair 7 days threshold at 0.95, refused | share 0.11504424778761062 |
| 1534 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].any_pair_7_days.out_of_sample_refused_at.0.99 | fold 20 DI, any pair 7 days threshold at 0.99, refused | share 0.10023085802231628 |
| 1535 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].any_pair_7_days.out_of_sample_refused_at.0.999 | fold 20 DI, any pair 7 days threshold at 0.999, refused | share 0.09368988072335514 |
| 1536 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].leave_one_out.out_of_sample_refused_at.0.5 | fold 20 DI, leave one out threshold at 0.5, refused | share 0.9980761831473643 |
| 1537 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].leave_one_out.out_of_sample_refused_at.0.9 | fold 20 DI, leave one out threshold at 0.9, refused | share 0.9007310504040016 |
| 1538 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].leave_one_out.out_of_sample_refused_at.0.95 | fold 20 DI, leave one out threshold at 0.95, refused | share 0.7847248941900731 |
| 1539 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].leave_one_out.out_of_sample_refused_at.0.99 | fold 20 DI, leave one out threshold at 0.99, refused | share 0.4284340130819546 |
| 1540 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].leave_one_out.out_of_sample_refused_at.0.999 | fold 20 DI, leave one out threshold at 0.999, refused | share 0.17121969988457098 |
| 1541 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].same_pair_48_bars.out_of_sample_refused_at.0.5 | fold 20 DI, same pair 48 bars threshold at 0.5, refused | share 0.9957676029242016 |
| 1542 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].same_pair_48_bars.out_of_sample_refused_at.0.9 | fold 20 DI, same pair 48 bars threshold at 0.9, refused | share 0.8518661023470565 |
| 1543 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].same_pair_48_bars.out_of_sample_refused_at.0.95 | fold 20 DI, same pair 48 bars threshold at 0.95, refused | share 0.7191227395151981 |
| 1544 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].same_pair_48_bars.out_of_sample_refused_at.0.99 | fold 20 DI, same pair 48 bars threshold at 0.99, refused | share 0.28395536744901884 |
| 1545 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].same_pair_48_bars.out_of_sample_refused_at.0.999 | fold 20 DI, same pair 48 bars threshold at 0.999, refused | share 0.11966140823393613 |
| 1546 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].same_pair_7_days.out_of_sample_refused_at.0.5 | fold 20 DI, same pair 7 days threshold at 0.5, refused | share 0.9957676029242016 |
| 1547 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].same_pair_7_days.out_of_sample_refused_at.0.9 | fold 20 DI, same pair 7 days threshold at 0.9, refused | share 0.8505194305502116 |
| 1548 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].same_pair_7_days.out_of_sample_refused_at.0.95 | fold 20 DI, same pair 7 days threshold at 0.95, refused | share 0.7121969988457099 |
| 1549 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].same_pair_7_days.out_of_sample_refused_at.0.99 | fold 20 DI, same pair 7 days threshold at 0.99, refused | share 0.28395536744901884 |
| 1550 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [0].same_pair_7_days.out_of_sample_refused_at.0.999 | fold 20 DI, same pair 7 days threshold at 0.999, refused | share 0.11966140823393613 |
| 1551 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].any_pair_48_bars.out_of_sample_refused_at.0.5 | fold 100 DI, any pair 48 bars threshold at 0.5, refused | share 0.42102577188058177 |
| 1552 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].any_pair_48_bars.out_of_sample_refused_at.0.9 | fold 100 DI, any pair 48 bars threshold at 0.9, refused | share 0.08573615718295484 |
| 1553 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].any_pair_48_bars.out_of_sample_refused_at.0.95 | fold 100 DI, any pair 48 bars threshold at 0.95, refused | share 0.025006379178361827 |
| 1554 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].any_pair_48_bars.out_of_sample_refused_at.0.99 | fold 100 DI, any pair 48 bars threshold at 0.99, refused | share 0.0 |
| 1555 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].any_pair_48_bars.out_of_sample_refused_at.0.999 | fold 100 DI, any pair 48 bars threshold at 0.999, refused | share 0.0 |
| 1556 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].any_pair_7_days.out_of_sample_refused_at.0.5 | fold 100 DI, any pair 7 days threshold at 0.5, refused | share 0.34447563153865784 |
| 1557 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].any_pair_7_days.out_of_sample_refused_at.0.9 | fold 100 DI, any pair 7 days threshold at 0.9, refused | share 0.06659862209747384 |
| 1558 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].any_pair_7_days.out_of_sample_refused_at.0.95 | fold 100 DI, any pair 7 days threshold at 0.95, refused | share 0.01607552947180403 |
| 1559 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].any_pair_7_days.out_of_sample_refused_at.0.99 | fold 100 DI, any pair 7 days threshold at 0.99, refused | share 0.0 |
| 1560 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].any_pair_7_days.out_of_sample_refused_at.0.999 | fold 100 DI, any pair 7 days threshold at 0.999, refused | share 0.0 |
| 1561 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].leave_one_out.out_of_sample_refused_at.0.5 | fold 100 DI, leave one out threshold at 0.5, refused | share 0.9788211278387343 |
| 1562 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].leave_one_out.out_of_sample_refused_at.0.9 | fold 100 DI, leave one out threshold at 0.9, refused | share 0.7129369737177852 |
| 1563 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].leave_one_out.out_of_sample_refused_at.0.95 | fold 100 DI, leave one out threshold at 0.95, refused | share 0.514672110232202 |
| 1564 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].leave_one_out.out_of_sample_refused_at.0.99 | fold 100 DI, leave one out threshold at 0.99, refused | share 0.18601684103087524 |
| 1565 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].leave_one_out.out_of_sample_refused_at.0.999 | fold 100 DI, leave one out threshold at 0.999, refused | share 0.05690227098749681 |
| 1566 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].same_pair_48_bars.out_of_sample_refused_at.0.5 | fold 100 DI, same pair 48 bars threshold at 0.5, refused | share 0.9706557795355958 |
| 1567 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].same_pair_48_bars.out_of_sample_refused_at.0.9 | fold 100 DI, same pair 48 bars threshold at 0.9, refused | share 0.6440418474100535 |
| 1568 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].same_pair_48_bars.out_of_sample_refused_at.0.95 | fold 100 DI, same pair 48 bars threshold at 0.95, refused | share 0.43505996427660115 |
| 1569 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].same_pair_48_bars.out_of_sample_refused_at.0.99 | fold 100 DI, same pair 48 bars threshold at 0.99, refused | share 0.16764480734881348 |
| 1570 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].same_pair_48_bars.out_of_sample_refused_at.0.999 | fold 100 DI, same pair 48 bars threshold at 0.999, refused | share 0.053840265373819855 |
| 1571 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].same_pair_7_days.out_of_sample_refused_at.0.5 | fold 100 DI, same pair 7 days threshold at 0.5, refused | share 0.9706557795355958 |
| 1572 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].same_pair_7_days.out_of_sample_refused_at.0.9 | fold 100 DI, same pair 7 days threshold at 0.9, refused | share 0.6425108446032151 |
| 1573 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].same_pair_7_days.out_of_sample_refused_at.0.95 | fold 100 DI, same pair 7 days threshold at 0.95, refused | share 0.43046695585608574 |
| 1574 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].same_pair_7_days.out_of_sample_refused_at.0.99 | fold 100 DI, same pair 7 days threshold at 0.99, refused | share 0.16509313600408268 |
| 1575 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [1].same_pair_7_days.out_of_sample_refused_at.0.999 | fold 100 DI, same pair 7 days threshold at 0.999, refused | share 0.04720591987751978 |
| 1576 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].any_pair_48_bars.out_of_sample_refused_at.0.5 | fold 180 DI, any pair 48 bars threshold at 0.5, refused | share 0.3278220044907124 |
| 1577 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].any_pair_48_bars.out_of_sample_refused_at.0.9 | fold 180 DI, any pair 48 bars threshold at 0.9, refused | share 0.016329863237395388 |
| 1578 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].any_pair_48_bars.out_of_sample_refused_at.0.95 | fold 180 DI, any pair 48 bars threshold at 0.95, refused | share 0.0 |
| 1579 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].any_pair_48_bars.out_of_sample_refused_at.0.99 | fold 180 DI, any pair 48 bars threshold at 0.99, refused | share 0.0 |
| 1580 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].any_pair_48_bars.out_of_sample_refused_at.0.999 | fold 180 DI, any pair 48 bars threshold at 0.999, refused | share 0.0 |
| 1581 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].any_pair_7_days.out_of_sample_refused_at.0.5 | fold 180 DI, any pair 7 days threshold at 0.5, refused | share 0.24903041437027965 |
| 1582 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].any_pair_7_days.out_of_sample_refused_at.0.9 | fold 180 DI, any pair 7 days threshold at 0.9, refused | share 0.006327822004490713 |
| 1583 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].any_pair_7_days.out_of_sample_refused_at.0.95 | fold 180 DI, any pair 7 days threshold at 0.95, refused | share 0.0 |
| 1584 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].any_pair_7_days.out_of_sample_refused_at.0.99 | fold 180 DI, any pair 7 days threshold at 0.99, refused | share 0.0 |
| 1585 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].any_pair_7_days.out_of_sample_refused_at.0.999 | fold 180 DI, any pair 7 days threshold at 0.999, refused | share 0.0 |
| 1586 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].leave_one_out.out_of_sample_refused_at.0.5 | fold 180 DI, leave one out threshold at 0.5, refused | share 0.9997958767095325 |
| 1587 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].leave_one_out.out_of_sample_refused_at.0.9 | fold 180 DI, leave one out threshold at 0.9, refused | share 0.9696876913655849 |
| 1588 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].leave_one_out.out_of_sample_refused_at.0.95 | fold 180 DI, leave one out threshold at 0.95, refused | share 0.9093692590324556 |
| 1589 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].leave_one_out.out_of_sample_refused_at.0.99 | fold 180 DI, leave one out threshold at 0.99, refused | share 0.57542355582772 |
| 1590 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].leave_one_out.out_of_sample_refused_at.0.999 | fold 180 DI, leave one out threshold at 0.999, refused | share 0.0877730149010002 |
| 1591 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].same_pair_48_bars.out_of_sample_refused_at.0.5 | fold 180 DI, same pair 48 bars threshold at 0.5, refused | share 0.9996938150642989 |
| 1592 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].same_pair_48_bars.out_of_sample_refused_at.0.9 | fold 180 DI, same pair 48 bars threshold at 0.9, refused | share 0.9642784241681976 |
| 1593 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].same_pair_48_bars.out_of_sample_refused_at.0.95 | fold 180 DI, same pair 48 bars threshold at 0.95, refused | share 0.9005919575423555 |
| 1594 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].same_pair_48_bars.out_of_sample_refused_at.0.99 | fold 180 DI, same pair 48 bars threshold at 0.99, refused | share 0.49438660951214536 |
| 1595 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].same_pair_48_bars.out_of_sample_refused_at.0.999 | fold 180 DI, same pair 48 bars threshold at 0.999, refused | share 0.08491528883445601 |
| 1596 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].same_pair_7_days.out_of_sample_refused_at.0.5 | fold 180 DI, same pair 7 days threshold at 0.5, refused | share 0.9996938150642989 |
| 1597 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].same_pair_7_days.out_of_sample_refused_at.0.9 | fold 180 DI, same pair 7 days threshold at 0.9, refused | share 0.9642784241681976 |
| 1598 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].same_pair_7_days.out_of_sample_refused_at.0.95 | fold 180 DI, same pair 7 days threshold at 0.95, refused | share 0.9005919575423555 |
| 1599 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].same_pair_7_days.out_of_sample_refused_at.0.99 | fold 180 DI, same pair 7 days threshold at 0.99, refused | share 0.49438660951214536 |
| 1600 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [2].same_pair_7_days.out_of_sample_refused_at.0.999 | fold 180 DI, same pair 7 days threshold at 0.999, refused | share 0.08369054909165136 |
| 1601 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].any_pair_48_bars.out_of_sample_refused_at.0.5 | fold 260 DI, any pair 48 bars threshold at 0.5, refused | share 0.37388964909432476 |
| 1602 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].any_pair_48_bars.out_of_sample_refused_at.0.9 | fold 260 DI, any pair 48 bars threshold at 0.9, refused | share 0.0984994317786488 |
| 1603 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].any_pair_48_bars.out_of_sample_refused_at.0.95 | fold 260 DI, any pair 48 bars threshold at 0.95, refused | share 0.08205580165595937 |
| 1604 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].any_pair_48_bars.out_of_sample_refused_at.0.99 | fold 260 DI, any pair 48 bars threshold at 0.99, refused | share 0.07788111417770253 |
| 1605 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].any_pair_48_bars.out_of_sample_refused_at.0.999 | fold 260 DI, any pair 48 bars threshold at 0.999, refused | share 0.03817519771783751 |
| 1606 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].any_pair_7_days.out_of_sample_refused_at.0.5 | fold 260 DI, any pair 7 days threshold at 0.5, refused | share 0.3057726650741007 |
| 1607 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].any_pair_7_days.out_of_sample_refused_at.0.9 | fold 260 DI, any pair 7 days threshold at 0.9, refused | share 0.09110095785884918 |
| 1608 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].any_pair_7_days.out_of_sample_refused_at.0.95 | fold 260 DI, any pair 7 days threshold at 0.95, refused | share 0.08117447874388292 |
| 1609 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].any_pair_7_days.out_of_sample_refused_at.0.99 | fold 260 DI, any pair 7 days threshold at 0.99, refused | share 0.07788111417770253 |
| 1610 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].any_pair_7_days.out_of_sample_refused_at.0.999 | fold 260 DI, any pair 7 days threshold at 0.999, refused | share 0.022125843634761232 |
| 1611 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].leave_one_out.out_of_sample_refused_at.0.5 | fold 260 DI, leave one out threshold at 0.5, refused | share 1.0 |
| 1612 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].leave_one_out.out_of_sample_refused_at.0.9 | fold 260 DI, leave one out threshold at 0.9, refused | share 0.9915810469188487 |
| 1613 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].leave_one_out.out_of_sample_refused_at.0.95 | fold 260 DI, leave one out threshold at 0.95, refused | share 0.964561541851242 |
| 1614 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].leave_one_out.out_of_sample_refused_at.0.99 | fold 260 DI, leave one out threshold at 0.99, refused | share 0.6709186631722986 |
| 1615 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].leave_one_out.out_of_sample_refused_at.0.999 | fold 260 DI, leave one out threshold at 0.999, refused | share 0.4369970081406406 |
| 1616 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].same_pair_48_bars.out_of_sample_refused_at.0.5 | fold 260 DI, same pair 48 bars threshold at 0.5, refused | share 1.0 |
| 1617 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].same_pair_48_bars.out_of_sample_refused_at.0.9 | fold 260 DI, same pair 48 bars threshold at 0.9, refused | share 0.9907924948396224 |
| 1618 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].same_pair_48_bars.out_of_sample_refused_at.0.95 | fold 260 DI, same pair 48 bars threshold at 0.95, refused | share 0.955725120022265 |
| 1619 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].same_pair_48_bars.out_of_sample_refused_at.0.99 | fold 260 DI, same pair 48 bars threshold at 0.99, refused | share 0.6479346893336735 |
| 1620 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].same_pair_48_bars.out_of_sample_refused_at.0.999 | fold 260 DI, same pair 48 bars threshold at 0.999, refused | share 0.4297144977619037 |
| 1621 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].same_pair_7_days.out_of_sample_refused_at.0.5 | fold 260 DI, same pair 7 days threshold at 0.5, refused | share 1.0 |
| 1622 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].same_pair_7_days.out_of_sample_refused_at.0.9 | fold 260 DI, same pair 7 days threshold at 0.9, refused | share 0.9907924948396224 |
| 1623 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].same_pair_7_days.out_of_sample_refused_at.0.95 | fold 260 DI, same pair 7 days threshold at 0.95, refused | share 0.955725120022265 |
| 1624 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].same_pair_7_days.out_of_sample_refused_at.0.99 | fold 260 DI, same pair 7 days threshold at 0.99, refused | share 0.6479346893336735 |
| 1625 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [3].same_pair_7_days.out_of_sample_refused_at.0.999 | fold 260 DI, same pair 7 days threshold at 0.999, refused | share 0.4297144977619037 |
| 1626 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].any_pair_48_bars.out_of_sample_refused_at.0.5 | fold 340 DI, any pair 48 bars threshold at 0.5, refused | share 0.4054820894766175 |
| 1627 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].any_pair_48_bars.out_of_sample_refused_at.0.9 | fold 340 DI, any pair 48 bars threshold at 0.9, refused | share 0.04970360237118103 |
| 1628 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].any_pair_48_bars.out_of_sample_refused_at.0.95 | fold 340 DI, any pair 48 bars threshold at 0.95, refused | share 0.020621168363986423 |
| 1629 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].any_pair_48_bars.out_of_sample_refused_at.0.99 | fold 340 DI, any pair 48 bars threshold at 0.99, refused | share 0.003850635861579774 |
| 1630 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].any_pair_48_bars.out_of_sample_refused_at.0.999 | fold 340 DI, any pair 48 bars threshold at 0.999, refused | share 0.0015199878400972793 |
| 1631 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].any_pair_7_days.out_of_sample_refused_at.0.5 | fold 340 DI, any pair 7 days threshold at 0.5, refused | share 0.3102295181638547 |
| 1632 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].any_pair_7_days.out_of_sample_refused_at.0.9 | fold 340 DI, any pair 7 days threshold at 0.9, refused | share 0.03587171302629579 |
| 1633 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].any_pair_7_days.out_of_sample_refused_at.0.95 | fold 340 DI, any pair 7 days threshold at 0.95, refused | share 0.013933221867558392 |
| 1634 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].any_pair_7_days.out_of_sample_refused_at.0.99 | fold 340 DI, any pair 7 days threshold at 0.99, refused | share 0.0022293154988093427 |
| 1635 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].any_pair_7_days.out_of_sample_refused_at.0.999 | fold 340 DI, any pair 7 days threshold at 0.999, refused | share 0.0012159902720778233 |
| 1636 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].leave_one_out.out_of_sample_refused_at.0.5 | fold 340 DI, leave one out threshold at 0.5, refused | share 0.9993413386026245 |
| 1637 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].leave_one_out.out_of_sample_refused_at.0.9 | fold 340 DI, leave one out threshold at 0.9, refused | share 0.9641282869737042 |
| 1638 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].leave_one_out.out_of_sample_refused_at.0.95 | fold 340 DI, leave one out threshold at 0.95, refused | share 0.8995288037695699 |
| 1639 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].leave_one_out.out_of_sample_refused_at.0.99 | fold 340 DI, leave one out threshold at 0.99, refused | share 0.6266403202107717 |
| 1640 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].leave_one_out.out_of_sample_refused_at.0.999 | fold 340 DI, leave one out threshold at 0.999, refused | share 0.24431271216496936 |
| 1641 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].same_pair_48_bars.out_of_sample_refused_at.0.5 | fold 340 DI, same pair 48 bars threshold at 0.5, refused | share 0.9993413386026245 |
| 1642 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].same_pair_48_bars.out_of_sample_refused_at.0.9 | fold 340 DI, same pair 48 bars threshold at 0.9, refused | share 0.9622029690429144 |
| 1643 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].same_pair_48_bars.out_of_sample_refused_at.0.95 | fold 340 DI, same pair 48 bars threshold at 0.95, refused | share 0.8881795612301768 |
| 1644 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].same_pair_48_bars.out_of_sample_refused_at.0.99 | fold 340 DI, same pair 48 bars threshold at 0.99, refused | share 0.5551502254648629 |
| 1645 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].same_pair_48_bars.out_of_sample_refused_at.0.999 | fold 340 DI, same pair 48 bars threshold at 0.999, refused | share 0.16192937123169682 |
| 1646 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].same_pair_7_days.out_of_sample_refused_at.0.5 | fold 340 DI, same pair 7 days threshold at 0.5, refused | share 0.9993413386026245 |
| 1647 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].same_pair_7_days.out_of_sample_refused_at.0.9 | fold 340 DI, same pair 7 days threshold at 0.9, refused | share 0.9622029690429144 |
| 1648 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].same_pair_7_days.out_of_sample_refused_at.0.95 | fold 340 DI, same pair 7 days threshold at 0.95, refused | share 0.8881795612301768 |
| 1649 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].same_pair_7_days.out_of_sample_refused_at.0.99 | fold 340 DI, same pair 7 days threshold at 0.99, refused | share 0.5551502254648629 |
| 1650 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [4].same_pair_7_days.out_of_sample_refused_at.0.999 | fold 340 DI, same pair 7 days threshold at 0.999, refused | share 0.16192937123169682 |
| 1651 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].any_pair_48_bars.out_of_sample_refused_at.0.5 | fold 404 DI, any pair 48 bars threshold at 0.5, refused | share 0.3738645271360723 |
| 1652 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].any_pair_48_bars.out_of_sample_refused_at.0.9 | fold 404 DI, any pair 48 bars threshold at 0.9, refused | share 0.040923133674551575 |
| 1653 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].any_pair_48_bars.out_of_sample_refused_at.0.95 | fold 404 DI, any pair 48 bars threshold at 0.95, refused | share 0.019135887859086088 |
| 1654 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].any_pair_48_bars.out_of_sample_refused_at.0.99 | fold 404 DI, any pair 48 bars threshold at 0.99, refused | share 0.0012910960483238807 |
| 1655 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].any_pair_48_bars.out_of_sample_refused_at.0.999 | fold 404 DI, any pair 48 bars threshold at 0.999, refused | share 0.00018444229261769724 |
| 1656 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].any_pair_7_days.out_of_sample_refused_at.0.5 | fold 404 DI, any pair 7 days threshold at 0.5, refused | share 0.29047355558629595 |
| 1657 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].any_pair_7_days.out_of_sample_refused_at.0.9 | fold 404 DI, any pair 7 days threshold at 0.9, refused | share 0.028703831788629133 |
| 1658 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].any_pair_7_days.out_of_sample_refused_at.0.95 | fold 404 DI, any pair 7 days threshold at 0.95, refused | share 0.011066537557061834 |
| 1659 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].any_pair_7_days.out_of_sample_refused_at.0.99 | fold 404 DI, any pair 7 days threshold at 0.99, refused | share 0.0006686033107391524 |
| 1660 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].any_pair_7_days.out_of_sample_refused_at.0.999 | fold 404 DI, any pair 7 days threshold at 0.999, refused | share 0.0 |
| 1661 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].leave_one_out.out_of_sample_refused_at.0.5 | fold 404 DI, leave one out threshold at 0.5, refused | share 1.0 |
| 1662 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].leave_one_out.out_of_sample_refused_at.0.9 | fold 404 DI, leave one out threshold at 0.9, refused | share 1.0 |
| 1663 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].leave_one_out.out_of_sample_refused_at.0.95 | fold 404 DI, leave one out threshold at 0.95, refused | share 0.9993775072624153 |
| 1664 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].leave_one_out.out_of_sample_refused_at.0.99 | fold 404 DI, leave one out threshold at 0.99, refused | share 0.9656706782865311 |
| 1665 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].leave_one_out.out_of_sample_refused_at.0.999 | fold 404 DI, leave one out threshold at 0.999, refused | share 0.5548485267671878 |
| 1666 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].same_pair_48_bars.out_of_sample_refused_at.0.5 | fold 404 DI, same pair 48 bars threshold at 0.5, refused | share 1.0 |
| 1667 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].same_pair_48_bars.out_of_sample_refused_at.0.9 | fold 404 DI, same pair 48 bars threshold at 0.9, refused | share 1.0 |
| 1668 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].same_pair_48_bars.out_of_sample_refused_at.0.95 | fold 404 DI, same pair 48 bars threshold at 0.95, refused | share 0.9992622308295293 |
| 1669 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].same_pair_48_bars.out_of_sample_refused_at.0.99 | fold 404 DI, same pair 48 bars threshold at 0.99, refused | share 0.9619818324341771 |
| 1670 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].same_pair_48_bars.out_of_sample_refused_at.0.999 | fold 404 DI, same pair 48 bars threshold at 0.999, refused | share 0.49707197860469404 |
| 1671 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].same_pair_7_days.out_of_sample_refused_at.0.5 | fold 404 DI, same pair 7 days threshold at 0.5, refused | share 1.0 |
| 1672 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].same_pair_7_days.out_of_sample_refused_at.0.9 | fold 404 DI, same pair 7 days threshold at 0.9, refused | share 1.0 |
| 1673 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].same_pair_7_days.out_of_sample_refused_at.0.95 | fold 404 DI, same pair 7 days threshold at 0.95, refused | share 0.9992622308295293 |
| 1674 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].same_pair_7_days.out_of_sample_refused_at.0.99 | fold 404 DI, same pair 7 days threshold at 0.99, refused | share 0.9619818324341771 |
| 1675 | di_anomaly | docs/dataset/di-serial-correlation-check-2026-09-15.json | [5].same_pair_7_days.out_of_sample_refused_at.0.999 | fold 404 DI, same pair 7 days threshold at 0.999, refused | share 0.49707197860469404 |
| 1676 | phase_7_runs | feature-specs/143-the-simulation-run.md | tier 3, expected_move | chain simulation, folds 379-404, tier 3, ranked by expected_move | counted before launch; the count is fixed before any simulated figure exists |
| 1677 | phase_7_runs | feature-specs/143-the-simulation-run.md | tier 5, expected_move | chain simulation, folds 379-404, tier 5, ranked by expected_move | counted before launch; the count is fixed before any simulated figure exists |
| 1678 | phase_7_runs | feature-specs/143-the-simulation-run.md | tier 3, alphabetical | chain simulation, folds 379-404, tier 3, ranked by alphabetical | counted before launch; the count is fixed before any simulated figure exists |
| 1679 | phase_7_runs | feature-specs/143-the-simulation-run.md | tier 5, alphabetical | chain simulation, folds 379-404, tier 5, ranked by alphabetical | counted before launch; the count is fixed before any simulated figure exists |
