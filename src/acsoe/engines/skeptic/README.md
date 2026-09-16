# Engine 15 — `skeptic`

**Number:** 15 · **Chain:** opportunity, the last gate before the decision · **Gate:** yes ·
**Runtime stage:** 3

A learned opinion about this specific trade: how likely is the predictor's BUY call to be
wrong. Above `skeptic.veto_threshold` the call is vetoed.

This is meta-labelling. The predictor says what it thinks will happen; the skeptic is trained
on the predictor's own out-of-sample BUY calls with the label `wrong = label != "target"`, so
it learns **when that call is wrong** rather than re-learning the market. Spec 69 built it.

## It can only veto

There is no output of this engine that makes a trade more likely. `state["skeptic"]` carries
`pair`, `model_run_id`, `p_wrong`, `threshold`, `vetoed`, `reason` and `reason_code` — no
`approved`, no confidence, no margin a downstream engine could widen a threshold with.

Invariant 4: a model output may refuse a trade and may never authorise one. That is written
into the published shape rather than into a rule, because a rule is a thing somebody can
forget while a missing field is a thing that cannot be read.

## It reads the prediction, and engine 13 must not

The two model gates are deliberate opposites.

| | reads the prediction | judges |
|---|---|---|
| 13 `anomaly` | no, and its contracts module has no name for one | the market |
| 15 `skeptic` | yes, that is its whole job | the predictor's call |

A skeptic that could not see the call could not grade it. An anomaly gate that could would be
a second opinion about the trade wearing a data-quality badge.

## What it reads from `state`

| Key | Publisher | Used for |
|---|---|---|
| `state["prediction"]["is_buy"]` | 8 `prediction` (C) | whether there is a call to grade |
| `state["prediction"]["p_target"]`, `["p_stop"]`, `["p_timeout"]` | 8 `prediction` (C) | three of the four extra inputs |
| `state["prediction"]["expected_move_pct"]` | 8 `prediction` (C) | the fourth, parsed from its decimal string |
| `state["feature"]["pairs"][pair]` | 5 `feature` (C) | the feature half of the vector |
| `state["scout"]["pair"]` | 7 `scout` (B) | the candidate, when the prediction names none |

The input order is the **manifest's** recorded `skeptic.input_names`: the feature list
followed by the three probabilities and the expected move. Engine 15 rebuilds exactly that
and refuses an artefact recording anything else. A vector assembled in the wrong order is
every value in range and every value in the wrong column.

`expected_move_pct` crosses `state` as an exact decimal string, because engine 10 does
`Decimal` arithmetic with it. The skeptic was trained on a float, so this engine parses it —
in one place, through `float`, not through a `Decimal` round trip.

## A non-BUY call is `OK`, not a block

The skeptic grades BUY calls. Asked about a call nobody made it is answering a different
question, so it returns `OK` with `vetoed: false` and `reason: "not a BUY call"`.

**Turning a non-BUY into no trade is the decision engine's job in Phase 6.** A `BLOCK` here
would write a veto into the one table the research reads that never happened, and the
leaderboard would then attribute to the skeptic every bar the predictor simply did not like.
The reason is still recorded, because "the skeptic was reached and had nothing to say" is
different from "the skeptic did not run".

**Only an explicit `is_buy: false` takes this path.** An absent `is_buy`, a `None`, or any
value that is not a boolean (`"true"`, `1`) is not a non-BUY call: it is engine 8 having made
no call at all, and this gate blocks with `skeptic_unavailable` rather than reading the
absence of a "no" as a pass. Invariant 3.

Since spec 95 engine 8 **omits** `is_buy` on every refusal and publishes it only when the
model scored, so the absence now says which of the two happened rather than merely being
unusable. The block did not change and must not — it landed in spec 73, a phase before the
payload did, and it is the reason nothing failed open in between. Only the sentence changed:
it names engine 8's refusal instead of saying this gate cannot tell.

With no candidate pair at all — neither `state["prediction"]["pair"]` nor
`state["scout"]["pair"]` — the engine returns `PASS`: there is nothing on this tick to grade.

## The two refusals

| Reason code | When |
|---|---|
| `skeptic_unavailable` | an absent or non-boolean `is_buy`, no `skeptic.veto_threshold`, no `models.skeptic_run_id`, no directory, a failed hash, a fold that produced no skeptic, no `skeptic.txt`, an unrebuildable input order, an incomplete input vector, or a non-finite `p_wrong` |
| `skeptic_veto` | `p_wrong` above the threshold |

**A veto's reason prints `p_wrong` and the threshold so they can be told apart.** It uses six
significant digits, or more when six would print the two numbers identically. A fixed four
decimal places once produced "0.0000 likely to be wrong against a veto threshold of 0.0000",
which is a refusal that doesn't show its score was over the line.

**A non-finite `p_wrong` blocks before it is compared.** `nan > threshold` is `False`, so a
comparison alone would pass every call a broken model scored as NaN.

**An absent threshold blocks; it does not pass.** A learned veto with no threshold cannot
tell a bad call from a good one, and failing open would mean the one gate meant to catch the
predictor's mistakes is the one gate not running.

**A fold with no skeptic is a reported absence, not a fault.** Spec 69: the first fold of
every run has no earlier out-of-sample BUY calls to learn from and correctly trains none. A
gate that guessed in its place would be a coin flip with a manifest.

## The score's direction

`p_wrong` is the probability the call is **wrong**. LightGBM's binary objective returns the
probability of the positive class, and the positive class here is `wrong`. Reading it as the
probability the call is right would veto exactly the good calls, at a rate that looks
entirely plausible and with nothing anywhere to notice.

## It never learns

Nothing here trains, adapts, or reads the store for outcomes. The model is the artefact's and
the threshold is the operator's config. Live learning is out of scope for this phase and
would make every leaderboard row a statement about a model that no longer exists.
