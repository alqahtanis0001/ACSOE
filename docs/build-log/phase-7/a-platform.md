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

