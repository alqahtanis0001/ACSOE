# Phase 4 — shared task list

## Handoff — 2026-09-11, between Phase 4 and Phase 5

Phase 4 stays closed. Nothing below is phase work; it is data collection, which does not wait
for a phase, and two rulings that do.

### The three hardcoded pair lists

The system was capped at BTC, ETH and SOL in three independent places. Two are now gone:

| Where | Was | Now |
|---|---|---|
| `scripts/record.py` | `DEFAULT_PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD")` | **Fixed.** No pair list in the file. Both tiers are derived at startup from Kraken's own `instrument` + `ticker` snapshot and written into the archive as a session marker. |
| `scripts/build_ohlcvt.py` | `DEFAULT_PAIRS = ("XBTUSD", "ETHUSD", "SOLUSD")` — 3 of 1,119 archive files ever read | **Fixed.** Enumerates the archive: every file ending in `USD` with at least `--min-years` (default 2) of history. **Not yet run** — see below. |
| `scripts/ohlc_fixture.py` | `DEFAULT_PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD")` | **Still three.** Not touched. It generates the fake-Kraken OHLC fixture, and `candles_match_kraken_ohlc` is written against three pairs, so widening it is a verify-criterion change and C's call, not a default to flip. |

**The build is planned and waiting for the operator's word**, not started: 413 USD-quoted files,
**234 with two or more years**, 21.8 GB to read, ~750M trades. Measured on six sampled pairs
(fill 7%–79%, median 38%): **~13.3M bars, ~13.3M labelled rows** after the 48-bar horizon comes
off each series, **0.76 GB of CSV** (2.0 GB if every interval had traded), **~0.5 h** wall clock
at 11.9 MB/s. Reproduce with `python scripts/build_ohlcvt.py --plan --measure`; build with
`--write`. The 13.3M is a floor rather than a point estimate: the fill sample was capped at
150 MB per file, so it under-weights the liquid pairs, whose measured fill is 84%–99.6%.

### The recorder: uptime, and what happens when the disk fills

**It had been stopped for about fifteen hours** (last line 01:12Z, restarted 15:44Z). That data
is gone; order book and spread cannot be backfilled. It is running again, now two-tier:

- **Tier 1** — full raw `book`+`ticker`+`trade`, the ten most liquid USD pairs by 24h quote
  volume, into `data/raw/` as before. Measured **17.0 GB/day**.
- **Tier 2** — one row per pair per minute (spread p25/p50/p75, depth at $10k both sides,
  trades, volume, update counts) for the 137 other USD pairs above $100k/24h, into
  `data/summaries/`. Measured **0.06 GB/day** written, 43.7 GB/day inbound and discarded.

**Runway is the thing to watch: ~9.5 days** from 187.5 GB free to the 25 GB floor. At the floor
the **disk guard** drops tier 1 to its top three pairs, logs it loudly, records a
`tier1_degraded` session marker, and keeps tier 2 running — sticky, no un-degrade, because
oscillating around the floor would cut the archive into interleaved subscription sets. Errno 28
has already killed this recorder once; degrading loses the least valuable part instead of all
of it. Lowering `--tier1-count` or raising `--disk-floor-gb` is one flag either way.

The existing 7.1 GB raw archive is untouched and still the only raw sample there is.

### Two rulings Phase 5 needs from the operator

Both are yours, not an agent's, and Phase 5 should not start until they are made:

1. **Is the training window past-only or two-sided?** Past-only (expanding or rolling window,
   train strictly before validate) is the defensible choice for a system that will trade
   forward; two-sided is standard in the cross-sectional literature and would make the numbers
   look better and mean less. This decides the walk-forward splitter, so it cannot be changed
   later without rerunning everything.
2. **Is the thin pre-2016 history excluded?** `XBTUSD` starts 2013-10-06 and its early years
   are sparse — its overall fill is 84% against ETH's 93%, and the missing 16% is concentrated
   at the start. Including it trains on a market with different microstructure; excluding it
   costs roughly two years of the longest series. The answer must be one rule applied to every
   pair, recorded in the provenance, not a per-pair judgement.

### One trap that cost an hour, so it is written down

`@dataclass` **cannot be used in `scripts/*.py`**. The scripts are loaded by path in the tests
(`spec_from_file_location`), a module loaded that way is absent from `sys.modules`, and
`dataclasses` looks its own module up there while processing the class: the decorator raises
`AttributeError: 'NoneType' object has no attribute '__dict__'` at import, and every test in
the file then errors in its fixture rather than in a test. Both new types are plain classes
with `__slots__` and a comment saying why.

Also in this change: `toolchain_green` now writes each failing tool's **complete** captured
output to `logs/verify/toolchain_green/` and names the file in its one-line message, instead of
keeping the last three lines. That is the mechanism-3 evidence fix — every investigation of the
intermittent red has started from a summary with the diagnosis already discarded.

---

Lead-owned. Teammates do not edit this file: **claim by recording the spec number in your own
`context/progress/<agent>.md` before writing code**, per ownership rule 5.

`SendMessage` is the coordination channel. Talk to each other directly — do not route every
question through the lead.

## The rule this phase is governed by, and it outranks the schedule

**Phase 4 is the phase where a mistake looks like success.** A purging bug or a short embargo
produces a model that appears excellent and is worthless. A missed block record makes the
circuit breaker inert. Neither crashes, neither turns a test red, and neither is visible to an
operator. There is no symptom to notice, so the only defence is proof.

**Every criterion and every labelling test must be proven capable of failing, and the proof
goes in the build log.** Write the assertion, break the thing it tests, record that it went
red, then fix it. Name the mutation and quote the red message. Phase 3 found three tests that
could not fail — all by mutation, none by review, all written by careful agents who believed
otherwise. **A claim that an assertion works is not evidence.**

For the walk-forward splitter specifically: prove the embargo by constructing a fold where a
label window straddles the boundary and asserting the row is excluded. **An end-to-end test
cannot see the difference between a correct embargo and none at all**, because the fold
indices do not overlap in either case.

## Headcount: four

| Agent | Specs | Count |
|---|---|---|
| **C — Interface and models** | 48 criteria, 49 memory/blocks, 50 memory/rows, 52 labelling, 53 walk-forward, 56 fixture, 57 console | 7 |
| **A — Platform** | 54 replay and the archive, 55 engine 23 and the offline chain | 2 |
| **B — Store and trading** | 51 store surface | 1 |
| **Lead** | 58 registration and the embargo key, review, verify, report | 1 |

Phase 4 is C-heavy the way Phase 3 was B-heavy, and for the same reason: ownership is
permanent and the work landed where it landed. **No filler was invented to even it out.** B has
one genuinely small spec and it blocks two other people, so it goes first.

## What this phase is

Engine 19 `memory` — the engine that writes everything the rest of the system reads — and
engine 23 `backtest`, which in this phase means **replay plus triple-barrier labelling** and
nothing more. Engines 5 to 16 do not exist; a backtest through the full chain is Phase 6 and
Phase 7 work and the gate forbids it here.

Phase 3 proved `safety` against the Phase 0 seed because engine 19 did not exist yet. This
phase produces the live rows and proves they reach the **same six totals**. That is the one
seam in the project where a consumer was built a phase ahead of its producer, and closing it
is the point of specs 49 and 50.

## Ordering

**Spec 48 first, from the first commit.** C registers the Phase 4 criteria against fabricated
subjects while A and B build. Same pattern as Phases 0, 1, 2 and 3: criteria exist so they can
report PENDING, and PENDING is what stops an empty phase looking finished. `--phase 4`
currently prints *Phase 4 is green* over a phase in which nothing has been built.

**Spec 51 early and quickly.** It is one method and it unblocks C twice.

**Spec 54 before 52 and 56.** No archive, no labels, no fixture. A should get the archive built
early even if `replay.py` is not finished, and message C the moment CSVs exist in
`data/historical/` — C can mock the frame until then and must not idle.

**Spec 52 before 53 before 56.** The label carries the window end the splitter purges on.

**Spec 58 last**, after 49 and 50 are green and engine 19 has been driven through two real
orchestrator ticks. A half-wired engine in the live chain turns every other criterion's
failure into a puzzle. That deferral has now paid twice.

**Nobody idles.** If you need something another agent is still building, agree the contract,
mock it, and continue. Message them directly.

## Two lead rulings you are held to, and neither is yours to relitigate

Both are in spec 52 in full. Both are flagged to the operator as lead rulings.

1. **A bar that touches both barriers is labelled `stop`.** OHLC carries no intra-bar
   ordering. The pessimistic reading is the only one that cannot flatter the strategy.
2. **The timeout barrier is a time, not a count of rows.** The archives contain only intervals
   in which trades occurred, so 48 existing rows can span days across a quiet period.

## What stops work immediately

- A spec is ambiguous about trading behaviour → open question in your progress file, stop that
  unit, message the lead. Never invent.
- A change would touch `src/acsoe/core/`, `bootstrap.py` or `config/` → lead.
- A schema change → lead and B.
- You need to edit a path you do not own → escalate, do not reach across.

## Write your two files as you go

`context/progress/<agent>.md` before the work, `docs/build-log/phase-4/<agent>.md` **at the
moment you diagnose a problem, before you write the fix.** Phase 3 wave 1 was interrupted with
three agents mid-task and every build log an empty stub while every progress file survived —
because progress files are written before the work and logs were being written after it. The
habit, not the crash, is the defect.

**Do not consolidate the build logs and do not close the phase.** Both are the lead's, and the
operator has withheld the close for this phase.
