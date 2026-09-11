# Build log — Phase 4 — a-platform

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem and its
fix, and every decision where two approaches were viable.

**Rule 1 is now diagnosis-before-fix.** Write **What happened** and **Why** the moment you know
why something is broken, *before* you write the fix; come back and add **Fix** afterwards. The
code survives on disk whatever happens to the session; the reasoning that found it does not.
Phase 3 opened with an interruption that took every build log and no progress file, because
progress files are written before the work and logs were being written after it.

Minimum headings per entry: What happened, Why, Fix.

Two habits Phase 3 turned into standards, both of which belong in entries here:

- **Break the code and watch the test go red**, then put it back, and say in the entry that you
  did. A test nobody has seen fail is a claim, not a check. A mutation that survives a *subset*
  of the suite has not survived — it has not been asked.
- **Record what you checked and found sound**, not only what you found broken. An audit that
  lists hits alone says nothing about coverage.

The lead consolidates these into `docs/build-log/phase-4.md` at phase close.

## Entries

### `backtest.embargo_bars` is a leaf, so it does not fail closed the way `cache_ttl_s` did

**Agent:** A · **Task:** spec 38 two-halves handoff for spec 58 · **Date:** 2026-09-11

**What happened.** The handoff was framed as a copy of the `kraken.cache_ttl_s` landing from
Phase 3: declare the field optional, let the lead paste the YAML, then tighten to required.
Writing the docstring, I claimed the same safety property that one has — that
`Config.get("backtest.embargo_bars")` raises `ConfigKeyError` while the key is absent, so
absence fails closed at the point of use. Checked it against `Config.get` before shipping the
claim, and it is false.

**Why.** `cache_ttl_s` is a **nested section**. `get("kraken.cache_ttl_s.asset_pairs")` has to
descend *into* the `None` to reach the leaf, and `get`'s walk raises `ConfigKeyError` on
descending into a non-model, non-dict. `embargo_bars` **is** the leaf: the walk ends on it and
returns `None`. Same declaration shape, opposite behaviour, and the difference is the depth of
the key rather than anything about the field. `trading.stable_quote_currencies` is the existing
precedent and the codebase already has `_optional_setting` for readers that want it.

**Fix.** Not in `platform/`. Making `get` raise on a `None` leaf would change
`trading.stable_quote_currencies`, whose two readers were *ruled* to disagree about absence
(engine 7 fails closed, engine 2 fails open) — that ruling is Phase 3's and not mine to
overturn from the config loader. Instead the docstring on `BacktestConfig` states the
difference explicitly and says the refusal has to live in whatever purges on the key, and the
both-worlds test asserts `get(...) is None` rather than asserting a raise that does not happen.
The real fix is the tighten-to-required once the YAML lands, and the lead has been told.

**Consequence.** The general rule, worth more than this key: **the optional-field handoff
pattern only fails closed for keys that are nested under an optional section.** For an optional
*leaf* the window between the two halves is a window in which a reader gets `None` silently. A
zero embargo is exactly the Phase 4 failure that looks like success, so the window wants to be
short.

### The zero-embargo assertion passed against a model with no such field

**Agent:** A · **Task:** spec 38 handoff · **Date:** 2026-09-11

**What happened.** `test_an_embargo_of_zero_is_refused_rather_than_meaning_no_embargo` was
written as `pytest.raises(ConfigError, match="embargo_bars")`. Mutation 2 below — deleting the
field from `BacktestConfig` entirely — left it **green**.

**Why.** `extra="forbid"` produces `backtest.embargo_bars: Extra inputs are not permitted`,
which contains the string `embargo_bars`. So the test could not tell "the `gt=0` constraint
refused a zero" from "this field does not exist at all". It was passing for a reason unrelated
to what it is named after — the same shape of defect as the Phase 3 `pytest.raises(
KrakenUnavailableError)` findings.

**Fix.** Both refusal tests now match `embargo_bars: Input should be greater than 0`, the
constraint's own message. Re-ran mutation 2 afterwards: all four embargo tests go red.

**Consequence.** General point for this repo: in a model with `extra="forbid"`, matching a
refusal on the **key name** is a weak assertion everywhere, because the forbid message always
contains the key name. Match the constraint.

### Mutations run — spec 38 handoff

**Agent:** A · **Date:** 2026-09-11

| # | Mutation | Result |
|---|---|---|
| 1 | `embargo_bars: int \| None = Field(default=None, gt=0)` → drop `gt=0` | **RED**, 2 failed: `test_an_embargo_of_zero_is_refused_rather_than_meaning_no_embargo` and `test_a_negative_embargo_is_refused`, both `Failed: DID NOT RAISE ConfigError` |
| 2 | delete the `embargo_bars` field from `BacktestConfig` | **RED**, 4 failed. `test_the_embargo_key_is_accepted_once_supplied`: `ConfigError: ... - backtest.embargo_bars: Extra inputs are not permitted`; `test_the_committed_config_and_the_embargo_bars_handoff`: `AttributeError: 'BacktestConfig' object has no attribute 'embargo_bars'` |

Mutation 2 was run **twice** — once against the original `match="embargo_bars"` assertions,
where the two refusal tests survived it, and again after tightening, where they did not. The
first run is the finding above.

### A hole in this archive does not mean what a hole in a Kraken archive means

**Agent:** A · **Task:** spec 54 · **Date:** 2026-09-11

**What happened.** First build of `data/historical/` came out at 184 rows per pair over a
225-interval span — 41 intervals with no row. Read through `research/historical.py`'s
contract, those 41 are quiet market: "a missing candle means no trades occurred, it is a fact
about the market and not a data error." That reading is **false for this artefact**, and
believing it would poison exactly what spec 54 exists to protect.

**Why.** Kraken's own archive is built by Kraken, which never stops watching. A hole in it can
only mean no trades. **This archive is built from a recording**, and the recorder stopped: the
session events in `data/raw/` show starts at 02:04, 02:30, 03:21, 04:01, 11:07, 12:19 and
14:15 on 09-09 with no matching stops, thirteen `kind: "gap"` records for dropped connections —
one of them `OSError: [Errno 28] No space left on device` — and a single one-minute session on
09-08 followed by ten hours of nothing. So a hole here is *either* a quiet interval *or* an
interval nobody was watching, and on BTC/USD, which trades every fifteen minutes without fail,
every hole is the second kind. Worse than the whole holes: an interval the recorder was up for
only part of produces a row that **looks complete and is not** — real trades, real prices,
understated volume, and a high or low that may never have been seen.

Phase 4 labels by walking forward from a decision bar until the target, the stop or the
timeout is touched. A walk across an unrecorded stretch reads it as a calm market and can
return `timeout` where the real market hit a barrier. That is the Phase 4 failure mode
precisely: nothing crashes, nothing goes red, the model just learns from outcomes that did
not happen.

**Fix.** The CSV cannot carry the distinction — Kraken's OHLCVT format has seven columns and
inventing an eighth would break `read_archive_rows` and stop the file being archive-shaped,
which is the whole point of it. So the distinction goes in `data/historical/PROVENANCE.json`
beside the CSVs, derived from the recording itself rather than assumed: the builder marks
every **minute** in which the recorder logged any frame at all (book frames arrive several
times a second on all three pairs, so a silent minute is a down minute), and then classifies
each interval as `not_recorded` (no minute logged), `partial` (some), or genuinely quiet (all
fifteen minutes logged and still no trade). Rows built from a partially recorded interval are
listed by timestamp, not just counted. `replay.py` carries the sidecar's caveat alongside the
gap report so it travels with the data instead of living in a file nobody opens.

**Consequence.** Told C and the lead: **`gap_count` from `load_archive` on this archive is not
a count of quiet markets.** The `--live` criterion against a real downloaded Kraken archive is
the only thing that makes the two readings the same, which is another reason `replay_full_archive`
is worth keeping opt-in rather than deleting.

### Decision: the archive built from `data/raw/` is retired, not deleted, and its coverage analysis survives it

**Agent:** A · **Task:** spec 54 · **Date:** 2026-09-11

**What happened.** Mid-task the operator supplied Kraken's own published history — 27 GB of
time-and-sales across 1,119 pair files in two directories under `data/historical/` — and spec
54 was amended to retire the `data/raw/` reduction. The three `*_15.csv` files I had just
built, and the whole `missing_not_recorded` / `partial_rows` apparatus, were built for a
problem that no longer exists.

**Options.** Leave the three files where they were and point the loader at the new source; or
remove them from `data/historical/` entirely.

**Chose.** Moved to `data/derived/archive_from_raw/`, not deleted, and the new derived bars go
in a directory of their own.

**Because.** Two archives in one directory under one naming convention is a silent
wrong-source defect — `load_archive` cannot tell `BTCUSD_15.csv` built from our recording from
`XBTUSD_15.csv` built from Kraken's history, and a labelled slice built from the weaker source
would look exactly like one built from the stronger. That is the Phase 4 failure mode again:
no crash, nothing red, a worse dataset wearing the right name. Moving rather than deleting
keeps the comparison available — the two sources cover an overlapping three days and
disagreeing on those bars would be worth knowing about — while making it impossible to load
one by accident.

**Cost.** `scripts/build_archive.py` stays in the tree with output nothing currently reads,
which is exactly the kind of thing that rots. Its docstring now says so at the top.

**What carried over, and it is the part worth keeping.** The coverage analysis was not wasted
work, it was a *measurement*: on the recording, `missing_quiet` was **0** on all three pairs —
every hole was a recorder outage, and 12 rows per pair were built from partly covered
intervals. Against Kraken's published archive that entire class of hazard is gone, because
Kraken never stops watching and a hole can only mean no trades occurred. **That is not an
assumption the new code inherits for free; it is the reason the old code needed three
categories and the new code needs one**, and the provenance says so rather than silently
dropping the two fields.

### The byte prefilter depended on `orjson`'s separator style, and would have failed silently

**Agent:** A · **Task:** spec 54 · **Date:** 2026-09-11

**What happened.** `scripts/build_archive.py` prefilters the 7 GB of recorded lines with a raw
byte search for `b'"channel":"trade"'` before spending a `json.loads` on anything. Every one of
the 26 tests in `tests/scripts/test_build_archive.py` that drives a constructed recording
failed at once with `KeyError: 'BTC/USD'` — no bars at all.

**Why.** The recorder writes with `orjson.dumps`, which emits compact separators:
`"channel":"trade"`. The test helper builds its lines with the standard library's
`json.dumps`, which defaults to `", "` and `": "` and emits `"channel": "trade"`. The prefilter
is a byte search, so the space makes the line invisible to it, and the builder happily reports
success over an empty archive.

**The part that matters is not the test.** This is a **silent** dependency on a serialiser's
formatting: if `record.py` ever moved off `orjson`, or a future recording were written by
anything else, `build_archive.py` would read every byte of the recording, find zero trade
frames, write zero-row CSVs and exit 1 with "no trades found" — or worse, on a partial change,
write a *short* archive and exit 0. Nothing in it asserted that the prefilter and the decoder
agree about what a trade frame looks like.

**Fix.** The prefilter is now the separator-independent `b'"trade"'` — the same marker
`scripts/ohlc_fixture.py` uses, and still cheap enough to keep the full pass tolerable, since
it only decides whether to spend a `json.loads`. The precise test (`kind == "tick"` and
`channel == "trade"`) stays where it always was, in `decode_trade_frame`, which is the only
place that should be deciding it. `tests/scripts/test_build_archive.py` now writes its
fixtures with **both** separator styles, so the prefilter and the decoder can never drift apart
again without something going red.

**Consequence.** General shape worth remembering: a cheap prefilter in front of an exact check
is a **second, weaker definition of the same predicate**, and the two can disagree without
anything failing. If the prefilter is narrower than the check, matches vanish silently. Make
the prefilter strictly broader than the check, and test them against an input that only the
broader one accepts.

### The same separator defect, one field along, and this one would have been believed

**Agent:** A · **Task:** spec 54 · **Date:** 2026-09-11

**What happened.** Fixing `_TRADE_MARKER` left three coverage tests red. `recorded_minute`
reads `ts_recv` out of the undecoded bytes — coverage is measured over all 22,081,231 lines of
the recording, so decoding each one is not affordable — and it matched `b'"ts_recv":"'`, with
the colon and the opening quote adjacent.

**Why.** Identical cause to the entry above: that is `orjson`'s spacing and nothing asserted
it. What makes this one worse is the **failure mode**. A prefilter that finds no trade frames
at least produces an empty archive and a visible "no trades found". A `ts_recv` search that
matches nothing produces `recorded_minutes = frozenset()`, and every interval in the history
then classifies as `not_recorded` — which reads as "the recorder was down for the entire
period". Given that the recording genuinely *does* contain restarts, dropped connections and a
disk-full, that is plausible enough to be believed and acted on. It would have made me throw
away good bars.

**Fix.** `_TS_RECV_MARKER` is now the key alone, `b'"ts_recv"'`, and `recorded_minute` steps
over whatever the serialiser put between key and value to find the opening quote — bounded to
eight bytes, so a `null` value cannot walk into the next key's quote and hand back sixteen
characters of something else as a minute. Both readers are now parametrised over spaced and
compact JSON in `tests/scripts/test_build_archive.py`, and there is a test that a line with no
`ts_recv` at all contributes no coverage.

**Consequence.** Worth stating next to the rule about handlers that conflate two situations:
**an optimisation that reads a structured format without parsing it is a parser**, and it is a
second, undocumented one. It needs the same tests as the real one and it must be strictly
broader, never narrower.

### Two of my own assertions could not fail, and both looked fine

**Agent:** A · **Task:** spec 54 · **Date:** 2026-09-11

Twenty-five mutations, twenty-three red, **two survived**. Neither was found by reading the
tests; both were written deliberately and read as careful.

**Survivor 1 — `test_a_tie_between_two_pairs_is_broken_deterministically`.** Mutation M8
removed the pair name from the sort key in `ArchiveReplay.bars`, leaving
`ordered.sort(key=lambda item: item[0])`. All 43 tests stayed green.

*Why.* The test's claim — two simultaneous bars come out in a fixed order across runs — is
true under the mutation, because the rows are *appended* in pair-name order
(`selected = sorted(self._rows)`) and Python's sort is **stable**. So two mechanisms
guaranteed the same property and the test exercised the other one. The tie-break in the sort
key was decorative, and no input could show the difference, because the selection list was
sorted before the sort ever ran. **A test cannot fail against a mutation of a redundant
mechanism.** Tightening the test would not have helped — there was nothing to tighten it
against.

*Fix.* Remove the redundancy rather than add an assertion: one mechanism, the explicit
`(ts, pair)` sort key, and `selected` now follows the caller's own order. The test constructs
a replay whose pairs are given in `SOL, BTC, ETH` order and asserts the output comes out
`BTC, ETH, SOL` — which fails the moment the key loses its second element. Re-ran M8: red.

**Survivor 2 — the frame digest in `scripts/build_archive.py`.** Mutation M13 replaced
`json.dumps(payload, sort_keys=True) + str(ts_exchange)` with
`json.dumps([payload, ts_exchange])`, dropping `sort_keys`. All 38 tests stayed green.

*Why.* Every fixture in the file builds its frames with one `json.dumps` call, so the two
copies of a duplicated frame always had their keys in the same order. `sort_keys=True` exists
for the case where they do not — two recorders, or a recorder and a later re-serialisation —
and **nothing in the suite produced that case**. The double it needed was a pair of frames
differing only in key order, and the fixture was simpler than the real thing in exactly the
dimension the canonicalisation is about.

*Fix.* A test that builds the same frame twice with its payload keys deliberately reversed and
asserts the two digests are equal and that the builder counts one duplicate. Re-ran M13 and a
narrower M26 (`sort_keys=False` alone): both red.

**The shared shape, and it is the one worth carrying forward.** Both survivors were in
*canonicalisation* code — code whose job is to make two different-looking things compare
equal. Such code is invisible to any test whose inputs are generated by one code path, because
one generator produces one form. **To test a canonicaliser you have to build the two forms by
hand.** Line coverage on both was 100%.

### The invariant-5 tripwire named the wrong five directories, and registering engine 23 is what showed it

**Agent:** A · **Task:** spec 55 · **Date:** 2026-09-11

**What happened.** Registering `BacktestEngine` in `OFFLINE_CHAIN` turned
`test_the_live_loop_does_not_import_research` in `tests/research/test_historical.py` red:
`['research.py: from acsoe.research.backtest import BacktestEngine']`.

**Why.** That test walks `engines/`, `core/`, `clients/`, **`cli/`** and `console/` looking for
any `import acsoe.research`, and `cli/` is the wrong member of that list. The invariant is that
the **live loop** never imports research code, and `cli/research.py` is not the live loop — it
is the offline entry point, and `context/ownership.md` and `context/engine-contracts.md` both
say in as many words that the offline chain is assembled there and never in `bootstrap.py`.
Spec 55's own done-condition names the four areas that matter and `acsoe.cli` is not among
them: "nothing under `acsoe.core`, `acsoe.bootstrap`, `acsoe.engines`, `acsoe.clients` imports
`acsoe.research`".

So the test was too strict in a way that had cost nothing for four phases, because the thing it
over-forbade did not exist yet. Written in Phase 2, it was correct about the danger and wrong
about the boundary, and the first time the boundary mattered it forbade the design the specs
require.

**Fix.** `cli` is removed from the forbidden list and replaced by two narrower assertions that
say what is actually meant: `cli/research.py` is the **only** module outside `research/`
allowed to import it, and `cli/main.py` must not — because the dispatcher imports each command
module lazily, which is what stops `acsoe engine` pulling `research/` into the daemon process.
`bootstrap.py` keeps its own separate assertion, which already existed and is the one that
actually guards the money.

**Consequence, and this is the generalisable half.** The test was not loose, it was *strict*,
and strictness is the failure mode nobody looks for — a too-strict tripwire reads as caution
right up to the moment it blocks the correct change, and then the pressure is to weaken it in a
hurry. **Widening a list of forbidden things is as much a defect as narrowing it, and it is
harder to see, because it only shows up when someone tries to do the right thing.** The
replacement is narrower *and* says more: "only this one module may" is a stronger claim than
"none of these five may", and it goes red in both directions.

### Mutations run — specs 54 and 55, forty-one in total, one survivor and it is equivalent

**Agent:** A · **Date:** 2026-09-11

Every mutation was applied to the real source, the named test file was run, the file was
restored, and the exact red message recorded. **`bootstrap.py` was deliberately not mutated** —
see the note after the tables.

#### `src/acsoe/research/replay.py`

| # | Mutation | Result |
|---|---|---|
| M1 | every hole filled with the previous close | **RED** — `assert {1700009000, ...} == set()`, "Extra items in the left set" |
| M2 | `close_ts` one interval late | **RED** — `assert 1700001800 == (1700000000 + 900)` |
| M3 | `close_ts` equals the bar open | **RED** — `assert 1700000000 == (1700000000 + 900)` |
| M4 | the clock is never moved | **RED** — `assert datetime(2000,1,1,...) == datetime(2023,11,14,22,28,20,...)` |
| M5 | an absent sidecar reports coverage as known | **RED** — `assert True is False` |
| M6 | `holes_mean_no_trades` read as truthiness | **RED** — `assert False is None` |
| M7 | the directory glob sweeps up the JSON sidecar | **RED** — `ArchiveError: line 1: expected at least 6 OHLCVT columns, got 1` |
| M8 | pair ties broken by arrival instead of name | **RED** *(after rewrite)* — `assert ['SOLUSD','BTCUSD','ETHUSD'] == ['BTCUSD','ETHUSD','SOLUSD']` |
| M9 | `index` counts the merged stream, not the pair's series | **RED** — `assert [100, 101, ...] == [0, 1, 2, ...]` |
| M25 | money coerced through `float` | **RED** — `assert Decimal('100.000000001') == Decimal('100.0')` |
| M27 | `selected` re-sorted, making the tie-break redundant again | **SURVIVED — equivalent mutant.** See below |

#### `scripts/build_archive.py` (the retired recording-derived builder, kept)

| # | Mutation | Result |
|---|---|---|
| M10 | **de-duplicate at the trade level** | **RED** — `assert Decimal('2.5') == Decimal('5.0')` |
| M11 | bar boundary off by one interval | **RED** — `KeyError: 1788912000` |
| M12 | quiet intervals filled with the previous close | **RED** — `assert 4 == 2` |
| M13 | frame digest over a different shape | **RED** *(after adding the key-order test)* — digests differ |
| M14 | prefilter narrowed back to `orjson`'s separators | **RED** — `KeyError: 'BTC/USD'` |
| M15 | `ts_recv` marker narrowed back the same way | **RED** — `assert 'not_recorded' == 'complete'` |
| M16 | a partly recorded interval reported complete | **RED** — `assert 'complete' == 'partial'` |
| M26 | frame digest without `sort_keys` | **RED** *(after adding the key-order test)* — digests differ |

#### `scripts/build_ohlcvt.py` (the operator's archive)

| # | Mutation | Result |
|---|---|---|
| M17 | bar boundary off by one interval | **RED** — `['1623944700', ...] != ['1623943800', ...]` |
| M18 | quiet intervals filled with the previous close | **RED** — `At index 1 diff: '1623944700' != '1623946500'` |
| M19 | a late row appended as a second bar | **RED** — `assert 25 == 24` (a duplicate timestamp in the file) |
| M20 | malformed rows silently skipped | **RED** — `assert 0 == 1` |
| M21 | a still-growing file read anyway | **RED** — `Failed: DID NOT RAISE RuntimeError` |
| M22 | a missing pair returns a path instead of raising | **RED** — `Failed: DID NOT RAISE FileNotFoundError` |
| M23 | money written with `str()`, so a small value goes scientific | **RED** — `assert '1E-8' == '0.00000001'` |
| M24 | tie-break reversed, so open and close swap | **RED** — `['1623943800','101.0',...] != ['1623943800','100.0',...]` |

#### `src/acsoe/research/backtest.py` and `src/acsoe/cli/research.py`

| # | Mutation | Result |
|---|---|---|
| M28 | `is_gate = True`, disagreeing with the registry table | **RED** |
| M29 | engine `number = 20` instead of 23 | **RED** |
| M30 | **engine 23 not registered in the offline chain** | **RED** (both `test_backtest.py` and `test_entrypoints.py`, run separately as M30/M30b) |
| M31 | every pair labelled as one merged stream | **RED** |
| M32 | target barrier written as a literal instead of read from config | **RED** |
| M33 | barriers passed positionally, so target and stop can swap | **RED** |
| M34 | an absent labeller returns a no-op instead of raising | **RED** |
| M35 | the target barrier crosses `state` as a `float` | **RED** |
| M36 | the slice filename fixed, so a second run replaces the first | **RED** |
| M37 | an opaque label row becomes an empty row instead of raising | **RED** |
| M38 | the slice written into the archive directory | **RED** |
| M39 | the no-spread statement dropped from the output | **RED** |
| M40 | an unknown `holes_mean_no_trades` reported as `True` | **RED** |

#### The one survivor, and why it is not a gap

**M27** re-adds `sorted()` to the pair list in `ArchiveReplay.bars`, restoring the redundancy
M8 exposed. It survives because it is an **equivalent mutant**: with the explicit `(ts, pair)`
sort key in place, sorting the input as well changes no output for any input. It is not a
defect and there is no assertion that could catch it without being wrong. What matters is that
**M8 — deleting the tie-break itself — is red**, which it now is. Recorded rather than quietly
dropped, because a survivor count of zero that was achieved by not listing the survivor is
worse than a survivor count of one.

#### The mutation I did not run, and what stands in for it

Spec 55 names one mutation directly: **engine 23 registered in `bootstrap.py`.** I did not
apply it. `bootstrap.py` is the lead's file under ownership rule 2, and a transient mutation is
still a write to another agent's path while three agents share one checkout — the lead could
read it inside the window, and `context/ownership.md` admits no exception for a write you mean
to undo.

What stands in for it, in `tests/research/test_backtest.py`:

1. `test_bootstrap_does_not_import_research` reads the **real** file, reached through
   `bootstrap.__file__` rather than a path built in the test, and asserts that path is the real
   one — so the check cannot be pointed at nothing by a file move.
2. `test_that_assertion_goes_red_when_the_import_is_added` copies the real file's text into a
   temp directory twice, adds the forbidden import to one copy, and runs the same detector over
   both: clean on one, red on the other.

Together: the detector is proven capable of failing, and proven to be reading the real file.
**Where that is weaker than the direct mutation, stated rather than glossed: no single test
does both at once.** The direct mutation is one line for the lead — add
`from acsoe.research.backtest import BacktestEngine` to `bootstrap.py`, run
`pytest tests/research/test_backtest.py`, confirm red, revert — and it is offered here rather
than assumed unnecessary.

### Decision: engine 23 bends to C's labelling API, not the other way round

**Agent:** A · **Task:** spec 55 · **Date:** 2026-09-11

**What happened.** `research/labelling.py` did not exist when engine 23 was written, so I
agreed a seam by message and built against a mock of it: `label_bars(bars, *, target_pct,
stop_pct, timeout_bars)`. C's module has now landed and exposes `label_frame(frame, *, pair,
config, interval_s, start_ts=None, end_ts=None) -> (pl.DataFrame, LabelledSeries)` and
`label_series(candles, *, pair, config, interval_s, ...)`. There is no `label_bars`.

**Options.** Ask C to add a `label_bars` adapter matching what I had already built and tested,
or rewrite my side.

**Chose.** Rewrote my side, to `label_frame`.

**Because.** Three reasons and only the first is about politeness. (1) The engine is the
caller; a caller that makes a callee change shape to suit its mock has let the mock become the
design. (2) C's signature is **better than mine in the specific way that matters most here**: it
takes `config` and reads the barriers itself through `read_barriers`, so there is exactly one
place in the project that turns `barriers.target_pct` into a `Decimal`. Mine passed three
already-converted values, which meant two readers of the same three config keys — and C's
converts a YAML float with `repr`, not `str`, because `Decimal(0.015)` is
`0.01499999999999999944...` and would move the stop barrier in the sixteenth decimal. Two
readers that disagree in the sixteenth decimal is a defect nobody would ever find. (3)
`label_frame` takes the `polars` frame `research/historical.py` already produces, which is
exactly what `ArchiveReplay.frame(pair)` hands over — one fewer conversion, and the money never
leaves `Decimal`.

**What I lost, and it is worth naming.** My keyword-only argument was built to stop
`target_pct` and `stop_pct` being swapped, since they are two ratios of the same magnitude in
one argument list. That hazard **disappears entirely** under C's design, because there is no
barrier argument list at all — the barriers never cross the seam. The test that guarded it is
deleted rather than adapted: it was guarding a risk that no longer exists, and a test kept past
its subject is the decayed assertion `code-standards.md` warns about.

**Cost.** Four tests rewritten, one deleted, and `LABELLER_ATTR` changed from `label_bars` to
`label_frame`. The engine still fails closed when the module is absent, still refuses a row it
cannot read, and still labels each pair as its own series.

### Every test of the labeller seam was green against a signature that never existed

**Agent:** A · **Task:** spec 55 · **Date:** 2026-09-11

**What happened.** Engine 23 was built and tested against `label_bars(bars, *, target_pct,
stop_pct, timeout_bars)` — a seam agreed with C by message while `research/labelling.py` did
not yet exist. Twenty-seven tests, all green, several of them asserting in detail on exactly
how the engine called it. C's module then landed with `label_frame(frame, *, pair, config,
interval_s)` and no `label_bars` at all. **Nothing went red**, because every one of those tests
drove a double, and a double agrees with whatever it was written to agree with.

**Why.** The double was not simpler than the real thing — it recorded faithfully and would have
exhibited any property I asserted. It was *a different thing entirely*, and no assertion about
how you call a function can detect that the function does not exist. This is the fallback
defect from `code-standards.md` seen from a new angle: not a scaffold that stopped being
load-bearing, but **a mock standing in for something that had not been built, with nothing
anywhere asserting the real thing had arrived**. A suite made only of mocks cannot notice a
seam moving under it, and the more carefully the mock is written the more convincing the green
is.

**Fix.** Two end-to-end tests with **no injection at all**, driving the engine's real import
path into C's real `label_frame`: one over a series shorter than the 48-bar horizon (asserting
zero labels and no slice, because every window runs past the end and an engine reporting seven
timeouts there would be reading `excluded_past_end` as a label), and one over a 200-bar series
that produces real labels, a real parquet, and the `label_window_end_ts` column the splitter
purges on. The mocked tests stay, because what the engine *hands over* is genuinely this side's
half of the seam.

**Consequence.** The rule this is worth becoming: **a mock for a module that does not exist yet
needs a test that fails once it does.** Exactly the shape `code-standards.md` already states
for `try/except ImportError` fallbacks, and I did not recognise it here because the scaffold was
a test double rather than an import guard. Concretely: when you mock across an agent seam,
write the no-injection test at the same time and let it fail until the other side lands, or the
day it lands is the day you find out your whole file was measuring itself.

### Two more assertions that could not fail, and the first is the double-too-simple rule again

**Agent:** A · **Task:** spec 55 · **Date:** 2026-09-11

**Survivor — `labelled_rows_by_pair` counted from the wrong number.** Mutation M41 replaced
`per_pair[pair] = len(pair_rows)` with `per_pair[pair] = series.considered`. All 28 tests
stayed green.

*Why.* `FakeSeries`, the double standing in for C's `LabelledSeries`, was constructed as
`FakeSeries(len(rows))` and set `considered = labelled`. In the real thing those two numbers are
**different on purpose**: `considered` is how many decision bars were offered to the labeller,
and it exceeds the label count by `excluded_past_end + excluded_empty_window` — every bar whose
window ran past the end of the series, which on a short series is all of them. The double was
simpler than the real thing in exactly the dimension the assertion was about, so no input could
distinguish the two implementations. This is the `code-standards.md` rule about doubles, and I
walked into it while writing a double specifically to avoid it.

*Fix.* `FakeSeries` now reports `considered = labelled + 3`, so the two numbers can never
coincide by accident, and the tests assert both `labelled_rows_by_pair` (rows produced) and
`decision_bars_considered` (bars offered) against their different expected values. M41 is red.

**Survivor — `ambiguous_labels` was reported and never asserted.** Mutation M45 replaced
`ambiguous += series.ambiguous_count` with `ambiguous += 0`; all 28 tests stayed green, because
nothing read the field.

*Why.* It is a field I added to the output late, for the right reason — ruling 1 says a bar
touching both barriers is labelled `stop`, and a slice where most labels were decided by a
ruling rather than by the data is one a reader should distrust — and then never asserted. **An
output field with no assertion on it is documentation, not behaviour**, and it will silently
become zero the first time someone refactors the loop.

*Fix.* Asserted, against a double that reports a non-zero ambiguous count, and in the
end-to-end test against the real labeller. M45 is red.

**What the two have in common.** Both are *reporting* code rather than decision code, and both
were added after the tests around them. Neither would have broken a trade; both would have
made a report quietly wrong, which in this phase is the whole failure mode. Worth applying to
every field added to an `EngineResult.data` after the fact: **if nothing asserts it, mutating
it to a constant is free.**

### Mutations re-run after the seam moved — engine 23, corrected table

**Agent:** A · **Date:** 2026-09-11

The engine-23 table further up was run against the `label_bars` seam and is superseded, not
deleted — rule 6. Five of those mutations no longer have anything to mutate, because the code
they targeted is gone: `M31` (merged stream), `M32` (barrier literal), `M33` (positional
barriers) and the old `M37` all described a call signature that no longer exists. Re-run
against `label_frame`:

| # | Mutation | Result |
|---|---|---|
| M28 | `is_gate = True`, disagreeing with the registry table | **RED** |
| M29 | engine `number = 20` instead of 23 | **RED** |
| M30 / M30b | engine 23 not registered in the offline chain | **RED**, both test files |
| M31 | every pair labelled against the **first** pair's frame | **RED** — `assert 4 == 7` |
| M32 | reported barriers re-read here instead of through `read_barriers` | **RED** |
| M33 | the `Config` not handed to the labeller | **RED** |
| M34 | an absent labeller returns a no-op instead of raising | **RED** |
| M35 | the target barrier crosses `state` as a `float` | **RED** |
| M36 | the slice filename fixed, so a second run replaces the first | **RED** |
| M37 | an unreadable label result becomes an empty row instead of raising | **RED** |
| M38 | the slice written into the archive directory | **RED** |
| M39 | the no-spread statement dropped from the output | **RED** |
| M40 | an unknown `holes_mean_no_trades` reported as `True` | **RED** |
| M41 | per-pair count taken from `considered` instead of the rows | **RED** *(after fixing the double)* |
| M42 | only the first pair labelled at all | **RED** — `assert 2 == 7` |
| M43 | an unreadable result becomes an empty slice, not a raise | **RED** — `Failed: DID NOT RAISE TypeError` |
| M44 | the interval is the loop tick, not the decision bar | **RED** — `assert 60 == 900` |
| M45 | ambiguous labels not counted | **RED** *(after adding the assertion)* |

**Running total across specs 54 and 55: forty-seven mutations, forty-six red.** The single
survivor is M27, the equivalent mutant documented above. Two of the forty-six — M41 and M45 —
only became red after the defects they exposed in my own tests were fixed, and both are written
up rather than folded into the count.

### The embargo handoff is closed, and the lead's generalisation of the weak-match finding

**Agent:** A · **Task:** spec 38 handoff, closing · **Date:** 2026-09-11

`backtest.embargo_bars: 48` is in `config/default.yaml`, so `BacktestConfig.embargo_bars` is now
`int = Field(gt=0)`. The optional window lasted one day. Two mutations: reverting to
`int | None = None` is **RED** (`test_the_embargo_handoff_is_closed_and_the_key_is_required`,
`test_removing_the_embargo_key_is_refused_at_startup`); dropping `gt=0` is **RED** (the zero and
negative cases).

The both-worlds test is **not** simply left in place. Its `else` branch — the one covering "the
YAML key is absent" — is now dead, and a dead branch in a test is a claim nobody is checking:
the same shape as an `except ImportError` fallback that stays armed after the real thing lands.
It now asserts the closed state instead, including `field.is_required()`, so making the field
optional again goes red rather than silently reopening the `None` window.

The lead's generalisation of the `match="embargo_bars"` finding, quoted as asked:

> In a model with `extra="forbid"`, the refusal message *always* contains the key name, so
> matching on the key name cannot distinguish "the constraint rejected the value" from "the
> field does not exist" — the assertion passes in both worlds and is therefore a test that
> cannot fail for the reason it exists. That is the same shape as `pytest.raises(SomeError)` on
> a path where one error type has several causes.

### `Path.write_text` is a text-mode writer, and two of mine needed pinning

**Agent:** A · **Task:** lead's CRLF ruling · **Date:** 2026-09-11

**What I checked and found sound, since an audit that lists only hits says nothing about
coverage.** `data/historical/*_15.csv` and the recording-derived CSVs contain **zero** carriage
returns: `write_archive` and `reduce_pair` already passed `newline="\n"` explicitly, written
that way because Kraken's archives are LF and `research/historical.py` reads the bytes back. My
committed evidence under `tests/fixtures/` — `record_sample.jsonl` and `recording_report.json` —
is unmodified this phase and carries zero carriage returns; the only changes under
`tests/fixtures/` are C's.

**What was wrong.** Both provenance writers used a bare
`write_text(json.dumps(..., indent=1) + "\n", encoding="utf-8")`. `json.dumps` with `indent`
produces a newline per line and every one of them would have been translated. Both now pass
`newline="\n"`, with the reason in a comment at the call site rather than in this file only.

**Three mutations, all red**, against tests that assert on **bytes**:

| # | Mutation | Result |
|---|---|---|
| M50 | archive handle opened without `newline` (text mode, CRLF) | **RED** |
| M51 | provenance written without `newline` | **RED** |
| M52 | source rows `rstrip` of the newline instead of `strip()`, leaving a stray carriage return | **RED** |

**Why the assertions are on bytes and on nothing else.** `read_text`, `splitlines`,
`csv.reader` and `json.loads` all normalise line endings, so a test written at any level above
bytes passes against LF, CRLF **and** the doubled ending `csv.writer` emits on a handle without
`newline=""`. There is no level except bytes at which this is observable, which is exactly why
it survived three phases of audits.

**And the other direction, which the rule does not cover.** We must never *write* CRLF and must
always be able to *read* it: the operator's 27 GB arrived out of an archive extraction and
nothing guarantees its line endings. A reducer that split on the newline alone and left a
carriage return on the last field would make every volume unparseable — and `iter_trades`
**counts** unparseable rows rather than raising, so the failure would present as a silently
empty archive rather than as an error.
`test_a_source_archive_with_windows_line_endings_still_loads` pins it.

**One thing I did do and should not have.** Many of my in-place source edits this session went
through `p.write_text(p.read_text().replace(...))` in throwaway scripts, which is precisely the
round trip the lead describes, so some tracked files in my lane now have CRLF working-tree
bytes. Harmless here — `* text=auto eol=lf` normalises them into the index and `git status` is
clean — and **not** harmless had any of them been under `tests/fixtures/**`, which is `-text`.
None were. Recorded because "it happened to land on paths where the clean filter saved me" is
the honest description, not "I followed the rule".

### The invariant-5 guard is now a reachability property, and the direct mutation was run

**Agent:** A · **Task:** spec 55, lead's ruling · **Date:** 2026-09-11

The lead's warning was right and the fix I had shipped earlier that day was still too weak.
Removing `cli` from a forbidden-directory list was correct in substance, but it left the guard
**one hop deep**: `bootstrap.py` importing an engine that imports `research/` would have passed
it every single time, and no allow-list version of it could ever have seen that.

`test_the_live_loop_does_not_import_research` now builds the static import graph of the whole
`acsoe` package — module-scope **and** function-scope imports, because a lazy import is still an
edge the moment the function runs — and walks it transitively from `acsoe.bootstrap`,
`acsoe.core.contracts`, `acsoe.core.orchestrator` and `acsoe.cli.engine`, asserting that nothing
reachable from them at any depth is `acsoe.research`. Failures report the trail, not the fact.
**There is no allow-list**: a reachability property has nowhere to put an exception, so the only
way to satisfy it is not to create the edge. That was the lead's point and it is the whole
reason for the rewrite.

`acsoe.cli.main` is deliberately not a root, and that is the one judgement call in it. The
dispatcher reaches `acsoe.cli.research` through an import inside `resolve_handler`, executed
only for `acsoe research`. The exclusion is recorded at the constant rather than left implicit,
and the edge is covered by `test_the_dispatcher_does_not_import_research` at module scope and by
`test_running_the_engine_does_not_import_the_research_entry_point`, which asserts on a real
subprocess's `sys.modules`.

Two supporting tests, because a reachability check that returns an empty set passes loudest:
`test_that_guard_can_see_an_edge_two_hops_away` runs the walker over a fabricated three-node
graph, and `test_the_daemon_roots_are_real_modules` fails if a root is renamed out from under
the tuple.

**The mutations, both run on the real files, both restored byte-identical:**

| # | Mutation | Result |
|---|---|---|
| M48 | the research import added to **`bootstrap.py`** | **RED**, 4 tests. Trail: `acsoe.cli.engine -> acsoe.bootstrap -> acsoe.research.backtest` |
| M49 | the same import added to `engines/data_guard/engine.py` — **two hops** from bootstrap | **RED**. Trail: `acsoe.cli.engine -> acsoe.bootstrap -> acsoe.engines.data_guard.engine -> acsoe.research.historical` |

**M49 is the one that matters**, and it is why this entry exists: under it,
`test_bootstrap_does_not_import_research` — the direct file scan — stayed **green**. The old
guard could not have caught that edge at all. M48 was run against `bootstrap.py` itself only
because the lead asked for it directly; the file was restored and verified byte-identical in the
same statement that mutated it.

**One correction to my own earlier claim.** I asserted the permitted edge was
`{acsoe.cli.main, acsoe.cli.research}`. It is `{acsoe.cli.research}` alone: `cli/main.py`
imports `acsoe.cli.research`, which is a different module from `acsoe.research`. The truth is
narrower than I guessed and the assertion is stronger for it.

### My CRLF audit used `grep`, and `grep` is a text-mode reader

**Agent:** A · **Task:** lead's CRLF ruling, correcting my own entry above · **Date:** 2026-09-11

**Correction to the entry "`Path.write_text` is a text-mode writer, and two of mine needed
pinning".** That entry says my committed evidence under `tests/fixtures/` "carries zero carriage
returns". **That was wrong, and the way it was wrong is worse than the fact.**

**What happened.** C read my deposits and reported `tests/fixtures/recording_report.json` as 168
CRLF, 0 bare LF. I had checked the same file an hour earlier and recorded it as clean.

**Why.** I audited with `grep -c $'\r'`. MSYS `grep` treats CRLF as a line terminator and strips
the carriage return before matching, so it reports **zero** against a file that is entirely
CRLF. I had, in the entry immediately above this one, written that "`read_text`, `splitlines`,
`csv.reader` and `json.loads` all normalise line endings, so a test written at any level above
bytes passes against LF, CRLF and `\r\r\n`" — and then conducted the audit with a tool that does
exactly that. **The rule was right and I did not apply it to the check that was verifying the
rule.**

Re-audited with `read_bytes`, which found two files, not one:

| file | before | after |
|---|---|---|
| `tests/fixtures/recording_report.json` | 168 CRLF, 0 bare LF, 5,274 bytes | 0 CRLF, 168 LF, 5,106 bytes |
| `tests/fixtures/kraken/ohlc.json` | 12,094 CRLF, 0 bare LF, 230,742 bytes | 0 CRLF, 12,094 LF, 218,648 bytes |
| `tests/fixtures/record_sample.jsonl` | 0 CRLF, 25 LF | unchanged — it was written with bytes |

`ohlc.json` is the one my audit would never have reached anyway: I only checked the three files
`context/ownership.md` names as A's evidence, and `ohlc.json` is not in that list even though
`scripts/ohlc_fixture.py` produces it and `candles_match_kraken_ohlc` judges it. **An audit
scoped by a document rather than by who writes the file misses the files the document forgot.**

**Why it matters here and nowhere else in the repository.** `.gitattributes` marks
`tests/fixtures/**` as `-text`, deliberately, with a comment saying why — every committed-fixture
criterion compares bytes git would otherwise rewrite between commit and clone. The consequence
is that **there is no clean filter under that directory**: everywhere else a text-mode write is
normalised into the index and is invisible, and here it changes the committed blob. The lead's
rule and the `-text` marking interact, and the interaction is the whole hazard.

**Fix.** Three parts, because fixing only the artefacts would let the next regeneration undo it:

1. Both producers pinned — `scripts/ohlc_fixture.py` and `scripts/recording_report.py` now pass
   `newline="\n"`, with the reason at the call site. (The lead asked me to leave
   `recording_report.py`'s two pre-existing ruff findings alone; I have. This is a separate line
   and a correctness fix, not lint churn.)
2. Both artefacts converted, and **proven to be a pure line-ending change**: the JSON object is
   parsed before and after and compared for equality, and the byte-length delta must equal
   exactly the CRLF count. 5,274 − 5,106 = 168. 230,742 − 218,648 = 12,094. Anything other than
   line endings changing would have failed the conversion rather than shipping.
3. `tests/scripts/test_fixture_bytes.py`, which asserts on `read_bytes` and on nothing else.

**The mechanism, measured on this machine rather than asserted:** a five-newline JSON payload
through a bare `write_text` is 5 CRLF and 38 bytes; through `newline="\n"` it is 0 CRLF and 33
bytes; `json.loads` returns an equal object from both. That last clause is why every consumer in
the project is blind to it — `verify.py` reads both files with
`json.loads(path.read_text(...))`, so both criteria passed throughout and would have kept
passing.

**Four mutations, all red:**

| # | Mutation | Result |
|---|---|---|
| M53 | `recording_report.json` rewritten as CRLF | **RED** — the parametrised byte assertion for that file |
| M54 | `tests/fixtures/** -text` commented out of `.gitattributes` | **RED** — `test_the_fixtures_directory_is_still_marked_minus_text` |
| M55 | mechanism: bare `write_text` on a 5-newline payload | 5 CRLF where the pinned call gives 0 |
| M56 | `test_the_line_ending_check_is_capable_of_failing` | the predicate run against a deliberately CRLF file, so "no CR" is not passing for want of newlines |

M54 is the one worth keeping. Without it, every byte assertion in that file becomes
**unfalsifiable** the day someone removes the `-text` marking: the clean filter would start
normalising the fixtures and the tests would pass because git was hiding the problem, not
because the producers were correct. A test whose premise can silently become true is the same
defect as a test that cannot fail.

**The general point, and it is the one I would keep.** *Audit a byte-level property with a
byte-level tool.* Every convenient tool for looking at a file — `grep`, `cat`, an editor,
`read_text`, `splitlines` — normalises line endings, so a line-ending audit conducted with any
of them returns clean against a file that is entirely wrong. This is the same shape as the
prefilter finding from earlier today (a cheap check standing in for an exact one, silently
weaker), arriving in the *verification* step rather than in the code. **I wrote the rule and
then verified it with a tool that could not see the thing the rule is about.**

### Why the derived bars are at the top level of `data/historical/`

**Agent:** A · **Task:** spec 54, at the lead's request · **Date:** 2026-09-11

Recorded because the next person will otherwise tidy it into a subdirectory and break a
criterion.

`data/historical/` holds the operator's Kraken archive in two subdirectories,
`KRAKEN_TimeAndSales_Combined/` and `TimeAndSales_Combined/`, and the three derived
`*_15.csv` files at the **top level** beside them. That looks untidy and is deliberate.

`scripts/verify.py`'s `replay_full_archive` globs `data/historical/*.csv`,
**non-recursively**. Non-recursive is itself load-bearing: a recursive glob would sweep up all
1,119 three-column time-and-sales files and hand them to a seven-column OHLCVT loader. So the
derived bars have to sit exactly one level up from the source files — deeper and the criterion
does not see them, shallower is not possible.

The alternative was a `data/historical/ohlcvt_15m/` subdirectory and one changed line in C's
`verify.py`. Agreeing with the criterion was worth more than the tidier tree, and it is C's file
rather than mine.

Confusion between source and derived is prevented by two things rather than by the nesting:
source files are one level down and never at the top, and the derived files carry an `_15`
suffix the source files do not — `XBTUSD.csv` is three-column time-and-sales, `XBTUSD_15.csv` is
seven-column OHLCVT. `tests/scripts/test_build_ohlcvt.py` asserts both, in both directions.
