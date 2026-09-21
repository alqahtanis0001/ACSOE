# Phase 8 build log — Lead

Per `context/script-rules.md`: every non-trivial problem and its resolution, written **at
diagnosis, before the fix**. Decisions go in `decisions-2026-09-21.md`; this file is what went
wrong and what was learned.

### Phase 8 opened: files created, housekeeping done, costing first

**Agent:** Lead · **Date:** 2026-09-21

**What happened.** The operator closed Phase 7 on the write-up at `48faf18` and asked for Phase 8
to be **costed before anything is built**: the live UI, a real activation button, and the four
live-path defects Phase 7 recorded. They also asked that Phase 8 carry the same paper trail as
Phase 7, so a fresh session can pick it up from files alone.

**Created,** mirroring Phase 7's names and layout exactly:
- `feature-specs/PHASE-8-TASKS.md` (the shared task list, as Phase 7 had it)
- `docs/build-log/phase-8/lead.md` (this file)
- `docs/build-log/phase-8/decisions-2026-09-21.md` (as Phase 7's `overnight-decisions-2026-09-19.md`)
- `docs/build-log/phase-8/team-brief.md`
- `docs/dataset/phase-8-findings.md` (alongside `phase-7-findings.md`)

**Housekeeping.** The Phase 7 watchdog task is unregistered (both runs finished; no `ACSOE*`
task and no watchdog process remain). The stale `rank_universe` docstring is corrected and
gated. **The config key was attempted and reverted** — see the entry below; it is not the
one-line change it looks like.

### C0 done: Phase 8's criteria written PENDING-first, and scoped to the ruled build

**Agent:** Lead (C's lane, operator instruction; no C session running) · **Date:** 2026-09-21

**Why it was first.** `verify.py --phase 8` registered only `docs_vocabulary` and
`toolchain_green` and therefore reported *"Phase 8 is green: every criterion PASS, zero
PENDING"* while nothing of Phase 8 existed. The operator's words: a phase that reports green
before it starts cannot tell them anything at its close.

**Four criteria, all PENDING the day they were written**, each observed PENDING, PASS and FAIL
by `tests/verify/test_phase8_criteria.py` (20 tests): `live_client_serves_the_stream`,
`pair_rules_key_on_engine_names`, `console_refuses_a_foreign_origin`,
`daemon_reads_the_real_exchange`. The FAIL arms aim at the *plausible wrong implementation*
rather than at absence — a stream member that exists but is not callable, a half-finished name
migration, an Origin check that also refuses the operator's own kill switch, a digest from the
fake client.

**Two defects in my own criteria, caught by running them rather than by reading them.** The first
version FAILed where it should have been PENDING: it read spec 127's recording as a parsed object,
but the recording stores the response **verbatim as a string** under `payload`, so the mapper was
handed nothing and refused. A mapper that cannot read the real body at all is unbuilt work, not a
wrong implementation, so that path now reports PENDING and carries the refusal in its message.
The second used a helper name that does not exist (`seed_database`) and then a bare
`TemporaryDirectory`, which on Windows raises `PermissionError` during cleanup because the console
holds the database open; `console_workspace()` exists for exactly that and is now used.

**Deliberately not written:** criteria for `mode: live`, the live order surface, `close_all` live
or the soak. The operator deferred all four, and a test asserts none of those names is
registered. **Phase 8 cannot be closed on this scope alone**, which the task list states.

### `scout.rank_feature` by option C: a daemon config, with drift caught by a test

**Agent:** Lead · **Date:** 2026-09-21

**Ruled by the operator** over option B, because naming `models.*_run_id` in the file every clone
gets would go stale on any retrain and mislead a future session.

**What was built.** `config/daemon.yaml`, an exact copy of `config/default.yaml` with one
override (`scout.rank_feature: expected_move`), started with
`acsoe --config config/daemon.yaml engine`. The loader has no overlay — `Config.load(path)` reads
one file, and the only environment reads in `platform/config.py` are for credentials — so a full
second file is the only shape option C can take.

**The cost the operator named, and what answers it.** Two files drift.
`tests/platform/test_daemon_config.py` flattens both and fails, naming the key, if they differ
anywhere but the declared override. Proven capable of failing by two mutations applied to a byte
copy **written to disk first**, restored and hash-checked: both killed.

**Still open, and reported rather than invented:** `daemon.yaml` alone does not make the daemon
rank. Ranking loads the artefacts named by `models.*_run_id`, those keys are absent, and engine 7
still fails closed. Which trained model a live daemon runs is the operator's decision. The newest
artefacts on this machine end their training on **2025-01-04, about twenty months before today**,
which is a fact the live plan needs.

### `scout.rank_feature: expected_move` makes the daemon fail closed on a fresh clone

**Agent:** Lead · **Date:** 2026-09-21

**What happened.** The operator's housekeeping item 2 was implemented: the key set in
`config/default.yaml`, its two stale comment blocks corrected, and the scout test that pinned
the key's absence rewritten so the alphabetical path kept its coverage. **34 of 63 scout tests
then failed**, and not on stale anchors: tests that read `entered` from engine 7's payload got a
`KeyError`, because the engine was publishing a block instead of a universe.

**Why.** With the key set, engine 7 ranks through the shared function, which loads the predictor
and anomaly artefacts named by `models.*_run_id`. Those keys are **absent from the committed
config**, and `models/` is gitignored, so on a fresh clone and in every test fixture the ranking
cannot be scored: `_expected_move_ranking` raises `MissingInputError` and engine 7 BLOCKs with
`scout_inputs_unavailable` on every tick. Verified directly against the committed file:
`scout.rank_feature = expected_move` with all three `models.*_run_id = None`.

So the change converts *"a fresh clone ranks alphabetically and runs"* into *"a fresh clone
blocks at engine 7 forever"*. That is a change to what the system does, which is a stop under
the operator's own rules.

**Fix.** Reverted the config and the test edits; the tree is green at 63 passed. Kept a docstring
correction that is true of the reverted state. Reported to the operator with three options and
their costs (`docs/dataset/phase-8-findings.md`). **Not decided by the lead.**

**Scope conflict, recorded rather than resolved silently.** `ai-workflow-rules.md`'s Phase 8 row
is *Live readiness* — `live_guard.py`, `close_all` end to end, and a 7-day soak. The operator's
goal for this phase is the **live UI and activation control**. Both are in the task list, marked
by origin. The workflow row's criteria remain what `verify.py --phase 8` judges. Flagged for the
operator rather than decided by the lead.

**Nothing else is built.** The costing is in `docs/dataset/phase-8-findings.md` and no item in
it is approved.

### Report verification (draft v2): the findings document's tier 3 mean is by a different definition from the module's

**Agent:** Lead · **Task:** operator's remaining items for the report, draft v2 · **Date:** 2026-09-21

**What happened.** The report states the tier 3 mean net return per trade as −1.08%, computed by the
committed acceptance module; `docs/dataset/phase-7-findings.md:1309` states −0.70% for the same twelve
trades. Re-running `promotion_verdict` over the twelve `trades` rows, with holds built exactly as
`engines/tournament/engine.py:_holds` builds them, gives −1.0766%; `avg(trades.realised_pnl_pct)` gives
the same.

**Why.** −0.70% is the sum of realised PnL over the trade count and the *starting balance*
(−421.96 / 12 / 5,000 = −0.7033%), i.e. the −8.44% equity return divided by twelve. The module's mean is
over each trade's own entry notional. The findings row mixes the two: its tier 5 figure in the same cell,
−2.19%, is the per-trade mean. The pre-registered bar is in per-trade units, so −1.08% is the comparable
figure. Two more things found the same way: the findings' and the report's "mean overshoot 0.51 pp" on the
13 stops is 0.488 pp from the rows (median 0.163 is right), and the report's "Bitcoin rose 58.2%" has no
source in the repository (the partitions and the archive give +58.0% tick to tick, +58.1% by daily closes).

**Fix.** None to the code or the databases. Nothing in the report was edited, as instructed; the findings
file is left as written and the correction is proposed in `docs/report/verification_draft_v2.md` §1 for
the operator to apply or refuse. The full Chapter 6 check, with every query, is in that file; the
refused-candidate labels are `docs/report/data/refused_candidates_labelled.csv`; the console capture is
`docs/report/figures/fig5_5_console.png`, taken over a renamed *copy* of the tier 3 database with the
console's clock injected at 2025-01-03 23:46:30Z.

**Consequence.** The PDF also embeds a pre-completion render of the exposure figure (tier 3 "1876 h",
where the committed regeneration says 2184 h), and the console renders equity at full stored precision
and pluralises "60 entrys" — both real properties of the committed console, reported not changed.

### F1: the facade was missing two methods, and no test could have noticed

**Agent:** Lead · **Task:** overnight item 1 · **Date:** 2026-09-21

**What happened.** `KrakenClient` claims to satisfy `MarketStreamProtocol` and the paper broker
calls it as one, but `recent_trades()` and `drain_gaps()` were never forwarded to the stream. The
daemon raised `AttributeError` on the first tick that asked for a trade tape.

**Why no test caught it.** Every existing facade test named the methods it expected, so the
methods nobody remembered to write were also the methods nobody remembered to test. A list of
names cannot catch a missing name.

**Fix.** Two forwarders, and a test that **discovers** the surface instead of restating it: it
walks `MarketStreamProtocol.__protocol_attrs__` and asserts `KrakenClient` both has each
attribute and delegates it to the stream object. Adding a method to the protocol now fails this
test until the facade forwards it. Criterion `live_client_serves_the_stream` PASS.

### F3: the defect was two defects, and the second one was in the balances

**Agent:** Lead · **Task:** overnight item 3 · **Date:** 2026-09-21

**What happened.** Phase 7 recorded F3 as "`map_asset_pairs` keys by REST name, engines want v2
names" — `XXBTZUSD` where everything downstream says `BTC/USD`. Checked against the recordings
before writing anything, and found a second half nobody had recorded: `map_balances` returns
**REST asset codes** too, so a wallet arrives as `XXBT`/`ZUSD` while positions and pair rules
speak `BTC` and `USD`. Fixing only the pair keys would have produced a daemon that subscribed
correctly and then could not find the money.

**What the recordings actually say.** 1,450 pairs in the live response. `wsname` gives the v2 name
directly for all of them, so the names are **read, not constructed** — with two aliases,
`XBT→BTC` and `XDG→DOGE`, needed for the base/quote fields, which have no `wsname`. The naive
"strip the leading X/Z" rule that looked reasonable from memory is wrong on real data: it turns
`XTZ` into `TZ`. That is now an assertion, not a comment.

**Fix.** `_engine_names()` prefers `wsname` and **falls back to the key** when it is absent, which
is what keeps the Phase 0 fixture (invented, no `wsname`) working untouched — invariant 11, the
recording is not edited to suit the code. `asset_code_names()` builds the code→name map from the
same response; `map_balances` takes it and **sums collisions**, because two REST codes can map to
one engine name. Unknown codes pass through unchanged rather than being dropped, so a new listing
is visible rather than invisible. Criterion `pair_rules_key_on_engine_names` PASS.

**Its gate went red, and it caught what the tests could not.** Two things, both real:
`WS_ASSET_ALIASES: Final` with **no `Final` imported** — every test passed, because
`from __future__ import annotations` makes the annotation a string at runtime, and only
`mypy --strict` and `ruff` saw it; and `check_rules()` in `scripts/record_asset_pairs.py`, which
reports a recording's dropped pairs as `set(result) - set(snapshot.pairs)` and so named **all
1,450** of them once the snapshot was keyed by symbol. The second is the lesson worth keeping:
re-keying a mapping breaks every caller that subtracts one key space from the other, and the
caller was in a script nothing about F3 pointed at. Joined through a new public
`engine_pair_names()` rather than re-keyed — reasons and the two rejected alternatives in **D13**
— and a grep confirmed no other consumer of `PairRulesSnapshot.pairs` keys by REST name. One fix
attempt; re-gated as `p8-f3b-pair-names`.

### Access control: the kill switch was reachable from any page the browser visited

**Agent:** Lead · **Task:** overnight item 5, operator items 1 and 2 · **Date:** 2026-09-21

**What happened.** `POST /api/command/close_all` takes no body, no token and no confirmation, so
it is a **simple request**: a cross-origin form POST fires it with no preflight and the browser
sends it happily. Any page the operator had open could liquidate the account. `/ws` was accepted
without looking at `Origin` at all, so any local page could read the balance, the positions and
the trades. And `--host 0.0.0.0` was one flag from putting all of that on the network.

**Fix, and what it deliberately is not.** `foreign_origin(origin, host)` compares authorities:
no `Origin` → serve (curl, uvicorn's own probe, and the ASGI call a verify criterion makes, with
the loopback bind as their control); matching authority → serve; anything else → **403 before the
command name is looked at**, so a foreign caller cannot use the 404 to enumerate command names. A
missing `Host` with a stated `Origin` is refused: fail closed, nothing to compare against.
`off_loopback_refusal()` refuses to start off loopback unless `ACSOE_CONSOLE_TOKEN` is set, and
**its value is not checked** — that is item 3, which the operator deferred — so the refusal text
says in as many words that setting it authenticates nothing. An acknowledgement, not a
credential; recording that distinction in the user-visible string is the point.

Driven through ASGI rather than `TestClient`, for the reason `test_app.py` already gives: the
repository's network guard patches `httpx.Client.send`, so a `TestClient` request never arrives.
Criterion `console_refuses_a_foreign_origin` PASS.

### The smoke run: it ran, it read the real exchange, and the opportunity chain never started

**Agent:** Lead · **Task:** overnight item 4 · **Date:** 2026-09-21

**What happened, first attempt.** The daemon froze on cycle 4 and engine 1 errored on every tick:
`PaperBrokerError: no pair rules for XBT/USD`. The cause was mine, not the code's: I ran it
against `data/db/acsoe.sqlite`, which holds the **Phase 0 seed** — built deliberately with a 20%
drawdown, an 8-loss streak and two open positions so Phase 3 could test `safety`. The daemon read
that as its own history and did exactly what it should: `safety` escalated `close_all`. The two
seeded positions are named `XBT/USD`, and the live client serves `BTC/USD`, so the broker could
not price them.

**What that is worth knowing.** No test catches the seed's naming, because the fake client's own
fixture is keyed the modern way — the two fixtures disagree and only a live run puts them in the
same process. Recorded as **D12**. The seeded file was copied to scratch **before** anything ran
and is restored byte-identical (verified with `cmp`); both run databases are kept as evidence.

**Second attempt, on a clean database — the real result.** 22 ticks, 04:42–05:03Z, private calls
enabled, `TradeVolume` and `AssetPairs` both HTTP 200, activation consumed and `mode: running`,
an equity row on every tick, and a subscription of **~1,450 pairs in v2 names that the v2 feed
accepted** — F1 and F3 proven end to end against the real exchange, which is what a smoke run is
for.

**And the finding.** 0 `scout_tallies`, 0 rejections, 0 orders: **18 of the 22 ticks were blocked
by `data_guard`**, 17 distinct thin pairs between them, each a quote older than the 120 s the
guard allows. The guard judges the whole tick on the oldest quote across **every** subscribed
pair. With 1,450 real pairs some illiquid one has always been quiet for two minutes, so the guard
blocks for ever. Phase 6 never saw it (four fake pairs) and Phase 7 never saw it (D7 stamps the
replay quote at `now` — recorded then as making this condition "structurally inert for the whole
simulation"). Live, nothing makes it inert.

**Not fixed, on purpose.** Changing which pairs a guard judges changes what the system trades:
that is a WHAT decision, so it is **D10, OPEN**, with four options and a recommendation, and the
item is skipped rather than decided. No smoke digest is committed, so
`daemon_reads_the_real_exchange` stays **PENDING** — making it pass on a run that never reached
the funnel would be exactly the kind of green that means nothing. The second finding, that the
screens show the paper ledger's 5,000.00 and not the real wallet, is **D11, OPEN**.

### The read-only key for `fees.py`: everything but the key

**Agent:** Lead · **Task:** overnight item 2 · **Date:** 2026-09-21

**What happened.** `fees.py` polls `TradeVolume` with the same key the daemon will trade on, which
means a recorder process holds trade-and-withdraw permissions it has no use for. The operator's
instruction was to build everything except the key itself.

**Fix.** `parse_env_credentials` now prefers `KRAKEN_READONLY_API_KEY`/`_SECRET` and falls back to
the existing pair, so the running process keeps working with **no key in `.env` and no restart**:
credentials are re-read on every poll, so the switch happens on the next poll after the operator
saves the file. A half-written pair (key present, secret missing) falls back rather than failing,
which is the state `.env` is in while it is being edited. Redaction covers the new names too —
tested, not assumed. Exact instructions, down to which permission boxes to leave unticked
(**Withdraw Funds** first among them), are in `readonly-key-instructions.md`. The process was not
restarted: the operator's DO NOT list is explicit, and it does not need to be.
