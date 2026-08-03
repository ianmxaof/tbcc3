"""
List / verify Loot Room forum topic → AOF network lane map.

  cd tbcc/backend
  py -3.13 scripts/sync_main_group_topic_map.py --list
  py -3.13 scripts/sync_main_group_topic_map.py --verify
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

from app.data.aof_main_group_topic_map import main_group_topic_deep_link
from app.data.aof_network import MAIN_GROUP_IDENT, match_topic_to_network_key, network_channel_by_key
from app.services.main_group_topic_resolve import build_live_topic_map, verify_loot_room_topic_map
from app.services.telegram_admin import run_telegram_io


async def _fetch_topics():
    async def go(storage):
        return await storage.list_forum_topics(MAIN_GROUP_IDENT)

    return await run_telegram_io(go)


def list_live() -> list[dict]:
    topics = asyncio.run(_fetch_topics())
    live_map = build_live_topic_map(topics)
    out = []
    for t in sorted(topics, key=lambda x: str(x.get("title") or "")):
        tid = int(t["id"])
        title = str(t.get("title") or "")
        key = match_topic_to_network_key(title)
        if not key:
            for nk, mapped_tid in live_map.items():
                if mapped_tid == tid:
                    key = nk
                    break
        net = network_channel_by_key(key) if key else None
        out.append(
            {
                "topic_id": tid,
                "topic_title": title,
                "deep_link": main_group_topic_deep_link(tid),
                "network_key": key,
                "receive_channel_id": net.identifier if net else None,
                "receive_channel_name": net.display_name if net else None,
            }
        )
    return out


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true", help="Live Loot Room topics + resolved mappings")
    p.add_argument("--verify", action="store_true", help="Compare static map file vs live Loot Room")
    args = p.parse_args()
    topics = asyncio.run(_fetch_topics())
    if args.verify:
        print(json.dumps(verify_loot_room_topic_map(live_topics=topics), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(list_live(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
