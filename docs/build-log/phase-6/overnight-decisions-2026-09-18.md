# Overnight decisions, 2026-09-18 — for the operator's morning review

**Lead.** The operator went to sleep at ~02:50 local on 2026-09-18 and authorised unattended work
until they say they are back. Order given: the nine criteria green (**already done**, `e3b5406`),
then the seed-vocabulary cleanup, then spec 109, then spec 118, then the `cash_source` default
removal. **Do not close the phase.**

Rules: *how* choices (naming, placement, test structure, equivalent mechanisms, order) are taken
and logged here with the option rejected; *what* choices (weakening a gate or criterion, a config
value/threshold/barrier, more willing to trade, an invariant or locked decision, a cheaper option
that proves less) **stop and wait**, as does anything costing more than about three hours. Unsure
= the second bucket. Entries marked **REVIEW** are ones where a competent objection exists.

**Nothing is carried forward unreviewed.** The lead wrongly listed D3 and D8 of 2026-09-17 as
still open, in Handoff 7 and in the first draft of this file: **both were accepted by the operator
on the morning of 2026-09-17** and the acceptance was recorded in that file's rulings section the
whole time. Only the `**REVIEW**` tags on the entries themselves were left standing, and a tag is
what a reader scanning for open items sees. **The lesson, and it is the same shape this phase keeps
finding: a record is not resolved because the resolution exists somewhere in the same file — the
marker has to move.** Both entries now carry their ruling and its date inline.

## Decisions taken

### E1 — The night's starting state

`e3b5406` pushed: 13 criteria, 13 PASS, 0 FAIL, 0 PENDING; the first complete paper trade runs end
to end. Handoff 7 is written for a session that has read only the documents. Nothing was in flight
and every agent was stopped when the night's work began.

### D1 — The seed-vocabulary cleanup is two specs, B then C, in that order

**Took.** Spec 119 (B): every seeded `rejections` row is repointed to an `(engine, code)` pair the
live system can actually emit. Spec 120 (C): the `REASON_PROSE` entries that no longer have a
producer are retired, **after** B's half lands.
**Rejected.** One spec, or C first. The tracker's own ruling fixes the order for a reason that
still holds: **every code stays mapped until B's half lands**, because the seeded rows exist and
the console must render them — a code absent from the map renders "No reason was recorded."
silently. C first would put that silence on screen for the length of one commit.

## Open questions for the operator — NOT decided overnight

### Q1 — Invariant 14 grants engines 21 and 22 a retained balance that neither reads

**Found by A during spec 109** (prose work), by reading rather than grepping, and **verified by the
lead in the code**:

- Invariant 14 says *"During a liquidation, engines 21 and 22 may use the last known good balances
  and the cached `AssetPairs` metadata past its TTL."*
- **Engine 22 reads only `last_known_good_asset_pairs`** (`engines/exit/engine.py:523`), and its
  `contracts.py:159` records *"there is deliberately no `balance_last_known_good` beside it"*,
  although spec 93 named one.
- **Engine 21 reads neither** — `last_known_good` does not occur in that package.
- **So `last_known_good_balances` has no reader in `src/` at all.** The client retains it, engine 1
  publishes its *age*, and nothing reads its value.

**There is a decision behind the engine's half** — B recorded the deviation from spec 93 in its
build log and progress file on 2026-09-16 and marked it escalated to the lead. What never happened
is the invariant moving to match, and A's README was never told either. So this is not drift with
no decision; it is a decision that stopped one file short of the document that authorises it.

**Why it is more than wording.** Invariant 2 justifies retaining the balance at all as *"a
requirement on Agent A's client, not an optimisation"*, on the ground that discarding it would make
rule 14 unimplementable at the moment it is needed. That premise holds for `AssetPairs` and, as
built, does not hold for the balance.

**Options.**
(a) **Amend invariant 14 to match the code**: a liquidation uses the retained `AssetPairs` and does
not need a balance, because engine 22 sells what the store says is open and never sizes against
cash. Then either drop the retention of balances or restate why it is kept (engine 1 publishing its
age is a real reader of the *timestamp*, not of the value).
(b) **Change engine 22 to use the retained balance**, honouring spec 93 as written.
(c) Leave both and record the divergence.

**Recommendation: (a).** Engine 22's reasoning is sound — a liquidation sells positions the store
records, and a balance it cannot trust would only be a second opinion about what to sell. **Case
against (a):** it narrows an invariant to fit what was built, which is the direction that needs the
most scepticism; if a future exit path ever does need cash (a quote-currency sweep, say), the
invariant will no longer authorise the retention it depends on.

**Not touched.** A left the prose unwritten rather than choose which correct fact to state, which
was right: writing either sentence would have answered the question.

### Q2 — The two fixtures spec 118 compares are not "frozen together", which was the ruling's own premise

**Found by C during spec 118, and it corrects the operator's stated rationale.** The ruling said a
red can never be news about Kraken **because both sides are recordings frozen together**. They are
not: `tests/fixtures/kraken/asset_pairs.json` landed in `afaf2f5` on **2026-09-08**, and
`tests/fixtures/book_sample.jsonl` was cut from the 2026-09-16 archive and landed in `a089bc7` on
**2026-09-16**. The `AssetPairs` recording carries **no provenance block**, so nothing in the
repository dates it except its commit.

**The conclusion still holds for today's files** — the two agree, and BTC/USD's declaration matches
783 recorded prices — but the *argument* does not: a red could mean a re-cut fixture beside a stale
declaration **or** a setting Kraken changed between the 8th and the 16th. C kept the check, stated
both dates in the criterion's prose, and wrote that a red means the two recordings disagree and
wants a human either way. **Aligning them is a what-choice, so C stopped.**

**Options.** (a) Leave it: the check is honest and its prose no longer over-claims. (b) Re-record
`asset_pairs.json` from the same archive day as the book sample, so the premise becomes true and a
red really can only mean an inconsistent re-cut. (c) Give `asset_pairs.json` a provenance block so
its date is readable from the file rather than from git. **Recommendation: (c) then (b) when a
recording is next cut** — provenance is cheap and makes the gap visible; re-recording is a change
to committed evidence other criteria read. **Case against:** (b) touches a fixture the Phase 2
candle criterion also reads, so it is not free.

### Q3 — Spec 118 compares 1 pair of 5, and widening it is C's re-cut, not A's cutter

Coverage is **1 compared (BTC/USD), 4 not** — ADA/USD is recorded but undeclared; ETH/BTC, ETH/USD
and SOL/USD are declared but not in the book sample. **Owner, since the operator asked for one:**
not A. `scripts/cut_book_fixture.py` "chooses nothing. Not the pairs, not the window" — pairs
arrive as `--pairs`, so widening is a **re-cut run by C**, with no change in A's lane. C checked the
archive read-only: `data/raw/kraken_v2__msi__2026-09-16.jsonl` already carries **ETH/USD and
SOL/USD**, both declared, so coverage could go **1 of 5 → 3 of 5 with no new recording and no code
change**. ETH/BTC is absent from the archive and is crypto-quoted (invariant 7), so it stays
uncomparable. **The cost, and why it is not a tidy-up:** `order_book_slippage_on_recorded_book`
drives this same fixture, picking ADA/USD as the thin book and BTC/USD as the deep one, so a re-cut
and that criterion have to be looked at together. **Operator's ruling; owner named.**

### F1 — An invented ADA/USD `pair_decimals` sits two screens from the criterion about declarations

`BOOK_THIN_PAIR_RULE` in `scripts/verify.py` carries six decimals for ADA/USD, labelled "Invented
exchange data for the fake" in its own comment. **Not a defect** — the fake client needs a rule, and
inventing one for a fake is legitimate where inventing one for a *declaration* is not. It is
recorded because ADA/USD's recorded prices stop at six places, so it would have "worked" as a
declaration, and it sits ~2,200 lines from a criterion whose whole subject is declarations. The new
criterion's docstring names it as the thing it must not read.
