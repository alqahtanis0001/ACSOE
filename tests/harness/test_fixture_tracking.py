"""The committed evidence under `tests/fixtures/` must actually survive git.

Spec 14 step 5. This is not a formality. `.gitignore` carries `*.jsonl`,
`*.parquet` and `*.sqlite` because `data/` is large and reveals account activity,
and every one of those globs would silently swallow the evidence files the phase
criteria read. The `!tests/fixtures/**` negation is the only thing preventing it,
and it fails *without an error message*: the file sits on disk, the criterion
passes locally, and a fresh clone has nothing to check.

The third audit found exactly that, which is why the negation exists. This test is
what stops it coming back.

Every assertion is a real `git` invocation against the real repository, and the
control cases are the point: if `.gitignore` ever lost the `*.jsonl` rule
altogether, the first test would pass for entirely the wrong reason.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

GIT = shutil.which("git")

# Extensions the global ignores would swallow, and where the evidence lives.
SWALLOWED_FIXTURES = (
    "tests/fixtures/record_sample.jsonl",
    "tests/fixtures/labelled_sample.parquet",
    "tests/fixtures/soak_digest.json",
    "tests/fixtures/anything.sqlite",
)

# The same extensions somewhere the ignore must still bite.
CONTROL_PATHS = (
    "data/raw/kraken_v2_2026-01-01.jsonl",
    "data/derived/features.parquet",
    "data/db/acsoe.sqlite",
)

pytestmark = pytest.mark.skipif(GIT is None, reason="git is not on PATH")


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    assert GIT is not None
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [GIT, *args], cwd=repo_root, capture_output=True, text=True, check=False
    )


def _is_ignored(repo_root: Path, path: str) -> bool:
    """`--no-index` is load-bearing.

    Without it `check-ignore` skips any path already in the index and reports "not
    ignored" for a tracked file whatever `.gitignore` says - which would make this
    test pass on the one file it is least interesting about and prove nothing about
    the ones that are not committed yet. `-q` keeps the exit code meaning "ignored"
    rather than "some pattern, possibly a negation, matched".
    """
    return _git(repo_root, "check-ignore", "--no-index", "-q", path).returncode == 0


@pytest.mark.parametrize("path", SWALLOWED_FIXTURES)
def test_committed_evidence_is_not_ignored(repo_root: Path, path: str) -> None:
    """The `!tests/fixtures/**` negation is live for every evidence extension.

    Paths that do not exist yet are included on purpose: `labelled_sample.parquet`
    is mine in Phase 4 and `soak_digest.json` is A's in Phase 8, and finding out
    then that git was going to swallow them is four phases too late.
    """
    assert not _is_ignored(repo_root, path), (
        f"{path} is ignored. The `!tests/fixtures/**` negation in .gitignore is "
        "what makes committed evidence possible; without it every offline criterion "
        "silently fails the fresh-clone rule."
    )


@pytest.mark.parametrize("path", CONTROL_PATHS)
def test_the_same_extensions_are_still_ignored_outside_the_fixtures_directory(
    repo_root: Path, path: str
) -> None:
    """Without this the test above would pass if the ignores vanished entirely."""
    assert _is_ignored(repo_root, path), (
        f"{path} is NOT ignored. `data/` is gitignored because it is large and "
        "reveals account activity; a recording or a database must never be committable."
    )


def test_the_recorder_sample_is_genuinely_tracked(repo_root: Path) -> None:
    """Not "exists on disk" - tracked. `git ls-files` is the only thing that
    distinguishes a committed fixture from a local artefact that a fresh clone
    will not have."""
    listed = _git(repo_root, "ls-files", "tests/fixtures/record_sample.jsonl").stdout.split()
    if not listed:
        pytest.skip(
            "tests/fixtures/record_sample.jsonl is not committed yet (the lead commits, "
            "not teammates); the ignore rules above are still proven"
        )
    assert listed == ["tests/fixtures/record_sample.jsonl"]


def test_a_fixture_can_actually_be_staged(repo_root: Path) -> None:
    """Spec 14 says confirm by actually staging one, rather than assuming.

    `--dry-run` does the whole check and reports what would happen without touching
    the index - teammates do not commit, and a test has no business leaving the
    working tree different from how it found it.
    """
    existing = [p for p in SWALLOWED_FIXTURES if (repo_root / p).is_file()]
    if not existing:
        pytest.skip("no committed evidence file exists yet to stage")
    done = _git(repo_root, "add", "--dry-run", *existing)
    assert done.returncode == 0, done.stderr
    assert "ignored by one of your .gitignore files" not in done.stderr


@pytest.mark.parametrize("path", SWALLOWED_FIXTURES)
def test_fixtures_are_marked_binary_so_a_windows_clone_cannot_rewrite_them(
    repo_root: Path, path: str
) -> None:
    """`.gitattributes` must hold `tests/fixtures/** -text`.

    Git for Windows ships `core.autocrlf=true` in the *system* config, so a fresh
    clone checks text files out with CRLF. Git's text/binary detection is a
    heuristic, and when it guesses wrong on a parquet payload it rewrites `0x0A`
    bytes inside it and corrupts the file with no error anywhere. Found by A while
    staging `record_sample.jsonl`.
    """
    if not (repo_root / ".gitattributes").is_file():
        pytest.skip(".gitattributes does not exist yet")
    attr = _git(repo_root, "check-attr", "text", "--", path).stdout.strip()
    assert attr.endswith(": text: unset"), (
        f"{path} has `{attr}`, expected `text: unset` from a `-text` rule. A CRLF "
        "rewrite between commit and clone breaks every byte-comparing criterion."
    )
