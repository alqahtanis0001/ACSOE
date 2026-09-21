"""The Phase 8 criteria, written PENDING-first (task C0, operator ruling 2026-09-21).

Each criterion is observed three ways, as spec 141 did for Phase 7: **PENDING** where its
subject is not built, **PASS** against a correct implementation, and **FAIL** against a
plausible wrong one. Fabricated trees are used wherever a real one would make the test
report on the developer's own repository instead of on the state under test.

Where each stands today, and why:

* `live_client_serves_the_stream` — PENDING: the live facade does not forward `recent_trades`
  or `drain_gaps` (F1).
* `pair_rules_key_on_engine_names` — PENDING: the live mapper keys all 1,450 recorded pairs
  by REST names (F3).
* `console_refuses_a_foreign_origin` — PENDING: a cross-origin POST is accepted today.
* `daemon_reads_the_real_exchange` — PENDING: no smoke-run digest is committed yet.

**The scope is deliberate.** There is no criterion here for `mode: live`, the live order
surface, `close_all` live or the soak: the operator deferred all four on 2026-09-21, and a
criterion for work nobody is doing is a PENDING that means nothing.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.verify.conftest import fabricate_package
from tests.verify.test_phase2_criteria import assert_fail, assert_pass, assert_pending, run

PHASE8_CRITERIA = (
    "live_client_serves_the_stream",
    "pair_rules_key_on_engine_names",
    "console_refuses_a_foreign_origin",
    "daemon_reads_the_real_exchange",
)

# A protocol with two members and a client that forwards them, as the live facade should.
CONTRACTS_WITH_PROTOCOL = """
from typing import Protocol, runtime_checkable

@runtime_checkable
class MarketStreamProtocol(Protocol):
    def recent_trades(self) -> tuple[object, ...]: ...
    def drain_gaps(self) -> tuple[object, ...]: ...
"""

CLIENT_FORWARDING = """
class KrakenClient:
    def recent_trades(self):
        return ()

    def drain_gaps(self):
        return ()
"""

CLIENT_MISSING = """
class KrakenClient:
    def drain(self):
        return ()
"""

CLIENT_NOT_CALLABLE = """
class KrakenClient:
    recent_trades = "a string, not a method"

    def drain_gaps(self):
        return ()
"""


def _kraken_tree(tmp_path: Path, client_source: str) -> Path:
    fabricate_package(
        tmp_path,
        {
            "acsoe.clients.kraken.contracts": CONTRACTS_WITH_PROTOCOL,
            "acsoe.clients.kraken.client": client_source,
        },
    )
    return tmp_path


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def test_the_four_phase_8_criteria_are_registered(verify_module: ModuleType) -> None:
    """Membership and order: the report is read top to bottom, defect first."""
    names = [c.name for c in verify_module._REGISTRY[8]]
    for name in PHASE8_CRITERIA:
        assert name in names, f"{name} is not registered for phase 8"
    assert names[-4:] == list(PHASE8_CRITERIA)
    assert "docs_vocabulary" in names and "toolchain_green" in names


def test_phase_8_registers_nothing_for_the_deferred_work(verify_module: ModuleType) -> None:
    """The operator deferred `mode: live`, the order surface, `close_all` live and the soak
    on 2026-09-21. A criterion for work nobody is doing reports PENDING for ever and teaches
    a reader that the phase is further along than it is."""
    names = " ".join(c.name for c in verify_module._REGISTRY[8])
    for absent in ("live_guard", "close_all", "soak", "order_placed", "live_order"):
        assert absent not in names, f"phase 8 registers {absent!r}, which was deferred"


# --------------------------------------------------------------------------- #
# live_client_serves_the_stream
# --------------------------------------------------------------------------- #


def test_the_stream_walk_is_pending_while_the_facade_does_not_forward(
    verify_module: ModuleType, unbuilt_tree: Path, tmp_path: Path
) -> None:
    root = _kraken_tree(unbuilt_tree, CLIENT_MISSING)
    outcome = run(verify_module, "live_client_serves_the_stream", root)

    assert_pending(outcome, verify_module)
    assert "recent_trades" in outcome.message and "drain_gaps" in outcome.message


def test_the_stream_walk_passes_when_every_member_is_forwarded(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    root = _kraken_tree(unbuilt_tree, CLIENT_FORWARDING)
    outcome = run(verify_module, "live_client_serves_the_stream", root)

    assert_pass(outcome, verify_module)
    assert "2 walked" in outcome.message


def test_the_stream_walk_fails_on_a_member_that_is_not_callable(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    """The wrong implementation that a presence check would miss: the name exists, so
    `hasattr` is satisfied, and the chain still cannot call it."""
    root = _kraken_tree(unbuilt_tree, CLIENT_NOT_CALLABLE)
    outcome = run(verify_module, "live_client_serves_the_stream", root)

    assert_fail(outcome, verify_module)
    assert "recent_trades" in outcome.message


def test_the_stream_walk_is_pending_on_a_tree_with_no_client(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    outcome = run(verify_module, "live_client_serves_the_stream", unbuilt_tree)

    assert_pending(outcome, verify_module)


# --------------------------------------------------------------------------- #
# pair_rules_key_on_engine_names
# --------------------------------------------------------------------------- #

REST_KEYED_MAPPER = """
class _Rules:
    def __init__(self, pairs):
        self.pairs = pairs

def map_asset_pairs(result, *, fetched_at):
    # Keyed by the REST name, which is the defect (F3).
    return _Rules({str(name): object() for name in result})
"""

V2_KEYED_MAPPER = """
import json
from pathlib import Path

class _Rules:
    def __init__(self, pairs):
        self.pairs = pairs

def map_asset_pairs(result, *, fetched_at):
    names = json.loads(
        Path("tests/fixtures/kraken/pair_names_recorded_2026-09-19.json").read_text(
            encoding="utf-8"
        )
    )["pairs"]
    by_rest = {key: entry["v2_symbol"] for key, entry in names.items()}
    return _Rules({by_rest[str(name)]: object() for name in result if str(name) in by_rest})
"""

HALF_MAPPED_MAPPER = """
import json
from pathlib import Path

class _Rules:
    def __init__(self, pairs):
        self.pairs = pairs

def map_asset_pairs(result, *, fetched_at):
    names = json.loads(
        Path("tests/fixtures/kraken/pair_names_recorded_2026-09-19.json").read_text(
            encoding="utf-8"
        )
    )["pairs"]
    by_rest = {key: entry["v2_symbol"] for key, entry in names.items()}
    pairs = {}
    for index, name in enumerate(result):
        key = str(name)
        # Half remapped, half left as REST names: the partial migration.
        pairs[by_rest.get(key, key) if index % 2 == 0 else key] = object()
    return _Rules(pairs)
"""


def _rules_tree(tmp_path: Path, repo_root: Path, mapper: str) -> Path:
    """A tree carrying the two recorded fixtures and a fabricated mapper."""
    fixtures = tmp_path / "tests" / "fixtures" / "kraken"
    fixtures.mkdir(parents=True, exist_ok=True)
    for name in (
        "asset_pairs_recorded_2026-09-19.json",
        "pair_names_recorded_2026-09-19.json",
    ):
        shutil.copy(repo_root / "tests" / "fixtures" / "kraken" / name, fixtures / name)
    fabricate_package(tmp_path, {"acsoe.clients.kraken.rest": mapper})
    return tmp_path


def test_pair_rules_is_pending_while_the_mapper_keys_rest_names(
    verify_module: ModuleType, unbuilt_tree: Path, repo_root: Path, monkeypatch: Any
) -> None:
    root = _rules_tree(unbuilt_tree, repo_root, REST_KEYED_MAPPER)
    outcome = run(verify_module, "pair_rules_key_on_engine_names", root)

    assert_pending(outcome, verify_module)
    assert "REST names" in outcome.message


def test_pair_rules_passes_when_every_key_is_the_engines_own_name(
    verify_module: ModuleType, unbuilt_tree: Path, repo_root: Path, monkeypatch: Any
) -> None:
    root = _rules_tree(unbuilt_tree, repo_root, V2_KEYED_MAPPER)
    monkeypatch.chdir(root)
    outcome = run(verify_module, "pair_rules_key_on_engine_names", root)

    assert_pass(outcome, verify_module)
    assert "the engines' own names" in outcome.message


def test_pair_rules_fails_on_a_half_finished_migration(
    verify_module: ModuleType, unbuilt_tree: Path, repo_root: Path, monkeypatch: Any
) -> None:
    """The dangerous middle state: some pairs remapped, some left REST-named. A check that
    only looked for *any* engine-named key would pass this and the universe would be half
    the size it should be."""
    root = _rules_tree(unbuilt_tree, repo_root, HALF_MAPPED_MAPPER)
    monkeypatch.chdir(root)
    outcome = run(verify_module, "pair_rules_key_on_engine_names", root)

    assert_fail(outcome, verify_module)
    assert "are not" in outcome.message


def test_pair_rules_is_pending_without_the_recording(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    outcome = run(verify_module, "pair_rules_key_on_engine_names", unbuilt_tree)

    assert_pending(outcome, verify_module)
    assert "not recorded yet" in outcome.message


# --------------------------------------------------------------------------- #
# console_refuses_a_foreign_origin
# --------------------------------------------------------------------------- #


class _StubApp:
    """An ASGI app that answers by `Origin`, standing in for the console.

    The criterion's own logic is what is under test here: building a real console needs a
    seeded database and the committed config, and fabricating those would test the
    fabrication rather than the rule.
    """

    def __init__(self, *, refuse_foreign: bool, refuse_own: bool = False) -> None:
        self.refuse_foreign = refuse_foreign
        self.refuse_own = refuse_own

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        origin = dict(scope["headers"]).get(b"origin", b"").decode()
        own = origin.endswith("console.verify")
        refuse = self.refuse_own if own else self.refuse_foreign
        status = 403 if refuse else 201
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})


@pytest.fixture
def stub_console(verify_module: ModuleType, monkeypatch: Any) -> Any:
    """Point the criterion at a stub app, leaving its seeding and config alone."""

    def install(app: Any) -> None:
        monkeypatch.setattr(
            verify_module, "seeded_console_db", lambda directory: (directory / "db.sqlite", None)
        )
        monkeypatch.setattr(verify_module, "console_config", lambda: (object(), None))
        monkeypatch.setattr(verify_module, "console_app", lambda config, db: (app, None))

    return install


def test_the_origin_check_is_pending_while_a_foreign_post_is_accepted(
    verify_module: ModuleType, tmp_path: Path, stub_console: Any
) -> None:
    stub_console(_StubApp(refuse_foreign=False))
    outcome = run(verify_module, "console_refuses_a_foreign_origin", tmp_path)

    assert_pending(outcome, verify_module)
    assert "no Origin check yet" in outcome.message


def test_the_origin_check_passes_when_foreign_is_refused_and_own_is_not(
    verify_module: ModuleType, tmp_path: Path, stub_console: Any
) -> None:
    stub_console(_StubApp(refuse_foreign=True))
    outcome = run(verify_module, "console_refuses_a_foreign_origin", tmp_path)

    assert_pass(outcome, verify_module)
    assert "403" in outcome.message and "201" in outcome.message


def test_the_origin_check_fails_when_the_operators_own_kill_switch_is_refused(
    verify_module: ModuleType, tmp_path: Path, stub_console: Any
) -> None:
    """The wrong fix: refuse everything. The kill switch has to keep working, and a check
    that only asserted the refusal would call this a pass."""
    stub_console(_StubApp(refuse_foreign=True, refuse_own=True))
    outcome = run(verify_module, "console_refuses_a_foreign_origin", tmp_path)

    assert_fail(outcome, verify_module)
    assert "its own origin" in outcome.message


# --------------------------------------------------------------------------- #
# daemon_reads_the_real_exchange
# --------------------------------------------------------------------------- #

GOOD_DIGEST = {
    "run_id": "daemon-20260921T000000Z",
    "mode": "paper",
    "client": "live",
    "ticks": 4,
    "scanned": 1450,
    "entered": 190,
    "refusals": {"cost:net_edge_below_hurdle": 4},
}


def _write_digest(root: Path, digest: Any) -> None:
    path = root / "tests" / "fixtures" / "phase8" / "smoke-digest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(digest), encoding="utf-8")


def test_the_smoke_run_is_pending_without_a_digest(
    verify_module: ModuleType, tmp_path: Path
) -> None:
    outcome = run(verify_module, "daemon_reads_the_real_exchange", tmp_path)

    assert_pending(outcome, verify_module)
    assert "smoke-digest.json" in outcome.message


def test_the_smoke_run_passes_on_a_paper_run_against_the_real_client(
    verify_module: ModuleType, tmp_path: Path
) -> None:
    _write_digest(tmp_path, GOOD_DIGEST)
    outcome = run(verify_module, "daemon_reads_the_real_exchange", tmp_path)

    assert_pass(outcome, verify_module)
    assert "1450 pairs scanned" in outcome.message
    assert "cost:net_edge_below_hurdle=4" in outcome.message


def test_the_smoke_run_fails_on_a_digest_from_the_fake_client(
    verify_module: ModuleType, tmp_path: Path
) -> None:
    """The whole point of the run is that the REAL client served it. A digest from the fake
    exchange would otherwise satisfy every other field."""
    _write_digest(tmp_path, {**GOOD_DIGEST, "client": "fake"})
    outcome = run(verify_module, "daemon_reads_the_real_exchange", tmp_path)

    assert_fail(outcome, verify_module)
    assert "client" in outcome.message


def test_the_smoke_run_fails_on_a_live_mode_digest(
    verify_module: ModuleType, tmp_path: Path
) -> None:
    """`mode: live` is a separate ruling (operator, 2026-09-21). A digest claiming live is
    either a mislabelled run or a scope breach, and both are FAIL."""
    _write_digest(tmp_path, {**GOOD_DIGEST, "mode": "live"})
    outcome = run(verify_module, "daemon_reads_the_real_exchange", tmp_path)

    assert_fail(outcome, verify_module)
    assert "separate ruling" in outcome.message


def test_the_smoke_run_fails_when_nothing_was_refused(
    verify_module: ModuleType, tmp_path: Path
) -> None:
    """At tier 1 the cost gate refuses everything, and the operator's requirement is that
    the screen shows it. A digest with no refusals means the funnel was not recorded."""
    _write_digest(tmp_path, {**GOOD_DIGEST, "refusals": {}})
    outcome = run(verify_module, "daemon_reads_the_real_exchange", tmp_path)

    assert_fail(outcome, verify_module)
    assert "no refusals" in outcome.message


def test_the_smoke_run_fails_on_a_digest_that_scanned_nothing(
    verify_module: ModuleType, tmp_path: Path
) -> None:
    _write_digest(tmp_path, {**GOOD_DIGEST, "scanned": 0})
    outcome = run(verify_module, "daemon_reads_the_real_exchange", tmp_path)

    assert_fail(outcome, verify_module)
    assert "scanned" in outcome.message


def test_the_smoke_run_fails_on_a_digest_missing_a_field(
    verify_module: ModuleType, tmp_path: Path
) -> None:
    digest = {k: v for k, v in GOOD_DIGEST.items() if k != "entered"}
    _write_digest(tmp_path, digest)
    outcome = run(verify_module, "daemon_reads_the_real_exchange", tmp_path)

    assert_fail(outcome, verify_module)
    assert "entered" in outcome.message
