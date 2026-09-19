"""``acsoe`` — the command line dispatcher.

Three commands, one per process the system runs:

* ``acsoe engine``   — the trading daemon
* ``acsoe console``  — the local read-only console
* ``acsoe research`` — the offline chain

The dispatcher does nothing but parse arguments and hand off. Every command
builds its own config, clock, logging and clients: they are separate processes
sharing only SQLite, and pretending otherwise here would hide that.

**Each command module is imported only when its command is chosen.** That is
architecture invariant 5 expressed in the import graph rather than in a comment.
From Phase 4, ``cli/research.py`` registers engines 20 ``tournament`` and 23
``backtest``, so it imports from ``acsoe.research``; a dispatcher that imported
all three modules eagerly would pull ``research/`` into the daemon process every
time anyone ran ``acsoe engine``. Nothing would fail — which is the problem, and
why the structure has to prevent it rather than a reviewer.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Final

from acsoe.platform.config import DEFAULT_CONFIG_PATH

Handler = Callable[[argparse.Namespace], int]

COMMANDS: Final = ("engine", "console", "research")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acsoe",
        description="Adaptive Crypto Spot Opportunity Engine.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"path to the configuration file (default: {DEFAULT_CONFIG_PATH})",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    engine = subcommands.add_parser("engine", help="run the trading daemon")
    engine.add_argument(
        "--ticks",
        type=int,
        default=0,
        help="stop after this many ticks; 0 runs until interrupted",
    )

    console = subcommands.add_parser("console", help="serve the local console")
    console.add_argument("--host", default="127.0.0.1", help="bind address")
    console.add_argument(
        "--port",
        type=int,
        default=None,
        help="override console.port from the configuration",
    )

    research = subcommands.add_parser("research", help="run the offline chain")
    research.add_argument(
        "--digest",
        type=Path,
        default=None,
        help=(
            "path to a training digest for engine 20 (tournament); "
            "the engine reports that it cannot score without one"
        ),
    )
    # Phase 7, spec 131: `acsoe research backtest` replays the ruled window through the
    # registered chains. Without the word, `acsoe research` runs the offline chain as
    # it always has.
    research.add_argument(
        "action",
        nargs="?",
        choices=("backtest",),
        default=None,
        help="`backtest`: replay the window through the registered chains (spec 131)",
    )
    research.add_argument(
        "--db", type=Path, default=None, help="backtest: this run's own database file"
    )
    research.add_argument(
        "--ranking",
        choices=("expected_move", "alphabetical"),
        default="expected_move",
        help="backtest: engine 7's ranking; `alphabetical` is the baseline",
    )
    research.add_argument(
        "--fee-tier",
        type=int,
        default=None,
        help="backtest: the declared fee tier; replay.fee_tier when omitted",
    )
    research.add_argument(
        "--begin",
        type=datetime.fromisoformat,
        default=None,
        help="backtest: first bar close to run, UTC (the rehearsal's day)",
    )
    research.add_argument(
        "--until",
        type=datetime.fromisoformat,
        default=None,
        help="backtest: last tick to run, UTC",
    )
    research.add_argument(
        "--resume", action="store_true", help="backtest: continue a killed run's database"
    )
    research.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="backtest: stop after this many ticks (tests only)",
    )
    research.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="backtest: this run's own log directory (default <cwd>/logs); one per "
        "concurrent run, so no two processes rotate one file",
    )

    return parser


def resolve_handler(command: str) -> Handler:
    """Import the module for ``command`` and return its ``run``.

    A match rather than a registry dict, because a dict of imports is evaluated
    at module scope and would defeat the whole point of importing lazily.
    """
    match command:
        case "engine":
            from acsoe.cli import engine

            return engine.run
        case "console":
            from acsoe.cli import console

            return console.run
        case "research":
            from acsoe.cli import research

            return research.run
        case _:
            raise SystemExit(f"acsoe: unknown command {command!r}; expected one of {COMMANDS}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return resolve_handler(args.command)(args)


if __name__ == "__main__":
    raise SystemExit(main())
