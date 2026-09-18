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

## The operator's rulings on this list, 2026-09-18 evening

Recorded inline so no marker below is left looking open. Each STOPPED entry carries its ruling.

- **S1 → accepted as recommended.** Engine 22 left as built; invariant 14 not amended in its grant.
  Invariant 14 now records that the authorisation is deliberately wider than the code, with the
  reasons. "My condition did its job."
- **S2 → accepted, reshaped by the lead's follow-up answer.** The Phase 2 criterion's verdict is
  sound (tolerance never engaged; all 9 bars agree to the digit) and its assertion is unchanged;
  its **prose** was false twice and is corrected. Honest provenance block on `asset_pairs.json`;
  spec 118's message says the declaration is invented; a genuine `AssetPairs` recording lands
  alongside Q3's re-cut, not now. **Recorded as a FINDING**: a criterion described itself as
  checking against Kraken with a fetched tolerance while checking against a local reduction with
  an invented one. The lead was to stop if Phase 2 had recorded a decision the change
  contradicted: it had recorded one (`phase-2.md:887`, A, spec 28) and the change **agrees**
  with it.
- **S3 → accepted.** Every trade criterion states its own run's computed figures; the Kraken
  tier-1 point survives only as a separate sentence about Kraken's reference schedule.
- **F-new-1 → a Phase 7 prerequisite**, with the reasoning, in the tracker.
- **F-new-2, 3, 4 → recorded, not fixed.** F-new-2 gets its own line: any analysis joining on
  `cycle_id` must know it is overwritten by later ticks.
- **D7 → right, for the right reason.**
- **Then:** re-gate Phase 2 and Phase 6 and commit. Phase 6 not marked green, not closed.

## The gates

Phases 0 to 6 re-gated in order at `98c0485`, 09:04–12:44Z, `mypy --strict src/ scripts/` (153
files) and `ruff check src/ tests/ scripts/` clean first. **Every phase exit 0**: phase 0 7/7, 1
10/10, 2 9/9, 3 9/9, 4 10/10, 5 14/14, 6 14/14, each `toolchain_green` at `3314 passed, 2
skipped`. HEAD identical before and after, and `git diff --stat HEAD -- src tests scripts config
db` empty at both ends (`logs/verify/regate-20260918-close-prep-lead-summary.txt`). The documents
tonight (tracker, `phase-6.md`, HANDOFF 9, this file, the walk-through, `phase-7/`) are the
docs-only delta on top, checked by `docs_vocabulary` and `tests/verify/test_docs_vocabulary.py`.

## STOPPED overnight — all three ruled by the operator, 2026-09-18 evening

### S1 — Q1: engine 22 reading the retained balance changes its behaviour, so the condition fired

**RULED 2026-09-18: (a) accepted.** Engine 22 as built; invariant 14 records the reasons.

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

**RULED 2026-09-18: provenance now; prose corrected; recording with Q3's re-cut; a FINDING.**

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

**RULED 2026-09-18: (a) accepted** — every message states its run's own figures.

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
which the merge asks them to do at the start of Phase 7. **Operator 2026-09-18: right, for the right reason.** A competent objection was that
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

## Evening, carrying out S1–S3 (operator awake) — how-choices, each with the option rejected

### D10 — The provenance is a top-level `provenance` key in the envelope

**Took.** A `provenance` list beside `error` and `result`, the precedent `ohlc.json` set. Every reader
tolerates it: the fake's `load_envelope` and the real `parse_envelope` check `error`/`result` only,
and spec 118's reader walks `result` only; the full suite ran green over it. **Rejected.** A sidecar
file (the block would not travel with the data it describes), and `_comment` as in `fee_tiers.json`
(that file is not an envelope, this one is, and `provenance` is the word the repository already uses
for "where did this come from").

### D11 — The criteria's names are left as they are

**Took.** `candles_match_kraken_ohlc` and `recorded_book_agrees_with_recorded_pair_decimals` both
still name something they do not check. The ruling said *messages* and *prose*; a rename reaches
the registry, two test files, the tracker and every earlier gate log that quotes the name. Each
docstring now says the name is inaccurate. **Rejected.** Renaming under the ruling's cover.
**REVIEW** — a competent objection is that a name is the most-read prose a criterion has.

### D12 — The Kraken tier-1 sentence is prose held by a tripwire, not arithmetic

**Took.** `KRAKEN_REFERENCE_TIER_1` quotes invariant 5 as text; a test in `tests/verify` holds the
reference 1.25% and fires if `hurdle_multiple` or `target_pct` moves so that the quoted 3.125% /
3.0% stops holding. **Rejected.** Computing the sentence from a `Decimal("0.0125")` in `verify.py`:
invariant 5 gives those figures "for sanity-checking only — never for use in code", and a test is
where a sanity check lives.

### D13 — The run's figures are collected from what engines 1 and 10 published, not recomputed

**Took.** `_note_engine10` keeps `(pair, maker, taker, friction, hurdle)` from each driven tick's
`state`, first-seen and de-duplicated, and the message quotes them digit for digit. **Rejected.**
Recomputing friction in `verify.py` from the fee tier and the spread: that is engine 10's
arithmetic, and a criterion that states its own sum is checking itself, not the run.

### D14 — The tier-1 claim was measured before any document stated it

**Took.** A scratch probe drove the criterion's own target leg with the fake's tier forced to 1:
friction 0.708%, hurdle 1.062%, cleared, entry placed. Every document written tonight that says
"the fake's tier 1 is not a no-trade regime" rests on that run. **Rejected.** Stating the S3
arithmetic (≈1.77% bar) as fact in fixture comments and docstrings: that would repeat, in the
correction, the defect being corrected — a claim no run had shown.

### D15 — The same false claim in three other lanes' test comments is reported, not edited

`tests/engines/test_decision.py:79`, `tests/engines/test_feature_chain_rehearsal.py:1825` (B) and
`tests/engines/test_order_book.py:973` (C) justify tier 3 with "at tier 1 the cost gate is
unreachable by construction", about the fake. **Took.** Report them; they are prose outside the
messages the ruling named, in files the lead does not own. `bootstrap.py`'s identical comment
**was** corrected: it is the lead's file. **Rejected.** Editing them under ownership rule 6: the
ruling did not reach them, and a lane rule is cheaper to keep than to explain.

## Later that evening: the rename, spec 118's removal, specs 121–125

### D11 correction — the entry above claimed more than was done

D11 said *"Each docstring now says the name is inaccurate."* Only spec 118's block comment said
so. The candle criterion's docstring did not, until the rename added its history paragraph. The
entry is left as written and corrected here, per `script-rules.md` rule 6. D11 itself was then
overtaken by the operator's ruling: one criterion renamed, the other removed.

### D16 — The new name is the operator's description, shortened only by articles

**Took.** `candles_match_independent_reduction_of_recorded_trades`, the operator's own words for
what it does. **Rejected.** A shorter name such as `candles_match_recorded_trades`, which drops
*independent*. The independence of the reduction (it shares no code with the builder) is the one
thing the check is worth, and A's spec 28 decision says so. Live code, tests, READMEs and the
provenance take the new name; build logs, progress files, old specs and old gate logs keep the old
one as history, and the docstring records the rename so the two can be joined.

### D17 — Historical gate quotes keep their numbers and get a dated note

**RULED 2026-09-18 evening: accepted, "better than my instruction"; the operator records that
their instruction was wrong on this point.**

**The operator's instruction** was that every count saying fourteen becomes thirteen, naming
HANDOFFs 8 to 10. **Took.** Current-state counts become thirteen:
- the tracker's status row;
- `phase-6.md`'s summary;
- HANDOFF 11.

The Phase 6 gate quotes inside HANDOFFs 8, 9 and 10 keep "14 criteria, 14 PASS", which is what
those gates printed, and each gets *[2026-09-18 evening: spec 118's criterion removed by operator
ruling; Phase 6 has 13 criteria from then.]* beside it.

**Rejected.** Rewriting them to 13: that would make each handoff quote a gate output that never
existed. The operator ordered the history kept as written in the same message.

**Not touched either way:** the tracker's four "14 criteria" counts that are **Phase 5's** (lines
10, 710, 716, 882). A sweep would have changed them.

**REVIEW:** this departs from the letter of the instruction. It was stated to the operator before
it was done.

### D18 — Spec 118 removed by anchored deletion, and the ADA/USD section proven untouched

**Took.** One script cut:
- the block from its banner to the `Registration` banner in `verify.py` (291 lines), and its
  registration (11 lines);
- the test block from its banner to end of file (281 lines);
- the constant, the ordered-list slot and the runner entry.

Every anchor was asserted once, and every removed name was asserted absent afterwards. One import
became unused (`assert_pass`); ruff named it and it went. The tracker was byte-copied before the
edit, and the ADA/USD section compared byte-for-byte afterwards: identical, 1,150 characters.
**Rejected.** Editing by hand across three files.

### D19 — A fifth stale-prose spec, 125, added and flagged

The operator listed four. A's `exchange/README.md` sentence ("engines 21 and 22 read it from the
client directly") is the same class. A had left it unwritten *because* it waited on the ruling S1
gave. **Took.** Spec 125 (A), marked in its own header as not on the operator's list. **Rejected.**
Folding it into another spec silently, or leaving it to be found a third time.

### D2 — This file, rather than appending to `overnight-decisions-2026-09-18.md`

**Took.** A new file for this night. **Rejected.** Appending to the earlier file of the same date:
that file is the record of the previous night and now carries the operator's rulings on it; mixing
a second night into it would make "which night decided this" a reading exercise.
