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
