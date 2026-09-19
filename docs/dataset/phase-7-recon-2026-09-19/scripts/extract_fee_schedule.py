"""Extract Kraken's published spot fee schedule from the committed raw page, verbatim. Read-only.

Input:  tests/fixtures/replay/kraken_fee_schedule_2026-09-19.html.gz, the page as fetched from
        https://www.kraken.com/features/fee-schedule at 2026-09-19T02:59:51Z (HTTP 200).
Output: tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json.

Every figure is copied as the page's own text: no figure is typed by hand, rounded or inferred.
The spot table is the one under the page's "Spot Crypto" tab (`content-spot-crypto`).
"""
import gzip
import hashlib
import html
import json
import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[4]
FIX = REPO / "tests/fixtures/replay"
raw = gzip.decompress((FIX / "kraken_fee_schedule_2026-09-19.html.gz").read_bytes())
page = raw.decode("utf-8", errors="replace")


def cells(row: str) -> list[str]:
    found = re.findall(r"<t[hd].*?</t[hd]>", row, flags=re.S)
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in found]


def table_after(anchor: str) -> list[list[str]]:
    start = page.index(anchor)
    table = re.search(r"<table.*?</table>", page[start:], flags=re.S).group(0)
    return [cells(r) for r in re.findall(r"<tr.*?</tr>", table, flags=re.S)]


def as_rows(rows: list[list[str]]) -> list[dict[str, str]]:
    header, body = rows[0], rows[1:]
    return [dict(zip(header, r)) for r in body]


spot = table_after('id="content-spot-crypto"')
rebate = table_after('id="content-spot-maker-rebate"')
stable_anchor = page.index("Stablecoin, Pegged Token &amp; FX Pairs")
stable = [cells(r) for r in re.findall(
    r"<tr.*?</tr>", re.search(r"<table.*?</table>", page[stable_anchor:], flags=re.S).group(0), flags=re.S)]
out = {
    "_provenance": {
        "source_url": "https://www.kraken.com/features/fee-schedule",
        "fetched_at_utc": "2026-09-19T02:59:51Z",
        "http_status": 200,
        "raw_page": "kraken_fee_schedule_2026-09-19.html.gz",
        "raw_page_sha256_uncompressed": hashlib.sha256(raw).hexdigest(),
        "extracted_by": "docs/dataset/phase-7-recon-2026-09-19/scripts/extract_fee_schedule.py",
        "restructure": {
            "statement": "On July 9, 2026, Kraken changed how the fee tier is determined: the best of "
                         "spot volume, futures volume and Assets on Platform, across the platform.",
            "source_url": "https://support.kraken.com/articles/cross-platform-fee-tier-changes",
            "fetched_at_utc": "2026-09-19T03:00:49Z",
            "raw_page": "kraken_cross_platform_fee_tiers_2026-09-19.html.gz",
        },
        "use": "A DECLARED fee scenario for offline replay only (invariant 2 amendment, operator "
               "ruling 2026-09-19). Never read by the live or paper path. This is the schedule in "
               "force on the fetch date; nothing on disk dates any earlier schedule, so applying it "
               "to a 2023-24 window is a stated assumption.",
        "scope_notes": [
            "The page's 'Spot Crypto' table applies to almost all cryptocurrency pairs.",
            "FX pairs, stablecoins in the base currency and pegged tokens follow a separate "
            "'Stablecoin, Pegged Token & FX Pairs' schedule, included below.",
            "A separate 'Maker Rebate' table exists on the page; it is included for completeness "
            "and is not the standard schedule.",
        ],
    },
    "spot_crypto": as_rows(spot),
    "spot_maker_rebate_program": as_rows(rebate),
    "stablecoin_pegged_fx": as_rows(stable),
}
target = FIX / "kraken_fee_schedule_2026-09-19.json"
target.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
for row in out["spot_crypto"][:6]:
    print(row)
