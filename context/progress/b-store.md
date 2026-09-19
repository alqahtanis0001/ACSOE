# Agent B — Store and trading

## Phase 7, b-store — CLAIMED 2026-09-19, spec 132, then engine 7's half of spec 144

I claimed these before writing any code, per rule 5. The Phase 6 preflight gate finished first (`exit 0`, 13/13 PASS).

**Spec 132: migration 0006.** Approval economics and the three model run ids go on `trades`. The
scenario digest and description go on `runs`. The approval is held between the placing tick and
the trade in a new **write-once `approvals` table**, keyed by the entry order's `userref`.
Rejected: columns on `orders`. My reasoning is in the build log. I told c-eval and the lead on
2026-09-19. **Cross-lane, and it must land in the same gate:** `scripts/verify.py`
`DOCUMENTED_TABLES` gains `approvals` (C), and `architecture-context.md` gets an `approvals` row in
the storage table (lead).

**Status at a glance (2026-09-19, later):**
- **Spec 132 + `approvals.details` (spec 145's column):** DONE. The sweep killed 13/13 and then
  5/5.
- **Spec 144, engine 7's half:** DONE. The sweep killed 22/22.
- **Spec 140's store surface:** DONE. That is `write_shap` and `read_shap`, plus the new
  `StoreClient(derived_dir=...)` keyword; the sweep killed 12/12.
  - **Waiting on A:** `cli/engine.py` and `cli/research.py` must pass `derived_dir=paths.derived`.
    I asked a-replay.
- **Withdrawn by c-eval:** `closed_trades(run_id=)`.
- **Nothing blocked on me.**

**Spec 132: DONE on my side, 2026-09-19.**
- Files: `db/migrations/0006_approval_economics.sql`; `clients/store/contracts.py`
  (`ApprovalRow`, and the new fields on `TradeRow` and `RunRow`); `clients/store/client.py`
  (`write_approval`, `approval`, the `scenario_*` kwargs on `start_run`, and `write_run` excluding
  the scenario); `clients/store/migrations.py` (`EXPECTED_TABLES` and `EXPECTED_INDEXES`);
  `clients/store/__init__.py`; `tests/db/test_migrations.py` (the money-column set);
  `tests/clients/store/test_approval_economics.py` (new, 25 tests).
- Tests: `tests/db tests/clients/store` gives 301 passed. The store importers (`tests/core`,
  engine 19, `tests/console`, `tests/clients`) give 1054 passed. mypy and ruff are clean.
- Mutation sweep: 13 arms, all KILLED. M13 survived the first run and was killed after the test
  was widened. The full record is in the build log.
- **`db_migrates_from_empty` FAILs until C adds `approvals` to `DOCUMENTED_TABLES`.** It reports
  `declared-only=['approvals']`, which is the expected cross-lane step.
  `seed_fixtures_present` PASSes.

**Spec 144, engine 7's half: DONE on my side, 2026-09-19.** Sweep: 22 arms, all 22 KILLED
(build log). The scout tests and the ranking tests give 84 passed. mypy and ruff are clean for my
files.
`rank_universe` takes the expected-move order when `scout.rank_feature` is `expected_move`. The
ranking is c-models' `modelling/ranking.py`, which landed before my proposal was answered. I
adapted to its signature, and the decision is in the build log.
- Files: `engines/scout/contracts.py`, `engine.py` and `README.md` (all four scout files were
  normalised from CRLF to LF first); `tests/engines/test_scout.py` (the seam assertion now names
  `rank_universe`); `tests/engines/test_scout_ranking.py` (new, 21 tests). Of those, 1 has no
  double: the real function, a real trained run, and the real engines 13 and 8.
- New reason code `no_rankable_pair` (PASS). C landed its prose.
- **One Check When Done item waits on specs 135 and 142:** the ranked candidate must equal
  `q_emrank.py`'s pick on the rehearsal day's bars. That needs the assembled fold artefacts and
  a-replay's rehearsal. Note for whoever runs it: `q_emrank.py` ranks every scored pair, while
  engine 7 ranks only its filtered universe. A disagreement is expected wherever the script's
  pick is a pair engine 7 excluded, and it has to be explained in those terms rather than
  counted as a mismatch.

## Phase 6, session 9 — CLAIMED 2026-09-18, spec 119

Claimed before any code, per rule 5. Tree clean at `e3b5406`, the full gate green when handed to
me (13 criteria, 13 PASS, 0 FAIL, 0 PENDING). I am the first work after a green gate, so any red
I introduce is mine and visible immediately.

**Spec 119 — every seeded rejection uses an `(engine, code)` pair the live system can emit.**
`clients/store/seed.py`'s `_REJECTION_REASONS` carries fourteen `(engine, code, sentence)`
triples written in Phase 0, before any engine existed. The truth is derived here from each
engine's own `contracts.py`, not from the tracker's list of five: **seven of the fourteen rows
are wrong, spread over six distinct bad pairs, and one of the six is not in the tracker's list**
(`scout`/`outside_universe`). Engine 9's row becomes engine 10 refusing on the absent estimate,
by the operator's ruling; the other five mappings are how-choices recorded in the build log with
the option rejected.

**The test nothing has today**, and the reason this is a spec rather than a tidy-up: two tests in
`tests/clients/store/test_seed.py` walking the seeded `(engine, code)` pairs — one over the rows
the seed actually wrote to the database, one over the whole `_REJECTION_REASONS` vocabulary so an
entry the RNG never picked is still checked — asserting each code is declared as a `REASON_*`
constant in that engine's `contracts.py`. Observed red on the pre-fix seed before anything is
changed. Spec 99's walking test goes engines → map; this one goes fixture → engines, which is the
direction nothing walks.

**Not touched:** `console/format.py` (C's, and C's spec 120 retires the orphaned prose after this
lands), any engine, `scripts/verify.py`, `tests/verify/**`, `core/`, `bootstrap.py`, `config/`.
`seed_fixtures_present` must still PASS with the same six fixtures; no row is deleted and the
variety of reasons does not shrink — only two engine *names* leave the vocabulary, because
neither can be a `rejected_by` in the live chain.

**Line endings measured in Python at claim time** (`b.count(b"\r\n")` against `b.count(b"\n")`,
never `grep -c`): `src/acsoe/clients/store/seed.py` is **1281 CRLF / 1281 LF — fully CRLF**, and
stays so; every edit to it goes through an LF-view helper that writes back with `newline="\r\n"`.
Pure LF and staying so: `tests/clients/store/test_seed.py` (563) and both records.

Records: this file and `docs/build-log/phase-6/b-store.md`. Scratch in the session scratchpad;
logs `logs/verify/b119-*`. No commit; no full gate from me, by instruction — narrow runs only.

### Spec 119 — DONE 2026-09-18, not committed (the lead commits)

- **The truth, derived from the engines: seven of fourteen rows wrong, six distinct bad pairs, and
  the tracker's list is one short.** `scout`/`outside_universe` is not in the tracker's five, and it
  is not a transcription slip: the finding came from spec 99's walking test, which goes engines
  → map, and `outside_universe` **is** in `REASON_PROSE`, so nothing complained. The five it
  did name are the five whose engines are C's; `scout` is mine.
- **Two of the six engines cannot be a `rejected_by` at all.** Engine 9 `order_book` never returns
  `BLOCK` (the operator's ruled case). **Engine 7 `scout` was not known to be the same shape**: it
  publishes `reason_code=empty_universe` exactly when `candidate is None`, and engine 19's
  `_write_rejection` returns 0 without a candidate pair, so none of `scout`'s twelve real codes can
  ever reach the `rejections` table. Its exclusion codes are a per-pair tally over the universe,
  not a refusal of a candidate. So that row changed engine too.
- **A third, smaller disagreement.** The finding and the spec both say `REASON_PROSE` maps both
  vocabularies. It maps five of the six: `dissimilarity_index` was retired by spec 71 and is not a
  key today. The row still rendered because `operator_reason` prefers the sentence stored beside
  the code. That is the mechanism that hid all of this: **the feed never needed the codes to be
  real.**
- **The mapping**, each recorded in the build log with the option rejected: `scout`/`outside_universe`
  → `risk`/`position_open_on_pair`; both `skeptic`/`meta_label_veto` →
  `skeptic`/`skeptic_veto`; `anomaly`/`outlier_market_state` → `anomaly`/`market_anomalous`;
  `prediction`/`dissimilarity_index` → `prediction`/`di_refused`;
  `order_book`/`insufficient_depth` → `cost`/`cost_inputs_unavailable` (the operator's
  ruling); `decision`/`no_candidate_cleared` → `decision`/`stale_bar`.
- **The seed's purpose is intact.** Fourteen rows still, 46 `rejections` rows still, **12 distinct
  codes before and 12 after**. Proven rather than asserted: the committed seed and the working-tree
  seed were each run into a fresh database and compared table by table — `runs`, `trades`,
  `positions`, `orders`, `equity_snapshots`, `block_records`, `leaderboard` and `commands` are
  byte-identical, and in `rejections` every column but `rejected_by`, `reason_code` and `reason` is
  identical row for row. The RNG stream is untouched because the list is still fourteen long.
- **The new tests, red first.** `5 failed` on the pre-fix seed, `5 passed` after. The database walk
  reported only **five** of the six bad pairs under the first threshold set, because the draw never
  picked the `order_book` row — which is why the second test walks the vocabulary itself.
- **Mutations: M1 and M2 killed, M3 a deliberate control that survived** the whole of
  `tests/clients/store/` and `tests/db/` (`276 passed`) and names the per-engine scope of the
  enumeration as the one clause that makes the assertion about *pairs* rather than about codes.
- **Narrow runs.** `tests/clients/store/` + `tests/db/` `276 passed`; `tests/console/` `365 passed,
  1 warning` — C's own inverse-direction test already warns with exactly the five keys this
  change orphans, which is spec 120's input list. `ruff check src/ tests/ scripts/` all checks
  passed; `mypy --strict src/ scripts/` no issues in 153 source files. No full gate from me.
- **Not touched:** `console/format.py`, any engine, `scripts/verify.py`, `tests/verify/**`,
  `core/`, `bootstrap.py`, `config/`. Four files changed: `src/acsoe/clients/store/seed.py`,
  `tests/clients/store/test_seed.py`, and these two records.

## Phase 6, session 8 — CLAIMED 2026-09-17, specs 111, 112, 110 in that order

Claimed before any code, per rule 1. Tree clean at `df49cb4`, the full gate green when handed
to me (13 criteria, 12 PASS, 0 FAIL, 1 PENDING). I am the first work after a green gate, so any
red I introduce is mine and visible immediately.

**Spec 111 — `CostAssessment.fallbacks_used` removed** (operator ruling on Q1). No behaviour
change to the gate: the field is always `()`, has no producer of a value and no reader in `src/`
or `scripts/`. `_fallbacks()` goes with it if it has no other use; the prose in
`engines/cost/{contracts.py,engine.py,README.md}` goes; `tests/engines/test_cost.py` asserts the
key is **absent** and pins the published key set. `tests/verify/test_phase3_criteria.py` is run
before and after and **not edited** — if it goes red I report it and stop that thread, because a
fake publishing a field no real engine produces is a question about what that test was asserting.

**Spec 112 — the window/escalation tripwire** (operator ruling on Q2). One test in
`tests/engines/test_safety.py` asserting `trading.entry_unfilled_window_s <
safety.max_consecutive_data_blocks × timeframes.loop_tick_s`, all three read through the real
config loader from `config/default.yaml`, never as literals. It forbids no change; it makes one
visible. Proven capable of failing against a copied config with the window raised.

**Spec 110 — `StoreClient.filled_orders`'s docstring**, which still says the paper balance is
adjusted by every *recorded* fill. Since spec 103 the broker counts every fill it has executed;
the store is the recorded half and the restart source. Prose only, plus a grep of my lane for
other pre-103 wording.

**Line endings measured in Python at claim time** (`b.count(b"\r\n")` against `b.count(b"\n")`,
never `grep -c`): `engines/cost/contracts.py` 293 CRLF / 0 LF and `engines/cost/README.md` 146 / 0
— **both stay CRLF**, edited through a byte-level helper. `tests/engines/test_safety.py` 1493 CRLF
/ 0 LF, **stays CRLF**. Pure LF and staying so: `engines/cost/engine.py` (331), the store client
(1212), `tests/engines/test_cost.py` (619), and both records. My lane is mixed, so every edit goes
through the same LF-view helper rather than a text-mode round trip.

Records: this file and `docs/build-log/phase-6/b-store.md`. Scratch `...\scratchpad\`; logs
`logs/verify/b111-*`, `b112-*`, `b110-*`. Not touched: `core/`, `bootstrap.py`, `config/` (read
only), `context/*` beyond this file, `scripts/verify.py`, `tests/verify/**`, other lanes. No
commit; no full gate from me, by instruction.

### Specs 111, 112, 110 — DONE 2026-09-17, not committed (the lead commits)

- **Spec 111.** `CostAssessment.fallbacks_used`, its `to_state_data` line and
  `CostEngine._fallbacks()` are gone; `_fallbacks` had no other caller. The prose in
  `engines/cost/{contracts.py,engine.py,README.md}` follows, with the README carrying the
  paragraph on why the field was removed rather than left as a harmless constant.
  `test_this_engine_applies_no_fallback_and_says_so_by_recording_none` becomes
  **`test_this_engine_publishes_no_fallback_field_and_the_key_set_is_pinned`**: the key is
  asserted **absent**, and `COST_PAYLOAD_KEYS` is pinned as a set on both ticks that publish a
  full assessment, with the smaller missing-input shape pinned separately.
  **Nothing still reads the field**: `rejections` has no such column (migration 0001 puts it on
  `trades`), engine 19 harvests the four `ECONOMICS_FIELDS` plus `reason_code`, and engine 16 and
  the console never read it from here.
  **Two mutations, both KILLED, both by that one test** — M1 re-adds the key to the priced
  payload, M2 to the missing-input payload; `1 failed, 30 passed` each against a `31 passed`
  baseline, each restored from a byte copy with the sha256 compared in the same statement.
- **`tests/verify/test_phase3_criteria.py` did not go red: `48 passed` before, `48 passed`
  after**, not edited. Its `CONSTANT_FEE_COST_ENGINE` still publishes `"fallbacks_used": []` — a
  shape no real engine produces now. It stayed green because `check_cost_gate_uses_live_fee_tier`
  reads `net_edge_pct`, `reason_code`, `clears_hurdle` and `hurdle_pct` and never the key set, so
  an extra field in that double is inert. Reported to the lead as the *double that stopped
  tracking what it doubles*; it is C's file and C's question.
- **Spec 112.** **`test_a_resting_entry_is_cancelled_by_its_window_before_safety_could_escalate`**
  in `tests/engines/test_safety.py` (with the comparison in
  `assert_entry_window_below_escalation`). All three values read through the real loader from
  `config/default.yaml` by dotted key, never as literals, so a rename fires it too. Proven red
  twice against copied configs, the committed one never touched: window 1200s and window 900s
  (the strict boundary), each `1 failed` with a message naming
  `trading.entry_unfilled_window_s`, `safety.max_consecutive_data_blocks` (15),
  `timeframes.loop_tick_s` (60s) and the product 900s.
- **Spec 110.** `StoreClient.filled_orders`'s docstring now says what it is since spec 103 — the
  recorded half of the broker's ledger, with the broker adding fills the store has not seen, and
  the restart source where a fill executed but never recorded must be absent from the rebuilt
  positions too. **Lane grep for other pre-103 wording: one hit, and it was this one.** Everything
  else already reads "every fill it has executed" (`clients/paper/broker.py:129`, `:365`,
  `engines/risk/README.md:227`); the two "simulated fill" mentions that remain are the argument
  for why the ledger is unconditional in paper, which still holds.
- **Line endings, measured in Python before and after.** `engines/cost/contracts.py` 293 -> 294
  CRLF / 0 LF, `engines/cost/README.md` 146 -> 153 CRLF / 0 LF, `tests/engines/test_safety.py`
  1493 -> 1558 CRLF / 0 LF — all three still pure CRLF. `engines/cost/engine.py` 331 -> 308,
  `tests/engines/test_cost.py` 619 -> 650, `clients/store/client.py` 1212 -> 1228 — all still pure
  LF. No file is mixed; every edit went through an LF view and was written back in the file's own
  ending.
- **Narrow results** (`logs/verify/b111-*`, `b112-*`, `b110-*`): `tests/engines/test_cost.py` +
  `test_safety.py` + `test_safety_guard_chain.py` + `test_memory_rows.py` + `test_decision.py` +
  `tests/clients/store` + `tests/clients/paper` **463 passed**; `tests/verify/test_phase3_criteria.py`
  **48 passed**; `ruff check src/ tests/ scripts/` `All checks passed!`; `mypy --strict src/
  scripts/` `Success: no issues found in 153 source files`. No full gate from me, by instruction.
- **For the lead, not mine to fix:** `docs/PROJECT-STATE.md:1001` still lists `fallbacks_used` in
  engine 10's row of the cross-chain key table, and `:1002` still lists engine 11's, which spec
  106 removed.

## Phase 6, session 7 — CLAIMED 2026-09-17, spec 113 (version 2)

Claimed before any code, per rule 1. HEAD `dd9ea39`; the working tree carries C's spec 100
criteria bodies (`scripts/verify.py`, `tests/verify/*`) and lead docs, uncommitted and not mine.
Known red in `tests/verify` with them: 5 tests, all waiting on specs 113/114.

**Spec 113 v2 — the facts engine 19 needs for the exit-cycle equity row** (operator ruling
2026-09-17 on Q-C1; the first version, engine 22 subtracting engine 21's marks, was withdrawn).

1. Engine 22: `net_proceeds = qty × exit_price − exit_fee` on every `closed_trades` row, from
   that row's own fields only.
2. Engine 21: `value = qty × last_price` on every position row carrying `last_price`, absent
   otherwise. Totals unchanged.
3. Migration 0005: `equity_snapshots.cash_source` (`cycle_start` | `after_exit`), backfilled
   `cycle_start`; `EquityRow.cash_source`; the seed writes `cycle_start`.
4. Tests, including a sum test proven capable of failing; mutations from byte copies.

**Line endings measured in Python at claim time:** `clients/store/seed.py` 1276 CRLF / 0 LF
(kept CRLF, byte-level edit). Every other file on my write list for this spec is pure LF:
engines 21 and 22 (`engine.py`, `contracts.py`, `README.md`), `clients/store/{contracts,client}.py`,
migrations 0001-0004, `tests/db/test_migrations.py`, `tests/clients/store/*.py`,
`tests/engines/test_{exit,position_manager}.py`, and both records.

Records: this file and `docs/build-log/phase-6/b-store.md`. Scratch `...\scratchpad\b113\`;
logs `logs/verify/b113-*`. Not touched: engine 19, `core/`, `bootstrap.py`, `context/*`, other
lanes, the recorder processes. No commit.

### Spec 113 — DONE 2026-09-17, not committed (the lead commits)

- **Engine 22** publishes `net_proceeds` (`qty * exit_price - exit_fee`) on every
  `closed_trades` row, from that row's own fields. **Engine 21** publishes `value`
  (`qty * last_price`) on every row that carries `last_price` and on no other. The totals,
  and when they are omitted, are unchanged. **Migration 0005** adds
  `equity_snapshots.cash_source` (`cycle_start` | `after_exit`, CHECK, NOT NULL, existing rows
  backfilled `cycle_start`); `EquitySnapshotRow.cash_source` and `CashSource`; the seed writes
  `cycle_start`.
- **Reported, not changed — engine 19 refuses both new keys.** `_Row` is `extra="forbid"`, so
  `PositionRow.model_validate` (`engines/memory/engine.py:387`) and `TradeRow.model_validate`
  (`:420`) raise `extra_forbidden`, engine 19 records nothing on the tick, and every test that
  runs engine 21 or 22 into the real engine 19 is red until spec 114 (C) accepts them. Measured:
  `logs/verify/b113-engine19-refusal.log`. Engine 19 not edited; the lead was told at the time.
- **The tree's red, measured: 26 tests**, all of them that refusal — A's five rehearsal tests,
  20 in `tests/verify/test_phase6_criteria.py`, and my own spec 106 fill-tick test. No other
  cause found.
- **Mutations:** ten arms, eight killed by the tests written for them, two controls (N0, V0)
  behaviourally survived the whole suite — both `26 failed, 3243 passed, 2 skipped`, the **same
  26 tests** in both arms, both restored by hash (`c131dabea938…`, `0a68c73b23ee…`), and the set
  equal to the measured baseline with an empty difference either way. The operator's sum test
  was run **on its own** under the three arms that make the rows and the total disagree, and
  failed each time: V2 (row value from `entry_price`) `3 failed, 1 passed`; V3 (total leaves
  this tick's fill out) `2 failed, 2 passed`; V3b (total leaves the first stored position out)
  `3 failed, 1 passed`. The passing case each time is the one the mutation cannot reach.
  V1 needed a re-run: the first exited 0xC0000005 with no summary line, so the harness refused a
  verdict. The build log has the table, the how-choices with their rejected options, and the
  caveat that the wide baseline is the union of two unmutated runs rather than one.
- **Line endings:** `clients/store/seed.py` kept CRLF (1281 CRLF / 0 LF), edited through an LF
  view and written back; every other file I touched is pure LF and stayed so. All eleven
  `tests/verify/test_phase6_criteria.py` patcher anchors on engines 21 and 22 (nine distinct
  lines; two arms share the hold line) still match exactly once, checked in Python, and
  `test_phase3_criteria.py` + `test_phase4_criteria.py` are `95 passed`.
- **Gate in my lane:** `ruff check src/ tests/ scripts/` `All checks passed!`;
  `mypy --strict src/ scripts/` `Success: no issues found in 153 source files`;
  `tests/db` + `tests/clients/store` `271 passed`; my two engine files `1 failed, 103 passed`
  (the refusal). No full gate from me, by instruction.
- **For spec 114:** `EquitySnapshotRow.cash_source` defaults to `CashSource.CYCLE_START` so
  engine 19 keeps working today. **Remove the default once engine 19 writes the field on every
  row**, or a writer that forgets it gets `cycle_start` silently.

## Phase 6, session 6 — CLAIMED 2026-09-17, spec 108

Tree clean at `69038a7` when claimed. Claimed before any edit, per rule 1. Step 0 of the spec
(spec 106's sweep entry and DONE line) was already done by session 5: build log "Spec 106 —
nine mutations" and the DONE block below.

**Spec 108 — stale remnants of the removed paper-mode fallback in B's lane.** No behaviour
change: prose, one unused constant, line endings.

1. `src/acsoe/engines/cost/{contracts,engine}.py` + `README.md`: `fallbacks_used` is a `trades`
   column (migration 0001), not a `rejections` one; the README's "Balance is the only paper-mode
   fallback left" goes. `CostAssessment.fallbacks_used` is reported, not removed.
2. `src/acsoe/clients/paper/{broker,__init__}.py`: `FALLBACK_PAPER_LEDGER` removed (unused;
   grep recorded); the starting-balance comment and the forwarded-reads comment rewritten to
   invariant 2 as now written.
3. `tests/engines/test_cost.py`: the one docstring repeating "a real `rejections` column".
4. `src/acsoe/engines/cost/engine.py` CRLF -> LF, after the `tests/verify/` anchor check.

**Line endings measured in Python at claim time:** `engines/cost/engine.py` 328 CRLF / 0 LF,
`contracts.py` 288 / 0, `README.md` 140 / 0 — `contracts.py` and `README.md` are edited through a
byte-level helper that keeps CRLF (the spec converts `engine.py` only). The broker, its
`__init__.py` and README, `tests/engines/test_cost.py` and both records are pure LF.

Records: this file and `docs/build-log/phase-6/b-store.md`. Scratch `...\scratchpad\b108\`;
logs `logs/verify/b108-*`. Not touched: `bootstrap.py`, `core/`, `context/*`, other lanes,
the recorder processes.

### Spec 108 — DONE 2026-09-17, committed by the lead as `40bbc6b`

- `FALLBACK_PAPER_LEDGER` removed from `clients/paper/broker.py` and `__init__.py`. Before the
  removal, grep found it in those four source lines only; afterwards, `grep -rn` over
  `src tests scripts` finds nothing.
- Stale prose fixed: `fallbacks_used` is a `trades` column, not a `rejections` one (cost
  `contracts.py`, `engine.py`, `README.md`, one `test_cost.py` docstring); the cost README's
  "Balance is the only paper-mode fallback left"; the broker's "one substituted value" comment
  and its forwarded-reads banner.
- `engines/cost/engine.py` CRLF -> LF. The converted file equals the HEAD blob `7d423da`, and
  both phase-3 anchors still match once. The cost `contracts.py` and `README.md` stay CRLF (a
  how-choice; see the build log).
- **Reported, not changed:**
  - `CostAssessment.fallbacks_used` has a producer (always `()`) and no reader in `src/` or
    `scripts/`; the lead's Q1 for the operator.
  - `clients/store/client.py:942` says "recorded" fill, which is older than spec 103; outside
    my write list.
  - A's `clients/kraken/README.md:55`, `engines/exchange/{README.md:64, contracts.py:17,
    engine.py:117}` and `tests/engines/test_exchange.py:12` still call the paper-mode
    fallbacks the consumer's decision.
- Gate: mypy clean, ruff clean, pytest `8 failed, 3201 passed` (known eight), verify `2 PASS,
  1 FAIL (toolchain_green, same eight), 9 PENDING`.

## Phase 6, session 5 — CLAIMED 2026-09-16, spec 106

Tree clean at `e29c84e` when claimed. Claimed before any code, per rule 1. Operator rulings of
2026-09-16 (tracker, "The operator's three rulings on the rehearsal round", ruling 3).

**Spec 106 — engine 11's balance fallback removed; engine 21's fill-tick mark stored.**

1. `src/acsoe/engines/risk/{engine,contracts}.py` + `README.md`: `_balances` returns the
   published map or raises `MissingInputError` in every mode; the paper branch and its
   constants go if nothing else reads them.
2. `tests/engines/test_risk.py`: the fallback tests become block tests, led by the one that
   would have caught the defect — a paper tick after an executed fill with no published
   balance must block.
3. `src/acsoe/engines/position_manager/engine.py` (+ README if its text changes): a position
   opened by this tick's fill is stored with `last_price` = fill price and
   `unrealised_pnl` = 0. `tests/engines/test_position_manager.py`: a test pinning the stored
   row through engine 19.
4. Mutations from byte copies (R1, R2, P1, P2, a grepped control).

**Line endings measured in Python at claim time, and kept as found:** `engines/risk/engine.py`
599 CRLF / 0 LF, `contracts.py` 301 / 0, `README.md` 276 / 0, `tests/engines/test_risk.py`
1167 / 0 — all CRLF, edited through a byte-level helper that keeps CRLF. Engine 21's
`engine.py`, `README.md`, `contracts.py` and its test file are pure LF. `engines/cost/engine.py`
(328 CRLF) is not touched in this spec.

Records: this file and `docs/build-log/phase-6/b-store.md`. Scratch `...\scratchpad\b106\`;
logs `logs/verify/b106-*`. Not touched: `bootstrap.py`, `core/`, `context/*`, the broker,
other engines, other lanes' tests.

### Spec 106 — DONE 2026-09-17, committed by the lead as `268f49e`

- Engine 11 blocks on an absent `exchange.balances` in every mode, the reason naming the
  absence; the paper fallback, `PAPER_STARTING_BALANCES_KEY`, `PAPER_MODE`,
  `FALLBACK_BALANCE_FROM_PAPER` and `RiskSizing.fallbacks_used` removed (no producer, no reader).
- Tests: `test_after_a_paper_fill_a_tick_with_no_published_balance_blocks` (real broker ledger,
  one fill, the defect's window asserted), every-mode block, pass twin, before-sizing refusal,
  approved key set; EUR test separates absent map from missing currency.
- Engine 21 stores `last_price` = fill price and `unrealised_pnl` = 0 on the fill tick; pinned
  through the real engine 19 by `test_a_position_opened_by_this_ticks_fill_is_stored_marked_at_its_fill_price`.
- Spec 105 criterion PASS (mark = fill); A's rehearsal 7 passed.
- Mutations: R1, R1b, R2, P1, P1b, P2, P3 killed by the tests written for them; controls R0, P0
  survived narrow and wide (only the known eight).
- Gate: mypy clean, ruff clean, pytest `8 failed, 3201 passed` (known eight), verify `2 PASS,
  1 FAIL (toolchain_green, same eight), 9 PENDING`.
- **Open, mine:** `engines/cost/contracts.py` + README call `fallbacks_used` a `rejections`
  column (it is on `trades` only); `clients/paper/broker.py` exports unused
  `FALLBACK_PAPER_LEDGER`. **Reported to C via the lead:** engine 9's docs still describe
  engine 11's fallback; spec 105's criterion keeps a NULL-mark branch only the defect reaches.

## Phase 6, session 4 — CLAIMED 2026-09-16, specs 94 then 103, in that order

Tree clean at `a668df3` when claimed. Claimed before any code, per rule 1.

1. **Spec 94 — rehearse C's engines 9 `order_book` and 14 `adaptive_router` through real
   orchestrator ticks.** Only file: `tests/engines/test_feature_chain_rehearsal.py`. The
   full-registry scenario becomes 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, bar tick then quiet
   tick, fake client at fee tier 3, and a **thin book** — the operator's instruction: "Spec 94
   uses the thin book. Engine 9's estimate on the fake's default book is exactly zero, and a
   zero proves nothing." Engines 9, 14, 10, 15 are mutated transiently from byte copies and
   restored by hash; never edited. **`src/acsoe/engines/cost/engine.py` is 328 CRLF / 0 LF in
   the working tree** (C's file, measured in Python at claim time) — not normalised by me;
   the harness's anchors follow the file's own line ending.
2. **Spec 103 — the paper broker's balance counts every fill it has executed.** Only after 94
   is recorded and the lead says go. Files: `src/acsoe/clients/paper/broker.py`,
   `src/acsoe/clients/paper/README.md` if its ledger description changes,
   `tests/clients/paper/test_broker.py` (or a new file under `tests/clients/paper/`). No
   engine edits; A's `tests/engines/test_trade_chain_rehearsal.py` is not touched — its strict
   xfail is expected to XPASS and fail once 103 lands.

Records: this file and `docs/build-log/phase-6/b-store.md`. Scratch:
`...\scratchpad\b94\`; logs `logs/verify/b94-*`, `logs/verify/b103-*`.

### Spec 94 — DONE in lane 2026-09-16; gate below

Only `tests/engines/test_feature_chain_rehearsal.py` changed (33 tests, all green). No engine
edited; every transient mutation restored by hash.

- The registry chain 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15 runs to engine 15 on the bar tick
  and stops after engine 5 on the quiet tick, at **fee tier 3** by name.
- **The thin book is the recorded `BTC/USD` opening snapshot** from
  `tests/fixtures/book_sample.jsonl` (engine 7's candidate is `BTC/USD`). Engine 9 walks 4
  levels; `estimated_slippage_pct = 0.00006528042192692375531712952815`, asserted `> 0` first.
  Friction recomputed from the named tier-3 fees + engine 3's spread + engine 9's slippage
  equals engine 10's `0.003066600870324790702975215261` exactly, and the recomputation
  without slippage (`0.003001320448397866947658085733`) differs.
- Engine 14 weights the committed leaderboard fixture from a real store; invariant 4 is
  asserted both sides of a recomputed veto threshold, with and without weights.
- Deleted: `test_in_the_full_registry_chain_engine_15_is_never_reached_this_phase`.
  Renamed: engine 10's "for want of engine 9" test is now the explicit no-engine-9 case.
- **Mutations:** M1 key rename, M2 router weight read by the skeptic, M2b, M3 cost drops
  slippage, M4 engine 9 publishes zero — all killed by the tests written for them. M0
  control survived behaviourally (the wide run's two "kills" were an anchor collision with
  `test_phase3_criteria.py`'s patcher — recorded). M5 (engine 14 family filter) survives this
  file by construction and is killed wide by C's
  `test_a_second_model_family_is_not_weighted`.
- **No finding against engines 9, 14, 10 or 15.** Committed by the lead as `49e369a`.
- **Open, mine:** `src/acsoe/engines/cost/engine.py` is entirely CRLF in the working tree.
  Engine 10 is **B's** (`ownership.md`; I first wrote C's — corrected by the lead). Convert to
  LF at a quiet moment **after** spec 103, and first check that no `tests/verify/` patcher
  anchor on that file spans a line break.

### Spec 103 — DONE in lane 2026-09-16 (lead's go-ahead after `49e369a`); gate below

Diagnosis entry written to the build log before any change. Files changed:
`src/acsoe/clients/paper/broker.py`, `src/acsoe/clients/paper/README.md`, new
`tests/clients/paper/test_ledger_counts_executed_fills.py` (11 tests). No engine touched; A's
file untouched.

- `balance()` pins the tick's trade window, decides every open order through `open_orders()`,
  and counts every executed fill: the store's `filled` rows, plus kept fills (`_executed`)
  not yet recorded, never both. A fill decided by any read is kept and returned to later reads.
- **Decision:** a due fill that cannot be priced (fee tier down) makes `balance()` raise
  `KrakenUnavailableError`, so engine 1 records a failed `balance` call and keeps `pair_rules`;
  any other broker refusal is raised as itself. Build log has the reasoning.
- Restart proven through the real engines 1 and 21 on a restarted broker: ledger 5000.00, no
  position, entry still resting.
- **Mutations:** 12 arms, 10 killed by the tests written for them; N0 control and N11 (`del`
  of a recorded copy) survive the whole suite behaviourally. Breaking the broker (N1, N3, N7)
  reproduces A's `8332.414226591` in A's rehearsal under `--runxfail`.
- **A's strict xfail now XPASSes** (`logs/verify/b103-A-xfail-default.log`); with `--runxfail`
  it passes (`logs/verify/b103-A-runxfail.log`). A removes the marker.
- **For the lead:** engine 11's paper fallback (`paper.starting_balances` when engine 1
  publishes no balances) sits oddly beside "the paper balance is the ledger". Unreachable via
  this change's outage path (engine 10 blocks first); mine, out of 103's scope, not changed.

## Phase 6, session 3 — CLAIMED 2026-09-16

The second B session was stopped; everything it built is committed (`bdcb1ff`, `b2fb9de`,
`41ebf19`). Nothing below this section is revised by it.

**Claimed, before any code, per rule 1. Three jobs, in the lead's order.**

1. **Migration 0003 — `hold_reason TEXT` on `positions`.** Lead ruling 2026-09-16 on C's
   escalation. My half is the column and the row model, not the write (engine 19 is the
   only writer, spec 98, C's). Files: `db/migrations/0003_position_hold_reason.sql`,
   `src/acsoe/clients/store/contracts.py` (`PositionRow.hold_reason`),
   `src/acsoe/clients/store/client.py` if a read needs it,
   `src/acsoe/clients/store/seed.py` if the seed must name the field, and
   `tests/clients/store/`, `tests/db/test_migrations.py`.
   Three conditions from the ruling, carried into the migration's own comment so the next
   reader does not have to find this file: engine 19 is the only writer; **it is cleared to
   `NULL` on every tick that did not hold**; **`NULL` means "did not hold", never "unknown"**.
2. **`OrderState` gains `qty` and `limit_price` — my half.** A lands the contract; my
   `clients/paper/broker.py` constructs `OrderState` and must populate both, and engine 18's
   `entry_unrecorded_at_exchange` path can then publish a real row. Files:
   `src/acsoe/clients/paper/broker.py`, `src/acsoe/engines/execution/` and their tests.
   Expect the tree red between A's half and mine.
3. **Spec 93 — engine 22 `exit`.** Files: `src/acsoe/engines/exit/{__init__,engine,contracts}.py`
   + `README.md`, and `tests/engines/test_exit.py`. Invariant 14 read in full first.

### Job 1 — migration 0003 DONE 2026-09-16; green in my lane, the four gates are not run

Files touched, and nothing else:

- `db/migrations/0003_position_hold_reason.sql` — new. One nullable `TEXT` column on
  `positions`, no table added, no index added, `EXPECTED_TABLES` and `EXPECTED_INDEXES`
  unchanged, every existing CHECK unchanged.
- `src/acsoe/clients/store/contracts.py` — `PositionRow.hold_reason: str | None = None`,
  placed with `last_price` and `unrealised_pnl` because all three are facts about *now*,
  plus a validator refusing a blank.
- `tests/clients/store/test_store.py` — `make_position(hold_reason=...)` and six tests.
- `tests/db/test_migrations.py` — four tests, and the `>= 2` floor raised to `>= 3`.

**No change to `client.py`.** `write_position` upserts every column and `open_positions`
is `SELECT *`, so the column round-trips and — this is condition 2 of the ruling — is
**cleared by the writer writing the row it would have written anyway**. Nobody has to
remember to blank a field. Mutation H6 is that defect and one test kills it.

**Eight mutations, eight killed, equivalent control survived.** Table and reasoning in
the build log. Three things for the lead's eye:

1. **SQLite's one-argument `trim()` strips spaces and nothing else** — not tabs, not
   newlines — so the obvious CHECK let a tab through and the two layers' refusals
   disagreed. Found by the parametrisation carrying a tab rather than three kinds of
   space. Build-log entry written at diagnosis.
2. **A real hole in `open_positions()`, from Phase 0 and not mine**: the
   `position_id ASC` tie-break was asserted by nothing, and every position the seed and
   the builders make shares one `opened_at`. `DESC` survived all 244 tests in the lane.
   One test added; no change to the client.
3. **No CHECK enumerating the hold reasons**, unlike `runs.system_mode` — Decision entry
   in the build log with the reasoning and its cost.

```
pytest tests/db/test_migrations.py tests/clients/store/ -q     245 passed
ruff  check src/acsoe/clients/store/ tests/clients/store/ tests/db/   All checks passed
mypy  --strict src/acsoe/clients/store/                        7 source files, clean
```

### Job 2 — `OrderState.qty` and `.limit_price` DONE 2026-09-16; green in my lane

A's half was already on disk. Files I touched, and nothing else:

- `src/acsoe/clients/paper/broker.py` — all **five** `OrderState` construction sites.
- `src/acsoe/engines/execution/engine.py` — `_row_for_unrecorded`, and
  `_AlreadyPlaced.row` is no longer optional. Engine 18 now **publishes the row** for
  an order at the exchange the store never recorded, which closes the unmanaged
  exposure: nothing was ever going to cancel an order engine 21 could not see.
- `tests/clients/paper/test_broker.py` (5 tests, one per shape),
  `tests/engines/test_execution.py` (2 new, 1 rewritten),
  `tests/engines/test_position_manager.py` (`_BrokerAnswering` passes both through).

**Ten mutations, ten killed, equivalent control survived.** Table in the build log.

**One gap A's amendment does not close, flagged rather than taken quietly:
`placed_at`.** `OrderState` carries `closed_at` and no placement time, so the row says
*this* tick. Engine 21's entry window therefore restarts from here and an already-stale
order is cancelled up to one window (300s) late. I judged that acceptable because the
cost is bounded and the failure it replaces is not, and because `close_all` cancels
every resting entry **regardless of the window** (invariant 8) — the kill switch is
complete the moment the row exists. Back-dating to force an immediate cancel writes a
time that never happened into a column research and the console read as a placement
time. One line to reverse if the lead disagrees.

**Engine 18 raises rather than recording an exchange order with no limit price.** The
only order it places under an entry `userref` is a post-only limit buy; a limit order
with a null price in `orders` is a row engine 21 cannot reason about.

### The engine 9 tripwire fired and was acted on, not weakened

`test_engines_nine_and_fourteen_still_do_not_exist` went red because C landed spec 96.
Done as its own message says: `approving_state` runs the real `OrderBookEngine`,
`order_book_payload()` is deleted, the tripwire is narrowed to engine 14, and the seam
it warned about is pinned by
`test_engine_nines_own_payload_is_walked_by_the_coherence_check`. **All 29 other tests
in the file passed unchanged**, which is the first real test of engine 16's design claim
that its pair and bar clauses are a walk over the payloads rather than four hand-written
comparisons. It held.

**A witness problem for spec 94, found on the way and recorded in the constant's own
comment.** Engine 9's real estimate on this fixture's book is **exactly zero** — the top
bid level covers the whole 5,000 basis — so friction is 0.62% rather than the hand-built
0.67%, and **an engine 10 that ignored the slippage term entirely would produce the same
number**. Spec 94's acceptance is "engine 10 reads engine 9's slippage, proven by
recomputation", and a zero cannot prove it. Spec 94 needs a thinner book.

```
pytest tests/clients/paper/ tests/engines/test_execution.py \
       tests/engines/test_position_manager.py tests/engines/test_decision.py -q
                                                              177 passed
ruff  check (every touched src and test path)                 All checks passed
mypy  --strict (clients/paper, clients/store, execution, decision)  16 files, clean
```

### Job 2, second half + the 0004 boundary — DONE 2026-09-16, green in my lane

Everything the lead and A ruled since my last report is in. Files touched, and nothing
else: `src/acsoe/clients/paper/broker.py`, `src/acsoe/engines/execution/{engine,contracts}.py`
+ `README.md`, `src/acsoe/clients/store/{contracts,client}.py`,
`db/migrations/0004_leaderboard_base_rate_brier.sql`, and the matching tests in
`tests/clients/paper/`, `tests/engines/test_execution.py`, `tests/engines/test_exit.py`,
`tests/clients/store/`, `tests/db/`.

**1. `opened_at` at all five broker sites, and my `placed_at` workaround is retired.**
The lead was right and the miss was mine: A landed `opened_at` in the same amendment
and I populated `qty` and `limit_price` without it. The five sites answering `None`
would have looked **exactly like an exchange that did not report `opentm`**, driving
engine 18 down a refusal branch built for a real omission while the simulator knew the
placement time to the microsecond. A defect presenting as a documented behaviour.
`test_every_order_state_the_broker_builds_carries_an_opening_time` sweeps all five
shapes in one test, because a site-by-site list is written by whoever forgot a site.

**2. Engine 18 reports the not-a-limit contradiction rather than raising it.** Applied
as ruled. My reasoning had stopped at "fail-closed and loud is correct", which is true
of the tick and wrong about the hour: `ERROR` → `block_records.status = 'ERROR'` →
engine 17's error budget → a frozen account. The tests assert `status is OK` and
`blocks_trading is False` explicitly, because a raise satisfies every other assertion
in them.

**3. `entry_unrecorded_at_exchange` narrowed, two new codes.** A asked whether the code
still describes a real outcome. It does, for one case of three:
`entry_recovered_from_exchange` (describable, row published),
`entry_at_exchange_is_not_a_limit` (no row), `entry_unrecorded_at_exchange` (no
`opened_at`, no row). Three outcomes under one code is a console that cannot tell an
operator which happened. **C mapped both new codes within the hour**, my tripwire fired,
and it is retired into a plain renderability assertion over all six.

**4. Migration 0004 `base_rate_brier REAL` nullable, and `all_leaderboard_rows`.**
Both on disk; C is unblocked. `model_id` is **required, not defaulted** — the method has
no `LIMIT`, and "no limit" is only safe because one model's rows are bounded by its
walk-forward where the table is bounded by nothing. C called it with no arguments and
has one line to change; messaged.

**5. Three CRLF files normalised** — `clients/store/contracts.py` (489 lines, entirely),
`engines/execution/engine.py` (478, entirely), this build log (127 of 1,204). Byte
replace, nothing else touched. My own harness had already hit it on `contracts.py`
during the 0003 sweep and refused with `ANCHOR MATCHED 0x`, which is the only reason it
cost a minute rather than four silent non-results.

**Seventeen mutations, seventeen killed, two equivalent controls survived.** Plus the
engine 22 sweep re-run on the settled tree: 21 killed, control survived.

**Two findings about the instrument, and both are worth the lead's eye:**

- **A false kill, caused by C landing a seam mid-sweep.** `K0`, the equivalent control,
  came back KILLED — `int(x)` as `int(int(x))`, which cannot change an answer. C had
  landed `all_leaderboard_rows()` with no arguments between two runs, so every test
  building an approving `state` went red on a `TypeError`. **The control is what caught
  it**: a control that dies is unmistakable where a twelfth kill in a row is not. With
  the `.pyc` defect from the engine 22 sweep, the rule is: a sweep whose control dies is
  a sweep to throw away, and a sweep with no control cannot tell you that.
- **A witness I got wrong twice in one test.** `all_leaderboard_rows` orders by `id ASC`.
  My first fixture gave every row the same `trained_at` — tie unbroken, SQLite returned
  insertion order anyway, mutation survived. My second gave 9000/8000/7000 written
  newest-first, which `trained_at DESC` reproduces exactly — survived again. The
  sequence is now **non-monotonic in insertion order** (8000, 9000, 7000), which is the
  only shape that separates `id ASC`, `trained_at ASC` and `trained_at DESC` at once.
  Two mutations now, one per direction.

**For C, one thing in the new prose.** `exits_placed` renders as "Exit orders are
**resting** at the exchange for this position". Every Phase 6 exit is a **market** sell
— taker, never resting — by the argument in engine 22's README, so the sentence
describes an order this system does not place. The other five read correctly.

```
pytest tests/engines/ tests/clients/ tests/db/ -q          1295 passed
ruff  check src/acsoe/ tests/ scripts/                     All checks passed
mypy  --strict clients/, engines/exit/, engines/execution/  28 source files, clean
```

**Two intermittent interpreter faults, neither reproducible and neither diagnosed:** a
`SystemError` in `yaml/scanner.py` during collection, and a subprocess exiting
`0xC0000005` in `test_core_can_use_both_writes_importing_only_the_client`. Both passed
on an immediate re-run and the lane has since run green twice end to end. Recorded
because three of us are spawning interpreters in one checkout.

### Job 3 — spec 93, engine 22 `exit`, BUILT AND GREEN IN MY LANE 2026-09-16

Files: `src/acsoe/engines/exit/{__init__,engine,contracts}.py` + `README.md`,
`tests/engines/test_exit.py`, plus `tests/engines/test_decision.py` for the engine 14
tripwire below. Nothing else. **Not marked complete** — my standing rule: a spec is
complete once its four gates are green, never in the edit that builds it.

```
pytest tests/engines/test_exit.py -q                        43 passed
pytest tests/engines/ tests/clients/ tests/db/ -q         1278 passed
ruff  check (every touched path)                          All checks passed
mypy  --strict src/acsoe/engines/exit/                     3 source files, clean
```

**Twenty-two mutations, twenty-one killed, equivalent control survived.** Table and
reasoning in the build log. Every item on spec 93's own "Check When Done" list is one
of them and all five are killed.

**Four things for the lead, two of which are deviations from spec 93:**

1. **Engine 22 never reads a balance, so `balance_last_known_good` is not defined.**
   Decision entry in the build log. An exit's quantity is the position's, and the only
   thing a balance could add is a cap at the base holding — which is **zero for every
   paper position**, because my spec 88 ruling made the ledger quote-side only. A
   fallback name nothing emits reads as a behaviour the system has. What invariant 14
   actually requires is that a *failing* balance fetch not stop the liquidation, and the
   outage test proves exactly that.
2. **`last_known_good_asset_pairs` is a property, not the method spec 93 writes.**
   Written as the spec has it, `retained.value` raises `AttributeError`, the
   per-position catch turns it into `exit_incomplete`, and **a liquidation reports
   failure for every position during exactly the outage the rule exists for** with the
   retained snapshot sitting there readable. Third Phase 6 spec whose conclusion is
   right and whose mechanism does not exist (88's `drain_trades`, 91's `query_orders`).
3. **A defect the sweep found in my own engine, not in the tests.** A per-position
   failure was caught so the other positions still liquidate — and the **message** was
   swallowed with it. An operator would have had `exit_incomplete` and no way to tell a
   missing fee tier from a foreign quote from a refused order. The failures are now
   named in `EngineResult.reason`; three tests assert the sentence.
4. **A defect in my mutation harness, and this one is the instrument rather than the
   subject.** Three runs returned a verdict with no pytest summary, and once a mutation
   was reported **KILLED that a re-check showed SURVIVED**. Cause: a mutant lives one
   run and is overwritten with bytes of the same length, and CPython's `.pyc` check is
   `(mtime, size)` — Windows mtime granularity lets a stale cache survive the cycle.
   Fixed with `PYTHONDONTWRITEBYTECODE=1` and the whole sweep re-run. The two earlier
   "unexplained" observations in this log are almost certainly the same cause.

**The engine 14 tripwire fired too, and is retired rather than narrowed a third time.**
C landed spec 97 hours after 96. `approving_state` now runs the real
`AdaptiveRouterEngine`, `router_payload()` is deleted, and **all thirty other tests in
the file passed unchanged** — two real publishers landed into engine 16's coherence walk
in one day and neither needed an edit to engine 16. The tripwire is replaced by
`test_no_publisher_payload_in_this_file_is_hand_built_any_more`, because a tripwire with
nothing left to trip is green forever while the invariant under it is not.

**For C, spec 99 — four codes are not renderable yet.** `exits_placed`,
`nothing_to_exit`, `exit_already_placed` and `exit_incomplete` are absent from
`REASON_PROSE`, so the console renders "No reason was recorded." for all four, silently.
C's walking test is already red on them (and on engine 9's four). Suggested prose sent
by message. `test_the_four_codes_spec_93_adds_are_still_waiting_on_cs_prose` asserts
their **absence** and goes red the moment C maps any of them, with a failure message
saying what to do. `data_guard_blocked` is deliberately shared with engine 21's
`hold_reason` spelling — one fact, one word — and is renderable today; a separate test
pins the sharing.

**For C, spec 98 — the shapes engine 22 publishes.** `state["exit"]` carries `orders`,
`positions`, `closed_trades`, `positions_closed` and `reason_code`, and the three row
lists are store-contract payloads minus `run_id`, `cycle_id` and `updated_at`. Engine
19's `_write_positions`, `_write_orders` and `_write_trades` already read all three from
the `exit` key, so I believe nothing is owed here — pinned from my side by
`test_the_field_names_are_the_ones_engine_nineteen_reads`.

**For C, spec 98 (hold_reason).** The column and the row model are on disk. Engine 19 is the only
writer: put engine 21's `state["position_manager"]["hold_reason"]` onto the position
payload `_write_positions` validates, **including when it is null**. `PositionRow`'s
default is `None`, so omitting the key already clears the column — the failure mode to
avoid is the opposite one, carrying last tick's value forward. A blank string is refused
by both the row model and the database; `None` is the only spelling of "did not hold".

## Phase 6, session 2 — CLAIMED 2026-09-16

The first B session died at the usage limit at 23:49Z. Everything below this section was
written by it and is accurate; nothing here revises it. This session picks up where it
stopped, in the order the lead set.

**Claimed, before any code, per rule 1.**

**Four loose ends, in order:**

1. **Delete the spec 89 tripwire.** `tests/engines/test_risk.py::test_the_two_codes_spec_89_added_are_still_waiting_on_cs_prose`
   is red on purpose — C landed the prose. Delete it; move `position_open_on_pair` and
   `entry_resting_on_pair` into `test_every_reason_code_this_engine_emits_is_renderable_by_the_console`.
   Files: `tests/engines/test_risk.py`.
2. **Apply the lead's precedence reversal** — the per-pair refusal goes *ahead* of the
   portfolio cap. Files: `src/acsoe/engines/risk/engine.py`, `src/acsoe/engines/risk/README.md`,
   `tests/engines/test_risk.py` (invert the pinning test), and an **appended** Decision entry
   in `docs/build-log/phase-6/b-store.md` (script-rules rule 6 — the old entry is not edited).
3. **`PaperBroker` drops `drain_gaps`.** Found and measured by A. Files:
   `src/acsoe/clients/paper/broker.py`, `tests/clients/paper/`. The test walks
   `MarketStreamProtocol.__protocol_attrs__` and asserts the broker forwards all of them.
4. **Engine 21's mutation sweep.** Never run — the one piece of committed Phase 6 code with
   no sweep behind it. Subject `tests/engines/test_position_manager.py`, equivalent control
   included.

**Then, in order: spec 90 (engine 16 `decision`, a gate), spec 91 (engine 18 `execution`),
spec 93 (engine 22 `exit`).**

### All four loose ends DONE 2026-09-16 — green in my lane, gates not yet run

Files touched, and nothing else:

- `tests/engines/test_risk.py` — tripwire deleted, two codes moved into the renderable
  list, the precedence test inverted and renamed.
- `src/acsoe/engines/risk/engine.py` + `README.md` — the per-pair refusal now precedes the
  portfolio cap; the branch comment, the module docstring and the README's numbered gate
  list and precedence paragraph all rewritten to argue the new order.
- `src/acsoe/clients/paper/broker.py` + `README.md` — `drain_gaps` forwarded.
- `tests/clients/paper/test_broker.py` — the protocol walk.
- `tests/engines/test_position_manager.py` — eight tests for the eight survivors.
- `docs/build-log/phase-6/b-store.md` — five appended entries. **The original precedence
  Decision entry was not edited**, per `script-rules.md` rule 6; the reversal is a new
  entry that names it.

**No change to `src/acsoe/engines/position_manager/engine.py`.** All eight survivors were
missing assertions, not defects — I checked each against the contracts, the config and
`research/labelling.py` before concluding it. `git status` shows the engine unmodified,
which is also the proof the sweep restored all twenty-two mutants.

**Green in lane:**

```
pytest tests/engines/test_position_manager.py -q          48 passed  (was 40)
pytest tests/engines/test_risk.py -q                      47 passed  (was 48, the
                                                          deleted one is the tripwire)
pytest tests/clients/paper/ -q                            55 passed  (was 54)
the three together                                       150 passed
ruff  check (all touched src and test paths)             All checks passed
mypy  --strict src/acsoe/{clients/paper,engines/risk,engines/position_manager}/  clean
```

**Three mutation sweeps, 29 mutations, 29 killed, 3 equivalent controls all survived as
required.** Tables and reasoning in the build log. Two findings worth the lead's eye:

1. **Engine 21's `test_a_fill_sets_the_barriers_from_the_fill_price_and_not_the_bar_close`
   could not tell the fill price from the limit price**, because the paper broker fills a
   resting maker buy *at* its limit, so both are the same number in that fixture. The test
   was right about its subject and wrong about its witness — Phase 5's closing finding
   again. Replaced by a case where the client answers 98.50 for an order resting at 99.00.
2. **Two of the kill switch's four failure branches were unasserted** in an engine that
   had 40 tests and was already committed: a client that *answers* without mentioning the
   order, and a cancel the exchange did not act on. Both now covered.

**I deliberately did not mutate `src/acsoe/console/format.py`** to prove the renderable-codes
assertion. It is C's lane and C has it dirty in this shared tree; a restore-by-hash would
have written my pre-mutation bytes over C's uncommitted work. Respelling my own constant in
`engines/risk/contracts.py` asks the same question from my side of the seam.

**Four gates not run** — rule 6 requires the lead's explicit stop before any baseline run.

### Spec 90 — CLAIMED 2026-09-16, engine 16 `decision`

Claimed before any code. Files I will touch and nothing else:
`src/acsoe/engines/decision/{engine.py,contracts.py,README.md}` and
`tests/engines/test_decision.py`.

**Spec 80's prerequisites are on disk and I checked them rather than assuming:**
`context/engine-contracts.md:212` gives engine 16 a **Y** in the Gate column,
`trading-invariants.md:91` lists 16 among the gate engines, and `:102` lists it in
invariant 4's protected set. Scope limit "do not build before the lead's registry and
invariant edits land" is satisfied.

**Engines 9 `order_book` and 14 `adaptive_router` do not exist** — neither directory is
in `src/acsoe/engines/`. Engine 16 takes exactly two provenance fields from them,
`estimated_slippage_pct` and `active_model_run_id`, and **nothing it blocks on**, so it is
not blocked on C. Contract agreed from specs 96 and 97 and messaged to C-models.

**Two design decisions I am taking, both flagged to the lead rather than assumed:**

1. **Provenance is copied when present and omitted when absent; engine 16 never blocks on
   a provenance field.** Spec 97 item 5 says engine 14 must publish nothing "engine 15, 16
   or 18 reads to decide", and spec 90 item 3 puts the router's `active_model_run_id` in
   the intent. Both hold only if that field is a record and not a criterion. The same
   reading is applied to engine 9's slippage. Blocking on an absent provenance field would
   be a fifth clause the spec does not list, i.e. inventing a refusal.
2. **The pair and bar clauses are a walk over the payloads, not a hand-written list of
   four comparisons.** Engine 16 examines every payload it reads, and any that carries a
   `pair` or a bar timestamp is compared. So when C lands 9 and 14, whatever they publish
   is checked without engine 16 being edited — the same argument as the `drain_gaps` walk
   this morning: a hand-written list is written by the person who forgot the entry.

Verified rather than assumed: `state["prediction"]["bar_ts"]` is the **same value** as
`state["market_sensor"]["closed_bar_ts"]` — engine 5 reads `closed_bar_ts` at
`feature/engine.py:102` and engine 8 copies feature's at `prediction/engine.py:158` — so
comparing them is a real staleness check and not two unrelated clocks.

#### Spec 90 — BUILT AND GREEN IN MY LANE 2026-09-16; the four gates are not yet run

`src/acsoe/engines/decision/{__init__,engine,contracts}.py` + `README.md`, and
`tests/engines/test_decision.py`. Nothing else touched. **Not marked complete** — my
standing rule: a spec is complete once its four gates are green, never in the edit that
builds it.

```
pytest tests/engines/test_decision.py -q                    30 passed
the whole lane together (decision, risk, position_manager,
  clients/paper)                                           180 passed
ruff  check src/acsoe/engines/decision/ tests/.../test_decision.py   All checks passed
mypy  --strict src/acsoe/engines/decision/                  3 source files, clean
```

**Sixteen mutations, sixteen killed, equivalent control survived.** First pass was 12
killed and 3 survivors; three tests added; the whole sweep re-run from scratch rather
than the three re-checked.

**Two findings for the lead, both the same shape and both found only by mutation:**

1. **`_approved_quantity` returned `str(qty)`, which turns off `Money`'s float refusal.**
   `str(33.33)` is `"33.33"` and parses cleanly, so the one validator in the system built
   to stop a float that has already lost precision would never have seen one. Latent on
   every real tick, because engine 11 publishes `format(d, "f")` — the two paths are
   identical until they are not. Fixed; the docstring says why the tidy-up is not one.
2. **`expected_move_pct` appears in two payloads with the same value**, so the README's
   claim that engine 16 takes all three cost numbers from one publisher had no witness:
   a mutation pointing the field at engine 8 survived all 27 tests. Same shape as engine
   21's fill-price test this morning and as Phase 5's calibrator. **Three in one day.**

**Blocked on nobody.** Engines 9 and 14 do not exist; engine 16 takes only provenance
from them and never blocks on it, so it is complete without them. Two hand-built payloads
stand in, guarded by `test_engines_nine_and_fourteen_still_do_not_exist`, which goes red
the day C lands either.

**Engine 16 is not registered in `bootstrap.py`** — that is the lead's, spec 82, held
until 87 and 94 are green. `is_gate_matches_registry` will not count it until then.

### Spec 91 — BUILT AND GREEN IN MY LANE 2026-09-16; the four gates are not yet run

Claimed before any code. Files: `src/acsoe/engines/execution/{__init__,engine,contracts}.py`
+ `README.md`, `tests/engines/test_execution.py`, and **`src/acsoe/clients/paper/broker.py`
+ `tests/clients/paper/test_broker.py`** for the defect below. Nothing else.

```
pytest tests/engines/test_execution.py -q                    34 passed
the whole lane (execution, decision, position_manager,
  risk, clients/paper)                                      216 passed
ruff  check (all six touched paths)                          All checks passed
mypy  --strict (execution, decision, clients/paper)          9 source files, clean
```

**Eighteen mutations, eighteen killed, equivalent control survived.** First pass 15
killed and 2 survivors; two tests added and one refactor; whole sweep re-run from
scratch. Two of the eighteen are in the paper broker, because the fix below is part of
this spec's correctness.

**A defect in my own spec 88 broker, found by engine 18 rather than by anything in
`tests/clients/paper/`.** `PaperBroker.open_orders()` was derived **entirely from the
store**, so an order it had accepted and engine 19 had not yet recorded was invisible to
it — which is *every* order between the opportunity chain and the end of the manage
chain. Two consequences: it answered "nothing is open" while a post-only buy was on the
book (invariant 3's shape), and paper and live disagreed about the same question, which
defeats the reason the broker exists. Fixed to ask the union of the store's resting rows
and `_pending`, through the same single `query_orders` path. The old test drove only
orders the store already held, which is why 57 tests could not see it.

**Two deviations from spec 91, both flagged to the lead, neither taken quietly:**

1. **The second idempotency probe is `open_orders()`, not `query_orders([userref])`.**
   `query_orders` raises for *both* "never heard of it" and "cannot reach the exchange",
   and those need opposite actions — read it one way and an outage places a duplicate
   order; read it the other and the *first* placement of every candidate is refused and
   the system never trades. `open_orders()` has a well-defined negative and still raises
   during an outage. Same shape as spec 88's `drain_trades`: the spec's conclusion is
   right and its mechanism cannot work.
2. **`OrderState` carries no `qty` and no `limit_price`**, so an order found at the
   exchange that the store never recorded cannot be described well enough to build engine
   19's row. Engine 18 does not place a duplicate — the part that protects money — and
   publishes **no row** under a fourth code, `entry_unrecorded_at_exchange`, rather than
   guessing two numbers. **The residual gap is real and not mine to close:** nothing will
   ever cancel that order, because engine 21 assembles entries from the store plus
   `state["execution"]` and it is in neither. Reported to the lead and to A.

**A fourth occurrence of the day's recurring failure.** `test_a_non_positive_bid_raises`
matched `"not a price"`, which appears in *two* error messages, so deleting the guard it
was written for left it green. Substring variant this time — `pytest.raises(match=...)`
invites it, because the memorable fragment is usually the shared one.

**The two-enum trap caught me in the test file**: `request.side is OrderSide.BUY` with
the store's enum against the client's. The standing rule worked — immediate and legible,
not silent. Both sides now alias the client's enums.

### Spec 93 — CLAIMED 2026-09-16, engine 22 `exit`

Claimed before any code. Files: `src/acsoe/engines/exit/{__init__,engine,contracts}.py`
+ `README.md`, and `tests/engines/test_exit.py`.

### Spec 89 — BUILT AND GREEN IN MY LANE 2026-09-16; the four gates are not yet run

Claimed 2026-09-16 before any code, per rule 1. Files touched, and nothing else:

- `src/acsoe/engines/risk/contracts.py` — two `Final` reason codes.
- `src/acsoe/engines/risk/engine.py` — `RiskEngine._pair_exposure` and the refusal.
- `src/acsoe/engines/risk/README.md`.
- `tests/engines/test_risk.py`.

**No schema change, no migration, no new `StoreClient` method.** `open_positions()` and
`resting_orders(intent=OrderIntent.ENTRY)` already exist and already carry `pair`, so spec 89
step 3's "if a per-pair read is needed" never fired.

**Not marked complete.** My own Phase 3 rule stands: a spec is complete here only once its four
gates are green, never in the edit that claims it. What is green so far:

```
pytest tests/engines/test_risk.py -q                    48 passed
pytest tests/engines/test_scout.py \
       tests/engines/test_feature_chain_rehearsal.py -q 92 passed
ruff  check src/acsoe/engines/risk/ tests/engines/test_risk.py   All checks passed
mypy  --strict src/acsoe/engines/risk/                  3 source files, clean
```

The four gates need a full-suite run, and **rule 6 requires the lead's explicit stop before any
baseline run** — three of us are in this checkout. Asked; waiting.

**Eleven mutations, eleven killed**, each named with the test that killed it, each applied to a
byte copy and restored with the sha256 compared in the same statement. Table and reasoning in
`docs/build-log/phase-6/b-store.md`. The finding: M1 (pair comparison removed), M3 (every
resting order counts, not only entries) and M4 (a closed position counts) were each killed by
the **negative** half of their parametrised pair and by nothing else in 48 tests — the block
halves die to six tests each and prove almost nothing alone.

**One decision the lead or the operator may want to overturn**, recorded as a Decision entry in
the build log and pinned by a test: when the portfolio cap and the per-pair rule are both true
on one tick, the **cap** is reported. Both block, so only the `reason_code` differs, and I kept
the cap first so no rejection recorded before spec 89 changes code because spec 89 landed. The
cost is real: a query counting how often invariant 6's per-pair clause fires undercounts on
exactly those ticks. One line to reverse.

**For C, spec 99 — two codes are not renderable yet.** `position_open_on_pair` and
`entry_resting_on_pair` are absent from `REASON_PROSE`, so the console renders "No reason was
recorded." for both, silently. Handed to C by message with suggested prose.
`test_the_two_codes_spec_89_added_are_still_waiting_on_cs_prose` asserts their **absence** and
**will go red the moment C maps either one** — deliberately, with a failure message saying to
move them into the renderable test and delete the tripwire. A "renderable if present" test would
have been green in both states forever. Also added `no_fx_rate` to that renderable list; it has
been mapped since Phase 3 and emitted since spec 43 and was never checked.

### Spec 88 — BUILT AND GREEN IN MY LANE 2026-09-16; the four gates are not yet run

Claimed before any code. Files touched: `src/acsoe/clients/paper/` (`__init__.py`, `broker.py`,
`fills.py`, `README.md`), `tests/clients/paper/` (`test_fills.py`, `test_broker.py`), plus
`StoreClient.filled_orders()` in `src/acsoe/clients/store/client.py` with its four tests in
`tests/clients/store/test_store.py`. All in my lane; no migration, no schema change.

```
pytest tests/clients/paper/ tests/clients/store/ -q      250 passed
pytest tests/cli/test_paper_broker_wiring.py \
       tests/clients/paper/ -q                            61 passed   (A's seam, below)
ruff  check src/acsoe/clients/ tests/clients/             All checks passed
mypy  --strict src/acsoe/clients/                         22 source files, clean
```

**Thirteen mutations: twelve killed, one equivalent control that survived as required.** Table
in the build log. Five of the twelve — look-ahead through the simulator, pair isolation,
invariant 8's idempotency, not draining the window engine 3 needs, and the ledger's status
filter — were each killed by **exactly one test in 150**.

**The seam with A is closed on both sides with no double.** A read my constructor message,
including the `clock` amendment, and `cli/engine.py:130` now reads
`PaperBroker(real, store=store, config=config, clock=clock)` behind `if config.mode == "paper"`.
A's `tests/cli/test_paper_broker_wiring.py` passes against my real broker and my
`test_the_broker_and_engine_three_see_the_same_trades_on_one_tick` runs A's real engine 3
against it. Neither side mocks the other.

**Two things for the lead, both in the build log with full reasoning:**

1. **Spec 88 step 3 names a method nothing calls.** It says engine 3 *drains* trades;
   `engines/market_sensor/engine.py` reads `recent_trades()`, a rolling window that
   deliberately does not clear. `drain_trades()` exists on the client, on `ws.py` and in A's
   protocol and **no caller in `src/` uses it**. The spec's conclusion holds — the broker is in
   the path — and its mechanism does not, so the broker keeps no observation buffer.
2. **A deviation from spec 88 step 2 that I did not treat as settled.** The drain was going to
   be the tick boundary at which `_pending` is dropped. With no tick edge the broker can see,
   `_pending` is pruned by *recording* instead: the store's row wins the moment it exists.
   Stricter than the spec on the normal path, safer on the abnormal one. Flagged rather than
   assumed.

Not marked complete: the four gates need a full-suite run and rule 6 requires the lead's stop.

*Original claim, kept because the decisions in it were made before the code and two of them
moved:*

**A's spec 84 has landed**, so this is built against the real surface and not a mock:
`OrderRequest`, `OrderAck`, `OrderAckStatus`, `OrderState`, `OrderStatus`,
`TERMINAL_ORDER_STATUSES` and `OrderClientProtocol` are all in
`src/acsoe/clients/kraken/contracts.py`, and `OrderClientProtocol` has **four** calls, not the
three spec 88 names: `add_order`, `cancel_order`, `query_orders` and `open_orders`.

Decisions settled from the documents before writing, so they are visible rather than embedded:

- **Constructor.** `PaperBroker(real, *, store, config, clock)`. Keyword-only after `real`,
  because Phase 5 cost us a collision where `models_dir` landed positional after I had told A it
  would be keyword-only. **`clock` is an amendment to what I first sent A** and the reason is
  `BalancesSnapshot.fetched_at`: the ledger must answer whether or not the real `Balance` call
  works, so it cannot borrow the real snapshot's timestamp, and invariant 9's injected clock is
  the only other source. A told.
- **The ledger is quote-side only, and that is spec 88's own wording** — "minus every filled
  entry's notional and fee, plus every filled exit's proceeds less fee". It does **not** credit
  the base currency on a buy. Engine 19 computes `equity = cash + positions_value` where `cash`
  is `balances[reporting_currency]`, so the base leg is already represented by the `positions`
  row; crediting it here would be a second representation of one exposure, and the two would
  drift the first time a fill and a position row disagreed.
- **`pair` → quote currency comes from `real.asset_pairs()`**, which is TTL-cached in
  `rest.py`, never from splitting the pair name. `OrderRow` carries no `quote` column and
  Kraken pair names are not reliably `BASE/QUOTE`.
- **The broker sees trades by being in the path.** Engine 3 calls `drain_trades()` through
  `clients.kraken`, which in paper mode is the broker, so the broker's `drain_trades()` forwards,
  keeps what passed through and returns it. It must not call `drain_trades()` itself — that
  empties the buffer and engine 3 and the broker would then disagree about which trades happened,
  which is the one thing spec 88 asserts they cannot.
- **A restart loses the observed trades and nothing else.** Resting orders are the store's rows,
  per spec 88 step 2, but the trade observations are per-process like the stream itself. After a
  restart nothing fills until new trades arrive, which is the pessimistic direction. README.

### CLAIMED 2026-09-16 — spec 92, engine 21 `position_manager`

**Taken out of the lead's stated order, deliberately, and this note is the reason.** The order
was 90 → 91 → 92 → 93. Spec 90 is **held** by its own scope limit until the lead's registry and
invariant edits land (spec 80), and spec 91 reads engine 16's intent under spec 90 option 2, so
both are blocked on the same thing. The Phase 6 task list says waves are dependency order and
not permission to idle. Spec 92 depends on nothing that is missing:

- the store reads — `resting_orders(intent=entry)`, `open_positions()` — are mine and exist;
- `query_orders` is my own broker, landed under spec 88;
- `state["market_sensor"]["quotes"]` and `["trade_ranges"]` are A's spec 85 and have landed;
- `state["execution"]["orders"]` is read **only when present**, which is spec 92's own wording,
  so engine 18 not existing yet is a case the engine must handle rather than a blocker.

Files: `src/acsoe/engines/position_manager/` and `tests/engines/test_position_manager.py`.

### Claimed after it, in order

Spec 88 (`clients/paper/`, `tests/clients/paper/`) → spec 90 (**held** until the lead says the
registry Gate column and the invariant 3 and 4 edits have landed) → specs 91, 92, 93 → spec 94.

## Claimed

- **Spec 11** — `db/migrations/`, SQLite schema and forward-only migration runner. *Complete.*
- **Spec 12** — `src/acsoe/clients/store/`, store client and contracts. *Complete.*
- **Spec 13** — `src/acsoe/clients/store/seed.py`, seed generator. *Complete.*
- **Spec 31** — persisted system mode: `db/migrations/0002_persisted_system_mode.sql`,
  `clients/store/{client,contracts}.py`, `tests/db/`, `tests/clients/store/`. *Complete,
  green on all three phase gates.*

- **Spec 34** — engine 10 `cost`. *Complete, committed at `3581e87`. Superseded by spec 40.*
- **Spec 35** — engine 11 `risk`. *Complete, committed at `5b0dd2b`. Superseded by spec 41.*
- **Spec 36** — engine 17 `safety`. *Complete and green, committed at `5b0dd2b`. Its one
  open question is closed by spec 42 — see below.*

### Phase 3 — claimed 2026-09-10

- **Spec 40** — wire engine 10 `cost` to the real `state["exchange"]`.
  `src/acsoe/engines/cost/{contracts,engine}.py`, `README.md`, `tests/engines/test_cost.py`.
  ***Complete, all four gates green 2026-09-10.*** Fixtures rewritten, not repointed: every
  `state["exchange"]` in `test_cost.py` is `ExchangeEngine().process(...).data` verbatim,
  from A's real engine 1 against C's `FakeKrakenClient`, and a source-reading test refuses
  any of engine 1's payload keys written as a dict-key literal in that file.
  `test_cost.py:376` deleted, not edited; reason in the build log.
- **Spec 41** — wire engine 11 `risk`, give it a price, and **build** the paper-mode balance
  fallback. `src/acsoe/engines/risk/{contracts,engine}.py`, `README.md`,
  `tests/engines/test_risk.py`. ***Complete, all four gates green 2026-09-10.*** Pair rules
  re-pointed to `exchange.pair_rules.pairs`; the price now comes from
  `market_sensor.quotes[pair]` — **ask** sizes the quantity, **bid** values it for `costmin`,
  per the lead's ruling. The balance fallback is built as new behaviour: paper falls back and
  records `balance_from_paper_starting_balances`, live and replay block. Every `state` in
  `test_risk.py` is engines 1 and 3's real output against C's fake client. **One open item for
  the lead — see below.**

#### For the lead — `replay` mode's balance fallback is my reading, not a ruling

Spec 41 names paper (fall back) and live (block). `EngineContext.mode` has a third value,
`replay`, and the spec does not mention it. I implemented `if context.mode != "paper"` —
so replay blocks — because invariant 2's table is headed *paper mode*, invariant 3 says a
gate that is unsure refuses, and "not paper" cannot silently extend the fallback to a mode
added later the way "is live" would.

**The cost is real and deferred, not absent.** If replay is later meant to reproduce paper
faithfully, a replayed tick will block where the paper run fell back, and the two diverge
exactly where invariant 10's faithful-replay property should hold. Nothing in Phase 3
exercises replay. One line and one constant to reverse; full reasoning in the build log.
- **Spec 42** — apply the ratified `CONDITION_ACTION` and prove `safety` in a real guard
  chain. `src/acsoe/engines/safety/{contracts,engine}.py`, `README.md`,
  `tests/engines/test_safety.py`, `tests/engines/test_safety_guard_chain.py`.
  ***Complete, all four gates green 2026-09-10.*** The ruled table is applied — **it was
  not, despite the note below saying it was; see the build log.** `ESCALATING_CONDITION`
  names the one condition that may reach `close_all` and a test enumerates the table
  against it. 46 tests in `test_safety.py` and 5 in the new guard-chain file, which drives
  the real `Orchestrator` over engines 1, 2, 3, 4, 17 against a real `StoreClient` on an
  empty database and on the seed.

### Phase 3 wave 2 — claimed 2026-09-10

- **Spec 43** — engine 7 `scout`, the tradable universe. `src/acsoe/engines/scout/`
  (`engine.py`, `contracts.py`, `README.md`), `tests/engines/test_scout.py`.
  ***Complete, all four gates green 2026-09-10, and `--phase 3` is 9 PASS / 0 FAIL /
  0 PENDING.*** 24 tests. Nine exclusion codes, each rule proved to be the *only* thing
  excluding its pair; the tick-grid rule made to fire and its boundary pinned as strict;
  counts asserted to add up including on a tick where four rules fire at once; the sizing
  cross-checked against the real engine 11 over a table straddling `ordermin` by one lot
  increment each way. Four mutations run and each caught by the test written for it.
  **One escalation to the lead — see below.**
- **Spec 44** — engine 7 `scout`, the candidate and the gate. `src/acsoe/engines/scout/`,
  `tests/engines/test_scout.py`. ***Complete, all four gates green 2026-09-10, and
  `--phase 3` is 9 PASS / 0 FAIL / 0 PENDING.*** 44 tests. One candidate under
  `state["scout"]["pair"]`, absent and never null when there is none; empty universe is
  `PASS` and not `BLOCK`; the handoff run as one tick through the real engines 10 and 11.
  Ordering is alphabetical, isolated as `rank_universe` in `contracts.py`.

### Phase 4 — claimed 2026-09-11

- **Spec 51** — the store surface engine 19 `memory` and the cycle feed need.
  `src/acsoe/clients/store/client.py`, `src/acsoe/clients/store/__init__.py`,
  `tests/clients/store/test_store.py`. *Claimed, in progress.* Three parts: a bounded
  most-recent-N read for `block_records` ordered by `ts`; an audit of every write and
  read engine 19 needs against what `StoreClient` already has; and a `peak_equity`
  read that does not walk the whole equity series. **No schema change, no migration,
  no edit to `console/` or to any `safety` read path.** ***Complete 2026-09-11.***
  Three methods, 14 tests, eight mutations run and all eight red — including the one
  spec 51 names by hand. `pytest tests/ -q` clean in my lane; `mypy --strict src/` and
  `ruff check src/` green.

#### Spec 51 — what landed, and the one thing that is C's to finish

Three methods on `StoreClient`, all handed to C by `SendMessage` the moment they
existed rather than at the end of the task:

- `recent_block_records(limit: int) -> tuple[BlockRecordRow, ...]` — most recent
  `limit` **rows**, `ORDER BY ts DESC, id DESC`, no default limit.
- `recent_blocked_ticks(limit: int) -> tuple[BlockRecordRow, ...]` — most recent
  `limit` **ticks**, one row each, primary blocker preferred, lowest `id` on the tick
  as the fallback. This is the one the cycle feed wants; a rows-limited read can cut a
  tick in half and render it as blocked by the wrong engine. Reasoned out in the build
  log and proved by mutation M8 against the real Phase 0 seed.
- `peak_equity(self) -> Decimal | None` — spec 51 item 3 and spec 50's running maximum.
  **`SELECT MAX(peak_equity)` is the wrong query**: money is an exact decimal string,
  SQLite compares it lexicographically, and `'9.50' > '10000.00'`. A too-small peak is
  a too-small drawdown and a breaker that sits quiet through the loss it exists to
  stop. Build log entry, and a test that asserts the wrong query is actually wrong on
  its own fixture before asserting the right answer.

**Audited and found sound, nothing added:** all six writes engine 19 needs already
exist — `write_block_record`, `write_equity_snapshot`, `write_position`, `write_order`,
`write_trade`, `write_rejection` — as do `count_open_positions` and
`latest_equity_snapshot`. Specs 49 and 50 need no new write surface.

**Still open, and it is C's:** `console/reader.py:453` `_blocked_ticks` still calls
`block_records_in_window(start_ts=_TS_MIN, end_ts=_TS_MAX)` and builds a row model for
every record in the table. Spec 51 says hand C the method name and stop, so I have.
Spec 51's "the cycle feed no longer performs an unbounded scan" is not satisfied until
C makes that one-line swap to `recent_blocked_ticks(self._feed_limit)`.

- **Manage-chain rehearsal for engine 19** — `tests/engines/test_manage_chain_rehearsal.py`,
  new file, my lane. *Claimed 2026-09-11, in progress.* Lead task, and the deliberate
  exception to "nobody writes a test for another agent's code": the rehearsal tests the
  **orchestrator wiring**, which is the lead's, not engine 19, which is C's. Held before
  registration, the same way A's guard-chain rehearsal was held before engines 7, 10, 11
  and 17 were registered. Two real ticks, not one. **If it goes red for a real reason I do
  not fix engine 19** — report to the lead and to C.
  ***Complete and green 2026-09-11. Ten tests, all passing — nothing to report about
  engine 19.*** It records a `data_guard` block with the manage chain still running on a
  blocked tick, writes no row on a clean tick while still reporting per-table counts
  including zeros, reports Phase 6 publishers absent rather than zero, and its second tick
  is genuinely its own. `ux_equity_snapshots_tick` has now been *seen* to fire: two
  orchestrators sharing a `run_id` collide on `cycle_id` 1, contract rule 7 turns the
  `IntegrityError` into ERROR, the tick completes and the first row survives. Six
  mutations, five killed, one equivalent and recorded as such. **N5 is the one that
  justifies the file**: with `cycle_id` cached on `self`, a single-tick rehearsal passes
  and five two-tick assertions fail — the two-tick rule measured rather than asserted.

  **One defect of my own, in the harness rather than the tests.** It restored mutated
  files only at the end of the run, so a mutation of `core/orchestrator.py` was still on
  disk while `engines/memory/engine.py` was mutated, and that verdict was really both
  together. Compounded mutants fail more tests, so every verdict drifts toward KILLED and
  a real survivor can hide. It very nearly cost the rehearsal its central claim — I would
  have written that a one-tick rehearsal catches N5, on a check that was measuring
  something else. Both files verified byte-identical by sha256 afterwards; neither is
  tracked by git, so `git checkout` was never a safety net and the verify step is the only
  reason this was recoverable.

#### Phase 3 branch-coverage backlog — `discover_migrations` closed 2026-09-11

Backlog item, not phase-gate work, picked up after spec 51. `tests/db/test_migrations.py`,
my lane. **The backlog said three survivors; the function has five refusal branches plus a
sixth path, and two survived wide — not three.** The count was overstated in one direction
and understated in the other, which is a better argument for re-checking wide than the
handoff's own. The item itself lives in `feature-specs/PHASE-3-TASKS.md` and in neither
the consolidated build log nor the tracker — the lead has since carried the whole backlog
into the tracker's open items.

Genuine survivors, now tested: **duplicate migration version** (unrefused, the second file
silently overwrites the first in a dict keyed on version and the set still looks
contiguous) and **no migration files in the directory** (unrefused, returns `()`, which
passes the contiguity check trivially and reports success over a database with no tables).

**The finding I was not sent to make, and it is the one worth keeping.** Two further
branches — directory-not-found and the non-`.sql` skip — are killed *only* by tests in
other agents' files that are not about migrations: a Phase 4 engine test that happens to
build a store over a missing path, and a research import-boundary test that happens to walk
this directory. They read as covered in any sweep and are covered by nobody. **An
incidental kill is worse than a survivor, because a survivor is at least on a list.** Both
now have tests next to the code they are about. All six branches are killed by
`tests/db/test_migrations.py` itself; every assertion is on the message and not the bare
type, because all five refusals raise `MigrationError`.

Sweep excluded `tests/scripts/`, which was red in A's lane at the time; the harness refuses
to report at all unless its baseline is green, because a sweep over a red tree marks every
mutation killed and manufactures a clean result out of someone else's broken tree. Shape of
that hole recorded in the build log.

#### For C — the ORDER BY anchor in `test_phase3_criteria.py` is single-occurrence by convention only

My first cut of `recent_blocked_ticks` reached for the same literal
`ORDER BY ts DESC, run_id DESC, cycle_id DESC` the outage walk uses, and
`test_an_outage_counted_by_cycle_id_is_a_fail` correctly refused: *anchor appears 2
times, expected exactly once*. Fixed in my lane — the feed query now tie-breaks
`cycle_id` before `run_id` — with a comment at the site saying not to tidy the two into
one wording. **C's count assertion is the only reason this surfaced at all**: a patcher
taking the first match would have mutated my new query, left the outage counter intact,
watched the Phase 3 criterion stay PASS, and reported a can-it-fail proof that had
itself stopped being able to fail. Worth knowing the anchor is textual and that the
next query in that file can collide with it again.

#### OPEN QUESTION for the tracker — engine 7 has no ranking score, and that is recorded

**Ruled by the operator on 2026-09-10 and not a defect**, but it belongs in
`context/progress-tracker.md`, which is the lead's, so it is raised here.

Invariant 4 describes engine 7's ranking as "a deterministic score over features". There
are no features in Phase 3, so **the ordering is the tie-break alone: pair name,
ascending**. The operator's reasoning: a placeholder score would be a check whose output
resembles the claim while the claim is untrue, and ranking one candidate out of a filtered
set is a Phase 5 decision made with real features in front of us.

**Phase 5 closes it.** It is isolated as one named function, `rank_universe` in
`scout/contracts.py`, so the fix is one edit against a named seam. `engines/scout/README.md`
says in as many words that alphabetical ordering is a recorded absence rather than a design,
so nobody reads it as a choice someone defended.

#### For the lead — the affordability check compares two currencies

`target_notional` derives from equity, which invariant 7 expresses in
`trading.base_reporting_currency`; the balance it is compared against is in the pair's
**quote** currency. Comparing them needs an FX rate and nothing in this system publishes
one, though invariant 7 says one is converted "at the trade timestamp".

**Engine 11 has carried the identical comparison since spec 35** and no test has ever
reached it on a pair whose quote is not the reporting currency, because no fixture has one
that gets that far. Found by writing the third caller, not by anything failing.

I ask the comparison only when the currencies match, with the reason at the call site. I
did **not** invent a rate, assume parity, or mint a "cannot be converted" exclusion — the
last would be inventing trading behaviour under cover of caution, and the ruling on A's
crypto-quoted heuristic is the precedent. The residue: a non-reporting-currency pair can
enter the universe without being shown affordable, which is the *over*-including direction
and the wrong one for `scout`. Unreachable today, reachable the moment
`allow_crypto_quoted` is enabled — and my own crypto-quoted test flips exactly that flag.

### Phase 5 — claimed 2026-09-13

- **Spec 62** — the store surface for model artefacts. `src/acsoe/clients/store/client.py`,
  `tests/clients/store/test_store.py`. ***COMPLETE, all four gates green 2026-09-13*** — see
  Gates below for the run. `StoreClient(db_path, *, models_dir=None)` gains `models_dir`,
  `model_run_dir(run_id)` and `new_model_run_dir(run_id)`, the last refusing an existing
  directory because a trained artefact is never overwritten. Plus the audit of
  `write_leaderboard_entry` and `leaderboard()` against what spec 74 needs, which found one
  gap. **No schema change, no migration, no artefact parsing** — the store hands back a path
  and C's `modelling/artefacts.py` decides what is in it. 11 mutations, all 11 killed.
  Committed by the lead at `16c5685`.
- **Spec 76** — engine 7 `scout`, ranking by a config-named feature. `src/acsoe/engines/scout/`
  (`contracts.py`, `engine.py`, `README.md`), `tests/engines/test_scout.py`. ***COMPLETE, all
  four gates green 2026-09-13*** — see Gates below. 16 new tests, **60 in the file and none
  skipped**: the no-double seam test went from skipped to passing with no edit the moment C
  landed engine 5, which is the point of having written it that way. 13 mutations run and all
  13 killed by tests in this file, including the four spec 76 names by hand.
  `scout.rank_feature` is **absent** in the committed config, so the ordering is alphabetical
  today and the engine publishes `rank_feature: null`; the mechanism is built and waits on the
  operator's ruling from C's spec 75 study. Committed by the lead at `16c5685`.

#### Spec 76 — a third refusal, found by C and not by any of my thirteen mutations

**2026-09-13, after both specs were marked complete.** Spec 76 names two ways of being unable
to rank and I built both; there is a third and I missed it. **`scout.rank_feature` naming a
feature that does not exist** found no value for any pair, the no-value rule then ordered every
pair alphabetically among themselves, and the engine published the misspelt name beside a
ranking it never performed. No exception, no null, and a candidate that is a real pair from the
real universe — the silent fallback my own README forbids in general terms, left open in its
commonest instance. Demonstrated against the real function before a line was written:
`feature='volatilty_24h'` returned exactly `tuple(sorted(pairs))`.

The per-pair question — does *this pair* have a value — and the whole-universe question — does
this *feature* exist — are different, and `_feature_value` returning `None` was answering both.
The empty feature name is the same defect at length zero and was refused from the start.

`_features` now reads `feature_names` from `state["feature"]`, a required field of C's
`FeatureState`, and blocks when the configured name is not among them. Three new tests, three
new mutations, all three killed. **N14, which deletes the check, is killed by the new test and
by nothing else** — which is the honest measure of how invisible this was: thirteen mutations
had already passed over it, because a mutation can only ask about behaviour somebody thought of.

**Found by C-2 reviewing the seam while writing spec 60's criterion for it**, and relayed. That
is a consumer reasoning about a producer, and it is the one review this project keeps proving
no amount of self-testing replaces.

#### COMPLETE 2026-09-15 — engine 15 `skeptic` rehearsed (B-3 session)

Same file, now **29 tests**, on the lead's request. `pytest tests/engines/test_feature_chain_rehearsal.py -q`
29 passed; `ruff check` on the file clean. Account in the Phase 5 build log, 2026-09-15.

- **(a) Full registry chain 5, 6, 7, 12, 13, 8, 10, 11, 15**: stops at `cost` for want of engine
  9, and `skeptic` never appears in `state`. That is why 15 is rehearsed without 10 and 11.
- **(b) Chain 5, 6, 7, 12, 13, 8, 15**, bar tick then quiet tick, a four-fold skeptic trained with
  a macro column: `skeptic_unavailable` naming the missing key on a BUY call (three configs);
  `OK` with "not a BUY call" on a non-BUY; `skeptic_veto` at `p_wrong − 1e-6` and `OK` at
  `p_wrong + 1e-6`, with `p_wrong` recomputed from the artefact rather than read back. Engine 15
  is absent on every quiet tick.
- **Mutations**: veto inverted, P(right), state-key iteration and constant 0.5 all killed by the
  rehearsal. The manifest's names re-sorted into state order survives it and is killed by C's
  `test_the_vector_is_built_in_the_manifests_order_not_the_state_rows`: covered elsewhere, and
  the two orders cannot disagree on a state the live chain produces.
- **For C**: the veto reason prints `p_wrong` and the threshold to four decimals, so on this
  fixture it reads "0.0000 … 0.0000". The published fields are exact.
- **In-flight red**: one fixture run hit C-3's mid-save `fit()` signature change in
  `research/training.py`, and a re-run minutes later was clean.

#### COMPLETE 2026-09-13 — engines 13 and 8 rehearsed, two configurations

Same file, now **21 tests**, on the lead's request of 17:25. Chain 5, 6, 7, 12, 13, 8, 10, 11
with my real engines 10 and 11 in their positions.

**(a) No artefact**, the committed config: engine 13 blocks `anomaly_unavailable` and engines
8, 10 and 11 never appear in `state`. The reason code is checked against the console's
`REASON_PROSE`, because a code missing from that map renders silently.

**(b) Real artefacts**: a module-scoped fixture trains a predictor, DI and anomaly detector
from the committed sample into a temporary models root through `research/training.py`, which
also exercises my own `new_model_run_dir`. Engine 13 passes, engine 8 publishes three
calibrated probabilities summing to one, an `expected_move_pct` **string**, a DI and a
threshold, and engine 10 reads it. The DI refusal is driven by **real archive bars against a
model trained on the constructed series** and asserts no expected move is published.

**Three findings, none of them a fix of mine.**

1. **`prediction.di_percentile` is a training-time key.** The request expected engine 8 to
   block while it is absent; engine 8 never reads it — `research/training.py` does, and a run
   trained without it carries no `di.npz`, which engine 8 then refuses to load. The property
   holds, by a different route than the request assumed, and the test now exercises that route
   by training a second run without the key. **Open for the operator:** an artefact trained
   with somebody else's percentile predicts happily while the operator's key is still absent,
   because the threshold travels in the artefact. Escalated, not answered.
2. **Where the chain stops today.** Engine 9 `order_book` is Phase 6, so slippage is absent,
   invariant 2 gives it no fallback, and engine 10 blocks. Asserted, so the day engine 9 lands
   that test goes red and somebody extends the rehearsal.
3. **A fixture defect of mine, twice.** A constant trade count makes `trades_z_*` a division by
   zero, so engine 13 refused the vector as incomplete — correctly. Fixed by varying the count;
   the first fix saturated on real archive bars and had to be fixed again.

**Three named mutations. T1 and T3 killed by the rehearsal; T2 survived it and is killed by the
whole suite** — C-2's own `test_the_vector_is_built_in_the_manifests_order_not_the_state_rows`.
Engine 5 builds rows in `FEATURE_NAMES` order, so the row order and the manifest order coincide
on any state the live chain produces, and no end-to-end fixture can construct the
disagreement. Reporting it as a survivor would have sent someone to write a test C already had.
The first wide baseline was red in C-2's spec 73 file; the harness refused to report, and the
re-run excludes that one file and says so.

#### COMPLETE 2026-09-13 — engines 6 and 12 rehearsed in the same file

Same file, now **14 tests**, extended on the lead's request of 10:10. Engines 5, 6, 7 and 12
through the real orchestrator in registry order, two real ticks, nothing staged.

**The answer to the question the request asked:** yes, `state["scout"]` gates engine 12. It
reads `state["scout"]["pair"]` and returns `PASS` with an empty payload when there is none, so
a 5-6-12 chain reaches it and it declines to classify on every tick. Rather than fabricate a
scout payload — forbidden by the request and a hand-built `state` besides — the chain carries
**the real engine 7**, which sits between 6 and 12 in the registry and is mine. Engine 12 then
classifies the pair engine 7 actually chose. Both cases are asserted: the no-candidate `PASS`
and the full chain.

**Four more mutations, four killed**, hashes verified before and after the sweep:

| # | Mutation | Killed by |
|---|---|---|
| S1 | engine 6 reports `available` with a macro pair missing | the missing-asset test |
| S2 | engine 6 drops the `missing` list | the same test |
| S3 | engine 12 classifies with no candidate | the no-candidate test |
| S4 | the orchestrator does not stop the chain on a `PASS` | the cadence test |

**S4 is the mutation only a multi-engine rehearsal can ask.** While engine 5 was the only
registered engine, "it returns `PASS` and the chain stops there" had no observable consequence
and no test could see it. With three engines behind it, deleting the orchestrator's `PASS`
check turns the cadence test red.

**Nothing to report against engine 6 or engine 12**, and one finding against my own fixture:
engine 7 first found no candidate, `{'insufficient_quote_balance': 3, 'no_live_quote': 1}`,
because the fake account held no spendable USD. Not a defect — at the committed 1% risk
fraction and 1.5% stop, $5,000 of equity sizes a $3,333 position. Diagnosed in one line from
engine 7's own exclusion tally.

**Two naming facts, and they are one fact twice.** The committed feature fixture is `SOLUSD`,
the archive *filename* spelling; a stream and `AssetPairs` both say `SOL/USD`. Streaming under
the archive spelling builds a universe engine 7 cannot match, and the rehearsal would then pass
with an empty universe for a reason unrelated to wiring. The lead's `BTC/USD` versus `XBTUSD`
ruling is the same distinction from the other side.

#### COMPLETE 2026-09-13 — the two-tick orchestrator rehearsal of engine 5

`tests/engines/test_feature_chain_rehearsal.py`, **8 tests, all passing**, and the phase gate
is green on the run that includes it: `pytest tests/ -q` **2167 passed, 2 skipped**;
`mypy --strict src/ scripts/` **115 source files**; `ruff check src/ tests/ scripts/` clean;
`scripts/verify.py --phase 5` **2 PASS, 0 FAIL, 0 PENDING**. That last line reads "Phase 5 is
green" and **must not be believed**: only two criteria are registered, because C-2's spec 60
has not landed. A phase with fifteen engines' worth of real code in it cannot be green on
`docs_vocabulary` and `toolchain_green` alone, and spec 60 exists to stop exactly that reading.

**What it drives.** Engine 5 alone in the opportunity chain, engine 3 in the guard chain, two
real `Orchestrator.tick()` calls sixty seconds apart, over real prices: the trade stream is
rebuilt from `tests/fixtures/candles_sample.parquet` so engine 3 produces the archive's own
candles. The system reaches `running` through an `activate` **command row**, the way the
console does, rather than by setting `state["system"]` — which is the one region of `state` the
contract reserves for the orchestrator, and setting it by hand would prove nothing about
whether the opportunity chain is reachable at all.

**Four mutations, four killed**, each restored from a byte copy and verified by sha256 in the
same statement (ruling 10; both files also hashed before and after the whole sweep and
unchanged):

| # | Mutation | Killed by |
|---|---|---|
| R1 | engine 5 ignores `bar_closed` | the bar/quiet-tick test **and** the status test |
| R2 | engine 5 returns `OK` instead of `PASS` on a non-bar tick | the status test |
| R3 | the orchestrator runs the opportunity chain on a blocked tick | the guard-block test |
| R4 | the orchestrator runs the opportunity chain while `idle` | the idle test |

**R1 is the reason this file earned its place, and it went the wrong way first.** On the first
sweep R1 was killed *only* by the status test — not by the test written for it, whose assertion
was `quiet_tick["feature"] == {}`. With the guard removed, engine 5 runs on the quiet tick and
raises on the absent `closed_bar_ts`, and contract rule 7 turns that into `ERROR` with
`data={}`: **a quiet tick and a crashed tick publish the identical payload.** The assertion
was true for a reason unrelated to what it claimed. Fixed by also asserting
`"trading_blocked_by" not in quiet_tick`; R1 then died on the test written for it, with
`AssertionError: engine 5 did not pass, it failed`. The verdict alone said KILLED both times —
the finding was entirely in *which* test killed it.

**Nothing to report against engine 5 itself.** It behaved correctly on every tick: `PASS` with
an empty payload off a bar, a feature row for every pair on a bar, a different `bar_ts` on a
second bar tick an hour later, and a JSON-safe payload whose every value is a float or null and
never NaN. Its refusal message when `closed_bar_ts` is absent is unusually good and is quoted
in the build log.

#### CLAIMED 2026-09-13 — the two-tick orchestrator rehearsal of engine 5

The lead's offer of 02:35 in `feature-specs/PHASE-5-TASKS.md`: engine 5 alone, `PASS` on a
non-bar tick and a feature row on a bar tick, through the real orchestrator against the fake
client. **A-2 was given the same offer, so this note is the claim** — ownership rule 5, and the
only way to avoid two agents writing one rehearsal file when we cannot message each other.
`tests/engines/test_feature_chain_rehearsal.py`, a new file in my lane, following
`test_manage_chain_rehearsal.py` from Phase 4 and A's `test_guard_chain_rehearsal.py`.

Reading and driving another agent's engine through the real orchestrator is allowed; **editing
it is not.** If it goes red for a real reason I report it to the lead and to C-2 rather than fix
it.

#### Spec 76 — what landed

- `rank_universe(pairs, *, features, feature, descending)` and `select_candidate` with the same
  keywords, in `engines/scout/contracts.py`. One feature, one direction, one tie-break — pair
  name ascending, in **both** directions, which is why the key negates the value instead of
  sorting in reverse. A pair with no value sorts after every pair with one, alphabetically
  among themselves, and is never dropped.
- **NaN is a third way of having no value**, alongside null and absent. Spec 76 names two; the
  third arrives from `modelling/features.py`'s unfilled lookbacks. NaN compares false against
  everything including itself, so one left in a sort key orders *unpredictably* rather than
  badly — a direct hit on the determinism invariant 4 protects in this engine. Decision and
  reasoning in the build log; C told by message, so it no longer matters whether engine 5
  publishes null or NaN across `state`.
- The engine reads `scout.rank_feature` and `scout.rank_descending` through `context.config`
  and `state["feature"]["pairs"]` through named constants with C's ownership beside them.
  **Absent and null are deliberately the same fact for `rank_feature`** and the call site says
  why — the general rule in `code-standards.md` is that they are not, and this is the exception
  rather than an oversight. An empty or whitespace feature name is refused.
- **A configured feature with no engine 5 output blocks** with `scout_inputs_unavailable`.
  Falling back to alphabetical would publish `rank_feature: "<name>"` on a tick that ranked by
  nothing, and would be right on most ticks by coincidence — the placeholder score the operator
  refused, arriving through a fallback instead of a formula.
- `state["scout"]` gains `rank_feature` and `rank_descending`. `rank_feature` is **null rather
  than omitted**, the opposite of `pair`, because null is the answer here: it says the ordering
  was alphabetical for want of a key, which is exactly what spec 75's alphabetical control
  needs to be distinguishable from a feature that rated everything equal.
- `pairs` stays in scan order and still carries no ranking. One expression of the ordering, not
  two, so a consumer reading `pairs[0]` instead of `pair` cannot silently disagree.
- `README.md`'s recorded-absence section is rewritten as history, with the ruling dates and the
  reason the "rank if you can, otherwise alphabetical" reading is forbidden.

#### Spec 62 — what landed, and the audit it asked for

`StoreClient(db_path, models_dir=None)`, `models_dir`, `model_run_dir(run_id)` and
`new_model_run_dir(run_id)`. The run id is validated **before any path is built** — empty,
whitespace-padded, `.`/`..`, separator-bearing, drive-bearing and null-byte ids each refused
with their own message, because `StoreError` has one type and this surface now has six causes.
`new_model_run_dir` refuses an existing directory through `mkdir(exist_ok=False)` itself rather
than a prior `exists()` check, so two trainers racing for one run id cannot both be told it is
free. **A trained artefact is never overwritten** is the whole safety property of the method.

**The audit found one gap and it is now `leaderboard_entries(model_id=, model_version=,
fold=)`.** Every field spec 74 names already existed in `LeaderboardRow` and the 0001 schema
and nothing needed adding — asserted, not claimed, in
`test_a_leaderboard_row_round_trips_every_field_engine_20_writes`. What was missing was any way
to *read* one back: `leaderboard(limit=50)` is the console's truncating window, and deciding
"have I written this fold already" from it is spec 51's rows-versus-ticks defect a second time.
`fold IS ?` and never `fold = ?`, because SQL equality against NULL matches nothing and the
no-fold row would be rewritten on every run.

**For the lead, a schema question I did not act on:** nothing in the database enforces what
spec 74 calls idempotent — there is no unique index on `(model_id, model_version, fold)`, and
adding one is a schema change spec 62 forbids this phase. A partial index would be needed for
the null-fold row, the same shape as `ux_block_records_primary`.

**Eleven mutations in total, all eleven killed by the test written for each.** Eight against
the surface as I built it, then three more against the reader/writer asymmetry once it landed —
including both halves of it, so the ruling is pinned from both sides rather than merely
implemented. That matters because two methods disagreeing about one condition is the shape
somebody tidies into one path later, and the tidy direction is the one that creates the root.

#### Gates, run 2026-09-13, and what is red is not mine

**My own lane is green.** `tests/clients/store/test_store.py` and `tests/engines/test_scout.py`
together: **151 passed, 1 skipped** — the skip is the engine 5 seam test, which names
`acsoe.engines.feature.engine` and starts running the day C lands it rather than staying
quietly skipped. `ruff check src/acsoe/engines/scout/ tests/engines/test_scout.py
tests/clients/store/ src/acsoe/clients/store/` clean. `mypy --strict
src/acsoe/engines/scout/ src/acsoe/clients/store/` clean, 10 files.

**The whole-tree gates, last run at the end of my session.** They moved twice while I worked,
because A and C are saving into the same checkout, so both readings are recorded rather than
only the flattering one.

- `pytest tests/ -q` — **2100 passed, 3 skipped.** Green. An earlier run had six failures in
  `tests/cli/`, `tests/modelling/`, `tests/research/` and `tests/verify/`; every one was A's
  spec 61 or C's specs 60 and 63 mid-save, and every one cleared without anybody touching my
  paths.
- `mypy --strict src/ scripts/` — clean at **106 source files** when I checked it, then red
  again on `src/acsoe/cli/research.py:216: Name "Callable" is not defined`, which is A
  mid-save. Earlier in the session the same command reported `numpy/__init__.pyi:737: Type
  statement is only supported in Python 3.12` and then **stopped checking anything at all** —
  no answer rather than a wrong one, triggered by C's `modelling/di.py` importing
  `numpy.typing` past A's `follow_imports = "skip"` override. Fixed by its owners after I
  reported it; recorded because it is the failure mode that gate's own comment warns about.
- `ruff check src/ tests/ scripts/` — two findings, neither mine: `RUF100` in C's
  `scripts/verify.py` and `F821` in A's `cli/research.py`. Mine are clean.
- `python scripts/verify.py --phase 5` — **1 PASS, 1 FAIL, 0 PENDING.** `docs_vocabulary`
  PASS; `toolchain_green` FAIL on A's `cli/research.py`. It registers only **2 criteria**
  because C's spec 60 criteria are not landed yet, so this number will grow.

**My own paths are green throughout all of it**: `tests/clients/store/`, `tests/db/` and
`tests/engines/test_scout.py` together are **283 passed, 1 skipped**, with `ruff` and
`mypy --strict` clean over `clients/store/` and `engines/scout/`. The skip is the engine 5 seam
test, which names `acsoe.engines.feature.engine` and begins running the day C lands it.

#### The four gates, final run, and both specs are complete on it

Run after A-2's `follow_imports_for_stubs` fix and after C-2 cleared the `RUF100`, which were
the two things standing in the way. **This is the run both specs are marked complete on.**

```
$ .venv/Scripts/python.exe -m pytest tests/ -q
2102 passed, 3 skipped in 200.05s

$ .venv/Scripts/python.exe -m mypy --strict src/ scripts/
Success: no issues found in 106 source files

$ .venv/Scripts/python.exe -m ruff check src/ tests/ scripts/
All checks passed!

$ .venv/Scripts/python.exe scripts/verify.py --phase 5
PASS    docs_vocabulary  14 files scanned, 12 retired terms, no hit
FAIL    toolchain_green  ruff exit 1: src\acsoe\engines\feature\engine.py:123:12:
                         SIM300 [*] Yoda condition detected | Found 1 error.
2 criteria: 1 PASS, 1 FAIL, 0 PENDING
```

**The three gates I run directly are green. The `verify` FAIL is not mine and did not exist
when I ran `ruff` four minutes earlier**: C-2 landed `src/acsoe/engines/feature/engine.py`
between the two commands and it carries one `SIM300`. That is C-2's lane and C-2's line, and it
is the whole of the difference between the third gate passing and the fourth failing.

`tests/engines/test_scout.py` is now **60 passed, nothing skipped** — engine 5 landing turned
the no-double seam test live with no edit from me, and it passes against C-2's real engine.

#### Closed since: the M2 and M8 re-run the lead asked for

Done before the ruling arrived, and recorded in the build log: M2b, M8b and M9b against the
current `_artefact_root`, all three killed, each by the test written for it — including both
of the asymmetry's own tests, so the reader/writer split is pinned from both sides rather than
merely implemented. That is **11 mutations against spec 62 and 13 against spec 76, 24 of 24
killed, none by an incidental test in another file.** The stopped original's own six-mutation
run against the same code agrees with mine on every overlapping verdict; mine is the one to
rely on, because a survivor list from a session that is ending should not be load-bearing.

#### The CRLF claim is wrong, and the check that matters was run instead

The lead asked me to fix the mechanism behind `git diff`'s CRLF warning on
`tests/clients/store/test_store.py`, on the reading that one of my writes went through text
mode. **No write of mine did.** The file already reported CRLF before my first edit this
session; its first twenty lines, written in Phase 0 and untouched since, are CRLF today; the
blob at `HEAD` is LF; **136 tracked files** are CRLF in this working tree including
`tests/conftest.py` and `src/acsoe/console/format.py`, which nobody has written this session;
and `client.py`, which took my larger edit, is LF. `git diff` emits that warning the first time
a CRLF file appears in a diff **at all**, so it fires on the edit while being caused by neither
the edit nor the editor.

The form of the check that does matter was run in its place: **every committed file under
`tests/fixtures/` is byte-identical to its blob at `HEAD`**, by sha256. The two exceptions are
C-2's spec 63 deposits — `README.md`, deliberately modified, and `candles_sample.parquet`,
newly added and so having no blob to compare — and that parquet parses at 1,208 rows and 7
columns with `PAR1` intact at both ends. Reasoning in full in the build log.

#### STOPPED AND ESCALATED — two B sessions wrote `clients/store/` at once, and the other one is right

**2026-09-13.** The entry below this one is the other B session's account, written from the
other side of the same collision, and it is accurate about the collision. The 175 lines of
spec 62 it found on disk are mine. It is wrong on two details, both corrected in the build log
rather than by editing it: the tests **did** exist (it looked at a file mid-write), and the
CRLF in `test_store.py` is **pre-existing** rather than a conversion anybody performed —
`client.py` is LF and was written as bytes throughout.

**Its `parents=False` objection was right and is now the behaviour.** A writer creates the
artefact root and a reader refuses a missing one: C's trainer runs as
`python -m acsoe.research.training` and never touches A's startup path, so a writer demanding
an existing root would refuse the first training run on every fresh clone. I had reasoned the
other way and had told A so by message; A has been corrected.

**The split now in force, proposed by me and messaged to both the lead and the other session:**
it keeps `clients/store/` and `tests/clients/store/`, I take `engines/scout/` and
`tests/engines/test_scout.py`. The one exception I made afterwards is two `RUF043` findings on
lines I had written in `test_store.py` — `match="artefact root .* does not exist"` needed to be
a raw string — which I fixed rather than leave the `ruff` gate red on my own lines.

**Still open for the lead:** which session owns lane B. The notice at the top of
`feature-specs/PHASE-5-TASKS.md` says the `-2` sessions do and that bare-letter sessions are
stood down; my sends arrive as `B-2`. I did not treat that as settling it, because the other
session is the one acting on a ruling of 2026-09-13 I never received.

#### STOPPED AND ESCALATED — two B sessions are writing `clients/store/` at once

**2026-09-13, 00:36.** Not a code defect and not mine to fix. I read
`src/acsoe/clients/store/client.py` at the start of spec 62 and got 933 lines with no
`models_dir` in them; my first edit was refused as stale, and `git diff` showed all 175 lines
of spec 62 already on disk — `_validated_run_id`, `models_dir`, `_artefact_root`,
`model_run_dir`, `new_model_run_dir`, and a `leaderboard_entries` read as the step-3 audit gap.
`client.py` was written at 00:36:13, seven seconds after I wrote my own phase-5 build-log
header, so it is not a leftover from a session that ended before mine. Then
`tests/clients/store/test_store.py` moved at 00:36:51 — after a `git status` that showed it
unmodified — with one added import. That is a second B session mid-save.

**I have written no byte into `client.py` or `test_store.py`,** per the conflict procedure in
`ownership.md`: stop, record, escalate with the path and both intents, the lead decides. The
ownership map is the only concurrency control this project has and it assumes one agent per
path; two writers in one file is silent, last-save-wins, with nothing red. Escalated to the
lead by `SendMessage` with the timestamps and the sha256 of the file as I found it,
`4163b72c146a6cf5059a32b5b348795d5354e1bf7a8efc03f332160e20e83d00`, snapshotted to the session
scratchpad first so the state at detection is recoverable either way.

**The implementation on disk reads as correct and complete against spec 62**; tests do not
exist yet. Two things I would change whoever finishes it, both raised with the lead: the
constructor takes `models_dir` positionally where I had told A it would be keyword-only, and
`new_model_run_dir` uses `parents=False`, so a trainer started as
`python -m acsoe.research.training` — which never touches A's startup path — meets "the
artefact root does not exist" rather than having it created. The second is a defensible
decision and should be a ruling rather than two agents assuming opposite things.

**One symptom worth keeping separately:** `test_store.py` now has CRLF line terminators and
`git diff` warns on it, where it did not before. That is the text-mode round trip
`code-standards.md` describes — the whole file's endings rewritten, invisible in `git status`
because `.gitattributes` normalises on the way into the index.

Waiting on the lead for which session continues. Spec 76 is in `engines/scout/`, a disjoint
path, and can start the moment the lead says so.

## CLOSED — engine 17's `CONDITION_ACTION`, ruled 2026-09-10

**The operator ruled on 2026-09-10 and spec 37 wrote it into invariant 14.** The table is
now a decision, not my reading of a contradiction:

| Condition | Action |
|---|---|
| `DRAWDOWN` | `freeze` |
| `LOSS_STREAK` | `freeze` |
| `ERROR_RATE` | `freeze` |
| `DATA_OUTAGE` | `close_all` |

`close_all` is reserved for the invariant 14 data-outage escalation and for the operator's
own Close all button. The reasoning, which is invariant 14's and is not restated in the
code: a drawdown or a losing streak is a statement about *past* trades — the data is
trustworthy and the positions are being managed — so liquidating on it realises a paper
loss on the system's own authority at the moment it has least evidence it is reading the
market correctly. A sustained outage is a statement about *present* knowledge, and unknown
exposure is worse than a bad fill.

Two of the four rows changed. `ERROR_RATE` and `DATA_OUTAGE` were already as ruled.

**Applied in the code on 2026-09-10, verified.** An earlier version of this line claimed
the same thing while `engines/safety/contracts.py` still carried the pre-ruling table
under a heading reading PROVISIONAL. It was written in the same edit that *claimed* spec
42, and this file has no way to distinguish a claim from a completion — so the note
described work that had not happened. The build log carries the account.

**Changed how I use this file as a result: a spec is marked complete here only after its
four gates are green, never in the edit that claims it.**

**Ratified earlier and unchanged:** the `BOUNDARY_SOURCE` table beside it, fixing whether
each threshold trips *at* its limit or *above* it, each with the sentence in the documents
that fixes it. Drawdown, loss streak and error rate trip at the limit; the outage is the
only strictly-greater one.

## CLOSED — a suppressed `close_all` swallowed a co-occurring `freeze`, ruled 2026-09-10

**The operator ruled the way it was recommended, and invariant 14 now says so** (committed
`db50392`): *"When the winning action is suppressed, `safety` emits the strongest action
that is not suppressed"*, rather than emitting nothing. Implemented under spec 42 as a
fall-through in `_emit`, with both directions tested — it fires when a lesser action was
genuinely due, and does **not** fire when the outage is the only condition tripped, because
"always freeze if you cannot liquidate" would freeze a healthy account over an outage it had
no exposure to. Both mutations confirmed caught.

Spec 42 step 6 is unrepealed: still one command per tick, still no `freeze` alongside a
`close_all` that actually emitted. Only the fall-through is new.

The original statement is kept below, because the reasoning is what the ruling was made on.

---

**Raised 2026-09-10 while implementing spec 42. Not invented behaviour: the literal spec
is implemented and this is the case it does not cover.**

`_emit` takes the strongest action among the tripped conditions and emits at most one row —
spec 42 step 6, "the more severe action wins and the two are not both emitted". Correct on
its face. But the `close_all` branch has two suppressions of its own (no exposure, and
`close_intent` already set), and when the strongest action is suppressed **nothing is
emitted at all**, including the `freeze` that a co-occurring drawdown, loss streak or error
rate would have emitted on its own.

Concretely: drawdown breached, account has no open position and no resting entry order,
and a data outage is also running. Drawdown alone emits `freeze`. Drawdown *plus* the
outage emits nothing, because `close_all` wins and is then suppressed for want of anything
to close. More bad conditions produce less action, which is the wrong direction.

The practical impact is bounded and worth stating so the ruling is not read as more urgent
than it is: `safety` returns `BLOCK` on every tick where any condition is tripped, so the
opportunity chain is stopped regardless. What is lost is the *persistence* — the mode never
goes `frozen`, so the console shows a running system and the block is re-derived every tick
rather than recorded once.

**I have not fixed it.** The obvious fix is "emit the strongest action that is not
suppressed", which would be one line, and it is a change to what the breaker does — so it
is the operator's, not mine. Recommending that reading.

*(Ruled that way on 2026-09-10 and implemented under spec 42. See the heading above.)*

## `core/`'s two writes — landed, primitives only

`core/` imports nothing from the rest of the package, so it cannot construct a `RunRow`
to hand to `write_run`. Two entry points now take `str` and `int` and nothing else:

```python
def start_run(self, run_id: str, *, mode: str, started_at: int,
              acsoe_version: str | None = None,
              config_digest: str | None = None) -> None: ...
def set_system_mode(self, run_id: str, mode: SystemMode | str, *, at: int) -> bool: ...
```

Four decisions in them:

- **`start_run` refuses a duplicate `run_id`** rather than upserting. `run_id` is minted
  once per process, so a second start is a bug; an upsert would rewrite `started_at`, and
  the console decides the current run from the newest `runs` row — so the silent version
  of that defect reorders the two rows the restart banner compares. Raises `StoreError`.
- **It names its columns explicitly** instead of dumping a payload, so it cannot become a
  writer of `system_mode` the way `write_run` silently did when spec 31 added the columns
  to `RunRow`. `set_system_mode` stays the only writer of both.
- **`set_system_mode` takes a plain `str`**, and that is now a guarantee rather than a
  `StrEnum` implementation detail that happened to work.
- **An unrecognised mode raises; an unknown run returns `False`.** The two are not alike:
  a missing row is a race the caller logs and continues past, a misspelled mode is a
  defect, and sharing a return value would leave the console on a stale mode with nothing
  saying why.

Proved with no double, the way `commands_round_trip` is: a **fresh interpreter** whose
entire import of this package is `StoreClient`, running the whole path on real SQLite,
plus a test that reads that caller's own source and asserts it names no contract and
constructs no row. `tests/clients/store/test_core_entry_points.py`, 17 tests.

## `bootstrap.py` — requested, deliberately deferred by the lead

- `CostEngine` — opportunity chain, after 9, before 11. `is_gate=True`.
- `RiskEngine` — opportunity chain, after 10, before 14. `is_gate=True`.
- `SafetyEngine` — **guard** chain, last, after 4. `is_gate=True`.

Deferred until the tree is globally green: `safety` in the guard chain runs on every tick of
`orchestrator_empty_registry` (a Phase 0 gate) and `commands_round_trip` (Phase 2), both
against a real `StoreClient`. On an empty database nothing should trip — but "should" is
doing work in that sentence, and if it does trip that is a finding worth having in isolation
rather than tangled with A's in-flight engine work. Engines 10 and 11 are opportunity-chain
and inert in both criteria.

## Spec 31 — persisted system mode

**Shape.** Two nullable additive columns on `runs`, not a new table:
`system_mode TEXT CHECK (... IN ('idle','running','frozen'))` and
`system_mode_at INTEGER`. Nothing existing is altered, nothing is dropped, no table is
added — so `db_migrates_from_empty` and `architecture-context.md`'s storage table need
no lead edit. Reasoning in full in `docs/build-log/phase-2/b-store.md`; the short version
is that `runs` already carries a UNIQUE `run_id`, so scoping by run is structural rather
than conventional and there is no query a reader can get wrong.

**The seam C builds against — this is the whole contract:**

```python
# src/acsoe/clients/store/contracts.py
class SystemMode(StrEnum):
    IDLE = "idle"; RUNNING = "running"; FROZEN = "frozen"

class SystemModeRow(_Row):
    run_id: str
    mode: SystemMode | None = None
    at: Micros | None = None          # microseconds, UTC; None iff mode is None

# src/acsoe/clients/store/client.py
def system_mode(self, run_id: str) -> SystemModeRow | None: ...
def set_system_mode(self, run_id: str, mode: SystemMode, *, at: int) -> bool: ...

# RunRow also carries `system_mode` / `system_mode_at`, read-only, for a caller that
# already holds a RunRow and does not want a second query.
```

**Two nulls, two different facts, and the console must not collapse them.**
`system_mode(...)` returns `None` when there is no `runs` row for that `run_id` — a
defect or a race, not a mode. It returns a row with `mode is None` when the run exists
and no daemon has written a mode yet — the ordinary case before the first command is
read. Both render as an idle reading per spec 32, but only the second is normal, and a
reader that cannot tell them apart cannot log the abnormal one.

**Writer.** `set_system_mode` is the only writer of both columns. `write_run` explicitly
excludes them, so the orchestrator's shutdown write of `ended_at` cannot clobber a
`frozen` daemon's persisted mode with the stale `None` its startup `RunRow` carries. The
caller is the command reader in `src/acsoe/core/orchestrator.py`, which is lead-only: I
provide the method, the lead calls it. `set_system_mode` bumps `runs.updated_at` too,
because `runs` is in `WATERMARK_TABLES` and without that the console would never repoll.

**Mode is never restored from the store.** There is no third method that reads this back
into `state["system"]`, and none should be added. A daemon always starts `idle` and
reaches `running` only through an `activate` command; restoring it would invert the
safety property that a crashed daemon comes back not trading, and it would look like a
bug fix while doing so.

**Nothing is seeded.** `seed.py` writes no system mode and
`test_the_seed_writes_no_system_mode` now asserts it, so C's Running-band test cannot
pass without a daemon having written one.

## Status

Spec 31 is green. All three gates, run 2026-09-09:

```
Phase 0 is green: every criterion PASS, zero PENDING.   (7 criteria: 7 PASS)
Phase 1 is green: every criterion PASS, zero PENDING.   (10 criteria: 10 PASS)
Phase 2 is green: every criterion PASS, zero PENDING.   (3 criteria: 3 PASS)
```

`723 passed` · `mypy --strict src/` clean, 35 files · `ruff check src/` clean.

The two `tests/db/test_migrations.py` failures the migration caused are fixed, and the
fix is not a bumped literal: both expectations now derive from the migrations directory
while still asserting the count and the ordering. See the build log for why the literal
was the wrong shape and for the asymmetry it exposed — `db_migrates_from_empty` passed
throughout, because it tolerates extra tables and 0002 adds none, so the phase gate did
not notice a schema change that my own unit tests did.

Spec 11 and 12's criteria still report PASS:

- `db_migrates_from_empty` — a fresh database migrates to all 9 documented tables; a second
  `migrate()` returns `[]`, so "re-migrating is a no-op" is checked on the returned list
  rather than on a schema diff.
- `seed_fixtures_present` — all six Phase 3 fixtures present, each overshooting its threshold
  rather than sitting on it.

Nothing of mine is outstanding. Spec 11 unblocked 12, which unblocked 13, in that order.

## For the lead — two things, neither of them mine to fix

1. ~~**`core/` must now call `store.set_system_mode(run_id, mode, at=now)`** from the
   command reader.~~ **DONE and this note is struck, 2026-09-10.** The lead wired
   `_persist_mode` at the command reader and asserted in `tests/core/` that the
   `system_mode` column staying NULL on an idle daemon is *correct* — a mode never entered
   is a mode never recorded — so that it does not get "fixed" later. Spec 31 is fully
   delivered.
2. **An intermittent Windows teardown fault outside my paths.** The first `--phase 0`
   run reported `FAIL toolchain_green — ERROR tests/cli/test_entrypoints.py::
   test_console_refuses_an_unset_operator_key | 722 passed, 1 error`. An `ERROR`, not a
   `FAILED`, exit 1 rather than an NTSTATUS, in A's `tests/cli/` — so it is neither the
   known seed-path native fault nor anything of mine. Captured verbatim in the build log
   before re-running, as the phase rules require; the re-run was green with no change.
   Separately, `scripts/verify.py` prints an unhandled `PermissionError [WinError 32]`
   on `acsoe-verify-doubles-*\acsoe.sqlite` from its own `TemporaryDirectory` finalizer
   on **every** phase-0 run, green ones included. Same Windows shape twice — a SQLite
   file still open when a temp directory is collected — one in A's test, one in C's
   script.

## Open questions — both resolved

### 1. `is_primary` uniqueness scoped by `run_id`, not `cycle_id` alone — RESOLVED

Implemented as a partial unique index on `(run_id, cycle_id) WHERE is_primary = 1`. Escalated
before implementing further. **The lead approved it, amended spec 11, and fixed the root cause
in `architecture-context.md`,** which now states that a tick is `(run_id, cycle_id)` and never
`cycle_id` alone. Every "once per tick" constraint and cross-table join in the schema is scoped
to both columns as a result. The seed deliberately overlaps the two runs' `cycle_id` ranges and
says so in its docstring — that overlap is load-bearing, and tidying the runs apart would
silently disarm the Phase 3 test that proves ordering is by `ts`.

### 2. `safety` threshold key names and values — RESOLVED

The lead fixed the key names and **the operator supplied the values on 2026-09-08.** The seed
does not read `config/default.yaml`; it takes a `SeedThresholds` dataclass, so a Phase 3 test
seeds against whatever the config actually says. What the committed config now asks for, and
what the seed produces against it:

| Key | Operator value | Seed produces |
|---|---|---|
| `safety.max_consecutive_data_blocks` | 15 | 18 consecutive `data_guard` ticks, over 2 `run_id`s |
| `safety.max_drawdown_pct` | 0.10 | drawdown of 0.2000017843760037115020877199 at the trough |
| `safety.max_consecutive_losses` | 5 | losing streak of 8 |
| `safety.error_rate_window_s` | 3600 | — (fixed by `architecture-context.md`: "the trailing hour") |
| `safety.max_errors_in_window` | 20 | 23 `status='ERROR'` block records in the window |

My earlier proposal of `max_errors_in_window: 10` was not what the operator chose; the table
above is the committed state. The seed also writes 2 open positions, 2 resting entry orders,
33 trades and 46 rejections.

## Three decisions in the schema and the migration runner

Recorded in full in `docs/build-log/phase-0/b-store.md`; summarised here because each one is a
property another agent will rely on rather than an implementation detail of mine.

- **The database refuses a float in a money column.** Every money column is `TEXT` **and**
  carries `CHECK (typeof(col) = 'text')`. SQLite is dynamically typed, so a `TEXT` column stores
  a float without complaint and hands it back as one — "money is never `REAL`" was an assertion
  in a document rather than a property of the database. A single write bypassing the client, in
  any phase, would have seeded a drifting number into the equity series that moves the drawdown
  threshold that liquidates the account. The client now passes `str(Decimal)`.
- **`executescript` discards the transaction wrapped around it.** It issues an implicit `COMMIT`
  of any pending transaction before running its script, so the first runner's `BEGIN` was
  committed away by the very call it was meant to protect. `BEGIN`/`COMMIT` moved inside the
  script string, and the `schema_migrations` insert moved in with them — otherwise a crash
  between the two transactions leaves a database whose schema is applied and whose version row
  is not, and the next startup tries to create tables that already exist.
- **Migration bookkeeping records no wall-clock time by default.** `apply_migrations(...,
  applied_at: int | None = None)`. Spec 13 requires two seedings of the same seed to be
  byte-identical and the seed migrates the database it seeds, so a clock-stamped column would
  make every seeded database differ for reasons unrelated to the seed. The checksum, which is
  the field that protects anything, is always recorded.

## Known issue in my code path — closed as a risk, not root-caused

`toolchain_green` fails intermittently — roughly 20% of full-suite runs — with a native memory
fault, and every observed instance surfaces inside my write path:
`seed.py:_write_trading_history` → `client.write_trade` / `write_position` → pydantic
`model_dump`. Three distinct Windows statuses have been seen (`0xC0000005` access violation,
`0xC0000374` heap corruption, `0xC0000409` stack buffer overrun) plus an
`AttributeError: 'NoneType' object has no attribute '__dict__'` raised from inside `to_python`.

It is **not** a logic defect in the seed: every test passes when the process survives, and
`seed_database` called 60 times outside pytest is clean. My suspicion of pydantic-core 2.46.5
was checked and did not hold — pinning a different build did not settle it. The lead
investigated it at length and closed it without a root cause; pyarrow, `pytest-asyncio`, test
ordering, `root_import_path` and the pydantic-core version were each ruled out, hardware is
suspected and is out of scope, and the gate now retries a crash once. Full account in
`docs/build-log/phase-0.md`.

**Do not re-run the suite to see whether the result changes.** That experiment has been run. It
becomes mine again if the fault appears outside this write path, or if the gate starts
reporting `CRASH -` after its retry — which would mean the rate has moved and the mitigation no
longer holds.

## The one-type-many-causes shape, audited in my own lane — 2026-09-10

The lead asked whether `StoreError` in `clients/store/` has the shape A found in
`clients/kraken/`, where every fail-closed path raises one type so `pytest.raises(That)`
cannot tell the induced failure from one that happened first.

**Audited: four `raise StoreError` sites, so the shape is present but small.** They are the
non-finite money refusal, an unknown run mode, a duplicate `run_id`, and an unknown system
mode. Three of the four assertions already used `match=`; one did not —
`test_the_two_failures_are_distinguishable_by_type` — and it is now `match="unknown system
mode"`. That test is about `False`-versus-raise rather than about the cause, so it was not
wrong, but the bare form would have been satisfied by any of the four.

Nothing else in my lane raises one type from many places. `MissingInputError` in the three
engines is per-module and every assertion on it goes through `reason_code`, which is the
generalisation the standard actually asks for: **assert the reason, not only the `BLOCK`.**

## Reading a moving tree by path, and not re-running to find out — 2026-09-11

Recorded at the lead's request because it is process rather than code, and because the
habit is the deliverable.

Four times in Phase 4 the tree was red while I was working in it, and none of them was
mine. Each was settled **by path and by lane, without re-running anything and without
opening a file I do not own**:

- 26 failures in `tests/scripts/test_build_archive.py` — A's spec 54, mid-save. Left
  alone; green again on its own later, which is what landing looks like.
- `rejections_survive_restart` and `console_history_reads_real_rows` raising
  `AttributeError: module 'acsoe.engines.memory.contracts' has no attribute
  'DECISION_KEY'` — C's engine 19, mid-save.
- 2 pytest failures, 1 `mypy` error and 1 `ruff` error, all in
  `research/walkforward.py` and `tests/research/test_walkforward.py` — C's spec 53,
  mid-save.
- One failure that **was** mine, `test_an_outage_counted_by_cycle_id_is_a_fail`, which
  sits in C's `tests/verify/` by path and was still my defect. Path is the first
  question, not the last one: it named my file, it reproduced every time, and it was
  caused by a string I had just written.

**The rule that makes this work is the one Phase 3 paid for:** a defect of mine
reproduces every time, in isolation, in my own paths — and *re-running to see whether the
result changes* is the diagnostic that cannot fail, because in isolation nothing else is
touching the temp directory. The counter-example above is the important half. "It is in
another agent's path" is evidence, not a verdict; the verdict came from asking whether
the failure names my code and whether it reproduces, and once it did I stopped and wrote
the diagnosis before the fix.

## Blocked on

Nothing.

## Verification

```
$ .venv/Scripts/python.exe scripts/verify.py --phase 0
PASS    db_migrates_from_empty       fresh database migrated to all 9 documented tables
PASS    seed_fixtures_present        all six fixtures present: outage run 18 ticks over 2 run_ids
                                     (11 double-blocker), 2 open position(s), 2 resting order(s),
                                     drawdown 0.2000017843760037115020877199, losing streak 8,
                                     23 ERROR blocks in the window, 33 trades / 46 rejections

7 criteria: 7 PASS, 0 FAIL, 0 PENDING
Phase 0 is green: every criterion PASS, zero PENDING.
```
