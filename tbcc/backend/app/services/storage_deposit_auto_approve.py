"""Auto-approve Storage Hub pool imports for channel/group workflow seeding."""



from __future__ import annotations



import logging

import os

from typing import Any



from sqlalchemy.orm import Session



from app.data.aof_network import AOF_NETWORK_CHANNELS

from app.data.aof_storage_hub_map import STORAGE_HUB_IDENT



logger = logging.getLogger(__name__)



_TRUSTED_POOL_NAMES: frozenset[str] = frozenset(ch.pool_name for ch in AOF_NETWORK_CHANNELS)





def storage_deposit_auto_approve_enabled() -> bool:

    return (os.getenv("TBCC_STORAGE_DEPOSIT_AUTO_APPROVE") or "1").strip().lower() in (

        "1",

        "true",

        "yes",

        "on",

    )





def storage_deposit_auto_approve_requires_clip() -> bool:

    """

    When false (default), Storage Hub → pool imports approve immediately on ingest.

    When true, wait for CLIP niche tags from the enrich pipeline (legacy behavior).

    """

    return (os.getenv("TBCC_STORAGE_DEPOSIT_AUTO_APPROVE_REQUIRES_CLIP") or "0").strip().lower() in (

        "1",

        "true",

        "yes",

        "on",

    )





def is_storage_hub_source_label(source: str | None) -> bool:

    raw = (source or "").strip()

    if not raw:

        return False

    ident = STORAGE_HUB_IDENT.lstrip("-")

    return STORAGE_HUB_IDENT in raw or ident in raw





def is_trusted_aof_pool_name(pool_name: str | None) -> bool:

    return bool(pool_name and pool_name.strip() in _TRUSTED_POOL_NAMES)





def clip_tags_passed(enrich_out: dict[str, Any]) -> bool:

    """True when CLIP applied at least one niche tag or returned a confident primary label."""

    if int(enrich_out.get("clip_tags") or 0) > 0:

        return True

    if not enrich_out.get("clip"):

        return False

    if enrich_out.get("clip_confident"):

        return True

    return False





def maybe_auto_approve_storage_deposit_media(

    db: Session,

    media_id: int,

    enrich_out: dict[str, Any] | None = None,

) -> dict[str, Any]:

    """

    Approve pending media from Storage Hub → trusted AOF pool.



    Default: immediate on import (/deposit or channel scan) — no CLIP required.

    Set TBCC_STORAGE_DEPOSIT_AUTO_APPROVE_REQUIRES_CLIP=1 to gate on CLIP tags instead.

    """

    from app.models.content_pool import ContentPool

    from app.models.media import Media



    if not storage_deposit_auto_approve_enabled():

        return {"applied": False, "reason": "disabled"}



    out = enrich_out or {}

    if storage_deposit_auto_approve_requires_clip() and not clip_tags_passed(out):

        return {"applied": False, "reason": "clip_tags_missing", "media_id": media_id}



    m = db.query(Media).filter(Media.id == int(media_id)).first()

    if not m:

        return {"applied": False, "reason": "not_found", "media_id": media_id}

    if (m.status or "").lower() != "pending":

        return {"applied": False, "reason": "not_pending", "status": m.status, "media_id": media_id}

    if not is_storage_hub_source_label(m.source_channel):

        return {"applied": False, "reason": "not_storage_hub", "media_id": media_id}



    pool = db.query(ContentPool).filter(ContentPool.id == m.pool_id).first() if m.pool_id else None

    if not pool or not is_trusted_aof_pool_name(pool.name):

        return {

            "applied": False,

            "reason": "untrusted_pool",

            "pool_name": pool.name if pool else None,

            "media_id": media_id,

        }



    m.status = "approved"

    db.commit()

    mode = "clip" if storage_deposit_auto_approve_requires_clip() else "immediate"

    logger.info(

        "storage auto-approve media_id=%s pool=%s mode=%s clip_tags=%s",

        media_id,

        pool.name,

        mode,

        out.get("clip_tags"),

    )

    return {

        "applied": True,

        "media_id": media_id,

        "pool_id": int(pool.id),

        "pool_name": pool.name,

        "mode": mode,

        "clip_tags": out.get("clip_tags"),

    }


