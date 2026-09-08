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
