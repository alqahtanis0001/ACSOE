"""A's committed evidence fixtures, asserted on their **bytes**.

`tests/fixtures/**` is `-text` in `.gitattributes`, deliberately and with a comment
saying why: every committed-fixture criterion compares bytes that git would otherwise
rewrite between commit and clone. The consequence is the one that bit us — **there is no
clean filter under that directory**, so unlike everywhere else in this repository a
text-mode write changes the *committed* bytes rather than being normalised away on the
way into the index.

`Path.write_text` and `open(path, "w")` are text-mode writers, and text mode on Windows
translates every `\n` to `\r\n`. Two of these fixtures were written that way and were
committed as all-CRLF: `recording_report.json` (168 lines) and `kraken/ohlc.json`
(12,094 lines). Both producers now pass `newline="\n"` and both artefacts are LF.

**Everything above bytes is blind to this.** `read_text`, `splitlines`, `json.loads`,
`csv.reader` and — the one that caught me out — `grep` all normalise line endings, so
an audit conducted with any of them reports a clean result against a CRLF file. This
file exists because the only honest check is `read_bytes`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A's committed evidence, per `context/ownership.md`, plus the OHLC fixture, which is
#: produced by `scripts/ohlc_fixture.py` and judged by `candles_match_independent_reduction_of_recorded_trades`.
#:
#: Named one by one rather than globbed. A glob over `tests/fixtures/**` would sweep up
#: C's and B's deposits, and a test of mine going red because another agent's fixture
#: regressed points the wrong person at the problem. C owns the structure of that
#: directory and a repository-wide version of this check belongs in their lane.
A_FIXTURES = (
    "tests/fixtures/record_sample.jsonl",
    "tests/fixtures/recording_report.json",
    "tests/fixtures/kraken/ohlc.json",
)

#: Written by `scripts/recording_report.py` in a later phase. Absent is not a failure
#: here — `recording_span_continuous` is the criterion that cares whether it exists —
#: but if it *is* present it is held to the same rule as the rest.
OPTIONAL_FIXTURES = ("tests/fixtures/soak_digest.json",)


def existing(names: tuple[str, ...]) -> list[Path]:
    return [REPO_ROOT / name for name in names if (REPO_ROOT / name).is_file()]


@pytest.mark.parametrize("name", A_FIXTURES)
def test_a_s_evidence_fixtures_are_committed_with_unix_line_endings(name: str) -> None:
    """Asserted on `read_bytes`, because nothing else can see it.

    A CRLF fixture is not a cosmetic problem under `-text`. It is committed bytes that
    change whenever somebody edits the file through a text-mode round trip, which makes
    an evidence artefact's diff depend on which machine last touched it — the exact
    thing `.gitattributes` was written to prevent.
    """
    path = REPO_ROOT / name
    assert path.is_file(), f"{name} is missing"
    raw = path.read_bytes()
    # Counted outside the f-string: the project's ruff target is Python 3.11, where a
    # backslash escape inside an f-string expression is a syntax error.
    crlf = raw.count(b"\x0d\x0a")
    assert b"\x0d" not in raw, (
        f"{name} carries {crlf} CRLF line ending(s). "
        "tests/fixtures/** is `-text`, so there is no clean filter and this is in the "
        "committed blob. Its producer is writing in text mode: pass newline='\\n'."
    )


@pytest.mark.parametrize("name", OPTIONAL_FIXTURES)
def test_an_optional_fixture_is_held_to_the_same_rule_once_it_exists(name: str) -> None:
    """Skips while absent rather than passing while absent.

    A test that silently passes on a missing file is one that will keep passing after
    the file arrives wrong. The skip reason says which state it is in.
    """
    path = REPO_ROOT / name
    if not path.is_file():
        pytest.skip(f"{name} has not been deposited yet")
    assert b"\x0d" not in path.read_bytes(), name


def test_the_fixtures_directory_is_still_marked_minus_text() -> None:
    """The reason the rule above is stricter here than anywhere else in the repository.

    If `tests/fixtures/** -text` were ever removed, the clean filter would start
    normalising these files and the byte assertions above would become unfalsifiable —
    passing not because the producers are correct but because git is hiding it. This
    pins the premise the other tests rest on.
    """
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    lines = [line.split("#", 1)[0].strip() for line in attributes.splitlines()]
    assert "tests/fixtures/**   -text" in lines or any(
        line.startswith("tests/fixtures/") and line.endswith("-text") for line in lines
    ), "tests/fixtures/** is no longer `-text`; the byte assertions above are now moot"


def test_the_line_ending_check_is_capable_of_failing(tmp_path: Path) -> None:
    """Proof the assertion is not vacuous.

    Every test above passes against a file with no newlines in it at all, and would pass
    against a check that read the wrong path. This runs the same predicate over a file
    that is deliberately CRLF.
    """
    crlf = tmp_path / "crlf.json"
    crlf.write_bytes(b'{\x0d\x0a "a": 1\x0d\x0a}\x0d\x0a')
    assert b"\x0d" in crlf.read_bytes()

    lf = tmp_path / "lf.json"
    lf.write_bytes(b'{\x0a "a": 1\x0a}\x0a')
    assert b"\x0d" not in lf.read_bytes()

    # ...and that the fixtures actually contain newlines, so "no CR" is not true only
    # because there is nothing in them to convert.
    for path in existing(A_FIXTURES):
        assert b"\x0a" in path.read_bytes(), path.name
