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

### Suppressing a lint

A `noqa` is a claim that the linter is wrong *here*, and it has to be readable as one.

- **Always name the rule.** `# noqa: RUF001`, never a bare `# noqa`, which silences every rule on the line including ones nobody has considered.
- **Always give the reason on the same line**, or in a comment directly above it. "Why this rule does not apply", not "ruff complains".
- **Never suppress a lint to make a failing check pass.** If the rule is right, fix the code. A suppression is for the case where following the rule would make the code *wrong* — and that case is rare enough to justify explaining every time.
- The standing example is `tests/console/test_format.py`, where `U2212 = "−"` trips `RUF001` for an ambiguous unicode character. The rule is correct to flag it and would be destructive to obey: that glyph **is** the fixture for the minus-sign rule, and replacing it with an ASCII hyphen would make the test pass against the exact character it exists to reject. A lint that is right in general and wrong on one line is what `noqa` is for; a lint that is simply inconvenient is not.

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

- `structlog`, JSON output, one event per line, written to `logs/` with daily rotation. `logs/` is gitignored — never commit a log.
- Every log line inside the loop carries `cycle_id` and `run_id`.
- Log the decision, not the narration. `gate_blocked engine=cost net_edge=-0.0021` beats "checking if the trade is profitable".
- **Never log an API key, a signature, or a nonce.** Redact at the client layer, not at the call site.
- **Never name a field after the credential it describes.** `SECRET_KEY_TOKENS` matches on
  substrings of the field *name*, so it cannot distinguish a credential from a statement about
  one: `credentialed` and `api_key_present` are both redacted, and they are the two names anyone
  reaches for first. There is no name for a boolean "do we have a key" that reads naturally and
  survives the redactor, so **name the consequence instead** — `private_calls_enabled`. It is the
  better field anyway, because an operator can act on "the private calls will not answer" and
  cannot act on "there is no key in the environment". The redactor is right in both cases; the
  field name was wrong. This failure is silent by construction: the line still appears, still
  looks well-formed, and carries `<redacted>` where the answer should be.

## Testing

- `pytest`. Every engine has tests before it is considered done.
- Every gate needs at least one test proving it blocks, and one proving it passes.
- Tests use a fake Kraken client with recorded fixtures. No test touches the network.
- Anything involving money uses exact `Decimal` assertions, never `pytest.approx`.
- Use `hypothesis` for sizing and rounding logic — that is where off-by-one errors hide.
- A test that asserts a gate can be bypassed is a defect in the test.
- **A double must be capable of exhibiting the property under test.** Before writing the
  assertion, ask what single property this test exists to demonstrate, and whether the fake,
  fixture or stub can actually exhibit it. A double that is simpler than the real thing *in
  exactly the dimension the test is about* cannot fail, and a test that cannot fail is not
  evidence — it is worse than no test, because it reads as coverage. Phase 3 found four:
  a fake transport that counted nothing, in tests about whether a second call makes a request;
  a client built without a TTL, in a test about whether a missing credential blocks; a
  `FakeTime.sleep` with no `await` in it, in a test about lock contention; and a hand-built
  `state["exchange"]` that agreed with its caller, in tests about whether the caller reads the
  right keys. All four were green for a whole phase.
- **Then break the code and watch the test go red.** Asking whether a double *can* exhibit the
  property is an instruction to imagine a failure, and imagining it is not reliable — the lead
  wrote the rule above and then committed a regression test that passed against the unfixed
  code, in the commit that cited the rule. Reverse the condition, delete the guard, return the
  wrong field; confirm the test fails; put it back. It takes a minute and it is the only step
  that cannot be talked past. A test you have never seen fail is a claim, not a check.
- **Coverage counts executions; a mutation asks whether anything would object.** They are not
  two measures of the same thing, and where they disagree the mutation is right. Spec 39's
  twelve mutations killed eleven; the survivor was a branch with *excellent* line coverage —
  every test in `test_market_data_recorder.py` ran engine 2 without engine 1, so the
  "engine 1 published nothing" path executed constantly and nothing asserted what it reported.
  A tick that had left the subscription alone could have claimed it recomputed it. High
  coverage pointed the opposite way from the truth, because a line everybody runs is the line
  nobody thinks to assert on. Run mutations as a matter of course rather than where you suspect
  a problem: that survivor was found after two earlier mutation runs had already made the author
  confident the area was covered.
- **A test whose purpose is "this goes red when X changes" must reach X through the code path
  X lives on.** A tripwire built to fire when the daemon was wired to real clients stayed green
  through exactly that change, because it constructed the empty client set *itself* rather than
  going through `cli/engine.py` — so it pinned a fact the test supplied, and replacing the
  daemon's wiring could not move it. This one passes the "can it fail?" question above: it can,
  just never for the reason it exists. Attach the tripwire to the cause, not to a local
  reproduction of the symptom.
- **A fallback for a thing that does not exist yet needs a test that fails once it does.** The
  shape is `try: import the real thing / except ImportError: define our own`, with nothing
  anywhere asserting which branch ran — so the workaround stays armed long after it stopped being
  needed, and a test importing *through* it cannot detect it. This is the decayed assertion from
  the opposite direction: not a claim that stopped being checked, but a scaffold that stopped
  being load-bearing and was never removed. The same applies to a fixture that returns `None` when
  an import fails, and to `pytest.importorskip`, which re-raises an `ImportError` from inside a
  module but **skips** a `ModuleNotFoundError` — so a dependency moving to an extra silently skips
  every test behind it, under a reason string that is no longer true.
  **The fix is never to delete the fallback — it is to add the assertion that the fallback is
  unreachable.** One line saying "the real branch is the live one" turns a stale workaround into
  a tripwire for the day someone breaks what it stood in for; deleting it throws that away. The
  same applies to `except KeyError: continue` over a config read, which conflates *absent* with
  *present-and-null* — two different facts that `Config.get` deliberately reports differently.
- **`pytest.raises(SomeError)` alone is a weak assertion wherever one error type has several
  causes.** Every fail-closed path in `clients/kraken/` raises `KrakenUnavailableError` on
  purpose, so the bare form cannot tell the failure you induced from one that happened first.
  Assert on the message, or on the reason code. The same applies to any status a gate returns
  for more than one reason: assert the reason, not only the `BLOCK`.

## Verification

Four commands. All four must be green before any task is reported complete. For `verify.py` mid-phase, green means **no FAIL** — PENDING is expected until phase close.

```
pytest tests/ -q
mypy --strict src/
ruff check src/
python scripts/verify.py --phase N
```

`scripts/verify.py` is the executable form of the phase exit criteria in `ai-workflow-rules.md`. Each criterion is one named check printing pass or fail. Adding a phase means adding its checks. A criterion that cannot be expressed as a check is badly written and should be rewritten, not skipped.

## Configuration
 **Where several branches raise one type, the message is not a
  nicety — it is the only thing that says which branch ran.** `parse_envelope` has three
  refusal branches and all three raise the same type; the test *named* for the second passed
  a non-JSON body, so it exercised the first, and the second had no test at all. Name claimed
  one branch, input reached another, and the shared type meant nothing objected. That branch
  is load-bearing: without it a body carrying a `result` and **no `error` key** parses as a
  clean success, in the one function deciding whether a Kraken response succeeded.
- One `config/default.yaml`, parsed into a pydantic `Config` at startup and passed through `EngineContext`.
- No engine reads an environment variable directly except through the config layer.
- Every threshold is named and configurable. No magic numbers inside engines.
- Config is validated at startup and the process refuses to start if it is invalid.
- **A key and its model field land in one change**, field first, then YAML. Every section sets
  `extra="forbid"`, so whichever half lands alone breaks every test that reads the committed
  config.
- **Whether that field is then required is a separate question, and the answer is per-reader.**
  Required when absence should stop the process — right when every reader raises on absence
  anyway, so startup is the same refusal delivered earlier and with a better message. Optional
  when a reader has been ruled to keep working without it, because a required field overrules
  that reader by never letting the process start. The landing order is universal; the resting
  state is not.
- **A half-landed key is not uniformly safe just because the reader raises.** `Config.get`
  raises on an unknown key, the orchestrator turns a raised engine into `ERROR`, and `ERROR`
  blocks — so a missing key once made engine 2 the tick's *primary blocker* and displaced
  `data_guard`, writing a wrong `block_records.is_primary` for every tick in that window. A
  corrupted audit row is worse than a stopped daemon, because it looks like data.

## File organisation

- `src/acsoe/core/` — contracts and the orchestrator only. No dependencies on anything else in the package.
- `src/acsoe/platform/` — config, clock, logging, and the live-mode guard
- `src/acsoe/engines/<name>/` — one engine, three files
- `src/acsoe/clients/` — everything that talks to the outside world
- `src/acsoe/research/` — offline labelling, training, walk-forward
- `src/acsoe/console/` — FastAPI app
- Name files after the responsibility, not the technology.
