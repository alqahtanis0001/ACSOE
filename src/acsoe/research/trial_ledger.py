"""The trial ledger: every configuration ever evaluated against the out-of-sample data. Spec 139.

Ruled 2026-09-19 (R9): every configuration ever evaluated against the out-of-sample data counts as
a trial, **listed one by one, not summarised**, and the count errs high. The promotion bar
(`modelling/promotion.py`) widens its interval by Bonferroni over this count, so an overstated
count makes the haircut harsher and a result harder to claim, which is the direction the ruling
chose.

**The ledger is built from the committed outputs by this module and never typed by hand.**
``python -m acsoe.research.trial_ledger`` rewrites `docs/dataset/phase-7-trial-ledger.json` and
its `.md` beside it. A test rebuilds both from the committed outputs and requires them to be
byte-identical to what is committed, so a hand edit is a red test.

## The rule, and the judgements it made

A **trial** is a *selection* (a rule deciding which rows, bars or calls would be traded) evaluated
on the out-of-sample data and reported with any statistic of what it selected: a count, a share,
a target rate or a return. **Each reported (selection, sample) is one row.** So:

- a funnel line counts once per stage it reports, because "every gate up to the DI" is a
  different selection from "every gate up to the cost gate";
- a sub-window (a year, a six-month slice) of a selection is a separate row;
- a selection and its complement (the skeptic's survivors and the calls it vetoed; the DI's kept
  and refused rows) are two rows, because each was reported with its own outcome;
- **the same selection reported twice, in two files or two lines, counts twice.** Nothing on disk
  proves the two reports were one computation, and the ruling says to count two where unclear.

Excluded, and listed in the ledger with the reason: anything that selects nothing (timings,
memory, a fit of spread on the 2026 recording, an identity or reproduction check of an artefact,
a tick-grid comparison, a fold construction), the permutation "no-skill" bands (a shuffled score is
a null distribution, not a configuration anyone could adopt), and outputs computed on data other
than the walk-forward's out-of-sample rows (the two-pair constructed series of 2026-09-13).

Every text output is read **line by line, and a line that is neither a counted cell nor a
recognised descriptive line raises**, so a new cell in an output can never be skipped silently.
A test plants one extra cell in a copy of an output and requires the count to rise by one.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

__all__ = [
    "LEDGER_JSON",
    "LEDGER_MD",
    "Exclusion",
    "Ledger",
    "LedgerError",
    "Trial",
    "build_ledger",
    "main",
    "render_json",
    "render_markdown",
]

DATASET: Final = Path("docs") / "dataset"
RECON: Final = DATASET / "phase-7-recon-2026-09-19" / "outputs"
LEDGER_JSON: Final = DATASET / "phase-7-trial-ledger.json"
LEDGER_MD: Final = DATASET / "phase-7-trial-ledger.md"

#: The four runs spec 143 launches (R3 tiers, R4 two rankings). They are trials the moment they
#: run, and they are counted before they do, because the count is fixed before launch.
PHASE_7_TIERS: Final = (3, 5)
PHASE_7_RANKINGS: Final = ("expected_move", "alphabetical")

#: Seen on disk by c-eval on 2026-09-19 and in no committed output: `models/` is gitignored. The
#: three fold models of a three-pair (ETHUSD, SOLUSD, XBTUSD) smoke training run, each evaluated
#: on its own test week of the archive. Whether that counts as "the out-of-sample data" is
#: unclear, so under the rule they count. Named here rather than read from `models/` so that a
#: fresh clone rebuilds the same ledger.
SMOKE_RUN_FOLD_MODELS: Final = (
    "train-20260913T100124-067b2b9d-f0",
    "train-20260913T100124-067b2b9d-f1",
    "train-20260913T100124-067b2b9d-f2",
)

RULE: Final = (
    "A trial is a selection (a rule deciding which rows, bars or calls would be traded) evaluated "
    "on the out-of-sample data and reported with any statistic of what it selected. Each reported "
    "(selection, sample) is one row. Where it is unclear whether two reports are one trial or two, "
    "they are two. The count errs high on purpose: a larger count makes the Bonferroni haircut "
    "harsher and a result harder to claim."
)


class LedgerError(ValueError):
    """An output this module cannot account for line by line, or a file it expected and lacks."""


@dataclass(frozen=True, slots=True)
class Trial:
    family: str
    source: str
    locator: str
    configuration: str
    statistic: str


@dataclass(frozen=True, slots=True)
class Exclusion:
    source: str
    locator: str
    reason: str


@dataclass(frozen=True, slots=True)
class Ledger:
    trials: tuple[Trial, ...]
    excluded: tuple[Exclusion, ...]
    judgements: tuple[str, ...]

    @property
    def trial_count(self) -> int:
        return len(self.trials)


# --------------------------------------------------------------------------- #
# Line-by-line reading of the text outputs
# --------------------------------------------------------------------------- #

#: A cell pattern's handler returns ``(configuration, statistic)`` pairs, one per trial.
Cells = Callable[[re.Match[str], dict[str, str]], list[tuple[str, str]]]


@dataclass(frozen=True, slots=True)
class _Pattern:
    regex: re.Pattern[str]
    cells: Cells | None = None  # None: a recognised descriptive line, counted as nothing
    context: Callable[[re.Match[str], dict[str, str]], None] | None = None


def _p(
    pattern: str,
    cells: Cells | None = None,
    context: Callable[[re.Match[str], dict[str, str]], None] | None = None,
) -> _Pattern:
    return _Pattern(re.compile(pattern), cells, context)


def _read_lines(
    root: Path,
    relative: Path,
    lines: Sequence[str],
    patterns: Sequence[_Pattern],
    *,
    family: str,
    first_line: int = 1,
) -> list[Trial]:
    """Classify every non-blank line, or raise. Returns one `Trial` per cell."""
    del root
    trials: list[Trial] = []
    context: dict[str, str] = {}
    for offset, line in enumerate(lines):
        text = line.rstrip("\r\n")
        if not text.strip():
            continue
        number = first_line + offset
        for pattern in patterns:
            match = pattern.regex.search(text)
            if match is None:
                continue
            if pattern.context is not None:
                pattern.context(match, context)
            if pattern.cells is not None:
                for configuration, statistic in pattern.cells(match, context):
                    trials.append(
                        Trial(
                            family=family,
                            source=relative.as_posix(),
                            locator=f"line {number}",
                            configuration=configuration,
                            statistic=statistic,
                        )
                    )
            break
        else:
            raise LedgerError(
                f"{relative.as_posix()} line {number} is neither a counted cell nor a recognised "
                f"descriptive line: {text!r}. Classify it before the ledger can be built; an "
                "unread line is how a trial goes uncounted."
            )
    return trials


def _text(root: Path, relative: Path) -> list[str]:
    path = root / relative
    if not path.is_file():
        raise LedgerError(f"{relative.as_posix()} is not a file; the ledger reads it")
    return path.read_bytes().decode("utf-8").splitlines()


def _stages(prefix: str, names: Sequence[str], values: Sequence[str]) -> list[tuple[str, str]]:
    return [
        (f"{prefix}; gates through {name}", f"{value} pass")
        for name, value in zip(names, values, strict=True)
    ]


# ---- q_funnel.out ------------------------------------------------------------


def _funnel_window(match: re.Match[str], context: dict[str, str]) -> None:
    context["window"] = match.group(1)


def _funnel_config(match: re.Match[str], context: dict[str, str]) -> None:
    context["ranking"] = match.group(1).strip()
    context["friction"] = match.group(2)


def _funnel_stages(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    prefix = (
        f"q_funnel: {context['window']}, {match.group(1).strip()}, total friction "
        f"{match.group(2)}%, flat 10 bps where the arm says so"
    )
    return _stages(prefix, ("anomaly", "DI", "cost", "risk"), match.groups()[3:7])


def _funnel_skeptic(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    kind = "uncapped" if match.group(1) == "unc" else "capped"
    return [
        (
            (f"q_funnel: {context['window']}, {context['ranking']}, total friction "
            f"{context['friction']}%, {kind} skeptic veto at {match.group(2)}, one per pair, "
            "at most three open"),
            f"{match.group(3)} trades",
        )
    ]


_FUNNEL: Final = (
    _p(r"^window bars \d+; candidate pairs"),
    _p(r"^=== (\d+m) \(\d+ folds\) ===$", context=_funnel_window),
    _p(
        r"^(alphabetical|log_return_4 asc)\s+friction ([\d.]+)% \| bars (\d+) -> anomaly (\d+) "
        r"-> DI (\d+) -> cost (\d+) -> risk (\d+)$",
        cells=_funnel_stages,
        context=_funnel_config,
    ),
    _p(r"^\s+(unc|cap)@([\d.]+): trades\s+(\d+)", cells=_funnel_skeptic),
)


# ---- q_window.out ------------------------------------------------------------


def _window_ab(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    head = (
        f"q_window: alphabetical, 18m, tier 3 reference fees, spread {match.group(1)} bps "
        f"(total friction {match.group(2)}%)"
    )
    return [
        (f"{head}; (a) clears the cost bar", f"{match.group(3)} bars"),
        (f"{head}; (b) and one position per pair", f"{match.group(4)} trades"),
    ]


def _window_ab_detail(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [
        (
            (f"q_window: alphabetical, 18m, upper bound arm ({match.group(1)}), reported again "
            "with its return"),
            f"n {match.group(2)}",
        )
    ]


def _window_frictions(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [
        (f"q_window: alphabetical, 18m, clears the cost bar at total friction {friction}%",
         f"{count} bars")
        for friction, count in re.findall(r"([\d.]+)%:(\d+)", match.group(0))
    ]


def _window_max(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [
        ("q_window: 18m, maximum expected move over any pair", f"{match.group(1)}%"),
        ("q_window: 18m, maximum expected move of the alphabetical candidate",
         f"{match.group(2)}%"),
    ]


def _window_strict(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    prefix = f"q_window: alphabetical, 18m, tier 3 reference fees, spread {match.group(1)} bps"
    names = ("cost", "complete vector", "anomaly", "DI", "uncapped skeptic", "one per pair")
    return _stages(prefix, names, match.groups()[1:7])


def _window_check(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [("q_window: 2024 reproduction of the alphabetical 1.5% bar count", match.group(1))]


_WINDOW: Final = (
    _p(r"^Q1 fold 404 test window"),
    _p(r"^Q2 1\.5 years"),
    _p(r"^\s+fold-to-fold test_start steps"),
    _p(r"^\s+fold \d+: test "),
    _p(r"^\s+span used below"),
    _p(r"^Q3 folds in span"),
    _p(r"^\s+2023 part:"),
    _p(r"^\s+2024\+:"),
    _p(r"^\s+study join:"),
    _p(r"^\s+alphabetical candidate pairs"),
    _p(r"^CHECK 2024 reproduction: (\d+)", cells=_window_check),
    _p(r"^Q5 UPPER BOUND"),
    _p(r"^\s+\(a\) bars clearing = "),
    _p(
        r"^\s+tier 3 ref fees, spread\s+(\d+) bps: friction ([\d.]+)%, bar [\d.]+% \| \(a\) (\d+) "
        r"\| \(b\) (\d+)$",
        cells=_window_ab,
    ),
    _p(r"^\s+\((a|b)\) n (\d+); realised", cells=_window_ab_detail),
    _p(r"^\s+The bound depends on friction alone"),
    _p(r"^\s+(?:[\d.]+%:\d+\s*)+$", cells=_window_frictions),
    _p(r"^\s+max expected_move_pct over the span, any pair ([\d.]+)%; alphabetical candidate "
       r"([\d.]+)%$", cells=_window_max),
    _p(r"^Q5 STRICTER"),
    _p(
        r"^\s+spread\s+(\d+) bps: clear (\d+) -> complete vector (\d+) -> anomaly (\d+) -> DI "
        r"(\d+) -> skeptic\(uncapped\) (\d+) -> one-per-pair (\d+)",
        cells=_window_strict,
    ),
)


# ---- the 2026-09-18 logs -----------------------------------------------------


def _em_bar(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [(f"q_em: all folds, any pair, expected move above {match.group(1)}%",
             f"{match.group(2)} rows")]


_EM: Final = (
    _p(r"^rows \d+ null expected_move"),
    _p(r"^rows with an expected move"),
    _p(r"^expected_move max"),
    _p(r"^p_target max"),
    _p(r"^2025 rows"),
    _p(r"^bar ([\d.]+)%: rows above (\d+)", cells=_em_bar),
)


def _bars_any(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [(f"q_bars: all folds, the best pair on each bar clears {match.group(1)}%",
             f"{match.group(2)} bars")]


def _bars_alpha(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [(f"q_bars: all folds, the alphabetical candidate clears {match.group(1)}%",
             f"{match.group(2)} bars")]


_BARS: Final = (
    _p(r"^rows \d+ decision bars"),
    _p(r"^pairs per bar:"),
    _p(r"^span \d+ \d+$"),
    _p(r"^bars where ANY pair clears ([\d.]+)% \(best-case ranking\): (\d+)", cells=_bars_any),
    _p(r"^bars where the alphabetically first pair clears ([\d.]+)% \(engine 7 today\): (\d+)",
       cells=_bars_alpha),
)


def _capped_fold(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [
        (f"q_capped: fold {match.group(1)} BUY calls, capped skeptic veto at 0.5",
         f"veto share {match.group(2)}"),
        (f"q_capped: fold {match.group(1)} BUY calls, uncapped skeptic veto at 0.5",
         f"veto share {match.group(3)}"),
    ]


_CAPPED_LOG: Final = (
    _p(r"^fold (\d+): capped rows \d+ vs uncapped manifest \d+; BUY calls \d+; veto@0\.5 "
       r"capped ([\d.]+) uncapped ([\d.]+);", cells=_capped_fold),
)


# ---- the transcribed terminal outputs ---------------------------------------


def _year_cells(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [(f"q_year: final 365 days, {match.group(1)} clears 1.5%", f"{match.group(2)} bars")]


def _net_cells(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [
        (
            (f"q_net: {match.group(1)}, alphabetical candidate clears 1.5%, spread "
            f"{match.group(2)} bps"),
            f"{match.group(3)} trades",
        )
    ]


def _hold_cells(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [
        (
            f"q_hold: alphabetical, 18m, total friction {match.group(1)}%, one position per pair",
            f"{match.group(2)} trades",
        )
    ]


def _compare_cells(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [
        (f"q_capped_compare: 18m BUY calls, {match.group(1)} skeptic veto at {match.group(2)}",
         f"{match.group(3)} survive")
    ]


def _overlap_cells(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    return [("q_capped_compare: 18m BUY calls surviving both skeptics at 0.5",
             f"{match.group(1)} survive")]


def _picks_cells(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    head = (
        f"q_picks: log_return_4 asc, flat 10 bps, total friction {match.group(1)}%, "
        f"{match.group(2)}m"
    )
    return [
        (f"{head}; every trade", f"{match.group(3)} trades"),
        (f"{head}; trades on a recorded pair", f"{match.group(4)} trades"),
        (f"{head}; trades on an unrecorded pair", "net reported"),
    ]


def _bucket_ranking(match: re.Match[str], context: dict[str, str]) -> None:
    context["ranking"] = match.group(1)


def _bucket_cells(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    prefix = (
        f"q_bucket: {context['ranking']}, fees {match.group(1)}%, declared bucket spread and "
        f"slippage, {match.group(2)}m"
    )
    return _stages(
        prefix, ("anomaly", "DI", "cost", "risk", "capped skeptic at 0.50"), match.groups()[2:7]
    )


def _emrank_cells(match: re.Match[str], context: dict[str, str]) -> list[tuple[str, str]]:
    del context
    prefix = (
        f"q_emrank: ranked by {match.group(2)}, fees {match.group(1)}%, declared bucket spread "
        f"and slippage, {match.group(3)}m"
    )
    return [
        (f"{prefix}; clears the cost gate", f"{match.group(4)} bars"),
        (f"{prefix}; capped skeptic at 0.50, one per pair, at most three open",
         f"{match.group(5)} trades"),
    ]


#: Each section of the transcribed file, by its title line: the patterns that read it, or the
#: reason it counts nothing. Every title must be here, so a new section raises.
_TRANSCRIBED: Final[Mapping[str, tuple[_Pattern, ...] | str]] = {
    "2026-09-18_q_year.py": (
        _p(r"^window "),
        _p(r"^folds \d+ min fold"),
        _p(r"^rows \d+ decision bars"),
        _p(r"^pairs per bar:"),
        _p(r"^(alphabetical-candidate|any-pair) bars clearing [^:]+: (\d+)$", cells=_year_cells),
    ),
    "2026-09-18_q_net.py": (
        _p(r"^return_pct sample"),
        _p(r"^(all years|2024), alphabetical candidate, spread (\d+) bps: (\d+) clear;",
           cells=_net_cells),
    ),
    "q_hold.py": (_p(r"^friction ([\d.]+)%: trades\s+(\d+);", cells=_hold_cells),),
    "q_spread_agg.py": "measures spread on the 2026 recording; selects no trade",
    "q_spread_fit.py": "fits a spread model on the 2026 recording; selects no trade",
    "q_spread_extrap.py": "backcasts spread levels for five pairs; selects no trade",
    "q_depth.py": "measures depth on the 2026 recording; selects no trade",
    "q_capped.py validate 20,40": (
        "checks the capped-skeptic replication reproduces two saved skeptics exactly; an "
        "identity check, not a selection"
    ),
    "q_capped_compare.py": (
        _p(r"^BUY calls \d+ base target rate"),
        _p(r"^p_(uncapped|capped) ([\d.]+) survive (\d+)", cells=_compare_cells),
        _p(r"^overlap of survivors at 0\.5: (\d+)$", cells=_overlap_cells),
        _p(r"^corr "),
    ),
    "q_picks.py": (
        _p(r"^friction ([\d.]+)% (\d+)m: trades (\d+), of which on a recorded pair (\d+);",
           cells=_picks_cells),
        _p(r"^\s+top pairs:"),
    ),
    "q_bucket.py": (
        _p(r"^recording spans"),
        _p(r"^\s+(<\$10k|\$10k-100k|\$100k-1M|\$1M-10M):"),
        _p(r"^(alphabetical|log_return_4 asc): candidate buckets", context=_bucket_ranking),
        _p(
            r"^\s+fees ([\d.]+)% (\d+)m: bars \d+ -> anomaly (\d+) -> DI (\d+) -> cost (\d+) -> "
            r"risk (\d+) -> skeptic\(capped \.50\) (\d+)",
            cells=_bucket_cells,
        ),
    ),
    "q_emrank.py": (
        _p(
            r"^fees ([\d.]+)% (expected_move|net_margin)\s+(\d+)m: clear cost\s+(\d+) -> "
            r"trades\s+(\d+)",
            cells=_emrank_cells,
        ),
    ),
    "q_di_rebuild.py 404,360,326": (
        "rebuilds three DI references and checks their identity; selects no trade"
    ),
    "q_timing.py": "times the engines; selects no trade",
    "q_rank_timing.py": "times the ranking; selects no trade",
    "probe_load.py 404": "probes artefact loading and memory; selects no trade",
}

_SECTION_RULE: Final = "=" * 70
_TITLE: Final = re.compile(r"^(.+?)\s+\(session [^)]*\)$")


def _transcribed(root: Path) -> tuple[list[Trial], list[Exclusion]]:
    relative = RECON / "transcribed-terminal-outputs.txt"
    lines = _text(root, relative)
    trials: list[Trial] = []
    excluded: list[Exclusion] = []
    index = 0
    # The preamble, up to the first section rule, describes the file and counts nothing.
    while index < len(lines) and lines[index].strip() != _SECTION_RULE:
        index += 1
    while index < len(lines):
        if lines[index].strip() != _SECTION_RULE or index + 2 >= len(lines):
            raise LedgerError(f"{relative.as_posix()} line {index + 1}: expected a section rule")
        title_match = _TITLE.match(lines[index + 1].strip())
        if title_match is None or lines[index + 2].strip() != _SECTION_RULE:
            raise LedgerError(f"{relative.as_posix()} line {index + 2}: expected a section title")
        title = title_match.group(1)
        start = index + 3
        end = start
        while end < len(lines) and lines[end].strip() != _SECTION_RULE:
            end += 1
        reader = _TRANSCRIBED.get(title)
        if reader is None:
            raise LedgerError(
                f"{relative.as_posix()} has a section {title!r} the ledger has no reader for. "
                "Say how it counts before the ledger can be built."
            )
        if isinstance(reader, str):
            excluded.append(Exclusion(relative.as_posix(), f"section {title}", reader))
        else:
            trials.extend(
                _read_lines(
                    root, relative, lines[start:end], reader, family="recon", first_line=start + 1
                )
            )
        index = end
    return trials, excluded


def _recon(root: Path) -> tuple[list[Trial], list[Exclusion]]:
    trials: list[Trial] = []
    excluded: list[Exclusion] = []
    for name, patterns in (
        ("q_funnel.out", _FUNNEL),
        ("q_window.out", _WINDOW),
        ("2026-09-18_q_em.log", _EM),
        ("2026-09-18_q_bars.log", _BARS),
    ):
        relative = RECON / name
        trials.extend(_read_lines(root, relative, _text(root, relative), patterns, family="recon"))
    capped = sorted((root / RECON).glob("q_capped_log_*.txt"))
    if not capped:
        raise LedgerError(f"no q_capped_log_*.txt under {RECON.as_posix()}")
    for path in capped:
        relative = path.relative_to(root)
        trials.extend(
            _read_lines(root, relative, _text(root, relative), _CAPPED_LOG, family="recon")
        )
    for name, reason in (
        ("2026-09-18_q_spread.log", ("measures spread and depth on the 2026 recording; selects "
         "no trade")),
        ("q_ticks.out", ("compares price grids between the archive and the 2026 recording; "
         "selects no trade")),
    ):
        if not (root / RECON / name).is_file():
            raise LedgerError(f"{(RECON / name).as_posix()} is not a file; the ledger reads it")
        excluded.append(Exclusion((RECON / name).as_posix(), "whole file", reason))
    more_trials, more_excluded = _transcribed(root)
    trials.extend(more_trials)
    excluded.extend(more_excluded)
    known = {
        "q_funnel.out", "q_window.out", "2026-09-18_q_em.log", "2026-09-18_q_bars.log",
        "2026-09-18_q_spread.log", "q_ticks.out", "transcribed-terminal-outputs.txt",
    }
    stray = sorted(
        path.name
        for path in (root / RECON).iterdir()
        if path.is_file() and path.name not in known and not path.name.startswith("q_capped_log_")
    )
    if stray:
        raise LedgerError(
            f"{RECON.as_posix()} holds output(s) the ledger does not read: {', '.join(stray)}"
        )
    return trials, excluded


# --------------------------------------------------------------------------- #
# The JSON studies
# --------------------------------------------------------------------------- #


def _json(root: Path, relative: Path) -> Any:
    path = root / relative
    if not path.is_file():
        raise LedgerError(f"{relative.as_posix()} is not a file; the ledger reads it")
    return json.loads(path.read_bytes().decode("utf-8"))


def _require(value: Any, kind: type, where: str) -> Any:
    if not isinstance(value, kind):
        raise LedgerError(f"{where} is a {type(value).__name__}, expected {kind.__name__}")
    return value


def _ranking_study(root: Path) -> tuple[list[Trial], list[Exclusion]]:
    trials: list[Trial] = []
    relative = DATASET / "ranking-study-2026-09-14.json"
    study = _json(root, relative)
    for index, row in enumerate(_require(study.get("rankings"), list, "rankings")):
        trials.append(
            Trial(
                "ranking_study",
                relative.as_posix(),
                f"rankings[{index}]",
                f"rank by {row['feature']} {row['direction']}, all folds",
                f"{row['bars']} bars, target rate {row['target_rate']}",
            )
        )
    relative = DATASET / "ranking-study-2026-09-14-by-year.json"
    by_year = _json(root, relative)
    for index, row in enumerate(_require(by_year.get("rows"), list, "rows")):
        name = f"rank by {row['feature']} {row['direction']}"
        trials.append(
            Trial("ranking_study", relative.as_posix(), f"rows[{index}].all",
                  f"{name}, all folds, reported again by the by-year study",
                  f"{row['all']['bars']} bars")
        )
        for year, cell in sorted(_require(row.get("by_year"), dict, "by_year").items()):
            trials.append(
                Trial("ranking_study", relative.as_posix(), f"rows[{index}].by_year.{year}",
                      f"{name}, test year {year}", f"{cell['bars']} bars")
            )
    excluded = [
        Exclusion(
            (DATASET / "ranking-study-2026-09-13.json").as_posix(),
            "whole file",
            "computed on the constructed two-pair series of tests/research/test_training.py "
            "(its own meta.source says so), not on the walk-forward's out-of-sample rows",
        )
    ]
    return trials, excluded


def _skeptic(root: Path) -> tuple[list[Trial], list[Exclusion]]:
    trials: list[Trial] = []
    relative = DATASET / "skeptic-veto-sweep-2026-09-14.json"
    sweep = _json(root, relative)
    source = relative.as_posix()
    for index, row in enumerate(_require(sweep.get("sweep"), list, "sweep")):
        threshold = row["threshold"]
        trials.append(Trial("skeptic_sweep", source, f"sweep[{index}] survivors",
                            f"uncapped skeptic, all folds, survivors at veto {threshold}",
                            f"{row['survivors']} calls, target rate {row['survivor_target_rate']}"))
        trials.append(Trial("skeptic_sweep", source, f"sweep[{index}] vetoed",
                            f"uncapped skeptic, all folds, calls vetoed at {threshold}",
                            f"{row['vetoed']} calls, target rate {row['vetoed_target_rate']}"))
    by_year = _require(sweep.get("by_test_year_at_0.5_0.6_0.7"), dict, "by_test_year")
    for year, rows in sorted(by_year.items()):
        for index, row in enumerate(rows):
            threshold = row["threshold"]
            for side, count in (("survivors", "survivors"), ("vetoed", "vetoed")):
                trials.append(Trial(
                    "skeptic_sweep", source,
                    f"by_test_year_at_0.5_0.6_0.7.{year}[{index}] {side}",
                    f"uncapped skeptic, test year {year}, {side} at {threshold}",
                    f"{row[count]} calls"))
    controls = _require(sweep.get("different_fold_controls"), list, "different_fold_controls")
    for index, control in enumerate(controls):
        for inner, row in enumerate(control["by_threshold"]):
            for side in ("own", "other"):
                trials.append(Trial(
                    "skeptic_sweep", source,
                    f"different_fold_controls[{index}].by_threshold[{inner}] {side}",
                    f"fold {control['rows_of_fold']} calls, {side} skeptic "
                    f"(fold {control['rows_of_fold'] if side == 'own' else control['skeptic_of_fold']})"
                    f", survivors at {row['threshold']}",
                    f"{row[side + '_survivors']} calls"))
    meta = _require(sweep.get("meta"), dict, "meta")
    trials.append(Trial("skeptic_sweep", source, "meta.all_buy_calls",
                        "every BUY call, all folds, no skeptic",
                        f"{meta['all_buy_calls']} calls"))
    trials.append(Trial("skeptic_sweep", source, "meta.buy_calls_without_a_skeptic",
                        "BUY calls of the fold with no skeptic",
                        f"{meta['buy_calls_without_a_skeptic']} calls"))
    excluded = [Exclusion(source, "no_skill_survivor_target_rate_* (every sweep row)",
                          "20 permutations of each fold's own scores: a null distribution, not a "
                          "configuration anyone could adopt")]

    relative = DATASET / "skeptic-vs-ptarget-2026-09-14.json"
    source = relative.as_posix()
    comparison = _json(root, relative)
    for index, row in enumerate(_require(comparison.get("by_threshold"), list, "by_threshold")):
        for key, cell in sorted(row.items()):
            if isinstance(cell, dict) and "target_rate" in cell:
                trials.append(Trial(
                    "skeptic_vs_p_target", source, f"by_threshold[{index}].{key}",
                    f"{key}, matched to the skeptic's survivor count at {row['threshold']}",
                    f"{cell['count']} calls, target rate {cell['target_rate']}"))
    return trials, excluded


def _outcome(prefix: str, cell: Mapping[str, Any]) -> str:
    return f"{prefix}: {cell['rows']} rows, target rate {cell['target_rate']}"


def _di_anomaly(root: Path) -> tuple[list[Trial], list[Exclusion]]:
    trials: list[Trial] = []
    relative = DATASET / "di-anomaly-distributions-2026-09-14.json"
    source = relative.as_posix()
    study = _json(root, relative)
    trials.append(Trial("di_anomaly", source, "all_rows", "every out-of-sample row, no gate",
                        _outcome("all", study["all_rows"])))
    for gate in ("anomaly", "di"):
        for index, row in enumerate(_require(study.get(gate), list, gate)):
            for side in ("kept", "refused", "buy_kept", "buy_refused"):
                trials.append(Trial(
                    "di_anomaly", source, f"{gate}[{index}].{side}",
                    f"{gate} gate at percentile {row['percentile']}, {side.replace('_', ' ')}",
                    _outcome(side, row[side])))
    for index, row in enumerate(_require(study.get("joint"), list, "joint")):
        for side in ("passing", "passing_buy_calls"):
            trials.append(Trial(
                "di_anomaly", source, f"joint[{index}].{side}",
                f"anomaly at {row['anomaly_percentile']} and DI at {row['di_percentile']}, "
                f"{side.replace('_', ' ')}",
                _outcome(side, row[side])))
    incomplete = _require(study.get("incomplete"), dict, "incomplete")
    for gate in ("anomaly", "di"):
        trials.append(Trial("di_anomaly", source, f"incomplete.{gate}",
                            f"{gate} refusal for an incomplete vector, all folds",
                            _outcome("incomplete", incomplete[gate])))
    for year, cell in sorted(_require(incomplete.get("by_year"), dict, "by_year").items()):
        for key in sorted(k for k in cell if k.endswith("_share")):
            trials.append(Trial("di_anomaly", source, f"incomplete.by_year.{year}.{key}",
                                f"{key.removesuffix('_share').replace('_', ' ')}, test year {year}",
                                f"share {cell[key]}"))
    excluded = [Exclusion(source, "folds[*] and coverage",
                          "per-fold threshold values and coverage counts; they select nothing")]

    relative = DATASET / "di-exclusion-refit-2026-09-15.json"
    source = relative.as_posix()
    refit = _json(root, relative)
    for percentile, row in sorted(_require(refit.get("percentiles"), dict, "percentiles").items()):
        for side in ("kept", "refused"):
            trials.append(Trial(
                "di_anomaly", source, f"percentiles.{percentile}.{side}",
                f"DI with the any-pair 48-bar exclusion at {percentile}, {side}",
                _outcome(side, row[side])))
        for year, share in sorted(_require(row.get("by_year"), dict, "by_year").items()):
            trials.append(Trial(
                "di_anomaly", source, f"percentiles.{percentile}.by_year.{year}",
                f"DI with the exclusion at {percentile}, refused, test year {year}",
                f"share {share}"))

    relative = DATASET / "di-serial-correlation-check-2026-09-15.json"
    source = relative.as_posix()
    checks = _require(_json(root, relative), list, "serial correlation check")
    for index, fold in enumerate(checks):
        for variant in sorted(k for k, v in fold.items()
                              if isinstance(v, dict) and "out_of_sample_refused_at" in v):
            for percentile, share in sorted(fold[variant]["out_of_sample_refused_at"].items()):
                trials.append(Trial(
                    "di_anomaly", source,
                    f"[{index}].{variant}.out_of_sample_refused_at.{percentile}",
                    f"fold {fold['fold_index']} DI, {variant.replace('_', ' ')} threshold at "
                    f"{percentile}, refused",
                    f"share {share}"))
    return trials, excluded


# --------------------------------------------------------------------------- #
# The leaderboard, and this phase's runs
# --------------------------------------------------------------------------- #

_FOLD_ROW: Final = re.compile(r"^\| (\d+) \| (\d{4}-\d\d-\d\d) \| ")


def _leaderboard(root: Path) -> tuple[list[Trial], list[Exclusion], list[str]]:
    relative = DATASET / "walkforward-folds-2026-09-14.md"
    trials: list[Trial] = []
    for number, line in enumerate(_text(root, relative), start=1):
        match = _FOLD_ROW.match(line)
        if match is None:
            continue
        trials.append(Trial(
            "leaderboard", relative.as_posix(), f"line {number}",
            f"predictor, walk-forward train-20260913T205245-067b2b9d, fold {match.group(1)}",
            f"test week {match.group(2)}"))
    if not trials:
        raise LedgerError(f"{relative.as_posix()} has no fold rows")
    for run_id in SMOKE_RUN_FOLD_MODELS:
        trials.append(Trial(
            "leaderboard", "models/ (gitignored; seen on disk 2026-09-19)", run_id,
            f"predictor, three-pair smoke run, {run_id}",
            "evaluated on its own test week"))
    excluded = [
        Exclusion("data/db/acsoe.sqlite (gitignored)", "leaderboard",
                  "six rows, model versions v0.1 to v0.6 of training runs seed-train-0000 to "
                  "0005: the Phase 0 seed's fabricated rows, evaluated on nothing"),
        Exclusion("tests/fixtures/leaderboard_sample.json", "whole file",
                  "the committed Phase 6 fixture: fabricated rows for engine 14's criterion"),
    ]
    judgements = [
        ("Leaderboard. Engine 20 has written no persisted leaderboard row for the walk-forward: "
        "the only database on disk (data/db/acsoe.sqlite) holds the six fabricated Phase 0 seed "
        "rows. The rows engine 20 would write are one per trained fold, and the committed "
        "walk-forward table (walkforward-folds-2026-09-14.md, rebuilt from the fold artefacts) "
        "lists them, so each fold there is counted as one leaderboard row."),
        ("The three fold models of a three-pair smoke training run exist only on disk under "
        "models/. Whether they count as evaluated on the out-of-sample data is unclear, so they "
        "count."),
    ]
    return trials, excluded, judgements


def _phase_7_runs() -> list[Trial]:
    return [
        Trial("phase_7_runs", "feature-specs/143-the-simulation-run.md", f"tier {tier}, {ranking}",
              f"chain simulation, folds 379-404, tier {tier}, ranked by {ranking}",
              "counted before launch; the count is fixed before any simulated figure exists")
        for ranking in PHASE_7_RANKINGS
        for tier in PHASE_7_TIERS
    ]


_JUDGEMENTS: Final = (
    ("Funnels: every stage a line reports counts, because each stage is a different selection "
    "(the gates up to that point)."),
    "Sub-windows (a year, a 6-, 12- or 18-month slice) of a selection count separately.",
    ("A selection and its complement reported with their own outcomes (survivors and vetoed; kept "
    "and refused) count as two."),
    ("The same selection reported in two files or two lines counts twice: nothing on disk proves "
    "two reports were one computation. Examples: q_window's (a)/(b) counts and their detail lines; "
    "the ranking study's rows and the by-year study's 'all' rows; the skeptic's own survivors in "
    "the skeptic-against-p_target comparison; q_hold against q_window's (b) column."),
    "The two tie-breaking seeds of the p_target comparison count as two.",
    ("Counts without an outcome (rows above an expected-move bar, a gate's refusal share) count, "
    "because a count of what a selection would have traded is a statistic of that selection."),
    ("Spec 139 lists the DI at 0.95, 0.99 and 0.999 and the anomaly gate at 0.95 and 0.99. The "
    "committed study evaluated seven percentiles of each and a 3x3 joint grid, so every one "
    "evaluated is counted, not only the ones the spec named."),
    ("Whether an output shows every cell its script evaluated: the loops of q_funnel, q_bucket, "
    "q_emrank, q_hold, q_picks, q_capped_compare, 2026-09-18_q_net and 2026-09-18_q_year were "
    "read against their outputs on 2026-09-19, and each prints one line per cell it evaluated, "
    "zero-trade cells included. Where a script could have been run more than once before its "
    "output was saved, only the saved run is visible, and it is what is counted."),
    ("Anything computed before 2026-09-19 in a session and never committed cannot be counted from "
    "the outputs. The ledger counts what the committed outputs show and the smoke-run models seen "
    "on disk; it cannot see more."),
)


def build_ledger(root: Path) -> Ledger:
    """Every trial the committed outputs under ``root`` show, in a fixed order."""
    trials: list[Trial] = []
    excluded: list[Exclusion] = []
    judgements: list[str] = list(_JUDGEMENTS)
    board, board_excluded, board_judgements = _leaderboard(root)
    trials.extend(board)
    excluded.extend(board_excluded)
    judgements.extend(board_judgements)
    for reader in (_recon, _ranking_study, _skeptic, _di_anomaly):
        more, more_excluded = reader(root)
        trials.extend(more)
        excluded.extend(more_excluded)
    trials.extend(_phase_7_runs())
    for relative, reason in (
        (DATASET / "labelled-dataset-2026-09-12.json", "dataset statistics; selects nothing"),
        (DATASET / "labelled-dataset-2026-09-12-before-cutoff.json",
         "dataset statistics; selects nothing"),
        (DATASET / "folds-three-pairs-2026-09-12.json", "fold construction; selects nothing"),
    ):
        if not (root / relative).is_file():
            raise LedgerError(f"{relative.as_posix()} is not a file; the ledger names it")
        excluded.append(Exclusion(relative.as_posix(), "whole file", reason))
    return Ledger(trials=tuple(trials), excluded=tuple(excluded), judgements=tuple(judgements))


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def render_json(ledger: Ledger) -> bytes:
    families = Counter(trial.family for trial in ledger.trials)
    payload = {
        "what": "Every configuration evaluated against the out-of-sample data, one row per "
        "trial (spec 139, ruling R9). Built by `python -m acsoe.research.trial_ledger` from the "
        "committed outputs; never typed by hand.",
        "rule": RULE,
        "trial_count": ledger.trial_count,
        "by_family": dict(sorted(families.items())),
        "judgements": list(ledger.judgements),
        "excluded": [asdict(item) for item in ledger.excluded],
        "trials": [asdict(item) for item in ledger.trials],
    }
    return (json.dumps(payload, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def render_markdown(ledger: Ledger) -> bytes:
    families = Counter(trial.family for trial in ledger.trials)
    lines = [
        "# Phase 7 trial ledger",
        "",
        ("Every configuration evaluated against the out-of-sample data, one row per trial (spec "
        "139, ruling R9). **Built by `python -m acsoe.research.trial_ledger` from the committed "
        "outputs; never typed by hand.** The JSON beside this file is the same ledger, and the "
        "promotion gate reads its `trial_count`."),
        "",
        f"**Trial count: {ledger.trial_count}.** It errs high on purpose.",
        "",
        "## The rule",
        "",
        RULE,
        "",
        "## Judgements made under the rule",
        "",
        *[f"- {text}" for text in ledger.judgements],
        "",
        "## By family",
        "",
        "| Family | Trials |",
        "|---|---|",
        *[f"| {family} | {count} |" for family, count in sorted(families.items())],
        "",
        "## Excluded, with the reason",
        "",
        "| Source | Where | Why it counts nothing |",
        "|---|---|---|",
        *[f"| {_cell(e.source)} | {_cell(e.locator)} | {_cell(e.reason)} |"
          for e in ledger.excluded],
        "",
        "## Every trial",
        "",
        "| # | Family | Source | Where | Configuration | Reported |",
        "|---|---|---|---|---|---|",
        *[
            f"| {n} | {t.family} | {_cell(t.source)} | {_cell(t.locator)} | "
            f"{_cell(t.configuration)} | {_cell(t.statistic)} |"
            for n, t in enumerate(ledger.trials, start=1)
        ],
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    """Rebuild both ledger files under the repository root (the working directory by default)."""
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args[0]) if args else Path.cwd()
    ledger = build_ledger(root)
    (root / LEDGER_JSON).write_bytes(render_json(ledger))
    (root / LEDGER_MD).write_bytes(render_markdown(ledger))
    sys.stdout.write(f"{ledger.trial_count} trials written to {LEDGER_JSON.as_posix()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
