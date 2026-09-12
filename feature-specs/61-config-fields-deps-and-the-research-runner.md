# 61 — Config fields, dependencies, the models root, and a research runner that runs

**Owner:** A — Platform

**Phase:** 5. `platform/config.py`, `pyproject.toml`, `cli/` and the runtime directories are A's.

## Goal

The model engines can be configured, installed and pointed at an artefact root, and
`acsoe research` actually runs the offline chain instead of listing it. Four small pieces; each
blocks C.

## Implementation

1. **Config fields, before the YAML.** Sections on the config model, every one
   `extra="forbid"`: `models` (`dir: Path`, `prediction_run_id`, `anomaly_run_id`,
   `skeptic_run_id`, the three run ids `str | None = None`, because a fresh clone has no
   artefact and the engines must block rather than the process refuse to start); `features`
   (`version: str`, `max_lookback_bars: int`, `min_lookback_fill: Ratio`); `macro` (a mapping
   of macro asset to `{live: str, archive: str}` pair names); `prediction` (`di_window_days`,
   `di_neighbours`, `di_reference_rows`, `calibration_days`, `threads`, and
   `di_percentile: Ratio | None = None`); `anomaly` (`threshold_percentile: Ratio | None =
   None`); `skeptic` (`veto_threshold: Ratio | None = None`); `regime` (`high_vol_percentile:
   Ratio`, `trend_efficiency: Ratio`); `scout` gains `rank_feature: str | None = None` and
   `rank_descending: bool = True`.
   A validator refuses `features.max_lookback_bars` above `market_sensor.published_bars`.
   The three operator keys are **optional leaves**: `Config.get` returns `None` for them, and
   every reader is told so in the field docstring, which is the spec 58 finding.
2. **Dependencies.** `lightgbm`, `scikit-learn` and `shap` move from the `research` extra to
   base dependencies; `hmmlearn` and `statsmodels` stay. The comment in `pyproject.toml` is
   rewritten to say why, and `tests/platform/` gains a test that the three import from a base
   install path.
3. **The models root.** `platform/paths.py` creates `models/` at startup beside `data/` and
   `logs/`; `cli/engine.py` and `cli/research.py` pass `models_dir` into B's `StoreClient`
   (spec 62). Creating the directory is A's; the artefacts written into it are C's.
4. **`acsoe research` runs the chain.** `run()` builds a `SystemClock`, a replay-mode
   `EngineContext` with the real config and a store client, runs each offline engine's
   `process` in registry order, and prints one line per engine with its status and `reason`.
   Non-zero exit on any `ERROR`. Engine 20 `tournament` is registered in `OFFLINE_CHAIN`
   **after** engine 23 the moment C's class exists, one line, and the invariant-5 reachability
   guard that covers 23 covers it.
5. `tests/cli/test_entrypoints.py` and `tests/platform/test_config.py`, A lane.

## Scope Limits

- Do **not** paste any YAML. The lead authors `config/default.yaml` after the fields land.
- Do **not** give a trading threshold a default. The three operator keys are `None` and stay so.
- Do **not** touch `research/training.py`, any engine, or `bootstrap.py`.
- Do **not** add a training subcommand. Training is `python -m acsoe.research.training` (C's).

## Check When Done

- Each new field observed refusing a bad value, and the `max_lookback_bars` validator observed
  red against `published_bars + 1`.
- `acsoe research --config config/default.yaml` runs engine 23 and exits 0.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
