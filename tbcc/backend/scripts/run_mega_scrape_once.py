#!/usr/bin/env python3
"""
Scrape Telegram channels for direct/paste/file-host links → LV wrap → loot_modifiers.

Uses scraper.session (same as media scraper). Skips LV/AdMaven URLs unless --include-lv
(and TBCC_BYPASS_API_KEY is set).

Usage (from tbcc/backend):
  python scripts/run_mega_scrape_once.py --dry-run
  python scripts/run_mega_scrape_once.py --execute --direct-only
  python scripts/run_mega_scrape_once.py --execute --limit 25 --channel -1002043056722
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv

load_dotenv(_root.parent / ".env")

logging.basicConfig(level=logging.INFO)


def main() -> None:
    p = argparse.ArgumentParser(description="Mega/link scrape from curated Telegram channels")
    p.add_argument("--execute", action="store_true", help="Write loot_modifiers (default: dry-run)")
    p.add_argument("--dry-run", action="store_true", help="Resolve only, no DB writes")
    p.add_argument("--direct-only", action="store_true", help="direct_host + mixed channels (default)")
    p.add_argument("--all-channels", action="store_true", help="Include lv_gated channels (needs bypass)")
    p.add_argument("--include-lv", action="store_true", help="Try obfuscated URLs via bypass.vip")
    p.add_argument("--limit", type=int, default=40, help="Messages per channel (max 200)")
    p.add_argument("--channel", action="append", dest="channels", help="Single chat_id (-100...) repeat ok")
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--use-admin-session",
        action="store_true",
        help="Use admin.session (if your main account joined the scrape channels)",
    )
    args = p.parse_args()

    execute = bool(args.execute) and not args.dry_run
    if not args.execute and not args.dry_run:
        args.dry_run = True

    kinds: set[str] | None = None
    if args.all_channels:
        kinds = None
    elif args.direct_only or not args.all_channels:
        kinds = {"direct_host", "mixed"}

    chat_ids: list[int] | None = None
    if args.channels:
        chat_ids = [int(c) for c in args.channels]

    from app.services.bypass_vip_client import bypass_configured
    from app.services.mega_scrape_service import run_mega_scrape
    from app.utils.telethon_session import admin_session_stem

    session_stem = admin_session_stem() if args.use_admin_session else None

    include_lv = bool(args.include_lv)
    if include_lv and not bypass_configured():
        print("WARN: --include-lv set but bypass not configured; LV URLs will fail.", file=sys.stderr)

    result = asyncio.run(
        run_mega_scrape(
            os.environ["API_ID"],
            os.environ["API_HASH"],
            session_stem=session_stem,
            kinds=kinds,
            chat_ids=chat_ids,
            messages_per_channel=args.limit,
            include_obfuscated=include_lv,
            execute=execute,
        )
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("\n--- mega scrape ---")
        print(f"  execute: {execute}")
        print(f"  sources: {result.get('sources')}")
        st = result.get("stats") or {}
        for k in (
            "channels_scanned",
            "messages_scanned",
            "urls_seen",
            "urls_eligible",
            "resolved",
            "modifiers_created",
            "skipped_duplicate",
            "skipped_obfuscated",
            "pipeline_failed",
        ):
            if k in st:
                print(f"  {k}: {st[k]}")
        errs = st.get("errors") or []
        if errs:
            print(f"  errors ({len(errs)}): {errs[:3]}")
    if not result.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
