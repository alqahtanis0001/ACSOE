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

**It never promotes a fold's row.** `promoted` is false on every per-fold row. Promotion is a
different question from "which model scored best", answered by the gate below over a run's
real trades, and it writes a row of its own.

**It computes no Sharpe, no deflated Sharpe, no alpha and no beta on a fold's row.** A Sharpe
over label returns with no friction, no position sizing and no holding period is not a worse
Sharpe — it is a different quantity wearing the name, and somebody who did not write it would
read it as the real one.

## The promotion gate, spec 139

`TournamentEngine(promote_run_id=..., ledger_path=...)` judges one finished run instead of
scoring a digest. It reads:

| Source | Used for |
|---|---|
| `StoreClient.recent_closed_trades(limit=...)`, filtered to the run | every closed trade of the run; the read asks for one row more than `PROMOTION_TRADE_CAP` and refuses if it gets it, because a truncated window is a different run |
| the trial ledger, `docs/dataset/phase-7-trial-ledger.json` | `trial_count`, refused unless it equals the number of rows beside it |

Each trade's net return is `realised_pnl / (qty x entry_price)`, recomputed from the row, never
read from `realised_pnl_pct`. The bar is `modelling/promotion.py`'s, fixed by spec 139 before
any simulated figure existed: HAC (Newey-West, Bartlett kernel) on the per-trade series in entry
order, the lag the largest number of other trades overlapping any one hold, Bonferroni over the
ledger's count, promoted only if `mean - q x SE_HAC > 0`, and no interval below ten trades.

It writes **one** leaderboard row per judged run: `model_id` `chain_run`, `model_version` the
run id, `fold` null, `promoted`, the per-trade Sharpe, the deflated Sharpe ratio (reported beside
the verdict, never deciding it), and `notes` as JSON with the reason code, every figure the
bar computed, and the effective sample size `n x (se_naive / se_hac)^2` (capped at `n`) the
leaderboard screen shows (spec 140). A second judgement of the same run writes nothing. Promotion changes nothing the
running system does: `models.*_run_id` stays the operator's key.

**It writes no relational row but `leaderboard`.**

## Idempotent, and the existence read matters

A `(model_id, model_version, fold)` already present is not written twice, and the engine
reports how many rows it wrote and how many it found.

The check is `StoreClient.leaderboard_entries`, which B-2 added for this. Deciding "have I
written this fold already" from `leaderboard()` — the console's newest-fifty read — would
silently start writing duplicates on the fifty-first fold, and a duplicate row looks exactly
like a second training run.

## The Brier extremes carry their base rates

`data` reports the best and worst fold by Brier, **each with that fold's own base-rate Brier
beside it**. A Brier alone says nothing: 0.18 is excellent against a base rate of 50% and poor
against one of 5%, so a report without the comparison ranks which folds had the rarest
targets.

**An empty fold gets no row.** The trainer reports a fold with no training or no test rows as
empty (`is_empty: true`, `run_id: null`) and writes no artefact for it; a leaderboard row names
a model version somebody could weight or promote, so a row for it would name a directory that
does not exist, with a `net_pnl` of exactly zero reading as a model that broke even. They are
counted in `data["folds_empty"]`. A non-empty fold whose entry has lost its `run_id` is refused
rather than given an invented version.

## The refusals

| Reason code | When |
|---|---|
| `tournament_no_digest` | no `--digest`, or a path that is not a readable training digest |
| `tournament_no_oos` | the out-of-sample file is absent, unreadable, or missing a column |
| `tournament_no_store` | no store client, so there is nowhere to write |
| `tournament_digest_mismatch` | the digest and the out-of-sample file disagree about a fold; nothing is written |
| `promotion_no_ledger` | the gate has no trial ledger, or its count disagrees with its rows; nothing is written |
| `promotion_bad_trade` | a trade has no entry notional, or is not in the reporting currency; nothing is written |

The gate's two verdict codes are not refusals: the engine returns `OK` and the code is on the
row. `promotion_too_few_trades` (fewer than ten) and `promotion_lower_bound_not_above_zero`.

The last is a block rather than a silent skip. A research run that reported success having
written nothing is the failure this engine exists to make impossible, and Phase 6's router
would then weight by an empty table.

## The constructor seam

`TournamentEngine(*, digest_path: Path | None = None)`, keyword-only, agreed by name with A-2.
`cli/research.py` resolves this class by name and raises loudly if the keyword does not exist
rather than falling back to a no-argument call — which is how engine 23 spent a phase green
against a labeller signature that never existed.
