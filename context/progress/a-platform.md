# Progress — a-platform

Your file. Only you write here. The lead merges into `context/progress-tracker.md`.
Never edit the tracker directly.

## PHASE 6 — CLAIMED 2026-09-15, before any code was written

Per `feature-specs/PHASE-6-TASKS.md` and ownership rule 5, A claims **specs 84, 85, 86 and 87**,
in that order. Nobody else may start them.

| Spec | What | Files I will touch | State |
|---|---|---|---|
| 84 | The order surface — `OrderRequest`, `OrderAck`, `OrderState`, `OrderClientProtocol`; the live client refuses every order call until Phase 8 | `src/acsoe/clients/kraken/contracts.py`, `rest.py`, `client.py`, `__init__.py`, `README.md`, `tests/clients/kraken/test_orders.py` | **LANDED 2026-09-16** |
| 85 | Engine 3 publishes each pair's trade low, high and count since the previous tick | `src/acsoe/engines/market_sensor/{contracts,engine,README}.py`, `tests/engines/test_market_sensor.py` | **LANDED 2026-09-16** |
| 86 | Paper broker wired into `build_clients` in paper mode only; `scripts/cut_book_fixture.py` | `src/acsoe/cli/engine.py`, `scripts/cut_book_fixture.py`, `tests/cli/test_paper_broker_wiring.py`, `tests/scripts/test_cut_book_fixture.py` | **LANDED 2026-09-16** |
| 87 | Rehearse B's engines 18, 21, 22 through real orchestrator ticks | `tests/engines/test_trade_chain_rehearsal.py` | **DONE 2026-09-16** (see SPEC 87 below). 7 scenarios green after spec 103 closed finding 1; 5 mutations killed (M1-M4, and B1 on the broker) + 1 equivalent control. Finding 2 is with specs 104/105 |

Spec 84 is first because nothing else in the phase can start without it: B's paper broker (88)
implements it and engines 18, 21 and 22 call it. The concrete signatures are under
**SPEC 84 — THE ORDER SURFACE, FOR B** immediately below.

## SPEC 109 — THE PAPER-MODE FALLBACK PROSE — DONE 2026-09-18

A claimed **spec 109**; claimed before any byte was changed, and the build-log diagnosis
entry was written before the first edit. Prose only: no behaviour, no payload, no test
assertion, nothing outside lane A.

| Spec | What | Files I touched | State |
|---|---|---|---|
| 109 | Lane A stops describing paper-mode fallbacks that no longer exist; each site points at invariant 2 instead of restating it | `clients/kraken/{README.md,rest.py}`, `engines/exchange/{README.md,contracts.py,engine.py}`, `platform/config.py`, `tests/engines/test_exchange.py`, `tests/clients/kraken/test_rest.py`, this file, `docs/build-log/phase-6/a-platform.md` | **DONE 2026-09-18** — `182 passed in 1.22s`; ruff clean; mypy `153 source files` |

**Narrow runs** (the lead runs the authoritative gate; I ran no full gate):
`tests/engines/test_exchange.py tests/clients/kraken/` → **`182 passed in 1.22s`**
(`logs/verify/a109-pytest.log`); `ruff check src/ tests/ scripts/` → **All checks passed**
(`logs/verify/a109-ruff.log`); `mypy --strict src/ scripts/` → **`Success: no issues found
in 153 source files`** (`logs/verify/a109-mypy.log`).

**Line endings.** Only `engines/exchange/contracts.py` and `engines/exchange/engine.py` are
CRLF; the other six files are wholly LF. Both CRLF files were patched through Python with the
replacement's endings converted explicitly and the counts re-read afterwards (108 and 197 CRLF,
**zero** bare LF in either). No heredoc carried an escape into any file.

**A measurement error worth recording, because it nearly went the other way.** My first CRLF
count used `grep -c $'\r$'` and reported *every* file as wholly CRLF — including four that hold
no CR at all. The number was equal to `wc -l` for all ten files, which is what gave it away. The
count that decides how a file is written has to be taken with the tool that will write it;
re-measuring with Python gave the real split above. Had I trusted the first reading I would have
converted six LF files to CRLF wholesale.

### The eight sites rewritten

Sites 1–5 are the ones spec 109 names. Sites 6–8 were found by the lane grep and carry the same
sentence or a worse one; they are the same defect and were not left behind.

| # | Site | Before, in substance | After, in substance |
|---|---|---|---|
| 1 | `clients/kraken/README.md` (~52) | The client supplies no fallback **because invariant 2's paper-mode fallbacks are the consumer's decision**, and the consumer must record which fired | Same refusal, and read invariant 2 for why: since 2026-09-16 no paper-mode fallback remains anywhere, so a failed fetch blocks in paper exactly as in live. The client reports the failed call and substitutes nothing; **no consumer substitutes either**. A value supplied here would not pre-empt a decision — there is none left — it would be the only thing still able to turn a block into a trade |
| 2 | `engines/exchange/README.md` (~62) | The three calls are concurrent so a consumer knows which value is missing, **because invariant 2's fallback is different for each one**; engine 1 applies none of *those fallbacks*, which are the consumer's to record | The concurrency reason is now the true one: **engine 10 `cost` is the reader that makes the per-call granularity load-bearing** — it quotes the named call and its reason in its block sentence, because "missing exchange.fee_tier" sends the operator to a `None`. Then: this engine substitutes nothing and no consumer substitutes either; invariant 2 is the place to read why and it is shorter than it was |
| 3 | `engines/exchange/contracts.py` (~16) | Engine 1 does not apply **invariant 2's paper-mode fallbacks: those are the consumer's decision** and supplying one here would erase the record | Engine 1 reports the failed call and substitutes nothing; invariant 2 — pointed at, not restated — leaves no paper-mode fallback anywhere, so no consumer substitutes either. The gate handed `None` still blocks, invariant 3 |
| 4 | `engines/exchange/engine.py` (~117) | One outage must not become three blanks, **because the paper-mode fallback for each one is different** | Same requirement, true reason: engine 10 quotes the named call and its reason rather than the state key that is merely `None` |
| 5 | `tests/engines/test_exchange.py` (module docstring, ~10) | The engine does not apply **invariant 2's paper-mode fallbacks: those are the consumer's decision** | It substitutes nothing, and under invariant 2 neither does any consumer: no paper-mode fallback remains, so the published absence is the answer and every gate handed it blocks |
| 6 | `clients/kraken/rest.py` (~300, `map_trade_volume`) | **Not named by spec 109.** There is no "assume a tier" **because invariant 2's paper-mode fee fallback is a decision made by the consumer** | The fee fallback was retired 2026-09-10 and the last of any kind 2026-09-16, so a confirmed pair with no fee data blocks in paper exactly as in live. **Nothing downstream is waiting to supply what this function refuses to invent** |
| 7 | `tests/engines/test_exchange.py` (~208, the fee-fallback test's docstring) | **Invariant 2's paper fallback is the consumer's decision** and the consumer must record which fired | Invariant 2 leaves no paper-mode fallback anywhere: a failed fee fetch blocks the pair in paper exactly as in live. A tier supplied here is the substitution the invariant forbids, and a hardcoded fee besides |
| 8 | `tests/clients/kraken/test_rest.py` (~263, docstring) | **Invariant 2's paper fallback is the consumer's decision**, recorded as such | Invariant 2 leaves no paper-mode fallback: a pair with no fee data blocks. A supplied tier is indistinguishable from a fetched one |

**Both test *names* were kept** — `test_no_fallback_is_ever_substituted_for_a_failed_fee_fetch`
and `test_a_missing_fee_field_is_a_failure_and_never_an_assumed_tier` are accurate under the
amended invariant and are more accurate than they were. Only the docstrings moved. **No
assertion was touched in either file.**

Site 9 — `platform/config.py::load_credentials` — is rewritten too and is written up as
**finding 3** below, because it is the one that claimed something about behaviour rather than
about whose decision a fallback is.

### THREE FINDINGS, none of them silently corrected

#### Finding 1 — an assertion in my own lane that cannot fail

`tests/engines/test_exchange.py`, in the fee-fallback test:

```python
assert data["fee_tier"] is None
assert "tier" not in str(data.get("fee_tier"))
```

Given the line above it the second is `"tier" not in "None"`, a tautology. It could only fail on
a `fee_tier` that was a mapping carrying the key, which the preceding line has already excluded.
The test's name is the property worth having and the **first** line proves it; the second reads
as a stronger second check and is not one.

**Not changed** — spec 109 is prose-only and a test assertion is not mine to edit under it. For
a ruling: delete it, or replace it with an arm that can fail — assert on the whole payload, so a
tier smuggled into a sibling key would be caught.

#### Finding 2 — `exchange/README.md` describes a retention read that no engine performs

Outside the grep's four words; found by reading the file. The "Retained last-known-good values"
section says *"engines 21 and 22 read it from the client directly in Phase 6"*. On disk at
`2beb8ba`:

- **Engine 21 `position_manager` reads neither retained value** — `last_known_good` does not
  occur anywhere in that package.
- **Engine 22 `exit` reads only `last_known_good_asset_pairs`** (`engines/exit/engine.py:523`),
  and its `contracts.py:159-166` records that it **deliberately never reads a balance**: an
  exit's quantity is the position's, and a cap at the base holding would round every paper exit
  to nothing, the paper ledger being quote-side only by B's spec 88 ruling.
- So **`last_known_good_balances` has no reader in `src/` at all.** The client retains it
  (`clients/kraken/rest.py:551`, on the facade, forwarded by the paper broker), engine 1 reads
  its *age* to publish `retained`, and nothing reads its value.

**The decision exists and it is in B's lane, not mine.** B recorded it 2026-09-16 in their build
log ("Decision: engine 22 never reads a balance…") and progress file, marked **escalated to the
lead** as a deviation from spec 93. So nothing changed unrecorded — A's README was simply never
told, and the sentence was true of the spec and never of the code.

**Why it is not a nicety.** Invariant 2 justifies the retention as *"a requirement on Agent A's
client, not an optimisation"* because discarding *"would make rule 14 unimplementable at exactly
the moment it is needed."* For `AssetPairs` that is right and engine 22 proves it. For the
balance the premise no longer holds, and A's README is the only place still asserting it does. A
reader auditing invariant 14 against the code finds a retained balance, a README saying two
engines read it, and no reader — and cannot tell a requirement being met from a limb nobody
amputated.

**Not changed**, per the rule on stale prose. Two questions for the lead, neither mine under a
prose spec:

1. Does `last_known_good_balances` keep its retention with no reader — invariant 2's wording
   requires the client to retain it regardless — or does invariant 14's *"engines 21 and 22 may
   use the last known good balances"* need amending to what B built and the lead accepted?
2. The README sentence is wrong either way, but **which** correct fact to write depends on the
   answer to (1), so it waits for the ruling rather than guessing.

#### Finding 3 — `load_credentials` told a fresh clone it could trade

`platform/config.py`: *"paper mode runs the whole pipeline without one, and invariant 2's paper
fallbacks exist exactly so that it can."* Both halves false, and the second worse than the other
eight sites: it names paper fallbacks as the **mechanism** that makes an unauthenticated clone
work. Invariant 2 states the truth in as many words — with an empty `.env` the private calls
fail, `TradeVolume` returns nothing and **every pair blocks at the cost gate**; the clone still
runs the loop, still records the book and still builds candles, but **takes no paper trades** and
writes no rejection past that gate.

**This one is rewritten as well as reported**, and the line between it and finding 2 is the test
the lead set. Here the ruling exists and is explicit — invariant 2 already spells out both what a
keyless clone does and what it does not — so the code does what the system decided and only the
sentence is stale. In finding 2 the ruling is B's, it points the other way from my prose, and
choosing which fact to record would be answering it.

### Every other grep hit, with a verdict

`fallback`, `starting_balances`, `substitut`, `assume` across `clients/kraken/`,
`clients/recorder/`, `platform/`, `cli/`, `scripts/` (less `verify.py`), `engines/exchange`,
`market_data_recorder`, `market_sensor`, `data_guard`, `research/{replay,historical,backtest}.py`
and lane A's tests. Everything below is **kept unchanged**; the eight rewritten sites are in the
table above and are not repeated.

**True statements of invariant 2 as it now reads — keep:**

- `clients/kraken/contracts.py:11` no default "not even as a fallback"; `:272` an assumed input
  invalidates the cost gate; `:334` the spread is the input that may never be assumed; `:397` a
  retained stale spread is a loaded gun pointed at the input that must have no fallback — this
  one is invariant 2's own reasoning almost verbatim and is still correct.
- `clients/kraken/README.md:41` no fee/minimum/tick/precision as constant, fallback or comment;
  `:129` and `:148` an assumed spread invalidates the gate; `:292` "It applies no fallback. See
  above" — still true, and "above" now points at the rewritten paragraph.
- `clients/kraken/rest.py:40` and `:351` assumed spread or fee invalidates the gate; `:47` no
  constant, fallback or comment; `:262` a missing pair rule blocks that pair with no fallback —
  matches invariant 2's table row exactly.
- `engines/data_guard/engine.py:84` "No default, and no fallback if the key is absent —
  `config.get` raises"; `engines/data_guard/README.md:62`; `engines/market_sensor/README.md:176`.
- `tests/platform/test_config.py:763` — *"a fallback here is a guessed answer to how much money
  is at risk"*. Stronger now than when written.
- `scripts/record.py:1298` — a hardcoded fallback is how a recorder quietly records the wrong
  thing.

**The word `fallback` used for something that is not an invariant-2 fallback — keep:**

- `clients/kraken/ws.py:149-156` `_parse_ts(value, fallback)` and `:435` `_fallback_now()`. A
  receive-timestamp for a frame whose own stamp will not parse. **Checked against invariant 9:**
  `_fallback_now` returns `self._clock.now()`, the injected clock, not a direct read. No trading
  value is involved.
- `engines/market_data_recorder/engine.py:133,143` `fallback_ts = _iso(context.now)` — a gap
  marker's stamp, also from the injected clock; `engine.py:5` and `README.md:157` — the
  standalone recorder is the *operational* fallback for when the engine framework is down.
- `platform/config.py:704` `ScoutConfig` — alphabetical ordering while `rank_feature` is absent,
  *"a stated, boring fallback rather than a guess at what predicts a move"*. A ranking order, not
  a traded value; invariant 2 does not reach it and the engine publishes `rank_feature: null` so
  the record says which ordering was used.
- `cli/console.py:10` no fallback console app; `cli/research.py:188` no silent fallback on an
  engine signature mismatch.
- `tests/platform/test_config.py:782` an `except ImportError` fallback that stays armed.

**`starting_balances` — keep, all of them:**

- `clients/kraken/contracts.py:124` — *"A currency code to amount map, exactly as
  `paper.starting_balances` is shaped."* **Verified structurally true**: the config field is
  `dict[str, Money]`, the alias is `Mapping[str, Money]`. It is a shape analogy and makes no
  claim about where a balance comes from.
- `platform/config.py:281,285,289,295,299,302` the validator and the field itself; `:959` a
  `Config.get` docstring example of a map key and a leaf inside it. Code and examples, not claims.
- `tests/platform/test_config.py` (11 hits) the section's own tests; `tests/cli/test_entrypoints.py:103,117` fixture config.
- **Nothing in lane A reads `paper.starting_balances` as a balance.** The only readers in `src/`
  are B's `clients/paper/broker.py`, which is the authority on its own cash, and the config
  layer that validates it. Engine 11's read was removed by spec 106.

**`substitut` — keep:** `platform/config.py:1111` YAML has no substitution;
`scripts/cut_book_fixture.py:138` *"None rather than a substituted time"* — the right instinct;
`scripts/recording/manager/registry.py:29` `{archive}` is substituted into a command template;
`tests/research/test_di.py:116` a named mutation.

**`assume` — keep:** the "measured rather than assumed" idiom throughout
(`scripts/build_archive.py:28,63`, `build_ohlcvt.py:21,54,393,647,687`,
`cut_book_fixture.py:120`, `ohlc_fixture.py:12`, `reconcile_spread.py:109`, `record.py:2387`,
`recording/manager/archive.py:4`, `engines/market_sensor/README.md:46,130`,
`tests/scripts/test_recording_manager.py:274`, `tests/clients/kraken/test_ws.py:622`,
`tests/research/test_replay.py:134,377`, `tests/research/test_training_main.py:225`); the naive-
datetime refusals (`clients/kraken/contracts.py:136`, `platform/clock.py:16`,
`tests/platform/test_clock.py:5`, `tests/clients/kraken/test_contracts.py:123`); *"a backtest
that silently assumes zero spread is invalid"* (`research/replay.py:111,405`,
`research/historical.py:35,82`, `research/backtest.py:26,100`, and their three tests);
`clients/kraken/README.md:59` "The field-name assumption", which is an honest statement about
Kraken's field names and not about a trading value; `tests/clients/kraken/test_cache.py:340`,
`test_rest.py:404`, `tests/engines/test_data_guard.py:170`.

**`cli/engine.py:75` was checked and needed nothing.** `build_clients` already says the right
thing — engine 1 records the failure and *"every gate that needs a value it did not get blocks on
its own. That is invariant 3 working."* No fallback is mentioned or implied.

### Stale copies outside lane A, reported not touched

Three historical records still carry the superseded framing. All three are append-only logs, and
rewriting a dated entry falsifies what was true on its date, so none was edited:

- `context/progress/b-store.md:287` — "fallbacks the consumer's decision". **B's file.**
- `context/progress-tracker.md:1476` — an audit entry stating the *old* invariant 2 outright:
  "Fee falls back to tier 1; balance falls back to `paper.starting_balances`". **The lead's
  file**, and the most quotable stale sentence left in the repository.
- `context/progress/a-platform.md` — my own Phase 2 spec 26 entry, under "Three things I want the
  next reader to notice". **Mine**, and given a supersession pointer rather than a rewrite; see
  the how-choices below.

`context/trading-invariants.md:97` also matches the grep — *"Every decision affected by a
fallback records which fallback fired"* — and is **correct**: line 99 immediately scopes it to
rule 14's liquidation, the one place a stale value is still used.

### How-choices, each with the option rejected

1. **Point at invariant 2; do not paraphrase it.** *Rejected:* restating the amended rule at each
   site. Every one of these nine sites was a paraphrase, and each had to be re-edited when the
   rule moved — nine sites, five files, three retirements (2026-09-10, 2026-09-16, tonight). A
   site that names the rule and states only its own local consequence survives the next amendment.
2. **Rewrite the paragraphs; delete none.** *Rejected:* deleting the fallback sentences outright.
   Each paragraph carries a second fact worth keeping — why the calls are concurrent, why
   `map_trade_volume` refuses a partial result — and the absence of a fallback is itself
   load-bearing prose now that it is absolute. Deleting would leave the refusal looking arbitrary.
3. **Fix sites 6–8 although spec 109 names only five.** *Rejected:* fixing exactly the five
   listed. Sites 6 and 8 carry the identical sentence, in lane A, one file away; leaving them
   would have left the defect in the repository under a spec whose title says it was removed.
4. **Replace engine 1's concurrency justification with engine 10's real use of it, rather than
   deleting the justification.** *Rejected:* saying only "one outage must not become three
   blanks". The per-call granularity has a live reader — `cost/engine.py::_failed_fetch_reason`,
   verified, not assumed — and a requirement with its reason deleted is the next thing someone
   simplifies away.
5. **A supersession pointer on my own Phase 2 entry, not a rewrite.** *Rejected:* rewriting the
   Phase 2 paragraph to read correctly. It was true on its date and a progress file is a record;
   the tracker's own idiom for this is a strikethrough plus "Superseded by", and that is what was
   used. *Also rejected:* leaving it alone, since a dissertation reader who reaches line 1299
   believes consumer-side fallbacks exist.
6. **Two test names kept, two docstrings rewritten.** *Rejected:* renaming
   `test_no_fallback_is_ever_substituted_for_a_failed_fee_fetch`. The name states the property
   that is still true and is now unconditionally true; renaming would churn a green test for
   nothing and would lose the grep trail from the spec to the test.
7. **`clients/kraken/contracts.py:124` left exactly as it is.** *Rejected:* adding "and never a
   source of balances for this client" to the `Balances` alias comment. The comment is a
   structural analogy on a type alias, verified true, and makes no sourcing claim; the warning
   belongs where a balance is actually chosen, which is not in lane A.

## SPEC 116 — THE REHEARSAL FOLLOWS THE EXIT-CYCLE RULING — CLAIMED 2026-09-17

A claims **spec 116**. Nobody else may start it.

| Spec | What | Files I will touch | State |
|---|---|---|---|
| 116 | `test_trade_chain_rehearsal.py` follows the operator's exit-cycle ruling of 2026-09-17: strip the two payload-only fields before the row models, and restate the equity expectation as the account *after* engine 22's sales | `tests/engines/test_trade_chain_rehearsal.py`, this file, `docs/build-log/phase-6/a-platform.md` | **DONE 2026-09-17** — `7 passed in 66.79s`; 2 mutation arms KILLED |

No engine, `core/`, `bootstrap.py`, `clients/`, `scripts/verify.py` or other lane's test was
touched. The mutations were run in a **copied tree** under my scratchpad, never in the
working tree, and the copy was deleted afterwards.

**What changed in the file.** Two things, both in `check_recorded`.

1. A `without(row, field)` helper drops `POSITION_VALUE_FIELD` and `NET_PROCEEDS_FIELD`
   before `PositionRow` / `TradeRow` validate the *expectation*. `_Row` is `extra="forbid"`
   and neither field is a column — engine 19 reads both off the payload — so this is the
   column set the tables actually have, not a relaxed comparison. Both names are imported
   from their owning engine's contracts, so a rename breaks the import.
2. A `ruled_equity(state)` helper returns the `(cash, positions_value, unrealised_pnl,
   cash_source)` the ruling licenses, or `None` for "no row is due". On an exit tick cash is
   engine 1's start-of-tick balance **plus** the published `net_proceeds`, the two position
   totals are sums over engine 21's marked rows **less** every `position_id` engine 22
   carries as closed, and the label is `after_exit`; otherwise engine 21's own totals and
   `cycle_start`. `None` now *requires* engine 19 to have skipped, so "it skipped" is no
   longer an unconditional early exit from the check.

**How it was kept independent.** Written from `context/engine-contracts.md` — the ruling and
the two cross-chain rows — and from the payload builders that produce the facts (engine 21's
`_mark`, engine 22's `_trade_row` / `_closed_position_row`), which are the sources, not the
consumer. `engines/memory/engine.py` was not opened until the file was already green and the
mutation needed an anchor; C's probe and C's build-log entry quoting it were not read. It also
does not copy engine 19's shape in three places, each a way for the two to disagree: whether a
row is due is decided from the remaining marked rows rather than from engine 21's withheld
total; the sums are taken over the per-row fields rather than the totals; and `cash_source` is
derived rather than read back. Full reasoning in the build log.

**Proof it can fail** (`logs/verify/a116-mutation-e19.log`). A1, the arm spec 116 names —
engine 19's `if sold or closed:` → `if False:`, so it writes the pre-exit row again — is
**KILLED, `4 failed, 3 passed in 75.06s`**, on `the row's cash is not the account the ruling
describes`, `Decimal('1663.92…') == Decimal('4924.37…')`. A2 — the label alone,
`CashSource.AFTER_EXIT` → `CYCLE_START` — is **KILLED, `4 failed, 3 passed in 70.26s`**, on
`the row is labelled for the wrong instant`. A2 exists because A1 dies on the cash assertion
in front of the label assertion and so leaves it unwitnessed. The three survivors under both
arms are the three scenarios with no exit tick, which is correct survival.

Nothing disagreed between the ruled behaviour and the rehearsal, so there is no finding to
escalate. Four of the seven scenarios reach an exit and `check_recorded` runs after every
tick, which is why one defect in engine 19 shows up as four failures rather than one.

## SPEC 87 — THE REHEARSAL OF 18, 21 AND 22 — BUILT 2026-09-16

File: `tests/engines/test_trade_chain_rehearsal.py`. Only that file, this file and
`docs/build-log/phase-6/a-platform.md` were written. No engine, simulator, `bootstrap.py`
or `core/` file was edited; the mutations were temporary and restored byte for byte, with
the hash checked each time.

**Fully real upstream, no compromise.** Guard 1, 2, 3, 4, 17; opportunity 5, 6, 7, 12,
13, 8, 9, 10, 11, 14, 15, 16, 18; manage 21, 22, 19. The models are trained in the test
(4 folds, about 17s, once per module). The thresholds are the committed ones, the market
is C's `ScriptedMarket` under B's `PaperBroker`, and everything runs at **fee tier 3**.

| Scenario (test) | Result |
|---|---|
| entry placed → filled on a later tick → stop touched and exited | green |
| timeout reached and exited | green |
| unfilled entry cancelled at `entry_unfilled_window_s` (300s) and not replaced | green |
| `data_guard` block holds a touched stop, `hold_reason` recorded; `close_all` then liquidates the same position under the same block | green |
| a non-`data_guard` block (engine 17 drawdown) does not hold a touched stop | green |
| the same bar evaluated by a restarted process places one entry (engine 18's `open_orders` probe) | green |
| position watched across quiet ticks | green since spec 103 (`178a0a8`); was a strict xfail for finding 1. Marker removed 2026-09-16; with the broker fix reverted (B1) it goes red on `8332.414226591` |

After every tick, `orders`, `positions`, `trades` and `equity_snapshots` are read back and
compared row for row with what 18, 21 and 22 published.

**Mutations:** M1, M2, M3 and M4 were each killed by the one test written for that
property. The equivalent control E1 survived `tests/engines/` and `tests/clients/paper/`
(855 tests), after three runs voided by the known native access-violation fault. The table
is in the build log.

### FOR THE LEAD — two findings, neither fixed, both block a clean spec 82

1. **Every paper fill inflates `peak_equity` by the position's notional; engine 17
   freezes the account two ticks later.** On the fill tick, engine 1's cash is the ledger
   *before* the fill (the broker counts only recorded fills), while engine 21 already
   includes the new position in `positions_value`. Engine 19 adds the two. Measured:
   `8332.414226591` = `5000.00 + 3332.414226591`, then a 40.03% drawdown on the next row.
   Owners: B (engine 21 and `clients/paper/`) and C (engine 19). Repro:
   `test_a_filled_position_is_watched_across_quiet_ticks` with `--runxfail`.
2. **An ERROR anywhere in the opportunity chain leaves the tick unrecorded.** Rule 7
   empties the raising engine's payload, and engine 19 then raises `MissingInputError`
   ("refused ... without publishing a 'reason_code'"). No rejection row, no block record
   and no equity row are written, and engine 17's error count never sees it. Reproduced on
   unmutated engines with engine 16 left out of the chain, so that engine 18 raises.
   Owner: C (engine 19), with a contract question for the lead.

Build-log entries: "FINDING, not fixed (B's lane): every paper fill inflates
`peak_equity`..." and "FINDING, not fixed (C's lane, and a contract question...)".

**Gate, 2026-09-16:** mypy clean (153 files); ruff clean; `pytest tests/ -q`
`8 failed, 3165 passed, 2 skipped, 1 xfailed`, where the 8 are C's known spec 100 red;
`verify.py --phase 6` `1 PASS, 1 FAIL, 9 PENDING`, where the FAIL is `toolchain_green`
from the same 8. Logs: `logs/verify/a87-{mypy,ruff,pytest,verify-phase6}.log`.

**Lead ruling received:** both findings are ruled (specs 103, 104 and 105). The strict
xfail stays until spec 103 lands, and the test file is not to be touched further.

**Choice the lead may overrule:** the broken scenario is a strict `xfail` (the first in
this repository) rather than a red test or a skip. It goes red the day finding 1 is
fixed.

## FOR B AND C — PROSE THAT NOW SAYS THE OPPOSITE OF THE CONTRACT

Routed by the lead 2026-09-16. A is stopping; you are not. **None of this is a code change and
none of it is in A's lane.** Every line below states that `OrderState` carries no quantity or
limit price, which stopped being true when the spec 84 amendment landed.

This is the drift `docs_vocabulary` cannot catch: there is no retired token to grep for. The
sentence is still grammatical, still about a real field, and simply wrong.

**B — `engines/execution/`:**

| File | Lines |
|---|---|
| `src/acsoe/engines/execution/engine.py` | 112, and the `row=None` comment block at 393–408 |
| `src/acsoe/engines/execution/contracts.py` | 164, the `REASON_ENTRY_UNRECORDED` docstring |
| `src/acsoe/engines/execution/README.md` | 100, 112 |
| `tests/engines/test_execution.py` | 310, "it publishes no order row" |

**C — one line:** `src/acsoe/console/format.py:332`, the comment above
`entry_unrecorded_at_exchange`, which says the system "cannot describe it because `OrderState`
carries no quantity or limit price". **The lead's ruling: the reason code keeps its name and
the branch stays**, narrowed — if the exchange answers without `opened_at`, engine 18 still has
no honest `placed_at` and still publishes no row. What needs rewriting is the operator-facing
**prose**, which currently describes an inability that has mostly been fixed. C owns that
sentence and takes it when it returns for the Phase 6 codes.

`src/acsoe/clients/store/client.py:954` mentions `OrderState` and its claim is **still true** —
no change needed there. The lead is fixing `feature-specs/84-the-order-surface-contract.md:22`.

**And the correction the lead made to my own framing, which B needs more than I do.** I wrote
that the amendment "cannot land half-applied and stay quiet" because `mypy --strict` names all
five source sites. That is true of the *source* and false of the three **test** sites —
`tests/engines/test_position_manager.py` 188, 210, 226 — because `mypy --strict` is deliberately
not run over `tests/`. The quiet half is real, and it is found by running the tests, not the
type checker.

## THE `order_book` CONFIG SECTION — spec 80's debt, for spec 96 — HALF ONE LANDED 2026-09-16

Claimed **before any code was written**. Lead-approved `depth: 10`.

| Half | What | Files | State |
|---|---|---|---|
| 1 | `OrderBookConfig` on the model as `OrderBookConfig \| None = None`, `extra="forbid"`, `depth` bounded both ends with a row per bound | `src/acsoe/platform/config.py`, `tests/platform/test_config.py` | **LANDED 2026-09-16** |
| 2 | the lead pastes the YAML | `config/default.yaml` | **LANDED 2026-09-16** (lead) |
| 3 | tighten to required, add `order_book` to `LANDED_SECTIONS`, collapse the landing tripwire's branch | same two files | **LANDED 2026-09-16** |

**The whole landing ran in about an hour and half three was triggered by the tripwire, not by
a message.** I was in another file when the lead pasted; the next routine gate run came back
red on `test_the_order_book_landing_is_in_flight_or_closed`, whose failure message said which
half was missing. That is what the branch was for, and it is gone now the landing is closed.

**One correction I made to my own reasoning**, because it is easy to repeat: I moved
`test_removing_a_phase_5_section_is_refused_at_startup` to `with_phase_6()` believing the
Phase 5 overlay could no longer load with `order_book` required. **False.**
`complete_config_dict()` starts from the *shipped* `config/default.yaml`, so every pasted
section is already in the base and the phase overlays only pin values on top. The move is
defensive, the mutation proving it survives is recorded as equivalent, and the comment in the
file says so.

**The bound, in one line, because it will look arbitrary otherwise.** `depth` is
`0 < depth <= MAX_BOOK_DEPTH` and `MAX_BOOK_DEPTH = 10` is a **copy of `BOOK_DEPTH`** in
`engines/market_data_recorder/contracts.py`, not a Kraken limit. The stream is subscribed at
ten levels a side, so a deeper configuration makes engine 9 walk levels that never arrive —
the book reads thin and nothing says the config caused it.
`test_the_book_depth_ceiling_agrees_with_the_feed` imports both constants and fails if they
diverge; that test is what pays for the duplicate, which exists because `platform/` may not
import upwards into `engines/`.

**FOR C-MODELS (spec 96):** read it as `config.get("order_book.depth")`. While the YAML is
absent that call **raises** — `order_book` is a section, not a leaf, so the walk descends into
the `None` and you fail closed rather than reading a depth of zero. Do not add a fallback.

## SPEC 84 AMENDMENT — `OrderState` gains `qty` and `limit_price` — CLAIMED 2026-09-16

Operator-approved amendment, handed to A by the lead. Claimed **before any code was written**.
Nobody else may touch `src/acsoe/clients/kraken/contracts.py` while this is open.

| What | Files I will touch | State |
|---|---|---|
| `OrderState.qty` required, `OrderState.limit_price` optional; `state_dict()`; README; the `a_state`/`a_filled_state` helpers and the new coupling tests | `src/acsoe/clients/kraken/contracts.py`, `src/acsoe/clients/kraken/README.md`, `tests/clients/kraken/test_orders.py` | **LANDED 2026-09-16** |

**Why**, in the operator's words: *an order that cannot be cancelled because nothing recorded
enough to identify it is an unmanaged exposure, and that is the failure invariant 8 exists to
prevent.* B found it building engine 18 — `_already_placed` finds the order at the exchange,
cannot describe it, and publishes no row, so nothing will ever cancel it.

**Out of my lane and not touched by me:** B's `clients/paper/broker.py` (5 construction sites)
and `tests/engines/test_position_manager.py` (3). Listed in full in the report to the lead.

### WHAT LANDED — FOR B, the new `OrderState`

```python
class OrderState:
    userref: UserRef
    order_id: str
    status: OrderStatus        # "resting" | "filled" | "cancelled" | "rejected" | "expired"
    qty: Money                 # NEW, REQUIRED, > 0
    limit_price: Money | None = None   # NEW, > 0 when present; absent for a market order
    filled_qty: Money          # >= 0, and NEVER greater than qty
    avg_fill_price: Money | None = None
    fee: Money                 # >= 0
    opened_at: int | None = None       # NEW. Kraken's `opentm`, microseconds.
                                       # Absent = the exchange did not say.
    closed_at: int | None = None
```

Four things that will refuse your code if you do not know them.

1. **`qty` is required.** `mypy --strict` names every site that omits it —
   `clients/paper/broker.py` lines 516, 609, 650, 684, 691 — and
   `tests/engines/test_position_manager.py` (188, 203, 217) is the same change, unchecked by
   mypy. The missing-field refusal is pydantic's `Field required`.
2. **A sixth coupling: `filled_qty` may not exceed `qty`.** New, only checkable now that `qty`
   is here, and it is the one most likely to surprise the ledger. `filled_qty == qty` is the
   ordinary full fill and is explicitly allowed, with its own test.
3. **There is no `order_type` on `OrderState` and there deliberately is not going to be one.**
   `limit_price is not None` **is** the order type: a market order has no limit price, a limit
   order always has one, so the discriminator is total and a second copy of it is one more
   thing that can disagree. Derive the type from presence when you build the row.

4. **`opened_at` is optional and coupled to nothing** — a resting order may carry one, a
   terminal order may lack one. The single rule: when both are known, `closed_at` may not be
   before `opened_at`. **Equality is allowed**, because in paper one injected clock reading
   stamps both and a stricter bound would refuse every simulated marketable order.

`state_dict()` now carries `"qty"`, `"limit_price"` and `"opened_at"` — if you assert on a
whole dict anywhere, those are the three keys to add.

**The gap is now closed as far as it honestly can be.** The engine-19 row needs twelve fields.
`OrderState` supplies six; `pair`, `side`, `order_type`, `oflags` and `intent` are structurally
known to engine 18 (invariant 8 makes every entry a post-only buy limit on the candidate's
pair, and a `userref` on a different pair already raises as a collision), so filling those from
what the engine knows is not fabrication. What is left is one case: **the exchange reported no
`opentm`.** Keep the existing fail-closed answer there — no row, `entry_unrecorded_at_exchange`,
`userref` published. Do not substitute a clock reading.

**And the lead's ruling you have to implement, because the model cannot:** engine 18 asked for
a post-only buy **limit**, so an `OrderState` that comes back with **no `limit_price`** is the
exchange contradicting the placement, not a market order. Refuse to record that row. The model
has no `order_type` and therefore cannot see it; you have the `OrderRequest` and can.

## SPEC 86 — THE WIRING AND THE BOOK CUTTER — LANDED 2026-09-16

### Step 1: the paper broker is wired in, paper mode only

`cli/engine.py::build_clients` wraps `KrakenClient` in B's `PaperBroker` when
`config.mode == "paper"`, and in no other mode. **No mock was needed** — B's
`clients/paper/broker.py` landed while I was on spec 85, built against my spec 84 contract
unchanged, so the wiring went straight onto the real constructor:
`PaperBroker(real, *, store, config, clock)`.

Written as `== "paper"`, **not** `!= "live"`. The two read the same today and stop reading the
same the moment a fourth mode exists, at which point the negative form wraps it silently. There
is a `replay` case in the test parametrisation for exactly that, and mutation P3 — the negative
form — is killed by the replay case *alone*.

Every assertion goes through `build_clients`, never a hand-built `Clients`. That is A-2's
Phase 2 lesson: a tripwire written to fire when the daemon was wired to real clients stayed
green through exactly that change, because it built the empty `Clients()` itself.

**This is also where spec 84's owed seam test landed.**
`test_an_order_in_paper_mode_never_reaches_the_live_client_s_refusal` has no double on either
side — B's real broker, built by the real `build_clients`, called with A's real `OrderRequest`
through A's real protocol. It asserts on **where the failure comes from**: with no credentials
the call fails either way, and the live client's refusal names Phase 8, so the absence of that
string is the proof the broker answered. An `isinstance` check against `OrderClientProtocol`
cannot show it — a `runtime_checkable` Protocol only checks the four names exist, and the bare
`KrakenClient` has all four; they are the ones that refuse.

### Step 2: `scripts/cut_book_fixture.py` — FOR C, spec 96

```
python scripts/cut_book_fixture.py \
    --pairs BTC/USD XRP/USD \
    --from 2026-09-15T04:00:00Z --to 2026-09-15T04:10:00Z \
    --out tests/fixtures/book_sample.jsonl --write
```

Dry run without `--write`. Exit 0 on success, **2 on a refusal** with the reason on stderr.
Also takes `--source-dir` (default `data/raw`) and `--prefix`.

**It chooses nothing** — not the pairs, not the window, not the destination. Those are C's.

**Output shape.** Line 1 is a header object carrying `_fixture`, the window (`[from, to)`), the
pairs, the source files, per-pair counts by frame type, and a **sha256 of the body**. Every line
after it is a recorded `book` frame **byte-for-byte as recorded** — the original bytes, never
re-serialised, because a Kraken book frame carries a checksum over what the exchange sent.
Written as bytes, no CRLF, because `tests/fixtures/` is `-text` and has no clean filter.

**Five refusals, each naming what it found:**

1. an output path inside `data/raw/` (invariant 11);
2. **a recorded gap intersecting the window** — tested on the gap's *interval*, not the
   marker's timestamp, because a marker is written at reconnect and a break that started inside
   the window and ended after it has its marker outside entirely;
3. a window the archive does not cover at both ends — the open gap no marker describes;
4. more than one archive file contributing — the doubled recording from 2026-09-09T13:19, which
   would give a slippage walk twice the depth;
5. a named pair with no book frame in the window.

**Confirmed on the real archive, read-only, dry run.** 2026-09-11, two files, 3.7 GB, 3m02s,
and it refused: no BTC/USD book frame in that window. Expect minutes, not seconds — the window
is short but the scan is the whole file.

## SPEC 85 — `trade_ranges`, FOR B — LANDED 2026-09-16

`state["market_sensor"]["trade_ranges"]`, per pair, exactly four keys:

```python
{"BTC/USD": {"low": "99.25", "high": "101.50", "trades": 3, "since_ts": 1772323740000000}}
```

`low` and `high` are exact decimal strings, `trades` an int, `since_ts` microseconds. No `pair`
inside the value — the map key carries it and a second copy is one more thing that can disagree.

**Four things you need to know before you read it in engines 21, 22 and the broker:**

1. **A pair with no trade since the previous tick is ABSENT.** Not `{"trades": 0}`, not a copied
   price. `TradeRange` refuses `trades=0` at construction, so it cannot happen. Your code gets a
   `KeyError` for a silent pair, which is a question you have to answer — a range of nothing at
   a copied price would tell a barrier check the market touched it.
2. **It is trades, not quotes.** A book that quoted 100 and never traded there has no range at
   100.
3. **The window is `(since_ts, now]`** — half-open at the bottom, so consecutive ticks tile
   without overlap and no trade is in two ranges. A trade exactly on `since_ts` belongs to the
   *earlier* tick.
4. **`trade_ranges` is `{}` on the first tick of a run**, including the first tick after a
   restart, because there is no previous tick to measure from. Engine 3 reads
   `state["cycle_id"]` to know this — it is stateless across cycles and that is the only place
   the answer exists.

**`since_ts` is `context.previous_now`** — the *real* stamp of the previous tick, not `now`
minus `loop_tick_s`. The lead added that field to `EngineContext` this session after I raised
the hole: under the arithmetic, a loop that ran late left the trades in the overshoot in **no**
range at all, and a stop touched there was missed by engines 21 and 22. With the real stamp a
late loop produces a **longer** range instead of a hole. (`bar_closed` still uses `now -
loop_tick_s` and is still right to: it asks about an *index* and fires once however late the
loop ran. An interval is the different case.)

Evidence: 38 tests in `tests/engines/test_market_sensor.py` (16 new), **13 mutations, 12 killed,
1 checked negative** (an equivalent mutant, filed with its non-equivalent twin rather than as a
survivor). Sweep scoped to the three files in A's lane that drive engine 3 for real so an
incidental kill would be visible — none was. The sweep was **re-run from scratch** after the
rework, because a mutation table for code that no longer exists reads as coverage. Build log has
both tables and the red messages.

**The mutation worth knowing about: N12** puts the `now - loop_tick_s` arithmetic back, and
exactly **one** test out of thirty-eight objects. That is the honest shape of the defect — a
range that is correct on every tick where the loop ran on time and silently short on the ones
where it did not — and a reminder that a green suite says nothing about a defect whose whole
nature is that it appears only under a condition no other test creates.

## SPEC 84 — THE ORDER SURFACE, FOR B — LANDED 2026-09-16

**This is the contract. It is on disk, it is green, and it will not change without a message to
B first.** `src/acsoe/clients/kraken/contracts.py`, exported from `acsoe.clients.kraken`.
Spec 88's broker implements `OrderClientProtocol`; engines 18, 21 and 22 call it through
`context.clients.kraken`.

```python
from acsoe.clients.kraken import (
    OrderAck, OrderAckStatus, OrderClientProtocol, OrderRequest,
    OrderSide, OrderState, OrderStatus, OrderType,
    TERMINAL_ORDER_STATUSES, USERREF_MAX, USERREF_MIN,
)

class OrderClientProtocol(Protocol):
    async def add_order(self, request: OrderRequest) -> OrderAck: ...
    async def cancel_order(self, userref: int) -> OrderState: ...
    async def query_orders(self, userrefs: Sequence[int]) -> tuple[OrderState, ...]: ...
    async def open_orders(self) -> tuple[OrderState, ...]: ...
```

Async, like every other call on the client. `platform/aio.py` is still the one place a
synchronous engine runs an async client call.

### The three models

Every one is `frozen=True, extra="forbid"`; money is `Money` (`Decimal` in, a `float`
**refused** not coerced); each has `state_dict()` rendering money as strings for
`EngineResult.data`, which refuses a `Decimal` outright and silently accepts a `float`.

```python
class OrderRequest:
    pair: str
    side: OrderSide            # "buy" | "sell"
    order_type: OrderType      # "limit" | "market"
    qty: Money                 # > 0
    limit_price: Money | None = None   # > 0 when present
    post_only: bool            # NO DEFAULT — you must state it
    userref: UserRef           # USERREF_MIN .. USERREF_MAX, inclusive

class OrderAck:
    userref: UserRef
    order_id: str
    status: OrderAckStatus     # "resting" | "filled" | "rejected"
    reason: str | None = None  # present and non-empty iff rejected

class OrderState:                      # SUPERSEDED — see the amendment above; it now
    userref: UserRef                   # also carries `qty` (required) and `limit_price`
    order_id: str
    status: OrderStatus        # "resting" | "filled" | "cancelled" | "rejected" | "expired"
    filled_qty: Money          # >= 0
    avg_fill_price: Money | None = None
    fee: Money                 # >= 0
    closed_at: int | None = None       # microseconds since epoch, like fetched_at
```

### The couplings, because they will refuse things if you do not know them

Each is enforced at construction and each has a passing test and a failing test.

- **`OrderRequest`** — a `limit` order **must** carry `limit_price`; a `market` order **must
  not**; `post_only=True` on a `market` order is refused (it is Kraken's `oflags=post`, a
  limit-order flag, and a market order always takes). `market` exists only because invariant 14's
  liquidation exits as a taker — engine 18 must never construct one, and that is asserted in
  engine 18's own tests, not in mine.
- **`OrderAck`** — `reason` is present and non-empty **exactly when** `status` is `rejected`,
  and absent otherwise. A post-only order that would have crossed is the ordinary rejection and
  it names that cause.
- **`OrderState`** — `avg_fill_price` present **exactly when** `filled_qty > 0`; an order that
  filled nothing paid **no** fee; `status == filled` requires `filled_qty > 0`; `closed_at`
  present **exactly when** the status is terminal (`TERMINAL_ORDER_STATUSES`, i.e. everything
  except `resting`).

**Two shapes that are deliberately allowed**, both with tests, because they are the ones the
broker and engine 21 need: a **partially filled order still `resting`** (fill, price, fee, no
`closed_at`), and a **partially filled order `cancelled`** at the unfilled-entry window (fill,
price, fee, `closed_at`). If you need a shape these refuse, message me — it is one line on my
side, not a workaround on yours.

### Three things about the design that will save you a round trip

1. **`userref` is the key everywhere, not `order_id`.** `cancel_order` and `query_orders` both
   take `userref`. Invariant 8 makes it the idempotency token: the system chooses it *before*
   the order exists, so it is the only identifier that survives a placement whose answer never
   came back. `order_id` is the exchange's, arrives afterwards, and is for reconciliation.
   The bound is one shared `UserRef` annotation on all three models, so the request cannot
   refuse a value the ack would accept.
2. **A call that cannot be completed raises; it never returns an empty result.** Invariant 3.
   An `open_orders()` answering `()` during an outage would tell engine 21 there was nothing
   resting to cancel.
3. **Nothing in the models knows a fee, a minimum, a tick size or a precision.** Sizes and
   prices arrive **already rounded** by the caller using the pair's own `lot_decimals` and
   `pair_decimals` from `AssetPairs`, rounded **down** for quantity. The contract will not do
   it for you and will not check it.

### What the live client does

`KrakenRestClient` and the `KrakenClient` facade implement all four and **refuse**, raising
`KrakenUnavailableError` naming the method and Phase 8, before the limiter, the nonce, the
signature or any request. `rest.py` owns the refusal; the facade forwards, so there is one copy
to remove in Phase 8. There is no flag that turns it off. `rest.ORDER_CALLS` is the list, and a
test compares it against the protocol's own attributes so a fifth call cannot be added without
a refusal.

`KrakenClientProtocol` (the four read-only calls) is unchanged and is **separate** from
`OrderClientProtocol`, so a consumer that only reads the market cannot be handed an object that
can place an order — and so your broker can implement one and forward the other.

### Evidence

60 tests in `tests/clients/kraken/test_orders.py`; 149 in `tests/clients/kraken/`, green.
`mypy --strict src/ scripts/` clean on 131 files, `ruff check src/ tests/ scripts/` clean.
**Fifteen mutations, fifteen killed, no survivors**, each restored from a byte copy with the
sha256 compared in the same statement and each verdict naming its killing test — table and red
messages in `docs/build-log/phase-6/a-platform.md`.

**What is not proven yet, and it is yours and mine jointly.** There is no consumer of this
contract on disk, so every test of it is a test of my own models and my own refusal. Phase 4's
lesson — A built engine 23 against `label_bars(...)`, agreed by message, which **never existed**,
and nothing went red because everything drove a double — applies exactly here. The seam test
with no double on either side is owed by **spec 86** (the `build_clients` wiring) and **spec 87**
(the rehearsal), both of which run your real broker against this real protocol. Until one of
those lands, a green test of the order surface is a test of a mock.

## RESUMED 2026-09-13 09:50 — spec 61's `training` section, then spec 78

Three things were asked of A this session, in order: the `training` config section, spec 78
(engine 23 streams the labelled slice), and an assessment of C-2's engine 3 `missing_bars`
finding.

**1. The `training` section — DONE, both halves closed.** `TrainingConfig` with `num_trees`,
`learning_rate`, `num_leaves`, `min_data_in_leaf`, `extra="forbid"`. Landed optional, the lead
pasted the YAML about twenty minutes later, my two-halves test went red on the paste exactly as
intended, and the field is now required with `training` in `LANDED_SECTIONS`. `num_leaves` is
bounded `> 1` rather than `> 0` deliberately: a single leaf is a model that returns the base
rate for every input, so it would report a Brier equal to the base-rate Brier — the comparison
spec 59 decision 4 made primary — and read as "no edge" rather than "no model".

A mutation survived the first version and the gap is worth remembering: the section shipped
with a parse test and a `num_leaves` test and **no rows in the `BAD_VALUES` table**, so
loosening `learning_rate` from `(0,1)` to `[0,1]` broke nothing. Seven rows added. Fill in the
mechanical constraint table first, write the interesting test second.

**2. Spec 78 — DONE, measured on the full archive.** Engine 23 no longer
accumulates every labelled row: it asks each pair's frame for its height, hands the frame
straight to a `_SliceWriter` that appends it as its own parquet row group, and releases it.
The schema is established by the first pair and later pairs are cast to it, because
`label_frame` infers dtypes per pair and a column that is all-null for a thin pair would infer
differently; the writer closes in a `finally`; and the per-pair counts are cross-checked
against the rows actually written, raising if they disagree.

Also fixed in the same function: the slice filename was stamped from `datetime.now(tz=UTC)`,
a direct clock read inside an engine that invariant 9 forbids. It now reads `context.now`.
The path convention is unchanged.

Also pinned: the parquet is written with zstd, because pyarrow's writer defaults to snappy
where `polars.write_parquet` used zstd, and that alone moved the full slice from 429 MB to
667 MB for byte-identical rows. One row group per pair, which is what lets a reader skip
pairs by the `pair` column's per-group statistics.

**The full archive, streamed: 20,331,237 rows, peak 23.6 GB, 31 minutes**, against the same
20,331,237 rows at 51.9 GB before. The labels are identical row for row, not merely the total:
target 4,857,764, stop 10,424,046, timeout 5,049,427 in both runs, a 23.89% target rate that
matches the base rate spec 59 quotes.

Peak memory over a 24-pair scratch archive, each run in its own process, the comparison run in
both orders as the control:

| | accumulate | stream | reader alone |
|---|---|---|---|
| accumulate first | 792.9 MB | 430.3 MB | 348.6 MB |
| stream first | 800.1 MB | 404.1 MB | 350.3 MB |

**5. The `missing_bars` seam work under the lead's 11:05 ruling — DONE.** One sentence each
in `engines/market_sensor/README.md`, `engines/market_sensor/contracts.py`,
`engines/data_guard/README.md` and `engines/data_guard/contracts.py` now says the same thing:
`missing_bars` is **bars in which no subscribed pair traded at all**, which is feed-level
silence and a real data fault; a single pair's hole is ordinary and is the feature layer's to
mark. Engine 3 grew no per-pair map and nothing was renamed.

The seam test has **no double on either engine** — engine 3 runs for real over a fake stream,
`data_guard` runs for real over what engine 3 published — because the seam was previously
tested by neither side. Two mutations: replacing the union with a per-pair reading goes red,
and **only one test of 43 fails**, which is the finding rather than the pass; deleting the
missing-candle condition goes red across six.

**One thing still with the lead:** `REASON_PROSE["missing_candle"]` reads "A decision bar has
no candle", which under the ruling is misleading — it sounds like one pair's hole. Proposed
wording sent to `main`; `console/format.py` is C-2's to land.

**3. The `missing_bars` assessment — DONE, reported to the lead, no code changed.** C-2 is
right that the field pools every pair, and the consequence is worse than lost attribution:
because the pooled set is a union, a bar counts as missing only when **no pair traded in it at
all**, so past a handful of pairs the field is empty on essentially every tick and
`data_guard`'s missing-candle block can never fire. Measured, not read. Neither side's tests
can see it: engine 3's gap tests use a single pair, and `data_guard`'s tests build the tuple
themselves. My proposal is to change *less* than was asked — engine 3 should not grow a
per-pair map, because spec 64's amendment already has engine 5 deriving it from the candles
engine 3 already publishes — and to get a ruling on whether the gate condition still means
anything at this pair count. Waiting on the lead.

**4. Spec 79 — DONE, 3.57 GB over the full archive.** `ArchiveReplay` holds paths
rather than rows. It used to keep two copies of the whole archive — every pair's parsed rows
as dicts and the same data again as polars frames, both eagerly in `__init__` — on a path that
reads one pair at a time and never touched the dicts at all. Now `frame(pair)` reads that file
and builds that frame when asked and keeps neither, `frames()` is a generator in
`report.pairs` order, and `bars()` goes through the same per-pair read. The replay-level report
sums the per-pair `ArchiveReport`s the loader already produced instead of counting rows a
second time, so construction reads each file once rather than twice.

| 24 pairs, both orders | before | after |
|---|---|---|
| construction only | 348.6 / 350.3 MB | 136.8 / 143.0 MB (5.0s to 1.5s) |
| full engine 23 run | 430.3 / 404.1 MB | 219.5 / 218.4 MB |

The full 234-pair run: **20,331,237 rows, peak 3,650.9 MB, 29.4 minutes.** The three
measurements of the same work, each in its own process on this machine:

| | peak | wall |
|---|---|---|
| before spec 78 | 51.9 GB | 36 min |
| spec 78 (streamed writer) | 23.6 GB | 31 min |
| spec 79 (lazy reader) | **3.57 GB** | 29 min |

The labels are identical across all three: target 4,857,764, stop 10,424,046, timeout
5,049,427. Spec 79 asks for under 5 GB.

**It broke one line in C-2's trainer, `mypy --strict` caught it, and C-2 has already fixed it
better than I suggested** — `_archive_frames` now calls `frame(pair)` once per wanted pair
rather than materialising the archive to throw most of it away.

### The open item on spec 78 — CLOSED by spec 79

**Spec 78's Check When Done asks for a full-archive peak "well under a tenth of 51.9 GB",
about 5 GB. The measured result is 23.6 GB, and the gap is not in the part spec 78 changed.**
`ArchiveReplay.__init__` keeps the whole archive in memory **twice** and eagerly: `self._rows`,
every pair's parsed rows as Python dicts, and `self._frames`, the same data again as polars
frames, both for the life of the run. Engine 23 reads only `frame(pair)`; `_rows` exists for
`bars()`, which the backtest never calls. On the 24-pair archive the reader alone is 81% of the
streaming peak.

**The next step, for whoever takes it:** make the reader lazy — load one pair's frame when it
is asked for, release it after, and stop keeping a second copy nothing in this path reads.
`research/replay.py` is A's. It is **not** in spec 78's Implementation steps, so it is reported
rather than done; it needs an amendment to 78 or its own spec. My estimate is that it takes the
full run close to a gigabyte, because nothing would then be resident but one pair.

Worth carrying forward as a shape: **the spec's Implementation steps and its acceptance number
disagreed**, and only measuring showed it. The steps describe the writer; the number can only
be met by also changing the reader. Reporting the number the change actually achieves is the
honest answer, and quietly widening the change to hit it would have been the other one.

## HANDOFF — lane A at session close, 2026-09-13 ~03:00

Written for a session that has never seen this one. Everything below is the state on disk,
not an intention.

**Spec 61 is done, all four parts, committed** (steps 3 and 4 at `02f8aad`; step 1 and the
dependency move in the commits before it). Four gates were green at the time of the last run:
2102 passed and 3 skipped, `mypy --strict src/ scripts/` clean on 106 source files,
`ruff check src/ tests/ scripts/` clean, and `verify.py --phase 5` with its only FAIL in
another lane. Detail is under "SPEC 61 IS COMPLETE" below and the gate output is under
Verification.

**Nothing in lane A is half-finished.** No file of mine is mid-edit and no change is
uncommitted except my own build log, which the lead commits. The tree is coherent.

### The one thing that was asked for and not started: a `training` config section

The lead asked at 02:15 for `training` (`num_trees`, `learning_rate`, `num_leaves`,
`min_data_in_leaf`) for the LightGBM hyperparameters, field first and then the lead pastes the
YAML. **It is not started** — no field, no YAML, nothing to back out. The stop order arrived
before it did and said not to begin it.

Whoever picks it up: it is the same two-halves landing as the other eight sections and the
pattern is in `platform/config.py` above `class SeedsConfig`. Declare the section
`TrainingConfig | None = None`, tell the lead, let the YAML land, then tighten to required in
one change — because `extra="forbid"` means a required field with no YAML key stops the
committed config parsing, which takes every test in every lane with it. There is a test for
that dance already: `test_the_phase_5_landing_is_closed_and_every_section_is_required` in
`tests/platform/test_config.py` asserts every section in `PHASE_5_SECTIONS` is both present in
the YAML and required on the model, so adding `training` to that tuple is what makes the
tripwire cover it.

### The full-archive run FINISHED, exit 0 — and my earlier diagnosis of it was wrong

It completed during the wind-down, after about 36 minutes: `backtest OK`, **exit 0**, and a
429 MB parquet at `data/derived/labelled_research-20260913T000430950753_20260913T004003Z.parquet`
carrying **20,331,237 labelled rows** over 13 columns. So spec 61's acceptance check is proven
against the committed config and the real archive, not only against the 400-bar scratch run.
Nothing needs killing; PID 42016 exited on its own.

**Correction, and it matters because the wrong version is already in
`feature-specs/PHASE-5-TASKS.md`.** I reported a mysterious divergence "in the multi-pair path"
and a run holding an order of magnitude more memory than the code should need. That was wrong,
and the error was mine: I was reasoning from a Phase 4 fact that had stopped being true.
`data/historical/` held **3 pair files and 859,248 bars** when I built it on 2026-09-11. It
holds **234 CSVs and 20,443,861 bars** — 47 GB — today.

With the real row count everything reconciles and there is no anomaly. My per-pair measurement
of ~3 KB per bar was correct; 20.3M rows at that rate is about 60 GB and the process peaked at
51.9 GB. Runtime likewise: 2,089 CPU-seconds over 20.3M rows is ~0.10 ms per bar, faster than
the 0.44 ms the small slices showed, because those paid fixed per-pair setup over a few tens of
thousands of rows.

**What remains true, narrowed to something cheap to fix.** Engine 23 accumulates every labelled
row of every pair in one Python list and writes a single parquet at the end, so it needs roughly
50 GB of memory to produce a 429 MB file. That should be streamed — one parquet per pair, or
appended row groups — and it is worth doing **before spec 67**, because the dataset every model
in this phase trains on comes out of this command and on a smaller machine the failure is a
killed process rather than a message. `research/backtest.py` is A's. It is an ordinary defect
with an obvious fix, not a hunt.

The cheap check I skipped was `ls data/historical/*.csv | wc -l`. The benchmark control I did
apply — running the comparison in reverse order — was sound and proved the per-bar numbers
honestly, and could not possibly have caught that I was multiplying them by the wrong N. A
control on a measurement says nothing about the assumption it is compared against.

### Open questions I am leaving

1. **Is `acsoe research` meant to replay the whole archive every time it is run?** It does
   now, by default, with no way to name a subset. That is what spec 61 asked for and it makes
   C's engine 20 loop expensive: `acsoe research --digest ...` runs engine 23 first, every
   time. A `--only <engine>` or a bar limit would fix it and neither is in any spec. The lead's
   call.
2. **Nothing has ever run engine 20 through `acsoe research`**, because the class does not
   exist. The registration resolves it by name so it needs no edit from A, but the first real
   run of that path will be the first test of it. The seam is
   `TournamentEngine(*, digest_path: Path | None = None)`, agreed with C.

## Current Task

**Phase 5. Claimed: spec 61**, all four parts, per `feature-specs/PHASE-5-TASKS.md` and
ownership rule 5. Claimed 2026-09-13, before any code was written. It is A's only spec this
phase and every part of it blocks C.

The four parts, in the order they land, because the order is what unblocks other people:

1. **Config fields, before any YAML.** Sections `models`, `features`, `macro`, `prediction`,
   `anomaly`, `skeptic`, `regime` and `scout` on the config model, every one
   `extra="forbid"`, plus the validator refusing `features.max_lookback_bars` above
   `market_sensor.published_bars`. The lead pastes the YAML afterwards; nothing in this spec
   writes `config/default.yaml`.
2. **Dependencies.** `lightgbm`, `scikit-learn` and `shap` out of the `research` extra and
   into the base install; `hmmlearn` and `statsmodels` stay in the extra.
3. **The models root.** `platform/paths.py` creates `models/` beside `data/` and `logs/`;
   `cli/engine.py` and `cli/research.py` pass it into B's `StoreClient` (spec 62).
4. **`acsoe research` runs the chain** against a real replay-mode `EngineContext` instead of
   listing engine names, one line per engine with its status and reason, non-zero exit on any
   `ERROR`.

**Landing rule, and it is the reason part 1 ships alone and first.** Every section is
`extra="forbid"`, so a YAML key without its model field is refused at load and a *required*
model field without its YAML key makes the committed `config/default.yaml` fail to parse —
taking `scripts/verify.py` and every test in every lane that reads the shipped config with
it. The new sections therefore land **optional** (`Section | None = None`), exactly as
`kraken.cache_ttl_s` did in Phase 3, and are tightened to required once the lead's YAML is
in. While a section is `None`, `Config.get("prediction.di_window_days")` *raises* — the walk
has to descend into the `None` — so a reader fails closed during the window. The three
operator leaves inside those sections do **not**: `Config.get` returns `None` for an absent
leaf, which is the spec 58 finding, and each of them says so in its own docstring.

### SPEC 61 IS COMPLETE — all four parts, 2026-09-13

Written by the instance that routes as `A-2`, which the lead's stand-down notice in
`feature-specs/PHASE-5-TASKS.md` makes the live one.

**Part 1 — the config fields, and both halves of the landing are closed.** Eight sections on
`Config` in `src/acsoe/platform/config.py`, every one `extra="forbid"`: `models`, `features`,
`macro`, `prediction`, `anomaly`, `skeptic`, `regime`, `scout`. They were declared
`Section | None = None` while the lead's YAML was in flight and are **required** now that it
has landed, so deleting a section refuses at startup by name instead of surfacing as a
`ConfigKeyError` from inside a gate three chains into a tick. The cross-section validator
refuses `features.max_lookback_bars` above `market_sensor.published_bars` — 192 against 200
today — because a feature wanting more history than engine 3 publishes is NaN live and a
number in replay, which is a divergence nothing else would show.

**The five keys absent by ruling stay optional leaves**, and every reader has to refuse the
`None` by name: `prediction.di_percentile`, `anomaly.threshold_percentile`,
`skeptic.veto_threshold`, the three `models.*_run_id`, and `scout.rank_feature`.
`Config.get` returns `None` for an absent leaf and *raises* only for a key the model does not
declare. A leaf read as zero is a gate that has been turned off, not a conservative default.

**A trap worth repeating to whoever next edits the YAML:** those keys must be **absent**, never
written as `null`. `_refuse_nulls` treats any null in `config/default.yaml` as OPERATOR
REQUIRED and stops the process naming it. Absent and null are one character apart in a diff and
behave in opposite directions; there is a test per key.

**Part 2 — dependencies.** `lightgbm`, `scikit-learn` and `shap` are base dependencies in
`pyproject.toml`; `hmmlearn` and `statsmodels` are what is left in the `research` extra. The
comment says why the line the extra draws is live-loop-versus-offline rather than
ML-versus-not: engines 8, 13 and 15 import all three on the opportunity chain, so an extra a
daemon cannot start without is a base dependency that a fresh clone meets as an `ImportError`
from inside a gate. `tests/platform/test_packaging.py` asserts the split both ways and imports
all three for real — deliberately not through `pytest.importorskip`, which *skips* a
`ModuleNotFoundError` and would turn a regression green under a reason string that is no longer
true.

**Part 3 — the models root.** `platform/paths.py` creates `models/` beside `data/` and `logs/`,
and `cli/engine.py` and `cli/research.py` hand it to B's `StoreClient` as
`models_dir=paths.models` — the seam agreed with B by message before either of us built it, and
it landed on both sides unchanged. Beside `data/` rather than inside it, because `data/` holds
rebuildable output and a trained artefact is not rebuildable from anything the archive carries.
The Phase 0 test asserting `models/` is *not* created is replaced by its opposite, with the
reason in the docstring rather than in a commit message.

**Part 4 — `acsoe research` runs the chain.** It builds a `SystemClock`, a replay-mode
`EngineContext` carrying the parsed `Config`, and a real `StoreClient` with the artefact root
and migrations applied, then runs each offline engine's `process` in registry order and prints
one flushed line per engine with its status and reason. `ERROR` exits 1, a config refusal exits
2 like `acsoe engine`, everything else 0. `kraken` and `recorder` are `None` in the offline
client set on purpose: nothing offline reaches the exchange, and invariant 11 means a replay
writes no archive line.

**Engine 20 needs no registration line from anyone.** `acsoe research` resolves
`acsoe.engines.tournament.engine.TournamentEngine` by name when it builds the chain, so C's
class registers itself after engine 23 the day it lands, and `--digest` is threaded into it as
`digest_path`. A missing package returns `None` by reading `exc.name`; a *broken* one raises,
because those are two different facts and answering the second as "not written yet" is how
engine 20 would vanish from the chain silently. A constructor that does not accept
`digest_path` raises naming the seam.

### Evidence

- `acsoe research --config config/default.yaml` run for real against a 400-bar archive in a
  scratch root: `backtest OK`, exit 0, a labelled parquet in `data/derived/`, a migrated
  database, and an empty `models/` created beside them. **The full-archive run finished too:**
  `backtest OK`, exit 0, about 36 minutes, 20,331,237 labelled rows written to a 429 MB parquet
  over the real 234-pair, 20,443,861-bar archive. Both halves of the evidence are in.
- Twelve mutations against `platform/config.py`, three against the packaging split, each
  restored from a byte copy and verified by sha256 in the same statement. Eleven of twelve
  killed; **one real survivor**, a default asserted against a fixture that supplied it, fixed
  and then killed. Every red message is in `docs/build-log/phase-5/a-platform.md`.

### Two things the lead should know that are not mine to change

1. **`config/default.yaml` spells the live BTC macro pair `BTC/USD`.** Kraken's WebSocket v2
   names it `XBT/USD`; the archive spelling `XBTUSD` beside it is right. Flagged, not touched.
2. **`mypy --strict src/ scripts/` was checking nothing for several hours today** and saying
   `Found 1 error`. `follow_imports = "skip"` silences a module's source but not its stub, so
   the first `import numpy.typing as npt` in `src/` pulled numpy's stubs back in and the PEP 695
   syntax error in them aborted the whole run. Fixed in `pyproject.toml` with
   `follow_imports_for_stubs = true`: 106 source files checked, passing, and the 3.11 floor
   kept. Build log has it.

### Two A sessions are in this lane, and the lane has not been assigned

Recorded by the instance whose messages route as `A`; the claim above is `A-2`'s. Both of us
read the brief for spec 61 and both started. Nothing is lost and the tree is consistent, but
the split of the remaining work is the lead's to make and it has been asked for.

**What is on disk right now, so neither of us has to guess again.** Step 1 is complete in
`src/acsoe/platform/config.py` — one copy of each of the eight sections, no conflict. Its tests
are in `tests/platform/test_config.py`: there were briefly **two** Phase 5 blocks, one from each
of us, both declaring a module-level `PHASE_5_SECTIONS`. I deleted mine, lines 839 to 1259, and
kept the earlier and stronger one. Steps 2, 3 and 4 are untouched by either of us.

**The failure mode is worth carrying forward past this phase.** Duplicated module-level names
do not collide in Python, they shadow — so the surviving block's tests were being driven by my
dict and mine by nothing anyone intended, and exactly one assertion out of eighteen was
sensitive enough to notice. Everything else stayed green while asserting against the wrong
subject. The next double-landing will look like that rather than like a merge conflict.

### Gate state, measured 2026-09-13, not from a summary line

| Gate | Result | Whose |
|---|---|---|
| `pytest tests/ -q` | **green** — 2,100 passed, 3 skipped, 193s | — |
| `mypy --strict src/ scripts/` | **RED** — aborts, checks nothing | mine to answer, C's trigger |
| `ruff check src/ tests/ scripts/` | **RED** — 1 error, `RUF100` in `scripts/verify.py:8025` | C's file |
| `scripts/verify.py --phase 5` | running at the time of writing | — |

The mypy failure is the one that matters and it is not a type error:

```
.venv\Lib\site-packages\numpy\__init__.pyi:737: error: Type statement is only supported in
Python 3.12 and greater  [syntax]
Found 1 error in 1 file (errors prevented further checking)
```

`errors prevented further checking` — the gate returns **no answer rather than a wrong one**,
so `src/` is currently unchecked and only the last line says so. Full diagnosis in the build
log. The bound is `numpy<2.5`, measured against the 2.2.6, 2.3.0 and 2.4.0 stubs rather than
assumed; C recommended `<2.3`, which is two minor versions stricter than the defect requires.

**It needs a `pip install` in the shared venv, not only a `pyproject.toml` edit**, because mypy
reads the installed numpy. That lands on B and C mid-run, so it has been put to the lead to
sequence behind a team stop rather than done underneath them. The file edit is `A-2`'s, since
it has claimed step 2 and is going into `pyproject.toml` anyway.

### Seams agreed by message, so neither A session re-litigates them

- **B, spec 62.** `StoreClient(db_path, models_dir=...)` — `models_dir` is the second
  positional-or-keyword parameter, defaulting to `None`, so every existing construction site
  keeps working. `platform/paths.py` still creates `models/` at startup and both `cli/engine.py`
  and `cli/research.py` still pass it; the client creating the root in `new_model_run_dir` is a
  fallback for `python -m acsoe.research.training`, which never goes through A's startup path.
- **C, spec 74.** `TournamentEngine(*, digest_path: Path | None = None)`, keyword-only, with the
  engine blocking when the digest is absent. C proposed a **required** argument; refused,
  because `build_offline_chain()` is called with no arguments by `is_gate_matches_registry` in
  `scripts/verify.py` and a required argument makes that criterion unable to construct the class
  to check `name`, `number` and `is_gate`. `build_offline_chain(*, digest_path=None)` on my side.
- **C, spec 61 step 1.** All eighteen key names confirmed verbatim. The five keys that stay
  absent by ruling are optional leaves and `Config.get` returns `None` for them; an absent
  *section* raises instead, and the difference is only the depth of the `None`.

### HANDOFF TO THE LEAD — `backtest.embargo_bars`, done, the YAML is now safe to paste

`BacktestConfig.embargo_bars` is declared in `src/acsoe/platform/config.py` as
`int | None = Field(default=None, gt=0)`. The `extra="forbid"` refusal that reverted the
lead's attempt today is gone: `backtest.embargo_bars: <positive int>` can be pasted under
`backtest:` and will parse. Four tests in `tests/platform/test_config.py`, all proven red
by mutation (build log).

**One thing the lead must know before pasting, because it is *not* how the
`kraken.cache_ttl_s` handoff behaved.** That key was a nested section, so
`Config.get("kraken.cache_ttl_s.asset_pairs")` raised while it was `None` — the walk had to
descend *into* the `None`. `embargo_bars` is a **leaf**, so `Config.get("backtest.embargo_bars")`
returns `None` rather than raising, exactly like `trading.stable_quote_currencies`. Absence
therefore does **not** fail closed at the point of use. Whatever purges on this key must
refuse `None` explicitly and must never treat it as zero. I did not change `Config.get` to
raise on a `None` leaf: that would change `trading.stable_quote_currencies`, whose two
readers were ruled in Phase 3 to disagree about absence, and overturning that ruling from
the config loader is not mine to do.

**Follow-up, one line, the lead's call:** once the YAML key is in, change
`embargo_bars: int | None = Field(default=None, gt=0)` to `embargo_bars: int = Field(gt=0)`.
`test_the_committed_config_and_the_embargo_bars_handoff` asserts both worlds and stays green
across the paste, so it does not need touching either way.

### Spec 54 — COMPLETE, 2026-09-11. Archive and replay.

**The spec changed under me mid-task.** The original worked around an empty
`data/historical/` by reducing `data/raw/` into archive-shaped CSVs; the operator then
supplied Kraken's own published time-and-sales history, ~27 GB across 1,119 pair files in
two directories, and the lead amended the spec to retire the workaround. Both halves are
built and the first one is kept, retired, with its output moved out of the way.

**What is in `data/historical/` now** (gitignored; rebuild with
`scripts/build_ohlcvt.py --pairs XBTUSD ETHUSD SOLUSD --write`):

| file | bars | span | gaps |
|---|---|---|---|
| `XBTUSD_15.csv` | 361,584 | 2013-10-06T21:30Z to 2025-12-31T23:45Z | 11,654 |
| `ETHUSD_15.csv` | 339,125 | 2015-08-07T14:00Z to 2025-12-31T23:45Z | 6,793 |
| `SOLUSD_15.csv` | 158,539 | 2021-06-17T15:30Z to 2025-12-31T23:45Z | 298 |

859,248 bars over 4,469 days, reduced from **179,701,248 real Kraken trades**. 0 out-of-order
rows, 0 late rows, 0 malformed rows, 0 duplicate timestamps. `PROVENANCE.json` sits beside
them. `replay_full_archive` PASSes under `--live` and PENDINGs without it.

Built at the **top level** of `data/historical/`, not in a subdirectory, because
`replay_full_archive` globs `data/historical/*.csv` non-recursively. The operator's source
files are one level down in `KRAKEN_TimeAndSales_Combined/` and `TimeAndSales_Combined/`, so
source and derived never share a directory, and the `_15` suffix distinguishes seven-column
OHLCVT from three-column time-and-sales. Agreeing with the criterion was worth more than a
tidier tree; C did not have to change a line.

**Files:** `scripts/build_ohlcvt.py` (new), `scripts/build_archive.py` (the retired
recording-derived builder, kept with its output moved to `data/derived/archive_from_raw/`),
`src/acsoe/research/replay.py`, `tests/research/test_replay.py`,
`tests/scripts/test_build_ohlcvt.py`, `tests/scripts/test_build_archive.py`.

**Three things worth knowing.**

1. **The coverage analysis was a measurement, not wasted work.** The recording-derived archive
   had to separate a quiet interval from an interval nobody watched, and it measured
   `missing_quiet = 0` on all three pairs: every hole in it was a recorder outage, and 12 rows
   per pair were built from partly covered intervals. Against Kraken's published archive that
   class of hazard is gone, because Kraken never stops watching. `replay.report`
   carries the answer as `holes_mean_no_trades: bool | None`, **three values not two** — `None`
   is unknown and a consumer must treat it the way it would treat `False`.
2. **Two silent separator bugs, both in code that read JSON without parsing it.** The trade
   prefilter and the `ts_recv` reader both matched `orjson`'s compact separators and would have
   found nothing against any other writer. The second was the dangerous one: it would have
   classified the entire history as unrecorded, which is plausible enough to be believed. Both
   in the build log; the general rule is that a cheap prefilter is a second, weaker parser and
   must be strictly broader than the check it fronts.
3. **Two of my own assertions could not fail**, found by mutation and not by review, both in
   canonicalisation code. Build log.

### Spec 55 — COMPLETE, 2026-09-11. Engine 23 and the offline chain.

`src/acsoe/research/backtest.py` (`BacktestEngine`, name `backtest`, number 23,
`is_gate=False`), registered in `OFFLINE_CHAIN` in `src/acsoe/cli/research.py` and **never in
`bootstrap.py`**. `acsoe research` now reports a real run. `tests/research/test_backtest.py`,
27 tests.

- **The labeller seam is `acsoe.research.labelling.label_frame`**, C's real signature —
  `label_frame(frame, *, pair, config, interval_s) -> (labels_frame, LabelledSeries)` — called
  once per pair over `ArchiveReplay.frame(pair)`, never over the merged stream.
- **I built the engine against a different seam first and every test was green against it.**
  `label_bars(bars, *, target_pct, stop_pct, timeout_bars)`, agreed by message while C's module
  did not exist. C's landed as `label_frame` and **nothing went red**, because every test drove
  a double. There are now two end-to-end tests with no injection at all. The general rule is in
  the build log: a mock for a module that does not exist yet needs a test that fails once it
  does — the same shape `code-standards.md` already states for `try/except ImportError`.
- **The barriers never cross the seam.** `label_frame` takes the `Config` and reads the three
  `barriers.*` keys itself, so there is exactly one reader in the project; the engine reports
  them through C's own `read_barriers` rather than becoming a second one. C converts a YAML
  float with `repr` — `Decimal(0.015)` is `0.01499999999999999944...` — and two readers
  disagreeing in the sixteenth decimal is a defect nobody would find.
- **Without the labeller module the engine refuses to run.** It does not write an unlabelled
  slice and report success — that is the Phase 4 failure mode exactly. A result it cannot read
  raises rather than becoming a slice of nulls.
- The slice goes to `data/derived/labelled_<run_id>_<stamp>.parquet`, named by the run so a
  second run with different barriers cannot silently replace the first.
- The output carries `has_spread: False`, the no-book note, the no-spread note, a note saying
  what a Phase 4 backtest is *not*, `holes_mean_no_trades`, `label_counts`,
  `decision_bars_considered` and `ambiguous_labels`.

**Forty-seven mutations run across both specs; forty-six red.** The one survivor is an
equivalent mutant and is written up rather than quietly dropped. Two more went red only after
they exposed defects in my own tests — a double that made `considered` equal the label count,
and a reported field nothing asserted. Full table with exact red messages in
`docs/build-log/phase-4/a-platform.md`.

### Phase 3 (closed, kept for the record)

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
- **Spec 27 — engine 2 `market_data_recorder`: COMPLETE.** The committed fixture
  `tests/fixtures/recording_report.json` landed on 2026-09-10 from the *clean* run —
  `2026-09-09T14:15:29Z` to `2026-09-10T14:20:00Z`, 86,649 seconds recorded, a 24.1h
  span tiled by 10 segments and 9 accounted breaks, 99.98% recorded against a 98%
  floor. `--phase 2` is 9 PASS / 0 FAIL / 0 PENDING and Phase 2 is closed. It was
  blocked on wall-clock time and never on code, which is why the refusal in
  `scripts/recording_report.py` was mechanical rather than remembered.
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
   missing fee field and never assumes a tier. ~~Invariant 2's paper-mode fallbacks are
   decisions made by the *consumer*, which must record which one fired, and a client
   that quietly supplied one would make that record impossible.~~ **Superseded by spec
   109, 2026-09-18** — the refusal is unchanged and the reason is not: there is no
   paper-mode fallback anywhere in the system and no consumer decision to defer to.
   True when written in Phase 2; left standing with its date rather than rewritten.
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

**`tests/fixtures/recording_report.json` — LANDED 2026-09-10, from the clean run.**
`2026-09-09T14:15:29Z` to `2026-09-10T14:20:00Z`, 86,649 seconds recorded, tiled by 10
segments and 9 accounted breaks, 99.98% recorded against a 98% floor.
`recording_span_continuous` PASSes and Phase 2 closed at 9 PASS / 0 FAIL / 0 PENDING.

*Kept for the record, because the reasoning is what mattered:* the earlier archive held
21h24m with a ~10-hour hole where no recorder was running, and **a report built from it
would have been truthful and would still have FAILed** — which is worse than the
PENDING the criterion was reporting. PENDING means "the subject does not exist yet",
which was true; FAIL would mean "it exists and is wrong", which was not.
`scripts/recording_report.py` refuses to write a digest under `--min-hours` (default
24), so the refusal was mechanical rather than remembered, and there is deliberately no
flag that fabricates a span.

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
  Agreed with C before landing. **Correction, 2026-09-10:** this used to claim "a test
  derives the code list from the engine's own constants so it cannot decay". It did
  not — the test hand-listed the four codes, so a fifth would simply not have been
  checked, and the failure that guards against is a silent blank in the console rather
  than an error anywhere. Found in the lead's sweep and fixed:
  `test_every_reason_code_exists_in_the_consoles_prose_map` now enumerates every
  `REASON_*` in `data_guard/contracts.__all__`, and adding a code without prose fails
  it. The claim was worse than the gap, because a claim like that stops the next reader
  looking.
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

**Nothing.** Both Phase 2 blockers cleared on 2026-09-10 and both are struck below.

- ~~**Spec 27's fixture: a clean 24-hour recording.**~~ **CLEARED.** The clean run
  completed and `tests/fixtures/recording_report.json` is committed —
  `2026-09-09T14:15:29Z` to `2026-09-10T14:20:00Z`. Operator ruling 2026-09-09 held:
  do not deposit on the old archive, which was 49% recorded and contained a disk outage
  we caused ourselves, and which would have been contaminated evidence for the phase
  whose subject is the data spine. One thing worth keeping from it: Windows lists the
  recorder as a **parent and a child with identical command lines**, which is one
  recorder and not two. That confusion cost an hour; the correction entry is in the
  Phase 2 build log.
- ~~**Spec 29's criterion: the operator's `data_guard.max_data_age_s`.**~~ **CLEARED.**
  Supplied; `data_guard_blocks_bad_data` PASSes and Phase 2 closed at 9 PASS / 0 FAIL /
  0 PENDING.
- **Nothing else.** `bootstrap.py` registration **landed**: the lead registered engines
  1 to 4 after C repointed `orchestrator_empty_registry`, and `console_shows_live_rows`
  is now PASS - "a tick of exchange, market_data_recorder, market_sensor, data_guard
  wrote rows under the daemon's own run_id". The rehearsal held; registration was a
  formality.

  It did take two of my own tests with it, both decayed the same way C's criterion was:
  `test_an_empty_registry_produces_a_valid_tick` and
  `test_the_offline_chain_is_not_in_bootstrap` asserted things true only while the
  registry was empty. Both repointed. Detail in the build log.

## Known gaps I own

**None. The Phase 2 gap here — `cli/engine.py` passing a `Clients()` of three
`None`s — was closed by spec 39 on 2026-09-10 and the note is struck.**

The note said the gap was blocked on `market_data.pairs` and `market_data.book_depth`
and offered two ways forward, and **both were wrong, because both assumed those keys
ought to exist.** Spec 37's Locked Decision retired the question: the universe is
computed per tick, so neither key exists and neither is going to. The subscription
scope is *derived* in engine 2 from `state["exchange"]`, and the book depth is the
recorder's own parameter. My stated lean — "have `acsoe engine` refuse to start
without the keys" — would have been a confident answer to a question that turned out
not to be a question, and it would have made a missing key stop the recorder.

The note also claimed a tripwire it did not have.
`test_a_tick_over_the_real_registry_records_errors_rather_than_raising` was supposed to
turn red when the real clients landed. It did not: it builds the empty `Clients()`
itself instead of going through `cli/engine.py`, so it pinned a fact about a
test-supplied value rather than about the daemon. Both errors are written up in
`docs/build-log/phase-3/a-platform.md`; the lesson worth carrying is the second one —
**a test whose purpose is "this goes red when X changes" has to reach X through the
code path X lives on.**

## Phase 4 — the second round, after the lead's four rulings (2026-09-11)

**`embargo_bars` is required again.** The YAML landed, the field is `int = Field(gt=0)`, and
the both-worlds test no longer branches — its "key absent" arm was dead, and a dead branch in a
test is a claim nobody checks. It asserts `field.is_required()` instead, so reopening the
`None` window goes red.

**The invariant-5 guard is a transitive reachability property now, not a file scan.** The
version I shipped earlier the same day removed `cli` from a forbidden-directory list — right in
substance, still **one hop deep**. It walks the whole `acsoe` import graph from `bootstrap`,
`core` and `cli/engine` and asserts nothing reachable at any depth is `acsoe.research`, with the
trail in the failure message. No allow-list: a reachability property has nowhere to put an
exception. **M48** (import added to `bootstrap.py`, at the lead's direct request; restored
byte-identical) is red; **M49** (the same import two hops away, in `engines/data_guard/`) is red
*and the old direct scan stayed green under it* — that is the gap, and the reason the rewrite
was worth more than a widening.

**CRLF.** My CSV writers already pinned `newline="
"`; the two provenance writers did not and
now do. Three mutations red, all asserted on **bytes** — no higher level can see this, because
`read_text`, `splitlines`, `csv.reader` and `json.loads` all normalise. Also pinned the
direction the rule does not cover: we must never write CRLF and must always read it, because
the operator's 27 GB came out of an extraction and `iter_trades` *counts* unparseable rows
rather than raising — so a stray `\r` would present as a silently empty archive.

**Fifty-two mutations across the phase, fifty-one red.** One equivalent mutant, written up.

## Phase 4 - the CRLF correction (2026-09-11)

**I reported my evidence fixtures clean and they were not.** C read them and found
`tests/fixtures/recording_report.json` at 168 CRLF, 0 bare LF. I had audited the same file an
hour earlier with `grep -c $'\r'`, and MSYS `grep` strips the carriage return as a line
terminator before matching - so it reports zero against a file that is entirely CRLF. I had
written in the build log, one entry earlier, that every reader above bytes normalises line
endings, and then ran the audit with one. **The rule was right; I did not apply it to the check
that was verifying the rule.**

Re-audited with `read_bytes` and found **two** files, not one. The second, `kraken/ohlc.json`
at 12,094 CRLF, my audit would never have reached: I scoped it to the three files
`ownership.md` names as A's evidence, and `ohlc.json` is not in that list even though
`scripts/ohlc_fixture.py` produces it. **An audit scoped by a document rather than by who
writes the file misses the files the document forgot.**

Fixed in three parts, because fixing the artefacts alone would let the next regeneration undo
it: both producers pinned to `newline="
"`; both artefacts converted with the change *proven*
to be line endings only (JSON parsed and compared either side, byte delta equal to the CRLF
count - 5,274-5,106=168 and 230,742-218,648=12,094); and `tests/scripts/test_fixture_bytes.py`,
which asserts on `read_bytes` and nothing else.

It matters under `tests/fixtures/**` and nowhere else because `.gitattributes` marks that
directory `-text`. There is no clean filter there, so unlike everywhere else in this repository
a text-mode write changes the **committed blob**. `verify.py` reads both files through
`json.loads(read_text(...))`, so both criteria passed throughout and would have kept passing.

Four mutations red, including one on `.gitattributes` itself: remove the `-text` marking and
every byte assertion in that file becomes unfalsifiable, passing because git is hiding the
problem rather than because the producers are correct.

**All five phases re-verified after changing committed fixture bytes:** 0, 1, 2, 3 green and
`--phase 4 --live` 10/10.

## Open Questions — Phase 4

**1. `bootstrap.py` mutation: RUN, at the lead's direct request.** Resolved. M48 red across four
tests; the file was restored and asserted byte-identical in the same statement that mutated it.
The substitute test stays, because it costs nothing and covers the case where someone runs the
suite without the mutation.

**1b. Superseded: the original wording of this item.** Spec 55 asks
for "the engine registered in `bootstrap.py` instead of the offline chain — the test that
forbids it must be observed red when the import is added". `bootstrap.py` is lead-only under
ownership rule 2 and a transient mutation is still a write to another agent's path in a shared
checkout. I built a substitute that proves the detector can fail and separately proves it reads
the real file, and said in the build log where that is weaker. **One line for the lead:** add
`from acsoe.research.backtest import BacktestEngine` to `bootstrap.py`, run
`pytest tests/research/test_backtest.py`, confirm red, revert.

**2. Closed: `backtest.embargo_bars` is required.** The YAML landed 2026-09-11 and the field
is tightened. The finding it produced outlives it: **the optional-field handoff pattern only
fails closed for keys nested under an optional section.** For an optional *leaf*, `Config.get`
returns `None` rather than raising, and the window between the two halves is a window in which
a reader silently gets nothing. Kept in the `BacktestConfig` docstring where the next person to
run this dance will meet it.

**3. Two pytest ERRORs appeared once under `verify.py`'s `toolchain_green` and did not
reproduce.** `tests/engines/test_market_data_recorder.py` and `tests/engines/test_scout.py`,
reported as ERROR rather than FAILED, during a run concurrent with another agent's saves. Two
subsequent full runs and the named test in isolation were green, and the error text was not
captured. **Recorded rather than dismissed**, because "it passed on a re-run" is exactly the
unfalsifiable diagnostic `code-standards.md` warns about. If it recurs, capture the traceback
before re-running.

**4. `scripts/recording_report.py` has two pre-existing ruff findings** (I001 import order,
RUF100 unused `noqa: E402`) from Phase 2, on a committed and unmodified file. Both are
autofixable. Left alone: `ruff check src/` is clean, the file is unrelated to specs 54 and 55,
and churning a committed file mid-phase in a shared checkout is not worth two lines of lint.

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

### Phase 5, spec 61 complete (2026-09-13)

Every command run by A-2 personally, output redirected to a file and read from the file.

```
$ .venv/Scripts/python.exe -m pytest tests/ -q
2102 passed, 3 skipped in 189.04s (0:03:09)

$ .venv/Scripts/python.exe -m mypy --strict src/ scripts/
Success: no issues found in 106 source files

$ .venv/Scripts/python.exe -m ruff check src/ tests/ scripts/
All checks passed!

$ .venv/Scripts/python.exe scripts/verify.py --phase 5
ACSOE verify - phase 5
repo: C:\Users\saad2\Documents\GitHub\ACSOE

PASS    docs_vocabulary  14 files scanned, 12 retired terms, no hit
FAIL    toolchain_green  ruff exit 1: src\acsoe\engines\feature\engine.py:123:12: SIM300 [*] Yoda condition detected

2 criteria: 1 PASS, 1 FAIL, 0 PENDING
```

**The one FAIL is not in A's lane and is reported, not touched.** It is a `SIM300` Yoda
condition on line 123 of C's engine 5, which landed between my clean `ruff check` four minutes
earlier and this run; `toolchain_green` runs ruff over the whole tree, so any agent's lint error
turns the gate red for everyone. Messaged C-2 with the line and the autofix. My own
`ruff check src/ tests/ scripts/` above is the same command over the same tree and passed, which
is what dates the two runs either side of that landing.

The `acsoe research` acceptance check, run for real against a 400-bar archive in a scratch root
so it completes in seconds rather than over the full 20-million-bar archive:

```
$ .venv/Scripts/python.exe -m acsoe.cli.main --config .../config/default.yaml research
acsoe research: running 1 offline engine(s) from ...\config\default.yaml: backtest.
  backtest   OK
exit=0
```

It wrote `data/derived/labelled_research-20260913T001726685548_<stamp>.parquet`, migrated
`data/db/acsoe.sqlite`, and created an empty `models/` beside them.

The same command against the **real** archive — 234 pair files, 20,443,861 bars — also
finished, exit 0, in about 36 minutes:

```
$ .venv/Scripts/python.exe -m acsoe.cli.main --config config/default.yaml research
acsoe research: running 1 offline engine(s) from config\default.yaml.
  backtest   OK
exit=0

rows 20331237  cols 13  mb 429
data/derived/labelled_research-20260913T000430950753_20260913T004003Z.parquet
```

### Phase 3, specs 38 and 39 complete (2026-09-10)

```
$ .venv/Scripts/python.exe -m pytest tests/ -q
1199 passed in 77.61s

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

**Spec 39's acceptance was mutation-tested, per the new standard.** Twelve mutations
across `subscription_scope`, `set_subscription` and `_apply_subscription`, applied one
at a time and reverted. Eleven killed on the first pass. **One survived**: flipping
`subscription_derived` to `True` on the branch where `state["exchange"]` is absent
entirely — not a rare branch but the one *most* tests take, since every test in
`test_market_data_recorder.py` runs engine 2 without engine 1. Excellent line coverage,
no assertion. Closed by
`test_engine_one_publishing_nothing_leaves_the_scope_alone_and_says_so`; twelve of
twelve now killed. **Coverage counts executions; a mutation asks whether anything would
object**, and re-reading the tests would never have found it, because re-reading is
what produced them.

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

## Recorder gap audit (2026-09-19) — separate from Phase 7 spec work

**Claimed 2026-09-19 on the lead's message. Audit only: no code edited, nothing built, and the
recorder, the manager and the funding poller were not stopped or restarted.** The scope is what
a replay of a recorded day needs that `scripts/record.py` and `scripts/recording/funding.py` do
not capture. Findings are in `docs/build-log/phase-7/a-platform.md` under "Recorder gap audit".
Spec 127 was not touched. AssetPairs and the v2 instrument snapshot were fetched once each into
the session scratchpad, not into `tests/fixtures/`, only to read their field sets.

Status: **findings delivered to the lead; waiting on the operator's ruling before any build.**

Open for the lead (details in the build log):
- The funding poller **is not running**. Its last poll was 2026-09-15 08:00Z. Nothing restarts it
  after a reboot, because `master.bat` starts only the supervisor and the recorder.
- `map_trade_volume` in `clients/kraken/rest.py` does not match Kraken's documented TradeVolume
  shape, and `trade_volume()` sends no `pair`, so Kraken returns no fees. The live fee fetch
  cannot succeed as written.
- `map_asset_pairs` keys pair rules by REST name (`XXBTZUSD`, quote `ZUSD`). Engine 3 keys quotes
  by v2 symbol (`BTC/USD`), and engine 7 compares the quote against `USD`, so live engine 7
  would exclude every pair. The recorder's frame has to be keyed the way engine 7 reads it.

### Build, on the operator's ruling of 2026-09-19 (claimed by A-recorder)

Order: P3-funding, then P2 (`fees.py`) with its `recorder.pollers` entry. P1 is **not ruled**
and is not to be built. Teammates do not commit and I restart nothing until the lead says so.

- [x] **P3-funding, built 2026-09-19, awaiting the lead's gate and commit.** `supervise.py`
  runs the recorder plus the pollers listed under `recorder.pollers`, re-read live, each with
  the recorder's backoff and lock-wait. `tests/scripts/test_supervise.py` has 27 tests, and the
  mutation sweep killed 10 of 10. The config key has been requested from the lead. The
  switchover restart waits for the lead's word.
- [ ] **P2.** `scripts/recording/fees.py`: hourly signed TradeVolume plus public AssetPairs,
  verbatim, into `data/raw/fees/`. It uses a copied `.env` reader and signer, per the lead's
  how-decision.

## a-replay — Phase 7 specs 129, 131, 142 (2026-09-19)

**Claimed 2026-09-19 by a-replay (Agent A, Platform), after the Phase 6 preflight gate exited 0:
spec 129 (the replay client), then 131 (engine 23 drives the registered chain), then 142 (rehearse
one replayed day).** Also: every new config model field this phase goes through a-replay
(`src/acsoe/platform/config.py`).

- [ ] 129 — in progress
- [ ] 131 — not started
- [ ] 142 — not started

### Seams agreed or proposed (by message)

- a-data (127, 128, 130): the partition, rules and table shapes, proposed 2026-09-19. I am
  building against mocks of exactly those shapes.
- c-models (135): run dirs named `train-20260913T205245-067b2b9d-f<k>-p7`, proposed; the fold
  block in the manifest.
- The lead (134): `clients.scenario_digest` and `clients.scenario_description`, both `str`,
  on the clients container, proposed.

### Stops and open items (messaged to the lead)

- **S-fee-class.** `FeeTierSnapshot` is account-level, so the Stablecoin, Pegged & FX fee table
  cannot be served per pair without a contract or engine change. Recommended: the Spot Crypto
  tier for every pair, with the count of candidates and trades on the ~11 affected pairs
  reported. Case against: those pairs would be priced at the wrong schedule. Alternative:
  exclude them from the rules, which is a universe change.
- **Core need for spec 131 step 6.** An optional `previous_now` keyword on the orchestrator
  constructor, so that a resumed replay's first tick has its trade range. Without it, killing
  and resuming cannot reproduce the uninterrupted rows exactly.
