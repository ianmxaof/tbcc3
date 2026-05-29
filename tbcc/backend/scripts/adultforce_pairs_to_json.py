"""
Convert AdultForce-style paste (numbered title line + URL line) to TBCC bulk JSON.

Usage (PowerShell):
  Get-Content adultforce.txt -Raw | python adultforce_pairs_to_json.py > promo_bulk.json

Pipe into Misc → Promo affiliate links → Bulk import JSON.
"""

from __future__ import annotations

import json
import re
import sys

TITLE_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")
URL_RE = re.compile(r"^https?://\S+")


def main() -> None:
    raw = sys.stdin.read()
    lines = [ln.rstrip() for ln in raw.splitlines()]
    items: list[dict] = []
    i = 0
    while i < len(lines):
        m = TITLE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        label = m.group(2).strip()
        j = i + 1
        url = ""
        while j < len(lines):
            cand = lines[j].strip()
            if cand and URL_RE.match(cand):
                url = cand
                break
            j += 1
        if label and url:
            items.append(
                {
                    "label": label[:512],
                    "url": url[:8192],
                    "payout_kind": "other",
                    "priority_tier": 10,
                    "active": True,
                }
            )
        i = j + 1 if url else i + 1

    json.dump({"items": items}, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
