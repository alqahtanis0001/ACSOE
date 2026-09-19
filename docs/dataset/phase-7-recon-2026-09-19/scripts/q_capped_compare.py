"""Capped against uncapped skeptic over the 1.5-year window's BUY calls. Read-only.

Run on 2026-09-19 as an inline `python -c` command; saved here verbatim in substance so the
figures in `phase-7-findings.md` can be re-derived. Reads the per-fold outputs `q_capped.py`
wrote (P(wrong) from the in-memory 13-fold-capped skeptic and from the trained, uncapped one).
"""
import glob
import sys

import polars as pl

folder = sys.argv[1]  # the directory q_capped.py wrote its fold_NNN.parquet files into
d = pl.concat([pl.read_parquet(f) for f in glob.glob(folder + "/fold_*.parquet") if int(f[-11:-8]) >= 326])
d = d.with_columns((pl.col("label") == "target").alias("hit"))
print("BUY calls", d.height, "base target rate", round(d["hit"].mean(), 4))
for t in (0.5, 0.6, 0.7):
    for c in ("p_uncapped", "p_capped"):
        s = d.filter(pl.col(c) <= t)
        print(c, t, "survive", s.height, f"{s.height / d.height:.3%}", "target rate",
              round(s["hit"].mean(), 4) if s.height else None)
both = d.filter((pl.col("p_uncapped") <= 0.5) & (pl.col("p_capped") <= 0.5)).height
print("overlap of survivors at 0.5:", both)
print("corr", d.select(pl.corr("p_uncapped", "p_capped")).item())
