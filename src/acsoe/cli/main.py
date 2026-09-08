"""``acsoe`` — the command line dispatcher.

Three commands, one per process the system runs:

* ``acsoe engine``   — the trading daemon
* ``acsoe console``  — the local read-only console
* ``acsoe research`` — the offline chain

The dispatcher does nothing but parse arguments and hand off. Every command
builds its own config, clock, logging and clients: they are separate processes
sharing only SQLite, and pretending otherwise here would hide that.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from acsoe.cli import console as console_cmd
from acsoe.cli import engine as engine_cmd
from acsoe.cli import research as research_cmd
from acsoe.platform.config import DEFAULT_CONFIG_PATH


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
    engine.set_defaults(handler=engine_cmd.run)

    console = subcommands.add_parser("console", help="serve the local console")
    console.add_argument("--host", default="127.0.0.1", help="bind address")
    console.add_argument(
        "--port",
        type=int,
        default=None,
        help="override console.port from the configuration",
    )
    console.set_defaults(handler=console_cmd.run)

    research = subcommands.add_parser("research", help="run the offline chain")
    research.set_defaults(handler=research_cmd.run)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: object = args.handler
    assert callable(handler)
    result = handler(args)
    assert isinstance(result, int)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
