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
3. **A missing candle in the archive means no trades occurred. It is not a data error, and the
   loader marks it and never interpolates it.** This is the single most important sentence in the
   spec. Kraken's archives contain only intervals in which trades happened, so a hole is a *fact
   about the market* — a quiet period — and it is information, not damage.

   It is called out this strongly because it is exactly the kind of thing an implementer fixes
   helpfully: a gap looks like missing data, forward-filling it makes the series continuous, every
   downstream chart looks tidier, and nothing fails. **It is load-bearing for Phase 4's
   triple-barrier labelling**, which walks forward from each decision bar to decide whether the
   target, the stop or the timeout came first. A synthesised candle at a price that never traded
   invents a barrier touch that never happened, and the label built from it is a fabricated
   outcome the model then learns from. That error is invisible in every test that only checks the
   series is continuous.
4. **Report gap statistics rather than repairing gaps.** Count them, bucket them by duration, and
   report the largest.
5. The archives are **OHLCVT only: no book, no spread.** State that in the module docstring and in
   the report, because engine 9 and the spread half of engine 10 cannot be backtested from this
   source and a backtest that silently assumes zero spread is invalid.
6. Money stays `Decimal` at the boundary; indicators and statistics may be float, per the Phase 0
   decision recorded in `docs/build-log/phase-0.md`.
7. `data/historical/` is gitignored, so the committed evidence is a small digest under
   `tests/fixtures/`, and the full ingest is verified by `--live`, which is opt-in.

## Scope Limits

- Do **not** import anything from `src/acsoe/engines/` or the live loop, and do not let the live
  loop import this.
- Do **not** interpolate, forward-fill, resample or otherwise synthesise a missing candle, and
  do **not** offer a flag that does. There is no correct value to put there.
- Do **not** build features, labels or splits. Phase 4 owns replay and triple-barrier labelling.
- Do **not** commit anything from `data/`; the criterion must pass on a fresh clone.
- Do **not** assume a spread or a book exists in this data.

## Check When Done

- One pair's full archive ingests and reports gap statistics: count, duration buckets, largest gap.
- A fabricated archive with a known number of holes reports exactly that number — the fixture is
  constructed so a loader that silently filled gaps would report a different count and fail.
- A separate assertion on the built output itself: the row count equals the archive's, and no
  timestamp exists in the output that was absent from the input. Counting gaps correctly while
  also emitting filled rows would pass the check above and still poison Phase 4's labels.
- The module imports nothing from the live loop, asserted by an import test.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
