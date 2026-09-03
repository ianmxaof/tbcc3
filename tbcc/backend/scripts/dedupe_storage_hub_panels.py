"""
Dedupe Storage Hub control panels — keep one panel per lane/topic (redis canonical id).

Scans lane deposit panels, Q&A master, live counter, inbox intake, and SENT VAULT panels.
Deletes duplicate bot posts; optional --repost refreshes singleton panels via Bot API.

  cd tbcc/backend
  py -3.13 scripts/dedupe_storage_hub_panels.py --dry-run
  py -3.13 scripts/dedupe_storage_hub_panels.py --apply
  py -3.13 scripts/dedupe_storage_hub_panels.py --apply --repost
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_storage_hub_map import (
    GATEKEEPER_REVIEW_TOPIC_ID,
    INBOX_TOPIC_ID,
    STORAGE_HUB_IDENT,
)
from app.services.storage_sent_cache import storage_sent_cache_topic_id
from app.services.storage_topic_deposit import storage_hub_chat_id_int
from app.services.telegram_admin import run_telegram_io
from app.utils.telegram_forum import normalize_hub_panel_thread_id

PANEL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("lane_deposit", re.compile(r"Lane control panel", re.I)),
    ("qa_master", re.compile(r"MASTER PANEL", re.I)),
    ("qa_live_counter", re.compile(r"Waiting quarantine:", re.I)),
    ("inbox_intake", re.compile(r"Inbox intake panel", re.I)),
    ("sent_cache", re.compile(r"SENT VAULT control panel", re.I)),
    ("legacy_deposit", re.compile(r"Storage deposit panel", re.I)),
    ("lane_manual", re.compile(r"Storage Hub — lane manual", re.I)),
]


def _classify_panel(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    for kind, pattern in PANEL_PATTERNS:
        if pattern.search(raw):
            return kind
    return None


async def _scan_panel_messages(
    client,
    hub,
    *,
    thread_id: int,
    scan_limit: int,
    allowed_kinds: set[str],
) -> list[tuple[int, str]]:
    """Chunked scan — tolerates Telethon TypeNotFound on newer inline-keyboard messages."""
    from telethon.errors.common import TypeNotFoundError

    matches: list[tuple[int, str]] = []
    offset_id = 0
    remaining = max(50, int(scan_limit))
    reply_to = thread_id if thread_id > 0 else None
    skipped_chunks = 0

    while remaining > 0:
        take = min(40, remaining)
        try:
            batch = await client.get_messages(
                hub,
                limit=take,
                reply_to=reply_to,
                offset_id=offset_id,
            )
        except TypeNotFoundError:
            skipped_chunks += 1
            if offset_id <= 0:
                break
            offset_id = max(0, offset_id - 1)
            if skipped_chunks > 25:
                break
            continue

        if not batch:
            break
        for msg in batch:
            mid = int(getattr(msg, "id", 0) or 0)
            if mid <= 0:
                continue
            text = getattr(msg, "message", None) or getattr(msg, "text", None)
            kind = _classify_panel(text)
            if kind and kind in allowed_kinds:
                matches.append((mid, kind))
        remaining -= len(batch)
        last_id = int(getattr(batch[-1], "id", 0) or 0)
        if last_id <= 0 or len(batch) < take:
            break
        offset_id = last_id

    return matches


def _lane_keep_id(chat_id: int, thread_id: int) -> int | None:
    from app.services.storage_deposit_panel_pins import get_stored_panel_message_id

    return get_stored_panel_message_id(chat_id, thread_id)


def _qa_master_keep_id(chat_id: int, thread_id: int) -> int | None:
    from app.services.qa_master_panel import get_stored_panel_message_id

    return get_stored_panel_message_id(chat_id, normalize_hub_panel_thread_id(thread_id))


def _qa_counter_keep_id(chat_id: int) -> int | None:
    from app.services.qa_live_counter import get_stored_counter_message_id

    return get_stored_counter_message_id(chat_id)


def _hub_panel_keep_id(kind: str, chat_id: int, thread_id: int) -> int | None:
    from app.services.storage_hub_control_panels import get_stored_hub_panel_message_id

    return get_stored_hub_panel_message_id(kind, chat_id, thread_id)


def _panel_targets() -> list[dict[str, Any]]:
    from app.data.aof_storage_hub_map import AOF_STORAGE_TOPIC_MAP
    from app.services.storage_deposit_panel_pins import storage_deposit_panel_targets

    chat_id = storage_hub_chat_id_int()
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    for row in storage_deposit_panel_targets():
        tid = int(row["message_thread_id"]) if row.get("message_thread_id") is not None else 0
        key = (chat_id, tid)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "chat_id": chat_id,
                "thread_id": tid,
                "title": row.get("topic_title") or "",
                "keep_resolver": lambda c=chat_id, t=tid: _lane_keep_id(c, t),
                "kinds": {"lane_deposit", "legacy_deposit", "lane_manual", "qa_master"},
            }
        )

    qa_tid = normalize_hub_panel_thread_id(int(GATEKEEPER_REVIEW_TOPIC_ID or 1))
    qa_key = (chat_id, qa_tid)
    if qa_key not in seen:
        seen.add(qa_key)
        out.append(
            {
                "chat_id": chat_id,
                "thread_id": qa_tid,
                "title": "Q&A | APPROVE / DENY",
                "keep_resolver": lambda c=chat_id, t=qa_tid: _qa_master_keep_id(c, t),
                "kinds": {"qa_master", "qa_live_counter"},
                "counter_keep": lambda c=chat_id: _qa_counter_keep_id(c),
            }
        )

    inbox_tid = int(INBOX_TOPIC_ID)
    inbox_key = (chat_id, inbox_tid)
    if inbox_key not in seen:
        seen.add(inbox_key)
        out.append(
            {
                "chat_id": chat_id,
                "thread_id": inbox_tid,
                "title": "AOF INBOX",
                "keep_resolver": lambda c=chat_id, t=inbox_tid: _hub_panel_keep_id("inbox", c, t),
                "kinds": {"inbox_intake"},
            }
        )

    vault_tid = int(storage_sent_cache_topic_id())
    vault_key = (chat_id, vault_tid)
    if vault_key not in seen:
        seen.add(vault_key)
        out.append(
            {
                "chat_id": chat_id,
                "thread_id": vault_tid,
                "title": "SENT VAULT",
                "keep_resolver": lambda c=chat_id, t=vault_tid: _hub_panel_keep_id("sent_cache", c, t),
                "kinds": {"sent_cache"},
            }
        )

    return out


async def _run(*, apply: bool, scan_limit: int) -> dict[str, Any]:
    async def go(storage):
        from app.utils.telegram_peer import resolve_telethon_entity

        hub = await resolve_telethon_entity(storage.client, STORAGE_HUB_IDENT)
        client = storage.client
        report: dict[str, Any] = {"dry_run": not apply, "topics": [], "deleted": []}

        for target in _panel_targets():
            thread_id = int(target["thread_id"])
            title = target.get("title") or ""
            keep_ids: set[int] = set()
            resolver: Callable[[], int | None] = target["keep_resolver"]
            stored = resolver()
            if stored and int(stored) > 0:
                keep_ids.add(int(stored))
            counter_keep = target.get("counter_keep")
            if counter_keep:
                cmid = counter_keep()
                if cmid and int(cmid) > 0:
                    keep_ids.add(int(cmid))

            allowed_kinds = set(target.get("kinds") or [])
            matches = await _scan_panel_messages(
                client,
                hub,
                thread_id=thread_id,
                scan_limit=int(scan_limit),
                allowed_kinds=allowed_kinds,
            )

            if not matches:
                report["topics"].append(
                    {"thread_id": thread_id, "title": title, "panels_found": 0, "deleted": 0}
                )
                continue

            if not keep_ids:
                # No redis canonical — keep newest panel message only.
                keep_ids.add(max(mid for mid, _ in matches))

            to_delete = [(mid, kind) for mid, kind in matches if mid not in keep_ids]
            topic_entry = {
                "thread_id": thread_id,
                "title": title,
                "panels_found": len(matches),
                "keep_ids": sorted(keep_ids),
                "deleted": 0,
            }
            for mid, kind in to_delete:
                entry = {
                    "thread_id": thread_id,
                    "title": title,
                    "message_id": mid,
                    "kind": kind,
                    "keep_ids": sorted(keep_ids),
                }
                if apply:
                    try:
                        await client.delete_messages(hub, mid)
                        entry["deleted"] = True
                        topic_entry["deleted"] += 1
                        await asyncio.sleep(0.15)
                    except Exception as e:
                        entry["deleted"] = False
                        entry["error"] = str(e)[:200]
                report["deleted"].append(entry)
            report["topics"].append(topic_entry)
        return report

    return await run_telegram_io(go)


async def _repost_panels() -> dict[str, Any]:
    import os

    from telegram import Bot

    token = (os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "error": "bot_token_missing"}
    bot = Bot(token)
    from app.services.qa_live_counter import ensure_qa_live_counter
    from app.services.storage_hub_control_panels import ensure_all_hub_control_panels

    hub = await ensure_all_hub_control_panels(bot, force_new=False)
    counter = await ensure_qa_live_counter(bot, force_new=False)
    return {"ok": True, "hub": hub, "counter": counter}


def main() -> None:
    p = argparse.ArgumentParser(description="Dedupe Storage Hub singleton control panels")
    p.add_argument("--apply", action="store_true", help="Delete duplicates (default dry-run)")
    p.add_argument("--scan-limit", type=int, default=400, help="Messages to scan per topic")
    p.add_argument(
        "--repost",
        action="store_true",
        help="After dedupe, refresh canonical panels via Bot API (use with --apply)",
    )
    args = p.parse_args()

    report = asyncio.run(_run(apply=bool(args.apply), scan_limit=int(args.scan_limit)))
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n=== {mode} panel dedupe ===")
    for topic in report.get("topics") or []:
        print(
            f"  {topic.get('title')} (thread {topic.get('thread_id')}): "
            f"found={topic.get('panels_found')} keep={topic.get('keep_ids')} "
            f"deleted={topic.get('deleted')}"
        )
    deleted = report.get("deleted") or []
    print(f"\nCandidates: {len(deleted)}")
    for row in deleted[:40]:
        flag = "DELETE" if args.apply and row.get("deleted") else "would_delete"
        err = f" ERR={row.get('error')}" if row.get("error") else ""
        print(
            f"  [{flag}] {row.get('kind')} thread={row.get('thread_id')} "
            f"msg={row.get('message_id')}{err}"
        )
    if len(deleted) > 40:
        print(f"  ... +{len(deleted) - 40} more")

    if args.repost:
        if not args.apply:
            print("\n--repost ignored without --apply")
        else:
            repost = asyncio.run(_repost_panels())
            print(f"\nRepost: {repost}")


if __name__ == "__main__":
    main()
