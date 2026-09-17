# Overnight decisions, 2026-09-17 — for the operator's morning review

**Lead.** The operator went to sleep on 2026-09-17 around 03:40 local and authorised
unattended work until they say they are back: finish the phase 0–5 re-gate, commit
registration, run C's criteria bodies, spec 101 and the seed-vocabulary cleanup, and route
the stale-comment items as small specs. The rules: *how* choices may be taken and logged
here; *what* choices (weakening a gate or criterion, a config value/threshold/barrier,
more willing to trade, an invariant or locked decision, a cheaper option that proves less)
stop and wait. **Every decision taken overnight is listed here, with the rejected option and
the case against.** Entries marked **REVIEW** are ones where a competent objection exists.

Do not close the phase: when the nine Phase 6 criteria are green, report and stop.

## Decisions taken

### D1 — Sequence: agents run one at a time, not in parallel

**Took.** B's small items (its unwritten spec 106 records, then spec 108) first, then C's
spec 107 and the spec 100 criteria bodies, then spec 101, then the seed-vocabulary
reconciliation (B, then C). One agent in the tree at a time, a gate and a commit at each
boundary.
**Rejected.** Running B's cleanup and C's criteria bodies concurrently, which would save
time overnight.
**Why.** C's criteria drive the whole chain, including the paper broker B is editing, and
both lanes run mutation sweeps; in a shared checkout a mid-save file or a live mutant in one
lane reads as a FAIL — or worse, a KILL — in the other (`code-standards.md`). The cost is
wall-clock time only.

### D2 — The stale-comment items are two small specs, split by owner

**Took.** Spec 107 (C): engine 9's README and docstring still describing engine 11's
removed fallback; spec 105's criterion still accepting a position with no mark. Spec 108
(B): engine 10's "rejections column" comment; the unused `FALLBACK_PAPER_LEDGER` constant
and the broker comment calling the starting balance a substituted value. C's two minor
findings (the tier-sentence test that never observes PENDING; the four-quote docstring at
`test_phase6_criteria.py:671`) are folded into the spec 100 criteria-body work, since they
are in the same file.
**Rejected.** One cross-lane cleanup spec (ownership rule 6 forbids it), or folding all of
them into spec 100 (it would mix B's lane into C's task).

### D3 — Spec 107's tightening of spec 105: **REVIEW**

**Took.** Tighten the criterion so that a fill-tick position with no stored mark is a FAIL,
now that spec 106 makes engine 21 store the fill price as the mark.
**Rejected.** Leaving the NULL-mark branch as it is (accepting a NULL mark when the equity
row valued the position at cost).
**Case against my choice.** It is *stricter*, not weaker, so it is in the "how" bucket by
the operator's rules — but it changes what the criterion accepts, and a stricter criterion
that couples to engine 21's display fields could go red for a reason unrelated to the
double count it exists to catch. The case for: the branch is now reachable only by a
regression of spec 106, and a criterion that silently accepts a regression is proving less
than it could.

### D5 — Spec 100's bodies before spec 101; `console_shows_position_live` PENDINGs on spec 101 meanwhile

**Took.** C writes all nine criterion bodies first, with `console_shows_position_live`
reporting PENDING naming spec 101 until the console shows the position; spec 101 follows as
its own boundary.
**Rejected.** Building spec 101 first so every criterion can reach PASS in one pass.
**Why.** Eight of the nine criteria are about the engines and the broker and need nothing from
the console; doing them first gets the most evidence soonest, and a PENDING that names its
missing subject is the criteria framework's normal shape. Order only.

### D6 — Spec 105's criterion switches to the registered `bootstrap` chains

**Took.** Now that spec 82 has landed, `paper_equity_continuous_across_fill` reads
`build_chains()` instead of its hand-built registry-order list, in the same work as the
other criteria.
**Rejected.** Keeping the hand-built chains, which are independent of registration.
**Why.** Its own docstring says to switch; a criterion that builds its own chains can pass
while the registry is wrong, which is the Phase 2 tripwire lesson ("reach X through the code
path X lives on"). Mechanism only; the assertion is unchanged.

### D7 — More stale fallback prose, routed as specs 109 (A) and 110 (B), scheduled last

**Took.** B found the same pre-ruling wording in A's lane (the Kraken client README and engine
1's README, contracts, engine and test) and in B's `clients/store/client.py`. Two prose-only
specs, one per owner, run after the seed-vocabulary reconciliation.
**Rejected.** Folding them into spec 108 (A's lane is not B's), or running them now, alongside
C's criteria work (D1: one agent in the tree at a time).
**Why.** They change no behaviour and block nothing; C's criteria are the work the operator
asked for tonight.

### D8 — `escalation_completes_during_outage` fails the balance by failing `AssetPairs` too: **REVIEW**

**Took (C's proposal, accepted).** In paper mode the broker never calls the real `Balance`,
so failing that call alone changes nothing. C fails `AssetPairs` as well; the broker's
`balance()` then raises `KrakenUnavailableError`, engine 1 records `balance` as a failed
fetch, and engine 22 must liquidate on the **retained** `AssetPairs` (invariant 14),
recording `asset_pairs_last_known_good`.
**Rejected.** A balance-only failure (for example the fee tier absent while a fill is due,
spec 103's path) — C is to record whether it is achievable and why it was not used.
**Case against.** The Phase 6 row says "the balance fetch is still failing"; this subject
fails more than that, so a pass also depends on the retained-cache path working. The case
for: it is a strictly harder condition that exercises invariant 14's other override too, and
the criterion's message names both failures, so nothing is hidden.

### D9 — The escalation criterion must prove the resting-entry cancel non-trivially

**Took.** At the committed config a resting entry is always cancelled by its unfilled window
(300 s) long before `safety` can escalate (more than 15 one-minute blocked ticks), so on the
escalation tick `entry_orders_cancelled` is true trivially. Asserting only that would prove
nothing about engine 21's `close_intent` cancel. The criterion therefore **also** cancels a
real resting entry under `close_intent` — an operator `close_all` issued well inside the
entry's window, with `data_guard` blocking and the balance failing — and asserts the cancel
happened because of `close_intent`. Its message states that a `safety` escalation can never
find a resting entry at this config.
**Rejected.** Asserting the flag alone (cheaper, proves less — the operator's stop bucket,
so not an option); or changing `entry_unfilled_window_s` in the subject so a resting entry
survives to the escalation (a config value — the stop bucket).

## Findings

### F1 — `safety`'s resting-entry escalation precondition is unreachable at the committed config

Found by C while planning the criteria bodies, read-only. `trading.entry_unfilled_window_s`
(300) is shorter than `safety.max_consecutive_data_blocks` (15) × `timeframes.loop_tick_s`
(60), and invariant 8 cancels a stale entry even during a `data_guard` hold, so no resting
entry is still on the book when `safety` escalates. Engine 11 also refuses a resting entry on a
pair that already holds a position (spec 89), and engine 7 does not skip such a pair. Nothing
is wrong — the window makes the system safer — but invariant 14's "or resting entry orders"
clause is only reachable through the operator's own Close all. See Q2.

## Events

### E1 — The network was down 03:13–08:20 UTC; the session stalled with it

The recorder's heartbeat (`data/raw/heartbeat__msi__2026-09-17.ndjson`) reports
`connected: false` for 308 consecutive minutes, 03:13Z to 08:20Z, and reconnected on its own;
both recorders and both supervisors are still running. **That span of order-book and spread
history is lost and cannot be recovered** (the recorder marks it; the archive is not edited).
The lead's session could not reach the model for the same span, so nothing progressed
overnight between the re-gate finishing and 09:21 local. The re-gate itself ran locally and
completed: phases 0–6 each fail only `toolchain_green`, on spec 100's known eight.

### D4 — Registration committed on the re-gate that measured it, with a docs-only delta after: **REVIEW**

**Took.** Commit `bootstrap.py` on the gate that ran against it (phases 0–6, logs
`logs/verify/phase6-20260917-registered-lead-*`). After that gate, only documentation changed:
B's two record files (written while the gate ran, on the lead's instruction), the two new
specs, this log, and the tracker follow-ups. For that delta, the lead re-ran the one criterion
that reads those documents, `docs_vocabulary`, and the `tests/verify` tests that parse
`context/*.md`, immediately before the commit.
**Rejected.** A second full re-gate (roughly three hours for phases 0–6, since every phase
re-runs the whole suite) before the commit.
**Case against my choice.** The operator's rule is one authoritative gate immediately before
the commit, and this is not literally that. The case for: no source, test or config byte
changed after the gate started (checked with `git diff --stat`), so a second run would
re-measure identical code; the docs delta is covered by the check that reads it. Cheaper,
but not because it proves less about anything that changed.

## Open questions for the operator — not decided overnight

### Q1 — `CostAssessment.fallbacks_used` has no producer and no reader

Spec 108 (B) found that engine 10's payload field `fallbacks_used` is always empty (no
fee-tier fallback exists since spec 37) and that nothing in `src/` reads it — the column of
that name is on `trades`, not `rejections`. Spec 106 removed the same field from engine 11
on exactly those grounds. **Not removed here**, because removing it changes engine 10's
published shape, which is a "what" choice.
**Options.** (a) Remove it, as engine 11's was — consistent, and an always-empty field reads
as "no fallback fired" on a record that cannot record one. (b) Keep it as a reserved,
always-empty field. **Recommendation: (a).** **Case against:** engine 22 still publishes a
real `fallbacks_used` (for rule 14's liquidation), so a uniform "every money-deciding engine
carries the field" convention has some value for readers of the payloads.

### Q2 — Is F1 acceptable as it stands?

**Options.** (a) Accept: the window cancel covers the hazard invariant 14's clause was written
for, and the operator's Close all is the path that still exercises a `close_intent` cancel of
a resting entry. (b) Record the relationship between `entry_unfilled_window_s` and
`max_consecutive_data_blocks × loop_tick_s` as a config-validation rule, so a future change to
either value cannot silently make the clause reachable-but-untested. **Recommendation: (a),
plus a one-line note in invariant 14.** **Case against:** (b) turns an accident of two
defaults into an enforced property, which is the kind of coupling nobody decided on — the
same objection `code-standards.md` makes to adding a constraint by default.

## The operator's rulings, 2026-09-17 morning

D1, D2, D5, D7: correctly in the "how" bucket — calibrated; do not escalate more. D3: accepted.
D4: accepted and made a standing rule in `code-standards.md`. D6: "the best call in the log" — keep
the instinct. D8: accepted. D9: right call; "an assertion that is true trivially is not an assertion."
Q1: remove the field (spec 111); engine 22's stays. Q2: a third option — a test asserting the
window/escalation relationship from config, commented as the notice that the clause has become
reachable (spec 112), plus a one-line pointer in invariant 14. F1's engine 7 half: a Phase 7 item.
E1: Known Risks. The operator is back; normal rhythm resumes.
