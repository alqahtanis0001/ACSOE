# Phase 8 findings: what the live path costs, measured from the code

**Written 2026-09-21, before anything is built.** Every estimate below is grounded in a file and
line read for this purpose, by two read-only audits (the live client and the console). **They are
estimates, not measurements.** Phase 7's build estimate ran about five hours over because it was
a sum of parts, so each item here carries a range, and the ranges are of *work*, excluding the
~40 minutes a boundary gate takes and excluding the operator's own time.

**Nothing here is approved and nothing is built beyond the housekeeping.**

---

## 0. The finding that changes the shape of the answer

**Paper mode already wraps the real Kraken client.** `cli/engine.py:125-132`:

```python
real = KrakenClient(rest=rest, stream=stream)
kraken: Any = real
if config.mode == "paper":
    kraken = PaperBroker(real, store=store, config=config, clock=clock)
```

So "the system live, reading the real market, sizing against my real wallet, deciding and
refusing, all visible on screen" — the operator's path (a) — **does not need live mode at all.**
It needs the four live-path defects fixed so the real client can actually serve the chain, and it
runs in paper, where the only simulated thing is the fill.

That matters for cost and for risk:

- **`platform/live_guard.py` does not exist, and `platform/config.py:982-986` refuses `mode:
  live` outright.** Building the guard is Phase 8's workflow row and is real work.
- **Path (a) does not need it.** It also cannot place an order by accident, because the paper
  broker is what stands between engine 18 and Kraken.
- **Path (b) — a real fill — needs the guard, the live wiring, and the order surface**, which
  `clients/kraken/rest.py` currently refuses on purpose until Phase 8.

**Recommendation: build (a) in paper against the real exchange.** It gives the operator every
screen they asked for, against their real wallet and the real market, with no path to a real
order. The estimates below are built that way, and the one-line cost of doing (a) in live mode
instead is given at the end of Q2.

---

## Q0. Housekeeping item 2 needs a ruling: it is not a one-line change

`scout.rank_feature: expected_move` was written into `config/default.yaml` and **reverted**.
With the key set, engine 7 ranks through the shared function, which loads the artefacts named
by `models.*_run_id`. **Those keys are absent from the committed config and `models/` is
gitignored**, so wherever the artefacts are missing — a fresh clone, and every scout test
fixture — the ranking cannot be scored and engine 7 **blocks every tick**
(`scout_inputs_unavailable`) instead of ranking alphabetically. 34 of 63 scout tests went red on
that behaviour. Verified: the committed config loads with `rank_feature = expected_move` and all
three `models.*_run_id = None`.

| Option | What it gives | Cost | Risk |
|---|---|---|---|
| **A. Leave it absent** (today) | Nothing changes | 0 | The daemon ranks alphabetically unless someone remembers `--ranking expected_move`. This is the open question the tracker has carried since 2026-09-19 |
| **B. Set the key *and* the three `models.*_run_id`** to the Phase 7 artefacts, which exist on this machine | The daemon on this machine ranks by expected move with no flag. A clone without artefacts fails closed — arguably right for a trading system | Config ~15 min + **1.5–2.5 h** updating the scout tests to pin the key absent for the filter-only tests (B's lane) | The committed config then names artefacts absent from a clone; engines 8 and 13 already fail closed on exactly that, so it is consistent, but it must be stated in the config comment |
| **C. Set the key in a separate daemon config** (e.g. `config/live.yaml`) that the daemon is started with, leaving `default.yaml` as the clone-safe baseline | The operator's daemon ranks by expected move; fresh clones and tests are untouched | **0.5–1 h** | Two config files to keep in step; the answer to "what does the daemon rank by" becomes "whichever file you started it with", which is the class of problem the operator asked to remove |

**My recommendation: B**, because it removes the flag dependency in the one file everything
reads, and the fail-closed behaviour on a clone is the correct direction for a system that
should not trade without the models it was measured with. **C** is the cheap answer if you want
the daemon fixed today without touching B's tests. **Not decided by the lead.**

## Q1. The four live-path defects

All four are **still open**, verified in the working tree. Layer assignments follow
`context/ownership.md`.

| # | Defect | Where | Fix | Estimate | Blocking? |
|---|---|---|---|---|---|
| **F1** | Live client exposes no `recent_trades` (and no `drain_gaps`) | `clients/kraken/client.py:99-124` — the stream block forwards `set_subscription`, `subscription`, `drain`, `drain_trades`, `latest_quote`, `connected`, `gaps` and stops | Forward the two methods the transport already has (`ws.py:349`, `ws.py:364`), plus a test that walks `MarketStreamProtocol` against `KrakenClient` as `tests/clients/paper/test_broker.py:773` already does against `PaperBroker` | **1–1.5 h** (A) | **YES — blocking today.** The paper broker raises `PaperBrokerError` in `_observe_trades` (`broker.py:331-338`), called from `balance()` on **every tick**, and that is not a `KrakenError`, so engine 1 re-raises it. The daemon cannot complete a single tick against the real client |
| **F2** | `TradeVolume` mapped from invented fixture shape, sends no pair | `rest.py:297-316` (mapper) and `rest.py:668` (`params={}`) | Rewrite the mapper against Kraken's real envelope (`currency`, `volume`, `fees[pair].fee`, `fees_maker[pair].fee`), **divide by 100** (Kraken returns percent strings and `FeeTierSnapshot` rejects > 1), decide what `tier` means now the response has no tier field, send `{"pair": …}`, and replace the invented fixture with a recording | **3–5 h** (A) | Degrading, but total: every one of the five keys it requires is absent from the real response, so the call raises, engine 1 records a failed fetch and **engine 10 blocks every candidate for a missing fee**. The daemon runs and never trades |
| **F3** | `AssetPairs` keyed by REST names | `rest.py:268-284` keys `PairRule` on the raw REST key (`XXBTZUSD`, quote `ZUSD`) | **Option 1, remap what is already fetched:** derive the v2 symbol from each entry's own `wsname`/`altname` plus the asset aliases (`XBT`→`BTC`, `XDG`→`DOGE`), and normalise `base`/`quote`. **Option 2, subscribe to the v2 `instrument` channel** and take Kraken's own keys, as the replay path does (`replay_scenario.py:272-344`) | **Option 1: 2–4 h. Option 2: 6–10 h** (A) | **YES — blocking live.** Bigger than engine 7: engine 2 derives the **websocket subscription itself** from these rules (`market_data_recorder/engine.py:200-212`), so the daemon would subscribe with REST symbols the v2 feed rejects and receive no market data at all. Invisible in paper today only because the fixture is keyed the right way |
| **F4** | Engine 7 ignores pair status | `clients/kraken/contracts.py:178-224` has no `status` field; `engines/scout/contracts.py:346-357` has no reason code | **A:** add `status` to `PairRule`, read it in `map_asset_pairs` (it is already in the fetched body), mirror it in `replay_scenario.py` for parity. **B:** add `REASON_PAIR_NOT_ONLINE`, insert it into `EXCLUSION_REASONS` in the right position (order is behaviour — the tally must still add up), branch in `_exclusion`, update the README's reason table | **A 1–1.5 h + B 1.5–2.5 h = 2.5–4 h** | Degrading — **and the only one that fails toward placing a bad order.** Measured in the committed recording: **78 `cancel_only` and 17 `post_only` pairs of 1,450**. One that quotes passes all ten current exclusions and can be entered |

**Blocking summary:** F1 blocks any tick against the real client today. F3 blocks live and breaks
the market-data subscription. F2 lets the daemon run but never trade. F4 never fails; it
misbehaves.

**Two adjacent findings from the audit, not in the operator's list:**

1. **`drain_gaps` is missing from the live facade for the same reason as `recent_trades`.** The
   broker calls it unguarded (`broker.py:296`); engine 2 guards it with `getattr`
   (`market_data_recorder/engine.py:225`) and therefore **records zero gaps silently** — the live
   archive would read as continuous across every reconnect, which invariant 11 cares about. Fix
   it in the same edit as F1; it is inside F1's estimate.
2. **No test walks `MarketStreamProtocol` against `KrakenClient`.** The walk exists only for the
   paper broker. That single missing test is why F1 survived. It is in F1's estimate.

**One dependency on the operator:** F2's mapper should be written against a **recorded real
response**, which needs one authenticated `TradeVolume` call with a pair. That is about 15
minutes of operator time (or the lead runs it with the existing read-only key) and it must be
recorded to a fixture with its URL and capture time, as Phase 7 did for the fee schedule.

---

## Q2. The minimum path to a live activation that genuinely runs the chain

### (a) Everything except a real fill — recommended in **paper against the real exchange**

In order, because each item unblocks the next:

| Step | Work | Estimate |
|---|---|---|
| a1 | **F1** — the client serves the stream the chain needs | 1–1.5 h |
| a2 | **F3** — pair rules keyed the way the engines and the websocket key them | 2–4 h (option 1) |
| a3 | **F2** — real fees, so the cost gate prices a real hurdle and refuses for a real reason | 3–5 h |
| a4 | **F4** — `cancel_only` and `post_only` pairs out of the universe | 2.5–4 h |
| a5 | **A smoke run against the real exchange**: the daemon up, one bar's full chain, the funnel and refusals recorded, with the operator's real balance | 1–2 h |
| a6 | **The main window** (Q4) | 6.5–10.5 h |
| a7 | **The activation control** (Q5) | 2–3.5 h |
| a8 | **Console access control** (Q6) | 0.75–1.5 h |
| | **Total (a)** | **19.75–32 h** |

**If (a) must run in `mode: live` rather than paper**, add `live_guard.py` and the live wiring
below (b1+b2, **3–5 h**) — and accept that with the guard satisfied, a candidate that clears
every gate *will* place a real order, because nothing else stands in the way. At tier 1 nothing
clears the cost gate, so the operator's stated plan works; it relies on the fee tier, not on a
safety mechanism. **I recommend paper-against-real for (a) and live only in (b).**

### (b) A real order placed and filled

| Step | Work | Estimate |
|---|---|---|
| b1 | **`platform/live_guard.py`**: the three switches of invariant 1, each proven individually required | 2–3 h |
| b2 | **Live wiring**: `platform/config.py:982-986` and `cli/engine.py:332-342` currently refuse anything but paper; open the live path deliberately, with the guard in front | 1–2 h |
| b3 | **The order surface**: `add_order`, `cancel_order`, `query_orders`, `open_orders` forward to `rest.py`, which refuses until Phase 8. Implement against Kraken's **validate mode** first, with `userref` idempotency (invariant 8) | 4–6 h |
| b4 | **`close_all` end to end, live** (workflow row): cancels every resting entry, closes every position, and a daemon killed mid-liquidation finishes on restart | 3–5 h |
| b5 | **One real minimum-size order**, watched, with its walk-through written up as Phase 6 did for the first paper trade | 1–2 h + operator time |
| b6 | **The 7-day soak** (workflow row): `soak_digest.json`, one unbroken `run_id`, contiguous `cycle_id`, zero unhandled exceptions | 2 h work + 7 days elapsed |
| | **Total (b), on top of (a)** | **13–20 h** plus the soak's elapsed week |

---

## Q3. The UI as it stands

**Scale:** 7 Python modules (~2,735 lines), one HTML page, one JS file, 9 routes. It is a
single-page app: Live / History / Research are CSS `:target` panes, not routes.

**What works, end to end:**

- **Activate, Freeze, Close all** buttons → `POST /api/command/{name}` → a `commands` row
  (`app.py:284-316`, `commands.py:219-239`), claimed and applied by the real orchestrator
  (`core/orchestrator.py:394-427`), with integration tests. **Close all** has a confirm step.
- The write connection is narrowed by a **SQLite authorizer** that denies every table but
  `commands`; the read connection is opened read-only with no writable fallback.
- **Status band** (mode, state, balance, age), **open positions** (10 columns, live marks),
  **cycle feed**, **closed trades** (8 columns), **refused candidates with prose reasons**
  (56-entry map, 44 tests), **leaderboard** (13 columns).
- **Push over one WebSocket** when the store watermark moves, 500 ms poll server-side; the
  browser never polls; a dropped socket shows a banner and reconnects with backoff.
- **205 tests** under `tests/console/`, including a design contract (palette, type scale, focus
  rings, reduced motion, no third-party fetches).

**What is broken or stale:**

- **`/health` reports `"phase": 1`** (`app.py:153`). The one field that identifies the build is
  wrong.
- **The funnel's two headline numbers are an excuse string.** `reader.py:144-146` returns "not
  recorded yet — engine 7 counts this on the tick and no table stores it" for *pairs scanned* and
  *entered the universe*. **That sentence stopped being true in Phase 7:** `scout_tallies`
  (migration 0007) stores exactly those numbers and the console never reads the table. This is
  the design doc's flagship empty state (`ui-context.md:95-99`).
- **`scout_tallies` and `approvals` are missing from `WATERMARK_TABLES`**
  (`clients/store/client.py:62-74`), so a tick that writes only a tally moves nothing and the
  socket pushes nothing. Wiring the funnel without this makes a screen that updates late.
- **A static sentence in the template says SHAP "arrives with the predictor in Phase 5. Nothing
  is computed yet"** (`index.html:281-284`) — false now, and visible until the first fetch
  overwrites it, or permanently if JS fails.
- **The amber live frame is unreachable**, because `mode: live` is refused by the config loader.
  The one bold visual move in the design doc has never been seen outside tests.

**What is dead — data sent to the browser and never rendered:** `resting_order_count` (the
operator cannot see resting entry orders anywhere, yet Close all's confirmation promises to
cancel them), `open_position_count`, `system_mode`, `run_id`, `equity_ts`, position `timeout_at`
(the template's own comment argues it is needed and there is no column), and trade
`entry_fee`/`exit_fee` (so realised PnL cannot be reconciled on screen).

**What is missing entirely:** anything from the `approvals` table (why a trade was *approved* —
the Phase 7 prerequisite that was built and is not shown), an equity curve, drawdown against the
stored peak, any per-reason breakdown of exclusions, any link to the recording manager, and any
SHAP rendering (the pane is structurally empty by design: `ShapPane` has no rows field).

---

## Q4. The main window, costed per item

| Item | What it needs | Estimate |
|---|---|---|
| **Real wallet balance and equity** | Already rendered from `equity_snapshots`. Against the real client it needs F1–F3 to be true, not console work. Add cash-vs-positions split and the stored peak | **0.5–1 h** |
| **System state: paper/live, trading/frozen, and why** | The four readings exist. Missing: *why* — the breaker's own sentence. `block_records` carries it ("Safety breaker: drawdown 10.07% at or past the 10.00% limit"); surface the latest one in the band | **1–1.5 h** |
| **The live decision stream** — what it looked at, what it ranked top, which gate refused it, with numbers | The refused-candidates table already shows pair, refusing gate, expected move, friction, net edge, hurdle. Missing: **what was ranked top and why it was examined**, which is `scout_tallies.ranked` (stored, unread) | **2–3 h** |
| **Open positions and closed trades with PnL** | Both exist. Add the missing columns the payload already carries: `timeout_at`, fees | **0.75–1 h** |
| **The funnel: scanned, examined, refused by gate, approved** | Read `scout_tallies` for the two missing stages, add `scout_tallies` + `approvals` to `WATERMARK_TABLES`, and add the per-reason `excluded` breakdown | **2–3 h** |
| **Recording master page linked in, not replaced** | A link to `127.0.0.1:8766`, plus a reachability indicator so a dead manager is visible. The two apps share nothing today | **0.25–0.5 h** |
| | **Total** | **6.5–10.5 h** |

**At tier 1 this window is honest by construction:** the funnel shows 1,450 scanned and ~190
entered, the decision stream shows the ranked candidate, and the refusal table shows the cost
gate's four numbers and how far short the candidate fell. That is the screen the operator asked
for, and it is what Phase 7's data already looks like.

---

## Q5. The activation button, and what "tested" means for it

The control exists and works. What it does **not** have is a live/paper distinction, because
live mode has never been reachable.

**What "tested" has to mean for a control that risks real money — five properties, each with its
own test:**

1. **It states the mode it will act in, on the button itself**, read from the running daemon's
   config and not from the page's memory. A button that says "Activate" in both modes is the
   defect.
2. **Live requires a second, different confirmation** — the `close_all` pattern
   (`commands.py:75` `CONFIRMED_COMMANDS`), extended to activation **when the mode is live**.
   Paper keeps one click.
3. **It cannot go live by accident**: the console cannot change the mode. Mode comes from
   invariant 1's three switches (env var, config field, dated `LIVE_CONFIRMED` file), and no
   console path may write any of them. A test asserts the console package cannot reach them.
4. **The screen shows the mode the daemon is in, not the mode the page was loaded with.** If a
   daemon restarts into paper while the page says live, the page is wrong until it reloads. The
   band already carries `system_mode`; it is not rendered.
5. **The refusal path is visible**: pressing Activate while the guard refuses live must show the
   refusal and its reason, not silently write a row that the daemon applies as paper.

**Estimate: 2–3.5 h** (C for the screen half, Lead for the command reader's half), with the
live-mode half only meaningful once `live_guard.py` exists (b1).

---

## Q6. Who can reach the console today, and the lightest adequate protection

**Today: no authentication of any kind.** No login, token, password, session, CORS config, rate
limit or IP allowlist anywhere in `src/acsoe/console` or the recording manager — greps for
`csrf|Authorization|login|HTTPBasic|api_key|add_middleware` return nothing.

- **Bind:** `127.0.0.1:8765` by default (`cli/main.py:59`), so **only this machine** reaches it
  today. The recording manager is the same on 8766, with an explicit note that loopback is
  deliberate.
- **`--host 0.0.0.0` is one flag away**, and behind it there is nothing at all.
- **No CSRF protection on `POST /api/command/{name}`**, which takes no body and no token
  (deliberately: `app.py:290-293` argues a server-side token would be a second gate on the kill
  switch). **A page in the operator's browser, from any origin, can POST `close_all`** — a simple
  cross-origin form POST triggers no preflight. Loopback is the only thing preventing it today.
- **No `Origin` check on the WebSocket** (`websocket.py:168`), so any local page can read every
  screen.

**Lightest adequate protection — 45 minutes to 1.5 hours:**

1. **Keep the loopback bind and make widening it deliberate** (~15 min): refuse to start on a
   non-loopback host unless a token is configured. This is the single highest-value line.
2. **An `Origin` check on the WebSocket and on POST** (~20–30 min): reject requests whose
   `Origin` is not the console's own. That closes the cross-origin kill-switch hole without
   putting a token in front of the operator's own kill switch.
3. **A shared secret from `.env` for non-loopback use** (~20–30 min): a header or cookie checked
   by one dependency, required only when bound off-loopback. Never committed, never logged.

**Under an hour if only 1 and 2 are done — which I recommend as the minimum**, because they need
no new secret and no login screen, and they remove the only remotely exploitable path (a
malicious page in the operator's own browser firing the kill switch). Item 3 is what makes "open
the console on my phone" safe, and should not be attempted without TLS in front of it.

---

## Totals, and the shortest sensible order

| | Estimate |
|---|---|
| **Path (a)** — the system live against the real exchange, deciding and refusing, all visible, no real fill | **19.75–32 h** (paper-against-real; add 3–5 h for `mode: live`) |
| **Path (b)** — a real order placed and filled | **+13–20 h**, plus 7 days elapsed for the soak |

**Order:**

1. **F1** (1–1.5 h) — nothing runs against the real client until this lands.
2. **F3** (2–4 h) — without it there is no market-data subscription and no universe.
3. **Smoke run** (1–2 h) — prove the chain ticks against the real exchange before building
   screens on top of it.
4. **F2** (3–5 h) — real fees, so refusals mean something.
5. **Console access control, items 1 and 2** (~45 min) — before the screen becomes worth looking
   at from elsewhere.
6. **The main window** (6.5–10.5 h), funnel last since it needs the watermark fix.
7. **F4** (2.5–4 h) — before any order can be placed, and it is the one that fails toward a bad
   order.
8. **The activation control** (2–3.5 h).
9. Then (b): `live_guard` → live wiring → order surface in validate mode → `close_all` live →
   one real order → soak.

**What can be cut to see (a) sooner, and what it costs:**

- **Cut F4 out of (a) to after the window** (saves 2.5–4 h). Safe only while no order can be
  placed — which is true in paper-against-real. **It must land before (b).**
- **Cut the funnel panel** (saves 2–3 h): the biggest single UI item, because it needs the
  watermark fix too. Cost: the screen shows refusals but not how many pairs were considered —
  the operator's "scanned / examined / refused" line is exactly what it drops.
- **Cut F2 and accept "no fee data" refusals** (saves 3–5 h): the system visibly runs and
  refuses, but every refusal reads *missing fee tier* rather than *net edge below hurdle*. **I
  advise against it** — it makes tier 1 look broken rather than selective, which is the opposite
  of the operator's requirement.
- **Fastest honest (a): F1 + F3 + smoke + access control 1–2 = 5–8 h**, giving a daemon that runs
  against the real market with the existing screens. Everything else is how good the window is.
