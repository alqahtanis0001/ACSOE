# Build log — Phase 0 — lead

Entries the lead owns directly. Consolidated into `docs/build-log/phase-0.md` at phase close.

Minimum headings per entry: What happened, Why, Fix.

## Entries

### The intermittent native memory fault in the seed write path, and why it was closed as a risk rather than a bug

**Agent:** Lead · **Task:** phase close · **Date:** 2026-09-08

**What happened.** `toolchain_green` fails intermittently — roughly one full-suite run in five —
because the pytest subprocess dies of a native memory fault rather than reporting a verdict.
Every observed instance surfaces in the same place: B's `seed.py:_write_trading_history` →
`client.write_trade` / `write_position` → pydantic `model_dump`, converging in pydantic-core's
`to_python`. Three distinct Windows statuses have been seen — `0xC0000005` ACCESS_VIOLATION,
`0xC0000374` HEAP_CORRUPTION and `0xC0000409` STACK_BUFFER_OVERRUN — plus one
`AttributeError: 'NoneType' object has no attribute '__dict__'` raised from inside `to_python`.
Every test passes whenever the process survives, and `seed_database` called 60 times outside
pytest is clean.

C's earlier figure was 6 failures in 20 runs; across the fuller sample it settles nearer 20%.
The rate is recorded as approximate on purpose — it is a probability, and no run count observed
here pins it more precisely than that.

**Why it was not root-caused.** It was investigated at length over a full session and the
investigation is closed as unsuccessful, not as pending. What was ruled out, each by direct
test rather than by argument:

- **pyarrow.** Not the cause; the fault occurs with it out of the picture.
- **`pytest-asyncio`.** Not the cause.
- **Test ordering.** Not the cause — the fault does not track a particular sequence, and
  `test_seed.py` alone still fails roughly 1 in 15 in isolation.
- **C's `root_import_path`.** The obvious suspect and not the cause. The swapper does create a
  second `PositionRow` class while instances of the first are still live, but 40 enter/exit
  cycles hammering `model_dump` across both do not crash, and the isolated `test_seed.py`
  failures never touch it at all.
- **The pydantic-core version.** Pinning a different build did not settle it.

The turbo-clock test — the one experiment that would have separated software from silicon — was
**inconclusive, and known to be inconclusive**: the active Windows power plan overrode the
setting, so the run that was supposed to be at reduced clocks was not.

**What is left.** The machine is an i9-14900HX, the same B0 die as the 14900K. The remaining
variable is hardware, and hardware is out of scope for this project. Three different fault
statuses converging on one hot native call path, with no reproduction outside the pytest
process and no software variable surviving elimination, is the shape of a hardware fault; it is
not proof of one, and this entry does not claim it is. The suspicion is recorded as a suspicion.

**Fix.** None available at this level, so the fault is **mitigated rather than repaired**, and
the mitigation is written to keep it visible:

1. `toolchain_green` already separates a crash from a verdict. `describe_exit` classifies each
   tool's returncode against that tool's own documented range (pytest 0–5, mypy and ruff 0–2),
   names the Windows NTSTATUS or POSIX signal, and quotes the summary line the run had already
   printed. A process that prints `520 passed` and then dies no longer reads as a failing suite.
2. The criterion now **retries a crash once, and only a crash.** A clean retry reports PASS with
   the crash named in the message. A second crash FAILs, with the `CRASH -` prefix. A verdict —
   any returncode inside the tool's own range — is never retried, at any exit code, ever.

That second rule is the whole design. Retrying a verdict is the "re-run until it goes green"
habit that turns a memory fault into a flaky test, which is precisely what `describe_exit` was
written to prevent; the retry would have re-introduced it through the back door. The bound of
one attempt is for the same reason: two crashes in a row is no longer noise worth absorbing.
Four tests in `tests/verify/test_phase0_criteria.py` pin both boundaries — clean retry passes
with the crash named, second crash fails, a verdict is not retried, and a verdict on the retry
stands as the verdict with the crash kept as context.

**Consequence.** This is now a **known risk, not an open question**, and it is recorded as one
in `context/progress-tracker.md`. Nobody should re-open it by re-running the suite to see
whether the result changes — that experiment has been run and its answer is the 20%. What would
justify re-opening it: the fault appearing on a second machine, appearing outside the seed write
path, or the retry starting to fail twice in a row with any regularity. The last of those is
what the bound exists to surface: if the gate begins reporting `CRASH -` after a retry, the rate
has moved and the assumption behind the mitigation no longer holds.

One consequence to carry forward. The seed write path is B's, and it is exercised hard by every
full-suite run; Phase 2 onward adds engines that write through the same client. If the crash
rate rises as that path gets busier, the mitigation will stop being adequate and the hardware
question will have to be answered by the operator on different hardware, not by an agent here.
