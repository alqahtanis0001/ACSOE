# Code Standards

## General

- Keep modules small and single-purpose.
- Fix root causes. Never layer a workaround over a bug.
- Respect the boundaries in `architecture-context.md`. Do not mix concerns across them.
- Delete dead code rather than commenting it out.

## Python

- Python 3.11+. Use `match`, `|` unions, and `Self` freely.
- **Type hints on every function signature.** `mypy --strict` must pass on `src/`.
- No bare `except:`. No `except Exception:` without re-raising or logging with the traceback.
- No mutable default arguments.
- `pathlib.Path` for every path. This is a Windows target; never assume `/`.
- Prefer pure functions. Anything that touches the network, the clock, or the disk is injected, not imported.

## Money and numbers

- **`Decimal` for prices, quantities, fees, and balances.** Never `float`. Floating-point drift in an order size is a real defect that will get an order rejected by Kraken.
- `float` and `numpy` are fine for features, indicators, model inputs, and statistics.
- Round order sizes and prices using the pair's own `lot_decimals` and `pair_decimals` from `AssetPairs`, and always round *down* for quantity.
- Percentages are stored as decimals (`0.0038`, not `0.38`). Name the variable so the unit is obvious: `taker_fee_pct` holds `0.0038`.

## Validation

- Every payload arriving from Kraken is parsed into a pydantic model at the client boundary before any logic sees it.
- Never index into a raw API response dict inside an engine.
- Kraken returns errors in a `{"error": [...], "result": {...}}` envelope. A non-empty `error` list is a failure even when HTTP status is 200. Check it every time.

## Async and rate limits

- The exchange client is async. Engines are synchronous and receive already-fetched data.
- All Kraken REST calls go through one shared rate limiter. Never call `httpx` directly from anywhere but the client layer.
- Retries use `tenacity` with exponential backoff and jitter. Never retry an order placement without checking `userref` first.

## Dataframes

- `polars` for anything columnar. `pandas` only where a library demands it.
- Never mutate a dataframe in place across function boundaries; return a new one.
- Timestamps are UTC, timezone-aware, and stored as microseconds since epoch in Parquet.

## Models

- Every trained artefact is written to `models/<run_id>/` and never overwritten.
- Save the feature list, the scaler, and the model together. A model without its exact feature order is unusable.
- Set every random seed from config. A training run must be reproducible from its config plus its data.
- Never load a model at import time. Load it in the engine's constructor.

## Logging

- `structlog`, JSON output, one event per line.
- Every log line inside the loop carries `cycle_id` and `run_id`.
- Log the decision, not the narration. `gate_blocked engine=cost net_edge=-0.0021` beats "checking if the trade is profitable".
- **Never log an API key, a signature, or a nonce.** Redact at the client layer, not at the call site.

## Testing

- `pytest`. Every engine has tests before it is considered done.
- Every gate needs at least one test proving it blocks, and one proving it passes.
- Tests use a fake Kraken client with recorded fixtures. No test touches the network.
- Anything involving money uses exact `Decimal` assertions, never `pytest.approx`.
- Use `hypothesis` for sizing and rounding logic — that is where off-by-one errors hide.
- A test that asserts a gate can be bypassed is a defect in the test.

## Verification

Four commands. All four must be green before any task is reported complete.

```
pytest tests/ -q
mypy --strict src/
ruff check src/
python scripts/verify.py --phase N
```

`scripts/verify.py` is the executable form of the phase exit criteria in `ai-workflow-rules.md`. Each criterion is one named check printing pass or fail. Adding a phase means adding its checks. A criterion that cannot be expressed as a check is badly written and should be rewritten, not skipped.

## Configuration

- One `config/default.yaml`, parsed into a pydantic `Config` at startup and passed through `EngineContext`.
- No engine reads an environment variable directly except through the config layer.
- Every threshold is named and configurable. No magic numbers inside engines.
- Config is validated at startup and the process refuses to start if it is invalid.

## File organisation

- `src/acsoe/core/` — contracts, orchestrator, config, clock, logging
- `src/acsoe/engines/<name>/` — one engine, three files
- `src/acsoe/clients/` — everything that talks to the outside world
- `src/acsoe/research/` — offline labelling, training, walk-forward
- `src/acsoe/console/` — FastAPI app
- Name files after the responsibility, not the technology.
