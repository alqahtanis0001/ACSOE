# 33 — Phase 2 criteria in `scripts/verify.py`

**Owner:** C — Interface and models

## Goal

The Phase 2 exit criteria exist as named executable checks reporting PENDING until the engines
they judge are built, so A has a gate to build against from the first commit.

## Implementation

1. Register for phase 2, alongside `commands_round_trip`, which the lead registered at the phase
   opening:
   - `recording_span_continuous` — parses `tests/fixtures/recording_report.json` and asserts a
     continuous span of at least 24 hours with **every break accounted for**. A report that simply
     shows no gaps is not the same as one that accounts for them; assert the accounting.
   - `candles_match_kraken_ohlc` — built 15-minute candles against a committed Kraken OHLC fixture
     for **three pairs**, every OHLC field within one `tick_size` for that pair **as reported by
     `AssetPairs`**, and volume within 0.1%. The tolerance is read from the fixture's pair rules,
     never hardcoded.
   - `data_guard_blocks_bad_data` — injected stale, negative-spread and missing-candle data each
     block, and clean data passes. Three block cases and a pass case in one criterion.
   - `historical_loader_reports_gaps` — the loader ingests a fabricated archive with a known number
     of holes and reports exactly that number.
   - `console_shows_live_rows` — the console renders rows written by the Phase 2 engines rather
     than by the seed, distinguished by run, so the criterion cannot be satisfied by seeded data.
   - `console_reads_persisted_mode` — the band renders `Running` and `Frozen` from a mode a **real
     daemon wrote**, per the operator's Phase 1 ruling: drive the real `Orchestrator` against a
     real `StoreClient`, apply `activate` and then `freeze`, and assert the band's State field
     follows. Not a fabricated column value.
2. Every criterion reports PENDING, not FAIL, while its subject does not exist.
3. **No criterion may read `data/`, `logs/` or `models/`** — they are gitignored and a criterion
   that depends on one cannot pass on a fresh clone. Seed or fabricate into a temporary directory.
4. `--live` variants, where the phase row names them, stay opt-in and are never required for the
   phase to be green.
5. Add `tests/verify/test_phase2_criteria.py` proving each criterion PENDING on an absent subject
   and PASS on a fabricated minimal one — the two-sided proof specs 01 and 16 established.
6. **Also prove `commands_round_trip` can fail.** The lead wrote and registered it, and it has no
   negative test. Add one showing it FAILs against a store that does not expose the command
   reader — the exact defect it exists to catch. A criterion nobody has seen fail is a comment.

## Scope Limits

- Do **not** build the things being checked. Engines 1 to 4 and the loader are A's; the schema is
  B's.
- Do **not** weaken a criterion to make it pass. A criterion that cannot be expressed honestly is
  raised with the lead.
- Do **not** add criteria for Phase 3 or later.
- Do **not** touch the Phase 0 or Phase 1 criteria; both phases are closed and green.
- Do **not** hardcode a tick size, a fee or an order minimum in a criterion — read them from the
  fixture's pair rules.

## Check When Done

- `python scripts/verify.py --phase 2` prints every criterion with no traceback and reports
  PENDING for each unbuilt subject.
- Each criterion is proved twice — PENDING on an absent subject, PASS on a fabricated one.
- `commands_round_trip` is proved to FAIL against a store missing the command reader.
- No criterion references a path under `data/`, `logs/` or `models/`.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
