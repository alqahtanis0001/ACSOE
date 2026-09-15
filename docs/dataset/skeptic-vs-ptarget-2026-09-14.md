# Skeptic against the predictor's own confidence, at matched counts

**Evidence for the operator's ruling on `skeptic.veto_threshold`; recommends nothing, sets nothing.** Run `train-20260913T205245-067b2b9d`, 405 of 457 folds; folds 1 to 404 carry a skeptic.

For each threshold and each fold, N is exactly that fold's skeptic survivor count (P(wrong) ≤ threshold). The comparator takes that fold's top N out-of-sample BUY calls by the predictor's calibrated `p_target`, ties at the cut broken at random (two seeds; the second agrees to within 0.0004 everywhere). Script `docs/dataset/skeptic-vs-ptarget-2026-09-14.py` (sha256 `e857bd4dbea414325a5747fc5ee4d4d5c32f0128831a95c75ca69c45521afc09`), results in the `.json` beside it. Scored: 8,948,485 BUY calls, target rate 0.2383, effective size 933,453.

| threshold | N | skeptic target rate | skeptic effective size | top-N by p_target target rate | p_target effective size | skeptic minus p_target | calls in both sets | rows tied at the cuts | random top-N (effective size) |
|---|---|---|---|---|---|---|---|---|---|
| 0.30 | 9,373 | 0.6349 ± 0.0085 | 3,243 | 0.5605 ± 0.0090 | 3,009 | +0.0744 | 2,729 (29%) | 2,358 | 0.2798 (1,273) |
| 0.35 | 24,888 | 0.6313 ± 0.0051 | 8,857 | 0.5560 ± 0.0056 | 7,808 | +0.0753 | 8,269 (33%) | 3,316 | 0.2665 (3,161) |
| 0.40 | 51,145 | 0.6035 ± 0.0037 | 17,778 | 0.5305 ± 0.0040 | 15,450 | +0.0729 | 19,874 (39%) | 6,845 | 0.2581 (6,270) |
| 0.45 | 88,931 | 0.5693 ± 0.0029 | 29,238 | 0.5025 ± 0.0031 | 25,530 | +0.0667 | 37,805 (43%) | 12,438 | 0.2544 (10,995) |
| 0.50 | 154,979 | 0.5309 ± 0.0023 | 46,616 | 0.4731 ± 0.0025 | 41,218 | +0.0578 | 67,551 (44%) | 14,377 | 0.2564 (19,045) |
| 0.55 | 289,977 | 0.4877 ± 0.0018 | 77,151 | 0.4419 ± 0.0019 | 69,943 | +0.0459 | 127,791 (44%) | 19,356 | 0.2588 (35,466) |
| 0.60 | 583,121 | 0.4403 ± 0.0014 | 132,708 | 0.4097 ± 0.0014 | 126,085 | +0.0306 | 274,712 (47%) | 26,609 | 0.2611 (70,297) |
| 0.65 | 1,265,683 | 0.3928 ± 0.0010 | 238,275 | 0.3780 ± 0.0010 | 239,748 | +0.0148 | 680,962 (54%) | 36,787 | 0.2638 (149,183) |
| 0.70 | 2,859,743 | 0.3482 ± 0.0007 | 439,499 | 0.3433 ± 0.0007 | 455,129 | +0.0049 | 1,933,153 (68%) | 42,824 | 0.2647 (328,267) |

**Proof the comparison can fail.** The same top-N machinery ranked by the skeptic's own score (lowest P(wrong) first) selected **the identical set** as the skeptic at all nine thresholds, so the matching reproduces a ranker exactly when given that ranker's order. Ranked at random, it lands at 0.254 to 0.280, in the no-skill band. The p_target comparator therefore measures the difference between two rankings and nothing else.

**Reading it.** The skeptic's survivors hit their target more often than the same number of the predictor's most confident calls at every threshold: by +0.074 at 0.30, +0.058 at 0.50, +0.031 at 0.60, +0.015 at 0.65, and +0.005 at 0.70, where the two sets share 68% of their calls and the margin is within a few floor standard errors. The predictor's own confidence is itself a strong ranker (0.47 at the 0.50 count against 0.24 for all BUY calls). The BUY rule `expected_move_pct > 0` passes 56% of bars, far too many for that ranking to show. All rates are before friction; the standard errors ignore correlation between pairs and folds and are floors.
