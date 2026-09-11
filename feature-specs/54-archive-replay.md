# 54 — Replay: archive in, decision bars out

**Owner:** A — Platform

**Phase:** 4. `research/replay.py`, `scripts/` and `data/` are A under the permanent
ownership map.

## Goal

`src/acsoe/research/replay.py` reads one or more Kraken OHLCVT archives through the Phase 2
loader and yields the decision-bar series the labeller consumes, with an injected clock and
no network. Plus the thing that has been missing since Phase 2: **an archive to replay.**

## The archive problem, stated plainly rather than worked around

`data/historical/` is empty. The Kraken downloadable OHLCVT archives have not been obtained,
the operator has rotated the API key, and no live call can be made. What the repository does
have is roughly three days of **real** Kraken WebSocket v2 trade frames in `data/raw/`,
recorded by `scripts/record.py` since Phase 0.

So: build archive-shaped CSVs from those real trades, with the provenance recorded in the
artefact and in the build log, and let `--live` be the criterion that proves the six-month
path when the operator supplies a real archive.

**What must not happen is a synthesised price series.** Every bar must come from real
recorded trades. This is the same standard `scripts/ohlc_fixture.py` already meets and says
out loud: the trades are real, the reduction is ours, and that is weaker than an independent
source — so it is written down rather than implied.

## Implementation

1. A script under `scripts/` that reduces `data/raw/` JSONL trade frames into Kraken-archive-
   shaped 15-minute OHLCVT CSVs in `data/historical/`, one file per pair, no header, columns
   in the order `research/historical.py` already defines. De-duplicate at the **frame** level
   and by exact bytes, never at the trade level — two recorders produce byte-identical frames,
   two genuinely identical trades arrive inside one frame. `scripts/ohlc_fixture.py` already
   solved this; reuse the reasoning.
2. **Never write into `data/raw/`.** Invariant 11: recorded data is immutable, corrections
   live in a derived layer.
3. **A quiet 15-minute interval produces no row**, exactly as a Kraken archive contains only
   intervals in which trades occurred. Emitting a zero-volume bar at the previous close is
   interpolation wearing a different hat, and it fabricates the barrier touches Phase 4
   labels. `research/historical.py` says why at length; do not undo it here.
4. `research/replay.py` — load one or more archives through `load_archive`, expose the gap
   report alongside the frame, and yield decision bars in timestamp order with an injected
   clock. **Offline only**: it imports nothing from `acsoe.engines`, `acsoe.core`,
   `acsoe.clients` or `acsoe.cli`, and nothing there imports it. Architecture invariant 5.
5. `tests/research/test_replay.py`, A lane.

## Rules this spec is held to

- **Every assertion must be proven capable of failing**, with the exact mutation and the exact
  red message recorded in `docs/build-log/phase-4/a-platform.md`. Name at least: the quiet
  interval emitting a filled row; frame de-duplication moved to the trade level; the bar
  boundary off by one interval.
- The no-interpolation assertion must be **separate** from any count assertion. A reducer that
  fills holes and a reducer that does not can produce the same row count on a series with no
  holes — so the test needs a series with holes and must assert on the timestamps.

## Scope Limits

- Do **not** label anything. Spec 52 is C.
- Do **not** split folds. Spec 53 is C.
- Do **not** commit anything under `data/`. It is gitignored and a criterion may never depend
  on it.
- Do **not** edit `research/labelling.py` or `research/walkforward.py`. They are C.
- Do **not** re-run or restart `scripts/record.py` in a way that interrupts it. It has been
  running since Phase 0 and order-book history cannot be recovered retroactively.

## Check When Done

- An archive exists under `data/historical/` and `research/historical.py` loads it with an
  honest gap report.
- `replay_full_archive` reports PENDING without `--live` and does something real with it.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 4`
