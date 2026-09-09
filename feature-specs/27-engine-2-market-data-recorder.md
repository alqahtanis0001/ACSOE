# 27 — Engine 2 `market_data_recorder`, superseding `scripts/record.py`

**Owner:** A — Platform

## Goal

The framework recorder that replaces the standalone day-one script: it subscribes through spec
25's WebSocket client and appends raw market data to `data/raw/`, and it produces the committed
evidence Phase 2's first criterion reads.

## Implementation

1. Create `src/acsoe/engines/market_data_recorder/` — `engine.py`, `contracts.py`, `README.md`.
   `name = "market_data_recorder"`, `number = 2`, `is_gate = False`, **guard** chain.
2. Create `src/acsoe/clients/recorder/` — the append-only JSONL writer with daily rotation, and
   `contracts.py` carrying the line schema. **The schema stays compatible with the 25-line sample
   `scripts/record.py` produced in Phase 0** (`tests/fixtures/record_sample.jsonl`), because
   `record_sample_valid` is a Phase 0 criterion and Phase 0 must stay green.
3. Order book and spread are recorded going forward and can never be recovered retroactively, so
   the recorder runs in the **guard chain, every tick, in every mode** — a freeze never stops data
   collection.
4. Produce `tests/fixtures/recording_report.json`: a digest of a real recording showing a
   **continuous span of at least 24 hours with every break accounted for** — each gap carrying its
   start, end and cause, so a silent outage cannot be mistaken for a quiet market. A gap is
   marked, never interpolated away.
5. The `--live` half of the criterion confirms the real `data/raw/` matches the committed report.
   `--live` is opt-in and is never required for the phase to be green, because `data/` is
   gitignored and a criterion may not depend on it.
6. `scripts/record.py` stays on disk and stays working. It is superseded, not deleted: it is the
   fallback if the engine framework is down, and `architecture-context.md` describes it as the
   day-one recorder.
7. Write `README.md`, and batch the `bootstrap.py` registration request to the lead.

## Scope Limits

- Do **not** delete or gut `scripts/record.py`, and do **not** change its line schema — a Phase 0
  criterion validates the committed sample against it.
- Do **not** build candles here. Engine 3 `market_sensor` owns aggregation; this engine records
  raw.
- Do **not** interpolate, backfill, or smooth a gap. Mark it and let the consumer decide.
- Do **not** commit anything from `data/raw/` — only the redacted digest under `tests/fixtures/`.
- Do **not** let the report depend on the machine that produced it: it must pass on a fresh clone.
- Do **not** register the engine yourself.

## Check When Done

- `tests/fixtures/recording_report.json` is committed, parses, and shows at least 24 continuous
  hours with every break accounted for.
- A test proves an injected gap appears in the report as a gap rather than being closed silently.
- `record_sample_valid` still passes — Phase 0 stays green.
- The recorder still runs on a tick where the mode is `frozen`.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
