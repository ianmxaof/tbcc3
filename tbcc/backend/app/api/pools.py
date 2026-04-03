from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.models.content_pool import ContentPool
from app.models.media import Media

router = APIRouter()


class PoolCreate(BaseModel):
    name: str
    channel_id: int
    album_size: int = 5
    interval_minutes: int = 60
    randomize_queue: bool = False


class PoolUpdate(BaseModel):
    name: str | None = None
    channel_id: int | None = None
    album_size: int | None = None
    interval_minutes: int | None = None
    randomize_queue: bool | None = None


@router.get("/")
def list_pools(db: Session = Depends(get_db)):
    from app.models.media import Media

    pools = db.query(ContentPool).all()
    result = []
    for p in pools:
        d = orm_to_dict(p)
        cnt = db.query(Media).filter(Media.pool_id == p.id, Media.status == "approved").count()
        d["approved_count"] = cnt
        result.append(d)
    return result


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
        randomize_queue=body.randomize_queue,
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
    if body.randomize_queue is not None:
        p.randomize_queue = body.randomize_queue
    db.commit()
    db.refresh(p)
    d = orm_to_dict(p)
    d["approved_count"] = db.query(Media).filter(Media.pool_id == p.id, Media.status == "approved").count()
    return d
