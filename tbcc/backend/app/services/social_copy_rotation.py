"""Pick and rotate social copy templates (demote after N uses)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import asc, func
from sqlalchemy.orm import Session

from app.models.social_copy_template import SocialCopyTemplate

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIES = ("paired", "lootgod", "spicy", "network", "affiliate")
REDIS_CATEGORY_KEY = "tbcc:social_copy:category_idx"


def rotation_categories() -> list[str]:
    raw = (os.getenv("TBCC_BUFFER_X_COPY_ROTATION_CATEGORIES") or "").strip()
    if raw:
        return [x.strip().lower() for x in raw.split(",") if x.strip()]
    return list(DEFAULT_CATEGORIES)


def _redis_client():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def pick_rotation_category() -> str:
    cats = rotation_categories()
    if not cats:
        return "network"
    if len(cats) == 1:
        return cats[0]
    try:
        r = _redis_client()
        n = int(r.incr(REDIS_CATEGORY_KEY))
        return cats[(n - 1) % len(cats)]
    except Exception:
        logger.debug("social_copy category rotation fallback", exc_info=True)
        return cats[0]


def pick_social_copy_template(
    db: Session,
    *,
    category: str | None = None,
    surface: str = "x_buffer",
) -> SocialCopyTemplate | None:
    cat = (category or pick_rotation_category()).strip().lower()
    surf = (surface or "x_buffer").strip().lower()
    row = (
        db.query(SocialCopyTemplate)
        .filter(
            SocialCopyTemplate.category == cat,
            SocialCopyTemplate.surface == surf,
            SocialCopyTemplate.is_active.is_(True),
        )
        .order_by(
            asc(SocialCopyTemplate.use_count),
            asc(SocialCopyTemplate.sort_order),
            asc(SocialCopyTemplate.last_used_at),
            asc(SocialCopyTemplate.id),
        )
        .first()
    )
    if not row:
        return None
    mark_template_used(db, row)
    return row


def mark_template_used(db: Session, row: SocialCopyTemplate) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row.use_count = int(row.use_count or 0) + 1
    row.last_used_at = now
    if row.use_count >= int(row.max_uses_before_demote or 2):
        max_order = (
            db.query(func.max(SocialCopyTemplate.sort_order))
            .filter(
                SocialCopyTemplate.category == row.category,
                SocialCopyTemplate.surface == row.surface,
            )
            .scalar()
        ) or 0
        row.use_count = 0
        row.sort_order = int(max_order) + 1
    db.flush()


def list_templates_for_category(
    db: Session,
    *,
    category: str,
    surface: str = "x_buffer",
    limit: int = 100,
) -> list[SocialCopyTemplate]:
    return (
        db.query(SocialCopyTemplate)
        .filter(
            SocialCopyTemplate.category == category.strip().lower(),
            SocialCopyTemplate.surface == surface.strip().lower(),
            SocialCopyTemplate.is_active.is_(True),
        )
        .order_by(asc(SocialCopyTemplate.sort_order), asc(SocialCopyTemplate.id))
        .limit(max(1, min(int(limit), 500)))
        .all()
    )


def template_to_pool_entry(row: SocialCopyTemplate) -> dict[str, str]:
    hint = (row.image_hint or "").strip().lower()
    entry: dict[str, str] = {
        "text": (row.body or "").strip(),
        "utm_campaign": f"social_{row.category}",
        "category": row.category,
        "template_id": str(row.id),
    }
    if hint == "gravatar":
        entry["image"] = "gravatar"
    return entry


def pick_pool_entry(
    db: Session,
    *,
    category: str | None = None,
    surface: str = "x_buffer",
) -> dict[str, str] | None:
    """Pick one rotated template and mark it used (demote after max uses)."""
    row = pick_social_copy_template(db, category=category, surface=surface)
    if not row:
        return None
    return template_to_pool_entry(row)


def build_pool_entries_from_db(
    db: Session,
    *,
    category: str | None = None,
    surface: str = "x_buffer",
    limit: int = 50,
) -> list[dict[str, str]]:
    cat = (category or pick_rotation_category()).strip().lower()
    rows = list_templates_for_category(db, category=cat, surface=surface, limit=limit)
    if not rows:
        return []
    return [template_to_pool_entry(r) for r in rows]


def rotation_status(db: Session) -> dict[str, Any]:
    cats = rotation_categories()
    per_cat: dict[str, int] = {}
    for cat in cats:
        per_cat[cat] = (
            db.query(SocialCopyTemplate)
            .filter(
                SocialCopyTemplate.category == cat,
                SocialCopyTemplate.is_active.is_(True),
            )
            .count()
        )
    return {
        "categories": cats,
        "counts": per_cat,
        "next_category": pick_rotation_category(),
    }
