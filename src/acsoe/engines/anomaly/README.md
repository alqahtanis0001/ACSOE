# Engine 13 — `anomaly`

**Number:** 13 · **Chain:** opportunity, after engine 12 and before engine 15 ·
**Gate:** yes · **Runtime stage:** 3

Asks one question: **is the candidate's market broken.** Scores the bar's market-quality
features against an unsupervised outlier model fitted per fold by `research/training.py`,
and blocks when the score is above that artefact's own threshold.

## It judges the market, not the trade

This is a data-quality gate, in the same family as `data_guard`. It can only veto — there is
no output of this engine that makes a trade more likely — and it has no way to form an
opinion about the candidate, because it cannot see one.

That last part is structural rather than a matter of discipline. `contracts.py` names
`state["scout"]` and `state["feature"]` and nothing else; contract rule 3 means an engine
reaches another engine's keys only by naming them, so this engine could not read a
probability if somebody wanted it to. A gate that could see the prediction would be a gate
with an opinion about the trade, which invariant 4 keeps out of the gate chain.

## No spread, and that is stated rather than implied

`trading-invariants.md` describes this engine's inputs as velocity, volume and spread. The
historical archive is OHLCVT and carries no book at all, so the detector was never fitted on
a spread, and scoring a live vector that carried one would be scoring against a model that
has never seen that column. The absence is recorded in every manifest under
`extras["anomaly"]["spread_input"]`. If a spread is wanted later it is a stop and a question
for the operator, not a reach for the recorder.

## What it reads from `state`

| Key | Publisher | Used for |
|---|---|---|
| `state["scout"]["pair"]` | 7 `scout` (B) | the candidate. Absent → `PASS` |
| `state["feature"]["pairs"][pair]` | 5 `feature` (C) | the market-quality features |
| `state["feature"]["bar_ts"]` | 5 `feature` (C) | the decision bar, echoed |

The inputs are `modelling/features.MARKET_QUALITY_FEATURES`: velocity, volume and
trade-count z-scores, range measures, and the lookback fill counters. The order is the
**artefact's** recorded `input_names`, checked at load against that set.

## What it publishes

`state["anomaly"]` carries `pair`, `bar_ts`, `model_run_id`, `score`, `threshold`,
`anomalous` and `reason_code`.

## The three refusals

| Reason code | When |
|---|---|
| `anomaly_unavailable` | no `models.anomaly_run_id`, no directory, a failed hash, an artefact with no detector, an artefact with no recorded threshold, or one fitted on a different input set |
| `anomaly_inputs_incomplete` | a market-quality feature arrived null, NaN or infinite |
| `market_anomalous` | the score is above the artefact's threshold |

## The threshold is the artefact's, and the artefact's is the operator's

Nothing is learned or adapted live. The threshold was computed at training time as the
`anomaly.threshold_percentile` quantile of that fold's own training scores, and that key is
absent from `config/default.yaml` by ruling. A run trained without it records no threshold
and this engine blocks: a data-quality gate that cannot tell a broken market from an ordinary
one has no basis for letting anything through.

**Read the build-log entries of 2026-09-13 before choosing that percentile.** Measured on the
live path, with a bar carrying ten sigma of volume and ten times the trades:

| | score | quantile of the training scores |
|---|---|---|
| the ordinary bar | 0.5210 | 0.607 |
| the same bar, spiked | 0.5263 | 0.664 |
| threshold at 0.85 | 0.5491 | — |

The spike reaches the features — `volume_z_96` moves from 1.53 to 6.93 — and the score moves
by five thousandths. **There is no percentile at which this detector both blocks that bar and
passes an ordinary one**: the threshold that separates them sits around 0.63, where the gate
would also refuse 37% of ordinary bars.

The cause is the model rather than the wiring. An isolation forest does not isolate an extreme
point in one split: the split value is drawn inside the node's own data range, so a point
beyond the training maximum travels outward *with* the largest training points and is isolated
only when that tail thins to one. Its depth is bounded by the size of the tail, not by how far
outside it sits, which is why the score is identical at ten sigma, a hundred and a thousand.

That is a design question for the operator, not something engine 13 can fix: this engine
compares a score against the artefact's threshold, and it does that correctly.

## The score's direction

**Larger is more anomalous, and above the threshold blocks.** `score_samples` returns the
opposite sign, so the negation is written once, in `_score`, and the artefact records the
orientation in its own manifest. A sign that flipped between the trainer and this engine
would produce a gate that blocks exactly the ordinary markets and passes the broken ones,
with a refusal rate that looks entirely reasonable.

## The one binary artefact

`anomaly.joblib` is the only file in a run directory that is not text, because scikit-learn
has no text dump for an isolation forest. `load_run` verifies its sha256 against the manifest
before this engine unpickles it. That defends against a swapped file, not against a hostile
original, and the limit is stated here rather than left to be assumed from the presence of a
hash.
