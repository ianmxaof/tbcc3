import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.models.scheduled_text_post import ScheduledTextPost
from app.models.channel import Channel
from app.workers.poster_worker import post_scheduled_text

router = APIRouter()


def _normalize_variations(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for x in raw:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


def scheduled_post_to_api_dict(post: ScheduledTextPost) -> dict:
    """JSON-serializable dict with parsed content_variations list."""
    d = orm_to_dict(post)
    d["content_variations"] = post.get_content_variations()
    return d


class ScheduledPostCreate(BaseModel):
    name: str | None = None
    channel_id: int
    """Telegram forum topic id (message_thread_id). Omit or null = main chat / broadcast."""
    message_thread_id: int | None = None
    content: str = ""
    scheduled_at: datetime | None = Field(default=None, description="Required for one-time; omit for recurring")
    interval_minutes: int | None = Field(default=None, description="Required for recurring")
    media_ids: list[int] | None = None
    pool_id: int | None = None
    buttons: list[dict] | None = None
    # When pool_id is set: per-job album size / randomize (overrides pool defaults if set)
    album_size: int | None = None
    pool_randomize: bool | None = None
    # 2+ non-empty strings: captions rotate in order each time the job runs (e.g. hourly A, B, A, …)
    content_variations: list[str] | None = None


class ScheduledPostUpdate(BaseModel):
    name: str | None = None
    channel_id: int | None = None
    message_thread_id: int | None = None
    content: str | None = None
    scheduled_at: datetime | None = None
    interval_minutes: int | None = None
    media_ids: list[int] | None = None
    pool_id: int | None = None
    buttons: list[dict] | None = None
    album_size: int | None = None
    pool_randomize: bool | None = None
    content_variations: list[str] | None = None


@router.get("/")
def list_scheduled_posts(db: Session = Depends(get_db)):
    posts = db.query(ScheduledTextPost).order_by(ScheduledTextPost.scheduled_at).all()
    result = []
    for p in posts:
        d = scheduled_post_to_api_dict(p)
        channel = db.query(Channel).filter(Channel.id == p.channel_id).first()
        d["channel_name"] = channel.name or channel.identifier if channel else None
        result.append(d)
    return result


@router.post("/", status_code=201)
def create_scheduled_post(body: ScheduledPostCreate, db: Session = Depends(get_db)):
    if body.interval_minutes is None and body.scheduled_at is None:
        raise HTTPException(400, "Either scheduled_at (one-time) or interval_minutes (recurring) required")
    vars_norm = _normalize_variations(body.content_variations)
    if len(vars_norm) >= 2:
        content_val = vars_norm[0]
        variations_json = json.dumps(vars_norm)
    elif len(vars_norm) == 1:
        content_val = vars_norm[0]
        variations_json = None
    else:
        content_val = (body.content or "").strip()
        variations_json = None

    if not content_val and not body.media_ids and not body.pool_id:
        raise HTTPException(
            400,
            "Provide caption text, at least two caption variations, or media/pool for scheduled content",
        )

    asize = body.album_size
    if asize is not None:
        asize = min(10, max(1, int(asize)))
    try:
        post = ScheduledTextPost(
            name=body.name,
            channel_id=body.channel_id,
            message_thread_id=body.message_thread_id,
            content=content_val,
            scheduled_at=body.scheduled_at,
            interval_minutes=body.interval_minutes,
            media_ids=json.dumps(body.media_ids) if body.media_ids else None,
            pool_id=body.pool_id if body.pool_id else None,
            buttons=json.dumps(body.buttons) if body.buttons else None,
            album_size=asize,
            pool_randomize=body.pool_randomize,
            content_variations=variations_json,
            caption_rotation_index=None,
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        return scheduled_post_to_api_dict(post)
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"{type(e).__name__}: {str(e)}")


@router.patch("/{post_id}")
def update_scheduled_post(post_id: int, body: ScheduledPostUpdate, db: Session = Depends(get_db)):
    post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == post_id).first()
    if not post:
        return {"error": "Not found"}
    if post.interval_minutes is None and post.sent_at:
        return {"error": "Cannot edit already sent post"}
    fs = getattr(body, "model_fields_set", None) or set()

    if body.name is not None:
        post.name = body.name
    if body.channel_id is not None:
        post.channel_id = body.channel_id
    if "message_thread_id" in fs:
        post.message_thread_id = body.message_thread_id

    if "content_variations" in fs:
        nv = _normalize_variations(body.content_variations)
        if len(nv) >= 2:
            post.content_variations = json.dumps(nv)
            post.content = nv[0]
            post.caption_rotation_index = None
        elif len(nv) == 1:
            post.content_variations = None
            post.content = nv[0]
            post.caption_rotation_index = None
        else:
            post.content_variations = None
            post.caption_rotation_index = None

    if body.content is not None:
        if "content_variations" not in fs:
            post.content = body.content
        else:
            nv2 = _normalize_variations(body.content_variations)
            if len(nv2) < 2:
                post.content = body.content

    if body.scheduled_at is not None:
        post.scheduled_at = body.scheduled_at
    if hasattr(body, "interval_minutes") and body.interval_minutes is not None:
        post.interval_minutes = body.interval_minutes
    if hasattr(body, "media_ids") and body.media_ids is not None:
        post.media_ids = json.dumps(body.media_ids)
    if hasattr(body, "pool_id"):
        post.pool_id = body.pool_id
    if hasattr(body, "buttons") and body.buttons is not None:
        post.buttons = json.dumps(body.buttons)
    if "album_size" in fs:
        v = body.album_size
        post.album_size = min(10, max(1, int(v))) if v is not None else None
    if "pool_randomize" in fs:
        post.pool_randomize = body.pool_randomize
    db.commit()
    db.refresh(post)
    return scheduled_post_to_api_dict(post)


@router.delete("/{post_id}")
def delete_scheduled_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == post_id).first()
    if not post:
        return {"error": "Not found"}
    db.delete(post)
    db.commit()
    return {"deleted": post_id}


@router.post("/{post_id}/trigger")
def trigger_scheduled_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(ScheduledTextPost).filter(ScheduledTextPost.id == post_id).first()
    if not post:
        return {"error": "Not found"}
    is_recurring = post.interval_minutes is not None
    if not is_recurring and post.sent_at:
        return {"error": "Post already sent"}
    channel = db.query(Channel).filter(Channel.id == post.channel_id).first()
    if not channel:
        return {"error": "Channel not found"}
    if is_recurring:
        post.last_posted_at = datetime.utcnow()
        db.commit()
    post_scheduled_text.delay(post_id)
    return {"status": "scheduled", "post_id": post_id}
