#!/usr/bin/env python
"""Refresh docs/ACSOE_source_dump.md: every source-shaped text file of the repository, verbatim,
in one Markdown file, with secrets redacted.

No script for this existed in the repository before 2026-09-20 (grep for `source_dump` and
`source dump` over scripts/, docs/, context/, tests/ found nothing), so this one was written by the
evidence-pack session under the rules the pack was given: no `.env`, no data, no logs, no
databases, no caches, no `.docx`; secrets redacted. It reads only; it writes only the dump.

Rules
-----
* Walk the repository from its root, skipping: `.git`, `.venv`, `.hypothesis`, `.mypy_cache`,
  `.pytest_cache`, `.ruff_cache`, `__pycache__`, `data/`, `logs/`, `models/`, and the dump itself.
* Skip by name: `.env` (any file whose name starts with `.env` except `.env.example`), `*.docx`,
  `*.sqlite*`, `*.db`, `*.parquet`, `*.gz`, `*.zip`, `*.npz`, `*.pyc`, `*.woff*`, `*.ttf`,
  `*.png`, `*.jpg`, `*.ico`, `*.jsonl` and `*.ndjson` larger than the cap.
* Include only text files with an allowed extension, under `MAX_BYTES`; anything larger is listed
  with its size and sha256 instead of its content.
* Redact: any value following `KRAKEN_API_KEY`, `KRAKEN_API_SECRET`, `API_KEY`, `API_SECRET`,
  `SECRET`, `TOKEN`, `PASSWORD` and `=`/`:`; any 56+ character base64-looking run; anything the
  `.env.example` names. Replaced with `[REDACTED]`.

Usage: `python docs/report/evidence/make_source_dump.py` from the repository root.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs" / "ACSOE_source_dump.md"
MAX_BYTES = 512 * 1024

SKIP_DIRS = {".git", ".venv", ".hypothesis", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__", "data", "logs", "models"}
SKIP_SUFFIXES = {".docx", ".db", ".sqlite", ".parquet", ".gz", ".zip", ".npz", ".pyc", ".woff", ".woff2", ".ttf", ".png", ".jpg", ".jpeg", ".ico", ".pdf", ".shm", ".wal"}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".yaml", ".yml", ".toml", ".sql", ".json", ".html", ".css", ".js", ".ps1", ".bat", ".cfg", ".ini", ".jsonl", ".ndjson", ".gitattributes", ".gitignore", ".example", ".in", ".typed", ".csv"}
LANG = {".py": "python", ".md": "markdown", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".sql": "sql", ".json": "json", ".html": "html", ".css": "css", ".js": "javascript", ".ps1": "powershell", ".bat": "bat", ".jsonl": "json", ".ndjson": "json", ".txt": "text", ".csv": "text"}

SECRET_KEY = re.compile(r"(?i)\b(KRAKEN_API_KEY|KRAKEN_API_SECRET|API_KEY|API_SECRET|SECRET|TOKEN|PASSWORD)\b(\s*[=:]\s*)(\S+)")
LONG_B64 = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{56,}={0,2}(?![A-Za-z0-9+/=])")


def redact(text: str) -> str:
    text = SECRET_KEY.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    return LONG_B64.sub("[REDACTED]", text)


def wanted(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    if path.suffix.lower() in SKIP_SUFFIXES or ".sqlite" in path.name:
        return False
    if path.resolve() == OUT.resolve():
        return False
    if path.name.endswith(".docx"):
        return False
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {".gitattributes", ".gitignore", "py.typed"}


def main() -> int:
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and wanted(p))
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    parts: list[str] = []
    parts.append("# ACSOE source dump\n\n")
    parts.append(f"Generated {now} at commit `{head}` by `docs/report/evidence/make_source_dump.py`. Working tree: {'clean' if not status else 'DIRTY — see git status'}.\n\n")
    parts.append("Exclusions: `.env`, `data/`, `logs/`, `models/`, databases, caches, `.docx`, binaries and compressed files; files over 512 KiB are listed with a hash instead of their content. Secrets are redacted as `[REDACTED]`. Every other text file is reproduced verbatim.\n\n")
    parts.append("## Index\n\n")
    listed: list[tuple[Path, int, bool]] = []
    for p in files:
        size = p.stat().st_size
        listed.append((p, size, size <= MAX_BYTES))
    for p, size, full in listed:
        rel = p.relative_to(ROOT).as_posix()
        parts.append(f"- `{rel}` ({size:,} B){'' if full else ' — content omitted (over cap), hash below'}\n")
    parts.append("\n---\n\n")
    for p, size, full in listed:
        rel = p.relative_to(ROOT).as_posix()
        parts.append(f"## `{rel}`\n\n")
        data = p.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        parts.append(f"*{size:,} bytes, sha256 `{digest}`*\n\n")
        if not full:
            parts.append("*Content omitted: over the 512 KiB cap.*\n\n")
            continue
        text = data.decode("utf-8", errors="replace")
        text = redact(text)
        lang = LANG.get(p.suffix.lower(), "")
        fence = "````" if "```" in text else "```"
        parts.append(f"{fence}{lang}\n{text.rstrip()}\n{fence}\n\n")
    OUT.write_bytes("".join(parts).encode("utf-8"))
    print(f"{OUT} {OUT.stat().st_size:,} bytes, {len(listed)} files ({sum(1 for _, _, f in listed if not f)} over cap)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
