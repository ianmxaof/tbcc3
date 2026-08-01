"""Token-scored creative RAG — copy + image_prompt catalog search."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.creative_catalog import CreativeCatalogEntry
from app.models.social_copy_template import SocialCopyTemplate

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def search_creative(
    db: Session,
    *,
    entry_type: str | None = None,
    surface: str | None = None,
    campaign: str | None = None,
    lane_key: str | None = None,
    query: str | None = None,
    limit: int = 5,
    require_asset: bool = False,
) -> list[CreativeCatalogEntry]:
    q = db.query(CreativeCatalogEntry).filter(CreativeCatalogEntry.is_active.is_(True))
    if entry_type:
        q = q.filter(CreativeCatalogEntry.entry_type == entry_type.strip().lower())
    if surface:
        q = q.filter(CreativeCatalogEntry.surface == surface.strip().lower())
    if campaign:
        q = q.filter(CreativeCatalogEntry.campaign == campaign.strip().lower())
    if lane_key:
        q = q.filter(CreativeCatalogEntry.lane_key == lane_key.strip().lower())
    if require_asset:
        q = q.filter(CreativeCatalogEntry.asset_url.isnot(None))
    rows = q.order_by(CreativeCatalogEntry.use_count.asc(), CreativeCatalogEntry.id.desc()).limit(
        max(1, min(limit * 4, 40))
    ).all()

    if not query:
        return rows[:limit]

    tokens = _tokenize(query)
    if not tokens:
        return rows[:limit]

    scored: list[tuple[float, CreativeCatalogEntry]] = []
    for row in rows:
        hay = " ".join(
            x
            for x in (
                row.title or "",
                row.campaign or "",
                row.catalog_key or "",
                row.body or "",
                row.subject_delta or "",
                row.tags_json or "",
            )
        )
        hits = len(tokens & _tokenize(hay))
        if hits:
            scored.append((hits - row.use_count * 0.01, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def search_social_copy(
    db: Session,
    *,
    category: str | None = None,
    surface: str = "x_buffer",
    query: str | None = None,
    limit: int = 5,
) -> list[SocialCopyTemplate]:
    q = db.query(SocialCopyTemplate).filter(SocialCopyTemplate.is_active.is_(True))
    if category:
        q = q.filter(SocialCopyTemplate.category == category.strip().lower())
    if surface:
        q = q.filter(SocialCopyTemplate.surface == surface.strip().lower())
    rows = q.order_by(SocialCopyTemplate.use_count.asc()).limit(max(1, min(limit * 4, 40))).all()
    if not query:
        return rows[:limit]
    tokens = _tokenize(query)
    scored: list[tuple[int, SocialCopyTemplate]] = []
    for row in rows:
        hits = len(tokens & _tokenize(row.body or ""))
        if hits:
            scored.append((hits, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def pick_creative_bundle(
    db: Session,
    *,
    copy_category: str | None = None,
    prompt_query: str | None = None,
    campaign: str | None = None,
) -> dict[str, Any]:
    """Return paired copy + optional image prompt for Buffer / goblin surfaces."""
    from app.services.social_copy_rotation import pick_social_copy_template

    copy_row = pick_social_copy_template(db, category=copy_category, surface="x_buffer")
    prompt_rows = search_creative(
        db,
        entry_type="image_prompt",
        campaign=campaign,
        query=prompt_query,
        limit=1,
    )
    prompt_row = prompt_rows[0] if prompt_rows else None
    lv_url = None
    if prompt_row and prompt_row.prompt_gate_key:
        from app.services.prompt_gate_lookup import prompt_gate_url

        lv_url = prompt_gate_url(prompt_row.prompt_gate_key, db=db)

    return {
        "copy": copy_row.body if copy_row else None,
        "copy_category": copy_row.category if copy_row else None,
        "prompt_key": prompt_row.catalog_key if prompt_row else None,
        "prompt_body": prompt_row.body if prompt_row else None,
        "prompt_lv_url": lv_url,
        "asset_url": prompt_row.asset_url if prompt_row else None,
    }


def build_creative_context(
    db: Session,
    *,
    surface: str,
    goal: str | None = None,
    limit: int = 3,
) -> str:
    rows = search_creative(db, surface=surface, query=goal, limit=limit)
    if not rows:
        return ""
    lines = ["Creative catalog:"]
    for r in rows:
        title = (r.title or r.catalog_key or "entry").strip()
        chunk = f"- {title}"
        if r.prompt_gate_key:
            chunk += f" [gate:{r.prompt_gate_key}]"
        if r.asset_url:
            chunk += " [asset]"
        lines.append(chunk)
    return "\n".join(lines)
