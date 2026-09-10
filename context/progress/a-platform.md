# Progress — a-platform

Your file. Only you write here. The lead merges into `context/progress-tracker.md`.
Never edit the tracker directly.

## Current Task

**Phase 3. Claimed: specs 38 and 39**, in that order, per
`feature-specs/PHASE-3-TASKS.md` and ownership rule 5. Claimed 2026-09-10, before
any code was written.

**Spec 38 — COMPLETE, 2026-09-10.** **Spec 39 — COMPLETE, 2026-09-10.** Four commands
green for both; output pasted under Verification.

### Spec 39 — what landed

`src/acsoe/cli/engine.py` (`build_clients`, `start_stream`, `close_clients`),
`src/acsoe/engines/market_data_recorder/{contracts,engine,README}.py`,
`src/acsoe/clients/kraken/{ws,client,limiter}.py`, `src/acsoe/platform/paths.py`
(`DB_FILENAME`). New `tests/engines/test_subscription_scope.py` (11 tests), four new
tests in `tests/clients/kraken/test_ws.py`, one in `test_limiter.py`, three in
`tests/cli/test_entrypoints.py`.

1. **The subscription scope is derived per tick and lives in the stream, not the
   engine.** That is what makes "a failed `AssetPairs` leaves it unchanged" true by
   construction rather than by an engine keeping a copy of last tick's answer.
   `subscription_scope` returns `None` for "no basis to decide" and `()` for "nothing
   qualifies" — two different answers that must not be one value, because
   unsubscribing on a transient failure destroys order-book history that cannot be
   recovered.
2. **Moving the scope is a delta on the live socket**, never a reconnect: a
   `subscribe` for what arrived, an `unsubscribe` for what left, silence for what
   stayed, and nothing at all on a tick where it has not moved — which is the common
   case, since this runs every minute.
3. **No test hand-builds `state["exchange"]`.** Every test drives the real
   `ExchangeEngine` through the real `Orchestrator` against C's fake and varies the
   *fake*. The stream in those tests is the real `KrakenWebSocketClient`, constructed
   and never started, so the delta bookkeeping under test is the production one rather
   than a double that would agree with whatever engine 2 did.

**Three defects found by wiring the real thing up**, all in the build log:

- **`RateLimiter` could not be held across ticks.** It serialises with an
  `asyncio.Lock` while `platform/aio.py` gives every engine call a fresh event loop.
  Binds on contention, so it does not fire on the shipped budget at all and arms once
  a tick makes ~30 REST calls — engine 7 plus per-pair order books. Fixed: the lock is
  per running loop, the token state is not. Rebuilding the limiter per tick is not a
  fix; it hands every tick a full bucket and removes the rate limit.
- **Engine 2 became a gate by reading a config key that had not landed.** `Config.get`
  raises on a key that does not exist, the orchestrator turns that into ERROR, and
  ERROR blocks — so a missing optional key made the *recorder* the tick's primary
  blocker and displaced `data_guard`. **The general point: a half-landed config key is
  not uniformly safe because the reader raises. Whether raising is safe depends
  entirely on who is reading.** Spec 38's landing order fixes the window; it does not
  decide what happens inside it.
- **The orchestrator crashed on tick 1 with a real store** — duplicate `run_id` in
  `_log`. `core/` is the lead's; escalated, and the lead had found it independently
  and fixed it.

**And one of my own tripwires did not go off.**
`test_a_tick_over_the_real_registry_records_errors_rather_than_raising` was written in
Phase 2 to turn red when the real clients landed. It stayed green, because it builds
the empty `Clients()` itself instead of going through `cli/engine.py` — it pinned a
fact about a value the test supplies, not about the daemon. **A tripwire attached to a
local reproduction of the symptom cannot detect the cause.** Rewritten to keep the
property it actually tests, with the daemon's own construction asserted separately.

**One decision that deliberately departs from the spec 38 pattern.**
`trading.stable_quote_currencies` stays `frozenset[str] | None = None` rather than
being tightened to required now the YAML has landed. `cache_ttl_s` was tightened
because its reader raises on absence, so refusing at startup is strictly better. This
key's readers were *ruled to disagree*: engine 7 fails closed, engine 2 fails open and
publishes `crypto_quoted_excluded: false`. A required field overrules both — an absent
key would stop the process, so the recorder would never run, which is the irreversible
error the lead's ruling identifies for engine 2. **The landing order is universal; the
resting state is not.** Tighten when absence should stop the process; leave optional
when a reader has been ruled to keep working without it.

### Spec 38 — what landed, and the three things worth knowing

`src/acsoe/clients/kraken/rest.py`, `README.md`, `tests/clients/kraken/test_cache.py`
(new, 20 tests), and repairs to `test_rest.py` and `test_secrets.py`. 76 tests in
`tests/clients/kraken/`, up from 50.

1. **The cache and the retention are two mechanisms and the tests now meet at the
   point where they interact.** `test_retention_survives_the_expiry_that_blocked_trading`
   is the pairing spec 38 asks for as one test: the TTL expires, the re-fetch fails,
   the call raises rather than returning the expired snapshot, and
   `last_known_good_asset_pairs` still holds that same snapshot with its original
   `fetched_at`. The fee is the mirror image — cached, never retained — so after its
   own expiry and failure there is nowhere in the client holding a fee at all.
2. **Every cache assertion is on the transport, never on the returned value.** A
   `CountingTransport` records one entry per request. The cache hands back the very
   object a fetch would have produced, so equality and identity checks pass against a
   client with no cache in it; only the request count can tell.
3. **The two TTLs are proved independent in both directions.** Parametrised over
   `(asset_pairs=60, trade_volume=300)` and the reverse, with the clock parked at 90
   seconds between them. A single shared TTL has to pick a number and whichever it
   picks it fails one of the two orders. Verified by mutation, not by inspection:
   forcing `self._trade_volume_ttl_s = asset_pairs_ttl_s` kills 11 tests, and making
   `_fresh` never expire kills 18.

**Two defects found on the way that were not the reported failures.** Both are in
the build log in full:

- `test_a_private_call_without_credentials_blocks_rather_than_defaulting` was
  **green and testing nothing**. It built a client with neither credentials nor
  TTLs, so `_require_ttl` raised `KrakenUnavailableError` about
  `cache_ttl_s.trade_volume` before the credential check it exists to exercise ever
  ran. Same exception type, so `pytest.raises` could not notice. It now supplies both
  TTLs and asserts on the message. **General point for everyone: every fail-closed
  path in `clients/kraken/` raises that one type on purpose, which makes
  `pytest.raises(KrakenUnavailableError)` on its own a weak assertion in this
  package.**
- **The two config keys the lead pasted were unreachable from `src/`.** Nothing
  outside `rest.py` and the tests named either TTL, so wiring the daemon up as it
  stood would have made every `asset_pairs()` and `trade_volume()` call raise about a
  missing TTL with the value sitting in `config/default.yaml`.
  `KrakenRestClient.from_config` is the fix and is what spec 39 builds through.

### HANDOFF TO THE LEAD — spec 38 step 1, done, the YAML is now safe to paste

*Kept for the record. Both halves landed on 2026-09-10 and the follow-up below was
taken: `cache_ttl_s` is now required.*

**`kraken.cache_ttl_s` exists on the config model.** `CacheTtlConfig` is declared in
`src/acsoe/platform/config.py` and `KrakenConfig.cache_ttl_s` points at it, so the
`extra="forbid"` refusal that reverted the lead's 2026-09-10 attempt is gone. The
block in `feature-specs/37-phase-3-rulings-into-the-documents.md`'s appendix —
`cache_ttl_s.asset_pairs: 300`, `cache_ttl_s.trade_volume: 60` — can be pasted
under `kraken:` and will parse.

**One deliberate difference from the obvious reading, and the lead should know it
before pasting.** The field is declared `CacheTtlConfig | None = None`, not
required. It had to be: the committed `config/default.yaml` does not carry the key
yet, and a required field would have made `load_config()` raise on the shipped
file — the same failure the lead hit, mirrored, taking `paper_config`,
`scripts/verify.py` and every test that reads the committed config with it. Spec 38
step 1 says in as many words *"you can test with a fabricated config until the YAML
lands"*, which is only possible if the shipped file still loads.

Nothing is defaulted. `None` is not a value: `Config.get("kraken.cache_ttl_s.…")`
raises `ConfigKeyError` on it, and `KrakenRestClient` raises
`KrakenUnavailableError` naming the missing key rather than caching for a guessed
interval. Absence fails closed at the point of use, exactly as
`data_guard.max_data_age_s` did before the operator supplied it.

**Recommended follow-up, one line, the lead's call:** once the YAML is in, change
`cache_ttl_s: CacheTtlConfig | None = None` to `cache_ttl_s: CacheTtlConfig` so a
later removal refuses at startup instead of blocking at read.
`test_the_committed_config_and_the_cache_ttl_handoff` in
`tests/platform/test_config.py` asserts both worlds and stays green across the
paste — it asserts the raising behaviour while the key is absent and asserts
`300`/`60` as positive ints the moment it is present.

### Phase 2 (closed, kept for the record)

**Phase 2. Claimed: specs 25, 26, 27, 28, 29, 30**, in that order, per
`feature-specs/PHASE-2-TASKS.md` and ownership rule 5.

- **Spec 25 — Kraken REST and WebSocket clients: COMPLETE.**
- **Spec 26 — engine 1 `exchange`: COMPLETE**, pending only the lead's `bootstrap.py`
  registration, which is batched with 27 to 29 by instruction.
- **Spec 27 — engine 2 `market_data_recorder`: CODE COMPLETE, SPEC NOT COMPLETE.** The
  committed fixture `tests/fixtures/recording_report.json` is outstanding and is
  blocked on wall-clock time, not on code. Detail below. **Do not treat 27 as done.**
- **Spec 28 - engine 3 `market_sensor`: COMPLETE.** `candles_match_kraken_ohlc` now
  reports PASS.
- **Spec 30 - historical OHLCVT loader: COMPLETE.** `historical_loader_reports_gaps`
  now reports PASS.
- **Spec 29 - engine 4 `data_guard`: CODE COMPLETE.** `data_guard_blocks_bad_data`
  reports PENDING naming `data_guard.max_data_age_s`, which the operator has not
  supplied. Nothing else about it is outstanding.

Phase 0 (below) is closed and green; it is kept for the record.

**Claimed in Phase 0: specs 03, 07, 08, 09, 10.** All five Phase 0 tasks for Agent A. All five
are finished. Nothing of mine is outstanding.

This session was a follow-up, not a new spec: the operator supplied the nine OPERATOR REQUIRED
values, three of my tests asserted the committed config refuses to load, and those assertions
had to move rather than be deleted. Done, and Phase 0 now reports 7 PASS / 0 FAIL / 0 PENDING.

## Completed

- **Spec 03 — package skeleton and `pyproject.toml`.** src layout, the stack table's
  dependencies and nothing else, `dev` and `research` extras, mypy `--strict` and the ruff
  rule set the standards imply, the package tree, and the `acsoe` console script.
- **Spec 07 — `platform/config.py`.** Pydantic model over every key in `config/default.yaml`,
  `yaml.safe_load` only, `Decimal` for money, and the refusals: every null OPERATOR REQUIRED
  key named together, `mode: live` refused naming invariant 1 and Phase 8, a poll interval
  above a quarter of the stale threshold refused, `starting_balances` required to be a
  currency map. The only module in the system that reads an environment variable.
- **Spec 08 — clock, logging, directory creation.** `SystemClock`/`FixedClock`, structlog JSON
  with daily rotation, two-layer redaction (recursive key-name redaction plus registered-value
  scrubbing of the rendered line), `run_id`/`cycle_id` binding, and idempotent creation of
  `data/{raw,historical,derived,db}` and `logs/`.
- **Spec 10 — `scripts/record.py` and `tests/fixtures/record_sample.jsonl`.** Standalone
  Kraken WebSocket v2 to JSONL recorder with no dependency on the engine framework, gap
  markers on reconnect, and a committed redacted 25-line sample that `record_sample_valid`
  reports PASS on.
- **Spec 09 — the three CLI entry points.**
  - `acsoe engine` builds config, clock, logging, clients and the orchestrator, then runs the
    tick loop at `timeframes.loop_tick_s`. The loop is mine; the tick is the lead's. A stop is
    checked **between** ticks only, so an interrupt never lands inside a half-run manage chain.
  - `acsoe console` loads the same config, prepares logging and the runtime directories, asks
    C's `acsoe.console.app.create_app` for the application and serves it on `console.port`.
  - `acsoe research` assembles `OFFLINE_CHAIN` in `cli/research.py` — never in `bootstrap.py` —
    reports that no offline engines are registered, and exits zero.
  - `tests/cli/test_entrypoints.py`, now 24 tests.
- **Follow-up — the operator's nine values.** The refusal tests moved off the committed file
  and onto a fabricated one; the committed file gained the opposite assertions. Detail below.

## The operator's nine values — what changed on my side

The operator supplied all nine previously-null OPERATOR REQUIRED keys, so `config/default.yaml`
carries zero nulls. Three of my tests asserted that file **refuses to load** and went red. That
was my design working: I duplicated the key list into `tests/cli/test_entrypoints.py` on purpose
so a change to the set would fail loudly rather than be silently inherited. It fired in the
direction I had not anticipated — the config becoming *more* valid, not a tenth key appearing.

**Nothing was deleted and no refusal machinery was weakened.** `platform/config.py` is unchanged
except for two docstrings that still claimed the shipped file carries nine nulls.
`_refuse_nulls` counts what it finds and never held a list of key names, which is why a config
with zero nulls needed no code change at all.

Three properties are now asserted separately, because they were previously conflated into one:

1. **A null OPERATOR REQUIRED key stops the process, by name.** Against a config the test
   fabricates — `unset_operator_config` (CLI) and `with_nulled()` (platform) — built by taking
   the shipped file and setting the nine back to `null`. Nine parametrised single-key cases
   proving one unset key is enough on its own and that the message names *that* key and no
   other, plus the all-nine-at-once message, plus both entry points refusing with exit code 2.
   `safety.error_rate_window_s` must still never appear in a refusal: it is specified as the
   trailing hour by `architecture-context.md` and was never the operator's to supply.
2. **A null anywhere stops the process.** `test_a_null_anywhere_is_refused` was already there
   and now carries more weight: it is what keeps the machinery honest with zero nulls shipped.
3. **The committed file is known-good.** It loads with no overlay and no fill-in, `mode` is
   `paper`, `acsoe engine --config config/default.yaml --ticks 1` completes a tick and exits
   zero, `acsoe console` accepts it, and each of the nine parses to the expected type — Decimal
   for money and rates, int for counts and durations, and `paper.starting_balances` as a
   currency-to-Decimal map whose `USD` still reads exactly `5000.00`. That last one is asserted
   twice on purpose: once on the raw YAML (the value is a *string*, so it never touches binary
   float) and once on the parsed Decimal (`str()` still shows the cents). The parsed value alone
   cannot tell you which route it took, because `Decimal("5000.0") == Decimal("5000.00")`.

One replacement was needed for a signal that would otherwise have been lost. While the nine were
null, the shipped config refusing to load *was* the tenth-key alarm. With zero nulls, the lead
could add a tenth key **and supply it** and nothing would notice.
`test_the_file_marks_exactly_these_nine_keys_as_the_operator_s` scans `config/default.yaml` for
its `Operator-chosen` marker and compares the set to the tests' own list. The marker is a
documented convention — the file's own header states it — not an inference from formatting. The
opposite case still needs no marker: a tenth key added as `null` survives the overlay in
`complete_config_dict()` / `startable_config` and takes every test using those fixtures down.

**I have not touched the operator's values and will not.** The tracker records both consequences
the lead checked by arithmetic — nothing clears the cost gate at tier 1 at `hurdle_multiple: 1.5`
with a 3.0% target, and `max_concurrent_positions: 3` is inert at a $5,000 balance where one
position is ~$3,333 notional. Neither is a defect and neither is mine. The loader-mechanics tests
deliberately use their own values (`starting_balances: {USD: "1000.00"}`) rather than the
operator's, so that revising a provisional trading number in Phase 3 does not churn a test about
YAML parsing. Assertions about the shipped numbers live in the `test_default_yaml_*` tests and
nowhere else.

## Phase 2 — spec 25, what was built

`src/acsoe/clients/kraken/` is now the system's only route to the exchange.
`contracts.py` landed first and was messaged to B and C the same session, so neither
waited on the implementation.

- **`contracts.py`** — `PairRule`, `PairRulesSnapshot`, `FeeTierSnapshot`,
  `BalancesSnapshot`, `OrderBookSnapshot`, `RetainedValue`, `RawFrame`, `TradeTick`,
  `QuoteTick`, and the `KrakenClientProtocol` / `MarketStreamProtocol` Protocols. Field
  names match `tests/harness/fake_kraken.py` exactly, so the fake and the real client
  are interchangeable and no consumer has to know which it has.
- **`errors.py`** — `KrakenError` / `KrakenAPIError(message, errors)` /
  `KrakenUnavailableError(message, cause)`, re-exported from the package. C's harness
  now takes its real-import branch; its fallback definitions are dead code.
- **`limiter.py`** — token bucket, injected clock and sleep, **no default budget**.
- **`rest.py`** — the envelope, the four `map_*` functions, retention, signing.
- **`ws.py`** — buffered v2 stream on its own thread, gaps marked never healed.
- **`client.py`** — the `KrakenClient` facade `context.clients.kraken` holds.
- **`README.md`** — the envelope rule, what is fetched at runtime, what is retained
  and why the other two deliberately are not.
- **`platform/config.py`** gained `Credentials` and `load_credentials()`. It stays the
  only module in the system that reads an environment variable, and `Credentials`
  renders as a constant from both `__repr__` and `__str__`.

50 tests in `tests/clients/kraken/`.

### Three things I want the next reader to notice

1. **The envelope is tested as a pair, not as one assertion.** A 200 with a populated
   `error` array raises, **and** a 200 with an empty one parses cleanly and yields its
   `result`. A parser that raised on everything satisfies the first perfectly and is
   useless; discrimination is the only property the envelope has and one assertion
   cannot demonstrate it.
2. **The client applies no fallback, deliberately.** `map_trade_volume` raises on a
   missing fee field and never assumes a tier. Invariant 2's paper-mode fallbacks are
   decisions made by the *consumer*, which must record which one fired, and a client
   that quietly supplied one would make that record impossible.
3. **Absent is structurally distinct from zero.** `OrderBookSnapshot` cannot be
   constructed with an empty side, so "no book" arrives as an exception rather than as
   a zero spread. A *crossed* book is reported faithfully — `spread` may be negative —
   because engine 4 has to see it.

## Phase 2 — spec 26, what was built

`src/acsoe/engines/exchange/` — `engine.py`, `contracts.py`, `README.md`,
`__init__.py`. 17 tests in `tests/engines/test_exchange.py`. Plus
`src/acsoe/platform/aio.py`, the one place a synchronous engine runs an async client
call.

**The decision worth reading is that engine 1 never blocks, not even when all three
fetches fail.** It is the one a later reader is most likely to "correct", so the
reasoning is in the module docstring and the README as well as here: a block would be
a fifth gate nobody registered; engine 1 runs first, so it would set
`state["trading_blocked_by"] = "exchange"` and mask the real blocker on the same tick,
making `block_records.is_primary` wrong as well; and because a `data_guard` block is
what makes the manage chain hold exits, a block here would give engine 1 a say in
whether an open position gets managed. Every gate that needs a value it did not get
blocks on its own — invariant 3 — so reporting the absence honestly is enough.

Three other things:

- **The three calls run concurrently with `return_exceptions=True`**, so one outage
  does not become three blanks. A consumer has to know exactly which value it is
  missing, because invariant 2's paper fallback differs per value.
- **No fallback is applied here, at all.** `fee_tier` is `null` when `TradeVolume`
  failed and is never "assume tier 1". Supplying one would erase the record invariant 2
  requires the consumer to keep, and would be a hardcoded fee besides.
- **`retained` publishes ages, never values.** For trading a stale value does not
  exist; only rule 14 may use one, and engines 21 and 22 read it from the client in
  Phase 6. A test asserts no `ordermin` and no balance string appears anywhere in the
  published `retained` payload.

An exception that is *not* exchange-shaped is re-raised rather than recorded — contract
rule 7 — and there is a test for that too.

## Phase 2 — spec 27, what was built and what is outstanding

Built and green: `src/acsoe/clients/recorder/` (`contracts.py`, `writer.py`,
`report.py`), `src/acsoe/engines/market_data_recorder/`, and
`scripts/recording_report.py`. 26 tests in `tests/clients/recorder/`, 13 in
`tests/engines/test_market_data_recorder.py`.

**Outstanding: `tests/fixtures/recording_report.json`.** The real archive holds
**21h24m** — `2026-09-08T16:01:22Z` to `2026-09-09T13:25:41Z` — with a ~10-hour hole
between 09-08T16:02 and 09-09T02:04 where no recorder was running. C's criterion needs
24 hours. The span crosses 24h at about **2026-09-09T16:01Z** provided
`scripts/record.py` keeps running.

**A report built from this archive now would be truthful and would still FAIL**, which
is worse than the PENDING the criterion reports. PENDING means "the subject does not
exist yet", which is true; FAIL would mean "it exists and is wrong", which is not.
`scripts/recording_report.py` refuses to write a digest under `--min-hours` (default
24) so the refusal is mechanical rather than remembered, and there is deliberately no
flag that fabricates a span. Regenerating it later is one command.

Two other things worth carrying forward:

- **The digest reports a tiling, not a gap count.** Segments and gaps together account
  for every microsecond in the span. A gap count can be right while a break sits
  unaccounted for between two segments nobody compared; a tiling has nowhere for that
  to hide, and it forces *unrecorded silence* — what an absent recorder leaves behind,
  writing no marker precisely because it was not there — to be a first-class gap.
- **Two `record.py` processes ran concurrently from 13:19 on 09-09.** The lead
  established both started at the same second, so the archive is single-recorded up to
  13:19 and doubled after. That discontinuity is worse for spec 28 than a uniform 2x
  would be, because a uniform factor is obvious and a mid-file step looks like a market
  event. De-duplication belongs in the **derived** layer: invariant 11 keeps the
  recording immutable, so the candle builder has to be idempotent over duplicates and
  correct **across the boundary**, not tuned to the doubled section.

## Phase 2 - spec 28, what was built

`src/acsoe/engines/market_sensor/` - `engine.py`, `contracts.py`, `candles.py`,
`README.md` - plus `scripts/ohlc_fixture.py` and the committed
`tests/fixtures/kraken/ohlc.json`. 20 tests in `tests/engines/test_market_sensor.py`.

- **`bar_closed` is `(now // bar) != ((now - tick) // bar)`**, not `now % bar == 0`.
  `context.now` carries microseconds off a real clock, so an exact-boundary test would
  essentially never fire. The index comparison is stateless - which it has to be, since
  `state` is fresh every tick - fires exactly once per bar, and still fires **once**
  when the loop ran late or skipped a tick.
- **A missing candle is reported and never invented**, and the tests assert the absence
  separately from the gap report: no candle carries a timestamp that had no trade. A
  forward-filled series would pass any check that only counted gaps.
- **The in-progress bar is never published** as a candle. That is look-ahead, invariant
  10.
- **The trade window lives in the client, not the engine.** `recent_trades()` returns a
  rolling window without draining it, because engine 3 rebuilds the same bar on each of
  the fifteen ticks it spans and an engine may not carry state across cycles.
- **`spread_pct` is `(ask - bid) / mid`** and may be negative; a pair with no quote is
  absent rather than present with a zero spread.

## Phase 2 - spec 30, what was built

`src/acsoe/research/historical.py` and 25 tests in `tests/research/test_historical.py`.

- **`gap_count` counts runs, not missing bars.** Three holes of 1, 2 and 4 bars are
  three gaps and seven missing bars; reporting seven is the signature of a loader that
  lost the distinction, which is what the criterion's differently-sized holes catch.
- **Nothing is ever invented, and the tests assert that separately from the gap count.**
  A loader that counts gaps correctly *and* emits filled rows passes every gap
  assertion and still hands Phase 4 candles at prices that never traded. There is no
  parameter that fills a hole and the module contains no fill, resample or interpolate
  call - asserted on the AST, because the docstring says the word deliberately.
- **Money never passes through a numeric parser.** The CSV is read with `csv.reader`
  and the money columns become `Decimal` in Python before polars sees them.
- **The report is a frozen pydantic model**, so the 'every value it emits is
  re-validated' property that makes the mypy compromise tolerable holds for this
  module too. **The dataframe itself stays unvalidated** - stated in the build log
  rather than implied.
- **Parquet is written only when `derived_dir` is given**, so merely reading an archive
  has no side effect on disk. A phase criterion calls this.
- No archive exists in `data/historical/` on this machine, so the `--live` half and the
  committed digest wait on the operator downloading one. No criterion depends on it.

## Phase 2 - spec 29, what was built

`src/acsoe/engines/data_guard/` - `engine.py`, `contracts.py`, `README.md`. 21 tests in
`tests/engines/test_data_guard.py`, plus 7 in `tests/engines/test_guard_chain_rehearsal.py`.

- **Six tests carry it: a block and a pass for each of the three named conditions.**
  Each bad scenario differs from `clean` in exactly one respect, asserted by its own
  test - a fixture that was stale *and* crossed would let a gate that only checked
  staleness pass the negative-spread case.
- **A fourth reason code, `no_market_data`**, for the fail-closed case invariant 3
  requires. Not folded into `market_data_stale` because the prose would be a false
  sentence: there is a difference between a feed that is behind and no feed at all.
  Agreed with C before landing, and a test derives the code list from the engine's own
  constants so it cannot decay.
- **Blocking on a hole in the candle series does not contradict the loader refusing to
  invent one.** The loader governs labelling, the gate governs trading, and fail-closed
  points the opposite way in each. Stated in three places because the obvious fix for
  either half breaks the other.
- **`data_guard.max_data_age_s` raises when absent** and no placeholder is written.
- The 'a second guard still runs on a blocked tick' test drives the **real**
  `Orchestrator` rather than asserting it about the engine in isolation: an engine
  cannot prove a property of the chain it sits in.

## In Progress

- **Nothing.** All six specs are code complete.

## Blocked On

- **Spec 27's fixture: a clean 24-hour recording, running now.** Operator ruling
  2026-09-09: do **not** deposit on the old archive. It was 49% recorded and contained a
  disk outage we caused ourselves, which is contaminated evidence for the phase whose
  subject is the data spine.

  ```
  clean run session start : 2026-09-09T14:15:29.997349Z
  24 hours complete at    : 2026-09-10T14:15:30Z
  disk when started       : 165G free, 83% used
  ```

  **The next session runs one command** once that moment has passed:

  ```
  .venv/Scripts/python.exe scripts/recording_report.py --write
  .venv/Scripts/python.exe scripts/verify.py --phase 2
  ```

  `recording_report.py` **refuses to write below 24 hours** and prints the numbers
  instead, so it cannot be run too early by accident. Check first that exactly one
  recorder is alive — and note that Windows lists it as a **parent and a child with
  identical command lines**, which is one recorder, not two. That confusion cost an hour
  today; see the correction entry in the build log.

  If the recorder died in the meantime, the span is broken and the 24 hours restarts.
  `python scripts/recording_report.py` with no `--write` prints every gap and its cause,
  which is how to tell.
- **Spec 29's criterion: the operator's `data_guard.max_data_age_s`.** PENDING, not
  FAIL, and correctly so.
- **Nothing else.** `bootstrap.py` registration **landed**: the lead registered engines
  1 to 4 after C repointed `orchestrator_empty_registry`, and `console_shows_live_rows`
  is now PASS - "a tick of exchange, market_data_recorder, market_sensor, data_guard
  wrote rows under the daemon's own run_id". The rehearsal held; registration was a
  formality.

  It did take two of my own tests with it, both decayed the same way C's criterion was:
  `test_an_empty_registry_produces_a_valid_tick` and
  `test_the_offline_chain_is_not_in_bootstrap` asserted things true only while the
  registry was empty. Both repointed. Detail in the build log.

## Known gap I own but have not closed

**CLOSED 2026-09-10 by spec 39.** Kept below for the record, and it is worth reading
against what actually happened, because the note was wrong in two ways.

It was wrong about the **blocker**: it says the gap is blocked on `market_data.pairs`
and `market_data.book_depth`, and offers two ways forward that both assume those keys
ought to exist. The operator ruled that neither key exists — the universe is computed
per tick, a Locked Decision — so the subscription set is *derived* in engine 2 from
`state["exchange"]`, and the book depth is the recorder's own parameter. I leaned to
"refuse to start without the keys", which would have been the wrong answer to a
question that turned out not to be a question. Recorded rather than deleted: the
reasoning was sound given what I believed, and what was missing was a ruling, not an
argument.

It was also wrong about the **tripwire**.
`test_a_tick_over_the_real_registry_records_errors_rather_than_raising` did not turn
red when the real clients landed, because it constructs the empty `Clients()` itself
instead of going through `cli/engine.py`. See the build log.

- **`cli/engine.py` still passes a `Clients()` of three `None`s**, so `acsoe engine` now
  blocks every tick: engine 1 raises on `None.asset_pairs` and engine 4 on its missing
  config key, both converted to `ERROR`. The tick **completes** and records both, which
  is contract rule 7 working - the daemon does nothing useful rather than dying.

  Blocked on `market_data.pairs` and `market_data.book_depth`, which do not exist. REST
  and the recorder can be wired without them; the WebSocket stream cannot subscribe
  without a pair list, and I will not invent one. Two ways forward, and the lead has
  both: wire what is possible and leave the stream unstarted (engines 2 and 3 then
  report `stream_available: false` and `data_guard` blocks, which is fail-closed), or
  have `acsoe engine` refuse to start without the keys, which matches how the config
  layer treats every other missing value. I lean to the second.

  **The current behaviour is asserted rather than left implicit** -
  `test_a_tick_over_the_real_registry_records_errors_rather_than_raising` pins it, so
  wiring the real clients turns that test red and forces a deliberate rewrite. No
  criterion depends on it: every Phase 2 criterion runs the orchestrator against C's
  fake client, not through the CLI.

## Open Questions

Unresolved requirements go here and that unit of work stops. Never guess at trading behaviour.

- **The signing scheme and the four `map_*` field names in `rest.py` are unverified
  against the live exchange, and cannot be verified offline.** `AGENTS.md` says any
  remembered endpoint shape is stale; the operator has rotated the key; the committed
  fixtures are C's simplified harness shape, not recorded responses. Both are isolated
  into single named functions so correcting them is a small edit, and a renamed field
  surfaces as a `KrakenUnavailableError` naming the field rather than as a default.
  Confirmed by `--live` when a key exists. **Blocks nothing** — every Phase 2 criterion
  runs offline.
- **Invariant 2's paper-mode fee fallback is unimplementable as written.** "Assume tier
  1, the worst tier" requires tier 1's rates, which are exchange-supplied, and the same
  rule forbids hardcoding a fee anywhere. Raised with the lead, who has taken it to the
  operator. Not mine to resolve — it is engine 10's surface — and my client deliberately
  does not paper over it. The lead asked whether `AssetPairs` carries a public fee
  schedule that would dissolve the contradiction: **it does not.**
  `tests/fixtures/kraken/asset_pairs.json` carries exactly `base`, `quote`, `ordermin`,
  `costmin`, `tick_size`, `lot_decimals`, `pair_decimals` for all four pairs, and no fee
  field of any kind. Reported to the lead.

## Escalations To Lead

Anything touching `core/`, `bootstrap.py`, the engine registry, an invariant, a dependency, or another agent's schema.

- **Nothing outstanding.** The `Config` Protocol mismatch and `.gitattributes`, both raised in
  earlier sessions, are closed.
- **Two prose corrections outside my lane, flagged not edited.** Both are stale in the same way
  my two docstrings were, and both are harmless — the code around them behaves correctly:
  - `tests/conftest.py` (C), the `paper_config` fixture docstring: "Its OPERATOR REQUIRED nulls
    are left as nulls." There are none left.
  - `scripts/verify.py` (C), around the `KEY_MAX_*` constants: "Three of them are written as
    null and marked OPERATOR REQUIRED." All three now carry values, which is why
    `seed_fixtures_present` has stopped reporting PENDING. `required_thresholds()` itself is
    correct and needs no change — it distinguishes absent from null and would go back to PENDING
    if a value were withdrawn.

## Notes for other agents

- **For C:** the two docstrings above, and one thing worth knowing before Phase 1's console
  work. A test that asserts a *refusal* from a function whose success path starts a server needs
  `uvicorn.run` stubbed anyway. While my `test_console_refuses_the_committed_config` was red it
  did not merely fail — it fell through into `uvicorn.run` and bound 127.0.0.1:8765 from inside
  the suite (`SystemExit: 3`, `[Errno 10048]`). The refusal was the only thing between the test
  and a real socket. `asgi_get` in `tests/cli/test_entrypoints.py` is the driver to copy: it
  runs a request through the real ASGI app with no httpx and no socket, so C's network guard
  never has to be relaxed for it.
- **For B:** `clients/store/seed.py` carries its own fixture-shape constants for keys that used
  to be OPERATOR REQUIRED, commented as such. Now that the config has real values, worth
  deciding whether the seed should read them or deliberately keep its own — the seed's numbers
  must stay independent of a provisional trading value that Phase 3 will revise, or every
  fixture moves when the operator retunes one number. Not mine to change; flagging the choice.

## Escalations To Lead — Phase 2

- **Config keys.** Requested six. Four approved and awaiting my model sections
  (`kraken.rest_capacity`, `kraken.rest_refill_per_s`, `kraken.rest_timeout_s`,
  `market_sensor.published_bars`). Two held as trading behaviour and put to the
  operator: **`data_guard.max_data_age_s`** and **`kraken.cache_ttl_s`**. The second is
  the more serious of the two: invariant 2 says "a cache stale beyond its TTL counts as
  a failed fetch" and rule 14 says a liquidation may use a value "past its TTL", and
  **no TTL exists anywhere in `config/default.yaml`** — so both sentences currently have
  no *its*.
- **`bootstrap.py` registration for engines 1 to 4** — will be sent as one batch, and
  deliberately not before all four survive two real orchestrator ticks against the fake
  client. C's `console_shows_live_rows` criterion turns from PENDING to a FAIL naming
  the exception if a registered engine raises during a tick.

## Verification

Paste the real output of your last run. Never report a task complete without it.

### Phase 3, specs 38 and 39 complete (2026-09-10)

```
$ .venv/Scripts/python.exe -m pytest tests/ -q
1198 passed in 95.13s

$ .venv/Scripts/python.exe -m mypy --strict src/
Success: no issues found in 68 source files

$ .venv/Scripts/python.exe -m ruff check src/
All checks passed!

$ .venv/Scripts/python.exe scripts/verify.py --phase 3
ACSOE verify - phase 3
repo: C:\Users\saad2\Documents\GitHub\ACSOE

PASS    docs_vocabulary                                       14 files scanned, 10 retired terms, no hit
PASS    toolchain_green                                       pytest, mypy --strict and ruff all green (python.exe)
PASS    cost_gate_uses_live_fee_tier                          BTC/USD: net edge 0.0075 at maker/taker 0.0005/0.0010 and 0.0020 at 0.0025/0.0045, moving by exactly the 0.0055 fee difference; the cheap tier clears the hurdle and the expensive tier is blocked
PASS    risk_rejects_sub_ordermin                             BTC/USD: sized 5.97481259, then refused at an `ordermin` of 5.97481260 - one lot increment (1E-8) above it - with reason 'below_ordermin' and no quantity returned
PENDING universe_varies_with_balance                          engine 7 `scout` does not exist yet (spec 43 and 44) ...
PASS    safety_freezes_on_drawdown_without_opportunity_chain   the seeded drawdown froze the system on a tick with an empty opportunity chain ...
PASS    safety_escalates_on_sustained_outage                   counted from the seeded block_records: 15 consecutive blocked tick(s) does not trip the outage and writes no `close_all`; 16 trips it and writes one ...
PASS    safety_inputs_all_from_the_seed                       all six inputs match the seeded tables ... and none of them moved when state was poisoned with an engine 19 payload
PENDING phase_3_gates_have_both_tests                         no test file yet for engine 7 `scout` (tests/engines/test_scout.py, spec 43 and 44) ...

9 criteria: 7 PASS, 0 FAIL, 2 PENDING
Phase 3 is not green: 2 PENDING. Mid-phase the bar is no FAIL, so this is expected.
```

Both PENDING are engine 7 `scout`, which is B's specs 43 and 44. Nothing of mine is
outstanding in the gate.

**On reading a FAIL while three agents are working in one tree.** Several runs while I
was finishing spec 39 reported `FAIL toolchain_green` naming a *different* pair of
tests each time, always under `tests/verify/` or `tests/engines/test_safety.py`. One
run also had `mypy` and `ruff` fail tree-wide on a syntax error in
`engines/safety/contracts.py` — a docstring caught mid-save without its opening quotes.
None of it was mine and none of it was the machine's intermittent fault: it is what a
shared working tree looks like while B and C are saving files. The tell is that the
named tests move between runs and all sit in another agent's paths, where the
intermittent fault produces a *stable* wrong verdict on one test. My own paths were
green throughout: 565 passed over `tests/cli`, `tests/clients`, `tests/platform`,
`tests/research` and my `tests/engines/` files, with `ruff` clean over my `src/`
directories. **Judge by path first, and only then consider re-running.**

`ruff check` is clean over `tests/cli`, `tests/clients`, `tests/platform` and
`tests/engines/test_guard_chain_rehearsal.py`; the standard's four commands cover
`src/` only, so I run it over my own test paths separately. Two lint errors remain in
`tests/` that are not mine and I have not touched: `UP031` in
`tests/core/test_contracts.py` (lead) and `F401` in `tests/engines/test_risk.py` (B).
Both reported.

**Note for the record: at the time spec 38 was reported, `verify.py --phase 3` printed
"Phase 3 is green" over two criteria** — `docs_vocabulary` and `toolchain_green` — and
that was the empty-phase problem C's spec 45 exists to fix rather than a statement
about spec 38. Spec 45 has since landed and the gate now has nine criteria and reports
honestly. Spec 38's own evidence is the 76 tests in `tests/clients/kraken/` and the two
mutation runs recorded in the build log.

### Phase 2, after spec 29 (2026-09-09)

```
$ .venv/Scripts/python.exe -m pytest tests/ -q
1060 passed in 45.19s

$ .venv/Scripts/python.exe -m mypy --strict src/
Success: no issues found in 68 source files

$ .venv/Scripts/python.exe -m ruff check src/
All checks passed!

$ .venv/Scripts/python.exe scripts/verify.py --phase 2
PASS    docs_vocabulary                 14 files scanned, 9 retired terms, no hit
PASS    toolchain_green                 pytest, mypy --strict and ruff all green (python.exe)
PASS    commands_round_trip             real StoreClient through the real reader: ...
PENDING recording_span_continuous       tests/fixtures/recording_report.json does not exist yet (spec 27) ...
PASS    candles_match_kraken_ohlc       3 pairs, 9 bar(s): every OHLC field within one tick_size as AssetPairs reports it, volume within 0.1%
PENDING data_guard_blocks_bad_data      engine 4 needs the config key `data_guard.max_data_age_s`, which config/default.yaml does not carry ...
PASS    historical_loader_reports_gaps  3 gaps of 1/2/4 bars reported exactly, over 41 rows, and no timestamp in the output was absent from the input
PENDING console_shows_live_rows         no Phase 2 engine is registered in bootstrap.py yet (specs 26-29) ...
PASS    console_reads_persisted_mode    a real daemon applied activate then freeze through the real store ...

9 criteria: 6 PASS, 0 FAIL, 3 PENDING
Phase 2 is not green: 3 PENDING. Mid-phase the bar is no FAIL, so this is expected.
```

Three PENDING, and none of them is code of mine that is missing:

1. `recording_span_continuous` - wall-clock time. See Blocked On.
2. `data_guard_blocks_bad_data` - the operator's `data_guard.max_data_age_s`.
3. `console_shows_live_rows` - `bootstrap.py` registration, which is the lead's and is
   held until C repoints `orchestrator_empty_registry` at a `Chains()` the criterion
   controls rather than at the live `bootstrap.GUARD_CHAIN`. My rehearsal is what found
   that: registering the four engines would have taken **Phase 0** red, because that
   criterion's body asserts no guard blocked while its name claims to be testing an
   empty registry, and those only coincide while nothing is registered.

### Phase 0 close, kept for the record

```
$ .venv/Scripts/python.exe -m pytest tests/ -q
430 passed in 8.75s

$ .venv/Scripts/python.exe -m mypy --strict src/
Success: no issues found in 29 source files

$ .venv/Scripts/python.exe -m ruff check src/
All checks passed!

$ .venv/Scripts/python.exe scripts/verify.py --phase 0
ACSOE verify - phase 0
repo: C:\Users\saad2\Documents\GitHub\ACSOE

PASS    docs_vocabulary              14 files scanned, 9 retired terms, no hit
PASS    orchestrator_empty_registry  one tick completed against 0 registered engines; empty chains are valid, state["system"]["mode"]='idle'
PASS    db_migrates_from_empty       fresh database migrated to all 9 documented tables
PASS    seed_fixtures_present        all six fixtures present: outage run 18 ticks over 2 run_ids (11 double-blocker), 2 open position(s), 2 resting order(s), drawdown 0.2000017843760037115020877199, losing streak 8, 23 ERROR blocks in the window, 33 trades / 46 rejections
PASS    record_sample_valid          25 lines valid against the recorder schema; kinds present: gap, session, tick
PASS    toolchain_green              pytest, mypy --strict and ruff all green (python.exe)
PASS    is_gate_matches_registry     0 engines registered; 0 mismatches

7 criteria: 7 PASS, 0 FAIL, 0 PENDING
Phase 0 is green: every criterion PASS, zero PENDING.
```

Phase 0 is green. `seed_fixtures_present` was the last PENDING and cleared on its own when the
operator supplied `safety.max_drawdown_pct` and the other two breaker limits — B's seed was
correct all along and was blocked on a value, not a bug.

`ruff check tests/cli tests/platform` is also clean; the standard's four commands cover `src/`
only, so I run it over my own test paths separately.

## Notes For Next Session

- Phase 2 is my next heavy phase: engines 1 `exchange`, 2 `market_data_recorder`,
  3 `market_sensor`, 4 `data_guard`, the historical OHLCVT loader, and `clients/kraken/`.
- `scripts/record.py` should be left running from now on. Order-book and spread history cannot
  be recovered retroactively, and Phase 2's `recording_report.json` criterion needs a
  continuous span of at least 24 hours.
- `Clients` in `cli/engine.py` carries three `None`s in Phase 0 because no engine is
  registered. Wiring B's store client into it is Phase 2 work, not a Phase 0 omission.
- If the operator withdraws a provisional value back to `null`, nothing in `platform/` needs
  editing — that is the point of the machinery. What *will* fail is
  `test_default_yaml_loads_cleanly` and the type-parsing cases, which is correct: the file would
  no longer be known-good. The refusal tests would keep passing throughout.
