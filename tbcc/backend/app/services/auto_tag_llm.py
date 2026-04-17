"""
LLM vision auto-tagging: classify images against existing tbcc_tags (OpenAI vision API).

Skips video and non-image types for v1. Requires TBCC_OPENAI_API_KEY.
Tags are stored as MediaTagLink with source=\"llm\"; re-runs replace previous llm links only.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def auto_tag_llm_enabled() -> bool:
    return (os.getenv("TBCC_AUTO_TAG_ON_IMPORT") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    ) and bool((os.getenv("TBCC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip())


def _openai_key() -> str:
    return (os.getenv("TBCC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()


def _model() -> str:
    return (os.getenv("TBCC_LLM_MODEL") or "gpt-4o-mini").strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    data = json.loads(t)
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data


async def _fetch_jpeg_bytes_for_llm(media_id: int) -> tuple[bytes, str] | None:
    """Return JPEG bytes and media_type label, or None if skipped / unsupported."""
    from app.api.media import MediaFetchContext, _fetch_media_bytes_and_type, _image_bytes_to_thumbnail_jpeg
    from app.database.session import SessionLocal
    from app.models.media import Media

    db = SessionLocal()
    try:
        m = db.query(Media).filter(Media.id == media_id).first()
        if not m:
            return None
        mt = (m.media_type or "").lower()
        if mt == "video":
            logger.info("auto_tag_llm: skip video media_id=%s", media_id)
            return None
        if mt == "document":
            logger.info("auto_tag_llm: skip document media_id=%s", media_id)
            return None
        ctx = MediaFetchContext(
            id=int(m.id),
            source_channel=m.source_channel,
            telegram_message_id=m.telegram_message_id,
            media_type=m.media_type,
        )
    finally:
        db.close()

    data, mime = await _fetch_media_bytes_and_type(ctx)
    if not data or len(data) < 32:
        return None
    # Normalize to JPEG for vision API size limits
    jpeg = _image_bytes_to_thumbnail_jpeg(data, max_edge=min(1024, int(os.getenv("TBCC_AUTO_TAG_MAX_EDGE", "1024"))))
    if jpeg:
        return jpeg, mt or "photo"
    if mt in ("photo", "gif") or "image" in (mime or "").lower():
        return data[:4_000_000], mt or "photo"
    return None


def clear_llm_tags(db: Session, media_id: int) -> None:
    from app.models.tbcc_tag import MediaTagLink

    db.query(MediaTagLink).filter(
        MediaTagLink.media_id == media_id,
        MediaTagLink.source == "llm",
    ).delete(synchronize_session=False)
    db.flush()


def apply_llm_tag_ids(
    db: Session,
    media_id: int,
    tag_ids: list[int],
    confidence: float = 0.82,
) -> None:
    """Insert llm tag links; caller cleared previous llm links."""
    from app.models.tbcc_tag import MediaTagLink, TbccTag
    from app.services.media_tagging import rebuild_legacy_tags_string

    seen: set[int] = set()
    for tid in tag_ids:
        if tid in seen:
            continue
        seen.add(tid)
        tag = db.query(TbccTag).filter(TbccTag.id == tid).first()
        if not tag:
            continue
        existing = (
            db.query(MediaTagLink)
            .filter(MediaTagLink.media_id == media_id, MediaTagLink.tag_id == tid)
            .first()
        )
        if existing:
            if existing.source == "manual":
                continue
            existing.source = "llm"
            existing.confidence = confidence
        else:
            db.add(
                MediaTagLink(
                    media_id=media_id,
                    tag_id=tid,
                    confidence=confidence,
                    source="llm",
                )
            )
    rebuild_legacy_tags_string(db, media_id)
    db.commit()


def run_auto_tag_llm_for_media(media_id: int) -> dict[str, Any]:
    """
    Synchronous entry: fetch image, call OpenAI vision, apply tags.
    Returns { ok, error?, tag_ids?, skipped? }.
    """
    from app.database.session import SessionLocal
    from app.models.media import Media
    from app.models.tbcc_tag import TbccTag

    key = _openai_key()
    if not key:
        return {"ok": False, "error": "TBCC_OPENAI_API_KEY not set", "media_id": media_id}

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        fetched = loop.run_until_complete(_fetch_jpeg_bytes_for_llm(media_id))
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    if not fetched:
        return {"ok": True, "skipped": True, "reason": "no_image_or_video", "media_id": media_id}

    jpeg_bytes, mt_label = fetched
    b64 = base64.standard_b64encode(jpeg_bytes).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"

    db = SessionLocal()
    try:
        rows = db.query(TbccTag).order_by(TbccTag.slug.asc()).all()
        if not rows:
            return {"ok": False, "error": "No tags in database — add tags under /tags first", "media_id": media_id}
        tag_catalog = [{"id": t.id, "slug": t.slug, "name": t.name, "category": t.category} for t in rows]
        allowed_ids = {int(t["id"]) for t in tag_catalog if t.get("id") is not None}
        catalog_json = json.dumps(
            [{"id": t["id"], "slug": t["slug"], "name": t["name"], "category": t.get("category")} for t in tag_catalog],
            ensure_ascii=False,
        )
    finally:
        db.close()

    user_text = (
        f"You are tagging media for a creator content library. Media type hint: {mt_label}.\n"
        "Return a single JSON object with exactly these keys:\n"
        '- "tag_ids": array of integer ids from the allowed list only (0–12 items). '
        "Use [] if nothing fits.\n"
        '- "nsfw_tier": one of "sfw", "suggestive", "explicit", "unknown" '
        "(how intense adult/sexual content is in the image).\n"
        '- "facets": optional array of up to 8 short strings (themes, setting, style).\n'
        '- "routing_hint": optional short string (which channel line or brand this might belong to).\n\n'
        f"Allowed tags (id, slug, name, category):\n{catalog_json}"
    )

    payload = {
        "model": _model(),
        "temperature": 0.35,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                ],
            }
        ],
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.text[:500]
        except Exception:
            pass
        logger.warning("OpenAI vision HTTP error: %s %s", e.response.status_code, detail)
        return {"ok": False, "error": f"OpenAI HTTP {e.response.status_code}", "media_id": media_id}
    except Exception as e:
        logger.exception("OpenAI vision failed media_id=%s", media_id)
        return {"ok": False, "error": str(e), "media_id": media_id}

    try:
        content = body["choices"][0]["message"]["content"]
        parsed = _parse_json_object(content)
    except (KeyError, IndexError, json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("bad OpenAI vision response media_id=%s: %s", media_id, e)
        return {"ok": False, "error": "Could not parse model response", "media_id": media_id}

    raw_ids = parsed.get("tag_ids")
    tag_ids: list[int] = []
    if isinstance(raw_ids, list):
        for x in raw_ids:
            try:
                i = int(x)
                if i in allowed_ids and i not in tag_ids:
                    tag_ids.append(i)
            except (TypeError, ValueError):
                continue
    tag_ids = tag_ids[:16]

    db = SessionLocal()
    try:
        clear_llm_tags(db, media_id)
        if tag_ids:
            apply_llm_tag_ids(db, media_id, tag_ids)
        else:
            from app.services.media_tagging import rebuild_legacy_tags_string

            rebuild_legacy_tags_string(db, media_id)
            db.commit()
    finally:
        db.close()

    from app.models.media import Media
    from app.services.media_pool_routing import normalize_nsfw_tier, try_assign_pool_from_tags

    extras: dict[str, Any] = {}
    facets_raw = parsed.get("facets")
    if isinstance(facets_raw, list):
        extras["facets"] = [
            str(x).strip() for x in facets_raw[:8] if x is not None and str(x).strip()
        ][:8]
    rh_raw = parsed.get("routing_hint")
    if isinstance(rh_raw, str) and rh_raw.strip():
        extras["routing_hint"] = rh_raw.strip()[:512]
    nt = normalize_nsfw_tier(parsed.get("nsfw_tier") if isinstance(parsed.get("nsfw_tier"), str) else None)
    if nt is None:
        nt = "unknown"

    route_out: dict[str, Any] = {}
    db2 = SessionLocal()
    try:
        m = db2.query(Media).filter(Media.id == media_id).first()
        if m:
            m.nsfw_tier = nt
            if extras:
                m.classification_json = json.dumps(extras, ensure_ascii=False)
            else:
                m.classification_json = None
            route_out = try_assign_pool_from_tags(db2, media_id)
            db2.commit()
    finally:
        db2.close()

    out: dict[str, Any] = {
        "ok": True,
        "media_id": media_id,
        "tag_ids": tag_ids,
        "model": _model(),
        "nsfw_tier": nt,
        "route": route_out,
    }
    return out


def enqueue_auto_tag_llm_if_enabled(media_id: int) -> None:
    """Fire-and-forget Celery task when TBCC_AUTO_TAG_ON_IMPORT is enabled."""
    if not auto_tag_llm_enabled():
        return
    try:
        from app.workers.media_auto_tag_worker import auto_tag_media_llm

        auto_tag_media_llm.delay(media_id)
    except Exception:
        logger.warning("enqueue auto_tag_llm failed (Celery down?) media_id=%s", media_id, exc_info=True)
