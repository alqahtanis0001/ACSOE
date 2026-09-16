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
positive, so `1 / brier` gives a model that is *worse than always predicting the base rate*
a perfectly respectable weight. Spec 67's first real run came in at or slightly worse than
base rate on two folds of three, so that is not hypothetical. Neither inverse-Brier nor a
rank ordering can express spec 97's own requirement that a model failing to beat its base
rate gets weight zero — the worst of three models still ranks third, and third of three is
a weight.

**Why an unweighted mean across folds.** The question is *how good is this model version*,
and each fold is one out-of-sample measurement of it. A most-recent-fold rule encodes a
judgement about recency; a fold-count-weighted mean quietly rewards a version for having
been around longer. An unweighted mean is the only one of the three that does not add a
second, unstated judgement to the one being asked. On the real table today all three agree,
because each version has exactly one fold — the fixture is what exercises the difference.

**`base_rate_brier` is a column, not a derivation.** It cannot be recomputed from
`win_rate`: `brier` and `base_rate_brier` are computed over **every** fold row while
`win_rate` is over the **BUY subset** only, so a skill score built from those two divides
quantities measured on different populations — in range, plausible, and wrong in whichever
direction the BUY subset leans. Engine 20 already computes the base rate per fold and
discarded it for want of somewhere to put it; migration 0004 adds the column.

**A version whose base rate cannot be read gets weight zero and is named in the basis**,
never a defaulted base rate. Choosing a default is choosing the line at which a model counts
as having edge, and that is the operator's.

## The regime and the DI margin are provenance, and were considered

Spec 97 has this engine read `state["regime"]["label"]`, and it does — into `basis` and the
published `regime`, so an operator can see which market the weights were published in. It
changes none of them, and the same goes for `di_margin`.

Conditioning a weight on regime requires per-regime metrics. The leaderboard holds **one**
Brier per model version over the whole out-of-sample window, with no regime breakdown
anywhere in the schema. A regime adjustment invented on top of that would be a methodology
choice with no measurement behind it — which is where specs 70 and 72 both stopped rather
than walking past, and stopping where the measurement stops is why this project's numbers
are worth anything. Assented by the lead, 2026-09-16.

## Reading the leaderboard, and the one refusal that matters

| Reason code | When |
|---|---|
| `leaderboard_empty` | no rows at all. A fresh clone, and not an error |
| `leaderboard_unreadable` | no store, or no enumerating read on it |
| `leaderboard_truncated` | a read came back **exactly full**, so rows beyond it exist and were not looked at |
| `no_model_beats_its_base_rate` | every version scored at or below its own base rate |

`leaderboard_truncated` is the one worth understanding. Spec 97 named
`leaderboard_entries(...)`, which is B's *existence check* for engine 20's idempotency and
takes `model_version` as an argument — you cannot enumerate versions with it. The only
enumerating read that exists today is the console's `leaderboard(limit=...)`, which
truncates, and weighting from a truncated window is the defect B's own docstring warns
about arriving at a different caller: **the weights would still sum to one, over the wrong
set.** A version outside the window would be absent *because nobody looked*, not zero
because it had no edge, and nothing downstream could tell those apart.

So a full window publishes no weights at all. When B's non-truncating read lands the check
stays rather than being deleted with the fallback — it is then the assertion that the
fallback is unreachable, which is this project's standing rule for a workaround whose cause
has since been fixed.

## What it never does

- **Never selects, loads or swaps the model engine 8 uses.** `models.prediction_run_id` is
  the operator's; `active_model_run_id` is an echo of what engine 8 already did.
- **Never blocks and never approves.** Every path that ran returns `OK`.
- **Never persists a previous bar's DI.** That is the tracker's open schema question.
- **Never weights across model families.** Only rows whose `model_id` is this engine's own
  are read. There is one family today, which is exactly why weighting across them would
  have gone unnoticed: normalising over a second family's score would hand it part of the
  predictor's weight.
