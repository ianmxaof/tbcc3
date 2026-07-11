"""SENT CACHE composer — bundle stamped items into albums, export to Loot Room + Erome."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.data.aof_main_group_topic_map import main_topic_for_network_key
from app.data.aof_network import MAIN_GROUP_IDENT
from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT
from app.models.media import Media
from app.services.album_service import chunk_into_full_albums, post_album
from app.services.cache_album_caption import build_cache_album_caption_html, build_main_group_caption_html
from app.services.storage_sent_cache import storage_sent_cache_topic_id

logger = logging.getLogger(__name__)


def composer_enabled() -> bool:
    return (os.getenv("TBCC_SENT_CACHE_COMPOSER_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def cache_album_size() -> int:
    raw = (os.getenv("TBCC_SENT_CACHE_ALBUM_SIZE") or "5").strip()
    try:
        return max(2, min(10, int(raw)))
    except ValueError:
        return 5


def rebundle_cache_enabled() -> bool:
    return (os.getenv("TBCC_SENT_CACHE_COMPOSER_REBUNDLE_CACHE") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def main_group_export_enabled() -> bool:
    return (os.getenv("TBCC_SENT_CACHE_COMPOSER_MAIN_GROUP") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def erome_export_enabled() -> bool:
    return (os.getenv("TBCC_SENT_CACHE_COMPOSER_EROME") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _media_type_bucket(m: Media) -> str:
    t = (m.media_type or "document").lower()
    if t not in ("photo", "video", "document", "gif"):
        return "document"
    return t


def _chunk_media_rows(rows: list[Media], size: int) -> list[list[Media]]:
    by_type: dict[str, list[Media]] = defaultdict(list)
    for m in sorted(rows, key=lambda x: int(x.id)):
        by_type[_media_type_bucket(m)].append(m)
    albums: list[list[Media]] = []
    for bucket in by_type.values():
        albums.extend(chunk_into_full_albums(bucket, size))
    return albums


def _cache_message_ids_for_chunk(
    chunk: list[Media],
    moved_items: list[dict[str, Any]],
) -> list[int]:
    mid_map = {int(x["media_id"]): int(x["cache_message_id"]) for x in moved_items if x.get("media_id")}
    return [mid_map[int(m.id)] for m in chunk if int(m.id) in mid_map]


async def compose_sent_cache_albums_async(
    db: Session,
    storage,
    *,
    network_key: str,
    media_ids: list[int],
    pool_id: int | None,
    moved_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build full albums from a deposit batch; rebundle cache, mirror main, upload Erome."""
    if not composer_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}
    nk = (network_key or "").strip().lower()
    if not nk or not media_ids:
        return {"ok": False, "error": "missing network_key or media_ids"}

    rows = db.query(Media).filter(Media.id.in_([int(x) for x in media_ids])).all()
    if not rows:
        return {"ok": False, "error": "no_media_rows"}

    size = cache_album_size()
    albums = _chunk_media_rows(rows, size)
    if not albums:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_full_albums",
            "approved": len(rows),
            "album_size": size,
        }

    from app.utils.telegram_peer import resolve_telethon_entity

    hub_entity = await resolve_telethon_entity(storage.client, STORAGE_HUB_IDENT)
    cache_tid = storage_sent_cache_topic_id()
    main_row = main_topic_for_network_key(nk) if main_group_export_enabled() else None
    main_entity = None
    if main_row:
        main_entity = await resolve_telethon_entity(storage.client, MAIN_GROUP_IDENT)

    cache_cap = build_cache_album_caption_html(db, nk)
    main_cap = build_main_group_caption_html(db, nk)
    moved_items = moved_items or []

    report_albums: list[dict[str, Any]] = []
    for idx, chunk in enumerate(albums, start=1):
        mids = [int(m.id) for m in chunk]
        album_rec: dict[str, Any] = {
            "index": idx,
            "media_ids": mids,
            "count": len(chunk),
            "cache": None,
            "main_group": None,
            "erome": None,
        }

        if rebundle_cache_enabled():
            try:
                old_cache_ids = _cache_message_ids_for_chunk(chunk, moved_items)
                msg_ids = await post_album(
                    storage.client,
                    hub_entity,
                    chunk,
                    caption=cache_cap,
                    reply_to=cache_tid,
                    send_silent=True,
                )
                album_rec["cache"] = {"ok": bool(msg_ids), "telegram_message_ids": msg_ids}
                if msg_ids and old_cache_ids:
                    try:
                        await storage.client.delete_messages(hub_entity, old_cache_ids)
                    except Exception:
                        logger.debug("cache single cleanup failed", exc_info=True)
                if msg_ids:
                    anchor = int(msg_ids[0])
                    for m in chunk:
                        m.telegram_message_id = anchor
                    db.commit()
            except Exception as e:
                album_rec["cache"] = {"ok": False, "error": str(e)[:200]}
        else:
            album_rec["cache"] = {"ok": True, "skipped": True}

        if main_row and main_entity:
            try:
                main_msg_ids = await post_album(
                    storage.client,
                    main_entity,
                    chunk,
                    caption=main_cap,
                    reply_to=int(main_row.message_thread_id),
                    send_silent=True,
                )
                album_rec["main_group"] = {
                    "ok": bool(main_msg_ids),
                    "topic_id": int(main_row.message_thread_id),
                    "telegram_message_ids": main_msg_ids,
                }
                if main_msg_ids and pool_id:
                    try:
                        from app.services.content_performance import record_post_delivery_metric

                        record_post_delivery_metric(
                            db,
                            outbound_event=None,
                            event_type="cache_composer_main",
                            channel=None,
                            pool_id=int(pool_id),
                            telegram_message_id=int(main_msg_ids[0]),
                            telegram_message_ids=main_msg_ids,
                            media_ids=mids,
                            network_key=nk,
                            export_source="cache_deposit",
                            surface="telegram",
                        )
                        db.commit()
                    except Exception:
                        logger.debug("cache composer delivery metric skipped", exc_info=True)
            except Exception as e:
                album_rec["main_group"] = {"ok": False, "error": str(e)[:200]}

        if erome_export_enabled() and pool_id:
            try:
                from app.services.pool_surface_mirror import mirror_pool_media_to_erome

                er = mirror_pool_media_to_erome(
                    db,
                    pool_id=int(pool_id),
                    media_ids=mids,
                    network_key=nk,
                )
                album_rec["erome"] = er
                if er.get("album_url"):
                    try:
                        from app.services.content_performance import record_surface_delivery_metric

                        record_surface_delivery_metric(
                            db,
                            parent=None,
                            surface="erome",
                            external_post_id=str(er["album_url"]),
                            export_source="cache_deposit",
                        )
                        db.commit()
                    except Exception:
                        logger.debug("erome surface metric skipped", exc_info=True)
            except Exception as e:
                album_rec["erome"] = {"ok": False, "error": str(e)[:200]}

        report_albums.append(album_rec)

    return {
        "ok": True,
        "network_key": nk,
        "album_size": size,
        "albums_built": len(report_albums),
        "albums": report_albums,
        "leftover_singles": max(0, len(rows) - sum(len(a["media_ids"]) for a in report_albums)),
    }


def compose_sent_cache_albums_sync(
    db: Session,
    *,
    network_key: str,
    media_ids: list[int],
    pool_id: int | None,
    moved_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from app.services.import_job_runner import _run_on_worker_loop
    from app.services.telegram_admin import run_telegram_import_io

    async def _go(storage):
        return await compose_sent_cache_albums_async(
            db,
            storage,
            network_key=network_key,
            media_ids=media_ids,
            pool_id=pool_id,
            moved_items=moved_items,
        )

    return _run_on_worker_loop(run_telegram_import_io(_go))


def notify_composer_bot(
    *,
    storage_thread_id: int,
    network_key: str,
    report: dict[str, Any],
) -> dict[str, Any]:
    """Post a summary into the Storage Hub deposit topic via Album Composer bot."""
    token = (os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "skipped": True, "reason": "no_bot_token"}

    from app.data.aof_storage_hub_map import category_emoji_for_network_key
    from app.services.storage_topic_deposit import storage_hub_chat_id_int

    nk = (network_key or "").strip().lower()
    emoji = category_emoji_for_network_key(nk)
    built = int(report.get("albums_built") or 0)
    leftover = int(report.get("leftover_singles") or 0)
    erome_ok = sum(1 for a in report.get("albums") or [] if (a.get("erome") or {}).get("ok"))
    main_ok = sum(1 for a in report.get("albums") or [] if (a.get("main_group") or {}).get("ok"))

    lines = [
        f"📦 SENT CACHE composer — {emoji} {nk}",
        f"Albums: {built} × {report.get('album_size', 5)} items",
    ]
    if leftover:
        lines.append(f"Leftover singles (need {report.get('album_size')} for next album): {leftover}")
    if main_ok:
        lines.append(f"Main group topics posted: {main_ok}")
    if erome_ok:
        lines.append(f"Erome uploads: {erome_ok}")
    for a in (report.get("albums") or [])[:6]:
        er = a.get("erome") or {}
        if er.get("album_url"):
            lines.append(f"• Album {a.get('index')}: {er['album_url']}")
    text = "\n".join(lines)

    import httpx

    chat_id = storage_hub_chat_id_int()
    payload = {
        "chat_id": chat_id,
        "message_thread_id": int(storage_thread_id),
        "text": text[:4000],
        "disable_web_page_preview": True,
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)
        body = r.json()
        return {"ok": bool(body.get("ok")), "telegram": body}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def enqueue_cache_composer_after_deposit(
    *,
    job_id: str,
    network_key: str,
    media_ids: list[int],
    pool_id: int | None,
    storage_thread_id: int | None,
    moved_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not composer_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}
    if not media_ids or not network_key:
        return {"ok": True, "skipped": True, "reason": "empty_batch"}

    from app.workers.sent_cache_composer_worker import compose_sent_cache_albums_task

    try:
        res = compose_sent_cache_albums_task.apply_async(
            kwargs={
                "job_id": job_id,
                "network_key": network_key,
                "media_ids": media_ids,
                "pool_id": pool_id,
                "storage_thread_id": storage_thread_id,
                "moved_items": moved_items,
            },
            countdown=max(0, int(os.getenv("TBCC_SENT_CACHE_COMPOSER_COUNTDOWN_S") or "8")),
        )
        return {"ok": True, "task_id": res.id}
    except Exception as e:
        logger.warning("cache composer enqueue failed: %s", e)
        return {"ok": False, "error": str(e)[:200]}
