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
