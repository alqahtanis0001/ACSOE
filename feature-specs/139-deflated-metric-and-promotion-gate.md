# 139 — The deflated metric and the promotion gate

**Owner:** C — Interface and models (engine 20 `tournament`)

**Phase:** 7. The Phase 7 row's second criterion. Engine 20 has promoted nothing since Phase 5.

## Goal

A model is promotable only if its edge survives a haircut for the number of configurations tried
on the same data. The gate rejects a model that does not survive, and records why.

## Implementation

1. **The deflated metric:** the deflated Sharpe ratio (Bailey and López de Prado), computed from
   the run's per-period returns, with the skew and kurtosis terms and the number of trials as
   inputs. The formula is cited in the module docstring, and its arithmetic is held to a worked
   example.
2. **The trial count, RULED 2026-09-19 (R9), broader than the lead's proposal.** Every configuration
   ever evaluated against the out-of-sample data counts as a trial. **Each is listed explicitly,
   one row per trial, not summarised.** The ledger is committed at
   `docs/dataset/phase-7-trial-ledger.json` (with a readable `.md` beside it). Each row names the
   configuration, the file that evaluated it, and the line or cell. It covers at least:
   - every leaderboard row;
   - every cell of every reconnaissance grid in `docs/dataset/phase-7-recon-2026-09-19/`
     (rankings × frictions × spread arms × skeptic variants × thresholds × windows, as each script
     actually ran them);
   - every feature and direction in the ranking study (`docs/dataset/ranking-study-2026-09-14*`);
   - every threshold in the skeptic veto sweep, and in the skeptic-against-`p_target` comparison;
   - every DI and anomaly percentile compared on the out-of-sample rows (0.95, 0.99 and 0.999 for
     the DI, both with and without the exclusion; 0.95 and 0.99 for the anomaly gate);
   - this phase's two rankings at two tiers: four trials.

   **Count conservatively, and say so in the ledger.** Where it is unclear whether two evaluations
   are one trial or two, count two. An overstated count makes the haircut harsher and the result
   harder to claim, which is the right direction to err. The ledger states the rule, and every
   judgement it made under the rule. The ledger is built by a script that reads the committed outputs
   and emits one row per cell. **It is not typed by hand.** A test plants an extra cell in a copy of
   one output and requires the count to rise by one.
3. **The gate** lives in engine 20. It reads the leaderboard, the run's report (spec 138) and the
   ledger's trial count. It writes `promoted` true only when step 4's bar is met. Otherwise it writes
   a reason code, mapped in `REASON_PROSE` in the same change. The deflated Sharpe ratio of step 1 is
   computed and reported beside the verdict, whatever the verdict.
4. **The bar, RULED 2026-09-19 before anything runs (R10). Its working form was ruled the same day
   (R10b), as proposed:** the interval is computed allowing for overlapping holds, then widened for
   trials, and a model is promoted only if the lower bound is above zero. The operator notes that
   this is stricter than the original wording, which is correct. **The statistics below are fixed by
   this spec.** They are committed as code with a worked example before any simulated figure
   exists, and they are not revisited after one does.
   - **The quantity.** Each closed trade's net return: `realised_pnl` divided by the entry
     notional. That is after both fees, the spread and slippage, exactly as the run recorded them.
     Liquidations count; nothing is excluded.
   - **Overlapping holds: HAC (Newey–West, Bartlett kernel)** on the per-trade series in entry
     order. **The lag is the largest number of other trades whose hold overlaps any single trade's
     hold.** It is computed from entry and exit times alone, before any return is read, so it cannot
     be chosen after seeing the answer.
   - **Widened for trials: Bonferroni over N**, where N is the ledger's count (step 2). The two-sided
     interval is taken at confidence 1 − 0.05 / N, with the Student-t quantile at n − 1 degrees of
     freedom for n trades.
   - **Promote only if** `mean − q × SE_HAC > 0`. With fewer than ten trades there is no interval,
     the model is not promoted, and the reason code says why.
   - *Rejected: a block bootstrap over clusters of overlapping trades.* At the trade counts
     expected (tens), there are few clusters and the bootstrap distribution is coarse. It also adds
     a seed and a resample count as further choices.
   - *Rejected: widening by the deflated Sharpe ratio's expected-maximum offset.* That needs the
     variance of Sharpe ratios across the trials. Most ledger rows are trade counts or target rates,
     not return series, so the variance would have to be estimated from inputs the ledger cannot
     supply. Bonferroni needs only N, and it stays conservative whatever the dependence between
     trials. That matches the ruling's direction: err towards harder to claim.

## Scope Limits

- Promotion never changes which model the running system uses. `models.*_run_id` stays the
  operator's key, and invariant 4 is untouched.
- No model output feeds the gate's decision except through the returns it is judging.

## Check When Done

- A fabricated model whose unwidened 95% lower bound is above zero but whose Bonferroni-widened
  bound is not, given the ledger's trial count, is rejected with its reason. The same model with a
  trial count of one is promoted.
- A fabricated series of overlapping trades whose naive (independent) interval excludes zero while
  its HAC interval does not is rejected. Setting the lag to zero is a planted defect that must turn
  this test red.
- A worked example, computed by hand in the module docstring, is equal to the code's output.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
