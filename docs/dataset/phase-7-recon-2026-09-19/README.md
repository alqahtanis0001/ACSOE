# Phase 7 reconnaissance, 2026-09-18 and 2026-09-19

The scripts and raw outputs behind `docs/dataset/phase-7-findings.md`. All of them are read-only:
none writes to `models/`, `data/` or the store, and none ran the engine chain.

- `scripts/` holds each script as it was run. Those prefixed `2026-09-18_` ran in the session of
  that date; the rest ran on 2026-09-19.
- `outputs/` holds the files the scripts wrote (`*.out`, `*.log`, the capped-skeptic logs) and
  `transcribed-terminal-outputs.txt` for the scripts that only printed. That file is copied
  verbatim from the terminal; nothing was re-run to produce it.

**Running them again.** They were run from a session scratchpad and carry absolute paths to the
repository. Several read or write intermediate files beside themselves:

| Script | Intermediate files |
|---|---|
| `q_spread_agg.py` | writes `spread_minutes.parquet` |
| `q_depth.py` | writes `per_pair_spread_depth.parquet` |
| `q_spread_fit.py` | writes `spread_bars.parquet` |
| `q_capped.py` | writes `capped/fold_NNN.parquet`, and **trains 79 skeptics in memory, about 50 s each** |

Copy the scripts to a scratch directory before running them rather than running them in place.
`q_funnel.py`, `q_bucket.py`, `q_emrank.py` and `q_picks.py` read those intermediates, and must
run after the scripts that write them.

`q_di_rebuild.py` replaces the study's config-digest guard for its own run only. The guard covers
the three thresholds ruled after training, so today's config no longer matches the training
digest. That is a fact for the Phase 7 artefact build, recorded in the findings.
