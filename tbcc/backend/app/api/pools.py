from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.models.content_pool import ContentPool
from app.models.media import Media
from app.services.pool_cleanup import cascade_delete_pool

router = APIRouter()


class PoolCreate(BaseModel):
    name: str
    channel_id: int
    album_size: int = 5
    interval_minutes: int = 60
    auto_post_enabled: bool = True
    randomize_queue: bool = False
    route_match_tag_slugs: str | None = None
    route_nsfw_tiers: str | None = None
    route_priority: int = 100


class PoolUpdate(BaseModel):
    name: str | None = None
    channel_id: int | None = None
    album_size: int | None = None
    interval_minutes: int | None = None
    auto_post_enabled: bool | None = None
    randomize_queue: bool | None = None
    route_match_tag_slugs: str | None = None
    route_nsfw_tiers: str | None = None
    route_priority: int | None = None


@router.get("/")
def list_pools(db: Session = Depends(get_db)):
    pools = db.query(ContentPool).all()
    result = []
    for p in pools:
        d = orm_to_dict(p)
        cnt = db.query(Media).filter(Media.pool_id == p.id, Media.status == "approved").count()
        d["approved_count"] = cnt
        result.append(d)
    return result


@router.get("/{pool_id}/suggest-album")
def suggest_album_for_pool(
    pool_id: int,
    seed_media_id: int | None = None,
    limit: int = 10,
    status: str = "approved",
    db: Session = Depends(get_db),
):
    """Pick up to ``limit`` (max 10) approved media ids in the pool, grouped by facet overlap."""
    from app.models.content_pool import ContentPool
    from app.services.facet_album_suggest import suggest_album_media_ids

    p = db.query(ContentPool).filter(ContentPool.id == pool_id).first()
    if not p:
        return {"error": "Not found", "media_ids": []}
    ids = suggest_album_media_ids(
        db,
        pool_id,
        seed_media_id=seed_media_id,
        limit=limit,
        status=status,
    )
    return {"pool_id": pool_id, "media_ids": ids, "seed_media_id": seed_media_id}


@router.get("/{pool_id}")
def get_pool(pool_id: int, db: Session = Depends(get_db)):
    p = db.query(ContentPool).filter(ContentPool.id == pool_id).first()
    if not p:
        return {"error": "Not found"}
    return orm_to_dict(p)


@router.post("/", status_code=201)
def create_pool(body: PoolCreate, db: Session = Depends(get_db)):
    pool = ContentPool(
        name=body.name,
        channel_id=body.channel_id,
        album_size=body.album_size,
        interval_minutes=body.interval_minutes,
        auto_post_enabled=body.auto_post_enabled,
        randomize_queue=body.randomize_queue,
        route_match_tag_slugs=(body.route_match_tag_slugs or "").strip()[:512] or None,
        route_nsfw_tiers=(body.route_nsfw_tiers or "").strip()[:128] or None,
        route_priority=int(body.route_priority) if body.route_priority is not None else 100,
    )
    db.add(pool)
    db.commit()
    db.refresh(pool)
    d = orm_to_dict(pool)
    d["approved_count"] = db.query(Media).filter(Media.pool_id == pool.id, Media.status == "approved").count()
    return d


@router.patch("/{pool_id}")
def update_pool(pool_id: int, body: PoolUpdate, db: Session = Depends(get_db)):
    p = db.query(ContentPool).filter(ContentPool.id == pool_id).first()
    if not p:
        return {"error": "Not found"}
    if body.name is not None:
        p.name = body.name
    if body.channel_id is not None:
        p.channel_id = body.channel_id
    if body.album_size is not None:
        p.album_size = body.album_size
    if body.interval_minutes is not None:
        p.interval_minutes = body.interval_minutes
    if body.auto_post_enabled is not None:
        p.auto_post_enabled = body.auto_post_enabled
    if body.randomize_queue is not None:
        p.randomize_queue = body.randomize_queue
    if body.route_match_tag_slugs is not None:
        s = body.route_match_tag_slugs.strip()[:512]
        p.route_match_tag_slugs = s or None
    if body.route_nsfw_tiers is not None:
        t = body.route_nsfw_tiers.strip()[:128]
        p.route_nsfw_tiers = t or None
    if body.route_priority is not None:
        p.route_priority = int(body.route_priority)
    db.commit()
    db.refresh(p)
    d = orm_to_dict(p)
    d["approved_count"] = db.query(Media).filter(Media.pool_id == p.id, Media.status == "approved").count()
    return d


@router.delete("/{pool_id}")
def delete_pool(pool_id: int, db: Session = Depends(get_db)):
    if not cascade_delete_pool(db, pool_id):
        raise HTTPException(status_code=404, detail="Pool not found")
    db.commit()
    return {"deleted": pool_id}
