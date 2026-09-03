"""
One-time: forward media from a Storage Hub forum topic → [ 🔞 ] REVIEW (827).

Default source is Q&A | APPROVE / DENY (topic 1). Skips bot panels and text-only posts.
Albums are forwarded as grouped batches when possible.

  cd tbcc/backend
  py -3.13 scripts/forward_hub_media_to_review_topic.py --dry-run
  py -3.13 scripts/forward_hub_media_to_review_topic.py --apply --limit 500
  py -3.13 scripts/forward_hub_media_to_review_topic.py --apply --delete-source
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.data.aof_storage_hub_map import (
    GATEKEEPER_REVIEW_TOPIC_ID,
    REVIEW_TOPIC_ID,
    REVIEW_TOPIC_TITLE,
    STORAGE_HUB_IDENT,
)
from app.services.telegram_admin import run_telegram_io
from app.services.telegram_storage import _channel_message_media_kind

SKIP_TEXT = re.compile(
    r"Lane control panel|MASTER PANEL|Inbox intake panel|SENT VAULT control panel|"
    r"Storage deposit panel|Storage Hub — lane manual|Waiting quarantine:|"
    r"QUARANTINE.*batch|INBOX QUARANTINE|Approve batch|Review all waiting",
    re.I,
)


def _iter_kwargs(message_thread_id: int | None) -> dict[str, Any]:
    if message_thread_id is None:
        return {}
    return {"reply_to": int(message_thread_id)}


def _is_skippable_bot_post(text: str | None) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    return bool(SKIP_TEXT.search(raw))


async def _reupload_to_forum_thread(
    storage,
    client,
    hub,
    messages: list[Any],
    *,
    dest_thread: int,
) -> None:
    """Re-upload media into a forum subtopic (Storage Hub blocks forwards)."""
    if len(messages) == 1:
        msg = messages[0]
        kind = _channel_message_media_kind(msg) or "photo"
        data = await client.download_media(msg, bytes)
        if not data:
            raise RuntimeError(f"download_media empty for msg_id={getattr(msg, 'id', '?')}")
        f, kwargs, _bucket = storage._prepare_file_for_send(data, kind, source_message=msg)
        await client.send_file(
            hub,
            f,
            reply_to=int(dest_thread),
            silent=True,
            **kwargs,
        )
        return

    prepared: list[tuple[Any, dict]] = []
    for msg in messages:
        kind = _channel_message_media_kind(msg) or "photo"
        data = await client.download_media(msg, bytes)
        if not data:
            raise RuntimeError(f"download_media empty for msg_id={getattr(msg, 'id', '?')}")
        f, kwargs, _bucket = storage._prepare_file_for_send(data, kind, source_message=msg)
        prepared.append((f, kwargs))
    files = [p[0] for p in prepared]
    kwargs = {**prepared[0][1], "reply_to": int(dest_thread), "silent": True}
    await client.send_file(hub, files, **kwargs)


async def _collect_media_messages(
    client,
    hub,
    *,
    source_thread: int,
    limit: int,
) -> tuple[list[Any], int, int, int]:
    """Chunked scan — tolerates Telethon TypeNotFound on newer inline-keyboard messages."""
    from telethon.errors.common import TypeNotFoundError

    media_msgs: list[Any] = []
    scanned = 0
    skipped_panel = 0
    skipped_no_media = 0
    offset_id = 0
    remaining = max(1, int(limit))
    reply_to = source_thread if source_thread > 0 else None
    skipped_chunks = 0

    while remaining > 0:
        take = min(60, remaining)
        try:
            batch = await client.get_messages(
                hub,
                limit=take,
                reply_to=reply_to,
                offset_id=offset_id,
            )
        except TypeNotFoundError:
            skipped_chunks += 1
            if offset_id <= 0 or skipped_chunks > 40:
                break
            offset_id = max(0, offset_id - 1)
            continue

        if not batch:
            break
        for msg in batch:
            scanned += 1
            text = getattr(msg, "message", None) or getattr(msg, "text", None)
            if _is_skippable_bot_post(text):
                skipped_panel += 1
                continue
            if not _channel_message_media_kind(msg):
                skipped_no_media += 1
                continue
            media_msgs.append(msg)
        remaining -= len(batch)
        last_id = int(getattr(batch[-1], "id", 0) or 0)
        if last_id <= 0 or len(batch) < take:
            break
        offset_id = last_id

    media_msgs.reverse()
    return media_msgs, scanned, skipped_panel, skipped_no_media


async def _run(
    *,
    apply: bool,
    source_thread: int,
    dest_thread: int,
    limit: int,
    delete_source: bool,
    pause_s: float,
) -> dict[str, Any]:
    async def go(storage):
        from app.utils.telegram_peer import resolve_telethon_entity

        hub = await resolve_telethon_entity(storage.client, STORAGE_HUB_IDENT)
        client = storage.client

        media_msgs, scanned, skipped_panel, skipped_no_media = await _collect_media_messages(
            client,
            hub,
            source_thread=source_thread,
            limit=limit,
        )

        forwarded = 0
        errors = 0
        deleted = 0
        albums = 0
        singles = 0
        seen_groups: set[int] = set()
        actions: list[dict[str, Any]] = []

        i = 0
        done_batches = 0
        while i < len(media_msgs):
            msg = media_msgs[i]
            gid = int(getattr(msg, "grouped_id", 0) or 0)
            batch: list[Any] = [msg]
            if gid:
                j = i + 1
                while j < len(media_msgs) and int(getattr(media_msgs[j], "grouped_id", 0) or 0) == gid:
                    batch.append(media_msgs[j])
                    j += 1
                if gid in seen_groups:
                    i = j
                    continue
                seen_groups.add(gid)
                i = j
            else:
                i += 1

            ids = [int(getattr(m, "id", 0) or 0) for m in batch if int(getattr(m, "id", 0) or 0) > 0]
            if not ids:
                continue

            entry = {
                "source_thread": source_thread,
                "dest_thread": dest_thread,
                "message_ids": ids,
                "album": len(ids) > 1,
            }
            if apply:
                try:
                    await _reupload_to_forum_thread(
                        storage,
                        client,
                        hub,
                        batch,
                        dest_thread=int(dest_thread),
                    )
                    forwarded += len(ids)
                    if len(ids) > 1:
                        albums += 1
                    else:
                        singles += 1
                    entry["forwarded"] = True
                    if delete_source:
                        await client.delete_messages(hub, ids)
                        deleted += len(ids)
                        entry["deleted_source"] = True
                    done_batches += 1
                    if done_batches % 10 == 0:
                        print(
                            f"  progress: {done_batches} batch(es), "
                            f"{forwarded} msg(s) re-uploaded, {errors} err(s)",
                            flush=True,
                        )
                except Exception as e:
                    errors += 1
                    entry["forwarded"] = False
                    entry["error"] = str(e)[:200]
                    print(f"  ERR batch ids={ids}: {entry['error']}", flush=True)
                if pause_s > 0:
                    await asyncio.sleep(pause_s)
            else:
                entry["forwarded"] = False
                entry["dry_run"] = True
            actions.append(entry)

        return {
            "ok": True,
            "dry_run": not apply,
            "source_thread": source_thread,
            "dest_thread": dest_thread,
            "dest_title": REVIEW_TOPIC_TITLE,
            "scanned": scanned,
            "media_candidates": len(media_msgs),
            "skipped_panel": skipped_panel,
            "skipped_no_media": skipped_no_media,
            "forwarded": forwarded,
            "albums": albums,
            "singles": singles,
            "deleted_source": deleted,
            "errors": errors,
            "actions": actions,
        }

    return await run_telegram_io(go)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Forward Storage Hub topic media → [ 🔞 ] REVIEW (827)",
    )
    p.add_argument("--apply", action="store_true", help="Actually forward (default dry-run)")
    p.add_argument(
        "--source-thread",
        type=int,
        default=int(GATEKEEPER_REVIEW_TOPIC_ID or 1),
        help="Source forum topic id (default Q&A APPROVE/DENY = 1)",
    )
    p.add_argument(
        "--dest-thread",
        type=int,
        default=int(REVIEW_TOPIC_ID),
        help=f"Destination topic id (default REVIEW = {REVIEW_TOPIC_ID})",
    )
    p.add_argument("--limit", type=int, default=2000, help="Max messages to scan in source topic")
    p.add_argument(
        "--delete-source",
        action="store_true",
        help="After successful forward, delete source copies (only with --apply)",
    )
    p.add_argument("--pause-s", type=float, default=0.35, help="Pause between forwards (flood control)")
    args = p.parse_args()

    if args.delete_source and not args.apply:
        print("ERROR: --delete-source requires --apply")
        raise SystemExit(2)

    report = asyncio.run(
        _run(
            apply=bool(args.apply),
            source_thread=int(args.source_thread),
            dest_thread=int(args.dest_thread),
            limit=int(args.limit),
            delete_source=bool(args.delete_source),
            pause_s=float(args.pause_s),
        )
    )

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n=== {mode} ===")
    print(f"Source thread: {report.get('source_thread')} -> REVIEW thread {report.get('dest_thread')}")
    print(f"Scanned: {report.get('scanned')} · media candidates: {report.get('media_candidates')}")
    print(f"Skipped panels: {report.get('skipped_panel')} · skipped non-media: {report.get('skipped_no_media')}")
    if args.apply:
        print(
            f"Forwarded: {report.get('forwarded')} "
            f"({report.get('albums')} albums, {report.get('singles')} singles) · "
            f"errors: {report.get('errors')} · deleted source: {report.get('deleted_source')}"
        )
    else:
        actions = report.get("actions") or []
        print(f"Would forward {sum(len(a.get('message_ids') or []) for a in actions)} message(s) in {len(actions)} batch(es)")
    for row in (report.get("actions") or [])[:25]:
        ids = row.get("message_ids") or []
        tag = "album" if row.get("album") else "single"
        extra = f" ERR={row.get('error')}" if row.get("error") else ""
        print(f"  [{tag}] ids={ids}{extra}")
    rest = len(report.get("actions") or []) - 25
    if rest > 0:
        print(f"  ... +{rest} more batch(es)")


if __name__ == "__main__":
    main()
