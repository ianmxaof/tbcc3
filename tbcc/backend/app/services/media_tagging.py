"""
Structured tagging + rule-based auto-tag on import.

Keeps Media.tags (comma-separated) in sync with media_tag_links for existing UI/API.
"""

from __future__ import annotations

import re
import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# --- Rule engine: (predicate(media) -> bool, tag_slug, tag_display_name, category, confidence) ---


def _url_host_source(media) -> str:
    raw = (getattr(media, "source_channel", None) or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        try:
            from urllib.parse import urlparse

            return (urlparse(raw).hostname or "").lower()
        except Exception:
            return ""
    return raw.lower()


def _rules() -> list[tuple[Any, str, str, str | None, float]]:
    """Built-in rules; extend via TBCC_TAG_RULES_JSON env in a follow-up if needed."""

    def is_photo(m) -> bool:
        return (getattr(m, "media_type", None) or "").lower() == "photo"

    def is_video(m) -> bool:
        return (getattr(m, "media_type", None) or "").lower() == "video"

    def is_doc(m) -> bool:
        return (getattr(m, "media_type", None) or "").lower() == "document"

    def host_has(sub: str):
        def fn(m) -> bool:
            h = _url_host_source(m)
            return bool(h and sub in h)

        return fn

    return [
        (is_photo, "type-photo", "photo", "type", 0.99),
        (is_video, "type-video", "video", "type", 0.99),
        (is_doc, "type-document", "document", "type", 0.99),
        (host_has("erome"), "src-erome", "erome", "source", 0.85),
        (host_has("coomer"), "src-coomer", "coomer", "source", 0.85),
        (host_has("kemono"), "src-kemono", "kemono", "source", 0.85),
        (host_has("onlyfans"), "src-onlyfans", "onlyfans", "source", 0.85),
        (host_has("motherless"), "src-motherless", "motherless", "source", 0.85),
        (host_has("reddit.com"), "src-reddit", "reddit", "source", 0.85),
        (host_has("redgifs"), "src-redgifs", "redgifs", "source", 0.85),
        (lambda m: "twitter.com" in _url_host_source(m) or "x.com" in _url_host_source(m), "src-x-twitter", "x-twitter", "source", 0.8),
    ]


_SLUG_SAFE = re.compile(r"[^a-z0-9\-]+")


def ensure_tag(db: Session, slug: str, name: str, category: str | None = None):
    from app.models.tbcc_tag import TbccTag

    slug = _SLUG_SAFE.sub("-", slug.lower().strip("-"))[:64] or "tag"
    row = db.query(TbccTag).filter(TbccTag.slug == slug).first()
    if row:
        return row
    row = TbccTag(slug=slug, name=name[:128], category=category[:64] if category else None)
    db.add(row)
    db.flush()
    return row


def rebuild_legacy_tags_string(db: Session, media_id: int) -> None:
    """Set Media.tags from all linked tag names (sorted, comma-separated)."""
    from app.models.media import Media
    from app.models.tbcc_tag import TbccTag, MediaTagLink

    links = (
        db.query(MediaTagLink, TbccTag)
        .join(TbccTag, TbccTag.id == MediaTagLink.tag_id)
        .filter(MediaTagLink.media_id == media_id)
        .all()
    )
    names = sorted({t.name for _, t in links})
    m = db.query(Media).filter(Media.id == media_id).first()
    if m:
        m.tags = ", ".join(names) if names else None
        db.flush()


def merge_manual_tags_from_csv(db: Session, media_id: int, tags_csv: str | None) -> None:
    """
    Replace only **manual** tag links from CSV; keeps rule-based (auto) tags from import.
    Use for extension/dashboard “add topic tags” without wiping type/source rules.
    """
    from app.models.tbcc_tag import MediaTagLink

    db.query(MediaTagLink).filter(
        MediaTagLink.media_id == media_id, MediaTagLink.source == "manual"
    ).delete(synchronize_session=False)
    db.flush()
    if not tags_csv or not str(tags_csv).strip():
        rebuild_legacy_tags_string(db, media_id)
        db.commit()
        return
    parts = [p.strip() for p in re.split(r"[,;]", str(tags_csv)) if p.strip()]
    seen_slugs: set[str] = set()
    for p in parts:
        slug = _SLUG_SAFE.sub("-", p.lower().replace(" ", "-"))[:64] or "tag"
        base = slug
        n = 0
        while slug in seen_slugs:
            n += 1
            slug = (base + "-" + str(n))[:64]
        seen_slugs.add(slug)
        tag = ensure_tag(db, slug, p[:128], "manual")
        existing = (
            db.query(MediaTagLink)
            .filter(MediaTagLink.media_id == media_id, MediaTagLink.tag_id == tag.id)
            .first()
        )
        if existing:
            if existing.source != "manual":
                existing.source = "manual"
                existing.confidence = 1.0
        else:
            db.add(
                MediaTagLink(
                    media_id=media_id,
                    tag_id=tag.id,
                    confidence=1.0,
                    source="manual",
                )
            )
    db.flush()
    rebuild_legacy_tags_string(db, media_id)
    db.commit()


def replace_manual_tags_from_csv(db: Session, media_id: int, tags_csv: str | None) -> None:
    """Replace all tag links with manual assignments from a comma-separated string."""
    from app.models.tbcc_tag import MediaTagLink

    db.query(MediaTagLink).filter(MediaTagLink.media_id == media_id).delete()
    db.flush()
    if not tags_csv or not str(tags_csv).strip():
        rebuild_legacy_tags_string(db, media_id)
        db.commit()
        return
    parts = [p.strip() for p in re.split(r"[,;]", str(tags_csv)) if p.strip()]
    seen_slugs: set[str] = set()
    for p in parts:
        slug = _SLUG_SAFE.sub("-", p.lower().replace(" ", "-"))[:64] or "tag"
        base = slug
        n = 0
        while slug in seen_slugs:
            n += 1
            slug = (base + "-" + str(n))[:64]
        seen_slugs.add(slug)
        tag = ensure_tag(db, slug, p[:128], "manual")
        db.add(
            MediaTagLink(
                media_id=media_id,
                tag_id=tag.id,
                confidence=1.0,
                source="manual",
            )
        )
    db.flush()
    rebuild_legacy_tags_string(db, media_id)
    db.commit()


def clear_rule_tags(db: Session, media_id: int) -> None:
    from app.models.tbcc_tag import MediaTagLink

    db.query(MediaTagLink).filter(
        MediaTagLink.media_id == media_id, MediaTagLink.source == "rule"
    ).delete(synchronize_session=False)
    db.flush()


def apply_rule_tags(db: Session, media) -> list[str]:
    """
    Apply built-in rules; adds/updates rule-sourced links. Does not remove manual tags.
    Returns list of slugs applied.
    """
    from app.models.tbcc_tag import MediaTagLink

    mid = media.id
    applied_slugs: list[str] = []

    # Remove previous auto-rules so re-runs are idempotent
    clear_rule_tags(db, mid)

    for pred, slug, name, cat, conf in _rules():
        try:
            if not pred(media):
                continue
        except Exception as e:
            logger.debug("tag rule predicate error: %s", e)
            continue
        tag = ensure_tag(db, slug, name, cat)
        existing = (
            db.query(MediaTagLink)
            .filter(MediaTagLink.media_id == mid, MediaTagLink.tag_id == tag.id)
            .first()
        )
        if existing:
            if existing.source == "manual":
                continue
            existing.source = "rule"
            existing.confidence = conf
        else:
            db.add(
                MediaTagLink(
                    media_id=mid,
                    tag_id=tag.id,
                    confidence=conf,
                    source="rule",
                )
            )
        applied_slugs.append(slug)
    db.flush()
    rebuild_legacy_tags_string(db, mid)
    db.commit()
    return applied_slugs


def apply_auto_tags_for_new_media(db: Session, media_id: int) -> None:
    """Called after Media row is committed (e.g. import)."""
    from app.models.media import Media

    m = db.query(Media).filter(Media.id == media_id).first()
    if not m:
        return
    try:
        apply_rule_tags(db, m)
    except Exception:
        logger.exception("apply_auto_tags_for_new_media failed media_id=%s", media_id)


def reapply_rules_keep_manual(db: Session, media_id: int) -> dict:
    """Re-run rules; keeps manual tag links. Rebuilds legacy string."""
    from app.models.media import Media

    m = db.query(Media).filter(Media.id == media_id).first()
    if not m:
        return {"ok": False, "error": "not_found"}
    slugs = apply_rule_tags(db, m)
    return {"ok": True, "applied": slugs}
