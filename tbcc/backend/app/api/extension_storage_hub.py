"""Extension: list Storage Hub forum topics + post media into a chosen subtopic."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.data.aof_storage_hub_map import (
    AOF_STORAGE_TOPIC_MAP,
    STORAGE_HUB_IDENT,
    category_emoji_for_network_key,
    topic_deep_link,
)
from app.services.telegram_admin import friendly_telegram_error, run_telegram_import_io

logger = logging.getLogger(__name__)

router = APIRouter()

_SEND_MAX_BYTES = 80 * 1024 * 1024


def _short_topic_label(topic_title: str) -> str:
    s = (topic_title or "").strip()
    if s.upper().startswith("AOF "):
        s = s[4:].strip()
    for suffix in (" STORAGE", " Storage", " storage"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
            break
    return s or topic_title


def _topics_payload() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in AOF_STORAGE_TOPIC_MAP:
        if not row.network_key:
            continue
        emoji = category_emoji_for_network_key(row.network_key)
        short = _short_topic_label(row.topic_title)
        out.append(
            {
                "network_key": row.network_key,
                "message_thread_id": int(row.message_thread_id),
                "topic_title": row.topic_title,
                "short_label": short,
                "menu_label": f"{emoji} {short}".strip(),
                "topic_deep_link": topic_deep_link(row.message_thread_id),
            }
        )
    out.sort(key=lambda x: (x.get("short_label") or "", x.get("network_key") or ""))
    return out


@router.get("")
def list_storage_hub_topics() -> dict[str, Any]:
    """Static AOF Storage Hub forum topics for the extension context submenu."""
    return {
        "storage_hub_ident": STORAGE_HUB_IDENT,
        "topics": _topics_payload(),
    }


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


@router.post("/send")
async def send_media_to_storage_hub_topic(
    file: UploadFile = File(...),
    media_type: str = Form("photo"),
    message_thread_id: int = Form(...),
    caption: str = Form(""),
    skip_watermark: str = Form("false"),
    network_key: str = Form(""),
):
    """
    Post one image/video into Storage & Bot Hangar forum topic (message_thread_id).
    Extension cherry-pick path — does not import into a DB pool.
    """
    from app.data.aof_storage_hub_map import network_key_for_storage_topic
    from app.services.telegram_storage import TelegramStorage

    raw = await file.read()
    if not raw:
        return JSONResponse({"ok": False, "error": "empty body"}, status_code=400)
    if len(raw) > _SEND_MAX_BYTES:
        return JSONResponse(
            {
                "ok": False,
                "error": f"file too large ({len(raw)} bytes); max {_SEND_MAX_BYTES}",
            },
            status_code=413,
        )

    try:
        tid = int(message_thread_id)
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "invalid message_thread_id"}, status_code=400)
    if tid < 1:
        return JSONResponse({"ok": False, "error": "message_thread_id must be >= 1"}, status_code=400)

    known = {int(t["message_thread_id"]) for t in _topics_payload()}
    if tid not in known:
        return JSONResponse(
            {"ok": False, "error": f"unknown Storage Hub topic id {tid}"},
            status_code=400,
        )

    mt = (media_type or "photo").strip().lower()
    if mt not in ("photo", "video"):
        mt = "photo"
    skip_wm = _truthy(skip_watermark)
    cap = (caption or "").strip()
    key = (network_key or "").strip() or (network_key_for_storage_topic(tid) or "")

    async def _job(storage: TelegramStorage):
        return await storage.post_bytes_to_channel(
            STORAGE_HUB_IDENT,
            [(raw, mt)],
            tid,
            caption=cap or None,
            send_silent=False,
            skip_watermark=skip_wm,
        )

    try:
        result = await run_telegram_import_io(_job)
    except Exception as e:
        logger.warning("extension storage-hub send failed topic=%s: %s", tid, e, exc_info=True)
        return JSONResponse({"ok": False, "error": friendly_telegram_error(e)}, status_code=502)

    ok = bool(result.get("ok")) if isinstance(result, dict) else False
    return {
        "ok": ok,
        "storage_hub_ident": STORAGE_HUB_IDENT,
        "message_thread_id": tid,
        "network_key": key,
        "result": result if isinstance(result, dict) else {"raw": str(result)},
    }
