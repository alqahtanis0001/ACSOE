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

**It never promotes.** `promoted` is always false. The promotion gate is Phase 7 and it is a
different question from "which model scored best": a model can top this table and still fail
on stability, on sample size, or on an operator's judgement about the period it was fitted in.

**It computes no Sharpe, no deflated Sharpe, no alpha and no beta.** A Sharpe over label
returns with no friction, no position sizing and no holding period is not a worse Sharpe — it
is a different quantity wearing the name, and somebody who did not write it would read it as
the real one.

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

## The four refusals

| Reason code | When |
|---|---|
| `tournament_no_digest` | no `--digest`, or a path that is not a readable training digest |
| `tournament_no_oos` | the out-of-sample file is absent, unreadable, or missing a column |
| `tournament_no_store` | no store client, so there is nowhere to write |
| `tournament_digest_mismatch` | the digest and the out-of-sample file disagree about a fold; nothing is written |

The last is a block rather than a silent skip. A research run that reported success having
written nothing is the failure this engine exists to make impossible, and Phase 6's router
would then weight by an empty table.

## The constructor seam

`TournamentEngine(*, digest_path: Path | None = None)`, keyword-only, agreed by name with A-2.
`cli/research.py` resolves this class by name and raises loudly if the keyword does not exist
rather than falling back to a no-argument call — which is how engine 23 spent a phase green
against a labeller signature that never existed.
