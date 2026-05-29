"""Tag definitions + structured links (dashboard / future routing)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db

router = APIRouter()


@router.get("/")
def list_tags(db: Session = Depends(get_db)):
    from app.models.tbcc_tag import TbccTag, MediaTagLink
    from sqlalchemy import func

    counts = (
        db.query(MediaTagLink.tag_id, func.count(MediaTagLink.id))
        .group_by(MediaTagLink.tag_id)
        .all()
    )
    count_map = {tid: n for tid, n in counts}
    rows = db.query(TbccTag).order_by(TbccTag.slug.asc()).all()
    return [
        {
            "id": t.id,
            "slug": t.slug,
            "name": t.name,
            "category": t.category,
            "usage_count": count_map.get(t.id, 0),
        }
        for t in rows
    ]


@router.post("/")
def create_tag(data: dict, db: Session = Depends(get_db)):
    from app.services.media_tagging import ensure_tag

    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    slug = (data.get("slug") or "").strip()
    if not slug:
        slug = name
    cat = (data.get("category") or "").strip() or None
    tag = ensure_tag(db, slug, name, cat)
    db.commit()
    return {"id": tag.id, "slug": tag.slug, "name": tag.name, "category": tag.category}


@router.get("/media/{media_id}")
def get_media_tags(media_id: int, db: Session = Depends(get_db)):
    from app.models.tbcc_tag import TbccTag, MediaTagLink

    rows = (
        db.query(MediaTagLink, TbccTag)
        .join(TbccTag, TbccTag.id == MediaTagLink.tag_id)
        .filter(MediaTagLink.media_id == media_id)
        .all()
    )
    return [
        {
            "slug": t.slug,
            "name": t.name,
            "category": t.category,
            "confidence": link.confidence,
            "source": link.source,
        }
        for link, t in rows
    ]


@router.post("/media/{media_id}/reapply-rules")
def reapply_rules(media_id: int, db: Session = Depends(get_db)):
    from app.services.media_tagging import reapply_rules_keep_manual

    return reapply_rules_keep_manual(db, media_id)


@router.post("/enrich-send")
def enrich_send_tags(data: dict):
    """
    Human-readable tags for extension Saved Messages (Lustpress + NSFW sample + page heuristics).
    Body: { items: [{ source_page_url, media_url, page_host? }], manual_tags?: string[] }
    """
    from app.services.send_tag_enrich import enrich_send_batch

    items = data.get("items")
    if not isinstance(items, list):
        items = []
    manual = data.get("manual_tags")
    if not isinstance(manual, list):
        manual = []
    fast = bool(data.get("fast"))
    default_lp = 1 if fast else 4
    default_nsfw = 1 if fast else 3
    return enrich_send_batch(
        items,
        manual_tags=[str(t) for t in manual if t],
        max_lustpress_pages=min(int(data.get("max_lustpress_pages") or default_lp), 8),
        max_nsfw_samples=min(int(data.get("max_nsfw_samples") or default_nsfw), 6),
        fast=fast,
    )


@router.post("/bulk/enrich-sync")
def bulk_enrich_sync(data: dict, db: Session = Depends(get_db)):
    """
    Run lustpress + NSFW enrich synchronously for recently imported media (library send).
    Use when Celery is down or you want tags before refresh. Caps batch size.
    """
    from app.services.auto_tag_enrich import run_auto_tag_enrich_for_media

    raw_ids = data.get("ids") or data.get("media_ids") or []
    if not isinstance(raw_ids, list):
        raise HTTPException(status_code=400, detail="ids array required")
    cap = min(max(int(data.get("max") or 12), 1), 24)
    results: list[dict] = []
    for mid in raw_ids[:cap]:
        try:
            mid_int = int(mid)
        except (TypeError, ValueError):
            continue
        results.append(run_auto_tag_enrich_for_media(mid_int))
    return {"ok": True, "count": len(results), "results": results}
