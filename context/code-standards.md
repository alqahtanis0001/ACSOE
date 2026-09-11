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

### Editing a file in place

- **Write bytes, or pass an empty `newline` argument. Never a bare `Path.write_text()`.**
  Text mode on Windows translates every line feed into a carriage-return/line-feed pair, so
  the round trip everyone reaches for — read the file, replace a string, write it back —
  rewrites the **whole file's** line endings, not the lines you edited. A two-line file
  written as LF comes back out as CRLF, every line of it.
- It hides for the same reason it is easy to do. `.gitattributes` carries `* text=auto
  eol=lf`, so git's clean filter normalises on the way into the index: the blob is correct,
  `git status` reports nothing, and 120 tracked files in this repository are already CRLF in
  the working tree without anyone noticing across three phases of audits. Phase 3 recorded
  it as an unexplained conversion "of the kind that hides"; this is the mechanism.
- **Where it stops being cosmetic is `tests/fixtures/`, marked `-text` precisely so no
  conversion happens near an evidence fixture.** There is no clean filter there, so a
  text-mode round trip changes the committed bytes — on a parquet payload that is
  corruption, and the criterion that reads it fails with a parse error naming nothing useful.
- `csv.writer` needs the same empty `newline` on the file object, or it doubles the carriage
  return before every line feed.

### Suppressing a lint

A `noqa` is a claim that the linter is wrong *here*, and it has to be readable as one.

- **Always name the rule.** `# noqa: RUF001`, never a bare `# noqa`, which silences every rule on the line including ones nobody has considered.
- **Always give the reason on the same line**, or in a comment directly above it. "Why this rule does not apply", not "ruff complains".
- **Never suppress a lint to make a failing check pass.** If the rule is right, fix the code. A suppression is for the case where following the rule would make the code *wrong* — and that case is rare enough to justify explaining every time.
- The standing example is `tests/console/test_format.py`, where `U2212 = "−"` trips `RUF001` for an ambiguous unicode character. The rule is correct to flag it and would be destructive to obey: that glyph **is** the fixture for the minus-sign rule, and replacing it with an ASCII hyphen would make the test pass against the exact character it exists to reject. A lint that is right in general and wrong on one line is what `noqa` is for; a lint that is simply inconvenient is not.

## Money and numbers


- **Never let SQLite compare a money column.** Money is stored as an exact decimal *string*,
  so SQL comparison is lexicographic and decides `'9.50' > '10000.00'`. No `MAX()`, `MIN()`,
  `ORDER BY`, `>` or `BETWEEN` on a money column, ever. B found this building
  `peak_equity()` in Phase 4, before it shipped: the obvious `SELECT MAX(peak_equity)` returns
  a peak that is too small, a too-small peak is a too-small drawdown, and the breaker then sits
  quiet through exactly the loss it exists to stop. Read the row you want by `ts` and compare
  in Python as `Decimal`, which is what `safety` already does.
  Checked across `src/` at the time of writing: every `ORDER BY` is on `ts`, `id`, `cycle_id`
  or a timestamp column, and the only `max`/`min` over prices is a polars `Decimal` dtype.
  The rule is here to keep it that way, because the next one will look just as reasonable.

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
  **And a mutation that survives a *subset* has not survived — it has not been asked.** Re-run
  survivors against the whole suite before believing them: two of eight survivors in one sweep died
  on contact with tests in another file. A false survivor is worse than a missed one, because it
  sends someone to write a test for a case already covered and makes the real survivors look less
  urgent. Without this caveat the practice produces confident noise.
- **A mutation harness must restore every file BEFORE the next mutation, not in a `finally` at
  the end of the run.** B's rehearsal harness restored only at the end, so one mutation was
  still on disk while the next was applied and the second verdict was really *first plus
  second*. **Compounded mutants fail more tests, so every verdict drifts toward KILLED and a
  real survivor hides** — the harness produces its most confident output exactly when it is
  most wrong, which is the same shape as sweeping a red tree. It nearly cost the rehearsal its
  central claim: B was about to write that a one-tick rehearsal also catches a cached-`cycle_id`
  bug, on the strength of a check that was measuring a different mutation. Caught only because
  a hand run disagreed with the harness about *which* tests failed — so compare the failing set,
  not the verdict.
- **An equivalent mutant is a checked negative, not a survivor.** Report it as one. B's N3 —
  dropping a `dict.fromkeys(...)` initialiser whose keys are all assigned unconditionally
  further down — changes nothing observable and no test can kill it. Filed as a survivor it
  sends the next person to write a test for a case that cannot fail and makes the real
  survivors look less urgent; filed as a checked negative alongside the non-equivalent form of
  the same claim, it is evidence.
- **Verify a cross-lane mutation restored, by hash, in the same statement that applied it.**
  A file that is not yet tracked by git has no `git checkout --` behind it, and Phase 4's
  mutations ran against `engines/memory/engine.py` and `core/orchestrator.py` while both were
  untracked. The hash check was the only safety net there was. The lead made the matching
  mistake from the other side — a backup written to an unresolved shell variable, discovered
  at the moment of restore — and was saved only because that file happened to be committed.
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
- **An incidental kill is worse than a survivor, because a survivor is at least on a list.**
  A mutation sweep reports a branch as killed without saying *what* killed it. B closed the
  `discover_migrations` backlog in Phase 4 and found two of its six branches killed only by
  tests in other agents' files that have nothing to do with migrations — an engine test that
  happens to build a store over a missing path, and an import-boundary test that happens to
  walk the directory. Both branches read as covered in every sweep and are covered by nobody:
  either test could be rewritten tomorrow for an unrelated reason and take the only coverage
  of a refusal branch with it, silently, with the sweep still reporting a clean kill.
  So when a sweep says killed, ask **which test killed it**, and if the answer is a file that
  has no business knowing about the code under test, write the real one. This is the same
  shape as "a line everybody runs is the line nobody thinks to assert on", arriving in a form
  no survivor count will ever show you.
- **Say which directories a sweep excluded, and why.** An excluded directory is a hole in the
  sweep's coverage with a shape the next reader needs. B excluded `tests/scripts/` from the
  same sweep because it was red in another agent's lane at the time, and leaving a red
  directory in marks every mutation "killed" regardless — manufacturing a clean sweep out of
  someone else's broken tree. The harness refusing to report unless the baseline is green is
  the right posture; naming the hole afterwards is the other half of it.
- **A seam is tested by neither side by default, and Phase 4 found it twice in one day.**
  Mutating a module's own logic does not test the fields it *exports*, because the module's
  tests assert its behaviour and the consumer's tests build their own inputs. C set
  `label_window_end_ts` to the decision bar — the single field `research/walkforward.py`
  purges on — and **all 41 labelling tests stayed green**, while three separate tests proving
  the splitter purges correctly could not see that its input had stopped telling the truth.
  It is the splitter's own purge mutation reintroduced from the producer side, and it would
  have shipped a leaky fold with every test in the phase green.
  A found the same seam from the other end: every test of the labeller seam was green against
  `label_bars(...)`, a signature agreed by message that **never existed** — C's module landed
  as `label_frame(...)` and nothing went red, because everything drove a double.
  So: **mutate the field the other module reads, not only the logic that computes it**, and
  for any seam agreed between two agents keep at least one test with no double in it.
- **A mock for a module that does not exist yet needs a test that fails once it does.** The
  same rule as the import fallback above, arriving through an agreed-by-message signature
  instead of an `ImportError`. Until the real module lands, every test of the seam is a test
  of the mock.
- **A cheap prefilter is a second, weaker parser, and it must be strictly broader than the
  check it fronts.** A found two of these in one file: a JSON prefilter matching `orjson`'s
  exact separators before parsing. The second would have classified **the entire recording as
  unrecorded** — plausible enough to be believed and acted on, and acting on it would have
  meant rebuilding an archive that was fine. A prefilter that is narrower than its parser does
  not make the check faster, it makes it wrong on the inputs it silently excludes.
- **Widening a forbidden-list is as much a defect as narrowing it, and it only shows up when
  someone tries to do the right thing.** `test_the_live_loop_does_not_import_research` forbade
  `cli/` from importing `research/` — which is the design `engine-contracts.md` mandates and
  the exact thing `cli/research.py` exists to do. It cost nothing for four phases and then
  blocked the correct change the first time it mattered. **An over-strict rule is invisible
  until it is in someone's way, and at that moment it looks like the change is wrong rather
  than the rule.** Replace it with narrower, stronger assertions; do not add an exception to
  it, and do not assume the rule is right because it is old.
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
- **A handler that cannot distinguish two situations will silently pick the wrong one.**
  `except ModuleNotFoundError` catches a module that was never written *and* one whose own
  dependency is missing. `except KeyError` catches a config key that is absent *and* one the
  operator has not decided. `rmtree(ignore_errors=True)` treats "I could not delete it" as "it was
  not mine to delete". In each case two facts with different right answers arrive through one
  channel and the code answers as though they were one. Ask of every broad `except` and every
  fallback: **what two situations is this conflating, and does the caller have any way to tell
  them apart?** The information is usually already there — `exc.name`, an mtime, a distinct
  exception — and using it is a few lines.
- **"Make it stricter" is a seductive wrong turn.** When a finding is "this could pass when it
  should not", the instinct is to demand more of the *consumer*. Twice on one defect that made a
  criterion stop checking what it could check — eighteen tests turned PENDING, then five — while
  the actual fault was a *producer* conflating two cases. Tightening the consumer is the right fix
  only when the consumer is the one making the unjustified assumption.
- **"It is in another agent's path" is evidence, not a verdict.** Judging a FAIL by path is
  the right first question in a shared checkout and it is not the last one. Four times in
  Phase 4 the tree was red under B while B was working in it. Three were settled by path and
  lane with no re-running and no touching, correctly. The fourth sat squarely in another
  agent's `tests/verify/` **and was still B's**: it named B's file, it reproduced every time,
  and it was caused by a string B had just written. A path heuristic that is right three times
  out of four is exactly the kind that gets promoted to a rule and then hides the fourth case.
  Ask the three questions underneath it — does it name my file, does it reproduce every time,
  does it reproduce in isolation — and let the path narrow the search rather than end it.
- **The evidence is destroyed at the pipe, before re-running is even a decision.** The Phase 3
  rule says capture the traceback before you re-run. Phase 4 found the step before it: two
  agents independently, within an hour, ran the gate through `grep "criteria:"` and `tail -2`,
  kept the summary line and binned the criterion name and message. Both then re-ran to find out
  what had failed, and one of the two failures never recurred and is now unattributable for
  good. **Redirect to a file and read the file.** A summary line is not evidence; it is the
  receipt for evidence you did not keep.
- **A wrong answer that is in range survives; a zero or a crash is found on day one.** The two
  worst defects of Phase 4 share this property and nothing else: `SELECT MAX(peak_equity)` over
  a decimal string returns *a* peak, plausible and too small, and a hardcoded `900` where
  `timeframes.decision_bar_s` belonged returns *a* gap count, plausible and wrong. Both would
  have been reported confidently over real data. When reviewing a calculation, ask not only
  whether it can fail loudly but **what it returns when it is quietly wrong, and whether anyone
  downstream could tell.**
- **A mutation harness in a shared checkout can turn another agent's run red, and a spurious
  failure reads as KILLED.** That is the direction that hides a survivor, and it is invisible
  from inside either agent's results. Phase 4 saw a live mutation surface in a second agent's
  run as two ruff findings that agent then reported as real. Two protections, both cheap: run
  the sweep that your conclusions rest on **narrowly**, against the test file that owns the
  code, and say so; and treat "it is probably the other agent's harness" as a hypothesis to
  check rather than an explanation to accept, because it is exactly the assumption that makes
  a real finding invisible.
- **A diagnostic procedure that cannot fail is the same defect as a test that cannot fail.**
  "Re-run the named test in isolation, and if it passes it was the machine's intermittent fault"
  ran for two phases and confirmed itself every time — because in isolation nothing else was
  sweeping the temp directory, which was the actual bug. The procedure produced an answer, the
  answer was unfalsifiable, and the surrounding prose is what made it convincing. Apply to a
  diagnostic the question you apply to a test: **under what observation would this have told me
  something else?**
- **A test that anchors on a literal string must assert the literal occurs exactly once.**
  A mutation harness that rewrites code *by its literal text* silently mutates whichever
  occurrence it finds first. B's new store query in Phase 4 copied an `ORDER BY` clause
  character-for-character from the one the Phase 3 outage counter uses, and C's criterion
  refused it: *anchor appears 2 times, expected exactly once*. Without that count, a patcher
  taking the first match would have mutated the new query, left the outage counter untouched,
  watched the Phase 3 criterion stay PASS, and reported a can-it-fail proof **that had itself
  stopped being able to fail**. The count assertion is the part that keeps the proof honest,
  not decoration on it.
- **`pytest.raises(SomeError)` alone is a weak assertion wherever one error type has several
  causes.** Every fail-closed path in `clients/kraken/` raises `KrakenUnavailableError` on
  purpose, so the bare form cannot tell the failure you induced from one that happened first.
  Assert on the message, or on the reason code. The same applies to any status a gate returns
  for more than one reason: assert the reason, not only the `BLOCK`.
  **The same defect wearing a pydantic hat: in a model with `extra="forbid"`, matching a
  refusal on the key name cannot fail.** The refusal message for an unknown key *always*
  contains the key name, so `match="embargo_bars"` passes whether the constraint rejected
  the value or the field does not exist at all — A found one of its own new assertions
  surviving the delete-the-field mutation for exactly that reason, in Phase 4, in the same
  hour it was written. Match on the constraint (`Input should be greater than 0`), not on
  the name of the thing being constrained.

## Verification

Four commands. All four must be green before any task is reported complete. For `verify.py` mid-phase, green means **no FAIL** — PENDING is expected until phase close.

```
pytest tests/ -q
mypy --strict src/ scripts/
ruff check src/ tests/ scripts/
python scripts/verify.py --phase N
```

**`TOOLCHAIN` was widened beyond `src/` on 2026-09-11, by operator ruling.** It had been
deferred since Phase 0 and declined once at the Phase 1 boundary, and it was widened because
the deferral finally cost something: a file committed in Phase 4 carried a backslash escape
inside an f-string expression — legal from 3.12, a **SyntaxError on 3.11**, which is this
project's declared floor. The venv is 3.13, so pytest imported it and every test passed.
`ruff check src/` was the gate and the file was under `tests/`.

A second defect surfaced the same hour, in `scripts/build_archive.py`: a `no-any-return` that
looked like a typing complaint and was a crash — `json.loads` is `Any`, and a recorded line
parsing to a list while carrying the trade marker reached `.get` and raised. Two defects in two
days, both in files the gate could not see.

**`mypy --strict` is deliberately NOT widened to `tests/`.** Roughly 1,680 test functions would
each need a return annotation. The hole that leaves is real and is stated rather than implied:
a type error in a test file is caught by nothing except the test failing. A test asserts the
exclusion, so anyone "fixing" it meets a red first and a decision rather than an omission.

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
