# Phase 8 — shared task list

## HANDOFF 0, 2026-09-21 — COSTED, NOT APPROVED. Nothing is built beyond the housekeeping.

**Phase 7 is CLOSED** by the operator on the write-up at `48faf18`. Nothing in Phase 7 —
number, figure, document or database — is re-run or changed. The Phase 7 runs are finished and
their watchdog is unregistered.

**The operator's goal for Phase 8, in their words:** *a working activation button that really
trades on Kraken, and a main window where I can see my wallet, the system's decisions, and
evidence it is running.* Quickly. **The account is tier 1, which approves nothing; the operator
will generate the volume to reach tier 3. Build for tier 3, and make tier 1 honest on screen:
the system must be visibly working and refusing, never a blank page.**

**Scope note, stated rather than glossed.** `ai-workflow-rules.md`'s Phase 8 row is **Live
readiness**: `platform/live_guard.py`, `close_all` end to end, and a 7-day soak. The operator's
goal adds the **live UI** and the **activation control**. This list carries both, and marks which
items are the workflow row and which are the operator's addition. The workflow row's criteria are
what `verify.py --phase 8` will judge; the UI items are the operator's acceptance.

**The costing is `docs/dataset/phase-8-findings.md`.** Every item below carries an estimate from
that document. **No item is approved.** The operator rules on scope and order after reading it.

## Standing rules for this phase

Carried from Phase 7 unchanged:

- claim before code; a build-log entry at diagnosis, **before** the fix;
- every assertion proven capable of failing, by mutation from a **byte copy written to disk**
  (Phase 7's harness kept it in memory and a hard kill would have lost the original);
- one gate per boundary, in a clean worktree, through the committed `gate.py`; the lead commits
  and **pushes** at every boundary;
- before any DONE, run all of `tests/verify`;
- **the recorder, the supervisor, `funding.py` and `fees.py` are never stopped, restarted or
  reconfigured.** A dead one is restarted; a live one is left alone;
- every decision recorded in `docs/build-log/phase-8/decisions-2026-09-21.md` with its reason;
- **anything over about an hour that the operator has not approved is a stop and a report.**

Two rules specific to this phase, because it ends with real money:

- **Nothing enables live trading without the operator's ruling.** Invariant 1's three switches
  stay as they are; Phase 8 proves them, it does not relax them.
- **The alphabetical ranking path is not deleted.** It is unplugged by config and left in place
  (operator ruling 2026-09-21).

## Boundaries

Each row is one gated boundary: one commit, one gate, one push.

### Housekeeping — DONE 2026-09-21, before the costing

| # | Item | Files | Acceptance | State |
|---|---|---|---|---|
| H1 | Unregister the Phase 7 watchdog task | (none; Windows task) | no `ACSOE*` scheduled task, no watchdog process | **done** |
| H2 | `scout.rank_feature: expected_move` **by option C** (operator ruling 2026-09-21): a separate daemon config, `default.yaml` untouched | `config/daemon.yaml`, `tests/platform/test_daemon_config.py` | the daemon config sets the key; `default.yaml` still leaves it absent so a clone runs; the two files differ nowhere else, enforced by a test | **done, gated (p8-h2-daemon-config).** Setting the key in `default.yaml` was attempted first and reverted: it makes engine 7 fail closed wherever `models.*_run_id` is absent (decisions D4a, D4b). **Open for the operator: which trained model a live daemon runs** — without `models.*_run_id` the daemon config still fails closed at engine 7 |
| H3 | The stale `rank_universe` docstring | `src/acsoe/engines/scout/contracts.py` | the docstring describes the committed state truthfully | **done, gated** — it now records that spec 75 is resolved (expected move), that the committed config does not set the key, and why setting it is not one line |

### Criteria — before anything else is judged

| # | Item | Owner | Acceptance |
|---|---|---|---|
| C0 | **Write Phase 8's criteria, PENDING first** (operator ruling: scoped to this build, nothing for deferred work) | C | four criteria registered, **all PENDING on the day they were written**, each observed PENDING, PASS and FAIL by `tests/verify/test_phase8_criteria.py` | **done, gated (p8-c0-criteria)** |

**Why this was first.** `verify.py --phase 8` registered only the two every-phase criteria and
therefore printed *"Phase 8 is green: every criterion PASS, zero PENDING"* while nothing of
Phase 8 existed. A phase that reports green before it starts cannot tell the operator anything
at its close.

**The four, and what each judges:**

| Criterion | Judges | Today |
|---|---|---|
| `live_client_serves_the_stream` | F1: the live facade forwards every `MarketStreamProtocol` member | PENDING — `recent_trades` and `drain_gaps` are not forwarded |
| `pair_rules_key_on_engine_names` | F3: the live mapper keys pairs as the engines and the websocket do, over spec 127's recording | PENDING — all 1,450 recorded pairs are keyed by REST names |
| `console_refuses_a_foreign_origin` | access control: a cross-origin POST is refused **and the operator's own kill switch still works** | PENDING — a foreign `Origin` is accepted today (201) |
| `daemon_reads_the_real_exchange` | the smoke run, judged on a committed digest: paper mode, **live client**, a universe scanned and refusals recorded | PENDING — no digest committed yet |

**Deliberately not written:** anything judging `mode: live`, the live order surface, `close_all`
live or the soak. The operator deferred all four on 2026-09-21, and a test asserts none of those
names is registered, so adding one later is a deliberate act. **Phase 8 cannot be closed on this
scope alone**, and that is the honest position rather than a green light.

### Path (a) — the system live and visible, no real fill

| # | Item | Owner | Acceptance |
|---|---|---|---|
| A1 | `recent_trades` on the live client (F1) | A | engine 3 publishes `stream_available: true` against the live client; the paper broker's `_observe_trades` does not raise; a recorded fixture proves the shape |
| A2 | `AssetPairs` keyed by the engines' pair names (F3) | A | engine 7's universe is non-empty against the live client; no pair is excluded as `pair_rules_missing` for a name-mapping reason |
| A3 | `TradeVolume` sends its pair and parses the real response (F2) | A | the fee tier comes back from the real endpoint for a named pair, and engine 10 prices a hurdle from it |
| A4 | Pair status respected (F4) | B + A | a `cancel_only` pair never enters engine 7's universe; a test proves it both ways |
| A5 | The main window: wallet and equity, mode and why, decision stream, positions and trades, funnel | C | each panel reads real rows; at tier 1 the screen shows refusals with their numbers, never a blank page |
| A6 | The activation control, paper/live explicit and safe by construction | C + Lead | it cannot go live by accident; what it writes is a `commands` row; a test proves the paper and live paths are distinguishable on screen |
| A7 | Console access control | A | the console is not reachable unauthenticated from the network |
| A8 | Live guard proven (workflow row) | A | all three switches individually required, each proven by a test |

### Path (b) — a real order placed and filled

| # | Item | Owner | Acceptance |
|---|---|---|---|
| B1 | The live order surface: place, cancel, query, with `userref` idempotency | A | against Kraken's own validate mode first, then one real minimum-size order |
| B2 | `close_all` end to end, live (workflow row) | Lead + B | the kill switch cancels every resting entry and closes every position within one tick; a daemon killed mid-liquidation finishes it on restart |
| B3 | First live trade, watched | Lead | one real order placed, filled and recorded, with its walk-through written up as Phase 6's first paper trade was |
| B4 | Soak (workflow row) | A | `tests/fixtures/soak_digest.json`: one unbroken `run_id`, contiguous `cycle_id`, 7 continuous days, zero unhandled exceptions |

### Carried from Phase 7, not yet scheduled

| Item | Source |
|---|---|
| The loss-streak and drawdown breakers have no recovery path | `phase-7-findings.md` Part III §2; tracker Open Questions |
| Exit slippage: stops overshoot, targets do not | Part III §3 |
| The mutation harness restores from memory only | tracker Open Questions |
| The rehearsal's identity check ignores the process segments inside `shap_ref` | tracker Open Questions |
| The non-deterministic native crash in polars | tracker Open Questions |

**None of these is in Phase 8's critical path and none is started.**
