"""
Assign media.pool_id from tag slugs, NSFW tier, or both (AND).

Enable with TBCC_AUTO_ROUTE_POOL=1. Configure per pool:
- route_match_tag_slugs: comma-separated tbcc_tags.slug (optional if tiers alone are set)
- route_nsfw_tiers: comma-separated sfw|suggestive|explicit|unknown (optional if slugs alone are set)
At least one must be non-empty for the pool to participate. First match by route_priority (asc), id.

TBCC_AUTO_ROUTE_OVERWRITE=1 allows changing pool_id when already set (still respects dedup).
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

VALID_NSFW_TIERS = frozenset({"sfw", "suggestive", "explicit", "unknown"})


def normalize_nsfw_tier(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip().lower()
    if s in VALID_NSFW_TIERS:
        return s
    return "unknown"


def auto_route_pool_enabled() -> bool:
    return os.getenv("TBCC_AUTO_ROUTE_POOL", "").strip().lower() in ("1", "true", "yes")


def auto_route_pool_overwrite() -> bool:
    return os.getenv("TBCC_AUTO_ROUTE_OVERWRITE", "").strip().lower() in ("1", "true", "yes")


def media_tag_slugs_lower(db: Session, media_id: int) -> set[str]:
    from app.models.tbcc_tag import MediaTagLink, TbccTag

    rows = (
        db.query(TbccTag.slug)
        .join(MediaTagLink, MediaTagLink.tag_id == TbccTag.id)
        .filter(MediaTagLink.media_id == media_id)
        .all()
    )
    out: set[str] = set()
    for (slug,) in rows:
        if slug and str(slug).strip():
            out.add(str(slug).strip().lower())
    return out


def _slug_want_set(pool) -> set[str] | None:
    raw = (pool.route_match_tag_slugs or "").strip()
    if not raw:
        return None
    s = {p.strip().lower() for p in raw.split(",") if p.strip()}
    return s or None


def _tier_allow_set(pool) -> frozenset[str] | None:
    raw = (pool.route_nsfw_tiers or "").strip()
    if not raw:
        return None
    allowed: set[str] = set()
    for part in raw.split(","):
        t = normalize_nsfw_tier(part.strip())
        if t:
            allowed.add(t)
    return frozenset(allowed) if allowed else None


def _pool_has_routing_rule(pool) -> bool:
    return _slug_want_set(pool) is not None or _tier_allow_set(pool) is not None


def try_assign_pool_from_tags(db: Session, media_id: int) -> dict:
    """
    Set media.pool_id from the first matching ContentPool. Does not commit.

    Returns { applied: bool, pool_id?: int, reason?: str }.
    """
    if not auto_route_pool_enabled():
        return {"applied": False, "reason": "disabled"}

    from app.models.content_pool import ContentPool
    from app.models.media import Media

    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        return {"applied": False, "reason": "no_media"}

    if media.pool_id is not None and not auto_route_pool_overwrite():
        return {"applied": False, "reason": "pool_already_set"}

    slugs = media_tag_slugs_lower(db, media_id)
    media_tier = normalize_nsfw_tier(getattr(media, "nsfw_tier", None)) or "unknown"

    pools = (
        db.query(ContentPool)
        .filter(
            or_(
                and_(ContentPool.route_match_tag_slugs.isnot(None), ContentPool.route_match_tag_slugs != ""),
                and_(ContentPool.route_nsfw_tiers.isnot(None), ContentPool.route_nsfw_tiers != ""),
            )
        )
        .order_by(ContentPool.route_priority.asc(), ContentPool.id.asc())
        .all()
    )

    for pool in pools:
        if not _pool_has_routing_rule(pool):
            continue
        want_slugs = _slug_want_set(pool)
        if want_slugs is not None:
            if not (slugs & want_slugs):
                continue
        allow_tiers = _tier_allow_set(pool)
        if allow_tiers is not None:
            if media_tier not in allow_tiers:
                continue

        fid = (media.file_unique_id or "").strip()
        if fid:
            conflict = (
                db.query(Media)
                .filter(
                    Media.pool_id == pool.id,
                    Media.file_unique_id == fid,
                    Media.id != media_id,
                )
                .first()
            )
            if conflict:
                logger.info(
                    "auto_route: skip pool_id=%s media_id=%s (file_unique_id already in target pool)",
                    pool.id,
                    media_id,
                )
                continue
        media.pool_id = pool.id
        return {"applied": True, "pool_id": pool.id}

    return {"applied": False, "reason": "no_rule_match"}
