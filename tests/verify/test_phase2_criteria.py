"""The six Phase 2 criteria, plus the negative test `commands_round_trip` never had.

Spec 33 steps 5 and 6. Same two-sided proof specs 01 and 16 established, for the
same reason: these criteria are written *before* the engines they judge, so both
halves have to be provable against something other than those engines.

* **PENDING** against a tree where the subject does not exist. A criterion that
  cannot reach that state makes a phase impossible to start.
* **PASS** against a fabricated minimal subject. A criterion asserted only in the
  PENDING direction can be one that never manages to check anything.
* **FAIL** wherever the criterion has a real failure mode - and every one of these
  six has one worth naming: a recording report with a hole nobody accounted for, a
  candle builder outside the pair's own tick size, a guard that passes stale data,
  a loader that counts missing bars instead of gaps, a console that renders the
  seed and calls it live, a band reading `Idle` over a running daemon.

The last section is not about a criterion of mine. `commands_round_trip` was
written and registered by the lead and passes, and it had no negative test. A
criterion nobody has seen fail is a comment, and this one exists to catch a defect
that shipped: a `StoreClient` with no command reader, which the orchestrator
reaches for through `getattr`, does not find, and skips with one debug line. So the
last test builds exactly that - the real `core/` orchestrator over a store missing
the reader - and asserts the criterion goes red.
"""

from __future__ import annotations

import inspect
import json
import shutil
import sqlite3
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.verify.conftest import fabricate_package

PHASE2_CRITERIA = (
    "recording_span_continuous",
    "candles_match_independent_reduction_of_recorded_trades",
    "data_guard_blocks_bad_data",
    "historical_loader_reports_gaps",
    "console_shows_live_rows",
    "console_reads_persisted_mode",
)

_DOCSTRING = __import__("re").compile(r"(\"\"\"|''')(?:.|\n)*?\1")
_COMMENT = __import__("re").compile(r"(?m)^\s*#.*$")

HOUR_US = 3_600_000_000
MINUTE_US = 60 * 1_000_000
DAY_US = 24 * HOUR_US
BASE_US = 1_800_000_000_000_000


def shadow_real_package(root: Path) -> Path:
    """Write an **empty** `src/acsoe/` so the editable install stops leaking in.

    The install is a plain `.pth` adding `src` to `sys.path`, so `root_import_path`
    only shadows the real package when the fabricated tree has one to shadow with.
    `tree_with_harness` builds on `bare_tree` and carries no `src/` at all, which is
    fine for a criterion whose subject is a file on disk and wrong for one that
    reaches the package by import: `candles_match_independent_reduction_of_recorded_trades` asked for
    `build_candles`, found **A's real one** in the developer's own checkout, handed
    it fabricated trades and got `ValueError: a trade must carry 'qty'` - a FAIL,
    where the test was asserting PENDING. The test was correct on the day it was
    written and became wrong the moment A landed engine 3, which is exactly the
    failure `unbuilt_tree` exists to prevent one directory over.
    """
    package = root / "src" / "acsoe"
    package.mkdir(parents=True, exist_ok=True)
    init = package / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")
    return root


def use_real_core(root: Path) -> Path:
    """Copy the **real** `src/acsoe/core/` into a fabricated tree.

    Never a fabricated `acsoe.core.contracts`, and this is the lesson rather than a
    convenience. `_guard_context` built its `EngineContext` with `cycle_id=1` - not
    a field; a tick is `(run_id, cycle_id)` and the cycle half lives in `state` -
    and omitted the required `mode`. Both halves of the two-sided proof passed
    anyway, because the fabricated contract this file wrote **agreed with the
    mistake**: it declared `cycle_id` and no `mode`. The criterion's body ran and
    proved nothing, and the defect would have surfaced only when A landed engine 4
    and the gate went red for everyone.

    `core/` imports nothing from the rest of the package (architecture invariant 0),
    so copying that one directory is cheap and gives the criterion the same contract
    the engines are compiled against. Fabricate a subject the criterion judges;
    never fabricate a contract that already exists and that the criterion is
    supposed to be held to.
    """
    package = root / "src" / "acsoe"
    package.mkdir(parents=True, exist_ok=True)
    init = package / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")
    destination = package / "core"
    if not destination.exists():
        shutil.copytree(
            Path(__file__).resolve().parents[2] / "src" / "acsoe" / "core",
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    return root


def run(verify_module: ModuleType, check: str, root: Path) -> Any:
    """One criterion against `root`, through the runner's exception guard."""
    return verify_module.run_criterion(
        verify_module.Criterion(check, getattr(verify_module, "check_" + check)),
        verify_module.VerifyContext(root=root),
    )


def assert_pending(outcome: Any, verify_module: ModuleType) -> None:
    assert outcome.result is verify_module.Result.PENDING, outcome


def assert_pass(outcome: Any, verify_module: ModuleType) -> None:
    assert outcome.result is verify_module.Result.PASS, outcome


def assert_fail(outcome: Any, verify_module: ModuleType) -> None:
    assert outcome.result is verify_module.Result.FAIL, outcome


# --------------------------------------------------------------------------- #
# Registration and the two standing rules
# --------------------------------------------------------------------------- #


def test_all_six_criteria_are_registered_for_phase_2(verify_module: ModuleType) -> None:
    """The six of spec 33, after the lead's `commands_round_trip`.

    Order matters as well as membership: the report is read top to bottom and
    `criteria_for` returns registration order.
    """
    to_run, _ = verify_module.criteria_for(2, False)
    names = [c.name for c in to_run]
    assert names == [
        "docs_vocabulary",
        "toolchain_green",
        "commands_round_trip",
        *PHASE2_CRITERIA,
    ]


def test_no_phase_2_criterion_touches_a_gitignored_directory(verify_module: ModuleType) -> None:
    """`data/`, `logs/` and `models/` are gitignored.

    A criterion reading one of them passes only on the machine that produced it,
    which `ai-workflow-rules.md` calls a broken criterion. Asserted on the source,
    because the defect is a path literal and a path literal is what a source scan
    catches. Docstrings and comments are stripped first, so a criterion may still
    explain *why* it does not read `data/raw/`.
    """
    helpers = (
        "_fabricate_archive",
        "_pair_tick_sizes",
        "_candle_builder",
        "_run_ids_in_store",
        "_registered_phase_2_engines",
        "_orchestrator_and_chains",
    )
    forbidden = ('"data"', "'data'", "data/db", "data/raw", "logs/", "models/")
    for name in [*("check_" + c for c in PHASE2_CRITERIA), *helpers]:
        source = inspect.getsource(getattr(verify_module, name))
        code = _COMMENT.sub("", _DOCSTRING.sub("", source))
        for token in forbidden:
            assert token not in code, f"{name} references {token}"


def test_no_phase_2_criterion_hardcodes_an_exchange_value(verify_module: ModuleType) -> None:
    """Rule 2 of `trading-invariants.md`: a remembered tick size is a stale one.

    `candles_match_independent_reduction_of_recorded_trades` compares within one `tick_size` **as `AssetPairs`
    reports it**, so the number has to be fetched. The volume tolerance is
    different in kind - 0.1% is the criterion's own statement of how close is close
    enough, not a value the exchange publishes - so it is named as a constant and
    deliberately not caught here.
    """
    source = inspect.getsource(verify_module.check_candles_match_independent_reduction_of_recorded_trades)
    code = _COMMENT.sub("", _DOCSTRING.sub("", source))
    for pair_rule in ("tick_size=", "0.1\"", "0.01\"", "ordermin"):
        assert pair_rule not in code
    assert "_pair_tick_sizes" in code


# --------------------------------------------------------------------------- #
# recording_span_continuous
# --------------------------------------------------------------------------- #


def write_report(root: Path, payload: Any) -> None:
    fixtures = root / "tests" / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / "recording_report.json").write_text(json.dumps(payload), encoding="utf-8")


def tiled_report(
    *,
    gap_cause: str | None = "websocket reconnect",
    gap_us: int = 6 * MINUTE_US,
) -> dict[str, Any]:
    """25 hours, tiling the span exactly, broken once by a short reconnect.

    `recorded_fraction` is **computed from the intervals below**, never written as a
    literal. A hand-written number could agree with a report it does not describe, and
    the criterion would then be checking the fixture's opinion of itself rather than its
    contents.

    The default break is six minutes because the criterion gained a
    `MIN_RECORDED_FRACTION` floor of 0.98 on 2026-09-10. The old default was an hour,
    which is 96% of a 25-hour span and now correctly FAILs - a report describing a
    recorder down for an hour is not evidence that it survives a day. `gap_us` is a
    parameter so the negative test can push it back under the floor deliberately.
    """
    start = BASE_US
    end = start + 25 * HOUR_US
    gap_start = start + 12 * HOUR_US
    gap_end = gap_start + gap_us
    gap: dict[str, Any] = {"start": gap_start, "end": gap_end}
    if gap_cause is not None:
        gap["cause"] = gap_cause
    span_us = end - start
    return {
        "span": {"start": start, "end": end},
        "segments": [
            {"start": start, "end": gap_start},
            {"start": gap_end, "end": end},
        ],
        "gaps": [gap],
        "totals": {
            "recorded_seconds": (span_us - gap_us) / 1_000_000,
            "missing_seconds": gap_us / 1_000_000,
            "recorded_fraction": (span_us - gap_us) / span_us,
        },
    }


def test_recording_span_is_pending_with_no_report(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    outcome = run(verify_module, "recording_span_continuous", bare_tree)
    assert_pending(outcome, verify_module)
    assert "recording_report.json" in outcome.message


def test_recording_span_passes_on_a_tiled_report(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    write_report(bare_tree, tiled_report())
    outcome = run(verify_module, "recording_span_continuous", bare_tree)
    assert_pass(outcome, verify_module)
    assert "1 accounted break" in outcome.message


def test_a_perfectly_tiled_report_still_fails_below_the_recorded_fraction_floor(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """Accounting for a break is not the same as not having one.

    This report is impeccable by every other measure the criterion applies: the span is
    over 24 hours, the segments and the gap tile it exactly, and the break carries a
    stated cause. It describes a recorder that was down for six of twenty-five hours.

    Until 2026-09-10 that PASSed, and the first real archive would have gone into the
    repository on the strength of it at 49% recorded. The fixture exists to prove the
    recorder survives a day; a run that was down for a quarter of it proves the opposite
    while reporting success. The floor is the only assertion that can tell those apart.
    """
    write_report(bare_tree, tiled_report(gap_us=6 * HOUR_US))
    outcome = run(verify_module, "recording_span_continuous", bare_tree)
    assert_fail(outcome, verify_module)
    assert "76.0%" in outcome.message
    assert "98%" in outcome.message


def test_a_report_with_no_recorded_fraction_is_pending_not_a_pass(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """An older digest predates the floor and cannot answer it.

    PENDING rather than FAIL: a report written before `recorded_fraction` existed is not
    a bad recording, it is a report that cannot speak to the question. Treating it as a
    FAIL would blame the recorder for the criterion changing under it.
    """
    report = tiled_report()
    del report["totals"]["recorded_fraction"]
    write_report(bare_tree, report)
    outcome = run(verify_module, "recording_span_continuous", bare_tree)
    assert_pending(outcome, verify_module)
    assert "recorded_fraction" in outcome.message


def test_a_break_nobody_accounted_for_is_a_fail(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    """The whole point of the criterion.

    This report claims **zero** gaps and its two segments leave an hour of the span
    covered by nothing. A check that only counted gap entries would read that as
    perfect uptime, which is exactly how a silent outage is mistaken for a quiet
    market.
    """
    report = tiled_report()
    report["gaps"] = []
    write_report(bare_tree, report)
    outcome = run(verify_module, "recording_span_continuous", bare_tree)
    assert_fail(outcome, verify_module)
    assert "neither a recorded segment nor an accounted break" in outcome.message


def test_a_gap_with_no_cause_is_a_fail(verify_module: ModuleType, bare_tree: Path) -> None:
    write_report(bare_tree, tiled_report(gap_cause=None))
    outcome = run(verify_module, "recording_span_continuous", bare_tree)
    assert_fail(outcome, verify_module)
    assert "cause" in outcome.message


def test_a_span_under_twenty_four_hours_is_a_fail(
    verify_module: ModuleType, bare_tree: Path
) -> None:
    report = tiled_report()
    report["span"]["end"] = report["span"]["start"] + 23 * HOUR_US
    report["segments"][-1]["end"] = report["span"]["end"]
    write_report(bare_tree, report)
    outcome = run(verify_module, "recording_span_continuous", bare_tree)
    assert_fail(outcome, verify_module)
    assert "23.00h" in outcome.message


def test_iso_8601_moments_are_accepted(verify_module: ModuleType, bare_tree: Path) -> None:
    """A digest meant to be read by a person may carry readable instants.

    Microseconds since epoch is the project's unit and stays the primary form; this
    only asserts the criterion does not turn a human-readable report into a FAIL.
    """
    report = tiled_report()
    report["span"] = {"start": "2027-01-14T21:20:00+00:00", "end": "2027-01-15T22:20:00+00:00"}
    report["segments"] = [
        {"start": "2027-01-14T21:20:00+00:00", "end": "2027-01-15T09:20:00+00:00"},
        {"start": "2027-01-15T10:20:00+00:00", "end": "2027-01-15T22:20:00+00:00"},
    ]
    report["gaps"] = [
        {
            "start": "2027-01-15T09:20:00+00:00",
            "end": "2027-01-15T10:20:00+00:00",
            "cause": "process restart",
        }
    ]
    write_report(bare_tree, report)
    assert_pass(run(verify_module, "recording_span_continuous", bare_tree), verify_module)


# --------------------------------------------------------------------------- #
# candles_match_independent_reduction_of_recorded_trades
# --------------------------------------------------------------------------- #

#: Three pairs that are all in spec 127's recorded `AssetPairs` and its name join, so the
#: tolerance can be read from the recording for every one of them.
OHLC_PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD")

#: Spec 127's recording and the REST key each v2 pair joins to in its recorded name map.
RECORDED_ASSET_PAIRS = Path("tests") / "fixtures" / "kraken" / "asset_pairs_recorded_2026-09-19.json"
REST_KEY = {"BTC/USD": "XXBTZUSD", "ETH/USD": "XETHZUSD", "SOL/USD": "SOLUSD"}


def edit_recorded_pairs(root: Path, edit: Any) -> None:
    """Apply `edit` to the recorded `AssetPairs` result in a copied tree, payload kept as text."""
    path = root / RECORDED_ASSET_PAIRS
    captured = json.loads(path.read_text(encoding="utf-8"))
    envelope = json.loads(captured["payload"])
    edit(envelope["result"])
    captured["payload"] = json.dumps(envelope)
    path.write_text(json.dumps(captured), encoding="utf-8")

#: A builder that reproduces the fixture exactly. `_offsets` shifts one field of one
#: bar so a test can walk the criterion over its tolerance without a second module.
CANDLE_BUILDER_MODULE = '''
import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "kraken" / "ohlc.json"
OFFSETS = {offsets!r}
DROP = {drop!r}


def build_candles(trades, *, interval_s):
    """Echo the committed bars for whichever pair these trades belong to."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pair = trades[0]["pair"]
    bars = []
    for bar in payload["pairs"][pair]["ohlc"]:
        if pair in DROP and bar["ts"] == DROP[pair]:
            continue
        built = dict(bar)
        for shift_pair, field, delta in OFFSETS:
            if shift_pair == pair:
                built[field] = str(float(built[field]) + delta)
        bars.append(built)
    return bars
'''


def ohlc_fixture(root: Path) -> dict[str, Any]:
    """Three pairs, four 15-minute bars each, with plausible OHLC and volume."""
    payload: dict[str, Any] = {"interval_s": 900, "pairs": {}}
    for index, pair in enumerate(OHLC_PAIRS):
        base = 100 * (index + 1)
        bars = []
        trades = []
        for bar in range(4):
            ts = BASE_US + bar * 900_000_000
            bars.append(
                {
                    "ts": ts,
                    "open": f"{base + bar}.0",
                    "high": f"{base + bar}.5",
                    "low": f"{base + bar}.0",
                    "close": f"{base + bar}.2",
                    "volume": "12.5",
                }
            )
            trades.append({"pair": pair, "ts": ts, "price": f"{base + bar}.2", "volume": "12.5"})
        payload["pairs"][pair] = {"trades": trades, "ohlc": bars}
    fixtures = root / "tests" / "fixtures" / "kraken"
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / "ohlc.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


def fabricate_builder(
    root: Path,
    *,
    offsets: tuple[tuple[str, str, float], ...] = (),
    drop: dict[str, int] | None = None,
) -> None:
    fabricate_package(
        root,
        {
            "acsoe.engines.market_sensor.candles": CANDLE_BUILDER_MODULE.format(
                offsets=offsets, drop=drop or {}
            )
        },
    )


def test_candles_are_pending_with_no_fixture(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    shadow_real_package(tree_with_harness)
    outcome = run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness)
    assert_pending(outcome, verify_module)
    assert "ohlc.json" in outcome.message


def test_candles_are_pending_with_a_fixture_and_no_builder(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    ohlc_fixture(tree_with_harness)
    shadow_real_package(tree_with_harness)
    outcome = run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness)
    assert_pending(outcome, verify_module)
    assert "build_candles" in outcome.message


def test_candles_pass_when_the_builder_reproduces_the_fixture(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    ohlc_fixture(tree_with_harness)
    fabricate_builder(tree_with_harness)
    outcome = run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness)
    assert_pass(outcome, verify_module)
    assert "tick_size" in outcome.message


def test_the_candle_pass_says_what_it_compared_against_and_what_it_measured(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The message states what is true, not the word `tick_size` alone. Operator ruling S2,
    2026-09-18.

    Until then the PASS said every field was "within one tick_size as AssetPairs reports
    it" and the FAILs said "vs Kraken", while the expected bars were a pure-Python
    reduction of recorded trades and the tick size was invented Phase 0 test data. The
    test above asserted only that `tick_size` appeared, so both false claims passed it for
    six phases. This one pins each claim to the fact it rests on. The fabricated builder
    reproduces the fixture exactly, so the largest difference is `0`, and the message
    must say so rather than imply it.
    """
    ohlc_fixture(tree_with_harness)
    fabricate_builder(tree_with_harness)
    outcome = run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness)
    assert_pass(outcome, verify_module)
    message = outcome.message
    assert "criterion raised" not in message, message
    assert "independent reduction of real recorded Kraken trades" in message, message
    assert "not Kraken's published OHLC" in message, message
    assert "largest OHLC difference 0," in message, message
    assert "Kraken's public AssetPairs as recorded at" in message, message
    assert "asset_pairs_recorded_2026-09-19.json" in message, message
    assert "invented" not in message, message
    assert "--live task" in message, message
    for false_claim in ("as AssetPairs reports it", "Kraken's own OHLC", "vs Kraken"):
        assert false_claim not in message, (false_claim, message)


def test_a_candle_fail_names_the_reference_reduction_and_not_kraken(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The FAIL half of the same ruling: a deviation is from the reference reduction."""
    ohlc_fixture(tree_with_harness)
    fabricate_builder(tree_with_harness, offsets=(("BTC/USD", "close", 0.5),))
    outcome = run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "vs the reference reduction's" in outcome.message, outcome.message
    assert "AssetPairs as recorded at" in outcome.message, outcome.message
    # The tolerance is Kraken's recorded rule since spec 141 step 5; what must never appear
    # is the deviation described as one from Kraken's OHLC, which the reference is not.
    for false_claim in ("vs Kraken", "Kraken's own OHLC", "Kraken's OHLC"):
        assert false_claim not in outcome.message, outcome.message


def test_a_close_outside_the_pairs_own_tick_size_is_a_fail(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """BTC/USD's `tick_size` is 0.1 in spec 127's recorded `AssetPairs`."""
    ohlc_fixture(tree_with_harness)
    fabricate_builder(tree_with_harness, offsets=(("BTC/USD", "close", 0.5),))
    outcome = run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "tick_size" in outcome.message


def test_the_tolerance_really_comes_from_asset_pairs(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The same deviation flips the verdict when the pair rule changes, and only then.

    This is the assertion that separates "reads the tolerance" from "happens to use
    a number equal to it". A 0.5 shift on BTC/USD is outside a 0.1 tick and inside a
    1.0 tick; nothing else about the tree moves. A criterion carrying its own copy
    of the tick size would answer the same both times.
    """
    ohlc_fixture(tree_with_harness)
    fabricate_builder(tree_with_harness, offsets=(("BTC/USD", "close", 0.5),))
    assert_fail(run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness), verify_module)

    edit_recorded_pairs(
        tree_with_harness, lambda result: result[REST_KEY["BTC/USD"]].update(tick_size="1.0")
    )

    assert_pass(run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness), verify_module)


def test_a_dropped_bar_is_a_fail(verify_module: ModuleType, tree_with_harness: Path) -> None:
    """A bar Kraken has and the builder does not is a missing decision bar."""
    ohlc_fixture(tree_with_harness)
    fabricate_builder(tree_with_harness, drop={"ETH/USD": BASE_US + 900_000_000})
    outcome = run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "no ETH/USD candle" in outcome.message


def test_volume_outside_one_tenth_of_a_percent_is_a_fail(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    ohlc_fixture(tree_with_harness)
    fabricate_builder(tree_with_harness, offsets=(("SOL/USD", "volume", 0.5),))
    outcome = run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "outside 0.1%" in outcome.message


def test_a_pair_absent_from_asset_pairs_is_a_fail_not_an_invented_tolerance(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """There is no honest tolerance for a pair the exchange did not describe."""
    ohlc_fixture(tree_with_harness)
    fabricate_builder(tree_with_harness)
    edit_recorded_pairs(tree_with_harness, lambda result: result.pop(REST_KEY["SOL/USD"]))
    outcome = run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "SOL/USD is in ohlc.json and not in Kraken's public AssetPairs" in outcome.message
    assert "will not have one invented" in outcome.message


def test_with_no_recorded_asset_pairs_the_candles_are_pending_and_the_invented_file_unread(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """Prerequisite 9: the invented `asset_pairs.json` is never a fallback for the recording."""
    ohlc_fixture(tree_with_harness)
    fabricate_builder(tree_with_harness)
    (tree_with_harness / RECORDED_ASSET_PAIRS).unlink()
    outcome = run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness)
    assert_pending(outcome, verify_module)
    assert "spec 127" in outcome.message, outcome.message


# --------------------------------------------------------------------------- #
# data_guard_blocks_bad_data
# --------------------------------------------------------------------------- #

GUARD_SCENARIOS_MODULE = '''
BAD_DATA_SCENARIOS = {
    "stale": {"market_sensor": {"age_s": 900}},
    "negative_spread": {"exchange": {"bid": "101", "ask": "100"}},
    "missing_candle": {"market_sensor": {"missing": True}},
    "clean": {"market_sensor": {"age_s": 1, "missing": False},
              "exchange": {"bid": "100", "ask": "101"}},
}
'''

GUARD_ENGINE_MODULE = '''
from dataclasses import dataclass

IS_GATE = {is_gate!r}
BLOCKS = {blocks!r}
REASONS = {reasons!r}
BLOCKS_CLEAN = {blocks_clean!r}


@dataclass
class _Result:
    engine: str
    blocks_trading: bool
    reason: str | None


class DataGuard:
    name = "data_guard"
    number = 4
    is_gate = IS_GATE

    def __init__(self, config=None):
        self._config = config

    def process(self, context, state):
        for key, blocking in BLOCKS.items():
            if state == SCENARIOS[key]:
                return _Result("data_guard", blocking, REASONS[key] if blocking else None)
        if state == SCENARIOS["clean"]:
            return _Result(
                "data_guard", BLOCKS_CLEAN, "clean data refused" if BLOCKS_CLEAN else None
            )
        raise AssertionError("the criterion handed the engine a state it did not fabricate")


from acsoe.engines.data_guard.contracts import BAD_DATA_SCENARIOS as SCENARIOS  # noqa: E402
'''


def fabricate_guard(
    root: Path,
    *,
    is_gate: bool = True,
    blocks: dict[str, bool] | None = None,
    reasons: dict[str, str] | None = None,
    blocks_clean: bool = False,
) -> None:
    use_real_core(root)
    fabricate_package(
        root,
        {
            "acsoe.engines.data_guard.contracts": GUARD_SCENARIOS_MODULE,
            "acsoe.engines.data_guard.engine": GUARD_ENGINE_MODULE.format(
                is_gate=is_gate,
                blocks=blocks
                or {"stale": True, "negative_spread": True, "missing_candle": True},
                reasons=reasons
                or {
                    "stale": "Market data is older than the loop can trust",
                    "negative_spread": "The book is crossed: the bid is above the ask",
                    "missing_candle": "The last decision bar never closed",
                },
                blocks_clean=blocks_clean,
            ),
        },
    )


def test_data_guard_is_pending_when_the_engine_does_not_exist(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    shadow_real_package(tree_with_harness)
    outcome = run(verify_module, "data_guard_blocks_bad_data", tree_with_harness)
    assert_pending(outcome, verify_module)
    assert "BAD_DATA_SCENARIOS" in outcome.message


def test_data_guard_passes_on_a_faithful_gate(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    fabricate_guard(tree_with_harness)
    outcome = run(verify_module, "data_guard_blocks_bad_data", tree_with_harness)
    assert_pass(outcome, verify_module)
    assert "clean data passes" in outcome.message


@pytest.mark.parametrize("condition", ["stale", "negative_spread", "missing_candle"])
def test_a_condition_that_does_not_block_is_a_fail(
    verify_module: ModuleType, tree_with_harness: Path, condition: str
) -> None:
    blocks = {"stale": True, "negative_spread": True, "missing_candle": True}
    blocks[condition] = False
    fabricate_guard(tree_with_harness, blocks=blocks)
    outcome = run(verify_module, "data_guard_blocks_bad_data", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "did not block" in outcome.message


def test_a_gate_that_blocks_clean_data_is_a_fail(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """Three block cases alone would be satisfied by a gate that refuses everything."""
    fabricate_guard(tree_with_harness, blocks_clean=True)
    outcome = run(verify_module, "data_guard_blocks_bad_data", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "blocks everything" in outcome.message


def test_three_conditions_reporting_one_reason_is_a_fail(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """An operator has to be able to tell a stale feed from a crossed book."""
    fabricate_guard(
        tree_with_harness,
        reasons=dict.fromkeys(
            ("stale", "negative_spread", "missing_candle"), "Data is not trusted"
        ),
    )
    outcome = run(verify_module, "data_guard_blocks_bad_data", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "same reason" in outcome.message


def test_a_blocking_reason_that_is_empty_is_a_fail(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    fabricate_guard(
        tree_with_harness,
        reasons={"stale": "   ", "negative_spread": "crossed", "missing_candle": "no bar"},
    )
    outcome = run(verify_module, "data_guard_blocks_bad_data", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "no reason for the operator" in outcome.message


def test_a_data_guard_declaring_it_is_not_a_gate_is_a_fail(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    fabricate_guard(tree_with_harness, is_gate=False)
    outcome = run(verify_module, "data_guard_blocks_bad_data", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "is_gate" in outcome.message


def test_the_guard_criterion_is_held_to_the_real_engine_context(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The regression, stated as a property rather than as a corrected argument list.

    `_guard_context` passed `cycle_id=1` - not a field - and omitted the required
    `mode`, so it raised `TypeError` and never returned a context. Both halves of
    the two-sided proof passed anyway, because this file had fabricated an
    `acsoe.core.contracts` that **agreed with the mistake**. The criterion's body
    ran and proved nothing.

    So this asserts the shape of the thing the fabricated tree carries: the real
    contract, with `mode`, without `cycle_id`. A future fabrication that quietly
    reintroduces a hand-written `EngineContext` fails here rather than in A's gate.
    """
    fabricate_guard(tree_with_harness)
    contracts = tree_with_harness / "src" / "acsoe" / "core" / "contracts.py"
    assert contracts.is_file(), "the fabricated tree must carry the real core/, not a stand-in"
    source = contracts.read_text(encoding="utf-8")
    assert "class EngineContext" in source
    assert "    mode: Mode" in source
    assert "    cycle_id" not in source

    assert_pass(run(verify_module, "data_guard_blocks_bad_data", tree_with_harness), verify_module)


#: A scenario module whose `clean` and `missing_candle` share **one** nested region.
#:
#: That is not a contrived shape. The scenarios differ by one flag each, so a
#: natural fixture builds them from a common base - and the moment two of them name
#: the same dict object, a criterion handing that object to an engine is handing over
#: the fixture for every scenario after it.
SHARED_REGION_SCENARIOS_MODULE = '''
import copy

_MARKET = {"age_s": 1, "missing": False}

BAD_DATA_SCENARIOS = {
    "stale": {"market_sensor": {"age_s": 900, "missing": False}},
    "negative_spread": {"exchange": {"bid": "101", "ask": "100"}},
    # Both name the same object on purpose.
    "missing_candle": {"market_sensor": _MARKET, "hole": True},
    "clean": {"market_sensor": _MARKET, "exchange": {"bid": "100", "ask": "101"}},
}


def bad_data_state(name):
    """A scenario nothing else shares. A's accessor, same contract."""
    return copy.deepcopy(BAD_DATA_SCENARIOS[name])
'''

#: A guard that publishes into the state region it was handed, which every engine is
#: entitled to do - `state` is how engines communicate at all. It blocks the three
#: bad scenarios, and it refuses the clean one if it finds its own mark there, which
#: it only can when the region it was given is the fixture rather than a copy.
LEAKY_GUARD_MODULE = '''
from dataclasses import dataclass

MARK = "_written_by_a_previous_scenario"


@dataclass
class _Result:
    engine: str
    blocks_trading: bool
    reason: str | None


class DataGuard:
    name = "data_guard"
    number = 4
    is_gate = True

    def __init__(self, config=None):
        self._config = config

    def process(self, context, state):
        market = state.get("market_sensor")
        seen = isinstance(market, dict) and market.get(MARK)
        if isinstance(market, dict):
            market[MARK] = True
        if isinstance(market, dict) and market.get("age_s", 0) > 60:
            return _Result("data_guard", True, "Market data is older than the guard allows")
        book = state.get("exchange")
        if isinstance(book, dict) and book.get("bid", "") > book.get("ask", ""):
            return _Result("data_guard", True, "The order book is crossed")
        if state.get("hole"):
            return _Result("data_guard", True, "A decision bar has no candle")
        if seen:
            # The clean scenario arrived carrying a mark this engine wrote while
            # judging `missing_candle`, so the two are the same object.
            return _Result("data_guard", True, "clean data carried a leaked mark")
        return _Result("data_guard", False, None)
'''


def fabricate_leaky_guard(root: Path) -> None:
    use_real_core(root)
    fabricate_package(
        root,
        {
            "acsoe.engines.data_guard.contracts": SHARED_REGION_SCENARIOS_MODULE,
            "acsoe.engines.data_guard.engine": LEAKY_GUARD_MODULE,
        },
    )


def test_the_criterion_hands_the_engine_a_copy_not_the_shared_fixture(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """`BAD_DATA_SCENARIOS` is a mapping of mappings, and `dict(...)` is a shallow copy.

    The outer dict is copied; every nested region stays the *same object* as the
    module-level fixture. A hit this on his own side, where a test set a nested key
    and quietly changed the fixture for every test after it, with the failure
    surfacing somewhere unrelated. Engines publish into `state` by design, so
    "nothing mutates it" is a property of today's engine 4 rather than of the
    contract.

    **The leak is within one criterion run, not across runs**, and that is worth
    stating because I first wrote this test the other way and it passed against a
    deliberately shallow copy. `root_import_path` drops and re-imports every `acsoe`
    module for each criterion, so a module-level fixture is rebuilt from source
    every time and nothing a criterion writes into one can reach the next. What it
    *can* reach is the next scenario in the same run, which is what this fabricates:
    `clean` and `missing_candle` naming one region, and a guard that writes into it.
    """
    fabricate_leaky_guard(tree_with_harness)
    assert_pass(run(verify_module, "data_guard_blocks_bad_data", tree_with_harness), verify_module)


def test_a_shallow_copy_really_would_have_leaked(
    verify_module: ModuleType, tree_with_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The test above has to be able to fail, or it proves nothing about the copy.

    Same shape as spec 17's `test_the_write_that_was_refused_really_would_have_worked`:
    a guard that has never been shown to fire is a comment. `_guard_state` is put back
    to the `dict(scenarios[key])` it used to be, and the clean case then arrives
    carrying a mark the engine wrote while judging `missing_candle` - so the criterion
    reports a gate that blocks everything, which is a real verdict about a fixture
    defect and reads as a defect in the engine.
    """
    fabricate_leaky_guard(tree_with_harness)

    def shallow(contracts_mod: Any, scenarios: Any, key: str) -> Any:
        return dict(scenarios[key])

    monkeypatch.setattr(verify_module, "_guard_state", shallow)
    outcome = run(verify_module, "data_guard_blocks_bad_data", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "blocks everything" in outcome.message


def test_the_criterion_prefers_a_s_deep_copy_accessor_when_it_exists(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """`bad_data_state(name)` is A's, and it is used in preference to `copy.deepcopy`.

    One producer of a scenario rather than two. The fallback stays so the criterion
    keeps working against a `contracts.py` that only exposes the mapping, but where
    the accessor exists it is the accessor that decides what a scenario is.
    """
    fabricate_leaky_guard(tree_with_harness)
    calls: list[str] = []
    module = __import__("types").ModuleType("stub")
    module.bad_data_state = lambda name: calls.append(name) or {"market_sensor": {"age_s": 1}}
    scenarios = {"stale": {}, "clean": {}}
    assert verify_module._guard_state(module, scenarios, "stale") == {"market_sensor": {"age_s": 1}}
    assert calls == ["stale"]


CONTEXT_WITH_A_NEW_FIELD = '''
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EngineContext:
    mode: Any
    run_id: str
    now: Any
    config: Any
    clients: Any
    tick_budget_ms: int
'''


def test_a_context_field_the_criterion_cannot_supply_is_named_not_raised(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The reason `_guard_context` introspects instead of passing a fixed list.

    A corrected argument list is the same defect one edit later: the lead owns
    `core/contracts.py` and may add a required field at any time, and this script
    would then raise `TypeError` from inside a criterion again. The context is
    therefore built from whatever the dataclass says it takes, and a required field
    with no value here is reported **by name** as PENDING.

    This is the one place that deliberately fabricates `acsoe.core.contracts`, and
    it does so because the subject under test is this script's adaptability to a
    contract it does not own - not the data guard.
    """
    fabricate_guard(tree_with_harness)
    fabricate_package(tree_with_harness, {"acsoe.core.contracts": CONTEXT_WITH_A_NEW_FIELD})
    outcome = run(verify_module, "data_guard_blocks_bad_data", tree_with_harness)
    assert_pending(outcome, verify_module)
    assert "tick_budget_ms" in outcome.message


UNSET_KEY_ENGINE = '''
from dataclasses import dataclass

KEY = {key!r}


@dataclass
class _Result:
    engine: str
    blocks_trading: bool
    reason: str | None


class DataGuard:
    name = "data_guard"
    number = 4
    is_gate = True

    def __init__(self, config=None):
        self._config = config

    def process(self, context, state):
        # What `platform/config.py` raises for a threshold nobody has set. An engine
        # that returned a default here instead would be inventing trading behaviour.
        raise KeyError(f"config has no key {{KEY!r}}; the last segment is not present")
'''


def test_an_unset_operator_threshold_is_pending_and_names_the_key(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """A gate whose threshold the operator has not supplied is an unbuilt subject.

    A `KeyError` from a threshold nobody has set is right - an engine silently
    receiving `None` for a threshold is the failure this project refuses. But a
    *configured* data guard does not exist yet, which is what PENDING means, and
    reporting it as FAIL would make the criterion lie about whose problem it is.
    Under the commit-at-every-boundary rule a FAIL also blocks every other agent's
    finished work, which is the practical half of the same argument.

    The key named here is deliberately one `config/default.yaml` does not carry, and
    is **not** `data_guard.max_data_age_s`. It was, until the operator supplied 120 on
    2026-09-09 - at which point this test went red, because it asserted "an unset
    threshold" while being held to whatever the shipped file happened to contain. That
    is the decayed-assertion shape this phase found six times over. The companion test
    below covers the other branch: a key that *is* in the file and still raises is a
    FAIL, because that is an engine asking for something in a shape it did not expect.
    """
    fabricate_guard(tree_with_harness)
    fabricate_package(
        tree_with_harness,
        {"acsoe.engines.data_guard.engine": UNSET_KEY_ENGINE.format(
            key="data_guard.a_threshold_no_config_carries"
        )},
    )
    outcome = run(verify_module, "data_guard_blocks_bad_data", tree_with_harness)
    assert_pending(outcome, verify_module)
    assert "data_guard.a_threshold_no_config_carries" in outcome.message


def test_a_key_that_is_configured_and_still_raises_is_a_failure(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The other side, and the one that keeps the leniency above from being a hole.

    "Unset" is *checked*, never assumed. A `KeyError` naming a key the committed
    config actually carries is not an unconfigured threshold - it is an engine
    asking for something that exists in a shape it did not expect - and that is a
    FAIL. Without this, the PENDING branch would swallow any `KeyError` at all and
    the criterion could never go red for a real defect.
    """
    fabricate_guard(tree_with_harness)
    fabricate_package(
        tree_with_harness,
        {"acsoe.engines.data_guard.engine": UNSET_KEY_ENGINE.format(key="safety.max_drawdown_pct")},
    )
    outcome = run(verify_module, "data_guard_blocks_bad_data", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "criterion raised" in outcome.message


# --------------------------------------------------------------------------- #
# historical_loader_reports_gaps
# --------------------------------------------------------------------------- #

LOADER_MODULE = '''
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ArchiveReport:
    gap_count: int
    row_count: int
    timestamps: tuple
    duration_buckets: dict = field(default_factory=dict)
    largest_gap_bars: int = 0


COUNT_MISSING_BARS = {count_missing_bars!r}
FILL_GAPS = {fill_gaps!r}


def load_archive(path, *, interval_s):
    stamps = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            stamps.append(int(line.split(",")[0]))
    runs = []
    missing = 0
    for previous, current in zip(stamps, stamps[1:]):
        step = (current - previous) // interval_s
        if step > 1:
            runs.append(step - 1)
            missing += step - 1
    emitted = list(stamps)
    if FILL_GAPS:
        emitted = list(range(stamps[0], stamps[-1] + interval_s, interval_s))
    return ArchiveReport(
        gap_count=missing if COUNT_MISSING_BARS else len(runs),
        # Deliberately the *archive's* row count even when the output is filled.
        # A loader that reported the filled count would be caught by the row_count
        # check and the timestamp assertion would never run - and the timestamp
        # assertion is the one spec 30 asks for separately.
        row_count=len(stamps),
        timestamps=tuple(emitted),
        duration_buckets={{"1-3 bars": sum(1 for r in runs if r <= 3)}},
        largest_gap_bars=max(runs) if runs else 0,
    )
'''


def fabricate_loader(
    root: Path, *, count_missing_bars: bool = False, fill_gaps: bool = False
) -> None:
    fabricate_package(
        root,
        {
            "acsoe.research.historical": LOADER_MODULE.format(
                count_missing_bars=count_missing_bars, fill_gaps=fill_gaps
            )
        },
    )


def test_loader_is_pending_when_it_does_not_exist(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    outcome = run(verify_module, "historical_loader_reports_gaps", unbuilt_tree)
    assert_pending(outcome, verify_module)
    assert "load_archive" in outcome.message


def test_loader_passes_when_it_counts_gaps(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    fabricate_loader(unbuilt_tree)
    outcome = run(verify_module, "historical_loader_reports_gaps", unbuilt_tree)
    assert_pass(outcome, verify_module)
    assert "3 gaps" in outcome.message


def test_counting_missing_bars_instead_of_gaps_is_a_fail(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    """Why the fabricated archive's three holes are 1, 2 and 4 bars rather than equal.

    A loader that reports the number of *missing bars* answers 7 where the answer
    is 3. With three holes of the same size the two numbers would only differ by a
    factor, and a loader off by a factor is much easier to write than one off by
    four.
    """
    fabricate_loader(unbuilt_tree, count_missing_bars=True)
    outcome = run(verify_module, "historical_loader_reports_gaps", unbuilt_tree)
    assert_fail(outcome, verify_module)
    assert "reported 7" in outcome.message


def test_a_loader_that_fills_the_holes_is_a_fail(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    """The assertion the gap count cannot make.

    This loader counts its three gaps perfectly and *also* emits a continuous
    series. Spec 30 calls that out as the failure that passes every check which
    only looks at the count, and it is the one that poisons Phase 4's labels: a
    synthesised candle at a price that never traded invents a barrier touch.
    """
    fabricate_loader(unbuilt_tree, fill_gaps=True)
    outcome = run(verify_module, "historical_loader_reports_gaps", unbuilt_tree)
    assert_fail(outcome, verify_module)
    assert "absent from the archive" in outcome.message


# --------------------------------------------------------------------------- #
# The daemon fabrication, shared by the last two criteria
# --------------------------------------------------------------------------- #

DAEMON_SEED_MODULE = '''
import sqlite3
from dataclasses import dataclass
from pathlib import Path

BASE_TS = 1_800_000_000_000_000


@dataclass(frozen=True)
class SeedFixtures:
    db_path: Path
    seed_now: int


def seed_database(db_path, *, seed=0):
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY,
                run_id TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL,
                started_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                system_mode TEXT,
                system_mode_at INTEGER);
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY,
                command TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                claimed_at INTEGER,
                consumed_at INTEGER,
                updated_at INTEGER NOT NULL);
            """
        )
        for index, name in ((1, "seed-a"), (2, "seed-b")):
            conn.execute(
                "INSERT OR REPLACE INTO runs (id, run_id, mode, started_at, updated_at) "
                "VALUES (?, ?, 'paper', ?, ?)",
                (index, name, BASE_TS + index, BASE_TS + index),
            )
        conn.commit()
    finally:
        conn.close()
    return SeedFixtures(db_path=db_path, seed_now=BASE_TS + 2)
'''

DAEMON_STORE_MODULE = '''
import sqlite3
from dataclasses import dataclass

HAS_MODE_ACCESSOR = {has_mode_accessor!r}


@dataclass(frozen=True)
class _Mode:
    run_id: str
    mode: str | None
    at: int | None


class StoreClient:
    def __init__(self, db_path):
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.connection.close()

    def migrate(self):
        """`tests.harness.doubles.migrated_store` calls this before handing it over."""
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY,
                run_id TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL,
                started_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                system_mode TEXT,
                system_mode_at INTEGER);
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY,
                command TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                claimed_at INTEGER,
                consumed_at INTEGER,
                updated_at INTEGER NOT NULL);
            """
        )
        self.connection.commit()
        return []

    def append_command(self, row):
        cursor = self.connection.execute(
            "INSERT INTO commands (command, source, created_at, updated_at) VALUES (?,?,?,?)",
            (row.command, str(row.source), row.created_at, row.updated_at),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def pending_commands(self):
        return [
            dict(r)
            for r in self.connection.execute(
                "SELECT * FROM commands WHERE claimed_at IS NULL ORDER BY id"
            )
        ]

    def claim_command(self, command_id, *, claimed_at, run_id):
        self.connection.execute(
            "UPDATE commands SET claimed_at = ? WHERE id = ?", (claimed_at, command_id)
        )
        self.connection.commit()
        return True

    def write_run(self, run_id, started_at):
        self.connection.execute(
            "INSERT OR IGNORE INTO runs (run_id, mode, started_at, updated_at) "
            "VALUES (?, 'paper', ?, ?)",
            (run_id, started_at, started_at),
        )
        self.connection.commit()

    if HAS_MODE_ACCESSOR:

        def set_system_mode(self, run_id, mode, *, at):
            cursor = self.connection.execute(
                "UPDATE runs SET system_mode = ?, system_mode_at = ?, updated_at = ? "
                "WHERE run_id = ?",
                (mode, at, at, run_id),
            )
            self.connection.commit()
            return cursor.rowcount == 1

        def system_mode(self, run_id):
            row = self.connection.execute(
                "SELECT run_id, system_mode, system_mode_at FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            return _Mode(row["run_id"], row["system_mode"], row["system_mode_at"])
'''

DAEMON_CONTRACTS_MODULE = '''
from dataclasses import dataclass
from enum import StrEnum


class CommandSource(StrEnum):
    CONSOLE = "console"
    SAFETY = "safety"


@dataclass(frozen=True)
class CommandRow:
    command: str
    source: CommandSource
    created_at: int
    updated_at: int
'''

DAEMON_ORCHESTRATOR_MODULE = '''
WRITES_RUN_ROW = {writes_run_row!r}
PERSISTS_MODE = {persists_mode!r}
WRITES_LIVE_ROW = {writes_live_row!r}

_MODES = {{"activate": "running", "freeze": "frozen", "close_all": "frozen"}}


class Orchestrator:
    def __init__(self, *, config, clock, clients, chains):
        self._clients = clients
        self._clock = clock
        self._chains = chains
        self.run_id = "daemon-0001"
        self.system = {{"mode": "idle", "close_intent": False}}
        self._started = False

    def tick(self):
        store = self._clients.store
        stamp = int(self._clock.now().timestamp() * 1_000_000)
        if not self._started:
            self._started = True
            if WRITES_RUN_ROW or WRITES_LIVE_ROW:
                store.write_run(self.run_id, stamp)
        for row in store.pending_commands():
            name = row["command"]
            if name in _MODES:
                self.system["mode"] = _MODES[name]
                store.claim_command(row["id"], claimed_at=stamp, run_id=self.run_id)
                if PERSISTS_MODE and hasattr(store, "set_system_mode"):
                    store.set_system_mode(self.run_id, self.system["mode"], at=stamp)
        for engine in (*self._chains.guard, *self._chains.opportunity, *self._chains.manage):
            engine.process(None, {{}})
        return {{"system": self.system, "guard_blockers": []}}
'''

DAEMON_BOOTSTRAP_MODULE = '''
class _Engine:
    name = "market_sensor"
    number = {number!r}
    is_gate = False

    def process(self, context, state):
        return None


GUARD_CHAIN = (_Engine(),)
OPPORTUNITY_CHAIN = ()
MANAGE_CHAIN = ()
'''

DAEMON_CONSOLE_MODULE = '''
import json
import sqlite3
from pathlib import Path

RENDERS_RUN_ID = {renders_run_id!r}
RENDERS_MODE = {renders_mode!r}

STATE_WORDS = {{"running": "Running", "frozen": "Frozen"}}


class _Reader:
    def __init__(self, db_path):
        self.db_path = Path(db_path)

    def latest(self):
        conn = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM runs ORDER BY started_at DESC, id DESC LIMIT 2"
                )
            ]
        finally:
            conn.close()

    def close(self):
        pass


class _State:
    pass


class _App:
    def __init__(self, config, db_path):
        self.config = config
        self.state = _State()
        self.state.reader = _Reader(db_path)

    async def __call__(self, scope, receive, send):
        rows = self.state.reader.latest()
        current = rows[0] if rows else {{}}
        state_text = "Idle \\u2014 restarted, not trading" if len(rows) > 1 else "Idle"
        mode = current.get("system_mode")
        if RENDERS_MODE and mode in STATE_WORDS:
            state_text = STATE_WORDS[mode]
        payload = {{"state": state_text}}
        if RENDERS_RUN_ID:
            payload["run_id"] = current.get("run_id")
        body = json.dumps(payload, ensure_ascii=False).encode()
        await send(
            {{
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }}
        )
        await send({{"type": "http.response.body", "body": body}})


def create_app(config, *, db_path=None, clock=None):
    return _App(config, db_path)
'''


def fabricate_daemon(
    root: Path,
    *,
    engine_number: int = 3,
    writes_run_row: bool = True,
    writes_live_row: bool = True,
    persists_mode: bool = True,
    has_mode_accessor: bool = True,
    renders_run_id: bool = True,
    renders_mode: bool = True,
) -> None:
    """A whole daemon-plus-console tree: bootstrap, orchestrator, store, seed, console."""
    use_real_core(root)
    fabricate_package(
        root,
        {
            "acsoe.bootstrap": DAEMON_BOOTSTRAP_MODULE.format(number=engine_number),
            "acsoe.core.orchestrator": DAEMON_ORCHESTRATOR_MODULE.format(
                writes_run_row=writes_run_row,
                persists_mode=persists_mode,
                writes_live_row=writes_live_row,
            ),
            "acsoe.clients.store.client": DAEMON_STORE_MODULE.format(
                has_mode_accessor=has_mode_accessor
            ),
            "acsoe.clients.store.contracts": DAEMON_CONTRACTS_MODULE,
            "acsoe.clients.store.seed": DAEMON_SEED_MODULE,
            "acsoe.console.app": DAEMON_CONSOLE_MODULE.format(
                renders_run_id=renders_run_id, renders_mode=renders_mode
            ),
        },
    )


# --------------------------------------------------------------------------- #
# console_shows_live_rows
# --------------------------------------------------------------------------- #


def test_live_rows_is_pending_with_no_phase_2_engine_registered(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    shadow_real_package(tree_with_harness)
    fabricate_daemon(tree_with_harness, engine_number=19)
    outcome = run(verify_module, "console_shows_live_rows", tree_with_harness)
    assert_pending(outcome, verify_module)
    assert "no Phase 2 engine is registered" in outcome.message


def test_live_rows_is_pending_when_the_daemon_writes_nothing(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """Registered engines that leave no row are honest PENDING, not FAIL.

    Engine 19 `memory` is the single writer of relational rows and is Phase 4. A
    Phase 2 daemon that records to JSONL and writes no SQLite row has not failed
    this criterion; its subject simply is not there yet.
    """
    fabricate_daemon(tree_with_harness, writes_run_row=False, writes_live_row=False)
    outcome = run(verify_module, "console_shows_live_rows", tree_with_harness)
    assert_pending(outcome, verify_module)
    assert "no store row carrying the daemon's run_id" in outcome.message


def test_live_rows_passes_when_the_console_renders_the_daemons_own_run(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    fabricate_daemon(tree_with_harness)
    outcome = run(verify_module, "console_shows_live_rows", tree_with_harness)
    assert_pass(outcome, verify_module)
    assert "market_sensor" in outcome.message


def test_a_console_that_renders_only_the_seed_is_a_fail(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """Distinguished by run, which is what makes seeded data unable to satisfy this."""
    fabricate_daemon(tree_with_harness, renders_run_id=False)
    outcome = run(verify_module, "console_shows_live_rows", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "no console screen renders any of them" in outcome.message


# --------------------------------------------------------------------------- #
# console_reads_persisted_mode
# --------------------------------------------------------------------------- #


def test_persisted_mode_is_pending_without_the_store_accessor(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    fabricate_daemon(tree_with_harness, has_mode_accessor=False)
    outcome = run(verify_module, "console_reads_persisted_mode", tree_with_harness)
    assert_pending(outcome, verify_module)
    assert "system-mode accessor" in outcome.message


def test_persisted_mode_is_pending_when_the_daemon_writes_no_run_row(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """`set_system_mode` returns False for an unknown `run_id` - there is no row.

    That is a different fact from a run whose mode has not been written yet, and
    B's `SystemModeRow` docstring is explicit that collapsing the two is how a band
    ends up confidently wrong. The criterion names which of the two it met.
    """
    fabricate_daemon(tree_with_harness, writes_run_row=False, writes_live_row=False)
    outcome = run(verify_module, "console_reads_persisted_mode", tree_with_harness)
    assert_pending(outcome, verify_module)
    assert "no `runs` row" in outcome.message


def test_persisted_mode_is_pending_when_core_never_calls_the_writer(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The lead's outstanding half, reported as PENDING rather than as my FAIL."""
    fabricate_daemon(tree_with_harness, persists_mode=False)
    outcome = run(verify_module, "console_reads_persisted_mode", tree_with_harness)
    assert_pending(outcome, verify_module)
    assert "not calling set_system_mode" in outcome.message


def test_persisted_mode_passes_when_a_real_daemon_wrote_it(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    fabricate_daemon(tree_with_harness)
    outcome = run(verify_module, "console_reads_persisted_mode", tree_with_harness)
    assert_pass(outcome, verify_module)
    assert "Running" in outcome.message


def test_a_band_that_ignores_the_persisted_mode_is_a_fail(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """The daemon wrote the fact; the band read something else."""
    fabricate_daemon(tree_with_harness, renders_mode=False)
    outcome = run(verify_module, "console_reads_persisted_mode", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "reading something else" in outcome.message


# --------------------------------------------------------------------------- #
# commands_round_trip - the negative test it never had. Spec 33 step 6.
# --------------------------------------------------------------------------- #

CRIPPLED_STORE_MODULE = '''
import sqlite3


class StoreClient:
    """B's store as it was through the whole of Phase 1: no command reader.

    `append_command` exists, so the console writes a perfectly correct row and its
    own criterion passes. Nothing here answers the orchestrator, which reaches for
    its reader through `getattr`, finds nothing, logs one debug line and continues.
    """

    def __init__(self, db_path):
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.connection.close()

    def append_command(self, row):
        cursor = self.connection.execute(
            "INSERT INTO commands (command, source, created_at, updated_at) VALUES (?,?,?,?)",
            (row.command, str(row.source), row.created_at, row.updated_at),
        )
        self.connection.commit()
        return int(cursor.lastrowid)
'''

CRIPPLED_MIGRATIONS_MODULE = '''
import sqlite3


def apply_migrations(db_path, migrations_dir=None):
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY,
                command TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                claimed_at INTEGER,
                consumed_at INTEGER,
                updated_at INTEGER NOT NULL);
            """
        )
        conn.commit()
    finally:
        conn.close()
'''


@pytest.fixture
def crippled_store_tree(bare_tree: Path, repo_root: Path) -> Path:
    """The **real** `core/` over a store with no command reader.

    The real orchestrator on purpose. `commands_round_trip` exists because a seam
    exercised only through a double is not tested - the double is - so its own
    negative test must not replace the half of the seam it is meant to judge.
    `core/` imports nothing from the rest of the package (architecture invariant
    0), so copying that one directory gives a genuine reader.
    """
    core_src = bare_tree / "src" / "acsoe"
    core_src.mkdir(parents=True)
    (core_src / "__init__.py").write_text("", encoding="utf-8")
    shutil.copytree(repo_root / "src" / "acsoe" / "core", core_src / "core")
    migrations = bare_tree / "db" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "0001_initial.sql").write_text("-- fabricated\n", encoding="utf-8")
    fabricate_package(
        bare_tree,
        {
            "acsoe.clients.store.client": CRIPPLED_STORE_MODULE,
            "acsoe.clients.store.contracts": DAEMON_CONTRACTS_MODULE,
            "acsoe.clients.store.migrations": CRIPPLED_MIGRATIONS_MODULE,
        },
    )
    return bare_tree


def test_commands_round_trip_fails_against_a_store_with_no_command_reader(
    verify_module: ModuleType, crippled_store_tree: Path
) -> None:
    """The defect the criterion exists to catch, reproduced.

    Through the whole of Phase 1 the orchestrator looked up
    `store.claim_pending_commands`, which `StoreClient` had never had. The lookup
    is a `getattr`, so finding nothing produced one debug line and a tick that
    carried on - and Phase 0 reported green, because the only implementations of
    that shape were test doubles. A daemon wired to the real store ignored every
    Activate, Freeze and Close-all ever written: the kill switch was inert.

    A criterion nobody has seen fail is a comment. This is the run where it fails.
    """
    outcome = run(verify_module, "commands_round_trip", crippled_store_tree)
    assert outcome.result is verify_module.Result.FAIL, outcome
    assert "The reader is not reading the store" in outcome.message


def test_commands_round_trip_is_pending_when_the_store_does_not_exist(
    verify_module: ModuleType, unbuilt_tree: Path
) -> None:
    """The other direction: absent is not broken.

    Without this, the FAIL above could be produced by a criterion that reports FAIL
    for everything, which would make it useless in the phase it was registered for.
    """
    outcome = run(verify_module, "commands_round_trip", unbuilt_tree)
    assert_pending(outcome, verify_module)


def test_the_crippled_store_really_would_have_satisfied_spec_24(
    crippled_store_tree: Path
) -> None:
    """The negative test has to be able to fail for the right reason.

    A store that could not write a command row at all would fail
    `commands_round_trip` for a reason that has nothing to do with the reader, and
    the test above would be green while proving nothing. This one writes the row
    through the crippled store and reads it straight back out of SQLite: the
    console's half of the seam is intact and only the daemon's half is missing,
    which is exactly the Phase 1 state.
    """
    db_path = crippled_store_tree / "acsoe.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            "CREATE TABLE commands (id INTEGER PRIMARY KEY, command TEXT NOT NULL, "
            "source TEXT NOT NULL, created_at INTEGER NOT NULL, claimed_at INTEGER, "
            "consumed_at INTEGER, updated_at INTEGER NOT NULL);"
        )
        conn.commit()
    finally:
        conn.close()

    namespace: dict[str, Any] = {}
    exec(CRIPPLED_STORE_MODULE, namespace)
    store = namespace["StoreClient"](db_path)
    try:
        row = type("Row", (), {"command": "activate", "source": "console"})()
        row.created_at = 1
        row.updated_at = 1
        command_id = store.append_command(row)
    finally:
        store.connection.close()

    conn = sqlite3.connect(db_path)
    try:
        stored = conn.execute(
            "SELECT command, claimed_at FROM commands WHERE id = ?", (command_id,)
        ).fetchone()
    finally:
        conn.close()
    assert stored == ("activate", None)


def test_a_commands_row_the_store_never_wrote_is_named_rather_than_unpacked(
    verify_module: ModuleType, tmp_path: Path
) -> None:
    """`_command_row` refuses a missing row instead of handing `None` to its caller.

    `sqlite3.Cursor.fetchone` is typed `Any` and returns `None` for a row that is not
    there, so the helper's declared `sqlite3.Row` was a claim nothing checked - which
    is how mypy found it once the toolchain widened to `scripts/`. All three callers
    index the result on the next line, so the absence used to arrive as
    `'NoneType' object is not subscriptable` three frames away, naming neither the
    command nor the table. The branch is only reachable from a store that returns an
    id for something it did not write, and a branch nobody has seen fire is a comment,
    so it is asked here directly.
    """
    db_path = tmp_path / "acsoe.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            "CREATE TABLE commands (id INTEGER PRIMARY KEY, command TEXT NOT NULL, "
            "source TEXT NOT NULL, created_at INTEGER NOT NULL, claimed_at INTEGER, "
            "consumed_at INTEGER, updated_at INTEGER NOT NULL);"
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(LookupError, match="`commands` has no such row"):
        verify_module._command_row(db_path, 4242)


def test_the_newest_recording_is_the_one_read(
    verify_module: ModuleType, tree_with_harness: Path
) -> None:
    """An older recording beside the newest must not supply the tolerance. Planted: a
    2026-01-01 recording in which BTC/USD's tick is 1.0, wide enough to pass a 0.5 shift that
    the newest recording's 0.1 tick fails."""
    ohlc_fixture(tree_with_harness)
    fabricate_builder(tree_with_harness, offsets=(("BTC/USD", "close", 0.5),))
    newest = tree_with_harness / RECORDED_ASSET_PAIRS
    older = newest.with_name("asset_pairs_recorded_2026-01-01.json")
    shutil.copy(newest, older)
    captured = json.loads(older.read_text(encoding="utf-8"))
    envelope = json.loads(captured["payload"])
    envelope["result"][REST_KEY["BTC/USD"]]["tick_size"] = "1.0"
    captured["payload"] = json.dumps(envelope)
    older.write_text(json.dumps(captured), encoding="utf-8")
    outcome = run(verify_module, "candles_match_independent_reduction_of_recorded_trades", tree_with_harness)
    assert_fail(outcome, verify_module)
    assert "asset_pairs_recorded_2026-09-19.json" in outcome.message, outcome.message
