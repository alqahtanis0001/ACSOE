#!/usr/bin/env python
"""Start the Recording Manager on this machine.

    python scripts/recording/manager/serve.py
    python scripts/recording/manager/serve.py --port 8770 --archive E:/acsoe/raw

Then open http://127.0.0.1:8766.

**Bound to 127.0.0.1 and not to 0.0.0.0, deliberately.** The manager can run
`ssh` with the master's private key and can write into the archive, so anything
that can reach it can reach both. Binding it to every interface would put that on
the network for the convenience of opening it from a laptop, and the whole design
of this system is that nothing reaches *into* the master. `--host` exists for
somebody who has decided otherwise and knows why; it is not a default.

This is a different application from `acsoe console`, on a different port, and it
shares nothing with it. The console reads the SQLite store and writes three
command rows. The manager never opens the store at all — engine 19 `memory` is
the single writer of every relational row, and the manager is not in that chain.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# `scripts/` is not a package, so put it on the path and import `recording.*`
# from there. This is the one place that happens; every other module in the
# package uses ordinary imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from recording.manager.app import (
    DEFAULT_ARCHIVE,
    DEFAULT_INBOX,
    DEFAULT_NODES_DIR,
    DEFAULT_REGISTRY,
    DEFAULT_STAGING,
    create_app,
)

DEFAULT_PORT = 8766
DEFAULT_HOST = "127.0.0.1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="serve.py",
        description=(
            "The Recording Manager: sources, coverage, gaps, import and node "
            "creation. Reads files and runs ssh; never records, never writes to "
            "the store."
        ),
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=(
            "interface to bind. The default is loopback only and should stay that way: "
            "this process can run ssh with the master's key and write into the archive."
        ),
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--archive", default=str(DEFAULT_ARCHIVE))
    parser.add_argument("--staging", default=str(DEFAULT_STAGING))
    parser.add_argument("--inbox", default=str(DEFAULT_INBOX))
    parser.add_argument("--nodes", default=str(DEFAULT_NODES_DIR))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    import uvicorn

    app = create_app(
        registry_path=Path(args.registry),
        archive_dir=Path(args.archive),
        staging_dir=Path(args.staging),
        inbox_dir=Path(args.inbox),
        nodes_dir=Path(args.nodes),
    )
    print(f"Recording Manager on http://{args.host}:{args.port}")
    print(f"  archive  {Path(args.archive).resolve()}")
    print(f"  registry {Path(args.registry).resolve()}")
    print(f"  inbox    {Path(args.inbox).resolve()}")
    print("  it does not record, and it does not write to the store.\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
