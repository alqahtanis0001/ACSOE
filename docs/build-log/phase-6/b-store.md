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
