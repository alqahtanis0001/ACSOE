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

### numpy's stubs took `mypy --strict` from "one error" to "no answer at all"

**Agent:** A · **Task:** spec 28 · **Date:** 2026-09-09

**What happened.** The first module in `src/` to import `polars` — `market_sensor`'s
candle builder — turned `mypy --strict src/` into:

    numpy/__init__.pyi:737: error: Type statement is only supported in Python 3.12
    and greater  [syntax]
    Found 1 error in 1 file (errors prevented further checking)

**Why.** numpy 2.5's bundled stubs use PEP 695 `type` statements, and `pyproject.toml`
pins `python_version = "3.11"` — the project's declared floor. mypy treats a PEP 695
statement under a 3.11 target as a **syntax error**, and a syntax error inside a
followed import aborts the whole run. So the check did not return a wrong answer, it
returned **no answer**, in one of the four commands the definition of done leans on.
That is the part worth remembering: a tool that stops checking looks a lot like a tool
that found nothing wrong.

**Fix.** `follow_imports = "skip"` for numpy — which alone did **not** work, because
mypy still reaches the stubs through polars' own annotations, so `polars` had to be
listed too.

**Why not just raise `python_version` to 3.12**, which also makes it pass. Because
`requires-python = ">=3.11"` and `architecture-context.md` both declare 3.11 as the
floor, and pinning mypy to it is the only thing that actually checks the code runs
there. Raising it to satisfy a dependency's stubs would silently stop checking the
promise the packaging makes.

**Cost, stated rather than buried.** `polars` and `numpy` are now `Any` to mypy, so a
typo in a polars call is not caught. `engines/market_sensor/candles.py` is the only
module using polars today and every value it produces is re-validated through a pydantic
`Candle`, which is what makes that acceptable for now. Three ways out, none of them mine
alone: bump the declared floor to 3.12, pin `numpy<2.3` whose stubs parse under 3.11, or
keep this. Raised with the lead.

### Decision: the OHLC fixture's trades are real; its expected bars are not Kraken's

**Agent:** A · **Task:** spec 28 · **Date:** 2026-09-09

**Options.** Compare built candles against Kraken's own published OHLC, or against a
reference computation over the same recorded trades.

**Chose.** The reference computation — because the first option is not available, not
because it is better.

**Because.** `scripts/record.py` subscribes to `book`, `ticker` and `trade`, so the
archive contains **no OHLC channel** to compare against, and no live call can be made:
the operator has rotated the key. So `tests/fixtures/kraken/ohlc.json` holds real Kraken
v2 `trade` frames taken verbatim from `data/raw/` — 1,997 trades across three bars for
BTC/USD, ETH/USD and SOL/USD — and the expected bars are computed by a deliberately
naive pure-Python reduction in `scripts/ohlc_fixture.py` that shares no code with the
`polars` implementation under test.

**What that is worth, and what it is not.** It catches a bug in the bucketing, the
grouping or the `Decimal` handling, which is what the criterion is actually for. It
**cannot** catch a shared misunderstanding of what a candle is, because both
implementations are mine. That limitation is written into the fixture's own
`provenance` field rather than left for a reader to infer, and confirming these bars
against Kraken's published OHLC is a `--live` task.

**Cost.** A weaker guarantee than an independent source, stated as such in three places
so nobody mistakes a PASS for more than it is.

### Frame-level de-duplication, never trade-level

**Agent:** A · **Task:** spec 28 · **Date:** 2026-09-09

**What happened.** Two `record.py` processes ran concurrently from 2026-09-09T13:19:34Z,
so part of the archive holds every frame twice. The obvious de-duplication — drop
duplicate *trades* — is wrong, and would have been very hard to notice.

**Why.** Two recorders produce byte-identical **frames**. Two genuinely identical trades
— same price, same quantity, same second — arrive inside **one** frame, not two, and are
a normal thing for a busy pair. De-duplicating at the trade level would therefore delete
real volume, quietly, in proportion to how active the market was.

**Fix.** `scripts/ohlc_fixture.py` de-duplicates on a SHA-256 of the frame payload plus
its exchange timestamp, and `build_candles` does not de-duplicate at all. The archive
itself is never edited — invariant 11 — so this happens on the way into the derived
artefact and nowhere else.

**Consequence.** The fixture was extracted from 03:00Z on 09-09, comfortably before the
duplication began, and reports `frame_duplicates_dropped: 0` — so the de-duplication is
in place and was not needed for this artefact. That is the right order: build it before
the comparison, not after the comparison surprises somebody.

### A native crash after a clean pass, not reproducible

**Agent:** A · **Task:** spec 28 · **Date:** 2026-09-09

**What happened.** `pytest tests/engines/test_market_sensor.py -q` died after the tests
themselves had all passed, dumping a faulthandler trace whose visible frames were all
pytest session teardown and `runpy`. I had piped to `tail`, so **I do not have the head
of the trace** — which is the only part that names the fault.

**Why it is recorded anyway.** Four immediate re-runs of the same file all exited 0 with
20 passed, and the full suite ran clean at 983 passed. Known Risks records an
intermittent native fault in the seed write path; this file touches no seed and no
SQLite, so it may be a different one — but with no head to the trace I cannot say that,
and saying it without evidence would be worse than saying nothing.

**Fix.** None. Flagged to the lead. The lesson is procedural and was already in the
brief: **capture the head of the output, not the tail.** The tail of one of these is
always `runpy` frames and says nothing at all.

### The loader's pydantic boundary, and exactly what it does not cover

**Agent:** A · **Task:** spec 30 · **Date:** 2026-09-09

**What happened.** `research/historical.py` is the second module in `src/` to import
`polars`, which is the point at which the mypy compromise recorded above stops being
comfortable. That compromise was acceptable because `engines/market_sensor/candles.py`
re-validates every value it emits through a pydantic `Candle`; a loader that returned a
dataframe would have no such boundary.

**Fix.** `load_archive` returns an `ArchiveReport` — a frozen pydantic model — and every
number a caller acts on is a validated field on it: `gap_count`, `row_count`,
`timestamps`, `duration_buckets`, `largest_gap_bars`, `missing_bars`,
`duplicate_timestamps`, `out_of_order_rows`. So the same property holds for both polars
users.

**What it does not cover, stated rather than implied.** **The dataframe itself is
unvalidated.** `to_frame` builds a `pl.DataFrame` and `load_archive` writes it to Parquet
when asked, and nothing type-checks that call chain while polars is `Any` to mypy. The
guarantee is "every value the loader *reports* is validated", not "the loader is
type-checked". A reader who takes the pydantic boundary as covering the frame would be
wrong.

**Money never goes through polars' parser at all.** The CSV is read with `csv.reader` and
the money columns become `Decimal` in Python before polars ever sees them, so an exact
value cannot be lost to a float on the way in. polars does the columnar work afterwards,
on values that are already exact. That is a stronger property than reading the CSV with
polars and casting, and it is the reason the reader is `csv` rather than
`pl.read_csv`.

### Measured: `numpy<2.3` restores full type checking, and nothing objects

**Agent:** A · **Task:** spec 30 · **Date:** 2026-09-09

**What happened.** The lead asked for a measured answer rather than a third hypothetical
about the mypy compromise. Tested without touching the shared virtualenv — other agents
run against it — by installing numpy 2.2.6 into a scratch directory and prepending it to
`PYTHONPATH`.

**Result, with the `numpy`/`polars` override in `pyproject.toml` disabled entirely:**

    mypy --strict src/   -> Success: no issues found in 65 source files
    pytest tests/ -q     -> 1029 passed in 45.57s

And polars typing is genuinely live rather than merely silent, which is the part worth
proving separately — a scratch file calling a method that does not exist:

    error: "DataFrame" has no attribute "sort_bogus"  [attr-defined]

Under the current arrangement that call type-checks clean, because polars is `Any`.

**Why the proof needed its own step.** "mypy passes" is exactly what the broken state
produced too. A configuration that stops checking and a configuration that finds nothing
wrong print the same line, which is the failure this phase has now hit four times in four
different places. The only way to tell them apart is to hand the checker something it
ought to reject.

**Not committed.** The finding went to the lead with the other two options; the version
ceiling is a dependency decision and not A's to take alone.

### Spec 30's fabricated archives, and the assertion that matters

**Agent:** A · **Date:** 2026-09-09

**Options.** Assert the loader's gap statistics, or also assert the output's timestamps
against the input's.

**Chose.** Both, as separate tests, and the second one is the one to keep if either has
to go.

**Because.** A loader that counts gaps correctly **and** emits filled rows passes every
gap assertion. It reports three gaps of 1, 2 and 4 bars, buckets them correctly, names
the largest — and quietly hands Phase 4 a continuous series containing candles at prices
that never traded. The triple-barrier labeller then walks forward from a decision bar,
touches a barrier that never existed, and produces a label the model learns from. Nothing
raises, nothing looks wrong, and every chart looks tidier than the truth.

`test_no_timestamp_in_the_output_was_absent_from_the_input` is the only assertion in the
file that catches it, and `test_the_series_is_left_discontinuous_on_purpose` states the
same thing positively: after loading an archive with a hole, consecutive output
timestamps are **not** all one interval apart, and that is correct.

**Also worth recording: a test I wrote badly and rewrote.** The first version of
"the loader offers no way to fill a gap" scanned the module's *text* for `interpolate`,
`forward_fill` and friends. It failed immediately — because the module's docstring says
"interpolate" repeatedly, on purpose, since saying so is most of that docstring's job. A
text scan would have forced the prose to stop saying the thing it exists to say. It now
walks the module's AST and looks for those names as *identifiers*, which is what was
meant. A second test in the same file was circular in the same way — it scanned its own
source for a string it itself contained — and was deleted rather than patched, because it
asserted nothing a fresh clone does not already enforce.

**Cost.** Three of the loader's tests are about what the loader must *not* do, which
reads oddly next to the ones about what it does. That is the correct ratio here.

### A shared fixture that three tests quietly rewrote for each other

**Agent:** A · **Task:** spec 29 · **Date:** 2026-09-09

**What happened.** `test_each_bad_scenario_differs_from_clean_in_exactly_one_respect`
failed with `('stale', ['missing_bars', 'quotes'])` — the `stale` fixture had somehow
acquired a missing bar. It had not been written that way.

**Why.** `BAD_DATA_SCENARIOS` is a module-level mapping of nested dicts, and my test
helper did `dict(BAD_DATA_SCENARIOS[name])` — a **shallow** copy. The outer dict is new;
`state["market_sensor"]` is the *same object* as the fixture's. An earlier test set
`state["market_sensor"]["missing_bars"]` to exercise a multi-finding tick, and from that
point on every test in the file, and every consumer of the module, saw a `stale` fixture
that was also missing a candle. The failure surfaced three tests away from the cause and
blamed the fixture rather than the test that had rewritten it.

**Fix.** `bad_data_state(name)` in `engines/data_guard/contracts.py` returns a
`copy.deepcopy`, and every test that intends to modify a scenario goes through it.

**Consequence, and the reason this is worth an entry.** `scripts/verify.py` does the
same shallow copy — `dict(scenarios[key])` — and is **correct today** only because the
engine does not mutate what it is handed. That is a property of the current
implementation, not of the interface, so it is exactly the kind of thing that stops being
true without anyone noticing. C has been told; the deep-copy factory is documented as
the way to take a scenario you intend to change; and the assertion that each bad scenario
differs from `clean` in exactly one respect is what caught it and stays.

The fixture-sharing itself is right and I would do it again: the fixtures live in the
engine's own contracts module so that a criterion and a test suite cannot drift from the
engine's idea of `state["market_sensor"]`. Sharing the *shape* is the point; sharing
mutable *instances* was the mistake.

### A fourth reason code, and why it is not just "stale"

**Agent:** A · **Task:** spec 29 · **Date:** 2026-09-09

**What happened.** The spec names three block conditions. Engine 4 emits four, and the
extra one is `no_market_data`.

**Why.** Invariant 3 says a gate that cannot reach its data blocks, so the empty case
needs a verdict whether or not the spec enumerates it — and it is not hypothetical: C's
fake Kraken client is REST-only, so on the real tree `market_sensor` publishes no quotes
and this is the code that fires.

I tried folding it into `market_data_stale` first, and the **prose** is what stopped me.
"Market data is older than the guard allows" is a false sentence when there is none, and
it would send an operator looking for a lagging feed rather than an absent one. Those
have different causes and different fixes.

**Fix.** A distinct code, agreed with C before landing rather than after — C's own
standing request, and the right order: `REASON_PROSE` is C's surface, and a code missing
from it renders as "No reason was recorded." **silently, with no error anywhere.**

**Consequence.** `test_every_reason_code_exists_in_the_consoles_prose_map` derives the
list from this engine's own constants rather than repeating it, so adding a fifth code
without telling C fails in A's own suite instead of going quiet on the console.

### Decision: the gate blocks on a hole in the candle series, and the loader still must not fill one

**Agent:** A · **Date:** 2026-09-09

**Options.** Treat a missing candle as a data fault and block, or treat it as the quiet
market it is and pass — which is what `architecture-context.md` says about the *archive*.

**Chose.** Block, and write down at length why that is not a contradiction.

**Because.** The two rules are about different acts. `architecture-context.md` and spec
30 govern **labelling**: a missing candle means no trades occurred, so inventing one
fabricates a barrier touch and poisons a label. Engine 4 governs **trading**: acting on a
series with a hole in it risks money on a price nobody observed. Fail-closed points in
opposite directions for the two, and both directions are the cautious one.

**Cost.** It reads like a contradiction on first encounter, and the obvious "fix" for
either half breaks the other. So it is stated three times — next to the constant in
`contracts.py`, in the engine README, and in a test whose name is the claim — and C
carried it into the comment above the reason codes as well.

### The registration rehearsal, run before asking for it

**Agent:** A · **Task:** specs 26-29 · **Date:** 2026-09-09

**What happened.** The lead deferred `bootstrap.py` registration until the tree was
globally green, on the grounds that registering `data_guard` as a real gate changes what
`orchestrator_empty_registry` — a **Phase 0** criterion — exercises on every tick.

**Fix.** `tests/engines/test_guard_chain_rehearsal.py` drives the **real** `Orchestrator`
over all four engines against C's fake client, twice, before the request is sent. Two
ticks rather than one on purpose: `state` is fresh every tick except `state["system"]`,
and an engine that quietly depended on something surviving would pass a single-tick test
and fail the second.

**What it found, which is worth knowing before registration rather than after.** Against
the fake client the guard chain **blocks every tick**, with
`state["data_guard"]["reason_code"] == "no_market_data"` — the fake is REST-only, so
there are no quotes. That is correct, and it completes the tick rather than raising,
which is the thing that matters: C's `console_shows_live_rows` turns an exception during
a tick into a FAIL naming it.

And with `data_guard.max_data_age_s` still absent from the config, the tick **still
completes**: `config.get` raises, the orchestrator converts it to `ERROR` with
`blocks_trading=True`, and engines 1 to 3 have already reported. So registering engine 4
before the operator supplies the key degrades the loop to "blocked" rather than breaking
it — which is the fail-closed outcome, and is asserted rather than assumed.

### The Windows file-handle teardown ERROR: hardened, not fixed, and the difference matters

**Agent:** A · **Task:** Phase 2 housekeeping · **Date:** 2026-09-09

**What happened.** B saw `tests/cli/test_entrypoints.py::test_console_refuses_an_unset_operator_key`
produce a teardown **ERROR** — not a FAILED — on one run, and it did not reproduce. The
fixture's own docstring already predicted the class of fault: `configure_logging()`
replaces the root logger's handlers process-wide, and a `TimedRotatingFileHandler` left
open holds a file inside a directory pytest is about to remove, which on Windows is an
error rather than a warning.

**Why it could not have been that test.** I could not reproduce it either, and reading
the code says why: `_isolated_runtime` is **autouse** in that module and already closed
every root handler on teardown, and the test in question returns 2 from the config
refusal *before* `configure_logging()` is ever called. So nothing in that module opened
a handle and nothing in that module failed to close one.

**What it probably was.** A handler leaked by a test in **another** module points at
*that* module's `tmp_path`, survives into this one, and is still open whenever pytest
gets round to collecting the older directory. The error then lands on whichever test
happens to be running when the collection happens — which is exactly the shape of the
observation: seen once, here, unreproducible, and with no local cause.

**Fix.** `_release_log_handlers()` is now called **before** the yield as well as after.
Releasing on entry means this module cannot be the place a stranger's handle comes due.

**Why this is filed as hardening rather than a fix, deliberately.** It does not stop
another module leaking a handler; it stops that leak being charged to this one. Claiming
it fixed a fault I could not reproduce would be worse than saying what it actually does.
If the ERROR reappears somewhere else, the same treatment belongs in whichever module
opens the handle — and the search should start with modules that call
`configure_logging()` without an autouse teardown, not with the module that reports it.

### A background thread that would have died silently

**Agent:** A · **Task:** Phase 2 hardening · **Date:** 2026-09-09

**What happened.** Reviewing `ws.py` after spec 29, not because anything failed:
`_run` caught only `_TRANSPORT_ERRORS` — `OSError` and `WebSocketException`. Anything
else escaping `_session` would end the coroutine, end `asyncio.run`, and end the thread.

**Why that is worse than an ordinary uncaught exception.** There is no caller to raise
into. The thread is a daemon, the traceback goes nowhere anybody looks, and the process
carries on perfectly happily with `connected` false and no frames arriving. **A dead
recorder is indistinguishable from a quiet market** — which is the single failure the
entire recording apparatus exists to make impossible, and the reason the digest reports a
tiling rather than a gap count. Every candidate cause is real: a pydantic
`ValidationError` from a frame shape nobody predicted, a `RecursionError` on a pathological
payload, a `MemoryError`.

**Fix.** `_run` now also catches `Exception`, records the break as a **gap** carrying
`unexpected <ExceptionType>: <message>` as its cause, and reconnects on the same backoff.
Engine 2 appends that gap to `data/raw/` on the next tick exactly like a disconnect.

**Why that is not a swallowed exception, which is the obvious objection.**
`code-standards.md` forbids `except Exception` without re-raising *or logging with the
traceback*. This does the durable equivalent of the second: the failure reaches the
append-only archive, where it outlives the process, rather than a log line that
`logs/` rotates away in fourteen days. It reconnects rather than stopping because a
recorder that gives up loses data nothing can recover; and if the fault is permanent the
backoff climbs to its 60-second ceiling and the archive fills with identically-caused
gaps, which says so about as plainly as anything could.

**Also added while there.** `test_start_and_stop_are_idempotent_and_the_thread_actually_exits`
drives the real thread against a socket that connects and then delivers nothing — the
shape a real socket has on a quiet market, and the one that would hang shutdown if
`stop()` did not reach the loop thread through `call_soon_threadsafe`. The thread
lifecycle was the only part of this client with no coverage at all, which is a poor place
for that to be true.
