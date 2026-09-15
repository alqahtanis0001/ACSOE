# Skeptic veto sweep, run `train-20260913T205245-067b2b9d`

**Evidence for the operator's ruling on `skeptic.veto_threshold`. It recommends nothing and sets nothing.** Covers 405 of 457 folds (the run died at fold 405; see the digest's `coverage`).

Each fold's own trained skeptic applied to that fold's out-of-sample BUY calls, scored by the trainer's own `_skeptic_matrix` on the commit that trained them. A call **survives when P(wrong) ≤ threshold**. Script `docs/dataset/skeptic-veto-sweep-2026-09-14.py` (sha256 `2b03e4f7d8b01ebd3cd2f6f5feaab67f170d298292731e1018710ab958db1556`), results `docs/dataset/skeptic-veto-sweep-2026-09-14.json`.

- All test rows: target rate **0.2422**.
- All BUY calls: **8,950,912**, target rate **0.2383**.
- Scored (folds 1 to 404, the folds with a skeptic): **8,948,485** BUY calls, target rate **0.2383**, effective sample size **933,453**. Fold 0 has no skeptic (no earlier calls): 2,427 calls, not scored.

| veto threshold | survivors | share | survivors' effective size | survivor target rate (± s.e. by effective size) | vetoed | vetoed effective size | vetoed target rate | no-skill band (20 permutations) |
|---|---|---|---|---|---|---|---|---|
| 0.30 | 9,373 | 0.10% | 3,243 | 0.6349 ± 0.0085 | 8,939,112 | 930,210 | 0.2379 | 0.2711 to 0.2892 |
| 0.35 | 24,888 | 0.28% | 8,857 | 0.6313 ± 0.0051 | 8,923,597 | 924,596 | 0.2372 | 0.2632 to 0.2722 |
| 0.40 | 51,145 | 0.57% | 17,778 | 0.6035 ± 0.0037 | 8,897,340 | 915,674 | 0.2362 | 0.2563 to 0.2621 |
| 0.45 | 88,931 | 0.99% | 29,238 | 0.5693 ± 0.0029 | 8,859,554 | 904,215 | 0.2350 | 0.2545 to 0.2605 |
| 0.50 | 154,979 | 1.73% | 46,616 | 0.5309 ± 0.0023 | 8,793,506 | 886,837 | 0.2331 | 0.2550 to 0.2596 |
| 0.55 | 289,977 | 3.24% | 77,151 | 0.4877 ± 0.0018 | 8,658,508 | 856,302 | 0.2300 | 0.2574 to 0.2610 |
| 0.60 | 583,121 | 6.52% | 132,708 | 0.4403 ± 0.0014 | 8,365,364 | 800,744 | 0.2242 | 0.2602 to 0.2629 |
| 0.65 | 1,265,683 | 14.14% | 238,275 | 0.3928 ± 0.0010 | 7,682,802 | 695,178 | 0.2128 | 0.2636 to 0.2649 |
| 0.70 | 2,859,743 | 31.96% | 439,499 | 0.3482 ± 0.0007 | 6,088,742 | 493,954 | 0.1867 | 0.2645 to 0.2653 |

**Reading it.** The survivor target rate is above 0.2383 at every threshold, from +0.110 (0.70) to +0.397 (0.30). The fair comparison is the no-skill band, not 0.2383: vetoing the same number of calls per fold at random already lifts the rate to about 0.26, because folds differ in how many calls survive and in their own target rates. The survivors clear the band's maximum at every threshold, by +0.083 (0.70) to +0.346 (0.30). **All rates are before friction**; break-even is `(stop_pct + friction) / (target_pct + stop_pct)` and friction is live-only. The standard error is a floor: it ignores correlation between pairs and between folds.

## By test year, at 0.50, 0.60 and 0.70

| year | threshold | survivors | effective size | survivor target rate | vetoed target rate |
|---|---|---|---|---|---|
| 2017 | 0.50 | 16,655 | 3,684 | 0.4837 | 0.2675 |
| 2017 | 0.60 | 33,811 | 6,387 | 0.4311 | 0.2475 |
| 2017 | 0.70 | 63,609 | 10,268 | 0.3845 | 0.2099 |
| 2018 | 0.50 | 5,376 | 1,221 | 0.4325 | 0.2210 |
| 2018 | 0.60 | 16,425 | 2,900 | 0.3986 | 0.2092 |
| 2018 | 0.70 | 50,336 | 6,707 | 0.3516 | 0.1746 |
| 2019 | 0.50 | 3,135 | 621 | 0.4469 | 0.1939 |
| 2019 | 0.60 | 12,018 | 1,800 | 0.3939 | 0.1873 |
| 2019 | 0.70 | 46,106 | 5,125 | 0.3282 | 0.1684 |
| 2020 | 0.50 | 6,718 | 1,937 | 0.5082 | 0.2033 |
| 2020 | 0.60 | 31,395 | 6,399 | 0.4176 | 0.1957 |
| 2020 | 0.70 | 151,611 | 21,111 | 0.3421 | 0.1652 |
| 2021 | 0.50 | 24,844 | 6,508 | 0.5017 | 0.2534 |
| 2021 | 0.60 | 109,814 | 22,137 | 0.4255 | 0.2421 |
| 2021 | 0.70 | 490,815 | 71,622 | 0.3547 | 0.1953 |
| 2022 | 0.50 | 27,072 | 8,855 | 0.5034 | 0.2291 |
| 2022 | 0.60 | 113,035 | 26,180 | 0.4115 | 0.2213 |
| 2022 | 0.70 | 566,383 | 86,297 | 0.3329 | 0.1874 |
| 2023 | 0.50 | 30,054 | 10,269 | 0.5821 | 0.2208 |
| 2023 | 0.60 | 100,358 | 26,381 | 0.4729 | 0.2140 |
| 2023 | 0.70 | 552,641 | 90,221 | 0.3473 | 0.1857 |
| 2024 | 0.50 | 41,125 | 13,522 | 0.5714 | 0.2485 |
| 2024 | 0.60 | 166,265 | 40,526 | 0.4636 | 0.2387 |
| 2024 | 0.70 | 938,242 | 148,147 | 0.3538 | 0.1925 |

## Proof the check can fail: a different fold's skeptic

| rows of fold | skeptic of fold | BUY calls | mean abs. P(wrong) diff | threshold | own survivors | other survivors | verdicts that differ | own survivor rate | other survivor rate |
|---|---|---|---|---|---|---|---|---|---|
| 404 | 403 | 3,685 | 0.0008 | 0.50 | 25 | 24 | 1 | 0.8400 | 0.8333 |
| 404 | 403 | 3,685 | 0.0008 | 0.60 | 26 | 26 | 0 | 0.8462 | 0.8462 |
| 404 | 403 | 3,685 | 0.0008 | 0.70 | 26 | 26 | 0 | 0.8462 | 0.8462 |
| 404 | 250 | 3,685 | 0.0026 | 0.50 | 25 | 18 | 7 | 0.8400 | 0.8333 |
| 404 | 250 | 3,685 | 0.0026 | 0.60 | 26 | 25 | 1 | 0.8462 | 0.8400 |
| 404 | 250 | 3,685 | 0.0026 | 0.70 | 26 | 26 | 0 | 0.8462 | 0.8462 |
| 300 | 150 | 16,083 | 0.0273 | 0.50 | 243 | 419 | 236 | 0.5802 | 0.5465 |
| 300 | 150 | 16,083 | 0.0273 | 0.60 | 583 | 792 | 283 | 0.5266 | 0.5025 |
| 300 | 150 | 16,083 | 0.0273 | 0.70 | 1,209 | 1,669 | 674 | 0.4491 | 0.4062 |
| 200 | 350 | 11,689 | 0.0430 | 0.50 | 719 | 400 | 765 | 0.5772 | 0.6325 |
| 200 | 350 | 11,689 | 0.0430 | 0.60 | 2,072 | 1,902 | 1,790 | 0.5458 | 0.6099 |
| 200 | 350 | 11,689 | 0.0430 | 0.70 | 5,275 | 5,752 | 1,485 | 0.5029 | 0.5315 |

Adjacent skeptics (404 and 403) share all but a few hundred of their ~8.9 million training rows and barely differ, as they should; distant ones differ in hundreds to over a thousand verdicts. Fold 200's calls scored by fold 350's skeptic, **which trained on fold 200's own rows**, reach a *higher* survivor rate (0.6325) than fold 200's own out-of-sample skeptic (0.5772): the measurement moves the way contamination would move it.

## Leak check: which rows each skeptic trained on

`docs/dataset/skeptic-training-identity-check-2026-09-14.py` recomputes each skeptic's eligible training set from the out-of-sample file with the trainer's rule (earlier folds' BUY calls, label window ending before this fold's test window, decision bar before its 48-bar embargo) and compares its identity with the manifest's `training_identity`:

| fold | recorded rows | recomputed rows | identity | rows reaching the test window | without purge and embargo |
|---|---|---|---|---|---|
| 1 | 2,252 | 2,252 | match | 0 | 2,427 rows, differs |
| 50 | 161,642 | 161,642 | match | 0 | 161,687 rows, differs |
| 150 | 616,394 | 616,394 | match | 0 | 617,471 rows, differs |
| 250 | 2,501,826 | 2,501,826 | match | 0 | 2,502,638 rows, differs |
| 300 | 4,232,186 | 4,232,186 | match | 0 | 4,233,064 rows, differs |
| 350 | 6,254,723 | 6,254,723 | match | 0 | 6,261,019 rows, differs |
| 404 | 8,946,942 | 8,946,942 | match | 0 | 8,947,227 rows, differs |
