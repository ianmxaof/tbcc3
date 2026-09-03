"""AOF keyword search — find media by tag/emoji/lane and DM an album."""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.request import HTTPXRequest

from app.database.session import SessionLocal, get_db
from app.services.aof_content_search import aof_content_search_enabled, search_approved_media
from app.services.aof_search_access import (
    album_size_for_tier,
    consume_search_quota,
    evaluate_search_access,
    resolve_search_tier,
)
from app.services.aof_search_deliver import build_search_result_caption, send_aof_search_album
from app.services.loot_bot_settings_effective import get_effective_loot_bot_settings, resolve_bot_token_raw

logger = logging.getLogger(__name__)

router = APIRouter()


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


class AofSearchFindBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    telegram_user_id: int = Field(..., ge=1)
    surface: str | None = None


@router.get("/status")
def aof_search_status(
    telegram_user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    access = evaluate_search_access(db, telegram_user_id)
    return {
        "ok": True,
        "enabled": aof_content_search_enabled(),
        **access,
    }


@router.post("/preview")
def aof_search_preview(
    body: AofSearchFindBody,
    db: Session = Depends(get_db),
):
    """Dry-run search — no DM delivery, no quota consumption (macro-search routing)."""
    if not aof_content_search_enabled():
        raise HTTPException(status_code=503, detail="AOF search disabled")

    uid = int(body.telegram_user_id)
    access = evaluate_search_access(db, uid, surface=body.surface)
    allowed = access.get("allowed_surfaces") or ["loot_room"]
    if access.get("surface"):
        surface = access["surface"]
    elif body.surface and body.surface.strip().lower() in allowed:
        surface = body.surface.strip().lower()
    else:
        surface = allowed[0]

    tier = resolve_search_tier(db, uid)
    limit = album_size_for_tier(tier)
    result = search_approved_media(
        db,
        body.query,
        surface=surface,  # type: ignore[arg-type]
        limit=limit,
    )
    items = result.get("items") or []
    return {
        "ok": True,
        "has_matches": bool(items),
        "match_count": len(items),
        "access": access,
        "surface": surface,
        "result": result,
    }


@router.post("/find")
def aof_search_find(
    body: AofSearchFindBody,
    db: Session = Depends(get_db),
):
    """
  Keyword / emoji search → DM album via @aof_lootgod_bot.

  Surfaces: loot_room (default), library (loot key+), vip (VIP+).
  """
    if not aof_content_search_enabled():
        raise HTTPException(status_code=503, detail="AOF search disabled")

    uid = int(body.telegram_user_id)
    access = evaluate_search_access(db, uid, surface=body.surface)
    if not access.get("can_search"):
        if access.get("surface") is None:
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "surface_forbidden",
                    "message": "Upgrade to Loot Room key or AOF VIP for library/VIP search.",
                    "allowed_surfaces": access.get("allowed_surfaces"),
                },
            )
        raise HTTPException(
            status_code=403,
            detail={
                "reason": "daily_limit",
                "message": "Daily search limit reached.",
                "searches_used_today": access.get("searches_used_today"),
                "daily_limit": access.get("daily_limit"),
            },
        )

    tier = resolve_search_tier(db, uid)
    limit = album_size_for_tier(tier)
    surface = access["surface"]
    result = search_approved_media(
        db,
        body.query,
        surface=surface,
        limit=limit,
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "reason": result.get("reason") or "no_matches",
            "access": access,
            "result": result,
            "delivery": {"albums_sent": 0, "media_sent": 0},
        }

    token = resolve_bot_token_raw(db)
    if not token:
        raise HTTPException(status_code=400, detail="Loot bot token not configured")
    eff = get_effective_loot_bot_settings(db)
    spoiler = bool(eff.get("drop_spoiler_default", True))
    bot = Bot(
        token=token,
        request=HTTPXRequest(connect_timeout=30.0, read_timeout=180.0, write_timeout=180.0),
    )

    media_ids = [int(x["id"]) for x in (result.get("items") or []) if x.get("id")]
    from app.models.media import Media

    rows = db.query(Media).filter(Media.id.in_(media_ids)).all()
    by_id = {int(m.id): m for m in rows}
    ordered = [by_id[mid] for mid in media_ids if mid in by_id]
    caption = build_search_result_caption(result, query=body.query)

    async def _run():
        worker_db = SessionLocal()
        try:
            return await send_aof_search_album(
                worker_db,
                bot=bot,
                chat_id=uid,
                media_rows=ordered,
                caption_html=caption,
                spoiler_default=spoiler,
            )
        finally:
            worker_db.close()

    delivery = _run_async(_run())
    if int(delivery.get("media_sent") or 0) <= 0:
        return {
            "ok": False,
            "reason": "delivery_failed",
            "access": access,
            "result": result,
            "delivery": delivery,
        }

    quota = consume_search_quota(uid, limit=int(access.get("daily_limit") or 3))
    return {
        "ok": True,
        "sent_to": uid,
        "access": access,
        "quota": quota,
        "result": result,
        "delivery": delivery,
    }
