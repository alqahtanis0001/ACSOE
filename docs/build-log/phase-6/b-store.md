# Build log — Phase 6 — b-store

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem and its
fix, and every decision where two approaches were viable.

**Rule 1 is diagnosis-before-fix.** Write **What happened** and **Why** the moment you know why
something is broken, *before* you write the fix; come back and add **Fix** afterwards. The code
survives on disk whatever happens to the session; the reasoning that found it does not.

Minimum headings per entry: What happened, Why, Fix.

**Rule 2, carried from Phase 5 and not retired with it:** every assertion is proven capable of
failing, and the proof goes here. Name the mutation, quote the red message, and say the file was
restored from a byte copy with its hash compared in the same statement that applied it. A claim
that an assertion works is not evidence. A mutation that survives a *subset* of the suite has not
survived — it has not been asked. An equivalent mutant is a checked negative, not a survivor.

**What Phase 6 is, and what that changes about these entries.** Phase 5 built components that
can be wrong while looking right. Phase 6 connects them to money: engines 9, 14, 16, 18, 21 and
22, and the fill simulator. For the first time the whole chain runs end to end, which means two
things for this log. First, **every number Phase 5 produced was measured on one gate in
isolation** — the skeptic's lift, the DI's refusal rate, the anomaly block rate — and this is the
phase that finds out what they are worth in sequence, after friction. Second, the manage chain
holds real positions, so a defect here costs money rather than a metric. Record what you checked
and found *sound*, not only what you found broken: an audit that lists hits alone says nothing
about coverage.

Three things from Phase 5 that will be in someone's way here, so they are written down rather
than rediscovered:

- **Engine 8 publishes `is_buy: false` when it refuses**, so its payload cannot distinguish "no
  call" from "not a BUY". It is an open item for this phase, it is not a fail-open today because
  engine 8's own `BLOCK` stops the tick, and it moves together with engine 15's read of that
  field. `expected_move_pct` is the field that got this right: omitted from the payload on a
  refusal, so the consumer fails closed on an absent key rather than on a value it must interpret.
- **50.2% of out-of-sample rows carry an incomplete feature vector** and engines 8 and 13 refuse
  those at any threshold. A chain that produces few candidates is that number showing up, not
  necessarily a defect.
- **At tier 1 nothing clears the cost gate, by construction** — the hurdle needs an expected move
  above 3.125% and the target barrier is 3.0%. Zero trades at tier 1 is these numbers interacting
  exactly as specified, and is not a bug to chase.

## Entries

### Invariant 6's "one open position per pair" was enforced nowhere, and the gap was structural

**Agent:** B · **Task:** spec 89 · **Date:** 2026-09-16

**What happened.** Invariant 6 ends with two sentences: "One open position per pair. A
configured maximum of concurrent positions across the portfolio." Engine 11 implemented the
second and nothing in `src/` implemented the first. `RiskEngine._count_open_positions` calls
`store.count_open_positions()`, which is `SELECT COUNT(*) FROM positions WHERE status = 'open'`
and never mentions a pair; engine 7 `scout` filters the universe on affordability and tick grid
and never asks either. So with `max_concurrent_positions` at 3 the system would have opened a
second, third and fourth position on the same pair and every gate would have approved.

**Why it stayed invisible for five phases.** It was unreachable, not untested. No engine in
phases 0 to 5 could open a position, so the only way to construct the failing case was to write
`positions` rows by hand, and the only fixture that does — the Phase 0 seed — is consumed by
engine 17 `safety`, which reads the same two tables for a different question and is correct
about it. A rule with no reachable violation looks exactly like a rule that is being obeyed.
This is the same shape as the `no_fx_rate` comparison found under spec 43: a branch nothing
reached, surfaced by writing the next caller rather than by anything going red.

**Fix.** `RiskEngine._pair_exposure`, checked after the portfolio cap and before sizing, over
`store.open_positions()` and `store.resting_orders(intent=OrderIntent.ENTRY)` — both of which
already existed and already carry `pair`, so spec 89 step 3's "if a per-pair read is needed"
never fired and there is no new store surface and no migration. Two reason codes,
`position_open_on_pair` and `entry_resting_on_pair`, because the two states are cleared by
different actions: a position is exited, an order is cancelled, and the operator reading the
rejection row has to know which.

**Consequence.** A resting entry refuses a candidate exactly as an open position does. That is
not an extension of the invariant — it is the reading invariant 14 already applies to `safety`'s
escalation precondition, "a resting post-only buy is exposure that has not happened yet". The
arithmetic is what makes it non-negotiable: a second entry beside an unfilled one is not a
second attempt at one trade, it is double the money at risk from the moment both fill, and by
then no gate stands between them and the account.

### Decision: the portfolio cap keeps its place in front of the per-pair refusal

**Agent:** B · **Date:** 2026-09-16

**Options.** Both refusals can be true on one tick — a full portfolio that also holds the
candidate's pair — and both are correct, so the order decides only which `reason_code` the
`rejections` row carries. Check the per-pair rule first, on the grounds that it is the more
specific statement and is true whatever the cap is configured to; or leave the cap where it was.

**Chose.** The cap stays first.

**Because.** A rejection that would have been recorded as `max_concurrent_positions` before spec
89 is still recorded that way after it. Research reading the `rejections` table across the phase
boundary sees one code change meaning if the order moves, and the coarser statement — the
account as a whole is full — is the one that was there first. It is not an argument that one
rule outranks the other; neither is weakened, because both block.

**Cost.** The per-pair code is invisible on a tick where the portfolio is also full, so a query
counting how often invariant 6's per-pair clause fires will undercount. Pinned by
`test_a_full_portfolio_that_also_holds_this_pair_reports_the_cap` so it is a recorded choice
rather than an accident of statement order, and named in `engines/risk/README.md`.

### Spec 89 — eleven mutations, eleven killed, each named with its killing test

**Agent:** B · **Task:** spec 89 · **Date:** 2026-09-16

Harness in the session scratchpad. Every mutation applied to a **byte copy** read before the
edit and restored by `write_bytes(original)` with `assert sha256(path.read_bytes()) == digest`
in the same statement that writes it, inside a `finally`, so a crashed pytest run cannot leave a
mutant on disk. Never `git checkout --`. One anchor per mutation, and the harness refuses to
apply a patch whose anchor matches other than exactly once — an anchor matching twice would
mutate two sites, and a verdict compounded out of two changes drifts toward KILLED. That is the
harness defect I found in my own Phase 4 rehearsal, fixed at the source this time.
`src/acsoe/engines/risk/engine.py` is CRLF and `src/acsoe/clients/store/client.py` is LF, so the
harness rewrites each anchor to the file's own terminator; a bare `\n` anchor matches nothing in
a CRLF file and would have reported eleven "anchor not found" as eleven non-results.

Subject: `pytest tests/engines/test_risk.py -q`, 48 tests. No mutation survived, so nothing
needed widening — the rule that a mutation surviving a subset has not been asked did not have to
fire. `client.py` verified byte-identical to `HEAD` afterwards by `git diff`, and the whole
working tree shows only the four files spec 89 touches.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| M0 | the per-pair refusal never fires (`and False`) | KILLED | 6 tests |
| M1 | the pair comparison removed: any open position refuses | KILLED | `..._on_that_pair_and_only_that_pair[another pair does not]` — **and nothing else** |
| M2 | resting entries not counted | KILLED | the two resting tests and the userref test |
| M3 | every resting order counts, not only entries | KILLED | `test_only_an_entry_still_resting_on_the_book_refuses_the_candidate[resting exit]` — **and nothing else** |
| M4 | `open_positions()` returns closed ones too (`OR 1 = 1`) | KILLED | `test_a_closed_position_on_the_pair_does_not_refuse_the_next_candidate[closed does not]` — **and nothing else** |
| M5 | an unreadable store reads as no exposure | KILLED | `test_an_unreadable_orders_table_blocks_rather_than_reading_as_no_exposure` |
| M6 | the refusal deleted outright | KILLED | 6 tests |
| M7 | a resting entry reports the open-position code | KILLED | the two resting-entry tests |
| M8 | the sentence stops naming the `position_id` | KILLED | `test_the_refusal_names_the_pair_and_the_position_it_already_holds` |
| M9 | the sentence stops naming the `userref` | KILLED | `test_the_resting_entry_refusal_names_the_pair_and_the_userref` |
| M10 | the per-pair refusal is asked before the cap | KILLED | `test_a_full_portfolio_that_also_holds_this_pair_reports_the_cap` |

**M1, M3 and M4 are the three that justify the parametrisation, and the interesting fact is
which test killed each.** Every one died on the *negative* half of its pair and on nothing else
in 48 tests. Spec 89's "each block test differs from its pass test in one input" reads as a
discipline about fixtures; this is the measurement that says it is load-bearing. The block
halves are killed by six tests each and prove almost nothing on their own — an implementation
that refused every candidate the moment any row existed in `positions` or `orders` satisfies all
of them.

Two red messages worth quoting, because they say what the defect would have cost rather than
that an assertion failed:

```
M1  E       AssertionError: assert 'position_open_on_pair' == None

M5  E       AssertionError: assert False is True
    E        +  where False = EngineResult(engine='risk', status=<EngineStatus.OK: 'OK'>,
    E              blocks_trading=False, ..., 'qty': '33.33333333',
    E              'notional': '3333.3333330000', ...).blocks_trading
```

M5 is the fail-open one. With the store read swallowing its exception and returning "no
exposure", the gate did not merely fail to block — it **approved a 33.33-unit, $3,333 position
while unable to read whether the account already held one.** That is invariant 3's "absence of a
no is never a yes" with a number attached.

**M5's test had to be built carefully and my first version of it was wrong.** I wrote it as
`store.close()`, and it passed — for the wrong reason. `_count_open_positions` runs three reads
earlier and catches the same `sqlite3.ProgrammingError` first, so the assertion on
`risk_inputs_unavailable` was satisfied without the mutated line ever executing. It is Phase 5's
closing finding in miniature: the check agreed with the claim while measuring something else.
Replaced with `DROP TABLE orders` on the real connection, which leaves `positions` readable so
the cap and the open-position check both succeed and the resting-entry read is the only one that
fails; the assertion now also requires the word `exposure` and the pair in the reason, so it
cannot be satisfied by an earlier refusal's message. No double anywhere — that is what `sqlite3`
itself raises at a missing table.

### A tripwire rather than a weaker test, for the two codes C has not mapped yet

**Agent:** B · **Task:** spec 89 step 6 · **Date:** 2026-09-16

`position_open_on_pair` and `entry_resting_on_pair` are absent from C's `REASON_PROSE`, which
means the console renders "No reason was recorded." for both, silently and with no error
anywhere — `ownership.md` carries that as a seam row for exactly this reason. Mapping them is
C's, under spec 99, and C has the two codes by message.

The obvious test — "these codes are renderable" — would be red in the tree until C lands, which
is not mine to inflict on the team. The tempting alternative — "renderable if present" — is
green in both states and therefore green forever.
So `test_the_two_codes_spec_89_added_are_still_waiting_on_cs_prose` asserts the **absence**, and
its failure message says to move the codes into the renderable test above and delete it. It goes
red the moment C is right, which is the only direction a placeholder should be able to fail in.

Same change, found while looking at that test: `no_fx_rate` was missing from the renderable
list although it has been in `REASON_PROSE` since Phase 3 and this engine has emitted it since
spec 43. Added, so five of this engine's seven codes are checked there directly, one is the
prose-preferring `risk_inputs_unavailable`, and the two new ones are held by the tripwire.

### Spec 88 names `drain_trades()` as the seam, and nothing in `src/` calls it

**Agent:** B · **Task:** spec 88 · **Date:** 2026-09-16

**What happened.** Spec 88 step 3 says "engine 3 drains trades through `clients.kraken`, which
in paper mode *is* the broker, so the broker observes the same drained tuple engine 3 builds
`trade_ranges` from". I built `PaperBroker.drain_trades()` on that sentence, with an observation
buffer, a tick boundary and a warning in the module docstring that the broker must never call
`drain_trades()` itself because draining empties the buffer and the two readers would then
disagree. Then I checked who actually calls it.

**Why.** `engines/market_sensor/engine.py:156` reads `recent_trades`, not `drain_trades`, and
`ws.py:349` says why in its own docstring: it is a **rolling window that does not clear**,
because engine 3 has to rebuild the same 15-minute bar on each of the fifteen ticks that bar
spans and an engine is stateless across cycles. `drain_trades()` exists on `KrakenClient`, on
`ws.py` and in A's `MarketStreamProtocol`, and **nothing in `src/` calls it** — my broker was
about to be its only caller. Spec 88's conclusion is right and its mechanism is wrong: engine 3
does reach trades through `clients.kraken`, so the broker is in the path, but by a
non-destructive read rather than by a drain.

**Fix.** The broker reads `self._real.recent_trades()` when it resolves a resting order, and
keeps no observation buffer at all. Reading is non-destructive, so there is no "whichever caller
went first takes the trades" hazard to guard against and the whole guard is deleted rather than
made correct. Seeing one trade repeatedly cannot double-fill: the order fills once and is
terminal thereafter, and every candidate trade is still filtered to `ts > placed_at`. The
broker's `recent_trades()` and `drain_trades()` both forward untouched.

**Consequence, and one deviation from the spec I want looked at.** The observation buffer was
also what gave `_pending` its tick boundary — spec 88 step 2 says the broker holds what it
accepted "only until the tick's end", and the drain was the end. With no drain there is no tick
edge the broker can see. `_pending` is now pruned by *recording* instead: a `userref` the store
knows is dropped from `_pending` at the next lookup, and the store's row wins whenever both have
it. For the normal path that is stricter than the spec — the entry disappears from `_pending`
the moment engine 19 writes it, which is earlier than the tick's end — and for the abnormal path
it is safer, because an order engine 19 failed to record lingers in `_pending` rather than
vanishing from a system that has accepted it. **Flagged to the lead rather than treated as
settled**, because it is a change to a step the operator's spec states.

**Second consequence, and it is a real limitation rather than a note.** `recent_trades()` is
bounded by `max_buffered_trades`, a window by **count and not by time** (`ws.py`'s own words).
A resting entry older than that window cannot see the trade that would have filled it. Engine 21
cancels an entry at `trading.entry_unfilled_window_s`, so the exposure is bounded, but on a very
busy pair the count window could be shorter than the time window and an entry could go
unfilled that a real exchange would have filled. That is the pessimistic direction, so it is not
a defect to fix here — it is a number to check once the two windows have real values against
each other, and it is in the README.

### Spec 88 — thirteen mutations: twelve killed, one equivalent control that survived

**Agent:** B · **Task:** spec 88 · **Date:** 2026-09-16

Same harness discipline as spec 89's, in the session scratchpad: byte copy taken before the
edit, restored inside a `finally` with `assert sha256(path.read_bytes()) == digest` in the same
statement that writes it, one anchor per mutation and a refusal if the anchor matches other than
exactly once. Subject: `tests/clients/paper/` (54 tests) and `tests/clients/store/test_store.py`
(96), together.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| P1 | a resting buy fills on a **touch** (`<` becomes `<=`) | KILLED | the `[a touch does not]` half of both the rule test and the broker test |
| P2 | a post-only buy **at** the ask is accepted (`>=` becomes `>`) | KILLED | the `[at the ask crosses]` half, the rejection test, and `test_a_rejected_placement_rests_nothing` |
| P3 | the market sell walks the **ask** side | KILLED | `test_a_market_sell_walks_the_bids_and_fills_at_the_weighted_average` |
| P4 | the ledger **adds** an entry's notional | KILLED | 4 tests including the Hypothesis round trip |
| P5 | the exit **adds** its fee to the proceeds | KILLED | `..._credits_the_proceeds_less_the_fee_and_not_plus_it` and the round-trip property |
| P6 | a trade printed **before** the order existed fills it | KILLED | `test_a_trade_printed_before_the_order_existed_does_not_fill_it` — and nothing else |
| P7 | a trade on **any** pair fills this one | KILLED | `test_a_trade_on_another_pair_does_not_fill_this_one` — and nothing else |
| P8 | a second placement under one `userref` is accepted | KILLED | `test_a_second_placement_under_one_userref_is_refused` — and nothing else |
| P9 | the store is never consulted | KILLED | the restart test, the store-wins test, `open_orders` |
| P10 | the ledger ignores every fill | KILLED | the round-trip and restart ledger tests |
| P11 | the broker **drains** the trade window | KILLED | `test_the_broker_never_drains_the_trade_window_itself` — and nothing else |
| P12 | the ledger reads every order, not only the fills | KILLED | `test_filled_orders_returns_only_the_fills` — and nothing else |
| P13 | **equivalent control**: a comment added and nothing else | **SURVIVED**, as required | — |

**P13 is the reason the other twelve verdicts are worth anything.** A harness with a broken
subject, a mis-resolved path or a swallowed exit code reports KILLED for everything, and twelve
kills in a row is exactly what that failure looks like from the outside. So one mutation that
*must* survive was run in the same sweep, under the same anchor check and the same restore. It
survived. Phase 4's compounded-mutant defect in my own harness was found the same way — by
asking what the harness would say if it were wrong — and the control is the cheap standing
version of that question.

**P6, P7, P8, P11 and P12 were each killed by exactly one test in 150.** That is the useful
reading of the table rather than the twelve. Each of those five is a property no other assertion
in either file touches: look-ahead through the simulator, pair isolation, invariant 8's
idempotency, not draining the window engine 3 needs, and the ledger's status filter. Delete any
one of those five tests and the corresponding defect ships silently.

**P4 and P5 are the pair worth keeping together.** P4 is a defect anybody would notice — the
balance goes *up* when you buy something. P5 is the same arithmetic one sign away and is nearly
invisible: it credits twice the fee on every round trip, a small number that compounds across
every trade and moves realised PnL in the flattering direction. The Hypothesis property
`test_a_round_trip_at_one_price_costs_exactly_the_two_fees` kills both, and it is the only
assertion in the suite that would have caught P5 on an arbitrary quantity and price rather than
on the one example I happened to choose.

### Two assertions in spec 88's test file that were wrong before they were right

**Agent:** B · **Task:** spec 88 · **Date:** 2026-09-16

Neither is a defect in the broker. Both are cases where my first assertion passed, or failed,
for a reason other than the one it claimed, and both are worth the entry because the shape
recurs.

**The fee-literal guard was a text search, and the modules legitimately contain the text.**
`test_the_broker_holds_no_fee_rate_of_its_own` first read both source files and asserted that
`"0.22"` and friends did not appear. It failed immediately — because `fills.py` and `broker.py`
both *explain* the ratio convention by writing "0.22% is 0.0022", which is documentation doing
its job. The fix is not to delete the sentence: the thing that must not exist is a **value**, not
a mention. The check now walks the AST, collects every `Constant` that is not a docstring, and
looks for the rates there. That is strictly narrower than the text search and also strictly
wider, because it catches a rate written as a bare float, which a string search for `"0.0022"`
would miss entirely.

**The engine 3 seam test passed its own premise and then failed on an empty dict.** The first
run reported `assert 'SOL/USD' in {}` — engine 3 published no `trade_ranges` at all. Not a
forwarding defect: `context.previous_now` is `None` on a process's first tick and engine 3
correctly publishes no range, because "since the previous tick" has no meaning yet. The seam is
about a second tick, so the context is now given a `previous_now`. Worth recording because the
failure looked exactly like "the broker did not forward the trades" and is not that at all —
and because a test written the other way round, asserting `trade_ranges == {}`, would have
passed on the first tick and proved nothing about forwarding.

### Decision: the ledger credits no base currency, and the spec is what settles it

**Agent:** B · **Date:** 2026-09-16

**Options.** A buy spends quote and receives base. Track both, so `balances` reads as an honest
wallet; or track the quote side only, as spec 88 words it — "minus every filled entry's notional
and fee, plus every filled exit's proceeds less fee".

**Chose.** Quote side only.

**Because.** Engine 19 computes `equity = cash + positions_value`, where `cash` is
`balances[trading.base_reporting_currency]` and `positions_value` is the marked value of the
open positions. The base leg of a filled entry is therefore *already* represented, by the
`positions` row. A base credit here would be a second representation of one exposure, and the
two would disagree the first time a fill and a position row did — which is precisely the class
of defect the ruling that created this ledger was fixing, arriving from the other side.

**Cost, stated so it is not discovered.** `balance()` in paper mode is not a wallet. It answers
"how much spendable quote currency is there", which is the only question engine 11 and engine 19
ask of it, and a future reader expecting to see base holdings will not find them. Named in the
README and asserted by `test_only_the_quote_currency_moves`.

### Two `OrderStatus` enums with identical spellings, and `is` silently chose the wrong branch

**Agent:** B · **Task:** spec 92 · **Date:** 2026-09-16

**What happened.** Every entry-handling test in `tests/engines/test_position_manager.py` failed
the same way — thirteen of them — with engine 21 publishing no orders at all and reporting
`entry_orders_cancelled: True` while a resting entry sat in the store. The engine returned `OK`,
no exception, no reason code. A stale entry was not cancelled, a filled entry did not become a
position, and a `close_all` reported itself finished with a live post-only buy on the book.

**Why.** There are **two** `OrderStatus` enums in this codebase with the same five spellings:
`acsoe.clients.store.contracts.OrderStatus`, which is what an `OrderRow` carries, and
`acsoe.clients.kraken.contracts.OrderStatus`, which is what A's `OrderState` carries. Engine 21
imports the store's, because it builds store-shaped row payloads. It then compared the *client's*
answer against it:

```python
if current.status is OrderStatus.RESTING:   # store's enum
```

`current` comes from `query_orders`, so `current.status` is the **kraken** enum. Both are
`StrEnum` and both are `"resting"`, so `==` is `True` and `is` is `False` — they are different
objects in different modules. Every resting entry therefore fell through to the branch that
means "already cancelled, rejected or expired at the exchange; nothing to do and nothing
resting", which is the one branch that sets neither a cancel nor `still_resting`.

**This is a fail-open on the kill switch, and it is spec 81's defect from the other side.** Spec
81 fixed the orchestrator reading `bool(payload.get(field))`, where a text-shaped flag cleared a
liquidation. Here the flag was a real `True` and the *engine* was wrong: it had concluded that
nothing was resting because it could not recognise the status of the thing that was. The
orchestrator would have cleared `close_intent`, marked the `close_all` row consumed, and left the
entry on the book to fill minutes after the emergency stop was pulled — invariant 8's named
failure, arriving through an enum import.

**Why no type checker caught it.** `mypy --strict` passed on the whole engine. `current` is typed
`Any`, because `context.clients.kraken` is structural — it is `KrakenClient` in the daemon and
C's fake or my broker in a test — so there is nothing for mypy to compare. It is the same `Any`
that A's `coerce_*` functions are typed with and for the same good reason, and this is what that
reason costs.

**Fix.** The client's enum is imported under its own name and used for every comparison against a
value that came back from the client; the store's keeps its name and is used only for the row
payloads the engine publishes. Comparison stays identity rather than becoming `==` — `==` would
have worked here and would also silently accept the string `"resting"` from anything, which is
the shape that hid this. A regression test asserts the two enums are distinct objects and equal
by value, so the next reader meets the hazard as a stated fact rather than as thirteen failures.

**What would have happened without a test.** Nothing visible. The engine returns `OK`, publishes
a well-formed payload, and reports the liquidation complete. There is no error anywhere in the
system, and the only symptom is an order that was never cancelled. It is exactly the class the
Phase 6 log's opening note warns about — a component that can be wrong while looking right — and
the only reason it was caught before a rehearsal is that the tests drive a **real** order client
rather than a double that would have been written to agree with the engine.

### Decision, reversed: the per-pair refusal now goes ahead of the portfolio cap

**Agent:** B · **Date:** 2026-09-16

**This entry replaces the ruling in "Decision: the portfolio cap keeps its place in front of
the per-pair refusal" above.** That entry is left standing and unedited, per `script-rules.md`
rule 6 — the reasoning in it was not wrong about what it weighed, it was wrong about one number
it did not weigh. Read the two together: the earlier entry is the argument, this one is the
correction.

**What the earlier entry missed.** It treated the two refusals as both reachable, and traded
them off as a question of which code a rejection row carries when both fire. **At this balance
the cap is inert.** `config/default.yaml` sets `max_concurrent_positions: 3` and the committed
comment on that key already says so: at $5,000, 1% risk against a 1.5% stop is ~$3,333 notional,
so the *balance* binds at one position and the cap at three is never the thing that refuses.
The Phase 6 task list carries the same number as its item 9, "not a defect". So the tick where
both refusals are true is not a rare tie between two live rules — with one position open it is
**every** tick on that pair, and the cap-first order makes invariant 6's specific clause
invisible on exactly the ticks where it is the rule actually doing the work.

**Chose.** The per-pair refusal is checked first. Ruled by the lead.

**Because.** The earlier entry's argument was continuity of the `rejections` table across the
phase boundary: a refusal recorded as `max_concurrent_positions` before spec 89 should still
read that way after it. That argument costs nothing when the cap is reachable and costs
everything when it is not — it preserves the code on rows that, at this balance, would only
ever have been produced by the specific rule anyway. There are no pre-spec-89 rejection rows to
protect: no engine in phases 0 to 5 could open a position, so nothing has ever written a
`max_concurrent_positions` row from a real portfolio. Continuity was being preserved for a
history that does not exist, against a measurement — "which pairs is invariant 6's per-pair
clause refusing, and how often" — that Phase 6 will actually want to make.

**Cost, stated so it is not discovered.** The reverse of the old cost, and it is the smaller
one. A genuinely full portfolio that also holds the candidate's pair now records
`position_open_on_pair` (or `entry_resting_on_pair`) rather than `max_concurrent_positions`, so
a query counting how often the *cap* fires will undercount. That query is uninteresting while
the cap is inert, and if the balance ever grows enough for the cap to bind on its own, it will
bind on pairs the account does not already hold — where no per-pair refusal exists to shadow it.
Pinned by `test_a_full_portfolio_that_also_holds_this_pair_reports_the_pair_rule`, which is the
inverted form of the test that pinned the old order, so the order remains a recorded choice
rather than an accident of statement order.

**Both still block.** Nothing is weakened. This decides a `reason_code` and nothing else: the
candidate is refused either way, and no quantity is computed for it either way.

### The two spec 89 loose ends, and four mutations that say the replacements hold

**Agent:** B (session 2) · **Task:** spec 89 tail · **Date:** 2026-09-16

**The tripwire did its job and was deleted.**
`test_the_two_codes_spec_89_added_are_still_waiting_on_cs_prose` asserted that
`position_open_on_pair` and `entry_resting_on_pair` were **absent** from C's `REASON_PROSE`.
C landed both under spec 99, so it went red, which is the only direction it could fail in and
the reason it was written that way. Deleted, and the two codes moved into
`test_every_reason_code_this_engine_emits_is_renderable_by_the_console` beside the other five —
exactly what the tripwire's own failure message said to do. `tests/engines/test_risk.py` is 47
tests now rather than 48; the lost one was the placeholder, not a case.

**Worth recording about the replacement, because it is not obvious from reading it.** R2 and R3
below respell each constant to something the console has no prose for, and each was killed by
**that renderable test and by nothing else in 47**. So the seven-code list is the only assertion
in this file that touches those spellings at all: every other test compares
`result.data["reason_code"]` against the imported constant, which follows the constant wherever
it goes. Rename a code and the *only* thing that notices is the console seam test. That is the
right place for it to be noticed — a renamed code with no prose renders "No reason was
recorded." silently — but it means the test is load-bearing alone and must not be folded into
anything.

**The precedence reversal.** Applied as the lead ruled; the reasoning is in the Decision entry
immediately above this one, which corrects rather than edits the original. Three files carried
the old argument and all three were changed together, because `code-standards.md` and AGENTS.md
both say a doc contradicting the implementation is fixed in the same change: the comment at the
branch in `engines/risk/engine.py`, the module docstring's "One position per pair" section, and
`engines/risk/README.md` in two places — the numbered gate-condition list, whose order *is* the
behaviour, and the "Order against the portfolio cap" paragraph.

The pinning test was inverted rather than deleted:
`test_a_full_portfolio_that_also_holds_this_pair_reports_the_cap` is now
`..._reports_the_pair_rule`, same three positions, same fixture, opposite expected code. And
`test_the_portfolio_cap_is_counted_from_the_store_not_from_state` gained a sentence saying why
it still reaches the cap at all: its three positions are on `BTC/USD`, `ETH/USD` and `XRP/USD`
while the candidate is `SOL/USD`, so no per-pair refusal shadows it. Those two tests are now a
pair — the cap alone, and the cap behind the per-pair rule.

**Mutations.** Harness rebuilt for this session with the same discipline as the first B
session's: byte copy read before the edit, restore inside a `finally` by a statement that
asserts `sha256(path.read_bytes()) == digest` taken before, one anchor per mutation and a
refusal if it matches other than exactly once, anchors rewritten to the file's own terminator
(`engine.py` is CRLF). Never `git checkout --`. Subject `tests/engines/test_risk.py`, 47 tests.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| R1 | the reversal undone — the cap is asked before the per-pair rule again | KILLED | `test_a_full_portfolio_that_also_holds_this_pair_reports_the_pair_rule` — **and nothing else** |
| R2 | `entry_resting_on_pair` respelled to a code the console has no prose for | KILLED | `test_every_reason_code_this_engine_emits_is_renderable_by_the_console` — **and nothing else** |
| R3 | `position_open_on_pair` respelled the same way | KILLED | the same test — **and nothing else** |
| R0 | **equivalent control**: a comment added to `engine.py` and nothing else | **SURVIVED**, as required | — |

**R1 is the one that matters and it is a one-test kill by design.** Both orders block, both
record a correct refusal, and 46 of the 47 tests cannot tell them apart — which is precisely why
the order needs a test naming it rather than being left to statement order. The old entry said
the same thing about the old order; the reversal does not change that property, it only changes
which code the pinned tick records.

**One thing I deliberately did not mutate.** The obvious proof for R2 and R3 is to delete the
line from `REASON_PROSE` itself. `src/acsoe/console/format.py` is **C's lane**, C is editing it
in this working tree right now (`git status` shows it dirty alongside two other C files), and a
restore-by-hash would have written my pre-mutation bytes over anything C saved in between —
destroying a teammate's uncommitted work to prove my own assertion. Respelling my own constant
in `engines/risk/contracts.py` asks the same question of the same test from my own side of the
seam. `git diff` afterwards shows `format.py` and `contracts.py` both byte-identical to `HEAD`.

### `PaperBroker` forwarded six of the stream's seven methods, and the one it dropped writes invariant 11's gap markers

**Agent:** B (session 2) · **Task:** spec 88 tail · **Date:** 2026-09-16

**Found by A, not by me, and not by anything failing.** A counted the surface:
`MarketStreamProtocol` in `clients/kraken/contracts.py` declares seven stream members and
`PaperBroker` forwards six. The missing one is `drain_gaps()`. Reported to the first B session,
which died before it could act; no daemon has run in Phase 6, so nothing is damaged.

**What happened.** In paper mode `cli/engine.py` puts the broker in the position of
`context.clients.kraken`, so every engine that reads the stream reads it through the broker.
Engine 2 `market_data_recorder` takes gaps with
`getattr(stream, "drain_gaps", None)` and returns `()` when the attribute is not callable —
`engines/market_data_recorder/engine.py:225`. Against the broker that branch is taken on every
single tick.

**Why it is worse than a missing method.** The engine's fallback is not wrong: `getattr` there
is deliberate, because engine 2 also runs against doubles and the surface has grown over three
phases. But the consequence in paper mode is that engine 2 writes **no `gap` line** into
`data/raw/` — ever — while continuing to write every frame. The archive that results is not
missing a feature; it is **actively claiming something false**. A recording that spans a
reconnect and carries no gap marker reads as continuous, which is exactly what
`context/trading-invariants.md` rule 11 forbids: "a gap is marked, never healed." And it
propagates: A's book cutter (`scripts/cut_book_fixture.py`, spec 86) refuses a window
containing a gap, so a gapless-looking archive **disarms the cutter's own refusal** and C's
committed `book_sample.jsonl` could be cut straight across a reconnect without anything
objecting. One silent forwarding omission defeats a safeguard two specs away, in another
agent's lane.

It also fails safe in the wrong direction from the broker's point of view. `drain_gaps` is
*consuming*: had the broker forwarded it, the gaps would be drained and recorded. Not
forwarding it means the real stream's gap buffer is never drained by anyone and grows for the
process's lifetime — so the information exists, in memory, and simply never reaches disk. The
`gaps` **property** was forwarded, which is why this looks fine from a console reading live
state and is only wrong in the archive.

**Why no test caught it.** Every test of the forwarded surface was a test *per method*, written
alongside the method. Nobody writes a test for the method they forgot — the omission and the
missing test have the same single cause, so a per-method suite can never find this class of
defect. This is the same shape as spec 99's walking test over reason codes, arriving through a
protocol instead of a dict.

**Fix.** One line of forwarding, `drain_gaps()` beside `drain()` and `drain_trades()`, and the
test A asked for: `test_the_broker_forwards_every_member_of_the_stream_protocol` walks
`MarketStreamProtocol.__protocol_attrs__` and asserts the broker presents **all** of them, so
the next member added to the protocol goes red here rather than silently vanishing in paper
mode. It is deliberately a walk over the protocol and not a hand-written list, for the reason
above: a hand-written list is written by the same person who forgot the method.

### `drain_gaps` — the fix, and four mutations, one of which is the defect itself

**Agent:** B (session 2) · **Task:** spec 88 tail · **Date:** 2026-09-16

Fix as described in the diagnosis above: `PaperBroker.drain_gaps()` forwards
`self._real.drain_gaps()`, with a docstring that says what the omission cost rather than that
the method exists, plus
`test_the_broker_forwards_every_member_of_the_stream_protocol`.

**The test asserts two things, because presenting a member and forwarding it are different
failures.** For each name in `MarketStreamProtocol.__protocol_attrs__`: the class presents it,
and calling it through a fresh broker touches exactly that one attribute on a recording
stand-in. A stub answering `()` without asking the real client would pass a presence check and
be exactly as silent as the missing method — G2 below is that mutant, and it dies.

Three details that are not decoration:

- **Presence is asked of the class, not the instance.** My first version used
  `hasattr(broker, name)` and went red on `connected` with `touched == ['connected',
  'connected']`: `hasattr` on an instance *evaluates* a property, so the presence check was
  itself a forward and the forwarding assertion counted two. Asked of `PaperBroker` the
  property object is returned unevaluated.
- **A fresh broker and a fresh stand-in per member**, so `touched == [name]` is an exact
  equality rather than a membership test. Membership would pass for a broker that forwarded
  every call to `drain` as well.
- **A guard against a vacuous pass.** `__protocol_attrs__` is a private typing detail. A rename
  would raise, which is loud; an *empty* set would make the whole walk iterate zero times and
  stay green while checking nothing. So the test first asserts `drain_gaps` is in the set and
  that the set has at least seven members. A green test that checks nothing is worse than a red
  one, and this is the second time in this project a walk needed that guard.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| G1 | `drain_gaps` not forwarded at all — **the defect exactly as it stood on disk** | KILLED | `test_the_broker_forwards_every_member_of_the_stream_protocol` — and nothing else |
| G2 | present but stubbed: answers `()` without asking the real client | KILLED | the same test — and nothing else |
| G3 | forwards to the wrong member, the non-consuming `gaps` property | KILLED | the same test — and nothing else |
| G0 | **equivalent control**: a comment added to `broker.py` and nothing else | **SURVIVED**, as required | — |

**G1 is the measurement worth keeping.** It restores the broker to precisely the state A found,
and under it **the other 54 tests in `tests/clients/paper/` all pass.** That is the empirical
version of the claim in the diagnosis: 54 tests, written by me, over the surface I built, and
not one of them could see the method I had not written. The only thing that sees it is a test
that does not know in advance what it is looking for.

G3 is the near-miss and the reason the test compares the touched name rather than only counting
a call: `gaps` and `drain_gaps` return the same data, and a broker forwarding to the property
would look right in every console reading and would still never clear the buffer engine 2
drains, so the archive would carry each gap on every tick or none at all depending on which
side you read it from.

**Green in lane after the fix:** `pytest tests/clients/paper/ -q` 55 passed;
`pytest tests/engines/test_risk.py -q` 47 passed; `ruff check` on all four touched paths clean;
`mypy --strict src/acsoe/clients/paper/ src/acsoe/engines/risk/` clean, 6 source files.

### Engine 21's first mutation sweep: fifteen killed, eight survivors, and every survivor is a real hole

**Agent:** B (session 2) · **Task:** spec 92 tail · **Date:** 2026-09-16

Engine 21 was built by the previous B session and committed at `55cf626` **without a sweep** —
the only piece of Phase 6 code in that state. I ran it against code I did not write, which is
the useful direction: I had no memory of what each test was for, so I could not talk myself
into "that one is covered".

Twenty-two mutations plus an equivalent control, same harness and same restore discipline as
the two sweeps above. Subject `tests/engines/test_position_manager.py`, 40 tests.

**Fifteen killed.** The whole kill-switch spine holds: `entry_orders_cancelled` forced to
`True` (M5) dies to five tests, `close_intent` read with `bool()` (M6) dies to the four
parametrised text-shaped values, a `data_guard` hold outranking a liquidation (M7) dies, a
stale entry left uncancelled during a hold (M8) dies, and the two-enum trap reintroduced (M10)
dies — which is the regression test the previous session added after losing thirteen tests to
it, doing exactly its job. The barrier rules hold: stop over target in one tick (M1), barriers
evaluated during a hold (M4), a timeout overriding a price barrier that already fired (M22).
The marking rules hold: a partial portfolio total published (M13), the unrealised sign (M14),
the stop placed above the entry (M17).

**Eight survivors. None is an equivalent mutant and none is a defect in the engine** — I
checked each against the contracts and the config before concluding anything, and in every case
the code is right and no assertion asks it. That distinction matters: the fix is eight tests,
not eight edits to a working engine.

| # | Survivor | What ships silently without it |
|---|---|---|
| M2 | a print **exactly at** the stop does not trigger it (`<=` → `<`) | the barrier test's fixture uses 97.51 and 97.52 around a stop of 97.515 and never lands *on* it. `research/labelling.py:344` computes the label with `low <= stop_price`, so a strict engine and an inclusive label would disagree on exactly the bars that touch — and the whole argument for stop-wins is that the live outcome and the label are computed the same way |
| M3 | a print exactly at the target does not trigger it (`>=` → `>`) | the mirror, against `labelling.py:343` |
| M9 | an order `query_orders` will not report on is treated as **gone** rather than still resting | invariant 3 on the kill switch. There *is* a test named for this — `test_the_flag_is_false_while_an_entry_the_client_will_not_report_on_still_rests` — and it drives the **exception** path (`kraken.fail("trade_volume")`), not the short-answer path. Two different branches, one name, and the name is why nobody noticed |
| M15 | a position opened by **this tick's** fill is left out of `positions_value` | equity understated by the whole notional of every new position for one tick, straight into engine 19's `equity_snapshots`, which is what engine 17's drawdown is measured against |
| M16 | barriers computed from `entry.limit_price` instead of `filled.avg_fill_price` | **the most interesting one — see below** |
| M19 | this tick's published entry is appended again when the store already holds it | the same order settled twice: two cancel rows for one `userref`, or two positions from one fill |
| M20 | an entry that filled **during** the cancel is recorded as a cancellation | a real position lost. The money is spent and no `positions` row exists, so nothing marks it, nothing stops it and nothing exits it. The engine handles this correctly and the comment at the branch explains why; no test drives it |
| M21 | a cancel that did not take still reports `entry_orders_cancelled: True` | the kill switch's retry. The comment at `_manage` states this property in three lines — "a failed cancel leaves something resting and leaves this `False`" — and nothing asserts it |

**M16 is Phase 5's closing finding, arriving again, and it is the reason to run a sweep on
code that already has 40 tests.** `test_a_fill_sets_the_barriers_from_the_fill_price_and_not_
the_bar_close` says in its own name what it is for, and it asserts
`Decimal(position["entry_price"]) == LIMIT`. The paper broker fills a resting post-only buy
**at its limit**, so `avg_fill_price` and `limit_price` are the same number in that fixture and
the assertion cannot tell which one the engine read. The test is not wrong about its subject;
it is wrong about its **witness** — it compares against a value that both the right and the
wrong implementation produce. Phase 5's calibrator mutation was the same shape: the check
agreed with the claim while measuring something else, and what killed it was recomputing the
expected value from a source the mutation could move. Here that means a fill reported at a
price the engine could not have got from its own record.

It also matters beyond paper mode. Reading `entry.limit_price` takes the barrier from **engine
18's own claim about what it asked for**; reading `filled.avg_fill_price` takes it from the
exchange's answer about what happened. `entry` may be a `_PublishedEntry` built out of this
tick's `state["execution"]` payload, so under M16 an engine 18 defect in one field would
propagate into every stop and target with nothing in between. A record of intent is not a
record of what happened.

**M9's lesson is about naming rather than coverage.** The branch is three lines apart from the
one that is tested and the test's name covers both readings, so a reviewer counting tests
against branches would tick it off. The fix names the mechanism in each test rather than the
consequence — "the client raises" and "the client answers for fewer orders than it was asked
about" — because they fail differently and are repaired differently.

**Fix.** Eight tests, no engine change. Each is listed with the mutation it kills in the
follow-up entry below, and the sweep was re-run from scratch afterwards rather than only the
eight being re-checked: a mutation that survives a subset has not been asked.

### Engine 21 — the eight tests, and the sweep re-run from scratch: 22 killed, control survived

**Agent:** B (session 2) · **Task:** spec 92 tail · **Date:** 2026-09-16

Eight tests, **no change to `engine.py`** — `git status` shows the engine unmodified, which is
also the proof the harness restored every one of the twenty-two mutants. The engine was right
about all eight; the suite was silent about all eight.

The whole sweep was re-run from scratch rather than the eight being re-checked on their own.
A mutation that survives a subset has not survived, and the same applies in reverse: a kill
measured only against the test written for it says nothing about whether the other twenty-one
still die.

| # | Survivor now killed by | |
|---|---|---|
| M2 | `test_both_barriers_in_one_tick_resolve_to_stop[a print exactly at the stop is a touch]` | two ids added to the existing parametrisation: a print **at** 97.515 and one **at** 101.97 |
| M3 | `..._resolve_to_stop[a print exactly at the target is a touch]` | |
| M9 | `test_the_flag_is_false_while_the_client_answers_for_fewer_orders_than_it_was_asked` | named for the **mechanism**, not the consequence, so it cannot be confused with the raising case again |
| M15 | `test_a_position_opened_by_this_ticks_fill_is_counted_in_the_portfolio_value` | |
| M16 | `test_the_barriers_come_from_the_price_the_client_reports_not_the_limit_on_record` | |
| M19 | `test_an_entry_in_both_the_store_and_this_ticks_payload_is_settled_once` | |
| M20 | `test_an_entry_that_filled_during_the_cancel_becomes_a_position_not_a_cancellation` | |
| M21 | `test_a_cancel_that_did_not_take_leaves_the_completion_flag_false` | |

**Each of the eight kills its own mutation and nothing else** — one `FAILED` line per run, and
a different one each time. That is the property worth having: eight mutants, eight disjoint
tests, so deleting any one of these tests brings its defect straight back.

**The one design decision here, and it needed thinking about.** Four of the eight need an
answer the paper broker **cannot** produce, and correctly cannot: it fills a resting maker buy
at its own limit and it raises on a `userref` it does not know, which is what
`test_an_unknown_userref_raises_rather_than_answering_nothing` pins over in
`tests/clients/paper/`. A fill at a price other than the limit, a query that omits an order, a
cancel that comes back filled, a cancel that comes back still resting — all four are states a
real exchange reaches and this simulator, by design, never does.

The tempting answer is a fake order client. This file's own docstring says why not: *"no
upstream payload is hand-built"*, and the reason engine 21's two-enum fail-open was caught at
all is that these tests drive a **real** order client rather than a double written to agree
with the engine. So instead there is `_BrokerAnswering`, a wrapper that forwards everything by
`__getattr__` to the real broker and replaces exactly one answer, and the replacement is a
freshly constructed `OrderState` so A's validators still apply — the model refuses a filled
order with no average price or a terminal status with no `closed_at`, so a sloppy double fails
at construction rather than teaching the engine something untrue. Everything the engine reads
about the book, the fee, the quote and the trades still comes from the real chain.

**What the sweep as a whole says about the engine.** Twenty-two mutations, twenty-two killed,
and the kill-switch path is now covered on all four of its failure branches: the flag forced
true, the flag read with `bool()`, the client raising, and the client answering short. That
path is where invariant 8 lives, and it is worth stating plainly that **before this sweep two
of those four were unasserted** in an engine that had 40 tests and was already committed.

Subject after: `pytest tests/engines/test_position_manager.py -q` 48 passed (was 40).
`ruff check` clean on the engine and its tests; `mypy --strict src/acsoe/engines/position_manager/`
clean, 3 source files. `pytest tests/engines/test_position_manager.py tests/engines/test_risk.py
tests/clients/paper/ -q` — 150 passed together.

### Spec 90 — engine 16, and `str(qty)` quietly defeating the one validator built to stop floats

**Agent:** B (session 2) · **Task:** spec 90 · **Date:** 2026-09-16

**What happened.** `DecisionEngine._approved_quantity` returned `str(qty)`, so that
`OrderIntent` could do the parsing. `mypy --strict` was happy, `ruff` was happy, and the
`Money` validator on `OrderIntent.qty` — whose entire job is to refuse a float, because a
float has already lost precision by the time it arrives — never saw one.

**Why.** `str(33.33)` is `"33.33"`, and `Decimal("33.33")` is a perfectly good decimal. The
coercion is not lossy *at that point*; the loss happened earlier, in whatever produced the
float, and stringifying is what hides the evidence. `_to_money` in `clients/kraken/contracts.py`
refuses `float` by type, not by value, precisely because the damage is invisible once you look
at the digits. One `str()` in a method that is not about money at all turned that check off for
the only money field the intent carries.

**It would not have been caught by a rehearsal either.** Engine 11 publishes `qty` as
`format(d, "f")`, a string, so on every real tick the two paths are identical and the defect is
latent. It becomes live only if engine 11 — or a future engine 18 reading the intent back —
ever puts a float in. That is the class the Phase 6 log's opening note names: wrong while
looking right, on every tick until one.

**Fix.** Return the published value untouched, typed `Any`, and let `model_validate` be the
only thing that decides what a quantity is. The docstring now says why the obvious tidy-up is
not one.

**Found by a test, not by reading.** `test_a_clause_that_cannot_be_evaluated_blocks[quantity is
a float]` was written as a throwaway third case in a parametrisation about unusable inputs — I
expected it to pass on the first run. It is the only one of the three that failed, and it is the
reason I now think the "unusable input" parametrisation should include the *type* hazards and
not only the obviously-malformed ones.

### Spec 90 — three more things the tests found before the sweep did

**Agent:** B · **Task:** spec 90 · **Date:** 2026-09-16

**1. The fixture's own premise was false, and the test that checks premises caught it.**
`test_the_upstream_chain_actually_approves_before_engine_sixteen_sees_it` asserts that engines
7, 10 and 11 really did approve before engine 16 is asked anything. It failed on the first run:
engine 11 answered `risk_inputs_unavailable`, because invariant 6 sizes against *total account
equity*, only engine 19 computes that, and engine 19 is C's and does not run in this chain — so
there was no `equity_snapshots` row. Every "engine 16 passes" test in the file would otherwise
have been passing against a chain that never reached engine 16, and passing is exactly what they
would have done, because engine 16 blocks on `no_approved_quantity` and I would have had a green
suite of block tests and no pass tests at all.

That test exists for one reason: **a gate test suite can be entirely green while the fixture
never produces an approval.** It is the cheap standing version of the equivalent-mutant control,
one level up — it asks what the suite would look like if the setup were wrong.

**2. The no-candidate test asserted something the helper had just overwritten.** `approving_state`
sets `state["scout"]["pair"] = candidate` after running engine 7, so `pair` was always present
and `assert "pair" not in state["scout"]` could never hold. Fixed by giving the helper
`candidate=None`, meaning "leave engine 7's own answer", so the payload in that test is a real
engine 7 refusal — the account holds no USD, every pair is excluded for `no_quote_balance`, and
engine 7 names nothing. Worth the entry because the first version *deleted* the key instead,
which would have tested a dict operation rather than engine 7's behaviour.

**3. `importlib.util.find_spec` raises for a missing package and returns `None` for a missing
module.** `test_engines_nine_and_fourteen_still_do_not_exist` guards the only two hand-built
publisher payloads in the file. Its first version failed with `ModuleNotFoundError` — which, for
a test whose failure message reads "C has landed engine 9 or engine 14", would have said the
exact opposite of the truth. Both shapes now count as absent.

**And one tripwire that did its job inside the hour.** The five reason codes went to C by
message with the engine still half-written, and `test_the_reason_codes_are_still_waiting_on_cs_prose`
asserted their absence from `REASON_PROSE`. It was red on the first full run of the file, because
C had already mapped all five. Replaced with the renderable test it was written to become — which
reads the code list out of `engines/decision/contracts.py` by walking `REASON_*` rather than
retyping it, so a sixth code is checked without anyone remembering.

### Decision: engine 16 copies engine 9's and engine 14's provenance and never blocks on it

**Agent:** B · **Date:** 2026-09-16

**Options.** Spec 90 step 3 puts `estimated_slippage_pct` and the router's
`active_model_run_id` in the order intent. Spec 97 step 5 says engine 14 must publish nothing
"engine 15, 16 or 18 reads to decide". Either engine 16 treats those two payloads like the other
five — required, and an absent one blocks with `input_missing` — or it treats them as provenance,
copied when present and omitted when absent.

**Chose.** Provenance. Engines 9 and 14 are in `OPTIONAL_SOURCES`; the other five are required.

**Because.** The two specs are only simultaneously satisfiable this way: a field engine 16 would
refuse over is a field engine 14 reads to decide with, whatever it is called. And spec 90's own
clause says "an **approving** engine's payload is absent" — 9 and 14 approve nothing; they are
non-gates by their own specs, and engine 9's spec goes out of its way to say it never blocks on
its own criteria because a non-gate that does makes `is_gate` wrong.

**Cost, and it is the part I checked rather than asserted.** Requiring them would refuse some
tick that treating them as provenance does not — unless it would not, and it would not. Engine 9
failing to publish means engine 10, a gate, refuses for want of the slippage, so the chain never
reaches engine 16. Engine 14 failing still leaves its key present, because the orchestrator
writes `result.data` into `state` on an `ERROR` result too. So there is no reachable tick where
the two readings differ, and the choice costs nothing rather than costing a little. Pinned by
`test_an_absent_provenance_payload_does_not_block`, parametrised over both.

**Flagged to the lead and to C rather than settled by me**, because it is a reading of two specs
against each other rather than of either one.

### Spec 90 — sixteen mutations, sixteen killed, and three survivors that each said something

**Agent:** B · **Task:** spec 90 · **Date:** 2026-09-16

Same harness, same discipline: byte copy before the edit, restore inside a `finally` with
`sha256` compared in the statement that writes it, one anchor per mutation with a refusal if it
matches other than exactly once. Subject `tests/engines/test_decision.py`. First pass 12 killed
and **3 survived**; three tests added; whole sweep re-run from scratch.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| D1 | the pair comparison dropped — any pair agrees | KILLED | `..._judging_another_candidate_blocks_and_names_both` + the intent walk |
| D2 | the bar comparison dropped — any bar agrees | KILLED | `..._carrying_a_previous_bar_blocks_and_names_both_bars` + the intent walk |
| D3 | an absent required payload read as agreement | KILLED | `test_a_required_payload_that_is_absent_blocks` × 4 of its 5 ids |
| D4 | the intent published on a block as well as a pass | KILLED | `test_no_block_publishes_an_intent` and both new guard cases |
| D5 | a risk payload that did not approve is accepted | KILLED | `..._no_publisher_can_produce_is_still_refused[refused but sized]` — **and nothing else** |
| D6 | an approval with no `qty` is accepted | KILLED | `test_an_approval_that_names_no_quantity_blocks` — and nothing else |
| D7 | a null `closed_bar_ts` read as a bar of zero | KILLED | `test_a_tick_on_which_no_bar_closed_blocks` — and nothing else |
| D8 | an absent candidate read as an empty pair | KILLED | `..._no_publisher_can_produce_is_still_refused[empty pair]` — and nothing else |
| D9 | `str(qty)`, laundering a float past `Money` | KILLED | `..._cannot_be_evaluated_blocks[quantity is a float]` — and nothing else |
| D10 | the walk skips the `cost` payload | KILLED | 4 tests, including `test_checked_records_what_was_examined` |
| D11 | only one bar spelling compared, so `bar_ts` is never checked | KILLED | the stale-bar test + the intent walk |
| D12 | the expected move taken from engine 8 rather than engine 10 | KILLED | `..._the_intent_is_the_one_the_cost_gate_used` — **and nothing else** |
| D13 | the cycle id hard-coded rather than read from `state` | KILLED | the recomputed-intent test — and nothing else |
| D14 | `checked` reports every source whether examined or not | KILLED | 3 tests |
| D15 | a value that will not validate is silently dropped instead of blocking | KILLED | `..._cannot_be_evaluated_blocks[quantity is a float]` — and nothing else |
| D0 | **equivalent control**: a comment and nothing else | **SURVIVED**, as required | — |

**D12 is the one worth the entry, and it is the third time in one day.** Engine 10 copies
`expected_move_pct` from engine 8 and republishes it, so on every real tick the two payloads
hold the **same number** and reading either gives the same answer. The README's claim — that
`net_edge_pct`, `hurdle_pct` and `expected_move_pct` all come from one publisher so the record
cannot show an edge computed from a move the record does not carry — therefore had **no
witness**: a mutation pointing the field at `state["prediction"]` survived all 27 tests.

That is the same shape as engine 21's fill-price test this morning and as Phase 5's calibrator:
an assertion whose two candidate sources happen to hold the same value proves nothing about
which one was read. The fix is the same fix — make them differ. Engine 10 now runs against one
prediction and a second, different one replaces it before engine 16 is asked; the number that
must survive is the one the gate decision was actually made on. **Three occurrences in one day
of "the witness cannot distinguish the hypotheses" is not a coincidence, it is the default
failure of a test written by the person who wrote the code**, and the only thing that has found
any of the three is a mutation.

**D5 and D8 are a different category and I nearly left them as equivalent mutants.** Neither
shape is reachable: engine 7 omits `pair` rather than publishing an empty one, and
`RiskSizing.to_state_data` emits `qty` only under `if self.approved`, so a refusal carrying a
size cannot come out of engine 11's contract. The argument for testing them anyway is that
**`state` is a plain dict** — nothing enforces that what sits under `state["risk"]` came from
`RiskSizing`, the contract governs the publisher and engine 16 reads the mapping. The test says
that explicitly, including that neither is producible today, so the next reader does not spend
an hour working out which publisher emits an empty pair. If a contract changes so that one
becomes producible, the guard is already there and already asserted.

**What the one-test kills say about the file.** Seven of the fifteen died to exactly one test.
Those seven are the properties nothing else touches: the approval check, the quantity check, the
null-bar check, the emptiness check, the float refusal, the cycle id, and the provenance source.
Delete any one of those tests and the corresponding defect ships with a green suite.

`git status` shows `engines/decision/` as the only change, untracked and whole, which is also
the proof the harness restored all sixteen mutants.

**Green:** `pytest tests/engines/test_decision.py -q` 30 passed. Together with the rest of my
lane — `test_risk.py`, `test_position_manager.py`, `tests/clients/paper/` — **180 passed**.
`ruff check` clean on the engine and its tests; `mypy --strict src/acsoe/engines/decision/`
clean, 3 source files.

**Not yet registered.** Engine 16 is not in `bootstrap.py`; registration is the lead's under
spec 82 and is held until specs 87 and 94 are green. `is_gate_matches_registry` will not count
it until then, which is expected rather than a failure.

### `PaperBroker.open_orders()` cannot see an order it accepted on this tick

**Agent:** B (session 2) · **Task:** spec 88 / spec 91 · **Date:** 2026-09-16

**What happened.** Engine 18's invariant 8 probe asks `kraken.open_orders()` whether this
`userref` is already resting. Written, run against the real broker, and the assertion came back
`assert [] == [462601006]`: the order engine 18 had just placed, and which `add_order` had
accepted, was not in `open_orders()`.

**Why.** `PaperBroker.open_orders()` is derived entirely from the **store**:

```python
resting = self._store.resting_orders()
states = await self.query_orders([row.userref for row in resting])
```

The broker's other mutable state, `_pending`, holds orders it has accepted that engine 19 has
not recorded yet — the gap between placing and recording. `_lookup` consults both, so
`query_orders` and `cancel_order` see a pending order; `open_orders` never asks `_pending` at
all, so it does not.

**Why it is a defect and not a quirk.** The broker's whole purpose is that engines 18, 21 and 22
run the *same code* in paper and live. A real exchange's `open_orders` lists an order the moment
it rests, whatever this system has recorded — so paper and live give **different answers to the
same question** on every tick between a placement and engine 19's write. Since engine 19 runs at
the end of the manage chain, that gap is every tick on which anything is placed.

It also under-reports in the one direction that matters. A client answering "nothing is open"
when something is is invariant 3's shape exactly, and it is the same class as the `drain_gaps`
omission this morning: a surface that looks complete and quietly says less than it knows.

**Nothing was damaged, and the reason is worth recording rather than being reassuring.** Nothing
called `open_orders()` until engine 18 did. Engine 21 does not use it — it assembles entries from
`store.resting_orders()` plus `state["execution"]`, precisely because it knows engine 19 has not
run yet — and `test_open_orders_reports_what_is_resting_and_nothing_terminal` drove only orders
the store already held, so the suite had no case where `_pending` was the only source. **A test
written against the store-backed path cannot fail on the store-backed path being the only one.**

**Fix.** `open_orders()` asks for the union of the store's resting rows and `_pending`'s keys,
in that order, through the same `query_orders` it already used — so there is still exactly one
code path deciding whether an order has filled, which is the property the method's own docstring
claims and which I did not want to lose while widening what it looks at. The terminal filter is
unchanged, so a pending order that has since filled is still excluded.

**Consequence for spec 91.** Engine 18's second probe works as designed, and the
`entry_unrecorded_at_exchange` path is now reachable in a test rather than only in principle.
Without this fix engine 18's `open_orders()` probe would have been exactly as blind as
`store.order_by_userref`, which is to say the second probe would have been decoration.

### Spec 91 — engine 18, and a fourth "the witness fits both hypotheses"

**Agent:** B · **Task:** spec 91 · **Date:** 2026-09-16

**Eighteen mutations, eighteen killed, equivalent control survived.** Subject
`tests/engines/test_execution.py` plus `tests/clients/paper/`, because two of the mutations are
in the broker. First pass 15 killed and **2 survived**; two tests added and one refactor; whole
sweep re-run from scratch.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| X1 | the store idempotency probe removed | KILLED | the same-tick-twice test and the collision test |
| X2 | the exchange probe removed | KILLED | `..._that_the_store_never_recorded_places_nothing` — and nothing else |
| X3 | the price rounded **up** | KILLED | 11 tests |
| X4 | `post_only` false | KILLED | 10 tests |
| X5 | the order sent at the **ask** | KILLED | 6 tests |
| X6 | a `userref` on another pair reused instead of raising | KILLED | the collision test — and nothing else |
| X7 | the `userref` ignores the bar | KILLED | the determinism test — and nothing else |
| X8 | the `userref` ignores the pair | KILLED | the same — and nothing else |
| X9 | the `userref` can be zero | KILLED | `test_the_range_mapping_never_produces_zero_at_any_edge` |
| X10 | a rejection published as resting | KILLED | the cross test — and nothing else |
| X11 | an absent intent defaults instead of raising | KILLED | `..._raises_rather_than_defaulting[intent]` |
| X12 | the quantity stringified, laundering a float | KILLED | `..._is_a_float_raises_rather_than_being_stringified` |
| X13 | `PASS` after placing, stopping the chain | KILLED | the placement test and `test_the_engine_never_returns_pass` |
| X14 | a rejected row carries no `closed_at` | KILLED | the cross test — and nothing else |
| X15 | a non-positive bid accepted | KILLED | `test_a_non_positive_bid_raises` |
| X16 | the broker's `open_orders` stops asking `_pending` | KILLED | 3 tests |
| X17 | the broker's `open_orders` double-counts | KILLED | 2 tests |
| X0 | **equivalent control** | **SURVIVED**, as required | — |

**X15 is the fourth occurrence of one failure and the clearest yet.**
`test_a_non_positive_bid_raises` used `pytest.raises(ExecutionError, match="not a price")`.
There are **two** guards that can fire on a zero bid — the bid check ("...is 0, which is not a
price") and the rounded-limit check ("...rounds to 0 ... which is not a price an order can rest
at") — and the regex matches both, so deleting the first guard left the test green. Same shape
as engine 16's expected move and engine 21's fill price: *the witness satisfies both
hypotheses.* Here it is a substring rather than a value, which is the variant worth naming,
because `pytest.raises(match=...)` invites it: the natural thing to type is the memorable
fragment, and the memorable fragment is usually the shared one. The bid guard's message now
names its publisher — "engine 3 published no usable price" — and the test matches that.

**X9 needed a change to the code, not to the test, and it is the right kind.** `userref_for`
hashed and mapped in one expression, and dropping the `1 +` changes the answer for exactly one
input in 2^31. No sampling test can find that, and a test that pretended to would be theatre.
So `to_userref(value)` is split out as the pure range mapping: the entropy is the digest's job
and the range is this function's, and the boundary that cannot be reached through a hash is
simply `to_userref(0)`. That is a decomposition worth having on its own merits — the property
lives in four lines instead of being smeared across a hash — and it happens to make the
guarantee testable at the only place it can fail.

**X2 is a one-test kill and the test only exists because the broker was fixed first.** Engine
18's second idempotency probe was decoration until `PaperBroker.open_orders()` learned to ask
`_pending` (the entry above). Before that fix, removing the probe changed nothing observable.

### Two deviations from spec 91, both flagged rather than quietly taken

**Agent:** B · **Date:** 2026-09-16

**1. The second idempotency probe is `open_orders()`, not `query_orders([userref])`.** Spec 91
step 3 names `query_orders`. It cannot do the job. `OrderClientProtocol` says a call that cannot
be completed **raises** rather than returning an empty result — invariant 3, and the paper
broker implements exactly that — so `query_orders` answers "I have never heard of this order"
and "I cannot reach the exchange" with the same exception. Those require opposite actions:

- read the raise as *unknown* and an outage places a **duplicate order**, which is invariant 8's
  named failure;
- read it as *cannot tell* and the **first** placement of every candidate is refused, because a
  first placement is always unknown, and the system never trades at all.

`open_orders()` has a well-defined negative and still raises during an outage, so invariant 3
holds. It cannot miss the case it exists for: a post-only limit buy at the best bid cannot fill
at placement, so an entry placed earlier in this bar and not yet recorded is still *resting*,
and resting is what `open_orders()` lists. The spec's conclusion is right and its mechanism is
the one that cannot work — the same shape as spec 88's `drain_trades`.

**2. `OrderState` cannot describe an order well enough to record it, so one case publishes no
row.** When the order is at the exchange and the store has never heard of it, engine 18 does not
place a duplicate — and publishes **no order row**, under a fourth reason code,
`entry_unrecorded_at_exchange`.

`OrderState` carries `userref`, `order_id`, `status`, `filled_qty`, `avg_fill_price`, `fee` and
`closed_at`. It carries **no `qty` and no `limit_price`**. Both could be guessed from this
tick — the approved quantity and the current best bid — and both would be wrong the moment
equity or the book moved between the placement and now. A fabricated `limit_price` is a price
nothing ever rested at, written into `orders` as though it had: invariant 2's posture applied to
a record rather than to a trade.

So the duplicate is not placed, which is the part that protects money, and the `userref` is
published so an operator can find the order by hand. **The residual gap is real and is not mine
to close**: an order in that state is one nothing will ever cancel, because engine 21 assembles
entries from the store plus `state["execution"]` and this one is in neither with a describable
shape. Reported to the lead and to A — describing an order found at the exchange needs a field
`OrderState` does not have.

**One thing the tests taught me about the chain, recorded because it first looked like a fixture
bug.** The first version of `test_the_same_tick_run_twice_places_exactly_one_order` re-derived
the whole chain between the two runs and failed with "engine 16 approved nothing". That is not a
fixture problem: once engine 19 has recorded the entry, **engine 11 refuses the pair** under
invariant 6's per-pair clause (spec 89, this morning) and engine 16 publishes no intent, so a
re-derived chain never reaches engine 18 at all.

Engine 18's own check therefore never fires in the ordinary course — and it is still necessary,
because engine 11's refusal is a *gate's* decision that depends on config, on the store being
readable and on spec 89 continuing to exist, and invariant 8 may not depend on any of those.
`test_a_recorded_entry_stops_the_chain_at_engine_eleven_before_engine_eighteen` says all of that
in one place rather than in a comment, and "the same tick twice" now replays one `state` object,
which is what a replay actually is.

**The two-enum trap caught me, in the test file this time.** `assert request.side is
OrderSide.BUY` failed with `<OrderSide.BUY: 'buy'> is <OrderSide.BUY: 'buy'>` — the store's enum
asserted against the client's. Exactly the standing rule the previous B session added to
`code-standards.md` after losing thirteen engine 21 tests to it, and the rule worked: the
failure was immediate and legible rather than silent. Both the engine and its tests now alias
the client's as `ClientOrderSide` and `ClientOrderType` and keep the store's under their own
names, with the client's used only for the `OrderRequest` and the store's only for the published
row.

**And one measurement about the harness itself.** X7 and X8 came back `ANCHOR MATCHED 0x` on the
second run, because splitting `to_userref` out had reformatted the line their anchors quoted.
The harness refused to apply them and said so, rather than reporting two silent non-results as
part of an 18-for-18 sweep. That guard is the previous B session's fix to its own Phase 4
harness defect, and this is the first time it has fired for me.

**Green:** `pytest tests/engines/test_execution.py -q` 34 passed. Whole lane — execution,
decision, position_manager, risk, clients/paper — **216 passed**. `ruff check` clean on all six
paths; `mypy --strict` clean on the three packages, 9 source files.
