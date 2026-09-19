# 130 — The declared scenario fixtures: the liquidity-bucket table and the fee schedule

**Owner:** A — Platform (the table and its script). Lead (committing the operator's fee schedule).

**Phase:** 7. Ruled 2026-09-19: spread and depth are declared from the recording, by liquidity
bucket (`docs/dataset/phase-7-findings.md` §3).

## Goal

Two committed fixtures, each with its provenance, that the replay client reads and nothing else
reads:

- **the bucket table:** spread, and depth to $10,000, per bucket of trailing 24-hour dollar volume;
- **the fee schedule:** the operator's supplied schedule, as a declared scenario.

## Implementation

1. **The table script** (A, `scripts/`) reads `data/summaries/` and, per recorded USD pair, takes:
   - the median minute-p50 spread, over clean minutes with samples;
   - the median depth to $10,000 on the bid, over minutes where the book reached it;
   - the pair's mean daily dollar volume over the recording.

   It assigns the buckets `<$10k`, `$10k–100k`, `$100k–1M`, `$1M–10M` and `>$10M`, and writes each
   bucket's median of per-pair medians with its IQR and pair count.
   - It must reproduce the table in `phase-7-findings.md` §3 (spread 30.4, 25.8, 12.3 and 5.5 bps
     on 16, 49, 84 and 36 pairs) from the same recording span, or report why not.
   - The `>$10M` bucket is empty in the recording, because BTC, ETH and SOL are recorded as full
     books rather than summaries. The fixture says so and maps that bucket to the `$1M–10M` row.
     **Using the full books to fill it instead is a ruling, not a choice to make here.**
2. The table is written to `tests/fixtures/replay/spread_book_table_<YYYY-MM-DD>.json` with:
   - the recording span;
   - the pair list per bucket;
   - the script's sha256;
   - the statement that it is a **declared** value applied to a different period, never a
     measurement of that period.
3. **The fee schedule** (lead): when the operator supplies it, commit it at
   `tests/fixtures/replay/fee_schedule_<YYYY-MM-DD>.json` with the source URL, the capture date,
   the tiers exactly as published, and the operator's name for the tiers the simulation will use.
   **No figure is typed from memory or from this conversation.** The tier-4 and tier-5 marks in
   `phase-7-findings.md` §2 are replaced by the fixture's figures once it lands.

## Scope Limits

- No live path may read either fixture. Spec 129's refusal outside replay mode is the enforcement,
  and spec 141 carries a criterion that proves it.
- Do not refit a spread model. The fitted model was rejected on the evidence in the findings.
- The recorder's files are read only.

## Check When Done

- The table script reproduces the findings' table, or the build log records the difference and
  its cause.
- Both fixtures carry provenance that a reader can check without this conversation.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
