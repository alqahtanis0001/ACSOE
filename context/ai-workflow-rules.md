# Development Workflow

## Approach

Spec-driven and phase-gated. `feature-specs/` defines what to build, context files define how, `progress-tracker.md` defines where we are. Implement against the specs — never infer trading behaviour from scratch.

**`feature-specs/` starts empty, deliberately.** The first action of every phase — including Phase 0 — is the lead writing that phase's specs from its row below and getting operator approval. The first response to "start phase 0" is therefore a list of specs, not code. That is correct, not a stall.

## Build order

**Structure, then interface, then backend.**

The interface is built early, against the real database schema populated with seeded fake rows. When the backend later fills that same schema with real data, the console works without changes. This is why Phase 0 creates the schema and the seed generator before anything else.

## How scripts/verify.py works

Each criterion prints one of three results:

- **PASS** — checked and satisfied
- **FAIL** — checked and not satisfied
- **PENDING** — the thing it checks does not exist yet

A phase is green only when every criterion is PASS and none are PENDING. PENDING is what lets Agent C write the criteria before A and B have built the things they judge, which is why `verify.py` is sequenced first in Phase 0.

Every criterion must run offline with no network and no API key, and **must pass on a fresh clone**. `data/`, `models/` and `logs/` are gitignored, so a criterion may never depend on anything inside them.

Where a criterion concerns live or long-running behaviour, it checks a small **committed** artefact under `tests/fixtures/` — a redacted JSONL sample, a gap report, a run-log digest — produced by the real run and checked in. The real run is verified by `--live`, which is opt-in and never required for a phase to be green.

A criterion that only passes on the machine that produced it is a broken criterion.

### Fabricate the subject a criterion judges. Never fabricate a contract it is held to.

A criterion is written before the thing it judges, so both halves of its proof — PENDING on an absent subject, PASS on a fabricated one — run against something the criterion's author built. That is the point, and it has one failure mode that is invisible from either half.

**If the fabricated tree also fabricates a contract the criterion depends on, the fabrication can agree with a mistake and both halves still pass.** C's `check_data_guard_blocks_bad_data` did exactly this: its helper built an `EngineContext` with a `cycle_id=` field that does not exist and no `mode=`, which raises `TypeError` — and the criterion reported PENDING and PASS regardless, because the test tree had fabricated its own `acsoe.core.contracts` whose `EngineContext` accepted the wrong call. **The criterion's body had never once executed.** It would have failed the instant A's real engine landed, which is the worst possible moment to discover it.

The rule that follows:

- **Fabricate the subject.** A minimal console, a stub engine, a two-row archive — whatever the criterion is judging. That is what lets a criterion exist before the code.
- **Never fabricate the contract.** `core/contracts.py`, `clients/store/contracts.py`, a config model, an engine's `contracts.py` — import the real one. A criterion held to a fabricated contract tests the fabrication.
- **If a criterion cannot reach its own body without a fabricated contract, that is the finding**, not an inconvenience to route around.

The same reasoning is why `commands_round_trip` refuses every double and why B proved `core/`'s store calls in a fresh interpreter through a subprocess rather than `exec`: a seam exercised only through something the author also wrote is not tested — the something is.

Phase 0 has no preflight — there is no phase −1.

## Retired vocabulary

Every audit of these documents has found the same class of defect: a decision that reached three files and not the fourth, leaving an agent to follow the stale copy in good faith. It is not caught by reading, because each file is self-consistent. It is caught by grep.

`scripts/verify.py` therefore carries a `docs_vocabulary` criterion in **every** phase. It scans `AGENTS.md`, `README.md` and `context/*.md`, and FAILs if any of these appear outside `~~strikethrough~~` and outside the two excluded regions below.

**Two regions are excluded, for one reason: a section whose job is to catalogue superseded things necessarily names them.** The exclusion is always the smallest section that does that job, ending at the next `## ` heading — never a whole file.

The first is this `## Retired vocabulary` section. It defines the terms, so it names them in the table and in any prose explaining the table, including a quotation of the historical defect a row exists to catch. A quotation of a defect is the one thing that will always look exactly like the defect. **This exclusion holds only while this section stays short and wholly about the check** — if current-state material ever accumulates here, re-narrow it, because a blanket exclusion over mixed content is precisely how a stale claim survived three audits inside the tracker.

The second is the `## Decision history` section of `context/progress-tracker.md` — the record of superseded decisions, which is *meant* to name retired terms. Everything else in the tracker (Current Goal, Locked Decisions, Architecture Decisions, Known Risks) is current-state text and is scanned like any other file. Excluding the whole tracker is how a stale claim about the memory engine survived three audits inside a section labelled Architecture Decisions.

| Retired term | Only a hit when the same line also contains | Superseded by |
|---|---|---|
| `two-chain` | — | three runtime chains: guard, opportunity, manage |
| `chain 1`, `chain 2`, `always chain` | — | the chains have names; use them |
| `INGEST_CHAIN` | — | `GUARD_CHAIN` |
| `state["system_mode"]` | — | `state["system"]["mode"]` |
| `paper.starting_balance` (singular) | — | `paper.starting_balances`, a per-currency map |
| `24 bars` | — | 48 bars |
| `eight` | `machine learning`, `non-ML`, or `engines` | nine — `scout` is deterministic |
| `tier 1` | `assume` | a pair with no fee data blocks; there is no fee fallback |
| `90 days either side` | — | the walk-forward trains on the 90 days **before** its test window and nothing after it, operator ruling 1 of 2026-09-12 |
| `accuracy` | `metric` or `score` | the Brier of P(target) against the fold's base-rate Brier, operator ruling 2026-09-12: at a 23.89% target rate a model that always predicts `stop` scores 51%, so a document reporting accuracy is reporting the model that never trades |

The middle column exists because some retired terms are ordinary English words. `eight` is only
wrong when it counts engines; it is perfectly good in any other sentence, and a bare-token match
would make the word unusable across every document. A qualifier is **data in this table, not a
special case in the checker** — any future row may carry one or leave it blank.

The qualifier is a same-line co-occurrence and nothing cleverer. That is deliberate: it catches
the actual historical defect ("Twenty-three engines run in a fixed order… Eight contain no
machine learning at all" — both cues on the line), and it needs no semantics the checker has to
infer. It will miss a sentence that straddles two lines. That residual gap is the manual
procedure's job, not the checker's, and the sixth audit already recorded why: a bare count is
not a distinctive token, and a check that only catches renamed identifiers misses corrected
facts.

When the lead retires a term, adding it to this table is part of the same change. A rename that does not update this table is an incomplete rename.

### What this check does not catch

`docs_vocabulary` finds **stale tokens**. It cannot find a **new rule that was never propagated**, because a rule that has just been written has no retired string to grep for. The fifth audit introduced the `close_intent` gate override into `engine-contracts.md` and left `trading-invariants.md` saying gates are never bypassed and `project-overview.md` saying "Nothing overrides a gate" — and the check reported PASS across all thirteen files while all three statements stood.

**A PASS is not a consistency guarantee. It means no known retired term is present, and nothing more.**

So when a change introduces or alters a rule, the lead still does this by hand, before the phase closes:

1. Name the file that has authority over the rule — `trading-invariants.md` for anything touching money, gates or modes; `engine-contracts.md` for the engine interface and the chains; `architecture-context.md` for layout, storage and the command table. Write the rule *there* first.
2. Grep for the claim the new rule contradicts, not for the new rule. A new exception means some file somewhere currently says "always" or "never" or "the only". Those words are the search. **Grep `AGENTS.md` and `README.md`, not just `context/`.** Twice now a rule has landed in the context files and missed the entry point — the file every agent reads first, before any of the documents the rule was written into.
3. Have every other mention point at the authority file rather than restate it. Restatements are what drift.
4. **If the rule depends on something another agent produces — a table, a seeded fixture, a state key, a retained cache — name the producer, check that the phase it is built in is not *later* than the phase that consumes it, and add a seam row to `ownership.md`.** Steps 1 to 3 catch contradictions; this one catches dependencies, and dependencies are what the eighth audit was almost entirely about. A rule whose producer arrives a phase late is a gate that can never go green. A rule whose producer is never named is a thing two agents will build twice, differently.

## The feature-spec format

Every spec in `feature-specs/` uses exactly this shape. The lead does not invent a variant.

```markdown
# NN — <title>

**Owner:** <agent>

## Goal
One or two sentences. What exists at the end that did not exist before.

## Implementation
Numbered steps naming real file paths. No code.

## Scope Limits
What this spec must NOT do. Never empty. This is the section that
stops an agent widening the work, so it is the most important one.

## Check When Done
Concrete checks, ending with:
pytest tests/ -q · mypy --strict src/ · ruff check src/ · python scripts/verify.py --phase N
```

## Phases are gates

Nine phases, in order. **A phase is done when `python scripts/verify.py --phase N` passes every criterion**, not when it looks finished. Never start later-phase work, even when blocked.

| Phase | Scope | Verified by |
|---|---|---|
| **0 — Structure** | `scripts/verify.py` first. Then package skeleton, `core/` contracts and three-chain orchestrator, `platform/` config, logging and injected clock, all three CLI entrypoints (`acsoe research` as a stub that reports no offline engines registered until Phase 4), `config/default.yaml`, SQLite schema and migrations, store client, seed data generator, fake Kraken client, test harness, `scripts/record.py` | Orchestrator runs an empty registry cleanly; a fresh database migrates from empty; seed generator produces a queryable database carrying every fixture Phase 3 tests `safety` against — trades, rejections, `block_records` with a consecutive `data_guard` run longer than `safety.max_consecutive_data_blocks`, **at least one open position**, **at least one resting entry order**, an `equity_snapshots` series with a drawdown past the limit, and a losing-trade streak past the limit; `tests/fixtures/record_sample.jsonl` parses and validates against the recorder schema; the `docs_vocabulary` check finds no retired term outside the tracker; `pytest`, `mypy --strict`, `ruff` all green |
| **1 — Interface** | The full console against seeded data: status band, positions, cycle feed, history, research views, WebSocket updates, three commands | Console starts and renders every screen from the seeded database; WebSocket pushes an update within twice `console.poll_interval_ms` of a database change; Activate, Freeze and Close-all each write a correct command row; live-mode frame renders amber and paper does not; no raw hex outside the token block; tabular figures on every numeric column; keyboard focus visible; `prefers-reduced-motion` respected; the status band reads `Idle — restarted, not trading` when the daemon's `run_id` has changed and the mode is `idle` |
| **2 — Data spine** | Engines 1, 2, 3, 4; historical OHLCVT loader; recorder engine supersedes `scripts/record.py` | `tests/fixtures/recording_report.json` shows a continuous span of at least 24 hours with every break accounted for, and `--live` confirms the real recording in `data/raw/` matches it; for three pairs, built 15m candles match an independent reduction of real recorded Kraken trades (`scripts/ohlc_fixture.py`, sharing no code with the builder), every OHLC field within one `tick_size` of the fake exchange's pair rules with the largest difference measured stated in the verdict, and volume within 0.1%; confirming the candles against Kraken's published OHLC with a real `tick_size` is a `--live` task (amended 2026-09-18, see below the table); data guard blocks on injected stale, negative-spread and missing-candle data; historical loader ingests one pair's full archive and reports gap statistics; console shows live data replacing seeds |
| **3 — Economics** | Engines 7, 10, 11, 17. Zero ML | Cost engine computes net edge from the fee tier returned by the fake Kraken client rather than a constant, and blocks below hurdle; risk engine rejects a sub-`ordermin` position rather than rounding up; universe filter yields different pair counts at $10 and $5,000 balances; safety engine freezes on injected drawdown **on a tick where the opportunity chain never runs**, proving the breaker is not gated behind the other gates, and re-emits no command while the condition persists; `safety` emits `close_all` on the tick after `safety.max_consecutive_data_blocks` consecutive `data_guard` blocks and **not one tick before**, counted from the seeded `block_records` of Phase 0 — not from a live engine 19, whose real implementation is Phase 4 and which Phase 3 may not depend on — ordered by `ts` so a seeded run spanning two `run_id`s still counts as consecutive, and emitted only because the seed also carries an open position and a resting entry order, which invariant 14 requires; **every one of `safety`'s six inputs is read from the Phase 0 seed and none from a live engine**; each has a block test and a pass test |
| **4 — Memory and replay** | Engine 19 real implementation; Engine 23 replay and triple-barrier labelling | `tests/fixtures/labelled_sample.parquet` holds a labelled slice replayed from the historical CSVs, and `--live` replays the full six months; a committed fixture of 20 hand-verified labels is asserted against by the labeller; purged walk-forward splitter produces folds with no label-window overlap across boundaries, and every training row pre-dates its fold's test window (past-only, operator ruling 2026-09-12); rejections persist and survive a restart; engine 19 writes a `block_records` row for **every guard blocker on every blocked tick**, including a tick where `data_guard` blocked and no candidate ever existed and a tick where two guards blocked at once with `is_primary` set on the first only; engine 19 also writes `positions`, `orders`, `equity_snapshots` and `trades`, and `safety` reading those live rows reaches the same six totals it reached against the Phase 0 seed; console history reads real rows |
| **5 — Models** | Engines 5, 6, 8, 12, 13, 15, plus the DI inside `engines/prediction/`, engine 7's ranking score, and engine 20 `tournament` (operator ruling 2026-09-12: its leaderboard is what engine 14 reads in Phase 6, so it must exist before then) | Predictor trains and produces calibrated probabilities; DI fitted on the predictor's training set with a rolling percentile threshold, proven by row identity; skeptic trains only on predictor out-of-sample BUY rows; full walk-forward with weekly retraining completes and reports out-of-sample Brier against the base-rate Brier per fold with the effective sample size beside every row count; engine 20 writes a leaderboard row per model version and promotes nothing; `rank_universe` proven on input where arrival order and intended order disagree on every element |
| **6 — Decision and execution** | Engines 9, 14, 16, 18, 21, 22; fill simulator | One complete paper trade end to end through all four gates: post-only entry, simulated fill, minute-by-minute watch, exit on each of target, stop and timeout, all logged; an unfilled entry cancels and abandons without chasing; a position whose stop has triggered places **no** exit on a tick where `data_guard` blocked, and `position_manager` records `hold_reason`, while the same position with `close_intent` set does exit; an escalation raised by `safety` during a sustained `data_guard` block completes — entry orders cancelled and positions closed — **while `data_guard` is still blocking and the balance fetch is still failing**, per invariant 14; console shows the position live |
| **7 — Evaluation** | Attribution, deflated metric, promotion gate, all reading the leaderboard engine 20 has written since Phase 5 | Three-month paper backtest emits an alpha-versus-benchmark report from the full equity curve including cash periods; promotion gate rejects a model whose edge does not survive the trial haircut; research screens render the leaderboard and SHAP view |
| **8 — Live readiness** | `platform/live_guard.py` (A), `close_all` end-to-end (Lead's reader plus B's exit engine), soak test | All three live switches proven individually required; kill switch halts a running loop within one tick, cancels every resting entry order and closes every position, and closes nothing it should not; a daemon killed part-way through a `close_all` finishes the liquidation on restart rather than coming back with the command marked consumed and positions still open; `tests/fixtures/soak_digest.json` shows **one unbroken `run_id` with a contiguous `cycle_id` sequence** spanning at least 7 continuous days in paper, with zero unhandled exceptions — a positive assertion, because a digest that only counts exceptions cannot tell a clean run from a daemon that died on day 2 and sat idle for five; and `--live` checks the real log in `logs/`; no secret appears in any log, artefact, or committed file |


**The Phase 2 row was amended by the operator on 2026-09-18, and the earlier wording was never met.**
It asked for candles to *"match a committed Kraken OHLC fixture … within one `tick_size` for that
pair as reported by `AssetPairs`"*. Neither half was ever available. The recording carries no OHLC
channel and no live call could be made, so the fixture's bars are a local reduction of recorded
trades, not Kraken's published OHLC. And the `tick_size` came from `asset_pairs.json`, which is
invented Phase 0 test data. **A recorded this at the time** (spec 28, `docs/build-log/phase-2.md`,
"its expected bars are not Kraken's", 2026-09-09), and **nothing carried it up to this rule.** So
Phase 2 was green for six phases against a definition of done that described something that could
not exist. The criterion is now `candles_match_independent_reduction_of_recorded_trades`. On the
committed fixture its largest difference is 0 and its tolerance is never engaged. The account is
the tracker's FINDING *"a criterion described itself as checking against Kraken …"*.
**Phase 2's green stands** (operator, the same evening): it was awarded on the criterion
actually passing, and the criterion checked the local reduction, so the amendment makes the
record match what was proven. It is not a re-examination of Phase 2, and nothing about that
phase reopens.

## Scoping

One engine or one subsystem at a time. Small verifiable increments. If a change cannot be verified end to end quickly, split it.

Split a step if it combines:

- An engine and the client it depends on
- Live loop code and research code
- More than one owner's directories
- Anything not clearly specified in `feature-specs/`

## Escalate, do not edit

Stop and escalate if the work requires:

- Changing `src/acsoe/core/` or `bootstrap.py` and you are not the lead
- Adding, removing, or reordering an engine
- Changing `trading-invariants.md` or `engine-contracts.md`
- A dependency not listed in `architecture-context.md`
- Changing a schema another agent writes to

## Missing or ambiguous requirements

Never invent trading behaviour. Add an open question to `context/progress/<agent>.md` and stop that unit. Being blocked is better than guessing at financial logic.

## Definition of done for a task

1. Works end to end within its stated scope.
2. Tests exist, including a block test and a pass test for any gate.
3. `pytest`, `mypy --strict`, and `ruff check` are green.
4. `python scripts/verify.py --phase N` reports **no FAIL**. PENDING is expected mid-phase and only has to reach zero at phase close.
5. No invariant is violated.
6. The engine's `README.md` is written and accurate.
7. `context/progress/<agent>.md` reflects reality.
8. `docs/build-log/phase-N/<agent>.md` records every non-trivial problem and its fix.
9. Any context file the implementation contradicted has been corrected.

## Keeping docs in sync

Update the relevant context file in the same change whenever implementation alters architecture, storage, contracts, conventions, or scope. Progress files record actual state, never intended state.
