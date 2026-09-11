"""`scripts/record.py` is standalone, and this proves it in a real subprocess.

Order-book and spread history cannot be backfilled, so the recorder has to be the
one piece of this system that can be copied to a bare server on its own and
started. `tests/platform/test_record_format.py` already asserts that no `import`
line in the file mentions `acsoe` — but that is a scan of the source text, and a
source scan cannot see an import that happens at runtime: inside a function, via
`importlib`, through a `sys.path` entry a helper appends, or as a transitive
consequence of importing something that imports the package. Every one of those
would pass the text check and fail on the server.

So this file runs the script in a **separate interpreter** with the repository's
own `src/` unreachable, and asserts on `sys.modules` afterwards. That is the only
form of the assertion that can actually fail for the right reason.

Two further properties are proved the same way, because both are things the
script has to do on a machine where nothing has been set up for it:

- it creates its output directories itself, rather than assuming somebody ran the
  package's startup code that creates `data/`;
- it starts, parses its arguments and reaches its first real decision without a
  config file anywhere, because `config/recorder.yaml` will not have been copied
  either.

Nothing here touches the network. The recorder is driven with `--dry-run
--measure-s 0`, which derives nothing and connects to nothing, and with `--help`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_PY = REPO_ROOT / "scripts" / "record.py"

#: The recorder's own dependencies, and the entire list of them. A third name
#: appearing here is a decision about what has to be installed on the recording
#: server, which is exactly the kind of thing that should require editing a test.
ALLOWED_THIRD_PARTY = frozenset({"orjson", "websockets"})

TIMEOUT_S = 120


def _run(code: str, *, cwd: Path, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run `code` in a fresh interpreter with this repository's `src/` hidden.

    `-I` is isolated mode: no `PYTHONPATH`, no user site-packages, and the
    current directory is not put on `sys.path`. Without it the test would run
    with whatever the pytest process happened to have importable and would prove
    nothing about a bare server.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-I", "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=TIMEOUT_S,
        check=False,
    )


@pytest.fixture(scope="module")
def _acsoe_is_importable() -> bool:
    """Whether `acsoe` can be imported at all in this environment.

    If the package is not installed, "the subprocess did not import acsoe" is
    true for the wrong reason and the assertion below cannot fail. The test says
    so rather than passing quietly — this is the `pytest.importorskip` trap
    recorded in `tests/conftest.py`, in the other direction.
    """
    import importlib.util

    return importlib.util.find_spec("acsoe") is not None


def test_the_package_is_importable_so_the_next_test_can_fail(_acsoe_is_importable: bool) -> None:
    """The control. Without this, `test_..._imports_no_acsoe_module` proves nothing."""
    assert _acsoe_is_importable, (
        "acsoe is not installed in this environment, so a subprocess failing to "
        "import it is not evidence of anything. Run `pip install -e .[dev]`."
    )


def test_running_the_recorder_imports_no_acsoe_module(tmp_path: Path) -> None:
    """Load and drive `record.py`, then look at what actually got imported.

    The check is on `sys.modules` after the module has been executed *and* after
    its argument parsing and storage resolution have run, so a lazy import inside
    a function is in scope. A source scan cannot reach this.
    """
    result = _run(
        f"""
        import importlib.util, json, sys
        from pathlib import Path

        spec = importlib.util.spec_from_file_location("rec", r"{RECORD_PY}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["rec"] = module
        spec.loader.exec_module(module)

        # Drive the parts that run before the socket opens.
        args = module.parse_args(["--out", r"{tmp_path / 'raw'}"])
        raw, summary, source_id = module.resolve_storage(args)
        module.JsonlWriter(raw, source_id=source_id).__enter__().close()

        acsoe = sorted(n for n in sys.modules if n == "acsoe" or n.startswith("acsoe."))
        print(json.dumps({{"acsoe": acsoe, "source_id": source_id}}))
        """,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["acsoe"] == [], (
        f"scripts/record.py pulled in {report['acsoe']} at runtime. It must import "
        f"nothing from the package: it has to run on a server that has no checkout."
    )
    assert report["source_id"]


def test_the_recorder_needs_only_its_own_two_dependencies(tmp_path: Path) -> None:
    """Whatever it imports beyond the standard library is `orjson` and `websockets`.

    This is the list somebody has to `pip install` on the recording server, and
    it is asserted rather than documented because a third entry added by accident
    is invisible until the day the server is rebuilt.
    """
    result = _run(
        f"""
        import importlib.util, json, sys, sysconfig
        from pathlib import Path

        before = set(sys.modules)
        spec = importlib.util.spec_from_file_location("rec", r"{RECORD_PY}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["rec"] = module
        spec.loader.exec_module(module)
        module.resolve_storage(module.parse_args(["--out", r"{tmp_path / 'raw'}"]))

        # "Third party" means "pip installed it into site-packages". Defining it
        # as "outside the stdlib directory" is wrong on Windows, where the
        # standard library's own C extensions (_socket, _ssl, _asyncio) live in
        # DLLs/ and would every one of them be reported as a dependency.
        sites = [
            Path(sysconfig.get_paths()[key]).resolve()
            for key in ("purelib", "platlib")
            if sysconfig.get_paths().get(key)
        ]
        third_party = set()
        for name in set(sys.modules) - before:
            top = name.split(".")[0]
            mod = sys.modules.get(top)
            origin = getattr(getattr(mod, "__spec__", None), "origin", None)
            if not origin or origin in ("built-in", "frozen"):
                continue
            resolved = Path(origin).resolve()
            if any(resolved.is_relative_to(site) for site in sites):
                third_party.add(top)
        third_party.discard("rec")
        print(json.dumps(sorted(third_party)))
        """,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    imported = set(json.loads(result.stdout.strip().splitlines()[-1]))
    # PyYAML is read opportunistically for the config and is allowed to be here;
    # the point of the assertion is that nothing ELSE crept in.
    assert imported - {"yaml"} <= ALLOWED_THIRD_PARTY, (
        f"scripts/record.py now needs {sorted(imported - ALLOWED_THIRD_PARTY)} as well. "
        f"Every name here has to be installed on the recording server."
    )


def test_it_runs_from_a_directory_with_no_project_in_it(tmp_path: Path) -> None:
    """The real shape of the claim: copy the one file somewhere else and start it.

    No `src/`, no `config/`, no repository — a working directory containing the
    script and nothing else, which is how it will sit on the server.
    """
    elsewhere = tmp_path / "server"
    elsewhere.mkdir()
    copied = elsewhere / "record.py"
    copied.write_bytes(RECORD_PY.read_bytes())

    result = subprocess.run(
        [sys.executable, "-I", str(copied), "--help"],
        capture_output=True,
        text=True,
        cwd=elsewhere,
        timeout=TIMEOUT_S,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--source-id" in result.stdout
    assert not (elsewhere / "config").exists()


def test_it_creates_its_own_output_directory(tmp_path: Path) -> None:
    """Nothing else has run, so nothing else has made `data/raw/`.

    The package creates its directories at startup; the recorder starts before
    the package exists and after it has been copied away from it, so it makes its
    own. Asserted through a subprocess with no config anywhere, because that is
    also the moment the default path has to apply.
    """
    elsewhere = tmp_path / "server"
    elsewhere.mkdir()
    copied = elsewhere / "record.py"
    copied.write_bytes(RECORD_PY.read_bytes())
    target = elsewhere / "deep" / "nested" / "raw"
    assert not target.exists()

    result = _run(
        f"""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("rec", r"{copied}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["rec"] = module
        spec.loader.exec_module(module)
        with module.JsonlWriter(__import__("pathlib").Path(r"{target}")) as writer:
            writer.write(
                module.build_line(
                    kind="tick", pair="BTC/USD", channel="book", ts_exchange=None,
                    ts_recv="2026-09-11T00:00:00.000000Z", payload={{"channel": "book"}},
                )
            )
        print("wrote", writer.path_for("2026-09-11").name)
        """,
        cwd=elsewhere,
    )
    assert result.returncode == 0, result.stderr
    assert target.is_dir(), "the recorder did not create its own output directory"
    written = list(target.glob("*.jsonl"))
    assert len(written) == 1
    assert written[0].name.startswith("kraken_v2__")
    assert written[0].name.endswith("__2026-09-11.jsonl")


def test_a_missing_config_is_not_an_error_but_a_named_one_is(tmp_path: Path) -> None:
    """No config file means built-in defaults; `--config nowhere.yaml` is a refusal.

    The asymmetry is deliberate and is the reason this is asserted. A recorder
    that refused to start because a file describing *where to put files* was
    absent would be an outage in the one process whose data cannot be backfilled.
    But an operator naming a file is a statement that it should be there, and
    silently ignoring it would write a day of recordings to the wrong disk.
    """
    elsewhere = tmp_path / "server"
    elsewhere.mkdir()
    copied = elsewhere / "record.py"
    copied.write_bytes(RECORD_PY.read_bytes())

    result = _run(
        f"""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("rec", r"{copied}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["rec"] = module
        spec.loader.exec_module(module)

        raw, summary, source_id = module.resolve_storage(module.parse_args([]))
        print("defaults", raw, summary)

        try:
            module.resolve_storage(module.parse_args(["--config", r"{elsewhere / 'nope.yaml'}"]))
        except (FileNotFoundError, ImportError) as exc:
            print("refused", type(exc).__name__)
        else:
            print("ACCEPTED A MISSING CONFIG")
        """,
        cwd=elsewhere,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "defaults" in out
    assert str(Path("data") / "raw") in out
    assert "refused" in out, out
    assert "ACCEPTED A MISSING CONFIG" not in out
