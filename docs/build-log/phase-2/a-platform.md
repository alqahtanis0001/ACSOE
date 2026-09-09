# Build log — Phase 2 — a-platform

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem
and its fix, and every decision where two approaches were viable. Not at the end of
the session — three IDE crashes in Phase 1 each took the code and the log at different
moments, and only the entries already written survived.

Minimum headings per entry: What happened, Why, Fix.

The lead consolidates these into `docs/build-log/phase-2.md` at phase close.

## Entries

### `websockets` no longer exposes `exceptions` as a package attribute

**Agent:** A · **Task:** spec 25 · **Date:** 2026-09-09

**What happened.** `ws.py` did `import websockets` and referred to
`websockets.exceptions.WebSocketException` at module scope, copying the pattern in
`scripts/record.py`. Under `websockets` 17.1 that raises `AttributeError: module
'websockets' has no attribute 'exceptions'`. Because `tests/harness/fake_kraken.py`
imports the error types from `acsoe.clients.kraken`, the failure landed inside
`conftest.py` and **pytest exited 4 with nothing collected** — so the whole team's
suite reported nothing, not just mine. C and the lead both hit it within minutes.

**Why.** `websockets` uses lazy attribute loading (`websockets/imports.py`), and the
top-level package's `__getattr__` no longer resolves `exceptions`. `record.py` gets
away with the same expression only because it evaluates it inside a running
coroutine, by which time something else has imported the submodule.

**Fix.** `import websockets.exceptions` and `from websockets.asyncio.client import
connect` explicitly. Both submodules, no package-attribute lookups.

**Consequence.** `scripts/record.py` has the same latent expression and is *not*
changed — its line schema is validated by a Phase 0 criterion and spec 27 says do not
touch it. It works today because of when it evaluates, which is luck rather than
design; worth revisiting if that file is ever reopened for another reason.

### A token bucket that spun forever on a fraction of a token

**Agent:** A · **Task:** spec 25 · **Date:** 2026-09-09

**What happened.** `RateLimiter.acquire` hung. Not slowly — permanently, with no
error, no CPU spike attributable to it and no output. `pytest tests/clients/kraken`
sat at `..` and had to be killed twice; the first kill produced a faulthandler dump
whose only useful frame was `limiter.py:112 in acquire`.

**Why.** Floating point, in the classic place. The first version looped: refill, and
if the bucket is still short of `cost`, sleep the shortfall and try again. With a
capacity of 5 and a refill of 10/s the sixth acquisition sleeps 0.1s and the refill
returns exactly one token. The *eleventh* does not: the clock is at 0.5, `0.5 + 0.1`
is `0.6`, and `0.6 - 0.5` is `0.09999999999999998`, so the refill lands about `2e-16`
under one token. The next shortfall is therefore `2e-16`, the sleep computed for it is
`2e-17`, and adding `2e-17` to a float already at `0.6` changes nothing at all.
Elapsed time is then zero forever, the refill adds nothing forever, and the loop never
terminates. The injected clock made it deterministic; against a real clock it would
have been an intermittent stall in the path that prices every REST call, which is a
far worse thing to own.

**Fix.** Removed the loop. `acquire` now refills once, sleeps the shortfall at most
once, refills again, and then deducts `cost` **unconditionally** — letting the balance
go very slightly negative. That is exact over any number of calls, because the next
refill starts from the deficit, and it has no loop that can fail to terminate.

**Consequence.** The negative balance looks like sloppiness and is the opposite, so it
carries a comment in the code saying why, and the tolerance is a fraction of one token
rather than an epsilon somebody has to choose. Worth remembering as a shape:
*re-checking a float condition in a loop that sleeps the difference* will always
eventually fail to make progress. Compute the wait once and carry the remainder.

### Two test modules called `test_contracts.py` stopped the whole suite collecting

**Agent:** A · **Task:** spec 25 · **Date:** 2026-09-09

**What happened.** `tests/clients/kraken/test_contracts.py` collided with
`tests/core/test_contracts.py`, which has existed since Phase 0. pytest aborted
collection: `845 tests collected, 1 error`, **zero executed**. Under the operator's
new commit-at-every-boundary rule this blocked B and C from confirming finished work,
not just me — B had spec 35 green on its own subset and could not report it.

**Why.** Neither directory had an `__init__.py`, so pytest's rootdir-relative import
gave both files the bare module name `test_contracts`, and the second one imported
loses.

**Fix.** Added empty `tests/clients/__init__.py` and
`tests/clients/kraken/__init__.py`, and cleared the stale `__pycache__` in
`tests/clients/`, `tests/clients/kraken/`, `tests/clients/store/` and `tests/core/`.
Two levels, not one: `tests/__init__.py` already exists, so both are needed for
`tests.clients.kraken.test_contracts` to resolve.

**Consequence.** Chosen over renaming the file. A rename fixes this collision;
`test_rest.py`, `test_ws.py` and `test_limiter.py` are equally generic and the next
one would come free. Nothing else moved: `tests/clients/store/` still has no
`__init__.py`, so its modules keep exactly the names they had.

### Decision: the HTTP transport is injected above `httpx`, not at `httpx`

**Agent:** A · **Date:** 2026-09-09

**Options.** Test the REST client through `httpx.MockTransport`, the ordinary way, or
define a narrow `HttpTransport` Protocol the client depends on and inject a fake.

**Chose.** The Protocol.

**Because.** `tests/conftest.py`'s autouse network guard patches
`httpx.AsyncClient.send` itself, not the socket underneath it. A `MockTransport` sits
*below* `send`, so nothing reaches it inside a test and the only way to use one would
be to relax the guard — which spec 25 forbids in as many words and which C's spec 14
forbids for the same reason. Injecting one level higher leaves the guard exactly as
strict as it is while the envelope, the field mapping, the retention and the
credential handling are all covered offline.

**Cost.** One extra indirection, and a real `HttpxTransport` that no unit test
exercises. That transport does nothing but call `httpx` and wrap its error type; it is
confirmed by `--live`.

### Decision: the WebSocket client owns a thread, and the parse is lenient

**Agent:** A · **Date:** 2026-09-09

**Options.** Poll the socket once per tick from the synchronous loop, or run it
continuously on its own thread and let the engines drain a buffer.

**Chose.** The thread and the buffer.

**Because.** The loop tick is 60 seconds and the socket delivers continuously. Polling
once a minute would discard almost everything, and order-book and spread history is
the one class of data that cannot be recovered retroactively — which is why
`scripts/record.py` exists at all.

**The second half of the decision is the one worth recording.** The frame parse is
deliberately *lenient*: every frame is buffered verbatim regardless of whether the
trade and quote extractors understand it, and a frame they do not understand
increments `unparsed_frames` rather than raising. `AGENTS.md` says any Kraken payload
shape an agent remembers may be stale, so the field names in `_extract_trades` are an
assumption. If that assumption is wrong, the lenient version keeps a correct and
complete archive and simply stops building candles, which engine 4 turns into a block
— fail-closed, with the irreplaceable half intact. A strict parser would raise on
every frame and throw the archive away to protect the part that can be rebuilt from
it.

**Cost.** A wrong field name is quiet rather than loud, so `unparsed_frames` is exposed
and engine 2's report has to surface it.

### The one thing in this package that cannot be proved offline

**Agent:** A · **Task:** spec 25 · **Date:** 2026-09-09

**What happened.** Nothing yet — this is a recorded limitation rather than a fix, and
it is here so the next session does not mistake green tests for a working client.

**Why.** Two things in `rest.py` are assumptions about Kraken that no offline test can
falsify: the four `map_*` functions' **field names**, and `sign_request`'s **signing
scheme**. `AGENTS.md` says any endpoint shape an agent remembers is stale, the operator
has rotated the key so no live call can succeed, and the committed fixtures in
`tests/fixtures/kraken/` are a simplified shape C's harness owns rather than recorded
responses. So the tests prove the envelope, the retention, the money handling and the
redaction — all of which are ours — and prove nothing about whether Kraken would accept
or answer any of it.

**Fix.** Isolation and honesty rather than cleverness. The field mapping lives in four
named functions with no logic around them, so correcting it is a small obvious edit; a
renamed field surfaces as a `KrakenUnavailableError` **naming the field**, never as a
default. `sign_request` is one function, deterministic, and tested as such.

**Consequence.** Confirming both is a `--live` task for whenever the operator restores
a key, and it is recorded as the only open question in
`context/progress/a-platform.md`. It blocks nothing: every Phase 2 criterion runs
offline.
