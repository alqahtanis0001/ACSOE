"""The nine Phase 6 criteria. Spec 100.

Three observations per criterion, and the order they arrive in is the phase's order:

* **PENDING** against a tree where the subject does not exist. A criterion that cannot
  reach that state makes a phase impossible to start, which is the whole reason these
  are written in wave 2 of a phase whose engines land in wave 3.
* **PASS** against the subject as it actually is.
* **FAIL**, deliberately induced against a *plausible* wrong implementation.

**Where this file is honestly incomplete, stated rather than implied.** On the tree it
was written against, **every one of the nine is PENDING**: engines 16, 18 and 22 are B's
and unbuilt, engines 9 and 14 are `C-models`'s and unbuilt, and neither committed fixture
has been cut. So every criterion here carries the PENDING observation plus an assertion
that its PENDING **names the engine or fixture that owes it and the spec that owns it** —
a PENDING line that does not say what to build makes the owning agent come and read
`scripts/verify.py`. Their PASS and FAIL halves are observed as those subjects land,
which is the sequencing every phase since Phase 1 has used.

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

import pytest

from tests.verify.conftest import fabricate_package
from tests.verify.test_phase2_criteria import (
    assert_fail,
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

#: Spec 105's criterion, registered after spec 100's nine. Kept out of `PHASE6_CRITERIA`
#: on purpose: those nine are PENDING on the real tree and the tests parametrised over
#: them say so, while this one runs to a verdict today. Its own tests are at the end of
#: this file.
EQUITY_ACROSS_FILL = "paper_equity_continuous_across_fill"

#: The seven that drive a trade through the gates and must therefore name their fee
#: regime in their own message. Ruling 8 of the Phase 6 task list.
TRADE_DRIVING = (
    "paper_trade_round_trip_target",
    "paper_trade_round_trip_stop",
    "paper_trade_round_trip_timeout",
    "unfilled_entry_cancels_without_chasing",
    "triggered_stop_holds_on_data_guard_block",
    "escalation_completes_during_outage",
    "console_shows_position_live",
)

#: The two that do not, and deliberately name no tier. Engine 9 walks a recorded book
#: and engine 14 weighs recorded leaderboard rows; the fee schedule enters neither, and
#: a criterion that claimed a fee regime it had not applied would be the same wrong
#: claim as one that omitted a regime it had.
NOT_TRADE_DRIVING = (
    "order_book_slippage_on_recorded_book",
    "adaptive_router_weights_on_fixture",
)

#: Each awaited subject, and the string its PENDING line must carry. The engine number
#: and the owning spec, because the reader of a PENDING is usually the agent who has to
#: act on it.
#:
#: **This mapping moves as the phase is built, and has moved twice on its first day.**
#: It named engine 16 `decision` for five of the nine when it was written; B landed
#: engine 16 that afternoon and the entries moved to engine 18 `execution`; B landed
#: engine 18 an hour later and they moved to engine 22 `exit`. Each move was a red test
#: and a deliberate edit, which is the intended behaviour and not friction: without it a
#: criterion can keep reporting PENDING for a reason that stopped being true, and a gate
#: cannot tell that state apart from progress.
#:
#: `unfilled_entry_cancels_without_chasing` has run out of other people's work to wait
#: for — engines 16, 18 and 21 and the paper broker all exist — so it now names **C** and
#: spec 100. That is the entry to watch: it is the one this session owes.
AWAITED: dict[str, tuple[str, ...]] = {
    "paper_trade_round_trip_target": ("engine 22 `exit`", "spec 93"),
    "paper_trade_round_trip_stop": ("engine 22 `exit`", "spec 93"),
    "paper_trade_round_trip_timeout": ("engine 22 `exit`", "spec 93"),
    "unfilled_entry_cancels_without_chasing": ("C, spec 100", "unfilled-entry driver"),
    "triggered_stop_holds_on_data_guard_block": ("engine 22 `exit`", "spec 93"),
    "escalation_completes_during_outage": ("engine 22 `exit`", "spec 93"),
    "console_shows_position_live": ("engine 22 `exit`", "spec 93"),
    "order_book_slippage_on_recorded_book": ("engine 9 `order_book`", "spec 96"),
    "adaptive_router_weights_on_fixture": ("engine 14 `adaptive_router`", "spec 97"),
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


@pytest.mark.parametrize("name", PHASE6_CRITERIA)
def test_pending_on_the_real_tree_names_the_subject_and_the_spec(
    verify_module: ModuleType, repo_root: Path, name: str
) -> None:
    """The PENDING that the team actually reads, and what it must contain.

    This runs against the **real repository**, which is the state the gate reports on
    today: engines 9, 14, 16, 18 and 22 are unbuilt and both fixtures are uncut. A
    PENDING that said only "not done" would make the owning agent come and read
    `scripts/verify.py` to find out what to build, so each one names the engine by
    number and the spec that owes it.

    **This test is expected to change as subjects land**, and that is the point of
    `AWAITED`: when B lands engine 16 the first four move on to naming engine 18, this
    goes red, and the entry is updated deliberately rather than the criterion quietly
    reporting PENDING for a reason that stopped being true.
    """
    outcome = run(verify_module, name, repo_root)
    assert_pending(outcome, verify_module)
    for fragment in AWAITED[name]:
        assert fragment in outcome.message, (fragment, outcome.message)


@pytest.mark.parametrize("name", TRADE_DRIVING)
def test_every_trade_driving_criterion_names_fee_tier_3_in_its_own_message(
    verify_module: ModuleType, repo_root: Path, name: str
) -> None:
    """Ruling 8, checked on the text the operator actually sees.

    At tier 1 the cost gate is unreachable by construction — the bar is 2.5x friction,
    tier-1 reference friction is about 1.25% round trip, and 3.125% is above the 3.0%
    target barrier — so *nothing* clears and a verdict from that regime says nothing
    about the engines. A criterion that did not name its regime would let a reader take
    a no-trade result for a tested one.

    Asserted on the PENDING as well as on the eventual PASS and FAIL, deliberately: the
    line is there to tell B which regime they are being built against, and it is most
    useful before the engine exists.
    """
    outcome = run(verify_module, name, repo_root)
    assert "tier 3" in outcome.message, outcome.message
    assert "no-trade regime" in outcome.message, outcome.message


@pytest.mark.parametrize("name", NOT_TRADE_DRIVING)
def test_the_two_criteria_that_drive_no_trade_claim_no_fee_regime(
    verify_module: ModuleType, repo_root: Path, name: str
) -> None:
    """The other half of ruling 8, and it is not decorative.

    Engine 9 walks a recorded book and engine 14 weighs recorded rows. Neither touches
    the fee schedule, so a message claiming "at fee tier 3" would be describing a
    condition the criterion never applied — the same class of untrue statement as
    omitting a regime that *was* applied, pointed the other way.
    """
    outcome = run(verify_module, name, repo_root)
    assert "tier 3" not in outcome.message, outcome.message


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


def test_the_tier_sentence_is_pending_rather_than_wrong_when_the_harness_is_absent(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """A criterion that cannot read the named tiers must not invent one.

    The sentence lives in `tests/harness/fake_kraken.py` beside the profile it
    describes, so the tier a criterion reports and the tier it applied come from one
    file. On a tree with no harness the right answer is PENDING — never a message that
    claims a regime nothing set up.
    """
    sentence, problem = verify_module._tier_sentence(3)
    del sentence, bare_tree  # the real harness is importable here; the branch below is not
    assert problem is None, "the harness is present in this repository, so this is the PASS side"
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
    verify_module: ModuleType, repo_root: Path
) -> None:
    """The real chain places, fills and records an entry, and equity moves by the fee.

    Engine 21 stores a position opened this tick marked at its fill price (spec 106), so
    the mark-to-bid part of the bound is zero on the fill tick and the tolerance is the
    maker fee alone.
    The equity row therefore moves by exactly minus the fee, which is asserted, so a
    criterion whose bound had drifted wide would not pass this test by being loose.
    """
    outcome = run(verify_module, EQUITY_ACROSS_FILL, repo_root)
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
    """"The tick before" means the entry tick, not the last row that happens to exist.

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
