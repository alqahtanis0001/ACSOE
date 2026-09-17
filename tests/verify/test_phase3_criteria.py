"""The seven Phase 3 criteria, each proved three ways.

Spec 45's "Rules this spec is held to", which are the same two-sided proof specs 01,
16 and 33 established, plus the third that spec 45 adds:

* **PENDING** against a tree where the subject does not exist. A criterion that cannot
  reach that state makes a phase impossible to start, and three of these four engines
  were unbuilt or unwired when the criteria were written.
* **PASS** against the subject as it actually is, or against a fabricated minimal one
  where it does not exist yet. A criterion asserted only in the PENDING direction can
  be one that never manages to check anything.
* **FAIL**, deliberately induced. *"A check nobody has seen fail is a comment."* Every
  induced failure here is also written up in `docs/build-log/phase-3/c-interface.md`,
  because the point of inducing it is to find out whether the criterion notices the
  thing it claims to, and the answer is worth keeping.

The failures are chosen to be the ones that matter rather than the ones that are easy.
A cost gate with the fee compiled in; a risk gate that rounds a sub-minimum size *up*
to the minimum instead of refusing it; a universe that ignores the balance; a breaker
that escalates on drawdown after spec 37 ruled it a freeze; one that fires a tick early
on the outage; one that reads engine 19 out of `state`; a gate shipped with only a
happy path. Every one of those has either happened in this project or is a defect the
authority documents exist to prevent.

**Fabricate the subject; never fabricate the contract.** `phase3_tree` carries the real
`src/acsoe`, the real `db/migrations/`, the real `config/` and the real test harness,
and a FAIL is induced by overwriting exactly one module in that copy. A tree assembled
the other way round - fabricated contracts with a real engine dropped in - is how
`check_data_guard_blocks_bad_data` came to have a body that never executed while both
halves of its proof passed.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from tests.verify.conftest import fabricate_package
from tests.verify.test_phase2_criteria import (
    assert_fail,
    assert_pass,
    assert_pending,
    run,
)

PHASE3_CRITERIA = (
    "cost_gate_uses_live_fee_tier",
    "risk_rejects_sub_ordermin",
    "universe_varies_with_balance",
    "safety_freezes_on_drawdown_without_opportunity_chain",
    "safety_escalates_on_sustained_outage",
    "safety_inputs_all_from_the_seed",
    "phase_3_gates_have_both_tests",
)

_NO_PYCACHE = shutil.ignore_patterns("__pycache__", "*.pyc")


# --------------------------------------------------------------------------- #
# A tree the Phase 3 criteria can actually run in
# --------------------------------------------------------------------------- #


@pytest.fixture
def phase3_tree(bare_tree: Path, repo_root: Path) -> Path:
    """The real package, harness, migrations and config, copied so one file can be
    replaced.

    Deliberately not a fabricated `acsoe`. These criteria drive the real engine 1 into
    the real gate over the real seed through the real `StoreClient`, and the whole
    point of spec 45 is that a criterion judging a fabricated version of the contract
    it is held to will agree with whatever mistake the fabrication shares. So the tree
    is the real one and a FAIL is induced by overwriting a single module in the copy -
    which is also the honest picture of the failure being tested, since that is exactly
    what a wrong engine would look like on disk.

    `tests/harness/` and `tests/fixtures/` rather than all of `tests/`: the criteria
    import `tests.harness.doubles` and `tests.harness.fake_kraken`, and the fake client
    reads the committed Kraken envelopes out of `tests/fixtures/kraken/` - which is what
    makes "no criterion touches the network" true rather than aspirational. `tests/` as
    a whole is the largest thing that would otherwise be copied per test.
    `phase_3_gates_have_both_tests` reads `tests/engines/`, and the tests that exercise
    it write the files they want to see.
    """
    # `src/acsoe`, not `src` — the latter also drags in `acsoe.egg-info`, which is the
    # editable install's metadata and has no business in a fabricated tree. Nineteen
    # tests use this fixture, so everything copied here is copied nineteen times a run;
    # `conftest.py` already records a full-suite run filling the disk when the Phase 2
    # criteria added twenty more tree copies to a suite that had dozens.
    shutil.copytree(repo_root / "src" / "acsoe", bare_tree / "src" / "acsoe", ignore=_NO_PYCACHE)
    shutil.copytree(repo_root / "config", bare_tree / "config")
    shutil.copytree(repo_root / "db", bare_tree / "db", ignore=_NO_PYCACHE)
    tests = bare_tree / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "__init__.py").write_text("", encoding="utf-8")
    shutil.copytree(repo_root / "tests" / "harness", tests / "harness", ignore=_NO_PYCACHE)
    shutil.copytree(repo_root / "tests" / "fixtures", tests / "fixtures", ignore=_NO_PYCACHE)
    return bare_tree


def replace_module(root: Path, dotted: str, source: str) -> None:
    """Overwrite one real module in a copied tree, leaving everything else real."""
    path = root / "src" / Path(*dotted.split("."))
    path = path.with_suffix(".py")
    if not path.exists():
        raise AssertionError(f"{dotted} is not in the copied tree; the fixture is wrong")
    path.write_text(source, encoding="utf-8")


def patch_module(root: Path, dotted: str, old: str, new: str) -> None:
    """Change one exact string inside a real module in a copied tree.

    Preferred over `replace_module` wherever the induced defect is a *change* to real
    behaviour rather than a stand-in for it: the rest of the module stays real, so the
    criterion is still being run against the engine it judges and the FAIL is
    attributable to the one thing that moved. It raises rather than silently
    no-op-ing when the anchor text is not found, because a patch that misses turns an
    induced-failure test into one asserting the criterion fails for some other reason.
    """
    path = (root / "src" / Path(*dotted.split("."))).with_suffix(".py")
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise AssertionError(
            f"{dotted}: anchor appears {text.count(old)} times, expected exactly once. "
            "The engine moved underneath this test and the induced failure would not be "
            "the one it claims to induce."
        )
    path.write_text(text.replace(old, new), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Registration and the rules that apply to all seven
# --------------------------------------------------------------------------- #


def test_all_seven_criteria_are_registered_for_phase_3(verify_module: ModuleType) -> None:
    registered = {c.name for c in verify_module._REGISTRY[3]}
    assert set(PHASE3_CRITERIA) <= registered


def test_no_phase_3_criterion_touches_a_gitignored_directory(verify_module: ModuleType) -> None:
    """`data/`, `models/` and `logs/` are gitignored, so a criterion reaching into one
    passes only on the machine that produced it. The Phase 0 rule, applied to the
    Phase 3 section - and it is why the safety criteria seed into a temporary directory
    rather than reading `data/db/acsoe.sqlite`."""
    import inspect

    for name in PHASE3_CRITERIA:
        source = inspect.getsource(getattr(verify_module, "check_" + name))
        for forbidden in ('"data"', "'data'", '"models"', '"logs"', "data/db"):
            assert forbidden not in source, f"{name} reads a gitignored path: {forbidden}"


def test_no_phase_3_criterion_hardcodes_an_exchange_value(verify_module: ModuleType) -> None:
    """`AGENTS.md` rule 1: a remembered fee, tier threshold or order minimum is stale.

    The criteria may *inject* fee rates and an `ordermin` into the fake client - that is
    varying the fixture, which is the only way to prove the engine reads it - but none
    of them may compare against a remembered value, and none may name a Kraken pair as
    the pair under test. The pair is chosen from what engine 1 publishes.
    """
    import inspect

    for name in PHASE3_CRITERIA:
        source = inspect.getsource(getattr(verify_module, "check_" + name))
        for forbidden in ("XBT", "XXBTZUSD", "BTC/USD", "ETH/USD", "SOL/USD"):
            assert forbidden not in source, f"{name} names a pair rather than reading one"


# --------------------------------------------------------------------------- #
# cost_gate_uses_live_fee_tier
# --------------------------------------------------------------------------- #

#: A cost engine with the fee schedule compiled into it. It is otherwise a faithful
#: implementation of invariant 5 - it reads the candidate, the spread and the slippage
#: out of `state`, does the right arithmetic and blocks below the hurdle - so a
#: criterion checking a single tick passes against it. That is the whole point:
#: `AGENTS.md` opens by saying any remembered fee percentage is stale, and this is what
#: "stale" looks like when it is otherwise competent code.
#:
#: **It must publish engine 10's key set, and only a tick can say whether it still does.**
#: It carried `"fallbacks_used": []` from spec 45 until spec 117: faithful when written,
#: inert from the first day (engine 10's `_fallbacks()` already returned an empty tuple
#: unconditionally), and stale once spec 111 removed the field -- with this file at 48
#: passed on both sides of that removal.
#: `test_the_fabricated_cost_engine_publishes_engine_tens_key_set` is what re-checks it.
CONSTANT_FEE_COST_ENGINE = '''
import time
from decimal import Decimal
from typing import Any

from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.cost.contracts import (
    CANDIDATE_PAIR_PATH,
    MARKET_SENSOR_KEY,
    MARKET_SENSOR_QUOTES_KEY,
    ORDER_BOOK_KEY,
    PREDICTION_KEY,
)

MAKER = Decimal("0.0025")
TAKER = Decimal("0.0045")


class CostEngine(BaseEngine):
    name = "cost"
    number = 10
    is_gate = True

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()
        scout_key, pair_field = CANDIDATE_PAIR_PATH
        pair = state[scout_key][pair_field]
        spread = Decimal(state[MARKET_SENSOR_KEY][MARKET_SENSOR_QUOTES_KEY][pair]["spread_pct"])
        slippage = Decimal(state[ORDER_BOOK_KEY]["estimated_slippage_pct"])
        move = Decimal(state[PREDICTION_KEY]["expected_move_pct"])
        multiple = Decimal(str(context.config.get("trading.hurdle_multiple")))

        friction = MAKER + TAKER + spread + slippage
        net_edge = move - friction
        hurdle = multiple * friction
        clears = net_edge > hurdle
        data: dict[str, Any] = {
            "pair": pair,
            "expected_move_pct": format(move, "f"),
            "friction_pct": format(friction, "f"),
            "net_edge_pct": format(net_edge, "f"),
            "hurdle_pct": format(hurdle, "f"),
            "clears_hurdle": clears,
            "reason_code": None if clears else "net_edge_below_hurdle",
        }
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK if clears else EngineStatus.BLOCK,
            blocks_trading=not clears,
            reason=None if clears else "below the hurdle",
            data=data,
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
'''


def _double_cost_engine(tmp_path: Path) -> Any:
    """`CONSTANT_FEE_COST_ENGINE` as a class, against the **real** package.

    Loaded from a file by path rather than `exec`ed into a dict so it gets an ordinary
    module identity and its `from acsoe...` imports resolve the way they do in the
    fabricated tree. The tree is not needed here: the only thing being read off this
    engine is the shape of what it publishes.
    """
    path = tmp_path / "constant_fee_cost_engine.py"
    path.write_text(CONSTANT_FEE_COST_ENGINE, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("constant_fee_cost_engine", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CostEngine


def test_the_fabricated_cost_engine_publishes_engine_tens_key_set(
    verify_module: ModuleType, tmp_path: Path
) -> None:
    """Spec 117. The double is a claim about engine 10's payload, and this re-checks it.

    It stopped being true in spec 111 and **nothing went red**: the double kept
    publishing `fallbacks_used` after engine 10 dropped it, and this file was 48 passed
    on both sides of that change, because `check_cost_gate_uses_live_fee_tier` reads
    `net_edge_pct`, `clears_hurdle`, `hurdle_pct` and `reason_code` and never looks at
    the key set. `code-standards.md`: a double is the one claim in this codebase that
    nothing re-checks -- mypy does not compare the two, and the criterion passes
    precisely because it never asks.

    The comparison is deliberately **not** a copy of B's `COST_PAYLOAD_KEYS`. Both key
    sets are read off a tick, so this needs no list of field names to go stale in its
    turn, and it goes red whichever side moves: an extra key in the double, a missing
    one, or engine 10 changing its payload without the double following.

    It belongs here and not inside the criterion. The criterion drives this fabrication
    on its FAIL path, so a shape assertion there would be a test of the fabrication in
    the one arm where the fabrication is the subject -- and it would answer every
    induced-failure test in this file with a complaint about a key instead of the defect
    each one induces. The real engine's key set is pinned in B's lane, on the real
    engine, by `test_this_engine_publishes_no_fallback_field_and_the_key_set_is_pinned`.
    """
    contracts_mod, problem = verify_module.try_import("acsoe.engines.cost.contracts")
    assert contracts_mod is not None, problem
    config, problem = verify_module._phase3_config()
    assert config is not None, problem
    real_cls, problem = verify_module._engine_class("acsoe.engines.cost.engine", "cost")
    assert real_cls is not None, problem

    tier = verify_module.CHEAP_TIER
    real, _pair, problem = verify_module._cost_tick(config, contracts_mod, real_cls, *tier)
    assert real is not None, problem
    double, _pair, problem = verify_module._cost_tick(
        config, contracts_mod, _double_cost_engine(tmp_path), *tier
    )
    assert double is not None, problem

    # The real engine reached a full assessment. It publishes two keys and nothing else
    # on the missing-input block, so without this the comparison could be between two
    # refusals that agree with each other and say nothing about the shape under test.
    assert real.data["clears_hurdle"] is True
    # The double refuses this tier, which is the defect it exists to exhibit: the
    # expensive fee is compiled into it, so the cheap tier does not clear. It publishes a
    # priced payload either way, and that payload is what is being compared.
    assert double.data["clears_hurdle"] is False
    assert double.data["net_edge_pct"]
    assert set(double.data) == set(real.data)


def test_cost_gate_is_pending_when_the_engine_does_not_exist(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    outcome = run(verify_module, "cost_gate_uses_live_fee_tier", unbuilt_tree)
    assert_pending(outcome, verify_module)
    assert "spec 40" in outcome.message


def test_cost_gate_passes_against_the_real_engine(
    verify_module: ModuleType, repo_root: Path
) -> None:
    outcome = run(verify_module, "cost_gate_uses_live_fee_tier", repo_root)
    assert_pass(outcome, verify_module)
    assert "moving by exactly" in outcome.message


def test_a_cost_gate_with_the_fee_compiled_in_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """The defect `AGENTS.md` opens by warning about, and the reason a single tick is
    not enough: this engine is otherwise correct and blocks below the hurdle."""
    replace_module(phase3_tree, "acsoe.engines.cost.engine", CONSTANT_FEE_COST_ENGINE)
    outcome = run(verify_module, "cost_gate_uses_live_fee_tier", phase3_tree)
    assert_fail(outcome, verify_module)
    assert "did not move when the fee tier did" in outcome.message


def test_a_cost_gate_reading_only_one_of_the_two_fees_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """The net edge moves with the tier, and by the wrong amount.

    This is why the criterion asserts the *exact* gap rather than "the two differ". An
    engine that read the maker fee and forgot the taker fee would pass a check that only
    asked whether anything changed, and would misprice every candidate in the system by
    the taker leg.
    """
    patch_module(
        phase3_tree,
        "acsoe.engines.cost.engine",
        "inputs.maker_fee_pct + inputs.taker_fee_pct + inputs.spread_pct + inputs.slippage_pct",
        "inputs.maker_fee_pct + inputs.spread_pct + inputs.slippage_pct",
    )
    outcome = run(verify_module, "cost_gate_uses_live_fee_tier", phase3_tree)
    assert_fail(outcome, verify_module)
    assert "Something other than the reported fee" in outcome.message


def test_a_cost_gate_that_never_blocks_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """Two tiers that differ, and no hurdle. A gate that lets everything through still
    reports a moving net edge."""
    patch_module(
        phase3_tree, "acsoe.engines.cost.engine", "clears = net_edge > hurdle", "clears = True"
    )
    outcome = run(verify_module, "cost_gate_uses_live_fee_tier", phase3_tree)
    assert_fail(outcome, verify_module)
    assert "still cleared the hurdle on the expensive tier" in outcome.message


def test_a_cost_gate_that_blocks_everything_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """The other half. A gate that refuses every candidate proves nothing about fees,
    and would satisfy a criterion that only checked the block case."""
    patch_module(
        phase3_tree, "acsoe.engines.cost.engine", "clears = net_edge > hurdle", "clears = False"
    )
    outcome = run(verify_module, "cost_gate_uses_live_fee_tier", phase3_tree)
    assert_fail(outcome, verify_module)
    assert "did not clear the hurdle on the cheap tier" in outcome.message


def test_a_cost_gate_that_cannot_read_engine_one_is_pending_not_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """The audit's own defect, and it must report as unfinished work rather than as a
    broken gate.

    A `cost` reading a key engine 1 does not publish fails closed with
    `cost_inputs_unavailable`, which is the correct behaviour for the engine and the
    wrong verdict for the phase: it is spec 40 not being done, not engine 10 being
    wrong, and a FAIL here would stop the phase over work in flight.
    """
    patch_module(
        phase3_tree,
        "acsoe.engines.cost.contracts",
        'EXCHANGE_FEE_TIER_KEY: Final = "fee_tier"',
        'EXCHANGE_FEE_TIER_KEY: Final = "fees"',
    )
    outcome = run(verify_module, "cost_gate_uses_live_fee_tier", phase3_tree)
    assert_pending(outcome, verify_module)
    assert "not wired to engine 1 yet" in outcome.message


# --------------------------------------------------------------------------- #
# risk_rejects_sub_ordermin
# --------------------------------------------------------------------------- #


def test_risk_is_pending_when_the_engine_does_not_exist(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    outcome = run(verify_module, "risk_rejects_sub_ordermin", unbuilt_tree)
    assert_pending(outcome, verify_module)
    assert "spec 41" in outcome.message


def test_risk_passes_against_the_real_engine(verify_module: ModuleType, repo_root: Path) -> None:
    outcome = run(verify_module, "risk_rejects_sub_ordermin", repo_root)
    assert_pass(outcome, verify_module)
    assert "no quantity returned" in outcome.message


def test_a_risk_gate_that_rounds_up_to_the_minimum_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """The failure the second half of the criterion exists for, and the reason "no order
    was placed" is not a sufficient assertion.

    This engine refuses nothing: a size below `ordermin` is quietly bumped to `ordermin`
    and approved. It would satisfy any check that only asked whether the gate had said
    no, while placing a trade at a size nothing sized.
    """
    patch_module(
        phase3_tree,
        "acsoe.engines.risk.engine",
        "        if qty < inputs.ordermin:",
        "        qty = max(qty, inputs.ordermin)  # bump instead of refuse\n        if False:",
    )
    outcome = run(verify_module, "risk_rejects_sub_ordermin", phase3_tree)
    assert_fail(outcome, verify_module)
    assert "approved" in outcome.message


def test_a_risk_gate_that_refuses_and_still_returns_a_size_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """Refused, unapproved, and a quantity comes back anyway.

    Nothing downstream is obliged to look at `approved` before reading `qty`, and a
    size that survives a rejection is one an executor can place. This is the narrower,
    likelier version of the bug above.
    """
    # Both halves, because either alone leaves the payload unchanged: `to_state_data`
    # omits the four sizing fields when `approved` is false, and on a rejection `qty` is
    # `None` anyway. This is the refactor `_reject`'s docstring names as the thing to
    # guard against - "a field a later refactor could quietly start filling with
    # `ordermin`" - so the induced defect is exactly that refactor.
    patch_module(
        phase3_tree,
        "acsoe.engines.risk.contracts",
        "        if self.approved:\n            for field, value in (",
        "        if True:  # emits the size on a rejection too\n            for field, value in (",
    )
    patch_module(
        phase3_tree,
        "acsoe.engines.risk.engine",
        "            approved=False,\n            ordermin=inputs.ordermin,",
        "            approved=False,\n            qty=inputs.ordermin,\n            ordermin=inputs.ordermin,",
    )
    outcome = run(verify_module, "risk_rejects_sub_ordermin", phase3_tree)
    assert_fail(outcome, verify_module)
    assert "still returned a quantity" in outcome.message


def test_a_risk_gate_refusing_for_the_wrong_reason_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """`code-standards.md`: assert the reason, not only the block. This gate refuses for
    five different reasons and a criterion that accepted any of them could not tell the
    order minimum from an empty balance."""
    # Patched in the *engine*, never in the shared constant. Renaming
    # `REASON_BELOW_ORDERMIN` would move the criterion's expectation and the engine's
    # answer together and the test would pass while proving nothing, because the
    # criterion reads that constant out of the same module it would have renamed.
    patch_module(
        phase3_tree,
        "acsoe.engines.risk.engine",
        "                inputs,\n                REASON_BELOW_ORDERMIN,",
        "                inputs,\n                REASON_BELOW_COSTMIN,",
    )
    outcome = run(verify_module, "risk_rejects_sub_ordermin", phase3_tree)
    assert_fail(outcome, verify_module)
    assert "cannot tell it was the minimum" in outcome.message


# --------------------------------------------------------------------------- #
# universe_varies_with_balance
# --------------------------------------------------------------------------- #

SCOUT_CONTRACTS = '''
from typing import Final

EXCHANGE_KEY: Final = "exchange"
STATE_KEY: Final = "scout"
UNIVERSE_FIELD: Final = "universe"
'''

#: A minimal engine 7. It excludes a pair when the held quote balance cannot fund the
#: pair's own `costmin` on every position the operator allows to be open at once -
#: `costmin x trading.max_concurrent_positions`. That shape is invariant 7's ("a pair is
#: only executable if the account holds spendable balance in that quote currency")
#: crossed with a real configured limit rather than a number invented here, and it
#: discriminates over the committed fixtures, where every pair's `costmin` is the same
#: and a plain `held >= costmin` would admit all four pairs at both balances.
#:
#: It is a **stand-in for an engine nobody has written**, not a proposal for what B
#: should write. Specs 43 and 44 name six exclusion rules and this implements one of
#: them; the criterion it is here to exercise cares only that the universe responds to
#: the balance at all.
SCOUT_ENGINE = '''
import time
from decimal import Decimal
from typing import Any

from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.scout.contracts import EXCHANGE_KEY, UNIVERSE_FIELD

IGNORE_BALANCE = {ignore_balance!r}


class ScoutEngine(BaseEngine):
    name = "scout"
    number = 7
    is_gate = True

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()
        exchange = state.get(EXCHANGE_KEY) or {{}}
        balances = exchange.get("balances") or {{}}
        pairs = (exchange.get("pair_rules") or {{}}).get("pairs") or {{}}
        concurrent = Decimal(str(context.config.get("trading.max_concurrent_positions")))
        universe: list[str] = []
        for name in sorted(pairs):
            rule = pairs[name]
            held = Decimal(str(balances.get(rule["quote"], "0")))
            if IGNORE_BALANCE or held >= Decimal(str(rule["costmin"])) * concurrent:
                universe.append(name)
        data: dict[str, Any] = {{UNIVERSE_FIELD: universe, "scanned": len(pairs)}}
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            data=data,
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
'''


def fabricate_scout(root: Path, *, ignore_balance: bool = False) -> None:
    fabricate_package(
        root,
        {
            "acsoe.engines.scout.contracts": SCOUT_CONTRACTS,
            "acsoe.engines.scout.engine": SCOUT_ENGINE.format(ignore_balance=ignore_balance),
        },
    )


def test_universe_is_pending_when_scout_does_not_exist(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    """The state the criterion was registered in, and the one it spends the phase in
    until spec 43 lands. The PENDING line has to name what to build."""
    outcome = run(verify_module, "universe_varies_with_balance", unbuilt_tree)
    assert_pending(outcome, verify_module)
    assert "spec 43" in outcome.message
    assert "UNIVERSE_FIELD" in outcome.message or "universe" in outcome.message


def test_universe_is_pending_when_scout_declares_no_universe_field(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """A `contracts.py` that exists and does not say where the universe is published.
    The criterion must not guess a key; guessing one is the audit's own defect."""
    fabricate_package(
        phase3_tree,
        {
            "acsoe.engines.scout.contracts": (
                'EXCHANGE_KEY = "exchange"\nSTATE_KEY = "scout"\n'
            ),
            "acsoe.engines.scout.engine": SCOUT_ENGINE.format(ignore_balance=False).replace(
                "from acsoe.engines.scout.contracts import EXCHANGE_KEY, UNIVERSE_FIELD",
                'from acsoe.engines.scout.contracts import EXCHANGE_KEY\n\nUNIVERSE_FIELD = "universe"',
            ),
        },
    )
    outcome = run(verify_module, "universe_varies_with_balance", phase3_tree)
    assert_pending(outcome, verify_module)
    assert "does not say where the universe is published" in outcome.message


def test_universe_passes_against_a_filter_that_reads_the_balance(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    fabricate_scout(phase3_tree)
    outcome = run(verify_module, "universe_varies_with_balance", phase3_tree)
    assert_pass(outcome, verify_module)
    assert "at a $10 balance" in outcome.message


def test_the_universe_key_is_read_from_scouts_own_model(verify_module: ModuleType) -> None:
    """The criterion follows the engine's contract rather than the other way round.

    Its PENDING line proposed a `UNIVERSE_FIELD` constant while engine 7 was unwritten.
    B built a `ScoutUniverse` model with a `to_state_data()` serialiser instead — the
    same shape engines 10 and 11 use, neither of which declares a field-name constant
    either — so the proposal was the worse of the two designs and the criterion adapts.
    A PENDING message is a proposal to the owning agent, not a decree.

    It adapts by *asking the model*, not by retyping `"pairs"`. That is the same
    discipline this section applies to `state["exchange"]`, where four retyped field
    names survived a whole phase because every test agreed with whoever wrote it.
    """
    from acsoe.engines.scout import contracts as scout_contracts

    key, problem = verify_module._scout_universe_field(scout_contracts)
    assert problem is None, problem
    assert key in scout_contracts.ScoutUniverse(pairs=("A/B",)).to_state_data()


def test_renaming_the_universe_field_moves_the_criterion_with_it(
    verify_module: ModuleType,
) -> None:
    """The property that makes the probe worth having rather than a literal.

    If B renames the field, the criterion follows on its own. A hardcoded `"pairs"`
    would keep looking for a key nobody publishes and would report a FAIL against a
    perfectly good engine — the drift this whole phase exists to stop, pointed the other
    way.
    """

    class RenamedUniverse:
        def __init__(self, pairs: tuple[str, ...] = ()) -> None:
            self._pairs = pairs

        def to_state_data(self) -> dict[str, object]:
            return {"tradable": list(self._pairs), "scanned": 0}

    key, problem = verify_module._scout_universe_field(
        SimpleNamespace(ScoutUniverse=RenamedUniverse)
    )
    assert problem is None, problem
    assert key == "tradable"


def test_a_model_that_publishes_no_universe_at_all_is_a_fail(
    verify_module: ModuleType,
) -> None:
    """Not PENDING. A `ScoutUniverse` that exists and drops the universe on the floor is
    a broken contract, not unfinished work, and nothing downstream could iterate it."""

    class UniverselessUniverse:
        def __init__(self, pairs: tuple[str, ...] = ()) -> None:
            self._pairs = pairs

        def to_state_data(self) -> dict[str, object]:
            return {"scanned": len(self._pairs)}

    key, problem = verify_module._scout_universe_field(
        SimpleNamespace(ScoutUniverse=UniverselessUniverse)
    )
    assert key is None
    assert problem is not None
    assert problem.result is verify_module.Result.FAIL


def test_a_universe_that_ignores_the_balance_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """Invariant 7 makes affordability part of tradability. This filter runs, publishes
    a universe and never looks at what the account holds - which a criterion checking
    only that a universe came back would accept."""
    fabricate_scout(phase3_tree, ignore_balance=True)
    outcome = run(verify_module, "universe_varies_with_balance", phase3_tree)
    assert_fail(outcome, verify_module)
    assert "ignores the balance" in outcome.message


# --------------------------------------------------------------------------- #
# safety_freezes_on_drawdown_without_opportunity_chain
# --------------------------------------------------------------------------- #

DRAWDOWN_CRITERION = "safety_freezes_on_drawdown_without_opportunity_chain"


def test_drawdown_freeze_is_pending_when_safety_does_not_exist(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    outcome = run(verify_module, DRAWDOWN_CRITERION, unbuilt_tree)
    assert_pending(outcome, verify_module)
    assert "spec 42" in outcome.message


def test_drawdown_freeze_is_pending_while_the_policy_table_still_escalates(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """The state the criterion was written in, on 2026-09-10.

    `CONDITION_ACTION` still mapped drawdown to `close_all`, marked PROVISIONAL and
    awaiting the ruling that spec 37 had by then delivered. That is spec 42 not yet
    done rather than engine 17 being wrong, so it reports PENDING and names the spec -
    and it starts judging behaviour the moment the table says FREEZE.
    """
    patch_module(
        phase3_tree,
        "acsoe.engines.safety.contracts",
        "SafetyCondition.DRAWDOWN: SafetyAction.FREEZE",
        "SafetyCondition.DRAWDOWN: SafetyAction.CLOSE_ALL",
    )
    outcome = run(verify_module, DRAWDOWN_CRITERION, phase3_tree)
    assert_pending(outcome, verify_module)
    assert "spec 42" in outcome.message


def test_drawdown_freeze_passes_against_the_real_engine(
    verify_module: ModuleType, repo_root: Path
) -> None:
    outcome = run(verify_module, DRAWDOWN_CRITERION, repo_root)
    assert_pass(outcome, verify_module)
    assert "no `close_all`" in outcome.message


def test_a_breaker_that_escalates_on_drawdown_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """Spec 37's ruling, asserted as an absence.

    The table says FREEZE and the engine writes `close_all` anyway - the shape a
    half-applied ruling leaves behind, where the policy is corrected and the code that
    reads it is not. The seed carries the open positions and resting orders that make
    an escalation permissible, so nothing else stops it.
    """
    patch_module(
        phase3_tree,
        "acsoe.engines.safety.contracts",
        "    if action is SafetyAction.FREEZE:\n        return CommandName.FREEZE",
        "    if action is SafetyAction.FREEZE:\n        return CommandName.CLOSE_ALL",
    )
    outcome = run(verify_module, DRAWDOWN_CRITERION, phase3_tree)
    assert_fail(outcome, verify_module)
    assert "emitted `close_all`" in outcome.message


def test_a_breaker_that_re_emits_every_tick_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """It runs every tick, so a breaker that emits whenever a condition holds appends a
    freeze row every sixty seconds forever - and re-triggers a liquidation already under
    way. The criterion ticks three times for exactly this."""
    patch_module(
        phase3_tree,
        "acsoe.engines.safety.engine",
        "    def _emit(",
        "    def _emit_disabled_suppression(",
    )
    patch_module(
        phase3_tree,
        "acsoe.engines.safety.engine",
        "        emitted, suppressed = self._emit(context, state, action, readings, tripped)",
        "        emitted, suppressed = self._emit_always(context, state, action, readings, tripped)",
    )
    path = phase3_tree / "src" / "acsoe" / "engines" / "safety" / "engine.py"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '''

def _emit_always(self, context, state, action, readings, tripped):
    """Emit whenever a condition is tripped, with no suppression at all."""
    from acsoe.clients.store.contracts import CommandRow, CommandSource, to_micros
    from acsoe.engines.safety.contracts import command_for

    command = command_for(action)
    if command is None:
        return None, None
    stamp = to_micros(context.now)
    context.clients.store.append_command(
        CommandRow(
            command=command,
            source=CommandSource.SAFETY,
            reason="re-emitting",
            created_at=stamp,
            created_by_run_id=context.run_id,
            updated_at=stamp,
        )
    )
    return command.value, None


SafetyEngine._emit_always = _emit_always
''',
        encoding="utf-8",
    )
    outcome = run(verify_module, DRAWDOWN_CRITERION, phase3_tree)
    assert_fail(outcome, verify_module)
    assert "re-emits while the condition persists" in outcome.message


# --------------------------------------------------------------------------- #
# safety_escalates_on_sustained_outage
# --------------------------------------------------------------------------- #

OUTAGE_CRITERION = "safety_escalates_on_sustained_outage"


def test_outage_is_pending_when_safety_does_not_exist(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    outcome = run(verify_module, OUTAGE_CRITERION, unbuilt_tree)
    assert_pending(outcome, verify_module)
    assert "safety" in outcome.message


def test_outage_passes_against_the_real_engine(
    verify_module: ModuleType, repo_root: Path
) -> None:
    outcome = run(verify_module, OUTAGE_CRITERION, repo_root)
    assert_pass(outcome, verify_module)
    assert "does not trip the outage" in outcome.message


def test_a_breaker_that_fires_a_tick_early_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """Invariant 14 says "more **than**", so the limit itself must not fire.

    This is the half that is usually missing, and it is the expensive one to get wrong:
    firing early liquidates an account over an outage that has not reached the threshold
    the operator chose. A criterion asserting only the escalation passes against it.
    """
    patch_module(
        phase3_tree,
        "acsoe.engines.safety.engine",
        "readings.consecutive_data_blocks > thresholds.max_consecutive_data_blocks",
        "readings.consecutive_data_blocks >= thresholds.max_consecutive_data_blocks",
    )
    outcome = run(verify_module, OUTAGE_CRITERION, phase3_tree)
    assert_fail(outcome, verify_module)
    assert "tripped at exactly" in outcome.message


def test_a_breaker_that_never_escalates_on_the_outage_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """The other side of the boundary, as its own test so a failure names which side.

    After spec 37 the sustained outage is the *only* condition that escalates, so an
    outage mapped to `freeze` is the breaker declining to do the one thing invariant 14
    reserves for it.
    """
    patch_module(
        phase3_tree,
        "acsoe.engines.safety.contracts",
        "SafetyCondition.DATA_OUTAGE: SafetyAction.CLOSE_ALL",
        "SafetyCondition.DATA_OUTAGE: SafetyAction.FREEZE",
    )
    outcome = run(verify_module, OUTAGE_CRITERION, phase3_tree)
    assert_fail(outcome, verify_module)
    assert "no `close_all` was written" in outcome.message


def test_an_outage_counted_by_cycle_id_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """The seeded outage spans two `run_id`s with overlapping `cycle_id`s on purpose.

    `cycle_id` restarts at 1 with each process, so ordering by it interleaves the two
    runs and the trailing count comes out wrong - and surviving a restart is the whole
    reason the counter lives in SQLite rather than in `state`.
    """
    patch_module(
        phase3_tree,
        "acsoe.clients.store.client",
        "ORDER BY ts DESC, run_id DESC, cycle_id DESC",
        "ORDER BY cycle_id DESC, ts DESC, run_id DESC",
    )
    outcome = run(verify_module, OUTAGE_CRITERION, phase3_tree)
    assert_fail(outcome, verify_module)


# --------------------------------------------------------------------------- #
# safety_inputs_all_from_the_seed
# --------------------------------------------------------------------------- #

INPUTS_CRITERION = "safety_inputs_all_from_the_seed"


def test_inputs_is_pending_when_safety_does_not_exist(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    outcome = run(verify_module, INPUTS_CRITERION, unbuilt_tree)
    assert_pending(outcome, verify_module)


def test_inputs_passes_against_the_real_engine(
    verify_module: ModuleType, repo_root: Path
) -> None:
    outcome = run(verify_module, INPUTS_CRITERION, repo_root)
    assert_pass(outcome, verify_module)
    assert "none of them moved when state was poisoned" in outcome.message


def test_a_breaker_reading_engine_nineteen_out_of_state_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """The forward dependency Phase 3 may not take.

    Engine 19 `memory` writes all six of these and is Phase 4; it also runs in the
    *manage* chain, after the guard chain, so even once it exists `state` cannot carry
    its output when engine 17 runs. A breaker that prefers a `state` payload when one is
    present would pass every test written against a database and would read nothing on a
    live tick. The poisoned half of the criterion is what notices.
    """
    patch_module(
        phase3_tree,
        "acsoe.engines.safety.engine",
        "        drawdown, equity, peak = self._drawdown(store)",
        "        drawdown, equity, peak = self._drawdown(store)\n"
        "        _memory = state.get('memory')\n"
        "        if isinstance(_memory, dict) and 'drawdown_pct' in _memory:\n"
        "            drawdown = Decimal(str(_memory['drawdown_pct']))",
    )
    outcome = run(verify_module, INPUTS_CRITERION, phase3_tree)
    assert_fail(outcome, verify_module)
    assert "poisoning `state`" in outcome.message


def test_a_breaker_reporting_a_reading_it_did_not_take_is_a_fail(
    verify_module: ModuleType, phase3_tree: Path
) -> None:
    """A number that does not come from the seeded rows, however it was arrived at.

    This is the half that catches a hardcoded reading, which the poisoned-state half
    cannot: a constant does not move when `state` moves either.
    """
    patch_module(
        phase3_tree,
        "acsoe.engines.safety.engine",
        "        losses, saturated = self._loss_streak(store)",
        "        losses, saturated = 0, False",
    )
    outcome = run(verify_module, INPUTS_CRITERION, phase3_tree)
    assert_fail(outcome, verify_module)
    assert "did not come from the Phase 0 seed" in outcome.message


# --------------------------------------------------------------------------- #
# phase_3_gates_have_both_tests
# --------------------------------------------------------------------------- #

BOTH_TESTS_CRITERION = "phase_3_gates_have_both_tests"

BLOCK_AND_PASS = '''
from acsoe.core.contracts import EngineStatus


def test_it_blocks() -> None:
    assert result.status is EngineStatus.BLOCK


def test_it_passes() -> None:
    assert result.status is EngineStatus.OK
'''

BLOCK_ONLY = '''
from acsoe.core.contracts import EngineStatus


def test_it_blocks() -> None:
    assert result.status is EngineStatus.BLOCK


def test_it_still_blocks_on_something_else() -> None:
    assert result.status is EngineStatus.BLOCK
'''

#: Both directions, asserted on `blocks_trading` rather than on `EngineStatus`. Some
#: engines are tested one way and some the other, and a criterion recognising only one
#: spelling would report a gate as untested because of the assertion style its author
#: preferred.
BOOLEAN_STYLE = '''
def test_it_blocks() -> None:
    assert result.blocks_trading is True


def test_it_passes() -> None:
    assert result.blocks_trading is False
'''

#: Named as though it covered both directions and asserting nothing at all. This is why
#: the criterion parses the assertions instead of reading the test names.
NAMED_BUT_EMPTY = '''
def test_it_blocks_on_a_wide_spread() -> None:
    assert True


def test_it_passes_on_a_tight_spread() -> None:
    assert True
'''


def write_engine_tests(root: Path, sources: dict[str, str]) -> None:
    directory = root / "tests" / "engines"
    directory.mkdir(parents=True, exist_ok=True)
    for engine, source in sources.items():
        (directory / f"test_{engine}.py").write_text(source, encoding="utf-8")


def test_both_tests_is_pending_when_an_engine_has_no_test_file(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Engine 7's tests arrive with specs 43 and 44. Until then the criterion is
    waiting on a file, which is PENDING, not a gate shipped without tests."""
    write_engine_tests(
        bare_tree, dict.fromkeys(("cost", "risk", "safety"), BLOCK_AND_PASS)
    )
    outcome = run(verify_module, BOTH_TESTS_CRITERION, bare_tree)
    assert_pending(outcome, verify_module)
    assert "scout" in outcome.message


def test_both_tests_passes_when_every_gate_has_both_halves(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    write_engine_tests(
        bare_tree, dict.fromkeys(("scout", "cost", "risk", "safety"), BLOCK_AND_PASS)
    )
    outcome = run(verify_module, BOTH_TESTS_CRITERION, bare_tree)
    assert_pass(outcome, verify_module)


def test_both_tests_reads_the_boolean_assertion_style_too(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    write_engine_tests(
        bare_tree, dict.fromkeys(("scout", "cost", "risk", "safety"), BOOLEAN_STYLE)
    )
    outcome = run(verify_module, BOTH_TESTS_CRITERION, bare_tree)
    assert_pass(outcome, verify_module)


def test_both_tests_never_fails_against_the_real_tree(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """Against the real repository: PASS once every gate has a test file, PENDING while
    one is still missing, and **never FAIL**.

    This test used to assert PENDING outright, because engine 7 had no test file when
    the criterion was registered. B landed `tests/engines/test_scout.py` a few hours
    later and the criterion went green on its own — correctly — and took this test red
    with it. It was asserting a fact about the calendar rather than a property of the
    criterion, which is the same defect as a fixture pinned to a literal: right on the
    day it is written and wrong the moment the thing it describes moves.

    The durable property is the one the criterion exists for. A FAIL means a gate has a
    test file carrying only one direction, and that is a real defect in somebody's
    tests; a PENDING means a file is not there yet and must name which, so the operator
    is not left to guess what the gate is waiting for.
    """
    outcome = run(verify_module, BOTH_TESTS_CRITERION, repo_root)
    assert outcome.result is not verify_module.Result.FAIL, outcome
    if outcome.result is verify_module.Result.PENDING:
        assert "tests/engines/test_" in outcome.message, outcome
    else:
        assert_pass(outcome, verify_module)
        for engine in ("scout", "cost", "risk", "safety"):
            assert engine in outcome.message, outcome


@pytest.mark.parametrize("engine", ["scout", "cost", "risk", "safety"])
def test_a_gate_with_only_block_tests_is_a_fail(
    verify_module: ModuleType, bare_tree: Path, engine: str
) -> None:
    """A gate with only block cases refuses everything and proves nothing, and it is the
    direction people forget less often than the happy path - so both are covered."""
    sources = dict.fromkeys(("scout", "cost", "risk", "safety"), BLOCK_AND_PASS)
    sources[engine] = BLOCK_ONLY
    write_engine_tests(bare_tree, sources)
    outcome = run(verify_module, BOTH_TESTS_CRITERION, bare_tree)
    assert_fail(outcome, verify_module)
    assert "no test asserting it passes" in outcome.message
    assert engine in outcome.message


def test_a_gate_whose_tests_only_look_like_both_halves_is_a_fail(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """The reason the criterion parses assertions rather than test names.

    Both functions here are named for the direction they cover and neither asserts
    anything about the gate. A criterion grepping for `block` and `pass` in a name would
    call this complete, which is a gate satisfied by the shape of the evidence rather
    than by its content - the rule Phase 2 produced at the cost of a criterion that
    would have accepted a 47%-recorded archive.
    """
    sources = dict.fromkeys(("scout", "cost", "risk", "safety"), BLOCK_AND_PASS)
    sources["cost"] = NAMED_BUT_EMPTY
    write_engine_tests(bare_tree, sources)
    outcome = run(verify_module, BOTH_TESTS_CRITERION, bare_tree)
    assert_fail(outcome, verify_module)
    assert "cost" in outcome.message


# --------------------------------------------------------------------------- #
# The shared helpers, held to the rule they exist to enforce
# --------------------------------------------------------------------------- #


def test_the_exchange_payload_is_never_hand_built(verify_module: ModuleType) -> None:
    """The audit's finding, stated as a property of this file rather than as a comment.

    Every Phase 3 criterion that needs `state["exchange"]` must get it from
    `_exchange_payload`, which runs the real engine 1. A criterion that assembled the
    payload itself would agree with whatever field names it was written against, which
    is exactly how four wrong keys survived a whole phase.
    """
    import inspect

    source = inspect.getsource(verify_module._exchange_payload)
    assert "process(context, {})" in source

    # The field names under `state["exchange"]` are the four the audit found wrong.
    # None of them may be a string literal in a criterion body - the criterion reads
    # engine 1's payload through the engine's own `contracts.py` constants or not at
    # all. Quoted, so the criterion's own *name* does not count: the function is called
    # `check_cost_gate_uses_live_fee_tier` and that is a description, not a state key.
    for name in ("cost_gate_uses_live_fee_tier", "risk_rejects_sub_ordermin"):
        body = inspect.getsource(getattr(verify_module, "check_" + name))
        for field in ("fee_tier", "maker_fee_pct", "taker_fee_pct", "pair_rules", "ordermin"):
            for literal in (f'"{field}"', f"'{field}'"):
                assert literal not in body, (
                    f"{name} names {field!r} as a literal. Every field under "
                    "state['exchange'] comes from the engine's own contracts module; "
                    "retyping one is how four of them were wrong for a whole phase."
                )


def test_the_seed_is_scaled_against_the_committed_config(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """Spec 13's rule, and the defect this file was written against.

    `seeded_console_db` passes no `thresholds`, so the seed scales to `seed.py`'s module
    defaults - where `max_errors_in_window` is 10 against the config's 20, giving 13
    ERROR rows rather than 23. The console criteria do not care; these do. A fixture
    pinned to a constant stops overshooting the moment the operator raises a limit, and
    the criterion then accuses the seed of a bug the criterion caused.
    """
    import sqlite3
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        with verify_module.root_import_path(repo_root):
            db_path, problem = verify_module._phase3_seeded_db(
                verify_module.VerifyContext(root=repo_root), Path(tmp)
            )
        assert problem is None, problem
        assert db_path is not None
        conn = sqlite3.connect(db_path)
        try:
            errors = conn.execute(
                "SELECT COUNT(*) FROM block_records WHERE status = 'ERROR'"
            ).fetchone()[0]
        finally:
            conn.close()

    config = verify_module.load_config(repo_root)[0]
    assert config is not None
    configured = int(verify_module.config_get(config, verify_module.KEY_MAX_ERRORS))
    assert errors > configured, (
        f"the seed produced {errors} ERROR rows against a configured limit of "
        f"{configured}; it is supposed to overshoot whatever limit it is given, and a "
        "seed that does not cannot make the error-rate condition trip"
    )


def test_a_criterion_clocked_off_the_seed_sees_the_seeded_error_rows(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """The zero-against-zero trap, as a regression.

    `safety_inputs_all_from_the_seed` originally ran at a fixed instant of my choosing.
    The seed's rows carry the seed's own timestamps, so the error-rate window landed
    entirely after them: the engine reported 0 and the criterion's own SQL reported 0,
    and they "agreed". An engine ignoring that input completely would have passed.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        with verify_module.root_import_path(repo_root):
            db_path, problem = verify_module._phase3_seeded_db(
                verify_module.VerifyContext(root=repo_root), Path(tmp)
            )
        assert problem is None, problem
        assert db_path is not None
        seed_now = verify_module._seed_now(db_path)
        assert seed_now != verify_module.PHASE3_NOW, (
            "the seed's instant is the fixed constant, so this test cannot tell the two "
            "apart and the regression it guards is invisible"
        )

    outcome = run(verify_module, INPUTS_CRITERION, repo_root)
    assert_pass(outcome, verify_module)
    assert "0 error block(s)" not in outcome.message
