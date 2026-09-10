# Build log — Phase 3: Economics

Written by the agents as work happens, per `context/script-rules.md`.
Record every non-trivial problem and its fix. This cannot be reconstructed later.

The per-agent files are `docs/build-log/phase-3/{lead,a-platform,b-store,c-interface}.md` and
they remain exactly as the agents wrote them. This file is the consolidation made at phase close.

## Phase 3 summary

*Written by the lead at phase close, 2026-09-10.*

**What this phase was for.** Phase 2 got honest data into the system. Phase 3 decides whether a
trade is worth making, and stops the account when something is wrong. It builds four gates and no
machine learning of any kind: engine 7 `scout` narrows the whole exchange down to the pairs this
account could actually trade on this bar; engine 10 `cost` refuses a trade whose expected move
cannot pay the fees, the spread and the slippage; engine 11 `risk` sizes the position and refuses
one below the exchange's own minimum; and engine 17 `safety` is the circuit breaker on the account
itself. Nothing here predicts anything. All four exist to say *no*.

**The phase opened with a problem, and that problem is its real subject.** Three of the four
engines already existed. Agent B had built `cost`, `risk` and `safety` during an authorised overlap
with Phase 2, against a mocked exchange client and a seeded database. They passed their own tests.
An audit at planning found that all three read a `state["exchange"]` payload that engine 1 does not
publish and never has: the fee tier under the wrong key, the pair rules under the wrong key, and a
*price* that nothing in the system publishes at all. On a live tick every one of them would have
blocked, permanently, for a reason naming a key nothing writes.

They passed because every test built that payload by hand, in the shape the engine expected. The
mock agreed with its caller, so both sides were consistent and both were wrong. The operator ruled
that the fixtures be **rewritten from engine 1's real output, not repointed** — changing a key name
inside a hand-built dictionary would have restored the green suite and left the seam exactly as
untested as it had been for a whole phase.

**Built.** Eleven specifications, 37 to 47, across three teammates and the lead.

- **Agent A — the platform and exchange side.** Time-bounded caching in the Kraken client, kept
  rigorously separate from the last-known-good retention it resembles; and the wiring that gives
  the daemon real clients for the first time, deriving what the system subscribes to on each tick
  from the currencies the account actually holds rather than from any configured list of pairs.
- **Agent B — the four gates.** All three existing engines rewired to the real contract, engine 11
  given a price and the system's last remaining paper-mode fallback, engine 17's escalation table
  applied as the operator ruled it, and engine 7 `scout` built from nothing.
- **Agent C — the checks and the operator's words.** Seven new exit criteria in `scripts/verify.py`,
  each observed reporting PENDING, PASS and FAIL before being trusted; and the plain-English
  sentence an operator reads for each of the nineteen machine-readable reason codes the four
  engines can emit.
- **The lead.** Three operator rulings written into the authority documents, two configuration keys
  landed across an ownership boundary, and the registration of all four engines into the live chains
  as the final act of the phase.

**Verify output.** Run at phase close on a quiet tree, all four gates, exit code 0 each:

```
$ python scripts/verify.py --phase 0
 7 criteria:  7 PASS, 0 FAIL, 0 PENDING     Phase 0 is green: every criterion PASS, zero PENDING.

$ python scripts/verify.py --phase 1
10 criteria: 10 PASS, 0 FAIL, 0 PENDING     Phase 1 is green: every criterion PASS, zero PENDING.

$ python scripts/verify.py --phase 2
 9 criteria:  9 PASS, 0 FAIL, 0 PENDING     Phase 2 is green: every criterion PASS, zero PENDING.

$ python scripts/verify.py --phase 3
 9 criteria:  9 PASS, 0 FAIL, 0 PENDING     Phase 3 is green: every criterion PASS, zero PENDING.

$ pytest tests/ -q          1340 passed
$ mypy --strict src/        Success: no issues found in 71 source files
$ ruff check src/           All checks passed!
```

The Phase 3 criteria, in full, are the record of what the four engines were actually shown to do:

```
PASS  cost_gate_uses_live_fee_tier      BTC/USD: net edge 0.0075 at maker/taker 0.0005/0.0010 and
                                        0.0020 at 0.0025/0.0045, moving by exactly the 0.0055 fee
                                        difference; the cheap tier clears the hurdle and the
                                        expensive tier is blocked
PASS  risk_rejects_sub_ordermin         BTC/USD: sized 5.97481259, then refused at an `ordermin` of
                                        5.97481260 - one lot increment (1E-8) above it - with
                                        reason 'below_ordermin' and no quantity returned
PASS  universe_varies_with_balance      0 pair(s) tradable at a $10 balance and 3 at $5,000, over
                                        the same fixture set
PASS  safety_freezes_on_drawdown_...    the seeded drawdown froze the system on a tick with an empty
                                        opportunity chain (tripped: drawdown, loss_streak); one
                                        `freeze` row over three ticks, no `close_all`, and the
                                        daemon reached `frozen`
PASS  safety_escalates_on_sustained_... 15 consecutive blocked tick(s) does not trip the outage and
                                        writes no `close_all`; 16 trips it and writes one
PASS  safety_inputs_all_from_the_seed   all six inputs match the seeded tables and none of them
                                        moved when state was poisoned with an engine 19 payload
PASS  phase_3_gates_have_both_tests     block/pass per engine: cost 10/3, risk 17/4, safety 6/4,
                                        scout 6/4
```

**Problems of note.** The phase produced one defect class in such quantity that it became the
phase's second subject, and the entries below are largely about it.

*A test that cannot fail.* Instances were found by every agent and by the lead, in three distinct
shapes that need three different questions.

1. **A double too simple to exhibit the property under test.** A fake transport that counted
   nothing, in tests about whether a second call makes a request. A client built without a cache
   interval, so the interval check raised before the credential check the test existed to exercise —
   both raising the same exception type, so `pytest.raises` could not tell them apart. A fake sleep
   with no suspension in it, in a test about lock contention. The lead's own orchestrator built
   without a logger, so the logging call under test was never reached.
2. **A claim and its evidence moving together.** B's fixtures agreeing with their caller. A
   criterion importing the very constant it checked its answer against, so expectation and answer
   moved as one. A test reading a queue the system had already emptied. A criterion comparing zero
   rows against zero rows.
3. **A double standing where the subject should be.** A tripwire written in Phase 2 *specifically*
   to turn red when the daemon was wired to real clients, which stayed green through exactly that
   change because it built the empty client set itself instead of going through the daemon's own
   construction path. This one passes the "could it fail?" question — it could, just never for the
   reason it existed.

A fourth was found by a commissioned sweep and is the decayed assertion from the opposite direction:
**a fallback for a thing that does not exist yet has an expiry date and nothing records it.** Each
was correct when written and had become a silent branch firing on a condition that should be
impossible. The fix formulation that came out of it is the transferable part: **never delete the
fallback — add the assertion that the fallback is unreachable**, which turns a stale workaround into
a tripwire for the day someone breaks what it stood in for.

The techniques that actually catch these are cheap and became standards mid-phase: read the source
before building against it; **break the code and watch the test go red**; and the caveat that makes
the second usable — *a mutation that survives a subset has not survived, it has not been asked.* Two
of twenty-three survivors died when re-run against the wider suite. A false survivor is worse than a
missed one, because it sends someone to write a test for a case already covered and makes the real
survivors look less urgent.

*Coverage pointed the wrong way, which is the sharpest single result of the phase.* A surviving
mutant sat on a branch with **excellent** line coverage: every test in one file exercised that path
constantly and none asserted what it reported. **Coverage counts executions; a mutation asks whether
anything would object**, and where they disagree the mutation is right. A line everybody runs is the
line nobody thinks to assert on.

*The strongest instance was a test whose own docstring was the most convincing thing about it.* An
ordering test claimed in prose to be "the assertion carrying the ordering" and named an
accidentally-stable sort as exactly what it would catch. That was the one case it could not detect.
Reading it would never have revealed this, because the docstring is persuasive and the test does
something real. **A test can be well-written, well-named, well-documented and still be untestable
prose.**

*One bug had been misdiagnosed for two phases, and the misdiagnosis is the more important finding.*
Intermittent test failures had been attributed to a native memory fault on this machine. Agent B
captured a traceback rather than re-running, proposed a mechanism as an explicitly unproven
candidate, and was right: `scripts/verify.py` deleted every `acsoe-verify-*` directory in the shared
temporary directory, including ones other processes were actively using. Its docstring asserted that
a directory in use "simply will not delete" — a POSIX assumption written as a fact about Windows —
and `ignore_errors=True` guaranteed *partial* deletion rather than none. One defect, two symptoms: a
vanished directory gives `unable to open database file`, while a surviving directory with its
database removed gives a freshly created empty database and then `no such table`. Both were charged
to the machine.

**Three mechanisms had been collapsed into one.** The sweeper, now fixed. A wall-clock assertion in
a Phase 1 criterion that was measuring connection setup rather than the push latency it named — its
reported figure fell from 509ms to 6ms once measured from a steady-state connection — now fixed. And
a genuine native fault, which remains, presents as a process crash rather than a test failure, and is
now charged only with what it actually causes.

**The generalisation is the finding, not the bug.** The standing instruction was *re-run the named
test in isolation, and if it passes it was the intermittent fault*. That instruction worked every
time — because in isolation nothing else was sweeping. **A diagnostic procedure that cannot fail is
the same defect as a test that cannot fail**, and this project spent a phase cataloguing the second
while running on the first. The question to ask of a diagnostic is the one asked of a test: *under
what observation would this have told me something else?*

*Two operator rulings came out of engines refusing to guess, and both were escalations rather than
inventions.* Engine 17 could emit no command at all when its strongest action was suppressed, so a
drawdown occurring alongside a data outage produced *less* action than the drawdown alone; the
operator ruled that the strongest unsuppressed action is emitted instead. And the affordability check
compared a value in the account's reporting currency against a balance in the pair's quote currency,
with no exchange rate published anywhere — a comparison engine 11 had carried unnoticed for two
specifications, because no test had ever reached it. It was found by writing the third caller, not by
anything failing. The operator ruled that a pair whose affordability cannot be computed leaves the
tradable universe. Neither engine invented a number, and a third proposal — a heuristic for deciding
which quote currencies are crypto — was rejected because it was wrong on real exchange data in the
*conservative* direction, which is the hardest kind of wrong to notice.

*An interruption early in the phase demonstrated a rule the project already had.* An IDE crash took
the session with three agents mid-task. Source code survived, because it was on disk. Progress files
survived, because agents write them *before* starting work. **Every build log was an empty stub**,
because the natural moment to write one feels like the end of a task. `script-rules.md` rule 1 was
rewritten from advice into a rule: write the entry when you have *diagnosed* the problem, before you
write the fix. The diagnosis is the only part of a fix that exists solely in one head.

**Deliberately deferred.**

- **The ranking score in engine 7 `scout` does not exist, and that is recorded rather than
  forgotten.** Ordering is alphabetical over the whole universe — a placeholder that cannot be
  mistaken for a judgement. Phase 5 closes it at one named seam, `rank_universe`, which exists as a
  separate function for that reason alone. Whoever replaces it must test that function *directly*:
  the engine sorts its scan set before ranking, so an end-to-end fixture cannot distinguish
  alphabetical ordering from a ranking that merely preserves arrival order.
- **The console's empty state does not show engine 7's scan tally.** The gap is structural rather
  than a missed wire: the console is a separate process reading the database and never sees the
  in-memory state where the tally lives for one tick. Persisting it is engine 19 `memory`, in Phase 4.
- **A genuine native fault on this machine remains unexplained**, now that the two defects hiding
  behind it are fixed. It presents as an access violation or stack-buffer-overrun crash, not as a
  test failure, and it is no longer permitted to absorb any failure carrying a database error.
- **Engines 5, 6, 8, 9, 12 to 16, 18, 19, 21 and 22 are unregistered because they do not exist.**
  The opportunity chain runs 7 → 10 → 11: registry order with holes, not a different order.


## Consolidated from the per-agent logs

Everything below is the agents' own text, unedited, in the order they wrote it. The per-agent files remain in `docs/build-log/phase-3/` exactly as written; this is a copy so the phase reads as one document.

## The lead

### A config key and its model field cannot land separately

**Agent:** Lead · **Task:** spec 37 · **Date:** 2026-09-10

**What happened.** Spec 37 called for two new keys under `kraken:` in
`config/default.yaml`. I added them, and `load_config()` raised:

```
kraken.cache_ttl_s
  Extra inputs are not permitted [type=extra_forbidden, input_value={'asset_pairs': 300, 'trade_volume': 60}, input_type=dict]
```

Every test in the tree fails on that, because almost everything loads the committed
config. I reverted inside the same minute.

**Why.** `KrakenConfig` in `platform/config.py` is a `_Section`, and every section sets
`extra="forbid"` — deliberately, so that a typo in a key name is a startup refusal
rather than a silently ignored setting. That makes the YAML and the model field two
halves of one change. And they have different owners: the lead authors
`config/default.yaml`, Agent A owns the loader. `ownership.md` already says "A may
request a config key; only the lead adds one", which describes the request direction
but not the landing order.

**Fix.** Ordered the halves rather than the ownership. Spec 38's step 1 became "add the
field to `KrakenConfig`, then tell the lead", and spec 37 grew an appendix carrying the
YAML block verbatim so the lead's half is a single paste that cannot drift from what A
validated against. A landed the field, published a handoff note in
`context/progress/a-platform.md`, and I pasted the block and confirmed both keys resolve
through `Config.get` before touching anything else.

**Consequence.** A made one call I want to record as A's rather than mine, because it is
the non-obvious half: the field is `CacheTtlConfig | None = None`, not required. A
required field would have made the *shipped* config raise until the YAML caught up —
the same failure I hit, with the halves reversed — and spec 38 explicitly told A to test
against a fabricated config until the YAML landed, which is only possible if the
committed file still loads. `None` is not a fallback: `Config.get` raises when asked to
descend through it and the REST client raises rather than caching for a guessed
interval, so an absent TTL fails closed at the point of use. Now that the YAML is in,
the field is tightened to required so a later removal refuses at startup instead.

**A generalisation worth carrying.** Any change that spans an ownership boundary in a
file pair where one half validates the other has a landing order, and the order is not
implied by who owns what. `ownership.md`'s seam table names producers and consumers; it
does not name which half may exist alone. This is the second seam this project has found
that way — the first was the command reader, where both halves passed their own tests
while disagreeing with each other.

### The IDE crashed with three agents mid-flight, and the log was the thing that was lost

**Agent:** Lead · **Task:** phase 3 wave 1 · **Date:** 2026-09-10

**What happened.** The IDE crashed while A, B and C were all working. On restart the
session had no completion record for any of them. The IDE had also committed the
working tree as `7c4f012` — a commit no agent made and no agent was authorised to make.

The tree was left genuinely red, and specifically: B had removed `EXCHANGE_FEES_KEY` and
`EXCHANGE_FALLBACKS_KEY` from `engines/cost/contracts.py` while `engine.py` still
referenced them, so `mypy --strict` reported six name-errors and 25 tests failed. That
is a deterministic failure and worth distinguishing loudly from this machine's known
intermittent fault, because the standing instruction on a FAIL is to re-run the named
test in isolation — advice that would have wasted time here.

**Why.** Nothing to diagnose in the crash itself; it is the known limitation recorded
under Known Risks. What is worth recording is the state it left: source code half-edited
and committed, progress files intact, **and all four `docs/build-log/phase-3/*.md` still
empty stubs.**

**Fix.** Assessed the tree before resuming anything — `git show --stat` on the unexpected
commit, `load_config()`, then the full gate — rather than restarting the agents blind.
Completed the lead half of the config handoff, which A's surviving progress note had
unblocked. Then resumed all three from their saved transcripts, each with a written
account of what had changed underneath them: what survived, what did not, that the red
tree was B's and not theirs, and that the config now differs from when they started.

**Consequence.** The code survived and the reasoning did not. Progress files survived
because agents write them before starting work; build logs did not, because the natural
moment to write one feels like the end of a task. That is exactly backwards, and
`script-rules.md` rule 1 already says so — "write the entry when you fix the thing, not
at the end of the session". Phase 1 lost work to three IDE crashes and produced that
rule; this is the first time the rule has been tested against a crash with several
agents running, and the rule held for the file it covers while the gap it leaves is that
nothing enforces it mid-task. Each resumed agent was told to write down anything it
still remembered from before the crash while it still had it. Whatever was not
remembered is gone, and it is gone in the way this project has already decided is
worst: a bug that was fixed and not recorded is a bug that never happened.


### Assessing the tree after the crash: three deterministic clusters, none of them the intermittent fault

**Agent:** Lead · **Task:** phase 3 wave 1 resumption · **Date:** 2026-09-10

**What happened.** The session moved to a standalone terminal, which removes the IDE-crash
mechanism entirely — `claude` is no longer a child of the IDE process. On resumption
`verify.py --phase 3` reported `FAIL toolchain_green`, with 23 failed / 1052 passed and two
ruff errors. `mypy --strict src/` was clean across 68 files. The 23 failures sort into three
clusters, and every one of them reproduces in isolation, so the standing "re-run the named
test before you believe it" advice does not apply to any of them. Recording that up front
because the previous crash cost time in exactly the opposite direction.

**Cluster 1 — A, spec 38, seven failures plus both ruff errors.** `KrakenRestClient` now
takes its two TTLs at construction and `_require_ttl` raises `KrakenUnavailableError` when
one is `None`. `build_client` in `tests/clients/kraken/test_rest.py` predates that change and
passes neither, so six `test_rest.py` tests and one in `test_secrets.py` fail on a missing
TTL rather than on anything they are about. The implementation half of spec 38 landed; the
existing-test half did not. Both ruff errors are `RUF100` unused-`noqa` on the two
`assert cached is not None` narrowing lines in `rest.py` — `S101` is not enabled, so the
suppression suppresses nothing.

**Cluster 2 — B, spec 40, fifteen failures.** `engines/cost/{contracts,engine}.py` are
rewritten against engine 1's real contract: `exchange.fee_tier.maker_fee_pct` /
`taker_fee_pct`, and `failed_fetches` read for the operator sentence only. The docstring
correcting "ratified" to "assumed" is written and is good. `tests/engines/test_cost.py` is
untouched — `build_state` still hand-builds `exchange.fees.maker_pct` and
`exchange.fallbacks_used` — so every cost test now blocks with `cost_inputs_unavailable`.
This is the audit's own subject appearing as a red suite, which is the correct direction: the
old fixtures agreed with the old engine and hid the mismatch for a phase; the new engine
disagrees with them loudly. The remaining half is the larger one, because spec 40 requires
the fixtures rebuilt from engine 1's output rather than repointed.

**Cluster 3 — mine, and the alarm that caught it is A's.** See the decision entry below.

**Why it matters that the clusters are clean.** A crash that leaves a half-edited tree looks
like a hundred unrelated defects, and the recovery section of `PHASE-3-TASKS.md` was written
after the last one for that reason. It held: config loaded first try, both TTL keys resolved,
mypy was clean, and the three clusters map one-to-one onto the three agents' claimed specs
with nothing left over. Nothing needed root-causing that was not simply unfinished.

### Decision: the `Operator-chosen` marker stays a claim about trading behaviour, so `cache_ttl_s` loses it

**Agent:** Lead · **Task:** spec 37 step 4, follow-up · **Date:** 2026-09-10

**What happened.** `test_the_file_marks_exactly_these_ten_keys_as_the_operator_s` failed with
one extra item in the set scanned from the file: `cache_ttl_s`. The YAML block I pasted from
spec 37's appendix carries `# Operator-chosen 2026-09-10`, verbatim as the appendix has it
and as step 4 asks for in as many words — "both marked operator-chosen 2026-09-10".

**Options.** Add `kraken.cache_ttl_s` to `OPERATOR_REQUIRED_KEYS` in the two test files that
declare it, or remove the marker from the YAML.

**Chose.** Removed the marker, and replaced it with an explicit provenance line naming the
lead and the spec, so the key still says where its value came from.

**Because.** The marker is not decoration; `config/default.yaml`'s own header defines it, and
the definition is narrow: a marked key is one "the context files name but never specify"
whose value "is trading behaviour, so the lead may not invent one". A cache TTL is neither.
The `kraken:` section header says of itself, three lines above the block I pasted, that
everything in it "is OUR OWN self-imposed request budget and timeout, chosen by the lead" —
and `rest_capacity`, `rest_refill_per_s` and `rest_timeout_s` all sit there unmarked. The
appendix comment says the same thing about these two keys specifically: "OUR OWN re-fetch
interval". Spec 37 step 4 contradicted its own block, and I wrote both.

**The tie-breaker is what A built the test for.** Its docstring says the shipped file's nulls
used to be the tenth-key alarm, and that with zero nulls "the lead can now add a tenth *and
supply it*, and nothing would notice". This is that case, on the first occasion it arose,
firing on the lead, within hours. Bumping the list to match the file is the one response that
converts the alarm into a rubber stamp — it would pass on any tenth key the lead marked for
any reason, including the one the test exists to catch. The list is the fixed thing and the
file is what gets checked against it.

**Cost, and it is real.** `OPERATOR_REQUIRED_KEYS` stays at ten, so nothing in the refusal
machinery names `kraken.cache_ttl_s`, and an agent editing 300 or 60 would not be stopped by
that list. It would still be stopped by `_refuse_nulls` if the key were emptied, and the
values are now attributed in the file itself. If the operator's view is that they chose 300
and 60 rather than the lead, the reversal is one line in each of two test files and this entry
is what it should be read against — but it should be a deliberate answer, not a list bumped to
silence a failing test.

**Consequence.** Spec 37's step 4 and its appendix both still say "operator-chosen". Per rule
6 I have not edited them; this entry is the correction, and step 4 is the wrong half.

### Confirmed A's `RateLimiter` loop-binding flag before spec 39 spent time on it

**Agent:** Lead · **Task:** spec 39 support, and spec 47's acceptance · **Date:** 2026-09-10

**What happened.** A flagged, from reading the code rather than from a failure, that
`RateLimiter` constructs an `asyncio.Lock` in `__init__` while `platform/aio.py`'s
`run_blocking` calls `asyncio.run` once per call — so a limiter held across ticks may bind to
the first event loop and raise on the second. A proposed to confirm it empirically under spec
39. I reproduced it immediately instead, because the answer changes how spec 39 is built and
because it lands on spec 47's acceptance, which is mine: *"a daemon tick completes on an empty
database and on the seeded one"*.

**It is real, and A's reasoning about the trigger was right in the part that matters.**
On this machine's Python 3.13.5, one `asyncio.Lock` across two separate `asyncio.run` calls:

```
uncontended run 1: ok
uncontended run 2: ok
contended run 1: ok
contended run 2 RAISED: RuntimeError - <asyncio.locks.Lock object at 0x... [locked]>
                        is bound to a different event loop
```

**Why contention is the whole story.** `Lock.acquire()` on the uncontended path sets
`_locked` and returns without ever calling `_get_loop()`, so an uncontended lock survives any
number of loops. The contended path calls `self._get_loop().create_future()`, and `_get_loop()`
binds `self._loop` on first use and raises against any later loop. Engine 1 gathers three
fetches concurrently, which is what makes it contended — so the binding happens on tick 1 and
tick 2 raises. A single-tick test can never see it and a concurrency-free one never will
either. That asymmetry is the non-obvious half and is the reason this is written down.

**Two things the reproduction added to A's read.** The lock is left `[locked]` in the raised
state, because the failure lands partway through `acquire()` — so it is not merely "tick 2
raises", the limiter is wedged, and any caller that catches the `RuntimeError` and retries gets
a lock that never opens. And the reason nothing has caught it is structural rather than lucky:
`cli/engine.py` passes three `None`s, so no real client has ever run two ticks against a shared
limiter, and the existing limiter tests inject their own sleep inside one loop.

**Fix.** Not mine — `clients/kraken/limiter.py` and `platform/aio.py` are A's, and A has the
reproduction and is writing its own entry. Recorded here because the confirmation is the lead's
and because spec 47 would otherwise have discovered it as a mystery on registration day. The
constraint A must not lose under the fix, which A named first: the limiter is deliberately
shared between the REST and WebSocket clients because one account has one rate budget, so a
per-loop lock must not become a per-loop *budget*.

**Consequence for the phase, and it is a point in the specs' favour.** Spec 39's acceptance
says "daemon completes **two** ticks with real clients". Written as one tick it would have
passed and shipped a daemon that dies on its second minute. The clause was not written with
this defect in mind — it was about the subscription set changing between ticks — which is the
argument for acceptance criteria that exercise a mechanism twice rather than once, whatever
the stated reason.

### Ruling: the crypto-quoted exclusion fails closed in engine 7 and fails open in engine 2, and that is not an inconsistency

**Agent:** Lead · **Task:** spec 39 step 3, spec 43 step 4 · **Date:** 2026-09-10

**What happened.** A escalated that invariant 7 defines a crypto-quoted pair as one whose
"quote is BTC, ETH, or **any non-stable asset**", and that no set of stable assets exists
anywhere in the repository. Confirmed by grep: `allow_crypto_quoted` is declared in
`config/default.yaml` and read by two specs, and nothing anywhere says which quote currencies
are crypto. It is not derivable from the exchange either — `AssetPairs` as this client maps it
carries no asset class, and there is no field that would hold one.

**A rejected the derivation, correctly, and the reason is worth keeping.** The available
heuristic is "a pair is crypto-quoted if its quote also appears as a base in the same
snapshot". It classifies our fixture perfectly. It is also wrong on real Kraken, which lists
fiat/fiat pairs, so EUR and GBP appear as bases and every EUR-quoted pair would be called
crypto. It fails *conservatively*, which is exactly why it would have survived every test we
have and then quietly shrunk the universe on real data. A heuristic that is wrong in the safe
direction is the hardest kind to find, because nothing ever complains.

**The question I was asked.** What should engine 2 do in the window where the key is absent?
A named two fail-closed directions pointing opposite ways: exclude every pair not provably
stable and subscribe to nothing, or apply the balance rule alone and publish the fact.

**Ruled: they point opposite ways because the two engines have opposite costs of being wrong,
and the answer is different in each.**

- **Engine 2 `market_data_recorder` proceeds** — balance rule only, crypto-quoted exclusion
  skipped, `crypto_quoted_excluded: false` published in its state so the gap is visible rather
  than silent. This is A's second option and A had already built it.
- **Engine 7 `scout` excludes** — with no stable set, a pair whose quote is not provably
  stable is treated as crypto-quoted and is out of the universe, and `scout` says so in its
  reason code rather than silently narrowing.

**Because the two engines are answering different questions and spec 39 step 4 already says
so in as many words.** Engine 2 computes the *subscription scope* — what the socket pays
attention to — and step 4 states outright that it "is **not** the tradable universe. Engine 7
`scout` is the sole authority on that." So no trade can occur in a crypto-quoted pair on
account of engine 2's behaviour, whatever engine 2 subscribes to; invariant 7's enforcement
lives in one place and it is not this one.

The costs are then asymmetric in opposite directions. For engine 2, over-subscribing costs
bandwidth and under-subscribing destroys order-book history that cannot be recovered — spec 39
step 5 calls that "the one thing this system may never do", in the neighbouring paragraph. For
engine 7, over-including risks a trade the operator explicitly disabled, and under-including
costs an opportunity that recurs on the next tick and every tick after. **Fail-closed is not a
direction, it is a question about which error is irreversible**, and the irreversible error is
data loss on one side and an unwanted position on the other.

**What makes this safe rather than a fudge:** engine 2 publishes `crypto_quoted_excluded:
false`, so the state carries the fact that the filter did not run. It is a published absence,
not a silent default, and it is the same shape as `failed_fetches` — the system says what it
did not manage to do rather than papering over it.

**Consequence.** The key itself, `trading.stable_quote_currencies`, is escalated to the
operator for its values and is not mine to fill in: it changes which pairs are tradable, which
is the test the YAML header sets for an operator-required key. A's model half is already landed
optional, the same paired-handoff shape as spec 38 step 1. **It must not land in the YAML as
`null`** — `_refuse_nulls` would take the whole tree down, which is the trap the nine originally
occupied and no longer do. Absent until supplied.

### A third green-for-the-wrong-reason test, and now it is a standing rule

**Agent:** Lead · **Task:** phase 3, cross-cutting · **Date:** 2026-09-10

**What happened.** A reported that its first regression test for the limiter's event-loop
binding **passed against the unfixed code**. `FakeTime.sleep` in
`tests/clients/kraken/test_limiter.py` is an `async def` with no `await` in it, so it never
suspends, so the lock is never contended, so the bug it was written to catch cannot occur. A
consequence A drew and I am recording because it is the more useful half:
`test_concurrent_acquirers_are_serialised_and_stay_inside_the_budget` has therefore never run
its twenty coroutines concurrently. Its arithmetic assertion is real and A left it alone, but
the name overclaims.

**Why this is the entry and not a footnote.** It is the third instance this phase and A
identified the shared shape: **a double that is simpler than the real thing in exactly the
dimension the test is about.** The three:

1. A fake transport that counted nothing, in tests about whether a second call makes a request.
2. A client built without a TTL, in a test about whether a missing credential blocks — the TTL
   raised first, same exception type, so `pytest.raises` could not tell.
3. A sleep that does not sleep, in a test about contention.

B's spec 40 fixture problem is the same family seen from the other end — a hand-built
`state["exchange"]` that agreed with its caller, in tests about whether the caller reads the
right keys. Four instances in one phase is a pattern, not a run of bad luck.

**Fix.** Added to `context/code-standards.md` under Testing, as a rule rather than an
observation, phrased as the question to ask: *what is the one property this test exists to
demonstrate, and is the double capable of exhibiting it?* A double simpler than the real thing
in the dimension under test cannot fail, and a test that cannot fail is not evidence. Also
recorded there that a package where every fail-closed path raises one exception type makes
`pytest.raises(ThatType)` alone a weak assertion — A's second finding, which is a special case
of the same rule and the one most likely to recur, since `clients/kraken/` is built that way on
purpose.

### `_log` injects `run_id`, and two callers passed it again — unreachable until spec 39 wired a real store

**Agent:** Lead · **Task:** spec 39 fallout, `core/orchestrator.py` · **Date:** 2026-09-10

**What happened.** Landing the operator's `trading.stable_quote_currencies` values, two CLI
tests went red — `test_engine_starts_against_the_committed_config` and
`test_engine_ticks_against_an_empty_registry_and_exits_zero` — with a traceback that has
nothing to do with config:

```
TypeError: structlog.stdlib.BoundLogger.debug() got multiple values for keyword argument 'run_id'
  orchestrator.py:292 in _record_run  ->  orchestrator.py:129 in _log
```

**Why.** `Orchestrator._log` is a helper that binds the run and cycle onto every event:
`self._logger.debug(event, run_id=self._run_id, cycle_id=self._cycle_id, **fields)`. Two call
sites inside `_record_run` pass `run_id=self._run_id` a second time through `**fields`, so the
call has the argument twice and Python refuses it. Lines 290 and 292; the rest of the file's
twenty-odd `_log` calls are correct, and none passes `cycle_id`.

**Why it has never fired.** `_record_run` returns early at line 280 —
`run_record_skipped, reason="store exposes no start_run"` — when the store does not expose that
method, and until this session `cli/engine.py` passed a `Clients()` of three `None`s. So the
only route to those two lines was a real store client, and nothing had one. **A's spec 39
wiring is what made the code reachable, and the bug was waiting there for it.** Line 290 is the
worse of the two: it is inside the `except` handler, so the path that exists to stop a
bookkeeping failure from killing the loop would itself have raised, turning a logged warning
into a dead daemon. The `except Exception` above it is annotated "a bookkeeping row must never
stop the loop", and it did the opposite.

**Not the intermittent fault and not A's.** Deterministic, reproduces every run, and it is in
`src/acsoe/core/`, which is the lead's file and which no teammate may edit — A would have been
blocked on it by the escalation rule. Recording that explicitly because a red suite arriving in
the middle of another agent's task is exactly the situation the recovery notes say to
disentangle before resuming anyone.

**Fix.** Dropped the redundant `run_id=` from both call sites; `_log` was already supplying it.
Added a regression test that drives a tick through an orchestrator holding a **real**
`StoreClient` on a temporary database, so `_record_run` actually executes both its success and
its failure branch. That is the real defect here — not the duplicated keyword, which is a typo,
but that a method existed for a phase with no test able to reach it. A typo in an unreachable
branch is invisible; the same typo under a test is a red line the moment it is written.

**Consequence, and it generalises past this file.** The pattern is the one `code-standards.md`
gained a rule about an hour ago from A's and B's findings — a double simpler than the real thing
in the dimension under test. Here the double was `Clients()` of three `None`s, which is simpler
than a real client in exactly the dimension `_record_run` is about, and it made two lines
unexecutable rather than merely untested. Worth stating as the sharper form: **a fixture that
makes a branch unreachable is not weak coverage, it is zero coverage that looks like weak
coverage.**

### The regression test I wrote for the `_log` bug passed against the unfixed code

**Agent:** Lead · **Task:** correcting `40dba32` · **Date:** 2026-09-10

**What happened.** A reported the `_record_run` duplicate-keyword crash independently, having
hit it by wiring the daemon up. I had already diagnosed and fixed it an hour earlier and had
added two regression tests. A's report carried one sentence mine did not, and it is the sentence
that matters:

> It needs a real store **and** a real logger at once, and nothing had both. Every test that
> drives the orchestrator against a real store constructs it with `logger=None`, so `_log`
> returns before the call.

I tested that against my own test by putting the duplicate keyword back:

```
mutation applied
27 passed in 0.65s
```

**My regression test does not catch the bug it was written for.** `Orchestrator._log` opens with
`if self._logger is None: return`, and I constructed the orchestrator without a logger, so the
guarded call is never reached and the duplicated keyword never binds.

**Why this entry is worth more than the fix it corrects.** I wrote the rule this bug is an
instance of — *a double must be capable of exhibiting the property under test* — into
`code-standards.md` roughly an hour before committing a test that violates it, in the commit
that cites the rule by name. Recording that plainly rather than fixing it quietly, because a
build log in which the lead's own work is the one clean thread is a build log nobody should
believe, and because it is evidence for a claim the rule makes: this failure is not carelessness
that more care would prevent. Three agents and the lead have now produced five instances in one
phase. The shape survives *knowing about it*, which is the argument for the mechanical checks B
and A have been writing — a source-reading guard, a mutation run — over an instruction to be
careful.

**The sharper diagnosis is A's and it is now the one on record.** I had "the store was the
missing half". It is *two* independent absences, each making the other harmless: no real store
in the CLI, and no real logger in the tests. Same shape as the `state["exchange"]` audit — two
halves that pass their own tests while nothing exercises them together — and A's observation
about how it was found is the part to keep: it was not found by a test aimed at it, but by
wiring the real thing up, because that is the only caller holding both halves.

**Fix.** Both new tests now take a real `structlog` logger through `platform/logging.get_logger`,
and I verified the mutation is caught before reverting it. The assertion is still on the `runs`
row rather than on "no exception", so the test fails for the right reason in both directions:
it goes red if the logging call raises, and it goes red if `_record_run` silently records
nothing.

**Consequence.** Adding the mutation step to the rule in `code-standards.md`. "Ask whether the
double can exhibit the property" is an instruction to imagine a failure, and this entry is
evidence that imagining it is not reliable — including for someone who has just written the
instruction down. Breaking the code and watching the test go red takes a minute and is not
imaginable-away. B did exactly that on spec 41 unprompted, with three mutations reverted, and
that is now the standard rather than the exception.

### One spurious FAIL, recorded rather than smoothed over

**Agent:** Lead · **Task:** verifying specs 42 and 45 · **Date:** 2026-09-10

**What happened.** Running the full suite to verify B's spec 42 and C's spec 45:

```
FAILED tests/engines/test_safety.py::test_no_second_close_all_while_the_outage_persists
1 failed, 1197 passed in 90.98s
```

The gate run immediately afterwards reported `PASS toolchain_green`, which is the
contradiction that made it worth chasing rather than shrugging at.

**What I did, in the order the phase rules set.** Ran the named test in isolation: passed.
Ran its whole file: 48 passed. Re-ran the full suite in the same order: **1198 passed**, the
same total, no failure. So it is non-deterministic and it is this machine's known intermittent
fault rather than a defect in B's engine or an ordering dependency between tests — an ordering
dependency would have reproduced on the second full run, which is the check that distinguishes
the two and the reason to do it before writing this entry.

**What I did not capture, and it is a real gap.** I have the summary line and not the
traceback: the first run's detail is gone. That is the fourth or fifth time this fault has
appeared in this project and there is still no captured traceback for any of them, which is
why it remains "the intermittent fault" rather than a diagnosed bug. **Next occurrence: run
the suite with the failure detail preserved before re-running anything.** The instinct to
re-run and confirm green is the instinct that keeps destroying the evidence.

**Why this is in the log at all.** The phase rules say a spurious FAIL is written down rather
than smoothed over, and the reason is cumulative: any one of these is noise, and the count is
not. Recording it costs a paragraph; not recording it means the next person to see it starts
from zero, and it has now cost this project time in Phase 2 and again here.

### The `close_all` fall-through landed inside the spec 42 commit, and that commit's message does not say so

**Agent:** Lead · **Task:** spec 42 follow-up · **Date:** 2026-09-10

**What happened.** B reported spec 42 with the suppressed-`close_all` question still open and
the fix unapplied, and its idle summary said the same. Both were stale. B had in fact applied
the operator's ruling before I committed, so the fall-through is in `5510243` — a commit whose
message describes spec 42 and does not mention it. Anyone later asking "when did the fall-through
land" will not find it by reading commit messages.

**Why the confusion, and it is worth naming rather than shrugging at.** Three exchanges crossed
in flight: the operator ruled, I wrote it into invariant 14 and messaged B, B applied it while
composing a report written against the pre-ruling position, and I then committed the tree and
asked B to do the thing it had already done. **Nobody was wrong at the moment they wrote — every
message was accurate when composed and stale when read.** That is the cost of parallel agents
with asynchronous messages, and it is the same failure the progress files keep having: a claim
and the code drifting apart, here by minutes rather than by sessions. Per rule 6 I have not
rewritten the commit; this entry is the correction and is where the fall-through's provenance
now lives.

**I verified it rather than trusting either account, by mutation.** Replacing the fall-through
call with `return None, suppressed_because` — the pre-ruling behaviour exactly — turns six tests
red, including both of the two that matter:

```
FAILED test_a_suppressed_close_all_falls_through_to_the_freeze_that_was_due
FAILED test_the_fall_through_does_not_fire_when_the_outage_is_the_only_condition
```

Restored, 48 passed. So the ruling is pinned in **both** directions: the first test says the
fall-through happens, the second says it does not over-fire when the outage is the only
condition tripped. B built the second one without being asked for it by name, and it is the one
that stops "emit the strongest unsuppressed action" quietly becoming "always emit something".

**The general point, which is the reason this is an entry and not a note.** I asked B to mutate
this and then verified it myself instead of asking whether it had. Three of the five cannot-fail
tests this phase were found by the person who wrote them, and two were found by someone else —
so the check is worth doing at the boundary regardless of who claims to have done it, and it
costs a minute. That is not distrust of B, whose mutation discipline is the best on the team and
is why the practice is now in `code-standards.md`. It is that "did you check?" and "I checked"
are two more claims that can drift from the code, and the mutation is the only one of the three
that cannot.

### Ruling: `stable_quote_currencies` stays optional — the landing order is universal, the resting state is not

**Agent:** Lead · **Task:** spec 39 close-out · **Date:** 2026-09-10

**What happened.** A declined to tighten `trading.stable_quote_currencies` to a required field
now that the YAML has landed, which is a deliberate departure from the `cache_ttl_s` precedent
set hours earlier, and flagged it for me to overrule.

**Ruled: A is right, and the distinction it drew is the one to carry.**

`cache_ttl_s` was tightened because **every** reader raises on absence, so refusing at startup
is strictly better than the identical refusal arriving at the first fetch — same outcome,
earlier and with a clearer message. `stable_quote_currencies` has readers I deliberately ruled
to *disagree*: engine 7 `scout` fails closed and excludes, engine 2 `market_data_recorder` fails
open and publishes `crypto_quoted_excluded: false`. A required field overrules both by stopping
the process at startup, and that means the recorder never runs — which is the **irreversible**
error my own asymmetry ruling identified for engine 2, arriving through the config layer instead
of through the engine. Optional leaves a coherent degraded state: recording continues, the
universe is empty, and `scout`'s reason code says why.

Nothing is weakened by it. `_refuse_nulls` still refuses a present-and-null key by name, and the
key is in `OPERATOR_REQUIRED_KEYS`, so the only tolerated state is *absent*, which is the state
the ruling is about.

**A's formulation, which is better than the rule it replaces:** *the landing order is universal;
the resting state is not.* Tighten when absence should stop the process. Leave optional when a
reader has been ruled to keep working without it. The spec 38 pattern fixed the two-owner
handoff window; it never decided what the field should look like afterwards, and I had been
treating "tighten once landed" as though it followed.

### A half-landed config key is not uniformly safe, and engine 2 briefly became a gate

**Agent:** Lead · **Task:** spec 39 close-out, recording A's finding · **Date:** 2026-09-10

**A's finding, and it corrects something I wrote today.** While `market_data.stable_quote_currencies`
was mid-landing, engine 2 read a config key that did not yet exist. `Config.get` raises on an
unknown key, the orchestrator converts a raised engine to `ERROR`, and `ERROR` blocks — so a
missing *optional* key silently turned the **recorder** into the tick's primary blocker and
displaced `data_guard`. `block_records.is_primary` would have been wrong for every tick in that
window, which is a corrupted audit trail rather than a stopped daemon: worse, because it looks
like data.

**Why this matters beyond the instance.** My spec 37 build-log entry concluded that a change
spanning an ownership boundary has a landing order, and I left it there. A's finding is the
other half: **the landing order fixes the length of the window; it does not decide what happens
inside it, and that is a per-reader question.** "The reader raises, so a half-landed key is safe"
is true for a client that raises into a caller expecting failure, and false for an engine whose
raise is converted into a blocking verdict with a name attached. Two engines reading the same
absent key produce a blocked pair and a mislabelled audit row respectively.

### A tripwire attached to a local reproduction of the symptom cannot detect the cause

**Agent:** Lead · **Task:** spec 39 close-out, recording A's finding · **Date:** 2026-09-10

**What happened.** `test_a_tick_over_the_real_registry_records_errors_rather_than_raising` was
written in Phase 2 *specifically* to turn red when spec 39 wired real clients into the daemon.
Spec 39 step 7 is written on that assumption, and so was A's progress note. **It stayed green.**

**Why.** It builds the empty `Clients()` itself rather than going through `cli/engine.py`, so it
pins a fact about a value the test supplies. Replacing the daemon's wiring cannot move a fact the
test constructs. The tripwire was attached to a local reproduction of the symptom rather than to
the cause, and those are only the same thing while nobody changes the cause.

**Why it is worth its own entry.** This is the third distinct angle on the same failure this
phase, and the angles are not interchangeable:

- **A double too simple to exhibit the property** — the fake transport, the sleep that does not
  sleep, the client with no TTL, the lead's orchestrator with no logger.
- **A claim and its evidence moving together** — B's fixtures agreeing with their caller, C's
  reason-code assertion importing the constant it checked, B's `pending_commands()` read of an
  already-emptied list.
- **A double standing where the subject was supposed to be** — this one. Nothing is too simple
  and nothing moves together; the test is simply not connected to the thing it claims to watch.

`code-standards.md` covers the first two. The third is now added, because the tell is different:
the first two are found by asking whether the test *can* fail, and this one passes that question
— it can fail, just never for the reason it was written for. The tell is that a test whose
purpose is "this goes red when X changes" must reach X through the code path X lives on, and
`build_clients` is that path.

**Fix.** A's, and it is the right shape: the test keeps the property it genuinely does test, and
the daemon's construction is asserted separately against `build_clients`.

### The sweep paid for itself on the first finding, and the count is the point

**Agent:** Lead · **Task:** reviewing A's audit · **Date:** 2026-09-10

**Why the sweep was commissioned.** Five instances of the cannot-fail family had turned up in one
phase, every one by accident, three of them by A while doing something else. A rate like that is
evidence of a population, not of bad luck, and finding them by accident is not a plan. A swept
the tree and returned **six findings and two clean areas**, which changes the estimate again: the
population is larger than the accidents suggested.

**The first finding is a latent defect on the live trading path and I verified it myself.**
`parse_envelope` has three refusal branches, all raising `KrakenUnavailableError`. Branches 1 and
3 had tests; branch 2 had none — and the test *named* for it passed `b"<html>maintenance</html>"`,
which is not JSON, so it exercised branch 1. The name claimed one branch, the input reached
another, and the shared exception type meant nothing objected.

It is load-bearing rather than defensive. I checked what the branch actually does before accepting
the severity: a body of `{"result": {...}}` with **no `error` key at all** is refused by it, and
without it that body returns as a clean success — from the one function in the package deciding
whether a Kraken response succeeded. Then I mutated A's fix rather than taking the report on
trust:

```
if False:  # branch 2 deleted
FAILED tests/clients/kraken/test_rest.py::test_json_that_is_not_a_kraken_envelope_is_refused_rather_than_returned
1 failed, 82 passed
```

Exactly one test, named for the branch it guards. Restored, 83 pass.

**A's sharpening of the weak-assertion rule is the transferable part**, and it is now in
`code-standards.md`: *where several branches raise one type, the message is not a nicety — it is
the only thing that says which branch ran.* I had written that rule this morning as "assert on the
message", with the reason being that the wrong *cause* could fire. A found the worse version: a
test can drift onto a *neighbouring branch* and stay green for a phase, with its own name
disagreeing with it.

**A's proposed fourth shape is genuinely not covered by the three and is now a standard:** *a
fallback for a thing that does not exist yet needs a test that fails once it does.* The tell is
`try: import the real thing / except ImportError: define our own`, with nothing asserting which
branch ran — so a test importing *through* the fallback cannot detect it. It is the decayed
assertion from the opposite direction: not a claim that stopped being checked, but a scaffold that
stopped being load-bearing and was never removed. A demonstrated it without touching a repo file,
by blocking `acsoe.clients.kraken` at the import system, and the harness test passed against the
fallback classes.

**The `importorskip` half is the one with scale behind it.** A expected it to mask a broken module
and it does not — pytest re-raises an `ImportError` raised from inside a module. But a
`ModuleNotFoundError` from inside it, which is exactly what a dependency moving to an extra
produces, **is** skipped. About **370 test functions** — a third of the suite — sit behind a
fixture guarded that way, and the skip reason would read "the store client does not exist yet",
which would be false. A green run with a third of it skipped under a false reason is worse than a
red one.

**Two clean areas, reported as findings, and they should be.** The network guard was probed for a
hole and none was found — real sockets, real httpx, `NetworkAccessError.layer` asserted so a
half-guard is distinguishable from a whole one. And B's
`test_the_seed_overshoots_the_operators_own_configured_limits` reads config on both sides but is
**not** self-referential: the seed's output is the subject and the config is an independent
reference. A said so explicitly rather than leaving it off the list. An audit that reports only
hits gives no information about coverage, and "I looked here and it is sound" is what makes the
six findings mean something.

**A also reported four `pytest.raises` calls it checked and deliberately left**, each with the
reason. That is the right disposition and worth naming: a sweep that fixes everything it touches
is indistinguishable from one that fixed things that were fine.

### A baseline cannot be captured while another agent is saving, and spec 47 depends on baselines

**Agent:** Lead · **Task:** spec 47 preparation · **Date:** 2026-09-10

**What happened.** Spec 47 step 3 requires re-running all four phase gates after registering the
engines and treating *any* change in Phases 0, 1 or 2 as a finding to have in isolation. That
needs a before-picture, so I captured Phase 0, 1 and 2 baselines before touching `bootstrap.py` —
the same discipline C used for spec 45, and C's turned out byte-identical, which is what made its
"unchanged" claim mean anything.

Mine came back with `FAIL toolchain_green` on Phases 0 and 1. Three consecutive runs named three
**different** sets of tests, all in C's `tests/verify/`:

```
run 1   FAILED tests/verify/test_phase1_criteria.py::test_the_push_budget_comes_from_config_not_from_a_literal   1 failed, 1285 passed
run 2   FAILED tests/verify/test_phase3_criteria.py::test_a_breaker_that_never_escalates_on_the_outage_is_a_fail  1 failed, 1287 passed
run 3   FAILED tests/verify/test_phase1_criteria.py::test_the_pass_message_still_reports_the_measured_time
        FAILED tests/verify/test_phase1_criteria.py::test_each_command_writes_exactly_one_row                     3 failed, 1285 passed
```

Asking pytest for the two tests named in runs 1 and 2 returned **"no tests ran"** — they no
longer exist. C is mid-edit on the Phase 1 timing criterion I assigned it, and
`test_the_pass_message_still_reports_the_measured_time` is precisely the test my own ruling asked
for. Moving names, moving totals, all in one agent's paths: the mid-save signature, exactly as the
triage note in `PHASE-3-TASKS.md` describes it. Nothing is regressed and nothing needs fixing.

**Why it is an entry rather than a shrug.** Had I taken that as the baseline and compared against
it after registering four engines, the diff would have shown Phase 0 and Phase 1 "changing" from
FAIL to PASS, and spec 47 says in as many words to treat a Phase 0-to-2 change as a finding. I
would have gone looking for a registration side-effect that does not exist — or worse, concluded
that registering the engines *fixed* two phases, which is a claim the evidence would appear to
support and which is nonsense.

**The general rule, which I have added to the triage section:** a baseline is only meaningful if
the tree is quiescent when it is taken. With three agents saving into one working tree, "before"
and "after" are not separated by your change alone. **Capture baselines when the team is idle, and
say in the entry when they were taken.** For spec 47 specifically this is not a constraint at all,
because the spec already lands last — the quiescent moment arrives on its own, and I am waiting
for it rather than working around it.

**A second-order point worth keeping.** The contaminated baseline was *legible* only because the
failures moved. A single stable FAIL from another agent's half-saved file would have looked
exactly like a real one. The thing that made this diagnosable was running it three times and
noticing the names change — which is the same two-run discipline that distinguishes this machine's
intermittent fault from an ordering dependency, applied to a third cause.

### `seed_thresholds_from_config` could silently reintroduce the defect its own docstring exists to prevent

**Agent:** Lead · **Task:** A's sweep finding 7 · **Date:** 2026-09-10

**What happened.** A reported it and flagged it to me specifically, because it sits under the
seed that all of Phase 3's `safety` evidence rests on. I reproduced it independently before
acting:

```
configured max_errors_in_window : 20
after the rename                : 10
```

**Why.** `tests/conftest.py::seed_thresholds_from_config` reads five `safety.*` values with

```python
try:
    value = config.get("safety." + name)
except KeyError:
    continue
```

`Config.get`'s own docstring is explicit that it **"raises on a miss, never returns a default,
and never returns None to mean absent"** — so `None` means present-and-null and the raise means
absent. Those are two different facts and `except KeyError: continue` collapses them into one
response. The helper's docstring carefully draws exactly that distinction — present-and-null is
left to `SeedThresholds` to default, because "the operator has not decided yet" must not become a
number this file invented — and the code does not implement the distinction it describes.

**Why it matters more than a normal test-helper bug.** The same docstring recounts the defect
this function was written to prevent: the seed scaled to `seed.py`'s shape default of 10 against
the operator's 20, and *"a Phase 3 test of engine 17's error-rate input against it found the
condition untripped and failed pointing at the engine."* Renaming or removing a `safety.*` key
returns the fixture to precisely that state, silently, and the next symptom is again a Phase 3
test failing while accusing an engine. A function whose entire purpose is to prevent a silent
wrong default had a path back to that silent wrong default.

**Fix.** An absent key now raises with the key named and the consequence spelt out, rather than
being skipped. Present-and-null still defaults, which is the case the docstring is right about.
The file's `config/default.yaml`-does-not-exist branch above is untouched: a tree with no config
at all is a legitimate state for several tests, and it is handled before this loop rather than
inside it.

**A's generalisation, which is the transferable half and is now the fifth rule.** Five of A's
eight findings are one mechanism: a fallback written when the real thing did not exist yet, still
armed, with nothing asserting the real branch is live — `try: import real / except: define our
own`, `getattr(mod, "Name", None)` then skip, and this `except KeyError: continue`. A's fix
formulation is better than the one I wrote into the standard this morning: **the fix is never to
delete the fallback — it is to add the assertion that the fallback is unreachable.** One line
saying "the real branch is the live one" turns a stale workaround into a tripwire for the day
someone breaks what it stood in for. Deleting it would have been the obvious move and would have
thrown away the tripwire.

**Scale, for the two I am not fixing.** `engine_context` does `getattr(contracts, "EngineContext",
None)` then `pytest.skip`, so a rename would skip **44 test functions across 7 files** — every
engine any of us has written, including `test_scout` — green. A rated `paper_config` lower rather
than reporting it flat, because a missing config fails loudly elsewhere and the skip would be
noise beside a real failure rather than silence. Both are C's and reported to C; the rating is the
part worth keeping, because eight findings all marked "sharp" would tell C nothing about where to
start.

### The intermittent fault is not a native memory fault — verify.py deletes other runs' databases

**Agent:** Lead · **Task:** confirming B's hypothesis · **Date:** 2026-09-10

**What happened.** B captured the traceback I asked the team for and offered a mechanism as a
candidate, explicitly unproven, having failed to make it fire on demand. I reproduced it on the
first attempt. **B is right, and the consequence is larger than the bug.**

**The mechanism.** `scripts/verify.py::sweep_stale_workspaces` globs every `acsoe-verify-*`
directory in the system temp directory and `shutil.rmtree`s it. Its docstring says:

> Best effort throughout: a directory another verify run is using right now simply will not
> delete, and that is fine — it is swept by whichever run goes last.

**That is a POSIX assumption and it is false on Windows**, in both directions at once. Windows
refuses to unlink a file that is currently *open* — but a SQLite database between connections is
not open, and a criterion that seeds a database, closes it, and reopens it to read is unlocked for
that entire window. And `ignore_errors=True` means the call does not stop when it hits something
it cannot remove: it deletes everything it can and silently skips the rest, so "will not delete"
is not merely wrong, it is guaranteed **partial** deletion.

**The reproduction, first attempt, no concurrency needed to demonstrate it:**

```
seeded, db exists: True
sweep removed: 3 dir(s)
db still exists: False | workspace still exists: False
sqlite3.OperationalError: unable to open database file
```

Note `removed: 3`. Those were not my leftovers — a single sweep took three live workspaces
belonging to whatever else was running at that moment.

**It accounts for both signatures the team has been reporting, and they are the same bug at
different moments.** If the workspace directory is gone when the next connection opens, SQLite
reports `unable to open database file` — B saw that twice, C saw it too. If the directory
survives but the file inside it was removed, `sqlite3.connect` **creates a fresh empty database**
and the next statement reports `no such table: equity_snapshots` — which is the traceback B
captured. A criterion that seeded a database and then found it empty was not confused; its
database really had been deleted, by a sibling process, between the write and the read.

**What this costs, and it is the part that matters.** For two phases this project has attributed
these to "this machine's intermittent native fault" and has written that into
`PHASE-3-TASKS.md` as standing advice: run the named test in isolation, and if it passes, say so
in the build log. That advice **worked** — the test does pass in isolation, because in isolation
nothing else is sweeping. So the mitigation confirmed the wrong diagnosis every time it was
applied. Four spurious FAILs in twenty runs while Phase 2 closed, one of them landing on the test
asserting no credential was committed; my own spurious FAIL earlier today; C's zero-byte report
file; B's four. **A real, deterministic, fixable defect has been sitting behind a folk
explanation, and the folk explanation was load-bearing enough to be written into the phase rules.**

`tests/verify/test_runner.py` calls `main()` nine times, so an ordinary `pytest tests/` sweeps the
shared temp directory nine times per run. Three agents each running the full suite is exactly the
concurrency required.

**Fix.** Not mine to write — `scripts/verify.py` is C's and C is editing it as I write this. Sent
to C with the reproduction. The shape I have asked for is to sweep only what this process could
possibly own: leftovers older than this process's own start time, which is the standard way to
garbage-collect a shared temp directory and needs no lock. Deleting *nothing* would also be
correct and is the safer half if C would rather do that first.

**What B did right, and it is the reason this was caught.** B captured the traceback before
re-running, which is the discipline nobody had managed for two phases and which I had put in the
task list only hours earlier. Then B offered the mechanism **as a candidate**, said plainly that
two direct provocations came back green, and refused to present it as more than plausible. An
honest half-answer that turns out to be right is worth more than the four confident wrong ones
that preceded it, and if B had rounded it up to a claim I would have had to discount it the same
way I discounted the native-fault story.

### A newly-named mechanism will absorb every flake in the tree unless someone stops it

**Agent:** Lead · **Task:** recording B's warning · **Date:** 2026-09-10

**What happened.** Within an hour of the sweeper being identified, B pushed back on my own
framing of it — and B is right in a way that matters more than the bug.

C reported a console-driving test failing in full runs and passing in isolation, across two
phases, recorded honestly as unexplained. B had four instances of that family this evening:

```
test_persisted_mode_is_pending_when_the_daemon_writes_no_run_row
test_persisted_mode_is_pending_without_the_store_accessor
test_live_rows_is_pending_when_the_daemon_writes_nothing
test_the_pass_message_still_reports_the_measured_time
```

**The first three failed with database errors and are the sweeper. The fourth is a timing
assertion and cannot be** — no amount of deleting temporary directories makes a measured
duration wrong. B's sentence: *the risk now is that a newly-named mechanism absorbs every flake
in the tree the way the native memory fault did for two phases.*

**Why this is the important entry and not the sweeper one.** The sweeper is a bug and it is
fixed. The failure mode B names is the one that cost two phases, and I walked straight back into
setting it up: I wrote an entry declaring the intermittent fault solved, and the immediate effect
of a satisfying explanation is that the next unexplained failure gets filed under it. That is
exactly what happened to the native memory fault — it was a real thing once, and then it became
the answer to everything that did not reproduce.

**The two stories are told apart by the same discipline that told the sweeper apart from an
ordering dependency, and there is a specific tell here.** A sweeper failure is always a
*database* error — `unable to open database file`, or `no such table` from a freshly created
empty file. C's is a **wall-clock budget** on a 500ms poll interval, in a suite that grew more
I/O-bound when spec 45 added forty-five tests, nineteen of which copy a tree. C diagnosed that
independently before the sweeper had a name and proposed the right fix: the interesting property
is a count of polls, not a duration. **Those are two defects and they must stay two.**

**Standing rule, and it is the one I will hold myself to first:** a failure is attributed to the
sweeper only if it carries a database error. Anything else is unexplained until it is explained,
and "unexplained" is an acceptable thing to write in this log — C wrote it, which is why the
timing bug was still visible as its own problem when B went looking.

### Spec 47's "Phases 0 to 2 unchanged" clause found the one thing it was written to find

**Agent:** Lead · **Task:** spec 47 · **Date:** 2026-09-10

**What happened.** Registered engines 7, 10, 11 and 17, then re-ran all four gates against
baselines taken minutes earlier on a genuinely quiet tree — the first clean baseline of the
session, and it was only obtainable because C's sweeper fix had landed. The diff is short, and
sorting it is the whole value of the clause.

**One real finding.** `tests/cli/test_entrypoints.py::test_the_registered_guard_chain_is_the_four_phase_2_engines`
asserts the guard chain is exactly the four Phase 2 engines. Registering `SafetyEngine` turns it
red, correctly. **It is a decayed assertion of the exact kind this phase has been cataloguing**:
its docstring says *"what `bootstrap` actually holds, asserted where it can be read as that
claim"*, which is a fact about what had been built on the afternoon it was written, not a
property that survives the next registration. It is the third expiring test found this phase —
after A's tripwire that pinned a value the test itself supplied, and C's criterion test asserting
PENDING because `test_scout.py` did not exist yet — and all three were written by careful agents
for good reasons.

**Two changes that are the criteria working, not findings.** `orchestrator_empty_registry` moved
from *"acsoe.bootstrap holds 4 registered engines"* to *"holds 8"*, and `is_gate_matches_registry`
from *"4 engines registered; 0 mismatches (1 gates)"* to *"8 engines registered; 0 mismatches (5
gates)"*. The second **is spec 47's acceptance clause** — four new gates matched against the Gate
column of the registry table, zero mismatches. The first is C's deliberate design: the criterion
reports the registry count while explicitly not ticking over it, so a registration is visible in
its message without changing its verdict. Both are the kind of "change" the clause is meant to
show you and then let you pass.

**One measurement, not a change.** `console_websocket_pushes_on_change` moved from 5ms to 18ms.
That is C's new form working as designed — the measured time is *evidence in the message* rather
than the assertion, precisely so that variation like this is visible without being a verdict.
Under the old form both numbers would have been compared against a 1000ms budget that was mostly
measuring connection setup.

**And the native fault is still here, which settles a question B and C both raised.** The Phase 1
baseline run carries `RETRIED AFTER CRASH: pytest CRASHED ... 0xC0000005 ACCESS_VIOLATION ... the
retry was clean`, and the Phase 2 post-registration run crashed once with `0xC0000409
STACK_BUFFER_OVERRUN` before its retry. **Neither is the sweeper**: no database error, and the
sweeper is fixed. So the phase closes with three distinct mechanisms rather than one — the
sweeper, now fixed; C's wall-clock timing assertion, now fixed; and a genuine native fault that
remains, is now *only* charged with the crashes it actually causes, and no longer has the other
two hiding behind it. B's warning that a newly named mechanism absorbs every flake was worth
making, and this run is the evidence it was not needed in the other direction either.

**Fix.** The decayed test is rewritten below rather than deleted: what it genuinely pins is worth
keeping.

## Agent A — Platform and exchange clients

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

### Six more untested refusal branches in the Kraken client, found by the tell

**Agent:** A · **Task:** branch-coverage pass · **Date:** 2026-09-10

**What happened.** The lead turned the `parse_envelope` finding into a greppable rule:
find every function in `clients/` and `platform/` with more than one refusal branch
raising the same exception type, and check that each branch has a test reaching *it*
rather than a neighbour. An AST scan found **18 such functions, 55 refusal branches**.
Disabling each branch on its own and running the tests killed 32 and left 23.

**Two of the 23 were false survivors and that matters for how this is reported.** The
first pass ran a narrow test subset per package. Re-running the survivors against a
wide set — `tests/{clients,engines,cli,platform,verify,core}` — killed
`_levels:325` and `map_order_book:347`, which are reached through the order-book
tests rather than through anything in the file they live in. **A mutation that
survives a subset has not survived; it has only not been asked.** Worth stating,
because reporting 23 would have been wrong by two and the two are indistinguishable
from the rest without the second pass.

**Six genuine survivors in `rest.py`**, all raising `KrakenUnavailableError`, all at
the boundary where the system finds out what the exchange said:

- `_decimal:241` — the value arrived as a **float**. This is the guard that stops a
  fee or a price that has already lost precision from entering the system at all, and
  `code-standards.md` opens its money section with exactly that rule. `json.loads`
  produces a float for any unquoted JSON number, so this is not a hypothetical shape —
  it is what an unquoted `0.0026` in a Kraken response becomes. Untested.
- `_decimal:247` — the value is not a decimal number at all. Untested, and invisible
  through `map_asset_pairs`, which catches the failure per pair and drops that pair, so
  removing the raise produces the same observable outcome by a different route.
- `map_asset_pairs:260` — the result was not a mapping of pairs.
- `map_asset_pairs:284` — **no pair in the response carried a complete rule set.**
  Without it an empty `PairRulesSnapshot` is returned as a success, and an empty pair
  map propagates as an empty subscription scope and an empty tradable universe — a
  system that has quietly stopped trading and reports nothing wrong.
- `_levels:329` — a level that is not a `[price, volume]` pair.
- `parse_envelope:212` — `error` is present but is **not a list**, e.g.
  `{"error": "boom"}`. The one remaining untested branch of the four in the function
  whose branch 2 started all of this.

**Why they cluster here rather than being scattered.** Every one is a guard against a
*shape* the exchange should never send, and the fixtures are all well-formed by
construction, because they were written to exercise the mapping rather than to attack
it. `AGENTS.md` says any remembered Kraken shape is stale, which is the argument for
these guards existing; nothing was arguing for testing them. The same reasoning that
makes the guards right makes them easy to leave unexercised.

**Fix.** A test per branch, each asserting the message so it cannot drift onto a
neighbour — the same rule that found the first one. Then each mutated again to confirm
it is killed.

## Agent B — Store and trading logic

### This file is a reconstruction from here to the fixture rewrite, and says so

**Agent:** B · **Task:** spec 40 · **Date:** 2026-09-10

**What happened.** The IDE crashed with me mid-repair of `engines/cost/`. The source edits
survived on disk; this file was an empty stub. On resumption I was asked to write down what I
still remembered before continuing.

**Why this heading exists.** I do not remember it. The session is gone, and a resumed agent
claiming recall of reasoning it is actually re-deriving from the diff would put fabricated
provenance into dissertation material — which is worse than an absent entry, for the same
reason spec 40 gives for deleting a test rather than editing it down until it passes.

So the next two entries are **reconstructed from the code that survived plus spec 40 and
invariant 2**, and are marked as such. What is genuinely lost, and what I want counted as the
cost of the crash rather than quietly absorbed: whether any alternative reading of engine 1's
payload was tried and rejected before the one on disk, and whether anything about the seam
surprised me while I was in it. If the answer to either was "yes", it is gone. The entries
below are what the artefact can still be made to say, not what I knew.

### Engine 10 read three `state["exchange"]` paths that engine 1 has never published

**Agent:** B · **Task:** spec 40 · **Date:** 2026-09-10
· *Reconstructed after the crash — see the entry above.*

**What happened.** Every input the cost gate takes from engine 1 was read from a key that does
not exist on engine 1's payload. `EXCHANGE_FEES_KEY` was `"fees"`; `ExchangeState` publishes
`fee_tier`. The two rate fields were read as `maker_pct` / `taker_pct`; `FeeTierSnapshot.
state_dict()` writes `maker_fee_pct` / `taker_fee_pct`. And `_fallbacks()` read
`exchange["fallbacks_used"]`, which no engine writes at all.

The first two are a `BLOCK` on every live tick — and the least useful kind of fail-closed
there is, because the gate refuses everything for the wrong reason and says so in prose naming
a key nothing writes. The third is worse in a quieter way: `_fallbacks()` returned `()` on
every tick and nothing anywhere raised, so invariant 2's "every decision affected by a
fallback records which fallback fired" was being satisfied by a read that could never have
found anything.

**Why.** I wrote those paths during the Phase 2 overlap, against an engine 1 that did not
exist yet, and I recorded them in `contracts.py` under a heading saying the state paths *"are
ratified"*. They were not. What the lead ratified on 2026-09-09 was a set of **positions in
the cross-chain key table** — which engine publishes which value, under which state key. That
table says the fee tier arrives on `state["exchange"]` from engine 1. It does not fix engine
1's field names and never did. The field names were mine, and calling them ratified is what
made them stop being questioned.

It stayed invisible for a whole phase because `build_state` in `tests/engines/test_cost.py`
hand-builds `state["exchange"]` in exactly the shape this engine expects. Both sides passed
their own tests while disagreeing with each other. That is the third time this project has hit
that shape — the command reader tested only through a store double, the criterion held against
a fabricated `EngineContext` whose body never ran, and now this.

**Fix.** `EXCHANGE_FEE_TIER_KEY = "fee_tier"`, and the two rate field names lifted out of
`_read_inputs` into `FEE_MAKER_FIELD` / `FEE_TAKER_FIELD` beside it — they were string
literals buried in a call, so nothing pointed at them and the next mismatch would have been
found the same way this one was. The `fallbacks_used` read is **deleted rather than repointed
at `failed_fetches`**, which is the decision in this repair worth arguing rather than just
recording: the two look interchangeable and are opposites. A fallback is a value the system
substituted and then traded on; a failed fetch is a value it never got. Copying one into the
`rejections.fallbacks_used` column would put a number in the audit trail that nothing
substituted, and would misreport precisely the thing invariant 2 wants recorded. After spec 37
retired the fee-tier row of the paper-mode table there is no fee-tier fallback in any mode, so
the honest content of that column for this engine is empty — and it is kept, empty, because it
is a real column that engine 19 fills.

`failed_fetches` is still read, for one purpose: when the fee tier is missing and
`trade_volume` is named in it, the operator sentence quotes *that call's* reason. "missing
exchange.fee_tier" is true and sends the operator to look at `state`, where they find a `None`
that tells them nothing.

**Consequence.** The module docstring of `cost/contracts.py` now carries the ratified-versus-
assumed distinction as a table, because "the lead ratified this" was load-bearing enough to
stop three wrong field names being checked for a phase, and the correction is worth more than
the tidy version of it.

### The cost fixtures had agreed with the old engine, so the repair turned the suite red

**Agent:** B · **Task:** spec 40 · **Date:** 2026-09-10

**What happened.** With `contracts.py` and `engine.py` rewritten against engine 1's real
payload, 15 of `tests/engines/test_cost.py`'s tests fail. Every one of them blocks with
`cost_inputs_unavailable` instead of reaching a net-edge comparison. `build_state` still emits
`exchange.fees.maker_pct` and `exchange.fallbacks_used`, so the fixture is now the only thing
in the tree still speaking the old shape.

**Why.** This is the audit's own subject appearing as a red suite, and the direction is
correct: the fixture agreed with the engine, so the pair moved together and neither noticed
the publisher. Now the engine has stopped agreeing with it and the disagreement is loud. It is
deterministic and reproduces in isolation — nothing to do with this machine's intermittent
native fault, and the standing "re-run the named test before you believe it" advice does not
apply.

**Fix.** `build_state` no longer builds the payload at all. It takes engine 1's published
payload as its first positional argument, and a `publish_exchange` fixture produces that by
running A's real `ExchangeEngine` against C's `FakeKrakenClient` — the same client instance the
`engine_context` fixture already carries, so configuring the fake configures the client engine 1
is about to call. A test that needs a specific fee calls `set_fee_tier` on the fake and lets
engine 1 republish; nothing writes a fee into a dict this engine then reads.

Two decisions inside that, because neither was forced:

- **The float-refusal test corrupts engine 1's real payload rather than keeping a hand-built
  one.** Engine 1 cannot currently publish a float — every money value goes through
  `money_text` — so there is an argument that the test has no subject. It is kept because the
  validator between the two engines *accepts* a float silently, so the gate must not depend on
  the publisher staying careful, and the place the dependency would surface is the fourth
  decimal of a hurdle comparison. Starting from the real payload and corrupting one field is
  the honest way to say that.
- **The ruling is enforced mechanically, not just obeyed.** `test_no_fixture_in_this_file_
  hand_builds_the_exchange_payload` reads its own source and refuses to find any of engine 1's
  payload keys written as a quoted key followed by a colon. It exists because the cheap way
  back to green was to rename `"fees"` to `"fee_tier"` inside the old fixture, which would have
  left the seam exactly as untested as it was.

**Consequence, and one thing that went wrong on the way.** That guard failed on its first run,
on its own docstring: the docstring quoted the literal it was searching for. The pattern is now
assembled from a bare name at runtime and the prose describes the shape instead of quoting it.
Worth recording because it is the same shape as `code-standards.md`'s standing `RUF001` example
— a file that contains the thing it is checking for is a fixture for itself, and the check has
to be written knowing that.

`tests/engines/test_cost.py` is 31 tests, all green, and no test in it hand-builds
`state["exchange"]`.

### Deleted `test_cost.py:376` rather than editing it: the assertion has no subject left

**Agent:** B · **Task:** spec 40 · **Date:** 2026-09-10

**What happened.** `test_a_fallback_that_fired_is_carried_into_the_decision` asserted
`data["fallbacks_used"] == ["fee_tier_assumed_tier_1"]`. It is deleted, on the operator's ruling
of 2026-09-10 and spec 40's instruction, and deliberately not edited.

**Why.** Spec 37 retired the fee-tier row of invariant 2's paper-mode table, so there is no
longer a tier 1 fallback for this gate to apply, in any mode. The test was not asserting a
detail that moved; the thing it was about stopped existing. Editing it down until it passed
again — dropping the list contents, asserting the field is present, asserting it is empty
because a fee was assumed — would produce a test about nothing that still *reads* as coverage of
invariant 2's recording requirement, and coverage that is not there is worse than coverage that
is absent, because the absent kind gets noticed.

**Fix.** Deleted, with a comment left at the site saying what stood there and why it went, so
the next reader does not re-add it. In its place is
`test_this_engine_applies_no_fallback_and_says_so_by_recording_none`, which is a different
assertion with a real subject: `fallbacks_used` is empty on a priced tick **and on a blocked
tick where engine 1 published a failed fetch**. The second half is the one worth having. That is
the tick where copying `failed_fetches` into the column would look like diligence, and it is the
mistake the deleted read had already made once.

**Consequence.** Second deletion of this kind in the project — spec 32 was the first — and the
shape is the same both times: an invariant changed, and the test that encoded the old one had no
honest rewrite. Recorded here rather than in a commit message because a commit says a test was
removed and cannot say why removing it was better than fixing it.

### Engine 11 sized against a price that nothing in the system publishes

**Agent:** B · **Task:** spec 41 · **Date:** 2026-09-10

**What happened.** Three findings in engine 11, and the third is a different kind of thing from
the other two.

`EXCHANGE_PAIRS_KEY` is `"pairs"`, so the engine read `state["exchange"]["pairs"][pair]`. Engine
1 publishes `pair_rules`, which is itself `{fetched_at, pairs: {...}}`, so the real path is one
level deeper. And `_fallbacks()` read `exchange["fallbacks_used"]` — the same dead read spec 40
found in the cost gate, returning `()` on every tick.

The third is not a renamed field. `PAIR_PRICE_FIELD` is `"last_price"`, read off that pair-rules
mapping, and **nothing anywhere in this system writes a price into `state["exchange"]`.** Engine
1 publishes balances, the fee tier and the pair rules; `AssetPairs` carries no price and engine 1
does not fetch one. The only `last_price` in the codebase is a column on an open position row,
which is a different fact about a different thing. So there was no key to correct: the input
did not exist.

**Why.** Same root as spec 40, one step worse. The paths were written during the Phase 2 overlap
against an engine 1 that did not exist, and `test_risk.py`'s `build_state` hand-built
`state["exchange"]` in the shape the engine expected — including a `last_price` field it invented
for the purpose. A hand-built fixture cannot notice that a field has no publisher, because
supplying it is what the fixture is for. The pair-rules nesting is the ordinary version of that
mistake; the price is the version where the mock did not merely agree with its caller, it
*conjured the input*.

Worth separating from the fee-tier case for the record: a wrong field name is a block on every
live tick, which is loud once anything runs. A field nobody publishes is also a block on every
live tick, and looks identical from the outside — but the repair is a decision rather than an
edit, because someone has to choose which price sizing uses.

**Fix.** `EXCHANGE_PAIR_RULES_KEY = "pair_rules"` with `PAIR_RULES_PAIRS_KEY = "pairs"` beside
it as its own constant rather than folded into a dotted path, so a null `pair_rules` — the
failed-`AssetPairs` case — reports as the missing snapshot it is rather than as an unknown pair.
Both levels go through `_require`. The `fallbacks_used` read is deleted, as in spec 40.

The price comes from `state["market_sensor"]["quotes"][pair]`, the same publisher engine 10
reads its spread from, with the ask sizing the quantity and the bid valuing it for `costmin`.
That is the lead's ruling and the reasoning is in `engines/risk/README.md` under a heading
saying it was ruled, because the next agent needs to be able to tell a decision from a default.

`RiskInputs` now carries `ask` and `bid` as separate fields and never blends them into a mid.
`RiskSizing` gained `value_at_bid` alongside `notional`, which was a judgement rather than a
requirement: `notional` is `qty x ask`, the cash the order commits, and `value_at_bid` is
`qty x bid`, the figure `costmin` was actually tested against. The old code computed one number
and published it under the other's name, which was harmless while there was one price and would
have put the number a decision was *not* made on into the record of that decision.

**Consequence, and the check that made me trust it.** The two prices are one character apart in
the source, so the tests that assert the ruling had to be shown to discriminate rather than
merely pass. Three mutations, each reverted: sizing from the bid (caught by 6 tests), valuing
`costmin` at the ask (caught by the 2 written for it), and dropping the mode check on the
balance fallback (caught by the live-mode test alone, which is why it exists). A mid-price
implementation gives 29.62962962 units on the wide-spread fixture against the ask's 26.66666666,
so the exact-`Decimal` assertion separates all three readings rather than two.

### Invariant 2's last surviving paper-mode fallback had no implementer

**Agent:** B · **Task:** spec 41 · **Date:** 2026-09-10

**What happened.** After spec 37 retired the fee-tier row, invariant 2's paper-mode table has
exactly one row that is still a fallback: balance. Pair rules block, the spread blocks, the fee
tier now blocks. **Nothing in the system implements the one that is left.**

**Why.** It fell into a gap between two correct decisions. Engine 1 deliberately applies no
fallback of its own — its own docstring says the fallback is the *consumer's* decision because
the consumer is the one that has to record which fired — and engine 11, the consumer, read a
`fallbacks_used` key that engine 1 never published and treated a missing `balances` as a plain
missing input. So both engines behaved as if the other one owned it. Nothing raised, because the
fail-closed path is the same shape as the unimplemented one: a failed `Balance` fetch blocked,
which is right in live mode and wrong in paper.

The reason it stayed invisible is that no test ever produced the state it happens in. Engine 1's
tests assert the failure is *reported*; engine 11's tests hand-built `balances` and so could not
omit it without also removing the pair rules.

**Fix.** `RiskEngine._balances` is the implementation, and it distinguishes three cases where
the old code saw one:

- `balances` published: use it. A currency **missing from a published map** is not a failed
  fetch — it is an account that holds nothing in that currency — so it blocks and never reaches
  the fallback. That distinction is the one most likely to be lost in a later refactor, so it
  has its own test.
- `balances` absent, mode `paper`: `paper.starting_balances`, with
  `balance_from_paper_starting_balances` recorded on the decision.
- `balances` absent, any other mode: block.

`_read_inputs` now returns the fallbacks alongside the inputs rather than having them
recomputed later, because invariant 2 requires the *decision* to record which fallback fired and
there is exactly one place that knows: where the substitution happened. That is also why a
**rejection** produced on a fallback tick carries it too — rejections are the rows this system
produces most of, and a research dataset that could not say a tick was priced against a
configured balance rather than a fetched one would be missing the thing invariant 2 asks for.

Two gaps recorded in the `README.md` rather than closed here. The map is used **exactly as
configured**: invariant 2 says "adjusted by simulated fills" and the fill simulator is Phase 6,
so a paper account that has traded sizes against its starting balance until then. And a
fallback map that does not name the pair's quote currency is a refusal, not a substitution of
nothing for something — it blocks and names the currency.

### Decision: `replay` mode blocks on a failed balance fetch, and that is mine rather than ruled

**Agent:** B · **Task:** spec 41 · **Date:** 2026-09-10

**Options.** `EngineContext.mode` is `paper | live | replay`. Spec 41 names two of them: paper
falls back, live blocks. Replay is unmentioned, and invariant 2's table is headed "in paper
mode". So either replay falls back with paper, or it blocks with live.

**Chose.** Blocks. `if context.mode != PAPER_MODE` rather than `if context.mode == "live"`, so
the fallback is opt-in by name and any mode added later blocks until someone decides otherwise.

**Because.** Invariant 2's table is explicitly a *paper-mode* table and replay is not paper; a
gate that is unsure refuses, per invariant 3; and blocking is the direction that cannot be
unsafe. Writing the condition as "not paper" rather than "is live" is the half that matters —
the second form silently extends the fallback to every future mode, which is the shape this
project has already been bitten by twice.

**Cost, and it is real.** If replay is later supposed to reproduce paper-mode behaviour
faithfully, this makes a replayed tick block where the live paper run fell back, and the two
runs diverge exactly where invariant 10's "faithful replay" property is supposed to hold.
Nothing in Phase 3 exercises replay, so the cost is deferred rather than paid. **Flagged to the
lead as an implementer's reading and not a ruling** — it is one line and one constant to
reverse, and this entry is what it should be read against.

### My own progress file said the ruling was applied. The code says it was not

**Agent:** B · **Task:** spec 42 · **Date:** 2026-09-10

**What happened.** `context/progress/b-store.md` carries the ruled `CONDITION_ACTION` table
under a heading reading CLOSED, ending "Applied in spec 42 on 2026-09-10". I was told on
resumption to verify that against the code rather than trust the note. It is not applied.
`engines/safety/contracts.py` still carries the pre-ruling table — `DRAWDOWN` and `LOSS_STREAK`
both mapped to `CLOSE_ALL` — under a comment block headed **PROVISIONAL — awaiting a lead
ruling**.

**Why.** The progress file is written *before* the work, which is what made it survive the
crash, and that same property is what let it describe work that had not happened yet. It is not
a lie and it is not a mistake in the note: "claimed 2026-09-10" and "applied 2026-09-10" were
written in the same edit, and only one of them was true at the time. Nothing distinguishes a
claim from a completion in that file's format.

The consequence is worth stating plainly, because it is the interesting half: had I trusted the
note, the pre-ruling table would have survived spec 42 — the spec whose entire first step is to
apply it — and every seeded test would have gone on passing, because on the seed the *outage*
also trips and emits `close_all` regardless of what the drawdown row says. The wrong table was
invisible behind a correct answer arrived at for the wrong reason.

**Fix.** The table applied, and the PROVISIONAL comment block replaced with the ruling and its
authority. Beyond that, a change to how I write the progress file: a spec is marked complete
there only after its gates are green, never in the same edit that claims it.

### The seed's outage hides the seeded drawdown, and the anchor is why

**Agent:** B · **Task:** spec 42 · **Date:** 2026-09-10

**What happened.** Spec 42 requires the seeded drawdown to emit a `freeze` and **no**
`close_all`, asserted as an absence. On the seed that is not directly assertable: the seed
carries a drawdown of 0.20 against a 0.10 limit *and* 18 consecutive `data_guard` ticks against
a limit of 15, so the outage trips on the same tick and the outage is the one condition that
still escalates. A tick that emits `close_all` on the seed proves nothing about the drawdown.

**Why, and this is the part that is not obvious.** Whether the seeded outage counts depends on
the `cycle_id` the tick is anchored at, and the existing tests all use 1.
`stored_data_guard_outage_excluding_current_tick` walks backwards requiring each stored tick to
be `(run, cycle - 1)` of the one after it — **except when `cycle == 1`**, where the tick before
is the last tick of some previous run, is unknowable, and the crossing is therefore allowed so
that a daemon dying mid-outage does not reset the clock. That rule is correct and is exactly
what invariant 14 asks for. It also means an anchor of `("run-fresh", 1)` — a run that has
never written a row — is treated as the first tick after a restart and silently adopts the
seed's trailing outage. Measured: 18 at `cycle_id=1`, **0** at `cycle_id=2` or later, where the
adjacency check breaks immediately.

**Fix.** The drawdown-freezes tests anchor at `cycle_id=2` and say why in the test docstring;
the outage tests keep `cycle_id=1`, where crossing the restart is the property being tested. So
the two conditions are separated by the fixture rather than by hoping they do not overlap, and
`test_the_seeded_drawdown_freezes_and_emits_no_close_all` is a real absence rather than a
coincidence. The four conditions also each got a block and a pass test **in isolation on a
fresh database**, because on the seed all four trip at once and a command emitted against it
says nothing about which condition produced it — which after the ruling is the entire question.

**Consequence.** The blind spot is in the *test anchor*, not in the store method — the method's
docstring already states the restart-crossing rule and calls its residual over-count out
explicitly. What it does not say, and what cost me a probe to establish, is that the rule makes
`cycle_id=1` a special anchor for *any* fresh `run_id`, which is the shape every test in this
file happened to use.

### A guard-chain test counted pending commands, so it could not have failed

**Agent:** B · **Task:** spec 42 · **Date:** 2026-09-10

**What happened.** `test_safety_guard_chain.py`'s helper read the emitted commands through
`store.pending_commands()`. The assertion it fed was "one liquidation, not one per tick" —
across two real orchestrator ticks. It passed. It would also have passed against an engine that
emitted a `close_all` on every single tick.

**Why.** The orchestrator claims and consumes a command at the top of the next tick, which is
the behaviour the test exists to exercise. So by the end of tick two the row `safety` wrote on
tick one is no longer pending, and `pending_commands()` returns an empty tuple whether the
engine emitted one row or fifty. The assertion was `len(rows) <= 1` against a list that was
always empty.

This is the shape `code-standards.md` has just been amended to name — a double or a reading
that cannot exhibit the property under test — arriving through the *query* rather than through
a fake. Nothing here was mocked; the store was real, the orchestrator was real, and the reading
was still incapable of failing.

**Fix.** The helper reads every row off the `commands` table with `source = 'safety'`, claimed
or not, and the assertion is now an equality on the sequence of commands rather than a bound on
a count. It caught a second thing immediately: what the second tick suppresses is the *freeze*,
not the `close_all` I had predicted in the docstring. `cycle_id` is 2 on that tick, the outage
walk breaks at the adjacency check, and the outage stops tripping — so drawdown and loss streak
are what remain, and they are suppressed because the mode is already `frozen`.

**Consequence, and it is the Phase 3 / Phase 4 boundary rather than a fixture artefact.** In a
running system tick 1's `data_guard` block would be written to `block_records` by engine 19
`memory` in the manage chain, and tick 2 would find it and continue the outage. Engine 19 is
Phase 4 and is not in this chain, so nothing records the tick and the count does not carry. The
test now says that in as many words instead of asserting a suppression reason that happens to
be right for the wrong reason.

**The deferred check came back clean.** The reason I deferred registration in Phase 2 was that
`safety` in the guard chain runs on every tick of `orchestrator_empty_registry` and
`commands_round_trip`, both against a real store, and "on an empty database nothing should
trip" had "should" doing the work. It does not trip: no equity snapshot reads as *no drawdown
measurable* rather than as zero or as a division by zero, and `safety` does not appear among
`state["guard_blockers"]`. That is the finding spec 47 needs and it is better had here.

### OPEN QUESTION: a suppressed `close_all` swallows a co-occurring `freeze`

**Agent:** B · **Task:** spec 42 · **Date:** 2026-09-10 · **Status: escalated, not fixed.**

**What happens.** `_emit` takes the strongest action among the tripped conditions and emits at
most one row — spec 42 step 6, "the more severe action wins and the two are not both emitted",
which is correct on its face. But the `close_all` branch has two suppressions of its own (no
exposure, and `close_intent` already set), and when the strongest action is suppressed
**nothing is emitted at all**, including the `freeze` a co-occurring drawdown, loss streak or
error rate would have emitted on its own.

Concretely: drawdown breached, no open position and no resting entry order, and a data outage
also running. Drawdown alone emits `freeze`. Drawdown *plus* the outage emits nothing, because
`close_all` wins and is then suppressed for want of anything to close. More bad conditions
produce less action, which is the wrong direction.

**Why it matters more after the ruling than before.** Under the pre-ruling table every
condition that could co-occur with the outage also escalated, so a suppressed `close_all` could
only ever swallow another `close_all` — the same command, so nothing was lost. The operator's
2026-09-10 ruling made three conditions emit `freeze`, and a suppressed `close_all` now
swallows a genuinely different command. The defect did not change; its reachability did.

**The bound, stated so this is not read as more urgent than it is.** `safety` returns `BLOCK`
on every tick where any condition is tripped, so the opportunity chain is stopped regardless
and nothing new is opened. What is lost is the *persistence*: the mode never goes `frozen`, so
the console shows a running system and the block is re-derived every tick rather than recorded
once.

**Not fixed, deliberately.** The obvious fix is "emit the strongest action that is not
suppressed", which is one line — and it is a change to what the breaker does, so it is the
operator's call and not mine. I am recommending that reading.

**What spec 42 added is the case, not the fix.**
`test_a_suppressed_close_all_currently_swallows_a_co_occurring_freeze` pins the current
behaviour, names itself an open question in its docstring, and asserts the bound as well as the
gap — so the escalation now has something executable attached rather than a description. If the
operator rules the other way, that test is the one that changes.

### RULED: a suppressed escalation must not swallow a freeze that was independently due

**Agent:** B · **Task:** spec 42 · **Date:** 2026-09-10 · **Supersedes the OPEN QUESTION above.**

**What happened.** The operator ruled on the open question recorded above and spec 37's successor
edit wrote it into invariant 14, committed as `db50392`:

> **A suppressed escalation never swallows a freeze that was independently due.** `safety` emits
> at most one command per tick and the more severe action wins — but `close_all` has its own
> suppressions: it is not written when there is no exposure to close, or when `close_intent` is
> already set. **When the winning action is suppressed, `safety` emits the strongest action that
> is not suppressed**, rather than emitting nothing.

**Why it is a change to behaviour and not a bug fix.** Spec 42 step 6 — "the more severe action
wins and the two are not both emitted" — is unrepealed and still true. One command per tick, and
no `freeze` alongside a `close_all` that actually emitted. What the ruling answers is the case
step 6 did not cover: what happens when the winner is suppressed. Emitting nothing was a
defensible reading of the literal spec, which is why I implemented it and escalated rather than
patching it.

**Fix.** *(pending — implementing the fall-through now, then mutating it to confirm the test
watches it.)*

**Fix.** `_emit`'s `close_all` branch now records *why* it was suppressed rather than returning
immediately, and hands off to `_fall_through`, which picks the strongest action among the
conditions that did **not** ask for `CLOSE_ALL` and re-enters `_emit` with it. Re-entering
rather than duplicating the freeze suppression is deliberate: a second copy of "only while the
mode is `running`" is a second place for it to drift. The re-entry is bounded at one further
call, because the lesser action is chosen from a set that excludes `CLOSE_ALL` by construction,
so the branch that got there cannot be reached again.

One contract change, and it is the honest one: on a fall-through the assessment carries **both**
`command_emitted` and `suppressed_because`. Everywhere else exactly one is set. A tick that
suppressed one action and emitted another genuinely did both, and an operator reading "it froze"
needs to know the outage wanted to liquidate and could not. `SafetyAssessment.action` still
records what the conditions *asked* for, so a fall-through tick reads `action: close_all`,
`command_emitted: freeze`, and the sentence naming the escalation that could not happen.

**Both boundaries are tested, because the ruling can be over-implemented as easily as
under-implemented.** "Emit the strongest action that is not suppressed" reads a lot like "always
freeze if you cannot liquidate", and that second reading would freeze a healthy account over an
outage it had no exposure to. So there is a test for the fall-through firing and a test for it
*not* firing when the outage is the only condition tripped.

**Mutated both, per the lead's instruction, and each was caught by exactly the test written for
it.** Removing the fall-through reddens
`test_a_suppressed_close_all_falls_through_to_the_freeze_that_was_due` and nothing else; making
it fire unconditionally reddens `test_the_fall_through_does_not_fire_when_the_outage_is_the_only
_condition` and `test_no_exposure_suppresses_the_escalation`. The engine is restored and the
suite is green.

**One existing test had to change, and the reason is the same defect in a different place.**
`test_no_second_close_all_while_the_outage_persists` passed `close_intent=True` with the default
`mode="running"` — a state the orchestrator cannot produce, because the command reader sets both
in the same step. It went red the moment the fall-through landed, correctly: against that
fixture a freeze genuinely was due. Setting the mode to `frozen` alongside `close_intent` makes
it the state the orchestrator actually produces, and the test now asserts *both* suppressions
rather than one. That is the second time in this spec a fixture has been holding a state the
system cannot reach — the first was the freeze idempotency test — and both times the new
behaviour is what exposed it rather than review.

### Correction: the faithful-replay property is not invariant 10

**Agent:** B · **Task:** spec 41, follow-up · **Date:** 2026-09-10

The decision entry above on `replay` mode cites invariant 10 for the property that a replayed
tick must reproduce the live one. That citation is wrong. **Invariant 10 is "No look-ahead,
ever"**, which is a different rule about features and labels. The property I meant is stated in
`src/acsoe/core/contracts.py` — "what makes replay faithful and look-ahead structurally
impossible" — and in invariant 9, which injects the clock for that reason.

Recorded as a new entry rather than by editing the old one, per rule 6. It matters because the
entry is addressed to whoever builds replay in Phase 4, and a wrong citation sends them to a
rule that does not answer their question.

The lead also supplied a fact that shrinks the deferred cost I recorded there:
`platform/config.py` **refuses `mode: replay` at load** — "Phase 0 accepts mode: paper only;
replay is built in Phase 4". So no tick can reach that branch today in any mode but paper, and
the divergence I was worried about cannot occur before Phase 4 builds replay and decides
deliberately. The ruling stands: keep `!= "paper"`.

### The affordability check compares two currencies, and nothing publishes a rate

**Agent:** B · **Task:** spec 43 · **Date:** 2026-09-10 · **Status: escalated, not guessed.**

**What happened.** Spec 43 makes the balance one of the filter's arithmetic inputs, and the
comparison that uses it is "does the account hold enough of this pair's quote currency to fund
the position this equity would size". Writing it exposed that the two sides are in **different
currencies**: `target_notional` derives from equity, which invariant 7 expresses in
`trading.base_reporting_currency`, while the balance is in the pair's quote currency. For a
USD-quoted pair on a USD-reporting account they coincide; for a EUR- or BTC-quoted pair they do
not, and comparing them is meaningless.

**Why it was not visible before.** Engine 11 `risk` carries the identical comparison and has
since spec 35 — `notional > inputs.quote_balance` — and no test has ever exercised it on a pair
whose quote is not the reporting currency, because no fixture has one that gets that far.
Crypto-quoted pairs are excluded by policy before the check, and there is no fiat-quoted pair in
a second currency anywhere in the committed fixtures. So the defect is two engines old and was
found by writing the third caller rather than by anything failing.

Invariant 7 says PnL and equity are converted "at the trade timestamp", so the intent is clear
and the mechanism is simply absent: **nothing in this system publishes an FX rate.**

**Fix.** The comparison is asked only when `facts.quote == reporting_currency`, and the reason
is a comment at the call site rather than a silent condition. **I did not invent a rate and did
not assume parity**, and I did not mint a seventh exclusion rule for "cannot be converted"
either — that would be inventing trading behaviour under cover of being careful, and the lead's
own ruling on A's crypto-quoted heuristic is the precedent: a rule that fails conservatively
passes every test we have and then quietly shrinks the universe on real data.

**What that leaves, stated plainly rather than left to be discovered.** With the check skipped,
a non-reporting-currency pair could enter the universe without being shown affordable. That is
the *over*-including direction, which is the wrong one for `scout` by the lead's own reasoning.
It is unreachable today — `allow_crypto_quoted` is false and no fixture has a second fiat quote
— but it becomes reachable the moment the operator enables crypto-quoted pairs, and my own
`test_a_crypto_quoted_pair_is_excluded_unless_the_operator_allows_it` flips exactly that flag.
So the test that proves the flag is the only thing excluding `ETH/BTC` is also the test that
walks through the gap.

Escalated to the lead with that stated. Nothing is blocked: everything else in spec 43 is built
and green.

### Scanning source text for a forbidden symbol flagged the invariant that forbids it

**Agent:** B · **Task:** spec 43 · **Date:** 2026-09-10

**What happened.** Engines 10 and 11 each carry a guard that reads their own module's source
text and asserts no remembered fee or order minimum appears in it. I wrote the same shape for
`scout` — no pair name, no remembered pair rule — and it failed immediately on the word `BTC`.

**Why.** The match was in `scout`'s own docstring, quoting invariant 7: a crypto-quoted pair is
one whose quote is *"BTC, ETH, or any non-stable asset"*. That quotation is not decoration — it
is what explains why there are two crypto-quoted reason codes rather than one, which is the
least obvious decision in the module. The only ways to satisfy a text scan are to delete the
reasoning or to paraphrase the invariant until it stops matching, and both make the file worse
to protect a check that was never about prose.

Same shape as `code-standards.md`'s standing `RUF001` example, where the ambiguous glyph **is**
the fixture for the rule that flags it: a rule that is right in general and wrong on the one
line that is the fixture for it.

**Fix.** The guard parses the module's AST and inspects string literals that are not
docstrings, instead of scanning raw text. That checks what the Locked Decision actually forbids
— a symbol or a pair rule used as a *value* — and comments do not survive into the AST at all,
so it is stricter than the text scan rather than looser. Verified by mutation: it still catches
a symbol written into a literal.

Deliberately **not** retrofitted to engines 10 and 11. Their guards are for numeric constants
that would never legitimately appear in prose, they are green, and changing a working check in
two other engines to match a decision made in a third is the kind of tidying that turns one
spec into three. Noted here so the next person to write one of these knows both shapes exist
and why.

### Decision: a named constant lost to a criterion that asks the serialiser instead

**Agent:** B · **Task:** spec 43 · **Date:** 2026-09-10

**What happened.** `universe_varies_with_balance` reported PENDING with *"acsoe.engines.scout.
contracts declares no UNIVERSE_FIELD naming where the universe is published"*. I added that
constant, re-ran the gate, and it turned **two** criteria red rather than green: C's criterion,
having found the universe key, drives `scout` with a `state` carrying only `state["exchange"]`
— no `market_sensor` quotes and no store — so the engine reached a fail-closed BLOCK and the
criterion reported *"engine 7 published no 'pairs'"*.

**Why that was worth thinking about rather than just fixing.** The choice was between a FAIL
that said "the engine is wrong" and a PENDING that said "this criterion is not finished". The
second is the accurate one — my engine was built and green; the criterion could not yet feed it
— and the standing rule is that a FAIL is a stop for every agent on a shared gate. So I reverted
the alias inside a few minutes, kept the constant under an honest name, and sent C the exact
recipe: engine 3's output, a store with an equity snapshot, and a stream double, because
`FakeKrakenClient` implements neither `recent_trades` nor `latest_quote`.

**Options, once C had that.** Add the alias C's criterion looked for, or have the criterion read
the name some other way.

**Chose: neither, and C's answer is better than both.** C's criterion now *asks* the model — it
serialises a `ScoutUniverse` carrying a sentinel pair through `to_state_data()` and takes the
key whose value contains it. The name is derived from my own serialiser, so a rename follows
automatically and there is no literal on either side to drift.

**Because** the alias would have been a second copy of a string that already exists, agreed by
two agents and maintained by neither. That is the shape the Phase 3 audit is about: four retyped
field names on `state["exchange"]` survived a whole phase because every test agreed with whoever
wrote it. A constant is only protection when one side owns it and the other reads it; when both
sides *declare* it, it is just a mock agreeing with its caller wearing a `Final` annotation.

**Cost.** `PAIRS_FIELD` exists and is used by my serialiser, so there is still one name in one
place; nothing outside this module reads it, which makes it weaker than it looks. If a future
consumer wants a constant rather than a probe, it should import this one rather than declare its
own — that is the whole point.

**Consequence, and it is a note about process rather than code.** I introduced a known FAIL to
the shared gate deliberately, having predicted it, and reverted it within minutes. I would not
do that again: the right order was to send C the recipe first and land the constant once the
criterion could consume it, which is what I did on the second attempt. Predicting a break is not
the same as having permission to cause one.

### A captured traceback for the intermittent test failures, and a candidate mechanism

**Agent:** B · **Task:** spec 43, aside · **Date:** 2026-09-10

**What happened.** Running the gate at a task boundary, `toolchain_green` failed four times in a
row naming a **different test each time**, and one of them was mine —
`tests/db/test_migrations.py::test_malformed_migration_sets_are_refused[0002_second.sql-contiguous]`.
Every one passed in isolation. The lead has asked repeatedly for a captured traceback before
anyone re-runs, because re-running to confirm green is what has destroyed the evidence every
previous time. So I captured one.

**The reproduction, which is the part that was missing.** Serially the suite is green — I ran
the migration test alone three times and the full suite twice, all green. **Four concurrent
pytest processes over `tests/db tests/clients/store tests/verify` produced one failure**, and
this is its traceback:

```
tests/verify/test_phase3_criteria.py::test_a_criterion_clocked_off_the_seed_sees_the_seeded_error_rows
outcome = Outcome(result=FAIL,
    message='criterion raised - OperationalError: no such table: equity_snapshots')
```

A criterion seeded a database and then found that database with no tables in it. Together with
the `OperationalError: unable to open database file` I saw twice earlier the same day, the
family is clear: **temporary databases disappearing underneath the process using them**, not
logic, and not the native memory fault that is separately known.

**Candidate mechanism, stated as a candidate because I could not make it fire on demand.**
`scripts/verify.py`'s `main()` calls `sweep_stale_workspaces()`, which `shutil.rmtree`s **every**
`acsoe-verify-*` directory in the system temp directory. Its docstring says "a directory another
verify run is using right now simply will not delete, and that is fine" — which holds on POSIX,
where an unlinked open file keeps working, and **does not hold on Windows**, where a SQLite file
that is merely between operations is deleted happily. There is a recursion guard for the
`toolchain_green` subprocess, so the nested case was considered; two *independent* runs were
not. And `tests/verify/test_runner.py` calls `verify_module.main(...)` **nine times**, so an
ordinary `pytest tests/` sweeps the shared temp directory nine times per run.

Three agents each running the full suite against one working tree, plus `verify.py` spawning its
own toolchain subprocess, is exactly the concurrency that turns that into someone else's missing
table.

**I did not fix it and did not try.** `scripts/verify.py` and `tests/verify/` are C's, and this
is a diagnosis rather than a patch. Two direct provocations — two concurrent `verify.py` runs,
and a loop of `test_runner.py` against the criteria tests — both came back green, so the
mechanism is **plausible and unproven**, and I would rather hand over an honest half-answer than
a confident wrong one.

**What is solid, and it is worth separating from the speculation:** the failures are real,
deterministic under concurrency, absent when serial, and every observed instance is a temporary
database vanishing. That is a different fault from the native memory fault in the seed write path
recorded in `docs/build-log/phase-0.md`, and it should not go on inheriting that one's
explanation — which is what "re-run it and it goes green" has been doing.

### RULED: a pair whose affordability cannot be computed is excluded, not skipped

**Agent:** B · **Task:** spec 43, follow-up · **Date:** 2026-09-10
· **Supersedes the FX entry above.**

**What happened.** The operator ruled on the currency-mismatch gap I escalated: a pair whose
affordability cannot be computed is **excluded from the universe, under its own reason code**,
rather than having the check quietly skipped. Engine 11 `risk` refuses such a candidate under
the same code.

**Why the ruling went against my reasoning, which is the part worth keeping.** I declined to
mint an exclusion because it would be "inventing trading behaviour under cover of caution", and
cited the lead's refusal of A's crypto-quoted heuristic as the precedent. **The precedent cuts
the other way**, and the distinction the lead drew is one I had collapsed:

- What was refused to A was **inventing a fact about the world** — a heuristic that would
  *claim* to know which quotes are crypto, and be wrong on real Kraken data.
- **Excluding a pair you cannot prove affordable claims nothing.** It asserts no rate, no
  parity, no classification. It says only that the question was not answerable.

The second is the same shape as the ruling that already existed for `scout` — a quote that is
not provably stable is excluded — which I had implemented an hour earlier without noticing it
was the answer to my own question. My analysis had even said the residue was the over-including
direction and that this was the wrong direction for `scout`; I stopped one step short of the
conclusion that followed from it.

**Fix.** `REASON_NO_FX_RATE = "no_fx_rate"` in both engines. In `scout` it is an exclusion
placed between the tick-grid rule and the affordability comparison — affordability cannot be
*compared* before it can be *computed*. In `risk` it is a rejection before the quote-balance
check, and the sentence names both currencies, because "no exchange rate" without saying
between what is the useless kind of true.

**The test that broke is the best evidence the hole was real.**
`test_a_crypto_quoted_pair_is_excluded_unless_the_operator_allows_it` asserted that flipping
`allow_crypto_quoted` admits `ETH/BTC`. It no longer does — BTC is not the reporting currency —
and that test was, as I had told the lead when escalating, the one walking straight through the
gap. It is rewritten to assert the flag moves the pair from one exclusion to a *different* one,
which is a stronger claim than "the flag was the only thing" and the true one.

Added `test_a_pair_quoted_in_another_currency_cannot_be_shown_affordable`, on a **EUR**-quoted
pair, because that is the case the ruling is actually about: EUR is in
`stable_quote_currencies`, so the crypto flag is irrelevant to it and only the missing rate
refuses it. The crypto-quoted test reaches the same rule only by disabling a policy.

**One assertion I got wrong on the way, and the engine was right.** I asserted the EUR fixture
would count two `no_fx_rate` exclusions — the EUR pair and `ETH/BTC`. It counts one:
`crypto_quoted` fires first, because a pair is attributed to the first rule it fails. That
ordering is the tally working as designed, and telling an operator "the operator disabled this"
is more useful than "we lack a rate for a pair you disabled anyway".

**Consequence.** It costs nothing today — no pair reaches it while `allow_crypto_quoted` is
false and every fixture quote is the reporting currency — which is the point rather than a
caveat. The hole is closed before the flag is ever turned on, and the flag was one line away in
my own test suite.

### A mutation showed three ordering tests proving less than their docstrings claimed

**Agent:** B · **Task:** spec 44 · **Date:** 2026-09-10

**What happened.** The lead asked for the ordering to be mutated: *"a sort that is stable by
accident rather than alphabetical by construction will pass a single fixture."* I replaced
`rank_universe`'s `sorted(pairs)` with `tuple(pairs)` — arrival order — expecting the three
behavioural ordering tests to go red. **All three stayed green.** The only thing that caught
it was a one-line unit assertion inside a test about something else.

**Why.** The engine builds its scan set as `sorted(set(rules) | set(quotes))` and appends
survivors in that order, so `rank_universe` is *always* handed an already-ordered sequence. A
ranking that merely preserved arrival order therefore answers alphabetically anyway. My
shuffle test rebuilds the published mappings in reverse and rotated order — but the engine
re-sorts them before ranking, so the shuffle never reaches the function under test.

The two sorts are defence in depth in the engine and I am keeping both; a gate that orders its
own scan deterministically is right. What was wrong was the **claim**:
`test_the_candidate_is_stable_under_a_shuffled_input_mapping` said in its docstring that it was
"the assertion carrying the ordering" and that an accidentally-stable sort "would give the same
answer on every fixture whose insertion order happens to be alphabetical". The first half was
false and the second half described precisely the case it could not detect.

**This is the shape I have spent the phase catching in other people's work**, and the lead's
instruction is the only reason I found it in mine. Reading the test would not have revealed it —
the docstring is persuasive and the test does something real. Only breaking the code did.

**Fix.** `test_rank_universe_orders_by_name_and_not_by_arrival` calls the function directly
with reverse-alphabetical input, so arrival order and name order disagree on every element
rather than on one; it asserts the whole tuple rather than the head, because a ranking that
returned the right head for the wrong reason would pass the weaker form; and it asserts
idempotence, because a ranking that reversed on each call would satisfy a single invocation.
Re-mutated: it now goes red, along with the seam test.

The shuffle test is **kept** — spec 44 asks for it directly and end-to-end insensitivity to
mapping order is genuinely worth having — with its docstring rewritten to say what it proves
and, explicitly, what it does not and why. The blind spot is named in `scout/README.md` too,
because the next person to change the ordering will read that before they read the tests.

**Consequence.** Two of the three claims I have had to withdraw today were about my own tests
rather than my own code, and both were caught by mutation rather than review. The engine has
been right every time; the prose about it has not.

## Agent C — Interface, criteria and models

### `verify.py` threw away every line of toolchain output on one non-UTF-8 byte

**Agent:** C · **Task:** spec 45 · **Date:** 2026-09-10

**What happened.** Capturing the pre-spec-45 baseline, `--phase 0` printed

```
FAIL    toolchain_green              pytest exit 1: (no output)
```

and, above the banner, an unhandled `UnicodeDecodeError: 'utf-8' codec can't decode
byte 0x97 in position 3880: invalid start byte` raised inside a `subprocess`
`_readerthread`. The same run under phases 1, 2 and 3 printed the full list of failing
tests. The verdict was right in every case — the tree is genuinely red from A's and B's
in-flight work — but on phase 0 the *reason* was gone.

**Why.** `_run_tool` (`scripts/verify.py:1264`) calls `subprocess.run(..., text=True)`
and names no encoding, so the child's bytes are decoded with whatever
`locale.getencoding()` returns for this process. Byte `0x97` is an em-dash in cp1252,
which is what pytest emitted, and it is not a valid UTF-8 start byte. The three
baseline phases ran under the default locale and decoded it as an em-dash. Phase 0 I
happened to run with `-X utf8`, which flips the same call to strict UTF-8, and the
decode raised **on the reader thread** rather than at the call site — so
`subprocess.run` returned an empty `stdout` and an empty `stderr` instead of
propagating, and `_run_tool` handed back `(1, "")`. `check_toolchain_green` rendered
that as `(no output)`. The gate reported a FAIL it could not explain, which is the one
thing the standing rule about never piping this script through `tail` exists to
prevent.

It is latent rather than exotic: `PYTHONUTF8=1` is a common Windows setting, and any
operator who has it on loses all toolchain detail from every phase, not just phase 0.
The mirror-image bug exists in the default locale — a genuinely UTF-8 byte in a tool's
output mojibakes silently rather than raising.

**Fix.** Pending — see the next entry.

*(Fix, completing the entry above.)* `_run_tool` and `_interpreter_with_toolchain` now pass
`encoding="utf-8", errors="replace"` explicitly to `subprocess.run`. The decode is
deterministic regardless of the operator's codepage or UTF-8 mode, it cannot raise, and a
byte that is not valid UTF-8 costs one replacement character instead of the whole report.
`errors="replace"` rather than `errors="strict"` on purpose: the output is diagnostic prose
for a human, and one mangled dash in a pytest summary is worth incomparably more than a
clean exception that deletes the summary. Every other read in this file already names
`encoding="utf-8"`; these two calls were the only place an encoding was inherited.

### A crash mid-run printed nothing at all, including the criteria that had already passed

**Agent:** C · **Task:** spec 45 · **Date:** 2026-09-10

**What happened.** The first baseline capture ran `--phase 0` with stdout redirected to a
file. The process died — exit 139, the bash rendering of the 0xC0000005 access violation
this machine is known for — and `phase0.txt` was **zero bytes**. Not truncated: empty. Six
criteria had run and four of them had already reached a verdict, and none of that reached
disk. I re-ran it and got a clean 7 PASS, so the fault was the known intermittent one and
not a defect in any criterion.

**Why.** Two causes, and only the second is mine to fix. Redirected stdout is
block-buffered, so nothing is flushed until the buffer fills or the process exits cleanly —
a hard crash discards it. But the deeper reason is `main`: it builds the entire report
**after every criterion has run**, with a single `print(format_report(...))` at the end. So
even line-buffered, a run that dies on criterion 4 of 7 prints nothing, because there is
nothing to print yet. The verdicts exist only inside a list comprehension until the run
finishes.

That matters more here than it would in most scripts. This gate is the one place the
project looks to decide whether a phase is real, `PHASE-3-TASKS.md` tells every agent never
to pipe it through `tail` because the detail is what makes a FAIL diagnosable, and this
machine has a documented intermittent fault that kills processes mid-run. Those three facts
together mean the run most worth reading is exactly the run that prints nothing.

**Fix.** `format_report` is split into `report_header`, `criterion_line` and
`report_summary`, and `main` now prints the header, then each criterion's line as that
criterion returns, flushing each one, then the summary. `format_report` is kept and
composes the same three pieces, so the unit tests that call it directly still hold and the
**bytes on stdout are identical to before** — the report is not reformatted, only emitted
progressively. The one thing that had to move is the column width, which `format_report`
computed from the finished results; it is computed from the criterion *names* instead,
which are known before the first check runs, so a streamed line lands in the same column
the batched one did.

A crash now leaves every verdict up to the crash on disk, and the missing tail is itself
the evidence of where it died.

### A criterion that reads `pending_commands()` cannot see a command the daemon has already obeyed

**Agent:** C · **Task:** spec 45, criterion 4 · **Date:** 2026-09-10

**What happened.** `safety_freezes_on_drawdown_without_opportunity_chain` drives the real
orchestrator over the seeded database with `safety` alone in the guard chain, ticks three
times, and asserts one `freeze` row was written and no `close_all`. It reported

```
the breaker tripped on the seeded drawdown and wrote no `freeze` row. Commands written: []
```

while `tripped` correctly carried `drawdown`. Engine 17 was doing exactly the right thing
and the criterion could not see it.

**Why.** Two causes, one after the other, and both are the criterion's.

The first is that a daemon starts `idle`, and `safety` does not re-emit a `freeze` for a
system that is not running — correctly, because freezing something already stopped is a
no-op and would append a row every tick forever. The criterion was ticking an orchestrator
nobody had activated, so it was asking whether the breaker stops a system that was already
stopped. Fixed by writing a real `activate` row to the `commands` table before the first
tick, the way the console writes one, and letting the real command reader apply it — which
has the side benefit of exercising the console-to-reader-to-breaker path rather than
asserting around it.

The second survived that fix. The helper read `store.pending_commands()`, which by
definition returns rows **nobody has claimed yet**. The orchestrator's command reader runs
at the top of every tick: the `activate` is claimed and consumed on tick 1, and the `freeze`
that `safety` writes during tick 1 is claimed and consumed at the top of tick 2. By the
third tick both rows are consumed and `pending_commands()` is empty — which is not "no row
was written", it is "every row was obeyed". The criterion was reading a *queue* and asking
it a question about *history*.

B's `tests/engines/test_safety.py` uses the same helper shape and is right to: those tests
call `SafetyEngine.process` directly, so no reader ever runs and nothing is ever consumed.
The moment a criterion puts a real orchestrator around the engine, the queue empties behind
it. This is a general hazard for anything in `verify.py` that drives a daemon rather than an
engine, and `check_commands_round_trip` already reads the `commands` table directly through
SQLite for the same reason — I had the precedent in front of me in this file and reached for
the store accessor anyway.

**Fix.** `_safety_command_rows` reads the `commands` table directly, selecting every row
whose `source` is `CommandSource.SAFETY` ordered by `id`, claimed or not. The source value
comes from B's enum rather than the string `'safety'`, for the same reason the exposure
query now takes its three status values from `PositionStatus`, `OrderStatus` and
`OrderIntent` — see the next entry.

**Consequence.** Criterion 4's idempotency assertion is now a claim about what was written
over three ticks rather than about what is still queued, which is what "re-emits no command
while the condition persists" actually means. Worth carrying into Phase 4: engine 19
`memory` will write to this table too, and any criterion asking "did this get written" must
read the table, not the queue.

### `safety_inputs_all_from_the_seed` was comparing zero against zero on one of its six inputs

**Agent:** C · **Task:** spec 45, criterion 6 · **Date:** 2026-09-10

**What happened.** The criterion went green with the message

```
all six inputs match the seeded tables (drawdown 0.2000..., 8 losing trade(s),
0 error block(s), 18 outage tick(s), 2 position(s), 2 resting order(s))
```

Five of those numbers are evidence. `0 error block(s)` is not. `--phase 0`'s
`seed_fixtures_present` reports **23** ERROR blocks in the seed, so the criterion and the
engine had agreed on a number that is wrong on both sides.

**Why.** The criterion clocked its `EngineContext` at `PHASE3_NOW`, a fixed instant I chose
so two runs a week apart give the same verdict. The seed's rows are stamped at the seed's
own epoch, which is earlier, and `safety`'s error-rate input is "ERROR rows inside
`safety.error_rate_window_s` counted back from `context.now`". At my instant that window
lands entirely after the seeded rows and contains none of them. The engine returned 0 and
the criterion's own SQL, using the same window, also returned 0.

This is precisely the failure mode spec 45 warns about in as many words — *"would it still
pass if the thing it names were false?"* An engine that ignored the error-rate input
entirely and returned a hardcoded 0 would have passed this criterion, and so would one that
read the wrong table. Two independent computations agreeing on zero is not agreement about
anything; it is both of them looking at an empty set. A fixed clock is the right instinct
for determinism and the wrong one for a fixture whose rows carry their own timestamps.

**Fix.** `_seed_now` reads the newest `block_records.ts` out of the seeded database and
criteria 4 and 6 clock themselves from that instead. It is still deterministic — the seed is
generated from a fixed seed value, so the instant is the same on every machine and every run
— but it is now the seed's instant rather than one I picked, so the error window contains
the rows it is supposed to contain. The other five inputs are unaffected: drawdown, loss
streak, positions and resting orders are not time-windowed, and the outage walk is anchored
on `(run_id, cycle_id)` rather than on the clock.

**Consequence.** A criterion asserting `reported == expected` needs one more question asked
of it than "do they match": *can this comparison distinguish anything?* Both sides being
derived from the same wrong assumption is the shape that survives review, because the code
looks like it is checking something. The other five comparisons here were fine only because
the seed's values for them are large and specific.

### The `safety` criteria were seeding against the seed module's defaults, not the operator's config

**Agent:** C · **Task:** spec 45, criteria 4, 5 and 6 · **Date:** 2026-09-10

**What happened.** With the clock fixed, criterion 6 reported **13** ERROR blocks where
`--phase 0`'s `seed_fixtures_present` reports **23** over what is nominally the same seed.
Both numbers are right; they are two different fixtures.

**Why.** `seeded_console_db` calls `seed_database(db_path)` with no `thresholds` argument, so
the seed scales its fixtures against `seed.py`'s module defaults. Those defaults are
documented as "fixture-shape constants, not recommended values", and one of them has
diverged: the default `max_errors_in_window` is 10 where `config/default.yaml` says 20. The
seed overshoots whatever limit it is given by three, so the default-scaled fixture holds 13
ERROR rows — which overshoots 10 and sits comfortably under 20, so the *configured* error
rate never trips against it. `check_seed_fixtures_present` already avoids this by building
`SeedThresholds` from the config through `_seed_threshold_kwargs`; `seeded_console_db` was
written for the console criteria, which do not care what the thresholds are, and I reused it
for three criteria that care a great deal.

Nothing was failing, which is what makes it worth writing down. All three criteria passed
against the default-scaled seed. The defect is latent and it is in the direction the seed
exists to prevent: **the moment the operator raises a limit, the criteria stop testing what
they claim to.** `safety_escalates_on_sustained_outage` asserts the seeded outage run is at
least `safety.max_consecutive_data_blocks` long; the default-scaled run is 18 and the
configured limit is 15, so it fits today. Raise `max_consecutive_data_blocks` to 20 and the
criterion FAILs, accusing the seed of being too short — while the config-scaled seed it
should have been reading would have carried 23. `_seed_threshold_kwargs`'s own docstring
describes exactly this: "a fixture pinned to a constant stops overshooting the moment the
operator raises a limit, and the criterion accuses the seed of a bug the criterion caused."

B independently found the same defect in the shared `seed_fixtures` fixture in
`tests/conftest.py` — also mine — and shadowed it locally in `tests/engines/test_safety.py`
rather than depending on it. That is two places now, from two directions, which says the
convenience helper is the wrong default rather than that either caller was careless.

**Fix.** `_phase3_seeded_db` seeds through the same config-derived `SeedThresholds` path
`seed_fixtures_present` uses, and criteria 4, 5 and 6 call it instead of
`seeded_console_db`. `seeded_console_db` is left alone: the console criteria genuinely do
not care, and changing it would be a Phase 1 and Phase 2 change inside a Phase 3 spec.

**Still open, and not mine to close inside this spec.** The shared `seed_fixtures` fixture in
`tests/conftest.py` has the same defect and spec 45's scope limits keep me out of it. Raised
to the lead as its own item.

### The induced failures: what each of the seven criteria was made to fail against

**Agent:** C · **Task:** spec 45 · **Date:** 2026-09-10

Spec 45 requires each criterion observed PENDING, observed PASS and **observed FAIL**, with
the induced failure recorded here — *"a check nobody has seen fail is a comment."* All
twenty-one observations are in `tests/verify/test_phase3_criteria.py`; this is the account of
what was broken to produce the FAIL half and what it cost to learn.

**How the failures are induced, and why it is not a fabricated tree.** `phase3_tree` copies
the **real** `src/acsoe`, the real `db/migrations/`, the real `config/` and the real harness,
and a FAIL is induced by changing exactly one string in one real module in the copy. The
alternative — fabricating an engine to be wrong — is what `check_data_guard_blocks_bad_data`
did, and its fabricated `EngineContext` agreed with the criterion's own mistake so precisely
that the criterion's body never executed while both halves of its two-sided proof passed.
`patch_module` refuses to apply when its anchor is not found exactly once, so a test cannot
silently degrade into asserting that the criterion fails for some unrelated reason.

**`cost_gate_uses_live_fee_tier`** — four failures. A cost engine with the fee schedule
compiled in as module constants, otherwise a faithful implementation of invariant 5 that
blocks below the hurdle; this is what `AGENTS.md` opens by warning about, and it is why the
criterion runs two tiers rather than one. An engine reading the maker fee and forgetting the
taker fee, which moves the net edge with the tier but by the wrong amount — this is why the
criterion asserts the *exact* fee delta rather than "the two differ", and it would otherwise
have accepted a gate mispricing every candidate in the system by the taker leg. `clears =
True`, a gate that lets everything through. `clears = False`, a gate that refuses
everything, which the block half alone would accept. A fifth case is not a FAIL and is the
interesting one: pointing `EXCHANGE_FEE_TIER_KEY` back at the audit's wrong `"fees"` makes
the engine fail closed with `cost_inputs_unavailable`, and the criterion reports **PENDING
naming spec 40** rather than FAIL — that is unfinished wiring, not a broken gate, and a FAIL
there would stop the phase over work in flight.

**`risk_rejects_sub_ordermin`** — three. A gate that bumps a sub-minimum size *up* to
`ordermin` and approves it instead of refusing, which is the failure the second half of the
criterion exists for and the reason "no order was placed" is not a sufficient assertion: it
places a trade at a size nothing sized. A gate that refuses and publishes the quantity
anyway — this needed **two** patches, because `to_state_data` omits the four sizing fields
when `approved` is false *and* `qty` is `None` on a rejection, so either alone leaves the
payload unchanged; `_reject`'s own docstring names this refactor ("a field a later refactor
could quietly start filling with `ordermin`") as the thing to guard against, so the induced
defect is exactly that refactor. And a gate refusing for `below_costmin` instead of
`below_ordermin`.

That last one is worth its own note, because the first version of the test was worthless. I
induced it by renaming the constant `REASON_BELOW_ORDERMIN` in `risk/contracts.py` — and the
criterion reads *that same constant* to decide what it expects. Renaming it moved the
expectation and the answer together and the test passed while proving nothing: the exact
"mock that agrees with its caller" shape this phase exists to correct, reproduced by me,
inside the test written to prove I had not done it. The patch now goes in the **engine**, at
the `_reject` call site, so only the answer moves.

**`universe_varies_with_balance`** — one, against a fabricated engine 7 since none exists: a
filter that runs, publishes a universe and never looks at the balance, which a criterion
checking only that a universe came back would accept. The stand-in's real rule had to be
chosen with some care. `held >= costmin` does not discriminate over the committed fixtures —
every pair's `costmin` is 5.00, so $10 and $5,000 both admit all four pairs and the PASS half
failed. It now requires the balance to fund `costmin` on every concurrent position the
operator allows, which is invariant 7 crossed with a configured limit rather than a constant
invented in a test.

**`safety_freezes_on_drawdown_without_opportunity_chain`** — two, plus a PENDING. A breaker
that emits `close_all` where spec 37's ruling says `freeze`, induced by leaving
`CONDITION_ACTION` correct and changing `command_for` — the shape a half-applied ruling
leaves behind, where the policy is corrected and the code reading it is not. And a breaker
with its emission suppression removed, which appends a row every tick forever; the criterion
ticks three times for exactly this. The PENDING case restores the pre-ruling
`CONDITION_ACTION[DRAWDOWN] = CLOSE_ALL` and asserts the criterion waits and names spec 42
rather than failing B for work not yet claimed.

**`safety_escalates_on_sustained_outage`** — three. `>` weakened to `>=` on the outage
comparison, which fires the breaker a tick early and liquidates an account over an outage
that has not reached the operator's threshold; this is the half usually missing and a
criterion asserting only the escalation passes against it. The outage mapped to `freeze`, so
the breaker declines the one thing invariant 14 reserves for it. And the outage walk ordered
by `cycle_id` instead of `ts`, which interleaves the seed's two `run_id`s — the seeded run
spans a restart on purpose and this is the defect that arrangement exists to catch.

**`safety_inputs_all_from_the_seed`** — two, and they catch different things. A breaker that
prefers a `state["memory"]` payload when one is present: it would pass every test written
against a database and read nothing on a live tick, and only the poisoned-state half notices
it. A breaker returning a hardcoded loss streak of 0: the poisoned half **cannot** catch that
one, because a constant does not move when `state` moves either, and it is the
compare-against-the-seeded-rows half that does. Neither half is redundant.

**`phase_3_gates_have_both_tests`** — two. A gate whose tests all assert `BLOCK` and none
assert `OK`, parametrised across all four engines so a failure names which. And the one the
criterion's design is for: two tests named `test_it_blocks_on_a_wide_spread` and
`test_it_passes_on_a_tight_spread` whose bodies are `assert True`. A criterion grepping test
*names* calls that complete. This one parses the AST and looks for the assertions, in both
the `EngineStatus` and the `blocks_trading is True/False` spellings — engines in this repo are
tested in both styles, and recognising only one would report a gate as untested because of
the assertion style its author happened to prefer.

**What the exercise actually bought.** Two of the twenty-one observations found real defects
in criteria that were already green: the `REASON_BELOW_ORDERMIN` self-agreement above, and
the zero-against-zero comparison recorded in its own entry earlier. Both were criteria that
looked right, passed against the real engines, and were checking less than they claimed.
Neither would have been found by writing more PASS cases.

### A Phase 1 timing test failed once under the full suite and passes in isolation

**Agent:** C · **Task:** spec 45 · **Date:** 2026-09-10

**What happened.** With spec 45's criteria and tests landed, one `--phase 1` gate run reported

```
FAIL toolchain_green  pytest exit 1: FAILED
  tests/verify/test_phase1_criteria.py::test_pass_against_a_fabricated_console[console_websocket_pushes_on_change]
  1 failed, 1197 passed
```

In the same run, the criterion that test drives **passed** at the top level, reporting a push
508ms after the watermark moved. Run in isolation three times it passed in 8.07s, 1.65s and
2.19s. Recording it rather than smoothing it over, per `PHASE-3-TASKS.md`.

**Why.** I do not think this is the machine's intermittent native fault, and it is worth
saying so because the standing advice on a FAIL — re-run the named test alone — gives the
same answer for both and the two want different responses.

`console_websocket_pushes_on_change` asserts a push arrives inside a **1000ms budget** against
a console polling at `console.poll_interval_ms`, 500ms in the committed config. That is a
factor of two of headroom, measured on a machine also running the rest of the suite. It is a
wall-clock assertion, and wall-clock assertions get slower under contention rather than
wrong. The isolated runs took 1.65s to 8.07s for the same eight parametrised cases, which is
itself a fivefold spread on an idle machine.

**What I think my part in it is.** Spec 45 added 45 tests, nineteen of which copy the package,
the migrations, the config and the harness into a temporary tree. The suite went from 1052 to
1197 tests and got measurably more I/O-bound, and the flake surfaced on the first full run
after that. The sensitivity was already there; I made it likelier to fire. I have narrowed
the copy to `src/acsoe` rather than all of `src/`, which drops the editable install's
`acsoe.egg-info` from nineteen copies a run — a small improvement, not a fix.

**Fix.** None, deliberately. Widening the budget or adding a retry would be **changing a
Phase 1 criterion**, which spec 45's scope limits forbid in as many words, and doing it
inside a Phase 3 spec is exactly how a timing assertion gets quietly loosened until it
asserts nothing. Raised to the lead as its own item instead. My view, for whoever picks it
up: the honest fix is to stop measuring the budget in wall-clock time under a shared CPU —
the interesting property is "the push happens on the first poll after the watermark moves",
which is a count of polls and does not care how loaded the machine is. The 1000ms is standing
in for two poll intervals and could say so directly.

**What I am not claiming.** One observation is not a pattern. If it recurs on a run where
nothing else is loading the machine, that is evidence for the native fault instead and this
entry is wrong; a later entry should say so rather than this one being edited.

### Decision: how each criterion decides between PENDING and FAIL when its subject exists but is not wired

**Agent:** C · **Task:** spec 45 · **Date:** 2026-09-10

**Options.** Three of the four Phase 3 engines existed when the criteria were registered but
were not wired to engine 1, and `safety`'s policy table still carried the pre-ruling
`CONDITION_ACTION`. `try_import`'s rule — a module of ours that is not written is PENDING, a
missing third-party dependency is FAIL — does not reach that state, because the module *is*
written. So each criterion had to choose: judge the engine as it stands and report FAIL, or
detect the unwired state and report PENDING.

**Chose.** PENDING, named to the spec that will land the wiring, and detected from the
engine's **own answer** rather than from a version marker. `cost` and `risk` both fail closed
with `cost_inputs_unavailable` / `risk_inputs_unavailable` when handed a `state["exchange"]`
whose keys they do not recognise, so the criteria drive engine 1's real payload in and treat
that specific reason code as "spec 40 / spec 41 is not done" — quoting the engine's own
operator sentence in the PENDING line. `safety` has no equivalent, so criterion 4 reads
`CONDITION_ACTION[DRAWDOWN]` and reports PENDING naming spec 42 while it is not `FREEZE`.

**Because.** Mid-phase the bar is no FAIL and a FAIL is a stop at any point in a phase. A
criterion that goes red the moment another agent's in-flight work is halfway landed stops the
phase over work that is progressing normally, and the agent whose spec is named cannot fix it
except by finishing — at which point it goes green on its own. That is what PENDING is for.
The reverse risk, that PENDING becomes a way of not noticing, is answered by what the PENDING
is keyed on: each one is keyed to the *engine's own refusal*, so the criterion starts judging
behaviour the moment the engine stops refusing. Nobody has to remember to switch it on.

**Cost, and it is real.** A genuinely broken gate that happens to fail closed for one of
those reasons reports PENDING rather than FAIL, and would keep reporting PENDING. The
mitigation is that the PENDING message quotes the engine's own reason verbatim rather than
saying "not wired yet", so a reason that is not the expected one is visible in the gate
output rather than hidden behind a category. `test_a_cost_gate_that_cannot_read_engine_one_is_pending_not_a_fail`
pins the behaviour so it is a decision rather than an accident.

**It expired within the session, which is the point.** B landed specs 41 and 42 while spec 45
was being built, and both criteria came off PENDING and started judging behaviour without
anything of mine changing. Criterion 4 in particular went from PENDING to a real FAIL — the
freeze row was not being written — and that FAIL was correct and led somewhere, twice: first
to a daemon nobody had activated, then to a criterion reading the command queue instead of
the command table. A criterion that had reported FAIL from the start would have been noise
for the hours before that and indistinguishable from the FAIL that mattered.

### Correction: `tests/conftest.py` was already fixed, and I escalated it without opening the file

**Agent:** C · **Task:** spec 45, follow-up · **Date:** 2026-09-10

**Correcting the entry above**, "The `safety` criteria were seeding against the seed module's
defaults". Per rule 6 this is a new entry rather than an edit to that one.

**What that entry got right, and it still stands.** `seeded_console_db` in `scripts/verify.py`
genuinely did call `seed_database` with no `thresholds`, my three `safety` criteria genuinely
were reading a default-scaled seed, and the fix — `_phase3_seeded_db`, taking the same
config-derived path `seed_fixtures_present` uses — is real. I verified that one empirically:
13 ERROR rows before, 23 after, against a configured limit of 20.

**What it got wrong.** It also said the shared `seed_fixtures` fixture in `tests/conftest.py`
had the same defect, and I raised that to the lead as its own item. It does not. At HEAD it
reads:

```python
return seed.seed_database(tmp_path / "acsoe.sqlite", thresholds=seed_thresholds_from_config())
```

The lead checked it, then ran the fixture and counted **30 non-`data_guard` block rows out of
55** — 13 is what the module defaults would give. `tests/conftest.py` was last touched in
`3765e0d`, which is my own Phase 2 commit for specs 32 and 33, and its docstring already
describes the 13-row bug in the past tense.

**Why I believed otherwise.** B's `tests/engines/test_safety.py` carries a fixture whose
docstring says it "deliberately shadows the shared `seed_fixtures` fixture in
`tests/conftest.py`, which calls `seed_database` with no `thresholds` argument", and ends
"Reported to C, who owns the shared fixture". That was true when B wrote it. I read it,
recognised the shape from the defect I had just found in my own file, treated the two as one
finding, and escalated — **without opening `tests/conftest.py`.** Two independent-looking
reports of the same defect felt like corroboration; one of them was a note about the past.

**The generalisation, and it is not really about this fixture.** A comment describing another
agent's state goes stale silently, because nothing fails when it does. B's `cost/contracts.py`
docstring went stale the same way in the same week — "deliberately not in C's `REASON_PROSE`
yet; C has been asked to add it", while B's own test had been asserting the opposite for days
— and I caught that one only because I went to action the request and looked at the file
first. Here I did not, and the direction was reversed: B's note said a thing was broken when
it was fixed, and mine then said the same. The lead has since seen the mirror image, a
progress file claiming a ruling had been applied when it had not.

Three notes, three drifts, in both directions, in one phase. The rule that follows is the
lead's and I am adopting it: **re-check the file before citing a defect from any note,
including my own.** Reading is what produced the wrong belief; only running it produced the
right one.

**Consequence.** The item is struck from `context/progress/c-interface.md` rather than left
for the next reader to act on. No code changes — `_phase3_seeded_db` was the right fix for
the defect that was real, and `tests/conftest.py` needs nothing.

### Spec 46: the enumeration, broken on purpose, and the empty state that does not read the tally

**Agent:** C · **Task:** spec 46 · **Date:** 2026-09-10

**Seven codes added to `REASON_PROSE`**, all with the producing agent's wording kept
verbatim: engine 7's six new per-exclusion codes plus `scout_inputs_unavailable`, and
`safety_inputs_unavailable` on B's explicit yes. `below_ordermin`, `below_costmin` and
`insufficient_quote_balance` needed nothing — `scout` reuses engine 11's codes deliberately
rather than minting parallel ones, which is right: it is the same arithmetic and should read
the same on screen, and two codes for one condition would give the operator two different
sentences depending on which gate got there first.

**The enumeration reads the module's attributes, not its `EXCLUSION_REASONS` tuple, and the
difference is load-bearing.** The tuple is the exhaustive list of ways a *pair* can be
excluded, ordered by the filter's own application order, and B deliberately keeps
`scout_inputs_unavailable` out of it: that code is a statement about the tick rather than
about a pair, and counting it in the tally would break `scanned == entered + sum(tally)`. A
test enumerating only the tuple would therefore have left exactly that code unmapped — and
it is the one an operator meets when something is *broken*, as opposed to when the market is
merely quiet. So `declared_reason_codes` walks `vars(module)` for `REASON_*` strings, which
covers a code whether or not B remembers to put it in the tuple, and a separate test pins
both halves of B's arrangement: the code is in `REASON_PROSE` *and* is not in
`EXCLUSION_REASONS`.

**I broke the check before trusting it**, per the standing rule the lead added to
`code-standards.md` today. Two ways, because they prove different things:

1. Against a fabricated module carrying a code absent from the table — `unmapped()` returns
   it, which shows the *mechanism* discriminates.
2. By deleting the real `barriers_below_tick_size` line from `format.py` and running the
   suite. Two tests went red with
   `AssertionError: assert {'REASON_TICK_GRID_TOO_COARSE': 'barriers_below_tick_size'} == {}`,
   and the entry was restored. That is the one that matters: the first test would still pass
   against a hand-written list, and the whole argument for enumerating is what happens when a
   code is *added*.

A third test records why any of this is worth doing — `operator_reason("quote_delisted_mid_tick")`
returns "No reason was recorded." No exception, no log line, no degraded rendering. The
failure mode is silence in the column whose entire job is to say why.

**`quote_not_provably_stable` is the one I would have got wrong**, and the test now pins the
distinction rather than just the presence. It exists beside `crypto_quoted` on the lead's
spec 43 ruling because a universe that shrank *by policy* and one that shrank because nobody
supplied `trading.stable_quote_currencies` look identical from the outside, and only the
second is a fault somebody must fix. Two codes rendering the same sentence would undo that
ruling in the view layer, where nothing else would notice — so
`test_the_two_crypto_quoted_codes_do_not_share_a_sentence` asserts the sentences differ and
that the second one points at configuration rather than at the market.

### Spec 46 step 5: the empty state does not read engine 7's tally, and the gap is structural

**What happened.** Step 5 asks me to confirm the existing counts-based empty state reads the
tally B publishes in `state["scout"]`, and to say so in the build log if it does not. **It
does not.** `ConsoleReader.feed_summary` in `src/acsoe/console/reader.py:462` builds four
stages and the first two are hardcoded absent:

```python
FeedStage(label="Pairs scanned", count=None, detail=_NOT_RECORDED),
FeedStage(label="Entered the tradable universe", count=None, detail=_NOT_RECORDED),
```

So the screen `ui-context.md` describes as the single most-viewed state in the product —
*"Scanned 412 pairs. 38 entered the tradable universe."* — currently renders its first two
lines as not recorded. Per the spec's scope limits I have not touched it.

**Why, and this is the part worth recording rather than the mismatch itself.** It is not a
wiring oversight, and it is not one line. **The console is a separate process that reads
SQLite; it never sees `state` at all.** B publishes the tally into `state["scout"]`, which
lives in the daemon's memory for the duration of a tick. For the console to render it,
something has to persist it — and the engine that writes engine output to the store is
engine 19 `memory`, which is Phase 4. `feed_summary` deliberately shows `None` rather than a
zero for exactly this reason, and its docstring says so: a zero in that column would read as
"no pair qualified", which is a *result*, when the truth is that nobody counted. That
judgement is right and should survive whoever wires this up.

**One thing in that docstring is wrong and it is mine.** It says "the universe filter is
engine 4 and its counts are Phase 2". The universe filter is engine **7** `scout` and it is
Phase **3** — engine 4 is `data_guard`. I wrote that in Phase 1 when the numbering was less
settled in my head. It is a comment rather than behaviour, and correcting it is a change to
`console/reader.py` inside a spec whose scope limits say "do not rebuild, restyle or extend
the empty state; report a mismatch, do not fix it inside this spec". I am reporting it here
and to the lead rather than reaching for it, because the honest version of that fix is the
same change that wires the tally up, and it wants to be one task in Phase 4 rather than a
stale comment corrected now and a rewrite later.

### A spec 45 test asserted a fact about the calendar rather than a property of the criterion

**Agent:** C · **Task:** spec 45, follow-up during spec 46 · **Date:** 2026-09-10

**What happened.** B landed `tests/engines/test_scout.py` for spec 43, and
`test_both_tests_passes_against_the_real_tree_for_the_three_built_gates` went red:

```
assert <Result.PASS: 'PASS'> is <Result.PENDING: 'PENDING'>
  Outcome(PASS, 'every Phase 3 gate has a test asserting it blocks and one asserting
  it passes (block/pass per engine: cost 10/3, risk 17/4, safety 6/4, scout 2/1)')
```

The criterion did exactly the right thing — engine 7's tests arrived carrying both
directions, so it came off PENDING and passed, with no change to `verify.py`. My test was
what broke.

**Why.** It asserted `assert_pending(...)` and `"test_scout.py" in outcome.message`, because
when I wrote it that was the state of the tree. That is a fact about what had been built by
lunchtime, not a property of the criterion, and it had a guaranteed expiry date — the whole
point of registering the criterion was that somebody would land that file. It is the same
defect as a fixture pinned to a literal threshold, which this phase has already produced
twice: correct on the day it is written, wrong the moment the thing it describes moves, and
red for a reason that has nothing to do with a defect.

**Fix.** Rewritten as `test_both_tests_never_fails_against_the_real_tree`, which asserts the
durable property instead: against the real repository the criterion must **never FAIL**, and
if it is PENDING the message must name a `tests/engines/test_*.py` path so the operator is
not left guessing what the gate waits for. A FAIL there would mean a gate has a test file
carrying only one direction, which is a real defect in somebody's tests; that is the thing
worth asserting and it holds whatever B has landed so far.

**Worth carrying.** The PENDING half of every two-sided proof is vulnerable to this in a way
the PASS and FAIL halves are not, because PENDING is by definition the state a subject is
*passing through*. The other six PENDING tests in that file are safe because they build their
own tree with the subject deliberately absent — `unbuilt_tree` and friends — rather than
relying on the real repository still lacking it. This was the one that asserted PENDING
against `repo_root`, and it is the one that expired.

### `universe_varies_with_balance` was under-supplying `state`, and the first missing input hid the rest

**Agent:** C · **Task:** spec 45, follow-up when engine 7 landed · **Date:** 2026-09-10

**What happened.** B landed `engines/scout/`, the criterion came off PENDING and started
judging for real, and it reported

```
FAIL universe_varies_with_balance  engine 7 published no 'pairs' at the $10.00 balance;
                                   the universe is what every later gate iterates over
```

which is a true sentence and an unhelpful one. Driving B's engine directly:

```
status: BLOCK  reason: Scout could not read the pairs it needs: missing market_sensor is absent
data: {"reason_code": "scout_inputs_unavailable"}
```

The engine was right. My criterion built a `state` carrying only `state["exchange"]`, and
engine 7 reads the live book per pair as well — it needs a bid and an ask to value a
position, the same way engines 10 and 11 do. It also reaches the store for an equity
snapshot. I had supplied none of that, so the gate fail-closed exactly as invariant 3 says
it should, and my criterion accused it of publishing no universe.

**Why it matters beyond the missing key.** Two things, and the second is the one worth
keeping.

The first is that this is the wrong verdict, not merely a wrong message. An engine that
cannot reach its inputs is unfinished wiring or an under-supplied caller; it is not a filter
that ignores the balance, which is what `universe_varies_with_balance` exists to catch. I had
already built the guard for this on `cost` and `risk` — both report **PENDING naming their
spec** when they answer `*_inputs_unavailable` against a real payload — and wrote a decision
entry about why. `scout` did not get the guard because `scout` did not exist when I wrote it,
so the one criterion registered furthest ahead of its subject was the one missing the
protection that being ahead of your subject requires.

The second is A's finding, relayed by the lead the same day, arriving from a different
direction: **a fail-closed path with several possible causes tells you only that one of them
fired.** A's `test_a_private_call_without_credentials_blocks_rather_than_defaulting` built a
client missing two things, the first raised before the check the test was named for, and both
raise the same type — green for a phase, asserting nothing. Here the same shape appears in a
criterion rather than a test: `scout` raises `MissingInputError` for an absent
`market_sensor`, an absent `exchange`, an unreachable store, a missing equity snapshot, a
null config key and a currency mismatch, and every one of them renders as the single code
`scout_inputs_unavailable`. Fixing only the market-sensor half would have moved the failure
to the next missing input and told me nothing I had not already guessed.

**Fix.** Two changes, and the second is the general one:

1. The criterion now supplies the full opportunity-chain `state` engine 7 actually reads —
   engine 1's real payload, plus quotes built through engine 3's real `QuoteView` for every
   pair engine 1 publishes — and hands it a real `StoreClient` over the config-scaled seed so
   the equity snapshot is there.
2. It reports **PENDING naming spec 43** when engine 7 answers `REASON_INPUTS_UNAVAILABLE`,
   **quoting the engine's own sentence verbatim**. That sentence is what distinguishes
   "missing market_sensor" from "no equity_snapshots row yet", and without it the PENDING
   would be the same undiagnosable category the code itself is. Same shape as `cost` and
   `risk`, and the reason it is worth the line is precisely that one code covers six causes.

**Consequence, and it generalises past this criterion.** When a gate has one fail-closed code
for many causes, a caller that reports only the code has thrown away the diagnosis. Every
PENDING and FAIL message in this section now carries the producing engine's own reason string
rather than restating the category — which is also the argument for never piping this gate's
output through `tail`, made concrete.

### Changing a Phase 1 criterion from Phase 3: the websocket budget was measuring the machine

**Agent:** C · **Task:** lead's ruling, following the entry above · **Date:** 2026-09-10

**Crossing a phase boundary, so the justification first.** `console_websocket_pushes_on_change`
is a Phase 1 criterion and this is a Phase 3 change to it, made on the lead's explicit
ruling after I escalated rather than touched it inside spec 45. The escalation was the right
call and the fix is not the one I would have made unprompted: I had proposed counting polls
instead of milliseconds, and the lead's answer is better — **separate the three jobs that
were being done by one number.**

**What was wrong.** `budget_ms = poll_ms * 2` was simultaneously the safety net stopping a
broken console hanging the gate, and the assertion that the push was prompt. The second is
load-sensitive: it is a factor of two of headroom, measured on a machine also running the
rest of the suite. It went red once during a full run and passed three times in isolation
(1.65s, 2.19s, 8.07s for the same eight parametrised cases, which is a fivefold spread on an
idle machine). Spec 45 added 45 tests, nineteen copying a tree, and made the suite more
I/O-bound; the sensitivity pre-existed and I made it likelier to fire.

**And the promptness assertion was never the interesting property.** A console that polls on
an interval is at most one interval late by construction, so the tight bound was standing in
for "the poll loop is actually running" — which can be demonstrated from a generous bound,
and now is.

**Fix — three jobs, three mechanisms.**

- **Safety net:** twenty poll intervals, still from config. Its only job is that a dead
  poller fails in finite time. It carries no promptness claim, and the FAIL message says so
  in as many words: "a dead poller rather than a slow one".
- **Assertion:** behavioural. The socket stays silent through a **quiet window** of two poll
  intervals in which nothing changed and the client sent nothing, and *then* pushes once the
  watermark moves. That pair is what `ui-context.md` actually specifies.
- **Evidence:** the measured elapsed time stays in the PASS message — "silent through 1000ms
  with nothing changed, then pushed 508ms after the watermark moved". A promptness regression
  stays visible in gate output without being a spurious FAIL.

**The quiet window's load behaviour is the opposite of the old budget's, and that is the
point.** Waiting longer only makes it stricter. A loaded machine cannot turn it into a false
accusation; the worst it can do is fail to notice a console that pushes on a timer, which is
a missed detection rather than a wrong verdict. The fabricated console in `tests/verify/`
catches that case deterministically on an idle machine.

**Mutated both ways, per the ruling.** `if current != seen:` to `if False:` — nothing is ever
pushed, FAIL, which the old form also caught. And `if current != seen:` to `if True:` —
pushes on every poll regardless, **which the old form could not catch**: "a push arrived
within the budget" is true of a console that pushes constantly, and that console is wrong in
a way the operator would feel, as a screen that refreshes forever and never means anything.
That second mutation is why this change is strictly stronger than what it replaced rather
than a loosening.

**Consequence.** A wall-clock number in an assertion is worth asking two questions of: what
property is it standing in for, and does a slower machine make it *stricter* or *wronger*?
The old budget answered "the poll loop runs" and "wronger". Both halves were fixable and
neither needed the number widened.

*(Follow-up to the entry above, recorded because the standing instruction is to say so
rather than smooth it over.)* On the first combined run after the change,
`test_a_socket_that_accepts_and_never_pushes_is_a_failure` failed once across
`tests/verify/ tests/console/ tests/harness/` — 1 failed, 514 passed. It has not reproduced
since: the same test passes in isolation (11.59s, which is the expected quiet window plus
the full safety net), the same combined selection passed on the next run at 515 passed, and
`test_phase1_criteria.py` has since run three times at 41 passed. I did not capture the
assertion message before it stopped happening, which was a mistake — the failing verdict
would have said whether it went PENDING on a handshake that never answered, or FAIL for a
different reason, and those want different responses.

Two candidates and I am not able to choose between them on one observation: this machine's
known intermittent fault, or a handshake exceeding `WS_ACCEPT_TIMEOUT_S` under contention.
What I can say is that this test is now the longest in the suite at ~11s, because it is the
one where the console is *designed* never to push and therefore pays the whole safety net —
and a longer test is a wider window for a transient to land in. That cost is bounded to one
test and is the deliberate price of a generous timeout, so I have not touched the number.
If it recurs, the message is the thing to capture.

### The spec 46 enumeration earned itself inside a day

**Agent:** C · **Task:** spec 46, follow-up · **Date:** 2026-09-10

**What happened.** Six consecutive runs of `tests/verify/ tests/harness/ tests/console/`
came back `2 failed, 519 passed` — deterministic, not the load flake I was chasing:

```
AssertionError: engine 7 declares exclusion reason(s) with no operator prose:
['no_fx_rate']. Each renders as 'No reason was recorded.' on the console, silently.
```

B had added `REASON_NO_FX_RATE = "no_fx_rate"` to `scout/contracts.py` on an operator
ruling made the same day, and the enumeration went red within minutes of it landing.

**Why it is worth an entry.** This is the seam working, and it is the case the spec argued
about in the abstract: *"a hand-written list drifts the first time B adds a code, and it
drifts silently, which is the failure mode this seam is known for."* B added a code, in good
faith, for a good reason, and told nobody — because there was nothing to tell; the code is
correct and its docstring is thorough. A hand-listed test would have stayed green and the
console would have rendered "No reason was recorded." for a real exclusion, with no error
anywhere. The gap between the code landing and the test going red was one test run.

It also lands on the right side of a distinction I had not thought about when writing it:
`no_fx_rate` **is** in `EXCLUSION_REASONS`, so even the narrower tuple-based enumeration
would have caught this one. The `vars(module)` scan earns its keep on the codes B keeps *out*
of the tuple, of which `scout_inputs_unavailable` is the only one so far.

**Fix, and the part of it I am least comfortable with.** I added the prose immediately rather
than waiting for B, because the alternative was leaving the tree red for everyone over a
one-line mapping. **The wording is mine, not the producer's**, which breaks the arrangement
every other entry follows — B has been asked to replace it if it is wrong. The sentence is
"No exchange rate to value this pair's quote currency", and it is deliberately not a variant
of `no_quote_balance` beside it: that one is "you hold none of it", a fact about the account,
while this one is "we cannot tell what it is worth", a fact about a mechanism nobody has
built. An operator handed the same sentence for both would go looking at their balances for a
fault that is not there.

**And a new invariant, which that pair is what suggested it.** `test_no_two_codes_share_a_sentence`
asserts no two codes render identically. The lead's spec 43 ruling is the specific case —
`crypto_quoted` and `quote_not_provably_stable` exist separately so a universe that shrank by
policy is distinguishable from one that shrank for want of a config key — but the property is
general, and two codes sharing a sentence is exactly how such a ruling gets undone in the view
layer, where nothing else is looking. There were no duplicates when I added it; the point is
that there cannot silently become one.

*(Follow-up, and it changes the reading of the two entries above.)* A second test showed the
same behaviour: `test_persisted_mode_is_pending_when_core_never_calls_the_writer` failed once
in a full-suite run, then passed twice in isolation and again across its whole directory
(248 passed). **That is a Phase 2 criterion test I have not touched**, driving a fabricated
console the same way the websocket one does.

Two different tests, in two different phases' criteria, one of them nothing to do with my
change, showing the same shape: green in isolation, green in their own directory,
occasionally red in a full run. That points away from the websocket quiet window as the
cause and towards something environmental about running ~1300 tests on this machine — which
is the same suspicion the intermittent native fault already carries. It does not exonerate
the old two-interval budget, which was separately and provably load-sensitive; it does mean I
should stop attributing every full-run flake to that change.

What the criteria have in common is that both drive an ASGI console through
`asyncio.run` in-process, with wall-clock waits, inside a suite that spawns hundreds of
event loops. I have not root-caused it and I am not going to guess further on three
observations. Recorded so the next person sees two data points rather than one, and so that
"C changed the websocket criterion and now things are flaky" is not the story that gets told.

### A's three cannot-fail findings in the shared harness, and one fix that was wrong twice

**Agent:** C · **Task:** A's sweep, files are C's · **Date:** 2026-09-10

A swept `tests/conftest.py` and `tests/harness/` for tests that cannot fail and found three,
all mine. A's framing is the right one and worth keeping: **each is a fallback that fires
silently when an import fails**, each was correct when written because the thing it fell back
from did not exist yet, and none has an assertion that the *real* branch is the live one — so
none notices when its own reason for existing has expired. The failure mode is not a red
test; it is a green suite that has quietly stopped testing.

**1. The fake Kraken client's error types.** `fake_kraken.py` imports `KrakenError` and its
two subclasses from `acsoe.clients.kraken` and defines its own on `ImportError`. The test
whose entire purpose is proving the fake raises *the real client's* type imports `KrakenError`
**from the harness** — so against the fallback both sides move together and it passes while
asserting nothing. A demonstrated it by blocking `acsoe.clients.kraken` at the import system:
the test still passes, against classes that are not the real error type.

Fixed with an identity check —
`test_the_harness_is_using_the_real_error_types_not_its_own_fallbacks` asserts all three
`is` the real ones. **The fallback stays**, because it is still reachable: `tests/verify/`
drives criteria against fabricated trees carrying `tests/` and no `src/`, and the harness
imports there with no real client to find. What was missing was anything noticing which
branch is live. The older test now carries a line saying it depends on the new one and is not
a tautology, because it reads like one.

**2. `migrated_store` returning `None`, and I got the fix wrong twice before getting it
right.** This is the part worth recording.

`migrated_store` caught `ModuleNotFoundError` and returned `None`, which `build_verify_doubles`
hands to `scripts/verify.py` — so a criterion could tick an orchestrator against a client
bundle with no store and still report PASS. A's comparison is exact: it is the shape that
made `Orchestrator._record_run` unexecutable for a whole phase.

**First attempt: require a store in `_harness_doubles`.** Eighteen tests went from green to
PENDING. Several criteria are *supposed* to run on trees with no store —
`data_guard_blocks_bad_data` judges an engine that never touches one, against a fabricated
tree with no `src/` at all. I had turned "this criterion cannot check everything" into "this
criterion refuses to check anything", which is the same defect pointed the other way.

**Second attempt: make it opt-in, `require_store=True`, on the two criteria that reach the
store.** Five tests still failed, for the same reason one level down: those two criteria are
*also* designed to run against fabricated trees, and a fabricated tree legitimately has no
store.

**What was actually wrong** was none of that. It is the same defect as finding 3, in a
different file: `except ModuleNotFoundError` catches the module's own absence *and* a missing
dependency raised from inside it. "Not written yet" and "written and will not import" are
different facts with different right answers, and the handler could not tell them apart. The
fix is four lines in `migrated_store` — narrow the `except` to a `ModuleNotFoundError` naming
the store client itself, re-raise anything else. Absent still returns `None`; broken now
raises. No criterion changed, no test moved.

**The lesson is about where I reached first.** Twice I went for the consumer — make the
criterion demand more — when the defect was in the producer's inability to distinguish two
cases. Both attempts made the gate *stricter* and both were wrong, and "stricter" is a
seductive direction when the finding is "this could pass when it should not". The question
that would have got me there first is the one A's finding already contained: *what are the two
situations this handler is conflating, and does the caller have any way to tell them apart?*

**3. `pytest.importorskip` and 370 tests.** A found that an `ImportError` from inside a module
is re-raised by pytest 9.1.1 — so a genuinely broken module fails loudly, which A expected to
be wrong about and was glad to be. But a **`ModuleNotFoundError`** from inside is skipped, and
that is what an absent dependency produces. About 370 test functions, a third of the suite,
reach a fixture guarded that way. All of them would vanish, the run would report green, and
the skip reason would read "the store client does not exist yet" — false, and pointing the
reader away from the cause.

Fixed with `require_module` in `tests/conftest.py`, which skips only when the named module
*itself* is what is missing and re-raises otherwise — the same discrimination
`scripts/verify.py`'s `try_import` has drawn since Phase 0. The tests should not be looser
than the gate that judges them. All five `importorskip` calls now use it, and
`pytest_sessionstart` aborts the run once, up front, if one of those modules is on disk and
unimportable — because the same fault otherwise surfaces as several hundred separate fixture
errors, which is loud but unreadable and blames the fixture rather than the thing that broke.

`tests/harness/test_require_module.py` proves the discrimination both ways against a real
temporary package whose import genuinely fails, including the negative half —
`pytest.importorskip` **is** shown swallowing the same module, so if pytest ever changes
behaviour the replacement stops being justified from a red test rather than from somebody's
memory. It also covers the prefix case (`acsoe.a.b.c` when the package is missing raises with
`name` set to the *package*), which a naive `exc.name == name` check gets wrong and which
would have turned every genuinely-unwritten module into a hard error — breaking the whole
working method of registering criteria ahead of their subjects.

**What A found that was not a finding, and is worth recording as such.** A went looking for a
hole in the network guard and did not find one: real sockets, real httpx, `NetworkAccessError.layer`
asserted so a half-guard is distinguishable from a whole one, plus the restore, loopback and
`socketpair` scoping tests. A green report from someone actively trying to break it is worth
more than the absence of complaints.

*(Second occurrence, and this one is the case the wider net was built for.)* B landed
`REASON_EMPTY_UNIVERSE = "empty_universe"` for spec 44 and the enumeration went red again.
Unlike `no_fx_rate`, this code is **deliberately not in `EXCLUSION_REASONS`** — like
`scout_inputs_unavailable` it is a statement about the tick rather than about a pair, and
every pair that produced it is already counted under its own exclusion code, so counting it
in the tally would double-count the whole universe. **A tuple-based enumeration would not
have seen it.** Two codes now sit outside that tuple and both need prose; the `vars(module)`
scan is what finds them.

The prose needed more care than the others because **this one is a `PASS`, not a refusal.**
B's docstring is emphatic about it: nothing qualifying is this system's honest default state
on a small account, and recording it as a block would fill `block_records` with a normal
Tuesday and corrupt engine 17's error rate, which counts those rows. `ui-context.md` says the
same thing from the other side — a console that looks empty most of the time is telling the
truth rather than failing. So the sentence is "No pair was tradable on this bar": what the
system did, past tense, no apology, and nothing suggesting a fault. A sentence borrowed from
the refusal codes around it would have made the system's normal state read as a problem on
the screen that is most often on display.

### The intermittent fault was mine: `sweep_stale_workspaces` deletes other runs' live databases

**Agent:** C · **Task:** the lead's root-cause finding · **Date:** 2026-09-10

**What happened.** B hypothesised and the lead reproduced on the first attempt: create one
workspace with a seeded database, close the connection, call `sweep_stale_workspaces` — and
it deletes that workspace *and two others that were live at that moment*.

```
seeded, db exists: True
sweep removed: 3 dir(s)
db still exists: False | workspace still exists: False
sqlite3.OperationalError: unable to open database file
```

**Why, and the docstring is the defect rather than a description of it.** It says:

> Best effort throughout: a directory another verify run is using right now simply will not
> delete, and that is fine - it is swept by whichever run goes last.

That is a POSIX assumption stated as a fact about Windows, and it is wrong twice over. An
*open* file cannot be unlinked on Windows — but **a SQLite database between connections is
not open**, and every criterion here seeds, closes, and reopens, so it is unlocked for that
entire window. And `ignore_errors=True` means the call does not stop at what it cannot
remove: it deletes everything it can and skips the rest, so **partial deletion is guaranteed
rather than possible**.

That is why there were two signatures and one bug. Directory gone before the next connection
opens → `unable to open database file`. Directory survives with the database deleted inside
it → `sqlite3.connect` helpfully **creates a fresh empty one** and the next statement says
`no such table: equity_snapshots`. The criterion that "seeded a database and then found it
empty" was not confused; its database had been deleted between the write and the read.

The concurrency required is our normal working state. `tests/verify/test_runner.py` calls
`main()` nine times, so one ordinary `pytest tests/` sweeps the shared temp directory nine
times, and three agents each running the full suite is three of those at once.

**I wrote that docstring, and it is the sentence that stopped anyone looking.** Worse, there
*is* a recursion guard immediately above it for the nested `toolchain_green` subprocess — so
a related concurrency case was genuinely considered, which made the unconsidered one look
handled. A comment asserting a property nobody checked is the same shape as the fallbacks A
found this morning, one door along: the assertion was in prose instead of in code, so nothing
could notice it going false. It was never true.

**Fix.** Next entry.

### Correction: three entries above attribute to a native fault what was my own sweeper

**Agent:** C · **Task:** the same · **Date:** 2026-09-10

Per rule 6, correcting with a new entry rather than editing the old ones.

Three entries above blame this machine's intermittent native fault, and at least the first is
certainly wrong: **the zero-byte `phase0.txt`** that opened this session's work. I recorded
that as "exit 139, the bash rendering of the 0xC0000005 access violation this machine is
known for", and used it to justify the streaming-output fix. The streaming fix stands on its
own merits — a run that dies mid-way should leave the verdicts it reached — but the reason it
died was almost certainly a concurrent sweep pulling the seeded database out from under
`seed_fixtures_present`, not the hardware.

The other two are the websocket test and `test_persisted_mode_is_pending_when_core_never_calls_the_writer`.
The lead has since made a standing rule that a failure is attributed to the sweeper **only if
it carries a database error**, and B pushed for it specifically to stop a newly-named
mechanism absorbing everything the way the native fault did. By that rule the Phase 2 one is
the sweeper — B captured `OperationalError: unable to open database file` on a sibling of it —
and the websocket one is **not**, because it is a wall-clock assertion and no amount of
deleted temp directories makes a measured duration wrong. That one still has no mechanism.
The native fault is also still real: a full run today died with `Windows fatal exception:
access violation`. Three mechanisms, not one.

**What is worth keeping from this, and it is uncomfortable.** `PHASE-3-TASKS.md` has told
every agent for two phases that on a FAIL you re-run the named test in isolation and, if it
passes, write it up as the intermittent fault. That advice *works* — the test does pass in
isolation, because in isolation nothing else is sweeping. **So the mitigation confirmed the
wrong diagnosis every single time it was applied**, and it did so with the authority of the
phase rules behind it. Four spurious FAILs while Phase 2 closed, one of them landing on the
test asserting no credential was committed. A real, deterministic, fixable defect sat behind
a folk explanation load-bearing enough to be written into the process.

I did not merely inherit that explanation, I extended it: I wrote a fresh entry this morning
attributing a zero-byte file to the hardware, having reached for the rule rather than the
evidence. The rule told me what the answer was before I had looked, and the check it
prescribed could not distinguish the two causes. A diagnostic procedure that cannot fail is
the same defect as a test that cannot fail, and this project has spent a whole phase on the
second while running on the first.

*(Fix, completing the entry two above.)* `sweep_stale_workspaces` now removes only
directories whose **newest mtime anywhere inside them** predates this process's start by more
than a minute. Four changes, and the middle two are the ones I would have missed:

**The cutoff is this process's start time, not a fixed age.** `PROCESS_STARTED_AT` is captured
at import. A run that has not finished has, by definition, written to its workspace since this
process started — so its directory cannot be older than this process and cannot be selected.
The ordering is the entire argument, which is why no lock file or inter-process protocol is
needed. "Anything older than an hour" would have been a guess about how long a run takes.

**The newest mtime *inside*, not the directory's own.** A directory's mtime changes when an
entry is added or removed from it, not when a file inside it is written — so a long-running
run's workspace carries the mtime of the moment it was created. Reading only that would have
left the bug exactly where it was for any run outlasting the margin, and `toolchain_green`
alone takes ninety seconds. `test_a_workspace_being_written_to_now_survives_even_if_it_was_created_long_ago`
is that case, and it fails against the naive version.

**A minute of margin, and the direction it errs in is the whole justification.** Filesystem
and system clocks do not agree to better than a second or two on Windows and are coarser on
FAT-derived filesystems. The two errors are not symmetric: keeping a leftover one run too long
costs some disk; deleting a live database costs a wrong verdict on a gate that decides whether
real money trades. The asymmetry picks the number.

**The suppression moved inside the loop.** `contextlib.suppress(OSError)` wrapped the whole
`for`, so a single entry that would not stat aborted the sweep and every workspace after it
alphabetically was kept forever — the 450MB-per-run leak this function exists to prevent,
reintroduced by its own error handling. Found by writing the unreadable-entry test, not by
reading the code. It has its own test now.

`ignore_errors=True` is kept and now means what the old docstring wrongly claimed: everything
reaching `rmtree` has already been established as nobody's, so a failure to remove one is a
genuine best-effort miss and the next run gets it. What it is no longer doing is deciding
*whether* a directory is safe to delete by trying and seeing what happens. **The false
docstring is gone**, replaced by the reasoning above — it was the sentence that stopped anyone
looking, and leaving it while fixing the code would have left the more durable half of the
defect in place.

**Ten tests in `tests/verify/test_workspace_sweep.py`, where there were none — which is the
other half of why this survived two phases.** Both directions are asserted, because each alone
is satisfiable by a broken sweeper: "delete everything" passes the stale-leftover test and
"delete nothing" passes the live-workspace test, so
`test_the_live_one_survives_while_the_stale_one_beside_it_goes` runs both in one sweep.
Mutated as the lead asked: removing the mtime guard turns **four** of the ten red, including
the headline one. Every test runs against a fabricated temp root — a regression test for this
bug that swept the real temp directory would be the bug, committed by its own test.

### The strongest instance yet of a test that cannot fail, and it is B's

**Agent:** C · **Task:** recorded at the lead's request · **Date:** 2026-09-10

Not my work, and it belongs here because it is the same argument as this file's
induced-failure entry approached from the other side, and it is a better example than any
of mine.

B mutated `rank_universe`'s `sorted(pairs)` to arrival order, expecting three ordering tests
to go red. **All three stayed green.** The engine sorts its scan set *before* ranking, so a
ranking that merely preserved arrival order still answered alphabetically — the shuffled
input never reached the function under test.

The part that makes it the best example is the docstring. That test **claimed to be "the
assertion carrying the ordering"** and described an accidentally-stable sort as precisely the
thing it would catch. It was the one case it could not detect. And no amount of *reading*
would have revealed that, because the docstring is persuasive and the test does something
real — it drives the engine, it asserts an order, the order is right.

My own entry above says the induced failures found two criteria that "looked right, passed
against the real engines, and were checking less than they claimed", and I wrote there that
neither would have been found by adding PASS cases. B's is stronger: **it would not have been
found by review either.** A test can be well-written, well-named, well-documented and still be
untestable prose. The only thing that distinguishes it from a real test is breaking the
subject and watching, which is why `code-standards.md` now requires it rather than commending
it.

Worth pairing with the correction two entries up, because they are the same failure at
different scales: a diagnostic procedure that cannot fail told four agents for two phases
that a deterministic bug was a hardware fault, and a test that cannot fail told B its ordering
was pinned. In both cases the check ran, produced an answer, and the answer was
unfalsifiable — and in both cases the prose around it was what made it convincing.

### A rename of one class would silently delete 141 tests, and the suite would report green

**Agent:** C · **Task:** A's finding 8 · **Date:** 2026-09-10

**What happened.** A's fifth finding: the `engine_context` fixture in `tests/conftest.py`
does `getattr(contracts, "EngineContext", None)` and skips if it is absent. A estimated the
cost at 44 test functions across 7 files. I measured it rather than taking the number, by
simulating the rename — one word changed in the `getattr`, suite run, revert:

```
1196 passed, 141 skipped in 156.84s
SKIPPED [1] tests\engines\test_scout.py:1164: acsoe.core.contracts.EngineContext does not exist yet
```

**141 tests, not 44** — the engine suites have roughly tripled today between B's specs 43 and
44 and A's spec 39, so A's number was right when counted and is now more than three times
larger. **Ten and a half percent of the suite disappears, the run exits zero, and the skip
reason is a false sentence** pointing the reader at Phase 0 work that was finished months
ago. Every engine any of us has written is in that set: cost, risk, safety, scout,
data_guard, exchange, market_data_recorder, market_sensor.

**Why.** The same expiry-dated fallback as the other four. `core/contracts.py` did not exist
when the fixture was written and skipping was the honest answer then. It exists now, is
committed, and `EngineContext`'s fields are fixed in `engine-contracts.md` — so the branch is
unreachable, nothing says so, and the day someone renames the class the fixture answers a
question about Phase 0 that nobody asked.

The measurement is the part I would not have got from reading. A's estimate and mine differ
by a factor of three for the honest reason that the tree moved underneath both of us, and a
number in a note about a growing codebase is a number with a date on it — the same drift that
put a stale claim in my own progress file this morning. Simulating the failure costs a minute
and produces a fact.

**Fix.** Next entry, and it follows A's rule rather than my instinct: **not deleting the
fallback — asserting it is unreachable.**

*(Fix, completing the entry above.)* `REQUIRED_SURFACES` in `tests/conftest.py` now pairs each
module the shared fixtures import with **the attribute that fixture actually reaches for**,
and `pytest_sessionstart` checks both. A module that genuinely does not exist is still not an
error — several suites run against trees where a package is unwritten, and skipping is honest
there. An attribute missing from a module that *imports* is a different fact: once
`core/contracts.py` exists, `EngineContext` absent from it does not mean Phase 0 is
unfinished, it means the class moved.

**The fallbacks all stay.** This is A's rule and my instinct was the other way: I would have
deleted the `getattr`-then-skip. Deleting it breaks the fabricated trees `tests/verify/`
depends on, which is where I went wrong twice on `migrated_store` this morning — reaching for
the consumer, making it stricter, and taking out the legitimate case with the illegitimate
one. Asserting the fallback is unreachable costs one line and breaks nothing.

`pytest.UsageError` exits **4**, inside pytest's documented range, so `toolchain_green` reads
it as a verdict rather than as a crash to retry. Verified, along with the message naming both
the missing attribute and the fixture that would have gone silent — the failure this replaces
was diagnosable only if you already knew to look, so the message has to carry the diagnosis.

Three tests in `tests/harness/test_require_module.py`, and the first is the one that matters:
`test_the_session_check_passes_against_the_real_tree` calls the hook against the live
repository, so if a fixture ever quietly starts answering "does not exist yet" about something
that shipped, that test says so. The other two mutate it in both directions — a renamed
surface aborts, an unwritten module does not — because a check that aborts on everything would
make registering a criterion ahead of its subject impossible, and that is this project's whole
working method.

**Five findings, one rule, and it is worth stating as A did.** A fallback for something that
does not exist *yet* has an expiry date and nothing in the code records it. `try: import real
/ except: define our own`. `getattr(mod, "Name", None)` then skip. `except KeyError: continue`.
`rmtree(ignore_errors=True)` treating "I could not delete it" as "it was not mine". Each was
correct when written; each became a silent branch firing on a condition that should now be
impossible. **The fix is never to delete the fallback — it is to add the assertion that the
fallback is unreachable.** One line turns a stale workaround into a tripwire for the day
someone breaks the thing it used to stand in for.
