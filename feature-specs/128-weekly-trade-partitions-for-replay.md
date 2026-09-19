# 128 — Kraken's time-and-sales, partitioned by week for replay

**Owner:** A — Platform

**Phase:** 7. The playback client (spec 129) reads these partitions and nothing else.

## Goal

For every archive USD pair and every week in the simulation window, plus the 96-bar lookback before
it, the replay can load that week's trades without reading a whole pair file. Some of those files
run to 2.7 GB and the archive is 47 GB. The Phase 5 run died of exactly an eager whole-file read
(prerequisite 2).

## Implementation

1. A script under `scripts/` streams each file in `data/historical/KRAKEN_TimeAndSales_Combined/`
   and `TimeAndSales_Combined/` once. It writes
   `data/derived/trades_weekly/<PAIR>/<week-start>.parquet` with three columns: timestamp, price
   and volume.
   - Prices and volumes are kept as they were published: as text, or as exact decimals. Never
     round-trip them through a float that changes a digit.
   - The two source directories are resolved exactly as `scripts/build_ohlcvt.py` resolved them
     for the archive, so the replay sees the trades the models were trained on.
2. **Nothing is interpolated, filled or resampled.** A week with no trades has no file, and the
   partition index records it as empty.
3. A manifest records, per pair:
   - the source file and its sha256;
   - the row count per week;
   - the total row count, equal to the source's rows inside the window.

   The script refuses to finish if any count disagrees.
4. **Peak memory is measured and bounded**, not assumed. Record the script's peak working set on
   the largest file (`XBTUSD.csv`, 2.7 GB) in the build log, and assert in a test on a synthetic
   large file that memory does not grow with file size.

## Scope Limits

- The raw archive is **read only**. Invariant 11: nothing in `data/historical/` is edited, moved or
  rewritten.
- Only the simulation window and its lookback. Not the whole archive.
- No bar building here. Engine 3 builds candles from the trades the client serves, as it does live.

## Check When Done

- Row counts reconcile per pair, and the refusal on a mismatch is proven by a planted miscount.
- Peak memory on `XBTUSD.csv` is recorded.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
