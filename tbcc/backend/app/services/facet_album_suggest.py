"""
Suggest album lineups from pool media using classification_json.facets overlap (no embeddings yet).

Greedy: maximize Jaccard overlap with running union of facets. Telegram caps albums at 10 items.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session


def _facets_lower(media_row: Any) -> set[str]:
    raw = getattr(media_row, "classification_json", None)
    if not raw or not str(raw).strip():
        return set()
    try:
        d = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return set()
    fac = d.get("facets") if isinstance(d, dict) else None
    if not isinstance(fac, list):
        return set()
    return {str(x).strip().lower() for x in fac if x is not None and str(x).strip()}


def suggest_album_media_ids(
    db: Session,
    pool_id: int,
    *,
    seed_media_id: int | None = None,
    limit: int = 10,
    status: str = "approved",
) -> list[int]:
    """Return up to ``limit`` media ids (≤10) from the pool, cohesive by facet overlap."""
    from app.models.media import Media

    lim = min(max(int(limit or 10), 1), 10)
    st = (status or "approved").strip() or "approved"
    rows = (
        db.query(Media)
        .filter(Media.pool_id == pool_id, Media.status == st)
        .order_by(Media.id.asc())
        .all()
    )
    if not rows:
        return []
    by_id = {m.id: m for m in rows}

    if seed_media_id is not None and seed_media_id not in by_id:
        seed_media_id = None

    if seed_media_id is None:
        seed_media_id = rows[0].id

    seed = by_id[seed_media_id]
    selected: list[int] = [seed.id]
    facet_union = set(_facets_lower(seed))
    candidates: set[int] = {m.id for m in rows if m.id != seed.id}

    def jaccard_to_union(f: set[str]) -> float:
        if not facet_union and not f:
            return 0.0
        if not facet_union or not f:
            return 0.05
        inter = len(facet_union & f)
        uni = len(facet_union | f)
        return float(inter) / float(uni) if uni else 0.0

    while len(selected) < lim and candidates:
        best_id: int | None = None
        best_score = -1.0
        for cid in sorted(candidates):
            f = _facets_lower(by_id[cid])
            score = jaccard_to_union(f)
            if score > best_score:
                best_score = score
                best_id = cid
        if best_id is None:
            break
        selected.append(best_id)
        facet_union |= _facets_lower(by_id[best_id])
        candidates.discard(best_id)

    return selected
