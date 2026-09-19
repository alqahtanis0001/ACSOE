# Progress Tracker

**Lead-only file.** Teammates write `context/progress/<agent>.md`. The lead merges here after a passing verify run.

## Current Phase

**Phase 7 — Evaluation. SPECS 126–144 WRITTEN AND EVERY RULING ANSWERED, 2026-09-19; AWAITING
OPERATOR APPROVAL TO BUILD. Nothing claimed or built.** The seven rulings still open after the second
round were answered by the operator on 2026-09-19 and applied to the specs and the findings the same
day: R2 capped skeptic; R4 six months (folds 379–404, ending at fold 404's test close, 2025-01-04);
R8 both benchmarks; R9 every configuration ever evaluated on the out-of-sample data, listed and
counted conservatively; R10b the working form; R11 the ranking skips pairs the anomaly and DI gates
would refuse; R12 invariant 4's wording in the operator's words. **Spec 75 is resolved** (Open
Questions). Phase 6 re-gated at the Phase 7 preflight, 2026-09-19
(`logs/verify/phase6-20260919-phase7-preflight-lead.log`). The task list is
`feature-specs/PHASE-7-TASKS.md`. The evidence is `docs/dataset/phase-7-findings.md`, which gathers
everything measured about the system's economic behaviour before the chain simulation, with the
simulation's slots marked. **The operator rules on the phase close after seeing the simulation's
output, as in Phase 6. The lead does not mark it green.**

**The account's own fee tier is a recorded fact; tiers 3 and 5 are declared scenarios.** On
2026-09-19 one read-only authenticated `TradeVolume` call (pair BTC/USD, HTTP 200, empty error
list) returned **tier 1: maker 0.40%, taker 0.80%**. That was measured on the account, not
assumed. The Phase 7 simulation's tiers 3 (0.22%/0.38%) and 5 (0.15%/0.30%) are **declared
scenarios** read from Kraken's published schedule
(`tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`), in replay mode only. They are not
the account's tier. At the account's own tier the cost gate cannot pass anything at the current
barriers (`phase-7-findings.md` §2, the tier-1 proof). The same call confirmed that the key rotated
in Phase 2 is alive and holds Kraken's Query Funds permission. Whether it also holds trade
permission cannot be read from the API; the operator checks it on Kraken's key page.

**Recordings made before the recorder gap fix lack the pair rules and the fee tier, 2026-09-19.**
Operator instruction, separate from Phase 7. The recorder reads Kraken's instrument snapshot to
choose its subscriptions and then discards it, and nothing records `TradeVolume`. **So every
recording up to the change that adds those frames has no recorded pair rules and no recorded fee
tier.** That covers the eleven days on disk and everything recorded until the fix lands. Engine 7
would exclude every pair as `pair_rules_missing` and engine 10 would block every pair, so **a replay
over those recordings needs declared substitutes, not recorded facts**. They would be a declared
`AssetPairs` and a declared fee scenario, labelled as declared wherever they appear, as in Phase 7's
replay of the 2023–24 archive. A's recorder audit (`docs/build-log/phase-7/a-platform.md`, the
recorder gap audit) lists what else the recording lacks. **THE CUT-OFF: 2026-09-19 05:08:44Z.** The
last line of the old recorder was written at 05:08:44.099Z. The new recorder's start marker is at
05:09:44.991Z, and its first `instrument` snapshot, 1,450 pairs, landed at 05:09:47.133Z. **The
recorder gap across the switchover is 62.79 s.** The hourly `fees.py` poll (AssetPairs and
TradeVolume) and the supervised `funding.py` began at 05:08:45Z. **Recordings before 05:08:44Z
have no recorded pair rules and no recorded fee tier; recordings after it have both** (the rules
from the connect onward, within about a second of each connect). Commits: P3 `b2119fd`, P1 and P2
`4b32655`. A's switchover entry is in `docs/build-log/phase-7/a-platform.md`.

*The second round of rulings, as recorded when the specs were first revised:* Ruled on 2026-09-19 and
carried by spec 126:

- invariant 2 permits a declared fee scenario in replay mode only, enforced by a test;
- a genuine `AssetPairs` is to be recorded (prerequisite 9);
- the DI and anomaly thresholds are rebuilt from the Phase 5 study, not refitted;
- spread and depth are declared by liquidity bucket, the form delegated to the lead;
- a replay-only client serves a synthetic book.

**Flagged:** the plan runs no full walk-forward, so prerequisites 2 to 4 are not scheduled. That
contradicts prerequisite list line "pays the same cost again unless all six are fixed first",
which assumed a rerun.

Three things carried into its first session by the operator at the Phase 6 close, 2026-09-18.
**Read these before planning anything.**

1. **Engine 14 `adaptive_router` has never weighted anything real.** On the first paper trade it
   returned `leaderboard_empty`: the drive's database held no leaderboard rows. It will not weight
   anything real until engine 20 writes persisted rows. **Phase 7's attribution must not read a
   router verdict as a judgement.**
2. **Engine 9's slippage on the first paper trade was 0 because the book was pinned to one level.**
   The real exercise of the walk is `order_book_slippage_on_recorded_book`, over the recorded book.
   **Phase 7 must not take that trade's zero as evidence about slippage.**
3. **F-new-1 is the most consequential open item: an approved trade leaves no record of why it was
   approved.** The counterfactual dataset records reasons for refusals and nothing for approvals:
   only `rejections` carries expected move, friction, net edge and hurdle. Phase 7's attribution
   will want to explain which trades the system took and why, and **it cannot** (Phase 7
   prerequisite 7).

**Phase 6 — Decision and execution. GREEN AND CLOSED 2026-09-18** by the operator, after reading
the first paper trade's walk-through (`docs/build-log/phase-6/first-paper-trade.md`); the
narrative is `docs/build-log/phase-6.md`. *As opened, 2026-09-16:* Engines 9 `order_book`, 14
`adaptive_router`, 16 `decision`, 18 `execution`, 21 `position_manager`, 22 `exit` and the fill
simulator — the Phase 6 row as written, not cut. Preflight: `verify.py --phase 5` re-run on a
quiet tree at `e75bc26`, **14 criteria, 14 PASS, 0 FAIL, 0 PENDING, exit 0**
(`logs/verify/phase5-20260916-phase6-preflight-lead.log`). Twenty specs, 80 to 102, approved by
the operator with **five rulings** (below) and four smaller lead decisions. The shared task list is
`feature-specs/PHASE-6-TASKS.md`. Two Phase 7 prerequisites are pulled forward — the DI's fitting
and scoring path (5), and the DI half of a real peak-memory test (4) — and engine 8's `is_buy` is
fixed here as the operator carried it out of Phase 5.

**The two numbers Phase 6 must not read as defects, stated plainly here because the criteria will
produce both.**

1. **Tier 1 is a no-trade regime at the current barriers, and that is the project's central
   economic finding rather than a defect.** `trading.hurdle_multiple: 1.5` means a candidate needs
   an expected move above **3.125%** at tier-1 friction, and the target barrier is **3.0%**, so
   nothing can ever clear the cost gate there. Separately, with an empty `.env` the private calls
   fail, `TradeVolume` returns nothing, and every pair blocks at the cost gate, so a fresh clone
   can never produce a trade against the real client. **Every Phase 6 criterion that needs a trade
   therefore runs against the fake client at tier 3** (friction ≈ 0.65%, bar 1.625%) **and says so
   in its own message** — a criterion passing only at a fee tier the account does not have says
   less than it appears to, and the message is where that gets recorded. `hurdle_multiple` is
   unchanged and the cost gate is not weakened. **The Phase 6 criteria therefore prove the
   machinery, not the economics.**
2. **Engine 14 `adaptive_router` weights a single real model, so the router is inert in
   practice** — the walk-forward trained one predictor per fold, not competing models. The same
   shape as `max_concurrent_positions: 3` being inert at this balance. A criterion asserting that
   the weights move is asserting a property of the committed leaderboard fixture, and it says so.
   The structural half is worse than the arithmetic: engines 14 and 16 both sit *after* the cost
   gate, so nothing either publishes may make the system more willing to trade (invariant 4), and
   making it less willing is a veto only a gate may issue.

**Corrected by operator ruling S3, 2026-09-18.** Item 1's "friction ≈ 0.65%, bar 1.625%" and
"tier 1 is a no-trade regime" are invariant 5's **reference** figures for Kraken's own
schedule, and item 1 is true of that schedule. **They are not the criteria's fees.** The
fake exchange's tier 3 charges 0.11% / 0.19%: engine 10 computed friction 0.308% and a
hurdle of 0.462% (a bar of 0.770% on the expected move). The fake's tier 1 charges 0.25% /
0.45% and **clears** (measured: friction 0.708%, hurdle 1.062%, entry placed). Every trade
criterion's message now states the figures its own run computed, and names Kraken's
reference tier 1 as a separate sentence.

### The operator's rulings on Q1–Q4, 2026-09-18, and what acting on them found

The four questions of `docs/build-log/phase-6/overnight-decisions-2026-09-18.md`, ruled by the
operator before sleeping on 2026-09-18. **Two of the four could not be carried out as ruled, and
the lead stopped on both** rather than choose; everything is in
`docs/build-log/phase-6/overnight-decisions-2026-09-18-night.md`, the night's one decision list.

- **Q1 — the retained balance in invariant 14. Ruled: do not amend invariant 14; change engine 22
  to read the retained balance, stopping first if that changes behaviour. Invariant 14 is not
  amended. The engine change STOPPED (S1): it changes behaviour.** **Ruled that evening: (a), below.** The only decision a balance could
  inform in engine 22 is the sell quantity, and the paper ledger is quote-side only
  (`clients/paper/fills.py:196`), so a cap sells nothing and a paper liquidation never completes.
  Worse, `PaperBroker.last_known_good_balances` forwards the **real** exchange client's retained
  `Balance` (`clients/paper/broker.py:262`), which in paper mode is not the paper account at all.
  Options and a recommendation are in S1.
- **Q2 — spec 118's premise. Ruled: a provenance block on `asset_pairs.json` naming the archive and
  date it was cut from; re-record both fixtures together at the next cut. STOPPED (S2): there is no
  archive.** **Ruled that evening, below: honest provenance, prose corrected, a FINDING.** `tests/fixtures/kraken/asset_pairs.json` has one commit (`afaf2f5`, 2026-09-08, the
  Phase 0 harness), and `tests/harness/fake_kraken.py`'s docstring calls every file in that
  directory **"invented test data for a fake exchange"**, promised to be replaced by recordings in
  Phase 2, which never happened. So spec 118's criterion, named for a *recorded* declaration,
  compares a real recording against an invented one, and the Phase 2 candle criterion's
  `tick_size` tolerance reads the same invented file. No provenance block was written: one naming an
  archive would be fabricated. Options in S2. *Spec 118's criterion was later removed (below).*
- **Q3 — WITHDRAWN 2026-09-18 evening, with spec 118's criterion**, which the operator removed
  (FINDING under Findings — Phase 6). As first recorded: **Q3 — spec 118's coverage. Ruled:
  accepted, not tonight. RECORDED.**
  `recorded_book_agrees_with_recorded_pair_decimals` **compares 1 pair of the 5 its two fixtures
  carry** (BTC/USD, 783 prices). The other four are named in its own message with the reason each is
  not compared. **Its PASS must not be read as broader than one pair.** Widening it to 3 of 5
  (ETH/USD and SOL/USD, both already in the 2026-09-16 archive) is **scheduled and not started**. It
  is a re-cut C runs, and it moves `order_book_slippage_on_recorded_book` with it, since the two
  share `tests/fixtures/book_sample.jsonl`. **After S2 the widening is not sufficient on its own**:
  it widens a comparison whose declaration side is still invented, so it should land with S2's
  answer.
- **Q4 — how the operator sees the first paper trade. Ruled: a database walk-through. DONE:**
  `docs/build-log/phase-6/first-paper-trade.md`. It is the criterion's own target round trip with
  its database kept, and every number is read from the rows or marked where it is not. It found
  that **the database holds no record of why the trade was taken** (F-new-1), and that every
  criterion's tier sentence quotes friction the run did not compute (S3, below).

**S3 — the tier sentence, found building Q4. STOPPED, then RULED that evening (below): every
message now states its own run's figures.** Item 1 above, rule 8
of `feature-specs/PHASE-6-TASKS.md`, and every trade-driving criterion's message say the criteria
run at "reference friction about 0.65% … a hurdle of 1.625%". **Those are the invariant's reference
values, quoted by a fixed string** (`tests/harness/fake_kraken.py:235-249`). The fake's tier 3
actually charges maker 0.0011 and taker 0.0019, and the round trip's friction was **0.308%** with a
hurdle of **0.462%**. And **the fake's tier 1 is not a no-trade regime**: 0.25% / 0.45% puts the bar
near 1.77%, under the 3% target. So "tier 1 is a no-trade regime" is true of Kraken's reference
schedule and is **neither measured nor tested by any criterion**. It changes no gate and no
reconciliation. It changes what the PASS lines claim.

### Open with the operator, 2026-09-18 evening

- **RULED 2026-09-18 evening: the Phase 2 row is amended** (see the FINDING). As first recorded:
  **the Phase 2 row in `ai-workflow-rules.md` still asks for what A's spec 28 decision could not
  provide**: *"built 15m candles match a committed Kraken OHLC fixture … every OHLC field within one
  `tick_size` for that pair as reported by `AssetPairs`"*. A chose the reference reduction because
  Kraken's OHLC was not available, and recorded why; the row never moved. It is the same shape as S1:
  a decision that stopped one file short. Changing a phase's exit criterion is the operator's
  decision, so it is reported, not edited.
- **Specs 121-125: stale prose sent back to its owners** (operator ruling of the same evening).
  - 121 (B): engine 22's contract comment still says its question was escalated.
  - 122 (B): `test_decision.py`'s tier comment. **Also found:** its `MAKER`/`TAKER` constants are
    invariant 5's *reference* tier-3 fees (0.0022 / 0.0038), not the fake's (0.0011 / 0.0019).
    The spec reports this and changes nothing.
  - 123 (B): `test_feature_chain_rehearsal.py`'s tier comment.
  - 124 (C): `test_order_book.py`'s tier docstring.
  - 125 (A): engine 1's README says engines 21 and 22 read the retained values. **Not on the
    operator's list**: the lead added it as the same class, because A had left it waiting on
    exactly the ruling S1 gave, and flagged it as an addition.
- **Spec 118's criterion: removed** by operator ruling. The FINDING is under Findings — Phase 6.
- **D17 → accepted, and the operator records that their own instruction was wrong on this
  point.** The instruction was to rewrite every Phase 6 "fourteen" to thirteen, naming HANDOFFs
  8 to 10. Those were real gate outputs from when they ran, so each keeps its number with a
  dated note, and four of the tracker's "fourteen"s were **Phase 5's** and would have been
  destroyed by the rewrite.

### The operator's rulings on S1–S3, 2026-09-18 evening

- **S1 → accepted.** Engine 22 as built. Invariant 14 now records that its balance authorisation
  is deliberately wider than the code, and why reading it would change behaviour (the paper ledger
  holds no base; the retained balance is the real account's in paper).
- **S2 → accepted, reshaped by the lead's follow-up answer.** The Phase 2 candle criterion's
  **verdict is sound** — its tolerance is never engaged, all 9 bars agree to the digit, and it
  would pass at any non-negative tolerance — and its assertion is unchanged. Its **prose** was
  false twice, and that is the FINDING recorded under Findings — Phase 6. `asset_pairs.json`
  carries an honest provenance block; the candle criterion says what it compared against (spec
  118 did too, and was then removed); a genuine `AssetPairs` recording is re-scoped to Phase 7
  item 9. Phase 2 had
  recorded a decision about the reference (`docs/build-log/phase-2.md:887`, A, spec 28): it
  limited the claim, and the correction **agrees** with it.
- **S3 → accepted.** Every trade criterion states the friction and hurdle engine 10 computed in
  its own run (`_run_regime` in `scripts/verify.py`, from what engines 1 and 10 published), and
  the Kraken tier-1 point survives only as a separate sentence about invariant 5's reference
  schedule. **Measured, not argued:** at the fake exchange's own tier 1, engine 10 computed
  friction 0.708% and hurdle 1.062% on the committed subject, cleared, and engine 18 placed the
  entry — so the fake's tier 1 is not a no-trade regime and no message may say it is.
- **F-new-1 → Phase 7 prerequisite 7. F-new-2 → Phase 7 prerequisite 8**, as a fact every join
  must carry. F-new-3 and F-new-4 recorded, not fixed.
- **D7 → right, for the right reason.**

### Where Phase 6 stands, 2026-09-16 06:30Z

**All six engines and the fill simulator are built.** 9 `order_book`, 14 `adaptive_router`,
16 `decision` (a gate, by operator ruling), 18 `execution`, 21 `position_manager`, 22 `exit`,
the paper broker in `clients/paper/`, and engine 19 rewritten to record what 18 and 22 publish.
**Nothing is registered yet** — spec 82 is held until the two rehearsals (A's spec 87 over
18/21/22, B's spec 94 over 9/14) are green, which is the same deferral Phases 2 to 5 took.

Nine Phase 6 criteria are registered and PENDING. Seven were waiting on engine 22, which now
exists; two need engines 9 and 14 driven against their fixtures.

**Outstanding at this point:** B's migration 0004 (`base_rate_brier`) and a non-truncating
leaderboard enumeration; C's remaining reason-code prose and the criteria bodies; then the
rehearsals, then registration, then the final gate. Engine 20's write of `base_rate_brier` and
engine 14's skill computation are one line each and wait on 0004.

**Two schema changes landed this phase**, both lead-approved on escalation: 0003
`positions.hold_reason`, because the console had no way to read why the manage chain held and
inferring it from `block_records` was rejected on the same grounds the system mode is never
inferred from the `commands` trail; and 0004 `leaderboard.base_rate_brier`, because engine 20
computes it per fold and discarded it for want of a column, and it cannot be recovered from
`win_rate` — `brier` is over every fold row, `win_rate` over the BUY subset only.

**Five spec lines of the lead's named a mechanism that could not do the job** — `drain_trades`
for the broker's fill rule, `query_orders` as engine 18's idempotency probe, `leaderboard_entries`
for an enumeration it cannot perform, spec 96's field list omitting `pair`, and
`last_known_good_asset_pairs` written as a method when it is a property. Every one was caught by
an agent building against the code rather than the spec, and the general rule is now in
`code-standards.md`: **a description of the code is not the code.**

### DEFECTS FOUND BY REHEARSAL, 2026-09-16 — neither is reachable without running the chain end to end

A's spec 87 rehearsal drove engines 18, 21 and 22 through real orchestrator ticks with **every**
upstream engine real (models trained in the test), at fee tier 3, against B's paper broker, with
engine 19 recording. Six scenarios green, four mutations killed by the tests written for them, one
equivalent control surviving the rehearsal and 855 tests in `tests/engines/` and
`tests/clients/paper/`. **And two defects that no unit test in any lane could have reached**,
because each lives between two engines that are individually correct. The operator ruled on both.

**Defect 1 — every paper trade would have frozen the account.** On the tick an entry fills,
`PaperBroker.balance()` counted only fills the store had recorded, so cash was still unspent,
while engine 21 — correctly for a live exchange — counted the new position in the portfolio value.
Engine 19 wrote equity `8332.41` against a true `4996.99`; `peak_equity` kept the inflated figure,
engine 17 read a 40.03% drawdown the next tick and froze, and every later tick stayed frozen.
**The cause is the operator's own paper-ledger ruling**, which said what the balance is adjusted
*by* and not *when*. **Ruled:** the broker's balance includes every fill it has executed, recorded
or not — the broker is the authority on its own cash. Invariant 2 amended and recorded as the
operator's. Fix is spec 103 (B). **And a criterion, not just a fix**: equity on the fill tick
equals equity on the tick before, within the fill's own cost, proven red by breaking the broker —
spec 105 (C). A's rehearsal pins the defect with a strict `xfail` that turns red when the fix lands.

**Defect 2 — a tick on which an opportunity-chain engine errored was not recorded at all.** Rule 7
empties the erroring engine's payload; engine 19 refused to write a rejection with no
`reason_code` and raised — so no rejection, no block record and no equity row. Invariant 12 says
every tick is recorded, and an erroring engine is the tick you most want. **Ruled:** engine 19
writes a `block_records` row for the errored engine with `status = 'ERROR'` and the code
`engine_errored` — never a `reason_code` the engine did not produce, because a reason code is a
decision and an error is its absence — and `REASON_PROSE` maps the code in the same change.
**The contract was wrong, not only the code**: it was satisfiable by code that broke invariant 12,
so rule 7 now says an `ERROR` owes no `reason_code` and engine 19 records the tick regardless.
The lead landed `state["block_status"]` in `core/` so engine 19 reads the status rather than
inferring it from an empty payload; the engine change is spec 104 (C). Consequence stated: engine
17's error rate now counts opportunity-chain errors too.

**Both defects are closed, 2026-09-16.** Defect 1: spec 103 (B, `178a0a8`) — the broker's
balance counts executed fills, restart proven; A's rehearsal test is a plain test again
(`ab2bf4f`) and goes red on the original `8332.414226591` when the fix is reverted. The criterion
`paper_equity_continuous_across_fill` (spec 105, C) PASSes with equity moving by exactly the
maker fee, and was observed to FAIL with the broker broken in place, reporting the same
`8332.414226591`. Defect 2: spec 104 (C, `3e1ded8`) — engine 19 writes the `engine_errored` block
record, proven through the real orchestrator with a real raising engine 18.

**Spec 94 (B, `49e369a`) found nothing** against engines 9, 14, 10 or 15. On the thin book —
the recorded BTC/USD snapshot, four levels walked — engine 9's estimate is nonzero and engine
10's friction equals the recomputation from the published parts, and differs without the
slippage term; the mutation "engine 10 drops the slippage term" is killed only there.

**Open, for the operator:** (1) B's spec 103 choice that a due fill with no fee tier makes
`balance()` a failed fetch (`KrakenUnavailableError`) rather than an `ERROR`, so engine 1 keeps
`pair_rules` and engine 10 blocks on the absent fee tier; (2) whether engine 11's paper-mode
fallback to `paper.starting_balances` should survive the ledger ruling — unreachable on the
outage path today because engine 10 blocks first. **Observations, not defects:** engine 21
stores a position opened on this tick with `last_price` NULL although its `_mark` docstring says
the mark is the fill price (B); spec 100's `test_pending_on_a_tree_with_nothing_built` must move
from `bare_tree` to `unbuilt_tree` when the criteria bodies are written, because the editable
install resolves the real package there (C).

### The operator's three rulings on the rehearsal round, 2026-09-16 evening

1. **Registration (spec 82): yes** — engines 9, 14, 16 and 18 into the opportunity chain, and the
   manage chain 21, 22, 19. **First**, C moves spec 100's `test_pending_on_a_tree_with_nothing_built`
   off `bare_tree`, where the editable install resolves the real package and a written criterion
   body would quietly PASS once registration lands.
2. **Fee-tier outage: confirmed.** B's spec 103 choice stands: a due paper fill whose fee tier did
   not return makes `balance()` a failed fetch (`KrakenUnavailableError`), not an `ERROR`. A fetch
   that did not return is the exchange being slow, not the code failing, and spending engine 17's
   error budget on it is the shape the engine 18 reason-code ruling already refused.
3. **Engine 11's balance fallback: REMOVED** (spec 106, B), and invariant 2's paper row now names
   the paper broker as the authority, with no fallback. **Not because it was unreachable — because
   reaching it would break invariant 6.** After one executed fill it fed the affordability check the
   raw `paper.starting_balances` and would approve a candidate against 5,000 the account no longer
   holds. Its docstring deferred the fill adjustment to Phase 6; Phase 6 put the ledger in the
   broker instead, and what remained was a second, wrong answer to the account question.

**FINDING — how it was found, which is the point.** It was found by asking **what the branch would
do if reached**, not **whether it could be reached**. The lead's first answer, "dead code behind
engine 7", was the wrong reassurance: it made engine 7's handling of an absent balance
load-bearing for invariant 6, an invariant engine 7 does not own, so an unrelated change to engine
7 would have armed the branch with nothing going red. Unreachability is a property of the callers;
correctness is a property of the branch. **Also folded into spec 106:** engine 21 stores a position
opened this tick with `last_price` NULL while its `_mark` docstring says the mark is the fill price
(C's observation from spec 105).

**Done, 2026-09-17.** C's test move `d28b756`; spec 106 (B) `268f49e` — engine 11 blocks on an
absent balance in every mode, `RiskSizing.fallbacks_used` removed (no producer, no reader; the
column exists on `trades` only), engine 21 stores the fill price as the fill-tick mark.
**Registration (spec 82) applied**: opportunity chain 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, 16,
18 and manage chain 21, 22, 19, in registry order with no holes; `is_gate_matches_registry`
23 engines, 8 gates, 0 mismatches. **Re-gated phases 0–6 on the registered tree**: every phase
fails only `toolchain_green`, on spec 100's known eight — phase 0 6/7, 1 9/10, 2 8/9, 3 8/9,
4 9/10, 5 13/14, 6 2 PASS / 1 FAIL / 9 PENDING. No fallout from registration.

**Follow-ups, routed as small specs (operator, 2026-09-17):**
- **Spec 107 (C):** engine 9's README and `_basis_notional` docstring still describe engine 11's
  removed fallback; spec 105's criterion still accepts a fill-tick position with no stored mark,
  which since spec 106 only a regression can produce (B's mutant P1 survives it today).
- **Spec 108 (B):** `engines/cost/contracts.py` and README call `fallbacks_used` a `rejections`
  column (it is on `trades` only); `clients/paper/broker.py` exports an unused
  `FALLBACK_PAPER_LEDGER` and calls the starting balance a substituted value; engine 10's source
  file is CRLF in the working tree.
- **Folded into the spec 100 criteria bodies (C):** `test_the_tier_sentence_is_pending_rather_than_wrong_when_the_harness_is_absent`
  takes `bare_tree` and never observes the PENDING its name promises; a four-quote docstring at
  `tests/verify/test_phase6_criteria.py:671` that `ruff format --check` flags.

### FINDING, 2026-09-17: the exit-cycle equity row described no real instant — found by the first criteria to run the registered chain

C's spec 100 criterion bodies are the first code to drive a whole paper trade through
`bootstrap.build_chains()`. Their round trips reconcile the trigger, the trade, the orders and the
position, and then **fail on the exit tick's equity row**: cash from engine 1 at the start of the
tick, positions value from engine 21 before the sale, open positions from the store after it. On the
stop leg the row read equity 4945.02 with 0 open positions and a positions value of 3281.10, against
a true 4938.79; on the target leg it sat above the true account and moved `peak_equity` to a figure
the account never held. Every unit test and both rehearsals were green, because each checked that
the row equalled the published totals — which it did. Not paper-only.

**Ruled by the operator, after one withdrawn design.** The first proposal had engine 22 publish
post-exit totals by subtracting engine 21's marks; the operator withdrew it because it couples engine
22 to engine 21's valuation method, which would change silently if that method did. The ruled design
(specs 113 B, 114 C): engine 22 publishes `net_proceeds` per closed trade; engine 21 publishes a
per-row `value`; on an exit tick engine 19 drops the closed positions from engine 21's rows, sums
the rest, and adds the net proceeds to engine 1's cash; totals on every other tick, with a sum test —
proven capable of failing — guarding the seam; a remaining unmarked position means no row, proven by
a test; `cash_source` recorded (migration 0005). And a criterion,
`equity_row_never_values_positions_it_does_not_hold`, observed FAIL on today's code before the fix.

**The criterion sweep found two assertions that could not fail and one real hole.** V8: engine 9's
walk was compared by level count alone, so a wrong walk with the right number of levels passed. V12:
the trained subject's cache key could be made constant with nothing noticing — the tests checked
what the criteria *said*, not what they *read*. V1: the check that every registered gate ran could
be disabled with nothing noticing, because the committed orchestrator never skips a gate and no test
built one that does. All three are now killed: V8 by arms that keep the level count and move the
price, V12 by a copied tree whose different training must be judged on its own subject, V1 by an arm
whose orchestrator skips the gates. **Also:** C's third heredoc slip in one session (an escape turned
into a real newline, a NUL byte, an unterminated heredoc) — the Phase 0 lesson recurring; C now writes
any escape-carrying script with the file tool. `research/labelling.py` is wholly CRLF in the working
tree (C's lane, not yet converted).

### SPEC 119 (B): the seed's vocabulary is real, and three findings the original one missed

B repointed seven seeded `rejections` rows across **six** bad pairs — the operator's engine 9 case
becomes engine 10 refusing on the absent estimate, and each other mapping is recorded in B's build
log with the option rejected. A new test walks every `(engine, code)` the seed writes against that
engine's own `contracts.py`; it was observed red on the pre-fix seed and is green after. **Three
findings, each correcting something this tracker previously stated:**

1. **The 2026-09-16 list of bad pairs was one short.** `scout`/`outside_universe` is a sixth, and
   nothing complained because spec 99's walk runs engines → map and that code *is* in the map.
2. **Engine 7 `scout` has the same shape as engine 9, which nobody knew.** None of its twelve real
   codes can reach `rejections` at all: it publishes `empty_universe` exactly when there is no
   candidate, and engine 19 writes no rejection without a candidate pair. Its exclusion codes are a
   per-pair tally over the universe, not a refusal of a candidate — so that row had to change
   engine, not merely code, exactly as engine 9's did.
3. **`REASON_PROSE` never needed the codes to be real, and that is the mechanism that hid five
   phases of drift.** `operator_reason` prefers the sentence stored beside the code, so the console
   rendered correctly whatever the code said. The earlier claim here that the map "maps both
   vocabularies" is wrong in detail: it maps five of six, and `dissimilarity_index` was retired by
   spec 71 without anything noticing.

**And a control worth keeping.** B's M3 applied a real code filed under the wrong engine *and*
widened the enumeration to the union over all engines: `5 passed`, and `276 passed` across the
wider lane. **The per-engine scope of that enumeration is the single clause doing the work** — one
line wider and a real code under the wrong engine passes everything. Also: B's first test reported
five bad pairs rather than six, because its sampled draw never picked the `order_book` row, which
is why the second test walks the constant rather than the written rows.

### `EquitySnapshotRow.cash_source`'s default removed (lead), 2026-09-18

Operator ruling, and spec 113's own recommendation. The default was `CYCLE_START` while engine 19
did not pass the field — a required field would have made engine 19 raise on every tick and written
**no equity row at all** — and spec 114 made engine 19 pass it on both branches, which is the
precondition the default was waiting on. The field is now required; ten fixture sites across eight
files pass it explicitly. **The removal landed with the operator's condition: a test that a row
lacking a source is refused**, proven red by restoring the default from a byte copy (only that test
failed; `contracts.py` sha256 identical after the restore).

**The condition earned itself within the hour.** Adding the keyword to the store's `make_equity`
helper made B's old `test_a_row_built_without_a_cash_source_says_cycle_start` **pass while
asserting nothing** — it called the very helper that now supplies the value. Retiring it without
the replacement would have removed a check rather than tightened one, which is exactly what the
operator said when they ruled.

**Two process mistakes of the lead's, recorded rather than quietly fixed.** (1) The red measurement
that enumerates every broken site was run as `pytest ... | tail -4 > log`, which kept the summary
and threw away all 39 failure names and 167 error names — the "evidence destroyed at the pipe" rule
from `code-standards.md`, which the lead had written into HANDOFF 7 a few hours earlier. Re-run
redirected whole; 30 minutes lost and nothing else. (2) The script that inserted the `CashSource`
import left the block unsorted in two files, and **the gate caught it** (`ruff` I001 inside
`toolchain_green`, a real FAIL on the lead's own work), taking two attempts to place the name
correctly. Both are in `docs/build-log/phase-6/lead.md`.

### SPEC 109 (A): the last of the stale fallback prose, and three findings

Eight sites rewritten across six files — the five spec 109 named, plus `clients/kraken/rest.py`,
`tests/clients/kraken/test_rest.py` and `platform/config.py`, all carrying the identical sentence
("invariant 2's paper-mode fallbacks are the consumer's decision"). **No behaviour, no payload and
no assertion changed**; both test names were kept, because each states a property that is still
true and is now unconditionally true. A's rule for the rewrites: **point at invariant 2, never
paraphrase it** — all nine sites were paraphrases, and each had needed re-editing at every
amendment (2026-09-10, 09-16, and tonight).

1. **An assertion in A's own lane that cannot fail.** `tests/engines/test_exchange.py` asserts
   `data["fee_tier"] is None` and then `"tier" not in str(data.get("fee_tier"))` — which is
   `"tier" not in "None"`, a tautology given the line above. Left for its owner: a prose spec does
   not touch assertions.
2. **Invariant 14 grants a retained balance nothing reads** — see "Open questions" in
   `docs/build-log/phase-6/overnight-decisions-2026-09-18.md`, Q1, raised to the operator.
3. **`platform/config.py::load_credentials` told a fresh clone it could trade**: *"paper mode runs
   the whole pipeline without one, and invariant 2's paper fallbacks exist exactly so that it
   can."* Both halves false, and it named paper fallbacks as the **mechanism**. Rewritten rather
   than only reported — and the distinction from finding 2 is the test that matters: **here the
   ruling exists and is explicit** (invariant 2 spells out what a keyless clone does and does not
   do), so only the sentence was stale; in finding 2 the ruling points the other way from the
   prose, so choosing which fact to write would have been answering the question.

**A's own method correction, worth more than the edit.** Its first CRLF count used
`grep -c $'
$'` and reported all ten files as wholly CRLF, four of which hold no CR at all — the
giveaway being every count equalling `wc -l`. Re-measured in Python, the tool that would do the
writing. Trusting the first reading would have converted six LF files to CRLF wholesale: a diff
that hides a real change inside three thousand touched lines. `code-standards.md` already warns
that this shell's `grep -c $'
$'` lies; this is the second time it has been caught doing so.

**No mutation table, with the reason stated rather than the omission left to be noticed:** the
change adds and alters no assertion, so there is nothing to mutate that would not merely re-test
the existing tests. What stands in for it is the verification done before each sentence was
written — engine 10's read of `failed_fetches` traced to the line, engines 21's and 22's retention
reads enumerated across all of `src/`, and the `Balances`/`starting_balances` shape claim checked
against both declarations. **Two of those three became findings, which is the evidence they were
checks rather than readings.**

### SPEC 120 (C): the seed-vocabulary finding is closed, and both directions are now asserted

Five orphaned `REASON_PROSE` keys retired — `insufficient_depth`, `meta_label_veto`,
`no_candidate_cleared`, `outlier_market_state`, `outside_universe` — **derived from the code, not
taken from the spec**, which is the lesson of B's finding 1. The producer set is every
`REASON_*`/`HOLD_*` constant across `acsoe.engines.*` plus every code `clients/store/seed.py`
writes; `REASON_PROSE` is now 65 entries and the two sets are exactly equal. **The inverse walk is
an assertion rather than a warning** — reporting orphans as a warning is why five keys sat there
unnoticed — and its docstring records why both directions are needed: one catches a silent "No
reason was recorded.", the other catches prose for a refusal the system cannot make.

**Engine 7's twelve codes are kept, correcting B's finding 2 in one respect.** They cannot reach
`rejections`, but they *are* produced: engine 7 publishes them as a per-pair tally and the
console's empty state renders it. **Unreachable-as-a-rejection and unproduced are different
properties, and only the second is what a prose retirement is about.**

**Three more findings.**
1. **`outside_universe` never had a producer at all** — it was not a retired code. `feature-specs/44`
   step 7 told B "it already exists in C's `REASON_PROSE`"; B then built engine 7 with twelve
   specific exclusion codes and emitted no generic one, and **nothing ever checked that the key got
   used.** Nothing is lost, but a spec asserted a key was in place and no test held it to that.
2. **The seed half of the producer set is currently unfalsifiable**: since spec 119 every seeded
   code is also an engine code, so removing that half changes nothing an orphan test can see. It is
   guarded by a vacuity test rather than left implicit, because the failure it hides is a **false
   orphan** — a key proposed for retirement that the console still needs.
3. **Four pieces of C's own prose and one test rested on the retired keys** (each justified by "it
   is already on seeded rows", which B's spec 119 made false that morning) and moved with the
   retirement. The test had asserted `meta_label_veto` **in** the map for that dead reason and now
   asserts it **out**. **A test that pins a justification has to move when the justification does,
   or it pins the wrong thing while staying green.**

**And the same control shape as B's M3:** C's N3 widened the producer set by one line and a key
nobody produces passed everything. In both halves of this work, **the scope of the enumeration is
the single clause doing the work.** The premise itself is now tested too: `operator_reason` prefers
a row's stored sentence over the map — the mechanism that hid five phases of drift — so the
retirement no longer rests on it silently, and the cost is written down (a row carrying a retired
code with *no* sentence renders "no reason recorded", which no producer writes today and the
forward walk would catch first).

### PHASE 6's NINE CRITERIA ARE GREEN, 2026-09-18 02:40 local

`verify.py --phase 6`: **13 criteria, 13 PASS, 0 FAIL, 0 PENDING, exit 0** —
`logs/verify/phase6-20260918-nine-lead-*.log`, `toolchain_green` reporting
`3297 passed, 2 skipped`. The first complete paper trade runs end to end through the registered
chains at fee tier 3: a post-only entry past all eight gates, a fill at its limit, a minute-by-
minute watch, and an exit on each of target, stop and timeout, with every order, position, trade
and equity row reconciled against figures recomputed from the book and the live fee tier. The
phase is **not closed**: the operator wants to see the trade first.

### Standing rules from 2026-09-17/18, recorded because they lived only in conversation

- **The gate is `verify.py` alone**, with `mypy` and `ruff` before it; the bare `pytest` run is
  retired. Reasoning in `code-standards.md`.
- **Push notification to the operator only when blocked on a ruling**, one line naming what is
  blocked and what the question is, and the blocked item stops while other work continues. Never
  for progress or boundary reports.
- **Any finding or design choice costing more than about three hours goes to the operator with
  the options before anyone starts on it.** Gate runs, re-gates and already-agreed work are
  exempt and take what they take. (~48 hours of coding time remained for Phases 6 to 8 when this
  was ruled.)
- **The seed-vocabulary reconciliation and spec 109 stay in the phase**, scheduled after the nine
  criteria are green. This code goes into a dissertation: a comment describing a fallback deleted
  yesterday is something a reader believes, so **correct prose is part of the deliverable, not
  decoration on it.**
- **Stale prose with no decision entry behind it is a FINDING, reported, not a typo silently
  corrected.** Three of this phase's findings started as something that read wrong.
- **What does not change:** every assertion proven capable of failing with the proof in the build
  log; one authoritative gate at every boundary; mutation over reading; commit and push at every
  boundary. The three defects this phase found — the entry double count, the unrecorded error
  tick, the exit-cycle row — would each have shipped as working code.

### Price precision is read live, and is held as a constant nowhere

Checked in the code 2026-09-18 and recorded because it was nowhere written down. Invariant 2's
table already lists "tick size, decimals" as exchange-supplied; this is the confirmation that the
code honours it. `clients/kraken/rest.py` parses `pair_decimals` and `tick_size` out of
`AssetPairs`; engine 1 publishes them; **engine 18 `execution`** rounds a limit price down onto
`pair_decimals` before placing it (`round_down_to_tick`, which refuses a negative value as "not a
grid"); **engine 7 `scout`** refuses a pair whose barriers fall inside one `tick_size`
(`barriers_below_tick_size`). No constant anywhere holds a precision, and the console holds none
either — it renders the quantum its writer stored. **So the locked decision on exchange-supplied
values covers precision exactly as it covers fees and minimums.**

### ADA/USD: a tool that answered "I cannot tell" rather than a plausible number

Spec 101 measured the recorded book prices against the recorded `AssetPairs` declaration. For
**BTC/USD** the declaration is `pair_decimals: 1` and all 783 recorded prices carry exactly one
decimal — the exchange is on its own grid, so the extra digits in the criterion's mark were the
harness's own pinned bid and **not** an engine 3 fault. For **ADA/USD the recorded `AssetPairs`
carries no entry at all**, so there was no declaration to compare against, and C reported it
**inconclusive rather than inferring a precision from the prices it happened to see** — which a
quiet pair could make wrong, and which would have been the fabricated exchange value `AGENTS.md`
forbids in its first paragraph. Recorded as the behaviour to keep: a tool that returns "I cannot
tell" beats one that returns a plausible number. **Spec 118 (C)** turns the comparison into a
standing criterion over both committed fixtures, scheduled after the nine criteria are green; it
can never go red because Kraken changed its settings, only because a re-cut fixture is internally
inconsistent.

### RULING 2026-09-18: rule 4 amended, and rounding barriers at write time rejected on the record

C's spec 101 criterion measured what the console renders against the pair's `pair_decimals` and
found the **mark, target and stop** past it; only the entry price sits on the grid, because engine
18 quantizes it before placing. The operator amended `ui-context.md` rule 4 rather than round
anything: **an order price renders at the precision it was stored at; a derived threshold renders
at the precision it was computed to, and the console does not round it.** Rule 4 has never been a
rule the console could obey — it reads only the store, the store holds **no pair rules**, and it
renders whatever quantum the writer chose. It is a rule about **writers**.

**Rounding the barriers at write time was available and is rejected, for a reason that has nothing
to do with display.** Engine 21 holds `state["exchange"]["pair_rules"]` at the line where it writes
`target_price` and `stop_price` (it already reads `pair_facts` there for `base` and `quote`), so
the option was real. But `research/labelling.py` computes its barriers the same unrounded way
(`close × (1 ± pct)`), so rounding the live ones would make the system trigger on barriers **the
training labels were never built from** — a look-ahead-shaped inconsistency, and a silent one.
Rounding in the view was rejected too: it needs a migration, a writer and a new seam into C's lane
to change how three numbers look, and `stop_price` **is** the trigger engine 21 compares against, so
rendering it rounded would show the operator a number that is not the threshold. Recorded here
because someone will otherwise propose it again.

**The mark is a separate case, still open.** It is an exchange-supplied bid passed through
unchanged, not a product, so it should already be at the exchange's precision. C measures it against
`pair_decimals` separately and reports; a breach is engine 3's, in A's lane, and a finding of its
own — not part of this amendment.

**And a criterion that pins a value cannot judge it.** C's console criterion supplies the mark it
then measures, so on that one figure it is judging its own harness. Recorded as the standing shape
it is: an assertion about a value the test itself supplied proves nothing about that value.

**Also ruled:** engine 19's two extra refusals stay (a closed trade with no `net_proceeds`; engine
21's rows not covering what the store still holds) — both fail closed, and a gap in the equity
series is visible to engine 17 where a wrong row is not. **Each refusal records which case it was:
a gap with no reason is the same defect as a number with no provenance.** And
`EquitySnapshotRow.cash_source`'s default is removed after the nine criteria are green, **landing
with a test that a row lacking a source is refused** — otherwise the change deletes a check instead
of tightening one.

### The operator's rulings on the overnight log, 2026-09-17 morning

**D3 accepted** (spec 105's criterion rejects a NULL fill-tick mark: the branch was reachable only by a
regression of spec 106). **D4 accepted and made standing** — `code-standards.md`, "When a gate must be
re-run before a commit". **D8 accepted** (the outage criterion fails `AssetPairs` too: strictly harder,
and its message names both failures). **D6 and D9 called out as the right instincts**: a criterion that
builds its own chains can pass while the registry is wrong; an assertion that is true trivially is not
an assertion. **D1, D2, D5 and D7 were correctly bucketed as "how"** — the bucketing is calibrated and
should not escalate more.

- **Q1 → remove `CostAssessment.fallbacks_used`** (spec 111, B). An always-empty field reading as "no
  fallback fired" on a record that cannot record one is a claim that looks true and means nothing.
  Engine 22's field stays: it carries a real value. If C's fake cost engine in
  `test_phase3_criteria.py` goes red, **C first establishes what that test was asserting** — a fake
  publishing a field nothing produces may have been passing against a shape the real engines never had.
- **Q2 → neither offered option; a third** (spec 112, B, in engine 17's tests): a test asserting
  `trading.entry_unfilled_window_s < safety.max_consecutive_data_blocks × timeframes.loop_tick_s`, all
  three read from config, commented that while it holds invariant 14's resting-entry clause is
  reachable only through an operator Close all — so a change to either value fires the test as notice
  that the clause has become reachable and untested. It forbids nothing and couples nothing; it makes
  the change visible. The lead adds a one-line pointer to it in invariant 14 once it exists.
- **F1's other half → a Phase 7 item, recorded not acted on:** engine 7 does not skip a pair that
  already holds a position, and engine 11 then refuses it, so a candidate that cannot succeed is
  computed through six engines every tick.
- **E1 → Known Risks**, as the second unrecoverable recording gap. Nothing else to do.

**Overnight, operator asleep:** decisions taken are listed in
`docs/build-log/phase-6/overnight-decisions-2026-09-17.md`, with the rejected option for each.
The network was down 03:13–08:20 UTC; the recorder was disconnected for those 308 minutes and
that span of book history is lost.

### FINDING: a defect mutation testing structurally cannot reach

**The first documented instance in this project, and it is evidence rather than theory.**
Mutation has been the main defence since Phase 3 and this is the shape it cannot see.

Engine 14's truncation tripwire — publish no weights when a leaderboard read "came back exactly
full", because a truncated window produces weights that still sum to one over the wrong set — was
ruled by the lead onto **both** read paths, the windowed fallback and B's new unlimited
enumeration. On the unlimited read that comparison is not a weaker check, it is **a different
claim sharing the same arithmetic**: it fires on a model that happens to have exactly
`_WINDOWED_PROBE` rows, a false positive costing that tick **all** of its weights, and over 405
folds that is not negligible.

**No mutation could have found it, and no fixture would have shown it.** The defect only appears
when the row count equals the probe constant exactly. A fixture is written with the row count the
test needs, never with that one, so every arm of every sweep passes and the sweep reports a clean
kill rate over the branch. The code is wrong for exactly one input that no test author would ever
choose, and mutation testing asks "would any test object to this change" — not "is there an input
nobody thought to write".

**Found by B3 reading C-models' code.** Neither agent's tests could have surfaced it; a colleague
reading a diff did. Recorded here rather than folded into a testing rule, on the operator's
instruction, because the point is not the fix — it is that **the project's primary defence has a
blind spot with a name and a worked example**, and code review is what covers it. The fix: the
length check stays on the windowed fallback, where "came back exactly full" is a fact about a
*limited* read and is exactly right; it is gone from the enumerating path; and the lead's
requirement that the detection outlive B's read as "the assertion that the fallback is
unreachable" is met **by a test rather than by a runtime heuristic**.

### UNATTRIBUTED, and it stays that way

`test_all_leaderboard_rows_is_scoped_to_one_model` failed once in a batch of 180 and passed on an
identical re-run minutes later, while B was landing that exact method. C-models **did not hash the
file on either side**, so it cannot prove the failure was a concurrent save rather than the known
native fault, and it recorded the gap in its own evidence rather than choosing between them.

**Do not resolve this later by reasoning.** Both explanations remain available and neither was
measured; a plausible account written months from now would be a new claim wearing the authority
of a contemporaneous record. It is correct as it stands, and it is the standard working — the
project's rule is that *unexplained* is an acceptable thing to write, and its companion, from this
phase, is that `unexplained` written where a documented mechanism already fits dilutes the real
entry. This one fits neither test, so it stays as it is: one observation, two candidates, no
evidence to separate them.

### Four smaller rulings of 2026-09-16, recorded here because they lived only in build logs

1. **Engine 11's per-pair refusal is asked BEFORE the portfolio cap** (lead, overturning B's
   original order). The cap is inert at this balance, so asking it first made invariant 6's
   specific clause invisible on exactly the ticks where both fire. Four places carried the old
   argument and all four moved together, including the README's numbered gate-condition list,
   whose order *is* the behaviour.
2. **Engine 18 publishes a reason code rather than raising** when an exchange order for one of its
   own entries comes back with no `limit_price`. A raise becomes `ERROR`, engine 19 writes
   `block_records.status = 'ERROR'`, and engine 17 counts those against
   `safety.max_errors_in_window` and freezes the account. **An exchange contradicting itself about
   one order is not the system malfunctioning and must not spend the breaker's budget.**
3. **Engine 14's aggregation, which spec 97 never named.** The leaderboard holds one row per
   version *per fold*, so there is a step between rows and weight: the **equal-weighted mean over
   a version's folds**, because every fold is one out-of-sample measurement and equal weighting
   adds no unstated judgement about recency or longevity. Amended twice by C-models on evidence:
   **duplicate `(version, fold)` rows are collapsed to the latest rather than averaged**, since
   the store returns every duplicate on purpose and averaging would let a data artefact move a
   weight; and **only the engine's own `model_id` is weighted**, since normalising across families
   would hand one family part of another's weight.
4. **The leaderboard read takes both halves**: B's non-truncating enumeration *and* C's truncation
   tripwire — the latter now on the windowed fallback only, per the finding above.

### FINDING: the Phase 0 seed's refusal vocabulary is invented, and no engine can emit any of it

Found 2026-09-16 by spec 99's walking test, from the one direction it cannot see directly — a
fixture rather than an engine. `clients/store/seed.py` writes seeded `rejections` rows as
`(engine, code, sentence)` triples, and **not one of those codes exists in the named engine's
`contracts.py`**: `order_book`/`insufficient_depth`, `prediction`/`dissimilarity_index`,
`decision`/`no_candidate_cleared`, `anomaly`/`outlier_market_state`,
`skeptic`/`meta_label_veto`. The real codes are `book_too_thin` (which is **not** a refusal),
`di_refused`, `pair_disagreement` and its four siblings, and so on.

**Why it happened and why nothing caught it.** The seed was written in Phase 0, before any engine
existed, so inventing plausible codes was the only option — and correct at the time. Nothing has
compared the two since. `REASON_PROSE` maps both vocabularies, so the console renders every row
and looks right; the walking test added in Phase 6 walks **engines**, so it can prove no engine
code is unmapped but not that no mapped code is unproduced.

**The sharpest instance, and the reason this is a finding rather than housekeeping.** Engine 9
`order_book` **cannot refuse at all** — one `EngineStatus.OK` in the module, zero of the others,
by operator-consistent ruling — so when a book is too thin it publishes no estimate and engine 10
`cost` refuses on the absence. The seeded row therefore shows the console a trade stopped by an
engine that is structurally incapable of stopping one. Since Phase 1, the console's rejection
feed has displayed a refusal vocabulary the system cannot produce.

**Ruled, scheduled after the Phase 6 gate:** B reconciles every seeded rejection to an
`(engine, code)` pair the live system can emit — engine 9's becomes engine 10 refusing on the
absent estimate — and C then retires the prose that no longer has a producer. Every code stays
mapped until B's half lands, because the seeded rows exist and must render; silence on the
console is the defect `REASON_PROSE` exists to prevent.

### The operator's five rulings of 2026-09-16

1. **The fill simulator is a client-layer paper broker**, `src/acsoe/clients/paper/`, B-owned,
   implementing A's order surface and wrapping `clients.kraken` in paper mode. **This corrects the
   operator's own earlier ruling** that it live under `engines/execution/`: contract rule 3 forbids
   engines 21 and 22 importing another engine, and a resting post-only entry fills on a later tick
   that only engine 21 sees. The correction is recorded as the operator's because the earlier
   ruling was made on a reconnaissance report that found the ownership gap and did not follow an
   order far enough to find the import one. Ownership row and reasoning in `ownership.md`.
2. **Engine 16 `decision` stays in the chain and becomes a gate.** Its job is the consistency check
   nothing performed: every approving engine judged *this* tick's candidate — same pair, same
   decision bar, an approval carrying a quantity — and it blocks otherwise. It also *composes* the
   order intent engine 18 reads, which its README calls composition and never decision. `is_gate`
   is `True`, the registry table's Gate column carries it, and invariants 3 and 4 both name it.
3. **In paper mode the balance is always the paper ledger** — `paper.starting_balances` adjusted by
   every recorded fill, whether or not the real fetch succeeded. Invariant 2's table is reworded.
   Recorded as a **defect found in planning**: the invariant promised an adjustment nothing
   implemented, so engine 11 would have sized against cash an earlier paper fill had already spent,
   and engine 19's equity counted that cash twice — in the series that moves the drawdown threshold
   engine 17 freezes on.
4. **The execution offset bandit is deferred to Phase 7.** Phase 6 places every entry at the best
   bid. It is a Locked Decision that is absent from the Phase 6 row, needs a table that does not
   exist, and learns from a fill history that does not exist either. The fixed rule is a recorded
   absence in engine 18's README, not a choice anyone defended.
5. **The skeptic's training set caps to a rolling window of the last 13 folds** (Phase 7
   prerequisite 1), mirroring the locked past-only 90-day window, bounded by construction and
   needing no seed. **The cap is Phase 7 work, not Phase 6**: capping changes training, so
   re-measuring means retraining 405 skeptics. **Finding 1's 0.531 survivor rate was measured on
   the uncapped skeptic and must be re-measured before it is cited anywhere** — a finding measured
   on code that no longer exists is a claim, not a measurement.

**Four smaller decisions the lead made and the operator approved**, all overturnable: barriers are
measured from the **fill price**, because engine 11 sized the quantity against it; a resting entry
fills only on a trade **strictly below** its limit, because queue position is unknown; a stop and a
target touched in one tick resolve to **stop**, as the labels do; and engine 9 estimates slippage
at the whole quote-currency balance as an **upper bound** and never blocks on its own — engine 10
refuses on the absent estimate, because a non-gate that refuses makes `is_gate` wrong.

*Phase 5, for the record.*

**Phase 5 — Models. GREEN AND CLOSED 2026-09-15** — 14 criteria, **14 PASS, 0 FAIL, 0 PENDING**, with phases 0 to 4 re-gated in order on the same quiet tree and every one exit 0. All twenty-one specs (59 to 79) delivered across A, B, C and the lead; the narrative account is `docs/build-log/phase-5.md`, consolidated from the four per-agent logs at close. The three withheld thresholds are supplied and all three are **provisional** until the chain runs end to end. **Phase 6 — Decision and execution is next**, and it opens carrying the six Phase 7 prerequisites, engine 8's `is_buy`, and the three findings below. 

*The phase as opened, for the record, 2026-09-12.* Phase 4 preflight re-run on the clean tree at `ef8f1f0`: **10 criteria, 10 PASS, 0 FAIL, 0 PENDING**, `replay_full_archive` skipped as `--live`. Nineteen specs (59 to 77) were written from the Phase 5 row and the ownership map and approved by the operator with all nine rulings confirmed (recorded under Locked Decisions) and one addition: the effective sample size is reported per fold beside that fold's row count, not only in aggregate. **Two more were added during the phase** — 78 and 79, A's streaming fixes to the full-archive replay — for twenty-one in total. The shared task list is `feature-specs/PHASE-5-TASKS.md`. The three operator values that opened the phase absent were all supplied before it closed: `skeptic.veto_threshold: 0.50` on 2026-09-14, `anomaly.threshold_percentile: 0.99` and `prediction.di_percentile: 0.99` on 2026-09-15, every one **provisional**. **This is the phase where a mistake looks like success**, so every assertion is proven capable of failing and the proof goes in the build log — and it held: the defects that mattered most this phase were each found by a mutation or a recomputation rather than by a red test.

**Gates re-run 2026-09-15, phases 0 to 5 in order on a quiet tree, every phase exit 0:**
Phase 0 **7/7**, Phase 1 **10/10**, Phase 2 **9/9**, Phase 3 **9/9**, Phase 4 **10/10**
(`replay_full_archive` skipped as `--live`), Phase 5 **14 criteria, 14 PASS, 0 FAIL, 0
PENDING**. The last PENDING — `di_fitted_on_predictor_training_set` — is resolved by the
operator's `prediction.di_percentile` ruling and now judges the artefact by row identity.
**The close and the consolidation stay withheld by the operator**, so this table is
unchanged and `docs/build-log/phase-5.md` is still not written. Logs:
`logs/verify/20260915-final-summary.txt`.


*Phase 4 — Memory and replay.* Green on its gate 2026-09-11; the operator withheld the close and the consolidation, so `docs/build-log/phase-4.md` does not exist and the four per-agent logs under `docs/build-log/phase-4/` are the record. The three operator rulings of 2026-09-12 (past-only walk-forward, 2017 cutoff, thin-pair floor as a named knob) were applied against the full 234-pair archive; the dataset is 20,331,237 labelled decision bars, 23.89% target, 51.27% stop, 24.84% timeout, 0.376% decided by the both-barriers rule.

*Phase 3 — Economics. GREEN AND CLOSED*, verified **2026-09-10**: 9 criteria, **9 PASS, 0 FAIL, 0 PENDING**. All eleven specs (37 to 47) delivered across A, B, C and the lead. All four gates re-run at close on a quiet tree, every one exit 0 — Phase 0 7/7, Phase 1 10/10, Phase 2 9/9, Phase 3 9/9 — with `pytest` 1340 passed, `mypy --strict src/` clean across 71 files and `ruff check src/` clean. Engines 7 `scout`, 10 `cost`, 11 `risk` and 17 `safety` are built, wired to A's real Kraken client, and registered in `bootstrap.py`: `is_gate_matches_registry` reports **8 engines registered; 0 mismatches (5 gates)**. The narrative account is `docs/build-log/phase-3.md`.

The phase's opening problem was the audit: engines 10, 11 and 17 were **built, not done** — all three read a `state["exchange"]` payload engine 1 does not publish, and one read a price *nothing* publishes. They were green against a payload nothing writes, because every test built that payload by hand in the shape the engine expected. The operator ruled the fixtures be rewritten from engine 1's real output rather than repointed. **Phase 4 is next.**

**Phase 4 — Memory and replay is next.** It opens carrying the deferred items under Open Questions below, including the console tally that needs engine 19 and the remaining mutation survivors A did not reach.

*Phase 2 — Data spine. Green and closed*, verified **2026-09-10**: 9 criteria, **9 PASS, 0 FAIL, 0 PENDING**. Nine specs (25 to 33) across A, B, C and the lead, plus three Phase 3 engines (34 to 36) built concurrently by B and deliberately excluded from this gate. The lead re-verified independently at close and re-ran all three phase gates: Phase 0 7/7, Phase 1 10/10, Phase 2 9/9. The two criteria PENDING at the last checkpoint are both resolved — `data_guard_blocks_bad_data` once the operator supplied `data_guard.max_data_age_s`, and `recording_span_continuous` on a clean 24-hour recording reporting **99.98% of its span actually recorded** against a newly enforced 0.98 floor. The narrative account is `docs/build-log/phase-2.md`.

*Phase 1 — Interface. Green and closed*, verified 2026-09-09: 10 criteria, 10 PASS, 0 FAIL, 0 PENDING. All nine specs (16 to 24) built by C alone; A and B had no Phase 1 work and none was invented for them. The lead re-verified independently of C's report: `pytest` 707 passed, `mypy --strict src/` clean across 35 files, `ruff check src/` clean. Survived three IDE crashes mid-phase with no lost work. **Phase 2 — Data spine is next**, and it opens carrying two obligations recorded under Open Questions, one of them a live defect in `core/`.

*Phase 0 — Structure. Green and closed*, verified 2026-09-08: 7 criteria, 7 PASS, 0 FAIL, 0 PENDING. All 16 feature specs built, all three teammates and the lead reporting nothing outstanding.

## Current Goal

**Phase 3 — economics.** Engines 7, 10, 11 and 17, zero ML. Three engines wired to A's real Kraken client rather than to a mock, plus engine 7 `scout`, which needs a real tradable universe and was deliberately excluded from the overlap for that reason. `CONDITION_ACTION` is ratified — see Decision history — and the daemon stops running with three empty client slots.

**The audit that opened the phase is the reason it is not a small phase.** Engines 10 and 11 read `state["exchange"]["fees"]` and `state["exchange"]["pairs"]`; engine 1 publishes `fee_tier` and `pair_rules`. Engine 11 reads a `last_price` that **nothing in the system publishes** — the only `last_price` in the codebase is a column on an open-position row. Both read a `fallbacks_used` key that does not exist. Every test builds `state["exchange"]` by hand, so both engines are green against a shape their publisher does not produce. This is the third appearance of that failure in this project and the operator ruled that the fixtures are rewritten, not repointed.

*Phase 2's goal, for the record:* the data spine — engines 1, 2, 3 and 4, the historical OHLCVT loader, and the recorder engine superseding `scripts/record.py`. The `core/` command reader was fixed first, before any engine work. The persisted system mode was spec 31 (B) and spec 32 (C), with the `core/` write staying lead work. All delivered.

*Phase 1's goal, for the record:* the full console against the seeded database — status band, positions, cycle feed, history, research views, WebSocket updates and the three commands. Nothing in the console reads a live exchange; it renders the Phase 0 seed, which is the whole point of building the interface before the backend. All delivered.

*Phase 0's goal, for the record:* `scripts/verify.py` first, then the package skeleton, `core/` contracts and three-chain orchestrator, `platform/` config, clock, logging and live guard, CLI entrypoints, `config/default.yaml`, SQLite schema and migrations, store client, seed generator, fake Kraken client, test harness, and `scripts/record.py`. No engines. All delivered.

## Phase Status

A phase is green only when `python scripts/verify.py --phase N` passes every criterion.

| Phase | Status | Verified |
|---|---|---|
| 0 — Structure | **Green** | 2026-09-08 — 7 PASS, 0 FAIL, 0 PENDING; re-verified 2026-09-09 at the Phase 1 gate, same result |
| 1 — Interface | **Green** | 2026-09-09 — 10 PASS, 0 FAIL, 0 PENDING (9 at close, plus `toolchain_green` once it was registered for every phase) |
| 2 — Data spine | **Green** | 2026-09-10 — 9 PASS, 0 FAIL, 0 PENDING; all three phase gates re-run clean at close |
| 3 — Economics | **Green** | 2026-09-10 — 9 PASS, 0 FAIL, 0 PENDING |
| 4 — Memory and replay | **Green on its gate; close and consolidation withheld by the operator** | 2026-09-11 — 10 PASS, 0 FAIL, 0 PENDING; re-verified 2026-09-12 at the Phase 5 preflight, same result, `replay_full_archive` skipped as `--live` |
| 5 — Models | **Green** | 2026-09-15 — 14 PASS, 0 FAIL, 0 PENDING; phases 0 to 4 re-gated in order on the same quiet tree, all exit 0. Specs 59–79: A (61, 78, 79), B (62, 76), C (60, 63–75), Lead (59, 77). Nine rulings confirmed by the operator plus one addition (per-fold effective sample size) |
| 6 — Decision and execution | **Green** — closed by the operator 2026-09-18 after reading the first paper trade's walk-through | 2026-09-18, the final gate at the close — **13 criteria, 13 PASS, 0 FAIL, 0 PENDING**, exit 0, `toolchain_green` `3309 passed, 2 skipped` (`logs/verify/phase6-20260918-phase6-close-lead-verify.log`). 2026-09-18 evening — **13 criteria, 13 PASS, 0 FAIL, 0 PENDING**, exit 0, after spec 118's criterion was removed and the Phase 2 candle criterion renamed (`logs/verify/phase6-20260918-rename-remove118-lead-verify.log`); earlier the same day phases 0–6 were re-gated in order at `98c0485`, all exit 0, when Phase 6 had 14. Specs 80–125 (102 parked to Phase 7; 118's criterion removed; 121–125 open with their owners, prose only) |
| 7 — Evaluation | **Next — not started** | — |
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

- **Phase 2 itself. Green on 2026-09-10.** All nine specs (25 to 33) built, across three teammates and the lead. The narrative account is `docs/build-log/phase-2.md`. Merged at close from the three progress files.

| Agent | Specs | Delivered |
|---|---|---|
| A — Platform | 25, 26, 27, 28, 29, 30 | The Kraken REST and WebSocket clients, with the envelope check and its paired positive test; engine 1 `exchange`; engine 2 `market_data_recorder` and `scripts/recording_report.py`, whose digest accounts for unrecorded silence as well as explicit `gap` markers and refuses to write a span under 24 hours; engine 3 `market_sensor`, building 15-minute candles that match a Kraken OHLC fixture within one tick size and 0.1% of volume; engine 4 `data_guard` with four distinct operator-readable block reasons; and the historical OHLCVT loader, which marks gaps and never interpolates. |
| B — Store | 31 | The persisted system mode as a column on `runs` rather than a single-row state table, migration `0002`, and the store surface the `core/` write and C's reader both sit on. Also 34, 35 and 36 — engines 10 `cost`, 11 `risk` and 17 `safety` — built concurrently under the Phase 3 overlap ruling and **deliberately not counted toward this gate**. |
| C — Interface | 32, 33 | All six Phase 2 criteria in `verify.py`, each proved twice — PENDING on an absent subject and PASS on a fabricated one — and each shown able to FAIL; and the status band reading `Running` and `Frozen` from the persisted mode, which was the Phase 1 debt this phase was required to pay. |
| Lead | — | The `core/` command reader, broken in three places rather than one; the run record at startup and the persisted-mode write; `bootstrap.py` registration of engines 1 to 4; the four config keys; the spec set; and the `recorded_fraction` floor that closed the `recording_span_continuous` defect. |

- **Nothing is outstanding for any agent.** A, B and C all report clear. Two items deliberately survive the close and are carried in Next Up rather than hidden: `cli/engine.py` still passes a `Clients()` of three `None`s, and engine 17's `CONDITION_ACTION` table is unratified.

## Phase 6 — how it closed

*Closed by the operator 2026-09-18, after reading the walk-through. The merge below was made in
preparation for the close and stands as the close record; specs 121–125 (prose only) remain
open with their owners and are not phase criteria.*

### Merged for the close

*Merged from the three progress files by the lead, 2026-09-18, as close preparation ordered by the
operator. **The phase is open**: the gate is green and the operator rules on the close after seeing
the first paper trade. Shared task list: `feature-specs/PHASE-6-TASKS.md`. Narrative:
`docs/build-log/phase-6.md`. Commit hashes are from `git log`, because the progress files rarely
record them.*

| Agent | Specs | State |
|---|---|---|
| Lead | 80, 81, 82, 83 | All done: 80 `5f84df3`, 81 `ea17381`, 82 `69038a7`, 83 recorded in this tracker and `phase-5.md`. Plus `context.previous_now` (`4b78593`), `state["block_status"]` (`a668df3`), the `cash_source` default removal (`98c0485`), and tonight's close preparation. |
| A — Platform | 84, 85, 86, 87, 109, 116, and the `order_book` config section for 80 | All done: 84–86 `4d9e106`, the 84 amendment and the config section `8fcc0d2`, 87 `3b2cedf` (its xfail lifted in `ab2bf4f`), 116 `df49cb4`, 109 `adbce06`. |
| B — Store and trading | 88, 89, 90, 91, 92, 93, 94, 103, 106, 108, 110, 111, 112, 113, 119, migrations 0003 and 0004 | All done: 88/89/92 `55cf626`, 90 `b2fb9de`, 91 `41ebf19`, 93 `ee51d2e`, 94 `49e369a`, 103 `178a0a8`, 106 `268f49e`, 108 `40bbc6b`, 110–112 `05a76f6`, 113 `df49cb4`, 119 `c0e95f9`, 0003/0004 `4e129c9`. |
| C — Interface and models | 95, 96, 97, 98, 99, 100, 101, 104, 105, 107, 114, 115, 117, 118, 120; **102 parked to Phase 7** | All done except 102: 95 `8941eec`, 96–98 `a089bc7`, 99 `27b203c`/`c7f6d13`, 100 `27b203c`/`d28b756`/`df49cb4`, 101 `e3b5406`, 104 `3e1ded8`, 105 `76035be`, 107 `dd9ea39`, 114 `df49cb4`, 115/117 `aa3e26f`, 118 `97927d9`, 120 `2beb8ba`. **Spec 102 was parked by the operator** (`fe06a72`); its two partial diffs are in C's scratchpad as named in `c-interface.md`, and item 1 of Current Phase still says the DI prerequisites were "pulled forward", which is true of the plan and not of what landed. |

**The progress files' own status lines are stale, and they are the teammates' files, so the lead
reports this rather than edits them.** Teammates do not commit, so their claims were written
"DONE, not committed" or "gates not yet run" and never moved when the lead committed. Every spec in
the table is committed, but the lines still say otherwise: A `a-platform.md` :16, :278, :328, :358,
:383, :425, :461, :757-763; B `b-store.md` :40, :121, :200, :392, :441, :616-621, :722, :772, :774,
:810-815, :849, :904, :909, :934, :959, :999, :1036 (**spec 92 has no done line at all**),
:1052-1055; C `c-interface.md` :28, :118, :128 (spec 100 bodies "IN PROGRESS"), :212, :222, :271
(spec 102 "IN PROGRESS", parked), :2584-2585, :2737. **The table above is the state.** This is the
shape the night of the 17th named — *a record is not resolved because the resolution exists
somewhere else; the marker has to move* — and each teammate should move its own markers at the
start of Phase 7.

**Carried out of the teammates' files rather than lost with them.**

1. **Standing instructions that outlive the phase.**
   - **The recorder, the recording manager and the funding poller keep running**, never stopped,
     restarted or reconfigured. Order-book history cannot be recovered.
   - The live client's order refusal stays as the **one copy to remove in Phase 8**
     (`rest.ORDER_CALLS`, compared against the protocol).
   - The paper wiring stays written as `== "paper"`, never `!= "live"`.
   - Re-cutting `book_sample.jsonl` moves `order_book_slippage_on_recorded_book`. (It moved spec
     118 too; that criterion was removed and Q3's re-cut is withdrawn with it, 2026-09-18.)
   - Line endings are measured in Python, never with this shell's `grep -c`.
2. **Open items no ruling has closed, beyond Q1–Q3 and S3 above.**
   - **A's tautological assertion**, `tests/engines/test_exchange.py:214-215`:
     `assert data["fee_tier"] is None` then `assert "tier" not in str(data.get("fee_tier"))`,
     which is `"tier" not in "None"`. A's lane.
   - **`research/labelling.py` is still wholly CRLF**: 479 of 479 lines, measured in Python. C's lane.
   - **Two prose items B raised on 2026-09-16 and nobody picked up**:
     - the console sentence for `exits_placed` says exits are "resting", when every exit is a
       market sell (F-new-3)
     - `docs/PROJECT-STATE.md` still lists `fallbacks_used` on engines 10 and 11 (F-new-4)
   - **Design decisions flagged to the lead with no recorded ruling**:
     - B's spec 88 deviation, `_pending` pruned by recording (`b-store.md:993-997`)
     - B's engine 16 choices, optional provenance and the pair/bar check as a walk
       (`b-store.md:791-803`)
     - C's `REASON_`/`HOLD_` naming collision, "a rename is the lead's call"
       (`c-interface.md:2004-2008`)
   - **Undiagnosed one-offs, recorded here so they are not lost**:
     - B's `yaml/scanner.py` fault and `0xC0000005` (`b-store.md:610-614`)
     - C's segfault inside `check_docs_vocabulary` (`c-interface.md:2118-2126`)

     Both fit the known native fault's signature on this machine. Neither was measured, so both
     stay unexplained rather than attributed.
   - **C's stated limitation**: the mutation "the model loses a field" was deliberately not run
     (`c-interface.md:2171-2176`).
3. **Deferred to Phase 7:**
   - spec 102
   - the execution-offset bandit
   - the skeptic's 13-fold cap, with Phase 5 Finding 1 re-measured before it is cited
   - engine 7 skipping a pair that already holds a position
   - the console's scan tally
   - engine 14: watch whether anything starts reading `state["adaptive_router"]`. The guard test
     scans engine 15 only, and engines 16 and 18 grew after it was written.

## Phase 5 — how it closed

*Merged at close from the three progress files, 2026-09-15. Shared task list:
`feature-specs/PHASE-5-TASKS.md`. Narrative: `docs/build-log/phase-5.md`.*

**All twenty-one specs delivered, and nothing is outstanding for any agent.**

| Agent | Specs | State at close |
|---|---|---|
| Lead | 59, 77 | Both done. Plus the nine rulings, the full-archive run and its rebuilt digest, the four threshold studies, the engine 15 review, the registration of 5, 6, 12, 13, 8 and 15, and the close. |
| A — Platform | 61, 78, 79 | All done. Reports nothing in progress, nothing blocked, no gaps owned. |
| B — Store and trading | 62, 76 | Both done, plus the rehearsals of engines 5, 6, 12, 13, 8 and 15 through real orchestrator ticks. Reports nothing outstanding and nothing blocked. |
| C — Interface and models | 60, 63–75 | All fourteen done. The one PENDING it reported — `di_fitted_on_predictor_training_set` — is resolved by the operator's `prediction.di_percentile` ruling and now PASSes. |

**Three things carried out of the teammates' files rather than lost with them.**

1. **A's standing instruction has not expired and does not expire with the phase**:
   `scripts/record.py` stays running. Order-book and spread history cannot be recovered
   retroactively, and engine 9 `order_book` — a Phase 6 engine — still has nothing else to read.
   The recorder has no working graceful shutdown on Windows; a kill costs at most a partial
   final line, because the archive is append-only and every line is flushed.
2. **A's two unverifiable items stand and block nothing**: the REST signing scheme and four
   `map_*` field names in `rest.py` cannot be checked offline, are isolated into single named
   functions, and surface a renamed field as a `KrakenUnavailableError` naming it rather than as
   a default.
3. **C's scan-tally deferral stands.** Engine 7 publishes `scanned`, `entered` and a per-reason
   `excluded` tally into `state` for exactly one tick and no column holds any of the three, so
   the console's empty-state tally still cannot be built. Deferred because the obvious fix —
   one `rejections` row per excluded pair — changes what that table means, and anyone counting
   refused trades would start counting filtered pairs. Phase 7's attribution is the natural
   forcing function.

## Phase 3 — how it closed

*Merged at close from the three progress files, 2026-09-10. Shared task list:
`feature-specs/PHASE-3-TASKS.md`.*

**All eleven specs delivered.** A: 38 TTL-bounded caching, 39 real clients and the derived
subscription scope. B: 40 `cost`, 41 `risk` and the balance fallback, 42 `safety`'s ratified
escalation table, 43 and 44 engine 7 `scout`. C: 45 the seven Phase 3 criteria, 46 the operator
prose for all nineteen reason codes. Lead: 37 the three rulings into the authority documents, 47
the registration of all four engines.

### FINDING: three mechanisms had been charged to one cause for two phases

Intermittent test failures across Phases 2 and 3 were attributed to a native memory fault on this
machine. **There were three distinct mechanisms and two of them were deterministic, fixable
defects.**

1. **`scripts/verify.py::sweep_stale_workspaces` deleted other processes' live databases.** It
   removed every `acsoe-verify-*` directory in the shared temporary directory, and its docstring
   asserted that a directory in use "simply will not delete" — a POSIX assumption written as a fact
   about Windows. `ignore_errors=True` guaranteed *partial* deletion rather than none, so one defect
   produced two symptoms: a vanished directory gives `unable to open database file`, a surviving
   directory with its database removed gives a freshly created empty database and then
   `no such table`. `tests/verify/test_runner.py` calls `main()` nine times, so one `pytest tests/`
   sweeps nine times — and three agents each running the suite is this project's normal state.
   **Fixed:** only leftovers whose newest internal mtime predates this process's start are removed.
2. **A Phase 1 wall-clock criterion was measuring connection setup rather than the push latency it
   named.** Its reported figure fell from 509ms to 6ms once measured from a steady-state connection.
   It could never have detected a promptness regression, because the quantity it reported was
   dominated by something else. **Fixed:** safety net, assertion and evidence are now three
   mechanisms instead of one number.
3. **A genuine native fault remains.** It presents as an `ACCESS_VIOLATION` or `STACK_BUFFER_OVERRUN`
   process crash, not as a test failure, and was seen again at phase close. It is now charged **only
   with what it actually causes.**

**Standing rule, so the third does not re-absorb the others:** a failure is attributed to the
sweeper only if it carries a database error. Anything else is unexplained until it is explained, and
*unexplained* is an acceptable thing to write in a build log. The rule exists because an agent
warned, within an hour of the sweeper being named, that a newly named mechanism will absorb every
flake exactly as the native fault had — and was right that it had already started.

### FINDING: a diagnostic procedure that cannot fail is the same defect as a test that cannot fail

The standing instruction in `PHASE-3-TASKS.md` was *re-run the named test in isolation, and if it
passes it was the intermittent fault.* **That instruction worked every time — because in isolation
nothing else was sweeping.** The mitigation was manufacturing the evidence for its own diagnosis,
and it confirmed the wrong answer on every occasion it was applied, over two phases and four agents.
It was not merely inherited: a fresh entry attributing a zero-byte report file to hardware was
written on the last morning of the phase, by an agent reaching for the rule rather than for the
evidence.

This project spent Phase 3 cataloguing tests that cannot fail while running on a *diagnostic* that
cannot fail. **Apply to a diagnostic the question you apply to a test: under what observation would
this have told me something else?** Now a rule in `context/code-standards.md`, alongside the three
shapes of unfailable test and the mutation practice that catches them.

### The rest of what closed


| Agent | Specs | State |
|---|---|---|
| Lead | 37, 47 | 37 **done**. 47 is the last spec in the phase and waits on 44 |
| A — Platform | 38, 39 | **Both done.** Then a commissioned audit — see below |
| B — Store and trading | 40, 41, 42, 43, 44 | 40, 41, 42, 43 **done**. 44 in progress |
| C — Interface and models | 45, 46 | **Both done.** Then the Phase 1 timing criterion and the harness findings |

**Ten of eleven specs are done.** `verify.py --phase 3` went from *"2 criteria: 2 PASS — Phase 3 is
green"* over four unbuilt or unwired engines, to **9 criteria driving four real engines**. That
false green was the reason spec 45 was ordered first, and it is gone.

**Two paired landings, both done, and the rule they produced.** `kraken.cache_ttl_s` landed first,
then `trading.stable_quote_currencies` — a key the operator had to supply because invariant 7
defines a crypto-quoted pair against a set of stable assets that existed nowhere in the repository
and is not derivable from Kraken's data. `extra="forbid"` means either half alone breaks every test
that reads the committed config, so the field lands with the YAML in one commit.

A's generalisation, now in `code-standards.md`: **the landing order is universal; the resting state
is not.** `cache_ttl_s` was tightened to required because every reader raises on absence, so startup
is the same refusal delivered earlier. `stable_quote_currencies` stays optional because its readers
were *ruled to disagree* — engine 7 fails closed and excludes, engine 2 fails open and publishes the
fact — and a required field overrules both by stopping the process, which would mean the recorder
never runs. A's second half: **a half-landed key is not uniformly safe just because the reader
raises.** `Config.get` raises, the orchestrator turns a raised engine into `ERROR`, `ERROR` blocks —
so a missing key briefly made engine 2 the tick's *primary blocker* and displaced `data_guard`,
which would have written a wrong `block_records.is_primary` for every tick in that window. A
corrupted audit row is worse than a stopped daemon, because it looks like data.


- **Spec 47 waits on spec 44**, which is B's and in progress. That ordering is deliberate: a
  half-wired gate in the live chain turns every other criterion's failure into a puzzle.
- **`scripts/verify.py::sweep_stale_workspaces` is a live defect and C is fixing it.** It deletes
  every `acsoe-verify-*` directory in the shared temp directory, including ones other processes are
  using. Its docstring claims a directory in use "simply will not delete" — a POSIX assumption that
  is false on Windows, and `ignore_errors=True` guarantees *partial* deletion rather than none.
  Reproduced by the lead first try: one sweep took a live seeded database plus two other running
  workspaces. **This is what has been reported as "the intermittent fault" for two phases.** The
  standing advice — re-run the named test in isolation, and if it passes record it as the fault —
  worked, because in isolation nothing else is sweeping, so the mitigation confirmed the wrong
  diagnosis every time it was applied.
- **Three flake mechanisms are now distinguished and must stay distinguished.** The sweeper, which
  always presents as a *database* error; a load-sensitive wall-clock assertion in a Phase 1
  criterion, which C diagnosed independently and has fixed; and the genuine native
  `access violation`, which C saw again today. B's warning, taken as a standing rule: **a newly
  named mechanism will absorb every flake in the tree the way the native memory fault did for two
  phases** — so a failure is attributed to the sweeper only if it carries a database error, and
  *unexplained* stays an acceptable thing to write in the log.

## Phase 2 — how it closed

Kept in full because the phase's difficulties are dissertation material and the summary in `docs/build-log/phase-2.md` points back at it.

### The two PENDING criteria, both now resolved

1. **`recording_span_continuous` — PASS.** The clean 24-hour single-recorder run started `2026-09-09T14:15:29Z` and completed `2026-09-10T14:15:30Z`. `scripts/recording_report.py --write` produced a digest over a **24.07-hour span, 10 segments, 9 accounted breaks, 11,924,857 lines, 20.25 seconds missing in total — `recorded_fraction` 0.9998**. Every one of the nine breaks is a websocket reconnect of between 0.9 and 3.1 seconds. The criterion now enforces a 0.98 floor on that fraction; see the entry below and in the build log.
2. **`data_guard_blocks_bad_data` — PASS.** The operator supplied `data_guard.max_data_age_s`. Stale data, a negative spread and a missing candle each block with a distinct operator-readable reason, and clean data passes. Reporting PENDING while the key was unset was the correct fail-closed reading and never a defect in the engine or the gate.

### The criterion defect, and how it was closed

**`recording_span_continuous` enforced "every break accounted for" rigorously and "a continuous span of at least 24 hours" not at all.** It measured start-to-end elapsed time, so a 24-hour span with nothing missing and a 24-hour span with eleven hours missing tiled identically, carried causes identically, and passed identically. Found by A dry-running the report before depositing rather than after.

**Closed 2026-09-10 with a `recorded_fraction` floor of 0.98**, and the criterion now prints the measured fraction beside the floor so the number the gate turns on is in the output. The floor was deliberately not set when the defect was found: the only archive available then was 49% recorded, and any floor chosen to admit it would have fixed the bar at the number we happened to have rather than at one anybody would choose. Setting it against a clean run is what made 0.98 principled rather than rationalised.

**The full archive is kept as separate evidence.** `tests/fixtures/recording_report_full_archive.json` reports **76.2% recorded across 47.24 hours** — dragged down by a ten-hour silence when no recorder was running (36,122 of the 40,471 missing seconds, 89% of the total) and by the self-inflicted disk-full outage of `2026-09-09T13:06:37Z` with the restarts either side of it. **Both causes predate the clean run**, which starts an hour after the disk incident. **The archive was not modified** — invariant 11 holds; the window is applied to the report and never to the data, and the nine gaps in the windowed report are exactly the nine the full archive reports at or after the clean-run start. Both artefacts are committed, so nobody has to take the good number on trust.

### The five operator rulings this phase

1. **Phase 3's deterministic engines overlap Phase 2.** Engines 10, 11 and 17 built by B against a mocked client and the Phase 0 seed, because they depend on the exchange only through a contract and the seed already carries every fixture `safety` needs. Engine 7 `scout` stays in Phase 3 proper — it needs real data, not a contract. They do not count toward Phase 2's gate.
2. **Spec 25's envelope check needs its paired positive test.** A parser that raised on every response would satisfy the negative half alone.
3. **Spec 30 marks gaps and never interpolates**, stated in the spec rather than implied, because a synthesised candle at a price that never traded invents a barrier touch and fabricates a Phase 4 label.
4. **Spec 32's Phase 1 deferral test is deleted and the deletion recorded** with the decision that retired it. C found the test never existed — the claim came from a docstring that was false when written.
5. **Phase 2 waits for a clean 24-hour recording** rather than closing on a 49%-recorded archive carrying a disk outage we caused ourselves. Everything else in the phase is finished and waiting.

### The pattern this phase kept producing, now eight instances

**A check whose output resembles the claim while the claim is untrue.** `mypy --strict` returning no answer at all behind a numpy stub syntax error; `ignore_errors=True` turning "do not fail the criterion" into "say nothing"; a `b'"gap"'` payload match that would have split segments silently; a fabricated `EngineContext` that agreed with the mistake it was meant to catch; `recording_span_continuous` measuring elapsed time and calling it continuity; assertions in three separate files holding `guard_blockers == []` while naming an empty registry; C's shallow-copy regression test, which passed with the defect it was written to catch deliberately reverted, because module reloading had already made the leak it tested for impossible; and — at the close — `recording_span_continuous` again, unable to tell a 76.2%-recorded archive from a 99.98%-recorded one because tiling, causes and elapsed time are all properties of the *shape* of the evidence rather than its content.

*(The seventh was recorded in C's build log and had not been merged here; the count of six carried in this file until the close was one short.)*

A's generalisation remains the useful form: **an assertion is decayed if it would still pass when the thing it names is false.** Its sibling, already in `ai-workflow-rules.md`, is *fabricate the subject a criterion judges; never fabricate a contract it is held to.* The close adds a third: **a gate satisfied by the shape of the evidence rather than by its content will accept fabricated evidence of the right shape.**

**None of the eight was caught by running the suite.** They were caught by an agent reading source before building against it, by making a green test go red on purpose, and by dry-running an artefact before depositing it. Those appear to be the only three techniques that work on this class of defect, and all three are cheap.

**Phase 3 produced far more than eight, and separated them into shapes.** Three distinct tells,
each needing a different question, all now rules in `code-standards.md`:

1. **A double too simple to exhibit the property under test** — a fake transport that counted
   nothing; a client built without a TTL, so the TTL check raised before the credential check the
   test existed to exercise; a `FakeTime.sleep` with no `await`, so the lock was never contended;
   the lead's own orchestrator built with no logger, so `_log` returned before the line under test.
2. **A claim and its evidence moving together** — B's fixtures agreeing with their caller; C's
   reason-code assertion importing the constant it checked against; B reading `pending_commands()`
   after the orchestrator had emptied it; C comparing zero error rows against zero.
3. **A double standing where the subject should be** — A's Phase 2 tripwire, which passes the "can
   it fail?" question and simply is not connected to what it claims to watch.

A fourth was found by A's commissioned sweep and is the decayed assertion from the opposite
direction: **a fallback for a thing that does not exist yet has an expiry date and nothing records
it.** `try: import real / except: define our own`, `getattr(mod, "Name", None)` then skip,
`except KeyError: continue`. Each was correct when written; each was a silent branch firing on a
condition that should be impossible. A's fix formulation is the one that matters: **never delete
the fallback — add the assertion that it is unreachable**, which turns a stale workaround into a
tripwire for the day someone breaks what it stood in for.

**Two techniques were added to the three above, and both earned their place by catching the
lead.** *Break the code and watch the test go red* became a standard after the lead wrote the rule
about doubles and then committed a regression test that passed against unfixed code, in the commit
citing that rule by name. And A's caveat, which makes mutation usable rather than noisy: **a
mutation that survives a subset has not survived — it has not been asked.** Two of A's 23 survivors
died when re-run against the wider suite. A false survivor is worse than a missed one: it sends
someone to write a test for a covered case and makes the real survivors look less urgent.

**The sharpest single result was A's**, and it inverts an assumption worth naming: **coverage counts
executions, a mutation asks whether anything would object.** A's surviving mutant sat on a branch
with *excellent* line coverage — every test in `test_market_data_recorder.py` runs engine 2 without
engine 1, so that path executed constantly and nothing asserted what it reported. A line everybody
runs is the line nobody thinks to assert on.

### Known gap, recorded not hidden

`cli/engine.py` still passes `Clients()` with three `None`s, so with the engines registered **`acsoe engine` blocks every tick** — engine 1 raises, the orchestrator converts it to `ERROR`, `data_guard` follows with its own missing-key error, and the tick completes recording both. That is contract rule 7 working, and a daemon doing nothing useful. A has pinned the current behaviour in a test so wiring the real clients turns it red and forces a deliberate rewrite. Blocked on `market_data.pairs` and `market_data.book_depth`; no Phase 2 criterion depended on it, because every Phase 2 criterion runs the orchestrator against the fake client rather than through the CLI. **Carried into Phase 3 and CLOSED there by spec 39.** `acsoe engine` now builds real clients and the subscription set is derived per tick from the pairs whose quote currency the account actually holds. Neither `market_data.pairs` nor `book_depth` was ever added: the operator's ruling retired both, and the universe is engine 7's per-tick computation. A's tripwire for this — written in Phase 2 precisely so that wiring real clients would turn it red — **did not fire**, because it built the empty `Clients()` itself instead of going through `cli/engine.py`, so it pinned a fact the test supplied rather than one about the daemon. That produced a standing rule: *a test whose purpose is "this goes red when X changes" must reach X through the code path X lives on.*

## Next Up

- **Phase 3 — economics. Unblocked and not yet planned.** It opens with two things, in this order. First, **wire B's engines 10 `cost`, 11 `risk` and 17 `safety` to A's real Kraken client**: all three were built during the Phase 2 overlap against a mock and the Phase 0 seed, they did not count toward Phase 2's gate, and *built* is not *done* — the Phase 3 criteria judge them against the real client. Second, **engine 7 `scout`**, which needs a real tradable universe and was deliberately left out of the overlap because it depends on data rather than on a contract.
- **~~Engine 17's `CONDITION_ACTION` table is still unratified~~ — RATIFIED 2026-09-10.** The drawdown and loss-streak limits **freeze**; `close_all` is reserved for the invariant 14 data-outage escalation and for the operator's own button. Written into invariant 14 by spec 37, applied to the table by spec 42. B held on it for four specs and was right to.
- **The ranking score inside engine 7 `scout` is absent on purpose and is a recorded absence
  rather than a design.** Spec 44 asked for one candidate per tick and deliberately did not say
  how to choose it; ordering is alphabetical over the whole universe, which is a placeholder that
  cannot be mistaken for a judgement. No agent invented one, and B held the line on it through two
  specs. **Phase 5 closes it**, and `rank_universe` in `engines/scout/contracts.py` is the single
  named seam to edit — it exists as a separate function for that reason and for no other. Recorded
  here at B's request because spec 44 step 3 asks for it and the tracker is the lead's file.

  The blind spot found while proving it is worth carrying with it: the engine builds its scan set
  as `sorted(set(rules) | set(quotes))`, so `rank_universe` is always handed an already-ordered
  sequence, and a ranking that merely preserved arrival order still answers alphabetically end to
  end. Whoever replaces the placeholder must test `rank_universe` **directly** on input where
  arrival order and the intended order disagree on every element; an end-to-end fixture cannot see
  the difference.

- **~~`cli/engine.py` and its three `None` clients, blocked on `market_data.pairs` and `market_data.book_depth`~~ — RULED 2026-09-10, and the answer is that neither key exists.** They stay undefaulted. The subscription set is derived per tick from the pairs whose quote currency the account actually holds, in engine 2, from `state["exchange"]`; the tradable universe is engine 7's and is a different question. `acsoe engine` does **not** refuse to start without credentials — paper mode is the default and must run on a fresh clone, and the gates block on their own. Spec 39.
- **~~Phase 2 carries a debt from Phase 1~~ — PAID, 2026-09-10.** The status band gained its `Running` and `Frozen` readings in Phase 2 as required. B added the column (spec 31), the lead wrote the run record and the mode write in `core/`, and C's reader takes the mode as a fact rather than inferring it (spec 32). `console_reads_persisted_mode` PASSes against a real daemon driving a real store. Kept here struck through rather than deleted, because a debt that is quietly removed from a list is indistinguishable from one that was never recorded.
- **Before Phase 4:** replace the cycle feed's full scan of `block_records` with a most-recent-N read on B's store surface. Harmless while the table holds a seed; engine 19 `memory` starts writing a row per guard per tick in Phase 4, which is when it stops being harmless.
- **`RUF001` on `tests/console/test_format.py` is suppressed deliberately, not fixed.** `U2212 = "−"` must be the U+2212 glyph: it is the fixture for the minus-sign rule, and "correcting" it to an ASCII hyphen would make the test pass against the exact character it exists to reject. Carries a rule-named `noqa` with its reason, and the general policy now lives in `context/code-standards.md` under Python — name the rule, give the reason, and never suppress a lint to make a failing check pass.
- **The console's scan tally is DEFERRED, and spec 57 step 3 was wrong to promise it.** Ruled
  by the lead 2026-09-11. The Phase 3 handoff said the empty state's tally *needs engine 19,
  which is Phase 4*, and I wrote that into spec 57 as though engine 19 arriving were
  sufficient. It is not. Engine 7 `scout` publishes `scanned`, `entered` and a per-reason
  `excluded` tally into `state["scout"]`, where they live for exactly one tick; **no column in
  any table has room for any of the three**, and engine 19 can only write what the schema
  holds. C stopped and asked rather than inventing, which is the correct move and the reason
  this is a deferral rather than a defect.
  The three options C set out, with what each costs:
  1. `rejections.details` as JSON, one row per tick — no schema change, but it puts a
     tick-level fact in a candidate-level table, and **anyone counting refused trades counts
     it**. That is invariant 12's table meaning something different depending on who reads it.
  2. One `rejections` row per excluded pair — defensible, since engine 7 is a gate and an
     excluded pair is a refused candidate, and Phase 3 already mapped all six per-exclusion
     codes into `REASON_PROSE`, which only makes sense if they reach that table. But it
     reconstructs `scanned` and **not** `entered`, and writes tens of rows per tick.
  3. A new column or a small table — lead approval, B's edit.
  **Deferred because option 2 changes what `rejections` means**, and that is invariant 12
  territory rather than a console nicety. Deferring is reversible; a table whose rows mean two
  things is not. Revisit when there is a reason to decide about tick-level telemetry in
  general — Phase 7's attribution is the natural forcing function, since it reads the equity
  curve including cash periods and will want to know what the system was doing while flat.
  What C **did** fix, because it was in scope and simply false: the empty state said the
  universe filter was engine 4 and its counts arrived in Phase 2. It is engine 7 and it
  shipped in Phase 3, so the console was telling an operator to wait for something already
  built. The stage still shows no count and still refuses to show a zero, because a zero there
  reads as *no pair qualified*, which is a result, when the truth is that nobody counted.
- **The branch-coverage backlog lives in one place and that place is not this file.** Phase 3
  recorded it inside the handoff box at the top of `feature-specs/PHASE-3-TASKS.md` and
  nowhere else. B went looking for it in `docs/build-log/phase-3.md`, the per-agent logs and
  this tracker — the three places a careful agent searches — and correctly reported it absent.
  It is not absent; it is in a fourth location that neither canonical file mirrors, because a
  handoff box is written at phase close and is neither a merged progress file nor a
  consolidated build log. **An open item recorded only in a handoff box is an open item the
  next phase will lose**, and this is the first time one nearly was. Carried here now:
  `clients/kraken/contracts.py::_to_money` (4), `limiter.py::acquire` (the `cost <= 0` guard),
  `engines/market_data_recorder/contracts.py::validate_line` (1), `platform/config.py` (5), and
  `clients/store/migrations.py::discover_migrations`. That last count was recorded as 3 and B
  re-checked it wide in Phase 4: it is **five** refusal branches, all raising `MigrationError`,
  plus a sixth path for the non-`.sql` skip. The handoff's own warning that the counts came
  from a narrow subset and that some would die on contact was right in both directions — some
  die, and at least one was undercounted.
- **~~Deferred from Phase 0, still deferred: widening `TOOLCHAIN` beyond `src/`~~ — DONE
  2026-09-11, by operator ruling.** `TOOLCHAIN` is now `pytest tests/`, `mypy --strict src/
  scripts/`, `ruff check src/ tests/ scripts/`. It was ruled because the deferral finally cost
  something: a file committed this phase could not be imported on Python 3.11, the declared
  floor, and a second defect in `scripts/build_archive.py` that presented as a typing
  complaint turned out to be a crash. Both sat in files the gate could not see.

  **Two things this entry said were wrong, and the staleness is the lesson.** It recorded
  `mypy --strict scripts/` as 2 errors — it was 7 — and `ruff check tests/` as 3 violations,
  when it is **clean**: the `RUF001` `noqa` had already landed with its reason. So a
  deferred-decision note had been quietly overstating the cost of the decision for four
  phases, which is part of why it kept being deferred. **A stale obstacle in a deferred item
  is its own hazard**: nobody re-measures a cost they have already accepted, and the note
  outlives the thing it describes. Re-measure before re-deferring.

  One measurement note worth keeping, from C: `mypy --strict scripts/` alone reports the
  `build_archive` error and `mypy --strict src/ scripts/` does not, because the argument list
  changes how the `acsoe` imports resolve. **An error count is only true for the exact command
  that produced it.**

  `mypy --strict` is deliberately **not** widened to `tests/` — roughly 1,680 test functions
  would each need a return annotation. The hole is stated rather than implied and a test
  asserts the exclusion, so the next person to "fix" it meets a red and a decision.
- **A's standing instruction, and it does not expire with the phase:** `scripts/record.py` should be left running from now on. Order-book and spread history cannot be recovered retroactively — Kraken's free archives carry OHLCV and no bid, ask, spread or depth — so every hour the recorder is not running is an hour of cost-model input that money cannot buy back later. Phase 2's criterion is satisfied, which is exactly when the temptation to switch it off appears; engine 9 `order_book` and the spread half of engine 10 `cost` still have nothing else to read. **Note the recorder has no working graceful shutdown on Windows** — `loop.add_signal_handler` raises on the Proactor loop and the exception is suppressed, so the `stop` marker never runs and a kill has to be forced. The archive is append-only and every line is flushed, so a kill costs at most a partial final line.

## Findings — Phase 5

*The three results an examiner should read first. Each is recorded here, and not only in the
build log, because a finding that lives in a build log is a finding the next phase will not
read. All three are measured over the 405 fitted folds of the full-archive run.*

### FINDING 1: the predictor's BUY calls show no selection skill on their own; the skeptic's veto does

> **CAVEAT ADDED 2026-09-16, and it applies to every number in this finding that involves the
> skeptic.** The 0.531 survivor target rate, the no-skill band, the +0.058 over `p_target` and the
> 44% overlap were all measured on the **uncapped** skeptic — the one that trains on every eligible
> BUY call from every earlier fold. The operator ruled on 2026-09-16 that the skeptic's training
> set caps to a rolling window of the last 13 folds (Phase 7 prerequisite 1), so that model will
> not exist once the cap lands. **Every one of these numbers must be re-measured on the capped
> skeptic before it is cited anywhere, including in the dissertation.** Re-measuring means
> retraining 405 skeptics, which is Phase 7's full run, and it is deliberately not done in Phase 6.
> Recorded as a correction beside the finding rather than an edit to it (`script-rules.md` rule 6).
> The shape is one this project keeps catching: **a finding measured on code that no longer exists
> is a claim, not a measurement.**

**The BUY rule selects nothing.** Across folds 1 to 404, **8,948,485 out-of-sample BUY calls**
hit the target at **0.2383**, against **0.2422** over all test rows — *below* the base rate, and
before any fee is paid. `expected_move_pct > 0` fires on 56% of bars, so the rule is close to
taking everything. Whatever the predictor knows, the BUY rule as defined does not extract it.

**The skeptic's veto does select.** At `skeptic.veto_threshold: 0.50` the surviving 154,979
calls (1.73%, effective sample size 46,616) hit the target at **0.5309**, against a **no-skill
band of 0.255 to 0.260** — each fold's own scores permuted across its calls over 20 seeds, which
is the fair comparator rather than the 0.2383 base, because folds differ in how many calls
survive and in their own target rates. The lift holds in every test year from 2017 to 2024, and
at 0.50, 0.60 and 0.70.

**It was treated as a leak until shown otherwise**, because a jump from 0.24 to 0.53 is exactly
the shape this phase exists to distrust. Three checks: the skeptic's training identity was
recomputed from the out-of-sample file for seven folds and matched each manifest with zero rows
reaching the scored window (dropping the purge and embargo breaks every match); adjacent folds'
skeptics differ in one verdict and distant ones in hundreds, which is the right direction; and
fold 200's calls scored by fold 350's skeptic — which *did* train on them — reach 0.6325 against
0.5772, so contamination shows up when it is present.

**And it is not just the predictor's own confidence.** Ranking by calibrated `p_target` at
matched survivor counts gives **+0.058 to the skeptic** at 0.50, with the two sets sharing only
**44%** of their calls. The margin narrows as the threshold loosens (+0.0049 at 0.70, 68%
overlap), so the second stage earns its place at the strict end and not at the loose one. Note
also that `p_target` ranking alone reaches 0.47 at that count: the predictor carries real
ordering that the BUY rule never uses.

**What this is not.** Every rate here is **before friction**, and friction is the thing this
system exists to beat — at tier 1 it is ~1.25% round trip against a 3% target. **The chain has
not run end to end.** Engine 9 does not exist, so engine 10 blocks every candidate and engine 15
is unreachable in the live chain; these numbers come from applying each fold's trained skeptic
to that fold's out-of-sample calls offline. **This is evidence about one gate, not about the
system.** The standard errors are a floor: they ignore correlation between pairs moving together
and between overlapping folds. Phase 6 is what turns it into evidence about the system.
Scripts and tables: `docs/dataset/skeptic-veto-sweep-2026-09-14.{py,json,md}` and
`skeptic-vs-ptarget-2026-09-14.{py,json,md}`.

### FINDING 2: the DI as first ruled measured time elapsed, not distributional distance

**78 of the DI's 117 columns are the BTC and ETH macro features**, which are identical for every
pair on the same bar, and the calendar columns are shared too. So a reference row's ten nearest
neighbours were **other pairs at the same moment**, and a leave-one-out that removed only the row
being scored left every one of them in the reference set. The threshold was therefore a measure
of *how close in time* a row sits to the reference window, not of how unfamiliar the market is.

**The consequence was extreme and would have been read as a working gate.** At the 0.95
percentile the DI refused **94.7%** of complete out-of-sample rows; 74.9% at 0.99; 31.1% at
0.999. A live candidate sits at least the 48-bar embargo after the reference window and has no
contemporaneous neighbours in it, so it lands above almost the whole distribution *whatever the
market is doing* — a refusal rate that looks like a cautious gate and is actually a clock.

**The wrong explanation was tested first and rejected**, which is why the right one is trusted:
excluding the same pair's rows within ±48 bars or ±7 days left the distribution unchanged
(median 0.632 in all three arms). Excluding **every pair's** rows within ±48 bars moved the
reference distribution onto the out-of-sample one (median 1.423 against 1.402).

**Fixed by operator ruling 2026-09-15**, amending ruling 6 of 2026-09-12: the leave-one-out
excludes every reference row within `backtest.embargo_bars` of the row being scored, **across all
pairs**. Refitted over all 405 folds, the same percentiles now refuse **6.79% (0.95), 3.31%
(0.99), 2.06% (0.999)**, and the refused rows carry a higher target and stop rate than the kept
ones — the volatile tail, which is what an out-of-distribution refusal should catch. The
exclusion was chosen over dropping the macro columns, which would blind the DI to the conditions
it exists to detect. `di_leave_one_out_excludes_48_bars` proves it is applied, and
`modelling.di.load` refuses an artefact fitted without it.

### FINDING 3: half of every test week carries an incomplete feature vector, and no threshold can help

**8,025,361 of 15,978,803 out-of-sample rows — 50.2% — carry an unfilled 48- or 96-bar
lookback**, because the pair did not trade in every bar of the window. It is not uniform and it
is getting worse as the universe widens: 26% of rows in 2017, **61% in 2023**.

**Engines 8 and 13 refuse an incomplete vector at any threshold**, and correctly: a NaN compared
against a threshold is False, so scoring one would silently mean "not dissimilar". This is not a
percentile question and no choice of `di_percentile` or `threshold_percentile` touches it.

**It bounds everything downstream of engine 8.** Half the candidate bars never reach a
prediction, and the half that do are systematically the more liquid ones — which is also where
the spread the archive cannot price is smallest, so the surviving population is not a random
sample of the universe. Any Phase 7 statement about coverage, capacity or opportunity count has
to carry this number. Recorded as Phase 7 prerequisite 6 by operator ruling 2026-09-15.
`docs/dataset/di-anomaly-distributions-2026-09-14.md`.

## Findings — Phase 6

### FINDING: engine 12's two reason codes have rendered as silence since Phase 5

Found 2026-09-16 by the spec 99 walking test, on its **first run**, before it had judged a single
Phase 6 engine. `engines/regime/contracts.py` declares `REASON_NO_FEATURE_ROW = 'no_feature_row'`
and `REASON_NO_INPUTS = 'regime_inputs_incomplete'`; neither was in `console/format.py`'s
`REASON_PROSE`. Engine 12 writes the bare code into `reason` and publishes no `reason_code`, so
`operator_reason` recognises the stored text as code-like, refuses to print it, looks up an empty
string, and the operator reads **"No reason was recorded."** on the field whose only job is to say
why the market could not be classified. Live since Phase 5, with every gate green throughout.

**The seam row named the gates; the hazard never cared.** `ownership.md`'s reason-code row was
written for "every gate", and this is a non-gate from a phase nobody was auditing — which is why
the walking test was specified to walk **every** engine's contracts rather than a maintained list.
It is also why `no_fx_rate` had been mapped but unlisted since Phase 3, found the same day from
the other direction.

**It was about to matter more, not less.** Engine 14 `adaptive_router` reads
`state["regime"]["label"]` under spec 97, so the `null`-label tick — the one these two codes
explain — is the tick the router will have to account for.

All four unmapped codes (these two plus engine 21's `data_guard_blocked` and
`position_unrecordable`) now have prose. `data_guard_blocked` is the first **hold** reason in the
map and is deliberately not worded as a refusal: nothing was rejected, exits are paused, and the
position is still being watched.

### FINDING: a test went green while asserting nothing, because it called the helper that supplied the value

**The clearest example this phase of a test passing for the wrong reason.** Recorded as a finding
on the operator's instruction of 2026-09-18, not as a smaller item.

When the lead removed `EquitySnapshotRow.cash_source`'s default (`98c0485`), the field became
required, and every site that built a row without it had to pass it. One of those sites was
`make_equity` in `tests/clients/store/test_store.py`, the shared helper that builds equity rows for
the store's tests. It gained `cash_source=CashSource.CYCLE_START`. B's existing test,
`test_a_row_built_without_a_cash_source_says_cycle_start`, built its row **through that same
helper** and asserted the row said `cycle_start`. After the change it **still passed**. It passed
because the helper now supplied the very value it asserted, not because anything defaulted.
It was asserting nothing.

**The operator's condition is what caught it.** The removal was ruled "landing with a test that a
row lacking a source is refused — otherwise the change deletes a check instead of tightening one."
Writing that replacement (`test_a_row_built_without_a_cash_source_is_refused`, which builds the
row from a field map with the key omitted) is what forced the question of what the old test had
been measuring. The replacement was proven red by restoring the default from a byte copy: only it
failed, and `contracts.py`'s sha256 was identical after the restore.

**Why it is a finding and not a slip.** The same shape recurs across this project: a value under
test supplied by the test's own machinery. Phase 6 has now seen it through a fixture value, a
model's own default (`PositionRow.hold_reason`), a criterion that pins the mark it then measures,
and here a shared helper. None of these is visible by reading the test: each assertion is true.
**What catches it is asking where the asserted value came from**, and here the answer moved while
the test text did not change at all.

### FINDING: `outside_universe` never had a producer, because a spec said the key already existed and nothing checked

**The same shape as the finding above, one level up**: not a test supplying its own value, but a
specification supplying its own premise. Recorded as a finding on the operator's instruction of
2026-09-18.

`feature-specs/44-engine-7-scout-candidate-and-gate.md` step 7 (2026-09-10) told B: *"`outside_universe`
already exists in C's `REASON_PROSE`"*. That was true of the map. But it was written as though it
settled what engine 7 would emit, and nobody made it a check. B built engine 7 with twelve specific
exclusion codes and never emitted the generic one. So from Phase 3 until spec 120 (C, `2beb8ba`,
2026-09-18), the console carried operator prose for a refusal **no engine could produce**, and the
forward walk (spec 99: every engine code has prose) could not see it, because it walks engines
into the map and never the map back to engines.

C found it deriving the orphan set **from the code rather than from the list it had been given**.
B's spec 119 list of bad seed pairs had been one short, and this was the missing one. Nothing is
lost: the twelve specific codes say which exclusion applied. **What was lost is the check**. A
spec's statement that a key exists was treated as an interface, and nothing held the producer to
it. Both directions of the walk are now assertions (spec 120), so the next key with no producer
goes red.

**The general form**, since it has now appeared twice in one day: a claim a document makes about
the code, whether a helper's value or a spec's key, is a description rather than evidence. It stays
true only while something re-checks it (`code-standards.md`, "a description of the code is not the
code").

### FINDING: a criterion described itself as checking against Kraken with a fetched tolerance; it checked a local reduction with an invented one

Recorded as a finding, not a note, by operator ruling S2 of 2026-09-18. **Both claims were false
from the day the criterion was written, and it took six phases and an unrelated question to
surface them.**

Phase 2's `candles_match_kraken_ohlc`. Its docstring said the tolerance was *"fetched, never
hardcoded"*, *"an exchange value the system fetches"*, and its messages compared built candles
*"vs Kraken"* and against *"Kraken's own OHLC"*. In fact:

- the expected bars are a pure-Python reduction of recorded trades (`scripts/ohlc_fixture.py`),
  not Kraken's published figures — the fixture's own `provenance` said so, and A's spec 28
  decision entry said so, and stated the limitation "in three places so nobody mistakes a PASS
  for more than it is". **The criterion's own message was never one of the three.**
- the tolerance is `tick_size` read through the fake client out of `asset_pairs.json`, which is
  **invented Phase 0 test data** that the fake's docstring promised would be replaced by
  recordings in Phase 2, and never was.

**The verdict was sound all along.** Measured: all 9 bars agree with the builder to the digit,
so the tolerance was never engaged and the PASS holds at any non-negative tolerance. What was
untrue was what the criterion said it had checked.

**No test could have caught it**, because the tests asserted that the word `tick_size` appeared
in the message rather than that the message was true. Measured on the correction: mutation M1
restores the original sentence verbatim, and **all 52 pre-existing tests in that file pass
against it**; only the test added with the correction goes red.

**The same shape as rule 4** (`ui-context.md`): a claim true only by the accident of what it
happened to be pointed at. It recurred the same evening in two more places, both corrected
under ruling S3: every trade criterion's message quoting invariant 5's reference friction for a
run at the fake's rates, and `fee_tiers.json`'s own comment. A third, spec 118's criterion,
compared a real recording against the same invented declaration and called it recorded; it was
removed rather than corrected (FINDING below). **So one criterion, this one, still compares
real recordings against invented data, and it now says so.** **A message is a claim
about evidence, and it needs a test that it is true, not a test that it is present.**

**And the name made the same claim, which is worse** (operator ruling of the same evening). A
criterion's name appears in every gate output, so it is read more often than any message and
questioned less. `candles_match_kraken_ohlc` claimed Kraken's OHLC as plainly as the prose did, on
every line of every Phase 2 gate for six phases. **Renamed
`candles_match_independent_reduction_of_recorded_trades`** in the registry, its tests, the market
sensor README, `scripts/ohlc_fixture.py`'s docstring and the fixture's provenance. Gate logs and
build logs written before 2026-09-18 keep the old name, as history.

**And the phase rule above it said the same thing** (operator ruling of the same evening, which
amended it). The Phase 2 row of `ai-workflow-rules.md` asked for candles to *"match a committed
Kraken OHLC fixture … within one `tick_size` for that pair as reported by `AssetPairs`"*. A's spec
28 decision had established at the time that neither half was available. A said so, and nothing
carried it up to the rule. **That is not a criterion misdescribing itself; it is the rule
misdescribing what any criterion could do**, and every green Phase 2 since was read against it.
**The chain, then: the criterion's name, its message, its docstring and the phase rule above it
all claimed the same thing, and none of them was true. Four layers, one false claim, six
phases.** The row now says what is achievable and true, and states that the earlier wording was
never met. **Phase 2's green stands** (operator, the same evening): it was awarded on the criterion
actually passing, and the criterion checked the local reduction, so the amendment makes the
record match what was proven. It is not a re-examination of Phase 2, and nothing about that
phase reopens.

### FINDING: a criterion was approved, built, passed and counted before anyone asked what its PASS demonstrated

Recorded by operator ruling of 2026-09-18 evening, which removed the criterion. **This matters
more than the removal.**

`recorded_book_agrees_with_recorded_pair_decimals` (spec 118) checked that every price in the
recorded book `tests/fixtures/book_sample.jsonl` sat on the `pair_decimals` grid declared for its
pair in `tests/fixtures/kraken/asset_pairs.json`. **It was offered by C**, out of spec 101's mark
measurement, and **approved by the operator**. It was built with care:
- coverage stated rather than implied (1 pair of 5, each uncompared pair named with its reason);
- five FAIL arms and a control (`75733.6` to `75733.60`, same grid point, still PASS);
- a test proving it read two files and nothing else;
- the rule that no precision is ever inferred from a price.

It passed, was mutation-swept and was counted as the 14th Phase 6 criterion.

**It rested on two premises, and both were false.**
1. *"Both sides are recordings frozen together."* `asset_pairs.json` is invented Phase 0 test data
   and was never cut from any archive. This survived a day: C found the dates did not match while
   building it, and the lead found the file was never a recording while answering Q2.
2. *"Every other criterion that reads those fixtures rests on their agreement."* The only other
   reader of both, `order_book_slippage_on_recorded_book`, never reads `pair_decimals`; nor do
   engines 9 and 10. This survived until a question that was not even about it: the operator
   asking what a PASS demonstrated once the first premise had gone.

**So a PASS demonstrated nothing anything relied on, and nothing about Kraken.** Its verdict turned
on a typed threshold: had someone typed `8` instead of `1`, any recording would have passed.

**Removed, not made PENDING.** It was not in the Phase 6 row of `ai-workflow-rules.md`, so the
phase's definition of done is unchanged. Nothing depended on it: every helper was its own, and its
commit `97927d9` added nothing another criterion uses. Q3, which existed only to widen it, is
withdrawn. The genuine `AssetPairs` recording is re-scoped to Phase 7 item 9. The history (spec
118, C's progress file, the build logs) stays as written, because what happened is the finding.

**The offer was C's and the approval was the operator's, and neither asked the question until the
criterion was green.** Nor did the lead, who scheduled it, gated it and counted it.

**The rule** (now in `code-standards.md`, Verification): **before a criterion is written, state what
a PASS will demonstrate and what would have to be true for that to hold. If the answer depends on a
number nobody has verified, verifying that number is the work — not the check.**

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
- DI fitted on the predictor's training set, MinMax-scaled, rolling percentile threshold, 30-day per-pair window; its leave-one-out excludes every row within 48 bars across all pairs (operator, 2026-09-15).
- DI threshold crossings also feed the regime engine.
- Alpha attribution uses the full equity curve including cash periods, not trade windows.
- Execution offset bandit pooled by spread tier, not per pair.
- Promotion metric haircut for the number of models tried.
- Backtest training window is the 90 days **before** each test window and nothing after it — past-only, never two-sided; retrains weekly during walk-forward. Operator ruling 2026-09-12; the earlier wording *capped at a rolling 90 days* was read as two-sided and is retired.
- Decision bars before `dataset.decision_start_date` (2017-01-01) are excluded from the labelled dataset. A tradability exclusion, not a data-quality one: the 2013–2016 bars are real but describe a market no position could have been taken in. Operator ruling 2026-09-12.
- Every pair that clears the archive's two-year rule is in the dataset, thin ones included. `dataset.min_labelled_rows` is the per-pair floor, 0 today (no floor); a cross-sectional model may want one, and the decision is deferred behind that named knob. Operator ruling 2026-09-12.
- An LLM is not the predictor. Any alternative method must first clear the fee hurdle.
- Build order is structure, then interface, then backend.
- Console is built against the real schema with seeded fake data, so no rework when real data arrives.
- Paper mode until a validated model exists. A readiness gate, not an account-size gate.

### Lead rulings of 2026-09-12 for Phase 5, each confirmed by the operator the same day and overturnable by the operator only

- **Engine 20 `tournament` is Phase 5 work.** Its leaderboard is what engine 14 reads in Phase 6.
- **`src/acsoe/modelling/` is the one package both the live loop and `research/` import**, C-owned, so live and replay compute from one implementation. Invariant 5 in `architecture-context.md` says so.
- **Engine 8 `prediction` blocks on a DI refusal** under contract rule 6, reason code `di_refused`, publishing no `expected_move_pct`, and stays a non-gate in the registry. The alternative put the veto after cost and risk had already run on a distrusted prediction.
- **The evaluation number is the Brier of P(target) against the fold's base-rate Brier**, with log loss beside it and the BUY-call target rate against the break-even rates in invariant 5.
  Accuracy is never computed: the base rate is 23.89% and a model that always predicts `stop` is right 51% of the time. Retired as a term in `ai-workflow-rules.md`.
- **Rows are weighted by average uniqueness**, and the effective sample size is reported **per fold on the same line as that fold's row count** and in aggregate. Operator addition: a fold with 8,000 rows and an effective size of 300 is a fold whose numbers mean almost nothing, and an aggregate hides exactly that fold.
- **The DI reference set** is the predictor's training rows for the fold, per pair the last `prediction.di_window_days`, mean k-nearest distance, thresholded at `prediction.di_percentile` of the leave-one-out distribution, refitted each weekly retrain. **Amended by the operator 2026-09-15: the leave-one-out excludes every reference row within 48 bars (`backtest.embargo_bars`) of the row being scored, across all pairs, not the row alone** — 78 of the 117 DI columns are shared by every pair on a bar, so excluding the row alone left near-identical same-moment neighbours and the threshold measured time proximity rather than distributional distance. Spec 68, amendment.
- **Engine 7's ranking is a config-named feature**, `scout.rank_feature` with `scout.rank_descending`; alphabetical while absent, and the engine says so. The feature is ruled after spec 75's study reports. **Ruled 2026-09-19 (R1): engine 8's expected move, not a studied feature.** Spec 75 is resolved; see Open Questions, and spec 144.
- **`lightgbm`, `scikit-learn` and `shap` are base dependencies** from Phase 5; `hmmlearn` and `statsmodels` stay in the `research` extra.

### Operator rulings of 2026-09-12, recorded here so Phase 5 inherits them rather than asking

Context: the same day, the historical loader was pointed at the whole archive instead of
three hand-picked pairs — 234 USD-quoted pairs with at least two years of history,
20,443,861 bars — and the labelled dataset was measured over all of it. The measurement
surfaced three things the operator ruled on.

**RULING 1 — The walk-forward is past-only, not two-sided.** A fold trains on the 90 days
before its test window and nothing after it. What was built trained on 90 days on both sides
of the test window, which is purged cross-validation: legitimate for hyperparameter selection,
but it lets a model see data from after the period it is scored on, so it reports a number
better than the same model would achieve live and nothing says so. The project's goal is a
system that trades, so the validation must answer "would this have worked if I had been
trading it". **Applied:** `research/walkforward.py` now sets `train_end = test_start` and
counts every row after the test window in `Fold.after_test_count` rather than training on it;
the embargo moved to the training side of the boundary (the last `embargo_bars` before the test
window). The Locked Decision above was reworded, and the retired wording is now a
`docs_vocabulary` row. A new Phase 4 criterion, `walkforward_trains_on_the_past_only`, proves
on every rolling fold that no training row's decision bar or label window end post-dates its
test window, with mutation proofs in `tests/verify/test_phase4_criteria.py`. Measured effect on
the three original pairs: median training rows fell from ~17,175 to
~8,586, which is the ruling doing what it says.

**RULING 2 — Exclude decision bars before 2017-01-01.** The archive begins 2013-10-07 and the
earliest bars are single trades of 0.1 BTC in fifteen minutes. Those bars are real but describe
a market no position could have been taken in at any size, and a model trained on them will
learn patterns that do not transfer. **The exclusion is about tradability, not data quality.**
**Applied:** `dataset.decision_start_date: "2017-01-01"` in `config/default.yaml`, read by
`research/labelling.py` with no default (a null raises), applied in `label_series`, and
reported per pair as `LabelledSeries.excluded_before_start` and by engine 23 as
`excluded_before_start_by_pair`. **Cost, measured:** 92,791 labelled rows
removed (0.45% of 20,424,028), across the 6 pairs whose history
predates 2017 — XBTUSD 46,671, ETHUSD 25,973,
LTCUSD 10,411, ETCUSD 7,221, ZECUSD 2,724,
REPUSD 475. The dataset is 20,331,237 rows. Both figures are in
`docs/PROJECT-STATE.md` section 10 and `docs/dataset/`.

**RULING 3 — Keep the eleven thin pairs; add the floor as a named knob.** Eleven of 234 pairs
carry fewer than 20,000 labelled rows (TUSDUSD 4,659 and ETHPYUSD 4,812 the
smallest). They stay. `dataset.min_labelled_rows` is the per-pair floor, reads `0` today so
nothing is excluded, and engine 23 names any pair it leaves out in `pairs_below_floor`. A
cross-sectional model may want a floor; that decision is deferred with a named knob, not
overlooked. **One deviation from the ruling's letter, stated:** the operator asked for a
default of null. `platform/config.py` refuses every null key at load — null means OPERATOR
REQUIRED and stops the process, which is the right rule for a trading threshold and is
documented as deliberately not special-cased — so the absence of a floor is spelled `0`, with
the reason in the YAML comment and in `DatasetConfig`.

## Open Questions

- **~~OPEN for the operator, Phase 5, deliberately: three values are absent until the walk-forward reports.~~ ALL THREE ARE NOW RULED AND LANDED, 2026-09-15, and all three are PROVISIONAL.** `prediction.di_percentile: 0.99`, `anomaly.threshold_percentile: 0.99` and `skeptic.veto_threshold: 0.50` are in `config/default.yaml`, each with its evidence in the comment beside it and each revisited once the chain runs end to end. The operator ruled 2026-09-12 that the lead's recommendations (0.95, 0.99, 0.5) were guesses until there was a distribution to place them on; each of the three was then chosen from that distribution, and the DI's only after the 48-bar exclusion had been applied and refitted. Engines 8, 13 and 15 no longer fail closed on an absent threshold — they fail closed on an absent `models.*_run_id`, which is what a fresh clone has. The fourth key, `scout.rank_feature`, stays absent: the operator ruled no feature 2026-09-15 and the question moves to Phase 7.

  **RULED 2026-09-15 by the operator: `prediction.di_percentile: 0.99`, provisional until the
  chain runs end to end.** With the 48-bar exclusion the DI refuses **3.31%** of complete
  out-of-sample rows against 1% nominal, over the 405 fitted folds — roughly three times its
  nominal rate, which is the right direction for an out-of-distribution refusal and nothing
  like the **74.9%** the same percentile refused before the exclusion. **0.95 rejected: 6.79%**,
  too much for a gate meant to catch genuinely unfamiliar conditions. 0.999 refuses 2.06% and
  was not chosen. Evidence: `docs/dataset/di-exclusion-refit-2026-09-15.py` and `.json`.
  This is the ruling the entry below (ruling 1 of 2026-09-15) left open, and it closes it.

  **RULED 2026-09-14 by the operator: `skeptic.veto_threshold: 0.50`, chosen from the veto sweep
  and provisional until the chain runs end to end.** Evidence: at 0.50 the skeptic's survivors hit
  the target at 0.531 against 0.473 for the same number of the predictor's most confident calls
  (top N by `p_target`, per fold), the two sets share only 44% of calls, and the survivors beat the
  vetoed calls in every test year 2017 to 2024. Stricter thresholds give bigger margins on too few
  effective outcomes; looser ones decay toward the predictor's own confidence (+0.005 at 0.70, 68%
  overlap). `docs/dataset/skeptic-veto-sweep-2026-09-14.md`, `skeptic-vs-ptarget-2026-09-14.md`.
  Lands in `config/default.yaml` with the other ruled values under spec 77, not before.

  **REPORTED 2026-09-15, awaiting the operator: the DI and anomaly distributions and the ranking
  study.** `docs/dataset/di-anomaly-distributions-2026-09-14.md` (all 405 folds fitted from their
  identity-verified training rows, nothing retrained) and `docs/dataset/ranking-study-2026-09-14.md`.
  Three findings the ruling cannot avoid: **(1)** the anomaly gate's out-of-sample block rate
  matches its nominal percentile (5.55% at 0.95, 1.24% at 0.99) and what it blocks is the volatile
  tail; **(2)** the DI as ruled (operator ruling 6 of 2026-09-12, leave-one-out) refuses 94.7% of
  complete out-of-sample rows at 0.95, 74.9% at 0.99 and 31.1% at 0.999, refusing no worse rows,
  because 78 of its 117 columns are macro features shared by every pair on a bar, so its nearest
  neighbours are other pairs at the same moment; excluding every pair's rows within 48 bars from
  the leave-one-out moves the reference distribution onto the test distribution on every fold
  tested. That is a question about ruling 6, not about a percentile. **(3)** 50% of test rows
  carry an incomplete vector (the 48- and 96-bar lookbacks on pairs that do not trade every bar),
  refused by engines 8 and 13 at any percentile.

  **RULED 2026-09-15 by the operator, three rulings on that report:**
  1. **The DI's leave-one-out excludes every reference row within 48 bars of the row being
     scored, across all pairs** — ruling 6 of 2026-09-12 amended (Locked Decisions below, spec 68
     amendment). The exclusion rather than dropping the macro columns, which would blind the DI
     to the conditions it exists to detect, and rather than rebuilding the reference set, which
     is a larger change with no evidence behind it. A DI fitted without the exclusion is a
     defect, and the criterion `di_leave_one_out_excludes_48_bars` proves it is applied.
     ~~**`prediction.di_percentile` stays absent** and engine 8 stays fail-closed until the
     operator rules on the refit's refusal rates at 0.95, 0.99 and 0.999
     (`docs/dataset/di-exclusion-refit-2026-09-15.py`, running).~~ **The refit finished and
     the operator ruled 0.99 on 2026-09-15** — 3.31% refused against 1% nominal, 0.95's 6.79%
     rejected. The value is in `config/default.yaml` and is provisional until the chain runs
     end to end; the entry above carries the reasoning.
  2. **`anomaly.threshold_percentile: 0.99`, provisional.** 1.24% blocked against 1% nominal,
     stable across years (0.9% to 1.8%), and what it blocks is the volatile tail (stop rate 0.67
     against 0.50). 0.95 was rejected: 5.55% blocked, including BUY calls with better
     pre-friction returns than the ones kept, which is too much for a data-quality gate. **The
     spec 70 ten-sigma question stays open** (entry below): a ten-sigma volume spike scores at
     the 0.904 quantile of training scores and 0.99 does not block it.
  3. **`scout.rank_feature`: none. Engine 7 stays alphabetical.** Recorded as an open question,
     not a finding: next entry.
- **RULED by the lead 2026-09-15, flagged to the operator as overturnable: `pytest` gets
  its own subprocess bound in `toolchain_green`, `PYTEST_TIMEOUT_S = 2700`; `mypy` and
  `ruff` keep 900 s.** With the three thresholds landed and the suite green,
  `--phase 0` reported `FAIL toolchain_green - pytest timed out after 900s` and every
  other criterion PASS. Because `toolchain_green` is registered for every phase, that is
  six red gates on a tree with nothing wrong in it.

  **The bound was already marginal before this session**, and the gate's own evidence
  directory says so: `logs/verify/toolchain_green/` holds a **820.9 s** completed run at
  07:06Z on 2026-09-15 against the 900 s bound, and a **timeout** at 04:10Z on the same
  tree, at 74%. 900 s was chosen in Phase 0 when the suite was a minute long and is now
  2,506 tests. **`prediction.di_percentile: 0.99` then took it over**: the trainer fits and
  scores a DI only when a percentile exists, so every trained fold in the suite now pays
  **3.1 s** for one (A/B over `test_training_main.py`: 126.9 s against 228.1 s; cProfile of
  one two-fold run: `di.fit` 1.1 s and the per-row `di.score` loop 1.5 s a fold, at 1.13 ms
  a row). The suite is **1502 s**.

  A timeout guards against a tool that has **hung**, not one that is slow, and this makes
  no criterion easier to satisfy - pytest still has to exit 0 with every test passing. The
  two alternatives were measured and neither removes the need to move the bound: Phase 7
  prerequisite 5 recovers at most the DI's own 5.4 s of a 10.1 s two-fold run and leaves the
  suite near 1000 s; stopping the non-DI tests inheriting the percentile lands near 850 s,
  which is the margin that already failed at 04:10Z, and pays for it by giving up the
  property that tests run against the shipped config. Account:
  `docs/build-log/phase-5/lead.md`.

  **Phase 7 prerequisite 5 now has a second and nearer-term reason**: the DI's fitting and
  scoring path is the test suite's largest single cost, not only the full run's.

- **OPEN, recorded 2026-09-15 and deliberately not fixed this session: `toolchain_green`
  cannot tell a collection error from a verdict.** It retries a **crash** once and never
  retries a **verdict**, where a verdict is any returncode inside the tool's documented
  range - 0 to 5 for pytest. **Exit 2 is inside that range and is not a verdict about the
  code**: pytest uses it for *interrupted*, which is what a collection error is. During the
  Phase 5 gate sweep an import fault inside scipy (no ACSOE frame anywhere in the
  traceback) interrupted collection after 4.51 s, and the criterion reported it exactly as
  it would report a failing test suite. The distinction worth drawing is probably **exit 2
  with zero tests run** against **exit 1 with failures named**. Not changed under a
  deadline, and in the same session that already moved this criterion's pytest timeout -
  one change to the gate's own behaviour is enough. Account:
  `docs/build-log/phase-5/lead.md`, the UNEXPLAINED entry of 2026-09-15.

- **OPEN FOR PHASE 6 by operator ruling 2026-09-15, deliberately not fixed in Phase 5:
  engine 8's `is_buy` cannot distinguish "no call" from "not a BUY".** Found by C-4 during
  spec 73's mutation sweep on engine 15. `PredictionResult.is_buy` is declared
  `is_buy: bool = False` in `engines/prediction/contracts.py` and `to_state()` publishes it
  unconditionally, so a **refusing** engine 8 — a DI refusal, an absent artefact, an
  incomplete vector — puts `is_buy: false` into `state["prediction"]` exactly as a predictor
  that ran and called no BUY does. Two facts arriving through one channel, which is the shape
  `code-standards.md` names under broad handlers.

  **It is not a fail-open and nothing is at risk today.** Engine 8 returns `BLOCK` on every
  refusal, the opportunity chain stops on the tick, and no consumer reaches the value. Engine
  15 was hardened in the same review to treat an absent or non-`bool` `is_buy` as non-BUY and
  block rather than pass, so the one reader in the chain already fails closed.

  **Why it is still worth fixing.** `expected_move_pct` is the field that got this right and
  is the model to copy: it is **omitted from the published mapping** on a refusal, so engine
  10 fails closed on a key that is not there rather than on a number it must interpret. The
  same treatment for `is_buy` (`bool | None`, omitted on a refusal) makes the payload say
  which of the two things happened, which matters for the console, for any log anyone reads
  after a refusal, and for Phase 6's engine 14 `adaptive_router`, the first component that
  reads engine 8's payload for something other than a gate decision.

  **Phase 6, engine 8's owner (C), and it touches engine 15's read** — the two land together
  or the hardening above starts reporting a refusal as a non-BUY. Not Phase 5 work: the phase
  is at its gate and this changes a published contract field, which is a lead approval and a
  seam, not a fix under a deadline.

- **FOUND 2026-09-13, ruled by the lead and flagged to the operator: `data_guard`'s
  missing-candle condition means "no subscribed pair traded in a bar", not "this pair has a
  hole".** Engine 3 computes `missing_bars` over the union of every pair's candles, so past a
  handful of pairs it is empty on essentially every tick, and the Phase 2 criterion that
  proves the block used one pair, where union and per-pair readings coincide. Measured by A-2
  against the real functions. Ruled: the field keeps its name and its union semantics, stated
  in one sentence at producer and consumer; per-pair holes are the feature layer's to mark
  (engine 5 counts them from each pair's own candles, spec 64 as amended); the staleness
  threshold is what guards a tick's liveness in practice; and a seam test with no double
  drives engine 3 with two pairs whose holes differ and asserts what `data_guard` does. The
  operator may overturn in favour of a per-pair block, which would block the whole tick on
  the ordinary fact that a thin pair did not trade.
- **OPEN AND BLOCKING THE PHASE, for the operator: the full 234-pair walk-forward projects
  to 22.2 hours and has deliberately not been started.** Measured by C-2 against the lead's
  three-hour guard, not estimated: one fold timed at 2, 4 and 8 pairs (6.76s, 8.46s, 12.42s),
  linear in training rows with the middle point predicted within 2%, fitting 4.87s plus
  109.74s per million training rows. The archive gives 2,021,760 training rows per fold and
  352 weekly folds, so 226.7s per fold and 22.2 hours. **It is a floor**: it excludes the
  dataset build over 47 GB of CSVs, excludes the skeptic's training set growing with every
  fold, and ignores LightGBM's cost per row rising as the data outgrows cache. The suspected
  culprit was cleared by measurement: `purged_walk_forward`'s per-row dicts cost 272ns per row
  per fold, about half an hour in total. **The 352 gradient-boosting fits are the cost, and
  they are the methodology rather than a defect** — retraining at the live cadence is what
  makes the walk-forward honest.

  **Lead's recommendation: cap to the most recent 52 folds, all 234 pairs.** That is one year
  of weekly retraining, about 3.3 hours plus the dataset build, and it preserves the two
  properties the withheld thresholds actually need — the full cross-section, because a DI or
  anomaly percentile fitted on a handful of pairs would refuse most of the universe the system
  trades, and the weekly cadence, which is a Locked Decision. It yields roughly 8 million
  out-of-sample rows across 234 pairs, far more than percentile estimation needs.
  **Rejected: widening `backtest.retrain_interval_days` for the offline run**, which would cut
  folds proportionally but changes the cadence the walk-forward exists to mirror, so it is a
  methodology change wearing a scheduling costume. **Rejected: bounding the pair set**, which
  keeps the time span and destroys the cross-section, which is the wrong half to keep.
  **Available: accept the day and schedule it**, which is the only option that satisfies the
  Phase 5 criterion's word "full" without qualification.

  Whichever is chosen, the digest says what it covers, and the full 352-fold run is named as
  Phase 7 work where the deflated metric wants the whole trial history.

  **OUTCOME, 2026-09-14.** The operator ruled to run it uncapped. It started 2026-09-13 21:46
  and **died 2026-09-14 21:55 at fold 405 of 457** (not 352: the dataset spans 2017-01-01 to
  2025-12-31) with `_ArrayMemoryError: Unable to allocate 7.80 GiB` in the skeptic's matrix
  build (8,950,630 rows by 117 columns). Folds 0 to 404 are on disk with complete manifests;
  the out-of-sample parquet and the digest were never written because the trainer writes them
  after the last fold. **Operator ruling 2026-09-14: no rerun, no resume; rebuild the
  out-of-sample parquet and the digest from the 405 artefacts**, verified fold by fold against
  each manifest, with the digest stating it covers 405 of 457 folds and why. The 52 missing
  folds are the 2025 test weeks. Account: `docs/build-log/phase-5/lead.md`.
- **PHASE 7 PREREQUISITES, recorded by operator ruling 2026-09-14. Phase 7's full walk-forward
  and its replays pay the same cost again unless all six are fixed first (the fifth added by the lead and the sixth by operator ruling, both 2026-09-15). Items 7 and 8 were added by operator ruling 2026-09-18: 7 is a gap in what the store records, and 8 is a fact every Phase 7 join must carry. Item 9 was added the same evening: a recording owed to a Phase 2 criterion.** Found by the
  Phase 5 full run (`docs/build-log/phase-5/lead.md`, the entries of 2026-09-13 and 2026-09-14):
  1. **Cap the skeptic's training set. RULED BY THE OPERATOR 2026-09-16: a rolling window of the
     last 13 folds**, matching the predictor's locked past-only 90-day window — it mirrors a Locked
     Decision rather than inventing a second convention, bounds memory by construction rather than
     by an arbitrary row count, and needs no sampling seed. The purge and embargo are unchanged and
     apply inside the window. **Implementation is Phase 7, not Phase 6**, because capping changes
     what the skeptic is trained on and re-measuring means retraining 405 skeptics.
     **Finding 1 below was measured on the uncapped skeptic** — see the caveat recorded against it.
     **Ruled 2026-09-19 (R2): the Phase 7 simulation runs the capped skeptic**, trained for the
     simulation window's folds only (spec 136). In the window the capped skeptic passes 6.2% of BUY
     calls at a 0.41 target rate against the uncapped one's 1.6% at 0.58 (`phase-7-findings.md` §5a).
     In the operator's words, that is a difference in this data at the step that decides the funnel's
     end, not a difference in principle. The all-405-fold re-measurement stays outstanding.
     The problem, for the record: fold k's skeptic trained on every eligible BUY call from every
     earlier fold, uncapped; by fold 404 that was 8.9M rows, the per-fold memory peak grew from
     ~66 GB to ~79 GB, and the run died allocating that matrix at fold 405.
  2. **No eager read-and-sort of the whole dataset.** `main()` reads the 20.3 GB dataset back
     and sorts it, a second full copy; about 43 GB of the run's memory was committed and idle
     afterwards. Write the dataset already ordered, or stream the sort.
  3. **No 20 million Python dicts in the splitter.** `train_walkforward` hands
     `purged_walk_forward` `to_dicts()` of two columns (~5 GB) and the splitter returns every
     fold's indices as tuples of Python ints (~10 GB). An index-based splitter over the two
     int64 columns costs megabytes; `walkforward_trains_on_the_past_only` must stay green.
  4. **A real memory test.** `test_the_builder_never_holds_two_archive_frames_at_once` counts
     frames and deliberately not bytes, so none of the above was visible to any test. A bounded
     peak-memory check over a run large enough to show growth per fold.
  5. **The DI's own fitting and scoring path does not finish at this size.** Found 2026-09-15 by
     the lead, fitting the DI from the saved rows: `di.score` costs 136 ms per test row (fold 404's
     93,166 rows are 3.5 hours) and the leave-one-out over a 200,000-row reference about 20 minutes
     of one core; the full run would have taken weeks had `prediction.di_percentile` been set.
     Batch the test-row score and parallelise or bound the leave-one-out, holding the result to
     `modelling.di`. Account: `docs/build-log/phase-5/lead.md`, 2026-09-15.
  6. **Half of every test week is an incomplete feature vector, refused by engines 8 and 13
     whatever any threshold is.** Recorded by operator ruling 2026-09-15. 8,025,361 of 15,978,803
     out-of-sample rows (50.2%) carry an unfilled 48- or 96-bar lookback feature, from pairs that
     do not trade every bar (26% of rows in 2017, 61% in 2023). That bounds everything
     downstream of engine 8 and it is not a threshold question.
     `docs/dataset/di-anomaly-distributions-2026-09-14.md`.
  7. **An approved trade leaves no record of why it was approved.** Recorded by operator ruling
     2026-09-18 (F-new-1 of `docs/build-log/phase-6/overnight-decisions-2026-09-18-night.md`).
     Only `rejections` carries `expected_move_pct`, `friction_pct`, `net_edge_pct` and
     `hurdle_pct` (engine 19's `ECONOMICS_FIELDS`, harvested from whichever engine blocked);
     `trades` carries none of them, and no decision or SHAP row is written for an approval. So
     the counterfactual dataset — this project's contribution — records the reasons for one side
     of the decision only. **Phase 7's attribution will want to explain which trades the system
     took and why, and as things stand it cannot.** A schema change (B) and an engine 19 change
     (C), so a spec, not a patch.
  8. **`cycle_id` on `orders` and `positions` rows is the last tick that wrote the row, not the
     tick that created it.** Recorded, not fixed, by operator ruling 2026-09-18 (F-new-2). Engine
     19 upserts both tables, so every later tick overwrites the column: the first paper trade's
     entry was placed on cycle 2 and is stored with `cycle_id` 3; its position opened on cycle 3
     and is stored with 7. `placed_at` and `opened_at` still say when. **Any analysis joining on
     `cycle_id` must know this, and Phase 7 will join on it** — a join from an order to the tick
     that placed it by `(run_id, cycle_id)` lands on the wrong tick.
  9. **A genuine `AssetPairs` recording, so the candle criterion's tolerance stops being an invented
     number.** Re-scoped by operator ruling of 2026-09-18 evening. It was first scheduled (S2)
     alongside Q3's re-cut, for spec 118's criterion, which has since been removed with Q3.
     `candles_match_independent_reduction_of_recorded_trades` still reads its `tick_size` from
     `tests/fixtures/kraken/asset_pairs.json`, which is invented Phase 0 data. The verdict does not
     depend on it (the tolerance is never engaged), but the number is a choice where the phase row
     asks for an exchange value.
  Also measured, for whoever plans Phase 7: 457 weekly folds, pairs arriving over time (14 in
  2017, 115 first appearing in 2022), folds ranging from ~25 s (2017) to ~10 min (late 2024)
  on this machine; the 22.2-hour projection assumed 234 pairs in every fold and was wrong.
- **RULED by the lead 2026-09-13, flagged to the operator as overturnable: engine 8 blocks
  when an artefact's baked-in DI percentile disagrees with the config.** Found by B-2 while
  rehearsing engines 13 and 8. The DI threshold travels *inside* the artefact, and engine 8
  never reads `prediction.di_percentile` — the trainer does, and a run trained without it
  carries no `di.npz`, which engine 8 refuses. So the withheld-key case is already
  fail-closed. What was open is the other case: once any percentile is baked in, changing the
  config changes nothing, and the operator would read a number the running system does not
  use. Ruled: compare the manifest's percentile against the config key **when the key is
  present** and block on a mismatch, reason code `di_percentile_mismatch`, naming both
  numbers; unchanged when the key is absent. It only reduces willingness to trade, so
  invariant 4 is untouched, and it is invariant 3's answer to "the system cannot tell which
  threshold governs".
- **NOTED 2026-09-13, live behaviour the operator should know about: a very thin pair can be
  refused by the anomaly gate for want of dispersion rather than for anomaly.** A constant
  trade count over a window makes the trade-count z-score a division by zero, so engine 13
  correctly refuses the vector as incomplete. Found by B-2 as a fixture defect twice over;
  the live case is real and is the correct fail-closed outcome, but it means the anomaly gate
  and the thin-pair floor (`dataset.min_labelled_rows`, operator ruling 3) are two views of
  one question the operator may want to answer together.
- **OPEN, Phase 5, for the operator, and it bears on `anomaly.threshold_percentile`: the
  anomaly detector as built does not flag a ten-sigma volume spike at any high percentile.**
  Measured by C-2 in spec 70: the spiked bar scores at the 0.904 quantile of training scores,
  under both 0.99 and 0.95, because the rolling z-score caps an outlier before the model sees
  it and an isolation forest over 21 columns dilutes a spike extreme in 8. Blocking it needs
  roughly a 0.90 percentile, which also blocks one ordinary bar in ten. Options: a lower
  percentile, a narrower velocity-and-volume input set for engine 13, or a different model.
  Lead's recommendation: the narrower input set. Nothing was tuned to make the spec's check
  pass; the spec's acceptance line is amended to the measurement.
- **OPEN, Phase 5, for the operator, a modelling decision: a macro pair's own rows can
  identify themselves.** On a BTC row, `macro_btc_log_return_4` equals `log_return_4`
  exactly, so the coincidence of two features encodes pair identity although no single
  feature does. Under 1% of rows in the 234-pair dataset, 33% in a three-pair smoke run.
  Lead ruling 2026-09-13: leave it in Phase 5 and document the fraction in the manifest and
  digest. Nulling the macro columns on those rows creates a distinctive missingness pattern,
  a stronger signal than the one removed; excluding the macro pairs from the candidate set
  throws away the two most liquid pairs and is a trading decision. C-2's build log has the
  three options.
- **OPEN, Phase 5, for the operator at leisure: where a previous bar's DI would live so that engine 12 `regime` can read DI threshold crossings.** The locked decision says crossings feed the regime engine; engine 12 runs before engine 8 on the same tick and `state` is fresh, so nothing persists last bar's DI. Engine 12 publishes `di_regime_shift: null` with the reason (spec 66). Persisting it is a schema question, B's edit and the lead's approval, and Phase 6's router is the first reader that would need it.
- **DECIDED 2026-09-09, and it is the first task of Phase 2, before any engine work.** The operator ruled on the defect below. The fix composes the reader from the four methods `StoreClient` already has — `pending_commands()`, `claim_command(command_id, *, claimed_at, run_id)`, `claimed_unconsumed_commands()` and `mark_command_consumed(command_id, *, consumed_at)` — **entirely inside `core/`, renaming nothing in B's directory.** It also wires the startup re-application of claimed-but-unconsumed rows, which is absent today. And it lands with a **Phase 2 criterion that drives the real `StoreClient` — not a double — through `activate`, `freeze` and `close_all`, asserting the mode changed and the row was consumed**: a criterion that would have caught this. **Phase 0 was reported green with the kill switch inert**, and that is the point worth carrying: `orchestrator_empty_registry` runs against an empty registry and every other test of the command path uses a test double, so nothing in the suite ever put the real store behind the real reader. A gate that only ever exercises a seam through a double does not test the seam; it tests the double. The same question should be asked of every other seam in `ownership.md` before its phase closes.
- **RESOLVED 2026-09-09, before Phase 2 engine work began — the orchestrator reads no commands, so the kill switch does not work.** Fixed by the lead as the first task of the phase, composed from the four methods `StoreClient` already exposes, entirely inside `core/`, renaming nothing in B's directory; the startup re-application of claimed-but-unconsumed rows is wired and had never existed. A third break in the same path turned up while fixing it: `_clear_close_intent_if_finished` called a `mark_close_all_consumed` the store has never had, so even a *successful* liquidation left its row unconsumed for the startup replay to re-run on the next boot against an already-flat account. `commands_round_trip` is registered for phase 2 and PASSes. The original finding, kept because the lesson is the transferable part: Found 2026-09-09 by C while building spec 24, confirmed and widened by the lead. `core/orchestrator.py:173` looks up `store.claim_pending_commands` via `getattr`; **`StoreClient` has no such method.** It exposes `pending_commands()`, `claimed_unconsumed_commands()`, `claim_command(command_id, *, claimed_at, run_id)` and `mark_command_consumed(command_id, *, consumed_at)`. So the lookup returns `None`, the reader logs `commands_skipped` at debug level and returns, and **a daemon wired to the real store would silently ignore every Activate, Freeze and Close-all ever written.** Two further faults in the same method: `_mark_consumed` calls `mark_command_consumed(command, now=...)` against a signature of `(command_id, *, consumed_at)`, which would raise if it were ever reached; and **the startup re-application of claimed-but-unconsumed rows is not wired at all** — nothing in `src/` calls `claimed_unconsumed_commands()`, though `architecture-context.md` requires it and names the exact failure it prevents, a daemon killed mid-liquidation coming back with `close_all` marked done and positions still open. The only implementations of the orchestrator's shape are a test double in `tests/core/test_orchestrator.py` and C's documented adapter in `tests/console/test_commands.py`, which is why every gate to date has passed over it. **This is Phase 0 work in `core/orchestrator.py`, which is lead-only, so it is the lead's to fix and no teammate's.** Harmless in Phase 1 — no daemon runs and the console only writes rows — and it bites the moment one does, which is Phase 2. The cheapest correct fix stays entirely inside `core/`: compose the reader from the four methods the store already has, rather than renaming anything in B's directory. **Fix before any Phase 2 work begins.**
- **RESOLVED 2026-09-09 — `toolchain_green` is now registered for every phase**, via `register_every_phase`, exactly as `docs_vocabulary` is. `TOOLCHAIN` stays scoped to `src/`: the operator deliberately did not widen it to `tests/` or `scripts/`, so the two Phase 0 findings in `verify.py` and the three in `tests/` remain out of scope for the gate. One consequence to expect: every phase's gate now runs `pytest`, so the intermittent seed-path crash below can now surface as a FAIL on any phase rather than only Phase 0. The account of the hole this closed:
- *Was open, for the operator at the Phase 1 boundary — `toolchain_green` was registered for Phase 0 only, so from Phase 1 onward the gate never ran the tests.* Found 2026-09-09: `scripts/verify.py --phase 1` reported `7 PASS, 0 FAIL, 2 PENDING` while `pytest` was reporting `2 failed, 639 passed`. Nothing in the report was wrong — no Phase 1 criterion makes a claim about the suite — but "a phase is done when `verify.py --phase N` passes every criterion" is the project's definition of done, and for every phase after 0 that definition currently cannot see a red suite. Run-protocol step 4 covers the gap by making each agent run all four commands themselves, which is why this was caught, but it depends on a person following a procedure rather than on the gate. **The obvious fix is to register `toolchain_green` for every phase, exactly as `docs_vocabulary` already is.** It is a change to what every phase asserts, so it belongs at a phase boundary and to the operator, not mid-phase and not to an agent — the same reasoning that deferred widening `TOOLCHAIN` beyond `src/` out of Phase 0. Note the two interact: registering it for every phase also spreads the intermittent seed-path crash across every phase's gate, so the crash question above should be settled first or at the same time.
- **RESOLVED 2026-09-19 by operator ruling (R1, closing spec 75, open since Phase 3): engine 7
  ranks its universe by engine 8's expected move, batched, and invariant 4 is amended to permit
  it** (the wording is R12, in `feature-specs/126-phase-7-rulings-into-the-documents.md` step 4,
  and lands in `trading-invariants.md` with spec 126). **The reasoning, as ruled:** expected move is
  not a selected feature. It is the predictor's own output and the exact number engine 10 compares
  against the hurdle, so choosing it involves no search over candidates. `log_return_4` was
  rejected because it was chosen from a study computed over the same out-of-sample data the Phase 7
  report uses. Net-margin ranking was rejected on live feasibility, not cost: 127 REST calls per bar,
  unchecked against the rate limiter, so simulating it would measure a system that could not run
  live. Alphabetical stays as the simulation's baseline, over the same window and tiers. The
  ranking skips pairs the anomaly and DI gates would refuse (R11), because that is how the 46-trade
  figure was measured, and every gate still judges the chosen pair independently. **The residual
  circularity is recorded, not denied:** the expected-move grid (`phase-7-findings.md` §4) was
  computed on the same out-of-sample data, before the decision to amend. Three things bound it: the
  stated criterion was sample size; the net stayed at about zero under every row; and the promotion
  bar was fixed before anything ran. Implemented by spec 144; `scout.rank_feature` lands with spec
  126. Alphabetical ordering therefore stays in force until spec 144 is built, and it is no longer
  an open question. *The entry below is the question as it stood, kept for the record.*
- *As it stood before 2026-09-19:* **OPEN, for Phase 7 by operator ruling 2026-09-15: whether any
  ranking feature pays for a trade.** Spec 75's study over the full run (`docs/dataset/ranking-study-2026-09-14.md`) reports
  the **mean realised barrier return per bar** of the pair each feature would rank first, and the
  short-horizon reversal features (`bar_body_pct`, `log_return_4`, `log_return_16` ascending) read
  positive in every test year. **That number is not comparable with friction**: friction is paid
  per round trip over a 2 to 12 hour hold spanning many bars, and a per-bar mean over candidate
  bars says nothing about returns per trade over the actual holding period. The comparison is to
  be settled in Phase 7, when the chain runs end to end and returns are measured over the holding
  period. **The thin-pair caveat stays attached**: `bar_body_pct` ascending's return grows as its
  picks move into intermittently traded pairs (37-44% of its picks from 2022, against 17-25% for
  the control), which is the shape a bid-ask bounce leaves, and the archive has no spread to rule
  it out. Until then `scout.rank_feature` is absent and engine 7 ranks alphabetically.
- **~~OPEN, and deliberately so: engine 7 `scout` has no ranking score, and Phase 3 does not give it one.~~ Superseded by the entry above (spec 76 built the named-feature seam; the operator ruled no feature 2026-09-15).** Operator ruling 2026-09-10. Invariant 4 says the candidate ranking is "a deterministic score over features"; features are engine 5, which is Phase 5. The operator's words, which belong in the record verbatim: *a deterministic score over features is meaningless before features exist, and a placeholder score would be a check whose output resembles the claim while the claim is untrue — this phase has produced enough of those. The universe filter is the contribution; ranking one candidate out of a filtered set is a Phase 5 decision made with real features in front of us.* So Phase 3 orders the universe **alphabetically**, which is equal treatment of every pair when nothing yet distinguishes them, and spec 44 isolates the ordering behind one named function so Phase 5 is a single edit. **An agent arriving in Phase 5 must not read alphabetical ordering as a choice anyone defended.** It is a recorded absence.
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
- ~~Paper-mode fallbacks are stated once, in a table, scoped to mode. Live mode always blocks. Fee falls back to tier 1; balance falls back to `paper.starting_balances`, a per-currency map; pair rules and spread have no fallback and block the pair.~~ **Superseded — every clause of this line is now false.** The fee row was retired 2026-09-10 (a pair with no fee data blocks); the balance row became the paper ledger on 2026-09-16 and engine 11's substitution was removed outright on the 17th. **There is no paper-mode fallback left anywhere in the system**; see invariant 2 as it now reads. The line is struck rather than rewritten because it was true on its date and this is a dated record. Found by A during spec 109, 2026-09-18, and reported rather than edited — it is the most quotable stale sentence left in the repository, in the lead's own file.
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

### The three rulings that opened Phase 3, 2026-09-10

**1. A drawdown breach freezes. It does not liquidate.** Engine 17's `CONDITION_ACTION` had been unratified since B built the engine, because invariant 14 and spec 36 could not both be satisfied by the Phase 0 seed: §14 listed the drawdown and loss-streak limits as escalation conditions, the seed carries a breached drawdown *and* an open position *and* a resting order, and spec 36's exit criterion required a freeze. No fixture could satisfy both. The ruling: **`close_all` is reserved for the invariant 14 data-outage escalation** and for the operator's Close all button. Drawdown, loss streak and error rate all write `freeze`. Freeze stops new positions while the manage chain keeps watching the open ones, and the operator decides whether to liquidate. The reasoning is what the condition is a statement *about*: a drawdown is a statement about past trades and liquidating on it realises a loss on the system's own authority at the moment it has least evidence it is reading the market correctly; a data outage is a statement about present knowledge, and unknown exposure is worse than a bad fill.

**2. Invariant 2's fee-tier fallback is retired.** The paper-mode table told the system to fall back to a named worst tier when `TradeVolume` failed. It was never implementable: `AssetPairs` carries no fee schedule, so there was no runtime source the value could come from, and the only way to honour the row was to write a fee percentage into the code — the hardcoded fee `AGENTS.md` forbids in its first paragraph. A confirmed pair with no fee data now **blocks that pair**, for the same reason an assumed spread does. Two consequences recorded rather than discovered: **balance is now the only paper-mode fallback in the whole system**, and it has no implementer — spec 41 builds it. And an unauthenticated fresh clone now runs its loop and records the order book but takes no paper trades, because every pair blocks at the cost gate. That is the honest description and it is preferable to a research dataset priced on a guess. A `docs_vocabulary` row was added for the retired wording, qualified so it only fires on a line that also tells the system to assume one, and it was **observed to FAIL** against a reinstatement before being trusted.

**3. `kraken.cache_ttl_s` is two keys: 300 seconds for `AssetPairs`, 60 for `TradeVolume`.** There was no cache at all, so invariant 2's *"a cache stale beyond its TTL counts as a failed fetch"* had nothing to be true of. Two keys and not one because pair rules change when Kraken lists something and a fee tier can move on a single trade. The cache and the last-known-good retention are separate mechanisms with separate readers and must not be merged: the cache answers *may I use this now*, retention answers *what is the last thing we knew*, and only invariant 14 may read the second.

**And one ruling on how the wiring is tested.** Every test that hand-builds `state["exchange"]` is rewritten to build it from engine 1's actual output. The operator's reason: *a mock that agrees with its caller is what hid this for a whole phase, and it is the third time that shape has appeared.* The first was the command reader whose every test used a store double; the second was a criterion held to a fabricated `EngineContext` whose body never once executed.

## Architecture Decisions

- Engines communicate only through `state`. No engine imports another.
- `context.now` is injected everywhere, so replay is faithful and look-ahead is structurally impossible.
- Engine 19 `memory` runs in the manage chain, every tick, so a rejection is recorded even on a tick where the opportunity chain never ran. `safety`'s outage counter is built from those records, which is why the per-tick block write is not optional.
- Live loop code and `research/` never import from each other. `scripts/verify.py` is outside both and may import either.
- Phase exit criteria are executable in `scripts/verify.py`, not a checklist anyone reads.

## Known Risks

- **A second unrecoverable gap in the live recording, 2026-09-17 03:13–08:20 UTC (308 minutes).** The network was down; the recorder's heartbeat reports `connected: false` for the whole span and both recorders and both supervisors reconnected on their own. The gap is marked in the archive and the archive is unedited (invariant 11); that span of order-book and spread history cannot be recovered. The first unrecoverable gap is the ten-hour silence of 2026-09-09, when no recorder was running.
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

  **RE-OPENED AND WIDENED 2026-09-09. The "seed write path" in this entry's title is now wrong, and the retry does not cover the worst shape.** A escalated two further instances, neither touching SQLite or `seed.py`:

  - **Inside CPython's own `ast.walk`**, during `tests/console/test_reader.py::test_no_console_module_reads_wall_time`: `todo` is a `deque` created two lines earlier and had become an `ast.Load` object — `AttributeError: 'Load' object has no attribute 'extend'`. **A local variable changed identity mid-function.** Not a test bug and not a library bug; it is interpreter state being corrupted, which is the signature this entry already describes. Passed in isolation, and C reported 1068 passing at the same moment.
  - `pytest tests/engines/test_market_sensor.py` died with a faulthandler dump **after all 20 of its tests had passed**. That file touches no seed and no SQLite.

  **The dangerous consequence, and the reason this matters more than the crash count.** The `ast.walk` instance **did not crash**. It produced an ordinary failing verdict with a non-zero exit. `toolchain_green` retries a *crash* and never retries a *verdict* — which is correct policy, and means **this shape is reported as a genuine test failure in whoever's file it lands in.** It looks exactly like another agent broke something. It landed in C's test during A's run.

  **So, standing guidance until this is understood: a one-off failure in another agent's tests, which passes in isolation and which that agent did not touch, should be suspected as this fault before it is treated as their defect.** Capture the full output — head included, never a `tail` pipe — and compare against the instances above.

  Nothing here is a request to chase the cause. Hardware remains suspected and out of scope by the operator's ruling. What has changed is that the entry's own scope statement is stale and the mitigation's coverage is narrower than it reads.

  **Consequences.** The `toolchain_green` retry is not sufficient on its own: at roughly a 20% per-run crash rate, two consecutive crashes is about 4%, which is how often a spurious FAIL should be expected. That matches what was seen. It does not block Phase 1 — the mid-phase bar is no FAIL, and `--phase 1` has been clean throughout — but it does mean a FAIL must be **captured in full before re-running**, and a spurious FAIL must never be assumed without the trace to prove it. Whether to widen the retry, quarantine the seed fixture, or chase the pytest lead is a decision for the operator at a phase boundary, not something to settle mid-phase.

  **Fired again at the Phase 2 close, 2026-09-10, and it is now a stated limitation of the work rather than only a risk on this register.**

  The fault appeared on the **first gate run of the closing session** and **cleared on the crash-aware retry in `toolchain_green`** — the mitigation behaving exactly as designed: one crash retried and named, a verdict never retried. It then fired **repeatedly across the rest of the close**, and the session became the densest sample of this fault the project has taken. Closing the phase meant running the gates again after each documentation change, so roughly **twenty gate runs** were made in one session — about ten of Phase 2 and five each of Phases 0 and 1 — plus three direct full-suite runs.

  **Four of those runs reported FAIL. Every one was this fault, and none was a defect.** Two landed on Phase 2, one on Phase 0 and one on Phase 1, which is itself diagnostic: the tree did not change between them. Of the three direct full-suite runs, two reported `1075 passed` and one died with a faulthandler dump.

  The failing tests were different every time and scattered across unrelated files:

  > `ERROR tests/clients/store/test_seed.py::test_a_tick_with_two_blockers_contributes_one_to_the_outage` — `1074 passed, 1 error`, first attempt crashed with `0xC0000005 ACCESS_VIOLATION`
  > `ERROR tests/engines/test_exchange.py::...` **and** `FAILED tests/platform/test_record_format.py::test_sample_contains_no_secret_shaped_key` — `1 failed, 1073 passed, 1 error`
  > `ERROR tests/cli/test_entrypoints.py::test_the_console_port_comes_from_config_and_never_from_a_constant` — `1074 passed, 1 error`
  > `RETRIED AFTER CRASH: the process died with 3221226505 (0xC0000409 STACK_BUFFER_OVERRUN) [...] the retry was clean`

  **All three named tests were then run together in isolation and passed in 0.72s**, and the only changes staged at the time were Markdown — the tracker and the build logs. No source file, test file or fixture was touched. So the tree that "failed" and the tree that passed were byte-identical.

  **Two of the four defeated the mitigation, and that is the shape that matters.** The retried run returned a wrong *verdict* rather than a second crash, and policy is that a crash is retried once and a verdict is never retried — so the gate correctly reported FAIL. That policy is right and must not be relaxed to make this go away: **a rule that retries verdicts is a rule that retries real defects until they pass.** B recorded the first instance of this shape earlier in the phase; there are now four.

  **One of them is worth singling out.** `test_sample_contains_no_secret_shaped_key` is the test that proves no credential was committed into the recorder sample. A spurious FAIL there reads as a leaked secret in a public repository, which is the single most alarming thing this suite could say, and it was false. A fault that can fabricate *that* verdict is a fault that can fabricate any of them, in either direction. The criterion named it in its own PASS line rather than hiding it:

  > `RETRIED AFTER CRASH: pytest CRASHED: the process died with 3221226505 (0xC0000409 STACK_BUFFER_OVERRUN), which is outside the 0-5 range pytest returns [...] the retry was clean`

  Four spurious FAILs and at least two native crashes across roughly twenty gate runs is a materially higher rate than the ~20% per-run this entry has recorded since Phase 0. Whether the rate has genuinely risen or this session simply sampled it far more heavily than any previous one is **not established**, and one session is not enough to claim a trend — the honest reading is that the earlier estimate was taken from far fewer runs. **Phase 2 is closed on gates that had to be run more than once**, and that is stated here rather than smoothed over: the PASSes are real, reproducible and were re-obtained on a byte-identical tree, the mitigation did what it was designed to do, and the fact that it had to is the limitation.

  **Why this moves it into the dissertation's limitations chapter.** It is no longer a hazard that might materialise; it has now materialised in every phase of the project — Phase 0 where it was found, Phase 1 where its recorded signature turned out to be wrong, Phase 2 where it beat the retry once (B's entry) and where it has now fired at the phase boundary itself. Across those phases it has been seen inside pydantic-core, inside `sqlite3`'s C extension, inside pure-Python pyyaml, inside CPython's own `ast.walk`, and as a lax pydantic validator returning a strict validator's error. That spread is not a defect in any one library, and it is not going to be fixed by this project.

  What it means for the claims the dissertation makes is specific and limited, and it should be written down in exactly these terms rather than as a general disclaimer:

  - **Every phase gate in this project is a retried measurement on hardware with a known intermittent fault.** A green gate means green on a run that completed; at roughly a 20% per-run crash rate, two consecutive crashes is about 4%, which is how often a spurious FAIL should be expected and has been seen.
  - **The retry covers crashes and not wrong answers.** The `ast.walk` instance produced an ordinary failing verdict, not a crash, and the lax-validator instance produced a `ValidationError` naming a real field. Those shapes reach the operator as somebody's defect. The standing guidance already on this register — suspect this fault before treating a one-off failure in an untouched file as an agent's defect — is a *procedural* mitigation, and procedural mitigations belong in a limitations section because they depend on a person following them.
  - **It is not reproducible on demand and the root cause was not established.** Hardware is suspected; pyarrow, `pytest-asyncio`, test ordering, `root_import_path` and the pydantic-core version were each ruled out by test; the one experiment that would have separated software from silicon was overridden by the power plan. 1,120 consecutive seeds outside pytest produced zero faults, which is suggestive at around p ≈ 0.1 and not conclusive.
  - **What is unaffected.** None of the five sites is in a code path that runs in production: they are the seed generator, the test harness and the verifier. No engine, no store write on the live path and no orchestrator tick has ever exhibited it. The limitation is on the *evidence-gathering apparatus*, not on the system under test — and that distinction is the honest way to state it.

  Still not a request to chase the cause. The operator's ruling that hardware is out of scope stands. What changed at this close is where it gets written up.

## Session Notes

- 2026-09-15 — lead (Opus 5) with C-3, C-4, B-3. Operator rulings recorded; DI 48-bar exclusion
  built with criterion `di_leave_one_out_excludes_48_bars`; engine 15 reviewed (two fail-open
  defects fixed) and rehearsed; engines 5, 6, 12, 13, 8, 15 registered; the exclusion refit over
  405 folds refuses 6.79% / 3.31% / 2.06% at 0.95 / 0.99 / 0.999. **Not done**: the two ruled
  config values (six tests to repoint), C-4's sweep 2, gates for phases 0 to 4. Exact state in
  Handoff 4 at the top of `feature-specs/PHASE-5-TASKS.md`.
- 2026-09-13, second session — Phase 5 resumed with the same team and wound down by the
  operator's command. Done and committed: 14 of 21 specs (59 to 69, 76, 78, 79); gate 10 PASS,
  0 FAIL, 3 PENDING; engines 5, 6, 7, 12 rehearsed together. Two items tracked to closure at
  the top of `feature-specs/PHASE-5-TASKS.md` (Handoff 2): the `build_dataset` per-pair fix
  followed by the full 234-pair training run, deliberately not started at the close; and the
  suite runtime, deferred until after spec 74. Remaining: 70 to 75, the engines 13, 8, 15
  rehearsal, 77.
- 2026-09-13 — Phase 5 opened and run for one session, then wound down by the operator at
  the session limit. Done and committed: specs 59, 61, 62, 63, 76. Half-finished and
  uncommitted: 60 (helper block only) and 64 (engine 5 landed, one lint finding); untouched:
  65 to 75, 77. The full handoff, the rulings made after spec 59, and the agent-team incident
  (a revived team, two writers per lane, sends by name reaching the wrong session) are at the
  top of `feature-specs/PHASE-5-TASKS.md` and in `docs/build-log/phase-5/lead.md`. The three
  operator thresholds are deliberately absent from config until the walk-forward reports.
- 2026-09-12 — full-archive rebuild (234 pairs), dataset measured, three operator rulings applied (past-only walk-forward, 2017 cutoff, thin-pair floor as a named knob). Phase 5 not started. The Phase 4 gate was not re-run in full after the new criterion landed; every Phase 4 criterion was run directly and the full pytest suite was run — see the lead's build log for the outputs.
- Project starts from scratch. Any earlier ACSOE code was throwaway scaffolding and must not be carried over or referenced.
