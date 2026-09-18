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
