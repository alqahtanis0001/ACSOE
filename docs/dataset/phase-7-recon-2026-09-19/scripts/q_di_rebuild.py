"""Read-only timing: rebuild ONLY the DI reference (matrix, identity, timestamps) for given folds,
with the Phase 5 study's own `load_fold` + `di_reference`, and check it against the identity the
study recorded. No leave-one-out, no file written."""
import importlib.util
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from winmem import peak, rss  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
folds = [int(v) for v in sys.argv[1].split(",")]
sys_config = sys.argv[2]
sys.argv = [sys.argv[0], str(REPO), sys_config, "import"]
spec = importlib.util.spec_from_file_location("fit", REPO / "docs/dataset/di-anomaly-fit-2026-09-14.py")
fit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fit)
from acsoe.research import training as _tr  # timing only: the digest guard covers thresholds ruled after training
_tr._config_digest = lambda config: '067b2b9d4c39e32c5f3d30c3dba9cfa809966aa47fc94354d53a308d267c345e'

for index in folds:
    t0 = time.perf_counter()
    f = fit.load_fold(index)
    t1 = time.perf_counter()
    reference, ids = fit.di_reference(f["training"], f["config"], f["train"], f["run"].scaler, f["names"], f["seed"])
    t2 = time.perf_counter()
    digest = f["identity_digest"]([e.split("|")[0] for e in ids], [int(e.split("|")[1]) for e in ids])
    recorded = json.loads((fit.OUT / f"fold_{index:03d}.json").read_bytes())["di"]["reference_identity"]
    print(f"fold {index}: load+verify training rows {t1 - t0:.1f} s; reference build {t2 - t1:.1f} s; "
          f"reference {reference.shape}; identity {'MATCHES' if digest == recorded else 'DIFFERS'} the study's; "
          f"rss {rss():.0f} MiB peak {peak():.0f} MiB", flush=True)
    del f, reference, ids
