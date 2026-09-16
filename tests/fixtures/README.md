# tests/fixtures

Committed evidence for `scripts/verify.py`. Small, redacted, and reproducible on a
fresh clone.

## Why these files are committed at all

Several phase criteria concern behaviour that is live, long-running, or both — a
recorder that must run for a day, a soak that must run for a week, a labelled
slice replayed from six months of archives. None of that can run inside a phase
gate, and every criterion has to pass offline on a fresh clone with no API key.

So the gate checks a **committed artefact produced by the real run**, and the real
run itself is verified by `--live`, which is opt-in and never required for a phase
to be green. A criterion that only passes on the machine that produced it is a
broken criterion.

`data/`, `models/` and `logs/` are gitignored, so nothing here may point into them.

## Who deposits what

Each agent deposits the evidence for its own criteria. Depositing a file you
produced is not writing in C's lane; C owns the *structure* of this directory and
the shared fixtures, not its contents.

| File | Agent | Criterion | Phase |
|---|---|---|---|
| `record_sample.jsonl` | A | `record_sample_valid` | 0 |
| `recording_report.json` | A | continuous 24h span with every break accounted for | 2 |
| `soak_digest.json` | A | one unbroken `run_id`, contiguous `cycle_id`s, 7 days | 8 |
| `labelled_sample.parquet` | C | `labelled_sample_replayed_from_archive` | 4 |
| `labels_hand_verified.json` | C | `labeller_matches_hand_verified_labels` | 4 |
| `candles_sample.parquet` | C | `features_reproduce_in_replay` and the Phase 5 training criteria | 5 |
| `walkforward_digest.json` | C | `walkforward_weekly_retrain_reports_oos` | 5 |
| `book_sample.jsonl` | C | engine 9 `order_book`'s slippage walk, on a thin and a deep pair | 6 |
| `leaderboard_sample.json` | C | engine 14 `adaptive_router`'s weighting rule | 6 |
| `kraken/*.json` | C | recorded responses backing the fake Kraken client | 0 |

`walkforward_digest.json` is the **partial** digest of the full 234-pair run `train-20260913T205245-067b2b9d`: 405 of 457 folds, because the run died in the skeptic's uncapped matrix build at fold 405. It was rebuilt from the 405 fold artefacts by `docs/dataset/rebuild-walkforward-2026-09-14.py`, every fold reproduced against its manifest, and its own `coverage` block says so (operator ruling 2026-09-14).

`book_sample.jsonl` is 30 seconds of live Kraken v2 order-book traffic for **ADA/USD and
BTC/USD**, cut from `data/raw/kraken_v2__msi__2026-09-16.jsonl` by A's
`scripts/cut_book_fixture.py` (spec 86) and copied byte for byte. Two pairs because spec 96
requires the walk hand-checked on a **thin** book and a **deep** one, and `book_too_thin` is
only reachable against a ladder that genuinely runs out inside the fetched depth. Line 1 is a
header object, not a recorded line: it carries the window, the pairs, per-pair frame counts by
type, and a sha256 of the body. Its own reader skips it.

**The window opens 48 ms after a reconnect, and that is the whole of its correctness.** Kraken
v2 sends book **deltas** — a `qty` of `0.0` deletes a level, anything else replaces one — and
the only absolute book is a `type: "snapshot"` frame, which arrives *only at subscribe*. A cut
taken from a quiet moment mid-stream is therefore full of real, well-formed, byte-exact frames
and still cannot say what the bid side was at any instant: reconstruction would start from an
empty book, fill in only the levels that happened to change, and produce a plausible four- or
five-level ladder that a slippage walk prices as far thinner than the market was. That is a
wrong answer in range, running in the direction that makes the cost gate refuse for a
fabricated reason. So the window opens at `00:17:06.100000Z`, which does **not** intersect the
gap interval the cutter refuses on and **does** contain one `snapshot` per pair ahead of every
delta: `ADA/USD` 1 snapshot and 451 updates, `BTC/USD` 1 snapshot and 524 updates.

**What it does not validate, stated here as well as in the engine's README.** Thirty seconds of
two pairs on one day. The historical archive carries no book at all, so there is no way to
extend this across regimes, sizes or years, and every slippage number this system reports
inherits that bound.

`leaderboard_sample.json` is **fabricated, and it is the one file here that is.** Its
`provenance` field says so in capitals inside the file, and a test asserts that: these rows
describe no trained model and no real run, and a reader who took them for a measurement
would conclude the predictor beats its base rate by a wide margin.

It is fabricated because the real leaderboard **cannot** exercise engine 14's weighting
rule. The walk-forward trains one predictor per fold and the fold's artefact run id *is*
the model version, so every real version has exactly one row: the unweighted mean across
folds, the most recent fold and a fold-count-weighted mean all give the same answer, one
model family means the family filter never fires, and a single version always weighs 1.0.
Every one of those is a branch that would be green and unreached.

So each row carries a `why` field naming the single property it exists to make observable,
and a test asserts every row has one: a two-fold version so the mean is actually computed;
a superseded duplicate of one `(version, fold)` whose brier would move the weight a long
way if it were averaged as a second fold or allowed to win; a version worse than its own
base rate, which must score zero **and** must not inflate the others by shrinking the
denominator; and a second `model_id` carrying the best score in the file, which must be
excluded entirely. The expected weights are recomputed in the test from the rows by a
second implementation of the rule — the `expected` block in the file is for a human
reading it and the test does not import it.

`labelled_sample.parquet` carries its own provenance **inside the file**, as parquet
key-value metadata under `acsoe_provenance`: which archive, which span, the barrier
settings it was labelled under, how many of its labels were decided by the
both-barriers-touched ruling, and the statement that the source carries no spread and no
book. A parquet that cannot say where it came from is indistinguishable from one written
by hand, and `labelled_sample_replayed_from_archive` is written to notice.

`candles_sample.parquet` is the **input** `labelled_sample.parquet` is the output of: the
OHLCVT slice of the same pair and span, taken from the operator's archive through
`research/historical.py` and sliced on `ts`, with nothing recomputed and no bar invented. It
exists because the labelled sample carries no `open`, `high`, `low`, `volume` or `trades`, so
there was nothing committed for `modelling/features.py` to consume and every Phase 5 training
criterion had no input. It reaches back `market_sensor.published_bars` bars before the first
labelled decision bar, so that bar has a full lookback behind it, and forward
`barriers.timeout_bars` past the last, so every labelled row's window is covered.

**Its one hole is deliberate and load-bearing.** The slice spans 1,209 fifteen-minute slots and
holds 1,208 bars: the archive records no trades in one of them. Nothing fills it. A lookback
that is a window of time and a lookback that is a count of rows return the same answer on every
contiguous series ever written, and differ only across a hole — so a fixture without one cannot
tell the correct implementation from the defect `feature_lookbacks_are_time_not_rows` exists to
catch. Its provenance block records `missing_bars`, and a rebuild that smooths the hole away has
broken the fixture rather than cleaned it.

`labels_hand_verified.json` carries **its own candle windows**. The archive lives under
`data/historical/`, which is gitignored, so a criterion that read it would pass only on
the machine that downloaded it. Each entry's window runs from the decision bar to the
timeout horizon plus one candle — the least context in which "does the series cover this
window" is answerable, which matters because three entries were wrongly excluded when the
window stopped exactly at the horizon.

`kraken/` holds `asset_pairs.json`, `balance.json`, `order_book.json` and
`trade_volume.json` — the recorded responses `tests/harness/fake_kraken.py` serves.
They are test fixtures for a fake exchange and **never** values the system falls
back on: no fee, minimum, tick size or precision in this directory is a system
default. Invariant 2 has no exceptions.

## Committability

`.gitignore` carries `*.jsonl`, `*.parquet` and `*.sqlite`, because `data/` is
large and reveals account activity. A `!tests/fixtures/**` negation re-admits
everything here. That negation is load-bearing and easy to lose, so
`tests/harness/test_fixture_tracking.py` asserts it in both directions: these paths
are not ignored, and the same extensions outside this directory still are.

`.gitattributes` marks `tests/fixtures/**` as `-text` so a Windows clone cannot
rewrite the bytes. Git's CRLF heuristic guessing wrong on a Parquet payload
corrupts it; on a JSONL sample it changes the byte count a validator reads.

## Rules

- Redact before you commit. No key, no signature, no nonce, no account balance —
  these files go into a public repository and into a dissertation.
- Keep them small. Evidence, not a dataset.
- Never generate one by hand to make a criterion pass. The artefact's whole value
  is that a real run produced it.
