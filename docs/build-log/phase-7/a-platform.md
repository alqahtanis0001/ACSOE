# Phase 7 — Agent A (Platform)

## Recorder gap audit, 2026-09-19 (separate from Phase 7 spec work)

**Agent:** A · **Task:** recorder gap audit, on the lead's message · **Date:** 2026-09-19

This was an audit only. No code was edited. The recorder (`record.py` under `supervise.py`, running
since 2026-09-16 21:09Z) was not stopped or restarted. Spec 127 was not touched. To read the field
sets, I fetched public `AssetPairs` and one v2 `instrument` snapshot into the session scratchpad.
Neither went into `tests/fixtures/`.

The question: what does the chain read live that a replay of a recorded day cannot get from
`data/raw/`, `data/summaries/` and `data/raw/funding/`?

### Correction 1: pair rules come from the v2 `instrument` channel, not REST `AssetPairs`

**What happened.** The operator described the recorder as reading an instrument snapshot at
startup, using it to choose the subscription list, and then discarding it. That is correct. It
subscribes to the WebSocket v2 `instrument` channel on a separate short-lived connection
(`scripts/record.py:1207-1250`), keeps only `symbol`, `status`, `quote`, `price_precision` and
`qty_precision` (`record.py:1224-1243`), unsubscribes, and ranks pairs by a `ticker` snapshot. The
session marker records the tier lists, the depth and `checksum_verifiable` (`record.py:2648-2669`).
It records no rule values.

**What the snapshot carries** (fetched 2026-09-19, 1,450 pairs, 842 assets). Per pair: `symbol`,
`base`, `quote`, `status`, `qty_precision`, `qty_increment`, `price_precision`, `cost_precision`,
`cost_min`, `qty_min`, `tick_size`, `price_increment`, `marginable`, `has_index`,
`ws_display_price_precision`, plus margin fields on 266 pairs. Per asset: `id`, `status`,
`precision`, `precision_display`, `borrowable`, `collateral_value`, `class`.

**It is equivalent to REST `AssetPairs` for every field engine 1 uses.** I joined the two on the
same minute's fetch: 1,419 pairs matched (via `wsname`, with the XBT→BTC and XDG→DOGE aliases). All
1,419 agree exactly on `ordermin`=`qty_min`, `costmin`=`cost_min`, `tick_size`,
`pair_decimals`=`price_precision`, `lot_decimals`=`qty_precision`, and `status`. Zero mismatches.
The 31 unmatched pairs are XBT-quoted, and XBT was not aliased on the quote side.

**Why the v2 form is the one to record, not REST.** `map_asset_pairs`
(`clients/kraken/rest.py:257-294`) keys rules by REST name (`XXBTZUSD`), with `base` `XXBT` and
`quote` `ZUSD`. Engine 3 keys quotes by the v2 trade symbol (`market_sensor/engine.py:272-289`,
`BTC/USD`). Engine 7 takes the union of both key sets (`scout/engine.py:215`). A REST-keyed rule
set would therefore:
- give every v2 name `pair_rules_missing` (`scout/engine.py:275`);
- give every REST name `no_live_quote`;
- fail the stable-quote check (`ZUSD` is not in `trading.stable_quote_currencies`,
  `scout/engine.py:292-296`) and the `no_fx_rate` check against `USD` (`scout/engine.py:329`).

The v2 snapshot is keyed exactly as engines 3, 7, 9, 10 and 11 read it.

**This is also a live defect, outside the recorder.** The same key mismatch applies to the live
REST client today. It has never shown up because no live `AssetPairs` has reached engine 7: the
fixtures are invented and already v2-keyed. `clients/kraken/` is mine but read-only in this
session, so this goes to the lead rather than being fixed here.

**Also checked:** REST `AssetPairs` `fees` and `fees_maker` are empty lists on all 1,450 pairs. The
fee schedule cannot be recovered from `AssetPairs`.

### Correction 2: the fee tier needs `pair`, and the live mapping does not match Kraken's shape

**What happened.** Nothing records `TradeVolume`. That is correct. Two further facts bear on
recording it.

1. **Kraken's documented shape** (docs.kraken.com, get-trade-volume, read 2026-09-19) is
   `currency`, `asset_class`, `volume`, `inputs{domain_spot_volume_30d, ...}`, `fees{pair:{fee,
   minfee, maxfee, nextfee, tiervolume, nextvolume, ...}}` (taker), `fees_maker{...}` (maker),
   `schedules[]` (with `fee_schedule=true`), and `volume_subaccounts`. **Fees are per pair and
   are returned only if `pair` is sent.** `map_trade_volume` (`rest.py:297-316`) requires `tier`,
   `volume_30d`, `maker_fee_pct` and `taker_fee_pct`. None of those exist in the real response;
   they come from the invented Phase 0 fixture `tests/fixtures/kraken/trade_volume.json`.
   `trade_volume()` also sends an empty form (`rest.py:668`). Against the real endpoint, the
   fetch therefore fails on the missing `tier` every time, and engine 10 blocks every pair live as
   well as in replay. Kraken's `fee` is a percent string (`"0.2600"` means 0.26%), while
   `FeeTierSnapshot` expects a ratio (`contracts.py:282-289`). A naive fix would pass the
   validator and be wrong by a factor of 100.
2. **`FeeTierSnapshot` has one maker and one taker for the account** (`contracts.py:260-299`).
   Kraken's fees differ by pair. The findings already name the stablecoin, pegged and FX fee
   class as a limitation. A recorded response should keep the per-pair map verbatim, so a replay
   client can serve the fee of the pair being priced.

**What a recording needs.** A signed `POST /0/private/TradeVolume` with `pair=<the subscribed
pairs, in REST names>` and `fee_schedule=true`, written verbatim with its time. The v2→REST name
mapping comes from public `AssetPairs` `wsname`, plus the two base aliases.

### Finding 3: the funding poller is not running, and nothing restarts it

**What happened.** No `funding.py` process exists, and the manager (`serve.py`) is not running
either. The last funding file is `data/raw/funding/funding__msi__2026-09-15.jsonl`, whose last
poll was 2026-09-15 08:00Z. Its `.funding.lock` stamp shows it was started by hand on
2026-09-11 22:22Z. `master.bat:80` starts `supervise.py`, which launches only `record.py`
(`supervise.py:441`). The startup folder holds only the `master` shortcut, and there is no
scheduled task.

**Why.** Something stopped both processes on 2026-09-15. The supervisor log for 09-11 ends at
05:04Z, and a new supervisor started at 13:49Z. The recorder came back through the startup
shortcut; the poller had no way back.

**Consequence.** About four days of open interest, 2026-09-15 09:00Z onward, cannot be recovered.
Funding rates can be backfilled. "Poll the fee tier hourly alongside the funding poller" would
inherit the same failure. Whatever runs the fee poll has to be supervised too. I did not restart
the poller: the brief said not to touch it, and restarting it is the operator's call.

### The chain, engine by engine

Tier 1 is the 10 pairs recorded raw: `book` depth 10, `ticker` and `trade`. On 2026-09-16 those
were USDT, BTC, USDC, ETH, ZEC, XRP, SOL, EUR, HYPE and ADA, all against USD. Tier 2 is about 140
pairs, recorded as one summary row per pair per minute only.

| Engine | Input read live | Recorded? | Class |
|---|---|---|---|
| 1 exchange | `asset_pairs()`: ordermin, costmin, tick_size, lot/pair_decimals, base, quote (`exchange/engine.py:122-129`) | **NO** | (i) session frame |
| 1 exchange | `trade_volume()`: maker/taker fee | **NO** | (i) hourly poll, needs credentials |
| 1 exchange | `balance()` | NO, and should not be | (iii) paper broker's ledger; the real balance is not a market fact |
| 3 market_sensor | `recent_trades()`, used for candles and per-tick `trade_ranges` (`market_sensor/engine.py:174-192, 220-257`) | Tier 1 YES (every trade verbatim: price, qty, side, ord_type, trade_id, timestamp). Tier 2 PARTIAL (per minute: count, volumes, last, vwap, and mid OHLC, but not trade low/high/open) | Tier 2 is (ii) |
| 3 market_sensor | `latest_quote()`: ticker bid/ask and its timestamp (`ws.py:459-472`) | Tier 1 YES (`ticker` recorded). Tier 2 NO (spread quantiles and mid only, no bid/ask per tick) | Tier 2 is (ii) |
| 3 market_sensor | `timeframes.*` and `published_bars` config; `previous_now` | Config, and replay-clock | n/a |
| 4 data_guard | quote `age_s`, `spread_pct`, `missing_bars`, `stream_available` (`data_guard/engine.py:87-146`) | Derivable from tier 1 ticker, trades, gap markers and `ts_recv` | n/a |
| 7 scout | `exchange.pair_rules` (v2-keyed), `market_sensor.quotes`, `exchange.balances`, equity from store, config (`scout/engine.py:183-252`) | Rules NO. Quotes tier 1 only. Balance and equity (iii) | (i) + (iii) |
| 9 order_book | `order_book(pair, 10)` REST Depth (`order_book/engine.py:139`); pair rules for the quote currency; balance as the notional | Book: tier 1 YES (depth 10, equal to `order_book.depth` 10), rebuilt from snapshot plus deltas and checkable against the CRC32 in every frame. Tier 2 NO (only depth in bps at $10k notional) | Tier 2 is (ii); balance (iii) |
| 10 cost | `fee_tier` maker/taker, `quotes.spread_pct`, `prediction.expected_move_pct`, `order_book.estimated_slippage_pct` (`cost/engine.py:158-185`) | Fee NO. Spread tier 1 YES. The other two are computed | (i) |
| 11 risk | pair rules, quotes, balances, store equity and positions, config (`risk/engine.py:424-458`) | Rules NO. Quotes tier 1. Rest (iii) | (i) + (iii) |
| paper broker | trade prints after placement (`broker.py:342`), REST book depth 10 for the post-only cross check and taker walk (`broker.py:537, 573`), taker/maker rate from `trade_volume`, quote currency from `asset_pairs` (`broker.py:495-502`) | Tier 1 prints and book YES. Fees and rules NO | (i) |
| 5, 6, 8, 12, 13 | `market_sensor.candles` and `feature`; 6 needs BTC/USD and ETH/USD features; 8 and 13 need store model artefacts | Derivable from tier 1 trades (BTC and ETH have always been tier 1). Artefacts are not market data | n/a / (iii) |

**Derivable, so not missing:**
- Clock skew: `ts_exchange` and `ts_recv` are on every line.
- Book snapshot versus delta: the `type` field. Checksum: in every frame.
- Trade side and order type: verbatim in the trade frame.
- Subscription list over time: `session` start/stop markers carry the full subscribe params, a
  disk-guard degrade writes its own marker (`record.py:2229`), and every minute's heartbeat
  carries the live pair list.
- Reconnects: `gap` markers with `gap_ms` (`record.py:2041-2078`).
- Candles and per-tick trade ranges for tier 1.

**Partial.** A process restart or a hard kill writes no `gap` marker. `stop` is written in a
`finally` block, which a kill or power cut skips. The hole can still be derived from the last
`ts_recv` before the next `start` marker, and from the supervisor log (three launches since
2026-09-11: 09-11 22:22Z, 09-15 13:49Z, 09-16 21:09Z).

### The additional gaps, beyond the two known ones

1. **Pair status and its changes** (online, cancel_only, post_only, and limit_only or
   reduce_only or delisted if Kraken uses them; the 2026-09-19 snapshot showed 1,355 online, 78
   cancel_only, 17 post_only). The recorder reads status once, at startup, to filter. Changes
   mid-run are not seen. **No engine reads status at all**: `PairRule` has no status field, so a
   cancel_only pair would pass engine 7 live. The engine side is B's lane (7) and mine
   (`clients/kraken/`), and is out of scope here. The recording side comes free with option P1
   below.
2. **The asset list** (precision and status per asset). It is in the same `instrument` frame.
   Nothing reads it today.
3. **Tier 2 coverage** (class ii). Tier 2 pairs have no per-tick bid/ask, no trade prints and no
   book. In replay, engines 3 and 7 therefore see only the 10 tier-1 pairs, and 3 of those (USDT,
   USDC, EUR) are stable or FX. The replayable universe is about 7 pairs. Two ways to widen it,
   neither within the operator's scope:
   - add trade open/high/low to the summary row (schema v3). That gives minute-grain candles and
     trade ranges, but still no quote or book;
   - widen tier 1. Today tier 1 costs roughly 9-14 GB/day for 10 pairs.
   Either choice needs the operator's decision.
4. **The supervision gap** (Finding 3). This is operational rather than a format change, but
   without a fix the fee poll would fail silently in the same way.

### Recommended minimal builds (none started)

- **P1. Pair rules: keep the `instrument` channel subscribed on the tier 1 socket.** Add
  `instrument` to what `Stream` subscribes for tier 1 (`record.py:372`, `subscriptions` at
  `record.py:1153`, which needs a no-symbol case). Kraken then sends the full snapshot on every
  connect and reconnect, plus `update` frames on a listing or status change, and the existing raw
  sink writes them verbatim.
  - Cost: about 0.6 MB per snapshot, against roughly 10 GB/day.
  - Effort: about 2 h, including `tests/platform/test_record_format.py` and a check that
    `build_archive.py` and `recording_report.py` pass a non-trade channel through (both filter on
    `channel`, `build_archive.py:279`).
  - **Contestable.** The operator asked for a session-level frame, and this is a new subscription.
    The rejected option is to write the snapshot `discover_pairs` already holds into the `start`
    session marker (`record.py:2648`). That is about 1 h and strictly within scope, but it
    records the rules only at a process start (three times in eight days), misses every status
    change, and still needs a new code path to hold the full pair dicts. **I recommend P1 and flag
    it for the operator.**
- **P2. Fee tier: an hourly `TradeVolume` poll**, verbatim, with `pair` set to the subscribed
  pairs in REST names and `fee_schedule=true`, into `data/raw/fees/fees__<source>__<date>.jsonl`.
  It uses the funding poller's line schema and writes a gap marker on a failed slot. The same poll
  should also write public `AssetPairs` verbatim, which gives the v2→REST name map and a second,
  REST-shaped rule record.
  - Where it runs: `funding.py` holds no credentials by design and is copyable to a bare node.
    So P2 should be a new master-only script, `scripts/recording/fees.py`, that reuses
    `platform/config.py`'s `.env` loader and redaction and `rest.py`'s `sign_request`, rather than
    a second signer. The existing `trade_volume()` cannot be reused as it stands (Correction 2).
  - Effort: 3-4 h. **Over the three-hour line, so it goes to the operator with the options first.**
- **P3. Supervise the pollers.** `supervise.py` or `master.bat` launches and restarts
  `funding.py` (and P2), so a reboot brings them back. About 1-2 h.
- **Out of the operator's scope:**
  - fixing `map_trade_volume` and `trade_volume()` to the documented shape, and deciding the
    per-pair fee model (`FeeTierSnapshot` is account-level);
  - `map_asset_pairs` keying (REST names against v2 symbols);
  - engine 7 reading pair status;
  - tier 2 coverage.
  The first two are `clients/kraken/`, which is mine but read-only this session. The third is B's.
  The fourth is the operator's.

### Credentials

`KRAKEN_API_KEY` and `KRAKEN_API_SECRET` are not set in the process, user or machine environment.
`.env` has both names with non-empty values. `platform/config.py` `load_dotenv` reads that file
into the daemon's environment. The standalone recorder and funding poller never read it. Whether
the key is valid is unknown and I did not test it: the Phase 2 build log records that the operator
rotated the key, and a private call was outside this audit. Only `TradeVolume` (P2) needs
credentials. Its response carries the account's 30-day volume, which goes into the gitignored
archive (`.gitignore:10`) and never into a build log, a fixture or a commit.

### A-recorder — Decision: one supervisor, the recorder plus a config-listed set of pollers, re-read live

**Agent:** A-recorder · **Task:** P3-funding (operator ruling 2026-09-19) · **Date:** 2026-09-19

**The diagnosis this answers** is Finding 3 above. Nothing restarted the funding poller when the
machine went down on 2026-09-15, because `supervise.py` has exactly one child hardcoded. Its loop
(`supervise.py:409-535`) blocks in `child.wait()` on that one process.

**Options.**
1. A second supervisor instance per poller, each launched by its own line in `master.bat`.
2. Hardcode `funding.py` as a second child of the one supervisor.
3. One supervisor that runs the recorder plus the pollers listed under `recorder.pollers` in
   `config/recorder.yaml`, re-reading that list while it runs.

**Chose 3.**

**Because.** Option 1 multiplies console windows and log files. A second supervisor also cannot
share the recorder's status block, and that block is the one place the operator looks. Option 2
means P2 changes the supervisor's code, and code changes only take effect on a restart. That
would interrupt the recorder a second time at P2's boundary, and the recorder is the one
process whose lost minutes are gone for good.

**Hot re-read, and why it is safe.**
- The list is re-read on a fixed interval. The re-read touches only poller children: the
  recorder's process object is not in the set it adds to or removes from.
- A newly listed poller is launched on the next pass. A delisted one is terminated and logged.
- **A config that cannot be read changes nothing.** That covers a missing file, a YAML error,
  an OS error such as a Windows editor holding the file, or a `recorder` section that is not a
  mapping. The supervisor logs the failure and keeps the running set as it was. Without this, a
  half-saved file would stop every poller.
- An entry names a script by bare filename only. It is resolved beside `supervise.py` or one
  directory up, the same rule `find_recorder` uses, so a poller cannot be found somewhere
  unexpected.

So P2's boundary is a config entry and a new file, with no supervisor restart. One limit: a
change to `supervise.py` itself still needs a restart, and P3's switchover is that restart.

**Each poller is supervised exactly as the recorder is.**
- Backoff doubles while failures continue and resets after a run of `--healthy-run-s`.
- Exit code 2, "the lock is held by another live process", means wait and look again, with no
  backoff and no restart counted. `funding.py:997-999` uses 2 for its own lock, the same meaning
  as `record.py`. This matters at the switchover: if the hand-started poller (PID 42044) still
  holds the funding lock, the supervised one waits rather than crash-looping.
- Each poller's output goes to its own log file, `logs/<name>__<source>__<date>.log`, so the
  recorder's output stays readable. The recorder keeps its event names unchanged
  (`recorder_launching`, `recorder_exited`, and so on); pollers use `<name>_launching`,
  `<name>_exited`.

**Cost.**
- The healthy status block grows by one line per poller, so it is no longer always six lines.
  The test that pinned six lines is kept for the no-poller case, which is what a node package
  with no `pollers` key gets.
- A delisted poller is stopped. If a half-saved config parses as valid with an entry missing,
  that poller is stopped once and restarted on the next re-read. That is logged, and the
  alternative — never honouring a removal — leaves no way to stop a poller short of restarting
  the supervisor.

**One refinement found while writing it: the list is all or nothing.** The first design applied
the valid entries and skipped a bad one. That would *stop* whatever the bad entry used to be: a
typo in the `fees` line would silently stop a poller that was recording. So `parse_pollers`
refuses the whole list on any bad entry, the running set is kept, and the refusal appears in the
log and in the status block as a `pollers    list not applied: ...` line.

**A second, found by the same test: a missing script must never reach `Popen`.** Python exits 2
for "can't open file", and 2 is the lock wait. A poller listed before its file exists would sit
in `waiting` indefinitely, looking healthy. The script is resolved before launching, and a
missing one is a launch failure with backoff, shown as `cannot launch`.

**Fix.** `scripts/recording/supervise.py` now has a `Child` per process, and none of them blocks
in `wait`. `Supervisor` holds the recorder plus the listed pollers, and one loop polls each child
every `--refresh-s` and re-reads the list every `--reload-s` (default 30). New flags:
`--poller-dir` (repeatable; defaults to beside the file, then one directory up) and `--reload-s`.
A poller gets `--config` and `--source-id` like the recorder, never `--out`, because that flag
means the archive to `record.py` and a poller's own output directory to `funding.py`. The
`KeyboardInterrupt` path still does not terminate children, for the reason it never did: Ctrl+C
reaches the whole console group and a forced terminate would race the recorder's stop marker.
The file was CRLF in the working tree. It was rewritten whole as LF, so `git diff` shows only
real changes.

**Verification.**
- `tests/scripts/test_supervise.py`, 27 tests. These cover the restart path, backoff, lock wait
  and launch failure against an injected launcher at exact monotonic times; the list rules; hot
  reload, delisting and unreadable config; and one end-to-end run with real child processes. In
  that run, a poller listed 1.5 s into the run starts, a crashing poller restarts at least three
  times, and the recorder launches exactly once.
- Mutation sweep, 10 of 10 killed: no relaunch after a crash; backoff never doubles; exit 2
  treated as a crash; healthy run never resets; relaunch ignores the backoff; newly listed poller
  never started; unreadable config read as empty; bad entry dropped rather than refusing the
  list; reload relaunches running pollers; missing script handed to the launcher. Every anchor
  was asserted to occur exactly once, and the file was restored byte-for-byte after each.
- `pytest tests/scripts -q`: 260 passed, 1 skipped (the soak digest, not yet deposited).
  `mypy --strict src/ scripts/` and `ruff check src/ tests/ scripts/` are clean.

**Consequence.** Nothing is running this code yet. The switchover — stop PID 42044, stop the
running supervisor and its recorder, start `master.bat` — waits for the lead's commit and the
lead's word. `config/recorder.yaml` needs `recorder.pollers: [{script: funding.py}]`. That file
is the lead's, so I have requested the key.

### A-recorder — Decision: how `fees.py` gets its credentials, and four choices made with it

**Agent:** A-recorder · **Task:** P2 (operator ruling 2026-09-19) · **Date:** 2026-09-19

**Credentials. The lead's how-decision, recorded here with the options it rejected.**
- **Chose:** a small `.env` reader copied into `fees.py`. It keeps only `KRAKEN_API_KEY` and
  `KRAKEN_API_SECRET`, with the same parsing rules as `platform/config.py`'s `parse_dotenv`, plus
  a copy of `rest.py`'s signer. This is `funding.py`'s copy-not-import pattern, and it keeps the
  script standalone.
- **Rejected: importing `acsoe.platform`.** It breaks the standalone property every script in
  `scripts/recording/` keeps.
- **Rejected: Windows environment variables.** They make a second copy of the secret, and every
  process on the machine inherits it.
- **Rejected: the supervisor passing the secrets to its children.** That spreads credential
  handling into a file that has none today.

The reader deliberately ignores the process environment. The daemon's loader lets an exported
variable win, but the decision was ".env, and only these two names". A copy that also read the
environment would carry exactly the second source that was rejected.

**Four choices made with it.**

1. **The nonce is in microseconds, the same scale as `rest.py`'s `_next_nonce`, and that is
   load-bearing.** The engine daemon and this poller use one key, and Kraken requires each key's
   nonce to increase. A poller counting milliseconds would sit about 1,000 times below any nonce
   the daemon has ever sent, so every `TradeVolume` would be refused with `EAPI:Invalid nonce`
   from the first moment the daemon ran — permanently, and looking like a bad key. With both on
   microseconds they interleave, and the rare collision is one refused call that the retry
   schedule absorbs.
2. **Form-encoded body, not JSON.** The `TradeVolume` page shows a JSON body with `fee_schedule`
   as a boolean. The authentication guide's own code signs `nonce + urlencode(data)`, and says
   nothing about how a JSON body is signed. `rest.py` sends forms, and the lead's successful call
   went that way. So the request is `pair=<comma-delimited REST names>&fee_schedule=true`. Whether
   Kraken reads `"true"` as the boolean cannot be known from the page. **The poller does not
   assume it**: every line stores Kraken's reply verbatim, and the session marker states whether
   `schedules` came back. That is confirmed or refuted by the first live poll, below.
3. **Pair names.** The heartbeat's tier-1 list is in v2 spelling (`BTC/USD`). Each is matched to
   an `AssetPairs` result key (`XXBTZUSD`) through `wsname`, trying the name as-is and then with
   the futures poller's two base aliases (BTC→XBT, DOGE→XDG), on both base and quote. The REST key
   is sent because `TradeVolume` keys its `fees` map by it, so the request and the reply use one
   spelling. A pair that matches nothing is written into the poll line as `unmatched` rather than
   dropped.
4. **No credentials is a recorded absence, not a crash.** With no key, the poller still records
   `AssetPairs`, which is public, and writes a `gap` marker for `TradeVolume` on every slot with
   the reason "credentials not set". A crash would make the supervisor restart it on a five-minute
   backoff, fill the log, and record nothing. `.env` is re-read on every poll, so a rotated key is
   picked up without a restart.

**Secrets and the volume.** Nothing this script prints or writes carries the key, the secret, a
signature or a nonce. Every message on its way to stderr or into a `gap` reason goes through a
redactor that replaces the two credential values if they ever appear, as a second line of
defence: no message built here includes them. The account's 30-day `volume` and the `inputs`
block are written only into `data/raw/fees/` (gitignored, `.gitignore:10`). The poller's stderr
summary names the keys that came back and the number of pairs, never a value.


## a-data — Phase 7 specs 128, 127, 130

### Decision: the warm-up is 15 weeks, measured, not the 96-bar lookback the spec names

**Agent:** A-data · **Task:** spec 128 · **Date:** 2026-09-19

**Options.** Partition from one day (96 bars) before 2024-07-06, as spec 128 names it. Or
partition from the earliest point any engine can reach back to at the window's first bar.

**Chose.** 15 weeks. Partitions start 2024-03-23 and end 2025-01-04, 41 weekly files per pair at
most.

**Because.** 96 bars is the longest *window* in `modelling/features.py`. It is not the longest
*reach back*:
- `vol_regime_rank` ranks `realised_vol_4` over a 96-bar window, so it reads 99 bars.
- Every bar's return is taken from the previous **existing** bar's close, which has no time bound
  on a thin pair.
- Engine 3 publishes the last `market_sensor.published_bars` (200) existing candles per pair, and
  that is everything engine 5 is ever shown.

The anomaly inputs are columns of the same frame. So "200 existing bars before the window" covers
every input. Measured over the `*_15.csv` bars, it reaches back:

| Pairs | Days back |
|---|---|
| median | 4.4 |
| p90 | 17.1 |
| p99 | 65.1 |
| LSKUSD | 100.6 |
| POLUSD | 98.3 |

15 weeks is 105 days. How much of it is served is the replay's choice (a-replay, spec 129). The
partitions only guarantee it is on disk.

*Rejected:* 96 bars. On the median pair the first bar's features would already differ from the
ones the models were trained on. *Rejected:* a start per pair (smaller on disk). It makes the
manifest harder to read, and the saving is small.

**Cost.** About 58% more weeks than the window alone. The whole USD archive is 21.8 GB of source
either way, because every file has to be read end to end for its sha256.

### Decision: refuse a row the bar builder would have skipped, rather than skip it too

**Agent:** A-data · **Task:** spec 128 · **Date:** 2026-09-19

**Options.** `build_ohlcvt.py` counts a malformed row and skips it. The partitioner could mirror
that, or refuse the pair.

**Chose.** Refuse. That covers a wrong field count, a fractional timestamp, and a price or volume
`Decimal` cannot read.

**Because.** Refusing costs nothing on this archive. `PROVENANCE.json` records zero malformed,
zero out-of-order and zero late rows on all 234 pairs. And a skip is exactly the silent difference
between the models' trades and the replay's trades that spec 128 exists to rule out. The
decimal check has a regex fast path, and `Decimal` itself is the test, so a value such as `1E-8`
that the bar builder accepted is kept verbatim, not refused.

*Rejected:* mirroring the skip, with a count in the manifest. A count nobody reads is the shape
this project keeps finding.

### Decision: pyarrow's streaming CSV reader, not a Python line loop

**Agent:** A-data · **Task:** spec 128 · **Date:** 2026-09-19

**Chose.** `pyarrow.csv.open_csv` over the file, wrapped by a reader that hashes every byte it
hands pyarrow. That gives one pass for both the parse and the sha256. Prices and volumes are
read as strings, so nothing goes through a float. Rows are appended to each week's Parquet file
as they arrive.

**Because.** It is measured. On XBTUSD.csv (2.70 GB, 92,716,525 rows) it took 15.0 s end to end,
with a **peak working set of 780 MiB**. A Python loop over lines runs at about 2 M lines/s, which
is roughly 45 s for XBTUSD alone and about 12 minutes for the 21.8 GB of USD sources.

*Rejected:* seeking by binary search to the warm-up start. It would skip most of each file, but
the sha256 the manifest carries needs the whole file anyway. And ordering before the window
would then be assumed rather than checked.

**Checked on XBTUSD (scratch output):**
- 9,749,093 rows inside the partition span;
- equal to the sum of the `trades` column of `XBTUSD_15.csv` over the same bars;
- the summed volume, as `Decimal`, equal to the bars' summed volume: 636400.49692795 both ways.

### A-recorder — P2 built: `fees.py`, and the one question the docs could not answer, answered live

**Agent:** A-recorder · **Task:** P2 (operator ruling 2026-09-19) · **Date:** 2026-09-19

**Fix.** `scripts/recording/fees.py` follows the decision entry above ("how `fees.py` gets its
credentials").
- **Each slot, on the hour:** public `AssetPairs` verbatim, then signed `TradeVolume` verbatim
  with `pair=<tier-1 REST keys>&fee_schedule=true`.
- **Where it writes:** into `data/raw/fees/fees__<source>__<date>.jsonl`, using the funding
  poller's seven-key schema.
- **When a call fails:** after `funding.py`'s retry schedule, a `gap` marker naming the call
  and the slot.
- **Locking:** a `.fees.lock` OS lock, and exit 2 when it is held, which the supervisor
  answers by waiting.
- **Optional config keys:** `recorder.fees_dir` and `recorder.fees_interval_s`, with the same
  defaults as funding.

**The live check, for the question the docs could not settle.** Whether Kraken honours
`fee_schedule` in a form-encoded body could not be read off its pages. One `--once` poll ran
against the real endpoints, into the session scratchpad and not the archive. Only key names were
read, and the output file was deleted afterwards because it held the account's volume. The
result:
- all 10 tier-1 pairs mapped to REST keys, none unmatched;
- `result` carried `asset_class`, `currency`, `fees`, `fees_maker`, `inputs`, `schedules` and
  `volume`;
- `fees` came back per pair for all 10, with rows `fee`, `minfee`, `maxfee`, `nextfee`,
  `tiervolume` and `nextvolume`;
- **`schedules` came back**: 10 entries of `pair`, `class`, `tiers[maker_fee, taker_fee,
  active]`.

So the form encoding works, `schedules_returned` is true, and the session marker will say so on
every start.

**Verification.**
- `tests/scripts/test_fees.py`: 21 tests, all with a stub transport and a made-up key pair.
  - The signer equals the package's `sign_request` on the same inputs; this is the anti-drift
    test for the copy.
  - Only the two names are read, and the environment is ignored.
  - The nonce counts microseconds and never repeats.
  - Redaction works.
  - v2→REST mapping works through the aliases.
  - Both answers are recorded verbatim, with the signed request checked.
  - Nothing written or printed carries the key, the secret, the signature, the nonce, or the
    volume outside the archive.
  - No credentials means AssetPairs is still recorded, a gap is written, and no private call is
    made.
  - Retries end in a gap with a redacted reason, and a retry uses a fresh nonce.
  - An AssetPairs outage keeps the last name map; with no map ever, the fee is a gap.
  - Covered end to end: `--once`, and exit 2 on a held lock.
- Mutation sweep, 12 of 12 killed:
  - nonce in milliseconds;
  - environment wins over `.env`;
  - redaction disabled;
  - no `pair` sent;
  - failed call leaves no gap;
  - private call with no credentials;
  - name map dropped on an outage;
  - summary carries the volume;
  - signer drift;
  - nonce may repeat;
  - gap reason not redacted;
  - aliases not tried.

  Each anchor was asserted to occur exactly once, and the file was restored in a `finally` with
  its sha256 re-checked after every arm.
- `pytest tests/scripts`: 297 passed, 1 skipped. `mypy --strict src/ scripts/` is clean. `ruff`
  is clean on `scripts/` and `tests/scripts/`. The 18 ruff findings elsewhere are all in files
  other agents have in progress (`research/trial_ledger.py`, `tests/modelling/test_promotion.py`,
  `tests/research/test_trial_ledger.py`).

**P3's extension inside this boundary** is one line in the lead's `config/recorder.yaml`:
`- script: fees.py` under `recorder.pollers`. Once the P3 switchover is done, the running
supervisor picks it up within 30 s, with no restart. The supervisor's parser was run on the
committed config and accepts it, and it resolves both `funding.py` and `fees.py` beside itself.


## a-replay: spec 129, the replay client

### Decision: rules are served from the v2 instrument snapshot, not through the live REST parser

**Agent:** A-replay · **Task:** spec 129 · **Date:** 2026-09-19

**Options.** (a) Serve pair rules through `map_asset_pairs`, the live REST parser, as spec 129
step 4 words it. (b) Read the v2 `instrument` snapshot recorded beside `AssetPairs` (spec 127)
with its own small reader, and use REST only for the archive-name mapping (`altname`, e.g.
`XBTUSD`, to `wsname`, e.g. `XBT/USD`, then v2 `BTC/USD` through the XBT and XDG aliases).

**Chose (b).** The recorder gap audit showed that (a) keys rules by `XXBTZUSD` with quote
`ZUSD`, so engine 7 would exclude every pair as `pair_rules_missing` or `no_live_quote`. The
two forms agree exactly on every rule value for all 1,419 comparable pairs, so (b) changes
keying and no value. **Rejected (a)** because it can only be made to work by re-keying its
output and rewriting base and quote, which amounts to (b) with extra steps. **Contestable:** the
spec's words "the same parser as live" are not met, and the live parser's keying defect is still
open (it goes to the lead, outside Phase 7).

### Decision: the trade window is bar-aligned and published_bars long, not live's count window

**Options.** (a) Live's shape: the last 200,000 trades by count (`ws.py`). (b) A time window,
`[bar_open(now) - published_bars x bar, now]`.

**Chose (b).** The features need 100 bars behind the decision bar (96-bar windows; `_r` reads the
previous close; `vol_regime_rank` ranks `realised_vol_4` across 96 bars). Engine 3 publishes 200.
At about 130 pairs, 200,000 trades is under a day, so under (a) the 96-bar features would go
unfilled and the replay would stop matching the offline measurement spec 144 requires it to
match. The window is bar-aligned so the oldest published candle is never partial. **Rejected
(a)** for that mismatch. **Flagged to the lead:** live's count window may under-fill the 96-bar
features in exactly this way.

### Decision: the declared quote is stamped `now`

**Options.** (a) Stamp the quote with the last trade's time. (b) Stamp it `now`.

**Chose (b).** The book is declared at `now`; it is not an observation made at the last trade.
Under (a), engine 4 would find some quiet pair among roughly 130 whose last trade is more than
120 s old on nearly every bar, and it blocks the whole tick on any stale pair. That block would
come from history, not from a feed fault, and the offline funnel the run must match applied no
such block. **Rejected (a)** for that reason. **Contestable, told to the lead:** under (b),
`data_guard`'s staleness check is inert in replay.

### Decision: the declared book is not rounded to the pair's tick

**Options.** (a) Round the bid down and the ask up to `tick_size`. (b) Serve the declared spread
exactly.

**Chose (b).** The ruling applies the table's value uniformly. Rounding would widen the spread past
the declared value on coarse-tick pairs, so the cost gate would see a number the table does not
hold. **Rejected (a)** on that ground. Case against (b): a real book sits on the tick grid.

### Found: rounding to nearest made engine 9 walk a level the declared book never reaches

**What happened.** The hand-check of engine 9's walk on the thin bucket expected 5 levels
consumed for a $5,000 balance (ten levels of $1,000 each) and got 6.

**Why.** Each level's quantity is `1000 / price`, which does not terminate. Rounded to nearest at
28 digits, some levels hold a part in 1e28 less than $1,000. The walk then finds the fifth level
short of the last fraction of a cent and takes a speck of the sixth. The fill price moves only in
the 26th digit, but `levels_consumed` reports a level the book was never meant to reach. A walk of
the full $10,000 would also read as too thin.

**Fix.** The quantity is rounded up in its last digit (`_covering_qty`), so no level falls short
of its share. That adds at most one unit in the 28th digit.

### A-recorder — Decision: P1, the `instrument` channel kept subscribed on the tier-1 socket

**Agent:** A-recorder · **Task:** P1 (operator ruling 2026-09-19: the subscription, not the
start-marker form) · **Date:** 2026-09-19

**Options for where the subscription lives.**
1. Add `"instrument"` to `TIER1_CHANNELS`.
2. A separate, symbol-less subscription that the tier-1 `Stream` sends first on every connect.

**Chose 2.**

**Because.** `TIER1_CHANNELS` feeds `subscriptions()`, which chunks by symbol. It also feeds
`drop_to()`, the disk guard's degrade, which sends an `unsubscribe` per channel for the dropped
symbols. `instrument` takes no symbol. Under option 1 the degrade would send
`unsubscribe instrument` with a symbol list, and what Kraken does with that is not documented. At
best it is refused; at worst the rules stop being recorded at the one moment the recorder is
already in trouble. As a separate subscription it is never in the degrade's path, is never
unsubscribed, and is re-sent on every reconnect.

**It is sent first.** After every connect the archive then holds the rules before any market data
priced against them, so a replay reading forward always has them in hand.

**What this costs, checked before building it.**
- About 0.6 MB per snapshot, once per connect (three process starts in eight days, plus
  reconnects), and small `update` frames on a listing or status change.
- **The line is larger than the 256 KiB edge windows** that `archive_merge.py`,
  `manager/archive.py`, `manager/staging.py` and `supervise.py` read for a file's first or last
  line.
  - The first line of a day's file is never the snapshot. A start writes its `session` marker
    before connecting, and a file begun at midnight begins with whatever frame arrived then.
  - The last line would be the snapshot only if the process died within moments of connecting.
    Every one of those readers already steps back over a line it cannot parse. So the worst case
    is "last-line time unknown" for that one file, never a wrong time.
- `instrument` frames carry no `symbol` and no `timestamp`, so `extract_pair` and
  `extract_ts_exchange` give them `pair: null` and `ts_exchange: null`. No consumer mistakes them
  for market data: `build_archive.py`, `ohlc_fixture.py`, `cut_book_fixture.py` and
  `reconcile_spread.py` all filter on `channel`.
- a-replay's `clients/kraken/replay_scenario.py` already reads a v2 instrument snapshot "wherever
  the capture nests it". A recorded line nests it at `payload.data.pairs`.
- Numbers are re-serialised by `orjson`, like every other frame in this archive, so `qty_min`
  can appear as `5e-05`. `Decimal(str(x))` of the shortest repr round-trips the decimal Kraken
  sent. The replay scenario already reads these fields as JSON numbers.


### Spec 128: the real run, the sweep, and one check removed because it could not fail

**Agent:** A-data · **Task:** spec 128 · **Date:** 2026-09-19

**The run.** `scripts/partition_trades.py --write --workers 2` wrote
`data/derived/trades_weekly/`: 234 pairs, 41 weeks each (2024-03-23 to 2025-01-04), 1.5 GB.
Log: `logs/a-data-partition-20260919.log`. The whole run took under 5 minutes, and the
partitioning itself 290 s of worker time.

- 112,552,742 rows inside the span.
- For **every** pair, three counts agree: the stream's count, the written files' Parquet
  metadata, and the `trades` column of the pair's own `_15.csv` bars.
- 0 out-of-order rows.
- 105 pair-weeks are empty; each has no file and is listed in `empty_weeks`.
- Manifest sha256 `cb7897c276695c7274f11bbd9496b7745683fecc22f3bd5ea15e5829f866d175`.
  It records the script's sha256, `c2d7a841432d1a31…`, equal to the committed script.

**Peak memory, measured.**
- XBTUSD.csv alone (2.70 GB, 92,716,525 rows): **780 MiB** peak working set, 15.0 s.
- In the full run, a worker's peak never passed 815 MiB. That figure is the Win32 peak over
  the worker's whole life, across every pair it handled, so it bounds each pair from above.
- `test_peak_memory_does_not_grow_with_file_size` runs a 1.5 M-row and a 6 M-row synthetic
  file in fresh subprocesses (about 130 MB apart). It asserts the peaks differ by less than a
  quarter of the size difference, and it went red when the stream was swapped for an eager
  `read_csv` (M14 below).

**Mutation sweep** (`scripts/partition_trades.py`, `tests/scripts/test_partition_trades.py`).
- Harness: each mutation applied from a byte copy, with `PYTHONDONTWRITEBYTECODE=1`, restored
  and hash-verified before the next.
- **17 applied, 15 killed, 2 survived. Both survivors are equivalent, so they are checked
  negatives.**
- Each killed arm, with its pytest summary line and the test that killed it:

| Arm | Mutation | Summary | Killed by |
|---|---|---|---|
| M1 | reconcile never compares | `1 failed, 15 passed` | the planted miscount |
| M2 | bars cross-check off | `1 failed, 15 passed` | `test_the_models_bars_must_agree` |
| M3 | closed-week check off | `1 failed` | the after-its-week test |
| M4 | window start exclusive | `7 failed` | |
| M5 | window end inclusive | `7 failed` | |
| M6 | decimal check skipped | `2 failed` | |
| M7 | `Decimal` fallback removed, which would refuse `1E-8` | `7 failed` | |
| M8 | non-finite accepted | `1 failed` | the `NaN` volume |
| M10 | overwrite allowed | `1 failed` | |
| M11 | week grid shifted a day | `9 failed` | |
| M12 | out-of-order counter zeroed | `1 failed` | |
| M13 | rename before reconcile | `3 failed` | |
| M14 | eager whole-file read | `1 failed, 15 passed` | the memory test |
| M15 | provenance resolution check off | `1 failed` | |
| M16 | rows re-sorted, not file order | `2 failed` | |

- **Checked negatives:**
  - **M9**, draining the hash to EOF removed: `16 passed`. pyarrow reads to end of file on
    every successful parse, and every unsuccessful parse refuses the pair. So the drain is
    defensive and no input can tell it apart. Kept, and recorded as equivalent.
  - **M17**, the "rows before + inside + after = source rows" check disabled: `16 passed`.
    It is a tautology: the three masks partition every row by construction, so the check
    could never fire. **Removed** rather than kept as decoration. The partitions were then
    re-run with the final script, so the manifest's `script_sha256` is the committed file's.

### A-recorder — P1 built: the tier-1 socket keeps `instrument`, proved live

**Agent:** A-recorder · **Task:** P1 · **Date:** 2026-09-19

**Fix.**
- `scripts/record.py` gains `INSTRUMENT_CHANNEL` and `instrument_subscription()`, and `Stream`
  gains `instrument: bool` and `all_subscriptions()`.
- `_session` sends `all_subscriptions()` on every connect, with `instrument` first.
- `write_marker` lists it too, so every `session` marker says the rules were subscribed.
- `drop_to` is unchanged, and that is the point: it rebuilds only the symbol subscriptions.
- `_record` passes `instrument=True` to tier 1 only.
- The module docstring gains "The pair rules are recorded too".

The diff is 47 lines added and 2 changed. The file was CRLF in the working tree. It was
normalised to LF first, and `git diff` was empty after that step, so the diff shows only the
change.

**Proved live.** `record.py` ran for 25 s against Kraken into the session scratchpad: its own
lock, not the archive's, tier 1 of two pairs, tier 2 empty. The start marker's
`subscriptions[0]` was `{"channel": "instrument"}`. One `instrument` snapshot arrived on the same
socket as book, ticker and trade: 1,450 pairs and 842 assets in a single 554,902-byte line, with
`pair: null` and `ts_exchange: null`. The scratch output was deleted.

**Verification.**
- `tests/platform/test_record_instrument.py`: 4 tests, driving the real `Stream` and the real
  `_record` through a scripted fake socket put where `record.py` looks up `connect`. The network
  guard refuses loopback too, so a local server was not an option. The tests prove:
  - `instrument` is first on every connect;
  - a reconnect re-records the snapshot, and an `update` frame is recorded;
  - the frames are verbatim;
  - the disk guard's degrade never unsubscribes it and a later reconnect still sends it;
  - a stream without the flag never asks for it;
  - `_record` gives it to tier 1 and not tier 2.
- Mutation sweep, 7 of 7 killed:
  - instrument never sent;
  - instrument sent last;
  - connect sends only the market subscriptions;
  - tier 1 not given the flag;
  - the degrade unsubscribes instrument;
  - the session marker omits it;
  - every stream asks for it.
  Each anchor was asserted to occur exactly once, and the file was restored in a `finally` with
  its sha256 checked.
- `pytest tests/platform tests/scripts`: 640 passed, 2 skipped. `mypy --strict src/ scripts/` is
  clean. `ruff` is clean on `scripts/`, `tests/scripts/` and `tests/platform/`.

**Consequence.** It is not running yet. The recorder on this machine is the 2026-09-16 process.
P1 takes effect at the one switchover, with the new supervisor.

### Decision (CONTESTABLE): a second one-shot public fetch, the v2 `instrument` snapshot, beside `AssetPairs`

**Agent:** A-data · **Task:** spec 127 · **Date:** 2026-09-19

**Options.**
1. Record REST `AssetPairs` only, as spec 127's scope line says ("no other public or private
   endpoint"). The replay then maps REST names to the engines' v2 symbols with a hand-written
   alias table: XBT to BTC, XDG to DOGE.
2. Also capture the public WebSocket v2 `instrument` snapshot once, verbatim, with the same
   provenance block. Derive the alias from Kraken's two answers, and check every REST rule
   against the v2 one.

**Chose.** Option 2, on the lead's instruction. It is recorded here as a how-decision and
**flagged CONTESTABLE**: it is a second fetch the spec's scope line forbids.

**Because.**
- The engines key by the v2 symbol (`BTC/USD`). REST keys by `XXBTZUSD`, and its `wsname`
  says `XBT/USD`, which is neither. The earlier recorder audit (above) found that rules served
  REST-keyed make engine 7 exclude every pair.
- A hand-written alias table is exactly the kind of invented value the Phase 0 `AssetPairs`
  was: nothing on disk would say whether it is complete.
- With the snapshot, the alias is **derived**. The script keeps an asset rename only where a
  v2 symbol no `wsname` names shares one side of the pair and every rule, and every such vote
  for that asset agrees. The join is then checked to be one to one, with ordermin, costmin,
  tick size, both decimals and status equal on every pair.
- On the audit's scratch copies this derives exactly {XBT: BTC, XDG: DOGE}, and joins all
  1,450 REST pairs to 1,450 v2 symbols with zero rule mismatches.

**The live-parser defect is not touched.** `map_asset_pairs` keying rules by REST name is a
live defect, and it goes to the operator as a FINDING via the lead. Changing it would change
live behaviour.

*Rejected:* option 1. The case for it: the spec says one endpoint, and the alias table is two
lines that anyone can read. The case against it, which decided it: two lines nobody can check
are the same shape as the invented fixture spec 127 exists to replace.

**The transport.** The REST call goes through `KrakenRestClient.asset_pairs()` with
`credentials=None`, wrapped by a `RecordingTransport` that keeps the body as received. That
means one HTTP stack, and a body the live parser rejects is never written. The WebSocket
capture uses `websockets.asyncio.client.connect` on `ws.py`'s own `KRAKEN_WS_V2_URL`: a
subscribe, the first snapshot frame, an unsubscribe. The streaming client has no instrument
path, and adding one would be a change to live code for a one-shot.

### A-recorder — P1 addendum: an `instrument` line against the schema and the continuity report

**Agent:** A-recorder · **Task:** P1 · **Date:** 2026-09-19

The lead asked for this explicitly, so it is recorded beside the P1 entry rather than assumed from
it.

**Schema.** An `instrument` frame built through `record.py`'s own `extract_*` and `build_line`
passes `validate_line`. Its key set equals `clients/recorder/contracts.py`'s `LINE_KEYS`: channel
`"instrument"`, pair null, ts_exchange null.

**`recording_report.py` / `clients/recorder/report.py`.** Neither reads `channel` or `pair`. The
report finds `kind` and `ts_recv` by their first occurrence in the raw bytes, and both precede
`payload` in every line the recorder writes. The check was made adversarial on purpose: a 0.7 MB
synthetic snapshot whose nested pairs each carried `"kind":"gap"` and a 1999 `ts_recv` was
reported as one ordinary tick. The span came from the lines' own times, with no gap and
`recorded_fraction` 1.0. The other readers are covered in the P1 decision entry: the ones that
filter on `channel`, and the 256 KiB edge readers.

### A-recorder — Known limit (P2): one API key, two nonce counters

**Agent:** A-recorder · **Task:** P2 · **Date:** 2026-09-19

This corrects the P2 decision entry, which called a nonce collision "the rare collision … one
refused call that the retry schedule absorbs". That is too kind. `fees.py` and the engine daemon
sign with one key, and Kraken requires each key's nonce to increase. Both count microseconds on
their own clocks. Two processes interleave out of order whenever one signs a request after the
other but reaches Kraken first, and Kraken then refuses the later-arriving one with
`EAPI:Invalid nonce`.
- For `fees.py` that costs a retry, and if every retry collides, a `gap` for the slot.
- For the daemon it is a failed `TradeVolume` or `Balance` fetch on that tick, which blocks.

**Nothing collides today: the daemon is not running.** Per the lead's instruction this is
**recorded as a known limit, not engineered around**. A shared nonce file or a lock across the two
processes would couple a standalone script to the daemon for a problem with a cleaner fix. The fix
is the operator's: a dedicated Query Funds key for `fees.py`. Kraken counts nonces per key, so
separate keys cannot collide. The swap is a change to `.env` and no change to code.


### Spec 127: the recording, the survivorship count, and the tick caveat

**Agent:** A-data · **Task:** spec 127 · **Date:** 2026-09-19

**Recorded once each, 2026-09-19.** Both fixtures are in `tests/fixtures/kraken/`:

| File | Captured | Payload | sha256 |
|---|---|---|---|
| `asset_pairs_recorded_2026-09-19.json` (`GET https://api.kraken.com/0/public/AssetPairs`) | 04:19:59.496708Z | 673,637 bytes | `7a5edf9a90b10ed0658943257763a8a77872abeb31796c8257729fd30168cfcd` |
| `instrument_recorded_2026-09-19.json` (`wss://ws.kraken.com/v2`, the first `instrument` snapshot frame) | 04:20:02.181402Z | 571,867 bytes | `227cf11cb91ba9e1560e0ae55a9c66a261d4511f680ce2f11dd76330a2d886ef` |

`pair_names_recorded_2026-09-19.json` is **derived** from those two, offline, and says so.

**Checks** (`python scripts/record_asset_pairs.py --report 2026-09-19`).
- All 1,450 REST pairs parse through `map_asset_pairs`. None is dropped, and every one has
  `ordermin`, `costmin` and `tick_size`.
- The derived asset map is exactly {XBT: BTC, XDG: DOGE}.
- All 1,450 REST pairs join one to one to the snapshot's 1,450 v2 symbols. **Zero
  disagreements** on ordermin, costmin, tick size, pair and lot decimals, and status.

**Survivorship, measured. This fills `phase-7-findings.md` §7's NOT MEASURED slot.** These are
archive USD pairs (`data/historical/*USD_15.csv`) with a bar inside the window whose `altname`
no `AssetPairs` entry carries. Engine 7 will exclude each one as `pair_rules_missing`.

- **Phase 7 window (folds 379–404, 2024-07-06 to 2025-01-04): 39 of 231.** They are AGLDUSD,
  AIRUSD, BITUSD, BONDUSD, BSXUSD, CSMUSD, EOSUSD, ETHWUSD, FARMUSD, FTMUSD, GALUSD, GARIUSD,
  ICXUSD, INTRUSD, KARUSD, KILTUSD, KINTUSD, LUNA2USD, MATICUSD, MCUSD, MKRUSD, MOONUSD, MVUSD,
  MXCUSD, NODLUSD, NYMUSD, OXYUSD, PSTAKEUSD, REPUSD, REPV2USD, ROOKUSD, SDNUSD, STEPUSD,
  TEERUSD, TOKEUSD, TUSDUSD, TVKUSD, USTUSD, XRTUSD.
- **1.5-year window (folds 326–404, 2023-07-01 to 2025-01-04), labelled: 42 of 234.** The same
  39, plus ANTUSD, RNDRUSD and WAVESUSD.

**Two things the count does not say, and neither is decided here.**
1. **Some are likely rebrands, not delistings.** MATIC (now POL, and POLUSD is itself an
   archive pair), FTM, RNDR and MKR, for example. The count is by name. Mapping a renamed pair
   to its successor's rules would change which pairs the replay can trade, so it is a
   **ruling**, flagged to the lead. It was not done.
2. **13 window pairs are present but `cancel_only` today:** ACAUSD, BNCUSD, CQTUSD, HDXUSD,
   JUNOUSD, KEYUSD, KINUSD, KP3RUSD, MIRUSD, MNGOUSD, MULTIUSD, RBCUSD, SBRUSD. `PairRule` has no
   status field, so engine 7 admits them, live and in replay. HDXUSD is one of the §3 thin-pair
   names. The recorder audit's gap 1 describes the same thing live. **Flagged, not changed.**

**The tick-size caveat.** All 15 pairs `q_ticks.out` found on a finer grid in 2026 have a
recorded `pair_decimals` equal to their 2026 grid, and finer than their 2023–24 grid. So the
recorded rules describe 2026 and not the window. On those 15 the replay's price rounding is
finer than the historical ticks: ASTR, AVAX, BLUR, COTI, CRV, CVC, CVX, DYDX, LMWR, MINA, NEAR,
SHIB, SUSHI, UNI and XTZ against USD.

**A flaw in my own provenance, left in place and named.** The instrument fixture's
`client_version` block carries the sha256 of `clients/kraken/rest.py`. That file did not make
the WebSocket call. The `acsoe` version in the block is right, and the capture code is
`scripts/record_asset_pairs.py` at the commit that adds it. A recording is written once, so
the file is not rewritten to correct it.

**Mutation sweep** (`scripts/record_asset_pairs.py`, `tests/scripts/test_record_asset_pairs.py`).
**18 applied, 17 killed, 1 checked negative.**
- The first pass left **four survivors**:
  - N3: the capture bypassing `asset_pairs()` and calling `_public`. It survived because the
    only rejection test used an error envelope, which `_public` also refuses. A test now uses a
    clean envelope that the live mapping rejects.
  - N4: a non-snapshot `instrument` frame accepted. It survived because no scripted frame was an
    instrument update. One now is.
  - N16: the name map written despite disagreeing recordings. There was no test of the refusal;
    there is now.
  - N18: the one-request check disabled.
- Re-run after the new tests: N3, N4 and N16 killed (`1 failed, 20 passed` each).
- **N18 is equivalent**: `KrakenRestClient.asset_pairs()` makes exactly one request, so the
  guard cannot fire without changing the client. It is kept as a check on a client change, and
  recorded as a checked negative.
- The other 14 were killed on the first pass, each with a pytest summary line: N1, N2, N5 to N15,
  and N17.
- Suite: `21 passed`.


## a-replay: spec 131, engine 23 drives the registered chain

### Decision: the driver is split into pure scheduling in `research/` and wiring in `cli/`

**Agent:** A-replay · **Task:** spec 131 · **Date:** 2026-09-19

**Options.** (a) Put the whole driver in `research/backtest.py`. (b) Keep the schedule, the fold
switching and the restart logic there (`ChainReplay`, written against callables), and do the
wiring in `cli/research.py`: `bootstrap.py`, the orchestrator, the store, the paper broker and
the replay client.

**Chose (b).** Architecture invariant 5 keeps the live loop's modules out of `research/`, and
`cli/research.py` is the one module licensed to import both sides. **Rejected (a):** it would
have had to import `bootstrap.py` and `clients/` from `research/`. Stepping needed no `core/`
change: `Orchestrator.tick()` plus `FixedClock.set()` is enough. The per-fold config goes
through `platform.config.ConfigView`. The orchestrator holds the view, and at each fold boundary
the driver points it at a freshly built, validated `Config` (`derive_config`). No loaded config
is ever mutated, and the view refuses a change of mode.

### Found: the orchestrator's minted `run_id` would repeat across a resume

**What happened.** The first kill-and-resume run lost rows after the resume point.

**Why.** The orchestrator mints its `run_id` from the clock at construction, and the replay
clock starts every process of a run at the window's start. The resumed process therefore took
the killed process's `run_id`, restarted `cycle_id` at 1, and hit engine 19's once-per-tick
uniqueness on `(run_id, cycle_id)`. Engine 19 raised, contract rule 7 turned that into ERROR, and
the ticks' rows were lost. The bootstrap docstring records the same collision.

**Fix.** The driver names each process's run itself: `replay-<start instant>`, and
`replay-<resume instant>-resumed` for a resume. It passes the name to the orchestrator.

### Decision: a resume seeds `previous_now` (the lead's `core/` keyword, decision D9)

Asked of the lead and added by the lead the same morning. Without it, a resumed process's first
tick has no trade range. A stop touched and recovered inside that minute is then missed, and the
resumed rows differ. `test_a_run_killed_with_a_position_open_resumes_to_the_same_exit` plants a
position, prints one trade through the stop and back inside the minute after the kill, and
requires the resumed exit to match the uninterrupted one. The rejected options were to accept
the difference, or to re-run the last tick (which decides it twice).

### Observed, not a defect: the first bar of a fresh run cannot size

On a fresh database, engine 7 blocks the first bar with `scout_inputs_unavailable` ("no
equity_snapshots row yet"). Engine 19 writes the first equity row at the end of that same tick.
A live daemon on a new database does the same, so the replay reproduces it rather than working
around it. The cost is one decision bar per run.

### Spec 130: the bucket table reproduces the findings except for one IQR bound, and why

**Agent:** A-data · **Task:** spec 130 · **Date:** 2026-09-19

**What happened.** `scripts/build_bucket_table.py` re-derives the table in `phase-7-findings.md`
§3 from `data/summaries/`, over the same span (up to 2026-09-19 00:45Z). It uses the same
definitions as `q_spread_agg.py`, `q_depth.py` and `q_bucket.py`, and polars' own quantiles.

- **Equal:** all four pair counts (16, 49, 84, 36), all four spread medians (30.4, 25.8, 12.3,
  5.5), seven of the eight IQR bounds, and all four slippage-at-$5k figures (17.7, 20.8, 7.5,
  1.7).
- **Different:** one figure, the **$100k–1M bucket's upper spread quartile: 19.6 against the
  published 19.4.**

**Why, as far as the disk can say.** Nothing on disk records which rows `q_depth.py` read.
- It had no time cut-off. It read the live, growing summary file at a moment nobody recorded,
  and the per-pair output it wrote (`per_pair_spread_depth.parquet`) was never committed.
- `q_spread_agg.py`, which set the bucket volumes, stopped at 00:45.
- I held the volumes at 00:45 and moved the spread and depth cut-off from −60 to +240 minutes.
  No single cut-off reproduces every published figure. At −60 to −5 minutes the $10k–100k
  median moves to 25.6 or 25.7. From 0 to +15 the only difference is this 19.6. At +30 it is
  19.5, and past +60 other figures move.
- So the published table came from a row set that no cut-off of this script reproduces
  exactly. The most likely cause is that the recon's two scripts read the recording at two
  different moments. That is **not proven**; the evidence that would prove it was not kept.

**Consequence.**
- The **declared values the replay reads are the medians**, and every median reproduces.
- The disagreement is one bound of one bucket's *declared uncertainty*, by 0.2 bps.
- The fixture records `"reproduction": {"all_equal": false, ...}` with the bucket named, so it
  does not claim more than it shows.
- The fixture's span is fixed by `--until`, and each summary file's bytes read are hashed, so
  **this** table can be reproduced exactly, which the recon's could not.

### Decision: the fee schedule's pair classes, mapped by the page's own rule, three stopped

**Agent:** A-data · **Task:** spec 130 · **Date:** 2026-09-19

**The rule**, verbatim from the committed page: "This fee schedule applies to FX pairs
(EUR/USD), stablecoins in the base currency (USDT/USD, DAI/USDT, etc.) and pegged tokens
(TBTC/BTC, WBTC/BTC, etc.). If the stablecoin is the quote currency only (BTC/DAI), the fee
schedule in the "Spot Crypto" tab applies."

**Mapped** (in `kraken_fee_schedule_2026-09-19.pair_classes.json`, not in code):
- **stablecoin/pegged/FX:** EURUSD, GBPUSD, AUDUSD, USDTUSD, DAIUSD, USDCUSD, PYUSDUSD.
- **Spot Crypto:** every other archive USD pair.

**Stopped** (RULING REQUIRED; `table: null` in the companion):
- **TBTCUSD and WBTCUSD.** The page's examples pair a pegged token with its peg (TBTC/BTC). It
  does not say whether the same token against USD is in the class.
- **PAXGUSD.** The page does not say whether a gold-backed token is a "pegged token" in its
  sense.

**Moot:** TUSDUSD and USTUSD are absent from the recorded `AssetPairs`, so the replay can never
trade them.

**Found while mapping, and bigger than the fee.** **XBTPYUSD and ETHPYUSD are not USD pairs.**
The recorded name map resolves them to **BTC/PYUSD** and **ETH/PYUSD**: quoted in PayPal's
stablecoin. `build_ohlcvt.py` selects pairs by the file name ending in `USD`, which `PYUSD`
also does. So both are in the models' "USD" universe, priced in PYUSD. For the fee, the page is
explicit (the stablecoin is the quote only, so Spot Crypto). For the universe and the reporting
currency this is a FINDING for the lead, not something to fix here.

**Also not mapped, and stopped:** which *row* of the stablecoin table corresponds to spot tiers
3 and 5. That table is keyed on 30-day volume alone. Spot tiers are reachable by volume or by
assets on platform, and the page says stablecoin and FX volume does not count towards the 30-day
volume. The options, the recommendation and the case against are in the progress file.

*Rejected:* the Spot Crypto table for every pair, which is `phase-7-findings.md` §7's stated
fallback. The spec asks for the other class to be mapped by the page's rule, and the rule is
clear for seven pairs.

### Spec 130: the fixtures written, and the sweep

**Agent:** A-data · **Task:** spec 130 · **Date:** 2026-09-19

**Written.**
- `tests/fixtures/replay/spread_book_table_2026-09-19.json`, by `scripts/build_bucket_table.py
  --write`. Span 2026-09-11T16:13Z to 2026-09-19T00:45Z (7.3556 days), 185 recorded USD pairs,
  and each summary file's bytes read with their sha256.
  - Declared depth to $10,000 from the mid (median, with IQR):
    - <$10k: 86.2 (39.4–141.9, 11 of 16 pairs ever reached it)
    - $10k–100k: 100.5 (45.3–176.4, 43 of 49)
    - $100k–1M: 35.2 (21.6–62.6, 83 of 84)
    - $1M–10M: 8.9 (5.3–15.9, 36 of 36)
  - `reproduction.all_equal` is false, for the one bound explained above.
  - The <$10k median depth is below the $10k–100k one. That is what the recording says; this
    table declares it and does not smooth it.
- `tests/fixtures/replay/kraken_fee_schedule_2026-09-19.pair_classes.json`, hand-authored from
  the page's rule, covering all 234 archive pairs: 7 in the stablecoin/pegged/FX table, 222 in
  Spot Crypto, 3 RULING REQUIRED, 2 absent from the rules.

**Mutation sweep** (`scripts/build_bucket_table.py`, `tests/scripts/test_build_bucket_table.py`).
**19 applied to code and fixture, 19 killed after one test fix.**
- The first pass ran 16 arms with the no-double tests deselected, since every script mutation
  changes the sha256 they check. 15 were killed, each with a `1 failed, 6 passed, 2 deselected`
  or wider summary line:
  - B1–B3: the clean, version and samples filters;
  - B4: depth over unreached minutes;
  - B5: volume from usable rows only;
  - B6: the bucket edge made exclusive;
  - B7: the span's end ignored;
  - B8: a half-written line read;
  - B9: the USD filter;
  - B10–B11: the top-bucket mapping;
  - B12: the reproduction check forced true;
  - B13: the day count;
  - B14: p25 read for p50;
  - B16: the never-reaching list emptied.
- **B15, the `kind` filter dropped, survived.** The planted gap row carried no spread, so
  admitting it changed nothing. It now carries one, and B15 is killed (`1 failed, 1 passed`).
- Two arms re-run with the no-double rebuild test selected, to show the committed table is a
  real check rather than a copy of itself. B14 (p25 for p50) and B4 (depth over every minute)
  both turn `test_the_committed_table_rebuilds_from_the_recording` red.
- Three arms on a byte copy of the fee-class companion, restored and hash-verified: a
  quote-only pair put in the stablecoin table, the rule quote altered, and an unknown table
  name. Each gives `1 failed`.

### Spec 130 and 127: the lead's rulings applied (a correction to the entries above)

**Agent:** A-data · **Date:** 2026-09-19

**The fee-class companion is a reporting list (lead decision D8).** The replay serves the Spot
Crypto tier to every pair, because `FeeTierSnapshot` is account-level. The companion was
regenerated before any commit. Its `_provenance.use` now says it is for reporting only, and no
client reads it to price anything. TBTCUSD, WBTCUSD and PAXGUSD are `table: null`, with status
"AMBIGUOUS: Spot Crypto served (D8)", and are no longer stops. So S-pegged and S-fee-rows above
are **moot**, not open.

**Spec 127 stops, ruled by the lead from spec 129 step 4.**
- S-renames: the pairs stay excluded. **39 is an upper bound on delistings.** The probable
  rebrands among them are MATICUSD (POL), FTMUSD, RNDRUSD (in the 1.5-year count) and MKRUSD.
  The lead carries this to findings §7.
- S-cancel-only: left as is for the replay. "Engine 7 ignores pair status, live too" is logged
  by the lead as live finding F3.

**PYUSD quote confirmed from the recordings.** In the v2 snapshot, BTC/PYUSD has base BTC and
quote PYUSD, and ETH/PYUSD has base ETH and quote PYUSD. In REST, XBTPYUSD's `wsname` is
XBT/PYUSD with quote PYUSD, and ETHPYUSD's is ETH/PYUSD. So the name map gives both pairs quote
**PYUSD, not USD**. Engine 7 excludes them for want of a PYUSD balance (invariant 7), as it
would live.


### Specs 129 and 131: the mutation sweep

**Agent:** A-replay · **Task:** specs 129, 131 · **Date:** 2026-09-19

The harness copied each file's bytes, applied the mutation (its anchor asserted to occur exactly
once), ran pytest with `PYTHONDONTWRITEBYTECODE=1`, wrote the bytes back and checked the hash,
all before the next arm. Every verdict below has a pytest summary line. Arms run with `-x` report
the first test that killed them. The three follow-up arms ran without `-x`.

**38 distinct arms: 37 killed, 1 checked negative (M29), 0 survivors.** M21 and M35 were each run twice (M35 after its test was added), which makes 40 runs in all.

| Arm | File | Mutation | Summary | Killed by |
|---|---|---|---|---|
| M1 | replay.py | `from_config`'s mode check off | `1 failed` | paper refused before any fixture is read |
| M2 | replay.py | constructor's mode check off | `1 failed, 2 passed` | the constructor refuses outside replay |
| M3 | replay.py | `now` rounded up, not down | `1 failed, 5 passed` | never a trade after `now` |
| M4 | replay.py | window lower bound exclusive | `1 failed, 6 passed` | the bar-aligned window |
| M5 | replay.py | subscription filter off | `1 failed, 7 passed` | only subscribed pairs are served |
| M6 | replay.py | 24 h window one second wider | `1 failed, 11 passed` | a trade exactly 24 h old is excluded |
| M7 | replay.py | quote stamped one second early | `1 failed, 12 passed` | the quote is stamped `now` |
| M8 | replay_scenario.py | full spread each side | `1 failed, 12 passed` | the declared spread around the last price |
| M9 | replay_scenario.py | levels walk inward from the depth | `1 failed, 12 passed` | same |
| M10 | replay_scenario.py | quantity rounded to nearest | `1 failed, 19 passed` | engine 9's hand walk, thin bucket (5 levels, not 6) |
| M11 | replay_scenario.py | lower bound exclusive | `1 failed, 14 passed` | the bucket boundary at $10,000 |
| M12 | replay_scenario.py | the next tier's row | `1 failed, 24 passed` | the fee at the configured tier |
| M13 | replay_scenario.py | percent divided by 10 | `1 failed, 24 passed` | same |
| M14 | replay.py | an expiring trade not uncounted | `1 failed, 11 passed` | the 24 h exclusion |
| M15 | replay.py | the incremental removal skipped | `1 failed, 11 passed` | same |
| M16 | replay.py | a pair without rules served under its archive name | `1 failed, 8 passed` | survivorship named, not patched |
| M17 | replay_scenario.py | the gap check off | `1 failed, 28 passed` | a table with a gap |
| M18 | replay_scenario.py | the depth-inside-spread check off | `1 failed, 29 passed` | a depth inside the half-spread |
| M19 | replay_scenario.py | the capture hash check off | `1 failed, 41 passed` | a capture that does not match its hash |
| M20 | replay.py | depth ignored | `1 failed, 21 passed` | ten levels, three when asked for three |
| M21 | replay_scenario.py | `mapped_to` ignored | `36 failed, 6 passed` (no `-x`) | the committed table's mapped row, and every fixture-built client |
| M22 | config.py | the view's mode check off | `1 failed, 195 passed` | the view refuses a change of mode |
| M23 | config.py | `derive_config` not validating | `1 failed, 194 passed` | derived configs are validated |
| M24 | cli/engine.py | the daemon accepts replay | `1 failed, 6 passed` | the daemon refuses a replay config |
| M25 | backtest.py | exposure ignored | `1 failed, 5 passed` | the next tick |
| M26 | backtest.py | the next bar counted from the last tick | `1 failed, 7 passed` | same |
| M27 | backtest.py | the fold chosen by the tick, not the closed bar | `1 failed, 2 passed` | the fold holding the closed bar |
| M28 | backtest.py | no `activate` on a resume | `1 failed, 12 passed` | once per process |
| M29b | cli/research.py | no explicit `run_id` (the orchestrator mints) | `2 failed, 8 passed` | both resume tests |
| M30 | cli/research.py | `previous_now` not seeded | `1 failed, 6 passed` | the resume with a position open |
| M31 | cli/research.py | resting orders are not exposure | `1 failed, 7 passed` | the planted resting entry |
| M32 | cli/research.py | the anomaly run id not set per fold | `1 failed` | two clean runs, engine 13's recorded rows |
| M33 | cli/research.py | a second run into one database allowed | `1 failed, 3 passed` | refused |
| M34 | cli/research.py | `--db` optional | `1 failed, 4 passed` | refused |
| M35 | cli/research.py | the run record ignored when resuming | `1 failed, 9 passed` (second run) | the later of the record and the store |
| M36 | backtest.py | `activate` never written | `1 failed, 12 passed` | once per process |
| M37 | replay.py | the mode refusal raises the wrong type | `1 failed` | paper refused, by type |

**Survivors on the first pass, and what was done.**
- **M35 survived.** No test had a tick in the run record that the store lacked. Added
  `test_a_resume_starts_after_the_later_of_the_run_record_and_the_store`, and the re-run
  killed it.
- **M29, a constant `run_id` with the resume suffix kept: checked negative.** It survived
  because the suffix alone keeps the two processes apart. The claim underneath it, that the
  driver must name the run and not leave the orchestrator to mint it, is tested by M29b, which
  removes the name and is killed by both resume tests.

M21's first-pass kill (under `-x`) came from an incidental test, since every fixture-built client
fails to load. The run without `-x` shows the targeted test,
`test_the_committed_bucket_table_loads_with_its_medians_and_its_mapped_row`, among the 36.


### Measured: a replayed bar tick costs about 7 s before engine 8, so a run is about 45 hours

**Agent:** A-replay · **Task:** specs 131 and 142 · **Date:** 2026-09-19

**What happened.** Nine bar ticks of 2024-10-20, run over the real partitions and rules with
alphabetical ranking. The source run directories stood in for the -p7 ones, so the chain stops
at engine 13. Mean per bar tick: engine 3 took 4,717 ms, engine 5 1,765 ms, engine 1 569 ms,
and every other engine under 25 ms. That is about 7.1 s. With the ranking and engines 8 to 18
it projects to 8.5 to 9.5 s, which is 41 to 46 hours for the window's 17,470 bar ticks, against
the 7 to 15 hours spec 143 estimated.

**Why.** Engine 3 rebuilds every candle of the published window from about 417k trades on every
tick, as it does live. Its `normalise_trades` is a per-trade Python loop: an abc `isinstance`
check per field (1.67M calls) and a `.timestamp()` per trade. It then builds a polars frame from
417k Python `Decimal`s. Engine 5 costs polars time per pair across 190 pairs. The trades
themselves are not the cost: each `TradeTick` is built once, when it enters the window, and the
window after that is a cached tuple.

**Stopped.** A behaviour-preserving speed-up of engine 3 is an engine-file change, and specs 129
and 131 forbid those. The options and my recommendation went to the lead.


### Correction: a faster candle build buys almost nothing; the recommendation is withdrawn

**Agent:** A-replay · **Task:** specs 131 and 142 · **Date:** 2026-09-19

The entry above named `normalise_trades` as engine 3's cost from a cProfile run. The profiler
inflated it. Measured without the profiler over the same 417k-trade window, the build splits
into 2.4-2.6 s for normalising, 1.0-1.4 s for the frame and 0.15 s for grouping. A fast path
for `TradeTick`, prototyped in the scratchpad and never written to the file, built identical
candles in 3.5-3.7 s against 2.6-3.8 s before, which is within the noise. The cost belongs to
the interface: every tick rebuilds all its candles from a tuple of about 400k trade objects.
Recommendation (a), speeding up engine 3, is withdrawn, and the lead was told the same hour.
What remains is (b), accepting about 40 to 45 hours per run, or (c), a shorter window, which I
do not recommend.

### A-recorder — The one switchover: P1, P2 and P3 live at 05:08:44Z, with a 62.8 s gap in the archive

**Agent:** A-recorder · **Task:** switchover, on the lead's GO (b2119fd, 4b32655) · **Date:** 2026-09-19

**What was done, in this order.** Every process here is a `.venv` launcher with a child
interpreter, and on Windows killing a parent does not kill its child, so each pair was stopped
explicitly.
1. **05:08:34Z.** Stopped the hand-started funding poller (42044, and its child 51648) and the
   old supervisor (34472/34540). The old recorder kept writing through this, so it cost nothing.
2. **05:08:44.150Z.** Stopped the old recorder (34416/14508). `master.bat` was started 76 ms
   later, in its own console, with the same target as the startup shortcut. The recording
   manager (52180) was not touched.
3. The old `master.bat` console (cmd 33180) was still open at its `pause` prompt, saying "The
   supervisor has stopped. Nothing is being recorded." — false by then, and misleading to anyone
   who looked at the screen. It had no children except its console host, so I closed it.

**The gap.**

| | `ts_recv` |
|---|---|
| Last line from the old recorder | 05:08:44.099487Z |
| New `session` start marker | 05:09:44.991246Z |
| First market tick (ticker, USDT/USD) | 05:09:46.891189Z |

**62.79 s with no market data.** 60.89 s of that is before the new start marker, which is the
new recorder's discovery pass: the instrument and ticker snapshots it ranks by. The old
recorder was killed, so it wrote no `stop` marker. Its last line is complete, since the file
ends in a newline at the kill length, so nothing is partial at the seam.

**Verified, not assumed.**
- **Recorder** (46220/46912): it is writing to `data/raw`, with a last `ts_recv` of
  05:10:20.83Z checked at 05:10:20.
  - The start marker's `subscriptions[0]` is `{"channel": "instrument"}`.
  - The first `instrument` snapshot landed at 05:09:47.133Z: 1,450 pairs, 842 assets, a
    554,902-byte line with `pair` and `ts_exchange` null.
  - Tier 2 summary rows for the 05:09 minute are written.
- **Tier 1 was re-ranked on the new start.** NEAR/USD is in and ADA/USD is out, which is the
  ordinary 24-hour-volume ranking. It is not a fault, but the tier-1 set changed at 05:09:44Z.
- **funding.py** (18684/39376): it polled at start, at 05:08:45Z. That wrote 7 funding lines
  (PF_XBTUSD, ETH, ZEC, XRP, SOL, HYPE, ADA) and its start marker, and it holds its lock.
- **fees.py** (28860/34472): it polled at start, at 05:08:45Z. That wrote the `asset_pairs`
  line (1,450 pairs), the `trade_volume` line (fees for all 10 tier-1 pairs,
  `schedules_returned: true`) and its start marker, and it holds its lock. Its next slot is
  06:00Z. **PID 34472 was reused by Windows.** It is now `fees.py`'s launcher, not the old
  supervisor.
- **Both pollers' first polls used the old tier-1 list**, with ADA rather than NEAR. They
  started before the new recorder's first heartbeat and read the old one. Each re-reads the
  heartbeat before every poll, so the 06:00Z polls follow the new list.
- **The supervisor log** shows `poller_listed` for fees and funding, a launch for each of the
  three children, and no exit, restart, lock wait or `list not applied` since.
- **Not directly observed: the status block.** It renders in the new console window, and I
  cannot read another console's screen buffer. The code draws one line per poller, and the log
  shows three children running, but nobody has looked at the lines themselves. Worth one glance
  at the window.

**A correction to my P1 decision entry**, which said that sending `instrument` first means "the
archive then holds the rules before any market data priced against them". **False in arrival
order.** The subscriptions are *sent* in that order, but Kraken *answered* the ticker
subscription first: the first ticker frame came 242 ms before the snapshot. The rules land within
a second of a connect, not strictly before the first tick. A replay that needs rules in force at a
tick should take the most recent `instrument` frame at or before that tick, and for the first
fraction of a second after a connect it may have to look ahead to the snapshot that follows. This
changes no code; it corrects a claim.


## a-replay: spec 142, rehearsing one replayed day

### Decision: the rehearsal day is 2024-10-20 (fold 394)

**Agent:** A-replay · **Task:** spec 142 · **Date:** 2026-09-19

**How it was chosen.** A read-only pass over folds 379-404, using `oos_…parquet`, the Phase 5
study's anomaly and DI outputs, the archive's 15-minute bars for trailing 24-hour volume, and
the committed bucket table. On each bar it takes the expected-move leader among pairs the
anomaly and DI gates pass (R11, as `q_emrank.py` does). It then tests engine 10's bar against
the friction the replay will actually serve: the tier's fees plus the bucket spread plus the
$5,000 slippage engine 9 walks from the declared book.

**Result.** At tier 3, 28 bars in six months clear, on 13 days. 2024-10-20 has the most, 7, all
on STORJUSD, with both targets and stops among them. At tier 5 it has 10. The runner-up is
2024-09-02, with 4 bars across three pairs.

**Rejected.** 2024-09-02, which has fewer clearing bars, though they span more pairs. The spec
asks for a day on which a candidate clears; the day with the most clearances gives the
skeptic, which this pass does not model, the most chances to let one through.

**Caveat.** The capped skeptic (spec 136) was not on disk, so the pass says nothing about
whether any of the 7 survives it. `q_emrank.py` itself cannot be re-run: it reads
`per_pair_spread_depth.parquet` and the capped-skeptic outputs from its own directory, and
neither was committed.

**Served slippage, recorded.** Ten evenly spaced levels from the half-spread to the declared
depth give engine 9, at $5,000, 15.8 / 19.5 / 6.5 / 1.4 bps by bucket. The table's check-only
figures, which assume a continuous book, are 17.7 / 20.8 / 7.5 / 1.7. The gap comes from spec
129's ten discrete levels.

### The committed day: `tests/fixtures/replay/rehearsal_2024-10-20/`

Cut by `scripts/cut_replay_fixture.py`: 720,585 trades over 231 pairs, from 51 hours before
the day to its end, byte for byte from the partitions, with each source partition's sha256 in
the manifest. That is 7.3 MB of zstd parquet. The lookback is 51 hours, not the spec's "96
bars", because the replay client serves engine 3 a window of `published_bars` (200) bars.


### Dry run of the rehearsal harness: determinism holds, 6.0 s per bar tick, 1.3 GB per process

**Agent:** A-replay · **Task:** spec 142 · **Date:** 2026-09-19

`scripts/rehearse_replay_day.py` ran over the committed day with the source run directories
standing in for spec 135's (which do not exist yet) and alphabetical ranking. So engine 13
refuses every bar (`anomaly_unavailable`, 96 rejections, all on the alphabetical first pair) and
nothing trades. This is a check of the harness, not the rehearsal.

- The two clean runs wrote **identical** rows.
- The run killed at 40 ticks and resumed wrote the **same** rows, excluding `run_id` and `cycle_id`.
- 97 bar ticks. **Mean 5,955 ms per bar tick, max 10,752 ms** (the first tick, which loads the
  tape). About 580 s of wall clock per day.
- **Peak working set 1.30-1.32 GB per process.** Four runs in parallel is about 5.3 GB, well
  inside what the recorder leaves free.

The full-chain figure, with engines 8 to 18 and the batched ranking, waits on specs 135 and 144.


### Observed in the rehearsal: a target exit realised +2.0%, not the +3.0% the label books

**Agent:** A-replay · **Task:** spec 142 · **Date:** 2026-09-19

**What happened.** On 2024-10-20 at tier 3, a STORJ/USD position entered at 0.55419 with
target 0.5708157 was recorded with `outcome = target` and an exit fill of 0.56532. That is
+2.0% before fees, against the +3.0% the triple-barrier label assumes for a target.

**Why, from the fixture's own prints.** Between the 06:41 and 06:42 ticks, STORJ printed as
high as 0.57264 (06:41:12), through the target, and then fell back. Its last print before the
06:42 tick was 0.56552. Engine 21 sees the touch in `trade_ranges` and triggers. Engine 22 then
exits as a market sell (Phase 6's rule for every exit, target included). The paper broker walks
the declared book, which is centred on the **last** price, 0.56552, at the tick, so the fill
lands below the target. The stop exit the same day filled at 0.55555 against a stop of
0.55577, which is the ordinary taker slippage.

**Why it matters.** It is not a replay artefact. A live daemon exits at the next tick's book in
the same way. But every offline figure in `phase-7-findings.md` books a target at exactly
+3.0%. The chain's realised return on targets will therefore sit systematically below the
labels the models were trained on and the grids were measured with. The rehearsal was run to
find exactly this kind of thing, so it is reported to the lead before spec 143 launches, and
nothing is changed.


### The rehearsal, 2024-10-20 at tiers 3 and 5, with fold 394's Phase 7 run directory

**Agent:** A-replay · **Task:** spec 142 · **Date:** 2026-09-19

`scripts/rehearse_replay_day.py --day 2024-10-20 --fold 394 --tier {3,5}` ran with ranking
`expected_move`, over the committed day and spec 135's `train-…-f394-p7`. The two tiers ran in
parallel as separate processes, like the four runs will.

**What the day did, both tiers alike in shape.**
- 97 bar ticks and 328 minute ticks. Four approvals, all at the cost gate with the hurdle
  cleared: three on STORJ/USD and one on DOGE/USD.
- One entry, placed at 04:30, filled at its limit at 04:34 and was later stopped out.
- One entry rested five minutes, had no print below its limit, and was cancelled by engine 21.
- One entry filled and exited on target.
- One DOGE/USD entry, filled at 13:20, exited on target at 17:10 (fill 0.14161 against an entry of 0.13731).
- In all: 7 orders, 3 positions, 3 trades, 71 rejections, and 425 equity rows (one per tick). Ending equity: 5,058.50 at tier 3 and 5,073.71 at tier 5, from 5,000.00.

**Every check by recomputation passed, at both tiers.**
- Friction and hurdle, recomputed in exact rationals from the fixtures alone, equal the
  `approvals` row and the `trades` row for all 4 approvals. The inputs are the fee tier, the
  bucket (from 24 h of the fixture's own prints), and the declared book walked at the ledger's
  balance.
- Every filled entry filled at its limit, on the first tick at or after the first print
  strictly below it. The cancelled entry had no such print.
- The two clean runs wrote **identical** rows.

**Resumed run: identical in content, but not proven on a quiet tree.** The run killed at 40 ticks
and resumed differed from the clean run in one way only: its `approvals` table had an extra
`details` column. B edited migration 0006 in the shared checkout while the rehearsal ran. My
digest over `src/` and the fold directory changed between the start and the end of the rehearsal,
and C's feature engine also changed on disk in that time. Ignoring that column, the resumed rows
equal the clean run's at both tiers. **So the resume identity holds on this evidence, but the
three runs did not all see the same source.** The harness now digests `src/`, the migrations and
the fold directories before and after every run, and reports `tree_unchanged`. The rehearsal
should be re-run on the committed tree before spec 143 launches.

**Measured cost** (tier 3; tier 5 within 2%).
- Bar tick: mean **4,911 ms**, max 14,195 ms (the first tick, which loads the tape and the models).
- Minute tick: mean **4,109 ms**.
- About 28 minutes of wall clock for the day.
- **Peak working set 2.1 GB per process** (1.84 GB for the 40-tick process).

**Projection for spec 143, stated as an estimate.**
- Bar ticks: 26 weeks at 672 per week is 17,472, at 4.9 s each, **about 24 h per run**.
- Minute ticks depend on exposure. On this, the window's busiest day, each placed entry brought
  about 82 exposed minutes. At tier 3, where the offline pass found 28 clearing bars, that is
  about 2,300 minute ticks, or **about 3 h**. At tier 5, which has 183 clearing bars before the
  skeptic, the upper bound is about 15,000 minute ticks, or **about 17 h**.
- So: **tier 3 about 27 h, tier 5 somewhere from 27 to 41 h**, and the alphabetical baselines
  lower (no batched ranking, fewer trades).
- Four processes need about 8.5 GB between them.

**Mutation sweep on the two scripts:** 9 arms, 9 killed. The half-spread, the ledger's sign,
fills counted only by then, the tolerance, the digest covering migrations, the slippage term,
the cut's inclusive start, the refusal to overwrite, and the refusal of a start before the
partitions. `C1` (the inclusive start) survived at first, because no trade sat exactly on the
start. The test gained one, and the re-run killed it.


### a-replay: the lead's rulings applied, and a second `run_id` collision found

**Agent:** A-replay · **Date:** 2026-09-19

- **`training.skeptic_cap_folds`** (spec 136, c-models) is an optional int of at least 1.
  Absent means uncapped. It has two BAD_VALUES rows and a test that it is optional.
- **Cost stop ruled (b):** the run goes ahead as specified and engine 3 is not changed. The
  prototype stayed in the scratchpad and never touched a repository file (entry above).
- **The rehearsal slice moved** to `tests/fixtures/phase7/rehearsal_2024-10-20/` (D17), because
  `tests/fixtures/replay/` holds only the declared scenario fixtures. It was re-cut with the
  final script, so the manifest's `script_sha256` matches it. `.gitattributes`'
  `tests/fixtures/** -text` covers it (`git check-attr` reports `text: unset`). The first cut
  had written the manifest in text mode, which gave CRLF on Windows inside a `-text`
  directory. The cutter now writes bytes.
- **`derived_dir=paths.derived`** is passed to `StoreClient` at all three construction sites
  (`cli/engine.py`, and `cli/research.py` twice) for spec 140's SHAP writer. Without it every
  `write_shap` refuses and engine 19 carries on, so the run would silently record no SHAP. The
  daemon's `build_clients` test asserts it.
- **The no-quote window is named in the scenario identity (D7):** `quote_rule.trailing_window_s
  = 86400`, with the reason (it is the window the bucket's volume is defined over) and the
  `now` stamp.
- **`test_trade_chain_rehearsal.py` after spec 133.** The expected `trades` row now carries
  the seven approval fields, recomputed from the placing tick's **published** payloads
  (engine 18's `placed`/`userref`, engine 10's four figures, engines 8/13/15's
  `model_run_id`), not read back from `approvals`. Two arms, dropping the merge and misreading
  one figure, were each killed with `4 failed, 3 passed`.

**Found: four runs over one window would all have shared one `run_id`.** The driver named a
run `replay-<start instant>`. All four spec 143 runs start at the window's first bar, so all
four would have carried the same `run_id`. Their databases are separate, so the rows would
not collide, but engine 19's SHAP files (spec 140) sit under one shared
`data/derived/shap/<run_id>/`, where `write_shap` refuses a second writer of a path. The
second run's explanations would have been refused while its engine 19 carried on, and a
rehearsal's second clean run would have lost its SHAP to the first. **Fix:** the name now
carries the database's stem, `replay-<db stem>-<instant>`. Two clean runs therefore differ in
`run_id` by construction, so the row comparison drops the run-id columns and replaces the run
id inside any text value (a SHAP reference, a detail) with a placeholder. Row ids and tick
numbers must still match exactly between clean runs.


### Found in the preliminary rehearsal: the replay's features differ from the dataset's in the last bits, and one tree split turns on it

**Agent:** A-replay · **Task:** spec 142 (spec 144's grid check) · **Date:** 2026-09-19

**What happened.** On the preliminary rehearsal's first 18 ranked bars, engine 7's candidate
matched the offline grid's (`research/ranking_check.grid_order`, names mapped through the
recorded join) on 17. At bar 2024-10-20 00:15 (`bar_ts` 1729383300) engine 7 took USDC/USD, where
the grid takes EUR/USD. Engine 8 scored USDC/USD at 0.0047706; the out-of-sample file has
0.0046550 for USDCUSD on that bar, the same figure it gives EUR, GBP and USDT.

**Why.** I rebuilt engine 8's 117-column input for USDC/USD on that bar (engines 3, 5 and 6 run
in-process over the committed day) and compared it with the dataset row. Within 1e-9 the
two agree in every column. Exactly, they do not. The replay has `log_return_16 = 0.0`,
`efficiency_ratio_16 = 0.0`, `log_return_96 = 0.0` and `efficiency_ratio_96 = 0.0` where the
dataset has −2.7e-20, 2.7e-17, −2.4e-18 and 5.5e-16. The z-scores and ranges differ at
1e-16 to 1e-14. The fold 394 booster fed each vector gives P(target) 0.287 for the replay's
against 0.176 for the dataset's: a tree split sits between an exact zero and a rounding
residue. The residue comes from `modelling/features.py`'s rolling sums and standard
deviations (`rolling_sum_by` and its siblings), which carry floating-point error forward
along the series. The dataset computed them over the whole archive, and engine 5 over the
200 bars engine 3 publishes, so the error differs, and on a pair whose price did not move it
is the whole value. **A live daemon computes exactly as the replay does**, so the chain
agrees with what a live system would decide. It is the offline grid, and the training
data, that carry the residue.

**Consequence.** Spec 144's "the simulation matches the measurement" fails on bars where a
flat pair's features sit at a split threshold. This is not a replay defect, and nothing is
changed. The owner of `modelling/features.py` (C) is the one to judge: rounding before a
split, exact summation, or accepting the effect as a stated limitation. Reported to the lead
and to c-criteria, who is working in engine 5.


### The grid comparison over the whole rehearsal day: 68 of 75 bars agree, 7 differ inside a tie

**Agent:** A-replay · **Task:** spec 142 (spec 144's check) · **Date:** 2026-09-19

Over the 75 bars on which engine 7 ranked a candidate, its choice equals the grid's, within
engine 7's own universe, on 68. On the other 7 the chosen pair sits in the grid's tied top
group. On those bars six or more pairs (EUR, GBP, TRX, USDC, USDT, XBT against USD) carry the
same expected move, 0.004654988, the all-timeout plateau of the calibrators. Both sides
break a tie by name, but the grid spells names as the archive does (`EURUSD` sorts before
`XBTUSD`) and engine 7 as the feed does (`BTC/USD` sorts before `EUR/USD`). Six of the seven
are exactly that. The seventh is the USDC/USD bar above, where the replay's exact-zero
features lift USDC off the plateau. **No bar differs outside a tie.** The harness now reports
the ties apart from the disagreements, so neither can hide the other. Whether the grid
or the engine should spell the tie-break differently is not mine to choose. It changes which
tied pair is examined, and a tied pair on this plateau clears no hurdle.


### The preliminary rehearsal (2024-10-20, tier 3, `expected_move`, fold 394): clean on a quiet tree

**Agent:** A-replay · **Task:** spec 142 · **Date:** 2026-09-19

The harness digested `src/`, the migrations and the fold directory before and after every
run, and `tree_unchanged` is true. On that basis:
- The **two clean runs are identical.**
- The **run killed at 40 ticks and resumed is identical** to them, apart from the run-id
  columns and `cycle_id`.
- Every recomputation is equal: friction and hurdle for all 4 approvals, equal to both the
  approvals row and the trades row; 3 fills at their limit on the expected tick; 1
  cancellation with no print below its limit.
- Trades: STORJ stop (−71.03 USD), STORJ target (+45.98), DOGE target (+83.55). 71
  rejections, all `cost:net_edge_below_hurdle`.
- Every placed entry has an approvals row, and the `runs` row carries its scenario digest.
  **`approvals.details`, `rejections.details` and SHAP files are all 0:** spec 140's writer
  is not yet in engine 19 on disk. That is expected for a preliminary run, and it is a launch
  precondition for the gating one.
- Cost: bar tick mean **4,444 ms** (max 11,049), minute tick mean **4,093 ms**, and peak working
  set **2.07-2.11 GB** per process.
- The report's own `ranking_check` ran on the in-memory code from before the capture fix and
  reads 0 of 75. It was recomputed afterwards, from the same `scout.jsonl`, with the fixed
  code: 68 of 75 bars agree, 7 fall inside a tie, and 0 differ (entry above).


### The F6 stop criterion is in the harness; `replay_store`; the cutter's docstring

**Agent:** A-replay · **Task:** spec 142 · **Date:** 2026-09-19

- **The lead's F6 ruling, in code.** `ranking_check` now lists `stops`. A stop is a grid
  disagreement, or a tie, in which either pick's expected move clears `(1 +
  hurdle_multiple) x fees` at the run's tier. That fees-only floor sits below every pair's
  real bar, so the check can only flag more bars than the true rule would, never fewer. The
  report carries `ranking_stop`.
  - On the preliminary capture: tier 3 (floor 1.5%) and tier 5 (floor 1.125%) give **0
    stops** from 7 ties. A planted fee of 0.1% (floor 0.25%) turns all 7 into stops.
  - Two arms on the condition (never a stop, and the engine pick only at ten times the
    floor) were each killed by the new test.
  - Rejected: the per-pair bar with spread and slippage. It needs each pair's bucket and
    walk on the grid's side too, and a floor that is conservative by construction is enough
    for a stop rule.
- **Launch precondition 1 is testable.** The replay's store construction is now
  `cli.research.replay_store`. A test writes one SHAP explanation through it and finds the
  parquet under the derived root.
- **The cutter's docstring no longer names the declared-scenario directory.** The criterion's
  AST walk reads a docstring as a string constant. The fixture was re-cut, so the manifest's
  `script_sha256` still matches the script.
