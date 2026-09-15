"""The leak check behind the skeptic veto sweep: did each fold's skeptic train only on rows it
was allowed to see?

The sweep shows the surviving BUY calls hitting their target far more often than all BUY calls.
In this phase a number that good is a leak until proven otherwise, so this recomputes, for a
spread of folds, the skeptic's eligible training set **from the out-of-sample file and the
trainer's own rule** (`_skeptic_training_rows`: BUY calls, from earlier folds, label window
ending before this fold's test window, decision bar before its embargo) and compares the
identity digest of that set with the `training_identity` the trainer recorded in the fold's
manifest, and the row count with the recorded `rows`. Ruling 7 of 2026-09-13: prove which rows a
model saw by identity; never trust a count it reported about itself.

A match proves the skeptic that scored fold k's calls never trained on any row from fold k's
test window or any row whose label window reached into it. The negative control drops the
purge and embargo (every earlier-fold BUY call) and must not match.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

from acsoe.modelling.artefacts import identity_digest

REPO = Path(sys.argv[1])
RUN_ID = "train-20260913T205245-067b2b9d"
OOS = REPO / "data" / "derived" / f"oos_{RUN_ID}.parquet"
FOLDS = [1, 50, 150, 250, 300, 350, 404]
EMBARGO_BARS = 48
INTERVAL_S = 900


def main() -> int:
    buys = pl.read_parquet(OOS, columns=["pair", "decision_ts", "label_window_end_ts", "fold_index", "is_buy"]).filter(pl.col("is_buy"))
    failures = 0
    for index in FOLDS:
        manifest = json.loads((REPO / "models" / f"{RUN_ID}-f{index}" / "manifest.json").read_bytes().decode("utf-8"))
        skeptic = manifest["extras"]["skeptic"]
        test_start = int(manifest["fold"]["test_start_ts"])
        embargo_start = test_start - EMBARGO_BARS * INTERVAL_S
        eligible = buys.filter(
            (pl.col("fold_index") < index)
            & (pl.col("label_window_end_ts") < test_start)
            & (pl.col("decision_ts") < embargo_start)
        )
        unpurged = buys.filter(pl.col("fold_index") < index)
        got = identity_digest([str(v) for v in eligible["pair"]], [int(v) for v in eligible["decision_ts"]])
        control = identity_digest([str(v) for v in unpurged["pair"]], [int(v) for v in unpurged["decision_ts"]])
        in_window = eligible.filter(pl.col("label_window_end_ts") >= test_start).height
        match = got == skeptic["training_identity"] and eligible.height == int(skeptic["rows"])
        control_match = control == skeptic["training_identity"]
        failures += (not match) + control_match
        sys.stdout.write(
            f"fold {index}: recorded {skeptic['rows']} rows, recomputed {eligible.height}; identity "
            f"{'MATCH' if match else 'DIFFERS'}; rows reaching the test window {in_window}; "
            f"control without purge/embargo {unpurged.height} rows, identity "
            f"{'MATCHES (bad)' if control_match else 'differs (good)'}\n"
        )
    sys.stdout.write("ALL MATCH\n" if failures == 0 else f"{failures} FAILURE(S)\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
