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

### The recording digest could not be deposited: the archive is 21 hours old, not 24

**Agent:** A · **Task:** spec 27 · **Date:** 2026-09-09

**What happened.** Spec 27's committed evidence is
`tests/fixtures/recording_report.json`, showing a continuous span of at least 24 hours
with every break accounted for. The real archive does not yet contain 24 hours:

    kraken_v2_2026-09-08.jsonl     2.5MB  2026-09-08T16:01:22Z -> 2026-09-08T16:02:17Z
    kraken_v2_2026-09-09.jsonl  1575.0MB  2026-09-09T02:04:19Z -> 2026-09-09T13:25:41Z

Total span **21h24m**, with a ~10-hour hole between 09-08T16:02 and 09-09T02:04 where
no recorder was running at all. The span crosses 24h at about **2026-09-09T16:01Z**,
provided `scripts/record.py` keeps running.

**Why it matters that the report was not written anyway.** The digest built from this
archive would be entirely *truthful* — the 10-hour hole appears as a gap with a cause,
because the digest accounts for unrecorded silence as well as for explicit `gap`
markers — and it would still **FAIL** `recording_span_continuous`, which requires 24
hours. That is strictly worse than the PENDING the criterion reports today. PENDING
means "the subject does not exist yet", which is true. FAIL means "the subject exists
and is wrong", which would not be. **Depositing early converts an accurate absence into
an inaccurate presence.**

**Fix.** None available in code, and that is the point worth recording: **the criterion
is satisfied by wall-clock time, not by anything anyone can write.**
`scripts/recording_report.py` refuses to write a digest whose span is under
`--min-hours` (default 24) and prints the numbers instead, so the refusal is mechanical
rather than a matter of somebody remembering. There is deliberately no flag that
fabricates a span.

**Consequence.** Everything else in spec 27 is finished and green; only the fixture
waits. Regenerating it later is one command — `python scripts/recording_report.py
--write` — rather than an archaeology exercise, which is why the script lives in
`scripts/` rather than being a throwaway.

### Two recorders were running at once, and the duplication is not uniform

**Agent:** A · **Task:** spec 27 · **Date:** 2026-09-09

**What happened.** Two `scripts/record.py` processes (PIDs 6968 and 46512) were
appending to the same daily file. I first assumed the whole 1.5GB file was doubled and
told the lead so. The lead checked the process creation times and corrected it: **both
started at the same second, 13:19:34 on 09-09** — about an hour before I looked, not
eleven. So everything before 13:19 is single-recorded and only the tail is doubled.

**Why the correction matters more than the original observation.** A uniform 2x would
be obvious in any volume series and easy to spot. **A discontinuity part-way through a
file is not** — it looks like a market event. Spec 28 builds 15-minute candles from
`trade` frames and its criterion asserts volume within 0.1% of a Kraken OHLC fixture, so
a naive build over this archive is correct up to 13:19 and doubled after, which no
tolerance would forgive and no eyeball would attribute to the right cause.

**Fix.** De-duplication belongs in the **derived** layer, not in the archive. Invariant
11: a recording is append-only and is never edited, backfilled or cleaned in place, so
the duplicate lines stay on disk exactly as they arrived and the candle builder is what
has to be idempotent over them. It also has to be correct **across the boundary** rather
than tuned to the doubled section — a de-duplicator calibrated on the tail would corrupt
the head.

**Consequence.** Neither process was killed. They are the operator's, they are
collecting data that cannot be recovered retroactively, and killing the wrong one loses
an open file handle mid-line. It is with the operator. Recorded here because a future
reader looking at that file's volume profile will otherwise spend an afternoon on it.

### A fast field scan that matched the value instead of the key

**Agent:** A · **Task:** spec 27 · **Date:** 2026-09-09

**What happened.** The digest scans gigabytes, so it reads `ts_recv` and `kind` out of
each line with a byte search rather than parsing the JSON. The first version searched
for the literal `b'"ts_recv":"'`. Every test in `test_report.py` failed with "no usable
line found in the recording": the fixtures are written with `json.dumps`, which emits
`"ts_recv": "..."` **with a space**, while `orjson` — which the recorder uses — emits
the compact form.

**Why.** Two serialisers, one hardcoded byte pattern. The production path happened to
match and the test path did not, which is the least useful arrangement of the two: it
would have passed CI on real files and failed on any recording that had been through
any other writer.

**Fix.** `_string_field(raw, key)` steps past the key, the colon, any whitespace and the
opening quote instead of matching a fixed prefix.

**The mistake worth recording is the one I made while fixing it.** The first repair also
loosened the `kind` detection from `b'"kind":"gap"'` to a bare `b'"gap"'`. That made the
tests pass and was wrong: a Kraken frame whose *payload* merely contained the word
"gap" would have been classified as a break in the archive, silently splitting a
segment. Matching the key and reading its value is the only version that is not a
guess. The first occurrence is safe because the recorder writes the seven schema keys
before `payload`, so a same-named key nested in a frame can never be reached first.

### Decision: the digest reports a tiling, not a gap count

**Agent:** A · **Date:** 2026-09-09

**Options.** Report an uptime percentage and a gap count, or report a `span`, a list of
`segments` and a list of `gaps` that together account for every microsecond in the span.

**Chose.** The tiling. C's criterion asks for it and it is the stronger property, so
this is a decision to agree rather than to negotiate — but it is worth recording why it
is stronger.

**Because.** A gap count can be **right while a break sits unaccounted for**. Two
segments with a hole between them that nobody compared produce a perfectly plausible
count of zero. A tiling has nowhere for that to hide: if the pieces do not abut, the
assertion fails. It also forces the digest to treat *unrecorded silence* — what a
recorder that was not running leaves behind, writing no marker precisely because it was
not there to write one — as a first-class gap rather than as an absence of evidence.

**Cost.** The digest has to reason about both kinds of break and about their
boundaries, which is more code than counting markers. `assert_tiles` in
`tests/clients/recorder/test_report.py` is the assertion that makes it worth it.
