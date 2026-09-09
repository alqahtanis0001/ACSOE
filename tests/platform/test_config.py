"""Spec 07 — the config model, the loader, and every refusal.

The refusals are the point. A config layer that accepts a bad file and carries on
is worse than none: it turns "the operator never chose a risk fraction" into
"something chose one for them".

**The shipped file used to be unstartable and is not any more.** Until 2026-09-08
`config/default.yaml` carried nine null OPERATOR REQUIRED keys and this file
asserted that it refused to load. The operator has now supplied all nine, so that
assertion has moved rather than gone: the refusal is proved against a *fabricated*
config carrying nulls, and the shipped file has acquired the opposite assertion —
that it loads cleanly and every one of the nine parses to the type it is supposed
to be. The nine values are provisional (`context/progress-tracker.md`) and a null
can come back, which is why none of the machinery was weakened to get here.

Three properties have to survive together, and each has its own test below:

1. A null OPERATOR REQUIRED key still stops the process, named.
2. A null *anywhere* still stops the process, so the machinery keeps its teeth
   with zero nulls in the shipped file.
3. The shipped file is known-good, exactly as committed.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from acsoe.platform.config import (
    Config,
    ConfigError,
    ConfigKeyError,
    arm_secret_redaction,
    load_config,
    load_dotenv,
    parse_dotenv,
)
from acsoe.platform.logging import clear_secrets, registered_secret_count

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YAML = REPO_ROOT / "config" / "default.yaml"

#: The nine keys the context files name but never value. The operator supplied all
#: nine on 2026-09-08 and they are marked `Operator-chosen` in the file; before
#: that they were null and marked OPERATOR REQUIRED. Either way this is the set
#: that no agent may choose a value for, and the set the refusal has to name.
OPERATOR_REQUIRED_KEYS: tuple[str, ...] = (
    "safety.max_drawdown_pct",
    "safety.max_consecutive_losses",
    "safety.max_errors_in_window",
    "trading.hurdle_multiple",
    "trading.risk_fraction_per_trade",
    "trading.max_concurrent_positions",
    "trading.entry_unfilled_window_s",
    "trading.base_reporting_currency",
    "paper.starting_balances",
    # Tenth, supplied 2026-09-09. Engine 4's staleness threshold: the whole
    # judgement of the first real gate, which is why the lead would not invent it
    # and the engine raised rather than defaulting until the operator set it.
    "data_guard.max_data_age_s",
)

#: `safety.error_rate_window_s` is the near miss: it lives beside three keys that
#: were operator-required and it never was, because `architecture-context.md`
#: fixes the error rate at the trailing hour. Naming it in a refusal would train
#: the operator to skim the list, and the list is the only thing between a fresh
#: clone and a daemon trading on numbers nobody chose.
NEVER_OPERATOR_REQUIRED = "safety.error_rate_window_s"

#: Test values, deliberately **not** the operator's. They exist so the *loader*
#: can be exercised on a config whose numbers cannot move; they are not defaults,
#: not recommendations, and nothing outside tests may use them. Kept distinct from
#: the shipped values on purpose: the nine in `config/default.yaml` are
#: provisional and will be revised once Phase 3 measures the economics, and a
#: loader test that moves when a trading number is retuned is a loader test that
#: will be edited under pressure. Assertions about the *shipped* numbers belong in
#: `test_default_yaml_*` and nowhere else.
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
    """`config/default.yaml` with the operator's nine replaced by test values.

    Built from the shipped file rather than written out here, so a key the lead
    adds arrives automatically. That is also what keeps this file honest about a
    *tenth* operator-required key: a new null in the shipped file survives the
    overlay, `Config.load` refuses it, and every test using `complete` fails at
    once instead of one of them silently inheriting a number chosen elsewhere.
    """
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    for section, values in OPERATOR_VALUES.items():
        raw[section].update(copy.deepcopy(values))
    return dict(raw)


def with_nulled(raw: dict[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    """Set each dotted key to `None`, the way an unset OPERATOR REQUIRED key looks."""
    for dotted in keys:
        section, _, leaf = dotted.rpartition(".")
        node = raw[section] if section else raw
        assert leaf in node, f"{dotted} is not in the shipped config"
        node[leaf] = None
    return raw


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
# An unset OPERATOR REQUIRED key stops the process
# --------------------------------------------------------------------------
#
# Asserted against a fabricated config, not the shipped one. Until 2026-09-08 the
# shipped file was itself the fixture — it carried all nine as null — and these
# tests read it directly. That was true and is not any more, so the assertion
# moved to a file the test builds. The property it protects has not changed: a
# null OPERATOR REQUIRED key must stop the process by name, whether it is the
# tenth key the lead adds or one of the nine the operator later withdraws.


def test_every_unset_operator_key_is_named_in_one_message(tmp_path: Path) -> None:
    """All nine at once, not the first one nine times over.

    Reporting them one per run is the difference between one conversation with
    the operator and nine, and an operator who has to run the daemon nine times
    to learn what it needs is an operator who fills the last four in by guessing.
    """
    raw = with_nulled(complete_config_dict(), OPERATOR_REQUIRED_KEYS)
    with pytest.raises(ConfigError) as caught:
        Config.load(write_config(tmp_path, raw))
    message = str(caught.value)
    for key in OPERATOR_REQUIRED_KEYS:
        assert key in message
    assert "OPERATOR REQUIRED" in message
    # Naming a key the operator never had to supply trains them to skim the list.
    assert NEVER_OPERATOR_REQUIRED not in message


@pytest.mark.parametrize("key", OPERATOR_REQUIRED_KEYS)
def test_one_unset_operator_key_is_enough_to_refuse(tmp_path: Path, key: str) -> None:
    """Each of the nine on its own, and the message names that one and no other.

    The parametrisation is the point: a refusal that fires only when several keys
    are missing would leave the single-key case — the realistic one, an operator
    revising one number and leaving it blank — starting on a `None` threshold.
    """
    raw = with_nulled(complete_config_dict(), [key])
    with pytest.raises(ConfigError) as caught:
        Config.load(write_config(tmp_path, raw))
    message = str(caught.value)
    assert key in message
    for other in OPERATOR_REQUIRED_KEYS:
        if other != key:
            assert other not in message
    assert NEVER_OPERATOR_REQUIRED not in message


# --------------------------------------------------------------------------
# The shipped file is known-good
# --------------------------------------------------------------------------


def test_default_yaml_loads_cleanly() -> None:
    """The committed file, exactly as committed, starts the system.

    Note what this test does *not* take: the `complete` fixture. No overlay, no
    fill-in, nothing supplied on the way past — because since 2026-09-08 the file
    needs none. That is the whole assertion.
    """
    config = Config.load(DEFAULT_YAML)
    assert config.mode == "paper"
    assert config.console.port == 8765
    assert config.safety.max_consecutive_data_blocks == 15
    assert config.timeframes.loop_tick_s == 60


def test_default_yaml_is_paper_mode() -> None:
    """Asserted on the file's own text as well as on the parsed model, because
    `mode: live` reaching a fresh clone is the one edit nobody may make quietly."""
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    assert raw["mode"] == "paper"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        # Money and rates are Decimal. `0.10` and `0.01` are YAML floats, so the
        # equality is with the decimal the author wrote, reached through `str()`.
        ("safety.max_drawdown_pct", Decimal("0.10")),
        ("trading.hurdle_multiple", Decimal("1.5")),
        ("trading.risk_fraction_per_trade", Decimal("0.01")),
        # Counts and durations are int.
        ("safety.max_consecutive_losses", 5),
        ("safety.max_errors_in_window", 20),
        ("trading.max_concurrent_positions", 3),
        ("trading.entry_unfilled_window_s", 300),
        # A currency code is neither.
        ("trading.base_reporting_currency", "USD"),
        ("paper.starting_balances", {"USD": Decimal("5000.00")}),
    ],
)
def test_every_operator_value_parses_to_the_expected_type(key: str, expected: Any) -> None:
    """The nine, read off the shipped file through the accessor engines will use.

    The type matters as much as the value. `risk_fraction_per_trade` arriving as a
    float rather than a `Decimal` would not fail here, it would fail four phases
    later as an order quantity Kraken rejects, so it is pinned at the boundary
    where it is cheap to see.
    """
    value = Config.load(DEFAULT_YAML).get(key)
    assert value == expected
    if isinstance(expected, dict):
        assert all(isinstance(amount, Decimal) for amount in value.values())
    elif isinstance(expected, Decimal):
        assert isinstance(value, Decimal)
    elif isinstance(expected, int):
        # `isinstance(True, int)` is True, so the strict check is the type itself.
        assert type(value) is int
    else:
        assert type(value) is type(expected)


def test_the_starting_balance_is_quoted_in_yaml_and_keeps_its_cents() -> None:
    """`{USD: "5000.00"}` is quoted for a reason and the quotes are load-bearing.

    Unquoted, YAML reads `5000.00` as the float `5000.0`, `str()` of that is
    `"5000.0"`, and the balance silently loses a decimal place on the way to
    `Decimal`. Quoted, it never touches binary floating point at all: the string
    reaches `Decimal` intact and the exponent survives, which is what makes
    `str()` still read `5000.00`. Asserting the raw YAML type as well as the
    parsed one is deliberate — the parsed value alone cannot tell you which route
    it took, because `Decimal("5000.0") == Decimal("5000.00")`.
    """
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    assert isinstance(raw["paper"]["starting_balances"]["USD"], str)

    balances = Config.load(DEFAULT_YAML).paper.starting_balances
    assert str(balances["USD"]) == "5000.00"


def test_the_file_marks_exactly_these_ten_keys_as_the_operator_s() -> None:
    """The shipped file still agrees with this file about which keys are the
    operator's.

    While the first nine were null, `Config.load(DEFAULT_YAML)` raising was itself the
    check: a tenth key would have appeared in the refusal message and the tests
    would have said so. With zero nulls that signal is gone in one direction —
    the lead can now add a tenth *and supply it*, and nothing would notice. The
    file's `Operator-chosen` marker is the replacement, and it is a documented
    convention rather than a guess: the header of `config/default.yaml` states it.

    The other direction is still covered without a marker at all: a tenth key
    added as `null` survives the overlay in `complete_config_dict` and takes every
    test using the `complete` fixture down with it.
    """
    marked = {
        line.split(":", 1)[0].strip()
        for line in DEFAULT_YAML.read_text(encoding="utf-8").splitlines()
        if "Operator-chosen" in line and ":" in line.split("#", 1)[0]
    }
    assert marked == {key.rpartition(".")[2] for key in OPERATOR_REQUIRED_KEYS}
    assert NEVER_OPERATOR_REQUIRED.rpartition(".")[2] not in marked


def test_the_completed_default_yaml_validates(complete: Path) -> None:
    """The overlay itself loads, so a failure in a test using `complete` is about
    the thing that test changed and not about the fixture."""
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
    with pytest.raises(ConfigError, match=r"barriers\.target_pct"):
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
    with pytest.raises(ValueError, match=r"frozen|immutable"):
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


# --------------------------------------------------------------------------
# The `Config` Protocol's dotted accessor
# --------------------------------------------------------------------------
#
# `core/contracts.py` declares `Config` as two members: a `mode` property and
# `get("safety.max_consecutive_data_blocks")`. The lead chose a dotted accessor
# over a fixed field list so the key names live in `config/default.yaml` and this
# model only, and cannot drift into a third copy inside `core/`. These tests are
# the conformance proof for the half of that Protocol which is not `mode`.


def test_the_model_satisfies_the_config_protocol(complete: Path) -> None:
    contracts = pytest.importorskip("acsoe.core.contracts")
    config = load_config(complete, load_env=False)
    assert isinstance(config, contracts.Config)


def test_get_resolves_a_dotted_path(complete: Path) -> None:
    config = load_config(complete, load_env=False)
    assert config.get("mode") == "paper"
    assert config.get("safety.max_consecutive_data_blocks") == 15
    assert config.get("timeframes.loop_tick_s") == 60


def test_get_returns_money_as_decimal(complete: Path) -> None:
    config = load_config(complete, load_env=False)
    assert config.get("barriers.target_pct") == Decimal("0.03")
    assert isinstance(config.get("barriers.target_pct"), Decimal)


def test_get_descends_into_a_mapping_value(complete: Path) -> None:
    """`paper.starting_balances` is a map, so both it and a currency inside it
    are addressable. A caller that had to special-case the one mapping key in the
    file would be a caller that eventually forgets to."""
    config = load_config(complete, load_env=False)
    assert config.get("paper.starting_balances") == {"USD": Decimal("1000.00")}
    assert config.get("paper.starting_balances.USD") == Decimal("1000.00")


def test_get_reaches_the_seed_aliased_around_the_python_keyword(complete: Path) -> None:
    """`seeds.global` is a perfectly good configuration key and `global` is a
    Python keyword, so the field is `global_` with an alias. A lookup that knew
    only the Python name would work for every key in the file except that one."""
    config = load_config(complete, load_env=False)
    assert config.get("seeds.global") == 20260908
    assert config.get("seeds.global_") == 20260908


@pytest.mark.parametrize(
    "missing",
    [
        "nonexistent",
        "safety.nonexistent",
        "safety.max_drawdown_pct.deeper",
        "paper.starting_balances.EUR",
        "",
        "   ",
    ],
)
def test_get_raises_on_a_miss_and_never_returns_none(complete: Path, missing: str) -> None:
    """The single most important property of the accessor.

    An engine silently receiving `None` for a threshold is the failure this
    project exists to prevent: a null hurdle multiple does not stop a trade, it
    prices one at zero. The raise becomes `ERROR` at the orchestrator, and
    `ERROR` blocks.
    """
    config = load_config(complete, load_env=False)
    with pytest.raises(ConfigKeyError):
        config.get(missing)


def test_a_missing_key_message_names_the_key_and_what_was_available(complete: Path) -> None:
    config = load_config(complete, load_env=False)
    with pytest.raises(ConfigKeyError) as caught:
        config.get("safety.max_drawdown")
    message = str(caught.value)
    assert "safety.max_drawdown" in message
    assert "max_drawdown_pct" in message
    assert message[0] != "'", "KeyError's repr rendering would mangle a multi-line message"


def test_get_has_no_default_parameter() -> None:
    """`dict.get`-shaped signatures invite `config.get(key, fallback)`, and a
    fallback here is a guessed answer to how much money is at risk."""
    import inspect

    parameters = list(inspect.signature(Config.get).parameters)
    assert parameters == ["self", "dotted_key"]
