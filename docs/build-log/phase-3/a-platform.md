# Build log — Phase 3 — a-platform

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem
and its fix, and every decision where two approaches were viable. Not at the end of
the session — three IDE crashes in Phase 1 each took the code and the log at different
moments, and only the entries already written survived.

Minimum headings per entry: What happened, Why, Fix.

The lead consolidates these into `docs/build-log/phase-3.md` at phase close.

## Entries

### Decision: `cache_ttl_s` landed optional, and refuses at the point of use

**Agent:** A · **Task:** spec 38 step 1 · **Date:** 2026-09-10

**Options.** Spec 38 step 1 is a two-sided handoff: I add `cache_ttl_s` to the config
model, the lead pastes the matching YAML block, neither half is committed without the
other. The obvious implementation is a required field — `cache_ttl_s: CacheTtlConfig`
— because every other threshold in `platform/config.py` is required and that is what
"validated like every other threshold" reads as. The alternative is
`CacheTtlConfig | None = None`, with every reader raising on the `None`.

**Chose.** Optional at load, refused at read.

**Because.** A required field is the lead's 2026-09-10 failure with the halves
reversed. The lead pasted the YAML without the model field, `extra="forbid"` made
`load_config()` raise, and every test in the tree failed until it was reverted. A
required model field without the YAML fails in exactly the same place for exactly the
same reason: `tests/conftest.py`'s `paper_config` fixture, `scripts/verify.py` and
`test_engine_starts_against_the_committed_config` all load the committed
`config/default.yaml`, and a required field it does not carry takes all of them down.
Spec 38 also says in as many words *"you can test with a fabricated config until the
YAML lands"*, which is only possible if the shipped file still loads. So the field had
to tolerate the gap, and the gap is real: teammates do not commit, so the working tree
genuinely sits in the half-landed state until the lead acts.

**Nothing was defaulted, and that is the part worth checking.** `None` is not a value
and nothing is computed from it. `Config.get("kraken.cache_ttl_s.asset_pairs")` raises
`ConfigKeyError` when asked to descend through it, and `KrakenRestClient._require_ttl`
raises `KrakenUnavailableError` naming the missing key rather than caching for an
interval nobody chose. Absence fails closed at the point of use, which is the
`data_guard.max_data_age_s` precedent from Phase 2. A `null` in the YAML is still
refused by name at startup by `_refuse_nulls`, which is what spec 38 step 3 actually
asks for — that function scans the raw YAML and never needed the field to be required.

**Cost.** A window in which the shipped config could be missing the key and the daemon
would only discover it at the first fetch. The lead approved closing that window the
moment the YAML landed; the follow-up entry below records it.

### Two mechanisms sharing a word: the cache and the retention

**Agent:** A · **Task:** spec 38 · **Date:** 2026-09-10

**What happened.** The first shape I wrote for the cache used one dictionary keyed by
call name, alongside the existing `self._retained` dictionary keyed the same way. Two
dictionaries with the same keys, the same shape and opposite lifetimes.

**Why that is wrong.** Invariant 2 spends four paragraphs on the fact that "a cache
stale beyond its TTL counts as a failed fetch, and is retained anyway" is two rules
sharing a word. `asset_pairs` is both cached and retained; `trade_volume` is cached and
must never be retained; `balance` is retained and must never be cached. Written as two
parallel dictionaries, the difference between those three is a `frozenset` membership
test in each of two helpers, and the failure mode of getting it wrong is silent — a
retained fee tier would look exactly like a working cache and would price the cost gate
on a fee nobody fetched.

**Fix.** The cache is two named fields, `_cached_asset_pairs` and
`_cached_trade_volume`, each with its own TTL field, its own expiry check and its own
call site. Retention stays in `_retained`. `RETAINED_CALLS` and `CACHED_CALLS` are both
written out as module constants so the asymmetry is visible rather than inferred. Two
separate fields also make "the two TTLs are read separately" structural — there is no
shared object a later edit could make one TTL govern both through.

**One decision inside it.** An entry whose age is *exactly* its TTL is treated as
expired, not fresh (`0 <= age < ttl`). Both readings of "stale beyond its TTL" are
defensible on a boundary; the fail-closed direction is to fetch again, so that is the
one taken, and there is a test pinning the microsecond either side of it. A negative
age — a clock that stood still or moved back — is expired for the same reason.

**Consequence.** An expired entry is dropped from its field *before* the network is
touched, so there is no code path on which it can be returned. That is stronger than
merely not writing the return: a later "optimisation" that reordered the expiry check
would find nothing to return.

### Adding a cache broke six tests that were never about caching

**Agent:** A · **Task:** spec 38 · **Date:** 2026-09-10

**What happened.** Landing the TTL cache turned seven existing tests red. Six are in
`tests/clients/kraken/test_rest.py` and one in `test_secrets.py`. The obvious reading —
the one the failure message supports — is that they all fail for the same shallow
reason: `build_client` at `test_rest.py:86` predates the constructor change, passes
neither `asset_pairs_ttl_s` nor `trade_volume_ttl_s`, and `_require_ttl` raises
`KrakenUnavailableError` naming the missing key before anything else in the call
happens. Thread the two TTLs through the helper and all seven go green.

**Why that repair would be wrong for three of them.** Those three call the *same
cached endpoint twice* against a `FixedClock` that never moves, and each of them
depends on the second call actually reaching the network:

- `test_pair_rules_come_from_the_payload_and_change_when_it_changes` alters the
  fixture between the two calls and asserts the second differs. With a TTL supplied
  and the clock standing still, the second call is a cache hit and returns the first
  snapshot. The test fails on the comparison instead — and if the comparison were
  ever weakened, it would pass while proving nothing.
- `test_the_fee_tier_comes_from_the_payload_and_changes_when_it_changes` is the same
  shape for `TradeVolume`.
- `test_pair_rules_and_balances_are_retained_across_a_later_failure` serves an error
  for the second `AssetPairs` call and asserts it raises. A cache hit returns
  successfully and nothing raises, so `pytest.raises` fails.

The three tests are testing "the value is fetched, never a constant" and "the last
known good survives a failure". Both properties are still true and both still matter;
what changed is that reaching the second fetch now requires advancing the clock past
the TTL. Making the TTL large enough to be irrelevant, or short enough that it always
expires, would have made them green while removing the interaction the cache
introduced.

**Fix.** `build_client` takes a `FixedClock` the test can move, defaults both TTLs to
distinct non-equal values, and lets a caller override either. The three tests above
advance the clock past the relevant TTL between the calls **and assert the transport
was hit again**, so a future change that made the second call a cache hit fails on the
request count rather than on a value comparison that might be relaxed.
`test_pair_rules_and_balances_are_retained_across_a_later_failure` is now the place
where spec 38's "retention survives that same expiry" is proved: the expiry is what
sends the call to the network, the network fails, the call raises, and
`last_known_good_asset_pairs` still holds the pre-expiry snapshot.
`test_the_fee_tier_and_the_book_are_deliberately_not_retained` gets the matching
negative — after the same expiry and the same failure there is no last-known-good fee
tier anywhere, because the cache is the only thing that ever held it.

**Consequence.** The cache is not a transparent optimisation. Any test that calls
`asset_pairs()` or `trade_volume()` more than once is now a test about the cache
whether it meant to be or not, and has to say which of the two it wants. That is worth
knowing before spec 39 drives two real ticks through the same client.

### A test that had gone green for the wrong reason

**Agent:** A · **Task:** spec 38 · **Date:** 2026-09-10

**What happened.** `test_a_private_call_without_credentials_blocks_rather_than_defaulting`
was **passing** through all of this, and it should not have been. It builds a client
with `credentials=None` — and, because it constructs `KrakenRestClient` directly
rather than through `build_client`, with no TTLs either — calls `trade_volume()` and
asserts `KrakenUnavailableError`. It got one. From `_require_ttl`, about
`kraken.cache_ttl_s.trade_volume`, several lines before `_private` is reached and the
credential check it exists to exercise ever runs.

**Why it matters more than the six red ones.** A red test tells you where to look. This
one was green, sitting in the middle of a file whose other tests were failing loudly,
asserting a property it had stopped testing. The exception type is the same, so
nothing in the assertion could have noticed. This is the same shape as the
`state["exchange"]` audit that the wiring specs exist for: two things agreeing on a
type while disagreeing about the subject, with a green suite over the top.

**Fix.** The test constructs with both TTLs supplied, so the TTL check passes and the
call reaches the credential check that is its actual subject. The assertion now names
the subject too — the message must mention credentials and must **not** mention
`cache_ttl_s` — so the test cannot silently start passing for a third reason later.

**Consequence.** Worth generalising: `KrakenUnavailableError` is deliberately the one
type every fail-closed path raises, which makes `pytest.raises(KrakenUnavailableError)`
on its own a weak assertion in this package. Where the *reason* is the point, the test
asserts on the message.

### Decision: no narrowing `assert` in the cache path, and therefore no suppression

**Agent:** A · **Task:** spec 38 · **Date:** 2026-09-10

**What happened.** `ruff check src/` reported two `RUF100` errors — unused `noqa`
directive, non-enabled rule `S101` — on the two `assert cached is not None` lines in
`asset_pairs()` and `trade_volume()`. `S` (flake8-bandit) is not in the selected rule
set in `pyproject.toml`, so the suppression suppressed nothing and `RUF100` is correct
to say so.

**Options.** Drop the directive and keep the bare `assert`, or remove the need for the
narrowing altogether.

**Chose.** Removed the need. `_cache_hit(cached, ttl) -> bool` became
`_fresh(cached, ttl) -> Snapshot | None`, which returns the entry when it is inside its
TTL and `None` when it is not. The call site binds the result and returns it if it is
not `None`, so the type narrows by ordinary control flow and there is nothing to assert.

**Because.** `code-standards.md` is explicit that a suppression is for a lint that
would make the code *wrong* to obey, and that one is never added to make a failing
check pass. Neither applied: the directive was inert, so obeying `RUF100` costs
nothing. That leaves the bare `assert`, and an `assert` in `src/` is a statement that
disappears under `python -O` — here it would disappear from the function that decides
whether a fee is fresh enough to price a trade. It was never load-bearing (`_cache_hit`
had already done the check) which is precisely the argument for deleting it rather than
keeping it. Making the helper return the value it has already validated is smaller than
either alternative and removes the class of problem.

**Consequence.** `_fresh` is generic over the two snapshot types through a value-
restricted `TypeVar`, so `asset_pairs()` gets a `PairRulesSnapshot | None` and
`trade_volume()` a `FeeTierSnapshot | None` rather than a union of both that would need
narrowing again at each call site.

### Decision: a construction site that cannot forget the TTLs

**Agent:** A · **Task:** spec 38 · **Date:** 2026-09-10

**What happened.** With the cache landed and the tests repaired, `grep` for
`asset_pairs_ttl_s` found it in `rest.py` and in the tests, and **nowhere else in
`src/`**. The two config keys the lead had just pasted were unreachable from the
running system: `KrakenRestClient` is constructed with two optional TTL parameters,
`clients/kraken/client.py` takes an already-built REST client, and `cli/engine.py`
still passes three `None` client slots. Wire the daemon up as it stood and every
`asset_pairs()` and `trade_volume()` call would raise about a missing TTL — with the
value sitting in `config/default.yaml` the whole time.

**Why the parameters are optional at all, since that is what allows it.** Because
tests and `scripts/` build clients directly and the absence has to fail closed at the
point of use rather than at construction — the same argument that made the config
field optional for a few hours. It is the right behaviour and it has a cost: an
optional parameter is precisely the kind of thing a caller omits by accident, and
this one had already been omitted by seven tests.

**Options.** Make the constructor require both TTLs, which turns every direct
construction into a compile-time reminder but also makes `KrakenRestClient`
unbuildable without deciding a caching policy — wrong for a script that makes one
public call. Or add a single construction path that reads config, and leave the
constructor as it is.

**Chose.** `KrakenRestClient.from_config(config, clock=..., limiter=...)`. It reads
`config.kraken.rest_timeout_s`, `config.kraken.cache_ttl_s.asset_pairs` and
`config.kraken.cache_ttl_s.trade_volume` — the two TTLs as two separate attribute
accesses on two separate fields, with no intermediate variable holding "the TTL",
because one shared value is the shape spec 38 exists to prevent and writing it down
once is how it comes back.

**The limiter is a parameter and not built here**, which is the one non-obvious part.
It is *the* limiter, shared with the WebSocket client, and a factory that made its own
would hand a single account two independent budgets against one rate limit — a bug
that shows up as a ban mid-session and not before.

**Cost.** Two ways to build the client still exist, and only one of them reads config.
`test_from_config_reads_each_ttl_from_its_own_key` asserts the config path through
behaviour rather than by reading the private fields back: it configures 1000 and 10,
parks the clock at 20 seconds, and asserts that exactly one of the two calls reached
the network. Reading the fields would only have proved that the constructor stored
what it was handed, which was never in doubt.

### The rate limiter cannot be held across ticks, and it fails late rather than first

**Agent:** A · **Task:** spec 39 · **Date:** 2026-09-10

**What happened.** Spec 39 has `cli/engine.py` construct the real clients once and
hold them for the life of the daemon, which means holding one `RateLimiter` across
every tick. `RateLimiter` serialises with an `asyncio.Lock`, and `platform/aio.py`
runs **one `asyncio.run` per engine call** — a fresh event loop every tick, by
design. An `asyncio.Lock` binds itself to the first running loop it needs a future
on and raises `RuntimeError: ... is bound to a different event loop` on any later
one. Reproduced directly:

```
tick 1: ok, waits=1
tick 2: ok, waits=2
tick 3: RuntimeError: <asyncio.locks.Lock object at 0x... [locked]> is bound to a different event loop
```

**Why it is worse than it looks.** Two things make this hard to find rather than
merely broken.

*It does not fire on the first contended tick.* `Lock.acquire` takes an uncontended
lock without ever touching `_get_loop()`, so nothing binds until a caller actually
has to wait, and the bookkeeping the lock leaves behind means the raise can land a
tick or two after the binding. A daemon that runs, then stops working, is diagnosed
completely differently from one that never started — and this machine already has an
intermittent fault that this would be filed under.

*It does not fire at all on the shipped budget.* `rest_capacity: 15`,
`rest_refill_per_s: 0.5` and `loop_tick_s: 60` give 30 tokens of refill between ticks
against engine 1's three calls, so the bucket is never short, nothing ever waits and
the lock is never contended. I ran eleven ticks at the shipped numbers without a
failure. It arms the moment a tick makes more than about thirty REST calls, which is
exactly what engine 7 `scout` plus per-pair order books will do in the next spec —
so this would have landed as a latent defect in spec 39 and detonated in someone
else's.

**Why the token state must still survive the loop.** The whole reason the limiter is
held across ticks is that the budget is an account-level fact: rebuilding it each tick
would hand every tick a full bucket and defeat the rate limit entirely. So "make a new
limiter per tick" is not a fix, it is the bug the class exists to prevent.

**Fix.** The lock is now created per running loop and the token state is not.
`_loop_lock()` returns the lock when the running loop is the one it was made for and
replaces it when the loop has changed; `_tokens`, `_updated_at`, `_granted` and
`_waits` are untouched by that and carry across as before. Recreating is safe because
concurrency only ever exists *inside* one `asyncio.run`: the previous loop is closed
and nothing can still be waiting on the lock it held. The property the lock provides —
that twenty coroutines in one loop do not all see a full bucket at once — is exactly
as strong as it was, because that property was always within a single loop.

**Consequence.** `tests/clients/kraken/test_limiter.py` gains a test that drives
genuine contention across two separate `asyncio.run` calls and asserts both halves:
that it does not raise, **and** that the budget carried over rather than resetting. The
second assertion is the one that matters — a "fix" that rebuilt the limiter would pass
the first and silently remove the rate limit.

### The first test I wrote for the limiter fix passed against the unfixed code

**Agent:** A · **Task:** spec 39 · **Date:** 2026-09-10

**What happened.** Having reproduced the event-loop binding by hand, I wrote the
regression test for it, watched it pass, and then ran it against the *unfixed*
limiter to check it had teeth. It passed there too. The test was worthless and I
would have shipped it as the evidence for the fix.

**Why.** `FakeTime.sleep` in `tests/clients/kraken/test_limiter.py` is
`async def sleep(self, seconds)` whose body only advances a counter. It contains no
`await`, so **it never suspends** — an `async def` that never awaits runs to
completion without ever yielding to the event loop. `RateLimiter.acquire` holds the
lock across `await self._sleep(...)`, so with a sleep that does not yield, the first
acquirer runs the entire critical section before the second one starts. The lock is
taken and released twenty times without ever being *contended*, and an
`asyncio.Lock` binds itself to a loop only when it has to create a future for a
waiter. No contention, no binding, no bug — against the broken code.

Isolated it to be sure rather than reasoning about it. Against the unfixed limiter:

```
non-yielding        : no error (waits=7)
yielding            : RuntimeError -> ... is bound to a different event loop
real asyncio.sleep  : RuntimeError -> ... is bound to a different event loop
```

The only difference between the first two is one `await asyncio.sleep(0)` inside
the injected sleep, which yields to the loop and waits no real time.

**Fix.** The new test injects a sleep that advances the fake clock **and** yields.
It keeps injected time — no test here waits for real — and adds back the single
property the injection had accidentally removed.

**Consequence, and it is larger than this test.**
`test_concurrent_acquirers_are_serialised_and_stay_inside_the_budget` has always run
its twenty coroutines strictly one after another, for the same reason. Its arithmetic
assertion is real and still worth having — twenty tokens at ten per second is 1.5
seconds of injected clock and anything faster means someone was granted a token the
budget did not have — but its name claims a serialisation property it has never
exercised. I have not rewritten it: it tests something true, and the concurrency it
does not cover is now covered by the new test, which says so in its docstring.

This is the third time this phase that a green test turned out to be asserting
something other than its subject, and all three have the same shape: **a double that
is simpler than the thing it stands in for, in exactly the dimension the test is
about.** The fake transport that never counted requests, the client built without a
TTL, and now a sleep that does not sleep. Worth stating as a habit rather than three
incidents — when a double replaces the mechanism under test, check it can still fail.

### Engine 2 turned into a gate by reading a config key that has not landed yet

**Agent:** A · **Task:** spec 39 · **Date:** 2026-09-10

**What happened.** Adding the subscription scope to engine 2 took four tests in
`tests/engines/test_guard_chain_rehearsal.py` red, and the failure was not the one
the change was about:

```
assert state["trading_blocked_by"] == "data_guard"
AssertionError: assert 'market_data_recorder' == 'data_guard'
```

Engine 2 had become the tick's primary blocker.

**Why.** The scope reads `trading.stable_quote_currencies`, whose YAML half has not
landed — I have requested it and the lead has not pasted it yet. `Config.get` raises
on a key that does not exist, deliberately and correctly: "an engine silently
receiving `None` for a threshold is exactly the failure this project refuses to
allow". The orchestrator turns any uncaught exception into `ERROR` with
`blocks_trading=True`, per contract rule 7. So a missing optional key made **engine 2
block trading** — an engine whose own module docstring says, in bold, that it is not a
gate and never blocks. It also displaced `data_guard` as the primary blocker, which
would have made `block_records.is_primary` wrong for every tick in that window.

The distinction the config doubles already draw is the one that matters here, and
`tests/harness/doubles.py` states it exactly: a key that is *present* and `null`
returns `None`, because "the operator has not decided yet" is not the same as "this
key does not exist". `stable_quote_currencies` is currently the second of those and
will become the first the moment the lead pastes the block.

**Fix.** One narrow helper, `_optional_setting`, catching `KeyError` only —
`ConfigKeyError` is a `KeyError` subclass and C's `MappingConfig` raises a plain one,
so the same catch covers the real config and the double. It is used for this one key
and nothing else: `trading.allow_crypto_quoted` is a required field on the model and
is still read with a bare `get`, so a genuinely missing required key still fails
loudly. Absence resolves to "the crypto-quoted exclusion was not applied", which
engine 2 publishes as `crypto_quoted_excluded: false` rather than leaving implicit.

**Consequence, and it is the part worth carrying.** This is the failure mode of the
paired config handoff that spec 38 did *not* hit. There, the reader was a client that
is allowed to raise, so an absent TTL fails closed and blocks — which is right. Here
the reader is an engine that must never block, so the same absence, handled the same
way, silently converts a recorder into a gate. **A half-landed config key is not
uniformly safe just because the reader raises; whether raising is safe depends
entirely on who is reading.** The landing order that spec 38 established fixes the
window; it does not decide what happens inside it, and that is a per-reader question.

### `acsoe engine` crashed on its first tick the moment it had a real store

**Agent:** A · **Task:** spec 39 · **Date:** 2026-09-10

**What happened.** Wiring the three real clients into `cli/engine.py` took two CLI
tests red with a `TypeError` from inside the orchestrator, on tick 1:

```
File "src/acsoe/core/orchestrator.py", line 292, in _record_run
    self._log("run_recorded", run_id=self._run_id, mode=str(self._config.mode))
File "src/acsoe/core/orchestrator.py", line 129, in _log
    self._logger.debug(event, run_id=self._run_id, cycle_id=self._cycle_id, **fields)
TypeError: structlog.stdlib.BoundLogger.debug() got multiple values for keyword argument 'run_id'
```

`Orchestrator._log` already binds `run_id` on every line — that is its job — and
`_record_run` passes `run_id=` again in `**fields`. The same duplicate is in
`run_record_failed` two lines above, and that one is *inside* an `except` block, so
it would replace whatever the store actually failed with.

**Why it had never fired.** It needs a real store **and** a real logger at the same
time, and until this change nothing had both. `_record_run` is only reached through
`_consume_commands`, which is skipped when `context.clients.store` is absent — and
`cli/engine.py` passed `Clients()` with three `None`s, which is the gap spec 39
exists to close. Every test that drives the orchestrator against a real store
constructs it with `logger=None`, so `_log` returns before the call. The daemon is
the only caller that has both, and the daemon had no store. Two independent
absences, each of which made the other harmless.

That is the same shape as the `state["exchange"]` audit this phase was called for:
two halves that each pass their own tests while nothing exercises them together. It
is worth noting that it was not found by a test aimed at it — it was found by
wiring the real thing up, which is the only thing that had both halves.

**Fix — not mine.** `src/acsoe/core/orchestrator.py` is lead-only, ownership rule 2,
so this is escalated rather than edited. The fix is to drop `run_id=self._run_id`
from the two `_log` calls at lines 289 and 292; `_log` supplies it already, and both
lines are already correct in intent.

**A second, smaller thing on my own side of the boundary.** The `engine_starting`
line I added logged `credentialed=True/False` so an operator can see whether the
daemon has a key without the key going anywhere near a log. It came out as
`"credentialed": "<redacted>"`, because the key-name redactor matches any field whose
*name* looks like a credential and this one does. The redactor is right and the field
name was wrong: it is a boolean about presence, not a credential, and redacting it
destroys the only thing it was for. Renamed to `api_key_present`. Worth recording
because the failure is silent — the line still appears, still looks fine, and says
nothing.

### Correction: `api_key_present` is redacted too

**Agent:** A · **Task:** spec 39 · **Date:** 2026-09-10

The entry above says the `credentialed` field was renamed to `api_key_present`. That
name is redacted for the same reason the old one was — `SECRET_KEY_TOKENS` in
`platform/logging.py` contains `api_key`, and the match is a substring test on the
field name, so `api_key_present` contains it outright. I caught it by reading the
token list rather than by running it, which is luck; the failure mode is a line that
appears, looks correct and carries `<redacted>` where the answer should be.

The field is `private_calls_enabled`, which contains none of the twelve tokens and
names the consequence rather than the credential — which is the better field anyway,
because what an operator wants to know is whether `TradeVolume` and `Balance` will
answer, not what is in the environment.

**The general point.** A redaction rule that matches on substrings of field names is
the right design and it cannot tell a credential from a *statement about* a
credential. There is no way to name a boolean "do we have an API key" that both reads
naturally and survives the redactor, so the field has to be named after what it
implies instead. Worth knowing before someone adds `api_key_source` or
`credential_status` and quietly loses it.

### The tripwire I set in Phase 2 did not go off

**Agent:** A · **Task:** spec 39 · **Date:** 2026-09-10

**What happened.** `test_a_tick_over_the_real_registry_records_errors_rather_than_raising`
was written in Phase 2 to pin the daemon's broken state — three `None` client slots,
every engine failing, the tick completing anyway — specifically so that wiring the
real clients would turn it red and force a deliberate rewrite. Spec 39 step 7 is
written on that assumption, and my own progress note says so in as many words.

I wired the real clients. It stayed green.

**Why.** The test never went through `cli/engine.py`'s `run()`. It calls
`build_orchestrator(config, clock, Clients())` and constructs the empty `Clients()`
**itself**, so it pins a fact about a value the test supplies rather than a fact about
what the daemon does. Replacing the daemon's wiring cannot move it, because the
daemon's wiring was never in it. It is a test of `Orchestrator` plus contract rule 7,
which is a real property and was passing for that reason the whole time.

The two tests that *did* go red are `test_engine_starts_against_the_committed_config`
and `test_engine_ticks_against_an_empty_registry_and_exits_zero`, both of which drive
`cli_main.main([...])` — and they went red on the orchestrator's duplicate `run_id`
rather than on anything about clients. So the change was caught, but by tests that
were not aiming at it and for a reason that was not it.

**The lesson, which is the reusable part.** A tripwire has to be attached to the thing
it is watching. I wrote that one against the *symptom* — a tick full of ERRORs — and
reproduced the symptom locally with a hand-built `Clients()`, which decoupled it from
the cause. The version that would have worked asserts on the daemon's own construction
path: whatever `cli/engine.py` builds, not what a test can build. A pin that a test
can satisfy by hand is not a pin.

**Fix.** Replaced with two tests that hold the two halves of spec 39's first
acceptance check. `test_the_daemon_builds_three_real_clients_and_needs_no_credentials`
asserts on what `build_clients` actually returns, including that a missing API key is
not a startup refusal. `test_the_daemon_completes_two_ticks_with_real_clients` runs the
real `build_chains()` registry over C's fake Kraken client, a real temporary store and
a real recorder, for two ticks, and asserts the stop event ends it cleanly. Both are
attached to the daemon's construction rather than to a reproduction of it.

### Decision: `stable_quote_currencies` stays optional, unlike `cache_ttl_s`

**Agent:** A · **Task:** spec 39 · **Date:** 2026-09-10

**What happened.** Spec 38 step 1 established a landing order for a config key whose
model half and YAML half have different owners: A lands the field optional, the lead
pastes the block, A tightens the field to required. That worked for
`kraken.cache_ttl_s` and the lead's entry on the crypto-quoted ruling describes
`trading.stable_quote_currencies` as "the same paired-handoff shape". The values have
now landed. Following the pattern, the next step is to tighten this field to required.

**I have not, and the pattern is the thing that is wrong here rather than the field.**

**Options.** Required, so a config missing the key refuses at startup by name. Or
optional, so a config missing the key starts and every reader decides what absence
means for it.

**Chose.** Optional.

**Because the two keys have opposite consequences for absence, and the lead's own
ruling turns on exactly that.** For `cache_ttl_s` the reader is the REST client, which
raises on absence — so required-at-startup is strictly better than the same refusal
arriving later at the first fetch, and nothing is lost by refusing early.

For `stable_quote_currencies` the readers were ruled to disagree on purpose. Engine 7
`scout` fails closed: with no stable set, a pair not provably stable is out of the
universe, so trading stops and says why. Engine 2 `market_data_recorder` fails open:
it applies the balance rule, skips the exclusion, and publishes
`crypto_quoted_excluded: false`. The ruling's own reasoning is that "fail-closed is
not a direction, it is a question about which error is irreversible" — data loss for
engine 2, an unwanted position for engine 7.

A required field overrules both. An absent key would stop the process at startup, so
**the recorder never runs at all** — which is the irreversible error the ruling
identifies for engine 2, arriving by a different door. With the field optional, an
absent key leaves the system in a coherent degraded state: recording continues, the
universe is empty, and `scout`'s reason code says why. That is the state the ruling
describes, and a required field makes it unreachable.

Note what is *not* weakened by this. `_refuse_nulls` scans the raw YAML before
pydantic sees it, and the lead has added the key to `OPERATOR_REQUIRED_KEYS`, so a key
present-and-`null` is still refused by name at startup. The only case the two options
differ on is the key being absent outright, and that is the case the ruling is about.

**Cost.** The spec 38 pattern now has an exception, and an exception nobody wrote down
is how a pattern becomes a rule that gets applied wrongly. So: **tighten the field when
absence should stop the process; leave it optional when a reader has been ruled to keep
working without it.** The landing *order* is universal; the resting state is not.

### Mutating spec 39's acceptance found a branch that was covered but not tested

**Agent:** A · **Task:** spec 39 · **Date:** 2026-09-10

**What happened.** On the lead's instruction — now a standing rule in
`code-standards.md` — I broke the code deliberately and watched for red, rather than
trusting that tests written to demonstrate a property actually do. Twelve mutations
across `subscription_scope`, `KrakenWebSocketClient.set_subscription` and engine 2's
`_apply_subscription`, each applied on its own and reverted. Eleven were killed
immediately. One survived:

```
SURVIVED  engine 2 claims it derived the scope when engine 1 published nothing
          24 passed in 0.55s
```

Flipping `subscription_derived` from `False` to `True` on the branch where
`state["exchange"]` is absent entirely broke nothing.

**Why, and it is not the obvious reason.** The branch is not rarely executed — it is
executed *constantly*. Every test in `test_market_data_recorder.py` runs engine 2 in a
chain engine 1 is not in, so `state` has no `"exchange"` key and this is the path they
all take. It has excellent line coverage and no assertion anywhere about what it
reports. A tick that had left the subscription alone could have claimed it recomputed
it, and the only thing that would have noticed is an operator reading `state` and
wondering why a derived scope never changed.

The two absences are also genuinely different and I had only tested one. "The fetch
failed" is `pair_rules` or `balances` being `None` inside a published
`state["exchange"]`; "engine 1 published nothing" is the key not being there at all,
which happens when engine 1 raised and the orchestrator recorded `ERROR`. Both must
leave the scope alone, and I had a test for the first and none for the second.

**Fix.** `test_engine_one_publishing_nothing_leaves_the_scope_alone_and_says_so` drives
engine 2 in a guard chain with engine 1 deliberately absent, over a stream that already
has a subscription, and asserts the scope is untouched and reported as not derived. The
mutation is now killed. Full set: twelve applied, twelve killed.

**The lesson is the one the rule was written for, sharpened by which mutation
survived.** It was not an obscure branch. High coverage on a line pointed the opposite
way from the truth — the line ran in most tests in the package, which is exactly why
nobody thought to assert on it. **Coverage counts executions; a mutation asks whether
anything would object.** I would not have found this by re-reading the tests, because
re-reading is what produced them.

### Sweep for the cannot-fail family: four findings, two of them mine

**Agent:** A · **Task:** lead-assigned sweep · **Date:** 2026-09-10

**What happened.** The lead asked for a deliberate sweep for the three shapes this
phase has produced five instances of by accident, prioritising `tests/conftest.py` and
`tests/harness/` because a defect in a shared fixture is multiplied across every
agent's suite and nobody owns them as a spec. Findings below; two are mine and fixed
here, two are C's and are reported rather than edited.

**Mine, finding 1 — `data_guard`'s reason codes are hand-listed, and my own progress
file claims they are not.** `test_every_reason_code_exists_in_the_consoles_prose_map`
in `tests/engines/test_data_guard.py` writes out four codes by hand and asserts each is
a key in C's `REASON_PROSE`. My Phase 2 note says "a test derives the code list from
the engine's own constants so it cannot decay". It does not. A fifth code added to
`data_guard/contracts.py` and not added to the list in the test is never checked, and
`ownership.md` says exactly what happens then: the console renders "No reason was
recorded." **silently, with no error anywhere.** Spec 46 requires enumeration rather
than hand-listing for engine 7's codes; `data_guard` predates that rule and never got
it. The test can fail — it just cannot fail for the thing the standard was written
about.

**Mine, finding 2 — the database filename is checked against itself.**
`tests/cli/test_entrypoints.py` asserts `clients.store.db_path == paths.db /
DB_FILENAME`, with `DB_FILENAME` imported from the module under test. Both sides move
together, so the test cannot notice the constant drifting away from the layout
`architecture-context.md` documents as `db/  acsoe.sqlite`. Low severity — the daemon
and the console both import the constant, so they would still agree with each other —
but it is the shape, and it is one line to fix by pinning the documented literal in the
test.

**Fix.** The reason-code test now enumerates every `REASON_*` constant declared in
`data_guard/contracts.py` and asserts each is in `REASON_PROSE`, so adding a code
without prose is a red test rather than a silent blank in the console. The filename
assertion pins `"acsoe.sqlite"` as a literal with a comment naming the document it
comes from. Both mutated to confirm they now fail for the reason they exist.

**Also corrected: the progress-file claim.** It said the list was derived. It was not,
and the claim is exactly the kind that makes a later reader stop looking.

### The envelope's third refusal branch could be deleted and nothing noticed

**Agent:** A · **Task:** lead-assigned sweep · **Date:** 2026-09-10

**What happened.** Scanning my own paths for the weak-assertion shape — `pytest.raises`
on a type that many causes share, with no look at the message — turned up four in
`tests/clients/kraken/test_rest.py`. Chasing the first one found something worse than a
weak assertion. `parse_envelope` has **three** refusal branches, all raising
`KrakenUnavailableError`:

1. the body is not JSON at all;
2. the body is JSON but is not a Kraken envelope — no `error` key;
3. the body is an envelope with neither an `error` nor a `result`.

Branches 1 and 3 have tests. Branch 2 has none, and the test named for it —
`test_a_body_that_is_not_an_envelope_is_unavailable_not_a_success` — passes
`b"<html>maintenance</html>"`, which is not JSON, so it exercises branch **1**. The
name claims one branch, the input reaches another, and the shared exception type means
nothing about the failure distinguishes them.

Confirmed by deleting branch 2 outright:

```
mutated: parse_envelope no longer refuses valid JSON that is not an envelope
82 passed in 3.50s
```

**Why the branch is load-bearing rather than defensive.** With it gone, a body of
`{"result": {...}}` carrying **no `error` key at all** takes `errors = payload.get("error") or []`,
finds nothing to object to, finds a `result`, and is **returned as a clean success**.
The envelope rule exists precisely because Kraken signals application errors in that
array and not in the HTTP status, so a body that does not carry the array is one where
we cannot know whether it was a yes or a no — and invariant 3 says the absence of a
"no" is never a "yes". This is the one function in the package that decides whether a
response is a success, and a third of its refusal logic was unexercised.

**Fix.** A test that hands `parse_envelope` valid JSON carrying a `result` and no
`error`, and asserts it raises. Deleting the branch now fails it. The misleading test
is renamed to say which branch it actually covers — it is a good test of branch 1 and
was only ever mislabelled — and the two of them now name their branches, so the third
is visibly a third rather than a variation.

**The generalisation.** The weak-assertion rule found this, but not the way I expected:
the assertion being weak was the *symptom*, and the cause was that a shared exception
type let a test drift onto a neighbouring branch without anything objecting. Where
several branches raise one type, the message is not a nicety — it is the only thing
that says which branch ran.

### Sweep findings in the shared harness — reported to C, not edited

**Agent:** A · **Task:** lead-assigned sweep · **Date:** 2026-09-10

Three findings in `tests/conftest.py` and `tests/harness/`, which are C's. Recorded
here because the sweep is mine and the reasoning should not live only in a message.
They share one mechanism: **a fallback that fires silently when an import fails**, so
the failure mode is not a red test but a green suite that has quietly stopped testing.

**1. `tests/harness/fake_kraken.py` — the error classes fall back, and the test named
for catching that cannot.** The harness does `from acsoe.clients.kraken import
KrakenError, KrakenAPIError, KrakenUnavailableError` inside a `try`, and on `ImportError`
defines its own three classes. That was right in Phase 1, when the real ones did not
exist. `test_configured_transport_failure_raises_the_real_error_type` exists to prove
the fake raises *the real client's* type across the handover — and it imports
`KrakenError` **from the harness**, i.e. from whichever branch ran. Both sides move
together.

Simulated the fallback by blocking `acsoe.clients.kraken` at the import system and
importing the harness fresh — no repo file touched:

```
fallback active: tests.harness.fake_kraken.KrakenError
pytest.raises(KrakenUnavailableError) caught it : True
assert isinstance(caught.value, KrakenError)    : True
```

The test passes against the fallback. Today the real branch is live —
`fake_kraken.KrakenError is acsoe.clients.kraken.errors.KrakenError` is `True` — and
nothing anywhere asserts that. One line fixes it: `assert KrakenError is
RealKrakenError`, importing the real one directly.

**2. `tests/harness/doubles.py::migrated_store` returns `None` on
`ModuleNotFoundError`.** It is what `build_verify_doubles` uses to give
`scripts/verify.py` a store. If the store client ever fails to import, the doubles come
back with `store=None` and the criteria run against a client bundle with no store — the
exact `Clients()`-of-`None`s shape that made `Orchestrator._record_run` unexecutable for
a whole phase, and the criteria would still report PASS.

**3. `pytest.importorskip` in `tests/conftest.py` skips on `ModuleNotFoundError`
raised from *inside* the module.** Worth stating precisely, because the first half of
this is reassuring and the second is not. An `ImportError` from inside a module is
**re-raised** by pytest 9.1.1 — I checked, expecting the opposite — so a broken module
fails loudly. A `ModuleNotFoundError` from inside it, which is what a dependency moving
to an extra produces, is **skipped**. **370 test functions**, about a third of the
suite, depend on a fixture guarded that way (`store`, `seeded_db`, `seed_fixtures`,
`migrated_db`, `seed_clock`, `fake_clients_with_store`, `engine_context`,
`verify_module`). They would vanish, the suite would be green, and the skip reason
would read "the store client does not exist yet" — which would be false and would send
the reader in the wrong direction.

**What the three have in common, and it is not "imports".** Each was written when the
thing it falls back from genuinely did not exist yet, and each was correct then. None
has an assertion that the *real* branch is the live one, so none of them notices when
its own reason for existing has expired. **A fallback for a thing that does not exist
yet needs a test that fails once it does.** That is the same defect as a decayed
assertion, arriving from the opposite direction: not a claim that stopped being
checked, but a workaround that stopped being needed and stayed armed.

### Two more in `tests/conftest.py`, and one of them reintroduces the bug it was written to prevent

**Agent:** A · **Task:** lead-assigned sweep, second pass · **Date:** 2026-09-10

The lead cleared `seed_fixtures` empirically and nothing else in the file. Going
through the rest fixture by fixture found two more of the same family, both verified
rather than reasoned about.

**7. `seed_thresholds_from_config` swallows a *renamed* key exactly as it deliberately
swallows a present-and-null one — and that is the drift it exists to stop.** It reads
five `safety.*` values out of the committed config and injects them into
`SeedThresholds`, with `except KeyError: continue` around each. Its own docstring
recounts why it exists: the seed's default `max_errors_in_window` was 10 while the
operator had set 20, the seed overshot the wrong limit, and "a Phase 3 test of engine
17's error-rate input against it found the condition untripped and **failed pointing at
the engine**".

The docstring then draws a careful distinction — a key that is *present and null* is
left to default, because "the operator has not decided yet" must not become a number
this file invented. That is right. But `Config.get` raises `KeyError` for **absent** as
well, and `continue` cannot tell the two apart. Simulated a rename:

```
configured max_errors_in_window  : 20
after the rename                 : 10 (silently the seed's own default)
```

So renaming or removing a `safety.*` key puts the fixture straight back into the state
that produced the original defect, by a different door, with nothing raised and nothing
warned. The distinction the docstring makes is real and the code does not implement it:
absent and null need different handling, and only one of them is a legitimate default.

**8. `engine_context` skips silently if `EngineContext` is ever renamed, taking 44
tests with it.** It does `importorskip("acsoe.core.contracts")`, then
`getattr(contracts, "EngineContext", None)` and `pytest.skip` if that is `None`. Both
guards were correct when `core/contracts.py` did not exist. It does now. If the class
were renamed, every one of **44 test functions across 7 files** — `test_cost`,
`test_data_guard`, `test_exchange`, `test_market_data_recorder`, `test_market_sensor`,
`test_risk`, `test_scout`, i.e. every engine any of us has written — would report
skipped, and the suite would be green.

`paper_config` has the same shape and I am rating it lower rather than reporting it
flat: it skips when `config/default.yaml` is missing, which is 45 more test functions,
but a missing config file fails loudly elsewhere — `test_config.py` reads it with
`read_text()` and would raise `FileNotFoundError`. The skip would be noise beside a real
failure rather than silence.

**All five harness findings are one rule and I would state it this way:** a fallback for
a thing that does not exist *yet* has an expiry date, and nothing in the code records
it. `try: import real / except: define our own`, `getattr(mod, "Name", None)` then skip,
`except KeyError: continue` — each was correct when written and each is now a silent
branch that fires on a condition that should be impossible. **The fix is never to delete
the fallback; it is to add the assertion that the fallback is unreachable.** One line
saying "the real branch is the live one" converts a silent workaround into a tripwire
for the day someone breaks the thing it used to stand in for.

### My own mutation harness rewrote a file's line endings, and the guard I put in it half-worked

**Agent:** A · **Task:** branch-coverage pass · **Date:** 2026-09-10

**What happened.** The harness for the refusal-branch sweep applies one mutation,
runs a test subset, and restores the file. It read the file with `read_bytes()` and
wrote the mutated version with `write_text(..., encoding="utf-8")`. On the first
mutation it stopped with:

```
!! src/acsoe/clients/kraken/contracts.py changed on disk during the run - NOT restoring blindly
```

The file had not changed on disk. `write_text` opens in **text mode**, so Python
translated every `\n` to `\r\n` on the way out — 665 of them. The file I compared
against was byte-for-byte different from the file I had written, for a reason that had
nothing to do with anyone else editing it.

**Why the guard was there and why it was still not enough.** Three agents share one
working tree, so a harness that restores a saved copy can clobber another agent's save
if they wrote during its window. The check exists to refuse that. It fired correctly on
its own terms — what it saw genuinely did not match what it wrote — and then did the
one thing that made the situation worse: it exited **without restoring**, leaving
`contracts.py` carrying a live `pass  # MUTANT` in `_to_money` and a whole-file line
ending change. `git diff --stat` reported 665 insertions and 665 deletions on a file I
had never intended to edit.

**Fix.** `write_bytes` throughout, so nothing is translated and the comparison is
exact. And the restore is unconditional: the original bytes go back first, and the
"changed underneath me" case becomes a warning after the file is safe rather than a
reason to leave it broken. A safety check that can leave the tree in a worse state than
no check is not a safety check.

Restored with `git checkout` — the file was clean in HEAD and I had made no edit to it
this session, so nothing was lost. Verified afterwards: no `MUTANT` anywhere in `src/`,
0 CRLF and 665 LF in the file, and 100 tests green across `tests/clients/kraken` and
`tests/engines/test_exchange.py`.

**Worth recording rather than quietly repairing**, for two reasons. A tool written to
find defects introduced one, in the package whose whole job is talking to the exchange
— and it did it by touching a file that was not even a candidate for the sweep. And the
line-ending translation is invisible in every diff view that normalises whitespace: had
the tests passed, the mutation would have been reverted and the CRLF conversion would
have stayed, showing up later as an unexplained 665-line diff on a file nobody edited.
`.gitattributes` was already the subject of an earlier escalation for adjacent reasons.

**The general point.** `Path.write_text` is not the text-mode-free counterpart of
`read_bytes`, and pairing them is the mistake. Read bytes, write bytes; if you are
round-tripping a file you did not author, never let the platform reformat it in
between.
