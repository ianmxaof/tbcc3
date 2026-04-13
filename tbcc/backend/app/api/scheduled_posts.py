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


def _normalize_attachment_urls(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for x in raw:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out[:10]


def _normalize_album_variants(raw: list | None) -> list[dict]:
    if not raw or not isinstance(raw, list):
        return []
    out: list[dict] = []
    for x in raw:
        if isinstance(x, dict):
            out.append(ScheduledTextPost._normalize_album_variant_entry(x))
    return out


def _has_media_or_promo(body) -> bool:
    av = _normalize_album_variants(getattr(body, "album_variants", None))
    for v in av:
        if v.get("media_ids") or v.get("attachment_urls"):
            return True
    att = _normalize_attachment_urls(getattr(body, "attachment_urls", None))
    if att:
        return True
    mids = getattr(body, "media_ids", None)
    if mids:
        return True
    if getattr(body, "pool_id", None):
        return True
    return False


def scheduled_post_to_api_dict(post: ScheduledTextPost) -> dict:
    """JSON-serializable dict with parsed content_variations, attachment_urls, album_variants."""
    d = orm_to_dict(post)
    d.pop("attachment_urls_json", None)
    d.pop("album_variants_json", None)
    d["content_variations"] = post.get_content_variations()
    d["attachment_urls"] = post.get_attachment_urls()
    d["album_variants"] = post.get_album_variants()
    d["album_order_mode"] = post.album_order_mode or "static"
    raw_btn = d.get("buttons")
    if isinstance(raw_btn, str) and raw_btn.strip():
        try:
            parsed = json.loads(raw_btn)
            d["buttons"] = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            d["buttons"] = []
    elif isinstance(raw_btn, list):
        d["buttons"] = raw_btn
    else:
        d["buttons"] = []
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
    pool_only_mode: bool | None = None
    # 2+ non-empty strings: captions rotate in order each time the job runs (e.g. hourly A, B, A, …)
    content_variations: list[str] | None = None
    # Dashboard promo uploads (/static/promo/…) — same store as Bot Shop; used when pool/media_ids yield no media
    attachment_urls: list[str] | None = None
    # Per-caption album variants (aligned with rotating captions via index % len); overrides flat attachment_urls when set
    album_variants: list[dict] | None = None
    album_order_mode: str | None = None  # static | shuffle | carousel
    send_silent: bool | None = None
    pin_after_send: bool | None = None


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
    pool_only_mode: bool | None = None
    content_variations: list[str] | None = None
    attachment_urls: list[str] | None = None
    album_variants: list[dict] | None = None
    album_order_mode: str | None = None
    send_silent: bool | None = None
    pin_after_send: bool | None = None


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

    if not content_val and not _has_media_or_promo(body):
        raise HTTPException(
            400,
            "Provide caption text, at least two caption variations, media/pool, promotional URLs, or album variants",
        )

    asize = body.album_size
    if asize is not None:
        asize = min(10, max(1, int(asize)))
    av_norm = _normalize_album_variants(body.album_variants)
    att_urls = _normalize_attachment_urls(body.attachment_urls)
    mode = (body.album_order_mode or "").strip().lower()
    if mode not in ("static", "shuffle", "carousel", ""):
        raise HTTPException(400, "album_order_mode must be static, shuffle, or carousel")
    order_mode = mode if mode else None
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
            pool_only_mode=bool(body.pool_only_mode) if body.pool_id else False,
            content_variations=variations_json,
            caption_rotation_index=None,
            attachment_urls_json=None if av_norm else (json.dumps(att_urls) if att_urls else None),
            album_variants_json=json.dumps(av_norm) if av_norm else None,
            album_order_mode=order_mode,
            album_carousel_index=None,
            send_silent=bool(body.send_silent),
            pin_after_send=bool(body.pin_after_send),
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
    fs = getattr(body, "model_fields_set", None) or getattr(body, "__fields_set__", None) or set()

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
    if "pool_only_mode" in fs:
        post.pool_only_mode = bool(body.pool_only_mode) if post.pool_id else False
    if "album_variants" in fs:
        av = _normalize_album_variants(body.album_variants)
        post.album_variants_json = json.dumps(av) if av else None
        if av:
            post.attachment_urls_json = None
    elif "attachment_urls" in fs:
        au = _normalize_attachment_urls(body.attachment_urls)
        post.attachment_urls_json = json.dumps(au) if au else None
    if "album_order_mode" in fs:
        m = (body.album_order_mode or "").strip().lower()
        if m not in ("static", "shuffle", "carousel", ""):
            raise HTTPException(400, "album_order_mode must be static, shuffle, or carousel")
        post.album_order_mode = m if m else None
    if "send_silent" in fs:
        post.send_silent = bool(body.send_silent)
    if "pin_after_send" in fs:
        post.pin_after_send = bool(body.pin_after_send)
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
