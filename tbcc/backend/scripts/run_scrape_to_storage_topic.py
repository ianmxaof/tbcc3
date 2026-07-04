#!/usr/bin/env python3
"""
Scrape a Telegram channel and deposit media into a Storage Hub forum subtopic.

  cd tbcc/backend
  py -3.13 scripts/run_scrape_to_storage_topic.py --source -1003733929993 --topic-key bop
  py -3.13 scripts/run_scrape_to_storage_topic.py --source -1003733929993 --topic-id 9501 --execute --limit 100

Requires admin.session (Telethon account joined to source + Storage Hub).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_storage_hub_map import AOF_STORAGE_TOPIC_MAP, STORAGE_HUB_IDENT, storage_map_by_key
from app.services.telegram_admin import run_telegram_io


def _resolve_topic(*, topic_key: str | None, topic_id: int | None) -> tuple[int, str]:
    if topic_id is not None:
        for row in AOF_STORAGE_TOPIC_MAP:
            if int(row.message_thread_id) == int(topic_id):
                return int(row.message_thread_id), row.topic_title
        return int(topic_id), f"topic:{topic_id}"
    key = (topic_key or "bop").strip().lower()
    row = storage_map_by_key().get(key)
    if not row:
        raise SystemExit(f"Unknown --topic-key {key!r}; use --topic-id or one of: {', '.join(storage_map_by_key())}")
    return int(row.message_thread_id), row.topic_title


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="Channel scrape → Storage Hub forum topic")
    p.add_argument("--source", required=True, help="Source channel id (@name or -100…)")
    p.add_argument("--topic-key", default="bop", help="AOF storage map key (default: bop)")
    p.add_argument("--topic-id", type=int, default=None, help="Forum message_thread_id override")
    p.add_argument("--dest", default=STORAGE_HUB_IDENT, help="Storage hub group id")
    p.add_argument("--limit", type=int, default=80, help="Max messages to scan (1–500)")
    p.add_argument("--media-types", choices=["both", "photos", "videos"], default="both")
    p.add_argument("--execute", action="store_true", help="Run scrape (default: preview only)")
    args = p.parse_args()

    thread_id, topic_title = _resolve_topic(topic_key=args.topic_key, topic_id=args.topic_id)
    preview = {
        "execute": args.execute,
        "source_channel": args.source.strip(),
        "dest_channel": args.dest.strip(),
        "topic_title": topic_title,
        "message_thread_id": thread_id,
        "topic_deep_link": f"https://t.me/c/3812457581/{thread_id}",
        "limit": max(1, min(int(args.limit), 500)),
        "media_types": args.media_types,
    }
    if not args.execute:
        preview["status"] = "preview — pass --execute to run"
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        return 0

    async def _run(storage):
        return await storage.forward_channel_to_forum_topic(
            args.source.strip(),
            args.dest.strip(),
            thread_id,
            limit=preview["limit"],
            media_types=args.media_types,
        )

    try:
        result = asyncio.run(run_telegram_io(_run))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:500], **preview}, indent=2, ensure_ascii=False))
        return 1

    out = {"ok": True, **preview, **result}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if (result.get("forwarded", 0) + result.get("uploaded", 0)) > 0 or result.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
