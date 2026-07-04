#!/usr/bin/env python3
"""Test mega link resolve + LV wrap. Usage: python scripts/run_mega_link_pipeline.py <url>"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from dotenv import load_dotenv

_env = _backend.parent / ".env"
if _env.exists():
    load_dotenv(_env, override=True)

from app.data.mega_scrape_channel_sources import MEGA_SCRAPE_PASTE_FIXTURES
from app.services.mega_link_pipeline import process_archive_entry_value, resolve_to_file_host


def main() -> None:
    p = argparse.ArgumentParser(description="Resolve obfuscated/paste URL to file host + LV wrap")
    p.add_argument("url", nargs="?", help="URL to resolve")
    p.add_argument("--fixtures", action="store_true", help="Run paste fixture URLs (no bypass needed for direct)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    urls: list[str] = []
    if args.fixtures:
        urls = [f["url"] for f in MEGA_SCRAPE_PASTE_FIXTURES]
    elif args.url:
        urls = [args.url]
    else:
        p.print_help()
        raise SystemExit(1)

    results = []
    for u in urls:
        r = process_archive_entry_value(u) if not args.fixtures else resolve_to_file_host(u)
        if r.ok:
            try:
                from app.services.mega_link_pipeline import build_modifier_payload

                build_modifier_payload(r, source_note="cli_test")
            except Exception:
                pass
        row = {
            "input": r.input_url,
            "ok": r.ok,
            "destination": r.destination_url,
            "lv_wrapped": r.lv_wrapped_url,
            "tier": r.min_rarity_tier,
            "size_gb": r.size_gb_hint,
            "hops": r.hops,
            "error": r.error,
        }
        results.append(row)
        if not args.json:
            status = "OK" if r.ok else f"FAIL ({r.error})"
            print(f"{status}: {u}")
            if r.destination_url:
                print(f"  dest: {r.destination_url}")
            if r.lv_wrapped_url:
                print(f"  lv:   {r.lv_wrapped_url[:120]}...")
            print(f"  tier: {r.min_rarity_tier}  hops: {len(r.hops)}")

    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
