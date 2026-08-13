"""
Remove legacy Storage Hub bot clutter from forum lanes:
  - Old payment-bot "Storage deposit panel" (depctl) duplicates
  - Standalone SENT VAULT / SENT CACHE composer summary posts

Keeps media, operator text, and non-matching bot posts.

  cd tbcc/backend
  py -3.13 scripts/cleanup_storage_hub_legacy_bot_messages.py --dry-run
  py -3.13 scripts/cleanup_storage_hub_legacy_bot_messages.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_storage_hub_map import (
    AOF_STORAGE_TOPIC_MAP,
    GATEKEEPER_REVIEW_TOPIC_ID,
    INBOX_TOPIC_ID,
    STORAGE_HUB_IDENT,
)
from app.services.storage_sent_cache import storage_sent_cache_topic_id
from app.services.telegram_admin import run_telegram_io

LEGACY_PANEL = re.compile(r"Storage deposit panel", re.I)
COMPOSER_SUMMARY = re.compile(r"SENT\s+(?:VAULT|CACHE)\s+composer", re.I)
LANE_PANEL = re.compile(r"Lane control panel", re.I)


def _should_delete(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if LEGACY_PANEL.search(raw):
        return "legacy_deposit_panel"
    if COMPOSER_SUMMARY.search(raw):
        return "composer_summary"
    return None


def _lane_panel_dupes(text: str | None) -> bool:
    return bool(LANE_PANEL.search(text or ""))


async def _run(*, apply: bool, include_lane_panels: bool) -> dict:
    topics = [
        (int(row.message_thread_id), row.topic_title, row.network_key)
        for row in AOF_STORAGE_TOPIC_MAP
        if row.network_key
    ]
    topics.append((int(INBOX_TOPIC_ID), "INBOX", "inbox"))
    # Skip Q&A + SENT VAULT archive topics
    skip = {int(GATEKEEPER_REVIEW_TOPIC_ID or 0), int(storage_sent_cache_topic_id())}

    async def go(storage):
        from app.utils.telegram_peer import resolve_telethon_entity

        hub = await resolve_telethon_entity(storage.client, STORAGE_HUB_IDENT)
        report: dict = {"deleted": [], "skipped_topics": list(skip), "dry_run": not apply}
        for thread_id, title, nk in topics:
            if thread_id in skip:
                continue
            candidates: list[tuple[int, str, str]] = []
            lane_panels: list[int] = []
            async for msg in storage.client.iter_messages(
                hub,
                limit=400,
                reply_to=thread_id,
            ):
                mid = int(getattr(msg, "id", 0) or 0)
                if mid <= 0:
                    continue
                text = getattr(msg, "message", None) or getattr(msg, "text", None)
                reason = _should_delete(text)
                if reason:
                    candidates.append((mid, reason, title))
                elif include_lane_panels and _lane_panel_dupes(text):
                    lane_panels.append(mid)
            # Remove all lane panels — remixer bootstrap will post one fresh copy
            for mid in lane_panels:
                candidates.append((mid, "lane_panel_reset", title))
            for mid, reason, ttitle in candidates:
                entry = {
                    "topic_id": thread_id,
                    "topic_title": ttitle,
                    "message_id": mid,
                    "reason": reason,
                }
                if apply:
                    try:
                        await storage.client.delete_messages(hub, mid)
                        entry["deleted"] = True
                    except Exception as e:
                        entry["deleted"] = False
                        entry["error"] = str(e)[:200]
                report["deleted"].append(entry)
        return report

    return await run_telegram_io(go)


def main() -> None:
    p = argparse.ArgumentParser(description="Clean legacy Storage Hub bot messages from lane topics")
    p.add_argument("--apply", action="store_true", help="Actually delete (default is dry-run)")
    p.add_argument(
        "--include-lane-panels",
        action="store_true",
        help="Also delete existing Lane control panel messages (remixer will repost on start)",
    )
    args = p.parse_args()
    report = asyncio.run(_run(apply=bool(args.apply), include_lane_panels=bool(args.include_lane_panels)))
    deleted = report.get("deleted") or []
    by_reason: dict[str, int] = {}
    for row in deleted:
        by_reason[row["reason"]] = by_reason.get(row["reason"], 0) + 1
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n=== {mode} ===")
    print(f"Candidates: {len(deleted)}")
    for reason, n in sorted(by_reason.items()):
        print(f"  {reason}: {n}")
    for row in deleted[:40]:
        print(
            f"  [{row.get('reason')}] {row.get('topic_title')} "
            f"thread={row.get('topic_id')} msg={row.get('message_id')}"
            + (f" ERR={row.get('error')}" if row.get("error") else "")
        )
    if len(deleted) > 40:
        print(f"  ... +{len(deleted) - 40} more")


if __name__ == "__main__":
    main()
