"""The nine Phase 6 criteria. Spec 100.

Three observations per criterion, and the order they arrive in is the phase's order:

* **PENDING** against a tree where the subject does not exist. A criterion that cannot
  reach that state makes a phase impossible to start, which is the whole reason these
  are written in wave 2 of a phase whose engines land in wave 3.
* **PASS** against the subject as it actually is.
* **FAIL**, deliberately induced against a *plausible* wrong implementation.

**Where it stands.** The nine were written while every subject was unbuilt and reported
PENDING, naming the engine or fixture that owed each. Since spec 82 registered the Phase 6
engines, spec 100's bodies landed and spec 101 built the console half, **all nine drive
the registered chain to a verdict**. Each is observed three ways here: PENDING on
`unbuilt_tree`, its verdict on the real tree (`REAL_TREE`), and FAIL under a named
mutation of the thing it judges, made in a copied tree (`MUTATIONS`).

Two branches that *can* be driven to a verdict today are driven to one here, because a
branch nobody has executed is a comment: the fixture that exists and is **empty** (FAIL,
not PENDING — an empty file is a deposited fixture that proves nothing, which is a
different fault from an absent one), and the engine module that exists and declares no
engine class.

**Phase 6 fails expensively**, and that shapes what these check. Every phase before this
one could fail on paper. Here a criterion that quietly stopped judging — because its
subject moved, or because it reported PENDING for a reason that had stopped being true —
would let an unwatched position or an unrecorded fill through the gate. So the tests
below assert on the *content* of each PENDING as well as its result.
"""

from __future__ import annotations

import ast
import hashlib
import re
import shutil
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.verify.conftest import fabricate_package
from tests.verify.test_phase2_criteria import (
    assert_fail,
    assert_pass,
    assert_pending,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Registered in this order, and the order is read top to bottom in the report.
PHASE6_CRITERIA = (
    "paper_trade_round_trip_target",
    "paper_trade_round_trip_stop",
    "paper_trade_round_trip_timeout",
    "unfilled_entry_cancels_without_chasing",
    "triggered_stop_holds_on_data_guard_block",
    "escalation_completes_during_outage",
    "console_shows_position_live",
    "order_book_slippage_on_recorded_book",
    "adaptive_router_weights_on_fixture",
)

#: Spec 105's criterion, registered after spec 100's nine. Kept out of `PHASE6_CRITERIA`,
#: whose tests are about spec 100's clauses; its own tests are near the end of this file.
EQUITY_ACROSS_FILL = "paper_equity_continuous_across_fill"

#: The operator's criterion of 2026-09-17, registered last. Its FAIL is today's code.
EQUITY_ROWS = "equity_row_never_values_positions_it_does_not_hold"

#: Spec 118, operator ruling 2026-09-18. Registered after the nine were green and kept
#: out of `PHASE6_CRITERIA` for the same reason the two above are: it judges neither an
#: engine nor the chain, so the clauses of spec 100 — the tier sentence, the PENDING that
#: names an absent engine — are not statements about it. Its own tests are at the end of
#: this file.
FIXTURES_AGREE = "recorded_book_agrees_with_recorded_pair_decimals"

#: The seven that drive a trade through the gates. Ruling 8 of the Phase 6 task list:
#: each names its fee regime in its own message.
TRADE_DRIVING = (
    "paper_trade_round_trip_target",
    "paper_trade_round_trip_stop",
    "paper_trade_round_trip_timeout",
    "unfilled_entry_cancels_without_chasing",
    "triggered_stop_holds_on_data_guard_block",
    "escalation_completes_during_outage",
    "console_shows_position_live",
)

#: The two that drive the chain only far enough to reach their engine. They name tier 3
#: too, because the chain they drive runs at tier 3 (engine 14 sits after the cost gate
#: and can be reached at no other tier), and they say the thing they judge reads no fee.
NOT_TRADE_DRIVING = (
    "order_book_slippage_on_recorded_book",
    "adaptive_router_weights_on_fixture",
)

#: What each criterion reports on the real registered tree, and a fragment its message
#: must carry.
#:
#: **This replaced `AWAITED`** when spec 100's bodies landed. `AWAITED` named the engine
#: each PENDING was waiting for, and it moved three times as engines 16, 18 and 22 landed.
#: Each move was a red test and a deliberate edit. Moving from PENDING to a verdict is the
#: last move, and it is made the same way.
REAL_TREE: dict[str, tuple[str, str]] = {
    "paper_trade_round_trip_target": ("PASS", "it exited at the target"),
    "paper_trade_round_trip_stop": ("PASS", "it exited at the stop"),
    "paper_trade_round_trip_timeout": ("PASS", "it exited at the timeout"),
    "unfilled_entry_cancels_without_chasing": ("PASS", "and not before"),
    "triggered_stop_holds_on_data_guard_block": ("PASS", "placed no exit"),
    "escalation_completes_during_outage": ("PASS", "can never find one"),
    "console_shows_position_live": ("PASS", "live, not a snapshot"),
    "order_book_slippage_on_recorded_book": ("PASS", "equals engine 9's payload exactly"),
    "adaptive_router_weights_on_fixture": ("PASS", "a property of the fixture"),
}

_NO_PYCACHE = shutil.ignore_patterns("__pycache__", "*.pyc")


@pytest.fixture
def phase6_tree(bare_tree: Path, repo_root: Path) -> Path:
    """The real package, config, migrations, harness and fixtures, copied.

    Deliberately not a fabricated `acsoe`, for the reason `phase5_tree` gives: these
    criteria drive real engines through the real orchestrator, and a tree assembled the
    other way round — fabricated contracts with a real module dropped in — is how
    `check_data_guard_blocks_bad_data` came to have a body that never executed while
    both halves of its proof passed.
    """
    shutil.copytree(repo_root / "src" / "acsoe", bare_tree / "src" / "acsoe", ignore=_NO_PYCACHE)
    shutil.copytree(repo_root / "config", bare_tree / "config")
    shutil.copytree(repo_root / "db", bare_tree / "db", ignore=_NO_PYCACHE)
    tests = bare_tree / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "__init__.py").write_bytes(b"")
    shutil.copytree(repo_root / "tests" / "harness", tests / "harness", ignore=_NO_PYCACHE)
    shutil.copytree(repo_root / "tests" / "fixtures", tests / "fixtures", ignore=_NO_PYCACHE)
    return bare_tree


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def test_all_nine_criteria_are_registered_for_phase_6(verify_module: ModuleType) -> None:
    """Membership **and** order.

    The report is read top to bottom, and the three round trips come first because
    they are the phase in one line: a candidate becomes a filled position and the
    position is recorded. A criterion registered into the wrong phase is silent — it
    simply never runs, or runs a phase too early — which is why this is pinned rather
    than assumed.
    """
    registered = [c.name for c in verify_module._REGISTRY[6]]
    every_phase = ("docs_vocabulary", "toolchain_green")
    assert [name for name in registered if name not in every_phase] == [
        *PHASE6_CRITERIA,
        EQUITY_ACROSS_FILL,
        EQUITY_ROWS,
        FIXTURES_AGREE,
    ]


def test_every_phase_6_criterion_is_offline_and_never_live_only(
    verify_module: ModuleType,
) -> None:
    """None of these is opt-in. A phase whose criteria only run under `--live` is a
    phase that closes green on a machine that never ran them."""
    for criterion in verify_module._REGISTRY[6]:
        assert criterion.live is False, criterion.name


# --------------------------------------------------------------------------- #
# PENDING, and what the PENDING has to say
# --------------------------------------------------------------------------- #


#: The PENDING an absent engine produces, as the first clause of the message.
_ABSENT_ENGINE = re.compile(r"engine \d+ `[a-z_]+` does not exist yet ")


@pytest.mark.parametrize("name", PHASE6_CRITERIA)
def test_pending_on_a_tree_with_nothing_built(
    verify_module: ModuleType, unbuilt_tree: Path, name: str
) -> None:
    """Every criterion reports PENDING, on a missing engine, where nothing is built.

    None of the nine may raise there and none may report PASS or FAIL: a FAIL on an
    unbuilt tree is an accusation against work nobody has done, and a PASS is worse.

    **`unbuilt_tree`, not `bare_tree`.** This test used `bare_tree` until spec 82, and
    on that tree the editable install resolves `acsoe` to the real repository. Seven of
    the nine got past every engine guard there and stopped at their "not written yet"
    placeholder, and engines 9 and 14 were imported for real. The test was green only
    because of the placeholders, so it never saw a missing subject. It could not catch
    a criterion that mishandles one, and a correctly guarded body would have run the
    real chain and turned it red. The empty package in `unbuilt_tree` shadows the real
    one. The build log has the measurement.

    Hence the second assertion: the PENDING has to be *about* the absent engine. Any
    other PENDING here means the criterion got past a guard it had nothing to pass.
    """
    outcome = run(verify_module, name, unbuilt_tree)
    assert_pending(outcome, verify_module)
    assert _ABSENT_ENGINE.match(outcome.message), f"{name}: {outcome.message}"


@pytest.fixture(scope="module")
def real_tree_outcomes(verify_module: ModuleType, repo_root: Path) -> dict[str, Any]:
    """Every Phase 6 criterion, run once on the real repository for this module.

    Each one drives the registered chain, so running it again for every assertion would
    multiply the suite's largest cost for nothing. The outcome is a value, and every test
    below reads it.
    """
    return {
        name: run(verify_module, name, repo_root)
        for name in (*PHASE6_CRITERIA, EQUITY_ACROSS_FILL, EQUITY_ROWS)
    }


@pytest.mark.parametrize("name", PHASE6_CRITERIA)
def test_the_real_tree_verdict_and_what_it_says(
    verify_module: ModuleType, real_tree_outcomes: dict[str, Any], name: str
) -> None:
    """The verdict the gate reports on the registered tree, and what the line says.

    Nine PASS since spec 101. A PASS line has to say what was shown, because the operator
    reads it; the fragment pins the claim each one exists to make, and
    `console_shows_position_live` was the ninth — PENDING and naming spec 101 until the
    console grew `hold_reason` and this criterion grew the drive that reads it back. A
    message that says `criterion raised` is a stack trace and judged nothing.
    """
    outcome = real_tree_outcomes[name]
    result, fragment = REAL_TREE[name]
    assert outcome.result is getattr(verify_module.Result, result), outcome
    assert "criterion raised" not in outcome.message, outcome.message
    assert fragment in outcome.message, (fragment, outcome.message)


@pytest.mark.parametrize("name", PHASE6_CRITERIA)
def test_every_phase_6_criterion_names_fee_tier_3_in_its_own_message(
    real_tree_outcomes: dict[str, Any], name: str
) -> None:
    """Ruling 8, checked on the text the operator actually sees.

    At tier 1 the cost gate is unreachable by construction. The bar is 2.5x friction,
    tier-1 reference friction is about 1.25% round trip, and 3.125% is above the 3.0%
    target barrier, so nothing clears and a verdict from that regime says nothing about
    the engines. All nine drive the registered chain at tier 3, so all nine say so.
    """
    message = real_tree_outcomes[name].message
    assert "tier 3" in message, message
    assert "no-trade regime" in message, message


@pytest.mark.parametrize("name", NOT_TRADE_DRIVING)
def test_the_two_that_trade_nothing_say_their_subject_reads_no_fee(
    real_tree_outcomes: dict[str, Any], name: str
) -> None:
    """The other half of ruling 8. These two drive the chain at tier 3 only to reach
    their engine, and the message says so. A reader must not take the weights or the
    walk for something the fee schedule decided.

    This replaced `test_the_two_criteria_that_drive_no_trade_claim_no_fee_regime`. That
    test was right while these criteria applied no tier. Once they drive the chain at
    tier 3, a message that hid the tier would be the untrue statement.
    """
    message = real_tree_outcomes[name].message
    assert "driven through the registered engines so that it reaches engine" in message, message


def test_no_criterion_reads_the_repositorys_data_models_or_logs(
    verify_module: ModuleType,
) -> None:
    """The fresh-clone rule, read off the source rather than trusted.

    All three directories are gitignored, so a criterion that reached into one would
    pass on the machine that produced it and report PENDING or FAIL on a clone. This
    catches the copy-paste a behavioural test cannot: a criterion reading
    `data/db/live.sqlite` on a developer's machine finds a real database and reports a
    real PASS, on this machine, forever.

    **The rule is about the repository's directories, not about the words.** Three
    versions of this test came first and each looked right, which is why they are
    written down rather than quietly replaced.

    A plain substring search over the section text went red on the prose explaining the
    rule. Stripping comments and strings and searching the code is worse: it drops the
    string literals a path is built from, and `data_guard` matches "data" in an
    identifier. Searching every string literal for the three names went red on
    `tmp / "subject" / "models"` — a **temporary** directory that happens to be called
    models, which is not a violation of anything and is where the subject's artefacts
    are supposed to go.

    So the check is what the rule actually says. Any `/` chain rooted at `ctx.root` or
    at `REPO_ROOT` must not name one of the three, and no literal anywhere in the
    section may carry one of them as a path segment.
    """
    del verify_module
    source = (REPO_ROOT / "scripts" / "verify.py").read_text(encoding="utf-8")
    start = source.index("# Phase 6 - decision and execution. Spec 100.")
    end = source.index("# Registration", start)
    section = source[start:end]
    tree = ast.parse(section)
    forbidden = ("data", "models", "logs")

    def base_and_parts(node: ast.AST) -> tuple[ast.AST, list[str]]:
        """The leftmost operand of a `/` chain, and the string segments joined to it."""
        parts: list[str] = []
        while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            if isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
                parts.append(node.right.value)
            node = node.left
        return node, parts

    rooted = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
            continue
        base, parts = base_and_parts(node)
        is_ctx_root = (
            isinstance(base, ast.Attribute)
            and base.attr == "root"
            and isinstance(base.value, ast.Name)
            and base.value.id == "ctx"
        )
        is_repo_root = isinstance(base, ast.Name) and base.id == "REPO_ROOT"
        if not (is_ctx_root or is_repo_root):
            continue
        rooted += 1
        for segment in parts:
            assert segment not in forbidden, (
                f"a Phase 6 criterion builds a path into the repository's {segment}/. "
                "All three are gitignored, so a criterion that reads one passes only on "
                "the machine that produced it."
            )
    assert rooted >= 1, (
        "no path rooted at ctx.root was found at all, so this search would pass "
        "vacuously — `_phase6_fixture` builds one"
    )

    # Docstrings are excluded from the literal sweep: the section's prose says
    # `models/<run_id>/` while explaining what the subject builds, and a test that
    # cannot tell its own rule from a statement of it is the first version of this test
    # again. A path a criterion opens is never a docstring.
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]
    assert any("tests/fixtures/" in text for text in literals), (
        "no path literal was found at all, so this sweep would pass vacuously"
    )
    for text in literals:
        for name in forbidden:
            for separator in ("/", "\\"):
                assert name + separator not in text, (
                    f"the Phase 6 section carries the path {text!r}, which names the "
                    f"repository's {name}/."
                )


# --------------------------------------------------------------------------- #
# The two branches that can be driven to a verdict today
# --------------------------------------------------------------------------- #


def test_a_fixture_that_exists_and_is_empty_fails_rather_than_pending(
    verify_module: ModuleType, phase6_tree: Path
) -> None:
    """An absent fixture and an empty one are different faults with different owners.

    Absent means nobody has cut it yet, which is a schedule fact and a PENDING. Empty
    means somebody deposited a file and it carries nothing, which is a broken deposit
    and would otherwise read as "the walk found no levels" or "the leaderboard has no
    models" — a criterion passing over an empty fixture is the vacuous pass this
    project has been burned by three times.

    Driven here rather than described, because `_phase6_fixture`'s FAIL branch is
    otherwise unreachable until spec 96 deposits something.
    """
    (phase6_tree / "tests" / "fixtures" / "book_sample.jsonl").write_bytes(b"")
    fabricate_package(
        phase6_tree,
        {
            "acsoe.engines.order_book.engine": (
                "class OrderBookEngine:\n"
                "    name = 'order_book'\n"
                "    number = 9\n"
                "    is_gate = False\n"
            )
        },
    )
    outcome = run(verify_module, "order_book_slippage_on_recorded_book", phase6_tree)
    assert_fail(outcome, verify_module)
    assert "empty" in outcome.message and "book_sample.jsonl" in outcome.message, outcome.message


def test_an_engine_module_that_declares_no_engine_class_is_named_as_such(
    verify_module: ModuleType, phase6_tree: Path
) -> None:
    """The half-built engine, which is what an interrupted session leaves behind.

    `acsoe.engines.adaptive_router.engine` importing cleanly and holding no class with
    `name = "adaptive_router"` and `number = 14` is not the same as the module being
    absent, and a PENDING saying "does not exist yet" would send somebody to write a
    file that is already there. Phase 6 opened on exactly this state in another lane —
    `modelling/di.py` naming `score_many` in `__all__` and not defining it — so the
    distinction is not hypothetical.
    """
    fabricate_package(
        phase6_tree,
        {"acsoe.engines.adaptive_router.engine": "ROUTER_IS_COMING = True\n"},
    )
    outcome = run(verify_module, "adaptive_router_weights_on_fixture", phase6_tree)
    assert_pending(outcome, verify_module)
    assert "declares no class" in outcome.message, outcome.message
    assert "number = 14" in outcome.message, outcome.message


@pytest.mark.parametrize("name", TRADE_DRIVING)
def test_the_tier_sentence_is_pending_rather_than_wrong_when_the_harness_is_absent(
    verify_module: ModuleType, phase6_tree: Path, name: str
) -> None:
    """A criterion that cannot read the named tiers must not invent one.

    The sentence lives in `tests/harness/fake_kraken.py` beside the profile it
    describes, so the tier a criterion reports and the tier it applied come from one
    file. Here the copied tree has every engine and **no harness**: its own `tests`
    package shadows the repository's, so `tests.harness` cannot be imported. The answer
    must be PENDING naming the harness, and the message may say only which regime it
    *will* run in, not that it ran in one.

    Until spec 100's bodies this test took `bare_tree`, called `_tier_sentence` in the
    real repository, and never observed the PENDING its name promised.
    """
    shutil.rmtree(phase6_tree / "tests" / "harness")
    outcome = run(verify_module, name, phase6_tree)
    assert_pending(outcome, verify_module)
    assert "tests.harness.fake_kraken" in outcome.message, outcome.message
    assert "run at fee tier 3" in outcome.message, outcome.message
    with pytest.raises(ValueError, match="no sentence for tier 2"):
        verify_module._tier_sentence(2)


# --------------------------------------------------------------------------- #
# The trade-producing subject — spec 100 step 2
# --------------------------------------------------------------------------- #


def test_the_planted_market_produces_a_real_buy_above_the_tier_3_bar(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """The one thing in spec 100 that could have been a finding instead of code.

    Step 2 asks for a candidate that is *a real BUY with an expected move above the
    tier-3 bar of 1.625%*, produced by the real predictor, not refused by the DI and not
    vetoed — and says in as many words that if that cannot be produced honestly it is
    raised to the lead rather than routed around with a hand-built `state`. So the claim
    is checked rather than asserted in a comment.

    **Everything except the prices is the committed code.** The labeller, the feature
    module, `research/training.py`, the calibrator, the DI and the anomaly detector are
    all reached through `_trained`; the one substitution is the candle builder.

    Three properties, and each of them is a way the subject could be quietly useless:

    * at least one out-of-sample row is a BUY, above the bar, with the DI not refusing —
      without it there is nothing for a round trip to be about;
    * the expected move stays **below the 3.0% target barrier**, since an expected move
      at or above the barrier it predicts a touch of is arithmetically impossible unless
      `p_target` is one and the stop term has vanished;
    * **the model is wrong about some of them.** Some rows it calls a BUY on above the
      bar are labelled `stop` by the real labeller, and `p_target` runs down into the
      low nineties and below. That is the property "not a memorised rule" actually
      cashes out to, and it is asserted on outcomes rather than on a probability
      ceiling — see the build log for why a ceiling was the wrong assertion.

    It trains a real walk-forward and costs about nine seconds. That cost is paid once
    per process — see `_TRADE_SUBJECTS` — and the test below shows that it is.
    """
    polars = pytest.importorskip("polars")
    subject, problem = verify_module._trade_subject_model(
        verify_module.VerifyContext(root=repo_root)
    )
    assert subject is not None, problem
    buys = verify_module._subject_buy_rows(subject, polars)
    assert buys.height > 0, (
        "the planted market produced no BUY above the tier-3 bar of "
        f"{verify_module.TIER_3_REFERENCE_HURDLE_PCT}. That is spec 100's named finding "
        "and is raised to the lead, not worked around."
    )
    moves = buys["expected_move_pct"].to_list()
    assert max(moves) < 0.03, (
        "an expected move at or above the 3.0% target barrier means p_target is one and "
        f"the stop term has vanished: {max(moves)}"
    )
    assert min(buys["p_target"].to_list()) < 0.95, (
        "every BUY above the bar is near-certain, so the chain would never be driven by "
        "a candidate the model is unsure about"
    )
    outcomes = dict(
        zip(
            buys["label"].value_counts()["label"].to_list(),
            buys["label"].value_counts()["count"].to_list(),
            strict=True,
        )
    )
    assert outcomes.get("target", 0) > 0, outcomes
    assert sum(count for label, count in outcomes.items() if label != "target") > 0, (
        "every BUY above the bar reached the target, so the planted pattern has been "
        f"learned as a deterministic rule: {outcomes}"
    )


def test_the_trained_subject_is_shared_across_criteria_and_the_database_is_not(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """Spec 100 step 6, and the half of it that is a hazard rather than a saving.

    Sharing one trained run across criteria is what keeps the gate's largest cost from
    being paid six times. Sharing anything *mutable* would let one criterion's state
    reach another's verdict, which is the failure the step is warning about — so the
    cache holds the fitted artefacts, which are read-only once written, and holds no
    store, no database and no broker ledger.

    Asserted by identity, not by equality: two equal `TradeSubjectModel`s built by two
    training runs would satisfy `==` and would mean the cost was paid twice.
    """
    ctx = verify_module.VerifyContext(root=repo_root)
    first, _ = verify_module._trade_subject_model(ctx)
    second, _ = verify_module._trade_subject_model(ctx)
    assert first is second, "the trained subject was rebuilt rather than reused"
    cached = verify_module._TRADE_SUBJECTS[str(repo_root)]
    for forbidden in ("store", "db", "broker", "ledger", "conn"):
        assert not hasattr(cached, forbidden), forbidden
    assert cached.seconds > 0, "the training cost was not recorded"


# --------------------------------------------------------------------------- #
# Spec 105 — paper_equity_continuous_across_fill
# --------------------------------------------------------------------------- #
#
# PENDING, PASS and FAIL, each observed. The FAIL is the named wrong implementation: the
# broker as it was before spec 103, whose balance leaves out a fill engine 19 has not
# recorded yet. The break is made in the **copied** tree, never in the real file,
# because this test runs inside `toolchain_green` and other pytest runs share the
# checkout. The in-place run against the real file was made once, by hand, with a byte
# copy and a hash-checked restore; the build log has it.

#: The one line spec 103 added the executed-but-unrecorded fills with, and its broken form.
#: A's spec 87 used the same break for the same proof.
BROKER_ANCHOR = b"        for userref, executed in list(self._executed.items()):\n"
BROKER_BROKEN = b"        for userref, executed in []:\n"

_MOVED = re.compile(r"it moved (-?[0-9.]+)\. The fill's own cost is (-?[0-9.]+): fee (-?[0-9.]+) ")


def moved_and_bound(outcome: object) -> tuple[Decimal, Decimal, Decimal]:
    """`(moved, tolerance, fee)` as the criterion reported them.

    Parsed rather than searched, so a message that merely mentions the words cannot
    pass. A message from a criterion that raised is refused outright: it has judged
    nothing.
    """
    message = str(getattr(outcome, "message", outcome))
    assert "criterion raised" not in message, message
    found = _MOVED.search(message)
    assert found is not None, "not an equity-across-fill verdict: " + message
    return Decimal(found[1]), Decimal(found[2]), Decimal(found[3])


def assert_names_tier_3(outcome: object) -> None:
    message = str(getattr(outcome, "message", outcome))
    assert "at fee tier 3" in message, message
    assert "no-trade regime" in message, message


def test_equity_across_fill_is_pending_on_a_tree_with_nothing_built(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    """An empty `acsoe` package: PENDING, naming the first engine it needs and its spec.

    **`unbuilt_tree`, not `bare_tree`.** On `bare_tree` the editable install resolves
    `acsoe` to the real repository, so this criterion ran the whole chain and reported
    PASS there. The first version of this test did exactly that; the build log has it.
    An empty package in the tree shadows the real one, which is the honest picture of
    nothing built.
    """
    outcome = run(verify_module, EQUITY_ACROSS_FILL, unbuilt_tree)
    assert_pending(outcome, verify_module)
    assert "engine 9 `order_book`" in outcome.message, outcome.message
    assert "spec 96" in outcome.message, outcome.message
    assert_names_tier_3(outcome)


def test_equity_across_fill_is_pending_without_the_paper_broker(
    verify_module: ModuleType, phase6_tree: Path
) -> None:
    """Every engine present and the broker absent: PENDING naming the broker's spec.

    Checked before anything is trained, so this costs nothing and says who owes the
    subject rather than failing on an import.
    """
    shutil.rmtree(phase6_tree / "src" / "acsoe" / "clients" / "paper")
    outcome = run(verify_module, EQUITY_ACROSS_FILL, phase6_tree)
    assert_pending(outcome, verify_module)
    assert "acsoe.clients.paper" in outcome.message, outcome.message
    assert "spec 88" in outcome.message, outcome.message
    assert_names_tier_3(outcome)


def test_equity_across_fill_passes_on_the_real_tree(
    verify_module: ModuleType, real_tree_outcomes: dict[str, Any]
) -> None:
    """The real chain places, fills and records an entry, and equity moves by the fee.

    Engine 21 stores a position opened this tick marked at its fill price (spec 106), so
    the mark-to-bid part of the bound is zero on the fill tick and the tolerance is the
    maker fee alone.
    The equity row therefore moves by exactly minus the fee, which is asserted, so a
    criterion whose bound had drifted wide would not pass this test by being loose.
    """
    outcome = real_tree_outcomes[EQUITY_ACROSS_FILL]
    assert outcome.result is verify_module.Result.PASS, outcome
    moved, bound, fee = moved_and_bound(outcome)
    assert fee > 0, outcome.message
    assert bound == fee, "the fill tick carries a mark gap, so the bound is wider than the fee"
    assert moved == -fee, outcome.message
    assert_names_tier_3(outcome)


def test_equity_across_fill_fails_when_the_broker_leaves_out_an_unrecorded_fill(
    verify_module: ModuleType, phase6_tree: Path, repo_root: Path
) -> None:
    """The defect put back, in the copy, and the criterion names it.

    On the fill tick the broken ledger still holds the cash the entry spent while engine
    21 counts the position, so equity jumps by the whole notional: far outside the fee.
    The real broker is hashed on both sides, so this test is shown not to have touched it.
    """
    real = repo_root / "src" / "acsoe" / "clients" / "paper" / "broker.py"
    real_before = hashlib.sha256(real.read_bytes()).hexdigest()
    copy = phase6_tree / "src" / "acsoe" / "clients" / "paper" / "broker.py"
    source = copy.read_bytes()
    assert source.count(BROKER_ANCHOR) == 1, "the anchor moved; the break would not apply"
    copy.write_bytes(source.replace(BROKER_ANCHOR, BROKER_BROKEN))

    outcome = run(verify_module, EQUITY_ACROSS_FILL, phase6_tree)

    assert hashlib.sha256(real.read_bytes()).hexdigest() == real_before
    assert_fail(outcome, verify_module)
    moved, bound, fee = moved_and_bound(outcome)
    assert moved > bound >= fee > 0, outcome.message
    assert "counted twice" in outcome.message, outcome.message
    assert_names_tier_3(outcome)


#: Engine 21's write of the fill-tick mark (spec 106), and B's mutant P1: the write gone,
#: so the position is stored with `last_price` NULL on the tick its fill opened it.
POSITION_MANAGER_MARK_ANCHOR = b'            position_row["last_price"] = format(mark, "f")\n'


def test_equity_across_fill_fails_when_the_fill_tick_position_is_stored_with_no_mark(
    verify_module: ModuleType, phase6_tree: Path, repo_root: Path
) -> None:
    """Spec 107: a NULL fill-tick mark is a FAIL naming the missing mark.

    Since spec 106 engine 21 stores the fill price as the mark of a position its tick's
    fill opened. The copy here drops that write (B's mutant P1). Before spec 107 the
    criterion then read the equity row instead, found it valued at cost, and reported
    PASS, so it could not tell the defect from the fix. The equity row is still right
    under this mutant, because engine 21's totals are untouched. The only thing wrong
    is the stored row, so the verdict has to come from the row.
    """
    real = repo_root / "src" / "acsoe" / "engines" / "position_manager" / "engine.py"
    real_before = hashlib.sha256(real.read_bytes()).hexdigest()
    engine = phase6_tree / "src" / "acsoe" / "engines" / "position_manager" / "engine.py"
    source = engine.read_bytes()
    assert source.count(POSITION_MANAGER_MARK_ANCHOR) == 1, "the anchor moved; P1 would not apply"
    engine.write_bytes(source.replace(POSITION_MANAGER_MARK_ANCHOR, b""))

    outcome = run(verify_module, EQUITY_ACROSS_FILL, phase6_tree)

    assert hashlib.sha256(real.read_bytes()).hexdigest() == real_before
    assert_fail(outcome, verify_module)
    message = outcome.message
    assert "criterion raised" not in message, message
    assert "stored with no mark (last_price NULL)" in message, message
    assert_names_tier_3(outcome)


#: Engine 19's equity call, and a copy that skips the row on the tick engine 18 ran.
MEMORY_EQUITY_ANCHOR = b"        equity, peak, skipped = self._write_equity(\n"
MEMORY_SKIPS_ENTRY_TICK = (
    b"        if EXECUTION_KEY in state:\n"
    b"            exchange = None\n"
    b"        equity, peak, skipped = self._write_equity(\n"
)


def test_equity_across_fill_fails_when_the_entry_tick_wrote_no_equity_row(
    verify_module: ModuleType, phase6_tree: Path
) -> None:
    """Here "the tick before" means the entry tick, not the last row that exists.

    Engine 19 is made, in the copy, to write no equity row on the tick engine 18 ran.
    The last row before the fill is then the quiet tick's, which holds the same cash and
    would compare clean. A criterion that took it would pass over a gap in the series on
    exactly the tick before a fill. This test exists because the check survived the
    sweep without it.
    """
    engine = phase6_tree / "src" / "acsoe" / "engines" / "memory" / "engine.py"
    source = engine.read_bytes()
    assert source.count(MEMORY_EQUITY_ANCHOR) == 1, "the anchor moved; the skip would not apply"
    engine.write_bytes(source.replace(MEMORY_EQUITY_ANCHOR, MEMORY_SKIPS_ENTRY_TICK))

    outcome = run(verify_module, EQUITY_ACROSS_FILL, phase6_tree)

    assert_fail(outcome, verify_module)
    message = outcome.message
    assert "criterion raised" not in message, message
    assert "so the entry tick wrote none" in message, message
    assert_names_tier_3(outcome)


# --------------------------------------------------------------------------- #
# Spec 100 — each criterion observed to FAIL against a named wrong implementation
# --------------------------------------------------------------------------- #
#
# Every break is made in the **copied** tree and never in the real file, because this
# file runs inside `toolchain_green` and other pytest runs share the checkout. The real
# file is hashed on both sides. Each anchor must occur exactly once, or the break would
# land on whichever occurrence came first and the test would prove nothing about the one
# it names.

_E = "src/acsoe/engines/"

#: `(criterion, file, anchor, replacement, fragment the FAIL must carry)`, by name.
MUTATIONS: dict[str, tuple[str, str, bytes, bytes, str]] = {
    # Engine 21 never decides the target barrier.
    "target_never_triggers": (
        "paper_trade_round_trip_target",
        _E + "position_manager/engine.py",
        b"                elif high is not None and _money(high) >= target_price:\n",
        b"                elif False:\n",
        "engine 21 triggered [] on the exit tick",
    ),
    # Engine 21 holds on a tick nothing blocked, so a touched stop is never taken.
    "held_with_no_block": (
        "paper_trade_round_trip_stop",
        _E + "position_manager/engine.py",
        b"        return state.get(TRADING_BLOCKED_BY_KEY) == DATA_GUARD_NAME\n",
        b"        return True\n",
        "and held for 'data_guard_blocked'",
    ),
    # The timeout compared strictly, so the tick that lands on it does not fire.
    "timeout_compared_strictly": (
        "paper_trade_round_trip_timeout",
        _E + "position_manager/engine.py",
        b'            if barrier is None and now >= int(row["timeout_at"]):\n',
        b'            if barrier is None and now > int(row["timeout_at"]):\n',
        "engine 21 triggered [] on the exit tick",
    ),
    # Engine 22 leaves the exit fee out of the realised PnL.
    "realised_without_exit_fee": (
        "paper_trade_round_trip_stop",
        _E + "exit/engine.py",
        b"        realised = proceeds - cost_basis - entry_fee - exit_fee\n",
        b"        realised = proceeds - cost_basis - entry_fee\n",
        "the trade (outcome, qty, entry, exit, entry fee, exit fee, realised",
    ),
    # Engine 21 re-places the cancelled entry at the bid: a chase.
    "cancelled_entry_replaced": (
        "unfilled_entry_cancels_without_chasing",
        _E + "position_manager/engine.py",
        b"                    cancels.append(self._cancelled_row(entry, cancelled, now))\n",
        (
            b"                    cancels.append(self._cancelled_row(entry, cancelled, now))\n"
            b"                    from acsoe.clients.kraken.contracts import OrderRequest as _Rq\n"
            b"                    from acsoe.clients.kraken.contracts import OrderSide as _Sd\n"
            b"                    from acsoe.clients.kraken.contracts import OrderType as _Tp\n"
            b"                    run_blocking(kraken.add_order(_Rq(pair=str(entry.pair), "
            b"side=_Sd.BUY, order_type=_Tp.LIMIT, qty=_money(entry.qty), "
            b"limit_price=_money(entry.limit_price), post_only=True, "
            b"userref=int(entry.userref) + 1)))\n"
        ),
        "any second order is a chase",
    ),
    # Engine 21 no longer holds on a data_guard block.
    "hold_removed_from_21": (
        "triggered_stop_holds_on_data_guard_block",
        _E + "position_manager/engine.py",
        b"        return state.get(TRADING_BLOCKED_BY_KEY) == DATA_GUARD_NAME\n",
        b"        return False\n",
        "on a tick data_guard blocked",
    ),
    # Engine 22 reads a liquidation as an ordinary tick, so the held position stays held.
    "liquidation_held_by_22": (
        "triggered_stop_holds_on_data_guard_block",
        _E + "exit/engine.py",
        b"        return system.get(CLOSE_INTENT_FIELD) is True\n",
        b"        return False\n",
        "with close_intent set the held position was not sold",
    ),
    # Engine 22 reads this tick's pair rules only, never the retained ones.
    "liquidation_needs_fresh_pair_rules": (
        "escalation_completes_during_outage",
        _E + "exit/engine.py",
        b"        if not close_intent:\n",
        b"        if True:\n",
        "the liquidation did not complete during the outage",
    ),
    # Engine 17 escalates on the limit itself, one blocked tick early.
    "safety_escalates_a_tick_early": (
        "escalation_completes_during_outage",
        _E + "safety/engine.py",
        b"        if readings.consecutive_data_blocks > thresholds.max_consecutive_data_blocks:\n",
        b"        if readings.consecutive_data_blocks >= thresholds.max_consecutive_data_blocks:\n",
        "engine 17 escalated after 15 blocked ticks",
    ),
    # Engine 21 cancels on elapsed time only; close_intent does not cancel an entry.
    "cancel_on_window_only": (
        "escalation_completes_during_outage",
        _E + "position_manager/engine.py",
        b"            if close_intent or expired:\n",
        b"            if expired:\n",
        "into a 300s window engine 21 published []",
    ),
    # Engine 9 walks the ask side.
    "walks_the_ask_side": (
        "order_book_slippage_on_recorded_book",
        _E + "order_book/engine.py",
        b"        walk = walk_the_bid_side(book.bids, basis_notional)\n",
        b"        walk = walk_the_bid_side(book.asks, basis_notional)\n",
        "disagrees with the walk recomputed",
    ),
    # A gate dropped from the registered chain. `bootstrap.py` is the lead's; the break is
    # in the copy. Judged against the chain alone, a missing gate is invisible (sweep arm
    # V1 survived until the criterion compared the chain with the registry table).
    "gate_unregistered": (
        "paper_trade_round_trip_target",
        "src/acsoe/bootstrap.py",
        b"    SkepticEngine(),\n",
        b"",
        "are not the registry table's gates",
    ),
    # The orchestrator runs the opportunity chain with its gates left out. `core/` is the
    # lead's; the break is in the copy. With the real orchestrator a registered gate that
    # did not run cannot sit before an engine that did, so the "every registered gate ran"
    # check had nothing to object to until this arm (sweep arm V1 survived two rounds).
    "orchestrator_skips_the_gates": (
        "paper_trade_round_trip_target",
        "src/acsoe/core/orchestrator.py",
        b"        for engine in self._chains.opportunity:\n",
        b"        for engine in [e for e in self._chains.opportunity if not e.is_gate]:\n",
        "did not run every registered gate",
    ),
    # Engine 21 marks an open position at the ask. The watch compares the stored mark with
    # the pinned bid (sweep arm V13 survived until this arm existed).
    "marked_at_the_ask": (
        "paper_trade_round_trip_stop",
        _E + "position_manager/engine.py",
        b"        bid = _money(quote[QUOTE_BID_FIELD])\n",
        b'        bid = _money(quote["ask"])\n',
        "the stored mark at",
    ),
    # Engine 9 measures slippage against its own fill rather than the best bid. The walk
    # touches the same levels, so a criterion comparing only the level count passes it
    # (sweep arm V8 survived until this arm and the next existed).
    "slippage_against_the_fill": (
        "order_book_slippage_on_recorded_book",
        _E + "order_book/contracts.py",
        b"        return (self.best_bid - self.fill_price) / self.best_bid\n",
        b"        return (self.best_bid - self.fill_price) / self.fill_price\n",
        "'estimated_slippage_pct': (",
    ),
    # Engine 9 prices the partly taken last level at the top bid: same levels, wrong fill.
    "partial_level_priced_at_the_top": (
        "order_book_slippage_on_recorded_book",
        _E + "order_book/contracts.py",
        b"            base_filled += remaining / price\n",
        b"            base_filled += remaining / bids[0][0]\n",
        "'fill_price': (",
    ),
    # Engine 9's walk skips the best level.
    "walk_off_by_a_level": (
        "order_book_slippage_on_recorded_book",
        _E + "order_book/contracts.py",
        b"    for price, quantity in bids:\n",
        b"    for price, quantity in bids[1:]:\n",
        "disagrees with the walk recomputed",
    ),
    # Engine 14 lets a model worse than its base rate take negative weight.
    "skill_not_clipped": (
        "adaptive_router_weights_on_fixture",
        _E + "adaptive_router/engine.py",
        b"    return max(0.0, 1.0 - brier / base_rate)\n",
        b"    return 1.0 - brier / base_rate\n",
        "recomputed from leaderboard_sample.json",
    ),
    # Engine 19 ignores engine 22's facts and writes the pre-exit figures, which is the
    # defect the operator ruled on: the exit tick's cash is engine 1's start-of-tick
    # balance and its positions value is engine 21's total from before the sale, while
    # the position count is read from the store after it. The criterion was written and
    # observed FAIL against exactly this code before spec 114; this arm is that
    # observation, kept.
    "pre_exit_figures_restored": (
        "equity_row_never_values_positions_it_does_not_hold",
        _E + "memory/engine.py",
        b"        if sold or closed:\n",
        b"        if False:\n",
        "value positions the account does not hold",
    ),
    # Spec 101's named mutation: the console serves the previous tick's mark.
    #
    # `entry_price` **is** the previous tick's mark here, and that is why this arm is the
    # one the spec names rather than an arbitrary wrong field. On the fill tick engine 21
    # marks a position at the price it was just filled at — `_mark`'s own docstring says
    # so — so a reader serving `entry_price` is serving exactly the figure the first read
    # legitimately saw. It passes the first read and freezes on the second, which is the
    # whole shape of the defect: a region that renders a correct number once and then
    # stops being live. A reader serving, say, the stop would be caught by the first read
    # and would prove nothing about the second.
    #
    # In C's own lane, and the only entry here that is: every other arm breaks an engine.
    # A criterion whose FAIL arm is in somebody else's file is not observing its own
    # subject go wrong.
    "console_serves_the_previous_mark": (
        "console_shows_position_live",
        "src/acsoe/console/reader.py",
        (
            b"            last_price=row.last_price,\n"
            b'            last_price_text="" if row.last_price is None '
            b"else format_money(row.last_price),\n"
        ),
        (
            b"            last_price=row.entry_price,\n"
            b"            last_price_text=format_money(row.entry_price),\n"
        ),
        "the open-positions region is a snapshot, not live",
    ),
    # Engine 14 keeps the older of two rows for one (version, fold).
    "older_duplicate_kept": (
        "adaptive_router_weights_on_fixture",
        _E + "adaptive_router/engine.py",
        b"        if held is None or _stamp(row) >= _stamp(held):\n",
        b"        if held is None:\n",
        "recomputed from leaderboard_sample.json",
    ),
}


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_each_criterion_fails_against_its_named_wrong_implementation(
    verify_module: ModuleType, phase6_tree: Path, repo_root: Path, mutation: str
) -> None:
    """Break the thing a criterion judges, in the copy, and watch the criterion say so.

    The FAIL must be the criterion's own verdict about the broken behaviour, identified
    by a fragment of its message, and never `criterion raised`. A criterion that fails
    only because the chain stopped earlier than the mutation proves nothing about the
    mutation. The fragments are chosen so that cannot pass.
    """
    name, relative, anchor, replacement, fragment = MUTATIONS[mutation]
    real = repo_root / relative
    real_before = hashlib.sha256(real.read_bytes()).hexdigest()
    target = phase6_tree / relative
    source = target.read_bytes()
    assert source.count(anchor) == 1, f"{mutation}: the anchor moved; the break would not apply"
    target.write_bytes(source.replace(anchor, replacement))

    outcome = run(verify_module, name, phase6_tree)

    assert hashlib.sha256(real.read_bytes()).hexdigest() == real_before
    assert_fail(outcome, verify_module)
    assert "criterion raised" not in outcome.message, outcome.message
    assert fragment in outcome.message, (fragment, outcome.message)
    assert_names_tier_3(outcome)


# --------------------------------------------------------------------------- #
# equity_row_never_values_positions_it_does_not_hold — operator ruling 2026-09-17
# --------------------------------------------------------------------------- #
#
# Written and observed FAIL on the code as it stood (the exit tick's row valued the sold
# position and counted none open); the FAIL message is quoted in the build log. The fix
# is B's spec 113 and C's spec 114. Until both land, the real-tree test below is red,
# and deliberately so: it states what the operator ruled must be true.


def test_equity_rows_is_pending_on_a_tree_with_nothing_built(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    outcome = run(verify_module, EQUITY_ROWS, unbuilt_tree)
    assert_pending(outcome, verify_module)
    assert _ABSENT_ENGINE.match(outcome.message), outcome.message
    assert_names_tier_3(outcome)


def test_equity_rows_passes_on_the_real_tree(
    verify_module: ModuleType, real_tree_outcomes: dict[str, Any]
) -> None:
    """Every row of a real round trip either holds a position or values none.

    Red until specs 113 and 114: today the exit tick's row counts no open position and
    still carries the sold position's value.
    """
    outcome = real_tree_outcomes[EQUITY_ROWS]
    assert outcome.result is verify_module.Result.PASS, outcome
    assert "carry a positions_value of zero whenever they count no open position" in outcome.message
    assert_names_tier_3(outcome)


# --------------------------------------------------------------------------- #
# What the criteria looked at, not only what they said — sweep arm V12
# --------------------------------------------------------------------------- #

#: A training-only break: every barrier touch is labelled `stop`, so the trained predictor
#: never learns a target and calls no BUY. The engines never import `research/`, so only a
#: subject trained from this tree carries it. Anchored without its line ending because
#: `research/labelling.py` is CRLF in the working tree.
LABELLING_ANCHOR = b"label = LABEL_STOP if (hit_stop or ambiguous) else LABEL_TARGET"
LABELLING_ALWAYS_STOP = b"label = LABEL_STOP"


def test_a_tree_whose_training_differs_is_judged_on_its_own_subject(
    verify_module: ModuleType,
    phase6_tree: Path,
    repo_root: Path,
    real_tree_outcomes: dict[str, Any],
) -> None:
    """The trained subject a criterion drives is the one its own tree's training yields.

    The subject is cached by a digest of what training reads, so every copied tree of an
    engine mutation reuses one training run. Sweep arm V12 replaced that digest with a
    constant, and every test stayed green: they checked what the criteria *said*, and a
    criterion driving the wrong subject says the same things. This test checks what the
    criterion *looked at*. The real tree's subject is already cached (the module fixture).
    This tree's training labels every touch `stop`, so its walk-forward has no BUY row to
    fit a skeptic on, and the subject builder refuses the run, naming its latest fold. Only
    a criterion that trained this tree's subject can report that. One handed the cached
    real subject reports PASS.
    """
    assert real_tree_outcomes["adaptive_router_weights_on_fixture"].result is (
        verify_module.Result.PASS
    )
    labelling = phase6_tree / "src" / "acsoe" / "research" / "labelling.py"
    source = labelling.read_bytes()
    assert source.count(LABELLING_ANCHOR) == 1, "the anchor moved; the break would not apply"
    labelling.write_bytes(source.replace(LABELLING_ANCHOR, LABELLING_ALWAYS_STOP))
    real = repo_root / "src" / "acsoe" / "research" / "labelling.py"
    real_before = hashlib.sha256(real.read_bytes()).hexdigest()

    copy_key = verify_module._fill_subject_key(verify_module.VerifyContext(root=phase6_tree))
    real_key = verify_module._fill_subject_key(verify_module.VerifyContext(root=repo_root))
    outcome = run(verify_module, "adaptive_router_weights_on_fixture", phase6_tree)

    assert hashlib.sha256(real.read_bytes()).hexdigest() == real_before
    assert copy_key != real_key
    assert_fail(outcome, verify_module)
    assert "criterion raised" not in outcome.message, outcome.message
    assert "fitted no skeptic.txt" in outcome.message, outcome.message


# --------------------------------------------------------------------------- #
# recorded_book_agrees_with_recorded_pair_decimals — spec 118
# --------------------------------------------------------------------------- #
#
# The subject is two committed fixtures and nothing else: no engine, no chain, no
# `acsoe` import at all. So every break below is made in a **copy of the fixtures** and
# the real pair is hashed on both sides, the same discipline the engine mutations above
# follow, and the tree is built from the two files rather than from `phase6_tree` —
# copying the package to judge two JSON files would hide which inputs the criterion
# actually reads.

#: `tests/fixtures/book_sample.jsonl` and the recorded `AssetPairs`, by path segment.
BOOK_REL = ("tests", "fixtures", "book_sample.jsonl")
RULES_REL = ("tests", "fixtures", "kraken", "asset_pairs.json")


@pytest.fixture
def fixtures_tree(tmp_path: Path, repo_root: Path) -> Path:
    """A tree carrying the two committed fixtures and nothing else.

    That is the whole input surface of this criterion, and building the tree this way is
    itself an assertion: a criterion that reached for an engine, for `data/raw/`, or for
    the invented ADA/USD rule two thousand lines up in `verify.py` could not report PASS
    here.
    """
    tree = tmp_path / "fixtures-only"
    (tree / "tests" / "fixtures" / "kraken").mkdir(parents=True)
    for relative in (BOOK_REL, RULES_REL):
        shutil.copyfile(repo_root.joinpath(*relative), tree.joinpath(*relative))
    return tree


def test_fixtures_agree_is_pending_before_either_fixture_is_deposited(
    verify_module: ModuleType, unbuilt_tree: Path, tmp_path: Path, repo_root: Path
) -> None:
    """Two absences, two PENDINGs, and each names the file that is missing.

    A criterion whose subject is a committed file has no engine to wait for, so its
    PENDING is the deposit and not a schedule of somebody else's work. The second half
    matters more than it looks: with only the book present the criterion has prices and
    no declaration, which is the exact shape of the ADA/USD case it is required to report
    rather than guess — at whole-fixture scale, where guessing would be a PASS over
    nothing.
    """
    outcome = run(verify_module, FIXTURES_AGREE, unbuilt_tree)
    assert_pending(outcome, verify_module)
    assert "book_sample.jsonl has not been deposited yet" in outcome.message, outcome.message

    half = tmp_path / "book-only"
    (half / "tests" / "fixtures").mkdir(parents=True)
    shutil.copyfile(repo_root.joinpath(*BOOK_REL), half.joinpath(*BOOK_REL))
    outcome = run(verify_module, FIXTURES_AGREE, half)
    assert_pending(outcome, verify_module)
    assert "asset_pairs.json has not been deposited yet" in outcome.message, outcome.message


def test_a_deposited_but_empty_declaration_fails_rather_than_pending(
    verify_module: ModuleType, fixtures_tree: Path
) -> None:
    """Absent is a schedule fact; empty is a broken deposit. The same distinction
    `_phase6_fixture` draws for the book, drawn for the file beside it."""
    fixtures_tree.joinpath(*RULES_REL).write_bytes(b"")
    outcome = run(verify_module, FIXTURES_AGREE, fixtures_tree)
    assert_fail(outcome, verify_module)
    assert "asset_pairs.json is empty" in outcome.message, outcome.message


def test_the_real_fixtures_agree_and_the_message_states_its_coverage(
    verify_module: ModuleType, repo_root: Path
) -> None:
    """The PASS, and the four things the operator required it to say.

    The counts are asserted as text because the coverage is the point: a reader must take
    it from the message rather than infer it from the PASS. One pair compared of five, and
    the four that could not be are named — ADA/USD because the recorded `AssetPairs` has
    no entry for it, the other three because the book sample carries no frames for them.

    `1dp` and `pair_decimals 1` are both pinned: a criterion that stopped measuring and
    only counted would still report the coverage correctly.
    """
    outcome = run(verify_module, FIXTURES_AGREE, repo_root)
    assert_pass(outcome, verify_module)
    message = outcome.message
    assert "criterion raised" not in message, message
    assert "BTC/USD 783 recorded prices, the widest at 1dp" in message, message
    assert "recorded pair_decimals 1" in message, message
    assert "Coverage: 1 compared of the 5 pairs" in message, message
    assert "4 not compared" in message, message
    for pair in ("ADA/USD", "ETH/BTC", "ETH/USD", "SOL/USD"):
        assert pair in message, (pair, message)
    assert "not declared in asset_pairs.json" in message, message
    assert "not recorded in book_sample.jsonl" in message, message
    # Named from the fixture's own header, never written into verify.py.
    assert "kraken_v2__msi__2026-09-16.jsonl" in message, message


#: `(label, fixture, anchor, replacement, expected result, fragment)`.
#:
#: The last arm is the **control**, and it is why the other three are worth anything: a
#: trailing zero is the same point on a 1-decimal grid, so a criterion counting the digits
#: as written rather than the value would go red on it. It is a checked negative, not a
#: survivor — nothing can kill it, because there is nothing there to kill.
FIXTURE_MUTATIONS: dict[str, tuple[tuple[str, ...], bytes, bytes, str, str]] = {
    "a_recorded_price_off_the_declared_grid": (
        BOOK_REL,
        b'{"price":75732.4,"qty":0.91087196}',
        b'{"price":75732.45,"qty":0.91087196}',
        "FAIL",
        "off that grid: 1 of 783 recorded prices - 1 at 2dp (for instance 75732.45)",
    ),
    "the_declaration_narrowed_and_the_book_untouched": (
        RULES_REL,
        b'"pair_decimals": 1',
        b'"pair_decimals": 0',
        "FAIL",
        "BTC/USD declares pair_decimals 0; off that grid: 733 of 783",
    ),
    "the_only_shared_pair_renamed_out_of_the_declaration": (
        RULES_REL,
        b'    "BTC/USD": {\n      "base": "BTC",',
        b'    "BTC/USDX": {\n      "base": "BTC",',
        "FAIL",
        "no pair is carried by both fixtures, so this criterion compared nothing",
    ),
    "the_shared_pair_declared_with_no_pair_decimals_field": (
        RULES_REL,
        b'      "lot_decimals": 8,\n      "pair_decimals": 1\n',
        b'      "lot_decimals": 8\n',
        "FAIL",
        "BTC/USD (783 recorded prices, its asset_pairs.json entry carries no pair_decimals)",
    ),
    "CONTROL_a_trailing_zero_is_the_same_grid_point": (
        BOOK_REL,
        b'{"price":75733.6,"qty":0.52596}',
        b'{"price":75733.60,"qty":0.52596}',
        "PASS",
        "the widest at 1dp",
    ),
}


@pytest.mark.parametrize("mutation", sorted(FIXTURE_MUTATIONS))
def test_the_fixture_agreement_is_observed_to_fail_and_to_hold(
    verify_module: ModuleType, fixtures_tree: Path, repo_root: Path, mutation: str
) -> None:
    """Break the agreement in the copy, and watch the criterion say which pair and which
    figure. The control is broken too, in a way that changes no grid point, and must not
    move the verdict.

    Both real fixtures are hashed before and after: this file runs inside
    `toolchain_green` and other pytest runs share the checkout, and invariant 11 makes a
    recording append-only, so a mutation that escaped into `tests/fixtures/` would be a
    defect of a different order from a red test.
    """
    relative, anchor, replacement, expected, fragment = FIXTURE_MUTATIONS[mutation]
    real = [repo_root.joinpath(*rel) for rel in (BOOK_REL, RULES_REL)]
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in real]
    target = fixtures_tree.joinpath(*relative)
    source = target.read_bytes()
    assert source.count(anchor) == 1, f"{mutation}: the anchor moved; the break would not apply"
    target.write_bytes(source.replace(anchor, replacement))

    outcome = run(verify_module, FIXTURES_AGREE, fixtures_tree)

    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in real] == before
    assert outcome.result is getattr(verify_module.Result, expected), outcome
    assert "criterion raised" not in outcome.message, outcome.message
    assert fragment in outcome.message, (fragment, outcome.message)


def test_a_price_that_is_not_a_number_is_a_fail_and_never_a_crash(
    verify_module: ModuleType, fixtures_tree: Path, repo_root: Path
) -> None:
    """A malformed recording is the criterion's verdict, not a stack trace.

    `criterion raised` names the file and the exception and judges nothing, which is the
    least useful thing a gate can print about a fixture it is the only reader of.
    """
    real = repo_root.joinpath(*BOOK_REL)
    before = hashlib.sha256(real.read_bytes()).hexdigest()
    target = fixtures_tree.joinpath(*BOOK_REL)
    source = target.read_bytes()
    anchor = b'{"price":75732.4,"qty":0.91087196}'
    assert source.count(anchor) == 1, "the anchor moved; the break would not apply"
    target.write_bytes(source.replace(anchor, b'{"price":"75732.4","qty":0.91087196}'))

    outcome = run(verify_module, FIXTURES_AGREE, fixtures_tree)

    assert hashlib.sha256(real.read_bytes()).hexdigest() == before
    assert_fail(outcome, verify_module)
    assert "criterion raised" not in outcome.message, outcome.message
    assert "is not a finite decimal number" in outcome.message, outcome.message


def test_the_criterion_reads_the_two_fixtures_and_nothing_else(
    verify_module: ModuleType, fixtures_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every path it opens, recorded, and compared with the two it is allowed.

    The fresh-clone rule is checked over the whole Phase 6 section by the AST sweep
    earlier in this file, which reads the source. This reads the run: `Path.open` and
    `Path.read_text` are wrapped for the duration, so a criterion that grew a third input
    — a `data/raw/` archive, a config file, the invented ADA/USD rule read from disk —
    fails here naming the path, wherever in the call graph it was opened.
    """
    opened: list[Path] = []
    real_open = Path.open
    real_read_text = Path.read_text

    def spy_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        opened.append(self)
        return real_open(self, *args, **kwargs)

    def spy_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        opened.append(self)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", spy_open)
    monkeypatch.setattr(Path, "read_text", spy_read_text)
    outcome = run(verify_module, FIXTURES_AGREE, fixtures_tree)
    monkeypatch.undo()

    assert_pass(outcome, verify_module)
    allowed = {fixtures_tree.joinpath(*rel).resolve() for rel in (BOOK_REL, RULES_REL)}
    assert opened, "nothing was opened at all, so this sweep would pass vacuously"
    assert {path.resolve() for path in opened} == allowed, sorted(str(p) for p in opened)


def test_a_compared_pair_whose_frames_carry_no_price_is_a_fail(
    verify_module: ModuleType, fixtures_tree: Path, repo_root: Path
) -> None:
    """A pair recorded with an empty book is a fixture fault, not zero breaches.

    The other arms all break an agreement. This one removes the *evidence*: SOL/USD is
    declared at 3 decimals and carries no frames, so appending one frame whose book is
    empty puts it in both fixtures with nothing to measure. A criterion that reported
    "no price was off the grid" there would be saying its loudest thing about a pair it
    never looked at, which is the vacuous pass per pair rather than over the whole file.

    Appended rather than substituted, because no anchor in the committed book produces
    this state: every recorded frame carries levels, which is what makes the branch
    otherwise unexecuted.
    """
    real = repo_root.joinpath(*BOOK_REL)
    before = hashlib.sha256(real.read_bytes()).hexdigest()
    target = fixtures_tree.joinpath(*BOOK_REL)
    source = target.read_bytes()
    empty_frame = (
        b'{"v":1,"kind":"tick","pair":"SOL/USD","channel":"book",'
        b'"ts_exchange":"2026-09-16T00:17:36.000000Z",'
        b'"ts_recv":"2026-09-16T00:17:36.000000Z",'
        b'"payload":{"channel":"book","type":"snapshot",'
        b'"data":[{"symbol":"SOL/USD","bids":[],"asks":[]}]}}\n'
    )
    target.write_bytes(source + empty_frame)

    outcome = run(verify_module, FIXTURES_AGREE, fixtures_tree)

    assert hashlib.sha256(real.read_bytes()).hexdigest() == before
    assert_fail(outcome, verify_module)
    assert "criterion raised" not in outcome.message, outcome.message
    assert "SOL/USD is in book_sample.jsonl and carries no price at all" in outcome.message, (
        outcome.message
    )
    # The pair that does have both halves is still measured and still reported.
    assert "Coverage: 2 compared of the 5 pairs" in outcome.message, outcome.message
