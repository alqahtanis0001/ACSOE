# 78 — Engine 23 streams the labelled slice per pair

**Owner:** A — Platform

**Phase:** 5. `research/backtest.py` is A's.

## Goal

`acsoe research` over the full 234-pair archive produces the same 20,331,237-row labelled
dataset it produces today without holding every row of every pair in memory first. Found by
A-2 at the Phase 5 wind-down: a 429 MB parquet cost a 51.9 GB peak, because engine 23
accumulates every labelled row in one Python list and writes once at the end. Linear, not
anomalous, and on a machine smaller than this one's 96 GB the failure is a killed process
rather than a message.

## Implementation

1. In `BacktestEngine.process`, write each pair's labelled rows as they are produced: one
   Parquet row group per pair appended to the single slice file through `pyarrow`'s writer,
   with the same schema and the same file path convention as today
   (`data/derived/labelled_<run_id>_<stamp>.parquet`). Row order within the file is pair by
   pair in `report.pairs` order, which is the order today.
2. The per-pair counts, the label totals, the ambiguous count and the exclusion buckets keep
   being accumulated as integers; nothing about `data` changes except that
   `labelled_rows` is now the sum of what was written.
3. A row-group-per-pair write is also what makes `--pairs` smoke runs and spec 67's dataset
   builder cheap to read selectively, so name the pair in the row group's metadata.
4. Peak memory is measured before and after over a scratch archive of at least twenty pairs,
   with the comparison run in both orders, and the two numbers go in the build log.
5. `tests/research/test_backtest.py`, A lane: the slice written by the streaming path is
   byte-for-byte the same rows, in the same order, as the accumulated path produced over the
   committed candles sample; and a test that the writer never holds more than one pair's rows
   at once, by counting rows resident at the seam.

## Scope Limits

- Do **not** change the labeller seam, the labels, the exclusions or the barriers.
- Do **not** change the slice's path convention, schema or column types.
- Do **not** add `--only` or a bar limit; that is A-2's open question for the operator and it
  is answered in the task file, not here.

## Check When Done

- The full-archive `acsoe research` run completes with the same `labelled_rows` and
  `label_counts` as the run recorded in the Phase 5 handoff, at a peak well under a tenth of
  51.9 GB, measured and recorded.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
