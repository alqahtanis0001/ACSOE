"""`config/daemon.yaml` is a copy of `config/default.yaml` with one documented override.

Operator ruling 2026-09-21 (option C): the daemon must rank by engine 8's expected move
without depending on a command-line flag, and `config/default.yaml` must stay the honest
baseline a fresh clone can run — with the key absent it ranks alphabetically, and with the key
set it would fail closed at engine 7, because ranking loads the artefacts named by
`models.*_run_id` and those are not in the committed config.

Two config files drift. **This test is what stops them:** every key in both files must agree
except the ones declared here, so a change to `default.yaml` that is not mirrored goes red.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DEFAULT = REPO / "config" / "default.yaml"
DAEMON = REPO / "config" / "daemon.yaml"

#: The only keys the daemon config is allowed to differ on, with their values. Widened from
#: one to four by operator ruling 2026-09-21: the daemon runs fold 404's artefacts, and those
#: run ids are in `daemon.yaml` alone because a committed default naming particular artefacts
#: goes stale on any retrain. **Anything not in this map is still a failure.**
_F404: Final = "train-20260913T205245-067b2b9d-f404-p7"
DECLARED_OVERRIDES: dict[str, Any] = {
    "scout.rank_feature": "expected_move",
    "models.prediction_run_id": _F404,
    "models.anomaly_run_id": _F404,
    "models.skeptic_run_id": _F404,
}


def _flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            flat.update(_flatten(value, f"{prefix}{key}."))
        return flat
    flat[prefix.rstrip(".")] = data
    return flat


@pytest.fixture(scope="module")
def default_keys() -> dict[str, Any]:
    return _flatten(yaml.safe_load(DEFAULT.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def daemon_keys() -> dict[str, Any]:
    return _flatten(yaml.safe_load(DAEMON.read_text(encoding="utf-8")))


def test_the_daemon_config_exists_and_parses() -> None:
    assert DAEMON.is_file(), f"{DAEMON} is missing"
    assert isinstance(yaml.safe_load(DAEMON.read_text(encoding="utf-8")), dict)


def test_the_daemon_config_sets_the_ranking_feature(daemon_keys: dict[str, Any]) -> None:
    """The whole reason the file exists."""
    assert daemon_keys.get("scout.rank_feature") == "expected_move"


def test_the_daemon_config_names_the_model_the_daemon_runs(daemon_keys: dict[str, Any]) -> None:
    """Operator ruling 2026-09-21: fold 404's artefacts, in this file only.

    Ranking loads what these name, so the key being set is what separates a daemon that ranks
    from one that fails closed at engine 7 on every tick. The value is asserted, not just
    presence: a run id pointing at a directory that does not exist fails the same way as an
    absent key, only later and less legibly.
    """
    for key in ("prediction_run_id", "anomaly_run_id", "skeptic_run_id"):
        assert daemon_keys.get(f"models.{key}") == _F404, key
    # The named run must exist *where the artefacts exist at all*. `models/` is gitignored,
    # so a fresh clone and every clean worktree have none — and a test that demanded the
    # directory there would be a test that only passes on the machine that trained it, which
    # `ai-workflow-rules.md` calls a broken criterion. Asserting it only when the root is
    # populated still catches the failure that matters: a run id naming a directory that is
    # missing on the machine the daemon runs on.
    root = REPO / "models"
    if not root.is_dir() or not any(root.iterdir()):
        pytest.skip("models/ is empty here (gitignored); nothing to check the run id against")
    assert (root / _F404).is_dir(), (
        f"{_F404} is not under models/ on this machine; the daemon config names artefacts "
        "the daemon cannot load, and engine 7 would fail closed on every tick"
    )


def test_the_committed_default_names_no_model_artefacts(default_keys: dict[str, Any]) -> None:
    """The other half of the ruling: `default.yaml` names no particular artefacts, because
    they go stale on any retrain and a fresh clone has none of them."""
    for key in ("prediction_run_id", "anomaly_run_id", "skeptic_run_id"):
        assert f"models.{key}" not in default_keys, key


def test_the_committed_default_still_leaves_the_key_absent(default_keys: dict[str, Any]) -> None:
    """The other half of the ruling, and the reason option B was refused: a fresh clone must
    still run. With the key set and no model artefacts, engine 7 blocks on every tick."""
    assert "scout.rank_feature" not in default_keys


def test_the_two_configs_differ_only_where_declared(
    default_keys: dict[str, Any], daemon_keys: dict[str, Any]
) -> None:
    """Drift detection. A key added to `default.yaml` and not to `daemon.yaml` — or a value
    changed in one and not the other — fails here, naming the key."""
    differing = {
        key
        for key in set(default_keys) | set(daemon_keys)
        if default_keys.get(key) != daemon_keys.get(key)
    }
    unexplained = sorted(differing - set(DECLARED_OVERRIDES))

    assert not unexplained, (
        "config/daemon.yaml and config/default.yaml differ on keys that are not declared "
        f"overrides: {unexplained}. Mirror the change or declare it in DECLARED_OVERRIDES."
    )
    for key, value in DECLARED_OVERRIDES.items():
        assert daemon_keys.get(key) == value, f"{key} is not the declared override"


def test_the_daemon_config_loads_through_the_real_loader() -> None:
    """It has to be a config the daemon can actually start with, not only valid YAML."""
    from acsoe.platform.config import load_config

    config = load_config(DAEMON, load_env=False)

    assert config.get("scout.rank_feature") == "expected_move"
    assert config.mode == "paper", "the daemon config must not be the thing that enables live"


def test_the_daemon_config_does_not_enable_live() -> None:
    """Invariant 1: mode is one of three switches and this file is not permission. The
    operator ruled on 2026-09-21 that `mode: live` is a separate decision, after path (a)
    works and access control is in."""
    assert "mode: live" not in DAEMON.read_text(encoding="utf-8")
