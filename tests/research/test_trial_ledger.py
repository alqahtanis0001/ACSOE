"""Spec 139 — the trial ledger is built from the committed outputs and never typed by hand.

The committed `docs/dataset/phase-7-trial-ledger.{json,md}` must be byte-identical to a rebuild
from the committed outputs, so a hand edit is a red test. The rest plant defects in a copy of
the outputs: one extra cell must raise the count by exactly one, and a line, section or file the
builder cannot classify must stop the build rather than go uncounted.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from acsoe.research import trial_ledger
from acsoe.research.trial_ledger import (
    LEDGER_JSON,
    LEDGER_MD,
    LedgerError,
    build_ledger,
    render_json,
    render_markdown,
)

ROOT = Path(__file__).resolve().parents[2]
FUNNEL = Path("docs/dataset/phase-7-recon-2026-09-19/outputs/q_funnel.out")
TRANSCRIBED = Path("docs/dataset/phase-7-recon-2026-09-19/outputs/transcribed-terminal-outputs.txt")


@pytest.fixture(scope="module")
def committed() -> trial_ledger.Ledger:
    return build_ledger(ROOT)


@pytest.fixture
def copy_root(tmp_path: Path) -> Path:
    """The committed outputs, copied, so a planted defect never touches the real ones."""
    shutil.copytree(ROOT / "docs" / "dataset", tmp_path / "docs" / "dataset")
    return tmp_path


def insert_after(path: Path, anchor: str, line: str) -> None:
    """Plant ``line`` after ``anchor``, in whatever line ending the checkout gave the file.

    The outputs are LF in git and may be CRLF in a Windows working tree; the builder reads
    either, and a planted line must not be the one line that differs.
    """
    text = path.read_bytes().decode("utf-8")
    if "\r\n" in text:
        anchor, line = anchor.replace("\n", "\r\n"), line.replace("\n", "\r\n")
    assert text.count(anchor) == 1, f"anchor appears {text.count(anchor)} times"
    path.write_bytes(text.replace(anchor, anchor + line, 1).encode("utf-8"))


def as_committed(path: Path) -> bytes:
    """The file's bytes with the checkout's line endings undone.

    Git stores these files LF; a Windows checkout may hand them back CRLF. The comparison is
    about content the builder decides, not about which checkout ran the test.
    """
    return path.read_bytes().replace(b"\r\n", b"\n")


def test_the_committed_json_is_exactly_what_the_builder_writes(
    committed: trial_ledger.Ledger,
) -> None:
    assert as_committed(ROOT / LEDGER_JSON) == render_json(committed)


def test_the_committed_markdown_is_exactly_what_the_builder_writes(
    committed: trial_ledger.Ledger,
) -> None:
    assert as_committed(ROOT / LEDGER_MD) == render_markdown(committed)


def test_the_count_is_the_rows_and_the_families_sum_to_it(committed: trial_ledger.Ledger) -> None:
    payload = json.loads((ROOT / LEDGER_JSON).read_bytes().decode("utf-8"))
    assert payload["trial_count"] == len(payload["trials"]) == committed.trial_count
    assert sum(payload["by_family"].values()) == committed.trial_count


def test_every_family_the_ruling_names_is_present(committed: trial_ledger.Ledger) -> None:
    families = {trial.family for trial in committed.trials}
    assert families == {
        "leaderboard",
        "recon",
        "ranking_study",
        "skeptic_sweep",
        "skeptic_vs_p_target",
        "di_anomaly",
        "phase_7_runs",
    }


def test_this_phases_four_runs_are_counted(committed: trial_ledger.Ledger) -> None:
    runs = [trial.locator for trial in committed.trials if trial.family == "phase_7_runs"]
    assert sorted(runs) == [
        "tier 3, alphabetical",
        "tier 3, expected_move",
        "tier 5, alphabetical",
        "tier 5, expected_move",
    ]


def test_every_counted_source_under_docs_is_a_committed_file(
    committed: trial_ledger.Ledger,
) -> None:
    sources = {trial.source for trial in committed.trials if trial.source.startswith("docs/")}
    assert sources
    missing = sorted(source for source in sources if not (ROOT / source).is_file())
    assert missing == []


def test_the_walk_forwards_folds_are_each_a_leaderboard_row(
    committed: trial_ledger.Ledger,
) -> None:
    folds = [
        trial for trial in committed.trials
        if trial.source == "docs/dataset/walkforward-folds-2026-09-14.md"
    ]
    assert len(folds) == 405


# --------------------------------------------------------------------------- #
# Planted defects in a copy of the outputs
# --------------------------------------------------------------------------- #


def test_one_planted_cell_raises_the_count_by_exactly_one(copy_root: Path) -> None:
    before = build_ledger(copy_root).trial_count
    insert_after(
        copy_root / FUNNEL,
        "      cap@0.70: trades  84 (38 pairs, 44 target) net +0.26% +/-0.48%\n",
        "      cap@0.80: trades  90 (40 pairs, 45 target) net +0.20% +/-0.40%\n",
    )
    after = build_ledger(copy_root)
    assert after.trial_count == before + 1
    assert any("capped skeptic veto at 0.80" in t.configuration for t in after.trials)


def test_a_planted_ranking_study_row_is_counted(copy_root: Path) -> None:
    path = copy_root / "docs" / "dataset" / "ranking-study-2026-09-14.json"
    study = json.loads(path.read_bytes().decode("utf-8"))
    before = build_ledger(copy_root).trial_count
    study["rankings"].append(dict(study["rankings"][0], feature="planted_feature"))
    path.write_bytes(json.dumps(study).encode("utf-8"))
    assert build_ledger(copy_root).trial_count == before + 1


def test_a_line_the_builder_cannot_classify_stops_the_build(copy_root: Path) -> None:
    insert_after(
        copy_root / FUNNEL,
        "      cap@0.70: trades  84 (38 pairs, 44 target) net +0.26% +/-0.48%\n",
        "      a new kind of cell nobody wrote a reader for: 12\n",
    )
    with pytest.raises(LedgerError, match=r"q_funnel\.out line \d+ is neither a counted cell"):
        build_ledger(copy_root)


def test_a_transcribed_section_with_no_reader_stops_the_build(copy_root: Path) -> None:
    path = copy_root / TRANSCRIBED
    rule = "=" * 70
    path.write_bytes(
        path.read_bytes()
        + f"\n{rule}\nq_new.py  (session 68f2f338)\n{rule}\nsomething: 3\n".encode()
    )
    with pytest.raises(LedgerError, match=r"section 'q_new\.py' the ledger has no reader for"):
        build_ledger(copy_root)


def test_an_output_file_the_builder_does_not_read_stops_the_build(copy_root: Path) -> None:
    (copy_root / FUNNEL).with_name("q_new.out").write_bytes(b"trades 5\n")
    with pytest.raises(LedgerError, match=r"does not read: q_new\.out"):
        build_ledger(copy_root)


def test_a_missing_output_stops_the_build(copy_root: Path) -> None:
    (copy_root / FUNNEL).unlink()
    with pytest.raises(LedgerError, match=r"q_funnel\.out is not a file"):
        build_ledger(copy_root)


def test_main_writes_both_files_under_the_root_it_is_given(copy_root: Path) -> None:
    assert trial_ledger.main([str(copy_root)]) == 0
    ledger = build_ledger(copy_root)
    assert (copy_root / LEDGER_JSON).read_bytes() == render_json(ledger)
    assert (copy_root / LEDGER_MD).read_bytes() == render_markdown(ledger)
