# Phase 3 — shared task list

> ## HANDOFF — Phase 3 is closed. Read this first if you are a cold Phase 4 session.
>
> *Written at phase close, 2026-09-10. Everything below this box is the Phase 3 task list as it
> stood during the phase, kept for the record.*
>
> ### What is green
>
> **All four gates, exit 0, verified at close on a quiet tree.**
>
> ```
> phase 0    7 criteria:  7 PASS, 0 FAIL, 0 PENDING
> phase 1   10 criteria: 10 PASS, 0 FAIL, 0 PENDING
> phase 2    9 criteria:  9 PASS, 0 FAIL, 0 PENDING
> phase 3    9 criteria:  9 PASS, 0 FAIL, 0 PENDING
>
> pytest tests/ -q       1340 passed
> mypy --strict src/     Success: no issues found in 71 source files
> ruff check src/        All checks passed!
> ```
>
> All eleven specs (37–47) are delivered. Engines 7 `scout`, 10 `cost`, 11 `risk` and 17 `safety`
> are built, wired to the real Kraken client, and **registered** — `is_gate_matches_registry`
> reports 8 engines, 0 mismatches, 5 gates. The guard chain is `exchange → market_data_recorder →
> market_sensor → data_guard → safety`; the opportunity chain is `scout → cost → risk`, which is
> registry order with holes rather than a different order. The manage chain is still empty.
>
> The narrative account is `docs/build-log/phase-3.md`. Write Phase 4 entries in
> `docs/build-log/phase-4/<agent>.md`, which already exist.
>
> ### What is open
>
> - **The ranking score in engine 7 `scout` does not exist**, deliberately. Ordering is alphabetical
>   over the whole universe — a placeholder that cannot be mistaken for a judgement. **Phase 5**
>   closes it at one seam, `rank_universe` in `engines/scout/contracts.py`. Test that function
>   *directly*: the engine sorts its scan set before ranking, so an end-to-end fixture cannot tell
>   alphabetical ordering from a ranking that merely preserves arrival order.
> - **The console's empty state does not show engine 7's scan tally.** Structural, not a missed wire
>   — the console is a separate process reading SQLite and never sees the in-memory state where the
>   tally lives for one tick. **Needs engine 19 `memory`, which is Phase 4.** A stale comment in
>   `console/reader.py` naming the wrong engine should be fixed by that same change, not before it.
> - **A genuine native fault on this machine remains unexplained.** It presents as an
>   `ACCESS_VIOLATION` or `STACK_BUFFER_OVERRUN` process crash, not a test failure. Two defects that
>   were hiding behind it are fixed; it is now charged only with what it causes.
> - **Mutation survivors not yet re-checked**: `clients/kraken/contracts.py`, `limiter.py`,
>   `engines/market_data_recorder/contracts.py`, `platform/config.py`, and three in
>   `clients/store/migrations.py`.
> - **An unexplained CRLF conversion, and it is the kind that hides.** A mutation-harness script
>   writing with `write_bytes` nevertheless returned `platform/config.py` with 733 CRLF line
>   endings. The file was restored and verified byte-for-byte, but **the cause was never found** and
>   was deliberately not guessed at. It matters because a whole-file line-ending change is invisible
>   in most diff views and would resurface later as an unexplained several-hundred-line diff on a
>   file nobody edited. `.gitattributes` has already been raised once for adjacent reasons.
> - **Branch-coverage backlog**, from the tell that found six untested refusal branches at the
>   exchange boundary: `clients/kraken/contracts.py::_to_money` (4), `limiter.py::acquire` (the
>   `cost <= 0` guard), `engines/market_data_recorder/contracts.py::validate_line` (1),
>   `platform/config.py` (5 across `_to_decimal`, `_require_currency_map`,
>   `_tick_divides_the_bar`, `get`, `load_yaml_mapping`), and `clients/store/migrations.py::discover_migrations`
>   (3). **These counts come from a narrow subset and have not been re-checked wide** — by the rule
>   below, expect some to die on contact.
> - **The harness stream doubles are not consolidated.** Three separate fakes exist for engine 3's
>   stream plus a fourth workaround in the criteria. A design is sketched; `tests/harness/` owns it.
>
> ### Two rules this phase produced, and they are why the above is trustworthy
>
> **1. A diagnostic procedure that cannot fail is the same defect as a test that cannot fail.**
>
> This file told everyone for two phases: *re-run the named test in isolation, and if it passes it
> was the machine's intermittent fault.* It worked every time — **because in isolation nothing else
> was sweeping the temp directory, which was the actual bug.** The mitigation was manufacturing the
> evidence for its own diagnosis, and it confirmed the wrong answer on every occasion it was
> applied. Apply to a diagnostic the question you apply to a test: **under what observation would
> this have told me something else?**
>
> **2. Three mechanisms had been collapsed into one, and keeping them apart is now a rule.**
>
> A workspace sweeper deleting other processes' live databases (fixed), a wall-clock assertion
> measuring connection setup rather than the latency it named (fixed), and a genuine native fault
> (open) were all charged to one cause. **A failure is attributed to the sweeper only if it carries
> a database error.** Anything else is unexplained until explained, and *unexplained* is an
> acceptable thing to write in a build log — writing it is what kept the second mechanism visible
> long enough to be found.
>
> ### How to read a FAIL, which is different from what this file used to say
>
> - **Named tests that MOVE between runs, in another agent's paths** → somebody is mid-save. Judge
>   by path, do not re-run, do not fix their file.
> - **A STABLE wrong verdict on one test that passes in isolation and on a full re-run in the same
>   order** → capture the traceback **before** re-running. Re-running to confirm green is what
>   destroyed the evidence for two phases.
> - **A defect of yours** reproduces every time, in isolation, in your own paths.
> - **A baseline is only meaningful if the tree is quiescent when it is taken**, and with several
>   agents writing, "before" and "after" are not separated by your change alone.


Lead-owned. Teammates do not edit this file: **claim by recording the spec number in your own
`context/progress/<agent>.md` before writing code**, per ownership rule 5.

`SendMessage` is the coordination channel. Talk to each other directly — do not route every
question through the lead.

## Headcount: four

All three teammates have real work. B carries five of the eleven specs, which is the phase being
lopsided honestly rather than filler being invented to even it out.

## What this phase is

Engines 7, 10, 11 and 17. **Zero ML.** The four gates that decide whether a trade can pay for
itself, plus the circuit breaker on the account. Nothing here trains, predicts or scores.

Three of the four already exist. B built `cost`, `risk` and `safety` during the Phase 2 overlap
against a mocked Kraken client and the Phase 0 seed. **They are built, not done**, and the audit at
planning is why.

## Done before the phase opened — lead, not assigned

**Spec 37 is landed.** The three operator rulings are in the authority documents:

- **Invariant 14 rewritten.** `safety` escalates on **one** condition, a sustained data outage.
  Drawdown, loss streak and error rate all write `freeze`. `close_all` is reserved for the outage
  and for the operator's own button.
- **Invariant 2's fee-tier fallback retired.** A confirmed pair with no fee data blocks that pair.
  `AssetPairs` carries no fee schedule, so the old row was never implementable. **Balance is now
  the only paper-mode fallback in the system, and nothing implements it** — spec 41 does.
- **A `docs_vocabulary` row for the retired wording**, qualified on `assume` so the phrase stays
  usable elsewhere. Observed to FAIL against a reinstatement before being trusted, per spec 37.
- One stale restatement found by the propagation grep and fixed: `architecture-context.md` said a
  drawdown threshold "liquidates the account".

`python scripts/verify.py --phase 3` is green at 2 PASS / 0 FAIL / 0 PENDING — **and that is the
problem C's spec 45 exists to fix.** The gate currently registers only `docs_vocabulary` and
`toolchain_green`, so it says "Phase 3 is green" over an empty phase. Nobody may read that as
progress.

## The audit, which is what the wiring specs are actually for

Read this before starting 40 or 41. B's engines read a `state["exchange"]` that engine 1 does not
publish, and every test builds that payload by hand, so both sides pass while disagreeing:

| B reads | Engine 1 publishes | Effect on a live tick |
|---|---|---|
| `exchange.fees.maker_pct` / `taker_pct` | `exchange.fee_tier.maker_fee_pct` / `taker_fee_pct` | cost blocks every tick |
| `exchange.pairs[pair]` | `exchange.pair_rules.pairs[pair]` | risk blocks every tick |
| `exchange.pairs[pair].last_price` | **nothing publishes a price** | risk cannot size at all |
| `exchange.fallbacks_used` | `exchange.failed_fetches` | dead read, silently returns `()` |

`state["market_sensor"]["quotes"][pair]["spread_pct"]` was audited and is **correct**. The one path
that was ratified into the cross-chain key table is the one that is right; the three that were
assumed are the three that are wrong.

**Operator ruling: the fixtures are rewritten, not repointed.** Every test that hand-builds
`state["exchange"]` builds it from engine 1's actual output or a fixture derived from it. *A mock
that agrees with its caller is what hid this for a whole phase, and it is the third time that shape
has appeared.*

## Ordering

**Spec 45 first, from the first commit.** C registers the Phase 3 criteria against fabricated
subjects while A and B build. Same pattern as Phases 0, 1 and 2: criteria exist so they can report
PENDING, and PENDING is what stops an empty phase looking finished. It is looking finished right now.

**Spec 38 step 1 is a handoff, and it is small.** A adds the `cache_ttl_s` field to `KrakenSection`
and messages the lead, who pastes the YAML from spec 37's appendix in the same change. `extra="forbid"`
means the YAML alone makes `load_config()` raise and fails **every test in the tree** — the lead
tried it on 2026-09-10 and reverted. Do this early so it is not blocking anything later.

**Spec 43 before 44.** The universe before the candidate.

**Spec 46 after B declares scout's reason codes.** C should not wait idle for it — 45 is the larger
task and comes first anyway. B: message C with the code strings as soon as `scout/contracts.py`
has them, and do not report 44 complete until they are in `REASON_PROSE`.

**Spec 47 last**, after 40 to 44 are green. A half-wired gate in the live chain turns every other
criterion's failure into a puzzle.

**Nobody idles.** If you need something another agent is still building, agree the contract, mock
it, and continue. Message them directly.

## Tasks

| # | Spec | Owner | Files it will touch | Acceptance check |
|---|---|---|---|---|
| 37 | The three rulings into the documents | Lead | `context/trading-invariants.md`, `context/ai-workflow-rules.md`, `context/architecture-context.md`, `config/default.yaml` | **DONE**, except the YAML block, which lands paired with spec 38 step 1 |
| 38 | TTL-bounded caching in the Kraken client | A | `src/acsoe/platform/config.py`, `src/acsoe/clients/kraken/{rest,client,contracts}.py`, `README.md`, `tests/clients/kraken/` | A second call inside the TTL makes **no HTTP request** — assert on the transport, not the return value; a call after the TTL whose re-fetch fails **raises** and does not return the expired entry; **retention survives that same expiry**; the two TTLs proved independent at different values; time advanced through the injected clock, no `sleep` |
| 39 | `acsoe engine` gets real clients | A | `src/acsoe/cli/engine.py`, `src/acsoe/engines/market_data_recorder/`, `tests/cli/`, `tests/engines/` | Daemon completes two ticks with real clients; the subscription set **changes when the balances change**, asserted both directions; `allow_crypto_quoted` excludes and includes; a failed `AssetPairs` leaves the subscription **unchanged**, asserted against the previous tick's; no hardcoded symbol anywhere under `cli/` or `market_data_recorder/` |
| 40 | Wire engine 10 `cost` to the real contract | B | `src/acsoe/engines/cost/{contracts,engine}.py`, `README.md`, `tests/engines/test_cost.py` | A's real `ExchangeEngine` output drives this gate to a **real net-edge comparison**, not a missing-input block; block test and pass test both hold through it; the fee still proved fetched by varying the fake's fixture; `test_cost.py:376` **deleted, not edited**, with the reason in the build log; **no test hand-builds `state["exchange"]`** |
| 41 | Wire engine 11 `risk`, and give it a price | B | `src/acsoe/engines/risk/{contracts,engine}.py`, `README.md`, `tests/engines/test_risk.py` | Sizing uses the **ask**, `costmin` uses the **bid**, asserted with exact `Decimal`s on a wide-spread fixture where the two differ; one increment below `ordermin` **rejected, not resized**; **the balance fallback built and tested as new behaviour** — paper falls back and records it, live blocks, both as a pair; **no test hand-builds `state["exchange"]`** |
| 42 | Ratify `CONDITION_ACTION`, prove it in the guard chain | B | `src/acsoe/engines/safety/{contracts,engine}.py`, `README.md`, `tests/engines/test_safety.py`, `context/progress/b-store.md` | Block and pass test for each of the four conditions **with the emitted command asserted**: drawdown→`freeze`, streak→`freeze`, errors→`freeze`, outage→`close_all`; the seeded drawdown emits **no `close_all`**, asserted as an absence; outage fires on the tick after the threshold and **not one before**, with a companion assertion that ordering by `cycle_id` gives a different answer; drawdown + outage together emits `close_all`, not `freeze`; **runs in a real guard chain against a real `StoreClient`**, empty database and seeded |
| 43 | Engine 7 `scout`, the universe filter | B | `src/acsoe/engines/scout/{engine,contracts}.py`, `README.md`, `tests/engines/test_scout.py` | **Different pair counts at $10 and $5,000**, both asserted and asserted to differ; each of the six exclusion rules tested and proved to be the *only* thing excluding that pair; **the tick-grid rule made to fire**; no live quote excludes and is not read as a zero spread; the sizing cross-check against engine 11 passes over a shared table; counts add up; driven from A's real engine 1 and 3 output |
| 44 | Engine 7 `scout`, the candidate and the gate | B | `src/acsoe/engines/scout/{engine,contracts}.py`, `README.md`, `tests/engines/test_scout.py` | Block test, pass test, **and a third for the middle case**: an empty universe returns `PASS`, not `BLOCK` — assert the status; ordering is alphabetical over the whole universe and does not move when spreads or volumes change; determinism under a shuffled input mapping; engines 10 and 11 read the published pair with no translation step; every emitted `reason_code` present in `REASON_PROSE`, enumerated not hand-listed |
| 45 | Phase 3 criteria in `verify.py` | C | `scripts/verify.py`, `tests/verify/` | Seven criteria registered; **each observed PENDING, observed PASS, and observed FAIL**, with the induced failure recorded in the build log; the real contracts imported, never fabricated; Phases 0, 1 and 2 report exactly what they reported before |
| 46 | Operator prose for engine 7's codes | C | `src/acsoe/console/format.py`, `tests/console/` | A test **enumerates** the codes declared in `scout/contracts.py` and asserts each is a key in `REASON_PROSE` — enumerated, never hand-listed; no prose string contains a digit |
| 47 | Register engines 7, 10, 11, 17 | Lead | `src/acsoe/bootstrap.py` | All four phase gates re-run with real output pasted into the build log; Phases 0 to 2 unchanged; `is_gate_matches_registry` PASSes with four new gates; a daemon tick completes on an empty database and on the seeded one |

## Session recovery — read this first if you are a fresh lead session

**Phase 3 wave 1 was interrupted once already**, on 2026-09-10, when the IDE crashed with A, B
and C all mid-task. The `claude` process is a child of the IDE process, so an IDE crash takes the
session and every in-process teammate with it. The operator has decided to move the session to a
standalone terminal once wave 1 reports, which removes the mechanism entirely.

**What that crash cost, and what it did not.** Source code survived, because it was on disk.
Progress files survived, because teammates write them *before* starting work. **Every build log was
an empty stub**, because the natural moment to write one feels like the end of a task — and that is
the one thing that cannot be reconstructed. `script-rules.md` rule 1 already says to write the
entry when you fix the thing. The crash is the demonstration.

**If you are picking this up cold, do this in order:**

1. `git log --oneline -6` — check for a commit nobody on the team made. The IDE committed the
   working tree as `7c4f012` last time. Teammates do not commit; the lead does.
2. `python -c "from acsoe.platform.config import load_config; load_config()"` — confirm the config
   still loads before anything else. A half-landed config key fails every test in the tree and
   looks like a hundred unrelated defects.
3. `python scripts/verify.py --phase 3` — full output, never through `tail`.
4. Read `context/progress/{a-platform,b-store,c-interface}.md`. Teammates claim there before
   writing code, so these tell you what was in flight.
5. Check `docs/build-log/phase-3/*.md`. A stub means that agent's reasoning was lost — ask the
   resumed agent to write down whatever it still remembers before it continues.
6. **Distinguish a half-finished edit from the machine fault before resuming anyone.** Last time B
   had removed two constants from `cost/contracts.py` while `engine.py` still referenced them:
   deterministic mypy name-errors, nothing to do with the intermittent fault, and re-running would
   have wasted the time the standing "run it in isolation" advice is meant to save.

**Wave state as of the interruption, 2026-09-10:**

| Agent | Specs | Where it had got to |
|---|---|---|
| A | 38, 39 | Spec 38 step 1 landed — `CacheTtlConfig` on the model, handoff note published, lead's YAML pasted, both keys resolve. Approved to tighten `cache_ttl_s` to required now the YAML is in. Then 39. |
| B | 40, 41, 42 | Mid-repair of `engines/cost/`. `CONDITION_ACTION` closure already written up correctly in its progress file. Then 41, then 42. |
| C | 45 | Restarted from the top; nothing of C's had reached disk. |

**Wave 2, not yet started:** B on 43 then 44 (scout), C on 46 (needs B's reason codes), lead on 47
(registration, lands last, after 40–44 are green).

## The bar, mid-phase

Four commands, all four green, before any task is reported complete:

```
pytest tests/ -q
mypy --strict src/
ruff check src/
python scripts/verify.py --phase 3
```

**Mid-phase the bar is no FAIL.** PENDING is expected and is not a failure.

**On a FAIL: run the named test in isolation before you believe it.** The intermittent fault on this
machine produced four spurious FAILs in roughly twenty gate runs while Phase 2 was closing, and
twice it returned a *wrong verdict* rather than crashing. One of them landed on the test asserting
no credential was committed. Re-run the named test on its own; if it passes, it was the fault, and
you say so in the build log rather than smoothing it over. **Never pipe gate output through `tail`** —
the detail is what makes a FAIL diagnosable.

**Judge by path first, re-run second — the two faults look different and the tell is reliable.**
With three agents saving files into one tree, most FAILs you see are somebody else's work in
flight, and the way to tell them apart is what *moves* between runs:

- **Another agent mid-save.** The named tests **change** from run to run and sit in paths you do
  not own. A `mypy` or `ruff` error tree-wide on a syntax error — a docstring caught without its
  closing quotes — is the same thing. Do not re-run, do not investigate, and above all do not
  fix another agent's file. Run your own paths and report those.
- **This machine's intermittent fault.** A **stable** wrong verdict on one test that passes in
  isolation, in its own file, and on a full re-run in the same order. Two full runs is what
  separates it from an ordering dependency, which would reproduce. Record it in the build log
  with the traceback — **capture the detail before re-running**, because there is still no
  captured traceback for any occurrence of this fault across the whole project, and the instinct
  to re-run and confirm green is what keeps destroying the evidence.
- **A real defect of yours.** Reproduces every time, in isolation, in your own paths.

**A baseline is only meaningful if the tree is quiescent when it is taken.** Any task that
compares a gate's output before and after a change — spec 47's "Phases 0 to 2 unchanged" is the
worked example — must capture its before-picture while nobody else is saving, and say in the
build log when it was taken. With three agents in one working tree, "before" and "after" are not
separated by your change alone, and a contaminated baseline manufactures a finding that does not
exist. The tell is the same as above: run it twice and see whether the names move.

## Two files every session

- `context/progress/<agent>.md` — what you built, what is in progress, what blocked you, open
  questions. Yours alone; the lead merges.
- `docs/build-log/phase-3/<agent>.md` — every non-trivial problem and its fix, as you fix it. This
  is dissertation material and it cannot be reconstructed later.

## Stop and escalate

- A change would touch `src/acsoe/core/` or `bootstrap.py` and you are not the lead
- A change would alter an invariant, the engine contract, or the engine registry
- A spec is ambiguous about trading behaviour — **spec 44 step 2 is a worked example of the right
  answer: the ranking score is absent on purpose and no agent may invent one**
- Another agent's work is required and no contract exists to mock
