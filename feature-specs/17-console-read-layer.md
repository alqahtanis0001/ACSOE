# 17 — Console read layer and seeded-database wiring

**Owner:** C — Interface and models

## Goal

`src/acsoe/console/app.py` stops being a Phase 0 placeholder: it opens the seeded SQLite
database read-only and turns rows into typed view models for every screen. No markup yet — this
is the layer every screen spec above it renders.

## Implementation

1. Replace the placeholder in `src/acsoe/console/app.py`. `create_app` gains a keyword-only
   `db_path: Path | None = None`, defaulting to `runtime_paths().db / "acsoe.sqlite"` from
   `acsoe.platform.paths`. **The signature stays call-compatible with `create_app(config)`** so
   Agent A's `src/acsoe/cli/console.py` needs no change — it is A's file and must not be edited.
   The injected path is what lets a test and `scripts/verify.py` point the console at a seeded
   temporary database.
2. The health payload's `console` field changes from `"placeholder"` to `"ready"`, and `phase`
   from `0` to `1`. That field exists so an operator can tell the two apart in one look.
3. Create `src/acsoe/console/reader.py` — the only module in the console that touches
   `StoreClient`. It composes the screens from methods that already exist in
   `src/acsoe/clients/store/client.py`: `latest_equity_snapshot`, `open_positions`,
   `recent_rejections`, `block_records_in_window`, `recent_closed_trades`, `latest_runs`,
   `leaderboard` and `watermark`.
4. Create `src/acsoe/console/views.py` — pydantic view models, one per screen region: the status
   band, a position row, a cycle-feed row, a history row and a leaderboard entry. Money crosses
   this boundary as `Decimal` or its exact string, **never as `float`**.
5. Restart detection is made **server-side in SQLite**, per `ui-context.md`: read `latest_runs(2)`
   and, when the two `run_id`s differ and the mode is idle, the status band's State field reads
   `Idle — restarted, not trading`. The console is a separate process with no memory across its
   own restarts, so this may never be derived from anything the browser or the app remembers.
6. Staleness: every figure carries its age against `config.get("console.stale_after_ms")`, and
   the view model exposes `age_ms` and `is_stale`. Read the threshold from config, never a
   literal.
7. Create `src/acsoe/console/format.py` — the string side of the number rules from
   `ui-context.md`: percentages always explicitly signed, a proper minus sign (−, U+2212) and
   never a hyphen, and money rendered at the precision of the stored `Decimal` without
   re-rounding and without ever passing through `float`.
8. The reader opens its connection **read-only** (a `file:...?mode=ro` SQLite URI). The console
   is read-only except for the three commands, and spec 24 opens its own narrow read-write
   connection for the `commands` table alone. Making that structural rather than a convention
   is what keeps it true.

## Scope Limits

- Do **not** write any HTML, CSS, JavaScript, WebSocket or command-writing code. Those are
  specs 18 to 24.
- Do **not** add or change a method in `src/acsoe/clients/store/`. That is B's directory.
  Compose the screens from the reads that already exist; if one is genuinely missing, message B
  and escalate to the lead rather than reaching across.
- Do **not** add a config key. `console.port`, `console.poll_interval_ms` and
  `console.stale_after_ms` already exist and cover this phase. Only the lead adds a key.
- Do **not** edit `src/acsoe/cli/console.py` or anything else under `src/acsoe/platform/` or
  `src/acsoe/cli/` — Agent A owns them.
- Do **not** import `tests/harness/` from anything under `src/`.
- Do **not** construct a Kraken client, read a credential, or open a network connection. The
  console holds no credentials and can never place an order.
- Do **not** let `float` touch money anywhere in this layer.

## Check When Done

- `create_app(config, db_path=<seeded temp database>)` builds, and `/health` reports
  `console: "ready"`.
- The reader returns populated view models against the seeded database and empty ones against a
  migrated-but-empty database, raising in neither case.
- Two tests on restart detection: differing `run_id`s with an idle mode yields
  `Idle — restarted, not trading`; matching `run_id`s yields plain `Idle`.
- A write attempted on the reader's connection is refused by SQLite.
- A percentage formats as `+0.62%` / `−1.50%` with U+2212, and no money value round-trips
  through `float`.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 1`
