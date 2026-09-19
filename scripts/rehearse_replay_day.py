"""Rehearse one replayed day end to end, and check every row by recomputation.

Spec 142. Before the six-month run (spec 143) launches, one calendar day of the window
runs through every registered chain against the replay client and the paper broker, with
the same client, config and engines as the full run, over the committed day fixture
(`scripts/cut_replay_fixture.py`). This script:

1. writes the run's config beside its databases: `config/default.yaml` with its `replay:`
   section, the partitions pointed at the committed fixture;
2. runs `acsoe research backtest` for the day **twice from a clean database**, and a third
   time **killed part-way and resumed**, each in its own process, measuring each process's
   wall clock and peak working set;
3. requires the two clean runs to write identical rows, and the resumed run to write the
   same rows apart from `run_id` and `cycle_id`, which differ between processes by
   construction;
4. for every approval, **recomputes** friction and hurdle from the fixtures alone: the fee
   schedule's tier, the bucket table, the pair's trailing 24-hour dollar volume summed from
   the fixture's own trades, and the declared book walked in exact rationals at the
   balance the paper ledger held. It requires equality with the `approvals` row and the
   `trades` row;
5. for every entry order, **recomputes** the fill from the fixture's trades under the
   broker's rule (a post-only buy fills at its limit on the first print strictly below
   it), or its absence for an order that was cancelled;
6. writes a report with the per-tick cost and the memory.

It reads the fixtures and writes only under `--out`. It never writes `data/raw/`,
`data/historical/` or `data/summaries/`.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

#: Columns that differ between two processes of one run by construction, never by a
#: decision: row ids, and the run and tick identity a new process mints.
PROCESS_COLUMNS = frozenset({"id", "run_id", "cycle_id", "claimed_by_run_id", "created_by_run_id"})
#: Two clean runs are separate databases, so each names its run differently; nothing
#: else may differ between them, row ids and tick numbers included.
RUN_COLUMNS = frozenset({"run_id", "claimed_by_run_id", "created_by_run_id"})
DECISION_TABLES = (
    "approvals", "rejections", "block_records", "equity_snapshots", "orders", "positions", "trades",
)


# --------------------------------------------------------------------------- #
# The child: one backtest process, reporting its own cost
# --------------------------------------------------------------------------- #


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_uint32),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_working_set_bytes() -> int | None:
    """The Win32 peak working set of this process, or `None` off Windows."""
    if sys.platform != "win32":
        return None
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.K32GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_ProcessMemoryCounters), ctypes.c_uint32,
    ]
    kernel32.K32GetProcessMemoryInfo.restype = ctypes.c_int
    if not kernel32.K32GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        return None
    return int(counters.PeakWorkingSetSize)


#: Where a child writes engine 7's published universe, candidate and ranking on every bar,
#: when the harness asks it to. Only for spec 144's comparison with the offline grid: the
#: database keeps the candidate but not the universe engine 7 ranked it in.
SCOUT_LOG_ENV = "ACSOE_REHEARSAL_SCOUT_LOG"


def _capture_scout(log_path: Path) -> None:
    """Wrap the orchestrator's `_run` in this process so engine 7's payload is logged.

    Observation only: the result is returned unchanged, and nothing is written to the
    store or into `state`.
    """
    from acsoe.core import orchestrator

    original = orchestrator.Orchestrator._run

    def run(self: Any, engine: Any, context: Any, state: Any) -> Any:
        result = original(self, engine, context, state)
        if engine.name == "scout":
            feature = state.get("feature") or {}
            with log_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps({
                    "now": context.now.isoformat(),
                    "bar_ts": feature.get("bar_ts"),
                    "universe": list(result.data.get("pairs", [])),
                    "candidate": result.data.get("pair"),
                    "ranked": list(result.data.get("ranked", [])),
                    "reason_code": result.data.get("reason_code"),
                }) + "\n")
        return result

    orchestrator.Orchestrator._run = run  # type: ignore[method-assign]


def child(argv: list[str]) -> int:
    import os

    from acsoe.cli import main as cli_main

    scout_log = os.environ.get(SCOUT_LOG_ENV)
    if scout_log:
        _capture_scout(Path(scout_log))
    started = time.perf_counter()
    code = cli_main.main(argv)
    print(
        "REHEARSAL-CHILD "
        + json.dumps(
            {"exit": code, "wall_s": round(time.perf_counter() - started, 1),
             "peak_working_set_bytes": peak_working_set_bytes()}
        ),
        flush=True,
    )
    return code


def tree_digest(model_dirs: list[Path]) -> str:
    """sha256 over every file a replay's decisions depend on and this script does not vary:
    the package source, the migrations, and the fold run directories in use.

    The checkout is shared with agents who are still building. A rehearsal whose three runs
    saw different source is comparing two systems, not rerunning one, and its identity
    verdicts mean nothing. So the digest is taken before and after every run, and the report
    says whether it moved (`code-standards.md`: hash the files that are not the variable).
    """
    import hashlib

    digest = hashlib.sha256()
    paths = [*sorted((REPO / "src").rglob("*.py")), *sorted((REPO / "db" / "migrations").glob("*.sql"))]
    for directory in model_dirs:
        paths.extend(sorted(directory.iterdir()))
    for path in paths:
        digest.update(path.relative_to(REPO).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_child(argv: list[str], log: Path, *, scout_log: Path | None = None) -> dict[str, Any]:
    import os

    env = dict(os.environ)
    env.pop(SCOUT_LOG_ENV, None)
    if scout_log is not None:
        env[SCOUT_LOG_ENV] = str(scout_log)
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child", *argv],
        cwd=REPO, capture_output=True, text=True, check=False, env=env,
    )
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    lines = [line for line in result.stdout.splitlines() if line.startswith("REHEARSAL-CHILD ")]
    if result.returncode != 0 or not lines:
        raise SystemExit(f"backtest failed (exit {result.returncode}); see {log}")
    report: dict[str, Any] = json.loads(lines[-1].split(" ", 1)[1])
    return report


# --------------------------------------------------------------------------- #
# Rows
# --------------------------------------------------------------------------- #


def rows(db: Path, *, drop: frozenset[str] = RUN_COLUMNS) -> dict[str, list[tuple[Any, ...]]]:
    connection = sqlite3.connect(db)
    try:
        # Run identity differs between databases and processes by construction (each
        # process names its own run), and a SHAP reference or a detail can carry it in
        # text, so every run id of this database is replaced by one placeholder.
        run_ids = [str(row[0]) for row in connection.execute("SELECT run_id FROM runs")]

        def neutral(value: Any) -> Any:
            if isinstance(value, str):
                for run_id in run_ids:
                    value = value.replace(run_id, "<run>")
            return value

        dumped: dict[str, list[tuple[Any, ...]]] = {}
        for table in DECISION_TABLES:
            cursor = connection.execute(f"SELECT * FROM {table}")
            names = [column[0] for column in cursor.description]
            keep = [index for index, name in enumerate(names) if name not in drop]
            dumped[table] = sorted(
                (tuple(neutral(row[index]) for index in keep) for row in cursor.fetchall()), key=repr
            )
        return dumped
    finally:
        connection.close()


def records(db: Path, table: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
    finally:
        connection.close()


# --------------------------------------------------------------------------- #
# Recomputation, from the fixtures alone
# --------------------------------------------------------------------------- #


class Fixture:
    """The day's trades, the bucket table and the fee tier, read directly."""

    def __init__(self, partitions: Path, table: Path, fees: Path, names: Path, tier: int) -> None:
        import polars as pl

        manifest = json.loads((partitions / "manifest.json").read_text(encoding="utf-8"))
        joined = json.loads(names.read_text(encoding="utf-8"))["pairs"]
        frames = []
        for archive in manifest["pairs"]:
            if archive not in joined:
                # Survivorship: no recorded rules, so the replay never serves this pair.
                continue
            for path in sorted((partitions / archive).glob("*.parquet")):
                frame = pl.read_parquet(path)
                frames.append(frame.with_columns(pl.lit(joined[archive]["v2_symbol"]).alias("pair")))
        self.trades = pl.concat(frames)
        raw = json.loads(table.read_text(encoding="utf-8"), parse_float=Decimal)["buckets"]
        by_name = {row["bucket"]: row for row in raw}
        self.buckets = []
        for row in raw:
            source = by_name[row["mapped_to"]] if row.get("mapped_to") else row
            self.buckets.append(
                (
                    Fraction(Decimal(str(row["usd_day_from"]))),
                    None if row["usd_day_below"] is None else Fraction(Decimal(str(row["usd_day_below"]))),
                    Fraction(Decimal(str(source["spread_bps"]["median"]))),
                    Fraction(Decimal(str(source["depth_bid_bps_to_10k_from_mid"]["median"]))),
                )
            )
        schedule = json.loads(fees.read_text(encoding="utf-8"))["spot_crypto"]
        (row,) = [item for item in schedule if item["Tier"] == f"Tier {tier}"]
        self.maker = Fraction(row["Spot Maker (%)"].replace("%", "").strip()) / 100
        self.taker = Fraction(row["Spot Taker (%)"].replace("%", "").strip()) / 100

    def window(self, pair: str, lo_s: int, hi_s: int) -> list[tuple[int, str, str]]:
        """`(ts, price, volume)` for `lo_s < ts <= hi_s`, in file order."""
        import polars as pl

        frame = self.trades.filter(
            (pl.col("pair") == pair) & (pl.col("ts") > lo_s) & (pl.col("ts") <= hi_s)
        )
        return list(zip(frame["ts"].to_list(), frame["price"].to_list(), frame["volume"].to_list(), strict=True))

    def friction(self, pair: str, at_s: int, balance: Fraction) -> tuple[Fraction, Fraction, Fraction]:
        """Fees + spread + slippage for `pair` at `at_s`, and the spread and slippage alone."""
        window = self.window(pair, at_s - 86400, at_s)
        volume = sum((Fraction(Decimal(price)) * Fraction(Decimal(qty)) for _ts, price, qty in window), Fraction(0))
        mid = Fraction(Decimal(window[-1][1]))
        (spread_bps, depth_bps) = next(
            (spread, depth) for lower, upper, spread, depth in self.buckets
            if volume >= lower and (upper is None or volume < upper)
        )
        half = spread_bps / 10_000 / 2
        far = depth_bps / 10_000
        levels = [mid * (1 - (half + (far - half) * i / 9)) for i in range(10)]
        remaining, base = balance, Fraction(0)
        for price in levels:
            if remaining <= 1000:
                base += remaining / price
                remaining = Fraction(0)
                break
            base += Fraction(1000) / price
            remaining -= 1000
        if remaining > 0:
            raise ValueError("the declared book cannot absorb the balance")
        best = levels[0]
        slippage = (best - balance / base) / best
        spread = spread_bps / 10_000
        return self.maker + self.taker + spread + slippage, spread, slippage


def usd_balance_at(orders: list[dict[str, Any]], at_micros: int, start: Fraction) -> Fraction:
    """The paper ledger's USD at `at_micros`: the opening balance, less every entry filled
    by then (cost and fee), plus every exit (proceeds less fee)."""
    balance = start
    for order in orders:
        if order["status"] != "filled" or order["closed_at"] is None or order["closed_at"] > at_micros:
            continue
        notional = Fraction(Decimal(order["avg_fill_price"])) * Fraction(Decimal(order["filled_qty"]))
        fee = Fraction(Decimal(order["fee"] or "0"))
        balance += -notional - fee if order["intent"] == "entry" else notional - fee
    return balance


def close(a: Fraction, b: Fraction) -> bool:
    """Equal to 1e-20 relative: the engines divide at 28 significant digits, and a level's
    quantity and a walk's fill price are not terminating decimals."""
    return abs(a - b) <= abs(b) * Fraction(1, 10**20)


def recompute(db: Path, fixture: Fixture, start_usd: Fraction, hurdle_multiple: Fraction) -> dict[str, Any]:
    orders = records(db, "orders")
    approvals = records(db, "approvals")
    trades = {row["entry_userref"]: row for row in records(db, "trades")}
    economics: list[dict[str, Any]] = []
    for approval in approvals:
        at_micros = int(approval["ts"])
        balance = usd_balance_at(orders, at_micros, start_usd)
        friction, spread, slippage = fixture.friction(approval["pair"], at_micros // 1_000_000, balance)
        hurdle = hurdle_multiple * friction
        stored = {key: Fraction(Decimal(approval[key])) for key in ("friction_pct", "hurdle_pct")}
        entry = {
            "userref": approval["userref"], "pair": approval["pair"], "ts": at_micros,
            "balance": str(float(balance)), "spread": float(spread), "slippage": float(slippage),
            "friction_equal": close(stored["friction_pct"], friction),
            "hurdle_equal": close(stored["hurdle_pct"], hurdle),
        }
        trade = trades.get(approval["userref"])
        if trade is not None:
            entry["trade_row_equal"] = all(
                trade[key] == approval[key]
                for key in ("expected_move_pct", "friction_pct", "net_edge_pct", "hurdle_pct")
            )
        economics.append(entry)

    fills: list[dict[str, Any]] = []
    for order in orders:
        if order["intent"] != "entry":
            continue
        limit = Fraction(Decimal(order["limit_price"]))
        placed_s = int(order["placed_at"]) // 1_000_000
        closed = order["closed_at"]
        horizon_s = (int(closed) // 1_000_000) if closed is not None else placed_s + 3600
        prints = [
            (ts, Fraction(Decimal(price)))
            for ts, price, _qty in fixture.window(order["pair"], placed_s - 1, horizon_s)
            if ts * 1_000_000 > int(order["placed_at"])
        ]
        first_below = next((ts for ts, price in prints if price < limit), None)
        if order["status"] == "filled":
            expected_tick = -(-first_below // 60) * 60 if first_below is not None else None
            fills.append({
                "userref": order["userref"], "status": "filled",
                "fill_at_limit": Fraction(Decimal(order["avg_fill_price"])) == limit,
                "fill_tick_equal": expected_tick is not None and int(closed) // 1_000_000 == expected_tick,
            })
        else:
            fills.append({
                "userref": order["userref"], "status": order["status"],
                "no_print_below_limit": first_below is None,
            })
    return {"economics": economics, "fills": fills}


# --------------------------------------------------------------------------- #
# Launch preconditions and spec 144's comparison
# --------------------------------------------------------------------------- #


def preconditions(db: Path) -> dict[str, Any]:
    """The counts the lead requires before spec 143 launches (overnight decision log)."""
    connection = sqlite3.connect(db)
    try:
        def one(sql: str) -> int:
            return int(connection.execute(sql).fetchone()[0])

        run_ids = [row[0] for row in connection.execute("SELECT run_id FROM runs")]
        placed = one("SELECT count(*) FROM orders WHERE intent = 'entry'")
        approved = one(
            "SELECT count(*) FROM orders o JOIN approvals a ON a.userref = o.userref "
            "WHERE o.intent = 'entry'"
        )
        result = {
            "runs": len(run_ids),
            "runs_with_scenario_digest": one("SELECT count(*) FROM runs WHERE scenario_digest IS NOT NULL"),
            "entries_placed": placed,
            "entries_with_an_approvals_row": approved,
            "approvals": one("SELECT count(*) FROM approvals"),
            "approvals_with_details": one("SELECT count(*) FROM approvals WHERE details IS NOT NULL"),
            "rejections": one("SELECT count(*) FROM rejections"),
            "rejections_with_details": one("SELECT count(*) FROM rejections WHERE details IS NOT NULL"),
        }
    finally:
        connection.close()
    shap = [REPO / "data" / "derived" / "shap" / str(run_id) for run_id in run_ids]
    result["shap_files"] = sum(len(list(path.rglob("*.parquet"))) for path in shap if path.is_dir())
    return result


def gates(db: Path) -> dict[str, int]:
    """Rejections per refusing engine and reason code."""
    connection = sqlite3.connect(db)
    try:
        return {
            f"{by}:{code}": int(count)
            for by, code, count in connection.execute(
                "SELECT rejected_by, reason_code, count(*) FROM rejections GROUP BY 1, 2 ORDER BY 3 DESC"
            )
        }
    finally:
        connection.close()


def ranking_check(
    scout_log: Path, config: Any, pair_names: Path, *, fee_round_trip: Fraction
) -> dict[str, Any]:
    """Spec 144: engine 7's candidate against the offline grid's, bar by bar, within
    engine 7's own universe, through C's `research/ranking_check.grid_order`.

    The grid names pairs as the archive does (`STORJUSD`) and engine 7 as the v2 feed does
    (`STORJ/USD`), so the grid's order is mapped through spec 127's recorded name join.
    A bar whose choice differs inside the universe is listed, and so is a bar whose
    choice sits inside a tie the two spellings break differently.

    **The stop criterion (the lead's ruling on F6).** Any disagreement or tie in which
    **either** pick's expected move clears the cost bar at the run's tier is a stop, listed
    under `stops`. The bar used is the fees-only one, `(1 + hurdle_multiple) x fees`, which
    is **below** every pair's real bar (spread and slippage only raise it), so the check can
    only flag more bars than the true rule would, never fewer. Differences confined to
    pairs below it are explained differences, counted and listed.
    """
    from acsoe.research.ranking_check import grid_order

    names = {k: v["v2_symbol"] for k, v in json.loads(pair_names.read_text(encoding="utf-8"))["pairs"].items()}
    bars = [json.loads(line) for line in scout_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    compared = 0
    disagreements: list[dict[str, Any]] = []
    ties: list[dict[str, Any]] = []
    stops: list[dict[str, Any]] = []
    hurdle = Fraction(Decimal(str(config.get("trading.hurdle_multiple"))))
    bar_floor = (1 + hurdle) * fee_round_trip
    for bar in bars:
        if bar["bar_ts"] is None or not bar["ranked"] or bar["candidate"] is None:
            continue
        fold, order = grid_order(
            int(bar["bar_ts"]),
            oos_path=REPO / "data" / "derived" / "oos_train-20260913T205245-067b2b9d.parquet",
            study_dir=REPO / "data" / "derived" / "di_anomaly_train-20260913T205245-067b2b9d",
            di_percentile=float(config.get("prediction.di_percentile")),
            anomaly_percentile=float(config.get("anomaly.threshold_percentile")),
        )
        universe = set(bar["universe"])
        mapped = [names.get(entry.pair, entry.pair) for entry in order]
        grid_inside = next((pair for pair in mapped if pair in universe), None)
        outside = [pair for pair in mapped[: mapped.index(grid_inside)] if pair not in universe] if grid_inside else mapped
        # The candidate engine 7 published: the ranking's first pair, as `select_candidate`
        # takes it.
        engine_choice = bar["candidate"]
        compared += 1
        if engine_choice == grid_inside:
            continue
        # A tie at the top is broken by name on both sides, but the grid spells pairs as
        # the archive does (`EURUSD`, `XBTUSD`) and engine 7 as the feed does (`BTC/USD`,
        # `EUR/USD`), so the two orders can differ inside a tie. Counted apart, not hidden.
        top = next((entry.expected_move_pct for entry in order if names.get(entry.pair, entry.pair) == grid_inside), None)
        tied = {
            names.get(entry.pair, entry.pair) for entry in order
            if top is not None and entry.expected_move_pct == top and names.get(entry.pair, entry.pair) in universe
        }
        engine_move = next(
            (Fraction(Decimal(str(entry["expected_move_pct"]))) for entry in bar["ranked"]
             if isinstance(entry, dict) and entry.get("pair") == engine_choice),
            None,
        )
        grid_move = None if top is None else Fraction(Decimal(repr(top)))
        entry_out = {
            "bar_ts": bar["bar_ts"], "fold": fold, "engine": engine_choice,
            "engine_expected_move": None if engine_move is None else float(engine_move),
            "grid_in_universe": grid_inside,
            "grid_expected_move": None if grid_move is None else float(grid_move),
        }
        if engine_choice in tied:
            ties.append(entry_out)
        else:
            disagreements.append({**entry_out, "grid_outside_universe": outside[:5]})
        if any(move is not None and move > bar_floor for move in (engine_move, grid_move)):
            stops.append(entry_out)
    return {
        "bars_compared": compared,
        "agree": compared - len(disagreements) - len(ties),
        "tie_broken_by_name_spelling": ties,
        "disagreements": disagreements,
        "cost_bar_floor": float(bar_floor),
        "stops": stops,
    }


# --------------------------------------------------------------------------- #
# The rehearsal
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    args_list = sys.argv[1:] if argv is None else argv
    if args_list and args_list[0] == "--child":
        return child(args_list[1:])
    parser = argparse.ArgumentParser(prog="rehearse_replay_day.py", description=__doc__.split("\n")[0])
    parser.add_argument("--day", required=True)
    parser.add_argument("--fixture", type=Path, required=True, help="the cut day, e.g. tests/fixtures/phase7/rehearsal_2024-10-20")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tier", type=int, default=3)
    parser.add_argument("--ranking", default="expected_move")
    parser.add_argument("--kill-after", type=int, default=40, help="ticks before the kill")
    parser.add_argument("--fold", type=int, default=None, help="restrict the window to the day's fold")
    parser.add_argument("--config", type=Path, default=REPO / "config" / "default.yaml")
    args = parser.parse_args(args_list)

    import yaml

    from acsoe.platform.config import load_config

    out: Path = args.out
    if out.exists():
        raise SystemExit(f"{out} exists; a rehearsal writes a fresh directory")
    out.mkdir(parents=True)
    raw = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if "replay" not in raw:
        raise SystemExit("the config has no replay: section")
    raw["replay"]["partitions_dir"] = args.fixture.as_posix()
    if args.fold is not None:
        # The day's own fold only. The driver refuses a window whose run directories do not
        # all exist, and the day never touches another fold's models, so narrowing the
        # window here changes no decision on the day.
        raw["replay"]["first_fold"] = args.fold
        raw["replay"]["last_fold"] = args.fold
    config_path = out / "config.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    committed = load_config(config_path, load_env=False)

    day = datetime.fromisoformat(args.day).replace(tzinfo=UTC)
    base = ["--config", str(config_path), "research", "backtest", "--ranking", args.ranking,
            "--fee-tier", str(args.tier), "--begin", day.isoformat(),
            "--until", (day + timedelta(days=1)).isoformat()]

    replay_section = committed.get("replay")
    model_dirs = [
        REPO / "models" / replay_section.run_id_format.format(fold=fold)
        for fold in range(replay_section.first_fold, replay_section.last_fold + 1)
    ]
    report: dict[str, Any] = {"day": args.day, "tier": args.tier, "ranking": args.ranking, "runs": {}}
    digests = [tree_digest(model_dirs)]
    for name in ("a", "b"):
        report["runs"][name] = run_child(
            [*base, "--db", str(out / f"{name}.sqlite")], out / f"{name}.log",
            scout_log=out / "scout.jsonl" if name == "a" else None,
        )
        digests.append(tree_digest(model_dirs))
    split = out / "split.sqlite"
    report["runs"]["split_first"] = run_child(
        [*base, "--db", str(split), "--max-ticks", str(args.kill_after)], out / "split_first.log"
    )
    digests.append(tree_digest(model_dirs))
    report["runs"]["split_resume"] = run_child([*base, "--db", str(split), "--resume"], out / "split_resume.log")
    digests.append(tree_digest(model_dirs))
    report["tree_digests"] = digests
    report["tree_unchanged"] = len(set(digests)) == 1

    report["clean_runs_identical"] = rows(out / "a.sqlite") == rows(out / "b.sqlite")
    report["resumed_identical"] = rows(out / "a.sqlite", drop=PROCESS_COLUMNS) == rows(split, drop=PROCESS_COLUMNS)

    record = [json.loads(line) for line in (out / "a.sqlite.runrecord.jsonl").read_text(encoding="utf-8").splitlines()]
    ticks = [entry for entry in record if entry["event"] == "tick"]
    bar = [entry["wall_ms"] for entry in ticks if entry["bar_tick"]]
    minute = [entry["wall_ms"] for entry in ticks if not entry["bar_tick"]]
    report["ticks"] = {
        "bar": len(bar), "minute": len(minute),
        "bar_ms_mean": round(sum(bar) / len(bar), 1) if bar else None,
        "bar_ms_max": max(bar) if bar else None,
        "minute_ms_mean": round(sum(minute) / len(minute), 1) if minute else None,
    }

    replay = committed.get("replay")
    fixture = Fixture(
        args.fixture, REPO / replay.spread_table_file, REPO / replay.fee_schedule_file,
        REPO / replay.pair_names_file, args.tier,
    )
    start_usd = Fraction(Decimal(str(committed.get("paper.starting_balances.USD"))))
    hurdle_multiple = Fraction(Decimal(str(committed.get("trading.hurdle_multiple"))))
    report["recomputed"] = recompute(out / "a.sqlite", fixture, start_usd, hurdle_multiple)
    counts = {table: len(values) for table, values in rows(out / "a.sqlite").items()}
    report["row_counts"] = counts
    report["launch_preconditions"] = preconditions(out / "a.sqlite")
    report["gates"] = gates(out / "a.sqlite")
    report["trades"] = records(out / "a.sqlite", "trades")
    if args.ranking == "expected_move":
        report["ranking_check"] = ranking_check(
            out / "scout.jsonl", committed, REPO / replay.pair_names_file,
            fee_round_trip=fixture.maker + fixture.taker,
        )
        report["ranking_stop"] = bool(report["ranking_check"]["stops"])
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
