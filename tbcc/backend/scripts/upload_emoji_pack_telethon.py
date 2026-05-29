"""
Upload emoji-factory manifest tiles as a Telegram custom emoji pack (admin session).

  cd tbcc/backend
  python scripts/upload_emoji_pack_telethon.py --manifest ../path/manifest.json --dry-run
  python scripts/upload_emoji_pack_telethon.py --manifest ../path/manifest.json --title "Wall" --short-name my_pack_v1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv

load_dotenv(_root.parent / ".env", override=True)

from app.services.emoji_pack_telethon import upload_custom_emoji_pack_from_manifest
from app.services.telegram_admin import get_telegram_client, import_lock


async def _main() -> int:
    p = argparse.ArgumentParser(description="Upload emoji-factory pack via Telethon")
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--title", default="TBCC emoji pack")
    p.add_argument("--short-name", required=True, help="Base short name (script adds _by_<user_id> if needed)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    async with import_lock():
        client = await get_telegram_client()
        result = await upload_custom_emoji_pack_from_manifest(
            client,
            manifest_path=args.manifest,
            title=args.title,
            short_name=args.short_name,
            dry_run=args.dry_run,
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
