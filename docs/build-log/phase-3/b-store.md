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
`test_the_seeded_drawdown_emits_a_freeze_and_no_close_all` is a real absence rather than a
coincidence.

**Consequence.** The blind spot is in the *test anchor*, not in the store method — the method's
docstring already states the restart-crossing rule and calls its residual over-count out
explicitly. What it does not say, and what cost me a probe to establish, is that the rule makes
`cycle_id=1` a special anchor for *any* fresh `run_id`, which is the shape every test in this
file happened to use.
