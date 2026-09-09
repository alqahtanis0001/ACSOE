# Progress — a-platform

Your file. Only you write here. The lead merges into `context/progress-tracker.md`.
Never edit the tracker directly.

## Current Task

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
- **Spec 29 `data_guard`: next.** Deliberately sequenced last - landing it before C's
  criterion fixes would have turned a PENDING into a FAIL, and a FAIL is a stop.

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

## In Progress

- **Spec 29 `data_guard`, last.** C has fixed `_guard_context` and made an unset
  `data_guard.max_data_age_s` report PENDING naming the key rather than FAIL, so
  landing engine 4 no longer turns a PENDING into a FAIL.
- Spec 27's fixture stays outstanding until the recording span reaches 24 hours. At
  13:52Z the span was 21h51m; crossover is about 16:01Z.

## Blocked On

- Nothing. Two config keys are with the operator (below) and neither blocks: I will
  reference them with `config.get(...)` and let the `KeyError` stand until they land,
  which is the correct fail-closed behaviour and is testable as such.

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
