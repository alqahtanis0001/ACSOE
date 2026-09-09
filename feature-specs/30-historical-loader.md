# 30 — Historical OHLCVT loader

**Owner:** A — Platform

## Goal

`research/historical.py` ingests Kraken's downloadable OHLCVT archives from `data/historical/` and
reports honest gap statistics, so Phase 4's replay and labelling have a real dataset to stand on.

## Implementation

1. Create `src/acsoe/research/historical.py`. It is **offline only**: research code never imports
   from the live loop path and the live loop never imports from `research/`, per invariant 5 of
   `architecture-context.md`.
2. Ingest one pair's full archive from `data/historical/` into `polars`, and write built output to
   `data/derived/` as Parquet — rebuildable from raw, never checked in.
3. **Report gap statistics rather than repairing gaps.** The archives contain only intervals where
   trades occurred, so a missing candle means no trades, not a data error. Count them, bucket them
   by duration, and report the largest — never interpolate.
4. The archives are **OHLCVT only: no book, no spread.** State that in the module docstring and in
   the report, because engine 9 and the spread half of engine 10 cannot be backtested from this
   source and a backtest that silently assumes zero spread is invalid.
5. Money stays `Decimal` at the boundary; indicators and statistics may be float, per the Phase 0
   decision recorded in `docs/build-log/phase-0.md`.
6. `data/historical/` is gitignored, so the committed evidence is a small digest under
   `tests/fixtures/`, and the full ingest is verified by `--live`, which is opt-in.

## Scope Limits

- Do **not** import anything from `src/acsoe/engines/` or the live loop, and do not let the live
  loop import this.
- Do **not** interpolate, forward-fill or synthesise a missing candle.
- Do **not** build features, labels or splits. Phase 4 owns replay and triple-barrier labelling.
- Do **not** commit anything from `data/`; the criterion must pass on a fresh clone.
- Do **not** assume a spread or a book exists in this data.

## Check When Done

- One pair's full archive ingests and reports gap statistics: count, duration buckets, largest gap.
- A fabricated archive with a known number of holes reports exactly that number — the fixture is
  constructed so a loader that silently filled gaps would report a different count and fail.
- The module imports nothing from the live loop, asserted by an import test.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
