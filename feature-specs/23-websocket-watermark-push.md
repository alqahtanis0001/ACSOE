# 23 — WebSocket updates on a moving watermark

**Owner:** C — Interface and models

## Goal

The page keeps itself current: when the database moves, an update reaches the browser within
twice `console.poll_interval_ms`, without the browser polling anything.

## Implementation

1. Create `src/acsoe/console/websocket.py` and mount a `WS /ws` endpoint on the app.
2. The **server** polls `StoreClient.watermark()` every `config.get("console.poll_interval_ms")`
   and pushes **only when the watermark has moved**. The watermark is monotonic, so a value that
   has not changed means nothing to send. No triggers, no file watching, and no polling from the
   browser — per `ui-context.md`, that is the whole design.
3. Read the interval from config every time. **Never hardcode 500, and never hardcode 120000.**
   The README's numbers are default values, not a second source of truth.
4. The push payload is built from the same view models as `GET /api/state` and `GET /api/feed`,
   so the socket and the plain endpoints can never disagree about what a screen says.
5. Create `src/acsoe/console/static/console.js` — vanilla JavaScript, no framework, no npm, no
   build step. It connects, applies a payload to the DOM, and reconnects with backoff when the
   socket drops. A dropped socket is a visible state, not a silently frozen screen.
6. Motion: a **200ms background flash on a value that has actually changed**, and nothing else.
   Under `@media (prefers-reduced-motion: reduce)` even that is dropped. Numbers never animate
   continuously — continuous animation hides real changes among fake ones.
7. Staleness keeps working over the socket: a figure older than `console.stale_after_ms` renders
   at 50% opacity with its age beside it, so a dead daemon fades rather than lying.

## Scope Limits

- Do **not** add a browser-side polling fallback that hits the API on a timer. If the socket is
  down, say so; do not quietly replace the design with polling.
- Do **not** use server-sent events, long-polling, or a third-party socket library.
- Do **not** hardcode either interval. Both come from config, on every read.
- Do **not** push on every poll — only on a moved watermark.
- Do **not** send a command over the socket. The three commands are `POST` in spec 24; the
  socket is one-directional and read-only.
- Do **not** write to the database from the socket loop, and do **not** open a read-write
  connection here.
- Do **not** add any motion beyond the 200ms flash.

## Check When Done

- A row written to the seeded database is reflected on a connected client within
  2 × `console.poll_interval_ms`, measured against the value read from config.
- No push occurs across multiple poll intervals when the watermark has not moved — one test
  asserting silence.
- Dropping the socket produces a visible disconnected state and a successful reconnect.
- `prefers-reduced-motion: reduce` drops the flash; no numeric element animates continuously.
- A grep of `src/acsoe/console/` finds neither `500` nor `120000` as a literal interval.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 1`
