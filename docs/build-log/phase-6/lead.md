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
