# Build log — Phase 7 — b-store

Entries are appended as work happens, following `context/script-rules.md`. Each entry is written
at diagnosis, before the fix. Each how-decision names the option it rejected. Each assertion is
proven by mutation, starting from a byte copy, and the hash is checked on restore.

### Decision: the approval economics wait for the trade in a write-once `approvals` table, not in columns on `orders`

**Agent:** B-store · **Task:** spec 132 · **Date:** 2026-09-19

**Options.** Spec 133 puts the question to B: where do the placing tick's expected move,
friction, net edge, hurdle and model run ids live until engine 19 writes the `trades` row, which
happens ticks later? The two options were (a) seven nullable columns on `orders`, and (b) a small
table keyed by the entry order's `userref`.

**Chose (b).** `approvals` is insert-only. A second write for the same `userref` raises
`IntegrityError`. `trades` gains the same seven columns, which engine 19 copies from
`store.approval(entry_userref)` when it writes the trade.

**Because.** Option (a) loses the figures silently. `StoreClient.write_order` upserts **every**
column, and engine 21 builds its fill and cancel rows from scratch (`_fill` and `_cancelled_row`
in `engines/position_manager/engine.py`), so the fill-tick write would overwrite the economics
with NULL. The same happens when the placement and the fill land on one tick, because engine 19
writes engine 18's row and then engine 21's. Keeping them under (a) would need one of two things:
- `COALESCE` semantics hidden in one table's upsert, which no reader of `_upsert` would expect; or
- engine 21 carrying figures that are not its business.

There is a second reason. The order row's `cycle_id` is rewritten by every later tick (F-new-2,
prerequisite 8). An insert-only row keeps the placing tick's `(run_id, cycle_id)` true by
construction, which is the join Phase 7's attribution wants.

**Cost.** A tenth table, so there is work outside my lane in the same gate:
- `scripts/verify.py` `DOCUMENTED_TABLES` (C) must gain `approvals`, or `db_migrates_from_empty`
  FAILs on `EXPECTED_TABLES` disagreeing;
- `architecture-context.md`'s storage table (lead) must gain its row.

Both were told on 2026-09-19.

### My spec 132 mutation sweep ran over the lead's phase-7 gate

**Agent:** B-store · **Task:** spec 132 · **Date:** 2026-09-19

**What happened.** I swept 13 mutations over the store and migration 0006 while the lead's
`verify.py --phase 7` gate (started 05:08) was running the full suite in this checkout. Each mutant
lived on disk for 1 to 25 seconds. Every one was restored from a byte copy and its hash verified.
Any test in the gate that imported the store during that window could have seen a mutant. That
gives a spurious FAIL, or a false PASS, in someone else's verdict. Separately, I started
`verify.py --phase 0` to check `db_migrates_from_empty` and forgot that `toolchain_green` runs the
full 30-minute suite, which the team brief forbids teammates to run. I stopped it after about 10
minutes and checked that it had left no child process.

**Why.** `code-standards.md` already names both hazards: a harness in a shared checkout can turn
another agent's run red, and a gate criterion is not a cheap probe. I checked neither what else
was running nor what the criterion invoked.

**Fix.** I told the lead to treat that gate as unreliable on store paths. The harness
(`scratchpad/mutate.py`) now refuses to start while any `verify.py` or `pytest tests/` process is
alive. Single criteria are checked by calling the criterion function, never the phase.

### Spec 132 mutation sweep: 13 arms, 13 killed, one of them only after the test was widened

**Agent:** B-store · **Task:** spec 132 · **Date:** 2026-09-19

The sweep ran with `PYTHONDONTWRITEBYTECODE=1` over `tests/clients/store tests/db` (baseline 301
passed). Every arm was applied from a byte copy with its anchor asserted to occur exactly once,
restored before the next arm, and hash-verified. Every verdict carries a pytest summary. **This
sweep overlapped the lead's gate (entry above).**

Killed, each by the test named for it:
- M1: CHECK dropped on `approvals.expected_move_pct`. Killed by the float-refused-by-database test.
- M2: `DEFAULT '0'` on `trades.net_edge_pct`. Killed by the pre-0006-rows-read-absent test.
- M3: `write_approval` upserts. Killed by the second-approval-refused test.
- M4: `write_run` writes the scenario. Killed by the write-run-never-erases test.
- M5: `start_run` drops the digest. Killed by the scenario round-trip test.
- M6: `approval()` reads the wrong userref. Killed by the approval round-trip test.
- M7: `TradeRow.expected_move_pct` typed as a plain `Decimal`. Killed by the float-refused-by-models test.
- M8: the blank-text validator disabled. Killed by the blank-run-id test.
- M9: `start_run`'s blank check removed. Killed by the blank-scenario test, which expects
  `StoreError`, not the database's `IntegrityError`.
- M10: `approvals` removed from `EXPECTED_TABLES`. Killed by `test_table_and_index_sets_match_the_contract`.
- M11: the blank CHECK dropped on `runs.scenario_digest`. Killed by the blank-scenario test.
- M12: the blank CHECK dropped on `approvals.anomaly_run_id`. Killed by the blank-run-id test.
- M13: the blank CHECK dropped on `trades.skeptic_run_id`.

**M13 SURVIVED at first.** The database half of the blank-run-id test checked only `approvals`,
so the same CHECK on `trades` had no test at all. I widened the test to update both tables and
to match the constraint's column name. Re-run, M13 was killed (24 passed, 1 failed) and M12 was
still killed.

### Engine 7's four files were all CRLF in the working tree, which disarms every literal-anchor patch

**Agent:** B-store · **Task:** spec 144 · **Date:** 2026-09-19

**What happened.** A patch script against `engines/scout/contracts.py` found its anchor zero times,
even though the text matched character for character.

**Why.** `contracts.py`, `engine.py`, `README.md` and `tests/engines/test_scout.py` were CRLF
throughout: 648, 595, 297 and 1731 CRLF, with no bare LF. The committed blobs are LF, and
`.gitattributes` normalises on the way in, so `git status` showed nothing. This is the mechanism
`code-standards.md` records. It predates this session, because the scout files had not been
touched since Phase 5.

**Fix.** I rewrote all four as LF bytes. `git diff` for `engine.py`, `README.md` and the test file
was empty afterwards, which confirms the change was line endings only. From then on I counted
CRLF in Python before every sweep.

### Decisions in engine 7's half of spec 144, each with the option rejected

**Agent:** B-store · **Task:** spec 144 · **Date:** 2026-09-19

1. **Signature: C's, not my proposal.** I proposed a
   `rank_by_expected_move(artefacts, pairs, rows, macro)` that took run ids. C landed
   `load_ranking_artefacts(prediction_dir, anomaly_dir)` and
   `rank_by_expected_move(rows, macro, artefacts, *, target_pct, stop_pct)`. That returns
   `Ranking(ranked, excluded)`, and the exclusion codes are the gates' own reason codes. I adapted
   to it. *Rejected:* asking C to change a landed, tested module to match a proposal it had not
   seen before building. Its shape is at least as good. It reuses the gates' vocabulary rather
   than a third set of codes.
2. **A universe the ranking skips entirely is `PASS` with a new code, `no_rankable_pair`.**
   *Rejected:* `empty_universe`, because it would tell the operator the account can trade nothing
   when it can. Also rejected: falling back to alphabetical. That would examine a pair every gate
   would refuse, and it contradicts `q_emrank.py`, which takes no pair on such a bar. It is not a
   `BLOCK`, because nothing failed: the gates would have refused every candidate anyway. C landed
   the prose before the engine was finished.
3. **Every universe pair goes to the function, including pairs engine 5 published no row for.**
   Those go in as `None`, which the function counts as `anomaly_inputs_incomplete`. *Rejected:*
   dropping them before the call. The pair would then vanish from `rank_skipped`, and the skip
   tally would no longer account for the universe.
4. **`scout.rank_descending` is honoured for the expected-move ranking too.** It already means
   "which end", with a default of `true`. *Rejected:* ignoring it for this ranking. A config key
   that silently stops meaning anything for one value is the placeholder shape the operator
   refused. It also gives the reversal proof a real, configured way to reverse.
5. **The model is loaded only when the filtered universe is non-empty.** *Rejected:* loading on
   every configured tick. That would turn a fresh clone's routine empty universe into a block,
   for want of a model nothing would have been asked about. A missing run id therefore blocks
   only on a tick that had something to rank. That is the fail-closed reading of "unable to rank
   what is here", and it is written in the README.
6. **`rank_universe` still does the sort, from the function's expected moves, rather than
   echoing the function's order.** *Rejected:* taking `Ranking.ranked`'s order as given. That
   would leave the seam the tracker names untestable on its own. The no-double test asserts that
   the two orders agree.
7. **The chosen-pair check.** Engine 8's published `expected_move_pct` is compared with engine
   7's published value as the rendered string. Both are `Decimal(repr(float))`, so a
   last-digit difference shows.

### The scratchpad is shared by the whole team, and my harness was overwritten under a queued sweep

**Agent:** B-store · **Task:** spec 144 · **Date:** 2026-09-19

**What happened.** At 05:47 another teammate wrote its own `scratchpad/mutate.py` over mine. It
takes `<arms.json> <target file> <pytest args>`. I had a sweep queued to launch `mutate.py` once
the lead's gate ended. It would have run their harness with my arguments. That would have crashed
at `sys.argv[2]` before writing anything, so no mutant was applied, but a compatible CLI would
have applied my arms under someone else's restore logic.

**Why.** Every teammate gets the same scratchpad path, and generic names collide.

**Fix.** I stopped the queued sweep. My harness and arms now live in `scratchpad/b-store/`. I told
the lead so the rule can be broadcast.

### Spec 144 mutation sweep: 22 arms, 22 killed, every kill by the test written for it

**Agent:** B-store · **Task:** spec 144 · **Date:** 2026-09-19

The sweep used my own harness (`scratchpad/b-store/mutate.py`) with `PYTHONDONTWRITEBYTECODE=1`
over `tests/engines/test_scout_ranking.py tests/engines/test_scout.py` (baseline 84 passed). Each
arm applied a single anchor from a byte copy, restored in `finally`, and verified the hash; every
verdict carries a pytest summary. The harness waits for any `verify.py` or `pytest tests/ -q`
process before each arm. **Arms S5 and S6 may still have been on disk when the lead's 06:20 gate
started**, which the per-arm check cannot prevent, and I told the lead.

Contracts (`rank_universe`):
- S1: a pass-through order. Killed, 8 tests.
- S2: a skipped pair sorted last rather than dropped.
- S3: the direction ignored. Killed by the direct test and by the no-double reversal test.
- S4: no name tie-break.
- S5: NaN kept.
- S6: None moves read as empty.

Engine:
- S7: the last pair taken as the candidate.
- S8: every row handed in, not just the universe's.
- S9: `no_rankable_pair` reported as `empty_universe`.
- S10: never reloaded on a changed run id.
- S11: reloaded every tick.
- S12: any `ModuleNotFoundError` read as the module missing.
- S13: `expected_move` checked against engine 5's names. Killed, 15 tests.
- S14: macro not passed.
- S15: barriers swapped. Killed by the stand-in call and by the real test's direct comparison.
- S16: skip tally dropped.
- S17: the published move carries the float's binary expansion. Killed by the stand-in and by
  the no-double engine 8 comparison.
- S18: loaded on an empty universe.
- S19: run ids crossed.
- S20: the anomaly run loaded from the prediction id.
- S21: a refused ranking falls back to alphabetical.
- S22: a blank run id accepted.

**Checked negative, stated rather than hidden.** One assertion was not proven capable of failing
by a mutation in my lane. That is the half of the reversal proof saying no gate's verdict
changes. A mutant that makes it fail would have to make engine 13 or 8 read `state["scout"]`
beyond `pair`, and those engines are C's. The assertion compares full payloads, minus timing,
under two scout payloads that differ in `rank_descending` and `ranked`. So any such read would
show. Mutating C's engines to prove it is a cross-lane mutation, and I did not do it.

**Seen while re-running the neighbours:** `tests/engines/test_trade_chain_rehearsal.py` (A's) has
4 failures. The cause is c-eval's spec 133: the recorded `trades` row now carries the approval
economics, and the rehearsal's expected row is built from engine 22's payload alone. It is not a
defect of 132 or 144. I told c-eval so they can agree the change with A.

### `approvals.details` added to 0006 before its first commit (spec 145)

**Agent:** B-store · **Task:** specs 132 and 145 · **Date:** 2026-09-19

Following the operator's ruling on spec 145, `approvals.details TEXT` went into
`0006_approval_economics.sql` while 0006 was still uncommitted, so no 0007 was needed. The column
is nullable, and a blank string is refused by `trim(details) <> ''`. It holds engine 19's
canonical JSON. `ApprovalRow.details` carries it through the same blank-refusing validator as the
run ids. The store treats the text as opaque, so it neither parses nor normalises it.
`approval()` reads it through `SELECT *`. `rejections.details` is untouched.

The tests are in `test_approval_economics.py`:
- the round trip returns the snapshot byte for byte;
- migrating from 0005 gives a nullable column with no default, and an approval written without
  details reads back `None`;
- a blank value is refused by both the model and the database.

Sweep (the same harness, `tests/clients/store/test_approval_economics.py tests/db/test_migrations.py`,
baseline 75 passed), 5/5 killed:
- D1: the column dropped from the migration. Killed, 13 tests.
- D2: the blank CHECK dropped.
- D3: `DEFAULT '{}'`, killed by the absent-after-migration test.
- D4: the model validator removed.
- D5: the text altered on the way in, killed by the byte-for-byte round trip.

This entry also records a slip. I edited the arms file through a bash heredoc, and the `\n`
escapes were eaten above the shell, which is exactly the mechanism `code-standards.md` names. The
arms file then failed to parse and nothing was applied. I fixed it with the file tool.

### Decision: the SHAP surface for spec 140 is one write-once Parquet file per decision, under a new `derived_dir`

**Agent:** B-store · **Task:** spec 140 (store half) · **Date:** 2026-09-19

**Options and choices.** c-eval proposed `write_shap(...) -> shap_ref` and `read_shap(shap_ref)`.
I accepted both, with three amendments.

1. **Empty contributions are refused.** Engine 8 publishes `shap: {}` when it cannot read `shap`'s
   output, and that must stay absent, with a null `shap_ref`. *Rejected:* writing an empty file,
   which would look like an explanation that attributes nothing.
2. **The path is `shap/<run_id>/<cycle_id>/<quote(pair)>.parquet`**, so `(run, tick, pair)` is
   unique by construction and the pair's `/` is reversibly escaped. *Rejected:* the seed's
   per-tick spelling `shap/<run_id>/<cycle_id>`, which makes uniqueness depend on one candidate
   per tick. Also rejected: batching many decisions into one file, which is a merge problem with
   no reader asking for it tonight. The cost is about 17k small files per six-month run.
3. **`read_shap` returns a `ShapRecord`**, including `model_run_id`, rather than bare pairs.

**The Parquet root is a new `derived_dir` constructor keyword**, mirroring `models_dir`.
*Rejected:* deriving it from `db_path.parent.parent`. That is a hidden default the arm H12 kills.
Without the keyword, both methods refuse with `StoreError`. The CLI must pass
`derived_dir=paths.derived` (A's lane), which I asked a-replay for.

Tests: `tests/clients/store/test_shap.py` has 15 tests, and the store suite gives 270 passed. mypy
and ruff are clean.

Sweep: 12/12 killed.
- H1: overwrite allowed.
- H2: pair left out of the path.
- H3: empty explanation written.
- H4: non-finite accepted.
- H5: bool accepted.
- H6: run id not validated.
- H7: the reader sorts the contributions.
- H8: mixed decisions accepted.
- H9: `model_run_id` dropped.
- H10: timestamp truncated to seconds.
- H11: blank pair accepted.
- H12: a missing root defaults to the database folder.

Each was killed by the test named for it.

This entry also records a slip. A `python -c "..."` in bash carried backticks inside a docstring,
and the shell executed them as commands, which deleted the quoted names from `ShapRecord`'s
docstring. I saw it in the tool output and fixed it with the file tool. The same class of hazard
as the heredoc rule: never build file text inside a shell-quoted string.
