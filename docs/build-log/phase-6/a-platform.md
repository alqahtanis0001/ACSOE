# Build log — Phase 6 — a-platform

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

### Decision: two status enums for one vocabulary, and couplings enforced at the boundary

**Agent:** A · **Task:** spec 84 · **Date:** 2026-09-16

**Options.** Spec 84 gives `OrderAck.status` three values (`resting`, `filled`, `rejected`) and
`OrderState.status` five (those plus `cancelled`, `expired`). Either one enum of five used by
both — with a validator on the ack refusing the two that cannot happen — or two enums.

**Chose.** Two `StrEnum`s, `OrderAckStatus` and `OrderStatus`, sharing the three spellings.
Because they are `StrEnum` members they compare equal across the two types, so
`ack.status == OrderStatus.RESTING` is True and a consumer holding either may compare against
either; `test_the_ack_statuses_compare_equal_to_the_order_statuses_they_share` pins that and
also pins the subset relation, so the vocabularies cannot drift apart.

**Because.** A placement cannot come back `cancelled` or `expired` — nothing has had time to
happen. A type that can express it invites a consumer to write a branch for it, and that branch
is then dead code nobody can test. The one-enum-plus-validator version moves the same fact from
the type to a runtime check, which is strictly later and strictly weaker.

**The second decision, and it is the one B will feel.** The three models enforce *couplings*
rather than values: `limit_price` present exactly for a limit order; `post_only` refused on a
market order; `avg_fill_price` present exactly when `filled_qty > 0`; no fee on an order that
filled nothing; `closed_at` present exactly when the status is terminal. Each of those is a
self-contradiction the consumer would otherwise have to re-check, and "absent is never zero" —
already the rule for `OrderBookSnapshot` and `QuoteTick` in this module — is only true if
something enforces it at the boundary. The concrete hazard is `avg_fill_price`: an unfilled
order whose price answered `0` puts a zero cost basis into B's ledger, and a ledger that is
"exact to the cent after a round trip" cannot notice it, because zero times zero is zero.

**Cost, stated so it can be overturned rather than discovered.** The couplings forbid some
shapes B might want. Two that were checked explicitly and are *allowed*: a partially filled
order that is still `resting` (fill, price, fee, no `closed_at`), and a partially filled order
`cancelled` at the unfilled-entry window (fill, price, fee, `closed_at`). Both have tests. If
B needs a shape these refuse, it is one line on my side and a message, not a workaround.

**`post_only` has no default, deliberately.** Invariant 8 makes an entry post-only; invariant 14
makes a liquidation a taker. A default is therefore silently right at one of the two call sites
and silently wrong at the other, and the wrong direction is an entry that crosses the book and
pays taker fees the cost gate never priced.

### The `userref` bound has to be asserted on the constraint, not the field name

**Agent:** A · **Task:** spec 84 · **Date:** 2026-09-16

**What happened.** Spec 84's acceptance says the `userref` bound is "asserted on the constraint,
not the field name". Writing it the obvious way —
`pytest.raises(ValidationError, match="userref")` — produces a test that cannot fail.

**Why.** All three order models are `extra="forbid"`. Pydantic's refusal for an unknown key
always contains the key name in its `loc`, so `match="userref"` passes whether the bound
rejected the value *or the field was deleted outright*. A found one of its own new assertions
surviving exactly that mutation in Phase 4, in the same hour it was written; the rule is in
`code-standards.md` and this is its second instance.

**Fix.** One shared annotation, `UserRef = Annotated[int, Field(ge=USERREF_MIN, le=USERREF_MAX)]`,
used by the request, the ack and the state, so the three cannot disagree about what a `userref`
is. Every assertion matches pydantic's constraint text — *"Input should be greater than or equal
to …"* — which no missing-field refusal can produce. The bound is also asserted *inclusive* at
both edges and at zero, because a model that refused every `userref` would satisfy the two
refusal cases perfectly.

**Consequence.** Mutations M3 and M4 drop one bound each. M3 →
`test_a_userref_outside_the_signed_32_bit_range_is_refused[below the signed 32-bit floor]`,
`Failed: DID NOT RAISE ValidationError`. M4 → the ceiling case **and both** ack/state cases,
three tests, which is the shared annotation doing its job.

### The live refusal: the exception is not the evidence, the transport count is

**Agent:** A · **Task:** spec 84 · **Date:** 2026-09-16

**What happened.** The four order calls on the live client must raise *and make no request*.
The natural test — `pytest.raises(KrakenUnavailableError)` — proves neither half.

**Why.** Two separate reasons, and each on its own is enough to make the test worthless.
First, every fail-closed path in `clients/kraken/` raises that one type on purpose, so the bare
form cannot tell a Phase 8 refusal from the missing-credential refusal in `_private` that would
fire anyway if the refusal were deleted. Second, an exception says nothing about whether the
network was touched: a method that placed the order and *then* raised would pass.

**Fix.** Three things. The client under test is built **with** credentials and both TTLs, so
nothing else can refuse first, and a paired test builds a credential-less one and asserts the
two messages differ (`"Phase 8"` in one, `"API credentials"` in the other). The refusal names
the method, so the four are told apart. And the assertion is `transport.calls == []` on a
`CountingTransport` that is **proven capable of counting inside the same test**: after the
refusal, the same object serves a real `asset_pairs()` and the count is asserted to have moved
to `["AssetPairs"]`. Without that control, deleting the transport's `calls.append` would leave
every zero-call assertion in the file green forever — the Phase 3 defect, "a fake transport that
counted nothing, in tests about whether a second call makes a request".

**Consequence.** M1 inserts a real `_public` call *before* the refusal in `add_order`. Red:
`AssertionError: add_order touched the network: ['AssetPairs']`, killed by
`test_a_live_order_call_makes_zero_transport_calls[add_order]` and
`test_the_facade_refuses_the_same_way_and_makes_no_request[add_order]` — and *not* by the
message test, which is the discrimination working. M15 makes the `KrakenClient` facade stop
forwarding to the refusing client: `Failed: DID NOT RAISE KrakenUnavailableError`, killed by the
facade test alone. The facade holds no refusal of its own on purpose — two copies is two things
to remove in Phase 8 and one of them would be missed.

**And a tripwire for a fifth call.** `test_no_order_call_is_left_without_a_refusal_test`
compares the test file's parametrisation, `rest.ORDER_CALLS`, and
`OrderClientProtocol.__protocol_attrs__`. A fifth method added to the protocol and implemented
in `rest.py` without a refusal is exactly the half-working live client spec 84 forbids, and it
would otherwise be invisible: every test above would keep passing on the other four.

### Spec 84 mutation sweep — 15 applied, 15 killed, 0 survivors

**Agent:** A · **Task:** spec 84 · **Date:** 2026-09-16

Harness at `scratchpad/mutate84.py`. Each mutation is applied by exact literal text whose
occurrence count is asserted to be **exactly one** first; the file is restored from a byte copy
taken before the mutation and the sha256 is compared in the same statement that restores it,
printed per mutation (`restored: True` on all fifteen). **Restored before the next mutation, not
in a `finally` at the end**, so no verdict is "this mutation plus the previous one". Never
`git checkout --`: teammates do not commit and that would delete their working tree.

**Scope, stated because an excluded directory is a hole with a shape.** The sweep ran against
`tests/clients/kraken/` only — the directory that owns the code — per the Phase 4 rule about
running a sweep narrowly in a shared checkout, and because a mutation live in this tree can turn
another agent's run red and a spurious failure reads as KILLED. Baseline immediately before the
sweep: **149 passed**. There were no survivors, so nothing needed re-running against the whole
suite; had there been one, a subset survival would not have counted as a survival.

Every kill is named by a test in `tests/clients/kraken/test_orders.py`. **No incidental kills** —
nothing was killed only by a file with no business knowing about the order surface.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| M1 | `add_order` makes a transport call before refusing | KILLED (2) | zero-transport-calls[add_order], facade[add_order] |
| M2 | the refusal names neither the method nor the phase | KILLED (8) | all four naming tests, all four facade tests |
| M3 | the `userref` floor is dropped | KILLED (1) | userref-outside-range[floor] |
| M4 | the `userref` ceiling is dropped | KILLED (3) | userref-outside-range[ceiling], ack bound, state bound |
| M5 | a reason on an accepted order is allowed | KILLED (2) | reason-on-accepted[resting, filled] |
| M6 | a rejection with no reason is allowed | KILLED (3) | rejection-with-no-cause[absent, empty, whitespace] |
| M7 | a limit order with no price is allowed | KILLED (1) | limit-without-a-price |
| M8 | `post_only` on a market order is allowed | KILLED (1) | post-only-on-a-market-order |
| M9 | `post_only` gains a default | KILLED (1) | post-only-has-no-default |
| M10 | an average price on an unfilled order is allowed | KILLED (1) | average-price-on-an-unfilled-order |
| M11 | a fill with no average price is allowed | KILLED (1) | fill-without-an-average-price |
| M12 | a terminal status needs no close time | KILLED (4) | all four terminal statuses |
| M13 | a resting order may carry a close time | KILLED (1) | resting-with-a-close-time |
| M14 | a fee on an order that filled nothing is allowed | KILLED (1) | fee-on-an-order-that-filled-nothing |
| M15 | the facade stops forwarding `add_order` | KILLED (1) | facade[add_order] |

**What this sweep does not prove, and it is the seam rule.** Spec 84 is a contract with no
consumer yet: B's paper broker (spec 88) and engines 18, 21 and 22 do not exist. Every test here
is a test of the models and of the live refusal, and nothing yet exercises the protocol with no
double on either side. Phase 4 found that shape twice in one day — A built engine 23 against
`label_bars(...)`, a signature agreed by message that never existed, and *nothing went red*
because everything drove a double. So the seam test for this contract is owed by spec 86's
wiring test and spec 87's rehearsal, both of which run B's real broker against A's real
protocol, and it is recorded here as owed rather than assumed.

### Engine 3 is stateless across cycles, and spec 85 asks it what happened since last tick

**Agent:** A · **Task:** spec 85 · **Date:** 2026-09-16

**What happened.** Spec 85 wants `trade_ranges[pair]["since_ts"]` to be "the previous tick's
`context.now`", and wants the first tick of a run to publish no ranges at all. Engine 3 can do
neither directly: architecture invariant 1 makes an engine stateless across cycles, `state` is a
fresh dict every tick, and `EngineContext` carries `now`, `mode`, `run_id`, `config` and
`clients` — no previous tick and no tick counter.

**Why.** The two halves have different answers and I nearly gave them the same one.

*`since_ts`* is `context.now - timeframes.loop_tick_s`. There is nowhere else it could come
from, and it is not an invention: `bar_closed_on` in this same engine already solves the
identical problem the identical way — "did the bar index change since one tick ago" — and that
device has been in the guard chain since Phase 2.

*"Is this the first tick"* is **not** derivable from the clock, and my first instinct was wrong
in an instructive way. I was about to add a `buffering_since` timestamp to
`KrakenWebSocketClient` — my own file, state in the client layer where state is allowed — and
have the engine refuse when the window reached back before the stream existed. It would have
worked for the real client and been **silently useless against C's fake**, which has no such
attribute: a `getattr` guard would either publish no ranges for the whole of spec 87's
rehearsal, or fall through and publish them on tick 1, and neither is a thing a test would
notice. The answer was already in `state`: `core/`'s `tick()` writes `state["cycle_id"]` and
starts it at 1 for every new `Orchestrator`. That is exactly "the first tick of a run",
including the first tick after a restart.

**Fix.** `_trade_ranges` returns `{}` when `state["cycle_id"]` is absent, is not an `int`, is a
`bool`, or is `<= 1`. Engine 3's README changes from "reads nothing from `state`" to "reads
`cycle_id`, which `core/` supplies, and no engine's payload" — the distinction that keeps
contract rule 2 honest.

**Consequence, and the one number in this spec that is approximate.** If the loop runs late,
the real gap between two ticks is longer than `loop_tick_s` and the trades in the overshoot
appear in **no** range at all — a stop touched in that overshoot is missed by engines 21 and
22. `bar_closed_on` has the same shape and does not have the same consequence, because it is
asking a question about an index rather than measuring an interval. Written into the engine
docstring and the README rather than left to be found, and raised with the lead: fixing it
properly means giving the engine the previous tick's time, which is a `core/` change and is not
mine. It is not a defect in this spec; it is the boundary of what a stateless engine can say.

**Also decided here.** The window is `(since_ts, now]`, half-open at the bottom, so consecutive
ticks tile the timeline without overlapping — that is what "a range never spans two ticks"
means operationally, and it is why a trade exactly on the boundary belongs to the earlier tick.
Closed at the top at `context.now`, so a trade stamped after the tick — exchange clock skew —
is excluded rather than read as the future.

**And one thing deliberately not done.** Spec 85's scope limit says "do not publish a range for
a pair that is not subscribed", and the obvious reading is a filter against
`stream.subscription`. There is no filter, and the absence is the point: step 3 requires the
ranges to be computed from **the same trades the candle builder consumes**, so filtering one
reading and not the other is precisely the disagreement step 3 exists to prevent. The scope
limit is satisfied by construction instead — the buffer only ever holds pairs that were
subscribed when the trade arrived.

### Spec 85 mutation sweep — 11 applied, 11 killed, 0 survivors

**Agent:** A · **Task:** spec 85 · **Date:** 2026-09-16

Harness at `scratchpad/mutate85.py`, same rules as spec 84's: anchor asserted to occur exactly
once, byte copy taken before the mutation, restored with the sha256 compared in the same
statement (`restored: True` on all eleven), restored **before** the next mutation rather than in
a `finally`. Never `git checkout --`.

**Scope, and why it is three files rather than one.** `tests/engines/test_market_sensor.py`
owns engine 3, and `test_data_guard.py` and `test_subscription_scope.py` are the two other files
in A's lane that drive engine 3 **for real** rather than hand-building its payload. Including
them is what makes an incidental kill visible: if a `trade_ranges` mutation had been killed only
by a `data_guard` test, that would be a branch nobody who knows about ranges is asserting on.
None was. Every one of the eleven was killed by a test in `test_market_sensor.py`. Baseline
immediately before the sweep: **75 passed**. No survivors, so nothing needed re-running against
the whole suite.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| N1 | the window is not bounded below — the range spans every buffered tick | KILLED (4) | the range test, the silent-pair test, never-spans-two-ticks, the boundary test |
| N2 | the window is closed at the bottom — a boundary trade is in both ticks | KILLED (1) | the boundary test |
| N3 | the window is not bounded above — a trade after the tick is included | KILLED (3) | never-spans-two-ticks, the boundary test, the clock-skew test |
| N4 | the first tick publishes a range anyway | KILLED (6) | the first-tick test and all five `cycle_id` cases |
| N5 | `since_ts` is two ticks back rather than one | KILLED (5) | five, including two pairs and never-spans-two-ticks |
| N6 | the low is the first price seen rather than the minimum | KILLED (3) | the range test, never-spans-two-ticks, ranges-and-candles |
| N7 | the high is the first price seen rather than the maximum | KILLED (3) | never-spans-two-ticks, ranges-and-candles, two pairs |
| N8 | a silent pair is published as a zero-trade range at its last price | KILLED (1) | a-range-of-zero-trades-cannot-be-constructed |
| N9 | a low above its high is accepted | KILLED (1) | a-low-above-its-high-is-refused |
| N10 | prices cross `state` as floats rather than exact decimal strings | KILLED (8) | eight, including the exact-decimal-strings test |
| N11 | `state_dict` reports `trades + 1` | KILLED (7) | seven |

**The two spec 85 names explicitly**: "a range carried across two ticks" is N1 and N5, and "the
absent pair published as zero" is N8.

Red messages worth keeping, because they say what the defect would have looked like in
production rather than only that something failed:

- **N1** — `{'low': '99.25', 'high': '500.00', 'trades': 4, ...} != {'low': '99.25',
  'high': '101.50', 'trades': 3, ...}`. The 500.00 is a trade from the *previous* tick's window.
  In production that is a stop far above the market reading as touched.
- **N2** — `AssertionError: the boundary trade is not in the later range / assert '777.00' ==
  '100.00'`, and the paired count assertion catches it from the other side: the two ticks' counts
  sum to one more than the number of trades.
- **N4** — `assert {'AAA/USD': {...}} == {}`. A range on tick 1, measured over a window the
  previous tick never observed.
- **N8** — `Failed: DID NOT RAISE ValidationError`. `TradeRange` is what makes "a silent pair is
  absent, never zero" structural rather than remembered, and N8 is the proof that the model —
  not a comment — is holding the rule.

**N10 is the one I would not have written without the rule about what a quietly wrong value
returns.** `float(self.low)` is not a crash and not a zero: it is the right number, in range,
readable in a log, and wrong in the fourth decimal on a small-tick pair — arriving in a barrier
comparison, which is the magnitude that comparison works at. `EngineResult.data` refuses a
`Decimal` and **accepts a float silently**, so nothing in `core/` would object. It is killed by
eight tests only because the assertions compare exact strings; had any of them compared numbers,
it would have survived every one.

### CORRECTION to the two entries above: `context.previous_now` landed and spec 85 was reworked onto it

**Agent:** A · **Task:** spec 85 · **Date:** 2026-09-16

*Correcting the two entries above rather than editing them, per script rule 6. Everything they
describe was true of the code for about an hour.*

**What happened.** I reported the late-loop approximation to the lead as a `core/` question and
carried on. The lead added `EngineContext.previous_now` the same hour — the previous tick's
`context.now`, `None` on the first tick of a process — and `Orchestrator._context` now carries
it. So the approximation did not have to stay, and engine 3 was reworked onto the real stamp
before spec 85 was reported done.

**What changed on my side.**

- `_trade_ranges` reads `context.previous_now` and returns `{}` when it is `None`. It no longer
  takes `state`, no longer takes `tick_s`, and `_MICROSECONDS_PER_SECOND` is gone from
  `engine.py`.
- Engine 3 reads **nothing** from `state` again. The `cycle_id` read and the `# noqa: ARG002`
  removal are both reverted, and the README's "What it reads from `state`" section goes back to
  "Nothing" with a pointer at `context.previous_now`.
- The docstrings in `engine.py`, `contracts.py` and `README.md` that explained the approximation
  now explain why the field exists instead. **`bar_closed_on` still uses `now - tick_s` and that
  is still correct**, and the distinction is written down in all three places because it is the
  thing a later reader will try to "fix": `bar_closed_on` asks about an *index* and fires exactly
  once however late the loop ran; a range measures an *interval*, and on an overshoot the trades
  inside it fell into no range at all.

**The new test is the one that matters.**
`test_a_loop_that_ran_late_produces_a_longer_range_and_not_a_hole` sets the previous tick three
ticks back and puts a trade in the overshoot. It asserts the range reaches it, **and** asserts
in the same test that the one-tick window does not — so the test cannot pass by accident on a
window that happens to be wide enough. That second assertion is what makes it a measurement of
the overshoot rather than a restatement of the arithmetic.

**And a defect of my own, in the test helper, found by the test failing.** `ranges_at` took
`previous: datetime | None = None` and treated `None` as "default to one tick back". But `None`
is a **meaningful value** for this field — it is "there was no previous tick" — so the default
conflated *the caller did not say* with *the caller said there is none*, and the first-tick test
asked for `previous=None` and silently got a one-tick window. It failed loudly only because the
engine then published a range where the test expected nothing; had the default been the other
way round it would have passed while testing nothing. Fixed with an `_ON_TIME` sentinel. This is
`code-standards.md`'s "a handler that cannot distinguish two situations will silently pick the
wrong one", arriving as a default argument rather than as an `except` clause.

### Spec 85 mutation sweep, re-run against the reworked engine — 13 applied, 12 killed, 1 checked negative

**Agent:** A · **Task:** spec 85 · **Date:** 2026-09-16

**The first sweep's evidence was invalidated by the rework and is superseded by this one.** A
mutation table for code that no longer exists is worse than none: it reads as coverage. Same
harness, same rules — anchor asserted to occur exactly once, byte copy taken first, restored
with the sha256 compared in the same statement (`restored: True` on all thirteen), restored
before the next rather than in a `finally`. Same scope: `test_market_sensor.py`, plus
`test_data_guard.py` and `test_subscription_scope.py`, the two other files in A's lane that
drive engine 3 for real. Baseline immediately before: **71 passed**. Every kill was by a test in
`test_market_sensor.py`; no incidental kills.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| N1 | the window is not bounded below | KILLED (5) | five, including the late-loop test |
| N2 | the window is closed at the bottom — a boundary trade is in both ticks | KILLED (1) | the boundary test |
| N3 | the window is not bounded above | KILLED (3) | never-spans-two-ticks, boundary, clock-skew |
| N4 | the first tick sets `previous = context.now` | **SURVIVED — equivalent** | see below |
| N4b | the first tick invents a one-minute start | KILLED (1) | the first-tick test |
| N5 | the window reaches a minute further back than the previous tick | KILLED (6) | six |
| N6 | the low is the first price seen rather than the minimum | KILLED (3) | three |
| N7 | the high is the first price seen rather than the maximum | KILLED (3) | three |
| N8 | a silent pair is published as a zero-trade range at its last price | KILLED (1) | a-range-of-zero-trades-cannot-be-constructed |
| N9 | a low above its high is accepted | KILLED (1) | a-low-above-its-high-is-refused |
| N10 | prices cross `state` as floats | KILLED (9) | nine |
| N11 | `state_dict` reports `trades + 1` | KILLED (8) | eight |
| N12 | the window is derived from `loop_tick_s` again instead of `previous_now` | KILLED (1) | **the late-loop test, alone** |

**N4 is a checked negative, not a survivor, and it is filed as one deliberately.** Setting
`previous = context.now` on the first tick makes the window `(now, now]`, which is empty, so the
engine still publishes `{}` and no test can tell. The behaviour is unchanged, so there is nothing
to write a test for; filing it as a survivor would send the next person to cover a case that
cannot fail and would make a real survivor look less urgent. **N4b is the non-equivalent form of
the same claim** — invent a one-minute start — and it dies on the first-tick test with
`assert {'AAA/USD': {...}} == {}`. The pair is the evidence; N4 alone is not.

**N12 is the mutation this rework exists for, and it is killed by exactly one test.** It puts
back `now - loop_tick_s`, which is what the code did an hour ago and what every other test in
the file still passes under: `assert '100.00' == '300.00'` from
`test_a_loop_that_ran_late_produces_a_longer_range_and_not_a_hole`, and nothing else objects.
That is the honest shape of the defect — a range that is right on every tick where the loop ran
on time, and silently short on the ones where it did not. One test out of thirty-eight can see
it, which is a reminder that "the rest of the suite is green" says nothing about a defect whose
whole nature is that it only appears under a condition no other test creates.

### A gap marker is written at reconnect, so a timestamp test misses the break that truncates the fixture

**Agent:** A · **Task:** spec 86 · **Date:** 2026-09-16

**What happened.** Spec 86 step 3 says the cutter "refuses a window with a recorded `gap`
marker inside it". The obvious implementation — refuse when a gap line's `ts_recv` falls inside
the window — is wrong in one direction, and it is the direction that silently damages the
fixture.

**Why.** `ws.py::_close_gap` writes the marker **on reconnect, not on disconnect**, and says
why: the length of a gap is not known until it ends, and a marker written at disconnect would
have to be edited afterwards, which invariant 11 forbids. `scripts/record.py` does the same.
So a break that begins at 04:09 inside a 04:00–04:10 window and ends at 04:12 has its **only**
marker at 04:12 — outside the window. A `ts_recv` test cuts happily and produces a fixture
whose last minute is missing, with nothing anywhere saying so. The direction matters: the miss
is silent and the fixture looks complete, whereas the opposite error (refusing too eagerly)
announces itself immediately.

**Fix.** The test is on the gap's **interval** against the window, not on the marker's
timestamp. `gap_interval` reads the span out of the payload and `intersects` compares two
half-open intervals. `test_a_gap_that_starts_inside_the_window_and_ends_after_it_is_refused`
is the test for exactly this case, and mutation **P4** — put the timestamp test back — dies on
it along with two others.

**Two more things fell out of writing that function, both recorded because each is a
conflation the code would otherwise have made silently.**

*Two payload shapes are in the archive.* `scripts/record.py` writes `disconnected_at` and
`reconnected_at`; engine 2 writes `ws.py`'s own dict, which uses `started_at` and `ended_at`.
Reading only the first makes **every break the daemon recorded** invisible to this cutter — and
the daemon's recordings are the newer half of the archive. Mutation **P7** drops the second
shape and dies.

*A marker carrying neither shape is not a zero-length gap.* It is a break whose span this script
does not know, which is a different fact with a different right answer. The cutter falls back to
the marker's own `ts_recv` as a **point** inside the window and says "span unknown" in the
refusal, rather than deciding the break did not happen.

### Decision: refuse an uncovered window, a doubled archive, and an empty pair

**Agent:** A · **Task:** spec 86 · **Date:** 2026-09-16

**Options.** Spec 86 names one refusal — the gap. Three more conditions produce a fixture that
is quietly wrong, and the choice was whether to refuse on them or leave them to whoever reads
the fixture later.

**Chose.** Refuse on all three, each naming what it found.

**Because.** A fixture that is quietly wrong is worse than no fixture: the criterion that reads
it then passes for the wrong reason, which is the failure mode this whole phase's rules are
written against.

- **The window is not covered by the archive at both ends.** This is the gap the *marker cannot
  describe*: if the recorder was not running there was no reconnect, so nothing wrote a marker,
  and the silence is indistinguishable from a quiet market. It is the same point
  `scripts/recording_report.py` makes by reporting a **tiling** rather than a gap count —
  unrecorded silence has to be a first-class gap or it hides between two segments nobody
  compared.
- **More than one archive file contributed.** Two `record.py` processes ran concurrently from
  2026-09-09T13:19 and part of `data/raw/` holds every frame twice. A fixture built from both
  gives engine 9's slippage walk **twice the depth** — a plausible, in-range, wrong answer that
  nothing downstream could detect, which is the exact shape `code-standards.md` says to look for.
  The refusal names `--prefix` as the fix, and there is a test that passing it then succeeds.
- **A named pair with no book frame in the window.** An empty pair in a two-pair fixture makes
  spec 96's "thin **and** deep" criterion silently test one book.

**Cost.** Four refusals is four ways for C to be told no. Each names the thing it found and, where
there is one, the flag that fixes it, because "refused" on its own sends the operator back to a
10 GB archive with no idea what to change.

**Confirmed against the real archive, read-only, dry run.** A 5-minute window on 2026-09-11 over
the real `data/raw/` — 3.7 GB across two files, 3m02s — **refused**: no BTC/USD book frame in
that window. That is the refusal working on real data rather than on a fixture I wrote, and it
also exercised the two-file path: both `kraken_v2_2026-09-11.jsonl` and
`kraken_v2__msi__2026-09-11.jsonl` were scanned.

### The prefilter is broader than its parser, and there is a test that says so

**Agent:** A · **Task:** spec 86 · **Date:** 2026-09-16

**What happened.** The archive is tens of gigabytes and the window is minutes, so the cutter
cannot parse every line — the real-archive run above spent three minutes on 3.7 GB *with* a
prefilter. But `code-standards.md` records that A shipped two prefilters in Phase 4 that were
**narrower** than the parsers they fronted, one of which would have classified the entire
recording as unrecorded: plausible enough to be believed and acted on, and acting on it would
have meant rebuilding an archive that was fine.

**Why the Phase 4 ones were wrong, and why this one is not.** They matched `orjson`'s exact
separators, so they found nothing against any other writer. `might_be_wanted` matches no
separator, no quoting and no key order. It admits a line containing `book`, `gap`, **or `\u`**,
and the third marker is the whole argument: a line whose parsed `channel` is `"book"` either
contains those four bytes or has escaped a character, in which case it contains `\u`. So a line
matching none of the three cannot be one we want, and the skip is provably safe.

**Fix, and the part that makes it evidence rather than a claim.**
`test_the_prefilter_admits_a_unicode_escaped_book_line` builds a line spelling the channel
`"book"`, asserts the bytes `book` appear nowhere in it, and asserts both that the
prefilter admits it and that the cutter emits it. Mutation **P13** drops the `\u` marker — the
narrower form — and dies on that test with `might_be_wanted(b'...\\u0062ook...')` returning
False. A paired test asserts a trade line **is** skipped, so a prefilter returning True for
everything would not satisfy the file.

### Spec 86 mutation sweep — 16 applied, 16 killed, 0 survivors

**Agent:** A · **Task:** spec 86 · **Date:** 2026-09-16

Harness at `scratchpad/mutate86.py`. Anchor asserted to occur exactly once, byte copy taken
first, restored with the sha256 compared in the same statement (`restored: True` on all
sixteen), restored **before** the next rather than in a `finally`. Never `git checkout --`.

**Scope: `tests/cli/` and `tests/scripts/test_cut_book_fixture.py`.** `tests/cli/` is
deliberately wider than the new wiring file alone, because `build_clients` already has tests in
`test_entrypoints.py` — so a wiring mutation killed *only* there would be an incidental kill and
would be visible as one. None was: every kill below is by a test in the file that owns the code.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| P1 | the paper wrap is applied in every mode, including live | KILLED (2) | no-other-mode[live], no-other-mode[replay] |
| P2 | the paper wrap is never applied | KILLED (2) | paper-receives-the-broker **and the seam test** |
| P3 | the mode test becomes `!= "live"` | KILLED (1) | no-other-mode[replay] |
| P4 | the cutter tests the gap marker's timestamp, not its interval | KILLED (3) | all three gap-refusal tests |
| P5 | the cutter ignores gaps entirely | KILLED (4) | four |
| P6 | a gap touching the window edge counts as intersecting | KILLED (1) | ends-exactly-at-the-window-start |
| P7 | only `record.py`'s gap shape is read | KILLED (2) | engine-2-shaped-marker, `gap_interval` unit |
| P8 | the coverage check is dropped | KILLED (1) | window-the-archive-does-not-cover |
| P9 | a doubled archive is accepted | KILLED (1) | two-recorders |
| P10 | an empty named pair is accepted | KILLED (1) | pair-with-no-book-frame |
| P11 | the body is re-serialised instead of copied | KILLED (2) | byte-for-byte, the `\u` test |
| P12 | the window's upper bound becomes inclusive | KILLED (1) | byte-for-byte |
| P13 | the prefilter drops the `\u` marker | KILLED (1) | the `\u` test |
| P14 | the output is written in text mode | KILLED (4) | four, including no-carriage-returns |
| P15 | the invariant 11 guard on the output path is dropped | KILLED (1) | refuses-to-write-inside-the-recording |
| P16 | a naive window bound is assumed to be UTC | KILLED (2) | naive-bound, the refusal-type unit |

Red messages worth keeping:

- **P3** is killed by the **replay** case alone, and that is the reason the parametrisation has
  a replay row at all. `== "paper"` and `!= "live"` read the same today and stop reading the
  same the moment a fourth mode exists; the negative form would then wrap it silently. Without
  the replay case this mutation survives and the "simplification" looks free.
- **P11** — `assert [b'{"v": 1, "...'] == [b'{"v":1,"ki...']`. The re-serialised line differs
  from the recorded one by whitespace alone, which is exactly the kind of difference that would
  never be noticed by eye and does break the Kraken checksum the frame carries over what the
  exchange actually sent.
- **P14** — `assert [b'...0000Z"}]}}\r'] == [b'...000000Z"}]}}']`. A text-mode write on Windows
  turning every LF into CRLF, in the one directory (`tests/fixtures/`, marked `-text`) where
  there is no clean filter to hide it.
- **P2** is killed by the wiring test **and** by
  `test_an_order_in_paper_mode_never_reaches_the_live_client_s_refusal`, which is the seam test
  with no double on either side — B's real broker, built by the real `build_clients`, against
  A's real protocol. That second kill is the one that discharges the debt spec 84 recorded as
  owed: until it existed, every test of the order surface on either side was a test of a mock.

**The seam test asserts on *where the failure comes from*, not on a type.** With no credentials
the broker cannot price a fill — `TradeVolume` gives nothing and a remembered fee is forbidden —
so the call fails either way. What distinguishes the two worlds is the **message**: the live
client's refusal names Phase 8. `isinstance` against `OrderClientProtocol` cannot show this,
because a `runtime_checkable` Protocol only checks that the four names exist and the bare
`KrakenClient` has all four — they are the ones that refuse.

### FINDING, not fixed (B's lane): in paper mode nothing writes a gap marker any more

**Agent:** A · **Task:** spec 86 · **Date:** 2026-09-16

**What happened.** Found while checking that `close_clients` still reaches the stream through
the new wrap. `PaperBroker` forwards six of the seven methods `MarketStreamProtocol` declares
and **does not forward `drain_gaps`**. Measured, not read:

```
MarketStreamProtocol declares: ['connected', 'drain', 'drain_gaps', 'drain_trades',
                                'gaps', 'latest_quote', 'recent_trades']
PaperBroker is missing:        ['drain_gaps']
has __getattr__ fallback:      False
```

**Why it is silent, and why it matters.** Engine 2 `market_data_recorder` takes breaks with
`getattr(stream, "drain_gaps", None)` and returns `()` when the attribute is absent. So from
the moment `build_clients` wraps the client — which is **every run**, because paper is the only
mode the loader accepts — engine 2 asks the broker for gaps, gets nothing, and writes no `gap`
line into `data/raw/`. Nothing raises, nothing logs, and `stream_available` and `connected`
still forward correctly, so the recorder looks healthy.

The damage is to the one artefact that cannot be rebuilt. Invariant 11: *a break is marked,
never healed.* A recording with the reconnects missing is not a recording with a known hole —
it is a recording that **claims to be continuous and is not**, and there is no way to tell
afterwards which it was. `scripts/recording_report.py` reports a tiling precisely so that a
break cannot hide between two segments nobody compared, and this removes the markers the
tiling is built from.

It also disarms a refusal I landed an hour ago: `scripts/cut_book_fixture.py` refuses a window
containing a gap marker, and a window with no markers written passes that check while spanning
a reconnect. Its coverage check would still catch a long outage and would not catch a
three-second one, which is the common case — the real archive shows several an hour.

This is the exact conflation `code-standards.md` names: `getattr(..., None)` answers *the
stream has no breaks to report* and *this object cannot report breaks* through one channel, and
engine 2 has no way to tell them apart. The broker is not at fault for engine 2's `getattr`,
and engine 2 is not at fault for the broker's missing method; the seam is, and a seam is tested
by neither side by default.

**Not fixed. `clients/paper/` is B's** — ownership rule 1, and spec 87 says in as many words
not to fix B's code if something goes red. Reported to B and to the lead the moment it was
confirmed, with the one-line fix (`def drain_gaps(self): return self._real.drain_gaps()`) and
the two tests that would keep it fixed: one asserting `PaperBroker` satisfies every attribute
of `MarketStreamProtocol` by walking `__protocol_attrs__` rather than by listing them, and one
driving engine 2 for real over a broker-wrapped stream that has a gap and asserting a `gap`
line reaches the recorder. The first is the one that scales — a seventh method added to the
protocol tomorrow would otherwise be dropped the same way, silently.

**The general shape, because it will recur in this phase.** A decorator that forwards by
writing out each method drops whatever the author did not think of, and the drop is invisible
at construction: `isinstance` against a `runtime_checkable` Protocol would have caught this in
one line, and nothing was calling it. A wrapper needs a test that walks the wrapped interface,
not a test per method.

---

## SPEC 84 AMENDMENT — `OrderState` gains `qty` and `limit_price`, 2026-09-16

### What happened

B, building engine 18, hit a case the spec 84 contract could not express. `_already_placed`
runs the invariant 8 probe: ask the store, then ask the exchange. When the store has never
recorded the `userref` and `open_orders()` *does* hold it — placed, then the process died
before engine 19 ran — the engine can tell the order exists and cannot describe it. The row
engine 19 records needs `qty` and `limit_price`, and `OrderState` carried neither, so engine 18
published `row=None` under `REASON_ENTRY_UNRECORDED` and nothing will ever cancel that order.

B refused to guess the two numbers, and was right to: this tick's approved quantity and this
tick's best bid are both wrong the moment equity or the book moves, and a fabricated
`limit_price` is a price nothing ever rested at, written into `orders` as though it had.

The operator approved the amendment on 2026-09-16: *an order that cannot be cancelled because
nothing recorded enough to identify it is an unmanaged exposure, and that is the failure
invariant 8 exists to prevent.*

### Why the contract was wrong in the first place, and it is a shape worth carrying

`OrderState` was designed as *what has happened to an order* — status, fill, price, fee, close
time — and not as *what the order is*. That reads correctly as long as the reader already knows
what it asked for, which is true for every consumer that placed the order itself and holds its
own `OrderRequest`. It is false for exactly one consumer: the one that is reconciling, which by
definition has no `OrderRequest` because that is what it lost. **A contract shaped around the
happy path's information is missing precisely the fields the recovery path needs**, and nothing
in my own lane could have shown it — every test of spec 84 constructed the state, so every test
already knew the answer.

### The design decision, and the one I did not take

`limit_price` is coupled to the order type the same way `OrderRequest`'s is: present for a
limit order, absent for a market one. `OrderRequest` enforces that against its `order_type`
field. `OrderState` has no `order_type`, and I deliberately did **not** add one.

Two readings were viable.

1. **Add `order_type` and enforce the coupling as a validator**, which is literally "the same
   shape `OrderRequest` already enforces".
2. **Let presence be the statement.** A market order has no limit price and a limit order
   always has one, so `limit_price is not None` is a total, lossless discriminator. A second
   field carrying the same fact is one more thing that can disagree — the same argument spec 85
   used to keep `pair` out of a `TradeRange` whose map key already carries it.

I took the second. The redundancy argument decided it: with `order_type` present, a state whose
`order_type` is `limit` and whose `limit_price` is `None` is a self-contradiction the model
would have to refuse, and a state with both fields agreeing is two copies of one bit.

**The cost, stated rather than hidden:** the coupling is now documented and not enforced. A
producer that forgets `limit_price` on a limit order is not refused. That is a real weakening
against `OrderRequest`, and if the lead wants it closed, `order_type: OrderType` plus a
`_price_matches_the_type` validator copied from `OrderRequest` is the one-line-each change —
but it changes B's five construction sites again, so it is a ruling and not mine to take.

### The gap this does *not* close, and B needs to know before building the row

The row engine 18 builds for engine 19 carries `userref`, `order_id`, `pair`, `side`, `intent`,
`order_type`, `oflags`, `status`, `qty`, `limit_price`, `filled_qty` and `placed_at`.
`OrderState` now supplies five of those twelve. The rest are **not** a second amendment, because
they are not unknowable the way the two numbers were:

- `pair` — engine 18 matched this order by a `userref` it derived from the candidate's pair, and
  a `userref` on a *different* pair already raises as a collision two branches above. The pair
  is the candidate's.
- `side`, `order_type`, `oflags` — structurally fixed for engine 18: invariant 8 makes every
  entry a post-only buy limit, and `order_types_named_in_this_module()` asserts by AST that this
  engine has no path that could place anything else.
- `intent` — the engine's own, this tick.
- `placed_at` — the only remaining unknown. Kraken's `OpenOrders` returns `opentm`, so it is
  fetchable, but it is not on `OrderState` and inventing it is the thing this amendment exists
  to stop. **If B needs it, ask; adding `opened_at` is the same one-line change.**

Filling the first four from what the engine structurally knows is not the fabrication the
operator ruled against. Substituting a *market observation* is. The distinction is worth naming
because the two look identical in a diff.

### Fix

`src/acsoe/clients/kraken/contracts.py`, `OrderState`:

- `qty: Money`, **required**, positive. Required rather than optional because every order has
  one — at the exchange and in the store — and an optional field would recreate exactly the
  ambiguity the amendment removes: a consumer could not tell "no quantity was recorded" from
  "no quantity exists".
- `limit_price: Money | None = None`, positive when present.
- A sixth coupling, only checkable now that `qty` is here: **`filled_qty` may not exceed `qty`**.
  A state saying otherwise would put a position the exchange never opened into the ledger.
- `state_dict()` renders both, money as strings.

`README.md` updated in the same change (`AGENTS.md`: keep docs true). Kraken returns both values
in `descr` on `OpenOrders` and `QueryOrders`, so the live client will actually have them.

### Mutations — ten run, ten killed, no survivors

`src/acsoe/clients/kraken/contracts.py` was copied byte-for-byte to the scratchpad before the
sweep; every mutation was written from that copy and **every restore wrote the original bytes
back and compared the sha256 in the same statement** (`assert
hashlib.sha256(TARGET.read_bytes()).hexdigest() == ORIG_SHA`). `git checkout --` was never used.
Pre- and post-sweep hash of the file on disk:
`fbd4c7468c325dcfff8c8e06fbe6ddf292fcd656f0ec548fe84eb5f30f4d2eba`.

Scoped to `tests/clients/kraken` — A's lane, 160 tests — so an incidental kill from another
lane could not be mistaken for coverage.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| A1 | `qty: Money` to `qty: Money = Decimal("1")` (required becomes optional) | killed | `test_a_state_without_a_qty_is_refused` |
| A2 | `_qty_is_positive` body reduced to `return value` | killed | `test_a_non_positive_order_quantity_is_refused[zero]`, `[negative]` |
| A3 | `_limit_price_is_positive` body reduced to `return value` | killed | `test_a_non_positive_limit_price_on_a_state_is_refused[zero]`, `[negative]` |
| A4 | over-fill bound `>` to `>=` | killed, 5 tests | `test_a_fill_exactly_equal_to_the_order_is_allowed` and 4 existing fill tests |
| A5 | `_fill_never_exceeds_the_order` reduced to `return self` | killed | `test_a_fill_larger_than_the_order_is_refused` |
| A6 | `state_dict` drops the `qty` key | killed | `test_the_state_crosses_state_with_money_as_strings`, `test_an_order_carries_the_quantity_and_price_it_was_placed_at` |
| A7 | `state_dict` renders `limit_price` as `None` unconditionally | killed | `test_the_state_crosses_state_with_money_as_strings` |
| A8 | `limit_price` becomes required on the state | killed | `test_a_market_order_state_has_no_limit_price`, `test_a_market_order_state_crosses_state_with_a_null_limit_price` |
| A9 | `qty: Money` to `qty: Decimal`, so a float is coerced instead of refused | killed | `test_a_float_qty_is_refused_rather_than_coerced` |
| A10 | `_qty_is_positive` returns `value.normalize()` | killed | `test_an_order_carries_the_quantity_and_price_it_was_placed_at` |

Two red messages, quoted:

```
A4  FAILED tests/clients/kraken/test_orders.py::test_a_fill_exactly_equal_to_the_order_is_allowed
    FAILED tests/clients/kraken/test_orders.py::test_a_filled_order_carries_its_price_fee_and_close_time
    FAILED tests/clients/kraken/test_orders.py::test_a_fill_without_an_average_price_is_refused
    FAILED tests/clients/kraken/test_orders.py::test_a_terminal_status_without_a_close_time_is_refused[filled]
    FAILED tests/clients/kraken/test_orders.py::test_the_state_crosses_state_with_money_as_strings
    5 failed, 155 passed

A10 FAILED tests/clients/kraken/test_orders.py::test_an_order_carries_the_quantity_and_price_it_was_placed_at
    1 failed, 159 passed
```

**A5 and A10 are the two that nearly were not written, and both say something.**

A5 is the *interesting* half of the over-fill pair, but A4 is the one that matters: `>=`
instead of `>` forbids every completely filled order, and it is killed by **five** tests
including four that existed before this amendment — because `a_filled_state()` fills the whole
order, as real orders usually do. Had I written only the refusal test and not
`test_a_fill_exactly_equal_to_the_order_is_allowed`, A4 would still have died, but by accident
of a fixture rather than by an assertion that says the boundary is deliberate.

A10 is the one that found a defect in my own test. The first version of
`test_an_order_carries_the_quantity_and_price_it_was_placed_at` asserted
`state.qty == Decimal("0.01000")`, and **`Decimal("0.01000") == Decimal("0.01")` is `True`** —
so a validator quietly normalising the quantum away would have passed. The assertion is now on
`state_dict()["qty"] == "0.01000"`, the rendered form, where the trailing zeros survive. This
module's own docstring says *the trailing zeros are the quantum*; an equality check on a
`Decimal` cannot see one.

### Construction sites outside A's lane — reported, not touched

`mypy --strict src/ scripts/` names all five source sites statically, which is worth knowing:
this amendment cannot land half-applied and stay quiet.

```
src\acsoe\clients\paper\broker.py:516: error: Missing named argument "qty" for "OrderState"
src\acsoe\clients\paper\broker.py:609: error: Missing named argument "qty" for "OrderState"
src\acsoe\clients\paper\broker.py:650: error: Missing named argument "qty" for "OrderState"
src\acsoe\clients\paper\broker.py:684: error: Missing named argument "qty" for "OrderState"
src\acsoe\clients\paper\broker.py:691: error: Missing named argument "qty" for "OrderState"
Found 5 errors in 1 file (checked 144 source files)
```

Plus three in `tests/engines/test_position_manager.py` (188, 203, 217), which mypy does not
check. Both files are B's. Full list, with the prose sites that now say something untrue, in the
report to the lead.

---

## THE `order_book` CONFIG SECTION — half one of two, 2026-09-16

Spec 80 owed this section and never landed it. Spec 96 step 2 reads
`order_book.depth`, and `config/default.yaml` has no `order_book:` key at all.
Lead-approved value: `depth: 10`.

### What landed, and what has deliberately not

**Half one only.** `OrderBookConfig` is on the model as `OrderBookConfig | None = None`
— optional. Nothing in this change writes `config/default.yaml`. The lead pastes the
YAML next; the tightening to required is one change after that.

The dance is the one in `code-standards.md` and it has now been run five times in this
project (`kraken.cache_ttl_s`, `backtest.embargo_bars`, the eight Phase 5 sections,
`training`, and this): `extra="forbid"` means a YAML key with no model field is refused
at load, and a **required** model field with no YAML key makes the committed config fail
to parse — taking `scripts/verify.py` and every test in every lane with it.

**Which way absence fails while the window is open, because it differs per shape and
this one is the safe shape.** `order_book` is a **section**, not a leaf, so
`Config.get("order_book.depth")` *raises* — the walk has to descend into the `None`.
A reader therefore fails closed. That is the `kraken.cache_ttl_s` shape and not the
`backtest.embargo_bars` one, where an absent *leaf* comes back as `None` and a careless
reader turns it into zero. It has its own test rather than a comment, because it is the
property that makes the window safe rather than merely short.

### The ceiling, and why it is not a Kraken number

`depth` is bounded `> 0` and `<= MAX_BOOK_DEPTH`, where `MAX_BOOK_DEPTH = 10`.

The obvious upper bound would have been one of Kraken's own — 500 for the REST `count`,
1000 for the v2 book subscription. **Both would have been exactly the thing `AGENTS.md`
forbids**: a remembered endpoint limit written into code, stale by assumption. And
neither is the constraint that actually matters.

The real one is in this repo. `engines/market_data_recorder/contracts.py` subscribes the
stream at `BOOK_DEPTH = 10` levels a side, and that constant is itself pinned to
`scripts/record.py`'s `DEFAULT_DEPTH` so the daemon's archive and the standalone
recorder's cannot diverge mid-history. Every recorded book frame therefore carries at
most ten levels a side — including `tests/fixtures/book_sample.jsonl`, which my own spec
86 cutter cut from those frames and which engine 9 is validated on. A larger
`order_book.depth` configures engine 9 to walk deeper than anything the feed delivers,
and the failure is silent in the worst direction: **the walk just ends early, the book
reads as thin, and nothing anywhere says the configuration was the cause.** A
`book_too_thin` refusal would then be one the committed fixture could never exercise —
a gate that looks configured and is untested. That is the lead's own reasoning for
choosing 10, turned into a bound rather than left as a note.

**Written out rather than imported, and the copy is paid for.** `platform/` sits under
`engines/` in the layering (`architecture-context.md` rule 0's direction), so importing
`BOOK_DEPTH` upwards into `config.py` would invert it. `config.py` imports nothing from
`acsoe` today except `platform.logging`, and I was not going to be the one to change
that for an integer. So the value is duplicated and
`test_the_book_depth_ceiling_agrees_with_the_feed` imports both and fails if they ever
disagree — the same trade `engines/market_data_recorder/contracts.py` already makes for
the state key it duplicates under contract rule 3. The test also asserts the bound is
*live* at that value, not merely equal to it: `BOOK_DEPTH` is accepted and
`BOOK_DEPTH + 1` is refused, so dropping the `le=` while leaving the constant in place
still goes red.

### The order the tests were written in, which is the point of the entry

**The `BAD_ORDER_BOOK_VALUES` table was written first and the interesting tests second.**
That is A's own Phase 5 lesson applied deliberately rather than remembered afterwards:
the `training` section shipped with a parse test and one good `num_leaves` story test and
**no rows in the bounds table**, and loosening `learning_rate` from `(0, 1)` to `[0, 1]`
broke nothing. Three of four fields had constraints nothing asked about. A field with no
row in the table is a field whose constraint is a claim.

Phase 6's rows live in their own table rather than in `BAD_VALUES`, because a row there
is loaded through `load_phase_5` and a section Phase 5 does not carry has nothing to
write the bad value into. `PHASE_6_SECTIONS`, `with_phase_6` and `load_phase_6` mirror
the Phase 5 machinery exactly, so the next section to land copies four lines.

Every row matches on the **constraint** message, never the key name: under
`extra="forbid"` a refusal always contains the key, so `match="depth"` would pass just
as happily against a model with no such field.

### Mutations — seven run, seven killed, no survivors

`src/acsoe/platform/config.py` was copied byte-for-byte to the scratchpad before the
sweep; every mutation was written from that copy and **every restore wrote the original
bytes back and compared the sha256 in the same statement**. `git checkout --` was never
used. Pre- and post-sweep hash of the file on disk:
`f993ae0b26f96bbada0fe605c375ad30da81e428e78d9f630bea5a1b8fa70f9a`.

Scoped to `tests/platform/test_config.py` — 176 tests.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| B1 | `depth` floor `gt=0` becomes `ge=0` | killed | `test_a_bad_order_book_value_is_refused_by_its_constraint[depth-0-…]`, `[depth--1-…]` |
| B2 | the `le=MAX_BOOK_DEPTH` ceiling is dropped | killed, 3 | the two over-ceiling rows and `test_the_book_depth_ceiling_agrees_with_the_feed` |
| B3 | `MAX_BOOK_DEPTH` drifts to 25 while `BOOK_DEPTH` stays 10 | killed, 3 | `test_the_book_depth_ceiling_agrees_with_the_feed` + `[depth-26-…]`, `[depth-500-…]` |
| B4 | the section lands **required** before the YAML | killed, 53 | `test_the_order_book_landing_is_in_flight_or_closed` and `test_default_yaml_loads_cleanly` |
| B5 | `OrderBookConfig` gets `extra="allow"` | killed | `test_the_order_book_section_refuses_an_unknown_key` |
| B6 | the absent section defaults to `OrderBookConfig(depth=10)` | killed | `test_a_missing_order_book_section_fails_closed_rather_than_reading_as_zero` |
| B7 | `depth` acquires `default=1`, so a deleted key is silently 1 | killed | `test_an_order_book_section_without_a_depth_is_refused` |

**B4 is the one worth reading, and not because it is the biggest.** Landing this section
required instead of optional takes **53 of 176 tests** in this file red, starting with
`test_default_yaml_loads_cleanly`:

```
acsoe.platform.config.ConfigError: configuration in config\default.yaml is invalid:
  - order_book: Field required
```

That is the whole justification for the two-halves dance, measured rather than asserted.
It is also a warning about scope: those 53 are one file. The same mutation takes every
test in every lane that reads the shipped config, which is why this must not be landed
required until the YAML is in.

**B7 is the one that nearly was not written.** I had a section test, a bounds table and a
missing-*section* test, and no test at all for a missing *key under a present section*.
Those fail in opposite directions: an absent section raises at the reader, while an
absent key under a section that parses is invisible everywhere — engine 9 starts, walks
whatever the default happens to be, and nothing is wrong anywhere a human would look.
The test was added because the mutation was written before the fix was called finished,
not because reading the code suggested it.

### For the lead — the exact paste, and what to do after it

```yaml
order_book:
  depth: 10                      # Levels a side engine 9 walks. Bounded by
                                 # market_data_recorder's BOOK_DEPTH: the stream is
                                 # subscribed at ten, so a deeper walk reads air.
```

Then step 3, one change, all in A's lane:

1. `order_book: OrderBookConfig | None = None` becomes `order_book: OrderBookConfig` in
   `src/acsoe/platform/config.py`, and the block comment above it goes.
2. `"order_book"` is appended to `LANDED_SECTIONS` in `tests/platform/test_config.py`,
   and `test_removing_a_phase_5_section_is_refused_at_startup` moves from
   `with_phase_5()` to `with_phase_6()` — it deletes each landed section in turn, and
   with `order_book` required the Phase 5 overlay no longer loads at all.
3. `test_the_order_book_landing_is_in_flight_or_closed` loses its `else` branch and
   becomes the closed assertion. It stays **green across the paste** and goes red only
   if the paste lands without the tightening — which is what it is for.

### One flake seen once, reported rather than buried

`test_a_bad_value_is_refused_by_its_constraint[models-anomaly_run_id-runs/2026-…]` failed
once, in one run of `pytest tests/platform tests/clients/kraken -q`, and has not reproduced
in six subsequent runs of the same command nor in the parametrisation run alone.

It is a **Phase 5 row this change does not touch**, and the most consistent explanation is
the shared working tree: that row loads through `complete_config_dict()`, which reads the
committed `config/default.yaml`, and three other agents are editing in this checkout
concurrently. A config that was transiently invalid for an unrelated reason raises
`ConfigError` with a *different* message, which is exactly a `pytest.raises(..., match=...)`
failure rather than a crash. Recorded because a flake nobody wrote down is a flake somebody
rediscovers, and because the lead's authoritative gate runs the whole suite at once.

---

## `OrderState.opened_at` — the amendment's last field, 2026-09-16

The lead's ruling on the two questions the amendment left open.

**Ruling 1: keep presence as the discriminator.** No `order_type` on `OrderState`.
The weakening it leaves — nothing refuses a limit order whose `limit_price` went
missing — is closed **at the consumer that knows the answer** rather than in the
model: engine 18 asked for a post-only buy limit, so a state with no `limit_price`
is the exchange contradicting the placement rather than a market order, and engine
18 refuses to record it. That is the better place for it and it is worth naming why:
the model sees one order at a time and has no idea what was asked for, while the
placer has the `OrderRequest` in hand. **A coupling belongs wherever both halves of
it are visible**, which for this one is not the boundary.

**Ruling 2: add `opened_at: int | None`.** My own analysis was the argument for it.
With `qty` and `limit_price` in, `placed_at` was the *only* value engine 18 could not
fill from what it structurally knows, and without it the unrecorded-order row still
could not be built — which was the entire point of the amendment.

### What landed

`opened_at: int | None = None`, microseconds since the epoch like `closed_at` and
`fetched_at`, from Kraken's `opentm` on `OpenOrders`. Rendered in `state_dict()`.

**Optional, and `qty` being required is not inconsistent with it.** Every order has a
quantity that something knows; a placement time is a thing only the exchange can
report, and it does not always. A required field here would force a consumer to
invent one — the fabrication the whole amendment exists to stop. Absent means *the
exchange did not say*: not now, not zero. Engine 18 keeps its existing fail-closed
answer in that case (no row, `entry_unrecorded_at_exchange`, `userref` published), so
the gap is now exactly the case the exchange itself cannot answer, which is as far as
this can honestly be taken.

**Coupled to nothing, deliberately — it is not the mirror of `closed_at`.** A resting
order has an open time and no close time, and that is the ordinary state of the entry
engine 21 watches. The one rule is a seventh coupling: **an order may not close before
it opened**, when both are known. Equality is allowed, and that is not pedantry — in
paper the same injected clock reading stamps both, so a bound written `<=` would
refuse every simulated marketable order. Mutation C3 is exactly that bound and exactly
one test objects.

### Mutations — six run, six killed, no survivors

Byte copy taken again after the previous sweep (the file had moved), every mutation
written from it, and **every restore wrote the original bytes back and compared the
sha256 in the same statement**. No `git checkout --`. Pre- and post-sweep hash:
`7a050f53e7591ee241a222c6001c8a4d5e4ffaae602bcb6b83ed1096a31d7656`. Scoped to
`tests/clients/kraken`, 165 tests.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| C1 | the `opened_at` field is removed | killed, 17 | `test_an_order_carries_when_it_opened` and every `a_state` caller, via `extra="forbid"` |
| C2 | `state_dict` drops `opened_at` | killed, 3 | `test_an_order_carries_when_it_opened`, `test_an_order_whose_open_time_the_exchange_did_not_report_is_still_valid`, `test_the_state_crosses_state_with_money_as_strings` |
| C3 | the ordering bound refuses equality too (`<` becomes `<=`) | killed, 1 | `test_an_order_that_opened_and_closed_in_the_same_microsecond_is_allowed` |
| C4 | the ordering check is removed | killed, 1 | `test_an_order_that_closed_before_it_opened_is_refused` |
| C5 | `opened_at` becomes required | killed, 23 | `test_an_order_whose_open_time_the_exchange_did_not_report_is_still_valid` and every state built without one |
| C6 | `opened_at` is coupled to a terminal status, mirroring `closed_at` | killed, 2 | `test_a_resting_order_may_know_when_it_opened`, `test_an_order_carries_when_it_opened` |

**C6 is the one that earns its place.** C1 and C5 are killed by seventeen and
twenty-three tests, almost all of them incidental — they die because `a_state()`
stops constructing, not because anything asserts the property. The *deliberate*
assertion in each case is a single test, and the honest reading of a 23-test kill is
that twenty-two of them prove the fixture works. C6 is the opposite shape: it is a
plausible design somebody could add later in good faith (make `opened_at` the mirror
of `closed_at`, since they look like a pair), it breaks only two tests, and one of
those exists purely to say the coupling is deliberately absent. A field that is
coupled to nothing needs a test saying so, or the next reader will add the coupling
and nothing will stop them.

### One ruff finding worth a line

The first version of the ordering check was a nested `if` and `ruff` refused it
(`SIM102`). Flattening it with `and` breaks mypy's narrowing — `self.closed_at <
self.opened_at` on two `int | None` — and the obvious escape is a `type: ignore`. It
is not needed: binding `opened, closed = self.opened_at, self.closed_at` first gives
mypy locals it can narrow, and the single `and` chain then satisfies both tools with
no suppression. **A `type: ignore` added to satisfy a linter is a suppression bought
with a real loss of checking**, and in this file the thing being unchecked would have
been a comparison on a value that can be `None`.

---

## `order_book` half three — the tightening, 2026-09-16

### The tripwire fired on its own, which is the point of writing it first

I was in `clients/kraken/contracts.py` adding `opened_at` when the lead pasted the
YAML. Nobody told me. The next routine gate run came back with two reds, and one of
them was `test_the_order_book_landing_is_in_flight_or_closed` saying in its own
message that half two had landed and half three had not. **A tripwire written before
the event it is waiting for costs one branch and replaces a thing somebody has to
remember to check.** The Phase 5 landing needed a message from the lead to close;
this one announced itself.

### What landed

1. `order_book: OrderBookConfig | None = None` becomes `order_book: OrderBookConfig`.
2. `"order_book"` appended to `LANDED_SECTIONS`.
3. `test_the_order_book_landing_is_in_flight_or_closed` loses its branch and becomes
   `test_the_order_book_landing_is_closed_and_the_section_is_required`.
4. `test_a_missing_order_book_section_fails_closed_rather_than_reading_as_zero`
   **deleted**, with the reason left in place of the body. It asserted that an absent
   *section* makes `Config.get("order_book.depth")` raise rather than answer `None` —
   true, and unreachable now that the field is required, because such a config no
   longer loads at all. What replaced it is stronger:
   `test_removing_a_phase_5_section_is_refused_at_startup[order_book]`, where the
   process does not start and the refusal names the section. A test whose premise
   cannot occur is a claim nobody is checking.

### Two mutations survived, and the reason corrected a comment I had already written

| # | Mutation | Verdict |
|---|---|---|
| D1 | `order_book` goes optional again | killed, 3 — the landing test, the Phase 5 landing test, and `test_removing_a_phase_5_section_is_refused_at_startup[order_book]` |
| D2 | `"order_book"` dropped from `LANDED_SECTIONS` | killed, 1 — the landing test's third assertion |
| D3 | the deletion test reverts from `with_phase_6()` to `with_phase_5()` | **survived — equivalent** |
| D4 | the deletion test counts missing sections instead of naming them | **survived — equivalent** |

Byte copies of both files taken before the sweep; every restore wrote the original
bytes back and compared the sha256 in the same statement. No `git checkout --`.
Hashes: `config.py` `1422df60…`, `test_config.py` `23eb5003…`.

**Why D3 and D4 survive, and it is not the reason I wrote in the comment.** When I
moved `test_removing_a_phase_5_section_is_refused_at_startup` from `with_phase_5()`
to `with_phase_6()`, I wrote that the Phase 5 overlay could no longer load with
`order_book` required, so every case would refuse for `order_book` rather than for
the section deleted. **That is false.** `complete_config_dict()` starts from the
*shipped* `config/default.yaml`, so every section the lead has ever pasted is already
in the base and the phase overlays only pin values on top of it. The Phase 5 overlay
carries `order_book` for a reason that has nothing to do with Phase 5.

So the move is defensive rather than necessary, and the list assertion with it. Both
are kept — the failure they guard is real and silent if the base ever stops carrying
a required section — but they are recorded as **equivalent mutants under the current
fixtures**, not as coverage, and the comment in the file now says so with the
measurement beside it.

**The part of that story that was real, and it cost a mutation to find.** I first
strengthened the deletion test to `match=rf"{section}: Field required"`, reasoning
that naming the section is the strong assertion here rather than the weak one. It
survived D3. Pydantic reports **every** missing field, so the deleted section's line
is in the message whether or not another section's line is sitting next to it, and
`re.search` finds it either way. **A `match=` pattern is a substring test on a
multi-error message and can never say what else went wrong.** Comparing the whole
extracted list is the only form that can. That generalises past this file: every
`pytest.raises(..., match=...)` in this project is a substring test, and wherever the
property is "*and nothing else*", `match=` cannot express it.

### Half three's own gate

`pytest tests/platform tests/clients/kraken -q` — 485 passed, 1 skipped (the
pre-existing Windows byte-range skip). `ruff` clean. `mypy --strict` clean on 147
source files, B's `broker.py` having landed its `qty` sites in the meantime.
