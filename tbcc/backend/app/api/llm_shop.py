"""LLM helpers for dashboard shop (product copy + tags from existing pool)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.models.tbcc_tag import TbccTag
from app.services.llm_shop_suggest import suggest_media_tags_and_caption, suggest_shop_product_copy

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status")
def llm_shop_status():
    from app.services.llm_shop_suggest import current_model, openai_configured

    return {
        "openai_configured": openai_configured(),
        "model": current_model(),
    }


@router.post("/suggest-shop-product")
def suggest_shop_product(data: dict = Body(...), db: Session = Depends(get_db)):
    """
    Suggest description, description variants, and tag ids using only tags from GET /tags.

    Env: TBCC_OPENAI_API_KEY or OPENAI_API_KEY, optional TBCC_LLM_MODEL (default gpt-4o-mini).
    """
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    product_type = (data.get("product_type") or "bundle").strip().lower()
    if product_type not in ("subscription", "bundle"):
        product_type = "bundle"

    description = (data.get("description") or "").strip() or None
    brand_voice_hint = (data.get("brand_voice_hint") or "").strip() or None

    rows = db.query(TbccTag).order_by(TbccTag.slug.asc()).all()
    tag_catalog = [{"id": t.id, "slug": t.slug, "name": t.name, "category": t.category} for t in rows]
    if not tag_catalog:
        raise HTTPException(
            status_code=400,
            detail="No tags in the database yet. Create tags (Dashboard → tags / media tagging) before AI can assign them.",
        )

    try:
        out = suggest_shop_product_copy(
            name=name,
            description=description,
            product_type=product_type,
            tag_catalog=tag_catalog,
            brand_voice_hint=brand_voice_hint,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("suggest_shop_product failed")
        raise HTTPException(status_code=500, detail=f"AI suggestion failed: {e!s}") from e

    return out


@router.post("/suggest-media-caption")
def suggest_media_caption(data: dict = Body(...), db: Session = Depends(get_db)):
    """
    Step 2: suggest tags (from catalog) + caption from text-only media context. Human reviews before apply.

    Body: { "media_id": int, "brand_voice_hint": optional str }
    """
    try:
        media_id = int(data.get("media_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="media_id is required (integer)")

    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    pool_name = None
    if media.pool_id:
        pool = db.query(ContentPool).filter(ContentPool.id == media.pool_id).first()
        if pool:
            pool_name = pool.name

    rows = db.query(TbccTag).order_by(TbccTag.slug.asc()).all()
    tag_catalog = [{"id": t.id, "slug": t.slug, "name": t.name, "category": t.category} for t in rows]
    if not tag_catalog:
        raise HTTPException(
            status_code=400,
            detail="No tags in the database yet. Create tags before AI can assign them.",
        )

    brand_voice_hint = (data.get("brand_voice_hint") or "").strip() or None

    try:
        out = suggest_media_tags_and_caption(
            media_id=media_id,
            media_type=media.media_type,
            existing_tags=media.tags,
            pool_name=pool_name,
            source_channel=media.source_channel,
            tag_catalog=tag_catalog,
            brand_voice_hint=brand_voice_hint,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("suggest_media_caption failed")
        raise HTTPException(status_code=500, detail=f"AI suggestion failed: {e!s}") from e

    return out
