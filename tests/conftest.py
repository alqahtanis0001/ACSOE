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
from datetime import UTC, datetime
from decimal import Decimal
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
def seed_fixtures(tmp_path: Path) -> Any:
    """B's seed generator run into a temporary database, with its named fixtures.

    Returns the `SeedFixtures` object rather than the path, because `seed_now` is
    on it and every console test that touches staleness needs a clock anchored to
    the seed rather than to wall time. `.db_path` is on it too.

    **The thresholds are injected from `config/default.yaml`**, which is the whole
    point of `SeedThresholds` being a parameter. Its defaults are documented as
    fixture-*shape* constants, not as recommended values, and one of them has
    already diverged: `max_errors_in_window` defaults to 10 while the operator set
    20. The seed overshoots a limit by three, so an uninjected fixture produced 13
    ERROR rows — over the default, comfortably under the config — and a Phase 3
    test of engine 17's error-rate input against it found the condition untripped
    and **failed pointing at the engine**. Nothing raised; the fixture was simply
    built against a limit nobody uses.

    `scripts/verify.py` has always done this, which is why `seed_fixtures_present`
    reports 23 ERROR rows where this fixture reported 13. Making `seed.py`'s
    defaults track the config instead would have the seed claim to know a trading
    threshold, which is exactly the coupling the injection exists to prevent — so
    the injection belongs here, in the fixture, and not there.

    Never under `data/`: `data/` is gitignored and no test or criterion may depend
    on anything inside it.
    """
    seed = pytest.importorskip(
        "acsoe.clients.store.seed", reason="the seed generator does not exist yet"
    )
    return seed.seed_database(tmp_path / "acsoe.sqlite", thresholds=seed_thresholds_from_config())


def seed_thresholds_from_config() -> Any:
    """`SeedThresholds` built from the committed config, or the defaults without one.

    A missing `config/default.yaml` is not an error here: several tests that use the
    seed run on trees where it has not been written yet, and the shape constants are
    a legitimate fallback for those. A key that is *present and null* is a different
    thing and is deliberately left to `SeedThresholds` to default, because "the
    operator has not decided yet" must not become a number this file invented.
    """
    seed = pytest.importorskip("acsoe.clients.store.seed")
    if not (REPO_ROOT / "config" / "default.yaml").is_file():
        return seed.SeedThresholds()
    config = load_default_config()
    fields = {
        "max_consecutive_data_blocks": int,
        "max_drawdown_pct": Decimal,
        "max_consecutive_losses": int,
        "error_rate_window_s": int,
        "max_errors_in_window": int,
    }
    supplied: dict[str, Any] = {}
    for name, cast in fields.items():
        dotted = "safety." + name
        try:
            value = config.get(dotted)
        except KeyError as absent:
            # ABSENT is not the same fact as PRESENT-AND-NULL, and this function used to
            # answer both with `continue`. `Config.get` raises on a miss and returns None
            # for a null - its docstring says so in as many words - so the information to
            # tell them apart was always here and was being discarded.
            #
            # Skipping an absent key silently returns the seed to `seed.py`'s shape
            # defaults, which is the exact defect this function exists to prevent and
            # which the docstring above recounts: the seed scaled to 10 against the
            # operator's 20, and a Phase 3 test of engine 17's error-rate input failed
            # pointing at the engine. A renamed or removed key must not be able to do
            # that again quietly.
            raise KeyError(
                f"{dotted} is not in config/default.yaml. The seed scales its fixtures "
                "to the operator's configured limits, and a key it cannot find would "
                "silently return it to seed.py's own shape constants - which are "
                "documented as fixture shapes, not recommended values. If the key was "
                "renamed, rename it here too; if it was removed, decide deliberately "
                "what the seed should overshoot instead. Do not let this default."
            ) from absent
        if value is not None:
            supplied[name] = cast(str(value)) if cast is Decimal else cast(value)
    return seed.SeedThresholds(**supplied)


@pytest.fixture
def seeded_db(seed_fixtures: Any) -> Path:
    """Just the path, for a test that does not care which fixtures are in it."""
    path: Path = seed_fixtures.db_path
    return path


@pytest.fixture
def seed_clock(seed_fixtures: Any) -> FixedClock:
    """A clock standing exactly at the seed's own last moment.

    The seeded timestamps have no relationship to wall time, so a console test
    that used the real clock would find every figure hours stale and would be
    asserting against the gap between the fixture and today rather than against
    the console.
    """
    return FixedClock(datetime.fromtimestamp(seed_fixtures.seed_now / 1_000_000, tz=UTC))


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
