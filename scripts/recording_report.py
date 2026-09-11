#!/usr/bin/env python
"""Build the committed recording digest from a real recording.

    python scripts/recording_report.py                       # print it
    python scripts/recording_report.py --write               # write the fixture
    python scripts/recording_report.py --raw-dir data/raw --min-hours 24

`data/` is gitignored and no phase criterion may depend on anything inside it, so the
evidence that the recorder ran is this small digest — produced from the real archive
and checked in — while the archive itself is verified by `verify.py --live`.

**It refuses to write a digest that would not satisfy the criterion.** A report whose
span is under `--min-hours` is printed with its numbers and *not* written, because
depositing one would turn a truthful PENDING into a FAIL. Waiting is the correct
answer to "the recorder has not run for long enough yet"; there is no other one, and
in particular there is no flag here that fabricates a span.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from acsoe.clients.recorder.report import (
    DEFAULT_SILENCE_THRESHOLD_S,
    build_report,
    parse_iso,
)

DEFAULT_RAW_DIR = Path("data") / "raw"
DEFAULT_FIXTURE = Path("tests") / "fixtures" / "recording_report.json"
DEFAULT_MIN_HOURS = 24.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="recording_report.py",
        description="Digest a raw recording into tests/fixtures/recording_report.json.",
    )
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--out", default=str(DEFAULT_FIXTURE))
    parser.add_argument(
        "--silence-threshold-s",
        type=float,
        default=DEFAULT_SILENCE_THRESHOLD_S,
        help="a stretch with no frame longer than this is an unrecorded silence",
    )
    parser.add_argument(
        "--min-hours",
        type=float,
        default=DEFAULT_MIN_HOURS,
        help="refuse to write a digest whose span is shorter than this",
    )
    parser.add_argument(
        "--from",
        dest="window_from",
        default=None,
        help=(
            "ISO-8601 UTC. Digest only frames at or after this moment. Narrows what the "
            "REPORT describes; the archive is never filtered or rewritten."
        ),
    )
    parser.add_argument(
        "--to",
        dest="window_to",
        default=None,
        help="ISO-8601 UTC. Digest only frames at or before this moment.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the fixture; without it the digest is printed and nothing is written",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    raw_dir = Path(args.raw_dir)
    paths = sorted(raw_dir.glob("*.jsonl"))
    if not paths:
        print(f"no recording found in {raw_dir}", file=sys.stderr)
        return 2

    window_start = parse_iso(args.window_from) if args.window_from else None
    window_end = parse_iso(args.window_to) if args.window_to else None
    report = build_report(
        paths,
        silence_threshold_s=args.silence_threshold_s,
        window_start=window_start,
        window_end=window_end,
    )
    span = report["span"]
    hours = float(span["hours"])

    window = report.get("window")
    if window is not None:
        print(
            f"window {window['start_iso']} -> {window['end_iso']}"
            "   (the archive itself is untouched)",
            file=sys.stderr,
        )
    print(
        f"span {span['start_iso']} -> {span['end_iso']}  ({hours:.2f}h)\n"
        f"segments {len(report['segments'])}  gaps {len(report['gaps'])}  "
        f"lines {report['totals']['lines']}\n"
        f"recorded {report['totals']['recorded_seconds'] / 3600:.2f}h  "
        f"missing {report['totals']['missing_seconds'] / 3600:.2f}h  "
        f"recorded_fraction {report['totals']['recorded_fraction']:.4f}",
        file=sys.stderr,
    )
    for gap in report["gaps"]:
        print(f"  gap {gap['start_iso']} -> {gap['end_iso']}: {gap['cause']}", file=sys.stderr)

    if not args.write:
        print(json.dumps(report, indent=2))
        return 0

    if hours < args.min_hours:
        print(
            f"REFUSING to write: the span is {hours:.2f}h and the criterion needs "
            f"{args.min_hours:.0f}h. A short digest is honest and would still FAIL the "
            "gate, which is worse than the PENDING it reports now. Let the recorder run.",
            file=sys.stderr,
        )
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # `newline="\n"` is load-bearing. `write_text` opens in TEXT mode, text mode on
    # Windows turns every `\n` into `\r\n`, and `tests/fixtures/**` is `-text` in
    # `.gitattributes` — so unlike everywhere else in this repository there is no clean
    # filter to normalise it, and a bare call changes the **committed bytes** of an
    # evidence file. Found 2026-09-11 by C.
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
