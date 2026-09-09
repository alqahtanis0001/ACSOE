# Progress Tracker

**Lead-only file.** Teammates write `context/progress/<agent>.md`. The lead merges here after a passing verify run.

## Current Phase

**Phase 2 — Data spine. In progress**, opened 2026-09-09. Phase 1 was confirmed green at the gate first: 10 criteria, 10 PASS, 0 FAIL, 0 PENDING. Nine Phase 2 specs (25 to 33) plus three Phase 3 engines (34 to 36) running concurrently, approved by the operator with three additions. **Three teammates this phase: A carries it, C builds the criteria and pays the Phase 1 console debt, B has one Phase 2 task and the three concurrent Phase 3 engines.**

*Phase 1 — Interface. Green and closed*, verified 2026-09-09: 10 criteria, 10 PASS, 0 FAIL, 0 PENDING. All nine specs (16 to 24) built by C alone; A and B had no Phase 1 work and none was invented for them. The lead re-verified independently of C's report: `pytest` 707 passed, `mypy --strict src/` clean across 35 files, `ruff check src/` clean. Survived three IDE crashes mid-phase with no lost work. **Phase 2 — Data spine is next**, and it opens carrying two obligations recorded under Open Questions, one of them a live defect in `core/`.

*Phase 0 — Structure. Green and closed*, verified 2026-09-08: 7 criteria, 7 PASS, 0 FAIL, 0 PENDING. All 16 feature specs built, all three teammates and the lead reporting nothing outstanding.

## Current Goal

Phase 2 — the data spine: engines 1, 2, 3 and 4, the historical OHLCVT loader, and the recorder engine superseding `scripts/record.py`. The `core/` command reader was fixed first, before any engine work, and is done. The persisted system mode is spec 31 (B) and spec 32 (C), with the `core/` write staying lead work.

*Phase 1's goal, for the record:* the full console against the seeded database — status band, positions, cycle feed, history, research views, WebSocket updates and the three commands. Nothing in the console reads a live exchange; it renders the Phase 0 seed, which is the whole point of building the interface before the backend. All delivered.

*Phase 0's goal, for the record:* `scripts/verify.py` first, then the package skeleton, `core/` contracts and three-chain orchestrator, `platform/` config, clock, logging and live guard, CLI entrypoints, `config/default.yaml`, SQLite schema and migrations, store client, seed generator, fake Kraken client, test harness, and `scripts/record.py`. No engines. All delivered.

## Phase Status

A phase is green only when `python scripts/verify.py --phase N` passes every criterion.

| Phase | Status | Verified |
|---|---|---|
| 0 — Structure | **Green** | 2026-09-08 — 7 PASS, 0 FAIL, 0 PENDING; re-verified 2026-09-09 at the Phase 1 gate, same result |
| 1 — Interface | **Green** | 2026-09-09 — 10 PASS, 0 FAIL, 0 PENDING (9 at close, plus `toolchain_green` once it was registered for every phase) |
| 2 — Data spine | **In progress** | Opened 2026-09-09. `commands_round_trip` already PASS |
| 3 — Economics | Blocked on 2 — **but 10, 11 and 17 are being built now** | See the overlap note under In Progress |
| 4 — Memory and replay | Blocked on 3 | — |
| 5 — Models | Blocked on 4 | — |
| 6 — Decision and execution | Blocked on 5 | — |
| 7 — Evaluation | Blocked on 6 | — |
| 8 — Live readiness | Blocked on 7 | — |

## Completed

- Phase 0 feature specs written to `feature-specs/`, 16 of them, and approved by the operator with three additions (spec 11 `is_primary` as a database constraint, spec 12 carrying the off-by-one reasoning, spec 14 requiring a negative test for the network guard).
- **Phase 0 itself. Green on 2026-09-08.** All 16 specs built, across four workers. Merged from the three progress files at phase close; the narrative account is `docs/build-log/phase-0.md`.

| Agent | Specs | Delivered |
|---|---|---|
| C — Interface | 00, 01, 02, 14, 15 | `scripts/verify.py` and its criterion framework, the seven Phase 0 criteria each proved twice (PENDING on an empty tree, PASS on a fabricated subject), `docs_vocabulary` registered for every phase with the retired-term table parsed rather than hardcoded, the test harness and `tests/fixtures/` structure, the network guard with its negative test, and the fake Kraken client. |
| A — Platform | 03, 07, 08, 09, 10 | The src-layout package and `pyproject.toml` with the `dev`/`research` split, `platform/config.py` and every refusal it owes, clock and structlog JSON logging with two-layer redaction, the three CLI entry points with a lazily-importing dispatcher, and `scripts/record.py` with a committed 25-line sample carrying a genuine `gap` marker. |
| B — Store | 11, 12, 13 | `db/migrations/` and the forward-only runner, the store client, and the seed generator producing all six Phase 3 fixtures — each overshooting its threshold rather than sitting on it. |
| Lead | 04, 05, 06 | `core/` contracts and the three-chain orchestrator, `bootstrap.py` and the engine registry, and `config/default.yaml`. |

- **Nothing is outstanding for any agent.** Every open question and escalation raised during the phase is resolved: the `Config` Protocol mismatch, `.gitattributes`, `pyyaml`'s absence from the stack table, `is_primary` scoping, the `safety` threshold key names, the `docs_vocabulary` false FAIL, and the entry-point shapes in `core/` and `cli/research.py`.
- **The operator's nine values landed mid-phase** and broke three of A's tests by making the config *more* valid. The assertions were moved onto a fabricated config rather than deleted, the shipped file gained the opposite assertions, and a new test scans the file's `Operator-chosen` marker so a tenth key that arrives *with* a value is still noticed.

- **Phase 1 itself. Green on 2026-09-09.** All nine specs (16 to 24) built by C alone. The narrative account is `docs/build-log/phase-1.md`.

| Agent | Specs | Delivered |
|---|---|---|
| C — Interface | 16–24 | The eight Phase 1 criteria in `verify.py`, each proved PENDING on an absent subject and PASS on a fabricated one; the console read layer over a read-only SQLite connection proved read-only by attempting real writes; the design tokens, self-hosted Plex faces and single-page shell with the live-mode amber frame; the status band with presence-based restart detection; the cycle feed with its counts-based empty state; history; the research views with the SHAP pane's honest empty state; the WebSocket watermark push; and the three commands behind a SQLite authorizer that denies every table but `commands`. |
| Lead | — | Specs 16–24 and the shared task list; the checkpoint review; three rulings taken to the operator; the `run_id` presence-test correction across `ui-context.md`, spec 16 and spec 19; the seam row for the Phase 2 persisted mode; and the diagnosis of the seed-path fault and the `core/` command-reader defect. No implementation — Phase 1 needed none from `core/`. |

- **Three IDE crashes mid-phase cost no work.** Each time the tree was re-assessed against the gate rather than the agent's transcript, and C was restarted from verified state. What the crashes did cost was C's two documentation files, twice — both times the code had landed and the build log had not. Recorded here because it is an argument for the "write as you work" rule rather than a mishap: the rule is what made the loss recoverable in minutes.

## In Progress

**Phase 2 — Data spine.** Shared task list: `feature-specs/PHASE-2-TASKS.md`.

| Spec | Title | Owner | Phase |
|---|---|---|---|
| 25 | Kraken REST and WebSocket clients | A | 2 |
| 26 | Engine 1 `exchange` | A | 2 |
| 27 | Engine 2 `market_data_recorder` | A | 2 |
| 28 | Engine 3 `market_sensor` | A | 2 |
| 29 | Engine 4 `data_guard` | A | 2 |
| 30 | Historical OHLCVT loader | A | 2 |
| 31 | Persisted system mode | B | 2 |
| 32 | Status band reads Running and Frozen | C | 2 |
| 33 | Phase 2 criteria in `verify.py` | C | 2 |
| 34 | Engine 10 `cost` | B | **3, built concurrently** |
| 35 | Engine 11 `risk` | B | **3, built concurrently** |
| 36 | Engine 17 `safety` | B | **3, built concurrently** |

**Done before the phase opened, by the lead and not assigned: the orchestrator command reader.** It looked up a `claim_pending_commands` the store has never had, so a daemon wired to the real store ignored every command ever written. Two further breaks in the same path were found while fixing it: `mark_command_consumed` was called with the wrong signature, and `mark_close_all_consumed` did not exist either — so even a *successful* liquidation left its row claimed-and-unconsumed for the startup replay to re-run on the next boot, against an already-flat account. The startup re-application of interrupted commands is now wired and had never existed at all. `commands_round_trip` is registered for phase 2 and passes, driving the real `StoreClient` through the real `Orchestrator` with no double anywhere in the seam.

**Phase 3's deterministic engines overlap Phase 2 deliberately.** Operator decision, 2026-09-09. Engines 10 `cost`, 11 `risk` and 17 `safety` are built by B during Phase 2, against a mocked Kraken client and the Phase 0 seed.

*The reason the overlap is safe, and the boundary it stops at:* **these three depend on the exchange only through a contract**, so B agrees the fee-tier and pair-rule shape with A against `clients/kraken/contracts.py` up front and builds against a mock of it — the same "agree, mock, continue" rule that governs every seam. And **the Phase 0 seed already carries every fixture `safety` needs**: all six of its inputs are written by engine 19 `memory`, which is Phase 4, which is exactly why B built those fixtures in Phase 0. Testing `safety` has never depended on anything later than the seed.

**Engine 7 `scout` is deliberately not in the overlap.** It needs a real tradable universe computed from live pair rules and balances, so it stays in Phase 3 proper. The line is drawn at "depends on a contract" versus "depends on real data".

**These three do not count toward Phase 2's gate, and Phase 3 stays closed** until Phase 2 is green *and* they are wired to A's real client. An engine that has only ever seen a mock is not a finished engine.

**The operator's three additions at approval**, all folded into the specs:

1. **Spec 25** — the envelope check needs a paired positive test. A parser that raised on every response would satisfy "a 200 with a populated `error` array raises" on its own; assert that a 200 with an empty `error` array parses cleanly.
2. **Spec 30** — the loader marks gaps and never interpolates, stated in the spec rather than left implied. A missing candle means no trades occurred, and the distinction is load-bearing for Phase 4's triple-barrier labelling: a synthesised candle at a price that never traded invents a barrier touch and produces a fabricated label. It is precisely the kind of thing an implementer fixes helpfully.
3. **Spec 32** — the Phase 1 deferral test is deleted, and the deletion is recorded in the build log with its reason. Deleting a test to make a spec buildable is normally what this project refuses; the written trail is what separates a retired test from an inconvenient one.

## Next Up

- **Phase 3 proper**, once Phase 2 is green and B's engines 10, 11 and 17 are wired to A's real client: engine 7 `scout`, which needs a real tradable universe and was deliberately left out of the Phase 2 overlap.
- **Phase 2 carries a debt from Phase 1, and it is not optional.** The status band must gain its `Running` and `Frozen` readings in Phase 2, because Phase 2 is where a daemon first runs and a band reading `Idle` over a running system is actively wrong. The approach is already decided: the command reader in `core/` persists the mode it already owns, and the console reads it as a fact rather than inferring it. It needs a column from B and the write from the lead, so it is a Phase 2 planning item for two agents, not a C task. See the `## Restart is visible` section of `ui-context.md` and the seam row in `ownership.md`.
- **Before Phase 4:** replace the cycle feed's full scan of `block_records` with a most-recent-N read on B's store surface. Harmless while the table holds a seed; engine 19 `memory` starts writing a row per guard per tick in Phase 4, which is when it stops being harmless.
- **`RUF001` on `tests/console/test_format.py` is suppressed deliberately, not fixed.** `U2212 = "−"` must be the U+2212 glyph: it is the fixture for the minus-sign rule, and "correcting" it to an ASCII hyphen would make the test pass against the exact character it exists to reject. Carries a rule-named `noqa` with its reason, and the general policy now lives in `context/code-standards.md` under Python — name the rule, give the reason, and never suppress a lint to make a failing check pass.
- **Deferred from Phase 0, still deferred:** widening `TOOLCHAIN` beyond `src/`. `mypy --strict scripts/` reports 2 errors in `verify.py`, and `ruff check tests/` now reports **3** violations, not the 2 recorded at Phase 0 close. The new one is `RUF001` on `tests/console/test_format.py:25`, where `U2212 = "−"` **must** be the U+2212 glyph — that constant is the fixture proving the minus-sign rule, and it starts passing against a pasted hyphen the moment the character is "corrected". The `noqa` policy that widening would need is now written (see the bullet above and `code-standards.md`), so the remaining blocker is only the decision itself. The operator declined to widen at the Phase 1 boundary, deliberately: registering `toolchain_green` everywhere was taken on its own, and changing what the toolchain covers is a separate change with its own blast radius.
- **A's standing instruction:** `scripts/record.py` should be left running from now on. Order-book and spread history cannot be recovered retroactively, and Phase 2's `recording_report.json` criterion needs a continuous span of at least 24 hours.

## Locked Decisions

Settled with evidence. Do not relitigate. Changing one requires the operator, not an agent.

- Kraken Pro, spot only. No margin, futures, leverage, or shorting.
- Fees read live from `TradeVolume`. Minimums read live from `AssetPairs`. Never hardcoded.
- Reference friction: ~1.25% round trip at tier 1, ~0.65% at tier 3.
- Break-even win rate: ~61% at tier 1, ~48% at tier 3.
- Decision bar 15 minutes; hold 2–12 hours; loop tick 1 minute.
- Triple-barrier labels: +3% / −1.5% / 48-bar timeout.
- Post-only limit entry, cancel if unfilled, never chase.
- Tradable universe computed per tick from `ordermin`, `costmin`, tick size, live spread and balance. No account-size thresholds.
- All Kraken quote currencies scanned; crypto-quoted pairs disabled by default.
- DI fitted on the predictor's training set, MinMax-scaled, rolling percentile threshold, 30-day per-pair window.
- DI threshold crossings also feed the regime engine.
- Alpha attribution uses the full equity curve including cash periods, not trade windows.
- Execution offset bandit pooled by spread tier, not per pair.
- Promotion metric haircut for the number of models tried.
- Backtest training window capped at a rolling 90 days; retrains weekly during walk-forward.
- An LLM is not the predictor. Any alternative method must first clear the fee hurdle.
- Build order is structure, then interface, then backend.
- Console is built against the real schema with seeded fake data, so no rework when real data arrives.
- Paper mode until a validated model exists. A readiness gate, not an account-size gate.

## Open Questions

- **DECIDED 2026-09-09, and it is the first task of Phase 2, before any engine work.** The operator ruled on the defect below. The fix composes the reader from the four methods `StoreClient` already has — `pending_commands()`, `claim_command(command_id, *, claimed_at, run_id)`, `claimed_unconsumed_commands()` and `mark_command_consumed(command_id, *, consumed_at)` — **entirely inside `core/`, renaming nothing in B's directory.** It also wires the startup re-application of claimed-but-unconsumed rows, which is absent today. And it lands with a **Phase 2 criterion that drives the real `StoreClient` — not a double — through `activate`, `freeze` and `close_all`, asserting the mode changed and the row was consumed**: a criterion that would have caught this. **Phase 0 was reported green with the kill switch inert**, and that is the point worth carrying: `orchestrator_empty_registry` runs against an empty registry and every other test of the command path uses a test double, so nothing in the suite ever put the real store behind the real reader. A gate that only ever exercises a seam through a double does not test the seam; it tests the double. The same question should be asked of every other seam in `ownership.md` before its phase closes.
- **RESOLVED 2026-09-09, before Phase 2 engine work began — the orchestrator reads no commands, so the kill switch does not work.** Fixed by the lead as the first task of the phase, composed from the four methods `StoreClient` already exposes, entirely inside `core/`, renaming nothing in B's directory; the startup re-application of claimed-but-unconsumed rows is wired and had never existed. A third break in the same path turned up while fixing it: `_clear_close_intent_if_finished` called a `mark_close_all_consumed` the store has never had, so even a *successful* liquidation left its row unconsumed for the startup replay to re-run on the next boot against an already-flat account. `commands_round_trip` is registered for phase 2 and PASSes. The original finding, kept because the lesson is the transferable part: Found 2026-09-09 by C while building spec 24, confirmed and widened by the lead. `core/orchestrator.py:173` looks up `store.claim_pending_commands` via `getattr`; **`StoreClient` has no such method.** It exposes `pending_commands()`, `claimed_unconsumed_commands()`, `claim_command(command_id, *, claimed_at, run_id)` and `mark_command_consumed(command_id, *, consumed_at)`. So the lookup returns `None`, the reader logs `commands_skipped` at debug level and returns, and **a daemon wired to the real store would silently ignore every Activate, Freeze and Close-all ever written.** Two further faults in the same method: `_mark_consumed` calls `mark_command_consumed(command, now=...)` against a signature of `(command_id, *, consumed_at)`, which would raise if it were ever reached; and **the startup re-application of claimed-but-unconsumed rows is not wired at all** — nothing in `src/` calls `claimed_unconsumed_commands()`, though `architecture-context.md` requires it and names the exact failure it prevents, a daemon killed mid-liquidation coming back with `close_all` marked done and positions still open. The only implementations of the orchestrator's shape are a test double in `tests/core/test_orchestrator.py` and C's documented adapter in `tests/console/test_commands.py`, which is why every gate to date has passed over it. **This is Phase 0 work in `core/orchestrator.py`, which is lead-only, so it is the lead's to fix and no teammate's.** Harmless in Phase 1 — no daemon runs and the console only writes rows — and it bites the moment one does, which is Phase 2. The cheapest correct fix stays entirely inside `core/`: compose the reader from the four methods the store already has, rather than renaming anything in B's directory. **Fix before any Phase 2 work begins.**
- **RESOLVED 2026-09-09 — `toolchain_green` is now registered for every phase**, via `register_every_phase`, exactly as `docs_vocabulary` is. `TOOLCHAIN` stays scoped to `src/`: the operator deliberately did not widen it to `tests/` or `scripts/`, so the two Phase 0 findings in `verify.py` and the three in `tests/` remain out of scope for the gate. One consequence to expect: every phase's gate now runs `pytest`, so the intermittent seed-path crash below can now surface as a FAIL on any phase rather than only Phase 0. The account of the hole this closed:
- *Was open, for the operator at the Phase 1 boundary — `toolchain_green` was registered for Phase 0 only, so from Phase 1 onward the gate never ran the tests.* Found 2026-09-09: `scripts/verify.py --phase 1` reported `7 PASS, 0 FAIL, 2 PENDING` while `pytest` was reporting `2 failed, 639 passed`. Nothing in the report was wrong — no Phase 1 criterion makes a claim about the suite — but "a phase is done when `verify.py --phase N` passes every criterion" is the project's definition of done, and for every phase after 0 that definition currently cannot see a red suite. Run-protocol step 4 covers the gap by making each agent run all four commands themselves, which is why this was caught, but it depends on a person following a procedure rather than on the gate. **The obvious fix is to register `toolchain_green` for every phase, exactly as `docs_vocabulary` already is.** It is a change to what every phase asserts, so it belongs at a phase boundary and to the operator, not mid-phase and not to an agent — the same reasoning that deferred widening `TOOLCHAIN` beyond `src/` out of Phase 0. Note the two interact: registering it for every phase also spreads the intermittent seed-path crash across every phase's gate, so the crash question above should be settled first or at the same time.
- None otherwise blocking. The nine operator-required values are set; see below.
- **Resolved 2026-09-09 — the console screens with no design.** History, the research views, the leaderboard and the SHAP view are named in the Phase 1 criteria and designed in no context file. Split in two at planning: history and the leaderboard have no design but do have data in the Phase 0 seed, and `ui-context.md` already grants an undesigned screen the cycle feed's table treatment, so specs 21 and 22 build them under it. The SHAP view has neither design nor data — `rejections.shap_ref` points at a Parquet artefact the training pipeline does not write until Phase 5 — so spec 22 renders an honest empty state and bans a placeholder chart. Put to the operator at approval rather than decided silently; the operator confirmed the empty state stands.

## Operator-chosen starting values (2026-09-08)

The operator supplied the nine values the context files name but never specify. **These are starting values, not settled ones — explicitly subject to revision once Phase 3 measures what the economics actually are.** They exist so Phase 3 can run, not because anyone yet knows they are right.

| Key | Value |
|---|---|
| `trading.hurdle_multiple` | 1.5 |
| `trading.risk_fraction_per_trade` | 0.01 |
| `trading.max_concurrent_positions` | 3 |
| `trading.entry_unfilled_window_s` | 300 |
| `trading.base_reporting_currency` | USD |
| `paper.starting_balances` | `{USD: "5000.00"}` |
| `safety.max_drawdown_pct` | 0.10 |
| `safety.max_consecutive_losses` | 5 |
| `safety.max_errors_in_window` | 20 |

The OPERATOR REQUIRED machinery stays in place. It is what will protect the tenth such key, and the loader still refuses to start on a null.

### Two consequences of these values, checked by arithmetic before they surprise anyone

**1. At tier 1, nothing clears the cost gate — by construction.** Invariant 5 requires `net_edge > hurdle_multiple x friction`, which rearranges to `expected_move > (1 + hurdle) x friction`. At `hurdle_multiple: 1.5` that is `2.5 x friction`. Tier 1 friction is ~1.25%, so a candidate needs an expected move above **3.125%** — and the target barrier is **3.0%**. The gate is therefore unreachable at tier 1 with these barriers. At tier 3 (~0.65% friction) the bar is 1.625% and clears comfortably.

This is consistent with the project's cost-adaptive selectivity and with "a negative result is a valid result", so it is recorded rather than corrected. But **Phase 6 must not read zero trades at tier 1 as a bug**: that is these three numbers interacting exactly as specified. Either the hurdle comes down, the target goes up, or tier 1 is understood to be a no-trade regime.

**2. `max_concurrent_positions: 3` is inert at this balance.** Risk of 1% of $5,000 is $50; a 1.5% stop implies ~$3,333 of notional per position. Three would need ~$10,000 against a $5,000 balance, so the **balance binds first and concurrency is effectively 1**. Invariant 6 already forbids allocating cash the account does not hold, so nothing is wrong — but a Phase 6 test asserting three simultaneous positions would fail for reasons unrelated to the code under test.

## Decision history

Four onboarding audits, in order. Later sections override earlier ones where they conflict; superseded lines are struck through. The current design is always `engine-contracts.md` and `architecture-context.md` — this section is the record of how it got there.

### After the first audit

The lead's onboarding audit found 25 issues. These were resolved by the operator:

- `core/` holds contracts and the orchestrator only. Config, clock and logging moved to `platform/`, owned by A.
- ~~The orchestrator has three runtime chains: ingest (1–4), opportunity (5–18), manage (21, 22, 19).~~ **Superseded by the fifth audit** — the first chain is the *guard* chain and carries engine 17 as well: 1, 2, 3, 4, 17. The opportunity chain is 5–16 plus 18. Engines 20 and 23 still run in an offline chain via `acsoe research`. Without this split, positions were never watched, and freeze would have stopped the recorder.
- `scripts/verify.py` is sequenced first in Phase 0 and reports PASS, FAIL or PENDING, so criteria can exist before the code they judge.
- Every criterion runs offline against a recorded artefact. `--live` is opt-in and never required for a phase to be green.
- Each agent owns `tests/` mirroring its own source paths, and its own `docs/build-log/phase-N/<agent>.md`.
- One working tree, one branch, no per-teammate branches. The ownership map is the only concurrency control. The lead commits at task boundaries; teammates do not commit.
- Timeout is 48 bars, which is 12 hours and consistent with the 2–12 hour horizon. It was 24 bars, which is 6.
- Break-even at tier 3 is ~48%, not 54%. The tier 1 figure of ~61% was correct.
- Engine 6 renamed `macro_context` to stop colliding with the `context/` directory.
- Engine 13 `anomaly` moved from B to C — it is a model engine built in Phase 5.
- The Dissimilarity Index lives inside `engines/prediction/`. The execution offset bandit lives inside `engines/execution/`. Neither is an engine.
- A `recorder` client was added to `Clients` so engine 2 can append JSONL without violating contract rule 4.
- Friction assumes maker entry and taker exit — the worst realistic case.
- Paper mode falls back to tier 1 on a failed fee fetch and logs it. Live mode still blocks.
- `config/LIVE_CONFIRMED` is compared against `context.now` in UTC.
- The lead authors `config/default.yaml`.

### After the second audit

The lead's second audit found 22 issues, most of them decisions that had reached some files and not others. Resolved:

- `code-standards.md` corrected — config, clock and logging are in `platform/`, not `core/`.
- `core/` imports nothing. `Config`, `Clock` and `Clients` are Protocols declared in `core/contracts.py` and implemented in `platform/` and `clients/`.
- ~~Chain 2 is exactly three engines: 21, 22, 19.~~ **Superseded by the fourth audit** — there are now three runtime chains; see below. Engine 20 still runs offline.
- Paper-mode fallbacks are stated once, in a table, scoped to mode. Live mode always blocks. Fee falls back to tier 1; balance falls back to `paper.starting_balances`, a per-currency map; pair rules and spread have no fallback and block the pair.
- `clients/recorder/` exists and belongs to A.
- Per-task done is **no FAIL**. PENDING is expected mid-phase and only reaches zero at phase close.
- Every criterion must pass on a fresh clone. Evidence lives in committed fixtures under `tests/fixtures/`, never in gitignored `data/`. `--live` verifies the real run and is never required for green.
- `logs/` exists, belongs to A, and is gitignored.
- The command table has defined semantics and a reader: the orchestrator, in `core/`, at the top of every tick, marking each command consumed.
- The three-switch live check is `platform/live_guard.py`, A's. Three conditions, not three read paths.
- `feature-specs/` has a mandatory template, so Scope Limits is a defined section.
- C owns `tests/` root, `conftest.py` and `tests/fixtures/`. A creates `data/` and `logs/`.
- "Within one tick" means one `tick_size` from `AssetPairs`.
- `console.poll_interval_ms` must be under a quarter of `console.stale_after_ms`, enforced by config validation.
- ~~The eight non-ML engines are enumerated: 1, 2, 3, 4, 10, 11, 16, 17.~~ **Superseded by the third audit** — scout is deterministic, so there are nine and engine 7 is among them.
- `.claude/settings.local.json` and `logs/` restored to `.gitignore`.

### After the third audit

- `.gitignore` gained `!tests/fixtures/**`. Without it `*.jsonl` and `*.parquet` silently swallowed every committed fixture, and the entire fresh-clone verification strategy failed without an error message.
- The four phase criteria that depended on gitignored directories now name committed fixtures: `record_sample.jsonl`, `recording_report.json`, `labelled_sample.parquet`, `soak_digest.json`. The real runs moved behind `--live`.
- Engine 20 has a caller. A third `OFFLINE_CHAIN` is invoked by `acsoe research`, never by the daemon. Engine 23 runs there too.
- **Scout is deterministic.** Design question resolved: engine 7 contains no model — the universe filter is arithmetic and the ranking is a fixed score. It is therefore protected by invariant 4, and the non-ML count is nine, not eight. Engine 15 `skeptic` is the only model gate, and it can only veto.
- ~~`state["system_mode"]` is now an orchestrator key.~~ **Superseded by the fourth audit** — the persistent key is `state["system"]`, holding `mode` and `close_intent`.
- **The kill switch is `close_all`.** No fourth mechanism. Freeze stops new trades and keeps managing open ones; close_all ends exposure.
- The orchestrator mints `run_id` and `cycle_id`, and holds the `Clock`. Engines see only `context.now`.
- `paper.starting_balances` is a currency-to-amount map, not a scalar. One number cannot satisfy the per-quote-currency invariants.
- Creating a directory is not owning the runtime data written into it. Rule 1 governs source files.
- `console.poll_interval_ms` default dropped to 500 so the Phase 1 criterion is achievable; the criterion is now twice the poll interval.
- `is_gate` is asserted by `verify.py` against the registry table, so a mis-registered gate fails loudly.

### After the fourth audit

- **Freeze no longer stops the recorder.** ~~Engines 1–4 are now their own ingest chain.~~ **Renamed by the fifth audit** — it is the guard chain, 1, 2, 3, 4, 17. It runs in every mode; only the opportunity chain is switched off by freeze. Order-book history is never lost to a freeze.
- **The safety engine freezes via the commands table.** It cannot write `state["system"]`, so it writes a `freeze` or `close_all` row through the store, which the orchestrator consumes next tick. Same channel as the console, and every stop is an audit row.
- **State is fresh every tick.** The only persistent region is `state["system"]` — `mode` and `close_intent` — carried by the orchestrator. Manage-chain engines read prior decisions from the store, never from stale state keys.
- `close_intent` is the kill switch's data path. `frozen` alone means stop opening; `frozen` plus `close_intent` means liquidate now.
- `run_id` lives only on `context.run_id`. The duplicate state key is gone.
- Engine 23 is registered in `OFFLINE_CHAIN` only, which `cli/research.py` assembles. `bootstrap.py` never imports from `research/`, so invariant 5 holds.
- Each agent deposits its own evidence fixtures under `tests/fixtures/`; C owns the structure and shared fixtures.
- Anomaly is a data-quality gate (unsupervised, over market data) and stays protected. Skeptic is a learned opinion about the trade and stays excused. The distinction is now stated.
- `acsoe research` ships in Phase 0 as a stub.
- The stray empty code fence in `engine-contracts.md` is removed.

### After the fifth audit

The fifth audit found nine issues. Four of them were one question wearing four hats — what runs unconditionally, and who may write the persistent state — so they were resolved together rather than patched one at a time.

- **Engine 17 `safety` moved from the opportunity chain to the guard chain.** It was second to last in a chain that stops at the first block or PASS, so the circuit breaker only ever ran on ticks where every other gate had already passed. An account in drawdown whose candidates were all being rejected by the cost gate would never have tripped it. The guard chain is now 1, 2, 3, 4, 17, runs every tick in every mode, and never breaks early — a bad-data block must not stop safety from evaluating. Safety is stage 1 gatekeeping, not stage 3 judgement.
- **The guard chain records the first blocker, not the last.** Two guards can block on one tick; the reason `memory` logs is the first one.
- **Safety is idempotent about what it emits.** It runs every tick now, so it writes a command row only when that row would change the state: `freeze` only while running, `close_all` only when positions are open and no intent is already set. Otherwise a sustained drawdown would append a freeze row every sixty seconds forever.
- **`close_all` cancels resting entry orders as well as closing positions.** A post-only limit still on the book is not a position and survived the old definition, so the emergency stop could leave an order that filled minutes later and re-opened exposure. Engine 21 cancels, engine 22 closes.
- **The orchestrator clears `close_intent`, not engine 22.** The old wording had an engine writing `state["system"]`, which rule 2 and the state-keys section both forbid. Engines now report `entry_orders_cancelled` and `positions_closed` in their own `data`; the orchestrator clears the intent only when both are true, so a failed cancel or close retries next tick instead of being lost.
- **Command consumption is two-phase.** `claimed_at` when read, `consumed_at` when the effect completes. A daemon killed part-way through a liquidation used to restart with the command marked done, the in-memory intent gone and positions still open. Unconsumed rows are now re-applied at startup.
- **Mode always starts `idle` and is never restored from the store.** A crashed daemon comes back not trading, with the manage chain still watching what is open.
- **Engine 3 `market_sensor` owns the decision-bar clock.** It publishes `bar_closed`; engine 5 `feature` returns PASS when it is false. Nothing previously named which engine stopped the chain on a non-bar tick, which is the mechanism the entire cadence rests on.
- **`scripts/verify.py` may import both the live path and `research/`.** It is neither, which is what lets its `is_gate` assertion cover engines 20 and 23.
- **A `docs_vocabulary` criterion runs in every phase.** Every audit so far has found a decision that reached three files and not the fourth; each file stays self-consistent, so reading does not catch it and grep does. Retiring a term now includes adding it to the table in `ai-workflow-rules.md`.

### After the sixth audit

- **README said eight non-ML engines; it is nine.** `project-overview.md` had been corrected when scout was ruled deterministic, and the README had not. The `docs_vocabulary` check passed over it because a bare count is not a distinctive token, so `eight` used as a count of the engines without ML is now a retired term in its own right. A check that only catches renamed identifiers misses corrected facts.
- **Ownership's Phase 0 row for A listed two CLI entrypoints; the phase scope lists three.** A builds `acsoe engine`, `acsoe console`, and `acsoe research` as a stub reporting no offline engines until Phase 4.
- **The manage chain now holds when `data_guard` blocks.** Previously undecided: with the opportunity chain skipped but the manage chain still running, engine 22 could have exited a position on a target or stop computed from the same stale or negative-spread data the guard had just rejected — a fabricated trigger acting on real money. Engines 21 and 22 now place no exit on such a tick, still run so that engine 19 records it, and engine 21 reports `hold_reason`.
- **`close_intent` is the one exception, and the only deliberate override of a gate in the system.** An emergency stop proceeds regardless of the guard, because a bad fill is a smaller risk than unknown exposure. It overrides in the direction of less exposure, never more, which is why it does not violate invariant 4. Blocks from engines other than `data_guard` do not hold the manage chain: they concern whether a new trade is wise, not whether an open position's data is trustworthy.
- Phase 6 gained a criterion that proves both halves — a triggered stop does not exit on a `data_guard` tick, and the same position under `close_intent` does.

### After the seventh audit

The sixth audit's own fixes produced most of this list. Four of the nine issues it found were introduced by the fix before it, which is the honest shape of a converging spec.

**The unbounded hold, and what it dragged in.**

- **The manage-chain hold is now bounded.** Holding exits on a `data_guard` block was right; leaving the hold unbounded was not. A position with a breached stop would have sat unexited for as long as the feed stayed bad, silently. Engine 17 `safety` now counts consecutive `data_guard` blocks and emits `close_all` past `safety.max_consecutive_data_blocks`, default **15** — one full decision bar at a one-minute tick, long enough to ride out a websocket reconnect, short enough that nothing is carried through a second bar on data nobody trusts.
- **The counter lives in the store, not in `state`.** `state` is fresh every tick and `safety` cannot write `state["system"]`, so there was nowhere in memory to keep it. Engine 19 `memory` writes a block record on every blocked tick — candidate or not — and `safety` counts the trailing run. It therefore survives a restart: a daemon that dies mid-outage does not reset the clock on an outage that is still running.
- **The off-by-one is specified, not left to the implementer.** `data_guard` runs before `safety` in the guard chain; `memory` runs after both, in the manage chain. So the count is stored blocks through tick T−1 plus one if the current tick is also blocked. Left implicit, this fires the breaker a minute early or a minute late.
- **Emergency liquidation now overrides a failed fetch, not just a `data_guard` block.** This was the sharpest gap: a feed outage triggers the escalation, and the same outage is failing the balance and book fetches, so under invariant 2 the `close_all` would have been blocked by the exact condition that raised it. Engines 21 and 22 may now use last known good balances and `AssetPairs` metadata past its TTL — the only place in the system where a stale cache is acceptable. Rounding still goes down, `userref` idempotency still applies, and every tolerated failure is recorded on the resulting trade.
- Phase 3 proves the breaker fires after the threshold and not one tick before, counting across a simulated restart. Phase 6 proves the escalation completes while `data_guard` is still blocking and the balance fetch is still failing.

**The override belongs in the authority file.**

- **Invariant 14 now exists.** The one deliberate override in the system was documented only in `engine-contracts.md`, while `trading-invariants.md` said gates are never bypassed and paper fallbacks were "the only exception", and `project-overview.md` said "Nothing overrides a gate". An agent reading in the prescribed order would have hit the override in a subordinate file and correctly concluded it was a bug. It is now rule 14, rules 2, 3 and 4 point at it, `project-overview.md` is corrected, and `engine-contracts.md` points at the invariant instead of restating the reasoning.
- It was appended as 14 rather than inserted after 4 on purpose: other files reference invariants by number, and renumbering would have broken every one of those references silently.

**The check's blind spot.**

- **`docs_vocabulary` no longer excludes the whole tracker**, only its `## Decision history` section. Current-state sections — Current Goal, Locked Decisions, Architecture Decisions, Known Risks — are now scanned like any other file. The blanket exclusion is how a stale claim about the memory engine survived three audits inside a section labelled Architecture Decisions.
- **What the check cannot catch is now written down.** A new rule that was never propagated has no retired token to grep for; the check reported PASS across thirteen files while three contradictory statements about gate overrides stood. `ai-workflow-rules.md` now states plainly that a PASS is not a consistency guarantee, and gives the lead a three-step manual procedure: write the rule in the authority file first, grep for the absolute claim it contradicts rather than for the new rule, and make every other mention point rather than restate.

**Smaller.**

- The cross-chain keys table is referred to by field name, not by position. Appending `hold_reason` had silently redirected "the last two" onto a field that means the opposite.
- `hold_reason` (B → C) and the per-tick block record (C writes, B reads) are now seams in `ownership.md`.
- `state["system"]` is written by **the orchestrator** in two named places — the command reader at step 0, and step 4 clearing `close_intent` — not by "the command reader" alone.
- Pseudocode step 4 uses explicit `state[...]` paths like the steps above it.
- Phase 8's soak criterion is a positive assertion: one unbroken `run_id` with a contiguous `cycle_id` sequence across the period. Counting exceptions could not distinguish a clean run from a daemon that died on day 2 and sat idle for five.
- The console shows `Idle — restarted, not trading` when the `run_id` changed and the mode is `idle`, so a silent overnight restart is visible. Text only; amber stays reserved for live mode.

### After the eighth audit

Six of the eight findings came from the seventh audit's own fixes. The pattern in them is worth naming, because it is not the pattern the earlier audits found: the *rule* was propagated correctly every time, and the *assumptions the rule rested on* were not. Contradiction-hunting does not find that. Dependency-hunting does, and the manual procedure now has a step for it.

**The forward dependency, and the chain behind it.**

- **Phase 3 depended on a Phase 4 deliverable.** Its escalation criterion counted block records written by engine 19, whose real implementation lands in Phase 4. Phases are gates; a gate that needs a later phase can never go green. Phase 3 now counts against **seeded** `block_records` from Phase 0 — offline and committed, which the criteria already demanded.
- **Seeded block records are now a Phase 0 deliverable for B**, in the ownership split and the Phase 0 exit criteria, including a consecutive `data_guard` run longer than the threshold so Phase 3 has something to count. Previously a later phase assumed them and no phase produced them.
- **`block_records` is its own table, not a column on `rejections`.** A rejection is one candidate refused; a block record is one blocked tick, and most blocked ticks never had a candidate because `data_guard` blocks before the opportunity chain runs. Folding them together would write candidate-less rejection rows and inflate the counterfactual dataset that is the point of the project. They join on `cycle_id`. Columns are fixed in `architecture-context.md`.
- **The counter orders by `ts`, never by `cycle_id`.** `cycle_id` restarts with the process, and surviving a restart is exactly why the counter lives in the store. Ordering by it would silently interleave two runs.
- **Phase 4 now proves the write the breaker depends on**: engine 19 writes a row on every blocked tick *including one with no candidate*, and `safety` counting live rows reaches the same total it reached against the seed. That requirement lived in `engine-contracts.md` and was verified nowhere — an implementer reading invariant 12 literally would have skipped candidate-less ticks and left the breaker silently inert with every test green.

**The escalation's preconditions.**

- **The trigger is now in invariant 14.** "The system liquidates your positions after fifteen minutes of bad data" is a money rule; it was stated in four files, none of them the invariants. Rule 14 now has a *When it fires* section holding the conditions, the threshold and its default, and the other files point at it.
- **A stale cache is two rules sharing a word, now separated.** For trading it does not exist. For an emergency liquidation it is the last thing the system knows, so `clients/kraken/` retains the last successful value of every fetch and never discards it on failure. Read literally, the old wording said discard, which would have made rule 14 unimplementable at the exact moment it is needed. It is a requirement on A consumed by B, and it now has a seam row.
- **Engine 21 still cancels a stale entry order during a hold.** The hold suppresses exits only. Cancelling is a decision about elapsed time, not price — no market data, and it reduces exposure. Read as "the manage chain does nothing", the hold would have left a live post-only buy on the book through an outage, which is the hazard invariant 8 exists to prevent.
- **`safety` escalates on open positions *or resting entry orders*.** The old condition was positions only, so an outage with no position but a live entry order escalated nothing and left that order to fill into a market the system had already declared untrustworthy.

**Smaller.**

- The console compares `run_id` against the previous row of the `runs` table, server-side in SQLite. "Since the console last saw one" was not implementable: the console is a separate process with no memory across its own restarts, and Phase 1 has to verify it.
- Invariant 14 no longer ends with a footnote about how other files are worded. That is the same coupling as the "last two" bug — a rule that describes its neighbours goes stale when a neighbour is reworded. It states the rule and stops.

**Correction, recorded by the ninth audit.** The step-4 dependency table reported with this audit listed `hold_reason` as producer B / Phase 6, consumer Phase 6. The seam row written in the same commit says the consumer is C — engine 19 `memory`, built in Phase 4, and the console, built in Phase 1. A consumer therefore *does* precede its producer, and the conclusion "no consumer precedes its producer's phase" was not supported by the check that was supposed to establish it. The dependency is harmless in practice, because a missing key reads as null exactly like the close-all flags — but the table was filled in from memory rather than read off the seam rows, and then presented as verification. Step 4 is now run against the parsed seam table, not by recall.

### After the ninth audit

All five findings were from the eighth audit's own fixes. The theme is narrower than last time and worse: a new clause was written into a rule without asking what the rule would need in order to run.

**The circuit breaker had no defined inputs.**

- Engine 17 asks about equity drawdown, consecutive losses, error rate, open positions and resting entry orders. Only the block count had a named source. It cannot read `state` — it runs in the guard chain, before the manage chain, and `state` is fresh every tick — so every input must come from the store, and none of them were specified. B would have invented five schemas.
- `architecture-context.md` now names the table and fields for each of the six inputs, and adds the three tables that were assumed everywhere and listed nowhere: `positions`, `orders` and `equity_snapshots`. The equity series was already required by the locked decision that alpha attribution uses the full curve including cash periods; nothing had ever given it a home.
- **Engine 19 `memory` is the single writer of every relational row** — trades, positions, orders, equity snapshots, block records, rejections. That was implicit and is now stated, because it is what makes the manage chain's always-runs guarantee sufficient for invariant 12, and it is why `memory` sits underneath `safety`'s entire input surface.
- Money columns are exact decimal strings in TEXT, never `REAL`. A drifting float equity series moves a drawdown threshold that liquidates the account.
- **All six producers are Phase 4 and `safety` is Phase 3.** The eighth audit fixed that forward dependency for one input and left it standing for five. Every one now takes the same seeded-fixture treatment.

**The seeded fixtures are named rather than assumed.**

- Phase 3's escalation criterion only passed because B's seed happens to contain an open position — invariant 14 gates emission on positions open or orders resting. Nothing said so. The Phase 0 split and the Phase 0 exit criteria now name all six fixtures explicitly: the consecutive block run, an open position, a resting entry order, an equity series with a drawdown past the limit, and a losing-trade streak past the limit.

**Two rules that promised more than they delivered.**

- **Retention is scoped to what rule 14 authorises.** Invariant 2 had required retaining the last successful value of *every* row in its table, including Spread — an input rule 2's own paper-mode table says must never have a fallback because an assumed spread invalidates the cost gate. Retention is now balances and `AssetPairs` only, and the file says plainly that spread and fee tier are not retained and why: a liquidation sells as a taker at whatever the book is, having already decided that getting flat beats getting a good price.
- **The guard chain records every blocker.** It never breaks early, so `data_guard` and `safety` can block on the same tick — and only the first was written, so a breaker firing during an outage left no row in `block_records` at all. The orchestrator now collects `state["guard_blockers"]`, engine 19 writes one row per blocker with `is_primary` on the first, and invariant 12 says so. The command row records the decision; the block row records the evaluation, and research needs both.
- The outage count is consecutive `cycle_id`s carrying a `data_guard` row, not consecutive rows. A tick where two guards blocked contributes one.

## Architecture Decisions

- Engines communicate only through `state`. No engine imports another.
- `context.now` is injected everywhere, so replay is faithful and look-ahead is structurally impossible.
- Engine 19 `memory` runs in the manage chain, every tick, so a rejection is recorded even on a tick where the opportunity chain never ran. `safety`'s outage counter is built from those records, which is why the per-tick block write is not optional.
- Live loop code and `research/` never import from each other. `scripts/verify.py` is outside both and may import either.
- Phase exit criteria are executable in `scripts/verify.py`, not a checklist anyone reads.

## Known Risks

- **Historical archives carry no order book or spread.** Engine 9 and the spread half of Engine 10 cannot be backtested before live recording began. `scripts/record.py` ships in Phase 0 for exactly this reason and must not be switched off.
- **A read-and-trade Kraken key exists on the dev machine.** Use a separate read-only key until Phase 8. The three live switches are the only thing between a bug and real money.
- **Every Kraken pair is a lot of pairs.** Develop against a config-limited subset; the universe filter handles the rest at runtime.
- **Building the interface before the backend risks guessing at data shapes.** Mitigated by fixing the schema in Phase 0 and seeding it. If a later phase needs a schema change, it goes through the lead and the console is updated in the same change.
- **An intermittent native memory fault in the seed write path.** Roughly 20% of full-suite runs die rather than reporting a verdict, always inside `seed.py` → `write_trade` / `write_position` → pydantic `model_dump`, with three different Windows fault statuses. **Not root-caused**; pyarrow, `pytest-asyncio`, test ordering, `root_import_path` and the pydantic-core version were each ruled out by test, and the one experiment that would have separated software from silicon was overridden by the power plan. Hardware is suspected and is out of scope. Mitigated by a crash-aware retry in `toolchain_green`: a crash is retried once and named in the PASS, a verdict is never retried, and a second crash FAILs. This is a closed question, not an open one — see `docs/build-log/phase-0.md`. It re-opens if the fault appears on other hardware, appears outside the seed write path, or starts failing the retry.

  **Re-opened 2026-09-09 with a captured trace. Two of this entry's three re-open conditions are met, and the recorded signature is wrong.**

  A `--phase 0` run mid-Phase-1 reported `6 PASS, 1 FAIL, 0 PENDING`; three immediate re-runs were clean. The lead re-ran before capturing the message, which was a mistake — but the underlying fault was then reproduced deliberately and captured in full. What it shows:

  - **It is not confined to `write_trade` / `write_position` → `model_dump`.** The captured trace is `seed_database` → `build` → `_write_equity` → `StoreClient.write_equity_snapshot` → `StoreClient._insert` at `client.py:194`, with `Windows fatal exception: access violation` as the innermost frame — inside `sqlite3`'s C extension, not pydantic's. `_insert` is plain parameter-bound SQL with no obvious hazard. **So this is not a pydantic bug**: the fault has now been seen inside two unrelated C extensions in the same process, which is what memory corruption looks like and is not what a library defect looks like.
  - **It does not need the full suite.** `pytest tests/clients/store/test_seed.py -q` alone crashed 1 in 8 runs. Test ordering and cross-test interaction are therefore not prerequisites, and the reproduction is far cheaper than the entry assumed.
  - **It may need pytest, but that is not proven.** `seed_database` called in a loop with no pytest in the process survived **1,120 consecutive seeds with zero faults**. `test_seed.py` collects 77 tests against a function-scoped `seeded` fixture, so those 8 runs performed roughly 480 seeds for 1 fault — about 0.2% per seed. At that rate 1,120 clean seeds is worth roughly two expected faults, so the difference is **suggestive at around p ≈ 0.1 and not conclusive**. It is the cheapest open lead: if pytest's process really is required, the candidates are things `tests/conftest.py` installs — the autouse network guard's socket patching, `hypothesis`, `pytest-asyncio` — rather than the store code, and none of those can reach production.

  **A third site, 2026-09-09, and this one is not a native crash at all.** C's first full-suite run of its final session reported `1 failed, 640 passed` — `tests/platform/test_config.py::test_a_missing_required_key_is_refused` raising `TypeError: object of type 'ScalarEvent' has no len()` from inside pyyaml's own `parser.py:118`. That file alone then passed 82/82, and two later full-suite runs passed 641 and 707. No randomised ordering plugin is installed, so the same code ran in the same order and disagreed once. C captured the trace before re-running, as instructed; it is in `docs/build-log/phase-1/c-interface.md`. **pyyaml is pure Python**, so a parser state object being handed to `len()` is not a fault in a C extension at all — it is a wrong value appearing in ordinary interpreter state. Together with the pydantic and sqlite3 sites, that is three unrelated libraries, one of them not compiled, which is consistent with process-level memory corruption and inconsistent with a defect in any of the three.

  **Consequences.** The `toolchain_green` retry is not sufficient on its own: at roughly a 20% per-run crash rate, two consecutive crashes is about 4%, which is how often a spurious FAIL should be expected. That matches what was seen. It does not block Phase 1 — the mid-phase bar is no FAIL, and `--phase 1` has been clean throughout — but it does mean a FAIL must be **captured in full before re-running**, and a spurious FAIL must never be assumed without the trace to prove it. Whether to widen the retry, quarantine the seed fixture, or chase the pytest lead is a decision for the operator at a phase boundary, not something to settle mid-phase.

## Session Notes

- Project starts from scratch. Any earlier ACSOE code was throwaway scaffolding and must not be carried over or referenced.
