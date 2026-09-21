#!/usr/bin/env python
"""Record a genuine Kraken ``AssetPairs`` for the Phase 7 replay, once. Spec 127.

    python scripts/record_asset_pairs.py --fetch            # one fetch of each, then stop
    python scripts/record_asset_pairs.py --report 2026-09-19   # offline: checks and counts
    python scripts/record_asset_pairs.py --names 2026-09-19    # offline: the derived name map

The only ``AssetPairs`` in the repository before this was `tests/fixtures/kraken/
asset_pairs.json`, invented Phase 0 data. The replay of 2024 needs real pair rules, and
the findings need a **measured** survivorship figure: how many archive pairs that traded
in the window are missing from Kraken's pair list today. That invented file is not
replaced. The fake exchange and every criterion that reads it keep reading it. This
records a second file with a different job.

## What it fetches, and how

**``GET /0/public/AssetPairs``, once, through the existing client.** It calls
`KrakenRestClient.asset_pairs()` itself, with the shared limiter, the envelope check and
`map_asset_pairs`. The transport is the client's own `HttpxTransport`, wrapped so that
the response body is kept exactly as received. So the fixture holds the bytes Kraken
sent, and the same bytes went through the live parser on the way in. A body the live
parser rejects is not written.

**The WebSocket v2 ``instrument`` snapshot, once.** The spec asks for the REST call only,
so this second fetch is a how-decision recorded in the build log, marked contestable.
Why it is needed:

- REST keys each pair by its REST name (``XXBTZUSD``, quote ``ZUSD``).
- The engines key pairs by the v2 symbol (``BTC/USD``).
- REST's own ``wsname`` (``XBT/USD``) is neither.

The snapshot is Kraken's own statement of the v2 symbol and its rules. So the replay
can key rules by v2 symbol, and check every REST value against it, without a
hand-written alias table. It is public, one subscribe, one frame and an unsubscribe,
on the URL `clients/kraken/ws.py` already uses.

Each fixture is ``{"provenance": {...}, "payload": "<the body, as text>"}``. The payload
is kept as a string rather than parsed, so ``sha256(payload)`` re-checks against the
digest taken as it arrived, byte for byte. The provenance carries:

- the URL;
- the capture time from the injected clock;
- the client version (the package version, and the sha256 of the client source that
  made the call);
- the sha256.

## What it reports, offline

Four things from the committed files, and no network:

1. **Every pair parses through `map_asset_pairs`** with ``ordermin``, ``costmin`` and a
   tick size. A pair it drops is named.
2. **REST against v2.** Every REST pair is joined to its v2 symbol through
   ``wsname``. Each rule the engines read is compared: ``ordermin`` with ``qty_min``,
   ``costmin`` with ``cost_min``, ``tick_size``, ``pair_decimals`` with
   ``price_precision``, ``lot_decimals`` with ``qty_precision``, and ``status``. The
   join needs an asset map where REST and v2 spell an asset differently. That map is
   **derived from the two recorded files**, from the pairs where the join is unambiguous,
   and never hand-written.
3. **Survivorship.** The archive's USD pairs (`data/historical/*USD_15.csv`) with at
   least one bar inside the window, and among those, the ones no ``AssetPairs`` entry
   names (by ``altname``, the spelling the archive uses). Reported for the Phase 7
   window (folds 379 to 404) and, labelled, for the 1.5-year window (folds 326 to 404).
4. **The tick-size caveat.** The 15 pairs that
   `docs/dataset/phase-7-recon-2026-09-19/outputs/q_ticks.out` found on a finer grid in
   2026, against the recorded ``pair_decimals``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

import acsoe
from acsoe.clients.kraken import rest as rest_module
from acsoe.clients.kraken.limiter import RateLimiter
from acsoe.clients.kraken.rest import (
    ASSET_PAIRS_PATH,
    KRAKEN_REST_URL,
    HttpResponse,
    HttpTransport,
    HttpxTransport,
    KrakenRestClient,
    engine_pair_names,
    map_asset_pairs,
)
from acsoe.clients.kraken.ws import KRAKEN_WS_V2_URL
from acsoe.platform.clock import Clock, SystemClock
from acsoe.platform.config import Config, load_config

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
FIXTURE_DIR: Final = Path("tests") / "fixtures" / "kraken"
ASSET_PAIRS_STEM: Final = "asset_pairs_recorded"
INSTRUMENT_STEM: Final = "instrument_recorded"
NAMES_STEM: Final = "pair_names_recorded"
HISTORICAL_DIR: Final = Path("data") / "historical"
Q_TICKS: Final = (
    Path("docs") / "dataset" / "phase-7-recon-2026-09-19" / "outputs" / "q_ticks.out"
)

#: The Phase 7 window, folds 379 to 404, and the 1.5-year window, folds 326 to 404
#: (`phase-7-findings.md` §0 and §R.6). Half-open, UTC.
WINDOWS: Final = {
    "phase_7_six_months": (datetime(2024, 7, 6, tzinfo=UTC), datetime(2025, 1, 4, tzinfo=UTC)),
    "one_and_a_half_years": (
        datetime(2023, 7, 1, tzinfo=UTC),
        datetime(2025, 1, 4, tzinfo=UTC),
    ),
}

#: How long the instrument subscription may take to deliver its snapshot.
INSTRUMENT_TIMEOUT_S: Final = 30.0


class RecordError(RuntimeError):
    """A recording that must not be written, or a fixture that does not check out."""


# --------------------------------------------------------------------------- #
# Capture
# --------------------------------------------------------------------------- #


class Captured:
    """One response, as received. Not a ``@dataclass``: the tests load this script by
    path, and a dataclass in a module absent from ``sys.modules`` fails at import (the
    same note as `build_ohlcvt.ArchivePair`)."""

    __slots__ = ("body", "captured_at", "url")

    def __init__(self, *, url: str, body: bytes, captured_at: datetime) -> None:
        self.url = url
        self.body = body
        self.captured_at = captured_at


class RecordingTransport:
    """The client's transport, wrapped to keep every response body as received.

    It is a seam, not a second HTTP stack: every request still goes through the
    wrapped transport, and the client above it still does the limiting, the envelope
    and the mapping.
    """

    def __init__(self, inner: HttpTransport) -> None:
        self._inner = inner
        self.responses: list[tuple[str, HttpResponse]] = []

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        content: bytes | None,
        timeout_s: float,
    ) -> HttpResponse:
        response = await self._inner.request(
            method, url, headers=headers, content=content, timeout_s=timeout_s
        )
        self.responses.append((url, response))
        return response


def client_version() -> dict[str, str]:
    """The package version, and a digest of the client source that made the call."""
    source = Path(rest_module.__file__)
    return {
        "acsoe": acsoe.__version__,
        "clients/kraken/rest.py sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


async def capture_asset_pairs(
    config: Config, *, clock: Clock, transport: HttpTransport
) -> Captured:
    """One ``AssetPairs`` fetch through `KrakenRestClient`. The body, as received.

    Raises if the live parser rejects it, so a body the replay could not read is never
    written.
    """
    recorder = RecordingTransport(transport)
    limiter = RateLimiter(
        capacity=config.kraken.rest_capacity,
        refill_per_second=float(config.kraken.rest_refill_per_s),
    )
    client = KrakenRestClient.from_config(
        config, clock=clock, limiter=limiter, transport=recorder, credentials=None
    )
    await client.asset_pairs()
    if len(recorder.responses) != 1:
        raise RecordError(f"expected one request, saw {len(recorder.responses)}")
    url, response = recorder.responses[0]
    if url != f"{KRAKEN_REST_URL}{ASSET_PAIRS_PATH}":
        raise RecordError(f"the client asked {url}, not AssetPairs")
    return Captured(url=url, body=response.body, captured_at=clock.now())


#: ``(url) -> (send, recv, close)`` for one WebSocket, so a test can script the frames.
Connector = Callable[[str], Awaitable[Any]]


async def capture_instrument(
    *, clock: Clock, url: str = KRAKEN_WS_V2_URL, connector: Connector | None = None,
    timeout_s: float = INSTRUMENT_TIMEOUT_S,
) -> Captured:
    """One v2 ``instrument`` snapshot frame, verbatim. Subscribe, read, unsubscribe."""
    if connector is None:
        from websockets.asyncio.client import connect

        async def connector(target: str) -> Any:
            return await connect(target, max_size=None)

    socket = await connector(url)
    try:
        await socket.send(json.dumps({"method": "subscribe", "params": {"channel": "instrument"}}))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise RecordError("no instrument snapshot before the deadline")
            frame = await asyncio.wait_for(socket.recv(), timeout=remaining)
            raw = frame.encode("utf-8") if isinstance(frame, str) else bytes(frame)
            payload = json.loads(raw)
            if (
                isinstance(payload, dict)
                and payload.get("channel") == "instrument"
                and payload.get("type") == "snapshot"
            ):
                captured = Captured(url=url, body=raw, captured_at=clock.now())
                break
        await socket.send(
            json.dumps({"method": "unsubscribe", "params": {"channel": "instrument"}})
        )
    finally:
        await socket.close()
    return captured


def fixture_document(captured: Captured, *, request: str) -> dict[str, Any]:
    try:
        text = captured.body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RecordError("the body is not UTF-8, so it cannot be kept verbatim as text") from exc
    return {
        "provenance": {
            "url": captured.url,
            "request": request,
            "captured_at": captured.captured_at.isoformat().replace("+00:00", "Z"),
            "client_version": client_version(),
            "payload_sha256": hashlib.sha256(captured.body).hexdigest(),
            "payload_bytes": len(captured.body),
            "recorded_by": "scripts/record_asset_pairs.py",
            "note": (
                "Recorded once from Kraken's public API for the Phase 7 replay. The "
                "payload is the response body exactly as received, kept as text. These "
                "are 2026 rules applied to a 2023-24 window; pairs delisted since are "
                "absent, which is the survivorship the findings name."
            ),
        },
        "payload": text,
    }


def fixture_path(root: Path, stem: str, captured_at: datetime) -> Path:
    return root / FIXTURE_DIR / f"{stem}_{captured_at.strftime('%Y-%m-%d')}.json"


def write_fixture(path: Path, document: Mapping[str, Any]) -> None:
    """Written once, as bytes: `tests/fixtures/` is ``-text`` and nothing may convert it."""
    if path.exists():
        raise RecordError(f"{path} already exists; a recording is written once")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(document, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))


# --------------------------------------------------------------------------- #
# Reading a fixture back
# --------------------------------------------------------------------------- #


def load_payload(path: Path) -> tuple[dict[str, Any], Any]:
    """The provenance and the parsed payload, after the payload's digest is re-checked."""
    document = json.loads(path.read_bytes())
    provenance = document["provenance"]
    body = str(document["payload"]).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    if digest != provenance["payload_sha256"]:
        raise RecordError(
            f"{path}: the payload's sha256 is {digest}, not the recorded "
            f"{provenance['payload_sha256']}"
        )
    return provenance, json.loads(body)


def asset_pairs_result(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("error"):
        raise RecordError("the AssetPairs payload is not a successful Kraken envelope")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RecordError("the AssetPairs payload carries no result mapping")
    return result


def instrument_pairs(payload: Any) -> dict[str, dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    pairs = data.get("pairs") if isinstance(data, dict) else None
    if not isinstance(pairs, list):
        raise RecordError("the instrument payload carries no pair list")
    return {str(item["symbol"]): item for item in pairs if isinstance(item, dict)}


def check_rules(result: Mapping[str, Any]) -> dict[str, Any]:
    """Every pair through the live parser. Returns counts, and names the pairs it drops.

    The drops are named by their **REST key**, which is what a reader of this report holds;
    since F3 the snapshot is keyed by the v2 symbol instead, so the two key spaces are joined
    through the client's own :func:`engine_pair_names` rather than subtracted directly. A pair
    the client cannot name is reported as dropped, because it is.
    """
    snapshot = map_asset_pairs(result, fetched_at=0)
    names = engine_pair_names(result)
    dropped = sorted(key for key in map(str, result) if names.get(key) not in snapshot.pairs)
    return {"pairs_in_payload": len(result), "parsed": len(snapshot.pairs), "dropped": dropped}


# --------------------------------------------------------------------------- #
# REST against v2
# --------------------------------------------------------------------------- #


def derive_asset_map(
    rest: Mapping[str, Any], v2: Mapping[str, Mapping[str, Any]]
) -> dict[str, str]:
    """REST asset spelling to v2 asset spelling, from the two recorded files only.

    A REST pair's ``wsname`` is ``BASE/QUOTE`` in REST spelling. Where that string is
    not a v2 symbol, the pair is matched against the v2 symbols **no REST ``wsname``
    names**. A candidate must share one side of the pair literally and carry identical
    rules. Its other side is then a vote for how the unshared asset is spelled in v2. An
    alias is kept only when every vote for that asset agrees. Every alias therefore comes
    from Kraken's own two answers, and one the evidence does not support is left out
    rather than guessed.
    """
    named = {str(entry.get("wsname", "")) for entry in rest.values()}
    unclaimed: dict[tuple[str, ...], list[str]] = {}
    for symbol, item in v2.items():
        if symbol not in named:
            unclaimed.setdefault(_v2_key(item), []).append(symbol)
    votes: dict[str, set[str]] = {}
    for entry in rest.values():
        wsname = str(entry.get("wsname", ""))
        if "/" not in wsname or wsname in v2:
            continue
        rest_base, rest_quote = wsname.split("/", 1)
        for candidate in unclaimed.get(_rest_key(entry), []):
            v2_base, v2_quote = candidate.split("/", 1)
            if v2_quote == rest_quote and v2_base != rest_base:
                votes.setdefault(rest_base, set()).add(v2_base)
            elif v2_base == rest_base and v2_quote != rest_quote:
                votes.setdefault(rest_quote, set()).add(v2_quote)
    return {asset: next(iter(names)) for asset, names in sorted(votes.items()) if len(names) == 1}


def _same(value: Any) -> str:
    """A number's value as text, so ``50`` and ``50.0`` compare equal."""
    return str(Decimal(str(value)).normalize())


def _rest_key(entry: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        _same(entry.get("ordermin")),
        _same(entry.get("costmin")),
        _same(entry.get("tick_size")),
        str(entry.get("pair_decimals")),
        str(entry.get("lot_decimals")),
    )


def _v2_key(item: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        _same(item.get("qty_min")),
        _same(item.get("cost_min")),
        _same(item.get("tick_size")),
        str(item.get("price_precision")),
        str(item.get("qty_precision")),
    )


def v2_symbol(entry: Mapping[str, Any], asset_map: Mapping[str, str]) -> str | None:
    wsname = str(entry.get("wsname", ""))
    if "/" not in wsname:
        return None
    base, quote = wsname.split("/", 1)
    return f"{asset_map.get(base, base)}/{asset_map.get(quote, quote)}"


FIELD_PAIRS: Final = (
    ("ordermin", "qty_min", "decimal"),
    ("costmin", "cost_min", "decimal"),
    ("tick_size", "tick_size", "decimal"),
    ("pair_decimals", "price_precision", "int"),
    ("lot_decimals", "qty_precision", "int"),
    ("status", "status", "text"),
)


def compare_rest_v2(
    rest: Mapping[str, Any], v2: Mapping[str, Mapping[str, Any]], asset_map: Mapping[str, str]
) -> dict[str, Any]:
    """Join every REST pair to its v2 symbol and compare the rules the engines read."""
    matched: dict[str, str] = {}
    unmatched: list[str] = []
    mismatches: list[str] = []
    for name, entry in sorted(rest.items()):
        symbol = v2_symbol(entry, asset_map)
        if symbol is None or symbol not in v2:
            unmatched.append(name)
            continue
        matched[name] = symbol
        item = v2[symbol]
        for rest_field, v2_field, kind in FIELD_PAIRS:
            mine, theirs = entry.get(rest_field), item.get(v2_field)
            same = (
                Decimal(str(mine)) == Decimal(str(theirs))
                if kind == "decimal"
                else str(mine) == str(theirs)
            )
            if not same:
                mismatches.append(f"{name} {rest_field}={mine!r} vs {symbol} {v2_field}={theirs!r}")
    return {
        "asset_map": dict(asset_map),
        "matched": len(matched),
        "unmatched": unmatched,
        "v2_without_rest": sorted(set(v2) - set(matched.values())),
        "mismatches": mismatches,
        "names": matched,
    }


# --------------------------------------------------------------------------- #
# Survivorship and the tick caveat
# --------------------------------------------------------------------------- #


def archive_pairs_trading(historical: Path, *, start: int, end: int) -> list[str]:
    """Archive USD pairs with at least one bar in ``[start, end)``, from ``*USD_15.csv``."""
    trading: list[str] = []
    for path in sorted(historical.glob("*USD_15.csv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            for line in handle:
                stamp = int(line.split(",", 1)[0])
                if start <= stamp < end:
                    trading.append(path.name[: -len("_15.csv")])
                    break
    return trading


def survivorship(rest: Mapping[str, Any], historical: Path) -> dict[str, Any]:
    altnames = {str(entry.get("altname")): name for name, entry in rest.items()}
    report: dict[str, Any] = {}
    for label, (start, end) in WINDOWS.items():
        trading = archive_pairs_trading(
            historical, start=int(start.timestamp()), end=int(end.timestamp())
        )
        absent = [pair for pair in trading if pair not in altnames]
        not_online = sorted(
            f"{pair} ({rest[altnames[pair]].get('status')})"
            for pair in trading
            if pair in altnames and rest[altnames[pair]].get("status") != "online"
        )
        report[label] = {
            "window": f"{start.isoformat()} to {end.isoformat()}",
            "archive_usd_pairs_trading": len(trading),
            "absent_from_asset_pairs": len(absent),
            "absent": absent,
            "present_but_not_online": not_online,
        }
    return report


def finer_grid_pairs(q_ticks: Path) -> dict[str, tuple[int, int]]:
    """The pairs `q_ticks.out` found finer in 2026: archive name to (window d, 2026 d)."""
    found: dict[str, tuple[int, int]] = {}
    for line in q_ticks.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text.startswith("differs: ("):
            continue
        fields = [part.strip(" ()'") for part in text[len("differs: (") :].split(",")]
        found[fields[0]] = (int(fields[2]), int(fields[4]))
    return found


def tick_check(rest: Mapping[str, Any], q_ticks: Path) -> list[dict[str, Any]]:
    altnames = {str(entry.get("altname")): entry for entry in rest.values()}
    rows: list[dict[str, Any]] = []
    for pair, (window_d, recent_d) in sorted(finer_grid_pairs(q_ticks).items()):
        entry = altnames.get(pair)
        recorded = None if entry is None else int(entry["pair_decimals"])
        rows.append(
            {
                "pair": pair,
                "window_grid_decimals": window_d,
                "grid_2026_decimals": recent_d,
                "recorded_pair_decimals": recorded,
                "agrees_with_2026_grid": recorded == recent_d,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def fetch(root: Path, *, clock: Clock, config: Config) -> list[Path]:
    rest_captured = asyncio.run(
        capture_asset_pairs(config, clock=clock, transport=HttpxTransport())
    )
    ws_captured = asyncio.run(capture_instrument(clock=clock))
    written = []
    for stem, captured, request in (
        (ASSET_PAIRS_STEM, rest_captured, f"GET {ASSET_PAIRS_PATH}"),
        (INSTRUMENT_STEM, ws_captured, 'subscribe {"channel": "instrument"}, first snapshot frame'),
    ):
        path = fixture_path(root, stem, captured.captured_at)
        write_fixture(path, fixture_document(captured, request=request))
        written.append(path)
    return written


def names_document(root: Path, day: str) -> dict[str, Any]:
    """The derived name map: archive name, REST key and v2 symbol, one row per REST pair.

    Derived, not recorded: it is computed from the two recorded files, and says so. It is
    written only when every REST pair joins to a v2 symbol and every compared rule agrees.
    A map with a hole or a disagreement in it would hand the replay rules for the wrong
    pair.
    """
    rest_path = root / FIXTURE_DIR / f"{ASSET_PAIRS_STEM}_{day}.json"
    v2_path = root / FIXTURE_DIR / f"{INSTRUMENT_STEM}_{day}.json"
    rest_provenance, rest_payload = load_payload(rest_path)
    v2_provenance, v2_payload = load_payload(v2_path)
    rest = asset_pairs_result(rest_payload)
    v2 = instrument_pairs(v2_payload)
    asset_map = derive_asset_map(rest, v2)
    comparison = compare_rest_v2(rest, v2, asset_map)
    if comparison["unmatched"] or comparison["v2_without_rest"] or comparison["mismatches"]:
        raise RecordError(
            "REST and v2 do not join one to one with agreeing rules: "
            f"unmatched {comparison['unmatched'][:10]}, v2 without REST "
            f"{comparison['v2_without_rest'][:10]}, mismatches {comparison['mismatches'][:10]}"
        )
    pairs = {
        str(rest[name].get("altname")): {"rest_key": name, "v2_symbol": symbol}
        for name, symbol in comparison["names"].items()
    }
    return {
        "provenance": {
            "derived_by": "scripts/record_asset_pairs.py --names",
            "derived_from": {
                rest_path.name: rest_provenance["payload_sha256"],
                v2_path.name: v2_provenance["payload_sha256"],
            },
            "asset_map": asset_map,
            "asset_map_basis": (
                "derived from the two recorded files: an asset is renamed only where a REST "
                "pair's wsname is not a v2 symbol, a v2 symbol no wsname names shares its "
                "other side and every rule, and every such vote for that asset agrees"
            ),
            "joined": comparison["matched"],
            "rules_compared": [f"{a} = {b}" for a, b, _ in FIELD_PAIRS],
            "rule_mismatches": 0,
            "key": "altname, which is the spelling the time-and-sales archive's file names use",
        },
        "pairs": dict(sorted(pairs.items())),
    }


def report(root: Path, day: str) -> dict[str, Any]:
    _, rest_payload = load_payload(root / FIXTURE_DIR / f"{ASSET_PAIRS_STEM}_{day}.json")
    _, v2_payload = load_payload(root / FIXTURE_DIR / f"{INSTRUMENT_STEM}_{day}.json")
    rest = asset_pairs_result(rest_payload)
    v2 = instrument_pairs(v2_payload)
    asset_map = derive_asset_map(rest, v2)
    comparison = compare_rest_v2(rest, v2, asset_map)
    comparison.pop("names")
    return {
        "rules": check_rules(rest),
        "rest_against_v2": comparison,
        "survivorship": survivorship(rest, root / HISTORICAL_DIR),
        "tick_caveat": tick_check(rest, root / Q_TICKS),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="record_asset_pairs.py")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch", action="store_true", help="fetch once and write the fixtures")
    mode.add_argument("--report", metavar="YYYY-MM-DD", help="check a recorded pair, offline")
    mode.add_argument(
        "--names", metavar="YYYY-MM-DD", help="write the derived name map beside them, offline"
    )
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)
    if args.fetch:
        config = load_config(Path(args.config) if args.config else None, load_env=False)
        for path in fetch(REPO_ROOT, clock=SystemClock(), config=config):
            print(f"wrote {path}", file=sys.stderr)
        return 0
    if args.names:
        target = REPO_ROOT / FIXTURE_DIR / f"{NAMES_STEM}_{args.names}.json"
        write_fixture(target, names_document(REPO_ROOT, args.names))
        print(f"wrote {target}", file=sys.stderr)
        return 0
    print(json.dumps(report(REPO_ROOT, args.report), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
