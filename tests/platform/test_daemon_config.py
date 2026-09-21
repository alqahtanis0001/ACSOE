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
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DEFAULT = REPO / "config" / "default.yaml"
DAEMON = REPO / "config" / "daemon.yaml"

#: The only key the daemon config is allowed to differ on, with its value.
DECLARED_OVERRIDES: dict[str, Any] = {"scout.rank_feature": "expected_move"}


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
