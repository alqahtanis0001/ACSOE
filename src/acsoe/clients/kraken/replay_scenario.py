"""The replay scenario: the recorded and declared inputs a replay is priced on.

Spec 129, Phase 7. Three committed fixtures and one derived manifest are loaded once,
validated at load, and summarised into one identity. Spec 134 writes that identity to
the `runs` row.

* **Pair rules**: the v2 `instrument` snapshot recorded beside `AssetPairs` (spec 127).
  Rules are keyed by the v2 symbol (`BTC/USD`), because that is how engines 3, 7, 9, 10
  and 11 key everything else. The archive names come from spec 127's recorded join. REST's
  own keys (`XXBTZUSD`, quote `ZUSD`) would make engine 7 exclude every pair, as A's
  recorder gap audit found.
* **The spread and depth table** (spec 130): per bucket of trailing 24-hour dollar
  volume. **Declared, not measured.** It comes from 7.4 days of a 2026 recording and is
  applied uniformly to a 2023-24 window, so it is never a measurement of the replayed
  period.
* **The fee schedule** (spec 130 step 3): Kraken's published schedule, fetched
  2026-09-19. **Declared.** One tier of its Spot Crypto table is served to every pair,
  through the `TradeVolume` surface.
* **The partition manifest** (spec 128): which trades are served.

Nothing here estimates anything. Every value returned is a recorded rule or a number
read from a declared fixture. A fixture that cannot be read refuses the whole scenario
rather than leaving a gap to be filled.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Final

from acsoe.clients.kraken.contracts import PairRule, money_text

__all__ = [
    "DECLARED_STATEMENT",
    "Bucket",
    "FeeScenario",
    "ReplayScenario",
    "ScenarioError",
    "SpreadTable",
    "canonical_json",
    "load_fee_scenario",
    "load_pair_rules",
    "load_spread_table",
]

#: Carried in every scenario description, so no reader of a `runs` row can take a
#: served spread, depth or fee for a measurement of the replayed period.
DECLARED_STATEMENT: Final = (
    "DECLARED, not measured. The spread and depth come from a liquidity-bucket table "
    "built from a 2026 recording and applied uniformly to every pair of a 2023-24 "
    "window. The fee is Kraken's schedule fetched 2026-09-19, applied at one tier to "
    "every pair. The pair rules are a 2026 recording. Only the trades are the period's "
    "own record."
)


class ScenarioError(ValueError):
    """A scenario fixture is missing, malformed or inconsistent. Never defaulted."""


def canonical_json(payload: Any) -> str:
    """Sorted keys, no whitespace: the one serialisation the digest is taken over."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    """JSON with every non-integer number read as an exact `Decimal`.

    The v2 `instrument` snapshot carries `qty_min` and `tick_size` as JSON **numbers**.
    Read through the default `float`, `0.0001` survives by luck and a longer increment
    does not, and a pair rule is a value that must never have been a float.
    """
    if not path.is_file():
        raise ScenarioError(f"scenario fixture not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"{path} is not valid JSON: {exc}") from exc


def _decimal(value: Any, where: str) -> Decimal:
    if isinstance(value, bool | float):
        raise ScenarioError(f"{where} is {value!r}, which is not an exact decimal")
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ScenarioError(f"{where} is not a decimal number: {value!r}") from exc
    if not result.is_finite():
        raise ScenarioError(f"{where} is not finite: {value!r}")
    return result


def _mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ScenarioError(f"{where} is {type(value).__name__}, expected an object")
    return value


# --------------------------------------------------------------------------- #
# The fee scenario
# --------------------------------------------------------------------------- #

#: The table of the committed schedule that is served. The page's other table,
#: "Stablecoin, Pegged Token & FX Pairs", cannot be served per pair: `TradeVolume`'s
#: snapshot is account-level, one maker and one taker, and engine 10 reads that. So
#: every pair is priced at this table's tier. The findings name the consequence (§7),
#: and the lead holds the choice as stop S-fee-class.
FEE_TABLE: Final = "spot_crypto"


@dataclass(frozen=True)
class FeeScenario:
    """One tier of the declared schedule, as the replay client serves it."""

    file: str
    sha256: str
    table: str
    tier: int
    maker_fee_pct: Decimal
    taker_fee_pct: Decimal
    spot_volume_floor_usd: Decimal
    """The tier's qualifying 30-day spot volume, from the same row. Nothing reads it;
    it fills `FeeTierSnapshot.volume_30d`, which is required, with the schedule's own
    figure rather than an invented one, and the description says so."""

    def describe(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "sha256": self.sha256,
            "table": self.table,
            "tier": self.tier,
            "maker_fee_pct": money_text(self.maker_fee_pct),
            "taker_fee_pct": money_text(self.taker_fee_pct),
            "volume_30d_served": money_text(self.spot_volume_floor_usd),
            "volume_30d_note": "the tier's qualifying spot volume from the schedule row; "
            "declared, and read by no engine",
        }


def _percent(text: Any, where: str) -> Decimal:
    """`"0.22 %"` as the ratio `0.0022`. The schedule publishes percents; the client
    boundary carries ratios, and a percent passed through unconverted would be a fee a
    hundred times too large that `FeeTierSnapshot`'s validator would still accept for
    any value up to 1%."""
    raw = str(text).replace("%", "").strip()
    return _decimal(raw, where) / Decimal(100)


def _usd_floor(text: Any, where: str) -> Decimal:
    """`"$10K+"` as `10000`: the schedule's own spelling, with its K and M."""
    raw = str(text).replace("$", "").replace(",", "").replace("+", "").strip().upper()
    scale = Decimal(1)
    if raw.endswith("K"):
        raw, scale = raw[:-1], Decimal(1_000)
    elif raw.endswith("M"):
        raw, scale = raw[:-1], Decimal(1_000_000)
    return _decimal(raw, where) * scale


def load_fee_scenario(path: Path, *, tier: int, relative_to: Path | None = None) -> FeeScenario:
    """The Spot Crypto row named `Tier <tier>`, or a refusal.

    An absent tier refuses construction. The spec's "an absent fixture or tier is a
    failed fetch" is kept stricter than that on purpose: a tier missing from a committed
    fixture is a configuration defect known before the first tick, and a run that
    blocked every pair for six months to report it would be the wrong place to learn it.
    """
    payload = _mapping(_read_json(path), str(path))
    rows = payload.get(FEE_TABLE)
    if not isinstance(rows, Sequence) or not rows:
        raise ScenarioError(f"{path} has no {FEE_TABLE!r} table")
    wanted = f"Tier {tier}"
    matches = [row for row in rows if isinstance(row, Mapping) and row.get("Tier") == wanted]
    if len(matches) != 1:
        raise ScenarioError(
            f"{path} has {len(matches)} rows named {wanted!r} in {FEE_TABLE!r}; exactly one "
            "is required, and no tier is assumed"
        )
    row = matches[0]
    where = f"{path.name}:{FEE_TABLE}:{wanted}"
    return FeeScenario(
        file=_relative(path, relative_to),
        sha256=sha256_file(path),
        table=FEE_TABLE,
        tier=tier,
        maker_fee_pct=_percent(row.get("Spot Maker (%)"), f"{where}:maker"),
        taker_fee_pct=_percent(row.get("Spot Taker (%)"), f"{where}:taker"),
        spot_volume_floor_usd=_usd_floor(
            row.get("Spot 30-Day Vol (USD) OR"), f"{where}:volume"
        ),
    )


def _relative(path: Path, root: Path | None) -> str:
    """A path as it goes into the description: relative to the repository when it can
    be, so the digest does not change with the checkout's location."""
    resolved = path.resolve()
    if root is not None:
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return resolved.as_posix()


# --------------------------------------------------------------------------- #
# Pair rules
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RecordedRules:
    """The recorded rules, keyed by v2 symbol, and the archive-name mapping."""

    rules: Mapping[str, PairRule]
    archive_symbols: Mapping[str, str]
    """Archive file stem (`XBTUSD`, the REST `altname`) to v2 symbol (`BTC/USD`), from
    spec 127's recorded name join, for every pair the v2 snapshot lists."""
    status_counts: Mapping[str, int]
    files: tuple[dict[str, str], ...]


def _captured_payload(path: Path) -> Any:
    """The verbatim payload of a spec 127 capture, parsed with exact decimals.

    Spec 127 stores the body as received, as a JSON **string** under `payload`, beside a
    `provenance` block carrying its sha256. That text is parsed here with
    `parse_float=Decimal`, so no rule value ever passes through a float, and its sha256 is
    checked against the recorded one: a capture edited after the fact is refused.
    """
    wrapper = _mapping(_read_json(path), str(path))
    payload = wrapper.get("payload")
    if isinstance(payload, str):
        provenance = _mapping(wrapper.get("provenance"), f"{path.name}:provenance")
        recorded = provenance.get("payload_sha256")
        actual = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if recorded != actual:
            raise ScenarioError(
                f"{path.name}: the payload's sha256 is {actual}, and its provenance records "
                f"{recorded}; a recording that does not match its own hash is refused"
            )
        try:
            return json.loads(payload, parse_float=Decimal)
        except json.JSONDecodeError as exc:
            raise ScenarioError(f"{path.name}: the captured payload is not JSON: {exc}") from exc
    raise ScenarioError(f"{path.name} carries no captured `payload` text")


def _v2_pairs(payload: Any, where: str) -> Sequence[Mapping[str, Any]]:
    """The `pairs` list of a v2 `instrument` snapshot frame."""
    data = payload.get("data") if isinstance(payload, Mapping) else None
    pairs = data.get("pairs") if isinstance(data, Mapping) else None
    if not isinstance(pairs, Sequence) or isinstance(pairs, str) or not pairs:
        raise ScenarioError(f"{where} carries no v2 instrument `pairs` list")
    return [_mapping(item, f"{where}:pairs[]") for item in pairs]


def load_pair_rules(
    instrument_path: Path,
    pair_names_path: Path,
    *,
    asset_pairs_path: Path | None = None,
    relative_to: Path | None = None,
) -> RecordedRules:
    """Every recorded pair's rules, through the v2 field names, keyed by v2 symbol.

    The v2 names map one to one onto `PairRule`'s: `qty_min` is `ordermin`, `cost_min`
    is `costmin`, `qty_precision` is `lot_decimals` and `price_precision` is
    `pair_decimals`. Spec 127's name join checked every one of them equal to REST's on
    all 1,450 pairs, so reading the v2 form changes no value and fixes only the keying.
    A pair missing any of them is refused by name, never defaulted.

    The archive names come from spec 127's recorded join (`pair_names`), whose asset
    aliases were derived from Kraken's two answers rather than written by hand. The REST
    `AssetPairs` capture is not parsed here: it is hashed into the description, as the
    source the join was derived from.
    """
    rules: dict[str, PairRule] = {}
    statuses: dict[str, int] = {}
    where = instrument_path.name
    for item in _v2_pairs(_captured_payload(instrument_path), where):
        symbol = str(item.get("symbol", "")).strip()
        if not symbol:
            raise ScenarioError(f"{where}: a pair carries no symbol")
        if symbol in rules:
            raise ScenarioError(f"{where}: {symbol} is listed twice")
        try:
            rules[symbol] = PairRule(
                pair=symbol,
                base=str(item["base"]),
                quote=str(item["quote"]),
                ordermin=_decimal(item["qty_min"], f"{where}:{symbol}:qty_min"),
                costmin=_decimal(item["cost_min"], f"{where}:{symbol}:cost_min"),
                tick_size=_decimal(item["tick_size"], f"{where}:{symbol}:tick_size"),
                lot_decimals=int(item["qty_precision"]),
                pair_decimals=int(item["price_precision"]),
            )
        except KeyError as missing:
            raise ScenarioError(f"{where}: {symbol} has no {missing}") from missing
        except ValueError as invalid:
            raise ScenarioError(f"{where}: {symbol} is refused: {invalid}") from invalid
        status = str(item.get("status", "unstated"))
        statuses[status] = statuses.get(status, 0) + 1

    names_where = pair_names_path.name
    joined = _mapping(
        _mapping(_read_json(pair_names_path), names_where).get("pairs"), f"{names_where}:pairs"
    )
    archive: dict[str, str] = {}
    for altname, entry in joined.items():
        v2_symbol = _mapping(entry, f"{names_where}:{altname}").get("v2_symbol")
        if not isinstance(v2_symbol, str) or v2_symbol not in rules:
            raise ScenarioError(
                f"{names_where}: {altname} joins to {v2_symbol!r}, which the instrument "
                "snapshot does not list; the two recordings disagree"
            )
        archive[str(altname)] = v2_symbol

    sources = [instrument_path, pair_names_path]
    if asset_pairs_path is not None:
        sources.append(asset_pairs_path)
    return RecordedRules(
        rules=rules,
        archive_symbols=archive,
        status_counts=dict(sorted(statuses.items())),
        files=tuple(
            {"file": _relative(source, relative_to), "sha256": sha256_file(source)}
            for source in sources
        ),
    )

# --------------------------------------------------------------------------- #
# The spread and depth table, and the book built from it
# --------------------------------------------------------------------------- #

#: Levels a side of the synthetic book, fixed by spec 129 step 3. Also the depth the
#: stream is subscribed at (`order_book.depth` may not exceed it), so engine 9 and the
#: paper broker walk the whole declared book and never past it.
BOOK_LEVELS: Final = 10

_BPS: Final = Decimal(10_000)


@dataclass(frozen=True)
class Bucket:
    """One row of the declared table. Bounds on trailing 24-hour dollar volume."""

    name: str
    lower_usd: Decimal
    upper_usd: Decimal | None
    spread_bps: Decimal
    depth_bps: Decimal
    """Distance from the mid at which the book's cumulative notional reaches the
    table's `depth_notional_usd`."""
    values_from: str | None = None
    """The bucket whose values this one takes, when the table maps it (`>$10M`)."""

    def contains(self, volume_usd: Decimal) -> bool:
        return volume_usd >= self.lower_usd and (
            self.upper_usd is None or volume_usd < self.upper_usd
        )

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "lower_usd": money_text(self.lower_usd),
            "upper_usd": None if self.upper_usd is None else money_text(self.upper_usd),
            "spread_bps": money_text(self.spread_bps),
            "depth_bps": money_text(self.depth_bps),
            "values_from": self.values_from,
        }


@dataclass(frozen=True)
class SpreadTable:
    file: str
    sha256: str
    buckets: tuple[Bucket, ...]
    depth_notional_usd: Decimal

    def bucket_for(self, volume_usd: Decimal) -> Bucket:
        for bucket in self.buckets:
            if bucket.contains(volume_usd):
                return bucket
        raise ScenarioError(
            f"no bucket holds a trailing volume of {volume_usd}; the table must cover "
            "every non-negative volume, and a gap is never filled from a neighbour"
        )

    def describe(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "sha256": self.sha256,
            "depth_notional_usd": money_text(self.depth_notional_usd),
            "levels_per_side": BOOK_LEVELS,
            "buckets": [bucket.describe() for bucket in self.buckets],
        }


#: The notional the table's depth is measured to, and so the book's total per side. Spec
#: 129 step 3 names it ("cumulative notional reaches $10,000"), and spec 130's column is
#: named for it; :func:`load_spread_table` refuses a table whose depth column says otherwise.
DEPTH_NOTIONAL_USD: Final = Decimal(10_000)

#: Spec 130's column names. The depth is the bid side's distance **from the mid** to the
#: $10,000 mark, which is what puts the book's tenth level there.
_SPREAD_COLUMN: Final = "spread_bps"
_DEPTH_COLUMN: Final = "depth_bid_bps_to_10k_from_mid"


def load_spread_table(path: Path, *, relative_to: Path | None = None) -> SpreadTable:
    """Spec 130's declared table, checked to cover `[0, inf)` without a gap or an overlap.

    Each bucket's **median** is the declared value. Its quartiles are the declared
    uncertainty and are carried into the description, never served. A bucket written as
    `mapped_to` another (the `>$10M` row, which the recording could not fill) takes that
    bucket's values, and the description says which. Numbers are read exactly as the
    fixture writes them: a median published as `30.395200000000003` is served as that
    decimal, and nothing here rounds it to what it probably meant.

    A table that left a volume uncovered would force the client to pick a neighbour for
    it, which is the choice the ruling took away from code. A bucket whose depth sits
    inside its own half-spread describes a book that cannot exist, and is refused.
    """
    payload = _mapping(_read_json(path), str(path))
    where = path.name
    raw = payload.get("buckets")
    if not isinstance(raw, Sequence) or isinstance(raw, str) or not raw:
        raise ScenarioError(f"{where} has no buckets")
    rows = {
        str(_mapping(item, f"{where}:buckets[{index}]").get("bucket", f"#{index}")): item
        for index, item in enumerate(raw)
    }
    if len(rows) != len(raw):
        raise ScenarioError(f"{where} names a bucket twice")
    buckets: list[Bucket] = []
    for name, row in rows.items():
        mapped = row.get("mapped_to")
        source = rows.get(str(mapped)) if mapped is not None else row
        if source is None or (mapped is not None and source.get("mapped_to") is not None):
            raise ScenarioError(f"{where}:{name} is mapped to {mapped!r}, which has no values")
        spread = _mapping(source.get(_SPREAD_COLUMN), f"{where}:{name}:{_SPREAD_COLUMN}")
        depth = _mapping(source.get(_DEPTH_COLUMN), f"{where}:{name}:{_DEPTH_COLUMN}")
        upper = row.get("usd_day_below")
        bucket = Bucket(
            name=name,
            lower_usd=_decimal(row.get("usd_day_from"), f"{where}:{name}:usd_day_from"),
            upper_usd=None if upper is None else _decimal(upper, f"{where}:{name}:usd_day_below"),
            spread_bps=_decimal(spread.get("median"), f"{where}:{name}:spread median"),
            depth_bps=_decimal(depth.get("median"), f"{where}:{name}:depth median"),
            values_from=None if mapped is None else str(mapped),
        )
        if bucket.spread_bps <= 0 or bucket.depth_bps <= 0:
            raise ScenarioError(f"{where}:{name}: spread and depth must be positive")
        if bucket.depth_bps < bucket.spread_bps / 2:
            raise ScenarioError(
                f"{where}:{name}: depth {bucket.depth_bps} bps is inside the half-spread "
                f"{bucket.spread_bps / 2} bps, which no book can have"
            )
        buckets.append(bucket)
    buckets.sort(key=lambda bucket: bucket.lower_usd)
    if buckets[0].lower_usd != 0:
        raise ScenarioError(f"{where}: the first bucket starts at {buckets[0].lower_usd}, not 0")
    for below, above in itertools.pairwise(buckets):
        if below.upper_usd is None or below.upper_usd != above.lower_usd:
            raise ScenarioError(f"{where}: {below.name} and {above.name} leave a gap or overlap")
    if buckets[-1].upper_usd is not None:
        raise ScenarioError(f"{where}: the last bucket must be open above")
    return SpreadTable(
        file=_relative(path, relative_to),
        sha256=sha256_file(path),
        buckets=tuple(buckets),
        depth_notional_usd=DEPTH_NOTIONAL_USD,
    )


def _covering_qty(notional: Decimal, price: Decimal) -> Decimal:
    """`notional / price`, rounded up, so `price x qty` is never below the level's share.

    `notional / price` does not terminate, and rounded to nearest it leaves some levels a
    part in 1e28 short of their share. Engine 9 then finds the fifth level short of the
    last dollars of a $5,000 walk and takes a speck of the sixth: the fill price moves in
    the 26th digit, but `levels_consumed` reports a level the declared book never meant
    to be reached, and a walk of the full declared notional would read as too thin.
    Rounding up closes both. It adds at most one unit in the 28th digit of a quantity.
    """
    with localcontext() as ctx:
        ctx.rounding = ROUND_CEILING
        return notional / price


@dataclass(frozen=True)
class SyntheticBook:
    """A declared book around one mid. Levels best first on each side."""

    bids: tuple[tuple[Decimal, Decimal], ...]
    asks: tuple[tuple[Decimal, Decimal], ...]


def synthetic_book(*, mid: Decimal, bucket: Bucket, depth_notional_usd: Decimal) -> SyntheticBook:
    """Ten levels a side, the first at the declared half-spread and the tenth at the
    declared depth, evenly spaced between, each holding an equal share of the notional.

    So the book's top is exactly the declared spread around `mid`, and its cumulative
    notional reaches `depth_notional_usd` at the declared depth. Quantity is the level's
    notional over its own price, in base units, rounded **up** in the last of 28 digits
    (see :func:`_covering_qty`). Nothing is rounded to the pair's
    tick: rounding would widen the spread on coarse-tick pairs past the declared value,
    and the ruling applies the table's value uniformly.
    """
    half = bucket.spread_bps / _BPS / 2
    far = bucket.depth_bps / _BPS
    step = (far - half) / (BOOK_LEVELS - 1)
    share = depth_notional_usd / BOOK_LEVELS
    bids: list[tuple[Decimal, Decimal]] = []
    asks: list[tuple[Decimal, Decimal]] = []
    for level in range(BOOK_LEVELS):
        distance = half + step * level
        bid = mid * (1 - distance)
        ask = mid * (1 + distance)
        if bid <= 0:
            raise ScenarioError(f"a declared depth of {bucket.depth_bps} bps puts a bid at or below zero")
        bids.append((bid, _covering_qty(share, bid)))
        asks.append((ask, _covering_qty(share, ask)))
    return SyntheticBook(bids=tuple(bids), asks=tuple(asks))


# --------------------------------------------------------------------------- #
# The whole scenario and its identity
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReplayScenario:
    """Everything a replay is priced on, and the one digest spec 134 records.

    `extras` is what the driver adds and the client cannot know: the window, the
    ranking, whether the run is the alphabetical baseline. They are part of the
    description and therefore of the digest, so two runs that differ only in their
    ranking can never share an identity.
    """

    rules: RecordedRules
    table: SpreadTable
    fee: FeeScenario
    partitions: Mapping[str, Any]
    extras: Mapping[str, Any]

    def description(self) -> dict[str, Any]:
        return {
            "kind": "acsoe-replay-scenario",
            "declared": DECLARED_STATEMENT,
            "pair_rules": {
                "files": list(self.rules.files),
                "pairs": len(self.rules.rules),
                "status_counts": dict(self.rules.status_counts),
                "archive_pairs_mapped": len(self.rules.archive_symbols),
            },
            "spread_book_table": self.table.describe(),
            "fee": self.fee.describe(),
            "partitions": dict(self.partitions),
            **{key: self.extras[key] for key in sorted(self.extras)},
        }

    @property
    def description_json(self) -> str:
        return canonical_json(self.description())

    @property
    def digest(self) -> str:
        """sha256 over the canonical description, so the two can never disagree."""
        return hashlib.sha256(self.description_json.encode("ascii")).hexdigest()
