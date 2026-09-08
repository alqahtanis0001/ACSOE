# Build log — Phase 0 — a-platform

Your file. Append as you work, per context/script-rules.md.
The lead consolidates these into docs/build-log/phase-0.md at phase close.

Minimum headings per entry: What happened, Why, Fix.

## Entries

### Decision: Python 3.13, and the model libraries behind a `research` extra

**Agent:** A · **Task:** spec 03 · **Date:** 2026-09-08

**Options.** The machine's default interpreter is Python 3.14.7 (3.13.5 also installed). The
stack table lists `lightgbm`, `scikit-learn`, `hmmlearn`, `shap` and `statsmodels` as runtime
dependencies. On 3.14 those have no Windows wheels yet and would be built from source, which
fails; `shap` drags in `numba`, historically the last package in that set to gain a new
interpreter. So either the whole set stays in `[project.dependencies]` and the Phase 0 install
is at the mercy of wheel availability, or it moves behind an extra.

**Chose.** Build the venv on **3.13.5** with `requires-python = ">=3.11"`, and split the five
model libraries into a `research` extra, with `dev` depending on `acsoe[research]` so
`pip install -e ".[dev]"` still installs everything and the README's setup line stays true.
Lead decision, taken after A proposed the split as a fallback.

**Because.** `pip install -e ".[dev]"` succeeding is a Phase 0 exit criterion, so a failing
install is a failed phase. A dry-run resolve on 3.13 confirmed every one of the five has a
`cp313` wheel (lightgbm 4.7.0, scikit-learn 1.9.0, shap 0.52.0 via numba 0.67.0/llvmlite 0.49.0,
hmmlearn 0.3.3, statsmodels 0.15.0), so 3.13 is not a workaround — it is the version the stack
actually ships for. The split also happens to encode architecture invariant 5 in the packaging:
nothing on the live-loop path imports a model library before Phase 5, and now the base install
does not contain one.

**Cost.** Two install shapes to keep straight, and a future agent who runs
`pip install -e .` and then imports `sklearn` gets an `ImportError` rather than a clear message.
`tests/platform/test_packaging.py` asserts the split (base and `research` are disjoint, `dev`
includes `research`), so an accidental merge of the two fails a test rather than passing review.

### `pyyaml` was missing from the stack table

**Agent:** A · **Task:** spec 03 · **Date:** 2026-09-08

**What happened.** `config/default.yaml` is YAML and spec 07 requires parsing it, but the stack
table in `architecture-context.md` names no YAML parser. `ai-workflow-rules.md` makes a
dependency outside that table an escalation, so adding `pyyaml` quietly would have been a rule
violation, and hand-rolling a parser in `platform/config.py` would have been worse — a
half-correct YAML subset silently mis-parsing a risk limit is exactly the class of defect the
config layer exists to prevent.

**Why.** The table was written from the runtime architecture and the config file was specified
separately; neither review caught that one needed something the other never listed. C hit the
same gap from the `verify.py` side at the same time.

**Fix.** Escalated to the lead by both A and C. The lead added the row, with the restriction
that it is **`yaml.safe_load` only, never `yaml.load`** — part of the approval, not a style
note, because `yaml.load` on a config file is arbitrary object construction. The restriction is
written next to the dependency in `pyproject.toml` so it travels with it.

**Consequence.** `tests/platform/test_packaging.py` now asserts the declared dependency set is a
subset of the stack table, so the next out-of-table dependency fails a test instead of relying
on a reviewer noticing a line in a diff.

### The reconnect backoff compounded across successful reconnects

**Agent:** A · **Task:** spec 10 · **Date:** 2026-09-08

**What happened.** `Recorder.run` held `backoff` as a local and reset it to 1s only after
`await self._session()` *returned*. `_session` never returns normally except when the recorder
is shutting down — it exits by raising `ConnectionClosedError`. So the reset was unreachable in
practice and the delay doubled on every disconnect for the life of the process, even when every
single reconnect had succeeded on its first attempt. Induced disconnects showed it plainly:
0.6s, 1.3s, 2.0s, 4.2s, with `attempt: 1` on all four.

**Why.** Exponential backoff is meant to be per-outage, and "the outage ended" is signalled by a
*successful connect*, not by the read loop returning. Writing it as a local in the retry loop
made the wrong event the reset point, and it is invisible in a short test because the first two
delays look fine.

**Fix.** `_backoff` is now an instance attribute reset inside `_session` immediately after the
`connect()` succeeds, next to `self._attempt = 0`, with a comment saying why that is the right
place. Re-running the induced-disconnect capture gives 0.8, 1.1, 0.9, 0.7, 1.4, 1.1, 1.1 — flat,
as it should be.

**How it was noticed.** Not by reading the code — it reads correctly. It surfaced because
producing the committed sample required a `gap` marker, which required inducing real
disconnects, which printed four reconnect lines to stderr in one 20-second run:
`reconnecting in 0.6s (attempt 1)`, then `1.3s (attempt 1)`, `2.0s (attempt 1)`, `4.2s (attempt 1)`.
The delay doubling while `attempt` stayed at 1 is the whole tell: `attempt` resets on a
successful connect and the delay did not, so the two were being reset at different points in the
loop. Without a fixture that had to contain a gap marker there would have been no reason to
disconnect the recorder repeatedly in a short window, and nothing would have made the pattern
visible.

**Consequence.** This mattered more than an ordinary retry bug. A recorder that drops once an
hour would, after twelve hours, sit out a full minute after each fault. Order-book and spread
history cannot be recovered retroactively, so every one of those minutes is data that no later
phase can obtain by any means. The gap marker would at least have recorded the loss honestly,
which is the only reason it would ever have been noticed.

### Forcing a real gap marker into the committed sample

**Agent:** A · **Task:** spec 10 · **Date:** 2026-09-08

**What happened.** The sample has to contain a `gap` line — the reconnect path is the part of
the recorder most likely to break later and least likely to be exercised by an ordinary capture.
A clean Kraken v2 session ran 45 seconds and 7,337 lines without a single disconnect, and
waiting for a natural one is not a plan.

**Why.** Fabricating the marker by hand was not acceptable: a fixture that was typed rather than
recorded proves the format, not the behaviour, and the whole point of committing evidence is
that it came out of the real code path.

**Fix.** Added `--ping-interval` and `--ping-timeout` to the recorder — legitimate operational
knobs — and captured the sample with `--ping-timeout 0.001`, well below the round trip to
Kraken. The `websockets` keepalive then declares the connection dead and closes it with
`1011 keepalive ping timeout`, the recorder's real reconnect path runs, and the gap markers in
`tests/fixtures/record_sample.jsonl` are genuine output of that path with real measured
`gap_ms` values (1986ms, 2292ms). Fault injection, not fabrication.

**Consequence.** The induced-fault capture was written to a scratch directory, **not** to
`data/raw/`. Polluting the real recording with artificial gaps would corrupt exactly the gap
statistics Phase 2's `recording_report.json` criterion has to report. The 45-second clean
capture in `data/raw/` stays clean, and nothing from `data/raw/` is committed.

### `git check-ignore` reports a *negation* as a match, so it cannot prove a file is committable

**Agent:** A · **Task:** spec 10 · **Date:** 2026-09-08

**What happened.** The instruction was to confirm that `!tests/fixtures/**` genuinely lets a
`.jsonl` be staged rather than assume it. `git check-ignore -v tests/fixtures/record_sample.jsonl`
printed `.gitignore:21:!tests/fixtures/**` and **exited 0**, which reads as "this file is
ignored" and is how a naive check would report it.

**Why.** `check-ignore` exits 0 when a path matches any ignore *rule*, including a negation
rule; the leading `!` in the printed pattern is the only thing distinguishing "ignored" from
"explicitly un-ignored". A shell test of the exit code alone gets the answer exactly backwards.

**Fix.** The real proof is `git add` followed by `git ls-files --stage <path>` returning a row.
It does: mode 100644, blob 60a0439. The negation is load-bearing and it works. Recording the
method here because the next agent to check a fixture will reach for `check-ignore` first.

### `core.autocrlf=true` will change the fixture's bytes on a fresh clone

**Agent:** A · **Task:** spec 10 · **Date:** 2026-09-08

**What happened.** `git add tests/fixtures/record_sample.jsonl` warned "LF will be replaced by
CRLF the next time Git touches it". `core.autocrlf` is `true`, inherited from Git for Windows'
system config at `C:/Program Files/Git/etc/gitconfig`. The blob in the index is LF; a fresh
clone on Windows checks it out as CRLF. There is no `.gitattributes` in the repository.

**Why.** Nobody set it — it is the Git for Windows default, so it applies to every clone on
every Windows machine and to nobody on Linux.

**Fix.** A `.gitattributes` at the repository root is the fix, and that is a cross-cutting file,
so it was escalated to the lead rather than created here. In the meantime
`tests/platform/test_record_format.py` parses the fixture with `splitlines()` and skips blank
lines, so it passes under either line ending.

**Consequence.** Bigger than this one fixture. `ai-workflow-rules.md` says a criterion that only
passes on the machine that produced it is a broken criterion, and this is the mechanism that
produces exactly that. It also threatens C's `tests/fixtures/labelled_sample.parquet`: Parquet
is binary, git's text/binary heuristic is a guess, and a wrong guess corrupts the file silently
rather than failing loudly.

### The `Config` Protocol had two members and the model implemented one

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

**What happened.** `acsoe engine` could not be typed against the real orchestrator.
`mypy --strict` reported `Argument "config" to "Orchestrator" has incompatible type
"acsoe.platform.config.Config"; expected "acsoe.core.contracts.Config"`. The model built for
spec 07 satisfied the Protocol's `mode` property and nothing else — `core/contracts.py` also
declares `get(dotted_key, /)`, a dotted-path accessor, and the model had no `get` at all.

**Why.** Spec 07 was built before `core/contracts.py` existed, against the key list in spec 06.
Every key in `config/default.yaml` was covered, so the model looked complete and the tests
passed; what was missing was not a key but the *access shape* the lead had chosen for engines
to reach one. Nothing failed until an object crossed the seam, which is the point at which a
structural Protocol is actually checked.

**Fix.** Added `Config.get` in `platform/config.py`, walking sections and mapping values alike
so both `"paper.starting_balances"` and `"paper.starting_balances.USD"` resolve, and matching a
section field by its YAML name as well as its Python name so `"seeds.global"` reaches a field
Python will not let anyone name `global`. It **raises on a miss and has no default parameter**.
That is the whole reason the method is worth writing carefully: a `dict.get`-shaped signature
invites `config.get(key, fallback)`, and a fallback here is a guessed answer to how much money
is at risk. The exception is `ConfigKeyError`, deliberately distinct from `ConfigError` — the
latter means the file is invalid and the process must not start; this means running code asked
for a key that does not exist. It subclasses `KeyError`, so an engine reaching for a threshold
it never had gets an exception the orchestrator converts to `ERROR`, and `ERROR` blocks.

**Consequence.** `tests/platform/test_config.py` now asserts `isinstance(config,
contracts.Config)` against the runtime-checkable Protocol, so the next divergence between the
lead's shape and my implementation fails a test rather than waiting for the next object to
cross the seam. `ConfigKeyError.__str__` is overridden because `KeyError` renders its argument
with `repr`, which would wrap the multi-line "here is what was available" diagnostic in quotes
and escape every newline in it — the message is the entire value of the exception, so having it
arrive mangled would have defeated the point of writing one.

### Decision: the dispatcher imports each command module lazily

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

**Options.** `cli/main.py` imported `engine`, `console` and `research` at module scope and hung
each subcommand's handler off `set_defaults`. That is the ordinary argparse shape and it works.
The alternative is to resolve the handler after parsing, importing only the chosen module.

**Chose.** Lazy. `resolve_handler(command)` matches on the subcommand name and imports inside
the branch.

**Because.** Architecture invariant 5 says the live loop never imports from `research/`. Today
that is trivially true because `cli/research.py` imports nothing. From Phase 4 it registers
engines 20 `tournament` and 23 `backtest`, so it will import from `acsoe.research` — and an
eager dispatcher would then pull `research/` into the daemon's process on every `acsoe engine`.
Nothing would fail. That is precisely the problem: an invariant nobody can observe being broken
is one that gets broken. Making the import graph enforce it costs about fifteen lines now and
nothing later, whereas noticing it in Phase 4 means editing the entry point during the phase
that is trying to land the offline chain.

**Cost.** The handler is no longer discoverable from the parser, so `main()` dispatches on
`args.command` rather than calling an attribute argparse filled in. `tests/cli/test_entrypoints.py`
asserts the property directly, in a subprocess — this process has already imported all three
modules, so an in-process `sys.modules` check would pass for the wrong reason.

### The console health check cannot use `TestClient`

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

**What happened.** The obvious way to assert that `acsoe console` serves a health response is
`fastapi.testclient.TestClient(app).get("/health")`. It raises `NetworkAccessError` from C's
network guard.

**Why.** `TestClient` is an `httpx.Client` subclass and does not override `send`, and the guard
in `tests/conftest.py` patches `httpx.Client.send` for every test. The call never leaves the
process — `TestClient` uses an ASGI transport — but the guard sits above the transport and
cannot tell an in-process ASGI request from a real one. Reaching around it would have meant
relaxing the guard for convenience, which spec 14 forbids in as many words, and a guard that is
slightly over-broad is the correct trade for a system whose tests must never touch Kraken.

**Fix.** `asgi_get` in `tests/cli/test_entrypoints.py` drives the ASGI callable directly: it
builds an HTTP scope, awaits `app(scope, receive, send)`, and reassembles the status and body
from the messages the app sends back. No socket, no httpx, nothing to relax. It exercises the
same routing and response path uvicorn would, which is more than calling the endpoint function
would have proved.

**Consequence.** Worth knowing before Phase 1, when C tests the real console: the same
constraint applies to every HTTP assertion in this repository, and the twenty-line driver is
the answer rather than an exemption.

### `--ticks 3` would have made the test suite take two minutes

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

**What happened.** The natural test of the daemon is `acsoe engine --ticks 3`. `run_loop` sleeps
`timeframes.loop_tick_s` — sixty seconds — *between* ticks, so that is a two-minute test. It is
not a bug in the loop: the sleep is the loop tick, and a daemon that ticked without waiting
would hammer the exchange.

**Fix.** The end-to-end test through the dispatcher uses `--ticks 1`, which breaks before the
first sleep. Multi-tick behaviour is exercised by calling `run_loop` directly with
`tick_seconds=0.0`, which is the seam that exists precisely so cadence is set by the caller.
Deliberately did **not** add a `--tick-seconds` flag: an operator-visible knob that makes the
daemon spin faster than the exchange expects is a worse thing to have in the CLI than a
slightly less convenient test.

**Consequence.** The shutdown property that actually matters — that a stop request never lands
inside a tick — is tested by subclassing the real `Orchestrator`, setting the stop event from
inside `tick()`, and asserting exactly one tick completed. That is the manage chain's
guarantee: it runs every tick in every mode and is what records that an open position was
watched, so a tick abandoned halfway is a decision taken and never written down.

### `acsoe console` no longer carries a fallback application

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

**What happened.** While `src/acsoe/console/app.py` did not exist, `cli/console.py` carried its
own `build_placeholder_app` and fell back to it on `ImportError`. C's module landed during the
session and the fallback was deleted rather than kept as a safety net.

**Why.** Two applications that both answer `/health` mean a health endpoint that proves nothing:
`acsoe console` would look identical whether it was serving the console or serving the thing
that stands in for the console. Keeping it would also have been dead code the moment C's file
existed, and `console/` is C's path — a placeholder living in `cli/` was only ever justified by
the other file's absence.

**Fix.** `cli/console.py` imports `create_app` at module scope. If `acsoe.console.app` is ever
missing, the command fails loudly at import rather than quietly serving something else. The
import shape was agreed with C directly before either of us wrote to it: `create_app(config) ->
FastAPI`, taking the `Config` **Protocol** from `core/contracts.py` rather than my concrete
model, so `console/` does not depend on `platform/`.

### The null count in `platform/config.py` said ten and the file has nine

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

**What happened.** Two docstrings in `platform/config.py` — the module header and
`_refuse_nulls` — said `config/default.yaml` carries ten OPERATOR REQUIRED nulls and that the
loader reports "all ten" at once. It carries nine.

**Why.** `safety.error_rate_window_s` was originally null and was set to `3600` after B pointed
out that `architecture-context.md` specifies the trailing hour, so the value was specified all
along and never operator-required. The code was correct — it counts what it finds — but the
prose was written when the answer was ten and nobody re-read it when the tenth key was filled.

**Fix.** Both corrected to nine. `AGENTS.md` requires that an implementation contradicting a
context file be fixed in the same change; this is the same defect one level down, in a
docstring rather than a document. Recording it because it is exactly the class of drift
`docs_vocabulary` exists to catch and cannot: a bare count is not a distinctive token, so no
grep would ever have found it.

**Consequence.** `tests/cli/test_entrypoints.py` asserts that the refusal message names all
nine keys **and** that it does not name `safety.error_rate_window_s`. Listing a key the
operator does not have to supply is not a cosmetic error — it trains them to skim the list, and
the list is the only thing standing between a fresh clone and a daemon trading on numbers
nobody chose.

### A test that encoded a transitional state as a permanent assertion

**Agent:** A · **Task:** specs 07, 09 · **Date:** 2026-09-08

**What happened.** The operator supplied all nine OPERATOR REQUIRED values and three of my
tests went red:
`test_engine_refuses_the_committed_config_and_names_the_unset_keys`,
`test_console_refuses_the_committed_config` and
`test_default_yaml_refuses_to_load_and_names_every_operator_key`. Each asserted that
`config/default.yaml` **refuses to load**. With zero nulls in the file, it loads.

**Why.** The assertion was true on the day it was written and was never going to stay true. It
conflated two different things: *the behaviour* — a null OPERATOR REQUIRED key must stop the
process, which is permanent — and *the state of one file on one day* — the shipped config
happens to carry nine of them, which was always transitional. Writing the behaviour test
against the shipped file was convenient (the fixture already existed, committed) and that
convenience is exactly what welded the two together. The failure direction is worth naming: the
tests broke because the config became **more** valid, which is not a direction anyone writes a
test expecting to be pushed in.

**Fix.** Moved the assertion rather than deleting it. The refusals now run against a config the
test fabricates — `unset_operator_config` in `tests/cli/test_entrypoints.py`, `with_nulled()` in
`tests/platform/test_config.py` — built by taking the shipped file and setting the nine keys
back to `null`. The shipped file acquired the opposite assertions: it loads cleanly, `mode` is
`paper`, and each of the nine parses to its expected type. Nothing in `platform/config.py`
changed except two stale docstrings; `_refuse_nulls` still counts what it finds and never held a
list of key names, which is why zero nulls needed no code change at all.

**Consequence.** Three properties are now separately testable and all three are asserted: a null
OPERATOR REQUIRED key stops the process **by name** (nine parametrised cases, one per key, plus
the all-nine-at-once message); a null **anywhere** stops the process, so the machinery keeps its
teeth with zero nulls shipped; and the committed file is known-good. The general lesson, which
is the reason this is in the log: **assert the behaviour against a fixture you control, and
assert the committed artefact's state separately.** A test that reads a real file to prove a
rule will pin that file's contents whether or not anyone meant it to.

### The duplicated key list fired, in the direction nobody expected

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

**What happened.** `tests/cli/test_entrypoints.py` and `tests/platform/test_config.py` each hold
their own copy of the nine operator keys, deliberately unshared, so that a tenth key would make
both files fail loudly rather than silently inherit a value chosen elsewhere. It worked — but it
fired on the operator *filling the nine in*, not on a tenth being added.

**Why.** The duplication protects against a **change to the set**, and a value arriving is a
change to the set as surely as a key arriving. That is the mechanism behaving correctly; my note
in the previous session's progress file predicted only the addition case.

**Consequence.** With zero nulls in the shipped file, one direction of that signal was lost: the
lead can now add a tenth key **and supply a value for it**, and nothing would have noticed.
`test_the_file_marks_exactly_these_nine_keys_as_the_operator_s` restores it by scanning the
shipped file for its `Operator-chosen` marker and comparing the set to the tests' own list. That
marker is a documented convention — the header of `config/default.yaml` states it — not an
inference from formatting. The other direction still needs no marker: a tenth key added as
`null` survives the overlay in `complete_config_dict()` / `startable_config` and takes every test
using those fixtures down at once.

### A failing test bound a real socket

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

**What happened.** While `test_console_refuses_the_committed_config` was red, it did not merely
fail. `cli_main.main(["--config", DEFAULT_YAML, "console"])` no longer returned 2 at the config
check, so it fell through the whole entry point into `uvicorn.run` and tried to bind
127.0.0.1:8765 from inside the test suite. It surfaced as `SystemExit: 3` and an
`[Errno 10048] only one usage of each socket address` in the captured stderr.

**Why.** The test asserted a return code on a call with a side effect at the far end of it. As
long as the refusal happened, the side effect was unreachable, so the assertion and the guard
against the side effect were the same line — and when the assertion stopped holding, both went
at once.

**Fix.** `test_console_accepts_the_committed_config` stubs `uvicorn.run` before calling the
entry point, captures the app it was handed, and drives `/health` through it with the existing
`asgi_get` driver. Nothing in this repository may bind a port or reach a socket to prove a
config was accepted.

**Consequence.** Worth generalising before Phase 1, when C tests the real console: a test that
asserts a *refusal* from a function whose success path starts a server needs the server stubbed
regardless, because the refusal is the only thing standing between the test and the server, and
tests exist precisely for the days that refusal stops happening.
