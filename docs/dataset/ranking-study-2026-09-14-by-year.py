"""By test year and by how thin the chosen pair is, for the rows of `ranking-study-2026-09-14.json`
that differ most from the alphabetical control. Evidence for `scout.rank_feature`; it sets nothing.

The chosen pair per bar comes from `acsoe.research.ranking_study.chosen_pairs`, the study's own
implementation of engine 7's `rank_universe` rule, so these rows are the study's rows split by
year, not a second ranking. Thinness is the taken row's own `bars_in_lookback_96` (how many of
the last 96 decision bars had a trade in that pair): the archive carries no spread, and a
close-to-close effect concentrated in pairs that trade intermittently is the shape a bid-ask
bounce would leave, which this archive cannot rule in or out.

    python ranking-study-2026-09-14-by-year.py <repo>
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from acsoe.research.ranking_study import chosen_pairs

REPO = Path(sys.argv[1])
RUN_ID = "train-20260913T205245-067b2b9d"
OOS = REPO / "data" / "derived" / f"oos_{RUN_ID}.parquet"
DATASET = REPO / "data" / "derived" / "dataset_20260913T205245.parquet"
OUT = REPO / "docs" / "dataset" / "ranking-study-2026-09-14-by-year.json"
ROWS = [
    (None, "ascending"),
    ("bar_body_pct", "ascending"),
    ("log_return_4", "ascending"),
    ("log_return_16", "ascending"),
    ("high_low_position_16", "ascending"),
    ("bars_in_lookback_96", "ascending"),
    ("realised_vol_16", "descending"),
    ("range_atr_4", "descending"),
    ("bar_range_pct", "descending"),
]
FEATURES = sorted({name for name, _ in ROWS if name} | {"bars_in_lookback_96"})


def summary(frame: pl.DataFrame) -> dict:
    n = frame.height
    return {
        "bars": n,
        "effective_bars": float(frame["weight"].sum() or 0.0),
        "target_rate": float((frame["label"] == "target").mean()),
        "stop_rate": float((frame["label"] == "stop").mean()),
        "timeout_rate": float((frame["label"] == "timeout").mean()),
        "mean_return_pct": float(frame["return_pct"].mean()),
        "distinct_pairs": int(frame["pair"].n_unique()),
        "top10_pair_share": float(
            frame.group_by("pair").len().sort("len", descending=True).head(10)["len"].sum() / n
        ),
        "mean_bars_in_lookback_96": float(frame["bars_in_lookback_96"].mean()),
        "share_bars_in_lookback_96_below_48": float((frame["bars_in_lookback_96"] < 48).mean()),
    }


def main() -> int:
    oos = pl.read_parquet(OOS, columns=["pair", "decision_ts", "label", "return_pct", "weight", "is_buy", "di", "di_refused"])
    dataset = pl.read_parquet(DATASET, columns=["pair", "decision_ts", *FEATURES])
    thin = dataset.select(["pair", "decision_ts", "bars_in_lookback_96"])
    base = oos.join(thin, on=["pair", "decision_ts"], how="inner")
    if base.height != oos.height:
        raise SystemExit(f"REFUSED: the join keeps {base.height} of {oos.height} rows")
    report = []
    for feature, direction in ROWS:
        taken = chosen_pairs(oos, dataset, feature=feature, direction=direction)
        keys = pl.DataFrame(
            {"decision_ts": list(taken.keys()), "pair": list(taken.values())},
            schema={"decision_ts": base.schema["decision_ts"], "pair": pl.String},
        )
        rows = base.join(keys, on=["decision_ts", "pair"], how="inner").with_columns(
            pl.from_epoch("decision_ts", time_unit="s").dt.year().alias("year")
        )
        if rows.height != len(taken):
            raise SystemExit(f"REFUSED: {feature} {direction}: {rows.height} rows for {len(taken)} bars")
        entry = {"feature": feature or "(alphabetical control)", "direction": direction, "all": summary(rows), "by_year": {}}
        for (year,), group in rows.group_by(["year"], maintain_order=False):
            entry["by_year"][str(year)] = summary(group)
        entry["by_year"] = dict(sorted(entry["by_year"].items()))
        report.append(entry)
        sys.stdout.write(f"{entry['feature']} {direction}: {json.dumps(entry['all'])}\n")
        sys.stdout.flush()
    OUT.write_bytes(
        json.dumps(
            {"measured_at": datetime.now(UTC).isoformat(), "run_id": RUN_ID, "rows": report},
            indent=1,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
