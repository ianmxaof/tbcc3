"""
Import-time enrichment: Lustpress metadata tags, NSFW classifier, conservative LLM fallback.

Runs async via Celery after Media row is created (replaces direct LLM enqueue).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy.exc import IntegrityError
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


# Routing tiers, most specific first. The classifier is told to tag big_tits/ass
# "whenever genuinely prominent", so they co-occur with the real subject on most
# nudes; a busty milf must land in MILF, not BIG TITS.
#
# Crucially this is *tiers*, not a flat ranking: big_tits and ass are peers, and
# so are the subject lanes. Within a tier the classifier's own ranking decides.
# Flattening it was a real bug — it demoted `ass` under `big_tits`, so a rear-view
# nude the model correctly ranked ["ass", "big_tits"] routed to BIG TITS.
_LANE_ROUTE_TIERS: tuple[tuple[str, ...], ...] = (
    ("taboo", "voyeur", "abg", "ai", "goon", "milf", "blowjob", "bop"),
    ("big_tits", "ass"),
    ("full_length",),
)


def vision_auto_route_lanes() -> set[str]:
    """Lane allowlist for hands-off auto-route. Unset/empty = disabled, ``all`` = every lane.

    Lanes off the list still get a MediaLaneVisionDecision suggestion for the Q&A
    panel, they just don't self-move into the lane subtopic. With ``all``, the
    priority table below is what keeps co-category hits (big_tits/ass) from
    stealing media that belongs in a more specific lane.
    """
    raw = os.getenv("TBCC_VISION_AUTO_ROUTE_LANES") or ""
    parts = {p.strip().lower() for p in raw.split(",") if p.strip()}
    if parts & {"all", "*"}:
        from app.data.clip_slug_lane_map import SPLIT_LANE_KEYS

        return set(SPLIT_LANE_KEYS)
    return parts


def vision_auto_route_is_all() -> bool:
    """True when operator set TBCC_VISION_AUTO_ROUTE_LANES=all (or *).

    Used to suppress soft inbox quarantine cards — vision enrich will route;
    hard-blocked items still get a human card.
    """
    raw = os.getenv("TBCC_VISION_AUTO_ROUTE_LANES") or ""
    parts = {p.strip().lower() for p in raw.split(",") if p.strip()}
    return bool(parts & {"all", "*"})


def lane_route_priority() -> tuple[tuple[str, ...], ...]:
    """Routing tiers. Env format is ``|``-separated tiers of comma-separated lanes."""
    raw = (os.getenv("TBCC_VISION_ROUTE_PRIORITY") or "").strip()
    if not raw:
        return _LANE_ROUTE_TIERS
    tiers = tuple(
        tuple(p.strip().lower() for p in tier.split(",") if p.strip())
        for tier in raw.split("|")
        if tier.strip()
    )
    return tuple(t for t in tiers if t) or _LANE_ROUTE_TIERS


def pick_route_lane(ranked_lanes: list[Any], allowlist: set[str]) -> str | None:
    """Most specific allowlisted lane out of a ranked multi-label result.

    Tier decides first; within a tier the classifier's own ranking wins. Lanes
    absent from every tier sort last, also by model rank.
    """
    if not allowlist:
        return None
    candidates: list[str] = []
    for raw in ranked_lanes or []:
        lane = str(raw or "").strip().lower()
        if lane and lane in allowlist and lane not in candidates:
            candidates.append(lane)
    if not candidates:
        return None
    tiers = lane_route_priority()

    def _rank(lane: str) -> tuple[int, int]:
        tier = next((i for i, names in enumerate(tiers) if lane in names), len(tiers))
        return (tier, candidates.index(lane))

    return min(candidates, key=_rank)


def clip_auto_route_enabled() -> bool:
    """May the local CLIP sidecar move media into a lane on its own? Default no.

    Measured 2026-08-24 on live inbox media: ViT-B/32 put 0.667 on
    "kneeling during oral sex" for a rear-view nude the vision LLM correctly read
    as ``["ass", "big_tits"]``. OpenAI's CLIP was trained with explicit content
    largely filtered out, so its confidence on this material is miscalibrated —
    high score, wrong lane, which is worse than paying for the vision call.
    CLIP still earns its keep as a tag/embedding source; it just does not route.
    Flip this on only after measuring agreement on a real labelled sample.
    """
    return (os.getenv("TBCC_CLIP_AUTO_ROUTE") or "").strip().lower() in ("1", "true", "yes")


def clip_route_min_score() -> float:
    """Aggregated lane score a CLIP-implied lane must clear before it can route."""
    try:
        return float(os.getenv("TBCC_CLIP_ROUTE_MIN_SCORE") or "0.22")
    except ValueError:
        return 0.22


def vision_llm_when_clip_routes() -> bool:
    """Keep paying for the vision LLM even after CLIP placed the media. Off by default."""
    return (os.getenv("TBCC_VISION_LLM_WHEN_CLIP_ROUTES") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def clip_lane_decision(clip_labels: Any) -> dict[str, Any] | None:
    """AOF lanes implied by scored CLIP labels, shaped like a vision decision.

    A catalog entry's ``group`` is authoritative when it names a split lane (the
    AOF lane catalog tags every prompt that way, and its ``group: null`` decoys
    resolve to no lane at all). Catalogs without groups fall back to the slug
    mapper. Returns None when nothing clears ``TBCC_CLIP_ROUTE_MIN_SCORE``, and
    the caller then pays for the vision LLM instead.
    """
    if not isinstance(clip_labels, list) or not clip_labels:
        return None
    from app.data.clip_slug_lane_map import SPLIT_LANE_KEYS, map_clip_slugs_to_lanes

    rows: list[tuple[str, float, str]] = []
    for row in clip_labels:
        if not isinstance(row, dict):
            continue
        slug = str(row.get("slug") or "").strip()
        if not slug:
            continue
        try:
            score = float(row.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        rows.append((slug, score, str(row.get("group") or "").strip().lower()))
    if not rows:
        return None

    lane_scores: dict[str, float] = {}
    if any(group for _, _, group in rows):
        # Lane-tagged catalog: groups are authoritative. Rows without one are the
        # decoys, which exist precisely to absorb probability mass — never fuzzy
        # match their slugs back into a lane.
        for _, score, group in rows:
            if group in SPLIT_LANE_KEYS and score > lane_scores.get(group, 0.0):
                lane_scores[group] = score
    else:
        slugs = [slug for slug, _, _ in rows]
        scores = {slug: score for slug, score, _ in rows}
        lane_scores = dict(map_clip_slugs_to_lanes(slugs, scores=scores))

    floor = clip_route_min_score()
    ranked = sorted(
        ((lane, score) for lane, score in lane_scores.items() if score >= floor),
        key=lambda kv: kv[1],
        reverse=True,
    )
    if not ranked:
        return None
    return {
        "lane_key": ranked[0][0],
        "matching_lanes": [lane for lane, _ in ranked],
        "lane_scores": dict(ranked),
        "source": "clip",
    }


def _maybe_auto_route_vision_lane(
    media_id: int,
    vision_decision: dict[str, Any] | None,
    *,
    source: str = "vision",
) -> None:
    """Move media into the most specific allowlisted lane the classifier named."""
    if not vision_decision:
        return
    allowlist = vision_auto_route_lanes()
    if not allowlist:
        return
    ranked = vision_decision.get("matching_lanes")
    if not isinstance(ranked, list) or not ranked:
        primary = vision_decision.get("lane_key")
        ranked = [primary] if primary else []
    lane_key = pick_route_lane(list(ranked), allowlist)
    if not lane_key:
        return
    try:
        from app.services.gatekeeper_review import enqueue_lane_route_for_media

        result = enqueue_lane_route_for_media(media_id, [lane_key])
        if not result.get("ok"):
            logger.error(
                "%s auto-route enqueue FAILED media_id=%s lane=%s reason=%s",
                source,
                media_id,
                lane_key,
                result.get("reason"),
            )
        else:
            logger.info("%s auto-route media_id=%s lane=%s", source, media_id, lane_key)
    except Exception:
        logger.warning("%s auto-route skipped media_id=%s lane=%s", source, media_id, lane_key, exc_info=True)


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
    from fastapi import HTTPException

    for attempt in range(2):
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

        try:
            data, mime = await _fetch_media_bytes_and_type(ctx)
        except HTTPException as exc:
            if attempt == 0 and exc.status_code == 404:
                continue
            return None
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
        if not img_for_clip and mt in ("photo", "gif", "", "video"):
            # _fetch_classify_bytes_sync already samples one ffmpeg frame for
            # video (media_frame_sample.extract_video_frame_jpeg) — this gate
            # just never invited video in, so vision classify was silently
            # blind to every video deposit (2026-08-22 finding).
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
                        {
                            "slug": row.get("slug"),
                            "score": row.get("score"),
                            "group": row.get("group"),
                        }
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

        # CLIP-first: the local sidecar is free, the vision LLM is metered. When CLIP
        # is confident enough to name a routable lane, place the media from that and
        # never call OpenRouter for it.
        # Gate on the aggregated *lane* score, not clip_confident. That flag compares
        # the top two labels, so two prompts from the same lane splitting the mass
        # (lane-tits-cleavage .34 / lane-tits-topless .33) reads as "unconfident"
        # even though the lane is unambiguous. The catalog's decoys are what keep
        # off-topic media from clearing the floor at all.
        clip_routed = False
        clip_decision = clip_lane_decision(out.get("clip_labels")) if clip_auto_route_enabled() else None
        if clip_decision:
            out["clip_lane_suggestion"] = clip_decision["matching_lanes"]
        if clip_decision and pick_route_lane(
            clip_decision["matching_lanes"], vision_auto_route_lanes()
        ):
            from app.services.media_lane_vision_classify import log_clip_lane_decision

            out["clip_lanes"] = clip_decision["matching_lanes"]
            log_clip_lane_decision(
                db,
                media_id,
                matching_lanes=clip_decision["matching_lanes"],
                scores=clip_decision.get("lane_scores"),
            )
            _maybe_auto_route_vision_lane(media_id, clip_decision, source="clip")
            clip_routed = True
            out["clip_routed"] = True

        if img_for_clip and not (clip_routed and not vision_llm_when_clip_routes()):
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
            try:
                out["auto_approve"] = maybe_auto_approve_storage_deposit_media(db, media_id, out)
            except IntegrityError:
                # Re-drop of media already in the destination pool trips
                # uq_media_file_unique_id_pool_id. That is a duplicate, not an
                # enrich failure — the lane route is already queued, so roll back
                # the pool assignment and let the rest of the run stand rather
                # than poisoning the session and returning ok=False.
                db.rollback()
                logger.info("auto-approve skipped duplicate media_id=%s", media_id)
                out["auto_approve"] = {"applied": False, "reason": "duplicate_in_pool"}
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


def tag_backfill_llm_enabled() -> bool:
    """Pay for an LLM vision pass during backfill too, not just sidecar tags. Off by default (cost)."""
    return (os.getenv("TBCC_TAG_BACKFILL_LLM") or "").strip().lower() in ("1", "true", "yes")


def run_tag_backfill_for_media(media_id: int) -> dict[str, Any]:
    """Tag-only re-enrich for media that already has a lane/approval decision.

    A trimmed ``run_auto_tag_enrich_for_media``: same lustpress/nsfw/CLIP tag
    sources, but never touches routing, pool assignment, gatekeeper verdicts,
    or auto-approve — those are settled facts for already-approved media, and
    re-running them risks duplicate lane routes / library mirror posts. This
    exists purely to widen ``media.tags`` so more of the existing archive is
    reachable from keyword search (aof_content_search ILIKE-matches it).
    """
    from app.database.session import SessionLocal
    from app.models.media import Media
    from app.services.lustpress_metadata import fetch_metadata_for_url, lustpress_enabled, metadata_to_tag_slugs
    from app.services.media_niche_classify import classify_image_bytes_niche
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

        nsfw_tier = (m.nsfw_tier or "unknown").lower()
        nsfw_confident = False
        top_class = ""
        mt = (m.media_type or "").lower()
        img_bytes: bytes | None = None

        if nsfw_classifier_enabled():
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
                db.commit()

        clip_confident = False
        clip_tag_count = 0
        img_for_clip = img_bytes
        if not img_for_clip and mt in ("photo", "gif", "", "video"):
            img_for_clip = _fetch_classify_bytes_sync(media_id)
        if img_for_clip:
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

        if tag_backfill_llm_enabled():
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

        try:
            raw_cj = m.classification_json
            extras = json.loads(raw_cj) if raw_cj else {}
            if not isinstance(extras, dict):
                extras = {}
        except Exception:
            extras = {}
        extras["tag_backfill_done"] = True
        m.classification_json = json.dumps(extras, ensure_ascii=False)
        db.commit()
    except Exception as e:
        logger.exception("tag_backfill failed media_id=%s", media_id)
        return {"ok": False, "error": str(e), "media_id": media_id}
    finally:
        db.close()
    return out


def enqueue_auto_tag_enrich_if_enabled(media_id: int) -> None:
    try:
        from app.services.focus_profile import count_active_import_jobs, pause_auto_tag_work

        if pause_auto_tag_work():
            logger.debug("skip auto_tag_enrich enqueue media_id=%s (focus profile)", media_id)
            return
        if count_active_import_jobs(include_queued=True) > 0:
            logger.debug(
                "skip auto_tag_enrich enqueue media_id=%s (import_jobs_pending)",
                media_id,
            )
            return
    except Exception:
        pass
    if not enrich_pipeline_enabled():
        return
    try:
        from app.workers.media_auto_tag_worker import auto_tag_media_enrich

        auto_tag_media_enrich.delay(int(media_id))
    except Exception:
        logger.warning("enqueue auto_tag_enrich failed (Celery down?) media_id=%s", media_id, exc_info=True)
        try:
            run_auto_tag_enrich_for_media(media_id)
        except Exception:
            logger.exception("sync auto_tag_enrich failed media_id=%s", media_id)
