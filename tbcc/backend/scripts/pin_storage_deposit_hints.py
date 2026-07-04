#!/usr/bin/env python3
"""Post + pin /deposit hint in each mapped Storage Hub forum subtopic."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_storage_hub_map import AOF_STORAGE_TOPIC_MAP, STORAGE_HUB_IDENT
from app.services.telegram_admin import run_telegram_io

HINT_MARKER = "TBCC deposit hint"
HINT_BODY = (
    "📥 **TBCC deposit** — use in this subtopic (Album Composer / remixer bot):\n"
    "`/deposit 5` → queue **5** newest deduped items (any count 1–200)\n"
    "`/deposit` → default batch · `/deposit 20 both` for photos+videos\n"
    "Admin only · Celery **telegram** queue must be running"
)


async def _topic_has_hint(client, entity, thread_id: int) -> bool:
    async for msg in client.iter_messages(entity, limit=40, reply_to=int(thread_id)):
        text = (getattr(msg, "message", None) or "") or ""
        if HINT_MARKER.lower() in text.lower() or "/deposit" in text.lower():
            return True
    return False


async def _post_and_pin(client, entity, thread_id: int, *, force: bool) -> dict:
    from telethon.tl import functions

    if not force and await _topic_has_hint(client, entity, thread_id):
        return {"status": "skipped", "reason": "hint_exists"}

    body = f"{HINT_MARKER}\n\n{HINT_BODY}"
    sent = await client.send_message(entity, body, reply_to=int(thread_id), link_preview=False)
    msg_id = getattr(sent, "id", None)
    pinned = False
    if msg_id:
        try:
            await client(
                functions.messages.UpdatePinnedMessageRequest(
                    peer=entity,
                    id=int(msg_id),
                    unpin=False,
                    pm_oneside=False,
                )
            )
            pinned = True
        except Exception as e:
            return {"status": "posted", "message_id": msg_id, "pinned": False, "pin_error": str(e)[:120]}
    return {"status": "posted", "message_id": msg_id, "pinned": pinned}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Pin /deposit hints in Storage Hub AOF topics")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--force", action="store_true", help="Post even if a hint already exists")
    p.add_argument("--topics", type=str, default="", help="Comma network keys (milf,full_length); default all")
    args = p.parse_args()

    allow = {k.strip().lower() for k in args.topics.split(",") if k.strip()}
    rows = [r for r in AOF_STORAGE_TOPIC_MAP if r.network_key and (not allow or r.network_key in allow)]

    async def go(storage):
        from app.utils.telegram_peer import resolve_telethon_entity

        entity = await resolve_telethon_entity(storage.client, STORAGE_HUB_IDENT)
        out: list[dict] = []
        for row in rows:
            entry = {
                "network_key": row.network_key,
                "topic_title": row.topic_title,
                "message_thread_id": row.message_thread_id,
            }
            if args.execute:
                try:
                    entry.update(await _post_and_pin(storage.client, entity, row.message_thread_id, force=args.force))
                except Exception as e:
                    entry["status"] = "error"
                    entry["error"] = str(e)[:200]
            else:
                entry["status"] = "would_post"
            out.append(entry)
        return out

    report = asyncio.run(run_telegram_io(go))
    print(json.dumps({"ok": True, "execute": args.execute, "topics": report}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
