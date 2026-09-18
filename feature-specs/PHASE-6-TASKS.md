# Phase 6 — shared task list

## HANDOFF 10, 2026-09-18 evening — rulings S1–S3 carried out; the phase is NOT closed

**Read this first. HANDOFF 9 and earlier are history.** The operator is awake and reading the
walk-through (`docs/build-log/phase-6/first-paper-trade.md`); nothing is waiting on the lead.

### State

`verify.py --phase 2` → **9/9, exit 0** and `--phase 6` → **14 criteria, 14 PASS, 0 FAIL, 0 PENDING, exit 0**, on the corrected tree, with `mypy --strict` and `ruff` clean first; the code delta's sha256 identical at the start and end of the gates, so the tree did not move. Logs: `logs/verify/phase{2,6}-20260918-rulings-s2s3-lead-verify.log` and
`regate-20260918-rulings-s2s3-lead-summary.txt`. Committed and pushed. **Phase 6 is not marked
green and not closed; Phase 7 is not started; Q3's re-cut is not started.**

### What the operator ruled, and what landed

- **S1.** Engine 22 as built. Invariant 14 records why its balance authorisation is deliberately
  wider than the code: in paper mode the retained balance is the real account's, and the paper
  ledger holds no base currency.
- **S2.** `asset_pairs.json` carries an honest provenance block (invented Phase 0 data, never cut
  from an archive).
  - `candles_match_kraken_ohlc`'s prose and messages now say what it compares against: a local
    reduction of recorded trades, with an invented tolerance. Its PASS reports the largest
    difference it measured, which is 0.
  - Spec 118 says its declaration is invented.
  - **Assertions unchanged.** Recorded as a FINDING in the tracker.
- **S3.** Every trade criterion states what engine 10 computed in its own run (`_run_regime`), and
  Kraken's reference tier 1 is a separate sentence, held by a tripwire test. Measured: the fake's
  tier 1 clears the gate (friction 0.708%, hurdle 1.062%).
- **F-new-1 and F-new-2** are Phase 7 prerequisites 7 and 8. F-new-3 and F-new-4 are recorded.
- **Mutation proof** is in `docs/build-log/phase-6/lead.md`, arms M1 to M10. M9 survived the
  real-tree tests and was killed by a unit test written for it.

### For the operator, not decided

- **D11 (REVIEW).** Two criteria's *names* still claim what they do not check:
  `candles_match_kraken_ohlc` and `recorded_book_agrees_with_recorded_pair_decimals`. A rename
  reaches the registry, two test files and the tracker.
- **D15.** The same false tier-1 claim sits in three test comments in B's and C's lanes, reported
  and not edited:
  - `tests/engines/test_decision.py:79`
  - `tests/engines/test_feature_chain_rehearsal.py:1825`
  - `tests/engines/test_order_book.py:973`
- **Engine 22's contract comment** (`engines/exit/contracts.py:159-166`) still ends "Escalated to
  the lead rather than decided here". The escalation was ruled on 2026-09-18 (S1); B's lane.

### What is left in Phase 6

1. The operator rules on the close after reading the walk-through.
2. The close itself: Phase 6 marked green in the tracker, and `phase-6.md`'s header updated.

### Standing rules

HANDOFF 8's list stands. Add one of tonight's: **a message is a claim about evidence, and needs a
test that it is true, not a test that it is present.**

## HANDOFF 9 (history), 2026-09-18 — close preparation done; two rulings stopped; the phase is NOT closed

**Read this first. HANDOFF 8 and earlier are history.** Written for a session that has read the
documents and nothing else.

### State

Phases 0 to 6 re-gated in order on a quiet tree at `98c0485` — every phase exit 0: phase 0 7/7, 1 10/10, 2 9/9, 3 9/9, 4 10/10, 5 14/14, 6 14/14, each with `toolchain_green` at 3314 passed, 2 skipped. Logs are
`logs/verify/phase{0..6}-20260918-close-prep-lead-verify.log`, with the summary and the
mypy/ruff logs beside them (`regate-20260918-close-prep-lead-*`). Everything below is committed
and pushed. **Phase 6 is not marked green and not closed. Phase 7 is not started.** The operator
sees the first paper trade, then rules.

### What the operator ruled before sleeping, and what happened

The night's one decision list is `docs/build-log/phase-6/overnight-decisions-2026-09-18-night.md`.

- **Q1** (invariant 14's retained balance): invariant 14 **not** amended, as ruled. **Engine 22
  unchanged — STOPPED (S1)**, because reading the balance changes behaviour: a paper liquidation
  would sell nothing, and the paper broker's retained balance is the *real* account's.
- **Q2** (spec 118's premise): **STOPPED (S2)**. `asset_pairs.json` was never cut from an archive.
  It is the Phase 0 fake's invented test data, and no provenance block was written.
- **Q3** (spec 118 covers 1 pair of 5): recorded in the tracker as ruled. The re-cut is scheduled,
  **not started**, and after S2 it should land with Q2's answer.
- **Q4** (the trade): **done**. `docs/build-log/phase-6/first-paper-trade.md` is the criterion's
  own round trip with its database kept, every number from the rows.

### Found tonight, all waiting on the operator

- **S3.** Every trade criterion's message quotes 0.65% friction / 1.625% hurdle. The run's were
  0.308% / 0.462%, because the fake's tier 3 is 0.11% / 0.19%. And the fake's own tier 1 is **not**
  a no-trade regime.
- **F-new-1.** An approved trade leaves no record of why it was approved. The economics columns
  exist only on `rejections`.
- **F-new-2.** `orders.cycle_id` and `positions.cycle_id` record the last writing tick, not the
  placing one.
- **F-new-3.** The console sentence for `exits_placed` says exits are "resting"; every exit is a
  market sell.
- **F-new-4.** `docs/PROJECT-STATE.md` is a 2026-09-12 snapshot nothing keeps true.

### Done tonight (close preparation, as ordered)

- The re-gate of phases 0 to 6, above.
- `docs/build-log/phase-6.md`: an examiner-readable summary, then every per-agent log and decision
  file verbatim.
- The teammate progress files merged into the tracker as "Phase 6 — merged for the close, NOT
  closed". The teammates' own stale status lines are listed there by line number, **not edited**
  (their files).
- `docs/build-log/phase-7/`, four empty files.
- Two FINDINGS in the tracker:
  - the `cash_source` test that passed asserting nothing
  - `outside_universe` never having a producer

### What is left in Phase 6

1. The operator reads the walk-through and the gates, then rules on the close.
2. Rulings on S1, S2, S3 and F-new-1 to 4, and on Q3's timing given S2.
3. The close itself, on the operator's word: Phase 6 marked green in the tracker, the phase status
   row, and `phase-6.md`'s summary header updated from "not closed".

### Standing rules

HANDOFF 8's list stands unchanged.

## HANDOFF 8 (history), 2026-09-18 08:50 local — the nine criteria are green and the follow-up work is done. The phase is NOT closed.

**Read this first. HANDOFF 7 and earlier are history.** Written for a session that has read the
documents and nothing else.

### State

`python scripts/verify.py --phase 6` → **14 criteria, 14 PASS, 0 FAIL, 0 PENDING, exit 0**
(`logs/verify/phase6-20260918-cashsource2-lead-*.log`; `toolchain_green` reports `3314 passed, 2
skipped`). The tree is clean, every agent is stopped, and everything below is committed and pushed.
**The operator has not yet seen the first paper trade, and asked to before the phase closes. Do not
close it.**

### Done since HANDOFF 7 (the operator was asleep; the night's decisions, each with the option
rejected, are in `docs/build-log/phase-6/overnight-decisions-2026-09-18.md`)

| Spec | What | Owner |
|---|---|---|
| 119 | Every seeded rejection uses an `(engine, code)` pair the live system can emit | B |
| 120 | The orphaned `REASON_PROSE` prose retired; **both** directions of the walk now asserted | C |
| 109 | The last stale paper-mode-fallback prose, eight sites across six files | A |
| 118 | New 14th criterion: the recorded book agrees with the recorded `pair_decimals` | C |
| — | `EquitySnapshotRow.cash_source`'s default removed, with a refusal test | Lead |

### Open questions for the operator — nothing else is blocked on them

All four are in the night's decision log with options and a recommendation:

- **Q1.** Invariant 14 grants engines 21 and 22 a retained balance **neither reads**. Engine 22
  deliberately reads only the retained `AssetPairs`; B recorded that deviation from spec 93 and
  escalated it on 2026-09-16; the invariant never moved. Amend the invariant, or change engine 22?
- **Q2.** Spec 118's own premise was wrong: the two fixtures are **not** frozen together
  (`asset_pairs.json` 2026-09-08, `book_sample.jsonl` cut 2026-09-16, no provenance block). The
  check is honest and its prose says so; aligning them is a ruling.
- **Q3.** That criterion compares **1 pair of 5**. Widening to 3 of 5 is a re-cut **C** runs (not
  A — the cutter chooses nothing), and it shares the fixture with
  `order_book_slippage_on_recorded_book`, so the two must move together.
- **F1.** An invented ADA/USD `pair_decimals` for the fake client sits two screens from the new
  criterion. Not a defect; the docstring names it as the thing it must not read.

Smaller, also for the operator: a tautological assertion in `tests/engines/test_exchange.py`
(A found it in its own lane and left it, since a prose spec does not touch assertions); a stale
line in `context/progress/b-store.md:287`; and C's finding that `outside_universe` **never** had a
producer — `feature-specs/44` said the key "already exists" and nothing ever checked it was used.

### What is left in Phase 6

1. **The operator sees the first paper trade**, then rules on closing.
2. The phase close itself: the final gate, the tracker, and `docs/build-log/phase-6.md`
   consolidated from the four per-agent logs.
3. Anything the operator rules on Q1–Q3.

### Standing rules (all also in `context/code-standards.md` or the tracker)

- **The gate is `verify.py` alone**, with `mypy --strict src/ scripts/` and
  `ruff check src/ tests/ scripts/` before it. The bare `pytest` run is retired; spec 115 puts the
  test count in the gate's own PASS message.
- **One gate per boundary, immediately before the commit**, and **commit only once the agent's
  records are on disk**. A re-gate is required when any source, test or config byte changed since
  the gate started; a docs-only delta needs only the document checks, with the proving diff in the
  commit message.
- **Every measurement lands in a file and is filtered afterwards.** The lead broke this the same
  night it wrote it into HANDOFF 7: a red enumeration piped through `tail` kept the summary and
  threw away all 39 failure and 167 error names.
- **One agent in the tree at a time**; push-notify the operator only when blocked on a ruling;
  anything over ~3 hours goes to the operator with options first (gates and agreed work exempt).
- **Every assertion proven capable of failing, mutation over reading**, byte-copy restores with the
  sha256 compared in the same statement, anchors asserted to occur exactly once, and **ask of every
  kill which test killed it**.
- **Never write a file through a bash heredoc carrying escapes** (three incidents this phase).
- **Prose is part of the deliverable**, and **stale prose with no decision entry behind it is a
  finding to report, not a typo to fix silently** — every prose spec this phase produced one.

## HANDOFF 7, 2026-09-18 02:45 local — THE NINE CRITERIA ARE GREEN. Phase 6 is not closed.

**Read this first. HANDOFF 6 and earlier are history.** Written for a session that has read the
documents and nothing else: everything below is on disk, nothing of substance lives in a
transcript.

### Where it stands

`python scripts/verify.py --phase 6` → **13 criteria, 13 PASS, 0 FAIL, 0 PENDING, exit 0**
(`logs/verify/phase6-20260918-nine-lead-*.log`; `toolchain_green` reports `3297 passed, 2
skipped`). **The first complete paper trade runs end to end** through the registered chains at fee
tier 3 — post-only entry past all eight gates, fill at its limit, minute-by-minute watch, exit on
each of target, stop and timeout — with every order, position, trade and equity row reconciled
against figures recomputed from the book and the live fee tier, and the console rendering the
position live.

**Do NOT close the phase.** The operator wants to see the trade before it closes. When the nine
were green the lead reported and stopped, which is where this handoff begins.

**Nothing is in flight. Every agent is stopped and the tree is clean at the commit carrying this
handoff.** Their progress files and build logs are current: `context/progress/{a-platform,
b-store,c-interface}.md`, `docs/build-log/phase-6/*.md`.

### What this session built, in order

Registration of engines 9, 14, 16, 18, 21, 22 (spec 82); the nine criteria bodies (100); the
exit-cycle equity row (113 B, 114 C, 116 A); the console showing the position live (101 C); and
the smaller work: 103, 104, 105, 106, 107, 108, 110, 111, 112, 115, 117. **Four defects were found
that would each have shipped as working code**, all recorded in `context/progress-tracker.md`:
the paper-fill double count, the unrecorded errored tick, the exit-cycle equity row (three moments
that never coexisted), and `verify.py` dying on the minus sign its own house style mandates —
exiting 1, the code a real FAIL returns, with six criteria never run.

### The next steps, in this order

1. **The seed-vocabulary reconciliation** — B repoints every seeded `rejections` row to an
   `(engine, code)` pair the live system can emit (engine 9's becomes engine 10 refusing on the
   absent estimate); **then** C retires the prose that no longer has a producer. Every code stays
   mapped until B's half lands, because the seeded rows exist and must render. The finding is in
   the tracker under "the Phase 0 seed's refusal vocabulary is invented".
2. **Spec 109 (A)** — engine 1 and the Kraken client stop describing paper-mode fallbacks that no
   longer exist.
3. **Spec 118 (C)** — the recorded prices agree with the recorded `pair_decimals`, over the two
   committed fixtures.
4. **The `cash_source` default removal (lead)** — `EquitySnapshotRow.cash_source`'s default goes,
   **landing with a test that a row lacking a source is refused**; ~8 files across three lanes, so
   it is a lead task under ownership rule 6, and B's test *of* the default is retired by it.
5. Then the phase close, on the operator's word: the final gate, the tracker, and
   `docs/build-log/phase-6.md` consolidated from the four per-agent logs.

### Standing rules in force (all also in `context/code-standards.md` or the tracker)

- **The gate is `verify.py` alone**, with `mypy --strict src/ scripts/` and
  `ruff check src/ tests/ scripts/` before it. The bare `pytest tests/ -q` is **retired** — the
  same suite twice on an unchanged tree measured nothing, and spec 115 puts the test count in the
  gate's own PASS message.
- **One authoritative gate at every boundary, immediately before the commit**, and **commit only
  once the agent's records are on disk**, not merely its logs. A re-gate is required when any
  source, test or config byte changed since the gate started; a docs-only delta needs only the
  document checks, with the diff proving it docs-only in the commit message.
- **Push-notify the operator only when blocked on a ruling** — one line, and the blocked item
  stops while other work continues.
- **Any finding or design choice costing more than about three hours goes to the operator with the
  options before anyone starts.** Gates, re-gates and agreed work are exempt.
- **One agent in the tree at a time.** Two lanes sweeping at once make each other's results wrong.
- **Every assertion proven capable of failing, with the proof in the build log. Mutation over
  reading.** Mutate from a byte copy, restore in a `finally` with the sha256 compared in the same
  statement, anchors asserted to occur exactly once, `PYTHONDONTWRITEBYTECODE=1`, and a verdict
  with no pytest summary line is not a result. **Ask of every kill which test killed it**: three
  survivors this phase (V8, V12, V1) and two kills-for-the-wrong-reason (M1, and A's first M4)
  were found that way.
- **Never write a file through a bash heredoc carrying escapes** — three incidents this phase; the
  escape is decoded one layer above the shell. Use the file tool and `chr(0x2212)`.
- **Prose is part of the deliverable**, not decoration: this code goes into a dissertation. And
  **stale prose with no decision entry behind it is a finding to report, not a typo to fix
  silently.**

### Open, and needing nobody's permission to read

`docs/build-log/phase-6/overnight-decisions-2026-09-17.md` holds every decision taken while the
operator slept, each with the option rejected. **All of it is ruled: Q1, Q2, and every decision
including D3 and D8**, which the operator accepted on the morning of 2026-09-17 and which now
carry their ruling inline. An earlier draft of this handoff called D3 and D8 outstanding; they
never were. The acceptance had been recorded in that file's rulings section the whole time, and
only the `**REVIEW**` tags on the entries were left standing — **a record is not resolved because
the resolution sits somewhere else in the same file; the marker has to move.**
`overnight-decisions-2026-09-18.md` is the list for the night of the 18th.

## HANDOFF 6, 2026-09-17 19:20 local — the criteria bodies exist; the exit-cycle row is mid-fix; MUCH IS UNCOMMITTED

**Read this first. HANDOFF 5 and earlier are history.** Written at the operator's instruction
because the last commit predates a full day's work.

### Committed and pushed (HEAD = `dd9ea39`)

Everything through spec 107: both rehearsals (87, 94) and the two defects they found (103 the
paper-fill double count, 104 the unrecorded errored tick); spec 105's equity-continuity criterion
and 107's tightening of it; spec 106 (engine 11's balance fallback removed, engine 21's fill-tick
mark); **spec 82, the registration of engines 9, 14, 16, 18, 21, 22** (`69038a7`) with phases 0–6
re-gated; spec 108; the operator's rulings in the documents.

### UNCOMMITTED AND UNGATED, on disk right now

| What | Where | State |
|---|---|---|
| **C's spec 100 criteria bodies** | `scripts/verify.py`, `tests/verify/test_phase6_criteria.py`, `tests/verify/test_runner.py` | complete, swept; 5 criteria PASS, 1 PENDING, 4 FAIL on the exit-cycle row |
| **B's spec 113 v2** | `engines/exit/`, `engines/position_manager/`, `clients/store/`, `db/migrations/0005_equity_cash_source.sql`, their tests | complete, swept, reported |
| **C's spec 114** | `engines/memory/`, `tests/engines/test_memory_rows.py` | **in progress** |
| **Lead documents** | `context/engine-contracts.md`, `ownership.md`, `architecture-context.md`, `progress-tracker.md`, `docs/build-log/phase-6/*`, `feature-specs/109–116` | committed in the commit carrying this handoff (docs-only, D4 rule) |

**No full gate has run since `dd9ea39`.** The code above is ungated. The authoritative gate runs
after spec 114 and 116, and is now **mypy + ruff, then `verify.py --phase 6` only** — the separate
`pytest tests/ -q` is retired (operator, 2026-09-17: `toolchain_green` runs the identical command;
the test count comes from its attempt log, and spec 115 will put it in the PASS message).

### The nine Phase 6 criteria, plus two

| Criterion | Real tree |
|---|---|
| `unfilled_entry_cancels_without_chasing` | **PASS** |
| `escalation_completes_during_outage` | **PASS** (both legs: positions via `safety`'s escalation, the resting-entry cancel via an operator `close_all`) |
| `order_book_slippage_on_recorded_book` | **PASS** |
| `adaptive_router_weights_on_fixture` | **PASS** |
| `paper_equity_continuous_across_fill` (spec 105, now on `bootstrap.build_chains()`) | **PASS** |
| `paper_trade_round_trip_target` / `_stop` / `_timeout` | **FAIL** — the exit-cycle equity row |
| `triggered_stop_holds_on_data_guard_block` | **FAIL** — same cause |
| `equity_row_never_values_positions_it_does_not_hold` (new) | **FAIL** on purpose, until the fix |
| `console_shows_position_live` | **PENDING**, naming spec 101 |

**The one defect behind every FAIL.** On the tick engine 22 sells, engine 19's equity row mixed
three moments: engine 1's start-of-tick cash, engine 21's pre-sale valuation, and the store's
post-sale position count. Operator ruling (one earlier design withdrawn): engine 22 publishes
`net_proceeds` per closed trade, engine 21 publishes `value` per marked position row, and engine 19
**filters and sums** — drop the closed `position_id`s, sum the rest, add the proceeds to engine 1's
cash — recording `cash_source`. The rule is in `context/engine-contracts.md`.

**The tree is red on 26 tests right now**, every one because engine 19 has not yet accepted the two
new payload keys (`_Row` is `extra="forbid"`): 20 in `tests/verify/test_phase6_criteria.py`, 5 in
A's `tests/engines/test_trade_chain_rehearsal.py`, 1 in B's `tests/engines/test_position_manager.py`.

### Mutation survivors, all three now killed

- **V8** — engine 9's walk compared by level count only. Killed by arms that keep the level count
  and move the price.
- **V12** — the trained subject's cache key made constant; the tests checked what the criteria
  *said*, not what they *read*. Killed by a copied tree whose different training must be judged on
  its own subject. No other criterion has this shape.
- **V1** — the "every registered gate ran" check could be disabled unnoticed, because the committed
  orchestrator never skips a gate. **A real hole.** Killed by an arm whose orchestrator skips them.

### The exact next three steps

1. **C finishes spec 114** (engine 19: accept the two payload keys as facts, strip them before the
   stored-row validation, build the exit-cycle row, write `cash_source`, the partial-mark test —
   a *remaining* unmarked position means **no** row — and the new criterion's FAIL arm).
2. **A does spec 116**: its rehearsal re-derives the ruled equity expectation independently (not a
   copy of engine 19's code), and strips the two keys before validating.
3. **The lead gates once** (mypy + ruff + `verify.py --phase 6`) and **commits everything above in
   one commit**, then reports to the operator.

Then: B's 111 (remove `CostAssessment.fallbacks_used`), 112 (the window/escalation config test),
110; C's 115; C's 101 (the console, which turns the ninth criterion green); the seed-vocabulary
reconciliation (B then C); A's 109. **Do not close the phase**: when the nine criteria are green,
report and stop — the operator wants to see the first paper trade.

### Standing rules in force

One agent in the tree at a time. A gate immediately before every commit, and the agent's records
must be on disk before the commit, not only its logs. Push notification to the operator **only**
when blocked on a ruling. Decisions taken while the operator was asleep, with the rejected option
for each, are in `docs/build-log/phase-6/overnight-decisions-2026-09-17.md`; open questions Q1
(engine 10's unused `fallbacks_used`, ruled: remove, spec 111) and Q2 (ruled: spec 112's test) are
closed there.

## HANDOFF 5, 2026-09-17 ~10:15 local — engines registered; the operator is asleep and the lead runs unattended

**Read this first. HANDOFF 4 and earlier are history.**

**The operator is asleep and has authorised unattended work until they say they are back.**
The rules, verbatim in substance: *how* choices (naming, placement, test structure,
equivalent mechanisms, order) may be taken and must be logged with the rejected option in
`docs/build-log/phase-6/overnight-decisions-2026-09-17.md`, flagged **REVIEW** where a
competent objection exists; *what* choices — anything weakening a gate or criterion,
changing a config value, threshold or barrier, making the system more willing to trade,
amending an invariant or locked decision, or a cheaper option that proves less — **stop**:
write the options there under "Open questions" and move to unblocked work. One authoritative
gate per boundary immediately before the commit; commit and push each boundary; stop only if
the gate is red after two fix attempts on the same thing. **Do not close the phase: when the
nine Phase 6 criteria are green, report and stop** — the operator wants to see the first paper
trade first. When the operator says they are back, the normal rhythm resumes.

### Where it stands

| Done | Commit |
|---|---|
| Spec 87 (A) rehearsal of 18/21/22; its two defects fixed by 103 (B) and 104 (C) | `3b2cedf`, `178a0a8`, `ab2bf4f`, `3e1ded8` |
| Spec 94 (B) rehearsal of 9/14 on the thin book | `49e369a` |
| Spec 105 (C) criterion `paper_equity_continuous_across_fill` | `76035be` |
| C's nothing-built PENDING test moved to `unbuilt_tree` | `d28b756` |
| Spec 106 (B): engine 11's fallback removed; engine 21's fill-tick mark | `268f49e` |
| **Spec 82: engines 9, 14, 16, 18, 21, 22 registered**; phases 0–6 re-gated, only `toolchain_green` (the known 8) failing | `69038a7` |
| Spec 108 (B): stale fallback prose, unused `FALLBACK_PAPER_LEDGER`, engine 10 LF | the commit after this handoff |

**The only red** is spec 100's eight `test_pending_on_the_real_tree_names_the_subject_and_the_spec`
parametrisations and `toolchain_green` in every phase that follows from them. They clear when
the criteria bodies are written.

### The order from here

1. **C, spec 107** — engine 9's stale prose; spec 105's criterion stops accepting a NULL mark
   (decision D3, REVIEW).
2. **C, spec 100 criteria bodies** — the nine Phase 6 criteria against the **registered**
   `bootstrap` chains, at fee tier 3, each proven PENDING/PASS/FAIL. Fold in: the tier-sentence
   test on `bare_tree` that never observes PENDING, and the four-quote docstring at
   `tests/verify/test_phase6_criteria.py:671`. Spec 105's criterion should switch from its
   hand-built chains to `bootstrap` in the same work.
3. **C, spec 101** — the console shows the position live.
4. **Seed-vocabulary reconciliation** — B repoints every seeded rejection to an `(engine,
   code)` pair the live system can emit; then C retires prose with no producer.
5. **Stop and report** when the nine criteria are green. Do not close the phase.

One agent in the tree at a time (decision D1). The recorder, its supervisor and the funding
poller keep running. The network was down 03:13–08:20 UTC overnight (event E1).

## HANDOFF 4, 2026-09-16 — spec 87 is done and found two defects; three specs added

**Read this first; HANDOFF 3 below still holds except where this says otherwise.** A's spec 87
rehearsal is committed. It found two defects between engines, both ruled by the operator — see
"DEFECTS FOUND BY REHEARSAL" in `context/progress-tracker.md`. Three new specs:

| Spec | Owner | What | Order |
|---|---|---|---|
| 103 | B | The paper broker's balance counts every fill it has executed, recorded or not | after B's spec 94 |
| 104 | C | Engine 19 records an errored opportunity-chain engine as `engine_errored`; prose in the same change | after 103, not concurrently with B's sweeps |
| 105 | C | Criterion `paper_equity_continuous_across_fill`, proven red by breaking the broker | after 103 has landed |

Plus A's one-line follow-up: remove the strict `xfail` in `test_trade_chain_rehearsal.py` once
103 lands. The lead has already landed `state["block_status"]` in `core/` (spec 104 step 1).
**Registration (82) is still held.** The sequence is: B's 94 → B's 103 → A's xfail →
C's 104 → C's 105 → the lead reports to the operator → 82.

**Status 2026-09-16 21:20 local: all of that sequence is done and committed** — 94 `49e369a`,
103 `178a0a8`, A's xfail `ab2bf4f`, 104 `3e1ded8`, 105 in the commit after this line. Gate:
pytest only spec 100's known 8; `verify --phase 6` 12 criteria, 2 PASS, 1 FAIL
(`toolchain_green`, the same 8), 9 PENDING. **Next: the operator's word on registration (82),
then spec 100's criteria bodies (C), then the gate.**

## HANDOFF 3, 2026-09-16 07:40Z — all six engines are committed; the order from here is forced

**Read this first. HANDOFF 2 and HANDOFF 1 below are history.** Every ruling and finding of the
session that produced this is on disk — in `context/progress-tracker.md` (rulings and findings),
`context/code-standards.md` (nine new standing rules), `context/trading-invariants.md`,
`context/engine-contracts.md` and the four `docs/build-log/phase-6/*.md`. Nothing of substance
lives only in a transcript.

### What is committed and pushed

**All six Phase 6 engines plus the fill simulator exist.** Fifteen commits, `4d9e106` to
`fe018e3`:

| Engine / piece | Spec | Owner |
|---|---|---|
| 9 `order_book` + committed book fixture | 96 | C |
| 14 `adaptive_router` + leaderboard fixture | 97 | C |
| 16 `decision` — **a gate**, the tick-coherence check | 90 | B |
| 18 `execution` | 91 | B |
| 21 `position_manager` | 92 | B |
| 22 `exit` — invariant 14's liquidation | 93 | B |
| Paper broker and ledger (`clients/paper/`) | 88 | B |
| 19 `memory` rewritten to record 18 and 22 | 98 | C |
| Order surface on `clients/kraken/` + `order_book` config | 84, 80 | A |
| Migrations 0003 `positions.hold_reason`, 0004 `leaderboard.base_rate_brier`, `all_leaderboard_rows` | — | B |
| Spec 99's walking test + all engine codes mapped; spec 100's nine criteria registered; scripted market harness; tier-3 profile | 99, 100 | C |

**Gate at that commit**, frozen tree, zero writes during the run:
`1 PASS, 1 FAIL, 9 PENDING` — `8 failed, 3159 passed, 2 skipped in 1256.96s`.
Log: `logs/verify/phase6-20260916-boundary2-lead.log`.

### The only red, and it is owned

All eight failures are one parametrised test,
`tests/verify/test_phase6_criteria.py::test_pending_on_the_real_tree_names_the_subject_and_the_spec`.
They fail **because the engines their PENDING messages named as missing have landed** — the
frontier moving, not a regression. C predicted it before the run. It is part of spec 100's
remaining work.

### Nothing is in flight — every teammate is stopped

`A2-platform`, `B3-store`, `C-models` and `C4-verify` were all stopped cleanly at boundaries;
their progress files and build logs are current. Earlier sessions of each lane are stopped too.
**A revived session is not a rogue one** — it is a session hours out of date, and the first thing
it should do is read this file.

### The forced order from here

1. **The two rehearsals**, each run by an agent that did not build the engines.
   - **A's spec 87** — engines 18, 21 and 22 through real `Orchestrator` ticks.
   - **B's spec 94** — engines 9 and 14. **Read spec 94 step 2 before writing the assertion**:
     engine 9's estimate on the fake client's *default* book is **exactly zero**, so recomputing
     friction with it is indistinguishable from recomputing with no slippage term at all. Script
     a thin book; the basis must not fit in level one.
2. **Registration, spec 82** — the lead adds 9, 14, 16, 18 to the opportunity chain and makes the
   manage chain 21, 22, 19. **Held until both rehearsals are green**, the same deferral Phases 2
   to 5 each took, and `is_gate_matches_registry` will only pass with engine 16 counted as a gate.
3. **Spec 100's criteria bodies** — they drive the real `bootstrap` chains, so they can only reach
   PASS after registration. Seven of the nine need a trade; all seven run at **fee tier 3** and say
   so in their own message.
4. **Then** spec 101 (console), and the seed-vocabulary reconciliation recorded as a finding in the
   tracker: B repoints every seeded rejection to an `(engine, code)` pair the live system can emit,
   C then retires prose with no producer. Every code stays mapped until B's half lands.

### Five things that will otherwise be relearned

- **Hard-stop every session before a gate.** A hold reaches an agent at its next tool boundary, by
  which point the nearest coherent stopping point is several steps away. Two gate runs were spent
  measuring a moving tree before this was accepted.
- **A description of the code is not the code.** Five spec lines of the lead's named mechanisms
  that could not do the job; each was caught by an agent building against the code.
- **Read the working tree, not `HEAD`.** Teammates do not commit, so another lane's landed work is
  invisible to `git show`. Two agents concluded a dependency was missing when it was on disk.
- **Count CRLF in Python before any sweep** (`b.count(b"
")`). `grep -c $'
$'` lies in this
  shell. A text-mode round trip disarms every literal-anchor patcher in the repository at once.
- **`PYTHONDONTWRITEBYTECODE=1` on every sweep**, and a verdict with no pytest summary line is not
  a result.

## HANDOFF 2, 2026-09-16 06:20Z — every remaining piece of Phase 6 runs through B

**Read this before HANDOFF 1, which is now history rather than state.**

**Committed and pushed** (nine commits, `4d9e106` to `fe06a72`): specs 84, 85, 86, 88, 89, 90,
91, 92, 95, the four loose ends, spec 99's first codes and spec 100's registration, and the lead's
81, 83 and `EngineContext.previous_now`. **Uncommitted on disk**, all lane-green, awaiting the
next gate: A's `OrderState` amendment (`qty`, `limit_price`, `opened_at`) and the `order_book`
config landing; B's migration 0003, the broker's `OrderState` sites and engine 18's unrecorded-row
build; C-models' engines 9, 14 and 19's rewrite; C-verify's walking test, nine criteria, the
scripted market harness and the tier-3 profile.

**Engines built:** 9, 14, 16, 18, 19 (rewritten), 21. **Engine 22 is the only one left.**

| Owner | State |
|---|---|
| **B3-store** | **The whole critical path.** Engine 22 (spec 93); migration 0004 `base_rate_brier REAL` nullable; a **non-truncating leaderboard enumeration** (`leaderboard_entries` takes the version as an argument and cannot enumerate); three CRLF files in its lane, `clients/store/contracts.py` most consequentially. |
| **C4-verify** | The Phase 4 replay fix in `scripts/verify.py` (three red criterion tests, caused by a correct engine 19 change); then twelve reason codes; then the criteria bodies. |
| **C-models** | **Stood down, lane complete.** Returns for two one-minute changes when 0004 lands: engine 20's write of `base_rate_brier`, and engine 14's skill computation. |
| **A** | **Stood down.** Spec 87's rehearsal of 18, 21 and 22 waits on engine 22. |
| **Lead** | Spec 82 registration (held until the 87 and 94 rehearsals are green); spec 80's remaining cross-chain rows; the gate and the commits. |

**Nine criteria are registered and PENDING.** Seven name engine 22 or the drivers that need it;
two name engines 9 and 14 and are answerable as soon as their fixtures are driven.

**Sessions die and revive in this project.** Four died at a usage limit at 23:49Z; two later
revived on their own and one of those collided with its own replacement in the same lane. The
protocol that works: the lead **hard-stops** every session before a gate rather than asking for a
hold, because a hold reaches an agent at its next tool boundary and by then the nearest coherent
stopping point is several steps away. Two gate runs were spent measuring a moving tree before this
was accepted. **A revived session is not a rogue one** — it is a session six hours out of date, and
the first thing it should do is read this file.

## HANDOFF 1, 2026-09-16 00:00Z — all four teammates died at the usage limit. Read this first.

**What happened.** A, B, C-models and C-verify all hit the session limit within 40 seconds of
each other at 23:49Z, **one minute before the limit reset**. Nobody was stopped, nothing was
abandoned by choice, and no message they sent went unread. A dead session is not a refusal: read
the files below rather than inferring anything from silence.

**What survived, and why.** Every one of the four had written its progress file **before** its
work and its build-log entries **at diagnosis**, so the only thing lost is in-flight reasoning —
no claim, no finding and no mutation table went with them. That is the "write before, not after"
rule paying for itself for the second time in this project (Phase 3 lost three build logs the
other way round). `context/progress/{a-platform,b-store,c-interface}.md` and
`docs/build-log/phase-6/*.md` are accurate as of the deaths.

**What was running, and what it cost: nothing.** Only `scripts/record.py` (x2) and
`scripts/recording/supervise.py` (x2) were alive, as they have been since 14:49, and they are
untouched. **No daemon has ever run in Phase 6**, which is why A's `drain_gaps` finding below has
cost the archive nothing so far.

### State on disk, per spec, verified by the lead rather than taken from a report

| Spec | Owner | State |
|---|---|---|
| 84 order surface | A | **Done**, 60 tests, 15 mutations killed. Seam test discharged by 86. |
| 85 trade ranges | A | **Done**, reworked onto `context.previous_now`, sweep re-run from scratch. |
| 86 wiring + book cutter | A | **Done**, 7 + 23 tests, 16 mutations killed. Cutter dry-run against the real archive, read-only. |
| 87 rehearsal of 18/21/22 | A | Not started, correctly — waits on B's 91 and 93. |
| 88 paper broker + ledger | B | **Done**, 250 tests in lane, 13 mutations (12 killed + 1 equivalent control that survived as designed). |
| 89 one position per pair | B | **Built**, 48 tests, 11 mutations killed. **The lead's precedence reversal is NOT applied** — see below. |
| 90 engine 16 | B | Not started. Unblocked since `5f84df3`. |
| 91 engine 18 | B | Not started. |
| 92 engine 21 | B | **Built, incomplete**: 632-line engine, 226-line contracts, README, 857 lines of tests, 40 passing. **Mutation sweep not run.** |
| 93 engine 22 | B | Not started. |
| 94 rehearsal of 9/14 | B | Not started. |
| 95 is_buy | C-models | **Done**, 4 mutations killed. Cross-chain key row added by the lead. |
| 96 engine 9 | C-models | Not started. |
| 97 engine 14 | C-models | Not started. |
| 98 engine 19 records 18 and 22 | C-models | Not started. **Grew a defect** — see below. |
| 99 reason prose | C-verify | **Partly done**: the two spec 89 codes are in `REASON_PROSE`. The walking test is not written. |
| 100 Phase 6 criteria | C-verify | Not started. |
| 101 console live position | C-verify | Not started. |
| 102 DI at size | C-models | **Half-applied on disk** — see below. |

### Four things waiting, and two of them are half-applied edits the deaths left behind

1. **~~`src/acsoe/modelling/di.py` names `score_many` in `__all__` and does not define it.~~
   CORRECTED AND CLOSED, 2026-09-16.** Two things in the original wording were wrong. It was far
   worse than an unusable `import *`: the rename left `_CHUNK` undefined at two call sites inside
   `_mean_nearest`, so **~180 tests errored** on a `NameError` — every file that imports the DI.
   I had run `compileall`, which answers *does this parse*, and read it as *do the names resolve*;
   `ruff`'s `F821` and `mypy`'s `name-defined` each name it in one line and I had run neither.
   And the instruction "do not revert it" is superseded: `di.py` **was** restored to its committed
   state, the 171 affected tests pass, the partial edit is saved as `scratchpad/di-102-partial.diff`
   with its `_BLOCK_ELEMENTS` reasoning intact, and **spec 102 is not started rather than
   half-done**. Spec 102 is now **parked by the operator** until Phase 7, where prerequisite 5
   lives. Correction raised by C-models against its own work.
2. **`PaperBroker` forwards six of `MarketStreamProtocol`'s seven methods and drops
   `drain_gaps`.** Found by A, measured, reported to B, never fixed — B died first. Engine 2 then
   records **no `gap` line** into `data/raw/`, so a recording made through the daemon would claim
   to be continuous while spanning reconnects (invariant 11, and it disarms the book cutter's gap
   refusal). **Nothing has been recorded through the daemon, so the archive is intact.** B fixes
   it with A's test that walks `MarketStreamProtocol.__protocol_attrs__` rather than a test per
   method — nobody writes a test for the method they forgot.
3. **B's precedence reversal is outstanding.** The lead ruled the per-pair refusal goes *ahead*
   of the portfolio cap; `engines/risk/engine.py` still checks the cap first and its comment still
   argues the old way. B applies it, inverts the test that pinned it, and appends the reversal to
   the Decision entry rather than editing it.
4. **B's tripwire is now red on purpose.** `test_the_two_codes_spec_89_added_are_still_waiting_on_cs_prose`
   asserts the two codes are absent from `REASON_PROSE`; C-verify landed the prose, so it fires.
   **B deletes the tripwire and moves the codes into its renderable list**, which is exactly what
   the tripwire's failure message says to do. Until then it is one known, expected red.

### The two-enum trap, now a standing rule

B lost thirteen tests to it and wrote it up: `clients/store/contracts.py` and
`clients/kraken/contracts.py` both declare `OrderStatus`, `OrderSide` and `OrderType` with
matching spellings **on purpose**, so they compare equal and are never identical — `is` between
them is always `False`. B's engine 21 read every resting entry as "nothing resting" and published
`entry_orders_cancelled: True` with a live post-only buy on the book. `mypy --strict` cannot see
it, because `context.clients.kraken` is `Any`. **Alias one on import** and compare a client answer
only against the client enum. Now in `context/code-standards.md` under Money and numbers.


**Phase 6 — Decision and execution.** Engines 9 `order_book`, 14 `adaptive_router`, 16 `decision`,
18 `execution`, 21 `position_manager`, 22 `exit`, plus the fill simulator. Specs 80 to 99 in
`feature-specs/`. Approved by the operator 2026-09-16 with five rulings, all recorded below.

Phase 5 preflight, run by the lead at `e75bc26` on a quiet tree:
**14 criteria: 14 PASS, 0 FAIL, 0 PENDING, exit 0**
(`logs/verify/phase5-20260916-phase6-preflight-lead.log`).

---

## Read this before you claim anything

**1. Claim in your progress file before you write code, not after.** Write
`context/progress/<agent>.md` — the claim, the spec number and the files you will touch — *then*
begin. Phase 3 lost three build logs and no progress files, because progress files are written
before the work.

**2. Build-log entry at diagnosis, before the fix.** `docs/build-log/phase-6/<agent>.md`. The
moment you know *why* something is broken, write **What happened** and **Why**; then fix it; then
come back for **Fix**. A perfect fix with no entry is a bug that never happened.

**3. Every assertion is proven capable of failing, and the proof goes in the build log.** Write
the assertion, break the thing it tests, record that it went red, then fix it. Mutate from a
**byte copy** taken before you apply it and compare the hash in the same statement that restores
it — never `git checkout --`, because teammates do not commit and that deletes your own work. A
mutation that survives a *subset* has not survived; it has not been asked. An equivalent mutant is
a checked negative. Ask of every kill **which test killed it**.

**4. Phase 5's closing finding is the one to hold.** A calibrator fitted on the test window
survived every test and every metric, and the manifest did not catch it either, because the
manifest recorded what the caller *intended* while the mutation changed what the fit was *handed*.
What killed it was recomputing the expected rows from the public splitter. **A record of intent is
not a record of what happened.** Recompute what a number was supposed to be computed from.

**5. "Re-run the named test in isolation" is retired as a diagnostic.** It confirmed itself every
time for two phases. Capture the full output to a file and read the file; `unexplained` is an
acceptable thing to write.

**6. Ask the lead for an explicit stop before any baseline run.** Do not infer quiescence from an
idle-looking tree — three of us share this checkout. Say what you are about to run and wait.

**7. The recorder, the recording manager and the funding poller run continuously. Do not stop,
restart or reconfigure any of them.** Order-book history cannot be recovered retroactively.

**8. Everything that drives a trade runs against the fake client at tier 3** (friction ≈ 0.65%,
bar 1.625% — **invariant 5's reference figures, not the fake's: corrected by operator ruling S3,
2026-09-18.** At the fake's tier 3 engine 10 computes 0.308% and 0.462%, the fake's tier 1
clears too, and every message states its own run's figures; see the tracker). At tier 1 the cost gate is unreachable by construction — `hurdle_multiple` 1.5 needs
an expected move above 3.125% against a 3.0% target — and with an empty `.env` every pair blocks
at the cost gate. **Every criterion that drives a trade says tier 3 in its own message.** Do not
change `hurdle_multiple` and do not weaken the cost gate.

**9. Two numbers that are not defects.** 50.2% of test rows carry an incomplete feature vector and
engines 8 and 13 refuse those at any threshold: a chain producing very few candidates is that
number. And `max_concurrent_positions: 3` is inert at a $5,000 balance — one position is ~$3,333
notional — so no test may assert three concurrent positions.

**10. Stay in your lane, and talk to each other directly.** Check `context/ownership.md` before
editing. If you need another agent's interface, agree the contract, mock it, keep building, and
message them — do not route everything through the lead. An unanswered message usually means a
dead session, not a refusal: read their progress file before concluding anything.

**11. Done means all four green, no FAIL:**
`pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
`python scripts/verify.py --phase 6`. PENDING is expected mid-phase.

---

## The operator's five rulings, 2026-09-16

1. **The fill simulator is a paper broker in the client layer**, `src/acsoe/clients/paper/`,
   B-owned, implementing A's order surface and wrapping `clients.kraken` in paper mode. This
   corrects the operator's earlier ruling that it live under `engines/execution/`, which contract
   rule 3 forbids. **The correction is the operator's own.**
2. **Engine 16 stays and becomes a gate.** `is_gate = True`. Its job is the tick-coherence check —
   every approving engine judged *this* tick's candidate — and it *composes* the order intent. Its
   README says composes, never decides, about the assembly.
3. **Paper mode's balance is always the ledger**: `paper.starting_balances` adjusted by every
   recorded fill, whether or not the real fetch works. Invariant 2's table is reworded.
4. **The offset bandit is deferred to Phase 7.** Phase 6 places every entry at the best bid, as a
   recorded absence.
5. **The skeptic's training set is capped to a rolling window of the last 13 folds** — Phase 7
   work, not Phase 6. Finding 1's 0.531 survivor rate was measured on the uncapped skeptic and
   must be re-measured before it is cited anywhere.

Four smaller decisions, approved as the lead made them and overturnable by the operator: barriers
measured from the **fill price**; a resting entry fills only on a trade **strictly below** the
limit; stop and target touched in one tick resolves to **stop**; engine 9 estimates slippage at
the **whole quote balance** as an upper bound and never blocks on its own.

---

## Tasks

Claim by writing the spec number in your progress file. Never start a task another agent has
claimed. Waves are dependency order, not permission to idle: if wave 2 is blocked on someone
else's interface, agree it, mock it, and keep building.

### Lead — 4 tasks

| Spec | Task | Files | Acceptance |
|---|---|---|---|
| 80 | The five rulings and every seam into the authority documents; engine 16's Gate column and invariant 3 and 4 edits **before B builds it**; config keys on request | `context/*`, `config/default.yaml` | `docs_vocabulary` PASS; every seam has a row; no row names a field that does not exist |
| 81 | `close_intent`'s fail-closed default re-proven; the `_flag` truthiness fail-open fixed after its test goes red | `core/orchestrator.py`, `tests/core/` | every mutation observed red with its killing test named |
| 82 | Registration of 9, 14, 16, 18 and the manage chain 21, 22, 19 | `bootstrap.py` | `is_gate_matches_registry` PASS; held until specs 87 and 94 are green |
| 83 | The skeptic cap ruling and Finding 1's caveat recorded | `context/progress-tracker.md`, `docs/build-log/phase-5.md` | the ruling, its Phase 7 placement and the caveat are in both files |

### A — Platform — 4 tasks

| Spec | Task | Files | Acceptance | Wave |
|---|---|---|---|---|
| 84 | The order surface: `OrderRequest`, `OrderAck`, `OrderState`, `OrderClientProtocol`; the live client refuses every order call until Phase 8 | `clients/kraken/contracts.py`, `client.py`, `rest.py`, `tests/clients/kraken/` | live refusal makes zero transport calls, proven with a counting transport; `userref` bound asserted on the constraint, not the field name | 1 |
| 85 | Engine 3 publishes each pair's trade low, high and count since the previous tick | `engines/market_sensor/`, `tests/engines/test_market_sensor.py` | a range never spans two ticks; a silent pair is absent, never zero | 1 |
| 86 | The paper broker wired into `build_clients` for paper mode only; `scripts/cut_book_fixture.py` for C | `cli/engine.py`, `scripts/`, `tests/cli/`, `tests/scripts/` | the wiring test reaches the wiring through `build_clients`; the cutter refuses a window containing a gap | 2 |
| 87 | Rehearse 18, 21 and 22 through real orchestrator ticks | `tests/engines/test_trade_chain_rehearsal.py` | every scenario green on B's final code; four mutations red, each naming its killing test | 4 |

### B — Store and trading — 7 tasks

| Spec | Task | Files | Acceptance | Wave |
|---|---|---|---|---|
| 89 | Engine 11 refuses a second position **or** a resting entry on one pair — invariant 6, enforced nowhere today | `engines/risk/`, `tests/engines/test_risk.py` | block and pass differing in one input; no schema change | 1 |
| 88 | The paper broker and the paper ledger | `clients/paper/`, `tests/clients/paper/` | fill on a touch is red; post-only cross rejected; ledger after a round trip exact to the cent; a restart rebuilds it | 2 |
| 90 | Engine 16 `decision`, the tick-coherence gate and the order intent | `engines/decision/`, `tests/engines/test_decision.py` | a block and a pass per clause; intent absent on every block; `is_gate_matches_registry` PASS | 2 |
| 91 | Engine 18 `execution` | `engines/execution/`, `tests/engines/test_execution.py` | the same tick twice places once; no market order ever constructed; price rounded down | 3 |
| 92 | Engine 21 `position_manager` | `engines/position_manager/`, `tests/engines/test_position_manager.py` | both barriers resolve to stop; the hold holds only on `data_guard`; a stale entry is still cancelled during a hold | 3 |
| 93 | Engine 22 `exit` | `engines/exit/`, `tests/engines/test_exit.py` | no exit during a hold; a liquidation completes with `data_guard` blocking and the balance and `AssetPairs` fetches failing, each fallback recorded | 3 |
| 94 | Rehearse 9 and 14 through real orchestrator ticks | `tests/engines/test_feature_chain_rehearsal.py` | the chain now reaches engine 15; engine 10 reads engine 9's slippage, proven by recomputation | 3 |

### C — Interface and models — 8 tasks

| Spec | Task | Files | Acceptance | Wave |
|---|---|---|---|---|
| 95 | Engine 8's `is_buy` omitted on a refusal, with engine 15's read in the same change | `engines/prediction/`, `engines/skeptic/`, their tests | a refusal publishes no `is_buy`; engine 15 blocks naming the absence | 1 |
| 102 | The DI's fit and score at size (Phase 7 prerequisite 5) plus its peak-memory test (part of prerequisite 4) | `modelling/di.py`, `research/training.py`, `tests/modelling/`, `tests/research/` | equivalence recomputed against the old path; `di_leave_one_out_excludes_48_bars` still PASS; times reported in both orders | 1 |
| 96 | Engine 9 `order_book` and the committed book fixture | `engines/order_book/`, `tests/fixtures/book_sample.jsonl`, `tests/engines/test_order_book.py` | the walk matches a hand computation on a thin **and** a deep book; engine 9 never blocks; the README states the seconds-to-minutes bound | 2 |
| 97 | Engine 14 `adaptive_router` and the leaderboard fixture (≥ 2 models) | `engines/adaptive_router/`, `tests/fixtures/leaderboard_sample.json`, tests | weights recomputed from the rows; every weights-move assertion names the fixture as its subject | 2 |
| 98 | Engine 19 records what 18 and 22 publish | `engines/memory/`, `tests/engines/test_memory_rows.py` | each new source recorded; absent sources record nothing, never a zero | 2 |
| 100 | The Phase 6 criteria in `verify.py`, the tier-3 fake profile and the trade-producing subject | `scripts/verify.py`, `tests/verify/`, `tests/harness/` | every criterion PENDING, PASS and FAIL observed; every trade criterion names tier 3 | 2–4 |
| 99 | Operator prose for every new code, and a test that walks every engine's codes | `console/format.py`, `tests/console/` | the walking test observed red on an unmapped scratch constant, restored by hash | 3 |
| 101 | The console shows the position live | `console/`, `tests/console/` | a second tick's mark moves the rendered figure; a held position shows its reason | 4 |

**On C's load.** C has the most tasks by count — engines 9 and 14, engine 19, the reason map, both
fixtures, the criteria, the console and the DI prerequisite are all C paths. B's are fewer and
larger. If C runs as two sessions, they take disjoint files: engines and models (95, 96, 97, 98,
102) against verification and interface (99, 100, 101). Two sessions in one lane cost Phase 5 a
day; disjoint files and a claim in the progress file before any code are what stop it.

## Seams agreed between agents

| Seam | Producer | Consumer | Where |
|---|---|---|---|
| Order surface | A (84) | B (88, 91, 92, 93) | `clients/kraken/contracts.py` |
| Per-tick trade ranges | A (85) | B (92, 93) | `engines/market_sensor/contracts.py` |
| The paper broker's construction | B (88) | A (86) | `clients/paper/` |
| Placed and closed rows | B (91, 93) | C (98) | `engines/execution/contracts.py`, `engines/exit/contracts.py` |
| Order intent | B (90) | B (91), C (console) | `engines/decision/contracts.py` |
| Slippage estimate | C (96) | B (10 `cost`, already reads it) | `engines/order_book/contracts.py` |
| Every reason code and hold reason | A, B, C | C (99) | `console/format.py` |
| The book cutter | A (86) | C (96) | `scripts/cut_book_fixture.py` |

A seam agreed by message needs **one test with no double on either side**. A mock for a module
that does not exist yet needs a test that fails once it does.
