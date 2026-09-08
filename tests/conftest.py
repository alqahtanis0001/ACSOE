"""Shared pytest scaffolding. Spec 14.

Every agent's tests draw their clock, database, config, context and `state` from
here, so four people writing tests against one system agree on what those are.

The one non-negotiable thing in this file is the **network guard**. It is autouse
and there is no opt-out fixture: `code-standards.md` says no test touches the
network, and spec 14 says do not relax the guard for convenience. Its negative
test - proof that it actually fires, on a real socket connect *and* a real httpx
request - is `tests/harness/test_network_guard.py`.

Layout each agent mirrors: `tests/<area>/test_*.py` matching the source path its
owner owns. `tests/harness/` and the shared fixtures are C's; nobody writes a test
for another agent's code.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Make `tests.harness.*` importable no matter how pytest was invoked, and before
# anything below imports it.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.harness.doubles import (  # noqa: E402
    FIXED_NOW,
    FakeClients,
    FixedClock,
    MappingConfig,
    load_default_config,
)
from tests.harness.doubles import fresh_state as _fresh_state  # noqa: E402
from tests.harness.fake_kraken import FakeKrakenClient, FakeRecorder  # noqa: E402
from tests.harness.network_guard import network_guard  # noqa: E402

VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify.py"


# --------------------------------------------------------------------------- #
# The network guard
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _block_the_network() -> Iterator[None]:
    """Fail any test that attempts an outbound connection.

    Both layers, per spec 14 step 7: the socket functions and the httpx client.
    Patching one and not the other is not a guard, because either can be reached
    without the other.
    """
    with network_guard():
        yield


# --------------------------------------------------------------------------- #
# Paths and the script under test
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def verify_module() -> ModuleType:
    """`scripts/verify.py`, imported as a module.

    It is a script rather than a package - C owns exactly that one file in
    `scripts/`, and a `scripts/verify/` directory would put two agents in one
    directory - so its tests load it by path.
    """
    spec = importlib.util.spec_from_file_location("acsoe_verify", VERIFY_SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"could not load {VERIFY_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["acsoe_verify"] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# Clock, config, state
# --------------------------------------------------------------------------- #


@pytest.fixture
def fixed_clock() -> FixedClock:
    """A clock that does not move unless the test moves it."""
    return FixedClock()


@pytest.fixture
def fixed_now() -> Any:
    return FIXED_NOW


@pytest.fixture
def paper_config() -> MappingConfig:
    """`config/default.yaml`, parsed, with `mode: paper` asserted.

    No key is null any more: the operator supplied all nine OPERATOR REQUIRED
    values on 2026-09-08, so the parsed config carries a real value everywhere.
    A test needing a threshold still passes it explicitly rather than reading it
    from here, so the test pins the value it asserts against and does not drift
    when the operator retunes the file.
    """
    if not (REPO_ROOT / "config" / "default.yaml").is_file():
        pytest.skip("config/default.yaml does not exist yet")
    return load_default_config()


@pytest.fixture
def fresh_state() -> dict[str, Any]:
    """`state` as the orchestrator hands it to the first engine of a tick."""
    return _fresh_state()


# --------------------------------------------------------------------------- #
# Clients
# --------------------------------------------------------------------------- #


@pytest.fixture
def fake_kraken() -> FakeKrakenClient:
    return FakeKrakenClient()


@pytest.fixture
def fake_recorder() -> FakeRecorder:
    return FakeRecorder()


@pytest.fixture
def migrated_db(tmp_path: Path) -> Path:
    """A fresh database file with every migration applied.

    Never under `data/`: `data/` is gitignored and no criterion or test may depend
    on anything inside it.
    """
    migrations = pytest.importorskip(
        "acsoe.clients.store.migrations", reason="db/migrations/ runner does not exist yet"
    )
    db_path = tmp_path / "acsoe.sqlite"
    migrations.apply_migrations(db_path)
    return db_path


@pytest.fixture
def store(migrated_db: Path) -> Iterator[Any]:
    """B's real store client against the migrated temporary database."""
    client_module = pytest.importorskip(
        "acsoe.clients.store.client", reason="the store client does not exist yet"
    )
    client = client_module.StoreClient(migrated_db)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def fake_clients(fake_kraken: FakeKrakenClient, fake_recorder: FakeRecorder) -> FakeClients:
    """The three injected clients, with no store attached.

    Ask for `fake_clients_with_store` when the code under test needs one; that
    fixture skips until B's client exists, and this one does not, so a test that
    never touches the store keeps running on a tree where it is missing.
    """
    return FakeClients(kraken=fake_kraken, store=None, recorder=fake_recorder)


@pytest.fixture
def fake_clients_with_store(
    fake_kraken: FakeKrakenClient, fake_recorder: FakeRecorder, store: Any
) -> FakeClients:
    return FakeClients(kraken=fake_kraken, store=store, recorder=fake_recorder)


@pytest.fixture
def engine_context(fixed_clock: FixedClock, paper_config: MappingConfig, fake_clients: Any) -> Any:
    """A built `EngineContext`, once `core/contracts.py` declares one.

    Skips until then rather than guessing at the dataclass - its fields are fixed
    in `engine-contracts.md` and adding one is an escalation to the operator, not
    something a test fixture invents.
    """
    contracts = pytest.importorskip(
        "acsoe.core.contracts", reason="core/contracts.py does not exist yet"
    )
    engine_context_cls = getattr(contracts, "EngineContext", None)
    if engine_context_cls is None:
        pytest.skip("acsoe.core.contracts.EngineContext does not exist yet")
    return engine_context_cls(
        mode="paper",
        run_id="test-run",
        now=fixed_clock.now(),
        config=paper_config,
        clients=fake_clients,
    )
