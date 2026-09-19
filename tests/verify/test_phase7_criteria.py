"""The Phase 7 criteria. Spec 141.

Each criterion is observed three ways, in the phase's order: **PENDING** against a tree where
its subject does not exist, **PASS** against the subject as it is, and **FAIL** against a
plausible wrong implementation made in a copied tree, never in the real one (the real file
is hashed on both sides of every FAIL test that copies it).

Where each stands tonight, and why:

* `fee_scenario_is_replay_only` — PASS: the replay client (spec 129) exists and refuses paper
  and live.
* `promotion_gate_rejects_haircut_edge` — PASS: spec 139's gate, ledger and statistics exist.
* `backtest_emits_alpha_report` — PENDING: it judges the committed digest of the six-month run,
  which cannot exist until the run ends (spec 143). Expected, and not a defect.
* `research_screens_render` — PENDING until spec 140 writes SHAP rows.

**Phase 7 fails quietly** (the task list's warning), so the PASS messages are asserted for the
figures they carry, not only for their result.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.verify.test_phase2_criteria import assert_fail, assert_pending, run

PHASE7_CRITERIA = (
    "backtest_emits_alpha_report",
    "promotion_gate_rejects_haircut_edge",
    "research_screens_render",
    "fee_scenario_is_replay_only",
)

_NO_PYCACHE = shutil.ignore_patterns("__pycache__", "*.pyc")

REPLAY = Path("src") / "acsoe" / "clients" / "kraken" / "replay.py"
#: The constructor's refusal, and its planted defect: the refusal gone.
REPLAY_GUARD = b'        if str(mode) != "replay":\n            raise ReplayModeError(\n'
REPLAY_GUARD_BROKEN = b'        if False:\n            raise ReplayModeError(\n'
#: `from_config`'s refusal, which must come before any key is read.
FROM_CONFIG_GUARD = b'        if str(config.mode) != "replay":\n'
FROM_CONFIG_GUARD_LATE = b'        config.get("replay.fee_tier")\n        if str(config.mode) != "replay":\n'


@pytest.fixture
def phase7_tree(bare_tree: Path, repo_root: Path) -> Path:
    """The real package, config, migrations, harness, fixtures and trial ledger, copied."""
    shutil.copytree(repo_root / "src" / "acsoe", bare_tree / "src" / "acsoe", ignore=_NO_PYCACHE)
    shutil.copytree(repo_root / "config", bare_tree / "config")
    shutil.copytree(repo_root / "db", bare_tree / "db", ignore=_NO_PYCACHE)
    tests = bare_tree / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "__init__.py").write_bytes(b"")
    shutil.copytree(repo_root / "tests" / "harness", tests / "harness", ignore=_NO_PYCACHE)
    shutil.copytree(repo_root / "tests" / "fixtures", tests / "fixtures", ignore=_NO_PYCACHE)
    ledger = Path("docs") / "dataset" / "phase-7-trial-ledger.json"
    (bare_tree / ledger).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(repo_root / ledger, bare_tree / ledger)
    return bare_tree


def break_copy(tree: Path, repo_root: Path, relative: Path, old: bytes, new: bytes) -> str:
    """Plant `new` over `old` in the copy only; return the real file's hash to re-check."""
    real = repo_root / relative
    before = hashlib.sha256(real.read_bytes()).hexdigest()
    copy = tree / relative
    source = copy.read_bytes().replace(b"\r\n", b"\n")
    assert source.count(old) == 1, f"the anchor appears {source.count(old)} times"
    copy.write_bytes(source.replace(old, new))
    return before


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def test_the_four_criteria_are_registered_for_phase_7_in_the_rows_order(
    verify_module: ModuleType,
) -> None:
    registered = [c.name for c in verify_module._REGISTRY[7]]
    assert [n for n in registered if n not in ("docs_vocabulary", "toolchain_green")] == list(
        PHASE7_CRITERIA
    )


def test_every_phase_7_criterion_is_offline(verify_module: ModuleType) -> None:
    for criterion in verify_module._REGISTRY[7]:
        assert criterion.live is False, criterion.name


# --------------------------------------------------------------------------- #
# PENDING where nothing is built, and it names what it waits for
# --------------------------------------------------------------------------- #

WAITS_FOR = {
    "backtest_emits_alpha_report": "spec 138",
    "promotion_gate_rejects_haircut_edge": "spec 139",
    "research_screens_render": "spec 140",
    "fee_scenario_is_replay_only": "spec 129",
}


@pytest.mark.parametrize("name", PHASE7_CRITERIA)
def test_pending_on_a_tree_with_nothing_built(
    verify_module: ModuleType, unbuilt_tree: Path, name: str
) -> None:
    outcome = run(verify_module, name, unbuilt_tree)
    assert_pending(outcome, verify_module)
    assert WAITS_FOR[name] in outcome.message, outcome.message


def test_the_alpha_report_is_pending_until_the_runs_digest_is_committed(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """Tonight's expected state, pinned so that it changes only on purpose."""
    outcome = run(verify_module, "backtest_emits_alpha_report", repo_root)
    assert_pending(outcome, verify_module)


# --------------------------------------------------------------------------- #
# fee_scenario_is_replay_only
# --------------------------------------------------------------------------- #


def test_the_fee_scenario_criterion_passes_on_the_real_tree(
    verify_module: ModuleType, repo_root: Path
) -> None:
    outcome = run(verify_module, "fee_scenario_is_replay_only", repo_root)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    assert "refused construction in paper and live" in outcome.message
    assert "accepted replay" in outcome.message


def test_a_replay_client_that_constructs_in_paper_fails(
    verify_module: ModuleType, phase7_tree: Path, repo_root: Path
) -> None:
    before = break_copy(phase7_tree, repo_root, REPLAY, REPLAY_GUARD, REPLAY_GUARD_BROKEN)
    outcome = run(verify_module, "fee_scenario_is_replay_only", phase7_tree)
    assert hashlib.sha256((repo_root / REPLAY).read_bytes()).hexdigest() == before
    assert_fail(outcome, verify_module)
    assert "constructed in mode 'paper'" in outcome.message, outcome.message


def test_a_from_config_that_reads_the_scenario_before_refusing_fails(
    verify_module: ModuleType, phase7_tree: Path, repo_root: Path
) -> None:
    before = break_copy(phase7_tree, repo_root, REPLAY, FROM_CONFIG_GUARD, FROM_CONFIG_GUARD_LATE)
    outcome = run(verify_module, "fee_scenario_is_replay_only", phase7_tree)
    assert hashlib.sha256((repo_root / REPLAY).read_bytes()).hexdigest() == before
    assert_fail(outcome, verify_module)
    assert "read ['replay.fee_tier'] before refusing" in outcome.message, outcome.message


def test_a_replay_client_that_refuses_every_mode_fails(
    verify_module: ModuleType, phase7_tree: Path, repo_root: Path
) -> None:
    """The positive control: a client refusing everything would pass the two halves above."""
    before = break_copy(
        phase7_tree, repo_root, REPLAY, REPLAY_GUARD, b"        if True:\n            raise ReplayModeError(\n"
    )
    outcome = run(verify_module, "fee_scenario_is_replay_only", phase7_tree)
    assert hashlib.sha256((repo_root / REPLAY).read_bytes()).hexdigest() == before
    assert_fail(outcome, verify_module)
    assert "refused mode 'replay' too" in outcome.message, outcome.message


@pytest.mark.parametrize(
    ("source", "named"),
    [
        (b'SCHEDULE = "tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json"\n',
         "kraken_fee_schedule"),
        (b"from acsoe.clients.kraken.replay_scenario import load_fee_scenario\n",
         "acsoe.clients.kraken.replay_scenario"),
        (b"import acsoe.clients.kraken.replay_scenario as s\n",
         "acsoe.clients.kraken.replay_scenario"),
        (b"from acsoe.clients.kraken import replay_scenario\n",
         "acsoe.clients.kraken.replay_scenario"),
        (b'TABLE = "spread_book_table_2026-09-19.json"\n', "spread_book_table"),
        (b"def f(m):\n    return m.load_spread_table\n", "load_spread_table"),
        (b"def f(m):\n    return m.load_fee_scenario\n", "load_fee_scenario"),
        (b'DIR = "tests/fixtures/replay/"\n', "fixtures/replay"),
        (b'from pathlib import Path\nDIR = Path("tests") / "fixtures" / "replay"\n',
         "fixtures/replay"),
        (b'from pathlib import Path\nDIR = Path("tests", "fixtures", "replay")\n',
         "fixtures/replay"),
    ],
)
def test_a_module_outside_the_replay_client_naming_the_fee_fails(
    verify_module: ModuleType, phase7_tree: Path, source: bytes, named: str
) -> None:
    stray = phase7_tree / "src" / "acsoe" / "engines" / "cost" / "declared.py"
    stray.write_bytes(source)
    outcome = run(verify_module, "fee_scenario_is_replay_only", phase7_tree)
    assert_fail(outcome, verify_module)
    assert f"src/acsoe/engines/cost/declared.py: {named}" in outcome.message, outcome.message


# --------------------------------------------------------------------------- #
# promotion_gate_rejects_haircut_edge
# --------------------------------------------------------------------------- #


def test_the_promotion_criterion_is_pending_without_the_ledger(
    verify_module: ModuleType, phase7_tree: Path
) -> None:
    (phase7_tree / "docs" / "dataset" / "phase-7-trial-ledger.json").unlink()
    outcome = run(verify_module, "promotion_gate_rejects_haircut_edge", phase7_tree)
    assert_pending(outcome, verify_module)
    assert "phase-7-trial-ledger.json does not exist yet" in outcome.message, outcome.message


def test_the_promotion_criterion_passes_on_the_real_tree(
    verify_module: ModuleType, repo_root: Path
) -> None:
    import json

    trials = json.loads(
        (repo_root / "docs" / "dataset" / "phase-7-trial-ledger.json").read_bytes()
    )["trial_count"]
    outcome = run(verify_module, "promotion_gate_rejects_haircut_edge", repo_root)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    assert f"committed ledger's {trials} trials" in outcome.message, outcome.message
    assert "rejected, promotion_lower_bound_not_above_zero" in outcome.message
    assert "promoted. Real engine 20, real store" in outcome.message


PROMOTION = Path("src") / "acsoe" / "modelling" / "promotion.py"
TOURNAMENT = Path("src") / "acsoe" / "engines" / "tournament" / "engine.py"


@pytest.mark.parametrize(
    ("relative", "old", "new", "says"),
    [
        # No Bonferroni: the haircut-failing model is promoted at the ledger's count.
        (PROMOTION, b"    alpha = FAMILY_ALPHA / n_trials\n    return",
         b"    alpha = FAMILY_ALPHA\n    return", "the gate let it through"),
        # A gate that refuses everything: the one-trial control goes unpromoted.
        (PROMOTION, b"    promoted = lower > 0.0\n", b"    promoted = False\n",
         "at one trial the same trades were not promoted"),
        # The ledger ignored: engine 20 judges at one trial whatever the ledger says.
        (TOURNAMENT, b"            trials = _ledger_trial_count(self._ledger_path)\n",
         b"            trials = 1\n", "judged with N = 1"),
    ],
)
def test_the_promotion_criterion_fails_on_a_planted_defect(
    verify_module: ModuleType,
    phase7_tree: Path,
    repo_root: Path,
    relative: Path,
    old: bytes,
    new: bytes,
    says: str,
) -> None:
    before = break_copy(phase7_tree, repo_root, relative, old, new)
    outcome = run(verify_module, "promotion_gate_rejects_haircut_edge", phase7_tree)
    assert hashlib.sha256((repo_root / relative).read_bytes()).hexdigest() == before
    assert_fail(outcome, verify_module)
    assert "criterion raised" not in outcome.message, outcome.message
    assert says in outcome.message, outcome.message


# --------------------------------------------------------------------------- #
# backtest_emits_alpha_report (c-criteria)
# --------------------------------------------------------------------------- #

ALPHA = "backtest_emits_alpha_report"
ATTRIBUTION = Path("src") / "acsoe" / "research" / "attribution.py"


def genuine_digest(verify_module: ModuleType, tmp: Path) -> dict[str, Any]:
    """A digest of a real report: the criterion's own fabricated run, through the real
    store, partition reader and attribution module."""
    with verify_module.root_import_path(verify_module.REPO_ROOT):
        import acsoe.research.attribution as attribution

        config, problem = verify_module._phase3_config()
        assert problem is None
        digest, problem = verify_module._alpha_pipeline(attribution, config, tmp)
    assert problem is None
    return copy.deepcopy(digest)


def commit_digest(tree: Path, digest: Mapping[str, Any], name: str = "tier3-em") -> Path:
    directory = tree / "tests" / "fixtures" / "phase7"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"run-digest-{name}.json"
    path.write_bytes(json.dumps(digest).encode("utf-8"))
    return path


def test_the_alpha_report_passes_on_a_committed_genuine_digest_and_names_what_it_judged(
    verify_module: ModuleType, phase7_tree: Path, tmp_path: Path
) -> None:
    digest = genuine_digest(verify_module, tmp_path)
    commit_digest(phase7_tree, digest)
    outcome = run(verify_module, ALPHA, phase7_tree)
    assert outcome.result is verify_module.Result.PASS, outcome.message
    message = outcome.message
    assert "criterion raised" not in message
    for fact in (
        "run-digest-tier3-em.json",
        "window 2024-07-06T00:00Z to 2024-07-12T00:00Z",
        "tier 3",
        "ranking expected_move",
        f"scenario {digest['scenario_digest'][:12]}",
        "BTC/USD buy-and-hold: alpha",
        "held-pairs basket: alpha",
        "every day regressed with flat days included",
    ):
        assert fact in message, (fact, message)


def test_the_alpha_report_checks_every_committed_digest(
    verify_module: ModuleType, phase7_tree: Path, tmp_path: Path
) -> None:
    digest = genuine_digest(verify_module, tmp_path)
    commit_digest(phase7_tree, digest, "a")
    broken = copy.deepcopy(digest)
    broken["flat_days"] += 1
    commit_digest(phase7_tree, broken, "b")
    outcome = run(verify_module, ALPHA, phase7_tree)
    assert_fail(outcome, verify_module)
    assert outcome.message.startswith("run-digest-b.json: "), outcome.message


def _drop_flat_days(verify_module: ModuleType, digest: dict[str, Any]) -> None:
    """Planted defect 1: the fits recomputed over the days the run held a position only."""
    with verify_module.root_import_path(verify_module.REPO_ROOT):
        from acsoe.research.attribution import regress

    def returns(levels: Sequence[Any]) -> list[float]:
        values = [float(v) for v in levels]
        return [values[i + 1] / values[i] - 1.0 for i in range(len(values) - 1)]

    y, x = returns(digest["equity_levels"]), returns(digest["btc_levels"])
    keep = [i for i, r in enumerate(y) if r != 0.0]
    assert 3 <= len(keep) < len(y), "the fabricated run must carry flat days to drop"
    fit = regress(
        [y[i] for i in keep], [x[i] for i in keep],
        lag=digest["btc"]["hac_lag"], lag_basis=digest["btc"]["lag_basis"],
    )
    digest["btc"] = json.loads(json.dumps(dataclasses.asdict(fit)))


def _pin_window(verify_module: ModuleType, digest: dict[str, Any]) -> None:
    """Planted defect 2: a benchmark marked over a constant window, not the run's."""
    del verify_module
    shift = 86_400 * 1_000_000 * 3
    digest["grid_us"] = [g - shift for g in digest["grid_us"]]


PLANTED_DIGEST_DEFECTS: dict[str, tuple[Any, str]] = {
    "flat days dropped": (_drop_flat_days, "days were dropped"),
    "a constant window": (_pin_window, "the benchmark was not marked over the run's own window"),
    "a stated alpha not from the series": (
        lambda _v, d: d["btc"].update(alpha_daily=d["btc"]["alpha_daily"] + 1e-4),
        "the BTC/USD fit states alpha_daily",
    ),
    "a basket fit that was never computed": (
        lambda _v, d: d.update(basket=None),
        "the basket fit is absent in the digest and present when recomputed",
    ),
    "a decision bar with no equity row": (
        lambda _v, d: d["coverage"].update(decision_bars=d["coverage"]["decision_bars"] - 1),
        "decision bars carry an equity row of",
    ),
    "flat days miscounted": (
        lambda _v, d: d.update(flat_days=d["flat_days"] + 1),
        "flat day(s); its equity series has",
    ),
    "a scenario digest from another description": (
        lambda _v, d: d["scenario_description"].update(ranking="alphabetical_baseline"),
        "is not the sha256 of the description",
    ),
    "a grid that is not whole days": (
        lambda _v, d: d["grid_us"].__setitem__(-1, d["grid_us"][-1] - 1),
        "the grid is not whole days apart",
    ),
    "a tail misstated": (
        lambda _v, d: d.update(tail_excluded_s=d["tail_excluded_s"] + 60),
        "and the digest states a tail of",
    ),
    "a significance verdict not from the series": (
        lambda _v, d: d["btc"].update(significant=not d["btc"]["significant"]),
        "the BTC/USD fit states significant",
    ),
    "a HAC lag below the rule": (
        lambda _v, d: [d[k].update(hac_lag=0) for k in ("btc", "basket")],
        "below the Newey-West rule's",
    ),
    "a series shorter than the grid": (
        lambda _v, d: d["btc_levels"].pop(),
        "btc_levels has",
    ),
}


@pytest.mark.parametrize("defect", sorted(PLANTED_DIGEST_DEFECTS))
def test_a_digest_carrying_a_planted_defect_fails(
    verify_module: ModuleType, phase7_tree: Path, tmp_path: Path, defect: str
) -> None:
    plant, named = PLANTED_DIGEST_DEFECTS[defect]
    digest = genuine_digest(verify_module, tmp_path)
    plant(verify_module, digest)
    commit_digest(phase7_tree, digest)
    outcome = run(verify_module, ALPHA, phase7_tree)
    assert_fail(outcome, verify_module)
    assert "criterion raised" not in outcome.message, outcome.message
    assert named in outcome.message, outcome.message


def test_an_attribution_that_drops_flat_days_fails_before_any_digest_is_read(
    verify_module: ModuleType, phase7_tree: Path, repo_root: Path
) -> None:
    """The producer-side defect, planted in a copy of spec 138's module: the fabricated
    pipeline catches it even with no digest committed. The regression drops the flat days
    from both series, so nothing raises and only the day count can tell."""
    before = break_copy(
        phase7_tree, repo_root, ATTRIBUTION,
        b"    n = len(y)\n    if len(set(x)) < 2:\n",
        b"    keep = [i for i, v in enumerate(y) if v != 0.0]\n"
        b"    y, x = [y[i] for i in keep], [x[i] for i in keep]\n"
        b"    n = len(y)\n    if len(set(x)) < 2:\n",
    )
    outcome = run(verify_module, ALPHA, phase7_tree)
    assert hashlib.sha256((repo_root / ATTRIBUTION).read_bytes()).hexdigest() == before
    assert_fail(outcome, verify_module)
    assert "criterion raised" not in outcome.message, outcome.message
    assert "days were dropped" in outcome.message, outcome.message


def test_a_report_that_refuses_the_fabricated_run_is_a_fail_naming_the_refusal(
    verify_module: ModuleType, phase7_tree: Path, repo_root: Path
) -> None:
    """A producer that raises on the fabricated run is a FAIL with its reason, not a crash."""
    before = break_copy(
        phase7_tree, repo_root, ATTRIBUTION,
        b"    y = _returns([float(v) for v in equity])\n",
        b"    y = [r for r in _returns([float(v) for v in equity]) if r != 0.0]\n",
    )
    outcome = run(verify_module, ALPHA, phase7_tree)
    assert hashlib.sha256((repo_root / ATTRIBUTION).read_bytes()).hexdigest() == before
    assert_fail(outcome, verify_module)
    assert "criterion raised" not in outcome.message, outcome.message
    assert "the report refused a fabricated run" in outcome.message, outcome.message


def test_an_attribution_whose_window_is_a_constant_fails_before_any_digest_is_read(
    verify_module: ModuleType, phase7_tree: Path, repo_root: Path
) -> None:
    before = break_copy(
        phase7_tree, repo_root, ATTRIBUTION,
        b"    start, end = stamps[0], stamps[-1]\n",
        b"    start, end = 1_720_224_000_000_000 + 3_600_000_000, stamps[-1]\n",
    )
    outcome = run(verify_module, ALPHA, phase7_tree)
    assert hashlib.sha256((repo_root / ATTRIBUTION).read_bytes()).hexdigest() == before
    assert_fail(outcome, verify_module)
    assert "the benchmark is not following the run's own window" in outcome.message


def test_the_alpha_report_is_pending_while_the_module_lacks_the_digest_recomputation(
    verify_module: ModuleType, phase7_tree: Path, repo_root: Path
) -> None:
    before = break_copy(
        phase7_tree, repo_root, ATTRIBUTION,
        b"def regress_digest(", b"def _not_yet_regress_digest(",
    )
    outcome = run(verify_module, ALPHA, phase7_tree)
    assert hashlib.sha256((repo_root / ATTRIBUTION).read_bytes()).hexdigest() == before
    assert_pending(outcome, verify_module)
    assert "no regress_digest yet (spec 138)" in outcome.message


# --------------------------------------------------------------------------- #
# fee_scenario_is_replay_only: the one named producer (lead ruling D22)
# --------------------------------------------------------------------------- #

#: What the bucket table's builder legitimately names: its output's directory, built from
#: pieces, and the fixture's own name.
PRODUCER_SOURCE = (
    b"from pathlib import Path\n"
    b'FIXTURE_DIR = Path("tests") / "fixtures" / "replay"\n'
    b'TARGET = FIXTURE_DIR / "spread_book_table_2026-09-19.json"\n'
)


def plant_script(tree: Path, relative: str, source: bytes) -> None:
    path = tree / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source)


def test_the_named_producer_may_name_the_table_it_writes(
    verify_module: ModuleType, phase7_tree: Path
) -> None:
    plant_script(phase7_tree, "scripts/build_bucket_table.py", PRODUCER_SOURCE)
    outcome = run(verify_module, "fee_scenario_is_replay_only", phase7_tree)
    assert outcome.result is verify_module.Result.PASS, outcome.message


@pytest.mark.parametrize(
    "relative",
    [
        "scripts/build_bucket_table_v2.py",
        "scripts/recording/build_bucket_table.py",
        "src/acsoe/research/build_bucket_table.py",
    ],
)
def test_the_producer_entry_covers_that_one_file_only(
    verify_module: ModuleType, phase7_tree: Path, relative: str
) -> None:
    plant_script(phase7_tree, relative, PRODUCER_SOURCE)
    outcome = run(verify_module, "fee_scenario_is_replay_only", phase7_tree)
    assert_fail(outcome, verify_module)
    assert relative in outcome.message, outcome.message


@pytest.mark.parametrize(
    ("extra", "named"),
    [
        (b'FEE = "tests/x/kraken_fee_schedule_2026-09-19.json"\n', "kraken_fee_schedule"),
        (b"from acsoe.clients.kraken.replay_scenario import load_spread_table\n",
         "acsoe.clients.kraken.replay_scenario"),
        (b"def f(m):\n    return m.load_spread_table\n", "load_spread_table"),
    ],
)
def test_the_producer_naming_anything_beyond_its_own_table_is_still_caught(
    verify_module: ModuleType, phase7_tree: Path, extra: bytes, named: str
) -> None:
    plant_script(phase7_tree, "scripts/build_bucket_table.py", PRODUCER_SOURCE + extra)
    outcome = run(verify_module, "fee_scenario_is_replay_only", phase7_tree)
    assert_fail(outcome, verify_module)
    assert f"scripts/build_bucket_table.py: {named}" in outcome.message, outcome.message


def test_the_producer_is_pinned_by_exact_path_to_its_two_markers(verify_module: ModuleType) -> None:
    producers = verify_module.FEE_SCENARIO_PRODUCERS
    assert producers == {
        Path("scripts") / "build_bucket_table.py": frozenset({"spread_book_table", "fixtures/replay"})
    }
    readers = {path.as_posix() for path in verify_module.FEE_SCENARIO_READERS}
    assert not readers & {path.as_posix() for path in producers}
