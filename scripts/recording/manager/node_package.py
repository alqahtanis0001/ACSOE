"""Building a folder you copy to a machine to turn it into a recording node.

A node package is deliberately four small files and no installer: `record.py`,
`supervise.py`, a config naming its own source id, and a startup script. Both
Python files import nothing from `acsoe` and nothing from each other, which is
what lets the folder be dragged onto a machine that has never heard of this
project. The only thing that has to be there already is Python, plus
`pip install orjson websockets`.

## The two kinds, and the difference that matters

**A server node** is one the master can reach over SSH. The package carries the
master's **public** key, to be appended to the node's `authorized_keys`, and the
registry learns how to reach it so Pull works.

**A standalone node** is identical minus the key. It records; a person carries the
archive over on a disk. It is the right answer for a laptop on a home connection,
a machine behind a NAT nobody wants to open, or anywhere the security cost of an
inbound route is not worth paying.

## What is never in a package

**No credential for the master.** Not a key, not a host, not a URL. A node never
initiates a connection to the master — the master reaches into a server node, and
a standalone node is collected by a person — so there is nothing a node *needs* in
order to do its job, and therefore nothing on it to steal. A node is the machine
most likely to be compromised; when one is, nothing on it opens a door back.

**No API key of any kind.** The recorder subscribes to `book`, `ticker`, `trade`
and `instrument` on `wss://ws.kraken.com/v2`, all of which are public and
unauthenticated. A recording node has no business holding a trading credential and
this package has never contained one.

## The source id is generated and is not negotiable afterwards

Every file a node writes carries its source id in the name. Two nodes sharing one
id produce files that collide on the same date and merge into a single apparent
source, which destroys the one thing a second recorder is for: an independent
observation to compare against. So the manager generates it, writes it into the
package's config, and registers it — the three places it has to agree.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Final

READ_ME: Final = "README.txt"
CONFIG_NAME: Final = "recorder.yaml"
START_BAT: Final = "start-recording.bat"
START_SH: Final = "start-recording.sh"
AUTHORIZED_KEY: Final = "authorize-this-key.pub"

DEFAULT_NODE_ARCHIVE: Final = "data/raw"
DEFAULT_NODE_SUMMARIES: Final = "data/summaries"


class PackagingError(RuntimeError):
    """The package cannot be built. Nothing was written."""


def _recorder_sources(repo_root: Path) -> tuple[Path, Path]:
    recorder = repo_root / "scripts" / "record.py"
    supervisor = repo_root / "scripts" / "recording" / "supervise.py"
    for path in (recorder, supervisor):
        if not path.is_file():
            raise PackagingError(f"{path} is missing, so a node package cannot be built")
    return recorder, supervisor


def config_text(*, source_id: str, archive_dir: str, summary_dir: str) -> str:
    """The node's own `recorder.yaml`, with its identity written into it."""
    return f"""# This node's recorder configuration.
#
# The source id below is in the name of every file this machine records:
#
#     kraken_v2__{source_id}__2026-09-11.jsonl
#
# DO NOT CHANGE IT once this node has recorded anything. The id is the machine's
# identity in the master's archive, and changing it splits one source into two
# everywhere it is counted - coverage, gaps, and the overlap report that is the
# only check there is on whether a feed went bad.

recorder:
  archive_dir: "{archive_dir}"
  summary_dir: "{summary_dir}"
  source_id: "{source_id}"
"""


def start_bat_text(*, source_id: str) -> str:
    return f"""@echo off
REM ===========================================================================
REM  ACSOE recording node - {source_id}
REM
REM  Double-click this to start recording. It runs the supervisor, and the
REM  supervisor runs the recorder and restarts it whenever it stops.
REM
REM  TO START ON BOOT: press Win+R, type  shell:startup  and press Enter, then
REM  drop a shortcut to this file into the folder that opens.
REM
REM  SAFE TO CLOSE? Yes. Closing this window stops the recorder and damages
REM  nothing - the archive is append-only and every line is flushed as it is
REM  written. But the market does not come back: every minute this is closed is
REM  a minute missing from the archive for good.
REM
REM  SAFE TO OPEN TWICE? Yes. The second copy finds the archive locked by the
REM  first, says so, and waits. Two recorders on one archive is the one thing
REM  that would corrupt it silently, and the lock makes it impossible.
REM
REM  FIRST RUN: you need Python, and then, once:
REM      pip install orjson websockets pyyaml
REM ===========================================================================
cd /d "%~dp0"
if exist ".venv\\Scripts\\python.exe" (set "NODE_PY=.venv\\Scripts\\python.exe") else (set "NODE_PY=python")
title ACSOE recording - {source_id}
"%NODE_PY%" supervise.py --config recorder.yaml
echo.
echo The supervisor has stopped. Nothing is being recorded.
pause
"""


def start_sh_text(*, source_id: str) -> str:
    return f"""#!/bin/sh
# ACSOE recording node - {source_id}
#
# Start recording:      ./start-recording.sh
# Start on boot:        see README.txt for the systemd unit.
#
# The supervisor runs the recorder and restarts it whenever it stops. Safe to
# stop with Ctrl-C: the archive is append-only and nothing is damaged. The market
# does not come back, though, so restart it promptly.
#
# First run, once:      pip install orjson websockets pyyaml
set -e
cd "$(dirname "$0")"
exec python3 supervise.py --config recorder.yaml
"""


def readme_text(*, source_id: str, kind: str, archive_dir: str, has_key: bool) -> str:
    collection = (
        """HOW THE DATA GETS TO THE MASTER
    The master pulls it over SSH. This machine never connects out to the master
    and holds no credential for it, so if this machine is ever compromised there
    is nothing on it that reaches back. That is deliberate and is not an
    oversight: a design where nodes push to the master is easier to set up and
    puts a key for the master on every machine you no longer control.

    For the pull to work, append the contents of authorize-this-key.pub to
    ~/.ssh/authorized_keys on this machine, and make sure an SSH server is
    running and reachable on whatever address you gave the manager."""
        if has_key
        else """HOW THE DATA GETS TO THE MASTER
    Somebody carries it. This is a standalone node: there is no route from the
    master to here and none from here to the master.

    When you want to hand over what it has recorded, copy the files out of the
    node's archive directory onto a disk or a share, and on the master use
    Import -> Check inbox. Copy whole files only, and copy everything except
    today's - today's file is still being written to.

    THE MASTER CANNOT TELL WHETHER THIS MACHINE IS RECORDING. It will report the
    last import and the dates it covered, and it will not claim this node is dead
    just because it has not heard from it. Silence here means nothing at all."""
    )

    return f"""ACSOE recording node - {source_id}
{"=" * (26 + len(source_id))}

WHAT THIS IS
    Four files that turn this machine into a market data recorder. It connects to
    Kraken's public WebSocket feed and writes everything it sees to disk. It does
    not trade, it holds no API key, and it cannot place an order: the channels it
    subscribes to are public and unauthenticated.

WHY IT MATTERS THAT IT KEEPS RUNNING
    Order book and spread history cannot be recovered afterwards from anywhere.
    Kraken's free archives carry OHLCV and no bid, ask, spread or depth. Every
    hour this is not running is an hour that no amount of money or effort will
    buy back later.

SETUP
    1. Install Python 3.11 or newer.
    2. In this folder:  pip install orjson websockets pyyaml
    3. Start it: {START_BAT} on Windows, ./{START_SH} on Linux or macOS.

WHAT YOU WILL SEE
    Six lines, refreshing in place. That is the whole interface:

        RECORDING - {source_id}
        started    <when it was started>
        uptime     <how long it has been recording>
        today      <megabytes written today>
        last write <how long ago the last line landed>
        restarts   <how many times the recorder has been restarted>

    "last write" is the number to look at. On a healthy recorder it reads 0s.

    There are no buttons and no commands, on purpose. Every decision about this
    node is taken on the master; an interface here would be a way to stop a
    recorder from the wrong keyboard.

WHERE THE DATA GOES
    {archive_dir} - the full raw recording.
    logs/          - the supervisor's log: every launch, exit code and restart.

{collection}

STARTING ON BOOT - LINUX
    Put this in /etc/systemd/system/acsoe-record.service, with the paths and user
    corrected, then: systemctl enable --now acsoe-record

        [Unit]
        Description=ACSOE recording node {source_id}
        After=network-online.target

        [Service]
        Type=simple
        User=YOUR_USER
        WorkingDirectory=THIS_FOLDER
        ExecStart=/usr/bin/python3 THIS_FOLDER/supervise.py --config recorder.yaml
        Restart=always
        RestartSec=10

        [Install]
        WantedBy=multi-user.target

    The supervisor already restarts the recorder; systemd's Restart=always is the
    layer above it, for the case where the supervisor itself dies or the machine
    reboots.

IF SOMETHING LOOKS WRONG
    Read logs/supervisor__{source_id}__<date>.log. Every launch, every exit code
    and every restart is in it, with the recorder's own output beside them.

    A growing "restarts" number with nothing being written means the recorder is
    failing on startup - the reason will be the last thing in the log.

kind: {kind}
"""


def build(
    *,
    repo_root: Path,
    out_dir: Path,
    source_id: str,
    kind: str,
    archive_dir: str = DEFAULT_NODE_ARCHIVE,
    summary_dir: str = DEFAULT_NODE_SUMMARIES,
    public_key: str | None = None,
) -> dict[str, Any]:
    """Write the folder. Returns what was written and what to do with it.

    Refuses an existing non-empty directory rather than writing into it: a package
    half-overwritten with another node's config is a machine that records under
    the wrong identity, and the identity is the one thing that cannot be corrected
    afterwards.
    """
    recorder, supervisor = _recorder_sources(repo_root)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise PackagingError(
            f"{out_dir} already exists and is not empty. A package written over another "
            f"one is a node that records under the wrong source id, and the id is in "
            f"every filename it will ever write."
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []

    shutil.copy2(recorder, out_dir / recorder.name)
    written.append(recorder.name)
    shutil.copy2(supervisor, out_dir / supervisor.name)
    written.append(supervisor.name)

    (out_dir / CONFIG_NAME).write_text(
        config_text(source_id=source_id, archive_dir=archive_dir, summary_dir=summary_dir),
        encoding="utf-8",
    )
    written.append(CONFIG_NAME)

    (out_dir / START_BAT).write_text(start_bat_text(source_id=source_id), encoding="utf-8")
    written.append(START_BAT)

    # Newline-normalised: a shell script checked out or written with CRLF fails
    # with "bad interpreter: /bin/sh^M", which is an hour of somebody's evening.
    (out_dir / START_SH).write_text(start_sh_text(source_id=source_id), encoding="utf-8", newline="\n")
    (out_dir / START_SH).chmod(0o755)
    written.append(START_SH)

    if public_key:
        (out_dir / AUTHORIZED_KEY).write_text(
            public_key.strip() + "\n", encoding="utf-8", newline="\n"
        )
        written.append(AUTHORIZED_KEY)

    (out_dir / READ_ME).write_text(
        readme_text(
            source_id=source_id,
            kind=kind,
            archive_dir=archive_dir,
            has_key=bool(public_key),
        ),
        encoding="utf-8",
    )
    written.append(READ_ME)

    return {
        "source_id": source_id,
        "kind": kind,
        "path": out_dir.as_posix(),
        "files": written,
        "next_steps": _next_steps(kind=kind, has_key=bool(public_key)),
    }


def _next_steps(*, kind: str, has_key: bool) -> list[str]:
    steps = [
        "Copy this whole folder to the target machine.",
        "Install Python 3.11+, then run: pip install orjson websockets pyyaml",
        f"Start it: {START_BAT} on Windows, ./{START_SH} on Linux or macOS.",
    ]
    if has_key:
        steps += [
            f"Append {AUTHORIZED_KEY} to ~/.ssh/authorized_keys on the node.",
            "Make sure an SSH server is running and reachable on the address you gave.",
            (
                "Connect once by hand from the master, so its host key is recorded and "
                "the fingerprint is seen by a person. Pull will refuse an unknown host."
            ),
        ]
    else:
        steps += [
            "Nothing to authorise: this node has no route to or from the master.",
            (
                "To hand over data, copy whole files (not today's) into the master's "
                "inbox and use Import -> Check inbox."
            ),
        ]
    if kind == "standalone":
        steps.append(
            "The master will show this node with NO live status, which is correct and is "
            "not a fault: silence from a standalone node is not evidence of anything."
        )
    return steps


def find_public_key(candidates: list[Path]) -> tuple[str | None, Path | None]:
    """The first readable public key among the candidates.

    Public keys only. The private key is never read by this process, never copied
    into a package and never leaves the master — a package carrying one would hand
    every node the ability to impersonate the master to every other node.
    """
    for path in candidates:
        expanded = path.expanduser()
        if not expanded.is_file():
            continue
        try:
            text = expanded.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text.startswith(("ssh-", "ecdsa-", "sk-")):
            return text, expanded
    return None, None
