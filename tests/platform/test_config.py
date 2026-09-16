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
import re
from collections.abc import Iterator, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from acsoe.engines.market_data_recorder.contracts import BOOK_DEPTH
from acsoe.platform.config import (
    MAX_BOOK_DEPTH,
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

#: The eleven keys the context files name but never value. The operator supplied the
#: first nine on 2026-09-08 and they are marked `Operator-chosen` in the file; before
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
    # Eleventh, supplied 2026-09-10. Invariant 7 defines a crypto-quoted pair as one
    # whose quote is "BTC, ETH, or any non-stable asset" and nothing in the repo held
    # the set of stable assets; Kraken does not supply it either. It decides which
    # pairs are tradable, which is the test the file's own header sets, so it is the
    # operator's and not the lead's. Contrast `kraken.cache_ttl_s`, which is marked in
    # the file but is NOT here: that one is lead-chosen client tuning, ruled 2026-09-10,
    # and the marker test caught the lead adding it. The alarm has now fired twice and
    # been answered both ways, deliberately, which is what it is for.
    "trading.stable_quote_currencies",
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


def test_the_file_marks_exactly_these_eleven_keys_as_the_operator_s() -> None:
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


# --------------------------------------------------------------------------
# Spec 38's two-halves landing: `backtest.embargo_bars`
# --------------------------------------------------------------------------


def test_the_embargo_handoff_is_closed_and_the_key_is_required() -> None:
    """Both halves of spec 38's landing are in, so this no longer asserts two worlds.

    It used to branch on whether `embargo_bars` was in the YAML, because the field was
    optional for the day the two halves were in flight. **That branch is now dead, and a
    dead branch in a test is a claim nobody is checking** — the same shape as an
    `except ImportError` fallback that stays armed after the real thing lands. So the
    test asserts the closed state instead: the key is present, it is a positive int, and
    the model requires it.
    """
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    assert "embargo_bars" in raw["backtest"], (
        "the YAML key was removed while the model field is required; that is the half "
        "of spec 38's dance that refuses at startup, and this says which half"
    )

    config = Config.load(DEFAULT_YAML)
    value = config.get("backtest.embargo_bars")
    assert isinstance(value, int) and not isinstance(value, bool)
    assert value > 0
    assert config.backtest.embargo_bars == value

    field = Config.model_fields["backtest"].annotation.model_fields["embargo_bars"]
    assert field.is_required(), (
        "`embargo_bars` is optional again. It is optional only while the YAML key and "
        "the model field are landing separately; at rest it must be required, so that "
        "removing the key refuses at startup instead of handing a reader None. It is a "
        "leaf, not a section, so `Config.get` returns None rather than raising - see "
        "the docstring on BacktestConfig."
    )


def test_removing_the_embargo_key_is_refused_at_startup(tmp_path: Path) -> None:
    """The whole point of tightening. While the field was optional this config loaded
    and handed `None` to whatever purged on it; now it does not start at all."""
    raw = complete_config_dict()
    del raw["backtest"]["embargo_bars"]
    with pytest.raises(ConfigError, match="embargo_bars"):
        Config.load(write_config(tmp_path, raw))


def test_an_embargo_of_zero_is_refused_rather_than_meaning_no_embargo(tmp_path: Path) -> None:
    """`gt=0` applies whether or not the YAML key has landed. Zero is the value a
    typo produces and the one that silently disables the purge."""
    raw = complete_config_dict()
    raw["backtest"]["embargo_bars"] = 0
    # Matched on the constraint, not just on the key name: `extra="forbid"` also
    # names the key, so `match="embargo_bars"` alone stays green against a model
    # with no such field at all. Proven by mutation, 2026-09-11.
    with pytest.raises(ConfigError, match="embargo_bars: Input should be greater than 0"):
        Config.load(write_config(tmp_path, raw))


def test_a_negative_embargo_is_refused(tmp_path: Path) -> None:
    raw = complete_config_dict()
    raw["backtest"]["embargo_bars"] = -1
    with pytest.raises(ConfigError, match="embargo_bars: Input should be greater than 0"):
        Config.load(write_config(tmp_path, raw))


def test_the_embargo_key_is_accepted_once_supplied(tmp_path: Path) -> None:
    """The half the lead is waiting on: with the field declared, the key parses
    instead of being refused by `extra="forbid"`."""
    raw = complete_config_dict()
    raw["backtest"]["embargo_bars"] = 48
    assert Config.load(write_config(tmp_path, raw)).backtest.embargo_bars == 48


# --------------------------------------------------------------------------
# Spec 61 step 1 — the eight Phase 5 sections
# --------------------------------------------------------------------------
#
# Same two-halves landing as `backtest.embargo_bars` above, eight times over: the
# model fields land first, the lead pastes the YAML, and the sections are then
# tightened from `Section | None = None` to required. Until the paste the shipped
# `config/default.yaml` carries none of them, so every test below builds its own
# config and only `test_the_phase_5_sections_are_landing_in_two_halves` looks at
# the shipped file.
#
# **These values are not the operator's and are not recommendations.** They exist
# so the loader can be exercised on numbers that cannot move. The three operator
# keys — `prediction.di_percentile`, `anomaly.threshold_percentile`,
# `skeptic.veto_threshold` — are deliberately ABSENT from this overlay, because
# absent is the state the engines have to fail closed in and the state the phase
# ships in.

#: The sections as the lead will paste them, minus the three operator keys.
PHASE_5_SECTIONS: dict[str, Any] = {
    "models": {"dir": "models"},
    "features": {
        "version": "test-v0",
        "max_lookback_bars": 96,
        "min_lookback_fill": "0.80",
    },
    "macro": {
        "btc": {"live": "XBT/USD", "archive": "XBTUSD"},
        "eth": {"live": "ETH/USD", "archive": "ETHUSD"},
    },
    "prediction": {
        "di_window_days": 30,
        "di_neighbours": 10,
        "di_reference_rows": 20000,
        "calibration_days": 14,
        "threads": 4,
    },
    "anomaly": {},
    "skeptic": {},
    "regime": {"high_vol_percentile": "0.80", "trend_efficiency": "0.40"},
    "scout": {"rank_descending": True},
    # Requested by the lead at 02:15 on 2026-09-13 for C's trainer, and the ninth
    # section. Hyperparameters are config keys rather than module constants because a
    # run has to be reproducible from its config plus its data, and the manifest
    # carries the config digest — a tree count in a constant is a number the manifest
    # cannot prove.
    "training": {
        "num_trees": 200,
        "learning_rate": "0.05",
        "num_leaves": 31,
        "min_data_in_leaf": 100,
    },
}

#: Every section whose YAML has landed and whose model field is therefore **required**.
#:
#: It agrees with `PHASE_5_SECTIONS` again, which is the resting state: a name here is
#: asserted to be present in the shipped file *and* required on the model, so either
#: half going missing is a red test that says which half. The tuple exists as a
#: separate name rather than as `tuple(PHASE_5_SECTIONS)` because it is what a section
#: mid-landing is temporarily left out of, and the next section to land will want that
#: back.
LANDED_SECTIONS: tuple[str, ...] = (
    "models",
    "features",
    "macro",
    "prediction",
    "anomaly",
    "skeptic",
    "regime",
    "scout",
    "training",
    # Phase 6. Landed 2026-09-16, the same hour the lead pasted it — the window in
    # which the committed config would otherwise have failed to parse is the whole
    # of the time this name was absent from here.
    "order_book",
)

#: The three keys the operator supplies after the walk-forward reports, and the
#: engine that blocks while each is absent. Spec 59 decision 9.
OPERATOR_MODEL_KEYS: tuple[str, ...] = (
    "prediction.di_percentile",
    "anomaly.threshold_percentile",
    "skeptic.veto_threshold",
)


def with_phase_5(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """A complete config carrying the eight Phase 5 sections."""
    base = raw if raw is not None else complete_config_dict()
    for section, values in PHASE_5_SECTIONS.items():
        base[section] = copy.deepcopy(values)
    return base


def load_phase_5(tmp_path: Path, mutate: Any = None) -> Config:
    raw = with_phase_5()
    if mutate is not None:
        mutate(raw)
    return Config.load(write_config(tmp_path, raw))


def test_the_phase_5_landing_is_closed_and_every_section_is_required() -> None:
    """Both halves are in, so this asserts the closed state and not two worlds.

    It branched on whether each section was in the shipped file for the two hours
    the landing was in flight — the fields first, the lead's YAML after. The paste
    happened on 2026-09-13 and the sections were tightened the same hour, so the
    branch is gone: **a dead branch in a test is a claim nobody is checking**, the
    same lesson `test_the_embargo_handoff_is_closed_and_the_key_is_required`
    records one spec earlier.
    """
    shipped = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    for section in LANDED_SECTIONS:
        assert section in shipped, (
            f"{section} has been removed from config/default.yaml while the model "
            "field is required, so the shipped config no longer parses. This names "
            "which half went missing."
        )
        assert Config.model_fields[section].is_required(), (
            f"{section} is optional again. Optional is only for the window between "
            "the two halves; at rest the section must be required, so that deleting "
            "it refuses at startup instead of raising from inside a gate three "
            "chains into a tick."
        )


@pytest.mark.parametrize("section", LANDED_SECTIONS)
def test_removing_a_phase_5_section_is_refused_at_startup(
    tmp_path: Path, section: str
) -> None:
    """What the tightening bought, stated as a test rather than as a comment.

    While the sections were optional this config loaded and every key under the
    missing one raised from wherever it was read. Now the process does not start at
    all, and the message names the section — which is the difference between an
    operator reading one refusal and an agent reading a `ConfigKeyError` traceback
    out of a blocked gate.
    """
    # `with_phase_6` rather than `with_phase_5`, and the assertion is on the whole
    # list of missing sections rather than on a `match=` pattern. **Both are
    # defensive and neither is load-bearing today** — measured, not assumed:
    # swapping `with_phase_6()` back to `with_phase_5()` and weakening the assertion
    # to a bare count both leave all 176 tests green.
    #
    # The reason is worth knowing, because the obvious story is wrong. It is not that
    # the Phase 5 overlay carries `order_book`; it does not. It is that
    # `complete_config_dict()` starts from the **shipped** `config/default.yaml`, so
    # every section the lead has pasted is already in the base and the overlays only
    # pin values on top of it. Which means these cases would still be correct with
    # `with_phase_5()`, for a reason that has nothing to do with Phase 5.
    #
    # They are kept because the failure they guard is real and silent when it does
    # occur: if the base ever stops carrying a required section, every case here
    # would refuse for *that* section as well, and a `match=` on a substring cannot
    # tell. Note that `match=rf"{section}: Field required"` does **not** help —
    # pydantic reports every missing field, so the deleted section's line is in the
    # message whether or not another one sits beside it, and `re.search` finds it.
    # Comparing the whole list is the only form that can say what else went wrong.
    raw = with_phase_6()
    del raw[section]
    with pytest.raises(ConfigError) as refusal:
        Config.load(write_config(tmp_path, raw))

    missing = re.findall(r"- (\w+): Field required", str(refusal.value))
    assert missing == [section], (
        f"deleting {section} should refuse naming {section} and nothing else; the "
        f"refusal named {missing}. More than one name means the base config this "
        f"test builds on is itself incomplete, so the case is not testing what it "
        f"says it tests."
    )


def test_the_training_hyperparameters_parse_and_bound_their_values(
    tmp_path: Path,
) -> None:
    """The section exists and refuses the values that are mistakes rather than choices.

    `learning_rate` is a `Ratio`, so it arrives as an exact `Decimal` and never as a
    binary float — the same rule every other ratio in this file follows, and it matters
    here because the value is written into the artefact manifest that says a run is
    reproducible.
    """
    config = load_phase_5(tmp_path)
    assert config.training is not None
    assert config.training.num_trees == 200
    assert config.training.learning_rate == Decimal("0.05")
    assert config.training.num_leaves == 31
    assert config.training.min_data_in_leaf == 100
    assert config.get("training.num_leaves") == 31


def test_a_single_leaf_is_refused_because_it_is_a_model_that_cannot_learn(
    tmp_path: Path,
) -> None:
    """`num_leaves: 1` is the bound worth its own test, because it fails quietly.

    One leaf per tree is a model that returns the base rate for every input. It trains,
    it scores, and it reports a Brier equal to the fold's base-rate Brier — which is
    precisely the comparison spec 59 decision 4 chose as the primary metric, and an
    operator reading that would conclude the strategy has no edge rather than that the
    model was never allowed to have one. Refusing at startup is the difference between
    a wrong result and no run.
    """

    def mutate(raw: dict[str, Any]) -> None:
        raw["training"]["num_leaves"] = 1

    with pytest.raises(ConfigError, match="Input should be greater than 1"):
        load_phase_5(tmp_path, mutate)


def test_the_shipped_config_loads_with_the_model_sections_in_it() -> None:
    """The property both halves of the landing exist to protect: the committed file
    parses. Every test in every lane reads it."""
    config = Config.load(DEFAULT_YAML)
    assert config.mode == "paper"
    assert config.models.dir == Path("models")
    assert config.features.max_lookback_bars <= config.market_sensor.published_bars


def test_a_complete_phase_5_config_parses_to_the_types_it_claims(tmp_path: Path) -> None:
    """One assertion per section that the values arrive as the declared type.

    A `Ratio` that silently stayed a float would be the money-shaped defect this
    project refuses; a `Path` that stayed a string would build `models/` by string
    concatenation on a Windows target.
    """
    config = load_phase_5(tmp_path)
    assert config.models is not None
    assert config.features is not None
    assert config.macro is not None
    assert config.prediction is not None
    assert config.regime is not None
    assert config.scout is not None

    assert config.models.dir == Path("models")
    assert config.features.version == "test-v0"
    assert config.features.min_lookback_fill == Decimal("0.80")
    assert config.macro["btc"].live == "XBT/USD"
    assert config.macro["btc"].archive == "XBTUSD"
    assert config.prediction.di_neighbours == 10
    assert config.regime.high_vol_percentile == Decimal("0.80")
    assert config.scout.rank_descending is True
    # Dotted access, which is how every engine actually reads a key.
    assert config.get("macro.eth.archive") == "ETHUSD"
    assert config.get("features.max_lookback_bars") == 96


# --- The optional leaves, and the difference between a leaf and a section ---


@pytest.mark.parametrize("key", OPERATOR_MODEL_KEYS)
def test_an_absent_operator_leaf_returns_none_rather_than_raising(
    tmp_path: Path, key: str
) -> None:
    """A's spec 58 finding, restated where the three keys that depend on it live.

    This is not the loader being lax. `Config.get` raises on a key the model does
    not declare and returns the value of one it does — and an unset optional leaf
    *is* declared. The consequence is the whole point: absence does NOT fail closed
    at the point of use, so each of engines 8, 13 and 15 has to refuse the `None`
    by name. A gate that reads it as zero is a gate that has been turned off.
    """
    config = load_phase_5(tmp_path)
    assert config.get(key) is None


@pytest.mark.parametrize(
    "key",
    ("models.prediction_run_id", "models.anomaly_run_id", "models.skeptic_run_id"),
)
def test_an_absent_run_id_returns_none_so_a_fresh_clone_still_starts(
    tmp_path: Path, key: str
) -> None:
    """Invariant 3 on a clone with no `models/`: the engine blocks, the process starts.

    A required run id would be a config that refuses to start until somebody has
    trained something, which would stop the recorder — and order-book history cannot
    be recovered later.
    """
    config = load_phase_5(tmp_path)
    assert config.get(key) is None


def test_an_absent_rank_feature_returns_none(tmp_path: Path) -> None:
    """Spec 59 decision 7: alphabetical while the operator has not ruled."""
    config = load_phase_5(tmp_path)
    assert config.get("scout.rank_feature") is None


def test_the_rank_direction_defaults_to_descending_when_the_key_is_absent(
    tmp_path: Path,
) -> None:
    """Asserted against a config that does NOT carry the key, which is the whole point.

    This test used to read `rank_descending` out of a config whose `scout` block set
    it to `true`, so it pinned a value the fixture had just written and stayed green
    with the field default flipped to `False`. Found by mutation, not by reading it;
    the entry is in the build log. The default is what applies the day the lead omits
    the key, so the only config that can check it is one without it.
    """

    def mutate(raw: dict[str, Any]) -> None:
        raw["scout"] = {}

    assert load_phase_5(tmp_path, mutate).get("scout.rank_descending") is True


def test_an_explicit_false_rank_direction_is_honoured(tmp_path: Path) -> None:
    """The other half: with the key present the file wins, so the test above is
    distinguishing "the default is True" from "the file said True"."""

    def mutate(raw: dict[str, Any]) -> None:
        raw["scout"] = {"rank_descending": False}

    assert load_phase_5(tmp_path, mutate).get("scout.rank_descending") is False


def test_get_answers_three_different_ways_on_the_shipped_model_sections() -> None:
    """A present key, an absent-by-ruling leaf, and a key that does not exist.

    Three outcomes that are easy to conflate and that a reader has to act on
    differently, asserted together against the committed file because that is the
    config every engine actually runs on:

    * a declared key with a value returns it;
    * an optional **leaf** that the operator has not supplied returns `None`, and
      the reader has to refuse that `None` by name;
    * a key the model does not declare at all **raises**, which the orchestrator
      turns into `ERROR`, and `ERROR` blocks.

    **The absent leaf is `models.prediction_run_id` since 2026-09-15.** It was
    `prediction.di_percentile` until the operator ruled that key at 0.99, at which
    point the second case stopped being reachable through it. The run id is the
    right replacement rather than a stand-in: a fresh clone has no `models/`, so it
    is absent by construction rather than by a ruling anyone can revise, which is
    what this case wants. The percentile now serves the first bullet.

    The fourth case — descending into a `None` *section* — was the state during the
    landing window and cannot happen any more: every section is required, so a
    missing one refuses at startup instead. That is a strictly stronger guarantee
    and `test_removing_a_phase_5_section_is_refused_at_startup` is where it lives
    now.
    """
    config = Config.load(DEFAULT_YAML)

    assert isinstance(config.get("prediction.di_window_days"), int)
    assert config.get("prediction.di_percentile") is not None
    assert config.get("models.prediction_run_id") is None
    with pytest.raises(ConfigKeyError, match="no such configuration key"):
        config.get("prediction.di_percentil")


@pytest.mark.parametrize("key", OPERATOR_MODEL_KEYS)
def test_an_operator_leaf_written_as_null_is_refused_rather_than_read_as_absent(
    tmp_path: Path, key: str
) -> None:
    """`di_percentile: null` in the YAML is NOT how "the operator has not chosen" is spelled.

    A null key anywhere in this file is OPERATOR REQUIRED and stops the process by
    name, and that machinery predates these three keys and still applies to them.
    The two states look identical in a diff and are not: the key must be **absent**
    from `config/default.yaml`, and writing it as null refuses at startup. Recorded
    here because it is the mistake the paste of spec 59's YAML block can make, and
    the failure is loud in the right direction.
    """
    section, _, leaf = key.partition(".")

    def mutate(raw: dict[str, Any]) -> None:
        raw[section][leaf] = None

    with pytest.raises(ConfigError, match="OPERATOR REQUIRED"):
        load_phase_5(tmp_path, mutate)


# --- Every new field refuses a bad value --------------------------------------
#
# Matched on the CONSTRAINT message, never on the key name. In a model with
# `extra="forbid"` the refusal for an unknown key always contains the key name, so
# `match="di_percentile"` passes just as happily against a model with no such field
# at all — A found one of its own assertions surviving exactly that mutation in
# Phase 4.

BAD_VALUES: tuple[tuple[str, str, Any, str], ...] = (
    ("models", "dir", "", "models.dir must name a directory"),
    ("models", "dir", ".", "models.dir must name a directory"),
    ("models", "prediction_run_id", "../etc", "must be a bare run id and not a path"),
    ("models", "anomaly_run_id", "runs/2026", "must be a bare run id and not a path"),
    ("models", "skeptic_run_id", "  ", "must be a bare run id"),
    ("features", "version", "", "String should have at least 1 character"),
    ("features", "max_lookback_bars", 0, "Input should be greater than 0"),
    ("features", "max_lookback_bars", -1, "Input should be greater than 0"),
    ("features", "min_lookback_fill", "0", "Input should be greater than 0"),
    ("features", "min_lookback_fill", "1.5", "Input should be less than or equal to 1"),
    ("prediction", "di_window_days", 0, "Input should be greater than 0"),
    ("prediction", "di_neighbours", 0, "Input should be greater than 0"),
    ("prediction", "di_reference_rows", 0, "Input should be greater than 0"),
    ("prediction", "calibration_days", 0, "Input should be greater than 0"),
    ("prediction", "threads", 0, "Input should be greater than 0"),
    ("prediction", "di_percentile", "0", "Input should be greater than 0"),
    ("prediction", "di_percentile", "1", "Input should be less than 1"),
    ("prediction", "di_percentile", "1.2", "Input should be less than 1"),
    ("anomaly", "threshold_percentile", "0", "Input should be greater than 0"),
    ("anomaly", "threshold_percentile", "1", "Input should be less than 1"),
    ("skeptic", "veto_threshold", "0", "Input should be greater than 0"),
    ("skeptic", "veto_threshold", "1", "Input should be less than 1"),
    ("regime", "high_vol_percentile", "1", "Input should be less than 1"),
    ("regime", "high_vol_percentile", "0", "Input should be greater than 0"),
    ("regime", "trend_efficiency", "1", "Input should be less than 1"),
    ("regime", "trend_efficiency", "0", "Input should be greater than 0"),
    ("scout", "rank_feature", "", "must be a feature name"),
    ("scout", "rank_feature", " realised_vol_24 ", "must be a feature name"),
    # The training hyperparameters. Added after a mutation survived: loosening
    # `learning_rate` from (0, 1) to [0, 1] broke nothing, because the section had a
    # parse test and a `num_leaves` test and no bounds test at all. A field with no
    # row here is a field whose constraint is a claim.
    ("training", "num_trees", 0, "Input should be greater than 0"),
    ("training", "num_trees", -1, "Input should be greater than 0"),
    ("training", "learning_rate", "0", "Input should be greater than 0"),
    ("training", "learning_rate", "1", "Input should be less than 1"),
    ("training", "learning_rate", "1.5", "Input should be less than 1"),
    ("training", "num_leaves", 0, "Input should be greater than 1"),
    ("training", "min_data_in_leaf", 0, "Input should be greater than 0"),
)
#: Phase 6's sections keep their own table at the bottom of the file
#: (`BAD_ORDER_BOOK_VALUES`), because a row here is loaded through `load_phase_5` and
#: a section Phase 5 does not carry has nothing to write the bad value into.


@pytest.mark.parametrize(("section", "leaf", "value", "constraint"), BAD_VALUES)
def test_a_bad_value_is_refused_by_its_constraint(
    tmp_path: Path, section: str, leaf: str, value: Any, constraint: str
) -> None:
    def mutate(raw: dict[str, Any]) -> None:
        raw[section][leaf] = value

    with pytest.raises(ConfigError, match=constraint):
        load_phase_5(tmp_path, mutate)


@pytest.mark.parametrize("section", tuple(PHASE_5_SECTIONS))
def test_every_new_section_refuses_an_unknown_key(tmp_path: Path, section: str) -> None:
    """`extra="forbid"` on all eight, `macro`'s asset entries included.

    A typo'd threshold that is silently dropped leaves the system running on a
    default nobody chose, and in this phase that default is inside a gate.
    """

    def mutate(raw: dict[str, Any]) -> None:
        if section == "macro":
            raw[section]["btc"]["achive"] = "XBTUSD"
        else:
            raw[section]["di_percentil"] = "0.95"

    with pytest.raises(ConfigError, match="Extra inputs are not permitted"):
        load_phase_5(tmp_path, mutate)


# --- The cross-section validator ----------------------------------------------


def test_a_lookback_longer_than_engine_3_publishes_is_refused(tmp_path: Path) -> None:
    """The defect this validator exists for is silent in both directions.

    A feature wanting more history than `market_sensor.published_bars` fills
    perfectly in replay, where the archive is on disk, and is NaN live, where engine
    3 publishes a bounded window. Nothing crashes and no test goes red; the model
    simply has a column in training that the live system cannot produce.
    """

    def mutate(raw: dict[str, Any]) -> None:
        raw["features"]["max_lookback_bars"] = raw["market_sensor"]["published_bars"] + 1

    with pytest.raises(ConfigError, match=re.escape("exceeds market_sensor.published_bars")):
        load_phase_5(tmp_path, mutate)


def test_a_lookback_exactly_equal_to_published_bars_is_accepted(tmp_path: Path) -> None:
    """The other side of the boundary, because a validator that is off by one in the
    accepting direction is just as wrong and nothing else would show it."""

    def mutate(raw: dict[str, Any]) -> None:
        raw["features"]["max_lookback_bars"] = raw["market_sensor"]["published_bars"]

    config = load_phase_5(tmp_path, mutate)
    assert config.features is not None
    assert config.features.max_lookback_bars == config.market_sensor.published_bars


# --- The macro mapping --------------------------------------------------------


def test_macro_must_be_a_mapping_of_asset_to_two_spellings(tmp_path: Path) -> None:
    def mutate(raw: dict[str, Any]) -> None:
        raw["macro"] = ["XBT/USD", "ETH/USD"]

    with pytest.raises(ConfigError, match="macro must be a map of asset to pair names"):
        load_phase_5(tmp_path, mutate)


def test_an_empty_macro_map_is_refused(tmp_path: Path) -> None:
    """Empty is not "no macro context": engine 6 would publish nothing while
    reporting `available: true`, and engine 8's feature vector would be short a
    block of columns its manifest names."""

    def mutate(raw: dict[str, Any]) -> None:
        raw["macro"] = {}

    with pytest.raises(ConfigError, match="macro must name at least one asset"):
        load_phase_5(tmp_path, mutate)


def test_a_macro_asset_missing_its_archive_spelling_is_refused(tmp_path: Path) -> None:
    """Both spellings or neither. One of them missing is the case where the live
    engine works and the offline dataset builder silently joins nothing."""

    def mutate(raw: dict[str, Any]) -> None:
        del raw["macro"]["eth"]["archive"]

    with pytest.raises(ConfigError, match="Field required"):
        load_phase_5(tmp_path, mutate)


# --- Phase 6: the `order_book` section ----------------------------------------
#
# Spec 80 owed this section and never landed it; spec 96 step 2 reads
# `order_book.depth`. Same two-halves landing as the nine sections above, and it ran
# in about an hour on 2026-09-16: the model field landed optional, the lead pasted
# the YAML, and the field was tightened to required in the change that also added
# `order_book` to `LANDED_SECTIONS`. Both halves are in. Every test here still builds
# its own config, so a change to the shipped file cannot quietly alter what they
# assert; only `test_the_order_book_landing_is_closed_and_the_section_is_required`
# reads it.
#
# `depth: 10` is the lead's approved value, 2026-09-16, and the reason is the ceiling
# rather than a preference — see `test_the_book_depth_ceiling_agrees_with_the_feed`.

#: The Phase 6 sections, matching what the lead pasted.
PHASE_6_SECTIONS: dict[str, Any] = {
    "order_book": {"depth": 10},
}


def with_phase_6(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """A complete config carrying the Phase 5 sections and the Phase 6 ones."""
    base = with_phase_5(raw)
    for section, values in PHASE_6_SECTIONS.items():
        base[section] = copy.deepcopy(values)
    return base


def load_phase_6(tmp_path: Path, mutate: Any = None) -> Config:
    raw = with_phase_6()
    if mutate is not None:
        mutate(raw)
    return Config.load(write_config(tmp_path, raw))


#: Every `order_book` value that is a mistake rather than a choice, **one row per
#: bound**, and the table is written before the interesting tests below it.
#:
#: That order is the lesson `training` taught one phase ago and it is worth repeating
#: at the top of every new section: `training` shipped with a parse test and one good
#: story test and no bounds rows at all, so loosening `learning_rate` from `(0, 1)` to
#: `[0, 1]` broke nothing and the mutation survived. A field with no row here is a
#: field whose constraint is a claim.
#:
#: Matched on the CONSTRAINT message and never on the key name, for the reason the
#: Phase 5 table states: under `extra="forbid"` a refusal always names the key, so
#: `match="depth"` would pass just as happily against a model with no such field.
BAD_ORDER_BOOK_VALUES: tuple[tuple[str, Any, str], ...] = (
    ("depth", 0, "Input should be greater than 0"),
    ("depth", -1, "Input should be greater than 0"),
    ("depth", MAX_BOOK_DEPTH + 1, "Input should be less than or equal to 10"),
    ("depth", 500, "Input should be less than or equal to 10"),
    ("depth", "ten", "Input should be a valid integer"),
)


@pytest.mark.parametrize(("leaf", "value", "constraint"), BAD_ORDER_BOOK_VALUES)
def test_a_bad_order_book_value_is_refused_by_its_constraint(
    tmp_path: Path, leaf: str, value: Any, constraint: str
) -> None:
    def mutate(raw: dict[str, Any]) -> None:
        raw["order_book"][leaf] = value

    with pytest.raises(ConfigError, match=constraint):
        load_phase_6(tmp_path, mutate)


def test_the_order_book_section_parses_and_engine_9_can_read_its_depth(
    tmp_path: Path,
) -> None:
    """The good story, and it asserts through `get` as well as through the field.

    Engine 9 reads `config.get("order_book.depth")`, not `config.order_book.depth`,
    so an attribute that parses and a key that does not resolve would be a section
    that looks landed from here and raises from inside the engine.
    """
    config = load_phase_6(tmp_path)
    assert config.order_book is not None
    assert config.order_book.depth == 10
    assert config.get("order_book.depth") == 10


# The landing window had its own test here — an absent `order_book` is a **section**
# and not a leaf, so `Config.get("order_book.depth")` raised rather than answering
# `None`, and a reader therefore failed closed rather than reading a depth of zero.
# It is **deleted rather than kept**, because the window closed on 2026-09-16 and the
# state it asserted can no longer be constructed: the field is required, so a config
# without the section does not load at all. What replaced it is stronger and is
# `test_removing_a_phase_5_section_is_refused_at_startup[order_book]` — the process
# does not start, and the refusal names the section. A test whose premise cannot occur
# is a claim nobody is checking, which is the same reason the Phase 5 landing test
# lost its branch.


def test_the_book_depth_ceiling_agrees_with_the_feed(tmp_path: Path) -> None:
    """`MAX_BOOK_DEPTH` is a copy of `BOOK_DEPTH`, and this is what pays for the copy.

    `platform/` sits under `engines/` in the layering, so `config.py` writes the
    integer out rather than importing upwards. A test may import both, and this one
    fails the moment they disagree — which is the only way the duplicate stays
    honest. If the recorder ever subscribes deeper, the ceiling moves with it here
    and not by somebody noticing.
    """
    assert MAX_BOOK_DEPTH == BOOK_DEPTH, (
        "order_book.depth is bounded by how many levels a side the stream is "
        "subscribed at. The two numbers have diverged, so the config now permits a "
        "depth the feed never delivers (or forbids one it does)."
    )
    # And the bound is live at that value, not merely equal to it.
    assert load_phase_6(tmp_path, _set_depth(BOOK_DEPTH)).get("order_book.depth") == BOOK_DEPTH
    with pytest.raises(ConfigError, match="less than or equal to"):
        load_phase_6(tmp_path, _set_depth(BOOK_DEPTH + 1))


def _set_depth(value: Any) -> Any:
    def mutate(raw: dict[str, Any]) -> None:
        raw["order_book"]["depth"] = value

    return mutate


def test_an_order_book_section_without_a_depth_is_refused(tmp_path: Path) -> None:
    """`depth` has no default, and this is what says so.

    A default would be a depth nobody chose, arrived at by deleting a line — and
    unlike a missing *section*, which raises at the reader, a missing *key* under a
    section that parses is invisible everywhere. The section exists, engine 9 starts,
    and it walks however deep the default happens to be.
    """

    def mutate(raw: dict[str, Any]) -> None:
        del raw["order_book"]["depth"]

    with pytest.raises(ConfigError, match="Field required"):
        load_phase_6(tmp_path, mutate)


def test_the_order_book_section_refuses_an_unknown_key(tmp_path: Path) -> None:
    """`extra="forbid"`, like every other section. A typo'd `dept: 25` that was
    silently dropped would leave engine 9 walking a depth nobody chose."""

    def mutate(raw: dict[str, Any]) -> None:
        raw["order_book"]["dept"] = 25

    with pytest.raises(ConfigError, match="Extra inputs are not permitted"):
        load_phase_6(tmp_path, mutate)


def test_the_order_book_landing_is_closed_and_the_section_is_required() -> None:
    """Both halves are in, so this asserts the closed state and not two worlds.

    It branched on whether `order_book:` was in the shipped file for the hour the
    landing was in flight — the field first, the lead's YAML after. The paste
    happened on 2026-09-16 and the field was tightened the same hour, so the branch
    is gone: **a dead branch in a test is a claim nobody is checking**, the same
    lesson `test_the_phase_5_landing_is_closed_and_every_section_is_required`
    records for the nine sections before it.

    The branch did its job on the way past. The paste landed while A was in another
    file and this test is what went red to say so — which is the whole point of
    writing the tripwire before the paste rather than remembering to check after it.
    """
    shipped = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    assert "order_book" in shipped, (
        "order_book has been removed from config/default.yaml while the model field "
        "is required, so the shipped config no longer parses."
    )
    assert Config.model_fields["order_book"].is_required(), (
        "order_book is optional again. Optional is only for the window between the "
        "two halves; at rest the section must be required, so that deleting it "
        "refuses at startup instead of raising from inside engine 9 three chains "
        "into a tick."
    )
    assert "order_book" in LANDED_SECTIONS, (
        "order_book has landed but is not in LANDED_SECTIONS, so nothing asserts "
        "that deleting the section is refused at startup."
    )
