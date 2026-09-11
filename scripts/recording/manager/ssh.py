"""Reaching into a server node. The master calls out; nothing ever calls in.

**The direction is a security property, not a convenience.** The master holds a
private key and opens the connection. A node holds only the matching public key in
its `authorized_keys` and holds no credential for the master at all. A node is the
machine most likely to be compromised — a VPS on somebody else's hardware, a
laptop in somebody else's bag — and when one is, there is nothing on it that
reaches back into the master's archive or its store. Inverting this, so nodes push
to the master, would be easier to set up and would put a credential for the master
on every machine you no longer control.

## Three settings that are not defaults, they are decisions

`BatchMode=yes` — never prompt. A blocked password prompt in a web request is a
hung page and a leaked thread, and there is no keyboard attached to a request.

`ConnectTimeout` — bounded. Without it an unreachable host holds the connection
open for the operating system's own timeout, which on some networks is minutes.

**Host key checking is left ON.** `StrictHostKeyChecking=no` would make every
"cannot connect" go away and would make this whole tool a way to hand an archive
to whoever answers on that address. The first connection to a new node is made by
hand, once, so a person sees the fingerprint; after that the key is known.

## Failure is reported, never inferred

Every function here returns what happened, including the exact stderr. A source
whose check failed is shown as *not reachable, this is when we last tried, this is
what it said* — never as "dead". The manager cannot tell an unreachable node from
a node that is recording perfectly behind a broken network, and pretending
otherwise is how somebody switches off a recorder that was working.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Final

DEFAULT_CONNECT_TIMEOUT_S: Final = 10
DEFAULT_COMMAND_TIMEOUT_S: Final = 30

#: Copying a day file is 1-2 GB over whatever link the node has. Generous, and
#: still bounded: a transfer that has genuinely stalled must not hold a worker
#: forever.
DEFAULT_TRANSFER_TIMEOUT_S: Final = 3600


class SshError(RuntimeError):
    """An ssh or scp invocation failed. Carries what it said."""


class Result:
    """One completed remote command. Not a ``@dataclass`` — see ``registry.Source``."""

    __slots__ = ("code", "command", "stderr", "stdout")

    def __init__(self, *, command: list[str], code: int, stdout: str, stderr: str) -> None:
        self.command = command
        self.code = code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def ok(self) -> bool:
        return self.code == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            # The command is reported with the key path in it, which is a path and
            # not a secret. The key itself is never read by this process.
            "command": " ".join(self.command),
            "stdout": self.stdout.strip(),
            "stderr": self.stderr.strip(),
        }


def have_ssh() -> bool:
    return shutil.which("ssh") is not None


def have_scp() -> bool:
    return shutil.which("scp") is not None


def _base_options(*, connect_timeout_s: int) -> list[str]:
    return [
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={connect_timeout_s}",
        # StrictHostKeyChecking is deliberately NOT set here. Leaving it at the
        # user's own configuration means the default (`ask`, which under
        # BatchMode refuses) applies, and an unknown host is refused rather than
        # trusted. Turning it off would make every connection succeed, including
        # the one to whoever has taken over that address.
    ]


def run(
    *,
    host: str,
    command: str,
    port: int = 22,
    key: str | None = None,
    connect_timeout_s: int = DEFAULT_CONNECT_TIMEOUT_S,
    timeout_s: int = DEFAULT_COMMAND_TIMEOUT_S,
) -> Result:
    """Run one command on a node and bring back what it said.

    Never raises for a remote failure — a node that answered "no such directory"
    has told us something useful, and turning that into an exception loses it.
    Raises only when `ssh` itself cannot be run at all.
    """
    if not have_ssh():
        raise SshError(
            "`ssh` is not on PATH. On Windows install the OpenSSH client "
            "(Settings > Apps > Optional features > OpenSSH Client); on Linux and "
            "macOS it is already there."
        )
    argv = ["ssh", *_base_options(connect_timeout_s=connect_timeout_s), "-p", str(port)]
    if key:
        argv += ["-i", str(Path(key).expanduser())]
    argv += [host, command]
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired:
        return Result(
            command=argv,
            code=124,
            stdout="",
            stderr=(
                f"the command did not finish within {timeout_s}s. The node may be "
                f"reachable and slow, or the connection may have stalled; either way "
                f"nothing was transferred."
            ),
        )
    except OSError as exc:
        raise SshError(f"could not run ssh: {exc}") from exc
    return Result(
        command=argv, code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
    )


def check(
    *, host: str, port: int = 22, key: str | None = None, archive_dir: str | None = None
) -> Result:
    """Is the node reachable, and is its archive where we think it is?

    Both questions in one round trip, because "I can log in" and "the archive is
    there" fail for different reasons and an operator needs to know which.
    """
    probe = "echo ok"
    if archive_dir:
        quoted = _quote(archive_dir)
        probe = f"test -d {quoted} && echo ok || echo 'missing-archive'"
    return run(host=host, command=probe, port=port, key=key)


def list_files(
    *,
    host: str,
    archive_dir: str,
    list_command: str,
    port: int = 22,
    key: str | None = None,
) -> tuple[list[str], Result]:
    """``(*.jsonl filenames on the node, the raw result)``.

    The listing command is configurable and comes from the registry, because a
    Linux node answers `ls -1` and a Windows OpenSSH node answers `dir /b`, and
    guessing wrong returns an empty list — which is indistinguishable from an
    empty archive and would make the manager report a recording node as having
    nothing to give.
    """
    command = list_command.format(archive=_quote(archive_dir))
    result = run(host=host, command=command, port=port, key=key)
    names = [
        line.strip().replace("\\", "/").rsplit("/", 1)[-1]
        for line in result.stdout.splitlines()
        if line.strip().endswith(".jsonl")
    ]
    return sorted(set(names)), result


def fetch(
    *,
    host: str,
    remote_path: str,
    local_path: Path,
    port: int = 22,
    key: str | None = None,
    timeout_s: int = DEFAULT_TRANSFER_TIMEOUT_S,
) -> Result:
    """Copy one file down. The caller verifies it; this only moves bytes.

    `scp` is used rather than `rsync` because it is present wherever OpenSSH is,
    including a Windows node, and this tool has to work on the machines that
    exist rather than the ones that would be convenient.
    """
    if not have_scp():
        raise SshError("`scp` is not on PATH, so files cannot be pulled from a node.")
    local_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        "scp",
        *_base_options(connect_timeout_s=DEFAULT_CONNECT_TIMEOUT_S),
        "-P",
        str(port),
        "-p",
    ]
    if key:
        argv += ["-i", str(Path(key).expanduser())]
    argv += [f"{host}:{remote_path}", str(local_path)]
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired:
        # A partial file may be on disk. It is in staging, never in the archive,
        # and the caller deletes it — which is the entire reason staging exists.
        local_path.unlink(missing_ok=True)
        return Result(
            command=argv,
            code=124,
            stdout="",
            stderr=f"the transfer did not finish within {timeout_s}s; the partial file was removed",
        )
    except OSError as exc:
        raise SshError(f"could not run scp: {exc}") from exc
    return Result(
        command=argv, code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
    )


def _quote(value: str) -> str:
    """Single-quote a path for a POSIX remote shell.

    The paths here come from `sources.yaml`, which a person edits, so this is
    hygiene rather than a defence against an attacker — but a path with a space in
    it silently listing the wrong directory is a real and ordinary failure.
    """
    return "'" + value.replace("'", "'\\''") + "'"
