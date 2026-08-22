"""
Import-time enrichment: Lustpress metadata tags, NSFW classifier, conservative LLM fallback.

Runs async via Celery after Media row is created (replaces direct LLM enqueue).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def enrich_pipeline_enabled() -> bool:
    """
    Heavy import enrich (NSFW/CLIP/Lustpress Celery jobs + Telethon downloads).

    TBCC_ENRICH_ON_IMPORT=0 — kill switch (recommended for /deposit).
    TBCC_ENRICH_ON_IMPORT=1 — force on even without sidecar URLs.
    When unset: only sidecar URLs (NSFW/CLIP/Lustpress) enable enrich — NOT
    TBCC_AUTO_TAG_ON_IMPORT alone (LLM vision uses enqueue_auto_tag_llm_if_enabled).
    """
    raw = (os.getenv("TBCC_ENRICH_ON_IMPORT") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    from app.services.clip_classifier import clip_classifier_enabled
    from app.services.lustpress_metadata import lustpress_enabled
    from app.services.nsfw_classifier import nsfw_classifier_enabled

    return lustpress_enabled() or nsfw_classifier_enabled() or clip_classifier_enabled()


def llm_fallback_enabled() -> bool:
    """When ON_IMPORT is set, LLM runs only if fallback mode is on (default) and heuristics say so."""
    if (os.getenv("TBCC_AUTO_TAG_LLM_ALWAYS") or "").strip().lower() in ("1", "true", "yes"):
        return True
    if (os.getenv("TBCC_AUTO_TAG_LLM_FALLBACK") or "").strip().lower() in ("0", "false", "no"):
        return False
    return (os.getenv("TBCC_AUTO_TAG_ON_IMPORT") or "").strip().lower() in ("1", "true", "yes")


def vision_auto_route_lanes() -> set[str]:
    """Comma-separated lane allowlist for hands-off vision auto-route. Unset/empty = disabled.

    Deliberately opt-in and narrow — only lanes with real validated ground-truth
    accuracy belong here. Everything else still lands as a MediaLaneVisionDecision
    suggestion for the Q&A panel, it just doesn't self-move into the lane subtopic.
    """
    raw = os.getenv("TBCC_VISION_AUTO_ROUTE_LANES") or ""
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _maybe_auto_route_vision_lane(media_id: int, vision_decision: dict[str, Any] | None) -> None:
    if not vision_decision:
        return
    lane_key = vision_decision.get("lane_key")
    if not lane_key:
        return
    allowlist = vision_auto_route_lanes()
    if not allowlist or lane_key not in allowlist:
        return
    try:
        from app.services.gatekeeper_review import enqueue_lane_route_for_media

        result = enqueue_lane_route_for_media(media_id, [lane_key])
        if not result.get("ok"):
            logger.error(
                "vision auto-route enqueue FAILED media_id=%s lane=%s reason=%s",
                media_id,
                lane_key,
                result.get("reason"),
            )
    except Exception:
        logger.warning("vision auto-route skipped media_id=%s lane=%s", media_id, lane_key, exc_info=True)


def _is_http_source(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return None


def _apply_metadata_tags(db: Session, media_id: int, slug_name_pairs: list[tuple[str, str, str | None]]) -> int:
    from app.models.tbcc_tag import MediaTagLink
    from app.services.media_tagging import ensure_tag, rebuild_legacy_tags_string

    applied = 0
    for slug, name, category in slug_name_pairs:
        tag = ensure_tag(db, slug, name, category)
        existing = (
            db.query(MediaTagLink)
            .filter(MediaTagLink.media_id == media_id, MediaTagLink.tag_id == tag.id)
            .first()
        )
        if existing:
            if existing.source == "manual":
                continue
            existing.source = "metadata"
            existing.confidence = 0.78
        else:
            db.add(
                MediaTagLink(
                    media_id=media_id,
                    tag_id=tag.id,
                    confidence=0.78,
                    source="metadata",
                )
            )
        applied += 1
    if applied:
        rebuild_legacy_tags_string(db, media_id)
        db.commit()
    return applied


def _count_non_rule_tags(db: Session, media_id: int) -> int:
    from app.models.tbcc_tag import MediaTagLink

    return (
        db.query(MediaTagLink)
        .filter(
            MediaTagLink.media_id == media_id,
            MediaTagLink.source.in_(("metadata", "llm", "manual")),
        )
        .count()
    )


def _should_enqueue_llm(
    *,
    nsfw_tier: str,
    nsfw_confident: bool,
    top_class: str,
    metadata_tag_count: int,
    topic_tag_count: int,
    media_type: str,
    clip_confident: bool = False,
    clip_tag_count: int = 0,
) -> bool:
    from app.services.auto_tag_llm import auto_tag_llm_enabled

    if not auto_tag_llm_enabled():
        return False
    if clip_confident and clip_tag_count >= 1:
        return False
    if not llm_fallback_enabled():
        return True
    mt = (media_type or "").lower()
    if mt == "document":
        return False
    # Ambiguous classifier (sexy/neutral borderline) → vision
    if not nsfw_confident or top_class in ("sexy", "neutral", "drawings"):
        if top_class == "sexy" or (not nsfw_confident and nsfw_tier == "unknown"):
            return True
    if topic_tag_count < 2 and metadata_tag_count < 1:
        return True
    if nsfw_tier == "unknown" and mt in ("photo", "video", "gif"):
        return True
    return False


async def _fetch_image_bytes_for_classify(media_id: int) -> bytes | None:
    import json
    from pathlib import Path

    from app.api.media import MediaFetchContext, _fetch_media_bytes_and_type, _image_bytes_to_thumbnail_jpeg
    from app.database.session import SessionLocal
    from app.models.media import Media
    from app.services.import_pipeline import classify_use_staged_bytes
    from app.services.media_frame_sample import extract_video_frame_jpeg

    db = SessionLocal()
    try:
        m = db.query(Media).filter(Media.id == media_id).first()
        if not m:
            return None
        mt = (m.media_type or "").lower()
        if classify_use_staged_bytes() and m.classification_json:
            try:
                meta = json.loads(m.classification_json)
                if isinstance(meta, dict):
                    poster = meta.get("import_poster_path")
                    if poster:
                        p = Path(str(poster))
                        if p.is_file():
                            return p.read_bytes()
            except Exception:
                pass
        ctx = MediaFetchContext(
            id=int(m.id),
            source_channel=m.source_channel,
            telegram_message_id=m.telegram_message_id,
            media_type=m.media_type,
        )
    finally:
        db.close()

    data, mime = await _fetch_media_bytes_and_type(ctx)
    if not data:
        return None
    if mt == "video":
        frame = extract_video_frame_jpeg(data)
        return frame
    jpeg = _image_bytes_to_thumbnail_jpeg(data, max_edge=768)
    if jpeg:
        return jpeg
    if mt in ("photo", "gif") or "image" in (mime or "").lower():
        return data[:4_000_000]
    return None


def _fetch_classify_bytes_sync(media_id: int) -> bytes | None:
    """Run classify download on the Celery worker loop (import session, no per-call loop teardown)."""
    from app.services.import_job_runner import _run_on_worker_loop

    return _run_on_worker_loop(_fetch_image_bytes_for_classify(media_id))


def run_auto_tag_enrich_for_media(media_id: int) -> dict[str, Any]:
    """Sync Celery entry: lustpress → nsfw → optional LLM enqueue."""
    if not enrich_pipeline_enabled():
        return {"ok": True, "media_id": media_id, "skipped": "enrich_disabled"}

    try:
        from app.services.focus_profile import pause_auto_tag_work, skip_sidecar_enrich

        if pause_auto_tag_work():
            return {"ok": True, "media_id": media_id, "skipped": "focus_pause_auto_tag"}
    except Exception:
        pass

    from app.database.session import SessionLocal
    from app.models.media import Media
    from app.services.lustpress_metadata import fetch_metadata_for_url, lustpress_enabled, metadata_to_tag_slugs
    from app.services.media_niche_classify import classify_image_bytes_niche
    from app.services.media_pool_routing import try_assign_pool_from_tags
    from app.services.nsfw_classifier import classify_image_bytes, classify_image_url, nsfw_classifier_enabled

    out: dict[str, Any] = {
        "ok": True,
        "media_id": media_id,
        "lustpress": False,
        "nsfw": False,
        "clip": False,
        "llm_enqueued": False,
    }
    db = SessionLocal()
    try:
        m = db.query(Media).filter(Media.id == media_id).first()
        if not m:
            return {"ok": False, "error": "not_found", "media_id": media_id}
        source_url = _is_http_source(m.source_channel)
        metadata_applied = 0

        if source_url and lustpress_enabled():
            meta = fetch_metadata_for_url(source_url)
            if meta and (meta.tag_names or meta.category_names or meta.title):
                pairs = metadata_to_tag_slugs(meta)
                metadata_applied = _apply_metadata_tags(db, media_id, pairs)
                out["lustpress"] = True
                out["metadata_tags"] = metadata_applied
                extras: dict[str, Any] = {}
                try:
                    raw_cj = m.classification_json
                    if raw_cj:
                        existing = json.loads(raw_cj)
                        if isinstance(existing, dict):
                            extras = existing
                except Exception:
                    pass
                extras["lustpress"] = {
                    "platform": meta.platform,
                    "title": meta.title[:256] if meta.title else "",
                }
                m.classification_json = json.dumps(extras, ensure_ascii=False)
                db.commit()

        nsfw_tier = (m.nsfw_tier or "unknown").lower()
        nsfw_confident = False
        top_class = ""
        mt = (m.media_type or "").lower()
        img_bytes: bytes | None = None

        _skip_sidecar = False
        try:
            from app.services.focus_profile import skip_sidecar_enrich

            _skip_sidecar = skip_sidecar_enrich()
        except Exception:
            pass

        if nsfw_classifier_enabled() and not _skip_sidecar:
            classify_url = source_url
            if mt == "video" or (
                classify_url and not classify_url.lower().split("?", 1)[0].endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
            ):
                img_bytes = _fetch_classify_bytes_sync(media_id)
            if img_bytes:
                res = classify_image_bytes(img_bytes)
            elif classify_url and mt in ("photo", "gif", ""):
                res = classify_image_url(classify_url)
            else:
                res = None
            if res and res.nsfw_tier in ("sfw", "suggestive", "explicit", "unknown"):
                m.nsfw_tier = res.nsfw_tier
                nsfw_tier = res.nsfw_tier
                nsfw_confident = res.confident
                top_class = res.top_class
                out["nsfw"] = True
                out["nsfw_tier"] = res.nsfw_tier
                out["nsfw_confident"] = res.confident
                if top_class:
                    try:
                        raw_cj = m.classification_json
                        extras = json.loads(raw_cj) if raw_cj else {}
                        if not isinstance(extras, dict):
                            extras = {}
                    except Exception:
                        extras = {}
                    extras["nsfw_classify"] = {
                        "top_class": top_class,
                        "top_probability": res.top_probability,
                        "confident": res.confident,
                    }
                    m.classification_json = json.dumps(extras, ensure_ascii=False)
                db.commit()

        clip_confident = False
        clip_tag_count = 0
        img_for_clip = img_bytes
        if not img_for_clip and mt in ("photo", "gif", ""):
            img_for_clip = _fetch_classify_bytes_sync(media_id)
        if img_for_clip and not _skip_sidecar:
            from app.services.clip_classifier import clip_classifier_enabled

            if clip_classifier_enabled():
                niche = classify_image_bytes_niche(img_for_clip)
                if niche:
                    out["clip"] = True
                    clip_meta = niche.get("clip") or {}
                    clip_confident = bool(clip_meta.get("confident"))
                    slug_pairs: list[tuple[str, str, str | None]] = []
                    for slug in niche.get("labels") or []:
                        s = str(slug).strip()
                        if s:
                            slug_pairs.append((s, s.replace("-", " ").title(), "topic"))
                    if slug_pairs:
                        clip_tag_count = _apply_metadata_tags(db, media_id, slug_pairs)
                        out["clip_tags"] = clip_tag_count
                    out["clip_confident"] = clip_confident
                    out["clip_slug"] = clip_meta.get("top_slug") or None
                    # Real per-slug scores for the gatekeeper inbox-split lane mapper —
                    # never a bare slug list, per the locked design's auto-route rule.
                    out["clip_labels"] = [
                        {"slug": row.get("slug"), "score": row.get("score")}
                        for row in (clip_meta.get("labels") or [])
                        if isinstance(row, dict) and row.get("slug")
                    ]
                    # Raw embedding for the gatekeeper prototype bank (record_label /
                    # inbox-split blending) — separate sidecar call from classify above.
                    try:
                        from app.services.clip_classifier import embed_image_bytes

                        embed_res = embed_image_bytes(img_for_clip)
                        if embed_res.ok and embed_res.embedding:
                            out["clip_embedding"] = embed_res.embedding
                    except Exception:
                        logger.debug("clip embed skipped media_id=%s", media_id, exc_info=True)
                    try:
                        raw_cj = m.classification_json
                        extras = json.loads(raw_cj) if raw_cj else {}
                        if not isinstance(extras, dict):
                            extras = {}
                    except Exception:
                        extras = {}
                    extras["niche_classify"] = niche
                    m.classification_json = json.dumps(extras, ensure_ascii=False)
                    db.commit()

        if img_for_clip:
            from app.services.media_lane_vision_classify import classify_and_log_lane_vision

            vision_decision = classify_and_log_lane_vision(db, media_id, img_for_clip)
            _maybe_auto_route_vision_lane(media_id, vision_decision)

        route = try_assign_pool_from_tags(db, media_id)
        if route.get("applied"):
            db.commit()
        out["route"] = route

        from app.services.media_gatekeeper import (
            apply_gatekeeper_after_ingest,
            should_attempt_storage_auto_approve,
        )
        from app.services.storage_deposit_auto_approve import maybe_auto_approve_storage_deposit_media

        apply_gatekeeper_after_ingest(db, media_id, enrich=out)
        if should_attempt_storage_auto_approve(db, media_id):
            out["auto_approve"] = maybe_auto_approve_storage_deposit_media(db, media_id, out)
        else:
            out["auto_approve"] = {"applied": False, "reason": "gatekeeper_or_scrape_skip"}

        topic_count = _count_non_rule_tags(db, media_id)
        if _should_enqueue_llm(
            nsfw_tier=nsfw_tier,
            nsfw_confident=nsfw_confident,
            top_class=top_class,
            metadata_tag_count=metadata_applied,
            topic_tag_count=topic_count,
            media_type=m.media_type or "",
            clip_confident=clip_confident,
            clip_tag_count=clip_tag_count,
        ):
            from app.services.auto_tag_llm import enqueue_auto_tag_llm_if_enabled

            enqueue_auto_tag_llm_if_enabled(media_id)
            out["llm_enqueued"] = True
    except Exception as e:
        if "database is locked" in str(e).lower():
            try:
                from app.services.focus_profile import record_session_stress_event

                record_session_stress_event("auto_tag_enrich")
            except Exception:
                pass
        logger.exception("auto_tag_enrich failed media_id=%s", media_id)
        return {"ok": False, "error": str(e), "media_id": media_id}
    finally:
        db.close()
    return out


def enqueue_auto_tag_enrich_if_enabled(media_id: int) -> None:
    try:
        from app.services.focus_profile import pause_auto_tag_work

        if pause_auto_tag_work():
            logger.debug("skip auto_tag_enrich enqueue media_id=%s (focus profile)", media_id)
            return
    except Exception:
        pass
    if not enrich_pipeline_enabled():
        return
    try:
        from app.workers.media_auto_tag_worker import auto_tag_media_enrich

        auto_tag_media_enrich.delay(media_id)
    except Exception:
        logger.warning("enqueue auto_tag_enrich failed (Celery down?) media_id=%s", media_id, exc_info=True)
        try:
            run_auto_tag_enrich_for_media(media_id)
        except Exception:
            logger.exception("sync auto_tag_enrich failed media_id=%s", media_id)
