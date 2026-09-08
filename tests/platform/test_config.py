"""Spec 07 — the config model, the loader, and every refusal.

The refusals are the point. A config layer that accepts a bad file and carries on
is worse than none: it turns "the operator never chose a risk fraction" into
"something chose one for them".
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from acsoe.platform.config import (
    Config,
    ConfigError,
    arm_secret_redaction,
    load_config,
    load_dotenv,
    parse_dotenv,
)
from acsoe.platform.logging import clear_secrets, registered_secret_count

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YAML = REPO_ROOT / "config" / "default.yaml"

#: Values the operator has not supplied yet. Chosen here only so the *loader*
#: can be tested; they are not defaults and nothing outside tests may use them.
#: `config/default.yaml` keeps them null on purpose — see `_refuse_nulls`.
OPERATOR_VALUES: dict[str, dict[str, Any]] = {
    "safety": {
        "max_drawdown_pct": "0.10",
        "max_consecutive_losses": 5,
        "max_errors_in_window": 20,
    },
    "trading": {
        "hurdle_multiple": "1.5",
        "risk_fraction_per_trade": "0.01",
        "max_concurrent_positions": 3,
        "entry_unfilled_window_s": 300,
        "base_reporting_currency": "USD",
    },
    "paper": {"starting_balances": {"USD": "1000.00"}},
}


def complete_config_dict() -> dict[str, Any]:
    """`config/default.yaml` with the OPERATOR REQUIRED nulls filled in."""
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    for section, values in OPERATOR_VALUES.items():
        raw[section].update(copy.deepcopy(values))
    return dict(raw)


def write_config(tmp_path: Path, raw: dict[str, Any]) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def complete(tmp_path: Path) -> Path:
    return write_config(tmp_path, complete_config_dict())


@pytest.fixture(autouse=True)
def _no_leaked_secrets() -> Iterator[None]:
    clear_secrets()
    yield
    clear_secrets()


# --------------------------------------------------------------------------
# The shipped file
# --------------------------------------------------------------------------


def test_default_yaml_refuses_to_load_and_names_every_operator_key() -> None:
    """The shipped config is deliberately unstartable.

    Nine keys are OPERATOR REQUIRED: the context files name them and value none
    of them, and every one is trading behaviour. The loader names all of them in
    one message rather than one per run.
    """
    with pytest.raises(ConfigError) as caught:
        Config.load(DEFAULT_YAML)
    message = str(caught.value)
    for key in (
        "safety.max_drawdown_pct",
        "safety.max_consecutive_losses",
        "safety.max_errors_in_window",
        "trading.hurdle_multiple",
        "trading.risk_fraction_per_trade",
        "trading.max_concurrent_positions",
        "trading.entry_unfilled_window_s",
        "trading.base_reporting_currency",
        "paper.starting_balances",
    ):
        assert key in message
    assert "OPERATOR REQUIRED" in message


def test_default_yaml_is_paper_mode() -> None:
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    assert raw["mode"] == "paper"


def test_the_completed_default_yaml_validates(complete: Path) -> None:
    config = Config.load(complete)
    assert config.mode == "paper"
    assert config.console.port == 8765
    assert config.safety.max_consecutive_data_blocks == 15
    assert config.timeframes.loop_tick_s == 60


# --------------------------------------------------------------------------
# Mode: Phase 0 forces paper
# --------------------------------------------------------------------------


def test_mode_live_is_refused_naming_the_invariant_and_the_phase(tmp_path: Path) -> None:
    """Invariant 1. `platform/live_guard.py` is a Phase 8 deliverable and the
    absence of the guard is not permission."""
    raw = complete_config_dict()
    raw["mode"] = "live"
    with pytest.raises(ConfigError) as caught:
        Config.load(write_config(tmp_path, raw))
    message = str(caught.value)
    assert "Phase 8" in message
    assert "invariant 1" in message
    assert "live_guard" in message


def test_mode_replay_is_refused(tmp_path: Path) -> None:
    raw = complete_config_dict()
    raw["mode"] = "replay"
    with pytest.raises(ConfigError, match="paper"):
        Config.load(write_config(tmp_path, raw))


def test_an_unknown_mode_is_refused(tmp_path: Path) -> None:
    raw = complete_config_dict()
    raw["mode"] = "LIVE"
    with pytest.raises(ConfigError):
        Config.load(write_config(tmp_path, raw))


# --------------------------------------------------------------------------
# Console: the poll/stale relationship
# --------------------------------------------------------------------------


def test_a_poll_interval_above_a_quarter_of_stale_is_refused(tmp_path: Path) -> None:
    raw = complete_config_dict()
    raw["console"]["poll_interval_ms"] = 30001
    raw["console"]["stale_after_ms"] = 120000
    with pytest.raises(ConfigError) as caught:
        Config.load(write_config(tmp_path, raw))
    assert "poll_interval_ms" in str(caught.value)


def test_exactly_a_quarter_is_accepted(tmp_path: Path) -> None:
    """The rule is `<=`, so the boundary must not be off by one."""
    raw = complete_config_dict()
    raw["console"]["poll_interval_ms"] = 30000
    raw["console"]["stale_after_ms"] = 120000
    assert Config.load(write_config(tmp_path, raw)).console.poll_interval_ms == 30000


# --------------------------------------------------------------------------
# Structural refusals
# --------------------------------------------------------------------------


def test_a_missing_required_key_is_refused(tmp_path: Path) -> None:
    raw = complete_config_dict()
    del raw["trading"]["hurdle_multiple"]
    with pytest.raises(ConfigError, match="hurdle_multiple"):
        Config.load(write_config(tmp_path, raw))


def test_a_missing_section_is_refused(tmp_path: Path) -> None:
    raw = complete_config_dict()
    del raw["barriers"]
    with pytest.raises(ConfigError, match="barriers"):
        Config.load(write_config(tmp_path, raw))


def test_an_unknown_key_is_refused_rather_than_ignored(tmp_path: Path) -> None:
    """A typo'd threshold silently dropped leaves the system on a value nobody chose."""
    raw = complete_config_dict()
    raw["trading"]["hurdle_multiplier"] = 2
    with pytest.raises(ConfigError, match="hurdle_multiplier"):
        Config.load(write_config(tmp_path, raw))


def test_a_null_anywhere_is_refused(tmp_path: Path) -> None:
    raw = complete_config_dict()
    raw["barriers"]["target_pct"] = None
    with pytest.raises(ConfigError, match="barriers.target_pct"):
        Config.load(write_config(tmp_path, raw))


def test_a_missing_file_is_refused() -> None:
    with pytest.raises(ConfigError, match="not found"):
        Config.load(Path("nope") / "missing.yaml")


def test_an_empty_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError, match="empty"):
        Config.load(path)


def test_the_config_is_immutable(complete: Path) -> None:
    """Nothing may mutate a threshold after startup."""
    config = Config.load(complete)
    with pytest.raises(ValueError, match="frozen|immutable"):
        config.trading.max_concurrent_positions = 99  # type: ignore[misc]


# --------------------------------------------------------------------------
# Ranges
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("barriers", "target_pct", "1.5"),
        ("barriers", "target_pct", "0"),
        ("barriers", "stop_pct", "-0.01"),
        ("safety", "max_drawdown_pct", "1.5"),
        ("trading", "risk_fraction_per_trade", "2"),
        ("trading", "risk_fraction_per_trade", "0"),
        ("trading", "hurdle_multiple", "0"),
        ("safety", "max_consecutive_data_blocks", 0),
        ("safety", "max_consecutive_losses", 0),
        ("console", "port", 0),
        ("console", "port", 70000),
        ("barriers", "timeout_bars", 0),
        ("logging", "retention_days", 0),
    ],
)
def test_a_value_outside_a_sane_range_is_refused(
    tmp_path: Path, section: str, key: str, value: Any
) -> None:
    raw = complete_config_dict()
    raw[section][key] = value
    with pytest.raises(ConfigError, match=key):
        Config.load(write_config(tmp_path, raw))


def test_an_unknown_log_level_is_refused(tmp_path: Path) -> None:
    raw = complete_config_dict()
    raw["logging"]["level"] = "CHATTY"
    with pytest.raises(ConfigError, match="level"):
        Config.load(write_config(tmp_path, raw))


def test_a_loop_tick_that_does_not_divide_the_bar_is_refused(tmp_path: Path) -> None:
    """The decision bar is counted in loop ticks; a tick that does not divide it
    means a bar close can never land on a tick boundary."""
    raw = complete_config_dict()
    raw["timeframes"]["loop_tick_s"] = 7
    with pytest.raises(ConfigError, match="loop_tick"):
        Config.load(write_config(tmp_path, raw))


# --------------------------------------------------------------------------
# paper.starting_balances is a map, not a number
# --------------------------------------------------------------------------


def test_starting_balances_must_be_a_currency_map(tmp_path: Path) -> None:
    """It was a scalar in an earlier revision of the design. One number cannot
    satisfy the per-quote-currency rules of invariant 7."""
    raw = complete_config_dict()
    raw["paper"]["starting_balances"] = 1000
    with pytest.raises(ConfigError, match="currency-to-amount map"):
        Config.load(write_config(tmp_path, raw))


def test_starting_balances_may_not_be_empty(tmp_path: Path) -> None:
    raw = complete_config_dict()
    raw["paper"]["starting_balances"] = {}
    with pytest.raises(ConfigError, match="at least one currency"):
        Config.load(write_config(tmp_path, raw))


def test_starting_balances_may_not_be_negative(tmp_path: Path) -> None:
    raw = complete_config_dict()
    raw["paper"]["starting_balances"] = {"USD": "-1.00"}
    with pytest.raises(ConfigError, match="negative"):
        Config.load(write_config(tmp_path, raw))


def test_starting_balances_are_decimals(complete: Path) -> None:
    balances = Config.load(complete).paper.starting_balances
    assert balances == {"USD": Decimal("1000.00")}
    assert isinstance(balances["USD"], Decimal)


# --------------------------------------------------------------------------
# Decimal, never float
# --------------------------------------------------------------------------


def test_money_values_are_exact_decimals_not_floats(complete: Path) -> None:
    """`0.03` in YAML is a binary float. Reaching `Decimal` through `str()` gives
    exactly `Decimal("0.03")`; going through `Decimal(float)` would give
    0.0299999999999999988897769753748...
    """
    config = Config.load(complete)
    assert config.barriers.target_pct == Decimal("0.03")
    assert str(config.barriers.target_pct) == "0.03"
    assert config.barriers.stop_pct == Decimal("0.015")
    assert isinstance(config.trading.risk_fraction_per_trade, Decimal)
    assert config.trading.hurdle_multiple == Decimal("1.5")


def test_a_float_whose_shortest_repr_is_long_is_refused(tmp_path: Path) -> None:
    """The case where `Decimal(str(value))` would invent precision.

    A YAML float carries about 15-17 significant digits. Below that,
    `str(value)` is the exact text the author wrote and `Decimal(str(value))`
    reproduces it exactly. Above it, `str()` is a 17-digit approximation of a
    binary number and the decimal it produces is not what anyone typed, so the
    loader refuses and asks for a quoted string instead.
    """
    raw = complete_config_dict()
    raw["trading"]["hurdle_multiple"] = 1.2345678901234567
    with pytest.raises(ConfigError, match="quote it"):
        Config.load(write_config(tmp_path, raw))


def test_a_short_float_literal_survives_the_round_trip_exactly(tmp_path: Path) -> None:
    """The guard above must not fire on ordinary values.

    Note what this test cannot prove, because YAML has already thrown the
    information away: writing `0.030000000000000000444089...` in the file parses
    to the same float as `0.03` and is accepted as `Decimal("0.03")`. The author's
    original text is unrecoverable after `yaml.safe_load`, so quoting is the only
    way to state a decimal exactly. That is why `config/default.yaml` says so at
    the top.
    """
    for literal in (0.03, 0.015, 1.5, 0.0001, 12345.678):
        raw = complete_config_dict()
        raw["trading"]["hurdle_multiple"] = literal
        loaded = Config.load(write_config(tmp_path, raw)).trading.hurdle_multiple
        assert loaded == Decimal(str(literal))


def test_a_quoted_money_string_is_read_exactly(tmp_path: Path) -> None:
    raw = complete_config_dict()
    raw["barriers"]["target_pct"] = "0.0300"
    config = Config.load(write_config(tmp_path, raw))
    assert config.barriers.target_pct == Decimal("0.0300")
    assert str(config.barriers.target_pct) == "0.0300"


def test_a_non_numeric_money_value_is_refused(tmp_path: Path) -> None:
    raw = complete_config_dict()
    raw["trading"]["hurdle_multiple"] = "one and a half"
    with pytest.raises(ConfigError, match="hurdle_multiple"):
        Config.load(write_config(tmp_path, raw))


def test_a_boolean_is_not_a_number(tmp_path: Path) -> None:
    raw = complete_config_dict()
    raw["trading"]["hurdle_multiple"] = True
    with pytest.raises(ConfigError, match="hurdle_multiple"):
        Config.load(write_config(tmp_path, raw))


# --------------------------------------------------------------------------
# Seeds, including the `global` keyword collision
# --------------------------------------------------------------------------


def test_the_global_seed_is_aliased_around_the_python_keyword(complete: Path) -> None:
    seeds = Config.load(complete).seeds
    assert seeds.global_ == 20260908
    assert seeds.train == 20260908
    assert seeds.seed_generator == 20260908


# --------------------------------------------------------------------------
# Environment: read here and nowhere else
# --------------------------------------------------------------------------


def test_parse_dotenv_handles_comments_quotes_and_export() -> None:
    parsed = parse_dotenv(
        "\n".join(
            [
                "# a comment",
                "",
                "KRAKEN_API_KEY=plain-value",
                'QUOTED="double quoted"',
                "SQUOTED='single quoted'",
                "export EXPORTED=yes",
                "NO_EQUALS_SIGN",
                "EMPTY=",
            ]
        )
    )
    assert parsed == {
        "KRAKEN_API_KEY": "plain-value",
        "QUOTED": "double quoted",
        "SQUOTED": "single quoted",
        "EXPORTED": "yes",
        "EMPTY": "",
    }


def test_dotenv_never_overrides_an_existing_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A value the operator exported is a deliberate act; a file must not win."""
    env = tmp_path / ".env"
    env.write_text("ACSOE_TEST_VAR=from-file\n", encoding="utf-8")
    monkeypatch.setenv("ACSOE_TEST_VAR", "from-environment")
    load_dotenv(env)
    import os

    assert os.environ["ACSOE_TEST_VAR"] == "from-environment"


def test_a_missing_dotenv_is_not_an_error(tmp_path: Path) -> None:
    assert load_dotenv(tmp_path / "absent") == 0


def test_credentials_are_armed_for_redaction_and_never_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invariant 13. The function that protects a credential must not expose it."""
    monkeypatch.setenv("KRAKEN_API_KEY", "a-long-enough-fake-api-key-value")
    monkeypatch.setenv("KRAKEN_API_SECRET", "a-long-enough-fake-api-secret-value")
    assert arm_secret_redaction() == 2
    assert registered_secret_count() == 2


def test_a_short_credential_is_not_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAKEN_API_KEY", "")
    monkeypatch.delenv("KRAKEN_API_SECRET", raising=False)
    assert arm_secret_redaction() == 0


def test_acsoe_live_is_not_read_here(monkeypatch: pytest.MonkeyPatch, complete: Path) -> None:
    """`ACSOE_LIVE` is switch 1 of invariant 1 and belongs to `live_guard.py` in
    Phase 8. Reading it here — even to ignore it — would put a live switch in the
    module that currently forbids live mode."""
    monkeypatch.setenv("ACSOE_LIVE", "1")
    config = load_config(complete, env_path=Path("does-not-exist"))
    assert config.mode == "paper"
    source = (REPO_ROOT / "src" / "acsoe" / "platform" / "config.py").read_text(encoding="utf-8")
    assert 'os.environ.get("ACSOE_LIVE")' not in source
    assert 'os.environ["ACSOE_LIVE"]' not in source


def test_load_config_arms_redaction_before_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure message from the loader itself must not be able to carry a key."""
    monkeypatch.setenv("KRAKEN_API_KEY", "a-long-enough-fake-api-key-value")
    monkeypatch.delenv("KRAKEN_API_SECRET", raising=False)
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.yaml", env_path=tmp_path / "absent-env")
    assert registered_secret_count() == 1
