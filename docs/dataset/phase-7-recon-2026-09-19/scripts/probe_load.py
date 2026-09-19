"""Read-only probe: do today's engine loaders accept fold 404's artefacts, and what does loading cost in memory."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from winmem import peak, peak_commit, rss  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
fold = int(sys.argv[1]) if len(sys.argv) > 1 else 404
run_id = f"train-20260913T205245-067b2b9d-f{fold}"
directory = REPO / "models" / run_id
print("baseline rss MiB", round(rss(), 1))

from acsoe.engines.prediction import engine as e8  # noqa: E402
from acsoe.engines.anomaly import engine as e13  # noqa: E402
from acsoe.engines.skeptic import engine as e15  # noqa: E402
print("after imports rss MiB", round(rss(), 1))

for name, mod in (("prediction(8)", e8), ("anomaly(13)", e13), ("skeptic(15)", e15)):
    before = rss()
    t = time.perf_counter()
    try:
        obj = mod._read(directory, run_id)
        print(f"{name}: LOADED in {time.perf_counter()-t:.2f}s, +{rss()-before:.1f} MiB")
    except Exception as problem:  # the probe reports every refusal verbatim
        print(f"{name}: REFUSED ({type(problem).__name__}) in {time.perf_counter()-t:.2f}s: {problem}")

# What engine 8 checks before the DI: the artefact itself, against today's feature list.
from acsoe.modelling.artefacts import load_run  # noqa: E402
before = rss()
from acsoe.modelling.features import FEATURE_NAMES  # noqa: E402
from acsoe.modelling.macro import macro_feature_names  # noqa: E402
expected = e8._expected_features(directory / "manifest.json", FEATURE_NAMES, macro_feature_names)
loaded = load_run(directory, expected_features=expected)
print("load_run with today's expected features: OK,", len(expected), "features, +", round(rss() - before, 1), "MiB")
print("rss MiB", round(rss(), 1), "| peak working set MiB", round(peak(), 1), "| peak commit MiB", round(peak_commit(), 1))
