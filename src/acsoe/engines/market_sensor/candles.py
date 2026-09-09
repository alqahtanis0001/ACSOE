"""Building 15-minute candles from trades.

Separated from the engine so `scripts/verify.py` can call :func:`build_candles`
directly against a committed fixture without constructing an `EngineContext`, and so
the arithmetic is testable on its own.

Three rules, and the third is the one this project cares most about.

**Candles come from trades, not from a ticker.** A candle is a statement about what
*traded*. Building from a ticker stream would manufacture a candle for every quiet
minute, which is the same lie as interpolating one.

**Money is `Decimal` throughout.** `polars` does the grouping — it is the columnar part
and where it earns its keep — with `pl.Decimal` columns, so open/high/low/close/volume
come back as exact `Decimal`s and never touch binary float.

**A bar in which nothing traded has no candle, and one is never invented.** The
timestamps of those bars are reported by :func:`missing_bar_timestamps` so the caller
can see them; nothing here fills, forward-fills, resamples or smooths one into
existence, and there is deliberately no flag that does. A synthesised candle at a price
that never traded invents a barrier touch that never happened, and Phase 4's
triple-barrier labelling would learn a fabricated outcome from it. That error is
invisible to any check that only asks whether the series is continuous.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

import polars as pl
from pydantic import BaseModel, ConfigDict

from acsoe.clients.kraken.contracts import Money, money_text

__all__ = [
    "Candle",
    "bar_open_seconds",
    "build_candles",
    "missing_bar_timestamps",
    "normalise_trades",
]

#: Wide enough for any crypto price or quantity, with room for a summed volume.
_DECIMAL_DTYPE = pl.Decimal(38, 12)


def _trim(value: Decimal) -> Decimal:
    """Drop the trailing zeros `polars` pads a fixed-scale Decimal column with.

    ``normalize()`` alone would turn ``Decimal("50000")`` into ``Decimal("5E+4")``,
    which is numerically identical and renders as nonsense in a JSON payload a human
    reads, so an integral result is re-quantised to a plain integer.
    """
    trimmed = value.normalize()
    return (
        trimmed.quantize(Decimal(1)) if trimmed == trimmed.to_integral_value() else trimmed
    )


def bar_open_seconds(moment_s: int, *, interval_s: int) -> int:
    """The opening second of the bar containing ``moment_s``."""
    if interval_s <= 0:
        raise ValueError("interval_s must be positive")
    return (moment_s // interval_s) * interval_s


class Candle(BaseModel):
    """One closed bar in which trading actually happened."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    ts: int
    """The bar's **opening** second, UTC. Integer seconds, as `verify.py` reads it."""

    open: Money
    high: Money
    low: Money
    close: Money
    volume: Money
    trades: int

    def state_dict(self) -> dict[str, Any]:
        """The JSON-safe form. Money as exact decimal strings, never floats."""
        return {
            "pair": self.pair,
            "ts": self.ts,
            "open": money_text(self.open),
            "high": money_text(self.high),
            "low": money_text(self.low),
            "close": money_text(self.close),
            "volume": money_text(self.volume),
            "trades": self.trades,
        }


def _seconds(value: Any) -> int:
    """Trade timestamps arrive as seconds, as an ISO string, or as a datetime."""
    if isinstance(value, bool):
        raise ValueError("a boolean is not a timestamp")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, datetime):
        return int(value.timestamp())
    if isinstance(value, str):
        text = value.strip()
        if text.replace(".", "", 1).isdigit():
            return int(float(text))
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    raise ValueError(f"cannot read a timestamp from {type(value).__name__}")


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise ValueError(
            f"{field} arrived as a float, which has already lost precision. Trade "
            "prices and quantities cross this boundary as strings or Decimals."
        )
    if isinstance(value, bool):
        raise ValueError(f"{field} cannot be a boolean")
    return Decimal(str(value))


def _field(trade: Any, name: str) -> Any:
    if isinstance(trade, Mapping):
        if name not in trade:
            raise ValueError(f"a trade must carry {name!r}")
        return trade[name]
    try:
        return getattr(trade, name)
    except AttributeError as exc:
        raise ValueError(f"a trade must carry {name!r}") from exc


def normalise_trades(trades: Iterable[Any]) -> list[tuple[str, int, Decimal, Decimal]]:
    """``(pair, seconds, price, qty)`` from mappings, `TradeTick`s, or anything with
    those four attributes.

    Deliberately structural. `scripts/verify.py` feeds this a committed JSON fixture,
    the engine feeds it `TradeTick`s off the stream, and neither should have to know
    about the other.
    """
    rows: list[tuple[str, int, Decimal, Decimal]] = []
    for trade in trades:
        pair = str(_field(trade, "pair"))
        stamp = _seconds(_field(trade, "ts"))
        price = _decimal(_field(trade, "price"), "price")
        qty = _decimal(_field(trade, "qty"), "qty")
        if price <= 0 or qty <= 0:
            raise ValueError("a trade has a positive price and a positive quantity")
        rows.append((pair, stamp, price, qty))
    return rows


def build_candles(trades: Iterable[Any], *, interval_s: int) -> list[Candle]:
    """One candle per bar **in which something traded**, oldest first.

    A bar with no trades produces no candle. That absence is the whole point and is
    load-bearing downstream — see the module docstring.

    Ties are broken by input order, which is the order the trades arrived in. Two
    trades stamped the same second are common; `open` is the first of them as
    received and `close` is the last, which is the only ordering available and the one
    the exchange itself implies.
    """
    if interval_s <= 0:
        raise ValueError("interval_s must be positive")
    rows = normalise_trades(trades)
    if not rows:
        return []

    frame = pl.DataFrame(
        {
            "pair": [row[0] for row in rows],
            "bar": [bar_open_seconds(row[1], interval_s=interval_s) for row in rows],
            "seq": list(range(len(rows))),
            "price": [row[2] for row in rows],
            "qty": [row[3] for row in rows],
        },
        schema_overrides={"price": _DECIMAL_DTYPE, "qty": _DECIMAL_DTYPE},
    ).sort("seq")

    grouped = (
        frame.group_by(["pair", "bar"])
        .agg(
            pl.first("price").alias("open"),
            pl.max("price").alias("high"),
            pl.min("price").alias("low"),
            pl.last("price").alias("close"),
            pl.sum("qty").alias("volume"),
            pl.len().alias("trades"),
        )
        .sort(["pair", "bar"])
    )

    return [
        Candle(
            pair=str(row["pair"]),
            ts=int(row["bar"]),
            open=_trim(row["open"]),
            high=_trim(row["high"]),
            low=_trim(row["low"]),
            close=_trim(row["close"]),
            volume=_trim(row["volume"]),
            trades=int(row["trades"]),
        )
        for row in grouped.to_dicts()
    ]


def missing_bar_timestamps(
    candles: Sequence[Candle], *, interval_s: int, pair: str | None = None
) -> list[int]:
    """The bar openings, inside the covered range, in which nothing traded.

    **Reported, never filled.** A missing candle means no trades occurred — a fact
    about the market, not damage to be repaired — and the feature layer decides what to
    do about it. Nothing in this module will invent one, and there is no flag that
    will.

    Bounded by the first and last candle present: a bar before the data starts or after
    it ends is not "missing", it is simply outside the range.
    """
    selected = [c for c in candles if pair is None or c.pair == pair]
    if len(selected) < 2:
        return []
    present = {c.ts for c in selected}
    first, last = min(present), max(present)
    return [ts for ts in range(first, last + interval_s, interval_s) if ts not in present]
