"""
Run Telegram scrape for one source (or all active telegram_channel sources).

Requires: tbcc/.env with API_ID, API_HASH; Telethon session `scraper.session` (created on first run).
Usage (from tbcc/backend):
  python scripts/run_scrape_once.py 1
  python scripts/run_scrape_once.py   # all active sources
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
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        sid = int(sys.argv[1])
    from bots.scraper_bot import run_scraper

    asyncio.run(
        run_scraper(
            api_id=os.environ["API_ID"],
            api_hash=os.environ["API_HASH"],
            source_id=sid,
        )
    )


if __name__ == "__main__":
    main()
