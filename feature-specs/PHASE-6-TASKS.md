# Phase 6 — shared task list

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
bar 1.625%). At tier 1 the cost gate is unreachable by construction — `hurdle_multiple` 1.5 needs
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
