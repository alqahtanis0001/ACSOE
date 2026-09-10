# Build log — Phase 3 — lead

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem
and its fix, and every decision where two approaches were viable. Not at the end of
the session — three IDE crashes in Phase 1 each took the code and the log at different
moments, and only the entries already written survived.

Minimum headings per entry: What happened, Why, Fix.

The lead consolidates these into `docs/build-log/phase-3.md` at phase close.

## Entries

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
