"""
List / verify Storage Hub forum topic → AOF channel map.

  cd tbcc/backend
  py -3.13 scripts/sync_storage_hub_map.py --list
  py -3.13 scripts/sync_storage_hub_map.py --verify
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

from app.data.aof_network import network_channel_by_key
from app.data.aof_storage_hub_map import (
    AOF_STORAGE_TOPIC_MAP,
    STORAGE_HUB_IDENT,
    network_key_for_storage_topic,
    topic_deep_link,
)
from app.database.session import SessionLocal
from app.models.channel import Channel
from app.models.content_pool import ContentPool
from app.services.telegram_admin import run_telegram_io


async def _fetch_topics():
    async def go(storage):
        return await storage.list_forum_topics(STORAGE_HUB_IDENT)

    return await run_telegram_io(go)


def verify_map() -> dict:
    topics = asyncio.run(_fetch_topics())
    live = {int(t["id"]): str(t.get("title") or "") for t in topics if t.get("id") is not None}
    rows = []
    for m in AOF_STORAGE_TOPIC_MAP:
        net = network_channel_by_key(m.network_key)
        title_live = live.get(m.message_thread_id, "")
        rows.append(
            {
                "network_key": m.network_key,
                "topic_id": m.message_thread_id,
                "topic_title_map": m.topic_title,
                "topic_title_live": title_live,
                "title_match": title_live == m.topic_title or not title_live,
                "deep_link": topic_deep_link(m.message_thread_id),
                "receive_channel": net.identifier if net else None,
                "receive_name": net.display_name if net else None,
                "pool_name": net.pool_name if net else None,
            }
        )
    unmapped_live = [
        {"id": tid, "title": title}
        for tid, title in sorted(live.items())
        if not network_key_for_storage_topic(tid, title)
    ]
    return {"mapped": rows, "unmapped_live_topics": unmapped_live}


def list_live() -> list[dict]:
    topics = asyncio.run(_fetch_topics())
    out = []
    db = SessionLocal()
    try:
        for t in sorted(topics, key=lambda x: str(x.get("title") or "")):
            tid = int(t["id"])
            title = str(t.get("title") or "")
            key = network_key_for_storage_topic(tid, title)
            net = network_channel_by_key(key) if key else None
            pool = None
            if net:
                pool = db.query(ContentPool).filter(ContentPool.name == net.pool_name).first()
            out.append(
                {
                    "topic_id": tid,
                    "topic_title": title,
                    "deep_link": topic_deep_link(tid),
                    "network_key": key,
                    "receive_channel_id": net.identifier if net else None,
                    "receive_channel_name": net.display_name if net else None,
                    "pool_id": pool.id if pool else None,
                    "pool_name": net.pool_name if net else None,
                }
            )
    finally:
        db.close()
    return out


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true", help="Live topics + resolved mappings")
    p.add_argument("--verify", action="store_true", help="Compare map file vs live group")
    args = p.parse_args()
    if args.verify:
        print(json.dumps(verify_map(), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(list_live(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
