"""Phase 7 scoping, Q6 step 1. Read-only over data/summaries/; writes one parquet to the scratchpad.

Reduces the recorder's per-minute summaries to 15-minute pair-bars carrying the spread (from the
minute p50s) beside only what the OHLCVT archive could also give for the same bar: quote volume,
trade count, and trade OHLC. rv from the book mid is NOT carried: the archive has no mid.
"""
import sys
from collections import defaultdict
from pathlib import Path

import orjson
import polars as pl

sys.stdout.reconfigure(encoding="utf-8")
SUMMARIES = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE\data\summaries")
OUT = Path(__file__).parent / "spread_minutes.parquet"

cols = defaultdict(list)
kinds = defaultdict(int)
for path in sorted(SUMMARIES.glob("summary*.jsonl")):
    n = 0
    with path.open("rb") as handle:
        for line in handle:
            try:
                d = orjson.loads(line)
            except orjson.JSONDecodeError:
                kinds["unparseable"] += 1
                continue
            kinds[d.get("kind")] += 1
            if d.get("kind") != "summary":
                continue
            pair = d.get("pair") or ""
            if not pair.endswith("/USD"):
                continue
            sp = d.get("spread_bps") or [None, None, None]
            cols["pair"].append(pair)
            cols["minute"].append(d["minute"])
            cols["p25"].append(sp[0])
            cols["p50"].append(sp[1])
            cols["p75"].append(sp[2])
            cols["samples"].append(d.get("samples", 0))
            cols["trades"].append(d.get("trades", 0))
            cols["volume"].append(d.get("volume"))
            cols["quote_volume"].append(d.get("quote_volume"))
            cols["open"].append(d.get("open"))
            cols["high"].append(d.get("high"))
            cols["low"].append(d.get("low"))
            cols["close"].append(d.get("close"))
            cols["mid"].append(d.get("mid"))
            cols["clean"].append(bool(d.get("clean")))
            n += 1
    print(path.name, n, flush=True)
print(dict(kinds))
frame = pl.DataFrame(cols, schema_overrides={k: pl.Float64 for k in
                     ("p25", "p50", "p75", "volume", "quote_volume", "open", "high", "low", "close", "mid")})
frame = frame.with_columns(pl.col("minute").str.to_datetime(time_zone="UTC"))
frame.write_parquet(OUT)
print("rows", frame.height, "pairs", frame["pair"].n_unique(), "from", frame["minute"].min(), "to", frame["minute"].max())
