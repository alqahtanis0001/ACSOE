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

### SQLite's one-argument `trim()` strips spaces and nothing else, so a tab was a hold reason

**Agent:** B (session 3) · **Task:** migration 0003 · **Date:** 2026-09-16

**What happened.** Migration 0003 adds `positions.hold_reason` with a CHECK whose whole
job is condition 3 of the lead's ruling — NULL means "did not hold", never "unknown" —
by refusing the blank string, which is how "unknown" normally gets past a nullable
column: non-null, so every `IS NOT NULL` read calls it a hold, and blank, so it renders
as nothing. Written the obvious way, `CHECK (hold_reason IS NULL OR trim(hold_reason) <> '')`,
and the parametrised test failed on one case of three: `DID NOT RAISE IntegrityError` for
a lone tab.

**Why.** **`trim(X)` in SQLite removes spaces only** — not tabs, not newlines. The
two-argument form `trim(X, Y)` removes any character in `Y`, and that is the form this
needed. Python's `str.strip()` removes all whitespace, so the row model's validator and
the database's CHECK — written to be the same refusal, deliberately, because a constraint
the two layers disagree about is one of them not really applying it — disagreed on every
whitespace character except the space.

**Fix.** `trim(hold_reason, ' ' || char(9) || char(10) || char(11) || char(12) || char(13))`,
which is the ASCII whitespace `str.strip()` removes. Python stays the stricter of the two on
exotic Unicode whitespace, which is the safe direction: `PositionRow` is the only supported
way in. The parametrisation now carries a tab, a newline and a CRLF-plus-spaces case rather
than three kinds of space, and the migration's comment says why those and not more spaces.

**Consequence.** The general shape is worth more than the bug: a parametrised case list whose
entries are all the *same* thing is a single test wearing a costume. Three kinds of space
would have been three copies of one question. The finding is the same family as the day's
recurring one — a witness that cannot distinguish the hypotheses — arriving in the inputs
rather than in the assertion.

### Decision: `hold_reason` is a column on `positions` with no enumeration of its values

**Agent:** B (session 3) · **Date:** 2026-09-16

**Options.** The lead's ruling settles *that* the database must carry the manage chain's
hold reason and rejects inferring it from a `data_guard` row in `block_records`. Three
things were still open when I wrote the migration.

**Chose, 1 — a column on `positions`, not a new table.** The hold is per position and is read
per position: the console renders it on the row it is already drawing, and a position is the
only thing that can be held. `positions` is already in `StoreClient.WATERMARK_TABLES`, so
writing a hold moves the console's poll watermark for free; a new table would have to be added
to that tuple, changing behaviour under every existing watermark test mid-phase, and would be
a lead escalation on its own because `db_migrates_from_empty` asserts the documented table set.
Same reasoning as 0002's, which put the system mode on `runs` rather than in a state table.

**Chose, 2 — no CHECK enumerating the hold reasons, unlike `runs.system_mode`.** Idle/running/
frozen is a closed set the console must render as a status band, so 0002's CHECK is right there.
Hold reasons are not closed: engine 21 declares them in its contracts and the console maps them
in `REASON_PROSE`. A CHECK would be a **third** copy of that list and the only one that cannot
be corrected without another migration, so it is the copy that would drift — and the failure it
would buy is a liquidation-era write refused at runtime by SQLite over a reason nobody had
enumerated. The list is already enforced where it can be kept true: spec 99's walking test goes
red at *test* time on a code the console cannot render.

**Chose, 3 — the blank string is refused, in both layers.** It is the one part of condition 3
a database can enforce. Whether a hold *happened* is a property of the tick and not of the row,
so no CHECK can enforce condition 2's "cleared on every tick that did not hold"; that is a
property of the writer and is pinned by tests.

**Cost.** A hold reason the console cannot render still reaches the database and still renders
as "No reason was recorded." — silently, exactly as `ownership.md` warns. That is deliberate:
the alternative pushes the failure into the write path of the one engine that must never fail
to record, and invariant 12 says a rejection that is not written is a defect equal to a lost
trade.

### Migration 0003 — eight mutations, eight killed, equivalent control survived

**Agent:** B (session 3) · **Task:** migration 0003 · **Date:** 2026-09-16

Subject `tests/db/test_migrations.py` plus `tests/clients/store/`. First pass: seven applied,
five killed, **one refused by the harness and one survivor**. Both are below, and the whole
sweep was re-run from scratch after the fix rather than the two being re-checked.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| H1 | the CHECK replaced by `1 = 1` — a blank is a hold reason | KILLED | `test_a_blank_hold_reason_is_refused`, all five cases |
| H2 | the obvious one-argument `trim()` | KILLED | the same test's tab and two newline cases — **and only those three**, which is the defect above |
| H3 | `PositionRow`'s validator never fires | KILLED | `test_a_blank_hold_reason_is_refused_by_the_row_model`, all four cases, and nothing else in 245 |
| H4 | `hold_reason` defaults to `""` rather than `None` | KILLED | `test_the_seed_writes_no_hold_reason` plus every seeded test in the lane — the database refuses the write, so 76 fixtures error |
| H5 | the upsert omits the column entirely | KILLED | the round-trip test and the clearing test |
| H6 | **condition 2 as a defect** — written on insert, never updated | KILLED | `test_rewriting_the_position_without_a_hold_reason_clears_it`, and nothing else |
| H7 | `open_positions` orders by `position_id` **descending** | KILLED (second pass) | `test_open_positions_breaks_a_tie_on_position_id_and_not_on_insertion_order` |
| H0 | **equivalent control** — `not value.strip()` spelled `value.strip() == ""` | **SURVIVED**, as required | — |

**H4 was the refusal, and the harness guard did its job for the second time this phase.**
`contracts.py` is one of the ~120 CRLF files `code-standards.md` records, and the anchor was
typed with LF, so the harness reported `ANCHOR MATCHED 0x — REFUSED, not applied` rather than
counting a silent non-result as a kill. The harness now retries a multi-line anchor with CRLF
before refusing, and the restore is still byte-exact because it writes the original bytes back.

**H6 is the one worth naming.** It is condition 2 of the ruling written as code: the column is
set when the row is first inserted and never updated afterwards, which is exactly "a hold
written and never cleared". One test kills it, and the test's own value is that the clearing
happens *by* the writer writing the row it would have written anyway — `_upsert` sends every
column — rather than by engine 19 remembering to blank a field. A mechanism nobody has to
remember is the only kind that survives the tick it was written for.

**H7 survived the first pass and is a real hole in code I did not write.** `open_positions()`
has ordered `opened_at ASC, position_id ASC` since Phase 0 and **nothing asserted the
tie-break**. Every position these builders and the seed make shares one `opened_at`, so the
tie is the ordinary case rather than a contrived one — a liquidation closes positions together
and the console renders them together — and with no tie-break SQLite may return them in any
order, so the console's list would reorder itself between two polls of a database nothing had
written to. It survived all 244 tests in the lane. The fix is one test and no change to the
client: the rows are written in the reverse of the expected order, so insertion order and sort
order disagree, and the first assertion checks the tie exists before the second checks how it
was broken.

**One unexplained observation, recorded rather than chased.** H3's first run reported `4 failed,
240 passed, 1 error`, the error in a `seed_fixtures`-backed test; the same mutation re-applied
and re-run over the same subject reported `4 failed, 241 passed` with no error and the same four
killing tests. Not reproduced, not diagnosed, and it does not change H3's verdict. `unexplained`
is an acceptable thing to write (HANDOFF 1, rule 5).

### `OrderState` gained `qty` and `limit_price`, and the order engine 18 could not describe is now recorded

**Agent:** B (session 3) · **Task:** job 2, A's spec 84 amendment · **Date:** 2026-09-16

**What happened.** Spec 91 shipped with a hole I found and could not close from my side:
`PaperBroker.open_orders()` tells engine 18 that an order is at the exchange, the store
has never heard of it, and `OrderState` carried no `qty` and no `limit_price` — so the
order could be **detected and not described**, and engine 18 published no row under
`entry_unrecorded_at_exchange`. Nothing would ever cancel that order, because engine 21
assembles entries from the store plus `state["execution"]` and it was in neither. A
landed both fields; this is my half.

**The five construction sites in `broker.py`**, one per shape, and each now says what the
order *is* beside what has happened to it: a resting order, a resting order that filled,
a market fill, a recorded row that is already over, and a cancel. Two of them are worth
naming because the value was available in more than one place:

* **A cancel takes both from the state it just resolved**, not re-derived from the
  `_Pending` or the `OrderRow`. A cancel changes what has *happened* to an order and
  never what the order *is*, so restating either would be a second place they could be
  computed, and the only way the two could differ is if one were wrong.
* **A market fill's `limit_price` is `None` because the request has none**, not because
  the field was left out. `OrderState` carries no `order_type` on purpose — presence
  *is* the statement — so the mutation that claims `pending.fill_price` as a limit price
  is the one that matters, and it dies to one test.

**Engine 18 now publishes the row**, and `_AlreadyPlaced.row` stopped being optional
rather than being left unreachable. Three of that row's fields still are not
observations, and each is a statement about what this system places rather than a guess
at a number: `pair`/`side`/`intent`/`order_type` (the `userref` is `userref_for(pair,
bar)`, so an order resting under it is this candidate's by construction, and the only
order this engine places is a post-only limit buy — an exchange answer with no limit
price therefore **raises** rather than being recorded as a limit order with a null
price), and `oflags` (invariant 8 says post-only; `""` would be the same kind of claim
with the opposite content).

**`placed_at` is the one gap the amendment does not close, and it is flagged rather than
taken quietly.** `OrderState` carries `closed_at` and no placement time. The row says
*this* tick — the earliest moment the system can attest to anything about the order —
and the cost is that engine 21's entry window restarts from here, so an already-stale
order is cancelled up to one window (300s) late. Two things make that the right trade.
The cost is bounded and the failure it replaces is not: an unrecorded order is one
nothing ever cancels. And the kill switch is complete the moment the row exists, because
**`close_all` cancels every resting entry immediately, regardless of that window**
(invariant 8) — which is the property that was actually broken, not the timeout.
Back-dating `placed_at` to force an immediate cancel was the alternative: it writes a
time that never happened into the column research and the console read as a placement
time, which is a downstream rule's logic smuggled into a data field.

### Job 2 — ten mutations, ten killed, equivalent control survived

**Agent:** B (session 3) · **Task:** job 2 · **Date:** 2026-09-16

Subject `tests/clients/paper/`, `tests/engines/test_execution.py` and
`tests/engines/test_position_manager.py`. First pass: nine applied, eight killed, one
**refused** and one **equivalent by accident**; both are below and the whole sweep was
re-run from scratch afterwards.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| J1 | a resting state reports a quantity that is not the order's | KILLED | 5 tests, including engine 21's `..._filled_during_the_cancel_becomes_a_position` |
| J2 | a resting state reports no limit price | KILLED | 5 tests, three of them the new broker ones |
| J3 | a terminal recorded row reports `filled_qty` as `qty` | KILLED | `test_a_filled_entry_still_says_what_it_asked_for_and_at_what_limit` and `test_a_recorded_order_wins_over_this_ticks_copy` |
| J4 | a terminal recorded row reports `avg_fill_price` as `limit_price` | KILLED | `..._still_says_what_it_asked_for_and_at_what_limit` — and nothing else |
| J5 | a cancel forgets the limit the order rested at | KILLED | `test_a_cancel_still_describes_the_order_it_cancelled` — and nothing else |
| J6 | a market fill claims its fill price as a limit price | KILLED | `test_a_market_sell_reports_no_limit_price_because_it_has_none` — and nothing else |
| J7 | engine 18 goes back to describing the unrecorded order by guessing | KILLED | the unrecorded test and the no-limit-price test |
| J8 | engine 18 reads `filled_qty` where it means `qty` | KILLED | `..._that_the_store_never_recorded_places_nothing` — and nothing else |
| J9 | the no-limit-price guard removed | KILLED | `test_an_exchange_order_with_no_limit_price_is_refused_rather_than_recorded` |
| J10 | the unrecorded row carries `placed_at` 0 | KILLED | `test_the_unrecorded_row_is_stamped_with_this_tick_and_not_left_unset` |
| J0 | **equivalent control** — `state.qty` read through a lambda | **SURVIVED**, as required | — |

**J4 was the refusal, and it is the harness earning its place for the third time this
phase.** The anchor `qty=row.qty,\n            limit_price=row.limit_price,` matches
**twice** in `broker.py` — once in `_terminal_state_of_row`'s `OrderState` and once in
`_state_of_row`'s call to `_resolve_resting`, which passes the same two fields by the
same names one indent level out. `ANCHOR MATCHED 2x — REFUSED` rather than a mutation
applied to whichever came first and a kill credited to the wrong branch. The fix is one
more line of context in the anchor, and the general point is that a *renamed-through*
value is exactly the text a positional anchor cannot tell apart.

**J1 was equivalent by accident on the first pass and that is worth recording as a
mistake rather than quietly fixed.** I wrote it as `qty=Decimal(0) + qty * 0 + qty`,
intending "reports the filled quantity", and that expression **is** `qty`. It survived,
and for a moment it read like a hole. The realistic wrong source, `filled_qty`, is zero
on a resting order and `OrderState` refuses a zero quantity outright, so there is no
in-universe wrong value to substitute — the mutation became a wrong constant, which asks
the assertion a slightly different question: does it pin the value, or only its presence?
It pins the value.

**One thing the witnesses had to be built around.** The obvious test of "a filled order
still says what it asked for" cannot be written against this simulator: it fills a
resting maker buy **in full at its own limit**, so `qty`, `filled_qty`, `limit_price` and
`avg_fill_price` are 10, 10, 99.00 and 99.00 and no assertion over them can tell which
field the broker read. The same shape as engine 21's fill-price test in the morning and
engine 16's expected move. So that test drives a **recorded row** that filled *partially*
and *below* its limit — 10, 4, 99.00, 98.50, four distinct numbers — which a real
exchange produces, `OrderRow` validates, and the simulator correctly never reaches. The
same reasoning made the engine 18 test move the book and the intent between the two runs:
with the same tick twice, "read from the exchange" and "guessed from this tick" produce
identical numbers and the assertion is about nothing.

### The engine 9 tripwire fired, and acting on it made engine 16's coherence walk real

**Agent:** B (session 3) · **Task:** job 2 tail · **Date:** 2026-09-16

**What happened.** `test_engines_nine_and_fourteen_still_do_not_exist` went red during
job 2 — not because of anything I changed, but because C landed spec 96 and engine 9
`order_book` now exists. That is the second tripwire of this phase to fire and be acted
on rather than weakened (the first was spec 89's two reason codes).

**What it asked for, and what it got.** The tripwire's own message says to replace the
hand-built payload with the real engine's output and to *check what it publishes for a
`pair` and a `bar_ts`*. `approving_state` in `tests/engines/test_decision.py` now runs
`OrderBookEngine()` in chain order, `order_book_payload()` is **deleted** rather than
kept "for the unit tests" — a stand-in that outlives its publisher is a second
description of engine 9 that nothing keeps true — and all 29 other tests in the file
passed unchanged, which is the evidence that engine 16's walk needed no edit. That was
the design claim made when engine 16 was built: the pair and bar clauses are a **walk
over the payloads**, not a hand-written list of four comparisons, precisely so that a
publisher landing later is checked without engine 16 being touched. This is the first
time that claim has been tested by an actual new publisher, and it held.

The seam is now pinned rather than assumed:
`test_engine_nines_own_payload_is_walked_by_the_coherence_check` asserts engine 9 appears
in `checked`, and splices a **real** engine 9 payload for the other candidate — not the
SOL/USD one with its `pair` edited — to prove a disagreement blocks. The tripwire is
narrowed to engine 14 and keeps its shape: it asserts absence, so it fails when C is
right, which is the only direction a placeholder should be able to fail in.

**And a witness problem it exposed, which is not mine to fix here.** Engine 9's real
estimate on this fixture's book is **exactly zero**: the fake's top bid level holds more
than the 5,000 quote basis, so the walk consumes one level and fills at the best bid.
Friction drops from the hand-built 0.67% to 0.62% and the constant comment is corrected.
That is engine 9 working correctly, and it makes a **weak witness** — an engine 10 that
ignored the slippage term entirely produces the same friction. Spec 94's acceptance is
"engine 10 reads engine 9's slippage, **proven by recomputation**", and a zero cannot
prove it. Recorded here and in the constant's own comment so spec 94 starts from a book
thin enough for the estimate to be non-zero, rather than discovering it while writing the
assertion.

### Decision: engine 22 never reads a balance, so spec 93's `balance_last_known_good` is not defined

**Agent:** B (session 3) · **Task:** spec 93 · **Date:** 2026-09-16

**Options.** Spec 93 item 4 names two fallbacks to record on a liquidation's trade,
`asset_pairs_last_known_good` and `balance_last_known_good`, and item 7 asks for a test
in which the balance fetch fails. Either engine 22 reads a balance somewhere, or the
second constant describes a behaviour it does not have.

**Chose.** Engine 22 reads no balance at all, defines only
`asset_pairs_last_known_good`, and the outage test proves the liquidation completes
**while the balance fetch is failing** rather than proving a fallback fired.

**Because.** An exit's quantity is the position's, from the `positions` row. The only
thing a balance could add is a cap at the base currency actually held — and **the paper
ledger is quote-side only**, by my own spec 88 ruling: it does not credit base on a buy,
because engine 19 already represents the base leg as the `positions` row and crediting
it here would be a second representation of one exposure. So the base balance of every
paper position is zero, and a cap would round every paper exit to nothing. The rule the
constant would be serving is real and is satisfied by a different mechanism: invariant
14 requires that a *failing* balance fetch must not stop the liquidation, and nothing on
this path asks for one.

**Cost.** A constant spec 93 names does not exist, so a reader comparing the spec to the
code finds a gap and has to come here. That is better than the alternative: a fallback
name nothing ever emits reads as a behaviour the system has, and the first person to
query `fallbacks_used` for it would conclude the balance was always fresh.

**Escalated to the lead**, because it is a deviation from a written spec rather than a
detail inside one.

### Two things spec 93 says that the surfaces do not

**Agent:** B (session 3) · **Task:** spec 93 · **Date:** 2026-09-16

**`last_known_good_asset_pairs` is a property, not a method.** Spec 93 item 4 writes
`clients.kraken.last_known_good_asset_pairs()`. A's client, C's fake and my paper broker
all declare it `@property`. Written as the spec has it, the engine would have got a bound
method, `retained.value` would have raised `AttributeError`, and — because a per-position
failure is caught — a **liquidation would have reported `exit_incomplete` for every
position during exactly the outage the rule exists for**, with the retained snapshot
sitting there readable. Recorded rather than silently corrected, because it is the third
time in Phase 6 a spec has named a mechanism that does not exist (`drain_trades` in 88,
`query_orders` as the second idempotency probe in 91) and the pattern is worth the
count: the specs' *conclusions* have been right every time and their *mechanisms* wrong.

**The paper broker cannot price a market sell during a total outage, and that is the
simulator rather than the rule.** The liquidation test fails `balance` and `asset_pairs`
and leaves the book and the fee tier up. Neither is retained — invariant 2 is explicit
that a stale spread is a loaded gun pointed at the cost gate and that a fee nobody
fetched invalidates it — so `PaperBroker._fill_market` has nothing to walk and no rate to
charge if they fail. In live mode the exchange prices the market order itself and neither
call is on the path. The test says so in its own docstring rather than arranging it
quietly.

### Spec 93 — engine 22, and the mutation that found a hole in the *reason* rather than the code

**Agent:** B (session 3) · **Task:** spec 93 · **Date:** 2026-09-16

**Twenty-two mutations, twenty-one killed, equivalent control survived.** Subject
`tests/engines/test_exit.py`. First pass: nineteen applied, sixteen killed, **three
survivors and three refusals**; four tests added, one engine change, and the whole sweep
re-run from scratch twice.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| E1 | the hold does not suppress exits | KILLED | `test_a_triggered_stop_places_no_exit_on_a_data_guard_tick` — and nothing else |
| E2 | a liquidation is held by a `data_guard` block | KILLED | the two liquidation tests |
| E3 | retained rules read on an ordinary tick | KILLED | `test_the_retained_rules_are_not_read_outside_a_liquidation` — and nothing else |
| E4 | `positions_closed` true with a position still open | KILLED | 6 tests |
| E5 | the exit quantity rounded **up** | KILLED | 22 tests, including the rounding test's 10.12-against-10.13 |
| E6 | the `userref` idempotency probe removed | KILLED | the same-tick-twice test and the collision test |
| E7 | a `userref` recorded against another position reused | KILLED | the collision test — and nothing else |
| E8 | the `\|exit` salt dropped from the digest | KILLED (third pass) | `test_the_exit_userref_scheme_is_pinned_to_its_values` |
| E9 | the missing-entry-fee guard removed | KILLED (second pass) | `test_an_entry_order_with_no_fee_is_refused_rather_than_priced_at_zero` |
| E10 | a foreign quote currency priced at 1 anyway | KILLED | `..._refused_rather_than_priced` — and nothing else |
| E11 | realised PnL ignores both fees | KILLED | the recomputation test — and nothing else |
| E12 | the entry price recorded as the exit price | KILLED | the same |
| E13 | a liquidation recorded as a barrier outcome | KILLED | `test_close_intent_exits_a_position_no_barrier_touched` |
| E14 | an unfilled exit closes the position | KILLED | `test_positions_closed_is_false_when_an_exit_did_not_fill` |
| E15 | the request reaches the client as a **buy** | KILLED (second pass) | `test_the_request_that_reaches_the_client_is_a_market_sell_and_not_only_the_row` |
| E16 | a position that could not be exited is not reported | KILLED | 6 tests |
| E17 | the retained-rules fallback not recorded | KILLED | the outage test — and nothing else |
| E18 | a flat account never finishes its liquidation | KILLED | `test_a_liquidation_on_a_flat_account_is_finished` |
| E19 | `close_intent` read with `bool()` | KILLED | the four text-shaped parametrised values |
| E20 | a short client answer treated as "no such order" | KILLED (second pass) | `test_a_client_that_answers_for_fewer_orders_than_it_was_asked_is_a_defect` |
| E21 | the per-position failure messages dropped from the reason | KILLED | 4 tests |
| E0 | **equivalent control** — `not still_open` spelled `len(...) == 0` | **SURVIVED**, as required | — |

**E9 is the one worth the entry, and it found a hole in the engine rather than in the
tests.** Deleting the guard that refuses an entry order with no fee left
`test_an_entry_order_with_no_fee_is_refused_rather_than_priced_at_zero` **green**. The
test was not wrong about its subject: no trade was written and the status was `ERROR`,
exactly as it asserts. What happened instead is that the next line raised `TypeError` on
`Decimal(None)`, the per-position `except` caught it, and both the guard and the crash
arrive as the same `exit_incomplete`.

That is a real defect and it is in the engine. A per-position exception is caught so the
other positions are still liquidated — on a liquidation, flat on two of three beats flat
on none — and the message was being **swallowed with it**. An operator during an
emergency would have had `exit_incomplete` and no way to tell a missing fee tier from a
foreign quote currency from an order the exchange refused, and each of those needs a
different response. The engine now collects the per-position messages and names them in
`EngineResult.reason`; three tests assert the sentence rather than only the status, and
E21 exists to keep it that way.

**E15 is the "a record of intent is not a record of what happened" shape again, and this
time on an order rather than a number.** Every assertion about the exit being a market
sell read the **published row** — which is engine 22's own claim about what it sent.
Pointing the request at `ClientOrderSide.BUY` left the row saying `"side": "sell"` and
survived. What kills it is a wrapper that captures the real `OrderRequest` handed to the
client, the same device engine 18's test uses. Phase 5's closing finding, fourth
appearance in this lane.

**E8 was a survivor I nearly wrote off as equivalent, and the argument for testing it is
the one worth recording.** Dropping the `|exit` salt from the digest changes the
`userref` and changes nothing a test could reasonably assert: still deterministic, still
positive, still in range, still derived from the position, same collision probability. It
is equivalent *within* a version. It is not equivalent **across** one — and that is the
hazard: change the scheme and the next release computes a different identifier for an
exit the exchange is already holding, finds no recorded order under it, and places a
second market sell. Invariant 8's named failure arriving through a deploy instead of
through a crash. So the values are pinned as golden numbers with a docstring saying that
a failure here is a question about the orders resting under the old identifiers, not an
invitation to update the literals.

**E20 needed a test the simulator cannot produce**, and the answer is engine 21's:
`_AnswersAboutNothing` wraps the real broker and replaces exactly one answer. The paper
broker *raises* on a `userref` it does not know, correctly, so "the client answers about
fewer orders than it was asked" is a state a real exchange reaches and this simulator by
design never does. Named for the mechanism rather than the consequence, which is the
lesson engine 21's sweep left behind: two branches three lines apart had one test name
between them.

**Three refusals, all from the anchor guard, and one of them mattered.** `E4` and `E0`
pointed at a line the E9 fix had reindented; `E16` pointed at `incomplete = True`, which
that fix replaced with `problems.append(...)`. The harness reported `ANCHOR MATCHED 0x —
REFUSED` each time rather than counting a silent non-result as part of a clean sweep.
That is now the fourth and fifth time that guard has fired in Phase 6.

### A mutation harness defect: a stale `.pyc` can report a kill that did not happen

**Agent:** B (session 3) · **Task:** spec 93 tail · **Date:** 2026-09-16

**What happened.** Three runs across the day came back with a non-zero exit and **no
pytest summary at all** — a verdict of KILLED with an empty list of killing tests. Twice
that was only a missing explanation. Once it was worse: `E8` was reported KILLED, and
re-applying the identical mutation on its own reported SURVIVED. A harness that reports a
kill that did not happen is the failure the equivalent-mutant control exists to catch and
would not have caught, because the control is one mutation out of twenty-two.

**Why.** Every incident followed a mutation to the **same file** as the one before it.
A mutant lives for exactly one pytest run and is then overwritten with bytes of the same
length; CPython validates a cached `.pyc` against `(source mtime, source size)`, and
Windows mtime granularity is coarse enough that an apply-run-restore cycle inside one
tick of the clock leaves a cache entry the next run considers current. The next run then
imports either the previous mutant or a half-written module, and pytest dies before it
prints a summary.

**Fix.** The subprocess runs with `PYTHONDONTWRITEBYTECODE=1`, which removes the
mechanism rather than working around it. The whole engine 22 sweep was re-run afterwards:
twenty-two mutations, seventy-nine `FAILED` lines, **every mutation now reporting its
killers** and none silent.

**Consequence.** This is a defect in the *instrument*, and the two earlier "unexplained"
observations in this log — `H3` reporting one spurious error, and `E8` — are almost
certainly the same cause. Worth the entry because a mutation sweep's whole value is that
its negatives mean something, and a harness that can report a false kill quietly reduces
it to theatre. The same care the previous B session's anchor guard was added with.

### Engine 14 landed and the tripwire fired a second time; it is retired rather than narrowed again

**Agent:** B (session 3) · **Task:** spec 93 tail · **Date:** 2026-09-16

C landed spec 97 hours after spec 96, so `test_engine_fourteen_still_does_not_exist` —
itself the narrowed remnant of the two-engine tripwire — went red the same day it was
written. `approving_state` now runs the real `AdaptiveRouterEngine` in chain order and
`router_payload()` is deleted, the same treatment engine 9's stand-in got.

**All thirty other tests in the file passed unchanged, again.** Two real publishers
landed into engine 16's coherence walk on one day and neither needed an edit to engine
16, which is what the walk-over-payloads design was for. `test_a_source_that_names_no_pair
_is_not_a_disagreement` is now asserted against engine 14's **real** payload rather than
against a dict that agreed with it by construction — the pass half of the pair clause got
stronger for free.

The tripwire is replaced by the property it was protecting rather than by a third
narrowing: `test_no_publisher_payload_in_this_file_is_hand_built_any_more` asserts both
engines exist and that neither payload function does. A tripwire that has run out of
things to trip is a test that will be green forever; the invariant underneath it is not.

### `opened_at` closed the `placed_at` gap, and the fix is smaller than the workaround was

**Agent:** B (session 3) · **Task:** job 2, second half · **Date:** 2026-09-16

**What happened.** I recorded `placed_at` on engine 18's recovered row as *this tick*,
argued at length that the resulting late cancel was bounded and therefore acceptable,
and wrote a test asserting it. A landed `OrderState.opened_at` — Kraken's `opentm` — in
the same amendment, and I had not read it: my five broker sites populated `qty` and
`limit_price` and silently dropped the field that answered my own objection. The lead
caught it by `grep`.

**Why it matters more than a missed field.** The five broker sites answering `None`
would have looked exactly like an exchange that did not report `opentm`, and engine 18
has a fail-closed branch for that — so **the simulator would have driven engine 18 down
a refusal path built for a real exchange's omission**, publishing no row for an order it
knew the placement time of to the microsecond. A defect that presents as a documented
behaviour is the worst kind to find later.

**Fix.** All five sites carry it: a resting order and a resting order that filled use
the placement time, a recorded row uses `row.placed_at`, a cancel passes the resolved
state's through unchanged, and a market fill uses the one injected clock reading for
both `opened_at` and `closed_at` — which is precisely the case A's seventh coupling
allows equality for. `test_every_order_state_the_broker_builds_carries_an_opening_time`
sweeps all five shapes in one test rather than trusting five separate ones, because the
property is "no site may answer `None`" and a site-by-site list is written by the person
who forgot a site.

**Consequence: the trade-off I reasoned my way into was the wrong question.** The "a
time that never happened" objection was right, and it applies to a case one-hundredth
the size of the one I applied it to — only an exchange that genuinely omits `opentm`.
`OrderRow` has no `fallbacks_used` column (that is a `trades` column), so a substituted
time could not even be recorded as a substitution, which is what keeps that case a
refusal rather than a fallback. **The general lesson is the lead's, not mine: read the
working tree, not `HEAD`, for anything another lane landed this session.** I had checked
`OrderState` at `fe06a72` and concluded A had not landed; A had, uncommitted.

### Decision, reversed: engine 18 reports the contradiction rather than raising it

**Agent:** B (session 3) · **Date:** 2026-09-16

**Options.** An `OrderState` for one of engine 18's own entries coming back with no
`limit_price` contradicts the placement — invariant 8 makes every entry a post-only buy
limit. I implemented the refusal as a `raise`; contract rule 7 turns that into `ERROR`
with `blocks_trading=True`, which is fail-closed and loud.

**Chose**, on the lead's ruling: a named reason code, no row, no raise, the candidate
abandoned for the tick. The sibling of `entry_unrecorded_at_exchange`.

**Because `ERROR` has a second consumer.** Engine 19 writes `block_records.status =
'ERROR'`, and engine 17 `safety` counts those rows in the trailing hour against
`safety.max_errors_in_window` and **freezes the account**. An exchange contradicting
itself about one order is not the system malfunctioning, and it must not spend the
circuit breaker's budget. My reasoning had stopped at "fail-closed and loud is correct",
which is true of the single tick and wrong about the hour.

**Cost.** A contradiction now looks, to anything reading `status`, like an ordinary tick
that placed nothing. That is what the reason code is for, and the test asserts
`status is OK` and `blocks_trading is False` explicitly rather than only asserting the
code — the half that would otherwise be missing, because a raise would satisfy every
other assertion in that test.

**The general shape is worth more than the ruling.** A fail-closed answer is not free:
it is spent out of a budget somewhere, and `ERROR` is the one status in this system
with an account-level consequence attached. Worth checking, before making something an
`ERROR`, what else counts them.

### `entry_unrecorded_at_exchange` narrowed to one case, and the other two got their own codes

**Agent:** B (session 3) · **Date:** 2026-09-16

A raised this rather than deciding it: once the row is buildable, the code may no longer
describe a real outcome, and its console prose and spec 99's walking test both hang off
whether the branch still publishes nothing.

It does — for one case out of three, so the code stays and is narrowed, and the two
cases it lost got their own spellings:

| Code | Outcome |
|---|---|
| `entry_recovered_from_exchange` | fully describable; the row is published and engine 21 cancels the order in the ordinary window |
| `entry_at_exchange_is_not_a_limit` | no `limit_price`; no row |
| `entry_unrecorded_at_exchange` | no `opened_at`; no row |

Three outcomes under one code is how a console ends up unable to tell an operator which
of them happened, and they call for different responses: the first needs nothing, the
second means the exchange is answering about an order this system did not place, the
third is an exchange quirk. `test_the_six_outcomes_this_engine_reports_have_six_spellings`
pins the count so a fourth outcome cannot quietly join an existing code.

### Migration 0004 and the enumeration engine 14 weights from

**Agent:** B (session 3) · **Task:** the 0004 boundary · **Date:** 2026-09-16

Two things at one boundary, both from C-models building against the store rather than
against the spec's description of it.

**`base_rate_brier REAL` nullable.** Engine 20 already computes it per fold and discarded
it for want of a column. The reasoning that matters is C's near-miss, and it is in the
migration's own comment because it will look reasonable again: deriving it as
`win_rate * (1 - win_rate)` gives a plausible number answering a different question,
because `brier` is over every row of the fold and `win_rate` is over the BUY subset
only. Nullable with no default, because `0.0` is a perfect baseline that would make
every pre-0004 row look skill-less and `0.25` is a guess about folds nobody measured.

**`all_leaderboard_rows(*, model_id)`.** Neither existing read can enumerate:
`leaderboard_entries` takes `model_version` as an argument, and `leaderboard()` is the
console's truncating window. My own docstring on the first was the argument against
reusing the second, and C found the consequence for weighting is worse than for an
existence check — **a version outside the window gets no weight because nobody looked,
not zero weight for having no edge, and the weights still sum to one over the wrong
set.** Nothing downstream can tell.

`model_id` is **required and not defaulted**, and that is the one design decision here.
The method has no `LIMIT`, and "no limit" is only safe because the read is bounded: one
model's rows are bounded by its walk-forward, the table as a whole by nothing. A default
would hide the bound at the call site, which is the same class of problem as the
truncating window — the caller cannot see what it is getting.

### A seam landed mid-sweep and produced a false kill on my equivalent control

**Agent:** B (session 3) · **Task:** the 0004 boundary · **Date:** 2026-09-16

**What happened.** The `opened_at` sweep reported `K0`, the **equivalent control**, as
KILLED — `int(x)` rewritten as `int(int(x))`, which cannot change an answer. Six tests
failed, including `test_engine_sixteen_really_approved_before_engine_eighteen_is_asked`,
which does not read `opened_at` at all.

**Why.** Not the mutation. C-models landed engine 14's `_read_leaderboard` between two
runs of the sweep, calling `all_leaderboard_rows()` with no arguments against the
signature I had landed an hour earlier as `(*, model_id)`. Every test that builds an
approving `state` went red on a `TypeError`, and the control happened to be the arm
running when it did.

**Fix.** One line on C's side; the signature stays required, for the reason in the entry
above. The control survived on the re-run, which is the confirmation.

**The lesson is about the instrument, and it is the second one today.** A mutation sweep
assumes the subject is otherwise still. In a shared checkout with three agents it is
not, and a *false kill* is the dangerous direction — a false survivor sends you to write
a test, a false kill sends you nowhere at all. **The equivalent-mutant control is what
caught this**, and it caught it only because a control that dies is unmistakable where a
twelfth kill in a row is not. That is the whole argument for carrying one, arriving as
evidence rather than as a principle. Combined with the `.pyc` defect from the engine 22
sweep, the rule I would write is: a sweep whose control dies is a sweep to throw away,
and a sweep with no control cannot tell you it should have been thrown away.

### Two more intermittent interpreter faults, recorded and not diagnosed

**Agent:** B (session 3) · **Date:** 2026-09-16

Two runs in my lane died in ways my code cannot explain and neither reproduced: a
`SystemError` inside `yaml/scanner.py` during collection, and a subprocess exiting
`3221225477` — `0xC0000005`, a Windows access violation — inside
`test_core_can_use_both_writes_importing_only_the_client`, which spawns a child
interpreter. Both passed on an immediate re-run of the same command, and the full lane
has since run green twice end to end.

`unexplained` is an acceptable thing to write (HANDOFF 1, rule 5), and writing it is
better than the alternative, which is a plausible story. Recorded because three agents
share this checkout and are spawning interpreters concurrently, so if anyone else sees
an access violation it is worth knowing it has happened here too rather than each of us
concluding independently that our own change caused it.

### Three CRLF files normalised, and what the conversion would have cost

**Agent:** B (session 3) · **Date:** 2026-09-16

`src/acsoe/clients/store/contracts.py` (489 lines, entirely CRLF),
`src/acsoe/engines/execution/engine.py` (478, entirely) and this build log (127 of
1,204), all against pure-LF blobs. Byte-replaced, `\r\n` to `\n`, and nothing else
touched.

It is invisible by construction: `.gitattributes` carries `* text=auto eol=lf`, so the
clean filter normalises into the index and `git status` and `git diff --numstat` both
say nothing. The cost is not cosmetic — **a text-mode round trip disarms every
literal-anchor patcher in the repository at once**, because an anchor written with `\n`
matches nothing in a file whose every line ends `\r\n`. My own harness hit exactly that
on `contracts.py` during the migration 0003 sweep, reported `ANCHOR MATCHED 0x` and
refused, which is the only reason it was a nuisance rather than a silent non-result
counted as a clean sweep. Found across the team by C-models after it cost four mutation
arms.

### Spec 94 — the registry chain reaches engine 15, on a book that can witness engine 9

**Agent:** B (session 4) · **Task:** spec 94 · **Date:** 2026-09-16

**What happened.** `tests/engines/test_feature_chain_rehearsal.py` now drives the chain the
registry will run — 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15 — through two real ticks (bar, then
quiet), every engine real, the artefacts trained in the module, B's real store, and the fake
client at **fee tier 3** by name (`TIER_3`, `fee_tier_profile(3)`: maker `0.0011`, taker
`0.0019`). Engine 7 picks `BTC/USD` on the BUY window, and that is asserted on every run.

**The book.** A probe of the chain on the fake's default book, before any test was written:
`order_book` published `estimated_slippage_pct: '0'`, `levels_consumed: 1`, `fill_price
'50000.0'` — the default top bid holds 0.75 BTC, about 37,500 USD, against the 5,000 USD
basis. That is the zero my session-3 entry measured, and the operator's instruction applies:
"Spec 94 uses the thin book." The rehearsal loads the **recorded `BTC/USD` opening snapshot**
from the committed `tests/fixtures/book_sample.jsonl` — the candidate's own pair, a real
ten-level book, no delta replay (a Kraken v2 `snapshot` frame is absolute on its own, so
nothing of C's `_replay_book` is duplicated), numbers parsed with `parse_float=Decimal`. It
is loaded into the stream double **before** the stream quote is read off it, so engine 3's
spread and engine 9's walk describe one market.

Measured on the bar tick:

| Figure | Value |
|---|---|
| best bid / ask | `75731.8` / `75731.9` |
| basis notional | `5000.00` (engine 1's USD) |
| levels consumed | **4** (`52.65` + `3.86` + `3.86` USD, then the remainder at `75726.8`) |
| fill price | `75726.85619614271459554707421` |
| `estimated_slippage_pct` | **`0.00006528042192692375531712952815`** — strictly positive |
| engine 3 `spread_pct` | `0.000001320448397866947658085732753` |
| engine 10 `friction_pct` | `0.003066600870324790702975215261` |
| recomputed maker + taker + spread + slippage | equal, exactly |
| recomputed **without** slippage | `0.003001320448397866947658085733` — **differs** |
| `hurdle_pct` / `expected_move_pct` | `0.004599901305487186054462822892` / `0.029999999932724522` — clears |

The test asserts in that order: the estimate is `> 0` first; it equals an independent walk
of the loaded bids (written from the README, not by calling `walk_the_bid_side`, same
operations in the same order so the 28-digit context rounds alike); friction equals the
four published parts summed in invariant 5's order — fees from the named profile, spread
from engine 3, slippage from engine 9 — and **differs** from the three-part sum; net edge and
hurdle follow from it. Engine 10's total is never read back against itself.

**Scenarios, all green on C's code as committed at `a668df3`:**

1. `test_the_full_registry_chain_reaches_engine_15_on_the_bar_tick_and_not_the_quiet_one` —
   tier 3 asserted from engine 1's payload; all eleven keys present on the bar tick, no
   blocker, `cost.clears_hurdle`, `risk.approved`, engine 15's **returned** statuses
   `[OK]`; on the quiet tick `feature == {}`, **no `trading_blocked_by`**, none of the ten
   downstream keys, and engine 15 called exactly once across both ticks.
2. `test_engine_10_prices_the_nonzero_slippage_engine_9_walked_on_the_recorded_book` — the
   table above.
3. `test_engine_14_weights_the_leaderboard_in_the_real_store_on_the_bar_tick` — the
   committed `leaderboard_sample.json` written through `write_leaderboard_entry` into a
   freshly migrated store; weights recomputed from the rows (aaaa `0.818…`, bbbb `0.181…`,
   cccc `0.0`), the other family absent, provenance matched to engines 8 and 12, absent on
   the quiet tick.
4. `test_nothing_engine_14_publishes_changes_whether_engine_15_blocks[pass|veto]` — invariant
   4. `p_wrong` recomputed from the artefact (`8.98e-06` on this bar), threshold a millionth
   either side; the bar judged with the leaderboard loaded (weights sum to 1) and with an
   empty store (`leaderboard_empty`), the two router payloads asserted **different**, and
   engine 15's status asserted to be **the one the threshold dictates** in both runs as well
   as identical across them. Equality alone would call a router output that engine 15 read
   on both runs sound, because it would move both answers alike.
5. `test_without_engine_9_before_it_engine_10_blocks_and_names_the_missing_estimate` — the
   Phase 5 test `test_engine_10_stops_the_chain_for_want_of_engine_9_and_says_so`, renamed
   for what it now is: the fail-closed half of the seam, with engine 9 explicitly removed.
   `judgement_chain()` now carries engine 9 in its registry position, and the three tests
   that assert "nothing after the block ran" now also assert `order_book` did not.

One database per run (`fresh_store`), because scenario 4 compares a loaded store with an
empty one and a leaderboard row cannot be taken back out through the store's surface.

**Deleted, per spec 94 step 5:** `test_in_the_full_registry_chain_engine_15_is_never_reached_
this_phase`, which asserted `skeptic` never appears in the registry chain because engine 10
blocked for want of engine 9. It was true of a chain that no longer exists: engine 9 has
landed, and scenario 1 asserts the opposite. A comment stands where it was, naming it.

**A wrong turn, mine.** My first version of scenario 5 asserted the block reason names
`order_book.estimated_slippage_pct`. It does not, and engine 10 is right: with engine 9
absent there is no `order_book` payload at all, and `_require` reports `missing order_book
is NoneType, expected a mapping`. The key-level sentence is what a payload carrying the
estimate under another name produces — mutation M1 below — which is a different case. The
assertion now names what engine 10 actually says for this one.

**Found and not touched: `src/acsoe/engines/cost/engine.py` is 328 CRLF / 0 LF in the
working tree** (measured in Python at claim time), against the LF the rest of the engines
carry. It is C's file, the blob is normalised by `.gitattributes`, and I did not convert it.
The sweep's engine-10 anchors contain no line break, so they match either way. Reported to
the lead for C.

**No finding against engines 9, 14, 10 or 15.** Every scenario was green on the first run of
section 6; the only red was my own assertion above.

### Spec 94 — seven mutations of C's engines: five killed by the tests written for them, one control, one equivalent on this path

**Agent:** B (session 4) · **Task:** spec 94 step 6 · **Date:** 2026-09-16

Harness: `scratchpad/b94/sweep94.py`. For each arm, a byte copy of every file it touches;
every anchor counted and required to occur **exactly once** (no anchor contains a line
break, so `cost/engine.py` being CRLF could not disarm one); the mutant written; pytest run
through `sys.executable` (absolute) with `PYTHONDONTWRITEBYTECODE=1` and `-p
no:cacheprovider`; the bytes restored in a `finally` **before the next arm**, with the sha256
compared in the same statement. A verdict with no pytest summary line is reported as NO
RESULT; none was. Sweep run against **my file only**, `tests/engines/
test_feature_chain_rehearsal.py`, narrowly, per the shared-checkout rule — the survivors
are then re-run against the whole suite below. Logs `logs/verify/b94-sweep-*.log`, table
`logs/verify/b94-sweep-M0-M1-M2-M2b-M3-M4-M5-1t.json`.

Pre-sweep baseline of the file: `33 passed`. Hashes before the sweep and after every
restore, identical:

```
src/acsoe/engines/order_book/contracts.py    f55419cbdecc17ff4d279b54fcb3e825b49f292a07c67ca2c45ad6a650a1a08f
src/acsoe/engines/order_book/engine.py       2d53b479b5778266bd8810f9da59d4bdce5fcd13cc9cae3940dbe573f46f89a2
src/acsoe/engines/cost/engine.py             9f8ac3d4b821614de5bc2a035d037c30b87acdb9a2b28f88f2da0472e2299087
src/acsoe/engines/adaptive_router/engine.py  f7e1ea62f53107d6fae344e50f44ef2b5d11253087e03ac4e8c335af9c5ff459
src/acsoe/engines/skeptic/engine.py          44525d29f4eb09ceadca79aec2497c67e1bb65d64d1e4a5b24397b138a54ef8b
tests/engines/test_feature_chain_rehearsal.py 57c4f9ea90d4224066b5bd0801d030648619b2c28aab36781dd8b72ee2e9ab95  (not a variable; unchanged)
```

| Arm | Mutation | Verdict (file) | Killing test — the one written for it | Incidental kills |
|---|---|---|---|---|
| M0 | engine 10 `clears = net_edge > hurdle` → `not net_edge <= hurdle` — **equivalent control** | survived, `33 passed` | — | — |
| M1 | engine 9 `ESTIMATED_SLIPPAGE_FIELD` → `"estimated_slippage"` (spec 94 step 6) | killed, `5 failed, 28 passed` | `…reaches_engine_15_on_the_bar_tick…` (`('cost', '… missing order_book.estimated_slippage_pct')`) and `…prices_the_nonzero_slippage…` (key absent) | engine 14 and invariant 4 tests: engine 14 never runs once 10 blocks |
| M2 | engine 14 publishes `skeptic_weight: 1.0`; engine 15 adds it to its threshold (spec 94 step 6) | killed, `2 failed, 31 passed` | `test_nothing_engine_14_publishes_changes_whether_engine_15_blocks[pass]` and `[veto]` | none |
| M2b | engine 15 adds the sum of engine 14's `weights` to its threshold | killed, `2 failed, 31 passed` | the same two | none |
| M3 | engine 10 drops `+ inputs.slippage_pct` from friction — **the arm the thin book exists for** | killed, `1 failed, 32 passed` | `test_engine_10_prices_the_nonzero_slippage_engine_9_walked_on_the_recorded_book` — `Decimal('0.003001320448397866947658085733') == … + Decimal('0.00006528042192692375531712952815')` | none |
| M4 | engine 9 publishes `walk.slippage_pct * 0` | killed, `1 failed, 32 passed` | the same test, at its first assertion: `engine 9 estimated 0E-32` | none |
| M5 | engine 14's own model-family filter → `if False:` | survived, `33 passed` | — | — |

**M2 is the arm that justifies the shape of the invariant 4 test, and the log shows it.** In
M2 engine 14 publishes the weight whether or not the leaderboard holds rows, so the two runs
the test compares are **identical to each other** — `with_weights["skeptic"] ==
without["skeptic"]` holds. The kill came from the absolute assertion, on the run *without*
weights: status `[OK]` where the recomputed threshold dictates `[BLOCK]`, and on the pass
side a published threshold of `1.0000099805859788` against the configured
`9.980585978810067e-06`. A test that asserted only that the two runs agree would have
passed M2. That is why the docstring says equality alone would call it sound.

**M3 is killed only by the recomputation test, and M4 only by its first line.** Scenario 1
stays green under both, because friction still clears the hurdle with or without 0.0065%.
That is the operator's point measured from the other side: every test that does not
recompute is blind to engine 10 ignoring engine 9.

**M3 on the default book would have been an equivalent mutant.** Not run as an arm — the
arithmetic settles it: engine 9 publishes `'0'` there, and `x + 0 == x` for these
`Decimal`s, so the recomputation assertion holds with or without the term.

**M5 is expected to survive this file and is not a finding against engine 14.** B's
`all_leaderboard_rows(model_id=...)` filters by family in SQL, so on the enumerating path
engine 14's own filter is redundant — C recorded exactly this in `code-standards.md` ("a
double that was faithful when written…"). In this chain the filter can never be reached
with a foreign row. Scenario 3's assertion that the other family is absent therefore
proves the *read* is scoped, not that engine 14 filters. Re-run against the whole suite
below, where C's windowed-fallback tests are the ones that can see it.

**The two file-survivors, re-run against the whole of `tests/`** (`logs/verify/b94-sweep-M5-
M0-1t.json`; each wide run's failing set compared with the known red, which is the eight
parametrisations of `test_pending_on_the_real_tree_names_the_subject_and_the_spec`, C's
spec 100):

- **M5 — killed**, `9 failed, 3170 passed, 2 skipped, 1 xfailed` in 1246.60s. The one failure
  beyond the known eight is C's `tests/engines/test_adaptive_router.py::
  test_a_second_model_family_is_not_weighted`. So the filter is covered, by the owner's test
  on the path that can reach it, and on the registry path it is an equivalent mutant because
  the store scopes the read. A checked negative for this file, not a hole.
- **M0 — behaviourally survived, and "killed" by an anchor collision I caused.** `10 failed,
  3169 passed, 2 skipped, 1 xfailed` in 887.99s: the known eight plus
  `tests/verify/test_phase3_criteria.py::test_a_cost_gate_that_never_blocks_is_a_fail` and
  `…blocks_everything_is_a_fail`, both with `acsoe.engines.cost.engine: anchor appears 0
  times, expected exactly once`. Those two tests patch engine 10 **by the literal text
  `clears = net_edge > hurdle`** — the same line I chose for the control. Rewriting it to an
  equivalent form did not change what engine 10 does; it removed the text another test's
  patcher anchors on, and that patcher refused loudly, as it is built to. No test failed on
  behaviour.

  **The lesson, which I have not seen written down here:** an equivalent-mutant control is
  equivalent *to the behaviour*, and this repository also has tests that read *the text*.
  A control placed on a line a `tests/verify/` patcher anchors on reads as a kill in any
  wide run. Pick a control's line by grepping `tests/` for its text first. It cost nothing
  this time because the refusal names itself; a patcher that silently no-op'd on a missing
  anchor would have turned the same collision into a quiet false PASS, which is why they
  refuse.

### Spec 94 — the gate at the spec 94 boundary

**Agent:** B (session 4) · **Date:** 2026-09-16

Tree: `a668df3` plus my three files (`tests/engines/test_feature_chain_rehearsal.py`, this
log, my progress file), nothing else modified, no sweep running. Four commands, each to its
own file, files read rather than piped:

| Command | Result | Log |
|---|---|---|
| `pytest tests/ -q` | `8 failed, 3171 passed, 2 skipped, 1 xfailed, 3 warnings in 869.99s` — the eight are exactly the known parametrisations of `test_pending_on_the_real_tree_names_the_subject_and_the_spec` (C, spec 100); no other failure | `logs/verify/b94-gate-pytest.log` |
| `mypy --strict src/ scripts/` | `Success: no issues found in 153 source files` | `logs/verify/b94-gate-mypy.log` |
| `ruff check src/ tests/ scripts/` | `All checks passed!` | `logs/verify/b94-gate-ruff.log` |
| `verify.py --phase 6` | `11 criteria: 1 PASS, 1 FAIL, 9 PENDING` — the FAIL is `toolchain_green` on the same eight | `logs/verify/b94-gate-verify.log` |

**One crash inside `toolchain_green`, attributed to the registered native fault.** Its first
pytest attempt died `3221225477 (0xC0000005 ACCESS_VIOLATION)`; the retry completed with the
same eight. The faulting stack (`logs/verify/toolchain_green/20260916T163220_659731-pytest-
attempt1.log`) is `clients/store/client.py` `_to_sql` → `_insert` → `write_equity_snapshot`,
called from `seed.py` under `tests/conftest.py`'s `seed_fixtures` — an access violation in
`sqlite3`, which is on the known fault's list, in a path spec 94 does not touch, and it did
not recur on the retry or in my own full run minutes earlier. Checked against the other
known mechanism, a stale `.pyc`: no sweep was running and nothing was mutated during the
gate. Not filed as unexplained.

### Correction: `engines/cost/` is B's, not C's

**Agent:** B (session 4) · **Date:** 2026-09-16

The spec 94 entries above call `src/acsoe/engines/cost/engine.py` "C's file". It is mine —
`ownership.md` gives engine 10 to B — and the lead corrected it. The facts stand (328 CRLF /
0 LF in the working tree, not normalised during the sweeps); the attribution was wrong. It
is mine to convert to LF at a quiet moment after spec 103, **after** checking that no
`tests/verify/` patcher anchor on that file spans a line break, since a conversion changes
what such an anchor matches.

### Spec 103, diagnosis — the ledger learns of a fill one tick after the broker executes it

**Agent:** B (session 4) · **Task:** spec 103 · **Date:** 2026-09-16

The diagnosis is A's (`a-platform.md`, "every paper fill inflates `peak_equity`"); this is
where in my broker the two readings disagree about *when*, written before any change.

**What happened.** On the tick a resting entry fills, `PaperBroker.balance()` reports the
pre-fill cash while engine 21 counts the new position, so engine 19 writes equity with the
notional counted twice (`8332.41` against a true `4996.99` in A's rehearsal), `peak_equity`
keeps it, and engine 17 freezes the account on the next tick and every tick after.

**Why, in `src/acsoe/clients/paper/broker.py`.** The broker has one place that *decides* a
fill and a different place that *counts* one, and they are reached at different moments of
the tick:

- **The decision** is `_resolve_resting`, reached only through `_state_of`, which only
  `query_orders`, `open_orders` and `cancel_order` call — that is, only when engine 21 (or
  22) asks, in the manage chain, near the end of the tick. The decision is not kept: it is
  recomputed from the live trade window on every call and lives nowhere once returned.
- **The count** is `balance()`, which reads `self._store.filled_orders()` and nothing else —
  fills **engine 19 has recorded**. Engine 1 calls it at the top of the tick, in the guard
  chain, before any engine has asked about the order. On the fill tick the store still says
  `resting`, so the fill is absent; it appears one tick later, after engine 19 has written
  the `filled` row.

So the balance lags the broker's own knowledge by exactly one tick, and the lag is
structural: the only reader that triggers the decision runs after the only reader that
counts. The same holds for a market sell from engine 22, which is held in `_pending` as
`FILLED` and never counted by `balance()` until recorded — harmless today only because
nothing reads the balance again in that tick.

**Two further properties the fix has to have, both from the spec.**

1. *Whichever read comes first, both see one fill.* The decision is currently a function of
   the live trade window at the moment of the call. In the daemon the window is the
   websocket's, filled on another thread (`ws.py` takes a lock), so a trade can arrive
   between engine 1's read and engine 21's. A balance that decided "not filled" and a query
   that then decided "filled" would reproduce the defect in a narrower window. So the
   decision has to be taken once and remembered, and the not-filled answer has to be pinned
   for the tick as well as the filled one.
2. *Never twice once recorded.* Once engine 19 writes the `filled` row, the store is the
   record and the broker's own memory of the fill must stop counting.

**Restart.** The broker holds no fill memory across a process, and the stream is
per-process, so a fill executed and never recorded is absent from the rebuilt ledger; the
store still holds the order as `resting` and no position row, so the rebuilt positions agree.
That is the claim the spec requires a test for rather than an assumption.

### Spec 103, fix — `balance()` decides the tick's fills, and counts every one it executed

**Agent:** B (session 4) · **Task:** spec 103 · **Date:** 2026-09-16

**Fix**, in `src/acsoe/clients/paper/broker.py` only (no engine touched):

1. **`balance()` is where fills are decided.** It pins the tick's view of the trade window
   (`_window`, a copy of `recent_trades()`), then calls `open_orders()`, which resolves every
   store-resting and not-yet-recorded order through the one existing resolution path, then
   counts. Engine 1 is the first engine of every tick, so in the daemon every fill due this
   tick is decided before anything reads the account.
2. **A fill, once decided, is kept** in `_executed` (`pair`, `is_entry`, `OrderState`) — by
   `_resolve_resting` for a resting entry and by `_fill_market` for engine 22's sweep — and
   `_resolve_resting` returns the kept state on every later read. One fill, one price, one
   fee, one `closed_at`, whichever read decided it; and a window that rolls past the trade
   cannot un-fill it.
3. **Every later read resolves against the pinned window**, so a trade the websocket thread
   delivers between engine 1 and engine 21 is decided on the next tick rather than by
   engine 21 alone. Before a process's first balance there is no pin and reads use the live
   window, which keeps every test and caller that never reads a balance on the old path.
4. **Counted once.** The store's `filled` rows are counted as before; each `_executed` entry
   is counted unless its `userref` is among them, in which case it is dropped — engine 19's
   row is the record from then on.
5. **Restart:** `_executed` and `_window` are per-process, like the stream. Proven by
   `test_a_fill_the_process_died_before_recording_is_absent_from_the_rebuilt_ledger_and_positions`,
   which runs the real engine 1 and engine 21 on the restarted broker over the same store
   and a fresh stream: `USD 5000.00`, `positions == []`, no fill recorded, the entry still
   resting, `entry_orders_cancelled` false.

**Decision: a due fill that cannot be priced makes the balance a failed fetch.** Step 1
gives `balance()` a dependency it never had — the maker rate, fetched when a fill is
priced. My first run of the neighbouring suites found it:
`test_position_manager.py::test_the_flag_is_false_while_an_entry_the_client_will_not_report_on_still_rests`
fails `TradeVolume` while a trade has printed through a resting entry, and engine 1 now
**raised**: the broker's `PaperBrokerError` is not a `KrakenError`, and engine 1 re-raises
anything that is not (contract rule 7), which would empty its whole payload — `pair_rules`
and all — for the length of the outage. Two options:

- *Let it raise.* Fail-closed, but engine 1 goes `ERROR` every tick of a fee outage while a
  fill is due, and every consumer of `pair_rules` loses it for a reason unrelated to pairs.
- *Report it as what it is* — the exchange call that prices the fill did not answer, so the
  balance is unknown. Chosen: `balance()` re-raises that one case, and **only** a
  `PaperBrokerError` whose `__cause__` is a `KrakenError`, as `KrakenUnavailableError`.
  Engine 1 then records `balance` and `trade_volume` as failed calls and keeps `pair_rules`.
  Anything else the broker refuses while deciding is re-raised unchanged, because laundering
  a defect into "the exchange was unavailable" sends the operator to wait rather than fix.

Consequences, checked rather than assumed: engine 19 writes no equity row on a tick with no
balances (it says why), and engine 9 publishes no estimate while engine 10 blocks on the
missing fee tier, so **engine 11's paper-mode balance fallback is not reachable through this
path** — the only way to reach it is the fee outage, which blocks the tick at engine 10 first.
Engine 11's fallback itself (`paper.starting_balances` when engine 1 publishes none) now sits
awkwardly beside the ruling that the paper balance *is* the ledger; it is my engine and out of
this spec's scope, so it is reported to the lead rather than changed. The existing engine 21
test passes unchanged under the chosen option.

**A wrong turn, mine.** My first "defect is raised as itself" test planted a row recorded as
`pending` and got `DID NOT RAISE`: `open_orders` reads only `resting` rows, so `balance()`
never reaches a `pending` one. The broker was right and the test was aimed at a path
`balance()` does not take. It now plants a resting row with no limit price, which
`_resolve_resting` refuses with no exchange failure behind it.

**A's strict xfail.** `test_a_filled_position_is_watched_across_quiet_ticks` now reports
`XPASS(strict)` and fails, as spec 103 said it would (`logs/verify/b103-A-xfail-default.log`,
`1 failed`); run with `--runxfail` it passes (`logs/verify/b103-A-runxfail.log`,
`1 passed in 22.81s`). A's file is not touched; removing the marker is A's.

### Spec 103 — twelve mutations of the broker: ten killed by the tests written for them, a control, and one checked negative

**Agent:** B (session 4) · **Task:** spec 103 step 4 · **Date:** 2026-09-16

Harness: `scratchpad/b94/sweep103.py` on spec 94's machinery (byte copy, every anchor
exactly once, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, `sys.executable`, restore
in a `finally` before the next arm with the sha256 compared in the same statement, no verdict
without a summary line). `broker.py` is pure LF (0 CRLF, counted in Python before the sweep)
and no `tests/verify/` or `scripts/verify.py` patcher anchors on its text — checked with a
grep first, the spec 94 control lesson. Hash before and after every arm:
`98c0df710256e4fb65c0e9dc6bf58acca6547eb2e38c7a088be01e28c70e6201`. Narrow target:
`tests/clients/paper/` (baseline `77 passed`). Logs `logs/verify/b103-sweep-*`.

| Arm | Mutation | Verdict | Killing test — written for it | Notes |
|---|---|---|---|---|
| N0 | `list(self._executed.items())` → `tuple(...)` — **control** | survived, `77 passed` | — | wide re-run below |
| N1 | `balance()` counts no executed fill (the defect restored) | killed, `8 failed` | `test_the_balance_on_the_fill_tick_counts_the_spend_before_the_store_records_it` | the other seven depend on the spend being counted |
| N2 | a recorded fill's kept copy counted too (`if userref in recorded:` → `if False:`) | killed, `2 failed` | `test_a_fill_recorded_by_engine_19_is_not_counted_twice` | also the market-sell test, which records and re-reads |
| N3 | `balance()` decides nothing (`await self.open_orders()` → `pass`) | killed, `7 failed` | `…counts_the_spend_before_the_store_records_it`; `…whichever_is_asked_first[balance]` — `[query]` stays green, which is the point of parametrising the order | the outage and defect-passthrough tests also die: nothing is decided, so nothing refuses |
| N4 | a kept fill ignored on the next read | killed, `1 failed` | `test_an_executed_fill_is_not_undone_when_its_trade_leaves_the_window` | none |
| N5 | reads use the live window, never the pinned one | killed, `1 failed` | `test_a_trade_that_arrives_after_the_balance_waits_for_the_next_tick` | none |
| N6 | engine 22's market fill not kept | killed, `1 failed` | `test_a_market_sell_is_counted_before_it_is_recorded` | none |
| N7 | a resting fill not kept | killed, `7 failed` | `…counts_the_spend_before_the_store_records_it` and both `…whichever_is_asked_first` | the rest depend on it |
| N8 | kept fills survive a restart (a module-level dict) | killed, `25 failed` | `test_a_fill_the_process_died_before_recording_is_absent_from_the_rebuilt_ledger_and_positions` | **mostly incidental**: one dict shared across every broker in the process contaminates unrelated tests. The deliberate kill is the restart test's `USD == 5000.00` |
| N9 | the fee-outage refusal not mapped to a failed fetch | killed, `1 failed` | `test_a_due_fill_with_no_fee_tier_makes_the_balance_a_failed_fetch_not_an_error` | none |
| N10 | every refusal mapped, defects included | killed, `1 failed` | `test_a_broker_defect_met_while_deciding_fills_is_raised_as_itself` | none |
| N11 | a recorded fill's kept copy not dropped (`del` removed, `continue` kept) | survived, `77 passed` | — | **checked negative**: see below |

**N11 is equivalent, and says what the `del` is for.** The count is protected by the
`continue`, not by the `del`: a kept copy of a recorded fill is reached only through
`balance()`'s loop, which skips it, or through `_resolve_resting`, which is reached only for
a `resting` row — and a recorded fill's row is `filled`. So the `del` is memory hygiene for
a long-running daemon and nothing observable depends on it. Recorded as a checked negative
beside N2, which is the non-equivalent form of the same claim.

**The defect itself, restored by breaking the broker, through A's rehearsal.** Arms N0, N1,
N3 and N7 run against `tests/engines/test_trade_chain_rehearsal.py::
test_a_filled_position_is_watched_across_quiet_ticks` with `--runxfail`, so the strict marker
does not turn the answer into its opposite (logs `b103-sweep-N*-2t-rsal.py_test_a_filled_…`):

| Arm | Result |
|---|---|
| N0 control | `1 passed` |
| N1, N3, N7 | `1 failed` each, every one at A's own assertion: `the fill tick's equity counts the entry's notional twice` — `Decimal('8332.414226591') == Decimal('1663.9201177597499') + Decimal('26.26015939') * Decimal('126.9')` |

`8332.414226591` is the exact figure A's finding recorded. That is spec 103's "proven capable
of failing by breaking the broker so the fill is excluded", measured through the chain rather
than through my own tests; the criterion that makes it permanent is C's, spec 105.

**The two survivors, against the whole of `tests/`.** The expected failing set at this
point is the known eight `test_pending_on_the_real_tree…` parametrisations **plus A's
`test_a_filled_position_is_watched_across_quiet_ticks` as `XPASS(strict)`**, which spec 103
predicts. Against that:

- **N11 — behaviourally survived**, `9 failed, 3182 passed, 2 skipped` in 693.08s, exactly
  the expected nine (`logs/verify/b103-sweep-wide-stdout3.log`). A checked negative.
- **N0 — behaviourally survived**, `9 failed, 3181 passed, 2 skipped, 1 error` in 733.68s: the
  expected nine, and one setup **error** in `tests/engines/test_exit.py::
  test_the_request_that_reaches_the_client_is_a_market_sell_and_not_only_the_row` —
  `TypeError: 'dict_keyiterator' object does not support the context manager protocol`
  raised inside `yaml/scanner.py:153`. No correct interpreter raises that from that line; it
  is the corrupted-interpreter shape of the registered native fault (the same family as the
  `SystemError` in `yaml/scanner.py` I recorded earlier this phase), in a test that neither
  N0 nor the broker reaches at setup.

**Getting those two answers took five wide runs, and three of them crashed.** Recorded
because they are evidence about the machine today, not about the broker, and because
the harness's "NO RESULT" rule is the only reason none of them was read as a verdict:

| Run | Outcome | Where |
|---|---|---|
| N11, attempt 1 | `Windows fatal exception: access violation` during collection, in `scipy/_lib/_array_api.py` under a scipy import | `logs/verify/b103-crashed/N11-attempt1.log` |
| N0, attempt 1 | access violation at 47%, in pure-Python `yaml/scanner.py` `stale_possible_simple_keys` | `logs/verify/b103-crashed/N0-attempt1.log` |
| N11, attempt 2 | died silently at 36% after ~50 s, no fault-handler output | `logs/verify/b103-crashed/N11-attempt2.log` |
| N0, attempt 2 | completed, with the one yaml `TypeError` above | `b103-sweep-N0-control-1t-tests_.log` |
| N11, attempt 3 | completed, clean | `b103-sweep-N11-recorded-copy-not-dropped-1t-tests_.log` |

Checked against the known mechanisms: nothing else was running (process list taken while N0's
second attempt ran, a minute after N11's silent death: only the recorder and supervisor
processes and my own sweep), 68 of 100 GB free,
`PYTHONDONTWRITEBYTECODE=1` on every run so no stale `.pyc`, and every crash site is in a
third-party module (scipy, PyYAML) rather than in the broker the arms change by one token. Attributed to the
registered native fault, not filed as unexplained. The harness did not record the exit
code, which is why attempt 2's silent death has no number beside it; it records it now.

### Spec 103 — the gate at the spec 103 boundary

**Agent:** B (session 4) · **Date:** 2026-09-16

Tree: `49e369a` plus `src/acsoe/clients/paper/{broker.py,README.md}`,
`tests/clients/paper/test_ledger_counts_executed_fills.py` (new), this log and my progress
file. No sweep running. Expected red: the eight `test_pending_on_the_real_tree…` (C, spec
100) and A's `test_a_filled_position_is_watched_across_quiet_ticks` as `XPASS(strict)`,
which spec 103 predicts.

| Command | Result | Log |
|---|---|---|
| `mypy --strict src/ scripts/` | `Success: no issues found in 153 source files` | `logs/verify/b103-gate-mypy.log` |
| `ruff check src/ tests/ scripts/` | `All checks passed!` | `logs/verify/b103-gate-ruff.log` |
| `pytest tests/ -q` | `10 failed, 3181 passed, 2 skipped in 842.98s` — the expected nine **plus one**, below | `logs/verify/b103-gate-pytest.log` |
| `verify.py --phase 6` | `11 criteria: 1 PASS, 1 FAIL, 9 PENDING`; `toolchain_green`'s own pytest run: `9 failed, 3182 passed, 2 skipped in 835.20s` — **exactly the expected nine** | `logs/verify/b103-gate-verify.log`, `logs/verify/toolchain_green/20260916T174507_035378-pytest-attempt1.log` |

**The one extra failure, attributed to the registered native fault.**
`tests/verify/test_phase1_criteria.py::test_pass_against_a_fabricated_console[console_live_frame_amber]`:
`criterion raised - TypeError: object of type 'MappingEndEvent' has no len()`, from inside
PyYAML. Pure-Python PyYAML does not ask for the length of an event object on a correct
interpreter; this is the third PyYAML-shaped corruption on this machine today (the
`SystemError` earlier this phase, the `dict_keyiterator` `TypeError` in the N0 wide run).
It names neither the broker nor any file of mine, the console criterion never constructs a
broker, and **the same test passed in `toolchain_green`'s pytest run over the same tree in
the same fifteen minutes.** One thing I did that I would not repeat: I ran my gate pytest and
`verify.py` (which runs its own pytest) **concurrently**, so two full suites shared the
machine. Nothing is written to the tree by either, so it cannot have changed an answer, but
it doubles the load on a machine that is faulting natively today.

### Spec 106, diagnosis — engine 11's paper fallback would approve a trade against cash already spent

**Agent:** B (session 5) · **Task:** spec 106 · **Date:** 2026-09-16

Written before any change, per the script rules. The finding is the operator's and the lead's
(tracker, "The operator's three rulings on the rehearsal round", ruling 3); this entry records
what the branch in my engine would have done if reached, read from the code.

**What happened.** `RiskEngine._balances` (`src/acsoe/engines/risk/engine.py`) had three cases:
the published `exchange.balances` map if present; otherwise, **in paper mode only**, the raw
`paper.starting_balances` config map, recorded as `balance_from_paper_starting_balances`;
otherwise a block. `_read_inputs` takes `quote_balance` from whichever map came back, and the
invariant 6 affordability check is `if target_notional > inputs.quote_balance` — so in the
paper branch the check compares against the **opening** balance, unadjusted by anything.

The lead's worked example, followed through the code:

| Step | Figure |
|---|---|
| Paper account opens | `paper.starting_balances` USD 5,000.00 |
| First entry fills (another pair) | ~3,332 spent, cash ~1,664 held |
| Engine 19's equity (cash + position) | ~4,996 |
| Second candidate, sized from equity: `4,996 × 1% / 1.5%` | `target_notional` ~3,331 |
| Engine 1 publishes no balance this tick | paper branch returns `{USD: 5000.00}` |
| `3,331 > 5,000`? | **no** — affordability passes |

With `ordermin`/`costmin` cleared, a different pair (so `position_open_on_pair` is silent) and
one position against a cap of three, the engine **approves** a ~3,331 position against ~1,664
held. Invariant 6: *never allocate cash the account does not hold in that pair's quote
currency.* The gate built to refuse exactly that would have said yes.

**Why the branch existed and why it was wrong by Phase 6.** Its own docstring said the map is
used "exactly as configured" and deferred "adjusted by simulated fills" to "the fill
simulator's contribution and that is Phase 6". Phase 6 did not adjust this map; it put the
ledger in the broker (spec 88, then spec 103), so engine 1's published balance *is* the
adjusted figure and the config map is only its opening value. What was left in engine 11 was a
second answer to "what does the account hold", and on any tick after a fill the wrong one.

**Why "unreachable" was the wrong reassurance, including from me.** Engine 1 publishes no
balance in paper only when the broker's `balance()` raises, which since spec 103 is the fee
outage with a fill due. On that tick engine 7 excludes every pair and engine 10 has no fee
tier, so the chain stops before engine 11. My own spec 103 entry says exactly that — "engine
11's paper-mode balance fallback is not reachable through this path" — and reported the
branch as "sitting awkwardly" rather than asking what it would *do*. Unreachability is a
property of the callers; correctness is a property of the branch. Leaning on engines 7 and 10
made their handling of an absent balance load-bearing for invariant 6, which neither owns, so
an unrelated change to either would have armed the branch with nothing going red.

**Why no test objected.** `test_paper_mode_falls_back_to_the_configured_starting_balances_and_records_it`
failed the balance on an account that had **never traded**, where the configured 5,000 and the
fetched 5,000 agree — its docstring even says "the sizing is unchanged and the only observable
difference is the recorded fallback". The fixture was the one account on which the defect
cannot show. The `code-standards.md` rule, "a double must be capable of exhibiting the
property under test", in a fixture rather than a double.

**A second thing the read found: the recorded fallback went nowhere.** The README called the
fallback "never silent" because `fallbacks_used` named it on the decision. But `rejections`
has no `fallbacks_used` column (migration 0001 puts one on `trades` only), `RejectionRow`
has no such field, and engine 19's `_write_rejection` never reads it; engine 16 and the
console do not read it either. The contracts comment "written into `rejections.fallbacks_used`
by engine 19" described a column that does not exist. With the branch gone the field has no
producer and no reader, so it goes too (decision below, in the fix entry).

**Engine 21, folded in (C's observation from spec 105).** `_fill` builds a new position's row
without `last_price` or `unrealised_pnl`, and `_mark` adds `qty × entry_price` to the
portfolio value for that row without writing the mark onto it. So engine 19 stores the fill
tick's position with both columns NULL while `_mark`'s docstring says "`last_price` on a
position that has existed for no time is the fill price" and the equity row values it there.
Checked before changing it, for a reason the docstring might be the wrong half: the bid is
the mark for every *existing* position, but the fill-tick valuation at the price paid is the
documented design, it is what spec 105's continuity criterion is built on (that criterion
accepts a NULL mark only when the equity row valued the position at cost, and otherwise reads
`last_price`), and engine 22 does not read `last_price` at all. No reason found to change the
docstring; the stored row is the half that is wrong.

### Spec 106, fix — engine 11 blocks on an absent balance in every mode; engine 21 stores the fill-tick mark

**Agent:** B (session 5) · **Task:** spec 106 · **Date:** 2026-09-16

**Fix, engine 11.** `RiskEngine._balances(exchange)` returns the published map or raises
`MissingInputError("exchange.balances: engine 1 published no balance this tick, and no mode
substitutes one (invariant 2)")`. The paper branch is gone, and with it
`PAPER_STARTING_BALANCES_KEY` and `PAPER_MODE` (nothing else in the engine read them; the
broker has its own copy of the key name). `_read_inputs` and `_reject` no longer thread a
fallbacks tuple. The README's "balance fallback" section is replaced by the rule, the worked
example, and why "unreachable" was not enough. The four `tests/verify/` patcher anchors on
this engine's text (`if qty < inputs.ordermin:`, `approved=False,⏎ordermin=inputs.ordermin,`,
`inputs,⏎REASON_BELOW_ORDERMIN,`, and `if self.approved:⏎for field, value in (` in contracts)
are untouched, and `tests/verify/test_phase3_criteria.py -k risk` is green (6 passed).

**Decision: `FALLBACK_BALANCE_FROM_PAPER` and `RiskSizing.fallbacks_used` are removed, not
kept empty.** The spec allowed removal only if engine 19 and the console do not read the
field. Checked in the code: `RejectionRow` has no `fallbacks_used`, the `rejections` table
has no such column (only `trades` does, migration 0001), `MemoryEngine._write_rejection`
reads `reason_code` and the four economics fields and nothing else, engine 16 reads `qty`
and `approved`, the console reads the store, and `scripts/verify.py` never reads it from
this payload (the one `fallbacks_used` in `tests/verify/test_phase3_criteria.py` is inside a
stub engine 10). So it had no producer and no reader. Keeping it always empty would have
published "no fallback fired" on a record that cannot say otherwise. `test_decision.py`
re-validates engine 11's real payload through `RiskSizing` with `extra="forbid"` and is
green, because the payload no longer carries the key either.

**Line endings.** `engines/risk/engine.py`, `contracts.py`, `README.md` and
`tests/engines/test_risk.py` were uniformly CRLF in the working tree and stay CRLF: edited
through a byte-level helper (`scratchpad/b106/crlf_edit.py`) that edits an LF view and
writes the file's own ending back, re-counted after every write (545/0, 300/0, 289/0,
1321/0). Engine 21's files are LF and stay LF. `engines/cost/engine.py` not touched.

**Tests, `tests/engines/test_risk.py`.** Replaced: the paper-fallback test, the live-mode
block (now one parametrisation), "a rejection on a fallback tick still records the
fallback", "an approved sizing records no fallback", and the GBP "the map names no such
currency" test (its subject was the removed config map). Added:

- `test_after_a_paper_fill_a_tick_with_no_published_balance_blocks[the ledger cannot answer |
  the ledger answers]` — **the test that would have caught it.** Engine 19's rows for one
  executed fill are written through the real row models (0.06664 BTC at 50,000.00, fee
  3.6652: cash 1,664.3348, equity 4,996.3348, one open position), a second entry rests on
  ETH/USD with a print through its limit, and the order client is the real `PaperBroker`,
  so engine 1's balance is the ledger. A precondition asserts the witness sits in the
  defect's window: the notional sized from equity (3,330.889…) is above the cash held and
  below `paper.starting_balances`. One input differs: whether `TradeVolume` answers. It
  does → the ledger is 1,664.3348 − 198.4356 = 1,465.8992 and the refusal is
  `insufficient_quote_balance` naming that figure; it does not → engine 1 publishes no
  balance and the refusal is `risk_inputs_unavailable` naming the absence. No `qty` either way.
- `test_a_failed_balance_fetch_blocks_in_every_mode_and_names_the_absence[paper|live|replay]`
  — the whole payload pinned to `{reason_code, approved: False}`.
- `test_the_same_paper_tick_with_its_balance_published_is_sized` — the pass half.
- `test_a_missing_balance_is_refused_before_anything_is_sized` — `ordermin` 500 plus no
  balance must report the absence, not `below_ordermin`.
- `test_an_approval_publishes_no_fallback_field` — the approved key set, pinned.
- The EUR test now asserts the reason names `exchange.balances.EUR` and **not** the absent
  map, so the two `risk_inputs_unavailable` causes are told apart.

**Fix, engine 21.** `_mark`'s loop over this tick's fills now writes `last_price` (the fill
price) and `unrealised_pnl` (`qty × (mark − entry)`, which is zero) onto the row, from the
same `mark` it adds to `positions_value`, and adds the zero to the unrealised total. The
docstring and README say the row now agrees. Test:
`test_a_position_opened_by_this_ticks_fill_is_stored_marked_at_its_fill_price` runs engine 21
and then the real engine 19 over the real store, reads the position back, and asserts
`last_price == 99.00` (the bid is 99.99, so a bid mark fails too), `unrealised_pnl == 0`,
and that the equity row engine 19 wrote values the position at `qty × last_price`.

**What the neighbours said, after the change.** `tests/verify/test_phase6_criteria.py -k
equity`: `5 passed, 35 deselected` (`logs/verify/b106-phase6-equity.log`). A's
`tests/engines/test_trade_chain_rehearsal.py`: `7 passed` (`logs/verify/b106-A-rehearsal.log`).
The criterion itself, run directly: **PASS**, "fee 3.6656556492501 + 26.26015939 x |mark
126.9 - fill 126.9|" (`logs/verify/b106-criterion-105.log`). Scout, decision, feature-chain
rehearsal, exit, execution, reason prose and `tests/clients/paper/`: `466 passed`.

### Spec 106 — nine mutations: seven killed by the tests written for them, two controls

**Agent:** B (session 5) · **Task:** spec 106 step 5 · **Date:** 2026-09-16

Harness: `scratchpad/b106/sweep106.py` on spec 94's machinery (byte copy to scratch, every
anchor exactly once, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, `sys.executable`,
restore in a `finally` before the next arm with the sha256 compared in the same statement, no
verdict without a pytest summary line). `engines/risk/engine.py` is CRLF, so its multi-line
anchors carry `\r\n`; engine 21 is LF. **Controls chosen after grepping `tests/` and
`scripts/verify.py` for their line text** (the spec 94 lesson): `if published is None:`
appears only in verify.py's own code, never as a patcher anchor on engine 11, and
`unrealised += pnl` appears nowhere. Hashes before the sweep and after every restore,
identical: `risk/engine.py` `8383393c…52ce2`, `position_manager/engine.py`
`2010de69…ee4e8` (full values in `logs/verify/b106-sweep-hashes-before.txt`). Narrow targets:
`tests/engines/test_risk.py` (baseline `50 passed`) and `tests/engines/test_position_manager.py`
(baseline `49 passed`). Logs `logs/verify/b106-sweep-*`.

| Arm | Mutation | Verdict (file) | Killing test — written for it | Notes |
|---|---|---|---|---|
| R0 | `if published is None:` → `if None is published:` — **control** | survived, `50 passed` | — | wide: behaviourally survived (below) |
| R1 | the paper fallback restored at the call site (paper mode, absent map → `paper.starting_balances`) | killed, `3 failed` | `test_after_a_paper_fill_a_tick_with_no_published_balance_blocks[the ledger cannot answer]` — `blocks_trading` False, **approved at notional `3330.8898660000`** on the account holding 1,664.3348: the defect, reproduced | also `…in_every_mode…[paper]` and `test_a_missing_balance_is_refused_before_anything_is_sized` (`below_ordermin` where the absence belongs) |
| R1b | the same fallback in every mode | killed, `5 failed` | the after-fill test, and `…in_every_mode…[paper, live, replay]` | the before-sizing test |
| R2 | `_balances` returns `{}` instead of raising | killed, `5 failed` | `…in_every_mode…[paper, live, replay]` and the after-fill test, **at the reason assertion only**: the gate still blocks, but says `missing exchange.balances.USD` — an account holding no USD — for an outage | the before-sizing test |
| P0 | `unrealised += pnl` → `unrealised = unrealised + pnl` — **control** | survived, `49 passed` | — | wide: behaviourally survived (below) |
| P1 | the fill-tick row's `last_price` not written (the defect restored) | killed, `1 failed` | `test_a_position_opened_by_this_ticks_fill_is_stored_marked_at_its_fill_price` — stored `last_price` `None` | none |
| P1b | neither `last_price` nor `unrealised_pnl` written | killed, `1 failed` | the same test | none |
| P2 | the row's `unrealised_pnl` is `pnl + 1` on the fill tick | killed, `1 failed` | the same test — stored `1.00`, not 0 | none |
| P3 | the fill-tick row marked at the bid while the totals value it at cost | killed, `1 failed` | the same test — stored `99.99`, not `99.00` | none |

**R2 is the arm that justifies asserting the words.** Both causes of
`risk_inputs_unavailable` block, so a test asserting the code and the block passes R2. What
R2 breaks is what the operator is told: "the account holds no USD" sends them to the account,
while the truth is that engine 1 could not read it. Only `NO_BALANCE_PUBLISHED` in the reason
tells the two apart, and the EUR test pins the other direction.

**Every P arm is killed by one test and nothing else in the file.** The payload-level test
beside it (`…counted_in_the_portfolio_value`) asserts the *totals* and stays green under all
four, which is exactly how the NULL row lived beside correct totals since spec 92.

**What else can see these arms — measured, not assumed.**

- **P1 against spec 105's criterion tests and A's rehearsal** (`tests/verify/test_phase6_criteria.py`
  and `tests/engines/test_trade_chain_rehearsal.py`, `-k "equity or rehearsal or filled or
  watched"`): **survived**, `15 passed, 32 deselected`. The criterion still has its NULL-mark
  branch — it accepts a missing `last_price` when the equity row valued the position at cost —
  so it cannot tell the defect from the fix; the stored-row test in my file is the only guard.
  Now that engine 21 always stores the mark on the fill tick, that branch is reachable only by
  the defect. Reported to C through the lead; the criterion is C's.
- **R1 against both rehearsals, `test_scout.py` and `test_decision.py`: survived**,
  `134 passed`. Every one of them publishes a balance, so the removed branch is guarded by
  `test_risk.py` alone — which is where it should be, and is now said rather than assumed.

**The two controls, against the whole of `tests/`** (`logs/verify/b106-sweep-R0-control-1t-tests_.log`,
`…P0-control-1t-tests_.log`). Expected red: the eight parametrisations of
`test_pending_on_the_real_tree_names_the_subject_and_the_spec` (C, spec 100).

- **R0 — behaviourally survived**, `8 failed, 3201 passed, 2 skipped` in 1339.20s: exactly the
  known eight, nothing else.
- **P0 — behaviourally survived**, `8 failed, 3201 passed, 2 skipped` in 1446.45s: exactly the
  known eight, nothing else.

The harness labels both "KILLED" because pytest exited 1; the failing sets were compared with
the known red, which is the verdict. Hashes after both runs equal the pre-sweep values. No
native fault this time; no run was repeated.

### Spec 106 — the gate at the spec 106 boundary

**Agent:** B (session 5) · **Date:** 2026-09-17

Run sequentially, each to its own file, after the sweep and with nothing else of mine running.

| Command | Result | Log |
|---|---|---|
| `mypy --strict src/ scripts/` | `Success: no issues found in 153 source files` | `logs/verify/b106-gate-mypy.log` |
| `ruff check src/ tests/ scripts/` | `All checks passed!` | `logs/verify/b106-gate-ruff.log` |
| `pytest tests/ -q` | `8 failed, 3201 passed, 2 skipped, 3 warnings in 1411.00s` — exactly the known eight | `logs/verify/b106-gate-pytest.log` |
| `verify.py --phase 6` | `12 criteria: 2 PASS, 1 FAIL, 9 PENDING`; the FAIL is `toolchain_green` on the same eight; `paper_equity_continuous_across_fill` PASS, `docs_vocabulary` PASS | `logs/verify/b106-gate-verify.log` |

Committed by the lead as `268f49e`. **Reported, not changed:** engine 9's README ("One deliberate
asymmetry with engine 11") and `order_book/engine.py` docstring still describe the removed
fallback (C's); spec 105's criterion keeps a NULL-mark branch only the defect now reaches (C's);
`engines/cost/contracts.py` and README call `fallbacks_used` a `rejections` column, and
`clients/paper/broker.py` exports an unused `FALLBACK_PAPER_LEDGER` under a stale comment (mine,
for a later session).
