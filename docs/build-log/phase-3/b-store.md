# Build log — Phase 3 — b-store

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem
and its fix, and every decision where two approaches were viable. Not at the end of
the session — three IDE crashes in Phase 1 each took the code and the log at different
moments, and only the entries already written survived.

Minimum headings per entry: What happened, Why, Fix.

The lead consolidates these into `docs/build-log/phase-3.md` at phase close.

## Entries

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
