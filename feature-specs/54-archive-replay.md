# 54 — Replay: archive in, decision bars out

**Owner:** A — Platform

**Phase:** 4. `research/replay.py`, `scripts/` and `data/` are A under the permanent
ownership map.

## Goal

`src/acsoe/research/replay.py` reads one or more Kraken OHLCVT archives through the Phase 2
loader and yields the decision-bar series the labeller consumes, with an injected clock and
no network. Plus the thing that has been missing since Phase 2: **an archive to replay.**

## AMENDED 2026-09-11 — the operator has supplied the real archive

The original version of this spec worked around an empty `data/historical/` by reducing
`data/raw/` into archive-shaped CSVs. **That workaround is retired.** The operator has
supplied Kraken's own published history and the loader points at it instead. What A already
built is not wasted — the reduction, the frame-level de-duplication reasoning and the coverage
analysis in `PROVENANCE.json` all carry over, and one whole class of hazard in it disappears.

**Read these five facts before writing anything.**

1. **It is time-and-sales, not OHLCVT.** Three columns, no header, `timestamp,price,volume`,
   epoch **seconds** as integers. `research/historical.py` expects seven-column OHLCVT, so the
   reduction to 15-minute bars is still ours — but it now runs on Kraken's own published trade
   history rather than on our recording. The `trades` column of OHLCVT (the T) becomes a real
   count of trades in the interval rather than something we cannot know.
2. **The entire `missing_not_recorded` / `partial_rows` hazard is gone**, and this is the
   important one. `PROVENANCE.json` currently has to separate a quiet interval from an interval
   nobody was watching, because our recorder stopped and Kraken never does. Against the
   published archive **a hole can only mean no trades occurred** — which is exactly what
   `research/historical.py` assumes and what makes the triple barrier safe to walk. Keep the
   `missing_quiet` accounting; drop the two categories that no longer exist, and say in the
   provenance why they are gone rather than silently removing them.
3. **It is split across two directories, alphabetically, and extraction was still running when
   this was written.** `data/historical/KRAKEN_TimeAndSales_Combined/` holds `1INCH` to `HONEY`
   and `data/historical/TimeAndSales_Combined/` holds `HPOS10I` onward. The second grew from
   408 to 605 files in the minutes it took to write this paragraph, and **`XBTUSD.csv` had not
   landed yet**. Do not start a reduction against a directory that is still being written:
   check the pair file you need exists, and that its size is stable across a pause, before
   reading it. A truncated final line is not a parse error, it is a silently short bar.
4. **It is 27 GB and growing; `ETHUSD.csv` alone is 1.7 GB.** Stream every file. Never read
   one into memory, and never sort one.
5. **The span is real history**: `ETHUSD` runs 2015-08-07 to 2025-12-31. The Phase 4 row asks
   `--live` to replay six months; six months is the floor, not the target.

**Delete or move the three `*_15.csv` files already in `data/historical/` that were built from
`data/raw/`.** Two archives in one directory under the same naming convention is a silent
wrong-source defect: the loader cannot tell them apart, and a labelled slice built from the
weaker source would look exactly like one built from the stronger. Keep the build script and
its build-log entries; retire its output.

**What must not happen is still a synthesised price series.** Every bar comes from real trades,
and the reduction being ours rather than Kraken's published OHLCVT is written down rather than
implied — the same standard `scripts/ohlc_fixture.py` already meets and says out loud.

## Implementation

1. A script under `scripts/` that reduces the operator's time-and-sales CSVs into Kraken-
   archive-shaped 15-minute OHLCVT CSVs, one file per pair, no header, columns in the order
   `research/historical.py` already defines. Write them somewhere the raw archive is not, so
   the source and the derived form can never be confused for one another.
2. **Never write into `data/raw/` or into the operator's archive directories.** Invariant 11:
   recorded data is immutable, corrections live in a derived layer. The archive is 27 GB of
   input the operator obtained once; treat it as read-only in the strongest sense.
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
