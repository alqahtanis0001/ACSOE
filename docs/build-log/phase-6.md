# Build log — Phase 6: Decision and execution

Written by the agents as work happens, per `context/script-rules.md`.
Record every non-trivial problem and its fix. This cannot be reconstructed later.

The per-agent files are `docs/build-log/phase-6/{lead,a-platform,b-store,c-interface}.md` and
they remain exactly as the agents wrote them. This file is the consolidation, made in
preparation for the phase close; **the phase is not closed** until the operator rules.

## Phase 6 summary

*Written by the lead, 2026-09-18, in preparation for the close. **The phase is not closed.** Its
gate is green, but the operator asked to see the first paper trade before ruling on the close,
and has not yet ruled. Nothing below should be read as the phase being finished.*

**What this phase was for.** Phases 0 to 5 built a system that could decide *not* to trade: the
data spine, the economics gates, the memory, and the models. Phase 6 builds the half that acts.
Engine 16 checks the decision. Engine 18 places an order. Engines 21 and 22 watch a position and
exit it. A paper broker simulates the fills without touching an exchange. A system that only
refuses can be wrong in ways that cost nothing. One that places orders can lose money, can fail to
stop, and can report a position closed while an order is still live. So the phase's measure of
success was not "a trade happens". It was that **one complete trade can be followed end to end, and
every row it leaves behind reconciles to the last digit** with figures recomputed independently from
the market the test scripted.

**Built.** Engines 9 `order_book`, 14 `adaptive_router`, 16 `decision`, 18 `execution`, 21
`position_manager` and 22 `exit`; the paper broker and its ledger in `src/acsoe/clients/paper/`;
engine 19 extended to record everything the new engines publish; and fourteen executable exit
criteria (twelve specific to this phase, plus the document check and the toolchain check every
phase carries).

- **Agent A — platform.** The order surface every engine uses to place, cancel and query an order,
  identical in paper and live, with the live half refusing every call until Phase 8 (spec 84). The
  per-minute trade ranges engine 3 publishes, which are what a fill and a barrier touch are decided
  on (85). The broker's wiring in paper mode only, and the tool that cuts a committed order-book
  sample from the live recording (86). The rehearsal that drove engines 18, 21 and 22 through real
  orchestrator ticks and found the phase's two worst defects (87). The last stale descriptions of a
  paper-mode fallback that no longer exists (109).
- **Agent B — store and trading.** The paper broker (88); engine 11 refusing a second position or
  resting entry on one pair (89); engines 16, 18, 21 and 22 (90–93); the rehearsal of engines 9 and
  14 (94); the broker's balance counting every fill it has executed (103); engine 11's balance
  fallback removed (106); and the smaller clean-ups and the exit-cycle inputs (108, 110–113, 119).
- **Agent C — interface and models.** Engine 8's `is_buy` made absent on a refusal (95); engines 9
  and 14 with their committed fixtures (96, 97); engine 19 recording the new rows (98, 104, 114);
  operator-facing prose for every reason code, walked by a test in both directions (99, 120); the
  twelve Phase 6 criteria (100, 105, 107, 115, 118), which sit beside the two every phase carries; and the console showing an open position live (101).
- **The lead.** The operator's rulings into the authority documents (80); the kill switch's
  completion flag made to accept only a boolean `True` (81); registration of the six engines (82);
  the skeptic-cap ruling recorded (83); `context.previous_now`, so an engine can measure "since the
  last tick" without guessing; and the removal of a default on the equity row's cash source.

**What the first paper trade shows, and what it does not.** The trade is BTC/USD. It passes all
eight gates, rests as a post-only buy at the best bid rounded down onto the exchange's grid, fills
at its own limit, and is watched minute by minute. It exits as a market sell when a trade crosses
its target, and it ends with every order, position, trade and equity row matching an independent
recomputation exactly. The stop and timeout legs do the same. The written walk-through is in
`docs/build-log/phase-6/first-paper-trade.md`. **It proves the machinery, not the economics.** The
market is scripted and the models are trained on a constructed series. The fees are the fake
exchange's "tier 3", chosen because at Kraken's reference tier-1 fees nothing can clear the cost
gate at the current barriers. That limitation is the project's central economic finding so far, not
a defect. One correction to how the criteria describe it is open with the operator (S3 of the night
of 2026-09-18). Every criterion's message quotes Kraken's reference friction of about 0.65%, but the
fake's tier 3 actually charged 0.30% in fees, and the run's friction was 0.308%.

**Problems of note.** Four defects were found that would each have shipped as working code, every
test green:

1. **Every paper trade would have frozen the account.** On the tick an entry filled, the paper
   broker's cash did not yet include the fill while engine 21 already counted the new position, so
   equity counted the same money twice. The drawdown breaker read a 40% loss the next minute and froze
   the system. Found by A's rehearsal. The fix is the operator's amendment to invariant 2: the broker
   is the authority on its own cash.
2. **A tick on which an engine crashed was not recorded at all**, when invariant 12 says that is the
   tick most worth recording. Two contract rules were each reasonable alone and together lost the
   tick. The contract was wrong, not only the code, and both were changed.
3. **The equity row on an exit tick described no moment that ever existed.** It had cash from before
   the sale, a position value from before the sale, and a position count from after it. It read zero
   open positions beside a non-zero position value, and on a winning trade it raised the account's
   recorded peak to a figure the account never held. Found by the first criteria to run the
   registered chain end to end. The fix records which moment the cash describes (`cash_source`).
4. **The verification script itself died writing the minus sign its own style rules require.**
   On Windows it printed seven criteria, never ran the other six, and exited with the same code
   a genuine failure returns.

**Findings of method, recorded as findings rather than folded into rules.** A mutation-testing blind
spot with a worked example: engine 14's truncation check fired falsely on exactly one row count no
test author would choose, and a colleague reading the diff found it. A test that went green while
asserting nothing, because it called the very helper that had just been given the value it checked.
A prose key with no producer, because a specification said it already existed and nothing checked.
And the seed data the console had displayed since Phase 1 turned out to use a refusal vocabulary no
engine could emit.

**Verify output.** The close preparation re-gated phases 0 to 6 in order on a quiet tree at
`98c0485`, every one exit 0 (phase 0 7/7, 1 10/10, 2 9/9, 3 9/9, 4 10/10, 5 14/14).
The Phase 6 gate, verbatim:

```
ACSOE verify - phase 6
repo: C:\Users\saad2\Documents\GitHub\ACSOE

PASS    docs_vocabulary                                     14 files scanned, 12 retired terms, no hit
PASS    toolchain_green                                     pytest, mypy --strict and ruff all green (python.exe) - pytest `3314 passed, 2 skipped, 2 warnings in 1865.52s (0:31:05)` - full output: C:/Users/saad2/Documents/GitHub/ACSOE/logs/verify/toolchain_green/20260918T124149_478932-pytest-attempt1.log
PASS    paper_trade_round_trip_target                       BTC/USD entry 1690626088: a post-only buy of 26.26015939 at 126.9, placed on the bar close past all 8 registered gates (data_guard, safety, scout, anomaly, cost, risk, skeptic, decision), filled at its limit on the next tick, watched for 3 ticks, then a trade at 130.757 crossed the target 130.707 the minute before 1715983501; it exited at the target when engine 22 sold 26.26015939 as a taker at 130.757. Entry fee 3.6656556492501, exit fee 6.524029356580637 and realised 91.095749761399263 were recomputed from the pinned book and engine 1's fee tier, and the orders, positions, trades and equity rows engine 19 wrote match them exactly; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers
PASS    paper_trade_round_trip_stop                         BTC/USD entry 1690626088: a post-only buy of 26.26015939 at 126.9, placed on the bar close past all 8 registered gates (data_guard, safety, scout, anomaly, cost, risk, skeptic, decision), filled at its limit on the next tick, watched for 3 ticks, then a trade at 124.9465 crossed the stop 124.9965 the minute before 1715983501; it exited at the stop when engine 22 sold 26.26015939 as a taker at 124.946. Entry fee 3.6656556492501, exit fee 6.234093562771586 and realised -61.212100660081686 were recomputed from the pinned book and engine 1's fee tier, and the orders, positions, trades and equity rows engine 19 wrote match them exactly; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers
PASS    paper_trade_round_trip_timeout                      BTC/USD entry 1690626088: a post-only buy of 26.26015939 at 126.9, placed on the bar close past all 8 registered gates (data_guard, safety, scout, anomaly, cost, risk, skeptic, decision), filled at its limit on the next tick, watched for 61 ticks, then the clock reached its timeout at 1716026461 with neither barrier traded; it exited at the timeout when engine 22 sold 26.26015939 as a taker at 126.925. Entry fee 3.6656556492501, exit fee 6.332834388093925 and realised -9.341986052594025 were recomputed from the pinned book and engine 1's fee tier, and the orders, positions, trades and equity rows engine 19 wrote match them exactly; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers
PASS    unfilled_entry_cancels_without_chasing              BTC/USD entry 1690626088, a post-only buy of 26.26015939 at 126.9, rested with nothing trading below it and was cancelled 300s after placement, on the first minute tick at trading.entry_unfilled_window_s (300s) and not before. Across 14 ticks to the next bar close the broker was asked for that one order and that one cancel and nothing else - no market order and no second entry - and afterwards nothing is open at the broker or in the store; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers
PASS    triggered_stop_holds_on_data_guard_block            BTC/USD position pos-1690626088: a trade at 124.9465 touched the stop 124.9965 on a tick engine 4 blocked for a crossed quote, and engines 21 and 22 placed no exit - no trigger, no order at the broker - with hold_reason 'data_guard_blocked' published and stored on the position. The operator's close_all on the next tick, with data_guard still blocking, sold the same position as a taker at 124.296 (outcome liquidation, realised -78.248772966735036, every row reconciled), cleared the hold, and the orchestrator cleared close_intent and consumed the command; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers
PASS    escalation_completes_during_outage                  Positions: engine 4 blocked 16 consecutive minute ticks on a crossed quote while the balance and AssetPairs fetches failed (engine 1: asset_pairs is unavailable (injected by the fake)); engine 17 wrote close_all on blocked tick 16 (1715984221) and not before (safety.max_consecutive_data_blocks 15); on the next tick, still blocked and still failing, engine 22 sold pos-1690626088 as a taker at 126.725 using the retained AssetPairs past its TTL (fallbacks_used [asset_pairs_last_known_good], realised -14.584039070025825, every row reconciled), engine 19 wrote no equity row while the balance was unknown, and the orchestrator cleared close_intent and consumed engine 17's command. Resting entries: a resting entry: at the committed config a safety escalation can never find one, because trading.entry_unfilled_window_s (300s) is shorter than the 16 blocked ticks of 60s it takes to escalate, and engine 21 cancels a stale entry during the hold - so the cancel path is proven through an operator close_all: entry 1690626088, placed 60s earlier and inside its 300s window, was cancelled at the broker on the close_all tick while data_guard blocked and the same two fetches failed, engine 17 wrote nothing, and the command was consumed on that tick; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers
PASS    console_shows_position_live                         BTC/USD position pos-1690626088: the console read engine 19's row at the fill mark 126.9, and after one tick at 127.4 it renders 127.4 with the unrealised PnL moved by exactly 13.130079695 on 26.26015939 - live, not a snapshot. Past console.stale_after_ms (120000ms) the same row reports stale with its age '4m 00s' beside it, and fresh before it. On the tick engine 4 blocked for a crossed quote the row shows the hold as "Exits are paused while this tick's market data is rejected; the position is still watched" and never the code 'data_guard_blocked'. Signed percentages (+0.39% and −1.82%), a real U+2212, and the entry price at exactly this pair's 1 AssetPairs decimal(s), which is where engine 18 put it. The console placed nothing - the broker saw 1 request(s) before and after - and its connection refused a write: attempt to write a readonly database. Derived thresholds render at the precision they were computed to and the console does not round them - ui-context.md rule 4 as amended 2026-09-18: target '130.707' (3dp), stop '124.9965' (4dp), unrealised '−60.50340723456' (11dp). Rounding them at write time was available and was rejected, because research/labelling.py computes its barriers the same unrounded way and stop_price is the trigger engine 21 compares against. The mark renders '124.596' (3dp) where AssetPairs gives this pair 1 - NOT a verdict on engine 3: this criterion pinned that bid itself, so here it measures its own harness. The archive says the exchange is on the grid (783 recorded BTC/USD book prices, all 1dp); at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers
PASS    order_book_slippage_on_recorded_book                ADA/USD (thin): 10 of 10 recorded bid levels walked to sell the whole 5000.00 USD balance, fill 0.1946473901839433686160148110 against best bid 0.194674, slippage 0.0001366891113175430924786514892; BTC/USD (deep): 4 of 10 recorded bid levels walked to sell the whole 5000.00 USD balance, fill 75726.85619614271459554707421 against best bid 75731.8, slippage 0.00006528042192692375531712952815. Each was recomputed from tests/fixtures/book_sample.jsonl and equals engine 9's payload exactly, and engine 9 blocked neither candidate tick. The chain was driven through the registered engines so that it reaches engine 9; the walk itself reads no fee; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers
PASS    adaptive_router_weights_on_fixture                  on tests/fixtures/leaderboard_sample.json - fabricated rows, so this is a property of the fixture and not of any trained model - engine 14 weighted {'train-20260913T120000-aaaa': 0.8181818181818181, 'train-20260913T120000-bbbb': 0.18181818181818196, 'train-20260913T120000-cccc': 0.0}, equal to the weights recomputed from the file: the mean over each version's folds of max(0, 1 - brier / base_rate_brier), normalised, with the older duplicate of a (version, fold) dropped, the other family (['some_other_family']) left out, and a version with no edge at zero. The chain was driven through the registered engines so that it reaches engine 14, which sits after the cost gate; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers
PASS    paper_equity_continuous_across_fill                 equity 5000.00 on cycle 2 and 4996.3343443507499 on the fill tick, cycle 3: it moved -3.6656556492501. The fill's own cost is 3.6656556492501: fee 3.6656556492501 + 26.26015939 x |mark 126.9 - fill 126.9|, recorded for BTC/USD entry 1690626088 (notional 3332.414226591); at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers
PASS    equity_row_never_values_positions_it_does_not_hold  all 8 equity rows of a round trip (4 with a position open, including the fill tick, the exit tick and the tick after it) carry a positions_value of zero whenever they count no open position; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers
PASS    recorded_book_agrees_with_recorded_pair_decimals    every recorded price sits at or inside its recorded pair_decimals - BTC/USD 783 recorded prices, the widest at 1dp, against the recorded pair_decimals 1. Coverage: 1 compared of the 5 pairs the two fixtures carry between them, 4 not compared - ADA/USD (881 recorded prices, recorded in book_sample.jsonl, not declared in asset_pairs.json); ETH/BTC (declared in asset_pairs.json, not recorded in book_sample.jsonl); ETH/USD (declared in asset_pairs.json, not recorded in book_sample.jsonl); SOL/USD (declared in asset_pairs.json, not recorded in book_sample.jsonl). Read from the two committed fixtures alone, and no precision is inferred from a price. book_sample.jsonl was cut from kraken_v2__msi__2026-09-16.jsonl over [2026-09-16T00:17:06.100000Z, 2026-09-16T00:17:36.100000Z).

14 criteria: 14 PASS, 0 FAIL, 0 PENDING
Phase 6 is green: every criterion PASS, zero PENDING.
```

**Deliberately deferred.**

- **To Phase 7:**
  - the Dissimilarity Index's fit and score at full size (spec 102, parked by the operator)
  - the execution-offset bandit (Phase 6 places every entry at the best bid)
  - the skeptic's 13-fold training cap, with Finding 1 of Phase 5 to be re-measured on the capped
    skeptic before it is cited
  - engine 7 skipping a pair that already holds a position
  - the console's scan tally
- **Open with the operator at the time of writing:**
  - Q1: engine 22 and the retained balance (stopped: reading it changes behaviour)
  - Q2: the `AssetPairs` fixture turned out to be invented test data, not a recording
  - Q3: widening spec 118 from 1 pair of 5 (scheduled, not started)
  - S3: the tier sentence in every criterion message
  - the findings F-new-1 to 4 of the night of 2026-09-18

The phase close itself, and marking the phase green in the tracker, wait on the operator.

## Consolidated from the per-agent logs

Each section below is the named file, verbatim. Headings inside them keep their own levels.

## The lead

*Verbatim from `docs/build-log/phase-6/lead.md`.*

# Build log — Phase 6 — lead

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

### Four things found while writing the Phase 6 specs, before any code

**Agent:** Lead · **Task:** specs 80 to 102 · **Date:** 2026-09-16

Recorded at diagnosis, per rule 1. None is fixed; three need the operator and one is a spec.

**1. The fill simulator cannot live under `engines/execution/` without breaking two rules.**
*What happened.* The operator ruled the simulator B's, under `engines/execution/`, from my
reconnaissance finding that it had no owner. Writing its spec, I followed a resting post-only entry
through its life: it is placed by engine 18 on a bar tick and fills on some *later* tick, which only
the manage chain sees — engine 21 — and exits fill in engine 22. *Why.* Contract rule 3 forbids 21
and 22 importing `engines/execution/`, and `architecture-context.md` says mode differences live only
in the client layer. The reconnaissance report named the owner gap and did not follow the order far
enough to see the import gap; that is my miss, and the ruling was made on it. *Not fixed* — put to
the operator with a recommendation (a B-owned paper broker in `clients/paper/` wrapping
`clients.kraken`), spec 88.

**2. Invariant 6's "one open position per pair" is enforced nowhere.** *What happened.* `grep`
across `src/` finds no per-pair check; engine 11 counts open positions against
`max_concurrent_positions` without asking which pair. *Why it has been invisible.* Nothing could
open a position until this phase, so no test could reach it. *Fix, to be built:* spec 89, a refusal
in engine 11 that lands before engine 18 does.

**3. `Orchestrator._flag` reads a non-boolean truthy value as "finished".** *What happened.*
`bool(payload.get(field, False))` turns the string `"false"` into `True`, so a publisher that
serialised `entry_orders_cancelled` as text would clear `close_intent` with orders still resting.
*Why it matters now.* Until 21 and 22 exist the flags are always absent and the absent case is the
only one exercised. *Fix, to be built:* spec 81 — the test first, observed red, then `is True`.

**4. Nothing implements invariant 2's "adjusted by simulated fills", and the unadjusted balance
double-counts.** *What happened.* Engine 11's paper fallback uses `paper.starting_balances` as a
constant, and engine 19's equity is fetched cash plus positions value. *Why.* A simulated fill never
touches either source, so after one paper entry the cash is unspent: sizing allocates it again and
equity counts it twice. With real credentials the fetch succeeds and returns the real account's
cash, which no paper fill spends either. *Not fixed* — a money rule, put to the operator with a
recommendation (paper mode always reads a ledger of starting balances adjusted by recorded fills),
spec 88.

**Checked and found sound, so the list above is not mistaken for coverage:** engine 19 already reads
the fields 21 and 22 were always going to publish (`positions`, `orders`, `positions_value`,
`unrealised_pnl`, `hold_reason`, `closed_trades`), and fails to *nothing* rather than to a zero when
they are absent; the `close_intent` spy tests in `tests/core/test_orchestrator.py` build their own
`Chains`, so registering 21 and 22 cannot silently remove their absent case — what they do not cover
is a present payload (finding 3, spec 81); `TradeOutcome` already carries `liquidation`; the store
already exposes `resting_orders(intent=...)`, `order_by_userref` and `open_positions`, so specs 89
and 92 need no migration.

### The kill switch could be cleared by the string "false"

**Agent:** Lead · **Task:** spec 81 · **Date:** 2026-09-16

**What happened.** `Orchestrator._clear_close_intent_if_finished` clears `close_intent` when both
manage-chain flags are true, and it read them through
`bool(payload.get(field, False))`. Written out as a test, four of seven present-but-not-`True`
values clear a liquidation:

```
FAILED tests/core/test_orchestrator.py::test_only_the_boolean_true_clears_the_intent[false]
FAILED tests/core/test_orchestrator.py::test_only_the_boolean_true_clears_the_intent[0_0]
FAILED tests/core/test_orchestrator.py::test_only_the_boolean_true_clears_the_intent[1]
FAILED tests/core/test_orchestrator.py::test_only_the_boolean_true_clears_the_intent[true]
4 failed, 33 passed in 0.35s
```

`'true'` is in that list as a control and `'false'` is the one that matters: `bool("false")` is
`True`, so a publisher that serialised `entry_orders_cancelled` as text would clear the intent
**while entry orders were still resting on the book**, the orchestrator would mark the `close_all`
row consumed, and the kill switch would report a liquidation that had not happened. `[]`, `{}` and
`0` were already safe, which is why the hole is easy to miss: the coercion is right for three of
the seven shapes and silently wrong for the other four.

**Why it has been invisible.** Until Phase 6 the manage chain is engine 19 alone, so
`state["position_manager"]` and `state["exit"]` are always **absent**, `.get` returns the
default `False`, and only the absent branch has ever executed. Registering 21 and 22 makes the
payload always present — the branch stops being dead on exactly the change that gives it
something to be wrong about. The existing tests cover absent, and absent cannot stand in for
present: `engine-contracts.md` says these fields are booleans, so nothing had asked what happens
when a publisher's shape changes.

**Fix.** `_flag` accepts only the boolean `True` (`payload.get(field) is True`). Anything else —
absent, `False`, `None`, a string, a number — reads as *not finished*, the intent survives, the
command stays unconsumed and the manage chain retries next tick. That is the same fail-closed
default the gates use and the one `engine-contracts.md` already states for these two fields:
"absent or false always means 'not finished', never 'finished'".

**Consequence.** Seven-shape parametrised test plus a raised engine 21 (contract rule 7 gives
`ERROR` with `data={}`, which is present-and-empty, a shape the absent case also cannot produce).
B is told, because engines 21 and 22 must publish real booleans rather than anything
string-shaped; a publisher that sends `"true"` now fails to finish a liquidation loudly instead
of finishing one falsely.

**Mutation proof for the fix above.** Three mutations of `_flag`, each applied by an anchor whose
occurrence count was asserted to be exactly one, each restored from a byte copy taken before the
first mutation with the sha256 compared in the same statement (`restored byte-identical: True` on
all three). Scope `tests/core`, which owns the code.

| Mutation | Result | Killed by |
|---|---|---|
| A — a missing payload reads as finished | 4 failed, 49 passed | `test_close_all_sets_intent_and_freezes`, `test_close_intent_survives_when_a_flag_is_missing`, `test_close_all_is_not_marked_consumed_on_the_claiming_tick`, `test_an_interrupted_close_all_is_re_applied_before_the_first_tick` |
| B — a **missing field** reads as finished | 1 failed, 52 passed | `test_close_intent_survives_when_the_position_manager_raised` **only** |
| C — the original `bool()` coercion | 4 failed, 49 passed | `test_only_the_boolean_true_clears_the_intent[false, 0, 1, true]` |

**B is the answer to the question spec 81 was written to ask.** One test kills it, and that test
did not exist an hour ago: before today, a present payload that simply lacked the field read as
*finished* and **nothing in the suite objected**. The absent-payload case (mutation A) is killed
four times over and cannot stand in for it, because it exits at the `isinstance` branch above.
That is the shape the operator predicted — a fail-closed default that stops being exercised when
the absent case stops occurring — arriving one branch lower than expected: not at the payload, at
the field inside it.

### Engine 19 records equity as cash alone when a position cannot be marked

**Agent:** Lead · **Task:** spec 98 review, raised by B · **Date:** 2026-09-16

**What happened.** B asked me to confirm that engine 19 treats an absent `positions_value` as
"nothing to record" rather than defaulting, because spec 92 has engine 21 publish it **absent**,
never zero, on a tick where no mark could be taken. It does not. `MemoryEngine._write_equity`
reads it through `decimal_field(manager or {}, POSITIONS_VALUE_FIELD, ...)`, and `decimal_field`
returns **`Decimal(0)`** for an absent field. The equity row is still written; only an absent
`balances` skips it.

**Why it matters, and why it is invisible today.** `equity = cash + positions_value`. With an open
position and no mark, the row records equity as the cash alone — the position's entire value
missing from one tick of the series. Engine 17's drawdown is
`(peak_equity − equity) / peak_equity` against a peak read from the store, so a single unmarked
tick on a fully invested account is a drawdown approaching 100%, which trips
`safety.max_drawdown_pct` (0.10) and freezes the account over a missing quote. It has been
unreachable for exactly the same reason as the `_flag` defect: no engine has ever published a
`position_manager` payload, so the zero default has only ever been applied to an account with no
positions, where zero is the right answer.

**Fix (C's, spec 98 gains it).** Distinguish *no positions* from *positions that could not be
marked*: engine 19 already calls `store.count_open_positions()` for the snapshot, so when that
count is non-zero and `positions_value` is absent, write **no** equity row and name it in
`equity_skipped_reason`, exactly as an absent `balances` already does. When the count is zero, a
`positions_value` of zero is correct and the row stands. `unrealised_pnl` takes the same treatment
for the same reason.

**Consequence.** The general shape, which is the third instance this phase: **a default that is
correct in the only state the system has ever been in.** `_flag`'s `bool()` was right for the
absent payload, `decimal_field`'s zero is right for a flat account, and engine 11's
`max_concurrent_positions` check was right while nothing could open a position. All three become
wrong on the first tick that holds a position, which is what Phase 6 is for.

### An engine can measure an instant but not an interval, and the overshoot fell in neither

**Agent:** Lead · **Task:** spec 85's question, raised by A · **Date:** 2026-09-16

**What happened.** A built engine 3's per-tick trade ranges and stopped to report what it could
not express: `since_ts` had to be `context.now − timeframes.loop_tick_s`, because an engine is
stateless across cycles, `state` is fresh every tick, and `EngineContext` carried nothing about
the previous one. A named the precedent honestly — `bar_closed_on` has used the same device since
Phase 2 — and then named the difference, which is the part that matters.

**Why the precedent does not carry.** `bar_closed_on` asks about an **index**: which decision bar
this tick falls in. A late loop still lands in some bar and the question still answers once. A
**range** is an interval, and `now − loop_tick_s` is the previous tick only in a loop that ran on
time. Overshoot by four minutes and the interval starts four minutes after the previous tick
ended: every trade in that gap is inside no range any engine ever published. Engines 21 and 22
decide a stop touch from exactly those ranges, so the missed window is a missed stop — silent, on
real money, on precisely the ticks where the machine was busy, which is when a market is moving.
Nothing would have gone red: each range is internally consistent and the gap is between them.

**Fix.** `EngineContext.previous_now`, the previous tick's stamp, carried by the orchestrator —
`core/`, so the lead's. `None` on the first tick of a process and after a restart, never a
fabricated start, and a consumer measuring an interval publishes nothing for that tick rather than
guessing. A `previous_now` after `now`, or naive, is refused at construction: an interval running
backwards is a clock fault, not a small number. The clock is still read exactly once per tick.
A can now drop the `state["cycle_id"]` read it had added for the first-tick case, so engine 3
returns to reading no `state` at all.

**Mutations**, `tests/core`, each anchored on a literal asserted to occur exactly once and
restored from a byte copy with the sha256 compared in the same statement (all five
`restored byte-identical: True`):

| Mutation | Result | Killed by |
|---|---|---|
| N1 — `previous_now` is a computed offset, not the previous stamp | 2 failed, 56 passed | `test_previous_now_is_the_previous_ticks_now_not_a_computed_offset`, `test_a_late_tick_still_reports_the_interval_that_actually_elapsed` |
| N2 — the first tick claims a previous tick | 1 failed, 57 passed | `test_the_first_tick_has_no_previous_now` |
| N3 — the stamp is never carried forward | 2 failed, 56 passed | the same two as N1 |
| N4 — a backwards interval is accepted | 1 failed, 57 passed | `test_previous_now_is_refused_when_it_is_after_now` |
| N5 — a naive `previous_now` is accepted | 1 failed, 57 passed | `test_a_naive_previous_now_is_refused` |

**N1 is the mutation this change exists for**, and only the late-tick test can see it: on a
punctual loop the offset and the real stamp are the same value, so every test built on the
auto-advancing `_Clock` passes under N1. A double that advances by exactly one loop tick per read
cannot exhibit lateness — the property under test — which is the Phase 3 rule about doubles
arriving in a new place.

**A wrong turn of my own, worth recording.** My first late-clock double stepped the time on every
`now()` call, and the test failed reporting a seven-minute interval where it expected five. The
code was right: the orchestrator reads the clock more than once per tick (the run record, the
command stamp), so a per-read step measures how many times unrelated paths looked at the time. A
clock the test holds steady and advances explicitly between ticks makes the interval exact. The
failure looked like the feature and was the instrument — the same shape as the benchmark lesson in
`code-standards.md`, arriving in a test rather than a measurement.

### All four teammates died one minute before the limit reset, and the write-before rule paid

**Agent:** Lead · **Task:** Phase 6 team · **Date:** 2026-09-16

**What happened.** A, B, C-models and C-verify all hit the usage limit within 40 seconds of each
other at 23:49Z, one minute before it reset. Nobody was stopped and nothing was abandoned by
choice. The tree was left exactly as four sessions mid-task left it.

**What it cost, measured rather than assumed.** Every one of the four had written its claim into
`context/progress/<agent>.md` **before** starting and its findings into
`docs/build-log/phase-6/<agent>.md` **at diagnosis**. So the specs, the mutation tables, the two
findings raised in the last hour and every state-of-play line survived on disk; what was lost is
in-flight reasoning and nothing else. Phase 3 lost three build logs to an interruption because
they were being written *after* the work; this is the same event with the rule applied, and the
difference is the whole argument for it.

**What it did not cost.** No daemon has run at any point in Phase 6 — only the two `record.py`
processes and their supervisor, alive since 14:49 and untouched — so A's `drain_gaps` finding
(engine 2 records no `gap` markers through the paper broker) has damaged no recording. The
archive is intact and the fix is a one-line forward in B's lane.

**Two half-applied edits the deaths left, both found by reading the tree rather than the
reports.** `modelling/di.py` exports `score_many` in `__all__` and does not define it — C-models
landed the export and the `_BLOCK_ELEMENTS` reasoning and died before the function. And
`engines/risk/engine.py` still checks the portfolio cap before the per-pair refusal, with a
comment arguing the old order: the reversal I ruled had not been applied when B died. Neither is
a defect anybody introduced; both are what an interrupted edit looks like, and both are in the
handoff at the top of `feature-specs/PHASE-6-TASKS.md` rather than in anybody's memory.

**One red that is a tripwire working.** C-verify landed the two `REASON_PROSE` entries B was
waiting on, which fires B's `test_the_two_codes_spec_89_added_are_still_waiting_on_cs_prose` —
a test written to go red at exactly this moment and to tell whoever sees it what to do. It is
expected, it is B's to delete, and it is named here so the next reader does not diagnose it.

**Procedural note for the next time, and there will be one.** Four simultaneous deaths is not
four independent events: every session in this team shares one usage limit, so the limit is a
single point of failure for the whole team and it will always take them together. The mitigation
is not more agents, it is the discipline that made this cheap — claim before, diagnose before,
and a lead who reads the tree instead of the transcript.

### The baseline: two independent reds, one of them mine, and `compileall` was the wrong check

**Agent:** Lead · **Task:** Phase 6 baseline · **Date:** 2026-09-16

**What happened.** `verify.py --phase 6` on the quiet tree left by the four deaths:
`2 criteria: 1 PASS, 1 FAIL`. `toolchain_green` reported **56 failed, 2570 passed, 124 errors**
in 551 s, plus `mypy` and `ruff` each naming `src/acsoe/modelling/di.py`. Log:
`logs/verify/phase6-20260916-baseline-lead.log`, full pytest output under
`logs/verify/toolchain_green/20260916T000131_807204-pytest-attempt1.log`.

**Attribution, by counting rather than by path.** `_CHUNK` appears **359 times** in that output.
Every failing and erroring file except two is downstream of one broken module: C-models renamed
`_CHUNK` to `_BLOCK_ELEMENTS` at the top of `di.py` and died before renaming its two uses inside
`_mean_nearest`. Tournament, skeptic, prediction, anomaly, the DI's own tests, the training and
research suites and nine Phase 5 criteria all error on a `NameError` in a module they import.

**My earlier assessment of that file was wrong, and the way it was wrong is the lesson.** I ran
`python -m compileall` over `src/`, got a clean exit, and wrote that the module "imports and
compiles" and that only `from ... import *` would break. `compileall` checks **syntax**, not name
resolution: an undefined global inside a function body is a perfectly valid parse and a
`NameError` at call time. The check I ran could not have told me what I used it to conclude —
a check whose output resembles the claim while the claim is untrue, which is this project's most
repeated defect, committed by the lead in the middle of assessing somebody else's. `ruff`
(`F821`) and `mypy` (`name-defined`) both name it in one line, and I had run neither on that file.

**Fix.** The partial edit is saved to the scratchpad as `di-102-partial.diff` and quoted in the
handoff; `di.py` is restored to its committed state so the tree is usable by everyone else. It is
twelve insertions containing a rename and a comment and **no finished work** — `score_many` was
never written — so nothing of value is lost, and C-models re-applies it as part of a complete
spec 102 change. Restoring an uncommitted, half-applied edit by a dead session is not patching a
teammate's work: it is returning a shared tree to its last known good state, and the diff was
preserved before the file was touched.

**The second red is mine and it is correct.** `test_is_gate_parses_the_registry_out_of_the_document`
pins the set of gates parsed out of `engine-contracts.md`, and spec 80 added the **Y** for engine
16 by operator ruling. The test is doing its job: the gate list grew, and it is meant to take a
human decision to agree. It is C's file, so C-verify updates the expected set — the point of that
test is that nobody widens the gate list silently, including me.

**The third red is B's tripwire firing exactly as designed** and is B's to delete.

**So the baseline's verdict, stated honestly: one broken module, one document change awaiting its
test, one deliberate tripwire. No defect in any of the work the four sessions completed.**

### The two rehearsal findings ruled, and `state["block_status"]` landed in `core/`

**Agent:** Lead · **Task:** spec 87 review, specs 103–105 · **Date:** 2026-09-16

**What happened.** A's spec 87 rehearsal found two defects between engines (A's build log has
the diagnoses). I confirmed finding 1 against the code before reporting it:
`PaperBroker.balance()` adjusts by recorded fills only, and engine 21's `_mark` counts this
tick's fills in the portfolio value by design. The operator ruled on both — the paper-ledger
amendment (invariant 2) and the errored-engine record (invariant 12, contract rule 7).

**Why `core/` had to change for finding 2.** The opportunity chain put only the blocker's name
and reason into `state`, never its status. Engine 19 could therefore tell an engine that raised
from one that refused only by the empty payload — and an empty payload is also what a refusal
missing its `reason_code` looks like, the conflation `code-standards.md` warns about. A fix in
engine 19 alone would have had to guess.

**Fix.** `state["block_status"]` beside `block_reason` in both chains, absent when unblocked. Two
tests added. Three mutations, each killed by exactly one test (`tests/core`, 60 tests):
L1 opportunity status dropped → `test_an_opportunity_engine_that_raised_is_distinguishable_from_one_that_blocked`;
L2 guard status dropped → `test_a_raising_engine_becomes_error_and_blocks_without_killing_the_tick`;
L3 opportunity status hardcoded `BLOCK` → the first again. Restored file sha256
`52abd51c32e02b21734e1d925a652cd0ee5c22c643b0bd8b6500b0be37936731`.

**My own wrong turn, recorded.** The first sweep script wrote mutant L1 to disk and then raised
before running anything — `subprocess` could not find `.venv/Scripts/python.exe` by relative path —
and its restore sat after the call rather than in a `finally`. The mutant stayed on disk. I found
it by grepping for the line, restored it by a single-anchor patch, and re-ran with
`sys.executable` and a per-arm `try/finally` restore checked by hash. Nobody else was in the tree.
It is the "restore before the next mutation" rule from the other side: **a restore that is not in
a `finally` is a restore that only runs when nothing went wrong.**

**Also.** `core/orchestrator.py`, `tests/core/test_orchestrator.py` and
`context/architecture-context.md` were CRLF on every line in the working tree against LF blobs;
all three were written back as LF.

### Correction to B's spec 108 gate entry: 40bbc6b was committed after the gate completed

**Agent:** Lead · **Task:** spec 108 boundary · **Date:** 2026-09-17

B's spec 108 gate entry says `40bbc6b` "went in before the gate finished". It did not: the lead
read all four `logs/verify/b108-gate-*.log` files to completion — including
`b108-gate-verify.log`'s summary line `12 criteria: 2 PASS, 1 FAIL, 9 PENDING` and the
`toolchain_green` pytest attempt log `20260917T092109_334414` (`8 failed, 3201 passed`, only
the known eight) — before committing. What was missing at the commit was B's own **write-up**
of the fix and the gate, which B had not yet written because it was waiting for its
notification. B's entry is left as written (script-rules rule 6: correct with a new entry, never
edit an old one). The lesson for the lead: commit at a boundary only after the agent's records
are on disk, not only after its gate logs are, or the commit carries code whose build-log entry
is still in a transcript.

### I destroyed the red measurement at the pipe, having written the rule against it the same night

**Agent:** Lead · **Task:** cash_source default removal · **Date:** 2026-09-18

**What happened.** Removing `EquitySnapshotRow.cash_source`'s default, I ran the full suite to
enumerate every site that breaks and wrote it as `pytest ... 2>&1 | tail -4 > log`. The run took
30 minutes and reported `39 failed, 3108 passed, 167 errors`. **The four lines I kept are the
summary; the names of all 39 failures and 167 errors went to the floor.** The background task's own
output file holds the same four lines, because the pipe ran inside it.

**Why it matters more than the lost half hour.** `code-standards.md` carries this exact rule —
*"The evidence is destroyed at the pipe, before re-running is even a decision… Redirect to a file
and read the file. A summary line is not evidence; it is the receipt for evidence you did not
keep."* Phase 4 lost an unattributable failure to it. I wrote that same rule into HANDOFF 7 for the
next session a few hours earlier, and then broke it on the first command that produced a large
list.

**Why I reached for it.** The habit is from reading *verdicts*, where the summary line is the whole
answer, and every gate command I have run tonight legitimately ends in a tail. This run was the
opposite: a deliberate red whose **contents** were the product. The tell was available and I did
not take it — a command whose purpose is "enumerate what broke" cannot be satisfied by a count.

**Fix.** Re-run redirected whole to `logs/verify/lead-cashsource-red2.log`, and read the file. For
the rest of this task every measurement lands in a file first and is filtered afterwards.

## Agent A — Platform

*Verbatim from `docs/build-log/phase-6/a-platform.md`.*

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

## Spec 87 — the rehearsal of engines 18, 21 and 22

### Decision: the whole opportunity chain is real, and no upstream payload is hand-built

**Agent:** A · **Task:** spec 87 · **Date:** 2026-09-16

**Options.** B's `test_decision.py` and `test_execution.py` run engines 1, 3, 7, 9, 10,
11, 14 and 16 for real and supply 8 and 15 through their contract models, because they
need a trained artefact. The alternative is to train one and run every engine.

**Chose.** Every engine, in registry order: guard 1, 2, 3, 4, 17; opportunity 5, 6, 7,
12, 13, 8, 9, 10, 11, 14, 15, 16, 18; manage 21, 22, 19. The artefacts are trained in the
test, four folds of C's constructed series (`tests/research/test_training.py`), exactly
the way `test_feature_chain_rehearsal.py` trains its skeptic fixture. The market is C's
`ScriptedMarket` (spec 100's harness) wrapped by B's `PaperBroker`, at **fee tier 3**,
with the committed thresholds — skeptic 0.50, DI and anomaly 0.99.

**Because.** It is possible, which settles it. A probe measured it before any test was
written: on the window ending 200 bars before the end of the series, engine 8 calls a
BUY with an expected move of 2.99999999%, engine 10 prices friction at 0.308% against a
0.462% hurdle, engine 15's `p_wrong` is 9e-6 against 0.50, engine 16 is coherent and
engine 18 places a post-only limit buy. Training costs about 17 seconds, once per module.
So there is no compromise on "real upstream" to record.

**Cost.** One module-scoped fit, and a scripted market that has to be kept consistent
by hand: the stream quote (engine 3, engine 18's limit) and the REST book (engine 9, the
broker's post-only check and its market-sell walk) are two different reads in this
design, and the test pins both to one price at every step.

### FINDING, not fixed (B's lane): every paper fill inflates `peak_equity` by the position's notional, and `safety` freezes the account two ticks later

**Agent:** A · **Task:** spec 87 · **Date:** 2026-09-16

**What happened.** Driving a real entry to a real fill through the real chain, engine 19
wrote an `equity_snapshots` row on the fill tick of **`8332.414226591`** against a
`paper.starting_balances` of `5000.00`. That number is exactly
`5000.00 + 3332.414226591`: the whole pre-fill cash **plus** the new position valued at
its entry price. The next tick wrote the true equity, `4996.9908483354999` (cash
`1663.92` after the spend and the maker fee, plus the position marked at the bid).
Engine 17 then read that row against the inflated peak, computed a drawdown of
**40.03%** against `safety.max_drawdown_pct` 0.10, blocked, and wrote a `freeze`. Every
tick after that is blocked by `safety`, because `peak_equity` is carried forward from
the store and never comes back down. Reproduced on the first probe, deterministic.

**Why.** Two readings of one fill disagree about *when* it happened.

- `state["exchange"]["balances"]` comes from engine 1 at the **top** of the tick, and in
  paper mode that is `PaperBroker.balance()`: the starting balance adjusted by every fill
  **the store has recorded** (`src/acsoe/clients/paper/broker.py`, `balance` and
  `_filled_orders`). This tick's fill is not recorded yet — engine 21 has not even
  observed it — so cash is still `5000.00`.
- Engine 21 then observes the fill through `query_orders` and **includes the new
  position in `positions_value`** (`src/acsoe/engines/position_manager/engine.py`,
  `_mark`, the loop over `fills`), deliberately:
  `test_a_position_opened_by_this_ticks_fill_is_counted_in_the_portfolio_value` argues
  that leaving it out would make the row "short by the whole notional". That argument
  holds only if cash already reflects the spend.
- Engine 19 writes `equity = cash + positions_value`
  (`src/acsoe/engines/memory/engine.py`, `_write_equity`). The notional is counted twice.

In **live** mode B's argument is right: the exchange applied the fill when the trade
printed, before the tick began, so the fetched balance already reflects it. In paper
mode the broker decides the fill lazily, at the moment engine 21 asks, so its ledger lags
by exactly one tick. The broker's ledger is therefore *not* the same balance a real
exchange would report on the fill tick, and engine 21's valuation assumes it is. The
exit side is consistent in both modes (cash before the sale, the position still valued
beside it), which is why only entries show it.

**Consequence.** With 18, 21, 22 and 19 registered as spec 82 plans, every paper trade
freezes the account the tick after the tick after its fill. It is the drawdown-breaker
shape `code-standards.md` names — a plausible, in-range number that nothing downstream
questions — and it would have surfaced on the first paper trade after registration.

**Minimal reproduction.** `tests/engines/test_trade_chain_rehearsal.py`,
`test_a_filled_position_is_watched_across_quiet_ticks` (see the Fix note below for its
state). By hand: a resting entry of qty `q` at limit `L`, a trade strictly below `L`
between two ticks, `paper.starting_balances` `C`; on the next tick
`state["memory"]["equity"] == C + q*L` where it should be `C - q*L - fee + q*L`.

**Not fixed, by the rules of this spec.** Engines 21 and 19 and the paper broker are
B's and C's. Reported to the lead. Where the fix belongs is their call, and there are at
least three places it could go: the broker's `balance()` could resolve not-yet-recorded
fills the way `query_orders` does; engine 21 could leave this tick's fills out of the
total in paper mode (but no engine may branch on mode); or engine 19 could net this
tick's entry fills out of cash.

**What the rest of the rehearsal does about it.** Every other scenario is arranged so
that the tick it is *about* is the tick directly after the fill: `safety` reads the
fill tick's own inflated row there, where equity equals peak and the drawdown is zero,
so that tick is clean. The one scenario that cannot be arranged that way is the one the
defect breaks — watching a position across several quiet ticks.

### M4 was killed by the right test for the wrong reason, and the reason is a second finding

**Agent:** A · **Task:** spec 87 · **Date:** 2026-09-16

**What happened.** The first sweep killed M4 (engine 18 skips the `userref` check) in
`test_a_restarted_process_does_not_place_the_same_entry_twice`, which is the test written
for it. But the failure was a `KeyError: 'cycle_id'` inside my own record-check helper,
before the test reached its assertion that nothing was placed twice. The helper read
`state["memory"]["cycle_id"]` and `state["memory"]` was `{}`: **engine 19 had raised.**
That is an incidental kill wearing the right test's name, and it stays that way until
the property assertion is what fires.

**Why engine 19 raised.** Under M4, engine 18 re-places the order, the broker refuses a
second placement under one `userref` (`PaperBrokerError`), engine 18 raises, and
contract rule 7 turns that into `ERROR` with `blocks_trading=True` and `data={}`. The
orchestrator then sets `trading_blocked_by = "execution"`. Engine 19's
`_write_rejection` sees a blocker that is not a guard and a candidate pair, so it treats
the tick as a rejection, finds no `reason_code` in `state["execution"]` (empty, by rule 7),
and raises `MissingInputError` on purpose (`src/acsoe/engines/memory/engine.py`, the
`if not reason_code:` branch).

### FINDING, not fixed (C's lane, and a contract question for the lead): an ERROR anywhere in the opportunity chain leaves the tick unrecorded

**Agent:** A · **Task:** spec 87 · **Date:** 2026-09-16

**What happened.** Reproduced on **unmutated** engines: the full chain with engine 16
left out, so a real engine 18 raises its own `ExecutionError` ("decision.intent is
absent"). Result on that tick: `state["memory"] == {}`; the orchestrator logged two
`engine_error`s, engine 18's and engine 19's `MissingInputError`; **no `rejections` row,
no `block_records` row and no `equity_snapshots` row** were written. Probe:
`scratchpad/a87/test_probe_error.py`, output `probe-error.log`.

**Why.** Rule 7 empties the payload of any engine that raises, and engine 19 refuses to
record a rejection without a `reason_code` read from that payload. The two rules are each
reasonable and together they make every opportunity-chain `ERROR` unrecordable. It is not
specific to engine 18: any opportunity-chain engine that raises (10, 11, 16, and so on)
leaves `{}` and trips the same branch. It is only newly visible because engine 18 is the
first engine in that chain whose raise can come from the **exchange**, an outage during
`open_orders()` or `add_order()`, rather than from a chain contradiction.

**Consequence.** Invariant 12 says a rejection that does not reach storage is a defect
equal to a lost trade. Engine 17 counts `status = 'ERROR'` rows in `block_records`
against `safety.max_errors_in_window`, but `block_records` is written only for **guard**
blockers, so an opportunity-chain `ERROR` never reaches that count either. Engine 19 also
raises **after** it has written that tick's positions and orders, so the tick is partly
recorded and its equity row is missing.

**Not fixed.** Engine 19 is C's; the `ERROR`-to-row question is the contract's. For the
rehearsal: the restart test now asserts the idempotency property **before** it reads
the store back, so M4 is killed by the assertion that states it.

### Spec 87 mutation sweep — 4 applied, 4 killed, 1 equivalent control survived everywhere

**Agent:** A · **Task:** spec 87 · **Date:** 2026-09-16

**Discipline.** Before the sweep all three engine files were counted in Python:
`position_manager/engine.py` 0 CRLF / 632 LF, `exit/engine.py` 0 / 690,
`execution/engine.py` 0 / 487, and the test file 0 / 1105. So every anchor is bare LF, and
the harness refuses any anchor that does not occur exactly once. `PYTHONDONTWRITEBYTECODE=1`
throughout. For each arm the harness takes a byte copy into the scratchpad, applies the
mutant, runs it, and **restores from the byte copy before the next arm**, comparing the
sha256 in the same statement. A verdict needs a pytest summary line from every process it
ran. Harness: `scratchpad/a87/sweep.py`. The final run is against the final test file,
sha256 `1c018836bfceedf65fa9cab81dc307bc72d1a09ffbb69e0372551472efc64c20`, after a green
baseline of `6 passed, 1 xfailed`. After the sweep, `sha256sum -c` on all four files was
OK, and `git status` shows no engine touched.

File hashes before and after every arm (restored), then each mutant's hash:
`position_manager/engine.py` `bdb1878b…c6db76`, `exit/engine.py` `878c574f…1942b3`,
`execution/engine.py` `b1651203…e28912`.

| Arm | Mutation (anchor) | Mutant sha256 | Killed by | Red message | Summary |
|---|---|---|---|---|---|
| M1 | 21 `_held`: `return state.get(TRADING_BLOCKED_BY_KEY) == DATA_GUARD_NAME` → `is not None` (holds on any block) | `3524c202…df2fdb` | `test_a_block_by_any_other_engine_does_not_hold_a_touched_stop` | `engine 21 held on a block that was not data_guard` | `1 failed, 5 passed, 1 xfailed` |
| M2 | 22 `_held`: the `if self._close_intent(state): return False` lines deleted | `719934e1…c0f08` | `test_a_data_guard_block_holds_a_touched_stop_and_close_intent_then_exits_it` | `assert 'data_guard_blocked' == 'exits_placed'` (tier-3 sentence in the message) | `1 failed, 5 passed, 1 xfailed` |
| M3 | 21 after `cancels.append(self._cancelled_row(entry, cancelled, now))`: a new post-only buy under `userref + 1` | `ea9dd7eb…e92e5` | `test_an_unfilled_entry_is_cancelled_at_its_window_and_not_replaced` | `the cancelled entry was replaced at the exchange` | `1 failed, 5 passed, 1 xfailed` |
| M4 | 18: `found = self._already_placed(context, pair, userref)` → `found = None` | `c6a36954…11f9a892` | `test_a_restarted_process_does_not_place_the_same_entry_twice` | `unhandled PaperBrokerError: userref … has already been placed` on `trading_blocked_by` | `1 failed, 5 passed, 1 xfailed` |
| E1 | **equivalent control**: 21 `_held` rewritten as `== DATA_GUARD_NAME and not self._close_intent(state)` | `d1d3eaf8…50988` | nothing, as designed | — | own file `6 passed, 1 xfailed`; wider suite below |

**Each kill is the one test written for that property, and nothing else went red.** No
arm was killed incidentally, and the xfailed test stayed xfailed under every arm (no
XPASS). The first sweep's M4 kill came from a `KeyError` in my helper; that is recorded
above, and the kill is now on the property assertion.

**One limit on M4's kill.** It is observed through the **paper broker** refusing a second
placement under one `userref`. A live exchange might accept the duplicate instead, and
then this test would see a different symptom (two resting orders). It would still go red,
through `open_orders()`, but that branch has only been reasoned about, not run.

**E1 against the wider suite.** The wider-suite baseline, one process over
`tests/engines/ tests/clients/paper/`, was `854 passed, 1 xfailed in 158.92s`
(`logs/verify/a87-wide-baseline.log`). E1 then took **four attempts**, because the process
died with `0xC0000005` (exit 3221225477) and no summary on three of them. Each is recorded
as "not a result", not as a verdict:

1. One process: access violation inside `research/walkforward.py:_required`, under
   `test_feature_chain_rehearsal.py`'s `trained_skeptic` fixture (`wide-E1-crashed.log`).
2. One process: access violation inside pydantic `model_dump`, from
   `test_macro_context.py` (`wide-E1.log`).
3. Four processes: two died, one inside `shap`'s tree explainer and one inside plain
   Python in `test_feature_chain_rehearsal.py:trades_for` (`wide3-E1.log`).
4. Six processes (`wide4-E1.log`): five green (`244 passed`, `229 passed`, `280 passed`,
   `6 passed, 1 xfailed`, `66 passed`), and the feature-chain rehearsal died again. That
   group alone was then re-run under E1 (`wide5-E1.log`): `29 passed`.

So **E1 survived every test in `tests/engines/` and `tests/clients/paper/`**: 855 tests in
total, the same as the baseline. The feature-chain rehearsal does not import engine 21 at
all (0 occurrences of `position_manager`). As an unmutated control it then passed
2 of 2 runs.

**The crashes are the registered native fault, and I checked the other mechanisms first.**
The fault sites are four unrelated places: a C extension (`shap`), pydantic-core, and
pure Python twice. That is the process-level memory-corruption signature on the Known
Risks register. None of the crashes carried a database error, so it is not the tmp-dir
sweeper. None was a failing assertion, so it is not the load-sensitive wall-clock one.
None landed in a file the mutant touches. Three of the four landed in or after the
feature-chain rehearsal's LightGBM training in the same process; this rehearsal trains
too, and it did not crash in any of the roughly twenty runs it had this session. That is an observation, not a cause.

**A change made during the sweep, and the reason the sweep was re-run.** The rehearsal
opened `StoreClient`s and never closed them. An open SQLite handle under `tmp_path` is a
directory Windows will not delete, which is the same family as the tmp-dir sweeper on the
register, so a module-level autouse fixture now closes them. It changes no assertion, but
the file changed, so the narrow sweep was run again from scratch against the final bytes,
with the results above.

### Spec 87's own gate

**Agent:** A · **Task:** spec 87 · **Date:** 2026-09-16

The four commands, run in sequence under the lead's explicit stop, each redirected to a
file and read in full:

- `mypy --strict src/ scripts/`: `Success: no issues found in 153 source files`
  (`logs/verify/a87-mypy.log`)
- `ruff check src/ tests/ scripts/`: `All checks passed!` (`logs/verify/a87-ruff.log`)
- `pytest tests/ -q`: `8 failed, 3165 passed, 2 skipped, 1 xfailed, 3 warnings in 633.64s`
  (`logs/verify/a87-pytest.log`). All 8 are
  `tests/verify/test_phase6_criteria.py::test_pending_on_the_real_tree_names_the_subject_and_the_spec`,
  the known red owned by C (spec 100). The 1 xfailed is finding 1's strict xfail.
- `verify.py --phase 6`: `11 criteria: 1 PASS, 1 FAIL, 9 PENDING`
  (`logs/verify/a87-verify-phase6.log`). The FAIL is `toolchain_green`, which carries the
  same 8. `docs_vocabulary` PASSes over these entries.

No failure outside the known one.

### Finding 1 closed by spec 103: the strict xfail is now a plain test, and it can still fail

**Agent:** A · **Task:** spec 87, after spec 103 (B, `178a0a8`) · **Date:** 2026-09-16

**What happened.** Once spec 103 landed, the paper ledger counts every fill the broker has
executed, recorded or not. The strict xfail on
`test_a_filled_position_is_watched_across_quiet_ticks` then XPASSed, which is what it was
for. The lead's log is `logs/verify/b103-A-xfail-default.log`.

**Fix.** The marker is removed. The docstrings now tell the finding in the past tense:
the module docstring, test 4's note that engine 17 co-blocked on tick B, and test 5's note
on why its drawdown is written into the store. The test keeps its history paragraph. No
assertion changed.

**Proof it can still fail.** One arm, B1, run through the same harness, with
`PYTHONDONTWRITEBYTECODE=1`, a byte copy, the restore in `finally`, and the sha256
compared in the same statement:

- **Mutation:** in `src/acsoe/clients/paper/broker.py`, `balance()` loses its loop over
  executed fills (`for userref, executed in list(self._executed.items()):` becomes
  `for userref, executed in []:`). That reverts spec 103's half: executed but unrecorded
  fills are left out of the ledger again. The anchor occurs once; the file is 0 CRLF and
  865 LF.
- **Hashes:** broker `98c0df71…8c70e6201` before and after restore; mutant
  `c15e1c2a…bfa0a4c1`. The test file is `79cc6747…8ba0b3a2`, unchanged by the run.
- **Verdict:** KILLED, `1 failed, 6 passed in 59.92s`. The only failure is
  `test_a_filled_position_is_watched_across_quiet_ticks`:
  `AssertionError: the fill tick's equity counts the entry's notional twice`,
  `assert Decimal('8332.414226591') == ...`. That is the original finding's number, exactly.
- **After restore:** `sha256sum -c` OK, and `git status` shows only the test file.

**Runs on the restored tree.** The file: `7 passed in 69.75s`
(`logs/verify/a87-after103-file.log`). `tests/clients/paper/`: `77 passed in 17.60s`
(`logs/verify/a87-after103-paper.log`). No full gate was run; the lead runs it.

### The rehearsal's equity expectation described a moment the ruling abolished

**Agent:** A - **Task:** spec 116 - **Date:** 2026-09-17

**What happened.** After specs 113 and 114 landed, five of the seven scenarios in
`tests/engines/test_trade_chain_rehearsal.py` went red, all inside `check_recorded`.
Two separate causes, neither of them in engine 19.

**Why.** The first is mechanical. `check_recorded` builds its *expectation* by feeding
engine 21's and engine 22's published rows back through `PositionRow` and `TradeRow`,
whose `_Row` base is `extra="forbid"`. Spec 113 added `value` to a marked position row
and `net_proceeds` to a closed-trade row. Both are payload facts that engine 19 reads
and neither is a column - the store keeps `qty` and `last_price`, and `qty`,
`exit_price` and `exit_fee`, from which each is recomputable - so the models rightly
refuse them, and the expectation raised before a single comparison was made.

The second is substantive, and it is the one worth recording. The equity block asserted
`row.cash == state["exchange"]["balances"]["USD"]` and
`row.positions_value == state["position_manager"]["positions_value"]`. On a tick where
engine 22 sold, those two figures come from different instants: engine 1's balance is
from the top of the tick, before the sale, and engine 21's valuation is from before it
too, while the store's position count is from after. That is precisely the three-moment
row the operator's ruling of 2026-09-17 abolished. So the rehearsal was not merely out of
date - it was asserting, as the expected account, the composite the ruling exists to
forbid. Left as it was it would have failed a correct engine 19 forever, and a rehearsal
that disagrees with the contract is worse than no rehearsal.

**Fix.** Two changes, both in `check_recorded` and its helpers.

`without(row, field)` drops one payload-only field before the row model sees it, leaving
the published dict untouched. It is used for `POSITION_VALUE_FIELD` and
`NET_PROCEEDS_FIELD`, both imported from their owning engine's contracts rather than
spelled as strings, so a rename breaks the import instead of silently re-arming the bug.
Nothing is weakened by the drop: the two fields are then checked where they actually
matter, in the equity derivation.

`ruled_equity(state)` returns `(cash, positions_value, unrealised_pnl, cash_source)` or
`None`, and the equity block asserts against it. `None` means the ruling licenses no row,
and the caller then requires `equity_skipped_reason` to be set - so "engine 19 skipped"
is no longer an unconditional early exit from the check.

**How it was kept independent of engine 19.** The rehearsal's worth is that it is a
*second* derivation, so this mattered more than the code. `ruled_equity` was written from
`context/engine-contracts.md` - the ruling paragraph and the two cross-chain rows for
`net_proceeds` and `value` - and from the payload builders that produce those facts:
engine 21's `_mark` and engine 22's `_trade_row` and `_closed_position_row`, which are the
*sources*, not the consumer. `src/acsoe/engines/memory/engine.py` was not opened until the
file was green and the mutation arm needed an anchor, and C's `scratchpad/probe_rehearsal.py`
and C's build-log entry quoting it were not read at all. Three places where the derivation
deliberately does not take engine 19's shape, each one a way for the two to disagree:

1. **Whether a row is due** is decided from the marked rows that *remain*, not from engine
   21's `positions_value`. On an exit tick the two differ: an unmarkable position makes
   engine 21 withhold both totals, but if that position is one engine 22 just sold, every
   remaining position is marked and the ruling's sum exists. An engine 19 still gated on
   the absent total would write nothing, and the rehearsal would say a row was due.
2. **The sums are taken over the per-row `value` and `unrealised_pnl`**, which is not where
   engine 21's totals come from - it accumulates them beside the rows, deliberately, so
   that a comparison is of two computations. A row disagreeing with its own total is
   therefore visible from here.
3. **`cash_source` is derived** from the closed set, not read back off the row, so a
   correct figure under a wrong label fails on the label.

**Proof it can fail.** Two arms, in a **copied tree** under the scratchpad, never in the
working tree: `PYTHONDONTWRITEBYTECODE=1`, `sys.executable`, `PYTHONPATH` pointed at the
copy's `src` with `acsoe.__file__` asserted to resolve inside the copy (the editable
install's `.pth` names the working tree, so without that check the mutation would have
tested nothing), each anchor asserted to occur exactly once, engine 19 confirmed 0 CRLF /
796 LF, the restore in a `finally` with the sha256 compared in the same statement, and the
copy deleted at the end. Log: `logs/verify/a116-mutation-e19.log`.

- **A1, the arm spec 116 asks for.** `if sold or closed:` becomes `if False:`, so engine 19
  ignores engine 22's facts and writes the pre-exit row again. Mutant
  `56593fc6...0a566e66`. **KILLED, `4 failed, 3 passed in 75.06s`.** The killing assertion
  is the equity row's cash in `check_recorded`:
  `AssertionError: the row's cash is not the account the ruling describes`,
  `assert Decimal('1663.9201177597499') == Decimal('4924.372253541980864')` - the pre-exit
  cash against the cash after the sale, on a row whose repr shows `open_position_count=0`
  beside `cash_source=CashSource.CYCLE_START`, which is the three-moment row exactly.
- **A2, the label alone.** `cash_source = CashSource.AFTER_EXIT` becomes
  `CashSource.CYCLE_START`, so the arithmetic is right and only the label is wrong. Mutant
  `8a331c9e...9947ab0d`. **KILLED, `4 failed, 3 passed in 70.26s`**, on
  `AssertionError: the row is labelled for the wrong instant`. This arm exists because A1
  is killed by the cash assertion *in front of* the label assertion, which leaves the label
  assertion unwitnessed; A2 witnesses it.

The three survivors under both arms are the three scenarios with no exit tick - the
cancelled entry, the restarted process, and the watched position - which is the correct
survival, not a gap.

**Consequence.** No assertion was weakened and no engine was touched. `4 failed` rather
than `1 failed` is because `check_recorded` runs after **every** tick in four scenarios
that each reach an exit, so one defect in engine 19 is caught four times over.

**Runs.** The file on the restored working tree: `7 passed in 66.79s`
(`logs/verify/a116-file.log`). `ruff check src/ tests/ scripts/` all clean;
`mypy --strict src/ scripts/` `Success: no issues found in 153 source files`. The
rehearsal file is `a907322197de...4e02267f9c` and engine 19 is
`6d0c226f92...4ef0831fa7`, both confirmed unchanged after the mutation run. No full gate
was run; the lead runs it.

## SPEC 109 — THE PAPER-MODE FALLBACK PROSE, AND TWO THINGS THE GREP DID NOT FIND

**Agent:** A · **Task:** spec 109 · **Date:** 2026-09-18 · **Written at diagnosis, before any
byte of the fix.**

### What happened

Nine places in lane A describe, in substance, a division of labour that no longer exists:
*engine 1 and the Kraken client decline to apply invariant 2's paper-mode fallback because the
fallback is the **consumer's** decision, and the consumer must record which one fired.* Every
clause of that was true when it was written. Since the operator's ruling of 2026-09-16 removed
engine 11's `paper.starting_balances` branch — the last one — **there is no paper-mode fallback
anywhere in the system**, so there is no consumer decision to defer to and no record for a
consumer to keep. The prose is not merely out of date: it tells a reader that a substitution
happens somewhere downstream, which is the one thing invariant 2 now forbids everywhere.

Spec 109 names five of the nine. The grep for `fallback`, `starting_balances`, `substitut` and
`assume` across the whole lane found four more, of which two carry the identical sentence
(`clients/kraken/rest.py`, `tests/clients/kraken/test_rest.py`) and one is worse than any of
the five (`platform/config.py::load_credentials`) — see below.

### Why

The five named sites and the two the grep added share one author's framing and one date. They
are a correct statement of invariant 2 **as it read before 2026-09-10**, when the fee-tier row
still named a tier to assume; the client and engine 1 were written to refuse the substitution
locally while conceding it might legitimately happen elsewhere. The two retirements since —
the fee tier on 2026-09-10, the balance on 2026-09-16 — each removed a fallback without
removing the concession, because nothing greps for a sentence that is still grammatical and
still about a real field. This is the same drift class as A's 2026-09-16 `OrderState` note:
`docs_vocabulary` cannot catch it, there being no retired token in the line.

**Why "point at invariant 2 rather than restate it" is the instruction and not a style
preference.** Each of these sites restated the invariant in its own words, and each therefore
had to be re-edited when the invariant moved — nine times, in five files, across three
retirements. A site that names the rule and states only its own local consequence (*this
function refuses to invent a tier*) stays true when the rule is amended.

### FINDING 1 — an assertion in my own lane that cannot fail

`tests/engines/test_exchange.py`, `test_no_fallback_is_ever_substituted_for_a_failed_fee_fetch`:

```python
assert data["fee_tier"] is None
assert "tier" not in str(data.get("fee_tier"))
```

Given the line above it, the second assertion is `"tier" not in "None"` — a tautology. It could
only ever fail on a `fee_tier` that was a mapping containing the key, which the preceding line
has already excluded. The test's *name* is the property worth having and the first line proves
it; the second line reads as a second, stronger check and is not one.

**Not changed.** Spec 109 is prose-only and the lead's brief says a test asserting something is
not mine to edit under a prose spec. Reported for a ruling: delete it, or replace it with an
arm that can fail (assert on the whole payload, so a tier smuggled into a sibling key is
caught).

### FINDING 2 — `exchange/README.md` describes a retention read that no engine performs

Outside the grep's vocabulary, found by reading the file. `src/acsoe/engines/exchange/README.md`,
under "Retained last-known-good values":

> Only rule 14's emergency liquidation may use one, and **engines 21 and 22 read it from the
> client directly in Phase 6** — publishing it here would put it one attribute lookup away from
> a gate that must never see it.

On disk, at `2beb8ba`:

- **Engine 21 `position_manager` reads neither retained value.** `last_known_good` does not
  occur anywhere in that package.
- **Engine 22 `exit` reads only `last_known_good_asset_pairs`** (`engines/exit/engine.py:523`),
  and its `contracts.py:159-166` records at length that it **deliberately never reads a
  balance**: an exit's quantity is the position's, and a cap at the base holding would round
  every paper exit to nothing, the paper ledger being quote-side only by B's spec 88 ruling.
- Consequently **`last_known_good_balances` has no reader in `src/` at all.** The client
  retains it (`clients/kraken/rest.py:551`, surfaced on the facade and forwarded by the paper
  broker), engine 1 reads its *age* to publish `retained`, and nothing ever reads its value.

**There is a decision entry, and it is in B's lane, not mine.** B recorded it on 2026-09-16 in
`docs/build-log/phase-6/b-store.md` ("Decision: engine 22 never reads a balance…") and in
`context/progress/b-store.md` item 1, marked **escalated to the lead** as a deviation from
spec 93. So this is not behaviour that changed unrecorded — it is A's README never having been
told. The claim was true of the spec and has never been true of the code.

**Why it matters rather than being a nicety.** Invariant 2 justifies the retention as *"a
requirement on Agent A's client, not an optimisation"*, on the ground that discarding on
failure *"would make rule 14 unimplementable at exactly the moment it is needed."* For
`AssetPairs` that is exactly right and engine 22 proves it. For the balance the premise no
longer holds: rule 14 as implemented does not need it, and A's README is the only place still
asserting that it does. A reader auditing invariant 14 against the code finds a retained
balance, a README saying two engines read it, and no reader — and cannot tell whether the
retention is a requirement being met or a limb nobody amputated.

**Not changed, per the lead's rule on stale prose.** Reported with two questions the lead owns,
neither of which is mine to answer under a prose spec:

1. Does `last_known_good_balances` keep its retention with no reader (invariant 2's wording
   requires the client to retain it regardless), or does invariant 14's "engines 21 and 22 may
   use the last known good balances" need amending to match what B built and the lead accepted?
2. Either way the README sentence is wrong today. The honest rewrite depends on the answer to
   (1), so it waits for the ruling rather than guessing which of the two facts to write down.

### FINDING 3 — `load_credentials` tells a fresh clone it can trade

`src/acsoe/platform/config.py`, `load_credentials`:

> a missing key is the normal state of a fresh clone: **paper mode runs the whole pipeline
> without one, and invariant 2's paper fallbacks exist exactly so that it can.**

Both halves are false, and the second is false in a way the other eight sites are not — it does
not merely defer a fallback to a consumer, it names paper fallbacks as the *mechanism* that
makes an unauthenticated clone work. Invariant 2 states the true consequence in as many words:
with an empty `.env` the private calls fail, `TradeVolume` returns nothing, and **every pair
blocks at the cost gate**; the clone still runs the loop, still records the order book and
still builds candles — *"which is what the recording exists for and cannot be recovered
later"* — but takes no paper trades and writes no rejection row past the cost gate.

**This one is rewritten rather than only reported**, because unlike finding 2 the ruling behind
it exists and is explicit: invariant 2 already spells out both what a keyless clone does and
what it does not, so the code is doing what the system decided and only the sentence is stale.
It is called out here because it is the site in this batch most likely to mislead — the other
eight would make a reader look downstream for a fallback and find none, whereas this one would
make a reader believe an unauthenticated clone produces a research dataset.

### The nine sites, and the verdict on every other grep hit

The full table, with the substance of each rewrite and a verdict on every hit of `fallback`,
`starting_balances`, `substitut` and `assume` across `clients/kraken/`, `clients/recorder/`,
`platform/`, `cli/`, `scripts/` (less `verify.py`), `engines/exchange`, `market_data_recorder`,
`market_sensor`, `data_guard`, `research/{replay,historical,backtest}.py` and lane A's tests,
is in `context/progress/a-platform.md` under SPEC 109. It is kept there rather than duplicated
here because it is a list of current state, which is what a progress file is for.

### Fix

Eight sites rewritten across six files — the five spec 109 names, plus `clients/kraken/rest.py`
and `tests/clients/kraken/test_rest.py` carrying the identical sentence and
`platform/config.py::load_credentials` carrying the worse one of finding 3. Each now **names
invariant 2 and states only its own local consequence** instead of paraphrasing the rule, which
is what stops the ninth re-edit: every one of these paraphrases had already survived two
retirements (the fee tier 2026-09-10, the balance 2026-09-16) by being grammatical.

Two substantive replacements rather than deletions, both verified against the code rather than
inferred:

- **Engine 1's concurrency justification.** The three calls ran concurrently "because the
  paper-mode fallback for each one is different", which is now no reason at all. The real reader
  of that granularity is **engine 10 `cost`**: `cost/engine.py::_failed_fetch_reason` walks
  `failed_fetches` for the named call so the block sentence quotes *that call and its reason*
  rather than `exchange.fee_tier`, which is true and sends the operator to look at a `None`.
  Read in `cost/engine.py` and `cost/contracts.py:74` before writing it down, not assumed. Both
  `engines/exchange/README.md` and `engines/exchange/engine.py` now say that.
- **`load_credentials`.** Replaced with invariant 2's own stated consequence: a keyless clone
  starts, loops, records the book and builds candles, and **takes no paper trades** because
  every pair blocks at the cost gate.

The two test **names** were kept — both state properties that are still true and are now
unconditionally true — and **no assertion in either file was touched**. Only docstrings moved.

**Line endings.** `engines/exchange/contracts.py` and `engines/exchange/engine.py` are the only
CRLF files of the eight; the rest are wholly LF. The two CRLF files were patched through Python
with the replacements' endings converted explicitly and the result re-read (108 and 197 CRLF,
zero bare LF). No heredoc carried an escape into any file.

**And the measurement that was wrong first time.** The opening CRLF count used
`grep -c $'\r$'` and reported all ten files as wholly CRLF, including four holding no CR at all
— the giveaway being that every count equalled `wc -l`. Re-measured with Python, which is the
tool that would do the writing. Trusting the first reading would have converted six LF files to
CRLF wholesale, which is the kind of diff that hides a real change inside 3,000 touched lines.

**Runs.** `tests/engines/test_exchange.py tests/clients/kraken/` → **`182 passed in 1.22s`**
(`logs/verify/a109-pytest.log`). `ruff check src/ tests/ scripts/` → **All checks passed**
(`logs/verify/a109-ruff.log`). `mypy --strict src/ scripts/` → **`Success: no issues found in
153 source files`** (`logs/verify/a109-mypy.log`). No full gate was run; the lead runs it.

**No mutation table, and the reason rather than the omission.** Rule 2 of this log asks every
assertion to be proven capable of failing. This change adds and alters **no assertion** — it is
eight docstrings and comments — so there is nothing to mutate that would not simply be testing
the tests that already existed. What stands in for it is the verification done before each
sentence was written: engine 10's read of `failed_fetches` traced to the line, engine 21 and
engine 22's retention reads enumerated across the whole of `src/`, and the `Balances`/
`starting_balances` shape claim checked against both declarations. Two of those three checks
turned into findings, which is the evidence that they were checks and not readings.

**Findings 1 and 2 are not fixed and were not touched.** Finding 1 is a test assertion, out of
scope for a prose spec. Finding 2 needs a ruling the lead owns — whether
`last_known_good_balances` keeps a retention no engine reads, or whether invariant 14's sentence
moves to match what B built — and **which of the two facts to write into the README depends on
that answer**, so writing either one now would be answering the question rather than reporting
it. Both are in `context/progress/a-platform.md` under SPEC 109 with the detail.

## Agent B — Store and trading

*Verbatim from `docs/build-log/phase-6/b-store.md`.*

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

### Spec 108, diagnosis — prose in B's lane still describes a fallback that no longer exists

**Agent:** B (session 6) · **Task:** spec 108 · **Date:** 2026-09-17

**What happened.** Spec 106 removed the last paper-mode fallback (engine 11's balance), and
invariant 2 now reads "Every row blocks. There is no paper-mode fallback left in this table" and
"A ledger balance is not recorded as a fallback fired." Six places in B's lane still say
otherwise, or name the wrong table:

| Where | What it says | Why it is stale |
|---|---|---|
| `engines/cost/contracts.py` module docstring and `CostAssessment` docstring | `fallbacks_used` is "a real `rejections` column" / "one of those columns" | Migration 0001 puts `fallbacks_used` on `trades` (line 271). `rejections` has no such column; engine 19 harvests exactly the four `ECONOMICS_FIELDS` from a blocker's payload and nothing else |
| `engines/cost/engine.py` `_fallbacks` docstring | "the `rejections` column that records it" | Same |
| `engines/cost/README.md` ("Output", and the paragraph after "every pair blocks here") | "a real `rejections` column that engine 19 fills"; "**Balance is the only paper-mode fallback left in this system**, and it belongs to engine 11" | Wrong table; and since spec 106 there is no paper-mode fallback anywhere |
| `tests/engines/test_cost.py`, `test_this_engine_applies_no_fallback_and_says_so_by_recording_none` docstring | "a real `rejections` column" | Same |
| `clients/paper/broker.py`, the comment on `FALLBACK_PAPER_LEDGER` and the constant itself | "invariant 2 requires the decision to carry it either way" | Invariant 2 now says the opposite: a ledger balance is not a fallback fired. The constant has no user (below) |
| `clients/paper/broker.py`, the comment on `PAPER_STARTING_BALANCES_KEY` | "Invariant 2's one substituted value" | Invariant 2 substitutes nothing; the starting balance is the ledger's opening figure, and the broker is the authority on its cash |
| `clients/paper/broker.py`, the "forwarded reads" banner | "the one row of that table that does substitute a value is the balance" | Every row of that table now blocks |

**Why.** Each was true, or believed true, when written: the cost docstrings date from spec 40,
when B still expected engine 19 to copy the payload wholesale into `rejections`; the broker's
comments were written during spec 88 under ruling 3's first wording, before the operator removed
engine 11's fallback and wrote "A ledger balance is not recorded as a fallback fired." Spec 106
fixed the code and engine 11's prose, not these.

**`FALLBACK_PAPER_LEDGER` has no user.** `git grep` over the whole tracked tree finds it only in
`clients/paper/broker.py` (definition, `__all__`), `clients/paper/__init__.py` (re-export,
`__all__`) and in records (tracker, spec 108, the build log, the overnight log, this progress
file). `grep -rn` over `src tests scripts`, untracked files included, finds the same four source
lines and nothing else. The string `balance_from_paper_ledger` appears nowhere else either, so no
stored row or fixture carries it. Output: `logs/verify/b108-grep-constant-before.log`.

**`CostAssessment.fallbacks_used` — a producer, no reader.** Producer: `CostEngine.process` sets
it from `_fallbacks()`, which returns `()` unconditionally, so the published `state["cost"]` always
carries `"fallbacks_used": []`. Readers of `state["cost"]` in `src/` and `scripts/`: engine 16
`decision._compose` reads `net_edge_pct`, `hurdle_pct`, `expected_move_pct`; engine 19
`memory._write_rejection` reads the four `ECONOMICS_FIELDS` and `reason_code`; `scripts/verify.py`
imports the engine and its contracts but reads no `fallbacks_used` off the payload. **Nothing in
`src/` or `scripts/` reads it.** The only readers are tests: `tests/engines/test_cost.py` (asserts
it is `[]`, priced and blocked) and C's/the lead's fake cost engine in
`tests/verify/test_phase3_criteria.py:227`, which *publishes* `"fallbacks_used": []` in its
stand-in payload. It is not removed here: removing it changes the published payload shape, and a
stand-in in another lane mirrors that shape. Listed for the lead.

**The line endings.** `engines/cost/engine.py` is 328 CRLF / 0 LF in the working tree (blob LF,
per `.gitattributes`). The only literal-anchor patchers on it are two in
`tests/verify/test_phase3_criteria.py` — `"inputs.maker_fee_pct + inputs.taker_fee_pct +
inputs.spread_pct + inputs.slippage_pct"` and `"clears = net_edge > hurdle"` — each single-line,
each counted once in the file today, and `patch_module` reads in text mode anyway. No other
`tests/` or `scripts/` file patches it (grep for `cost/engine`, `engines.cost`). `contracts.py`
(288 CRLF) and `README.md` (140 CRLF) are CRLF as well.


### Spec 108, fix — the prose now matches invariant 2; one constant gone; engine 10's source is LF

**Agent:** B (session 6) · **Task:** spec 108 · **Date:** 2026-09-17

**Fix.**

- `clients/paper/broker.py`: removed `FALLBACK_PAPER_LEDGER` and its comment, and dropped it from
  `__all__`; removed the re-export from `clients/paper/__init__.py`. Rewrote the
  `PAPER_STARTING_BALANCES_KEY` comment: it is the ledger's opening figure and not a substituted
  value; the broker is the authority on its own cash; `balance()` raises rather than answering
  with that figure unadjusted. The forwarded-reads banner now says every row of the paper-mode
  table blocks and that the balance, which is not forwarded, is not a fallback either.
- `engines/cost/contracts.py` (module docstring, `CostAssessment` docstring),
  `engines/cost/engine.py` (`_fallbacks` docstring), `engines/cost/README.md`: `fallbacks_used`
  is described as a payload field, not a `rejections` column. Migration 0001 puts it on
  `trades`, and nothing in `src/` reads it. The README's "Balance is the only paper-mode
  fallback left" became "There is no paper-mode fallback left anywhere in this system"
  (spec 106), and a paragraph records the correction.
- `tests/engines/test_cost.py`: the summary line of
  `test_this_engine_applies_no_fallback_and_says_so_by_recording_none` no longer says
  "a real `rejections` column". The test is unchanged.
- Applied by a byte-level helper (`scratchpad/b108/edit108.py`): each anchor must match exactly
  once in the file's LF view, and each file is written back with the line ending it was found
  with.

**How-choices, with the option rejected.**

- `engines/cost/contracts.py` (288 CRLF) and `README.md` (140 CRLF) **left CRLF**, edited through
  the helper that keeps CRLF. Rejected: converting them as well. The spec names `engine.py`
  only, and `contracts.py` carries the phase-3 anchor `EXCHANGE_FEE_TIER_KEY: Final = "fee_tier"`
  (single-line, still counted once), so converting it would widen the change for no gain
  tonight.
- `engine.py` converted **before** the prose edit. Rejected: after. Converting first makes the
  LF proof a comparison against the untouched byte copy, not against a file I had already
  edited.
- The broker's starting-balance sentence was rewritten rather than deleted, so the next reader
  meets the rule where the constant is. Rejected: deleting the sentence and leaving only the
  "only config key" paragraph.
- The test name was kept. Rejected: renaming it, because the name is still true and appears in
  earlier logs.

**No mutation, and why.** Nothing here changes behaviour: comments, one unused constant, line
endings. The proofs are instead:

- **The constant had no user.** `logs/verify/b108-grep-constant-before.log`: four source lines,
  all definition, re-export or `__all__`. `logs/verify/b108-grep-constant-after.log`: `grep -rn`
  over `src tests scripts` finds nothing (exit 1).
- **The LF conversion changed only line endings** (`logs/verify/b108-lf-proof.log`):
  - Before: 328 CRLF / 0 bare LF / 0 bare CR, sha256
    `9f8ac3d4b821614de5bc2a035d037c30b87acdb9a2b28f88f2da0472e2299087`.
  - After: 0 CRLF / 328 LF, sha256
    `7f8feb8873ddfb2764bdf295eab1e7d705ad39dc22d8cf021ba70ec47df94139`.
  - `old.replace(b"\r\n", b"\n") == new` is True, the 11156 non-whitespace bytes are
    identical, and `git hash-object --no-filters` equals HEAD's blob `7d423da`.
- **The anchors still hold.** The two single-line strings in `test_phase3_criteria.py` each
  count once in the LF file. `-k cost_gate` gives `7 passed` (`logs/verify/b108-anchors.log`).
  `test_phase3_criteria.py` + `test_cost.py` + `tests/clients/paper` give `156 passed`
  (`logs/verify/b108-narrow.log`).

**Reported, not changed.**

- `CostAssessment.fallbacks_used`: engine 10 produces it, always `()`, and nothing in `src/` or
  `scripts/` reads it. The only other places are tests: `test_cost.py` asserts it is empty, and
  the stand-in at `tests/verify/test_phase3_criteria.py:227` publishes it. It stays, because
  removing it changes the payload shape. The lead's Q1 for the operator.
- `clients/store/client.py:942` (B's, outside this spec's write list): the `filled_orders`
  docstring says the balance is adjusted by every *recorded* fill, which is older than the
  spec 103 amendment (every *executed* fill).
- A's lane: `clients/kraken/README.md:55`, `engines/exchange/README.md:64`,
  `engines/exchange/contracts.py:17`, `engines/exchange/engine.py:117` and
  `tests/engines/test_exchange.py:12` still describe "invariant 2's paper-mode fallbacks" as
  the consumer's decision; there are none left.

### Spec 108 — the gate

**Agent:** B (session 6) · **Date:** 2026-09-17

Run one after another, each to its own file, with nothing else of mine running. pytest ran with
`-p no:cacheprovider`, which only stops it writing its cache folder.

| Command | Result | Log |
|---|---|---|
| `pytest tests/ -q` | `8 failed, 3201 passed, 2 skipped, 3 warnings in 1543.83s`. All 8 are `test_pending_on_the_real_tree_names_the_subject_and_the_spec` | `logs/verify/b108-gate-pytest.log` |
| `mypy --strict src/ scripts/` | `Success: no issues found in 153 source files` | `logs/verify/b108-gate-mypy.log` |
| `ruff check src/ tests/ scripts/` | `All checks passed!` | `logs/verify/b108-gate-ruff.log` |
| `verify.py --phase 6` | `12 criteria: 2 PASS, 1 FAIL, 9 PENDING`. The FAIL is `toolchain_green` on the same eight | `logs/verify/b108-gate-verify.log` |

Committed by the lead as `40bbc6b`, which went in before this gate finished. This entry was
written afterwards at the lead's request.

### Spec 113, diagnosis — what engines 21 and 22 must publish, and the one thing engine 19 will refuse

**Agent:** B (session 7) · **Task:** spec 113 (version 2) · **Date:** 2026-09-17

**What happened.** C's spec 100 criteria are the first code to run a whole paper trade through
the registered chain. On the exit tick, engine 19's equity row mixed three moments: cash from
engine 1 at the start of the tick, positions value from engine 21 before the sale, and the open
position count from the store after it. The operator ruled (Q-C1): each engine publishes only
what it knows, and engine 19 builds the exit-tick row by filtering and summing. B's part is
three facts: a sale's net proceeds (engine 22), a position's value (engine 21), and a column
saying where a row's cash came from (migration 0005).

**Read in the code, not the spec.**

- Engine 22, `ExitEngine._trade_row` (`engines/exit/engine.py`): `qty` is the client's
  `filled_qty`, `exit_price` its `avg_fill_price`, and `exit_fee` its `fee`. The row already
  computes `proceeds = qty * exit_price`, so `net_proceeds = proceeds - exit_fee` uses exactly
  the numbers the row carries. `format(x, "f")` round-trips a `Decimal` exactly, so these
  locals are the row's own fields. Engine 22 reads no balance and no engine 21 total for this.
- Engine 21, `PositionManagerEngine._mark` (`engines/position_manager/engine.py`): a stored
  position gets `last_price` and `unrealised_pnl` only when `_bid` answers. A position opened
  by this tick's fill always gets `last_price` = fill price (spec 106). The totals are
  `value += qty * mark`, in two loops. `value` goes beside `last_price` in both loops, and
  nowhere else.
- The equity model is **`EquitySnapshotRow`** (`clients/store/contracts.py`), not the
  `EquityRow` the spec names. The store writes it with `_insert(model_dump())`, so a new model
  field is a new column in every insert. Engine 19 builds it with keyword arguments and no
  `cash_source` (`engines/memory/engine.py:603`).
- `ALTER TABLE ... ADD COLUMN ... NOT NULL` in SQLite needs a non-null `DEFAULT`, so migration
  0005's form is decided by the engine: `DEFAULT 'cycle_start'`, which also backfills the
  existing rows.

**Why engine 19 will refuse both new keys.** Every store row model inherits `_Row`, whose
`model_config` is `extra="forbid"`. Engine 19 passes the publishers' dicts straight to it:
`store.write_position(PositionRow.model_validate(stamped))` (`engines/memory/engine.py:387`)
and `TradeRow.model_validate(self._stamped(row, ...))` (`engines/memory/engine.py:420`). A
position row carrying `value` or a trade row carrying `net_proceeds` raises
`ValidationError: Extra inputs are not permitted`. `MemoryEngine.process` does not catch it,
so contract rule 7 turns the tick into `ERROR` and **nothing** is recorded on it: no position,
no order, no trade, no equity row. That happens on every tick with a marked position. Engine 19
is C's. The operator approved C accepting the keys in spec 114, so B reports this and does not
edit engine 19. The alternative in B's lane, adding `value` and `net_proceeds` to `PositionRow`
and `TradeRow`, would make them columns (`_upsert` writes every field) with no migration. It is
rejected. So between spec 113 and spec 114, every test that runs engine 21 or 22 into the real
engine 19 is expected to go red. That includes my own spec 106 test
`test_a_position_opened_by_this_ticks_fill_is_stored_marked_at_its_fill_price`. The next entry
measures it.

**Line endings.** `clients/store/seed.py` is 1276 CRLF / 0 LF and stays CRLF: it gets a
byte-level edit. Every other file on this spec's write list is pure LF.

**Anchors to keep at exactly one occurrence** (`tests/verify/test_phase6_criteria.py`):
engine 21's `position_row["last_price"] = format(mark, "f")`,
`bid = _money(quote[QUOTE_BID_FIELD])`, the target, timeout, hold, cancel and `close_intent`
lines; engine 22's `realised = proceeds - cost_basis - entry_fee - exit_fee`,
`return system.get(CLOSE_INTENT_FIELD) is True` and `if not close_intent:`. The new lines are
written so that none of them repeats an anchor.

### Spec 113, fix — `net_proceeds` on each sale, `value` on each marked position, `cash_source` on each equity row

**Agent:** B (session 7) · **Task:** spec 113 (version 2) · **Date:** 2026-09-17

**Fix.**

- Engine 22, `_trade_row`: `NET_PROCEEDS_FIELD: format(proceeds - exit_fee, "f")`, where
  `proceeds = qty * exit_price` is the line the row already had. The constant
  (`"net_proceeds"`) is in `engines/exit/contracts.py`, with the reason it reads no other
  engine. The README's trade-row section says the same.
- Engine 21, `_mark`: `row[POSITION_VALUE_FIELD] = format(position.qty * bid, "f")` beside the
  stored row's `last_price`, and `position_row[POSITION_VALUE_FIELD] = format(qty * mark, "f")`
  beside the fill-tick row's. Neither is written on a row without a mark. The two `value +=`
  lines are unchanged, and so is when the totals are omitted. The constant (`"value"`) is in
  `engines/position_manager/contracts.py`, and the README gained a paragraph.
- `db/migrations/0005_equity_cash_source.sql`: `ALTER TABLE equity_snapshots ADD COLUMN
  cash_source TEXT NOT NULL DEFAULT 'cycle_start' CHECK (cash_source IN ('cycle_start',
  'after_exit'))`. The default is the backfill. `EXPECTED_TABLES` and `EXPECTED_INDEXES` are
  unchanged, because no table or index was added.
- `clients/store/contracts.py`: `CashSource(StrEnum)` with `CYCLE_START` and `AFTER_EXIT`, and
  `EquitySnapshotRow.cash_source: CashSource = CashSource.CYCLE_START`. Exported from
  `clients/store/__init__.py`. `_to_sql` already writes an enum's value, and `_row_to_dict`
  hands the text back for pydantic to validate.
- `clients/store/seed.py` passes `cash_source=CashSource.CYCLE_START` explicitly. The file is
  CRLF and stays CRLF (1276 lines before, 1281 CRLF / 0 LF after). The edit was made on an LF
  view with every anchor counted once, then written back with CRLF. A diff against the byte copy
  shows only the import line and the four added lines.

**How-choices, with the option rejected.**

- **`cash_source` defaults to `cycle_start` in the model.** Rejected: making it required.
  Engine 19 builds `EquitySnapshotRow` by keyword without the field
  (`engines/memory/engine.py:603`), so a required field raises on every tick and no equity
  row is written until spec 114. The default is also the true label for everything engine
  19 writes today. The risk is the one `code-standards.md` names: a model default can
  satisfy an assertion on your behalf. So the store test asserts the stored text for
  `after_exit`, and the docstring says the default should go once engine 19 passes the
  field. **Recommendation for spec 114: remove the default when engine 19 writes the field
  on every row.**
- **A `StrEnum`, not a bare `str` with a validator.** Rejected: `str` plus a
  `field_validator`. Every other closed set in this module is an enum (`BlockStatus`,
  `PositionStatus`, `OrderStatus`), and C's spec 114 gets a name to import rather than
  spelling `"after_exit"` by hand.
- **`NOT NULL DEFAULT` in the migration.** Rejected: a nullable column, which would be a third
  answer meaning "not recorded", and a table rebuild to get NOT NULL without a default, which
  must recreate `ux_equity_snapshots_tick` and gains nothing, because every write goes through
  the model. The reasons are written in the migration itself.
- **A closed CHECK.** 0003 refused to enumerate hold reasons. The difference is written in
  0005: two values answer a yes-or-no question, and a third would be a new design.
- **Each row's value is computed beside its total, not the total from the rows.** Rejected:
  `value += row_value`, which would make the rows and the total agree by construction. That
  would change how `positions_value` is computed, which spec 113 rules out. It would also
  leave the operator's sum test comparing one number with itself, the shape the operator
  warned against.
- **`net_proceeds` from the locals, not re-parsed from the row's strings.** `format(x, "f")`
  of a `Decimal` parses back to the same `Decimal`, so the locals *are* the row's fields.
  The test checks the claim by recomputing from the strings.
- **Named constants** (`NET_PROCEEDS_FIELD`, `POSITION_VALUE_FIELD`), because both contracts
  modules say every cross-engine key is a `Final`. Neither can yet be pinned against
  `engines/memory/contracts.py`, which does not name them until spec 114. That pin belongs
  to spec 114, beside the existing `test_the_field_names_are_the_ones_engine_nineteen_reads`.

**Tests.**

- `tests/engines/test_exit.py`:
  - `test_the_net_proceeds_are_the_rows_own_qty_times_exit_price_less_its_exit_fee`:
    recomputed from the row's strings and from the fixture (10 × 99.99 less the tier 3
    taker fee), and not equal to the figure less the entry fee as well.
  - `test_the_net_proceeds_read_neither_engine_twenty_ones_valuation_nor_the_balance`: the
    same sale is run twice, the second time with engine 21's totals and marks replaced and
    engine 1's `balances` removed, and the figure is unchanged. The exit order is recorded
    between the runs, as in the run-twice test. My first draft did not do this, and the
    second run was refused a second placement under the same `userref` (0 closed trades).
- `tests/engines/test_position_manager.py`:
  - `MARKED_TICKS` has four shapes: one stored position; two stored positions at two bids
    (SOL 99.99 against entry 99.00, BTC 60000.50 against entry 59000); a stored position
    plus this tick's fill; a fill alone.
  - `test_every_marked_row_carries_its_value_recomputed_from_its_own_fields[4]`.
  - `test_each_row_is_valued_at_its_own_mark_and_not_its_entry`: pinned to the numbers.
  - `test_value_is_present_exactly_when_last_price_is`: a partial mark, with BTC unquoted
    and a SOL fill. BTC has neither field, the fill row has both, and the totals are
    absent.
  - **`test_the_row_values_sum_exactly_to_positions_value_whenever_it_is_present[4]`**, the
    operator's sum test. It also requires every row to carry a value whenever the total is
    present.
  - `test_a_position_with_no_quote_carries_no_last_price` now also asserts that there is no
    `value`.
- `tests/db/test_migrations.py`, a 0005 section:
  - both values accepted;
  - blank, upper case, a third value, a trailing space and NULL all refused;
  - **the backfill, measured**: migrations 1-4 applied from a copy of the real directory,
    two rows written before the column exists, 0005 applied alone (`== [5]`), both rows
    read `cycle_start`, and their money is untouched;
  - the one-row-per-tick index still fires, and the column is `TEXT` and not a money
    column.
  - The "at least N migrations" floor went from 4 to 5.
- `tests/clients/store/test_store.py`: the round trip for both values, including the stored
  text; the model default; the refusal matched on the constraint, not on the name.
- `tests/clients/store/test_seed.py`: every seeded row is `cycle_start`.

**What the neighbours said** (`logs/verify/b113-*`):

- My two engine files: `1 failed, 103 passed`. The one is
  `test_a_position_opened_by_this_ticks_fill_is_stored_marked_at_its_fill_price`, the engine 19
  refusal (`b113-engines-second.log`, and `b113-engine19-refusal.log` for the traceback).
- `tests/db` + `tests/clients/store`: `271 passed` (`b113-store-first.log`).
- `tests/engines/test_memory*.py`, read only: `50 passed` (`b113-memory.log`). They build their
  own payloads, so they cannot see the refusal.
- `tests/verify/test_phase3_criteria.py` + `test_phase4_criteria.py`: `95 passed`
  (`b113-phase34.log`).
- A's rehearsal + `tests/verify/test_phase6_criteria.py` + `test_runner.py`:
  `25 failed, 74 passed` in 375.53s (`b113-neighbours.log`). The lead's baseline was 5 known.
  The other 20 are all the refusal:
  - A's five rehearsal tests say "engine 19 raised on this tick".
  - Every criterion message reads "a trade below the limit … did not fill it: the stored order
    is 'resting'": engine 19 raised on the fill tick, so the fill was never recorded.
  - That covers the five real-tree criteria. `escalation_completes_during_outage` is new red
    among them, while target, stop, timeout and held stop were already known.
  - It also covers the four equity-across-fill tests and ten of the `MUTATIONS` arms, whose
    criteria fail earlier than the fragment they expect.
  - All of it turns green only when engine 19 accepts the keys (spec 114). Engine 19 is not
    edited here.
- `ruff check src/ tests/ scripts/`: `All checks passed!`, after fixing my own seven findings:
  `×`/`−` in new comments, one import order, and one non-raw `match=`.
- `mypy --strict src/ scripts/`: `Success: no issues found in 153 source files`.

### Spec 113 — ten mutations: eight killed by the tests written for them, two controls, and the sum test proven red on its own

**Agent:** B (session 7) · **Task:** spec 113 steps 5 and 6 · **Date:** 2026-09-17

Harness: `scratchpad/b113/sweep113.py`, on spec 106's machinery — byte copy to scratch, the
anchor refused unless it appears exactly once, `PYTHONDONTWRITEBYTECODE=1`,
`-p no:cacheprovider`, `sys.executable`, the restore in a `finally` **before** the next arm with
the sha256 compared in the same statement, and no verdict without a pytest summary line. Both
engine files are pure LF, so the anchors carry bare `\n`. Hashes before the sweep and after every
arm, identical throughout: `engines/position_manager/engine.py` `c131dabea938…58fac`,
`engines/exit/engine.py` `0a68c73b23ee…f8c2a`
(`logs/verify/b113-sweep-hashes-before.txt`). Narrow targets:
`tests/engines/test_position_manager.py` and `tests/engines/test_exit.py`. Logs
`logs/verify/b113-sweep-*`.

**The narrow baseline is `1 failed, 103 passed`**, and that one failure is the engine 19
refusal (`…fill_is_stored_marked_at_its_fill_price`). It appears in every arm below and is
never the kill. **Controls chosen after grepping `tests/` and `scripts/` for their line text**:
`format(qty * mark, "f")` and `format(proceeds - exit_fee, "f")` appear in no patcher; the only
hits are two assertions inside my own new exit test, which are expressions and not anchors.

| Arm | Mutation | Verdict (narrow) | Killing test — written for it |
|---|---|---|---|
| N0 | `proceeds - exit_fee` → `-exit_fee + proceeds` — **control** | survived, `1 failed` (the baseline) | — |
| N1 | net proceeds without the exit fee | killed, `2 failed` | `test_the_net_proceeds_are_the_rows_own_qty_times_exit_price_less_its_exit_fee` |
| N2 | net proceeds less the entry fee as well | killed, `2 failed` | the same test, at its `!=` assertion |
| V0 | fill-tick row valued at `entry_price`, which **is** its mark — **control, equivalent** | survived, `1 failed` (the baseline) | — |
| V1 | a value at cost on a row with no mark | killed, `3 failed` | `test_value_is_present_exactly_when_last_price_is`, and `test_a_position_with_no_quote_carries_no_last_price` |
| V1b | a value of `"0"` on a row with no mark | killed, `3 failed` | the same two |
| V2 | stored row value from `entry_price` while the total uses the bid | killed, `8 failed` | **the sum test, 3 of its 4 cases**; also the recompute test (3 cases) and `test_each_row_is_valued_at_its_own_mark_and_not_its_entry` |
| V3 | the total left this tick's fill out | killed, `4 failed` | **the sum test, 2 of its 4 cases**; also `…fill_is_counted_in_the_portfolio_value` (spec 106's) |
| V3b | the total left the first stored position out | killed, `5 failed` | **the sum test, 3 of its 4 cases**; also `test_a_position_is_marked_at_the_bid` |
| V4 | the fill-tick row carries no value | killed, `5 failed` | the recompute test (2 cases), the sum test (2 cases), the present-iff test |

**The operator's condition, met directly (spec 113 step 6).** V2, V3 and V3b were re-run with
**only the sum test selected**, so nothing else could be the killer
(`logs/verify/b113-sweep-V2-only.log` and its siblings):

- V2 — row value from the entry price, total from the bid: `3 failed, 1 passed`.
- V3 — total over one row fewer (the fill): `2 failed, 2 passed`.
- V3b — total over one row fewer (the first stored position): `3 failed, 1 passed`.

In each case the case that passes is the one the mutation cannot reach: V2 cannot move a
fill-tick row, whose mark *is* its entry price, so the fill-only tick still agrees; V3 touches
only the fills loop, so the stored-only ticks still agree. That is the shape the operator asked
for — the test compares two computations and goes red on its own when they disagree, rather than
comparing one number with itself.

**V1 had to be run twice, and the first run was not a result.** It exited `3221226505`
(0xC0000005) with **no pytest summary line at all**. That is the registered native fault, and the
harness refused a verdict rather than reporting one. The re-run gave `3 failed, 100 passed,
1 error`, and the error is the same register: a `TypeError: object of type 'MappingStartEvent'
has no len()` inside pure-Python PyYAML, loading the committed config in the setup of an
unrelated test (`test_a_touched_barrier_wins_over_an_elapsed_timeout`). The config is unmodified
in the working tree, the two killing tests are the ones named above, and neither touches YAML.
Not filed as a new mystery; it fits the entries already on the register.

**The two controls, against the whole of `tests/`** (`logs/verify/b113-sweep-N0-wide.log`,
`…V0-wide.log`). Both: `26 failed, 3243 passed, 2 skipped`, **the same 26 tests in both arms**,
and both restored by hash.

The 26 are exactly the tree's current red, measured unmutated in two runs that between them
cover every one of those files: the neighbour run's 25 (`b113-neighbours.log` — A's five
rehearsal tests and 20 in `tests/verify/test_phase6_criteria.py`) plus the one in my own two
files (`b113-engines-second.log`). Compared as sets, and the difference either way is empty. So
both controls **behaviourally survived**: the harness labels them KILLED because pytest exits 1
on a tree that is already red, and the failing set is the verdict. All 26 are the engine 19
refusal and go green with spec 114.

**What I did not run:** a single unmutated whole-suite run. The baseline above is the union of
two unmutated runs rather than one, which is enough to compare the sets and is worth saying
plainly. The lead's gate after spec 114 is the authoritative one.

**The patcher anchors, re-counted in Python after the last edit.** All eleven anchors that
`tests/verify/test_phase6_criteria.py` applies to engines 21 and 22 — nine distinct lines, with
two arms sharing the hold line — still appear exactly once in the files as they now stand,
including `position_row["last_price"] = format(mark, "f")`, which the new `value` line sits
directly beneath. `test_phase3_criteria.py` + `test_phase4_criteria.py`: `95 passed`.

**Not swept: the store.** Migration 0005, `CashSource` and the seed line change no engine
arithmetic, and their proofs are the tests instead: the backfill measured by applying 1-4,
writing rows, then applying 5 alone; the CHECK refusing five shapes of wrong value including
NULL; the round trip asserting the stored text so a writer that dropped the field and let the
database default fill it fails the `after_exit` case. Named here because an unswept area is a
hole with a shape the next reader needs.

### An always-empty `fallbacks_used` is a claim that looks true and means nothing

**Agent:** B · **Task:** spec 111 · **Date:** 2026-09-17

**What happened.** Engine 10 `cost` published `fallbacks_used: []` on every tick. Spec 108
reported it to the lead rather than removing it — removing a published field changes the shape —
and the operator ruled on it as Q1: the field goes.

**Why.** Three facts, each checked in the code rather than in a description of it. It has **no
producer of a value**: `_fallbacks()` returned `()` unconditionally, and had done since spec 40
deleted the dead read of `state["exchange"]["fallbacks_used"]`, a key engine 1 does not publish
and never did. It has **no reader**: `rejections` carries no such column (migration 0001 puts
`fallbacks_used` on `trades`), engine 19 harvests the four `ECONOMICS_FIELDS` and `reason_code`
from a blocker's payload and nothing else, and engine 16 and the console never read it from here.
And there is **nothing left for it to record**: spec 37 retired the fee-tier row of invariant 2's
paper-mode table and spec 106 removed the last paper-mode fallback in the system, so this gate
applies none, in any mode.

What makes it worth removing rather than leaving is the third fact meeting the first. An empty
list reads as *no fallback fired on this decision* — a statement about the tick. It is really a
statement about the field: nothing could ever have fired, because nothing can write it. A record
that cannot record the thing it is named for answers the question anyway, and answers it
reassuringly. Engine 22 `exit`'s `fallbacks_used` stays, and the contrast is the point: there the
list is filled from the fetch failures rule 14 tolerates during a liquidation, so an empty one
there is a measurement.

**The precedent is spec 106**, which removed `RiskSizing.fallbacks_used` on the same three
findings a day earlier, and whose payload key set is now pinned by
`test_an_approval_publishes_no_fallback_field`. This is the same removal in engine 10.

**Fix.** The field, its `to_state_data` line and `_fallbacks()` are gone from
`engines/cost/{contracts,engine}.py`; the prose in both files and in the README now says what
is true, with the README carrying the paragraph on why it was removed rather than left as a
harmless constant. `tests/engines/test_cost.py`'s assertion that the list was empty becomes
`test_this_engine_publishes_no_fallback_field_and_the_key_set_is_pinned`, which asserts the key
is **absent** and pins `COST_PAYLOAD_KEYS` as a set on both ticks that publish a full assessment,
plus the smaller missing-input shape separately. A set rather than a `>=`: the property is
*which* keys there are, and a `>=` is satisfied by a payload carrying an extra field nothing
reads, which is the thing being removed.

**Two mutations, both killed, both by that one test** (`logs/verify/b111-sweep-M1.log`,
`…-M2.log`). M1 re-adds `"fallbacks_used": []` to `CostAssessment.to_state_data`:
`1 failed, 30 passed`. M2 re-adds it to `_blocked_on_missing_input`'s payload, which is the arm
the third assertion exists for: `1 failed, 30 passed`. Baseline `31 passed`; each arm restored
from a byte copy in a `finally` with the sha256 compared in the same statement
(`2965ca3c43e9e143`, `37c50de06a20739a`), one arm on disk at a time.

**`tests/verify/test_phase3_criteria.py` did not go red: `48 passed` before and `48 passed`
after** (`logs/verify/b111-phase3-criteria-{before,after}.log`). Reported rather than passed
over, because the operator's question about it has an answer. Its `CONSTANT_FEE_COST_ENGINE`
is a deliberately-wrong engine written to disk for the criterion to FAIL against, and it still
publishes `"fallbacks_used": []` — a shape no real engine produces any more. It stayed green
because `check_cost_gate_uses_live_fee_tier` reads `net_edge_pct`, `reason_code`,
`clears_hurdle` and `hurdle_pct` and never the key set, so an extra field in the double is
inert. That is the *double that stopped tracking what it doubles* from `code-standards.md`,
caught at the moment it stopped tracking: harmless today, and it is C's file and C's question
what the fake should be. Not edited.

**One more place carries the old shape and is not mine:** `docs/PROJECT-STATE.md:1001` still
lists `fallbacks_used: tuple[str, ...]` in engine 10's row of the cross-chain key table (line
1002 lists engine 11's, which spec 106 removed). Reported to the lead.

### Decision: the window/escalation tripwire asserts a config relationship, not an engine

**Agent:** B · **Task:** spec 112 · **Date:** 2026-09-17

**What it is for.** Invariant 14 says `safety` escalates only when there are open positions
**or resting entry orders**, and the resting-entry half has no escalation test. It cannot have
one on today's config: `safety` escalates after `safety.max_consecutive_data_blocks` ×
`timeframes.loop_tick_s` = 900s of outage, and engine 21 cancels a resting entry after
`trading.entry_unfilled_window_s` = 300s — while the manage chain is holding on the very
`data_guard` block that is counting towards the escalation, because invariant 8's cancellation
is a decision about elapsed time and not about price. Every resting entry is off the book long
before an outage could escalate, so the clause is reachable only through an operator Close all,
which `escalation_completes_during_outage` exercises.

**Options.** Leave it (F1 stays a note nobody reads); write the escalation test anyway against a
hand-built state the orchestrator cannot produce; or assert the *reason* the path is unreachable
and let a change to either value announce itself. The operator ruled the third, and the reason is
A's Phase 5 rule: an unreachable path earns an assertion that it is unreachable rather than a
deletion, and the assertion has to sit on the cause.

**Chose.** `test_a_resting_entry_is_cancelled_by_its_window_before_safety_could_escalate` in
`tests/engines/test_safety.py`, asserting `trading.entry_unfilled_window_s <
safety.max_consecutive_data_blocks × timeframes.loop_tick_s` with all three read through the real
loader (`load_config`) from the committed `config/default.yaml`, by dotted key. No literals: a
literal would pin this file's memory of the config rather than the config, and the change the
test exists to notice *is* a change to the config. Reading by dotted key means `Config.get` also
raises if any of the three is renamed, so a rename fires it as loudly as a retune.

**Because** it forbids nothing and couples nothing. The failure message says in as many words
that nothing is broken: the clause has become reachable through a `safety` escalation and now
needs its own test.

**Proven capable of failing, twice** (`logs/verify/b112-proof-W1-window-1200.log`,
`…-W2-window-900-equal.log`). The committed config is the lead's file and other agents run in
this checkout, so it was never edited: each arm copies `config/default.yaml` to the scratchpad
with the window raised and re-points the test's one config-path expression at the copy for the
length of one run, restoring `tests/engines/test_safety.py` from a byte copy in a `finally` with
the sha256 compared in the same statement (`819d599514db3c18` both arms). W1, window 1200s:
`1 failed`, message `trading.entry_unfilled_window_s is 1200s, which is no longer below
safety.max_consecutive_data_blocks (15) x timeframes.loop_tick_s (60s) = 900s`. W2, window 900s —
the boundary, because the comparison is strict and an untested boundary is a boundary nobody
decided: `1 failed`, same message with 900s. Both name all three values and the product.

**Cost.** One test that goes red on a config change that is otherwise legitimate. That is the
point of it, and the message is written so the next reader is not misled into reverting the
config. The lead adds a one-line pointer to the test in invariant 14.

### The store's ledger docstring still described the ledger it had before spec 103

**Agent:** B · **Task:** spec 110 · **Date:** 2026-09-17

**What happened.** `StoreClient.filled_orders`'s docstring opened "paper mode's balance is
`paper.starting_balances` adjusted by every **recorded** fill". That was the operator's ruling as
first written, and it was superseded on exactly that point on 2026-09-16: the broker's balance
includes every fill **it has executed**, recorded or not.

**Why it matters more than a word.** The superseded sentence is the defect spec 103 fixed, quoted
as the current design in the docstring of the very query the broker calls. A balance counting only
recorded fills lags the broker by one tick — the broker decides a resting entry's fill part-way
through a tick and engine 19 records it at the end of it — and that lag counted the notional twice
on the fill tick, moved `peak_equity` to a figure the account never held, and froze every paper
account on the next tick. A reader who trusted the docstring would have reintroduced it, and the
docstring is the natural place to look for what the read is *for*.

**Fix.** Rewritten to say what it now is: the recorded half of the broker's ledger, with the
broker adding the fills it holds and the store has not seen on top; and the restart source, where
the store is the whole ledger and a fill executed but never recorded must be absent from the
rebuilt positions too, so the two still agree. Invariant 2 is cited for both halves.

**Grep of the lane for other pre-103 wording: one hit, and it was this one.** Searched
`clients/store/`, `clients/paper/`, `db/migrations/`, all eight of my engines and my tests for
"adjusted by every", "recorded fill", "every recorded", "simulated fill" and "ledger". Everything
else already reads "every fill it has executed" — `clients/paper/broker.py:129` and `:365`, and
`engines/risk/README.md:227` — and the two remaining "simulated fill" mentions
(`broker.py:378`, `tests/clients/paper/test_broker.py:632`) are the argument for *why* the ledger
is unconditional in paper rather than a failure path, which is still true.

### Spec 119, diagnosis — the seeded refusal vocabulary, checked against the engines rather than against the finding

**Agent:** B · **Task:** spec 119 · **Date:** 2026-09-18

**What happened.** `clients/store/seed.py`'s `_REJECTION_REASONS` holds fourteen
`(engine, code, sentence)` triples that become `rejections` rows. Checked one at a time against
the named engine's own `contracts.py` — every `REASON_*` string constant the module declares,
which is the same enumeration C's spec 99 test uses — **seven of the fourteen rows name a code
that engine does not declare**, over six distinct bad pairs:

| Seeded engine | Seeded code | Codes the engine actually declares |
|---|---|---|
| `scout` | `outside_universe` | `pair_rules_missing`, `no_live_quote`, `crypto_quoted`, `quote_not_provably_stable`, `no_quote_balance`, `barriers_below_tick_size`, `no_fx_rate`, `insufficient_quote_balance`, `below_ordermin`, `below_costmin`, `scout_inputs_unavailable`, `empty_universe` |
| `skeptic` (×2 rows) | `meta_label_veto` | `skeptic_unavailable`, `skeptic_veto` |
| `anomaly` | `outlier_market_state` | `anomaly_unavailable`, `anomaly_inputs_incomplete`, `market_anomalous` |
| `prediction` | `dissimilarity_index` | `prediction_unavailable`, `prediction_inputs_incomplete`, `di_refused`, `di_percentile_mismatch` |
| `order_book` | `insufficient_depth` | `book_fetch_failed`, `book_unusable`, `book_too_thin`, `no_quote_balance`, `order_book_inputs_unavailable` |
| `decision` | `no_candidate_cleared` | `pair_disagreement`, `stale_bar`, `input_missing`, `no_approved_quantity`, `decision_inputs_unavailable` |

The other seven rows — three `cost` and four `risk` — name codes their engines do declare and are
correct as they stand.

**Why the tracker's list is one short, and it is not a transcription slip.** The finding of
2026-09-16 names five bad pairs and does not name `scout`/`outside_universe`. That one is invisible
from the direction the finding was found from: it was found by spec 99's walking test, which goes
*engines → map*, and `outside_universe` **is** in `REASON_PROSE`, so the console renders it and
nothing complains. The five it did name are the five whose engines are C's; `scout` is mine, and it
is the only bad pair in an engine the finder did not own. Reported to the lead as a disagreement
with the tracker rather than corrected in place.

**Two of the six engines cannot be a `rejected_by` at all, not merely a wrong code.** A
`rejections` row is written by engine 19 only when the *opportunity* chain blocked, `state["scout"]
["pair"]` is present, and the blocking engine published a `reason_code` (`engines/memory/engine.py`,
`_write_rejection`). Engine 9 `order_book` never returns `BLOCK` — it omits its estimate and engine
10 refuses on the absence — which is the operator's ruled case. **Engine 7 `scout` fails the second
condition instead**: it publishes `reason_code=empty_universe` exactly when `candidate is None`
(`engines/scout/engine.py:249`), so on the one tick it refuses, there is no pair, and
`_write_rejection` returns 0 before it ever looks at the code. `scout`'s twelve codes are real, and
none of them can ever reach the `rejections` table — its exclusion codes are a per-pair *tally* on
the universe, not a refusal of a candidate. So repointing that row is not a rename either: the row
changes engine, exactly as engine 9's does.

**A third disagreement, smaller.** Both the finding and spec 119 say `REASON_PROSE` maps both
vocabularies, which is what has kept the console looking right. It maps five of the six:
`dissimilarity_index` was retired from the map by spec 71 and is **not** a key today. The seeded row
still renders, because `operator_reason` prefers the row's own prose sentence when it has one and
only falls back to the map for an empty or code-like `reason` — so the one row whose code is
unmapped is saved by the sentence beside it. Worth recording because it is the mechanism that hid
all of this for six phases, stated exactly: **the console never needed the codes to be real.**

**Why it matters.** Every one of these rows is research data about a refusal the system has never
been able to make, and the rejection feed is the counterfactual dataset the whole exercise exists to
build. Nothing walks from the fixture to the engines, which is the direction that would have caught
it; that walk is what this spec adds.

### Spec 119, fix — the seed's refusal vocabulary is now the engines' own, and two tests walk from the fixture back to them

**Agent:** B · **Task:** spec 119 · **Date:** 2026-09-18

**Fix.** Seven of the fourteen `_REJECTION_REASONS` rows are repointed. No row was deleted, the
list is still fourteen long, and the number of **distinct codes is 12 before and 12 after** — the
variety of reasons the console feed exercises is unchanged, and only two engine *names* leave it,
because neither can be a `rejected_by` in the live chain.

| # | Before | After | Why this one |
|---|---|---|---|
| 1 | `scout` / `outside_universe` | `risk` / `position_open_on_pair` | The engine had to change, not only the code: `scout` can never write a rejection. Invariant 6's one-position-per-pair refusal is the same *question* the retired row asked — is this pair tradable in the account's current state — asked by an engine that can actually refuse a candidate over it |
| 2 | `skeptic` / `meta_label_veto` | `skeptic` / `skeptic_veto` | Engine 15 declares one veto code and one unavailability code. A rename |
| 3 | `skeptic` / `meta_label_veto` | `skeptic` / `skeptic_veto` | The second sentence stays: engine 15 distinguishes nothing finer than a veto, so the variety lives in the prose, exactly as it does for the two `net_edge_below_hurdle` rows |
| 4 | `anomaly` / `outlier_market_state` | `anomaly` / `market_anomalous` | A rename. `REASON_PROSE` already carries a comment saying the engine's code is `market_anomalous` |
| 5 | `prediction` / `dissimilarity_index` | `prediction` / `di_refused` | A rename, and the one row whose code was **not** in `REASON_PROSE` either — spec 71 retired that spelling from the map and the seed kept it |
| 6 | `order_book` / `insufficient_depth` | `cost` / `cost_inputs_unavailable` | **The operator's ruling.** Engine 9 publishes `book_too_thin` and omits `estimated_slippage_pct`; engine 10's `_require` refuses on the absent key with `cost_inputs_unavailable`. The sentence now says what the chain actually did |
| 7 | `decision` / `no_candidate_cleared` | `decision` / `stale_bar` | The engine keeps a row — engine 16 became a gate on 2026-09-16 and its coherence refusal is one nothing else in the fixture exercises — but not that code: `no_candidate_cleared` describes the old "it combines their outputs" reading of engine 16, which is exactly what the gate ruling retired |

**Options rejected, one per mapping that had a real alternative.** Row 1:
`decision`/`pair_disagreement` — rejected because row 7 already gives the fixture a `decision`
row, and because "is this pair tradable in the account's current state" is engine 11's question,
not engine 16's. Row 6: `order_book`/`book_too_thin`, the minimal rename — rejected because it
leaves the row describing a refusal by an engine that never returns `BLOCK`, which is the finding
itself. Row 7: `decision`/`no_approved_quantity` — rejected because engine 11 refusing is
already four rows, while `stale_bar` is the coherence failure only engine 16 can see.

**The test, red before the fix, and the evidence that one test was not enough.** Two tests in
`tests/clients/store/test_seed.py`, both walking fixture → engines, which is the direction
nothing walks. Verbatim, on the pre-fix seed:

```
FAILED tests/clients/store/test_seed.py::test_every_rejection_the_seed_wrote_names_a_code_its_engine_declares[blocks1-dd0.01-loss1-err1]
FAILED tests/clients/store/test_seed.py::test_every_rejection_the_seed_wrote_names_a_code_its_engine_declares[blocks15-dd0.10-loss5-err20]
FAILED tests/clients/store/test_seed.py::test_every_rejection_the_seed_wrote_names_a_code_its_engine_declares[blocks30-dd0.25-loss12-err60]
FAILED tests/clients/store/test_seed.py::test_every_rejection_the_seed_wrote_names_a_code_its_engine_declares[blocks60-dd0.50-loss40-err80]
FAILED tests/clients/store/test_seed.py::test_every_reason_in_the_seeds_vocabulary_names_a_code_its_engine_declares
5 failed, 81 deselected in 14.76s
```

```
AssertionError: the seed's rejection vocabulary carries (engine, code) pair(s) the named engine
does not declare: [('anomaly', 'outlier_market_state'), ('decision', 'no_candidate_cleared'),
('order_book', 'insufficient_depth'), ('prediction', 'dissimilarity_index'),
('scout', 'outside_universe'), ('skeptic', 'meta_label_veto')]
```

**The first threshold case reported five bad pairs, not six**, and the one it missed was
`order_book`/`insufficient_depth`: `_write_rejections` draws a triple at random per bar, so under
that seed the worst row in the list — the operator's own named case — **never reached a
database row at all**. That is why there is a second test walking the module constant rather than
the table. The database walk is the one that describes what the console actually shows; the
vocabulary walk is the one an unlucky draw cannot dodge. After the fix, `5 passed`.

**Nothing but the vocabulary moved.** The committed seed and the working-tree seed were each run
into a fresh database and compared table by table (`seed.py` byte-copied and restored in a
`finally` with the sha256 compared in the same statement, `6194fea090807e23` both arms).
`runs`, `trades`, `positions`, `orders`, `equity_snapshots`, `block_records`, `leaderboard` and
`commands` are **byte-identical**; `rejections` still holds 46 rows and every column but
`rejected_by`, `reason_code` and `reason` is identical row for row. The RNG stream is untouched
because the list is still fourteen entries long, which is why the six Phase 3 fixtures come out
unchanged: the 18-tick outage over two `run_id`s with 5 double-blocker ticks, 2 open positions, 2
resting entry orders, drawdown `0.2000017843760037115020877199`, a losing streak of 8, and 33
trades / 46 rejections.

**Mutations.** `PYTHONDONTWRITEBYTECODE=1`, one mutant at a time, each target byte-copied and
restored in a `finally` with the sha256 compared in the same statement, every anchor asserted to
occur exactly once, no mutant left on disk. Baseline `5 passed, 81 deselected`.

| # | Mutation | Target sha256 | Verdict | Killed by |
|---|---|---|---|---|
| M1 | `("prediction", "di_refused",` to `("prediction", "dissimilarity_index",` — one repointed code reverted to its Phase 0 spelling | `6194fea090807e23` | `4 failed, 1 passed` — **KILLED** | both tests; the one passing case is the threshold set whose draw never picked that row, which is the second test's whole justification |
| M2 | `("anomaly", "market_anomalous",` to `("risk", "market_anomalous",` — a **real** code moved onto an engine that does not declare it | `6194fea090807e23` | `5 failed` — **KILLED** | both tests |
| M3 | **Control.** M2, plus `_declared_reason_codes` widened to the union over every engine's contracts | seed `6194fea090807e23`, test `4e911948274f4f6b` | `5 passed` — **SURVIVED**, and re-run against the whole of `tests/clients/store/` and `tests/db/`: `276 passed` | nothing |

M3 is the one worth keeping. It says the assertion is about **pairs** and not about codes, and that
the per-engine scope of the enumeration is the single clause doing that work: widen it by one line
and a real code filed under the wrong engine passes every test in my lane. M1's split verdict is
the other half — asked *which* test killed it, the honest answer is "one of the two, and under
one draw in four only the vocabulary walk".

**Not touched, deliberately.** `console/format.py` is C's and every code stays mapped until spec
120. C's own `test_the_inverse_is_reported_as_a_warning_and_never_as_a_failure` already names the
five keys this change orphans — `insufficient_depth`, `meta_label_veto`, `no_candidate_cleared`,
`outlier_market_state`, `outside_universe` — as a warning rather than a failure, which is
exactly the list spec 120 retires. `tests/console/` is `365 passed, 1 warning` after the change.

**Consequence.** The seed's docstring now states the rule it was missing: a row's code is picked
out of the engine's module, never composed because it reads well, and engines 7 and 9 are named as
deliberately absent with the reason for each. The fixture-to-engine walk is the half of the seam
spec 99 could not write from the console side.

## Agent C — Interface and models

*Verbatim from `docs/build-log/phase-6/c-interface.md`.*

# Build log — Phase 6 — c-interface

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

### Engine 8's `is_buy` said "not a BUY" when it meant "no call"

**Agent:** C (engines and models) · **Task:** spec 95 · **Date:** 2026-09-16

**What happened.** `PredictionState.is_buy` was declared `is_buy: bool = False` and
`to_state()` published it unconditionally, so all six of engine 8's refusal shapes —
`prediction_unavailable` in its six forms, `prediction_inputs_incomplete`, `di_refused`,
`di_percentile_mismatch` — put `is_buy: false` into `state["prediction"]`. That is the
identical payload a predictor publishes when it ran, scored, and called no BUY. Found by
C-4 during spec 73's mutation sweep on engine 15 and carried out of Phase 5 as an open
item.

**Why.** It is the same design question `expected_move_pct` had already answered the other
way in spec 71, and only one of the two fields got the answer. A pydantic field with a
non-`None` default is published on every path by construction: there is no code in engine
8 that *decides* to publish `is_buy: false` on a refusal, which is why nothing looked
wrong at any call site. The default did it.

Nothing failed open in between, and that is worth being precise about rather than
generous: engine 8's own `BLOCK` stops the opportunity chain under contract rule 6, so the
tick never reached engine 15 at all; and when engine 15 *is* handed such a payload
directly, its spec 73 hardening blocks, because that read is three-way (`bool` or block)
rather than two-way. The cost was to the record, not to the money — `block_records` and
the research dataset could not distinguish two different facts — and to the next reader.
Engine 14 `adaptive_router` (spec 97) is the first consumer of this field that is not a
gate, which is why the operator scheduled the fix before it rather than after.

**Fix.** `is_buy: bool | None = None` in `engines/prediction/contracts.py`, with
`to_state()` omitting the key when `None` in the same shape as `expected_move_pct`, and
`IS_BUY_FIELD` declared beside `EXPECTED_MOVE_FIELD`. Engine 8 needed no logic change:
every refusal already routes through `_blocked`, which takes no `is_buy` argument and so
cannot set one, and the single `OK` return sets it from `is_buy_call(move)` on a model
that has already scored. **The property is stated as a property of the signature** — the
way to break it is to add an `is_buy` parameter to `_blocked`, and there is no reason to.
That is the M4 mutation below.

Engine 15's read did **not** change and must not: the block it returns on a non-`bool`
`is_buy` landed in spec 73, a phase before the payload did, and it is the reason nothing
failed open in the meantime. What changed is its sentence. It used to say "engine 8
published no usable BUY verdict … and no way to know there was none", which was true when
the absence was uninformative; now the absence *is* engine 8's way of reporting a refusal,
so the sentence names which of the two happened and distinguishes the absent case from the
present-but-unusable one. The two READMEs and both contracts modules carry the same
distinction.

**Consequence.** One wording decision worth recording, because it nearly created a test
that could not fail. The first draft of engine 15's new sentence ended "This is not a
non-BUY call; a non-BUY is an explicit false" — and `NOT_A_BUY_CALL` is the literal string
`"not a BUY call"`. The obvious regression assertion is `NOT_A_BUY_CALL not in reason`, and
against that draft it passes for an accidental reason: `"not a BUY call"` is not a
substring of `"not a non-BUY call"`, by four characters. An assertion whose truth turns on
a near-miss of the literal it is checking is one edit away from silently inverting. The
sentence was reworded to avoid the phrase entirely, and the assertion is in both engine-15
tests.

**Why the tests are shaped the way they are.** Spec 95's check is *every refusal shape*,
which is a claim a list of examples cannot make on its own. `refusal_shapes` in
`tests/engines/test_prediction.py` drives ten shapes end to end through the real engines 3,
5 and 6 and the real artefact loader, and a second test asserts that the reason codes those
ten reach are **exactly** the set of `REASON_*` constants the contracts module declares —
the same enumeration `tests/console/test_reason_prose.py` already uses to require operator
prose. A fifth code added tomorrow turns that test red until a shape reaching it joins the
list, which is the part that makes "every" checkable rather than aspirational.

The two scored cases are asserted on their **sign**, not assumed. The fixture window that
`predicted` uses is the one the chain rehearsal calls `NOT_A_BUY_WINDOW_END`, where the
fixture model's expected move is negative; the BUY control runs on the window 200 bars
earlier. Both tests assert the sign before asserting `is_buy`, so a retrained fixture that
moved either answer turns the affected test red by name instead of leaving a branch green
and unreached — the same protection B built into the rehearsal for the same two windows.

And the seam gets one test with no double on either side:
`test_a_refusing_engine_8s_real_payload_blocks_naming_the_absence` induces a real
`di_refused` out of the real engine 8 and hands that payload to the real engine 15. Spec 95
is a change to what engine 8 *publishes*, and Phase 4 found twice in one day that mutating
a module's own logic does not test the fields it exports.

### Spec 95 — four mutations, four killed, and which test killed each

**Agent:** C (engines and models) · **Task:** spec 95 · **Date:** 2026-09-16

**Harness.** `scratchpad/mutate.py`. Every arm runs a **baseline first** and refuses to
report if the tree is already red. The target file is copied to the scratchpad *before*
the mutation and restored from those bytes with `sha256` compared **in the same statement
that writes it back** — never `git checkout --`, because teammates do not commit and that
restores the committed version over their uncommitted work. Every anchor is asserted to
occur **exactly once** in the file before it is replaced. Every file that is not the
variable is hashed on both sides of the arm and the hashes are printed with the result,
because three sessions share this checkout and without that an A/B here measures whichever
save was on disk. All four arms reported `witness files unchanged: True`.

**The arm** is `tests/engines/test_prediction.py`, `tests/engines/test_skeptic.py` and
`tests/engines/test_feature_chain_rehearsal.py` — the two files spec 95 changes plus B's
Phase 5 rehearsal, which is the only other place `state["prediction"]["is_buy"]` is read.
352 tests. **Directories deliberately excluded and why:** the rest of `tests/`, because
nothing else in the repository reads this key — checked by grep across `src/`, `tests/`,
`scripts/` and `console/` — and because the full suite was red in another lane throughout
(see the entry below). Every verdict here is a KILL, and a kill on a subset is a kill; no
survivor is being claimed on a subset, which is the direction the rule guards.

| | Mutation | Verdict | Killed by |
|---|---|---|---|
| M1 | `is_buy: bool \| None = None` back to `is_buy: bool = False` — spec 95's first named one | KILLED | `test_no_refusal_shape_publishes_is_buy`, `test_a_refusing_engine_8s_real_payload_blocks_naming_the_absence` |
| M2 | `to_state` emits the key as `null` instead of omitting it — spec 95's second | KILLED | the same two |
| M3 | engine 15 reads an absent verdict as a non-BUY — spec 95's third | KILLED | 8 tests, listed below |
| M4 | `_blocked` hands `is_buy=False` to `PredictionState` explicitly, leaving the contract alone | KILLED | the same two as M1 |

**M1's red message**, which is the defect in its own words:

```
AssertionError: the no run id configured refusal published is_buy=False, which is the
payload of a predictor that ran and called no BUY
```

**M2's**, showing that null is caught as well as false — the point of omitting rather than
nulling:

```
AssertionError: the no run id configured refusal published is_buy=None, which is the
payload of a predictor that ran and called no BUY
```

**M3 is the one worth reading.** It restores the pre-spec-73 fail-open exactly: the
three-way read collapsed to a truthiness test, so absent, `None` and `0` all take the
not-a-BUY `OK` path. Eight tests went red —
`test_an_is_buy_that_is_not_a_boolean_blocks_rather_than_reading_as_non_buy` in all six
of its parametrisations, `test_a_candidate_with_no_prediction_published_blocks_rather_than_passing`,
and the new seam test. The seam test's message is the whole finding in one line:

```
AssertionError: assert <EngineStatus.OK: 'OK'> is <EngineStatus.BLOCK: 'BLOCK'>
  ... data={'pair': 'AAAUS..., 'vetoed': False, 'reason': 'not a BUY call', ...}
```

A tick on which engine 8 refused, reported by the last gate as a call the predictor made
and did not like. That is what spec 95 and spec 73 between them prevent, and it is worth
noting which half does the preventing: **engine 15's block is what stops it, not engine
8's omission.** The omission makes the payload honest; the three-way read is the safety.
Removing either leaves the other holding — removing both is M3 plus M1 together, and
nothing would object.

**M4 is the mutation the contract change alone does not cover**, and it is the reason the
"no `is_buy` parameter on `_blocked`" property is worth stating out loud rather than
leaving as an accident of the current code. With `is_buy: bool | None = None` still in
place, a refusal path can publish a verdict simply by passing one, and the field's type
gives no warning. It is killed by the same two tests, which is the answer to "is the
contract change on its own enough" — no, and the behavioural tests are what cover the gap.

**Equivalent mutants, reported as checked negatives rather than survivors.** None was run.
The two obvious candidates are not equivalent and are covered above; there is no third
edit to this field that leaves behaviour unchanged.

### One red test at the spec 95 gate, and it is not spec 95's

**Agent:** C (engines and models) · **Task:** spec 95 · **Date:** 2026-09-16

**What happened.** `tests/console/test_real_rows.py::test_every_reason_code_engine_19_can_write_is_in_the_map`
fails: *"Left contains 2 more items, first extra item: `entry_resting_on_pair`"*.

**Why.** B's spec 89 added `REASON_ENTRY_RESTING_ON_PAIR` and `REASON_POSITION_OPEN_ON_PAIR`
to `engines/risk/contracts.py`, and spec 89 step 6 hands both codes to C's spec 99 for
operator prose in `console/format.py`. Spec 99 is the **verification-and-interface** half
of lane C, not this session — the task list splits lane C into disjoint files precisely so
two sessions never touch `console/format.py` at once. So this is a seam mid-flight between
two specs, doing exactly what the seam was designed to do: a code with no prose renders
"No reason was recorded." silently, and that test is the thing that stops it being silent.

I applied the three questions `code-standards.md` puts under "it is in another agent's path
is evidence, not a verdict", because a path heuristic that is right three times in four is
how the fourth case hides. Does it name my file? No — `engines/risk/contracts.py` and
`console/format.py`, neither mine. Does it reproduce every time? Yes. Is it caused by a
string I just wrote? No: `grep -rn entry_resting_on_pair src/ tests/` finds it in B's
contracts module and B's test only, and nothing in spec 95 touches a reason code at all.

**Fix.** Not mine to make. Reported to the lead for spec 99. Recorded here because it is
the reason `toolchain_green` cannot be green on this tree, and the next person to run the
gate should not spend the diagnosis twice.

### The DI paid for the whole reference set once per scored row

**Agent:** C (engines and models) · **Task:** spec 102 · **Date:** 2026-09-16

**What happened.** `di.score` costs about 1.13 ms a row at the test suite's sizes and about
136 ms a row at the full run's reference size, and the leave-one-out over a 200,000-row
reference takes roughly twenty minutes of one core. It is the test suite's largest single
cost at 3.1 s per trained fold, and every Phase 6 gate run pays it six times.

**Why — the time.** `_mean_nearest` computes `np.sum(reference**2, axis=1)` **inside its
chunk loop**, and `score()` calls it with a single query row. `research/training.py::_fit_di`
then scores the fold's test rows one at a time in a Python `for`. So each scored row squares
and sums the entire reference matrix: at the full run's size that is 200,000 x 117 float64,
about 187 MB allocated, written and read, **per row**. The k-nearest search the function
exists to do is O(N) on a vector of 200,000 distances and costs a fraction of that. The cost
is therefore linear in reference size for a reason that has nothing to do with the statistic
being computed, which is why it did not look wrong: every individual piece of that function
is the right arithmetic, and the only thing wrong is where the loop boundary sits.

**Why — the memory, which is the half that will not merely be slow on a smaller machine.**
The leave-one-out builds its exclusion mask as
`np.abs(decision_ts[None, :] - stamps[:, None]) <= exclusion_s`. At `_CHUNK = 512` against a
200,000-row reference that is an 819 MB int64 intermediate plus a 102 MB boolean, allocated
391 times, beside an 819 MB float64 distance block and an 819 MB squared block. The twenty
minutes is very unlikely to be the matrix multiply — 200,000² x 117 is about 4.7 TFLOP, which
a threaded BLAS does in a couple of minutes — and much more likely to be four gigabyte-scale
allocations per chunk starving it.

**Why it has not bitten yet.** The committed fixtures are small: the suite's reference sets
are in the low thousands of rows, where 187 MB becomes 2 MB and the whole defect reads as
"the DI is a bit slow". The full-archive numbers in the goal are the ones that make it a
prerequisite, and they came from a run nobody had a reason to profile until the gate started
paying for it six times.

**Fix.** Four changes, all arithmetic-preserving; the scope limit forbids touching k, the
percentile, the window, the exclusion, the scaler or what is refused, and none of these does.

1. The reference norms are computed **once per call** rather than once per chunk. Same
   values, same order, fewer times.
2. A batched `score_many(fitted, matrix)` chunking query rows against a **fixed element
   budget** rather than a fixed row count, so peak memory is a property of the reference
   size and not of how many rows are being scored. `research/training.py` calls it; engine 8
   keeps `score` for its single live vector and `score` delegates to the same code path, so
   the offline and live readings cannot drift — the same reason spec 72 narrowed one scaler
   rather than writing the arithmetic twice.
3. The pairwise-timestamp mask is replaced by the `searchsorted` bounds `fit` already
   computes for its own too-short-reference check: the excluded columns are a contiguous
   range in timestamp-sorted order, so they are set to infinity by index. **The set of
   excluded columns is identical by construction** — the same two bounds, in exact integer
   arithmetic — so this change is bit-for-bit rather than merely close, and the reference's
   own column order is untouched.
4. The partition runs on **squared** distances and the square root is taken of only the k
   selected. `sqrt` is monotone and correctly rounded, so the k smallest squared distances
   are the k smallest distances, their roots are the same floats, and sorting ascending
   before the mean puts them in the same summation order.

**The one place equivalence is not bitwise, stated rather than discovered.** Change 2 turns
a one-row GEMV into a many-row GEMM, and BLAS is entitled to associate differently. DI values
may move in the last few ulp. Spec 102 anticipates this and asks for a stated tolerance
justified in the docstring; the tolerance is measured rather than picked, and **refusals are
asserted identical with no tolerance at all**, because the refusal is the only thing anything
downstream can see. The residual risk — a row sitting within a few ulp of the threshold could
in principle flip — is inherent to any reassociation and is recorded here rather than left
for someone to find.

**Deliberately not written: a whole-run per-fold memory test.** Spec 102 says so and the
reason is worth repeating, because the absence otherwise looks like an omission. The
skeptic's training set grows every fold by design — it is the accumulation of every earlier
fold's out-of-sample BUY calls — until prerequisite 1 is ruled under spec 83. A test
asserting per-fold memory is flat cannot be green today, and one written against the capped
methodology would be a test of a methodology the operator has not chosen.

### Spec 99, first increment — the two spec 89 codes, and the red they trade for

**Agent:** C (verification and interface) · **Task:** spec 99 · **Date:** 2026-09-16

**Diagnosis, written before the fix.** `tests/console/test_real_rows.py::test_every_reason_code_engine_19_can_write_is_in_the_map`
fails with *"Left contains 2 more items, first extra item: `entry_resting_on_pair`"*. The
enumeration walks `acsoe.engines.risk.contracts` for `REASON_*` string constants and finds two
that `REASON_PROSE` does not carry: `position_open_on_pair` and `entry_resting_on_pair`, both
added by B's spec 89 (`contracts.py:182` and `:192`). Spec 89 step 6 hands the prose to spec 99,
which is this session. `C-models` diagnosed the same failure independently at the spec 95 gate
and correctly declined to fix it; the entry above this one is that diagnosis, and this is the
same fault seen from the owning side.

**It is the seam working, not a surprise.** A code with no entry in the map renders
"No reason was recorded." with no exception, no log line and no visibly degraded screen — the
one genuinely silent failure the console has, and the reason the enumeration exists. It went
red within a day of B landing the constants, which is the whole return on that test.

**The wording is B's, kept verbatim.** `position_open_on_pair` -> "This pair already holds an
open position"; `entry_resting_on_pair` -> "This pair already has an entry order resting on the
book". Same arrangement as engines 4, 7, 10 and 11: the producer writes the sentence and the
consumer does not paraphrase it, so the two cannot drift. Two sentences rather than one because
B's contract note is explicit that the two states are cleared by different actions — a position
is exited, an order is cancelled — and the operator reading the rejection row needs to know
which. `test_no_two_codes_share_a_sentence` would refuse one shared sentence anyway, which is
the same ruling enforced from the other end.

Neither sentence carries a number, a threshold or a cause, per spec 46: engine 11 writes prose
with the actual figure and `operator_reason` prefers the row's own text over this table.

**This deliberately turns a second test red, in B's lane.**
`tests/engines/test_risk.py::test_the_two_codes_spec_89_added_are_still_waiting_on_cs_prose`
asserts the codes are *absent* and is written to fail the moment C lands; its own failure
message says to move them into the renderable list and delete the tripwire. That file is B's
and I did not edit it. Reported to the lead and to B in the same breath as the fix, so the tree
is never red without somebody knowing which red is which.

### The gate list went red because a document changed, which is the arrangement working

**Agent:** C (verification and interface) · **Task:** spec 99 / housekeeping · **Date:** 2026-09-16

**What happened.** `tests/verify/test_phase0_criteria.py::test_is_gate_parses_the_registry_out_of_the_document`
fails on a clean tree:

```
AssertionError: assert {'anomaly', '...'safety', ...} == {'anomaly', '... 'scout', ...}
  Extra items in the left set:
  'decision'
```

**Why.** The operator ruled engine 16 `decision` a gate on 2026-09-16 (ruling 2), and the lead
put the **Y** into the Gate column of `context/engine-contracts.md` under spec 80. That test
does not read a list of gates from anywhere — it parses the registry table out of the document
and pins the parsed result against seven names written out by hand. The hand-written set is the
point. `verify.py`'s `is_gate_matches_registry` criterion checks that each *registered engine's*
`is_gate` attribute agrees with the document, so the document is the authority for everything
downstream of it; nothing else in the suite would notice if the document itself grew a gate. So
one test holds the document to a set a human has to retype, and widening the gate list is a
deliberate act with a red test in front of it — including when the lead is the one widening it.

**Fix.** `decision` added to the expected set, eight names now. The test keeps its shape: it
still parses, still asserts 23 rows, still spot-checks `data_guard` as a gate and `exchange` as
not one, and still compares against an enumerated literal rather than against anything derived
from the document. Making it derive the set from the same table it is checking would turn it
into a tautology that can never fail, which is the one change that must not be made here.

### The walk over every engine found four silent codes, and two are a phase old

**Agent:** C (verification and interface) · **Task:** spec 99 · **Date:** 2026-09-16

**What happened.** `tests/console/test_reason_prose.py` grew the walk spec 99 asks for — import
every `acsoe.engines.*.contracts`, collect every module-level `REASON_*` / `HOLD_*` string
constant, require each value to be a key of `REASON_PROSE`. It went red on its first run naming
four codes:

```
AssertionError: these engines publish a code with no operator prose, so it renders
'No reason was recorded.' on the console, silently:
engines/position_manager/contracts.py::HOLD_DATA_GUARD_BLOCKED = 'data_guard_blocked',
engines/position_manager/contracts.py::REASON_POSITION_UNRECORDABLE = 'position_unrecordable',
engines/regime/contracts.py::REASON_NO_FEATURE_ROW = 'no_feature_row',
engines/regime/contracts.py::REASON_NO_INPUTS = 'regime_inputs_incomplete'
```

**Why, and why the two halves are different findings.** The two from engine 21 are expected:
B landed them under spec 92 yesterday and B's own contracts module says *"Flagged to C for
`REASON_PROSE` (spec 99)"*. The seam worked as designed.

**Engine 12 `regime`'s two are the finding.** They have been on disk since Phase 5 and nothing
noticed, because until now this file enumerated one module per test and there had never been a
test named after engine 12. That is the exact failure spec 99 predicts in the abstract — "the
existing enumeration walks gates, and none of 9, 14, 18, 21, 22 is a gate" — turning up in a
place nobody listed: engine 12 is not a gate either, it is a phase old, and it was already
live. Six single-module tests written one per engine cannot catch the seventh engine; that is
not a property of the engines, it is a property of listing things by hand.

They render as silence rather than as a code, which is worth being exact about because the two
failures look different on screen. Engine 12 writes the bare code into `reason` and publishes no
`reason_code`, so `operator_reason("", "no_feature_row")` takes the `_CODE_LIKE` branch — the
stored text is recognised as a code and refused, the map lookup is on an empty string, and the
operator gets "No reason was recorded." on the one field whose job is to say why the market was
not classified. Engine 14 `adaptive_router` is about to read `state["regime"]["label"]` under
spec 97, so the tick where the label is `null` is about to matter more than it did.

**Fix.** Four sentences in `REASON_PROSE`. Engine 21's two are **my wording, not B's** — B is
not running and the precedent is already in this file for `no_fx_rate` and
`barriers_below_tick_size`, added the same way with B asked to replace them if wrong. Engine 12's
two are mine because engine 12 is lane C's and `C-models` is not running either. All four obey
spec 46: no number, no threshold, no cause the row did not carry.

`data_guard_blocked` is the first **hold** reason to get a sentence, and it is deliberately not
written as a refusal. Nothing was rejected; the manage chain declined to compute a barrier from
data the guard had already refused, and the position is still being watched. An operator told
"blocked" would go looking for a fault, so the sentence says what is paused and what is not.

**Two things the walk had to be built not to do**, both of which would have made it green and
useless:

- **Pass on an empty walk.** `unmapped == {}` is satisfied by reading nothing at all, and
  `pkgutil.iter_modules` returning nothing is a plausible accident. So the import-system answer
  is compared against an independent filesystem scan for `engines/*/contracts.py`, five engines
  that certainly exist must be in it, and four codes that certainly exist must have been
  collected out of it.
- **Exempt a real code by shape.** Three constants carry the `REASON_`/`HOLD_` prefix and are
  *not* codes: `memory.REASON_CODE_FIELD`, `memory.HOLD_REASON_FIELD` and
  `position_manager.HOLD_REASON_FIELD`, all naming a place in `state` rather than a value. The
  codebase convention is `*_FIELD`/`*_KEY`/`*_PATH` for a location, and skipping on that suffix
  alone is a rule a future real code could satisfy by accident — `REASON_TIMEOUT_FIELD` would
  vanish from the map with nothing to notice. So the inventory is pinned exactly and a fourth
  such constant turns the suite red and gets a decision. **Raised with the lead as a convention
  question**, per spec 99 step 5: both modules belong to other agents and the scope limit forbids
  renaming somebody else's constant to suit this test.

`BLOCK_REASON_KEY = "block_reason"` in `engines/memory/contracts.py` is the near miss that needed
no rule: it contains "REASON" but starts with neither prefix, and it names a location, so it is
out of scope rather than exempted.

**The inverse, as spec 99 step 4 asks, is a warning and not a failure.** Five prose keys no
engine publishes today — `insufficient_depth`, `meta_label_veto`, `no_candidate_cleared`,
`outlier_market_state`, `outside_universe`. Four are the seed generator's older spellings on
seeded rows that still have to render, and `insufficient_depth` is engine 9's, which does not
exist yet. Pinning that list would make it fail for cosmetic reasons on somebody else's change;
warning makes a retired code visible without that.

### Spec 99 — five mutations, five killed, and which test killed each

**Agent:** C (verification and interface) · **Task:** spec 99 · **Date:** 2026-09-16

**Harness.** `scratchpad/mutate_99.py`, `mutate_99b.py` and `mutate_99c.py`. Every arm runs a
**baseline first** and refuses to report if the tree is already red. The target is copied to the
scratchpad *before* the mutation and restored from those bytes with `sha256` compared **in the
same statement that writes it back** — never `git checkout --`, because teammates do not commit
and that would restore the committed file over their uncommitted work. Every anchor is asserted
to occur **exactly once** before it is replaced. Four files that are not the variable are hashed
on both sides of every arm and printed with the result. All five arms reported
`witness files unchanged: True` and `restored exactly: True`.

**The arm** is `tests/console/test_reason_prose.py` alone, 118 tests. Nothing else in the
repository reads `REASON_PROSE`'s completeness — `tests/console/test_real_rows.py` reads the map
but for engine 19's subset, and it was green throughout. Every verdict below is a KILL; no
survivor is claimed on a subset, which is the direction the rule guards.

| | Mutation | Verdict | Killed by |
|---|---|---|---|
| A | An unmapped `REASON_A_CODE_NOBODY_MAPPED = "tournament_fold_count_changed"` added to `engines/tournament/contracts.py` | KILLED | `test_every_code_every_engine_publishes_has_operator_prose` **and** `test_every_reason_code_tournament_declares_has_prose` |
| B | The same, in `engines/regime/contracts.py` — an engine with **no** per-module test | KILLED | `test_every_code_every_engine_publishes_has_operator_prose`, alone |
| C | `CODE_PREFIXES` mistyped to `("REASONS_", "HOLDS_")`, so the walk reads every module and collects nothing | KILLED | `test_the_walk_collects_codes_and_not_merely_modules`, `test_the_state_field_constants_are_pinned_rather_than_exempted_by_shape`, `test_the_inverse_is_reported_as_a_warning_and_never_as_a_failure` |
| D | The walk iterates an empty list instead of `pkgutil.iter_modules` | KILLED | `test_the_walk_reaches_every_engine_on_disk`, plus the three above |
| E | One entry dropped from the pinned `STATE_FIELD_CONSTANTS` inventory | KILLED | `test_every_code_every_engine_publishes_has_operator_prose`, `test_the_state_field_constants_are_pinned_rather_than_exempted_by_shape` |

**A and B are the same mutation in two places, and the difference between them is the finding.**
A is killed twice, because engine 20 already had a per-module test written when engine 20
landed. B is killed **once**, by the walk:

```
AssertionError: these engines publish a code with no operator prose, so it renders
'No reason was recorded.' on the console, silently:
engines/regime/contracts.py::REASON_A_CODE_NOBODY_MAPPED = 'regime_model_absent'.
Add a sentence to REASON_PROSE in src/acsoe/console/format.py.
```

Without the walk that mutation survives the entire suite, and survives it *silently* — which is
precisely how engine 12's two real codes sat unmapped for a phase. A mutation killed only by the
new test is the only kind of evidence that the new test was worth writing.

**C and D are the vacuous-pass arms**, and they are the ones a walk most needs. Both leave the
headline assertion green — nothing collected means nothing unmapped — and both are caught by the
guards instead:

```
AssertionError: the walk and the filesystem disagree about which engines exist;
only imported: []; only on disk: ['anomaly', 'cost', 'data_guard', 'exchange', ...]
```

**E proves the exemption inventory is load-bearing rather than decorative.** Drop
`("memory", "REASON_CODE_FIELD")` and the walk immediately demands prose for `reason_code` —
which is the *name of a column*, not a code. That is the shape of the mistake the pinning
prevents in the other direction too: a real code named `REASON_SOMETHING_FIELD` skipped by a
suffix rule nobody had to think about.

**Equivalent mutants, reported as a checked negative rather than a survivor.** One was
considered and not run: widening `CODE_PREFIXES` to include a prefix no engine uses
(`("REASON_", "HOLD_", "REFUSAL_")`) changes nothing today and would be equivalent by
construction rather than by test weakness. It is recorded here because "no survivors" is only
meaningful if the arms that could not have survived are named.

### `Path.write_text` rewrote every line of a file it was not asked to change

**Agent:** C (verification and interface) · **Task:** spec 99 · **Date:** 2026-09-16

**What happened.** After appending the walk to `tests/console/test_reason_prose.py` with a short
Python script, `git diff --stat` reported 250 changed lines in a file I had added 250 lines to —
which looked right — but `git diff` warned *"CRLF will be replaced by LF the next time Git
touches it"*, and a byte count showed **663 CRLF and zero LF**. The same had happened to
`docs/build-log/phase-6/c-interface.md`.

**Why.** `Path.write_text` opens in text mode, and on Windows text mode translates every `\n` to
`\r\n` on the way out. Reading a LF file and writing it back through `write_text` therefore
rewrites every line in the file, not only the ones that changed. `.gitattributes` in this repo
is `* text=auto eol=lf` precisely because line endings are evidence here — every committed
fixture is compared byte for byte by `verify.py` — so a working tree quietly converted to CRLF
is the class of thing that file exists to prevent.

It also corrupted two mutation arms before it was noticed: the harness's mutant step did
`write_text` on an already-CRLF string, producing `\r\r\n`, and pytest's line numbers in those
runs came out roughly doubled. The *verdicts* were unaffected and the restores were exact —
the restore path uses `write_bytes` and compares sha256 — but the evidence was not clean, so
arms C and D were re-run on the corrected file and the table above is from that run.

**Fix.** Both files converted back with `write_bytes(data.replace(b"\r\n", b"\n"))`; `git diff`
now shows insertions only. The mutation harness writes mutants with `write_bytes` as well, so a
mutant differs from its original in exactly the anchor and nothing else — which is what the
witness-hash check was already claiming and could not previously have caught, because the
witnesses are the files the arm does *not* touch.

**Consequence.** Any script in this repository that edits a tracked file must write bytes, not
text. `B`'s `engines/risk/engine.py`, `engines/risk/README.md` and `tests/engines/test_risk.py`
are CRLF in the working tree right now for what is very likely the same reason; that is B's lane
and is reported rather than fixed here.

### Spec 100 — the nine criteria registered while every one of them is PENDING

**Agent:** C (verification and interface) · **Task:** spec 100 · **Date:** 2026-09-16

**What this entry is for.** Registering criteria is routine and would not belong here.
Three things about *these* are not routine, and two of them are defects the tests caught
in the criteria themselves.

**The first draft judged the wrong repository, and the test found it.** Every Phase 6
criterion looked up its engines with `try_import`, with no `root_import_path(ctx.root)`
around the body. That is not an import-hygiene nicety: `ctx.root` is the entire reason a
criterion takes its repository as a parameter, and without the context manager the nine
criteria imported the **installed** `acsoe` regardless of which tree they were pointed
at. On this machine that is the same repository, so all nine reported plausibly and the
defect was invisible — a criterion that always reports on the developer's own checkout
is exactly the fresh-clone failure the rule exists to prevent, wearing the costume of a
passing criterion.

It was found by the two tests in `tests/verify/test_phase6_criteria.py` that fabricate a
subject into a copied tree and ask what the criterion thinks: both reported "does not
exist yet" about a module sitting in the tree they had just written it into. Every check
now opens `with root_import_path(ctx.root):` before it looks anything up, which is what
every criterion from Phase 1 onward already did.

**An absent fixture and an empty one are different faults, and only one is PENDING.**
Absent means nobody has cut it yet: a schedule fact, and the owning spec is named.
**Empty is a FAIL**, because a deposited file carrying nothing reads downstream as "the
walk found no levels" or "the leaderboard has no models" — the vacuous pass this project
has been burned by three times. Both branches are driven to a verdict in the tests
rather than described, because `_phase6_fixture`'s FAIL branch is otherwise unreachable
until spec 96 deposits something, and a branch nobody has executed is a comment.

The same distinction one level up: an engine module that imports and declares no engine
class gets its own sentence rather than "does not exist yet". A PENDING that sends
somebody to write a file already sitting there is worse than no PENDING, and this phase
opened on exactly that state in another lane — `modelling/di.py` naming `score_many` in
`__all__` and not defining it.

**A test that could not tell its own rule from a violation of it, twice.**
`test_no_criterion_reads_data_models_or_logs` reads the Phase 6 section of `verify.py`
and checks that no criterion reaches into a gitignored directory. The first version
searched the text for `data/`, `models/` and `logs/` and went red on the section's own
prose explaining why it must not read them. The second stripped comments and strings
with `tokenize` and searched the code, which is worse in two ways at once: it drops the
string literals a path is actually built from, and `data_guard` matches "data" in an
identifier — so it reported a violation where there was none and would have missed a
real one. The third parses the section and searches **non-docstring string literals**,
which is what a path is, with a guard that at least one path literal was found so the
search cannot pass vacuously. Recorded because the wrong two versions both looked right.

**Why all nine are PENDING and why that is the deliverable.** Engines 18 and 22 are B's
and unbuilt, engines 9 and 14 are `C-models`'s and unbuilt, and neither committed fixture
is cut. A criterion exists so it can report PENDING, and PENDING is what stops a phase
with nothing in it looking finished — `--phase 6` carried `docs_vocabulary` and
`toolchain_green` alone until this landed and would have printed "Phase 6 is green" over
a phase in which nothing had ever placed an order. Each PENDING names the engine by
number, the spec that owes it, and the fee regime it will run in when it does.

### The fee tier is named once, in a fixture, because four files had already copied it

**Agent:** C (verification and interface) · **Task:** spec 100 · **Date:** 2026-09-16

**What happened.** Ruling 8 requires every trade-driving criterion to run at fee tier 3
and to say so in its own message. Before writing them I looked at how tier 3 was already
being set, and found `set_fee_tier(tier=3, maker_fee_pct="0.0011", taker_fee_pct="0.0019")`
typed out by hand in four test files — B's paper broker tests, B's engine 21 tests, A's
engine 1 tests and the harness's own.

**Why that is a problem specifically here.** Nothing was wrong with any of the four. But
"tier 3" is about to become a claim that appears in a verdict the operator reads, and
four hand-typed copies of a pair of decimal strings is four opportunities for two
criteria to mean different things by the same sentence — silently, because both numbers
are plausible and neither is checked against anything.

**Fix.** `tests/fixtures/kraken/fee_tiers.json` names the tiers, `fee_tier_profile(tier)`
reads them, `FakeKrakenClient.use_fee_tier(tier)` applies one **and returns the profile
it applied**, so the tier a criterion reports and the tier it ran at are one object
rather than two statements that happen to agree. `tier_sentence(tier)` is the clause the
criteria embed, and it lives beside the profile for the same reason.

Five properties are asserted rather than assumed, and three of them are the ones a typo
breaks. The named tier 1 is pinned **equal to `trade_volume.json`'s default envelope**,
so the fake's default tier and its named tier 1 cannot disagree — "no trade at tier 1"
would otherwise mean two different things depending which route a test took. An unnamed
tier **raises** rather than falling back to tier 1, because a fake kinder than reality
hides fail-closed bugs and a silent fallback would give a criterion a no-trade regime
while its message said otherwise. And tier 3's fees are asserted lower than tier 1's on
both sides: a tier-3 profile carrying tier-1 numbers would leave every Phase 6 criterion
in the no-trade regime while reporting that it was not, and every one of them would
simply find no candidate — a whole phase of criteria passing for the wrong reason.

Not asserted, deliberately: the friction and the hurdle. Those are engine 10's
arithmetic, and a criterion that recomputed them here would be checking its own sum.
`fees_round_trip_pct` exists and its docstring says in as many words that it is **not**
the friction the gate hurdles against.

**One more, and it is the standing rule rather than a new one.**
`test_no_fee_number_in_the_fixture_reaches_src` searches `src/` for the literal strings,
not for the filename. `AGENTS.md` is explicit that a fee percentage in `src/` is stale by
definition, and the way one gets there is not by importing a fixture — it is by somebody
typing the number.

### The walk caught engine 16 within minutes of it landing, which is the second time today

**Agent:** C (verification and interface) · **Task:** spec 99 · **Date:** 2026-09-16

**What happened.** A full run of `tests/verify tests/console tests/harness` went red on
`test_every_code_every_engine_publishes_has_operator_prose` naming five codes that had
not existed when the previous run of the same file passed:

```
engines/decision/contracts.py::REASON_INPUTS_UNAVAILABLE = 'decision_inputs_unavailable',
engines/decision/contracts.py::REASON_INPUT_MISSING = 'input_missing',
engines/decision/contracts.py::REASON_NO_APPROVED_QUANTITY = 'no_approved_quantity',
engines/decision/contracts.py::REASON_PAIR_DISAGREEMENT = 'pair_disagreement',
engines/decision/contracts.py::REASON_STALE_BAR = 'stale_bar'
```

**Why.** B landed engine 16 `decision` (spec 90) while I was working, in the same
checkout. Nobody messaged anybody; the test simply noticed. Before the walk existed this
would have required somebody to write `test_every_reason_code_decision_declares_has_prose`
by hand, and the evidence that nobody reliably does is engine 12 `regime`, whose two
codes went unmapped for a whole phase for exactly that reason.

**Fix.** Five sentences, my wording with B asked to replace any that is wrong, on the
same terms as engine 21's earlier today. One wording constraint worth recording: engine
16 is a gate that **composes** the order intent and never decides — the operator's ruling
2 and the engine's own README say so in those words — so none of the five sentences says
"decided". A README that says composes and a console that says decided would put the
ruling back at issue in the one place nobody looks.

**Consequence, and it is the reason this is a separate entry rather than a line in the
one above.** The walk has now paid for itself twice on the day it was written, on two
engines nobody had a per-engine test for, one of them a phase old and one of them an hour
old. The interval between a code landing and the console being able to render it is now
bounded by a test run rather than by whether somebody remembered.

### The PENDING that moved, and why that is the mechanism rather than the friction

**Agent:** C (verification and interface) · **Task:** spec 100 · **Date:** 2026-09-16

**What happened.** The same run turned three Phase 6 criterion tests red:
`test_pending_on_the_real_tree_names_the_subject_and_the_spec` for the three round trips
and for `console_shows_position_live`, each asserting the PENDING line named "engine 16
`decision`" and "spec 90".

**Why.** Because engine 16 now exists. The criteria correctly moved on to naming engine
18 `execution` and spec 91, and the mapping that pins what each PENDING must say had not
moved with them.

**Fix.** `AWAITED` updated to engine 18, with a note saying the mapping moves as the
phase is built and has now moved once. This is the intended behaviour and was written
down before it happened: without it, a criterion can go on reporting PENDING for a reason
that stopped being true, and a gate cannot tell that state apart from progress. The cost
is one deliberate edit per engine landed; the alternative is a PENDING line nobody has
read since it was written.

### A real BUY above the tier-3 bar can be produced honestly, and here is the measurement

**Agent:** C (verification and interface) · **Task:** spec 100 step 2 · **Date:** 2026-09-16

**What this settles.** Spec 100 step 2 asks for a candidate that is *a real BUY with an
expected move above the tier-3 bar of 1.625%*, produced by the real predictor, not
refused by the DI and not vetoed — and says that if it cannot be produced honestly, that
is a finding for the lead rather than something to route around with a hand-built
`state`. It can be produced. This entry is the measurement, because "a real BUY exists"
is exactly the kind of claim that gets repeated as fact later.

**What is fabricated, and it is one function.** The prices. The labeller, the feature
module, `research/training.py`, the calibrator, the DI and the anomaly detector are the
committed ones, reached through `verify.py`'s existing `_trained`, which gained an
optional `candles_builder` parameter so Phase 5's unremarkable market and Phase 6's
planted one come out of the same pipeline.

**The pattern had to be something a feature vector can see.** Planting "the price goes
up later" is not plantable: the model reads one row of `FEATURE_NAMES` and has no view
of the future. So the signature is four bars of a straight, positive, volume-breaking
climb — `log_return_4`, `efficiency_ratio_4`, `volume_z_4` — and the 4.5% rise that
follows over eight bars is what the real labeller turns into a `target` before the 1.5%
stop can be touched. A `-2.2%` bar later in each cycle supplies the `stop` label, because
a dataset of nothing but `target` and `timeout` teaches a predictor that the stop never
happens, and every expected move it produces is then too high by exactly the term that
is supposed to subtract.

**Measured, 140 days over two pairs, two folds, ~9 seconds to train:**

```
oos rows 2688 · BUY calls 794 · DI refusals 7
BUYs above the tier-3 bar of 0.01625: 656
p_target over those: min 0.702, p25 0.921, p50 0.982
expected move: min 0.0166, p50 0.0292, max 0.0300 (the target barrier, as the ceiling)
realised labels of those 656: target 597, stop 57, timeout 2
```

Fifty-seven of the rows the model calls a BUY on above the bar end at the **stop**. That
is the number that matters most here, and it is not a defect: it is the evidence that the
pattern was learned rather than memorised, and it means the chain will be driven by
candidates the model is wrong about as well as ones it is right about.

**The first version of the series was memorised and was reshaped.** Every signature was
followed by the rise, and the model returned `p_target` of 0.97 and above with `p_stop`
at nine decimal places of zero. Nothing about that is incorrect, and it is a poor
subject: a chain driven by a certainty never exercises the paths that exist *because* the
model is unsure, and a calibrator fitted on perfect separation is not a calibrator
anybody has tested. One signature in five now drifts down instead, which is where the
spread above came from.

### The assertion I wrote against that memorisation was asking the calibrator not to be isotonic

**Agent:** C (verification and interface) · **Task:** spec 100 step 2 · **Date:** 2026-09-16

**What happened.** Having reshaped the series, I asserted the property directly:
`max(p_target) < 0.99` over the BUY rows. It failed at `0.9999999979999998`, and kept
failing after I changed the planting period from 96 bars to 89 and replaced the cycle
arithmetic with a scramble.

**Why — and the first diagnosis was wrong, which is the part worth recording.** My first
explanation was that the clock features were leaking: `PLANTED_PERIOD` of 96 bars is
exactly 24 hours at a 15-minute bar, so every signature fell at the same time of day and
`hour_sin`, `hour_cos`, `weekday_sin` and `weekday_cos` could carry it. That is a real
hazard and the change to 89 bars — prime, and not a divisor of a day — is worth keeping.
It was not the cause. The maximum did not move.

The cause is that `modelling/calibration.py` fits an **isotonic** regression per class.
An isotonic fit is a step function, and when the top bin is pure its step is 1.0 — clipped
to `1 - 2e-9` by the storage form. Forty-eight per cent of the BUY rows sit in that top
step. Nothing is wrong with the model, the series or the calibrator: I had written an
assertion that can only pass if the calibrator stops being isotonic, and it would have
kept failing for as long as the top bin was pure, which is most of the time on any
separable problem.

**Fix.** The property is asserted where it actually lives — in outcomes. The subject must
produce BUY rows above the bar that the real labeller ends at something **other** than
`target` (57 of 656 do), and `min(p_target)` must be short of certain (0.702). Both are
statements about the model having learned a tendency rather than a rule, and neither
demands anything of the calibrator's shape. A probability *ceiling* was the wrong
instrument: what "not memorised" means is "wrong sometimes", and that is measurable
directly.

**Consequence.** The 89-bar period stays. A planting period that divides the day is a
real leak into the clock features even though it was not this one, and finding out that
it was not required changing it first — which is the cheaper order.

### The fresh-clone test took four versions, and the fourth is the first that states the rule

**Agent:** C (verification and interface) · **Task:** spec 100 · **Date:** 2026-09-16

**What happened.** `test_no_criterion_reads_the_repositorys_data_models_or_logs` checks
that no Phase 6 criterion reaches into a gitignored directory. Versions one and two are
recorded in an earlier entry: a substring search that went red on the section's own
prose, and a `tokenize` strip that dropped the string literals a path is built from while
matching "data" inside `data_guard`. Version three searched non-docstring string literals
and passed — until the trade-producing subject landed and it went red on
`tmp / "subject" / "models"`.

**Why that was the test being wrong rather than the code.** That is a **temporary**
directory that happens to be called models, which is exactly where the subject's
artefacts are supposed to go, and `_trained` has constructed the same path since Phase 5.
The rule was never "do not write the word models"; it is "do not read *this repository's*
`data/`, `models/` or `logs/`", and versions one to three were all searching for the word.

**Fix.** Version four checks the rule. Every `/` chain in the section whose leftmost
operand is `ctx.root` or `REPO_ROOT` is walked and its string segments refused, with a
guard that at least one such chain was found so the check cannot pass vacuously; and
separately, no literal may carry one of the three names as a *path segment*
(`data/`, `models\\`), which catches a relative path built without `ctx.root`.
Docstrings stay excluded, for the reason version one exists.

**Consequence, and it is the reason this is a third entry rather than a footnote.** Three
of the four versions were green at the moment they were written. What moved was the code
under them, and each time the test failed for a reason that was about the test. A check
that has to be loosened every time the code grows is a check that was written against the
code's current shape rather than against the property — and the tempting repair each time
was a carve-out, which is how a rule becomes a list of exceptions nobody can read.

### The scripted market: what it refuses to do is the design

**Agent:** C (verification and interface) · **Task:** spec 100 step 1 · **Date:** 2026-09-16

**What happened.** `tests/harness/market_script.py` is the stream half of the fake
exchange: a rolling trade window and a top-of-book quote per pair, everything filtered by
an injected clock. `FakeKrakenClient` answers the four REST calls and nothing else, which
is enough for a gate and not for a round trip — engine 3 reads a stream, and the paper
broker's fills and the console's mark both move when that moves.

**Three things it deliberately does not do, and each was a real temptation.**

It does not **simulate**. A criterion says what traded and when; nothing in the harness
decides what the market does. A simulator would be a second opinion about price sitting
between the criterion and the engines, and when a round trip came out wrong there would
be two places to look instead of one.

It does not **fill orders**. B's paper broker owns fills, the ledger and the order state
by the operator's ruling of 2026-09-16, and the whole point of that ruling was that one
fill rule should exist once. A harness that decided fills would be its third copy.

It does not **hold its own clock**. It reads the same injected `Clock` the orchestrator
holds, so a criterion advances time in one place. A test that had to move the clock and
then tell the market about it is a test that will forget on the tick it matters.

**`drain()` returns nothing, and the docstring says why.** Engine 2 writes what `drain()`
returns into the archive. Fabricating raw frames would put invented JSONL in front of the
one engine whose entire job is to record what actually arrived, and no Phase 6 criterion
judges the archive — `recording_span_continuous` does that in Phase 2, against a committed
report. An empty return with a reason is honest; a plausible one would not be.

**The trade count per bar has to vary, and that is correctness rather than realism.**
`trades_z_*` is a z-score of the trade count over a lookback. A constant count is a
zero-variance window: it divides by zero, yields NaN, publishes as null, and engine 13
then correctly refuses the whole market-quality vector as incomplete — so a fixture with
a fixed count *cannot exhibit the property the criterion is about*. B hit this twice
building the Phase 5 rehearsal, the second time because the obvious fix, `min(trades, 24)`,
saturates: real bars carry hundreds of trades, every bar sat at the ceiling, and the count
was constant again one level down. Both failures have a test here, the second one against
bars carrying a thousand trades.

**The protocol is walked, not listed.** `test_every_method_the_real_stream_declares_is_here`
reads `MarketStreamProtocol.__protocol_attrs__` and checks each name, with an assertion
that the Protocol declares something so it cannot pass vacuously. That shape is A's, and
the reason is this phase's own finding: `PaperBroker` forwarded six of seven methods and
dropped `drain_gaps`, which would have had engine 2 record no `gap` line and a recording
claim to be continuous across reconnects. It was found by measurement rather than by a
test, because the test that would have caught it would have had to be written by the
person who forgot. Nobody writes a test for the method they forgot; a walk does not need
them to.

**Checked against its consumer, not against itself.** Two of the tests drive the real
engine 3 rather than reading the harness's fields back — one asserting the open bar is
never published (invariant 10; a partial high and close in front of the feature engine is
look-ahead by another name), and one planting a trade **between** two loop ticks and
asserting engine 3's per-tick range still carries it. The second is what
`context.previous_now` exists for, and a harness that could only plant trades on tick
boundaries could never show it.

### Spec 101 reads the position's hold reason out of a column that does not exist

**Agent:** C (verification and interface) · **Task:** spec 101 · **Date:** 2026-09-16

**What happened.** Spec 101 step 3: *"`hold_reason` rendered on the position when the
manage chain held, through `REASON_PROSE`."* Nothing in the database carries it, so the
console cannot render it and no amount of work in `console/` will change that.

**Why.** The chain is complete right up to the last step and then stops. Engine 21
publishes `state["position_manager"]["hold_reason"]`; engine 19 reads it
(`_hold_reason`), carries it into `MemoryState` and re-publishes it in
`state["memory"]["hold_reason"]` — and `state` is a fresh dict every tick with only
`state["system"]` surviving. **The console is a separate process reading SQLite.** It
never sees `state` at all.

`grep -rn hold_reason db/ src/acsoe/clients/store/` finds nothing: the `positions` table
has `position_id`, prices, barriers, `last_price`, `unrealised_pnl`, `opened_at`,
`timeout_at` and `updated_at`, and no hold. `ownership.md`'s seam row says
*"Manage-chain hold (`hold_reason`) | B writes | C (19 `memory`, console) reads"*, and
the reading half is true for engine 19 and impossible for the console.

This is the same shape as the persisted-mode seam of Phase 2, which is worth saying
because it is the reason the obvious workaround is refused. The console could *infer* a
hold from a `data_guard` row in `block_records` on the latest cycle. `engine-contracts.md`
already ruled that exact move out for the system mode — it is written by the command
reader that owns the value and **"never inferred from the `commands` trail"** — and the
reasoning transfers unchanged: an inference agrees with the truth until the day the rule
changes in one place, and a screen that guesses is worse than a screen that says nothing.

**Fix — not mine to make.** A schema change, so it is the lead's to approve and B's to
migrate (ownership rule 4). Escalated with a proposal rather than a question:
`hold_reason TEXT` on `positions`, written by engine 19 on the tick it updates the row
and `NULL` on any tick the chain did not hold. The column matches what `hold_reason`
already is — a fact about *now*, null whenever the manage chain did not hold — and the
console already reads `positions`, so no new read path appears. The alternative, a
`manage_ticks` table, is heavier and nothing else wants it.

**What I did instead**, so the spec is not blocked entirely: the age column, below.

### The open-positions table has never shown how old a position is

**Agent:** C (verification and interface) · **Task:** spec 101 · **Date:** 2026-09-16

**What happened.** Spec 101 wants the position rendered with *"its mark and unrealised
PnL changing tick by tick, **its age shown**, stale figures faded"*. Two of the three are
there from Phase 1: `last_price` and `unrealised_pnl` are on `PositionView` and
`staleness` fades past `console.stale_after_ms`. The age is not: `opened_at` and
`timeout_at` reach the view model and the payload, and the table renders eight columns —
pair, quantity, entry, last, target, stop, unrealised, change — none of which is age.

**Why it was not noticed in Phase 1.** Phase 1 rendered **seeded** rows, and spec 19's
acceptance was that the region renders and is absent when nothing is open. How long a
seeded position had been open is not a question anybody had a reason to ask of a fixture.
It becomes a real question the moment a position is a live one with a twelve-hour timeout
against it: "opened 4h 12m ago" and "times out in 7h 48m" are the two facts an operator
uses to decide whether to leave it alone.

**Fix.** `age_us` and `age_text` on `PositionView`, computed **in the reader from the
injected clock** — which is the rule `views.py` already states for `Staleness`: *"a view
model that worked out its own age"* would be reading a clock, and view models do not
read clocks. `format_age` already exists and is already the coarse form the band uses, so
the console says "4h 12m" in one voice rather than two.

### The declared protocol is not the whole surface, and a walk over it cannot say so

**Agent:** C (verification and interface) · **Task:** spec 100 · **Date:** 2026-09-16

**What happened.** Driving the real chain against `ScriptedMarket` for the first time,
the guard chain blocked at engine 2:

```
blocked by market_data_recorder
unhandled AttributeError: 'ScriptedMarket' object has no attribute 'set_subscription'
```

`test_every_method_the_real_stream_declares_is_here` was green at the time, and it was
not wrong: `ScriptedMarket` **does** answer all seven names in
`MarketStreamProtocol.__protocol_attrs__`.

**Why.** The protocol is not the whole surface. Engine 2 reaches the stream's
*lifecycle* — `set_subscription` and the `subscription` property — and `PaperBroker`
forwards ten names to the client it wraps, of which four (`start`, `stop`,
`set_subscription`, `subscription`) are declared nowhere in `MarketStreamProtocol`.

The two layers then fail in opposite ways and only one of them fails loudly. Engine 2
takes `getattr(stream, "set_subscription", None)` and skips when it is absent, which is
what lets it run against C's plain `FakeKrakenClient`. `PaperBroker.set_subscription`
calls `self._real.set_subscription(pairs)` **unconditionally** — correctly: it is a
forwarder, and a forwarder that silently swallowed a missing method would be the
`drain_gaps` defect again. So in paper mode, where the broker is the stream every engine
sees, a client missing a lifecycle method raises rather than degrades, and it raises
inside the guard chain, which contract rule 7 turns into `ERROR` and `ERROR` blocks.

**This is the more interesting half of the finding.** A walk over `__protocol_attrs__` is
necessary and it is not sufficient, because a Protocol records what somebody wrote down
and an engine uses what it uses. Two things a double must satisfy are invisible to it:
the names reached by `getattr`, and the names a wrapper forwards.

**Fix.** Two parts.

`ScriptedMarket` gains the four lifecycle methods, with `subscription` holding what it
was last given — a stream that accepted a subscription and then reported a different one
would make engine 2's read-back meaningless, and the read-back is how engine 2 learns
what it is actually recording.

And a second test that derives its expectation rather than listing it: the AST of
`clients/paper/broker.py` is walked for every `self._real.<name>`, and `ScriptedMarket`
must answer each. **In paper mode the broker is the stream every engine sees**, so the
surface that matters is the one the broker forwards, not the one the Protocol declares.
It is derived from B's file, so a name B adds tomorrow is covered without anybody
remembering — which is the same property the reason-code walk has, arrived at from the
other direction.

### The whole Phase 6 trade chain is gated on engine 9, and engine 9 has no session

**Agent:** C (verification and interface) · **Task:** spec 100 · **Date:** 2026-09-16

**What happened.** Driving the real chain against the planted market at tier 3, with
engines 16, 18, 21 and 19 in place and the paper broker wrapping the scripted stream,
the tick gets six engines further than it ever has and stops:

```
tick 1  no block
tick 2  no block
tick 3  blocked by cost
        Cost gate could not price this candidate: missing order_book is NoneType,
        expected a mapping
```

Everything before it worked. Engine 3 published 200 candles and a closed bar; engine 5
produced the feature row; engine 7 scanned five pairs and **entered one**; engine 12
classified the market `choppy`; engine 13 loaded the anomaly artefact and did not block;
engine 8 scored. Then engine 10 `cost` read `state["order_book"]` and found nothing.

**Why.** Engine 9 `order_book` does not exist. Engine 10's `_require` treats an absent
key and a `None` identically and raises `MissingInputError`, which is correct and is the
fail-closed posture stated in its own docstring: *"engine 1 publishing `spread_pct: null`
because the order book fetch failed must not be read as a spread of zero, which would be
the most optimistic possible reading of a failure."* Slippage is one of the four terms of
friction, and a friction computed without it is a hurdle that is too low.

None of this is a surprise to the documents. `bootstrap.py` says the hole is load-bearing
this phase and that *"the tick stops at `cost` and `skeptic` never runs"*;
`ownership.md`'s seam table has "Slippage estimate | C (96) | B (10 `cost`, already reads
it)". The Phase 6 wave ordering puts spec 96 in wave 2 and specs 91, 92 and 93 in wave 3.
Everything is written down.

**What is new is who owns it.** Spec 96 is `C-models`'s, and `C-models` died at the usage
limit at 23:49Z and has not returned. So the critical path for **seven** of my nine
criteria and for B's specs 91, 92 and 93 rehearsals runs through a file belonging to a
session that is not running. Measured rather than inferred: this is the first time
anything has driven the chain far enough to find out, because until today engines 16 and
18 did not exist either.

**Not fixed here.** `engines/order_book/` is `C-models`'s lane and this session was told
not to touch `engines/`. Escalated to the lead with the measurement, which is the part
that makes it a scheduling decision rather than a guess.

**What this does not block.** The seven criteria still report PENDING and still name what
they wait for, which is the state they are supposed to be in. Everything up to engine 10
is now known to work end to end against the planted subject — six engines, a real
candidate, a real feature row and a real model score — and that is a stronger position
than the criteria could report before today.

---

# C-models, session 3 — spec 96, engine 9 `order_book`

Appended under my own heading. Nothing above this line is mine and nothing above it is edited.

### The archive records book **deltas**, so a mid-stream cut has no book in it at all

**Agent:** C (engines and models) · **Task:** spec 96, the fixture · **Date:** 2026-09-16

**What happened.** Spec 96 step 5 says "choose one deep pair and one thin pair from the tier-1
recording and a window of a few minutes with no gap". Taken literally that produces a fixture
from which no book can be reconstructed. Every `book` frame in `data/raw/` after the first is a
Kraken v2 **update**:

```
{"kind":"tick","pair":"ETH/USD","channel":"book", ...
 "payload":{"channel":"book","type":"update","data":[{"symbol":"ETH/USD",
   "bids":[{"price":2396.31,"qty":0.0},{"price":2396.17,"qty":20.8666329}],
   "asks":[], "checksum":839555268, ...}]}}
```

A `qty` of `0.0` deletes a level; everything else replaces one. There is no absolute book in any
of those lines. The only absolute book is a `type:"snapshot"` frame, and Kraken sends one **only
at subscribe** — which in a continuous recording means only after a reconnect.

**Why this is a trap and not merely an inconvenience.** A cutter window chosen anywhere in the
middle of the stream produces a file full of well-formed, real, byte-exact book frames that
cannot answer "what was the bid side" at any instant. It would have read as a good fixture. The
reconstruction would then have started from an empty book and filled in only the levels that
happened to change during the window — a *plausible* shallow book, four or five levels deep,
which a slippage walk would price as far thinner than the market was. That is the failure shape
`code-standards.md` names twice: a wrong answer that is in range survives, and the levels nobody
saw are the worst ones, so the error runs in the direction that makes the cost gate refuse for a
fabricated reason.

**Fix.** Cut from a **resubscribe**, not from a quiet moment. `data/raw/kraken_v2__msi__
2026-09-16.jsonl` carries four `gap` markers; the first is at `00:17:06.052717Z` with
`reconnected_at` equal to it, and the ten tier-1 snapshots land 250 to 290 ms later. A window
opening at `00:17:06.100000Z` therefore

- does **not** intersect the gap's interval `[disconnected_at, reconnected_at]`, which is what
  A's cutter refuses on, and
- **does** contain one `snapshot` frame per pair, ahead of every delta.

The dry run confirmed both, per pair: `ADA/USD: {'snapshot': 1, 'update': 451}`,
`BTC/USD: {'snapshot': 1, 'update': 524}`. The fixture reader can now start from a real ten-level
book and apply deltas in recorded order, with nothing assumed.

### `order_book.depth` does not exist in `config/default.yaml`, and its value is decided by the archive

**Agent:** C (engines and models) · **Task:** spec 96 step 2 · **Date:** 2026-09-16

**What happened.** Spec 96 step 2 reads `depth` from config key `order_book.depth`, marked
"requested of the lead, spec 80". There is **no `order_book:` section** in `config/default.yaml`
and no matching pydantic section in `src/acsoe/platform/config.py`. `Config` is `extra="forbid"`,
so the key needs both halves or the loader refuses to start, and both files are other agents'.

**Why it matters more than a missing key usually does.** `depth` is not tuning. It is the bound
on the walk, so it is the definition of `book_too_thin`: a notional the bid side cannot absorb
*within that many levels* is declined rather than extrapolated. Set it above what the archive
recorded and the live engine is configured to walk further than any committed evidence can
validate — the fixture could no longer exercise the refusal it exists to prove, and the README's
seconds-to-minutes bound would be quietly weaker than it claims.

`scripts/record.py`'s `DEFAULT_DEPTH` is `10`, and every snapshot in the archive confirms it:
ten bids and ten asks, for all ten tier-1 pairs, at every resubscribe measured. So **10** is the
value asked for, and it is asked for on the evidence rather than as a round number.

**Fix.** Requested of the lead by message, with the reasoning above, before any code. Until it
lands, `_depth` treats the absent key exactly as it treats a null one: `OK`,
`order_book_inputs_unavailable`, no estimate, and engine 10 refuses — which is the same posture
as every other fail-closed shape and does not special-case the phase's own incompleteness.
Three cases are told apart rather than conflated, per `code-standards.md` on handlers that cannot
distinguish two situations: `Config.get` **raises** `ConfigKeyError` (a `KeyError` subclass) for a
key the model does not declare, **returns `None`** for a declared key the operator left unset, and
returns the value for a key set to something that is not a count.

### Spec 96 — five mutations, five killed, and which test killed each

**Agent:** C (engines and models), session 4 · **Task:** spec 96 · **Date:** 2026-09-16

Session 3 built engine 9, its tests and the fixture and died before sweeping them. This is
the sweep, plus the fixtures README row it also owed. Nothing in the engine changed.

**Harness.** `scratchpad/mutate_ob.py`. Baseline first, and it refuses to report if the tree
is already red — sweeping a red tree marks every mutation KILLED. The target file is copied
to the scratchpad **before** the mutation and restored from those bytes with the sha256
compared **in the same statement that writes it back**; never `git checkout --`, because
`engines/order_book/` is untracked and there is nothing behind it. Every anchor is asserted
to occur exactly once. Every file that is not the variable is hashed on both sides of the arm
and reported: all five runs printed `witness files unchanged: True`.

**Arm, and the directory it excludes.** `tests/engines/test_order_book.py` — 51 tests, the
file that owns this engine. Running the sweep narrowly against the tests that own the code is
the protection `code-standards.md` asks for in a shared checkout, because a mutation live on
disk turns another agent's run red and a spurious failure reads as KILLED. **Excluded:**
`tests/engines/test_cost.py` and the chain rehearsals, which are B's and A's and would have
made attribution impossible; every verdict below is a kill, and a kill on a subset is a kill.
No survivor is being claimed on a subset, which is the direction the rule guards.

| | Mutation | Verdict | Newly red |
|---|---|---|---|
| O1 | the **ask** side walked instead of the bid side — spec 96's first named one | KILLED | 8 |
| O2 | the walk **stopping one level early** — spec 96's second | KILLED | 11 |
| O3 | slippage measured from the fill price rather than the **best bid** — spec 96's third | KILLED | 8 |
| O4 | a partial walk reported as complete instead of refusing past the fetched depth | KILLED | 7 |
| O5 | `levels_consumed` published one short of the levels the walk touched | KILLED | 8 |

**O1** was killed by, among others, `test_the_deep_pairs_walk_matches_the_hand_computation`
and `test_the_cost_gate_prices_the_slippage_engine_nine_published`. Worth naming because the
two failures say different things: the first is the arithmetic, the second is that engine 10
priced a different number. A file asserting only the arithmetic would have caught the defect
and not the consequence.

**O2** is the broadest kill at eleven tests, and the one that most needed the real fixture.
Stopping one level early is not a small error in one direction: a notional the book *can*
absorb is declined as `book_too_thin`, and one it can only just absorb is filled at a better
price than the book offers. `test_the_whole_book_exactly_is_a_fill_and_one_cent_more_is_not`
is the boundary that separates those two, and it is the test a hand-written ladder alone
would not have motivated.

**O3 is the interesting one and it is why spec 96 named it.** Measuring `(best_bid −
fill_price) / fill_price` rather than `/ best_bid` moves the answer by a fraction of a
percent, which is exactly the size of the thing being measured — a wrong answer in range. The
consequence downstream is a double charge: engine 10 already adds the measured spread as its
own term of `friction`, so slippage measured from anything between the bid and the ask
charges part of that spread twice, and the hurdle refuses trades for a cost the book does not
impose. Killed by both hand computations and by
`test_the_published_payload_can_be_recomputed_without_trusting_it`, which is the one that
recomputes the ratio from `best_bid` and `fill_price` rather than reading the published
`estimated_slippage_pct` — ruling 7's shape, and the reason that test exists.

**O5 is the checked negative that turned out not to be one.** `levels_consumed` changes no
decision: it is provenance beside the estimate, and the slippage is identical with it wrong.
I expected it to survive, which would have said that a published field nobody asserts on can
say anything. It was killed by eight tests, because the fixture's walks are asserted in full —
`test_the_engine_publishes_the_walk_it_made` is parametrised over both pairs and pins the
level count against a hand computation (ADA/USD consuming 10 levels for
0.0001366891113175430924786514892, BTC/USD consuming 4 for
0.00006528042192692375531712952815). That is the difference between publishing a number and
asserting it.

**No survivors, so nothing was re-run wide.** Had one survived, the rule is that a mutation
surviving a subset has not survived, and it would have gone to
`tests/engines/test_cost.py` and the chain rehearsal before being believed.

**Also landed, and it was outstanding rather than new:** the `book_sample.jsonl` row in
`tests/fixtures/README.md`, with the provenance session 3 worked out and did not get to
write down — the two pairs, the 30-second window, and above all *why the window opens 48 ms
after a reconnect*. Kraken v2 sends book **deltas**, and the only absolute book is the
`snapshot` frame at subscribe, so a cut from a quiet moment mid-stream would have produced a
file of real, byte-exact frames that cannot say what the bid side was at any instant. The
reconstruction would have started from an empty book and produced a plausible four- or
five-level ladder — thinner than the market was, in the direction that makes the cost gate
refuse for a fabricated reason. That reasoning belongs beside the file, not only in a build
log, because the next person to re-cut it will read the README.

### Decision: engine 14 weights by Brier skill against the fold's own base rate — and the base rate is not in the table

**Agent:** C (engines and models) · **Task:** spec 97 step 3 · **Date:** 2026-09-16

**Proposed here before any of engine 14 is written**, per spec 97 step 3, which makes this a
methodology choice the lead approves rather than something a lane decides.

**Options.** Three were on the table.

1. **Brier skill against the base rate, clipped at zero, normalised.** For each model version,
   `skill = 1 - brier / base_rate_brier`, clipped below at zero; `weight = skill / sum(skill)`,
   or all zero when nothing beats its base rate.
2. **Inverse Brier**, `weight ∝ 1 / brier`. Needs no base rate at all.
3. **Rank-based**, weight by position in a Brier ordering.

**Chose option 1**, which is the example spec 97 itself offers.

**Because** the other two both hand weight to a model that has no edge. Inverse Brier is the
sharper illustration: Brier is bounded and always positive, so `1 / brier` gives a model that
is *worse than always predicting the base rate* a perfectly respectable weight — and on the
numbers this project actually has, that is not a hypothetical. Spec 67's first real run came
in at or slightly worse than base rate on two folds of three. A rule that cannot express "this
model has no edge" would weight those folds as confidently as a good one, and spec 97's own
requirement that a model failing to beat its base rate gets weight zero would be unstatable.
Rank-based has the same defect wearing a different hat: the worst of three models still ranks
third, and third of three is a weight.

Option 1 also has the property that makes it honest about today: with one model version in the
table the weight is 1.0 whatever its skill, and with none it is the empty case. The rule does
not pretend to be doing work it is not.

**The blocker, and it is spec 97's own warning coming true.** `leaderboard` has a `brier`
column and **no base-rate Brier column** (`db/migrations/0001_initial.sql`). Engine 20 already
computes `base_rate_brier` per fold — `engines/tournament/engine.py` holds it on `_FoldScore`,
recomputes it from the out-of-sample rows, and checks the digest against it — and then
**discards it** on the way into the store, because there is no column to write it to.

**It cannot be recovered from the columns that exist, and the near-miss is worth recording
because I nearly took it.** `win_rate` is stored, and for a binary outcome the base-rate Brier
is `p(1-p)`, so `win_rate * (1 - win_rate)` looks like the number. It is not. `brier` and
`base_rate_brier` are computed over **every** fold row; `win_rate` is computed over the **BUY
subset** only. Two different populations, and on a fold where the BUY calls are the confident
ones they differ substantially. A skill score built from those two would be a ratio of
quantities measured on different sets — in range, plausible, and wrong in whichever direction
the BUY subset happens to lean. That is exactly the witness rule the lead added to
`code-standards.md` today, met from the other side: two numbers that look like the same
quantity, in one table, with nothing saying they are not.

**So this is a schema question, which spec 97 says in as many words is the lead's and not a
number encoded into `notes` and parsed back out.** What I am asking for: **`base_rate_brier
REAL` on `leaderboard`**, nullable, written by engine 20 from the value it already has. That
is a migration (B's `db/migrations/`), a `LeaderboardRow` field (B's `clients/store/`) and one
line in engine 20's `_write` (mine). Until it lands, engine 14 has no way to evaluate the
approved rule, and the fail-closed reading is the one I would build meanwhile: a row whose
`base_rate_brier` is absent gets **weight zero with a reason code**, not a default base rate
— inventing one would be this lane choosing the line at which a model counts as having edge.

**The regime and the DI margin are published as provenance and are not in the arithmetic**,
and that is deliberate rather than an omission. Spec 97 has engine 14 read
`state["regime"]["label"]`, and the mutation list says "the regime ignored **if** the approved
rule uses it". Conditioning a weight on regime requires per-regime metrics, and the leaderboard
holds one Brier per model version over the whole out-of-sample window with no regime breakdown
anywhere. A regime adjustment invented on top of that would be a methodology choice with no
measurement behind it, which is the thing spec 70 and spec 72 both stopped at rather than
walked past. The regime goes into `basis` so the operator can see which market the weights were
published in; it changes none of them. The same for `di_margin`.

**Cost.** One schema change and the seam it opens with B. And the honest statement that engine
14 is inert today — the walk-forward trains one predictor per fold, so there is one version to
weight — which the README says and which the fixture is built to work around rather than hide:
`leaderboard_sample.json` carries three fabricated versions precisely because the real table
cannot exercise the rule, and its provenance line says so.

### An unmarked position was worth nothing, and one such tick freezes the account

**Agent:** C (engines and models) · **Task:** spec 98 · **Date:** 2026-09-16

**What happened.** `_write_equity` read `positions_value` through
`decimal_field(manager or {}, ...)`, and `decimal_field` returns `Decimal(0)` for an
absent field. Only an absent `balances` skipped the row. So on a tick where engine 21
could not take a mark, `equity = cash + 0` and the position's entire value vanished from
that tick of the series. Found by the lead while confirming for B that engine 19 treats an
absent `positions_value` as nothing-to-record. It does not, and the lead checked the code
rather than the docstring — the docstring said the right thing.

**Why it matters more than a wrong number.** Engine 17 computes
`(peak_equity - equity) / peak_equity` against a peak read from the store, so on a fully
invested account one unmarked tick is a drawdown approaching 100% against a
`safety.max_drawdown_pct` of 0.10. The account freezes over a missing quote. Spec 92 has
engine 21 publish `positions_value` **absent, never zero**, precisely so this is
detectable — and `decimal_field`'s default threw that distinction away at the reader.

The lead's framing is the part worth keeping: this is the third instance this phase of
**a default that is correct in the only state the system has ever been in**.
`Orchestrator._flag`'s `bool()` was right for an absent payload, `decimal_field`'s zero is
right for a flat account, and engine 11's concurrency check was right while nothing could
open a position. All three become wrong on the first tick that holds a position, and none
of them looks wrong until then.

**Fix.** `store.count_open_positions()` is read **before** the equity arithmetic rather
than at the write, because this tick's positions have already landed and it is that count
which decides whether cash-only equity is the truth or a hole. Non-zero count with
`positions_value` or `unrealised_pnl` absent writes **no** equity row and names itself in
`equity_skipped_reason`; zero count with an absent mark writes the row on cash alone,
because there is nothing to mark. `unrealised_pnl` gets the same treatment: an absent one
reading as zero is a claim that the position sits exactly at its entry price, which Phase
7's attribution would read as fact.

**One existing test of mine was green because of the defect**, and it is worth naming
rather than quietly fixing. `test_the_position_count_comes_from_the_store_not_from_this_
tick_s_state` drove two ticks with an open position and no mark, and asserted
`open_position_count == 1` on **two equity rows that valued that position at nothing**.
The fix removes those rows, so the test had to change to supply a mark. Its subject is
sharper for it: tick 2 now publishes a mark and no positions list, so the store says one
open position while `state` says none — which is what the test was always about.

### The three new sources, and the write order that decides which row survives

**Agent:** C (engines and models) · **Task:** spec 98 · **Date:** 2026-09-16

`state["execution"]["orders"]`, `state["exit"]["orders"]` and `state["exit"]["positions"]`
are read now; engine 19 is the single writer of relational rows, so before this those rows
reached no table at all. Field shapes confirmed by B's audit rather than negotiated: the
row payloads are the store contract's minus `run_id`, `cycle_id` and `updated_at`, which
`_stamped` sets itself because a row carrying the publisher's `run_id` cannot be joined to
the block record for the tick.

**The write order is chain order and it is load-bearing twice**, per the lead's ruling.
`write_position` upserts on `position_id` and `write_order` on `userref`, so the row
engine 19 writes *last* is the stored state. Positions: 21 then 22, because engine 22 runs
after 21 and a position closed this tick must not be stored as open with a mark on it — a
row the console renders as live and `safety` counts towards its escalation precondition.
Orders: 18 then 21 then 22, because an entry placed on the opportunity chain and cancelled
on the manage chain must end cancelled; the other way it is stored as resting, which is a
live post-only buy to everything that reads the table, and invariant 8 exists for exactly
that order. Both are tested with an assertion on the **row count** as well as the status,
because an upsert that had silently become an insert would leave both rows present and the
status assertion would pass on whichever came back first.

### Spec 98 — eight mutations, eight killed, and the one that survived first

**Agent:** C (engines and models) · **Task:** spec 98 · **Date:** 2026-09-16

Harness `scratchpad/mutate_mem.py`, same guarantees as the other two sweeps: baseline
first with a refusal if it is red, byte copy before the mutation, sha256 compared in the
same statement that restores it, every anchor asserted to occur exactly once, witnesses
hashed on both sides. Arm `tests/engines/test_memory.py` and
`tests/engines/test_memory_rows.py`. **Excluded and named:** `tests/verify/`, which is the
other C session's and would make attribution impossible.

| | Mutation | Verdict | Killed by |
|---|---|---|---|
| P1 | engine 18's orders not read — spec 98's first named one | KILLED | `test_the_entry_order_engine_18_places_reaches_the_store` |
| P2 | engine 22's positions not read — spec 98's second | KILLED | the closed-position test and the 22-sources test |
| P3 | engine 22's orders not read | KILLED | the 22-sources test |
| P4 | 18's orders written after 21's — spec 98's third | KILLED | `test_a_placement_and_its_same_tick_cancel_end_as_cancelled` |
| P5 | 22's positions written before 21's | KILLED | `test_a_position_marked_and_closed_on_one_tick_ends_closed` |
| P6 | the equity row skipped whenever a mark is absent, open position or not | KILLED, 6 tests | `test_a_flat_account_still_writes_its_equity_row` and five older equity tests |
| P7 | the equity row never skipped — the defect as it stood | KILLED, 3 tests | the three invested-account tests |
| P8 | the hold reason carried forward instead of cleared | **survived, then killed** | `test_the_hold_reason_is_written_and_then_cleared` |

P6 and P7 are the lead's two required mutations and they fail in opposite directions,
which is the point: a version that always skips loses the flat account's row — a silent,
permanent hole in the one series the drawdown breaker reads — and a version that never
skips is the defect. The two tests they redden differ in **exactly one input**, whether a
position was published.

**P8 survived the first sweep and the test was at fault, not the engine.** The mutation
sets `hold_reason` only when there is one, so the previous tick's reason is carried
forward — an hour-old hold rendered forever, reporting a paused manage chain over one
running normally. My test drove a tick that held and then a tick that did not, and it
passed under the mutation: `a_position` dumps a real `PositionRow`, which carries
`hold_reason: None` as a **model default**, so the row payload itself already said null
and the column came out null whether or not engine 19 assigned anything. Two sources
supplying the same value — the lead's witness rule, met from the other side, on a test
written the same day the rule was added.

The fix is the one the rule prescribes: make the sources differ. Tick 2's row now carries
a **stale** `hold_reason`, which is not a contrivance — engine 21 builds its published
rows from the open positions it read out of the store, so last tick's value is exactly
what comes back — and only engine 19's tick-level assignment can clear it. Tick 1 already
distinguished the two, with the row saying null and the tick saying `data_guard`, and it
now asserts that precondition explicitly. P8 is red on re-run.

**One baseline refusal, and the harness was right to make it.** P8's first attempt aborted
with `REFUSED: baseline is red` on a `TypeError: object of type 'ScalarEvent' has no len()`
out of PyYAML, loading `config/default.yaml` — another agent mid-save. Nothing was
mutated, nothing was reported. That is the protection working: without the baseline the
mutation would have been applied to a tree that was already failing and reported KILLED on
somebody else's half-written config.

### `Path.write_text` again, this time inside the editing tool, and it broke a mutation sweep

**Agent:** C (engines and models) · **Task:** spec 98 · **Date:** 2026-09-16

**What happened.** Four mutation arms in a row aborted with
`anchor appears 0 times, expected exactly once`, against anchors I had copied character for
character out of the file. `src/acsoe/engines/memory/engine.py` was **566 CRLF and 0 bare
LF** in the working tree; its committed blob is 521 bare LF and no CRLF.
`tests/engines/test_memory_rows.py` was **mixed**: 614 CRLF and 390 LF.

**Why.** The text-mode round trip `code-standards.md` names, arriving through the editing
tool rather than through anyone's `Path.write_text`. It rewrites the **whole file's** line
endings, not the lines it was asked to change — and `.gitattributes` carries
`* text=auto eol=lf`, so git's clean filter normalises on the way into the index and
`git diff --numstat` reported only my real changes (53/8 and 416/3). `git status` said
nothing. The only visible symptom was four sweeps refusing to find an anchor.

**This is the same mechanism that cost the lead the spec 102 revert**, and connecting them
is the reason this entry exists rather than a one-line fix. Two Phase 5 criterion tests
patch `modelling/di.py` **by literal anchor** to prove the DI criterion can fail; the
refactor rewrote those lines and both proofs reported "anchor appears 0 times". A
whole-file line-ending rewrite does the same thing to every literal-anchor patcher in the
repository, silently, with no diff to show for it. Anywhere under `tests/fixtures/`, which
is marked `-text` so that no conversion happens near an evidence fixture, it would change
committed bytes instead.

**Fix.** Both files rewritten as bytes with `\r\n` replaced by `\n`: engine.py 25,109 →
24,543 bytes, test_memory_rows.py 39,810 → 39,196. Every file this session has touched was
then scanned; the only other CRLF file in the set is `tests/engines/test_memory.py`, which
is **not mine** — its blob is pure LF, `git status` reports it clean, and I have never
written it, so it is one of the ~120 pre-existing conversions `code-standards.md` already
records. Left alone rather than tidied, because a file I did not change is not mine to
rewrite in a shared checkout.

**Consequence.** The scan is worth making a habit rather than a reaction: `CRLF count` on
every file a session touched, before the mutation sweep rather than after four refusals.

### Engine 9 audited rather than only swept, and what was found sound

**Agent:** C (engines and models), session 4 · **Task:** spec 96 · **Date:** 2026-09-16

A mutation sweep proves the *tests* can fail. It says nothing about whether the engine is
right, and I inherited engine 9 from session 3 rather than writing it. This log asks for
what was checked and found sound as well as what was found broken, so: every one of spec
96's structural requirements was read against the code, and all of them hold.

- **`number = 9`, `is_gate = False`**, matching the registry's Gate column.
- **It cannot block, and that is structural rather than careful.** `EngineStatus.OK`
  appears exactly once in the module and `BLOCK`, `PASS` and `ERROR` appear zero times —
  one return point, one status. Spec 96 step 4 requires a non-gate that refuses on its own
  criteria to be impossible, and this is the strongest available form of it.
- **Nothing can escape as an `ERROR` either, which is the half a status count misses.**
  Contract rule 7 turns an uncaught exception into `ERROR` with `blocks_trading=True`, so
  a raise here would be engine 9 blocking the tick by the back door. Every `SetupError` —
  a missing config key, a null depth, a non-integer depth, a missing scout pair, an
  unreadable quote currency, an unparseable balance — is raised inside the one `try` that
  turns it into an `OK` with `order_book_inputs_unavailable`. The client call is wrapped
  separately and catches `KrakenError`, `ValidationError` and `ValueError` only, with the
  reasoning written beside it: anything that is not exchange-shaped propagates on purpose,
  because a defect on this side of the boundary is not a thin book.
- **No `float(` anywhere in the engine or its contracts**, and every money field is typed
  `Money`. The walk is `Decimal` throughout, and the two inexact operations — a remainder
  divided by a price, and quote divided by base — are named in the docstring with the
  reason nothing is quantized.
- **The README carries spec 96 step 6's bound in the required terms**: validated over
  seconds to minutes of recorded book rather than years of archive, because the historical
  archive carries no book at all, and every slippage number this system reports inherits
  that limit.

The one thing I would still like closed is not a defect in the engine: **engine 9 publishes
no `pair`**, so B2's engine 16 coherence walk — which checks any payload carrying a `pair`
against `state["scout"]["pair"]` — is silently exempt from the one engine whose whole job
is to price a specific pair's book. A cached or misread pair there produces a slippage
number that is in range, plausible, and about the wrong market. Raised with the lead as a
field-list question, since spec 96 fixes the payload and B2 is building against the spec.

### The Phase 4 equity replay drove an invested account as though it were all cash

**Agent:** C (verification and interface), session 3 · **Task:** the lead's job 1 ·
**Date:** 2026-09-16

**What happened.** Three tests in `tests/verify/test_phase4_criteria.py` fail, all with the
same message:

```
criterion raised - ValueError: live.drawdown_pct is not a decimal: None
```

`test_every_phase_4_criterion_passes_against_the_real_repository`,
`test_a_memory_engine_that_drops_the_closed_trades_is_a_fail` and
`test_a_memory_engine_that_drops_the_resting_orders_is_a_fail`. The criterion is
`memory_writes_safety_inputs_live` — the one that closes the project's single forward
dependency by reading the same six `safety` numbers out of B's Phase 0 seed and out of C's
engine 19.

**Why.** Nothing is wrong with engine 19. C-models changed it, correctly and by the lead's
ruling, so that an absent `positions_value` no longer means a position worth nothing:
`decimal_field` returns `Decimal(0)` for a missing field, and on a fully invested account
`equity = cash + 0` is a drawdown approaching 100% against the stored peak — an account
frozen by a missing quote. Engine 19 now reads `store.count_open_positions()` and, where
positions exist with no mark published, writes **no** equity row and names
`equity_skipped_reason`.

`_replay_seed_through_memory` in `scripts/verify.py` — mine — had already written the seed's
open positions into the live database at step 2, and then drove its two equity ticks at step 4
with `state["exchange"]["balances"]` **and nothing else**. Under the new rule both rows are
correctly skipped, `equity_snapshots` is empty, `safety` reads `drawdown_pct: None`, and the
criterion's own `as_decimal` raises on it.

So the replay was asserting a number it was producing by accident. Its two ticks said *this
account holds positions and is entirely in cash*, which is not a state the system can be in;
the old engine 19 answered the contradiction by silently discarding the positions' value, and
the criterion passed on the arithmetic that came out. The new engine 19 refuses the
contradiction instead, which is what made it visible. **The replay was wrong before this
change and produced the right answer anyway** — that is the shape worth recording, not the
red.

**A second defect, found while confirming the first, and worse than it.**
`test_a_peak_equity_recomputed_from_this_tick_is_a_fail` is **green right now and green for
the wrong reason**. It induces spec 50's named mutation (`peak = equity`), expects a FAIL, and
asserts `"drawdown_pct" in outcome.message`. The criterion never reaches its comparison — it
raises — and `verify.py` renders the raise as a FAIL whose message is
`criterion raised - ValueError: live.drawdown_pct is not a decimal: None`. That string
contains `drawdown_pct`, so both assertions hold, and **the one test standing behind the
reason the replay drives two equity ticks rather than one has not exercised the criterion
since the engine changed.** It is the substring rule in `code-standards.md` — `match=` can
only ever say *at least this* — wearing a different hat: `in outcome.message` on a bare
`FAIL` cannot tell a disagreement from a crash. It went unnoticed because it kept passing,
which is the only direction of this defect nobody looks in.

**A third thing, and a habit paying off.** `tests/verify/test_phase4_criteria.py` was **mixed**
in the working tree — 867 CRLF lines against 62 bare LF — measured before touching anything,
per the rule C-models added to `code-standards.md` today. A multi-line anchor written with
`\n` would have matched only inside the 62-line region, and the refusal would have surfaced a
long way from the cause. Note that `grep -c $'\r$'` in this shell reported the file as
*uniformly* CRLF and was wrong about every file I checked; the byte count
(`b.count(b'\r\n')` against `b.count(b'\n')`) is the one to trust.

**Fix.** In `scripts/verify.py` and `tests/verify/test_phase4_criteria.py`, both mine. The
lead approved "give the two equity ticks a `position_manager` payload with `positions_value`
and `unrealised_pnl` from the seed's latest `equity_snapshots` row and cash of
`equity - positions_value`". **I built that, measured it, and it was not enough — so what
landed is one step further, and the step is the reason this entry is long.**

1. `_seed_equity_bounds` became `_seed_equity_ticks`, returning **two whole rows** as
   `SeedEquityRow` — the row that set the peak and the latest row — each carrying `ts`,
   `equity`, `peak_equity`, `cash`, `positions_value` and `unrealised_pnl`. The peak row is
   found by walking the series as `Decimal`, never by `SELECT MAX` on a money column.
2. Each equity tick now replays **its own row**: the balance is that row's `cash`, the mark is
   that row's `positions_value` and `unrealised_pnl`. Engine 19 adds them and has to *arrive
   at* that row's equity.
3. A new comparison, `_equity_composition_disagreements`, checks engine 19's latest
   `equity_snapshots` row against the seed's on all five money columns —
   `realised_pnl_cum` deliberately excluded, being a running total over whichever trades each
   producer has seen and the one column the two sides are not expected to agree on.
4. A new refusal, `_no_equity_row_written`, reports "engine 19 wrote no equity_snapshots row"
   **before** the six readings are compared, so the original symptom can never again reach
   `as_decimal` and arrive as a raise. The composition comparison is reported **after** the six
   readings, because those are the criterion's thesis and this is the fidelity underneath them.
5. `tests/verify/test_phase4_criteria.py`: two parsers, `disagreeing_readings` and
   `disagreeing_columns`, which refuse a message containing `criterion raised` and then
   **extract and compare the whole set** of what disagreed. The three induced-failure tests
   now assert `== ["drawdown_pct"]`, `== ["consecutive_losses"]`, `== ["resting_entry_orders"]`
   rather than `in outcome.message`. One new test,
   `test_a_memory_engine_that_stores_the_total_without_its_composition_is_a_fail`.
6. The file was rewritten as bytes to pure LF, 41,284 → 40,417 bytes, 867 CRLF → 0.
   `git diff --quiet` rc 0 either side: the blob never changed, because `.gitattributes` had
   been normalising it into the index the whole time.

**Why the approved fix was not enough, measured rather than argued.** With
`cash = equity - positions_value`, the arm *"the mark is read out of the wrong column"*
**survived**: `cash + positions_value` returns the seed's total for **any** mark whatsoever,
because the cash was derived to cancel it. The replay would have reproduced the number while
the composition behind it was free. Reading the row's own `cash` turns the addition into an
assertion, and that arm now dies. Phase 5's closing finding, in a new place: recompute what a
number was supposed to be computed from — do not rearrange it.

The composition columns also had **no reader at all** before this. `cash`, `positions_value`
and `unrealised_pnl` are stored because the Phase 7 alpha attribution reads the curve
*including its cash periods* — `0001_initial.sql` says so in a comment — and every test in the
project compared the total. A writer keeping the total and losing the split left every
`safety` reading correct and handed Phase 7 a portfolio that was never invested.

**Mutation sweep — seven arms, six killed, one equivalent control survived as designed.**
Arm: `tests/verify/test_phase4_criteria.py` alone, 47 tests, named because a narrow arm is
what the shared-checkout rule asks for. Target `scripts/verify.py`, byte copy taken before any
arm at sha256 `e59a8f00661112986be8649f159b3c972c34d977f9a840cae3f5912d1a5953ab`, every anchor
asserted to occur exactly once, every restore written and its sha256 compared **in the same
statement** — `sha((path.write_bytes(original), path.read_bytes())[1]) == before`, a tuple and
not an `or`, because `write_bytes(...) or sha(...)` short-circuits on the byte count and
compares nothing. All hashes matched at the end of the sweep. Baseline green before it started.

| Arm | Mutation | Result | Killed by |
|---|---|---|---|
| V1 | the tick's cash is its whole equity, so the position is counted twice | KILLED | `passes_against_the_real_repository`, `drops_the_closed_trades`, `drops_the_resting_orders`, `stores_the_total_without_its_composition` |
| V2 | the mark published out of the wrong column of the seed's own row | KILLED | the same four |
| V3 | no mark published at all — **the exact defect this job fixed** | KILLED | those four plus `a_peak_equity_recomputed_from_this_tick` |
| V4 | **EQUIVALENT CONTROL** — the compared columns listed in a different order | SURVIVED, as designed | — |
| V5 | one equity tick instead of two, so no peak is ever established | KILLED | the same four as V1 |
| V6 | the composition comparison dropped, leaving the six readings alone | KILLED | `stores_the_total_without_its_composition` — and **only** that one, which is the evidence the new test was worth writing |
| V7 | the unrealised mark published as zero | KILLED | `stores_the_total_without_its_composition`, `passes_against_the_real_repository` |

V2 is the arm that changed the design: under the lead-approved arrangement it is the arm that
**survived**. V6 is the arm that says the new comparison is load-bearing rather than ornamental
— one test kills it, and that test did not exist this morning.

**One refusal and one thing left unexplained, both recorded rather than tidied away.**

* The sweep's **first** run reported a red baseline — `1 failed, 46 passed` — and printed only
  the summary line, which named nothing, so nothing was mutated and the run was thrown away.
  Three captured re-runs were green. The harness now writes each arm's **whole** output to
  `scratchpad/sweep-logs/<arm>.log` before anything is concluded from an exit code, which is
  rule 5 applied to a harness rather than to a test: the first version's diagnosis could only
  ever have been "something failed".
* A **segmentation fault**, once, running `tests/verify tests/console tests/harness` together:
  a Windows access violation inside `re` at `scripts/verify.py:509`,
  `check_docs_vocabulary`'s `pattern.search(line)`, reached from
  `test_a_planted_term_in_a_current_state_section_fails`. That is the shape of catastrophic
  regex backtracking overflowing the C stack. It has not recurred in two runs of
  `test_docs_vocabulary.py` (24 passed each) or a full 780-test lane run, and the lane log
  carries zero further access violations. **Unexplained**, and written down as unexplained —
  `check_docs_vocabulary` scans `context/*.md`, three agents share this checkout, and a
  mid-save file is a plausible cause I have not demonstrated. Flagged to the lead because it
  is in a criterion that runs in every phase gate.

### Spec 99's map caught up to four engines, and one sentence was describing a repaired defect

**Agent:** C (verification and interface), session 3 · **Task:** spec 99, the lead's job 2 ·
**Date:** 2026-09-16

**What happened.** `tests/console/test_reason_prose.py`'s walking test went red naming
**fourteen** codes with no operator prose, across four engines that landed after session 2
stopped: engine 9 `order_book` (4), engine 14 `adaptive_router` (4), engine 18 `execution`
(2 of its 6), engine 22 `exit` (4). Engines 16 and 21 were already fully mapped — checked
against their own `contracts.py` rather than against any list, as the lead asked.

Separately, `console/format.py`'s sentence for `entry_unrecorded_at_exchange` said the system
"cannot describe it because `OrderState` carries no quantity or limit price", and that had
stopped being true.

**Why.** Two different causes, and only the first is the walk working as designed.

The fourteen are the seam doing its job: a code with no prose renders `"No reason was
recorded."` on the console **silently, with no error anywhere**, and the walk is the only
thing in the project that can notice. Four engines landing in one afternoon is exactly the
rate the walk was written for.

The stale sentence is the other kind. A's spec 84 amendment added `qty`, `limit_price` and
`opened_at` to `OrderState`; B then built the row; the lead narrowed
`REASON_ENTRY_UNRECORDED` to the single remaining case — **the exchange answering with no
`opentm`**, so the order cannot be dated — and introduced `REASON_ENTRY_RECOVERED` for the
ordinary crash-recovery case. Every one of those changes was correct, and **the sentence
survived all of them.** Nothing could have caught it: a stale sentence is not a failing test,
it is a screen that quietly misinforms whoever reads it at 3am. A listed it in its progress
file under a heading naming B and C rather than editing another agent's file, which is how it
reached me at all.

**Fix.** Fourteen sentences in `REASON_PROSE`, one rewrite, and **six new property tests** in
`tests/console/test_reason_prose.py` — because presence is the weakest thing that can be
asserted about a sentence, and the editorial decisions are where the value is.

The rewrite names the specific gap instead of a general inability: *"An order is resting at
the exchange and this system cannot tell when it was placed, so it was left unrecorded; find
it by its reference."* "when it was placed" rather than "`opentm`", because the operator reads
this screen and not Kraken's field list, and the `userref` pointer survives because that is
still the only thing an operator can act on.

The editorial decisions the new tests pin, each of which could otherwise be undone by a
well-meaning edit with nothing objecting:

- **Engines 9 and 22 cannot refuse, so none of their sentences may read as a refusal.** This
  is structural rather than stylistic for engine 9: `EngineStatus.OK` appears exactly once in
  the module and `BLOCK`, `PASS` and `ERROR` zero times. When it cannot price the book it
  publishes *no estimate* and engine 10 `cost` is what refuses, on the absence. A sentence
  saying "rejected" here sends the operator past the gate that actually stopped the trade,
  looking for one that does not exist.
- **Two of engine 22's codes and one of engine 18's are things the engine *did*, not
  refusals.** `exits_placed` with no sentence is the console narrating a placed stop-loss as
  silence.
- **`exit_incomplete` must say the position is still open.** `positions_closed` is false
  beside it. A sentence saying only "incomplete" leaves the one question that matters — *am I
  still holding this?* — unanswered on the screen whose whole job is to answer it.
- **Engine 14's four codes all mean "no weights" and mean four different things to an
  operator**, two ordinary states and two refusals to guess. `leaderboard_empty` is where
  every fresh clone lives and `no_model_beats_its_base_rate` is a *finding* — the tournament
  reporting, correctly and usefully, that nothing on it has edge. Neither may borrow "could
  not" from the two beside them.
- **One fact keeps one spelling and one sentence.** Engine 9 reuses engine 7's
  `no_quote_balance`; engine 22 spells its hold exactly as engine 21's
  `HOLD_DATA_GUARD_BLOCKED`. Both are now asserted between the two producing modules, so a
  parallel code cannot be minted quietly. Two vocabularies for one fact is how a `trades`
  table ends up carrying both "stop" and "stopped".
- **The prose and the contract are read in one test.** `test_the_unrecorded_entry_sentence_matches_what_order_state_can_now_carry`
  asserts `{"qty", "limit_price", "opened_at"} <= OrderState.model_fields` **and** that the
  sentence no longer claims the order is indescribable, **and** that it names the timing gap.
  That is the answer to the class of defect this entry is about: the sentence went stale
  because nothing held it against the contract it described, and now something does.

**Mutation sweep — fifteen arms, fourteen killed, one equivalent control survived as
designed.** Arm: `tests/console/test_reason_prose.py` alone, 178 tests. Targets
`src/acsoe/console/format.py` and the test file, both hashed as bytes before any arm, both
verified CRLF-free before the sweep started (the harness refuses outright on a CRLF target,
because an LF anchor would match nothing and the refusal would read as "the code moved").
Every anchor asserted to occur exactly once; every restore written and its sha256 compared in
the same statement that wrote it. All hashes matched at the end.

| Arm | Mutation | Result | Killed by |
|---|---|---|---|
| P1 | an engine 9 sentence reads as a refusal | KILLED | `no_engine_nine_sentence_reads_as_a_refusal` |
| P2 | the thin-book sentence stops naming the depth fetched | KILLED | `the_thin_book_and_the_unreadable_setup_are_not_one_sentence` |
| P3 | the unrecorded-entry sentence reverted to the one A's amendment falsified | KILLED | `the_unrecorded_entry_sentence_matches_what_order_state_can_now_carry` |
| P4 | the recovered entry borrows the already-placed sentence | KILLED | `no_two_codes_share_a_sentence`, `the_three_provenance_codes_are_three_sentences` |
| P5 | the incomplete exit stops saying the position is still open | KILLED | `the_incomplete_exit_says_the_position_is_still_open` |
| P6 | the empty leaderboard reads as a fault | KILLED | `the_two_ordinary_router_states_do_not_read_as_faults` |
| P7 | engine 14's base-rate sentence deleted | KILLED | the walk, `every_reason_code_adaptive_router_declares_has_prose`, `the_four_router_codes_are_four_sentences`, `the_two_ordinary_router_states_do_not_read_as_faults` |
| P8 | **EQUIVALENT CONTROL** — two entries swapped in declaration order | SURVIVED, as designed | — |
| P9 | the `OrderState` field set fabricated rather than read | KILLED | `the_unrecorded_entry_sentence_matches_what_order_state_can_now_carry` |
| P10 | engine 9's fetch-failure sentence deleted | KILLED | the walk, `every_reason_code_order_book_declares_has_prose`, `no_engine_nine_sentence_reads_as_a_refusal` |
| P11 | engine 22's placed-exit sentence deleted | KILLED | the walk, `every_reason_code_exit_declares_has_prose`, `the_exit_outcome_codes_do_not_read_as_refusals` |
| P12 | the engine 9 / engine 7 shared-code comparison pointed elsewhere | KILLED | `engine_nine_reuses_the_scouts_empty_balance_code` |
| P13 | the engine 22 / engine 21 shared-hold comparison pointed elsewhere | KILLED | `engine_twenty_two_spells_the_hold_exactly_as_engine_twenty_one_does` |
| P14 | engine 22's quiet tick reads as a refusal | KILLED | `the_exit_outcome_codes_do_not_read_as_refusals` |
| P15 | engine 18's recovered-entry sentence deleted | KILLED | the walk, `every_reason_code_execution_declares_has_prose`, `the_three_provenance_codes_are_three_sentences` |

**Every one of the six new tests was observed red at least once**, which is the question a
kill count cannot answer. P4 and P7 each killed more than one test, and in both cases the
*deliberate* assertion is a single one of them — A's Phase 6 finding about `opened_at`'s
mutation C6 applies here too: a high kill count is not evidence that the property is tested.

**One mutation deliberately not run, and what that costs.** Proving the prose-to-contract
coupling from the *contract* side means deleting `opened_at` from A's `OrderState`. A owns
that file, three agents share this checkout, and a live mutation in someone else's run
surfaces as a spurious failure they may report as real — the direction that hides a survivor,
which `code-standards.md` already records from Phase 4. P9 mutates the test's own expected
field set instead. **That proves the set is read from the real model rather than fabricated;
it does not prove that the model losing a field turns this test red.** Stated rather than
implied, because the gap is small and the habit of not stating it is not.

**A finding the warning list gave up, and it is not mine to fix.**
`test_the_inverse_is_reported_as_a_warning_and_never_as_a_failure` warns that `REASON_PROSE`
carries five sentences no engine publishes. Session 2 wrote that four are the seed
generator's older spellings and that `insufficient_depth` "is engine 9's, which does not
exist yet". Engine 9 exists now, so I went and looked, and **that sentence was half wrong in
a way worth writing down**: `insufficient_depth` is not an engine spelling at all. It is at
`src/acsoe/clients/store/seed.py:188`, written as

```
("order_book", "insufficient_depth", "Order book too thin to fill without 0.8% slippage")
```

— a seeded **rejection row attributed to engine 9**. Two things follow, and both are other
agents' calls:

1. **Two spellings for one condition.** The seed says `insufficient_depth`, engine 9 says
   `book_too_thin`, and they render two different sentences. That is exactly the divergence
   the two sharing assertions added above exist to prevent, arriving from the one direction
   they cannot see — a *fixture* rather than an engine.
2. **Worse, and the reason this is a finding rather than tidying: engine 9 cannot reject.**
   It has one return point and one status, `OK`, and it publishes an absent estimate rather
   than a refusal; engine 10 `cost` is what refuses. The seed writes a rejection *attributed
   to* engine 9, so the console will render a refusal from an engine that has no refusal
   path. The seed predates the engine and nothing has compared the two since.

`clients/store/seed.py` is B's and `engines/order_book/` is C-models'. Raised with the lead
with both paths named, not touched. Both sentences stay in `REASON_PROSE` meanwhile, because
the seeded rows exist and must still render — the alternative is silence on the console,
which is the defect this whole file exists to prevent.

### I told B2 engine 9 publishes no `pair`. It always did, and I had read the spec

**Agent:** C (engines and models), session 4 · **Task:** spec 96 · **Date:** 2026-09-16

**What happened.** B2 asked whether engines 9 or 14 publish a `pair`, because engine 16's
coherence walk checks any payload that carries one against `state["scout"]["pair"]`. I
answered that engine 9 does not, argued that it should, and asked the lead to amend spec
96's field list. The lead approved the amendment. **Engine 9 has published `pair` since
session 3 built it** — `SlippageEstimate.pair`, set from
`_require(state.get(SCOUT_KEY), SCOUT_PAIR_FIELD, SCOUT_KEY)`, verbatim from scout, and
written by `to_state_data`.

**Why.** I answered from **spec 96's step 4 field list**, which names
`estimated_slippage_pct`, `basis_notional` and `levels_consumed` and does not mention
`pair`. I had swept the engine's tests and read its refusal paths; I had not read its
payload model. This is the exact mistake the lead has now made three times from the other
direction — naming a mechanism without checking its signature against the job — and the
correction in both directions is the same: **build against the code, not against the
description of it.** I had been told that an hour earlier and then did the opposite.

**Fix.** Nothing in the engine. B3-store told that the field is already there, and my
message to B2 corrected. The spec amendment is still worth having, because a field list
that omits a field the engine publishes is a document that will mislead the next reader
exactly as it misled me.

**What the episode did produce, and it is worth more than the correction.** My argument to
the lead was about a **cached or misread** pair — a slippage number in range, plausible
and about the wrong market, with engine 10 pricing a hurdle on it. Checking the tests, the
published pair was asserted, but only ever on a single tick against a `state` built with
that same pair. **One tick cannot tell an echo from a cache**: the assertion is satisfied
by an engine that reads scout, by one that re-derives the pair from the book it fetched,
and by one holding the first pair it ever saw. Two sources agreeing by construction is the
witness problem, and it means the hazard I had just described to the lead was uncovered.

`test_the_published_pair_follows_scout_across_ticks_rather_than_being_cached` drives **one
engine instance over two ticks with different candidates** and asserts the published pair
follows scout each time, plus that the two slippage estimates differ — otherwise the pair
could be wrong with no observable consequence on this fixture. Mutation O6 caches the
candidate on the instance: **KILLED, by that test and by nothing else in 56**, which is
the answer to "which test killed it" and confirms it was the only cover.

### Decision: the aggregation across a version's folds, which spec 97 never named

**Agent:** C (engines and models) · **Task:** spec 97 step 3 · **Date:** 2026-09-16

The lead raised this after approving the weighting rule, and it is not obvious: the
leaderboard holds **one row per model version per fold**, and the rule weights **versions**.
There is an aggregation step between the rows and the weight, and the three candidates give
three different numbers.

**Options.** The unweighted mean of the per-fold skills; the most recent fold's skill; a
fold-count-weighted mean.

**Chose the unweighted mean**, which is the lead's prior and I agree with it. The question
engine 14 asks is *how good is this model version*, and each fold is one out-of-sample
measurement of it. A most-recent-fold rule encodes a judgement about recency; a
fold-count-weighted mean quietly rewards a version for having been around longer. The
unweighted mean is the only one of the three that does not add a second, unstated judgement
to the one being asked.

**Two things the lead did not ask about, and one of them changes the answer.**

**Duplicates are not folds.** B's `leaderboard_entries` docstring records that there is no
unique index on `(model_id, model_version, fold)` and that it deliberately returns *every*
match, so a broken idempotency convention stays visible rather than being collapsed by the
reader. Those rows reaching a mean-over-folds would weight one fold twice — a weighting
decision made by a duplicate row rather than by a measurement. So engine 14 keeps the
latest row per `(version, fold)` by `updated_at` and reports how many it collapsed in
`basis`. Absorbed silently, the duplicate would move the weight and leave nothing to notice
it by; collapsed and counted, the broken convention is still visible where B wanted it.

**Only this engine's own model family is weighted.** The leaderboard is keyed on
`(model_id, model_version, fold)` and nothing stops a second family appearing in it.
Weighting across families would put a predictor's Brier in a distribution with a score
measured on a different question, and normalising would hand that family part of the
predictor's weight. There is exactly one family today, which is precisely why this would
have been unnoticeable — and it is what spec 97's "at least two distinct `model_id`s"
requirement for the fixture is *for*, which I only understood once I had to build the
fixture.

**Cost.** The aggregation is **inert on the real table**: engine 20 writes one row per
`(version, fold)` and the fold's artefact run id *is* the version, so every real version has
exactly one fold and all three aggregations agree. The fixture is the only thing that can
tell them apart, and `test_the_mean_across_a_versions_folds_is_unweighted` asserts the
fixture still carries a multi-fold version — otherwise the branch is green and unreached.

### Spec 97 — eight mutations, eight killed, and which test killed each

**Agent:** C (engines and models) · **Task:** spec 97 · **Date:** 2026-09-16

Harness `scratchpad/mutate_ar.py`, same guarantees as the other sweeps: baseline first with
a refusal if it is red, byte copy before the mutation, sha256 compared in the same statement
that restores it, every anchor asserted to occur exactly once, witnesses hashed both sides
and unchanged on all eight runs. Arm `tests/engines/test_adaptive_router.py`. **Excluded and
named:** everything else, because engine 14 is inert — nothing downstream reads its payload,
so no other file could observe a change in it, and a wider arm would add runtime and no
coverage. R6 is the exception and it mutates *engine 15's* source, for the reason below.

| | Mutation | Verdict | Killed by |
|---|---|---|---|
| R1 | the clip at zero removed — spec 97's first named one | KILLED | the below-base-rate test and the whole-rule test |
| R2 | the mean across folds replaced by the most recent fold | KILLED | the aggregation test and the whole-rule test |
| R3 | the model-family filter dropped | KILLED | `test_a_second_model_family_is_not_weighted` |
| R4 | duplicate `(version, fold)` rows kept as separate folds | KILLED | `test_a_duplicate_row_for_one_fold_is_collapsed_to_the_latest` |
| R5 | the truncation tripwire removed from the windowed read | KILLED | `test_a_full_window_publishes_no_weights_rather_than_a_partial_distribution` |
| R6 | engine 15 reading engine 14's weights — spec 97's third named one | KILLED | `test_engine_fifteen_does_not_read_this_payload` |
| R7 | a missing base rate defaulted to 0.25 | KILLED | `test_a_version_with_no_base_rate_gets_zero_rather_than_a_default` |
| R8 | the approved rule starts using the regime — spec 97's second, made concrete | KILLED | `test_the_regime_does_not_change_a_single_weight` |

**R1 is the one worth reading, because it leaves everything looking right.** Removing the
clip lets a version with *negative* skill shrink the denominator, so every other weight goes
**above** its true share — and the weights still sum to one, every value stays in [0, 1], and
the below-base-rate version still reads lowest. Nothing about the shape of the answer says it
is wrong. What catches it is the whole-rule test recomputing the expected weights from the
fixture's rows by a second implementation, plus an explicit control asserting the best
version does *not* equal `0.45 / 0.30`, which is what the unclipped denominator would give.

**R6 had to be applied to engine 15, not to engine 14**, and that is the point of it. Spec
97's claim is about the *consumer* — that the skeptic's verdict does not depend on a weight —
and no mutation of engine 14 could ever show it. The test scans engine 15's own source and
contracts for this engine's state key, which is the structural form of the claim under
contract rule 3: engine 15 names every key it is allowed to reach, so the absence of
`adaptive_router` from that list is the guarantee.

**R8 is spec 97's second named mutation made buildable.** The spec says "the regime ignored
*if* the approved rule uses it" — the approved rule does not, so the informative mutation is
the inverse: make the rule start using it. A uniform regime factor would have been an
*equivalent* mutant, because normalisation cancels a constant, so the mutation boosts only
multi-fold versions when the regime is `trending`. That is what a regime-conditional rule
would actually look like, and it is killed by the test asserting the weights are identical
across all three regime labels.

**No survivors, so nothing was re-run wide.**

### Amendment: the lead's fold-aggregation ruling, corrected by what the store does

**Agent:** C (engines and models) · **Task:** spec 97 step 3 · **Date:** 2026-09-16

Correcting the Decision entry above with a new entry rather than editing it, per script rule
6. The lead has accepted the duplicate-row handling **as an amendment to ruling 3 rather than
as a detail of the implementation**, and the distinction matters enough to record.

Ruling 3 was "the equal-weighted mean across a version's folds". Written literally, and
applied to what `leaderboard_entries` actually returns, that weights a fold **twice** when
the table holds two rows for it — because B's read deliberately returns *every* match on
`(model_id, model_version, fold)`, there being no unique index, precisely so that a broken
idempotency convention stays visible rather than being collapsed by the reader.

So under the ruling as written, **a weighting decision would have been made by a data
artefact rather than by a measurement.** The amendment: collapse to the latest row per
`(version, fold)` by `updated_at`, and **report how many were collapsed** in `basis`. The
arithmetic stops depending on the artefact, and B keeps the visibility the store was built
to give — the duplicate is still discoverable, it just no longer moves a number.

The general form, which is the part worth carrying: **a rule stated over "folds" is not
stated over "rows", and the gap between them belongs to whoever wrote the read.** Neither
the spec nor the ruling could have caught this, because both were written against the
concept and the hazard lives in the storage.

### Why the fixture requirement I did not understand was the one that found the defect

**Agent:** C (engines and models) · **Task:** spec 97 step 6 · **Date:** 2026-09-16

Spec 97 requires the leaderboard fixture to carry **at least two distinct `model_id`s**, and
it does not say why. I read that as "make the fixture varied" and nearly wrote one family
with three versions, which satisfies every other clause in the step.

Building the second family is what made me ask what engine 14 should do with it — and the
answer is that it must be excluded entirely, because normalising across families hands one
family part of another's weight. **There is one model family on the real table today, which
is exactly why this would have gone unnoticed**: with a single `model_id` the filter never
fires, the weights are correct by accident, and no test, metric or review could distinguish
an engine that filters from one that does not.

So the requirement was load-bearing and I could not see it from the requirement. The
transferable part: **write the fixture the spec asks for even when the reason is not
stated**, because a fixture clause that looks like arbitrary variety is often the only thing
standing between a correct-by-accident branch and a measurement. Mutation R3 drops the
filter and dies on `test_a_second_model_family_is_not_weighted`; without that fixture row,
R3 is an equivalent mutant and the sweep reports a clean kill rate over a hole.

### Correction: the scipy import crash is the known native fault, not unexplained

**Agent:** C (engines and models) · **Task:** spec 97 · **Date:** 2026-09-16

I filed the wide-arm crash as `unexplained`. **That attribution is wrong and the lead
corrected it.** A `Windows fatal exception: access violation` is the signature of the native
memory fault in the tracker's Known Risks, open since Phase 0 and seen inside pydantic-core,
inside `sqlite3`'s C extension, inside pure-Python PyYAML and inside CPython's own
`ast.walk`. Four unrelated libraries, one of them not compiled, which is what process-level
memory corruption looks like and is not what any library defect looks like.

**The new site is `scipy._lib._array_api._make_capabilities_note` → `textwrap.dedent` →
`re.sub`, during `import sklearn`, before any test ran.** The locus is new; the signature is
not. My evidence fits it exactly — nothing of mine on the stack, the identical command clean
immediately afterwards, and `tests/engines/` green through the same imports an hour earlier.

The standing rule I should have applied first: **suspect the known native fault before
treating a one-off in an untouched path as a defect.** `unexplained` stays an acceptable
thing to write, and writing it where a documented mechanism already fits is not caution, it
is a second unexplained entry diluting a real one. Distinct from the Phase 5 scipy entry,
which was a `TypeError` during collection and remains genuinely unexplained.

### Correction: spec 96's field list was wrong, and that is half of the `pair` mistake

**Agent:** C (engines and models) · **Task:** spec 96 · **Date:** 2026-09-16

Correcting my own earlier entry with a new one, per script rule 6. I wrote that telling B2
"engine 9 publishes no `pair`" was my mistake for reading spec 96's field list instead of
`engines/order_book/contracts.py`. That is true and it is not the whole account: **the
field list was wrong.** The lead has amended spec 96 to list `pair`, with a note that the
engine always published it.

The general form the lead put on it, kept here because it is the reusable part: **a spec's
field list is a description; `contracts.py` is the fact, and where they disagree the spec
is what is wrong.** That is the same shape as spec 97 step 2 naming `leaderboard_entries`,
a method whose signature cannot enumerate — a conclusion written correctly and the nearest
plausible mechanism reached for without checking it against the job.

So the reading rule stands unchanged — build against the code — but the failure is not
only a reader's. A description that disagrees with the code will mislead every reader in
turn until somebody checks, and the fix is to correct the description rather than to
remember that a particular one was unreliable.

**What being wrong produced, which cost less than it returned.** The published pair had
only ever been asserted on single ticks, against a `state` built with that same pair — two
sources agreeing by construction — so a **cached** pair was uncovered in the one engine
whose output is defined by which market it walked. Mutation O6 caches the candidate on the
instance and now dies on `test_the_published_pair_follows_scout_across_ticks_rather_than_
being_cached`, and on nothing else in the file.

### Migration 0004 landed, and the double was simpler than the read in the one dimension that changed

**Agent:** C (engines and models) · **Task:** spec 97 close-out · **Date:** 2026-09-16

**What happened.** B3 landed `all_leaderboard_rows(*, model_id)` and `base_rate_brier`.
Engine 14 called `enumerate_all()` with no argument, which raised `TypeError` and was red
in B3's lane before it was red in mine. One line. But re-pointing the tests at the real
row model turned 15 of 26 red with `_Store._all() got an unexpected keyword argument
'model_id'` — **the test double had the old signature**, and it had been green for as long
as the engine and the double agreed with each other rather than with the store.

**Why that is worth an entry rather than a fix.** It is `code-standards.md`'s double rule
arriving from the direction that rule does not describe. The usual form is a double too
simple to exhibit the property under test. This one was faithful enough on the day it was
written and then **stopped tracking the thing it stood for**, silently, because nothing
compares a double's signature against the real method. The engine and the double moved as
a pair and the store moved separately.

**Fix, and the part that is not just a signature.** `_Store` now mirrors
`all_leaderboard_rows` faithfully — **including that the store filters by family itself**
— and records the `model_id` it was asked for. Modelling the filter honestly immediately
exposed something I had not seen: **on the enumerating path engine 14's own family filter
is redundant**, because the store has already applied it. The filter is only load-bearing
on the **windowed fallback**, which returns every family.

So `test_a_second_model_family_is_not_weighted` now drives the *windowed* store. Left on
the enumerating path it would have been green against an engine with no filter at all —
the store would have filtered for it — and mutation R3 would have become an equivalent
mutant without anything saying so. It is the witness rule again: two sources capable of
producing the same correct answer, and the test must drive the one where only the subject
can.

A new test asserts the store was **asked** for `MODEL_ID`, rather than asserting the rows
that came back, because a filtered result is equally consistent with the engine filtering
afterwards. Mutation R9 asks for a different family: killed by eight tests.

**B3's `model_id` being required rather than defaulted is right** and the reasoning is
worth keeping: the read has no `LIMIT`, and "no limit" is only safe because one model's
rows are bounded by its walk-forward while the table is bounded by nothing. A default
would hide the scope at the call site, which is the same fault as the truncating window.

### The truncation tripwire was wrong on the real read, and B3 found it by reading

**Agent:** C (engines and models) · **Task:** spec 97 close-out · **Date:** 2026-09-16

**What happened.** The tripwire was `len(rows) == _WINDOWED_PROBE` on **both** read paths.
B3 pointed out that against the unlimited read it fires on a model that genuinely has
exactly `_WINDOWED_PROBE` rows — a false positive costing that tick **all** of its weights.

**Why it was wrong.** "Came back exactly full" is a fact about a *limited* read. The
enumerating read has no limit, so the comparison is not a weaker version of the check, it
is a different claim that happens to share its arithmetic — and one that cannot
distinguish a truncation from a coincidence. Over 405 folds the coincidence is not
negligible.

**Fix.** The length check stays on the windowed fallback, where it is exactly right, and
is gone from the enumerating path. The lead's requirement that the detection survive B's
read as "the assertion that the fallback is unreachable" is met **by a test** rather than
by a runtime heuristic, which is what an assertion is. `test_a_window_that_did_not_fill_is_
weighted_normally` and `test_a_full_window_publishes_no_weights_rather_than_a_partial_
distribution` keep the fallback's behaviour pinned; R5 still kills.

**Found by a colleague reading the code.** No fixture would have had exactly that many
rows, so no test would ever have shown it, and the sweep would have reported a clean kill
rate over it. Worth recording as evidence that review catches a class of defect mutation
testing structurally cannot: a wrong branch that no input in the suite reaches.

### One red in B's lane that I could not attribute, and did not

**Agent:** C (engines and models) · **Task:** spec 97 close-out · **Date:** 2026-09-16

`tests/clients/store/test_store.py::test_all_leaderboard_rows_is_scoped_to_one_model`
failed once in a batch of 180 and passed on an identical re-run of the same batch, same
order, minutes later. B3 had told me it was landing that exact method at that time.

**I did not hash the file on either side, so I cannot prove it was a save rather than a
flake** — `code-standards.md` says to hash what is not the variable on both sides of an
A/B in a shared checkout, and I did not. The honest statement is that the evidence is
consistent with B3 mid-save and I cannot rule out the native fault. Recorded as B's, not
chased, and flagged to B3 rather than filed as a defect. Re-running in isolation passed,
which tells me nothing and is noted only so nobody treats it as having told me something.

### Spec 104, diagnosis — engine 19 read an errored engine as a refusal with no code

**Agent:** C (interface and models) · **Task:** spec 104 · **Date:** 2026-09-16

The diagnosis is A's (`a-platform.md`, "an ERROR anywhere in the opportunity chain leaves the
tick unrecorded"). This is where in engine 19 it happens, re-derived from the code and
reproduced before any change.

**What happened.** On a tick where an opportunity-chain engine raises, engine 19 raises too, so
the tick has no `block_records` row, no `rejections` row and no `equity_snapshots` row.
Reproduced on unmodified engines with a lighter chain than A's: guard 1, 2, 3, 4, 17;
opportunity 5, 7, 18 (no engine 16, so a real engine 18 raises `ExecutionError: decision.intent
is absent`); manage 19; the scripted market at tier 3 behind B's paper broker. Tick 2 logged two
`engine_error`s, engine 18's and engine 19's `MissingInputError: engine 'execution' refused
'BTC/USD' without publishing a 'reason_code'`, and `state["memory"] == {}`.
Probe: `scratchpad/c104/probe_error.py`, output `probe_error.log`. No model is trained: engine 7
ranks alphabetically while `scout.rank_feature` is absent, so engines 5 and 7 produce a real
candidate on flat bars, which is all the defect needs.

**Why, in `src/acsoe/engines/memory/engine.py`.** Two functions, each right about the case it
was written for:

- `_write_block_records` writes rows from `state["guard_blockers"]` only. An opportunity-chain
  blocker never enters that list (the orchestrator appends only in the guard chain), so no row
  can exist for it whatever its status.
- `_write_rejection` decides "this is a rejection" from two facts: the primary blocker is not a
  guard, and scout published a pair. **Neither fact says whether the blocker decided anything.**
  It then reads `reason_code` from the blocker's payload, which rule 7 has emptied, and raises
  on purpose. The raise comes after positions and orders are written and before
  `_write_equity`, so the tick is half recorded.

Until the lead's `state["block_status"]` landed, the only way to tell an error from a refusal
here was the empty payload, and that is also exactly what a gate that blocked **without** its
code looks like — the case the raise exists for. Now the orchestrator publishes the status, so
engine 19 can read the fact instead of inferring it.

**What the fix must keep.** A `BLOCK` with no `reason_code` still raises (a gate breaking its
contract). A guard that errored is still recorded from `guard_blockers` alone, with no second
row. And `is_primary` on the new row is true because the opportunity chain runs only when no
guard blocked, so the unique primary index cannot be hit twice on one tick.

### Spec 104, fix — engine 19 reads `block_status`, and the errored engine gets one row

**Agent:** C (interface and models) · **Task:** spec 104 · **Date:** 2026-09-16

**Fix**, in `src/acsoe/engines/memory/` only:

1. `contracts.py`: `BLOCK_STATUS_KEY = "block_status"` and `REASON_ENGINE_ERRORED =
   "engine_errored"`, both exported. The comment on `TRADING_BLOCKED_BY_KEY` no longer says
   that every non-guard blocker is a rejection.
2. `engine.py`: one helper, `_errored_opportunity_engine(state)`, returns the blocker's name
   only when `state["block_status"] == "ERROR"` and the blocker is not in `guard_blockers`.
   `_write_block_records` writes the guard rows exactly as before, then, if the helper names
   an engine, one more row: that name, `status` `ERROR`, `block_reason` `engine_errored`,
   `is_primary` true. `_write_rejection` returns 0 for the same case **after** the guard check
   and **before** it reads the candidate or any `reason_code`. Nothing else moved, so
   positions, orders and the equity row are written in their usual order.
3. `console/format.py`: `engine_errored` → "A check failed with an error before it could
   decide, so nothing was traded; the log for this tick says why". It says *failed* and not
   *refused*, and it points at the log, because the engine's own error is not on the row. My
   first draft also said repeated errors would freeze trading. I cut it: that is a threshold
   the row does not carry, and the table's rule is that no sentence adds one.
4. `README.md`: a section for the errored engine and the two neighbouring cases, and
   `block_status` in the table of keys read.

**Decisions made on the way.**

- **An absent `block_status` reads as "not an error".** The orchestrator always publishes it
  beside `trading_blocked_by`, so absence comes only from a hand-built `state`. The alternative
  was refusing the tick, which would turn every older hand-built test red without protecting
  anything the orchestrator can produce. With the key absent, a blocker with no code still
  raises, which is the fail-loud direction. `a_rejection()` in the test file now carries
  `block_status: "BLOCK"`, so the fixture looks like what the orchestrator actually publishes.
- **`block_reason` is `engine_errored`, not the orchestrator's `unhandled X: ...` text.** The
  spec and invariant 12 both say so. The exception text is in the log line the orchestrator
  writes for the same `(run_id, cycle_id)`, and the prose sends the operator there.
- **`is_primary` is hard-coded true, not derived.** The opportunity chain runs only when no
  guard blocked, so there is nothing to be primary against. If a hand-built `state` ever had
  both, the unique index `ux_block_records_primary` would refuse the second primary, and that
  refusal is the visible symptom this engine already relies on.

**A wrong turn, mine.** The first run of the new tests failed one of them with
`tick() got multiple values for keyword argument 'exchange'`: the guard-error test passed
balances *and* an empty `exchange` payload. The empty payload is the right one (an errored
guard's payload is `{}`), so the balances went. That one is a test typo, not a finding.

**The lighter chain, and why it counts as "a real raising engine".** The orchestrator test
runs guard 1, 2, 3, 4, 17; opportunity 5, 7, 18; manage 19, all real, at fee tier 3 behind
B's paper broker, with no trained model. Engine 18 raises its own `ExecutionError` because
engine 16 is not in the chain. That is the same raise A's probe produced with the full chain,
reached for less. Nothing about the status is hand-built. The test asserts that the tick had a
real candidate (`state["scout"]["pair"]`), because without one the old code never reached
the raise and the test could not have gone red.

### Spec 104 — six mutations of engine 19, six killed, and a control that survived everywhere

**Agent:** C (interface and models) · **Task:** spec 104 · **Date:** 2026-09-16

Harness: `scratchpad/c104/sweep104.py`. It takes a byte copy first, checks every anchor
occurs exactly once, sets `PYTHONDONTWRITEBYTECODE=1`, passes `-p no:cacheprovider`, uses
`sys.executable`, and restores in a `finally` before the next arm with the sha256 compared in
the same statement. It gives no verdict without a pytest summary line. `engine.py` is 0 CRLF,
LF only, counted in Python before the sweep. Before the sweep I also checked the `tests/verify/`
patchers that anchor on this file's text (`test_phase4_criteria.py`, ten anchors): each still
occurs exactly once after the change, and the control's line (`return len(blockers) + 1`)
occurs nowhere in `tests/` or `scripts/`. File sha256 before and after every arm:
`5b10da0c08f0eaf72f237a388e8eb1f7f2122bb213745d4084ab9778aa782712`. Narrow target:
`tests/engines/test_memory_rows.py`, with a baseline of `39 passed`. Logs:
`logs/verify/c104-sweep-*`.

| Arm | Mutation | Mutant sha256 | Verdict | Killing test (written for it) | Red message |
|---|---|---|---|---|---|
| M1 | the ERROR skip in `_write_rejection` → `if False:` (**ERROR treated as a rejection**) | `feb9c7858147…` | killed, `4 failed, 35 passed` | `test_an_engine_that_raised_is_recorded_through_the_real_orchestrator` (spec 104's named check) | `engine 19 raised on the errored tick` — the orchestrator logged `MissingInputError: engine 'execution' refused … without publishing a 'reason_code'` |
| M2 | `status=BlockStatus.ERROR` → `BLOCK` | `821d40b207e0…` | killed, `3 failed` | `test_an_errored_engine_writes_a_block_record_no_rejection_and_the_equity_row` | `engine 17's error rate counts status = 'ERROR'` / `'BLOCK' == 'ERROR'` |
| M3 | a `RejectionRow` written as well (`reason_code=engine_errored`) | `adb4d27cc819…` | killed, `4 failed` | orchestrator test, and `…writes_a_block_record_no_rejection…` | `an engine that raised refused nothing` |
| M4 | `process` returns before `_write_equity` on the errored path | `2c6d545b2c98…` | killed, `2 failed` | orchestrator test, and `…writes_a_block_record_no_rejection_and_the_equity_row` | `the errored tick has no equity row, so the tick was lost` / `assert 0 == 1` |
| M5 | the error inferred from an empty payload (`state.get(str(blocked_by)) != {}`) instead of `block_status` | `a7eddcb9d892…` | killed, `3 failed` | `test_an_engine_that_raised_and_a_gate_that_blocked_without_a_code_are_different_facts` and `test_an_errored_engine_is_never_asked_for_a_reason_code` | `DID NOT RAISE MissingInputError` / `[] == ['engine_errored']` |
| M6 | `is_primary=True` → `False` | `0dfa8ea5d79e…` | killed, `3 failed` | orchestrator test, `…with_no_candidate…`, `…writes_a_block_record…` | `(…, 0)] == [(…, 1)]` |
| E1 | **equivalent control**: `return len(blockers) + 1` → `return 1 + len(blockers)` | `58a20dffce58…` | survived: `39 passed` narrow; `1259 passed` wide | — | — |

**Which test killed what.** Every kill landed on a test written for that property. Two notes
beside them. M5 also killed the older `test_a_refusal_without_a_reason_code_raises…`, which is
the same fact seen from spec 50's side, so it is not an incidental kill. M1 also killed
`…different_facts`, whose second half runs the errored tick. The orchestrator test is red
under M1, M2, M3, M4 and M6, which is what spec 104's "Check When Done" asks of it. It is
**not** red under M5, and it should not be: its payload is `{}`, so inferring the error from
the emptiness gives the right answer there. The two hand-built tests are the ones that tell
the two readings apart.

**The control against the wider suite.** Baseline over `tests/engines tests/console
tests/verify/test_phase4_criteria.py tests/core`: `1259 passed, 1 warning in 363.50s`
(`logs/verify/c104-wide-baseline.log`). E1 over the same set: `1259 passed, 1 warning in
357.71s`. No crash and no native fault in either run. After the sweep the file's hash is the
same as before it, and `git status` shows only my lane's files.

### Spec 105, first runs — the new position carries no mark on its fill tick, and one unexplained raise

**Agent:** C (interface and models) · **Task:** spec 105 · **Date:** 2026-09-16

**What happened (1).** The first complete run of `paper_equity_continuous_across_fill` on the
real tree reached the fill and returned FAIL: `entry 1690626088 filled and the store holds 1
position(s) for it with no mark`. The chain did approve, place and fill the entry at tier 3,
and engine 19 wrote both equity rows. What stopped the criterion was my own reading of "the
mark": I took it from `positions.last_price`, and on the fill tick that column is NULL.

**Why.** Engine 21's `_mark` (B's) does not re-mark a position opened by this tick's fill.
It adds `qty * entry_price` to `positions_value` and publishes the row without `last_price`
or `unrealised_pnl`. Its docstring says such a position "is worth what was just paid for it,
and `last_price` on a position that has existed for no time is the fill price". So on the
fill tick the mark **is** the fill price, but it is recorded only through the equity row's
`positions_value`, never on the position row. From the next tick on, `last_price` is the bid.

**How the bound handles it.** I did not widen it. The mark now comes from the store in one of
two ways, and each is checked rather than assumed:

- if the position row carries a `last_price`, that is the mark;
- if it does not, the equity row's `positions_value` must equal `qty x fill price` **exactly**,
  with exactly one open position, and the mark-to-bid gap is then zero.

A position valued at anything else with no mark is a FAIL. The tolerance on the fill tick is
therefore the maker fee alone, which is the tightest honest bound.

**For B, not changed by me.** The docstring's "`last_price` ... is the fill price" reads as a
statement about the stored row, and the stored row says NULL. The console would show that
position with no mark for one tick. This is reported to the lead as an observation, not a
defect; the engine is B's.

**What happened (2).** The very first invocation, through a throwaway script that called
`run_criterion`, returned after 0.7 s with `criterion raised - TypeError: 'float' object is
not callable`. That is before any training could have started. I did not keep a traceback.
Three later runs of the same code (one calling the check directly, two with a traceback
handler) did not reproduce it. The shape, a nonsensical `TypeError` once with no
reproduction, fits the registered native fault's corrupted-interpreter family (B's
`'MappingEndEvent' has no len()` today). I checked the other mechanisms: no stale `.pyc`
(`PYTHONDONTWRITEBYTECODE=1`), no concurrent writer (I am alone in the checkout), and no
tmp-dir sweeper symptom. Without the traceback this cannot be proven, so it is recorded as
**consistent with the native fault, not attributed**. The harness now keeps tracebacks.

### Spec 105 — my PENDING test ran the whole chain and reported PASS, because `bare_tree` is not an absent subject

**Agent:** C (interface and models) · **Task:** spec 105 · **Date:** 2026-09-16

**What happened.** My first PENDING test pointed the criterion at `bare_tree`, as spec 100's
`test_pending_on_a_tree_with_nothing_built` does. It came back **PASS**: the criterion
trained its subject, drove three ticks and judged the fill, all against a tree with no
`src/`.

**Why.** The editable install makes the real `acsoe` importable from any directory, and
pytest puts the repository root on `sys.path`, so `tests.harness` resolves as well.
`root_import_path` only shadows what the tree actually carries. `unbuilt_tree` in
`tests/verify/conftest.py` exists for exactly this and says so in its docstring. I had not
read it.

**Fix.** The test uses `unbuilt_tree`, an empty `acsoe` package that shadows the real one.
There the criterion is PENDING and names engine 9 and spec 96, the first engine it needs.

**For the lead, and it is spec 100's rather than mine.** Spec 100's nine criteria pass
`test_pending_on_a_tree_with_nothing_built` on `bare_tree` only because their bodies end
in a hard-coded PENDING ("not written yet"). The day a body is written, the same test will
run the real chain from the real repository and report PASS or FAIL on "a tree with nothing
built". That test should move to `unbuilt_tree` when the bodies land.

### Spec 105 — the criterion, observed PENDING, PASS and FAIL, and the broker broken in place

**Agent:** C (interface and models) · **Task:** spec 105 · **Date:** 2026-09-16

**What landed.**

- `scripts/verify.py`: `check_paper_equity_continuous_across_fill`, registered for phase 6 after
  spec 100's nine. `_trained` and `_constructed_dataset` gain an optional `macro_archive`,
  passed to `build_dataset` only when given, so the Phase 5 criteria train exactly as before.
- `tests/verify/test_phase6_criteria.py`: five tests. `EQUITY_ACROSS_FILL` is kept out of
  `PHASE6_CRITERIA`, so the parametrised real-tree PENDING test does not gain a ninth red.
- `tests/verify/test_runner.py`: the phase-6 set now includes the new name.

**The subject** is A's spec 87 rehearsal, rebuilt from verify.py's own pieces.
`_constructed_candles` is the same formula as `tests/research/test_training.py`, trained over
four folds with `btc` joined from `AAAUSD`, and the replay window ends 200 bars before the
series end. All 21 engines are real and run in registry order. The chains are hand-built
because spec 82 is held, and the docstring says to read `bootstrap.py` once it lands. The
market is the scripted market at fee tier 3 behind `PaperBroker`, and the store is a real
`StoreClient` in a temporary directory. The ticks are quiet, entry, then a planted trade at
`limit x 0.999`, then the fill tick. Training costs about 30 s and is cached per repository
root, like `_TRADE_SUBJECTS`; the store and the broker are never cached. A whole run takes
about 32 s.

**The tolerance.** It is read from the store alone:

- the fee, quantity and fill price come from the entry's `orders` row;
- the mark comes from the `positions` row's `last_price`, or, when that is empty, the fill
  price, but only if the equity row's `positions_value` is exactly `qty x fill price` with one
  open position;
- `tolerance = fee + qty x |mark - fill price|`, and the verdict is
  `|equity(fill tick) - equity(entry tick)| <= tolerance`.

It also checks that the row before the fill is the entry tick's (`cycle_id - 1`). On this
subject the mark gap is zero, so the bound is the maker fee alone, and equity moved by exactly
minus the fee.

**Observed messages, verbatim.**

PASS (real tree, `logs/verify/c105-probe-real-3.log`):

> equity 5000.00 on cycle 2 and 4996.3343443507499 on the fill tick, cycle 3: it moved -3.6656556492501. The fill's own cost is 3.6656556492501: fee 3.6656556492501 + 26.26015939 x |mark 126.9 - fill 126.9|, recorded for BTC/USD entry 1690626088 (notional 3332.414226591); at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers

FAIL (the real `broker.py` broken in place, arm B1, `logs/verify/c105-inplace-B1-unrecorded-fill-excluded.log`):

> equity 5000.00 on cycle 2 and 8332.414226591 on the fill tick, cycle 3: it moved 3332.414226591. The fill's own cost is 3.6656556492501: fee 3.6656556492501 + 26.26015939 x |mark 126.9 - fill 126.9|, recorded for BTC/USD entry 1690626088 (notional 3332.414226591). Equity moved by more than the fill cost, so the cash and the position disagree about when the fill happened. The paper ledger must count every fill the broker has executed, recorded or not (invariant 2, spec 103); otherwise the notional is counted twice and peak_equity carries it into engine 17's drawdown; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers

`8332.414226591` is A's finding-1 figure to the digit.

PENDING (`unbuilt_tree`): the message names engine 9 `order_book` and spec 96, and then "will run
at fee tier 3 ...".

**The in-place cross-lane run**, approved by the lead and made once through
`scratchpad/c104/sweep105.py`. It takes a byte copy of `src/acsoe/clients/paper/broker.py`
(0 CRLF, anchor `for userref, executed in list(self._executed.items()):` exactly once, and no
test or script anchors on it), restores in a `finally`, and compares the sha256 in the same
statement. `PYTHONDONTWRITEBYTECODE=1`, `sys.executable`, `-X faulthandler`.

| Arm | Mutation | Mutant sha256 | Result |
|---|---|---|---|
| B1 attempt 1 | `... in []:` | `c15e1c2a…bfa0a4c1` (A's B1, identical) | **no result**: exit `0xC0000005`, empty output. The registered native fault, not counted. Log moved to `logs/verify/c105-crashed/B1-attempt1.log` |
| B1 attempt 2 | same | same | **FAIL**, quoted above |
| B0 control | `list(...)` → `tuple(...)` | `f5a55ae4…73cc8d7` | PASS, identical numbers to the real tree |

The broker's sha256 was `98c0df710256e4fb65c0e9dc6bf58acca6547eb2e38c7a088be01e28c70e6201`
before and after every arm, and `git status` never showed it modified. The committed FAIL test
makes the same break in the copied `phase6_tree`, never in the real file, and hashes the real
file on both sides.

### Spec 105 — eight mutations of the criterion: six killed, one equivalent, one control

**Agent:** C (interface and models) · **Task:** spec 105 · **Date:** 2026-09-16

Harness: `scratchpad/c104/sweep105v.py`, the spec 104 harness pointed at `scripts/verify.py`
(0 CRLF; every anchor exactly once in the file and absent from `tests/`), with a byte copy, a
`finally` restore and the sha256 in the same statement. File sha256 before and after every
arm: `f2299ae8fb19a000b633e4e29833e629a6348858fbdb539826c42ed03b5e0844`. Narrow target:
`test_phase6_criteria.py -k equity_across_fill`, baseline `4 passed` (then `5 passed` once
the V7 test existed).

| Arm | Mutation | Mutant | Verdict | Killing test |
|---|---|---|---|---|
| V1 | tolerance also admits the notional | `87a0e497…` | killed, 2 failed | `…fails_when_the_broker_leaves_out_an_unrecorded_fill` (the defect passes); `…passes_on_the_real_tree` (bound != fee) |
| V2 | the comparison is `if True:` | `73308f43…` | killed, 1 failed | `…fails_when_the_broker_leaves_out…` |
| V3 | tolerance is `Decimal("5")` | `0b23fa5d…` | killed, 1 failed | `…passes_on_the_real_tree` (bound != fee). The FAIL test stayed red because 5 is below the notional, so a constant is caught only by the test that pins the bound to the fee |
| V4 | the fee is left out of the bound | `87afe97b…` | killed, 2 failed | `…passes_on_the_real_tree` (moved -fee is outside a zero bound) |
| V5 | PASS message without the tier sentence | `b60f05b4…` | killed, 1 failed | `…passes_on_the_real_tree` |
| V6 | the no-mark branch accepts any value (`elif True:`) | `9e2af240…` | survived narrow and wide (checked negative) | — the very next check (`positions_value != qty x mark`) refuses the same values, so the branch only chooses the message. Recorded as a checked negative, not a survivor |
| V7 | the entry-tick check becomes `if False:` | `5c64c500…` | **survived the first sweep**; killed after a new test, 1 failed | `…fails_when_the_entry_tick_wrote_no_equity_row`, written for it. It makes engine 19 skip the entry tick's equity row in the copied tree, so the last earlier row is the quiet tick's, which compares clean |
| E2 | control: `moved = -(before - after)` | `b62a5c03…` | survived narrow and wide | — |

**Survivors against the wider set.** The wider set was the whole of
`tests/verify/test_phase6_criteria.py` and `tests/verify/test_runner.py`. The baseline was
`8 failed, 53 passed`, and the 8 are the known
`test_pending_on_the_real_tree_names_the_subject_and_the_spec` parametrisations
(`logs/verify/c105-verify-wide-baseline.log`). V6 and E2 each gave `8 failed, 53 passed` with
**the same eight**. My harness printed "KILLED" for both because it reads the exit code and
does not compare against the baseline set; the failing sets are identical, so both survived.
**A correction to my own tool, recorded rather than hidden:** a verdict over a red baseline
has to compare failing sets, which `code-standards.md` already says.

**No ninth red.** The new criterion runs to PASS on the real tree, so it is not in
`PHASE6_CRITERIA` and does not join that parametrised test's failures.

### Spec 105 — the gate at the spec 105 boundary

**Agent:** C (interface and models) · **Date:** 2026-09-16

The tree is `3e1ded8` plus `scripts/verify.py`, `tests/verify/test_phase6_criteria.py`,
`tests/verify/test_runner.py`, this log and my progress file. I was the only agent in the
checkout, and nothing was running beside the gate. The four commands ran one after another,
each redirected to its own file, and each file was read in full.

| Command | Result | Log |
|---|---|---|
| `pytest tests/ -q` | `8 failed, 3197 passed, 2 skipped, 3 warnings in 1383.05s`; all 8 are the known `test_pending_on_the_real_tree_names_the_subject_and_the_spec` parametrisations | `logs/verify/c105-gate-pytest.log` |
| `mypy --strict src/ scripts/` | `Success: no issues found in 153 source files` | `logs/verify/c105-gate-mypy.log` |
| `ruff check src/ tests/ scripts/` | `All checks passed!` | `logs/verify/c105-gate-ruff.log` |
| `verify.py --phase 6` | `12 criteria: 2 PASS, 1 FAIL, 9 PENDING`; `paper_equity_continuous_across_fill` PASS, and `toolchain_green` FAIL on the same 8 (its own run: `8 failed, 3197 passed, 2 skipped`, no other failure) | `logs/verify/c105-gate-verify.log`, `logs/verify/toolchain_green/20260916T201415_806009-pytest-attempt1.log` |

The suite grew by 5 tests over spec 104's boundary (A's gate had 3165 passed). No native fault
crashed any of the four runs.

### Spec 100 — the nothing-built PENDING test never had an absent subject, measured before moving it

**Agent:** C (interface and models) · **Task:** spec 100, the lead's fix before spec 82 · **Date:** 2026-09-16

**What happened.** `test_pending_on_a_tree_with_nothing_built` runs the nine criteria against
`bare_tree`, which has no `src/`. I ran all nine against `bare_tree` and against `unbuilt_tree`
from a scratch probe (`scratchpad/c100b/probe_trees.py`), and the two trees give different
results. On `bare_tree`, **seven of the nine got past every engine guard** and stopped at the
hard-coded placeholder ("every engine and the paper broker exist; ... is not written yet").
The other two, engines 9 and 14, also found the **real** engine class and stopped only
because the fixture lookup is rooted at `ctx.root`, which has no `tests/fixtures/`. On
`unbuilt_tree` all nine report PENDING on an engine that "does not exist yet": engine 16, 21,
9 or 14.

**Why.** The editable install is a plain `.pth`, so `acsoe` resolves to the repository from
any directory, and `root_import_path` only shadows what the tree carries. On `bare_tree` the
subject is not absent, it is the developer's own. The test was green only because the nine
bodies end in a hard-coded PENDING. So it had never observed the thing its name claims.
**It could not see a criterion that mishandles an absent subject**, for example one that
reports FAIL or PASS when the engine import fails, because on its tree the import never fails.
And a correctly guarded body, once written, would run the real chain there and turn it red for
no fault. Phases 0 to 5 already route their import-based PENDING tests through `unbuilt_tree`.
Their remaining `bare_tree` entries (`db_migrates_from_empty`, `seed_fixtures_present`,
`record_sample_valid`, the four static console criteria, `recording_span_continuous`) gave
**identical** results on both trees in the same probe, because each one stops on a file under
`ctx.root` before any import. None of them is exposed.

**Fix.** `test_pending_on_a_tree_with_nothing_built` now takes `unbuilt_tree` and makes a second
assertion: the message must begin with `engine N `name` does not exist yet `. A PENDING for
any other reason, such as the placeholder, means the criterion got past a guard it had
nothing to pass. Nothing else moved. `test_the_tier_sentence_is_pending_rather_than_wrong_when_the_harness_is_absent`
also takes `bare_tree`, but it drives no criterion and deletes the fixture on its first line.
Its name promises a PENDING it never observes. I reported it to the lead and did not change it.

### Spec 100 — the moved test proved able to fail, and the old one proved blind, under the same mutants

**Agent:** C (interface and models) · **Task:** spec 100, the lead's fix before spec 82 · **Date:** 2026-09-16

**The lead's arm could not do what it was asked to show, and that is the first result.** The
lead asked for a mutant that makes a criterion "return PASS when its subject can be imported"
and expected the moved test to go red and the old one to stay green. It does the reverse. On
`unbuilt_tree` the subject cannot be imported, so a correctly guarded written body is PENDING
and the moved test is right to stay green. On `bare_tree` the subject *can* be imported, so the
old test goes red on a body that is correct. So I ran that arm and added the arms that separate
the two forms.

**Harness.** `scratchpad/c100b/sweep.py`. It copies `scripts/`, `tests/`, `config/`,
`context/`, `AGENTS.md`, `README.md` and `pyproject.toml` into `scratchpad/c100b/tree`, and
mutates the **copy's** `verify.py`. The real file is never written, and its sha256 is
`f2299ae8fb19a000b633e4e29833e629a6348858fbdb539826c42ed03b5e0844` before and after. In the
copy, each arm is written from a byte copy and restored in a `finally`, with the sha256
compared in the same statement. The file has 0 CRLF. The anchor is the whole held-stop guard
block in `check_triggered_stop_holds_on_data_guard_block` and occurs exactly once, because its
first line alone occurs twice. No test file carries the anchor text. Each run used
`PYTHONDONTWRITEBYTECODE=1`, `sys.executable -X faulthandler`, `-p no:cacheprovider`, and
required a pytest summary line. The pytest traceback shows the module was loaded from the
copy's `scripts/verify.py`. Three test forms ran, each over the nine criteria:

- **MOVED**: the committed test, which checks the result and the absent-engine message.
- **MOVED-r**: the same test on `unbuilt_tree` with the message assertion removed.
- **OLD**: the `76035be` body on `bare_tree`, verbatim, from a scratch test file in the copy.

| Arm | Mutation of the held-stop criterion | Mutant sha256 | Summary | Red |
|---|---|---|---|---|
| BASE | none | `f2299ae8fb19a000b633e4e29833e629a6348858fbdb539826c42ed03b5e0844` | 27 passed | — |
| W (the lead's) | written body: guard kept, PASS when the engines import | `987a930c203dbd4395b70c453b81c5ae87073f18c8ef58f712c1ab138e9401f5` | 1 failed, 26 passed | **OLD only**. MOVED is green, correctly |
| A | absent subject reported PASS: `if problem is not None: return passed(...)` | `c972de74a6ec148cbe69469406d86c9b85bd5d97fbdfb668814664e12aa4d888` | 2 failed, 25 passed | **MOVED** and MOVED-r. **OLD green** |
| G | guard dropped (`problem = None`), placeholder PENDING kept | `0420cff89e347de8ed34d8989d12ccc60ee1082edfe454c14a9b615dafd85bfc` | 1 failed, 26 passed | **MOVED only**. MOVED-r and OLD green |
| WG | guard dropped, written body returns PASS | `473558b19abedacca7f3cb6266718e143435a066195180b67572df5d95bd7e26` | 3 failed, 24 passed | all three |
| E0 | control: placeholder reworded | `9645364450be502470aa26e3e19c524a40e6cdc019e54e132929afbdc03d80cd` | 27 passed | — |

Every red is the `[triggered_stop_holds_on_data_guard_block]` parametrisation, and the other
eight stayed green in every arm. Logs: `logs/verify/c100b-sweep-<arm>.log`.

**The two verdicts the lead asked for.**

- **Moved test red, old test green, same mutant:** arms A and G. The killing test is
  `test_pending_on_a_tree_with_nothing_built[triggered_stop_holds_on_data_guard_block]`.
  Arm A: `AssertionError: Outcome(result=<Result.PASS: 'PASS'>, message='MUTANT A: held-stop reported PASS on an absent subject')`.
  Arm G: `AssertionError: triggered_stop_holds_on_data_guard_block: every subject exists; the held-stop driver of spec 100 is not written yet (C, spec 100) - ...`.
  On `bare_tree` the engines import in both arms, so the broken branch never runs and the old
  test passes.
- **The lead's arm W** turns only the old test red, on a correct body. That is the false
  alarm spec 82 plus the first written body would have raised.

**G is killed only by the new message assertion.** MOVED-r survives it because the result
is still PENDING. A criterion whose guard has been dropped keeps reporting PENDING until its
body is written, so a check on the result alone cannot tell "absent" from "not reached".

### Spec 107, diagnosis — spec 105's criterion accepts the defect spec 106 fixed, and engine 9 describes a fallback that is gone

**Agent:** C (interface and models) · **Task:** spec 107 · **Date:** 2026-09-17

**What happened (1).** `_judge_fill` in `scripts/verify.py` reads the fill-tick mark from the
`positions` row. When `last_price` is NULL it does not fail: it accepts the row if the equity
row valued the position at exactly `qty x fill price`, and then sets the mark-to-bid gap to
zero. I wrote that branch in spec 105 because engine 21 did store NULL on the fill tick then.
Spec 106 (B, `268f49e`) changed engine 21 so the fill-tick row carries `last_price` = the fill
price and `unrealised_pnl` = 0. B then ran its mutant P1, which removes that `last_price` write
again, against my criterion tests: **survived**, `15 passed` (B's build log, spec 106
mutations). So the branch is now reachable only by that regression, and the criterion reports
PASS on it.

**Why it matters.** It is a small hole, but the shape is the one this project keeps finding: a
criterion that accepts the broken form of the thing next to what it judges. The console reads
`last_price` (spec 101), so a NULL mark on the fill tick is a position shown with no price.
The criterion is the only phase-level check that reads that row on that tick.

**What happened (2).** `src/acsoe/engines/order_book/README.md` ("One deliberate asymmetry with
engine 11") and the `_basis_notional` docstring in `engine.py` both say engine 11 falls back to
`paper.starting_balances` when engine 1 publishes no balance. Spec 106 removed that fallback.
Engine 9's own rule (no balance, no estimate) is unchanged and correct; only the comparison is
stale.

**Fix (planned, spec 107).** The NULL-mark branch becomes a FAIL that names the missing mark.
The mark comes from `last_price` only, and nothing else in the bound changes. A new test makes
engine 21 skip the `last_price` write in the copied tree (B's P1) and requires that FAIL. The
two prose passages state engine 9's rule and point at invariant 2, without describing engine 11.

### Spec 107, fix — the NULL mark is a FAIL, and three mutations of the new branch

**Agent:** C (interface and models) · **Task:** spec 107 · **Date:** 2026-09-17

**Fix.** `_judge_fill` reads the mark from `positions.last_price` only. A NULL there is a FAIL
that names the missing mark, the fill tick's cycle, and spec 106. Nothing else in the bound
moved: the tolerance is still `fee + qty x |mark - fill|`, and the check that the equity row
values the position at `qty x mark` is still next. Engine 9's README section is renamed "No
balance, no estimate" and states engine 9's own rule, pointing at invariant 2 for the reason.
The `_basis_notional` docstring says the same in four lines. Neither mentions engine 11.

**The new test.** `test_equity_across_fill_fails_when_the_fill_tick_position_is_stored_with_no_mark`
deletes engine 21's `position_row["last_price"] = format(mark, "f")` in the copied
`phase6_tree` (B's P1; the anchor occurs once in engine 21 and nowhere in `tests/` or
`scripts/`), hashes the real engine 21 on both sides, and requires FAIL with the words
"stored with no mark (last_price NULL)". Under P1 the equity row is still exactly right,
because engine 21's totals are untouched. So the verdict can only come from the stored row,
which is what the test pins.

**P1, run once through a scratch probe on a copied tree** (`scratchpad/c107/probe_p1.py`,
`logs/verify/c107-probe-p1.log`), verbatim:

> FAIL | entry 1690626088's position is stored with no mark (last_price NULL) on its fill tick, cycle 3. Engine 21 stores the fill price as the mark of a position this tick's fill opened (spec 106), so the mark-to-bid part of the fill's cost cannot be read from the store; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers

Real engine 21 sha256 before and after: `2010de69d0163ac38aeda657da9ec928f71b51cb9e824178cd8eb01e9e46e4e8`.

**Mutations of the criterion** (`scratchpad/c107/sweep107.py`). It takes a byte copy of
`scripts/verify.py` (0 CRLF, each anchor exactly once), restores it in a `finally` before the
next arm, and compares the sha256 in the same statement. It runs with
`PYTHONDONTWRITEBYTECODE=1`, `sys.executable -X faulthandler` and `-p no:cacheprovider`, and
every verdict needs a pytest summary line. Narrow target:
`test_phase6_criteria.py -k equity_across_fill`, baseline `6 passed`. The file sha256 was the
same before the sweep and after every restore:
`a7040cd4699777e17a5d788e3fda7048a76f128efa945a22d2331533cc2e6b07`. Before choosing the control
I grepped `tests/` and `scripts/` for its text: `if position.last_price is None` occurs only
at the criterion's own line.

| Arm | Mutation | Mutant sha256 | Summary | Killing test |
|---|---|---|---|---|
| S1 | the pre-107 acceptance restored: a NULL mark is read as the fill price when the equity row values the position at cost | `c5c629ab770e…` | 1 failed, 5 passed | `…fails_when_the_fill_tick_position_is_stored_with_no_mark`: the criterion said PASS (`equity 5000.00 on cycle 2 and 4996.3343443507499 …`) |
| S2 | a NULL mark is always read as the fill price, and the FAIL is unreachable | `9c2729d45013…` | 1 failed, 5 passed | the same test, the same PASS |
| S0 | control: `if None is position.last_price:` | `ee3d895a7167…` | 6 passed | — (the wide run is below) |

Logs: `logs/verify/c107-sweep-<arm>-narrow.log`.

**Wide, on the fixed tree.** `pytest tests/verify` gave `8 failed, 384 passed, 2 warnings in
494.11s`, and the 8 are exactly the known
`test_pending_on_the_real_tree_names_the_subject_and_the_spec` parametrisations
(`logs/verify/c107-verify-wide.log`). `ruff check src/ tests/ scripts/`: all checks passed.
`mypy --strict src/ scripts/`: no issues in 153 files. `ruff format --check` flags the same
pre-existing lines in `verify.py` and `order_book/engine.py` as at `HEAD` (352 and 13 diff
lines, both before and after this change). It also flags the four-quote docstring, which is
folded into the spec 100 bodies. **Not yet run: control S0 against the whole of
`tests/verify`.** It survived narrow only; see the progress file.

**Control S0, wide** (`logs/verify/c107-sweep-S0-control-wide.log`). The lead asked for this
run. Result: `8 failed, 384 passed in 508.32s`, and the failing set is identical to the
baseline's known 8, so S0 survived behaviourally. The harness prints exit `0x1`, but the
verdict comes from comparing the two failing sets. `verify.py` sha256 after the restore:
`a7040cd4…6b07`, the same as before.

### FINDING, spec 100 bodies — the exit tick's equity row values the account as it was before the exit

**Agent:** C (interface and models) · **Task:** spec 100 criteria bodies · **Date:** 2026-09-17

**What happened.** The first run of the round-trip bodies on the real registered tree:
`paper_trade_round_trip_target`, `_stop` and `triggered_stop_holds_on_data_guard_block`
FAIL at the same assertion. The trade, the orders and the position reconcile exactly. The
`equity_snapshots` row of the exit tick does not. Stop leg, measured
(`logs/verify/c100c-probe-exit-equity.log`):

| cycle | tick | cash | positions_value | equity | open | realised_cum |
|---|---|---|---|---|---|---|
| 4 | watch | 1663.9201177597499 | 3333.07073057575 | 4996.9908483354999 | 1 | 0 |
| 5 | **exit** | 1663.9201177597499 | 3281.10187514294 | **4945.0219929026899** | **0** | -61.212100660081686 |
| 6 | next | 4938.787899339918314 | 0 | 4938.787899339918314 | 0 | -61.212100660081686 |

The account after the sale holds 4938.787899339918314. The exit tick records 4945.02, and the
gap is 6.234, which is the taker fee on the sale. Here the mark equals the fill, so there is
no price gap. The row is also internally inconsistent: `open_position_count` is 0 and
`positions_value` is 3281.10. On the target leg the exit tick records 5097.62 against a true
5091.10, which is **above the 5000.00 peak**, so `peak_equity` takes a figure the account never
held.

**Why.** The order of reads within one tick. Engine 1 reads the paper ledger at the top of the
tick, before engine 22 sells. Engine 21 marks every open position before engine 22 sells.
Engine 19 writes `equity = cash + positions_value` from those two payloads, but it counts
`open_position_count` from the store after it has recorded the close. So the row is the
pre-exit valuation with a post-exit count and a post-exit `realised_pnl_cum`. This is the
exit-side mirror of spec 87's finding 1, but milder: there is no double count, and the error is
the exit fee plus any gap between engine 21's mark and the walked fill. Spec 103's fix cannot
reach it, because the broker decides a market sell inside `add_order`, after engine 1 has read
the balance. On a liquidation into a thin book the mark-to-fill gap is the book's slippage, so
the overstatement, and the peak it can set, grows with it.

**Why no unit test saw it.** Engine 19's tests hand it the payloads of one tick. A's rehearsal
checks that the equity row equals `cash + positions_value` **as published**, which is true
here. Nothing compared the exit tick's row with the account after the exit. Only a criterion
that recomputes the round trip from the market does.

**Not fixed.** Engine 19 is in lane C, but it is outside this task's write list. The remedy
changes what an equity row means, so it is a decision, not a correction. The criterion keeps
its requirement (the exit tick's row equals the account after the exit) and reports FAIL.
Options are in the progress file and have gone to the lead.

### Spec 100 bodies — the operator's criterion for the exit-tick row, observed FAIL before the fix

**Agent:** C (interface and models) · **Task:** spec 100, operator ruling on Q-C1 · **Date:** 2026-09-17

**Ruling (operator, relayed by the lead).** Engine 22 publishes the post-exit figures for the
positions it closed: cash adjusted by its proceeds and fees, and positions value less engine
21's marks of those positions. Engine 19 uses them when present and does no arithmetic of its
own, and it records the cash source in a new column (migration 0005). The work is B's spec 113,
then C's spec 114. My options (a), (b) and (c) were not taken. Until both specs land, the three
failing criteria keep asserting what they assert now.

**The new criterion,** `equity_row_never_values_positions_it_does_not_hold`, is registered for
phase 6 after spec 105's. It drives a real round trip to the stop plus one tick after the exit,
and FAILs if any `equity_snapshots` row carries a non-zero `positions_value` with
`open_position_count` 0. It refuses to judge a drive that wrote no row on the fill tick, the exit
tick or the tick after, because an empty series satisfies any rule about its rows.

**Observed FAIL on the code as it stands** (`logs/verify/c100c-probe-2.log`, 40.3 s), verbatim:

> FAIL equity_row_never_values_positions_it_does_not_hold — the equity rows of a round trip: 1 of 8 equity rows value positions the account does not hold, as (cycle, ts, positions_value, open_position_count, equity): [(7, 1715983501000000, '3281.10187514294', 0, '4945.0219929026899')]. A row that counts no open position and still carries a positions value is an equity figure for an account that no longer exists, and engine 17 reads its drawdown, and peak_equity keeps it, from exactly this series; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers

The row is the exit tick's. The test that asserts it PASSes on the real tree
(`test_equity_rows_passes_on_the_real_tree`) is red until specs 113 and 114. Its FAIL proof
is today's code. Once the fix lands, a mutation arm is owed that restores the pre-exit figures
in the copy.

### Recurrence of the Phase 0 heredoc lesson: a bash heredoc wrote two NUL bytes into `verify.py`

**Agent:** C (interface and models) · **Task:** spec 100 criteria bodies · **Date:** 2026-09-17

**What happened.** I spliced the content-keyed subject cache into `scripts/verify.py` with a
Python script passed through a quoted bash heredoc. The source I meant to write contained
`b"\0"`, the two-character escape. The file on disk contained **two real NUL bytes**, and
mypy refused it: `Source code string cannot contain null bytes`. ruff did not flag it.
Earlier in the same session, another heredoc body failed with `unexpected EOF while looking
for matching '`.

**Why this is a recurrence and not a new finding.** Phase 0's build log records the same
defect: "Bash heredocs mangled Python source, twice, in two different ways", including
backslashes in a heredoc body not arriving literally. The fix recorded then was to stop
writing Python source through heredocs and to write files directly. I went back to heredocs
for convenience, and they failed again on the same kind of character. The operator asked for
it to be recorded as a recurrence of that lesson.

**Fix.** The bytes were replaced by a script written with the file tool
(`scratchpad/c100c/fixnul.py`), and the count was confirmed zero. Every later edit in this task
was a Python script written with the file tool, and each checks NUL and CRLF counts
afterwards. mypy was the only gate that caught it. A file with a NUL in it cannot be imported,
so pytest would have gone red too, but with nothing that points at the byte.

### Spec 100 bodies — how-choices taken, with the options rejected

**Agent:** C (interface and models) · **Date:** 2026-09-17

1. **The subject is A's rehearsal window (`_fill_subject_model`), not the planted market.**
   *Rejected:* the planted-market subject `_trade_subject_model`, built for spec 100 step 2.
   *Why:* the fill subject is the one on which the real chain has been measured end to end, by
   A and by spec 105. The planted subject stays for its own test. *Objection:* two trained
   subjects now exist in one file, and one of them drives nothing. REVIEW.
2. **The trained subject is cached by a digest of what training reads**
   (`research/`, `modelling/`, `core/`, `platform/`, the config, the harness's config loader),
   not by root. *Rejected:* the root key, which retrains about 30 s in every copied tree of
   every mutation arm. *Why:* an engine mutation cannot change the artefacts, and a mutation of
   anything training reads changes the digest. A tree with none of those files falls back to
   its root.
3. **"No market order" and "no second entry" are observed at the broker, through a
   transparent `RecordingBroker`.** *Rejected:* reading the broker's private `_pending` and
   `_executed`, and the store alone. The store cannot see a replacement nobody recorded.
   *Objection, stated in the class's docstring:* an order an engine built and never handed
   over is invisible, and seeing it would mean replacing the contract class. REVIEW.
4. **The timeout leg is watched minute by minute for the first bar, then once a bar, and
   exits on the `timeout_at` tick.** *Rejected:* every minute of the horizon. That was measured
   at 436 s, and the criterion runs three times per gate. *Objection:* a defect that only shows
   on a non-bar minute tick mid-horizon is not watched. The first bar and every bar-close tick
   are. REVIEW.
5. **The escalation's balance failure is realised by failing `AssetPairs` as well as
   `Balance`** (operator D8). **Is a balance-only failure achievable in paper mode?** Not in a
   way that leaves a liquidation completable. `PaperBroker.balance()` never calls the real
   `Balance`, so failing it alone changes nothing. The ledger fails in exactly two ways:
   (i) `AssetPairs` fails, and it cannot tell which currency a fill spent; (ii) a fill is due
   and `TradeVolume` fails, so the fill cannot be priced. (ii) was not used. In the positions leg
   the only fill due during the outage is the liquidation's own market sell, which is priced
   inside `add_order` and would fail with the same missing fee tier. Engine 22 then records the
   position unclosed and retries, by design (no fee is invented), so the liquidation could not
   complete and the criterion would be asserting the impossible. In the entry leg, a due fill
   means the entry filled rather than being cancelled. The message names both failed fetches,
   engine 1's reason for the balance, and the retained-`AssetPairs` fallback on the trade.
6. **The escalation criterion has two drives**, positions through engine 17 and a resting
   entry through an operator `close_all` 60 s into its 300 s window (operator ruling via the
   lead). *Rejected:* asserting `entry_orders_cancelled` on the escalation tick, which is
   trivially true at the committed config. The message computes and states why.
7. **The two criteria that trade nothing now name tier 3.** Their drive runs at tier 3, and
   engine 14 can be reached at no other. *Rejected:* keeping
   `test_the_two_criteria_that_drive_no_trade_claim_no_fee_regime`, which was right while they
   applied no tier. They now say the thing they judge reads no fee. *Objection:* engine 9 could
   be reached at tier 1, and the old sentence was the operator-visible line. REVIEW.
8. **Engine 9 is judged on the fixture's opening snapshot of each pair**, loaded into the fake
   exchange, with the thin pair made the candidate by streaming ADA/USD first. ADA/USD's rules
   are the same invented fake-exchange values `test_order_book.py` uses. *Rejected:* relabelling
   the ADA book as BTC/USD, which would put a recorded book under a pair it was not recorded
   for.
9. **The console criterion PENDINGs on a concrete absence**, `PositionView` having no
   `hold_reason` (spec 101 step 3), and keeps PENDING until spec 101 writes the drive.
   *Rejected:* writing the drive now behind the PENDING, which would be a body that never
   executes.
10. **`test_the_tier_sentence_is_pending_…` was made real**, not renamed. It now removes
    `tests/harness` from a copied tree and observes PENDING naming the harness, for all seven
    trade-driving criteria.
11. **Real-tree verdicts are computed once per module** (`real_tree_outcomes`), and every
    real-tree assertion reads from them.

### Spec 100 bodies — fourteen engine mutations, each killed by the criterion it names

**Agent:** C (interface and models) · **Task:** spec 100 · **Date:** 2026-09-17

These are the committed arms: `MUTATIONS` in `tests/verify/test_phase6_criteria.py`, driven by
`test_each_criterion_fails_against_its_named_wrong_implementation`. Each is applied in a copied
tree, and the real file is hashed on both sides. Each anchor occurs once in its file and
nowhere in `tests/`, and every engine file touched is 0 CRLF. A scratch runner captured the
verbatim verdicts (`scratchpad/c100c/arm_messages.py`, `logs/verify/c100c-arm-messages.log`).
Each verdict carries the arm's fragment, and every real file's sha256 was unchanged. The
narrow file run was `5 failed, 80 passed`, and all five are the known reds (below); the
fourteenth arm ran on its own: `1 passed`.

In the table, the killing test is the arm's own parametrisation of
`test_each_criterion_fails_against_its_named_wrong_implementation`.

| Arm | Break (copied tree) | Criterion, verdict (abridged) |
|---|---|---|
| `target_never_triggers` | engine 21's target branch is `elif False:` | target: "engine 21 triggered [] on the exit tick, not [{… 'barrier': 'target'}]" |
| `held_with_no_block` | engine 21 `_held` returns True | stop: "on flat trading at 1715983321 engine 21 triggered [] and held for 'data_guard_blocked'" |
| `timeout_compared_strictly` | `now >= timeout_at` becomes `>` | timeout: "engine 21 triggered [] on the exit tick, not [{… 'barrier': 'timeout'}]" |
| `realised_without_exit_fee` | engine 22's realised PnL omits the exit fee | stop: "the trade … is (… Decimal('-54.9780070973101') …); recomputed it is (… Decimal('-61.212100660081686') …)" |
| `cancelled_entry_replaced` | engine 21 re-places the cancelled entry at its limit, userref + 1 | unfilled: "the broker was asked for [('buy','limit',True,1690626088), ('buy','limit',True,1690626089)]; … any second order is a chase (invariant 8)" |
| `hold_removed_from_21` | engine 21 `_held` returns False | held stop: "engine 21 triggered [{… 'stop'}] and published hold_reason None on a tick data_guard blocked" |
| `liquidation_held_by_22` | engine 22 `_close_intent` returns False | held stop: "with close_intent set the held position was not sold: 'data_guard_blocked'" |
| `liquidation_needs_fresh_pair_rules` | engine 22 refuses retained pair rules in every case | escalation: "the liquidation did not complete during the outage: engine 21 held None, engine 22 said 'exit_incomplete'" |
| `safety_escalates_a_tick_early` | engine 17 `>` becomes `>=` | escalation: "engine 17 escalated after 15 blocked ticks; the limit is 15 and it escalates on the tick after it, not before" |
| `cancel_on_window_only` | engine 21 `if close_intent or expired:` becomes `if expired:` | escalation: "with close_intent set 60s into a 300s window engine 21 published [], not the entry cancelled at 1715983261000000" |
| `walks_the_ask_side` | engine 9 walks `book.asks` | order book: "engine 9's thin walk of ADA/USD disagrees …: fill_price 0.19479… vs 0.19464…, levels_consumed (7, 10), estimated_slippage_pct (-0.0000198…, 0.000136…)" |
| `walk_off_by_a_level` | the walk skips the top bid | order book: "… levels_consumed (9, 10) …" |
| `skill_not_clipped` | engine 14's skill is not clipped at zero | router: "engine 14 published … cccc: -0.833… ; recomputed … cccc: 0.0" |
| `older_duplicate_kept` | engine 14 keeps the first row of a duplicated (version, fold) | router: "… aaaa: 0.333…, bbbb: 0.666… ; recomputed … aaaa: 0.818…, bbbb: 0.181…" |

**What the arms cannot show while Q-C1 is open.** The target, stop and held-stop arms kill
before reconciliation reaches the equity row, so they stay valid while those criteria are red
on the real tree for the exit-tick reason. `realised_without_exit_fee` kills at the trade row,
which is compared before the equity row.

### Spec 100 bodies — mutations of the criteria themselves, round 1: eleven killed, four survived

**Agent:** C (interface and models) · **Task:** spec 100 · **Date:** 2026-09-17

Harness: `scratchpad/c100c/sweep100.py`. It takes a byte copy of `scripts/verify.py` (0 CRLF,
every anchor exactly once there and absent from `tests/`), restores it in a `finally` before the
next arm, and compares the sha256 in the same statement. It runs with
`PYTHONDONTWRITEBYTECODE=1` and `sys.executable -X faulthandler`. Target:
`tests/verify/test_phase6_criteria.py` and `tests/verify/test_runner.py`, whose baseline is
`5 failed, 81 passed`, the five known reds (four real-tree verdicts waiting on specs 113 and 114,
and the new equity-rows criterion's PASS test). **A verdict is the failing set compared with
the baseline's**, never the exit code, which is 1 in every arm. File sha256 before and after:
`d0309c1d…05de`. Summary: `logs/verify/c100c-sweep-summary.log`; each arm has its own log.

| Arm | Weakening | Verdict | Killed by (added to the failing set) |
|---|---|---|---|
| V1 | `_entry` stops checking that every registered gate ran | **survived** | — |
| V2 | the unfilled window compared strictly | killed | real-tree `unfilled`, arm `cancelled_entry_replaced` |
| V3 | the broker-requests check in `unfilled` removed | killed | arm `cancelled_entry_replaced` |
| V4 | the held-tick trigger/hold check removed | killed | arm `hold_removed_from_21` |
| V5 | the early-escalation check removed | killed | arm `safety_escalates_a_tick_early` |
| V6 | the retained-AssetPairs fallback no longer required on the trade | killed | real-tree `escalation`, arm `cancel_on_window_only` |
| V7 | the operator-cancel row check removed | killed | arm `cancel_on_window_only` |
| V8 | engine 9's payload compared by `levels_consumed` only | **survived** | — |
| V9 | engine 14's weights not compared | killed | arms `older_duplicate_kept`, `skill_not_clipped` |
| V10 | the trade row not compared | killed | arm `realised_without_exit_fee` |
| V11 | the equity-rows rule made inert | killed | the equity-rows real-tree test **left** the failing set (it PASSed) |
| V12 | the subject cache key replaced by a constant | **survived** | — |
| V13 | the watch stops checking the stored mark | **survived** | — |
| V14 | the expected exit request is a limit, not a market sell | killed | real-tree `escalation`, arm `cancel_on_window_only` |
| C0 | control: `taken = min(volume, remaining)` in `_sold_at` | survived, as required | — |

**Why each survived, and what was done** (the operator required V8 and V12 killed before
commit):

- **V8.** Both engine-9 arms (ask side, skipped top level) also change the level count, so a
  criterion comparing only the count still failed on them. Nothing tested a walk over the right
  levels at the wrong price. **Added:** arms `slippage_against_the_fill` (the slippage divides
  by the fill, not the best bid) and `partial_level_priced_at_the_top` (the partly taken level
  priced at the top bid). Both keep the level count and change the price, and both are asserted
  on the price fields of the FAIL.
- **V12.** Every test checked what a criterion *said*. A criterion driving the wrong trained
  subject says the same things. **Added:**
  `test_a_tree_whose_training_differs_is_judged_on_its_own_subject`. With the real subject
  already cached, it runs a criterion on a copied tree whose labeller calls every touch `stop`,
  and requires the FAIL only that tree's own subject can produce ("fitted no skeptic.txt").
  **Other criteria of this shape:** the only other module-level cache in `verify.py` is
  `_TRADE_SUBJECTS`, keyed by root and read by no criterion (only by its own two tests). No
  criterion of phases 0 to 5 caches anything.
- **V13.** No engine arm broke the mark. **Added:** arm `marked_at_the_ask`.
- **V1.** Judged against the registered chain, a gate that was never registered is invisible,
  and a registered gate that did not run while engine 18 still placed an order cannot happen,
  because the orchestrator writes every engine's payload into `state` before the next one runs.
  **Added:** `_entry` now compares the registered gates with the Gate column of
  `context/engine-contracts.md` (through `parse_engine_registry`), and arm `gate_unregistered`
  drops engine 15 from a copied `bootstrap.py`. V1b, which disables that comparison, is in round 2.

### Third instance in one session of the heredoc lesson

**Agent:** C (interface and models) · **Date:** 2026-09-17

**What happened.** After the NUL-byte entry above, I added one arm to the scratch sweep harness
through a Python heredoc. `b"\n"` arrived in the file as a real line break, the harness died
with `SyntaxError: unterminated string literal`, and no arm ran. `verify.py`'s hash was the same
before and after, `c73034fe…`. The fix was written with the file tool.

**Why it is recorded.** It is the same mechanism as the NUL bytes, and it happened within an
hour of writing that entry. The rule I wrote there ("every later edit in this task was a Python
script written with the file tool") was already broken by my next edit. A rule that relies on
remembering it is not a rule. From here, every script that carries an escape sequence is
written with the file tool, with no exceptions for small edits.

### Spec 100 bodies — criterion mutations, rounds 2 and 3: every non-control arm killed

**Agent:** C (interface and models) · **Task:** spec 100 · **Date:** 2026-09-17

Same harness and target as round 1. The baseline is still the five known reds. File sha256
before and after both rounds: `c73034fe…9eab6f`. Summaries:
`logs/verify/c100c-sweep-round2-summary.log` and `…-round3-summary.log`.

| Arm | Round 1 | Round 2 | Round 3 | Killing test |
|---|---|---|---|---|
| V8, engine 9 compared by level count only | survived | **killed** | — | arms `slippage_against_the_fill`, `partial_level_priced_at_the_top` |
| V12, subject cache key made constant | survived | **killed** | — | `test_a_tree_whose_training_differs_is_judged_on_its_own_subject` |
| V13, the watch's mark check removed | survived | **killed** | — | arm `marked_at_the_ask` |
| V1b, the registry-table gate comparison disabled | — | **killed** | — | arm `gate_unregistered` |
| V1, the unrun-gate check disabled | survived | survived | **killed** | arm `orchestrator_skips_the_gates` |
| C0, control | survived | survived | — | — (as required) |

**V1 was a real hole, not an equivalent mutant.** With the committed orchestrator it could not be
observed: `_run_opportunity_chain` writes every engine's payload into `state` and stops at the
first block or PASS, so a registered gate cannot have not run while engine 18 did. The check
exists to catch an orchestrator that skips a gate, though, and nothing tested that. Arm
`orchestrator_skips_the_gates` makes a copied `core/orchestrator.py` (the lead's file; the real
one is hashed on both sides) run the opportunity chain without its gates. Only the unrun check
objects, with "did not run every registered gate". I considered calling V1 equivalent and
rejected it: an equivalent mutant is one no change to any file could expose, and a one-line
change to the orchestrator exposes this one.

**The new arms' verbatim verdicts** are in `logs/verify/c100c-arm-messages-2.log`.

### Spec 100 bodies — the final runs, and where this stops

**Agent:** C (interface and models) · **Task:** spec 100 · **Date:** 2026-09-17

**`pytest tests/verify`, whole directory** (`logs/verify/c100c-verify-wide-final.log`):
`5 failed, 417 passed, 2 warnings in 760.36s`. The five are exactly the known reds:
`test_the_real_tree_verdict_and_what_it_says` for the target, stop and timeout round trips and for
the held stop, and `test_equity_rows_passes_on_the_real_tree`. All five wait on specs 113 and 114.

**The timeout round trip fails for the same reason as target and stop.** Its verdict
(`logs/verify/c100c-final-messages.log`) is on the exit tick's equity row. The row holds the
pre-exit cash 1663.9201177597499 and the pre-exit positions value 3333.07073057575 with 0 open
positions, and the recomputed account is 4990.658013947405975. The trigger, the trade, the
orders and the position all reconcile before that point. Every criterion's final verbatim
verdict is in that log. The PENDING lines at the bottom were produced outside pytest, where the
repository root is not on `sys.path`, so the seven that drive a trade name the missing harness
first. Inside pytest the harness resolves from the repository and the first missing engine is
named instead (`engine 9 \`order_book\` does not exist yet (C, spec 96)`), which is what
`test_pending_on_a_tree_with_nothing_built` asserts.

**The three heredoc slips, counted.** (1) A bash heredoc appending draft code to a scratch file
failed with `unexpected EOF while looking for matching '`; nothing was written. (2) A Python
heredoc wrote two NUL bytes into `scripts/verify.py`, and mypy caught it. (3) A Python heredoc
turned `\n` into a real line break in the scratch sweep harness, which then failed to compile, so
no arm ran and `verify.py` was untouched. (2) and (3) are the ones recorded above. All three are
the Phase 0 lesson.

**Stopped here, on the lead's instruction.** B takes the tree for spec 113. Nothing of mine is
running, and no mutant is on disk: `verify.py` sha256 is `c73034fe…9eab6f`, and every engine
file the arms touched was hashed unchanged. Not committed.

### Spec 114 — engine 19 refused spec 113's two payload keys, and lost the tick when it did

**Agent:** C (interface and models) · **Task:** spec 114 · **Date:** 2026-09-17

**What happened.** With B's spec 113 on disk the tree is red on 26 tests: 5 in A's
`tests/engines/test_trade_chain_rehearsal.py`, 20 in `tests/verify/test_phase6_criteria.py` and
1 in B's `tests/engines/test_position_manager.py`. Every one of them is the same failure inside
engine 19, at `src/acsoe/engines/memory/engine.py:387`:

> `pydantic_core._pydantic_core.ValidationError: 1 validation error for PositionRow` ·
> `Extra inputs are not permitted [type=extra_forbidden, input_value='990.00', input_type=str]`

**Why.** `_Row` in `clients/store/contracts.py` is `extra="forbid"`, and engine 19 validates the
publisher's payload *as* the stored row: `PositionRow.model_validate(stamped)` and
`TradeRow.model_validate(stamped)` are handed the whole published mapping. Spec 113 added
`value` to every marked position row and `net_proceeds` to every closed trade row — facts about
the tick, not columns — so the first marked position of a run raises. The raise is converted by
contract rule 7 into an `ERROR` result for engine 19, which means the whole tick is recorded
nowhere: no positions, no orders, no trades, no block record and no equity row. It is the same
shape as the loss invariant 12's 2026-09-16 ruling was written about, arriving from the other
direction — there the tick was lost because an engine's payload was *empty*, here because it
carries one field more than the store has a column for.

B flagged the risk in spec 113 step 2 and left it, correctly: engine 19 is lane C.

**Fix (this spec).** Engine 19 strips the two payload-only fields off its copy of the row before
validating the stored row, and uses them for the equity row. No column is added for either and
`extra="forbid"` is not weakened for anything else, so the next unknown key on a stored row still
raises. The names live in `engines/memory/contracts.py` beside the engine that owns each, as
contract rule 3 requires, restated rather than imported.

### Decision: three ways the exit-cycle row can be a plausible lie, and each one skips the row

**Agent:** C (interface and models) · **Task:** spec 114 · **Date:** 2026-09-17

**Options.** The operator ruled the arithmetic — filter engine 21's rows by the position
ids engine 22 closed, add engine 22's net proceeds to engine 1's cash — and named one
refusal: a *remaining* position with no `value` writes no row. Two more cases are reachable
and the ruling does not name them, and each could be read either way.

**Chose.** Both skip the row, with the reason recorded, exactly as the named case does.

- **A closed trade with no `net_proceeds`.** `decimal_field` returns `Decimal(0)` for an
  absent field, so the row would read as an account that sold a position and was paid
  nothing for it: a realised loss of the whole notional, in the series engine 17 reads its
  drawdown from. That is the same absent-is-not-zero rule this engine is arranged around.
- **Engine 21's remaining rows not covering what the account still holds.** The count comes
  from the store after this tick's rows land, so it is what survived the sale. Fewer rows
  than that and the sum is over a subset of the account — the same hole as the named case,
  arriving through a position engine 21 never published a row for at all, where the
  field-by-field check cannot see it because there is no row to find a missing field on.

**Because.** Both can only make engine 19 write fewer rows, never a wrong one, and a gap in
the curve names itself in `equity_skipped_reason` while a wrong row does not. The operator's
own reasoning for the named case — a partial sum is a drawdown that did not happen — applies
unchanged to both.

**Cost.** Engine 19 now has three ways to decline the exit tick's row where it had one, and
each needs its own test or it is an unreachable branch. There are three. Reported to the
lead as how-choices rather than decided silently, because they are refusals the ruling did
not name.

### Decision: `value` and `net_proceeds` are stripped per row, not tolerated model-wide

**Agent:** C (interface and models) · **Task:** spec 114 · **Date:** 2026-09-17

**Options.** Engine 19 hands the publisher's whole mapping to `PositionRow.model_validate`
and `TradeRow.model_validate`, and `_Row` is `extra="forbid"`. Three ways out: relax
`extra` to `ignore` on those two models (B's file); add columns for the two figures
(a migration, and B's file again); or take the two named fields off engine 19's own copy
of the row before validating.

**Chose.** The third, which is also what the spec approved.

**Because.** `extra="ignore"` would silently drop *every* unknown key, so the next field a
publisher renames or misspells reaches the store as a null instead of raising — and this
engine's whole failure mode is defects that leave the suite green. A column for either
figure would be a second copy of a number the store already keeps: `net_proceeds` is
recomputable from the trade's `qty`, `exit_price` and `exit_fee`, and `value` from the
position's `qty` and `last_price`, so the column could only ever disagree with them.

**Cost.** Two names engine 19 must keep in step with engines 21 and 22, restated in
`engines/memory/contracts.py` under contract rule 3 rather than imported. A rename upstream
does not raise — engine 19 would simply stop reading the field — which is the standing
hazard of every key in that file, and the reason they all live in one place with the owning
engine written beside each.

### Spec 114 — the exit-cycle row landed, and the five criteria it was written for turned PASS

**Agent:** C (interface and models) · **Task:** spec 114 · **Date:** 2026-09-17

**The four criteria that had been FAILing since the spec 100 bodies, and the one written to
observe the defect, all PASS on the real tree** (`logs/verify/c114-criterion-messages.log`,
verbatim, tier sentence trimmed where it repeats):

> PASS `paper_trade_round_trip_target` — BTC/USD entry 1690626088: a post-only buy of
> 26.26015939 at 126.9, placed on the bar close past all 8 registered gates (data_guard,
> safety, scout, anomaly, cost, risk, skeptic, decision), filled at its limit on the next
> tick, watched for 3 ticks, then a trade at 130.757 crossed the target 130.707 the minute
> before 1715983501; it exited at the target when engine 22 sold 26.26015939 as a taker at
> 130.757. Entry fee 3.6656556492501, exit fee 6.524029356580637 and realised
> 91.095749761399263 were recomputed from the pinned book and engine 1's fee tier, and the
> orders, positions, trades and equity rows engine 19 wrote match them exactly; at fee tier
> 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade
> regime at the current barriers

> PASS `paper_trade_round_trip_stop` — … a trade at 124.9465 crossed the stop 124.9965 the
> minute before 1715983501; it exited at the stop when engine 22 sold 26.26015939 as a taker
> at 124.946. Entry fee 3.6656556492501, exit fee 6.234093562771586 and realised
> -61.212100660081686 were recomputed from the pinned book and engine 1's fee tier, and the
> orders, positions, trades and equity rows engine 19 wrote match them exactly; …

> PASS `paper_trade_round_trip_timeout` — … watched for 61 ticks, then the clock reached its
> timeout at 1716026461 with neither barrier traded; it exited at the timeout when engine 22
> sold 26.26015939 as a taker at 126.925. Entry fee 3.6656556492501, exit fee
> 6.332834388093925 and realised -9.341986052594025 were recomputed … and the orders,
> positions, trades and equity rows engine 19 wrote match them exactly; …

> PASS `triggered_stop_holds_on_data_guard_block` — BTC/USD position pos-1690626088: a trade
> at 124.9465 touched the stop 124.9965 on a tick engine 4 blocked for a crossed quote, and
> engines 21 and 22 placed no exit - no trigger, no order at the broker - with hold_reason
> 'data_guard_blocked' published and stored on the position. The operator's close_all on the
> next tick, with data_guard still blocking, sold the same position as a taker at 124.296
> (outcome liquidation, realised -78.248772966735036, every row reconciled), cleared the
> hold, and the orchestrator cleared close_intent and consumed the command; …

> PASS `equity_row_never_values_positions_it_does_not_hold` — all 8 equity rows of a round
> trip (4 with a position open, including the fill tick, the exit tick and the tick after
> it) carry a positions_value of zero whenever they count no open position; at fee tier 3,
> reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade
> regime at the current barriers

**The stop leg is the one to compare against the finding.** It read equity 4945.02 with 0
open positions and a positions value of 3281.10 against a true 4938.79. It now reconciles to
the digit against the account recomputed from the scripted market, with no tolerance.

**`tests/verify/test_phase6_criteria.py` and `tests/verify/test_runner.py`: `93 passed in
438.76s`** (`logs/verify/c114-phase6-criteria-1.log`) — the 20 reds green, including all four
`test_the_real_tree_verdict_and_what_it_says` arms and `test_equity_rows_passes_on_the_real_tree`.

**The FAIL arm is committed as a mutation.** `pre_exit_figures_restored` in `MUTATIONS` forces
engine 19's ordinary branch in the copied tree (`if sold or closed:` → `if False:`), which is
exactly the pre-exit row: engine 1's start-of-tick cash, engine 21's total from before the
sale, the store's count from after it. The criterion FAILs on it naming "value positions the
account does not hold". Killing test:
`test_each_criterion_fails_against_its_named_wrong_implementation[pre_exit_figures_restored]`.
The criterion's own FAIL text against the *unfixed* engine is in the earlier entry of this log.

**Mutation sweep over the exit-cycle branch** (`logs/verify/c114-sweep-narrow.log`). Every arm
from a byte copy, restored in a `finally` with sha256 compared in the same statement; anchors
asserted to occur exactly once; `PYTHONDONTWRITEBYTECODE=1`; `sys.executable`; every verdict
carries a pytest summary line. Baseline `58 passed in 2.72s`. Engine 19 hash
`6d0c226f921f…` before and after every arm.

| Arm | What it breaks | Verdict | Killed by |
|---|---|---|---|
| M1 closed position not dropped | the sold position's mark stays in the sum | KILLED, 4 failed / 54 passed | `test_the_exit_ticks_row_is_the_account_after_the_sale` (+3) |
| M2 unmarked remaining worth zero | a remaining position with no `value` is summed as nothing | KILLED, 1 failed / 57 passed | `test_a_remaining_position_with_no_value_writes_no_equity_row` |
| M3 net proceeds not added | the exit tick's cash stays at engine 1's balance | KILLED, 2 failed / 56 passed | `test_the_exit_ticks_row_is_the_account_after_the_sale` (+1) |
| M4 wrong `cash_source` | the post-exit row is labelled start-of-tick cash | KILLED, 2 failed / 56 passed | `test_the_exit_ticks_row_is_the_account_after_the_sale` (+1) |
| M5 exit branch on every tick | the filtering branch is taken where engine 22 sold nothing | KILLED, 5 failed / 53 passed | `test_an_ordinary_tick_still_reads_engine_21s_totals_and_says_cycle_start` (+4) |
| C0 control (equivalent) | two independent accumulators initialised in the other order | SURVIVED, 58 passed | — |

**The sweep excludes `tests/engines/test_trade_chain_rehearsal.py`, and the exclusion is the
point.** That file is red in A's lane (spec 116) for a reason engine 19 cannot fix. Leaving a
red file in marks every arm killed regardless, which manufactures a clean sweep out of someone
else's broken tree.

**The control's line text was grepped in `tests/` and `scripts/` first**: neither
`positions_value = Decimal(0)` nor `unrealised = Decimal(0)` appears in either tree, so no
assertion is written against the text of the line the control moves.

### Spec 114 — M1's kill came from the neighbouring guard, so the assertion it was written for was untested

**Agent:** C (interface and models) · **Task:** spec 114 · **Date:** 2026-09-17

**What happened.** M1 — the sold position left in engine 21's sum — reported KILLED by four
tests, `test_the_exit_ticks_row_is_the_account_after_the_sale` among them. Asking *how* it
was killed (`code-standards.md`: "when a sweep says killed, ask which test killed it")
showed the kill was not the assertion the arm was written for. With the sold position still
in `remaining`, the **count guard** fires first — two rows against one open position — so no
equity row is written at all and the test dies on `(row,) = rows_in(...)` with a
`ValueError`, three lines before the `positions_value` assertion. That assertion had never
been observed failing, and in this fixture the count guard subsumes M1 completely: no
variant of "do not drop the closed position" can reach the sum.

**Why it matters.** `assert Decimal(row["positions_value"]) == KEPT_VALUE` is the line that
states the operator's ruling about the positions value. On the sweep as first run it was a
claim, not a check — the same shape as V8 and V12 in the spec 100 criterion sweep, arriving
in the one place where a clean kill made it invisible.

**Fix.** Arm **M1b**, which isolates the sum: `remaining` is still computed and still
compared with the store's count, and only the summation iterates over every published row
(`for row in remaining:` → `for row in self._rows(marked, POSITIONS_FIELD):`). KILLED,
`2 failed, 56 passed in 3.26s` (`logs/verify/c114-sweep-m1b.log`), and the killing line is
the intended one, verbatim:

> `AssertionError: the sold position's mark is still in the positions value, so the row
> values a position the account no longer holds` · `assert Decimal('707.00') ==
> Decimal('336.00')`

Engine 19 hash `6d0c226f921f…` before and after. M1 stays in the table as a checked kill by
the count guard; M1b is what proves the sum.

**The control, asked the whole suite.** A mutation that survives a subset has not survived.
C0 was re-run against `tests/` less A's rehearsal: **`3271 passed, 2 skipped, 3 warnings in
1887.83s`** (`logs/verify/c114-sweep-wide.log`), so it is an equivalent mutant rather than a
hole — and, since the control changes nothing observable, that run is also the statement
that the whole tree less spec 116's file is green.

### FINDING for the lead: removing `EquitySnapshotRow.cash_source`'s default is a 202-test, 8-file change

**Agent:** C (interface and models) · **Task:** spec 114, step 5 · **Date:** 2026-09-17

**The question.** B recommends, and the lead endorses, removing the model default now that
engine 19 writes `cash_source` on every row, so that a writer who forgets it fails loudly.
`clients/store/contracts.py` is B's file; C was asked to check what it would break, not to
make the change. Checked by byte copy —
`    cash_source: CashSource = CashSource.CYCLE_START` → `    cash_source: CashSource` —
restored with sha256 compared in the same statement (`f56374631d68` before and after,
`logs/verify/c114-cash-source-default.log`).

**The precondition holds.** Nothing in `src/` or `scripts/` relies on the default: engine 19
passes the field on both branches, and `seed.py` already sets it explicitly with a comment
saying why. `mypy --strict src/ scripts/` is clean without the default — pydantic's
requiredness is a runtime matter, so the type checker says nothing either way.

**What breaks is the fixtures.** `37 failed, 2644 passed, 2 skipped, 167 errors in 998.28s`
over `tests/` less `tests/verify` and less A's rehearsal: **202 tests across 7 files**, plus
`tests/engines/test_trade_chain_rehearsal.py`, which builds two such rows and is excluded
only because spec 116 has it red already — **8 files**, in all three lanes:

| File | Lane | Why |
|---|---|---|
| `tests/clients/store/test_store.py` | B | 12 tests; **one of them, `test_a_row_built_without_a_cash_source_says_cycle_start`, asserts the default exists** and has to be replaced rather than fixed |
| `tests/engines/test_risk.py` | B | a seeded equity row in a fixture; the file errors out |
| `tests/engines/test_scout.py` | B | same |
| `tests/engines/test_safety.py` | B | same |
| `tests/engines/test_decision.py` | B | same |
| `tests/engines/test_execution.py` | B | same |
| `tests/engines/test_feature_chain_rehearsal.py` | C | same |
| `tests/engines/test_trade_chain_rehearsal.py` | A | two constructions; already red on spec 116 |

Most of the 202 are one fixture per file taking the whole file down with it, so the edit is
small and repeated — one keyword argument in eight places — but it lands in three lanes at
once, which makes it a lead task under ownership rule 6 rather than a teammate's.

**C's view, offered not taken.** Worth doing, and cheaper now than later: every one of those
fixtures currently asserts nothing about `cash_source` while silently receiving
`cycle_start`, which is exactly the "a model's own default supplied the value the test was
asserting" trap this phase already recorded once. The one thing to decide rather than
mechanise is B's `test_a_row_built_without_a_cash_source_says_cycle_start`: it is a test of
the default, so removing the default retires it, and what should replace it is the assertion
that a row built without one is **refused** — otherwise the change removes a check instead of
tightening one.

### Spec 114 — everything that was only in a scratchpad or only in a message, written down

**Agent:** C (interface and models) · **Task:** spec 114 · **Date:** 2026-09-17

Written on the operator's instruction, relayed by the lead: a scratchpad does not survive a
session and neither does a message. Nothing below is new work — it is the reproducible part
of work already reported, recorded so a fresh session does not have to redo it.

#### A. What engine 19's change actually is, file by file

- `src/acsoe/engines/memory/contracts.py` — `POSITION_VALUE_FIELD = "value"` and
  `NET_PROCEEDS_FIELD = "net_proceeds"` added under a heading explaining that both are
  payload facts and neither is a column, plus `POSITION_ID_FIELD` and
  `POSITION_STATUS_FIELD` for matching engine 21's marks against engine 22's closes. All
  four restated rather than imported (contract rule 3) and added to `__all__`.
- `src/acsoe/engines/memory/engine.py` —
  - two `NamedTuple`s at module level: `ClosedTrade(row, net_proceeds)` and
    `Account(cash, positions_value, unrealised_pnl)`;
  - `_write_positions` pops `POSITION_VALUE_FIELD` off `stamped` (the copy `_stamped`
    already made) before `PositionRow.model_validate`;
  - `_write_trades` reads `net_proceeds` through `decimal_field` off the published row,
    pops it off `stamped`, and returns `list[ClosedTrade]` instead of `list[TradeRow]`;
  - `_write_equity` gains an `exiting` parameter and splits on `if sold or closed:` into the
    filtering branch (`_after_exit`, `CashSource.AFTER_EXIT`) and today's totals branch
    (`CashSource.CYCLE_START`); `cash_source` is passed to `EquitySnapshotRow` on both;
  - `_closed_position_ids(exiting)` returns the closed `position_id`s and raises on a closed
    row that names none;
  - `_after_exit(...)` filters, sums, and returns `(Account | None, skip reason | None)`.
- `src/acsoe/engines/memory/README.md` — a new section, "The exit-cycle equity row", and
  three rows added to the inputs table.
- `tests/engines/test_memory_rows.py` — `a_position` gained a `pair` parameter (the database
  refuses two open positions on one pair, `ux_positions_open_pair`); `a_closed_trade` now
  carries `net_proceeds` as engine 22 does; helpers `a_marked_position`, `an_exit_tick`,
  `a_sale`; eight new tests in a "Spec 114" section.
- `tests/verify/test_phase6_criteria.py` — one `MUTATIONS` entry, `pre_exit_figures_restored`.

Nothing else was touched. `scripts/verify.py` needed no change.

#### B. The A-rehearsal blocker, and the probe that measured it

Now spec 116 (A). Recorded here because C found and measured it, and because
`probe_rehearsal.py` lived only in a scratchpad.

**Two sites, both in `tests/engines/test_trade_chain_rehearsal.py`, neither fixable from
engine 19.** `check_recorded` (around line 313) builds its *expectation* by re-validating
engine 21's and engine 22's published rows through the store's own models, so it meets
`extra="forbid"` on its own account:

1. `positions[str(row["position_id"])] = PositionRow.model_validate({**row, **stamp, "hold_reason": hold})`
   — raises on spec 113's `value`;
2. `trades = {str(row["trade_id"]): TradeRow.model_validate({**row, **stamp}) ...}`
   — raises on spec 113's `net_proceeds`;

and a third site, the equity block at the end of the same function, asserts the **pre-exit**
reading directly: `row.cash == Decimal(state["exchange"]["balances"]["USD"])`,
`row.positions_value == Decimal(manager["positions_value"])` and
`row.unrealised_pnl == Decimal(manager["unrealised_pnl"])` — which is exactly what the
operator's ruling changes on an exit tick.

**The probe.** Byte copy of the file, three anchors replaced, `pytest
tests/engines/test_trade_chain_rehearsal.py -q -p no:randomly`, bytes written back and
sha256 compared in the same statement. Result **`7 passed in 65.72s`**; file restored,
sha256 `79cc6747dfe3` before and after; nothing left on disk. The third anchor's replacement
computed, on a tick where `state["exit"]["positions"]` carries a closed row or
`closed_trades` is non-empty, `cash` as the balance plus the published `net_proceeds`, and
`value` / `unrealised` as the sums over engine 21's rows whose `position_id` is not in the
closed set; otherwise the totals as today.

**The patch is deliberately not reproduced here.** Spec 116 step 4 requires A to derive the
expectation from `context/engine-contracts.md`'s "The exit-cycle equity row" rather than copy
either engine 19's implementation or C's probe, because the rehearsal's value is that it is a
*second* derivation of the same rule. What is worth keeping is the measurement: three sites,
and `7 passed in 65.72s` is the outcome to expect.

#### C. The mutation arms, so the sweep can be re-run

Against `src/acsoe/engines/memory/engine.py`. Each anchor occurs exactly once and the harness
asserts so before applying. Narrow set: `tests/engines/test_memory_rows.py` and
`tests/engines/test_memory.py` (baseline `58 passed`), deliberately excluding
`tests/engines/test_trade_chain_rehearsal.py`.

| Arm | Anchor | Replacement |
|---|---|---|
| M1 | `            if str(row.get(POSITION_ID_FIELD)) not in sold` | `            if True` |
| M1b | `        for row in remaining:` | `        for row in self._rows(marked, POSITIONS_FIELD):` |
| M2 | `                if row.get(field) is None:` | `                if False:` |
| M3 | `            proceeds += trade.net_proceeds` | `            proceeds += Decimal(0)` |
| M4 | `            cash_source = CashSource.AFTER_EXIT` | `            cash_source = CashSource.CYCLE_START` |
| M5 | `        if sold or closed:` | `        if True:` |
| C0 control | `        positions_value = Decimal(0)` then `        unrealised = Decimal(0)` | the two lines swapped |

The committed FAIL arm `pre_exit_figures_restored` uses the M5 anchor with `        if False:`
instead, which is the opposite branch and is the pre-exit row.

The `cash_source` probe's anchor, against `src/acsoe/clients/store/contracts.py` (B's file,
restored by hash `f56374631d68`): `    cash_source: CashSource = CashSource.CYCLE_START`
replaced by `    cash_source: CashSource`.

#### D. How the verbatim criterion verdicts were obtained

Not through pytest, which does not print them. Load `scripts/verify.py` by path with
`importlib.util.spec_from_file_location`, with the repository root on `sys.path`, then
`{c.name: c for c in verify.criteria_for(6, live=False)[0]}` and
`verify.run_criterion(criterion, verify.VerifyContext(root=ROOT))`. The `Outcome` carries
`.result` and `.message`. Output at `logs/verify/c114-criterion-messages.log`.

#### E. Log files, all under `logs/verify/` and all on disk

`c114-phase6-criteria-1.log` (93 passed in 438.76s) · `c114-criterion-messages.log` (the five
verdicts verbatim) · `c114-sweep-narrow.log` (M1-M5, C0) · `c114-sweep-m1b.log` (M1b and its
killing line) · `c114-sweep-wide.log` (M1 diagnostic, and C0 against the whole suite:
3271 passed, 2 skipped in 1887.83s) · `c114-cash-source-default.log` (37 failed, 167 errors,
202 tests, 7 files + A's) · `c114-narrow-final.log` (5 failed, 445 passed) · `c114-ruff.log` ·
`c114-mypy.log`.


### Decision: a green pytest deposits its evidence, and the PASS carries the count

**Agent:** C · **Task:** spec 115 · **Date:** 2026-09-17

**Options.** Put pytest's summary line in the PASS message and leave the evidence file a
failure-only artefact; or write the file on a green run too and name it in the message.

**Chose.** Both -- `_pytest_count_note` in `scripts/verify.py` writes the evidence and
returns ``pytest `N passed ...` - full output: ...``, and `check_toolchain_green` joins
those notes into the PASS message.

**Because.** The operator retired the lead's separate `pytest tests/ -q` on 2026-09-17 on
the ground that `toolchain_green` runs the identical command. That is true of the command
and was not true of the *record*: the wrapper reported "all green" and threw the run away,
so retiring the second run would have deleted the test count from every boundary rather
than moving it. `0 passed` and `3271 passed` are both exit 0. Exit 5 covers *no tests
collected*, but a renamed directory, a stray `-k`, or a `testpaths` edit that simply
collects **less** is silent at the returncode, and that is the failure the count exists to
make visible.

**Cost.** One log file per gate run under `logs/verify/toolchain_green/`, which is
gitignored, plus a longer PASS message. Nothing in the retry, the timeout, the exit-code
classification or the `TOOLCHAIN` commands moved.

**The degraded branch is stated, not silent.** Exit 0 with no counts line reports
`pytest exited 0 but printed no summary line`. A PASS that cannot count has to look
different from one that did, or the number stops being on record again without anyone
touching this code.

**Which attempt the count comes from.** On the crash-then-clean-retry path it is read off
the **retry**. `CRASH_OUTPUT` in the Phase 0 tests is `520 passed in 12.68s` followed by a
Windows fatal exception -- that is how far the process had got before it died, not a
total, and introducing it as the count would be the same defect this spec fixes wearing a
plausible number. `test_the_count_is_read_off_the_attempt_that_finished_not_the_crashed_one`
drives the two attempts with **different** counts, so it asserts which one is introduced
as the count rather than only that both strings appear.

**Checked against real pytest, not against my memory of it.** The three committed tests
script `_run_tool`, so they prove the plumbing and not the parse. A hand run built a
throwaway tree (`src/`, `scripts/`, one two-test `tests/`) and called the real
`check_toolchain_green` on it. Verbatim:

    PASS - pytest, mypy --strict and ruff all green (python.exe) - pytest `2 passed in
    0.21s` - full output: .../20260917T212441_263818-pytest-attempt1.log

and the deposited file carried the header, the progress line and the summary with LF
endings. `pytest_summary_line` was written for a crash report and had never been asked to
parse a *green* tail before.

**Mutations.** Narrow set `tests/verify/test_phase0_criteria.py`, baseline `74 passed in
22.17s`. `scripts/verify.py` sha256 `63ef97974a31` before and after, compared in the same
statement as the restore; every anchor asserted to occur exactly once;
`PYTHONDONTWRITEBYTECODE=1`; `sys.executable`. Log at `logs/verify/c115-sweep.log`.

| Arm | What it does | Verdict | Killed by |
|---|---|---|---|
| T1 | a green pytest deposits nothing and the PASS says nothing (the spec's named mutation) | KILLED | `test_a_green_pytest_puts_its_count_in_the_pass_message_and_keeps_the_output`, `test_a_green_pytest_that_printed_no_summary_says_so_rather_than_implying_one` |
| T2 | the note keeps the evidence path and drops the summary line | KILLED | `...puts_its_count_in_the_pass_message...`, `...read_off_the_attempt_that_finished...` |
| T3 | a crash then a clean retry passes with no count at all | KILLED | `test_the_count_is_read_off_the_attempt_that_finished_not_the_crashed_one` |
| T4 | the summary reaches the message and the output is thrown away | KILLED | all three |
| C0 | control: the crash note is printed *before* the count instead of after | SURVIVED | -- |

**C0 is a checked negative and is reported as one.** Nothing asserts the order of the two
clauses in the PASS message and nothing should: both are present, both are named, and an
operator reads the whole line. It is here so the four kills above are not the only thing
the sweep can say.

### The fake cost engine's `fallbacks_used`: what it was asserting, and whether it ever mattered

**Agent:** C · **Task:** spec 117 · **Date:** 2026-09-17

**What happened.** `CONSTANT_FEE_COST_ENGINE` in `tests/verify/test_phase3_criteria.py`
-- the deliberately-wrong cost engine `check_cost_gate_uses_live_fee_tier` is proved FAIL
against -- publishes `"fallbacks_used": []`. Engine 10 stopped publishing that key in spec
111, and the file was **48 passed before and after**. B found it while removing the field
and reported it rather than editing, because the file is C's.

**The operator's question: what was that key asserting?** **Nothing, on any day of its
life.** Two findings, from the history rather than from today's code:

1. The double was born in `6291981` (spec 45, 2026-09-10) and carried the key from its
   first line. At that commit engine 10 *did* publish `fallbacks_used`, as
   `fallbacks_used=self._fallbacks()`. So the double was faithful when written.
2. It was faithful to something **already inert**. `_fallbacks()` at that same commit
   returns an empty tuple unconditionally, and its own docstring says why: it used to read
   `state["exchange"]["fallbacks_used"]`, *"which engine 1 does not publish and never
   did"*. On the day the double copied the field, the field it copied could not take a
   non-empty value. The double's `[]` was a faithful copy of a constant.

**Had it ever been load-bearing?** No, and the check is cheap:
`git log -S "fallbacks_used" -- scripts/verify.py` has exactly one hit, `df49cb4`, which
is spec 113/114 and engine 22's trade rows -- a different field on a different engine.
`check_cost_gate_uses_live_fee_tier` has never contained the string. It reads
`net_edge_pct` twice, then `clears_hurdle`, `hurdle_pct` and `reason_code`, and
`result.blocks_trading`. The key set has never been in its field of view, so the extra
field was inert on the day it was written and inert on the day it went stale. This is
`code-standards.md`'s *double that stopped tracking what it doubles*, caught unusually at
the exact moment it stopped -- and the more interesting half is that **the drift is not
what made it useless**. It was never carrying a claim.

**Decision: the key comes out, and no key-set assertion goes into the criterion.** Spec
117 step 3 invites the answer that the right check lives in B's lane, and it does.
`tests/engines/test_cost.py::test_this_engine_publishes_no_fallback_field_and_the_key_set_is_pinned`
already compares `set(result.data)` against `COST_PAYLOAD_KEYS` on **the real engine**, on
all three published shapes. Three reasons not to copy it into the criterion:

* The criterion judges a *fabricated* engine on its FAIL path, so a key-set assertion
  there is a test of C's fabrication in exactly the arm where the fabrication is the
  subject.
* `COST_PAYLOAD_KEYS` is a statement about B's payload. A second copy maintained in C's
  `verify.py` is the same defect one level up: a description of another lane's contract,
  kept by the lane that does not own it, with nothing comparing the two.
* It would **shadow the FAIL arms that already exist.** Each induced-failure test in this
  file induces one defect and asserts the criterion names *that* defect (`"did not move
  when the fee tier did"`, `"Something other than the reported fee"`). A shape check
  running before the arithmetic would answer every one of them with a complaint about a
  key, and those assertions would go red for a reason that has nothing to do with what
  they test.

**Fix.** The key is deleted from the double, and the blindness is closed **where it
actually is** -- on the double, not on the criterion.
`test_the_fabricated_cost_engine_publishes_engine_tens_key_set` drives the real engine 10
and the fabricated one over the same tick, through the criterion's own `_cost_tick`, and
compares `set(result.data)`. It reads the two payloads rather than either lane's
description of them, so it carries no copy of the key set and goes red whichever side
moves.

**What now goes red that did not before.** Restoring `"fallbacks_used": []` to the double
turns that test red -- which is precisely what `48 passed both before and after` was
reporting as fine. Deleting a *real* key from the double turns it red too, in the other
direction, so it is a tripwire rather than a one-sided ban on extra fields. Both arms were
observed, and the tree's pre-fix state was observed red with the tripwire in place before
the key was removed. Mutation table with sha256s below.

**Mutations, spec 117.** Against `tests/verify/test_phase3_criteria.py`, which is a CRLF
file -- read and written as bytes throughout, with the anchors carrying `\r\n`, because a
patch that normalised the endings would rewrite all 1222 lines and the restore check would
be comparing the wrong thing. sha256 `e3366224b083` before and after, compared in the same
statement as the restore. Every anchor asserted to occur exactly once.
`PYTHONDONTWRITEBYTECODE=1`, `sys.executable`. Narrow set the file itself, baseline
`49 passed in 21.81s`. Log at `logs/verify/c117-sweep.log`.

| Arm | What it does | Verdict | Killed by |
|---|---|---|---|
| F1 | `"fallbacks_used": []` is put back -- the exact state the file was 48-green in | KILLED, `1 failed, 48 passed` | `test_the_fabricated_cost_engine_publishes_engine_tens_key_set` |
| F2 | the drift in the other direction: the double drops `hurdle_pct`, which engine 10 publishes | KILLED, `1 failed, 48 passed` | the same test, and nothing else |
| C0 | control: a *value* in the double changes (`pair` uppercased) and no key does | SURVIVED, `49 passed` | -- |

**Both kills are `1 failed`, and that is the finding.** Each arm is caught by the new test
and by nothing else in the file -- F1 is the stale key restored, and the seven existing
observations of `cost_gate_uses_live_fee_tier` sat green through it for a whole spec. F2
proves the tripwire is a comparison rather than a one-sided ban on extra fields: a double
that quietly drops a key engine 10 publishes is the same defect and the criterion is as
blind to it.

**C0 is a checked negative.** The double's *values* are load-bearing only where the
criterion reads them, and `pair` is not one of those -- the criterion takes the pair from
`_cost_tick`'s return, not from the payload. It survives because the tripwire is about
shape, which is what it should be about; filed here so the two kills are not the only
thing the sweep says.

**Narrow results.** `tests/verify/test_phase3_criteria.py` 48 passed before, **49 passed**
after (`logs/verify/c117-phase3.log`). `tests/verify/test_phase3_criteria.py` +
`test_phase0_criteria.py` together, with `pytest-randomly` left on, 123 passed.
`tests/verify/test_runner.py` + `test_workspace_sweep.py` + `test_docs_vocabulary.py`
55 passed. B's own pin, run read-only to check the claim above rather than to change
anything: `tests/engines/test_cost.py -k key_set` 1 passed.


### Spec 101 step 1: what the console actually shows of a live position

**Agent:** C · **Task:** spec 101 · **Date:** 2026-09-17

**What happened.** Hand check before any change, as step 1 requires. A real daemon at fee
tier 3 was driven through `verify.py`'s own harness -- `_driven` / `_warm_up` / `_entry` /
`_fill` -- so engines 18, 21 and 19 opened a position for real, and a `ConsoleReader` was
pointed at that same database and asked for `positions()` on three ticks: the fill, a
second tick with the mark moved, and a tick engine 4 blocked so engine 21 held. Every
field of the view and of the WebSocket payload was dumped. `BTC/USD`, `pair_decimals` 1,
`lot_decimals` 8, entry 126.9, qty 26.26015939, position `pos-1690626088`.

**Most of it is already right, and that is worth saying first.** The mark moved with the
market (126.9 to 127.425 to 124.596), `unrealised_pnl` moved with it and changed sign,
`direction` went `flat` / `pos` / `neg`, the percentage was explicitly signed throughout
(`+0.00%`, `+0.41%`, `−1.82%`), the minus is a real U+2212 -- it crashed my own dump
script under cp1252, which is the most convincing evidence rule 6 holds that I could have
asked for -- and `age_text` counted up `0ms` / `1m 00s` / `2m 00s` against `timeout_at`.
Phase 1 built this against seeded rows and it survives contact with rows engine 19 wrote.

**Three findings.**

**1. The hold is invisible.** On the held tick engine 21 published
`hold_reason='data_guard_blocked'` and engine 19 stored it on the position -- both
confirmed in the dump -- and the console renders **nothing**. `PositionView` has no
`hold_reason` field at all, so a held position and an ordinary one are the same row on
screen. This is the criterion's own PENDING and spec 101 step 3. What the operator is not
being told is specific and it matters: exits are paused. The prose already exists in
`REASON_PROSE` (`format.py`), added with engine 21's codes -- *"Exits are paused while
this tick's market data is rejected; the position is still watched"* -- and nothing was
ever wired to render it.

**2. Staleness is computed, sent, and then dropped on the floor.** `PositionView.staleness`
is built by the reader, reaches the browser inside `_position_payload`, and
`static/console.js` **never applies it to a position row**. `applyStaleness` is called
twice, both times for the status band (balance, data age). So `ui-context.md` rule 5 --
"any figure older than `console.stale_after_ms` renders at 50% opacity with its age shown
beside it" -- does not hold for the open-positions region, which is the region spec 101 is
about. The CSS was never the gap: `.stale { opacity: 0.5 }` and `.age` are both already in
`console.css` under a comment quoting rule 5. Nothing called them.

This is the shape `code-standards.md` keeps recording from other directions -- a value
that is produced, carried and asserted on at the producing end, with no test anywhere
asking whether the consumer does anything with it. `test_a_position_view_renders_every_
figure_as_a_string_too` checks `staleness.stale_after_ms` on the view; no test asks
whether a stale row looks stale.

**3. Rule 4 holds for every figure the daemon quantized, and `unrealised_pnl` is not one.**
This one is a **stop-and-report, not a fix**, and it is recorded here rather than acted on.

`ui-context.md` rule 4 reads "Money renders to the quote currency's own precision from
`AssetPairs`, never more digits than the exchange itself uses." `format.py`'s own header
restates the same rule as "Money renders to the precision it was stored at", and
`format_money` therefore never quantizes -- a Phase 1 decision with a test behind it
(`test_money_renders_at_the_precision_it_was_stored_at`). The two readings agree exactly
as long as the **writer** quantizes to the exchange's precision, and for prices it does:
`entry_price_text` is `126.9`, one decimal, which is this pair's `pair_decimals`.

`unrealised_pnl_text` rendered **`−60.50340723456`** -- eleven decimal places. It is a
product, `qty` at 8 lot decimals times a price, and nothing quantizes the result. By
`ui-context.md`'s wording that is a violation on the figure an operator looks at most; by
`format.py`'s wording the console is behaving correctly and the number it was handed is
the problem.

**Why I am not deciding it.** Every available fix is either outside my lane or forbidden
by this spec:

* Quantizing in the reader or the view is **re-rounding money the console did not
  compute**, which spec 101's own scope limit forbids ("do not compute PnL in the browser
  or the reader beyond formatting what engine 21 published") -- and it changes the value
  the operator reads, not merely its presentation.
* Quantizing in engine 21 is B's lane and changes what the daemon stores.
* And the rule does not say which precision a *PnL* takes. `pair_decimals` is a **price**
  precision for a pair; an unrealised PnL is an amount in the quote currency, whose own
  display precision `AssetPairs` gives per asset -- and the console has no asset-level
  data plumbed to it at all.

So three documents would have to agree before a line is written, and the operator is the
one who settles that. Reported rather than decided, per the lead's instruction. Everything
about rule 4 that **is** settled gets asserted: the criterion checks the price figures
against the `pair_decimals` engine 1 published on the same tick, so the half of the rule
that holds is held, and the half that does not is named here rather than quietly rounded
away.

**Fix (findings 1 and 2).** Recorded below with the design choice and the mutations.


### Spec 101: the fix, and a correction to finding 3 that the criterion made for me

**Agent:** C · **Task:** spec 101 · **Date:** 2026-09-17

**Fix for findings 1 and 2.** `PositionView` gained `hold_reason` and `hold_reason_text`;
the reader fills them from `PositionRow.hold_reason` through `operator_reason`;
`payloads.py` sends both halves; the template gained a left-aligned `Hold` column and
`console.js` renders `p.hold_reason_text` in it. Rule 5 now reaches the row: the three
`aged` cells take the `stale` class and the mark carries an `.age` span, through the
**existing** `applyStaleness` rather than a second implementation.

**Both view fields are required, with no default**, although `None` is the ordinary value
for `hold_reason`. `code-standards.md` records the cost of the other choice in this exact
place and in this lane: a `PositionRow` whose `hold_reason` defaults to `None` satisfied
the assertion a test was making about engine 19, and the test passed under its own
mutation. Every construction site is the reader, which always has the row.

**Decision: a `Hold` column, left-aligned and last.** Options were a tenth column, a
second row beneath each position spanning the table, or a `title` attribute.

*Chose* the column. `ui-context.md` designs the status band, the open-positions region and
the cycle feed, and it hands an undesigned column "the same table treatment as the cycle
feed: left-aligned labels, right-aligned tabular numbers" — and the cycle feed's own row
is *time · pair · outcome · reason*. A reason as a trailing left-aligned column is
therefore the treatment the document already gives a reason, rather than one I invented.

*Rejected* the spanning second row: it changes the row count of a table an operator scans
by eye, and a region that is sometimes one row per position and sometimes two is harder
to read at a glance than a column that is usually blank. *Rejected* the `title`
attribute outright — invisible to a keyboard user and to anyone not hovering, which fails
the quality floor rather than meeting it.

`test_the_hold_column_is_prose_and_stays_out_of_the_tabular_run` holds the one thing that
could quietly go wrong: marking it `num` would right-align an English clause into the mono
face, which is the treatment the document reserves for numbers.

**Which cells rule 5 fades, and why not the row.** `staleness` is measured from
`updated_at`, so it ages exactly the figures that come from the daemon's last touch: the
mark and the two unrealised figures computed from it. The entry, target and stop were
decided at the fill and are still exactly true. Fading the whole row would be worse than
imprecise: `age_us` says a long-held position is hours old, so a row faded on the
*position's* age would sit at half opacity for as long as it was held — which is the
failure `ui-context.md` names for a poll interval set too close to the stale threshold,
"a slow poll would fade the entire screen to half opacity permanently". The three cells
are found by an `aged` marker class rather than by counting columns, so inserting a
column cannot silently fade the wrong one, and the marker deliberately has **no** CSS:
`.stale { opacity: 0.5 }` stays the only appearance rule, asserted by
`test_the_stylesheet_still_owns_rule_5_and_nothing_else_declares_the_opacity`.

### Correction: rule 4 is broken wider than the hand check said, and the criterion found it

**Agent:** C · **Task:** spec 101 · **Date:** 2026-09-17

**What happened.** Finding 3 above named `unrealised_pnl` as the one figure rendering more
decimals than the exchange uses. That was the figure I *looked at*. When the criterion
asserted the rule across all four price figures, it came back FAIL naming three more:

    the mark renders '124.596', which is 3 decimal places where AssetPairs gives this
    pair 1; the target renders '130.707', ... 3 ...; the stop renders '124.9965',
    which is 4 decimal places where AssetPairs gives this pair 1

**Why.** Only the **entry price** has a writer that puts it on the exchange's grid —
engine 18 quantizes the limit before placing the order, and `verify.py`'s `_entry`
recomputes that and refuses anything else. The target and the stop are
`entry * (1 +/- pct)` from engine 21 and **nothing quantizes the product**. The unrealised
PnL is `qty * (mark - entry)`, a lot-precision quantity times a price, and nothing
quantizes that either. The mark is the published bid, which in this drive is a price the
criterion itself pinned — so on that one figure a criterion would be judging its own
harness.

**This is the correction worth keeping**, and it is the same shape as the rule this lane
has now hit three times: *a description of the code is not the code.* I read one figure,
generalised from it, and wrote a build-log entry naming one field. The check that ran
against all four disagreed with me within a minute of existing. The hand check was not
wrong to look — it found the thing — it was wrong to stop at the first instance and
report the shape from a sample of one.

**Decided: measured and named, never judged.** `_console_rule_4` in `scripts/verify.py`
returns the over-precise figures and the PASS message carries them verbatim. Three
reasons a FAIL would have been the wrong verdict:

* It would be **red on a tree nobody has broken.** The console renders exactly what it was
  handed; the digits are the daemon's.
* Every fix is outside this spec or this lane. Quantizing in the reader is what spec 101's
  scope limit forbids by name — "do not compute PnL in the browser or the reader beyond
  formatting what engine 21 published" — and re-rounding changes the value, not its
  presentation. Quantizing in engine 21 is B's lane.
* **The rule does not settle which precision applies.** `ui-context.md` says "the quote
  currency's own precision from `AssetPairs`"; `format.py` says "the precision it was
  stored at" and never quantizes, with a Phase 1 test behind it. `pair_decimals` is a
  **price** precision for a pair, and an unrealised PnL is an amount in the quote
  currency, whose own display precision `AssetPairs` gives per *asset* — which the console
  has no plumbing for at all.

So the criterion asserts the half that is settled (the entry price must be on engine 18's
grid, a FAIL if the console loses or invents a digit there) and reports the rest as an
`OPEN` clause in its PASS line. Saying nothing would have let the operator's open question
quietly become the answer; failing would have been a gate that is wrong about a tree that
is right.

**Raised to the lead as a stop-and-report.** Nothing was changed in engine 21, in the
reader's formatting or in either document.


### The staleness test could not see its own mutation, and the sweep is what said so

**Agent:** C · **Task:** spec 101 · **Date:** 2026-09-18

**What happened.** The first console sweep came back eight arms, **seven killed and S1
SURVIVED**. S1 is `applyStaleness(aged[0], null)` — the verdict is computed, serialised,
sent, and then thrown away at the last step. That is *exactly* the pre-spec-101 behaviour
the whole staleness half of this spec exists to fix, and the entire console suite,
including the test I had just written for it, stayed green: `365 passed`.

**Why.** `test_a_stale_position_row_is_faded_and_shows_its_age` asserted
`"applyStaleness" in source` and `"p.staleness" in source` as **two separate substring
checks**. Under S1 both were still true: the call was still there, and `p.staleness` was
still there — in a *different* statement, the `classList.toggle` loop that faded the other
two cells. The test said "this row applies its staleness" and asserted "these two words
both occur somewhere in this function". A test can see that a function is called far more
easily than it can see what it was handed.

This is the substring trap from `code-standards.md` in its passing-for-the-wrong-reason
direction, and it is the second time this lane has hit that direction specifically. It is
also the lead's instruction (1) failing on its own terms: the staleness fix was to be
**asserted, not merely fixed**, and it was merely fixed.

**Fix, and it is in the code as much as in the test.** The builder had **two** places
where rule 5 was decided — `applyStaleness` for the mark, `classList.toggle` for the other
two cells — and two places is what made the argument hard to pin. There is now **one**: the
`.age` span is created first, then a single loop calls `applyStaleness(aged[a],
p.staleness)` over every aged cell. The test pins that call **with its argument**, asserts
`applyStaleness` occurs exactly once so the argument is the only thing that can be wrong,
and asserts `classList` does not appear at all so a second path cannot grow back. S1
re-aimed at the new line is **KILLED**.

**The residual limit, stated rather than hidden**, as `check_console_tabular_figures`
states its own: this reads source text. It holds the verdict to being *passed* to the one
function that fades a cell; it cannot watch a browser compute an opacity. What it now does
is go red the moment the position row stops handing rule 5 its answer, which is the
failure that actually occurred.

**Mutations, spec 101 console side.** Four targets, byte copies taken before anything was
applied, all restored in a `finally` with every sha256 compared in the same statement.
Every anchor asserted to occur exactly once. `PYTHONDONTWRITEBYTECODE=1`,
`sys.executable`, narrow set `tests/console/`, baseline `365 passed`. Logs:
`logs/verify/c101-sweep.log` (the run that found S1) and `logs/verify/c101-sweep-2.log`
(after the fix).

sha256 before and after: `reader.py` `082714b4297b`, `payloads.py` `a6a5fc14d628`,
`index.html` `1e82c54dadfc`, `console.js` `98ab474489fc` in the first sweep and
`8199ec2f1655` in the second — the one file the fix changed, and the only hash that
differs between the two runs.

| Arm | File | What it does | Verdict | Killed by |
|---|---|---|---|---|
| H1 | reader | drops the hold engine 19 stored | KILLED, 3 failed | the three `test_live_position` hold tests |
| H2 | reader | the raw reason code reaches the screen instead of prose | KILLED, 1 failed | `test_a_held_position_shows_its_reason_as_operator_prose` |
| H3 | payloads | the prose is built and then not sent to the browser | KILLED, 1 failed | the same test, through `payload()` |
| H4 | console.js | the page renders an empty Hold cell whatever arrives | KILLED, 2 failed | `..._builds_one_cell_per_column`, `..._shows_the_hold_reason_spec_101_asks_for` |
| S1 | console.js | rule 5 is never applied to the row (the pre-spec-101 behaviour) | **SURVIVED**, then KILLED | `test_a_stale_position_row_is_faded_and_shows_its_age`, after the fix above |
| S2 | console.js | the unrealised figure stops fading with the mark it comes from | KILLED, 1 failed | `test_the_faded_cells_are_the_figures_that_age_and_not_the_whole_row` |
| S3 | console.js | a figure decided at the fill fades with the mark | KILLED, 1 failed | the same test, from the other side |
| T1 | template | the prose column joins the tabular run | KILLED, 1 failed | `test_the_hold_column_is_prose_and_stays_out_of_the_tabular_run` |
| C0 | reader | control: `is None` becomes a falsiness test | SURVIVED | — |

**C0 is a checked negative and is reported as one.** `hold_reason` is either a code or
null; no engine writes it empty, so `is None` and falsiness cannot disagree on any value
that exists. Killing it would need a fixture asserting a fact the system cannot produce.
It is in the table so the eight kills are not the only thing the sweep says — and, this
time, so that a survivor in the table is not automatically read as a hole.

**S2 and S3 are the pair that matters for the "which cells" claim.** S2 stops the
unrealised figure fading with the mark it is computed from; S3 fades a figure that was
decided at the fill and cannot go stale. One test kills both, from opposite directions,
which is what stops it being a one-sided ban on a class name.

**The criterion's FAIL arm is not in this sweep** and is observed separately, in a copied
tree, at `logs/verify/c101-fail-arm.log`: `reader.py` sha256 `082714b4297b` before and
after, the mutation applied only to the copy, and the verdict

    FAIL - the console's open-positions region: the console still shows the mark as 126.9
    after the market moved to 127.4; the open-positions region is a snapshot, not live

It is registered in `MUTATIONS` as `console_serves_the_previous_mark` and is the only
entry there that breaks a file in C's own lane; every other arm breaks an engine. A
criterion whose FAIL arm lives in somebody else's file is not watching its own subject go
wrong.


### Rule 4 amended: what the criterion now says, and the one figure it cannot stand behind

**Agent:** C · **Task:** spec 101 · **Date:** 2026-09-18

**The ruling.** The operator amended `ui-context.md` rule 4 rather than round anything: an
**order price** renders at the precision it was stored at, because its writer rounded it
to the exchange's grid before sending it; a **derived threshold** renders at the precision
it was computed to, **and the console does not round it.** Rule 4 is a rule about
*writers*, and the console has never been able to obey the older wording — it reads only
the store, and the store holds no pair rules. Rounding the barriers at write time was
available (engine 21 holds `pair_rules` at the line where it writes the row) and was
rejected, because `research/labelling.py` computes its barriers the same unrounded way, so
rounding the live ones would make the system trigger on barriers the training labels were
never built from.

**What changed in the criterion.** `_console_rule_4` is gone, replaced by two readings
that the amendment separates:

* `_console_thresholds` reports the target, the stop and the unrealised PnL **as what they
  are** — derived, deliberately unrounded — citing rule 4 *as amended 2026-09-18* so the
  sentence stays true if the rule moves again. They are no longer described as a breach.
* `_console_mark_precision` measures the mark on its own, because it is a third case: an
  exchange-supplied bid passed through unchanged should already be on the grid.

The entry price is unchanged and is still the one rule-4 **FAIL** in this criterion: it is
the order price, engine 18 put it on the grid, and the console rendering it at any other
precision is the console losing or inventing a digit.

**Why the old wording had to go and not just be tolerated.** It reported a measurement
against a rule that no longer applies — a permanent false positive in a PASS message,
which is the thing the operator rejected. A gate that cries about correct behaviour on
every run teaches its reader to skim it.

**The mark: this criterion judges its own harness, and that is on the record.** `drive.pin`
sets the bid the criterion then measures. An assertion about a value the test itself
supplied proves nothing about that value — the same defect as a double that agrees with
its caller, arriving through a *fixture* rather than through a stub. So the message says
so in as many words: *NOT a verdict on engine 3: this criterion pinned that bid itself.*

**The independent measurement, and it is conclusive.** A bid the drive did not choose was
available after all: `tests/fixtures/book_sample.jsonl` is 977 Kraken v2 book frames copied
**byte-for-byte** out of `data/raw/` by A's cutter, and the recorded `AssetPairs` sits
beside it in `tests/fixtures/kraken/asset_pairs.json`. Both are recordings; neither is a
number anybody in this project chose. Measured by hand:

* **BTC/USD** — recorded `pair_decimals` **1**, and **783 recorded book prices, every one
  at exactly 1 decimal place.** The exchange publishes on its own grid, so the 3dp mark in
  this criterion is this harness's pin and **not** an engine 3 finding. Nothing to route
  to A.
* **ADA/USD** — prices at 4, 5 and 6 places, and **no `pair_decimals` for it in the
  recorded `AssetPairs` at all**, so there is nothing to compare against. Reported as
  inconclusive rather than guessed: inventing a precision for it would be exactly the
  fabricated-exchange-value `AGENTS.md` opens by forbidding. (A cheaper asset plausibly
  carries a larger `pair_decimals`; plausible is not measured.)

**The archive check is deliberately not added to this criterion.** A criterion named
`console_shows_position_live` has no business asserting Kraken's price grid, and
`order_book_slippage_on_recorded_book` already reads that fixture in A's own area. Where it
would belong is recorded in `_console_mark_precision`'s docstring along with the numbers,
so the next person does not have to re-derive them.


### The gate cannot print its own verdicts when its output is redirected

**Agent:** C · **Task:** spec 101 follow-up · **Date:** 2026-09-18

**What happened.** The lead ran `python scripts/verify.py --phase 6 > log 2>&1` and the
process **died mid-run**:

    File "...scripts/verify.py", line 14314, in main
        print(criterion_line(criterion, outcome, width), flush=True)
    UnicodeEncodeError: 'charmap' codec can't encode character '\u2212' in position 647

Seven criteria had printed. The remaining criteria **never ran**, and the phase result was
never printed. Log: `logs/verify/phase6-20260918-spec101-lead-verify.log`.

**Why.** `main()` prints to `sys.stdout`. When stdout is a console, Python 3.13 on Windows
uses the UTF-8 console writer and everything is fine; when it is **redirected to a file**,
the stream is opened with `locale.getencoding()`, which here is **cp1252**, and cp1252 has
no U+2212. Every gate run this project has ever done was fine because no criterion message
had ever contained one. Spec 101's is the first: `ui-context.md` rule 6 requires U+2212 in
numeric output, my criterion asserts the console obeys it, and the PASS message quotes the
figures it checked — `−1.82%`, `−60.50340723456`.

**So the project's own house style was unprintable by its own gate**, and the two had never
met. Nothing was wrong with the message; the tool could not carry it.

**Why no test caught it.** Every test of `verify.py` calls the criteria directly and reads
`outcome.message` as a `str`. **Nothing had ever driven `main()`'s printer through a stream
with a real encoding**, so the entire output path — the one thing the operator actually
looks at — was exercised only against pytest's capture, which is UTF-8 and forgiving. This
is the seam rule from `code-standards.md` in a new place: the criteria's tests assert what
a criterion *returns*, and the printer's behaviour is what the operator *gets*, and no test
stood between the two.

**And note which failure mode this is.** Not a wrong answer — a *lost* one. The run died
with `exit 1`, which is the same exit code a real FAIL produces, so a reader who saw only
the code would conclude the phase was red on its merits. Six criteria that had not yet run
reported nothing at all.

**Fix.** `main()` makes its own streams UTF-8 before it prints anything, with
`errors="backslashreplace"` so that a verdict can never be lost to an encoding — see the
next entry for why `strict` is not enough even with UTF-8. Done inside `main()` and **not**
at import, because `tests/verify/` imports this module and reconfiguring global streams at
import time would fight pytest's capture.

**Consequence.** `scripts/verify.py` only. The criterion message the operator settled is
not touched.


### The fix, and what could still end a run

**Agent:** C · **Task:** spec 101 follow-up · **Date:** 2026-09-18

**Fix.** `make_console_utf8()` in `scripts/verify.py`, called as the first statement of
`main()`, reconfigures `sys.stdout` and `sys.stderr` to UTF-8 with
`errors="backslashreplace"`. It returns the streams it could not change, and `main()`
prints a **WARNING** line under the header naming them — on such a stream the original
crash is still possible, and the reader has to learn that before it happens rather than
from a traceback six criteria later.

It never raises. A stream that cannot be reconfigured (already wrapped, replaced by a
test, something a caller handed us) is not a reason to refuse to run the gate. And it is
called from `main()` and **never at import**, because `tests/verify/` imports this module
and mutating global streams at import time would fight pytest's capture.

**Why `backslashreplace` and not `strict`, which is the part worth keeping.** UTF-8
encodes every Unicode scalar value, so with `strict` the fix would look complete. It is
not: UTF-8 cannot encode a **lone surrogate**, and lone surrogates reach this program by
an ordinary route rather than an exotic one — `os.fsdecode` maps undecodable filesystem
bytes into the surrogate range, and criterion messages **embed paths**
(`toolchain_green`'s "full output: ..." is one, and it is a path this tool constructs on
every run). Strict UTF-8 would therefore still be able to kill a run, on a rarer input,
which is the worse version of this bug rather than a fixed one: the same defect, now
firing once a year instead of once a phase, when nobody is expecting it.

`backslashreplace` over `replace` because it keeps the information. The escape names the
code point; `replace` discards it. A tool whose whole purpose is not losing a diagnosis
should not lose one at the last step either.

**So, the answer to "can any criterion message still carry a character this cannot
represent": no.** Every `str` is now printable — scalars by UTF-8, lone surrogates by the
escape. The only residual is a stream with no `reconfigure` at all, and that is named in
the output rather than hidden.

**Proofs, both on the record.** `logs/verify/c101-encoding-proof.log`. `verify.py` sha256
`4659e831fd67` before and after, compared in the same statement as the restore; the anchor
occurs exactly once; `PYTHONDONTWRITEBYTECODE=1`; `sys.executable`.

*A. The tests fail on today's code.* With `make_console_utf8`'s body neutered in place,
`tests/verify/test_runner.py` goes **3 failed, 22 passed** — the three tests about the fix.
`test_a_locale_encoded_stream_cannot_carry_the_minus_sign_this_project_mandates` stays
**green**, and deliberately: it pins the *hazard*, which is a property of cp1252 and not of
this code, and it is what stops the fix quietly becoming decoration. Restored: 25 passed.

*B. The fixed path works end to end, through the real `main()`.* A subprocess drives
`main()` against a registry holding one criterion whose verdict carries U+2212, with
**stdout redirected to a file** and `PYTHONIOENCODING=cp1252` so the stream is opened
exactly as the operator's redirect opened it:

| | exit | `UnicodeEncodeError` in output | U+2212 present | summary line |
|---|---|---|---|---|
| with the fix | 0 | no | yes, as UTF-8 | yes |
| without it | 1 | **yes** | no | **no** |

The bottom row is the operator's failure reproduced exactly, including the part that makes
it dangerous: **exit 1 with no summary line**, which is indistinguishable by exit code from
a phase that is red on its merits.

**A note on how this entry was nearly written wrong.** The first draft of the test file
went in through a bash heredoc and the `\u2212` escapes arrived as literal minus signs,
which `ruff`'s RUF001 then refused. That is the **third** time a heredoc has done this in
this project and my own build log records the previous two. The literals are now
`chr(0x2212)`, which has a second reason beyond the lint: an editor that helpfully
normalised the character into an ASCII hyphen would turn these tests into *hyphen* tests,
and cp1252 encodes a hyphen perfectly well — so both halves would go green against the
very bug they exist to catch.


### Recurrence: the bash heredoc has now eaten an escape three times in one phase

**Agent:** C · **Task:** spec 101 follow-up · **Date:** 2026-09-18

**Filed as a pattern, on the lead's instruction, because three is not an accident.** The
first two are already in this file as incidents; this is the entry that names the
mechanism.

**What happens.** A file is written with

    python - <<'PYEOF'
    ... source containing \u2212 or \n ...
    PYEOF

The quoted delimiter is supposed to make the heredoc literal, and for the **shell** it
does. The escape is eaten one layer up, before the shell ever sees it: the tool call's own
argument is a JSON-ish string, so `\u2212` in the command text can arrive at bash already
decoded to the character, and `\n` already decoded to a newline. The heredoc then faithfully
passes on something that is no longer what was written. Nothing warns, because the result
is still valid Python.

**The three occurrences, and note that the symptom differs every time** — which is why it
keeps being read as a fresh problem rather than as this one:

1. **Escapes silently dropped from an edit** (recorded earlier this phase): three edits
   lost, discovered only because the file did not do what it said.
2. **A `\n` inside a patch string became a real newline**, so an anchor that should have
   matched one line spanned two and matched nothing. Caught by an `assert count == 1`.
3. **Today**: `\u2212` arrived as a literal U+2212 in `tests/verify/test_runner.py`, and
   `ruff`'s RUF001 refused it. Caught by the linter, not by me.

**Why it is worth a rule and not just care.** Each time, the failure surfaced somewhere
unrelated to the cause — a silent no-op, a non-matching anchor, a lint about ambiguous
characters — and each time the first hypothesis was about the *content* rather than the
*transport*. The cost is not the mistake; it is the minutes spent looking in the wrong
place, three times.

**The rule, which was already written down and which I broke anyway.** Write files with
the file tool, or with a Python script written to disk and then executed. **Never a bash
heredoc carrying escapes.** My own build log has said so since yesterday. I used one today
because the edit was small, which is exactly the circumstance the rule exists for: nobody
reaches for a heredoc on a large file.

**Two guards that actually caught things, worth keeping:**

* **Never hand-type a mandated character into source.** `chr(0x2212)` in both
  `scripts/verify.py` and `tests/verify/test_runner.py`. This defends against more than
  the transport: an editor that normalised U+2212 into an ASCII hyphen would turn the
  encoding tests into *hyphen* tests, and cp1252 encodes a hyphen perfectly well — so
  both halves would go green against the bug they exist to catch.
* **Every patch script asserts its anchor occurs exactly once, before writing.** That is
  what caught occurrence 2, and today it is what stopped a half-applied patch reaching
  disk: the `_console_rule_4` replacement aborted on `assert text.count(whole) == 1`
  because the two anchor halves needed the blank line between them, and the file was left
  untouched rather than mangled.


### Spec 120, diagnosis — the five orphaned keys, derived rather than taken from the list

**Agent:** C · **Task:** spec 120 · **Date:** 2026-09-18

**What happened.** `REASON_PROSE` carries five keys that nothing can now emit:
`insufficient_depth`, `meta_label_veto`, `no_candidate_cleared`, `outlier_market_state`,
`outside_universe`. Each is a sentence on the operator's screen describing a refusal the
system cannot make.

**Derived, not believed.** The spec, the tracker and my own warning test all name the same
five, and B's finding 1 is exactly what happens when a list in a document is trusted — the
2026-09-16 finding named five bad pairs and there were six. So the set was recomputed from
the code in one pass: every `REASON_*` / `HOLD_*` string constant in every
`acsoe.engines.*.contracts` module, minus the three pinned state-field constants, **plus**
every code `clients/store/seed.py` writes, subtracted from `set(REASON_PROSE)`. 65 engine
codes, 12 distinct seed codes, all 12 of them already engine codes after B's spec 119, and
the difference is the five above. The independent derivation and the document agree this
time, which is a result rather than a formality.

**Why the seed is now part of the producer set, and why that is a smaller change than it
looks.** Before spec 119 the seed was a *second* vocabulary — it kept five of the six
invented codes alive, and retiring them would have blanked real rows. After spec 119 every
code it writes is picked out of the named engine's own module, so the seed adds nothing to
the producer set that the engine walk did not already have. That is not a reason to leave
it out: the day somebody adds a seeded row for a code that exists only in a fixture, the
seed is the producer and the walk has to know it.

**What each retired key was, checked one at a time in the code.** `insufficient_depth` is
the Phase 0 spelling of engine 9's `book_too_thin`, and engine 9 has no refusal path at all
— one `EngineStatus.OK` in the module — so the entry describes a refusal by an engine
structurally incapable of making one. This is the case I raised with the lead on 2026-09-16
and could not fix then, because `seed.py` is B's and the row had to keep rendering.
`meta_label_veto` and `outlier_market_state` are the seed's spellings of `skeptic_veto` and
`market_anomalous`; the engines' own codes are mapped beside them and always were.
`no_candidate_cleared` describes engine 16 as "it combines their outputs", which is the
reading the 2026-09-16 gate ruling retired — engine 16 is a coherence gate with five
specific codes and never decides. `outside_universe` is the one with no seed row behind it
at all: it predates engine 7, spec 44 step 7 says in as many words *"`outside_universe`
already exists in C's `REASON_PROSE`"* — and B then built engine 7 with twelve specific
exclusion codes and never emitted the generic one. Nothing was lost by that; the specific
codes say which exclusion, and a per-pair tally keyed on a generic bucket would have been
worse.

**Why the warning was never going to catch this, which is the actual defect.** The inverse
walk has existed since spec 99 and has been printing these five names on every run of
`tests/console/` for two days. A warning in a suite that ends `365 passed, 1 warning` is
read as the shape of the tree, not as a finding. The forward walk (engines to map) is a
hard assertion and goes red the same afternoon a code lands — twice in one day for engines
16, 18 and 21. The two directions catch different defects: forward catches a silent
`"No reason was recorded."`, inverse catches prose describing a refusal nobody can make.
Only one of them was load-bearing, and the unenforced one is the one that sat.

**The justification that died with spec 119, and now reads as a live claim.** Three places
say these keys "stay because they are already on seeded rows": the comments beside
`meta_label_veto` and `outlier_market_state` in `format.py`, and
`test_the_two_skeptic_codes_and_the_seeded_one_are_three_sentences`. A fourth,
`test_the_seed_generators_older_di_spelling_still_renders_because_it_carries_prose`, says
*"`clients/store/seed.py` still writes `dissimilarity_index` on its seeded rows"* — false
since B's spec 119 this morning. All four are mine, all four have a decision entry behind
them (B's, today), and all four go with the retirement rather than being left as prose
describing a repaired defect.


### Spec 120, fix — five sentences retired, and the inverse walk is an assertion

**Agent:** C · **Task:** spec 120 · **Date:** 2026-09-18

**Fix.** Five keys left `REASON_PROSE`: `insufficient_depth`, `meta_label_veto`,
`no_candidate_cleared`, `outlier_market_state`, `outside_universe`. The map is 65 entries
and every one of them is a code some producer emits. `test_the_inverse_is_reported_as_a_
warning_and_never_as_a_failure` is gone and
`test_no_prose_entry_describes_a_refusal_no_producer_can_make` stands in its place: the
same walk, asserted, with the producer set widened from *the engines* to *the engines plus
`clients/store/seed.py`*.

**The red, verbatim, on the unretired map** — the assertion written first and the
retirement second, so the five were named by the mechanism rather than by the spec:

```
E       AssertionError: REASON_PROSE carries sentences no engine and no fixture can
produce, so each is prose for a refusal this system cannot make: insufficient_depth,
meta_label_veto, no_candidate_cleared, outlier_market_state, outside_universe.
FAILED tests/console/test_reason_prose.py::test_no_prose_entry_describes_a_refusal_no_producer_can_make
1 failed, 180 passed in 0.53s
```

After the retirement: `tests/console/ 362 passed`, no warnings, from a baseline of
`365 passed, 1 warning`. The arithmetic of that difference is worth stating because it
looks like a loss: the warning test became two tests (+1), the DI-spelling test became a
narrower one (0), the skeptic seeded-spelling test was turned around (0), the retired
spellings gained six parametrized cases (+6) — and the two tests parametrized over
`sorted(REASON_PROSE)` lost five cases each (−10). 365 + 7 − 10 = 362.

**Three pieces of prose that rested on the retired keys went with them, and they are the
reason this is a spec and not a deletion.** Two comments in `format.py` said each seeded
spelling "stays because it is already on seeded rows", which was true until B's spec 119
this morning; `test_the_two_skeptic_codes_and_the_seeded_one_are_three_sentences` asserted
`meta_label_veto` **in** the map for the same dead reason and is now
`test_the_two_skeptic_codes_are_two_sentences_and_the_seeded_spelling_is_gone`, asserting
it out. A test that pins a justification has to move when the justification does, or it
pins the wrong thing while staying green.

**The `operator_reason` question spec 120 left open: yes, and here is the argument.** The
preference for the row's own sentence is what let the invented vocabulary render correctly
for five phases, and it is also the thing that makes this retirement safe — every row a
producer ever wrote carries a sentence, so removing the key costs those rows nothing. A
premise that load-bearing should not be left to be inferred from behaviour, and it had
exactly one test: the `dissimilarity_index` case, whose docstring was already false.
`test_a_row_carrying_a_retired_code_still_renders_its_own_sentence` now runs all six
retired spellings through both halves — the sentence is preferred, and a row with *no*
sentence renders `NO_REASON_RECORDED`. The second half is the cost of the retirement
written down rather than discovered later. A general test of `operator_reason`'s ordering
for its own sake would belong in `test_format.py` and not here; this one is in this file
because it is this spec's premise.

**Mutations.** `PYTHONDONTWRITEBYTECODE=1`, one mutant at a time, each target byte-copied
and restored in a `finally` with the sha256 compared in the same statement, every anchor
asserted to occur exactly once before writing, no mutant left on disk. Targets
`src/acsoe/console/format.py` = `9efd4601329fb551` and
`tests/console/test_reason_prose.py` = `23274bf6a600f422`, both confirmed identical after
the sweep. Baseline `177 passed`.

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| N1 | A key nobody produces added to the map (`quote_halted_mid_tick`) | `1 failed, 178 passed` — **KILLED** | `test_no_prose_entry_describes_a_refusal_no_producer_can_make`, alone |
| N2 | `meta_label_veto` put back exactly as it was | `3 failed, 176 passed` — **KILLED** | the inverse assertion, the skeptic test, and the retired-spelling case for that code |
| N3 | **Control.** N1, plus the producer set widened to subtract `set(REASON_PROSE)` | `179 passed` — **SURVIVED**, and re-run against the whole of `tests/console/`: `364 passed` | nothing |
| N4 | The seed half of the producer set replaced with `set()` | `1 failed, 176 passed` — killed by the **vacuity guard only**, not by the orphan test | `test_the_seed_walk_collects_codes_and_not_merely_a_tuple` |
| N5 | `operator_reason` stops preferring the row's own sentence | `6 failed, 171 passed` — **KILLED** | all six cases of `test_a_row_carrying_a_retired_code_still_renders_its_own_sentence` |

**N1's first run was a kill for the wrong reason and I nearly kept it.** The fabricated
code I reached for was `quote_delisted_mid_tick` — which is the string
`test_the_enumeration_catches_a_code_nobody_mapped` and
`test_an_unmapped_code_really_does_render_as_silence` already use as *their* fixture, so
the arm reported `3 failed` with two of the three failures having nothing to do with the
walk. Re-run with `quote_halted_mid_tick` it is a single clean kill. Asking *which* test
killed it is what caught it; the verdict alone looked stronger, not weaker.

**N3 is the arm worth keeping**, the same shape as B's M3 on the other side of this seam:
with the producer set widened by one line, a key nothing can emit passes every test in the
console lane. The assertion is about the *derivation*, not about the map, and the
derivation is the single clause doing the work.

**N4 is a checked negative and a finding rather than a survivor.** Every code the seed
writes is, since spec 119, also an engine code, so removing the seed half of the producer
set changes nothing the orphan test can see — an equivalent mutant *today*, and only
today. That is precisely the case the vacuity guard was written for, and it is the one
that killed it: `test_the_seed_walk_collects_codes_and_not_merely_a_tuple` fails because
the walk collected nothing. Without that guard the seed half would be unfalsifiable, and
the failure it hides is not a false pass but a **false orphan** — a key reported for
retirement that the console still needs.

**One run that was not a result.** The first `pytest tests/console/` after the retirement
printed eight dots and stopped: no summary line, no failures, exit status never seen. Per
the standing rule a verdict with no summary line is a run that did not happen, so it was
re-run rather than interpreted; the second run gave `362 passed in 66.31s`, exit 0. Noted
because the temptation was to read the eight dots as a hang in my own change.

**The numbers, for whoever reads this next.** 74 `REASON_*`/`HOLD_*` constants across
the engines, 71 once the three pinned state-field constants are removed, 65 distinct
code values (six spellings are deliberately shared between engines), and 12 distinct
codes in the seed, all 12 of them engine codes since spec 119. `REASON_PROSE` is now 65
entries and the two sets are **equal**: no engine code without a sentence, no sentence
without a producer. That equality is a fact about today rather than a rule - a seeded
code that no engine declares would be a legitimate sixty-sixth entry, which is why the
test subtracts the seed rather than comparing the two sets directly.

**And the fourth heredoc, recorded because it did not fail.** The paragraph above was
appended through `python - <<'PYEOF'` carrying `\n` escapes inside Python string literals
- the exact transport my own entry two sections up says never to use again. It landed
intact and the bytes check out (LF only, no NUL, text verbatim), which is the reason it is
worth an entry rather than a shrug: three previous occurrences failed in three different
places and this one failed nowhere, so the habit gets reinforced by the run that happens to
work. What made it survive is luck about the layer the escape sits in - inside a Python
string literal, a prematurely decoded `\n` would have been a real newline inside a quoted
string and a `SyntaxError`, which is loud. The occurrences that hurt put the escape
somewhere a decoded version is still valid. The rule stands as written: file tool or a
script written to disk first, and no exception for a small append.


### Spec 118: the two fixtures were not "frozen together", and the criterion says so instead

**Agent:** C · **Task:** spec 118 · **Date:** 2026-09-18

**What happened.** Spec 118's rationale says the criterion "can never go red because the
exchange changed its own settings" because "both sides are recordings frozen together".
Before writing the check I went looking for the freeze. There is not one.
`tests/fixtures/kraken/asset_pairs.json` entered the repository in `afaf2f5`, **2026-09-08**;
`tests/fixtures/book_sample.jsonl` was cut from the 2026-09-16 archive and committed in
`a089bc7`, **2026-09-16**. Eight days apart, and neither file records when its response was
fetched — the book sample's header block names its archive window, the `AssetPairs` recording
carries no provenance block at all.

**Why it matters, and why it is small.** The strong form of the rationale — *a red here is
never news about Kraken* — rests on the two recordings being simultaneous. They are not, so a
`pair_decimals` Kraken changed between those two dates would show up here as a red. It did not:
BTC/USD is declared at 1 decimal and all 783 recorded BTC/USD prices carry exactly 1. So the
claim is unsound as an argument and true as a fact about today's two files, which is a
different thing and the criterion must not pretend otherwise.

**Fix.** None in the fixtures — they are not mine and re-cutting to align them is a what-choice.
The criterion's prose states the two dates and says what a red would actually mean: *these two
recordings disagree*, which is either a re-cut fixture landing beside a stale declaration (the
case spec 118 was written for) or, if the recordings are far enough apart, a change the exchange
made in between. Both are worth a human look; neither is a reason to soften the check. Reported
to the lead as a finding against the spec's wording rather than corrected silently.

### Spec 118: where the invented ADA/USD precision sits, and why the criterion cannot see it

**Agent:** C · **Task:** spec 118 · **Date:** 2026-09-18

**What happened.** ADA/USD is the pair spec 118's condition 1 exists for: it is in the book
sample and has no entry in the recorded `AssetPairs`. But `scripts/verify.py` already holds a
`pair_decimals` for it — `BOOK_THIN_PAIR_RULE`, six decimals, fed to the fake exchange by
`order_book_slippage_on_recorded_book` and labelled in its own comment as *"Invented exchange
data for the fake"*. It sits about 1,400 lines above where this criterion now lives, in the same
file, and ADA/USD's recorded prices run to 4, 5 and 6 places — so the invented value would have
"worked".

**Why that is the trap and not the convenience.** A constant in this file is not a declaration
by the exchange. Reaching for it would have turned "I cannot tell" into a plausible number
derived from a value somebody in this project chose, which is the fabricated exchange value
`AGENTS.md` forbids in its first paragraph and the exact behaviour the tracker's ADA/USD entry
records as the one to keep.

**Fix.** The criterion reads the two committed fixtures and nothing else, and its docstring names
`BOOK_THIN_PAIR_RULE` explicitly as the thing it must not read — a near-miss is worth naming,
because the next reader will find it two screens away and wonder why the criterion is
"incomplete".

### Decision: the recorded prices are measured on the grid point, not on the JSON spelling

**Agent:** C · **Date:** 2026-09-18

**Options.** Count the digits a price is *written* with — `75731.0` is 1 decimal place — or
strip trailing zeros first and count the digits the *value* needs — `75731.0` is 0.

**Chose.** The value, via `Decimal.normalize()`.

**Because.** `75731.0` and `75731` and `75731.00` are one point on a 1-decimal grid. A
criterion that went red because Kraken serialised a trailing zero would be firing on how the
exchange formats JSON, which is exactly the "fires on somebody else's decision, therefore gets
ignored" shape spec 118 is written to avoid. It matters in this fixture and not
hypothetically: **50 of the 783 recorded BTC/USD prices are written `x.0`**, and the other 733
carry a digit. Both are on the declared 1-decimal grid; only the spelling differs.

**Cost.** The number in spec 101's hand measurement — *"783 prices, every one at exactly 1
decimal place"* — is a statement about the spelling, and this criterion's message reports the
grid instead. The block comment beside the criterion states both readings and the 733/50 split
so the two records do not look like a contradiction.

**And it gave the mutation proof its control.** The equivalent arm writes one price as
`75733.60` where the fixture has `75733.6`: a genuinely different byte string, the same grid
point, and the verdict must not move. Under the rejected option that arm would be red, which
is what makes it a control and not decoration.

### Spec 118: the criterion, and the four verdicts it was watched to produce

**Agent:** C · **Task:** spec 118 · **Date:** 2026-09-18

**Fix.** `recorded_book_agrees_with_recorded_pair_decimals`, registered last in phase 6 and
reading `tests/fixtures/book_sample.jsonl` and `tests/fixtures/kraken/asset_pairs.json` and
nothing else. For every pair both fixtures carry, no recorded price may sit off that pair's
declared `pair_decimals` grid. Pairs only one fixture carries are named, counted, and compared
against nothing.

**PASS, verbatim** (`python scripts/verify.py --phase 6`, and the same string from a direct
run against the repository root):

    every recorded price sits at or inside its recorded pair_decimals - BTC/USD 783
    recorded prices, the widest at 1dp, against the recorded pair_decimals 1. Coverage: 1
    compared of the 5 pairs the two fixtures carry between them, 4 not compared - ADA/USD
    (881 recorded prices, recorded in book_sample.jsonl, not declared in
    asset_pairs.json); ETH/BTC (declared in asset_pairs.json, not recorded in
    book_sample.jsonl); ETH/USD (declared in asset_pairs.json, not recorded in
    book_sample.jsonl); SOL/USD (declared in asset_pairs.json, not recorded in
    book_sample.jsonl). Read from the two committed fixtures alone, and no precision is
    inferred from a price. book_sample.jsonl was cut from kraken_v2__msi__2026-09-16.jsonl
    over [2026-09-16T00:17:06.100000Z, 2026-09-16T00:17:36.100000Z).

The archive name and the window are read out of the fixture's own header block rather than
written into `verify.py`, so the criterion's claim about its subject's provenance cannot drift
from the subject.

**PENDING, both of them.** A tree with no `tests/fixtures/` reports *"book_sample.jsonl has
not been deposited yet"*; a tree carrying the book and no recorded `AssetPairs` reports the
same about `asset_pairs.json`. The second is the ADA/USD case at whole-fixture scale — prices
and no declaration — and it must not be a PASS. A deposited but **empty** `asset_pairs.json`
is a FAIL, not a PENDING, the same distinction `_phase6_fixture` already draws for the book.

**The mutation proof.** Four arms, all applied to a **copy** of the two fixtures in a temp
tree and never to the repository's; each anchor asserted to occur exactly once before it was
used; the copy restored from a byte copy taken beforehand; both real fixtures hashed on the
way in and the way out and compared in one statement.

    real book_sample.jsonl  sha256 before and after:
      223aafec0eb3349b09512ac07618ca5717f02559d7f446763ee7ce3a0c8c4ef1
    real asset_pairs.json   sha256 before and after:
      6711d1d720bda594cdbdefa881831bf32e0dd8e0d4eac5730aaad77039351ecb

| Arm | Break | Verdict |
|---|---|---|
| M1 | one recorded BTC/USD price `75732.4` → `75732.45` | **FAIL** |
| M2 | the declaration narrowed, `"pair_decimals": 1` → `0`, book untouched | **FAIL** |
| M3 | the only shared pair renamed out of the declaration (`BTC/USD` → `BTC/USDX`) | **FAIL** |
| C1 | **control** — `75733.6` → `75733.60`: same grid point, different bytes | **PASS** |

M1's FAIL, verbatim and trimmed after the clause that names the figure:

    the recorded book disagrees with the recorded AssetPairs declaration, so the two
    fixtures are not internally consistent - BTC/USD declares pair_decimals 1; off that
    grid: 1 of 783 recorded prices - 1 at 2dp (for instance 75732.45). This is not a
    verdict on Kraken: both sides are committed recordings, and a disagreement means a
    re-cut fixture landed beside a stale declaration. Coverage: 1 compared of the 5 pairs
    ...

**M2 and M3 are the two arms worth having beyond the one the spec names.** M2 breaks the
*declaration* rather than the book, which is the only thing separating this criterion from one
that has a precision written into it: a criterion holding `1` as a constant passes M2. M3
removes the last shared pair, and the answer is a FAIL saying *"no pair is carried by both
fixtures, so this criterion compared nothing"* — without it, a fixture pair that drifted apart
entirely would report a green PASS over zero comparisons, which is the vacuous pass this
project has been burned by three times.

**One more arm, and it is about the message rather than the verdict.** A price rewritten as the
string `"75732.4"` is a FAIL naming the malformed price, not `criterion raised`. This criterion
is the only reader of these two files, so a stack trace from it judges nothing and tells nobody
which file is wrong.

**What the tests hold that the hand proof does not.** `test_the_criterion_reads_the_two_fixtures
_and_nothing_else` wraps `Path.open` and `Path.read_text` for the duration of one run and
asserts the set of paths opened is exactly the two fixtures. The AST sweep earlier in that file
already reads the Phase 6 *source* for a path into `data/`, `models/` or `logs/`; this reads the
*run*, so a third input reached through any helper anywhere in the call graph fails here naming
it. The fabricated tree for these tests carries the two JSON files and nothing else at all —
no `acsoe`, no config — which is itself the assertion.

### Spec 118, addendum: two more arms, and the two branches they were written to execute

**Agent:** C · **Task:** spec 118 · **Date:** 2026-09-18

**What happened.** Re-reading the criterion after the four-arm proof above, two branches had
never executed. Both were written on purpose and both would have read as comments.

**M4 — the shared pair declared with no `pair_decimals` field.** `_recorded_pair_decimals`
returns those pairs separately from the ones it could read, and the message calls them *"its
asset_pairs.json entry carries no pair_decimals"* rather than *"not declared in
asset_pairs.json"*. The distinction is not pedantry: the second sentence sends somebody to add
an entry that is already there. Arm: delete BTC/USD's `"pair_decimals": 1` line from the copied
declaration. Verdict **FAIL**, naming BTC/USD with its 783 prices and that reason, and the
coverage drops to 0 compared of 5.

**M5 — a compared pair whose frames carry no price.** The other arms all break an *agreement*;
this one removes the *evidence*. SOL/USD is declared at 3 decimals and the book carries no
frames for it, so appending one frame with empty `bids` and `asks` puts it in both fixtures
with nothing to measure. Without the guard the criterion would report "no price was off the
grid" about a pair it never looked at — the vacuous pass, per pair rather than per file — and
`max()` over an empty mapping would raise on the way there. Verdict **FAIL**: *"SOL/USD is in
book_sample.jsonl and carries no price at all"*, with BTC/USD still measured and the coverage
now 2 of 5. It is appended rather than substituted because no anchor in the committed book
produces that state: every recorded frame carries levels, which is exactly why the branch was
unexecuted.

**One change to the FAIL text while proving M5.** A FAIL used to list only the breaches. It now
also names the pairs that agreed, because "one pair of two is wrong" and "the fixture is wrong
throughout" are different situations with different responses, and the first FAIL a reader sees
should distinguish them. `tests/verify/test_phase6_criteria.py` now holds six arms for this
criterion, five of them red and one — the trailing zero — the control that must stay green.

### Spec 118: a new criterion is pinned in two places, and only one of them is obvious

**Agent:** C · **Task:** spec 118 · **Date:** 2026-09-18

**What happened.** The first full `pytest tests/verify/` after the criterion landed came back
`1 failed, 442 passed in 626.99s`, and the failure was
`test_runner.py::test_each_phase_registers_its_own_criteria_and_no_others` — not any of the
sixteen tests written for the new criterion, all of which were green.

**Why.** The registry is pinned twice, by two files with different jobs.
`test_phase6_criteria.py` pins Phase 6's criteria **as an ordered list**, because the report is
read top to bottom; `test_runner.py` pins **every phase's set at once**, because a criterion
registered into the wrong phase is silent — it simply never runs, or runs a phase too early.
Updating the first and not the second leaves a red that looks unrelated to what you changed, and
the useful part is that the second is the one that would have caught the real mistake: had I
registered this into phase 7, the phase-6 list test would have gone red saying a name was
missing, and only the runner's `for phase in range(7, MAX_PHASE + 1)` loop would have said where
it went.

**Fix.** Added the name to the Phase 6 set in `test_runner.py` with a comment saying what makes
it unlike its neighbours — its subject is two committed fixtures rather than an engine or the
chain. `tests/verify/test_runner.py` 25 passed. The full suite was then re-run from a clean
start rather than reasoned about, because the earlier 442 was measured against a tree I had
edited while it ran.

**Consequence.** Worth knowing before the next criterion is registered: the two pins are
deliberate, they are not redundant, and a new criterion needs both. Ten minutes of suite per
discovery is the cost of finding it the other way.

### Spec 118: one pair of five is thin coverage — whose question it is, and what it would cost

**Agent:** C · **Task:** spec 118 · **Date:** 2026-09-18 · **Raised by:** the lead, at hand-off

**What happened.** The criterion compares **1 pair of the 5** the two fixtures carry between
them. The message says so, which is what the operator asked for, but a check with one subject is
a thin check and the question of widening it needs an owner rather than a shrug.

**Whose it is.** **Not A's cutter.** `scripts/cut_book_fixture.py`'s own docstring opens with
*"It chooses nothing. Not the pairs, not the window, not where the result goes"* — the pairs
arrive as `--pairs` on the command line, and the seam table records the split as *A cuts, C
deposits and owns*. So widening the fixture is a **re-cut with a longer `--pairs`, run by C**,
and A's code does not change.

**And the archive already holds what it would take.** A read-only sample of
`data/raw/kraken_v2__msi__2026-09-16.jsonl` — the archive this fixture was cut from — carries
frames for ADA/USD, BTC/USD, **ETH/USD**, **SOL/USD**, XRP/USD, ZEC/USD, HYPE/USD, EUR/USD,
USDC/USD and USDT/USD. Two of those, ETH/USD and SOL/USD, are declared in the recorded
`AssetPairs` at 2 and 3 decimals. So coverage could go from **1 of 5 to 3 of 5 with no new
recording and no change to anybody's code** — only a re-cut of the committed fixture.

**ETH/BTC cannot be covered from this archive.** It is not recorded, and it is crypto-quoted,
which invariant 7 disables by default. It would stay in the "declared, not recorded" bucket.

**Why I did not do it, and what it would cost.** Re-cutting changes a committed fixture's
content, which is a what-choice and the operator's. It is also not free: `book_sample.jsonl` is
the subject of `order_book_slippage_on_recorded_book`, which streams ADA/USD first so engine 7
chooses the thin pair and takes BTC/USD as the deep one (`BOOK_THIN_PAIR`, `BOOK_DEEP_PAIR`,
`BOOK_THIN_UNIVERSE`). Two more pairs in the file changes what that drive sees, so the re-cut
and that criterion have to be looked at together — which is an argument for doing it
deliberately rather than as a tidy-up.

**The honest summary for the operator.** Widening is cheap, available today, owned by C, and
needs one ruling: whether a committed recording may be re-cut. Until then the criterion covers
one pair and says which one, which is the behaviour the ADA/USD entry in the tracker asks for —
a tool that reports what it could not do beats one that looks complete.

## Overnight decisions, 2026-09-17

*Verbatim from `docs/build-log/phase-6/overnight-decisions-2026-09-17.md`.*

# Overnight decisions, 2026-09-17 — for the operator's morning review

**Lead.** The operator went to sleep on 2026-09-17 around 03:40 local and authorised
unattended work until they say they are back: finish the phase 0–5 re-gate, commit
registration, run C's criteria bodies, spec 101 and the seed-vocabulary cleanup, and route
the stale-comment items as small specs. The rules: *how* choices may be taken and logged
here; *what* choices (weakening a gate or criterion, a config value/threshold/barrier,
more willing to trade, an invariant or locked decision, a cheaper option that proves less)
stop and wait. **Every decision taken overnight is listed here, with the rejected option and
the case against.** Entries marked **REVIEW** are ones where a competent objection exists.

Do not close the phase: when the nine Phase 6 criteria are green, report and stop.

## Decisions taken

### D1 — Sequence: agents run one at a time, not in parallel

**Took.** B's small items (its unwritten spec 106 records, then spec 108) first, then C's
spec 107 and the spec 100 criteria bodies, then spec 101, then the seed-vocabulary
reconciliation (B, then C). One agent in the tree at a time, a gate and a commit at each
boundary.
**Rejected.** Running B's cleanup and C's criteria bodies concurrently, which would save
time overnight.
**Why.** C's criteria drive the whole chain, including the paper broker B is editing, and
both lanes run mutation sweeps; in a shared checkout a mid-save file or a live mutant in one
lane reads as a FAIL — or worse, a KILL — in the other (`code-standards.md`). The cost is
wall-clock time only.

### D2 — The stale-comment items are two small specs, split by owner

**Took.** Spec 107 (C): engine 9's README and docstring still describing engine 11's
removed fallback; spec 105's criterion still accepting a position with no mark. Spec 108
(B): engine 10's "rejections column" comment; the unused `FALLBACK_PAPER_LEDGER` constant
and the broker comment calling the starting balance a substituted value. C's two minor
findings (the tier-sentence test that never observes PENDING; the four-quote docstring at
`test_phase6_criteria.py:671`) are folded into the spec 100 criteria-body work, since they
are in the same file.
**Rejected.** One cross-lane cleanup spec (ownership rule 6 forbids it), or folding all of
them into spec 100 (it would mix B's lane into C's task).

### D3 — Spec 107's tightening of spec 105: **RESOLVED — accepted by the operator 2026-09-17**

**Ruling (2026-09-17 morning):** accepted. *"The branch is reachable only by a regression of spec 106, and a criterion that silently accepts a regression proves less than it could."* Re-confirmed 2026-09-18 when the lead wrongly listed it as still open; the ruling had been recorded here all along and only the REVIEW tag was left standing.

**Took.** Tighten the criterion so that a fill-tick position with no stored mark is a FAIL,
now that spec 106 makes engine 21 store the fill price as the mark.
**Rejected.** Leaving the NULL-mark branch as it is (accepting a NULL mark when the equity
row valued the position at cost).
**Case against my choice.** It is *stricter*, not weaker, so it is in the "how" bucket by
the operator's rules — but it changes what the criterion accepts, and a stricter criterion
that couples to engine 21's display fields could go red for a reason unrelated to the
double count it exists to catch. The case for: the branch is now reachable only by a
regression of spec 106, and a criterion that silently accepts a regression is proving less
than it could.

### D5 — Spec 100's bodies before spec 101; `console_shows_position_live` PENDINGs on spec 101 meanwhile

**Took.** C writes all nine criterion bodies first, with `console_shows_position_live`
reporting PENDING naming spec 101 until the console shows the position; spec 101 follows as
its own boundary.
**Rejected.** Building spec 101 first so every criterion can reach PASS in one pass.
**Why.** Eight of the nine criteria are about the engines and the broker and need nothing from
the console; doing them first gets the most evidence soonest, and a PENDING that names its
missing subject is the criteria framework's normal shape. Order only.

### D6 — Spec 105's criterion switches to the registered `bootstrap` chains

**Took.** Now that spec 82 has landed, `paper_equity_continuous_across_fill` reads
`build_chains()` instead of its hand-built registry-order list, in the same work as the
other criteria.
**Rejected.** Keeping the hand-built chains, which are independent of registration.
**Why.** Its own docstring says to switch; a criterion that builds its own chains can pass
while the registry is wrong, which is the Phase 2 tripwire lesson ("reach X through the code
path X lives on"). Mechanism only; the assertion is unchanged.

### D7 — More stale fallback prose, routed as specs 109 (A) and 110 (B), scheduled last

**Took.** B found the same pre-ruling wording in A's lane (the Kraken client README and engine
1's README, contracts, engine and test) and in B's `clients/store/client.py`. Two prose-only
specs, one per owner, run after the seed-vocabulary reconciliation.
**Rejected.** Folding them into spec 108 (A's lane is not B's), or running them now, alongside
C's criteria work (D1: one agent in the tree at a time).
**Why.** They change no behaviour and block nothing; C's criteria are the work the operator
asked for tonight.

### D8 — `escalation_completes_during_outage` fails the balance by failing `AssetPairs` too: **RESOLVED — accepted by the operator 2026-09-17**

**Ruling (2026-09-17 morning):** accepted — strictly harder, it exercises invariant 14's retained-cache override as well, and the message names both failures so a pass cannot hide which path carried it. Re-confirmed 2026-09-18, same correction as D3.

**Took (C's proposal, accepted).** In paper mode the broker never calls the real `Balance`,
so failing that call alone changes nothing. C fails `AssetPairs` as well; the broker's
`balance()` then raises `KrakenUnavailableError`, engine 1 records `balance` as a failed
fetch, and engine 22 must liquidate on the **retained** `AssetPairs` (invariant 14),
recording `asset_pairs_last_known_good`.
**Rejected.** A balance-only failure (for example the fee tier absent while a fill is due,
spec 103's path) — C is to record whether it is achievable and why it was not used.
**Case against.** The Phase 6 row says "the balance fetch is still failing"; this subject
fails more than that, so a pass also depends on the retained-cache path working. The case
for: it is a strictly harder condition that exercises invariant 14's other override too, and
the criterion's message names both failures, so nothing is hidden.

### D9 — The escalation criterion must prove the resting-entry cancel non-trivially

**Took.** At the committed config a resting entry is always cancelled by its unfilled window
(300 s) long before `safety` can escalate (more than 15 one-minute blocked ticks), so on the
escalation tick `entry_orders_cancelled` is true trivially. Asserting only that would prove
nothing about engine 21's `close_intent` cancel. The criterion therefore **also** cancels a
real resting entry under `close_intent` — an operator `close_all` issued well inside the
entry's window, with `data_guard` blocking and the balance failing — and asserts the cancel
happened because of `close_intent`. Its message states that a `safety` escalation can never
find a resting entry at this config.
**Rejected.** Asserting the flag alone (cheaper, proves less — the operator's stop bucket,
so not an option); or changing `entry_unfilled_window_s` in the subject so a resting entry
survives to the escalation (a config value — the stop bucket).

## Findings

### F1 — `safety`'s resting-entry escalation precondition is unreachable at the committed config

Found by C while planning the criteria bodies, read-only. `trading.entry_unfilled_window_s`
(300) is shorter than `safety.max_consecutive_data_blocks` (15) × `timeframes.loop_tick_s`
(60), and invariant 8 cancels a stale entry even during a `data_guard` hold, so no resting
entry is still on the book when `safety` escalates. Engine 11 also refuses a resting entry on a
pair that already holds a position (spec 89), and engine 7 does not skip such a pair. Nothing
is wrong — the window makes the system safer — but invariant 14's "or resting entry orders"
clause is only reachable through the operator's own Close all. See Q2.

## Events

### E1 — The network was down 03:13–08:20 UTC; the session stalled with it

The recorder's heartbeat (`data/raw/heartbeat__msi__2026-09-17.ndjson`) reports
`connected: false` for 308 consecutive minutes, 03:13Z to 08:20Z, and reconnected on its own;
both recorders and both supervisors are still running. **That span of order-book and spread
history is lost and cannot be recovered** (the recorder marks it; the archive is not edited).
The lead's session could not reach the model for the same span, so nothing progressed
overnight between the re-gate finishing and 09:21 local. The re-gate itself ran locally and
completed: phases 0–6 each fail only `toolchain_green`, on spec 100's known eight.

### D4 — Registration committed on the re-gate that measured it, with a docs-only delta after: **REVIEW**

**Took.** Commit `bootstrap.py` on the gate that ran against it (phases 0–6, logs
`logs/verify/phase6-20260917-registered-lead-*`). After that gate, only documentation changed:
B's two record files (written while the gate ran, on the lead's instruction), the two new
specs, this log, and the tracker follow-ups. For that delta, the lead re-ran the one criterion
that reads those documents, `docs_vocabulary`, and the `tests/verify` tests that parse
`context/*.md`, immediately before the commit.
**Rejected.** A second full re-gate (roughly three hours for phases 0–6, since every phase
re-runs the whole suite) before the commit.
**Case against my choice.** The operator's rule is one authoritative gate immediately before
the commit, and this is not literally that. The case for: no source, test or config byte
changed after the gate started (checked with `git diff --stat`), so a second run would
re-measure identical code; the docs delta is covered by the check that reads it. Cheaper,
but not because it proves less about anything that changed.

## Open questions for the operator — not decided overnight

### Q1 — `CostAssessment.fallbacks_used` has no producer and no reader

Spec 108 (B) found that engine 10's payload field `fallbacks_used` is always empty (no
fee-tier fallback exists since spec 37) and that nothing in `src/` reads it — the column of
that name is on `trades`, not `rejections`. Spec 106 removed the same field from engine 11
on exactly those grounds. **Not removed here**, because removing it changes engine 10's
published shape, which is a "what" choice.
**Options.** (a) Remove it, as engine 11's was — consistent, and an always-empty field reads
as "no fallback fired" on a record that cannot record one. (b) Keep it as a reserved,
always-empty field. **Recommendation: (a).** **Case against:** engine 22 still publishes a
real `fallbacks_used` (for rule 14's liquidation), so a uniform "every money-deciding engine
carries the field" convention has some value for readers of the payloads.

### Q2 — Is F1 acceptable as it stands?

**Options.** (a) Accept: the window cancel covers the hazard invariant 14's clause was written
for, and the operator's Close all is the path that still exercises a `close_intent` cancel of
a resting entry. (b) Record the relationship between `entry_unfilled_window_s` and
`max_consecutive_data_blocks × loop_tick_s` as a config-validation rule, so a future change to
either value cannot silently make the clause reachable-but-untested. **Recommendation: (a),
plus a one-line note in invariant 14.** **Case against:** (b) turns an accident of two
defaults into an enforced property, which is the kind of coupling nobody decided on — the
same objection `code-standards.md` makes to adding a constraint by default.

## The operator's rulings, 2026-09-17 morning

D1, D2, D5, D7: correctly in the "how" bucket — calibrated; do not escalate more. D3: accepted.
D4: accepted and made a standing rule in `code-standards.md`. D6: "the best call in the log" — keep
the instinct. D8: accepted. D9: right call; "an assertion that is true trivially is not an assertion."
Q1: remove the field (spec 111); engine 22's stays. Q2: a third option — a test asserting the
window/escalation relationship from config, commented as the notice that the clause has become
reachable (spec 112), plus a one-line pointer in invariant 14. F1's engine 7 half: a Phase 7 item.
E1: Known Risks. The operator is back; normal rhythm resumes.

## Overnight decisions, 2026-09-18

*Verbatim from `docs/build-log/phase-6/overnight-decisions-2026-09-18.md`.*

# Overnight decisions, 2026-09-18 — for the operator's morning review

**Lead.** The operator went to sleep at ~02:50 local on 2026-09-18 and authorised unattended work
until they say they are back. Order given: the nine criteria green (**already done**, `e3b5406`),
then the seed-vocabulary cleanup, then spec 109, then spec 118, then the `cash_source` default
removal. **Do not close the phase.**

Rules: *how* choices (naming, placement, test structure, equivalent mechanisms, order) are taken
and logged here with the option rejected; *what* choices (weakening a gate or criterion, a config
value/threshold/barrier, more willing to trade, an invariant or locked decision, a cheaper option
that proves less) **stop and wait**, as does anything costing more than about three hours. Unsure
= the second bucket. Entries marked **REVIEW** are ones where a competent objection exists.

**Nothing is carried forward unreviewed.** The lead wrongly listed D3 and D8 of 2026-09-17 as
still open, in Handoff 7 and in the first draft of this file: **both were accepted by the operator
on the morning of 2026-09-17** and the acceptance was recorded in that file's rulings section the
whole time. Only the `**REVIEW**` tags on the entries themselves were left standing, and a tag is
what a reader scanning for open items sees. **The lesson, and it is the same shape this phase keeps
finding: a record is not resolved because the resolution exists somewhere in the same file — the
marker has to move.** Both entries now carry their ruling and its date inline.

## Decisions taken

### E1 — The night's starting state

`e3b5406` pushed: 13 criteria, 13 PASS, 0 FAIL, 0 PENDING; the first complete paper trade runs end
to end. Handoff 7 is written for a session that has read only the documents. Nothing was in flight
and every agent was stopped when the night's work began.

### D1 — The seed-vocabulary cleanup is two specs, B then C, in that order

**Took.** Spec 119 (B): every seeded `rejections` row is repointed to an `(engine, code)` pair the
live system can actually emit. Spec 120 (C): the `REASON_PROSE` entries that no longer have a
producer are retired, **after** B's half lands.
**Rejected.** One spec, or C first. The tracker's own ruling fixes the order for a reason that
still holds: **every code stays mapped until B's half lands**, because the seeded rows exist and
the console must render them — a code absent from the map renders "No reason was recorded."
silently. C first would put that silence on screen for the length of one commit.

## Open questions for the operator — NOT decided overnight

### Q1 — Invariant 14 grants engines 21 and 22 a retained balance that neither reads

**Found by A during spec 109** (prose work), by reading rather than grepping, and **verified by the
lead in the code**:

- Invariant 14 says *"During a liquidation, engines 21 and 22 may use the last known good balances
  and the cached `AssetPairs` metadata past its TTL."*
- **Engine 22 reads only `last_known_good_asset_pairs`** (`engines/exit/engine.py:523`), and its
  `contracts.py:159` records *"there is deliberately no `balance_last_known_good` beside it"*,
  although spec 93 named one.
- **Engine 21 reads neither** — `last_known_good` does not occur in that package.
- **So `last_known_good_balances` has no reader in `src/` at all.** The client retains it, engine 1
  publishes its *age*, and nothing reads its value.

**There is a decision behind the engine's half** — B recorded the deviation from spec 93 in its
build log and progress file on 2026-09-16 and marked it escalated to the lead. What never happened
is the invariant moving to match, and A's README was never told either. So this is not drift with
no decision; it is a decision that stopped one file short of the document that authorises it.

**Why it is more than wording.** Invariant 2 justifies retaining the balance at all as *"a
requirement on Agent A's client, not an optimisation"*, on the ground that discarding it would make
rule 14 unimplementable at the moment it is needed. That premise holds for `AssetPairs` and, as
built, does not hold for the balance.

**Options.**
(a) **Amend invariant 14 to match the code**: a liquidation uses the retained `AssetPairs` and does
not need a balance, because engine 22 sells what the store says is open and never sizes against
cash. Then either drop the retention of balances or restate why it is kept (engine 1 publishing its
age is a real reader of the *timestamp*, not of the value).
(b) **Change engine 22 to use the retained balance**, honouring spec 93 as written.
(c) Leave both and record the divergence.

**Recommendation: (a).** Engine 22's reasoning is sound — a liquidation sells positions the store
records, and a balance it cannot trust would only be a second opinion about what to sell. **Case
against (a):** it narrows an invariant to fit what was built, which is the direction that needs the
most scepticism; if a future exit path ever does need cash (a quote-currency sweep, say), the
invariant will no longer authorise the retention it depends on.

**Not touched.** A left the prose unwritten rather than choose which correct fact to state, which
was right: writing either sentence would have answered the question.

### Q2 — The two fixtures spec 118 compares are not "frozen together", which was the ruling's own premise

**Found by C during spec 118, and it corrects the operator's stated rationale.** The ruling said a
red can never be news about Kraken **because both sides are recordings frozen together**. They are
not: `tests/fixtures/kraken/asset_pairs.json` landed in `afaf2f5` on **2026-09-08**, and
`tests/fixtures/book_sample.jsonl` was cut from the 2026-09-16 archive and landed in `a089bc7` on
**2026-09-16**. The `AssetPairs` recording carries **no provenance block**, so nothing in the
repository dates it except its commit.

**The conclusion still holds for today's files** — the two agree, and BTC/USD's declaration matches
783 recorded prices — but the *argument* does not: a red could mean a re-cut fixture beside a stale
declaration **or** a setting Kraken changed between the 8th and the 16th. C kept the check, stated
both dates in the criterion's prose, and wrote that a red means the two recordings disagree and
wants a human either way. **Aligning them is a what-choice, so C stopped.**

**Options.** (a) Leave it: the check is honest and its prose no longer over-claims. (b) Re-record
`asset_pairs.json` from the same archive day as the book sample, so the premise becomes true and a
red really can only mean an inconsistent re-cut. (c) Give `asset_pairs.json` a provenance block so
its date is readable from the file rather than from git. **Recommendation: (c) then (b) when a
recording is next cut** — provenance is cheap and makes the gap visible; re-recording is a change
to committed evidence other criteria read. **Case against:** (b) touches a fixture the Phase 2
candle criterion also reads, so it is not free.

### Q3 — Spec 118 compares 1 pair of 5, and widening it is C's re-cut, not A's cutter

Coverage is **1 compared (BTC/USD), 4 not** — ADA/USD is recorded but undeclared; ETH/BTC, ETH/USD
and SOL/USD are declared but not in the book sample. **Owner, since the operator asked for one:**
not A. `scripts/cut_book_fixture.py` "chooses nothing. Not the pairs, not the window" — pairs
arrive as `--pairs`, so widening is a **re-cut run by C**, with no change in A's lane. C checked the
archive read-only: `data/raw/kraken_v2__msi__2026-09-16.jsonl` already carries **ETH/USD and
SOL/USD**, both declared, so coverage could go **1 of 5 → 3 of 5 with no new recording and no code
change**. ETH/BTC is absent from the archive and is crypto-quoted (invariant 7), so it stays
uncomparable. **The cost, and why it is not a tidy-up:** `order_book_slippage_on_recorded_book`
drives this same fixture, picking ADA/USD as the thin book and BTC/USD as the deep one, so a re-cut
and that criterion have to be looked at together. **Operator's ruling; owner named.**

### F1 — An invented ADA/USD `pair_decimals` sits two screens from the criterion about declarations

`BOOK_THIN_PAIR_RULE` in `scripts/verify.py` carries six decimals for ADA/USD, labelled "Invented
exchange data for the fake" in its own comment. **Not a defect** — the fake client needs a rule, and
inventing one for a fake is legitimate where inventing one for a *declaration* is not. It is
recorded because ADA/USD's recorded prices stop at six places, so it would have "worked" as a
declaration, and it sits ~2,200 lines from a criterion whose whole subject is declarations. The new
criterion's docstring names it as the thing it must not read.

## Overnight decisions, night of 2026-09-18

*Verbatim from `docs/build-log/phase-6/overnight-decisions-2026-09-18-night.md`.*

# Overnight decisions, night of 2026-09-18 — for the operator's morning review

**Lead.** The operator ruled on Q1–Q4 of `overnight-decisions-2026-09-18.md`, ordered the close
preparation (re-gate phases 0–6, consolidate `docs/build-log/phase-6.md`, merge progress files,
create `docs/build-log/phase-7/`, record two FINDINGS), and went to sleep for roughly five hours.
**Do not mark Phase 6 green, do not close it, do not start Phase 7, do not start Q3's re-cut.**

This is the **one running list** of every decision taken while the operator is asleep. The buckets
are the operator's: *how* choices are taken and logged with the option rejected; anything that
changes what the system does or what a number means, weakens a gate or criterion, touches a config
value, threshold or barrier, needs an invariant or locked decision amended, or costs more than ~3
hours **stops**. Unsure = stop. Entries marked **REVIEW** are ones where a competent objection
exists.

`docs/build-log/` is read by no check (every hit in `scripts/verify.py`, `tests/` and `src/` is a
comment), so this file is written as the work happens, including while the gate runs.

## The gates

Phases 0 to 6 re-gated in order at `98c0485`, 09:04–12:44Z, `mypy --strict src/ scripts/` (153
files) and `ruff check src/ tests/ scripts/` clean first. **Every phase exit 0**: phase 0 7/7, 1
10/10, 2 9/9, 3 9/9, 4 10/10, 5 14/14, 6 14/14, each `toolchain_green` at `3314 passed, 2
skipped`. HEAD identical before and after, and `git diff --stat HEAD -- src tests scripts config
db` empty at both ends (`logs/verify/regate-20260918-close-prep-lead-summary.txt`). The documents
tonight (tracker, `phase-6.md`, HANDOFF 9, this file, the walk-through, `phase-7/`) are the
docs-only delta on top, checked by `docs_vocabulary` and `tests/verify/test_docs_vocabulary.py`.

## STOPPED — waiting on the operator

### S1 — Q1: engine 22 reading the retained balance changes its behaviour, so the condition fired

**The ruling:** do not amend invariant 14; change engine 22 to read the retained balance —
*"if reading the retained balance changes engine 22's behaviour in any way, stop and tell me."*

**Invariant 14 is not amended.** That half of the ruling needs no code and is done by not doing it.

**The engine change stopped, because there is no way to read the value that leaves behaviour
unchanged.** Checked in the code, not in the contract comment:

1. **The only decision a balance could inform in engine 22 is the sell quantity** — capping it at
   the account's base holding. Engine 22 sizes an exit from the `positions` row
   (`engines/exit/contracts.py:159-166`, B's recorded deviation from spec 93).
2. **In paper mode that cap sells nothing.** The paper ledger is quote-side only by rule:
   `clients/paper/fills.py:196` — *"Only the quote currency moves. A buy is not credited with
   base."* Every paper position's base balance is zero, so a capped liquidation rounds every
   position to zero, `positions_closed` never becomes true, and `close_intent` never clears — the
   kill switch would retry forever and close nothing.
3. **And the retained balance in paper mode is not the paper account at all.**
   `PaperBroker.last_known_good_balances` (`clients/paper/broker.py:262`) forwards to the *real*
   Kraken client's retained `Balance` — the real exchange account's last answer, or `None` on a
   fresh clone whose private calls fail. `PaperBroker.balance()` never makes the real call
   (docstring, lines 383-386), so the real client retains nothing in paper unless something else
   calls `Balance`. The paper ledger is never retained anywhere.
4. **Reading it without acting on it** would either be dead code (a read whose value decides
   nothing), or would add `balance_last_known_good` to `fallbacks_used` on the trade — a record
   that a fallback informed an exit it did not inform. That is the shape the operator removed from
   `CostAssessment.fallbacks_used` on 2026-09-17: *"a claim that looks true and means nothing."*
   Either way it changes what the trade record says.

**Options.**
- **(a) Leave engine 22 as built, and record that the authorisation is deliberately wider than the
  implementation.** Invariant 14 keeps the balance authorised (as ruled); engine 22's contract
  comment moves from "escalated to the lead rather than decided here" to "ruled 2026-09-18: the
  invariant keeps the authorisation; no current exit path reads it, because…" (B's lane, prose).
  No behaviour changes.
- **(b) Give engine 22 a real use for the balance in live mode only** — cap a liquidation at the
  exchange's reported base holding, so a store that over-states a position cannot produce a sell
  the exchange rejects. Needs either a mode branch in an engine (forbidden: mode differences live
  in the client layer) or a paper broker whose retained balance reports a base leg (overturns the
  quote-side ledger ruling of spec 88 and the double-representation argument in `fills.py`).
  Changes what the system does; multi-lane; likely over three hours.
- **(c) Make the paper broker retain its own ledger** as `last_known_good_balances`, so the
  retained value is at least the right account in paper. Changes a client's behaviour and still
  gives engine 22 nothing to do with it.

**Recommendation: (a).** It honours the half of the ruling that carries the reasoning — the
authorisation stays wide, so an exit path that one day needs cash (a quote-currency sweep) finds
it still authorised — without inventing a use for the value today.
**Case against (a):** it leaves an authorised, retained value that **no consumer reads**, so
nothing tests that it is *correct*, only that it is kept; the first real reader will inherit a
value no test has ever checked from the consumer's side. And it leaves item 3 in place: in paper
mode the retained balance describes the wrong account, which is a trap for exactly the future
exit path (a) is meant to protect. If (a) is taken, item 3 should be written into invariant 2's
retention paragraph so the future reader meets it.

### S2 — Q2: `asset_pairs.json` was never cut from an archive; it is invented test data

**The ruling:** add a provenance block to `tests/fixtures/kraken/asset_pairs.json` *"naming the
archive and the date it was cut from"*; re-record both fixtures together at the next cut.

**There is no archive to name.** Checked:

- `git log --follow` shows **one** commit touching the file: `afaf2f5`, 2026-09-08 17:24, the
  Phase 0 harness commit (spec 15), alongside `tests/harness/fake_kraken.py`.
- That harness's module docstring, lines 8-22: *"The numbers in `tests/fixtures/kraken/*.json` are
  **invented test data for a fake exchange**. They are not Kraken's fee schedule, minimums, tick
  sizes or precisions … The *shape of the result body* is a simplified one owned by this harness …
  A replaces these with genuine redacted recordings in Phase 2."* **The replacement never
  happened** — no later commit touches the file.
- The recorder archive is WebSocket v2 JSONL; `AssetPairs` is a REST call. No file under
  `tests/fixtures/` other than this one carries `pair_decimals`.

**So the finding is wider than Q2, and it is a *what*:**

1. **Spec 118's criterion compares a real recording against an invented declaration.** It is named
   `recorded_book_agrees_with_recorded_pair_decimals`, and its prose (`scripts/verify.py` ~13885-
   13905) calls the file *"the recorded `AssetPairs`"* and says a red means *"these two recordings
   disagree"*. One of them is not a recording. BTC/USD's `pair_decimals: 1` agreeing with 783
   recorded prices is an agreement between the exchange and a value somebody in this project typed
   in Phase 0 — the exact thing the criterion's own docstring says it must not rest on when it
   warns against `BOOK_THIN_PAIR_RULE`.
2. **The Phase 2 candle criterion's tolerance is the same invented file.** The Phase 2 row reads
   *"every OHLC field within one `tick_size` for that pair as reported by `AssetPairs`"*, and
   `scripts/verify.py:3726` reads the tolerance from `asset_pairs.json`. That tolerance is typed,
   not reported.
3. **Q3's "1 pair of 5" is coverage against that invented declaration**, so widening it by a
   re-cut of the book alone would widen a comparison whose other side is still invented.

**Not done:** no provenance block written. A block naming an archive would be a fabricated
provenance; a truthful block ("hand-authored for the Phase 0 fake, spec 15, 2026-09-08, not a
recording") contradicts the ruling's content and changes what spec 118's PASS is understood to
mean — both are the operator's.

**Options.**
- **(a) Truthful provenance block now** ("invented for the Phase 0 fake, 2026-09-08, spec 15; not a
  recording"), and spec 118's criterion re-worded to say it compares against the fake's
  declaration — honest, cheap, and it states plainly that the criterion proves less than its name.
- **(b) Record a genuine `AssetPairs` response** (public endpoint, no key) into a **new** fixture on
  the day the book is next cut, and point spec 118 (and, if ruled, Phase 2's tolerance) at it,
  leaving `asset_pairs.json` as the fake's invented data. This is what makes the ruling's premise
  true. Needs the network at cut time; costs a re-cut C runs and a criterion change.
- **(c) Replace `asset_pairs.json` itself with a recording.** Rejected by the lead as an option to
  recommend: the fake client serves this file to hundreds of tests, so changing its values moves
  every test built on the fake exchange at once.

**Recommendation: (a) now, (b) with Q3's re-cut.** **Case against:** (a) re-words a criterion,
which the operator may regard as weakening it; the alternative reading is that it is the opposite —
it stops the criterion's name claiming a recording it does not have. Either way it is a ruling.

### S3 — Every Phase 6 criterion's tier sentence quotes friction the run did not compute (found building the Q4 walk-through)

**What happened.** The walk-through reads one target round trip's rows (the criterion's own drive,
database kept). Engine 10's payload on the entry tick: `friction_pct` **0.003078783581501615…**
(0.308%), `hurdle_pct` **0.004618175372252422…** (0.462%), `net_edge_pct` 0.0269. Every Phase 6
criterion's PASS message ends *"at fee tier 3, reference friction about 0.65% round trip and a
hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers"*.

**Why.** `tests/harness/fake_kraken.py:235-249` — `tier_sentence` is a fixed string that quotes the
**invariant's reference values** (invariant 5: tier 3 maker 0.22% / taker 0.38%), "not computed
here". The fake's tier 3 in `tests/fixtures/kraken/fee_tiers.json` is **maker 0.0011, taker
0.0019** — invented test data, as its own `_comment` says — so fees alone are 0.30%, not ~0.60%.

**The consequence that matters more than the number.** The clause *"tier 1 is a no-trade regime"*
is true at the invariant's reference tier 1 (maker 0.40%, taker 0.80% → friction ≈1.25% → the
expected move must exceed 2.5 × friction ≈ 3.125% > the 3.0% target). **It is not true of the
harness's own tier 1** (`fee_tiers.json`: maker 0.0025, taker 0.0045 → fees 0.70%, friction ≈0.71%
with this spread → bar ≈1.77% < 3.0%). So the sentence every Phase 6 PASS carries to explain *why
the criteria run at tier 3* describes Kraken's reference schedule, not the fees the criteria were
run at. The Phase 6 headline "tier 1 is a no-trade regime" (tracker, Current Phase, item 1) rests on
the invariant's reference figures, which the invariant itself says are "for sanity-checking only";
the criteria neither measure nor test it.

**What it does not change.** Engine 10's arithmetic is right on the numbers it was given; no gate
is affected; the round trip reconciles to the last digit. This is a criterion *message* claiming
something its run did not show — exactly the difference between an assertion and the rows the
operator asked to see in Q4.

**Not fixed — a what.** Re-wording every criterion's message, or changing the fake's tier values,
changes what a PASS says or what a fixture means. **Options:** (a) make `tier_sentence` state the
fees the fake actually served and the friction/hurdle engine 10 actually published (computed from
the run, not quoted); (b) keep the quoted reference sentence but prefix it "Kraken's reference
schedule, not this run's fees:"; (c) align `fee_tiers.json`'s tier 1 and tier 3 to the invariant's
reference values so the sentence becomes true — rejected by the lead as a recommendation: it
chooses fee values for a fake to make a sentence true, and every trade-driving criterion's numbers
move. **Recommendation: (a).** **Case against:** it touches `scripts/verify.py` (C's lane) and every
Phase 6 criterion's message at once, and the tracker's item 1 would then need re-wording too.

## Findings recorded tonight — reported, nothing changed

Stale prose or an absent record, with no decision entry behind it, is a finding and is reported
rather than silently corrected (standing rule, 2026-09-17/18). None of these is in the lead's lane
to fix, and none of them blocks the close preparation.

### F-new-1 — An approved trade leaves no record of why it was approved

Found building the Q4 walk-through. The round trip's database holds `orders`, `positions`,
`trades` and `equity_snapshots`, but **no row carries the candidate or any gate's verdict**, and no
row carries the economics that approved the entry. `rejections` is the only table with
`expected_move_pct`, `friction_pct`, `net_edge_pct` and `hurdle_pct`
(`engines/memory/contracts.py:185-194`, `ECONOMICS_FIELDS`, "harvested from whichever engine
blocked"), and it is written only for a refusal. `trades` has none of the four, and nothing writes
a SHAP or decision row for an approval. So the counterfactual dataset records *why not* for every
refusal and **nothing about why** for every trade, and project-overview success criterion 2 —
"every trade and every rejection is logged with a machine-readable reason" — is met for rejections
and, for trades, only in the sense that `outcome` is a reason for the *exit*. **A schema and
engine-19 change, so an operator question**, most likely for Phase 7's attribution work, which is
the first reader that would need it.

### F-new-2 — `orders.cycle_id` and `positions.cycle_id` record the last tick that wrote the row

The entry order was placed on cycle 2 and is stored with `cycle_id` **3**; the position was opened on
cycle 3 and is stored with `cycle_id` **7**. Engine 19 upserts these rows (`WRITTEN_TABLES`
comment, same file), so `cycle_id` is overwritten by every later tick. `placed_at` and `opened_at`
still answer "when", so nothing is lost, but `engine-contracts.md` says `cycle_id` "joins logs,
decisions and SHAP rows together with `context.run_id`", and a join from an order to the tick that
placed it by `cycle_id` would land on the wrong tick. Observation for the operator; not a defect in
any criterion, and not changed.

### F-new-3 — The console's sentence for `exits_placed` describes a behaviour the system does not have

`src/acsoe/console/format.py:411`: `"exits_placed": "Exit orders are resting at the exchange for
this position"`. Every Phase 6 exit is a **market sell** that fills on the tick it is placed (engine
22's docstring, "Every exit is a taker, in Phase 6, and that is a recorded choice"); nothing rests.
B noted it in `context/progress/b-store.md:599-602` on 2026-09-16 and it was never picked up. C's
lane; operator-facing prose; reported, not edited. The neighbouring `nothing_to_exit` ("No position
reached a barrier **on this bar**") is also looser than the code — engine 22 runs every minute tick,
not every bar.

### F-new-4 — `docs/PROJECT-STATE.md` is a 2026-09-12 snapshot nothing keeps true

Last touched `ef8f1f0` (2026-09-12). It still lists `fallbacks_used` on engines 10 and 11
(lines ~1001-1002; spec 111 removed engine 10's, spec 106 engine 11's). `docs_vocabulary` scans
`AGENTS.md`, `README.md` and `context/*.md` only, so nothing notices. **Options:** retire it with a
banner naming its date, or add it to the scan — the operator's call; recorded here so a
dissertation reader does not take it as current.

### Checked and discarded

- **`context/progress-tracker.md:1554`** ("Paper mode falls back to tier 1 on a failed fee fetch")
  is unstruck, but it sits inside `## Decision history`, the section whose job is to record
  superseded decisions (`ai-workflow-rules.md`, retired vocabulary). Not a defect.

## Decisions taken

### D1 — The order of the night: code-touching items first, then the gate, then docs

**Took.** Q1 and Q2 investigated before the re-gate (both would have changed bytes the gate must
see), then the six-phase re-gate on a quiet tree, with every docs-only item drafted during it and
landed after it with the proving diff (`code-standards.md`, "When a gate must be re-run").
**Rejected.** Gate first and code after — it would have gated a tree that was about to change and
forced a second 3.5-hour gate.

### D3 — The walk-through reads the criterion's own drive, with the database kept, not a new drive

**Took.** A scratch script (outside the repository) imports `scripts/verify.py` and calls
`_round_trip(ctx, "target")` unchanged, patching two things in its own process only:
`tempfile.TemporaryDirectory` (so the drive's SQLite file survives) and `Drive.tick` (so every
tick's published `state` is kept beside the rows). The run's PASS message is identical, digit for
digit, to the gate's `paper_trade_round_trip_target` line (entry `1690626088`, realised
`91.095749761399263`). A second scratch run adds **one tick after the exit** — the criterion stops
on the exit tick, so without it there is no "after" equity row — calling the criterion's own
helpers in the criterion's own order and only then ticking once more.
**Rejected.** (1) Reading a trade out of `data/db/acsoe.sqlite`: no daemon has traded, so there is
none. (2) Writing a new drive: it would be a second description of the trade beside the one the
gate judges, which is the thing Q4 exists to avoid. (3) Changing `verify.py` to keep its database:
a code change for a report.
**Target leg, not stop or timeout:** the operator asked for one trade; target is the leg where the
exit is caused by a traded price rather than by the clock, and the stop leg differs only in which
barrier the planted trade crosses.

### D4 — The "after" drive ran while the gate's Phase 0 pytest was running

**Took.** Ran it concurrently: 32 logical processors, 63 GB free, the gate's pytest is one process,
and the drive is one short single-process run writing only to the scratchpad — no byte of the tree.
**Rejected.** Waiting ~3.5 hours for the gate to finish. **Stated rather than hidden** because
`toolchain_green` has a timeout and contention is the one way a concurrent run could touch it; the
Phase 0 pytest duration is in its log for comparison against the ~1790 s measured earlier today.
**Measured:** `3314 passed, 2 skipped, 2 warnings in 1794.08s` against `1786.75s` in the gate of
`98c0485` — 7 s slower, 0.4%, inside run-to-run noise. The overlap did not measurably touch it.

### D5 — The walk-through lives at `docs/build-log/phase-6/first-paper-trade.md`

**Took.** Beside the per-agent logs, so the phase consolidation carries it. **Rejected.** `docs/`
root or `tests/fixtures/`: it is a narrative record of one run, not evidence a criterion reads.

### D6 — `docs/build-log/phase-7/` holds four zero-byte files

**Took.** `lead.md`, `a-platform.md`, `b-store.md`, `c-interface.md`, the four names every earlier
phase's directory uses, each **empty**, exactly as ordered. **Rejected.** A title line in each
(`# Build log — Phase 7 — <agent>`): harmless, but a file with a heading reads as a started log,
and Phase 7 has not started. Empty is the true state. Git tracks empty files, so the directory
survives the commit.

### D7 — The merge reports the teammates' stale status lines; it does not edit them

**Took.** The merge section in the tracker states every spec's real state with its commit hash,
and **lists** the stale "not committed", "CLAIMED" and "IN PROGRESS" lines in each teammate's
progress file by line number. **Rejected.** Correcting those lines in place: `AGENTS.md` and
`ownership.md` rule 3 make `context/progress/<agent>.md` the agent's own file, and the lead writes
the tracker. The cost, stated: the teammate files stay wrong until each agent moves its own markers,
which the merge asks them to do at the start of Phase 7. **REVIEW** — a competent objection is that
leaving a known-wrong status line in place, for the sake of a lane rule, is how the D3/D8 marker
survived on the night of the 17th. The difference is that tonight's marker is *moved* in the file
that has authority over state (the tracker), and the stale copies are enumerated there rather than
left to be found.

### D8 — The extraction of the progress files was delegated to one read-only agent

**Took.** One general-purpose agent, read-only, to read ~7,000 lines of progress files and report
specs, stale markers and open items with line citations. **Every claim that reached a document was
then re-checked by the lead** (seven commit hashes against `git log`; the CRLF count in Python; the
tautology's line numbers; three cited passages), and **one claim was discarded**: the agent's "extra"
stale line at `progress-tracker.md:1554` sits in `## Decision history`, where naming a superseded
decision is the section's job. **Rejected.** Reading all three files in the lead's own context — the
same result at the cost of the context the rest of the night needs.

### D9 — One commit after the gate, not a docs-only commit while it runs

**Took.** Everything tonight lands in one commit once the six gates have finished, then the tracker
and handoff (which quote the gate results) as the docs-only delta the rule allows, proven by the
diff stat over `src tests scripts config db` being empty against the gated HEAD.
**Rejected.** Committing the walk-through and this list mid-gate so they are pushed sooner: no byte
the gate reads would change, but HEAD would move under a gate whose summary records HEAD before and
after, and a reader should never have to reason about whether the tree moved. The cost is that the
night's documents exist only on disk for ~3.5 hours; they are docs, and the session is attended by
nothing that could delete them.

**The tracker edits were built and checked before the gate finished, on a copy.** A script applies
every insertion to a scratchpad copy with each anchor asserted to occur exactly once; the real
`check_docs_vocabulary` was run on a copied tree carrying it (PASS, 14 files, 12 terms), and **proven
able to fail on the new text**: `two-chain` injected into the new rulings section went red at
`progress-tracker.md:68`, restored PASS. So the new section is inside the scanned region, not in an
excluded one.

### D2 — This file, rather than appending to `overnight-decisions-2026-09-18.md`

**Took.** A new file for this night. **Rejected.** Appending to the earlier file of the same date:
that file is the record of the previous night and now carries the operator's rulings on it; mixing
a second night into it would make "which night decided this" a reading exercise.

## The first paper trade, read from the database

*Verbatim from `docs/build-log/phase-6/first-paper-trade.md`.*

# The first paper trade, read from the database

**Lead, 2026-09-18, for the operator (Q4 of `overnight-decisions-2026-09-18.md`, ruled: "the
database walk-through").** One complete trade, in plain prose, with every number read from the
rows engine 19 wrote. Where a number is **not** in the database, that is said at the point it is
used, and where it came from instead.

## What this trade is, before any number is believed

- **It is the committed criterion's own trade.** `paper_trade_round_trip_target` drives it in every
  Phase 6 gate. The walk-through ran that criterion's code unchanged, keeping the SQLite file it
  normally deletes (method: decision D3 of `overnight-decisions-2026-09-18-night.md`). Its PASS
  message was identical, digit for digit, to tonight's gate line.
- **The market is scripted, not recorded.** The harness plants one constructed candle series on
  BTC/USD, ETH/USD and SOL/USD alike and pins every bid at 126.925. **"BTC/USD at 126.9" is not a
  Bitcoin price**; the timestamps (17 May 2024) are where the constructed series happens to sit.
- **The models were trained inside the drive**, on that constructed series, into a temporary
  directory. They are the subject a criterion needs, not a model anyone should read skill into.
- **The fees are the fake exchange's tier 3**: maker 0.0011, taker 0.0019. They are invented test
  data (`tests/fixtures/kraken/fee_tiers.json` says so in its own comment), and they are **not**
  the invariant's reference tier 3 of 0.22% / 0.38%. See S3 in tonight's decision list: the
  sentence every Phase 6 criterion appends ("reference friction about 0.65% … hurdle of 1.625%")
  does not describe this run, whose friction was 0.308% and hurdle 0.462%.
- **Paper mode**, opening balance 5000.00 USD (`paper.starting_balances`), run id
  `verify-phase-6-drive`.

So this walk-through shows **the machinery** doing exactly what the rows say it did. It shows
nothing about whether a trade like this would make money.

## What the database does and does not hold

The database holds **ten tables**. For this run `runs` has 1 row, `commands` 1, `orders` 2,
`positions` 1, `trades` 1, `equity_snapshots` 8, and `rejections`, `block_records` and
`leaderboard` hold **none**.

**The database holds no record of why this trade was taken.** Nothing was refused, so
`rejections` is empty, and that is the only table with columns for expected move, friction, net
edge and hurdle. Nothing was blocked, so `block_records` is empty. `trades` carries the outcome and
the money but **no column for any gate's verdict or for the economics that approved the entry**,
and no decision or SHAP row is written for an approval. **The candidate and the gate verdicts
below are therefore read from the engines' published payloads on the entry tick, kept in the
drive's process, not from the database.** Each figure from there is marked *(state)*. This is a
finding in its own right (F-new-1 in tonight's list): an approved trade's reasons live in `state`
for one tick and then are gone.

## The ticks

One tick per minute. The drive runs eight of them (one more than the criterion, to show the equity
row after the exit):

| Cycle | Time (UTC) | What happened |
|---|---|---|
| 1 | 2024-05-17 21:59:01 | Quiet tick before the bar closes; writes the first equity row |
| 2 | 22:00:01 | A 15-minute bar closed. The opportunity chain ran and **the entry was placed** |
| 3 | 22:01:01 | **The entry filled**; the position opened |
| 4, 5, 6 | 22:02:01 – 22:04:01 | The watch: marked each minute, nothing triggered |
| 7 | 22:05:01 | A trade crossed the target the minute before; **the exit** |
| 8 | 22:06:01 | The tick after: flat, cash only |

The one command in the store is the `activate` the drive wrote (source `console`, reason
`verify.py spec 100`), claimed and consumed at 21:59:01 by run `verify-phase-6-drive`. `runs`
records `system_mode` `running` from that moment.

## The candidate, and why that pair *(state)*

Engine 7 `scout`, on the bar-close tick (cycle 2), scanned **4** pairs and let **3** into the
tradable universe: BTC/USD, ETH/USD and SOL/USD. The fourth, ETH/BTC, was excluded with
`no_live_quote`, because the scripted market publishes no quote for it (it is crypto-quoted and
disabled by invariant 7 in any case).

**Why BTC/USD: alphabetical order.** `scout.rank_feature` is `null`, so engine 7 does not rank by
any feature. It keeps the universe in its sorted order until the operator rules on spec 75's
ranking study, and BTC/USD is first. The three pairs carry identical candles and identical quotes
here, so no pair *could* have been preferred on its merits. That is the honest answer, and it is a
recorded absence, not a choice.

## Each gate's verdict, in the order the chain ran them *(state)*

The chain on cycle 2 was the guard chain (1, 2, 3, 4, 17), then the opportunity chain (5, 6, 7,
12, 13, 8, 9, 10, 11, 14, 15, 16, 18). The eight gates, in the order they ran:

**A passing gate has no reason string.** `engine-contracts.md` rule 6 makes a reason mandatory only
when an engine blocks, so every gate below published `reason_code: null`. What each gate decided
on is given instead.

1. **Engine 4 `data_guard` — pass.** `blocked: false`, no findings. Oldest quote 0.0 s old against
   `max_data_age_s` 120.0; 3 pairs seen; 0 missing bars.
2. **Engine 17 `safety` — pass.** `action: none`, nothing tripped. Drawdown 0 (equity 5000.00,
   peak 5000.00); 0 consecutive losses; 0 errors in the window; 0 open positions; 0 resting
   entries; 0 consecutive data blocks.
3. **Engine 7 `scout` — pass.** The universe above; candidate BTC/USD.
4. **Engine 13 `anomaly` — pass.** Score 0.4949463747723813 against threshold 0.603100400911309,
   `anomalous: false`, model `train-20260913T120000-8b12f900-f3`.
5. **Engine 10 `cost` — pass.** Expected move 0.029999999932724522 (engine 8's, 3.0%). Friction
   0.003078783581501615063420783109: maker 0.0011, plus taker 0.0019, plus measured spread
   0.0000787835815…, plus estimated slippage 0 (engine 9 walked one book level of the pinned book).
   Net edge 0.02692121635122290693657921689 against a hurdle of 0.004618175372252422595131174664
   (1.5 × friction). `clears_hurdle: true`.
6. **Engine 11 `risk` — pass.** `approved: true`. Risk amount 50.0000 (1% of 5000.00 equity).
   Notional 3333.33333216965 = that risk ÷ the 1.5% stop, **sized at the ask 126.935**, giving
   quantity 26.26015939 rounded down to 8 lot decimals. The pair's `ordermin` is 0.00005 and its
   `costmin` 5.00; the value at the bid is 3333.07073057575.
7. **Engine 15 `skeptic` — pass.** P(wrong) 0.000007844180605057358 against the veto threshold
   0.5, `vetoed: false`.
8. **Engine 16 `decision` — pass.** `coherent: true`. It checked that scout, prediction,
   order_book, cost, risk, adaptive_router and skeptic all judged the same pair on the same bar
   (`closed_bar_ts` 1715982300), and it composed the order intent: BTC/USD, quantity 26.26015939,
   the net edge and hurdle above.

The non-gates between them, for completeness. Engine 12 `regime`: `trending`. Engine 8
`prediction`: P(target) 0.9999999979999998, P(stop) and P(timeout) 9.99999998e-10 each, DI
1.240601686375737 under a threshold of 2.0541314397998427. That is a model trained on a
steadily rising constructed series, and it says so by being certain. Engine 9 `order_book`:
slippage 0. Engine 14 `adaptive_router`: **`leaderboard_empty`**. This database has no leaderboard
rows, so the router weighted nothing and named the model it was handed. It is not a gate, and it
changed nothing.

## The order placed

From `orders`, userref **1690626088**. A **buy**, intent `entry`, type `limit`, `oflags` **`post`**
(post-only). Quantity **26.26015939**, limit price **126.9**, placed at 22:00:01
(`placed_at` 1715983201000000). Paper order id `paper-1690626088`.

The limit is the best bid 126.925 rounded **down** onto the pair's grid of one decimal
(`pair_decimals` 1): 126.9. Rounding down is why a post-only buy at the bid cannot cross the book.

*One observation about the row itself:* its `cycle_id` is **3**, not the 2 it was placed on. The
row is upserted by each tick that touches it, and the fill tick wrote it last. "Which tick placed
this order" is answered by `placed_at`, not by `cycle_id` (F-new-2 in tonight's list).

## The fill

The same `orders` row, at 22:01:01 (`closed_at` 1715983261000000): status **`filled`**,
`filled_qty` **26.26015939**, `avg_fill_price` **126.9** (its own limit), fee
**3.6656556492501**.

That fee is 26.26015939 × 126.9 × 0.0011 (maker), and it recomputes exactly. The fill happened
because the scripted market printed one trade at **126.7731** (engine 3's published trade range
for that minute) — 0.1% under the limit. The paper broker fills a resting buy only on a trade
**strictly below** its limit, because the queue position is unknown.

The position it opened, from `positions`: **`pos-1690626088`**, long, 26.26015939 BTC/USD at entry
**126.9**, opened 22:01:01. The barriers are measured from the fill price. Target **130.707** is
126.9 × 1.03. Stop **124.9965** is 126.9 × 0.985. Timeout at **1716026461000000** (2024-05-18
10:01:01) is the opening plus 48 bars of 900 s.

## The watch, minute by minute

The `positions` row is updated in place, so its per-minute marks do not survive in it. Its
`last_price` is `null` now that it is closed. **The minute-by-minute record in the database is
`equity_snapshots`**, one row per tick:

| Cycle | Time | Cash | Positions value | Unrealised PnL | Equity | Open |
|---|---|---|---|---|---|---|
| 3 (fill) | 22:01:01 | 1663.9201177597499 | 3332.414226591 | 0.000000000 | 4996.3343443507499 | 1 |
| 4 | 22:02:01 | 1663.9201177597499 | 3333.07073057575 | 0.65650398475 | 4996.9908483354999 | 1 |
| 5 | 22:03:01 | 1663.9201177597499 | 3333.07073057575 | 0.65650398475 | 4996.9908483354999 | 1 |
| 6 | 22:04:01 | 1663.9201177597499 | 3333.07073057575 | 0.65650398475 | 4996.9908483354999 | 1 |

On the fill tick the position is marked at its own fill price, 126.9. That is spec 106's rule, and
it is why unrealised is exactly zero and equity falls by exactly the maker fee: 5000.00 −
3.6656556492501 = 4996.3343443507499. From cycle 4 it is marked at the bid, 126.925:
26.26015939 × 126.925 = 3333.07073057575, and 26.26015939 × 0.025 = 0.65650398475 unrealised.
Engine 21 triggered nothing and held for nothing on all three watch ticks *(state)*.

## The exit, and which barrier fired

**The target.** In the minute before 22:05:01 the scripted market printed one trade at
**130.757**, above the target 130.707. On the tick at 22:05:01 engine 21 published
`triggered: [{position_id: pos-1690626088, barrier: target}]` *(state)*, and engine 22 sold.

From `orders`, the exit: userref **300065105**, a **sell**, intent `exit`, type **`market`** (a
taker — Phase 6 takes every exit as a taker, a recorded choice in engine 22's docstring), quantity
26.26015939, filled 26.26015939 at **130.757**, fee **6.524029356580637** (= 26.26015939 × 130.757
× 0.0019), placed and filled at 22:05:01.

From `positions`: `pos-1690626088` is **`closed`** at 22:05:01, with trade id
`trade-pos-1690626088`.

From `trades`, the one row:

- outcome **`target`**
- quantity 26.26015939, entry price 126.9, exit price 130.757
- entry fee 3.6656556492501, exit fee 6.524029356580637
- entry userref 1690626088, exit userref 300065105
- opened 22:01:01, closed 22:05:01
- **realised PnL 91.095749761399263** USD. That is proceeds 3433.69966135823, less cost
  3332.414226591, less both fees. It is **0.02733626241134751773049645390** of the entry
  notional, about +2.73%.
- reporting currency USD, FX rate 1 at entry and exit
- `fallbacks_used` **`[]`**: nothing was priced on stale data

## The equity row before, during and after the exit, with the cash source on each

| | Cycle | Time | `cash_source` | Cash | Positions value | Equity | Peak | Realised to date | Open |
|---|---|---|---|---|---|---|---|---|---|
| **Before** | 6 | 22:04:01 | `cycle_start` | 1663.9201177597499 | 3333.07073057575 | 4996.9908483354999 | 5000.00 | 0 | 1 |
| **During** (the exit tick) | 7 | 22:05:01 | **`after_exit`** | 5091.095749761399263 | 0 | 5091.095749761399263 | 5091.095749761399263 | 91.095749761399263 | 0 |
| **After** | 8 | 22:06:01 | `cycle_start` | 5091.095749761399263 | 0 | 5091.095749761399263 | 5091.095749761399263 | 91.095749761399263 | 0 |

**Why the exit tick says `after_exit`.** Engine 1's cash that tick was still 1663.9201177597499,
read at the start of the tick before the sale *(state)*. Engine 21 had valued the position at
130.757 before the sale, at 3433.69966135823 *(state)*. A row built from those would describe no
instant that ever existed. That was the exit-cycle defect ruled on 2026-09-17. So engine 19 drops
the closed position and adds engine 22's net proceeds, 3427.175632001649363 *(state)* =
3433.69966135823 − 6.524029356580637, to the start-of-tick cash: 1663.9201177597499 +
3427.175632001649363 = **5091.095749761399263**, and records `after_exit`.

**Why the row after says `cycle_start` with the same figure.** On cycle 8 engine 1 read the
broker's ledger at the start of the tick, and it already held **5091.095749761399263** *(state)*.
**The `after_exit` figure engine 19 computed on the exit tick equals, to the last digit, the
balance the broker reported independently one minute later.** That is the strongest single check
in this walk-through, and the only one that compares two different writers' answers to the same
question.

**The whole account, reconciled:** 5000.00 − 3332.414226591 (bought) − 3.6656556492501 (maker fee)
+ 3433.69966135823 (sold) − 6.524029356580637 (taker fee) = **5091.095749761399263**, which is
cash, equity and peak on the last two rows, and 5000.00 + the realised 91.095749761399263.
