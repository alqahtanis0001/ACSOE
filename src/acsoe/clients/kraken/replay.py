"""The replay client: history served through the surfaces the live client exposes.

Spec 129, Phase 7. `context.clients.kraken` in a replay, wrapped by the paper broker
exactly as the live client is in paper mode, so engines 1, 2, 3 and 9 and the broker
read it through their usual calls. **No engine branches on mode.** The mode difference
lives here, in the client layer, as `architecture-context.md` requires.

## It exists only in replay

Construction refuses any mode but `replay`. That refusal enforces invariant 2's
amendment (spec 126): a declared fee and a declared book may price an offline
experiment and nothing else, and this is the only reader of either fixture.

## What it serves

* **Trades.** Kraken's own time-and-sales, from the weekly partitions of spec 128, for
  every subscribed pair, in timestamp order, **never one second past `now`**.
  `recent_trades()` is a bar-aligned window of `market_sensor.published_bars` closed
  bars plus the open one, so engine 3 publishes the same candles the features were
  trained on. Live keeps a window of 200,000 trades by count; at this pair count that is
  under a day, the 96-bar features would go unfilled, and the replay would stop
  describing the offline measurement it has to match (spec 144). No gap marker is ever
  synthesised: history has no outages, and a fabricated gap would be a fabricated
  `data_guard` block.
* **A declared book** per pair at `now`: centred on the last traded price, with the
  spread and depth of the pair's bucket of trailing 24-hour dollar volume (spec 130).
  Every pair takes its bucket's value, recorded or not. **A pair with no trade in that
  24-hour window has no quote and no book**, never a zero spread. The quote is stamped
  `now`: the book is declared at `now`, not observed at the last trade, so engine 4's
  staleness check does not fire in replay.
* **Pair rules** from the recorded snapshot, keyed by v2 symbol.
* **The fee** at the configured tier of the declared schedule, through `TradeVolume`.
* **No balance.** The paper broker wraps this client and is the account (invariant 2's
  paper ledger). `balance()` refuses.
* **No order.** The four order calls refuse. The broker answers them and never forwards.

Every spread, depth and fee here is **declared**. The trades are the only thing that is
the replayed period's own record.
"""

from __future__ import annotations

import bisect
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, Inexact, localcontext
from pathlib import Path
from typing import Any, Final

from acsoe.clients.kraken.contracts import (
    BalancesSnapshot,
    FeeTierSnapshot,
    OrderAck,
    OrderBookSnapshot,
    OrderRequest,
    OrderState,
    PairRulesSnapshot,
    QuoteTick,
    RawFrame,
    RetainedValue,
    TradeTick,
    to_micros,
)
from acsoe.clients.kraken.errors import KrakenUnavailableError
from acsoe.clients.kraken.replay_scenario import (
    BOOK_LEVELS,
    ReplayScenario,
    ScenarioError,
    SyntheticBook,
    load_fee_scenario,
    load_pair_rules,
    load_spread_table,
    sha256_file,
    synthetic_book,
)

__all__ = ["ReplayKrakenClient", "ReplayModeError", "TradeTape"]

#: The trailing window a pair's liquidity bucket is measured over, fixed by the ruling
#: (spec 130: "trailing 24-hour dollar volume"). A pair with no trade inside it has no
#: quote. A definition of the declared table, not a Kraken value.
VOLUME_WINDOW_S: Final = 24 * 60 * 60

_WEEK_S: Final = 7 * 24 * 60 * 60

#: Enough digits that summing a day of `price x qty` is exact, and a trap on `Inexact`
#: that proves it: an incremental sum and a from-scratch sum after a resume must be the
#: same number, and a rounded sum is not associative.
_VOLUME_PRECISION: Final = 80


class ReplayModeError(RuntimeError):
    """The replay client was asked for outside replay mode. Invariant 2's amendment."""


def _week_start(moment_s: int, anchor_s: int) -> int:
    """The start of the partition week holding `moment_s`, on the manifest's grid."""
    return anchor_s + ((moment_s - anchor_s) // _WEEK_S) * _WEEK_S


class TradeTape:
    """The weekly partitions, loaded as the clock reaches them and dropped behind it.

    Every trade is held as its published text until it first enters a window, and is
    parsed into a validated `TradeTick` then, once. Trades are ordered by timestamp,
    then by symbol, then by their order in the source file, so two trades in one second
    on one pair keep the order the archive gave them (engine 3 takes a bar's open and
    close from arrival order).
    """

    def __init__(
        self,
        directory: Path,
        *,
        manifest: Mapping[str, Any],
        archive_symbols: Mapping[str, str],
        keep_s: int,
    ) -> None:
        self._directory = directory
        self._keep_s = keep_s
        pairs = manifest.get("pairs")
        if not isinstance(pairs, Mapping) or not pairs:
            raise ScenarioError("the partition manifest lists no pairs")
        self._weeks: dict[int, list[tuple[str, str]]] = {}
        for archive, entry in pairs.items():
            symbol = archive_symbols.get(str(archive))
            if symbol is None:
                continue
            weeks = entry.get("weeks") if isinstance(entry, Mapping) else None
            if not isinstance(weeks, Mapping):
                raise ScenarioError(f"the partition manifest has no weeks for {archive}")
            for week, rows in weeks.items():
                if int(rows) <= 0:
                    continue
                start = int(datetime.fromisoformat(str(week)).replace(tzinfo=UTC).timestamp())
                self._weeks.setdefault(start, []).append((str(archive), symbol))
        if not self._weeks:
            raise ScenarioError("no partition week holds a trade on a pair with rules")
        self._anchor = min(self._weeks)
        self._last_week = max(self._weeks)
        self._loaded: dict[int, list[tuple[int, str, str, str]]] = {}
        self._ts: list[int] = []
        self._rows: list[tuple[int, str, str, str]] = []
        self._ticks: list[TradeTick | None] = []

    def ensure(self, now_s: int) -> None:
        """Hold every week that can contain a trade in `[now_s - keep_s, now_s]`."""
        if now_s >= self._last_week + _WEEK_S:
            raise ScenarioError(
                f"{datetime.fromtimestamp(now_s, UTC).isoformat()} is past the last "
                "partition week; the replay cannot serve a period it has no trades for"
            )
        first = _week_start(now_s - self._keep_s, self._anchor)
        wanted = set(range(first, _week_start(now_s, self._anchor) + 1, _WEEK_S))
        if first < self._anchor:
            raise ScenarioError(
                "the window reaches before the first partition week: the warm-up history "
                "is missing, and features built on it would be under-filled"
            )
        if wanted == set(self._loaded):
            return
        for week in sorted(set(self._loaded) - wanted):
            del self._loaded[week]
        for week in sorted(wanted - set(self._loaded)):
            self._loaded[week] = self._read_week(week)
        rows = [row for week in sorted(self._loaded) for row in self._loaded[week]]
        # Weeks do not overlap, so the concatenation is already in order.
        self._rows = rows
        self._ts = [row[0] for row in rows]
        self._ticks = [None] * len(rows)

    def _read_week(self, week: int) -> list[tuple[int, str, str, str]]:
        import polars as pl

        label = datetime.fromtimestamp(week, UTC).strftime("%Y-%m-%d")
        rows: list[tuple[int, str, str, int, str, str]] = []
        for archive, symbol in self._weeks.get(week, []):
            path = self._directory / archive / f"{label}.parquet"
            if not path.is_file():
                raise ScenarioError(f"the manifest lists {path} and it is not on disk")
            frame = pl.read_parquet(path)
            stamps = frame["ts"].to_list()
            prices = frame["price"].cast(pl.Utf8).to_list()
            volumes = frame["volume"].cast(pl.Utf8).to_list()
            rows.extend(
                (int(ts), symbol, archive, seq, price, qty)
                for seq, (ts, price, qty) in enumerate(zip(stamps, prices, volumes, strict=True))
            )
        rows.sort(key=lambda row: (row[0], row[1], row[3]))
        return [(ts, symbol, price, qty) for ts, symbol, _archive, _seq, price, qty in rows]

    # -- reads ----------------------------------------------------------- #

    def bounds(self, lower_s: int, upper_s: int) -> tuple[int, int]:
        """Indices of trades with `lower_s < ts <= upper_s`."""
        return bisect.bisect_right(self._ts, lower_s), bisect.bisect_right(self._ts, upper_s)

    def row(self, index: int) -> tuple[int, str, str, str]:
        return self._rows[index]

    def tick(self, index: int) -> TradeTick:
        built = self._ticks[index]
        if built is None:
            ts, symbol, price, qty = self._rows[index]
            built = TradeTick(
                pair=symbol,
                ts=datetime.fromtimestamp(ts, UTC),
                price=Decimal(price),
                qty=Decimal(qty),
            )
            self._ticks[index] = built
        return built

    @property
    def loaded_weeks(self) -> tuple[int, ...]:
        return tuple(sorted(self._loaded))


class ReplayKrakenClient:
    """REST reads, the stream, and four refusing order calls, all served from history.

    Build it with :meth:`from_config`. The constructor takes the loaded parts so a test
    can build one over fabricated fixtures, and it still refuses any mode but replay.
    """

    def __init__(
        self,
        *,
        mode: str,
        clock: Any,
        scenario: ReplayScenario,
        tape: TradeTape,
        interval_s: int,
        published_bars: int,
    ) -> None:
        if str(mode) != "replay":
            raise ReplayModeError(
                f"the replay client serves a declared fee and a declared book, which "
                f"invariant 2 permits in replay mode only; refused in mode {mode!r}"
            )
        self._clock = clock
        self._scenario = scenario
        self._tape = tape
        self._interval_s = interval_s
        self._published_bars = published_bars
        self._subscription: tuple[str, ...] = ()
        self._rules = scenario.rules.rules
        self._last_rules: PairRulesSnapshot | None = None
        # The rolling 24-hour state: the window `(lo, hi]` it currently describes, each
        # pair's dollar volume and trade count inside it, and its last traded price.
        self._vol_lo: int | None = None
        self._vol_hi: int | None = None
        self._volume: dict[str, Decimal] = {}
        self._count: dict[str, int] = {}
        self._last_price: dict[str, Decimal] = {}
        self._drained_to: int | None = None
        self._window_cache: tuple[int, tuple[str, ...], tuple[TradeTick, ...]] | None = None

    # -- construction --------------------------------------------------- #

    @classmethod
    def from_config(
        cls,
        config: Any,
        *,
        clock: Any,
        root: Path,
        extras: Mapping[str, Any] | None = None,
    ) -> ReplayKrakenClient:
        """Load the scenario the `replay` section names, refusing outside replay first.

        The mode is checked before any fixture is opened, so a paper or live process
        never so much as reads the declared fee.
        """
        if str(config.mode) != "replay":
            raise ReplayModeError(
                "the replay client is constructible in replay mode only (invariant 2's "
                f"amendment, spec 126); this config is mode {config.mode!r}"
            )

        def path(key: str) -> Path:
            value = Path(str(config.get(key)))
            return value if value.is_absolute() else root / value

        rules = load_pair_rules(
            path("replay.instrument_file"),
            path("replay.pair_names_file"),
            asset_pairs_path=path("replay.asset_pairs_file"),
            relative_to=root,
        )
        table = load_spread_table(path("replay.spread_table_file"), relative_to=root)
        fee = load_fee_scenario(
            path("replay.fee_schedule_file"), tier=int(config.get("replay.fee_tier")),
            relative_to=root,
        )
        partitions_dir = path("replay.partitions_dir")
        manifest_path = partitions_dir / "manifest.json"
        if not manifest_path.is_file():
            raise ScenarioError(f"no partition manifest at {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        interval_s = int(config.get("timeframes.decision_bar_s"))
        published_bars = int(config.get("market_sensor.published_bars"))
        unmapped = sorted(
            str(name) for name in manifest.get("pairs", {}) if name not in rules.archive_symbols
        )
        scenario = ReplayScenario(
            rules=rules,
            table=table,
            fee=fee,
            partitions={
                "manifest": manifest_path.relative_to(root).as_posix()
                if manifest_path.is_relative_to(root)
                else manifest_path.as_posix(),
                "sha256": sha256_file(manifest_path),
                "archive_pairs": len(manifest.get("pairs", {})),
                "archive_pairs_without_rules": unmapped,
            },
            extras={
                # Which pairs have a quote at all, and so which pairs are in the universe:
                # a pair quotes only if it traded in the trailing window its bucket is
                # measured over. The lead asked for it named in the identity (D7).
                "quote_rule": {
                    "trailing_window_s": VOLUME_WINDOW_S,
                    "rule": "a pair has a quote and a book at `now` only if it traded in "
                    "(now - 24 h, now]; otherwise it has none, never a zero spread",
                    "why": "the 24 h is the window the bucket's dollar volume is defined "
                    "over (spec 130); a pair with no trade in it has no bucket and no "
                    "last price to centre a declared book on",
                    "quote_stamped": "now (D7): the book is declared at the tick",
                },
                **dict(extras or {}),
            },
        )
        tape = TradeTape(
            partitions_dir,
            manifest=manifest,
            archive_symbols=rules.archive_symbols,
            keep_s=max(VOLUME_WINDOW_S, (published_bars + 1) * interval_s),
        )
        return cls(
            mode=str(config.mode),
            clock=clock,
            scenario=scenario,
            tape=tape,
            interval_s=interval_s,
            published_bars=published_bars,
        )

    # -- identity, for spec 134 ----------------------------------------- #

    @property
    def scenario(self) -> ReplayScenario:
        return self._scenario

    @property
    def scenario_digest(self) -> str:
        return self._scenario.digest

    @property
    def scenario_description(self) -> str:
        return self._scenario.description_json

    # -- the clock ------------------------------------------------------ #

    def _now(self) -> datetime:
        now: datetime = self._clock.now()
        if now.tzinfo is None:
            raise ValueError("the replay clock returned a naive datetime")
        return now

    def _now_s(self) -> int:
        """`now` in whole seconds, rounded **down**: a trade stamped in the second
        after `now` is in the future and is never served."""
        return int(to_micros(self._now()) // 1_000_000)

    def _advance(self) -> int:
        """Bring the tape and the rolling 24-hour state up to `now`. Idempotent."""
        now_s = self._now_s()
        self._tape.ensure(now_s)
        lo, hi = now_s - VOLUME_WINDOW_S, now_s
        if self._vol_hi is not None and (hi < self._vol_hi or lo < (self._vol_lo or lo)):
            raise ValueError("the replay clock moved backwards; history is only walked forward")
        with localcontext() as ctx:
            ctx.prec = _VOLUME_PRECISION
            ctx.traps[Inexact] = True
            if self._vol_hi is None or self._vol_lo is None or lo >= self._vol_hi:
                self._volume, self._count, self._last_price = {}, {}, {}
                start, end = self._tape.bounds(lo, hi)
                self._add(range(start, end))
            else:
                self._add(range(*self._tape.bounds(self._vol_hi, hi)))
                self._remove(range(*self._tape.bounds(self._vol_lo, lo)))
        self._vol_lo, self._vol_hi = lo, hi
        return now_s

    def _add(self, indices: range) -> None:
        for index in indices:
            _ts, symbol, price, qty = self._tape.row(index)
            value = Decimal(price)
            self._volume[symbol] = self._volume.get(symbol, Decimal(0)) + value * Decimal(qty)
            self._count[symbol] = self._count.get(symbol, 0) + 1
            self._last_price[symbol] = value

    def _remove(self, indices: range) -> None:
        for index in indices:
            _ts, symbol, price, qty = self._tape.row(index)
            self._volume[symbol] -= Decimal(price) * Decimal(qty)
            self._count[symbol] -= 1
            if self._count[symbol] == 0:
                del self._count[symbol]
                del self._volume[symbol]
                del self._last_price[symbol]

    def _book(self, pair: str) -> SyntheticBook | None:
        self._advance()
        if pair not in self._count:
            return None
        bucket = self._scenario.table.bucket_for(self._volume[pair])
        return synthetic_book(
            mid=self._last_price[pair],
            bucket=bucket,
            depth_notional_usd=self._scenario.table.depth_notional_usd,
        )

    def trailing_volume_usd(self, pair: str) -> Decimal | None:
        """The pair's dollar volume over the trailing 24 hours, or `None` with no trade.
        Exposed for the rehearsal's recomputation, never read by an engine."""
        self._advance()
        return self._volume.get(pair)

    # -- REST ----------------------------------------------------------- #

    async def asset_pairs(self) -> PairRulesSnapshot:
        snapshot = PairRulesSnapshot(pairs=self._rules, fetched_at=to_micros(self._now()))
        self._last_rules = snapshot
        return snapshot

    async def trade_volume(self) -> FeeTierSnapshot:
        fee = self._scenario.fee
        return FeeTierSnapshot(
            tier=fee.tier,
            currency="USD",
            volume_30d=fee.spot_volume_floor_usd,
            maker_fee_pct=fee.maker_fee_pct,
            taker_fee_pct=fee.taker_fee_pct,
            fetched_at=to_micros(self._now()),
        )

    async def balance(self) -> BalancesSnapshot:
        raise KrakenUnavailableError(
            "the replay client holds no account: in a replay the paper broker wraps it "
            "and is the balance (invariant 2's paper ledger)"
        )

    async def order_book(self, pair: str, depth: int = BOOK_LEVELS) -> OrderBookSnapshot:
        book = self._book(pair)
        if book is None:
            raise KrakenUnavailableError(
                f"{pair} has no trade in the trailing 24 hours, so the replay declares no "
                "book for it; absent is never a zero spread"
            )
        levels = max(1, min(int(depth), BOOK_LEVELS))
        return OrderBookSnapshot(
            pair=pair,
            bids=book.bids[:levels],
            asks=book.asks[:levels],
            fetched_at=to_micros(self._now()),
        )

    @property
    def last_known_good_asset_pairs(self) -> RetainedValue | None:
        if self._last_rules is None:
            return None
        return RetainedValue(value=self._last_rules, fetched_at=self._last_rules.fetched_at)

    @property
    def last_known_good_balances(self) -> RetainedValue | None:
        return None

    # -- orders: never here --------------------------------------------- #

    def _no_orders(self) -> KrakenUnavailableError:
        return KrakenUnavailableError(
            "the replay client places no order; in a replay the paper broker wraps it and "
            "answers every order call itself"
        )

    async def add_order(self, request: OrderRequest) -> OrderAck:  # noqa: ARG002 - the order surface is fixed and this client places nothing
        raise self._no_orders()

    async def cancel_order(self, userref: int) -> OrderState:  # noqa: ARG002 - as above
        raise self._no_orders()

    async def query_orders(self, userrefs: Sequence[int]) -> tuple[OrderState, ...]:  # noqa: ARG002 - as above
        raise self._no_orders()

    async def open_orders(self) -> tuple[OrderState, ...]:
        raise self._no_orders()

    # -- stream --------------------------------------------------------- #

    def start(self) -> None:
        """Nothing to open: history is on disk."""

    def stop(self) -> None:
        """Nothing to close."""

    def set_subscription(self, pairs: Sequence[str]) -> bool:
        desired = tuple(sorted(dict.fromkeys(str(pair) for pair in pairs)))
        if desired == self._subscription:
            return False
        self._subscription = desired
        return True

    @property
    def subscription(self) -> tuple[str, ...]:
        return self._subscription

    @property
    def connected(self) -> bool:
        return True

    @property
    def gaps(self) -> tuple[Mapping[str, Any], ...]:
        return ()

    def drain(self) -> tuple[RawFrame, ...]:
        """No raw frame. A replay writes nothing to the archive (invariant 11)."""
        return ()

    def drain_gaps(self) -> tuple[Mapping[str, Any], ...]:
        """No gap is ever synthesised: history has no outages."""
        return ()

    def recent_trades(self) -> tuple[TradeTick, ...]:
        """The subscribed pairs' trades in the bar-aligned window, oldest first.

        `[bar_open(now) - published_bars x bar, now]`: exactly `published_bars` closed
        bars and the open one, so no candle engine 3 publishes is ever partial.
        """
        now_s = self._advance()
        cached = self._window_cache
        if cached is not None and cached[0] == now_s and cached[1] == self._subscription:
            return cached[2]
        bar_open = (now_s // self._interval_s) * self._interval_s
        lower = bar_open - self._published_bars * self._interval_s
        start, end = self._tape.bounds(lower - 1, now_s)
        wanted = frozenset(self._subscription)
        trades = tuple(
            self._tape.tick(index)
            for index in range(start, end)
            if self._tape.row(index)[1] in wanted
        )
        self._window_cache = (now_s, self._subscription, trades)
        return trades

    def drain_trades(self) -> tuple[TradeTick, ...]:
        """Subscribed trades since the previous call, consumed. Nothing calls it."""
        now_s = self._advance()
        since = self._drained_to if self._drained_to is not None else now_s - VOLUME_WINDOW_S
        start, end = self._tape.bounds(since, now_s)
        wanted = frozenset(self._subscription)
        self._drained_to = now_s
        return tuple(
            self._tape.tick(index)
            for index in range(start, end)
            if self._tape.row(index)[1] in wanted
        )

    def latest_quote(self, pair: str) -> QuoteTick | None:
        book = self._book(pair)
        if book is None:
            return None
        return QuoteTick(pair=pair, ts=self._now(), bid=book.bids[0][0], ask=book.asks[0][0])

