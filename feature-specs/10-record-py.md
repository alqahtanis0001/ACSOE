# 10 — `scripts/record.py` and the committed sample

**Owner:** A — Platform

## Goal

Order-book and spread recording starts on day one, and a small redacted sample is committed so
the Phase 0 gate can verify the format on a fresh clone.

## Implementation

1. Create `scripts/record.py` as a standalone Kraken WebSocket v2 to JSONL recorder with **no
   dependency on the engine framework**. It must run before `src/acsoe/` is finished.
2. Append-only writes to `data/raw/`, daily rotation, `orjson` on the hot path.
3. Reconnect with backoff on disconnect, and record a gap marker rather than silently
   resuming — a missing interval must be visible later.
4. Define the line schema — pair, channel, exchange timestamp, receive timestamp, payload —
   and validate on write. `context/architecture-context.md` describes what is being captured.
5. Run it against live Kraken long enough to produce real lines, then redact and commit a
   small sample as `tests/fixtures/record_sample.jsonl`. The `!tests/fixtures/**` negation in
   `.gitignore` is what lets a `.jsonl` be committed there; confirm `git add` actually stages
   it rather than assuming.
6. Add `tests/platform/test_record_format.py` validating the committed sample against the
   schema, offline.

## Scope Limits

- Do **not** import anything from `src/acsoe/` — this script is deliberately dumb and outlives
  the framework's absence.
- Do **not** commit a raw unredacted capture, and never anything from `data/raw/`.
- Do **not** implement engines 1 or 2; they supersede this script in Phase 2 and it stays.
- Do **not** interpolate, backfill or clean a recorded line. Recordings are immutable.

## Check When Done

- `python scripts/record.py` writes valid JSONL to `data/raw/` against live Kraken.
- `tests/fixtures/record_sample.jsonl` is committed, redacted, and validates offline.
- `python scripts/verify.py --phase 0` reports `record_sample_valid` as PASS.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
