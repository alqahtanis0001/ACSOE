# Agent B — Store and trading

## Claimed

- **Spec 11** — `db/migrations/`, SQLite schema and forward-only migration runner. *Complete.*
- **Spec 12** — `src/acsoe/clients/store/`, store client and contracts. *Complete.*
- **Spec 13** — `src/acsoe/clients/store/seed.py`, seed generator. *Complete.*
- **Spec 31** — persisted system mode: `db/migrations/0002_persisted_system_mode.sql`,
  `clients/store/{client,contracts}.py`, `tests/db/`, `tests/clients/store/`. *Complete,
  green on all three phase gates.*

- **Spec 34** — engine 10 `cost`. *Complete, committed at `3581e87`. Superseded by spec 40.*
- **Spec 35** — engine 11 `risk`. *Complete, committed at `5b0dd2b`. Superseded by spec 41.*
- **Spec 36** — engine 17 `safety`. *Complete and green, committed at `5b0dd2b`. Its one
  open question is closed by spec 42 — see below.*

### Phase 3 — claimed 2026-09-10

- **Spec 40** — wire engine 10 `cost` to the real `state["exchange"]`.
  `src/acsoe/engines/cost/{contracts,engine}.py`, `README.md`, `tests/engines/test_cost.py`.
  ***Complete, all four gates green 2026-09-10.*** Fixtures rewritten, not repointed: every
  `state["exchange"]` in `test_cost.py` is `ExchangeEngine().process(...).data` verbatim,
  from A's real engine 1 against C's `FakeKrakenClient`, and a source-reading test refuses
  any of engine 1's payload keys written as a dict-key literal in that file.
  `test_cost.py:376` deleted, not edited; reason in the build log.
- **Spec 41** — wire engine 11 `risk`, give it a price, and **build** the paper-mode balance
  fallback. `src/acsoe/engines/risk/{contracts,engine}.py`, `README.md`,
  `tests/engines/test_risk.py`. ***Complete, all four gates green 2026-09-10.*** Pair rules
  re-pointed to `exchange.pair_rules.pairs`; the price now comes from
  `market_sensor.quotes[pair]` — **ask** sizes the quantity, **bid** values it for `costmin`,
  per the lead's ruling. The balance fallback is built as new behaviour: paper falls back and
  records `balance_from_paper_starting_balances`, live and replay block. Every `state` in
  `test_risk.py` is engines 1 and 3's real output against C's fake client. **One open item for
  the lead — see below.**

#### For the lead — `replay` mode's balance fallback is my reading, not a ruling

Spec 41 names paper (fall back) and live (block). `EngineContext.mode` has a third value,
`replay`, and the spec does not mention it. I implemented `if context.mode != "paper"` —
so replay blocks — because invariant 2's table is headed *paper mode*, invariant 3 says a
gate that is unsure refuses, and "not paper" cannot silently extend the fallback to a mode
added later the way "is live" would.

**The cost is real and deferred, not absent.** If replay is later meant to reproduce paper
faithfully, a replayed tick will block where the paper run fell back, and the two diverge
exactly where invariant 10's faithful-replay property should hold. Nothing in Phase 3
exercises replay. One line and one constant to reverse; full reasoning in the build log.
- **Spec 42** — apply the ratified `CONDITION_ACTION` and prove `safety` in a real guard
  chain. `src/acsoe/engines/safety/{contracts,engine}.py`, `README.md`,
  `tests/engines/test_safety.py`, `tests/engines/test_safety_guard_chain.py`.
  ***Complete, all four gates green 2026-09-10.*** The ruled table is applied — **it was
  not, despite the note below saying it was; see the build log.** `ESCALATING_CONDITION`
  names the one condition that may reach `close_all` and a test enumerates the table
  against it. 46 tests in `test_safety.py` and 5 in the new guard-chain file, which drives
  the real `Orchestrator` over engines 1, 2, 3, 4, 17 against a real `StoreClient` on an
  empty database and on the seed.

### Phase 3 wave 2 — claimed 2026-09-10

- **Spec 43** — engine 7 `scout`, the tradable universe. `src/acsoe/engines/scout/`
  (`engine.py`, `contracts.py`, `README.md`), `tests/engines/test_scout.py`.
  ***Complete, all four gates green 2026-09-10, and `--phase 3` is 9 PASS / 0 FAIL /
  0 PENDING.*** 24 tests. Nine exclusion codes, each rule proved to be the *only* thing
  excluding its pair; the tick-grid rule made to fire and its boundary pinned as strict;
  counts asserted to add up including on a tick where four rules fire at once; the sizing
  cross-checked against the real engine 11 over a table straddling `ordermin` by one lot
  increment each way. Four mutations run and each caught by the test written for it.
  **One escalation to the lead — see below.**
- **Spec 44** — engine 7 `scout`, the candidate and the gate. `src/acsoe/engines/scout/`,
  `tests/engines/test_scout.py`. ***Complete, all four gates green 2026-09-10, and
  `--phase 3` is 9 PASS / 0 FAIL / 0 PENDING.*** 44 tests. One candidate under
  `state["scout"]["pair"]`, absent and never null when there is none; empty universe is
  `PASS` and not `BLOCK`; the handoff run as one tick through the real engines 10 and 11.
  Ordering is alphabetical, isolated as `rank_universe` in `contracts.py`.

### Phase 4 — claimed 2026-09-11

- **Spec 51** — the store surface engine 19 `memory` and the cycle feed need.
  `src/acsoe/clients/store/client.py`, `src/acsoe/clients/store/__init__.py`,
  `tests/clients/store/test_store.py`. *Claimed, in progress.* Three parts: a bounded
  most-recent-N read for `block_records` ordered by `ts`; an audit of every write and
  read engine 19 needs against what `StoreClient` already has; and a `peak_equity`
  read that does not walk the whole equity series. **No schema change, no migration,
  no edit to `console/` or to any `safety` read path.** ***Complete 2026-09-11.***
  Three methods, 14 tests, eight mutations run and all eight red — including the one
  spec 51 names by hand. `pytest tests/ -q` clean in my lane; `mypy --strict src/` and
  `ruff check src/` green.

#### Spec 51 — what landed, and the one thing that is C's to finish

Three methods on `StoreClient`, all handed to C by `SendMessage` the moment they
existed rather than at the end of the task:

- `recent_block_records(limit: int) -> tuple[BlockRecordRow, ...]` — most recent
  `limit` **rows**, `ORDER BY ts DESC, id DESC`, no default limit.
- `recent_blocked_ticks(limit: int) -> tuple[BlockRecordRow, ...]` — most recent
  `limit` **ticks**, one row each, primary blocker preferred, lowest `id` on the tick
  as the fallback. This is the one the cycle feed wants; a rows-limited read can cut a
  tick in half and render it as blocked by the wrong engine. Reasoned out in the build
  log and proved by mutation M8 against the real Phase 0 seed.
- `peak_equity(self) -> Decimal | None` — spec 51 item 3 and spec 50's running maximum.
  **`SELECT MAX(peak_equity)` is the wrong query**: money is an exact decimal string,
  SQLite compares it lexicographically, and `'9.50' > '10000.00'`. A too-small peak is
  a too-small drawdown and a breaker that sits quiet through the loss it exists to
  stop. Build log entry, and a test that asserts the wrong query is actually wrong on
  its own fixture before asserting the right answer.

**Audited and found sound, nothing added:** all six writes engine 19 needs already
exist — `write_block_record`, `write_equity_snapshot`, `write_position`, `write_order`,
`write_trade`, `write_rejection` — as do `count_open_positions` and
`latest_equity_snapshot`. Specs 49 and 50 need no new write surface.

**Still open, and it is C's:** `console/reader.py:453` `_blocked_ticks` still calls
`block_records_in_window(start_ts=_TS_MIN, end_ts=_TS_MAX)` and builds a row model for
every record in the table. Spec 51 says hand C the method name and stop, so I have.
Spec 51's "the cycle feed no longer performs an unbounded scan" is not satisfied until
C makes that one-line swap to `recent_blocked_ticks(self._feed_limit)`.

- **Manage-chain rehearsal for engine 19** — `tests/engines/test_manage_chain_rehearsal.py`,
  new file, my lane. *Claimed 2026-09-11, in progress.* Lead task, and the deliberate
  exception to "nobody writes a test for another agent's code": the rehearsal tests the
  **orchestrator wiring**, which is the lead's, not engine 19, which is C's. Held before
  registration, the same way A's guard-chain rehearsal was held before engines 7, 10, 11
  and 17 were registered. Two real ticks, not one. **If it goes red for a real reason I do
  not fix engine 19** — report to the lead and to C.
  ***Complete and green 2026-09-11. Ten tests, all passing — nothing to report about
  engine 19.*** It records a `data_guard` block with the manage chain still running on a
  blocked tick, writes no row on a clean tick while still reporting per-table counts
  including zeros, reports Phase 6 publishers absent rather than zero, and its second tick
  is genuinely its own. `ux_equity_snapshots_tick` has now been *seen* to fire: two
  orchestrators sharing a `run_id` collide on `cycle_id` 1, contract rule 7 turns the
  `IntegrityError` into ERROR, the tick completes and the first row survives. Six
  mutations, five killed, one equivalent and recorded as such. **N5 is the one that
  justifies the file**: with `cycle_id` cached on `self`, a single-tick rehearsal passes
  and five two-tick assertions fail — the two-tick rule measured rather than asserted.

  **One defect of my own, in the harness rather than the tests.** It restored mutated
  files only at the end of the run, so a mutation of `core/orchestrator.py` was still on
  disk while `engines/memory/engine.py` was mutated, and that verdict was really both
  together. Compounded mutants fail more tests, so every verdict drifts toward KILLED and
  a real survivor can hide. It very nearly cost the rehearsal its central claim — I would
  have written that a one-tick rehearsal catches N5, on a check that was measuring
  something else. Both files verified byte-identical by sha256 afterwards; neither is
  tracked by git, so `git checkout` was never a safety net and the verify step is the only
  reason this was recoverable.

#### Phase 3 branch-coverage backlog — `discover_migrations` closed 2026-09-11

Backlog item, not phase-gate work, picked up after spec 51. `tests/db/test_migrations.py`,
my lane. **The backlog said three survivors; the function has five refusal branches plus a
sixth path, and two survived wide — not three.** The count was overstated in one direction
and understated in the other, which is a better argument for re-checking wide than the
handoff's own. The item itself lives in `feature-specs/PHASE-3-TASKS.md` and in neither
the consolidated build log nor the tracker — the lead has since carried the whole backlog
into the tracker's open items.

Genuine survivors, now tested: **duplicate migration version** (unrefused, the second file
silently overwrites the first in a dict keyed on version and the set still looks
contiguous) and **no migration files in the directory** (unrefused, returns `()`, which
passes the contiguity check trivially and reports success over a database with no tables).

**The finding I was not sent to make, and it is the one worth keeping.** Two further
branches — directory-not-found and the non-`.sql` skip — are killed *only* by tests in
other agents' files that are not about migrations: a Phase 4 engine test that happens to
build a store over a missing path, and a research import-boundary test that happens to walk
this directory. They read as covered in any sweep and are covered by nobody. **An
incidental kill is worse than a survivor, because a survivor is at least on a list.** Both
now have tests next to the code they are about. All six branches are killed by
`tests/db/test_migrations.py` itself; every assertion is on the message and not the bare
type, because all five refusals raise `MigrationError`.

Sweep excluded `tests/scripts/`, which was red in A's lane at the time; the harness refuses
to report at all unless its baseline is green, because a sweep over a red tree marks every
mutation killed and manufactures a clean result out of someone else's broken tree. Shape of
that hole recorded in the build log.

#### For C — the ORDER BY anchor in `test_phase3_criteria.py` is single-occurrence by convention only

My first cut of `recent_blocked_ticks` reached for the same literal
`ORDER BY ts DESC, run_id DESC, cycle_id DESC` the outage walk uses, and
`test_an_outage_counted_by_cycle_id_is_a_fail` correctly refused: *anchor appears 2
times, expected exactly once*. Fixed in my lane — the feed query now tie-breaks
`cycle_id` before `run_id` — with a comment at the site saying not to tidy the two into
one wording. **C's count assertion is the only reason this surfaced at all**: a patcher
taking the first match would have mutated my new query, left the outage counter intact,
watched the Phase 3 criterion stay PASS, and reported a can-it-fail proof that had
itself stopped being able to fail. Worth knowing the anchor is textual and that the
next query in that file can collide with it again.

#### OPEN QUESTION for the tracker — engine 7 has no ranking score, and that is recorded

**Ruled by the operator on 2026-09-10 and not a defect**, but it belongs in
`context/progress-tracker.md`, which is the lead's, so it is raised here.

Invariant 4 describes engine 7's ranking as "a deterministic score over features". There
are no features in Phase 3, so **the ordering is the tie-break alone: pair name,
ascending**. The operator's reasoning: a placeholder score would be a check whose output
resembles the claim while the claim is untrue, and ranking one candidate out of a filtered
set is a Phase 5 decision made with real features in front of us.

**Phase 5 closes it.** It is isolated as one named function, `rank_universe` in
`scout/contracts.py`, so the fix is one edit against a named seam. `engines/scout/README.md`
says in as many words that alphabetical ordering is a recorded absence rather than a design,
so nobody reads it as a choice someone defended.

#### For the lead — the affordability check compares two currencies

`target_notional` derives from equity, which invariant 7 expresses in
`trading.base_reporting_currency`; the balance it is compared against is in the pair's
**quote** currency. Comparing them needs an FX rate and nothing in this system publishes
one, though invariant 7 says one is converted "at the trade timestamp".

**Engine 11 has carried the identical comparison since spec 35** and no test has ever
reached it on a pair whose quote is not the reporting currency, because no fixture has one
that gets that far. Found by writing the third caller, not by anything failing.

I ask the comparison only when the currencies match, with the reason at the call site. I
did **not** invent a rate, assume parity, or mint a "cannot be converted" exclusion — the
last would be inventing trading behaviour under cover of caution, and the ruling on A's
crypto-quoted heuristic is the precedent. The residue: a non-reporting-currency pair can
enter the universe without being shown affordable, which is the *over*-including direction
and the wrong one for `scout`. Unreachable today, reachable the moment
`allow_crypto_quoted` is enabled — and my own crypto-quoted test flips exactly that flag.

### Phase 5 — claimed 2026-09-13

- **Spec 62** — the store surface for model artefacts. `src/acsoe/clients/store/client.py`,
  `tests/clients/store/test_store.py`. ***COMPLETE, all four gates green 2026-09-13*** — see
  Gates below for the run. `StoreClient(db_path, *, models_dir=None)` gains `models_dir`,
  `model_run_dir(run_id)` and `new_model_run_dir(run_id)`, the last refusing an existing
  directory because a trained artefact is never overwritten. Plus the audit of
  `write_leaderboard_entry` and `leaderboard()` against what spec 74 needs, which found one
  gap. **No schema change, no migration, no artefact parsing** — the store hands back a path
  and C's `modelling/artefacts.py` decides what is in it. 11 mutations, all 11 killed.
  Committed by the lead at `16c5685`.
- **Spec 76** — engine 7 `scout`, ranking by a config-named feature. `src/acsoe/engines/scout/`
  (`contracts.py`, `engine.py`, `README.md`), `tests/engines/test_scout.py`. ***COMPLETE, all
  four gates green 2026-09-13*** — see Gates below. 16 new tests, **60 in the file and none
  skipped**: the no-double seam test went from skipped to passing with no edit the moment C
  landed engine 5, which is the point of having written it that way. 13 mutations run and all
  13 killed by tests in this file, including the four spec 76 names by hand.
  `scout.rank_feature` is **absent** in the committed config, so the ordering is alphabetical
  today and the engine publishes `rank_feature: null`; the mechanism is built and waits on the
  operator's ruling from C's spec 75 study. Committed by the lead at `16c5685`.

#### Spec 76 — a third refusal, found by C and not by any of my thirteen mutations

**2026-09-13, after both specs were marked complete.** Spec 76 names two ways of being unable
to rank and I built both; there is a third and I missed it. **`scout.rank_feature` naming a
feature that does not exist** found no value for any pair, the no-value rule then ordered every
pair alphabetically among themselves, and the engine published the misspelt name beside a
ranking it never performed. No exception, no null, and a candidate that is a real pair from the
real universe — the silent fallback my own README forbids in general terms, left open in its
commonest instance. Demonstrated against the real function before a line was written:
`feature='volatilty_24h'` returned exactly `tuple(sorted(pairs))`.

The per-pair question — does *this pair* have a value — and the whole-universe question — does
this *feature* exist — are different, and `_feature_value` returning `None` was answering both.
The empty feature name is the same defect at length zero and was refused from the start.

`_features` now reads `feature_names` from `state["feature"]`, a required field of C's
`FeatureState`, and blocks when the configured name is not among them. Three new tests, three
new mutations, all three killed. **N14, which deletes the check, is killed by the new test and
by nothing else** — which is the honest measure of how invisible this was: thirteen mutations
had already passed over it, because a mutation can only ask about behaviour somebody thought of.

**Found by C-2 reviewing the seam while writing spec 60's criterion for it**, and relayed. That
is a consumer reasoning about a producer, and it is the one review this project keeps proving
no amount of self-testing replaces.

#### COMPLETE 2026-09-13 — engines 6 and 12 rehearsed in the same file

Same file, now **14 tests**, extended on the lead's request of 10:10. Engines 5, 6, 7 and 12
through the real orchestrator in registry order, two real ticks, nothing staged.

**The answer to the question the request asked:** yes, `state["scout"]` gates engine 12. It
reads `state["scout"]["pair"]` and returns `PASS` with an empty payload when there is none, so
a 5-6-12 chain reaches it and it declines to classify on every tick. Rather than fabricate a
scout payload — forbidden by the request and a hand-built `state` besides — the chain carries
**the real engine 7**, which sits between 6 and 12 in the registry and is mine. Engine 12 then
classifies the pair engine 7 actually chose. Both cases are asserted: the no-candidate `PASS`
and the full chain.

**Four more mutations, four killed**, hashes verified before and after the sweep:

| # | Mutation | Killed by |
|---|---|---|
| S1 | engine 6 reports `available` with a macro pair missing | the missing-asset test |
| S2 | engine 6 drops the `missing` list | the same test |
| S3 | engine 12 classifies with no candidate | the no-candidate test |
| S4 | the orchestrator does not stop the chain on a `PASS` | the cadence test |

**S4 is the mutation only a multi-engine rehearsal can ask.** While engine 5 was the only
registered engine, "it returns `PASS` and the chain stops there" had no observable consequence
and no test could see it. With three engines behind it, deleting the orchestrator's `PASS`
check turns the cadence test red.

**Nothing to report against engine 6 or engine 12**, and one finding against my own fixture:
engine 7 first found no candidate, `{'insufficient_quote_balance': 3, 'no_live_quote': 1}`,
because the fake account held no spendable USD. Not a defect — at the committed 1% risk
fraction and 1.5% stop, $5,000 of equity sizes a $3,333 position. Diagnosed in one line from
engine 7's own exclusion tally.

**Two naming facts, and they are one fact twice.** The committed feature fixture is `SOLUSD`,
the archive *filename* spelling; a stream and `AssetPairs` both say `SOL/USD`. Streaming under
the archive spelling builds a universe engine 7 cannot match, and the rehearsal would then pass
with an empty universe for a reason unrelated to wiring. The lead's `BTC/USD` versus `XBTUSD`
ruling is the same distinction from the other side.

#### COMPLETE 2026-09-13 — the two-tick orchestrator rehearsal of engine 5

`tests/engines/test_feature_chain_rehearsal.py`, **8 tests, all passing**, and the phase gate
is green on the run that includes it: `pytest tests/ -q` **2167 passed, 2 skipped**;
`mypy --strict src/ scripts/` **115 source files**; `ruff check src/ tests/ scripts/` clean;
`scripts/verify.py --phase 5` **2 PASS, 0 FAIL, 0 PENDING**. That last line reads "Phase 5 is
green" and **must not be believed**: only two criteria are registered, because C-2's spec 60
has not landed. A phase with fifteen engines' worth of real code in it cannot be green on
`docs_vocabulary` and `toolchain_green` alone, and spec 60 exists to stop exactly that reading.

**What it drives.** Engine 5 alone in the opportunity chain, engine 3 in the guard chain, two
real `Orchestrator.tick()` calls sixty seconds apart, over real prices: the trade stream is
rebuilt from `tests/fixtures/candles_sample.parquet` so engine 3 produces the archive's own
candles. The system reaches `running` through an `activate` **command row**, the way the
console does, rather than by setting `state["system"]` — which is the one region of `state` the
contract reserves for the orchestrator, and setting it by hand would prove nothing about
whether the opportunity chain is reachable at all.

**Four mutations, four killed**, each restored from a byte copy and verified by sha256 in the
same statement (ruling 10; both files also hashed before and after the whole sweep and
unchanged):

| # | Mutation | Killed by |
|---|---|---|
| R1 | engine 5 ignores `bar_closed` | the bar/quiet-tick test **and** the status test |
| R2 | engine 5 returns `OK` instead of `PASS` on a non-bar tick | the status test |
| R3 | the orchestrator runs the opportunity chain on a blocked tick | the guard-block test |
| R4 | the orchestrator runs the opportunity chain while `idle` | the idle test |

**R1 is the reason this file earned its place, and it went the wrong way first.** On the first
sweep R1 was killed *only* by the status test — not by the test written for it, whose assertion
was `quiet_tick["feature"] == {}`. With the guard removed, engine 5 runs on the quiet tick and
raises on the absent `closed_bar_ts`, and contract rule 7 turns that into `ERROR` with
`data={}`: **a quiet tick and a crashed tick publish the identical payload.** The assertion
was true for a reason unrelated to what it claimed. Fixed by also asserting
`"trading_blocked_by" not in quiet_tick`; R1 then died on the test written for it, with
`AssertionError: engine 5 did not pass, it failed`. The verdict alone said KILLED both times —
the finding was entirely in *which* test killed it.

**Nothing to report against engine 5 itself.** It behaved correctly on every tick: `PASS` with
an empty payload off a bar, a feature row for every pair on a bar, a different `bar_ts` on a
second bar tick an hour later, and a JSON-safe payload whose every value is a float or null and
never NaN. Its refusal message when `closed_bar_ts` is absent is unusually good and is quoted
in the build log.

#### CLAIMED 2026-09-13 — the two-tick orchestrator rehearsal of engine 5

The lead's offer of 02:35 in `feature-specs/PHASE-5-TASKS.md`: engine 5 alone, `PASS` on a
non-bar tick and a feature row on a bar tick, through the real orchestrator against the fake
client. **A-2 was given the same offer, so this note is the claim** — ownership rule 5, and the
only way to avoid two agents writing one rehearsal file when we cannot message each other.
`tests/engines/test_feature_chain_rehearsal.py`, a new file in my lane, following
`test_manage_chain_rehearsal.py` from Phase 4 and A's `test_guard_chain_rehearsal.py`.

Reading and driving another agent's engine through the real orchestrator is allowed; **editing
it is not.** If it goes red for a real reason I report it to the lead and to C-2 rather than fix
it.

#### Spec 76 — what landed

- `rank_universe(pairs, *, features, feature, descending)` and `select_candidate` with the same
  keywords, in `engines/scout/contracts.py`. One feature, one direction, one tie-break — pair
  name ascending, in **both** directions, which is why the key negates the value instead of
  sorting in reverse. A pair with no value sorts after every pair with one, alphabetically
  among themselves, and is never dropped.
- **NaN is a third way of having no value**, alongside null and absent. Spec 76 names two; the
  third arrives from `modelling/features.py`'s unfilled lookbacks. NaN compares false against
  everything including itself, so one left in a sort key orders *unpredictably* rather than
  badly — a direct hit on the determinism invariant 4 protects in this engine. Decision and
  reasoning in the build log; C told by message, so it no longer matters whether engine 5
  publishes null or NaN across `state`.
- The engine reads `scout.rank_feature` and `scout.rank_descending` through `context.config`
  and `state["feature"]["pairs"]` through named constants with C's ownership beside them.
  **Absent and null are deliberately the same fact for `rank_feature`** and the call site says
  why — the general rule in `code-standards.md` is that they are not, and this is the exception
  rather than an oversight. An empty or whitespace feature name is refused.
- **A configured feature with no engine 5 output blocks** with `scout_inputs_unavailable`.
  Falling back to alphabetical would publish `rank_feature: "<name>"` on a tick that ranked by
  nothing, and would be right on most ticks by coincidence — the placeholder score the operator
  refused, arriving through a fallback instead of a formula.
- `state["scout"]` gains `rank_feature` and `rank_descending`. `rank_feature` is **null rather
  than omitted**, the opposite of `pair`, because null is the answer here: it says the ordering
  was alphabetical for want of a key, which is exactly what spec 75's alphabetical control
  needs to be distinguishable from a feature that rated everything equal.
- `pairs` stays in scan order and still carries no ranking. One expression of the ordering, not
  two, so a consumer reading `pairs[0]` instead of `pair` cannot silently disagree.
- `README.md`'s recorded-absence section is rewritten as history, with the ruling dates and the
  reason the "rank if you can, otherwise alphabetical" reading is forbidden.

#### Spec 62 — what landed, and the audit it asked for

`StoreClient(db_path, models_dir=None)`, `models_dir`, `model_run_dir(run_id)` and
`new_model_run_dir(run_id)`. The run id is validated **before any path is built** — empty,
whitespace-padded, `.`/`..`, separator-bearing, drive-bearing and null-byte ids each refused
with their own message, because `StoreError` has one type and this surface now has six causes.
`new_model_run_dir` refuses an existing directory through `mkdir(exist_ok=False)` itself rather
than a prior `exists()` check, so two trainers racing for one run id cannot both be told it is
free. **A trained artefact is never overwritten** is the whole safety property of the method.

**The audit found one gap and it is now `leaderboard_entries(model_id=, model_version=,
fold=)`.** Every field spec 74 names already existed in `LeaderboardRow` and the 0001 schema
and nothing needed adding — asserted, not claimed, in
`test_a_leaderboard_row_round_trips_every_field_engine_20_writes`. What was missing was any way
to *read* one back: `leaderboard(limit=50)` is the console's truncating window, and deciding
"have I written this fold already" from it is spec 51's rows-versus-ticks defect a second time.
`fold IS ?` and never `fold = ?`, because SQL equality against NULL matches nothing and the
no-fold row would be rewritten on every run.

**For the lead, a schema question I did not act on:** nothing in the database enforces what
spec 74 calls idempotent — there is no unique index on `(model_id, model_version, fold)`, and
adding one is a schema change spec 62 forbids this phase. A partial index would be needed for
the null-fold row, the same shape as `ux_block_records_primary`.

**Eleven mutations in total, all eleven killed by the test written for each.** Eight against
the surface as I built it, then three more against the reader/writer asymmetry once it landed —
including both halves of it, so the ruling is pinned from both sides rather than merely
implemented. That matters because two methods disagreeing about one condition is the shape
somebody tidies into one path later, and the tidy direction is the one that creates the root.

#### Gates, run 2026-09-13, and what is red is not mine

**My own lane is green.** `tests/clients/store/test_store.py` and `tests/engines/test_scout.py`
together: **151 passed, 1 skipped** — the skip is the engine 5 seam test, which names
`acsoe.engines.feature.engine` and starts running the day C lands it rather than staying
quietly skipped. `ruff check src/acsoe/engines/scout/ tests/engines/test_scout.py
tests/clients/store/ src/acsoe/clients/store/` clean. `mypy --strict
src/acsoe/engines/scout/ src/acsoe/clients/store/` clean, 10 files.

**The whole-tree gates, last run at the end of my session.** They moved twice while I worked,
because A and C are saving into the same checkout, so both readings are recorded rather than
only the flattering one.

- `pytest tests/ -q` — **2100 passed, 3 skipped.** Green. An earlier run had six failures in
  `tests/cli/`, `tests/modelling/`, `tests/research/` and `tests/verify/`; every one was A's
  spec 61 or C's specs 60 and 63 mid-save, and every one cleared without anybody touching my
  paths.
- `mypy --strict src/ scripts/` — clean at **106 source files** when I checked it, then red
  again on `src/acsoe/cli/research.py:216: Name "Callable" is not defined`, which is A
  mid-save. Earlier in the session the same command reported `numpy/__init__.pyi:737: Type
  statement is only supported in Python 3.12` and then **stopped checking anything at all** —
  no answer rather than a wrong one, triggered by C's `modelling/di.py` importing
  `numpy.typing` past A's `follow_imports = "skip"` override. Fixed by its owners after I
  reported it; recorded because it is the failure mode that gate's own comment warns about.
- `ruff check src/ tests/ scripts/` — two findings, neither mine: `RUF100` in C's
  `scripts/verify.py` and `F821` in A's `cli/research.py`. Mine are clean.
- `python scripts/verify.py --phase 5` — **1 PASS, 1 FAIL, 0 PENDING.** `docs_vocabulary`
  PASS; `toolchain_green` FAIL on A's `cli/research.py`. It registers only **2 criteria**
  because C's spec 60 criteria are not landed yet, so this number will grow.

**My own paths are green throughout all of it**: `tests/clients/store/`, `tests/db/` and
`tests/engines/test_scout.py` together are **283 passed, 1 skipped**, with `ruff` and
`mypy --strict` clean over `clients/store/` and `engines/scout/`. The skip is the engine 5 seam
test, which names `acsoe.engines.feature.engine` and begins running the day C lands it.

#### The four gates, final run, and both specs are complete on it

Run after A-2's `follow_imports_for_stubs` fix and after C-2 cleared the `RUF100`, which were
the two things standing in the way. **This is the run both specs are marked complete on.**

```
$ .venv/Scripts/python.exe -m pytest tests/ -q
2102 passed, 3 skipped in 200.05s

$ .venv/Scripts/python.exe -m mypy --strict src/ scripts/
Success: no issues found in 106 source files

$ .venv/Scripts/python.exe -m ruff check src/ tests/ scripts/
All checks passed!

$ .venv/Scripts/python.exe scripts/verify.py --phase 5
PASS    docs_vocabulary  14 files scanned, 12 retired terms, no hit
FAIL    toolchain_green  ruff exit 1: src\acsoe\engines\feature\engine.py:123:12:
                         SIM300 [*] Yoda condition detected | Found 1 error.
2 criteria: 1 PASS, 1 FAIL, 0 PENDING
```

**The three gates I run directly are green. The `verify` FAIL is not mine and did not exist
when I ran `ruff` four minutes earlier**: C-2 landed `src/acsoe/engines/feature/engine.py`
between the two commands and it carries one `SIM300`. That is C-2's lane and C-2's line, and it
is the whole of the difference between the third gate passing and the fourth failing.

`tests/engines/test_scout.py` is now **60 passed, nothing skipped** — engine 5 landing turned
the no-double seam test live with no edit from me, and it passes against C-2's real engine.

#### Closed since: the M2 and M8 re-run the lead asked for

Done before the ruling arrived, and recorded in the build log: M2b, M8b and M9b against the
current `_artefact_root`, all three killed, each by the test written for it — including both
of the asymmetry's own tests, so the reader/writer split is pinned from both sides rather than
merely implemented. That is **11 mutations against spec 62 and 13 against spec 76, 24 of 24
killed, none by an incidental test in another file.** The stopped original's own six-mutation
run against the same code agrees with mine on every overlapping verdict; mine is the one to
rely on, because a survivor list from a session that is ending should not be load-bearing.

#### The CRLF claim is wrong, and the check that matters was run instead

The lead asked me to fix the mechanism behind `git diff`'s CRLF warning on
`tests/clients/store/test_store.py`, on the reading that one of my writes went through text
mode. **No write of mine did.** The file already reported CRLF before my first edit this
session; its first twenty lines, written in Phase 0 and untouched since, are CRLF today; the
blob at `HEAD` is LF; **136 tracked files** are CRLF in this working tree including
`tests/conftest.py` and `src/acsoe/console/format.py`, which nobody has written this session;
and `client.py`, which took my larger edit, is LF. `git diff` emits that warning the first time
a CRLF file appears in a diff **at all**, so it fires on the edit while being caused by neither
the edit nor the editor.

The form of the check that does matter was run in its place: **every committed file under
`tests/fixtures/` is byte-identical to its blob at `HEAD`**, by sha256. The two exceptions are
C-2's spec 63 deposits — `README.md`, deliberately modified, and `candles_sample.parquet`,
newly added and so having no blob to compare — and that parquet parses at 1,208 rows and 7
columns with `PAR1` intact at both ends. Reasoning in full in the build log.

#### STOPPED AND ESCALATED — two B sessions wrote `clients/store/` at once, and the other one is right

**2026-09-13.** The entry below this one is the other B session's account, written from the
other side of the same collision, and it is accurate about the collision. The 175 lines of
spec 62 it found on disk are mine. It is wrong on two details, both corrected in the build log
rather than by editing it: the tests **did** exist (it looked at a file mid-write), and the
CRLF in `test_store.py` is **pre-existing** rather than a conversion anybody performed —
`client.py` is LF and was written as bytes throughout.

**Its `parents=False` objection was right and is now the behaviour.** A writer creates the
artefact root and a reader refuses a missing one: C's trainer runs as
`python -m acsoe.research.training` and never touches A's startup path, so a writer demanding
an existing root would refuse the first training run on every fresh clone. I had reasoned the
other way and had told A so by message; A has been corrected.

**The split now in force, proposed by me and messaged to both the lead and the other session:**
it keeps `clients/store/` and `tests/clients/store/`, I take `engines/scout/` and
`tests/engines/test_scout.py`. The one exception I made afterwards is two `RUF043` findings on
lines I had written in `test_store.py` — `match="artefact root .* does not exist"` needed to be
a raw string — which I fixed rather than leave the `ruff` gate red on my own lines.

**Still open for the lead:** which session owns lane B. The notice at the top of
`feature-specs/PHASE-5-TASKS.md` says the `-2` sessions do and that bare-letter sessions are
stood down; my sends arrive as `B-2`. I did not treat that as settling it, because the other
session is the one acting on a ruling of 2026-09-13 I never received.

#### STOPPED AND ESCALATED — two B sessions are writing `clients/store/` at once

**2026-09-13, 00:36.** Not a code defect and not mine to fix. I read
`src/acsoe/clients/store/client.py` at the start of spec 62 and got 933 lines with no
`models_dir` in them; my first edit was refused as stale, and `git diff` showed all 175 lines
of spec 62 already on disk — `_validated_run_id`, `models_dir`, `_artefact_root`,
`model_run_dir`, `new_model_run_dir`, and a `leaderboard_entries` read as the step-3 audit gap.
`client.py` was written at 00:36:13, seven seconds after I wrote my own phase-5 build-log
header, so it is not a leftover from a session that ended before mine. Then
`tests/clients/store/test_store.py` moved at 00:36:51 — after a `git status` that showed it
unmodified — with one added import. That is a second B session mid-save.

**I have written no byte into `client.py` or `test_store.py`,** per the conflict procedure in
`ownership.md`: stop, record, escalate with the path and both intents, the lead decides. The
ownership map is the only concurrency control this project has and it assumes one agent per
path; two writers in one file is silent, last-save-wins, with nothing red. Escalated to the
lead by `SendMessage` with the timestamps and the sha256 of the file as I found it,
`4163b72c146a6cf5059a32b5b348795d5354e1bf7a8efc03f332160e20e83d00`, snapshotted to the session
scratchpad first so the state at detection is recoverable either way.

**The implementation on disk reads as correct and complete against spec 62**; tests do not
exist yet. Two things I would change whoever finishes it, both raised with the lead: the
constructor takes `models_dir` positionally where I had told A it would be keyword-only, and
`new_model_run_dir` uses `parents=False`, so a trainer started as
`python -m acsoe.research.training` — which never touches A's startup path — meets "the
artefact root does not exist" rather than having it created. The second is a defensible
decision and should be a ruling rather than two agents assuming opposite things.

**One symptom worth keeping separately:** `test_store.py` now has CRLF line terminators and
`git diff` warns on it, where it did not before. That is the text-mode round trip
`code-standards.md` describes — the whole file's endings rewritten, invisible in `git status`
because `.gitattributes` normalises on the way into the index.

Waiting on the lead for which session continues. Spec 76 is in `engines/scout/`, a disjoint
path, and can start the moment the lead says so.

## CLOSED — engine 17's `CONDITION_ACTION`, ruled 2026-09-10

**The operator ruled on 2026-09-10 and spec 37 wrote it into invariant 14.** The table is
now a decision, not my reading of a contradiction:

| Condition | Action |
|---|---|
| `DRAWDOWN` | `freeze` |
| `LOSS_STREAK` | `freeze` |
| `ERROR_RATE` | `freeze` |
| `DATA_OUTAGE` | `close_all` |

`close_all` is reserved for the invariant 14 data-outage escalation and for the operator's
own Close all button. The reasoning, which is invariant 14's and is not restated in the
code: a drawdown or a losing streak is a statement about *past* trades — the data is
trustworthy and the positions are being managed — so liquidating on it realises a paper
loss on the system's own authority at the moment it has least evidence it is reading the
market correctly. A sustained outage is a statement about *present* knowledge, and unknown
exposure is worse than a bad fill.

Two of the four rows changed. `ERROR_RATE` and `DATA_OUTAGE` were already as ruled.

**Applied in the code on 2026-09-10, verified.** An earlier version of this line claimed
the same thing while `engines/safety/contracts.py` still carried the pre-ruling table
under a heading reading PROVISIONAL. It was written in the same edit that *claimed* spec
42, and this file has no way to distinguish a claim from a completion — so the note
described work that had not happened. The build log carries the account.

**Changed how I use this file as a result: a spec is marked complete here only after its
four gates are green, never in the edit that claims it.**

**Ratified earlier and unchanged:** the `BOUNDARY_SOURCE` table beside it, fixing whether
each threshold trips *at* its limit or *above* it, each with the sentence in the documents
that fixes it. Drawdown, loss streak and error rate trip at the limit; the outage is the
only strictly-greater one.

## CLOSED — a suppressed `close_all` swallowed a co-occurring `freeze`, ruled 2026-09-10

**The operator ruled the way it was recommended, and invariant 14 now says so** (committed
`db50392`): *"When the winning action is suppressed, `safety` emits the strongest action
that is not suppressed"*, rather than emitting nothing. Implemented under spec 42 as a
fall-through in `_emit`, with both directions tested — it fires when a lesser action was
genuinely due, and does **not** fire when the outage is the only condition tripped, because
"always freeze if you cannot liquidate" would freeze a healthy account over an outage it had
no exposure to. Both mutations confirmed caught.

Spec 42 step 6 is unrepealed: still one command per tick, still no `freeze` alongside a
`close_all` that actually emitted. Only the fall-through is new.

The original statement is kept below, because the reasoning is what the ruling was made on.

---

**Raised 2026-09-10 while implementing spec 42. Not invented behaviour: the literal spec
is implemented and this is the case it does not cover.**

`_emit` takes the strongest action among the tripped conditions and emits at most one row —
spec 42 step 6, "the more severe action wins and the two are not both emitted". Correct on
its face. But the `close_all` branch has two suppressions of its own (no exposure, and
`close_intent` already set), and when the strongest action is suppressed **nothing is
emitted at all**, including the `freeze` that a co-occurring drawdown, loss streak or error
rate would have emitted on its own.

Concretely: drawdown breached, account has no open position and no resting entry order,
and a data outage is also running. Drawdown alone emits `freeze`. Drawdown *plus* the
outage emits nothing, because `close_all` wins and is then suppressed for want of anything
to close. More bad conditions produce less action, which is the wrong direction.

The practical impact is bounded and worth stating so the ruling is not read as more urgent
than it is: `safety` returns `BLOCK` on every tick where any condition is tripped, so the
opportunity chain is stopped regardless. What is lost is the *persistence* — the mode never
goes `frozen`, so the console shows a running system and the block is re-derived every tick
rather than recorded once.

**I have not fixed it.** The obvious fix is "emit the strongest action that is not
suppressed", which would be one line, and it is a change to what the breaker does — so it
is the operator's, not mine. Recommending that reading.

*(Ruled that way on 2026-09-10 and implemented under spec 42. See the heading above.)*

## `core/`'s two writes — landed, primitives only

`core/` imports nothing from the rest of the package, so it cannot construct a `RunRow`
to hand to `write_run`. Two entry points now take `str` and `int` and nothing else:

```python
def start_run(self, run_id: str, *, mode: str, started_at: int,
              acsoe_version: str | None = None,
              config_digest: str | None = None) -> None: ...
def set_system_mode(self, run_id: str, mode: SystemMode | str, *, at: int) -> bool: ...
```

Four decisions in them:

- **`start_run` refuses a duplicate `run_id`** rather than upserting. `run_id` is minted
  once per process, so a second start is a bug; an upsert would rewrite `started_at`, and
  the console decides the current run from the newest `runs` row — so the silent version
  of that defect reorders the two rows the restart banner compares. Raises `StoreError`.
- **It names its columns explicitly** instead of dumping a payload, so it cannot become a
  writer of `system_mode` the way `write_run` silently did when spec 31 added the columns
  to `RunRow`. `set_system_mode` stays the only writer of both.
- **`set_system_mode` takes a plain `str`**, and that is now a guarantee rather than a
  `StrEnum` implementation detail that happened to work.
- **An unrecognised mode raises; an unknown run returns `False`.** The two are not alike:
  a missing row is a race the caller logs and continues past, a misspelled mode is a
  defect, and sharing a return value would leave the console on a stale mode with nothing
  saying why.

Proved with no double, the way `commands_round_trip` is: a **fresh interpreter** whose
entire import of this package is `StoreClient`, running the whole path on real SQLite,
plus a test that reads that caller's own source and asserts it names no contract and
constructs no row. `tests/clients/store/test_core_entry_points.py`, 17 tests.

## `bootstrap.py` — requested, deliberately deferred by the lead

- `CostEngine` — opportunity chain, after 9, before 11. `is_gate=True`.
- `RiskEngine` — opportunity chain, after 10, before 14. `is_gate=True`.
- `SafetyEngine` — **guard** chain, last, after 4. `is_gate=True`.

Deferred until the tree is globally green: `safety` in the guard chain runs on every tick of
`orchestrator_empty_registry` (a Phase 0 gate) and `commands_round_trip` (Phase 2), both
against a real `StoreClient`. On an empty database nothing should trip — but "should" is
doing work in that sentence, and if it does trip that is a finding worth having in isolation
rather than tangled with A's in-flight engine work. Engines 10 and 11 are opportunity-chain
and inert in both criteria.

## Spec 31 — persisted system mode

**Shape.** Two nullable additive columns on `runs`, not a new table:
`system_mode TEXT CHECK (... IN ('idle','running','frozen'))` and
`system_mode_at INTEGER`. Nothing existing is altered, nothing is dropped, no table is
added — so `db_migrates_from_empty` and `architecture-context.md`'s storage table need
no lead edit. Reasoning in full in `docs/build-log/phase-2/b-store.md`; the short version
is that `runs` already carries a UNIQUE `run_id`, so scoping by run is structural rather
than conventional and there is no query a reader can get wrong.

**The seam C builds against — this is the whole contract:**

```python
# src/acsoe/clients/store/contracts.py
class SystemMode(StrEnum):
    IDLE = "idle"; RUNNING = "running"; FROZEN = "frozen"

class SystemModeRow(_Row):
    run_id: str
    mode: SystemMode | None = None
    at: Micros | None = None          # microseconds, UTC; None iff mode is None

# src/acsoe/clients/store/client.py
def system_mode(self, run_id: str) -> SystemModeRow | None: ...
def set_system_mode(self, run_id: str, mode: SystemMode, *, at: int) -> bool: ...

# RunRow also carries `system_mode` / `system_mode_at`, read-only, for a caller that
# already holds a RunRow and does not want a second query.
```

**Two nulls, two different facts, and the console must not collapse them.**
`system_mode(...)` returns `None` when there is no `runs` row for that `run_id` — a
defect or a race, not a mode. It returns a row with `mode is None` when the run exists
and no daemon has written a mode yet — the ordinary case before the first command is
read. Both render as an idle reading per spec 32, but only the second is normal, and a
reader that cannot tell them apart cannot log the abnormal one.

**Writer.** `set_system_mode` is the only writer of both columns. `write_run` explicitly
excludes them, so the orchestrator's shutdown write of `ended_at` cannot clobber a
`frozen` daemon's persisted mode with the stale `None` its startup `RunRow` carries. The
caller is the command reader in `src/acsoe/core/orchestrator.py`, which is lead-only: I
provide the method, the lead calls it. `set_system_mode` bumps `runs.updated_at` too,
because `runs` is in `WATERMARK_TABLES` and without that the console would never repoll.

**Mode is never restored from the store.** There is no third method that reads this back
into `state["system"]`, and none should be added. A daemon always starts `idle` and
reaches `running` only through an `activate` command; restoring it would invert the
safety property that a crashed daemon comes back not trading, and it would look like a
bug fix while doing so.

**Nothing is seeded.** `seed.py` writes no system mode and
`test_the_seed_writes_no_system_mode` now asserts it, so C's Running-band test cannot
pass without a daemon having written one.

## Status

Spec 31 is green. All three gates, run 2026-09-09:

```
Phase 0 is green: every criterion PASS, zero PENDING.   (7 criteria: 7 PASS)
Phase 1 is green: every criterion PASS, zero PENDING.   (10 criteria: 10 PASS)
Phase 2 is green: every criterion PASS, zero PENDING.   (3 criteria: 3 PASS)
```

`723 passed` · `mypy --strict src/` clean, 35 files · `ruff check src/` clean.

The two `tests/db/test_migrations.py` failures the migration caused are fixed, and the
fix is not a bumped literal: both expectations now derive from the migrations directory
while still asserting the count and the ordering. See the build log for why the literal
was the wrong shape and for the asymmetry it exposed — `db_migrates_from_empty` passed
throughout, because it tolerates extra tables and 0002 adds none, so the phase gate did
not notice a schema change that my own unit tests did.

Spec 11 and 12's criteria still report PASS:

- `db_migrates_from_empty` — a fresh database migrates to all 9 documented tables; a second
  `migrate()` returns `[]`, so "re-migrating is a no-op" is checked on the returned list
  rather than on a schema diff.
- `seed_fixtures_present` — all six Phase 3 fixtures present, each overshooting its threshold
  rather than sitting on it.

Nothing of mine is outstanding. Spec 11 unblocked 12, which unblocked 13, in that order.

## For the lead — two things, neither of them mine to fix

1. ~~**`core/` must now call `store.set_system_mode(run_id, mode, at=now)`** from the
   command reader.~~ **DONE and this note is struck, 2026-09-10.** The lead wired
   `_persist_mode` at the command reader and asserted in `tests/core/` that the
   `system_mode` column staying NULL on an idle daemon is *correct* — a mode never entered
   is a mode never recorded — so that it does not get "fixed" later. Spec 31 is fully
   delivered.
2. **An intermittent Windows teardown fault outside my paths.** The first `--phase 0`
   run reported `FAIL toolchain_green — ERROR tests/cli/test_entrypoints.py::
   test_console_refuses_an_unset_operator_key | 722 passed, 1 error`. An `ERROR`, not a
   `FAILED`, exit 1 rather than an NTSTATUS, in A's `tests/cli/` — so it is neither the
   known seed-path native fault nor anything of mine. Captured verbatim in the build log
   before re-running, as the phase rules require; the re-run was green with no change.
   Separately, `scripts/verify.py` prints an unhandled `PermissionError [WinError 32]`
   on `acsoe-verify-doubles-*\acsoe.sqlite` from its own `TemporaryDirectory` finalizer
   on **every** phase-0 run, green ones included. Same Windows shape twice — a SQLite
   file still open when a temp directory is collected — one in A's test, one in C's
   script.

## Open questions — both resolved

### 1. `is_primary` uniqueness scoped by `run_id`, not `cycle_id` alone — RESOLVED

Implemented as a partial unique index on `(run_id, cycle_id) WHERE is_primary = 1`. Escalated
before implementing further. **The lead approved it, amended spec 11, and fixed the root cause
in `architecture-context.md`,** which now states that a tick is `(run_id, cycle_id)` and never
`cycle_id` alone. Every "once per tick" constraint and cross-table join in the schema is scoped
to both columns as a result. The seed deliberately overlaps the two runs' `cycle_id` ranges and
says so in its docstring — that overlap is load-bearing, and tidying the runs apart would
silently disarm the Phase 3 test that proves ordering is by `ts`.

### 2. `safety` threshold key names and values — RESOLVED

The lead fixed the key names and **the operator supplied the values on 2026-09-08.** The seed
does not read `config/default.yaml`; it takes a `SeedThresholds` dataclass, so a Phase 3 test
seeds against whatever the config actually says. What the committed config now asks for, and
what the seed produces against it:

| Key | Operator value | Seed produces |
|---|---|---|
| `safety.max_consecutive_data_blocks` | 15 | 18 consecutive `data_guard` ticks, over 2 `run_id`s |
| `safety.max_drawdown_pct` | 0.10 | drawdown of 0.2000017843760037115020877199 at the trough |
| `safety.max_consecutive_losses` | 5 | losing streak of 8 |
| `safety.error_rate_window_s` | 3600 | — (fixed by `architecture-context.md`: "the trailing hour") |
| `safety.max_errors_in_window` | 20 | 23 `status='ERROR'` block records in the window |

My earlier proposal of `max_errors_in_window: 10` was not what the operator chose; the table
above is the committed state. The seed also writes 2 open positions, 2 resting entry orders,
33 trades and 46 rejections.

## Three decisions in the schema and the migration runner

Recorded in full in `docs/build-log/phase-0/b-store.md`; summarised here because each one is a
property another agent will rely on rather than an implementation detail of mine.

- **The database refuses a float in a money column.** Every money column is `TEXT` **and**
  carries `CHECK (typeof(col) = 'text')`. SQLite is dynamically typed, so a `TEXT` column stores
  a float without complaint and hands it back as one — "money is never `REAL`" was an assertion
  in a document rather than a property of the database. A single write bypassing the client, in
  any phase, would have seeded a drifting number into the equity series that moves the drawdown
  threshold that liquidates the account. The client now passes `str(Decimal)`.
- **`executescript` discards the transaction wrapped around it.** It issues an implicit `COMMIT`
  of any pending transaction before running its script, so the first runner's `BEGIN` was
  committed away by the very call it was meant to protect. `BEGIN`/`COMMIT` moved inside the
  script string, and the `schema_migrations` insert moved in with them — otherwise a crash
  between the two transactions leaves a database whose schema is applied and whose version row
  is not, and the next startup tries to create tables that already exist.
- **Migration bookkeeping records no wall-clock time by default.** `apply_migrations(...,
  applied_at: int | None = None)`. Spec 13 requires two seedings of the same seed to be
  byte-identical and the seed migrates the database it seeds, so a clock-stamped column would
  make every seeded database differ for reasons unrelated to the seed. The checksum, which is
  the field that protects anything, is always recorded.

## Known issue in my code path — closed as a risk, not root-caused

`toolchain_green` fails intermittently — roughly 20% of full-suite runs — with a native memory
fault, and every observed instance surfaces inside my write path:
`seed.py:_write_trading_history` → `client.write_trade` / `write_position` → pydantic
`model_dump`. Three distinct Windows statuses have been seen (`0xC0000005` access violation,
`0xC0000374` heap corruption, `0xC0000409` stack buffer overrun) plus an
`AttributeError: 'NoneType' object has no attribute '__dict__'` raised from inside `to_python`.

It is **not** a logic defect in the seed: every test passes when the process survives, and
`seed_database` called 60 times outside pytest is clean. My suspicion of pydantic-core 2.46.5
was checked and did not hold — pinning a different build did not settle it. The lead
investigated it at length and closed it without a root cause; pyarrow, `pytest-asyncio`, test
ordering, `root_import_path` and the pydantic-core version were each ruled out, hardware is
suspected and is out of scope, and the gate now retries a crash once. Full account in
`docs/build-log/phase-0.md`.

**Do not re-run the suite to see whether the result changes.** That experiment has been run. It
becomes mine again if the fault appears outside this write path, or if the gate starts
reporting `CRASH -` after its retry — which would mean the rate has moved and the mitigation no
longer holds.

## The one-type-many-causes shape, audited in my own lane — 2026-09-10

The lead asked whether `StoreError` in `clients/store/` has the shape A found in
`clients/kraken/`, where every fail-closed path raises one type so `pytest.raises(That)`
cannot tell the induced failure from one that happened first.

**Audited: four `raise StoreError` sites, so the shape is present but small.** They are the
non-finite money refusal, an unknown run mode, a duplicate `run_id`, and an unknown system
mode. Three of the four assertions already used `match=`; one did not —
`test_the_two_failures_are_distinguishable_by_type` — and it is now `match="unknown system
mode"`. That test is about `False`-versus-raise rather than about the cause, so it was not
wrong, but the bare form would have been satisfied by any of the four.

Nothing else in my lane raises one type from many places. `MissingInputError` in the three
engines is per-module and every assertion on it goes through `reason_code`, which is the
generalisation the standard actually asks for: **assert the reason, not only the `BLOCK`.**

## Reading a moving tree by path, and not re-running to find out — 2026-09-11

Recorded at the lead's request because it is process rather than code, and because the
habit is the deliverable.

Four times in Phase 4 the tree was red while I was working in it, and none of them was
mine. Each was settled **by path and by lane, without re-running anything and without
opening a file I do not own**:

- 26 failures in `tests/scripts/test_build_archive.py` — A's spec 54, mid-save. Left
  alone; green again on its own later, which is what landing looks like.
- `rejections_survive_restart` and `console_history_reads_real_rows` raising
  `AttributeError: module 'acsoe.engines.memory.contracts' has no attribute
  'DECISION_KEY'` — C's engine 19, mid-save.
- 2 pytest failures, 1 `mypy` error and 1 `ruff` error, all in
  `research/walkforward.py` and `tests/research/test_walkforward.py` — C's spec 53,
  mid-save.
- One failure that **was** mine, `test_an_outage_counted_by_cycle_id_is_a_fail`, which
  sits in C's `tests/verify/` by path and was still my defect. Path is the first
  question, not the last one: it named my file, it reproduced every time, and it was
  caused by a string I had just written.

**The rule that makes this work is the one Phase 3 paid for:** a defect of mine
reproduces every time, in isolation, in my own paths — and *re-running to see whether the
result changes* is the diagnostic that cannot fail, because in isolation nothing else is
touching the temp directory. The counter-example above is the important half. "It is in
another agent's path" is evidence, not a verdict; the verdict came from asking whether
the failure names my code and whether it reproduces, and once it did I stopped and wrote
the diagnosis before the fix.

## Blocked on

Nothing.

## Verification

```
$ .venv/Scripts/python.exe scripts/verify.py --phase 0
PASS    db_migrates_from_empty       fresh database migrated to all 9 documented tables
PASS    seed_fixtures_present        all six fixtures present: outage run 18 ticks over 2 run_ids
                                     (11 double-blocker), 2 open position(s), 2 resting order(s),
                                     drawdown 0.2000017843760037115020877199, losing streak 8,
                                     23 ERROR blocks in the window, 33 trades / 46 rejections

7 criteria: 7 PASS, 0 FAIL, 0 PENDING
Phase 0 is green: every criterion PASS, zero PENDING.
```
