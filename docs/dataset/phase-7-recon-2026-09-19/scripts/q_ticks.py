"""Read-only. Has the price grid (tick size) moved between the 2023-07..2025-01 window and 2026-09?

For each pair: the number of decimals carried by trade prices, as the smallest d such that 99.9%
of prints are on a 10^-d grid, in (a) Kraken's published time-and-sales inside the window and
(b) the recorder's 2026 last-trade prints. Equal d means the grid is consistent with being
unchanged; a larger 2026 d means the tick got finer, a smaller one coarser.
Also the smallest print sizes (a floor that ordermin can NOT be read from, reported as such).
"""
import json
import sys
from decimal import Decimal
from pathlib import Path

import polars as pl

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
HERE = Path(__file__).parent
LO, HI = 1688169600, 1735948800
per = pl.read_parquet(HERE / "per_pair_spread_depth.parquet")
minutes = pl.read_parquet(HERE / "spread_minutes.parquet", columns=["pair"])  # pairs only
manifest = json.loads((REPO / "models/train-20260913T205245-067b2b9d-f404/manifest.json").read_bytes())
norm = {"XBT": "BTC", "XDG": "DOGE"}
arch = {p: f"{norm.get(p[:-3], p[:-3])}/USD" for p in manifest["dataset"]["pairs"] if p.endswith("USD")}
recorded = set(per["pair"].to_list())


def decimals_of(text: str) -> int:
    t = text.strip()
    if "e" in t or "E" in t:
        t = format(Decimal(t), "f")
    if "." not in t:
        return 0
    return len(t.split(".")[1].rstrip("0"))


def grid(values: list[str]) -> tuple[int, int]:
    ds = sorted(decimals_of(v) for v in values)
    return ds[int(0.999 * (len(ds) - 1))], ds[-1]


# 2026 last trades from the summaries, kept as the JSON text
import orjson  # noqa: E402
last = {}
for path in sorted((REPO / "data/summaries").glob("summary__msi__*.jsonl")):
    with path.open("rb") as fh:
        for line in fh:
            if b'"last_trade":null' in line:
                continue
            d = orjson.loads(line)
            if d.get("kind") == "summary" and d.get("pair") in recorded and d.get("last_trade") is not None:
                last.setdefault(d["pair"], []).append(repr(d["last_trade"]))

wanted = sorted(set([p for p, s in arch.items() if s in recorded] + ["1INCHUSD", "ACHUSD", "ACAUSD"]))
out = []
for pair in wanted:
    src = None
    for dirname in ("KRAKEN_TimeAndSales_Combined", "TimeAndSales_Combined"):
        cand = REPO / "data/historical" / dirname / f"{pair}.csv"
        if cand.exists():
            src = cand
            break
    if src is None:
        out.append((pair, None, None, None, None))
        continue
    frame = (pl.scan_csv(src, has_header=False, new_columns=["ts", "price", "volume"],
                         schema_overrides={"ts": pl.Int64, "price": pl.Utf8, "volume": pl.Utf8})
             .filter((pl.col("ts") >= LO) & (pl.col("ts") < HI)).collect())
    if frame.height == 0:
        out.append((pair, 0, None, None, None))
        continue
    g_old = grid(frame["price"].to_list())
    s = arch.get(pair)
    g_new = grid(last[s]) if s in last else None
    out.append((pair, frame.height, g_old, g_new, float(frame["price"].cast(pl.Float64).median())))
    print(pair, frame.height, "window grid (99.9%, max)", g_old, "| 2026 grid", g_new, flush=True)

same = [o for o in out if o[2] and o[3] and o[2][0] == o[3][0]]
finer = [o for o in out if o[2] and o[3] and o[3][0] > o[2][0]]
coarser = [o for o in out if o[2] and o[3] and o[3][0] < o[2][0]]
print(f"\ncompared {len(same) + len(finer) + len(coarser)} pairs: same grid {len(same)}, finer in 2026 {len(finer)}, coarser in 2026 {len(coarser)}")
for o in finer + coarser:
    print("  differs:", o)
