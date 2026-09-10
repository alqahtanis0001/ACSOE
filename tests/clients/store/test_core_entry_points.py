"""The two writes `core/` makes, and the constraint that shapes both of them.

Invariant 0: `core/` imports nothing from the rest of the package. The command reader
gets away with duck-typing today only because it exclusively *reads* attributes off rows
this client hands it — a write is a different problem, because a write needs a
constructor, and `write_run(row: RunRow)` needs one it cannot import.

So `start_run` and `set_system_mode` take `str` and `int` and nothing else, and
`test_core_can_use_both_writes_importing_only_the_client` proves it the way
`commands_round_trip` proves its own claim: **no double**. A real `StoreClient`, a real
migration, real SQLite, and a **fresh interpreter** whose entire import of this package is
`StoreClient`. A seam exercised only through a double is not tested.
"""

from __future__ import annotations

import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from acsoe.clients.store.client import StoreClient, StoreError
from acsoe.clients.store.contracts import RunMode, RunRow, SystemMode

# --------------------------------------------------------------------------- #
# The no-import proof
# --------------------------------------------------------------------------- #

#: Run in a subprocess, verbatim. Written the way `core/orchestrator.py` will have to
#: write it: primitives in, nothing from `clients/` imported but the client itself, and
#: no row constructed anywhere.
#:
#: Asserting on this text is not decoration. A test in *this* file cannot demonstrate the
#: absence of an import, because this file imports `RunRow` two lines up for its other
#: tests — the only honest proof is a separate caller whose source can be read and whose
#: execution can be observed, which is what the two halves below do together.
CORE_STYLE_CALLER = '''
import sys

from acsoe.clients.store.client import StoreClient

client = StoreClient(sys.argv[1])
client.migrate()

# Startup: the orchestrator has a run_id, a mode string and a timestamp. Nothing else.
client.start_run("run-core", mode="paper", started_at=1_000)

# After a transition the command reader has applied to state["system"]["mode"].
applied = client.set_system_mode("run-core", "running", at=2_000)
unknown = client.set_system_mode("run-that-does-not-exist", "frozen", at=2_000)

row = client.system_mode("run-core")
client.close()

assert applied is True, "the run exists, so the write must land"
assert unknown is False, "an unknown run is reported, not raised"
assert row is not None and row.mode == "running" and row.at == 2_000
print("OK")
'''

#: Tokens whose presence in the caller would void the proof. `Row(` catches constructing
#: any contract model; `contracts` catches importing the module the models live in.
FORBIDDEN_IN_CALLER = ("contracts", "Row(", "SystemMode", "RunMode")


def test_the_core_style_caller_imports_no_contract_and_builds_no_row() -> None:
    """Half one: the caller's source is genuinely primitive-only.

    Checked separately from running it, because a script that ran fine while importing
    `RunRow` would prove the opposite of what this file claims.
    """
    for token in FORBIDDEN_IN_CALLER:
        assert token not in CORE_STYLE_CALLER, (
            f"the core-style caller mentions {token!r}, so it no longer demonstrates that "
            "core/ can use these methods without importing from clients/"
        )
    assert "from acsoe.clients.store.client import StoreClient" in CORE_STYLE_CALLER


def test_core_can_use_both_writes_importing_only_the_client(tmp_path: Path) -> None:
    """Half two: that same source actually works, in a fresh interpreter.

    A subprocess rather than an `exec`, so the import graph is built from nothing and this
    test file's own imports cannot satisfy the script's by accident.
    """
    script = tmp_path / "core_style_caller.py"
    script.write_text(CORE_STYLE_CALLER, encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(script), str(tmp_path / "acsoe.sqlite")],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, (
        f"the core-style caller failed:\nstdout: {completed.stdout}\n"
        f"stderr: {completed.stderr}"
    )
    assert "OK" in completed.stdout


# --------------------------------------------------------------------------- #
# start_run
# --------------------------------------------------------------------------- #


def test_start_run_records_the_process(store: StoreClient) -> None:
    store.start_run("run-a", mode="paper", started_at=1_000, acsoe_version="0.1.0")

    runs = store.latest_runs()

    assert len(runs) == 1
    assert (runs[0].run_id, runs[0].mode, runs[0].started_at) == ("run-a", RunMode.PAPER, 1_000)
    assert runs[0].acsoe_version == "0.1.0"
    assert runs[0].ended_at is None


def test_start_run_writes_no_system_mode(store: StoreClient) -> None:
    """The trap a new entry point is most likely to walk back into.

    Adding `system_mode` and `system_mode_at` to `runs` in spec 31 silently made
    `write_run` a writer of the mode, because they arrived in `RunRow.model_dump()`
    without anyone deciding they should. `start_run` names its columns explicitly instead
    of dumping a payload, so the same thing cannot happen here by omission.
    """
    store.start_run("run-a", mode="paper", started_at=1_000)

    row = store.system_mode("run-a")

    assert row is not None
    assert (row.mode, row.at) == (None, None)


def test_the_startup_write_then_a_shutdown_write_preserves_the_mode(
    store: StoreClient,
) -> None:
    """The whole lifecycle in one test, because it is the sequence that broke before.

    Start the run, set a mode, then amend the row at shutdown through `write_run` with a
    `RunRow` built at startup — the exact shape that would have reset a frozen daemon's
    persisted mode to NULL.
    """
    store.start_run("run-a", mode="paper", started_at=1_000)
    store.set_system_mode("run-a", "frozen", at=2_000)

    store.write_run(
        RunRow(
            run_id="run-a", mode=RunMode.PAPER, started_at=1_000, ended_at=5_000,
            updated_at=5_000,
        )
    )

    row = store.system_mode("run-a")
    assert row is not None
    assert (row.mode, row.at) == (SystemMode.FROZEN, 2_000)
    assert store.latest_runs()[0].ended_at == 5_000


def test_starting_the_same_run_twice_is_refused(store: StoreClient) -> None:
    """`run_id` is minted once per process, so a second start is a bug, not a restart.

    Refused rather than upserted deliberately. An upsert would rewrite `started_at`, and
    the console decides the current run from the newest `runs` row — so the silent
    version of this defect reorders the two rows the restart banner compares.
    """
    store.start_run("run-a", mode="paper", started_at=1_000)

    with pytest.raises(StoreError, match="already exists"):
        store.start_run("run-a", mode="paper", started_at=9_000)

    assert store.latest_runs()[0].started_at == 1_000, "the original row is untouched"


def test_start_run_refuses_an_unrecognised_mode(store: StoreClient) -> None:
    """A defect, not a missing row: writing nothing for a typo would leave the console
    reading a run that does not exist, silently and forever."""
    with pytest.raises(StoreError, match="unknown run mode"):
        store.start_run("run-a", mode="pape", started_at=1_000)

    assert store.latest_runs() == ()


def test_start_run_accepts_every_mode_the_schema_allows(store: StoreClient) -> None:
    """Including `live`. This method records what it is told; invariant 1's three
    switches are `platform/live_guard.py`'s job, and a store that refused to record a
    live run would make a real one unauditable."""
    for index, mode in enumerate(sorted(member.value for member in RunMode)):
        store.start_run(f"run-{index}", mode=mode, started_at=1_000 + index)

    assert {row.mode.value for row in store.latest_runs(limit=10)} == {
        member.value for member in RunMode
    }


# --------------------------------------------------------------------------- #
# set_system_mode with a plain string
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", ["idle", "running", "frozen"])
def test_a_plain_string_mode_is_accepted_and_stored(store: StoreClient, mode: str) -> None:
    """The guarantee the lead asked to have written down rather than inferred.

    `SystemMode` is a `StrEnum`, so passing a bare string has always worked — but "it
    happens to work" should not be load-bearing under the status band, and `core/` may not
    import the enum at all.
    """
    store.start_run("run-a", mode="paper", started_at=1_000)

    assert store.set_system_mode("run-a", mode, at=2_000) is True

    row = store.system_mode("run-a")
    assert row is not None
    assert row.mode == mode
    assert row.mode is SystemMode(mode)


def test_a_string_and_the_enum_are_interchangeable(store: StoreClient) -> None:
    store.start_run("run-a", mode="paper", started_at=1_000)
    store.start_run("run-b", mode="paper", started_at=1_000)

    store.set_system_mode("run-a", "running", at=2_000)
    store.set_system_mode("run-b", SystemMode.RUNNING, at=2_000)

    first = store.system_mode("run-a")
    second = store.system_mode("run-b")
    assert first is not None and second is not None
    assert first.mode == second.mode


def test_an_unrecognised_system_mode_raises_rather_than_returning_false(
    store: StoreClient,
) -> None:
    """The two failure modes are not alike and must not share a return value.

    An unknown run is a race the caller logs and continues past. A misspelled mode is a
    defect, and reporting it as `False` would be indistinguishable from the race — the
    console would sit on a stale mode with nothing anywhere saying why.
    """
    store.start_run("run-a", mode="paper", started_at=1_000)

    with pytest.raises(StoreError, match="unknown system mode"):
        store.set_system_mode("run-a", "runnning", at=2_000)

    row = store.system_mode("run-a")
    assert row is not None
    assert row.mode is None, "nothing was written"


def test_the_two_failures_are_distinguishable_by_type(store: StoreClient) -> None:
    """Stated as a test because it is the property the caller branches on: `core/` logs a
    `False` and lets the tick continue; an exception is a defect it should not swallow."""
    store.start_run("run-a", mode="paper", started_at=1_000)

    assert store.set_system_mode("run-missing", "running", at=2_000) is False
    # `match=` rather than the bare form: `StoreError` is raised from four places in this
    # client, so the bare assertion cannot tell the failure induced here from one that
    # happened first. `code-standards.md` gained that rule on 2026-09-10 after A found the
    # same shape in `clients/kraken/`, where every fail-closed path raises one type.
    with pytest.raises(StoreError, match="unknown system mode"):
        store.set_system_mode("run-a", "nonsense", at=2_000)


def test_the_startup_write_moves_the_console_watermark(store: StoreClient) -> None:
    """`runs` is in `WATERMARK_TABLES`. The console polls the watermark, so a run record
    that did not move it would leave the first tick invisible until something else
    wrote."""
    assert store.watermark() == 0

    store.start_run("run-a", mode="paper", started_at=7_000)

    assert store.watermark() == 7_000


def test_the_seed_still_writes_no_system_mode(seeded_db: Path) -> None:
    """Unchanged by the new entry point, and re-asserted here because `start_run` is a
    second way into the same table. A seeded `running` would let the console's Running
    test pass without a daemon ever having written one."""
    with StoreClient(seeded_db) as seeded:
        modes = [row.system_mode for row in seeded.latest_runs(limit=100)]

    assert modes != []
    assert modes == [None] * len(modes)


def test_money_is_not_involved_anywhere_in_this_path(store: StoreClient) -> None:
    """A guard against the obvious future edit. `runs` carries no money column, and if
    one is ever added it must not arrive through a primitive-taking entry point that
    would accept a `float` from `core/` without complaint."""
    store.start_run("run-a", mode="paper", started_at=1_000)
    row = store.latest_runs()[0]

    assert not any(isinstance(value, (Decimal, float)) for value in row.model_dump().values())
