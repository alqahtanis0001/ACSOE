"""Regenerate every Phase 7 figure from the two run databases. Deterministic.

    <figures venv>\\Scripts\\python.exe docs/dataset/phase-7-figures/make_phase7_figures.py

The figures venv is deliberately NOT the project's `.venv`: matplotlib is not a runtime
dependency, and installing it into `.venv` while the runs were live could have upgraded a
package underneath them. Create it once with:

    py -3 -m venv ../ACSOE-figures-venv
    ../ACSOE-figures-venv/Scripts/python.exe -m pip install matplotlib

Each figure is written as **vector PDF** and **300 dpi PNG**, with the **CSV it was plotted
from** under the same base name, so every number in every chart is checkable. `captions.tex`
holds the numbered captions.

Rules this script keeps:
- **Measured data only.** No projection, no smoothing, no interpolation across gaps. Where a
  series has no data (a frozen run stops producing rejections), the gap is left as a gap.
- **Greyscale-safe.** Series differ by line style, marker and hatch, never by colour alone.
- **Read-only on the runs.** Each database is copied with SQLite's backup API into a temporary
  directory and read there, so a live run is never locked or written to.
- **Deterministic.** Queries are ordered, no timestamp is embedded in the PDFs, and nothing
  depends on the wall clock. Re-running it reproduces the same figures.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import shutil
import sqlite3
import tempfile
from decimal import Decimal
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RUNS = {"tier 3": REPO / "data/db/phase7-t3-expected_move.sqlite",
        "tier 5": REPO / "data/db/phase7-t5-expected_move.sqlite"}
STYLE = {"tier 3": {"ls": "-", "marker": "o", "hatch": "///", "grey": "0.15"},
         "tier 5": {"ls": "--", "marker": "s", "hatch": "...", "grey": "0.55"}}
TARGET_PCT, STOP_PCT, DRAWDOWN_LIMIT = Decimal("0.03"), Decimal("0.015"), 10.0
UTC = dt.UTC

plt.rcParams.update({
    "figure.figsize": (7.0, 4.2), "figure.dpi": 100, "savefig.bbox": "tight",
    "font.size": 9, "axes.grid": True, "grid.alpha": 0.3, "grid.linewidth": 0.5,
    "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42,
})


def save(fig, name: str) -> None:
    fig.savefig(OUT / f"{name}.pdf", metadata={"CreationDate": None})
    fig.savefig(OUT / f"{name}.png", dpi=300)
    plt.close(fig)


def write_text(path: Path, text: str) -> None:
    """LF endings on every platform, so re-running reproduces the committed bytes."""
    path.write_text(text, encoding="utf-8", newline="\n")


def write_csv(name: str, header: list[str], rows: list[list]) -> None:
    with (OUT / f"{name}.csv").open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def stamp(micros: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(micros / 1e6, UTC)


def load(tmp: Path) -> dict[str, sqlite3.Connection]:
    """A consistent read-only snapshot of each run, taken with the backup API."""
    conns = {}
    for tier, live in RUNS.items():
        snap = tmp / f"{tier.replace(' ', '')}.sqlite"
        src = sqlite3.connect(f"file:{live.as_posix()}?mode=ro", uri=True)
        dst = sqlite3.connect(snap)
        with dst:
            src.backup(dst)
        src.close(); dst.close()
        c = sqlite3.connect(f"file:{snap.as_posix()}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        conns[tier] = c
    return conns


def equity(c: sqlite3.Connection) -> list[tuple[dt.datetime, float, float]]:
    return [(stamp(r["ts"]), float(r["equity"]), float(r["peak_equity"]))
            for r in c.execute("SELECT ts, equity, peak_equity FROM equity_snapshots ORDER BY ts, id")]


def trades(c: sqlite3.Connection) -> list[dict]:
    out = []
    for r in c.execute("""SELECT tr.pair, tr.opened_at, tr.closed_at, tr.outcome, tr.realised_pnl,
                                 tr.realised_pnl_pct, tr.entry_price, tr.exit_price,
                                 p.target_price, p.stop_price
                          FROM trades tr JOIN positions p ON p.position_id = tr.position_id
                          ORDER BY tr.closed_at, tr.trade_id"""):
        entry = Decimal(r["entry_price"]); exit_ = Decimal(r["exit_price"])
        barrier = Decimal(r["target_price"] if r["outcome"] == "target" else r["stop_price"])
        out.append({
            "pair": r["pair"], "opened": stamp(r["opened_at"]), "closed": stamp(r["closed_at"]),
            "hold_h": (r["closed_at"] - r["opened_at"]) / 3.6e9, "outcome": str(r["outcome"]),
            "pnl": float(r["realised_pnl"]), "net_pct": float(r["realised_pnl_pct"]) * 100,
            "barrier_pct": float((barrier - entry) / entry * 100),
            "gross_pct": float((exit_ - entry) / entry * 100),
        })
    for t in out:
        t["diff_pp"] = t["gross_pct"] - t["barrier_pct"]
    return out


def freeze(c: sqlite3.Connection) -> tuple[dt.datetime, str] | None:
    row = c.execute("SELECT created_at, reason FROM commands WHERE command = 'freeze' "
                    "ORDER BY created_at LIMIT 1").fetchone()
    return (stamp(row["created_at"]), str(row["reason"])) if row else None


def rejections(c: sqlite3.Connection) -> list[tuple[dt.datetime, str, str]]:
    return [(stamp(r["ts"]), str(r["rejected_by"]), str(r["reason_code"]))
            for r in c.execute("SELECT ts, rejected_by, reason_code FROM rejections ORDER BY ts, id")]


def week_of(when: dt.datetime) -> str:
    return (when - dt.timedelta(days=when.weekday())).strftime("%Y-%m-%d")


def bar_ticks_run(tier: str) -> int:
    """Every bar tick the process ran, from the run's own record — including ticks while frozen,
    which write no `scout_tallies` row because the opportunity chain never runs."""
    record = RUNS[tier].with_suffix(".sqlite.runrecord.jsonl")
    return sum(1 for line in record.read_text(encoding="utf-8").splitlines()
               if line.strip() and (e := json.loads(line)).get("event") == "tick" and e["bar_tick"])


# --------------------------------------------------------------------------- figures
def f1_equity(data) -> None:
    fig, ax = plt.subplots()
    rows = []
    for tier, c in data.items():
        series = equity(c); st = STYLE[tier]
        ax.plot([p[0] for p in series], [p[1] for p in series], st["ls"], color=st["grey"],
                lw=1.1, label=f"{tier} equity")
        for t in trades(c):
            ax.plot(t["closed"], next(e for ts_, e, _ in reversed(series) if ts_ <= t["closed"]),
                    st["marker"], color=st["grey"], ms=4, mfc="white", mew=0.9)
        fr = freeze(c)
        if fr:
            ax.axvline(fr[0], color=st["grey"], ls=":", lw=1.2)
            trigger = "loss streak" if "loss" in fr[1] else "drawdown"
            # staggered, and below the curves, so neither label sits on a series
            height, dx = (4720, 8) if tier == "tier 5" else (4640, -104)
            ax.annotate(f"{tier} frozen {fr[0]:%Y-%m-%d}\n({trigger})", xy=(fr[0], height),
                        xytext=(dx, 0), textcoords="offset points", fontsize=7, va="top",
                        color=st["grey"])
        rows += [[tier, ts_.isoformat(), f"{e:.6f}", f"{pk:.6f}"] for ts_, e, pk in series]
    ax.axhline(5000, color="0.7", lw=0.8, ls="-")
    ax.set_xlabel("simulated date (UTC)"); ax.set_ylabel("account equity (USD)")
    ax.legend(loc="lower left", frameon=False, fontsize=8)
    fig.autofmt_xdate()
    save(fig, "F1_equity_curves")
    write_csv("F1_equity_curves", ["run", "ts_utc", "equity_usd", "peak_equity_usd"], rows)


def f2_drawdown(data) -> None:
    c = data["tier 3"]; series = equity(c)
    xs = [p[0] for p in series]
    dd = [(pk - e) / pk * 100 if pk else 0.0 for _t, e, pk in series]
    fig, ax = plt.subplots()
    ax.plot(xs, dd, "-", color="0.15", lw=1.1, label="tier 3 drawdown from stored peak")
    ax.axhline(DRAWDOWN_LIMIT, color="0.35", ls="--", lw=1.2, label="safety.max_drawdown_pct = 10%")
    crossed = next((x for x, d in zip(xs, dd) if d >= DRAWDOWN_LIMIT), None)
    if crossed:
        ax.axvline(crossed, color="0.15", ls=":", lw=1.0)
        ax.annotate(f"limit crossed\n{crossed:%Y-%m-%d %H:%M}Z", xy=(crossed, DRAWDOWN_LIMIT),
                    xytext=(-110, 18), textcoords="offset points", fontsize=7,
                    arrowprops={"arrowstyle": "->", "lw": 0.8, "color": "0.15"})
    luna = next((t for t in trades(c) if t["pair"].startswith("LUNA")), None)
    if luna:
        ax.plot(luna["closed"], next(d for x, d in zip(xs, dd) if x >= luna["closed"]), "v",
                color="0.15", ms=6, mfc="white")
        ax.annotate("LUNA/USD stop\n-6.12% in 1 minute", xy=(luna["closed"], 6.0),
                    xytext=(-96, -26), textcoords="offset points", fontsize=7,
                    arrowprops={"arrowstyle": "->", "lw": 0.8, "color": "0.15"})
    ax.set_xlabel("simulated date (UTC)"); ax.set_ylabel("drawdown from stored peak (%)")
    ax.legend(loc="upper left", frameon=False, fontsize=8)
    fig.autofmt_xdate()
    save(fig, "F2_tier3_drawdown")
    write_csv("F2_tier3_drawdown", ["ts_utc", "equity_usd", "peak_equity_usd", "drawdown_pct"],
              [[t.isoformat(), f"{e:.6f}", f"{pk:.6f}", f"{d:.4f}"] for (t, e, pk), d in zip(series, dd)])


def f3_per_trade(data) -> None:
    rows, labels, vals, hatches, edges = [], [], [], [], []
    for tier, c in data.items():
        for i, t in enumerate(trades(c), 1):
            labels.append(f"{tier.split()[1]}·{i} {t['pair'].split('/')[0]}")
            vals.append(t["pnl"]); hatches.append("" if t["outcome"] == "target" else "///")
            edges.append(STYLE[tier]["grey"])
            rows.append([tier, i, t["pair"], t["closed"].isoformat(), t["outcome"],
                         f"{t['pnl']:.2f}", f"{t['net_pct']:.4f}", f"{t['hold_h']:.2f}"])
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    bars = ax.bar(range(len(vals)), vals, color="white", edgecolor=edges, linewidth=1.0)
    for b, h in zip(bars, hatches):
        b.set_hatch(h)
    ax.axhline(0, color="0.2", lw=0.8)
    ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, rotation=90, fontsize=6.5)
    ax.set_ylabel("realised PnL (USD, net of fees)")
    worst = min(range(len(vals)), key=lambda i: vals[i])
    ax.annotate("LUNA/USD -200.71\n(-6.12% in 1 minute)", xy=(worst, vals[worst]),
                xytext=(10, 18), textcoords="offset points", fontsize=7,
                arrowprops={"arrowstyle": "->", "lw": 0.8, "color": "0.15"})
    ax.legend(handles=[Line2D([], [], marker="s", ls="", mfc="white", mec="0.15", label="target exit"),
                       Line2D([], [], marker="s", ls="", mfc="white", mec="0.15", label="stop exit (hatched)"),
                       Line2D([], [], marker="s", ls="", mfc="white", mec="0.55", label="tier 5 (lighter edge)")],
              loc="lower left", frameon=False, fontsize=7.5)
    save(fig, "F3_per_trade_pnl")
    write_csv("F3_per_trade_pnl",
              ["run", "trade_index", "pair", "closed_utc", "outcome", "pnl_usd", "net_pct", "hold_hours"], rows)


def f4_barrier_vs_realised(data) -> None:
    fig, ax = plt.subplots(figsize=(5.4, 5.0))
    rows = []
    for tier, c in data.items():
        st = STYLE[tier]
        for t in trades(c):
            ax.plot(t["barrier_pct"], t["gross_pct"], st["marker"], ms=7,
                    mfc="white" if t["outcome"] == "stop" else st["grey"], mec=st["grey"], mew=1.1)
            rows.append([tier, t["pair"], t["closed"].isoformat(), t["outcome"],
                         f"{t['barrier_pct']:.4f}", f"{t['gross_pct']:.4f}", f"{t['diff_pp']:.4f}",
                         f"{t['net_pct']:.4f}"])
    # Several stops share the barrier exactly (-1.5%), so points overlap. The count is
    # annotated rather than jittered: a jitter would put a value on the chart that no trade had.
    for tier, c in data.items():
        for outcome, barrier in (("stop", -1.5), ("target", 3.0)):
            n = sum(1 for t in trades(c) if t["outcome"] == outcome)
            if n > 1:
                ax.annotate(f"{n} {tier} {outcome}s\n(overlapping)",
                            xy=(barrier, -1.7 if outcome == "stop" else 3.0),
                            xytext=(14, -26 if outcome == "stop" else -30),
                            textcoords="offset points", fontsize=6.5, color=STYLE[tier]["grey"])
    lim = [-6.5, 4.0]
    ax.plot(lim, lim, "-", color="0.6", lw=0.9, label="realised = barrier (45°)")
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("barrier the trade was aiming at (%, gross)")
    ax.set_ylabel("realised return at exit (%, gross)")
    ax.annotate("LUNA/USD: stop at -1.5%,\nrealised -5.54%", xy=(-1.5, -5.54), xytext=(-6.2, -3.0),
                fontsize=7, arrowprops={"arrowstyle": "->", "lw": 0.8, "color": "0.15"})
    ax.legend(handles=[Line2D([], [], color="0.6", lw=0.9, label="realised = barrier (45°)"),
                       Line2D([], [], marker="o", ls="", mfc="0.15", mec="0.15", label="tier 3 target"),
                       Line2D([], [], marker="o", ls="", mfc="white", mec="0.15", label="tier 3 stop"),
                       Line2D([], [], marker="s", ls="", mfc="white", mec="0.55", label="tier 5 stop")],
              loc="upper left", frameon=False, fontsize=7.5)
    save(fig, "F4_barrier_vs_realised")
    write_csv("F4_barrier_vs_realised",
              ["run", "pair", "closed_utc", "outcome", "barrier_pct_gross", "realised_pct_gross",
               "difference_pp", "net_pct_after_fees"], rows)


def f5_funnel(data) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    rows = []
    stages = ["bar ticks run (whole window)", "bar ticks with engine 7 running (not frozen)",
              "ticks with a candidate", "candidates refused (cost gate)",
              "approvals", "entry orders placed", "entries filled", "trades closed"]
    for n, (tier, c) in enumerate(data.items()):
        one = lambda s: c.execute(s).fetchone()[0]
        vals = [bar_ticks_run(tier),
                one("SELECT count(*) FROM scout_tallies"),
                one("SELECT count(*) FROM scout_tallies WHERE candidate IS NOT NULL"),
                one("SELECT count(*) FROM rejections"),
                one("SELECT count(*) FROM approvals"),
                one("SELECT count(*) FROM orders WHERE intent = 'entry'"),
                one("SELECT count(*) FROM orders WHERE intent = 'entry' AND status = 'filled'"),
                one("SELECT count(*) FROM trades")]
        ys = [i + (0.2 if n else -0.2) for i in range(len(stages))]
        ax.barh(ys, vals, height=0.38, color="white", edgecolor=STYLE[tier]["grey"],
                hatch=STYLE[tier]["hatch"], linewidth=1.0, label=tier)
        for y, v in zip(ys, vals):
            ax.annotate(f"{v:,}", xy=(v, y), xytext=(4, -2.5), textcoords="offset points", fontsize=7)
        rows += [[tier, s, v] for s, v in zip(stages, vals)]
    ax.set_yticks(range(len(stages))); ax.set_yticklabels(stages, fontsize=8)
    ax.invert_yaxis(); ax.set_xscale("log"); ax.set_xlabel("count (log scale)")
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    save(fig, "F5_decision_funnel")
    write_csv("F5_decision_funnel", ["run", "stage", "count"], rows)


def f6_rejections_over_time(data) -> None:
    fig, ax = plt.subplots()
    rows = []
    for tier, c in data.items():
        st = STYLE[tier]
        per_week: dict[str, dict[str, int]] = {}
        for when, by, code in rejections(c):
            per_week.setdefault(week_of(when), {}).setdefault(f"{by}:{code}", 0)
            per_week[week_of(when)][f"{by}:{code}"] += 1
        weeks = sorted(per_week)
        xs = [dt.datetime.fromisoformat(w).replace(tzinfo=UTC) for w in weeks]
        totals = [sum(per_week[w].values()) for w in weeks]
        ax.plot(xs, totals, st["ls"], marker=st["marker"], ms=4, color=st["grey"], lw=1.1,
                mfc="white", label=f"{tier}: cost gate refusals per week")
        for w in weeks:
            for key, n in sorted(per_week[w].items()):
                rows.append([tier, w, key, n])
    ax.set_xlabel("simulated week (UTC, week beginning)")
    ax.set_ylabel("candidates refused per week")
    ax.annotate("no bar has a second refusing gate:\nevery rejection in both runs is engine 10 `cost`",
                xy=(0.02, 0.92), xycoords="axes fraction", fontsize=7.5, va="top")
    ax.annotate("gaps: the run is frozen,\nso no candidate is examined", xy=(0.02, 0.72),
                xycoords="axes fraction", fontsize=7.5, va="top")
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    fig.autofmt_xdate()
    save(fig, "F6_rejections_over_time")
    write_csv("F6_rejections_over_time", ["run", "week_beginning_utc", "refusing_gate_and_reason", "count"], rows)


def f7_trading_vs_frozen(data) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.0), sharex=True)
    rows = []
    for ax, (tier, c) in zip(axes, data.items()):
        st = STYLE[tier]
        ts_rows = [stamp(r["ts"]) for r in c.execute("SELECT ts FROM scout_tallies ORDER BY ts")]
        first, last = ts_rows[0], ts_rows[-1]
        fr = freeze(c)
        end = stamp(c.execute("SELECT max(ts) FROM equity_snapshots").fetchone()[0])
        if fr:
            ax.axvspan(fr[0], end, facecolor="0.88", edgecolor="none")
            ax.annotate(f"frozen from {fr[0]:%Y-%m-%d}\n({'loss streak' if 'loss' in fr[1] else 'drawdown'})",
                        xy=(fr[0], 0.72), xycoords=("data", "axes fraction"), fontsize=7.5,
                        xytext=(6, 0), textcoords="offset points")
        for t in trades(c):
            ax.plot([t["opened"], t["closed"]], [1, 1], "-", color=st["grey"], lw=3, solid_capstyle="butt")
            ax.plot(t["closed"], 1, st["marker"], ms=5, color=st["grey"],
                    mfc="white" if t["outcome"] == "stop" else st["grey"])
            rows.append([tier, t["pair"], t["opened"].isoformat(), t["closed"].isoformat(),
                         t["outcome"], f"{t['hold_h']:.2f}"])
        exposed = sum(t["hold_h"] for t in trades(c))
        span_h = (end - first).total_seconds() / 3600
        ax.set_yticks([]); ax.set_ylim(0.6, 1.4)
        ax.set_title(f"{tier}: {len(trades(c))} trades, {exposed:.1f} h exposed of {span_h:.0f} h "
                     f"simulated ({exposed/span_h*100:.1f}%)", fontsize=8.5, loc="left")
        rows.append([tier, "TOTAL", first.isoformat(), end.isoformat(), "exposed_hours", f"{exposed:.2f}"])
    axes[-1].set_xlabel("simulated date (UTC)")
    fig.autofmt_xdate()
    save(fig, "F7_trading_vs_frozen")
    write_csv("F7_trading_vs_frozen", ["run", "pair", "opened_utc", "closed_utc", "outcome", "hold_hours"], rows)


CHAIN = {
    "guard (every tick, every mode)": ["1 exchange", "2 market_data_recorder", "3 market_sensor",
                                       "4 data_guard [gate]", "17 safety [gate]"],
    "opportunity (bar ticks, while running and unblocked)":
        ["5 feature", "6 macro_context", "7 scout [gate, ranks]", "12 regime", "13 anomaly [gate]",
         "8 prediction", "9 order_book", "10 cost [gate]", "11 risk [gate]", "14 adaptive_router",
         "15 skeptic [gate]", "16 decision [gate]", "18 execution"],
    "manage (every tick)": ["21 position_manager", "22 exit", "19 memory (single writer)"],
}


def f8_chain(data) -> None:
    """The chain as it ran. Drawn here rather than rendered from Mermaid so that the figure is
    reproducible offline; the Mermaid source is committed beside it as F8_engine_chain.mmd."""
    fig, ax = plt.subplots(figsize=(7.6, 8.2))
    ax.set_axis_off(); ax.set_xlim(0, 10.4); ax.set_ylim(-4.8, 26.0)
    y = 23.2
    for band, engines in CHAIN.items():
        top = y + 0.55
        ax.text(0.35, y + 0.95, band, fontsize=8.5, fontweight="bold")
        for name in engines:
            y -= 1.02
            gate = "[gate]" in name
            ax.add_patch(Rectangle((0.6, y - 0.34), 4.6, 0.68, fill=False, ec="0.15",
                                   lw=1.3 if gate else 0.8))
            ax.text(0.8, y - 0.09, name, fontsize=8)
            if gate:
                ax.annotate("refusal stops the chain here", xy=(5.25, y), xytext=(5.75, y),
                            fontsize=7, va="center",
                            arrowprops={"arrowstyle": "->", "lw": 0.7, "color": "0.3"})
        ax.add_patch(Rectangle((0.2, y - 0.62), 5.4, top - y + 0.6, fill=False, ec="0.5",
                               lw=0.8, ls=":"))
        y -= 2.3  # clear space between a band's box and the next band's title
    ax.text(5.75, 2.4, "engine 19 records, every tick:\nequity snapshot; positions, orders, trades;\n"
                       "one block_records row per blocker;\none rejections row per refused candidate\n"
                       "with every gate's verdict (details);\none approvals row per placed entry;\n"
                       "one scout_tallies row per tick engine 7 ran;\na SHAP file per explained decision",
            fontsize=7.5, va="top",
            bbox={"boxstyle": "round,pad=0.4", "fc": "white", "ec": "0.4", "lw": 0.8})
    ax.annotate("", xy=(9.9, 23.0), xytext=(9.9, -3.8),
                arrowprops={"arrowstyle": "-|>", "lw": 0.9, "color": "0.45"})
    ax.text(9.72, 11.0, "one tick, top to bottom", fontsize=7.5, rotation=90,
            va="center", ha="center", color="0.35")
    save(fig, "F8_engine_chain")
    write_text(OUT / "F8_engine_chain.mmd",
        "flowchart TD\n"
        "  %% Phase 7: the chain as it ran. Source for F8; the committed PDF/PNG is drawn by\n"
        "  %% make_phase7_figures.py so the figure reproduces offline.\n"
        "  subgraph GUARD[guard - every tick, every mode]\n"
        "    E1[1 exchange] --> E2[2 market_data_recorder] --> E3[3 market_sensor]\n"
        "    E3 --> E4{{4 data_guard - gate}} --> E17{{17 safety - gate}}\n"
        "  end\n"
        "  subgraph OPP[opportunity - bar ticks, while running and unblocked]\n"
        "    E5[5 feature] --> E6[6 macro_context] --> E7{{7 scout - gate, ranks by expected move}}\n"
        "    E7 --> E12[12 regime] --> E13{{13 anomaly - gate}} --> E8[8 prediction] --> E9[9 order_book]\n"
        "    E9 --> E10{{10 cost - gate}} --> E11{{11 risk - gate}} --> E14[14 adaptive_router]\n"
        "    E14 --> E15{{15 skeptic - gate}} --> E16{{16 decision - gate}} --> E18[18 execution]\n"
        "  end\n"
        "  subgraph MANAGE[manage - every tick]\n"
        "    E21[21 position_manager] --> E22[22 exit] --> E19[(19 memory - single writer)]\n"
        "  end\n"
        "  E17 -->|not blocked and running| E5\n"
        "  E17 -->|blocked or frozen| E21\n"
        "  E18 --> E21\n"
        "  E10 -.->|refused: chain stops, later gates never run| E19\n"
        "  E19 --- NOTE[/equity; positions, orders, trades; block_records per blocker;\\n"
        "  rejections with every gate's verdict; approvals; scout_tallies per tick;\\n"
        "  one SHAP file per explained decision/]\n")


CAPTIONS = [
    ("F1_equity_curves", "Account equity through the simulated window, both fee tiers, from 5,000 USD. "
     "Markers show each trade's close; the dotted verticals mark the protective freeze on each run, "
     "labelled with its date and trigger. Replay of 2024-10-05 to 2025-01-04, folds 392-404."),
    ("F2_tier3_drawdown", "Tier 3's drawdown from its stored peak equity, against the 10\\% limit "
     "(\\texttt{safety.max\\_drawdown\\_pct}). The LUNA/USD stop of 9 December, which realised -6.12\\% on a "
     "one-minute hold, is marked; the limit is crossed on 19 December and the run freezes."),
    ("F3_per_trade_pnl", "Realised profit and loss per closed trade, net of fees, in time order. "
     "Hatched bars are stop exits, plain bars target exits; lighter edges are tier 5. "
     "The LUNA/USD stop is 2.5 times the size of any other loss."),
    ("F4_barrier_vs_realised", "Realised return at exit against the barrier the trade was aiming at, "
     "per closed trade, both tiers, gross of fees. Points on the 45-degree line realised exactly their "
     "barrier. Every stop lies below the line; the exit rule caps gains at the target but does not cap "
     "losses at the stop."),
    ("F5_decision_funnel", "The decision funnel for both runs, log scale: bar ticks run, ticks where "
     "engine 7 published a candidate, candidates refused, approvals, entry orders, fills and closed "
     "trades. Every refusal in both runs came from engine 10 \\texttt{cost}."),
    ("F6_rejections_over_time", "Candidates refused per simulated week, by refusing gate and reason. "
     "Gaps are weeks in which the run was frozen and examined no candidate."),
    ("F7_trading_vs_frozen", "When each run could trade. Horizontal bars are open positions; the shaded "
     "region is the frozen remainder of the window after the protective breaker fired."),
    ("F8_engine_chain", "The engine chain as it ran: guard, opportunity and manage, with the gates "
     "marked, the point at which a refusal stops the chain, and what engine 19 records on every tick."),
]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        data = load(Path(tmpdir))
        for fn in (f1_equity, f2_drawdown, f3_per_trade, f4_barrier_vs_realised,
                   f5_funnel, f6_rejections_over_time, f7_trading_vs_frozen, f8_chain):
            fn(data)
        summary = {}
        for tier, c in data.items():
            one = lambda s: c.execute(s).fetchone()[0]
            fr = freeze(c)
            ts_rows = trades(c)
            summary[tier] = {
                "bar_ticks": one("SELECT count(*) FROM scout_tallies"),
                "candidate_ticks": one("SELECT count(*) FROM scout_tallies WHERE candidate IS NOT NULL"),
                "rejections": one("SELECT count(*) FROM rejections"),
                "approvals": one("SELECT count(*) FROM approvals"),
                "entries_filled": one("SELECT count(*) FROM orders WHERE intent = 'entry' AND status = 'filled'"),
                "trades": len(ts_rows),
                "block_records": one("SELECT count(*) FROM block_records"),
                "final_equity": float(one("SELECT equity FROM equity_snapshots ORDER BY ts DESC, id DESC LIMIT 1")),
                "freeze": None if not fr else {"at": fr[0].isoformat(), "reason": fr[1]},
                "stops": sum(1 for t in ts_rows if t["outcome"] == "stop"),
                "targets": sum(1 for t in ts_rows if t["outcome"] == "target"),
                "worst_overshoot_pp": min((t["diff_pp"] for t in ts_rows), default=None),
            }
            c.close()
        write_text(OUT / "summary.json", json.dumps(summary, indent=1, sort_keys=True) + "\n")
        write_text(OUT / "captions.tex",
            "% Captions for the Phase 7 figures. Generated by make_phase7_figures.py.\n" +
            "".join(f"\\caption{{{text}}}\n%% file: {name}.pdf / {name}.png / {name}.csv\n\n"
                    for name, text in CAPTIONS))
    print("wrote:", ", ".join(sorted(p.name for p in OUT.iterdir() if p.suffix in {".pdf", ".png", ".csv", ".mmd", ".tex", ".json"})))


if __name__ == "__main__":
    main()
