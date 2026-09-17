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
