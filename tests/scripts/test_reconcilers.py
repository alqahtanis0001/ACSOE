"""The two reconcilers, against the line the daemon actually writes.

Both read `logs/acsoe.jsonl` for the per-tick line `run_loop` emits. That is a
seam between two files nobody edits together, and it fails in the quietest way
available: rename the event and both scripts keep running, keep printing, and
report "nothing found" — which is also what they print when the daemon has never
run. So the event name is asserted against the daemon's own constant rather than
against a copy.

The rest of this file is about the other silent failures:

* **An empty subscription is an answer, not an absence.** "The daemon ran and
  subscribed to nothing" and "the daemon was not running" must not render the
  same, or a daemon with a broken scope reads as a daemon that is off.
* **Rotated logs must be read.** `TimedRotatingFileHandler` renames yesterday's
  file at midnight, so a `--from`/`--to` question about last week answered from
  today's file alone is answered from less data than was asked for, silently.
* **Both `quotes` shapes must parse**, because a log written before the list
  shape existed still holds real history and throwing it away to make a point
  would be worse than reading it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from acsoe.cli.engine import MARKET_SNAPSHOT_EVENT

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> ModuleType:
    """`scripts/` is not a package, so these are loaded by path."""
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"acsoe_{name}_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


universe = _load("reconcile_universe")
spread = _load("reconcile_spread")


# --------------------------------------------------------------------------- #
# The seam
# --------------------------------------------------------------------------- #


def test_both_reconcilers_read_the_event_the_daemon_writes() -> None:
    """**The assertion that stops this whole thing rotting quietly.**

    If `cli/engine.py` renames the event, both scripts keep running and report
    "nothing found" — which is indistinguishable from a daemon that has not run.
    Nothing else in the system would notice.
    """
    assert universe.SUBSCRIPTION_EVENT == MARKET_SNAPSHOT_EVENT
    assert spread.QUOTES_EVENT == MARKET_SNAPSHOT_EVENT


def test_the_field_names_the_reconcilers_read_are_the_ones_the_daemon_writes() -> None:
    from acsoe.cli.engine import QUOTE_FIELDS, market_snapshot

    snapshot = market_snapshot(
        {
            "market_data_recorder": {"subscription": ("BTC/USD",)},
            "market_sensor": {
                "quotes": {
                    "BTC/USD": {
                        "pair": "BTC/USD",
                        "bid": "1",
                        "ask": "2",
                        "spread": "1",
                        "spread_pct": "0.5",
                        "ts": "2026-09-11T00:00:00Z",
                    }
                }
            },
        }
    )
    # reconcile_universe reads one of SUBSCRIPTION_FIELDS.
    assert any(field in snapshot for field in universe.SUBSCRIPTION_FIELDS)
    # reconcile_spread reads `spread_pct` out of each quote.
    assert "spread_pct" in snapshot["quotes"][0]
    assert "spread_pct" in QUOTE_FIELDS


# --------------------------------------------------------------------------- #
# reconcile_universe
# --------------------------------------------------------------------------- #


def write_log(path: Path, lines: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(line) for line in lines) + ("\n" if lines else ""), encoding="utf-8"
    )
    return path


def snapshot_line(
    pairs: list[str], *, ts: str, quotes: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "event": MARKET_SNAPSHOT_EVENT,
        "level": "info",
        "logger": "acsoe.engine",
        "ts": ts,
        "cycle_id": 1,
        "mode": "paper",
        "subscription": pairs,
        "subscription_count": len(pairs),
        "subscription_derived": True,
        "quotes": quotes or [],
        "quote_count": len(quotes or []),
    }


def test_the_daemons_subscription_is_read_from_the_log(tmp_path: Path) -> None:
    log = write_log(
        tmp_path / "acsoe.jsonl",
        [
            {"event": "engine_starting", "ts": "2026-09-11T00:00:00Z"},
            snapshot_line(["BTC/USD", "ETH/USD"], ts="2026-09-11T00:01:00Z"),
        ],
    )
    pairs, line, scanned = universe.read_daemon_subscription(log)
    assert pairs == {"BTC/USD", "ETH/USD"}
    assert line is not None
    assert scanned == 2


def test_the_last_line_wins_because_the_scope_is_rederived_each_tick(
    tmp_path: Path,
) -> None:
    log = write_log(
        tmp_path / "acsoe.jsonl",
        [
            snapshot_line(["BTC/USD"], ts="2026-09-11T00:01:00Z"),
            snapshot_line(["BTC/USD", "SOL/USD"], ts="2026-09-11T00:02:00Z"),
        ],
    )
    pairs, _line, _scanned = universe.read_daemon_subscription(log)
    assert pairs == {"BTC/USD", "SOL/USD"}


def test_an_empty_subscription_is_an_answer_not_an_absence(tmp_path: Path) -> None:
    """**Two different facts that must not render the same.**

    A daemon whose scope came out empty — no balance, no pair rules — is a real
    and urgent finding. A daemon that has not run is a different one. If an empty
    list read as "no pair list found", the first would be reported as the second
    and nobody would look at the scope.
    """
    log = write_log(tmp_path / "acsoe.jsonl", [snapshot_line([], ts="2026-09-11T00:01:00Z")])
    pairs, line, _scanned = universe.read_daemon_subscription(log)
    assert pairs == set()
    assert line is not None, "an empty subscription must still count as a line"

    empty_log = write_log(tmp_path / "empty.jsonl", [])
    _pairs, missing, _scanned = universe.read_daemon_subscription(empty_log)
    assert missing is None, "a log with no snapshot line must report no line at all"


def test_rotated_logs_are_read(tmp_path: Path) -> None:
    """`TimedRotatingFileHandler` renames yesterday's file at midnight."""
    live = tmp_path / "acsoe.jsonl"
    write_log(tmp_path / "acsoe.jsonl.2026-09-10", [snapshot_line(["OLD/USD"], ts="2026-09-10T00:00:00Z")])
    write_log(live, [snapshot_line(["BTC/USD"], ts="2026-09-11T00:00:00Z")])

    assert [path.name for path in universe.log_files(live)] == [
        "acsoe.jsonl.2026-09-10",
        "acsoe.jsonl",
    ], "the live file must be read last, so the LAST line is the most recent one"
    pairs, _line, scanned = universe.read_daemon_subscription(live)
    assert scanned == 2
    assert pairs == {"BTC/USD"}


def test_the_comparison_names_a_pair_the_recorder_does_not_record() -> None:
    result = universe.compare(
        recorded_raw={"BTC/USD", "ETH/USD"},
        recorded_summary={"SOL/USD"},
        daemon={"BTC/USD", "ETH/USD", "SOL/USD", "FAKE/USD"},
    )
    assert result["daemon_only"] == ["FAKE/USD"]
    assert result["daemon_summary_only"] == ["SOL/USD"]
    assert result["both_full"] == ["BTC/USD", "ETH/USD"]

    lines, clean = universe.report(result, have_daemon_list=True)
    assert not clean
    text = "\n".join(lines)
    assert "FAKE/USD" in text
    assert "cannot be backfilled" in text


def test_no_daemon_list_is_reported_as_not_clean() -> None:
    """A reconciler that printed "no differences" over an empty comparison would
    be worse than not having one."""
    result = universe.compare(recorded_raw={"BTC/USD"}, recorded_summary=set(), daemon=set())
    lines, clean = universe.report(result, have_daemon_list=False)
    assert not clean
    text = "\n".join(lines)
    assert "NOT a clean result" in text
    assert MARKET_SNAPSHOT_EVENT in text


# --------------------------------------------------------------------------- #
# reconcile_spread
# --------------------------------------------------------------------------- #


def test_quotes_are_read_from_the_list_shape_the_daemon_writes() -> None:
    entries = spread.quote_entries(
        [{"pair": "BTC/USD", "spread_pct": "0.0002"}, {"pair": "ETH/USD", "spread_pct": "0.0003"}]
    )
    assert [pair for pair, _quote in entries] == ["BTC/USD", "ETH/USD"]


def test_the_older_mapping_shape_is_still_read() -> None:
    """A log written before the list shape existed holds real history, and
    throwing it away to make a point would be worse than reading it."""
    entries = spread.quote_entries({"BTC/USD": {"spread_pct": "0.0002"}})
    assert [pair for pair, _quote in entries] == ["BTC/USD"]


def test_spread_pct_is_a_ratio_and_converts_to_basis_points() -> None:
    """`spread_pct` is `(ask - bid) / mid` as a DECIMAL RATIO despite the name.

    Multiplying by 100 instead of 10,000 is the single most likely bug in that
    file, and it would present as a 100x calibration error rather than as an
    exception — a finding-shaped number that is really a units bug.
    """
    assert spread._spread_bps_of({"spread_pct": "0.0002"}) == pytest.approx(2.0)
    assert spread._spread_bps_of({"bid": "99990", "ask": "100010"}) == pytest.approx(2.0)


def test_a_crossed_quote_is_kept_rather_than_clamped() -> None:
    """Engine 3 publishes a negative `spread_pct` rather than clamping it, and a
    systematically crossed feed is a finding."""
    assert spread._spread_bps_of({"spread_pct": "-0.0001"}) == pytest.approx(-1.0)


def test_daemon_spreads_are_read_from_a_real_shaped_log(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    ts = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    log = write_log(
        tmp_path / "acsoe.jsonl",
        [
            snapshot_line(
                ["BTC/USD"],
                ts=ts,
                quotes=[
                    {"pair": "BTC/USD", "bid": "99990", "ask": "100010", "spread_pct": "0.0002"},
                    {"pair": "KEY/USD", "bid": "9.99", "ask": "10.01", "spread_pct": "0.002"},
                ],
            )
        ],
    )
    observations, scanned = spread.read_daemon_spreads(
        log, start=(now - timedelta(hours=1)).timestamp(), end=(now + timedelta(hours=1)).timestamp(), pairs=None
    )
    assert scanned == 1
    by_pair = {item.pair: item.spread_bps for item in observations}
    assert by_pair["BTC/USD"] == pytest.approx(2.0)
    assert by_pair["KEY/USD"] == pytest.approx(20.0), (
        "a pair whose symbol looks like a credential must reach the comparison"
    )


def test_a_window_excludes_lines_outside_it(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    log = write_log(
        tmp_path / "acsoe.jsonl",
        [
            snapshot_line(
                ["BTC/USD"],
                ts=(now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                quotes=[{"pair": "BTC/USD", "spread_pct": "0.0002"}],
            )
        ],
    )
    observations, _scanned = spread.read_daemon_spreads(
        log, start=(now - timedelta(hours=1)).timestamp(), end=now.timestamp(), pairs=None
    )
    assert observations == []


def test_the_difference_is_reported_as_a_distribution_not_a_number() -> None:
    """A mean near zero over a wide spread is timing noise between two observers
    of one book; a small constant offset is a calibration error. A mean alone
    cannot tell them apart, and only the second one should change anything.
    """
    daemon = [
        spread.Observation(pair="BTC/USD", ts=float(index * 60), spread_bps=2.0, source="daemon")
        for index in range(10)
    ]
    archive = [
        spread.Observation(
            pair="BTC/USD", ts=float(index * 60), spread_bps=2.5, source="tier2_minute_median"
        )
        for index in range(10)
    ]
    matched = spread.match(daemon, archive, window_s=60.0)
    assert len(matched) == 10
    result = spread.analyse(matched)
    assert result["overall"]["mean"] == pytest.approx(-0.5)
    assert result["overall"]["stdev"] == pytest.approx(0.0)
    assert "tier2_minute_median" in result["by_source"]
    assert "systematic difference" in spread.interpret(result["overall"])


def test_noise_is_not_called_a_calibration_error() -> None:
    """The interpretation says what the numbers are consistent with, never what
    they prove. A wide symmetric spread around zero is two observers disagreeing
    by timing, and calling that a calibration error would invite somebody to
    correct for noise."""
    stats = spread.distribution([-3.0, 3.0, -2.0, 2.0, -1.0, 1.0, 0.0, 0.5, -0.5, 0.2])
    assert "timing noise" in spread.interpret(stats)


def test_an_archive_observation_is_matched_to_the_nearest_quote_in_time() -> None:
    """Nearest, not "the one before": preferring the earlier observation would
    build a systematic lag into the very statistic being measured."""
    daemon = [spread.Observation(pair="BTC/USD", ts=100.0, spread_bps=2.0, source="daemon")]
    archive = [
        spread.Observation(pair="BTC/USD", ts=50.0, spread_bps=9.0, source="tier2_minute_median"),
        spread.Observation(pair="BTC/USD", ts=101.0, spread_bps=2.5, source="tier2_minute_median"),
    ]
    matched = spread.match(daemon, archive, window_s=60.0)
    assert len(matched) == 1
    assert matched[0][1].spread_bps == pytest.approx(2.5)
    assert matched[0][2] == pytest.approx(1.0)


def test_rotated_logs_are_read_by_the_spread_reconciler(tmp_path: Path) -> None:
    live = tmp_path / "acsoe.jsonl"
    now = datetime.now(UTC)
    write_log(
        tmp_path / "acsoe.jsonl.2026-09-10",
        [
            snapshot_line(
                ["BTC/USD"],
                ts=(now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                quotes=[{"pair": "BTC/USD", "spread_pct": "0.0002"}],
            )
        ],
    )
    write_log(live, [])
    observations, _scanned = spread.read_daemon_spreads(
        live,
        start=(now - timedelta(hours=1)).timestamp(),
        end=(now + timedelta(hours=1)).timestamp(),
        pairs=None,
    )
    assert len(observations) == 1, "a rotated log holds real history and must be read"
