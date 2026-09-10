"""Engine 2 `market_data_recorder` — the framework recorder.

Drains everything the WebSocket stream buffered since the last tick and appends it,
verbatim, to the append-only archive in `data/raw/`. Supersedes `scripts/record.py`,
which stays on disk and stays working as the fallback for when the engine framework
is down.

**It runs in the guard chain, every tick, in every mode.** A freeze stops trading; it
never stops data collection. Order-book and spread history cannot be recovered
retroactively, so a minute not recorded is a minute gone — which is why the guard
chain runs in `idle` and `frozen` as well as `running`, and why this engine is in it.

**It is not a gate and it never blocks.** A dead feed is engine 4 `data_guard`'s
judgement to make, on the market data itself; engine 2's job is to write down what
arrived and what did not.

**A break is written into the archive, never healed.** Gaps are drained from the
stream and appended as `gap` marker lines carrying their own cause, so a silent
outage cannot be mistaken later for a quiet market.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, ClassVar

from acsoe.clients.recorder.contracts import RECORDER_CHANNEL, build_line
from acsoe.core.contracts import (
    BaseEngine,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.engines.market_data_recorder.contracts import (
    EXCHANGE_STATE_KEY,
    RecorderState,
    subscription_scope,
)

__all__ = ["MarketDataRecorderEngine"]


def _iso(moment: Any) -> str:
    """ISO-8601 UTC ending in ``Z``, the form the recording schema requires."""
    text: str = moment.isoformat()
    return text.replace("+00:00", "Z") if text.endswith("+00:00") else text + "Z"


def _optional_setting(context: EngineContext, key: str) -> Any:
    """A config key that may not have landed yet, without making this engine a gate.

    ``Config.get`` raises on a key that does not exist, deliberately: an engine
    silently receiving ``None`` for a threshold is the failure this project exists to
    prevent. For every gate that is the right behaviour, because the orchestrator
    turns the exception into ``ERROR`` and ``ERROR`` blocks.

    **Engine 2 must never block.** It is not a gate, it runs in every mode including
    frozen, and a tick it fails is a minute of order-book history that cannot be
    recovered. So a key whose YAML half is still in flight — currently
    ``trading.stable_quote_currencies``, which is requested and not yet pasted —
    would otherwise make the recorder the tick's primary blocker and displace
    ``data_guard``, which is both wrong and hard to read.

    ``KeyError`` only, and only for keys this engine has already decided it can work
    without. ``ConfigKeyError`` is a ``KeyError`` subclass and the test double raises
    a plain one, so this covers both without either being special-cased. A key that
    is present and ``null`` is a different state and reaches the caller as ``None``
    through the normal path, exactly as it should: "the operator has not decided yet"
    is not the same as "this key does not exist".
    """
    try:
        return context.config.get(key)
    except KeyError:
        return None


class MarketDataRecorderEngine(BaseEngine):
    """Raw market data to `data/raw/`, every tick, in every mode."""

    name: ClassVar[str] = "market_data_recorder"
    number: ClassVar[int] = 2
    #: Registry table in `context/engine-contracts.md` marks engine 2 with no Gate.
    is_gate: ClassVar[bool] = False

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()
        stream = context.clients.kraken
        recorder = context.clients.recorder

        scope, derived, crypto_excluded = self._apply_subscription(context, state, stream)

        drain = getattr(stream, "drain", None)
        if not callable(drain):
            # No stream on this client. Reported, not raised: a client double without
            # one is a legitimate thing to be handed, and raising here would take the
            # whole guard chain to ERROR on a tick where nothing is actually wrong.
            payload = RecorderState(
                stream_available=False,
                connected=False,
                frames_recorded=0,
                gaps_recorded=0,
                dropped_frames=0,
                unparsed_frames=0,
                subscription=scope,
                subscription_derived=derived,
                crypto_quoted_excluded=crypto_excluded,
            )
            return EngineResult(
                engine=self.name,
                status=EngineStatus.OK,
                data=payload.to_state(),
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        frames = tuple(drain())
        for frame in frames:
            recorder.append(
                build_line(
                    kind="tick",
                    pair=frame.pair,
                    channel=frame.channel,
                    ts_exchange=frame.ts_exchange,
                    ts_recv=frame.ts_recv,
                    # Verbatim. Invariant 11: a recording is never edited, cleaned or
                    # normalised on the way in.
                    payload=frame.payload,
                )
            )

        gaps = self._drain_gaps(stream)
        fallback_ts = _iso(context.now)
        for gap in gaps:
            recorder.append(
                build_line(
                    kind="gap",
                    pair=None,
                    channel=RECORDER_CHANNEL,
                    ts_exchange=None,
                    # The gap's own end, so the marker sits at the moment the break
                    # closed rather than at the moment the loop happened to notice.
                    ts_recv=str(gap.get("ended_at") or fallback_ts),
                    payload=dict(gap),
                )
            )

        payload = RecorderState(
            stream_available=True,
            connected=bool(getattr(stream, "connected", False)),
            frames_recorded=len(frames),
            gaps_recorded=len(gaps),
            dropped_frames=int(getattr(stream, "dropped_frames", 0)),
            unparsed_frames=int(getattr(stream, "unparsed_frames", 0)),
            subscription=scope,
            subscription_derived=derived,
            crypto_quoted_excluded=crypto_excluded,
        )
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            data=payload.to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------- subscription scope

    def _apply_subscription(
        self, context: EngineContext, state: State, stream: Any
    ) -> tuple[tuple[str, ...], bool, bool]:
        """Move the stream's subscription to the scope this tick implies.

        Returns the scope now in force, whether this tick derived it, and whether the
        crypto-quoted exclusion was actually applied.

        **This engine remembers nothing between ticks**, which is architecture
        invariant 1 and is not a limitation to work around here. When the inputs are
        absent there is nothing to compare against and nothing to restore, because
        the subscription is the *stream's* state, not the engine's: the engine simply
        does not call ``set_subscription`` and reads back what is already there. That
        is what makes "a failed `AssetPairs` leaves the subscription unchanged" true
        by construction rather than by an engine holding a copy of last tick's answer
        and hoping it is still right.
        """
        current: tuple[str, ...] = tuple(getattr(stream, "subscription", ()) or ())

        exchange = state.get(EXCHANGE_STATE_KEY)
        if not isinstance(exchange, Mapping):
            # Engine 1 did not publish this tick — it errored, or it is not
            # registered. Nothing to derive from, so nothing changes.
            return current, False, False

        # `allow_crypto_quoted` is a required field and is read with a bare `get`, so
        # a genuinely missing required key still fails loudly. The stable-quote set is
        # the one key that may legitimately not exist yet — see `_optional_setting`.
        allow_crypto = bool(context.config.get("trading.allow_crypto_quoted"))
        stable = _optional_setting(context, "trading.stable_quote_currencies")
        stable_quotes = frozenset(stable) if stable is not None else None

        scope = subscription_scope(
            pair_rules=exchange.get("pair_rules"),
            balances=exchange.get("balances"),
            allow_crypto_quoted=allow_crypto,
            stable_quotes=stable_quotes,
        )
        if scope is None:
            return current, False, False

        applied_crypto_rule = not allow_crypto and stable_quotes is not None
        set_subscription = getattr(stream, "set_subscription", None)
        if callable(set_subscription):
            set_subscription(scope)
            scope = tuple(getattr(stream, "subscription", scope) or scope)
        return scope, True, applied_crypto_rule

    @staticmethod
    def _drain_gaps(stream: Any) -> tuple[Mapping[str, Any], ...]:
        """Take the breaks recorded since the last tick, and clear them.

        Drained rather than read so this engine stays stateless across cycles
        (architecture invariant 1): it never has to remember which breaks it has
        already written into the archive, which is the kind of bookkeeping that
        silently duplicates or silently drops one after a restart.
        """
        drain_gaps = getattr(stream, "drain_gaps", None)
        if not callable(drain_gaps):
            return ()
        return tuple(drain_gaps())
