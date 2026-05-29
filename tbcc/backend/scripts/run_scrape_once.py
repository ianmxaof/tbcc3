"""
Run Telegram scrape for one source (or all active telegram_channel sources).

Requires: tbcc/.env with API_ID, API_HASH; Telethon session `scraper.session` (created on first run).

The numeric argument is SOURCE ID (Automation -> Ingest table "ID" column), NOT pool id.
Pool id is configured on the source row and used automatically.

Usage (from tbcc/backend):
  python scripts/run_scrape_once.py 1
  python scripts/run_scrape_once.py   # all active telegram sources

Prefer first-time login via:
  cd .. && .\\scripts\\setup-scraper-session.ps1 -SourceId 1
"""
from __future__ import annotations

import asyncio
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
    sid: int | None = None
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg in ("-h", "--help"):
            print(__doc__)
            return
        if arg.isdigit():
            sid = int(arg)
        else:
            print(
                f"Invalid source id {arg!r}. Use the SOURCE ID from Automation -> Ingest (ID column), "
                "not pool id or Telegram channel id.\n"
                "Example: python scripts/run_scrape_once.py 1\n"
                "Or: ..\\scripts\\setup-scraper-session.ps1 -SourceId 1"
            )
            sys.exit(2)
    from bots.scraper_bot import run_scraper

    stats = asyncio.run(
        run_scraper(
            api_id=os.environ["API_ID"],
            api_hash=os.environ["API_HASH"],
            source_id=sid,
        )
    )
    print("\n--- scrape result ---")
    for key in (
        "messages_scanned",
        "stored",
        "skipped_duplicate",
        "skipped_media_type",
        "skipped_no_media",
        "errors_count",
        "status",
    ):
        if key in stats:
            print(f"  {key}: {stats[key]}")
    if stats.get("error_summary"):
        print(f"  error_summary: {stats['error_summary']}")
    if stats.get("errors"):
        print(f"  errors: {stats['errors'][:3]}")
    if stats.get("fatal"):
        sys.exit(1)


if __name__ == "__main__":
    main()
