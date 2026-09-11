"""Configuration: the pydantic model, the loader, and the refusals.

``config/default.yaml`` is parsed into a validated :class:`Config` at startup and
the process refuses to start on an invalid one. There is no partially-valid
config and no "sensible default" applied on the way past a problem — a plausible
default for ``trading.risk_fraction_per_trade`` is a guessed answer to how much
money is at risk.

Three refusals are worth reading before changing anything here.

**Mode.** Phase 0 accepts ``paper`` and nothing else. ``platform/live_guard.py``,
which implements the three switches of invariant 1, is a Phase 8 deliverable.
Until it exists the loader refuses to start on any other mode. The absence of the
guard is not permission, and no code path may promote paper to live implicitly.

**Nulls.** A key written as ``null`` in ``config/default.yaml`` is marked OPERATOR
REQUIRED: the context files name it and value it nowhere, and it is trading
behaviour, so nobody may invent one. It is refused by name rather than defaulted.
The shipped file carried nine such keys until 2026-09-08 and now carries none —
the operator supplied all nine, and they are provisional starting values subject
to revision once Phase 3 measures the economics. This code is unchanged by that
and must stay so: it counts what it finds, the tenth such key is why it exists,
and a withdrawn value has to stop the process exactly as an unsupplied one does.

**Floats.** Every money-valued key is a ``Decimal``. YAML parses ``0.03`` as a
float, so the conversion goes through ``Decimal(str(value))`` — ``str`` of a float
is its shortest round-tripping repr, so ``0.03`` becomes exactly ``Decimal("0.03")``
and never ``0.0299999999999999988...``. A float with more precision than that can
survive is refused, with a message telling the author to quote it.

This module is the **only** place in the system that reads an environment
variable. It deliberately does not read ``ACSOE_LIVE``: that is one of invariant
1's three switches and belongs to ``live_guard.py`` in Phase 8.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any, Final, Literal, Self

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

from acsoe.platform.logging import register_secret

DEFAULT_CONFIG_PATH: Final = Path("config") / "default.yaml"
DEFAULT_ENV_PATH: Final = Path(".env")

#: Environment variables holding credentials. Read here and nowhere else, and
#: registered with the log redactor the moment they enter the process, so the
#: logger is armed before any client that could leak one exists.
CREDENTIAL_ENV_VARS: Final = ("KRAKEN_API_KEY", "KRAKEN_API_SECRET")

#: A float carrying more significant digits than this was never an exact decimal
#: literal, so `Decimal(str(value))` would silently invent precision.
MAX_FLOAT_SIGNIFICANT_DIGITS: Final = 15


class ConfigError(RuntimeError):
    """The configuration is invalid and the process must not start."""


class ConfigKeyError(KeyError):
    """No such configuration key.

    Distinct from :class:`ConfigError` on purpose. ``ConfigError`` means the file
    is invalid and the process must not start; this means running code asked for
    a key that does not exist, which is a defect in that code rather than in the
    operator's file. It is a ``KeyError`` because a failed lookup is what it is,
    so an engine that reaches for a threshold it never had gets an exception the
    orchestrator turns into ``ERROR`` — and ``ERROR`` blocks. Fail closed.

    ``__str__`` is overridden because ``KeyError`` renders its argument with
    ``repr``, which would wrap a multi-line diagnostic in quotes and escape every
    newline in it.
    """

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def _to_decimal(value: Any) -> Any:
    """Coerce a YAML scalar to ``Decimal`` without ever going through binary float
    arithmetic."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("a boolean is not a number")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        text = str(value)
        digits = len(Decimal(text).as_tuple().digits)
        if digits > MAX_FLOAT_SIGNIFICANT_DIGITS:
            raise ValueError(
                f"{value!r} has more precision than a YAML float can carry exactly; "
                "quote it in the config file so it is read as a decimal string"
            )
        return Decimal(text)
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValueError(f"{value!r} is not a decimal number") from exc
    raise ValueError(f"expected a number, got {type(value).__name__}")


Money = Annotated[Decimal, BeforeValidator(_to_decimal)]
#: A ratio expressed as a decimal: 0.03 means 3%. `code-standards.md` — never 3.
Ratio = Annotated[Decimal, BeforeValidator(_to_decimal)]


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


class _Section(BaseModel):
    # A stray key is refused rather than ignored. A typo'd threshold that is
    # silently dropped leaves the system running on a default nobody chose.
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConsoleConfig(_Section):
    port: int = Field(gt=0, lt=65536)
    poll_interval_ms: int = Field(gt=0)
    stale_after_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def _poll_well_below_stale(self) -> Self:
        """`ui-context.md`: the poll interval must stay under a quarter of the
        stale threshold. Without it a slow poll fades the whole screen to half
        opacity permanently, and the operator learns to ignore the one signal
        that says the data is old."""
        limit = self.stale_after_ms / 4
        if self.poll_interval_ms > limit:
            raise ValueError(
                f"console.poll_interval_ms ({self.poll_interval_ms}) must be at most a "
                f"quarter of console.stale_after_ms ({self.stale_after_ms}), i.e. {limit:.0f}"
            )
        return self


class LoggingConfig(_Section):
    level: str = "INFO"
    retention_days: int = Field(gt=0)

    @model_validator(mode="after")
    def _known_level(self) -> Self:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if self.level.upper() not in allowed:
            raise ValueError(f"logging.level must be one of {sorted(allowed)}, got {self.level!r}")
        return self


class TimeframesConfig(_Section):
    decision_bar_s: int = Field(gt=0)
    loop_tick_s: int = Field(gt=0)

    @model_validator(mode="after")
    def _tick_divides_the_bar(self) -> Self:
        """The decision bar is measured in loop ticks. A tick that does not divide
        the bar means `market_sensor` can never land exactly on a bar close."""
        if self.loop_tick_s > self.decision_bar_s:
            raise ValueError(
                "timeframes.loop_tick_s must not exceed timeframes.decision_bar_s"
            )
        if self.decision_bar_s % self.loop_tick_s != 0:
            raise ValueError(
                f"timeframes.decision_bar_s ({self.decision_bar_s}) must be a whole number of "
                f"loop ticks ({self.loop_tick_s})"
            )
        return self


class BarriersConfig(_Section):
    target_pct: Ratio = Field(gt=0, le=1)
    stop_pct: Ratio = Field(gt=0, le=1)
    timeout_bars: int = Field(gt=0)


class SafetyConfig(_Section):
    max_consecutive_data_blocks: int = Field(gt=0)
    max_drawdown_pct: Ratio = Field(gt=0, le=1)
    max_consecutive_losses: int = Field(gt=0)
    error_rate_window_s: int = Field(gt=0)
    max_errors_in_window: int = Field(gt=0)


class TradingConfig(_Section):
    hurdle_multiple: Money = Field(gt=0)
    risk_fraction_per_trade: Ratio = Field(gt=0, le=1)
    max_concurrent_positions: int = Field(gt=0)
    entry_unfilled_window_s: int = Field(gt=0)
    base_reporting_currency: str = Field(min_length=1)
    allow_crypto_quoted: bool

    stable_quote_currencies: frozenset[str] | None = None
    """The quote currencies that are **not** crypto. Requested by A, spec 39.

    Invariant 7 disables crypto-quoted pairs behind :attr:`allow_crypto_quoted` and
    defines one as a pair whose "quote is BTC, ETH, or any non-stable asset". That
    sentence needs a set of stable assets — fiat and stablecoins — and no such set
    exists anywhere in this repository. ``AssetPairs`` carries ``base``, ``quote``,
    ``ordermin``, ``costmin``, ``tick_size`` and the two precisions, and no asset
    class, so nothing about it is derivable at runtime.

    **It is a list of currencies, not a list of pairs**, which is why it does not
    collide with spec 39's scope limit or the Locked Decision behind it: the tradable
    universe is still computed per tick by engine 7 from balances and live prices.
    This names which currencies are stable, which is a fact about the world rather
    than a choice about what to trade.

    Two engines read it and neither may hold its own copy: engine 2's subscription
    scope (A) and engine 7 `scout`'s universe filter (B). Contract rule 3 forbids one
    engine importing another, so config is the seam.

    **Optional at load, and deliberately so, for exactly as long as the YAML is
    absent.** Spec 38 step 1 established the pattern and the reason: the model field
    and the YAML key are two halves of one change with two different owners, and
    `extra="forbid"` plus a required field means whichever half lands first breaks
    every test that loads the committed config. A landed the field, told the lead,
    the lead pasted the block, and the field was then tightened to required. Same
    dance here. ``None`` is not a value and nothing is computed from it — the reader
    in ``engines/market_data_recorder/`` says what it does with the absence, in one
    place, and publishes it.
    """

    @model_validator(mode="after")
    def _currency_is_a_bare_code(self) -> Self:
        code = self.base_reporting_currency
        if code != code.strip() or " " in code:
            raise ValueError(
                f"trading.base_reporting_currency must be a bare currency code, got {code!r}"
            )
        return self

    @model_validator(mode="after")
    def _stable_quotes_are_bare_codes(self) -> Self:
        for code in self.stable_quote_currencies or ():
            if not code or code != code.strip() or " " in code:
                raise ValueError(
                    "trading.stable_quote_currencies must be bare currency codes, "
                    f"got {code!r}"
                )
        return self


def _require_currency_map(value: Any) -> Any:
    if not isinstance(value, dict):
        raise ValueError(
            "paper.starting_balances must be a currency-to-amount map, "
            f'e.g. {{USD: "1000.00"}}, got {type(value).__name__}'
        )
    if not value:
        raise ValueError("paper.starting_balances must name at least one currency")
    for currency in value:
        if not isinstance(currency, str) or not currency.strip():
            raise ValueError(
                f"paper.starting_balances keys must be currency codes, got {currency!r}"
            )
    return value


class PaperConfig(_Section):
    starting_balances: Annotated[dict[str, Money], BeforeValidator(_require_currency_map)]

    @model_validator(mode="after")
    def _balances_are_not_negative(self) -> Self:
        for currency, amount in self.starting_balances.items():
            if amount < 0:
                raise ValueError(
                    f"paper.starting_balances[{currency}] is negative ({amount}); "
                    "a simulated account cannot start overdrawn"
                )
        return self


class CacheTtlConfig(_Section):
    """How long a fetched snapshot may price a decision before it is fetched again.

    **Not a claim about anything Kraken publishes or permits.** It is *our own*
    re-fetch interval, chosen by the operator, and it holds no exchange-supplied
    value: no fee, no minimum, no tick size, no precision.

    **Two keys and not one.** Pair rules change when Kraken lists or delists
    something; a fee tier can move on a single trade and it prices the cost gate.
    They are read separately by ``clients/kraken/rest.py`` and a single shared TTL
    is the shape spec 38 exists to prevent.

    Invariant 2: a cache stale beyond its TTL **counts as a failed fetch**. It is not
    returned and the call raises. That is a different mechanism from the
    last-known-good retention in ``clients/kraken/``, which keeps the same values
    forever, past any TTL, and may be read only by invariant 14's emergency
    liquidation. Two mechanisms, two readers; do not merge them.
    """

    asset_pairs: int = Field(gt=0)
    """Seconds a ``PairRulesSnapshot`` may be reused for."""

    trade_volume: int = Field(gt=0)
    """Seconds a ``FeeTierSnapshot`` may be reused for."""


class KrakenConfig(_Section):
    """Exchange-client tuning.

    **Nothing in this section is something the exchange can tell us.** No fee, no order
    minimum, no tick size, no precision — those are fetched at runtime, every time,
    under rule 2 of ``context/trading-invariants.md``. What is here is *our own
    self-imposed request budget and timeout*, chosen by the lead, and it is explicitly
    **not a claim about what Kraken permits**: a remembered published rate limit is
    exactly the stale knowledge ``AGENTS.md`` warns about. It is deliberately
    conservative — under the real ceiling costs latency, over it costs a ban mid-session
    — and is flagged for revision against the documented limits before Phase 8.
    """

    rest_capacity: int = Field(gt=0)
    """Token-bucket depth: the largest burst of REST calls permitted at once."""

    rest_refill_per_s: Ratio = Field(gt=0)
    """Sustained REST call rate, in calls per second."""

    rest_timeout_s: int = Field(gt=0)
    """HTTP timeout for one REST call."""

    cache_ttl_s: CacheTtlConfig
    """How long ``AssetPairs`` and ``TradeVolume`` may be reused. Spec 38 step 1.

    **Required, since 2026-09-10, and it was deliberately optional for the few hours
    before that.** The two halves of spec 38 step 1 land in one change: A adds this
    field, the lead pastes the block from spec 37's appendix. While the YAML had not
    landed, a required field would have made ``load_config()`` raise on the committed
    ``config/default.yaml`` — the same failure that reverted the lead's attempt
    earlier the same day, with the halves reversed. It was declared
    ``CacheTtlConfig | None = None`` for exactly as long as that gap existed, with
    every reader raising on the ``None`` rather than defaulting, and tightened the
    moment the YAML was in. The build log carries the decision and the reversal.

    Required is the stronger of the two and is the right resting state: a withdrawn
    TTL now refuses at startup, by name, rather than blocking at the first fetch. A
    ``null`` is refused by :func:`_refuse_nulls` before pydantic ever sees it, which
    is what spec 38 step 3 asks for.

    ``clients/kraken/rest.py`` still raises on an absent TTL rather than assuming one,
    and that is not now-dead code: :class:`KrakenRestClient` is constructed directly
    by tests and by ``scripts/``, not only from a validated :class:`Config`, so the
    fail-closed path is the one a caller that forgot to pass a TTL takes.
    """


class MarketSensorConfig(_Section):
    """Engine 3 tuning.

    ``published_bars`` is a **plumbing bound, not a trading threshold** — no gate reads
    it and no money depends on it, which is why the lead may choose it and it is not
    OPERATOR REQUIRED. It bounds how many recent closed 15-minute candles reach
    ``state`` each tick, so ``state`` stays serialisable and the payload stays bounded.
    """

    published_bars: int = Field(gt=0)


class DataGuardConfig(_Section):
    """Engine 4's staleness threshold. **A trading threshold, operator-chosen.**

    Market data older than ``max_data_age_s`` blocks the tick. It is the whole judgement
    of the first real gate in the system, which is why the lead would not invent it and
    the engine raised rather than defaulting until the operator supplied a value on
    2026-09-09.

    Deliberately **not** ``console.stale_after_ms``. That one is a rendering rule about
    fading a figure to half opacity and decides nothing about trading; this one decides
    whether the system is allowed to act on what it can see. Two keys, two axes, and
    collapsing them would let a display preference gate a trade.
    """

    max_data_age_s: int = Field(gt=0)


class BacktestConfig(_Section):
    """Walk-forward training cadence, plus the embargo the splitter purges on.

    ``embargo_bars`` was declared ``int | None = None`` for one day — 2026-09-11 — while
    spec 38's two-halves landing was in flight. ``extra="forbid"`` means the YAML key and
    the model field cannot be separated in either order: the key alone is refused at load,
    and a required field alone makes the committed ``config/default.yaml`` fail to parse,
    taking ``scripts/verify.py`` and every test that reads the shipped config with it.
    Optional was the only state in which both halves load. **Both halves have landed and
    it is required again**, so a later removal now refuses at startup rather than blocking
    at the point of use.

    **The reason that window was dangerous is worth keeping, because it is not the reason
    the ``kraken.cache_ttl_s`` handoff would have led you to expect.** ``cache_ttl_s`` is a
    nested *section*: ``Config.get("kraken.cache_ttl_s.asset_pairs")`` raised
    ``ConfigKeyError`` while it was ``None``, because the walk had to descend *into* the
    ``None`` and descending into a non-model raises. ``embargo_bars`` **is** the leaf, so
    the walk ends on it and ``Config.get`` returns ``None`` — exactly as
    ``trading.stable_quote_currencies`` does. **The optional-field handoff pattern only
    fails closed for keys nested under an optional section. For an optional leaf the window
    between the two halves is a window in which a reader silently gets ``None``**, and a
    zero embargo is the Phase 4 failure that looks like success: no crash, no red test, just
    a flattering model. ``research/walkforward.py`` refuses a missing or null key rather than
    defaulting, which is the half of that seam this model cannot enforce.
    """

    training_window_days: int = Field(gt=0)
    retrain_interval_days: int = Field(gt=0)
    embargo_bars: int = Field(gt=0)


class SeedsConfig(_Section):
    # `global` is a Python keyword, so the field is aliased. `populate_by_name`
    # lets code refer to it as `global_` while the YAML keeps the readable name.
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    global_: int = Field(alias="global")
    train: int
    seed_generator: int


# ---------------------------------------------------------------------------
# The config
# ---------------------------------------------------------------------------


class Config(BaseModel):
    """The whole configuration, validated. Satisfies the ``Config`` Protocol in
    ``core/contracts.py``; ``core/`` declares the shape, ``platform/`` implements it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["paper", "live", "replay"]
    console: ConsoleConfig
    logging: LoggingConfig
    timeframes: TimeframesConfig
    barriers: BarriersConfig
    safety: SafetyConfig
    trading: TradingConfig
    paper: PaperConfig
    kraken: KrakenConfig
    market_sensor: MarketSensorConfig
    data_guard: DataGuardConfig
    backtest: BacktestConfig
    seeds: SeedsConfig

    @model_validator(mode="after")
    def _phase_0_forces_paper(self) -> Self:
        """Invariant 1. ``platform/live_guard.py`` is a Phase 8 deliverable.

        Until it exists this loader is the only thing standing between a config
        file and real money, so it fails closed. Do not add a flag that skips
        this, and do not implement the three switches here — they belong to
        ``live_guard.py``, and three conditions checked in the module that
        forbids them is not a guard.
        """
        if self.mode == "live":
            raise ValueError(
                "mode: live is refused. Live trading requires all three switches of "
                "invariant 1 in context/trading-invariants.md, implemented in "
                "platform/live_guard.py, which is a Phase 8 deliverable and does not "
                "exist yet. The absence of the guard is not permission. Set mode: paper."
            )
        if self.mode != "paper":
            raise ValueError(
                f"mode: {self.mode} is refused. Phase 0 accepts mode: paper only; "
                "replay is built in Phase 4 and live in Phase 8."
            )
        return self

    def get(self, dotted_key: str, /) -> Any:
        """Look up a value by dotted path, e.g. ``"safety.max_consecutive_data_blocks"``.

        The second half of the ``Config`` Protocol in ``core/contracts.py``. The
        lead chose a dotted accessor over a fixed field list so that the key
        names live in ``config/default.yaml`` and this model only, and cannot
        drift into a third copy inside ``core/``.

        **Raises on a miss. Never returns a default, and never returns None to
        mean "absent".** An engine silently receiving ``None`` for a threshold is
        the exact failure this project exists to prevent: a null hurdle multiple
        does not stop a trade, it prices one at zero. The raise becomes ``ERROR``
        at the orchestrator, and ``ERROR`` blocks.

        Descends through sections and through mapping values alike, so both
        ``"paper.starting_balances"`` and ``"paper.starting_balances.USD"``
        resolve. Section field names are matched by their YAML name as well as
        their Python name, which is what makes ``"seeds.global"`` work against a
        field Python will not let anyone call ``global``.
        """
        if not dotted_key or not dotted_key.strip():
            raise ConfigKeyError("a configuration key must be a non-empty dotted path")

        node: Any = self
        walked: list[str] = []
        for part in dotted_key.split("."):
            if isinstance(node, BaseModel):
                found, child = _model_attribute(node, part)
                if not found:
                    raise ConfigKeyError(
                        _no_such_key(dotted_key, walked, part, _model_keys(node))
                    )
                node = child
            elif isinstance(node, dict):
                if part not in node:
                    raise ConfigKeyError(
                        _no_such_key(dotted_key, walked, part, sorted(str(k) for k in node))
                    )
                node = node[part]
            else:
                raise ConfigKeyError(
                    f"configuration key {dotted_key!r} is not resolvable: "
                    f"{'.'.join(walked) or '<root>'} is a {type(node).__name__}, "
                    f"which has no member {part!r}"
                )
            walked.append(part)
        return node

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        """Parse and validate. Raises :class:`ConfigError` and never returns a
        half-valid config."""
        config_path = (path or DEFAULT_CONFIG_PATH).resolve()
        if not config_path.is_file():
            raise ConfigError(f"configuration file not found: {config_path}")

        raw = load_yaml_mapping(config_path)
        _refuse_nulls(raw, config_path)

        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise ConfigError(_readable(exc, config_path)) from exc


def _model_keys(model: BaseModel) -> list[str]:
    """The names a section answers to, as they appear in the YAML."""
    fields = type(model).model_fields
    return sorted(info.alias or name for name, info in fields.items())


def _model_attribute(model: BaseModel, part: str) -> tuple[bool, Any]:
    """Resolve one path segment against a section, by YAML name or Python name.

    Both, because ``seeds.global`` is a perfectly good configuration key and
    ``global`` is a Python keyword, so the field is ``global_`` with an alias. A
    lookup that knew only one of the two names would work for every key in the
    file except that one, which is precisely the kind of gap nobody finds until
    a training run cannot read its seed.
    """
    fields = type(model).model_fields
    for name, info in fields.items():
        if part in (name, info.alias or name):
            return True, getattr(model, name)
    return False, None


def _no_such_key(dotted_key: str, walked: list[str], part: str, available: list[str]) -> str:
    location = ".".join(walked) or "<root>"
    return (
        f"no such configuration key: {dotted_key!r}. "
        f"{location} has no member {part!r}. "
        f"Available at {location}: {', '.join(available)}. "
        "A missing configuration key is a defect, not a reason to fall back to a default."
    )


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    """`yaml.safe_load` only, never `yaml.load` — the restriction under which the
    dependency was approved."""
    with path.open("r", encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle)
    if parsed is None:
        raise ConfigError(f"configuration file is empty: {path}")
    if not isinstance(parsed, dict):
        raise ConfigError(f"configuration file must be a mapping, got {type(parsed).__name__}")
    return parsed


def _null_paths(node: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if value is None:
                found.append(path)
            else:
                found.extend(_null_paths(value, path))
    return found


def _refuse_nulls(raw: dict[str, Any], path: Path) -> None:
    """Refuse every null key by name, all of them at once.

    ``config/default.yaml`` marks a null key OPERATOR REQUIRED: the context files
    name it and never specify its value, and it is trading behaviour, so nobody
    may invent one. Reporting all of them together rather than one per run is the
    difference between one conversation with the operator and nine — an operator
    who has to start the daemon nine times to learn what it needs is an operator
    who fills the last four in by guessing.

    Deliberately counts what it finds rather than checking a list of key names.
    The shipped file has carried nine of these and now carries none; a hard-coded
    list would have had to be edited on both of those days and would be a second
    place for the set to drift from ``config/default.yaml``.
    """
    nulls = _null_paths(raw)
    if not nulls:
        return
    listed = "\n".join(f"  - {name}" for name in nulls)
    raise ConfigError(
        f"{len(nulls)} configuration value(s) in {path} are null and must be supplied by the "
        f"operator before the system can start:\n{listed}\n"
        "These are marked OPERATOR REQUIRED in the file. Each one is trading behaviour that "
        "the context files name but never value, so no agent may choose it and no default is "
        "applied. Refusing to start is deliberate: a plausible default here is a guessed "
        "answer to how much money is at risk."
    )


def _readable(exc: ValidationError, path: Path) -> str:
    lines = [f"configuration in {path} is invalid:"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        lines.append(f"  - {location}: {error['msg']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse a ``.env`` file. ``KEY=VALUE``, ``#`` comments, optional quotes.

    Deliberately minimal and stdlib-only: no interpolation, no command
    substitution, no multi-line values. A config parser that can execute
    something is a config parser that will, and adding a dependency for fifteen
    lines is not worth an escalation.
    """
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_dotenv(path: Path | None = None) -> int:
    """Load ``.env`` into the process environment. Returns how many were set.

    An existing environment variable always wins: a value already exported by the
    operator is a deliberate act and a file must not override it.
    """
    env_path = path or DEFAULT_ENV_PATH
    if not env_path.is_file():
        return 0
    loaded = 0
    for key, value in parse_dotenv(env_path.read_text(encoding="utf-8")).items():
        if key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


@dataclass(frozen=True)
class Credentials:
    """A Kraken API key pair, carried without ever being renderable.

    ``__repr__`` and ``__str__`` are overridden together and both return a constant.
    That is not belt and braces: the single most common way a key reaches a log is
    that nobody logged it — an exception was formatted, or a dataclass holding it
    was interpolated into a message, and the default ``repr`` printed every field.
    ``platform/logging.py``'s value scrubber is the second line of defence and this
    is the first, because the scrubber only protects lines that go through the
    logger.

    Constructed only by :func:`load_credentials`, which is the only reader of the
    environment in the system.
    """

    key: str
    secret: str

    def __repr__(self) -> str:
        return "Credentials(key=<redacted>, secret=<redacted>)"

    def __str__(self) -> str:
        return self.__repr__()


def load_credentials(*, arm_redaction: bool = True) -> Credentials | None:
    """The Kraken key pair from the environment, or None when it is not set.

    Returns None rather than raising, because a missing key is the normal state of a
    fresh clone: paper mode runs the whole pipeline without one, and invariant 2's
    paper fallbacks exist exactly so that it can. The caller decides whether the
    absence blocks — in live mode it does.

    Registers both values with the log redactor before returning them, so a client
    built from this can never be the first thing to leak one.
    """
    key = os.environ.get("KRAKEN_API_KEY", "").strip()
    secret = os.environ.get("KRAKEN_API_SECRET", "").strip()
    if not key or not secret:
        return None
    if arm_redaction:
        register_secret(key)
        register_secret(secret)
    return Credentials(key=key, secret=secret)


def arm_secret_redaction() -> int:
    """Register every credential in the environment with the log redactor.

    Called at startup, before any client exists. Returns the count — never a
    value. Invariant 13: a credential is never logged, printed or echoed, and
    that includes by the function whose job is to protect it.
    """
    armed = 0
    for name in CREDENTIAL_ENV_VARS:
        if register_secret(os.environ.get(name)):
            armed += 1
    return armed


def load_config(
    path: Path | None = None,
    *,
    env_path: Path | None = None,
    load_env: bool = True,
) -> Config:
    """The startup entry point: load ``.env``, arm redaction, then validate the config.

    Redaction is armed *before* the config is parsed, so even a failure message
    from this function cannot carry a credential.
    """
    if load_env:
        load_dotenv(env_path)
        arm_secret_redaction()
    return Config.load(path)
