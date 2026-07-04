"""Ornamental divider image sent after main-group posts (view count / timestamp between drops)."""

from __future__ import annotations

import json
import logging
import os
import random
from typing import Any

from sqlalchemy.orm import Session
from telethon import TelegramClient

from app.data.aof_network import MAIN_GROUP_IDENT
from app.models.main_channel_divider_settings import MainChannelDividerSettings
from app.services.post_divider_storage import post_divider_image_path, save_post_divider_image
from app.utils.telegram_peer import normalize_telethon_peer_identifier

logger = logging.getLogger(__name__)

ROW_ID = 1
MAX_IMAGES = 24


def _public_base_url() -> str:
    return (
        (os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_API_URL") or "").strip()
        or "http://127.0.0.1:8000"
    ).rstrip("/")


def _parse_images(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id") or "").strip()
        fn = str(item.get("filename") or "").strip()
        if not iid or not fn:
            continue
        if not post_divider_image_path(fn):
            continue
        out.append(
            {
                "id": iid,
                "filename": fn,
                "label": str(item.get("label") or "").strip()[:64],
            }
        )
    return out[:MAX_IMAGES]


def _serialize_images(images: list[dict[str, Any]]) -> str:
    slim = [{"id": i["id"], "filename": i["filename"], "label": i.get("label") or ""} for i in images[:MAX_IMAGES]]
    return json.dumps(slim)


def _ensure_row(db: Session) -> MainChannelDividerSettings:
    r = db.query(MainChannelDividerSettings).filter(MainChannelDividerSettings.id == ROW_ID).first()
    if r:
        return r
    r = MainChannelDividerSettings(
        id=ROW_ID,
        enabled=False,
        rotate_images=True,
        apply_in_topics=False,
        images_json="[]",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def get_main_channel_divider_public(db: Session) -> dict[str, Any]:
    row = _ensure_row(db)
    base = _public_base_url()
    images_in = _parse_images(row.images_json)
    images: list[dict[str, Any]] = []
    for img in images_in:
        fn = img["filename"]
        images.append(
            {
                "id": img["id"],
                "filename": fn,
                "label": img.get("label") or "",
                "url": f"{base}/static/post-dividers/{fn}",
            }
        )
    active = next((i for i in images if i["id"] == row.active_image_id), None)
    if active is None and images:
        active = images[0]
    return {
        "enabled": bool(row.enabled),
        "rotate_images": bool(row.rotate_images),
        "apply_in_topics": bool(row.apply_in_topics),
        "active_image_id": row.active_image_id,
        "active_image": active,
        "images": images,
        "main_group_identifier": MAIN_GROUP_IDENT,
    }


def pick_divider_image_meta(db: Session) -> dict[str, Any] | None:
    row = _ensure_row(db)
    if not row.enabled:
        return None
    images = _parse_images(row.images_json)
    if not images:
        return None
    if row.rotate_images and len(images) > 1:
        return random.choice(images)
    aid = (row.active_image_id or "").strip()
    if aid:
        hit = next((i for i in images if i["id"] == aid), None)
        if hit:
            return hit
    return images[0]


def load_divider_bytes(db: Session) -> tuple[bytes, str] | None:
    meta = pick_divider_image_meta(db)
    if not meta:
        return None
    path = post_divider_image_path(meta["filename"])
    if not path:
        return None
    data = path.read_bytes()
    if not data:
        return None
    return data, "photo"


def divider_applies_to_send(
    channel_identifier: str | int,
    *,
    message_thread_id: int | None,
    db: Session,
) -> bool:
    row = _ensure_row(db)
    if not row.enabled:
        return False
    ident = normalize_telethon_peer_identifier(channel_identifier)
    if ident != normalize_telethon_peer_identifier(MAIN_GROUP_IDENT):
        return False
    if message_thread_id and not row.apply_in_topics:
        return False
    return True


async def maybe_send_main_channel_post_divider(
    client: TelegramClient,
    channel_peer: str | int,
    db: Session,
    *,
    channel_identifier: str | int | None = None,
    message_thread_id: int | None = None,
    send_silent: bool = True,
) -> bool:
    """
    Send a standalone divider image after a content post.
    Telegram shows views + timestamp on that spacer message (native channel chrome).
    """
    ident = channel_identifier if channel_identifier is not None else channel_peer
    if not divider_applies_to_send(ident, message_thread_id=message_thread_id, db=db):
        return False
    item = load_divider_bytes(db)
    if not item:
        logger.info("main channel divider enabled but no image configured")
        return False
    data, hint = item
    try:
        from app.services.telegram_storage import TelegramStorage

        storage = TelegramStorage(client)
        f, kwargs, _bucket = storage._prepare_file_for_send(data, hint, skip_watermark=True)
        send_kw: dict = {"silent": bool(send_silent), **kwargs}
        if message_thread_id:
            send_kw["reply_to"] = int(message_thread_id)
        await client.send_file(channel_peer, f, **send_kw)
        logger.info(
            "main channel post divider sent peer=%s thread=%s",
            ident,
            message_thread_id,
        )
        return True
    except Exception:
        logger.exception("main channel post divider send failed peer=%s", ident)
        return False
