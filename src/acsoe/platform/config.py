"""Configuration: the pydantic model, the loader, and the refusals.

``config/default.yaml`` is parsed into a validated :class:`Config` at startup and
the process refuses to start on an invalid one. There is no partially-valid
config and no "sensible default" applied on the way past a problem — a plausible
default for ``trading.risk_fraction_per_trade`` is a guessed answer to how much
money is at risk.

Three refusals are worth reading before changing anything here.

**Mode.** ``live`` is refused. ``platform/live_guard.py``, which implements the
three switches of invariant 1, is a Phase 8 deliverable, and until it exists the
loader refuses to start in live mode. The absence of the guard is not permission,
and no code path may promote paper to live implicitly. ``paper`` is the default.
``replay`` is accepted since Phase 7 for the offline replay (spec 129), which builds
its config in memory and never reaches the exchange; ``acsoe engine`` refuses it.

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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
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


class DatasetConfig(_Section):
    """Which labelled rows and pairs form the training dataset.

    Two operator rulings of 2026-09-12, recorded under Locked Decisions in
    ``context/progress-tracker.md``. ``decision_start_date`` is an ISO calendar date, UTC;
    ``research/labelling.py`` turns it into the first permitted ``decision_ts`` and
    excludes every decision bar before it, reporting the count per pair. The exclusion is
    about tradability rather than data quality. ``min_labelled_rows`` is a per-pair floor
    read by engine 23 ``backtest``; ``0`` means no floor and is the committed value.

    It is ``0`` and not ``null`` because :func:`_refuse_nulls` treats a null key as
    OPERATOR REQUIRED and stops the process. That is the right rule for a trading
    threshold and it would make an off-by-default research knob impossible to ship, so
    the absence of a floor is spelled as a number rather than as a hole.
    """

    decision_start_date: date
    min_labelled_rows: int = Field(ge=0)


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
    """The staleness threshold, **read by three gates.** A trading threshold, operator-chosen.

    **Engine 4** blocks the tick when the *freshest* quote is older than
    ``max_data_age_s`` — the feed has gone quiet. **Engine 7** excludes any one pair whose
    quote is older, under ``no_live_quote``. **Engine 16** refuses an order whose chosen
    pair's quote is older, reading engine 4's published copy of this value because it may
    not read config itself. One number, one meaning of "too old", in all three (D10,
    operator ruling 2026-09-21).

    **It used to block the tick on the oldest quote of any pair**, which with Kraken's 668
    USD pairs meant always: some thin pair is always quiet for two minutes, and the first
    smoke run against the real exchange blocked 18 of 22 ticks on it. That is why it is no
    longer "the whole judgement" of engine 4 — the feed-wide half stays there and the
    per-pair half moved to the gates that judge pairs.

    The lead would not invent the value, and engine 4 raised rather than defaulting until
    the operator supplied one on 2026-09-09.

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


# ---------------------------------------------------------------------------
# Phase 5 — the model sections
# ---------------------------------------------------------------------------
#
# Eight sections landed by spec 61 step 1. Every one of them is declared on
# :class:`Config` as ``Section | None = None`` **for exactly as long as the
# lead's YAML block is not in `config/default.yaml`**, and is tightened to
# required the moment it is. That dance is `code-standards.md` Configuration and
# it is not optional: `extra="forbid"` means a YAML key without its model field
# is refused at load, and a required model field without its YAML key makes the
# committed config fail to parse — which takes `scripts/verify.py` and every test
# in every lane that reads the shipped config with it. Optional is the only state
# in which both halves load, and required is the right resting state, because a
# withdrawn section then refuses at startup by name instead of surfacing as a
# `ConfigKeyError` from inside an engine three chains later.
#
# **An absent *section* fails closed; an absent *leaf* does not.** ``Config.get``
# walks the dotted path, and descending *into* a ``None`` raises
# ``ConfigKeyError`` — so while a section is ``None`` every key under it raises,
# which is what a reader wants. A leaf that is present-and-``None`` is the end of
# the walk, so ``get`` **returns ``None``**. That is A's spec 58 finding, it is
# why each optional leaf below says so in its own docstring, and it is why every
# reader of one has to refuse the ``None`` explicitly rather than treat it as
# zero. A zero DI percentile, a zero anomaly threshold or a zero veto threshold
# is not a conservative default — it is a gate that has been turned off.


class ModelsConfig(_Section):
    """Where trained artefacts live, and which run each model engine loads.

    ``dir`` is the root of ``models/<run_id>/`` described under Storage in
    ``context/architecture-context.md``. ``platform/paths.py`` creates it at startup
    beside ``data/`` and ``logs/``; the artefacts inside it are C's and are written
    once and never overwritten. An engine reaches a run through
    ``context.clients.store.model_run_dir(run_id)`` and never by building a path,
    which is contract rule 4.

    **The three run ids are optional leaves and a fresh clone has none.** That is the
    whole reason they are ``None`` rather than required: a clone with no ``models/``
    must still start, run its loop, record market data and build candles. Engines 8,
    13 and 15 block when the key is absent — invariant 3, fail closed — and the
    process does not refuse to start. ``Config.get("models.prediction_run_id")``
    therefore **returns ``None`` rather than raising**, so every reader must test for
    it by name and must never treat the absence as "load the latest": there is no
    "latest" anywhere in this system, by design, because a run that cannot be named
    is a result nobody can reproduce.
    """

    dir: Path
    """Root of the artefact tree. Created by ``platform/paths.py``, never by an engine."""

    prediction_run_id: str | None = None
    """Run id engine 8 ``prediction`` loads. Absent means the engine blocks.

    Optional **leaf**: ``Config.get`` returns ``None`` for it rather than raising.
    """

    anomaly_run_id: str | None = None
    """Run id engine 13 ``anomaly`` loads. Absent means the gate blocks.

    Optional **leaf**: ``Config.get`` returns ``None`` for it rather than raising.
    """

    skeptic_run_id: str | None = None
    """Run id engine 15 ``skeptic`` loads. Absent means the gate blocks.

    Optional **leaf**: ``Config.get`` returns ``None`` for it rather than raising.
    """

    @model_validator(mode="after")
    def _dir_is_a_real_path(self) -> Self:
        text = str(self.dir).strip()
        if not text or text == ".":
            raise ValueError(
                "models.dir must name a directory, and an empty value resolves to the "
                "working directory, which would scatter run directories across the "
                "repository root"
            )
        return self

    @model_validator(mode="after")
    def _run_ids_are_bare_names(self) -> Self:
        """A run id becomes a directory name under ``models.dir``.

        Refused here rather than at the point of use because B's ``model_run_dir``
        raises on a traversal-shaped id (spec 62) and the operator should learn about
        a malformed one at startup rather than from a blocked gate three chains into a
        tick. Both refusals stay: this one is a convenience, that one is the boundary.
        """
        for name, value in (
            ("prediction_run_id", self.prediction_run_id),
            ("anomaly_run_id", self.anomaly_run_id),
            ("skeptic_run_id", self.skeptic_run_id),
        ):
            if value is None:
                continue
            if not value.strip() or value != value.strip():
                raise ValueError(f"models.{name} must be a bare run id, got {value!r}")
            if "/" in value or "\\" in value or value in (".", ".."):
                raise ValueError(
                    f"models.{name} must be a bare run id and not a path, got {value!r}"
                )
        return self


class FeaturesConfig(_Section):
    """The feature layer's version and its lookback bounds.

    ``version`` is written into every artefact manifest and compared on load, so an
    engine can never score a model with features computed by different arithmetic.

    ``max_lookback_bars`` is bounded by ``market_sensor.published_bars`` — the
    cross-section validator on :class:`Config` refuses it above that. Engine 3
    publishes only that many closed bars into ``state`` each tick, so a feature
    wanting more could never be filled live while filling perfectly in replay over
    the archive. That is a *silent* divergence between live and replay, which is the
    one class of defect Phase 5 exists to be careful about.

    ``min_lookback_fill`` is the fraction of a time window that must actually carry
    bars before a feature over it is a number rather than NaN. The archives only
    contain intervals where trades occurred, so a 200-bar window can hold twelve
    bars; nothing is interpolated. **Zero is refused** rather than meaning "no
    floor": a window with no bars in it yields a feature computed from nothing, and
    a model trained on those has learned the shape of the gaps.
    """

    version: str = Field(min_length=1)
    max_lookback_bars: int = Field(gt=0)
    min_lookback_fill: Ratio = Field(gt=0, le=1)


class MacroAssetConfig(_Section):
    """The two spellings of one macro pair: live and archive.

    Kraken's WebSocket names a pair ``XBT/USD``; its downloadable archive names the
    same pair ``XBTUSD``. Engine 6 ``macro_context`` reads the live spelling out of
    ``state["feature"]["pairs"]`` and spec 67's dataset builder joins the archive
    spelling, and a hardcoded translation between the two in either place is a
    mapping that can disagree with itself. Both come from here.
    """

    live: str = Field(min_length=1)
    archive: str = Field(min_length=1)


def _require_macro_map(value: Any) -> Any:
    if not isinstance(value, dict):
        raise ValueError(
            "macro must be a map of asset to pair names, "
            'e.g. {btc: {live: "XBT/USD", archive: "XBTUSD"}}, '
            f"got {type(value).__name__}"
        )
    if not value:
        raise ValueError("macro must name at least one asset")
    for asset in value:
        if not isinstance(asset, str) or not asset.strip() or asset != asset.strip():
            raise ValueError(f"macro keys must be bare asset names, got {asset!r}")
    return value


#: ``macro`` is a mapping and not a section: the asset names are the operator's
#: choice, so ``extra="forbid"`` cannot apply at that level and would forbid the
#: only thing that varies. The *value* of every entry is a forbidding section, so a
#: typo inside one is still refused.
MacroAssets = Annotated[dict[str, MacroAssetConfig], BeforeValidator(_require_macro_map)]


class PredictionConfig(_Section):
    """Engine 8 and its Dissimilarity Index.

    The first five keys are plumbing the lead chooses: they size the DI's reference
    set, the calibration slice and the trainer's thread count, and no gate reads them
    and no order is sized from them.

    ``di_percentile`` is different and is the operator's. It is the quantile of the
    leave-one-out distance distribution at which engine 8 stops predicting, so it
    decides how strange a market has to look before the system refuses to have an
    opinion about it. **Absent until the walk-forward reports** (spec 59 decision 9),
    and the engine blocks meanwhile.
    """

    di_window_days: int = Field(gt=0)
    """How many days of the training window, per pair, form the DI reference set."""

    di_neighbours: int = Field(gt=0)
    """``k`` in the mean k-nearest distance that is the DI of a vector."""

    di_reference_rows: int = Field(gt=0)
    """Cap on reference rows after subsampling with ``seeds.train``."""

    calibration_days: int = Field(gt=0)
    """Trailing days of the *training* window used to calibrate, never the test window."""

    threads: int = Field(gt=0)
    """Trainer thread count. Reproducibility is from the seeds, not from a thread count."""

    di_percentile: Ratio | None = Field(default=None, gt=0, lt=1)
    """OPERATOR REQUIRED, absent until supplied. Engine 8 blocks while it is.

    Optional **leaf**: ``Config.get("prediction.di_percentile")`` returns ``None``
    rather than raising, so the reader must refuse the ``None`` explicitly. Treating
    it as zero would set the threshold at the minimum observed distance and refuse
    every candidate; treating it as one would refuse none. The first is merely
    useless and the second is the one that flatters.

    Bounded below 1 rather than at it for that reason: a percentile of exactly 1
    puts the threshold at the largest distance in the reference set, so nothing can
    exceed it and the check is off while still looking configured.
    """


class AnomalyConfig(_Section):
    """Engine 13's veto threshold, as a percentile of the fitted score distribution."""

    threshold_percentile: Ratio | None = Field(default=None, gt=0, lt=1)
    """OPERATOR REQUIRED, absent until supplied. The gate blocks while it is.

    Optional **leaf**: ``Config.get`` returns ``None`` rather than raising. Same
    bounds and the same reasoning as ``prediction.di_percentile``: at 1 the gate
    passes everything while reading as configured, which is a gate that has been
    turned off rather than tuned.
    """


class SkepticConfig(_Section):
    """Engine 15's veto threshold on ``p_wrong``."""

    veto_threshold: Ratio | None = Field(default=None, gt=0, lt=1)
    """OPERATOR REQUIRED, absent until supplied. The gate blocks while it is.

    Optional **leaf**: ``Config.get`` returns ``None`` rather than raising. It is a
    probability, not a percentile, but the failure shape is identical — at 1 nothing
    is ever vetoed. Invariant 4: this engine can only make the system less willing to
    trade, so an accidentally disabled veto is a gate silently removed from the
    chain.
    """


class RegimeConfig(_Section):
    """Engine 12's two cutoffs. Plumbing, lead-chosen, flagged provisional.

    Both are **relative to the pair's own trailing window** rather than absolute
    numbers, which is what lets one pair of cutoffs classify a market that trades at
    four dollars and one that trades at ninety thousand. ``high_vol_percentile`` is a
    quantile of the pair's own long-window volatility distribution;
    ``trend_efficiency`` is a cutoff on the efficiency ratio, net move over path
    length, which lives in ``[0, 1]`` by construction.

    Both are bounded strictly inside ``(0, 1)``: at 1 neither can ever be exceeded,
    so every candidate would be labelled ``choppy`` and the engine would look like it
    was working.
    """

    high_vol_percentile: Ratio = Field(gt=0, lt=1)
    trend_efficiency: Ratio = Field(gt=0, lt=1)


class ScoutConfig(_Section):
    """Engine 7's candidate ranking.

    Spec 59 decision 7: the ranking is a **config-named feature, not a formula**. The
    feature is chosen by the operator from spec 75's study and is absent until then,
    and engine 7 orders alphabetically while it is — which is a stated, boring
    fallback rather than a guess at what predicts a move.

    ``rank_feature`` is an optional **leaf**, so ``Config.get("scout.rank_feature")``
    returns ``None`` rather than raising. The engine publishes ``rank_feature: null``
    in that state so the console and the research record say which ordering was used.
    """

    rank_feature: str | None = None
    rank_descending: bool = True

    @model_validator(mode="after")
    def _rank_feature_is_a_name(self) -> Self:
        value = self.rank_feature
        if value is None:
            return self
        if not value.strip() or value != value.strip():
            raise ValueError(
                f"scout.rank_feature must be a feature name from modelling/features.py, "
                f"got {value!r}"
            )
        return self


class TrainingConfig(_Section):
    """The predictor's LightGBM hyperparameters. Plumbing, lead-chosen, provisional.

    **Config keys and not module constants, and that is the whole reason this section
    exists.** ``code-standards.md`` requires a run to be reproducible from its config
    plus its data, and `modelling/artefacts.py` writes the config digest into every
    manifest. A tree count living in a Python constant is a number the manifest cannot
    prove and a retrain cannot be held to: two runs a month apart would carry the same
    digest and different models, and nothing would say so.

    No gate reads any of these and no order is sized from them, which is what makes
    them the lead's to choose rather than the operator's. They do decide what the model
    is, so they are named and versioned rather than defaulted quietly.

    The bounds are the ones that separate a value from a mistake, not opinions about
    good hyperparameters:

    * ``num_leaves`` is ``> 1`` because a single leaf is a model that returns the base
      rate for every input — it would train, score, and report a Brier equal to the
      base-rate Brier, which is the one result this phase is set up to detect and the
      one an operator might read as "the model learned nothing" rather than "the model
      was never allowed to exist".
    * ``learning_rate`` is strictly inside ``(0, 1)``. At 0 no boosting round changes
      anything and the ensemble stays at its initial score; at 1 each round takes the
      full step, which is not invalid but is far outside anything this project should
      reach by way of a typo in a config file.
    * ``num_trees`` and ``min_data_in_leaf`` are ``> 0`` because zero of either is not
      a configuration, it is an absence.
    """

    num_trees: int = Field(gt=0)
    """Boosting rounds. Reported in the manifest, so a retrain is comparable."""

    learning_rate: Ratio = Field(gt=0, lt=1)
    """Shrinkage per round. A ratio, so it is a `Decimal` and never a binary float."""

    num_leaves: int = Field(gt=1)
    """Leaves per tree. One leaf is a model that cannot express anything."""

    min_data_in_leaf: int = Field(gt=0)
    """Minimum rows behind a leaf. The main guard against fitting noise in a thin pair."""

    skeptic_cap_folds: int | None = Field(default=None, ge=1)
    """The skeptic's rolling training window, in folds (operator ruling 2026-09-16, R2).

    Fold *k*'s skeptic trains only on the out-of-sample BUY calls of folds *k*-cap to
    *k*-1. Optional **leaf**: absent or null means uncapped, the Phase 5 trainer's
    behaviour, and ``Config.get`` returns ``None``. When present it must be at least 1,
    because a cap of zero folds is a skeptic trained on nothing. Read by C's
    ``research/skeptic_cap.py`` (spec 136).
    """


#: The deepest book engine 9 may be configured to walk, and it is **not** a Kraken
#: limit — it is what this system's own feed delivers.
#:
#: ``engines/market_data_recorder/contracts.py`` subscribes the stream at
#: ``BOOK_DEPTH`` levels a side, and that number is itself pinned to
#: ``scripts/record.py``'s ``DEFAULT_DEPTH`` so the daemon's archive and the
#: standalone recorder's cannot diverge. Every recorded book frame therefore carries
#: at most that many levels, including the committed ``tests/fixtures/book_sample.jsonl``
#: that engine 9 is validated on. A larger ``order_book.depth`` would configure the
#: engine to walk deeper than any evidence can reach — making a thin-book refusal one
#: the fixture could never exercise, so the gate would look configured and be untested.
#:
#: **Written out rather than imported.** ``platform/`` is under ``engines/`` in the
#: layering and importing upwards would invert it, so the cost is a duplicated integer
#: and it is paid back by ``test_the_book_depth_ceiling_agrees_with_what_the_stream_
#: subscribes``, which imports both and fails if they ever disagree.
MAX_BOOK_DEPTH: Final = 10


class OrderBookConfig(_Section):
    """Engine 9's view of the book. Spec 80's debt, needed by spec 96.

    One key. ``depth`` is how many levels a side engine 9 walks, and both bounds are
    the difference between a value and a mistake rather than opinions:

    * ``> 0`` because a book walked zero levels deep has no best price at all, and
      the engine would report a spread of nothing rather than refusing. Absent is
      never zero, and neither is zero a depth.
    * ``<= MAX_BOOK_DEPTH`` because the stream is subscribed at that many levels, so
      a deeper configuration asks the engine for levels that never arrive. The
      failure is silent in the direction that matters: the walk simply ends early,
      the book reads as thin, and nothing says the configuration was the cause.
    """

    depth: int = Field(gt=0, le=MAX_BOOK_DEPTH)
    """Levels a side engine 9 walks. Approved by the lead at 10, 2026-09-16."""


class ReplayConfig(_Section):
    """The Phase 7 replay's declared scenario and its window. Specs 126, 129 and 131.

    **Optional as a section**, and read only by the replay client and the replay driver.
    A paper process never reads it, and the replay client refuses construction outside
    replay mode before it opens any file named here (invariant 2's amendment, spec 126).

    The paths are relative to the repository root. `fee_tier` is the committed default;
    the driver builds each run's config with the tier that run uses (R3: tiers 3 and 5,
    one per run), and never edits the committed file between runs.

    `run_id_format` names each fold's Phase 7 run directory (spec 135) and must contain
    `{fold}`. It is the one place the name is written, so the driver and C's assembly
    cannot spell it two ways.
    """

    asset_pairs_file: str
    instrument_file: str
    pair_names_file: str
    spread_table_file: str
    fee_schedule_file: str
    fee_tier: int = Field(gt=0)
    partitions_dir: str
    first_fold: int = Field(ge=0)
    last_fold: int = Field(ge=0)
    run_id_format: str

    @model_validator(mode="after")
    def _window_is_ordered(self) -> Self:
        if self.last_fold < self.first_fold:
            raise ValueError(
                f"replay.last_fold ({self.last_fold}) is before replay.first_fold "
                f"({self.first_fold})"
            )
        return self

    @model_validator(mode="after")
    def _run_id_format_names_the_fold(self) -> Self:
        if "{fold}" not in self.run_id_format:
            raise ValueError(
                "replay.run_id_format must contain {fold}: without it every fold would "
                "load the same models"
            )
        return self


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
    dataset: DatasetConfig
    safety: SafetyConfig
    trading: TradingConfig
    paper: PaperConfig
    kraken: KrakenConfig
    market_sensor: MarketSensorConfig
    data_guard: DataGuardConfig
    backtest: BacktestConfig
    seeds: SeedsConfig

    # ---- Phase 5, spec 61 step 1. -----------------------------------------
    # Declared `Section | None = None` for the two hours the lead's YAML block was
    # in flight, and **required since it landed on 2026-09-13**. Required is the
    # resting state for the same reason it is for `kraken.cache_ttl_s`: a section
    # deleted from the file now refuses at startup, by name, instead of surfacing
    # as a `ConfigKeyError` from inside a gate three chains into a tick.
    #
    # The leaves inside them are a separate question with a per-reader answer —
    # the five that are absent by ruling stay optional, and `Config.get` returns
    # `None` for each. See the block comment above ModelsConfig.
    models: ModelsConfig
    features: FeaturesConfig
    macro: MacroAssets
    prediction: PredictionConfig
    anomaly: AnomalyConfig
    skeptic: SkepticConfig
    regime: RegimeConfig
    scout: ScoutConfig

    # The ninth section, requested by the lead at 02:15 on 2026-09-13 for C's trainer
    # and landed the same way as the eight above: field first, YAML second, tightened
    # to required the hour the paste arrived. It was optional for about twenty
    # minutes, which is the whole of the window in which the committed config would
    # otherwise have failed to parse.
    training: TrainingConfig

    # ---- Phase 6, spec 80's debt, needed by spec 96. -----------------------
    # Optional for about an hour on 2026-09-16 while the lead's YAML was in flight,
    # and **required since it landed**, for the same reason as every section above:
    # a section deleted from the file now refuses at startup, by name, instead of
    # surfacing as a `ConfigKeyError` from inside engine 9 three chains into a tick.
    order_book: OrderBookConfig

    # ---- Phase 7, spec 129. -----------------------------------------------
    # Optional, and it stays optional: only the offline replay reads it, and a paper
    # daemon must start without it. See ReplayConfig.
    replay: ReplayConfig | None = None

    @model_validator(mode="after")
    def _lookback_fits_in_what_engine_3_publishes(self) -> Self:
        """A feature may not want more history than engine 3 puts in ``state``.

        ``market_sensor.published_bars`` bounds how many recent closed candles reach
        ``state`` each tick. A feature whose lookback exceeds it can never be filled
        **live** — and would fill perfectly in **replay**, where the whole archive is
        on disk. That is not a crash, it is a feature that is a number offline and
        NaN online, in a model whose training set therefore contains a column the
        live system cannot produce. Nothing goes red; the model simply stops working
        the day it is deployed, in a direction nobody can see from either side.

        Refused at startup because that is the only place both numbers are visible at
        once: ``features.max_lookback_bars`` is read by C's ``modelling/features.py``
        and ``market_sensor.published_bars`` by A's engine 3, and neither of them can
        see the other's key without becoming a second reader of it.
        """
        allowed = self.market_sensor.published_bars
        wanted = self.features.max_lookback_bars
        if wanted > allowed:
            raise ValueError(
                f"features.max_lookback_bars ({wanted}) exceeds "
                f"market_sensor.published_bars ({allowed}): engine 3 publishes only "
                f"{allowed} closed bars per tick, so a feature with a longer lookback "
                "would be NaN live and a number in replay"
            )
        return self

    @model_validator(mode="after")
    def _phase_0_forces_paper(self) -> Self:
        """Invariant 1. ``platform/live_guard.py`` is a Phase 8 deliverable.

        Until it exists this loader is the only thing standing between a config
        file and real money, so it fails closed. Do not add a flag that skips
        this, and do not implement the three switches here — they belong to
        ``live_guard.py``, and three conditions checked in the module that
        forbids them is not a guard.

        Its name is from Phase 0, when it refused ``replay`` too. Phase 7 lifted that
        half (spec 129) and left the live half exactly as it was.
        """
        if self.mode == "live":
            raise ValueError(
                "mode: live is refused. Live trading requires all three switches of "
                "invariant 1 in context/trading-invariants.md, implemented in "
                "platform/live_guard.py, which is a Phase 8 deliverable and does not "
                "exist yet. The absence of the guard is not permission. Set mode: paper."
            )
        # `replay` is accepted since Phase 7 (spec 129): the offline replay runs the
        # registered chains in mode replay, and its config is built in memory by the
        # driver from the committed file, which stays `mode: paper`. Nothing in replay
        # reaches the exchange. `acsoe engine` refuses a replay config itself, so this
        # opens no route by which a daemon runs in any mode but paper.
        return self

    def get(self, dotted_key: str, /) -> Any:
        """Look up a value by dotted path, e.g. ``"safety.max_consecutive_data_blocks"``.

        The second half of the ``Config`` Protocol in ``core/contracts.py``. The
        lead chose a dotted accessor over a fixed field list so that the key
        names live in ``config/default.yaml`` and this model only, and cannot
        drift into a third copy inside ``core/``.

        **Raises on a miss, and never returns a default.** An engine silently
        receiving ``None`` for a threshold is the exact failure this project
        exists to prevent: a null hurdle multiple does not stop a trade, it
        prices one at zero. The raise becomes ``ERROR`` at the orchestrator, and
        ``ERROR`` blocks.

        **A miss is a key this model does not declare. An optional field that is
        declared and unset is not a miss, and this returns its ``None``.** The two
        are different facts and reporting them differently is deliberate — but the
        consequence catches everybody once, so it is stated here rather than left
        in a field docstring. The walk ends on a leaf, so
        ``get("prediction.di_percentile")`` returns ``None`` while the operator has
        not supplied it; the walk has to descend *into* a ``None`` section, so
        ``get("prediction.di_window_days")`` **raises** while the whole
        ``prediction`` section is absent. Same shape, opposite behaviour, and the
        difference is the depth of the ``None``: an absent section fails closed on
        its own, an absent leaf does not and its reader must refuse the ``None``
        by name. Found by A in spec 58, on ``backtest.embargo_bars``, where a leaf
        read as zero is a walk-forward with no embargo — no crash, no red test,
        just a model that flatters.

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


class ConfigView:
    """A `Config` the replay driver re-points at a new, immutable `Config` per fold.

    Spec 131 step 3. The orchestrator holds one config object for its whole life, and
    the models in force change at every fold boundary. So the orchestrator is handed
    this view, and the driver builds each fold's `Config` fresh with
    :func:`derive_config` (validated, frozen, never a loaded one mutated) and points the
    view at it. Engines read `mode` and `get`, both delegated, so they cannot tell the
    view from the config. Satisfies the `Config` Protocol in `core/contracts.py`.

    **The mode cannot change through the view.** A switch that moved a replay into paper
    would change what the run is part-way through it, and is refused.
    """

    __slots__ = ("_current",)

    def __init__(self, config: Config) -> None:
        self._current = config

    @property
    def mode(self) -> Literal["paper", "live", "replay"]:
        return self._current.mode

    def get(self, dotted_key: str, /) -> Any:
        return self._current.get(dotted_key)

    @property
    def current(self) -> Config:
        return self._current

    def use(self, config: Config) -> None:
        if config.mode != self._current.mode:
            raise ValueError(
                f"a config view cannot change mode, and this switch would move it from "
                f"{self._current.mode} to {config.mode}"
            )
        self._current = config


def derive_config(base: Config, updates: Mapping[str, Any]) -> Config:
    """A new, validated `Config`: `base` with each dotted key in `updates` replaced.

    The driver's one way to build a run's config or a fold's config (spec 126 step 6,
    spec 131 step 3). It goes through `model_validate`, so a derived config meets every
    constraint the committed one does, including the refusal of live mode. A path through
    something that is not a section is refused by name. A leaf the model does not declare
    is refused by `extra="forbid"`, because adding a key here would give the config a
    setting that `config/default.yaml` does not have.
    """
    raw: dict[str, Any] = base.model_dump(by_alias=True)
    for dotted, value in updates.items():
        node: Any = raw
        parts = dotted.split(".")
        for part in parts[:-1]:
            child = node.get(part) if isinstance(node, dict) else None
            if not isinstance(child, dict):
                raise ConfigKeyError(
                    f"cannot derive {dotted!r}: {part!r} is not a section of the config"
                )
            node = child
        node[parts[-1]] = value
    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"a derived config is invalid: {exc}") from exc


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
    fresh clone: paper mode starts, runs its loop, records the order book and builds
    candles without one. It does **not** run the whole pipeline, and no paper fallback
    is holding it up — invariant 2 states the consequence plainly and there has been no
    paper-mode fallback since 2026-09-16. With an empty ``.env`` the private calls
    fail, ``TradeVolume`` returns nothing, and every pair blocks at the cost gate, so
    an unauthenticated clone takes no paper trades and writes no rejection past that
    gate. The caller decides whether the absence blocks — in live mode it does.

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
