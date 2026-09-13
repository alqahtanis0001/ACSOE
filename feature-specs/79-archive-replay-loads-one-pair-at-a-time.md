# 79 — `ArchiveReplay` loads one pair at a time

**Owner:** A — Platform

**Phase:** 5. `research/replay.py` is A's.

## Goal

The full-archive `acsoe research` run peaks near one pair's worth of memory rather than the
whole archive's. Spec 78 streamed the writer and took the peak from 51.9 GB to 23.6 GB with
identical rows and labels; A-2 measured that the remaining floor is the reader, which holds
every pair's parsed rows as Python dicts and the same data again as polars frames, eagerly,
for the life of the run, on a path that reads only the frames one pair at a time.

## Implementation

1. `ArchiveReplay.frame(pair)` reads and builds that pair's frame on demand and does not keep
   it; `frames()` becomes a generator in `report.pairs` order; the eager dict copy is dropped
   from `__init__` and `bars()` builds what it needs from the frame when it is called.
2. `report` keeps being computed at construction from what it needs and no more; if it needs
   every pair's timestamps, it reads them once and keeps the report, not the rows.
3. Engine 23's loop asks for each frame in turn and releases it, as spec 78 left it.
4. Peak memory over the same 24-pair scratch archive, both orders as the control, before and
   after, in the build log; then the full 234-pair run with its peak, row count and label
   counts against spec 78's figures, which must be identical.
5. `tests/research/test_replay.py`, A lane: `frame(pair)` for one pair reads that pair's
   file and no other (assert on the files opened); `bars()` still yields the same
   `DecisionBar`s as before over the committed sample; and a test that construction holds no
   pair's rows resident.

## Scope Limits

- Do **not** change `DecisionBar`, `ReplayReport`, `pair_from_filename` or the provenance
  reading.
- Do **not** change the labeller seam or engine 23's output.
- Do **not** cache frames across calls; one pair resident at a time is the property.

## Check When Done

- The full-archive run reports the same 20,331,237 rows and the same label counts as spec 78
  at a peak under 5 GB, measured and recorded.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
