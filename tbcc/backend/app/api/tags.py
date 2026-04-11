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
